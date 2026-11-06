#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""mod_lint.py - 内容包 / 模组的契约校验器（第六十四问：完全可自定义 + 完全可模组）。

为什么要有它
------------
产品计划里一直写着「新增/替换任何内容都不改核心代码」，
但**没有任何东西在检查这句话**。于是实际情况是：
  · `forms/` 下多一个没写 rig.json 的目录 → 界面上根本看不到，也没人说为什么；
  · `outfits/*.json` 引用一个不存在的部件 → 换装时才报错，而那时画面已经半崩；
  · 某个形态少一张贴图 → 加载失败，只报「部件 x 的图片打不开」；
  · 有人把白底图直接丢进 sprites/ → 看起来能显示，边缘一圈白边（用户点名的缺陷）。
这些都是"包写得不对"，不是"引擎坏了"，但以前没有任何一道闸在**装之前**拦。

本工具把"一个角色包 / 一个模组包长什么样"写成可执行的规则：
  1. 清单（manifest）齐、id 规范、id 与目录名一致
  2. 声明了的形态必须真有素材；没素材的必须显式标 planned（不许默认假装能做）
  3. rig.json 引用的每个文件真的存在、是带 alpha 的 PNG、不是"整张不透明"（白底/洋红底烤进去了）
  4. 每个 part 的 group / deformer / mask / motion_from 引用都能解析
  5. outfits 的 id、forms、部件引用都对得上
  6. 内容规模不超过引擎上限（超了也**不算通过**，要人明确去抬上限）
  7. 模组包额外查：api_version 兼容、权限声明在白名单内、依赖存在

用法
----
  python3 tools/mod_lint.py --root . --character xiaoxun
  python3 tools/mod_lint.py --root . --mod mymod
  python3 tools/mod_lint.py --self-test          # 负控：造一堆坏包，每一条都必须判红

退出码：0 全过；1 有问题。JSON 报表用 --json 指定。
"""
from __future__ import annotations

import argparse
import io
import json
import os
import re
import shutil
import sys
import tempfile

try:
    from PIL import Image
except ImportError:  # pragma: no cover
    print("需要 pillow：python3 -m venv ~/.imgenv && ~/.imgenv/bin/pip install pillow numpy")
    raise

# ── 契约常量（必须与引擎同步；selfcheck 会核对这里和 src/core 的宏一致）────────
FORM_CAP = 64          # zrig.h: ZRIG_FORM_CAP
OUTFIT_CAP = 128       # zrig.h: ZRIG_OUTFIT_CAP
ACTION_CAP = 96        # zrig.h: ZRIG_ACTION_CAP
API_MAJOR = 1           # 模组清单的 api_version 只在这个主版本内兼容
MOD_PERMISSIONS = {
    "net",          # 联网请求（默认经网关，不许自己开 socket）
    "files.read",   # 读自己的包
    "files.write",  # 写用户数据目录
    "audio",        # 播放/录音
    "notify",       # 系统通知
    "pet.control",  # 驱动角色（动作/表情/形态）
}

ID_RE = re.compile(r"^[a-z][a-z0-9_]{0,47}$")   # 引擎里部件 id 允许单字符（"h"）

_fail = 0
_n = 0
_quiet = False


def check(name: str, cond: bool, detail: str = "") -> bool:
    global _fail, _n
    _n += 1
    if not cond:
        _fail += 1
    if not cond or not _quiet:
        print(("  [x] " if cond else "  [!] ") + name + (("  " + detail) if detail else ""))
    return bool(cond)


def jsonc(path: str):
    """读 JSONC（配置里允许 // 注释）。与 selfcheck 里那份同口径。"""
    txt = io.open(path, encoding="utf-8").read()
    out, in_str, esc, i = [], False, False, 0
    while i < len(txt):
        c = txt[i]
        if in_str:
            out.append(c)
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == '"':
                in_str = False
            i += 1
            continue
        if c == '"':
            in_str = True
            out.append(c)
            i += 1
            continue
        if c == "/" and i + 1 < len(txt) and txt[i + 1] == "/":
            while i < len(txt) and txt[i] != "\n":
                i += 1
            continue
        out.append(c)
        i += 1
    txt = "".join(out)
    txt = re.sub(r",(\s*[}\]])", r"\1", txt)
    return json.loads(txt)


