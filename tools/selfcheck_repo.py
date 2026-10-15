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
import argparse, datetime, glob, io, json, math, os, re, subprocess, sys

OK, BAD = "通过", "不通过"
_fail = 0
_n = 0
_quiet = False
_strict = False


# 分两栏计数的理由（2026-10-15 自我校准）：
#   加了结论登记表和真机验收清单之后，600 项里有 324 项（54%）在检查"我有没有好好填表"。
#   项数一膨胀，"0 不通过"这个信号就变便宜了 —— 读的人分不清这一把绿里有多少是
#   "软件是对的"、多少是"文档是齐的"。两者的价值完全不同：
#   文档纪律红了是"记账没跟上"，工程事实红了是"软件坏了"，后者才该拦住交付。
#   所以这里按小节分类计数，末尾分开报。
DOC_KEYS = ("记忆区", "结论登记表", "真机验收清单", "口径一致", "计划", "文档",
            "写进文档", "需求", "交接", "记账")
_cur_kind = "eng"
_kind_n = {"eng": 0, "doc": 0}
_kind_fail = {"eng": 0, "doc": 0}


def check(name, cond, detail=""):
    global _fail, _n
    _n += 1
    _kind_n[_cur_kind] += 1
    if not cond:
        _fail += 1
        _kind_fail[_cur_kind] += 1
    if not cond or not _quiet:
        print(f"  {OK if cond else BAD}  {name:<28} {detail}")
    return bool(cond)


def section(title):
    global _cur_kind
    _cur_kind = "doc" if any(k in title for k in DOC_KEYS) else "eng"
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
def check_decisions(root):
    """结论登记表必须写全（A33，2026-10-15 加；同日按用户授权做了校准）。

    用户 2026-10-15：「我发现你自行推翻了很多自己得出的结论，下次再给出结论之前
    一定要仔细确认，再三检查。旧结论可以推翻，但是检查必不可少。」
    后又授权：「你可以自行判断我的规则，做出边界以及优化，不用完全被这个约束。」

    复盘 2026-10-14 被推翻的四条，没有一条是算错，全都是**下结论时少做一步**：
    前提没验 / 只做一次模拟就否决 / 指标选错 / 否定结论没复查。
    所以把"有后果的结论"做成有字段的登记表，缺字段就判红。

    —— 校准点（为什么这个函数现在只报 8 项而不是 166 项）——
    原来每个条目每个字段各算一项，26 条就刷出 166 项。检出能力一点没多，
    但把"0 不通过"这个信号稀释了：读的人分不清这把绿里有多少是软件真的对。
    现在改成**每条规则一项、把违例全列在 detail 里** —— 一条规则坏了只红一项，
    但 detail 直接告诉你是哪几条坏的。负控验证过：四次故意改坏，照样四次报红。
    """
    section("结论登记表（A33：下结论之前先查）")
    fp = os.path.join(root, "docs", "memory", "DECISIONS.md")
    if not check("结论登记表在（docs/memory/DECISIONS.md）", os.path.isfile(fp),
                 "A33.6 要求的落点"):
        return
    with io.open(fp, encoding="utf-8") as fh:
        txt = fh.read()
    # 先把 ``` 围栏里的示例剥掉 —— 文件开头那段"怎么写一条"的模板里
    # 也有一行 ### DC##，不剥的话闸会去检查模板本身（第一版就这么红过）。
    txt = re.sub(r"(?s)```.*?```", "", txt)
    blocks = re.split(r"(?m)^### ", txt)[1:]
    STATUS = ("✅", "❌", "🔁")
    ids, bad_head, bad_st, miss_field = [], [], [], []
    no_super, lazy_neg, weak_na = [], [], []
    for b in blocks:
        head = b.splitlines()[0].strip()
        m = re.match(r"(DC\d+)\s*(\S+)", head)
        if not m:
            bad_head.append(head[:28])
            continue
        did, st = m.group(1), m.group(2)
        ids.append(did)
        body = b.split("\n### ")[0]
        if st not in STATUS:
            bad_st.append("%s=%s" % (did, st))
        for field in ("前提", "证据", "负控", "复查触发"):
            mm = re.search(r"(?m)^-\s*%s[：:]\s*(.+)$" % field, body)
            if not (mm and len(mm.group(1).strip()) >= 6):
                miss_field.append("%s 缺%s" % (did, field))
        neg = re.search(r"(?m)^-\s*负控[：:]\s*(.+)$", body)
        negtxt = neg.group(1) if neg else ""
        if st == "🔁" and not re.search(r"由\s*DC\d+\s*取代", head + body):
            no_super.append(did)
        if st == "❌" and ("没做" in negtxt or negtxt.strip().startswith("❌")):
            lazy_neg.append(did)
        # 校准新增：负控写"不适用"的，必须给出替代检验，不能一句话带过
        if re.match(r"\s*(➖|不适用|无法)", negtxt) and not re.search(
                r"替代|反证|代价|对照", negtxt + body):
            weak_na.append(did)

    check("条目标题都是「DC## <状态> 一句话」", not bad_head,
          "不合格：%s" % bad_head[:3] if bad_head else "%d 条" % len(ids))
    check("状态只用 ✅/❌/🔁", not bad_st, "；".join(bad_st[:3]) if bad_st else "无自创状态")
    check("四个字段（前提/证据/负控/复查触发）齐全", not miss_field,
          "；".join(miss_field[:5]) if miss_field
          else "%d 条 × 4 栏全齐" % len(ids))
    check("🔁已推翻的都写明被哪条取代", not no_super,
          "没写的：%s" % no_super[:3] if no_super else "读的人不会不知道该信谁")
    check("❌否决类的负控不是「没做」", not lazy_neg,
          "糊弄的：%s" % lazy_neg[:3] if lazy_neg
          else "否决会关掉一条路，必须答『如果反过来会怎样』")
    check("负控写「不适用」的都给了替代检验", not weak_na,
          "只写了不适用：%s" % weak_na[:3] if weak_na
          else "路线类结论做不了负控，但要说清楚拿什么代替")
    check("编号不重复", len(ids) == len(set(ids)),
          "重复：%s" % [i for i in ids if ids.count(i) > 1][:3])
    refs = set(re.findall(r"由\s*(DC\d+)\s*取代", txt))
    missing = sorted(refs - set(ids))
    check("「由 DC## 取代」指向的条目都存在", not missing, "找不到：%s" % missing)
    check("登记表里留着被推翻的反面教材", 
          len([b for b in blocks if b.startswith("DC0") and "🔁" in b.splitlines()[0]]) >= 4,
          "被推翻的中间结论也要留着（用户 2026-10-14 的要求）")
    # 反膨胀：表太长就没人读了，该归档的归档（校准时加的上限）
    check("登记表没有膨胀到没人读（≤ 40 条）", len(ids) <= 40,
          "%d 条 —— 超了就把已推翻且无人引用的移进归档段" % len(ids))


