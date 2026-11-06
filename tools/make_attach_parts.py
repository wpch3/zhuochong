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


def harden_interior(a: np.ndarray, thr: float = 0.35, band: int = 2) -> np.ndarray:
    """把洋红键出来的 alpha，在**件的内部**补成不透明。

    ★ 2026-10-18 第十二问查出来的系统性缺陷。key_alpha_soft 的推导有一个前提，
    它自己的文档串里也写着：「前景本身不能是洋红系」。而本项目的**头发就是淡紫**
    —— R 和 B 都比 G 高，正好部分满足洋红的判据：

        excess = (R+B)/2 − G
        淡紫 (200,190,225) → excess = 22.5 → a = 0.91
        再紫一点 (180,150,220) → excess = 50 → a = 0.80

    于是**整件头发被系统性地抠成半透明**，而不是只有边缘。实测：
      acc_hair_crown_pony   alpha>240 的像素只占 **1.9%**
      acc_hair_sidelong_l                        **18.8%**
      acc_hair_sweep_pony_l                      **26.8%**
    画面上就是"能看穿的头发"——发丝底下透出衣领和发卡。用户第十二问说长发
    "一坨"、看着脏，有这一份原因。

    修法是形态学的：alpha 超过 thr 的区域先腐蚀掉 band 像素得到**内芯**，
    内芯一律补成 1；只有外圈那条 band 宽的带子保留原来的软过渡（抗锯齿还在）。
    不改 key_alpha_soft 本身 —— 它算边缘覆盖度是对的，错的是把它用在内部。
    """
    from PIL import Image as _I, ImageFilter as _F
    m = (a > thr).astype(np.uint8) * 255
    core = np.asarray(_I.fromarray(m, "L").filter(_F.MinFilter(2 * band + 1)))
    return np.where(core > 127, 1.0, a)


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
                 keep: float = 1.0, l_sigma_max: float = 2.5,
                 l_offset: float = 0.0, src_lab_pool=None) -> np.ndarray:
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
    # ★★★ 2026-10-21 第二十九问：src_lab_pool = **整组共用的源统计**。
    #   不给的话，μ_src/σ_src 就按**这一件自己的像素**算 —— 于是同一张模板切下来的
    #   每一片各自得到一套不同的仿射系数：刘海片算出一套、横髪片算出另一套，
    #   两片在脸侧相接的地方颜色对不上，就是用户看到的「头发突然截断变色」。
    #   更糟的是长发帘这种**自带蓝梢渐变**的大片，它自己的 σ(a/b) 很大，
    #   被 σ_ref/σ_src 一除就把渐变压平，蓝梢褪成粉灰。
    #   给了 pool（= 同一张套准模板上所有发片的像素合在一起）之后，整组共用
    #   一个仿射变换：组内的相对关系（哪片亮、哪段偏蓝）**原样保留**，
    #   只把整组的色相/明度平移到本体头发的分布上。
    ref_lab = _srgb_to_lab(ref.reshape(-1, 1, 3))[:, 0, :]
    out = np.empty_like(src_lab)
    for ch in range(3):
        sv = (src_lab[..., ch][solid] if src_lab_pool is None
              else src_lab_pool[:, ch])
        mu_s, sd_s = sv.mean(), max(sv.std(), 1e-6)
        mu_r, sd_r = ref_lab[:, ch].mean(), ref_lab[:, ch].std()
        # σ 比值限幅：参考分布比源窄很多时，不要把源图压成一张平色；
        # 明度(L)留得宽一点（阴影层次是头发的立体感），彩度(a/b)收得紧一点。
        # ★ l_sigma_max（2026-10-18 第十一问）：L 的 σ 放大系数要能按件收。
        #   新画的长发刘海是一张**又亮又平**的图（L mean 95.7、sd 6.6），而本体
        #   头发 sd 12.65 ⇒ k=1.92。L 的均值虽然对齐到了参考值 80.9，但 σ 放大
        #   是**绕均值双向拉开**的：亮端顶到 L=100 被削平，暗端一路压下去，
        #   再经 sRGB 的非线性转回来，**RGB 均值从 ~(205,200,210) 掉到 (164,157,177)**
        #   —— 肉眼就是"灰了一个号"，用户第十一问说长发那版前髪不对，有这一半原因。
        #   默认仍是 2.5（现有件一个都不动），需要的件单独收到 1.0。
        lo, hi = (0.35, float(l_sigma_max)) if ch == 0 else (0.15, 1.6)
        k = float(np.clip(sd_r / sd_s, lo, hi))
        # l_offset：把明度整体再抬/压一点。参考池是**全部头发**的分布（含后发壳
        #   的大片暗部），而刘海在原画里本来就比平均亮 —— 统计对齐到池均值会让
        #   新刘海看着"灰一号"。这个偏移就是补这一截，默认 0。
        out[..., ch] = (src_lab[..., ch] - mu_s) * k + mu_r \
            + (float(l_offset) if ch == 0 else 0.0)
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


