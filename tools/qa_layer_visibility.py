#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""qa_layer_visibility.py —— 静止姿态下"某个部件到底露出多少"（离屏、确定性）

★ 为什么不能用"渲染两帧作差"
--------------------------------------------------------------------
2026-10-26 我在尾巴可见性上连错两次，根因都是**用帧差**：
同一状态连拍三次，严格判据下差异就有 2,788 / 3,437 px（最大通道差 255）——
渲染不是字节确定的。于是"关掉尾巴前后差 60,000 px"根本不是尾巴，
而是整张图的抖动。**帧差只能用来判"大形态有没有变"，不能用来数面积。**

★ 这里改成纯几何（静止姿态，默认参数）
--------------------------------------------------------------------
Live2D 的遮挡只有一条规则：**层号大的盖住层号小的**。于是：

    部件可见像素 = 它自己的不透明footprint − 所有层号更大部件的 footprint 并集

footprint 由 `rig.json` 的 `pos / anchor / scale` 把精灵 alpha 投到画布上得到
（与 `move_hair_islands.py` 里那三行数学同源，禁止再写第四遍）。

局限（写清楚，不许装作没有）：这算的是**静止姿态**下的遮挡。
摆姿势、形变之后会变；所以它是"基线闸"，不是运行时真值。

用法
----
    python3 tools/qa_layer_visibility.py --character xiaoxun --form teen \\
        --parts acc_tail_cat_relaxed acc_tail_cat_up acc_tail_cat_puff acc_tail_cat_tuck
    python3 tools/qa_layer_visibility.py --parts acc_hair_sidelong_l --min-visible 800
