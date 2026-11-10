#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""mind_probe.py —— 让每个角色「想事情的方式」也不一样（T67.58）

为什么不能只做「立场」（persona_probe 做的那部分）
----------------------------------------------------
立场回答的是「世界上最美的一个字是什么」这种**没有代价**的问题。
真人之间的差别，更多时候落在有代价的地方：

    约好的事被临时取消 / 半夜被叫醒 / 被指出做错了 / 你情绪很低但不说话 /
    被人当面开玩笑 / 两分钟内要决定一件影响很久的事

这些情境里，两个人的差别不在"说什么漂亮话"，而在
**先做什么、接着说什么、把什么藏起来、事后怎么收场**。

所以这里存的是**倾向**（`characters/<id>/inner.json` 的 `mind` 块）：

    thinking  怎么想：分析/直觉、整体/拆解、愿不愿意花力气、改不改口、快慢
    decide    怎么定：理性/直觉/问人/回避/冲动 + 风险 + 后悔
    emotion   怎么消化：重评/压住/换场景/转移注意/用玩笑 + 表现强度 + 恢复快慢 + 触发点
    conflict  怎么处理冲突：回避/正面对/安抚/协作/打岔 + 事后怎么办
    attach    关系里的底色：安全/焦虑/回避/混乱
    attention 先看见什么、常常漏掉什么
    memory_bias 记得什么、忘什么
    habits    小动作与语言习惯
    constraints 底线（宁可不说也不越过的两条）

**行为不是写死的台词，是从这些取值推出来的**（本文件 `scenario_action()`）。
同一份数据永远推出同一个结果；换一个人，推出来的顺序就不一样。

对外的用法
----------
    python3 tools/mind_probe.py --probe                 # 八个人 x 六个情境，一张表
    python3 tools/mind_probe.py --probe --scenario plan-broken
    python3 tools/mind_probe.py --check                 # 七道闸
    python3 tools/mind_probe.py --write-fragments       # 生成 inner.mind.txt
    python3 tools/mind_probe.py --check-fresh
