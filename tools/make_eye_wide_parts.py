#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""make_eye_wide_parts.py —— 真·瞪大眼（ParamEyeL/RWide）补片

为什么这张补片**不再**从 AI 重绘里切
--------------------------------------
Live2D 里 `ParamEyeLWide` 不是"换一张新画"，而是把**同一张眼件的顶点往上拉**：
眼眶张开、眼白露得多、虹膜尺寸不变。Cubism 官方参数表写的是
"Widen the eye beyond ParamEyeLOpen"，实现上就是网格形变。

本工程的引擎还没有可变形网格（P0 待做，见 docs/ENGINE_AUDIT_2026-10-25.md），
能做的是**整件仿射**。所以这张补片的正确做法是：
拿原画自己的 `eye_<side>_base.png`（眼白 + 上睫毛），以眼球中心为锚各向异性放大
（横向 x1.12、纵向 x1.20），虹膜本来就不在这张图里（在 eye_<side>_ball 上）——
等价于"眼眶被撑开、虹膜不变"，和 Cubism 的口径一致。

为什么不用 AI 重绘那张 `face_eyeswide.png`
------------------------------------------
试过，且配准是准的（按虹膜两点相似变换，误差 < 2px），问题出在**画**上：
AI 把"瞪大"画成了"整只眼放大"——重绘眼白 127x136 画布像素，而本体眼眶只有
104x87。照抄的结果是脸颊上一块白色圆角矩形（沙箱实拍 /tmp/f_surprise.png、
/tmp/surprise_zoom2.png）。把它各向异性缩回眼眶尺寸后又变成"重新画一遍眼白"，
边缘必然和原画对不上（覆盖率当场掉到 0%）。
一句话：这张 AI 图的比例和本体不是同一套，硬套只能二选一（白板 / 错边）。

输出：sprites/eye_l_wide.png、eye_r_wide.png、eye_wide_parts.json
      （字段与 make_eye_closed_parts.py 的 --variant wide 完全兼容，make_rig 不用改）

用法：
  ~/.imgenv/bin/python tools/make_eye_wide_parts.py --character xiaoxun --form chibi
