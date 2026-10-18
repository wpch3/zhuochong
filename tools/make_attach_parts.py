#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""挂件切件器：洋红底 AI 原图 → 按色卡重铺的挂件贴图（A49 / T45）。

挂件 = 耳饰 / 尾饰 / 发饰 / 装饰品这类**加法**部件（往剪影上或外加东西，
底下的画面不用动）。服装变化是**替换**类，不走这条路（阻塞于 D19，见 T45.6）。

和另外两个切件器的分工：
  · make_star_eye_parts.py —— 散布型特效（一张素材铺很多片，✨）
  · make_manpu_parts.py    —— 漫符（一个符号一张图，方形，飘在身体外）
  · 本文件                  —— 挂件（**非方形**，挂在身体上，要接物理与形变器）

三者的键色与重铺是同一套算法，直接从 make_manpu_parts 导入，不重写
（重写第二份 = 两份会慢慢长歪，这正是 G117 要消灭的那种事）。

挂件和漫符的两个实质差别：
  1. **不是方的**。尾巴是 1:2 的竖图，强行压成正方会把它压扁。
  2. **锚点不在中心**。悬垂件的锚点必须落在**根部**，因为那就是物理支点；
     zrig.c:751 的 anchor 默认 (0.5,0.5)，表里要显式写 [0.5,0.0] 之类。
