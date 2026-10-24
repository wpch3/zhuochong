#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把发型参考模板图逐张"套准"到短发底图上。

为什么要这一步
--------------
7 张参考模板是 AI 一张张编辑出来的，就算提示词里反复写"身体保持不变"，
每张还是会带零点几个百分点的尺度/位移漂移（实测鞋底差 5px、袜筒差 3px）。
这点误差在整图上看不出来，但参考模板的用途是**按同一套坐标切件**——
切件靠的是"同一个像素位置对应同一个身体部位"，漂了就全错位。

所以这里不靠眼睛放过，而是解一个相似变换（等比缩放 + 平移），
把每张图的**膝盖以下**（裙摆之下只有腿、袜、鞋，任何发型和兜帽都不该动它）
对齐到底图，然后**只重采样一次**输出到底图画布。

判据
----
对齐后再量一遍"腿脚带差异率"，这就是 selfcheck 里那道闸的输入。
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import sys

import numpy as np
from PIL import Image

# 底图画布
CANVAS = (1024, 1536)
# 套准参照带：裙摆以下。上沿取 1100 是为了避开长发垂到胯的那一段。
BAND = (1100, 1520)


def magenta(arr: np.ndarray) -> np.ndarray:
    """洋红键底色掩膜。"""
    r, g, b = arr[..., 0], arr[..., 1], arr[..., 2]
    return (r > 150) & (b > 150) & (g < 110) & ((r - g) > 80) & ((b - g) > 80)


def silhouette(im: Image.Image) -> np.ndarray:
    return ~magenta(np.asarray(im.convert("RGB")).astype(np.int16))


def warp(src: Image.Image, scale: float, dx: float, dy: float) -> Image.Image:
    """把 src 按 (scale, dx, dy) 映射到底图画布，只重采样一次。

    out = scale * in + (dx, dy)  ⇒  in = (out - d) / scale
    """
    inv = 1.0 / scale
    return src.convert("RGB").transform(
        CANVAS,
        Image.AFFINE,
        (inv, 0.0, -dx * inv, 0.0, inv, -dy * inv),
        resample=Image.BICUBIC,
        fillcolor=(255, 0, 255),
    )


def band_cost(sil_a: np.ndarray, sil_b: np.ndarray) -> float:
    y0, y1 = BAND
    return float((sil_a[y0:y1] != sil_b[y0:y1]).mean())


def register(src: Image.Image, base_sil: np.ndarray, verbose: bool = False):
    """粗到细搜 (scale, dx, dy)，返回 (best_img, scale, dx, dy, cost)。"""
    w, h = src.size
    s0 = CANVAS[1] / float(h)  # 标称缩放：画布高之比

    best = None
    # 粗搜 → 细搜，每轮把步长减半、范围收窄
    ks, dxs, dys = 1.0, 0.0, 0.0
    for rnd, (kstep, krange, pstep, prange) in enumerate(
        [(0.004, 0.020, 4, 12), (0.002, 0.006, 2, 5), (0.001, 0.002, 1, 2)]
    ):
        cand = None
        kvals = np.arange(ks - krange, ks + krange + 1e-9, kstep)
        for k in kvals:
            for dx in range(int(dxs - prange), int(dxs + prange) + 1, pstep):
                for dy in range(int(dys - prange), int(dys + prange) + 1, pstep):
                    im = warp(src, s0 * k, dx, dy)
                    c = band_cost(silhouette(im), base_sil)
                    if cand is None or c < cand[0]:
                        cand = (c, k, dx, dy, im)
        _, ks, dxs, dys, bestim = cand
        best = cand
        if verbose:
            print(
                "      第%d轮  k=%.4f dx=%+d dy=%+d  腿脚剪影不合 %.3f%%"
                % (rnd + 1, ks, dxs, dys, cand[0] * 100)
            )
    c, k, dx, dy, im = best
    return im, s0 * k, dx, dy, c


def sha16(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for blk in iter(lambda: fh.read(1 << 20), b""):
            h.update(blk)
    return h.hexdigest()[:16]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--character", default="xiaoxun")
    ap.add_argument("--base", default=None)
    ap.add_argument("--dir", default=None)
    ap.add_argument("--verbose", action="store_true")
    a = ap.parse_args()

    root = os.path.join("characters", a.character, "design")
    base_path = a.base or os.path.join(root, "design_sheet_short.png")
    sheet_dir = a.dir or os.path.join(root, "sheets")

    base = Image.open(base_path).convert("RGB")
    if base.size != CANVAS:
        base = base.resize(CANVAS, Image.LANCZOS)
    base_sil = silhouette(base)
    base_arr = np.asarray(base).astype(np.int16)

    names = sorted(
        f for f in os.listdir(sheet_dir) if f.endswith(".png") and not f.endswith("_raw.png")
    )
    if not names:
        print("没有找到参考模板图：%s" % sheet_dir)
        return 1

    print("套准基准：%s  画布 %dx%d" % (base_path, CANVAS[0], CANVAS[1]))
    print("参照带：y %d~%d（裙摆以下，只有腿/袜/鞋）\n" % BAND)

    worst = 0.0
    entries = []
    base_bottom = int(np.nonzero(base_sil)[0].max())
    for n in names:
        p = os.path.join(sheet_dir, n)
        src = Image.open(p)
        raw = os.path.join(sheet_dir, n[:-4] + "_raw.png")
        if not os.path.exists(raw):
            src.save(raw)  # 留一份未套准的原件，便于回溯
        src = Image.open(raw)

        if a.verbose:
            print("  %s  原始 %dx%d" % (n, src.size[0], src.size[1]))
        im, scale, dx, dy, cost = register(src, base_sil, a.verbose)
        im.save(p)

        arr = np.asarray(im).astype(np.int16)
        leg = float((np.abs(arr - base_arr).max(axis=2) > 40)[BAND[0] : BAND[1]].mean()) * 100
        sil = silhouette(im)
        bottom = int(np.nonzero(sil)[0].max())
        worst = max(worst, leg)
        entries.append(
            {
                "file": n,
                "sha16": sha16(p),
                "scale": round(scale, 5),
                "dx": int(dx),
                "dy": int(dy),
                "leg_diff_pct": round(leg, 3),
                "sole_y": bottom,
            }
        )
        print(
            "  %-24s scale %.4f  dx %+3d dy %+3d   腿脚差 %5.2f%%  鞋底 y=%d"
            % (n, scale, dx, dy, leg, bottom)
        )

    man = {
        "_note": (
            "参考模板套准台账，由 tools/register_sheets.py 生成。"
            "sha16 绑死图片内容：换了图不重跑套准，selfcheck 的"
            "「参考模板套准到同一套身体坐标上」那一项就会红。"
            "leg_diff_pct = 膝盖以下（裙摆之下只有腿/袜/鞋）与短发底图的像素差异率，"
            "这一带任何发型和兜帽都不该动它。"
        ),
        "base": os.path.relpath(base_path).replace(os.sep, "/"),
        "canvas": list(CANVAS),
        "band": list(BAND),
        "leg_diff_max_pct": 3.0,
        "base_sole_y": base_bottom,
        "sheets": entries,
    }
    mp = os.path.join(sheet_dir, "manifest.json")
    with io.open(mp, "w", encoding="utf-8") as fh:
        json.dump(man, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    print("\n最差腿脚差异 %.2f%%（上限 %.1f%%）→ 台账 %s" % (worst, man["leg_diff_max_pct"], mp))
    return 0 if worst <= man["leg_diff_max_pct"] else 1


if __name__ == "__main__":
    sys.exit(main())
