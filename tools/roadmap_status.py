#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""roadmap_status.py —— 让 docs/ROADMAP.md 没法悄悄过期。

为什么需要它
------------
2026-10-15 盘点时发现 `docs/ROADMAP.md` 停在 2026-10-11：**一个 T 编号都不提**，
里面还写着「身体分段 ⬜」「嘴 待拆 AEIOU」——而那时这些早就做完了。
一份过期的路线图比没有路线图更坏，因为它看起来是真的。

散文式的路线图必然过期。所以这一版 ROADMAP 改成**和 TASKS 挂钩**：
每个阶段列出它包含的 T 编号和进度数字，由本脚本校验数字是否属实。

它检查四件事
------------
  1. TASKS 里的每个大项（T<n>）都在 ROADMAP 里排进了某个阶段
     —— 漏掉的就是「有任务但没排期」，正是「计划被忘掉」的样子。
  2. ROADMAP 提到的每个 T 编号在 TASKS 里确实存在（防止排了不存在的期）。
  3. ROADMAP 里写的每个 `完成/总数` 数字和 TASKS 的实际勾选一致。
  4. 总进度那一行的三个数字（总项数 / 完成 / 进行中）也一致。

用法
----
    python3 tools/roadmap_status.py           # 只检查，不改文件；有问题退出码 1
    python3 tools/roadmap_status.py --fix     # 把对不上的数字就地改对
    python3 tools/roadmap_status.py --print   # 打印当前真实进度表（给人看）

