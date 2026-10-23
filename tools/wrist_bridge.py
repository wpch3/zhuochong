#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""wrist_bridge.py — 给手部差分件补「以腕枢轴为心的半圆塗り足し」。

为什么要有这一步（2026-10-22 第四十六问）
------------------------------------------------
用户第 5 张截图：「右手与手肘关节处完全错位了」。
染色实拍（绿=袖管 arm_r_fore、黄=张开手 hand_r_open、红=腕垫 hand_r_pad，
logs/asset_qa/q46_tint_wave.png / q46_tint_junction.png）看到两处病：

  ① 腕垫沿袖口外缘露出一整条月牙 —— 已由 round_wrist_socket.py 改口径解决；
  ② 手与袖口之间**漏出背景**（8× 放大图里黄绿之间的洋红）。

② 的根因在 hand_parts.json 里摆着：

    hand_r_pad   wrist_w = 43      ← 袖口洞有这么宽
    hand_r_open  wrist_w = 24      ← 手自带的腕桩只有这么宽

手件绕腕枢轴旋转（挥手时腕角 21°±16°），而袖管不转。手腕一摆，
24px 宽的桩子立刻从 43px 宽的袖口洞里让开一道楔形缝，缝里什么都没有。
腕垫 hand_r_pad 挂在**前臂**上、又被裁进袖口掩膜里，填不到袖口**外面**那道缝。

官方口径（已落档 docs/REFERENCE_NOTES.md 第五十四~五十六批）：
  · 「関節パーツは正円にする、直径＝腕の幅」
  · 「隙間が生じる部分は描き足す」「描きすぎるくらいでちょうどいい」
正圆**关于自身旋转不变** ⇒ 手转到任何角度，半径 R 以内的区域永远是满的。
所以这一步给每张手件在腕口那一侧补一枚半径 R 的半圆（近端），
R 取**袖口半宽 − 1.5**：既盖满袖口洞，又永远缩在袖管轮廓里
（袖管还会被 ParamForeSlim 收窄 6%，必须留这点余量，否则换成肉色月牙）。

补料是平涂肤色（取腕口那几行的中位色），因为它在正常姿势下
**整片藏在袖子底下**（手件层 130~133 < 袖管层 144/145），
只有手转开时才在缝里露出一丁点 —— 露出来的正该是手腕。