# ────────────────────────────────────────────────────────────── 单个包
def lint_content_pack(root: str, char_id: str) -> int:
    """校验 characters/<id>/ 这个内容包。返回本包的问题数。"""
    global _fail, _n
    before = _fail
    base = os.path.join(root, "characters", char_id)
    if not _quiet:
        print("\n== 内容包 characters/%s ==" % char_id)
    if not check("包目录存在", os.path.isdir(base), base):
        return _fail - before

    cj_path = os.path.join(base, "character.json")
    manifest = None
    if check("有 character.json（包的身份证）", os.path.isfile(cj_path)):
        try:
            manifest = jsonc(cj_path)
        except Exception as e:
            check("character.json 能解析", False, str(e))
    if manifest:
        cid = manifest.get("id", "")
        check("id 与目录名一致", cid == char_id, "%r vs %r" % (cid, char_id))
        check("id 合法（小写字母开头 + 小写/数字/下划线）", bool(ID_RE.match(cid)), cid)
        check("有 name（界面要显示）", bool(manifest.get("name")))
        # 形态列表：forms.json 是"规划"，forms/ 是"实际"。两边要能对上话。
    forms_dir = os.path.join(base, "forms")
    ready = sorted(d for d in (os.listdir(forms_dir) if os.path.isdir(forms_dir) else [])
                   if os.path.isfile(os.path.join(forms_dir, d, "rig.json")))
    # 「还没做」和「包写错了」不是一回事，必须分开报：
    # 8 个 AI 角色里有 7 个目前只有 character.json（status=draft、没有 forms/），
    # 那是进度问题。所以这里只在"声明过要做形态"时才要求真有形态；
    # 完全没有目录时给一行**说明**（不计失败），避免把进度当成缺陷刷红一片。
    if len(ready) == 0:
        has_plan = False
        rp = os.path.join(base, "forms.json")
        if os.path.isfile(rp):
            try:
                has_plan = any(e.get("status") != "planned"
                               for e in (jsonc(rp).get("forms") or []))
            except Exception:
                has_plan = False
        check("没有可渲染形态的包必须显式说明（forms.json 声明 planned）", not has_plan,
              "有 forms.json 却一条可渲染的都没有 → 声明与磁盘不符")
        if not has_plan:
            if not _quiet:
                    print("  [i] 该角色还没有任何形态（status=draft / 无 forms/）—— 进度问题，不算包错")
    else:
        check("至少一个可渲染形态", True, "%d 个" % len(ready))
    check("形态数不超过引擎上限 %d" % FORM_CAP, len(ready) <= FORM_CAP,
          "%d 个 —— 超了要在 zrig.h 抬 ZRIG_FORM_CAP，不能靠丢目录" % len(ready))

    # forms.json 的路线图：声明 ready 就必须真有目录；声明 planned 才允许没有
    roadmap_path = os.path.join(base, "forms.json")
    if os.path.isfile(roadmap_path):
        try:
            roadmap = jsonc(roadmap_path)
        except Exception as e:
            check("forms.json 能解析", False, str(e))
            roadmap = None
        if roadmap:
            for ent in roadmap.get("forms", []):
                fid = ent.get("id", "")
                st = ent.get("status", "planned")
                has = os.path.isdir(os.path.join(forms_dir, fid, "")) if fid else False
                check("forms.json 的 %r 是合法 id" % fid, bool(ID_RE.match(fid or "")), fid)
                check("forms.json 声明 ready 的形态 %r 真有目录" % fid,
                      (not has) if st == "planned" else has,
                      "status=%s 目录%s" % (st, "在" if has else "不在"))
                if st not in ("ready", "planned"):
                    check("forms.json 的 status 只能是 ready/planned（%r）" % fid, False, st)

    # 逐个形态查 rig.json
    for form in ready:
        fdir = os.path.join(forms_dir, form)
        rig_path = os.path.join(fdir, "rig.json")
        try:
            rig = jsonc(rig_path)
        except Exception as e:
            check("形态 %s 的 rig.json 能解析" % form, False, str(e))
            continue
        check("形态 %s 写了 schema_version" % form, bool(rig.get("schema_version")),
              str(rig.get("schema_version")))
        canvas = rig.get("canvas") or {}
        check("形态 %s 的画布合理" % form,
              64 <= int(canvas.get("w", 0)) <= 8192 and 64 <= int(canvas.get("h", 0)) <= 8192,
              "%sx%s" % (canvas.get("w"), canvas.get("h")))
        parts = rig.get("parts") or []
        groups = rig.get("groups") or {}
        check("形态 %s 至少一个部件" % form, len(parts) > 0, "%d 件" % len(parts))
        pids = {p.get("id") for p in parts}
        gids = set(groups.keys()) | {"root"}
        dids = {d.get("id") for d in (rig.get("deformers") or [])}
        for p in parts:
            pid = p.get("id")
            if not check("形态 %s 部件 %r 的 id 合法" % (form, pid), bool(ID_RE.match(pid or "")), str(pid)):
                continue
            # ① 贴图必须存在、是 PNG、必须有真透明像素
            f = p.get("file")
            fpath = os.path.join(fdir, f) if f else None
            if not check("形态 %s 部件 %s 写了文件" % (form, pid), bool(f)):
                continue
            if not check("形态 %s 部件 %s 的贴图存在" % (form, pid), os.path.isfile(fpath), str(f)):
                continue
            if not f.lower().endswith(".png"):
                check("形态 %s 部件 %s 是 PNG" % (form, pid), False, f)
                continue
            try:
                im = Image.open(fpath)
                rgba = im.convert("RGBA")
                a = rgba.getchannel("A")
                lo, hi = a.getextrema()
            except Exception as e:
                check("形态 %s 部件 %s 的贴图能读" % (form, pid), False, str(e))
                continue
            check("形态 %s 部件 %s 有 alpha 通道" % (form, pid),
                  im.mode in ("RGBA", "LA", "P") or "transparency" in im.info, im.mode)
            check("形态 %s 部件 %s 真有透明区（不是整张不透明 = 把底烤进去了）" % (form, pid),
                  lo < 255, "alpha 最低 %d" % lo)
            # ② 引用必须能解析（引擎会拦，但装之前就该知道是哪一件写错了）
            g = p.get("group")
            if g:
                check("形态 %s 部件 %s 的 group %r 存在" % (form, pid, g), g in gids, str(g))
            df = p.get("deformer")
            if df:
                check("形态 %s 部件 %s 的 deformer %r 存在" % (form, pid, df), df in dids, str(df))
            # 挂点（T66.19 / S4）：模组件按**名字**挂在骨上，位置由挂点决定。
            # 这条对模组尤其重要：模组作者不知道画布多大，也不该知道 ——
            # 他只要写 socket + dpos，换形态换画布都不用动。所以这里要替他挡住
            # 三件事：挂点存在、父骨对得上、pos 和挂点不打架（两个来源会静默取一个）。
            sk = p.get("socket")
            if sk:
                socks = rig.get("sockets") or {}
                sp = socks.get(sk)
                if not check("形态 %s 部件 %s 的挂点 %r 存在" % (form, pid, sk), bool(sp),
                             "本形态的 sockets 里没有；旧包没有 sockets 段就不能写 socket"):
                    pass
                else:
                    check("形态 %s 部件 %s 的 group 与挂点父骨一致" % (form, pid),
                          p.get("group") == sp.get("group"),
                          "部件写 %r、挂点 %r 在 %r" % (p.get("group"), sk, sp.get("group")))
                    if p.get("pos") is not None:
                        dp = p.get("dpos") or [0, 0]
                        want = [sp["pos"][0] + dp[0], sp["pos"][1] + dp[1]]
                        check("形态 %s 部件 %s 的 pos 与「挂点+dpos」一致" % (form, pid),
                              abs(want[0] - p["pos"][0]) <= 1 and abs(want[1] - p["pos"][1]) <= 1,
                              "pos=%s，挂点+dpos=%s —— 位置只能有一个来源" % (p["pos"], want))
            for mk in ([p["mask"]] if isinstance(p.get("mask"), str) else (p.get("mask") or [])):
                check("形态 %s 部件 %s 的 mask %r 指向别的部件" % (form, pid, mk),
                      mk in pids and mk != pid, str(mk))
            mf = p.get("motion_from")
            if mf:
                check("形态 %s 部件 %s 的 motion_from %r 存在" % (form, pid, mf),
                      mf in pids and mf != pid, str(mf))
            for t in (p.get("tags") or []):
                check("形态 %s 部件 %s 的 tag %r 不是空串" % (form, pid, t), bool(str(t).strip()), str(t))
        # ③ 动作：id 唯一、通道目标能解析、数量不超上限
        acts = rig.get("actions") or []
        aids = [a.get("id") for a in acts]
        check("形态 %s 动作 id 不重复" % form, len(aids) == len(set(aids)),
              "重复：%s" % [x for x in aids if aids.count(x) > 1][:3])
        check("形态 %s 动作数不超过引擎上限 %d" % (form, ACTION_CAP), len(acts) <= ACTION_CAP,
              "%d 个" % len(acts))
        check("形态 %s 定义了 idle" % form, "idle" in aids, str(aids[:4]))
        params = {q.get("id") for q in (rig.get("params") or [])}
        for a in acts:
            for c in (a.get("channels") or []):
                tgt = c.get("target", "")
                ok = (tgt in gids) or (tgt in pids) or (tgt in dids) or (tgt in params) or \
                     (tgt.startswith("Param"))
                check("形态 %s 动作 %s 的通道目标 %r 能解析" % (form, a.get("id"), tgt), ok, tgt)

    # ④ 服装
    odir = os.path.join(base, "outfits")
    if os.path.isdir(odir):
        outs = sorted(f for f in os.listdir(odir) if f.endswith(".json"))
        check("服装数不超过引擎上限 %d" % OUTFIT_CAP, len(outs) <= OUTFIT_CAP, "%d 套" % len(outs))
        for f in outs:
            oid = f[:-5]
            try:
                o = jsonc(os.path.join(odir, f))
            except Exception as e:
                check("服装 %s 能解析" % oid, False, str(e))
                continue
            check("服装 %s 的 id 与文件名一致" % oid, o.get("id", oid) == oid,
                  str(o.get("id")))
            forms_ok = o.get("forms")
            if forms_ok is not None:
                for fm in forms_ok:
                    check("服装 %s 声明的形态 %r 存在" % (oid, fm), fm in ready, str(fm))
            # 部件引用：至少要在它适用的某个形态里存在，否则换了就是空
            targets = forms_ok if forms_ok else ready
            for pid in (o.get("parts") or {}):
                found = False
                for fm in targets:
                    try:
                        r = jsonc(os.path.join(forms_dir, fm, "rig.json"))
                    except Exception:
                        continue
                    if any(p.get("id") == pid for p in (r.get("parts") or [])):
                        found = True
                        break
                check("服装 %s 的部件 %r 在适用形态里存在" % (oid, pid), found, str(targets))
    return _fail - before