被 `tools/selfcheck_repo.py :: check_roadmap` 调用。
"""
from __future__ import annotations

import argparse
import io
import os
import re
import sys
from collections import defaultdict

TASKS = "docs/memory/TASKS.md"
ROADMAP = "docs/ROADMAP.md"

# 这些大项已完成或是纯标记，不强制出现在阶段表里（但仍可出现）
# —— 留空：目前所有大项都要求排期。加白名单前先想清楚为什么。
EXEMPT: set[str] = set()


def task_stats(root: str):
    """统计 TASKS.md 每个大项的 (完成, 进行中, 待办)。

    表格行形如：  | T30.1 | 说明 | [x] | 备注 |
    状态只认 [x] / [~] / [ ] 三种。
    """
    p = os.path.join(root, TASKS)
    txt = io.open(p, encoding="utf-8").read()
    rows = re.findall(r"^\|\s*T(\d+)[\d.]*[a-z]?\s*\|[^|]*\|\s*\[([ x~])\]\s*\|",
                      txt, re.M)
    g: dict[str, list[int]] = defaultdict(lambda: [0, 0, 0])
    for top, st in rows:
        g["T" + top][{"x": 0, "~": 1, " ": 2}[st]] += 1
    # 大项标题也算存在（即使还没有表格行）
    for m in re.findall(r"^#+\s*(T\d+)\b", txt, re.M):
        g.setdefault(m, [0, 0, 0])
    return g


def roadmap_text(root: str) -> str:
    return io.open(os.path.join(root, ROADMAP), encoding="utf-8").read()


def check(root: str, fix: bool = False):
    """返回 (problems, fixed_text or None)。"""
    g = task_stats(root)
    txt = roadmap_text(root)
    orig = txt
    problems: list[str] = []

    # ---- 1. 覆盖：TASKS 的大项都要在 ROADMAP 里出现 ----
    # 排除 T0：记忆分层曾用 T0~T3 命名，和任务编号撞车，已统一改成 L0~L3。
    mentioned = {"T" + m for m in re.findall(r"\bT(\d+)", txt) if m != "0"}
    missing = sorted((set(g) - mentioned) - EXEMPT,
                     key=lambda x: int(x[1:]))
    if missing:
        problems.append(f"TASKS 里有但 ROADMAP 没排期：{missing}"
                        " —— 这就是「有任务但没人安排」")

    # ---- 2. 反向：ROADMAP 提到的 T 要真的存在 ----
    ghost = sorted(mentioned - set(g), key=lambda x: int(x[1:]))
    if ghost:
        problems.append(f"ROADMAP 排了 TASKS 里不存在的任务：{ghost}")

    # ---- 3. 每个 `| **T30** | ... | 4/11 |` 的数字要对 ----
    def fix_row(m: re.Match) -> str:
        tid, mid, done, total = m.group(1), m.group(2), int(m.group(3)), int(m.group(4))
        st = g.get(tid)
        if st is None:
            return m.group(0)
        d, i, w = st
        real_total = d + i + w
        if (done, total) != (d, real_total):
            problems.append(f"{tid} 进度写的是 {done}/{total}，实际 {d}/{real_total}")
            if fix:
                return f"| {mid}{tid}{m.group(5)}{m.group(6)}| {d}/{real_total} |"
        return m.group(0)

    row_re = re.compile(
        r"^\|\s*(?:(\*\*)?)(T\d+)(\*\*)?(?!\.)([^|]*)\|([^|]*)\|\s*(\d+)/(\d+)\s*\|", re.M)

    # 用更直接的写法重新匹配（上面的分组容易错位）
    def repl(m: re.Match) -> str:
        bold_open, tid, bold_close, rest1, col2, done, total = m.groups()
        st = g.get(tid)
        if st is None:
            return m.group(0)
        d, i, w = st
        rt = d + i + w
        if (int(done), int(total)) != (d, rt):
            problems.append(f"  {tid} 写 {done}/{total}，实际 {d}/{rt}")
            if fix:
                head = f"| {bold_open or ''}{tid}{bold_close or ''}{rest1}|{col2}|"
                return f"{head} {d}/{rt} |"
        return m.group(0)

    txt = row_re.sub(repl, txt)

    # ---- 4. 阶段汇总 `| **M1** | 立绘站得住 | 18/69 |` ----
    #    阶段包含哪些 T：从该阶段小节的表格里取
    stage_tasks: dict[str, set[str]] = {}
    for sm in re.finditer(r"^## (M\d+) (.+?)$(.*?)(?=^## |\Z)", txt, re.M | re.S):
        sid, body = sm.group(1), sm.group(3)
        stage_tasks[sid] = {"T" + x for x in re.findall(r"^\|\s*\**(?:T)(\d+)", body, re.M)}

    def stage_repl(m: re.Match) -> str:
        sid, name, done, total = m.group(1), m.group(2), int(m.group(3)), int(m.group(4))
        ts = stage_tasks.get(sid)
        if not ts:
            return m.group(0)
        d = sum(g[t][0] for t in ts if t in g)
        rt = sum(sum(g[t]) for t in ts if t in g)
        if (done, total) != (d, rt):
            problems.append(f"  阶段 {sid} 写 {done}/{total}，实际 {d}/{rt}")
            if fix:
                bold = "**" if m.group(0).lstrip("| ").startswith("**") else ""
                return f"| {bold}{sid}{bold} |{name}| {d}/{rt} |"
        return m.group(0)

    # 加粗与不加粗都要盖到 —— 第一版只写了 \*\*M\d+\*\*，结果 8 个阶段只校验了 M1 一个，
    # 看着绿其实没管住。这类"正则只匹配到一部分"的闸最危险。
    txt = re.sub(r"^\|\s*\*{0,2}(M\d+)\*{0,2}\s*\|([^|]*)\|\s*(\d+)/(\d+)\s*\|",
                 stage_repl, txt, flags=re.M)

    # ---- 5. 总进度行 ----
    td = sum(v[0] for v in g.values())
    ti = sum(v[1] for v in g.values())
    tn = sum(sum(v) for v in g.values())

    def total_repl(m: re.Match) -> str:
        a, b, c = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if (a, b, c) != (tn, td, ti):
            problems.append(f"  总进度写 {a} 项/完成 {b}/进行 {c}，实际 {tn}/{td}/{ti}")
            if fix:
                return f"**总进度：{tn} 项任务，完成 {td}，进行中 {ti}。**"
        return m.group(0)

    txt = re.sub(r"\*\*总进度：(\d+) 项任务，完成 (\d+)，进行中 (\d+)。\*\*",
                 total_repl, txt)

    return problems, (txt if fix and txt != orig else None)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    ap.add_argument("--fix", action="store_true", help="把对不上的数字就地改对")
    ap.add_argument("--print", dest="show", action="store_true",
                    help="打印真实进度表")
    a = ap.parse_args()

    if a.show:
        g = task_stats(a.root)
        print(f"{'大项':6s}{'完成':>5s}{'进行':>5s}{'待办':>5s}")
        for k in sorted(g, key=lambda x: int(x[1:])):
            d, i, w = g[k]
            print(f"{k:6s}{d:5d}{i:5d}{w:5d}")
        td = sum(v[0] for v in g.values())
        tn = sum(sum(v) for v in g.values())
        print(f"\n合计 {tn} 项，完成 {td}（{100*td//max(1,tn)}%）")
        return 0

    problems, fixed = check(a.root, fix=a.fix)
    if fixed is not None:
        io.open(os.path.join(a.root, ROADMAP), "w", encoding="utf-8").write(fixed)
        print(f"[已修正] {ROADMAP}")
    if problems:
        print("ROADMAP 和 TASKS 对不上：", file=sys.stderr)
        for p in problems:
            print("  " + p.strip(), file=sys.stderr)
        if not a.fix:
            print("\n  用 `python3 tools/roadmap_status.py --fix` 自动改数字。",
                  file=sys.stderr)
            return 1
        return 0
    print("ROADMAP 与 TASKS 一致")
    return 0


if __name__ == "__main__":
    sys.exit(main())
