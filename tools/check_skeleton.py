#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_skeleton.py —— 角色骨架契约闸（第六十五问：少女底层骨骼 + 四形态兼容）。

为什么需要
----------
引擎里的「骨」有两层，而且一直是各形态自己随手起名的：
  · 刚体骨 = rig.json 的 `groups`（pivot + 位移/旋转/缩放）
  · 网格骨 = rig.json 的 `deformers`（逐顶点形变，可互为父子）
于是「换形态 / 换衣服 / 换 AI 角色」每次都要重新量坐标：
服装写了 `arm_l` 的关节，套到 Q 版上根本没有 `forearm_l` 可挂；动作里那一段身体
**悄悄不动**，画面看着"有点僵"，但没有任何东西会报错。

这个闸把 `<角色>/skeleton.json` 当成契约，逐形态核对：
  1. 骨架自身：id 唯一、父级先声明、无环、pivot 角色合法
  2. 四形态一致性：required 的刚体骨每个形态都要有；真做不到必须写 waiver（带 reason + task）
  3. 反向：形态里出现的骨必须在骨架里声明过（不许野生骨）
  4. 父子关系两边必须一致（骨架写 parent=chest，rig 里写 parent=root 就是红）
  5. pivot 必须落在画布内（量错一个 0，整根骨在画面外转，动作看起来像"抖"）
  6. 每个部件都必须挂到一根已声明的骨上（`group` 必须解析）
  7. `parts[].deformer` 与 `forms.<form>.mesh_bones` 里点名的网格骨必须真的存在
  8. 挂点（socket）的父骨必须存在 —— 父骨没有，挂点就是死代码

用法
----
  python3 tools/check_skeleton.py --root .                 # 所有有 skeleton.json 的角色
  python3 tools/check_skeleton.py --root . --character xiaoxun -v
  python3 tools/check_skeleton.py --self-test               # 负控：坏骨架必须判红

退出码：0 全过；1 有问题。纯标准库，不依赖 venv。
"""
from __future__ import annotations

import argparse
import glob
import io
import json
import os
import shutil
import tempfile

_fail = 0
_n = 0
_quiet = False
_verbose = False
_silent = False     # 负控跑用例时把细则静音，只留"期望红/绿"那一行


def check(name, cond, detail=""):
    global _fail, _n
    _n += 1
    ok = bool(cond)
    if not ok:
        _fail += 1
    if (not ok or (not _quiet and (_verbose or not ok))) and not _silent:
        print(("  [x] " if ok else "  [!] ") + name + (("  " + detail) if detail else ""))
    return ok


def info(name, detail=""):
    if not _quiet and not _silent:
        print("  [i] " + name + (("  " + detail) if detail else ""))


def load_jsonc(path):
    """读 json（容忍 // 注释与尾逗号：工程里几个 rig 用过，读法要一致）。"""
    txt = io.open(path, encoding="utf-8").read()
    out, i, n = [], 0, len(txt)
    in_str = False
    while i < n:
        c = txt[i]
        if in_str:
            out.append(c)
            if c == "\\" and i + 1 < n:
                out.append(txt[i + 1])
                i += 2
                continue
            if c == '"':
                in_str = False
            i += 1
            continue
        if c == '"':
            in_str = True
            out.append(c)
            i += 1
            continue
        if c == "/" and i + 1 < n and txt[i + 1] == "/":
            while i < n and txt[i] != "\n":
                i += 1
            continue
        out.append(c)
        i += 1
    s = "".join(out)
    # 去尾逗号
    res, i, in_str = [], 0, False
    while i < len(s):
        c = s[i]
        if in_str:
            res.append(c)
            if c == "\\" and i + 1 < len(s):
                res.append(s[i + 1])
                i += 2
                continue
            if c == '"':
                in_str = False
            i += 1
            continue
        if c == '"':
            in_str = True
        if c == ",":
            j = i + 1
            while j < len(s) and s[j] in " \t\r\n":
                j += 1
            if j < len(s) and s[j] in "}]":
                i += 1
                continue
        res.append(c)
        i += 1
    return json.loads("".join(res))


