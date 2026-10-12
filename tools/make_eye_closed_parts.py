#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""make_eye_closed_parts.py - 用 AI 重绘的「闭眼脸」切出真·闭眼零件（G4r / D19）。

为什么要重做：
  第一版 make_eyelid_parts.py 的眼皮是**从眼睛上方那块皮肤切下来的几何贴片**，
  靠往下滑盖住眼睛。问题是：原画里根本没有"闭着的眼睛"这张画——闭到底时屏幕上
  只剩一块比周围亮的肤色饼 + 一条被眼眶遮罩裁短的睫毛线，用户实拍反馈
  「开心的闭眼错位」。按 D19，原画没有的像素必须 AI 生图重绘。

做法（和张嘴/刘海/眉毛同一条流水线）：
  1. design/redraw/face_eyesclosed.png = 同一张脸、眼睛闭上的 AI 重绘（洋红底）；
  2. 配准：闭眼图里没有虹膜可用，改用**肤色区域的外接框**定初值，
     再在"挖掉眼睛那条带"的脸部做 NCC 网格微调（缩放 + 平移）；
  3. 每只眼睛切一块"盖得住原画睁眼"的补片（眼眶外扩 + 羽化），
     逐通道最小二乘把补片的肤色配到本体上，避免贴上去有色阶；
  4. rig 里用 tags:["eye_closed"]（引擎已有：opacity *= blink），
     和睁眼件交叉淡化 —— 这就是 Live2D 的 ParamEyeLOpen 在贴图版里的等价做法。

输出：sprites/eye_l_closed.png、eye_r_closed.png、eye_closed_parts.json

用法：
  ~/.imgenv/bin/python tools/make_eye_closed_parts.py --character xiaoxun --form teen
