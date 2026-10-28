#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""make_parts.py - 从 body_full.png 生成“第一版可动拆件”。【不在重建链上】

当前阶段（交接文件第十一节第 4 步：先做待机、眨眼、视线）：
  - 真实拆件（眼睛、嘴、身体分段）需要 AI 重绘的独立素材，属于下一步；
  - 本脚本生成的是**几何正确的中间件**：
      head        = 头部区域裁剪（用于摸头/头部旋转）
      eye_open_L/R = 从原图切出的眼睛（含睫毛/眼白/虹膜/高光），供眨眼时交叉淡化
      eye_closed_L/R = 将眼睛区域按上眼睑位置“压扁”得到的闭眼占位，
                       由表情集替代后会自然升级为高质量闭眼（配置不用改）
      mouth_open  = 嘴部裁剪（说话口型用）
  - 所有坐标从原图量取，保证与立绘完全对齐。

用法：
  python3 tools/make_parts.py --character xiaoxun --form teen \
      --eyes "left=95,180,132,232;right=222,180,355,232" --mouth "200,232,250,266"
"""
from __future__ import annotations
import argparse, json, os, sys
import numpy as np
from PIL import Image


def crop_rgba(im: Image.Image, box) -> Image.Image:
    return im.crop(box)


def tighten(im: Image.Image):
    """裁到不透明内容；返回 (图像, 相对原图的左上偏移)。"""
    a = np.asarray(im)[..., 3]
    ys, xs = np.where(a > 4)
    if len(xs) == 0:
        return im, (0, 0)
    x0, y0 = int(xs.min()), int(ys.min())
    return im.crop((x0, y0, int(xs.max()) + 1, int(ys.max()) + 1)), (x0, y0)


def make_closed(im: Image.Image, lid_ratio: float = 0.62) -> Image.Image:
    """由睁眼图生成“闭眼”：取上眼睑弧线以下压成细缝。
    做法：按行统计不透明像素宽度，取最宽行作为眼睛中心线，
    从其上方 lid_ratio 处取一条窄带，向下做弧形收缩，模拟闭眼线。
    这是一版可见的占位实现，保留在脚本里便于对比；AI 表情集到位后此函数不再被使用。"""
    arr = np.asarray(im).astype(np.float32)
    h, w, _ = arr.shape
    alpha = arr[..., 3]
    widths = (alpha > 8).sum(axis=1)
    cy = int(np.argmax(widths))
    band_h = max(3, int(h * 0.18))
    y0 = max(0, cy - int(h * lid_ratio * 0.1) - band_h // 2)
    band = arr[y0:y0 + band_h]
    out = np.zeros_like(arr)
    # 弧形：中间厚两端薄
    xs = np.linspace(-1, 1, w)
    thickness = (1.0 - xs ** 2)
    for x in range(w):
        t = max(1, int(round(band_h * (0.35 + 0.65 * thickness[x]))))
        out[0:t, x] = band[min(band.shape[0] - 1, band_h // 2), x]
    return Image.fromarray(out.astype(np.uint8), "RGBA")


def mask_mouth(im: Image.Image, keep_alpha: float = 0.9) -> Image.Image:
    """把嘴部裁剪块变成“只有嘴线”的图层。

    整块裁剪会把肤色矩形盖在脸上（虽然颜色接近，但一动就会露馅）。
    这里按“比周围肤色暗”的程度生成 alpha：嘴线/唇缝保住，皮肤变透明。
    """
    arr = np.asarray(im).astype(np.float32)
    rgb = arr[..., :3]
    lum = rgb.mean(axis=2)
    # 参考亮度取该区域最亮的 20% 分位（即肤色），暗于参考值越多 alpha 越高
    ref = float(np.percentile(lum, 80))
    diff = np.clip((ref - lum) / 60.0, 0, 1)
    alpha = (diff ** 0.85) * 255.0 * keep_alpha
    out = arr.copy()
    out[..., 3] = alpha
    return Image.fromarray(out.astype(np.uint8), "RGBA")


def auto_boxes(root, character, form, body):
    """从 anchors.json + 色卡**自动量出**眼框与嘴框（T2.2.5，2026-10-17）。

    为什么要加这个：原来这三个框只能命令行手填，所以 `rebuild_parts.sh` 里
    根本没有这一步 —— 少女的 parts_report.json 是当初手动跑出来的历史产物。
    结果是「照着流水线跑一遍做不出一个新形态」：Q 版跑到第 4 步就因为
    缺 parts_report.json 炸了。眼睛和嘴的位置本来就能从素材量出来，不该手填。

    量法（都不含任何形态常数）：
      · 眼 = 色卡「眼睛」色的像素，在头部范围内按中线分左右两簇，各取外接框，
            再按**虹膜自身的尺寸**外扩（上 0.9 倍含睫毛、下 0.5 倍、左右 0.35 倍）。
      · 嘴 = 眼线与颈之间、靠中线的窄带里，比肤色暗的暖色像素（嘴线是褐的，
            头发是蓝紫的），取最集中那一行附近；框宽按头宽的 12% 取。
    """
    import json as _json
    base = os.path.join(root, "characters", character, "forms", form)
    with open(os.path.join(base, "design", "anchors.json"), encoding="utf-8") as f:
        anc = _json.load(f)
    pts = anc["points"]
    eye_y = int(pts["eye_line"][1]); neck_y = int(pts["neck"][1])
    top_y = int(pts["head_top"][1]); cx = int(pts["eye_line"][0])
    head = max(neck_y - top_y, 1)

    pal_path = os.path.join(root, "characters", character, "design", "palette.json")
    eye_rgb, skin_rgb = (74, 143, 212), (252, 228, 216)
    if os.path.exists(pal_path):
        with open(pal_path, encoding="utf-8") as f:
            for c in _json.load(f).get("colors", []):
                h = c["hex"].lstrip("#")
                rgb = (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))
                # ★ 必须精确匹配：色卡里既有「肤色」也有「肤色暗部（嘴/阴影）」，
                #   用 in 匹配会被后者覆盖，嘴线当场读错（少女实测 249 → 219）。
                nm = c.get("name", "").strip()
                if nm == "眼睛":
                    eye_rgb = rgb
                if nm == "肤色":
                    skin_rgb = rgb

    a = np.asarray(body)
    rgb, al = a[..., :3].astype(int), a[..., 3]

    # 眼框：几何法。系数是在少女**已有的手填框**上对出来的（逐项差 ≤ 2px）：
    #   x 半宽 = 眼线那一行的剪影宽 × 0.50（含头发，脸的可见宽度就是它）
    #   y 上 0.10 头高（睫毛/眼睑）、下 0.15 头高（下睫毛/卧蚕）
    # 框只要**框住眼睛**就行，具体哪里是眼白/虹膜/眼线由 make_eye_parts.split_eye 自己找。
    row = np.flatnonzero(al[min(eye_y, a.shape[0] - 1)] > 24)
    hw = float(row[-1] - row[0] + 1) if row.size else float(head)
    y0 = max(0, int(eye_y - head * 0.10))
    y1 = min(a.shape[0], int(eye_y + head * 0.15))
    eyes = {
        "left": (max(0, int(cx - hw * 0.50)), y0, max(1, int(cx - hw * 0.03)), y1),
        "right": (min(a.shape[1] - 1, int(cx + hw * 0.03)), y0,
                  min(a.shape[1], int(cx + hw * 0.50)), y1),
    }

    # 嘴：眼线与颈之间 20%~80% 的带（排除下巴线），**只看中线附近 ±0.05 头高的窄柱**
    #   —— 柱子放宽到 0.12 就会把眼角的睫毛数进来，少女实测把嘴线读到 y=219（真值 249）。
    lo = eye_y + int((neck_y - eye_y) * 0.20)
    hi = eye_y + int((neck_y - eye_y) * 0.80)
    half = max(5, int(head * 0.05))
    sub = rgb[lo:hi, max(0, cx - half):cx + half]
    sa = al[lo:hi, max(0, cx - half):cx + half]
    warm_dark = ((sa > 128)
                 & (np.abs(sub - np.array(skin_rgb)).sum(2) > 90)
                 & (sub[..., 0] > sub[..., 2] + 8))
    rows = warm_dark.sum(axis=1)
    if rows.sum() < 8:
        raise SystemExit("自动量嘴框失败：找不到嘴线")
    my = lo + int(np.argmax(rows))
    mouth = (max(0, cx - half), max(0, my - int(head * 0.035)),
             min(a.shape[1], cx + half), min(a.shape[0], my + int(head * 0.035)))
    return eyes, mouth, my


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--character", required=True)
    ap.add_argument("--form", required=True)
    ap.add_argument("--eyes", default="", help="left=x0,y0,x1,y1;right=...")
    ap.add_argument("--mouth", default="", help="x0,y0,x1,y1")
    ap.add_argument("--head", default="", help="x0,y0,x1,y1（头部裁剪范围）")
    ap.add_argument("--auto", action="store_true",
                    help="从 anchors.json + 色卡自动量眼框与嘴框（新形态用这个）")
    ap.add_argument("--dry-run", action="store_true", help="只打印量到的框，不写文件")
    ap.add_argument("--root", default=".")
    args = ap.parse_args()

    sp = os.path.join(args.root, "characters", args.character, "forms", args.form, "sprites")
    body_path = os.path.join(sp, "body_full.png")
    if not os.path.exists(body_path):
        print(f"[错误] 找不到 {body_path}，先运行 prepare_sprites.py", file=sys.stderr)
        return 2
    body = Image.open(body_path).convert("RGBA")
    report = {"source": body_path, "parts": []}

    if args.auto:
        eyes, mouth, my = auto_boxes(args.root, args.character, args.form, body)
        args.eyes = ";".join(f"{s}={b[0]},{b[1]},{b[2]},{b[3]}" for s, b in eyes.items())
        args.mouth = ",".join(str(v) for v in mouth)
        print(f"[auto] 眼框 {args.eyes}")
        print(f"[auto] 嘴框 {args.mouth}（嘴线 y={my}）")
        if args.dry_run:
            return 0

    def save(img: Image.Image, name: str, origin=(0, 0)):
        """origin 为该图在 body_full.png 中的左上坐标，用于 rig.json 定位。"""
        img, off = tighten(img)
        p = os.path.join(sp, name)
        img.save(p)
        pos = [origin[0] + off[0], origin[1] + off[1]]
        report["parts"].append({"name": name, "size": list(img.size), "pos": pos})
        print(f"  写出 {name} {img.size[0]}x{img.size[1]} @ {pos}")

    if args.head:
        x0, y0, x1, y1 = (int(v) for v in args.head.replace(",", " ").split())
        save(crop_rgba(body, (x0, y0, x1, y1)), "head.png", (x0, y0))
    if args.eyes:
        for item in args.eyes.split(";"):
            if not item.strip():
                continue
            side, box = item.split("=")
            x0, y0, x1, y1 = (int(v) for v in box.replace(",", " ").split())
            eye = crop_rgba(body, (x0, y0, x1, y1))
            save(eye, f"eye_open_{side.strip()}.png", (x0, y0))
            closed = make_closed(eye)
            # 闭眼图比睁眼窄（一条弧线），垂直位置取原眼框内约 45% 处
            save(closed, f"eye_closed_{side.strip()}.png",
                 (x0, y0 + int((y1 - y0) * 0.45)))
    if args.mouth:
        x0, y0, x1, y1 = (int(v) for v in args.mouth.replace(",", " ").split())
        save(mask_mouth(crop_rgba(body, (x0, y0, x1, y1))), "mouth_open.png", (x0, y0))

    with open(os.path.join(sp, "parts_report.json"), "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(json.dumps(report, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
