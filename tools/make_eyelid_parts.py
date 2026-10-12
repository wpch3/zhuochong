#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""make_eyelid_parts.py - 切出上眼睑，让眨眼变成「眼皮真的盖下来」。

在这之前，眨眼是「睁眼图淡出 + 闭眼图淡入」——整只眼睛在那儿忽隐忽现，
放慢了看很假。Live2D 的做法是：眼眶当遮罩，上眼皮是一块能往下滑的皮肤，
参数 0 时藏在眼眶上面，参数 1 时正好滑满整个眼眶。

这件零件怎么来：
  **不用 AI 重绘** —— 眼皮要盖住的是眼眶里面，而眼眶里本来就有眼白/眼球
  （都是已经补全的独立零件），没有「原画缺像素」的问题。眼皮自己那块皮肤，
  取的是眼睛正上方（眉毛挪走之后露出来的那片）真实皮肤的逐列中位色，
  所以颜色和脸上完全连得上。

  睫毛不另画：原来的 eye_?_lash（眼线+睫毛）也打上 eyelid 标签跟着一起下滑，
  闭眼时它自然落到下眼睑位置，变成那条闭眼的线。

输入：sprites/seg_head.png、sprites/eye_parts.json、sprites/eye_?_socket.png
输出：sprites/eye_l_lid.png、eye_r_lid.png、body_parts.json 里登记两件
      （带 eyelid_travel = 行程像素）

用法：
  ~/.imgenv/bin/python tools/make_eyelid_parts.py --character xiaoxun --form teen