def check_acceptance(root):
    """A32.4：真机验收清单与 TASKS 的 [需真机] 标记双向对账。

    这张表的价值全在"对得上"三个字：
      · TASKS 里标了 [需真机] 却没登记 → 又变成散在备注里的、永远不会被验的东西；
      · 清单里留着 TASKS 已经删掉的条目 → 读的人以为还欠着，实际早没了。
    两个方向都查，而且是全称判断（每一处，不是"有一处对"）—— LESSONS 97。

    同 check_decisions：按规则计数，不按条目×字段计数（校准，见那边的说明）。
    """
    section("真机验收清单（A32 / G82）")
    fp = os.path.join(root, "docs", "ACCEPTANCE.md")
    tp = os.path.join(root, "docs", "memory", "TASKS.md")
    if not check("真机验收清单在（docs/ACCEPTANCE.md）", os.path.isfile(fp),
                 "A32.1 要求的落点；T23.4"):
        return
    with io.open(fp, encoding="utf-8") as fh:
        txt = re.sub(r"(?s)```.*?```", "", fh.read())
    with io.open(tp, encoding="utf-8") as fh:
        tasks = fh.read()

    marked, stray = [], []
    for line in tasks.splitlines():
        if "[需真机]" not in line:
            continue
        m = re.match(r"\|\s*(T\d+\.\d+)\s*\|", line)
        if m:
            marked.append(m.group(1))
        else:
            stray.append(line.strip()[:30])
    check("[需真机] 标记都挂在任务行上", not stray,
          "散在说明文字里的无法对账：%s" % stray[:2] if stray
          else "%d 处标记" % len(marked))

    blocks = re.split(r"(?m)^### ", txt)[1:]
    listed, acids, bad_head, no_box, miss_field = [], [], [], [], []
    for b in blocks:
        head = b.splitlines()[0].strip()
        m = re.match(r"(AC-\d+)\s*·\s*(T\d+\.\d+)", head)
        if not m:
            bad_head.append(head[:28])
            continue
        acid, tid = m.group(1), m.group(2)
        acids.append(acid)
        listed.append(tid)
        body = b.split("\n### ")[0]
        if not re.search(r"`\[( |~|x)\]`", head):
            no_box.append(acid)
        for field in ("怎么测", "算过", "不过先查", "沙箱边界"):
            mm = re.search(r"(?m)^-\s*%s[：:]\s*(.+)$" % field, body)
            if not (mm and len(mm.group(1).strip()) >= 6):
                miss_field.append("%s 缺%s" % (acid, field))

    check("条目标题都是「AC-## · T#.#」", not bad_head,
          "不合格：%s" % bad_head[:3] if bad_head else "%d 条" % len(acids))
    check("每条都有勾选框 [ ]/[~]/[x]", not no_box,
          "没框的：%s" % no_box[:3] if no_box else "只有用户能勾")
    check("四栏（怎么测/算过/不过先查/沙箱边界）齐全", not miss_field,
          "；".join(miss_field[:5]) if miss_field
          else "%d 条 × 4 栏全齐；最容易糊弄的是『沙箱边界』" % len(acids))
    check("AC 编号不重复", len(acids) == len(set(acids)),
          "重复：%s" % [i for i in acids if acids.count(i) > 1][:3])
    miss = sorted(set(marked) - set(listed))
    check("TASKS 里每处 [需真机] 都登记进清单了", not miss,
          "漏登：%s —— 这正是『写了但从没验证过』的来源" % miss
          if miss else "%d 处全部对上" % len(marked))
    extra = sorted(set(listed) - set(marked))
    check("清单里没有 TASKS 已经不标 [需真机] 的条目", not extra,
          "多出：%s —— 清单比现实旧了" % extra if extra else "没有过期条目")


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
    "ParamHipDrop": "胯下沉／屈膝承重（上身起伏但脚不离地；和 ParamBaseY 的区别就是它不动脚）",
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

    # —— 第二个高风险口径（2026-10-14 加）：踮脚 ——
    # 原话在 GAPS G88 / TASKS T24 里写着"脚部拆件已否决""要走 AI 重绘"，
    # 两条都已被推翻（否决的前提是"踮脚时鞋会变扁"，而正确物理是鞋变高；
    # AI 重绘两次都保不住构图，最后是几何重采样做成的）。
    # 这种"把一条对的路否掉"的旧结论留在文档里，杀伤力比漏写大得多。
    STALE_FOOT = re.compile(r"拆件.{0,6}否决|否决.{0,6}拆件|AI 重绘踮脚|重绘踮脚姿态")
    FIXED_FOOT = re.compile(r"作废|已推翻|⚠|不是让人照着做|最终实现|正确口径|变高")
    for rel in ("docs/memory/GAPS.md", "docs/memory/TASKS.md",
                "docs/ART_PARTS.md", "docs/REFERENCE_NOTES.md"):
        txt = rd(rel)
        if not txt:
            continue
        bad = []
        for sec in re.split(r"(?m)^##\s", txt):
            if not STALE_FOOT.search(sec) or FIXED_FOOT.search(sec):
                continue
            bad.append((sec.splitlines() or ["(无标题)"])[0][:40])
        check(f"{os.path.basename(rel)} 没有留着「脚部拆件已否决」这类已推翻的结论",
              not bad, f"这些小节还在说踮脚只能 AI 重绘 / 拆件被否决：{bad[:3]}")

    # —— 文档里的数字必须和生成物对得上（2026-10-14 加）——
    # 断代的另一种形态：文字还在，数字已经过期。照着过期数字去改素材，
    # 结果就是"按文档做出来的东西过不了闸"。这里盯住踮脚这几个关键常数。
    art = rd("docs/ART_PARTS.md")
    fp_path = os.path.join(root, "characters", "xiaoxun", "forms", "teen",
                           "sprites", "foot_parts.json")
    rig_path = os.path.join(root, "characters", "xiaoxun", "forms", "teen", "rig.json")
    if art and os.path.isfile(fp_path) and os.path.isfile(rig_path):
        fj = json.load(io.open(fp_path, encoding="utf-8"))
        rj = json.load(io.open(rig_path, encoding="utf-8"))
        # 判据要的是"**每一处**都对"，不是"有一处对"：
        # 第一版写成 `token in art` 时做负控发现，把文档里某一处 lift 改成 24
        # 照样绿 —— 因为别处还留着 lift=30。半对半错的文档恰恰最坑人。
        for label, key, real in (("抬高 lift", "lift", "%g" % fj["lift_px"]),
                                 ("鞋底压扁 ks", "ks", "%g" % fj["warp"]["sole_squash"]),
                                 ("鞋身拉伸 ku", "ku", "%g" % fj["warp"]["upper_stretch"])):
            got = re.findall(r"%s\s*=\s*([0-9.]+)" % key, art)
            check("ART_PARTS 里的%s处处等于素材的 %s（%d 处）" % (label, real, len(got)),
                  bool(got) and all(g.rstrip(".") == real for g in got),
                  "文档里写着 %s —— 数字过期（或只改了一半）的文档比没有文档更坑"
                  % (sorted(set(got)) or "根本没写"))
        want = [("腿件切线（画布）", "%d" % (int(fj["cut"]["leg_cut_y"]) + 68))]
        xf = (rj.get("xfades") or [{}])[0].get("in") or []
        if len(xf) == 2:
            want.append(("交叉淡化窗口", "[%.2f,%.2f]" % (xf[0], xf[1])))
        for label, token in want:
            check("ART_PARTS 里的%s和素材一致（%s）" % (label, token), token in art,
                  "文档里找不到 %s —— 数字过期的文档比没有文档更坑" % token)

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