"""
from __future__ import annotations

import argparse
import glob
import io
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

FRAG_MAX = 1000          # 一段太长会把别的人设稀释掉
FRAG_MIN = 200
NO_RECITE = "倾向，不是台词"

# ---------------------------------------------------------------- 枚举与取值
STYLE = ("analytic", "intuitive", "integrated")
SPAN = ("wholist", "analytic")
PACE = ("slow", "steady", "fast")
D_STYLE = ("rational", "intuitive", "dependent", "avoidant", "spontaneous")
REG = ("reappraise", "suppress", "situation", "attention", "humor")
SCRIPT = ("avoid", "confront", "appease", "collaborate", "deflect")
ATTACH = ("secure", "anxious", "avoidant", "fearful")
FIRST = ("人", "气氛", "细节", "物件", "声音光")

# 每个轴的"人话"（片段用）
STYLE_W = {
    "analytic": "先拆开、一步步来",
    "intuitive": "先有整体感觉，再补理由",
    "integrated": "先扫全局，再拆关键处",
}
SPAN_W = {"wholist": "看整体和关系", "analytic": "看具体那一块"}
PACE_W = {"slow": "慢，答话前停一下", "steady": "不快不慢", "fast": "快，话比想法先出来"}
D_W = {
    "rational": "要能说出为什么才动",
    "intuitive": "靠直觉，越分析越拿不定",
    "dependent": "先问一句别人的看法",
    "avoidant": "能不动就不动",
    "spontaneous": "先做再想",
}
REG_W = {
    "reappraise": "先给它找个解释",
    "suppress": "收起来，脸上看不出",
    "situation": "去做点手上的事",
    "attention": "把注意力挪开",
    "humor": "用玩笑盖过去",
}
SCRIPT_W = {
    "avoid": "先绕开，等它凉",
    "confront": "当面顶回去",
    "appease": "先让对方下台阶",
    "collaborate": "摆事实一起看",
    "deflect": "打岔嘴硬，但人不会走",
}
ATTACH_W = {
    "secure": "不担心对方会走",
    "anxious": "会轻轻试探你还在不在",
    "avoidant": "别人靠近先退半步",
    "fearful": "想靠近又怕靠近",
}
RECOVER_W = {1: "一会儿就过去", 2: "要小半天", 3: "会压很久"}


def char_dirs():
    return [os.path.dirname(p) for p in
            sorted(glob.glob(os.path.join(ROOT, "characters", "*", "inner.json")))]


def load(cdir):
    with io.open(os.path.join(cdir, "inner.json"), encoding="utf-8") as f:
        return json.load(f)


def mind(doc):
    return doc.get("mind") or {}


# ---------------------------------------------------------------- 情境与推导
# 每个情境给四个槽：先做 / 接着说什么 / 藏起来的是什么 / 事后怎么收场。
# 规则**只读数据**，不读角色名，所以同一套规则对八个人成立。
SCENARIOS = [
    {"id": "plan-broken", "q": "约好的事被临时取消"},
    {"id": "woken", "q": "半夜三点被叫醒"},
    {"id": "blamed", "q": "做错了一件事，被当面指出来"},
    {"id": "silent-low", "q": "你情绪很低，但什么也不说"},
    {"id": "joked-at", "q": "被人当面开玩笑，她不太舒服"},
    {"id": "quick-decision", "q": "两分钟内要决定一件影响很久的事"},
]


def _after(attach):
    return {
        "anxious": "过一会儿试探地问「那你下次还找我吗」",
        "avoidant": "自己待着，不提这件事",
        "secure": "过一会儿主动说「那改天吧」",
        "fearful": "很久以后才轻轻提一句",
    }[attach]


def _after_quiet(attach):
    """回避/混乱型连上面那句都不会说出口 —— 这层差别要在推出来的行为里看得见。"""
    base = _after(attach)
    return base + ("，但不会说出口" if attach in ("avoidant", "fearful") else "")


def scenario_action(m, sid):
    """从倾向推出这个人在这个情境里的行动序列（四句话）。纯函数，无随机。"""
    th, de, em = m["thinking"], m["decide"], m["emotion"]
    cf, at, ai = m["conflict"], m["attach"], m["attention"]
    mb = m["memory_bias"]
    fast = th["pace"] == "fast"
    slow = th["pace"] == "slow"
    vivid = em["express"] >= 0.7
    quiet = em["express"] <= 0.3
    guard = em["regulate"]

    if sid == "plan-broken":
        first = {"confront": "当场问「怎么突然就变了」",
                 "deflect": "先说一句「哦，随便你」，转身去倒水",
                 "avoid": "把话咽回去，只应一声「好」",
                 "appease": "先替对方找理由：「你肯定也有难处」",
                 "collaborate": "先问清楚是哪一步变了"}[cf["script"]]
        say = "直接说不高兴" if vivid else ("说「没事」" if quiet else "嘴上说没事，语气不太像")
        hide = {"reappraise": "已经在心里给这件事换了个说法",
                "suppress": "不高兴收起来，等你问第二遍才讲",
                "situation": "转身去洗东西，手一忙就不想了",
                "attention": "把注意力挪到窗外",
                "humor": "用一句玩笑把话岔开"}[guard]
        after = _after_quiet(at["style"])
    elif sid == "woken":
        first = ("一骨碌爬起来" if fast else
                 ("花了十几秒才反应过来" if slow else "先坐起来，手摸到灯"))
        say = ("先问「怎么了、出什么事了」" if th["style"] == "intuitive"
               else "先问「几点了、你多久没睡了」")
        hide = ("没说自己被吓到了" if guard == "suppress" else
                "把自己的困先放着" if guard == "reappraise" else
                "先笑一下缓和气氛" if guard == "humor" else
                "先去倒杯水" if guard == "situation" else "先听你说完")
        after = ("天亮以后会把这件事再提一次" if th["effort"] >= 0.7 else
                 "第二天就当没发生过")
    elif sid == "blamed":
        first = {"avoid": "先低头，不解释", "confront": "先反驳「不是那样的」",
                 "appease": "先说「对不起，是我没想周全」",
                 "collaborate": "先把事实按顺序讲一遍",
                 "deflect": "先笑一下，把话岔开"}[cf["script"]]
        say = ("认错认得很快，但心里在过一遍" if de["regret"] >= 0.6 else
               "认错，但会顺便说清哪一部分不是自己的问题" if de["regret"] >= 0.4 else
               "嘴上认，心里不服")
        hide = ("憋着不服" if guard == "suppress" else
                "已经在想怎么补救" if guard == "reappraise" else
                "想找个地方待一会儿" if guard == "situation" else
                "把注意力挪开，先不看你" if guard == "attention" else
                # 用玩笑盖过去的人，盖的动机不一样：怕失去 vs 怕难堪
                ("先道一句歉，怕你真的不高兴" if at["style"] == "anxious" else
                 "先低头，心里怕你因此不喜欢我" if at["style"] == "fearful" else
                 "用玩笑把难堪盖过去"))
        after = ("事后会反复想这句话" if de["regret"] >= 0.6 else
                 "事情说完就过去了" if cf["after"].find("翻篇") >= 0 else
                 "会记着，但不会再提")
    elif sid == "silent-low":
        first = ("先看你一眼，什么都不问" if ai["first"] == "气氛" else
                 "先去倒杯水放到你手边" if ai["first"] == "人" else
                 "先注意到你哪里和平时不一样" if ai["first"] == "细节" else
                 "先把房间里的声音弄小一点")
        say = ("直接问「你今天怎么了」" if vivid else
               "说「不想说就不说，我在」" if not quiet else
               "什么也不说，就在旁边坐着")
        hide = ("自己也跟着沉下去" if at["style"] == "anxious" else
                "怕问多了你会烦" if at["style"] == "avoidant" else
                "担心自己是不是做错了什么" if at["style"] == "fearful" else
                "其实也不太会安慰人")
        after = ("会记住你今天是这样" if mb["keeps"].find("习惯") >= 0 else
                 "过两天再试探一次")
    elif sid == "joked-at":
        first = {"confront": "当面把玩笑顶回去", "avoid": "笑一下，把话咽下去",
                 "appease": "跟着笑，替对方圆一下",
                 "collaborate": "笑着说「这个不太好笑」，把线划出来",
                 "deflect": "回一个更响的嘴，把场子抢回来"}[cf["script"]]
        say = ("直接说「我不喜欢这个」" if vivid else
               "什么也不说" if quiet else "说「行吧」，语气有点硬")
        hide = ("被戳到了，但不承认" if guard == "suppress" else
                "已经给自己找了理由：他不是故意的" if guard == "reappraise" else
                "心里过不去，会记一阵" if em["recover"] >= 3 else "很快就过去了")
        after = _after(at["style"])
    elif sid == "quick-decision":
        first = {"spontaneous": "先答应下来，细节回头再说",
                 "rational": "先问三个关键的条件",
                 "dependent": "先问「你觉得呢」",
                 "avoidant": "先说「让我想一下」，把时间往后拖",
                 "intuitive": "闭一下眼，凭第一反应"}[de["style"]]
        say = ("说「就这个吧」" if de["risk"] >= 0.6 else
               "说「如果条件是这样，我就选它」" if de["risk"] >= 0.35 else
               "说「我能不能明天给你答复」")
        hide = ("怕选错，但不会说出来" if de["regret"] >= 0.6 else
                "已经在算最坏的情况" if th["style"] == "analytic" else
                "其实心里已经有答案了")
        after = ("选完会反复复盘" if de["regret"] >= 0.6 else
                 "选完就不再看" if de["regret"] <= 0.2 else
                 "过一阵确认一次")
    else:
        raise KeyError(sid)
    return [first, say, hide, after]


def action_signature(m, sid):
    return "|".join(scenario_action(m, sid))


# ---------------------------------------------------------------- 片段
# ★ 中文一个字符 3 字节，1000 字节只有 330 来个字。
#   所以这里不写"完整的解释"，只写**能约束行为的最短一句**：
#   每行都得能改变她遇到事时的做法，否则就是在稀释提示词。
def fragment(doc):
    m = mind(doc)
    th, de, em = m["thinking"], m["decide"], m["emotion"]
    cf, at, ai = m["conflict"], m["attach"], m["attention"]
    mb = m["memory_bias"]
    open_w = ("新说法你认真考虑" if th["openness"] >= 0.7
              else ("新说法先顶回去，过一阵才消化" if th["openness"] < 0.5
                    else "新说法听着，自己想通才认"))
    effort_w = ("愿意花力气" if th["effort"] >= 0.7
                else ("不爱花力气" if th["effort"] < 0.45 else "愿意想但不绕太久"))
    risk_w = "敢赌" if de["risk"] >= 0.6 else ("不太敢冒" if de["risk"] < 0.35 else "看情况")
    regret_w = "失手会反复想" if de["regret"] >= 0.6 else "失手不回头"
    show_w = ("藏不太住" if em["express"] >= 0.7
              else ("基本看不出" if em["express"] <= 0.3 else "看得出一点"))
    lines = [
        "【你这个人怎么运转】",
        "- 想事：%s；%s；%s。" % (STYLE_W[th["style"]], SPAN_W[th["span"]], PACE_W[th["pace"]]),
        "- 改口：%s；%s。" % (open_w, effort_w),
        "- 拿主意：%s；%s，%s。" % (D_W[de["style"]], risk_w, regret_w),
        "- 情绪：%s；%s，%s。戳点：%s。" % (REG_W[em["regulate"]], show_w,
                                          RECOVER_W[int(em["recover"])], em["trigger"]),
        "- 冲突：%s；%s。关系里：%s。" % (SCRIPT_W[cf["script"]], cf["after"],
                                        ATTACH_W[at["style"]]),
        "- 先看见：%s；常漏：%s。" % (ai.get("first_note", ai["first"]), ai["misses"]),
        "- 记得：%s；忘掉：%s。" % (mb["keeps"], mb["loses"]),
        "- 小动作：%s。底线：%s。" % ("；".join(m["habits"]), "；".join(m["constraints"])),
        "【用法】上面是%s：遇到具体事按情形做，别照念，也别把这段说出来。" % NO_RECITE,
    ]
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------- 节奏参数（T69.1）
# 「脱口而出还是先想一想」由引擎决定（src/core/zthink.c），但**她有多快**来自这里。
# C 侧不认识 inner.json 里那套结构，也不该认识 —— 推导只做一份，避免两边漂移。
PACE_FAST = {"fast": 0.85, "steady": 0.5, "slow": 0.2}


def params_of(doc):
    """把 mind 块压成五个 0~1 的数。每个数都要能说出是从哪个字段来的。"""
    m = mind(doc)
    th, em = m["thinking"], m["emotion"]
    at = m["attach"]["style"]
    cf = m["conflict"]["script"]
    # 主动倾向：愿意先说的人有两种 —— 不怕被拒的（安全型）和憋不住的（正面冲突型）。
    # 回避型/混乱型会把这份倾向压下去，这和"她其实想说话但不敢开口"是同一件事。
    pro = 0.35
    pro += {"anxious": 0.15, "secure": 0.08, "avoidant": -0.10, "fearful": -0.05}[at]
    pro += {"confront": 0.15, "deflect": 0.05, "collaborate": 0.05,
            "appease": 0.02, "avoid": -0.12}[cf]
    if em["express"] >= 0.7:
        pro += 0.10
    elif em["express"] <= 0.3:
        pro -= 0.05
    pro = max(0.0, min(1.0, round(pro, 2)))
    return {
        "character": None,
        "pace_fast": PACE_FAST[th["pace"]],
        "effort": round(float(th["effort"]), 2),
        "express": round(float(em["express"]), 2),
        "proactive": pro,
        "curiosity": round(float(th["openness"]), 2),
    }


def params_path(cdir):
    return os.path.join(cdir, "mind.params.json")


def export_params(cdir, doc):
    p = params_of(doc)
    p["character"] = os.path.basename(cdir)
    p["_from"] = ("由 tools/mind_probe.py 从 inner.json 的 mind 块导出："
                  "pace_fast←thinking.pace / effort←thinking.effort / express←emotion.express / "
                  "proactive←依恋+冲突脚本+外显 / curiosity←thinking.openness")
    with io.open(params_path(cdir), "w", encoding="utf-8") as f:
        json.dump(p, f, ensure_ascii=False, indent=2)
        f.write("\n")
    return p


def frag_path(cdir):
    return os.path.join(cdir, "inner.mind.txt")


def write_fragments():
    n = 0
    for cdir in char_dirs():
        doc = load(cdir)
        with io.open(frag_path(cdir), "w", encoding="utf-8") as f:
            f.write(fragment(doc))
        export_params(cdir, doc)
        n += 1
    print("已写 %d 个思维片段（inner.mind.txt）+ %d 份节奏参数（mind.params.json）" % (n, n))
    return 0


# ---------------------------------------------------------------- 七道闸
def _bigrams(s):
    s = re.sub(r"[\s，。、：；「」（）—…·,.!？?\-]", "", s)
    return set(s[i:i + 2] for i in range(max(0, len(s) - 1)))


def _jacc(a, b):
    if not a or not b:
        return 0.0
    return len(a & b) / float(len(a | b))


# 每条轴：路径 / 允许取值 / 八个人里至少要出现几种。
# span（整体-分析）天生只有两端，要求 3 种等于逼人编数据 —— 这里写 2 是故意的。
AXES = (
    ("thinking.style", STYLE, 2), ("thinking.span", SPAN, 2), ("thinking.pace", PACE, 3),
    ("decide.style", D_STYLE, 3), ("emotion.regulate", REG, 3),
    ("conflict.script", SCRIPT, 3), ("attach.style", ATTACH, 3),
    ("attention.first", FIRST, 3),
)


def _get(m, path):
    cur = m
    for k in path.split("."):
        cur = (cur or {}).get(k)
    return cur


def _unit(v):
    return isinstance(v, (int, float)) and 0.0 <= float(v) <= 1.0


def check():
    dirs = char_dirs()
    docs = {os.path.basename(d): load(d) for d in dirs}
    fails = []

    def bad(code, msg):
        fails.append((code, msg))

    # ---- 闸 1：结构。缺项、越界、枚举外的值，一律红
    for cid, doc in docs.items():
        m = mind(doc)
        if not m:
            bad("M1", "%s：没有 mind 块" % cid)
            continue
        for path, allowed, _min in AXES:
            v = _get(m, path)
            if v not in allowed:
                bad("M1", "%s：%s = %r 不在 %s 里" % (cid, path, v, "/".join(allowed)))
        for path in ("thinking.openness", "thinking.effort", "decide.risk",
                     "decide.regret", "emotion.express"):
            if not _unit(_get(m, path)):
                bad("M1", "%s：%s 必须是 0~1 的数" % (cid, path))
        if _get(m, "emotion.recover") not in (1, 2, 3):
            bad("M1", "%s：emotion.recover 必须是 1/2/3" % cid)
        for path in ("thinking.note", "decide.note", "emotion.note",
                     "emotion.trigger", "attention.misses", "memory_bias.keeps",
                     "memory_bias.loses", "conflict.after"):
            if not (_get(m, path) or "").strip():
                bad("M1", "%s：%s 是空的（说明没想清楚）" % (cid, path))
        if len(m.get("habits") or []) < 2:
            bad("M1", "%s：习惯至少两条" % cid)
        if len(m.get("constraints") or []) < 2:
            bad("M1", "%s：底线至少两条" % cid)
        diel = m.get("diel")
        if diel:
            for part in ("day", "night"):
                if part not in diel:
                    bad("M1", "%s：diel 缺 %s" % (cid, part))
                elif diel[part].get("pace") not in (None,) + PACE:
                    bad("M1", "%s：diel.%s.pace 不合法" % (cid, part))

    # ---- 闸 2：多样性。每个枚举轴至少 3 种取值；任意两人至少 5 个轴不同
    for path, _allowed, need in AXES:
        vals = set(_get(m, path) for m in (mind(d) for d in docs.values()))
        if len(vals) < need:
            bad("M2", "轴 %s 只有 %d 种取值（%s），至少要 %d 种 —— 挤在一起就是套皮"
                % (path, len(vals), "/".join(str(v) for v in vals), need))
    numeric = ("thinking.openness", "thinking.effort", "decide.risk",
               "decide.regret", "emotion.express")
    ids = sorted(docs)
    for i in range(len(ids)):
        for j in range(i + 1, len(ids)):
            a, b = mind(docs[ids[i]]), mind(docs[ids[j]])
            diff = 0
            for path, _a, _n in AXES:
                if _get(a, path) != _get(b, path):
                    diff += 1
            for path in numeric:
                if abs(float(_get(a, path)) - float(_get(b, path))) >= 0.15:
                    diff += 1
            if diff < 5:
                bad("M2", "%s 和 %s 只有 %d 个轴不同（至少要 5 个）" % (ids[i], ids[j], diff))

    # ---- 闸 3：自洽。有些组合是说不通的，必须当场拦住
    for cid, doc in docs.items():
        m = mind(doc)
        em, th, de = m.get("emotion", {}), m.get("thinking", {}), m.get("decide", {})
        if em.get("express", 0) >= 0.7 and em.get("regulate") == "suppress":
            bad("M3", "%s：又「压住」又「藏不太住」—— 这两个说法互相打脸" % cid)
        if th.get("effort", 0) >= 0.8 and de.get("style") == "spontaneous":
            bad("M3", "%s：愿意花力气想，却总是先做再想" % cid)
        if th.get("pace") == "fast" and de.get("style") == "avoidant":
            bad("M3", "%s：反应快的人不太可能事事拖着不做" % cid)
        if th.get("openness", 0) >= 0.75 and m.get("conflict", {}).get("script") == "deflect":
            bad("M3", "%s：愿意改口的人不会一有冲突就打岔带过" % cid)

    # ---- 闸 4：行为可推。同一情境八个人至少四种不同做法；同一人重复必须一致
    for sc in SCENARIOS:
        sigs = {}
        for cid, doc in docs.items():
            m = mind(doc)
            if not m:
                continue
            sig = action_signature(m, sc["id"])
            if sig != action_signature(m, sc["id"]):
                bad("M4", "%s / %s：同样的数据推出两种做法" % (cid, sc["id"]))
            sigs.setdefault(sig, []).append(cid)
        if len(sigs) < 4:
            bad("M4", "情境「%s」八个人只有 %d 种做法（至少 4 种）" % (sc["q"], len(sigs)))

    # ---- 闸 5：不许把答案写成台词。推出来的四句话不许在数据里逐字出现
    for cid, doc in docs.items():
        m = mind(doc)
        if not m:
            continue
        blob = json.dumps(m, ensure_ascii=False)
        for sc in SCENARIOS:
            for line in scenario_action(m, sc["id"]):
                if line and line in blob:
                    bad("M5", "%s：%s 的推断「%s」在数据里逐字存在 —— 那是台词，不是倾向"
                        % (cid, sc["id"], line))

    # ---- 闸 6：片段本身
    frags = {}
    for cid, doc in docs.items():
        if not mind(doc):
            continue
        s = fragment(doc)
        frags[cid] = s
        if len(s.encode("utf-8")) > FRAG_MAX:
            bad("M6", "%s：片段 %d 字节，超过 %d" % (cid, len(s.encode("utf-8")), FRAG_MAX))
        if len(s.encode("utf-8")) < FRAG_MIN:
            bad("M6", "%s：片段只有 %d 字节，信息太少" % (cid, len(s.encode("utf-8"))))
        if NO_RECITE not in s:
            bad("M6", "%s：片段缺「倾向，不是台词」—— 模型会把倾向当台词念" % cid)
    ids = sorted(frags)
    for i in range(len(ids)):
        for j in range(i + 1, len(ids)):
            sim = _jacc(_bigrams(frags[ids[i]]), _bigrams(frags[ids[j]]))
            if sim > 0.60:
                bad("M6", "%s 和 %s 的片段重合 %.2f（上限 0.60）" % (ids[i], ids[j], sim))

    # ---- 闸 7：仓库里的 inner.mind.txt 必须与 inner.json 同步
    for cid, doc in docs.items():
        p = frag_path(os.path.join(ROOT, "characters", cid))
        want = fragment(doc) if mind(doc) else None
        got = io.open(p, encoding="utf-8").read() if os.path.exists(p) else None
        if mind(doc) and got != want:
            bad("M7", "%s 的 inner.mind.txt 过期或缺失 —— 跑 --write-fragments" % cid)
        if not mind(doc) and got is not None:
            bad("M7", "%s 没有 mind 块却有 inner.mind.txt（会拼进提示词）" % cid)

    # ---- 闸 8：节奏参数（T69.1）必须与 inner.json 同步。
    #      C 侧靠这份参数决定"她多快"，它一旦过期，人物的快慢就和人设脱节了 ——
    #      而画面/对话里完全看不出来，只能靠这道闸。
    for cid, doc in docs.items():
        if not mind(doc):
            continue
        want = params_of(doc)
        p = params_path(os.path.join(ROOT, "characters", cid))
        got = None
        if os.path.exists(p):
            try:
                got = json.load(io.open(p, encoding="utf-8"))
            except Exception:                       # noqa: BLE001
                got = None
        if got is None:
            bad("M8", "%s 缺 mind.params.json —— 跑 --write-fragments" % cid)
            continue
        for k, v in want.items():
            if k == "character":
                continue
            if abs(float(got.get(k, -9)) - float(v)) > 1e-6:
                bad("M8", "%s 的 %s 过期：文件 %r / 数据 %r"
                    % (cid, k, got.get(k), v))

    # ---- 报告
    print("== 六个情境：八个人各自先做什么 ==")
    for sc in SCENARIOS:
        print("\n【%s】" % sc["q"])
        for cid in sorted(docs):
            m = mind(docs[cid])
            if not m:
                continue
            acts = scenario_action(m, sc["id"])
            print("  %-9s %s → %s" % (cid, acts[0], acts[3]))
    print("\n" + "-" * 78)
    print("闸 1 结构 / 2 多样性 / 3 自洽 / 4 行为可推 / 5 不许写死台词 / 6 片段 / 7 片段新鲜"
          " / 8 节奏参数同步")
    print("片段字节：" + "  ".join("%s=%d" % (cid, len(frags[cid].encode("utf-8")))
                                for cid in sorted(frags)))
    if fails:
        for code, msg in fails:
            print("  [%s] %s" % (code, msg))
        print("\n思维档案：%d 项不通过" % len(fails))
        return 1
    print("思维档案：%d 个角色 x %d 个轴，八道闸全过（含节奏参数与 inner.json 同步）"
          % (len(docs), len(AXES)))
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--probe", action="store_true")
    ap.add_argument("--scenario", default="")
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--write-fragments", action="store_true")
    ap.add_argument("--check-fresh", action="store_true")
    a = ap.parse_args()

    if a.write_fragments:
        return write_fragments()
    if a.check_fresh:
        stale = 0
        for d in char_dirs():
            doc = load(d)
            p = frag_path(d)
            want = fragment(doc) if mind(doc) else None
            got = io.open(p, encoding="utf-8").read() if os.path.exists(p) else None
            if want != got:
                stale += 1
        print("思维片段同步：%s" % ("通过" if not stale else "%d 个过期" % stale))
        return 0 if not stale else 1
    if a.probe:
        want = [s for s in SCENARIOS if not a.scenario or s["id"] == a.scenario]
        if not want:
            print("没有这个情境：%s（可用：%s）"
                  % (a.scenario, " / ".join(s["id"] for s in SCENARIOS)))
            return 2
        for sc in want:
            print("\n【%s】" % sc["q"])
            for d in char_dirs():
                m = mind(load(d))
                if not m:
                    continue
                acts = scenario_action(m, sc["id"])
                print("  %-9s 先：%s" % (os.path.basename(d), acts[0]))
                print("  %-9s 说：%s" % ("", acts[1]))
                print("  %-9s 藏：%s" % ("", acts[2]))
                print("  %-9s 后：%s" % ("", acts[3]))
        return 0
    return check()


if __name__ == "__main__":
    sys.exit(main())
