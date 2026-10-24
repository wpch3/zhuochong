#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""make_face_parts.py - 从统一取景表情图里切出左右眼与嘴部候选部件。

为什么需要它（LESSONS.md 二.4/二.5）：
  旧路线"从整张立绘抠眼睛闭合层"失败过四次。正确做法是让每张表情图都用同一取景生成，
  再由脚本**按眼睛位置自动对齐**，然后从每张图里切出眼睛/嘴的小块部件——
  这样所有部件天然落在同一坐标系里，互换时不会漂。

对齐原理：
  1. 抠掉洋红背景（复用 prepare_sprites 的抠图逻辑）；
  2. 在上半脸检测虹膜；闭眼图改用受限脸框估计眼裂锚点，避免蓝发夹/衣服误检；
  3. 用与 body_full 对应的眼距和眼中心缩放/平移；
  4. 按实测基准框切左右眼，并把嘴部柔边映射到统一位置；
  5. 输出部件 + 对齐报告 + 可视化检查图（带检测标记），便于人工复核。

用法：
  python3 tools/make_face_parts.py --character xiaoxun --form teen \
      --src characters/xiaoxun/parts_src/expressions_a \
      --include characters/xiaoxun/parts_src/expressions/smile.png \
      --out /tmp/xiaoxun_face_parts --report /tmp/face_parts_report.json
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
# 按 body_full.png 的实际虹膜中心重测，而不是把切框中心误作眼球中心。
REF = {
    "eye_left_box": (145, 180, 216, 228),
    "eye_right_box": (230, 180, 301, 228),
    "mouth_box": (195, 236, 239, 264),  # 44x28，中心对准原立绘嘴线
}

CANON = {
    "eye_dist": 86.0,          # body_full.png 实测虹膜中心约 x=181 / 266
    "eye_mid_y": 204.0,       # body_full.png 虹膜中心约 y=204
    "eye_mid_x": 223.5,       # 双眼视觉中心
}


def face_box(rgba: np.ndarray):
    """估计上半身头像中的脸框，排除颈部/手臂等下方肤色区域。

    旧实现把连到脖子、手和身体的肤色块当作整张脸，ROI 因而落到胸口，
    还会把蓝色发夹/衣服误当虹膜。输入是表情特写图，限定搜索在画布上方 70%。
    """
    h, w, _ = rgba.shape
    r, g, b, a = (rgba[..., i].astype(np.int16) for i in range(4))
    skin = (a > 128) & (r > 200) & (r > g + 10) & (g > b) & (b > 150)
    skin[int(h * 0.70):, :] = False
    skin[:, :int(w * 0.18)] = False
    skin[:, int(w * 0.82):] = False
    skin = keep_largest_blob(skin.astype(np.uint8) * 255, 0.01) > 0
    ys, xs = np.where(skin)
    if len(xs) < 100:
        return None
    return (float(np.percentile(xs, 2)), float(np.percentile(ys, 2)),
            float(np.percentile(xs, 98)), float(np.percentile(ys, 98)))


def detect_eyes(rgba: np.ndarray) -> tuple:
    """返回 (left_center, right_center, method)。虹膜只在上半脸中找；闭眼用几何锚点。

    蓝色鲸鱼发夹、蓝发尾和衣服会被误当虹膜，故不再用整张脸/身体肤色框定位。
    闭眼表情没有虹膜时，用脸部肤色框估计眼距和眼线高度，保持坐标系稳定。
    """
    h, w, _ = rgba.shape
    fb = face_box(rgba)
    if fb is None:
        return None, None, "未检测到脸部"
    fx0, fy0, fx1, fy1 = fb
    fh = fy1 - fy0
    fw = fx1 - fx0
    mid = (fx0 + fx1) / 2.0
    # 真正的眼睛在面部框上部；排除发夹、下方衣服及颈部蓝色区域。
    ey0, ey1 = int(fy0 + fh * 0.20), int(fy0 + fh * 0.52)
    ex0, ex1 = int(fx0 + fw * 0.08), int(fx1 - fw * 0.08)
    r, g, b, a = (rgba[..., i].astype(np.int16) for i in range(4))
    roi = np.zeros((h, w), dtype=bool)
    roi[ey0:ey1, ex0:ex1] = True
    iris = (a > 128) & roi & (b > r + 25) & (b > 110) & (g > 60) & (b < 250)
    ys, xs = np.where(iris)
    if len(xs) >= 40:
        left = xs < mid
        right = ~left
        if left.sum() >= 20 and right.sum() >= 20:
            lc = (float(xs[left].mean()), float(ys[left].mean()))
            rc = (float(xs[right].mean()), float(ys[right].mean()))
            if abs(lc[1] - rc[1]) <= fh * 0.10 and (rc[0] - lc[0]) >= fw * 0.20:
                return lc, rc, "iris"

    # 闭眼/困倦/上扬眼线时不依赖虹膜。宽度比例在同批生成头像中稳定，
    # 以脸宽估算眼距，再与虹膜路线使用相同的 CANON 归一化。
    eye_y = fy0 + fh * 0.25
    eye_dist = fw * 0.68
    lc = (mid - eye_dist / 2.0, eye_y)
    rc = (mid + eye_dist / 2.0, eye_y)
    return lc, rc, "face_geometry"


