#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""move_hair_islands.py —— 把"画错层的碎发片"从前景侧发搬回后发层（T67.26）

★ 病灶（用户 2026-10-26 截图指出）
--------------------------------------------------------------------
两腿之间有一道**竖着的浅蓝薄片**，从头裙下缘一直到膝盖。一开始以为是后发
（后发在最底层，被腿挡着，照理看不见），隔离探针一打才定位到：
它是 `acc_hair_sidelong_l/r`（长鬓发，**层 249/251 = 在腿和裙子前面**）里
**一块断开的碎岛**。

三个证据说明它是**画错层**，不是"设计如此"：
1. 它是**不连通**的一块（主发块 18.8 万 px，这块只有 8 千 px，中间没有连接）；
2. 参考立绘 `design/sheets/sheet_long.png` 里，两腿之间**确实有一缕**头发 ——
   但那缕是**后发**，在腿和裙子的**后面**；
3. 我们这件层号 249/251 在腿（60）前面，所以它盖在大腿上，边缘还是切出来的直线。

★ 治法
--------------------------------------------------------------------
不删（删了就没有参考里那缕头发了），也不重画：
**把碎岛按画布坐标搬到后发精灵里**。后发在最底层，于是它自动变成"被腿挡住、
只在两腿缝隙里露出来"，和参考一致；碎岛的上缘正好在裙摆下缘，
本来就被裙子盖住，不需要另画连接带。

★ 为什么用画布坐标搬
--------------------------------------------------------------------
两个件各有自己的 `pos/anchor/scale`。只按精灵像素搬会错位。
这里把碎岛映射到画布坐标，再映射进目标件的精灵坐标，于是"看起来在哪就还在哪"。

用法
----
    python3 tools/move_hair_islands.py --character xiaoxun --form teen
    python3 tools/move_hair_islands.py --character xiaoxun --form teen --dry-run

幂等：碎岛搬走之后源件里就没有"岛"了，再跑一次是空操作。
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import deque

import numpy as np
from PIL import Image, ImageFilter

MIN_ISLAND_PX = 200      # 小于 200px 的当噪点/抗锯齿毛边，不动。
#                            ★ 试过 20px：搬走 13~17 个"碎屑"，那是主发缕轮廓上的抗锯齿毛边，
#                              搬走等于给侧发咬边、同时在后发上撒点。
#                              200 的实测分界：碎屑 20~89px，真正的碎发片 225/240/344/786/5309/8280px。
MAX_ISLAND_RATIO = 0.10  # 超过主块 10% 的当"身体"，不动

# 谁身上有画错层的岛 → 搬到谁身上
JOBS = {
    ("xiaoxun", "teen"): [
        # (源件 id, 目标件 id)
        ("acc_hair_sidelong_l", "acc_hair_long"),
        ("acc_hair_sidelong_r", "acc_hair_long"),
    ],
}


def label(mask):
    h, w = mask.shape
    lab = np.zeros((h, w), np.int32)
    cur = 0
    sizes = {}
    ys, xs = np.nonzero(mask)
    for y0, x0 in zip(ys, xs):
        if lab[y0, x0]:
            continue
        cur += 1
        dq = deque([(y0, x0)])
        lab[y0, x0] = cur
        n = 0
        while dq:
            y, x = dq.popleft()
            n += 1
            for dy in (-1, 0, 1):
                for dx in (-1, 0, 1):
                    ny, nx = y + dy, x + dx
                    if 0 <= ny < h and 0 <= nx < w and mask[ny, nx] and not lab[ny, nx]:
                        lab[ny, nx] = cur
                        dq.append((ny, nx))
        sizes[cur] = n
    return lab, sizes


class Placement:
    """精灵像素 ↔ 画布坐标。rig 里 pos/anchor/scale 的三行数学，别在别处再写一遍。"""

    def __init__(self, part, size):
        self.pos = part["pos"]
        self.anchor = part["anchor"]
        self.scale = part.get("scale", 0.5)
        self.W, self.H = size

    def to_canvas(self, u, v):
        cx = self.pos[0] + (u - self.W * self.anchor[0]) * self.scale
        cy = self.pos[1] + (v - self.H * self.anchor[1]) * self.scale
        return cx, cy

    def to_sprite(self, cx, cy):
        u = (cx - self.pos[0]) / self.scale + self.W * self.anchor[0]
        v = (cy - self.pos[1]) / self.scale + self.H * self.anchor[1]
        return u, v


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--character", default="xiaoxun")
    ap.add_argument("--form", default="teen")
    ap.add_argument("--root", default=".")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    jobs = JOBS.get((a.character, a.form), [])
    if not jobs:
        print("move_hair_islands：%s/%s 没有要搬的岛，跳过" % (a.character, a.form))
        return 0

    base = os.path.join(a.root, "characters", a.character, "forms", a.form)
    rig = json.load(open(os.path.join(base, "rig.json"), encoding="utf-8"))
    byid = {p["id"]: p for p in rig["parts"]}

    moved_total = 0
    for src_id, dst_id in jobs:
        sp = byid[src_id]
        dp = byid[dst_id]
        spath = os.path.join(base, sp["file"])
        dpath = os.path.join(base, dp["file"])
        simg = Image.open(spath).convert("RGBA")
        dimg = Image.open(dpath).convert("RGBA")
        sa = np.array(simg)
        alpha = sa[:, :, 3]
        lab, sizes = label(alpha > 4)
        main = max(sizes, key=lambda k: sizes[k])
        islands = [k for k, n in sizes.items()
                   if k != main and n >= MIN_ISLAND_PX and n <= sizes[main] * MAX_ISLAND_RATIO]
        if not islands:
            print("  %-24s 没有岛（已搬过）" % src_id)
            continue
        print("  %-24s 找到 %d 块岛 → %s" % (src_id, len(islands), dst_id))

        src_pl = Placement(sp, simg.size)
        dst_pl = Placement(dp, dimg.size)
        da = np.array(dimg)
        for k in islands:
            mask = (lab == k)
            # 膨胀 2px 连淡边一起搬走，避免源件留下 1px 毛边
            grown = np.array(Image.fromarray((mask * 255).astype(np.uint8))
                             .filter(ImageFilter.MaxFilter(5))) > 128
            ys, xs = np.nonzero(grown)
            n = 0
            for y, x in zip(ys, xs):
                cx, cy = src_pl.to_canvas(x, y)
                du, dv = dst_pl.to_sprite(cx, cy)
                du, dv = int(round(du)), int(round(dv))
                if 0 <= dv < da.shape[0] and 0 <= du < da.shape[1]:
                    # 目标处已有像素就叠加（按 alpha 取大），空处直接写入
                    if da[dv, du, 3] == 0:
                        da[dv, du] = sa[y, x]
                    elif sa[y, x, 3] > da[dv, du, 3]:
                        da[dv, du, 3] = sa[y, x, 3]
                    n += 1
            # 从源件删掉
            sa[:, :, 3][grown] = 0
            print("     岛 %5d px → 目标写入 %d px" % (int(mask.sum()), n))
            moved_total += int(mask.sum())

        if a.dry_run:
            print("     (dry-run，不写文件)")
            continue
        Image.fromarray(sa).save(spath)
        Image.fromarray(da).save(dpath)

    print("move_hair_islands：搬走 %d px" % moved_total)
    return 0


if __name__ == "__main__":
    sys.exit(main())
