#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""make_brow_parts.py - 把两条眉毛从脸上切下来，变成能挑能皱的独立零件。

前提：先跑过 make_bangs_parts.py（额头补全后，眉毛才是完整的两条）。

为什么还要再生一张图：
  眉毛底下压着的那块额头皮肤，原画同样没有。所以还是老办法——
  让 AI 把"同一张脸去掉眉毛"再画一遍，用它来补眉毛挪走后露出来的皮肤。
  两张图用虹膜质心对齐（AI 不保构图），只动眉毛那一小块。

切法用的是 **alpha 抠像（matte）** 而不是硬掩膜：
  眉毛边缘本来就是半透明的笔触，硬切会出锯齿。
  a = 「有眉的脸」和「没眉的脸」的差 / 满值差；
  眉毛颜色再按 C = (src - (1-a)*skin) / a 解混，拿到干净的笔触色。
  这样 眉(a) 叠回 补好皮肤的脸(1-a) = 原来的脸，**静止画面一个像素都不变**。

输入：sprites/seg_head.png（已补额头）+ 一张"同构图、无眉毛"的重绘图
输出：sprites/brow_l.png、brow_r.png、seg_head.png（眉位置换成皮肤）、brow_report.json

用法：
  ~/.imgenv/bin/python tools/make_brow_parts.py --character xiaoxun --form teen \
      --redraw characters/xiaoxun/design/redraw/head_nobrows.png