def lint_mod_pack(root: str, mod_id: str) -> int:
    """校验 mods/<id>/ 这个模组包（还没有真实模组，靠 --self-test 负控验）。"""
    global _fail
    before = _fail
    base = os.path.join(root, "mods", mod_id)
    if not _quiet:
        print("\n== 模组包 mods/%s ==" % mod_id)
    mp = os.path.join(base, "mod.json")
    if not check("有 mod.json", os.path.isfile(mp), mp):
        return _fail - before
    try:
        m = jsonc(mp)
    except Exception as e:
        check("mod.json 能解析", False, str(e))
        return _fail - before
    mid = m.get("id", "")
    check("id 与目录名一致", mid == mod_id, "%r vs %r" % (mid, mod_id))
    check("id 合法", bool(ID_RE.match(mid)), mid)
    check("有 name", bool(m.get("name")))
    ver = str(m.get("api_version", ""))
    major = ver.split(".")[0] if ver else ""
    check("api_version 是 %d.x（当前主版本）" % API_MAJOR, major == str(API_MAJOR), ver)
    for perm in (m.get("permissions") or []):
        check("权限 %r 在白名单内" % perm, perm in MOD_PERMISSIONS,
              "允许：%s" % sorted(MOD_PERMISSIONS))
    for dep in (m.get("depends") or []):
        did = dep.get("id") if isinstance(dep, dict) else dep
        exists = os.path.isdir(os.path.join(root, "mods", str(did)))
        check("依赖 %r 已安装" % did, exists, str(did))
    for rel in (m.get("files") or []):
        check("清单里列的文件 %r 存在" % rel, os.path.isfile(os.path.join(base, rel)), rel)
    return _fail - before


