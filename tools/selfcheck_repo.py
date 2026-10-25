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
import argparse, ast, datetime, glob, io, json, math, os, re, struct, subprocess, sys

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
    # 取代者可能已经被归档 —— 归档不是删除，归档表也是登记表的一部分。
    # 2026-10-15 踩过：DC05/DC06 外部零引用就被归档了，结果主表里 DC01~DC04 四条
    # 🔁 全是「由 DC05 取代」，闸当场红。挑归档条目时**必须连"被谁引为取代者"一起看**。
    arch_p = os.path.join(root, "docs/memory/DECISIONS_ARCHIVE.md")
    arch_ids = set()
    if os.path.exists(arch_p):
        arch_ids = set(re.findall(r"^###\s*(DC\d+)\s",
                                  io.open(arch_p, encoding="utf-8").read(), re.M))
    missing = sorted(refs - set(ids) - arch_ids)
    check("「由 DC## 取代」指向的条目都存在", not missing,
          "找不到：%s（主表和归档表里都没有）" % missing)
    # 被引为"取代者"的条目如果在归档表，主表必须留指路牌，否则读的人找不到
    moved_refs = sorted(refs & arch_ids)
    check("被引为取代者的条目若已归档，主表要指得到",
          (not moved_refs) or ("DECISIONS_ARCHIVE.md" in txt),
          "%s 已归档，主表必须写明去哪找" % moved_refs if moved_refs
          else "没有取代者被归档")
    check("登记表里留着被推翻的反面教材", 
          len([b for b in blocks if b.startswith("DC0") and "🔁" in b.splitlines()[0]]) >= 4,
          "被推翻的中间结论也要留着（用户 2026-10-14 的要求）")
    # 反膨胀：表太长就没人读了，该归档的归档（校准时加的上限）
    check("登记表没有膨胀到没人读（≤ 40 条）", len(ids) <= 40,
          "%d 条 —— 超了就把已推翻且无人引用的移进归档段" % len(ids))

    # 归档不是删除：搬走的条目必须真的落在归档文件里，而且格式一样。
    # 2026-10-15 第一次归档（DC07~DC11）时加的闸 —— 没有它的话，"超了就归档"
    # 这句话很容易变成"超了就删掉"，而用户要求的是**被推翻的中间结论也要留着**。
    # 另外两类条目永远不许归档：用户硬约束（DC12~DC16）和四条 🔁 反面教材（DC01~DC04）。
    ap = os.path.join(root, "docs", "memory", "DECISIONS_ARCHIVE.md")
    if os.path.exists(ap):
        with io.open(ap, encoding="utf-8") as fh:
            atxt = fh.read()
        atxt = re.sub(r"(?s)```.*?```", "", atxt)
        ablocks = re.split(r"(?m)^### ", atxt)[1:]
        aids, amiss = [], []
        for b in ablocks:
            m = re.match(r"(DC\d+)\s*(\S+)", b.splitlines()[0].strip())
            if not m:
                continue
            aids.append(m.group(1))
            body = b.split("\n### ")[0]
            for field in ("前提", "证据", "负控", "复查触发"):
                mm = re.search(r"(?m)^-\s*%s[：:]\s*(.+)$" % field, body)
                if not (mm and len(mm.group(1).strip()) >= 6):
                    amiss.append("%s 缺%s" % (m.group(1), field))
        check("归档条目的四栏也齐全（归档≠降格）", not amiss,
              "；".join(amiss[:5]) if amiss else "%d 条 × 4 栏全齐" % len(aids))
        check("归档与主表没有重号", not (set(aids) & set(ids)),
              "两边都有：%s" % sorted(set(aids) & set(ids))[:3])
        NEVER = {"DC01", "DC02", "DC03", "DC04",      # 🔁 反面教材，用户要求留着
                 "DC12", "DC13", "DC14", "DC15", "DC16"}  # 用户硬约束
        leaked = sorted(NEVER & set(aids))
        check("硬约束与反面教材没被归档走", not leaked, "被归档了：%s" % leaked)
        # 主表里要有指路牌，不然归档等于失踪
        check("主表写明了归档去向", "DECISIONS_ARCHIVE.md" in txt,
              "主表里要留一句「DC## 已移到 DECISIONS_ARCHIVE.md」")


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

        # ---- 上下文管理器（T60.1 / T61.11）的红线 ----
    # 这几条守的是隐私，不是风格。
    ctxc = read(os.path.join(root, "src/core/zctx.c"))
    if ctxc:
        check("zctx 要按目的地挡下敏感轮次（不许跟着上云）",
              "t->sensitive && !local" in ctxc,
              "zctx_build 里要有按 local 过滤 sensitive 的分支")
        check("取历史时也要独立再挡一次（两道防线）",
              "t->sensitive && !c->last_local" in ctxc,
              "kept_turn_index 里要有独立的过滤")
        check("被裁掉的块不许无声消失（要写原因）", "drop_reason" in ctxc)
        check("清单要报告被挡下的轮数", "没上云" in ctxc)
    mh = read(os.path.join(root, "src/headless/main_headless.c"))
    if mh:
        # 2026-10-24 实测：模型想 6 秒，整个预览卡死 6 秒、立绘变雕塑。
        # 两层都修了，两层都要盯住。
        check("慢请求不许攥着渲染用的那把锁",
              "AILOCK" in mh and "g_ai_lock" in mh,
              "网关/上下文要用 g_ai_lock，别和 g_lock 混用")
        check("慢端点要交给工作线程（否则 zpet_tick 被一起拖住）",
              "dispatch_slow" in mh)
        check("回复可能引用敏感内容，要跟着算敏感（污染传播）",
              "tainted" in mh)

    # 动作要有给人看的名字，而且得真是中文 —— 不是把 id 抄一遍。
        # 2026-10-24 用户截图里 nod / wave_both / kirara_jump 等 8 个按钮露了英文 id，
        # 根因是名字写在界面的硬编码表里、漏了新动作。名字搬到 rig.json 之后，
        # 这条盯住"数据层有没有漏"，正式软件 UI 重做时也不用重写一遍文案。
        # 名字加在 tools/make_rig.py 的 ACTION_TITLES 里。
        noname = [a.get("id") for a in r.get("actions", [])
                  if not a.get("title") or a.get("title") == a.get("id")
                  or all(ord(ch) < 128 for ch in str(a.get("title", "")))]
        check("每个动作都有中文名（露英文 id 的界面是半成品）", not noname,
              f"{tag}：{len(r.get('actions', []))} 个动作" + (f"，没名字的 {noname}" if noname else ""))

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
        # 纯变换节点（第六十三问 P0 的旋转骨）本来就没有 part：它靠 parent 串在链上、
        # 由部件的 "deformer" 点名。只有**带网格**（cols/rows/points）的节点才必须挂部件。
        # 2026-10-25（S2 骨链接线）第一次跑红就是这条口径没跟上引擎的新节点类型。
        badd = [f["id"] for f in dfs
                if (f.get("part") is not None or f.get("points") or f.get("cols"))
                and f.get("part") not in pids]
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
        # 特效件（fx_*）画在人物剪影**外面**的空气里，底下根本没有像素可乘可加。
        # zimg.c:76 的 ADD/MULTIPLY 分支写死 `oa = da`（不改目标 alpha），
        # 所以这种件用加算 = 一个像素都画不出来。2026-10-16 真机踩过：
        # 8 颗 ✨ 全写成 blend:"add"，渲染出来一颗都没有，而下面那条
        # 「层号不能最底」完全拦不住（✨ 在 300~307，是最顶层）。
        fxbad = [p["id"] for p in r["parts"]
                 if p["id"].startswith("fx_") and p.get("blend") in ("add", "multiply")]
        badblend += [f"{i}=特效件不能加算" for i in fxbad]

        # 表情是**状态**（挂上去就一直生效），不许把眼睛开合钉死：
        # set 之后眨眼驱动再也推不动它，角色会一眼不眨地瞪着人。2026-10-16 真机发现
        # 六个表情全中（smile/shy/angry/sad/surprise/sleepy），挂上任一个
        # /api/blink?v=1 就失灵。「眯一点」请用 multiply（乘 0.85，眨眼仍能压到 0），
        # 「睁大眼」请放进动作（动作有时长，会自己结束）。
        eye_pin = [f"{ex['id']}.{q['id']}" for ex in r.get("expressions", [])
                   for q in ex.get("params", [])
                   if q.get("id") in ("ParamEyeOpen", "ParamEyeLOpen", "ParamEyeROpen")
                   and q.get("mode") in ("set", "overwrite")]
        check("表情不许把眼睛开合钉死（否则永远不眨眼）", not eye_pin,
              f"{eye_pin} —— 表情是状态，set 上去眨眼就被压住了；眯眼用 multiply"
              if eye_pin else
              f"{len(r.get('expressions', []))} 个表情，眼开合都没被 set 钉住")

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
            # default 可以是 "none" = 一上来整组都不显示（T46.3 发型组：短发那一档
            # 恰恰是\"一束都不加\"）。引擎侧 zrig.c load_poses 认这个值并置 cur=-1，
            # 两边必须同时认 —— 下面那条闸就是盯着\"两边同时认\"的。
            if (g.get("default") and g["default"] != "none"
                    and g["default"] not in eids):
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
    "ParamSkirtSway": "裙摆自主摆动（T45.9）。标准表只有身体角度，没有"
                      "「布自己在动」这一层。两级形变器：裙身 skirt_sway_x + "
                      "下摆 skirt_hem_x，下摆带 0.11 秒行波延迟",
    # ★ ParamHairLong（T46.2 的长发开关）已于 T46.3 退场：发型的显隐改由互斥组
    #   hairstyle（none/long/twin/pony）统管。两套开关并存时「长发+双马尾同时开」
    #   是个合法状态，画面上就是三坨头发打架。双马尾/马尾的摆动形变器直接由物理
    #   2.0 的摆链驱动（twin_l2 / twin_r2 / pony2），**不再新增参数** ——
    #   所以这张表里没有 ParamHairTwin*/ParamHairPony*，是对的，不是漏登记。
    "ParamHairSway": "头发自主飘动（第四十七问 / T46.56）。和 ParamSkirtSway "
                     "完全同类：短发四件（刘海/左右侧发/后发）的物理只有 "
                     "driver: head 一个输入，而本引擎物理输出的是滞后量 "
                     "pos−target ⇒ 待机时头不动 = 头发是死的（实测发团质心 "
                     "3 秒只晃 2.94px，还全是头自己动带出来的）。一条参数推四件，"
                     "每件带不同的行波延迟（0 / .04 / .09 / .13 秒），"
                     "发梢那级再慢半拍；挂件发型的摆链（long/twin/pony）也混进"
                     "同一股风。ambient drift 0.19Hz —— 比尾巴 0.21 慢、比裙摆 "
                     "0.13 快，教程口径「軽いものほど揺れやすく、早く収まる」",
    "ParamHairBackS": "后发第二段·发梢甩动（T46.1）。标准表只有 ParamHairBack 一条，"
                      "但教程一致认为「揺れが1段しかない＝髪が棒のように見える」，"
                      "後ろ髪は2~3段が普通。和 ParamHairAhogeS/ParamHairSideS 同族",
    "ParamJacketSway": "外套前襟下摆自主摆动（T45.12）。和 ParamSkirtSway 同类，"
                       "但幅度小、频率低、延迟大 —— 教程口径「上着は少し重い素材"
                       "なのであまり揺らさない」。形变器 jacket_hem_x 只推前襟两片的列",
    "ParamForeLongR": "右前臂折肘时沿轴加长（第四十八问 / T46.59）。和 "
                      "ParamForeSlimR 同族：一个管粗细、一个管长短。原画是一条"
                      "垂着的胳膊，肘的切点由原画决定，前/上臂 = 0.71，而参考图 "
                      "wave_up.png 是 0.87 ⇒ 折起来就是「吊在袖口下的拳套」。"
                      "折肘时沿肘→腕轴线拉长 26px（116→142 = 0.87），"
                      "hand_? 组 dx/dy 同步外移；静止时为 0，画面一个像素不动",
    "ParamForeLongL": "同上，左前臂",
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
    # ---- Q36 手差分（官方口径：手の差分は**パーツ切替**，不是把手掰开）----
    "ParamHandLOpen": "左手·张开差分（0=放松 1=摊掌）。绑两条 alpha：张开件 +1、"
                      "放松件 −1，所以同一时刻只有一张不透明。"
                      "官方《腕と手のモーション》：腕/手の差分は VISIBLE で切替",
    "ParamHandROpen": "同上，右手",
    "ParamHandLHeart": "左手·比心差分（指尖围出心形的负空间）。同样是切贴图，"
                       "靠旋转掰不出手指造型",
    "ParamHandRHeart": "同上，右手",
    # ---- Q36 腿脚真关节（标准表只到 ParamLegL/R 的整条弯）----
    "ParamHipL": "左髋绕骨盆旋转（真关节，不是 bend）。有了它腿才能像手臂一样抬起来",
    "ParamHipR": "同上，右髋",
    "ParamAnkleL": "左踝跖屈/背屈（绷脚尖 / 勾脚）。跳跃的蹬地和落地缓冲靠它",
    "ParamAnkleR": "同上，右踝",
    # ---- Q45 手臂姿势（第四十五问：挥手被判「袖口下吊着一只大拳套」）----
    "ParamShoulderRY": "右肩单侧上提。标准表的 ParamShoulderY 是**双肩共用**"
                       "（binds 里 arm_l/arm_r/chest 各一条）且量程只够 ±8px，"
                       "而举手打招呼抬的是举手那一侧、幅度 26px。"
                       "真人抬手时同侧肩本来就上提（waterarena 挥手作画口径）",
    "ParamShoulderLY": "同上，左肩",
    "ParamForeSlimR": "右前臂『折肘时收窄』（网格形变器 arm_r_fore_slim）。"
                      "这张原画的袖子是 1.55:1 的胖筒，肘一折前臂就整条压在上臂上"
                      "糊成一坨；沿肘→腕轴线横向收窄 15%（肘端 0%、袖口 6%）"
                      "就能把两根管子分开。0 = 原件，静止画面零改动",
    "ParamForeSlimL": "同上，左前臂",
    "ParamStarEye": "星星眼总闸（常态虹膜淡出↔星形虹膜淡入 + 放行画面上的 ✨）",
    "ParamMouthX": "嘴左右（单边嘴角）。不是 Live2D 标准表的名字，是 Animaze《复杂口角"
                   "形状的模型制作方法》扩展表里的 ID，口径=嘴整体左右偏 + 顺带抬起那侧嘴角。"
                   "不能用 ParamMouthForm 代替：Form 被口型同步占着（T44.1 第 ⑦ 条）",
    "ParamAccTailCat": "猫尾挂件开关（0=摘 1=戴）。A49 挂件插槽系统的第一件；走 DC59 差分件口径 min0/max1，绑 alpha 而不是把部件删掉",
    "ParamAccTailSwing": "猫尾自主摆动。本引擎物理输出的是滞后量不是摆角（zrig.c:3013），慢输入推不出位移，所以「自己动」要靠动作通道驱动这条参数",
    **{f"ParamAccTail{k}Swing": "猫尾摆动（%s 姿态）。四种姿态是互斥差分件，各有各的摆动参数 —— 放松是慢而大，兴奋是快而小，炸毛是僵直发抖，夹紧几乎不动（恐惧的冻结）。值域不是 ±1 而是按 mood_swing 的最大幅度倍率撑开的，否则放大那一侧会被 clamp 削平" % k
       for k in ("Relaxed", "Up", "Puff", "Tuck")},
    **{f"ParamAccEar{k}": "猫耳挂件开关（%s）。0=摘 1=戴" % k for k in ("L", "R")},
    **{f"ParamEar{k}Angle": "猫耳角度（%s）−1 飞机耳 / +1 竖起前倾。官方/社区做法是**一条连续参数**不是差分件（「耳揺れ」−30~30，「−30で耳が下がる、30ではピンと張る」）" % k
       for k in ("L", "R")},
    **{f"ParamSparkle{i}": "第 %d 颗 ✨ 的生命周期（scale+alpha 合一，一颗一个参数）" % i
       for i in range(1, 9)},
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
    # 2026-10-25（第六十三问 P0）：补上 groups / actions / deformers ——
    # 用户要的是"一角色四形态 × 多套服装 × 多配件"，这三样都会成倍长，
    # 而它们撞上限的表现是 zrig_load 失败（新口径）或静默丢件（旧口径）。
    caps = [("ZRIG_MAX_PHYS", "physics"), ("ZRIG_MAX_PARAMS", "params"),
            ("ZRIG_MAX_PARTS", "parts"), ("ZRIG_MAX_XFADE", "xfades"),
            ("ZRIG_MAX_GROUPS", "groups"), ("ZRIG_MAX_ACTIONS", "actions"),
            ("ZRIG_MAX_DEFORMS", "deformers"), ("ZRIG_MAX_CHANNELS", None)]
    hsrc = ""
    hpath = os.path.join(root, "src", "core", "zrig.h")
    if os.path.isfile(hpath):
        with io.open(hpath, encoding="utf-8") as fh:
            hsrc = fh.read()

    def cap_of(macro):
        """取一个上限宏的数值；允许一层层别名（zrig.c 的 ZRIG_MAX_ACTIONS →
        zrig.h 的 ZRIG_ACTION_CAP）。别名链断掉或成环都返回 None。"""
        seen = set()
        cur = macro
        for _ in range(8):
            if cur in seen:
                return None
            seen.add(cur)
            m = None
            for text in (csrc, hsrc):
                m = re.search(r"#define\s+%s\s+(\w+)\b" % re.escape(cur), text)
                if m:
                    break
            if not m:
                return None
            v = m.group(1)
            if v.isdigit():
                return int(v)
            cur = v
        return None

    for macro, key in caps:
        cap = cap_of(macro)
        if not check("zrig.c 里找得到 %s" % macro, cap is not None,
                     "解析不到数值（别名链断了？）" if cap is None else ""):
            continue
        if key is None:
            # 通道数嵌在每个动作里：只看**最多那个动作**（每条动作各自过 loader）
            used = max([len(a.get("channels", [])) for a in rig.get("actions", [])] or [0])
            check("%s 没超（最多的动作用了 %d / 上限 %d）" % (macro, used, cap), used <= cap)
            continue
        used = len(rig.get(key, []))
        check("%s 没超（%s 用了 %d / 上限 %d）" % (macro, key, used, cap), used <= cap,
              "超出的会被静默丢掉 —— back_x 就这么哑了很久")
        check("%s 还有余量（用量不超过上限的 85%%）" % macro, used <= cap * 0.85,
              "用了 %d / %d = %.0f%%，快顶满了，加东西之前先把上限调大"
              % (used, cap, used * 100.0 / cap))
    # ZRIG_MAX_BINDS 不是顶层键（绑定嵌在每个 param 里），上面那个循环覆盖不到。
    # 2026-10-16 补：绑定数涨得比参数数快得多 —— 一个 ParamStarEye 就带 12 条，
    # 真顶满了照样是静默截断/硬报错，没理由只守三个不守它。
    m = re.search(r"#define\s+ZRIG_MAX_BINDS\s+(\d+)", csrc)
    if check("zrig.c 里找得到 ZRIG_MAX_BINDS", m is not None):
        cap = int(m.group(1))
        used = sum(len(q.get("binds", [])) for q in rig.get("params", []))
        check("ZRIG_MAX_BINDS 没超（binds 用了 %d / 上限 %d）" % (used, cap), used <= cap)
        check("ZRIG_MAX_BINDS 还有余量（用量不超过上限的 85%)", used <= cap * 0.85,
              "用了 %d / %d = %.0f%%" % (used, cap, used * 100.0 / cap))

    # ⑰ 变形器树 / keyform / 「撞上限必须报错」——第六十三问 P0 的四根柱子。
    #    这几样都是"错了不报错、只是画面悄悄不对"的高危区，所以从源码这头钉住。
    for needle, label in [
        ("deform_chain_matrix", "部件 → warp → rotate → root 的链矩阵"),
        ("deform_local_matrix", "每个节点自己的 pivot / rot / sx / sy"),
        ("zimg_matrix_mul(acc, out, loc)", "父包住子的连乘顺序"),
        ("kf_w", "keyform 插值权重"),
        ("deform_vertex_at", "渲染与探针共用同一个逐顶点求值"),
        ("zrig_deform_mesh", "逐顶点位移的读取接口"),
    ]:
        check("引擎里有%s" % label, needle in csrc,
              "找到了" if needle in csrc else "第六十三问 P0 的元件被删了")
    check("组/部件/动作撞上限都报错而不是静默截断",
          all(k in csrc for k in ("组数超过上限", "部件数超过上限", "动作数超过上限")),
          "三处都有" if all(k in csrc for k in ("组数超过上限", "部件数超过上限", "动作数超过上限"))
          else "又有 loader 退回 `i < n && n < MAX` 的静默丢件写法了")
    check("没有残留的静默截断循环",
          re.search(r"for \(i = 0; i < n && r->n\w+ < ZRIG_MAX", csrc) is None,
          "干净" if re.search(r"for \(i = 0; i < n && r->n\w+ < ZRIG_MAX", csrc) is None
          else "还有 loader 用循环条件静默丢弃超限条目")
    # 状态机与动作表的上限必须同步，否则"动作能装 96 条、第 33 条先炸"
    act_cap = cap_of("ZRIG_MAX_ACTIONS")
    zsm_h = os.path.join(root, "src", "core", "zsm.h")
    zsm_src = io.open(zsm_h, encoding="utf-8").read() if os.path.isfile(zsm_h) else ""
    m_zsm = re.search(r"#define\s+ZSM_MAX_STATES\s+(\d+)", zsm_src)
    if check("找得到 ZSM_MAX_STATES", m_zsm is not None, zsm_h):
        check("状态机容量不小于动作表上限",
              act_cap is not None and int(m_zsm.group(1)) >= act_cap,
              "ZSM %s / ACTIONS %s" % (m_zsm.group(1), act_cap if act_cap is not None else "?"))


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

    # ---- 动作幅度不许超出参数行程（超出的部分会被引擎 clamp 掉，而且一声不吭）----
    # Q36 实例：kirara_jump 的腾空关键帧写 −120px，换算成 ParamBaseY = 30，
    # 可那时候 ParamBaseY 的行程只有 ±10 —— 画面上只跳了 40px，声明却是 120px，
    # 两边都"自洽"，只有拿尺子量实拍帧才发现。这条闸就是替人去量。
    prange = {p["id"]: max(abs(float(p.get("min", 0))), abs(float(p.get("max", 0))))
              for p in rig.get("params", [])}
    over = []
    for act in rig.get("actions", []):
        for c in act.get("channels", []):
            tgt = str(c.get("target", ""))
            lim = prange.get(tgt)
            if lim is None:
                continue                      # 直接打部件的通道没有行程概念
            if c.get("keys"):
                peak = max((abs(float(v)) for _t, v in c["keys"]), default=0.0)
            else:
                peak = abs(float(c.get("amp", 0) or 0)) + abs(float(c.get("bias", 0) or 0))
            if peak > lim + 1e-6:
                over.append("%s/%s %.2f>%.2f" % (act.get("id"), tgt, peak, lim))
    check("动作幅度都在参数行程内（超出会被悄悄削平）", not over,
          "、".join(over[:6]) + ("…" if len(over) > 6 else ""))

    for act in rig.get("actions", []):
        worst = 0.0
        terms = []
        for c in act.get("channels", []):
            tgt = str(c.get("target", ""))
            # 关键帧通道没有 amp，幅度要从 keys 里取最大绝对值 —— 不补这一手，
            # 一条 "keys":[[0,0],[0.69,-120]] 的腾空通道在这里是**完全看不见**的，
            # 闸门会以为这个动作根本没动过脚（Q36 把 kirara_jump 改成关键帧时发现）。
            if c.get("keys"):
                amp = max((abs(float(v)) for _t, v in c["keys"]), default=0.0)
            else:
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
    lo = float(m_shut.group(1))          # 闭眼件开始淡入的闭合度（现在是 0.85）
    hi = 0.98                            # 过渡尾部：闭眼件已覆盖绝大部分，长时停留仍可能双线
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
    # ⑳ 内容包 / 模组契约（第六十四问：完全可自定义 + 完全可模组）。
    #    这一条盯的是"新增内容不改核心代码"这句话有没有真的被检查：
    #    包写错了（缺贴图、白底烤进去、group 指向不存在的组、forms.json 说能做却没目录）
    #    以前要等装载时才炸，或者干脆静默少几件。细目在 tools/mod_lint.py。
    # mod_lint 要 pillow（判"贴图是不是整张不透明"必须真解码像素）。
    # selfcheck 自己只依赖标准库，所以这里**找一个能 import PIL 的解释器**：
    # 依次试 $ZC_PY、当前解释器、~/.imgenv/bin/python（WORKFLOW 里的约定环境）。
    # 找不到就直说"缺环境"，不要伪装成"包写错了"。
    _pys = [os.environ.get("ZC_PY"), sys.executable,
            os.path.expanduser("~/.imgenv/bin/python")]
    _lint_py = None
    for _c in [x for x in _pys if x and os.path.exists(x)]:
        try:
            _ok = subprocess.run([_c, "-c", "import PIL"], capture_output=True).returncode == 0
        except OSError:
            _ok = False
        if _ok:
            _lint_py = _c
            break
    if _lint_py is None:
        check("找得到带 pillow 的 python（跑内容包契约闸）", False,
              "试过 %s；装法：python3 -m venv ~/.imgenv && "
              "~/.imgenv/bin/pip install pillow numpy" % [x for x in _pys if x])
    _rc = subprocess.run([_lint_py or sys.executable, os.path.join(root, "tools/mod_lint.py"),
                          "--root", root, "--all-characters", "--quiet"],
                         capture_output=True, text=True)
    check("内容包契约全部通过（tools/mod_lint.py --all-characters）", _rc.returncode == 0,
          (([ln for ln in _rc.stdout.strip().splitlines() if ln.strip()] or ["?"])[-1]))
    # 负控：闸本身要被打红过 14 次，否则它只是一堆永远通过的 print。
    _rc = subprocess.run([_lint_py or sys.executable, os.path.join(root, "tools/mod_lint.py"),
                          "--self-test"], capture_output=True, text=True)
    check("mod_lint 的负控全部符合预期（14 例坏包）", _rc.returncode == 0,
          (([ln for ln in _rc.stdout.strip().splitlines() if ln.strip()] or ["?"])[-1]))
    # 闸里写的上限必须与引擎宏一致 —— 两处各说各话的坑这一轮已经踩过一次
    # （ZRIG_MAX_ACTIONS 96 vs ZSM_MAX_STATES 32）。
    _lint = read(os.path.join(root, "tools", "mod_lint.py"))
    _zrigh = read(os.path.join(root, "src", "core", "zrig.h"))
    for _macro, _var in (("ZRIG_FORM_CAP", "FORM_CAP"), ("ZRIG_OUTFIT_CAP", "OUTFIT_CAP"),
                         ("ZRIG_ACTION_CAP", "ACTION_CAP")):
        _m1 = re.search(r"#define\s+%s\s+(\d+)" % _macro, _zrigh)
        _m2 = re.search(r"^%s\s*=\s*(\d+)" % _var, _lint, re.M)
        check("mod_lint 的 %s 与引擎 %s 一致" % (_var, _macro),
              bool(_m1) and bool(_m2) and _m1.group(1) == _m2.group(1),
              "%s vs %s" % (_m2.group(1) if _m2 else "?", _m1.group(1) if _m1 else "?"))

    # ㉑ 骨架契约（第六十五问）：四形态共用同一套骨名，是"换形态/换衣服/换 AI 角色"的前提。
    #    纯标准库，所以直接跑。负控 13 例必须全红 —— 否则它只是一堆永远通过的 print。
    _rc = subprocess.run([sys.executable, os.path.join(root, "tools/check_skeleton.py"),
                          "--root", root, "--quiet"], capture_output=True, text=True)
    check("骨架契约成立（tools/check_skeleton.py）", _rc.returncode == 0,
          (([ln for ln in _rc.stdout.strip().splitlines() if ln.strip()] or ["?"])[-1]))
    _rc = subprocess.run([sys.executable, os.path.join(root, "tools/check_skeleton.py"),
                          "--self-test"], capture_output=True, text=True)
    check("骨架闸的负控全部符合预期（14 例坏骨架）", _rc.returncode == 0,
          (([ln for ln in _rc.stdout.strip().splitlines() if ln.strip()] or ["?"])[-1]))

    # ⑲ 挂件表的形态可移植性（T2.2.0）：角色级挂件表一旦写死画布绝对像素，
    #    就只对量它的那个形态成立。实测过账：照少女 teen 量的 7 个挂件套到
    #    chibi（1:2.5）上平均偏 92 画布像素，而画布总高才 1360。
    #    细目在 tools/check_form_portable.py，那里拿四种头身比各算一遍。
    for _cd in sorted(glob.glob(os.path.join(root, "characters/*/design/attachments.json"))):
        _c = _cd.split(os.sep)[-3]
        _rc = subprocess.run([sys.executable,
                              os.path.join(root, "tools/check_form_portable.py"),
                              "--root", root, "--character", _c],
                             capture_output=True, text=True)
        check("挂件表对四个形态都可移植（%s）" % _c, _rc.returncode == 0,
              (_rc.stdout.strip().splitlines() or ["?"])[-1])
    # ⑳ 猫耳朝向（T45.3，用户第五次打回才定位到的错）：左右两张贴图装反时，
    #    渲染出来是「耳尖对着中间、耳廓躲在内侧」—— 位置、大小、动画全都是对的，
    #    任何现有闸门都发现不了，人眼也容易误读成「角度不对」。
    #    判据（三家日文教程 + 真猫正面照 + 二次元参考图互相印证，见 REFERENCE_NOTES 第三十七批）：
    #      正面视角下 **耳尖朝外倒**、**耳廓（暖色内耳）落在耳宽的外侧半边**。
    #    细目在 tools/qa_ear_orient.py（故意只用标准库，闸门才跑得起来）。
    for _cd in sorted(glob.glob(os.path.join(root, "characters/*/design/attachments.json"))):
        _c = _cd.split(os.sep)[-3]
        for _fd in sorted(glob.glob(os.path.join(root, "characters", _c, "forms/*/sprites"))):
            _f = _fd.split(os.sep)[-2]
            _rc = subprocess.run([sys.executable,
                                  os.path.join(root, "tools/qa_ear_orient.py"),
                                  "--root", root, "--character", _c, "--form", _f],
                                 capture_output=True, text=True)
            if "没有找到带 ear 标签的挂件" in _rc.stdout:
                continue
            _bad = [l.strip() for l in _rc.stdout.splitlines() if "不通过" in l]
            check("猫耳朝向：耳尖朝外 + 耳廓在外侧（%s/%s）" % (_c, _f),
                  _rc.returncode == 0 and not _bad,
                  "; ".join(_bad) if _bad else (_rc.stderr.strip().splitlines() or ["两只耳朵都对"])[-1])
    # ㉑ 裙子里布（T45.11）：Cubism 官方教程的原话是「スカートなどは**手前の面と奥の面で
    #    足を挟むように**画像を分けておく」—— 里布要夹在腿**后面**，表布在腿前面。
    #    层号一旦被挪到腿前面，静止时就会糊在大腿上，而所有现有闸门都看不出来
    #    （部件在、形变器在、参数也动）。另外里布必须跟表布同一条参数驱动且带延迟，
    #    否则它会和表布齐步走，甩出去时根本露不出里子，等于白做。
    for _sp in sorted(glob.glob(os.path.join(root, "characters/*/forms/*/sprites/skirt_parts.json"))):
        _form_dir = os.path.dirname(os.path.dirname(_sp))
        _tag = "%s/%s" % (_form_dir.split(os.sep)[-3], os.path.basename(_form_dir))
        with io.open(_sp, encoding="utf-8") as _f:
            _sk = json.load(_f)
        _lin_ids = [x["id"] for x in _sk.get("parts", [])]
        _rp = os.path.join(_form_dir, "rig.json")
        if not os.path.exists(_rp):
            continue
        with io.open(_rp, encoding="utf-8") as _f:
            _rig = json.load(_f)
        _by_id = {x["id"]: x for x in _rig.get("parts", [])}
        for _lid in _lin_ids:
            _part = _by_id.get(_lid)
            check("裙子里布 %s 进了 rig（%s）" % (_lid, _tag), _part is not None,
                  "rig.json 里没有这个部件 —— 生成器没接上" if _part is None else "layer %s" % _part.get("layer"))
            if not _part:
                continue
            # 腿、脚、表布都得在里布**前面**（层号更大）
            _front = [x for x in _rig["parts"]
                      if (x["id"].startswith("seg_leg") or x["id"].startswith("seg_foot")
                          or x["id"] == "seg_torso")]
            _bad = [x["id"] for x in _front if int(x.get("layer", 0)) <= int(_part.get("layer", 0))]
            check("裙子里布夹在腿后面（%s）" % _tag, not _bad,
                  "这些部件没排在里布前面：%s" % _bad if _bad
                  else "里布 layer %d < 腿/脚/表布" % int(_part.get("layer", 0)))
            # 和表布同一条参数驱动，而且要带延迟（齐步走就露不出里子）
            _defs = [d["id"] for d in _rig.get("deformers", []) if d.get("part") == _lid]
            _drv = []
            for _pm in _rig.get("params", []):
                for _b in _pm.get("binds", []) or []:
                    if _b.get("deformer") in _defs:
                        _drv.append((_pm["id"], float(_b.get("lag", 0.0) or 0.0)))
            # 表布可能在 seg_torso 上，也可能已经被切件成 skirt_main（T66.16）——
            # 判据是「部件 id 里带 skirt」，别再写死 seg_torso。
            _skirt_params = set()
            for _pm in _rig.get("params", []):
                for _b in _pm.get("binds", []) or []:
                    _d = next((d for d in _rig.get("deformers", [])
                               if d.get("id") == _b.get("deformer")), None)
                    if _d and "skirt" in str(_d.get("part", "")) and "skirt" in _d.get("id", ""):
                        _skirt_params.add(_pm["id"])
            check("裙子里布跟表布同一条参数、且有延迟（%s）" % _tag,
                  bool(_drv) and any(pid in _skirt_params and lag > 0 for pid, lag in _drv),
                  "里布形变器 %s 被 %s 驱动；表布参数 %s"
                  % (_defs, [(p_, l_) for p_, l_ in _drv], sorted(_skirt_params)))
            # 里布必须**跟得比表布少**：两边位移一样大就等于齐步走，甩出去也露不出里子。
            # 形变器的驱动量两边都会收到 ≈ 参数值，差距写在各自的 dx 表里，
            # 所以这是静态性质（冒烟那边只验"确实被同一条参数驱动"）。
            def _maxdx(_ids):
                _v = 0.0
                for _d in _rig.get("deformers", []):
                    if _d.get("id") in _ids:
                        for _pt in _d.get("points", []):
                            _v = max(_v, abs(float(_pt.get("dx", 0.0) or 0.0)))
                return _v
            _front_defs = {d["id"] for d in _rig.get("deformers", [])
                           if "skirt" in str(d.get("part", "")) and "skirt" in d.get("id", "")
                           and d.get("part") != _lid}
            _lin_dx, _front_dx = _maxdx(set(_defs)), _maxdx(_front_defs)
            check("裙子里布跟得比表布少（%s）" % _tag,
                  _front_dx > 0 and 0 < _lin_dx < _front_dx,
                  "里布最大位移 %.2f vs 表布 %.2f（里布 / 表布 = %.2f）"
                  % (_lin_dx, _front_dx, (_lin_dx / _front_dx) if _front_dx else 0))
    # ㉓ 裙子切件（T66.16）：裙子必须从 seg_torso 里切出来、挂自己的骨链。
    #    为什么这条必须存在：骨链（回転デフォーマ）作用于**整个部件**。裙子还长在
    #    躯干上的时候给裙子插一根转骨，转起来会把整个上身带飞（G66.6）—— 而这个
    #    错误在单测里看不出来、在截图上要看半天。反过来，切件之后如果**没把**网格
    #    改挂到裙件上，裙子就成了死件（能摆但不摆），一样是"看起来做了"。
    for _split in sorted(glob.glob(os.path.join(root, "characters/*/forms/*/sprites/skirt_split.json"))):
        _sp_dir = os.path.dirname(_split)
        _fdir = os.path.dirname(_sp_dir)
        _tag = "%s/%s" % (_fdir.split(os.sep)[-3], os.path.basename(_fdir))
        with io.open(_split, encoding="utf-8") as _f:
            _sj = json.load(_f)
        _sid = _sj.get("id", "skirt_main")
        _rp = os.path.join(_fdir, "rig.json")
        if not os.path.exists(_rp):
            continue
        with io.open(_rp, encoding="utf-8") as _f:
            _rig = json.load(_f)
        _bp = {x["id"]: x for x in _rig.get("parts", [])}
        check("裙子切件 %s 进了 rig（%s）" % (_sid, _tag), _sid in _bp,
              "rig.json 里没有 —— make_rig 没接上（%s）" % sorted(_bp)[:5])
        if _sid not in _bp:
            continue
        # 只数**带网格**的裙摆形变器：skirt_root / skirt_mid 是纯变换节点（骨），
        # 它们本来就没有 part（由 parent 串成链、由部件的 deformer 点名）。
        _sd = [d for d in _rig.get("deformers", [])
               if str(d.get("id", "")).startswith("skirt_")
               and (d.get("points") or d.get("cols") or d.get("keys"))]
        _wrong = [d["id"] for d in _sd if d.get("part") != _sid]
        check("裙摆网格全部挂在裙件上（%s）" % _tag, bool(_sd) and not _wrong,
              "这些网格还挂在别处：%s" % _wrong if _wrong
              else "%d 张网格" % len(_sd))
        # 躯干上**不许**再有任何裙摆网格：那等于裙子没切干净
        _left = [d["id"] for d in _rig.get("deformers", [])
                 if d.get("part") == "seg_torso" and "skirt" in str(d.get("id", ""))]
        check("躯干上不再挂着裙摆网格（%s）" % _tag, not _left,
              "躯干上还剩 %s —— 切件没切干净，裙子会被两套网格同时推" % _left
              if _left else "干净")
        # 裙件必须有自己的骨链（root→mid 两层，网格挂在中段下面）
        _parent = {d["id"]: d.get("parent") for d in _rig.get("deformers", [])}
        _chain = [_parent.get(d["id"]) for d in _sd if _parent.get(d["id"])]
        check("裙件接了骨链（%s）" % _tag, bool(_chain) and bool(_bp[_sid].get("deformer")),
              "网格没有 parent 骨、或部件没有 points deformer —— 裙子只能是死件"
              if not _chain or not _bp[_sid].get("deformer")
              else "链尾 %s，入口 %s" % (sorted(set(_chain)), _bp[_sid]["deformer"]))
        check("裙子切件是无损的（%s）" % _tag, int(_sj.get("lossless", 1)) == 0,
              "切件时合成误差 %s 像素（必须 0）" % _sj.get("lossless"))

    # ㉒ 同一部件上的多张网格形变器**必须同尺寸**（引擎硬约束）。
    #    zrig 是把同部件的几张网格**逐点相加**之后再去采样的，尺寸不一样直接拒载
    #    整份 rig（T45.12 第一版给躯干加了张 6x34，撞上裙摆的 2x10 ⇒ 启动期 ERROR、
    #    画面停在上一帧）。这条闸让它在生成器这一侧就红，而不是等引擎拒载。
    for _rp in sorted(glob.glob(os.path.join(root, "characters/*/forms/*/rig.json"))):
        _tag = "%s/%s" % (_rp.split(os.sep)[-4], _rp.split(os.sep)[-2])
        with io.open(_rp, encoding="utf-8") as _f:
            _rig = json.load(_f)
        _bypart = {}
        for _d in _rig.get("deformers", []):
            _bypart.setdefault(_d.get("part"), []).append(
                (_d.get("id"), int(_d.get("cols", 0)), int(_d.get("rows", 0))))
        _bad = {k: v for k, v in _bypart.items()
                if len({(c, r) for _, c, r in v}) > 1}
        check("同部件的网格形变器尺寸一致（%s）" % _tag, not _bad,
              "; ".join(f"{k}: {v}" for k, v in _bad.items()) if _bad
              else "%d 个部件带网格" % len(_bypart))

    # ㉓ 外套前襟下摆（T45.12）：摆动做在躯干的网格上，所以三件事必须成立 ——
    #    ① 中间开襟那几列不许被推（推了会把衬衫扣子和裙腰一起平移）；
    #    ② 幅度要小于裙摆（「上着は少し重い素材なのであまり揺らさない」）；
    #    ③ 由自己的参数驱动、且延迟比裙摆大（两件衣服不许同拍子动）。
    for _jp in sorted(glob.glob(os.path.join(root, "characters/*/forms/*/sprites/jacket_parts.json"))):
        _form_dir = os.path.dirname(os.path.dirname(_jp))
        _tag = "%s/%s" % (_form_dir.split(os.sep)[-3], os.path.basename(_form_dir))
        _rp = os.path.join(_form_dir, "rig.json")
        if not os.path.exists(_rp):
            continue
        with io.open(_jp, encoding="utf-8") as _f:
            _hem = json.load(_f)["hem"]
        with io.open(_rp, encoding="utf-8") as _f:
            _rig = json.load(_f)
        _jd = next((d for d in _rig.get("deformers", []) if d.get("id") == "jacket_hem_x"), None)
        check("外套下摆形变器进了 rig（%s）" % _tag, _jd is not None,
              "没有 jacket_hem_x —— 生成器没接上" if _jd is None
              else "%dx%d，%d 个点" % (_jd["cols"], _jd["rows"], len(_jd["points"])))
        if not _jd:
            continue
        _tw = float(_hem["torso_size"][0])
        _pan = [(float(q["x0"]), float(q["x1"])) for q in _hem["panels"]]
        _gapped = []
        for _pt in _jd["points"]:
            _x = _tw * int(_pt["c"]) / int(_jd["cols"])
            _inside = any(x0 - 0.3 * (_pan[1][0] - _pan[0][1]) <= _x <= x1 + 0.3 * (_pan[1][0] - _pan[0][1])
                          for x0, x1 in _pan)
            if not _inside and abs(float(_pt.get("dx", 0.0))) > 1e-6:
                _gapped.append((_pt["c"], _pt["r"], _pt["dx"]))
        check("外套下摆不推中间开襟那几列（%s）" % _tag, not _gapped,
              "这些点落在两片前襟之间却有位移：%s" % _gapped[:4] if _gapped
              else "开襟列位移恒为 0，衬衫/裙腰不跟着走")
        _amax = lambda ids: max([abs(float(p.get("dx", 0.0)))
                                 for d in _rig["deformers"] if d["id"] in ids
                                 for p in d["points"]] or [0.0])
        _skirt_ids = {d["id"] for d in _rig["deformers"]
                      if "skirt" in str(d.get("part", "")) and d["id"].startswith("skirt_")
                      and d["id"].endswith("_x")}
        _ja, _sk = _amax({"jacket_hem_x"}), _amax(_skirt_ids)
        check("外套下摆摆得比裙摆小（%s）" % _tag, 0 < _ja < _sk,
              "外套 %.1f vs 裙摆 %.1f（上着は重い素材）" % (_ja, _sk))
        _lag = {}
        for _pm in _rig.get("params", []):
            for _b in _pm.get("binds", []) or []:
                if _b.get("deformer") == "jacket_hem_x":
                    _lag[_pm["id"]] = float(_b.get("lag", 0.0) or 0.0)
                if _b.get("deformer") in _skirt_ids and _b.get("deformer") != "jacket_hem_x":
                    _lag.setdefault("__skirt__", 0.0)
                    _lag["__skirt__"] = max(_lag["__skirt__"], float(_b.get("lag", 0.0) or 0.0))
        _jlag = _lag.get("ParamJacketSway", -1.0)
        check("外套下摆由 ParamJacketSway 驱动、比裙摆更迟钝（%s）" % _tag,
              _jlag > _lag.get("__skirt__", 0.0),
              "外套 lag %.2fs vs 裙摆 lag %.2fs" % (_jlag, _lag.get("__skirt__", 0.0)))

    # ㉔ 头发的摇物必须是**多段**，而且后发不许动到头顶剪影（T46.1）。
    #    教程口径：前髪・横髪は1段で十分、**後ろ髪は2~3段**（長いほど段数を増やす）。
    #    「1段しかない＝髪全体が棒のように一体で動いて硬く見える」。
    #    本项目的后发是一顶短发壳，露在外面的上半截就是**头部剪影**——
    #    所以第二段的位移必须全部压在下沿，上面几行一个像素都不许动。
    for _rp in sorted(glob.glob(os.path.join(root, "characters/*/forms/*/rig.json"))):
        _tag = "%s/%s" % (_rp.split(os.sep)[-4], _rp.split(os.sep)[-2])
        with io.open(_rp, encoding="utf-8") as _f:
            _rig = json.load(_f)
        if not any(p.get("id") == "hair_back" for p in _rig.get("parts", [])):
            continue
        _ph = [x for x in _rig.get("physics", []) if x.get("part") == "hair_back"]
        _chain = [x for x in _ph if x.get("driver") in {y["id"] for y in _ph}]
        check("后发是多段摆（%s）" % _tag, len(_ph) >= 2 and len(_chain) >= 1,
              "hair_back 上 %d 条物理、其中 %d 条串在前一段后面"
              % (len(_ph), len(_chain)))
        _bs = next((d for d in _rig.get("deformers", []) if d.get("id") == "back_s"), None)
        if _bs:
            _rows = int(_bs["rows"])
            _top = [(p["r"], p.get("dx", 0)) for p in _bs["points"]
                    if p["r"] <= _rows // 2 and abs(float(p.get("dx", 0.0))) > 1e-9]
            check("后发第二段不动头顶剪影（%s）" % _tag, not _top,
                  "上半截这些行有位移：%s" % _top[:4] if _top
                  else "位移全在下沿（r>%d）" % (_rows // 2))
            _side = next((x for x in _rig["physics"] if x.get("id") == "side_l_tip"), None)
            _btip = next((x for x in _rig["physics"] if x.get("deformer") == "back_s"), None)
            if _side and _btip:
                check("后发比侧发更软更慢（%s）" % _tag,
                      float(_btip["stiffness"]) < float(_side["stiffness"]),
                      "后发梢 stiffness %.0f vs 侧发梢 %.0f（重的头发摆得慢）"
                      % (_btip["stiffness"], _side["stiffness"]))

    # ㉕ 长发（T46.2）：三件事必须成立 —— ① 层在**所有身体件之后**（后ろ髪的标准层位），
    #    ② 组挂 head（层管遮挡、组管跟谁动，后发必须跟着头转），
    #    ③ 摆动是 **3 段**且逐段变软（長い後ろ髪は3段振り子；軽い/先ほど柔らかく）。
    for _rp in sorted(glob.glob(os.path.join(root, "characters/*/forms/*/rig.json"))):
        _tag = "%s/%s" % (_rp.split(os.sep)[-4], _rp.split(os.sep)[-2])
        with io.open(_rp, encoding="utf-8") as _f:
            _rig = json.load(_f)
        _lh = next((p for p in _rig.get("parts", []) if p.get("id") == "acc_hair_long"), None)
        if not _lh:
            continue
        _body = [p for p in _rig["parts"]
                 if p["id"].startswith("seg_") or p["id"].startswith("arm_")]
        _minb = min(int(p["layer"]) for p in _body)
        check("长发在整个身体之后（%s）" % _tag, int(_lh["layer"]) < _minb,
              "长发 layer %d vs 最低的身体件 %d" % (_lh["layer"], _minb))
        check("长发跟着头转（组是 head）（%s）" % _tag, _lh.get("group") == "head",
              "group=%r —— 层号管遮挡、组管跟谁动，后发必须挂 head" % _lh.get("group"))
        # 2026-10-17（T47.2）：长发已经从旧弹簧摆迁到物理 2.0 的粒子链上。
        # "逐段变软"的口径也跟着换 —— 旧的看 stiffness 递减，
        # 新的看官方那两个旋钮：摆长 Radius 递减（根长梢短）+ 反応速度 Delay 递减。
        _ch = next((c for c in _rig.get("physics2", [])
                    if c.get("part") == "acc_hair_long"), None)
        if check("长发挂的是物理 2.0 的摆链（%s）" % _tag, _ch is not None,
                 "没有 → 要么没迁，要么迁错了部件"):
            _pt = _ch["particles"][1:]
            _rad = [float(x["radius"]) for x in _pt]
            _dly = [float(x.get("delay", 1.0)) for x in _pt]
            check("长发是 3 段摆、而且逐段变软（%s）" % _tag,
                  len(_pt) >= 3
                  and all(a > b for a, b in zip(_rad, _rad[1:]))
                  and all(a >= b for a, b in zip(_dly, _dly[1:])),
                  "%d 段，摆长 %s，反応速度 %s（長い後ろ髪は3段振り子）"
                  % (len(_pt), "/".join("%.0f" % v for v in _rad),
                     "/".join("%.2f" % v for v in _dly)))

    # ㉖ 发型互斥组（T46.3 双马尾 / 马尾）。四条，每条都对着一个具体的坑：
    #    ① 一个发型 = 一个档位，**不许再有自己的开关参数**（两套开关并存 ⇒
    #       "长发+双马尾同时开"是个合法状态，画面上就是三坨头发打架）；
    #    ② default:"none" 这个写法必须**两边同时认**（表里写了、引擎 load_poses 也要认），
    #       只改一边的话：表这边以为默认短发，引擎那边会退回第一个档位 = 一开机就戴着长发；
    #    ③ 双马尾是同一张原图镜像出来的，左右必须**真对称**（锚点互补、位置关于中线对称、
    #       层号不重复）—— 猫耳那四轮返工全栽在"镜像件没单独验"上；
    #    ④ 扎起来的发束要比披着的头发**硬**（段数更少、摆长更短），
    #       这是教程口径「ツインテールは束ねられている分硬い」，也是手感的来源。
    _att_p = os.path.join(root, "characters", "xiaoxun", "design", "attachments.json")
    if os.path.exists(_att_p):
        _att = jsonc(_att_p)
        _by = {x["id"]: x for x in _att["attachments"]}
        _hair = [x for x in _att["attachments"] if "hairstyle" in (x.get("tags") or [])]
        _nogrp = [x["id"] for x in _hair if x.get("pose_group") != "hairstyle"]
        _dblsw = [x["id"] for x in _hair if x.get("param")]
        check("发型都归在同一个互斥组里，而且没有一个还留着自己的开关参数",
              not _nogrp and not _dblsw,
              ("不在组里：%s；还留着 param：%s" % (_nogrp, _dblsw))
              if (_nogrp or _dblsw) else
              "%d 个发型挂件（%s）全在 hairstyle 组里，显隐只有一套开关"
              % (len(_hair), "/".join(sorted(x.get("pose_id", "?") for x in _hair))))
        _hg = next((g for g in _att.get("pose_groups", []) if g["id"] == "hairstyle"), None)
        _zrig_src = io.open(os.path.join(root, "src", "core", "zrig.c"),
                            encoding="utf-8").read()
        check("default:\"none\"（= 默认短发）表里写了，引擎也认",
              _hg is not None and _hg.get("default") == "none"
              and 'z_streq(defid, "none")' in _zrig_src,
              "表 default=%r / zrig.c load_poses 认不认 none：%s"
              % (_hg and _hg.get("default"),
                 'z_streq(defid, "none")' in _zrig_src))
        _tl, _tr = _by.get("hair_twin_l"), _by.get("hair_twin_r")
        if _tl and _tr:
            _ax = float(_tl["anchor"][0]) + float(_tr["anchor"][0])
            _dx = float(_tl["pos_rel"][0]) + float(_tr["pos_rel"][0])
            _dy = abs(float(_tl["pos_rel"][1]) - float(_tr["pos_rel"][1]))
            _mir = bool(_tl.get("mirror")) != bool(_tr.get("mirror"))
            check("双马尾左右真对称（锚点互补 / 位置关于中线对称 / 只镜像一侧 / 层号不重复）",
                  abs(_ax - 1.0) < 0.02 and abs(_dx) < 0.06 and _dy < 1e-6 and _mir
                  and int(_tl["layer"]) != int(_tr["layer"]),
                  "锚点和 %.3f（要 1.0）、左右偏移和 %+.3f 个头高（要 ~0）、"
                  "高度差 %.4f、镜像只有一侧 %s、层 %d/%d"
                  % (_ax, _dx, _dy, _mir, _tl["layer"], _tr["layer"]))
            # 层位：必须夹在手臂之上、后发壳之下 —— 高了会盖住脸，低了会被身体吃掉
            _slot = next((x for x in _att["slots"] if x["id"] == "head_side_hair"), {})
            check("双马尾的层夹在手臂之上、后发壳之下（发根藏得住、辫子遮不住脸）",
                  143 < int(_tl["layer"]) < 170 and 143 < int(_tr["layer"]) < 170
                  and _slot.get("group") == "head",
                  "层 %d/%d（手臂 143 < x < 后发壳 170），组 %r"
                  % (_tl["layer"], _tr["layer"], _slot.get("group")))
        # ⑤ 这一条被改过两次，两次都是用户打回，前因后果都留着：
        #    第八问按「短发甚至都没去除」给 twin/pony 加了
        #    hide_parts:[hair_side_l, hair_side_r] —— 用户拿截图打回四条：
        #    人耳裸露在脸颊、后发壳平切口横在颧骨、发丝碎片、剪影缺一块。
        #    第九问据此写成「承重件一律不许裸隐」，并撤销了 hide_parts。
        #    第十问用户再次打回：「马尾不是加个马尾，而是**整个发型都要配合着
        #    做出改变**」—— 不藏鬓发就永远做不出"换了一套发型"。教程口径一致
        #    （kawase：ショートヘアはロングヘアから削除するだけだと印象が変わらない）。
        #    所以规矩第三版：**藏可以，但必须自带接管件**。
        #      · 藏之前先把底图补画了（tools/make_scalp_patch.py，塗り足し，
        #        Live2D 官方 PSD 教程的硬性工序）——这解决"底下见不得人"。
        #      · 这一档必须同时 extra_parts 里给出替代件——这解决"只减不加"。
        #    覆盖率的量化门槛在 check_assets 的几何闸（head_silhouette.hide_backing，
        #    接管 >=45% 且不露透明背景 <=2%）；这里只查结构：藏了就得有东西顶上。
        _hide = (_hg or {}).get("hide_parts") or {}
        _load_bearing = {"hair_side_l", "hair_side_r", "hair_back", "seg_head"}
        # 接管件 = 表里**自己声明属于这一档**的挂件（pose_group/pose_id）
        #    接管必须是**同一个部位**的：藏鬓发就得给鬓发位的件，拿脑后的马尾
        #    顶名额不算（第一版就是这么漏过去的——马尾本体 body_back_pony 占着
        #    pony 档的名额，抽掉掠发也照样绿）。
        #   横髪位的替代件有三种：原生槽、扎发用的细缕、长发用的长鬓发。
        #   第十二问加 head_side_long —— 用户贴的长发参考图里，长发的**横髪也是
        #   长的**（从太阳穴一路垂到胸口），齐腮短鬓配过腰长发本来就不成立。
        #   第十六问（2026-10-19）又加了 head_crown_tied：T46.16 之后这个槽里
        #   装的不再是"头顶一小片"，而是**从参考模板上切下来的整片头发壳**
        #   （下巴以上一整圈，脸挖空）。它一件同时顶掉了底图的齐腮鬓发**和**
        #   后发壳在头部那一段 —— 这正是用户要的「换发型要换整颗头」。
        #   角色表不更新的话，做对了反而会红（实测 pony:hair_side_l/r、
        #   twin:hair_back 三条）。另外双马尾的辫子在 head_side_hair 槽，
        #   它接管的就是后发壳伸到剪影外的那部分体积，所以也给 hair_back 算数。
        _CROWN = {"head_crown_tied"}
        _SIDE = {"head_side_hair", "head_side_sweep", "head_side_long"} | _CROWN
        _ROLE = {"hair_side_l": _SIDE,
                 "hair_side_r": _SIDE,
                 "hair_back": {"body_back_hair", "body_back_pony",
                               "head_side_hair"} | _CROWN,
                 "seg_head": {"head_under_bangs", "head_in_hair"}}
        _extra = {}
        for _a in _att.get("attachments", []):
            if _a.get("pose_group") == "hairstyle" and _a.get("pose_id"):
                _extra.setdefault(_a["pose_id"], []).append(_a.get("slot"))
        _bad = sorted({
            "%s:%s" % (_k, _p)
            for _k, _v in _hide.items() for _p in (_v or [])
            if _p in _load_bearing
            and not (set(_extra.get(_k) or []) & _ROLE.get(_p, set()))})
        _scalp = os.path.exists(os.path.join(root, "tools", "make_scalp_patch.py"))
        _who = sorted({_k for _k, _v in _hide.items()
                       if set(_v or []) & _load_bearing})
        check("藏承重件的档位都自带了接管件（只减不加 = 在头上开洞）",
              not _bad and _scalp,
              ("这些档位藏了承重件却没给替代件：%s" % _bad) if _bad else
              ("缺 tools/make_scalp_patch.py（藏之前要先把底图补画了）"
               if not _scalp else
               "藏承重件的档位 %s，每档都带了**同部位**的替代件；底图补画工具在位"
               % (_who or "（无）")))
        # ⑥ 收侧发这件事要**一路通到引擎**：表里写了 hide，生成器要搬进 rig.json，
        #    引擎的 pose_opacity 要认。少任何一环都是"在 JSON 里写日记"（G117 那类病）。
        _rigp = os.path.join(root, "characters", "xiaoxun", "forms", "teen", "rig.json")
        _rig_ok = False
        if os.path.exists(_rigp):
            _rg = jsonc(_rigp)
            _grp = next((g for g in _rg.get("poses", []) if g["id"] == "hairstyle"), {})
            _ents = {e["id"]: e for e in _grp.get("entries", [])}
            # 表里写什么，rig.json 就要有什么 —— 包括"什么都不藏"。
            _rig_ok = all(set(_hide.get(k) or []) ==
                          set(_ents.get(k, {}).get("hide") or [])
                          for k in _ents)
        _eng_ok = ("e->nhid" in _zrig_src and "posehide" in _zrig_src
                   and "op *= 1.0 - e->opacity" in _zrig_src)
        check("藏件这条链路是通的：表 → rig.json → 引擎 pose_opacity 三处一致",
              _rig_ok and _eng_ok,
              "rig.json 的 hide 和表一致：%s；zrig.c 认 hide（nhid/posehide/乘 1-w）：%s"
              "（引擎这一侧要留着：T46.7 换 hair_back 本体时还要用）"
              % (_rig_ok, _eng_ok))
        # ⑦ 发型这类**带渐变**的件不许再走色卡三色重铺。
        #    k-means 平色重铺是给漫符用的；按亮度压成 3 色会把柔和明暗和蓝发梢
        #    一起碾平 —— 那正是用户说"色彩完全不一样非常的违和"的原因。
        #    ★ 2026-10-18 增补：走 derive 的件**天然豁免**。derive 是直接拿
        #    本体那张贴图（hair_side_l.png 等）拉伸/收窄出来的，逐像素就是
        #    原画的颜色和笔触，同源性比"统计上对齐"更强 —— 再套一层 Lab 匹配
        #    是拿自己匹配自己。要求它写 recolor_match 只会逼出一行空配置。
        _wrong = [x["id"] for x in _hair if x.get("recolor")]
        _nomatch = [x["id"] for x in _hair
                    if not x.get("recolor_match") and not x.get("derive")]
        check("发型挂件走 Lab 统计匹配（recolor_match），不走色卡平色重铺",
              not _wrong and not _nomatch,
              ("还在用 recolor 重铺：%s；没写 recolor_match：%s" % (_wrong, _nomatch))
              if (_wrong or _nomatch) else
              "%d 件发型全部按本体头发做 Lab mean/std 对齐（参考系 %s）"
              % (len(_hair),
                 "/".join((_hair[0].get("recolor_match") or {}).get("ref_sprites", []))))

        _lch = (_by.get("hair_long") or {}).get("physics", {}).get("chain", {})
        _tch = (_tl or {}).get("physics", {}).get("chain", {})
        if _lch and _tch:
            _lp, _tp = _lch["particles"][1:], _tch["particles"][1:]
            check("扎起来的发束比披着的头发硬（段数更少、摆长更短）",
                  len(_tp) < len(_lp)
                  and float(_tp[0]["radius"]) < float(_lp[0]["radius"]),
                  "双马尾 %d 段 / 根半径 %.0f　vs　长发 %d 段 / 根半径 %.0f"
                  % (len(_tp), float(_tp[0]["radius"]),
                     len(_lp), float(_lp[0]["radius"])))

    # ⑳ 兜帽的几何闸（T46.6）。用户 2026-10-18 第三次退回这件衣服，三条意见是
    #    「没链接衣服 / 大小和头型不匹配 / 把新头发全遮住了」。前两条都是**几何**问题，
    #    靠眼睛看一轮过一轮，所以这里按实测锚点焊死四条线：
    #      ① 兜帽顶必须真的盖过头顶 —— 比头顶还矮就是顶在脑门上，一眼假；
    #      ② 兜帽下摆不许越过肩线太多 —— 越过就变成披肩/斗篷，那正是"没链接衣服"的来源；
    #      ③ 宽度要按头宽定标（1.1~1.6 个头单位）—— 窄了夹头，宽了变灯罩；
    #      ④ 高宽比 ≤ 1.35 —— 比这更瘦长的就不是兜帽，是连帽斗篷。
    #    尺寸直接读 PNG 文件头（8~24 字节），不依赖 PIL，闸子在没装图像库的机器上也能跑。
    _hood = _by.get("hood_up") if os.path.exists(_att_p) else None
    if _hood:
        _fm_dir = os.path.join(root, "characters", "xiaoxun", "forms", "teen")
        _anc = jsonc(os.path.join(_fm_dir, "design", "anchors.json"))
        _rig_h = jsonc(os.path.join(_fm_dir, "rig.json"))
        _unit = float(_anc["meta"]["head_ratio"]) * float(_anc["meta"]["height_px"])
        _pt = next((p for p in _rig_h["parts"] if p["id"] == "acc_hood_up"), None)
        _png = os.path.join(_fm_dir, (_pt or {}).get("file", ""))

        def _png_wh(path):
            with io.open(path, "rb") as _f:
                _b = _f.read(24)
            return (int.from_bytes(_b[16:20], "big"), int.from_bytes(_b[20:24], "big"))

        if _pt and os.path.exists(_png):
            _sw, _sh = _png_wh(_png)
            _sc = float(_pt.get("scale", 1.0))
            _sw, _sh = _sw * _sc, _sh * _sc          # @2x 贴图 → 画布像素
            _pad = 0.04 / 1.08                        # CROP_MARGIN 补边占成品的比例
            _cw, _ch = _sw * (1 - 2 * _pad), _sh * (1 - 2 * _pad)
            _top = _pt["pos"][1] + _sh * _pad
            _bot = _top + _ch
            # 原画在画布里的纵向偏移：画布比原画高出来的那一截（make_rig 的 oy）
            _oy = float(_rig_h["canvas"]["h"]) - float(_anc["meta"]["height_px"])
            _head_top = _oy + float(_anc["points"]["head_top"][1])
            _sh_y = _oy + float(_anc["points"]["shoulder_l"][1])
            # ★★★ 2026-10-19 T46.17：这里原来还有一条「兜帽顶盖过头顶」。
            #   删掉了 —— 它拿 `anchors.points.head_top` 当头顶，而那个点是
            #   **呆毛的尖**（画布 y=68），不是颅顶（y=116）；戴上兜帽时呆毛
            #   本来就收起来了，拿一根不在场的呆毛要求帽子盖住它，前提是错的。
            #   用户连着四次打回的「帽子浮在头上/像顶锅」，根子就是为了过这条闸
            #   把整顶帽子往上推了几十像素（详见 LESSONS 248）。
            #   同一件事现在只留**一把尺子**：check_assets 的「头饰按头宽定标」，
            #   它量的是真像素（帽顶 vs 实测剪影颅顶），而且本轮从查 1 顶
            #   扩到查 4 顶 —— 合起来是**变严**，不是少查。
            #   `_head_top` 仍保留给下面的「下摆不越肩线」用。
            check("兜帽下摆不越过肩线太多（越过就变披肩，用户退回过）",
                  _bot <= _sh_y + 0.15 * _unit,
                  "下摆 y=%.0f　肩线 y=%.0f　上限 y=%.0f" % (_bot, _sh_y, _sh_y + 0.15 * _unit))
            # 2026-10-18 第九问收紧：1.10~1.60 这条带子**太松，放过了 v3**
            #（v3 实测 1.33 头单位，画面上是顶在头上的一口锅，用户原话"大小完全错误"）。
            # 根子在"头单位"是 anchors 里的**比例常数 278px**，不是头的实际宽度 ——
            # 头部剪影实测只有 244px 宽（1 头单位 ≈ 1.14 倍实测头宽）。
            # 按剪影算，兜帽该是 1.10~1.40 倍，换算回头单位就是 0.97~1.23；
            # 取 0.95~1.25。像素级真值由 check_assets 的头部几何闸兜底。
            check("兜帽宽度按头宽定标（0.95~1.25 个头单位 = 1.08~1.43 倍实测头宽）",
                  0.95 <= _cw / _unit <= 1.25,
                  "宽 %.0f px = %.2f 个头单位（头单位 %.0f px；实测头部剪影宽 244px）"
                  % (_cw, _cw / _unit, _unit))
            check("兜帽高宽比 ≤ 1.35（再瘦长就是连帽斗篷不是兜帽）",
                  _ch / _cw <= 1.35,
                  "高 %.0f / 宽 %.0f = %.2f" % (_ch, _cw, _ch / _cw))

    # ㉑ 头部几何闸不许是死工具（T46.8）。tools/head_silhouette.py 要被
    #    check_assets 真的调起来，否则就又是"在仓库里写日记"。
    _hs_p = os.path.join(root, "tools", "head_silhouette.py")
    _ca_p = os.path.join(root, "tools", "check_assets.py")
    _hs_src = io.open(_hs_p, encoding="utf-8").read() if os.path.exists(_hs_p) else ""
    _ca_src = io.open(_ca_p, encoding="utf-8").read() if os.path.exists(_ca_p) else ""
    check("头部几何闸装好了并且真被调起来（藏件露底 + 头饰按实测头宽定标）",
          "def hide_backing" in _hs_src and "def headwear_fit" in _hs_src
          and "import head_silhouette" in _ca_src
          and "hide_backing(character, form)" in _ca_src
          and "headwear_fit(character, form)" in _ca_src,
          "head_silhouette.py 有两个量法：%s/%s；check_assets 调了：%s"
          % ("def hide_backing" in _hs_src, "def headwear_fit" in _hs_src,
             "import head_silhouette" in _ca_src))

    # 遮挡别人的差分件必须有**用户点得到**的开关（2026-10-18 用户原话「做个开关」）。
    # 调试台那块把英文 id 原样铺出来，不算数 —— 它是给我自己验引擎的。
    # 这里核的是装扮面板：layout.json 里挂着、而且每个互斥组都登记了中文名。
    _du_p = os.path.join(root, "web", "components", "dressup.js")
    if os.path.exists(_att_p) and os.path.exists(_du_p):
        _du = io.open(_du_p, encoding="utf-8").read()
        _lay_ids = []
        for _items in jsonc(os.path.join(root, "web", "layout.json"))["regions"].values():
            _lay_ids += [x if isinstance(x, str) else x.get("id") for x in _items]
        check("装扮面板挂在界面上（用户点得到，不是只有调试台）", "dressup" in _lay_ids,
              "layout.json 的组件：%s" % " ".join(x for x in _lay_ids if x))
        _grp_ids = [g["id"] for g in _att.get("pose_groups", [])]
        _nong = [g for g in _grp_ids if ("%s:" % g) not in _du]
        check("每个互斥差分组在装扮面板里都有中文名（没登记就只能看见英文 id）",
              not _nong, "缺 %s" % _nong if _nong else "%d 个组：%s"
              % (len(_grp_ids), " ".join(_grp_ids)))
        _hood_g = next((g for g in _att.get("pose_groups", []) if g["id"] == "hood_pose"), None)
        _hood_r = next((g for g in jsonc(os.path.join(root, "characters", "xiaoxun", "forms",
                                                      "teen", "rig.json")).get("poses", [])
                        if g["id"] == "hood_pose"), None)
        _back = (_hood_g or {}).get("extra_parts", {}).get("down", [])
        check("兜帽是两档开关，摘下那档把呆毛和猫耳放回来",
              bool(_hood_r) and sorted(e["id"] for e in _hood_r["entries"]) == ["down", "up"]
              and len(_back) >= 3,
              "档位 %s；摘下档放回 %d 个部件（%s）"
              % ([e["id"] for e in (_hood_r or {}).get("entries", [])], len(_back),
                 " ".join(_back)))

    # 形态元数据必须描述**成品**：forms.json 声明的头身比要和 anchors.json 实测的对上。
    # 挂件的相对几何就是按实测值定标的，声明值写错会让别的形态跟着一起偏。
    for _fp in sorted(glob.glob(os.path.join(root, "characters/*/forms.json"))):
        _cd2 = os.path.dirname(_fp)
        with io.open(_fp, encoding="utf-8") as _f:
            _forms = json.load(_f)["forms"]
        for _fm in _forms:
            if _fm.get("status") != "ready":
                continue
            _ap = os.path.join(_cd2, "forms", _fm["id"], "design", "anchors.json")
            if not os.path.exists(_ap):
                continue
            with io.open(_ap, encoding="utf-8") as _f:
                _ht = float(json.load(_f)["meta"]["heads_tall"])
            _decl = str(_fm.get("head_body_ratio", "")).split(":")
            _ok = len(_decl) == 2 and abs(float(_decl[1]) - _ht) < 0.15
            check("%s/%s 声明的头身比和实测一致" % (os.path.basename(_cd2), _fm["id"]), _ok,
                  "声明 %s，实测 1:%.2f" % (_fm.get("head_body_ratio"), _ht))
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
    # ---- TLS 的不可退让项（T61.9，2026-10-24）----
    # 这几条不是风格问题，是安全底线。放源码级检查是因为：
    # 行为级的闸（make tls）要起服务端、要造证书，跑得慢也容易被人"先跳过"；
    # 而这几行一旦被改坏，后果是用户的 API key 明文上网或被中间人读走。
    tls_c = ""
    tp = os.path.join(root, "src", "core", "ztls.c")
    if os.path.isfile(tp):
        tls_c = io.open(tp, encoding="utf-8").read()
    if tls_c:
        check("TLS 必须要求对端证书（SSL_VERIFY_PEER）",
              "ZSSL_VERIFY_PEER" in tls_c and "SSL_CTX_set_verify" in tls_c,
              "src/core/ztls.c —— 少了它就是\"假 https\"")
        check("TLS 必须校验主机名（SSL_set1_host）",
              "SSL_set1_host" in tls_c,
              "只验签名链不验名字，攻击者拿一张自己域名的合法证书就能冒充任何站")
        check("握手后还要复查一次 verify_result",
              "SSL_get_verify_result" in tls_c,
              "白拿的第二道防线：实测把 set_verify 改坏时，就是它独自守住的")
        # 绝不能出现"跳过校验"的开关。有开关就一定有人在某天打开它。
        bad = [k for k in ("SSL_VERIFY_NONE", "ZSSL_VERIFY_NONE", "insecure",
                           "skip_verify", "no_verify", "allow_invalid")
               if k in tls_c]
        check("源码里不许有\"跳过证书校验\"的开关", not bad,
              "发现 %s —— 不验证书的 https 和明文没区别，而这条线上跑的是用户的密钥" % bad)
    # 降级红线：https 失败时绝不能改用明文重试
    hp = os.path.join(root, "src", "core", "zhttp.c")
    if os.path.isfile(hp):
        http_c = io.open(hp, encoding="utf-8").read()
        check("https 失败后不许回退明文",
              "u.tls = 0" not in http_c and "u.tls=0" not in http_c,
              "src/core/zhttp.c —— 出现把 tls 标志清零的代码就是在偷偷降级")

    # ---- 云端 TTS 客户端的密钥纪律（T58，2026-10-18）----
    # 两条都踩得起：密钥进日志 = 泄露，而日志是会被提交回仓库的（voice-render 的失败回传）。
    vcp = os.path.join(root, "tools", "voice_cloud.py")
    if os.path.isfile(vcp):
        vcs = io.open(vcp, encoding="utf-8").read()
        # (?<![A-Za-z_]) 是必须的：没有它，`def fingerprint(key: str)` 会被当成 print(key) 误报
        leak = re.findall(r"(?<![A-Za-z_])print\([^)]*\bkey\b(?![_a-zA-Z])[^)]*\)", vcs)
        leak = [x for x in leak if "fingerprint(" not in x and "key_ref" not in x
                and "env" not in x]
        check("云端 TTS 客户端不会把密钥打印出来（只许打指纹）", not leak,
              "可疑：%s" % leak[:2] if leak else "所有输出走 fingerprint()")
        check("密钥指纹反推不出原文（长度 + 首尾两字 + sha256 前 8 位）",
              "hashlib.sha256" in vcs and "def fingerprint" in vcs,
              "fingerprint() 用的是 sha256 截断")
    wf = os.path.join(root, ".github", "workflows", "voice-render.yml")
    if os.path.isfile(wf):
        wl = io.open(wf, encoding="utf-8").read().splitlines()
        # secrets 只许出现在 env: 映射里；写进 run: 的命令行会原样进日志
        bad = [l.strip() for l in wl if "secrets." in l and ("run:" in l or "$(" in l)]
        check("workflow 里的密钥只经 env 注入，没写进命令行", not bad,
              "；".join(bad[:2]) or "3 个 secret 都在 env 段")

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

        # ★ 2026-10-18：路由表**不许顶到引擎上限**。
        #   zgateway.c 读表时是 `while (nroutes < ZGW_MAX_ROUTES)` —— 超出的部分
        #   被**静默丢弃**（只在诊断里留一行），而被丢掉的永远是排在后面的那几条，
        #   也就是优先级最低的本地建模/视频。供应商一多就会踩，所以用到 80% 就报红。
        _gh = io.open(os.path.join(root, "src/core/zgateway.h"), encoding="utf-8").read()
        _m = re.search(r"#define\s+ZGW_MAX_ROUTES\s+(\d+)", _gh)
        _cap_n = int(_m.group(1)) if _m else 0
        check("路由表没顶到引擎上限（留 20% 余量）",
              _cap_n > 0 and len(rts) <= _cap_n * 0.8,
              "%d 条路由 / 上限 %d（%.0f%%）—— 超了会被 zgateway.c 静默截断"
              % (len(rts), _cap_n, 100.0 * len(rts) / max(_cap_n, 1)))

        # ★ 云端/本地**双栈**：用户 2026-10-18 的要求是"都要做云端和本地的适配"。
        #   逐条能力检查两边都有候选 —— 只有云端 = 断网就哑；只有本地 = 配置不够就废。
        #   允许留白的能力写在 _solo 里，每条都要说清为什么。
        _solo = {
            "web.search": "联网搜索天然只有云端（本地没有索引）",
            "code.execute": "沙箱执行只在本地（云端执行等于把代码交出去）",
            "file.read": "读本机文件只能在本机",
            "memory.recall": "记忆库在本机",
        }
        _sides = {}
        for r in rts:
            _sides.setdefault(r["cap"], set()).add(bool(r.get("local")))
        _half = sorted(c for c, sd in _sides.items()
                       if len(sd) < 2 and c not in _solo)
        check("每种能力都有云端和本地两条腿（双栈）", not _half,
              ("这些能力只有一侧：%s" % _half) if _half else
              "%d 种能力双栈齐备，另有 %d 种按设计单边（%s）"
              % (len(_sides) - len(_solo), len(_solo), "、".join(sorted(_solo))))
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
        # 服装件是**按形态的像素**重绘/换色出来的，不可能跨形态通用：
        # 每套服装用 forms[] 声明自己支持哪些形态，这里只查它声明的那些。
        # （2026-10-17：chibi 变成 ready 之后这条闸开始查它，才发现白名单一直没人读。）
        on_disk = {os.path.basename(f) for f in glob.glob(os.path.join(cdir, "forms/*"))}
        only = [f for f in (o.get("forms") or [])] or sorted(on_disk)
        miss = []
        for fid in only:
            for pid, v in (o.get("parts") or {}).items():
                f = v.get("file") if isinstance(v, dict) else v
                if f and not os.path.exists(os.path.join(cdir, "forms", fid, f)):
                    miss.append(f"{fid}:{f}")
        check(f"服装 {os.path.basename(od)} 贴图在", not miss, f"缺 {miss[:2]}" if miss else "")
        # 白名单不能变成后门：声明的形态必须真的存在，否则这条闸会悄悄空转
        check(f"服装 {os.path.basename(od)} 声明的形态都在磁盘上",
              set(only) <= on_disk, f"声明了不存在的形态 {sorted(set(only) - on_disk)}")

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
def strip_prose(src):
    """把源码里的注释和 docstring 都剥掉，只留会真正执行的部分。

    反向闸要查的是「源码里还有没有写死的字面量」。**讲解这条禁令的文字
    本身一定会提到那个字面量** —— 注释说明 ≠ 影子配置，两者必须分开。

    顺序很要命：**先 parse 再剥**。第一版反过来，先按行 split("#") 剥注释，
    结果 docstring 里的 `#2C2939` 把那段字符串截断成了语法错误，ast.parse
    抛 SyntaxError 走了回退分支，等于一点没剥 —— 闸照样误报。
    剥注释也不能按行 split，要用 tokenize，不然字符串里的 # 会被当注释。
    """
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return src
    lines = src.splitlines()
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Module, ast.FunctionDef,
                                 ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        body = getattr(node, "body", None)
        if (body and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)):
            for i in range(body[0].lineno - 1, min(body[0].end_lineno, len(lines))):
                lines[i] = ""
    import tokenize as _tk
    out = "\n".join(lines)
    try:
        toks = [t for t in _tk.generate_tokens(io.StringIO(out).readline)
                if t.type != _tk.COMMENT]
        return _tk.untokenize(toks)
    except Exception:
        return out


def check_no_dead_tables(root):
    """设计表里的顶层字段必须真的有人读（防"死表"）。

    2026-10-16 撞到的事：`design/attachments.json` 里有一张 `mood_swing`
    （情绪 → [频率倍率, 幅度倍率]），写得有模有样还带注释，但是
    **生成器不搬运、rig 里没有、引擎不认识**。它完全不起作用，
    等于在 JSON 里写日记 —— 而「生气时尾巴快速甩」「专注时慢而大」
    这两条行为词汇因此从来没交付过，我却按"做完了"报了上去。

    这类 bug 的险恶之处：表在、注释在、文档也写了，静态看一切正常，
    只有去量运行时才看得出来（tools/probe_swing.c：11 种情绪峰峰值全一样）。

    所以设两道闸：
      1. 设计表的每个顶层表名，必须在某个 tools/*.py 里被字面引用（搬运方）；
      2. 对已知要进 rig 的表，直接查 rig.json 里在不在（落地方）。
    """
    section("设计表没有死表（写了没人读）")
    designs = sorted(glob.glob(os.path.join(root, "characters/*/design/attachments.json")))
    srcs = ""
    for f in sorted(glob.glob(os.path.join(root, "tools", "*.py"))):
        with io.open(f, encoding="utf-8") as fh:
            srcs += fh.read()
    for dp in designs:
        tag = os.path.relpath(dp, root)
        t = jsonc(dp)
        for key in t:
            if key.startswith("_"):
                continue
            ok_ = ('"%s"' % key) in srcs or ("'%s'" % key) in srcs
            check("%s：顶层表 %s 有生成器读它" % (tag, key), ok_,
                  "tools/*.py 里有引用" if ok_ else
                  "没有任何 tools/*.py 提到 %r —— 这张表只是注释、运行时"
                  "完全不生效（mood_swing 就是这么漏掉的）" % key)
    # 落地方：这几张表必须出现在 rig 里
    must = ("mood_params", "mood_swing", "tail_flick")
    for rp in sorted(glob.glob(os.path.join(root, "characters/*/forms/*/rig.json"))):
        tag = os.path.relpath(rp, root)
        dp = os.path.join(root, "characters",
                          rp.split(os.sep)[-4], "design", "attachments.json")
        if not os.path.isfile(dp):
            continue
        t = jsonc(dp)
        with io.open(rp, encoding="utf-8") as fh:
            rig = json.load(fh)
        for key in must:
            if key not in t:
                continue
            check("%s：设计表的 %s 落到 rig 里了" % (tag, key), key in rig,
                  "已搬运" if key in rig else
                  "design 里有 %s 但 rig 里没有 —— 生成器漏了搬运这一步" % key)


def check_swing_headroom(root):
    """摆动 + 自发抽动的合计行程，必须装得进参数值域（防 clamp 削平）。

    T45.2f 撞到的事：mood_swing 接通之后，**缩小**倍率（0.5/0.6/0.9）全对，
    **放大**倍率（angry 1.8 / think 2.2）全变成 ×1.00。病根是摆动参数的值域
    照抄了设计表里写的 ±1，而基准幅度本来就顶着 ±1 —— 放大的那一侧直接
    撞墙被 clamp 削平。

    这类 bug 最险的地方是「一半对一半错」：抽查很容易抽到对的那一半当场结案。
    T45.2g 又加了自发抽动（叠加在摆动之上、还带 ±35% 的力度抖动），
    撞墙的风险只会更大，所以把这条算式固化成闸：

        需要的行程 = |bias| + |amp| × max(幅度倍率) + max(抽动幅度) × scale × 1.35

    1.35 是引擎每起一下抽动的力度抖动上界（zrig.c accumulate_tail_flick）。
    """
    section("摆动+抽动装得进参数值域（不会被 clamp 削平）")
    for rp in sorted(glob.glob(os.path.join(root, "characters/*/forms/*/rig.json"))):
        tag = os.path.relpath(rp, root)
        with io.open(rp, encoding="utf-8") as fh:
            rig = json.load(fh)
        msw = rig.get("mood_swing") or {}
        tfl = rig.get("tail_flick") or {}
        if not msw:
            continue
        amul = max([1.0] + [float(v[1]) for k, v in (msw.get("moods") or {}).items()
                            if not k.startswith("_")])
        fmax = max([0.0] + [float(v[2]) for k, v in (tfl.get("moods") or {}).items()
                            if not k.startswith("_")])
        fsc = dict(zip(tfl.get("params") or [], tfl.get("scale") or []))
        chans = {}
        for a in rig.get("actions", []):
            for c in a.get("channels", []):
                t = c.get("target", "")
                if t.startswith("ParamAcc") and t.endswith("Swing"):
                    chans[t] = c
        for pr in rig.get("params", []):
            pid = pr["id"]
            c = chans.get(pid)
            if c is None:
                continue
            bias = float(c.get("bias", 0.0))
            amp = abs(float(c.get("amp", 0.0))) * amul
            fl = fmax * float(fsc.get(pid, 1.0)) * 1.35
            lo, hi = bias - amp - fl, bias + amp + fl
            ok_ = pr["min"] <= lo + 1e-9 and pr["max"] >= hi - 1e-9
            check("%s：%s 的值域装得下摆动+抽动" % (tag, pid), ok_,
                  "需要 [%.3f, %.3f]，值域 [%.3f, %.3f]" % (lo, hi, pr["min"], pr["max"])
                  if ok_ else
                  "需要 [%.3f, %.3f] 但值域只有 [%.3f, %.3f] —— 超出的部分会被 "
                  "clamp 悄悄削平（T45.2f 就是这么漏的，而且只错放大那一半）"
                  % (lo, hi, pr["min"], pr["max"]))

    # 行波延迟：被 ambient 驱动、且绑了形变器的摆动件，**最后一级形变器**必须有 lag。
    # 只认 ParamAcc*Swing 是不够的 —— 裙摆叫 ParamSkirtSway，会漏。
    for rp in sorted(glob.glob(os.path.join(root, "characters/*/forms/*/rig.json"))):
        tag = os.path.relpath(rp, root)
        with io.open(rp, encoding="utf-8") as fh:
            rig = json.load(fh)
        amb_targets = {c.get("target") for c in rig.get("ambient", [])}
        for pr in rig.get("params", []):
            if pr["id"] not in amb_targets:
                continue
            dfm = [b for b in pr.get("binds", []) if "deformer" in b]
            if len(dfm) < 1:
                continue
            # 一级形变器 = 整条一起动，允许（耳朵那种小件）；
            # 两级以上 = 根和梢，最后一级必须带 lag。
            need = dfm[1:] if len(dfm) > 1 else dfm
            # 骨链（S2/S3）之后，"梢"有两种写法：
            #   ① 直接挂一条带 lag 的绑定（老写法，网格自己延迟）；
            #   ② 网格挂在中段骨下面，中段骨带 lag —— 网格跟着骨头的**已延迟**变换走，
            #      再给它自己加一次 lag 就是延迟两次（尾巴会甩得像果冻）。
            # 所以判据是「自己带 lag，或者任何一个祖先带着 lag 被这条参数驱动」。
            _par = {d["id"]: d.get("parent") for d in rig.get("deformers", [])}
            _lagged = {b["deformer"] for b in dfm if b.get("lag")}
            def _inherits_lag(dfid):
                seen = set()
                cur = _par.get(dfid)
                while cur and cur not in seen:
                    if cur in _lagged:
                        return True
                    seen.add(cur)
                    cur = _par.get(cur)
                return False
            bad = [b["deformer"] for b in need
                   if not b.get("lag") and not _inherits_lag(b["deformer"])]
            check("%s：%s 的梢部形变带行波延迟" % (tag, pr["id"]), not bad,
                  "lag=%s" % ", ".join("%.2f" % b.get("lag", 0) for b in need)
                  if not bad else
                  "形变器 %s 没有 lag —— 根和梢会**同相位**被推，"
                  "那是僵硬的钟摆，不是软组织（动画的 wave principle）" % bad)


def check_ambient_sway(root):
    """自主摆动必须挂在 rig 级的 ambient 上，不许挂进某个动作。

    2026-10-17 量出来的事：裙摆和尾巴的自主摆动写成了 `idle` 的动作通道，
    而待机动作有四个会轮换 ——

        动作          裙摆形变    尾巴 rot_deg
        idle          1.1377      7.9751
        sway          0.7019      6.2181
        shift_weight  0.1273      5.8572
        breath        0.0000      3.0466     ← 布料整个冻住

    而且动作通道按"动作内经过时间"求值，一换动作就从 0 重来 ⇒ 相位跳回原点。
    两个毛病同一个根：**环境摆动不属于任何一个动作**。

    这又是 DC41「一个行为多条入口都要验」的翻版：功能只接了一个入口，
    而它看起来是好的 —— 因为 idle 恰好是最常出现的那个入口。
    """
    section("自主摆动挂在 ambient 上（不是挂在某个动作里）")
    for rp in sorted(glob.glob(os.path.join(root, "characters/*/forms/*/rig.json"))):
        tag = os.path.relpath(rp, root)
        with io.open(rp, encoding="utf-8") as fh:
            rig = json.load(fh)
        amb = rig.get("ambient") or []
        # 1) 摆动参数不许出现在任何动作的通道里
        swing = {pr["id"] for pr in rig.get("params", [])
                 if (pr["id"].endswith("Swing") or pr["id"].endswith("Sway"))
                 and any("deformer" in b for b in pr.get("binds", []))}
        if not swing:
            continue
        leaked = sorted({(a["id"], c["target"])
                         for a in rig.get("actions", [])
                         for c in a.get("channels", [])
                         if c.get("target") in swing})
        check("%s：摆动参数没有被挂进动作里" % tag, not leaked,
              "%d 条摆动参数全在 ambient" % len(swing) if not leaked else
              "这些摆动通道挂在动作上，切到别的待机动作就会停："
              + "、".join("%s→%s" % x for x in leaked))
        # 2) ambient 必须覆盖到每一条摆动参数
        covered = {c.get("target") for c in amb}
        miss = sorted(swing - covered)
        check("%s：每条摆动参数都有 ambient 在推" % tag, not miss,
              "%d 条" % len(swing) if not miss else
              "这些参数没人推，等于不会自己动：" + "、".join(miss))
        # 3) 频率不许撞车 —— 全身揺れ物同拍子摆是机械感的第二大来源
        #    （教程：「すべてのパーツが同じ設定だと全部が同じタイミングで揺れて
        #     機械的に見える。軽いものほど揺れやすく、早く収まるように差をつける」）
        freqs = {}
        for c in amb:
            freqs.setdefault(round(float(c.get("freq", 0)), 4), []).append(c["target"])
        # 左右成对的件（ParamEarLAngle / ParamEarRAngle）本来就该同频，豁免。
        # ⚠ 第一版写的是 x.rstrip("LR") —— 而 L 在名字**中间**，rstrip 只削尾部，
        #   一个字符都削不掉，左右耳被判成"撞车"。配对要按位置去字母。
        def _pair_key(x):
            return re.sub(r"(?<=[a-z])[LR](?=[A-Z0-9]|$)", "", x)
        dup = {f: t for f, t in freqs.items() if len(t) > 1
               and len({_pair_key(x) for x in t}) > 1}
        check("%s：各揺れ物的频率是分开调的" % tag, not dup,
              "%d 条 ambient 通道，频率各不相同" % len(amb) if not dup else
              "这些件共用同一个频率、会同拍子摆（机械感）："
              + "；".join("%.3fHz: %s" % (f, "+".join(t)) for f, t in dup.items()))


def check_attach_switch(root):
    """挂件摘戴开关必须真的能摘掉（T45.3 撞出来的类 bug）。

    病根：引擎的 alpha 是**乘性**的 —— zrig.c:2764

        case P_ALPHA: r->p_alpha[part] *= ZC_CLAMP(1.0 + v, 0.0, 1.0); break;

    绑定写 `{"param":"alpha","scale":1.0}` 时 v = 参数值 ∈ [0,1]，
    因子 = clamp(1.0~2.0) **恒为 1**，开关怎么拨都摘不掉，而且不报错、不告警。
    正确配方就写在同一个文件 zrig.c:1305 的注释里：**scale 1 + offset −1**
    ⇒ 透明度 = 参数值。

    这个 bug 从 T45.1（猫尾）起就在，直到 T45.3 做几何检测、需要"摘掉"那一档
    来做差分时才撞出来 —— 没有量化验收就发现不了。所以设闸：
    凡是「0=摘 1=戴」这类开关参数，绑到 alpha 上就必须带 offset=-1。
    """
    section("挂件摘戴开关（alpha 是乘性的，必须带 offset=-1）")
    rigs = sorted(glob.glob(os.path.join(root, "characters/*/forms/*/rig.json")))
    seen = 0
    bad = []
    for rp in rigs:
        with io.open(rp, encoding="utf-8") as fh:
            rig = json.load(fh)
        for prm in rig.get("params", []):
            pid = prm.get("id", "")
            if not pid.startswith("ParamAcc"):
                continue
            for b in prm.get("binds", []):
                if b.get("param") != "alpha":
                    continue
                seen += 1
                if abs(float(b.get("offset", 0.0)) + 1.0) > 1e-9:
                    bad.append("%s→%s offset=%s" % (pid, b.get("part"),
                                                    b.get("offset", 0.0)))
    check("挂件开关的 alpha 绑定都带 offset=-1", not bad,
          "%d 条绑定全部合规" % seen if not bad
          else "这些开关是摆设，拨了也摘不掉：" + "；".join(bad[:6]))
    zr = os.path.join(root, "src", "core", "zrig.c")
    if os.path.isfile(zr):
        with io.open(zr, encoding="utf-8") as fh:
            src = fh.read()
        check("zrig.c 的 alpha 仍是乘性（上面那条闸的依据）",
              "r->p_alpha[part] *= ZC_CLAMP(1.0 + v" in src,
              "zrig.c:2764 一线；语义若改，offset=-1 这条闸要跟着重订")


def check_effects_table(root):
    """声明式特效表（T43.2 / G117）。

    这一节防的是**回退**：G117 的病根是特效的几何/层号/动法写死在 .py 源码里，
    加一种漫符就得照抄一遍代码。迁到 design/effects.json 之后，最容易发生的事
    就是下一个人图省事，又在生成器里塞一行字面量 —— 那张表就名存实亡了。
    所以这里既查表本身的完整性，也**反向查源码里不许再出现那些字面量**。
    """
    section("声明式特效表（T43.2 / G117）")
    tables = sorted(glob.glob(os.path.join(root, "characters/*/design/effects.json")))
    check("有角色声明了特效表", bool(tables),
          "%d 份" % len(tables) if tables else "一份都没有 —— G117 还没迁")
    for tp in tables:
        tag = os.path.relpath(tp, root)
        t = jsonc(tp)
        effs = t.get("effects", [])
        check("%s：effects 非空" % tag, bool(effs), "%d 组" % len(effs))
        for e in effs:
            eid = e.get("id", "?")
            need = ["id", "sprite", "sprite_px", "layer0", "blend", "tags",
                    "anchor", "size_class", "param", "motion", "instances"]
            miss = [k for k in need if k not in e]
            check("%s#%s：字段齐全" % (tag, eid), not miss,
                  "齐" if not miss else "缺 %s" % miss)
            # DC57：剪影外的特效件只能 normal。ADD 保留目标 alpha，
            # 画在透明背景上等于没画（第一版八颗全看不见就是这么来的）。
            check("%s#%s：混合模式是 normal（DC57）" % (tag, eid),
                  e.get("blend") == "normal", "blend=%r" % e.get("blend"))
            inst = e.get("instances", [])
            fr = [i.get("freq") for i in inst]
            check("%s#%s：每片的 freq 两两不同" % (tag, eid),
                  len(set(fr)) == len(fr),
                  "%d 片 %d 个不同频率（相同会跑着跑着对齐成『整齐划一地闪』）"
                  % (len(fr), len(set(fr))))
            sc = e.get("size_class", {})
            used = set(i.get("size") for i in inst)
            bad = sorted(used - set(sc))
            check("%s#%s：每片的 size 都在 size_class 表里" % (tag, eid), not bad,
                  "都在" if not bad else "表外的档位 %s" % bad)
            # 只有**散布型**（一张素材铺很多片，像 ✨）才要求混用档位 ——
            # 一个大小的散布会假。漫符是「一个符号一张图」，就该只有一个大小，
            # 硬要它混档位等于逼着人把 💢 画成大小两个叠在一起。
            if len(inst) >= 3:
                check("%s#%s：尺寸档位混用（官方讲座：一个大小会假）" % (tag, eid),
                      len(used) >= 2, "用了 %s" % sorted(used))

            # ---- 漫符组（有 source = 一个符号一张图，由 make_manpu_parts.py 切）----
            if e.get("source"):
                src = os.path.join(os.path.dirname(tp), "redraw", e["source"])
                check("%s#%s：原图在 design/redraw/ 里" % (tag, eid),
                      os.path.exists(src), e["source"] if os.path.exists(src)
                      else "找不到 %s" % e["source"])
                ramp = e.get("recolor", [])
                check("%s#%s：声明了 recolor 梯度" % (tag, eid), len(ramp) >= 2,
                      "%d 站" % len(ramp))
                ats = [x.get("at") for x in ramp]
                check("%s#%s：recolor 的 at 严格递增" % (tag, eid),
                      all(b > a for a, b in zip(ats, ats[1:])), "at=%s" % ats)
                # D19 / DC55：AI 只出形状，颜色一律按色卡重铺。
                # 梯度上随便混进一个「差不多的」颜色，这条约束就漏了。
                pal = os.path.join(os.path.dirname(tp), "palette.json")
                hexes = set()
                if os.path.exists(pal):
                    hexes = set(c["hex"].upper() for c in jsonc(pal)["colors"])
                off = sorted(set(x["hex"].upper() for x in ramp) - hexes)
                check("%s#%s：recolor 每一站都是色卡上的颜色（D19/DC55）" % (tag, eid),
                      not off, "都在色卡里" if not off else "色卡外的颜色 %s" % off)

    # ★ 反向闸：生成器里不许再出现特效的几何/层号/动法字面量。
    #   这一条比上面所有条都重要 —— 表在不在不要紧，源码里有没有影子配置才要紧。
    gen = os.path.join(root, "tools/make_rig.py")
    gtxt = io.open(gen, encoding="utf-8").read() if os.path.exists(gen) else ""
    code = strip_prose(gtxt)        # 注释和 docstring 都剥掉再查
    banned = [
        ("SPARKLE_LAYER0", "✨ 的起始层号，该在 effects.json 的 layer0"),
        ('f"fx_sparkle_{i}"', "✨ 的部件 id，该由 effects.json 的 id 派生"),
        ('f"ParamSparkle{i}"', "✨ 的参数名，该由 effects.json 的 param.prefix 派生"),
    ]
    hit = ["%s（%s）" % (k, v) for k, v in banned if k in code]
    check("make_rig.py 里不再写死 ✨ 的层号/部件名/参数名", not hit,
          "干净" if not hit else "又有影子配置了：" + "；".join(hit))

    cut = os.path.join(root, "tools/make_star_eye_parts.py")
    ctxt = io.open(cut, encoding="utf-8").read() if os.path.exists(cut) else ""
    ccode = strip_prose(ctxt)
    m = re.search(r"(?m)^SPARKLES\s*=\s*(.+)$", ccode)
    check("make_star_eye_parts.py 的 SPARKLES 是空壳（几何来自表）",
          bool(m) and m.group(1).strip() == "[]",
          "SPARKLES = %s" % (m.group(1).strip() if m else "（找不到）"))
    man = os.path.join(root, "tools/make_manpu_parts.py")
    if os.path.exists(man):
        mtxt = io.open(man, encoding="utf-8").read()
        mcode = strip_prose(mtxt)
        # 漫符切件器唯一该知道的是「怎么键色、怎么重铺」，不该知道任何一种
        # 漫符叫什么、摆哪儿、什么颜色 —— 那些全在 effects.json 里。
        mbad = [k for k in ("fx_sweat", "fx_anger", "fx_gloom", "fx_zzz",
                            "#E0484A", "#9FC4E8", "seg_head\"")
                if k in mcode]
        check("make_manpu_parts.py 里不写死任何一种漫符的名字/颜色",
              not mbad, "干净" if not mbad else "影子配置：%s" % mbad)
        reads = "effects.json" in mtxt and "recolor" in mtxt and "sprite_px" in mtxt
        check("漫符切件器真的会去读 effects.json",
              reads, "会" if reads else "没读表，等于白写")

    check("切件器有 load_effect（真的会去读表）",
          "def load_effect(" in ctxt and "effects.json" in ctxt,
          "有" if "def load_effect(" in ctxt else "没有，等于表白写")


def check_design_sheets(root):
    """参考模板必须成套、而且套准在同一套身体坐标上（2026-10-18 用户第十五问）。

    用户原话：「你先生成参考模板，像短发一样……没有目的的制作你做的太乱了」
    「全身上下都必须和短发一致，除了发型」。

    这是把工序掰回 Live2D 官方那条路：**画师先画完整差分立绘、再拆图层**。
    之前几轮一直在反着做（拿短发成品挖开、贴 AI 单独生成的碎片），
    碎片之间没有共同的几何和光照约束，拼起来必然是一坨（POSTMORTEM_ART 第一层）。

    为什么要设这道闸：
      参考模板的用途是**按同一套坐标切件**，靠的是"同一个像素位置对应同一个
      身体部位"。AI 一张张编辑出来的图，就算提示词里反复写"身体不变"，
      实测仍有 0.4% 的尺度漂移（鞋底差 5px）—— 整图看不出来，切件全错位。
      所以 tools/register_sheets.py 解相似变换把每张套准到短发底图，
      并写 manifest.json 记账；这里静态核对那份台账。
      **sha16 绑死图片内容**：换了图不重跑套准，这项就会红。

    这是静态检查（不依赖 PIL），只读 manifest + 文件哈希。
    """
    section("参考模板成套 + 套准到同一套身体坐标（用户第十五问）")
    import hashlib

    sheet_dirs = sorted(glob.glob(os.path.join(root, "characters/*/design/sheets")))
    check("至少有一个角色有参考模板目录 design/sheets/", bool(sheet_dirs),
          "没有就说明还在用\"挖成品贴碎片\"的老工艺")
    if not sheet_dirs:
        return

    for sd in sheet_dirs:
        who = sd.split(os.sep)[-3]
        mp = os.path.join(sd, "manifest.json")
        if not check(f"{who}：有套准台账 sheets/manifest.json", os.path.exists(mp),
                     "跑 tools/register_sheets.py 生成"):
            continue
        with io.open(mp, encoding="utf-8") as fh:
            man = json.load(fh)

        base = os.path.join(root, man.get("base", ""))
        check(f"{who}：台账指向的短发底图存在", os.path.exists(base), man.get("base", ""))

        ents = man.get("sheets", [])
        by_file = {e["file"]: e for e in ents}
        # 发型 × 兜帽收/戴 必须铺满。短发+兜帽放下 = 底图本身，不单独出图。
        want = []
        for hs in ("twin", "pony", "long"):
            want += [f"sheet_{hs}.png", f"sheet_{hs}_hood.png"]
        want.append("sheet_short_hood.png")
        miss = [w for w in want if w not in by_file]
        check(f"{who}：四种发型 × 兜帽收/戴 的参考模板铺满（7 张 + 底图）",
              not miss, "缺：" + "、".join(miss) if miss else
              f"{len(want)} 张齐（短发+兜帽放下 = 底图本身）")

        lim = float(man.get("leg_diff_max_pct", 3.0))
        canvas = tuple(man.get("canvas", [0, 0]))
        sole = man.get("base_sole_y")
        bad_hash, bad_leg, bad_sole = [], [], []
        for e in ents:
            p = os.path.join(sd, e["file"])
            if not os.path.exists(p):
                bad_hash.append(e["file"] + "(文件没了)")
                continue
            h = hashlib.sha256()
            with open(p, "rb") as fh:
                for blk in iter(lambda: fh.read(1 << 20), b""):
                    h.update(blk)
            if h.hexdigest()[:16] != e.get("sha16"):
                bad_hash.append(e["file"])
            if float(e.get("leg_diff_pct", 99)) > lim:
                bad_leg.append("%s %.2f%%" % (e["file"], e["leg_diff_pct"]))
            if sole is not None and int(e.get("sole_y", -1)) != int(sole):
                bad_sole.append("%s y=%s" % (e["file"], e.get("sole_y")))

        check(f"{who}：台账哈希与磁盘上的图一致（改了图必须重跑套准）",
              not bad_hash, "对不上：" + "、".join(bad_hash) if bad_hash else
              f"{len(ents)} 张全部对上")
        check(f"{who}：每张模板膝盖以下与短发底图的差异 ≤ {lim:.1f}%",
              not bad_leg, "超标：" + "、".join(bad_leg) if bad_leg else
              "最差 %.2f%%" % max([float(e.get("leg_diff_pct", 0)) for e in ents] or [0]))
        check(f"{who}：每张模板的鞋底都落在同一行 y={sole}",
              not bad_sole, "对不齐：" + "、".join(bad_sole) if bad_sole else
              "套准后全部一致，切件可以共用一套坐标")
        check(f"{who}：参考模板画布统一 {canvas[0]}x{canvas[1]}",
              len(canvas) == 2 and canvas[0] > 0 and canvas[1] > 0, str(canvas))


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
        # 笑线剪切必须在链上，且排在「所有会改写 seg_head 的工具」之后、make_rig 之前。
        # 它要擦的是 seg_head 上那条闭合笑线；只要后面还有工具把 AI 重绘回贴到脸上，
        # 笑线就会被重新盖回去，胡须（G107）当场复发。
        i_cut = txt.find("make_mouth_line_cut.py")
        i_eyeline = txt.find("make_eyeline_parts.py")
        i_sidehair = txt.find("make_sidehair_parts.py")
        i_rig = txt.find("make_rig.py")
        check("笑线剪切在重建链上且位置正确",
              i_cut > 0 and i_cut > i_eyeline and i_cut > i_sidehair and i_cut < i_rig,
              f"make_mouth_line_cut.py 偏移 {i_cut}（眼线 {i_eyeline} / 侧发 {i_sidehair} "
              f"/ make_rig {i_rig}）")

    # 路线图不许过期。
    #
    # 2026-10-15 盘点时发现 docs/ROADMAP.md 停在 10-11：一个 T 编号都不提，
    # 还写着「身体分段 ⬜」「嘴待拆 AEIOU」——那时这些早做完了。
    # **一份过期的路线图比没有路线图更坏，因为它看起来是真的。**
    # 所以 ROADMAP 改成和 TASKS 挂钩，由 roadmap_status.py 校验：
    # 每个大项都排进了某个阶段 + 写的进度数字和实际勾选一致。
    rs = os.path.join(root, "tools", "roadmap_status.py")
    if os.path.exists(rs):
        r = subprocess.run([sys.executable, rs, "--root", root],
                           capture_output=True, text=True)
        detail = (r.stderr or r.stdout).strip().replace("\n", " ")[:200]
        check("路线图和任务表对得上（无过期）", r.returncode == 0,
              detail or "ROADMAP 与 TASKS 一致；"
              "对不上就跑 python3 tools/roadmap_status.py --fix")

    # 高清切件（T30.1）：file 和 scale 必须配套，一个件都不许漏。
    #
    # 做法见 tools/make_hires_sprites.py 的文件头：切件链不动坐标，
    # 只在最后一步把每个 sprite 换成 2× 像素，rig 里对应把 scale 乘 0.5。
    # 两件事会悄悄出错，所以必须有闸：
    #   ① file 指向 @2x 但 scale 忘了减半 → 整件放大一倍，画面直接崩；
    #   ② 新增部件后忘了跑高清化 → 那个件在放大时糊，而且只有肉眼能发现。
    # 另外 mask/motion_from 把件两两绑在一起（eye_*_socket 罩 eye_*_base/ball、
    # mouth_mask 罩 mouth_cavity、hair_front 罩 brow_*_ghost），
    # **一个 2× 一个 1× 遮罩就对不上**，所以要求全量，不许挑着做。
    rigp = os.path.join(root, "characters", "xiaoxun", "forms", "teen", "rig.json")
    spd = os.path.join(root, "characters", "xiaoxun", "forms", "teen")
    if os.path.exists(rigp):
        with open(rigp, encoding="utf-8") as fh:
            rj = json.load(fh)
        rparts = [p for p in rj.get("parts", []) if p.get("file")]
        hires = [p for p in rparts if p["file"].endswith("@2x.png")]
        plain = [p for p in rparts if not p["file"].endswith("@2x.png")]
        check("高清切件全量启用（不许一半 2× 一半 1×）",
              not hires or not plain,
              f"{len(hires)} 个用 @2x、{len(plain)} 个还是 1×："
              f"{[p['id'] for p in plain][:4]} —— mask 会对不上"
              if hires and plain else f"{len(hires)} 个全部 @2x")
        bad_scale = []
        for p in hires:
            sc = p.get("scale", 1.0)
            # 要验的是「换成 2× 素材之后几何没变」= scale 恰好是 1× 口径的一半。
            # make_rig 把 1× 口径留在 scale_1x 里（它自己就是从那儿算出来的）。
            # 不能写死"必须等于 0.5"：那隐含假设所有件 1× 的 scale 都是 1.0，
            # 而闪光件是一张素材复制成大中小（1× scale 0.68/0.45），会被误报。
            base = p.get("scale_1x")
            if base is None:
                bad_scale.append((p["id"], "缺 scale_1x（make_rig 没写）"))
                continue
            av = sc if isinstance(sc, list) else [sc]
            bv = base if isinstance(base, list) else [base]
            if len(av) != len(bv) or any(abs(a - b * 0.5) > 1e-6
                                         for a, b in zip(av, bv)):
                bad_scale.append((p["id"], f"{sc} 不是 {base} 的一半"))
        check("用了 @2x 的部件 scale 都减半了", not bad_scale,
              f"没减半的：{bad_scale[:4]} —— file 换了 scale 没换，画面会大一倍"
              if bad_scale else f"{len(hires)} 个都是 1× 口径的一半")
        missing_h, wrong_size = [], []
        for p in rparts:
            f2 = p["file"] if p["file"].endswith("@2x.png") else None
            if not f2:
                continue
            f1 = f2.replace("@2x.png", ".png")
            p1 = os.path.join(spd, f1)
            p2 = os.path.join(spd, f2)
            if not os.path.exists(p2):
                missing_h.append(p["id"]); continue
            if os.path.exists(p1):
                def _wh(fp):
                    with open(fp, "rb") as fh2:
                        return struct.unpack(">II", fh2.read(26)[16:24])
                w1, h1 = _wh(p1)
                w2, h2 = _wh(p2)
                if (w2, h2) != (w1 * 2, h1 * 2):
                    wrong_size.append((p["id"], f"{w1}x{h1}->{w2}x{h2}"))
        check("rig 引用的 @2x 文件都在", not missing_h,
              f"缺：{missing_h[:4]}" if missing_h else f"{len(hires)} 个齐全")
        check("@2x 恰好是 1× 的两倍尺寸", not wrong_size,
              f"对不上：{wrong_size[:3]} —— 不是同一张图放大来的"
              if wrong_size else "尺寸全部 ×2")

    # 超分基准（T30.1）：判据不许被悄悄放宽，高清 sheet 不许和原图脱钩。
    #
    # 背景：T30.1 原来写的是「按源图 1696x2528 重切」，2026-10-15 查下来前提是错的 ——
    # 真正的拆件基准 design_sheet 只有 1024x1536，而那张 1696x2528 是**另一个姿势**的
    # 白底参考图。唯一能拿到真 2x 的路是 Real-ESRGAN anime 超分（DC44）。
    # 能不能直接换基准，全靠 upscale_sheet.py 里那五条判据；判据一松，
    # 44 个部件的坐标就会在"看起来还行"的对齐度上集体漂掉，而且很难再查出来。
    up = os.path.join(root, "tools", "upscale_sheet.py")
    if os.path.exists(up):
        ups = io.open(up, encoding="utf-8").read()
        check("超分验收判据没被放宽（NCC/IoU 门槛 0.97）",
              "iou > 0.97" in ups and "ncc > 0.97" in ups,
              "upscale_sheet.py 的 verify()：两条门槛都必须是 >0.97。"
              "放宽等于允许部件坐标集体漂掉")
        check("超分度量只比两边实心的像素",
              'aA[..., 3] > 200) & (aB[..., 3] > 200' in ups,
              "把透明区算进 NCC 会得到假的『不通过』——"
              "第一版就是这么差点把可行的路否掉的（MAE 61.9 vs 真实 6.35）")
        check("超分模型有 sha256 校验",
              "MODEL_SHA256" in ups and "sha256 对不上" in ups,
              "素材是生成物；拿不认识的权重去生成素材，产物就不可复现了")
    # 高清 sheet 若已生成，必须恰好是原图的 2 倍（不是另画一张）
    design = os.path.join(root, "characters", "xiaoxun", "design")
    base_p = os.path.join(design, "design_sheet_short.png")
    x2_p = os.path.join(design, "design_sheet_short_x2.png")
    if os.path.exists(x2_p) and os.path.exists(base_p):
        def _png_wh(fp):
            with open(fp, "rb") as fh:
                d = fh.read(26)
            return struct.unpack(">II", d[16:24])
        bw, bh = _png_wh(base_p)
        xw, xh = _png_wh(x2_p)
        check("高清 sheet 恰好是原 sheet 的 2 倍",
              xw == bw * 2 and xh == bh * 2,
              f"{bw}x{bh} -> {xw}x{xh}（必须正好 2 倍；"
              f"尺寸对不上说明它不是同一张图超分来的）")

    # 惊讶时不许把瞳孔放大。
    # 2026-10-15 用户实拍反馈「眼球会不自然的变大，看着像个怪物」—— 当时 surprised 挂的是
    # ParamEyeBallForm +1.0，而这个参数在本 rig 里只绑了眼球缩放（sx 0.18 / sy 0.22），
    # 于是虹膜被撑大 18~22%。官方口径相反：shocked = 眼睛开得更大 + 瞳孔**变小**
    # （saltech.llc 的 ParamEyeLWide 条目 / Animaze 手册 ParamEyeLOpen 往 max / r/Live2D 两帖）。
    # 这条闸只认一件事：surprised 的 ParamEyeBallForm 幅度不许为正。
    rig_path = os.path.join(root, "characters", "xiaoxun", "forms", "teen", "rig.json")
    if os.path.exists(rig_path):
        with open(rig_path, encoding="utf-8") as f:
            rigj = json.load(f)
        sp = next((a for a in rigj.get("actions", []) if a.get("id") == "surprised"), None)
        if sp:
            ebf = [c for c in sp.get("channels", []) if c.get("target") == "ParamEyeBallForm"]
            amps = [c.get("amp", 0) for c in ebf]
            check("惊讶不许放大瞳孔", all(v <= 0 for v in amps),
                  "surprised 的 ParamEyeBallForm 幅度 %s（必须 <=0，正值=虹膜被撑大）"
                  % (amps if amps else "无此通道"))

    # 上唇线淡出斜率：参数绑定与 GEO2PARAM 换算表必须是同一个数。
    # 对不上的后果不是报错而是**静默跑偏**——部件级通道换算出来的参数幅度会被
    # 按错误的比例放大或缩小（amp 是除以 scale 的）。
    mr = os.path.join(root, "tools", "make_rig.py")
    if os.path.exists(mr):
        src = open(mr, encoding="utf-8").read()
        m1 = re.search(r'\{"part":\s*"mouth_open",\s*"param":\s*"alpha",\s*"scale":\s*(-?[\d.]+)\}', src)
        m2 = re.search(r'\("mouth_open",\s*"alpha"\):\s*\("ParamMouthOpenY",\s*(-?[\d.]+)\)', src)
        same = bool(m1 and m2) and float(m1.group(1)) == float(m2.group(1))
        check("上唇线淡出斜率两处一致", same,
              f'bind={m1.group(1) if m1 else "缺"} / GEO2PARAM={m2.group(1) if m2 else "缺"}')
        # 斜率必须 <= -1.0，否则满张嘴时上唇线还有残留（-0.9 时剩 10%，就是那两撇小胡子）。
        steep = bool(m1) and float(m1.group(1)) <= -1.0
        check("上唇线满张时能归零", steep,
              f'scale={m1.group(1) if m1 else "缺"}，'
              f'张到 {abs(1.0/float(m1.group(1))):.0%} 时归零' if m1 else "没找到绑定")
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


# ------------------------------------------------------------------ 7.9 语音语感（A52 / T57）
def check_prosody(root):
    """语感表必须真的有高低差，角色必须真的接上，演出引擎自检必须全过。

    用户 2026-10-17：「情绪变化、语气等我听测试台词都没有变化」——
    这三道闸就是防止它再退回"一条直线"。
    """
    section("语音语感：情绪表不平 + 角色接上了 + 演出引擎自检全过（A52/T57）")
    cfg_p = os.path.join(root, "config", "prosody.json")
    if not check("语感表在（config/prosody.json）", os.path.exists(cfg_p), "T57.1 的落点"):
        return
    cfg = jsonc(cfg_p)

    # ① 情绪表不能是平的 —— 平了就等于没有情绪（这正是本轮要修的毛病）
    emos = cfg.get("emotions", {})
    base = emos.get("neutral", {})
    keys = ("rate_pct", "pitch_hz", "volume_pct", "pause_scale")
    diff = [e for e, v in emos.items()
            if e != "neutral" and any(v.get(k) != base.get(k) for k in keys)]
    check("情绪表不是平的", len(emos) >= 8 and len(diff) >= 7,
          f"{len(emos)} 种情绪，{len(diff)} 种与中性不同")

    # ② 克制上限必须在，且数值落在查到的公开区间内（防"为了听出区别而演过头"）
    lim = cfg.get("_restraint", {})
    check("克制上限写了且合理",
          0 < lim.get("max_abs_rate_pct", 0) <= 40
          and 0 < lim.get("max_abs_pitch_hz", 0) <= 60
          and 300 <= lim.get("max_pause_ms", 0) <= 900
          and 0 < lim.get("max_strong_ratio", 0) <= 0.6,
          f"rate≤{lim.get('max_abs_rate_pct')}% pitch≤{lim.get('max_abs_pitch_hz')}Hz "
          f"停顿≤{lim.get('max_pause_ms')}ms 强情绪≤{lim.get('max_strong_ratio')}")

    # ③ 每个角色的 plan.json 若接了语感，profile 必须真的存在
    bad = []
    for plan_p in sorted(glob.glob("characters/*/voice/plan.json", root_dir=root)):
        plan = jsonc(os.path.join(root, plan_p))
        prof = (plan.get("prosody") or {}).get("profile")
        if prof and prof not in cfg.get("profiles", {}):
            bad.append(f"{plan_p}:{prof}")
    check("角色接的语感档都存在", not bad, f"指向不存在的档：{bad[:2]}" if bad else
          "profiles=" + "/".join(cfg.get("profiles", {}).keys()))

    # ④ 演出引擎自检（纯逻辑、不联网）必须全过 —— 含它自己的负向对照
    eng = os.path.join(root, "tools", "voice_prosody.py")
    if check("演出引擎在（tools/voice_prosody.py）", os.path.exists(eng), "T57.2 的落点"):
        r = subprocess.run([sys.executable, eng, "--selftest", "--root", root],
                           capture_output=True, text=True)
        tail = (r.stdout or "").strip().splitlines()[-1:] or [""]
        check("演出引擎自检全过", r.returncode == 0, tail[0].strip())


# --------------------------------------------------- 7c 物理内核 2.0（T47.1）
def check_phys2(root):
    """粒子摆链：参考实现和金标准对得上、两边常量一致、链条参数在官方区间内。

    为什么要这道闸：物理这种东西"看着像在动"根本不算对。差一个系数只是
    "摆得小一点"，眼睛分不出来，但以后导入别人的 physics3.json 就全错。
    所以把 Python 参考实现 + 600 步金标准钉成常设闸（C 侧对拍在 test_core 里）。
    """
    section("物理 2.0：粒子摆链的参考实现与金标准对得上（T47.1）")
    ref = os.path.join(root, "tools", "physics_ref.py")
    gold = os.path.join(root, "tests", "data", "phys2_golden.json")
    hdr = os.path.join(root, "src", "core", "zphys2.h")
    if not check("参考实现在（tools/physics_ref.py）", os.path.exists(ref), "T47.1 的对拍基准"):
        return
    if not check("金标准在（tests/data/phys2_golden.json）", os.path.exists(gold),
                 "C 单测 test_phys2 逐步对拍用的就是它"):
        return
    g = jsonc(gold)
    steps = g.get("steps", [])
    check("金标准够长（≥600 步）", len(steps) >= 600, f"{len(steps)} 步")
    # "在本地存在"不等于"进了库"：.gitignore 的 data/ 曾经把 tests/data/ 一起吞掉，
    # 结果本地全绿、CI 一 checkout 就红。存在性检查必须配一条"真的被 git 跟踪"。
    tracked = set(l for l in git(root, "ls-files", "tests/data").splitlines() if l)
    check("金标准进了库（不是只躺在本地）", "tests/data/phys2_golden.json" in tracked,
          f"tests/data 下被跟踪 {len(tracked)} 个文件")

    # ① 参考实现重算一遍必须和金标准一致（防"改了算法忘了重生成"）
    r = subprocess.run([sys.executable, ref, "--verify"], capture_output=True, text=True,
                       cwd=root)
    tail = (r.stdout or "").strip().splitlines()[-1:] or [""]
    check("参考实现与金标准一致", r.returncode == 0, tail[0].strip())

    # ② C 与 Python 的常量必须一字不差，否则两边算的不是同一个模型
    hs = io.open(hdr, encoding="utf-8").read() if os.path.exists(hdr) else ""
    rs = io.open(ref, encoding="utf-8").read()
    pairs = []
    for name, c_macro, py_name in (("FPS", "ZPHYS2_FPS", "FPS"),
                                   ("空气阻力", "ZPHYS2_AIR_RESISTANCE", "AIR_RESISTANCE"),
                                   ("吸附阈值", "ZPHYS2_THRESHOLD", "THRESHOLD")):
        mc = re.search(r"#define\s+%s\s+([0-9.]+)" % c_macro, hs)
        mp = re.search(r"(?m)^%s\s*=\s*([0-9.]+)" % py_name, rs)
        cv = float(mc.group(1)) if mc else None
        pv = float(mp.group(1)) if mp else None
        if cv is None or pv is None or abs(cv - pv) > 1e-12:
            pairs.append(f"{name} C={cv} py={pv}")
    check("C 与 Python 的物理常量一致", not pairs,
          "；".join(pairs) if pairs else "FPS / 空气阻力 / 吸附阈值 三项都对得上")

    # ③ 链条参数要落在官方区间：Mobility 0.7~0.99、Radius 沿链递减或持平。
    #    金标准自己先受约束，rig 里将来写的 physics2 段也一起查（T47.2 之后会有）。
    chains = [("tests/data/phys2_golden.json", g.get("particles", []))]
    for rig_p in sorted(glob.glob("characters/*/forms/*/rig.json", root_dir=root)):
        rig = jsonc(os.path.join(root, rig_p))
        for ch in (rig.get("physics2") or []):
            chains.append((f"{rig_p}:{ch.get('id', '?')}",
                           [[v.get("radius", 0), v.get("mobility", 0),
                             v.get("delay", 1), v.get("acceleration", 1)]
                            for v in (ch.get("particles") or [])]))
    bad_mob, bad_rad = [], []
    for name, verts in chains:
        prev = None
        for i, v in enumerate(verts):
            if i == 0:
                continue          # 根粒子没有摆长，也不参与积分
            rad, mob = float(v[0]), float(v[1])
            if not (0.7 <= mob <= 0.99):
                bad_mob.append(f"{name}#{i} mobility={mob}")
            if prev is not None and rad > prev + 1e-9:
                bad_rad.append(f"{name}#{i} radius {prev}→{rad} 变长了")
            prev = rad
    check("Mobility 都在 0.7~0.99（官方编辑器的区间）", not bad_mob,
          "；".join(bad_mob[:3]) if bad_mob else f"{len(chains)} 条链")
    check("Radius 沿链递减或持平（根硬梢软）", not bad_rad,
          "；".join(bad_rad[:3]) if bad_rad else "没有越往梢越长的链")


def check_phys2_rig(root):
    """物理 2.0 的**接线**：摆角到底写没写到部件上（T47.2）。

    §7c 守的是"内核算得对"，这一段守的是"接对了地方"：
    算得再准，输出倍率写错、旧摆没删干净、两套内核打在同一个通道上，
    画面照样是错的 —— 而这种错**眼睛看不出来**，只会觉得"怪怪的"。
    """
    section("物理 2.0：摆链接到部件上（T47.2 输出适配层）")
    hdr = os.path.join(root, "src", "core", "zrig.c")
    if not os.path.isfile(hdr):
        return
    src = io.open(hdr, encoding="utf-8").read()
    m = re.search(r"#define\s+ZRIG_MAX_PHYS2\s+(\d+)", src)
    m2 = re.search(r"#define\s+ZRIG_MAX_P2_OUT\s+(\d+)", src)
    cap_ch = int(m.group(1)) if m else 0
    cap_out = int(m2.group(1)) if m2 else 0
    check("引擎声明了摆链上限（超了要报错，不能静默截断）", cap_ch > 0 and cap_out > 0,
          f"ZRIG_MAX_PHYS2={cap_ch} ZRIG_MAX_P2_OUT={cap_out}")

    rigs = sorted(glob.glob("characters/*/forms/*/rig.json", root_dir=root))
    n_chain = 0
    bad_cap, bad_out, bad_root, bad_scale, no_breath, dup = [], [], [], [], [], []
    bad_input = []
    for rig_p in rigs:
        rig = jsonc(os.path.join(root, rig_p))
        pids = {p["id"] for p in rig.get("parts", [])}
        dids = {d["id"] for d in rig.get("deformers", [])}
        chains = rig.get("physics2") or []
        if len(chains) > cap_ch:
            bad_cap.append(f"{rig_p} {len(chains)}>{cap_ch}")
        # 同一个部件同一个通道被两套内核一起写 = 叠加，画面会多摆一倍
        old_ch = {(x.get("part"), x.get("deformer") or x.get("param", "bend_x"))
                  for x in rig.get("physics", [])}
        for ch in chains:
            n_chain += 1
            parts = ch.get("particles") or []
            if not parts or float(parts[0].get("radius", 1)) != 0.0:
                bad_root.append(f"{rig_p}:{ch.get('id')}")
            outs = ch.get("outputs") or []
            if not outs or len(outs) > cap_out:
                bad_cap.append(f"{rig_p}:{ch.get('id')} outputs={len(outs)}")
            for o in outs:
                tgt = o.get("part", ch.get("part"))
                if o.get("deformer"):
                    if o["deformer"] not in dids:
                        bad_out.append(f"{rig_p}:{ch.get('id')}→{o['deformer']}")
                elif tgt not in pids:
                    bad_out.append(f"{rig_p}:{ch.get('id')}→{tgt}")
                if not float(o.get("scale", 1)) or float(o.get("max", 0)) <= 0:
                    bad_scale.append(f"{rig_p}:{ch.get('id')} scale={o.get('scale')} "
                                     f"max={o.get('max')}")
                key = (o.get("deformer") and (tgt, o["deformer"])) or \
                      (tgt, o.get("param", "bend_x"))
                if key in old_ch:
                    dup.append(f"{rig_p}:{ch.get('id')} 和旧摆抢 {key}")
            # ★ T47.2 的那句承诺：呼吸要混进物理输入，静止时才有东西推着它晃。
            srcs = [i.get("param") for i in (ch.get("input") or [])]
            if "ParamBreath" not in srcs:
                no_breath.append(f"{rig_p}:{ch.get('id')}")
            # ★ 2026-10-24（第六十一问）Q 版整份 rig 装不进去的真因：
            #   physics2 的 input/angle_input 点名了一个**本形态没有声明**的参数。
            #   引擎在 zrig.c:1278 逐条校验、指不到就拒绝加载整份 rig，
            #   而 /api/form 照样回 {"ok":true} —— 表现是"切形态没反应"。
            #   新形态永远从"素材缺一半"开始，所以这条必须常设。
            pd = {q["id"] for q in rig.get("params", [])}
            for k in ("input", "angle_input"):
                for one in (ch.get(k) or []):
                    nm = one.get("param")
                    if isinstance(nm, str) and nm not in pd:
                        bad_input.append(f"{rig_p}:{ch.get('id')}.{k}→{nm}")
    check("摆链条数/输出条数都没超引擎上限", not bad_cap, "；".join(bad_cap[:3]) or
          f"{n_chain} 条链")
    check("每条输出都指得到真实的部件或形变器", not bad_out,
          "；".join(bad_out[:3]) or "全部能解析")
    check("每条链的 particles[0] 是根（radius=0，不积分）", not bad_root,
          "；".join(bad_root[:3]) or f"{n_chain} 条链")
    check("倍率非零、限幅为正（倍率 0 = 这条输出白接）", not bad_scale,
          "；".join(bad_scale[:3]) or "全部有效")
    check("没有和旧摆抢同一个通道（两套内核叠加 = 摆双倍）", not dup,
          "；".join(dup[:3]) or "新旧内核各写各的")
    check("每条链都把呼吸混进了物理输入（静止时也活着的唯一来源）", not no_breath,
          "；".join(no_breath[:3]) or f"{n_chain} 条链都接了 ParamBreath")
    check("摆链的输入参数都真的声明过（否则引擎拒载整份 rig、切形态静默失败）",
          not bad_input, "；".join(bad_input[:4]) or f"{n_chain} 条链的输入全部能解析")

    # 迁过去的旧条目必须删干净，不能两份都留着
    teen = os.path.join(root, "characters/xiaoxun/forms/teen/rig.json")
    if os.path.isfile(teen):
        rig = jsonc(teen)
        olds = {x.get("id") for x in rig.get("physics", [])}
        gone = {"ahoge_x", "ahoge_tip", "longhair_x", "longhair_mid_p", "longhair_tip_p"}
        check("迁到物理 2.0 的那几条旧弹簧摆已经删干净", not (olds & gone),
              "还留着：%s" % "、".join(sorted(olds & gone)) if (olds & gone)
              else "呆毛 2 条 + 长发 3 条已换成 2 条粒子链")

    # ---- T47.3 力场 ----
    # 这里盯的两件事都踩过：
    #   ① 重力写成 (0,−1)：官方模型空间 Y 轴向上，我们的像素空间 Y 轴向下。
    #      照抄官方默认值 = 头发朝天上飘，而且是"静态看截图看不出来"的那种错。
    #   ② 风的量纲：内核里 力 = 重力单位向量 × Acceleration + 风，所以风是"几个 g"。
    #      误当成像素写个 30 进去，一帧就把摆吹到输出上限钉死。
    bad_force = []
    for form in ("teen", "chibi"):
        rp = os.path.join(root, "characters/xiaoxun/forms/%s/rig.json" % form)
        if not os.path.isfile(rp):
            continue
        rig = jsonc(rp)
        if not rig.get("physics2"):
            continue
        f = rig.get("forces")
        if not f:
            bad_force.append("%s 没有 forces 段" % form)
            continue
        g = f.get("gravity") or []
        if len(g) != 2 or abs(float(g[0])) > 1e-9 or float(g[1]) <= 0:
            bad_force.append("%s 重力 %s（像素空间 Y 向下，应是 [0, 正数]）" % (form, g))
        bz = f.get("breeze") or {}
        amp = float(bz.get("amp", 0) or 0)
        hz = float(bz.get("hz", 0) or 0)
        if not (0.0 < amp <= 1.5):
            bad_force.append("%s 微风 amp=%s（应在 0~1.5 这个「几个 g」的量纲里，0 = 站着不动就彻底死了）"
                             % (form, amp))
        if not (0.0 < hz <= 2.0):
            bad_force.append("%s 微风 hz=%s（应在 0~2Hz；再高就不是风是抖动）" % (form, hz))
    check("力场段齐全且量纲对（重力向下为正、微风在 0~1.5g）", not bad_force,
          "；".join(bad_force[:3]) or "teen / chibi 两形态的 forces 都对")

    # 引擎上限和闸里的数字必须同源，否则改了引擎闸还在守旧值
    mb = re.search(r"#define\s+ZRIG_BREEZE_MAX\s+([0-9.]+)", src)
    check("引擎声明的微风上限和闸里用的一致", bool(mb) and abs(float(mb.group(1)) - 1.5) < 1e-9,
          "zrig.c 写 %s，闸按 1.5 判" % (mb.group(1) if mb else "没找到"))

    # 符号约定：像素空间 Y 向下，角度读数必须补一次取负，否则风往右吹头发往左飘。
    # 这条是 2026-10-18 的回归 —— 当时 855 条断言全套了 fabs()，一条都没拦住。
    kp = os.path.join(root, "src", "core", "zphys2.c")
    ref = os.path.join(root, "tools", "physics_ref.py")
    if os.path.isfile(kp) and os.path.isfile(ref):
        ks = io.open(kp, encoding="utf-8").read()
        rs = io.open(ref, encoding="utf-8").read()
        check("摆角读数补了坐标系镜像（C 与 Python 参考实现同时补）",
              "return -rad * 180.0 / ZP2_PI;" in ks
              and "-math.degrees(dir_to_radian(" in rs,
              "两边都取负了" if "return -rad * 180.0 / ZP2_PI;" in ks
              else "zphys2_angle 没取负 ⇒ 风往右吹头发会往左飘")


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
               check_web, check_contract, check_attach_switch,
               check_no_dead_tables, check_swing_headroom,
               check_ambient_sway,
               check_effects_table,
               check_prosody,
               check_phys2,
               check_phys2_rig,
               check_design_sheets,
               check_tools, check_hygiene):
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
