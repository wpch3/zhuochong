#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""armpit_patch.py — 把**脇の下（腋下）**补画进躯干件。

为什么要有这一步（2026-10-22 第四十六问，kirara_jump 全身巡检查出来的）
----------------------------------------------------------------------
把手臂抬起来的三个动作逐帧数「被实体包住的背景像素」（判据：框内某个
背景像素的上下左右都还有实体 ⇒ 它是个洞，不是轮廓外的空白）：

    kirara_jump  f24  左 66 / 右 92 px
    wave_both    全程 左 50~87 / 右 29~50 px
    wave         全程 右 23~83 px        ← 单手挥手也一直有，是老账

实拍（logs/asset_qa/q46_hole_wave_both.png）：白夹克的侧缘和青袖子之间
裂开一道**楔形背景**，正在腋窝的位置。

根因是原画的先天缺陷，和第四十四问的袖根是同一类：原画里手臂垂着，
**腋下那块身体根本没画**（被胳膊挡着）。手臂一抬，那里就只剩背景。
官方教程写得很直白（REFERENCE_NOTES 第五十批）：
  「元画で隠れていた部分（脇の下、袖の中の腕の続き）は描き足しておく」

袖子那一半已经由 sleeve_underlay.py 补过（arm_*_root），但那是**跟着
手臂转**的件，手臂抬走它也跟着走，填不了腋窝。腋窝必须补在**不动的
躯干**上。

做法
----
  patch_zone = 休止姿势下手臂四件的并集 ∩ ¬躯干 ∩ 肩枢轴附近
  patch      = 把躯干**侧缘的像素逐行向外挤出**填满 patch_zone，压暗 10%
  seg_torso  = 原躯干 ∪ patch

· 只补「休止姿势下被手臂盖住」的地方 ⇒ 手臂垂着时**一个像素都看不见**
  （手臂件在层 140~145，躯干 100，盖得严严实实）；
· 压暗 10%：腋窝本来就是阴影区，直接平铺侧缘的亮色会糊成一块白板；
· 逐行挤出而不是镜像：夹克侧缘是一条竖直的布料，挤出正好延续它的明暗。

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

    sig = {"radius": a.radius, "darken": a.darken, "v": 1}
    if BJ.get("armpit_patch", {}).get("sig") == sig and not a.force:
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
        tim = load(bak)
        ta = np.array(tim).astype(np.int16)
        tpos = BP["seg_torso"]["pos"]
        H, W = ta.shape[:2]
        torso = ta[:, :, 3] > 16

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
        zone = armzone & ~torso & near
        if zone.sum() == 0:
            print("[armpit] %s 没有要补的地方" % suf)
            continue

        # 逐行把躯干**侧缘**向外挤出去填满 zone
        out = ta.copy()
        filled = 0
        for y in range(H):
            zs = np.nonzero(zone[y])[0]
            if len(zs) == 0:
                continue
            ts = np.nonzero(torso[y])[0]
            if len(ts) == 0:
                continue
            lo, hi = ts.min(), ts.max()
            for x in zs:
                src = lo if x < lo else (hi if x > hi else None)
                if src is None:
                    # 躯干内部的孔（极少）——取同行最近的实体像素
                    d = np.abs(ts - x)
                    src = ts[int(np.argmin(d))]
                px = ta[y, src].astype(float)
                px[:3] *= a.darken
                out[y, x] = np.clip(px, 0, 255)
                filled += 1

        # 轻微模糊只作用在补料区，避免挤出留下竖条纹
        blur = np.array(Image.fromarray(out.astype(np.uint8)).filter(
            ImageFilter.GaussianBlur(1.2 * s))).astype(np.int16)
        inner = zone.copy()
        out[inner] = blur[inner]
        Image.fromarray(np.clip(out, 0, 255).astype(np.uint8)).save(f_t)
        stats[suf or "1x"] = int(filled)
        print("[armpit] seg_torso%s 补了 %d px" % (suf, filled))

    BJ["armpit_patch"] = {
        "sig": sig, "filled_px": stats,
        "note": "tools/armpit_patch.py：把休止姿势下被手臂盖住、抬臂后会露出背景的"
                "腋窝区域用躯干侧缘挤出补满（脇の下の描き足し）"}
    with io.open(bpj, "w", encoding="utf-8") as f:
        f.write(json.dumps(BJ, ensure_ascii=False, indent=2))
        f.write(u"\n")
    print("[armpit] 完成")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
