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
import argparse, datetime, glob, json, os, re, subprocess, sys

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
        ghosts = []
        for a in r.get("actions", []):
            for c in a.get("channels", []):
                t = c.get("target", "")
                if t and t not in pids and t not in gids:
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
    for fn in (check_memory, check_json, check_rig, check_character,
               check_web, check_contract, check_tools, check_hygiene):
        try:
            fn(root)
        except Exception as e:                            # noqa: BLE001
            check(f"{fn.__name__} 本身出错", False, repr(e))
    print(f"\n合计 {_n} 项，{_fail} 项不通过 → " + ("全部通过" if not _fail else "有问题，别交付"))
    sys.exit(1 if _fail else 0)


if __name__ == "__main__":
    main()