# ────────────────────────────────────────────────────────── 骨架自身的合法性
def check_skeleton_doc(sk, path):
    """① 骨架文件本身写得对不对（顺序、重复、环、kind、canvas）。"""
    good = True
    bones = sk.get("bones")
    if not check("骨架有 bones 数组", isinstance(bones, list) and len(bones) > 0, path):
        return False
    canvas = sk.get("canvas") or []
    if not check("骨架声明了 canvas [w,h]",
                 isinstance(canvas, list) and len(canvas) == 2 and
                 all(isinstance(v, (int, float)) and v > 0 for v in canvas), str(canvas)):
        good = False

    seen = {}
    kinds = {"rigid", "mesh", "socket"}
    for b in bones:
        bid = b.get("id")
        if not check("骨有 id", bool(bid), path):
            good = False
            continue
        if not check("骨 id 唯一（%s）" % bid, bid not in seen):
            good = False
            continue
        if not check("骨的 kind 合法（%s）" % bid, b.get("kind") in kinds, str(b.get("kind"))):
            good = False
        par = b.get("parent")
        if par in (None, ""):
            if not check("只有 root 可以没有父级（%s）" % bid, bid == "root",
                         "没写 parent 的骨会被当成根，树就断了"):
                good = False
        else:
            if not check("父级 %s 必须先声明（%s）" % (par, bid), par in seen,
                         "骨架里骨必须按「父在子前」排" if par not in seen else ""):
                good = False
        seen[bid] = b

    # 环（父在子前已经能挡住大多数，但显式判一遍，报错更准确）
    for bid in seen:
        chain, cur = set(), bid
        while cur in seen:
            if cur in chain:
                check("骨架里没有父子成环（%s）" % bid, False)
                good = False
                break
            chain.add(cur)
            cur = seen[cur].get("parent") or ""
    return good and check("骨架没有父子成环", True)


