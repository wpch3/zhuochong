#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""漫符（manpu）切件器：洋红底 AI 原图 → 按色卡重铺的特效贴图。

漫符 = 漫画里那套符号化的情绪记号（汗 / 怒りマーク 💢 / 暗雲 / ZZZ）。
正式名与分类见 docs/REFERENCE_NOTES.md 第二十六批。

和 make_star_eye_parts.py 的分工：
  · 那一个管「✨」——它是**散布**型特效，一张素材铺 8 个实例；
  · 这一个管「一个符号就是一张图」的那类，每种 1~2 个实例。

**几何与动法一律来自 design/effects.json（T43.2 / G117）**，本文件不持有任何
坐标/颜色字面量。加一种新漫符 = 表里加一条 + 放一张洋红底原图，不改这个脚本。

每一步在做什么
  1. 键出洋红：按「离底色的欧氏距离」算覆盖度，比按色相判稳 —— 漫符里有大片
     深色描边，只看 G 通道会把描边一起吃掉（star_eye 那边踩过）。
  2. 裁到内容包围盒 + 留边：AI 出图经常把符号顶到画框边上，直接缩放会切掉描边。
  3. **按色卡重铺颜色**（D19 / DC55）：AI 给的是**形状**，颜色一律不信 ——
     按亮度把每个像素映射到表里声明的 recolor 梯度上。梯度的每一站都必须是
     palette.json 里的颜色，所以出来的件天然过 check_assets 的色卡闸。
  4. 出 1× 与 @2x 两套（DC48：高清走末尾 @2x）。
  5. 写 manpu_parts.json 给 make_rig.py 用（和 star_eye_parts.json 同构）。
"""
from __future__ import annotations

import argparse
import io
import json
import os
import sys

import numpy as np
from PIL import Image

# 键色判据：和 make_star_eye_parts.py 同口径（那边实测过洋红底的噪声水平）
KEY_D_LO = 0.055        # 归一化距离 <= 这个数 = 纯底
KEY_D_HI = 0.260        # >= 这个数 = 纯内容；中间线性 = 抗锯齿边
MAGENTA_R, MAGENTA_G, MAGENTA_B = 150, 60, 150   # 「还是洋红」的判据阈值
CROP_MARGIN = 0.04      # 裁切后四周留白（占裁切边长的比例），护住描边
SOLID_A = 0.85          # 只有覆盖度高过这个的像素颜色才可信（最外圈半透明像素颜色不可信）


def key_alpha(rgb: np.ndarray, bg: np.ndarray) -> np.ndarray:
    """洋红底 → 覆盖度 0..1。用欧氏距离，深色描边也认得出。"""
    d = np.linalg.norm(rgb.astype(np.float64) - bg[None, None, :], axis=-1) / 441.67
    return np.clip((d - KEY_D_LO) / (KEY_D_HI - KEY_D_LO), 0.0, 1.0)


def bg_color(rgb: np.ndarray) -> np.ndarray:
    """取四条边的中位数当底色 —— 比假定 #FF00FF 稳（AI 出图的底会偏一点）。"""
    edge = np.concatenate([rgb[0, :, :], rgb[-1, :, :], rgb[:, 0, :], rgb[:, -1, :]])
    return np.median(edge, axis=0)


def left_magenta(rgb: np.ndarray, a: np.ndarray) -> int:
    """还剩多少个「看着仍是洋红」的不透明像素。>0 就是键没干净。"""
    r, g, b = rgb[..., 0].astype(int), rgb[..., 1].astype(int), rgb[..., 2].astype(int)
    m = (r - g > 60) & (b - g > 60) & (r > MAGENTA_R) & (b > MAGENTA_B)
    return int((m & (a > 0.5)).sum())


