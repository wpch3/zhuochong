#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""wrist_tab_trim.py — 裁掉袖管末端那块「不跟手转的肉色方桩」。

================================ 病因 ================================
2026-10-23 第四十七问，用户第二次指着同一处说「这个手腕我不信你看不出来」。

上一轮（第四十六问）我只修了「腕口漏背景」，那是另一个病。这一轮放大看
logs/asset_qa/q47_wrist_after.png，袖口左右两个角上各挂着一小片
**白/肉色的硬边方块**，像贴歪的胶布 —— 染色实拍
（logs/asset_qa/q47_tint_cmp.png，红=hand_r_open 黄=arm_r_fore）证明
那两片是**黄的**，也就是袖管件 arm_?_fore 自己带的料。

打开 arm_r_fore.png 看末端（logs/asset_qa/q47_fore_end.png，8× 洋红底）：
条纹袖口下面接着一块**平底的肉色方块**，是原图切袖管时带出来的塗り足し。
它挂在前臂上 ⇒ **不跟手腕转**；手一摆，方块的两个角就从手的剪影外面探出来。

量化（切件坐标，腕枢轴 (390,666)）：
    袖管末端肉色共 304 px
      · 挥手腕角区间 [−35°,+5°] 里手**永远**盖得住的只有 141 px
      · 比心腕角区间 [0°,+60°] 里只有 103 px
      · 两者都安全的（A∩B）只有 74 px   ⇒ **230 px 必然在某个相位露出来**

================================ 做法 ================================
    肉色_new = 肉色_old ∩ ( 安全区 ∪ 袖布区 )

  · **安全区** = ⋂(θ∈腕角区间) 旋转(手件 alpha, θ)
    —— 以腕枢轴为心把手件转遍整个工作区间再求交集，剩下的就是
    「无论手摆到哪一帧都压在手底下」的那块料。按定义裁完不可能再露出来。
  · **袖布区**（非肉色的袖管像素）原样不动，只裁肉色塗り足し。
  · 裁掉的地方不会漏背景：袖筒洞由 hand_?_pad（round_wrist_socket.py 做的
    正圆垫片，挂前臂、层 128/129 在最底下）+ 手件自带的腕半圆
    （wrist_bridge.py）两层兜着，这两件一个不动一个跟着手转。

为什么不是「把方块改圆」就完事：正圆只在**它自己转**的时候形状不变，
这块料是**不转的**，转的是手。所以判据必须写成「手转遍区间后的交集」。

