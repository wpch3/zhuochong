#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""make_skirt_parts.py —— 裙子里布（裏地）：T45.11，2026-10-17。

为什么要有里布
--------------
用户要的是「服装组件化」。T45.9 已经让裙摆能自己摆了，但摆开的那一瞬间，
裙子底下露出来的是**背景或大腿**，看着像一张纸片在平移 —— 布没有"厚度"。

教程口径（查过才动手）
----------------------
  · Live2D Cubism 2 官方手册「髪や服の『揺れ』の動きを表現する」：
      「スカートなどは**手前の面と奥の面で足を挟むように**画像を分けておく。
        これはスカートが揺れたときに、手前も奥も見える範囲が変わるため」
    ⇒ 里布要排在**腿的后面**，表布在腿的前面，两片夹着腿。
  · CLIP STUDIO 官方《Live2D用のデータをCLIP STUDIO PAINTで作る【後編】》：
      「スカートとして表裏くっついたまま１パーツで作成してしまうと、
        間にパーツがある場合、動かした時にパーツが食い込んで不自然な見た目になってしまいます。
        表と裏は分けておくと自然に動かすことができる」
  · 实务做法（没有里布原画时）：
      「スカートの裏側パーツがない場合はスカートのパーツを**コピーして乗算をかけて**
        裏側パーツとして使うとよい」（Live2D Tips 短视频，2023-10-10）
    ⇒ 我们正是这种情况：原画没有里布，所以**复制裙子 + 乘法压暗**。
  · note.com/morris_343（モデル制作記）：里布挂在主裙摆形变器的**子级**，
    自己再有一层曲面 ⇒ 对应我们这里「同一个参数、里布自己一条形变器、幅度更小 + 延迟」。
  · atam-academy.com/blog/2488（スカートの描き方）：
      「裏地が一切見えないスカートは、紙で作った円錐のように硬く見えてしまう」
      「反射光は**裏地と足の境目**を中心に入れる」
    ⇒ 压暗之后要在下沿补一点反射光，否则是一块死黑。

做法
----
1. 从 `sprites/seg_torso.png` 里按裙色（色卡「裙」）找出**裙摆满宽的那一段**
   （上面被外套挡住的窄条不要：那段根本不会露出来，白做还会在外套边上闪）。
2. 逐列从该列第一行裙色一直取到躯干底沿 —— 把褶皱暗部、底边线稿一起带上，
   这样里布的轮廓和表布**一模一样**（静止时必须被完全盖住，这是本工具的硬判据）。
3. 乘法压暗 ×0.58，再在下沿 18% 内补一道反射光（最多提亮 16%）。
4. 1× 与 @2x 各切一张 —— @2x 直接从 `seg_torso@2x.png` 上切，
   不需要超分模型（新部件没有 @2x 会让「高清切件全量启用」那条闸报红）。

输出：`sprites/skirt_lining.png` / `skirt_lining@2x.png` / `skirt_parts.json`
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

DARK = 0.58             # 乘法压暗系数（里布比表布暗）
BOUNCE_BAND = 0.18      # 下沿多高的一段补反射光（占里布高度）
BOUNCE_MAX = 0.16       # 反射光最多提亮多少
FULL_WIDTH_FRAC = 0.55  # 裙色宽度达到最大宽度的多少，才算"满宽裙摆"（上面是外套挡住的窄条）
MIN_RUN = 12            # 一列里至少连续多少行裙色才算数


def skirt_color(root: str, character: str) -> np.ndarray:
    p = os.path.join(root, "characters", character, "design", "palette.json")
    with open(p, encoding="utf-8") as f:
        for c in json.load(f)["colors"]:
            if c.get("name", "").strip() == "裙":
                h = c["hex"].lstrip("#")
                return np.array([int(h[i:i + 2], 16) for i in (0, 2, 4)])
    raise SystemExit("[make_skirt_parts] 色卡里没有「裙」这一项")


