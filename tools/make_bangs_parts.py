#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""make_bangs_parts.py - 用 AI 重绘的"无刘海脸"补出额头，把刘海拆成独立零件。

为什么必须用重绘：
  刘海底下的额头与眉毛，在原画里**一个像素都没有**。抠图抠不出来、程序也算不出来，
  只能让 AI 按同一套配色重画一张"没有刘海的脸"，再**只把被挡住的那块**贴回去。
  这是 docs/ART_PARTS.md 里写的 G4c 流程第一次真正跑通。

输入：
  sprites/seg_head.png            现在的头（刘海压在额头上）
  重绘图（洋红底，AI 生成的"无刘海脸"）
输出：
  sprites/hair_front.png          刘海（原画像素，一刀不改）
  sprites/seg_head.png            额头被补全的头（刘海位置换成重绘的皮肤+眉毛）
  sprites/bangs_report.json       对齐参数、补了多少像素、色差

对齐方式：两张图都找蓝色虹膜，用两眼中点与瞳距解出缩放+平移（AI 重绘的构图总会偏一点）。
贴回去之前先做肤色配准（按两张图公共皮肤区的均值做逐通道增益），否则额头会出现色块。

用法：
  ~/.imgenv/bin/python tools/make_bangs_parts.py --character xiaoxun --form teen \
      --redraw characters/xiaoxun/design/redraw/head_nobangs.png
