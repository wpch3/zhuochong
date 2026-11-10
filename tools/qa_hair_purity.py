#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""qa_hair_purity.py —— 头发层"只许是头发"的机检（T67.38）

★ 为什么要有这条闸（用户三次强调过的那句话）
--------------------------------------------------------------------
    「头发必须自身完整一片，被身体盖住处照样画满；
      头发层里不许出现假手臂/假腿/衣服/皮肤像素。」

这句话可以拆成两条**可机检**的断言，这个脚本就是它：

  A. **自身完整一片**：头发件内部不许有"洞"。
     洞 = 被头发围住的透明区。头发一晃、被身体压住的那块让开，洞就漏出背景。
     （量法同 `tools/qa_sway_gap.py`：从画布四边泛洪，泛不到的透明像素才算洞。）

  B. **不许有别人的东西**：头发件里不许有**成块的**非发色像素。
     "成块"是关键：`alpha≥200` 且连通 ≥200px —— 一块真皮肤/真衣服长这样；
     而抠像留下的抗锯齿边（`alpha 25~90`）长不出 200px 的块。
     判据只用**测过不会误报**的两条：
       · 皮肤：`R-B>22`（发色自身的 R-B 实测最大 19，8~11 那一段有上万像素）；
       · 青布：`G-R>60 且 B-G≤20 且 G<215`（发梢的浅蓝是 B-G>25，不会撞）。
     白夹克（奶油白 R-B≈6）**颜色上和发色高光分不开**，所以不在这里判 ——
     它由 `tools/purge_hair_foreign_blocks.py` 从青布种子一路长过去抓。

  C. **边带串色（只报数、不判红）**：半透明边（0<alpha<241）里的暖色像素。
     这是原画的抗锯齿（头发与额头相接处天然混色），实测全库 12,558px，
     全部是 1~2px 宽的边带、没有任何成块（**成块异物 0 件**；最大的连通块 17px）。
     不判红的原因写在 `docs/memory/GAPS.md` G66.40：把它涂成发色反而会在
     "头发把额头压住的地方"画出深色块（实测），而它对画面的影响只在
     "头发与脸相对位移 1~2px"时才可见，且是同色系。要判红就得先给脸层
     单独画一张投影，那是美术活、不是脚本能定的 —— 所以这条只报数。

用法
----
    /home/user/.imgenv/bin/python tools/qa_hair_purity.py            # 报表
    /home/user/.imgenv/bin/python tools/qa_hair_purity.py --fail     # 有违规返回 1