幂等：原件备份进 sprites/_orig/，签名写进 hand_parts.json 的 wrist_bridge 段。
用法：python tools/wrist_bridge.py --character xiaoxun --form teen [--force]
"""
import argparse
import io
import json
import os

import numpy as np
from PIL import Image

POSES = ("open", "heart")


# 腕角工作区间（度，引擎口径 正=顺时针）：wave pulse −15 + sine ±12 + lag ±6，
# heart pulse +55 + sine ±4 ⇒ 合起来 [−36, +62]，两端各留 3°。
BRIDGE_ANGLES = (-36.0, 62.0)
BRIDGE_STEP = 3.0


def always_under_sleeve(fore_arr, fpos, piv, nx0, ny0, s, H2, W2):
    """手件画布上「手转遍腕角区间后每一帧都还压在袖管剪影里」的掩膜。

    手件绕腕枢轴转 θ ⇒ 在**手件自己的坐标系**里看，袖管相当于转了 −θ。
    所以把袖管掩膜贴到手件画布上、绕枢轴转 −θ，对整个区间求交集即可。
    """
    sleeve = Image.fromarray((fore_arr[:, :, 3] > 40).astype(np.uint8) * 255, "L")
    cv = Image.new("L", (W2, H2), 0)
    cv.paste(sleeve, (int(round((fpos[0] - nx0) * s)),
                      int(round((fpos[1] - ny0) * s))))
    cx = (piv[0] - nx0) * s
    cy = (piv[1] - ny0) * s
    acc = None
    t = BRIDGE_ANGLES[0]
    while t <= BRIDGE_ANGLES[1] + 1e-6:
        m = np.array(cv.rotate(t, resample=Image.NEAREST, center=(cx, cy))) > 40
        acc = m if acc is None else (acc & m)
        t += BRIDGE_STEP
    return acc


def load(path):
    return Image.open(path).convert("RGBA")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--character", required=True)
    ap.add_argument("--form", required=True)
    ap.add_argument("--inset", type=float, default=1.5,
                    help="半圆半径比袖口半宽小多少（留给收窄形变器的余量）")
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args()

    base = os.path.join("characters", a.character, "forms", a.form)
    sprites = os.path.join(base, "sprites")
    hpj = os.path.join(sprites, "hand_parts.json")
    apj = os.path.join(sprites, "arm_parts.json")
    if not (os.path.exists(hpj) and os.path.exists(apj)):
        print("[wrist_bridge] 缺 hand_parts.json / arm_parts.json，跳过")
        return 0
    with io.open(hpj, encoding="utf-8") as f:
        HJ = json.load(f)
    with io.open(apj, encoding="utf-8") as f:
        AJ = json.load(f)
    HP = {p["id"]: p for p in HJ["parts"]}
    AP = {p["id"]: p for p in AJ["parts"]}

    sig = {"inset": a.inset, "v": 2, "angles": BRIDGE_ANGLES}
    if HJ.get("wrist_bridge", {}).get("sig") == sig and not a.force:
        print("[wrist_bridge] 已补过腕半圆，跳过（--force 强制）")
        return 0

    orig_dir = os.path.join(sprites, "_orig")
    if not os.path.isdir(orig_dir):
        os.makedirs(orig_dir)

    done = {}
    for side in ("l", "r"):
        fid = "arm_%s_fore" % side
        pid_pad = "hand_%s_pad" % side
        if fid not in AP or pid_pad not in HP:
            continue
        piv = HP[pid_pad]["pivot"]

        # 袖口半宽：和 round_wrist_socket.py 同一口径 —— 枢轴那一行袖子的实宽
        fpos = AP[fid]["pos"]
        fo_by_s = {}
        for _s in (1, 2):
            _f = os.path.join(sprites, "%s%s.png" % (fid, "" if _s == 1 else "@2x"))
            if os.path.exists(_f):
                fo_by_s[_s] = np.array(load(_f))
        fo = fo_by_s.get(1)
        row = int(round(piv[1] - fpos[1]))
        half = 22.5
        if 0 <= row < fo.shape[0]:
            xs = np.nonzero(fo[row, :, 3] > 128)[0]
            if len(xs):
                half = (xs.max() - xs.min() + 1) / 2.0
        R = half - a.inset

        for pose in POSES:
            pid = "hand_%s_%s" % (side, pose)
            if pid not in HP:
                continue
            stat = {}
            for s in (1, 2):
                suf = "" if s == 1 else "@2x"
                f_h = os.path.join(sprites, "%s%s.png" % (pid, suf))
                if not os.path.exists(f_h):
                    continue
                bak = os.path.join(orig_dir, "%s%s.png" % (pid, suf))
                if not os.path.exists(bak):
                    load(f_h).save(bak)
                im = load(bak)
                arr = np.array(im)
                fo = fo_by_s.get(s, fo_by_s.get(1))
                pos = HP[pid]["pos"]           # 1× 画布坐标

                # 腕口在**上**边（make_hand_parts 把生图旋了 180°）。
                # 画布可能不够高，先往上扩到能装下整枚半圆。
                need_top = piv[1] - R - 2.0
                grow = max(0, int(np.ceil((pos[1] - need_top) * s)))
                # 左右也要装得下半圆
                need_l = piv[0] - R - 2.0
                need_r = piv[0] + R + 2.0
                grow_l = max(0, int(np.ceil((pos[0] - need_l) * s)))
                grow_r = max(0, int(np.ceil((need_r - (pos[0] + arr.shape[1] / s)) * s)))
                H2 = arr.shape[0] + grow
                W2 = arr.shape[1] + grow_l + grow_r
                big = np.zeros((H2, W2, 4), np.uint8)
                big[grow:, grow_l:grow_l + arr.shape[1]] = arr
                nx0 = pos[0] - grow_l / float(s)
                ny0 = pos[1] - grow / float(s)

                # 肤色：取腕口那 6 行里不透明像素的中位色
                opq = arr[:, :, 3] > 200
                band = opq[: max(4, int(8 * s))]
                if band.sum() < 20:
                    band = opq
                src = arr[: band.shape[0]]
                cols = [int(np.median(src[:, :, k][band])) for k in range(3)]
                fill = np.array(cols + [255], np.uint8)

                yy, xx = np.mgrid[0:H2, 0:W2]
                cx = (piv[0] - nx0) * s
                cy = (piv[1] - ny0) * s
                disc = ((xx - cx) ** 2 + (yy - cy) ** 2) <= (R * s) ** 2
                # 只补**近端**半圆（腕口那半边）：远端是手掌，不该多出肉
                disc &= yy <= cy + 1.5 * s
                # ★ 2026-10-23 第四十七问补判据：补料**只许待在袖管底下**。
                #   半圆是跟着手转的，袖管不转 —— 手一摆，半圆的边就从袖口
                #   侧面探出来一小块（logs/asset_qa/q47_tint2.png 里红色那块）。
                #   所以把补料限制在「手转遍整个腕角工作区间后，**每一帧**都还
                #   压在袖管剪影里」的那块区域：⋂(θ) 旋转(袖管掩膜, −θ)。
                disc &= always_under_sleeve(fo, fpos, piv, nx0, ny0, s, H2, W2)
                add = disc & (big[:, :, 3] == 0)
                big[add] = fill

                ys2, xs2 = np.nonzero(big[:, :, 3] > 0)
                if s == 1:
                    stat["box"] = [int(nx0 + xs2.min()), int(ny0 + ys2.min()),
                                   int(nx0 + xs2.max() + 1), int(ny0 + ys2.max() + 1)]
                bx0, by0, bx1, by1 = stat["box"]
                crop = big[int(by0 * s - ny0 * s):int(by1 * s - ny0 * s),
                           int(bx0 * s - nx0 * s):int(bx1 * s - nx0 * s)]
                Image.fromarray(crop).save(f_h)
                stat[s] = [int(crop.shape[1]), int(crop.shape[0]),
                           int(add.sum())]
            if "box" in stat:
                bx0, by0, bx1, by1 = stat["box"]
                HP[pid]["pos"] = [int(bx0), int(by0)]
                HP[pid]["size"] = [int(bx1 - bx0), int(by1 - by0)]
                HP[pid]["wrist_w"] = int(round(2 * R))
                HP[pid]["note"] = (
                    "腕半圆塗り足し（Q46）：以腕枢轴为心、半径=袖口半宽−%.1f 的近端半圆。"
                    "正圆关于旋转不变 ⇒ 手腕摆到任何角度，袖口那道缝都有肉填着。" % a.inset)
                done[pid] = {"R": round(R, 1), "size_1x": stat.get(1),
                             "size_2x": stat.get(2)}
                print("[wrist_bridge] %s  R=%.1f  1x=%s  2x=%s"
                      % (pid, R, stat.get(1), stat.get(2)))

    HJ["wrist_bridge"] = {"sig": sig, "done": done,
                          "note": "tools/wrist_bridge.py：手件腕口补正圆塗り足し"}
    with io.open(hpj, "w", encoding="utf-8") as f:
        f.write(json.dumps(HJ, ensure_ascii=False, indent=2))
        f.write(u"\n")
    print("[wrist_bridge] 完成 %d 件" % len(done))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
