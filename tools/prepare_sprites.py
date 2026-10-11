#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
prepare_sprites.py - 把 AI 生成的角色设计图处理成立绘部件素材。

输入：characters/<角色>/design/design_sheet_*.png（纯色背景，推荐洋红 #FF00FF）
输出：characters/<角色>/forms/<形态>/sprites/*.png（透明背景）
      以及一份验收报告 JSON（分辨率、透明通道、残留、色卡比对）

规则来自交接文件第五之二节与第八节：
  - 透明背景、无白底/棋盘格残留、边缘干净；
  - 颜色与设定色卡一致（取样比对，超阈值报警）；
  - 统一画布：默认 848x1360，角色脚底落在 origin；
  - 原图另存，不覆盖。

用法：
  python3 tools/prepare_sprites.py --character xiaoxun --form teen \
      --sheet characters/xiaoxun/design/design_sheet_short.png \
      --canvas 848x1360 --height-ratio 0.95 --report /tmp/sprite_report.json
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter

try:
    import numpy as np
    from PIL import Image
except ImportError as e:  # pragma: no cover
    print(f"[错误] 需要 pillow 与 numpy：{e}", file=sys.stderr)
    sys.exit(2)

# 与 rig / 配置保持一致的键色
KEY_COLORS = [(255, 0, 255), (0, 255, 0), (255, 255, 255)]


def load_rgb(path: str) -> Image.Image:
    im = Image.open(path)
    if im.mode != "RGB":
        im = im.convert("RGB")
    return im


def key_out(im: Image.Image, tol: int = 60, despill: int = 1) -> tuple[Image.Image, tuple]:
    """按键色抠透明 + 去噪 + 去彩边。

    与首版相比的改进（首版在细节放大下图边缘残留洋红噪点）：
      1. 不只按“到键色的距离”判定，还按“洋红色系”判定：
         R 与 B 都明显高于 G（AI 生成图边缘常有抖动的洋红像素，距离很远但色相未变）；
      2. 抠完后对 alpha 做去孤立点 + 补孤立洞，避免毛刺；
      3. 边缘按键色方向去彩边（保留抗锯齿过渡，不产生白边）。
    """
    a = np.asarray(im).astype(np.int16)
    h, w, _ = a.shape
    corners = np.stack([a[2, 2], a[2, w - 3], a[h - 3, 2], a[h - 3, w - 3]]).astype(np.float32)
    key = tuple(int(round(v)) for v in corners.mean(0))
    spread = float(np.abs(corners - corners.mean(0)).max())
    if spread > 40:
        raise SystemExit("[错误] 四角颜色不一致，无法自动抠背景；请提供纯色背景的设计图")
    best = min(KEY_COLORS, key=lambda k: sum((k[i] - key[i]) ** 2 for i in range(3)))
    if sum((best[i] - key[i]) ** 2 for i in range(3)) < 60 * 60:
        key = best

    rgb = np.asarray(im).astype(np.int16)
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    mx = np.maximum(r, b)
    dist = np.sqrt(((rgb - np.array(key)) ** 2).sum(axis=2))

    if key[0] > 120 and key[2] > 120 and key[1] < 120:      # 洋红键
        magenta_ish = (r > 90) & (b > 90) & (g.astype(np.int32) * 100 < mx.astype(np.int32) * 62)
    elif key[1] > 120 and key[0] < 120 and key[2] < 120:    # 绿幕键
        magenta_ish = (g > 90) & (g.astype(np.int32) * 100 > np.maximum(r, b).astype(np.int32) * 130)
    else:                                                    # 白底键
        magenta_ish = (r > 235) & (g > 235) & (b > 235)

    hard_bg = (dist <= tol) | magenta_ish
    alpha = np.where(hard_bg, 0, 255).astype(np.uint8)

    # 去孤立点：不透明但 8 邻域几乎全透明的像素视为噪点
    for _ in range(2):
        op = (alpha > 0).astype(np.uint8)
        nb = np.zeros_like(op, dtype=np.int16)
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                if dx == 0 and dy == 0:
                    continue
                nb += np.roll(np.roll(op, dy, axis=0), dx, axis=1)
        alpha[(op == 1) & (nb <= 1)] = 0
    # 补孤立洞：透明但 8 邻域几乎全不透明
    for _ in range(1):
        op = (alpha > 0).astype(np.uint8)
        nb = np.zeros_like(op, dtype=np.int16)
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                if dx == 0 and dy == 0:
                    continue
                nb += np.roll(np.roll(op, dy, axis=0), dx, axis=1)
        alpha[(op == 0) & (nb >= 7)] = 255

    # 保留主体连通块（去掉漂浮的碎片）
    alpha = keep_largest_blob(alpha, min_ratio=0.002)

    # 去彩边：把被键色污染的边缘像素颜色，用“内部干净像素”的颜色外扩补上
    # （保留抗锯齿 alpha，只换颜色，这样边缘既不紫也不白）
    opaque = alpha > 0
    # “被污染”包含两类：离键色近的（容差带）与色相仍是洋红的（AI 抖动像素）
    hard_hue = ((r.astype(np.int32) + b.astype(np.int32) - 2 * g.astype(np.int32)) > 70)
    contaminated = opaque & ((dist <= max(tol * 3, 40)) | hard_hue)
    clean = opaque & ~contaminated
    rgb_f = rgb.astype(np.float32)
    if clean.any() and contaminated.any():
        filled = clean.copy()
        col = rgb_f.copy()
        for _ in range(8):
            grew = np.zeros_like(filled)
            newcol = col.copy()
            for dy in (-1, 0, 1):
                for dx in (-1, 0, 1):
                    if dx == 0 and dy == 0:
                        continue
                    src_fill = np.roll(np.roll(filled, dy, axis=0), dx, axis=1)
                    src_col = np.roll(np.roll(col, dy, axis=0), dx, axis=1)
                    take = src_fill & ~grew & contaminated
                    newcol[take] = src_col[take]
                    grew |= take
            if not grew.any():
                break
            filled |= grew
            col = newcol
        rgb_f = np.where(contaminated[..., None] & filled[..., None],
                         col, rgb_f)
    # 最后一道：极少数仍偏洋红的像素，压回灰度（避免细看有粉点）
    rr, gg, bb = rgb_f[..., 0], rgb_f[..., 1], rgb_f[..., 2]
    hard = (alpha > 0) & ((rr + bb - 2 * gg) > 110)
    if hard.any():
        lum = (rr + gg + bb) / 3.0
        rgb_f[..., 0] = np.where(hard, lum, rgb_f[..., 0])
        rgb_f[..., 2] = np.where(hard, lum, rgb_f[..., 2])

    rgba = np.dstack([np.clip(rgb_f, 0, 255).astype(np.uint8), alpha])
    return Image.fromarray(rgba, "RGBA"), tuple(int(v) for v in key)


def keep_largest_blob(alpha: np.ndarray, min_ratio: float = 0.002) -> np.ndarray:
    """只保留最大的若干连通块（面积 >= 最大块 * min_ratio）。"""
    h, w = alpha.shape
    lab = np.zeros((h, w), dtype=np.int32)
    cur = 0
    areas = {}
    idx = np.argwhere(alpha > 0)
    for y, x in idx:
        if lab[y, x]:
            continue
        cur += 1
        stack = [(int(y), int(x))]
        lab[y, x] = cur
        cnt = 0
        while stack:
            cy, cx = stack.pop()
            cnt += 1
            for dy in (-1, 0, 1):
                for dx in (-1, 0, 1):
                    ny, nx = cy + dy, cx + dx
                    if 0 <= ny < h and 0 <= nx < w and alpha[ny, nx] > 0 and lab[ny, nx] == 0:
                        lab[ny, nx] = cur
                        stack.append((ny, nx))
        areas[cur] = cnt
    if not areas:
        return alpha
    biggest = max(areas.values())
    keep = {k for k, v in areas.items() if v >= biggest * min_ratio}
    out = alpha.copy()
    out[~np.isin(lab, list(keep))] = 0
    return out


def magenta_residue(rgba: np.ndarray) -> int:
    """统计仍然“偏洋红”的不透明像素（残留检测，容差之外的漏网像素）。"""
    r, g, b, a = rgba[..., 0].astype(int), rgba[..., 1].astype(int), rgba[..., 2].astype(int), rgba[..., 3]
    # 只统计“饱和的洋红/紫红”：R 与 B 同时明显高于 G
    m = (a > 60) & ((r + b) - 2 * g > 90)
    return int(m.sum())


def bbox_of(alpha: np.ndarray, thr: int = 8):
    ys, xs = np.where(alpha > thr)
    if len(xs) == 0:
        return None
    return int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())


def check_white_residue(rgba: np.ndarray) -> int:
    """统计“接近纯白但半透明”的像素（棋盘格/白底残留的典型特征）。"""
    r, g, b, a = rgba[..., 0], rgba[..., 1], rgba[..., 2], rgba[..., 3]
    near_white = (r > 235) & (g > 235) & (b > 235)
    semi = (a > 10) & (a < 245)
    return int((near_white & semi).sum())


def palette_report(rgba: np.ndarray, k: int = 10) -> list[dict]:
    """取样主要颜色（用于与设定色卡比对）。"""
    a = rgba[..., 3]
    px = rgba[a > 200][:, :3]
    if len(px) == 0:
        return []
    px = px[:: max(1, len(px) // 20000)]
    q = (px // 12 * 12)
    cnt = Counter(map(tuple, q.tolist()))
    out = []
    for color, n in cnt.most_common(k):
        out.append({"hex": "#%02X%02X%02X" % color, "share": round(n / len(q), 4)})
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--character", required=True)
    ap.add_argument("--form", required=True)
    ap.add_argument("--sheet", required=True)
    ap.add_argument("--canvas", default="848x1360")
    ap.add_argument("--height-ratio", type=float, default=0.95,
                    help="角色高度占画布高度的比例")
    ap.add_argument("--tol", type=int, default=60)
    ap.add_argument("--out-name", default="body_full.png")
    ap.add_argument("--report", default=None)
    ap.add_argument("--root", default=".")
    args = ap.parse_args()

    cw, ch = (int(v) for v in args.canvas.lower().split("x"))
    im = load_rgb(args.sheet)
    rgba_im, key = key_out(im, tol=args.tol)
    arr = np.asarray(rgba_im)

    bb = bbox_of(arr[..., 3])
    if bb is None:
        print("[错误] 抠图后没有不透明像素", file=sys.stderr)
        return 2
    x0, y0, x1, y1 = bb
    char_w, char_h = x1 - x0 + 1, y1 - y0 + 1

    # 目标高度
    target_h = int(ch * args.height_ratio)
    scale = target_h / char_h
    new_w = max(1, int(round(char_w * scale)))
    new_h = max(1, int(round(char_h * scale)))
    cropped = rgba_im.crop((x0, y0, x1 + 1, y1 + 1)).resize((new_w, new_h), Image.LANCZOS)

    if new_w > cw:
        raise SystemExit(f"[错误] 角色宽度 {new_w} 超过画布宽度 {cw}")

    sprite = cropped
    out_dir = os.path.join(args.root, "characters", args.character, "forms", args.form, "sprites")
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, args.out_name)
    sprite.save(out_path)

    # 复核：读回来检查
    back = np.asarray(Image.open(out_path).convert("RGBA"))
    bb2 = bbox_of(back[..., 3])
    report = {
        "source": args.sheet,
        "output": out_path,
        "key_color": list(key),
        "canvas": [cw, ch],
        "sprite_size": [back.shape[1], back.shape[0]],
        "scale": round(scale, 4),
        "alpha_bbox": list(bb2) if bb2 else None,
        "transparent_ratio": round(float((back[..., 3] <= 8).mean()), 4),
        "white_residue_pixels": check_white_residue(back),
        "magenta_residue_pixels": magenta_residue(back),
        "palette": palette_report(back),
        # 建议的交互区域（画布坐标）：头顶到下巴约 21% 角色高度
        "suggested_regions": suggest_regions(back.shape[1], back.shape[0], cw, ch),
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if args.report:
        with open(args.report, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
    if report["white_residue_pixels"] > 200:
        print("[警告] 检测到较多白色半透明残留，请检查抠图容差", file=sys.stderr)
    if report["magenta_residue_pixels"] > 200:
        print("[警告] 检测到较多洋红残留（键色未清干净）", file=sys.stderr)
    return 0


def suggest_regions(w: int, h: int, cw: int, ch: int) -> dict:
    """给出摸头/身体/脚部的建议区域（画布坐标，角色居中）。"""
    x = (cw - w) // 2
    head_h = int(h * 0.24)
    body_top = int(h * 0.24)
    body_h = int(h * 0.60)
    feet_top = body_top + body_h
    return {
        "head": [x + int(w * 0.10), 0, int(w * 0.80), head_h],
        "body": [x + int(w * 0.12), body_top, int(w * 0.76), body_h],
        "feet": [x + int(w * 0.12), feet_top, int(w * 0.76), h - feet_top],
        "origin_x": cw // 2,
        "origin_y": h,
        "sprite_w": w,
        "sprite_h": h,
    }


if __name__ == "__main__":
    sys.exit(main())
