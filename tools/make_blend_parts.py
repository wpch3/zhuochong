#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成「混合模式」专用的两类小零件（A7）。

这两类零件在 Live2D 里是标配，但它们不是从立绘上抠出来的，而是**画上去的**：

  腮红 blush_l/r   —— 乘算（multiply）。乘算只会压暗底下的皮肤，
                      不会像普通叠加那样糊一层不透明的粉色膜，所以脸红是"透出来"的。
  眼高光 eye_hl_l/r —— 加算（additive）。加算只提亮已经有画面的地方，
                      透明背景上不会凭空多出一个白点，这正是高光该有的行为。

两者都是程序化生成的软边椭圆（径向渐变），不需要 AI 生图，也不吃原画分辨率：
形状由参数决定，想换大小/位置改这里就行。

用法：
    python3 tools/make_blend_parts.py --character xiaoxun --form teen
输出：
    characters/<c>/forms/<f>/sprites/blush_l.png blush_r.png eye_hl_l.png eye_hl_r.png
    characters/<c>/forms/<f>/sprites/blend_parts.json（位置/尺寸，给 make_rig.py 读）
"""
from __future__ import annotations

import argparse
import json
import math
import os

from PIL import Image

# 画布坐标（848×1360）下的落点。依据 rig.json 现有几何：
#   eye_l_socket pos[298,246] 117×68、eye_r_socket pos[428,246]
#   mouth pos[422,316]，所以脸颊在 y≈300~340、眼眶外下方。
BLUSH = {
    "l": {"pos": [311, 300], "size": [64, 34]},
    "r": {"pos": [472, 300], "size": [64, 34]},
}
# 高光落在瞳孔左上（眼球 eye_l_ball pos[369,258] 31×30 / eye_r_ball pos[442,253]）
HIGHLIGHT = {
    "l": {"pos": [373, 262], "size": [13, 13]},
    "r": {"pos": [446, 257], "size": [13, 13]},
}
BLUSH_RGB = (242, 150, 162)      # 乘算色：越暗压得越狠，这个值出来是淡淡的桃粉
HL_RGB = (255, 253, 246)         # 加算色：略偏暖的白，纯白会显得发青


def radial(w: int, h: int, rgb, peak: float, gamma: float) -> Image.Image:
    """软边椭圆：中心 alpha=peak，向边缘按 (1-r)^gamma 衰减到 0。"""
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    px = im.load()
    cx, cy = (w - 1) / 2.0, (h - 1) / 2.0
    for y in range(h):
        for x in range(w):
            nx = (x - cx) / max(cx, 1e-6)
            ny = (y - cy) / max(cy, 1e-6)
            d = math.hypot(nx, ny)
            if d >= 1.0:
                continue
            a = peak * ((1.0 - d) ** gamma)
            if a <= 0.002:
                continue
            px[x, y] = (rgb[0], rgb[1], rgb[2], int(round(a * 255)))
    return im


def speckle(im: Image.Image, n: int = 3) -> Image.Image:
    """腮红上点几道更浓的小斜线——二次元腮红惯常画法，避免纯渐变显得像污渍。"""
    w, h = im.size
    px = im.load()
    for i in range(n):
        x0 = int(w * (0.28 + 0.18 * i))
        for t in range(int(h * 0.52)):
            x = x0 + int(t * 0.45)
            y = int(h * 0.24) + t
            if 0 <= x < w and 0 <= y < h:
                r, g, b, a = px[x, y]
                if a:
                    px[x, y] = (r, g, b, min(255, int(a * 1.45) + 18))
    return im


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--character", required=True)
    ap.add_argument("--form", required=True)
    ap.add_argument("--root", default=".")
    a = ap.parse_args()

    out_dir = os.path.join(a.root, "characters", a.character, "forms", a.form, "sprites")
    os.makedirs(out_dir, exist_ok=True)
    report = {"blush": {}, "highlight": {}}

    for side, cfg in BLUSH.items():
        w, h = cfg["size"]
        im = speckle(radial(w, h, BLUSH_RGB, peak=0.62, gamma=1.35))
        im.save(os.path.join(out_dir, f"blush_{side}.png"))
        report["blush"][side] = {"file": f"sprites/blush_{side}.png",
                                 "pos": cfg["pos"], "size": [w, h], "blend": "multiply"}

    for side, cfg in HIGHLIGHT.items():
        w, h = cfg["size"]
        im = radial(w, h, HL_RGB, peak=0.92, gamma=0.85)
        im.save(os.path.join(out_dir, f"eye_hl_{side}.png"))
        report["highlight"][side] = {"file": f"sprites/eye_hl_{side}.png",
                                     "pos": cfg["pos"], "size": [w, h], "blend": "add"}

    with open(os.path.join(out_dir, "blend_parts.json"), "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"写出 {out_dir}/blush_[lr].png + eye_hl_[lr].png + blend_parts.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