def check_render_parallel(root):
    """分块渲染与 PNG 并行编码的结构性前提（T30.2，2026-10-15 加）。

    这两处的正确性闸在 tests/test_core.c（逐字节对拍）和 tools/api_smoke.py
    （用 Python 标准 zlib 解 /api/frame.png）里，跑起来要半分钟。
    这里只做**静态**的那几条：谁把关键代码删了，1 秒内就红。

    为什么这几条值得单独拦：
      · 所有会写 dst 的 zimg 函数都必须尊重 clip_y，漏一个就是静默的数据竞争
        —— 画面偶尔花一下，复现不出来，查到死；
      · zimg_new 用的 z_alloc 是裸 malloc，clip 字段不显式清零就是随机裁剪；
      · send_png 曾经是"写 /tmp 再读回来再 remove"，每帧三次文件系统往返，
        谁改回去都等于白做这一轮；
      · adler32 必须是延迟取模版（每字节取模慢 7 倍，4.6MB 14.3ms → 2.1ms）。
    """
    section("渲染分块 / PNG 并行的结构前提")
    zimg_c = os.path.join(root, "src", "core", "zimg.c")
    zimg_h = os.path.join(root, "src", "core", "zimg.h")
    zrig_c = os.path.join(root, "src", "core", "zrig.c")
    zdef_c = os.path.join(root, "src", "core", "zdeflate.c")
    head_c = os.path.join(root, "src", "headless", "main_headless.c")
    mk = os.path.join(root, "Makefile")
    for f in (zimg_c, zimg_h, zrig_c, zdef_c, head_c, mk):
        if not os.path.isfile(f):
            return
    rd = lambda f: io.open(f, encoding="utf-8").read()
    ic, ih, rc, dc, hc, mkt = rd(zimg_c), rd(zimg_h), rd(zrig_c), rd(zdef_c), rd(head_c), rd(mk)

    check("zimg 结构里有行裁剪字段 clip_y0/clip_y1",
          "clip_y0" in ih and "clip_y1" in ih)
    check("zimg_new 显式初始化 clip（z_alloc 不清零）",
          "im->clip_y0 = 0;" in ic and "im->clip_y1 = 0;" in ic)
    # 四个会写 dst 的入口都要调一次 zimg_clip_range
    nclip = ic.count("zimg_clip_range(")
    check("zimg.c 里尊重 clip 的写入点 ≥ 4 处（clear/draw_impl/draw_tri/composite）",
          nclip >= 5, f"{nclip} 处（含定义）")
    check("zimg_band 还在（分块靠它做共享像素的带视图）",
          "zimg zimg_band(" in ic)
    check("zrig 每条带各有自己的 scratch/maskbuf（共享会互相 clear 掉）",
          "band_scratch" in rc and "band_maskbuf" in rc)
    check("zrig 起线程前预分配带缓冲（惰性分配会在多线程里抢同一个槽）",
          "if (!r->band_scratch[i]) r->band_scratch[i] = zimg_new(fw, fh);" in rc)
    check("单线程路径会把带缓冲的 clip 重置成整幅",
          "b.scratch->clip_y1 = fh;" in rc)
    check("zrig_set_render_threads 还在（测试靠它做单线程/多线程对拍）",
          "void zrig_set_render_threads(" in rc)

    check("deflate 支持可拼接分段 zdeflate_lz77_part",
          "size_t zdeflate_lz77_part(" in dc)
    check("非末段要补空 stored 块对齐到字节（不然位流错位）",
          "while (b.bitcnt != 0) bw_putbit(&b, 0);" in dc)
    check("adler32 是延迟取模版（批长 5552）",
          "5552" in dc and "z_adler32" in dc)
    check("拼接流的 adler32 按原始数据算",
          "z_adler32(raw, rawlen)" in dc)
    check("PNG 编码走并行行带", "z_parallel_for(nb, png_band" in ic)

    # ⚠ 别拿 "zc_frame_" 当判据：那串字还留在解释这段历史的注释里（第一版就这么误报了）。
    #    要查的是**代码**：有没有再去写临时文件、再读回来。
    check("send_png 走内存编码，不再写 /tmp 再读回来",
          "zimg_encode_png(im, &len)" in hc
          and "zimg_save_png(im, tmp_path" not in hc
          and "z_read_file(tmp_path" not in hc)
    check("Makefile 带 -pthread（少了它线程创建会失败）",
          "-pthread" in mkt)


def check_engine_caps(root):
    """rig 里声明的条数不许超过引擎的静态上限（2026-10-14 加）。

    引擎用 `#define ZRIG_MAX_xxx` 开固定数组，解析循环写的是
    `for (i = 0; i < n && r->nxxx < MAX; ++i)` —— **超出的部分直接丢掉**。

    实测代价：ZRIG_MAX_PHYS 曾是 12，而 rig 里已经声明到 13 条，
    第 13 条 `back_x`（后发摆动，look_around 时峰值 1.77px，是全场最大的一个摆）
    **一直是哑的**，从头到尾没有任何报错，谁也没发现。
    直到再加一条把 skirt_y 也挤掉，单测「裙摆纵摆」才红出来。
    同类坑 ZRIG_MAX_PARAMS 也撞过（48 → 64）。

    现在引擎里超限已改成硬报错，这道闸是第二层：在**跑之前**就拦住，
    并且要求留出余量（快顶满时提前提醒，不要等撞上）。
    """
    section("rig 的条数没有顶到引擎上限（静默截断）")
    src = os.path.join(root, "src", "core", "zrig.c")
    rig_path = os.path.join(root, "characters", "xiaoxun", "forms", "teen", "rig.json")
    if not (os.path.isfile(src) and os.path.isfile(rig_path)):
        return
    with io.open(src, encoding="utf-8") as fh:
        csrc = fh.read()
    with io.open(rig_path, encoding="utf-8") as fh:
        rig = json.load(fh)
    caps = [("ZRIG_MAX_PHYS", "physics"), ("ZRIG_MAX_PARAMS", "params"),
            ("ZRIG_MAX_PARTS", "parts"), ("ZRIG_MAX_XFADE", "xfades")]
    for macro, key in caps:
        m = re.search(r"#define\s+%s\s+(\d+)" % macro, csrc)
        if not check("zrig.c 里找得到 %s" % macro, m is not None):
            continue
        cap = int(m.group(1))
        used = len(rig.get(key, []))
        check("%s 没超（%s 用了 %d / 上限 %d）" % (macro, key, used, cap), used <= cap,
              "超出的会被静默丢掉 —— back_x 就这么哑了很久")
        check("%s 还有余量（用量不超过上限的 85%%）" % macro, used <= cap * 0.85,
              "用了 %d / %d = %.0f%%，快顶满了，加东西之前先把上限调大"
              % (used, cap, used * 100.0 / cap))


