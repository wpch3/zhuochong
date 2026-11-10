#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""make_qa_shots.py —— 一键重拍"验收证据"（写进 docs/qa/，可选写 logs/ 草稿）

★ 为什么要有它
--------------------------------------------------------------------
2026-10-26 工作区被还原，**本地未跟踪文件全丢了**，包括所有证据图。
这才发现一件事：这些图一直放在 `logs/asset_qa/`，而 `.gitignore` 第 11 行是 `logs/` ——
**它们从来没进过库**，"证据已入库"是我记错账。图丢了，结论就没法复核。

所以证据必须能**重拍**，而不是"当时截过一张"。这个脚本就是那条重拍路径：
所有对照图都由 `rig.json + sprites + 预览帧` 现场生成，一条命令补齐，
输出到 `docs/qa/`（入库）。

★ 它拍什么（每条对应一个结论）
--------------------------------------------------------------------
    1. 后发换源头前后（现在 vs sprites/_ghostbak 里的旧件）→ t67_25_ab_*.png
    2. 两腿之间那缕头发的归属（全量 / 只后发 / 只侧发）→ t67_26_strip_owner.png
    3. 四个尾巴档位在正面视角的真实可见性 → t67_11_tail_poses.png
    4. 四个尾巴精灵本身的美术问题 → t67_11_tail_sprites.png
    5. 参考立绘同一区域（要长什么样） → t67_26_reference.png

用法
----
    python3 tools/make_qa_shots.py                 # 只拍 docs/qa/
    python3 tools/make_qa_shots.py --port 5173
    python3 tools/make_qa_shots.py --out logs/x    # 拍草稿