def face_align(rgba: np.ndarray) -> tuple:
    """保留旧调用接口：返回受限脸框中心，供诊断/兜底使用。"""
    fb = face_box(rgba)
    if fb is None:
        return None
    x0, y0, x1, y1 = fb
    return (float((x0 + x1) / 2.0), float((y0 + y1) / 2.0))


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


def warp_to_canon(rgba: np.ndarray, scale: float, sx: float, sy: float,
                  target_y: float | None = None) -> Image.Image:
    """按锚点重采样成基准取景；闭眼几何锚点可单独对准眼睑线。"""
    im = Image.fromarray(rgba, "RGBA")
    w, h = im.size
    nw = max(1, int(round(w * scale)))
    nh = max(1, int(round(h * scale)))
    im = im.resize((nw, nh), Image.LANCZOS)
    # 缩放后源锚点的位置
    ax = sx * scale
    ay = sy * scale
    canvas = Image.new("RGBA", (max(nw, 600), max(nh, 600)))
    y_anchor = CANON["eye_mid_y"] if target_y is None else target_y
    canvas.alpha_composite(im, (int(round(CANON["eye_mid_x"] - ax)),
                                int(round(y_anchor - ay))))
    return canvas


def crop_box(canvas: Image.Image, box, pad=2):
    x0, y0, x1, y1 = box
    return canvas.crop((max(0, x0 - pad), max(0, y0 - pad), x1 + pad, y1 + pad))


def mask_eye_patch(piece: Image.Image) -> Image.Image:
    """给眼部小面板做椭圆软边，消除切件的矩形边缘而保留完整眼型。"""
    from PIL import ImageFilter

    rgba = piece.convert("RGBA")
    w, h = rgba.size
    mask = Image.new("L", (w, h), 0)
    draw = ImageDraw.Draw(mask)
    # 眼框切片含额头/脸颊；用杏仁形眼裂蒙版覆盖原眼本体，
    # 使闭眼表情能遮住底图虹膜，同时避免矩形或大椭圆把刘海/脸颊烘焙进去。
    cx = w / 2.0
    points = [
        (2, h * 0.50), (w * 0.18, h * 0.27), (cx, 2),
        (w * 0.82, h * 0.27), (w - 2, h * 0.50),
        (w * 0.82, h * 0.73), (cx, h - 2), (w * 0.18, h * 0.73),
    ]
    draw.polygon(points, fill=255)
    mask = mask.filter(ImageFilter.GaussianBlur(radius=1.0))
    alpha = np.asarray(rgba.getchannel("A")).astype(np.float32)
    alpha *= np.asarray(mask).astype(np.float32) / 255.0
    rgba.putalpha(Image.fromarray(np.clip(alpha, 0, 255).astype(np.uint8)))
    return rgba


def fit_mouth(piece: Image.Image) -> Image.Image:
    """把同取景嘴部面板映射到基准锚框，以柔边覆盖底图旧嘴线并避免重影。"""
    from PIL import ImageFilter

    x0, y0, x1, y1 = REF["mouth_box"]
    target = Image.new("RGBA", (x1 - x0, y1 - y0), (0, 0, 0, 0))
    panel = piece.convert("RGBA").resize(target.size, Image.Resampling.LANCZOS)
    mask = Image.new("L", target.size, 0)
    ImageDraw.Draw(mask).ellipse((1, 1, target.width - 2, target.height - 2), fill=255)
    mask = mask.filter(ImageFilter.GaussianBlur(radius=1.5))
    alpha = np.asarray(panel.getchannel("A")).astype(np.float32)
    alpha *= np.asarray(mask).astype(np.float32) / 255.0
    panel.putalpha(Image.fromarray(np.clip(alpha, 0, 255).astype(np.uint8)))
    target.alpha_composite(panel)
    return target