def scrub_key(arr):
    """把缩放后边缘上残留的键色（洋红 / 纯绿）像素换成最近的真实颜色。

    ★ 为什么不能只 assert：make_manpu_parts.left_magenta 判\"可见\"用的是
      alpha > 127，而 check_assets 的键色垃圾闸用的是 alpha > 40。中间这段
      半透明边像素里混进来的洋红，切件器一声不吭，验收闸直接判红
      （2026-10-18 实测 acc_hair_sidelong_l@2x 等 4 个件共 13 个像素）。
      两边阈值不统一就会一直来回踩，所以这里按**更严**的那个（>24）直接擦干净。
    ★ 根因是 LANCZOS 缩放会把洋红底的颜色吸进边缘的半透明像素里；
      alpha 本身是对的（边就该是半透明），错的只是 RGB。所以只改 RGB、不动 alpha。
    """
    a = arr.astype(np.int32)
    R, G, B, A = a[..., 0], a[..., 1], a[..., 2], a[..., 3]
    vis = A > 24
    bad = vis & (((R - G > 60) & (B - G > 60) & (R > 150) & (B > 150))
                 | (G - np.maximum(R, B) > 60))
    if not bad.any():
        return arr
    good = vis & (~bad)
    rgb = arr[..., :3].astype(np.float64).copy()
    todo = bad.copy()
    src = good.copy()
    for _ in range(8):
        if not todo.any():
            break
        acc = np.zeros(rgb.shape, np.float64)
        cnt = np.zeros(rgb.shape[:2], np.float64)
        for dy, dx in ((-1, 0), (1, 0), (0, -1), (0, 1),
                       (-1, -1), (-1, 1), (1, -1), (1, 1)):
            sh = np.roll(np.roll(rgb * src[..., None], dy, 0), dx, 1)
            sc = np.roll(np.roll(src.astype(np.float64), dy, 0), dx, 1)
            acc += sh
            cnt += sc
        hit = todo & (cnt > 0)
        rgb[hit] = acc[hit] / cnt[hit][:, None]
        src = src | hit
        todo = todo & (~hit)
    out = arr.copy()
    out[..., :3] = np.clip(rgb, 0, 255).astype(np.uint8)
    return out


def _emit(att, crgb, ca, bw, bh, sprites_dir, anchors):
    """公用收尾：镜像 / 旋转 / 按锚点几何定尺寸 / 出 1× 和 @2x。"""
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
    # socket 挂件的位置由挂点表负责，附件表只保留头高比例尺寸；此时不能
    # 调 resolve() 要求 ref/pos_rel（socket 迁移后这两个字段有意移除了）。
    if att.get("socket") and "pos_rel" not in att:
        h1 = int(round(float(att["sprite_h_rel"])
                       * attach_geom.unit_px(anchors, att.get("unit", "head"))))
    else:
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
        arr = scrub_key(np.asarray(out))
        out = Image.fromarray(arr, "RGBA")
        leftover = left_magenta(arr[..., :3], arr[..., 3] / 255.0)
        if leftover:
            raise SystemExit("[attach] %s %s 还剩 %d 个洋红像素"
                             % (att["id"], name, leftover))
        out.save(os.path.join(sprites_dir, name))
        made.append(name)
    return w1, h1, made, float((ca > 0.5).sum()) / float(ca.size)


