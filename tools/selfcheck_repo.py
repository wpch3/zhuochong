#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""selfcheck_repo.py - 仓库自检（不编译、不渲染，纯静态核对，1 秒内跑完）。

为什么要有这个：单测和冒烟只能证明"代码跑得动"，证明不了
**配置里写错名字、文档和代码对不上、素材漏提交、记忆区没更新**这类问题。
这些恰恰是过去真出过事的地方：

  · 删了 `*_lid` 部件却忘了改动作展开表 → 预览启动直接 exit 3
  · 前端 HTML 里两张卡片用了同一个 id → 后写的那个永远不显示
  · 证据数字只写在 json 里没人校 → 重建回归了也没人知道
  · 素材是生成物，忘了 git add → 换台机器全是空白

所以这里按"引用完整性 + 唯一性 + 一致性 + 卫生"四类做静态核对。
失败就 exit 1，CI 和 scripts/selfcheck_all.sh 都会拦住。

用法：python3 tools/selfcheck_repo.py [--root .] [--quiet]
"""
from __future__ import annotations
import argparse, datetime, glob, io, json, os, re, subprocess, sys

OK, BAD = "通过", "不通过"
_fail = 0
_n = 0
_quiet = False
_strict = False


def check(name, cond, detail=""):
    global _fail, _n
    _n += 1
    if not cond:
        _fail += 1
    if not cond or not _quiet:
        print(f"  {OK if cond else BAD}  {name:<28} {detail}")
    return bool(cond)


def section(title):
    if not _quiet:
        print(f"\n== {title} ==")


def read(path):
    """读源码文本；文件不在就返回空串（后面的 check 自然判红）。"""
    return io.open(path, encoding="utf-8").read() if os.path.exists(path) else ""


def jsonc(path):
    """读 JSONC（配置里允许 // 注释）。"""
    txt = open(path, encoding="utf-8").read()
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
        elif c == "/" and i + 1 < len(txt) and txt[i + 1] == "/":
            while i < len(txt) and txt[i] != "\n":
                i += 1
            continue
        elif c == "/" and i + 1 < len(txt) and txt[i + 1] == "*":
            j = txt.find("*/", i + 2)
            i = (j + 2) if j > 0 else len(txt)
            continue
        else:
            out.append(c)
        i += 1
    return json.loads("".join(out))


def git(root, *args):
    try:
        return subprocess.run(["git", "-C", root, *args], capture_output=True,
                              text=True, timeout=30).stdout
    except Exception:
        return ""


# ------------------------------------------------------------------ 1 记忆区
def check_memory(root):
    section("记忆区（七件套 + 编号唯一 + 有没有在更新）")
    mem = os.path.join(root, "docs", "memory")
    need = ["MEMORY.md", "TASKS.md", "GAPS.md", "REQUIREMENTS.md",
            "WORKFLOW.md", "JOURNAL.md", "LESSONS.md"]           # 记忆区七件套
    need += ["../PROJECT_SPEC.md", "../PRODUCT_PLAN.md"]          # 规格与路线图在 docs/
    for f in need:
        p = os.path.join(mem, f)
        check(os.path.basename(f), os.path.exists(p) and os.path.getsize(p) > 200,
              f"{os.path.getsize(p)} 字节" if os.path.exists(p) else "缺文件")

    jp = os.path.join(mem, "JOURNAL.md")
    if os.path.exists(jp):
        days = [datetime.date.fromisoformat(d) for d in
                re.findall(r"20\d\d-\d\d-\d\d", open(jp, encoding="utf-8").read())]
        last = max(days) if days else datetime.date(2000, 1, 1)
        gap = (datetime.date.today() - last).days
        check("JOURNAL 最近有更新", gap <= 14, f"最后一条 {last}（{gap} 天前）")

    gp = os.path.join(mem, "GAPS.md")
    if os.path.exists(gp):
        ids = re.findall(r"^\|\s*~*\s*([A-Z]\d+[a-z]?\d?)\s*~*\s*[（(|]",
                         open(gp, encoding="utf-8").read(), re.M)
        dup = sorted({i for i in ids if ids.count(i) > 1})
        check("GAPS 编号不重复", not dup, f"重复：{dup}" if dup else f"{len(ids)} 条")

    tp = os.path.join(mem, "TASKS.md")
    if os.path.exists(tp):
        txt = open(tp, encoding="utf-8").read()
        ids = re.findall(r"^\|\s*(T[\d.]+)\s*\|", txt, re.M)
        dup = sorted({i for i in ids if ids.count(i) > 1})
        check("TASKS 编号不重复", not dup, f"重复：{dup}" if dup else f"{len(ids)} 条")
        bad = re.findall(r"^\|\s*T[\d.]+\s*\|[^|]*\|\s*([^|]*?)\s*\|", txt, re.M)
        illegal = sorted({s for s in bad if s not in ("[ ]", "[~]", "[x]", "状态")})
        check("TASKS 状态只用 [ ]/[~]/[x]", not illegal, f"异常：{illegal[:4]}")


# ------------------------------------------------------------------ 2 JSON
def check_json(root):
    section("配置与角色包：JSON 全部能解析")
    pats = ["config/*.json", "schemas/*.json", "characters/*/*.json",
            "characters/*/forms/*/*.json", "characters/*/forms/*/sprites/*.json",
            "characters/*/outfits/*.json", "characters/*/voice/*.json"]
    bad = []
    n = 0
    for pat in pats:
        for f in glob.glob(os.path.join(root, pat)):
            n += 1
            try:
                jsonc(f)
            except Exception as e:                       # noqa: BLE001
                bad.append(f"{os.path.relpath(f, root)}: {e}")
    check("全部 JSON/JSONC 可解析", not bad, f"{n} 个文件" + ("；" + bad[0] if bad else ""))


