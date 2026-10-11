#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""make_face_parts.py - 从"表情特写图"里切出可互换的眼睛/眉毛/嘴部件。

为什么需要它（LESSONS.md 二.4/二.5）：
  旧路线"从整张立绘抠眼睛闭合层"失败过四次。正确做法是让每张表情图都用同一取景生成，
  再由脚本**按眼睛位置自动对齐**，然后从每张图里切出眼睛/嘴的小块部件——
  这样所有部件天然落在同一坐标系里，互换时不会漂。

对齐原理：
  1. 抠掉洋红背景（复用 prepare_sprites 的抠图逻辑）；
  2. 检测虹膜（蓝瞳）或眼线（深色）得到左右眼中心；
  3. 用"两眼距离"做缩放、用"两眼中点"做平移，把每张图归一到基准取景；
  4. 按基准框（相对脸宽/眼距的固定比例）切眼睛、眉毛、嘴；
  5. 输出部件 + 对齐报告 + 可视化检查图（带检测标记），便于人工复核。

用法：
  python3 tools/make_face_parts.py --character xiaoxun --form teen \
      --src characters/xiaoxun/parts_src/expressions \
      --ref characters/xiaoxun/forms/teen/sprites/body_full.png \
      --sprite-offset 201,68 --out characters/xiaoxun/forms/teen/sprites \
      --report /tmp/face_parts_report.json
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from glob import glob

import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from prepare_sprites import key_out, keep_largest_blob, magenta_residue  # noqa: E402

# ---------------------------------------------------------------- 基准取景
# 由 body_full.png 量得（精灵坐标，445x1292）：
#   左眼框 96..215 / 右眼框 228..347，眼睛纵向 178..246
REF = {
    "eye_left_box": (96, 178, 215, 246),
    "eye_right_box": (228, 178, 347, 246),
    "mouth_box": (212, 246, 256, 278),
    "brow_box": (96, 150, 347, 182),
}

CANON = {
    "eye_dist": 131.0,        # 两眼中心距离（body_full 量得：287.5-156.5）
    "eye_mid_y": 212.0,       # 两眼中心连线的高度
    "eye_mid_x": 222.0,       # 两眼中心连线的中点 x
}


def face_box(rgba: np.ndarray):
    """肤色脸框 (x0,y0,x1,y1)。用最大连通肤色块的 2%~98% 分位，避免被发丝/衣领拉偏。"""
    r, g, b, a = (rgba[..., i].astype(np.int16) for i in range(4))
    skin = (a > 128) & (r > 200) & (r > g + 10) & (g > b) & (b > 150)
    skin = keep_largest_blob(skin.astype(np.uint8) * 255, 0.01) > 0
    ys, xs = np.where(skin)
    if len(xs) < 100:
        return None
    return (int(np.percentile(xs, 2)), int(np.percentile(ys, 2)),
            int(np.percentile(xs, 98)), int(np.percentile(ys, 98)))


def detect_eyes(rgba: np.ndarray) -> tuple:
    """返回 (left_center, right_center, method)。只在脸框内找虹膜，避免蓝色发尾误判。

    闭眼/困倦图没有可见虹膜，会返回 None，由调用方走脸框兜底。
    """
    h, w, _ = rgba.shape
    fb = face_box(rgba)
    if fb is None:
        return None, None, "未检测到脸部"
    fx0, fy0, fx1, fy1 = fb
    fh = fy1 - fy0
    fw = fx1 - fx0
    # 眼睛只可能出现在脸的上半部中段、左右两侧 15%~85%
    ey0, ey1 = fy0 + int(fh * 0.25), fy0 + int(fh * 0.65)
    ex0, ex1 = fx0 + int(fw * 0.10), fx1 - int(fw * 0.10)
    r, g, b, a = (rgba[..., i].astype(np.int16) for i in range(4))
    roi = np.zeros((h, w), dtype=bool)
    roi[ey0:ey1, ex0:ex1] = True
    op = (a > 128) & roi
    iris = op & (b > r + 25) & (b > 110) & (g > 60) & (b < 250)
    ys, xs = np.where(iris)
    if len(xs) < 40:
        return None, None, "未检测到虹膜（闭眼/困倦）"
    mid = (fx0 + fx1) / 2.0
    left = xs < mid
    right = ~left
    if left.sum() < 20 or right.sum() < 20:
        return None, None, "虹膜只出现在一侧"
    lc = (float(xs[left].mean()), float(ys[left].mean()))
    rc = (float(xs[right].mean()), float(ys[right].mean()))
    if abs(lc[1] - rc[1]) > fh * 0.08 or (rc[0] - lc[0]) < fw * 0.2:
        return None, None, "虹膜位置不合理"
    return lc, rc, "iris"


