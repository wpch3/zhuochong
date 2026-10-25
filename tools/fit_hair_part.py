#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""fit_hair_part.py —— 把"髮だけ差分"的候选件，变成可直接顶替旧件的精灵（T67.25）

★ 它解决什么
--------------------------------------------------------------------
`key_magenta.py` 出来的图是**画家尺寸**（另一张画布、另一套比例），
而 rig.json 里一个部件的位置写的是
`pos / anchor / scale_1x` + 一张 `@2x` 精灵，四者必须严丝合缝。
手调 pos 是最容易出事的做法（历史上每一次"头发飘了""头发长在肩膀外"都出在这）。

这个工具换一个思路：**不动 rig，只让新件的几何去就旧件**。
   1. 量旧件精灵里"内容"的外接框（旧件是从正式立绘切的，它的位置就是真值）；
   2. 把新图的内容**非等比**缩放到同一个外接框；
   3. 贴进一张**和旧件同尺寸**的画布，内容落在同一个位置。
于是新件可以直接改名顶替旧件，`rig.json` 一个字都不用改。

★ 为什么允许非等比（x、y 两个方向缩放不同）
--------------------------------------------------------------------
生成出来的图固有比例和立绘差约 10%（实测宽高比 0.68 vs 0.62）。
等比缩放只能二选一：对齐高度就宽 10%、对齐宽度就短 9%。
两个都不行 —— 宽 10% 会盖住手臂，短 9% 发梢会露在裙子上面。
而头发没有刚体的圆、没有文字，10% 的各向异性**肉眼不可辨**，
所以这里选"两个方向都对齐"，并在报告里把两个缩放系数都打出来备查。

用法
----
    python3 tools/fit_hair_part.py --src design/redraw/hair_only/hair_long_backonly_v1.png \
        --ref forms/teen/sprites/hair_long_back@2x.png \
        --out design/redraw/hair_only/hair_long_back_v2@2x.png \
        --drop-ahoge 405 0 471 64
