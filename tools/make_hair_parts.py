#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""make_hair_parts.py - 把头发里"能单独动"的部分拆出来。

第一件：**呆毛**（头顶那根翘起来的发丝）。
它整根都露在头部剪影之外，背后没有任何别的零件 —— 所以可以干净地切下来，
不需要补画，是全身上下最便宜的一件"真·可动零件"。
（规格 H3 要求：呆毛参与物理摆动与组层级。）

做法：
  1. 逐行数不透明像素：发丝那几行只有十几个像素，到了头顶圆弧会突然涨到几十上百，
     这一跳就是切线。
  2. 切线以上整根取走，再往下吃 ov 行当"根部"（让它长在头上，不会浮空）。
  3. 从 seg_head.png 里抹掉切线以上的发丝（背后是空的，抹掉不留洞），
     根部那几行保留不动，正好被呆毛零件盖住。
  4. 把新零件登记进 sprites/body_parts.json，make_rig.py 会自动接线。

幂等：再跑一次会发现头顶已经没有发丝，直接跳过。

用法：
  ~/.imgenv/bin/python tools/make_hair_parts.py --character xiaoxun --form teen
"""
from __future__ import annotations
import argparse, json, os
from collections import deque

import numpy as np
from PIL import Image


def flood(mask, seeds):
    out = np.zeros(mask.shape, bool)
    q = deque()
    for s in seeds:
        if mask[s] and not out[s]:
            out[s] = True
            q.append(s)
    while q:
        y, x = q.popleft()
        for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (1, -1), (-1, 1), (-1, -1)):
            v, u = y + dy, x + dx
            if 0 <= v < mask.shape[0] and 0 <= u < mask.shape[1] and mask[v, u] and not out[v, u]:
                out[v, u] = True
                q.append((v, u))
    return out


def find_cut(counts, dome_factor=3.0, min_rows=6):
    """找发丝与头顶圆弧的分界行。"""
    thin = [c for c in counts[:min_rows] if c > 0]
    if not thin:
        return None
    base = max(4, int(np.median(thin)))
    for y in range(min_rows, len(counts)):
        if counts[y] > base * dome_factor and counts[y] > 30:
            return y
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--character", required=True)
    ap.add_argument("--form", required=True)
    ap.add_argument("--root", default=".")
    ap.add_argument("--overlap", type=int, default=12, help="根部往下多吃几行")
    args = ap.parse_args()

    base = os.path.join(args.root, "characters", args.character, "forms", args.form)
    sp = os.path.join(base, "sprites")
    head_path = os.path.join(sp, "seg_head.png")
    head = Image.open(head_path).convert("RGBA")
    a = np.array(head)
    al = a[..., 3]
    counts = [int((al[y] > 8).sum()) for y in range(al.shape[0])]

    y_cut = find_cut(counts)
    if y_cut is None or y_cut < 6:
        print("头顶没有露在轮廓外的发丝（可能已经拆过），跳过")
        return

    # 呆毛 = 切线以上那一团（连通），再加上根部 overlap 行
    top = al > 8
    seeds = [(y, x) for y in range(y_cut) for x in range(al.shape[1]) if top[y, x]]
    strand = flood(top & (np.arange(al.shape[0])[:, None] < y_cut), seeds)
    cols = np.nonzero(strand.any(0))[0]
    if cols.size == 0:
        print("没找到发丝连通块，跳过")
        return
    x0, x1 = int(cols.min()), int(cols.max())
    # 根部：切线下面 overlap 行里、发丝所在列附近的像素，一起带走当作根
    root_band = np.zeros_like(strand)
    rx0, rx1 = max(0, x0 - 2), min(al.shape[1], x1 + 3)
    root_band[y_cut:y_cut + args.overlap, rx0:rx1] = top[y_cut:y_cut + args.overlap, rx0:rx1]
    piece = strand | root_band

    ys, xs = np.nonzero(piece)
    py0, py1, px0, px1 = int(ys.min()), int(ys.max()) + 1, int(xs.min()), int(xs.max()) + 1
    out = np.zeros((py1 - py0, px1 - px0, 4), np.uint8)
    sub = a[py0:py1, px0:px1]
    sub_m = piece[py0:py1, px0:px1]
    out[..., :3] = np.where(sub_m[..., None], sub[..., :3], 0)
    # 根部渐隐：最下面几行慢慢变透明，接在头上不会出现硬切口
    fade = np.ones(out.shape[0], float)
    f0 = max(0, (y_cut + args.overlap - 6) - py0)
    for i, y in enumerate(range(py0, py1)):
        if y >= y_cut + args.overlap - 6:
            fade[i] = max(0.0, 1.0 - (y - (y_cut + args.overlap - 6)) / 6.0)
    out[..., 3] = (np.where(sub_m, sub[..., 3], 0) * fade[:, None]).astype(np.uint8)
    Image.fromarray(out).save(os.path.join(sp, "hair_ahoge.png"))

    # 头上抹掉切线以上的发丝（背后是透明背景，抹掉不留洞）
    head_new = a.copy()
    head_new[..., 3] = np.where(strand, 0, head_new[..., 3])
    head_new[..., :3] = np.where(head_new[..., 3:4] > 0, head_new[..., :3], 0)
    Image.fromarray(head_new).save(head_path)

    # 登记到 body_parts.json，make_rig.py 会自动接线
    bp_path = os.path.join(sp, "body_parts.json")
    bp = json.load(open(bp_path, encoding="utf-8"))
    head_pos = next(p["pos"] for p in bp["parts"] if p["id"] == "seg_head")
    entry = {
        "id": "hair_ahoge",
        "file": "sprites/hair_ahoge.png",
        "pos": [head_pos[0] + px0, head_pos[1] + py0],
        "size": [px1 - px0, py1 - py0],
        "group": "head",
        "layer": 190,
        "note": "呆毛：整根露在剪影外，可以无损切下来；根在底边，用 curve=root 摆动",
    }
    bp["parts"] = [p for p in bp["parts"] if p["id"] != "hair_ahoge"] + [entry]
    bp.setdefault("patches", []).append("呆毛已拆成独立部件（make_hair_parts.py）")
    json.dump(bp, open(bp_path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)

    print(f"呆毛切线 y={y_cut}，零件 {px1 - px0}x{py1 - py0} @ 身体坐标 {entry['pos']}")
    print("已写出 sprites/hair_ahoge.png，并从 seg_head.png 抹掉原来的发丝")


if __name__ == "__main__":
    main()
