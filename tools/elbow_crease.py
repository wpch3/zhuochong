#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""肘折线（arm_*_crease）—— 修"折起手臂时肘部是一团没有轮廓的圆疙瘩"。

================================ 病因 ================================
第四十四问实拍（logs/asset_qa/q44_final_zoom.png）：挥手把肘折到内角 32° 之后，
前臂整段压在上臂上，两块青色沥青一样糊成一团，看不出"前臂在前、上臂在后"。

原因是**切口没有轮廓线**：`round_arm_sockets.py` 把前臂近端做成了以肘枢轴为心的
正圆（这一步是对的，官方口径「関節パーツは正円」），但那一圈是**从袖子内部切开**
的新边 —— 原画在那儿没有描边。伸直时它被上臂盖住看不见，一折起来就成了
"无边界的色块压色块"。

真人/插画的画法：前臂压在上臂前面时，**前臂的轮廓线要压在上臂的颜色上**。

================================ 做法 ================================
把这圈切口的轮廓线单独做成一个薄件：

  · 形状 = 前臂件在"肘圆周上**真正是边界**的那一段"（往外 2px 已经没有料了），
    自然就只取到近端那半圈，远端（袖子继续往手腕走的那一侧）不画。
  · 颜色 = 从前臂件自己的描边像素里取中位色（同一支笔）。
  · 层 146/147（压在前臂 144/145 之上），组跟前臂走。
  · **alpha 绑肘角**：伸直(ParamArm?B=0) → 0 全透明，折到 ~72° → 1。
    伸直时画面一个像素都不变；折起来才显形。
    （alpha = clamp(1 + 0.25·v − 1) ⇒ v=0→0、v=4→1、v=8→clamp 1）

这就是 Live2D 的「差分パーツ + パラメータでフェード」：不改原件、不动引擎，
靠一个参数驱动的薄件补上折叠时才需要的那条线。

幂等：写 arm_parts.json["elbow_crease"]；重复跑直接跳过（--force 强制）。

用法：
    python3 tools/elbow_crease.py --character xiaoxun --form teen [--force]
