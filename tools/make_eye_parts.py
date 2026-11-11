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
from PIL import Image, ImageFilter


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
def keep_big_cc(m, min_px: int):
    """去掉面积小于 min_px 的碎连通块（睫毛边缘的麻点就是这些）。"""
    lab = np.zeros(m.shape, np.int32)
    keep = np.zeros(m.shape, bool)
    n = 0
    for sy in range(m.shape[0]):
        for sx in range(m.shape[1]):
            if m[sy, sx] and lab[sy, sx] == 0:
                n += 1
                comp = flood(m & (lab == 0), (sy, sx))
                lab[comp] = n
                if int(comp.sum()) >= min_px:
                    keep |= comp
    return keep


def _align_mask(src, ref):
    """把 src 掩膜平移到 ref 掩膜的中心（按内容外接框中心对齐）。"""
    ay, ax = np.nonzero(src)
    by, bx = np.nonzero(ref)
    if not len(ay) or not len(by):
        return src
    dy = int(round((by.min() + by.max()) * 0.5 - (ay.min() + ay.max()) * 0.5))
    dx = int(round((bx.min() + bx.max()) * 0.5 - (ax.min() + ax.max()) * 0.5))
    h, w = ref.shape          # ★ 按**目标**形状建画布：左右眼画布可能差 1px
    out = np.zeros((h, w), bool)
    sh, sw = src.shape
    y0, y1 = max(0, dy), min(h, dy + sh)
    x0, x1 = max(0, dx), min(w, dx + sw)
    if y1 > y0 and x1 > x0:
        out[y0:y1, x0:x1] = src[y0 - dy:y1 - dy, x0 - dx:x1 - dx]
    return fill_holes(out)


