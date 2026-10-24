#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""用真实的决策流水重标双路由阈值。

为什么要有这个工具：`config/gateway_routes.json` 里那三条阈值
（512 token 上云 / 本地负载 85% 溢出 / 敏感只走本地）**全是从别人的博客抄来的**
（见 docs/REFERENCE_NOTES.md 第二十批、DECISIONS DC18）。
抄来的数字要用自己的分布重标，否则"70~85% 走本地"这个目标就只是句口号。

用法：
    python3 tools/usage_report.py                      # 读 data/usage.jsonl
    python3 tools/usage_report.py --file data/usage.jsonl.1
    python3 tools/usage_report.py --sweep              # 扫 token 阈值看分流会怎么变

这个工具**只读**，不改任何配置 —— 改阈值是人看完数字之后的决定，不是脚本的。
"""
from __future__ import print_function

import argparse
import io
import json
import os
import sys

DEFAULT = os.path.join("data", "usage.jsonl")

# 目标区间来自调研（arxiv 2507.15553 + 三家工程博客的一致做法）：
# 本地分流 70~85%。低了说明钱花在了本可以本地干的活上，
# 高了说明重活被硬留在本地，用户看到的是"答得差"。
TARGET_LO, TARGET_HI = 0.70, 0.85


def load(path):
    rows, bad = [], 0
    if not os.path.exists(path):
        return rows, bad
    with io.open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except ValueError:
                bad += 1          # 崩溃时可能留半行，丢掉就是了，不要整个报错
    return rows, bad


def pct(a, b):
    return (100.0 * a / b) if b else 0.0


def bar(frac, width=28):
    n = int(round(frac * width))
    return "#" * n + "·" * (width - n)


def report(rows, bad, path):
    print("决策流水：%s（%d 条%s）" % (path, len(rows),
                                      "，%d 行坏掉已跳过" % bad if bad else ""))
    if not rows:
        print("\n还没有数据。跑起来用一阵子再回来看 —— 没有真实分布就不要动阈值，"
              "照抄的数字至少还是别人在真实流量上调出来的。")
        return 1

    picked = [r for r in rows if r.get("picked")]
    local = [r for r in picked if r.get("local")]
    cloud = [r for r in picked if not r.get("local")]
    nocand = [r for r in rows if r.get("reason") == "no_candidate"]
    blocked = [r for r in rows if r.get("reason") == "sensitive_blocked"]

    print("\n== 分流 ==")
    if picked:
        share = len(local) / float(len(picked))
        print("  本地 %4d  %s %.1f%%" % (len(local), bar(share), 100 * share))
        print("  云端 %4d  %s %.1f%%" % (len(cloud), bar(1 - share), 100 * (1 - share)))
        verdict = ("在目标区间内" if TARGET_LO <= share <= TARGET_HI else
                   ("**低于** %.0f%%：有活本可以留在本地，正在多花钱" % (TARGET_LO * 100)
                    if share < TARGET_LO else
                    "**高于** %.0f%%：重活可能被硬留在本地，答案质量会掉" % (TARGET_HI * 100)))
        print("  目标 %.0f~%.0f%% → %s" % (TARGET_LO * 100, TARGET_HI * 100, verdict))
    else:
        print("  一次都没落地（全是没候选 / 被拒）")
    if nocand:
        print("  没候选 %d 次（%.1f%%）—— 这些请求根本没路可走，先去接供应商"
              % (len(nocand), pct(len(nocand), len(rows))))
    if blocked:
        print("  敏感被拒 %d 次 —— 这是故意的（绝不偷偷上云），但次数多说明本地模型该装了"
              % len(blocked))

    print("\n== 为什么这么走 ==")
    reasons = {}
    for r in rows:
        k = r.get("reason", "?")
        reasons[k] = reasons.get(k, 0) + 1
    for k, v in sorted(reasons.items(), key=lambda kv: -kv[1]):
        print("  %-18s %5d  %s %.1f%%" % (k, v, bar(v / float(len(rows)), 20),
                                          pct(v, len(rows))))

    print("\n== token 分布（重标 tokens_cloud 的依据）==")
    toks = sorted(r.get("tokens", 0) or 0 for r in rows)
    if toks and toks[-1] > 0:
        def q(p):
            return toks[min(int(p * (len(toks) - 1)), len(toks) - 1)]
        print("  中位 %d / p75 %d / p90 %d / p99 %d / 最大 %d"
              % (q(0.5), q(0.75), q(0.9), q(0.99), toks[-1]))
    else:
        print("  调用方一直没报 token 数（全是 0）——"
              "先让调用方把估算值填上，否则这条阈值永远重标不了。")

    print("\n== 每家落了多少 ==")
    prov = {}
    for r in picked:
        k = "%s/%s%s" % (r.get("provider", "?"), r.get("model", "?"),
                         "（本地）" if r.get("local") else "")
        prov[k] = prov.get(k, 0) + 1
    for k, v in sorted(prov.items(), key=lambda kv: -kv[1])[:12]:
        print("  %-34s %5d  %.1f%%" % (k, v, pct(v, len(picked))))
    return 0


def sweep(rows):
    """把 tokens_cloud 换成别的值，分流会变成什么样 —— 纯按流水重算。

    只重算"长文上云"这一条：敏感、重活、负载溢出的判定跟 token 无关，
    它们在流水里已经定了，不该被这里的假设改掉。
    """
    usable = [r for r in rows if r.get("picked")]
    if not usable:
        print("没有落地的决策，扫不出东西来。")
        return 1
    print("把 tokens_cloud 换成别的值，本地分流会变成：\n")
    print("  %8s  %8s  %s" % ("阈值", "本地占比", "（目标 70~85%）"))
    for thr in (128, 256, 512, 1024, 2048, 4096, 8192):
        nloc = 0
        for r in usable:
            reason = r.get("reason", "")
            tok = r.get("tokens", 0) or 0
            if reason in ("sensitive_local", "cloud_down"):
                nloc += 1                      # 与 token 无关，原样保留
            elif reason in ("heavy_cloud", "local_busy", "sensitive_blocked"):
                pass                           # 同上，仍然上云
            elif reason == "only_choice":
                nloc += 1 if r.get("local") else 0
            else:                              # default_local / long_cloud
                nloc += 0 if tok > thr else 1
        share = nloc / float(len(usable))
        mark = "  ← 在区间内" if TARGET_LO <= share <= TARGET_HI else ""
        print("  %8d  %7.1f%%  %s%s" % (thr, 100 * share, bar(share), mark))
    print("\n注意：这只是**按已经发生过的请求**重算，没有考虑换阈值之后"
          "用户行为会不会变。要定下来还得真跑一段。")
    return 0


def main():
    ap = argparse.ArgumentParser(description="按真实决策流水重标双路由阈值")
    ap.add_argument("--file", default=DEFAULT, help="流水路径（默认 data/usage.jsonl）")
    ap.add_argument("--sweep", action="store_true", help="扫 token 阈值")
    a = ap.parse_args()
    rows, bad = load(a.file)
    if a.sweep:
        if not rows:
            print("流水是空的：%s" % a.file)
            return 1
        return sweep(rows)
    return report(rows, bad, a.file)


if __name__ == "__main__":
    sys.exit(main())