"""
import argparse
import io
import json
import math
import os
import sys

import numpy as np

from PIL import Image


def load(p):
    return Image.open(p).convert("RGBA")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--character", required=True)
    ap.add_argument("--form", required=True)
    ap.add_argument("--width", type=float, default=2.2, help="线宽（1x 像素）")
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args()

    base = os.path.join("characters", a.character, "forms", a.form)
    sprites = os.path.join(base, "sprites")
    apj = os.path.join(sprites, "arm_parts.json")
    with io.open(apj, encoding="utf-8") as f:
        J = json.load(f)
    parts = {p["id"]: p for p in J["parts"]}
    sig = {"width": a.width, "v": 1}
    if J.get("elbow_crease", {}).get("sig") == sig and not a.force:
        print("[crease] 已做过，跳过（--force 强制）")
        return 0

    done = {}
    for side in ("l", "r"):
        fid = "arm_%s_fore" % side
        cid = "arm_%s_crease" % side
        if fid not in parts:
            continue
        fo = parts[fid]
        piv = fo["pivot"]                      # 肘枢轴（切件坐标）
        R = J["round_socket"][side]["r_elbow"]

        geo = {}
        for s in (1, 2):
            suf = "" if s == 1 else "@2x"
            fpath = os.path.join(sprites, "%s%s.png" % (fid, suf))
            if not os.path.exists(fpath):
                continue
            im = load(fpath)
            al = np.array(im)[:, :, 3]
            px0, py0 = fo["pos"][0] * s, fo["pos"][1] * s
            cx, cy = piv[0] * s - px0, piv[1] * s - py0
            rr = R * s
            W = a.width * s

            def alpha_at(x, y):
                ix, iy = int(round(x)), int(round(y))
                if 0 <= ix < al.shape[1] and 0 <= iy < al.shape[0]:
                    return al[iy, ix]
                return 0

            # 描边色：前臂件边界上最暗的一批像素的中位色
            arr = np.array(im)
            edge_cols = []
            for k in range(0, 3600, 7):
                th = math.radians(k / 10.0)
                for d in (0.0, -1.0, -2.0):
                    x = cx + (rr + d) * math.cos(th)
                    y = cy + (rr + d) * math.sin(th)
                    ix, iy = int(round(x)), int(round(y))
                    if 0 <= ix < al.shape[1] and 0 <= iy < al.shape[0] and al[iy, ix] > 200:
                        c = arr[iy, ix]
                        if 0.3 * c[0] + 0.6 * c[1] + 0.1 * c[2] < 110:
                            edge_cols.append(c[:3])
                        break
            if edge_cols:
                ec = np.median(np.array(edge_cols), axis=0).astype(int)
            else:
                ec = np.array([45, 80, 100])

            # ★ 切口不是圆弧而是**直切线**（make_arm_parts 留了 elbow_overlap_px=24，
            #   所以前臂近端是一条横切边，只有两个角被正圆削圆）。第一版照圆周找，
            #   只找到 8~22px。改成沿前臂件的**真实边界**走：近端一侧 + 原本没有描边
            #   （亮＝袖面被切开）的那一段，就是需要补线的地方。
            m = al > 128
            er = (m & np.roll(m, 1, 0) & np.roll(m, -1, 0)
                  & np.roll(m, 1, 1) & np.roll(m, -1, 1)
                  & np.roll(np.roll(m, 1, 0), 1, 1) & np.roll(np.roll(m, -1, 0), -1, 1)
                  & np.roll(np.roll(m, 1, 0), -1, 1) & np.roll(np.roll(m, -1, 0), 1, 1))
            bnd = m & ~er
            YY, XX = np.mgrid[0:al.shape[0], 0:al.shape[1]]
            ax = np.array([piv[0] - parts["arm_%s_upper" % side]["pivot"][0],
                           piv[1] - parts["arm_%s_upper" % side]["pivot"][1]], float)
            ax /= np.hypot(*ax)                      # 肩→肘方向（= 前臂的近端朝后）
            along = (XX - cx) * ax[0] + (YY - cy) * ax[1]
            lum = (0.3 * arr[:, :, 0] + 0.6 * arr[:, :, 1] + 0.1 * arr[:, :, 2])
            cut = bnd & (along < 6.0 * s) & (lum > 110)
            pts = {}
            ys_, xs_ = np.nonzero(cut)
            W_i = int(round(W))
            for (yy0, xx0) in zip(ys_, xs_):
                for dy in range(-W_i, W_i + 1):
                    for dx in range(-W_i, W_i + 1):
                        if dx * dx + dy * dy > W * W:
                            continue
                        X, Y = xx0 + dx, yy0 + dy
                        if 0 <= X < al.shape[1] and 0 <= Y < al.shape[0] and al[Y, X] > 64:
                            pts[(X, Y)] = 255
            if not pts:
                print("  [%s] %s 没找到切口边，跳过" % (side, suf or "1x"))
                continue
            xs = [p[0] for p in pts]
            ys = [p[1] for p in pts]
            if s == 1:
                geo["box"] = [min(xs) + fo["pos"][0], min(ys) + fo["pos"][1],
                              max(xs) + fo["pos"][0] + 1, max(ys) + fo["pos"][1] + 1]
            bx0, by0, bx1, by1 = geo["box"]
            Wd, Hd = int((bx1 - bx0) * s), int((by1 - by0) * s)
            out = np.zeros((Hd, Wd, 4), np.uint8)
            for (x, y) in pts:
                X = x + int(px0) - int(bx0 * s)
                Y = y + int(py0) - int(by0 * s)
                if 0 <= X < Wd and 0 <= Y < Hd:
                    out[Y, X] = [ec[0], ec[1], ec[2], 255]
            Image.fromarray(out).save(os.path.join(sprites, "%s%s.png" % (cid, suf)))
            geo[s] = [Wd, Hd, len(pts)]
            print("  [%s] %-3s 肘折线 %d px → %dx%d  色(%d,%d,%d)"
                  % (side, suf or "1x", len(pts), Wd, Hd, ec[0], ec[1], ec[2]))

        if "box" in geo:
            bx0, by0, bx1, by1 = geo["box"]
            ent = {
                "id": cid,
                "file": "sprites/%s.png" % cid,
                "group": "forearm_%s" % side,
                "layer": 146 if side == "l" else 147,
                "pos": [int(bx0), int(by0)],
                "size": [int(bx1 - bx0), int(by1 - by0)],
                "pivot": list(fo["pivot"]),
                "note": ("肘折线（Q44）：前臂近端正圆切口的轮廓线。伸直时 alpha=0 完全不显，"
                         "肘一折就显形 —— 没有它，折起来的前臂和上臂糊成一团没有边界"),
            }
            J["parts"] = [p for p in J["parts"] if p["id"] != cid] + [ent]
            parts[cid] = ent
            done[side] = {"r_elbow": R, "px_1x": geo.get(1, [0, 0, 0])[2]}

    J["elbow_crease"] = {"sig": sig, "sides": done}
    with io.open(apj, "w", encoding="utf-8") as f:
        json.dump(J, f, ensure_ascii=False, indent=1)
    print("[crease] 写回 %s" % apj)
    return 0


if __name__ == "__main__":
    sys.exit(main())
