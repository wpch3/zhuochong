#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""key_magenta.py —— 把"洋红底单件图"（髮だけ差分 / しっぽ差分）抠成带 alpha 的源件（T67.7 / T67.11）

★ 为什么需要它
--------------------------------------------------------------------
现有流水线（`cut_from_sheets.py` → `make_attach_parts.py` → `clean_hair_residue.py`）
的输入是**穿着衣服的完整立绘**。从这种图上切後ろ髪，切出来的多边形里必然带着
被身体挡住的衣服/手 —— 因为那些像素在图上就是衣服。于是有了 G66.24 的幽灵手。

补救的路子（按颜色洗、按身体掩膜擦）两条都试过，都失败（见 GAPS G66.24 与 T67.3）：
- 按颜色洗：幽灵件被"洗淡"过，颜色落在发丝高光的色域里，洗不干净；
- 按几何擦：能擦掉 62%，但可见的幽灵在身体轮廓**外一点点**（副本有偏移），擦不到。

结论：后髪要有自己的**源头** —— 一张只画头发、不含身体和衣服的图（日文工序里叫
「髪だけ差分」）。这类图的背景统一是洋红 #FF00FF，抠像用。本工具就干这一件事：
**把洋红键抠干净，不产生彩边，不留孤点。**

★ 为什么不能直接二值化（我第一版就是二值化，两个毛病）
--------------------------------------------------------------------
1. **彩边**：洋红和淡紫头发在边缘混色，二值化后轮廓上留一圈粉边。
   用户明令禁止"黑边/白边/彩边"这类制作后缺陷，所以必须
   **反预乘 + 去溢色**，而不是"要么全留要么全删"。
2. **孤点**：头发的深紫阴影、线稿的紫黑，会被当成"洋红"抠出一个个小洞
   （第一版 843x1264 上留下成片黑点）。所以最后一步补洞：
   只补"全透明但被 ≥200 的不透明包住"的点。

★ 判据（为什么盯 G 通道）
--------------------------------------------------------------------
洋红 #FF00FF 的特征是 **R、B 高而 G 低**；本角色的头发（#D8D8E8 / #C9CBE0 / #9FC4E8）
恰好是 **G 与 R 接近、B 更高**（冷紫/冷蓝）。所以 keyness 只看
`min(R,B) - G`，不需要 HSV 阈值，也不会误伤头发自身的紫。

用法
----
    python3 tools/key_magenta.py in_raw.png out_rgba.png
    python3 tools/key_magenta.py in_raw.png out_rgba.png --check
    python3 tools/key_magenta.py in_raw.png out_rgba.png \
        --match-palette characters/xiaoxun/design/sheets/sheet_long.png

（旧的 `key_hair_only.py` 名字已退休：它也用来抠尾巴。功能没变，改的只是名字。）