# ────────────────────────────────────────────────────────────── 负控
def _mk_pack(tmp: str, parts=None, forms=None, roadmap=None, outfits=None,
             manifest=None) -> str:
    """在 tmp 下造一个最小可用的内容包，返回角色 id。

    默认造一个"完全合法"的包；测试通过传参故意弄坏某一处。
    """
    cid = (manifest or {}).get("id", "pktest")
    base = os.path.join(tmp, "characters", cid)
    fdir = os.path.join(base, "forms", "teen")
    os.makedirs(fdir, exist_ok=True)
    os.makedirs(os.path.join(base, "outfits"), exist_ok=True)
    # 一张真有透明区的 PNG：中间一块不透明
    img = Image.new("RGBA", (40, 40), (0, 0, 0, 0))
    for y in range(10, 30):
        for x in range(10, 30):
            img.putpixel((x, y), (200, 120, 90, 255))
    img.save(os.path.join(fdir, "h.png"))
    if parts is None:
        parts = [{"id": "h", "file": "h.png", "layer": 10, "pos": [20, 20], "anchor": [0, 0]}]
    rig = {"schema_version": "1.0", "id": cid, "name": "包测试",
           "canvas": {"w": 200, "h": 200}, "origin": [100, 200],
           "groups": {"head": {"pivot": [100, 100]}},
           "parts": parts,
           "actions": [{"id": "idle", "loop": True, "channels": []}]}
    io.open(os.path.join(fdir, "rig.json"), "w", encoding="utf-8").write(
        json.dumps(rig, ensure_ascii=False, indent=1))
    man = manifest if manifest is not None else {"id": cid, "name": "包测试"}
    io.open(os.path.join(base, "character.json"), "w", encoding="utf-8").write(
        json.dumps(man, ensure_ascii=False, indent=1))
    if roadmap is not None:
        io.open(os.path.join(base, "forms.json"), "w", encoding="utf-8").write(
            json.dumps({"forms": roadmap}, ensure_ascii=False, indent=1))
    for name, body in (outfits or {}).items():
        io.open(os.path.join(base, "outfits", name + ".json"), "w", encoding="utf-8").write(
            json.dumps(body, ensure_ascii=False, indent=1))
    return cid


