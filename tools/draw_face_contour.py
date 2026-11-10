#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""draw_face_contour.py —— 把**脸的轮廓线（輪郭線）**按模板补回 seg_head 上。

为什么需要这一步（第三十二问，2026-10-21）
-------------------------------------------
用户原话：「脸的形状有点不对劲，感觉有点胖，以及没有描边」。两句话是**同一个缺陷**：

  量出来的事实 —— 把模板(design_sheet_short.png)和产物按同一几何逐行比脸宽：
      模板 sheet y=310 脸宽 100px → 产物 131.6px   (+32%)
      模板      y=316      90px → 产物 149.6px   (+66%)
      模板      y=322      72px → 产物 129.3px   (+80%)
      模板      y=328      48px → 产物  97.8px   (+104%)
  同一带模板的描边亮度是 34~88，产物最暗只有 237~253 —— **一条线都不剩**。

  成因有两层：
    ① 抠像把剪影上的线稿吃掉了（已在 prepare_sprites.py 重写里修掉，那是全身的）；
    ② **下颌这一段的线不在剪影上**，它在「脸 ↔ 头发」的内部交界上。
       切件时 make_sidehair_parts 把横髪从 seg_head 上挖走，线跟着头发一起走了，
       剩下的脸就是一圈没有边界的软肤色；再被 fix_seam 往外补成塗り足し，
       **脸在视觉上就一路胖到塗り足し的外沿**。
       短发档因为 hair_side_l/r(245·246) 正好盖住看不出来，
       twin / pony / long 一藏鬓发就全露出来。

做法（照 Live2D 官方与教程的口径，不是自己发明的）
--------------------------------------------------
  · Live2D Cubism 2 官方手册「01. 素材分けについて」：
    「パーツ同士の繋ぎ目も、動いた時に途切れてしまうのを防ぐために
      **『のりしろ』のように余分に描き足します**」＋ 明确给了**輪郭の例**；
    并且「**主線が無いパーツの分かれ目部分**は、モデルで綺麗に表示するために
      少しぼかしておきましょう」—— 反过来说，**有主線的地方就该是实的**。
    https://sites.google.com/a/cybernoids.jp/cubism2/modeler/texture/texture
  · CLIP STUDIO 官方教程（後編）给的描き足し顺序：
    ベースレイヤーを**パーツのベースカラー**で塗る → 影 → **その上に線画の
    描き足しレイヤーを作成し、線画を描写** → 最後にマスクで馴染ませる。
    https://tips.clip-studio.com/ja-jp/articles/674
    ⇒ 所以这里是「肤色塗り足し保持不动 + **在它上面单独补一条轮廓线**」，
      而不是把塗り足し裁掉（裁掉就违反第十问的「每件都要塗り足し」）。
  · 「輪郭を分ける際に注意が必要なのは、髪に隠れていた部分です…一旦髪の毛の
    レイヤーを非表示にし輪郭部分だけ表示して…途切れた部分から大体耳の付け根
    あたりまで描き足すと良いです」
    https://www.geboku-kyoudai.com/entry/Live2D-Head
    ⇒ 正是 twin/pony 的情形：藏掉鬓发以后，轮廓必须自己接到耳根。

实现
----
  1. 从模板上量出**脸的区域**（肤色最大连通块 + 填洞），得到亚像素的 face 掩膜；
  2. 用 design/body_fit.json 的仿射把它采样到 seg_head 的像素系（3×3 超采样）；
  3. 边界位置由平滑掩膜的 0.5 等值线给出，**带符号距离**用 (m-0.5)/|∇m| 估，
     所以线的位置是亚像素的，不会出现 1px 台阶；
  4. 线色不是拍脑袋定的：在模板上沿轮廓法线往外 3px 取**最暗**的像素，
     取不到（被头发压着）就退回全局线色；
  5. 只画**眼线以下**那段（额头被前髪压着，上面是头皮塗り足し，不能画线）；
  6. **只改 RGB，不动 alpha** —— seg_* 同时是 body_full 的分段件，
     check_assets 的「无损切分」闸对覆盖面积零容忍。