def check_torso_inertia(root):
    """上身要慢半拍追头，而且这个摆必须是收敛的（2026-10-14 加）。

    Live2D 官方《提高动态质量的技巧》第 2 条：
    「转动脸部，身体会在稍后跟随」—— 脸和身体**同时**到位仍然像机器人。

    实现上靠一条物理：input=ParamAngleZ，输出写 seg_torso.bend_x。
    它能和 ParamAngleZ→chest.rot_deg 那条瞬时绑定共存而不重复计数，
    是因为物理的输出是 `pos - target`（纯滞后量），静止时自动归零。

    这里顺便把摆的参数钉住：阻尼比 ζ = damping / (2√stiffness)。
    ζ 太小会一直晃，太大就等于没有惯性。
    """
    section("上身慢半拍追头，且摆是收敛的")
    rig_path = os.path.join(root, "characters", "xiaoxun", "forms", "teen", "rig.json")
    if not os.path.isfile(rig_path):
        return
    with io.open(rig_path, encoding="utf-8") as fh:
        rig = json.load(fh)
    ph = next((x for x in rig.get("physics", [])
               if x.get("id") == "torso_follow_head"), None)
    if not check("有 torso_follow_head 这条物理", ph is not None,
                 "没有 → 头和身体同时到位，官方说这仍然像机器人"):
        return
    ins = [i.get("param") for i in ph.get("input", [])]
    check("它的输入是头部歪头参数", "ParamAngleZ" in ins, "输入：%s" % ins)
    check("它的输出写在躯干上", ph.get("part") == "seg_torso",
          "part=%s" % ph.get("part"))
    st, dp = ph.get("stiffness"), ph.get("damping")
    if check("stiffness / damping 都写了", st and dp):
        zeta = dp / (2.0 * (st ** 0.5))
        check("阻尼比 ζ 落在收敛区间 0.4~1.2（太小一直晃，太大等于没惯性）",
              0.4 <= zeta <= 1.2,
              "ζ = %.2f / (2*sqrt(%.0f)) = %.3f" % (dp, st, zeta))
        check("躯干要比头发慢（stiffness 低于呆毛的 42）", st < 42,
              "躯干 %.0f vs 呆毛 42 —— 躯干是重的，不该跟头发一样弹" % st)
    check("惯性量被 max 钳住", (ph.get("max") or 0) > 0,
          "max=%s" % ph.get("max"))


def check_tiptoe_grounded(root):
    """踮脚时脚底必须留在地面上（2026-10-14 加；同日 T24.5 改口径）。

    这条闸的历史值得留着 —— 它换过两次说法，照着旧说法改会直接踩坑：

    第一版（错）：`root.dy = -7` 和 `seg_leg_*.bend_y = -5` **同号**，
      两个一起往上 → 不是踮脚，是整个人连脚浮空 12px（最底行 1359 → 1347）。
      用户反馈"踮脚脚部没有变化"，有一半是这个 —— 脚跟着人飘走了。

    第二版（对，但只是权宜）：root 上提多少，腿的底端就 bend_y 下推多少抵消。
      脚底钉住了，可鞋本身只被压扁 3px，看不出踮脚。

    第三版（现在，T24.5）：鞋拆成独立部件，另有一张**踮脚姿态**的鞋
      （鞋身纵向拉长 lift、鞋底带压扁）。于是：
        root.dy = -lift（整个人升）
        foot_l/foot_r 两个**组** dy = +lift（鞋钉在地上）
        腿不再需要拉伸 —— 鞋口自己长高了 lift，正好接住升上去的脚踝。
      所以有鞋拆件时，ParamTiptoe 上**不应该**再有 seg_leg_* 的 bend_y。
    """
    section("踮脚时脚底钉在地面（不许整个人浮空）")
    base = os.path.join(root, "characters", "xiaoxun", "forms", "teen")
    rig_path = os.path.join(base, "rig.json")
    if not os.path.isfile(rig_path):
        return
    with io.open(rig_path, encoding="utf-8") as fh:
        rig = json.load(fh)
    foot_path = os.path.join(base, "sprites", "foot_parts.json")
    footp = None
    if os.path.isfile(foot_path):
        with io.open(foot_path, encoding="utf-8") as fh:
            footp = json.load(fh)
    tp = next((p for p in rig.get("params", []) if p["id"] == "ParamTiptoe"), None)
    if not check("找得到 ParamTiptoe", tp is not None):
        return
    lift = None
    legs, feet = [], []
    for b in tp.get("binds", []):
        if b.get("group") == "root" and b.get("param") == "dy":
            lift = b.get("scale")
        elif b.get("param") == "bend_y" and str(b.get("part", "")).startswith("seg_leg"):
            legs.append((b.get("part"), b.get("scale"), b.get("curve")))
        elif b.get("param") == "dy" and str(b.get("group", "")).startswith("foot_"):
            feet.append((b.get("group"), b.get("scale")))
    if not check("ParamTiptoe 有 root.dy 上提", lift is not None):
        return

    if footp:
        # —— 有踮脚鞋素材：靠两只脚的组反向位移钉地 ——
        check("踮脚抬起量和鞋素材是同一个数（素材 lift=%s）" % footp.get("lift_px"),
              abs(abs(lift) - float(footp.get("lift_px", -1))) < 0.51,
              "rig 的 root.dy=%s，鞋是按 lift=%s 画的；两边不一致 = 鞋口接不上脚踝"
              % (lift, footp.get("lift_px")))
        if check("ParamTiptoe 绑了两只脚的组 dy", len(feet) == 2,
                 "实际 %d 条：%s" % (len(feet), feet)):
            for grp, sc in feet:
                check("%s 的 dy 与 root.dy **异号**（同号 = 整个人浮空）" % grp,
                      sc is not None and sc * lift < 0,
                      "root.dy=%s  %s.dy=%s" % (lift, grp, sc))
                check("%s 的 dy 量值与 root.dy 相抵（鞋底净位移≈0）" % grp,
                      sc is not None and abs(abs(sc) - abs(lift)) < 0.51,
                      "|%s| vs |%s|" % (sc, lift))
        check("有鞋拆件时腿不再拉伸（旧口径已作废）", not legs,
              "ParamTiptoe 上还挂着 %s —— 鞋口已经自己长高 lift，再拉腿会把袜子抻长" % (legs,))
        return

    # —— 没有踮脚鞋素材时的退路：腿底端下推抵消 ——
    if not check("ParamTiptoe 有两条腿的 bend_y", len(legs) == 2,
                 "实际 %d 条：%s" % (len(legs), legs)):
        return
    for part, sc, curve in legs:
        check("%s 的 bend_y 与 root.dy **异号**（同号 = 整个人浮空）" % part,
              sc is not None and lift is not None and sc * lift < 0,
              "root.dy=%s  %s.bend_y=%s —— 同号时实测角色最底行 1359→1347" % (lift, part, sc))
        check("%s 的 bend_y 量值与 root.dy 相抵（脚底净位移≈0）" % part,
              sc is not None and abs(abs(sc) - abs(lift)) < 0.75,
              "|%s| vs |%s|，差 %.2f" % (sc, lift, abs(abs(sc) - abs(lift)))
              if sc is not None else "")
        check("%s 的 bend_y 用 tip 曲线（底端满额才抵得掉）" % part, curve == "tip",
              "实际 curve=%s" % curve)