def lining_mask(a: np.ndarray, navy: np.ndarray, tol: int = 110):
    """返回 (掩码, 满宽起始行)。掩码 = 满宽裙摆那一段里，逐列「首行裙色→躯干底沿」。"""
    rgb, al = a[..., :3].astype(int), a[..., 3]
    solid = al > 128
    navy_m = solid & (np.abs(rgb - navy).sum(2) < tol)
    w_per_row = navy_m.sum(1)
    if not w_per_row.any():
        raise SystemExit("[make_skirt_parts] 躯干图里找不到裙色像素")
    top = None
    thr = w_per_row.max() * FULL_WIDTH_FRAC
    for y in range(a.shape[0]):
        if w_per_row[y] >= thr:
            top = y
            break
    if top is None:
        raise SystemExit("[make_skirt_parts] 找不到满宽裙摆")

    m = np.zeros(a.shape[:2], bool)
    for x in range(a.shape[1]):
        col = np.nonzero(navy_m[top:, x])[0]
        if col.size < MIN_RUN:
            continue
        y0 = top + int(col[0])
        sol = np.nonzero(solid[y0:, x])[0]
        if sol.size == 0:
            continue
        y1 = y0 + int(sol[-1])
        m[y0:y1 + 1, x] = True
    # 逐行补洞：有的列被高光/褶皱压得不像裙色（实测中间有一条 1~3px 的白缝），
    # 裙摆甩开时那条缝会变成一道背景色的裂口。按行取「最左→最右」再与躯干实心相交，
    # 形状仍然不会超出表布一个像素（硬判据：静止合成必须零变化）。
    for y in range(a.shape[0]):
        xs = np.nonzero(m[y])[0]
        if xs.size:
            m[y, xs[0]:xs[-1] + 1] = solid[y, xs[0]:xs[-1] + 1]
    return m, top


def build(a: np.ndarray, m: np.ndarray):
    """表布 → 里布：乘法压暗 + 下沿反射光。形状与表布逐像素相同。"""
    out = a.copy()
    rgb = out[..., :3].astype(np.float32)
    ys = np.nonzero(m.any(axis=1))[0]
    y0, y1 = int(ys[0]), int(ys[-1])
    h = max(1, y1 - y0 + 1)
    k = np.full(a.shape[:2], DARK, np.float32)
    band = max(1, int(round(h * BOUNCE_BAND)))
    for i in range(band):                      # 下沿往上渐隐的反射光
        y = y1 - i
        if y < 0:
            break
        k[y] = DARK + BOUNCE_MAX * (1.0 - i / band)
    rgb = np.clip(rgb * k[..., None], 0, 255)
    out[..., :3] = rgb.astype(np.uint8)
    out[..., 3] = np.where(m, a[..., 3], 0)
    return out


def shrink_under_solid(m: np.ndarray, alpha: np.ndarray, thr: int = 250) -> np.ndarray:
    """只保留"四邻都压在表布实心像素底下"的那些里布像素。

    ★ 为什么必须有这一步：表布边缘是**半透明的抗锯齿像素**（alpha 200 之类）。
      里布如果铺到那一圈底下，静止时就会从半透明边里透出来，整条裙边发暗 ——
      实测没这一步时静止帧差 599 个像素。往里收一圈之后，
      "静止时里布不可见"就是一条**可以证明**的性质（见下面的自检打印）。
    """
    solid = alpha >= thr
    e = solid.copy()
    e[1:, :] &= solid[:-1, :]
    e[:-1, :] &= solid[1:, :]
    e[:, 1:] &= solid[:, :-1]
    e[:, :-1] &= solid[:, 1:]
    return m & e


def cut(src_path: str, navy: np.ndarray):
    """1× 上定形状：返回 (里布 RGBA, 掩码, 偏移, 尺寸, 像素数, 满宽起始行)。"""
    a = np.asarray(Image.open(src_path).convert("RGBA")).copy()
    m, top = lining_mask(a, navy)
    m = shrink_under_solid(m, a[..., 3])
    lin = build(a, m)
    xs = np.nonzero(m.any(axis=0))[0]
    ys = np.nonzero(m.any(axis=1))[0]
    x0, x1, y0, y1 = int(xs[0]), int(xs[-1]), int(ys[0]), int(ys[-1])
    crop = lin[y0:y1 + 1, x0:x1 + 1]
    return (Image.fromarray(crop, "RGBA"), m, (x0, y0),
            (x1 - x0 + 1, y1 - y0 + 1), int(m.sum()), top)


