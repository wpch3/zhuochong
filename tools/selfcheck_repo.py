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
        pnames = {q["id"] for q in r.get("params", [])}
        badin = []
        for f in phys:
            drv = f.get("driver")
            ins = f.get("input") or []
            # G43：输入可以是参数数组（官方 physics3 的 Input），这类没有 driver
            if ins:
                for one in ins:
                    if one.get("param") not in pnames:
                        badin.append(f"{f['id']}→{one.get('param')}")
            elif drv not in gids and drv not in seen:
                badchain.append(f"{f['id']}→{drv}")
            if f.get("deformer") and f["deformer"] not in dids:
                baddfm.append(f"{f['id']}→{f['deformer']}")
            seen.append(f.get("id"))
        check("physics 的参数输入都指向真参数", not badin,
              f"坏输入 {badin}" if badin else
              f"{sum(1 for f in phys if f.get('input'))} 条吃参数")
        nchain = sum(1 for f in phys if not f.get("input") and f.get("driver") not in gids)
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
    "ParamKneeL": "左膝屈伸（标准表没有腿参数；bend 的 sine 峰正好落在膝盖高度）",
    "ParamKneeR": "同上",
    "ParamWeightShift": "重心左右（一个参数同时驱动骨盆横移与两腿补偿，站立微动）",
    "ParamTiptoe": "踮脚（整体上提 + 脚踝收，裙摆下沿仍不动）",
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


def check_plan_traceability(root):
    """「我们所有的计划不能忘」—— 把这句话落成闸。

    用户 2026-10-14 明确要求计划不能只停在对话里。文档会写，但写完照样会忘：
    真正的风险是**需求写进了 REQUIREMENTS，却没有任何地方安排谁去做**，
    半年后翻出来发现它从来没进过排期。所以这里做双向追溯：

      · 每条需求（A/B/C/D/E/F/H/I 系）必须在 TASKS 或 GAPS 里被提到
      · 每个缺口 G<n> 必须在 TASKS 里有落点，或自己写明已修完
      · PLATFORM_PLAN 里列出的 G 编号必须真的在 GAPS 里登记过

    任何一条断链都判红。这比"记得写文档"可靠，因为它每次 make check 都跑。
    """
    section("计划追溯：需求 → 缺口 → 任务，一条都不许断")
    mem = os.path.join(root, "docs/memory")

    def rd(name, base=mem):
        fp = os.path.join(base, name)
        return io.open(fp, encoding="utf-8").read() if os.path.exists(fp) else ""

    req, tasks, gaps = rd("REQUIREMENTS.md"), rd("TASKS.md"), rd("GAPS.md")
    plan = rd("PLATFORM_PLAN.md", os.path.join(root, "docs"))
    elsewhere = tasks + gaps + plan

    # ① 每条需求要么自己写明落点（表格第 4 列），要么在排期里被引用到。
    #    REQUIREMENTS 的表格是 | 编号 | 需求 | 来源 | 落点 | 状态 |，
    #    落点列填了 T9.1 / src/win32 这种就算有归宿；空着就必须在别处排期。
    orphan, nreq = [], 0
    for line in req.splitlines():
        m = re.match(r"\|\s*([ABCDEFHI]\d+)\s*\|", line)
        if m:
            nreq += 1
            cols = [c.strip() for c in line.strip().strip("|").split("|")]
            landing = cols[3] if len(cols) > 3 else ""
            status = cols[4] if len(cols) > 4 else ""
            if "✅" in status or "已完成" in status:   # 做完了就不用再排期
                continue
            if landing in ("", "—", "-", "待定", "TBD"):
                if not re.search(r"\b" + m.group(1) + r"\b", elsewhere):
                    orphan.append(m.group(1))
            continue
        m = re.match(r"#+\s*([ABCDEFHI]\d+)\s", line)      # 小节形式的需求（A22/A23…）
        if m:
            nreq += 1
            rid = m.group(1)
            # 小节形式的需求，落点可能写在小节正文里（"已落成闸"/"验收口径"），
            # 所以正文提到闸或验收也算有归宿。
            body = req[req.index(line):]
            body = body[:body.find("\n## ", 1) if body.find("\n## ", 1) > 0 else len(body)]
            if ("已落成闸" in body or "验收口径" in body
                    or re.search(r"\b" + rid + r"\b", elsewhere)):
                continue
            orphan.append(rid)
    check("每条需求都有落点（自己写明或排进任务）", not orphan,
          f"{orphan[:8]} 既没写落点也没进排期 —— 这就是「计划被忘掉」的样子"
          if orphan else f"{nreq} 条需求全部可追溯")

    # ② 缺口编号都要有归宿：要么排了期，要么自己写明修完了。
    #    GAPS 里编号有两种写法：老的表格行 | G12 （…） 和新的小节标题 ## G68 …
    gnums = {int(m) for m in re.findall(r"^#+\s*G(\d+)", gaps, re.M)}
    gnums |= {int(m) for m in re.findall(r"^\|\s*~*\s*G(\d+)[a-z]?\d?\s*~*\s*[（(|]",
                                         gaps, re.M)}
    done = {int(m) for m in re.findall(
        r"(?:^#+\s*G|^\|\s*~*\s*G)(\d+)[^\n]*?(?:修完|已修|完成|做完|✅|~~)", gaps, re.M)}
    # 老格式把落点写在编号后的括号里：| G2 (T9.2) | …
    inline = {int(m) for m in re.findall(r"^\|\s*~*\s*G(\d+)[a-z]?\d?\s*\(T[\d.]+\)",
                                         gaps, re.M)}
    lost = sorted(g for g in gnums
                  if g not in done and g not in inline
                  and not re.search(r"\bG%d\b" % g, tasks + plan))
    check("每个缺口要么排了期要么写明修完", not lost,
          f"G{lost[:8]} 既没修完也没进 TASKS/计划" if lost
          else f"{len(gnums)} 个缺口，{len(done)} 个已了结，其余都有排期")

    # ③ 计划里提到的 G 编号必须真的在 GAPS 登记过（防止计划里凭空冒出一个编号）
    plan_g = {int(m) for m in re.findall(r"\bG(\d+)\b", plan)}
    unlogged = sorted(g for g in plan_g if g not in gnums)
    check("计划里的缺口编号都在 GAPS 登记过", not unlogged,
          f"G{unlogged[:8]} 出现在计划里但 GAPS 没这条" if unlogged
          else f"计划引用 {len(plan_g)} 个编号，全部有据")

    # ④ 用户明确排除的东西，不许偷偷出现在代码和配置里
    banned = ("doubao", "volcengine", "volces", "火山方舟")
    hit = []
    for sub in ("src", "config", "web"):
        d = os.path.join(root, sub)
        for dp, _dn, fns in os.walk(d):
            for fn in fns:
                if not fn.endswith((".c", ".h", ".js", ".json", ".css")):
                    continue
                fp = os.path.join(dp, fn)
                try:
                    low = io.open(fp, encoding="utf-8").read().lower()
                except (UnicodeDecodeError, OSError):
                    continue
                for b in banned:
                    if b in low:
                        hit.append(os.path.relpath(fp, root) + " 命中 " + b)
    check("代码与配置里没有豆包 / 火山（用户明确排除）", not hit, "；".join(hit[:3]))