# ────────────────────────────────────────────────────────── 形态与骨架对账
def check_form(root, char_id, sk, form, rig_path):
    before = _fail
    if not _quiet:
        print("\n== %s / %s ==" % (char_id, form))
    try:
        rig = load_jsonc(rig_path)
    except Exception as e:  # noqa: BLE001
        check("rig.json 能解析", False, "%s: %s" % (rig_path, e))
        return

    bones = {b["id"]: b for b in sk.get("bones", []) if b.get("id")}
    canvas = sk.get("canvas") or [0, 0]
    groups = rig.get("groups") or {}
    parts = rig.get("parts") or []
    defs = {d.get("id"): d for d in (rig.get("deformers") or []) if d.get("id")}
    waivers = {}
    for w in sk.get("waivers") or []:
        if w.get("form") == form:
            waivers[w.get("bone")] = w

    # ② required 刚体骨：该形态必须都有，除非有合规 waiver
    for b in sk.get("bones", []):
        if b.get("kind") != "rigid" or not b.get("required"):
            continue
        bid = b["id"]
        if bid in groups:
            continue
        w = waivers.get(bid)
        if w:
            ok = check("缺骨 %s 的豁免写清了原因与任务" % bid,
                       bool(w.get("reason")) and bool(w.get("task")), str(w))
            if not ok:
                continue
        else:
            check("必需骨 %s 在该形态存在（四形态共用同一套骨名）" % bid, False,
                  "缺了就是「动作里这一段不动」；真做不到请写进 skeleton.json 的 waivers")

    # ③ 反向：形态里的骨必须声明过（不许野生骨）
    for gid in groups:
        check("形态里的骨 %r 在骨架里声明过" % gid, gid in bones,
              "野生骨 = 换形态/换衣服时没人知道它是什么")

    # ④ 父子关系两边一致
    for gid, g in groups.items():
        want = (bones.get(gid) or {}).get("parent") or ""
        have = g.get("parent") or ""
        check("骨 %s 的父级与骨架一致" % gid, want == have,
              "骨架写 %r，rig 写 %r" % (want, have))

    # ⑤ pivot 在画布内
    w, h = float(canvas[0]), float(canvas[1])
    for gid, g in groups.items():
        pv = g.get("pivot")
        if not (isinstance(pv, list) and len(pv) == 2):
            check("骨 %s 有 pivot" % gid, False, str(pv))
            continue
        x, y = float(pv[0]), float(pv[1])
        check("骨 %s 的 pivot 在画布内" % gid, -1 <= x <= w + 1 and -1 <= y <= h + 1,
              "(%.1f,%.1f) 画布 %dx%d" % (x, y, w, h))

    # ⑥ 每个部件都挂到已声明的骨上
    #    "网格骨绑定"有两种合法写法：① parts[].deformer 直接点名一根链；
    #    ② 网格形变器自己写 deformers[].part（引擎按部件匹配）。两种都算挂上，
    #    只数 ① 会把 S2 之前的老 rig 全判成"没骨"——这条口径 2026-10-25 修过一次。
    mesh_on_part = {}
    for did, d in defs.items():
        if d.get("part"):
            mesh_on_part.setdefault(d["part"], []).append(did)
    bound = 0
    for p in parts:
        pid = p.get("id", "?")
        gid = p.get("group")
        if not gid:
            # 没有 group 的部件 = 不跟任何骨动（只能做绝对定位的贴纸）
            check("部件 %s 声明了 group" % pid, False, "没 group 的件永远不会跟着动")
            continue
        check("部件 %s 的骨 %r 已声明" % (pid, gid), gid in groups, "解析不到的骨")
        if p.get("deformer") or mesh_on_part.get(pid):
            bound += 1
        if p.get("deformer"):
            check("部件 %s 挂的网格骨 %r 存在" % (pid, p["deformer"]),
                  p["deformer"] in defs, "deformer 写了但没定义 → 加载会报错")
    if parts:
        info("网格骨绑定覆盖率 %d/%d" % (bound, len(parts)),
             "（= 有网格骨的件数；0 就是「只有刚体骨在动」）")
    # ⑥b 骨链：写了 parent 的网格骨，父节点必须排在前面（引擎按顺序连乘，父在后就是错的）
    order = {d: i for i, d in enumerate(defs)}
    for did, d in defs.items():
        par = d.get("parent")
        if not par:
            continue
        if not check("网格骨 %s 的父节点 %r 存在" % (did, par), par in defs,
                     "链断了：子节点还留着 parent 指向没人定义的节点"):
            continue
        check("网格骨 %s 的父节点排在它前面（引擎按顺序连乘）" % did,
              order[par] < order[did], "父 %s @%d / 子 @%d" % (par, order[par], order[did]))

    # ⑦ forms.<form>.mesh_bones 点名的网格骨必须真的存在
    fb = ((sk.get("forms") or {}).get(form) or {}).get("mesh_bones") or {}
    for role, ids in fb.items():
        if role not in bones:
            check("mesh_bones 的角色 %r 在骨架里声明过" % role, False,
                  "角色名必须来自 bones[].id")
        for did in (ids if isinstance(ids, list) else [ids]):
            check("网格骨 %s→%r 在该形态存在" % (role, did), did in defs,
                  "rig.json 的 deformers 里找不到")
    # ⑦b 骨链不许退回"平铺"：至少有一个网格骨写了 parent。
    #     2026-10-25（第六十六问 S2）之前，两个形态的 25 个网格全是平铺的 ——
    #     表现是"头发能整块弯一下"，做不出发根/发梢分层。这条闸保证它不会悄悄退回去。
    chains = [d for d, v in defs.items() if v.get("parent")]
    check("形态 %s 至少有一条骨链（deformers[].parent）" % form, bool(chains),
          "全是平铺网格 = 每件只能整体弯，没有分层；这是 S2 之前的状态")

    # ⑦c 声明了"继承"的件（T66.10b）：自己没有网格，逐顶点场从另一件借。
    #     为什么要在契约里写一份：它是**替代了一段手抄点表**的机制，
    #     一旦 rig 上的 inherit_from 被谁顺手删了，里布就变成一块钉死的布 ——
    #     画面上只在裙摆甩开时才看得出来，静态截图完全正常。
    ip = ((sk.get("forms") or {}).get(form) or {}).get("inherit_parts") or {}
    for pid, spec in ip.items():
        part = next((x for x in parts if x.get("id") == pid), None)
        if part is None:
            continue                       # 该形态没有这件，跳过（Q 版就是这种情况）
        check("继承件 %s 声明了 inherit_from" % pid,
              part.get("inherit_from") == spec.get("from"),
              "rig 上是 %r，契约写 %r" % (part.get("inherit_from"), spec.get("from")))
        got = part.get("warp_inherit", 1.0)
        want = float(spec.get("strength", 1.0))
        check("继承件 %s 的继承强度对得上契约" % pid, abs(got - want) < 1e-6,
              "rig 上 %.3f，契约写 %.3f —— 两边不一致说明有人只改了一边" % (got, want))
        check("继承件 %s 自己没有网格（继承了就别再叠一份手抄表）" % pid,
              not [d for d, v in defs.items() if v.get("part") == pid],
              "还挂着网格：%s" % [d for d, v in defs.items() if v.get("part") == pid])

    # 反向：形态里每一个带 part 的形变器都该被某个角色收编（否则没人知道它归哪根骨）
    claimed = set()
    for ids in fb.values():
        claimed.update(ids if isinstance(ids, list) else [ids])
    orphans = [d for d, v in defs.items() if v.get("part") and d not in claimed]
    if defs:
        check("每个网格骨都被 mesh_bones 收编", not orphans,
              "没收编：%s" % (orphans[:8] if orphans else "无"))

    # ⑧ 挂点：父骨必须存在（父骨没有，挂点就是死代码）
    for b in sk.get("bones", []):
        if b.get("kind") != "socket":
            continue
        par = b.get("parent")
        if par in groups:
            continue
        if par in defs:
            continue
        wv = waivers.get(par)
        check("挂点 %s 的父骨 %r 在该形态可用" % (b["id"], par), bool(wv),
              "父骨缺了，这个挂点在任何形态上都挂不上东西")

    # ⑧b 挂点真的落到 rig 上了（T66.19 / S4）。
    #     只写在文档里的挂点等于没有：配件挂上来会在装载期报"未知的挂点"。
    #     反向也要查 —— rig 里冒出一个骨架没声明的挂点，说明有人手改过 rig。
    rig_socks = rig.get("sockets") or {}
    for sid, sd in rig_socks.items():
        b = bones.get(sid) or {}
        check("rig 里的挂点 %s 在骨架里声明过" % sid, b.get("kind") == "socket",
              "骨架里没有这个 kind:socket 的骨")
        check("挂点 %s 的父骨与骨架一致" % sid,
              (b.get("parent") or "") == (sd.get("group") or ""),
              "骨架写 %r，rig 写 %r" % (b.get("parent"), sd.get("group")))
        pv = sd.get("pos")
        if isinstance(pv, list) and len(pv) == 2:
            check("挂点 %s 的坐标在画布内" % sid,
                  -w * 0.2 <= float(pv[0]) <= w * 1.2 and
                  -h * 0.2 <= float(pv[1]) <= h * 1.2, str(pv))
        else:
            check("挂点 %s 有坐标 pos" % sid, False, str(pv))
    for b in sk.get("bones", []):
        if b.get("kind") != "socket" or (b.get("parent") or "") not in groups:
            continue                       # 该形态连父骨都没有，跳过（required:false 的情形）
        check("挂点 %s 已落到该形态的 rig 上" % b["id"], b["id"] in rig_socks,
              "父骨在、挂点却不在 rig 里 —— 生成器漏了一段")
    return _fail - before