# ------------------------------------------------------------------ 3 rig
def check_rig(root):
    section("rig.json：引用完整 + 唯一 + 动作通道的 target 都存在")
    for rp in glob.glob(os.path.join(root, "characters/*/forms/*/rig.json")):
        base = os.path.dirname(rp)
        tag = os.path.relpath(rp, root)
        r = jsonc(rp)
        parts = r.get("parts", [])
        pids = [p["id"] for p in parts]
        gids = list(r.get("groups", {}).keys())
        dup = sorted({i for i in pids if pids.count(i) > 1})
        check(f"部件 id 唯一", not dup, f"{tag}：{len(pids)} 件" + (f"，重复 {dup}" if dup else ""))

        layers = [p["layer"] for p in parts]
        dupl = sorted({l for l in layers if layers.count(l) > 1})
        check("层号不重复", not dupl, f"重复层 {dupl}" if dupl else f"{len(layers)} 层")

        miss = [p["file"] for p in parts if not os.path.exists(os.path.join(base, p["file"]))]
        check("部件贴图都在", not miss, f"缺：{miss[:3]}" if miss else f"{len(parts)} 张")

        # 遮罩可以写一个 id，也可以写数组（多个遮罩取并集，A9）
        def masklist(p):
            m = p.get("mask")
            if not m:
                return []
            return list(m) if isinstance(m, list) else [m]

        badmask = [f"{p['id']}→{q}" for p in parts for q in masklist(p)
                   if q not in pids or q == p["id"]]
        # 遮罩源自己不能再被裁（引擎不支持套娃，会直接加载失败）
        masksrc = {q for p in parts for q in masklist(p)}
        nested = [p["id"] for p in parts if p["id"] in masksrc and masklist(p)]
        over4 = [p["id"] for p in parts if len(masklist(p)) > 4]
        check("遮罩指向真部件", not badmask and not nested and not over4,
              f"坏遮罩 {badmask[:3]} 套娃 {nested} 超 4 个 {over4}"
              if (badmask or nested or over4)
              else f"{sum(1 for p in parts if masklist(p))} 件被裁")

        badmf = [p["id"] for p in parts
                 if p.get("motion_from") and (p["motion_from"] not in pids or
                                              p["motion_from"] == p["id"])]
        check("motion_from 不自指且存在", not badmf, f"坏引用：{badmf}" if badmf else "")

        badg = [p["id"] for p in parts if p.get("group") and p["group"] not in gids]
        check("部件的组都存在", not badg, f"坏组：{badg}" if badg else f"{len(gids)} 组")

        # ★ 这条就是上次预览 exit 3 的那个坑：删了部件却忘改动作展开表
        # 动作通道现在打在参数上（≈ .motion3 的 Parameter 曲线），
        # 参数名的正确性由下面 check_live2d 的 ⑬ 组单独核；这里只拦
        # "指向一个不存在的部件/组/形变器" 这种删件漏改。
        ghosts = []
        dfids = {q.get("id") for q in r.get("deformers", [])}
        for a in r.get("actions", []):
            for c in a.get("channels", []):
                t = c.get("target", "")
                if t.startswith("Param"):
                    continue
                if t and t not in pids and t not in gids and t not in dfids:
                    ghosts.append(f"{a['id']}→{t}")
        check("动作通道没有幽灵 target", not ghosts, f"坏通道：{ghosts[:4]}" if ghosts else
              f"{sum(len(a.get('channels', [])) for a in r.get('actions', []))} 条通道")

        badbind = []
        for q in r.get("params", []):
            for b in q.get("binds", []):
                t = b.get("part") or b.get("group")
                if t and t not in pids and t not in gids:
                    badbind.append(f"{q['id']}→{t}")
        check("参数绑定的目标都存在", not badbind, f"坏绑定：{badbind[:4]}" if badbind else
              f"{len(r.get('params', []))} 个参数")

        badexp = [f"{e['id']}→{q['id']}" for e in r.get("expressions", [])
                  for q in e.get("params", [])
                  if q["id"] not in [x["id"] for x in r.get("params", [])]
                  and not q["id"].startswith("Param")]
        check("表情引用的参数都存在", not badexp, f"坏表情：{badexp[:4]}" if badexp else
              f"{len(r.get('expressions', []))} 个表情")

        dfs = r.get("deformers", [])
        dids = [f["id"] for f in dfs]
        badd = [f["id"] for f in dfs if f.get("part") not in pids]
        badd += [i for i in dids if dids.count(i) > 1 or i in pids or i in gids]
        badpt = [f"{f['id']}({q['c']},{q['r']})" for f in dfs for q in f.get("points", [])
                 if not (0 <= q["c"] <= f.get("cols", 2) and 0 <= q["r"] <= f.get("rows", 2))]
        check("网格形变器引用正确", not badd and not badpt,
              f"坏形变器 {badd} 坏控制点 {badpt}" if (badd or badpt) else f"{len(dfs)} 个")

        badphy = [f["id"] for f in r.get("physics", []) if f.get("part") not in pids]
        check("物理绑定的部件都存在", not badphy, f"坏物理：{badphy}" if badphy else
              f"{len(r.get('physics', []))} 条")

        # 多段摆链（G16）：driver 要么是组，要么是**写在自己前面**的另一条 physics；
        # 写在后面 = 这一帧拿到的是上一帧的旧值，引擎直接拒绝加载，所以这里先拦下来。
        phys = r.get("physics", [])
        seen, badchain, baddfm = [], [], []
        for f in phys:
            drv = f.get("driver")
            if drv not in gids and drv not in seen:
                badchain.append(f"{f['id']}→{drv}")
            if f.get("deformer") and f["deformer"] not in dids:
                baddfm.append(f"{f['id']}→{f['deformer']}")
            seen.append(f.get("id"))
        nchain = sum(1 for f in phys if f.get("driver") not in gids)
        check("多段摆链的 driver 按根→梢顺序声明", not badchain and not baddfm,
              f"坏链 {badchain} 坏形变器 {baddfm}" if (badchain or baddfm)
              else f"{nchain} 条串在别的摆后面")

        # 混合模式（A7）：只认 normal/add/multiply；加算·乘算的零件必须有东西垫在底下
        # （它们不改目标 alpha，画在空白处等于白画），所以层号不能是最底层。
        badblend = [f"{p['id']}={p['blend']}" for p in r["parts"]
                    if p.get("blend") not in (None, "normal", "add", "multiply")]
        nb = [p for p in r["parts"] if p.get("blend") in ("add", "multiply")]
        minlayer = min([p.get("layer", 0) for p in r["parts"]], default=0)
        lowblend = [p["id"] for p in nb if p.get("layer", 0) <= minlayer]
        check("混合模式零件写法合法", not badblend and not lowblend,
              f"坏取值 {badblend} 压在最底层 {lowblend}" if (badblend or lowblend)
              else f"{len(nb)} 件（加算/乘算）")

        # Pose 互斥组（A8）：部件必须存在、一个部件只能归一个档位、default 要在档位里、
        # 至少两个档位（只有一个就不叫互斥）。
        badpose, seenmem = [], {}
        for g in r.get("poses", []):
            ents = g.get("entries", [])
            if len(ents) < 2:
                badpose.append(f"{g.get('id')}:档位不足 2 个")
            eids = [e.get("id") for e in ents]
            if g.get("default") and g["default"] not in eids:
                badpose.append(f"{g['id']}:default={g['default']} 不在档位里")
            for e in ents:
                for q in e.get("parts", []):
                    if q not in pids:
                        badpose.append(f"{g['id']}/{e.get('id')}:没有部件 {q}")
                    elif q in seenmem:
                        badpose.append(f"{q} 同时属于 {seenmem[q]} 和 {g['id']}/{e.get('id')}")
                    else:
                        seenmem[q] = f"{g['id']}/{e.get('id')}"
        check("Pose 互斥组写法合法", not badpose,
              f"坏组 {badpose[:3]}" if badpose else f"{len(r.get('poses', []))} 组")

        # 关键帧曲线（≈ .motion3）：时间必须递增、每帧两个数、不能越过动作时长太多
        badkeys = []
        for a in r.get("actions", []):
            for ci, c in enumerate(a.get("channels", [])):
                ks = c.get("keys")
                if not ks:
                    continue
                if any(len(k) < 2 for k in ks):
                    badkeys.append(f"{a['id']}#{ci}:帧要写成[时间,值]")
                elif any(ks[i][0] > ks[i + 1][0] for i in range(len(ks) - 1)):
                    badkeys.append(f"{a['id']}#{ci}:时间倒退")
                elif c.get("interp") not in (None, "linear", "smooth", "step"):
                    badkeys.append(f"{a['id']}#{ci}:interp={c['interp']}")
        nkey = sum(1 for a in r.get("actions", []) for c in a.get("channels", []) if c.get("keys"))
        check("关键帧曲线写法合法", not badkeys,
              f"坏关键帧 {badkeys[:3]}" if badkeys else f"{nkey} 条关键帧通道")