def save_candidate_pair(piece: Image.Image, out_path: str) -> None:
    """输出候选原尺寸与 2×运行时贴图；两者保留同一锚框与透明通道。"""
    piece = piece.convert("RGBA")
    piece.save(out_path)
    hires = piece.resize((piece.width * 2, piece.height * 2), Image.Resampling.LANCZOS)
    hires.save(os.path.splitext(out_path)[0] + "@2x.png")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--character", required=True)
    ap.add_argument("--form", required=True)
    ap.add_argument("--src", required=True, help="表情特写图目录（*.png）")
    ap.add_argument("--include", action="append", default=[],
                    help="额外纳入的表情 PNG，可重复指定（如 smile 基准图）")
    ap.add_argument("--base", default="", help="可选 body_full.png，用其原始部件生成 calm 基准")
    ap.add_argument("--out", required=True, help="输出部件目录")
    ap.add_argument("--only", default="", help="只处理名字含该子串的文件")
    ap.add_argument("--check-dir", default="/tmp/face_check", help="对齐检查图输出目录")
    ap.add_argument("--report", default="/tmp/face_parts_report.json")
    ap.add_argument("--dry-run", action="store_true", help="只检测与画检查图，不写部件")
    args = ap.parse_args()

    os.makedirs(args.out, exist_ok=True)
    os.makedirs(args.check_dir, exist_ok=True)

    files = sorted(set(glob(os.path.join(args.src, "*.png")) + args.include))
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
            # 闭眼几何锚点对应睫毛线，比开眼虹膜中心略高；匹配 body_full 的闭眼部件位置。
            target_eye_y = CANON["eye_mid_y"] - 5.0 if method == "face_geometry" else CANON["eye_mid_y"]
            canvas = warp_to_canon(arr, scale, sx, sy, target_y=target_eye_y)

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
                parts = [
                    ("eye_left", REF["eye_left_box"]),
                    ("eye_right", REF["eye_right_box"]),
                ]
                for part_name, box in parts:
                    piece = mask_eye_patch(crop_box(canvas, box))
                    out_name = f"{part_name}__{name}.png"
                    save_candidate_pair(piece, os.path.join(args.out, out_name))
                    pa = np.asarray(piece)
                    item["parts"].append({
                        "file": out_name,
                        "size": [piece.width, piece.height],
                        "origin": [max(0, box[0] - 2), max(0, box[1] - 2)],
                        "magenta_residue": magenta_residue(pa),
                        "opaque_ratio": round(float((pa[..., 3] > 32).mean()), 4),
                    })

                # 嘴部在不同表情中的实际 y 会有轻微变化，先在对齐脸的中央下半区取候选，
                # 去肤色后再放入 body_full 嘴部的统一锚框，不能直接硬切 REF 的错误坐标。
                mouth_source = canvas.crop((190, 236, 254, 272))
                mouth = fit_mouth(mouth_source)
                out_name = f"mouth__{name}.png"
                save_candidate_pair(mouth, os.path.join(args.out, out_name))
                pa = np.asarray(mouth)
                item["parts"].append({
                    "file": out_name,
                    "size": [mouth.width, mouth.height],
                    "origin": [REF["mouth_box"][0], REF["mouth_box"][1]],
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

    # 原始立绘就是 calm 状态，按同样锚框存一份中性基准，补齐 9 种状态中的 calm。
    if args.base:
        try:
            base_path = args.base
            base = Image.open(base_path).convert("RGBA")
            calm = {"name": "calm", "source": base_path, "detect": "body_reference",
                    "align": {"scale": 1.0, "src_anchor": [CANON["eye_mid_x"], CANON["eye_mid_y"]]},
                    "parts": []}
            if not args.dry_run:
                for part_name, box in (("eye_left", REF["eye_left_box"]),
                                       ("eye_right", REF["eye_right_box"])):
                    piece = mask_eye_patch(crop_box(base, box))
                    out_name = f"{part_name}__calm.png"
                    save_candidate_pair(piece, os.path.join(args.out, out_name))
                    pa = np.asarray(piece)
                    calm["parts"].append({"file": out_name, "size": list(piece.size),
                                          "origin": [max(0, box[0] - 2), max(0, box[1] - 2)],
                                          "magenta_residue": magenta_residue(pa),
                                          "opaque_ratio": round(float((pa[..., 3] > 32).mean()), 4)})
                mouth = fit_mouth(base.crop(REF["mouth_box"]))
                out_name = "mouth__calm.png"
                save_candidate_pair(mouth, os.path.join(args.out, out_name))
                pa = np.asarray(mouth)
                calm["parts"].append({"file": out_name, "size": list(mouth.size),
                                      "origin": [REF["mouth_box"][0], REF["mouth_box"][1]],
                                      "magenta_residue": magenta_residue(pa),
                                      "opaque_ratio": round(float((pa[..., 3] > 32).mean()), 4)})
            report["items"].append(calm)
        except Exception as exc:  # noqa: BLE001
            report["errors"].append({"file": args.base, "reason": str(exc)})
            print(f"  [异常] calm 基准: {exc}", file=sys.stderr)

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
