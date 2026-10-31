#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""make_star_eye_parts.py —— 星星眼的 L1 与 L3 两层素材（T39.1 / T39.1b）。

为什么要分层
------------
2026-10-16 查了一圈日文 Live2D 教程（结论写在 docs/REFERENCE_NOTES.md 第二十五批），
「星星眼」在原画/建模口径里**从来不是一张贴图**，而是三层叠出来的：

    L1  星形瞳孔      —— 把虹膜本身换成一颗填满瞳孔的星（きらきら目差分）
    L2  眼内多层高光  —— 大高光 + 碎钻反光；**这层才决定"像不像动漫少女的眼睛"**
    L3  画面 ✨ 特效  —— 脸周围飘的闪光，和眼睛是两回事

第一版只做了 L1 而且配色抄错（照着用户截图里**小埋**的金色做，小寻的瞳色是
蓝 #4A8FD4），被用户两次打回。现在：L1 + L2 合画进同一张虹膜贴图（高光画在
虹膜上，和官方拆件口径「瞳 / 瞳的高光」一致，省一个部件），L3 单独一张素材。

本脚本做两件事
--------------
    1) 星形虹膜差分件  design/redraw/eye_star_iris.png → eye_{l,r}_ball_star.png
       尺寸、锚点、alpha 轮廓**完全照抄** eye_{l,r}_ball.png，
       所以它能原地盖住常态虹膜，由 ParamStarEye 做不透明度交叉切换
       （= 日文教程里的「差分パーツを不透明度 0↔100 で切り替える」）。

    2) 闪光特效素材    design/redraw/fx_sparkle.png → fx_sparkle.png（一张）
       カワナミ 的做法：**素材只要一张**，大中小和散布全靠复制 + 变形，
       每颗各自一个参数（共用参数会整齐划一地闪，一眼假）。
       本脚本只出素材 + 一张散布表，参数/动作由 make_rig.py 生成。

抠像口径
--------
两张源图都是洋红底（#FF00FF 系，实测边框中位数 (239,9,232) / (233,5,221)）。
键色判据走 **G 通道**：底色 G≈5~12，内容 G 最高 255，单通道就够分，
不用再调三通道容差。缩放一律走**预乘 alpha**（premultiply → resize → unpremultiply），
否则缩小时洋红会被插值进边缘，变成 check_assets 的「键色垃圾像素」。

用法
----
    ~/.imgenv/bin/python tools/make_star_eye_parts.py --character xiaoxun --form teen