# ------------------------------------------------- 3.5 Live2D 标准合规（静态）
# 口径来自官方 CubismWebFramework/src/cubismdefaultparameterid.ts（41 个标准参数 ID）
# 与样本 model3.json 的 Groups（EyeBlink / LipSync）。
L2D_STANDARD = {
    "ParamAngleX", "ParamAngleY", "ParamAngleZ",
    "ParamEyeLOpen", "ParamEyeLSmile", "ParamEyeROpen", "ParamEyeRSmile",
    "ParamEyeBallX", "ParamEyeBallY", "ParamEyeBallForm",
    "ParamBrowLY", "ParamBrowRY", "ParamBrowLX", "ParamBrowRX",
    "ParamBrowLAngle", "ParamBrowRAngle", "ParamBrowLForm", "ParamBrowRForm",
    "ParamMouthForm", "ParamMouthOpenY", "ParamCheek",
    "ParamBodyAngleX", "ParamBodyAngleY", "ParamBodyAngleZ", "ParamBreath",
    "ParamArmLA", "ParamArmRA", "ParamArmLB", "ParamArmRB",
    "ParamHandL", "ParamHandR",
    "ParamHairFront", "ParamHairSide", "ParamHairBack", "ParamHairFluffy",
    "ParamShoulderY", "ParamBustX", "ParamBustY", "ParamBaseX", "ParamBaseY",
    "ParamNONE",
}
# 标准表里没有、但我们确实需要的扩展。每加一个都必须在这里登记 + 写进
# docs/LIVE2D_CONFORMANCE.md，否则参数命名会慢慢跑偏，以后接任何现成工具都对不上。
L2D_EXTENSIONS = {
    "ParamLegL": "裙下大腿 bend（标准表没有腿参数）",
    "ParamLegR": "同上",
    "ParamHairAhoge": "呆毛整体摆（标准表只有 Front/Side/Back/Fluffy）",
    "ParamHairAhogeS": "呆毛 S 形（网格形变器）",
    "ParamHairSideS": "侧发 S 形（网格形变器）",
    "ParamEyeSparkle": "眼高光强弱（加算图层）",
    "ParamEyeOpen": "两眼一起开合的便捷参数（引擎内建，L/R 之外的额外入口）",
    "ParamBaseRot": "全身倾斜（标准表只有 ParamBodyAngleZ=上身；被摸头/被拖拽要整个人晃）",
}
# 官方惯例的取值范围（Cubism 标准模板）
L2D_RANGE = {
    "ParamAngleX": (-30, 30), "ParamAngleY": (-30, 30), "ParamAngleZ": (-30, 30),
    "ParamEyeLOpen": (0, 1), "ParamEyeROpen": (0, 1),
    "ParamEyeBallX": (-1, 1), "ParamEyeBallY": (-1, 1),
    "ParamBrowLY": (-1, 1), "ParamBrowRY": (-1, 1),
    "ParamBrowLX": (-1, 1), "ParamBrowRX": (-1, 1),
    "ParamMouthForm": (-1, 1), "ParamMouthOpenY": (0, 1), "ParamCheek": (0, 1),
    "ParamBodyAngleX": (-10, 10), "ParamBodyAngleY": (-10, 10),
    "ParamBodyAngleZ": (-10, 10), "ParamBreath": (0, 1),
    "ParamArmLA": (-10, 10), "ParamArmRA": (-10, 10),
    "ParamArmLB": (-10, 10), "ParamArmRB": (-10, 10),
    "ParamShoulderY": (-10, 10), "ParamBaseX": (-10, 10), "ParamBaseY": (-10, 10),
}