def check_contract_status(sk, forms):
    """⑧ 骨架的 status：「只写了契约」和「做完了」必须分得开（T66.23）。

    为什么要这条：七个角色原来只有 character.json，看起来"有人设"，实际上一点美术
    都没有；反过来，脚手架刚生成 skeleton.json 的时候，目录看上去也和做完的角色一样。
    光看目录分不出来，就必须写在文件里、由闸来对账：
      · status 缺省 = full（老角色不受影响）
      · contract_only ⇒ todo 必须非空（说清还缺什么），且不能已经有形态 rig
      · full          ⇒ 至少得有一个形态的 rig
    """
    st = sk.get("status", "full")
    if not check("骨架 status 合法（%s）" % sk.get("character"),
                 st in ("full", "contract_only"), str(st)):
        return st
    if st == "contract_only":
        todo = sk.get("todo")
        ok = (isinstance(todo, list) and len(todo) > 0 and
              all(isinstance(t, str) and t.strip() for t in todo))
        check("contract_only 的骨架有非空 todo（说清还缺什么素材）", ok,
              "空 todo 等于「什么都没做，也没记下来」" if not ok else "")
        check("contract_only 的骨架还没有形态 rig（有了就该改成 full）",
              not forms, "已有 %s 的 rig；把 status 改成 full 再跑一次" % (forms,))
    else:
        check("full 的角色至少有一个形态 rig", bool(forms),
              "骨架写完了但没有任何形态素材 —— 要么补素材，要么改成 contract_only 并写 todo")
    return st


