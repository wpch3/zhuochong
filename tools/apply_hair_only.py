#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""apply_hair_only.py —— 把"髮だけ差分"正式顶替掉从立绘上抠出来的后发（T67.25）

★ 为什么需要这一层（而不是手工改图）
--------------------------------------------------------------------
`hair_long_back@2x.png` 是重建链（`tools/rebuild_parts.sh`）的产物。
手工把它换掉，下一次 rebuild 就会被**原样还原** —— 这不是假设，
2026-10-19 已经踩过一次：`trim_exposed_residue.py` 改掉的 274px 因为没接进链，
下一轮重建把深褐横条又带了回来（见 rebuild_parts.sh 里那段警告）。

所以本脚本是重建链的最后一步（27b）：**它自己就是"把新源头写进成品件"的那一步**。
链上跑一次，成品就是新的；不跑，就是旧的。

★ 为什么排最后
--------------------------------------------------------------------
它直接覆盖 `sprites/hair_long_back@2x.png`，任何后面还会写这张图的步骤都会把它顶掉。

★ 表里为什么要写 ref
--------------------------------------------------------------------
新图是"画家尺寸"，几何则是 `rig.json` 里写死的（pos/anchor/scale + @2x 精灵尺寸）。
`fit_hair_part.fit_part()` 用**旧件的内容框**当几何真值，把新图非等比重采样过去，
于是 `rig.json` 一个字都不用改。旧件必须留着当 ref（`_ghostbak`）。缺了就跳过并报错。

用法
----
    python3 tools/apply_hair_only.py --character xiaoxun --form teen
    python3 tools/apply_hair_only.py --character xiaoxun --form teen --dry-run
"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fit_hair_part import fit_part  # noqa: E402

# 角色/形态 → 替换表。一项 = （髮だけ差分源件, 旧件（几何真值与备份）, 成品件, 呆毛框）
# 呆毛框是"把生成图里顺带画上去的呆毛擦掉"的矩形（呆毛是独立件 hair_ahoge，不能烤进后发）。
JOBS = {
    ("xiaoxun", "teen"): [
        {
            "src": "characters/xiaoxun/design/redraw/hair_only/hair_long_backonly_v1.png",
            "ref": "characters/xiaoxun/forms/teen/sprites/_ghostbak/hair_long_back@2x.png",
            "out": "characters/xiaoxun/forms/teen/sprites/hair_long_back@2x.png",
            "ahoge": (405, 0, 471, 64),
        },
    ],
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--character", default="xiaoxun")
    ap.add_argument("--form", default="teen")
    ap.add_argument("--root", default=".")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    jobs = JOBS.get((a.character, a.form), [])
    if not jobs:
        print("apply_hair_only：%s/%s 没有髮だけ差分源件，跳过" % (a.character, a.form))
        return 0
    rc = 0
    for j in jobs:
        src = os.path.join(a.root, j["src"])
        ref = os.path.join(a.root, j["ref"])
        out = os.path.join(a.root, j["out"])
        if not os.path.exists(src):
            print("  [跳过] 源件不在：%s" % j["src"])
            continue
        if not os.path.exists(ref):
            # 没有几何真值就不许猜 —— 猜出来的 pos 会在换发型时暴露成"头发飘了"
            print("  [错误] 旧件（几何真值）不在：%s" % j["ref"])
            rc = 2
            continue
        print("髮だけ差分 → %s" % j["out"])
        if a.dry_run:
            print("  (dry-run)")
            continue
        fit_part(src, ref, out, j["ahoge"])
    return rc


if __name__ == "__main__":
    sys.exit(main())