def check_live2d(root):
    section("Live2D 标准合规：参数命名 / 取值范围 / model3 分组（静态）")
    doc = os.path.join(root, "docs/LIVE2D_CONFORMANCE.md")
    doc_txt = io.open(doc, encoding="utf-8").read() if os.path.exists(doc) else ""
    check("有合规对照表文档", bool(doc_txt), "docs/LIVE2D_CONFORMANCE.md")
    for rp in sorted(glob.glob(os.path.join(root, "characters/*/forms/*/rig.json"))):
        tag = os.path.relpath(rp, root)
        r = jsonc(rp)
        params = r.get("params", [])
        ids = [q["id"] for q in params]

        # ① 不许出现"标准表里有、我们却另起炉灶"的名字
        renamed = [i for i in ids if i in ("ParamBlush", "ParamEyeL", "ParamEyeR")]
        check("没有被标准名取代的旧参数名", not renamed,
              f"{tag}：{renamed}（ParamBlush 的标准名是 ParamCheek）" if renamed else "（已对齐）")

        # ② 非标准名必须登记成扩展
        unknown = [i for i in ids if i not in L2D_STANDARD and i not in L2D_EXTENSIONS]
        check("自定义参数都已登记", not unknown,
              f"{tag}：{unknown} 不在标准表也不在扩展表" if unknown else
              f"扩展 {len([i for i in ids if i in L2D_EXTENSIONS])} 个，其余全是标准名")

        # ③ 取值范围跟官方惯例一致（范围错了，外部的 motion / 表情文件推进来幅度就不对）
        bad = []
        for q in params:
            want = L2D_RANGE.get(q["id"])
            if want and (abs(q.get("min", 0) - want[0]) > 1e-6 or abs(q.get("max", 0) - want[1]) > 1e-6):
                bad.append(f"{q['id']} {q.get('min')}..{q.get('max')}≠{want[0]}..{want[1]}")
        check("标准参数取值范围符合官方惯例", not bad, f"{bad[:3]}" if bad else "（逐条核对过）")

        # ④ model3.json 的 Groups：EyeBlink / LipSync
        groups = {g.get("name"): g.get("ids", []) for g in r.get("param_groups", [])}
        check("声明了 EyeBlink 分组",
              set(groups.get("EyeBlink", [])) == {"ParamEyeLOpen", "ParamEyeROpen"},
              f"{tag}：EyeBlink={groups.get('EyeBlink')}")
        check("声明了 LipSync 分组", groups.get("LipSync") == ["ParamMouthOpenY"],
              f"{tag}：LipSync={groups.get('LipSync')}")

        # ⑤ 眼部件必须标明左右，否则左右眼参数驱动不了
        eye = [p for p in r.get("parts", []) if p["id"].split("_")[0] == "eye"]
        noside = [p["id"] for p in eye if p.get("eye_side") not in ("l", "r")]
        check("眼部件都标了 eye_side", not noside,
              f"{tag}：{noside[:4]} 没标左右" if noside else f"{len(eye)} 件都标了")

        # ⑥ 口型音素表（母音識別）：必须齐、必须只写标准嘴参数、五个母音不许重样
        vis = r.get("visemes", [])
        vids = [v.get("id") for v in vis]
        if "ParamMouthOpenY" in ids:
            check("有口型音素表且五个母音齐全",
                  set(["SIL", "A", "I", "U", "E", "O"]).issubset(set(vids)),
                  f"{tag}：visemes={vids}")
            offenders, outrange, rows = [], [], {}
            prange = {q["id"]: (q.get("min", 0.0), q.get("max", 1.0)) for q in params}
            for v in vis:
                ps = v.get("params", {})
                for pid, pv in ps.items():
                    # 音素只能写模型声明过的标准嘴参数 —— 不许偷偷自造 ParamMouthA 这类
                    if pid not in ids or pid not in ("ParamMouthOpenY", "ParamMouthForm"):
                        offenders.append(f"{v.get('id')}:{pid}")
                    lo, hi = prange.get(pid, (0.0, 1.0))
                    if not (lo - 1e-9 <= pv <= hi + 1e-9):
                        outrange.append(f"{v.get('id')}:{pid}={pv}∉[{lo},{hi}]")
                rows[v.get("id")] = tuple(sorted(ps.items()))
            check("音素只写标准嘴参数（OpenY / Form）", not offenders,
                  f"{tag}：{offenders[:4]}" if offenders else "（没有自造音素参数）")
            check("音素取值都在参数区间内", not outrange, f"{outrange[:3]}" if outrange else "（逐条核对过）")
            dup = [f"{a_}={b_}" for i, a_ in enumerate(vids) for b_ in vids[i + 1:]
                   if a_ in rows and b_ in rows and rows[a_] == rows[b_]]
            check("五个母音互不重样（重样=少一张嘴）", not dup, f"{dup[:3]}" if dup else "（两两都不同）")
            # 嘴形参数必须真的接到素材上，否则 い/う 只剩开合大小的区别
            mf = [q for q in params if q["id"] == "ParamMouthForm"]
            check("ParamMouthForm 真接了素材（≥2 条 bind）",
                  bool(mf) and len(mf[0].get("binds", [])) >= 2,
                  f"{tag}：binds={len(mf[0].get('binds', [])) if mf else 0}")
            if doc_txt:
                nodoc = [v for v in vids if f"| {v} " not in doc_txt and f"`{v}`" not in doc_txt]
                check("对照表记载了音素表", not nodoc,
                      f"文档里查不到音素 {nodoc[:4]}" if nodoc else f"{len(vids)} 个音素都有记载")

        # ⑦ 文档与 rig 对得上：每个参数都要在对照表里出现
        if doc_txt:
            missing = [i for i in ids if i not in doc_txt]
            check("对照表覆盖所有参数", not missing,
                  f"文档里查不到 {missing[:4]}" if missing else f"{len(ids)} 个参数都有记载")

        # ⑧ 表情 × 口型的叠加口径：权重要在 0~1，而且必须在对照表里登记成偏差
        vw = r.get("viseme_weight", 0.8)
        check("口型权重 viseme_weight 在 0~1", isinstance(vw, (int, float)) and 0.0 <= vw <= 1.0,
              f"{tag}：viseme_weight={vw}")
        if doc_txt:
            check("对照表登记了口型压过表情的口径", "viseme_weight" in doc_txt,
                  "docs/LIVE2D_CONFORMANCE.md 里要写明 LipSync 为什么不是纯加算")

    # ⑨ 引擎这边：三种 Blend 都在、执行序是「表情 → 口型」、API 把分层值报出来
    rig_c = read(os.path.join(root, "src/core/zrig.c"))
    head_c = read(os.path.join(root, "src/headless/main_headless.c"))
    test_c = read(os.path.join(root, "tests/test_core.c"))
    page = read(os.path.join(root, "web/test.html"))
    check("表情支持 Cubism 的三种 Blend（add / multiply / overwrite）",
          all(k in rig_c for k in ("EXPR_MUL", '"multiply"', '"overwrite"')),
          "src/core/zrig.c")
    check("表情按三累加器求值（overwrite + additive）× multiply",
          "expr_apply" in rig_c and "(base + ov + add) * mul" in rig_c.replace("  ", " "),
          "照 CubismExpressionMotion 的 calculateExpressionParameters")
    check("口型层排在表情之后（param_effective 里先表情后音素）",
          "param_effective" in rig_c
          and rig_c.index("expr_apply(r, pi") < rig_c.index("viseme_slot(r, pi)"),
          "官方执行序 Expression 300 < LipSync 700")
    check("音素层不回写基础参数值（分层，不是改滑条）",
          "viseme_write" not in rig_c, "viseme_write() 已删除")
    check("/api/params.json 报出分层值（value / expr / effective）",
          all(k in head_c for k in ('\\"expr\\":', '\\"effective\\":')), "src/headless/main_headless.c")
    check("有「表情 × 口型」的单测和负控判据",
          "test_expr_viseme_order" in test_c and "test_expression_blend" in test_c,
          "tests/test_core.c")
    check("测试台有分层看板", "mx-table" in page, "web/test.html")

    # ⑩ 睡醒要成套：唤醒只能走 pet_wake()，强制闭眼不是 bool（2026-10-13 事故）
    pet_c = read(os.path.join(root, "src/core/zpet.c"))
    wake_sites = [ln.strip() for ln in pet_c.splitlines() if re.search(r"\bsleeping\s*=\s*0\b", ln)]
    check("唤醒只有一处（统一走 pet_wake，少一步就是醒着也闭眼）",
          len(wake_sites) == 1, "src/core/zpet.c 里 %d 处 sleeping=0：%s" % (len(wake_sites), wake_sites))
    check("pet_wake 会解除强制闭眼",
          "static void pet_wake" in pet_c
          and "zrig_blink_force" in pet_c.split("static void pet_wake")[1][:400],
          "src/core/zpet.c")
    check("zrig_blink_force 是三态（>0 闭眼，<=0 取消），不是 bool",
          "(mode > 0) ? 1 : -1" in rig_c,
          "传 -1 想表达\"取消\"却被当成真 → 醒着也永远闭眼")
    check("/api/blink 认 on= 且参数缺失会报错",
          'qstr(r, "on"' in head_c and "要给 v=0..1|auto 或 on=0|1" in head_c,
          "src/headless/main_headless.c")

    # ⑪ 口型接管与松口（2026-10-13「张嘴了微笑还在 / 收尾抽一下」两个事故的闸）
    check("口型接管力度随本帧口型用力程度缩放（不是恒定权重）",
          "viseme_activity" in rig_c
          and "vis_mix * viseme_activity" in rig_c.replace("  ", " "),
          "小声说话要漏出表情，满力说话由口型独占")
    clear_body = rig_c.split("void zrig_viseme_clear")[1].split("\n}")[0] if "void zrig_viseme_clear" in rig_c else ""
    # 没在说话时直接清是允许的（本来就没有可见跳变）；在说话时必须走 vis_weight→0 的平滑收口
    hard = [ln for ln in clear_body.splitlines()
            if "viseme_release" in ln and "vis_active" not in ln]
    check("zrig_viseme_clear 是平滑松口（不许一帧切回表情）",
          bool(clear_body) and not hard and "vis_weight = 0" in clear_body,
          "硬切 = 说完话嘴角抽一下；要立刻清零请用 zrig_viseme_reset()")
    check("有 zrig_viseme_reset（换角色 / 测试基准用的立即清零）",
          "void zrig_viseme_reset" in rig_c, "src/core/zrig.c")
    mo = re.search(r"ZRIG_VIS_RELEASE_OFF\s+([0-9.]+)", rig_c)
    mr = re.search(r"ZRIG_VIS_RELEASE\s+([0-9.]+)", rig_c)
    check("整句松口比音素间回落更慢（两档 release）",
          bool(mo and mr) and float(mo.group(1)) < float(mr.group(1)),
          "RELEASE_OFF=%s / RELEASE=%s" % (mo.group(1) if mo else "?", mr.group(1) if mr else "?"))
    draw = rig_c.split("compute_draw_state")[-1] if "compute_draw_state" in rig_c else ""
    fade = draw.split("TAG_EYE_CLOSED")[0][-600:] if "TAG_EYE_CLOSED" in draw else ""
    check("眼件淡化只看闭合度，不看 blink_enabled",
          "blink_enabled" not in fade,
          "关掉自动眨眼后闭眼件会 100% 盖住睁眼件 = 一上表情就全闭眼")
    if doc_txt:
        check("对照表登记了口型接管与松口的偏差",
              "viseme_activity" in doc_txt and "RELEASE_OFF" in doc_txt,
              "docs/LIVE2D_CONFORMANCE.md 要写明权重调制与两档 release")

    # ⑫ 笑眼（Live2D 标准 6/7）：山型 ∩ 的闭眼，官方 Haru F05 的口径
    for rp in sorted(glob.glob(os.path.join(root, "characters/*/forms/*/rig.json"))):
        tag = os.path.relpath(rp, root)
        r = jsonc(rp)
        sm = [p for p in r.get("parts", []) if "eye_smile" in (p.get("tags") or [])]
        if not sm:
            continue
        check("笑眼件左右各一、都标了 eye_side",
              len(sm) == 2 and {p.get("eye_side") for p in sm} == {"l", "r"},
              f"{tag}：{[(p['id'], p.get('eye_side')) for p in sm]}")
        # 笑眼件必须压在同侧闭眼件之上，否则谷型线会盖住山型线
        closed = {p.get("eye_side"): p for p in r.get("parts", [])
                  if "eye_closed" in (p.get("tags") or [])}
        bad = [p["id"] for p in sm
               if closed.get(p.get("eye_side")) and p["layer"] <= closed[p["eye_side"]]["layer"]]
        check("笑眼件画在谷型闭眼件之上", not bad, f"{tag}：{bad}" if bad else "（层号已排好）")
        exprs = {e["id"]: e for e in r.get("expressions", [])}
        hp = exprs.get("happy", {})
        pids = {q.get("id"): q for q in hp.get("params", [])}
        check("有带笑眼的表情（happy）",
              "ParamEyeLSmile" in pids and "ParamEyeRSmile" in pids,
              f"{tag}：happy={list(pids)}")
    check("笑眼隐含闭眼（照 Haru F05：EyeOpen=0 + Smile=1）",
          "r->smile_l > r->blink_l" in rig_c and "r->smile_r > r->blink_r" in rig_c,
          "src/core/zrig.c：blink = max(blink, smile)")
    check("笑眼显形时谷型闭眼件要让位",
          "TAG_EYE_CLOSED) opacity *= 1.0 - smile" in rig_c,
          "两条睫毛线一起画会叠成一团黑")
    check("有笑眼的单测（含结构闸）",
          "test_eye_smile" in test_c and "frame_opaque_box" in test_c, "tests/test_core.c")
    if doc_txt:
        check("对照表把笑眼登记成已实现",
              "`ParamEyeLSmile` | 左眼 笑眼 | ✅" in doc_txt,
              "docs/LIVE2D_CONFORMANCE.md 第 6/7 行")

    # ⑬ 动作通道：官方 .motion3 的曲线目标只有 Parameter / PartOpacity / Model
    #    （CubismWebFramework cubismmotion.ts 的 TargetName* 三个常量）。
    #    直接写部件的位移/旋转/缩放不在其中 —— 这里把门守死。
    mk = io.open(os.path.join(root, "tools/make_rig.py"), encoding="utf-8").read()
    for rp in sorted(glob.glob(os.path.join(root, "characters/*/forms/*/rig.json"))):
        tag = os.path.relpath(rp, root)
        r = jsonc(rp)
        known = {q["id"] for q in r.get("params", [])} | {
            "ParamAngleX", "ParamAngleY", "ParamEyeOpen", "ParamEyeLOpen", "ParamEyeROpen",
            "ParamEyeLSmile", "ParamEyeRSmile", "ParamEyeBallX", "ParamEyeBallY"}
        geom, unknown = [], []
        nch = 0
        for a_ in r.get("actions", []):
            for c in a_.get("channels", []):
                nch += 1
                t = c.get("target", "")
                if not t.startswith("Param"):
                    geom.append(f'{a_["id"]}:{t}.{c.get("param")}')
                elif t not in known:
                    unknown.append(f'{a_["id"]}:{t}')
        check("动作通道只打在参数上（≈ .motion3 的 Parameter 曲线）",
              not geom, f"{tag}：{geom[:4]}" if geom else f"{tag}：{nch} 条全是参数通道")
        check("动作引用的参数都存在",
              not unknown, f"{tag}：{unknown[:4]}" if unknown else f"{tag}：{len(known)} 个参数可用")
    check("make_rig 有几何→参数的换算表，并对漏登记的目标报错",
          "GEO2PARAM" in mk and "没有对应的参数" in mk,
          "tools/make_rig.py：新动作直接写参数，换算表只是守门人")
    check("引擎会数出残留的几何通道",
          "legacy_geom_chans" in rig_c and "zrig_action_geom_channels" in rig_c,
          "src/core/zrig.c")
    check("几何通道计数对外可查",
          "zrig_action_geom_channels" in io.open(
              os.path.join(root, "src/core/zrig.h"), encoding="utf-8").read(),
          "src/core/zrig.h")
    check("有动作通道的单测（含反向验证计数器）",
          "test_action_param_channels" in test_c and "zc_geomchan_rig" in test_c,
          "tests/test_core.c")
    check("支持直流偏置 bias（官方 CubismBreath 的 offset）",
          "c->bias" in rig_c and '"bias"' in rig_c, "src/core/zrig.c：value = offset + peak*sin")

