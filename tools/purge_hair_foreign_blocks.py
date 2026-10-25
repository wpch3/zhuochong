#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""purge_hair_foreign_blocks.py —— 把烘进头发层的"别人的块"整块挖掉（T67.39）

★ 病灶（2026-10-26 第五轮，实测）
--------------------------------------------------------------------
`hair_hood_long@2x` 底部烘着一整段**棒球夹克的下摆**：青布 587+495+461 px、
白条若干（截图 docs/qa/t67_39_hood_cuff_before.png）。
这就是用户说的"在头发上画个假手臂"的同一类错误 —— 头发层里出现了衣服。

来源：这些头发件是从"穿着衣服的完整立绘"上切下来的，切框吃到了衣服。
在一件 38 万像素的件里它只占 0.5%，所以以前所有按面积比例的闸都放过去了。

★ 判据（只用"这颗头上只可能属于身体"的颜色）
--------------------------------------------------------------------
发色是**冷紫/冷蓝**（B ≥ R，发梢浅蓝 B-G>25），线稿是冷灰紫，高光是冷白。
所以只有两类像素绝不可能属于头发：

  · **暖**：`R - B > 6`（肤色、奶油白夹克、以及被它们染过的抗锯齿边）；
  · **青布**：`G - R > 60 且 B - G <= 20 且 G < 215`（袖口/帽衬的青，发梢浅蓝 B-G>25 不会撞）。

**成块**才算：`alpha ≥ 200` 且连通 `≥ 200 px`。这个门槛是量出来的 ——
真衣服/真皮肤是成百上千像素的块；抠像留下的边带串色最大连通只有 17px。

★ 做法
--------------------------------------------------------------------
整块 `alpha → 0`（连外扩 2px 把边缘那圈抗锯齿也带走），RGB 用邻域色补一遍
免得留垃圾；被挖掉的地方由**后面那张图**（手臂/躯干层）接住 —— 那本来就是
它该显示的东西。1× 与 @2x 同步处理（从 1× 的块映射到 @2x，或各自独立判也行，
这里各自独立判，因为 @2x 是 1× 的超分，块位置天然一致）。

用法
----
    /home/user/.imgenv/bin/python tools/purge_hair_foreign_blocks.py --dry-run
    /home/user/.imgenv/bin/python tools/purge_hair_foreign_blocks.py
