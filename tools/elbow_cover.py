#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""肘关节补件（arm_*_elbow）—— 修「折肘处有一道折叠一样的痕迹」。

================================ 病因 ================================
第四十八问用户原话：「肘关节的位置有一些折叠一样的痕迹，看起来不是很自然」。

按工序先出参考比对图、再分件染色实拍，证据链：
  · logs/asset_qa/q48_arm_ab2.png —— 参考 wave_up.png 按头宽 213→109 缩到我们
    的尺度，与挥手峰值帧同比例并排：参考的肘是**一整块连续的布**，
    外轮廓一条 U 兜底，里面只有柔和的布褶。
  · logs/asset_qa/q48_elbow_tint.png（红=上臂 蓝=前臂 绿=肩帽）
    + logs/asset_qa/q48_cover_dbg.png（离线按定稿角度摆位）：
    我们的肘**外轮廓其实是好的** —— round_arm_sockets.py 把两件在肘处都切成了
    「以肘枢轴为心、r≈34.7 的同心半圆」，并集仍是一段光滑圆弧，
    形态学闭运算量出来的缺口只有 99 px（补了也看不见）。

真正的病在**内侧**：
  ① 那个圆里，一半是上臂的料、一半是前臂的料，前臂一转 141°，
     两个半圆各转各的，明暗在交界处断层；
  ② 两条袖管的轮廓线在折肘内侧交成一个尖角 X，上臂那条线越过交点还往
     前臂肚子里扎进去一小段 —— 肉眼读出来就是「布上折了一道痕」。

================================ 做法 ================================
官方口径（sites.google.com/cybernoids.jp/cubism2/.../animator_arms_mtn）：
「関節部分には**腕幅と同じ直径の正円のパーツ**を作り、関節に重ねる」。

  1. 把上臂件 + 前臂件按**静止姿势**合成（静止时两件的切口互补，合起来就是
     原画那条完整的袖子），在 @2x 上取以肘枢轴为心、半径 R 的圆。
  2. 抹掉圆内的描边（最暗的 dark% 像素），用邻近袖色迭代填掉，再轻微模糊
     —— 得到一块「只有明暗、没有线」的袖布。
  3. **只保留内侧扇区**：扇区中心 = 摆好姿势后「肘→肩」与「肘→腕」两个方向的
     角平分线（再反旋转回前臂静止系，因为这块件挂在 forearm_? 组上跟着前臂转）。
     ★ 第一版盖的是整个正圆，实拍三档对照（logs/asset_qa/q48_crease3.png：
       A 只有肘折线 / B 折线+正圆 / C 只有正圆）证明那样是**倒退** ——
       肘底那条深色弧线是这块布**正经的剪影轮廓**，被羽化的圆盖住就糊成一团。
       所以外侧一律不碰，只盖内侧。
  4. 半径方向羽化 + 扇区边缘软化（官方「付け根はぼかす」），不留圆片边。
  5. alpha 绑肘角（make_rig 的 elbow_fade）：伸直 0、折到挥手那档 1。
     **静止画面一个像素都不动**；heart_hands 那种反向折肘也不显形。

幂等：写 arm_parts.json["elbow_cover"]；签名没变就跳过（--force 强制重做）。

用法：
    python3 tools/elbow_cover.py --character xiaoxun --form teen [--force]
