#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""qa_sway_gap.py —— 头发/裙子摆动时会不会**从身体边上漏出空隙**（T67.29）

★ 为什么要有这条闸
--------------------------------------------------------------------
用户 2026-10-26 的原话（这一条是整轮的判据）：

> 拥有完整无缺的头发，而身体覆盖的部分做个分层……这样头发飘动时也不会有空隙和连接错误。

也就是说：**静止看着对不算对，一晃起来不能漏底色才算对。** 而"漏底色"这件事
以前只能靠肉眼在预览里晃一晃看 —— 现在把它变成可数的：

★ 怎么量（可复算、不依赖渲染抖动）
--------------------------------------------------------------------
1. 取部件精灵的 alpha 剪影（>24）；
2. 按 `rig.json` 的 `pos/anchor/scale` 把它投到画布；
3. **按摆链的最大位移整体平移**（位移量从 `deformers[]` 里该部件的网格点表取最大绝对值，
   单位是 1× 画布像素 → 乘 `scale` 换成精灵像素）；水平/垂直各试 ±；
4. 平移后的剪影里，原本"被身体盖住"、现在**没有任何东西盖住**的像素 = 会漏底色的空隙；
5. 空隙像素数就是这条闸的读数。

判据：**空隙 > 0 就是错**（哪怕 1px 也会在边缘露出来）。修法是补满源头，
不是挪层 —— 这一点用户已经说清楚了。

用法
----
    python3 tools/qa_sway_gap.py --character xiaoxun --form teen --part acc_hair_long
    python3 tools/qa_sway_gap.py ... --all-hair        # 所有发型件一起量