def lint_character(root, char_id, logs):
    before = _fail
    base = os.path.join(root, "characters", char_id)
    skp = os.path.join(base, "skeleton.json")
    if not check("有骨架契约 skeleton.json（%s）" % char_id, os.path.isfile(skp),
                 "没有它，四形态/换装/换角色就还是各写各的" if not os.path.isfile(skp) else ""):
        return _fail - before
    try:
        sk = load_jsonc(skp)
    except Exception as e:  # noqa: BLE001
        check("骨架能解析", False, str(e))
        return _fail - before
    if not _quiet:
        print("\n== 骨架 %s（%s）==" % (sk.get("skeleton"), char_id))
    if not check_skeleton_doc(sk, skp):
        logs.append("骨架自身不合法，形态对账跳过")
        return _fail - before
    forms = sorted(d for d in os.listdir(os.path.join(base, "forms"))
                   if os.path.isfile(os.path.join(base, "forms", d, "rig.json"))) \
        if os.path.isdir(os.path.join(base, "forms")) else []
    contract_only = check_contract_status(sk, forms) == "contract_only"
    if not contract_only:   # 契约态由上面那条管，不重复报「没有 rig」
        check("至少有一个形态的 rig", bool(forms), str(forms))
    for f in forms:
        check_form(root, char_id, sk, f, os.path.join(base, "forms", f, "rig.json"))
    if not _quiet:
        print("  [i] 形态清单：%s（四个形态共用同一套骨名是这条契约的目的）" % (forms or "无"))
    return _fail - before


