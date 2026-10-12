#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""make_eye_parts.py - 把"一整块眼睛贴图"拆成 Live2D 式的四件可动零件。

为什么要拆：
  单图层素材里，眼睛是一整块（眼白 + 眼球 + 睫毛 + 周围皮肤画死在一起）。
  这样眼球就不能单独动——一动整块都动，眼睛会从脸上滑走。
  Live2D 的做法是把一只眼拆成"眼眶（裁切用）/ 眼白底 / 眼球 / 眼线睫毛"，
  眼球画成完整的圆（包括被眼皮盖住的那部分），再用眼眶把它裁出来。
  本脚本就是把这套结构从现有贴图里**还原**出来：

    <eye>_socket.png  眼眶轮廓（纯剪影，rig 里 mask_only=true，只当遮罩不显示）
    <eye>_base.png    眼白底：原贴图，但眼眶内部填成眼白色（眼球移开也不露洞）
    <eye>_ball.png    眼球：虹膜+瞳孔+高光，被眼皮遮住的上半部分按列补全成完整圆
    <eye>_lash.png    眼线/睫毛：压在眼球上面，眼球上翻时会被它盖住

  rig.json 里的层序必须是 socket < base < ball < lash，且 ball.mask = socket。

用法：
  ~/.imgenv/bin/python tools/make_eye_parts.py --character xiaoxun --form teen