"""
from __future__ import annotations
import argparse, json, os

import numpy as np
from PIL import Image

PAD = 5          # 眼睑比眼眶宽出来的边（防止眼角露缝）
LINE_RGB = (0x2C, 0x29, 0x39)   # 闭眼线的颜色 = 色卡里的"眼线"
BOTTOM_GAP = 1   # 静止时眼睑底边离眼眶上沿留 1px
OVERSHOOT = 3    # 闭到底时再多盖 3px（眼眶下沿要盖严）


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--character", required=True)
    ap.add_argument("--form", required=True)
    ap.add_argument("--root", default=".")
    args = ap.parse_args()

    base = os.path.join(args.root, "characters", args.character, "forms", args.form)
    sp = os.path.join(base, "sprites")
    eyes = json.load(open(os.path.join(sp, "eye_parts.json"), encoding="utf-8"))
    bp_path = os.path.join(sp, "body_parts.json")
    bp = json.load(open(bp_path, encoding="utf-8"))
    head_pos = next(p["pos"] for p in bp["parts"] if p["id"] == "seg_head")
    head = np.array(Image.open(os.path.join(sp, "seg_head.png")).convert("RGBA")).astype(int)
    hrgb, hal = head[..., :3], head[..., 3]
    HH, HW = hal.shape
    skin_m = (hal > 100) & (hrgb[..., 0] > 200) & (hrgb[..., 0] > hrgb[..., 2] + 18)
    fallback = np.median(hrgb[skin_m], axis=0) if skin_m.any() else np.array([252, 228, 216])

    out, report = [], []
    for e in eyes["eyes"]:
        side = e["side"]
        px, py = e["patch_pos"]                       # 眼部贴片在身体坐标里的位置
        hx, hy = head_pos
        sock = np.array(Image.open(os.path.join(sp, e["socket"])).convert("RGBA"))[..., 3]
        A = sock > 100
        ys, xs = np.nonzero(A)
        ax0, ax1, ay0, ay1 = int(xs.min()), int(xs.max()), int(ys.min()), int(ys.max())
        ap_w, ap_h = ax1 - ax0 + 1, ay1 - ay0 + 1     # 眼眶（可见开口）的尺寸

        # 眼皮就按**眼眶**来裁，外面交给眼眶遮罩裁切：
        #   试过让眼皮盖住整条眼线（不挂遮罩、把宽度放到眼线那么宽），
        #   结果一张 54x60 的皮肤矩形压在脸上，边缘和脸的渐变对不齐，闭眼时
        #   额头上会出现一块方的浅色补丁。挂遮罩的版本不会溢出，1 倍看着自然。
        PADX = PAD
        x0 = ax0 - PADX
        lid_w = ap_w + 2 * PADX
        travel = ap_h + BOTTOM_GAP + OVERSHOOT
        lid_h = travel + 6
        liner_top = ay0
        bx = px + x0
        by = py + ay0 - BOTTOM_GAP - lid_h

        # 逐列取皮肤色：取眼线上沿再往上 4..24px 的那条带（眉毛拆走后就是干净皮肤）
        samp_y1 = max(0, py + liner_top - hy - 4)
        samp_y0 = max(0, samp_y1 - 20)
        # 下眼睑那一侧也取一条：眼眶下沿再往下 2..10px。
        # 只取上面那条的话，眼皮是**额头**的亮肤色，闭眼时脸上会多出一块比周围亮
        # 十来个灰阶的方块（实测眼皮 253,239,226 vs 眼周 248,229,220）。
        samp2_y0 = min(HH - 1, py + ay1 - hy + 2)
        samp2_y1 = min(HH, samp2_y0 + 8)
        cols, cols_lo = [], []
        for i in range(lid_w):
            cx = bx + i - hx
            col = fallback
            if 0 <= cx < HW and samp_y1 > samp_y0:
                m = skin_m[samp_y0:samp_y1, cx]
                if m.sum() >= 3:
                    col = np.median(hrgb[samp_y0:samp_y1, cx][m], axis=0)
            lo = col * 0.97
            if 0 <= cx < HW and samp2_y1 > samp2_y0:
                m2 = skin_m[samp2_y0:samp2_y1, cx]
                if m2.sum() >= 3:
                    lo = np.median(hrgb[samp2_y0:samp2_y1, cx][m2], axis=0)
            cols.append(col)
            cols_lo.append(lo)
        # 上下两色按行线性过渡 = 眼皮自带一点明暗，贴上去才像脸的一部分
        top = np.array(cols, float)[None, :, :]
        low = np.array(cols_lo, float)[None, :, :]
        t = (np.arange(lid_h, dtype=float) / max(lid_h - 1, 1))[:, None, None]
        rgba = np.zeros((lid_h, lid_w, 4), np.uint8)
        rgba[..., :3] = np.clip(top * (1 - t) + low * t, 0, 255).round().astype(np.uint8)
        rgba[..., 3] = 255

        # 下沿 = 眼眶的下沿曲线（逐列），所以闭到底时正好贴着下眼睑，不会糊到脸上。
        # 闭眼线就画在下沿上面两行 —— 闭眼时看见的那条线。
        bot = np.full(lid_w, -1, int)
        for i in range(lid_w):
            cx = x0 + i
            if 0 <= cx < A.shape[1]:
                rows = np.nonzero(A[:, cx])[0]
                if len(rows):
                    bot[i] = lid_h - 1 - (ay1 - int(rows.max()))
        known = np.nonzero(bot >= 0)[0]
        if len(known):
            for i in range(lid_w):
                if bot[i] < 0:
                    # 眼眶之外的列（眼线尖角那几列）：按最近一列，再抬 2 行收个角
                    bot[i] = bot[known[np.argmin(np.abs(known - i))]] - 2
            line = np.array(LINE_RGB, float)
            for i in range(lid_w):
                yb = int(np.clip(bot[i], 2, lid_h - 1))
                rgba[yb + 1:, i, 3] = 0
                if yb + 1 < lid_h:
                    rgba[yb + 1, i, 3] = 110
                # 闭眼线要画在"闭到底时正好落在眼眶下沿"的那几行，也就是
                # 要把 OVERSHOOT 那几行让出来 —— 不然线落到眼眶外面，
                # 被眼眶遮罩一刀切掉，闭眼时只剩一块白板，看不到那条线
                # （实测：lid 自身 R=76 的线在渲染帧里完全不见）。
                yl = int(np.clip(yb - OVERSHOOT, 2, lid_h - 1))
                for dy, w in ((0, 0.85), (-1, 0.45), (-2, 0.15)):
                    y = yl + dy
                    if 0 <= y < lid_h:
                        base_c = rgba[y, i, :3].astype(float)
                        rgba[y, i, :3] = (base_c * (1 - w) + line * w).round().astype(np.uint8)

        name = f"eye_{side}_lid.png"
        Image.fromarray(rgba).save(os.path.join(sp, name))
        out.append((side, name, bx, by, lid_w, lid_h, travel))
        report.append({"side": side, "file": name, "pos": [bx, by],
                       "size": [lid_w, lid_h], "travel": travel,
                       "aperture": [ap_w, ap_h], "liner_top": int(liner_top)})
        print(f"眼睑 {side}: {lid_w}x{lid_h} @ 身体({bx},{by})  行程 {travel}px（眼眶 {ap_w}x{ap_h}）")

    # 注意：**不往 body_parts.json 里登记**。
    # 身体分段那张表里的每一件 make_rig 都会原样摆一遍，眼睑要是也登记进去，
    # 就会和眼部那段生成的同名零件撞车（实测出现两个 eye_l_lid，一个还带 body 标签）。
    # 眼睑只写自己的清单，由 make_rig 的眼部分支去读。
    bp["parts"] = [p for p in bp["parts"] if not p["id"].endswith("_lid")]
    note = "上眼睑已拆件，眨眼改为眼皮下滑（make_eyelid_parts.py）"
    if note not in bp.setdefault("patches", []):
        bp["patches"].append(note)
    json.dump(bp, open(bp_path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    json.dump({"lids": report}, open(os.path.join(sp, "eyelid_parts.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print("写出 sprites/eye_l_lid.png、eye_r_lid.png、eyelid_parts.json")


if __name__ == "__main__":
    main()