def derive_source(spec, sprites_dir, design_dir):
    """从**本体已有的那张贴图**派生一个挂件素材（而不是外挂一张 AI 碎片）。

    ★ 这是 2026-10-18 第十三问之后改的产线口径。此前每个发型件都是**单独**生成
      的一张 AI 图，彼此之间没有共同的几何/光照/轮廓约束，于是：
        · 长发的长鬓发是粉的，本体的头发是淡紫的 —— 用户说「接发痕迹太明显」；
        · 扎发的脸侧细缕和本体的鬓发不是一回事 —— 用户说「前发也不自然」。
      按着原画拉长 / 压窄出来的件，**逐像素都是本体那张图的颜色和笔触**，
      接缝从定义上就不存在。Live2D 的髪型差分本来也是在同一张原画上改的。

    spec 字段：
      sprite      从 sprites/ 里取（本体贴图，已经是干净 RGBA）
      design      从 design/ 里取（程序化画的件，比如兜帽）
      stretch     {top, bottom, to_height}：上下各留多少比例不动，
                  中段纵向拉伸到总高 to_height。只拉中段是因为**发根的走向和
                  发梢的收口**都不能变形，能拉的只有中间那段发丝。
      taper       底部横向收窄系数（1.0 = 不收）
      curve_px    底部横向偏移像素（让发缕自然地往外/往内飘一点）
    """
    if spec.get("design"):
        p = os.path.join(design_dir, spec["design"])
    else:
        p = os.path.join(sprites_dir, spec["sprite"])
    if not os.path.exists(p):
        raise SystemExit("[attach] derive 缺源图 %s" % p)
    arr = np.asarray(Image.open(p).convert("RGBA")).astype(np.float64)
    rgb, al = arr[..., :3], arr[..., 3] / 255.0

    st = spec.get("stretch")
    if st:
        h = rgb.shape[0]
        t = max(1, int(round(h * float(st.get("top", 0.3)))))
        b = max(1, int(round(h * float(st.get("bottom", 0.15)))))
        mid = h - t - b
        if mid < 4:
            raise SystemExit("[attach] derive stretch：中段只剩 %d 行" % mid)
        want = int(st["to_height"])
        new_mid = max(4, want - t - b)
        band = Image.fromarray(
            np.dstack([rgb, al * 255.0]).astype(np.uint8)[t:t + mid], "RGBA")
        band = band.resize((rgb.shape[1], new_mid), Image.LANCZOS)
        ba = np.asarray(band).astype(np.float64)
        rgb = np.vstack([rgb[:t], ba[..., :3], rgb[t + mid:]])
        al = np.vstack([al[:t], ba[..., 3] / 255.0, al[t + mid:]])

    taper = float(spec.get("taper", 1.0))
    curve = float(spec.get("curve_px", 0.0))
    if taper != 1.0 or curve != 0.0:
        h, w = al.shape
        cx = (w - 1) / 2.0
        # 从"开始拉伸的那一行"起才收窄 —— 发根那一截要和本体严丝合缝
        y0 = int(round(h * float((st or {}).get("top", 0.25)))) if st else 0
        out_rgb = np.empty_like(rgb)
        out_a = np.empty_like(al)
        xs = np.arange(w, dtype=np.float64)
        for y in range(h):
            u = 0.0 if y <= y0 else (y - y0) / max(1.0, (h - 1 - y0))
            s = 1.0 + (taper - 1.0) * (u ** 1.3)
            off = curve * (u ** 1.8)
            src = cx + (xs - cx - off) / max(1e-3, s)
            i0 = np.clip(np.floor(src).astype(int), 0, w - 1)
            i1 = np.clip(i0 + 1, 0, w - 1)
            f = np.clip(src - np.floor(src), 0, 1)[:, None]
            out_rgb[y] = rgb[y][i0] * (1 - f) + rgb[y][i1] * f
            out_a[y] = (al[y][i0] * (1 - f[:, 0]) + al[y][i1] * f[:, 0]) * \
                np.where((src < -0.5) | (src > w - 0.5), 0.0, 1.0)
        rgb, al = out_rgb, out_a
    return rgb, al