用法：python3 tools/draw_face_contour.py --character xiaoxun --form teen
"""
from __future__ import annotations

import argparse
import json
import os
import sys

try:
    import numpy as np
    from PIL import Image
except ImportError as e:  # pragma: no cover
    print(f"[错误] 需要 pillow 与 numpy：{e}", file=sys.stderr)
    sys.exit(2)

LINE_FALLBACK = (90, 90, 110)      # #5A5A6E，小寻的线稿色
LINE_W = 1.55                      # 1× 下的线宽（模板上约 2px × 0.89）
SS = 3                             # 掩膜超采样倍数


def skinish(rgb: np.ndarray) -> np.ndarray:
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    return ((r > 215) & (g > 180) & (b > 170) & (r >= g) & (g >= b)
            & ((r - b) > 8) & ((r - b) < 80))


def largest_blob(m: np.ndarray) -> np.ndarray:
    """八邻域最大连通块（沙箱没有 scipy，用 roll 迭代扩张）。"""
    ys, xs = np.where(m)
    if len(ys) == 0:
        return m
    # 从最靠近重心的点开始漫延
    cy, cx = int(ys.mean()), int(xs.mean())
    if not m[cy, cx]:
        d = (ys - cy) ** 2 + (xs - cx) ** 2
        cy, cx = int(ys[d.argmin()]), int(xs[d.argmin()])
    cur = np.zeros_like(m)
    cur[cy, cx] = True
    while True:
        nxt = cur.copy()
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                nxt |= np.roll(np.roll(cur, dy, axis=0), dx, axis=1)
        nxt &= m
        if nxt.sum() == cur.sum():
            return cur
        cur = nxt


def _grow(m: np.ndarray, r: int) -> np.ndarray:
    out = m.copy()
    for _ in range(r):
        nxt = out.copy()
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                nxt |= np.roll(np.roll(out, dy, axis=0), dx, axis=1)
        out = nxt
    return out


def close_gaps(m: np.ndarray, r: int) -> np.ndarray:
    """闭运算：把睫毛/眉毛在眼眶和外界之间留的窄通道封死。

    不封的话 fill_holes 会从画框外一路漫进眼睛，眼睛就不算"洞"，
    轮廓线会沿着眼眶画一圈（实测：左眼下睑被描了一道黑边）。
    """
    return ~_grow(~_grow(m, r), r)


def fill_holes(m: np.ndarray) -> np.ndarray:
    """从画框外漫延，漫不到的透明区就是洞（眼睛/嘴/腮红都在脸里面）。"""
    out = np.zeros_like(m)
    out[0, :] = out[-1, :] = True
    out[:, 0] = out[:, -1] = True
    out &= ~m
    while True:
        nxt = out.copy()
        for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nxt |= np.roll(out, (dy, dx), axis=(0, 1))
        nxt &= ~m
        if nxt.sum() == out.sum():
            break
        out = nxt
    return ~out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--character", required=True)
    ap.add_argument("--form", required=True)
    ap.add_argument("--root", default=".")
    ap.add_argument("--sheet", default=None)
    ap.add_argument("--debug", default=None, help="写一张对比图到这个路径")
    args = ap.parse_args()

    base = os.path.join(args.root, "characters", args.character)
    sp = os.path.join(base, "forms", args.form, "sprites")
    head_path = os.path.join(sp, "seg_head.png")
    if not os.path.exists(head_path):
        print(f"[脸轮廓] 没有 {head_path}，跳过")
        return 0

    sheet_path = args.sheet or os.path.join(base, "design", "design_sheet_short.png")
    fit_path = os.path.join(base, "design", "body_fit.json")
    if not (os.path.exists(sheet_path) and os.path.exists(fit_path)):
        print("[脸轮廓] 缺模板或 body_fit.json，跳过")
        return 0
    with open(fit_path, encoding="utf-8") as fh:
        allfit = json.load(fh)
    fit = allfit.get(os.path.basename(sheet_path))
    if not fit:
        print("[脸轮廓] body_fit.json 里没有这张模板的裁框，跳过")
        return 0
    fx, fy = fit["box"]
    fs = float(fit["scale"])

    with open(os.path.join(sp, "body_parts.json"), encoding="utf-8") as fh:
        bp = json.load(fh)
    parts = bp["parts"] if isinstance(bp, dict) else bp
    head = next(p for p in parts if p["id"] == "seg_head")
    hx, hy = head["pos"]

    sheet = np.asarray(Image.open(sheet_path).convert("RGB")).astype(np.int16)
    SH, SW = sheet.shape[:2]

    # ── 1. 模板上的脸 ────────────────────────────────────────────────
    win = np.zeros(sheet.shape[:2], bool)
    win[120:420, 330:700] = True           # 头部窗口（模板坐标）
    face = skinish(sheet) & win
    face = largest_blob(face)
    n0 = int(face.sum())
    face = fill_holes(close_gaps(face, 5))
    face = largest_blob(face)
    print(f"[脸轮廓] 肤色连通块 {n0} → 闭运算+填洞 {int(face.sum())} 像素")
    if face.sum() < 5000:
        print(f"[脸轮廓] 模板上量到的脸只有 {int(face.sum())} 像素，疑似判据失效，跳过")
        return 0
    ys, xs = np.where(face)
    print(f"[脸轮廓] 模板脸区 {int(face.sum())} 像素，"
          f"x {xs.min()}..{xs.max()} y {ys.min()}..{ys.max()}")

    # ── 2. 采样到 seg_head 像素系（3×3 超采样 ⇒ 亚像素掩膜） ─────────
    im = Image.open(head_path).convert("RGBA")
    H = np.asarray(im).astype(np.float32)
    hh, hw = H.shape[:2]
    oy, ox = np.meshgrid((np.arange(hh * SS) + 0.5) / SS,
                         (np.arange(hw * SS) + 0.5) / SS, indexing="ij")
    sx = fx + (ox + hx) / fs
    sy = fy + (oy + hy) / fs
    ix = np.clip(sx.astype(np.int32), 0, SW - 1)
    iy = np.clip(sy.astype(np.int32), 0, SH - 1)
    m_ss = face[iy, ix].astype(np.float32)
    m = m_ss.reshape(hh, SS, hw, SS).mean(axis=(1, 3))     # 0..1 的软掩膜

    # ── 3. 亚像素带符号距离：d = (m - 0.5) / |∇m| ───────────────────
    gy, gx = np.gradient(m)
    gmag = np.sqrt(gx ** 2 + gy ** 2)
    far = gmag < 1e-3
    dist = np.where(far, np.where(m > 0.5, 99.0, -99.0),
                    (m - 0.5) / np.maximum(gmag, 1e-3))
    cov = np.clip(LINE_W * 0.5 - np.abs(dist) + 0.5, 0.0, 1.0)

    # ── 4. 只画眼线以下那段（额头归前髪/头皮塗り足し管） ─────────────
    eyeline_sheet = 258.0
    eyeline_local = (eyeline_sheet - fy) * fs - hy
    yy = np.arange(hh)[:, None] * np.ones((1, hw))
    cov = np.where(yy > eyeline_local, cov, 0.0)

    # ── 4b. 眼眶里一笔都不许画 ───────────────────────────────────────
    # 脸的**外**轮廓不可能穿过眼睛。但模板上的眼眶并不总是封闭的 ——
    # 睫毛和鬓发之间常留一条 1~2px 的缝，fill_holes 就顺着缝漫进眼睛，
    # 眼眶于是也成了"脸的边界"，被描了一圈。
    # 实测（2026-10-21）：左右眼各在眼眶开口里多出 26 粒暗像素，
    # 正好撞上 check_assets 的「脸上无残留睁眼」闸（上限 24）——
    # 那条闸是对的：眼眶一收，这些线就从眼皮底下浮出来。
    # 这里按 17 步写出的 eyeline_parts.json 把两个眼眶整块挖掉。
    el_path = os.path.join(sp, "eyeline_parts.json")
    if os.path.exists(el_path):
        with open(el_path, encoding="utf-8") as fh:
            el = json.load(fh)
        n_eye = 0
        for e in el.get("eyes", []):
            spath = os.path.join(sp, e.get("socket") or f"eye_{e['side']}_socket.png")
            if not os.path.exists(spath):
                continue
            sock = np.asarray(Image.open(spath).convert("RGBA"))[..., 3]
            ph, pw = sock.shape
            ex, ey = e["patch_pos"]
            gy0, gx0 = ey - hy, ex - hx
            yA, xA = max(0, gy0), max(0, gx0)
            yB = min(hh, gy0 + ph)
            xB = min(hw, gx0 + pw)
            if yB <= yA or xB <= xA:
                continue
            sub = sock[yA - gy0:yB - gy0, xA - gx0:xB - gx0]
            blk = _grow(sub > 8, 3)
            n_eye += int((cov[yA:yB, xA:xB] > 0.1)[blk].sum())
            cov[yA:yB, xA:xB] = np.where(blk, 0.0, cov[yA:yB, xA:xB])
        if n_eye:
            print(f"[脸轮廓] 眼眶内剔除 {n_eye} 个轮廓像素（外轮廓不穿过眼睛）")

    alpha = H[..., 3]
    cov = np.where(alpha > 8, cov, 0.0)
    if cov.sum() < 10:
        print("[脸轮廓] 轮廓落在件外，跳过")
        return 0

    # ── 5. 线色：沿法线往外 3px 在模板上取最暗 ───────────────────────
    nx = np.where(gmag > 1e-3, -gx / np.maximum(gmag, 1e-3), 0.0)   # 指向外侧
    ny = np.where(gmag > 1e-3, -gy / np.maximum(gmag, 1e-3), 0.0)
    best = np.full(H.shape[:2] + (3,), -1.0, np.float32)
    bestl = np.full(H.shape[:2], 1e9, np.float32)
    for t in (0.0, 0.8, 1.6, 2.4, 3.2):
        px = fx + (np.arange(hw)[None, :] + hx + nx * t) / fs
        py = fy + (np.arange(hh)[:, None] + hy + ny * t) / fs
        c = sheet[np.clip(py.astype(np.int32), 0, SH - 1),
                  np.clip(px.astype(np.int32), 0, SW - 1)].astype(np.float32)
        lu = 0.299 * c[..., 0] + 0.587 * c[..., 1] + 0.114 * c[..., 2]
        take = lu < bestl
        bestl = np.where(take, lu, bestl)
        best = np.where(take[..., None], c, best)
    line = np.where((bestl < 150)[..., None], best,
                    np.array(LINE_FALLBACK, np.float32))

    # ── 6. 合成：只改 RGB ───────────────────────────────────────────
    before = H[..., :3].copy()
    w = cov[..., None]
    H[..., :3] = H[..., :3] * (1 - w) + line * w
    changed = int((np.abs(H[..., :3] - before).max(axis=2) > 3).sum())
    out = np.dstack([np.clip(H[..., :3], 0, 255), alpha]).astype(np.uint8)
    Image.fromarray(out, "RGBA").save(head_path)
    lum_before = float((0.299 * before[..., 0] + 0.587 * before[..., 1]
                        + 0.114 * before[..., 2])[cov > 0.5].mean()) if (cov > 0.5).any() else 0
    lum_after = float((0.299 * out[..., 0] + 0.587 * out[..., 1]
                       + 0.114 * out[..., 2])[cov > 0.5].mean()) if (cov > 0.5).any() else 0
    print(f"[脸轮廓] seg_head.png 补回轮廓线 {changed} 像素"
          f"（线上亮度 {lum_before:.0f} → {lum_after:.0f}，线色样本 "
          f"{tuple(int(v) for v in line[cov > 0.5].mean(axis=0))}）"
          if (cov > 0.5).any() else f"[脸轮廓] 改了 {changed} 像素")

    if args.debug:
        Z = 4
        box = (0, int(max(0, eyeline_local - 10)), hw, hh)
        a = Image.fromarray(np.dstack([before, alpha]).astype(np.uint8), "RGBA").crop(box)
        b = Image.fromarray(out, "RGBA").crop(box)
        panels = []
        for p in (a, b):
            q = p.resize((p.width * Z, p.height * Z), Image.NEAREST)
            bg = Image.new("RGB", q.size, (255, 255, 255))
            bg.paste(q, (0, 0), q)
            panels.append(bg)
        cv = Image.new("RGB", (panels[0].width * 2 + 8, panels[0].height), (40, 40, 40))
        cv.paste(panels[0], (0, 0))
        cv.paste(panels[1], (panels[0].width + 8, 0))
        os.makedirs(os.path.dirname(args.debug) or ".", exist_ok=True)
        cv.save(args.debug)
        print(f"[脸轮廓] 对比图 {args.debug}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
