#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""腕正圆关节（hand_*_pad 重建）—— 修"挥手时手腕变形/冒出一块肉色疙瘩"。

================================ 病因 ================================
用户第四十四问截图第二处：挥手时手腕处会变形。

实拍逐帧（logs/asset_qa/q44_wrist_before.png，HandR −1.6…+1.6 五格）：
袖口左下角会冒出一块**肉色方疙瘩**，手摆到另一侧时又缩回去。

量出来的几何（切件坐标，腕枢轴 (390,666)）：

    hand_r_pad（层 129，挂 **forearm_r** 组 ⇒ 不跟着手转）
        y=枢轴−20: 45px   −10: 45   0: 43   +8: 34   +12: 25   +16: 5
    arm_r_fore 袖口
        y=枢轴−16: 51px   −8: 43    0: 45   +4: 37   +8: 0（袖子到此为止）
    hand_r_open
        y=枢轴  0: 24px   +8: 25    +16: 35   +24: 42

⇒ 垫片在**袖口以下**还留着 +8…+17 那一截（34→5px）。它不是正圆、又不跟手转，
  手一摆，这截固定的料就从袖口下面探出来，成了那块疙瘩。

Live2D 官方口径（sites.google.com/cybernoids.jp 官方手册 / castcraft.live/blog/464）：
**関節パーツは正円にする、直径＝腕の幅**。只要关节料是以枢轴为心的正圆，
不管转多少度，剪影都是同一个圆 —— 不可能变形。

================================ 做法 ================================
    pad_new = ( 旧 pad ∪ 正圆(枢轴, R) ) ∩ 膨胀(袖口掩膜, margin)

  · **正圆**：补齐袖筒内部，保证手转到任何角度，袖口这个洞都是满的；
  · **∩ 袖口掩膜**：把袖口以外的料全部裁掉 —— 疙瘩就是这么来的。
    留 margin(3px) 余量防止袖口边缘出现发丝缝（两边各自抗锯齿会透底）。
  · 垫片挂在前臂组、画在手下面（129 < hand 139 < fore 144/145），
    所以它只负责"填满袖筒"，永远不参与外轮廓 ⇒ 不会把手腕撑粗。

R 取**袖口半宽 + 1.5**：圆要能盖住袖口开口，又不必更大（更大也会被裁掉）。

幂等：写 hand_parts.json["round_wrist"]，参数相同即跳过（--force 强制）。

用法：
    python3 tools/round_wrist_socket.py --character xiaoxun --form teen [--force]