"""
from __future__ import annotations
import argparse, json, os, sys
from collections import deque

import numpy as np
from PIL import Image, ImageFilter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from make_bangs_parts import components, iris_centers, dilate   # noqa: E402

SCALE = 3


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--character", required=True)
    ap.add_argument("--form", required=True)
    ap.add_argument("--redraw", required=True, help="同构图的无眉毛重绘图（洋红底）")
    ap.add_argument("--root", default=".")
    args = ap.parse_args()

    base = os.path.join(args.root, "characters", args.character, "forms", args.form)
    sp = os.path.join(base, "sprites")
    head = Image.open(os.path.join(sp, "seg_head.png")).convert("RGBA")
    W, H = head.size
    ha = np.array(head).astype(int)
    hrgb, hal = ha[..., :3], ha[..., 3]

    # --- 1) 对齐：相似变换（缩放 + **旋转** + 平移）
    #     这张重绘图两只眼睛差了 30px 高度 —— 只缩放不转，眉毛位置会错十几像素，
    #     第一版就是这么把"眉毛"找到发际线上去的。
    src_big = Image.new("RGBA", (W, H), (255, 0, 255, 255))
    src_big.alpha_composite(head)
    src_big = src_big.convert("RGB").resize((W * SCALE, H * SCALE), Image.LANCZOS)
    gen = Image.open(args.redraw).convert("RGB")
    (sx0, sy0, _), (sx1, sy1, _) = iris_centers(np.array(src_big).astype(int))
    (gx0, gy0, _), (gx1, gy1, _) = iris_centers(np.array(gen).astype(int))
    import math
    vs = (sx1 - sx0, sy1 - sy0)
    vg = (gx1 - gx0, gy1 - gy0)
    k = math.hypot(*vs) / math.hypot(*vg)
    th = math.atan2(vs[1], vs[0]) - math.atan2(vg[1], vg[0])
    cs = ((sx0 + sx1) / 2, (sy0 + sy1) / 2)
    cg = ((gx0 + gx1) / 2, (gy0 + gy1) / 2)
    # PIL 的 AFFINE 要的是"输出→输入"的逆映射
    ia, ib = math.cos(-th) / k, -math.sin(-th) / k
    ic_, id_ = math.sin(-th) / k, math.cos(-th) / k
    e = cg[0] - (ia * cs[0] + ib * cs[1])
    f = cg[1] - (ic_ * cs[0] + id_ * cs[1])
    big = gen.transform(src_big.size, Image.AFFINE, (ia, ib, e, ic_, id_, f),
                        resample=Image.BICUBIC, fillcolor=(255, 0, 255))
    dx, dy = cs[0] - cg[0] * k, cs[1] - cg[1] * k
    skin = np.array(big.resize((W, H), Image.LANCZOS)).astype(int)
    res = iris_centers(np.array(big).astype(int))
    err = max(math.hypot(res[i][0] - (sx0, sx1)[i], res[i][1] - (sy0, sy1)[i])
              for i in (0, 1))
    print(f"对齐残差（两只虹膜最大偏差）{err:.1f}px（3 倍坐标系）")
    if err > 12:
        raise SystemExit("对齐残差太大，重绘图构图偏得厉害，重新生图")

    # --- 2) 肤色配准（额头上"两张图都是皮肤"的地方）
    solid = hal > 100
    # 眉毛带：按虹膜位置和瞳距推，不写死像素
    #   上界 = 虹膜上方 0.80 个瞳距（再往上就是发际线了）
    #   下界 = 虹膜上方 0.28 个瞳距（再往下就吃到上睫毛）
    iris_y = min(sy0, sy1) / SCALE
    eye_d = abs(sx1 - sx0) / SCALE
    y_lo, y_hi = int(iris_y - 0.80 * eye_d), int(iris_y - 0.28 * eye_d)
    zone = np.zeros((H, W), bool)
    zone[max(0, y_lo):y_hi, :] = True
    warm_s = (hrgb[..., 0] > hrgb[..., 2] + 18) & (hrgb[..., 0] > 200)
    warm_g = (skin[..., 0] > skin[..., 2] + 18) & (skin[..., 0] > 200)
    band = solid & zone & warm_s & warm_g
    # 只配「中位数」，不配方差：额头是平涂的，重绘图比原图更平，
    # 按 std 算增益会被钳到 1.25（实测），等于把重绘皮肤做了次对比度拉伸，
    # 后面解混出来的眉色就飘成灰紫（#887898），过不了色卡。
    gain, off = np.ones(3), np.zeros(3)
    for c in range(3):
        a_v = hrgb[..., c][band].astype(float)
        b_v = skin[..., c][band].astype(float)
        if len(a_v) > 50:
            off[c] = float(np.median(a_v) - np.median(b_v))
    skin = np.clip(skin * gain + off, 0, 255)

    # --- 3) 找眉毛：**不靠重绘图找**（AI 构图总有残差），而是拿脸自己比。
    #     额头是平涂的，先估一张"本地皮肤底色"（只用皮肤像素做中值模糊），
    #     再看谁比底色暗出一截 —— 平的额头上，只有眉毛会跳出来。
    med_src = Image.fromarray(np.where(
        (solid & warm_s)[..., None], hrgb, np.median(hrgb[solid & warm_s], axis=0)
    ).round().astype(np.uint8))
    est = np.array(med_src.filter(ImageFilter.MedianFilter(9))
                   .filter(ImageFilter.MedianFilter(9))).astype(int)
    # 只认"比底色**暗**"的像素：眉毛是压在皮肤上的深色笔触。
    # 用绝对差会把笔触外侧那圈偏亮的描边也吃进来，挑眉时就会拖一条白边出来。
    lum = lambda a: 0.299 * a[..., 0] + 0.587 * a[..., 1] + 0.114 * a[..., 2]
    diff = np.clip(lum(est) - lum(hrgb), 0, 255)
    # 注意：眉毛本身比 200 暗，**不能**要求候选像素是"皮肤"。
    skin_m = solid & warm_s

    # 候选范围要卡在「脸的内部」，不能只是「离皮肤近」：
    #   鲸鱼发卡就贴在脸左边，dilate(skin,7) 会把它整只圈进来，
    #   结果眉毛零件里带出来半只鲸鱼（2026-10-12 实测）。
    #   做法 = 取最大的一块皮肤连通域 → 把里面的洞（眉毛本身就是洞）填上 → 外扩 2px。
    face_blobs = components(skin_m, 200)
    face = np.zeros((H, W), bool)
    if face_blobs:
        for y, x in max(face_blobs, key=len):
            face[y, x] = True
    holes = np.zeros((H, W), bool)
    for blob in components(~face, 1):
        ys_ = [q[0] for q in blob]
        xs_ = [q[1] for q in blob]
        if min(ys_) > 0 and max(ys_) < H - 1 and min(xs_) > 0 and max(xs_) < W - 1:
            for y, x in blob:
                holes[y, x] = True          # 不挨边框的空洞 = 脸内部的五官
    near = dilate(face | holes, 2)
    dgen = np.clip(lum(skin) - lum(hrgb), 0, 255)   # 比"没眉毛的重绘脸"暗多少
    # 眉毛是**暖褐色**（R 明显大于 B），额头上零星的发丝是冷紫灰（R≈B）——先按颜色筛一遍
    # 两套判据分工：
    #   找种子 —— 要暖褐色（R 比 B 大），这样不会把发丝当成眉毛；
    #   长回完整笔触 —— 只要"比底色暗"就行，因为眉毛上缘压着一道冷灰色描边，
    #   要是也卡颜色，那道描边会被留在脸上，挑眉时就出现"两条眉毛"。
    cand = solid & zone & near & (diff > 5)
    cand_seed = cand & ((hrgb[..., 0] - hrgb[..., 2]) > 14)

    # 再按"形状"定种子：眉毛是又长又扁的一条，横向开运算之后只剩它；
    # 竖着的碎发会被抹掉。（这是本工具最关键的一步，没有它会把太阳穴的发丝一起切走。）
    def hopen(m, r):
        er = m.copy()
        for k in range(1, r + 1):
            er &= np.roll(m, k, axis=1) & np.roll(m, -k, axis=1)
        out = er.copy()
        for k in range(1, r + 1):
            out |= np.roll(er, k, axis=1) | np.roll(er, -k, axis=1)
        return out & m

    sides = {"l": [], "r": []}
    for pts in components(hopen(cand_seed, 2), 30):
        cx = float(np.mean([q[1] for q in pts]))
        sides["l" if cx < W / 2 else "r"].append(pts)
    # 每边只留**最大**的一条：鲸鱼发卡边上也能凑出一小块横向的暖色种子，
    # 留着它行窗就会从眉毛一路开到发卡（眉毛零件里带出半只鲸鱼）。
    for side in ("l", "r"):
        if len(sides[side]) > 1:
            sides[side] = [max(sides[side], key=len)]
    if not sides["l"] or not sides["r"]:
        if os.path.exists(os.path.join(sp, "brow_l.png")):
            print("脸上已经没有眉毛了（之前拆过），跳过")
            return
        raise SystemExit(f"眉毛种子不齐（左 {len(sides['l'])} 右 {len(sides['r'])}），"
                         "检查重绘图或眉毛带范围")

    comps = []
    for side in ("l", "r"):
        allp = [q for g in sides[side] for q in g]
        # 行窗比种子多放 4 行：眉毛上下缘是软笔触，种子（横向开运算后）只剩笔画中段，
        # 只放 2 行会把软边切掉 —— 右眉一度只剩 10px 高，过不了 check_assets 的尺寸关。
        r0, r1 = min(q[0] for q in allp) - 4, max(q[0] for q in allp) + 4
        win = np.zeros((H, W), bool)
        win[max(0, r0):r1 + 1, :] = True
        grow = cand & win                       # 从种子长回完整笔触，但不许跑出这条带
        seen = np.zeros((H, W), bool)
        dq = deque(allp)
        for q in allp:
            seen[q] = True
        while dq:
            y, x = dq.popleft()
            for dy2 in (-1, 0, 1):
                for dx2 in (-1, 0, 1):
                    v, u = y + dy2, x + dx2
                    if 0 <= v < H and 0 <= u < W and grow[v, u] and not seen[v, u]:
                        seen[v, u] = True
                        dq.append((v, u))
        # 长完还要去掉「冷色」像素：鲸鱼发卡是蓝的（B-R>40），一旦和眉毛连上，
        # 整只鲸鱼都会被当成眉毛长进来。眉毛上缘那道冷灰描边 B-R≈8，所以阈值取 22：
        # 留得住描边，拦得住发卡。去掉之后只保留还压着种子的那一块连通域。
        cold = (hrgb[..., 2] - hrgb[..., 0]) > 22
        # 再按「重绘图到底擦掉了什么」剪一刀：额头上那几根淡紫发丝在无眉图里
        # 原样还在（dgen≈0），只有眉毛被擦掉（dgen 几十）。对齐残差 0.2px 时这刀很准。
        seen &= ~cold & (dgen > 4)
        # 最后再按「离笔画有多远」收一刀：发卡那边还剩十几个像素会跟着眉毛一起动，
        # 它们离种子笔画 20 行以外。种子外扩 7px 就是眉毛的软边范围。
        seed_m = np.zeros((H, W), bool)
        for q in allp:
            seed_m[q] = True
        seen &= dilate(seed_m, 7)
        seedset = set(allp)
        keep = np.zeros((H, W), bool)
        for blob in components(seen, 1):
            if any(q in seedset for q in blob):
                for y, x in blob:
                    keep[y, x] = True
        seen = keep
        pts = [(int(y), int(x)) for y, x in zip(*np.nonzero(seen))]
        # 对齐没对上的话，这块区域在重绘图里还是眉毛，两张图就不会有像样的差。
        # 判据用「最暗的一成有多暗」而不是「多少像素超过阈值」：眉毛笔触边缘本来
        # 就软，软边占比会随重绘图的轻重变化（实测 0.24~0.45 都是对的），
        # 但只要对上了，笔触中心的差一定很大（实测 p90≈66）。
        dvals = np.array([dgen[y, x] for y, x in pts])
        frac = float((dvals > 14).mean()) if len(dvals) else 0.0
        p90 = float(np.percentile(dvals, 90)) if len(dvals) else 0.0
        if p90 < 35 or frac < 0.15:
            raise SystemExit(f"{side} 眉和无眉重绘图差异太小（p90={p90:.0f} 占比={frac:.2f}），"
                             "对齐可能不对")
        comps.append(pts)
    # 笔画外再带 2px 的软边：抗锯齿那一圈本来就是眉毛的一部分，
    # 不带的话右眉只剩 11px 高（check_assets 的最小边长是 12，判为抠错）。
    # 这圈像素 alpha 算出来接近 0，叠回去对静止画面没有影响。
    comps_m = []
    for pts in comps:
        m1 = np.zeros((H, W), bool)
        for y, x in pts:
            m1[y, x] = True
        comps_m.append(dilate(m1, 2) & solid)
    mask = np.zeros((H, W), bool)
    for m1 in comps_m:
        mask |= m1

    # --- 4) alpha 抠像 + 解混
    # alpha 怎么定？单张图里 a 和眉色是乘在一起的，分不开（a 大一点、颜色浅一点
    # 合成结果一样）。所以**以色卡上的眉毛褐为准**反解 a：
    #     src = a*C0 + (1-a)*S   →   a = <S-src, S-C0> / |S-C0|^2
    # 这样切出来的颜色天然落在色卡上（不用这条约束时主色会飘成 #987888，
    # 离色卡 88，直接被 check_assets 拦下）。
    pal_path = os.path.join(args.root, "characters", args.character, "design", "palette.json")
    c0 = (0x78, 0x48, 0x48)
    if os.path.exists(pal_path):
        for c in json.load(open(pal_path, encoding="utf-8"))["colors"]:
            if c["name"].startswith("眉毛褐"):
                h = c["hex"].lstrip("#")
                c0 = tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))
    C0 = np.array(c0, float)
    dpix = skin - hrgb                       # S - src
    dref = skin - C0                         # S - C0
    alpha = np.clip((dpix * dref).sum(-1) / np.maximum((dref * dref).sum(-1), 1e-6),
                    0, 1) * mask
    a3 = alpha[..., None]
    # 解混：src = a*眉色 + (1-a)*皮肤  →  眉色 = (src - (1-a)*皮肤) / a
    with np.errstate(divide="ignore", invalid="ignore"):
        unmix = np.where(a3 > 0.03, (hrgb - (1 - a3) * skin) / np.maximum(a3, 1e-6), hrgb)
    unmix = np.clip(unmix, 0, 255)

    # 脸：掩膜内**整块**换成重绘的皮肤（不是按 alpha 混，那样会留一层眉毛鬼影，
    # 而且叠回去会偏黑 —— 第一版就是这个错）。
    # 叠加时 a*眉色 + (1-a)*皮肤 = 原来的脸，所以静止画面一个像素不变。
    newhead = np.array(head)
    for c in range(3):
        newhead[..., c] = np.where(mask, skin[..., c].round().astype(np.uint8),
                                   newhead[..., c])

    out, report = [], []
    cx = [np.mean([p[1] for p in pts]) for pts in comps]
    order = np.argsort(cx)          # 画面左边那条 = 角色的右眉，按 Live2D 习惯仍叫 l/r（画面左右）
    for side, idx in zip(("l", "r"), order):
        sub = comps_m[idx]
        ys, xs = np.nonzero(sub)
        y0, y1, x0, x1 = int(ys.min()), int(ys.max()) + 1, int(xs.min()), int(xs.max()) + 1
        rgba = np.zeros((y1 - y0, x1 - x0, 4), np.uint8)
        rgba[..., :3] = unmix[y0:y1, x0:x1].round().astype(np.uint8)
        rgba[..., 3] = (alpha[y0:y1, x0:x1] * sub[y0:y1, x0:x1] * 255).round().astype(np.uint8)
        name = f"brow_{side}.png"
        Image.fromarray(rgba).save(os.path.join(sp, name))
        out.append((side, name, x0, y0, x1 - x0, y1 - y0, int(sub.sum())))
        report.append({"side": side, "box": [x0, y0, x1 - x0, y1 - y0],
                       "px": int(sub.sum()), "max_alpha": int(rgba[..., 3].max())})

    Image.fromarray(newhead).save(os.path.join(sp, "seg_head.png"))

    # --- 5) 登记零件
    bp_path = os.path.join(sp, "body_parts.json")
    bp = json.load(open(bp_path, encoding="utf-8"))
    hx, hy = next(p["pos"] for p in bp["parts"] if p["id"] == "seg_head")
    keep = [p for p in bp["parts"] if not p["id"].startswith("brow_")]
    for i, (side, name, x0, y0, w, h, _px) in enumerate(out):
        keep.append({
            "id": f"brow_{side}", "file": f"sprites/{name}",
            "pos": [hx + x0, hy + y0], "size": [w, h],
            "group": "head", "layer": 236 + i,   # 见 make_rig.py 的 FACE_LAYER：两只眼各占 216~225 / 226~235
            "note": "眉毛：alpha 抠像切出，底下的额头皮肤由 AI 重绘补全（挑眉时自动滑进刘海底下）",
        })
    bp["parts"] = keep
    note = "眉毛已拆件，眉下皮肤由 AI 重绘补全（make_brow_parts.py）"
    if note not in bp.setdefault("patches", []):
        bp["patches"].append(note)
    json.dump(bp, open(bp_path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    json.dump({"redraw": args.redraw,
               "align": {"scale": round(float(k), 4), "dx": round(float(dx), 1),
                         "dy": round(float(dy), 1)},
               "skin_gain": [round(float(v), 4) for v in gain],
               "skin_offset": [round(float(v), 2) for v in off],
               "brows": report},
              open(os.path.join(sp, "brow_report.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    for side, name, x0, y0, w, h, px in out:
        print(f"眉 {side}: {w}x{h} @ seg_head({x0},{y0})  {px} 像素 → {name}")
    print(f"对齐 scale={k:.4f} 平移=({dx:.1f},{dy:.1f}) 肤色 gain={np.round(gain,3).tolist()}")


if __name__ == "__main__":
    main()