"""
import argparse
import io
import json
import math
import os
import sys

import numpy as np

from PIL import Image

LAYER = {"r": 147, "l": 146}      # 压在前臂(144/145) 之上、肘折线(148/149) 之下
#   ★ Q50：原来是 148/149（盖在折线上面）。把圆盘放大到 grow 1.45 之后，
#   它会把 elbow_crease 那条「前臂压在上臂前面」的轮廓线整条吃掉，肘又
#   变回 Q44 那个没有轮廓的圆疙瘩。两件分工：**补件只负责抹掉上臂那条
#   扎进前臂肚子的残线**（在下），**折线负责画前臂的剪影边**（在上）。
SIG_V = 3
# —— 挥手定稿姿势（绝对角，离竖直向下；和 make_rig 的 wave 通道同源）——
#   右：A_u=21.69° / A_f=153.73°   左：A_u=−22.12° / A_f=−152.17°
#   只用来算「折肘时哪半边是内侧」，不参与任何像素采样。
POSE = {"r": (21.69, 153.73), "l": (-22.12, -152.17)}


def load(p):
    return Image.open(p).convert("RGBA")


def nearest_fill(rgb, known, target, rounds=48):
    """把 known 区域的颜色一圈圈推进 target（最近色填充）。"""
    out = rgb.astype(np.float32).copy()
    have = known.copy()
    todo = target & ~have
    for _ in range(rounds):
        if not todo.any():
            break
        acc = np.zeros(out.shape, np.float32)
        cnt = np.zeros(have.shape, np.float32)
        for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            sh = np.roll(np.roll(out, dy, 0), dx, 1)
            sm = np.roll(np.roll(have, dy, 0), dx, 1)
            acc += sh * sm[..., None]
            cnt += sm
        new = todo & (cnt > 0)
        if not new.any():
            break
        out[new] = acc[new] / cnt[new][:, None]
        have |= new
        todo &= ~new
    return out


def box_blur(rgb, mask, rounds):
    out = rgb.astype(np.float32).copy()
    for _ in range(int(rounds)):
        acc = out.copy()
        for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1),
                       (1, 1), (1, -1), (-1, 1), (-1, -1)):
            acc += np.roll(np.roll(out, dy, 0), dx, 1)
        acc /= 9.0
        out[mask] = acc[mask]
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--character", required=True)
    ap.add_argument("--form", required=True)
    ap.add_argument("--grow", type=float, default=1.45,
                    help="补件半径 = 关节 socket 半径 × 这个倍数")
    ap.add_argument("--feather", type=float, default=7.0,
                    help="圆周往里羽化多少像素（1x）")
    ap.add_argument("--dark", type=float, default=14.0,
                    help="圆内最暗的百分之几算描边、要抹掉")
    ap.add_argument("--blur", type=int, default=3, help="抹线后再模糊几轮")
    ap.add_argument("--half", type=float, default=62.0,
                    help="内侧扇区的半角（度）—— 只盖这一片，外侧轮廓不碰")
    ap.add_argument("--soft", type=float, default=26.0,
                    help="扇区边缘再软化多少度")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--quiet", action="store_true")
    a = ap.parse_args()

    base = os.path.join("characters", a.character, "forms", a.form)
    sprites = os.path.join(base, "sprites")
    apj = os.path.join(sprites, "arm_parts.json")
    if not os.path.exists(apj):
        print("[肘补件] 没有 arm_parts.json，跳过")
        return 0
    with io.open(apj, encoding="utf-8") as f:
        meta = json.load(f)
    parts = {p["id"]: p for p in meta["parts"]}

    sig = {"v": SIG_V, "grow": a.grow, "feather": a.feather, "dark": a.dark,
           "blur": a.blur, "half": a.half, "soft": a.soft, "pose": POSE}
    if not a.force and meta.get("elbow_cover", {}).get("sig") == sig:
        if not a.quiet:
            print("[肘补件] 签名未变，跳过（--force 强制重做）")
        return 0

    K = 2                       # 全程在 @2x 上算
    done = {}
    for side in ("l", "r"):
        up = parts.get("arm_%s_upper" % side)
        fo = parts.get("arm_%s_fore" % side)
        hp = parts.get("hand_%s" % side)
        if not up or not fo or not hp:
            continue
        ex, ey = fo["pivot"]
        r_sock = float(meta.get("round_socket", {}).get(side, {}).get("r_elbow", 34.0))
        R = r_sock * a.grow

        # —— 静止姿势下把两件拼回原画那条袖子（@2x）——
        box = (int((ex - R - 4) * K), int((ey - R - 4) * K),
               int((ex + R + 4) * K) + 1, int((ey + R + 4) * K) + 1)
        W, H = box[2] - box[0], box[3] - box[1]
        canvas = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        for pt in (up, fo):      # 前臂后贴 = 压在上臂之上，和运行时层序一致
            img = load(os.path.join(base, pt["file"].replace(".png", "@2x.png")))
            canvas.alpha_composite(
                img, (int(pt["pos"][0] * K) - box[0], int(pt["pos"][1] * K) - box[1]))
        arr = np.array(canvas)
        rgb = arr[..., :3].astype(np.float32)
        solid = arr[..., 3] > 200

        cx, cy = ex * K - box[0], ey * K - box[1]
        yy, xx = np.mgrid[0:H, 0:W]
        rad = np.hypot(xx - cx, yy - cy)

        # —— 内侧扇区：肘→肩 与 肘→腕 的角平分线，反旋转回前臂静止系 ——
        au, af = POSE[side]
        wx, wy = hp["pivot"]
        f0 = math.degrees(math.atan2(wx - ex, wy - ey))
        thf = af - f0                       # 前臂内容的净转角
        v_up = (-math.sin(math.radians(au)), -math.cos(math.radians(au)))
        v_fo = (math.sin(math.radians(af)), math.cos(math.radians(af)))
        bx, by = v_up[0] + v_fo[0], v_up[1] + v_fo[1]
        bn = math.hypot(bx, by) or 1.0
        bx, by = bx / bn, by / bn
        ca, sa = math.cos(math.radians(-thf)), math.sin(math.radians(-thf))
        rx = bx * ca + by * sa
        ry = -bx * sa + by * ca
        ang = np.degrees(np.arccos(np.clip(
            ((xx - cx) * rx + (yy - cy) * ry) / np.maximum(rad, 1e-6), -1, 1)))
        sector = np.clip((a.half + a.soft - ang) / max(1.0, a.soft), 0.0, 1.0)

        disc = (rad <= R * K) & solid & (sector > 0.02)
        if disc.sum() < 100:
            if not a.quiet:
                print("[肘补件] %s 侧圆内有料太少（%d），跳过" % (side, disc.sum()))
            continue

        # —— 抹掉圆内的描边：最暗的 dark% 交给邻近袖色 ——
        lum = rgb.mean(2)
        thr = np.percentile(lum[disc], a.dark)
        ink = disc & (lum <= thr)
        keep = disc & ~ink
        flat = nearest_fill(rgb, keep, ink)
        flat = box_blur(flat, disc, a.blur)

        # —— 羽化：圆心 1.0、圆周 0；扇区边缘再乘一层软化 ——
        fe = max(1.0, a.feather * K)
        al = np.clip((R * K - rad) / fe, 0.0, 1.0) * sector
        out = np.zeros((H, W, 4), np.uint8)
        out[..., :3] = flat.clip(0, 255).astype(np.uint8)
        out[..., 3] = (al * 255.0 * disc).astype(np.uint8)

        im2 = Image.fromarray(out)
        ys, xs = np.where(out[..., 3] > 2)
        x0, x1 = int(xs.min()), int(xs.max()) + 1
        y0, y1 = int(ys.min()), int(ys.max()) + 1
        x0 -= (x0 + box[0]) % K
        y0 -= (y0 + box[1]) % K
        x1 += (-(x1 + box[0])) % K
        y1 += (-(y1 + box[1])) % K
        crop = im2.crop((x0, y0, x1, y1))
        pid = "arm_%s_elbow" % side
        crop.save(os.path.join(sprites, pid + "@2x.png"))
        crop.resize((crop.width // K, crop.height // K),
                    Image.LANCZOS).save(os.path.join(sprites, pid + ".png"))

        entry = {"id": pid, "file": "sprites/%s.png" % pid,
                 "group": "forearm_%s" % side, "layer": LAYER[side],
                 "pos": [(x0 + box[0]) // K, (y0 + box[1]) // K],
                 "size": [crop.width // K, crop.height // K],
                 "pivot": [ex, ey],
                 "note": "肘关节补件（Q48）：折肘时上臂半圆与前臂半圆在**内侧**的"
                         "拼缝 + 两条轮廓线交出来的尖角，用这块抹过线、羽化过的"
                         "袖布盖住（官方「関節に正円を重ねる / 付け根はぼかす」）。"
                         "外侧剪影轮廓一律不碰；伸直时 alpha=0，静止画面零改动"}
        meta["parts"] = [p for p in meta["parts"] if p["id"] != pid] + [entry]
        done[side] = {"r_socket": r_sock, "r_cover": round(R, 1),
                      "inner_dir": [round(rx, 3), round(ry, 3)],
                      "disc_px_2x": int(disc.sum()), "ink_px_2x": int(ink.sum()),
                      "size": entry["size"], "pos": entry["pos"]}
        if not a.quiet:
            print("[肘补件] %s 侧：r %.1f→%.1f，扇区内 %d px、抹线 %d px，切件 %dx%d @%s"
                  % (side, r_sock, R, disc.sum(), ink.sum(),
                     entry["size"][0], entry["size"][1], entry["pos"]))

    meta["elbow_cover"] = {"sig": sig, "sides": done}
    with io.open(apj, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
    return 0


if __name__ == "__main__":
    sys.exit(main())