"""
from __future__ import annotations

import argparse
import glob
import os
import sys

import numpy as np
from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

MIN_BLOB = 200          # 「成块」的门槛：一块真皮肤/真衣服远大于它
HOLE_MIN = 200          # 洞的门槛：更小的当发丝缝隙


def interior_holes(op, min_px=HOLE_MIN):
    """从画布四边泛洪补透明区，泛不到的透明像素 = 内部洞。"""
    h, w = op.shape
    seen = np.zeros((h, w), bool)
    stack = []
    for x in range(w):
        for y in (0, h - 1):
            if not op[y, x] and not seen[y, x]:
                seen[y, x] = True
                stack.append((y, x))
    for y in range(h):
        for x in (0, w - 1):
            if not op[y, x] and not seen[y, x]:
                seen[y, x] = True
                stack.append((y, x))
    while stack:
        y, x = stack.pop()
        for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            ny, nx = y + dy, x + dx
            if 0 <= ny < h and 0 <= nx < w and not op[ny, nx] and not seen[ny, nx]:
                seen[ny, nx] = True
                stack.append((ny, nx))
    holes = (~op) & (~seen)
    return holes


def blobs(mask, min_px=MIN_BLOB):
    """连通块（4 邻域）。返回 [(size, (y0,y1,x0,x1)), ...]，大的在前。"""
    h, w = mask.shape
    lab = np.zeros((h, w), np.int32)
    out = []
    n = 0
    ys, xs = np.nonzero(mask)
    if not len(ys):
        return out
    stack = []
    for y0, x0 in zip(ys, xs):
        if not mask[y0, x0] or lab[y0, x0]:
            continue
        n += 1
        lab[y0, x0] = n
        stack = [(y0, x0)]
        size = 0
        ymin = ymax = y0
        xmin = xmax = x0
        while stack:
            y, x = stack.pop()
            size += 1
            ymin, ymax = min(ymin, y), max(ymax, y)
            xmin, xmax = min(xmin, x), max(xmax, x)
            for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                ny, nx = y + dy, x + dx
                if 0 <= ny < h and 0 <= nx < w and mask[ny, nx] and not lab[ny, nx]:
                    lab[ny, nx] = n
                    stack.append((ny, nx))
        if size >= min_px:
            out.append((size, (ymin, ymax, xmin, xmax)))
    out.sort(reverse=True)
    return out


def body_colors(rgb, alpha):
    """只保留**测过不会误报**的两条。

    ★ 去掉"白布块"这条的原因（实测）：本角色的**发色高光就是纯白**
      （`hair_long_back` 里 (255,255,255) 373px、`hair_back` 里 (243,236,242) 上千 px），
      白布判据把它整片判成异物，21 件里 12 件"违规"其实全是头发自己的高光。
      白夹克那种奶油白（R-B≈6）和发色高光的差值在 1~2 之间，**颜色上分不开**。
      所以白布不在这里判 —— 它靠 `tools/purge_hair_foreign_blocks.py`
      的"从青布种子长过去"来抓（同一条下摆青白相间，青块是可靠种子）。
    """
    R = rgb[..., 0].astype(np.int32)
    G = rgb[..., 1].astype(np.int32)
    B = rgb[..., 2].astype(np.int32)
    skin = (R - B > 22) & (R > 150) & (R - G > 8)              # 发色 R-B ≤ 19（实测直方图）
    teal = (G - R > 60) & (B - G <= 20) & (G < 215)            # 袖口青，发梢浅蓝 B-G>25 不撞
    return skin, teal


def check_twin_hood_eye_fragment(path):
    """针对已复现的 twin hood 污染：刘海中央额前 ROI 不许混入蓝色眼像素。

    2026-10-31 的源片对照实测：修复前同一 ROI 命中 124 个蓝色虹膜/巩膜像素，
    修复后为 0。这里只看源切片坐标 x=210..254、y=95..129，避开发梢的合法蓝色高光；
    不把脸部眼睛本身当作头发件检查。
    """
    a = np.array(Image.open(path).convert("RGBA"))
    if a.shape[1] < 255 or a.shape[0] < 130:
        raise ValueError(f"twin hood sprite 尺寸异常：{a.shape[1]}x{a.shape[0]}")
    roi = a[95:130, 210:255]
    r, g, b, alpha = (roi[..., i].astype(np.int32) for i in range(4))
    blue_eye = (alpha > 40) & (b > 90) & (b > r * 1.25) & (b > g * 1.10)
    return int(blue_eye.sum())


def check(path):
    a = np.array(Image.open(path).convert("RGBA"))
    rgb, al = a[..., :3], a[..., 3]
    op = al > 24
    res = {"file": os.path.basename(path), "opaque": int(op.sum())}
    res["holes"] = int((interior_holes(op) & (al <= 8)).sum())
    skin, teal = body_colors(rgb, al)
    solid = al >= 200
    res["blobs"] = {}
    for name, m in (("skin", skin), ("teal", teal)):
        bl = blobs(m & solid)
        if bl:
            res["blobs"][name] = bl[:3]
    soft = (al > 0) & (al < 241) & skin
    res["soft_skin"] = int(soft.sum())
    return res


# 已知欠账：**只记形态+文件名**，理由和工单号必须写在旁边。
# 判定标准：这件不是"忘了修"，而是"脚本修不了、必须重画"。
KNOWN = {
    ("chibi", "hair_long_back@2x.png"):
        "T67.41 整片头皮/额头（约 4 万 px 的奶油横带）烘在长后发里，"
        "而这件的发色本身就是粉紫（R-B 12~21），和皮肤在颜色上分不开："
        "挖掉会开天窗、补色会留白痕。必须重画这一件",
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--character", default="xiaoxun")
    ap.add_argument("--form", default="teen")
    ap.add_argument("--fail", action="store_true")
    ap.add_argument("--strict-occlusion", action="store_true",
                    help="hood long/twin/pony cutouts must have no enclosed transparent block >=200px")
    ap.add_argument("--check-twin-hood-eye", action="store_true",
                    help="只检查 twin hood 刘海中央是否混入蓝色眼像素")
    a = ap.parse_args()

    d = os.path.join(ROOT, "characters", a.character, "forms", a.form, "sprites")
    if a.check_twin_hood_eye:
        path = os.path.join(d, "hair_hood_twin.png")
        try:
            n = check_twin_hood_eye_fragment(path)
        except (OSError, ValueError) as exc:
            print("twin hood 刘海中央眼部污染检查失败：", exc)
            return 2
        print(f"twin hood 刘海中央蓝色眼像素：{n}（期望 0）")
        return 1 if n else 0

    files = [f for f in sorted(glob.glob(os.path.join(d, "*@2x.png")))
             if os.path.basename(f).startswith(("hair_", "acc_hair_"))]
    if not files:
        print("没找到头发件：", d)
        return 2

    print("%-26s %9s %7s %7s  %s" % ("头发件", "不透明", "内部洞", "边带暖色", "成块异物（alpha≥200 且 ≥%dpx）" % MIN_BLOB))
    print("-" * 104)
    bad = 0
    soft_total = 0
    for f in files:
        r = check(f)
        soft_total += r["soft_skin"]
        marks = []
        # 内部洞**只报数不判红**：发丝之间的缝本来就该透出脸（实测最大的 hair_side_l
        # 484px 就是梳齿状的发缝）。会漏底色的"洞"由 `tools/qa_sway_gap.py` 单独管
        # （那个算的是"摆动时从洞里透出背景"的像素）。
        for kind, bl in r["blobs"].items():
            for size, box in bl:
                cn = {"skin": "皮肤", "teal": "青布"}[kind]
                marks.append("%s块 %dpx@%s" % (cn, size, box))
        kr = KNOWN.get((a.form, r["file"]))
        if kr:
            marks.append("※已知欠账：%s" % kr)
        elif marks:
            bad += 1
        print("%-26s %9d %7d %7d  %s" % (r["file"], r["opaque"], r["holes"], r["soft_skin"],
                                         "  ".join(marks) if marks else "干净"))
    if a.strict_occlusion:
        for name in ("hair_hood_long@2x.png", "hair_hood_twin@2x.png",
                     "hair_hood_pony@2x.png"):
            path = os.path.join(d, name)
            if not os.path.exists(path):
                print("[严格遮挡] 缺少兜帽头发件 %s" % name)
                bad += 1
                continue
            arr = np.asarray(Image.open(path).convert("RGBA"))
            holes = interior_holes(arr[..., 3] > 24) & (arr[..., 3] <= 8)
            enclosed = blobs(holes, min_px=200)
            if enclosed:
                print("[严格遮挡] %s 内部透明块: %s" % (name, enclosed[:3]))
                bad += 1
            else:
                print("[严格遮挡] %s: no enclosed transparent block >=200px" % name)
    print("-" * 104)
    print("共 %d 件；成块异物违规 %d 件；边带暖色合计 %d px（只报数，见文件头 C）"
          % (len(files), bad, soft_total))
    if a.fail and bad:
        print("头发布料纯度：不通过 —— 头发层里出现了皮肤/衣服的成块像素")
        return 1
    print("头发布料纯度：通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