"""
import argparse
import io
import json
import os
import sys

import numpy as np

try:
    from PIL import Image
except ImportError:  # pragma: no cover
    sys.stderr.write("需要 Pillow\n")
    raise


def load(path):
    return Image.open(path).convert("RGBA")


def dilate(mask, r):
    """方形膨胀 r 像素（够用且快；关节这点尺度不必做圆形结构元）。"""
    out = mask.copy()
    for dy in range(-int(r), int(r) + 1):
        for dx in range(-int(r), int(r) + 1):
            if dx * dx + dy * dy > r * r:
                continue
            out |= np.roll(np.roll(mask, dy, axis=0), dx, axis=1)
    return out


def erode(mask, r):
    """方形腐蚀 r 像素（dilate 的对偶，同样用圆形结构元）。"""
    out = mask.copy()
    for dy in range(-int(r), int(r) + 1):
        for dx in range(-int(r), int(r) + 1):
            if dx * dx + dy * dy > r * r:
                continue
            out &= np.roll(np.roll(mask, dy, axis=0), dx, axis=1)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--character", required=True)
    ap.add_argument("--form", required=True)
    ap.add_argument("--margin", type=float, default=-2.0,
                    help="垫片相对袖口掩膜的余量：正数=外探（防发丝缝），"
                         "负数=内缩（防收窄形变器把袖子缩进垫片里，Q46）")
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args()

    base = os.path.join("characters", a.character, "forms", a.form)
    sprites = os.path.join(base, "sprites")
    hpj = os.path.join(sprites, "hand_parts.json")
    apj = os.path.join(sprites, "arm_parts.json")
    if not (os.path.exists(hpj) and os.path.exists(apj)):
        print("[wrist] 缺 hand_parts.json / arm_parts.json，跳过")
        return 0
    with io.open(hpj, encoding="utf-8") as f:
        HJ = json.load(f)
    with io.open(apj, encoding="utf-8") as f:
        AJ = json.load(f)
    HP = {p["id"]: p for p in HJ["parts"]}
    AP = {p["id"]: p for p in AJ["parts"]}

    sig = {"margin": a.margin, "v": 2}
    if HJ.get("round_wrist", {}).get("sig") == sig and not a.force:
        print("[wrist] 已做过腕正圆，跳过（--force 强制）")
        return 0

    orig_dir = os.path.join(sprites, "_orig")
    if not os.path.isdir(orig_dir):
        os.makedirs(orig_dir)

    done = {}
    for side in ("l", "r"):
        pid = "hand_%s_pad" % side
        fid = "arm_%s_fore" % side
        if pid not in HP or fid not in AP:
            continue
        pad = HP[pid]
        piv = pad["pivot"]

        # 袖口半宽：取枢轴那一行袖子的实际宽度
        fo1 = load(os.path.join(base, AP[fid]["file"]))
        fa = np.array(fo1)
        fpos = AP[fid]["pos"]
        row = int(round(piv[1] - fpos[1]))
        half = 22.5
        if 0 <= row < fa.shape[0]:
            xs = np.nonzero(fa[row, :, 3] > 128)[0]
            if len(xs):
                half = (xs.max() - xs.min() + 1) / 2.0
        #    ★★★ 2026-10-22 第四十六问：R 从 half+1.5 改成 half-1.5，裁剪从
        #      dilate 改成 erode。用户第 5 张截图「右手与手肘关节处完全错位」，
        #      染色实拍（logs/asset_qa/q46_tint_junction.png，红=垫片）看到
        #      垫片沿袖口外缘露出一整条月牙，每帧 112~119px。
        #      两笔账叠在一起：① 这里主动放了 margin=+3 让它外探；
        #      ② 挥手时 ParamForeSlimR=1 把袖管横向收窄（袖口处 6%，
        #         43.5px → 40.9px，每边缩 1.3px），而垫片**没有挂这个形变器**。
        #      垫片在层 128/129、袖管在 145，本来应该整片藏在袖子里。
        #      官方口径「関節パーツは正円、直径＝腕の幅」说的是**不超过**腕宽。
        R = half - 1.5

        stat = {}
        for s in (1, 2):
            suf = "" if s == 1 else "@2x"
            f_pad = os.path.join(sprites, "%s%s.png" % (pid, suf))
            f_fo = os.path.join(base, AP[fid]["file"].replace(".png", suf + ".png"))
            if not (os.path.exists(f_pad) and os.path.exists(f_fo)):
                continue
            # 原件备份（本脚本原地覆盖 ⇒ 换参数重跑要从原件重算）
            bak = os.path.join(orig_dir, "%s%s.png" % (pid, suf))
            if not os.path.exists(bak):
                load(f_pad).save(bak)
            im_pad = load(bak)
            im_fo = load(f_fo)
            pa = np.array(im_pad)
            fm = np.array(im_fo)[:, :, 3] > 8

            # 统一到"切件坐标 × s"的大画布上算，最后再裁
            px0, py0 = pad["pos"][0] * s, pad["pos"][1] * s
            fx0, fy0 = AP[fid]["pos"][0] * s, AP[fid]["pos"][1] * s
            X0 = int(min(px0, fx0)) - 4
            Y0 = int(min(py0, fy0)) - 4
            X1 = int(max(px0 + pa.shape[1], fx0 + fm.shape[1])) + 4
            Y1 = int(max(py0 + pa.shape[0], fy0 + fm.shape[0])) + 4
            W, H = X1 - X0, Y1 - Y0

            big = np.zeros((H, W, 4), np.uint8)
            big[int(py0 - Y0):int(py0 - Y0) + pa.shape[0],
                int(px0 - X0):int(px0 - X0) + pa.shape[1]] = pa
            sleeve = np.zeros((H, W), bool)
            sleeve[int(fy0 - Y0):int(fy0 - Y0) + fm.shape[0],
                   int(fx0 - X0):int(fx0 - X0) + fm.shape[1]] = fm

            yy, xx = np.mgrid[0:H, 0:W]
            cx, cy = piv[0] * s - X0, piv[1] * s - Y0
            disc = ((xx - cx) ** 2 + (yy - cy) ** 2) <= (R * s) ** 2

            # 填色：用旧垫片的主色（肤色）；旧料有像素的地方原样保留
            op = pa[:, :, 3] > 200
            if op.sum() == 0:
                print("  [%s] 旧垫片是空的，跳过" % side)
                break
            fill = np.array([int(np.median(pa[:, :, k][op])) for k in range(3)] + [255],
                            np.uint8)
            have = big[:, :, 3] > 0
            add = disc & ~have
            big[add] = fill

            clip = (dilate(sleeve, a.margin * s) if a.margin >= 0
                    else erode(sleeve, -a.margin * s))
            keep = (have | disc) & clip
            big[~keep] = 0

            ys, xs = np.nonzero(big[:, :, 3] > 0)
            if len(xs) == 0:
                print("  [%s] 裁完是空的，跳过" % side)
                break
            if s == 1:
                nx0, ny0 = X0 + xs.min(), Y0 + ys.min()
                nx1, ny1 = X0 + xs.max() + 1, Y0 + ys.max() + 1
                stat["box"] = [nx0, ny0, nx1, ny1]
            bx0, by0, bx1, by1 = stat["box"]
            crop = big[int(by0 * s - Y0):int(by1 * s - Y0),
                       int(bx0 * s - X0):int(bx1 * s - X0)]
            Image.fromarray(crop).save(f_pad)
            stat[s] = [int(crop.shape[1]), int(crop.shape[0]),
                       int((crop[:, :, 3] > 0).sum())]
        if "box" in stat:
            bx0, by0, bx1, by1 = stat["box"]
            pad["pos"] = [int(bx0), int(by0)]
            pad["size"] = [int(bx1 - bx0), int(by1 - by0)]
            pad["note"] = ("腕正圆关节（Q44）：以腕枢轴为心的正圆 ∩ 袖口掩膜。"
                           "圆关于枢轴旋转不变 ⇒ 手摆任何角度，袖口这个洞都是满的；"
                           "裁掉袖口以外的料 ⇒ 不会再从袖口下面探出肉色疙瘩")
            done[side] = {"R": round(R, 1), "size_1x": stat.get(1),
                          "size_2x": stat.get(2)}
            print("[wrist] %s 腕圆 R=%.1f  垫片 1x=%s  2x=%s"
                  % (side, R, stat.get(1), stat.get(2)))

    HJ["round_wrist"] = {"sig": sig, "sides": done}
    with io.open(hpj, "w", encoding="utf-8") as f:
        json.dump(HJ, f, ensure_ascii=False, indent=1)
    print("[wrist] 写回 %s" % hpj)
    return 0


if __name__ == "__main__":
    sys.exit(main())