def check_no_stale_decisions(root):
    """不许留着已经作废的结论 —— 用户说的「不要出现操作断代」。

    断代最常见的形态不是漏做，而是**文档里留着一个已经被推翻的说法**，
    后来的人（或后来的我）照着它做。2026-10-14 就真发生过一次：
    调研笔记第十五批写着"网络竞技游戏明确不在名单内"，而用户后来澄清
    网游不是排除、只是锁在只读档 —— 两份文档打架。

    规则：凡是记录了"被推翻/已作废"信息的地方，必须在同一份文档里
    带上修正指引（警示框或「修正」小节），不能只留旧说法。
    这里盯住几个已知的高风险口径，发现新旧说法并存却没有修正标记就判红。
    """
    section("口径一致：不留已作废的结论")
    docs_dir = os.path.join(root, "docs")

    def rd(rel):
        fp = os.path.join(root, rel)
        return io.open(fp, encoding="utf-8").read() if os.path.exists(fp) else ""

    # 判据踩过两次坑才定下来：
    #   ① 盯"旧说法的原文" —— 原文一改措辞闸就失效（当场踩过）
    #   ② 盯"整份文档里有没有现行口径" —— 长文档里别处的"只读""档一"会蒙混过关（又踩一次）
    # 所以按**节**判：某一节里说了网游被排除/不做，就必须在**同一节内**
    # 给出现行口径或修正指引。半截话留在节里，后来的人只读那一节就会被带沟里。
    STALE_SAY = re.compile(r"不在名单内|被排除|不做网络竞技|完全禁止网游|排除网游")
    FIXED_SAY = re.compile(r"修正|档一|只读档|只看不碰|陪聊|不代打|watch_and_chat")
    TOPIC = re.compile(r"英雄联盟|网络竞技|网游")
    for rel in ("docs/REFERENCE_NOTES.md", "docs/memory/REQUIREMENTS.md",
                "docs/PLATFORM_PLAN.md", "docs/memory/GAPS.md"):
        txt = rd(rel)
        if not txt:
            continue
        # 按二级标题切节；没有标题的文档整篇算一节
        parts = re.split(r"(?m)^##\s", txt)
        bad = []
        for sec in parts:
            if not TOPIC.search(sec) or not STALE_SAY.search(sec):
                continue
            if not FIXED_SAY.search(sec):
                title = sec.splitlines()[0][:40] if sec.splitlines() else "(无标题)"
                bad.append(title)
        check(f"{os.path.basename(rel)} 没有「只说排除、不说现行口径」的半截话",
              not bad,
              f"这些小节里只说了网游被排除，没写现在怎么办：{bad[:3]}")

    # 现行口径本身必须自洽：A25 既然是三档，就不能同时写着"不做网游"
    req = rd("docs/memory/REQUIREMENTS.md")
    has_tiers = "档一" in req and "档二" in req and "档三" in req
    says_ban = bool(re.search(r"A25\.\d+\s+\*\*不做网络竞技", req))
    check("A25 的三档模式没有和「不做网游」并存", not (has_tiers and says_ban),
          "同一份 REQUIREMENTS 里既写了三档又写了不做网游")

    # 档位表与需求文档必须说同一件事
    gt = os.path.join(root, "config", "game_tiers.json")
    if os.path.exists(gt) and has_tiers:
        d = json.load(io.open(gt, encoding="utf-8"))
        lol = next((g for g in d.get("games", []) if g.get("id") == "lol"), None)
        check("档位表与 A25 口径一致（网游在档一而不是被删掉）",
              bool(lol) and lol.get("max_tier") == 1,
              "A25 说网游锁档一，档位表里却查不到 lol" if not lol
              else f"lol max_tier={lol.get('max_tier')}")