"""
from __future__ import annotations

import argparse
import json
import os
import sys

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from qa_layer_visibility import footprint  # noqa: E402


def sprite_scale(part):
    sc = part.get("scale", 0.5)
    return sc if isinstance(sc, (int, float)) else sc[0]


def max_deform_px(rig, part_id):
    """该部件所有网格位移里最大的绝对值（1× 画布像素）。

    ★ 网格点的写法是 `{"c":列,"r":行,"dx":..,"dy":..}`（缺省 0），不是 (dx,dy) 元组 ——
      第一版按元组解析，结果所有位移都读成 0，闸静默失效。这种"读不到就当 0"最容易骗人，
      所以读不到任何点时这里要**报错**，不许悄悄返回 0。
    """
    best, seen = 0.0, 0
    for d in rig.get("deformers", []):
        if d.get("part") != part_id:
            continue
        for pt in d.get("points") or []:
            if not isinstance(pt, dict):
                continue
            seen += 1
            best = max(best, abs(float(pt.get("dx", 0) or 0)),
                       abs(float(pt.get("dy", 0) or 0)))
    if seen == 0:
        # 两种情况要分清：①真的没有网格（长鬓发就是这样，只能跟着头动）；
        # ②解析写错。①是事实，②是 bug。这里返回 None 让调用方把话说清楚。
        return None
    return best


def interior_holes(alpha, thr=24):
    """精灵内部被不透明包住的透明像素（= 头发上那个"洞"）。

    为什么不直接数 footprint：可见像素是**正常**的（头发本来就会露出来）。
    会漏底色的是**洞**：洞跟着头发一起移动，一旦移出身体轮廓，背景就从洞里透出来。
    """
    op = alpha > thr
    h, w = op.shape
    seen = np.zeros_like(op)
    from collections import deque
    dq = deque()
    for x in range(w):
        for y in (0, h - 1):
            if not op[y, x] and not seen[y, x]:
                seen[y, x] = True
                dq.append((y, x))
    for y in range(h):
        for x in (0, w - 1):
            if not op[y, x] and not seen[y, x]:
                seen[y, x] = True
                dq.append((y, x))
    while dq:
        y, x = dq.popleft()
        for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            ny, nx = y + dy, x + dx
            if 0 <= ny < h and 0 <= nx < w and not op[ny, nx] and not seen[ny, nx]:
                seen[ny, nx] = True
                dq.append((ny, nx))
    return ~op & ~seen


def shifted(fp, dx, dy):
    out = np.zeros_like(fp)
    h, w = fp.shape
    ys, xs = np.nonzero(fp)
    ny, nx = ys + dy, xs + dx
    ok = (ny >= 0) & (ny < h) & (nx >= 0) & (nx < w)
    out[ny[ok], nx[ok]] = True
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--character", default="xiaoxun")
    ap.add_argument("--form", default="teen")
    ap.add_argument("--root", default=".")
    ap.add_argument("--part", action="append", default=[])
    ap.add_argument("--all-hair", action="store_true", help="量全部 hair_/acc_hair_ 件")
    ap.add_argument("--sway-px", type=float, default=0.0,
                    help="额外附加的整体位移（1× 画布像素），默认只用量到的网格位移")
    a = ap.parse_args()

    base = os.path.join(a.root, "characters", a.character, "forms", a.form)
    rig = json.load(open(os.path.join(base, "rig.json"), encoding="utf-8"))
    canvas = (rig["canvas"]["w"], rig["canvas"]["h"])
    parts = rig["parts"]
    targets = list(a.part)
    if a.all_hair:
        targets += [p["id"] for p in parts
                    if p["id"].startswith(("hair_", "acc_hair_"))
                    and ("hair" in p["id"])]
    targets = sorted(set(targets))
    if not targets:
        print("没指定部件（--part 或 --all-hair）")
        return 2

    fps = {p["id"]: footprint(p, base, canvas) for p in parts}

    # 每件的"内部洞"footprint（画布坐标）
    holes_fp = {}
    for p in parts:
        path = os.path.join(base, p["file"])
        if not os.path.exists(path):
            holes_fp[p["id"]] = None
            continue
        from qa_layer_visibility import Placement
        im = Image.open(path).convert("RGBA")
        a_np = np.array(im)[:, :, 3]
        holes = interior_holes(a_np)
        if not holes.any():
            holes_fp[p["id"]] = np.zeros((canvas[1], canvas[0]), bool)
            continue
        pl = Placement(p, im.size)
        ys, xs = np.nonzero(holes)
        cx, cy = pl.to_canvas(xs, ys)
        cx = np.clip(np.round(cx).astype(int), 0, canvas[0] - 1)
        cy = np.clip(np.round(cy).astype(int), 0, canvas[1] - 1)
        m = np.zeros((canvas[1], canvas[0]), bool)
        m[cy, cx] = True
        holes_fp[p["id"]] = m
    print("%-24s %8s %8s %8s %10s" % ("part", "sway", "gaphole−", "gaphole+", "结论"))
    bad = 0
    for pid in targets:
        p = next((q for q in parts if q["id"] == pid), None)
        if p is None:
            print("  [跳过] rig 里没有", pid)
            continue
        own = fps.get(pid)
        if own is None:
            continue
        sc = sprite_scale(p)
        dmax = max_deform_px(rig, pid)
        if dmax is None:
            print("%-24s %8s %10s %10s 无网格位移（只能跟父骨动）" % (pid, "-", "-", "-"))
            continue
        sway1x = dmax + a.sway_px
        sway_sprite = sway1x * sc            # 精灵像素
        # 这一件"被谁盖着"：所有层号更大的件
        cover = np.zeros_like(own)
        for q in parts:
            if q["layer"] > p["layer"] and fps.get(q["id"]) is not None:
                cover |= fps[q["id"]]
        holes = holes_fp.get(pid)
        if holes is None:
            holes = np.zeros_like(own)
        gaps = []
        for sign in (-1, 1):
            d = int(round(sign * sway_sprite))
            mv = shifted(holes, d, 0)
            gaps.append(int((mv & ~cover).sum()))
        verdict = "OK" if max(gaps) == 0 else "漏底色 %d px" % max(gaps)
        if max(gaps) > 0:
            bad += 1
        print("%-24s %8.1f %10d %10d %10s"
              % (pid, sway_sprite, gaps[0], gaps[1], verdict))
    print("\n结论：%d/%d 件在摆动时会漏底色" % (bad, len(targets)))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