"""
from __future__ import annotations
import argparse, json, os, sys
from collections import deque

import numpy as np
from PIL import Image


# ----------------------------------------------------------------- 形态学
def shift(m, dy, dx):
    out = np.zeros_like(m)
    h, w = m.shape
    ys0, ys1 = max(0, dy), min(h, h + dy)
    xs0, xs1 = max(0, dx), min(w, w + dx)
    out[ys0:ys1, xs0:xs1] = m[ys0 - dy:ys1 - dy, xs0 - dx:xs1 - dx]
    return out


def dilate(m, r=1):
    out = m.copy()
    for _ in range(r):
        acc = out.copy()
        for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (1, -1), (-1, 1), (-1, -1)):
            acc |= shift(out, dy, dx)
        out = acc
    return out


def erode(m, r=1):
    return ~dilate(~m, r)


def flood(mask, seed):
    """八连通洪水填充，返回与 seed 连通的那一块。"""
    out = np.zeros(mask.shape, bool)
    if not mask[seed]:
        return out
    q = deque([seed])
    out[seed] = True
    while q:
        y, x = q.popleft()
        for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (1, -1), (-1, 1), (-1, -1)):
            v, u = y + dy, x + dx
            if 0 <= v < mask.shape[0] and 0 <= u < mask.shape[1] and mask[v, u] and not out[v, u]:
                out[v, u] = True
                q.append((v, u))
    return out


def fill_holes(m):
    """填掉内部空洞：从画面边界洪水填充补集，没被填到的就是洞。"""
    h, w = m.shape
    free = ~m
    outside = np.zeros_like(m)
    q = deque()
    for x in range(w):
        for y in (0, h - 1):
            if free[y, x] and not outside[y, x]:
                outside[y, x] = True
                q.append((y, x))
    for y in range(h):
        for x in (0, w - 1):
            if free[y, x] and not outside[y, x]:
                outside[y, x] = True
                q.append((y, x))
    while q:
        y, x = q.popleft()
        for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            v, u = y + dy, x + dx
            if 0 <= v < h and 0 <= u < w and free[v, u] and not outside[v, u]:
                outside[v, u] = True
                q.append((v, u))
    return m | (free & ~outside)


def largest_cc(m):
    lab = np.zeros(m.shape, int)
    n, best, best_n = 0, None, 0
    for sy in range(m.shape[0]):
        for sx in range(m.shape[1]):
            if m[sy, sx] and lab[sy, sx] == 0:
                n += 1
                comp = flood(m & (lab == 0), (sy, sx))
                lab[comp] = n
                c = int(comp.sum())
                if c > best_n:
                    best_n, best = c, comp
    return best if best is not None else m


# ----------------------------------------------------------------- 拆件
def split_eye(path, side, debug=None):
    im = Image.open(path).convert("RGBA")
    a = np.array(im).astype(int)
    al = a[..., 3]
    rgb = a[..., :3]
    h, w = al.shape
    solid = al > 100

    # 1) 找眼睛：虹膜是"深蓝"（#4A8FD4 一类），头发的蓝高光要淡得多，用蓝红差挑出来
    core = solid & ((rgb[..., 2] - rgb[..., 0]) > 80) & (rgb[..., 0] < 170)
    if core.sum() < 20:
        raise SystemExit(f"{path}: 找不到虹膜（深蓝像素只有 {int(core.sum())} 个）")
    core = largest_cc(core)
    ys, xs = np.nonzero(core)
    seed = (int(np.median(ys)), int(np.median(xs)))

    # 2) 从虹膜往外长到整只眼睛：蓝色 + 深色线稿都算眼睛（眼白是洞，稍后补）
    loose = solid & (((rgb[..., 2] - rgb[..., 0]) > 38) | (rgb.sum(2) < 400))
    blob = flood(loose, seed)
    lens = fill_holes(blob)
    # 眉毛/发丝是细线，开运算（先腐蚀后膨胀）能把它们断掉，只留下眼睛这块"豆荚"
    lens = largest_cc(erode(lens, 2))
    lens = dilate(lens, 2) & fill_holes(blob)
    lens = fill_holes(lens)
    aperture = lens                      # 眼眶 = 眼睛开口（含眼线那一圈）

    # 3) 眼线/睫毛：眼眶里（略放宽）的深色笔触。
    #    关键是别把虹膜当成睫毛——睫毛是暖褐色（R≥B），虹膜哪怕最深的一圈也偏蓝（B>R）。
    near = dilate(aperture, 2)
    lash = near & (rgb.sum(2) < 430) & ((rgb[..., 2] - rgb[..., 0]) < 30)

    # 4) 虹膜圆：左右不会被眼皮挡住，用它定直径；下沿不会被挡，用它定圆心
    iris = aperture & ((rgb[..., 2] - rgb[..., 0]) > 30) & ~lash
    if iris.sum() < 20:
        iris = aperture & ((rgb[..., 2] - rgb[..., 0]) > 15)
    iris = largest_cc(iris)
    iy, ix = np.nonzero(iris)
    white = solid & (rgb.min(2) > 232)
    sclera_m = aperture & ~lash & ~iris
    yy, xx = np.mgrid[0:h, 0:w]
    # 虹膜上、左、右都可能被眼皮/眼角切掉，所以不能直接拿外接框当直径。
    # 这里小范围穷举圆心与半径，目标：圆要盖住所有看得见的虹膜，又别溢进眼白。
    best = None
    cx0, cy0 = float(ix.mean()), float(iy.mean())
    n_iris = float(iris.sum())
    for rad_t in np.arange(max(4.0, np.sqrt(n_iris / np.pi) * 0.8),
                           np.sqrt(n_iris / np.pi) * 1.9, 0.5):
        for cx_t in np.arange(cx0 - 5, cx0 + 5.01, 0.5):
            for cy_t in np.arange(cy0 - 6, cy0 + 6.01, 0.5):
                d2 = (xx - cx_t) ** 2 + (yy - cy_t) ** 2
                dd = d2 <= rad_t * rad_t
                miss = float((iris & ~dd).sum())      # 虹膜没被圆盖住
                spill = float((dd & sclera_m).sum())  # 圆压到眼白上
                cost = miss * 3.0 + spill
                if best is None or cost < best[0]:
                    best = (cost, cx_t, cy_t, rad_t)
    _, cx, cy, rad = best
    disc = ((xx - cx) ** 2 + (yy - cy) ** 2) <= (rad + 0.5) ** 2
    ball_src = aperture & disc & ~lash

    # 5) 眼球补全：被眼皮/眼线挡住的格子，按列从上方最近的已知像素补上去
    #    （Live2D 里这一步是美术把眼球画成完整的圆，这里用程序把它补出来）
    out = np.zeros((h, w, 4), np.uint8)
    out[..., :3] = rgb
    known = ball_src
    filled = known.copy()
    colors = rgb.copy()
    for x in range(w):
        col = np.nonzero(known[:, x])[0]
        if col.size == 0:
            continue
        top = col.min()
        for y in range(h):
            if disc[y, x] and not known[y, x]:
                srcy = top if y < top else col.max()
                colors[y, x] = rgb[srcy, x]
                filled[y, x] = True
    # 整列都没有已知像素（圆的最两侧）→ 从最近的有效列借色
    for x in range(w):
        if not (disc[:, x] & filled[:, x]).any():
            cand = [u for u in range(w) if (disc[:, u] & filled[:, u]).any()]
            if not cand:
                continue
            nx = min(cand, key=lambda u: abs(u - x))
            for y in range(h):
                if disc[y, x]:
                    colors[y, x] = colors[y, nx]
                    filled[y, x] = True

    # 眼球 alpha：圆内实心，边缘 1px 抗锯齿
    dist = np.sqrt((xx - cx) ** 2 + (yy - cy) ** 2)
    ball_a = np.clip((rad + 0.5 - dist), 0.0, 1.0) * 255.0
    ball_a = np.where(filled | disc, ball_a, 0.0)
    ball = np.zeros((h, w, 4), np.uint8)
    ball[..., :3] = colors
    ball[..., 3] = ball_a.astype(np.uint8)

    # 6) 眼白底：原贴图，眼眶内部（非眼线）填成眼白色，眼球挪开也不会露出洞
    sclera_px = rgb[white & aperture]
    sclera = sclera_px.mean(0) if len(sclera_px) >= 8 else np.array([253, 248, 246])
    base = np.array(im).copy()
    inner = aperture & ~lash
    for c in range(3):
        base[..., c] = np.where(inner, int(round(sclera[c])), base[..., c])
    base[..., 3] = np.where(inner, 255, base[..., 3])

    # 7) 眼线层：只留深色笔触，边缘按原 alpha 软化
    lash_img = np.zeros((h, w, 4), np.uint8)
    lash_img[..., :3] = rgb
    soft = np.clip((430 - rgb.sum(2)) / 60.0, 0.0, 1.0)
    lash_img[..., 3] = (np.where(lash, 1.0, 0.0) * soft * (al / 255.0) * 255.0).astype(np.uint8)

    # 8) 眼眶剪影（遮罩源）：实心白 + 1px 软边
    sock = np.zeros((h, w, 4), np.uint8)
    sock[..., :3] = 255
    edge = aperture & ~erode(aperture, 1)
    sock[..., 3] = np.where(aperture, np.where(edge, 170, 255), 0).astype(np.uint8)

    # 眼球可移动范围：虹膜本来就快把眼眶填满，所以移动时被眼眶裁掉一点是正常的
    # （这正是遮罩存在的意义）。按眼眶尺寸给个自然幅度，而不是要求"完全不被裁"。
    ay, ax = np.nonzero(aperture)
    ap_w = int(ax.max() - ax.min() + 1)
    ap_h = int(ay.max() - ay.min() + 1)
    travel_x = max(2, int(round(ap_w * 0.18)))
    travel_y = max(2, int(round(ap_h * 0.12)))

    # 眼球单独裁成小图，省得每帧画一整块透明区
    bx0, bx1 = int(max(0, np.floor(cx - rad - 1))), int(min(w, np.ceil(cx + rad + 2)))
    by0, by1 = int(max(0, np.floor(cy - rad - 1))), int(min(h, np.ceil(cy + rad + 2)))

    info = {
        "side": side,
        "iris_center": [round(float(cx), 1), round(float(cy), 1)],
        "iris_radius": round(float(rad), 1),
        "aperture_px": int(aperture.sum()),
        "ball_offset": [int(bx0), int(by0)],
        "ball_size": [int(bx1 - bx0), int(by1 - by0)],
        "travel": [int(travel_x), int(travel_y)],
        "aperture_size": [ap_w, ap_h],
        "sclera": "#%02X%02X%02X" % tuple(int(round(v)) for v in sclera),
    }
    # 透明处的 RGB 清零：省得残留的垃圾颜色混进验收统计，PNG 也能小一点
    for arr in (ball, lash_img, sock):
        arr[..., :3] = np.where(arr[..., 3:4] > 0, arr[..., :3], 0)
    ball_crop = ball[by0:by1, bx0:bx1]

    imgs = {
        "socket": Image.fromarray(sock),
        "base": Image.fromarray(base.astype(np.uint8)),
        "ball": Image.fromarray(ball_crop),
        "lash": Image.fromarray(lash_img),
    }
    if debug is not None:
        debug[side] = {"aperture": aperture, "lash": lash, "disc": disc, "im": im}
    return imgs, info


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--character", required=True)
    ap.add_argument("--form", required=True)
    ap.add_argument("--root", default=".")
    args = ap.parse_args()

    base_dir = os.path.join(args.root, "characters", args.character, "forms", args.form)
    sp_dir = os.path.join(base_dir, "sprites")
    report = json.load(open(os.path.join(sp_dir, "parts_report.json"), encoding="utf-8"))
    pos_of = {p["name"]: p["pos"] for p in report["parts"]}

    out = {"source": "eye_open_left.png / eye_open_right.png", "eyes": []}
    for side, src_name in (("l", "eye_open_left.png"), ("r", "eye_open_right.png")):
        src = os.path.join(sp_dir, src_name)
        imgs, info = split_eye(src, side)
        px, py = pos_of[src_name]
        info["patch_pos"] = [px, py]
        info["patch_size"] = list(Image.open(src).size)
        for key, img in imgs.items():
            name = f"eye_{side}_{key}.png"
            img.save(os.path.join(sp_dir, name))
            info[key] = name
        # 眼球自己的位置 = 贴图位置 + 裁切偏移
        info["ball_pos"] = [px + info["ball_offset"][0], py + info["ball_offset"][1]]
        out["eyes"].append(info)
        print(f"[{side}] 虹膜半径 {info['iris_radius']}px  眼眶 {info['aperture_px']}px  "
              f"可动范围 ±{info['travel'][0]}/±{info['travel'][1]}px  眼白 {info['sclera']}")

    with open(os.path.join(sp_dir, "eye_parts.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print("写出 sprites/eye_parts.json")


if __name__ == "__main__":
    main()