def check_action_dead_time(root):
    """非循环动作的声明时长不许比通道真实结束晚太多（2026-10-14 加）。

    用户反馈"点击时有个中途卡顿"，查出来是 clicked 声明 0.55 秒，但
    bounce(dur 0.28) 到点归零、decay 的包络 7*exp(-6t/0.4) 在 0.28s 已衰到
    0.1 度 —— 后面 0.27 秒角色完全不动，然后"啪"地切回 idle。
    同样的毛病当时还有 happy / hammered / tiptoe 三个。

    判据按波形算每条通道真正结束的时刻：
      · bounce  sin(pi*u)，u=t/dur → dur 到点自然归零
      · decay   amp*exp(-6t/dur)，包络衰到 2% 即看不见 → dur*ln(50)/6
      · sine/flap 有 freq 的是循环型，铺满整个动作
      · pulse   冲上去之后**保持**，靠动作的 fade_out 收尾 —— 这种"不动"
                是有意的姿势保持，不算死时间，所以带 pulse 的动作直接放行
    """
    section("动作没有尾巴空转（声明时长要贴着通道）")
    import math
    rig_path = os.path.join(root, "characters", "xiaoxun", "forms", "teen", "rig.json")
    if not os.path.isfile(rig_path):
        return
    with io.open(rig_path, encoding="utf-8") as fh:
        rig = json.load(fh)
    worst = []
    for a in rig.get("actions", []):
        dur = a.get("duration")
        if not dur or a.get("loop"):
            continue
        chans = a.get("channels", [])
        if any(c.get("wave") == "pulse" for c in chans):
            continue                      # 保持型姿势，尾部静止是有意的
        ends = []
        for c in chans:
            w, d = c.get("wave", "sine"), c.get("dur")
            if w == "decay" and d:
                ends.append(d * math.log(50) / 6.0)
            elif d:
                ends.append(d)
            elif c.get("freq"):
                ends.append(dur)
        if not ends:
            continue
        dead = dur - max(ends)
        if dead > 0.15:
            worst.append((a["id"], dur, max(ends), dead))
    check("没有动作在结尾空转超过 0.15 秒", not worst,
          "；".join("%s 声明%.2fs 通道%.2fs 空转%.2fs" % w for w in worst)
          if worst else "逐个核对过")


def check_motion_measure(root):
    """动画实测工具的三道防护不许被拆（2026-10-14 加）。

    这个工具的价值不在"能跑出数字"，而在它强制带上负对照、饱和检查和周期防呆。
    拆掉任何一个，它就退化成当初那个"看起来很漂亮但全是假数"的临时脚本
    （LESSONS 78/79 两次误判都是这么来的）。"""
    section("动画实测工具的防护没被拆")
    f = os.path.join(root, "tools", "measure_motion.py")
    if not check("动画实测工具在", os.path.isfile(f), "tools/measure_motion.py"):
        return
    with io.open(f, encoding="utf-8") as fh:
        txt = fh.read()
    for need, label, why in (
        ("--control", "负对照 --control 还在", "没有它量到的是整体位移的混淆"),
        ("def ceiling", "饱和检查 ceiling() 还在", "不先算天花板就报比例会误判"),
        ("def self_variance", "自方差 self_variance() 还在", "一次性和循环不能同指标"),
        ("def loop_period", "周期防呆 loop_period() 还在", "窗盖不住周期就量不到"),
    ):
        check(label, need in txt, why)
    check("提示了要做 A/B", "A/B" in txt, "单边测量不足以归因")


