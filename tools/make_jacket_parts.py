#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""make_jacket_parts.py —— 外套前襟下摆的「裾断面の影」：T45.12，2026-10-17。

要解决什么
----------
服装组件化的第 3 项（第 1 项裙摆两段活布 T45.9、第 2 项裙子里布 T45.11）。
外套的前襟下摆现在和躯干烘焙在一张图里，身体怎么动它都跟着刚性平移，
看着像一块贴在身上的硬壳。

教程口径（查过才动手，详见 docs/REFERENCE_NOTES.md 第三十八批）
--------------------------------------------------------------
  · note.com/majohope（モデリング記録）：
      「上着の揺れ。**少し重い素材のイメージなので、あまり揺らさないようにした**」
      ⇒ 外套的摆幅必须**明显小于**裙摆和头发。
      裾の層順是「裾の上の線 ＞ 足を消すマスク ＞ **裾断面の影** ＞ 裾ベース」
      ⇒ 下摆底下要垫一层**断面的影**，布一掀就看见厚度。
  · nnwarks.com/live2d_page2（注意点）：
      「腕より後ろの服パーツ…個別に揺らすのは**非推奨**。**境目が飛び出しがち**」
      ⇒ 不要把前襟整片切出来单独摆（我们原画是烘焙的，切出来必然留洞）；
        摆动用躯干上的网格形变器做，接缝就不存在。
  · shiroikarasu.net（拆件三原则）：轮廓要往邻接件底下多伸一点做「のりしろ」。

所以这里做的是
--------------
**不切件**：下摆的摆动交给躯干上的网格形变器 `jacket_hem_x`（make_rig 生成），
只推下摆那几行、只推前襟那两片的列，中间开襟露出来的衬衫/裙腰基本不动。
本工具负责**量出那几行那几列**（下摆带的上下沿、两片前襟的列区间），
写成 `jacket_parts.json` 给 make_rig 用 —— 形态专属的数字不许写进共用的生成器。

★ 试过但**去掉了**的一层：教程里下摆的层顺是
  「裾の上の線 ＞ 足を消すマスク ＞ **裾断面の影** ＞ 裾ベース」，
  于是第一版照着做了一张"断面影"（下摆带复制 + 压暗，放在躯干后面）。
  **实测它根本不会露出来**：摆动是网格形变（布在拉伸），不是整片平移，
  躯干的轮廓几乎没有"让开"的地方 —— 推到参数上限也只露出 **9 个像素**。
  那张图是给"下摆是独立一片、整片平移"的模型用的，和本实现不是一回事。
  留着就是每一轮都要重算、要走闸、要占 @2x 的死重，所以删掉，只留几何。
  （判断方法记在 LESSONS：照搬教程的层结构之前，先量它在你的实现里露不露得出来。）