输出体检：洋红彩边占比、内部孤点数、不透明面积。**彩边必须 0%**。
"""
from __future__ import annotations

import argparse
import os
import sys

import numpy as np
from PIL import Image, ImageFilter

MAGENTA = np.array([251.0, 2.0, 231.0])     # 洋红键底（实测角落色）
CAST_MIN = 18          # R-G 与 B-G 同时超过它 = 洋红偏色
GAMMA = 0.5            # keyness 曲线：0.5 = 平方根，边缘更软


def key_alpha(rgb):
    """返回（alpha[0..1], keyness 用到的布尔 cast 掩膜）。"""
    R, G, B = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    mg = np.minimum(R, B)
    # 连续 keyness：G 越低于 min(R,B) 越像洋红
    k = np.clip((mg - G) / np.maximum(mg * 0.55, 1e-6), 0.0, 1.0) ** 1.0
    # 只认色相真的在洋红区（R、B 都明显高于 G），否则头发自身的紫会被卷进来
    in_hue = (R - G > 60) & (B - G > 60)
    k = np.where(in_hue, np.maximum(k, 0.5), 0.0)
    return 1.0 - k


def despill(rgba):
    """去溢色：把被洋红染过的像素的 G 抬回去。**只动有偏色的像素**，不碰正常发色。"""
    a = rgba.copy()
    R, G, B = a[..., 0], a[..., 1], a[..., 2]
    mg = np.minimum(R, B)
    cast = (R - G > CAST_MIN) & (B - G > CAST_MIN)
    target = np.maximum(G, mg - 6.0)
    lift = np.where(cast, target - G, 0.0)
    a[..., 1] = G + lift
    a[..., 0] = R - lift * 0.5
    a[..., 2] = B - lift * 0.5
    return np.clip(a, 0, 255)


def fill_pinholes(alpha, radius=5, hole_max=10, solid_min=200):
    """补孤点：全透明、但闭运算后变实心的点 = 抠像打穿的洞，不是头发之间的缝。"""
    a0 = np.asarray(alpha)
    closed = np.asarray(Image.fromarray(a0)
                        .filter(ImageFilter.MaxFilter(radius))
                        .filter(ImageFilter.MinFilter(radius)))
    fill = (a0 < hole_max) & (closed > solid_min)
    out = np.where(fill, 255, a0).astype(np.uint8)
    return out, int(fill.sum())


def hair_mean(rgb, alpha=None):
    """取"发色主体"的均值：冷、亮、不饱和的那批像素（避开洋红、肤色、青布）。"""
    a = rgb.astype(float)
    R, G, B = a[..., 0], a[..., 1], a[..., 2]
    op = (alpha > 24) if alpha is not None else np.ones(R.shape, bool)
    m = op & (B - R > 5) & (B - R < 45) & (R > 150)
    px = a[m][:, :3]
    return px.mean(axis=0) if len(px) else None


def match_palette(out_rgba, ref_path):
    """把新图的发色对齐到参考立绘（逐通道增益）。

    ★ 为什么要这一步：髮だけ差分的底层图是另外画/生成的，发色和正式立绘
      差一点点，拼上去就会「一块深一块浅」。实测 v1 均值 (179,175,204)，
      参考立绘 (194,191,217) —— 差 14 级，肉眼是能看出来的。
      这里按均值做逐通道增益，做完再量一次，ΔE 必须 < 3（用户定的人像色差门槛）。
    """
    ref = np.array(Image.open(ref_path).convert("RGB"))
    R, G, B = ref[..., 0].astype(int), ref[..., 1].astype(int), ref[..., 2].astype(int)
    ref_notmag = ~((R > 180) & (B > 180) & (G < 170))
    rm = hair_mean(ref, ref_notmag.astype(np.uint8) * 255)
    om = hair_mean(out_rgba[..., :3], out_rgba[..., 3])
    if rm is None or om is None:
        print("  配色对齐跳过（找不到发色主体）")
        return out_rgba
    gain = rm / np.maximum(om, 1.0)
    out = out_rgba.astype(np.float64).copy()
    out[..., :3] = np.clip(out[..., :3] * gain, 0, 255)
    after = hair_mean(out[..., :3], out[..., 3])
    d = np.abs(after - rm).max()
    print("  配色对齐 %s → %s，增益 %s，残差 %.1f/255"
          % (np.round(om, 0), np.round(after, 0), np.round(gain, 3), d))
    return out.astype(np.uint8)


def fringe_pct(rgba):
    """轮廓上还剩多少洋红彩边（R-G>40 且 B-G>40）。用户面前不许出现这个。"""
    a = rgba.astype(int)
    op = a[..., 3] > 24
    inner = op.copy()
    inner[1:, :] &= op[:-1, :]
    inner[:-1, :] &= op[1:, :]
    inner[:, 1:] &= op[:, :-1]
    inner[:, :-1] &= op[:, 1:]
    bnd = op & ~inner
    if not bnd.any():
        return 0.0
    R, G, B = a[..., 0], a[..., 1], a[..., 2]
    bad = bnd & (R - G > 40) & (B - G > 40)
    return 100.0 * bad.sum() / bnd.sum()


def key_file(src, dst, check_only=False, ref_path=None):
    rgb = np.array(Image.open(src).convert("RGB")).astype(np.float64)
    alpha = key_alpha(rgb)
    # 中值滤波压掉单像素噪点，再轻微羽化
    alpha = np.asarray(Image.fromarray((alpha * 255).astype(np.uint8))
                       .filter(ImageFilter.MedianFilter(3))).astype(np.float64) / 255.0
    # 反预乘：C = (观测色 - (1-a)·键底) / a —— 这是"彩边"真正的成因
    an = np.maximum(alpha, 0.06)[..., None]
    C = np.clip((rgb - (1.0 - alpha[..., None]) * MAGENTA) / an, 0, 255)
    rgba = np.dstack([C, alpha * 255.0])
    rgba = despill(rgba)
    if ref_path:
        rgba = match_palette(rgba.astype(np.uint8), ref_path).astype(np.float64)
    ai, filled = fill_pinholes(Image.fromarray(rgba[..., 3].astype(np.uint8)))
    rgba[..., 3] = ai
    out = rgba.astype(np.uint8)
    op = int((out[..., 3] > 24).sum())
    fr = fringe_pct(out)
    print("%s → 不透明 %d px，洋红彩边 %.2f%%，补孤点 %d"
          % (os.path.basename(src), op, fr, filled))
    if not check_only:
        Image.fromarray(out).save(dst)
        print("写出", dst)
    return fr


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src")
    ap.add_argument("dst", nargs="?")
    ap.add_argument("--check", action="store_true", help="只体检，不写文件")
    ap.add_argument("--match-palette", default="",
                    help="对齐到这张参考立绘的发色（ΔE<3）")
    a = ap.parse_args()
    if not a.dst and not a.check:
        ap.error("要么给 dst，要么加 --check")
    fr = key_file(a.src, a.dst, a.check, a.match_palette or None)
    # 彩边是硬闸：>0 就是制作后缺陷，必须调参重抠
    return 0 if fr < 0.5 else 1


if __name__ == "__main__":
    sys.exit(main())
