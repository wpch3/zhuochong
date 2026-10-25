#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""persona_probe.py —— 让每个角色对「没有标准答案的问题」有自己的答案（T67.44）

为什么要有这个工具
------------------
「世界上最伟大的一个字是什么」这种问题，陪伴产品只有三种做法：

  ① 全网共用一个答案      —— 八个角色异口同声，等于一个人穿了八套衣服；
  ② 每人写死一句台词      —— 也是套皮：换个名字就串台，问第二次一模一样；
  ③ 每人有自己的**立场**，答案由立场和**她自己的经历**推出来
                          —— 会犹豫、会改口、改口说得出为什么变了。

③ 才是"人"。所以这里不存台词，只存两样东西（`characters/<id>/inner.json`）：

    values   立场：一个字 + 为什么 + 这条立场是哪件事撑起来的 + 权重（随关系档变化）
    episodes 经历：时间、地点、发生了什么、当时心里怎么想

答案 = 权重 x 关系档系数的最大值。**同一个人同一档问两次必须一样**（一致才叫有自我），
**不同人必须不一样**（不一样才叫两个人），**改口必须有据**（档位变了，系数变了）。

对外的用法
----------
    python3 tools/persona_probe.py --probe "世界上最伟大的一个字是什么"
    python3 tools/persona_probe.py --check          # 六道闸，红了返回 1
    python3 tools/persona_probe.py --write-fragments # 生成 inner.prompt.<档>.txt
    python3 tools/persona_probe.py --check-fresh     # 片段是否与 inner.json 同步

`inner.prompt.<档>.txt` 是给 C 侧 `zpersona_compose()` 直接拼进系统提示词用的：
C 不认识 JSON 里那套权重，也不该认识 —— 推导只在这里做一份，避免两边漂移。
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
TIERS = 4                       # 关系档 0..3，和 zpersona 的 story.tiers 对齐
FRAG_MAX = 900                  # 片段太长的提示词会稀释别的指令（实测超过 1200 就开始被忽略）
# 不许出现在答案里的"通用大词"：不是禁词，是**不许当答案**——
# 这种字谁都能说，说了等于没说（G66.44）。
GENERIC = ("爱", "心", "情", "光", "梦", "缘", "家")

# 片段里必须有的一句。没有它，模型就会把我们给的立场当台词背出来 ——
# 那和第 ② 种做法没有区别。
NO_RECITE = "不要逐字背上面这些字"


def char_dirs():
    out = []
    for p in sorted(glob.glob(os.path.join(ROOT, "characters", "*", "inner.json"))):
        out.append(os.path.dirname(p))
    return out


def load(cdir):
    with io.open(os.path.join(cdir, "inner.json"), encoding="utf-8") as f:
        return json.load(f)


def _ep(doc, eid):
    for e in doc["episodes"]:
        if e["id"] == eid:
            return e
    return None


def derive(doc, tier):
    """按 权重 x 关系档系数 选一条立场。同样的入参永远得到同样的结果（不掷骰子）。"""
    vals = doc["self"]["values"]
    best, best_score = None, -1.0
    for v in vals:                        # 数据里的书写顺序就是平局时的次序
        bond = v.get("bond") or [1.0] * TIERS
        score = float(v.get("weight", 0.0)) * float(bond[tier])
        if score > best_score:
            best, best_score = v, score
    ep = _ep(doc, best["episode"])
    return {
        "word": best["word"],
        "why": best["why"],
        "value_id": best["id"],
        "episode_id": best["episode"],
        "episode": ep,
        "score": round(best_score, 4),
        "core": doc["self"]["core"],
    }


def fragment(doc, tier):
    """生成给系统提示词的一段话（纯文本，C 侧直接 append）。"""
    cur = derive(doc, tier)
    ep = cur["episode"] or {}
    lines = [
        "【你自己的答案，不是标准答案】",
        "- 你的底色：%s" % cur["core"],
        "- 遇到没有标准答案的问题（比如「世界上最美的一个字是什么」），"
        "先给自己的想法，不要去找通用答案，也不要说得像格言。",
        "- 此刻你会答：「%s」" % cur["word"],
        "  理由：%s" % cur["why"],
        "  撑住这句话的是你自己的记忆（%s，%s）：%s" %
        (ep.get("when", ""), ep.get("where", ""), ep.get("what", "")),
    ]
    if ep.get("felt"):
        lines.append("  当时你心里是：%s" % ep["felt"])
    if tier > 0:
        old = derive(doc, 0)
        if old["word"] != cur["word"]:
            lines.append("- 刚认识那会儿你不会这么答，那时你会说「%s」。"
                         "如果对方问起，可以承认自己变了，说清为什么。" % old["word"])
    lines.append("- 这只是此刻的你。可以犹豫、可以说「我也说不准」，"
                 "但不要为了好听而编一个理由。")
    lines.append("- %s，用自己的话说。" % NO_RECITE)
    return "\n".join(lines) + "\n"