"""
from __future__ import annotations

import argparse
import io
import json
import os

import numpy as np
from PIL import Image

import attach_geom
from make_manpu_parts import (SOLID_A, bg_color, key_alpha, left_magenta,
                              relay_colors, CROP_MARGIN)


def key_alpha_soft(rgb: np.ndarray, bg: np.ndarray) -> np.ndarray:
    """洋红底的**精确** alpha —— 给要保留渐变的挂件用。

    `make_manpu_parts.key_alpha` 用「到背景的欧氏距离」估覆盖度。那对漫符够用
    （硬边 + 事后按色卡重铺，边上那点误差被重铺盖掉了），但对要保留渐变的柔边
    **会系统性高估**：30% 白压在洋红上得到 (255,76,255)，距离法给 0.57，真值是 0.30。
    结果就是一圈半透明的紫边，而且去边公式拿错 a 一除，紫得更凶。

    洋红底其实有精确解：背景是 (255,0,255)，G 通道为 0，所以
        观测G = a·前景G + (1−a)·0 = a·前景G
    把「比中性色多出来多少洋红」定义成 excess = (R+B)/2 − G，
    纯背景 excess = 255、纯中性前景 excess = 0，于是 a = 1 − excess/255。
    代回上面的例子：excess = 255−76 = 179 ⇒ a = 0.30。**对上了。**

    前提：前景本身不能是洋红系。银紫→青蓝的尾巴满足；真要做粉色挂件得换判据。
    """
    f = rgb.astype(np.float64)
    excess = (f[..., 0] + f[..., 2]) * 0.5 - f[..., 1]
    denom = (float(bg[0]) + float(bg[2])) * 0.5 - float(bg[1])
    if denom < 1.0:
        raise SystemExit("[attach] 背景不是洋红系，key_alpha_soft 用不了")
    return np.clip(1.0 - np.maximum(excess, 0.0) / denom, 0.0, 1.0)


def _srgb_to_lab(rgb: np.ndarray) -> np.ndarray:
    """sRGB(0~255) → CIE Lab(D65)。只用 numpy，不拉 scikit-image 进依赖。"""
    c = np.clip(rgb.astype(np.float64) / 255.0, 0.0, 1.0)
    c = np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)
    m = np.array([[0.4124564, 0.3575761, 0.1804375],
                  [0.2126729, 0.7151522, 0.0721750],
                  [0.0193339, 0.1191920, 0.9503041]])
    xyz = c @ m.T
    wp = np.array([0.95047, 1.0, 1.08883])
    t = xyz / wp
    d = 6.0 / 29.0
    f = np.where(t > d ** 3, np.cbrt(np.maximum(t, 1e-12)),
                 t / (3 * d * d) + 4.0 / 29.0)
    return np.dstack([116.0 * f[..., 1] - 16.0,
                      500.0 * (f[..., 0] - f[..., 1]),
                      200.0 * (f[..., 1] - f[..., 2])])


def _lab_to_srgb(lab: np.ndarray) -> np.ndarray:
    fy = (lab[..., 0] + 16.0) / 116.0
    fx = fy + lab[..., 1] / 500.0
    fz = fy - lab[..., 2] / 200.0
    d = 6.0 / 29.0
    def finv(u):
        return np.where(u > d, u ** 3, 3 * d * d * (u - 4.0 / 29.0))
    wp = np.array([0.95047, 1.0, 1.08883])
    xyz = np.dstack([finv(fx) * wp[0], finv(fy) * wp[1], finv(fz) * wp[2]])
    m = np.array([[3.2404542, -1.5371385, -0.4985314],
                  [-0.9692660, 1.8760108, 0.0415560],
                  [0.0556434, -0.2040259, 1.0572252]])
    c = xyz @ m.T
    c = np.where(c <= 0.0031308, 12.92 * c,
                 1.055 * np.power(np.maximum(c, 0.0), 1.0 / 2.4) - 0.055)
    return np.clip(c, 0.0, 1.0) * 255.0


def ref_hair_pixels(sprites_dir: str, names, palette_hex=None,
                    tol: float = 25.0) -> np.ndarray:
    """从**本体已有的头发贴图**里取样，作为配色基准。

    画师的做法就是这个（CLIP STUDIO 官方 making，森倉円）：追加画的发丝
    「[スポイト]ツールで髪色の**明るいところや暗いところから**スポイトして描くと
    なじみやすい」—— 取的是本体发色的明暗**两端**，不是一个平均色。
    我们这里干脆把整条分布都取来（alpha 可信的像素），交给 Lab 统计匹配。
    """
    acc = []
    for n in names:
        fp = os.path.join(sprites_dir, n)
        if not os.path.exists(fp):
            continue                      # 这个形态没拆这件，换下一个候选
        im = np.asarray(Image.open(fp).convert("RGBA"), dtype=np.float64)
        sel = im[..., 3] > 0.85 * 255.0
        if sel.sum() < 64:
            continue
        acc.append(im[..., :3][sel])
    if acc:
        return np.concatenate(acc, axis=0)
    # —— 退路：这个形态根本没有单独的头发贴图（chibi 的头发是画在 body_full 里的）——
    # 用色卡当**选择器**（不是当目标分布）：从本形态自己的整图里挑出
    # 「离任一发色足够近」的像素，拿它们的真实分布做基准。
    # 这样基准永远来自**这个形态自己的成品**，不会跨形态串色。
    if not palette_hex:
        raise SystemExit("[attach] 没有可用的配色基准贴图，也没给色卡")
    fp = os.path.join(sprites_dir, "body_full.png")
    if not os.path.exists(fp):
        raise SystemExit("[attach] 配色基准：%s 不存在" % fp)
    im = np.asarray(Image.open(fp).convert("RGBA"), dtype=np.float64)
    solid = im[..., 3] > 0.85 * 255.0
    px = im[..., :3][solid]
    pal = np.array([[int(h[i:i + 2], 16) for i in (1, 3, 5)] for h in palette_hex],
                   dtype=np.float64)
    dist = np.sqrt(((px[:, None, :] - pal[None, :, :]) ** 2).sum(axis=2)).min(axis=1)
    hit = px[dist < tol]
    if len(hit) < 256:
        raise SystemExit("[attach] 按色卡从 body_full 里只挑出 %d 个发色像素，"
                         "太少（tol=%.0f）" % (len(hit), tol))
    return hit


def bleed_edge(rgb: np.ndarray, a: np.ndarray, rounds: int = 3) -> np.ndarray:
    """把**实心区**的颜色往半透明边缘推（alpha-weighted color bleed）。

    为什么需要：反预乘只能在 alpha 估得准的地方还原颜色，最外圈一两个像素的
    覆盖度估计误差会留下一点底色（我们的底是洋红，于是 `left_magenta` 当场报红）。
    通用做法是把边缘像素的颜色换成邻域里**更实**的像素的加权平均 ——
    反正那些像素的 alpha 很低，颜色换掉肉眼看不出来，但键色残留没了。
    """
    w = np.clip(a, 0.0, 1.0) ** 2.0           # 越实的像素话语权越大
    acc_c = rgb.astype(np.float64) * w[..., None]
    acc_w = w.copy()
    for _ in range(rounds):
        c = acc_c.copy()
        ww = acc_w.copy()
        for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            c += np.roll(acc_c, (dy, dx), axis=(0, 1)) * 0.5
            ww += np.roll(acc_w, (dy, dx), axis=(0, 1)) * 0.5
        acc_c, acc_w = c, ww
    out = acc_c / np.maximum(acc_w, 1e-6)[..., None]
    # 实心区保持原样，只把边缘换成扩散来的颜色
    t = np.clip((a - 0.15) / 0.55, 0.0, 1.0)[..., None]
    return np.clip(rgb.astype(np.float64) * t + out * (1.0 - t), 0, 255)


def match_colors(rgb: np.ndarray, a: np.ndarray, ref: np.ndarray,
                 keep: float = 1.0) -> np.ndarray:
    """Reinhard 色彩迁移（Lab 的 mean/std 对齐）：让挂件**长得像本体的头发**。

    为什么不用 relay_colors（按亮度 k-means 重铺到 3 色）：那套是给**漫符**设计的 ——
    卡通符号本来就是大片平色，聚成纯色既对画风也好过色卡闸。但头发不是平色：
    它有柔和的明暗过渡和**梢部的蓝色渐变**，k-means 一压就变成三条硬边灰带，
    蓝梢直接被归进阴影簇消失。2026-10-18 用户看截图第一句话就是
    「色彩和形态完全不一样非常的违和」，病因就在这里。

    Reinhard(2001)《Color transfer between images》：把源图和参考图都转进 Lab，
    逐通道做 `(x−μ_src)·σ_ref/σ_src + μ_ref`，统计对齐后"看起来就是同一套配色"。
    它**保留图像内部的相对结构**（哪里亮哪里暗、哪缕偏蓝），只把整体的
    色相/明度/对比挪到参考分布上 —— 正好是"同一个角色的另一绺头发"要的效果。

    keep<1 时把结果往原色方向回拉一点（给需要保留本来颜色的挂件留口子）。
    """
    solid = a > SOLID_A
    if solid.sum() < 64:
        raise SystemExit("[attach] 可信像素太少，没法做配色匹配")
    src_lab = _srgb_to_lab(rgb)
    ref_lab = _srgb_to_lab(ref.reshape(-1, 1, 3))[:, 0, :]
    out = np.empty_like(src_lab)
    for ch in range(3):
        sv = src_lab[..., ch][solid]
        mu_s, sd_s = sv.mean(), max(sv.std(), 1e-6)
        mu_r, sd_r = ref_lab[:, ch].mean(), ref_lab[:, ch].std()
        # σ 比值限幅：参考分布比源窄很多时，不要把源图压成一张平色；
        # 明度(L)留得宽一点（阴影层次是头发的立体感），彩度(a/b)收得紧一点。
        lo, hi = (0.35, 2.5) if ch == 0 else (0.15, 1.6)
        k = float(np.clip(sd_r / sd_s, lo, hi))
        out[..., ch] = (src_lab[..., ch] - mu_s) * k + mu_r
    # ★ 彩度封顶：输出的 a/b 不许超出**本体头发自己的彩度范围**。
    #   没有这一道时，源图里的深色线稿（蓝紫，RGB≈(60,17,123)）被统计迁移抬亮之后
    #   会落成粉紫 (209,106,175) —— 肉眼就是"洋红残留"，切件器的键色闸当场报警。
    #   道理也站得住：所谓"同源配色"，本来就包含"不许比本体更艳"。
    for ch in (1, 2):
        lo = float(np.percentile(ref_lab[:, ch], 0.5)) - 2.0
        hi = float(np.percentile(ref_lab[:, ch], 99.5)) + 2.0
        out[..., ch] = np.clip(out[..., ch], lo, hi)
    res = _lab_to_srgb(out)
    if keep < 1.0:
        res = res * keep + rgb.astype(np.float64) * (1.0 - keep)
    return np.clip(res, 0, 255)


def build_one(att, slot, redraw_dir, sprites_dir, anchors):
    src = os.path.join(redraw_dir, att["source"])
    if not os.path.exists(src):
        raise SystemExit("[attach] 缺原图 %s" % src)
    im = Image.open(src).convert("RGB")
    rgb = np.asarray(im, dtype=np.uint8)
    bg = bg_color(rgb)
    a = key_alpha(rgb, bg)

    ys, xs = np.nonzero(a > 0.35)
    if len(xs) == 0:
        raise SystemExit("[attach] %s：键完什么都不剩，底色判错了？bg=%s"
                         % (att["id"], bg))
    x0, x1, y0, y1 = xs.min(), xs.max() + 1, ys.min(), ys.max() + 1

    # source_crop：在**内容框**里再截一刀，四个数是比例 [左, 上, 右, 下]。
    # ★ 为什么需要：出图模型对"长度"很难精确控制。猫尾「夹紧」那张，钩是对的，
    #   但上面的直杆段画得过长 —— 要让笔画粗细对齐 relaxed（69px）就得把
    #   sprite_h 开到 675，从胯部一路垂到画布底。截掉上段直杆（尾根本来就被
    #   裙子挡着）之后，同样的粗细只要 404，和 relaxed 的 410 同量级。
    # 截在**内容框**的比例上而不是原图像素上，是为了换一张同题材的图也能用。
    cr = att.get("source_crop")
    if cr:
        cw, ch = x1 - x0, y1 - y0
        nx0 = x0 + int(round(cw * float(cr[0])))
        ny0 = y0 + int(round(ch * float(cr[1])))
        nx1 = x0 + int(round(cw * float(cr[2])))
        ny1 = y0 + int(round(ch * float(cr[3])))
        if not (nx0 < nx1 <= x1 and ny0 < ny1 <= y1):
            raise SystemExit("[attach] %s：source_crop %s 截出空区间" % (att["id"], cr))
        x0, x1, y0, y1 = nx0, nx1, ny0, ny1

    # ★ 保长宽比。漫符那边裁成正方是因为漫符本来就是方的；
    #   挂件不是 —— 尾巴 1:2，压成正方会变成一坨。
    padx = int(round((x1 - x0) * CROP_MARGIN))
    pady = int(round((y1 - y0) * CROP_MARGIN))
    bx0, by0 = x0 - padx, y0 - pady
    bw, bh = (x1 - x0) + padx * 2, (y1 - y0) + pady * 2
    canvas = np.empty((bh, bw, 3), dtype=np.uint8)
    canvas[:, :] = bg.astype(np.uint8)
    sx0, sy0 = max(bx0, 0), max(by0, 0)
    sx1, sy1 = min(bx0 + bw, rgb.shape[1]), min(by0 + bh, rgb.shape[0])
    canvas[sy0 - by0:sy1 - by0, sx0 - bx0:sx1 - bx0] = rgb[sy0:sy1, sx0:sx1]

    if att.get("recolor_match"):
        # 保留渐变的 alpha（和 else 分支同一套），颜色走 Lab 统计匹配。
        rm = att["recolor_match"]
        ca = key_alpha_soft(canvas, bg)
        aa = ca[..., None]
        unpre = np.clip((canvas.astype(np.float64)
                         - (1.0 - aa) * bg.astype(np.float64))
                        / np.maximum(aa, 1e-3), 0, 255)
        unpre = bleed_edge(unpre, ca)
        crgb = match_colors(unpre, ca,
                            ref_hair_pixels(sprites_dir, rm["ref_sprites"],
                                            rm.get("palette_hex")),
                            float(rm.get("keep", 1.0)))
    elif att.get("recolor"):
        ca = key_alpha(canvas, bg)
        crgb = relay_colors(canvas, ca, att["recolor"])
    else:
        # 保留渐变的路径：精确 alpha + 反预乘去边。
        ca = key_alpha_soft(canvas, bg)
        aa = ca[..., None]
        crgb = canvas.astype(np.float64) - (1.0 - aa) * bg.astype(np.float64)
        crgb = np.clip(crgb / np.maximum(aa, 1e-3), 0, 255)

    if att.get("mirror"):
        # 左右耳用同一张原图镜像出来：AI 画两只一定不对称，而头上的东西
        # 一不对称就特别显眼（脸是对称参照物）。镜像还省一次出图。
        crgb = crgb[:, ::-1, :]
        ca = ca[:, ::-1]

    if att.get("rotate_deg"):
        # 静态外倾：真猫耳是向外斜的，不是笔直向上。
        # 在**切件期**转而不是用参数转，是因为参数那条通道已经被
        # mood_params（情绪→耳角）占着了，再叠一个静态量两边会打架。
        rot = Image.fromarray(
            np.dstack([crgb, ca * 255.0]).astype(np.uint8), "RGBA").rotate(
                float(att["rotate_deg"]), resample=Image.BICUBIC, expand=True)
        ra = np.asarray(rot)
        crgb = ra[..., :3].astype(np.float64)
        ca = ra[..., 3].astype(np.float64) / 255.0

    # 高度来自**形态级** anchors.json（相对几何，T2.2.0）：
    # 同一张挂件表要能套在 teen/loli/adult/chibi 四个形态上，
    # 写绝对像素的话 chibi 那个 517px 的头上会扣一对 104px 的耳朵。
    _pos, h1 = attach_geom.resolve(att, anchors)
    # width_ratio：横向压扁/拉宽系数，1.0 = 保持原图宽高比。
    # ★ 猫耳要用到：素材画出来的宽高比是 1.09（扁三角），但真猫耳从正面看
    #   底宽约为高的 0.8，1.09 会让两只耳朵横着铺满整个头顶 —— 用户原话「过宽」。
    #   不在原图上改，是因为原图还要留给别的槽复用；压扁放在切件期做。
    w1 = max(1, int(round(h1 * bw / float(bh) * float(att.get("width_ratio", 1.0)))))
    made = []
    for mul, name in ((1, att["sprite"]),
                      (2, att["sprite"].replace(".png", "@2x.png"))):
        # ★ 缩放走 straight RGBA（不是预乘）。试过预乘缩放再除回来，
        #   边缘低 alpha 处的除法会把颜色放大成近白，白边像素从 ~200 暴涨到 5870，
        #   check_assets 的白边闸当场红 —— 对这套素材来说，
        #   "先把边缘颜色抹成相邻实心色（bleed_edge）再直缩"更稳。
        rgba = np.dstack([crgb, ca * 255.0]).astype(np.uint8)
        out = Image.fromarray(rgba, "RGBA").resize((w1 * mul, h1 * mul),
                                                   Image.LANCZOS)
        arr = np.asarray(out)
        leftover = left_magenta(arr[..., :3], arr[..., 3] / 255.0)
        if leftover:
            raise SystemExit("[attach] %s %s 还剩 %d 个洋红像素"
                             % (att["id"], name, leftover))
        out.save(os.path.join(sprites_dir, name))
        made.append(name)
    return w1, h1, made, float((ca > 0.5).sum()) / float(ca.size)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    ap.add_argument("--character", required=True)
    ap.add_argument("--form", required=True)
    a = ap.parse_args()

    base = os.path.join(a.root, "characters", a.character)
    sprites = os.path.join(base, "forms", a.form, "sprites")
    redraw = os.path.join(base, "design", "redraw")
    tp = os.path.join(base, "design", "attachments.json")
    if not os.path.exists(tp):
        print("[attach] 没有 %s，跳过" % tp)
        return 0
    with io.open(tp, encoding="utf-8") as f:
        table = json.load(f)

    # 形态级锚点：挂件几何是**相对**这个形态的头高/身高表达的（T2.2.0）。
    # 同一张挂件表要能套在 teen/loli/adult/chibi 上，不能写绝对像素。
    anchors = attach_geom.load_anchors(os.path.join(base, "forms", a.form, "design"))
    _ovr = attach_geom.load_overrides(
        os.path.join(base, "forms", a.form, "design"))
    if anchors is None:
        anchors = attach_geom.load_anchors(os.path.join(base, "forms", a.form))
    slots = {s["id"]: s for s in table["slots"]}
    out = {"schema_version": "1.0", "slots": table["slots"], "attachments": []}
    for att in table["attachments"]:
        slot = slots.get(att["slot"])
        if slot is None:
            raise SystemExit("[attach] %s 落在不存在的插槽 %r"
                             % (att["id"], att["slot"]))
        w, h, made, cover = build_one(
            attach_geom.apply_overrides(att, _ovr), slot, redraw, sprites, anchors)
        out["attachments"].append({
            "id": att["id"], "slot": att["slot"],
            "file": "sprites/" + att["sprite"],
            "size": [w, h],
        })
        print("[attach] %-10s → 槽 %-18s %dx%d（覆盖 %.0f%%）"
              % (att["id"], att["slot"], w, h, cover * 100))

    dst = os.path.join(sprites, "attach_parts.json")
    with io.open(dst, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print("写出 %s：%d 件 / %d 槽" % (dst, len(out["attachments"]), len(slots)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