def parse_ramp(ramp):
    """[{"at":0.0,"hex":"#2C2939"}, ...] → (stops, colors) 两个 ndarray。"""
    stops = np.array([float(s["at"]) for s in ramp], dtype=np.float64)
    cols = np.array([[int(s["hex"][i:i + 2], 16) for i in (1, 3, 5)] for s in ramp],
                    dtype=np.float64)
    if not np.all(np.diff(stops) > 0):
        raise SystemExit("[manpu] recolor 的 at 必须严格递增")
    return stops, cols


def relay_colors(rgb: np.ndarray, a: np.ndarray, ramp) -> np.ndarray:
    """按亮度**聚类**把像素重铺到色卡上。

    为什么是聚类而不是「亮度归一化后插值」：第一版就是插值，结果 fx_anger 的红
    整个变成了淡粉（实测：红占 79.6% 的像素、亮度 76~78，而 p2=24 / p98=78，
    于是 t=(76−24)/54=0.96，被映到梯度顶端的白）。**平色占压倒多数时，
    百分位归一化会塌掉** —— 这类卡通符号恰恰就是大片平色。

    聚类的另一个好处：输出就是色卡上的**纯色**，不是插值出来的中间色，
    既符合 cel-shaded 的画风，也天然过 check_assets 的色卡闸。

    亮度统计只用覆盖度可信的像素（既有教训：最外圈半透明像素颜色不可信，
    可信 a>0.85）。抗锯齿边按最近簇取色，软硬过渡交给 alpha。
    """
    stops, cols = parse_ramp(ramp)
    k = len(cols)
    lum = (0.299 * rgb[..., 0] + 0.587 * rgb[..., 1] + 0.114 * rgb[..., 2])
    soft = a > SOLID_A
    if soft.sum() < 16:
        raise SystemExit("[manpu] 可信像素太少，键色八成出问题了")
    L = lum[soft]
    # 1D k-means（Lloyd）。初值取等分位，比随机初值稳定且可复现。
    c = np.percentile(L, np.linspace(5.0, 95.0, k))
    for _ in range(40):
        lab = np.abs(L[:, None] - c[None, :]).argmin(axis=1)
        new_c = np.array([L[lab == j].mean() if (lab == j).any() else c[j]
                          for j in range(k)])
        if np.allclose(new_c, c, atol=1e-4):
            c = new_c
            break
        c = new_c
    c = np.sort(c)           # 从暗到亮，对上 ramp 的顺序（parse_ramp 已查过 at 递增）
    lab_all = np.abs(lum[..., None] - c[None, None, :]).argmin(axis=-1)
    out = cols[lab_all]
    return out


