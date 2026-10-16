#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""挂件切件器：洋红底 AI 原图 → 按色卡重铺的挂件贴图（A49 / T45）。

挂件 = 耳饰 / 尾饰 / 发饰 / 装饰品这类**加法**部件（往剪影上或外加东西，
底下的画面不用动）。服装变化是**替换**类，不走这条路（阻塞于 D19，见 T45.6）。

和另外两个切件器的分工：
  · make_star_eye_parts.py —— 散布型特效（一张素材铺很多片，✨）
  · make_manpu_parts.py    —— 漫符（一个符号一张图，方形，飘在身体外）
  · 本文件                  —— 挂件（**非方形**，挂在身体上，要接物理与形变器）

三者的键色与重铺是同一套算法，直接从 make_manpu_parts 导入，不重写
（重写第二份 = 两份会慢慢长歪，这正是 G117 要消灭的那种事）。

挂件和漫符的两个实质差别：
  1. **不是方的**。尾巴是 1:2 的竖图，强行压成正方会把它压扁。
  2. **锚点不在中心**。悬垂件的锚点必须落在**根部**，因为那就是物理支点；
     zrig.c:751 的 anchor 默认 (0.5,0.5)，表里要显式写 [0.5,0.0] 之类。
"""
from __future__ import annotations

import argparse
import io
import json
import os

import numpy as np
from PIL import Image

from make_manpu_parts import (SOLID_A, bg_color, key_alpha, left_magenta,
                              relay_colors, CROP_MARGIN)


def build_one(att, slot, redraw_dir, sprites_dir):
    src = os.path.join(redraw_dir, att["source"])
    if not os.path.exists(src):
        raise SystemExit("[attach] 缺原图 %s" % src)
    im = Image.open(src).convert("RGB")
    rgb = np.asarray(im, dtype=np.uint8)
    bg = bg_color(rgb)
    a = key_alpha(rgb, bg)

    ys, xs = np.nonzero(a > 0.35)
    if len(xs) == 0:
        raise SystemExit("[attach] %s：键完什么都不剩，底色判错了？bg=%s"
                         % (att["id"], bg))
    x0, x1, y0, y1 = xs.min(), xs.max() + 1, ys.min(), ys.max() + 1

    # ★ 保长宽比。漫符那边裁成正方是因为漫符本来就是方的；
    #   挂件不是 —— 尾巴 1:2，压成正方会变成一坨。
    padx = int(round((x1 - x0) * CROP_MARGIN))
    pady = int(round((y1 - y0) * CROP_MARGIN))
    bx0, by0 = x0 - padx, y0 - pady
    bw, bh = (x1 - x0) + padx * 2, (y1 - y0) + pady * 2
    canvas = np.empty((bh, bw, 3), dtype=np.uint8)
    canvas[:, :] = bg.astype(np.uint8)
    sx0, sy0 = max(bx0, 0), max(by0, 0)
    sx1, sy1 = min(bx0 + bw, rgb.shape[1]), min(by0 + bh, rgb.shape[0])
    canvas[sy0 - by0:sy1 - by0, sx0 - bx0:sx1 - bx0] = rgb[sy0:sy1, sx0:sx1]

    ca = key_alpha(canvas, bg)
    crgb = relay_colors(canvas, ca, att["recolor"])

    h1 = int(att["sprite_h"])
    w1 = max(1, int(round(h1 * bw / float(bh))))
    made = []
    for mul, name in ((1, att["sprite"]),
                      (2, att["sprite"].replace(".png", "@2x.png"))):
        rgba = np.dstack([crgb, ca * 255.0]).astype(np.uint8)
        out = Image.fromarray(rgba, "RGBA").resize((w1 * mul, h1 * mul),
                                                   Image.LANCZOS)
        arr = np.asarray(out)
        leftover = left_magenta(arr[..., :3], arr[..., 3] / 255.0)
        if leftover:
            raise SystemExit("[attach] %s %s 还剩 %d 个洋红像素"
                             % (att["id"], name, leftover))
        out.save(os.path.join(sprites_dir, name))
        made.append(name)
    return w1, h1, made, float((ca > 0.5).sum()) / float(ca.size)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    ap.add_argument("--character", required=True)
    ap.add_argument("--form", required=True)
    a = ap.parse_args()

    base = os.path.join(a.root, "characters", a.character)
    sprites = os.path.join(base, "forms", a.form, "sprites")
    redraw = os.path.join(base, "design", "redraw")
    tp = os.path.join(base, "design", "attachments.json")
    if not os.path.exists(tp):
        print("[attach] 没有 %s，跳过" % tp)
        return 0
    with io.open(tp, encoding="utf-8") as f:
        table = json.load(f)

    slots = {s["id"]: s for s in table["slots"]}
    out = {"schema_version": "1.0", "slots": table["slots"], "attachments": []}
    for att in table["attachments"]:
        slot = slots.get(att["slot"])
        if slot is None:
            raise SystemExit("[attach] %s 落在不存在的插槽 %r"
                             % (att["id"], att["slot"]))
        w, h, made, cover = build_one(att, slot, redraw, sprites)
        out["attachments"].append({
            "id": att["id"], "slot": att["slot"],
            "file": "sprites/" + att["sprite"],
            "size": [w, h],
        })
        print("[attach] %-10s → 槽 %-18s %dx%d（覆盖 %.0f%%）"
              % (att["id"], att["slot"], w, h, cover * 100))

    dst = os.path.join(sprites, "attach_parts.json")
    with io.open(dst, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print("写出 %s：%d 件 / %d 槽" % (dst, len(out["attachments"]), len(slots)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