def check_foot_switch(root):
    """踮脚鞋的切换装置（T24.5，2026-10-14 加）。

    鞋拆成独立部件之后，有三件事只要漏一件就当场出洋相，而且都不会报错：

      ① **鞋不跟腿走**：腿是 bend_x 摆的（ParamLegL 在脚踝处 ±20px），
         bend 只作用于那张贴图自己。鞋是另一张图，不挂 bend_follow 的话
         一摆腿鞋就留在原地 —— 脚踝直接错开十几像素。
         所以 foot_* 组必须 `bend_follow` 对应的腿件，且取样高度 = 切线。
      ② **两张姿态图没有交叉淡化**：会在一帧之间硬切，鞋"跳"一下。
      ③ **层序反了**：踮脚鞋画在常态鞋下面，淡入的时候被盖住，白做。

    另外淡化窗口要窄（≤0.3 量程）：两张图的鞋口差着 lift，交叠期一定看得见
    双轮廓（官方《创建有姿势切换的动态》也只说"尽量减少"）。窗口越窄，
    参数扫过它的时间越短 —— 实测踮脚动作里交叠只有 3 帧 ≈ 50ms。
    """
    section("踮脚鞋：拆件 + 交叉淡化装配正确")
    base = os.path.join(root, "characters", "xiaoxun", "forms", "teen")
    rig_path = os.path.join(base, "rig.json")
    foot_path = os.path.join(base, "sprites", "foot_parts.json")
    if not (os.path.isfile(rig_path) and os.path.isfile(foot_path)):
        return
    with io.open(rig_path, encoding="utf-8") as fh:
        rig = json.load(fh)
    with io.open(foot_path, encoding="utf-8") as fh:
        footp = json.load(fh)
    parts = {p["id"]: p for p in rig.get("parts", [])}
    groups = rig.get("groups", {})
    cutline = int(footp["cut"]["leg_cut_y"]) + 68      # 源图 → 画布（+68）

    for side in ("l", "r"):
        flat, tip = "seg_foot_%s" % side, "seg_foot_%s_tip" % side
        if not check("rig 里有 %s / %s 两件" % (flat, tip),
                     flat in parts and tip in parts):
            continue
        check("%s 画在 %s 上面（淡入才看得见）" % (tip, flat),
              parts[tip]["layer"] > parts[flat]["layer"],
              "layer %s vs %s" % (parts[tip]["layer"], parts[flat]["layer"]))
        check("两件都在 foot_%s 组里" % side,
              parts[flat].get("group") == "foot_%s" % side
              and parts[tip].get("group") == "foot_%s" % side,
              "%s / %s" % (parts[flat].get("group"), parts[tip].get("group")))
        g = groups.get("foot_%s" % side)
        if not check("有 foot_%s 组" % side, isinstance(g, dict)):
            continue
        check("foot_%s 挂在 leg_%s 下面" % (side, side), g.get("parent") == "leg_%s" % side,
              "parent=%s" % g.get("parent"))
        check("foot_%s 跟着腿的形变走（bend_follow）" % side,
              g.get("bend_follow") == "seg_leg_%s" % side,
              "bend_follow=%s —— 不写的话腿一摆（±20px）鞋就留在原地"
              % g.get("bend_follow"))
        check("foot_%s 的取样高度 = 切线 y=%d" % (side, cutline),
              abs(float(g.get("bend_follow_at", -1)) - cutline) <= 1.0,
              "bend_follow_at=%s，切线在 %d（取样点不在切口上，腿脚之间会错位）"
              % (g.get("bend_follow_at"), cutline))

    xf = {x["id"]: x for x in rig.get("xfades", [])}
    check("两只脚各有一条交叉淡化", len(xf) >= 2, "实际 %d 条" % len(xf))
    for side in ("l", "r"):
        x = xf.get("foot_%s_tiptoe" % side)
        if not check("有 foot_%s_tiptoe 这条淡化" % side, x is not None):
            continue
        check("foot_%s_tiptoe 由 ParamTiptoe 驱动" % side, x.get("param") == "ParamTiptoe",
              "param=%s" % x.get("param"))
        check("foot_%s_tiptoe 是 常态鞋 → 踮脚鞋" % side,
              x.get("from") == "seg_foot_%s" % side and x.get("to") == "seg_foot_%s_tip" % side,
              "%s → %s" % (x.get("from"), x.get("to")))
        w = x.get("in", [0.0, 1.0])
        ok = (len(w) == 2 and 0.0 < w[0] < w[1] < 1.0 and (w[1] - w[0]) <= 0.30)
        check("foot_%s_tiptoe 的淡化窗口又窄又在量程内" % side, ok,
              "in=%s —— 要求 0<in0<in1<1 且宽度≤0.30（窗口越宽，双轮廓看得越久）" % (w,))