# ------------------------------------------------------------------ 4 角色包其它引用
def check_character(root):
    section("角色包其它引用：服装 / 互动 / 语音 / 口型包络")
    for od in glob.glob(os.path.join(root, "characters/*/outfits/*.json")):
        o = jsonc(od)
        cdir = os.path.dirname(os.path.dirname(od))
        miss = []
        for form in glob.glob(os.path.join(cdir, "forms/*")):
            for pid, v in (o.get("parts") or {}).items():
                f = v.get("file") if isinstance(v, dict) else v
                if f and not os.path.exists(os.path.join(form, f)):
                    miss.append(f"{os.path.basename(form)}:{f}")
        check(f"服装 {os.path.basename(od)} 贴图在", not miss, f"缺 {miss[:2]}" if miss else "")

    ip = os.path.join(root, "config", "interactions.json")
    if os.path.exists(ip):
        it = jsonc(ip)
        rules = it.get("rules", [])
        rids = [x.get("id") for x in rules if x.get("id")]
        dup = sorted({i for i in rids if rids.count(i) > 1})
        check("互动规则 id 不重复", not dup, f"重复 {dup}" if dup else f"{len(rules)} 条")

    for cat in glob.glob(os.path.join(root, "characters/*/voice/catalog.json")):
        c = jsonc(cat)
        lines = c.get("lines", [])
        miss = [l["file"] for l in lines if not os.path.exists(os.path.join(root, l["file"]))]
        check("语音文件都在", not miss, f"{len(lines)} 条" + (f"，缺 {len(miss)}" if miss else ""))
        idx = os.path.join(os.path.dirname(cat), "lipsync", "index.json")
        if os.path.exists(idx):
            items = json.load(open(idx, encoding="utf-8")).get("items", [])
            m2 = [i["id"] for i in items
                  if not os.path.exists(os.path.join(os.path.dirname(idx), i["id"] + ".json"))]
            check("口型包络都在", not m2, f"{len(items)} 条" + (f"，缺 {m2[:3]}" if m2 else ""))
            check("口型包络覆盖所有台词", len(items) >= len(lines),
                  f"包络 {len(items)} / 台词 {len(lines)}")
            # 母音口型：没装 pypinyin 重跑 make_lipsync.py 会把音素轨**静默**抹掉，
            # 嘴退回只会张合。所以这里要红，不能让它悄悄降级。
            envs = [f for f in glob.glob(os.path.join(os.path.dirname(idx), "*.json"))
                    if not f.endswith("index.json")]
            withvis, badlen = 0, []
            for f in envs:
                e = json.load(open(f, encoding="utf-8"))
                v = e.get("visemes")
                if not v:
                    continue
                withvis += 1
                if len(v) != len(e.get("values", [])):
                    badlen.append(os.path.basename(f))
            check("口型包络带母音音素轨", envs and withvis >= len(envs) * 0.9,
                  f"{withvis}/{len(envs)} 条带 visemes"
                  + ("（缺的那些重跑 make_lipsync.py，需要 pypinyin）" if withvis < len(envs) else ""))
            check("音素轨与包络等长", not badlen, f"{badlen[:3]}" if badlen else f"{withvis} 条逐条核对")


