#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""眼睛开合扫描：参数一档一档走，抓帧、裁眼区、放大拼成一张证据图（T66.22b）。

为什么写这个工具
----------------
眼睛的毛病（半闭被直线切、肤色缝、黑钩、闭眼线错位）**只能靠放大看**。
而"抓两张图对比"这件事在本项目里踩过一次坑：待机呼吸/摆头每帧都在动，
不冻结时钟的话两张图里头的位置本来就不一样，diff 出来的差异一大半是相位差 ——
上一轮就是拿这种 A/B 得出"方案 C 接近可用"的错误结论（记在 GAPS G66.13）。

所以这里把正确的抓图姿势固定下来（三条，缺一条图就不可信）：
  1. `/api/ambient?on=0`    关掉环境摆动
  2. `/api/blink?on=0`      关掉自动眨眼（否则闭眼时刻是随机的）
  3. `/api/pause?on=1&t=2.0` 冻结时钟到固定相位，再 `/api/step` 空跑几帧让形变/lag 到位
每改一次参数都要 step —— 引擎的 keyform 和迟滞是**按帧**推进的，只写参数不推进
等于看的是上一帧（这一条也让早期几次实验白跑了）。

用法
----
    python3 tools/qa_eye_sweep.py --port 5173 --out logs/asset_qa/t66_22b_arc.png
    python3 tools/qa_eye_sweep.py --port 5173 --steps 1.0,0.45,0.0 --zoom 16 --crop 190,124,234,168
不加 --crop 时按帧尺寸自动取"脸上部中间"一块，四形态都能用。
"""
import argparse
import io
import json
import os
import sys
import time
import urllib.request

from PIL import Image, ImageDraw, ImageFont

FONT = ("/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf")


def get(port, path, timeout=10.0):
    with urllib.request.urlopen("http://127.0.0.1:%d%s" % (port, path), timeout=timeout) as r:
        return r.read()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=5173)
    ap.add_argument("--out", default="logs/asset_qa/eye_sweep.png")
    ap.add_argument("--steps", default="1.0,0.9,0.8,0.7,0.6,0.5,0.4,0.3,0.2,0.1,0.0")
    ap.add_argument("--crop", default=None, help="x0,y0,x1,y1（帧坐标；默认自动取脸）")
    ap.add_argument("--zoom", type=int, default=10)
    ap.add_argument("--cols", type=int, default=6)
    ap.add_argument("--keep", default=None, help="逐档原图另存到这个目录")
    ap.add_argument("--param", default="ParamEyeLOpen")
    ap.add_argument("--param2", default="ParamEyeROpen")
    a = ap.parse_args()
    steps = [float(x) for x in a.steps.split(",") if x.strip()]

    # —— 固定观察条件（见文件头：缺一条图就不可信）——
    get(a.port, "/api/ambient?on=0")
    get(a.port, "/api/blink?on=0")
    get(a.port, "/api/pause?on=1&t=2.0")
    info = json.loads(get(a.port, "/api/info.json"))
    W, H = info["frame_w"], info["frame_h"]
    crop = ([int(x) for x in a.crop.split(",")] if a.crop
            else [int(W * 0.40), int(H * 0.13), int(W * 0.62), int(H * 0.235)])

    tiles = []
    for v in steps:
        get(a.port, "/api/param?id=%s&v=%.4f" % (a.param, v))
        if a.param2:
            get(a.port, "/api/param?id=%s&v=%.4f" % (a.param2, v))
        get(a.port, "/api/step?n=3")
        png = get(a.port, "/api/frame.png?t=5&s=100")
        im = Image.open(io.BytesIO(png)).convert("RGBA")
        if a.keep:
            os.makedirs(a.keep, exist_ok=True)
            im.save(os.path.join(a.keep, "open_%.2f.png" % v))
        t = im.crop(tuple(crop))
        tiles.append((v, t.resize((t.width * a.zoom, t.height * a.zoom), Image.NEAREST)))

    get(a.port, "/api/param?id=%s&reset=1" % a.param)
    if a.param2:
        get(a.port, "/api/param?id=%s&reset=1" % a.param2)
    get(a.port, "/api/pause?on=0")
    get(a.port, "/api/ambient?on=1")
    get(a.port, "/api/blink?on=1")

    tw, th = tiles[0][1].size
    cols = max(1, min(a.cols, len(tiles)))
    rows = (len(tiles) + cols - 1) // cols
    lab = 22
    board = Image.new("RGB", (cols * tw, rows * (th + lab)), (28, 30, 34))
    g = ImageDraw.Draw(board)
    f = ImageFont.truetype(FONT, 15)
    for i, (v, t) in enumerate(tiles):
        x, y = (i % cols) * tw, (i // cols) * (th + lab)
        # 透明处垫深灰：否则会误判成"边缘黑边"
        bg = Image.new("RGB", t.size, (46, 50, 58))
        bg.paste(t, (0, 0), t)
        board.paste(bg, (x, y + lab))
        g.text((x + 4, y + 3), "Open=%.2f" % v, font=f, fill=(232, 232, 232))
    os.makedirs(os.path.dirname(os.path.abspath(a.out)) or ".", exist_ok=True)
    board.save(a.out)
    print("[eye] 写出 %s（%d 档 ×%d，眼区 %s，%dx%d）"
          % (a.out, len(tiles), a.zoom, crop, board.width, board.height))
    return 0


if __name__ == "__main__":
    sys.exit(main())