def check_feet_on_ground(root):
    """动作跑起来时脚底不许离地（T24.5，2026-10-14 加）。

    官方《4.添加身体动作》写死的一条："身体上下运动时，脚不能离开地面"。
    桌宠尤其吃这一条 —— 窗口是透明的，人站在任务栏上，脚一浮就是穿帮。

    之前只量过"拉 ParamTiptoe 滑条时底行不动"，**动作跑起来却是另一回事**：
    tiptoe 里还挂着一条 ParamBaseY（那是给 happy 跳跃用的，走 root.dy、
    不补偿脚），实测动作期间画面最底行 747→744，整个人浮了 3px。
    所以这道闸不看参数，看**动作**：把动作里每条通道的幅度乘上该参数
    对鞋底的纵向系数，加起来必须≈0。

    鞋底的纵向系数 = root.dy（整体升降）
                  + foot_*.dy（两只脚的反向补偿）
                  + Σ seg_leg_*.bend_y × 曲线在跟随取样线处的值
                    （脚是刚性跟随腿在切线处的形变的，腿一纵向形变就把脚抬走）

    真要跳的动作（happy 蹦、hammered 被砸塌、sleep 坐下去）在 rig 里写
    "airborne": true 明示放行 —— 新动作默认是"必须站稳"，想离地得自己声明。
    """
    section("动作跑起来脚也不离地")
    base = os.path.join(root, "characters", "xiaoxun", "forms", "teen")
    rig_path = os.path.join(base, "rig.json")
    bp_path = os.path.join(base, "sprites", "body_parts.json")
    if not os.path.isfile(rig_path):
        return
    with io.open(rig_path, encoding="utf-8") as fh:
        rig = json.load(fh)
    sizes = {}
    if os.path.isfile(bp_path):
        with io.open(bp_path, encoding="utf-8") as fh:
            for q in json.load(fh).get("parts", []):
                if q.get("size"):
                    sizes[q["id"]] = q["size"]
    parts = {p["id"]: p for p in rig.get("parts", [])}
    # 脚在腿的哪条线上取样（画布坐标）
    follow_at = {}
    for gname, g in rig.get("groups", {}).items():
        if gname.startswith("foot_") and g.get("bend_follow"):
            follow_at[g["bend_follow"]] = g.get("bend_follow_at")

    def curve_at(curve, t):
        t = max(0.0, min(1.0, t))
        if curve == "root":
            return (1.0 - t) ** 2
        if curve == "tip":
            return t * t
        if curve == "sine":
            return math.sin(math.pi * t)
        return t

    dsole = {}            # 参数 → 每单位参数值带动鞋底的纵向像素
    for prm in rig.get("params", []):
        tot = 0.0
        for b in prm.get("binds", []):
            pm, grp, prt = b.get("param"), str(b.get("group", "")), str(b.get("part", ""))
            sc = float(b.get("scale", 0) or 0)
            if pm == "dy" and grp == "root":
                tot += sc
            elif pm == "dy" and grp.startswith("foot_"):
                tot += sc / 2.0          # 左右各一条，两条合起来才是一次位移
            elif pm == "bend_y" and prt in follow_at and prt in sizes:
                y0 = parts.get(prt, {}).get("pos", [0, 0])[1]
                h = float(sizes[prt][1]) or 1.0
                tot += sc * curve_at(str(b.get("curve", "root")),
                                     (float(follow_at[prt]) - y0) / h) / 2.0
        if abs(tot) > 1e-9:
            dsole[prm["id"]] = tot
    check("找得到会动到鞋底的参数", bool(dsole),
          "、".join("%s=%+.1f" % kv for kv in sorted(dsole.items())))

    for act in rig.get("actions", []):
        worst = 0.0
        terms = []
        for c in act.get("channels", []):
            tgt = str(c.get("target", ""))
            amp = abs(float(c.get("amp", 0) or 0))
            k = dsole.get(tgt)
            if k is None and tgt == "root" and c.get("param") == "dy":
                k = 1.0                     # 直接写部件通道的老写法
            if not k or amp <= 0:
                continue
            worst += amp * abs(k)
            terms.append("%s %.2f×%+.1f" % (tgt, amp, k))
        decl = act.get("airborne")
        if decl is not None:
            # 声明可以写 true（只表态），也可以写数字（连幅度一起锁住）——
            # 写数字才拦得住"后来有人把 amp 调大了一倍"这种漂移。
            if decl is True:
                check("%s 声明了会离地（%s）" % (act.get("id"), "、".join(terms) or "可并没动到脚"),
                      worst > 0.5, "写了 airborne 却根本不离地，这标记是抄来的，删掉")
            else:
                check("%s 离地幅度和声明对得上（声明 %gpx）" % (act.get("id"), float(decl)),
                      abs(worst - float(decl)) <= 1.0,
                      "实际算出来 %.2fpx，来源：%s" % (worst, "、".join(terms) or "?"))
            continue
        check("%s 全程脚不离地（净位移 %.2fpx）" % (act.get("id"), worst), worst <= 0.5,
              "来源：%s —— 要么补偿两只脚的 dy，要么在动作上写 \"airborne\": true"
              % ("、".join(terms) or "?"))


def check_head_body_link(root):
    """头部参数必须带动身体，且摸头不许拉长脖子（2026-10-14 加）。

    Live2D 官方《提高动态质量的技巧》第 1 条：
    「如果只转动脸部，则会看起来像一个机器人」。
    用户实测反馈同一句话：「光是头在动，身体没联动，看着还是很怪」。

    ParamAngleX/Y 是引擎内建、走 look 系统，本来就同时给 head 和 chest；
    唯独 ParamAngleZ 是普通参数，原先只绑 head.rot_deg，20 个动作里 12 个
    用的正是它 —— A/B 实测：剥掉胸部分量后身体位移是**精确的 0.00px**。

    另外盯住摸头：head.dy 取负 = 把头整个往上平移 = 脖子凭空抽长
    （实测 -9.48px），正确做法是歪头（ParamAngleZ，绕颈关节转，不改颈长）。
    """
    section("头动必须带着身体（不许只有头在动）")
    rig_path = os.path.join(root, "characters", "xiaoxun", "forms", "teen", "rig.json")
    if not os.path.isfile(rig_path):
        return
    with io.open(rig_path, encoding="utf-8") as fh:
        rig = json.load(fh)
    az = next((p for p in rig.get("params", []) if p["id"] == "ParamAngleZ"), None)
    if check("找得到 ParamAngleZ", az is not None):
        tg = {b.get("group"): b.get("scale") for b in az.get("binds", [])}
        check("ParamAngleZ 带动 head", "head" in tg, "绑定：%s" % tg)
        check("ParamAngleZ 也带动 chest（否则歪头时身体是刚体）",
              "chest" in tg and (tg.get("chest") or 0) > 0,
              "绑定：%s —— 剥掉它实测身体位移精确为 0.00px" % tg)
        if "chest" in tg and "head" in tg and tg["head"]:
            ratio = tg["chest"] / tg["head"]
            check("chest/head 比例贴着 look 里调好的 0.24", 0.15 <= ratio <= 0.35,
                  "实际 %.3f（look 里是 chest.rot 1.2 / head.rot 5.0 = 0.24）" % ratio)
    hp = next((a for a in rig.get("actions", []) if a["id"] == "head_pat"), None)
    if check("找得到 head_pat", hp is not None):
        up = [c for c in hp.get("channels", [])
              if c.get("target") == "head" and c.get("param") == "dy"
              and (c.get("amp") or 0) < -0.5]
        check("摸头不许把头整个往上平移（= 脖子抽长）", not up,
              "有 %d 条 head.dy 负向通道：%s" % (len(up), up) if up else "没有负向 head.dy")
        joy = {c.get("target") for c in hp.get("channels", [])}
        check("摸头要有开心表情（笑眼/脸红/笑嘴至少一样）",
              bool(joy & {"ParamEyeLSmile", "ParamEyeRSmile",
                          "ParamCheek", "ParamMouthForm"}),
              "通道目标：%s" % sorted(joy))
        check("摸头要歪头（ParamAngleZ）", "ParamAngleZ" in joy,
              "通道目标：%s" % sorted(joy))