# ------------------------------------------------------------------ 5 前端
def check_web(root):
    section("前端：HTML id 唯一 + JS 引用的 id 都存在")
    html_ids = {}
    for h in glob.glob(os.path.join(root, "web/*.html")):
        ids = re.findall(r'\bid="([^"]+)"', open(h, encoding="utf-8").read())
        dup = sorted({i for i in ids if ids.count(i) > 1})
        check(f"{os.path.basename(h)} id 唯一", not dup, f"重复 {dup}" if dup else f"{len(ids)} 个")
        html_ids[os.path.basename(h)] = set(ids)
    pairs = [("test.js", "test.html"), ("app.js", "index.html")]
    for js, html in pairs:
        jp = os.path.join(root, "web", js)
        if not os.path.exists(jp) or html not in html_ids:
            continue
        used = set(re.findall(r'\$\("([^"]+)"\)', open(jp, encoding="utf-8").read()))
        # 动态创建的节点 id 以 ls-/p-/v-/s- 之外的前缀出现时也可能是后插的，统一看存在性
        missing = sorted(u for u in used if u not in html_ids[html])
        check(f"{js} 引用的 id 都在 {html}", not missing, f"缺 {missing[:4]}" if missing else
              f"{len(used)} 个")


# ------------------------------------------------------------------ 6 契约
def check_contract(root):
    section("契约：代码里的 HTTP 端点都写进文档了")
    src = os.path.join(root, "src", "headless", "main_headless.c")
    if not os.path.exists(src):
        return
    eps = sorted(set(re.findall(r'"(/api/[a-z_.]+)"', open(src, encoding="utf-8").read())))
    docs = ""
    for d in ("docs/ART_PARTS.md", "docs/memory/WORKFLOW.md", "docs/memory/GAPS.md",
              "docs/memory/PROJECT_SPEC.md", "README.md"):
        p = os.path.join(root, d)
        if os.path.exists(p):
            docs += open(p, encoding="utf-8").read()
    undoc = [e for e in eps if e not in docs]
    check("端点都有文档", not undoc, f"{len(eps)} 个端点" + (f"，没写文档：{undoc}" if undoc else ""))


