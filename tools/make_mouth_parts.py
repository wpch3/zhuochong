#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""make_mouth_parts.py - 造出"会张开的嘴"所需的零件。

现状：原画里的嘴只有一条闭合的笑线，**没有口腔**——嘴张开后该露出来的东西
（口内、舌头、下唇线）在素材里根本不存在，所以不能"切"，只能按角色配色画出来。
这正是 Live2D 的做法：口内是一张独立图，被"开口形状"遮罩裁切，
开口大小由参数（ParamMouthOpenY）压缩遮罩的高度来控制。

产物（写进 sprites/）：
  mouth_mask.png    开口形状（最大张开时的剪影）；rig 里 mask_only=true，
                    锚点在上唇线，靠 sy 缩放控制张开多少
  mouth_cavity.png  口内：上颚阴影 → 口腔深色 → 舌头 → 下唇线，被 mask 裁切
  mouth_parts.json  位置、尺寸、最大开口、配色

嘴线（闭合笑线）沿用现成的 sprites/mouth_open.png，它压在口内上面当上唇。

用法：
  ~/.imgenv/bin/python tools/make_mouth_parts.py --character xiaoxun --form teen
"""
from __future__ import annotations
import argparse, json, os

import numpy as np
from PIL import Image


def find_mouth_line(body_px, alpha, cx_hint, y_hint, skin):
    """在嘴部附近找出那条笑线：比肤色明显暗、且是暖色（排除蓝色发丝）的像素。"""
    y0, y1 = max(0, y_hint - 18), y_hint + 2
    x0, x1 = max(0, cx_hint - 22), cx_hint + 22
    sub = body_px[y0:y1, x0:x1]
    sa = alpha[y0:y1, x0:x1]
    dist = np.abs(sub - np.array(skin)).sum(2)
    warm = sub[..., 0] > sub[..., 2] + 8          # 嘴线是褐色，头发是蓝紫
    m = (sa > 128) & (dist > 90) & warm
    if m.sum() < 8:
        raise SystemExit("找不到嘴线：请检查 anchors.json 的 mouth_line")
    # 只保留离脸中线最近的那一簇（笑线左右两段算同一簇：按 x 聚合）
    ys, xs = np.nonzero(m)
    keep = np.abs((x0 + xs) - cx_hint) <= 20
    ys, xs = ys[keep], xs[keep]
    return {
        "x0": int(x0 + xs.min()), "x1": int(x0 + xs.max()),
        "y0": int(y0 + ys.min()), "y1": int(y0 + ys.max()),
        "color": tuple(int(v) for v in sub[m][np.argmin(sub[m].sum(1))]),
    }


def build_mouth(line, scale_hint=1.0):
    """按嘴线的尺寸造开口形状与口内。坐标都在"身体图"像素空间。"""
    mw = line["x1"] - line["x0"] + 1          # 笑线宽度
    cx = (line["x0"] + line["x1"]) / 2.0
    top = line["y0"] + (line["y1"] - line["y0"]) * 0.5   # 上唇线高度

    # 张开的嘴比笑线窄一点、够深：按真人/动画比例取 0.78 宽、0.62 深
    W = max(10, int(round(mw * 0.78)))
    H = max(8, int(round(mw * 0.62)))
    pad = 2
    w, h = W + pad * 2, H + pad * 2

    yy, xx = np.mgrid[0:h, 0:w]
    ex = (xx - (w - 1) / 2.0) / (W / 2.0)
    ey = (yy - pad) / float(H)
    # 嘴角比中间晚开：每一列的"起始高度"随着离中线越远而下移。
    # 遮罩是从上往下压扁的，所以微张时只有中间露出来 → 得到一枚小小的梭形，
    # 而不是一条横贯嘴角的黑杠（这是第一版的毛病）。
    t0 = 0.30 * np.abs(ex) ** 1.6
    inside = (ey >= t0) & (np.abs(ex) <= 1.0) & \
             (np.abs(ex) ** 2.0 + np.clip(ey, 0, None) ** 2.4 <= 1.0)
    # 1px 软边
    cov = inside.astype(float)
    soft = cov.copy()
    for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        soft += np.roll(np.roll(cov, dy, 0), dx, 1)
    soft = np.clip(soft / 5.0, 0, 1)
    alpha = np.where(inside, 1.0, soft * 0.55)

    mask = np.zeros((h, w, 4), np.uint8)
    mask[..., :3] = 255
    mask[..., 3] = (alpha * 255).astype(np.uint8)

    # 口内配色：由嘴线颜色推出来，保证和角色同一套色系
    lip = np.array(line["color"], float)
    deep = np.clip(lip * 0.62, 0, 255)                     # 口腔最深处
    roof = np.clip(lip * 0.80, 0, 255)                     # 上颚阴影
    tongue = np.clip(lip * 0.55 + np.array([120, 45, 50]), 0, 255)   # 舌头偏粉
    rim = np.clip(lip * 0.72, 0, 255)                      # 下唇线

    cav = np.zeros((h, w, 4), np.uint8)
    for y in range(h):
        t = (y - pad) / float(H)                 # 0 = 上唇线，1 = 最深
        if t < 0.14:
            c = roof
        elif t < 0.58:
            k = (t - 0.14) / 0.44
            c = roof * (1 - k) + deep * k
        else:
            k = min(1.0, (t - 0.58) / 0.30)
            c = deep * (1 - k) + tongue * k
        cav[y, :, :3] = c.round().astype(np.uint8)
    # 下唇线：最底下两行压暗，张到最大时就是下唇
    for y in range(h):
        t = (y - pad) / float(H)
        if t > 0.90:
            cav[y, :, :3] = rim.round().astype(np.uint8)
    # 形状本来交给遮罩，但口内自己也套一遍开口剪影：这样万一遮罩缺失也不会糊出一块方砖，
    # 素材验收也要求每张图都有透明通道。
    cav[..., 3] = (alpha * 255).astype(np.uint8)
    cav[..., :3] = np.where(cav[..., 3:4] > 0, cav[..., :3], 0)

    return {
        "mask": Image.fromarray(mask),
        "cavity": Image.fromarray(cav),
        "pos": [int(round(cx - w / 2.0)), int(round(top))],
        # 遮罩按 anchor=[0.5,0] 缩放（上唇线中点是支点），rig 里要用这个点定位
        "anchor_pos": [round(float(cx), 1), round(float(top), 1)],
        "size": [w, h],
        "open_h": H,
        "colors": {
            "上颚": "#%02X%02X%02X" % tuple(roof.round().astype(int)),
            "口腔": "#%02X%02X%02X" % tuple(deep.round().astype(int)),
            "舌": "#%02X%02X%02X" % tuple(tongue.round().astype(int)),
            "下唇": "#%02X%02X%02X" % tuple(rim.round().astype(int)),
        },
        "line": line,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--character", required=True)
    ap.add_argument("--form", required=True)
    ap.add_argument("--root", default=".")
    args = ap.parse_args()

    base = os.path.join(args.root, "characters", args.character, "forms", args.form)
    sp = os.path.join(base, "sprites")
    body = Image.open(os.path.join(sp, "body_full.png")).convert("RGBA")
    a = np.array(body).astype(int)

    anchors = json.load(open(os.path.join(base, "design", "anchors.json"), encoding="utf-8"))
    mx, my = anchors["points"]["mouth_line"]
    palette = json.load(open(os.path.join(args.root, "characters", args.character,
                                          "design", "palette.json"), encoding="utf-8"))
    skin = next((c["hex"] for c in palette["colors"] if "肤" in c["name"]), "#FCE4D8").lstrip("#")
    skin = tuple(int(skin[i:i + 2], 16) for i in (0, 2, 4))

    line = find_mouth_line(a[..., :3], a[..., 3], int(round(mx)), int(round(my)), skin)
    out = build_mouth(line)
    out["mask"].save(os.path.join(sp, "mouth_mask.png"))
    out["cavity"].save(os.path.join(sp, "mouth_cavity.png"))

    rep = {
        "source": "body_full.png（嘴线实测）+ 程序绘制的口内",
        "line": line,
        "mask": "mouth_mask.png",
        "cavity": "mouth_cavity.png",
        "pos": out["pos"],
        "anchor_pos": out["anchor_pos"],
        "size": out["size"],
        "open_h": out["open_h"],
        "closed_sy": round(1.2 / out["size"][1], 3),   # 闭嘴时遮罩压到只剩一线
        "colors": out["colors"],
        "note": "口内是画出来的（原画没有）；开口大小 = 压缩 mouth_mask 的 sy，"
                "锚点在上唇线，所以嘴是往下张开的。",
    }
    with open(os.path.join(sp, "mouth_parts.json"), "w", encoding="utf-8") as f:
        json.dump(rep, f, ensure_ascii=False, indent=2)
    print(f"嘴线 x{line['x0']}..{line['x1']} y{line['y0']}..{line['y1']}  "
          f"开口 {out['size'][0]}x{out['size'][1]}（最大张 {out['open_h']}px）")
    print("配色", out["colors"])
    print("写出 sprites/mouth_mask.png、mouth_cavity.png、mouth_parts.json")


if __name__ == "__main__":
    main()