def check_eye_hold_zone(root):
    """动作不许把眼睛停在"交叉淡化幽灵区"，上眼线必须延迟下滑。

    背景（2026-10-15 用户实测反馈"眼睛还是会卡住 / 脸部模糊"）：
    引擎里眨眼是两张图交叉淡化 —— 睁眼件在闭合度 lo 之后开始淡出、闭眼件
    在 lo 之后淡入（zrig.c 里那两行 ZC_CLAMP）。落在这段中间时，屏幕上同时
    有"被压扁的睁眼"和"半透明的闭眼线"，叠出来是一条没有瞳孔的扁青带。
    眨一下眼只路过 0.1 秒看不出来，但 blink_hold 是**一直按着**的：
    stroke（loop）原本按在 0.7，被抚摸时眼睛就永远停在那个坏画面上。
    正解是用山型笑眼件（ParamEyeL/RSmile）表现"眯眼笑"，不是把睁眼压扁。

    两端的阈值都从 zrig.c 里**现读**，读不到就直接红 —— 否则引擎改了公式，
    这个闸会拿着过期的数字继续发绿。
    """
    section("眼睛不停在交叉淡化幽灵区")
    zrig = os.path.join(root, "src", "core", "zrig.c")
    src = read(zrig)
    m_open = re.search(r"\(1\.0 - blink\) / ([0-9.]+)", src)
    m_shut = re.search(r"\(blink - ([0-9.]+)\) / ([0-9.]+)", src)
    check("能从 zrig.c 读出眨眼交叉淡化的阈值", bool(m_open and m_shut),
          f"睁眼淡出分母={m_open.group(1) if m_open else '?'}，"
          f"闭眼起点={m_shut.group(1) if m_shut else '?'}")
    if not (m_open and m_shut):
        return
    lo = float(m_shut.group(1))          # 闭眼件开始淡入的闭合度（现在是 0.55）
    hi = 0.90                            # 再往上睁眼件只剩 <0.25 不透明度，叠影看不出来
    rig_path = os.path.join(root, "characters", "xiaoxun", "forms", "teen", "rig.json")
    if not os.path.isfile(rig_path):
        return
    rig = jsonc(rig_path)
    bad = []
    for a in rig.get("actions", []):
        h = a.get("blink_hold")
        if h is None:
            continue
        long_lived = bool(a.get("loop")) or float(a.get("duration") or 0) >= 0.8
        if long_lived and lo < float(h) < hi:
            bad.append(f"{a['id']} blink_hold={h}"
                       + ("（loop）" if a.get("loop") else f"（{a.get('duration')}s）"))
    check("长动作的 blink_hold 都避开幽灵区", not bad,
          f"幽灵区 {lo}~{hi}；越界：{bad}" if bad
          else f"幽灵区 {lo}~{hi}，已检查 "
               f"{sum(1 for a in rig.get('actions', []) if a.get('blink_hold') is not None)} 个带 blink_hold 的动作")

    # 眯眼笑要有笑眼件兜底：按到 0.9 以上又没有笑眼通道 = 纯闭眼（睡觉那种），也允许，
    # 但"被摸/开心"这类既按高又该笑的动作，笑眼通道丢了就会变成面无表情地闭眼。
    #
    # ⚠ 2026-10-15 这条闸的前提被推翻过一次，改口径时连同理由一起记在这里：
    #   旧口径要求这些动作「两条 Smile 通道 + blink_hold ≥ 0.9」。但 blink_hold 是
    #   **阶跃**生效的（动作第 0 帧闭合度直接跳到 0.95），而 Smile 是 pulse（0.3s
    #   才爬满、收尾又先退场），两条曲线根本不同步 —— 动作开头 0.3 秒和结尾 0.15 秒
    #   各露出一段「眼睛闭着但没在笑」的谷型 ∪，用户 2026-10-15 验收就是报的这个。
    #   新口径：有笑眼通道就**不许**再写 blink_hold，闭合度交给引擎的
    #   blink = max(blink, smile) 自己跟（官方 Haru F05 也是两者同一条淡入）。
    #   运行时那一面由 test_core 的「笑眼动作时序」守（逐帧扫，闭眼必须在笑）。
    want_smile = ("stroke", "happy", "head_pat")
    missing = []
    for a in rig.get("actions", []):
        if a["id"] not in want_smile:
            continue
        chans = [c for c in a.get("channels", []) if "Smile" in str(c.get("target", ""))]
        if len(chans) < 2:
            missing.append(f"{a['id']}(笑眼通道只有{len(chans)}条)")
        elif a.get("blink_hold") is not None:
            missing.append(f"{a['id']}(有笑眼通道却还写了 blink_hold={a.get('blink_hold')}，"
                           f"两条曲线不同步会露出 ∪ 窗口)")
    check("被摸/开心类动作用的是山型笑眼", not missing,
          f"缺：{missing}" if missing
          else "stroke/happy/head_pat 都是两条 Smile 通道且不再写 blink_hold")

    # 上眼线延迟下滑（lash_hold）：半闭时睫毛压进虹膜会出现黑钩、瞳孔被吃掉。
    check("引擎支持 lash_hold（上眼线延迟下滑）", "lash_hold" in src,
          "zrig.c 里有 lash_hold 的解析与曲线" if "lash_hold" in src else "引擎没有这个字段")
    lashes = [p for p in rig.get("parts", []) if p.get("eyelid_travel")]
    weak = [f"{p['id']} lash_hold={p.get('lash_hold')}" for p in lashes
            if float(p.get("lash_hold") or 0) < 0.4]
    check("上眼线都设了 lash_hold≥0.4", lashes and not weak,
          f"{len(lashes)} 条上眼线" + (f"，不达标：{weak}" if weak else "，都是后半程才滑"))