输出：`sprites/jacket_parts.json`（下摆几何：带的上下沿 + 两片前襟的列区间）
"""
from __future__ import annotations

import argparse
import json
import os
import sys

try:
    from PIL import Image
    import numpy as np
except ImportError:  # pragma: no cover
    print("需要 pillow 与 numpy：python3 -m venv ~/.imgenv && ~/.imgenv/bin/pip install pillow numpy",
          file=sys.stderr)
    raise

HEM_FRAC = 0.075      # 下摆带占躯干高度的比例（teen 501px ⇒ 38px）
DEEP_FRAC = 0.18      # 「垂到多低才算下摆列」：底边在最低点往上 18% 躯干高之内
GAP_MIN = 5           # 两片前襟之间至少隔这么多列
PANEL_MIN_FRAC = 0.08 # 一片前襟至少占躯干宽度的 8%，否则是碎点
COLOR_TOL = 60        # 外套色的曼哈顿容差


def palette_color(root: str, character: str, name: str) -> np.ndarray:
    p = os.path.join(root, "characters", character, "design", "palette.json")
    with open(p, encoding="utf-8") as f:
        for c in json.load(f)["colors"]:
            if c.get("name", "").strip() == name:          # ★ 精确相等，不许子串匹配
                h = c["hex"].lstrip("#")
                return np.array([int(h[i:i + 2], 16) for i in (0, 2, 4)])
    raise SystemExit(f"[make_jacket_parts] 色卡里没有「{name}」这一项")


def find_panels(a: np.ndarray, coat: np.ndarray):
    """找出前襟下摆：返回 (panels, bottom_of_column, band_top, band_bottom)。

    判据是「这一列的外套色垂到了多低」—— 前襟下摆垂到腰下，
    而中间开襟那段外套（领口、门襟上段）停在高处，不会被选中。
    """
    al = a[..., 3]
    rgb = a[..., :3]
    h, w = al.shape
    solid = al > 128
    white = solid & (np.abs(rgb - coat).sum(2) < COLOR_TOL)
    bot = np.full(w, -1)
    for x in range(w):
        ys = np.nonzero(white[:, x])[0]
        if ys.size:
            bot[x] = ys[-1]
    if not (bot > 0).any():
        raise SystemExit("[make_jacket_parts] 躯干图里找不到外套色")
    deep_thr = bot.max() - DEEP_FRAC * h
    cols = np.nonzero(bot > deep_thr)[0]
    if cols.size == 0:
        raise SystemExit("[make_jacket_parts] 找不到垂到腰下的前襟列")
    panels, run = [], [int(cols[0])]
    for x in cols[1:]:
        if x - run[-1] > GAP_MIN:
            panels.append((run[0], run[-1]))
            run = []
        run.append(int(x))
    panels.append((run[0], run[-1]))
    panels = [p for p in panels if p[1] - p[0] + 1 >= PANEL_MIN_FRAC * w]
    if len(panels) < 2:
        raise SystemExit(f"[make_jacket_parts] 只找到 {len(panels)} 片前襟（应当是左右两片）")
    hem_h = max(4, int(round(h * HEM_FRAC)))
    band_bottom = int(max(bot[p[0]:p[1] + 1].max() for p in panels))
    band_top = int(min(bot[p[0]:p[1] + 1].min() for p in panels)) - hem_h
    return panels, bot, max(0, band_top), band_bottom, hem_h


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--character", required=True)
    ap.add_argument("--form", required=True)
    ap.add_argument("--root", default=".")
    args = ap.parse_args()

    base = os.path.join(args.root, "characters", args.character, "forms", args.form)
    spr = os.path.join(base, "sprites")
    bp_path = os.path.join(spr, "body_parts.json")
    if not os.path.exists(bp_path):
        raise SystemExit(f"[make_jacket_parts] 缺少 {bp_path}（先跑 make_body_parts.py）")
    with open(bp_path, encoding="utf-8") as f:
        bp = json.load(f)
    torso = next(p for p in bp["parts"] if p["id"] == "seg_torso")
    coat = palette_color(args.root, args.character, "外套主体")

    a = np.asarray(Image.open(os.path.join(spr, "seg_torso.png")).convert("RGBA")).copy()
    panels, bot, band_top, band_bottom, hem_h = find_panels(a, coat)
    width = [p[1] - p[0] + 1 for p in panels]
    print(f"前襟 {len(panels)} 片：{[(p[0], p[1]) for p in panels]}（宽 {width} 列）")
    print(f"下摆带局部 y={band_top}..{band_bottom}（带高 {hem_h} = 躯干高的 {HEM_FRAC:.1%}）")
    print(f"两片之间的空当 {panels[1][0] - panels[0][1]} 列 —— 中间的衬衫/裙腰不许跟着摆")

    out = {
        "schema_version": "1.0",
        "source": "sprites/seg_torso.png 上按色卡「外套主体」量出来的前襟下摆几何",
        "note": "外套前襟下摆：摆动由躯干上的网格形变器 jacket_hem_x 做（见 make_rig.py）。"
                "不切件 —— 教程明确不建议把腕より後ろ的衣服单独切出来摆"
                "（境目が飛び出しがち），而且本项目的原画是烘焙的，切出来会留洞。",
        "hem": {
            "torso_pos": list(torso["pos"]),
            "torso_size": list(torso["size"]),
            "band_top": band_top,
            "band_bottom": band_bottom,
            "hem_h": hem_h,
            "panels": [{"x0": int(p[0]), "x1": int(p[1])} for p in panels],
        },
    }
    with open(os.path.join(spr, "jacket_parts.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print("写出 sprites/jacket_parts.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