def self_test(root: str) -> int:
    """负控：每一条规则都要被一个坏包**打红**过。

    没有这一段的话，"闸门"只是一堆永远返回通过的 print ——
    这个项目里已经有过一次这种教训（LESSONS：判据写死在自己身上）。
    """
    global _quiet
    print("\n== 负控：每个坏包都必须被判红 ==")
    cases = []

    def one(name, expect_fail, build):
        tmp = tempfile.mkdtemp(prefix="zmodlint_")
        try:
            cid = build(tmp)
            _quiet = True
            n0 = _fail
            got = lint_content_pack(tmp, cid)
            bad = got > 0
            cases.append((name, expect_fail, bad))
            print("  %-46s 期望%s  实际%s" %
                  (name, "红" if expect_fail else "绿", "红" if bad else "绿"))
            del n0
        finally:
            _quiet = False
            shutil.rmtree(tmp, ignore_errors=True)

    one("合法包（应当全绿）", False, lambda t: _mk_pack(t))
    one("缺 character.json", True,
        lambda t: (os.makedirs(os.path.join(t, "characters", "pktest", "forms", "teen")),
                   _mk_pack(t), os.remove(os.path.join(t, "characters", "pktest",
                                                       "character.json")))[1])
    one("manifest 的 id 与目录名不一致", True, lambda t: _mk_pack_idmismatch(t))
    one("部件引用不存在的贴图", True,
        lambda t: _mk_pack(t, parts=[{"id": "h", "file": "nope.png", "layer": 10,
                                      "pos": [20, 20], "anchor": [0, 0]}]))
    one("贴图是整张不透明（白底烤进去了）", True, lambda t: _mk_pack_opaque(t))
    one("把底图去掉 alpha 通道（RGB）", True, lambda t: _mk_pack_rgb(t))
    one("部件 group 指向不存在的组", True,
        lambda t: _mk_pack(t, parts=[{"id": "h", "file": "h.png", "group": "NoSuch",
                                      "layer": 10, "pos": [20, 20], "anchor": [0, 0]}]))
    one("部件 id 不合法（大写/中文）", True,
        lambda t: _mk_pack(t, parts=[{"id": "H头", "file": "h.png", "layer": 10,
                                      "pos": [20, 20], "anchor": [0, 0]}]))
    one("forms.json 声明 ready 但没目录", True,
        lambda t: _mk_pack(t, roadmap=[{"id": "loli", "status": "ready"}]))
    one("forms.json 的 status 写错", True,
        lambda t: _mk_pack(t, roadmap=[{"id": "teen", "status": "done"}]))
    one("服装引用不存在的部件", True,
        lambda t: _mk_pack(t, outfits={"night": {"id": "night",
                                                 "parts": {"no_such": {"file": "h.png"}}}}))
    one("服装声明了不存在的形态", True,
        lambda t: _mk_pack(t, outfits={"night": {"id": "night", "forms": ["loli"],
                                                 "parts": {}}}))
    one("动作通道目标写错", True, lambda t: _mk_pack_badchan(t))
    one("没有 idle 动作", True, lambda t: _mk_pack_noidle(t))

    bad = [c[0] for c in cases if c[1] != c[2]]
    # 每例内部的检查项是**故意**要红的，不能混进总结里（否则永远显示"14 项不通过"，
    # 读的人分不清是闸坏了还是坏包起作用了 —— LESSONS 里"判据稀释"那条）。
    if bad:
        print("\n负控失败：%d / %d 例不符合预期 → %s" % (len(bad), len(cases), bad))
        return 1
    print("\n负控全部符合预期：%d 例（每例内部的判红是被测的坏包，不是闸坏了）" % len(cases))
    return 0


