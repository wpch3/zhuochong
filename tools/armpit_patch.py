#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""armpit_patch.py — repair only hidden axilla pixels without extending the torso silhouette.

The previous side-extrusion fill created broad gray rectangles when an arm lifted.
For forms with a registered no-arms redraw, that redraw's alpha is now authoritative:
copy its exact opaque pixels inside the hidden-arm zone and leave the rest transparent.
This preserves the natural cardigan outline and avoids inventing a rectangular side panel.
Forms without a redraw retain the legacy fallback for now.

幂等：原件备份进 sprites/_orig/，签名写进 body_parts.json 的 armpit_patch 段。
用法：python tools/armpit_patch.py --character xiaoxun --form teen [--force]
"""
import argparse
import io
import json
import os

import numpy as np
from PIL import Image, ImageFilter


def load(path):
    return Image.open(path).convert("RGBA")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--character", required=True)
    ap.add_argument("--form", required=True)
    ap.add_argument("--radius", type=float, default=118.0,
                    help="从肩枢轴算起，多大范围内才补（1× 像素）")
    ap.add_argument("--darken", type=float, default=0.90,
                    help="补料压暗系数（腋窝是阴影区）")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--repair", action="store_true",
                    help="就地修现有 seg_torso 里补成雾的腋下（不复用 _orig 备份，"
                         "因为备份是「带手臂」的上游版本）")
    a = ap.parse_args()

    base = os.path.join("characters", a.character, "forms", a.form)
    sprites = os.path.join(base, "sprites")
    bpj = os.path.join(sprites, "body_parts.json")
    apj = os.path.join(sprites, "arm_parts.json")
    if not (os.path.exists(bpj) and os.path.exists(apj)):
        print("[armpit] 缺 body_parts.json / arm_parts.json，跳过")
        return 0
    with io.open(bpj, encoding="utf-8") as f:
        BJ = json.load(f)
    with io.open(apj, encoding="utf-8") as f:
        AJ = json.load(f)
    BP = {p["id"]: p for p in BJ["parts"]}
    AP = {p["id"]: p for p in AJ["parts"]}
    if "seg_torso" not in BP:
        print("[armpit] 没有 seg_torso，跳过")
        return 0

    # The old broad fill extended the torso side silhouette into the old arm's
    # bounding box, creating two conspicuous gray rectangles when the arms moved.
    # Use the registered no-arms redraw as the silhouette authority instead:
    # pixels outside its opaque garment edge stay transparent; only real redraw
    # pixels can be restored. This keeps the armpit from becoming a rectangular
    # paint patch and avoids inventing a side contour the source art never had.
    redraw_rel = AJ.get("redraw", "")
    redraw_candidates = ([os.path.join(base, redraw_rel),
                         os.path.join("characters", a.character, redraw_rel)]
                        if redraw_rel else [])
    redraw_path = next((p for p in redraw_candidates if os.path.isfile(p)), "")
    redraw_full = load(redraw_path) if redraw_path else None

    sig = {"radius": a.radius, "darken": a.darken, "v": 3,
           "silhouette": "redraw-alpha-transparent-outside"}
    if (BJ.get("armpit_patch", {}).get("sig") == sig and not a.force
            and not a.repair):
        print("[armpit] 已补过腋下，跳过（--force 强制）")
        return 0

    orig_dir = os.path.join(sprites, "_orig")
    if not os.path.isdir(orig_dir):
        os.makedirs(orig_dir)

    joints = AJ.get("shoulder_joint", {})
    stats = {}
    for s in (1, 2):
        suf = "" if s == 1 else "@2x"
        f_t = os.path.join(sprites, "seg_torso%s.png" % suf)
        if not os.path.exists(f_t):
            continue
        bak = os.path.join(orig_dir, "seg_torso%s.png" % suf)
        if not os.path.exists(bak):
            load(f_t).save(bak)
        # --repair：拿**当前文件**当底，把已经补成雾的那块就地改成实体
        tim = load(f_t if a.repair else bak)
        ta = np.array(tim).astype(np.int16)
        tpos = BP["seg_torso"]["pos"]
        H, W = ta.shape[:2]
        torso = ta[:, :, 3] > 16
        # 算 zone 用的「已经是躯干」判据：--repair 时不能把雾当成躯干，
        # 否则雾自己占住了补料区，等于什么都不补。
        torso_ref = (ta[:, :, 3] >= 200) if a.repair else torso

        # 休止姿势下手臂占的地盘（换算到躯干件的局部坐标）
        armzone = np.zeros((H, W), bool)
        for aid in ("arm_l_root", "arm_l_upper", "arm_l_cap", "arm_l_fore",
                    "arm_r_root", "arm_r_upper", "arm_r_cap", "arm_r_fore"):
            if aid not in AP:
                continue
            f_a = os.path.join(base, AP[aid]["file"].replace(".png", suf + ".png"))
            if not os.path.exists(f_a):
                continue
            aa = np.array(load(f_a))[:, :, 3] > 16
            ax = int(round((AP[aid]["pos"][0] - tpos[0]) * s))
            ay = int(round((AP[aid]["pos"][1] - tpos[1]) * s))
            x0, y0 = max(0, ax), max(0, ay)
            x1, y1 = min(W, ax + aa.shape[1]), min(H, ay + aa.shape[0])
            if x1 <= x0 or y1 <= y0:
                continue
            armzone[y0:y1, x0:x1] |= aa[y0 - ay:y1 - ay, x0 - ax:x1 - ax]

        # 只在肩枢轴附近补
        yy, xx = np.mgrid[0:H, 0:W]
        near = np.zeros((H, W), bool)
        for side in ("l", "r"):
            if side not in joints:
                continue
            jx = (joints[side][0] - tpos[0]) * s
            jy = (joints[side][1] - tpos[1]) * s
            near |= ((xx - jx) ** 2 + (yy - jy) ** 2) <= (a.radius * s) ** 2
        zone = armzone & ~torso_ref & near
        if zone.sum() == 0:
            print("[armpit] %s 没有要补的地方" % suf)
            continue

        if redraw_full is not None:
            # The redraw lives in full-canvas coordinates; match the current
            # 1x/2x sprite resolution, then crop by the measured torso origin.
            if s == 1:
                redraw_scaled = redraw_full
            else:
                redraw_scaled = redraw_full.resize(
                    (redraw_full.width * s, redraw_full.height * s),
                    Image.Resampling.LANCZOS)
            rx, ry = int(tpos[0] * s), int(tpos[1] * s)
            redraw_crop = np.array(redraw_scaled.crop((rx, ry, rx + W, ry + H)))
            if redraw_crop.shape[:2] != (H, W):
                raise SystemExit("[armpit] 无臂重绘图与 seg_torso 裁框不匹配")
            # The source redraw was keyed on magenta. Respect its alpha edge,
            # and reject any residual key fringe rather than turning it opaque.
            rr = redraw_crop[..., :3].astype(np.int16)
            purple = (np.minimum(rr[..., 0], rr[..., 2]) - rr[..., 1]) > 25
            redraw_valid = (redraw_crop[..., 3] >= 200) & ~purple
            copy_zone = zone & redraw_valid
            out = ta.copy()
            # Never extend the old arm's rectangular envelope. The exact
            # redraw silhouette is the only authority for opaque pixels here.
            out[zone, 3] = 0
            out[copy_zone, :3] = redraw_crop[copy_zone, :3].astype(np.int16)
            out[copy_zone, 3] = redraw_crop[copy_zone, 3].astype(np.int16)
            out = np.clip(out, 0, 255).astype(np.uint8)
            Image.fromarray(out).save(f_t)
            Image.fromarray((copy_zone.astype(np.uint8) * 255)).save(
                os.path.join(sprites, "armpit_mask%s.png" % suf))
            filled = int(copy_zone.sum())
            transparent = int(zone.sum() - filled)
            stats[suf or "1x"] = {
                "target_px": int(zone.sum()), "redraw_px": filled,
                "transparent_outside_redraw": transparent,
            }
            print("[armpit] seg_torso%s 自然剪影：重绘 %d px，透明 %d px（不扩张衣服外轮廓）"
                  % (suf, filled, transparent))
            continue

        # Legacy fallback for forms without a no-arms redraw. Teen has one, so
        # it takes the silhouette-clipped path above.
        # 逐行把躯干**侧缘**向外挤出去填满 zone
        #
        # ★★★ 2026-10-26 T67.31：这里原来连**alpha 一起抄**（`px = ta[y, src]`），
        #   而 src 取的是 `torso`（alpha>16）的最外一行像素 —— 那一格恰恰是
        #   抗锯齿的**半透明边**（实测 alpha≈35）。于是整块补出来的腋下
        #   是 alpha 35/255 ≈ 14% 的**雾**：像素数统计（alpha>16）全部通过，
        #   肉眼却是腋下根本没补上，抬臂照样透背景。
        #   实测 seg_torso@2x 里这块雾 23,726 px（左）+ 同量（右），
        #   alpha 中位数 35、颜色是侧缘那圈近白 AA 色 ⇒ 深底上一道灰白雾带，
        #   叠在换装件上就是用户说的「彩边/白边」。
        #   修法：① 颜色只从**实心**像素（alpha≥250）取；② alpha 一律写 255。
        solid = (ta[..., 3] >= 250)
        out = ta.copy()
        filled = 0
        # ★★★ 2026-10-26 T67.32：颜色**不许逐行从侧缘那一个像素抄**。
        #   补完之后实测是一道道横纹（每行取到的是不同的线稿/AA 像素，
        #   逐行颜色跳变 = 横条），这正是用户两次判死过的「逐行插值」。
        #   改成：① 每行取**行内实体像素的中位数**（不看最外圈线稿）；
        #        ② 沿 y 方向做一次窗口平滑（window≈15px@1x）；
        #        ③ 每个像素按"离躯干多远"再压暗一点点，形成侧片阴影，
        #           而不是一条平涂色带。
        #   中位数 + 滑动平均之后，相邻行的差 < 1/255，横纹从根上没了。
        inner = solid & ~zone
        # 行内实体像素的 x 范围（用于算「离躯干多远」）
        row_lo = np.full(H, -1, np.int32)
        row_hi = np.full(H, -1, np.int32)
        prof = np.zeros((H, 3), np.float64)
        have_row = np.zeros(H, bool)
        # 行内**排除线稿**（深色）和靠近补料区的边缘像素
        bright = ta[..., :3].astype(np.float64).mean(axis=2) > 150
        srcmask = solid & bright & ~zone
        if srcmask.sum() < 100:
            srcmask = solid & ~zone
        for y in range(H):
            xs = np.nonzero(inner[y])[0]
            if xs.size:
                row_lo[y], row_hi[y] = int(xs.min()), int(xs.max())
            srow = np.nonzero(srcmask[y])[0]
            if srow.size:
                prof[y] = np.median(ta[y, srow][:, :3], axis=0)
                have_row[y] = True
        if not have_row.any():
            continue
        # 沿 y 平滑（只跨过有数据的行）
        # ★ 窗口必须**够大**：行中位数沿 y 会被衣领/口袋/袖口这些横线带得跳
        #   （实测相邻行差到 101/255），小窗口平滑压不住，补出来仍是一道道横条。
        #   腋下这一小块本来就该是「侧片的一片柔光」，用 ±12% 画布高的窗口
        #   拉成缓变，才是它该有的样子。
        rad = max(3, int(0.12 * H))
        idx = np.nonzero(have_row)[0]
        sm = prof.copy()
        for y in idx:
            lo_y, hi_y = max(0, y - rad), min(H, y + rad + 1)
            win = [k for k in idx if lo_y <= k < hi_y]
            if win:
                # 用**中位数**而不是均值：衣领/袖口那几行是离群值，
                # 均值会把它们摊成一道坡，中位数直接无视。
                sm[y] = np.median(prof[win], axis=0)
        # 没有数据的行沿用最近一行
        last = None
        for y in range(H):
            if have_row[y]:
                last = sm[y]
            elif last is not None:
                sm[y] = last
        dmax_global = 1
        for y in range(H):
            zs = np.nonzero(zone[y])[0]
            if zs.size and row_lo[y] >= 0:
                dmax_global = max(dmax_global, int(np.abs(
                    zs - np.clip(zs, row_lo[y], row_hi[y])).max()))
        for y in range(H):
            zs = np.nonzero(zone[y])[0]
            if len(zs) == 0 or row_lo[y] < 0:
                continue
            rowc = sm[y]          # ★ 别叫 base：外面那个 base 是角色目录路径
            # 侧片阴影按**本行**的宽度归一化：各行的相对渐变一致，
            # 行与行之间才不会因为「这一行补得宽、那一行补得窄」而跳色。
            for x in zs:
                # 离躯干边缘多远 → 越远越暗（侧片背光），最多再压 8%
                d_out = 0 if row_lo[y] <= x <= row_hi[y] else min(
                    abs(x - row_lo[y]), abs(x - row_hi[y]))
                k = a.darken * (1.0 - 0.08 * min(1.0, d_out / float(dmax_global)))
                px = np.clip(np.asarray(rowc) * k, 0, 255)
                out[y, x, :3] = px.astype(np.int16)
                out[y, x, 3] = 255                # ★ 补的是**实体**，不是雾
                filled += 1

        # 轻微模糊只作用在补料区，避免挤出留下竖条纹
        blur = np.array(Image.fromarray(out.astype(np.uint8)).filter(
            ImageFilter.GaussianBlur(1.2 * s))).astype(np.int16)
        inner = zone.copy()
        out[inner] = blur[inner]
        out = np.clip(out, 0, 255).astype(np.uint8)
        Image.fromarray(out).save(f_t)
        # 把补料区单独存成掩膜：① 换装重绘比对剪影时要把它排除（AI 从没见过
        # 这块，它照着「空着的腋下」画，拿补出来的形状去卡它必然判错位）；
        # ② 审计要能量「这块补料是不是又变回雾了」。
        Image.fromarray((zone.astype(np.uint8) * 255)).save(
            os.path.join(sprites, "armpit_mask%s.png" % suf))
        stats[suf or "1x"] = int(filled)
        # ★ 闸：补完的腋下必须是**实体**。只留补料外缘那一圈模糊（≤3px）当抗锯齿。
        # ★ 横纹闸（T67.32）：逐行填色最容易画成一道道横条。
        #   量法：补料区每行的平均色，相邻行的差最大不许超过 2/255。
        #   量的是**补料本身用的行色**（`sm`），不是成图里那一行所有像素：
        #   成图在 zone 与躯干的交界处会混进夹克自己的边线色，那是抗锯齿，
        #   不是横纹，混进来会把正常结果判成条纹（实测误判 9.18/255）。
        rows_mean = [sm[y] for y in range(H)
                     if have_row[y] and (zone[y] & (out[y, :, 3] >= 200)).sum() >= 3]
        if len(rows_mean) >= 9:
            rm = np.asarray(rows_mean)
            # ★ 判据是**高频**分量，不是相邻行差：衣服本身沿 y 就有明暗变化
            #   （领子、口袋、袖口），拿相邻行差当横纹会把正常渐变判成条纹。
            #   去掉 21 行滑动平均之后剩下的才是「条纹」。
            k21 = np.ones(21) / 21.0
            pad = np.pad(rm, ((10, 10), (0, 0)), mode="edge")
            trend = np.stack([np.convolve(pad[:, c], k21, mode="same")[10:-10]
                              for c in range(3)], axis=1)
            jump = float(np.abs(rm - trend).max())
            stats.setdefault("banding", {})[suf or "1x"] = round(jump, 2)
            print("[armpit] seg_torso%s 补料高频条纹 %.2f/255（闸 ≤1.5）" % (suf, jump))
            if jump > 1.5:
                raise SystemExit(
                    "[armpit] seg_torso%s 补料出现横纹（高频 %.2f/255）"
                    " —— 逐行插值已被判死，改用行中位数 + 纵向平滑" % (suf, jump))
        al = out[..., 3]
        veil = int((zone & (al > 16) & (al < 200)).sum())
        hard = int((zone & (al >= 200)).sum())
        stats.setdefault("alpha", {})[suf or "1x"] = {"veil": veil, "hard": hard}
        print("[armpit] seg_torso%s 补了 %d px（实体 %d / 半透 %d，半透应为外缘一圈）"
              % (suf, filled, hard, veil))
        if veil > 0.02 * max(1, hard):
            raise SystemExit(
                "[armpit] seg_torso%s 补出来的腋下有 %d px 是半透的（实体 %d）"
                " —— 补成了雾，抬臂会透背景" % (suf, veil, hard))

    BJ["armpit_patch"] = {
        "sig": sig, "filled_px": stats,
        "note": "tools/armpit_patch.py：补料仅来自无臂重绘图的真实 alpha 剪影；"
                "重绘图之外保持透明，避免侧缘矩形补丁（脇の下の描き足し）"}
    with io.open(bpj, "w", encoding="utf-8") as f:
        f.write(json.dumps(BJ, ensure_ascii=False, indent=2))
        f.write(u"\n")
    print("[armpit] 完成")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