# ------------------------------------------------------------------ 7 工具链
def check_tools(root):
    section("工具链：重建脚本引用的工具都在 + 全部能编译")
    rb = os.path.join(root, "tools", "rebuild_parts.sh")
    if os.path.exists(rb):
        used = sorted(set(re.findall(r"tools/([a-z_0-9]+\.py)", open(rb, encoding="utf-8").read())))
        miss = [u for u in used if not os.path.exists(os.path.join(root, "tools", u))]
        check("重建链里的工具都在", not miss, f"{len(used)} 个" + (f"，缺 {miss}" if miss else ""))
        # 反向再查一遍：切件工具漏进重建链 = 零件会静默过期。
        # （真出过两次：眼睑那次七步漏一步、侧发那次十二步漏一步，
        #   表现都是"单独跑一遍工具好好的，重建一次零件就没了"。）
        txt = open(rb, encoding="utf-8").read()
        allmk = sorted(os.path.basename(f) for f in
                       glob.glob(os.path.join(root, "tools", "make_*_parts.py")))
        # 例外：不是从 base.png 这条身体重建链上走的工具（输入是另一批图）
        off_chain = {"make_face_parts.py"}    # 表情特写切件，输入是 parts_src/expressions
        notin = [m for m in allmk if m not in txt and m not in off_chain]
        check("切件工具都进了重建链", not notin,
              f"{len(allmk)} 个" + (f"，漏了 {notin}" if notin else ""))
        # 步骤编号必须连号、总数一致（改脚本时最容易忘改的就是这个）
        steps = re.findall(r'step\s+"(\d+)/(\d+)\s', txt)
        nums = [int(a) for a, _ in steps]
        tots = {int(b) for _, b in steps}
        ok = bool(steps) and nums == list(range(1, len(nums) + 1)) and tots == {len(nums)}
        check("重建链步骤编号连号", ok,
              f"{len(nums)} 步，分母 {sorted(tots)}")
    bad = []
    pys = glob.glob(os.path.join(root, "tools/*.py")) + glob.glob(os.path.join(root, "scripts/*.py"))
    for f in pys:
        try:
            compile(open(f, encoding="utf-8").read(), f, "exec")
        except SyntaxError as e:
            bad.append(f"{os.path.basename(f)}:{e.lineno}")
    check("Python 工具语法都正确", not bad, f"{len(pys)} 个" + (f"，坏：{bad}" if bad else ""))
    shs = glob.glob(os.path.join(root, "scripts/*.sh")) + glob.glob(os.path.join(root, "tools/*.sh"))
    badsh = []
    for f in shs:
        r = subprocess.run(["bash", "-n", f], capture_output=True, text=True)
        if r.returncode != 0:
            badsh.append(os.path.basename(f))
    check("Shell 脚本语法都正确", not badsh, f"{len(shs)} 个" + (f"，坏：{badsh}" if badsh else ""))


