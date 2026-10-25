#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""qa_sockets.py —— 挂点（socket）的两件事：量 + 看（T66.19 / S4）。

为什么要这个工具
----------------
挂点如果只是"存了一对坐标"，它和把 pos 写死在配件里没有任何区别。它值不值得存在，
全靠一件事：**父骨动了，挂点跟着动**。这件事没法用眼睛看（0.55 的画布上 20px 只是
一条边），所以要有能算的数：

    python3 tools/qa_sockets.py probe      # 腕骨转 70°，每个挂点各走了多少 px
    python3 tools/qa_sockets.py overlay    # 把 8 个挂点画回角色帧上（引线 + 坐标）

probe 的判据来自实测（2026-10-25，teen / 默认缩放 0.55）：
    socket_wrist_l  26.5~37.2 px      socket_wrist_r  < 0.2 px
    其余 6 个挂点    < 0.6 px
腕骨只该带动腕挂点 —— 别的挂点动了，说明挂点没挂在各自的父骨上（例如全挂在 root）。

overlay 出图是 **QA 叠加图**，不是素材：标记只画在这张图上，不进 `characters/`。
帧是透明背景的 PNG，必须 alpha 合成到白底再转 RGB（直接 convert 会把透明处压成黑色）。
标签只写 ASCII —— PIL 自带位图字体没有中文字形，写中文会变成方框。
"""
from __future__ import annotations

import argparse
import io
import json
import os
import sys
import urllib.request

DEFAULT_BASE = "http://127.0.0.1:5173"


def api(base, path):
    return json.load(urllib.request.urlopen(base + path))


def freeze(base):
    """固定时钟 + 关 ambient/physics：两次读数之间只允许有我们主动改的那一个变量。"""
    api(base, "/api/pause?on=1&t=1000")
    api(base, "/api/ambient?on=0")
    api(base, "/api/physics?on=0")
    api(base, "/api/param?all=1&reset=1")
    api(base, "/api/step?n=40&dt=0.016")


def probe(base):
    freeze(base)
    d = api(base, "/api/sockets.json")
    socks = d.get("sockets") or []
    if not socks:
        print("没有挂点：/api/sockets.json 返回空数组")
        return 1
    base_pos = {s["id"]: tuple(s["screen"]) for s in socks}
    print("静止（画布像素，已乘当前缩放）：")
    for s in socks:
        print("  %-16s group=%-7s pos=%-12s screen=(%.2f, %.2f)"
              % (s["id"], s["group"], s["pos"], s["screen"][0], s["screen"][1]))
    api(base, "/api/param?id=ParamHandL&v=3.2")        # 腕骨 22×3.2 = 70.4°
    api(base, "/api/step?n=20&dt=0.016")
    d = api(base, "/api/sockets.json")
    print("\n腕骨转 70.4° 之后每个挂点走了多少：")
    worst = 0.0
    for s in d.get("sockets") or []:
        a = base_pos.get(s["id"])
        if not a:
            continue
        moved = abs(s["screen"][0] - a[0]) + abs(s["screen"][1] - a[1])
        if "wrist" not in s["id"]:
            worst = max(worst, moved)
        print("  %-16s %7.2f px" % (s["id"], moved))
    print("\n判据：腕挂点 >> 其它（其它最大 %.2f px，超过 3px 就说明挂点没挂在各自父骨上）"
          % worst)
    return 0 if worst < 3.0 else 1


def overlay(base, out):
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        print("overlay 需要 Pillow：用带 Pillow 的解释器跑，例如 "
              "/home/user/.imgenv/bin/python tools/qa_sockets.py overlay",
              file=sys.stderr)
        return 2

    freeze(base)
    d = api(base, "/api/sockets.json")
    raw = urllib.request.urlopen(base + "/api/frame.png").read()
    im = Image.open(io.BytesIO(raw)).convert("RGBA")
    bg = Image.new("RGBA", im.size, (255, 255, 255, 255))
    bg.alpha_composite(im)
    im = bg.convert("RGB")
    margin = 210
    canvas = Image.new("RGB", (im.width + margin * 2, im.height), (250, 250, 252))
    canvas.paste(im, (margin, 0))
    g = ImageDraw.Draw(canvas)
    rows = sorted(d.get("sockets") or [], key=lambda s: s["screen"][1])
    mid = im.width * 0.5
    left = [s for s in rows if s["screen"][0] < mid]
    right = [s for s in rows if s not in left]
    for side, group in (("L", left), ("R", right)):
        for i, s in enumerate(group):
            x, y = s["screen"][0] + margin, s["screen"][1]
            col = (214, 40, 40) if "wrist" in s["id"] else (20, 120, 190)
            g.line([(x - 8, y), (x + 8, y)], fill=col, width=2)
            g.line([(x, y - 8), (x, y + 8)], fill=col, width=2)
            ly = 26 + i * 22
            label = "%-10s %s  %d,%d" % (s["id"].replace("socket_", ""), s["group"],
                                         s["pos"][0], s["pos"][1])
            if side == "L":
                g.text((8, ly), label, fill=col)
                tw = g.textlength(label)
                g.line([(8 + tw + 6, ly + 5), (margin - 46, ly + 5)], fill=col, width=1)
                g.line([(margin - 46, ly + 5), (x, y)], fill=col, width=1)
            else:
                tx = margin + im.width + 10
                g.text((tx, ly), label, fill=col)
                g.line([(margin + im.width + 46, ly + 5), (tx - 6, ly + 5)],
                       fill=col, width=1)
                g.line([(margin + im.width + 46, ly + 5), (x, y)], fill=col, width=1)
    canvas = canvas.resize((canvas.width * 2, canvas.height * 2), Image.LANCZOS)
    canvas.save(out)
    print("写出 %s（%dx%d）" % (out, canvas.width, canvas.height))
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("what", choices=["probe", "overlay"])
    ap.add_argument("--base", default=DEFAULT_BASE)
    ap.add_argument("--out", default="logs/asset_qa/t66_19_sockets.png")
    a = ap.parse_args()
    if a.what == "probe":
        return probe(a.base)
    os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
    return overlay(a.base, a.out)


if __name__ == "__main__":
    sys.exit(main())