# ────────────────────────────────────────────────────────── 负控
def _mk(tmp, rig_over=None, sk_over=None, drop_bones=(), add_bones=()):
    """造一个最小角色包：一个形态 teen，骨架 + rig 两边都对得上。"""
    base = os.path.join(tmp, "characters", "pktest")
    fdir = os.path.join(base, "forms", "teen")
    os.makedirs(fdir, exist_ok=True)
    bones = [
        {"id": "root", "parent": None, "kind": "rigid", "required": True},
        {"id": "chest", "parent": "root", "kind": "rigid", "required": True},
        {"id": "head", "parent": "chest", "kind": "rigid", "required": True},
        {"id": "hair_side_l", "parent": "head", "kind": "mesh", "required": False},
        {"id": "socket_head_top", "parent": "head", "kind": "socket", "required": False},
    ]
    bones = [b for b in bones if b["id"] not in drop_bones] + list(add_bones)
    sk = {"schema_version": "1.0", "character": "pktest", "skeleton": "t",
          "canvas": [200, 200], "bones": bones, "waivers": [],
          "forms": {"teen": {"mesh_bones": {"hair_side_l": ["hair_wave"]}}}}
    sk.update(sk_over or {})
    rig = {"schema_version": "1.0", "groups": {
        "root": {"pivot": [100, 200], "parent": ""},
        "chest": {"pivot": [100, 120], "parent": "root"},
        "head": {"pivot": [100, 60], "parent": "chest"}},
        "parts": [{"id": "h", "file": "h.png", "group": "head", "layer": 1,
                   "pos": [10, 10], "anchor": [0, 0], "deformer": "hair_root"}],
        "deformers": [{"id": "hair_root", "pivot": [100, 60]},
                      {"id": "hair_mid", "parent": "hair_root", "pivot": [100, 90]},
                      {"id": "hair_wave", "part": "h", "parent": "hair_mid",
                       "cols": 1, "rows": 1,
                       "points": [{"c": 0, "r": 0, "dx": 0}]}],
        # 挂点（T66.19）：骨架声明了 socket_head_top，rig 就得把它落下来
        "sockets": {"socket_head_top": {"group": "head", "pos": [100, 40]}},
        "actions": [{"id": "idle", "loop": True, "channels": []}]}
    for k, v in (rig_over or {}).items():
        rig[k] = v
    io.open(os.path.join(base, "skeleton.json"), "w", encoding="utf-8").write(
        json.dumps(sk, ensure_ascii=False, indent=1))
    io.open(os.path.join(fdir, "rig.json"), "w", encoding="utf-8").write(
        json.dumps(rig, ensure_ascii=False, indent=1))
    return base