"""
from __future__ import annotations

import argparse
import io
import json
import os
import urllib.request

import numpy as np
from PIL import Image, ImageDraw, ImageFont

FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"


def _font(sz=16):
    try:
        return ImageFont.truetype(FONT, sz)
    except OSError:
        return None


def get(base, path, timeout=60):
    with urllib.request.urlopen(base + path, timeout=timeout) as r:
        return r.read()


def frame(base):
    return Image.open(io.BytesIO(get(base, "/api/frame.png?t=5"))).convert("RGBA")


def reset(base, form="teen"):
    """回到"静止、无自动动作、无表情"的干净状态。顺序有讲究：先关自动，再冻时钟。"""
    for p in ("/api/ambient?on=0", "/api/blink?on=0", "/api/idle?on=0",
              "/api/param?all=1", "/api/part?all=1", "/api/pause?on=0"):
        get(base, p)
    get(base, "/api/pose?group=hairstyle&id=long")
    get(base, "/api/pose?group=hood_pose&id=down")
    get(base, "/api/pose?group=tail_pose&id=relaxed")
    get(base, "/api/step?n=90")
    get(base, "/api/pause?on=1&t=2")
    get(base, "/api/step?n=3")


def tile(label, im, zoom=1, bg=(40, 42, 48)):
    """im 可以是 RGB（已铺底）也可以是 RGBA（按 alpha 贴到 bg 上）。"""
    w, h = im.size
    canvas = Image.new("RGB", (w, h), bg)
    if im.mode == "RGBA":
        canvas.paste(im, (0, 0), im)
    else:
        canvas.paste(im.convert("RGB"), (0, 0))
    if zoom != 1:
        canvas = canvas.resize((w * zoom, h * zoom), Image.LANCZOS)
    out = Image.new("RGB", (canvas.width + 6, canvas.height + 24), (22, 22, 26))
    out.paste(canvas, (3, 22))
    f = _font(15)
    if f:
        ImageDraw.Draw(out).text((4, 3), label, font=f, fill=(255, 255, 0))
    return out


def hstack(tiles):
    w = sum(t.width for t in tiles)
    h = max(t.height for t in tiles)
    sh = Image.new("RGB", (w, h), (12, 12, 12))
    x = 0
    for t in tiles:
        sh.paste(t, (x, 0))
        x += t.width
    return sh


def shot_hair_ab(root, out_dir):
    old = Image.open(os.path.join(root, "characters/xiaoxun/forms/teen/sprites/_ghostbak/hair_long_back@2x.png")).convert("RGBA")
    new = Image.open(os.path.join(root, "characters/xiaoxun/forms/teen/sprites/hair_long_back@2x.png")).convert("RGBA")
    H = 600

    def fit(im):
        r = H / im.height
        return im.resize((max(1, int(im.width * r)), H), Image.LANCZOS)

    def on_mag(im):
        bg = Image.new("RGB", im.size, (255, 0, 255))
        bg.paste(im, (0, 0), im)
        return bg

    a, b = fit(old), fit(new)
    hstack([tile("OLD: hair_long_back (ghost hands/cuffs/shirt baked in)", on_mag(a)),
            tile("NEW: hair-long back-only (keyed, 0% magenta fringe)", on_mag(b))]).save(
        os.path.join(out_dir, "t67_25_ab_full.png"))
    # 局部放大：左髋/手
    ca = on_mag(old).crop((60, 1150, 460, 1560))
    cb = on_mag(new).crop((60, 1150, 460, 1560))
    hstack([tile("OLD left hip / hand (stair-step silhouette)", ca, 2),
            tile("NEW left hip / hand (organic silhouette)", cb, 2)]).save(
        os.path.join(out_dir, "t67_25_ab_zoom.png"))


def shot_tail_sprites(root, out_dir):
    sp = os.path.join(root, "characters/xiaoxun/forms/teen/sprites")
    names = ("acc_tail_relaxed", "acc_tail_up", "acc_tail_puff", "acc_tail_tuck")
    tiles = []
    for n in names:
        p = os.path.join(sp, n + "@2x.png")
        im = Image.open(p).convert("RGBA")
        bg = Image.new("RGB", im.size, (255, 0, 255))
        bg.paste(im, (0, 0), im)
        bg.thumbnail((200, 300), Image.LANCZOS)
        tiles.append(tile(n.replace("acc_tail_", "tail="), bg))
    hstack(tiles).save(os.path.join(out_dir, "t67_11_tail_sprites.png"))


def shot_tail_poses(base, out_dir):
    get(base, "/api/scale?s=1")
    box = (220, 600, 620, 1000)
    tiles = []
    for pose in ("relaxed", "up", "puff", "tuck"):
        get(base, "/api/pause?on=0")
        get(base, "/api/pose?group=tail_pose&id=%s" % pose)
        get(base, "/api/step?n=45")
        get(base, "/api/pause?on=1&t=2")
        get(base, "/api/step?n=2")
        tiles.append(tile("tail=" + pose, frame(base).crop(box)))
    get(base, "/api/pause?on=0")
    get(base, "/api/pose?group=tail_pose&id=relaxed")
    hstack(tiles).save(os.path.join(out_dir, "t67_11_tail_poses.png"))


def shot_strip_owner(base, out_dir):
    get(base, "/api/scale?s=1")
    reset(base)
    box = (360, 730, 520, 1010)
    tiles = [tile("ALL", frame(base).crop(box), 2)]
    for pid, lab in (("acc_hair_long", "ONLY acc_hair_long (layer 58)"),
                     ("acc_hair_sidelong_l", "ONLY acc_hair_sidelong_l (layer 249)")):
        get(base, "/api/part?all=1")
        get(base, "/api/part?id=%s&vis=2" % pid)
        get(base, "/api/step?n=2")
        tiles.append(tile(lab, frame(base).crop(box), 2))
    get(base, "/api/part?all=1")
    hstack(tiles).save(os.path.join(out_dir, "t67_26_strip_owner.png"))


def shot_reference(root, out_dir):
    p = os.path.join(root, "characters/xiaoxun/design/sheets/sheet_long.png")
    im = Image.open(p).convert("RGB").crop((400, 780, 640, 1180))
    im = im.resize((im.width * 2, im.height * 2), Image.LANCZOS)
    bg = Image.new("RGB", im.size, (40, 42, 48))
    bg.paste(im, (0, 0))
    out = Image.new("RGB", (bg.width + 6, bg.height + 24), (22, 22, 26))
    out.paste(bg, (3, 22))
    f = _font(15)
    if f:
        ImageDraw.Draw(out).text((4, 3), "REFERENCE sheet_long.png: that strand is BACK hair (behind legs)",
                                 font=f, fill=(255, 255, 0))
    out.save(os.path.join(out_dir, "t67_26_reference.png"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    ap.add_argument("--port", type=int, default=5173)
    ap.add_argument("--out", default="docs/qa")
    a = ap.parse_args()
    root = os.path.abspath(a.root)
    out_dir = os.path.join(root, a.out)
    os.makedirs(out_dir, exist_ok=True)
    base = "http://127.0.0.1:%d" % a.port

    shot_hair_ab(root, out_dir)
    shot_tail_sprites(root, out_dir)
    shot_reference(root, out_dir)
    try:
        shot_tail_poses(base, out_dir)
        shot_strip_owner(base, out_dir)
    except Exception as e:                                    # noqa: BLE001
        print("预览没起来，跳过需要渲染的两张：%r" % (e,))
    print("证据图 →", out_dir)
    for f in sorted(os.listdir(out_dir)):
        if f.endswith(".png"):
            print("   ", f)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