幂等：原件备份进 sprites/_orig/，签名写进 arm_parts.json 的 wrist_tab 段。
用法：python tools/wrist_tab_trim.py --character xiaoxun --form teen [--force]
"""
import argparse
import io
import json
import os

import numpy as np
from PIL import Image

# 腕角工作区间（度，引擎口径：正=顺时针）。覆盖 wave / wave_both / heart_hands：
#   wave:   pulse −15 + sine ±12 + hand_r_lag ±6  ⇒ [−33, +3]
#   heart:  pulse +55 + sine ±4                   ⇒ [  0, +59]
# 两端各留 3° 余量。
ANGLE_SETS = {
    "open": (-36.0, 6.0),
    "heart": (-6.0, 62.0),
}
STEP = 3.0
# 腕口线沿前臂轴往回退多少像素再开始裁（留给袖口边缘的抗锯齿）
BACKOFF = 2.0


def load(path):
    return Image.open(path).convert("RGBA")


def always_covered(alpha_canvas, cx, cy, lo, hi, step=STEP):
    """手件 alpha 绕 (cx,cy) 转遍 [lo,hi] 后的交集。"""
    acc = None
    t = lo
    while t <= hi + 1e-6:
        rot = alpha_canvas.rotate(-t, resample=Image.NEAREST, center=(cx, cy))
        m = np.array(rot) > 40
        acc = m if acc is None else (acc & m)
        t += step
    return acc


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--character", required=True)
    ap.add_argument("--form", required=True)
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args()

    base = os.path.join("characters", a.character, "forms", a.form)
    sprites = os.path.join(base, "sprites")
    apj = os.path.join(sprites, "arm_parts.json")
    hpj = os.path.join(sprites, "hand_parts.json")
    if not (os.path.exists(apj) and os.path.exists(hpj)):
        print("[wrist_tab] 缺 arm_parts.json / hand_parts.json，跳过")
        return 0
    with io.open(apj, encoding="utf-8") as f:
        AJ = json.load(f)
    with io.open(hpj, encoding="utf-8") as f:
        HJ = json.load(f)
    AP = {p["id"]: p for p in AJ["parts"]}
    HP = {p["id"]: p for p in HJ["parts"]}

    sig = {"v": 3, "angles": ANGLE_SETS, "step": STEP, "backoff": BACKOFF}
    if AJ.get("wrist_tab", {}).get("sig") == sig and not a.force:
        print("[wrist_tab] 已裁过袖口肉桩，跳过（--force 强制）")
        return 0

    orig_dir = os.path.join(sprites, "_orig")
    if not os.path.isdir(orig_dir):
        os.makedirs(orig_dir)

    PAD = 150  # 1× 画布四周余量：手件转进来的那部分不能被裁掉
    done = {}
    for side in ("l", "r"):
        fid = "arm_%s_fore" % side
        if fid not in AP or ("hand_%s" % side) not in AP:
            continue
        piv = AP["hand_%s" % side]["pivot"]

        for s in (1, 2):
            suf = "" if s == 1 else "@2x"
            f_fore = os.path.join(sprites, "%s%s.png" % (fid, suf))
            if not os.path.exists(f_fore):
                continue
            bak = os.path.join(orig_dir, "%s%s.png" % (fid, suf))
            if not os.path.exists(bak):
                load(f_fore).save(bak)

            # 工作画布 = 袖管件四周各放 PAD（像素坐标原点 = 袖管件左上 − PAD）
            fore = load(bak)
            fw, fh = fore.size
            pad = int(PAD * s)
            W = fw + 2 * pad
            H = fh + 2 * pad
            fpos = AP[fid]["pos"]
            cx = (piv[0] - fpos[0]) * s + pad
            cy = (piv[1] - fpos[1]) * s + pad

            # —— 安全区：手件（各姿势）绕腕枢轴转遍各自区间后的交集 ——
            safe = np.ones((H, W), bool)
            used = []
            for pose, (lo, hi) in ANGLE_SETS.items():
                pid = "hand_%s_%s" % (side, pose)
                if pid not in HP:
                    continue
                f_h = os.path.join(sprites, "%s%s.png" % (pid, suf))
                if not os.path.exists(f_h):
                    continue
                im = load(f_h)
                cv = Image.new("L", (W, H), 0)
                cv.paste(im.split()[3],
                         (int(round((HP[pid]["pos"][0] - fpos[0]) * s)) + pad,
                          int(round((HP[pid]["pos"][1] - fpos[1]) * s)) + pad))
                safe &= always_covered(cv, cx, cy, lo, hi)
                used.append(pose)
            if not used:
                continue
            safe = safe[pad:pad + fh, pad:pad + fw]

            # —— 判据走**几何**不走颜色（第二十四问口径）——
            # 颜色判据栽过一次：第一版只认「肉色」，结果袖口白条和描边那几粒
            # 白色像素没被认出来，裁完袖口两角还各挂着一小块白方块
            # （logs/asset_qa/q47_cuff_zoom.png 11× 看得一清二楚）。
            # 改成：**腕口线以外**（沿前臂轴方向越过腕枢轴的那一侧）
            #       且**不在安全区**里的袖管像素，一律裁掉。
            arr = np.array(fore)
            al = arr[..., 3].astype(int)
            ex, ey = AJ["elbow_joint"][side]                 # 肘枢轴（切件坐标）
            ax, ay = piv[0] - ex, piv[1] - ey                # 前臂轴（肘 → 腕）
            n_ = (ax * ax + ay * ay) ** 0.5
            ax, ay = ax / n_, ay / n_
            hh, ww = al.shape
            yy, xx = np.mgrid[0:hh, 0:ww]
            px = (piv[0] - fpos[0]) * s - BACKOFF * s * ax   # 腕口线往回退一点
            py = (piv[1] - fpos[1]) * s - BACKOFF * s * ay
            distal = ((xx - px) * ax + (yy - py) * ay) > 0
            drop = (al > 0) & distal & (~safe)
            if drop.sum() == 0:
                continue
            arr[drop] = (0, 0, 0, 0)
            Image.fromarray(arr).save(f_fore)
            sleeve_sil = (al > 0) & (~drop)

            # —— 顺手修垫片 hand_?_pad —— 
            # 它挂在**前臂**上（跟袖管一起不动），被 round_wrist_socket 裁进
            # 「袖口掩膜膨胀 3px」里 ⇒ 边上多出 3px 探在袖管轮廓外面，
            # 染色实拍 logs/asset_qa/q47_tint2.png 里就是袖口左上那块绿方块。
            # 判据同上：**袖管盖不住、手也盖不住**的垫片像素一律裁掉。
            pid_pad = "hand_%s_pad" % side
            if pid_pad in HP:
                f_pad = os.path.join(sprites, "%s%s.png" % (pid_pad, suf))
                if os.path.exists(f_pad):
                    pbak = os.path.join(orig_dir, "tab_%s%s.png" % (pid_pad, suf))
                    if not os.path.exists(pbak):
                        load(f_pad).save(pbak)
                    pim = load(pbak)        # 永远从自己的备份重算（幂等）
                    ppos = HP[pid_pad]["pos"]
                    pa = np.array(pim)
                    ph, pw = pa.shape[:2]
                    # 把袖管剪影 / 安全区搬到垫片坐标系
                    dx = int(round((fpos[0] - ppos[0]) * s))
                    dy = int(round((fpos[1] - ppos[1]) * s))
                    cover = np.zeros((ph, pw), bool)
                    src = sleeve_sil | safe
                    y1 = max(0, dy); y2 = min(ph, dy + src.shape[0])
                    x1 = max(0, dx); x2 = min(pw, dx + src.shape[1])
                    if y2 > y1 and x2 > x1:
                        cover[y1:y2, x1:x2] = src[y1 - dy:y2 - dy, x1 - dx:x2 - dx]
                    pdrop = (pa[..., 3] > 0) & (~cover)
                    if pdrop.sum():
                        pa[pdrop] = (0, 0, 0, 0)
                        Image.fromarray(pa).save(f_pad)
                        if s == 1:
                            print("[wrist_tab] %s 探出袖管 %d px → 裁掉"
                                  % (pid_pad, int(pdrop.sum())))
            if s == 1:
                tot = int(((al > 0) & distal).sum())
                done[fid] = {"distal": tot, "keep": tot - int(drop.sum()),
                             "drop": int(drop.sum()), "poses": used}
                print("[wrist_tab] %s 腕口线外 %d px → 保留 %d / 裁掉 %d"
                      % (fid, tot, tot - drop.sum(), drop.sum()))

    AJ["wrist_tab"] = {
        "sig": sig, "done": done,
        "note": "tools/wrist_tab_trim.py：裁掉袖管末端不跟手转的肉色方桩（Q47）",
    }
    with io.open(apj, "w", encoding="utf-8") as f:
        f.write(json.dumps(AJ, ensure_ascii=False, indent=2))
        f.write(u"\n")
    print("[wrist_tab] 完成 %d 件" % len(done))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
