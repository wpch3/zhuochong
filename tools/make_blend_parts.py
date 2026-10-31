#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成「混合模式」专用的两类小零件（A7）。

这两类零件在 Live2D 里是标配，但它们不是从立绘上抠出来的，而是**画上去的**：

  腮红 blush_l/r   —— 乘算（multiply）。乘算只会压暗底下的皮肤，
                      不会像普通叠加那样糊一层不透明的粉色膜，所以脸红是"透出来"的。
  眼高光 eye_hl_l/r —— 加算（additive）。加算只提亮已经有画面的地方，
                      透明背景上不会凭空多出一个白点，这正是高光该有的行为。

两者都是程序化生成的软边形状（径向渐变），不需要 AI 生图，也不吃原画分辨率：
形状由参数决定，想换大小/位置改这里就行。腮红保持低峰值、无硬质斜线，按模板里的淡暖红气质画，避免小尺寸下变成红色刮痕。

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
    # 2026-10-14 重新定位。原来放在 [311,300]/[472,300]、64×34 —— 实测那片区域
    # **大半在脸的轮廓外**（seg_head 在画布 y=300 的实心范围只有 x 345..491，
    # 而且越往下越窄，y=340 时只剩 386..455）。乘算画在透明背景上等于没画，
    # 所以满值腮红只带来 27 像素可见变化。
    # 现在按瞳孔位置摆：eye_l_ball 中心 x≈384、eye_r_ball x≈457，腮红落在瞳孔正下方，
    # 尺寸收到 40×22 以保证整块都压在实心脸上（下沿只溢出 1~2 px 的软边）。
    "l": {"pos": [366, 299], "size": [40, 22]},
    "r": {"pos": [437, 299], "size": [40, 22]},   # 对齐右瞳孔中心 457.5
}
# 高光落在瞳孔左上（眼球 eye_l_ball pos[369,258] 31×30 / eye_r_ball pos[442,253]）
HIGHLIGHT = {
    "l": {"pos": [373, 262], "size": [13, 13]},
    "r": {"pos": [446, 257], "size": [13, 13]},
}
# 乘算色：R 不压、G/B 适度压低，得到与短发全身模板相符的浅暖粉。
# 2026-10-31 目视 ParamCheek=1 发现旧 3 道 speckle 经 40×22 小尺寸后成为
# 高对比红色短划痕。按模板淡腮红真值移除斜线，并把中心 alpha 峰值由 0.88 降至 0.40。
BLUSH_RGB = (255, 190, 187)
BLUSH_PEAK = 0.40
BLUSH_GAMMA = 1.25
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



def star(w: int, h: int, rgb, peak: float) -> Image.Image:
    """四角星高光（Live2D 模型最常见的「キラキラ」差分）。

    用两条正交的纺锤形叠出来：横轴 |y| 衰减快、纵轴 |x| 衰减快，
    中心再补一个小圆核。比画多边形柔和，缩小后也不会出锯齿。
    """
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    px = im.load()
    cx, cy = (w - 1) / 2.0, (h - 1) / 2.0
    for y in range(h):
        for x in range(w):
            nx = (x - cx) / max(cx, 1e-6)
            ny = (y - cy) / max(cy, 1e-6)
            ax, ay = abs(nx), abs(ny)
            # 两条臂：沿 x 的臂要求 |y| 很小，沿 y 的臂要求 |x| 很小
            arm_x = max(0.0, 1.0 - ax) * max(0.0, 1.0 - ay * 3.2)
            arm_y = max(0.0, 1.0 - ay) * max(0.0, 1.0 - ax * 3.2)
            core = max(0.0, 1.0 - math.hypot(nx, ny) * 2.1)
            a = peak * min(1.0, arm_x + arm_y + core * 0.9)
            if a <= 0.004:
                continue
            px[x, y] = (rgb[0], rgb[1], rgb[2], int(round(a * 255)))
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
        im = radial(w, h, BLUSH_RGB, peak=BLUSH_PEAK, gamma=BLUSH_GAMMA)
        im.save(os.path.join(out_dir, f"blush_{side}.png"))
        report["blush"][side] = {"file": f"sprites/blush_{side}.png",
                                 "pos": cfg["pos"], "size": [w, h], "blend": "multiply"}

    for side, cfg in HIGHLIGHT.items():
        w, h = cfg["size"]
        im = radial(w, h, HL_RGB, peak=0.92, gamma=0.85)
        im.save(os.path.join(out_dir, f"eye_hl_{side}.png"))
        report["highlight"][side] = {"file": f"sprites/eye_hl_{side}.png",
                                     "pos": cfg["pos"], "size": [w, h], "blend": "add"}

    # 星形高光：Pose 互斥组（A8）里的另一个档位，和圆形高光二选一
    report["star"] = {}
    for side, cfg in HIGHLIGHT.items():
        w, h = cfg["size"][0] + 7, cfg["size"][1] + 7      # 星形要大一点才看得出形状
        im = star(w, h, HL_RGB, peak=0.95)
        im.save(os.path.join(out_dir, f"eye_hl_star_{side}.png"))
        pos = [cfg["pos"][0] - 4, cfg["pos"][1] - 4]       # 保持中心和圆形高光重合
        report["star"][side] = {"file": f"sprites/eye_hl_star_{side}.png",
                                "pos": pos, "size": [w, h], "blend": "add"}

    with open(os.path.join(out_dir, "blend_parts.json"), "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"写出 {out_dir}/blush_[lr].png + eye_hl_[lr].png + eye_hl_star_[lr].png"
          f" + blend_parts.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