def build_one(eff, redraw_dir, sprites_dir, report):
    src = os.path.join(redraw_dir, eff["source"])
    if not os.path.exists(src):
        return None
    im = Image.open(src).convert("RGB")
    rgb = np.asarray(im, dtype=np.uint8)
    bg = bg_color(rgb)
    a = key_alpha(rgb, bg)

    # --- 裁到内容包围盒 ---
    ys, xs = np.nonzero(a > 0.35)
    if len(xs) == 0:
        raise SystemExit(f"[manpu] {eff['id']}：键完什么都不剩，底色判错了？bg={bg}")
    x0, x1, y0, y1 = xs.min(), xs.max() + 1, ys.min(), ys.max() + 1
    side = max(x1 - x0, y1 - y0)
    pad = int(round(side * CROP_MARGIN))
    side += pad * 2
    cx, cy = (x0 + x1) // 2, (y0 + y1) // 2
    bx0, by0 = cx - side // 2, cy - side // 2
    # 越界时补洋红（而不是夹回画内）—— 夹回去会让符号偏心
    canvas = np.empty((side, side, 3), dtype=np.uint8)
    canvas[:, :] = bg.astype(np.uint8)
    sx0, sy0 = max(bx0, 0), max(by0, 0)
    sx1, sy1 = min(bx0 + side, rgb.shape[1]), min(by0 + side, rgb.shape[0])
    canvas[sy0 - by0:sy1 - by0, sx0 - bx0:sx1 - bx0] = rgb[sy0:sy1, sx0:sx1]

    ca = key_alpha(canvas, bg)
    crgb = relay_colors(canvas, ca, eff["recolor"])

    # --- 出 1× 与 @2x ---
    px = int(eff["sprite_px"])
    made = []
    for n, name in ((px, eff["sprite"]),
                    (px * 2, eff["sprite"].replace(".png", "@2x.png"))):
        rgba = np.dstack([crgb, ca * 255.0]).astype(np.uint8)
        out = Image.fromarray(rgba, "RGBA").resize((n, n), Image.LANCZOS)
        # 缩放后再核一次键色：缩小时洋红会被插值进边缘（check_assets 的键色垃圾闸）
        arr = np.asarray(out)
        leftover = left_magenta(arr[..., :3], arr[..., 3] / 255.0)
        if leftover:
            raise SystemExit(f"[manpu] {eff['id']} {name} 还剩 {leftover} 个洋红像素")
        out.save(os.path.join(sprites_dir, name))
        made.append(name)

    cover = float((ca > 0.5).sum()) / float(ca.size)
    report.setdefault("sources", {})[eff["id"]] = {
        "src": os.path.relpath(src),
        "src_size": list(im.size),
        "crop_side": int(side),
        "cover": round(cover, 4),
        "files": made,
    }
    return cover


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    ap.add_argument("--character", required=True)
    ap.add_argument("--form", required=True)
    a = ap.parse_args()

    base = os.path.join(a.root, "characters", a.character)
    sprites = os.path.join(base, "forms", a.form, "sprites")
    redraw = os.path.join(base, "design", "redraw")
    fx_path = os.path.join(base, "design", "effects.json")
    if not os.path.exists(fx_path):
        print(f"[manpu] 没有 {fx_path}，跳过")
        return 0
    with io.open(fx_path, encoding="utf-8") as f:
        table = json.load(f)

    # 只处理「一个符号一张图」那类（表里有 source 字段的）。
    # ✨ 那种散布型没有 source，归 make_star_eye_parts.py。
    effs = [e for e in table["effects"] if e.get("source")]
    if not effs:
        print("[manpu] effects.json 里没有带 source 的特效组，跳过")
        return 0

    bp = os.path.join(sprites, "body_parts.json")
    with io.open(bp, encoding="utf-8") as f:
        body = json.load(f)

    report: dict = {"schema_version": "1.0", "effects": []}
    for e in effs:
        box_id = e.get("anchor", {}).get("box")
        if not box_id:
            # 不给兜底默认值：`.get(..., "seg_head")` 等于在源码里藏第二份配置，
            # 正是 G117 要消灭的东西。表缺字段就当场停。
            raise SystemExit(f"[manpu] {e['id']}：effects.json 缺 anchor.box")
        box = next(p for p in body["parts"] if p["id"] == box_id)
        bx, by = box["pos"]
        bw, bh = box["size"]
        cover = build_one(e, redraw, sprites, report)
        if cover is None:
            print(f"[manpu] 缺原图 {e['source']}，{e['id']} 整组跳过", file=sys.stderr)
            continue
        inst = []
        for i, it in enumerate(e["instances"], 1):
            inst.append({
                "id": f"fx_{e['id']}_{i}",
                "pos": [int(round(bx + it["u"] * bw)), int(round(by + it["v"] * bh))],
                "scale": e["size_class"][it["size"]],
                "size_class": it["size"],
                "rot_deg": it["rot_deg"],
                "freq": it["freq"], "phase": it["phase"],
            })
        report["effects"].append({
            "id": e["id"], "file": f"sprites/{e['sprite']}",
            "size": [e["sprite_px"], e["sprite_px"]],
            "instances": inst,
        })
        print(f"[manpu] {e['id']}: {e['sprite']} {e['sprite_px']}px "
              f"× {len(inst)} 片（覆盖 {cover:.0%}）")

    out = os.path.join(sprites, "manpu_parts.json")
    with io.open(out, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print(f"写出 {out}：{len(report['effects'])} 组")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
