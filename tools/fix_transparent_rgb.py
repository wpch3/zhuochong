#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""fix_transparent_rgb.py —— 清掉透明区里的垃圾 RGB，并把边缘颜色外扩（T67.30）

★ 为什么透明像素的 RGB 也要管
--------------------------------------------------------------------
alpha=0 的像素肉眼看不见，但它**参与过滤**。以下环节都会把它混进来：

  · 缩放（PIL 对 RGBA 是 RGB、A 各自插值，不预乘）；
  · 引擎的线性采样 / mipmap / 双线性放大；
  · 任何"先在浮点上算再 clip"的合成。

结果是边缘出现一圈**不该有的颜色**：黑边（透明区是黑的）、绿点（反预乘炸出来的 (0,255,0)）、
洋红边（键底没抠净）。用户明令禁止"黑边/白边/彩边"这类制作后缺陷，所以这条必须治。

★ 治法是"外扩"，不是"涂黑"
--------------------------------------------------------------------
把**不透明像素的颜色往外扩**到透明区（alpha 一律不动）。这样边缘做过滤时混进来的是
"旁边那块头发/皮肤的颜色"，过渡连续 —— 这才是标准做法（edge extend / color bleed）。

★ 两段式外扩
--------------------------------------------------------------------
  1) 近边缘 12 px：逐圈精确外扩（8 邻域平均），这一圈才是真正会被采到的；
  2) 更远处：用已填充像素做指数级（±1/2/4/8…/256）传播，几百 px 内全部填满。
     远处颜色只在极小缩放时被 mipmap 采到，但仍必须"不是垃圾色"。

★ 安全闸（写盘前自检，不通过就不写）
--------------------------------------------------------------------
  · alpha 通道必须**逐字节不变**；
  · alpha>8 的像素 RGB 必须**逐字节不变**；
不满足直接 abort，绝不写盘。

用法
----
    /home/user/.imgenv/bin/python tools/fix_transparent_rgb.py --dry-run
    /home/user/.imgenv/bin/python tools/fix_transparent_rgb.py
"""
from __future__ import annotations

import argparse
import glob
import os
import sys

import numpy as np
from PIL import Image

# 备份/纯参照目录，默认不动（要动显式加 --include-reference）
SKIP_DIRS = ("_ghostbak",)


def bad_hue_mask(rgb, alpha, thr=8):
    """异色判据：纯绿（G 明显高于 R 且 B 接近 0）或洋红（R、B 同时高于 G）。"""
    a = rgb.astype(np.int32)
    R, G, B = a[..., 0], a[..., 1], a[..., 2]
    # ★ 绿也必须要求**饱和的纯绿**：青布 #6CB4C0 的暗部（48,147,117）满足
    #   G-R=99、B 也低，只看这两条会把鞋子的青条暗部判成垃圾（实测 51 px）。
    #   键色残渣长的是 (0,255,0)：R、B 都很低，G 很高。
    green = (G > 150) & (R < 120) & (B < 120) & (G - np.maximum(R, B) > 60)
    magenta = (R - G > 60) & (B - G > 60)
    return (green | magenta) & (alpha <= thr)


def _spread(arr, known, offsets, bad=None):
    acc = np.zeros(arr[..., :3].shape, np.float64)
    cnt = np.zeros(arr.shape[:2], np.float64)
    for dy, dx in offsets:
        k = np.roll(np.roll(known, dy, 0), dx, 1)
        if bad is not None:
            k = k & ~np.roll(np.roll(bad, dy, 0), dx, 1)
        v = np.roll(np.roll(arr[..., :3], dy, 0), dx, 1)
        acc += v * k[..., None]
        cnt += k
    fill = (~known) & (cnt > 0)
    if fill.any():
        arr[fill, :3] = np.rint(acc[fill] / cnt[fill][:, None]).astype(np.uint8)
    return known | fill


N8 = ((1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (1, -1), (-1, 1), (-1, -1))


def edge_extend(arr, thr=8, near_px=12, far_max=512):
    """外扩。**取色源排除异色像素** —— 否则垃圾色会被一圈圈传下去。"""
    out = arr.copy()
    bad = bad_hue_mask(out[..., :3], out[..., 3])
    known = (out[..., 3] > thr) & ~bad
    if known.all():
        return out, 0
    for _ in range(near_px):
        known = _spread(out, known, N8, bad)
    step = 1
    while step <= far_max:
        if known.all():
            break
        offs = [(step, 0), (-step, 0), (0, step), (0, -step),
                (step, step), (step, -step), (-step, step), (-step, -step)]
        known = _spread(out, known, offs, bad)
        # 再补一圈 8 邻域，让步长之间的缝被填上
        known = _spread(out, known, N8, bad)
        step *= 2
    return out, int((~known).sum())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--character", default="xiaoxun")
    ap.add_argument("--root", default=".")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--include-reference", action="store_true",
                    help="连 _ghostbak 一起处理（默认跳过：备份必须保持原样）")
    ap.add_argument("--quiet", action="store_true")
    a = ap.parse_args()

    # 只扫**出货的精灵目录**（forms/*/sprites/**）：design/redraw/ 里是中间素材，
    # 带洋红底天经地义，扫它既没意义又会淹掉真问题（实测多出 49 万 px 噪声）。
    pat = os.path.join(a.root, "characters", a.character, "forms", "**", "sprites", "**", "*@2x.png")
    files = sorted(glob.glob(pat, recursive=True))
    if not files:
        print("没找到精灵：", pat)
        return 2
    if not a.include_reference:
        files = [f for f in files if not any(s in f.replace(os.sep, "/") for s in SKIP_DIRS)]

    touched = 0
    total_bad = 0
    total_far = 0
    skipped_ref = 0
    for f in files:
        im = Image.open(f).convert("RGBA")
        arr = np.array(im)
        bad = bad_hue_mask(arr[..., :3], arr[..., 3])
        n = int(bad.sum())
        if not n:
            continue
        total_bad += n
        touched += 1
        if not a.quiet:
            print("%-58s 透明区垃圾 %6d px%s" % (
                os.path.relpath(f, a.root), n, "（dry-run）" if a.dry_run else ""))
        if a.dry_run:
            continue
        before_alpha = arr[..., 3].copy()
        before_vis = arr[arr[..., 3] > 8].copy()
        out, far = edge_extend(arr)
        # ---- 安全闸 ----
        if not np.array_equal(out[..., 3], before_alpha):
            print("ABORT：alpha 被改动 %s" % f)
            return 3
        if not np.array_equal(out[out[..., 3] > 8], before_vis):
            print("ABORT：可见像素被改动 %s" % f)
            return 3
        residual = int(bad_hue_mask(out[..., :3], out[..., 3]).sum())
        total_far += far
        Image.fromarray(out).save(f)
        if residual and not a.quiet:
            print("    ⚠ 残留 %d px（周围整块全是透明、连不到任何不透明像素）" % residual)
        if far and not a.quiet:
            print("    远端未连通像素 %d px 保留原状" % far)

    print("\n合计 %d 件有透明区垃圾，共 %d px；备份目录跳过 %d 件" % (
        touched, total_bad, skipped_ref))
    return 0


if __name__ == "__main__":
    sys.exit(main())