"""
from __future__ import annotations

import argparse
import json
import os

import numpy as np
from PIL import Image

# 眼眶撑开的量。live2d 的 EyeWide 一般是把上眼线抬 10~20%、下眼线不动，
# 这里用各向异性放大近似：横向 1.12（眼白变宽）、纵向 1.20（上眼线抬高）。
KX = 1.12
KY = 1.20
FEATHER = 0.14      # 边缘羽化占比（相对半径）——不含羽化的话放大后边界是一圈硬线


def _dilate(mask, n):
    m = mask.copy()
    for _ in range(n):
        g = m.copy()
        g[1:, :] |= m[:-1, :]
        g[:-1, :] |= m[1:, :]
        g[:, 1:] |= m[:, :-1]
        g[:, :-1] |= m[:, 1:]
        m = g
    return m


def _isolate(mask, seed):
    """只留与 seed 连通的那一块（4 邻域）。"""
    from collections import deque
    h, w = mask.shape
    if not mask[seed]:
        ys, xs = np.nonzero(mask)
        if ys.size == 0:
            return mask
        seed = (int(ys[0]), int(xs[0]))
    keep = np.zeros_like(mask)
    q = deque([seed])
    keep[seed] = True
    while q:
        cy, cx = q.popleft()
        for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            ny, nx = cy + dy, cx + dx
            if 0 <= ny < h and 0 <= nx < w and mask[ny, nx] and not keep[ny, nx]:
                keep[ny, nx] = True
                q.append((ny, nx))
    return keep


def _fill_holes(mask):
    """把 mask 内部的洞补上（从边界 flood 背景，没被淹到的空洞算作内部）。"""
    from collections import deque
    h, w = mask.shape
    bg = ~mask
    seen = np.zeros_like(mask)
    q = deque()
    for x in range(w):
        for y in (0, h - 1):
            if bg[y, x] and not seen[y, x]:
                seen[y, x] = True
                q.append((y, x))
    for y in range(h):
        for x in (0, w - 1):
            if bg[y, x] and not seen[y, x]:
                seen[y, x] = True
                q.append((y, x))
    while q:
        cy, cx = q.popleft()
        for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            ny, nx = cy + dy, cx + dx
            if 0 <= ny < h and 0 <= nx < w and bg[ny, nx] and not seen[ny, nx]:
                seen[ny, nx] = True
                q.append((ny, nx))
    return mask | (bg & ~seen)


def _premul_scale(rgb, a, kx, ky):
    pm = np.dstack([rgb * a[..., None], a * 255.0])
    im = Image.fromarray(np.clip(pm, 0, 255).astype(np.uint8), "RGBA")
    im = im.resize((max(4, int(round(rgb.shape[1] * kx))),
                    max(4, int(round(rgb.shape[0] * ky)))), Image.LANCZOS)
    arr = np.asarray(im).astype(np.float32)
    a2 = arr[..., 3] / 255.0
    rgb2 = np.clip(arr[..., :3] / np.maximum(a2[..., None], 1e-3), 0, 255)
    return rgb2, a2


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--character", required=True)
    ap.add_argument("--form", required=True)
    ap.add_argument("--root", default=".")
    a = ap.parse_args()

    sp = os.path.join(a.root, "characters", a.character, "forms", a.form, "sprites")
    body = np.array(Image.open(os.path.join(sp, "body_full.png")).convert("RGBA"))
    H, W = body.shape[:2]
    brgb = body[..., :3].astype(np.float32)
    bkeep = body[..., 3] > 128
    eyes = {e["side"]: e for e in
            json.load(open(os.path.join(sp, "eye_parts.json"), encoding="utf-8"))["eyes"]}

    out = {"source": "eye_<side>_base.png（原画眼白 + 上睫毛）各向异性放大",
           "register": {"scale": [KX, KY], "ncc": None, "tx": 0.0, "ty": 0.0,
                        "seeded_by": "base_affine"},
           "source_note": "原画眼件仿射撑开（Live2D ParamEyeLWide 的贴图等价做法）",
           "eyes": []}

    for side in ("l", "r"):
        e = eyes[side]
        px, py = e["patch_pos"]
        base = np.array(Image.open(os.path.join(sp, f"eye_{side}_base.png")).convert("RGBA"))
        bh, bw = base.shape[:2]
        rgb = base[..., :3].astype(np.float32)
        alpha = base[..., 3].astype(np.float32) / 255.0
        # 睫毛件如果单独存在就叠上（有的形态把它并进 base 了）
        try:
            lash = np.array(Image.open(os.path.join(sp, f"eye_{side}_lash.png")).convert("RGBA"))
            if lash.shape[:2] == (bh, bw):
                la = lash[..., 3].astype(np.float32) / 255.0
                lrgb = lash[..., :3].astype(np.float32)
                m = la[..., None]
                rgb = rgb * (1 - m) + lrgb * m
                alpha = np.maximum(alpha, la)
        except OSError:
            pass

        # 以眼球中心为锚放大：锚点 = ball 框中心（画布坐标）→ base 图内坐标
        gx0, gy0 = e["ball_pos"]
        gw, gh = e["ball_size"]
        cxb, cyb = gx0 + gw / 2.0, gy0 + gh / 2.0      # 眼球中心（画布）
        cxl, cyl = cxb - px, cyb - py                  # 同一根锚在 base 图内
        # ★ base 件整幅 264x151 里除了眼白还带着眼眶外侧的一撮头发，
        #   直接放大等于把那撮头发一起糊到脸上（实测接缝色差 95）。
        #   只留与眼球中心连通的那一块 —— 眼球、上睫毛、眼线本来就是连着的。
        # 只留与眼球中心连通的那一块（base 件里还带着眼眶外侧的一撮头发）
        _seed = (int(np.clip(cyb - py, 0, bh - 1)), int(np.clip(cxb - px, 0, bw - 1)))
        keep_eye = _fill_holes(_isolate(base[..., 3] > 40, _seed))
        alpha = alpha * keep_eye.astype(np.float32)

        s_rgb, s_a = _premul_scale(rgb, alpha, KX, KY)
        sh, sw = s_a.shape
        nacx, nacy = cxl * KX, cyl * KY
        ax0 = int(round(cxb - nacx))
        ay0 = int(round(cyb - nacy))
        ax0 = max(0, min(W - sw, ax0))
        ay0 = max(0, min(H - sh, ay0))
        ax1, ay1 = ax0 + sw, ay0 + sh
        tgt = brgb[ay0:ay1, ax0:ax1]
        bk = bkeep[ay0:ay1, ax0:ax1]

        # alpha 口径**和闭眼件完全一致**：软椭圆 ∩ (原画这里是皮肤/线稿/眼睛)。
        # 这条口径在闭眼/笑眼/痛苦三档上已经验证过（不会把头发糊到脸上、也不会
        # 把脸糊成一整块）；早先试过"按颜色挑眼白"的写法，洞与边会互相打架，
        # 补片变成一块白色圆角矩形（沙箱实拍 /tmp/surprise_zoom5.png）。
        yy = np.arange(sh)[:, None].astype(np.float32)
        xx = np.arange(sw)[None, :].astype(np.float32)
        eccy, eccx = (sh - 1) / 2.0, (sw - 1) / 2.0
        rad = np.sqrt(((xx - eccx) / (sw / 2.0)) ** 2 + ((yy - eccy) / (sh / 2.0)) ** 2)
        kf = FEATHER / max(sw, sh) * 2.0
        soft = np.clip((1.0 - rad) / max(kf, 1e-3) + 0.35, 0, 1)
        _r, _b = tgt[..., 0], tgt[..., 2]
        body_skin = (_r > 200) & (_r > _b + 8)
        body_line = tgt.mean(axis=2) < 150
        eye_zone = np.zeros((sh, sw), bool)
        eye_zone[max(0, gy0 - 6 - ay0):min(sh, gy0 + gh + 6 - ay0),
                 max(0, gx0 - 6 - ax0):min(sw, gx0 + gw + 6 - ax0)] = True
        alpha2 = soft * s_a * bk * (body_skin | body_line | eye_zone).astype(np.float32)

        # 覆盖检查：原画眼球件必须被盖住（和闭眼件同一口径）
        must = np.zeros((sh, sw), bool)
        # 要盖住的"原画眼睛" = 眼球件 ∪ 眼白/睫毛件（后者正是这张补片要顶替的那张画）
        ball = np.array(Image.open(os.path.join(sp, f"eye_{side}_ball.png")).convert("RGBA"))
        bb_a = ball[..., 3]
        bh2, bw2 = bb_a.shape
        ox, oy = gx0 - ax0, gy0 - ay0
        sx0, sy0 = max(0, -ox), max(0, -oy)
        dx0, dy0 = max(0, ox), max(0, oy)
        cw = min(bw2 - sx0, sw - dx0)
        chh = min(bh2 - sy0, sh - dy0)
        if cw > 0 and chh > 0:
            must[dy0:dy0 + chh, dx0:dx0 + cw] |= bb_a[sy0:sy0 + chh, sx0:sx0 + cw] > 128
        cover = float((alpha2[must] > 0.9).mean()) if must.sum() else 1.0
        if cover < 0.995:
            raise SystemExit(f"[wide] {side} 放大后的补片没盖住眼球件（{cover:.1%}）——"
                             "KX/KY 太大或锚点算错")

        img = np.zeros((sh, sw, 4), np.uint8)
        img[..., :3] = np.clip(s_rgb, 0, 255).round().astype(np.uint8)
        img[..., 3] = (alpha2 * 255).round().astype(np.uint8)
        fn = f"eye_{side}_wide.png"
        Image.fromarray(img, "RGBA").save(os.path.join(sp, fn))

        edge = (alpha2 > 0.05) & (alpha2 < 0.95) & bk
        seam = float(np.abs(s_rgb - tgt)[edge].mean()) if edge.sum() else 0.0
        out["eyes"].append({
            "side": side, "file": fn, "pos": [ax0, ay0], "size": [sw, sh],
            "gain": [1.0, 1.0, 1.0], "offset": [0.0, 0.0, 0.0],
            "checks": {"cover_ratio": round(cover, 4), "seam_mean_abs": round(seam, 2),
                       "opaque_px": int((alpha2 > 0.9).sum()), "iris_erased_px": 0},
        })
        print(f"瞪大眼 {side}: {sw}x{sh} @ 身体({ax0},{ay0})  盖住眼球 {cover*100:.1f}%  "
              f"接缝色差 {seam:.1f}（原画眼件 x({KX},{KY}) 放大）")

    with open(os.path.join(sp, "eye_wide_parts.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print("[wide] → sprites/eye_wide_parts.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
