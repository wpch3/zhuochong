#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""make_eye_wide_parts.py —— Chibi 瞪大眼差分（ParamEyeL/RWide）

以 Chibi 原画的 eye socket、独立 iris ball 和 make_eyeline_parts 生成的
upper-lash-only 贴图构造 wide 候选：只轻微扩张外露眼白翼/上睫毛，不拉伸虹膜，
也不使用带脸/头发 halo 的矩形裁切。AI 的 face_eyeswide 曾生成错比例白块，故不照搬。

当前倍率 KX=1.04、KY=1.10 只是待验收近似，不等价于 Live2D 网格形变；真实引擎
截图与 full-chain QA 通过前不得把该候选视为完成。

用法：
  ~/.imgenv/bin/python tools/make_eye_wide_parts.py --character xiaoxun --form chibi
"""
from __future__ import annotations

import argparse
import json
import os

import numpy as np
from PIL import Image

# 候选采用轻量各向异性近似，不代表已经通过真实 wide 表情验收。
KX = 1.04
KY = 1.10
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
    el_path = os.path.join(sp, "eyeline_parts.json")
    eyelines = ({x["side"]: x for x in json.load(open(el_path, encoding="utf-8")).get("eyes", [])}
                if os.path.exists(el_path) else {})

    out = {"source": "eye_<side>_socket + eye_<side>_lash_up（无裁切脸块）各向异性放大",
           "register": {"scale": [KX, KY], "ncc": None, "tx": 0.0, "ty": 0.0,
                        "seeded_by": "base_affine"},
           "source_note": "原画眼件仿射撑开（Live2D ParamEyeLWide 的贴图等价做法）",
           "eyes": []}

    for side in ("l", "r"):
        e = eyes[side]
        px, py = e["patch_pos"]
        base = np.array(Image.open(os.path.join(sp, f"eye_{side}_base.png")).convert("RGBA"))
        socket = np.array(Image.open(os.path.join(sp, e["socket"])).convert("RGBA"))
        bh, bw = base.shape[:2]
        if socket.shape[:2] != (bh, bw):
            raise SystemExit(f"[wide] {side} socket/base 尺寸不一致")
        socket_a = socket[..., 3].astype(np.float32) / 255.0

        # The normal clean sclera base remains visible in Chibi wide mode. This
        # overlay contains only the *incremental* sclera outside that base silhouette
        # plus a mildly raised upper lash; drawing a full white ring around a fixed
        # iris was the visible defect in v3/v4.
        lash_file = eyelines.get(side, {}).get("lash_file") or f"eye_{side}_lash.png"
        lash = np.array(Image.open(os.path.join(sp, lash_file)).convert("RGBA"))
        if lash.shape[:2] != (bh, bw):
            raise SystemExit(f"[wide] {side} upper-lash/base 尺寸不一致")
        la = lash[..., 3].astype(np.float32) / 255.0

        gx0, gy0 = e["ball_pos"]
        gw, gh = e["ball_size"]
        cxb, cyb = gx0 + gw / 2.0, gy0 + gh / 2.0
        cxl, cyl = cxb - px, cyb - py
        s_base_rgb, s_base_a = _premul_scale(base[..., :3].astype(np.float32), socket_a, KX, KY)
        s_lash_rgb, s_lash_a = _premul_scale(lash[..., :3].astype(np.float32), la, KX, KY)
        sh, sw = s_base_a.shape
        ax0 = int(round(cxb - cxl * KX))
        ay0 = int(round(cyb - cyl * KY))
        ax0 = max(0, min(W - sw, ax0))
        ay0 = max(0, min(H - sh, ay0))
        ax1, ay1 = ax0 + sw, ay0 + sh

        # Compare the expanded socket against the original base in the same body
        # coordinates. Only positive difference is painted; the normal base supplies
        # all unchanged sclera, so the iris has no white halo/ring overlay.
        original_socket = np.zeros((H, W), np.float32)
        sx1, sy1 = min(W, px + bw), min(H, py + bh)
        if px < sx1 and py < sy1:
            original_socket[py:sy1, px:sx1] = socket_a[:sy1-py, :sx1-px]
        orig_crop = original_socket[ay0:ay1, ax0:ax1]
        extra_a = np.clip(s_base_a - orig_crop, 0.0, 1.0)
        # Widening should reveal a modest upper sclera crescent, not a white ring
        # beneath and around the iris. Keep only the upper half of the incremental
        # expansion; the unchanged base already supplies the lower/side eye shape.
        body_y = np.arange(sh, dtype=np.float32)[:, None] + ay0
        upper_gate = np.clip((cyb + 4.0 - body_y) / 8.0, 0.0, 1.0)
        extra_a *= upper_gate

        # Upper lash is a full replacement for the normal lash (hidden by the rig in
        # wide mode); composite it over the incremental sclera extension.
        combined_a = extra_a + s_lash_a * (1.0 - extra_a)
        premul = (s_base_rgb * extra_a[..., None]
                  + s_lash_rgb * (s_lash_a * (1.0 - extra_a))[..., None])
        combined_rgb = np.divide(premul, np.maximum(combined_a[..., None], 1e-4),
                                 out=np.zeros_like(premul), where=combined_a[..., None] > 1e-4)
        bk = bkeep[ay0:ay1, ax0:ax1]
        alpha2 = combined_a * bk.astype(np.float32)

        if int((alpha2 > 0.9).sum()) < 120:
            raise SystemExit(f"[wide] {side} 扩展/睫毛补片有效像素不足，拒绝写出")
        img = np.zeros((sh, sw, 4), np.uint8)
        img[..., :3] = np.clip(combined_rgb, 0, 255).round().astype(np.uint8)
        img[..., 3] = (alpha2 * 255).round().astype(np.uint8)
        rr, gg, bb, aa = (img[..., i].astype(int) for i in range(4))
        keyed = ((aa > 40) & (gg - np.maximum(rr, bb) > 60)) | (
            (aa > 40) & (rr - gg > 60) & (bb - gg > 60) & (rr > 150) & (bb > 150))
        img[keyed, :3] = 0
        img[keyed, 3] = 0
        fn = f"eye_{side}_wide.png"
        Image.fromarray(img, "RGBA").save(os.path.join(sp, fn))

        edge = (alpha2 > 0.05) & (alpha2 < 0.95) & bk
        tgt = brgb[ay0:ay1, ax0:ax1]
        seam = float(np.abs(combined_rgb - tgt)[edge].mean()) if edge.sum() else 0.0
        upper_opaque = int((extra_a > 0.9).sum())
        lash_opaque = int((s_lash_a > 0.9).sum())
        out["eyes"].append({
            "side": side, "file": fn, "pos": [ax0, ay0], "size": [sw, sh],
            "gain": [1.0, 1.0, 1.0], "offset": [0.0, 0.0, 0.0],
            "checks": {"added_sclera_px": upper_opaque, "upper_lash_px": lash_opaque,
                       "seam_mean_abs": round(seam, 2), "keyed_px_removed": int(keyed.sum())},
        })
        print(f"瞪大眼 {side}: {sw}x{sh} @ 身体({ax0},{ay0})  "
              f"新增眼白 {upper_opaque}px / 上睫毛 {lash_opaque}px  接缝 {seam:.1f}")

    with open(os.path.join(sp, "eye_wide_parts.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print("[wide] → sprites/eye_wide_parts.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