def check_neck_seam(root):
    """跟随件和它所跟随的形变之间不许有相对滑移（2026-10-14 加，同日补方向）。

    躯干贴图的顶边其实是脖子和衣领，而 bend_x 用的 root 曲线 f(t)=(1-t)^2
    恰好在顶边给出满额形变；头则按颈关节那一行做刚性平移，只拿到 0.854 倍。
    于是衣领比它上面的头、下面的胸都移动得多 —— 用户实测反馈
    "颈部会横向整体错误细微的位移，包括兜帽"。

    关键是**方向**：出问题的永远是取样线"另一侧"那块本该归跟随件管、
    却还在跟着源自己的曲线动的贴图。而哪一侧是"另一侧"由曲线说了算：

      · root 曲线（顶端满额）→ 跟随件挂在上面（头/手臂跟躯干）。
        取样线**以上**的源贴图（脖子、衣领）要被按住 → 必须写
        bend_hold_above，让那几行共用取样线处的形变量。
      · tip 曲线（底端满额）→ 跟随件挂在下面（脚跟腿）。
        取样线**以下**的源贴图要归跟随件 —— 这回不是按住，而是**切掉**：
        make_foot_parts.py 把 seg_leg_* 在切线以下擦干净，那块像素改由
        鞋部件自己画。所以这种情况不该有 bend_hold_above，
        而要求切线和取样线是同一条（差一行，腿脚之间就错一行）。
        像素层面"真的擦干净了"由 check_assets.py 的「腿件切线以下已清空」把关。

    （2026-10-15 起引擎有 bend_hold_below 了（G97 补上的，下平台，与 bend_hold_above
      互为镜像）。现有的腿件仍然走"切掉"这条路 —— 既然已经切干净了就别回头改，
      多一条平台线就多一处要对齐的参数。新增第三种跟随关系时两条路都可以走。）
    """
    section("跟随件不相对滑移（脖子/脚踝）")
    base = os.path.join(root, "characters", "xiaoxun", "forms", "teen")
    rig_path = os.path.join(base, "rig.json")
    if not os.path.isfile(rig_path):
        return
    with io.open(rig_path, encoding="utf-8") as fh:
        rig = json.load(fh)
    parts = {p["id"]: p for p in rig.get("parts", [])}
    # 已登记的"切掉"：源部件 → 切线（画布坐标；源图 → 画布要 +68）
    cuts = {}
    foot_path = os.path.join(base, "sprites", "foot_parts.json")
    if os.path.isfile(foot_path):
        with io.open(foot_path, encoding="utf-8") as fh:
            fj = json.load(fh)
        cy = int(fj.get("cut", {}).get("leg_cut_y", 0)) + 68
        cuts["seg_leg_l"] = cuts["seg_leg_r"] = cy
    # 每个源部件被哪些 bend 曲线驱动（取 |scale| 最大的那条定性）
    drv = {}
    for prm in rig.get("params", []):
        for b in prm.get("binds", []):
            if "bend" in str(b.get("param", "")) and b.get("part"):
                d = drv.setdefault(b["part"], {})
                c = str(b.get("curve", "root"))
                d[c] = max(d.get(c, 0.0), abs(float(b.get("scale", 0) or 0)))
    pairs = [(gn, g) for gn, g in rig.get("groups", {}).items() if g.get("bend_follow")]
    check("找得到跟随形变的组", bool(pairs), "一个都没有？")
    seen = set()
    for gname, g in sorted(pairs):
        src = g["bend_follow"]
        yat = g.get("bend_follow_at")
        p = parts.get(src)
        if not check("%s 跟随的 %s 真的存在" % (gname, src), p is not None):
            continue
        curves = drv.get(src, {})
        if not check("%s 真的被 bend 驱动（否则跟随没意义）" % src, bool(curves)):
            continue
        top = int(p.get("pos", [0, 0])[1])
        main = max(curves.items(), key=lambda kv: kv[1])[0]
        if main == "tip":
            # 跟随件在下面：取样线以下的源贴图必须已经切掉，交给跟随件画
            cut = cuts.get(src)
            check("%s 在取样线以下已登记切掉（而不是靠形变平台）" % src, cut is not None,
                  "tip 曲线底端满额，取样线以下的贴图会比刚性跟随的脚多动 "
                  "—— 要么切掉，要么写 bend_hold_below（引擎已支持），不能就这么放着")
            if cut is not None:
                check("%s 的切线和 %s 的取样线对齐（%s vs %s）" % (src, gname, cut, yat),
                      abs(float(cut) - float(yat)) <= 1.0,
                      "差一行，腿和鞋就错一行")
            check("%s 不该写 bend_hold_above（那会把整条腿按死，连摆都摆不动）" % src,
                  p.get("bend_hold_above") is None,
                  "bend_hold_above=%s" % p.get("bend_hold_above"))
            # 切线和下平台是两条**互斥**的路：都写上等于按两次，
            # 而且切线挪了平台线不会跟着挪，迟早对不齐。
            check("%s 不要既切掉又写 bend_hold_below" % src,
                  not (cut is not None and p.get("bend_hold_below")),
                  "切线 %s + 下平台 %s —— 二选一" % (cut, p.get("bend_hold_below")))
            continue
        # 跟随件在上面：取样线以上的源贴图（脖子/衣领）必须被平台按住
        if src in seen:
            continue
        seen.add(src)
        hold = p.get("bend_hold_above")
        if not check("%s 写了形变平台 bend_hold_above" % src, bool(hold),
                     "没写 → 衣领会比头多动，脖子横向滑移"):
            continue
        check("%s 的平台线落在部件范围内" % src, hold > top,
              "平台 y=%s 顶边 y=%s" % (hold, top))


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

    # 决策流水（G99）：三条阈值全是抄来的，要用自己的数据重标 —— 前提是先存下来。
    # 内存计数器一重启就清零，所以这一组守的是"真的落盘了"。
    mh = code_of("src/headless/main_headless.c")
    check("路由决策落盘已接线", "zgw_set_usage_log" in mh and "data/usage.jsonl" in mh,
          "src/headless/main_headless.c —— 不接线的话 usage.jsonl 永远是空的")
    check("没候选的决策也记流水", "ZGW_R_NO_CANDIDATE" in gw_c,
          "只记成功的那些会把分母做小，本地占比虚高")
    check("流水文件会自己滚", "2L * 1024L * 1024L" in gw_c and "rename(" in gw_c,
          "src/core/zgateway.c:usage_append —— 不滚的话跑一年会涨到几百兆")
    check("重标工具在", os.path.exists(os.path.join(root, "tools/usage_report.py")),
          "tools/usage_report.py：按真实流水反算阈值该设多少")
    check("data/ 不入库", "data/" in open(os.path.join(root, ".gitignore"),
                                           encoding="utf-8").read(),
          ".gitignore —— 流水是本机运行数据，带用户的 token 规模，不进仓库")

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
               check_decisions, check_acceptance,
               check_json, check_rig, check_engine_caps, check_render_parallel, check_torso_inertia,
               check_tiptoe_grounded, check_foot_switch, check_feet_on_ground,
               check_head_body_link,
               check_neck_seam,
               check_eye_hold_zone,
               check_action_dead_time,
               check_motion_measure,
               check_form_roadmap,
               check_live2d, check_character,
               check_web, check_contract, check_tools, check_hygiene):
        try:
            fn(root)
        except Exception as e:                            # noqa: BLE001
            check(f"{fn.__name__} 本身出错", False, repr(e))
    print(f"\n合计 {_n} 项，{_fail} 项不通过 → " + ("全部通过" if not _fail else "有问题，别交付"))
    # 分栏报，别让"文档齐不齐"把"软件对不对"稀释掉
    print(f"  · 工程事实 {_kind_n['eng']} 项，{_kind_fail['eng']} 项不通过"
          f"（这一栏红了 = 软件坏了，必须拦住交付）")
    print(f"  · 文档纪律 {_kind_n['doc']} 项，{_kind_fail['doc']} 项不通过"
          f"（这一栏红了 = 记账没跟上，当轮补齐）")
    sys.exit(1 if _fail else 0)


if __name__ == "__main__":
    main()