"""
from __future__ import annotations

import argparse
import glob
import os
import sys

import numpy as np
from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MIN_BLOB = 200
SOLID = 200


def foreign(rgb, alpha):
    """"绝不可能属于头发"的种子像素。

    ★ 实测过的分界（`R-B` 直方图，四件头发件）：发色自身的 R-B 落在 -20..+19，
      其中 8~11 这一段有上万像素（这几缕头发本来就偏粉紫），**所以不能用 R-B>6**
      —— 第一版就是 6，一口气吃掉 40 万像素。
      皮肤是 R-B 40~55，青布是 G-R>60，两者都远在发色分布之外，可以当种子。
      奶油白夹克（R-B≈6）**单看颜色分不出来**，所以它靠"从青布种子长过去"来收：
      同一条下摆上青白相间，白色那几条（R-B≥0 且够亮）从青块一路连过去。
    """
    R = rgb[..., 0].astype(np.int32)
    G = rgb[..., 1].astype(np.int32)
    B = rgb[..., 2].astype(np.int32)
    lum = (R + G + B) / 3.0
    skin = (R - B > 22) & (R > 150) & (R - G > 8)
    teal = (G - R > 60) & (B - G <= 20) & (G < 215)
    cream = (R - B >= 2) & (lum >= 195) & (alpha >= SOLID)
    return (skin | teal) & (alpha >= SOLID), cream


def blobs(mask, min_px=MIN_BLOB):
    h, w = mask.shape
    lab = np.zeros((h, w), np.int32)
    ys, xs = np.nonzero(mask)
    out = []
    n = 0
    for y0, x0 in zip(ys, xs):
        if not mask[y0, x0] or lab[y0, x0]:
            continue
        n += 1
        lab[y0, x0] = n
        stack = [(y0, x0)]
        size = 0
        ymin = ymax = y0
        xmin = xmax = x0
        while stack:
            y, x = stack.pop()
            size += 1
            ymin, ymax = min(ymin, y), max(ymax, y)
            xmin, xmax = min(xmin, x), max(xmax, x)
            for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                ny, nx = y + dy, x + dx
                if 0 <= ny < h and 0 <= nx < w and mask[ny, nx] and not lab[ny, nx]:
                    lab[ny, nx] = n
                    stack.append((ny, nx))
        if size >= min_px:
            out.append((size, ymin, ymax, xmin, xmax, lab == n))
    out.sort(key=lambda t: -t[0])
    return out


def classify(arr, region):
    """这块异物是「贴在头发外面」还是「被头发包在中间」。

    外圈的 alpha 说了算：外圈 70% 以上是不透明头发 ⇒ 它在头发**里面**。
    这个区分是第五轮补的，因为两张图挖完的结果差很多：
      · `hair_hood_long` 底部那只手在剪影**边缘**（外面是空的）⇒ 直接 alpha→0，
        反正那个位置本来就该由后层的手臂/躯干显示；
      · chibi 的 `hair_long_back` 那块皮肤被头发**包在中间**（它其实是透过发缝
        露出来的头皮/额头）⇒ alpha→0 会在头发正中开天窗，实测把
        `docs/qa/t67_41_chibi_hair_hole.png` 那种斑驳的洞挖了出来。
        这种必须**补成头发**（塗り足し），不能挖。
    """
    ring = dilate(region, 3) & ~region
    if not ring.any():
        return "edge"
    frac = float((arr[..., 3][ring] >= 200).mean())
    return "hole" if frac >= 0.70 else "edge"


def fill_hair_in_hole(arr, region, foreign_mask=None):
    """把头发中间的洞按**列的上下发丝**插值补成头发（不动 alpha 以外的东西）。

    为什么是"按列插值"而不是"贴一块邻居"：这些头发全是**竖向发丝**，
    同一列上下的颜色本来就是连续的（亮部/暗部都在同一缕上），
    列内线性插值等于把这一缕**拉长**盖住缺口；贴一块别处的头发则会
    在接缝处出现方向/明暗突变。左右列各自独立处理，所以发丝的宽度和
    明暗过渡都保留下来。
    """
    h, w = region.shape
    out = arr.copy()
    M = 4          # 上下各取 4 行求均值，压掉单像素噪点
    # ★ 取色源必须**跳过异物本身**：这块皮肤就是横跨整片头发的宽条，
    #   紧挨着它的上下 4 行还是皮肤/奶油白，直接取会补出一条更亮的奶油带
    #   （第一版就是这样，`/tmp/chibi_hair_filled.png` 里那道白痕）。
    #   所以往上下各扫到 **8 个不透明的真发像素**为止，源不干净就不补。
    ok = None if foreign_mask is None else ~foreign_mask
    for x in range(w):
        col = region[:, x]
        if not col.any():
            continue
        ys = np.nonzero(col)[0]
        yt, yb = int(ys[0]), int(ys[-1])
        top_v, bot_v = [], []
        for y in range(yt - 1, -1, -1):
            if arr[y, x, 3] >= 200 and (ok is None or ok[y, x]):
                top_v.append(arr[y, x, :3])
                if len(top_v) >= M:
                    break
        for y in range(yb + 1, h):
            if arr[y, x, 3] >= 200 and (ok is None or ok[y, x]):
                bot_v.append(arr[y, x, :3])
                if len(bot_v) >= M:
                    break
        top_v = np.array(top_v, np.float64)
        bot_v = np.array(bot_v, np.float64)
        c_top = top_v.mean(axis=0) if len(top_v) else None
        c_bot = bot_v.mean(axis=0) if len(bot_v) else None
        if c_top is None and c_bot is None:
            continue
        if c_top is None:
            c_top = c_bot
        if c_bot is None:
            c_bot = c_top
        n = yb - yt + 1
        for i, y in enumerate(range(yt, yb + 1)):
            if not col[y]:
                continue
            t = (i + 0.5) / n
            out[y, x, :3] = (c_top * (1 - t) + c_bot * t).astype(np.uint8)
            out[y, x, 3] = 255
    return out


def dilate(m, n=1):
    for _ in range(n):
        m = (m | np.roll(m, 1, 0) | np.roll(m, -1, 0)
             | np.roll(m, 1, 1) | np.roll(m, -1, 1))
    return m


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--character", default="xiaoxun")
    ap.add_argument("--form", default="teen")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--no-fill-holes", dest="fill_holes", action="store_false",
                    help="被头发包住的洞也直接挖掉（默认补成头发）")
    ap.add_argument("--grow", type=int, default=2, help="挖掉后往外多带几圈（吃掉抗锯齿边）")
    a = ap.parse_args()

    d = os.path.join(ROOT, "characters", a.character, "forms", a.form, "sprites")
    files = [f for f in sorted(glob.glob(os.path.join(d, "*@2x.png")))
             if os.path.basename(f).startswith(("hair_", "acc_hair_"))]
    # 1× 同步（没有 @2x 的形态就只处理有的）
    ones = [f[:-7] + ".png" for f in files if os.path.exists(f[:-7] + ".png")]
    files = files + ones
    if not files:
        print("没找到头发件：", d)
        return 2

    # ★ 已知"挖不掉"的件：这里**必须**跳过，否则每次 rebuild 都会把它们再挖开一次。
    #   chibi 的长后发里那片头皮被头发包在正中（G66.41）：挖 → 头发正中开天窗，
    #   补 → 留亮平带；这件的发色本身是粉紫（R-B 12~21），和皮肤分不开。
    #   ⇒ 只能重画（T67.41）。和 `qa_hair_purity.py` 的 KNOWN 是同一条账。
    KNOWN_SKIP = {("chibi", "hair_long_back@2x.png"), ("chibi", "hair_long_back.png")}

    total = 0
    touched = 0
    for f in files:
        if (a.form, os.path.basename(f)) in KNOWN_SKIP:
            print("%-26s 跳过：已知欠账 T67.41（必须重画，脚本修不了）" % os.path.basename(f))
            continue
        arr = np.array(Image.open(f).convert("RGBA"))
        m, cream = foreign(arr[..., :3], arr[..., 3])
        bl = blobs(m)
        # 从每个种子块往**同一片下摆的白色条纹**长（R-B≥0 且够亮），
        # 迭代次数上限 80：下摆最宽也就几十像素，长了也不会窜到头发里
        grew = []
        for size, y0, y1, x0, x1, cm in bl:
            region = cm.copy()
            # 只长 8 圈：同一条下摆的白条纹紧挨着青块，8px 足够；
            # 放开了长（试过 80）会顺着发丝一路爬出去，实测把 hair_crown_long
            # 从几百像素长到 6,585 px 的一根长条 —— 那就不是"挖异物"了。
            for _ in range(8):
                nxt = dilate(region, 1) & cream & ~region
                if not nxt.any():
                    break
                region |= nxt
            grew.append((int(region.sum()), y0, y1, x0, x1, region))
        bl = grew
        if not bl:
            continue
        touched += 1
        name = os.path.relpath(f, d)
        kinds = [classify(arr, cm) if a.fill_holes else "edge"
                 for _s, _y0, _y1, _x0, _x1, cm in bl]
        for (size, y0, y1, x0, x1, _cm), kind in zip(bl, kinds):
            total += size
            print("%-26s 异物块 %5d px  y[%d,%d] x[%d,%d]  %s%s"
                  % (name, size, y0, y1, x0, x1,
                     "头发中间（补发）" if kind == "hole" else "剪影边缘（挖掉）",
                     "（dry-run）" if a.dry_run else ""))
        if a.dry_run:
            continue
        # 先分好类：被头发包住的洞要**补成头发**，贴在剪影外沿的才挖掉。
        holes = np.zeros(m.shape, bool)
        edges = np.zeros(m.shape, bool)
        for (_s, _y0, _y1, _x0, _x1, cm), kind in zip(bl, kinds):
            if kind == "hole":
                holes |= cm
            else:
                edges |= cm
        cut = dilate(edges, a.grow)
        before_full = arr.copy()
        if holes.any():
            arr = fill_hair_in_hole(arr, dilate(holes, a.grow), m)
        arr[..., 3][cut] = 0
        # RGB 顺手用邻居色补，免得挖出来的地方是垃圾色（fix_transparent_rgb 会再扫一遍兜底）。
        # ★ 只补**挖掉的那些像素**：第一版补的是整张图所有 alpha≤8 的像素，
        #   结果"块外一个字节都不许动"的自检当场报错（ABORT）—— 自检是对的。
        need = cut.copy()
        known = (~cut) & (arr[..., 3] > 8)
        for _ in range(16):
            acc = np.zeros(arr[..., :3].shape, np.int64)
            cnt = np.zeros(arr.shape[:2], np.int64)
            for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                k = np.roll(np.roll(known, dy, 0), dx, 1)
                v = np.roll(np.roll(arr[..., :3], dy, 0), dx, 1)
                acc += v * k[..., None]
                cnt += k
            todo = need & (cnt > 0)
            if not todo.any():
                break
            arr[todo, :3] = (acc[todo] / cnt[todo][:, None]).astype(np.uint8)
            need &= ~todo
            known |= todo
        # ---- 安全闸：**块外一个字节都不许动** ----
        #   （下面补 RGB 那几步只碰 alpha≤8 的像素，而 cut 之外可能也有 alpha≤8 的，
        #    所以这里必须逐字节比，不能只比 alpha。）
        keep = ~(cut | dilate(holes, a.grow))
        if not np.array_equal(arr[keep], before_full[keep]):
            print("ABORT：块外的像素被改动 %s" % name)
            return 3
        if holes.any():
            hb = arr[dilate(holes, a.grow)]
            if int(hb[hb[..., 3] == 255].shape[0]) == 0:
                print("ABORT：洞里没补成不透明头发 %s" % name)
                return 3
        Image.fromarray(arr).save(f)
        print("%-26s 挖掉 %d 块 / 补发 %d 块（外扩 %dpx）"
              % (name, kinds.count("edge"), kinds.count("hole"), a.grow))

    print("\n合计 %d 个文件、%d px 异物%s"
          % (touched, total, "（dry-run，未写盘）" if a.dry_run else "已挖除"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