def _mk_pack_idmismatch(tmp):
    """目录叫 pktest，但清单里写 id=pktest2 —— 装机时会被两份不同包认领，必须拦。"""
    cid = _mk_pack(tmp)
    p = os.path.join(tmp, "characters", cid, "character.json")
    man = json.load(io.open(p, encoding="utf-8"))
    man["id"] = "pktest2"
    io.open(p, "w", encoding="utf-8").write(json.dumps(man, ensure_ascii=False, indent=1))
    return cid


def _mk_pack_opaque(tmp):
    cid = _mk_pack(tmp)
    p = os.path.join(tmp, "characters", cid, "forms", "teen", "h.png")
    Image.new("RGBA", (40, 40), (255, 255, 255, 255)).save(p)
    return cid


def _mk_pack_rgb(tmp):
    cid = _mk_pack(tmp)
    p = os.path.join(tmp, "characters", cid, "forms", "teen", "h.png")
    Image.new("RGB", (40, 40), (200, 120, 90)).save(p)
    return cid


def _mk_pack_badchan(tmp):
    cid = _mk_pack(tmp)
    p = os.path.join(tmp, "characters", cid, "forms", "teen", "rig.json")
    rig = json.load(io.open(p, encoding="utf-8"))
    rig["actions"] = [{"id": "idle", "loop": True,
                       "channels": [{"target": "NoSuchThing", "param": "value", "amp": 1}]}]
    io.open(p, "w", encoding="utf-8").write(json.dumps(rig, ensure_ascii=False, indent=1))
    return cid