def frag_path(cdir, tier):
    return os.path.join(cdir, "inner.prompt.%d.txt" % tier)


def write_fragments():
    n = 0
    for cdir in char_dirs():
        doc = load(cdir)
        for t in range(TIERS):
            with io.open(frag_path(cdir, t), "w", encoding="utf-8") as f:
                f.write(fragment(doc, t))
            n += 1
    print("已写 %d 个提示词片段（%d 个角色 x %d 档）" % (n, len(char_dirs()), TIERS))
    return 0


# ------------------------------------------------------------------ 六道闸

def _bigrams(s):
    s = re.sub(r"[\s，。、：；「」（）—…·,.\-]", "", s)
    return set(s[i:i + 2] for i in range(max(0, len(s) - 1)))


def _jacc(a, b):
    if not a or not b:
        return 0.0
    return len(a & b) / float(len(a | b))


def check():
    dirs = char_dirs()
    if not dirs:
        print("没有找到任何 inner.json")
        return 2
    docs = {os.path.basename(d): load(d) for d in dirs}
    fails = []

    def bad(code, msg):
        fails.append((code, msg))

    # ---- 闸 1：每一条自己的话都要有出处，每段经历都要用得上
    for cid, doc in docs.items():
        eids = [e["id"] for e in doc["episodes"]]
        if len(set(eids)) != len(eids):
            bad("G1", "%s：episode id 重复" % cid)
        used = []
        for v in doc["self"]["values"]:
            if v["episode"] not in eids:
                bad("G1", "%s：立场「%s」指的 %s 不存在 —— 这是编的"
                    % (cid, v["word"], v["episode"]))
            used.append(v["episode"])
        if len(set(used)) != len(used):
            bad("G1", "%s：两条立场共用一段经历（撑不住两种说法）" % cid)
        for e in doc["episodes"]:
            if not all(e.get(k) for k in ("when", "where", "what", "felt")):
                bad("G1", "%s：经历 %s 有四要素缺项" % (cid, e["id"]))

    # ---- 闸 2：同一个字不许被两个角色拿去当答案（任何档位都算）
    owner = {}
    for cid, doc in docs.items():
        for t in range(TIERS):
            w = derive(doc, t)["word"]
            if w in GENERIC:
                bad("G2", "%s（档%d）：答案「%s」是通用大词，说了等于没说" % (cid, t, w))
            if owner.get(w, cid) != cid:
                bad("G2", "%s 和 %s 都会答「%s」—— 这就是套皮" % (cid, owner[w], w))
            owner[w] = cid

    # ---- 闸 3：理由必须真的不一样（去掉名字后比中文二元组）
    names = set()
    for cid, doc in docs.items():
        names.add(cid)
    pairs = list(docs.items())
    for i in range(len(pairs)):
        for j in range(i + 1, len(pairs)):
            a, b = pairs[i], pairs[j]
            ta = derive(a[1], 0)
            tb = derive(b[1], 0)
            sa = ta["why"] + (ta["episode"] or {}).get("what", "")
            sb = tb["why"] + (tb["episode"] or {}).get("what", "")
            for nm in names | {"小寻", "深语", "闪电", "双晞", "通琳", "拂晓", "星璇", "月见"}:
                sa = sa.replace(nm, "")
                sb = sb.replace(nm, "")
            sim = _jacc(_bigrams(sa), _bigrams(sb))
            if sim > 0.20:
                bad("G3", "%s / %s 的理由重合 %.2f（上限 0.20）" % (a[0], b[0], sim))

    # ---- 闸 4：同一个状态问两次必须一模一样（不掷骰子才叫有自我）
    for cid, doc in docs.items():
        for t in range(TIERS):
            if json.dumps(derive(doc, t), ensure_ascii=False, sort_keys=True) != \
               json.dumps(derive(doc, t), ensure_ascii=False, sort_keys=True):
                bad("G4", "%s（档%d）：同样的输入得到不同答案" % (cid, t))

    # ---- 闸 5：关系档必须真的能改变答案（否则"会变"是假的）
    changed = 0
    for cid, doc in docs.items():
        w0 = derive(doc, 0)["word"]
        for t in range(1, TIERS):
            if derive(doc, t)["word"] != w0:
                changed += 1
                break
    if changed < max(1, len(docs) // 4):
        bad("G5", "只有 %d 个角色会随关系档改口（至少 %d 个）"
            % (changed, max(1, len(docs) // 4)))

    # ---- 闸 6：片段本身（长度、必须有"别背"，且八个人两两不同）
    frags = {}
    for cid, doc in docs.items():
        for t in range(TIERS):
            s = fragment(doc, t)
            frags[(cid, t)] = s
            if len(s) > FRAG_MAX:
                bad("G6", "%s（档%d）：片段 %d 字，超过 %d 会把别的指令稀释掉"
                    % (cid, t, len(s), FRAG_MAX))
            if NO_RECITE not in s:
                bad("G6", "%s（档%d）：片段缺「不要逐字背」—— 模型会把立场当台词念"
                    % (cid, t))
    seen = {}
    for (cid, t), s in frags.items():
        if t != 0:
            continue
        body = re.sub(r"「|」|\d", "", s)
        for prev_cid, prev in seen.items():
            if _jacc(_bigrams(body), _bigrams(prev)) > 0.95:
                bad("G6", "%s 和 %s 的提示词几乎一样" % (cid, prev_cid))
        seen[cid] = body

    # ---- 闸 7：仓库里的片段必须与 inner.json 同步（防止改了数据忘生成）
    for d in dirs:
        cid = os.path.basename(d)
        for t in range(TIERS):
            p = frag_path(d, t)
            want = fragment(docs[cid], t)
            got = io.open(p, encoding="utf-8").read() if os.path.exists(p) else None
            if got != want:
                bad("G7", "%s 的 inner.prompt.%d.txt 过期或缺失 —— 跑 --write-fragments"
                    % (cid, t))

    # ---- 报告
    print("%-10s %-4s %-6s %s" % ("角色", "档", "答案", "理由"))
    print("-" * 78)
    for cid in sorted(docs):
        for t in range(TIERS):
            r = derive(docs[cid], t)
            print("%-10s %-4d 「%s」  %s" % (cid, t, r["word"], r["why"]))
    print("-" * 78)
    print("闸 1 出处 / 2 不撞车 / 3 理由不重合 / 4 同状态同答案 / 5 会改口 / 6 片段 / 7 片段新鲜")
    if fails:
        for code, msg in fails:
            print("  [%s] %s" % (code, msg))
        print("\n内心档案：%d 项不通过" % len(fails))
        return 1
    print("内心档案：%d 个角色 x %d 档，七道闸全过" % (len(docs), TIERS))
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--probe", default="", help="问一句话，看每个角色怎么答")
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--write-fragments", action="store_true")
    ap.add_argument("--check-fresh", action="store_true")
    a = ap.parse_args()

    if a.write_fragments:
        return write_fragments()
    if a.check_fresh:
        dirs = char_dirs()
        stale = 0
        for d in dirs:
            doc = load(d)
            for t in range(TIERS):
                p = frag_path(d, t)
                want = fragment(doc, t)
                got = io.open(p, encoding="utf-8").read() if os.path.exists(p) else None
                if got != want:
                    stale += 1
        print("片段同步：%s" % ("通过" if not stale else "%d 个过期" % stale))
        return 0 if not stale else 1
    if a.probe:
        print("问：%s\n" % a.probe)
        for d in char_dirs():
            doc = load(d)
            r = derive(doc, 0)
            ep = r["episode"] or {}
            print("%-9s 「%s」" % (os.path.basename(d), r["word"]))
            print("           %s" % r["why"])
            print("           （%s，%s：%s）\n"
                  % (ep.get("when", ""), ep.get("where", ""), ep.get("what", "")))
        return 0
    return check()


if __name__ == "__main__":
    sys.exit(main())
