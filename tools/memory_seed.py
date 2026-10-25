#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""memory_seed.py —— 把角色的"内心档案"导入长记忆（T67.45）

她自己的过去（`characters/<id>/inner.json` 里的 episodes）在记忆里应当是**真的存在过的事件**，
而不是只躺在提示词里的一段设定。导入之后：

  · 她翻得到（`zmem_recall` 能检索到）；
  · 时间是真的（写入时给绝对时间戳，不是"三年前"这种模型自己算的说法）；
  · 和"第一次见面"分得清 —— 那些是**遇见你之前**的事，锚点才是遇见之后。

★ 为什么不做自动导入：`MEMORY_PLAN` 的规矩是长期记忆默认关、逐条确认。
  这个工具是"用户点了导入"的那一下，不是后台偷偷跑的东西。

用法
----
    python3 tools/memory_seed.py --dry-run                  # 只看会写什么
    python3 tools/memory_seed.py --character xiaoxun        # 通过正在跑的服务写入
    python3 tools/memory_seed.py --character xiaoxun --api http://127.0.0.1:5173

时间怎么定（重要）
------------------
inner.json 里的 `when` 是**相对说法**（"上周三""去年梅雨季"）。这里不猜具体日子，
而是按它在列表里的顺序往前摊：最近的一条 = 3 天前，最远的一条 = 240 天前。
写进去的正文会**保留原来的说法**（"上周三"），绝对时间是引擎记的 ——
四年后她说的会是"那件事是几年前的了"，而不是编一个精确日期。
"""
from __future__ import annotations

import argparse
import glob
import io
import json
import os
import sys
import time
import urllib.parse
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NEWEST_DAYS_AGO = 3        # 最近的一条经历：3 天前
OLDEST_DAYS_AGO = 240      # 最远的一条：240 天前
DAY = 86400


def load_inner(cid):
    p = os.path.join(ROOT, "characters", cid, "inner.json")
    if not os.path.exists(p):
        return None
    with io.open(p, encoding="utf-8") as f:
        return json.load(f)


def plan(cid):
    """返回 [(t, kind, salience, text, once_key), ...]"""
    doc = load_inner(cid)
    if not doc:
        return None
    eps = doc.get("episodes", [])
    if not eps:
        return []
    # 权重 → 重要性：这条经历撑不撑得住一句"我就是这样的人"
    weight = {}
    for v in doc.get("self", {}).get("values", []):
        weight[v.get("episode")] = float(v.get("weight", 0.0))
    n = len(eps)
    out = []
    for i, e in enumerate(eps):
        # i=0 最远，i=n-1 最近
        days = OLDEST_DAYS_AGO - (OLDEST_DAYS_AGO - NEWEST_DAYS_AGO) * (i / max(1, n - 1))
        t = int(time.time()) - int(days * DAY)
        w = weight.get(e["id"], 0.15)
        sal = max(3, min(9, int(round(3 + w * 6))))
        # ★ 正文里不许出现 episode id（那是引擎的内部编号）：写进去她会念出来。
        #   id 只用在 once-key 上，保证同一条经历不会导两次。
        text = "%s，%s：%s 当时我心里是：%s" % (
            e.get("when", ""), e.get("where", ""),
            e.get("what", ""), e.get("felt", ""))
        out.append((t, 0, sal, text, "inner:%s:%s" % (cid, e["id"])))
    return out


def post(api, path, params):
    url = api.rstrip("/") + path + "?" + urllib.parse.urlencode(params)
    with urllib.request.urlopen(url, timeout=15) as r:
        return json.loads(r.read().decode("utf-8"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--character", default="")
    ap.add_argument("--api", default="http://127.0.0.1:5173")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    chars = []
    if a.character:
        chars = [a.character]
    else:
        for p in sorted(glob.glob(os.path.join(ROOT, "characters", "*", "inner.json"))):
            chars.append(os.path.basename(os.path.dirname(p)))

    wrote = 0
    for cid in chars:
        rows = plan(cid)
        if rows is None:
            print("%-10s 没有 inner.json，跳过" % cid)
            continue
        if not rows:
            print("%-10s inner.json 里没有经历，跳过" % cid)
            continue
        print("== %s ==" % cid)
        for t, kind, sal, text, once in rows:
            day = time.strftime("%Y-%m-%d %H:%M", time.localtime(t))
            print("   %s  重要性 %d  一次键 %s" % (day, sal, once))
            print("      %s" % text)
            if a.dry_run:
                continue
            try:
                r = post(a.api, "/api/memory/add",
                         dict(kind=kind, salience=sal, text=text, once=once, t=t))
            except Exception as e:                    # noqa: BLE001
                print("      [失败] %s" % e)
                continue
            if r.get("ok"):
                wrote += 1
                print("      → id %s" % r.get("id"))
            else:
                print("      [被拒] %s" % r.get("error"))
    if a.dry_run:
        print("\n（dry-run：一条都没写）")
    else:
        print("\n写进去 %d 条" % wrote)
    return 0


if __name__ == "__main__":
    sys.exit(main())