"""
from __future__ import annotations

import argparse
import os
import sys

import numpy as np
from PIL import Image


def content_bbox(alpha, thr=24):
    ys, xs = np.nonzero(alpha > thr)
    if not len(xs):
        raise SystemExit("空图")
    return int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())


def drop_ahoge(im, box):
    """把呆毛（呆毛是独立件 hair_ahoge，不能烤进后发）整块擦掉。

    ★ 记住它擦不干净：呆毛的根部是**画在**头发上的（不是 alpha 叠上去的），
      所以擦完圆顶上会留一点点卷曲的笔触（10px 级）。这一块正好在头的后面，
      Live2D 里始终被头遮住，视觉上不出现 —— 但如果你把头发单独拎出来看，
      会看到那个小卷。不要以为是 bug，也别试图"修"，除非重画。
    """
    x0, y0, x1, y1 = box
    a = np.array(im)
    before = int((a[:, :, 3] > 24).sum())
    a[y0:y1, x0:x1, 3] = 0
    after = int((a[:, :, 3] > 24).sum())
    print("  去呆毛：擦掉 %d px（%.2f%%）" % (before - after, 100.0 * (before - after) / before))
    return Image.fromarray(a)


def resize_premultiplied(im, size):
    """按**预乘 alpha** 缩放。

    ★ 为什么不能直接 resize：PIL 对 RGBA 是 RGB 和 A 各自独立插值的。
      透明区域的 RGB 即使是垃圾（反预乘时 0/a 会炸出纯绿），也会被混进边缘像素 →
      头发边上出现绿点/杂边。预乘之后透明区的 RGB 权重为 0，天然不参与混合。
      这是所有 sprite 缩放的标配做法，别省。
    """
    a = np.array(im).astype(np.float64)
    al = a[..., 3:4] / 255.0
    pm = np.concatenate([a[..., :3] * al, a[..., 3:4]], axis=2)
    pm_im = Image.fromarray(np.clip(pm, 0, 255).astype(np.uint8))
    pm_im = pm_im.resize(size, Image.LANCZOS)
    b = np.array(pm_im).astype(np.float64)
    # 分母夹在 0.25：alpha=3/255 时若直接除，放大约 85 倍，边缘会炸出一圈杂色。
    al2 = np.maximum(b[..., 3:4] / 255.0, 0.25)
    rgb = np.clip(b[..., :3] / al2, 0, 255)
    out = np.concatenate([rgb, b[..., 3:4]], axis=2)
    out = extend_edge_color(out.astype(np.uint8))
    out = despeckle_color(out)
    return Image.fromarray(out)


def despeckle_color(arr, iters=6):
    """把"不可能是这个素材的颜色"替换成邻居颜色（alpha 不动）。

    ★ 判据只认两种**绝不可能**的颜色，不做任何审美判断：
      · 偏绿：`G-R>40`（本角色的发色是冷紫，R≈G，绝不会有绿）
      · 洋红：`R-G>60 且 B-G>60`（键底色，抠像没抠干净时会有）
      抓到就取邻域平均替换，逐轮扩散。这样既不会改坏正常发色，又能把
      反预乘在 alpha 很小时炸出来的杂色彻底清掉 —— 否则它会在缩放/采样时
      污染边缘，表现为头发边上冒绿点（本轮实测 31,219 个）。
    """
    out = arr.copy()
    for _ in range(iters):
        a = out.astype(np.int32)
        R, G, B = a[..., 0], a[..., 1], a[..., 2]
        bad = (G - R > 40) | ((R - G > 60) & (B - G > 60))
        if not bad.any():
            break
        good = ~bad
        acc = np.zeros(out[..., :3].shape, np.float64)
        cnt = np.zeros(out.shape[:2], np.float64)
        for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (1, -1), (-1, 1), (-1, -1)):
            k = np.roll(np.roll(good, dy, 0), dx, 1)
            v = np.roll(np.roll(out[..., :3], dy, 0), dx, 1)
            acc += v * k[..., None]
            cnt += k
        fill = bad & (cnt > 0)
        if not fill.any():
            break
        out[fill, :3] = (acc[fill] / cnt[fill][:, None]).astype(np.uint8)
    return out


def extend_edge_color(arr, thr=16, iters=10):
    """把不透明像素的颜色**往外扩**到透明区（alpha 不动）。

    ★ 为什么：任何做了 alpha 过滤（引擎线性采样、mipmap、缩放）的地方，
      边缘像素的颜色都会和**旁边透明像素的 RGB**混合。透明像素 RGB 要是黑的，
      边缘就发暗（黑边）；要是垃圾（0,255,0），边缘就冒绿点。
      正确做法不是"把透明区涂黑"，而是"让它带上邻近的皮肤/头发颜色"。
    """
    out = arr.copy()
    A = out[..., 3]
    known = A > thr
    for _ in range(iters):
        if known.all():
            break
        acc = np.zeros(out[..., :3].shape, np.float64)
        cnt = np.zeros(A.shape, np.float64)
        for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (1, -1), (-1, 1), (-1, -1)):
            k = np.roll(np.roll(known, dy, 0), dx, 1)
            v = np.roll(np.roll(out[..., :3], dy, 0), dx, 1)
            acc += v * k[..., None]
            cnt += k
        fill = (~known) & (cnt > 0)
        if not fill.any():
            break
        out[fill, :3] = (acc[fill] / cnt[fill][:, None]).astype(np.uint8)
        known = known | fill
    return out


def fit_part(src_path, ref_path, out_path, ahoge_box=None):
    """把 src 拟合到 ref 的几何上并写出 out。返回 (sx, sy, 不透明px)。"""
    src = Image.open(src_path).convert("RGBA")
    ref = Image.open(ref_path).convert("RGBA")
    if ahoge_box:
        src = drop_ahoge(src, ahoge_box)
    RW, RH = ref.size
    rox0, roy0, rox1, roy1 = content_bbox(np.array(ref)[:, :, 3])
    nx0, ny0, nx1, ny1 = content_bbox(np.array(src)[:, :, 3])
    rw, rh = rox1 - rox0 + 1, roy1 - roy0 + 1
    nw, nh = nx1 - nx0 + 1, ny1 - ny0 + 1
    sx, sy = rw / nw, rh / nh
    print("  旧件画布 %dx%d，内容框 %dx%d @ (%d,%d)" % (RW, RH, rw, rh, rox0, roy0))
    print("  新件内容框 %dx%d → 缩放 x%.4f y%.4f（各向异性 %.1f%%）"
          % (nw, nh, sx, sy, 100 * (sy / sx - 1)))
    new = resize_premultiplied(src.crop((nx0, ny0, nx1 + 1, ny1 + 1)), (rw, rh))
    canvas = Image.new("RGBA", (RW, RH), (0, 0, 0, 0))
    canvas.paste(new, (rox0, roy0))
    canvas.save(out_path)
    op = int((np.array(canvas)[:, :, 3] > 24).sum())
    print("  写出 %s（%dx%d，不透明 %d px）" % (out_path, RW, RH, op))
    return sx, sy, op


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True, help="髮だけ差分（带 alpha）")
    ap.add_argument("--ref", required=True, help="要顶替的旧 @2x 精灵（几何真值）")
    ap.add_argument("--out", required=True)
    ap.add_argument("--drop-ahoge", nargs=4, type=int, default=None,
                    metavar=("X0", "Y0", "X1", "Y1"))
    a = ap.parse_args()

    box = tuple(a.drop_ahoge) if a.drop_ahoge else None
    fit_part(a.src, a.ref, a.out, box)
    return 0


if __name__ == "__main__":
    sys.exit(main())