def check_form_roadmap(root):
    """形态路线图与磁盘必须对得上。

    「其他形态先留空、做好了再加」这个做法只有配上这条闸才不会烂掉 —— 否则半年后
    没人说得清 loli/adult/chibi 是「还没做」还是「做了但坏了」。规则三条：
      · 清单写 status=ready 的，forms/<id>/rig.json 必须真的存在
      · 磁盘上有 rig.json 的，必须在清单里登记（做完了忘记登记，名字会退回目录名）
      · planned 的形态不许留半拉子素材目录（有素材就该做完登记成 ready）
    """
    section("形态路线图：声明与磁盘一致")
    chars_dir = os.path.join(root, "characters")
    if not os.path.isdir(chars_dir):
        return
    for cid in sorted(os.listdir(chars_dir)):
        cdir = os.path.join(chars_dir, cid)
        forms_dir = os.path.join(cdir, "forms")
        rm_path = os.path.join(cdir, "forms.json")
        if not os.path.isdir(cdir) or not os.path.isdir(forms_dir):
            continue
        on_disk = sorted(d for d in os.listdir(forms_dir)
                         if os.path.exists(os.path.join(forms_dir, d, "rig.json")))
        check(f"{cid} 有形态路线图 forms.json", os.path.exists(rm_path),
              "缺了这份清单，界面上就只剩做好的形态，规划中的会凭空消失")
        if not os.path.exists(rm_path):
            continue
        decl = {f["id"]: f for f in
                json.load(io.open(rm_path, encoding="utf-8")).get("forms", [])}
        bad = [i for i, f in decl.items()
               if f.get("status") == "ready" and i not in on_disk]
        check(f"{cid} 声明 ready 的形态都有 rig.json", not bad,
              f"{bad} 写着 ready 但 forms/<id>/rig.json 不存在")
        missing = [i for i in on_disk if i not in decl]
        check(f"{cid} 磁盘上的形态都已登记", not missing,
              f"{missing} 有素材却没写进 forms.json")
        half = [i for i, f in decl.items()
                if f.get("status") != "ready"
                and os.path.isdir(os.path.join(forms_dir, i))]
        check(f"{cid} planned 的形态没有半拉子素材", not half,
              f"{half} 标着 planned 却有素材目录 —— 要么做完登记 ready，要么删干净")
        bad_status = [i for i, f in decl.items()
                      if f.get("status") not in ("ready", "planned")]
        check(f"{cid} 形态状态只用 ready/planned", not bad_status, f"{bad_status}")