"""
from __future__ import annotations
import argparse, json, os
from collections import deque

import numpy as np
from PIL import Image


# ----------------------------------------------------------------- 工具
def components(mask, min_px=1):
    out = []
    seen = np.zeros(mask.shape, bool)
    for sy in range(mask.shape[0]):
        for sx in range(mask.shape[1]):
            if mask[sy, sx] and not seen[sy, sx]:
                q = deque([(sy, sx)])
                seen[sy, sx] = True
                pts = [(sy, sx)]
                while q:
                    y, x = q.popleft()
                    for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1),
                                   (1, 1), (1, -1), (-1, 1), (-1, -1)):
                        v, u = y + dy, x + dx
                        if 0 <= v < mask.shape[0] and 0 <= u < mask.shape[1] \
                           and mask[v, u] and not seen[v, u]:
                            seen[v, u] = True
                            q.append((v, u))
                            pts.append((v, u))
                if len(pts) >= min_px:
                    out.append(pts)
    out.sort(key=len, reverse=True)
    return out


def iris_centers(rgb):
    """找两只眼睛的虹膜中心（按 x 排序）。

    坑：这个角色的**发梢也是蓝的**（#6599C6），而且左右对称、比眼睛还大一点。
    第一版判据（B-R>70）把发梢当成了眼睛，整整差了 70px —— 对齐还能凑合，
    但拿它定"眉毛在哪一条带上"就全错了。
    现在用两条规矩挡掉：① 虹膜更暗（R<110）；② 成对的候选里取**靠上**那一对。
    """
    blue = (rgb[..., 2] - rgb[..., 0] > 40) & (rgb[..., 0] < 110) & \
           (rgb[..., 2] < 195) & (rgb[..., 2] > 90)
    cs = []
    for pts in components(blue, 60)[:10]:
        ys = [p[0] for p in pts]
        xs = [p[1] for p in pts]
        cs.append((sum(xs) / len(xs), sum(ys) / len(ys), len(pts)))
    pairs = []
    for i in range(len(cs)):
        for j in range(i + 1, len(cs)):
            dy = abs(cs[i][1] - cs[j][1])
            dxx = abs(cs[i][0] - cs[j][0])
            if dy < 0.05 * rgb.shape[0] and dxx > 0.15 * rgb.shape[1]:
                pairs.append(sorted([cs[i], cs[j]]))
    if not pairs:
        raise SystemExit("找不到两只眼睛，无法对齐")
    pairs.sort(key=lambda pr: (pr[0][1] + pr[1][1]) / 2)   # y 最小的一对 = 眼睛
    return pairs[0]


def dilate(m, r=1):
    out = m.copy()
    for _ in range(r):
        acc = out.copy()
        for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            acc |= np.roll(np.roll(out, dy, 0), dx, 1)
        out = acc
    return out


def erode(m, r=1):
    return ~dilate(~m, r)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--character", required=True)
    ap.add_argument("--form", required=True)
    ap.add_argument("--redraw", required=True, help="AI 重绘的无刘海脸（洋红底）")
    ap.add_argument("--root", default=".")
    args = ap.parse_args()

    base = os.path.join(args.root, "characters", args.character, "forms", args.form)
    sp = os.path.join(base, "sprites")
    head = Image.open(os.path.join(sp, "seg_head.png")).convert("RGBA")
    H, W = head.height, head.width
    ha = np.array(head).astype(int)
    hal = ha[..., 3]
    hrgb = ha[..., :3]

    # --- 1) 对齐：两张图都按 3 倍做，精度高一点
    SCALE = 3
    src_big = Image.new("RGBA", (W, H), (255, 0, 255, 255))
    src_big.alpha_composite(head)
    src_big = src_big.convert("RGB").resize((W * SCALE, H * SCALE), Image.LANCZOS)
    gen = Image.open(args.redraw).convert("RGB")
    s_rgb = np.array(src_big).astype(int)
    g_rgb = np.array(gen).astype(int)
    (sx0, sy0, _), (sx1, sy1, _) = iris_centers(s_rgb)
    (gx0, gy0, _), (gx1, gy1, _) = iris_centers(g_rgb)
    k = ((sx1 - sx0) ** 2 + (sy1 - sy0) ** 2) ** 0.5 / \
        (((gx1 - gx0) ** 2 + (gy1 - gy0) ** 2) ** 0.5)
    gw, gh = int(round(gen.width * k)), int(round(gen.height * k))
    g2 = gen.resize((gw, gh), Image.LANCZOS)
    dx = (sx0 + sx1) / 2 - ((gx0 + gx1) / 2) * k
    dy = (sy0 + sy1) / 2 - ((gy0 + gy1) / 2) * k
    aligned_big = Image.new("RGB", src_big.size, (255, 0, 255))
    aligned_big.paste(g2, (int(round(dx)), int(round(dy))))
    aligned = np.array(aligned_big.resize((W, H), Image.LANCZOS)).astype(int)

    # --- 2) 判定：哪里是"刘海压着额头"
    solid = hal > 100
    warm_src = (hrgb[..., 0] > hrgb[..., 2] + 18) & (hrgb[..., 0] > 200)   # 原图是皮肤
    warm_gen = (aligned[..., 0] > aligned[..., 2] + 18) & (aligned[..., 0] > 200)
    # 刘海会一直垂到眼睛上沿，所以补画区要留到虹膜稍下面一点；
    # 再往下就进眼睛了（那块由眼睛零件负责）。
    eye_top = int(min(sy0, sy1) / SCALE) + 60
    zone = np.zeros((H, W), bool)
    zone[:eye_top, :] = True
    occluded = solid & zone & (~warm_src) & warm_gen
    occluded = erode(dilate(occluded, 2), 2)        # 去掉零碎
    comps = components(occluded, 80)
    occluded = np.zeros((H, W), bool)
    for pts in comps:
        for y, x in pts:
            occluded[y, x] = True
    # 往"脸这一侧"外扩 2px：发丝边缘的半透明过渡像素要一起交给刘海零件，
    # 否则刘海一摆，额头上会留下一圈淡淡的"发丝幽灵"。
    # 只在重绘图判定为皮肤的地方扩，所以不会啃进头顶的头发。
    occluded = (dilate(occluded, 2) & warm_gen & solid & zone) | occluded
    # 补丁内部的小窟窿（零散发丝、残留抗锯齿点）一并补掉，不然刘海一动就是一脸麻点
    hole_zone = dilate(occluded, 3)
    for pts in components(hole_zone & (~occluded), 1):
        if len(pts) <= 400 and all(occluded[max(0, y - 4):y + 5, max(0, x - 4):x + 5].any()
                                   for y, x in pts[:1]):
            edge = any(y == 0 or x == 0 or y == H - 1 or x == W - 1 for y, x in pts)
            ring = set()
            for y, x in pts:
                for dy2, dx2 in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    v, u = y + dy2, x + dx2
                    if 0 <= v < H and 0 <= u < W and not (hole_zone[v, u] & ~occluded[v, u]):
                        ring.add(bool(occluded[v, u]))
            if not edge and ring == {True}:          # 四面都被补丁围住 = 真窟窿
                for y, x in pts:
                    occluded[y, x] = True
    if occluded.sum() < 200:
        print(f"额头上没找到被刘海挡住的区域（只有 {int(occluded.sum())} 像素），"
              "可能已经补过了，跳过")
        return

    # --- 3) 肤色配准：只拿"补丁四周那一圈皮肤"来算，别拿整张脸
    #      （整张脸里有腮红、下巴阴影，算出来的增益会让额头发黄 —— 第一版就是这么黄的）
    band = dilate(occluded, 6) & (~occluded) & warm_src & warm_gen & solid
    if band.sum() < 200:
        band = solid & warm_src & warm_gen
    gain = np.ones(3)
    off = np.zeros(3)
    for c in range(3):
        a_v = hrgb[..., c][band].astype(float)
        b_v = aligned[..., c][band].astype(float)
        if len(a_v) > 50 and b_v.std() > 1.0:
            g = np.clip(a_v.std() / b_v.std(), 0.8, 1.25)       # 对比度
            o = a_v.mean() - g * b_v.mean()                      # 亮度
            gain[c], off[c] = g, o
        elif len(a_v) > 10 and b_v.mean() > 1:
            gain[c] = a_v.mean() / b_v.mean()
    fixed = np.clip(aligned * gain + off, 0, 255)

    # --- 4) 刘海零件 = 原画像素；头 = 换成重绘的额头
    bangs = np.zeros((H, W, 4), np.uint8)
    bangs[..., :3] = np.where(occluded[..., None], hrgb, 0)
    bangs[..., 3] = np.where(occluded, hal, 0)
    ys, xs = np.nonzero(occluded)
    by0, by1, bx0, bx1 = int(ys.min()), int(ys.max()) + 1, int(xs.min()), int(xs.max()) + 1
    Image.fromarray(bangs[by0:by1, bx0:bx1]).save(os.path.join(sp, "hair_front.png"))

    newhead = np.array(head).copy()
    for c in range(3):
        newhead[..., c] = np.where(occluded, fixed[..., c].round().astype(np.uint8),
                                   newhead[..., c])
    newhead[..., 3] = np.where(occluded, 255, newhead[..., 3])
    Image.fromarray(newhead).save(os.path.join(sp, "seg_head.png"))

    # --- 5) 登记零件 + 报告
    bp_path = os.path.join(sp, "body_parts.json")
    bp = json.load(open(bp_path, encoding="utf-8"))
    head_pos = next(p["pos"] for p in bp["parts"] if p["id"] == "seg_head")
    entry = {
        "id": "hair_front",
        "file": "sprites/hair_front.png",
        "pos": [head_pos[0] + bx0, head_pos[1] + by0],
        "size": [bx1 - bx0, by1 - by0],
        "group": "head",
        "layer": 240,
        "note": "刘海：原画像素原样切出；它底下的额头由 AI 重绘补全，所以能摆动",
    }
    bp["parts"] = [p for p in bp["parts"] if p["id"] != "hair_front"] + [entry]
    note = "刘海已拆件，额头由 AI 重绘补全（make_bangs_parts.py）"
    if note not in bp.setdefault("patches", []):
        bp["patches"].append(note)
    json.dump(bp, open(bp_path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)

    rep = {
        "redraw": args.redraw,
        "align": {"scale": round(float(k), 4), "dx": round(float(dx), 1),
                  "dy": round(float(dy), 1),
                  "src_iris": [[round(sx0), round(sy0)], [round(sx1), round(sy1)]],
                  "gen_iris": [[round(gx0), round(gy0)], [round(gx1), round(gy1)]]},
        "filled_px": int(occluded.sum()),
        "skin_gain": [round(float(v), 4) for v in gain],
        "skin_offset": [round(float(v), 2) for v in off],
        "part": entry,
    }
    json.dump(rep, open(os.path.join(sp, "bangs_report.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    print(f"对齐 scale={k:.4f} 平移=({dx:.1f},{dy:.1f})  "
          f"肤色增益 {np.round(gain,3).tolist()} 偏移 {np.round(off,1).tolist()}")
    print(f"补全额头 {int(occluded.sum())} 像素；刘海零件 {bx1-bx0}x{by1-by0} @ {entry['pos']}")


if __name__ == "__main__":
    main()