"""
from __future__ import annotations

import argparse
import json
import io
import os
import sys

import numpy as np
from PIL import Image, ImageFilter

# —— 键色 ——
# 两张源图都是洋红底。**不能只看 G 通道**：虹膜那圈深海军蓝描边是 (13,19,45)，
# G 只有 19，拿 G 当键会把描边判成背景，despill 再除以 ~0 → 整圈变荧光绿
# （2026-10-16 首版实测，logs/asset_qa/iris_scale_probe.png 左三格）。
# 正确口径是**离底色多远**：pix = fg·a + bg·(1−a) ⇒ ‖pix−bg‖ = a·‖fg−bg‖，
# 所以覆盖度 = 离底色的欧氏距离 / 内容离底色的典型距离。深色、浅色一视同仁。
KEY_D_LO = 0.055       # 归一化距离 ≤ 这个数 = 纯底（吃掉底色自身的噪声，实测 std≈0.04）
KEY_D_HI = 0.260       # ≥ 这个数 = 纯内容；中间线性 = 抗锯齿边 / 辉光过渡
MAGENTA_R = 150        # 判「还是洋红」用：R−G>60 且 B−G>60 且 R>150 且 B>150
MAGENTA_B = 150
MAGENTA_G = 60

SUPER = 4              # 中间分辨率倍率（先缩到 4× 目标再做颜色外溢，最后缩到位）
BLEED_ITERS = 6        # 4× 分辨率下往外糊几圈（≈1.5 个目标像素）
SOLID_A = 0.85         # 只有覆盖度高过这个的像素才算「颜色可信」，其余一律重糊。
#   为什么不是 0.5：despill 要除以 alpha，最外那圈半透明像素误差被放大到离谱
#   —— 实测虹膜最外环（r/R 0.99~1.02，a≈0.14）despill 出来是 (90,143,30) 的脏绿，
#   G−max(R,B)=53，离 check_assets 的「纯绿垃圾」阈值 60 只差 7。不要赌这 7。
SHARPEN = (1.1, 85, 2)  # UnsharpMask(radius, percent, threshold)：见 build_star_iris

# 闪光的调色板（#4A8FD4 系）。只借 AI 图的**形状与明暗**，颜色按角色配色表重铺：
# 加算混合下任何一点洋红残留都会发成紫点，而 despill 在 alpha<0.2 的辉光尾部
# 本来就不稳。重铺之后「素材里不可能出现洋红」是构造性保证，不是靠阈值赌。
SPARK_CORE = np.array([255.0, 255.0, 255.0])   # 芯：纯白
SPARK_MID = np.array([198.0, 228.0, 255.0])    # 中段：冰蓝白
SPARK_TIP = np.array([74.0, 143.0, 212.0])     # 尖：#4A8FD4

# 虹膜的调色梯（从暗到亮）。**每一站都取自 design/palette.json**，站与站之间
# 的 L1 距离都压在 ~80 以内，所以插值出来的任何一个颜色离色卡都不会超过 40 ——
# check_assets 的「色卡」闸上限是 70（L1）。
#
# 为什么必须重铺：AI 出图的虹膜外圈是 #181878（偏紫的深蓝），离色卡最近的
# 「瞳孔深蓝 #385783」L1 距离 100，闸直接判红。这不是闸太严 —— 用户两次打回的
# 第一条就是「配色不对」（上一版我做成了小埋的金瞳）。所以只借 AI 的**明暗结构**，
# 颜色一律落回小寻自己的色卡。
# —— 程序化四角 sparkle 的几何（见 star_mask_proc）——
STAR_P = 0.50          # astroid 指数：<1 才有内凹的尖角；越小越尖
STAR_FILL_X = 0.90     # 星的横向半径 / 虹膜半径
STAR_FILL_Y = 1.00     # 纵向半径 / 虹膜半径（参考图里星略呈纵长）

STAR_SPLIT_Q = 42      # （旧路：从 AI 图分割星形用的亮度分位）
STAR_FLOOR = 0.72      # 星内亮度下限（映射到色卡梯的 [STAR_FLOOR, 1.0] = 淡蓝→白）
STAR_LIFT = 0.24       # 星内相对**当地底色**至少抬这么多 —— 常态虹膜下半本来就亮，
#                        只按绝对亮度映射的话星在下半截会和底一样白、读不出来。
EDGE_COLOR = (0x2C, 0x29, 0x39)   # 星形描边色 = 色卡「眼线睫毛 #2C2939」
EDGE_MIX = 0.80        # 描边浓度
#   为什么要描边：参考实物（ac-illust「アニメ風キラキラ目」）里瞳孔都有深色边，
#   亮形状靠深边才"咬"得住。注意这和"源图自带的 1px 描边"不是一回事 ——
#   那条线是在 2048px 上画的，缩到 31px 就没了；这条是**在最终分辨率上画**的，
#   1× 画 1px、2× 画 2px，缩放不会吃掉它。
OPEN_R = 40            # 数角之前开运算的半径（源分辨率像素）。
#   实测扫过 14/22/30/40/50：≤30 仍数出 6（细颈没断），≥40 才稳定数出 5，
#   而 r=40 只吃掉星形 4.7% 的面积（r=50 是 7.0%）—— 取 40，离阈值两边都有余量。
STAR_CONTRAST_MIN = 30.0  # 最终 31px 贴图上「星内 − 星外」的亮度差下限
# ⚠ 这条只是"星读不读得出来"的下限，**不是越大越好**：第一版靠把底压黑把它刷到 108，
#   结果是整只眼睛发黑（用户打回）。所以另加一条上限，见 GROUND_KEEP_MIN。
EDGE_CONTRAST_MIN = 18.0  # 描边必须比底深这么多（否则亮星在亮底上咬不住）
GROUND_KEEP_MIN = 0.92    # 星外区域必须和常态虹膜**几乎逐像素一致**（相似度下限）
#   第二版的做法保证星外一个像素都不动，所以这条实测是 1.000；
#   它存在的意义是：以后谁再想"顺手调一下整只虹膜的色调"，这条会立刻红。

IRIS_RAMP = [
    (0.00, "#2C2939"),   # 眼线睫毛（线稿最深）—— 虹膜外描边
    (0.12, "#324868"),   # ↑↓ 两站之间的插值站
    (0.24, "#385783"),   # 瞳孔深蓝
    (0.38, "#4173AB"),
    (0.52, "#4A8FD4"),   # 眼睛主色
    (0.66, "#74A7DE"),
    (0.80, "#9FC4E8"),   # 发梢淡蓝（眼内反光那一圈）
    (0.90, "#CFE1F3"),
    (1.00, "#FFFFFF"),   # 高光
]

# —— 闪光散布表 ——
# ✨ 的几何、尺寸档、动法全部搬到 **design/effects.json**（T43.2 / G117）。
# 这里只负责"按表出图"，不再持有任何一颗的坐标 —— 加一种新漫符不该改这个文件。
# load_effect() 在 main 里调用后填充下面三个模块级变量。
SPARKLES = []           # [(u, v, size, rot_deg, freq, phase), ...]
SPARKLE_PX = 0          # 1× 素材边长
SPARKLE_SCALE = {}      # {"lg": 1.0, ...}


def load_effect(design_dir, eff_id="sparkle"):
    """从 design/effects.json 取一组特效的声明，填进模块级变量。

    刻意不做默认值兜底：表里缺字段就直接炸，而不是悄悄用一个硬编码的旧值
    —— 那正是 G117 要消灭的东西（源码里藏着一份影子配置）。
    """
    global SPARKLES, SPARKLE_PX, SPARKLE_SCALE
    path = os.path.join(design_dir, "effects.json")
    with io.open(path, encoding="utf-8") as f:
        tbl = json.load(f)
    hit = [e for e in tbl["effects"] if e["id"] == eff_id]
    if not hit:
        raise SystemExit(f"[star_eye] {path} 里没有 id={eff_id} 的特效组")
    e = hit[0]
    SPARKLE_PX = int(e["sprite_px"])
    SPARKLE_SCALE = dict(e["size_class"])
    SPARKLES = [(i["u"], i["v"], i["size"], i["rot_deg"], i["freq"], i["phase"])
                for i in e["instances"]]
    for _, _, sz, _, _, _ in SPARKLES:
        if sz not in SPARKLE_SCALE:
            raise SystemExit(f"[star_eye] effects.json: size={sz!r} 不在 size_class 表里")
    freqs = [i[4] for i in SPARKLES]
    if len(set(freqs)) != len(freqs):
        raise SystemExit("[star_eye] effects.json: freq 必须两两不同，"
                         "否则跑久了会重新对齐，又变成『整齐划一地闪』")
    return e


# ----------------------------------------------------------------- 小工具
def key_alpha(rgb: np.ndarray, bg: np.ndarray) -> np.ndarray:
    """洋红底 → 覆盖度 0..1（离底色的欧氏距离，深色内容也认得出）。"""
    d = np.linalg.norm(rgb.astype(np.float64) - bg[None, None, :], axis=-1) / 441.67
    return np.clip((d - KEY_D_LO) / (KEY_D_HI - KEY_D_LO), 0.0, 1.0)


def despill(rgb: np.ndarray, a: np.ndarray, bg: np.ndarray) -> np.ndarray:
    """把已知底色从半透明边缘里减掉：pix = fg*a + bg*(1-a) → fg = (pix-bg*(1-a))/a。"""
    af = np.maximum(a, 1e-3)[..., None]
    fg = (rgb.astype(np.float64) - bg[None, None, :] * (1.0 - af)) / af
    return np.clip(fg, 0.0, 255.0)


def premul_resize(rgb: np.ndarray, a: np.ndarray, size) -> tuple:
    """预乘 alpha 之后再缩放，回来再除掉。直接缩 RGB 会把底色插值进边缘。"""
    pre = Image.fromarray(np.clip(rgb * a[..., None], 0, 255).astype(np.uint8), "RGB")
    am = Image.fromarray(np.clip(a * 255.0, 0, 255).astype(np.uint8), "L")
    pre = np.asarray(pre.resize(size, Image.LANCZOS)).astype(np.float64)
    a2 = np.asarray(am.resize(size, Image.LANCZOS)).astype(np.float64) / 255.0
    out = pre / np.maximum(a2, 1e-3)[..., None]
    return np.clip(out, 0.0, 255.0), np.clip(a2, 0.0, 1.0)


def bleed(rgb: np.ndarray, known: np.ndarray, iters: int) -> np.ndarray:
    """把已知像素的颜色往外糊 iters 圈（四邻域均值），消掉缩放时的边缘脏色。"""
    out = rgb.copy()
    k = known.copy()
    for _ in range(iters):
        if k.all():
            break
        acc = np.zeros_like(out)
        cnt = np.zeros(k.shape, np.float64)
        for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            s = np.roll(np.roll(out, dy, 0), dx, 1)
            m = np.roll(np.roll(k, dy, 0), dx, 1)
            acc += s * m[..., None]
            cnt += m
        new = (~k) & (cnt > 0)
        if not new.any():
            break
        out[new] = acc[new] / cnt[new][..., None]
        k = k | new
    return out


def largest_blob(mask: np.ndarray) -> np.ndarray:
    """取最大连通块（四邻域，迭代式膨胀而不是递归，2048² 也不会爆栈）。"""
    h, w = mask.shape
    ys, xs = np.nonzero(mask)
    if ys.size == 0:
        return mask
    # 从质心附近的一个 True 像素起洪水：星形虹膜/闪光都只有一个主体，
    # 真要有碎点也离主体远，取最大块等价于「从主体长出去」。
    cy, cx = int(ys.mean()), int(xs.mean())
    if not mask[cy, cx]:
        d = (ys - cy) ** 2 + (xs - cx) ** 2
        i = int(np.argmin(d))
        cy, cx = int(ys[i]), int(xs[i])
    cur = np.zeros_like(mask)
    cur[cy, cx] = True
    while True:
        nxt = cur.copy()
        for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nxt |= np.roll(np.roll(cur, dy, 0), dx, 1)
        nxt &= mask
        if nxt.sum() == cur.sum():
            return nxt
        cur = nxt


def bbox(mask: np.ndarray):
    ys, xs = np.nonzero(mask)
    return int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1


def border_bg(rgb: np.ndarray) -> np.ndarray:
    edge = np.concatenate([rgb[0, :], rgb[-1, :], rgb[:, 0], rgb[:, -1]])
    return np.median(edge, axis=0).astype(np.float64)


def keycolor_left(rgb: np.ndarray, a: np.ndarray) -> int:
    """还剩几个「看得见的洋红」像素 —— check_assets 那道闸的同口径（alpha>40）。"""
    vis = a > (40 / 255.0)
    mag = ((rgb[..., 0] > MAGENTA_R) & (rgb[..., 2] > MAGENTA_B)
           & (rgb[..., 1] < MAGENTA_G))
    return int((vis & mag).sum())


# ----------------------------------------------------------------- L1 星形虹膜
def _fit(crop_rgb, crop_a, box_w, box_h, disc_box, sharpen=True, star_src=None):
    """把虹膜源图塞进「常态虹膜的 alpha 圆」那块地方，返回 box_h×box_w×3 的 RGB。

    关键是**对齐到 alpha 圆而不是整张贴图**：eye_l_ball.png 是 31×30 的框，
    里面的圆只有 27×28。按整框缩放会把虹膜外圈那道海军蓝描边顶到框外、再被
    alpha 裁掉 —— 首版就是这么丢的（星星像块蓝饼，没有眼眶感）。
    """
    dx0, dy0, dx1, dy1 = disc_box
    dw, dh = dx1 - dx0, dy1 - dy0
    mid = (dw * SUPER, dh * SUPER)
    rgb4, a4 = premul_resize(crop_rgb, crop_a, mid)
    rgb4 = bleed(rgb4, a4 > SOLID_A, BLEED_ITERS)
    img = Image.fromarray(rgb4.astype(np.uint8), "RGB")
    if sharpen:
        # 缩 30 倍之后，1px 的星形描边会被低通掉 —— 先在 4× 中间尺度上
        # 锐一刀，让描边在最终尺度上还剩得下一点对比度（阈值 2 是为了不把
        # 虹膜内部的柔和渐变也搓出硬边）。
        img = img.filter(ImageFilter.UnsharpMask(SHARPEN[0], SHARPEN[1], SHARPEN[2]))
    small = np.asarray(img.resize((dw, dh), Image.LANCZOS)).astype(np.float64)
    out = np.zeros((box_h, box_w, 3), np.float64)
    out[dy0:dy1, dx0:dx1] = small
    # 圆外那一圈（框角）虽然 alpha=0，仍旧糊上邻近颜色：make_hires 的 alpha 是
    # LANCZOS 插值出来的，会把 alpha 抬到 0 以上一点，那时框角的黑就会露出来。
    known = np.zeros((box_h, box_w), bool)
    known[dy0:dy1, dx0:dx1] = True
    out = bleed(out, known, 4)
    if star_src is None:
        return out, None
    sm = np.asarray(Image.fromarray((star_src * 255).astype(np.uint8), "L")
                    .resize((dw, dh), Image.LANCZOS)) > 128
    mask = np.zeros((box_h, box_w), bool)
    mask[dy0:dy1, dx0:dx1] = sm
    return out, mask


def _ramp(stops):
    t = np.array([q for q, _ in stops])
    c = np.array([[int(h[1:3], 16), int(h[3:5], 16), int(h[5:7], 16)]
                  for _, h in stops], float)
    return t, c


def star_mask_proc(shape) -> np.ndarray:
    """★★★ 2026-10-21 第三十问：**程序化**四角 sparkle，不再从 AI 图里分割。

    用户给了参考图（`logs/asset_qa/user/q29_6.png`）：**整颗虹膜一枚四角星**，
    角细、腰收、对比强。而我们原来的做法是「从 AI 原图里按亮度分位切出星形」，
    切出来的是一枚**偏小的五角星**（实测占虹膜 29%，角数 5），
    放到 31px 的贴图上只剩几个像素的亮斑 —— 用户说「没看到星星」是对的。

    为什么改成程序化：星形是**纯几何**，没有任何理由依赖一张 AI 图。
    从图里分割有三个固有缺点：① 形状由那张图决定（想要四角就得重新出图）；
    ② 大小由分位阈值决定，调不准；③ 还得靠开运算掐掉它伸出去的细颈。
    换成解析式之后，角数/大小/腰粗都是可调常量，而且**在源分辨率上生成**，
    缩到 31px 时边缘由 LANCZOS 自然抗锯齿，比分割出来的锯齿边干净。

    形状用 **astroid 家族**（星芒曲线）：|x/rx|^p + |y/ry|^p ≤ 1。
      · p = 2 是椭圆；p = 1 是菱形；**p < 1 时边向内凹，就是 sparkle 的尖角**。
      · p 越小角越尖、腰越细。p=0.62 实测和参考图那枚最接近。
    竖轴比横轴长一点（STAR_FILL_Y > STAR_FILL_X），和参考图一样略呈纵长。
    """
    h, w = shape
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float64)
    cx, cy = (w - 1) / 2.0, (h - 1) / 2.0
    rx = max(w * 0.5 * STAR_FILL_X, 1.0)
    ry = max(h * 0.5 * STAR_FILL_Y, 1.0)
    u = np.abs(xx - cx) / rx
    v = np.abs(yy - cy) / ry
    return (u ** STAR_P + v ** STAR_P) <= 1.0


def star_mask_of(rgb: np.ndarray, a: np.ndarray) -> np.ndarray:
    """从 AI 原图里把**星形区域**分割出来。只要形状，不要它的颜色。

    2026-10-16 第二版。第一版是「按色卡重铺整只虹膜」，被用户打回：
    「星星眼的蓝色部分过于深色黑，以及颜色没有类似眼睛的色彩变化，
      导致也很怪，感觉像眼睛突然黑了，里面有点东西也不明显，反而没看到星星。」
    —— 说得完全对。第一版为了让星"读得出来"，把星以外的整只虹膜压到色卡梯的
    最暗段（GROUND_HI=0.34，起点是近黑的 #2C2939），于是指标（星内外亮度差 108）
    涨了、眼睛却黑成一坨。**对比度是靠压黑底换来的，不是靠把星提亮。**

    参考实物（ac-illust「アニメ風キラキラ目」等）：キラキラ目 = 在**原本的虹膜**上
    加亮点，虹膜自己那套"上深下亮、饱和蓝"的渐变原样保留。不是重铺。

    所以第二版只从 AI 图里取星形**遮罩**，颜色一律由常态虹膜那张贴图提供。
    """
    lum = rgb @ np.array([0.299, 0.587, 0.114])
    vis = a > SOLID_A
    if not vis.any():
        return np.zeros(lum.shape, bool)
    return largest_blob((lum > np.percentile(lum[vis], STAR_SPLIT_Q)) & vis)


def paint_star(base_rgb: np.ndarray, base_a: np.ndarray,
               star: np.ndarray, edge_w: int = 1) -> np.ndarray:
    """把星形"点亮"在常态虹膜上：底原样不动，只有星内抬亮度。

    星内的新亮度 = STAR_FLOOR + (1-STAR_FLOOR) × 底自己的亮度
    —— 保留底的明暗起伏（上深下亮那套），所以星里面也有渐变，
    不是一块死白。星外一个像素都不碰，颜色变化自然和常态眼完全一致。
    """
    vis = base_a > SOLID_A
    if not (vis.any() and star.any()):
        return base_rgb
    lum = base_rgb @ np.array([0.299, 0.587, 0.114])
    lo, hi = np.percentile(lum[vis], 2), np.percentile(lum[vis], 98)
    t = np.clip((lum - lo) / max(hi - lo, 1e-6), 0.0, 1.0)
    ts, cs = _ramp(IRIS_RAMP)
    out = base_rgb.copy()
    t2 = np.clip(np.maximum(STAR_FLOOR + (1.0 - STAR_FLOOR) * t, t + STAR_LIFT), 0.0, 1.0)
    for k in range(3):
        ch = np.interp(t2, ts, cs[:, k])
        out[..., k] = np.where(star, ch, out[..., k])
    # 描边：星形最外一圈压深，让亮星在亮底上也咬得住
    edge = star & ~_erode(star, edge_w)
    for k in range(3):
        out[..., k] = np.where(edge,
                               out[..., k] * (1.0 - EDGE_MIX) + EDGE_COLOR[k] * EDGE_MIX,
                               out[..., k])
    return out


def build_star_iris(src_path: str, sprites: str, report: dict) -> list:
    im = np.asarray(Image.open(src_path).convert("RGB")).astype(np.float64)
    bg = border_bg(im)
    a = key_alpha(im, bg)
    disc = largest_blob(a > 0.5)
    x0, y0, x1, y1 = bbox(disc)
    side = max(x1 - x0, y1 - y0)                 # 虹膜是圆，用外接正方形
    cx, cy = (x0 + x1) // 2, (y0 + y1) // 2
    x0, y0 = max(0, cx - side // 2), max(0, cy - side // 2)
    x1, y1 = min(im.shape[1], x0 + side), min(im.shape[0], y0 + side)
    crop_rgb, crop_a = im[y0:y1, x0:x1], a[y0:y1, x0:x1]
    crop_rgb = despill(crop_rgb, crop_a, bg)
    # ★ 2026-10-21：星形改成程序化生成（见 star_mask_proc 的文档串）。
    #   旧的 star_mask_of 留着没删 —— 它是"从图里分割"那条路的实现，
    #   万一以后要换成画师手绘的星形贴图，这条路还用得上。
    star_mask = star_mask_proc(crop_a.shape) & (crop_a > 0.0).any() if False \
        else star_mask_proc(crop_a.shape)
    star_ratio = float(star_mask.sum()) / max(float((crop_a > SOLID_A).sum()), 1.0)

    out = []
    for tag in ("l", "r"):
        ball_path = os.path.join(sprites, f"eye_{tag}_ball.png")
        if not os.path.exists(ball_path):
            raise SystemExit(f"[star_eye] 缺 {ball_path} —— 先跑 make_eye_parts.py")
        ball = Image.open(ball_path).convert("RGBA")
        bw, bh = ball.size
        alpha1 = ball.split()[3]
        am = np.asarray(alpha1).astype(np.float64) / 255.0
        d_box = bbox(am > 0.5)                   # 真正画着虹膜的那块

        base1 = np.asarray(ball.convert("RGB")).astype(np.float64)
        _, sm1 = _fit(crop_rgb, crop_a, bw, bh, d_box, star_src=star_mask)
        rgb1 = paint_star(base1, am, sm1)
        px = np.zeros((bh, bw, 4), np.uint8)
        px[..., :3] = np.clip(rgb1, 0, 255).astype(np.uint8)
        px[..., 3] = np.asarray(alpha1)          # 轮廓完全照抄常态虹膜
        fn = f"eye_{tag}_ball_star.png"
        Image.fromarray(px, "RGBA").save(os.path.join(sprites, fn))

        # 2× 直接拿**常态虹膜的 2× 成品**当底（所以本工具必须排在 make_hires_sprites 之后）。
        # 这样星形件和常态件在星以外的区域逐像素相同 —— 两张图切换时不会有
        # "锐度忽然变一下"的跳感；而星形边缘来自 2048px 源图，依然干净。
        b2p = os.path.join(sprites, f"eye_{tag}_ball@2x.png")
        if not os.path.exists(b2p):
            raise SystemExit(f"[star_eye] 缺 {b2p} —— 本工具必须排在 make_hires_sprites 之后")
        ball2 = Image.open(b2p).convert("RGBA")
        bw2, bh2 = ball2.size
        if (bw2, bh2) != (bw * 2, bh * 2):
            raise SystemExit(f"[star_eye] {b2p} 不是 1x 的两倍（{bw2}x{bh2} vs {bw*2}x{bh*2}）")
        a2 = ball2.split()[3]
        am2 = np.asarray(a2).astype(np.float64) / 255.0
        d_box2 = bbox(am2 > 0.5)
        _, sm2 = _fit(crop_rgb, crop_a, bw2, bh2, d_box2, star_src=star_mask)
        rgb2 = paint_star(np.asarray(ball2.convert("RGB")).astype(np.float64),
                          am2, sm2, edge_w=2)      # 2× 上描边也要 2px
        px2 = np.zeros((bh2, bw2, 4), np.uint8)
        px2[..., :3] = np.clip(rgb2, 0, 255).astype(np.uint8)
        px2[..., 3] = np.asarray(a2)
        Image.fromarray(px2, "RGBA").save(os.path.join(sprites, f"eye_{tag}_ball_star@2x.png"))

        left = keycolor_left(px[..., :3].astype(np.float64), am)
        if left:
            raise SystemExit(f"[star_eye] {fn} 还剩 {left} 个洋红像素 —— 抠像没干净")

        # 判据一（T39.4）：星读不读得出来 = 最终 31px 贴图上「星内 - 星外」的亮度差。
        # 不用"数出几个角"：那个指标重跑之间会在 2~5 之间跳（圆周采样落在哪个像素上
        # 全看眼球 alpha 圆的 1px 抖动），拿它当验收等于掷骰子。
        # ⚠ 加了描边之后这个指标要重新定义：星形区域里最外一圈是**故意压深**的描边，
        #   把它算进"星内均值"会把均值拉下来，于是"描边画得越好、指标越红"（实测
        #   28.5 < 30 直接把自己拦下来了）。读得出读不出靠的是两个台阶，分别量：
        #     · 亮芯 vs 底   —— 星是亮的
        #     · 底   vs 描边 —— 边是深的，亮形状靠它"咬"住
        disc = am > 0.5
        lum1 = rgb1 @ np.array([0.299, 0.587, 0.114])
        core = disc & _erode(sm1, 1)
        ring = disc & sm1 & ~core
        outside = disc & ~sm1
        contrast = round(float(lum1[core].mean() - lum1[outside].mean()), 1)
        edge_c = round(float(lum1[outside].mean() - lum1[ring].mean()), 1)
        if contrast < STAR_CONTRAST_MIN:
            raise SystemExit(f"[star_eye] {fn} 亮芯比底只亮 {contrast}"
                             f"（下限 {STAR_CONTRAST_MIN}）—— 缩到这个尺寸就读不出星形了")
        if edge_c < EDGE_CONTRAST_MIN:
            raise SystemExit(f"[star_eye] {fn} 描边比底只深 {edge_c}"
                             f"（下限 {EDGE_CONTRAST_MIN}）—— 没有深边，亮星在亮底上糊掉")

        # 判据二（用户 2026-10-16 打回后加的）：**星以外必须还是那只眼睛**。
        # 量星外区域和常态虹膜的逐像素相似度，1.0 = 一个像素都没动。
        d_out = np.abs(rgb1 - base1).sum(axis=2)[outside]
        keep = round(float((d_out < 8).mean()), 3)
        if keep < GROUND_KEEP_MIN:
            raise SystemExit(f"[star_eye] {fn} 星外只有 {keep:.0%} 的像素和常态虹膜一致"
                             f"（下限 {GROUND_KEEP_MIN:.0%}）—— 又在动整只虹膜的颜色了")

        out.append({
            "side": tag, "file": f"sprites/{fn}", "size": [int(bw), int(bh)],
            "disc_box": [int(v) for v in d_box],
            "checks": {"keycolor_px": left, "star_contrast": contrast,
                       "edge_contrast": edge_c, "ground_kept": keep,
                       "star_px": int(core.sum())},
        })
    report["source_iris"] = os.path.relpath(src_path)
    report["iris_crop"] = [int(x0), int(y0), int(x1 - x0), int(y1 - y0)]
    report["star_area_ratio"] = round(star_ratio, 4)
    # 角数在**源分辨率的分割遮罩**上数：2048px 的星，采样抖动影响不到它。
    report["star_points"] = _mask_points(star_mask)
    # 五角星占外接圆的面积比理论上约 0.40；我们的星外还留着一圈虹膜和描边，
    # 实测 0.29。低于 0.15 说明分割没咬住星形（多半是源图换了），直接报错别硬出。
    if not 0.15 <= star_ratio <= 0.55:
        raise SystemExit(f"[star_eye] 星形分割可疑：占虹膜 {star_ratio:.1%}"
                         f"（期望 15%~55%）—— 换源图了就调 STAR_SPLIT_Q")
    return out


def _erode(mask: np.ndarray, r: int) -> np.ndarray:
    """四邻域腐蚀 r 次。"""
    out = mask.copy()
    for _ in range(max(r, 0)):
        acc = out.copy()
        for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            acc &= np.roll(np.roll(out, dy, 0), dx, 1)
        out = acc
    return out


def _open(mask: np.ndarray, r: int) -> np.ndarray:
    """形态学开运算（先腐蚀后膨胀）：掐断细颈，保留主体形状。"""
    def grow(m, n, op):
        out = m.copy()
        for _ in range(n):
            acc = out.copy()
            for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                nb = np.roll(np.roll(out, dy, 0), dx, 1)
                acc = (acc | nb) if op else (acc & nb)
            out = acc
        return out
    return grow(grow(mask, r, False), r, True)


def _mask_points(mask: np.ndarray) -> int:
    """数这个遮罩有几个"角"：沿质心取一圈，看边界半径有几个极大值。

    在源分辨率（~1100px 的星）上跑，所以结果是稳定的 —— 五角星应当是 5。
    做法：360 个角度各自求"遮罩在这个方向上最远到哪"，平滑后数高于均值的区段。

    ⚠ 数之前先做一次开运算：分割出来的星会从左上角伸出一条**细颈**连到那块
    水晶碎钻高光上（见 logs/asset_qa/star_mask_probe.png），不掐断就会多数出
    一个角（实测 6 而不是 5）。开运算只影响计数，不影响重铺用的遮罩。
    """
    mask = largest_blob(_open(mask, OPEN_R))
    ys, xs = np.nonzero(mask)
    if ys.size == 0:
        return 0
    cy, cx = ys.mean(), xs.mean()
    ang = np.arctan2(ys - cy, xs - cx)
    rad = np.hypot(ys - cy, xs - cx)
    nb = 360
    idx = ((ang + np.pi) / (2 * np.pi) * nb).astype(int) % nb
    far = np.zeros(nb)
    np.maximum.at(far, idx, rad)
    k = np.ones(15) / 15.0
    far = np.convolve(np.concatenate([far[-14:], far, far[:14]]), k, "same")[14:-14]
    hot = far > far.mean()
    runs, prev = 0, hot[-1]
    for cur in hot:
        if cur and not prev:
            runs += 1
        prev = cur
    return int(runs)


# ----------------------------------------------------------------- L3 闪光素材
def _repaint(rgb: np.ndarray, a: np.ndarray) -> np.ndarray:
    """按调色板重铺颜色：保留 AI 图的明暗结构，换掉色相。

    t = 归一化亮度（在可见区内拉满 0..1）。t→1 是芯（白），t→0 是尖（#4A8FD4）。
    这样「素材里不可能有洋红」是构造出来的，不是靠 despill 的阈值赌出来的。
    """
    lum = rgb @ np.array([0.299, 0.587, 0.114])
    vis = a > 0.05
    if not vis.any():
        return rgb
    lo, hi = np.percentile(lum[vis], 2), np.percentile(lum[vis], 98)
    t = np.clip((lum - lo) / max(hi - lo, 1e-6), 0.0, 1.0)[..., None]
    low = SPARK_TIP[None, None, :] + (SPARK_MID - SPARK_TIP)[None, None, :] * (t / 0.5)
    high = SPARK_MID[None, None, :] + (SPARK_CORE - SPARK_MID)[None, None, :] * ((t - 0.5) / 0.5)
    return np.where(t < 0.5, low, high)


def build_sparkle(src_path: str, sprites: str, head_pos, head_size, report: dict) -> dict:
    im = np.asarray(Image.open(src_path).convert("RGB")).astype(np.float64)
    bg = border_bg(im)
    a = key_alpha(im, bg)
    body = largest_blob(a > 0.5)
    x0, y0, x1, y1 = bbox(body)
    side = int(max(x1 - x0, y1 - y0) * 1.10)     # 尖角很淡，外扩 10% 别切了
    cx, cy = (x0 + x1) // 2, (y0 + y1) // 2
    x0, y0 = max(0, cx - side // 2), max(0, cy - side // 2)
    x1, y1 = min(im.shape[1], x0 + side), min(im.shape[0], y0 + side)
    crop_rgb, crop_a = im[y0:y1, x0:x1], a[y0:y1, x0:x1]
    crop_rgb = despill(crop_rgb, crop_a, bg)


    left_total = 0
    for n, dst in ((SPARKLE_PX, os.path.join(sprites, "fx_sparkle.png")),
                   (SPARKLE_PX * 2, os.path.join(sprites, "fx_sparkle@2x.png"))):
        rgb, al = premul_resize(crop_rgb, crop_a, (n, n))
        rgb = _repaint(rgb, al)
        px = np.zeros((n, n, 4), np.uint8)
        px[..., :3] = rgb.astype(np.uint8)
        px[..., 3] = (al * 255.0).astype(np.uint8)
        Image.fromarray(px, "RGBA").save(dst)
        left_total += keycolor_left(rgb, al)
    if left_total:
        raise SystemExit(f"[star_eye] fx_sparkle 还剩 {left_total} 个洋红像素")

    hx, hy = head_pos
    hw, hh = head_size
    inst = []
    for i, (u, v, sz, rot, freq, phase) in enumerate(SPARKLES, 1):
        inst.append({
            "id": f"fx_sparkle_{i}",
            "pos": [int(round(hx + u * hw)), int(round(hy + v * hh))],
            "scale": SPARKLE_SCALE[sz], "size_class": sz, "rot_deg": rot,
            "freq": freq, "phase": phase,
        })
    report["source_sparkle"] = os.path.relpath(src_path)
    return {"file": "sprites/fx_sparkle.png", "size": [SPARKLE_PX, SPARKLE_PX],
            "blend": "add", "keycolor_px": left_total, "instances": inst}
    # ⚠ 这里的 "blend":"add" 只是切件器的历史字段，rig 侧**不读它**；
    #    真正落到 rig.json 的混合模式来自 effects.json 的 "blend"（DC57：剪影外只能 normal）。


# ----------------------------------------------------------------- main
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--character", default="xiaoxun")
    ap.add_argument("--form", default="teen")
    ap.add_argument("--root", default=".")
    a = ap.parse_args()

    base = os.path.join(a.root, "characters", a.character)
    sprites = os.path.join(base, "forms", a.form, "sprites")
    iris_src = os.path.join(base, "design", "redraw", "eye_star_iris.png")
    spark_src = os.path.join(base, "design", "redraw", "fx_sparkle.png")
    for p in (iris_src, spark_src):
        if not os.path.exists(p):
            print(f"[star_eye] 没有 {p}，跳过（星星眼是可选差分件）")
            return 0

    eff = load_effect(os.path.join(base, "design"))    # ← T43.2：几何从表来，不在源码里

    bp = os.path.join(sprites, "body_parts.json")
    with open(bp, encoding="utf-8") as fh:
        body = json.load(fh)
    anchor_box = eff.get("anchor", {}).get("box", "seg_head")
    head = next(p for p in body["parts"] if p["id"] == anchor_box)

    report: dict = {"schema_version": "1.0"}
    eyes = build_star_iris(iris_src, sprites, report)
    spark = build_sparkle(spark_src, sprites, head["pos"], head["size"], report)
    report["eyes"] = eyes
    report["sparkle"] = spark
    out = os.path.join(sprites, "star_eye_parts.json")
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=2)
        fh.write("\n")

    print(f"写出 {sprites}/eye_[lr]_ball_star.png（{report['star_points']} 个角，"
          f"占虹膜 {report['star_area_ratio']:.0%}，星内外亮度差 "
          f"{'/'.join(str(e['checks']['star_contrast']) for e in eyes)}，"
          f"描边深 {'/'.join(str(e['checks']['edge_contrast']) for e in eyes)}，"
          f"星外保真 {'/'.join(format(e['checks']['ground_kept'], '.0%') for e in eyes)}）"
          f" + fx_sparkle.png {SPARKLE_PX}×{SPARKLE_PX}"
          f" + {len(spark['instances'])} 个散布点 → star_eye_parts.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