"""
from __future__ import annotations
import argparse, json, os

import numpy as np
from PIL import Image

SKIN = (252, 228, 216)
MARGIN = 9          # 眼眶外扩多少像素（要盖住原画的上睫毛和眼角）
FEATHER = 7         # 边缘羽化宽度（软椭圆）


def skin_mask(rgb, keep):
    """暖色皮肤：白夹克 R≈G≈B、头发偏蓝，都要排掉，否则外接框会变成整张图。"""
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    return keep & (r > 205) & ((r - b) > 18) & ((r - b) < 70) & (g < r) & (g > r - 45)


def warp_box(rd_rgba, s, tx, ty, box):
    """把重绘图按 (缩放 s, 平移 tx,ty) 采样到 body 空间的 box=(x0,y0,x1,y1)。
    只算这一块，所以可以在网格搜索里跑几千次。"""
    x0, y0, x1, y1 = box
    im = Image.fromarray(rd_rgba, "RGBA")
    # 输出 (u,v) → 输入：x_in = (u + x0)/s + tx
    m = (1.0 / s, 0.0, x0 / s + tx, 0.0, 1.0 / s, y0 / s + ty)
    out = im.transform((x1 - x0, y1 - y0), Image.AFFINE, m, resample=Image.BICUBIC)
    a = np.array(out)
    return a[..., :3].astype(np.float32), a[..., 3]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--character", required=True)
    ap.add_argument("--form", required=True)
    ap.add_argument("--root", default=".")
    args = ap.parse_args()
    base = os.path.join(args.root, "characters", args.character, "forms", args.form)
    sp = os.path.join(base, "sprites")
    redraw = os.path.join(args.root, "characters", args.character,
                          "design", "redraw", "face_eyesclosed.png")
    if not os.path.exists(redraw):
        raise SystemExit(f"[eye_closed] 缺少 AI 重绘底图：{redraw}（D19：原画没有闭眼，必须重绘）")

    body = np.array(Image.open(os.path.join(sp, "body_full.png")).convert("RGBA"))
    H, W = body.shape[:2]
    brgb = body[..., :3].astype(np.float32)
    bkeep = body[..., 3] > 128

    rd = np.array(Image.open(redraw).convert("RGBA"))
    rrgb = rd[..., :3].astype(np.int32)
    r_, g_, b_ = rrgb[..., 0], rrgb[..., 1], rrgb[..., 2]
    magenta = (np.minimum(r_, b_) - g_ > 60) & (r_ > 140) & (b_ > 140)
    rkeep = (rd[..., 3] > 128) & ~magenta
    rd_rgba = np.dstack([rd[..., :3], (rkeep * 255).astype(np.uint8)]).astype(np.uint8)

    eyes = {e["side"]: e for e in
            json.load(open(os.path.join(sp, "eye_parts.json"), encoding="utf-8"))["eyes"]}

    # ---- 1. 初值：两张图的"脸"（肤色块）外接框 ----
    bk_head = bkeep.copy(); bk_head[300:, :] = False      # 只要头那一段（手和腿也是皮肤）
    bs = skin_mask(brgb.astype(np.int32), bk_head)
    rs = skin_mask(rrgb, rkeep)
    def bbox(m):
        ys, xs = np.nonzero(m)
        return xs.min(), ys.min(), xs.max(), ys.max()
    bx0, by0, bx1, by1 = bbox(bs)
    rx0, ry0, rx1, ry1 = bbox(rs)
    s0 = (bx1 - bx0) / float(rx1 - rx0)
    # 对齐脸的中心
    bcx, bcy = (bx0 + bx1) / 2.0, (by0 + by1) / 2.0
    rcx, rcy = (rx0 + rx1) / 2.0, (ry0 + ry1) / 2.0

    # ---- 2. NCC 网格微调（脸部，挖掉眼睛那条带）----
    el, er = eyes["l"], eyes["r"]
    eye_y = (el["patch_pos"][1] + er["patch_pos"][1]) / 2.0
    fx0 = int(min(el["patch_pos"][0], er["patch_pos"][0]) - 20)
    fx1 = int(max(el["patch_pos"][0] + el["patch_size"][0],
                  er["patch_pos"][0] + er["patch_size"][0]) + 20)
    fy0, fy1 = int(eye_y - 70), int(eye_y + 120)
    fx0, fy0 = max(0, fx0), max(0, fy0)
    fx1, fy1 = min(W, fx1), min(H, fy1)
    ref = brgb[fy0:fy1, fx0:fx1].mean(axis=2)
    refm = bkeep[fy0:fy1, fx0:fx1].copy()
    refm[max(0, int(eye_y - 20) - fy0):int(eye_y + 75) - fy0, :] = False   # 挖掉眼睛带

    # 初值只是个量级参考（两张图的脸框不完全等价），所以缩放要大范围扫
    best = None
    for s in np.linspace(s0 * 0.65, s0 * 1.30, 17):
        for dy in range(-24, 25, 3):
            for dx in range(-24, 25, 3):
                tx = rcx - (bcx + dx) / s
                ty = rcy - (bcy + dy) / s
                cur, ca = warp_box(rd_rgba, s, tx, ty, (fx0, fy0, fx1, fy1))
                m = refm & (ca > 128)
                if m.sum() < 800:
                    continue
                cm = cur.mean(axis=2)
                a = ref[m] - ref[m].mean(); bq = cm[m] - cm[m].mean()
                ncc = float((a * bq).sum() / (np.sqrt((a * a).sum() * (bq * bq).sum()) + 1e-6))
                if best is None or ncc > best[0]:
                    best = (ncc, s, tx, ty)
    ncc, s, tx, ty = best
    # 再细一轮（步长 1px，缩放 ±1%）
    bs_, btx, bty = s, tx, ty
    for ds in np.linspace(-0.01, 0.01, 5):
        ss = bs_ * (1 + ds)
        for dy in np.arange(-2, 2.01, 1.0):
            for dx in np.arange(-2, 2.01, 1.0):
                txx = rcx - (bcx + dx) / ss
                tyy = rcy - (bcy + dy) / ss
                cur, ca = warp_box(rd_rgba, ss, txx, tyy, (fx0, fy0, fx1, fy1))
                m = refm & (ca > 128)
                if m.sum() < 800:
                    continue
                cm = cur.mean(axis=2)
                a = ref[m] - ref[m].mean(); bq = cm[m] - cm[m].mean()
                v = float((a * bq).sum() / (np.sqrt((a * a).sum() * (bq * bq).sum()) + 1e-6))
                if v > ncc:
                    ncc, s, tx, ty = v, ss, txx, tyy

    out = {"source": "design/redraw/face_eyesclosed.png（AI 重绘闭眼脸）",
           "register": {"scale": round(s, 4), "ncc": round(ncc, 4)}, "eyes": []}

    for side in ("l", "r"):
        e = eyes[side]
        # ---- 补片范围 = 眼球框外扩 MARGIN（眼球框来自 eye_parts.json，身体坐标）----
        # 不能拿"窗口里的深色像素"定框：那个窗口里还有眉毛和压过来的发丝，
        # 框会一路长到把两只眼连起来（实测 dark bbox 117x68 = 整个窗口）。
        gx0, gy0 = e["ball_pos"]
        gw, gh = e["ball_size"]
        ax0 = max(0, gx0 - MARGIN - 4); ax1 = min(W, gx0 + gw + MARGIN + 4)
        ay0 = max(0, gy0 - MARGIN - 4); ay1 = min(H, gy0 + gh + MARGIN + 4)
        box = (ax0, ay0, ax1, ay1)
        # 要盖住的"原画眼睛" = 眼球框再放一点（睫毛和眼角），不含眉毛/头发
        eye_zone = np.zeros((ay1 - ay0, ax1 - ax0), bool)
        eye_zone[max(0, gy0 - 6 - ay0):gy0 + gh + 6 - ay0,
                 max(0, gx0 - 6 - ax0):gx0 + gw + 6 - ax0] = True
        patch, pa = warp_box(rd_rgba, s, tx, ty, box)
        if (pa > 128).mean() < 0.9:
            raise SystemExit(f"[eye_closed] {side} 眼补片在重绘图里没盖满（配准失败？）")
        hh, ww = patch.shape[:2]
        tgt = brgb[ay0:ay1, ax0:ax1]
        bk_box = bkeep[ay0:ay1, ax0:ax1]

        # ---- 逐通道最小二乘配色：只用"两边都是皮肤"的像素，别把头发和睫毛算进去 ----
        both_skin = (skin_mask(patch.astype(np.int32), pa > 128)
                     & skin_mask(tgt.astype(np.int32), bk_box))
        # ⚠️ 皮肤像素的取值范围很窄（都在 240 上下），直接最小二乘解 gain+offset 是**病态**的：
        # 实测解出 gain=0.15 / offset=214，皮肤是对上了，但睫毛那种暗像素被映射成亮红色
        # （40*0.15+214=246，而绿通道只到 123）——截图里那条"红杠"就是这么来的。
        # 正确做法（cel 风格专用）：
        #   · 只解**平移**（gain 固定 1），把两张图的肤色均值对齐；
        #   · 而且只把这个平移**作用在肤色像素上**：睫毛/线稿这种暗像素原样保留
        #     （AI 出图时 prompt 已经锁死了线稿色，本来就是对的）。
        gain = [1.0, 1.0, 1.0]; off = [0.0, 0.0, 0.0]
        if both_skin.sum() > 60:
            for c in range(3):
                X = patch[..., c][both_skin]; Y = tgt[..., c][both_skin]
                off[c] = float(np.clip(Y.mean() - X.mean(), -45, 45))
        lum_p = patch.mean(axis=2)
        w = np.clip((lum_p - 130.0) / 50.0, 0.0, 1.0)[..., None]   # 亮=皮肤才改色
        patch = patch + w * np.array(off, np.float32)[None, None, :]
        patch = np.clip(patch, 0, 255)

        # ---- 羽化成一个软椭圆：方补丁的直角边在脸上一眼就看得出来 ----
        yy = np.arange(hh)[:, None].astype(np.float32)
        xx = np.arange(ww)[None, :].astype(np.float32)
        cy, cx = (hh - 1) / 2.0, (ww - 1) / 2.0
        rad = np.sqrt(((xx - cx) / (ww / 2.0)) ** 2 + ((yy - cy) / (hh / 2.0)) ** 2)
        k = FEATHER / max(ww, hh) * 2.0
        alpha = np.clip((1.0 - rad) / max(k, 1e-3) + 0.35, 0, 1)
        alpha *= (pa > 128)
        alpha *= bk_box                       # 不要糊到脸外面去

        # 覆盖检查：原画的深色眼睛像素必须被 alpha≥0.9 的部分盖住
        dark = (tgt.mean(axis=2) < 165) & bk_box & eye_zone
        for _ in range(6):
            cover = float((alpha[dark] > 0.9).mean()) if dark.sum() else 1.0
            if cover > 0.995:
                break
            alpha = np.clip(alpha * 1.25, 0, 1) * (pa > 128) * bk_box   # 把不透明区域撑大一点
        cover = float((alpha[dark] > 0.9).mean()) if dark.sum() else 1.0

        img = np.zeros((hh, ww, 4), np.uint8)
        img[..., :3] = patch.round().astype(np.uint8)
        img[..., 3] = (alpha * 255).round().astype(np.uint8)
        fn = f"eye_{side}_closed.png"
        Image.fromarray(img, "RGBA").save(os.path.join(sp, fn))

        edge = (alpha > 0.05) & (alpha < 0.95) & both_skin
        seam = float(np.abs(patch - tgt)[edge].mean()) if edge.sum() else 0.0
        out["eyes"].append({
            "side": side, "file": fn, "pos": [ax0, ay0], "size": [ww, hh],
            "gain": [round(v, 4) for v in gain], "offset": [round(v, 2) for v in off],
            "checks": {"cover_ratio": round(cover, 4), "seam_mean_abs": round(seam, 2),
                       "opaque_px": int((alpha > 0.9).sum())},
        })
        print(f"闭眼 {side}: {ww}x{hh} @ 身体({ax0},{ay0})  盖住原画眼睛 {cover*100:.1f}%  "
              f"接缝色差 {seam:.1f}")

    json.dump(out, open(os.path.join(sp, "eye_closed_parts.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    print(f"配准 scale={s:.4f} NCC={ncc:.3f} → sprites/eye_closed_parts.json")


if __name__ == "__main__":
    main()