def split_eye(path, side, debug=None, form=None, mirror_socket=None):
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
    core_box = (int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1)

    # 2) 从虹膜往外长到整只眼睛：蓝色 + 深色线稿 + **眼白**都算眼睛。
    #    ★ 2026-11-11 修复（用户"眼睛两边很乱很糊"）：旧判据只有「蓝」和「暗」，
    #      眼白（R≈250 G≈247 B≈247）既不蓝也不暗 ⇒ 长不到，aperture 只剩
    #      「虹膜 + 上睫毛」，眼白整个露在掩膜外，于是 base 在眼白处被填成
    #      云状白团、又被椭圆 envelope 切成方块缺口。
    #      现在把眼白也加进判据，但必须排除脸部皮肤（皮肤也亮且低饱和）：
    #      皮肤是暖色（R 明显 > B），眼白是冷/中性（B ≥ R-10）。
    _rr, _gg, _bb = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    _skin = solid & (_rr > 200) & (_rr > _bb + 18)
    _sclera = solid & (_rr > 222) & (_gg > 210) & (_bb > 210) \
        & ((_bb - _rr) > -10) & (~_skin)
    #    还要限制在虹膜附近：否则眼白判据会顺着皮肤/白衣服一路漫出去。
    _iy0, _iy1 = ys.min(), ys.max() + 1
    _ix0, _ix1 = xs.min(), xs.max() + 1
    _ih, _iw = max(1, _iy1 - _iy0), max(1, _ix1 - _ix0)
    _ex, _ey = (_ix0 + _ix1 - 1) * 0.5, (_iy0 + _iy1 - 1) * 0.5
    _yy2, _xx2 = np.mgrid[0:h, 0:w]
    _near_iris = (((_xx2 - _ex) / (_iw * 1.15)) ** 2
                  + ((_yy2 - _ey) / (_ih * 1.45)) ** 2) <= 1.0
    loose = solid & ((((rgb[..., 2] - rgb[..., 0]) > 38)
                      | (rgb.sum(2) < 400)
                      | _sclera) & _near_iris)
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
    if form == "chibi":
        # ★ 2026-11-11：原来把**整个眼眶**都填成平涂眼白，结果眼角外侧那片
        #   被 socket 吃进来的原画眼白/皮肤全变成一块死白云（用户看到的
        #   "眼角白色残渣"）。只填**眼球真正会挪出去的那块**才需要兜底：
        #   以虹膜圆心为中心、半径 = 眼球半径 + 可动幅度，其余保持原画像素。
        _ay, _ax = np.nonzero(aperture)
        _tr = max(2, int(round((_ax.max() - _ax.min() + 1) * 0.18)))
        _ty = max(2, int(round((_ay.max() - _ay.min() + 1) * 0.12)))
        _fill = inner & (((xx - cx) ** 2) / ((rad + _tr + 1) ** 2)
                         + ((yy - cy) ** 2) / ((rad + _ty + 1) ** 2) <= 1.0)
    else:
        _fill = inner
    for c in range(3):
        base[..., c] = np.where(_fill, int(round(sclera[c])), base[..., c])
    base[..., 3] = np.where(_fill, 255, base[..., 3])

    # 7) 眼线层：只留深色笔触，边缘按原 alpha 软化
    lash_img = np.zeros((h, w, 4), np.uint8)
    lash_img[..., :3] = rgb
    soft = np.clip((430 - rgb.sum(2)) / 60.0, 0.0, 1.0)
    if form == "chibi":
        # ★ 2026-11-11：旧写法把「soft 灰度×源 alpha」直接当不透明度，中灰区域
        #   留下大量半透明麻点，放大看睫毛边缘是一圈噪点（用户说的"糊"）。
        #   改成：只认真正的深色笔触 → 去掉小于 24px 的碎点 → 用高斯把二值
        #   掩膜柔化出 1px 抗锯齿边。整条线因此是实心、边缘连续。
        _lm = lash & (rgb.sum(2) < 400)
        _lm = keep_big_cc(_lm, 24)
        _la = Image.fromarray((_lm * 255).astype(np.uint8), "L")
        _la = _la.filter(ImageFilter.GaussianBlur(0.8))
        lash_img[..., 3] = np.asarray(_la)
    else:
        lash_img[..., 3] = (np.where(lash, 1.0, 0.0) * soft * (al / 255.0) * 255.0).astype(np.uint8)

    # 8) 眼眶剪影（遮罩源）
    #    遮罩要比"眼眶"再往下吃一点：原画里眼白下缘有一层淡蓝（#CCE2E7 一类），
    #    蓝红差只有 27，第 2 步的 flood 判据（>38）够不着，于是它既不在眼眶里、
    #    也就不在遮罩里 —— 眼皮盖下来时这条淡蓝一直露在外面，眼睛**闭不严**
    #    （实测闭眼帧画布 y279..285 那条淡蓝和睁眼帧一模一样）。
    #    所以逐列往下延伸，直到撞上下眼睑的皮肤为止（最多 8px）。
    #    只放大遮罩，不动 aperture：眼白/虹膜/眼线的判定还按原来的来，
    #    睁眼时这块淡蓝保持原画像素不变。
    sock_m = aperture.copy()
    skin_px_m = solid & (rgb[..., 0] > 200) & (rgb[..., 0] > rgb[..., 2] + 18)
    for c in range(w):
        rows = np.nonzero(aperture[:, c])[0]
        if not len(rows):
            continue
        for y in range(int(rows.max()) + 1, min(h, int(rows.max()) + 9)):
            if skin_px_m[y, c] or not solid[y, c]:
                break
            sock_m[y, c] = True
    # 再把"眼角那两撇"吃进来：外眼角的眼白和那根睫毛尖在第 2 步的 flood 判据之外
    #   （眼白 R≈250 B≈247 既不蓝也不暗），它们不在遮罩里，闭眼时就留在脸上
    #   （实测闭眼帧左眼 x363..370 y271..281 还是一块白）。
    #   做法：从现有遮罩往外长，只认"眼白色"和"眼线黑"，范围限制在眼眶外扩 10px 内。
    ay_, ax_ = np.nonzero(aperture)
    bb = (max(0, ay_.min() - 10), min(h, ay_.max() + 11),
          max(0, ax_.min() - 10), min(w, ax_.max() + 11))
    zone = np.zeros((h, w), bool)
    zone[bb[0]:bb[1], bb[2]:bb[3]] = True
    sclera_like = solid & (rgb.min(2) > 225) & (np.abs(rgb[..., 0] - rgb[..., 2]) < 18)
    dark_like = solid & (rgb.sum(2) < 430)
    growable = zone & (sclera_like | dark_like)
    for _ in range(10):
        nxt = sock_m | (dilate(sock_m, 1) & growable)
        if nxt.sum() == sock_m.sum():
            break
        sock_m = nxt
    sock_m = fill_holes(sock_m)

    carve_m = aperture
    # Chibi：socket 直接取**真实眼形**（眼白+虹膜+眼线围出来的那块），
    # 不再用「椭圆 envelope ∪ 虹膜圆盘」拼。旧做法把眼眶画成圆坨 + 方形缺口，
    # 于是 base 在眼白处是一片云状白团、又被 envelope 的矩形边切成硬方块，
    # 用户看到的就是"眼白是方块、眼角有白色残渣"。
    # 现在 aperture（第 2 步已经把眼白算进去）本身就是眼形，先去掉睫毛尖这类
    # 细长外延（开运算），再 fill_holes 补严，最后只保留与虹膜相连的那一大块。
    if form == "chibi":
        sock_m = fill_holes(largest_cc(erode(aperture, 1)))
        sock_m = dilate(sock_m, 1) & fill_holes(aperture)
        sock_m = fill_holes(sock_m)
        # 轮廓平滑：色块判据出来的边界是锯齿多边形，直接当眼眶会在眼白外缘留下
        # 一圈阶梯边（用户看到的"糊"）。反复做「高斯模糊→按 0.5 二值化」，
        # 相当于对轮廓做几次温和的低通，边界变连续曲线。
        _f = Image.fromarray((sock_m * 255).astype(np.uint8), "L")
        for _ in range(3):
            _f = _f.filter(ImageFilter.GaussianBlur(2.2))
            _f = _f.point(lambda v: 255 if v >= 128 else 0)
        sock_m = np.asarray(_f) >= 128
        # 左右眼在原画里是同一只眼镜像出来的（实测镜像重合 98.5%）。右眼单独做
        # 色块分割时，上睫毛尖会和眼孔连成一条"月牙钩"，形态学剥不掉（同一条
        # run）。既然本来就对称，右眼直接复用左眼掩膜的镜像，按内容外接框对齐。
        if mirror_socket is not None:
            sock_m = _align_mask(mirror_socket[:, ::-1], sock_m)

        # 眼眶里必须至少包住虹膜，否则说明判据崩了，宁可报错不写脏图
        if int((sock_m & iris).sum()) < 0.85 * int(iris.sum()) or int(sock_m.sum()) < 1500:
            raise SystemExit(
                f"{path}: Chibi 眼眶掩膜异常（覆盖虹膜 "
                f"{int((sock_m & iris).sum())}/{int(iris.sum())}，"
                f"总面积 {int(sock_m.sum())}），拒绝写出")
        carve_m = sock_m

    # The base is masked by this expanded socket in the rig. Therefore its pixels
    # across the *whole* socket must be clean sclera underlay, not source iris/hair
    # pixels left over from the rectangular eye crop. The lash is a separate moving
    # layer, so it must not remain baked into the base either. Keep the mask's soft
    # edge for compositing; make the base opaque inside the binary socket core.
    if form == "chibi":
        # ★ 2026-11-11：这一段原来把**整个眼眶**无条件刷成平涂眼白，
        #   于是把步骤 6 里"只在眼球可动区兜底"的结果又覆盖掉了，眼角外侧
        #   那片本可以保留原画柔和眼白的地方变成一块死白云 —— 正是用户说的
        #   "眼角白色残渣"。现在分两层：
        #     ① 眼眶内、原画本来就是眼白/浅色的像素 → 原样保留（有明暗过渡）
        #     ② 眼球可动区内、原画是虹膜/眼线的像素 → 刷平涂眼白兜底
        #        （眼球挪开后这里必须不留虹膜残像）
        # ② 保留原画的柔和眼白：眼眶里**本来就是亮/低饱和**的像素原样留着
        #    （原画眼白有淡淡的冷暖过渡和眼窝阴影，全刷平涂才会读出"云块"）。
        #    只有真的深色（虹膜/睫毛根）才刷眼白，因为眼球挪开后那里不能留残像。
        _rr4, _gg4, _bb4 = rgb[..., 0], rgb[..., 1], rgb[..., 2]
        _lum4 = 0.299 * _rr4 + 0.587 * _gg4 + 0.114 * _bb4
        _orig_sclera = sock_m & (_lum4 > 196) & ((_rr4 - _bb4) < 26)
        for c in range(3):
            base[..., c] = np.where(_fill, int(round(sclera[c])), base[..., c])
            base[..., c] = np.where(sock_m & ~_fill & ~_orig_sclera,
                                    int(round(sclera[c])), base[..., c])
    else:
        for c in range(3):
            base[..., c] = np.where(sock_m, int(round(sclera[c])), base[..., c])
    # The rig attaches a socket mask, so Chibi's base only needs clean pixels in
    # that aperture. Do not retain its opaque crop halo: the wide-eye generator could
    # otherwise stretch surrounding face/hair into a visible rectangle. Preserve the
    # legacy Teen alpha path unchanged.
    if form == "chibi":
        base[..., 3] = np.where(sock_m, 255, 0)
    else:
        base[..., 3] = np.where(sock_m, 255, base[..., 3])

    sock = np.zeros((h, w, 4), np.uint8)
    sock[..., :3] = 255
    # 边缘给 2px 斜坡（不是一圈 170 的硬边），遮罩边界才不会出现阶梯
    cov = sock_m.astype(np.float32)
    for _ in range(2):
        acc = cov.copy()
        for dy2 in (-1, 0, 1):
            for dx2 in (-1, 0, 1):
                if dy2 or dx2:
                    acc += np.roll(np.roll(cov, dy2, 0), dx2, 1)
        cov = acc / 9.0
    cov = np.clip(cov * 1.45 - 0.25, 0.0, 1.0)
    cov[sock_m & (cov > 0.6)] = 1.0
    sock[..., 3] = np.clip(cov * 255.0 + 0.5, 0, 255).astype(np.uint8)

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
    if form == "chibi":
        # Keep the complete original eye silhouette for face cleanup. The eye socket
        # is intentionally narrower than the source eye on Chibi; using only the
        # socket to carve seg_head leaves the baked top half of the iris behind.
        carve_img = np.zeros((h, w, 4), np.uint8)
        carve_img[..., :3] = 255
        carve_img[..., 3] = np.where(carve_m, 255, 0).astype(np.uint8)
        imgs["carve"] = Image.fromarray(carve_img)
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
    _left_socket = None
    for side, src_name in (("l", "eye_open_left.png"), ("r", "eye_open_right.png")):
        src = os.path.join(sp_dir, src_name)
        imgs, info = split_eye(src, side, form=args.form,
                               mirror_socket=_left_socket)
        if side == "l" and args.form == "chibi":
            _left_socket = np.asarray(imgs["socket"])[..., 3] > 128
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