def cut_hires(src_path: str, m1: np.ndarray, box1, size1):
    """@2x 不重新找形状，而是把 1× 的掩码**原样放大两倍**再去切。

    ★ 独立在 @2x 上找一次的后果（实测）：抗锯齿让裙色边界差了几个像素，
      切出来 536x161 而不是 532x160，再缩放对齐就和表布错位 ——
      渲染时 @2x 的 scale 是 ×0.5，错一两像素就能在裙边上看见一条暗线。
    """
    a = np.asarray(Image.open(src_path).convert("RGBA")).copy()
    m2 = np.kron(m1, np.ones((2, 2), bool))
    if m2.shape != a.shape[:2]:
        raise SystemExit(f"[make_skirt_parts] @2x 不是 1× 的整两倍：{a.shape[:2]} vs {m2.shape}")
    m2 = shrink_under_solid(m2, a[..., 3])
    lin = build(a, m2)
    x0, y0 = box1[0] * 2, box1[1] * 2
    crop = lin[y0:y0 + size1[1] * 2, x0:x0 + size1[0] * 2]
    return Image.fromarray(crop, "RGBA"), int(m2.sum())


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
        raise SystemExit(f"[make_skirt_parts] 缺少 {bp_path}（先跑 make_body_parts.py）")
    with open(bp_path, encoding="utf-8") as f:
        bp = json.load(f)
    # ★ T66.16：裙子已经被 split_skirt.py 从 seg_torso 里整件切出去了（skirt_main）。
    #   这时候「找裙子」必须去裙件上找 —— 躯干上已经一个裙像素都没有，
    #   照老代码跑会直接报「躯干图里找不到裙色像素」把重建链打断。
    #   坐标系跟着换：pos 的基准是**裙件**的 pos，不是躯干的。
    _split = os.path.join(spr, "skirt_split.json")
    if os.path.exists(_split):
        with open(_split, encoding="utf-8") as f:
            sid = json.load(f)["id"]
        torso = next(p for p in bp["parts"] if p["id"] == sid)
        src1, src2 = (os.path.join(spr, sid + ".png"), os.path.join(spr, sid + "@2x.png"))
    else:
        torso = next(p for p in bp["parts"] if p["id"] == "seg_torso")
        src1, src2 = (os.path.join(spr, "seg_torso.png"), os.path.join(spr, "seg_torso@2x.png"))
    navy = skirt_color(args.root, args.character)

    img, m1, off, size, npx, top = cut(src1, navy)
    img.save(os.path.join(spr, "skirt_lining.png"))
    pos = [torso["pos"][0] + off[0], torso["pos"][1] + off[1]]
    print(f"里布 {size[0]}x{size[1]} @ 身体({pos[0]},{pos[1]})  "
          f"满宽裙摆起始局部 y={top}  像素 {npx}")

    # 自检：里布必须整个压在表布的**实心**像素底下 —— 这就是"静止时看不见"的证明
    _t = np.asarray(Image.open(src1).convert("RGBA"))
    leak = int((m1 & (_t[..., 3] < 250)).sum())
    print(f"  压在表布半透明边上的里布像素 = {leak}（必须 0，否则静止时裙边会发暗）")
    if leak:
        raise SystemExit("[make_skirt_parts] 里布越过了表布的实心边界")

    hi = src2
    checks = {"px": npx, "dark": DARK, "bounce": BOUNCE_MAX, "leak": leak}
    if os.path.exists(hi):
        img2, npx2 = cut_hires(hi, m1, off, size)
        img2.save(os.path.join(spr, "skirt_lining@2x.png"))
        ok = img2.size == (size[0] * 2, size[1] * 2)
        print(f"  @2x {img2.size[0]}x{img2.size[1]}"
              f"（{'正好是 1× 的两倍' if ok else '★ 和 1× 对不上'}）")
        if not ok:
            raise SystemExit("[make_skirt_parts] @2x 尺寸不是 1× 的两倍")
        checks["px_2x"] = npx2

    out = {
        "schema_version": "1.0",
        "source": "表布（seg_torso / 切出来的 skirt_main）的裙摆段复制 + 乘法压暗"
                  "（原画没有里布，教程口径的通行做法）",
        "note": "裏地：排在腿的后面（官方手册「手前の面と奥の面で足を挟むように」），"
                "静止时被表布完全盖住，裙摆甩开才露出来。",
        "parts": [{
            "id": "skirt_lining",
            "file": "sprites/skirt_lining.png",
            "pos": pos,
            "size": list(size),
            "layer": 50,
            "note": "层 50 = 腿（60/61）之后、尾巴（30~33）之前",
        }],
        "checks": checks,
    }
    with open(os.path.join(spr, "skirt_parts.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print("写出 sprites/skirt_lining.png、skirt_lining@2x.png、skirt_parts.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