def check_live2d(root):
    section("Live2D 标准合规：参数命名 / 取值范围 / model3 分组（静态）")

    # ⑭ 动作淡化只认官方那条曲线（CubismMath.getEasingSine = 0.5−0.5cos(πt)）。
    #    单测能抓"函数算错了"，抓不住"函数还在、调用处偷偷换回 smoothstep"，
    #    所以这里盯住调用点本身。
    rigc = io.open(os.path.join(root, "src/core/zrig.c"), encoding="utf-8").read()
    m = re.search(r"static void compute_group_transforms\(.*?\n\}\n", rigc, re.S)
    body = m.group(0) if m else ""
    check("能定位 compute_group_transforms（动作淡化在这里算）", bool(body),
          f"{len(body)} 字符")
    check("动作淡入用官方 getEasingSine", "z_ease_sine(u)" in body,
          "z_ease_sine(u)" if "z_ease_sine(u)" in body else "没找到，是不是换回 smoothstep 了")
    check("动作淡化不许再用 smoothstep", "z_smoothstep" not in body,
          "干净" if "z_smoothstep" not in body else "compute_group_transforms 里还有 z_smoothstep")
    check("非循环动作按自己的 FadeOutTime 收尾",
          "a->fade_out" in body and "tot > 0.0" in body,
          "w *= z_ease_sine((tot - el) / a->fade_out)")
    check("循环动作不淡出（官方 endTime<0 时 fadeOut 恒 1）",
          re.search(r"tot > 0\.0 && a->fade_out", body) is not None,
          "淡出乘法被 tot>0 挡住")
    check("ease_sine 实现就是 0.5-0.5cos(pi t)",
          "0.5 - 0.5 * cos(t * 3.14159265358979323846)" in
          io.open(os.path.join(root, "src/core/zc.c"), encoding="utf-8").read(),
          "src/core/zc.c:z_ease_sine")
    # ⑱ 平台契约（G50）：能力/供应商/网关三份契约与生成出来的清单必须同步。
    #    细目由 tools/check_platform.py 负责，这里只盯"清单没过期"这件事 ——
    #    契约改了却忘了重新生成 web/platform.json，界面上看到的就是旧的。
    import subprocess
    rc = subprocess.run([sys.executable, os.path.join(root, "tools/check_platform.py"), "--check"],
                        capture_output=True, text=True)
    check("平台契约自检通过（tools/check_platform.py）", rc.returncode == 0,
          (rc.stdout.strip().splitlines() or ["?"])[-1])
    pf_p = os.path.join(root, "web/platform.json")
    if os.path.exists(pf_p):
        pf = json.load(io.open(pf_p, encoding="utf-8"))
        cap_dir = os.path.join(root, "config/capabilities")
        prov_dir = os.path.join(root, "config/providers")
        n_cap = len([x for x in os.listdir(cap_dir) if x.endswith(".json")])
        n_prov = len([x for x in os.listdir(prov_dir) if x.endswith(".json")])
        check("web/platform.json 与契约数量一致（改了契约要重新生成）",
              len(pf.get("capabilities", [])) == n_cap and len(pf.get("providers", [])) == n_prov,
              f"清单 {len(pf.get('capabilities', []))}/{len(pf.get('providers', []))} vs 契约 {n_cap}/{n_prov}")
        ids = {p["id"] for p in pf.get("providers", [])}
        onfile = {x[:-5] for x in os.listdir(prov_dir) if x.endswith(".json")}
        check("清单里的供应商都有契约文件", ids == onfile,
              f"清单独有 {sorted(ids - onfile)} / 文件独有 {sorted(onfile - ids)}" if ids != onfile else f"{len(ids)} 个")
    else:
        check("web/platform.json 已生成", False, "跑 python3 tools/check_platform.py")

    # ⑲ 网关（G51）：这几条约束一旦被改掉，表现都是"悄悄花钱"或"悄悄发空密钥"，
    #    运行时看不出来，所以钉在源码层面。注意要剥掉注释再 grep ——
    #    否则注释里提到这些词就能把闸骗过去（之前栽过一次）。
    def code_of(rel):
        txt = io.open(os.path.join(root, rel), encoding="utf-8").read()
        out, i, n = [], 0, len(txt)
        while i < n:
            c = txt[i]
            if c == '"':
                # 字符串字面量要整段保留：zgateway.c 里就有 "secret://"，
                # 不认字符串的话里面那个 // 会被当成行注释，把后面半行吃掉。
                out.append(c); i += 1
                while i < n:
                    out.append(txt[i])
                    if txt[i] == "\\" and i + 1 < n:
                        out.append(txt[i + 1]); i += 2; continue
                    if txt[i] == '"':
                        i += 1; break
                    i += 1
                continue
            if txt.startswith("/*", i):
                j = txt.find("*/", i + 2)
                i = n if j < 0 else j + 2
            elif txt.startswith("//", i):
                j = txt.find("\n", i)
                i = n if j < 0 else j
            else:
                out.append(c); i += 1
        return "".join(out)

    gw_c = code_of("src/core/zgateway.c")
    check("路由必须跳过没启用的供应商",
          "if (!r->enabled) continue;" in gw_c,
          "src/core/zgateway.c:zgw_pick —— 少了它，用户关掉的供应商照样会被调用")
    check("结算入账的是实际花费而不是预扣额",
          "g->spent_total += actual;" in gw_c and "spent_total += h->estimated" not in gw_c,
          "src/core/zgateway.c:zgw_hold_settle")
    check("退还不记花费",
          "zgw_hold_release" in gw_c and gw_c.count("g->spent_total +=") == 1,
          "失败的请求不该扣钱，全文件只应有一处 spent_total 累加")
    check("密钥只认 secret:// 引用",
          'strncmp(ref, "secret://", 9)' in gw_c,
          "src/core/zgateway.c:zgw_secret_resolve —— 允许裸值就等于允许密钥进仓库")
    def body_of(code, sig):
        """抠出一个 C 函数的函数体（大括号配平）。整文件数 return 0 是没意义的——
        别的函数成功时也 return 0。"""
        i = code.find(sig)
        if i < 0:
            return ""
        i = code.find("{", i)
        if i < 0:
            return ""
        depth, j = 0, i
        while j < len(code):
            if code[j] == "{":
                depth += 1
            elif code[j] == "}":
                depth -= 1
                if depth == 0:
                    return code[i:j + 1]
            j += 1
        return code[i:]

    sec_body = body_of(gw_c, "int zgw_secret_resolve")
    check("密钥取不到时不许返回成功",
          bool(sec_body) and sec_body.count("return 0;") == 1,
          "zgw_secret_resolve 里只有拿到密钥那一条路径能 return 0，"
          "实际 %d 处" % sec_body.count("return 0;"))
    check("网关端点已注册", '"/api/gateway.json"' in code_of("src/headless/main_headless.c"),
          "src/headless/main_headless.c")

    # 路由表是生成物，必须和契约对得上（内容一致性由 check_platform --check 管，
    # 这里只核"每个供应商都写了 priority"——漏写的话路由顺序会变成随机的）
    gr_p = os.path.join(root, "config/gateway_routes.json")
    if os.path.exists(gr_p):
        gr = json.load(io.open(gr_p, encoding="utf-8"))
        prov_dir = os.path.join(root, "config/providers")
        noprio = [x for x in os.listdir(prov_dir) if x.endswith(".json")
                  and not isinstance(json.load(io.open(os.path.join(prov_dir, x),
                                                       encoding="utf-8")).get("priority"), int)]
        check("每个供应商都写了 priority", not noprio, str(noprio))

        rts = gr.get("routes", [])
        bycap = {}
        for r in rts:
            bycap.setdefault(r["cap"], []).append(r["priority"])
        unsorted_caps = [c for c, ps in bycap.items() if ps != sorted(ps, reverse=True)]
        check("路由表内每种能力按优先级降序排好", not unsorted_caps,
              "运行时取第一个就是首选，顺序错了等于路由错 " + str(unsorted_caps))
    else:
        check("config/gateway_routes.json 已生成", False, "跑 python3 tools/check_platform.py")

    # ⑳ 音色库（G64）：用户 2026-10-14 要求去掉本地声源、全部换云端标准音色，
    # 并且"每个 AI 的声音都不一样、不能同一种生源"。契约层面的校验在 check_platform
    # 里（⑱ 组已经 subprocess 调它了），这里守文件层面——防的是"删了一半"和"手改生成物"。
    vb_dir = os.path.join(root, "config/voicebank")
    nvb = len([x for x in os.listdir(vb_dir) if x.endswith(".json")]) if os.path.isdir(vb_dir) else 0
    check("音色库契约齐全", nvb >= 12, "config/voicebank/ 下 %d 个" % nvb)

    # 本地声源必须删干净。留半截的后果是：配置还指着它，跑起来才报找不到模型文件。
    leftovers = [x for x in ("voices", "tools/voice_local.py", "tools/voice_packs.py",
                             "tools/voice_setup.sh")
                 if os.path.exists(os.path.join(root, x))]
    check("本地声源已删干净", not leftovers, "还剩 %s" % leftovers)
    # 删文件容易漏引用——配置和脚本里不能再指着它
    ref_local = []
    for f in ("config/voices.json", "tools/voice_render.py", "web/layout.json"):
        fp = os.path.join(root, f)
        if os.path.exists(fp):
            t = io.open(fp, encoding="utf-8").read()
            if "piper" in t.lower() or "voices/xiaoya" in t or "voice_local" in t:
                ref_local.append(f)
    check("没有残留的本地声源引用", not ref_local, str(ref_local))

    # config/voices.json 现在是生成物（第四个降级成生成物的遗留格式）。
    # 手改它会在下次 check_platform 跑的时候被覆盖，所以文件头必须有警告。
    vj = os.path.join(root, "config/voices.json")
    if os.path.exists(vj):
        d = json.load(io.open(vj, encoding="utf-8"))
        check("voices.json 标明了是生成物",
              "check_platform" in (d.get("_note") or ""),
              "缺 _note 警告，会有人手改它")
        bad_v = [v for v in d.get("voices", []) if not v.get("character")]
        check("voices.json 每条都有 character", not bad_v,
              "C 侧 load_voices() 要求非空，否则整条被丢掉")

    # 情绪映射：桌宠脸上的表情和声音里的情绪要对得上
    emp = os.path.join(root, "config/emotion_map.json")
    check("情绪映射表在", os.path.exists(emp), "config/emotion_map.json")
    if os.path.exists(emp):
        em = json.load(io.open(emp, encoding="utf-8"))
        # 四条通路缺一不可——少一条就意味着某家供应商没法表达情绪
        modes = set()
        for e in em.get("emotions", {}).values():
            if e.get("style"): modes.add("style")
            if e.get("minimax"): modes.add("emotion")
            if e.get("tag"): modes.add("inline_tag")
            if e.get("prosody"): modes.add("prosody")
        check("情绪映射覆盖四种通路", len(modes) == 4, "只有 %s" % sorted(modes))

    # 面板要挂上去，不然做了等于没做
    lay = json.load(io.open(os.path.join(root, "web/layout.json"), encoding="utf-8"))
    allc = []
    for r in lay.get("regions", {}).values():
        allc += [x if isinstance(x, str) else x.get("id") for x in r]
    check("音色库面板已挂进布局", "voicebank" in allc, str(allc))

    # 组件只能从 web 根目录取文件。写成 config/ 下的路径在单测里（直接读文件）发现不了，
    # 一跑真服务就 404 —— 整块面板静默降级。这里按组件源码里的 fetch 反查。
    import re as _re
    comp_dir = os.path.join(root, "web/components")
    miss_data = []
    for f in sorted(os.listdir(comp_dir)):
        if not f.endswith(".js"):
            continue
        src = io.open(os.path.join(comp_dir, f), encoding="utf-8").read()
        for m in _re.findall(r'api\(\s*"(/[A-Za-z0-9_./\-]+\.json)"', src):
            if m.startswith("/api/"):
                continue                       # 动态接口，不是静态文件
            if not os.path.exists(os.path.join(root, "web", m.lstrip("/"))):
                miss_data.append(f + " 要 " + m)
    # 跨语言契约：前端拼的 query 参数名，必须和 C 侧 qstr/qint 读的那个名字一致。
    # 这条是血的教训 —— 2026-10-14 一天之内踩了两次：
    #   /api/viseme 真实签名是 v=音素&w=音量，前端写成了 id=&v=
    #   /api/pause  真实签名是 on=0|1，      前端写成了 v=
    # 两次都"返回 200 ok"，功能静默失效，单测的 fetch stub 又不校验参数名，
    # 只有拿真服务一个个点才会发现。静态核一遍最省事。
    import re as _re2
    hc = io.open(os.path.join(root, "src/headless/main_headless.c"), encoding="utf-8").read()

    def _ep_body(ep):
        """按大括号配平抠出某个端点的处理块 —— 整文件 grep 会跨到别的端点去。"""
        m = _re2.search(r'if \(strcmp\(r->path, "%s"\) == 0\) \{' % _re2.escape(ep), hc)
        if not m:
            return ""
        i, d = m.end() - 1, 0
        while i < len(hc):
            if hc[i] == "{":
                d += 1
            elif hc[i] == "}":
                d -= 1
                if d == 0:
                    break
            i += 1
        return hc[m.start():i + 1]

    bad_q = []
    for f in sorted(os.listdir(comp_dir)):
        if not f.endswith(".js"):
            continue
        src = io.open(os.path.join(comp_dir, f), encoding="utf-8").read()
        pairs = []
        # 形式一：api("/api/xx?k=" + v)  —— 抓问号后所有 k=
        for m in _re2.finditer(r'"(/api/[a-z.]+)\?([^"]*)"', src):
            ep = m.group(1)
            for k in _re2.findall(r'([a-zA-Z_][a-zA-Z0-9_]*)=', m.group(2)):
                pairs.append((ep, k, f))
        # 形式二：api("/api/xx", { k: v })  —— host.api 会把对象拼成 query
        for m in _re2.finditer(r'"(/api/[a-z.]+)"\s*,\s*\{([^}]*)\}', src):
            ep = m.group(1)
            for k in _re2.findall(r'([a-zA-Z_][a-zA-Z0-9_]*)\s*:', m.group(2)):
                pairs.append((ep, k, f))
        for ep, k, fn in pairs:
            body = _ep_body(ep)
            if not body:
                bad_q.append("%s 调了不存在的端点 %s" % (fn, ep))
                continue
            if ('"%s"' % k) not in body:
                bad_q.append("%s 给 %s 传了 %s=，但 C 侧没读这个名字" % (fn, ep, k))
    check("前端传的参数名和 C 侧读的对得上", not bad_q,
          "；".join(sorted(set(bad_q))[:4]) if bad_q else "逐个核过")

    check("组件要的数据文件都在 web 根下", not miss_data,
          "；".join(miss_data) if miss_data else "都能取到")

    # ⑰ 界面骨架（G1）：layout.json 是界面的唯一装配表，它和组件文件必须对得上。
    #    配置里写了但组件不存在 / 组件文件忘了 register / 主题缺色键 —— 这三样
    #    在浏览器里都只表现为"某块空白"，静态核一遍最省事。
    web = os.path.join(root, "web")
    lay_p = os.path.join(web, "layout.json")
    if os.path.exists(lay_p):
        lay = json.load(io.open(lay_p, encoding="utf-8"))
        regions = lay.get("regions", {})
        ids = []
        for rk, items in regions.items():
            for it in items:
                ids.append(it if isinstance(it, str) else it.get("id"))
        check("layout.json 能解析且有区域", bool(regions), f"{len(regions)} 个区域 / {len(ids)} 个组件")
        missing, unreg = [], []
        for cid in ids:
            f = os.path.join(web, "components", f"{cid}.js")
            if not os.path.exists(f):
                missing.append(cid)
                continue
            src = io.open(f, encoding="utf-8").read()
            if f'id: "{cid}"' not in src and f"id: '{cid}'" not in src:
                unreg.append(cid)
        check("layout 引用的组件文件都在", not missing, f"缺 {missing}" if missing else f"{len(ids)} 个都在")
        check("每个组件文件都注册了同名 id", not unreg,
              f"对不上 {unreg}" if unreg else "id 与文件名一致")
        # 区域容器必须在 index.html 里真的存在，否则那一区整块不显示
        idx = io.open(os.path.join(web, "index.html"), encoding="utf-8").read()
        noreg = [rk for rk in regions if f'id="region-{rk}"' not in idx]
        check("index.html 里有 layout 用到的全部区域容器", not noreg,
              f"缺 #region-{noreg}" if noreg else " ".join(sorted(regions)))
        # 主题：每个主题都要给齐同一套变量，少一个色就会露出上一个主题的残留
        themes = [t.get("id") for t in lay.get("themes", [])] or ["sakura"]
        keysets, badt = {}, []
        for t in themes:
            tp = os.path.join(web, "themes", f"{t}.json")
            if not os.path.exists(tp):
                badt.append(t)
                continue
            keysets[t] = set((json.load(io.open(tp, encoding="utf-8")).get("vars") or {}).keys())
        check("layout 里列出的主题文件都在", not badt, f"缺 {badt}" if badt else " ".join(themes))
        if len(keysets) > 1:
            base = set.union(*keysets.values())
            diff = {t: sorted(base - ks) for t, ks in keysets.items() if base - ks}
            check("各主题的变量表要齐平（少一个色就会串主题）", not diff,
                  f"缺色 {diff}" if diff else f"{len(base)} 个变量")
        # 内核不该再残留业务逻辑：app.js 里写死 getElementById 就说明组件化没做干净
        app_js = io.open(os.path.join(web, "app.js"), encoding="utf-8").read()
        hard = app_js.count("getElementById")
        check("内核 app.js 不写死页面元素（业务归组件）", hard <= 1,
              f"{hard} 处 getElementById（只许保留查区域容器那一处）")

    # ⑯ 眉形 ParamBrowL/RForm 的几何约束。官方 Cubism 手册：
    #    「変形」只改形状、不带位置移动（上下/左右/角度另有参数）。
    #    这是配置层的事（看得到每个控制点），所以在这里核，不在单测里核。
    for rp in sorted(glob.glob(os.path.join(root, "characters/*/forms/*/rig.json"))):
        r = jsonc(rp)
        dfs = {g["id"]: g for g in r.get("deformers", [])}
        pids2 = {q["id"] for q in r.get("params", [])}
        if "ParamBrowLForm" not in pids2:
            continue
        for side in ("l", "r"):
            gid = f"brow_{side}_form"
            g = dfs.get(gid)
            check(f"{gid} 存在", g is not None, gid)
            if not g:
                continue
            cols = {}
            for q in g.get("points", []):
                cols.setdefault(q["c"], q.get("dy", 0.0))
            vs = [cols[c] for c in sorted(cols)]
            mid = vs[len(vs) // 2]
            ends = (vs[0] + vs[-1]) / 2.0
            check(f"{gid} 中段与两端反向（才是'变形'不是'平移'）",
                  mid * ends < 0, f"中段 {mid:+.2f} / 两端均值 {ends:+.2f}")
            tot, mag = sum(vs), sum(abs(v) for v in vs)
            check(f"{gid} 净位移要远小于形变量（官方：変形不带位置移动）",
                  mag > 0 and abs(tot) / mag < 0.25,
                  f"净和 {tot:+.2f} / 形变量 {mag:.2f} = {abs(tot)/mag:.3f}")

    # ⑮ 网格形变器与 bend 必须共存、同部件多张网格必须累加（G43 修的两个 bug）。
    #    单测从像素那头验效果，这里从源码这头把退化路径钉死。
    zimgc = io.open(os.path.join(root, "src/core/zimg.c"), encoding="utf-8").read()
    m2 = re.search(r"static void draw_state\(.*?\n\}\n", rigc, re.S)
    ds = m2.group(0) if m2 else ""
    check("能定位 draw_state（决定一笔怎么画）", bool(ds), f"{len(ds)} 字符")
    check("网格路径要把 bend 一起带上", "zimg_draw_mesh_bend_blend" in ds,
          "mesh+bend 同时画" if "zimg_draw_mesh_bend_blend" in ds else "又退回 if/else 互斥了")
    check("网格路径不许丢 bend", "st->warped ? st->bx" in ds,
          "bx/by 传进去了" if "st->warped ? st->bx" in ds else "bend 参数被写死成 0")
    check("zimg 侧有 mesh+bend 的实现", "zimg_draw_mesh_bend_blend" in zimgc and
          "zimg_bend_factor(tb, curve_x)" in zimgc, "src/core/zimg.c")
    mdg = re.search(r"/\* 一个部件可以挂多张网格.*?\n    \}", rigc, re.S)
    dgs = mdg.group(0) if mdg else ""
    # 注意：别直接 grep "break" —— 这段代码的注释里就写着"不能找到第一张就 break"，
    # 会把自己判红（已经踩过一次）。只认带分号的真语句。
    dgs_code = "\n".join(ln.split("/*")[0] for ln in dgs.splitlines())
    check("同部件的多张网格要累加",
          bool(dgs) and "+=" in dgs_code and "break;" not in dgs_code,
          "累加且不提前 break" if dgs and "+=" in dgs_code and "break;" not in dgs_code
          else "又变回「找到第一张就 break」了")
    check("加载时拦住同部件不同尺寸的网格", "网格尺寸不一样" in rigc,
          "load_deformers 有校验")
    check("physics 支持参数输入（官方 physics3 的 Input）",
          "ph->n_in" in rigc and "in_param" in rigc, "zphys.n_in / in_param")

    check("pulse 波形不再自带收尾 hack",
          "total - 0.15" not in rigc,
          "干净" if "total - 0.15" not in rigc else "W_PULSE 里还留着 total-0.15 的后门")

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
    for fn in (check_memory, check_plan_traceability, check_no_stale_decisions,
               check_json, check_rig, check_action_dead_time, check_motion_measure,
               check_form_roadmap,
               check_live2d, check_character,
               check_web, check_contract, check_tools, check_hygiene):
        try:
            fn(root)
        except Exception as e:                            # noqa: BLE001
            check(f"{fn.__name__} 本身出错", False, repr(e))
    print(f"\n合计 {_n} 项，{_fail} 项不通过 → " + ("全部通过" if not _fail else "有问题，别交付"))
    sys.exit(1 if _fail else 0)


if __name__ == "__main__":
    main()