# ------------------------------------------------------------------ 8 仓库卫生
def check_hygiene(root):
    section("仓库卫生：素材没漏提交 + 没有巨型文件 + 日志没进库")
    tracked = [l for l in git(root, "ls-files").splitlines() if l]
    check("仓库非空且能读", len(tracked) > 50, f"{len(tracked)} 个文件在库")

    big = []
    for f in tracked:
        p = os.path.join(root, f)
        if os.path.exists(p) and os.path.getsize(p) > 8 * 1024 * 1024:
            big.append(f"{f} {os.path.getsize(p)//1024//1024}MB")
    check("没有 >8MB 的巨型文件", not big, f"{big[:2]}" if big else "")

    logs = [f for f in tracked if f.startswith("logs/")]
    check("logs/ 没进库", not logs, f"误提交 {logs[:3]}" if logs else "（gitignore 生效）")

    sp = set(glob.glob("characters/*/forms/*/sprites/*.png", root_dir=root))
    untracked = sorted(sp - set(tracked))
    check("素材全部已提交", not untracked, f"漏提交 {len(untracked)} 张：{untracked[:3]}"
          if untracked else f"{len(sp)} 张")

    status = git(root, "status", "--porcelain")
    dirty = [l for l in status.splitlines() if l and not l.startswith("??")]
    if _strict:          # 只有 CI（--strict）才把"有未提交改动"当失败
        check("工作区干净", not dirty, f"{len(dirty)} 处未提交改动")
    elif not _quiet:
        print(f"  说明  工作区改动                       {len(dirty)} 处（开发中正常）")


def main():
    global _quiet, _strict
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    ap.add_argument("--quiet", action="store_true")
    ap.add_argument("--strict", action="store_true",
                    help="CI 用：工作区有未提交改动也算失败")
    a = ap.parse_args()
    _quiet = a.quiet
    _strict = a.strict
    root = os.path.abspath(a.root)
    print(f"仓库自检（静态核对）：{root}")
    for fn in (check_memory, check_json, check_rig, check_live2d, check_character,
               check_web, check_contract, check_tools, check_hygiene):
        try:
            fn(root)
        except Exception as e:                            # noqa: BLE001
            check(f"{fn.__name__} 本身出错", False, repr(e))
    print(f"\n合计 {_n} 项，{_fail} 项不通过 → " + ("全部通过" if not _fail else "有问题，别交付"))
    sys.exit(1 if _fail else 0)


if __name__ == "__main__":
    main()