def face_align(rgba: np.ndarray) -> tuple:
    """脸框对齐：用肤色区域估算缩放与平移（闭眼等表情的兜底）。"""
    r, g, b, a = (rgba[..., i].astype(np.int16) for i in range(4))
    skin = (a > 128) & (r > 200) & (r > g + 10) & (g > b) & (b > 150)
    skin = keep_largest_blob(skin.astype(np.uint8) * 255, 0.01) > 0
    ys, xs = np.where(skin)
    if len(xs) < 100:
        return None
    cx = float((xs.min() + xs.max()) / 2.0)
    cy = float((ys.min() + ys.max()) / 2.0)
    return cx, cy


def align_to_canon(rgba: np.ndarray, lc, rc, face_center) -> tuple:
    """计算把该图归一到基准取景所需的 (scale, dx, dy)。

    返回 (scale, dx, dy)：目标坐标 = (原坐标 - 源锚点) * scale + 基准锚点
    """
    if lc and rc:
        dist = ((rc[0] - lc[0]) ** 2 + (rc[1] - lc[1]) ** 2) ** 0.5
        if dist < 10:
            return None
        scale = CANON["eye_dist"] / dist
        mx = (lc[0] + rc[0]) / 2.0
        my = (lc[1] + rc[1]) / 2.0
        return scale, mx, my
    if face_center:
        # 兜底：按脸宽给出近似缩放（脸宽 ≈ 1.35 倍眼距）
        scale = 1.0
        return scale, face_center[0], CANON["eye_mid_y"]
    return None


def warp_to_canon(rgba: np.ndarray, scale: float, sx: float, sy: float) -> Image.Image:
    """按 (scale, sx, sy) 重采样成基准取景的图。"""
    im = Image.fromarray(rgba, "RGBA")
    w, h = im.size
    nw = max(1, int(round(w * scale)))
    nh = max(1, int(round(h * scale)))
    im = im.resize((nw, nh), Image.LANCZOS)
    # 缩放后源锚点的位置
    ax = sx * scale
    ay = sy * scale
    canvas = Image.new("RGBA", (max(nw, 600), max(nh, 600)))
    canvas.alpha_composite(im, (int(round(CANON["eye_mid_x"] - ax)),
                                int(round(CANON["eye_mid_y"] - ay))))
    return canvas