def self_test(_root):
    """每条规则都要被一个故意写坏的角色包打红过（否则闸只是永远通过的 print）。"""
    global _quiet, _verbose, _silent
    _quiet, _verbose = False, False
    cases = []

    def run(name, expect_red, **kw):
        global _silent
        tmp = tempfile.mkdtemp(prefix="zskel_")
        try:
            _mk(tmp, **kw)
            before = _fail
            _silent = True
            lint_character(tmp, "pktest", [])
            _silent = False
            red = _fail > before
            cases.append((name, expect_red, red))
            print("  %-52s 期望%s  实际%s" % (name, "红" if expect_red else "绿",
                                              "红" if red else "绿"))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    print("== 负控：每个坏骨架 / 坏 rig 都必须被判红 ==")
    run("合法包（应当全绿）", False)
    run("骨架里父级没先声明", True, sk_over={"bones": [
        {"id": "chest", "parent": "root", "kind": "rigid", "required": True},
        {"id": "root", "parent": None, "kind": "rigid", "required": True}]})
    run("骨架里父子成环", True, sk_over={"bones": [
        {"id": "root", "parent": None, "kind": "rigid", "required": True},
        {"id": "a", "parent": "b", "kind": "rigid", "required": False},
        {"id": "b", "parent": "a", "kind": "rigid", "required": False}]})
    run("必需骨在形态里缺失且没豁免", True, rig_over={"groups": {
        "root": {"pivot": [100, 200], "parent": ""},
        "head": {"pivot": [100, 60], "parent": "chest"}}})
    run("缺骨豁免缺 reason/task", True,
        rig_over={"groups": {"root": {"pivot": [100, 200], "parent": ""}}},
        sk_over={"waivers": [{"form": "teen", "bone": "chest"}]})
    run("形态里有骨架没声明的野生骨", True, rig_over={"groups": {
        "root": {"pivot": [100, 200], "parent": ""},
        "chest": {"pivot": [100, 120], "parent": "root"},
        "head": {"pivot": [100, 60], "parent": "chest"},
        "wing_l": {"pivot": [50, 70], "parent": "chest"}}})
    run("父子关系两边不一致", True, rig_over={"groups": {
        "root": {"pivot": [100, 200], "parent": ""},
        "chest": {"pivot": [100, 120], "parent": ""},
        "head": {"pivot": [100, 60], "parent": "chest"}}})
    run("pivot 跑到画布外", True, rig_over={"groups": {
        "root": {"pivot": [100, 900], "parent": ""},
        "chest": {"pivot": [100, 120], "parent": "root"},
        "head": {"pivot": [100, 60], "parent": "chest"}}})
    run("部件没写 group", True, rig_over={"parts": [
        {"id": "h", "file": "h.png", "layer": 1, "pos": [10, 10], "anchor": [0, 0]}]})
    run("部件 group 指向不存在的骨", True, rig_over={"parts": [
        {"id": "h", "file": "h.png", "group": "nope", "layer": 1,
         "pos": [10, 10], "anchor": [0, 0]}]})
    run("mesh_bones 指向不存在的网格骨", True,
        sk_over={"forms": {"teen": {"mesh_bones": {"hair_side_l": ["nope"]}}}})
    run("网格骨没被 mesh_bones 收编", True,
        sk_over={"forms": {"teen": {"mesh_bones": {}}}})
    run("网格全是平铺的（没有骨链）", True, rig_over={"deformers": [
        {"id": "hair_wave", "part": "h", "cols": 1, "rows": 1,
         "points": [{"c": 0, "r": 0, "dx": 0}]}]})
    run("骨架声明的挂点没落到 rig 上", True,
        rig_over={"sockets": {}})
    run("rig 里的挂点父骨与骨架不一致", True,
        rig_over={"sockets": {"socket_head_top": {"group": "chest", "pos": [100, 40]}}})
    run("挂点的父骨不存在", True,
        sk_over={"bones": [
            {"id": "root", "parent": None, "kind": "rigid", "required": True},
            {"id": "chest", "parent": "root", "kind": "rigid", "required": True},
            {"id": "head", "parent": "chest", "kind": "rigid", "required": True},
            {"id": "hair_side_l", "parent": "head", "kind": "mesh", "required": False},
            {"id": "socket_head_top", "parent": "nope", "kind": "socket", "required": False}]})
    # ⑧ 契约态（T66.23）：脚手架生成的角色不能看起来像做完的角色
    run("status 写了不认识的值", True, sk_over={"status": "done"})
    run("contract_only 却没有 todo", True,
        sk_over={"status": "contract_only", "todo": []})
    run("contract_only 的 todo 里混了空串", True,
        sk_over={"status": "contract_only", "todo": ["做素材", "  "]})
    run("contract_only 但已经有形态 rig", True,
        sk_over={"status": "contract_only", "todo": ["做素材"]})

    bad = [c[0] for c in cases if c[1] != c[2]]
    if bad:
        print("\n负控失败：%d / %d 例不符合预期 → %s" % (len(bad), len(cases), bad))
        return 1
    print("\n负控全部符合预期：%d 例（例内判红是被测的坏包，不是闸坏了）" % len(cases))
    return 0


def main():
    global _quiet, _verbose
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    ap.add_argument("--character", default=None)
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--quiet", action="store_true")
    ap.add_argument("-v", "--verbose", action="store_true")
    a = ap.parse_args()
    _quiet = a.quiet
    _verbose = a.verbose
    root = os.path.abspath(a.root)

    if a.self_test:
        return self_test(root)

    if a.character:
        chars = [a.character]
    else:
        chars = sorted(os.path.basename(os.path.dirname(p)) for p in
                       glob.glob(os.path.join(root, "characters", "*", "skeleton.json")))
    if not chars:
        print("没有找到任何 skeleton.json：%s/characters/*/skeleton.json" % root)
        return 1
    logs = []
    for c in chars:
        lint_character(root, c, logs)
    print("\n合计 %d 项，%d 项不通过 → %s" %
          (_n, _fail, "骨架契约成立" if _fail == 0 else "骨架和形态对不上，先修骨架再谈动作"))
    return 0 if _fail == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