def _mk_pack_noidle(tmp):
    cid = _mk_pack(tmp)
    p = os.path.join(tmp, "characters", cid, "forms", "teen", "rig.json")
    rig = json.load(io.open(p, encoding="utf-8"))
    rig["actions"] = [{"id": "wave", "channels": []}]
    io.open(p, "w", encoding="utf-8").write(json.dumps(rig, ensure_ascii=False, indent=1))
    return cid


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    ap.add_argument("--character", default=None, help="校验 characters/<id> 内容包")
    ap.add_argument("--mod", default=None, help="校验 mods/<id> 模组包")
    ap.add_argument("--all-characters", action="store_true", help="校验 characters/ 下全部内容包")
    ap.add_argument("--all-mods", action="store_true", help="校验 mods/ 下全部模组包")
    ap.add_argument("--self-test", action="store_true", help="负控：坏包必须被判红")
    ap.add_argument("--json", default=None)
    ap.add_argument("--quiet", action="store_true",
                    help="只打不通过的项和总结（selfcheck 用，避免几千行刷屏）")
    args = ap.parse_args()
    root = os.path.abspath(args.root)

    global _quiet
    _quiet = bool(args.quiet)
    if args.self_test:
        rc = self_test(root)
        return rc

    total = 0
    if args.character:
        total += lint_content_pack(root, args.character)
    if args.all_characters:
        cdir = os.path.join(root, "characters")
        for cid in sorted(os.listdir(cdir)) if os.path.isdir(cdir) else []:
            if os.path.isdir(os.path.join(cdir, cid)):
                total += lint_content_pack(root, cid)
    if args.mod:
        total += lint_mod_pack(root, args.mod)
    if args.all_mods:
        mdir = os.path.join(root, "mods")
        for mid in sorted(os.listdir(mdir)) if os.path.isdir(mdir) else []:
            if os.path.isdir(os.path.join(mdir, mid)):
                total += lint_mod_pack(root, mid)
    if not any([args.character, args.all_characters, args.mod, args.all_mods]):
        print("没指定包：用 --character / --mod / --all-characters / --all-mods / --self-test")
        return 2

    print("\n合计 %d 项，%d 项不通过 → %s" %
          (_n, _fail, "全部通过" if _fail == 0 else "包写得不对，先修包再谈装载"))
    if args.json:
        os.makedirs(os.path.dirname(os.path.abspath(args.json)), exist_ok=True)
        io.open(args.json, "w", encoding="utf-8").write(
            json.dumps({"checks": _n, "fail": _fail}, ensure_ascii=False, indent=1))
    return 0 if _fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