_GRP_CACHE = {}


def group_src_lab(group, table, redraw_dir):
    """把**同一组**（= 同一张套准模板）所有发片的实心像素合成一个 Lab 池。

    为什么要整组一起算：见 match_colors 里 src_lab_pool 的注释 —— 逐片各算
    一套系数必然在片与片的接缝上留色差。组的粒度取「一张模板」而不是
    「全部发型」，是因为七张模板是分别出图的，整体明度本来就有差；
    按模板分组，组内接缝严丝合缝，组间差异由各自的均值对齐抹平。
    """
    if group in _GRP_CACHE:
        return _GRP_CACHE[group]
    pool = []
    for a2 in (table or {}).get("attachments", []):
        rm2 = a2.get("recolor_match") or {}
        if rm2.get("stats_group") != group or not a2.get("source"):
            continue
        sp = os.path.join(redraw_dir, a2["source"])
        if not os.path.exists(sp):
            continue
        arr = np.asarray(Image.open(sp).convert("RGB"), dtype=np.uint8)
        bg2 = bg_color(arr)
        ca2 = key_alpha_soft(arr, bg2)
        aa2 = ca2[..., None]
        up2 = np.clip((arr.astype(np.float64) - (1.0 - aa2) * bg2.astype(np.float64))
                      / np.maximum(aa2, 1e-3), 0, 255)
        sel = ca2 > SOLID_A
        if sel.sum() < 64:
            continue
        px = up2[sel]
        if len(px) > 120000:                 # 抽稀，统计量足够且省内存
            px = px[::max(1, len(px) // 120000)]
        pool.append(px)
    if not pool:
        _GRP_CACHE[group] = None
        return None
    allpx = np.concatenate(pool, 0)
    lab = _srgb_to_lab(allpx.reshape(-1, 1, 3))[:, 0, :]
    print("[attach] 组 %-10s 源统计池 %d 像素（%d 片共用一套系数）"
          % (group, len(lab), len(pool)))
    _GRP_CACHE[group] = lab
    return lab


def build_one(att, slot, redraw_dir, sprites_dir, anchors, design_dir=None,
              table=None):
    if att.get("derive"):
        crgb, ca = derive_source(att["derive"], sprites_dir, design_dir or redraw_dir)
        bh, bw = ca.shape
        return _emit(att, crgb, ca, bw, bh, sprites_dir, anchors)

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
                            float(rm.get("keep", 1.0)),
                            float(rm.get("l_sigma_max", 2.5)),
                            float(rm.get("l_offset", 0.0)),
                            src_lab_pool=(group_src_lab(rm["stats_group"],
                                                        table, redraw_dir)
                                          if rm.get("stats_group") else None))
    elif att.get("recolor"):
        ca = key_alpha(canvas, bg)
        crgb = bleed_edge(relay_colors(canvas, ca, att["recolor"]), ca)
    else:
        # 保留渐变的路径：精确 alpha + 反预乘去边。
        ca = key_alpha_soft(canvas, bg)
        aa = ca[..., None]
        crgb = canvas.astype(np.float64) - (1.0 - aa) * bg.astype(np.float64)
        crgb = np.clip(crgb / np.maximum(aa, 1e-3), 0, 255)
        # ★★★ 2026-10-21 第二十九问：这里**必须**也抹一遍边。
        #   以前只有 recolor_match 分支调 bleed_edge，这条「原色直通」分支没调。
        #   反预乘在 a→0 的地方是 (观测−底色)/a，分母 0.02 就把噪声放大 40 倍，
        #   实测长发件里躺着 rgba=(255,212,255,6) 这种像素 —— **alpha 快到 0 了，
        #   RGB 通道却还是洋红**。它自己看不见，可是 @2x 放大（LANCZOS）和
        #   GPU 采样都按直通 RGB 插值，洋红就被混进旁边的实心发丝里。
        #   长发整片都是细缕、边缘占比极高 ⇒ 整条发帘泛粉。
        #   bleed_edge 把 a<0.15 的像素颜色换成邻域实心色，alpha 一个都不动。
        crgb = bleed_edge(crgb, ca)

    # ★ 内部补实（默认开）：见 harden_interior 的文档串 —— 淡紫头发会被洋红键
    #   系统性抠成半透明。个别确实要半透明的件可以写 "solid_fill": false 关掉。
    if att.get("solid_fill", True):
        ca = harden_interior(ca)

    return _emit(att, crgb, ca, bw, bh, sprites_dir, anchors)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    ap.add_argument("--character", required=True)
    ap.add_argument("--form", required=True)
    ap.add_argument("--only", default="",
                    help="逗号分隔的挂件 id；只重做指定挂件并合并原 attach_parts.json")
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
    all_attachments = [att for att in table["attachments"]
                       if not att.get("forms") or a.form in att["forms"]]
    only = {x.strip() for x in a.only.split(",") if x.strip()}
    known_ids = {att["id"] for att in all_attachments}
    unknown = only - known_ids
    if unknown:
        raise SystemExit("[attach] --only 有未知挂件 id：" + ", ".join(sorted(unknown)))

    dst = os.path.join(sprites, "attach_parts.json")
    previous = {}
    if only:
        if not os.path.exists(dst):
            raise SystemExit("[attach] --only 需要现有 attach_parts.json 以保留未选条目")
        with io.open(dst, encoding="utf-8") as f:
            old = json.load(f)
        previous = {entry["id"]: entry for entry in old.get("attachments", [])}
        missing = known_ids - only - previous.keys()
        if missing:
            raise SystemExit("[attach] --only 无法保留缺失的既有条目：" + ", ".join(sorted(missing)))
    out = {"schema_version": "1.0", "slots": table["slots"], "attachments": []}
    entries = dict(previous) if only else {}
    for att in all_attachments:
        if only and att["id"] not in only:
            continue
        slot = slots.get(att["slot"])
        if slot is None:
            raise SystemExit("[attach] %s 落在不存在的插槽 %r"
                             % (att["id"], att["slot"]))
        w, h, made, cover = build_one(
            attach_geom.apply_overrides(att, _ovr), slot, redraw, sprites, anchors,
            design_dir=os.path.join(base, "design"), table=table)
        entries[att["id"]] = {
            "id": att["id"], "slot": att["slot"],
            "file": "sprites/" + att["sprite"],
            "size": [w, h],
        }
        print("[attach] %-10s → 槽 %-18s %dx%d（覆盖 %.0f%%）"
              % (att["id"], att["slot"], w, h, cover * 100))

    out["attachments"] = [entries[att["id"]] for att in all_attachments
                          if att["id"] in entries]
    if len(out["attachments"]) != len(all_attachments):
        missing = known_ids - entries.keys()
        raise SystemExit("[attach] 输出表缺少挂件：" + ", ".join(sorted(missing)))
    with io.open(dst, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print("写出 %s：%d 件 / %d 槽" % (dst, len(out["attachments"]), len(slots)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