def crop_box(canvas: Image.Image, box, pad=2):
    x0, y0, x1, y1 = box
    return canvas.crop((max(0, x0 - pad), max(0, y0 - pad), x1 + pad, y1 + pad))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--character", required=True)
    ap.add_argument("--form", required=True)
    ap.add_argument("--src", required=True, help="表情特写图目录（*.png）")
    ap.add_argument("--out", required=True, help="输出部件目录")
    ap.add_argument("--only", default="", help="只处理名字含该子串的文件")
    ap.add_argument("--check-dir", default="/tmp/face_check", help="对齐检查图输出目录")
    ap.add_argument("--report", default="/tmp/face_parts_report.json")
    ap.add_argument("--dry-run", action="store_true", help="只检测与画检查图，不写部件")
    args = ap.parse_args()

    os.makedirs(args.out, exist_ok=True)
    os.makedirs(args.check_dir, exist_ok=True)

    files = sorted(glob(os.path.join(args.src, "*.png")))
    if args.only:
        files = [f for f in files if args.only in os.path.basename(f)]
    if not files:
        print(f"[错误] {args.src} 下没有 png", file=sys.stderr)
        return 2

    report = {"source_dir": args.src, "items": [], "errors": []}
    sheet_rows = []

    for path in files:
        name = os.path.splitext(os.path.basename(path))[0]
        try:
            im = Image.open(path)
            if im.mode != "RGB":
                im = im.convert("RGB")
            rgba_im, key = key_out(im, tol=60, despill=1)
            arr = np.asarray(rgba_im)
            lc, rc, method = detect_eyes(arr)
            face_center = face_align(arr) if (lc is None or rc is None) else None
            al = align_to_canon(arr, lc, rc, face_center)
            if al is None:
                report["errors"].append({"file": name, "reason": "无法对齐（未检测到眼睛或脸部）"})
                print(f"  [跳过] {name}: 无法对齐")
                continue
            scale, sx, sy = al
            canvas = warp_to_canon(arr, scale, sx, sy)

            item = {
                "name": name,
                "source": os.path.basename(path),
                "key_color": list(key),
                "detect": method,
                "eye_left": lc, "eye_right": rc,
                "align": {"scale": round(scale, 4), "src_anchor": [round(sx, 1), round(sy, 1)]},
                "parts": [],
            }

            if not args.dry_run:
                for part_name, box in (
                    ("eye_open_left", REF["eye_left_box"]),
                    ("eye_open_right", REF["eye_right_box"]),
                    ("brow", REF["brow_box"]),
                    ("mouth", REF["mouth_box"]),
                ):
                    piece = crop_box(canvas, box)
                    out_name = f"{part_name}__{name}.png"
                    piece.save(os.path.join(args.out, out_name))
                    pa = np.asarray(piece)
                    item["parts"].append({
                        "file": out_name,
                        "size": [piece.width, piece.height],
                        "magenta_residue": magenta_residue(pa),
                        "opaque_ratio": round(float((pa[..., 3] > 32).mean()), 4),
                    })

            # 可视化检查图：原图上半 + 检测点 + 切框
            vis = rgba_im.convert("RGB")
            d = ImageDraw.Draw(vis)
            if lc:
                d.ellipse([lc[0] - 4, lc[1] - 4, lc[0] + 4, lc[1] + 4], outline=(255, 0, 0), width=2)
            if rc:
                d.ellipse([rc[0] - 4, rc[1] - 4, rc[0] + 4, rc[1] + 4], outline=(255, 0, 0), width=2)
            if face_center:
                d.line([face_center[0] - 10, face_center[1], face_center[0] + 10, face_center[1]], fill=(0, 128, 255), width=2)
            vis.save(os.path.join(args.check_dir, f"detect_{name}.png"))
            canvas.convert("RGB").save(os.path.join(args.check_dir, f"aligned_{name}.png"))
            sheet_rows.append((name, canvas))
            report["items"].append(item)
            print(f"  [对齐] {name:26s} 方式={method:8s} 缩放={scale:.3f} 锚点=({sx:.0f},{sy:.0f})")
        except Exception as exc:  # noqa: BLE001
            report["errors"].append({"file": name, "reason": str(exc)})
            print(f"  [异常] {name}: {exc}", file=sys.stderr)

    # 对齐总览图：把所有归一后的图并排，检查眼睛是否在同一水平线上
    if sheet_rows:
        cw, ch = sheet_rows[0][1].size
        gap = 8
        sheet = Image.new("RGBA", (cw * len(sheet_rows) + gap * (len(sheet_rows) + 1),
                                  ch + gap * 2 + 24), (245, 248, 252, 255))
        d = ImageDraw.Draw(sheet)
        # 基准眼睛水平线
        for i, (name, canvas) in enumerate(sheet_rows):
            x = gap + i * (cw + gap)
            sheet.alpha_composite(canvas, (x, gap))
            d.line([(x, gap + CANON["eye_mid_y"]), (x + cw, gap + CANON["eye_mid_y"])],
                   fill=(255, 0, 0), width=1)
            d.text((x + 4, ch + gap + 4), name, fill=(60, 70, 90))
        sheet.convert("RGB").save(os.path.join(args.check_dir, "sheet_aligned.png"))
        print(f"\n对齐总览：{os.path.join(args.check_dir, 'sheet_aligned.png')}")

    with open(args.report, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"报告：{args.report}（成功 {len(report['items'])}，失败 {len(report['errors'])}）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
