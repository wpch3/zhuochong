#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""fit_hair_part.py —— 把"髮だけ差分"的候选件，变成可直接顶替旧件的精灵（T67.25）

★ 它解决什么
--------------------------------------------------------------------
`key_hair_only.py` 出来的图是**画家尺寸**（另一张画布、另一套比例），
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
    new = src.crop((nx0, ny0, nx1 + 1, ny1 + 1)).resize((rw, rh), Image.LANCZOS)
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