"""
from __future__ import annotations

import argparse
import json
import os
import sys

import numpy as np
from PIL import Image


class Placement:
    def __init__(self, part, size):
        self.pos = part["pos"]
        self.anchor = part["anchor"]
        sc = part.get("scale", 0.5)
        # ★ 少数件的 scale 是 [sx, sy]（嘴部遮罩/口腔按两轴不同比例缩放）。
        #   这里统一成二元组，别让调用方到处判类型 —— 写这一行是因为第一版
        #   直接把它当标量，`self.W * scale` 得到的是长度为 2 的数组，
        #   报错信息是"shapes (1840,) and (2,) could not be broadcast"，很难一眼看懂。
        self.scale = (sc, sc) if isinstance(sc, (int, float)) else (sc[0], sc[1])
        self.W, self.H = size

    def to_canvas(self, u, v):
        sx, sy = self.scale
        return (self.pos[0] + (u - self.W * self.anchor[0]) * sx,
                self.pos[1] + (v - self.H * self.anchor[1]) * sy)

    def canvas_bbox(self):
        """把精灵四角投到画布，返回 (x0, y0, x1, y1)。逐像素投影太慢，先用框粗筛。"""
        xs, ys = [], []
        for u in (0, self.W):
            for v in (0, self.H):
                x, y = self.to_canvas(u, v)
                xs.append(x)
                ys.append(y)
        return min(xs), min(ys), max(xs), max(ys)


def footprint(part, base, canvas, alpha_thr=24):
    path = os.path.join(base, part["file"])
    if not os.path.exists(path):
        return None
    im = Image.open(path).convert("RGBA")
    a = np.array(im)[:, :, 3]
    pl = Placement(part, (a.shape[1], a.shape[0]))
    ys, xs = np.nonzero(a > alpha_thr)
    if not len(xs):
        return None
    cx, cy = pl.to_canvas(xs, ys)
    cx = np.round(cx).astype(int)
    cy = np.round(cy).astype(int)
    ok = (cx >= 0) & (cx < canvas[0]) & (cy >= 0) & (cy < canvas[1])
    m = np.zeros((canvas[1], canvas[0]), bool)
    m[cy[ok], cx[ok]] = True
    return m


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--character", default="xiaoxun")
    ap.add_argument("--form", default="teen")
    ap.add_argument("--root", default=".")
    ap.add_argument("--parts", nargs="+", required=True)
    ap.add_argument("--min-visible", type=int, default=0,
                    help="低于它就算失败（退出码 1），用来接 CI")
    ap.add_argument("--overlay", default="", help="把「露出/被挡」画成一张图（红=露出，灰=被挡）")
    ap.add_argument("--pose", action="append", default=[], metavar="GROUP=ENTRY",
                    help="当前档位，可重复。同组其它条目里的部件会被当成隐藏（否则会把同伴当遮挡物）")
    a = ap.parse_args()

    base = os.path.join(a.root, "characters", a.character, "forms", a.form)
    rig = json.load(open(os.path.join(base, "rig.json"), encoding="utf-8"))
    canvas = (rig["canvas"]["w"], rig["canvas"]["h"])
    parts = rig["parts"]
    byid = {p["id"]: p for p in parts}

    # ��� poses 把"同组其它档位"的部件排除掉。这一步不做，算出来的可见量是错的。
    hidden = set()
    for spec in a.pose:
        if "=" not in spec:
            raise SystemExit("--pose 要写成 GROUP=ENTRY，例如 tail_pose=relaxed")
        gid, ent = spec.split("=", 1)
        grp = next((g for g in rig.get("poses", []) if g.get("id") == gid), None)
        if not grp:
            raise SystemExit("rig 里没有 pose group：%s" % gid)
        ids = [e.get("id") for e in grp.get("entries", [])]
        if ent not in ids:
            raise SystemExit("%s 里没有档位 %s（有 %s）" % (gid, ent, ids))
        for e in grp.get("entries", []):
            if e.get("id") != ent:
                hidden.update(e.get("parts", []))
    if hidden:
        print("（按档位隐藏 %d 件：%s%s）" % (
            len(hidden), ", ".join(sorted(hidden)[:4]), " …" if len(hidden) > 4 else ""))
    parts = [p for p in parts if p["id"] not in hidden] + [p for p in parts if p["id"] in hidden]
    # ↑ 顺序无关；hidden 的部件 footprint 照算但不参与遮挡（下面 fps 里置 None）

    # 先把所有部件的 footprint 算出来（缓存，别重复读图）
    fps = {}
    for p in parts:
        fps[p["id"]] = None if p["id"] in hidden else footprint(p, base, canvas)

    bad = 0
    overlays = []
    print("%-24s %-6s %9s %9s %8s" % ("part", "layer", "footprint", "visible", "占比"))
    for pid in a.parts:
        p = byid.get(pid)
        if not p:
            print("  [错误] rig 里没有 %s" % pid)
            bad += 1
            continue
        own = fps.get(pid)
        if own is None:
            print("  [错误] %s 的精灵读不出来" % pid)
            bad += 1
            continue
        cover = np.zeros_like(own)
        for q in parts:
            if q["layer"] > p["layer"] and fps.get(q["id"]) is not None:
                cover |= fps[q["id"]]
        vis = own & ~cover
        n_own, n_vis = int(own.sum()), int(vis.sum())
        pct = 100.0 * n_vis / n_own if n_own else 0.0
        flag = ""
        if a.min_visible and n_vis < a.min_visible:
            flag = "  ← 低于 %d" % a.min_visible
            bad += 1
        print("%-24s %-6s %9d %9d %7.1f%%%s" % (pid, p["layer"], n_own, n_vis, pct, flag))
        overlays.append((pid, own, vis, n_vis))

    if a.overlay:
        _write_overlay(a.overlay, canvas, overlays)
    return 1 if bad else 0


def _write_overlay(path, canvas, overlays):
    """每件一行：灰 = 它自己的形状，红 = 真正露出来的那一部分。"""
    from PIL import ImageDraw
    tiles = []
    for pid, own, vis, n_vis in overlays:
        img = np.full((canvas[1], canvas[0], 3), 24, np.uint8)
        img[own] = (90, 92, 104)
        img[vis] = (255, 40, 40)
        im = Image.fromarray(img)
        im.thumbnail((240, 400), Image.LANCZOS)
        t = Image.new("RGB", (im.width + 6, im.height + 22), (18, 18, 22))
        t.paste(im, (3, 20))
        ImageDraw.Draw(t).text((4, 3), "%s: %d px" % (pid.replace("acc_tail_cat_", "tail="), n_vis),
                               fill=(255, 255, 0))
        tiles.append(t)
    W = sum(t.width for t in tiles)
    H = max(t.height for t in tiles)
    sh = Image.new("RGB", (W, H), (10, 10, 12))
    x = 0
    for t in tiles:
        sh.paste(t, (x, 0))
        x += t.width
    sh.save(path)
    print("叠图 →", path)


if __name__ == "__main__":
    sys.exit(main())
