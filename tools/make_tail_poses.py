# -*- coding: utf-8 -*-
"""从**一条**尾巴原画重铺出其余三档姿态（up / puff / tuck）。

★★★ 2026-10-21 第二十九问 ①「竖起的尾巴和放松的尾巴不是同一条」的根治。

病根（用户一眼看出来的那个）
--------------------------------
`design/redraw/acc_tail_cat_{relaxed,up,puff,tuck}.png` 是**四张互不相干的 AI 出图**。
四张各画一遍，粗细、毛流、体积、渐变就必然对不上：

  · relaxed —— 粗、S 形、梢部钝圆、淡紫→天蓝、边缘有毛刺（这条是对的）
  · up      —— 一根**等粗细的细直棍**加个小钩，扁平、没有高光脊
  · puff    —— 像把**羽毛掸子／蕨叶**，根本不是猫尾
  · tuck    —— 粗细接近 relaxed，但毛流方向又是另一套

这不是调参数能救的，是**做法**错了。

查到的做法（第五十一批，URL 见 docs/REFERENCE_NOTES.md）
--------------------------------------------------------------
  · https://miracle-usausa-nurse.com/paint/499/
    「曲げた状態で元絵を描いたので、反対側に揺らすと綺麗に変形できなかった。
      揺らす前提ならば、**尻尾はまっすぐ描いておく**」
    —— 反面经验：姿态烘进原画 = 不能再变形。
  · https://cgbox.jp/2020/12/05/live2d-shake-part/
    「しっぽ…くねくね曲がっている場合、デフォーマや変形パスで揺れを作ろうとすると
      …難易度が高い。この場合、**スキニングを使用すると簡単かつきれいに動きます**」
  · https://saraemi.com/vtuber/2021/11/02/live2d_skinning/
    スキニング = 沿部件打一串回転デフォーマ，紐/尻尾这种长条物专用。

也就是说，业界口径是「**一条原画 + 一根骨链**」，不是「四张图」。
本引擎没有 Live2D 的骨链编辑器，但骨链变形本身是纯几何的，可以**离线烘**：
把原画沿自己的脊线拆成 (弧长 s, 法向偏移 t) 的曲线坐标，再沿目标脊线铺回去。
逐像素都是 relaxed 那张原画的颜色和笔触 ⇒ 四档从定义上就是同一条尾巴。

实现
----
1. `spine_of()`  距离变换脊线行走：从根部出发，每步在 ±28° 的锥内选
   「到边界距离最大」的方向前进 ⇒ 得到脊线折线 + 每点的半宽。
2. `sample_profile()` 沿每个脊线点的法线向两侧扫，把 RGBA 记成 (s,t) 剖面表。
   **扫到比实心半宽更远**，这样边缘那圈毛刺也一起带走。
3. `lay_along()`  把剖面表铺到目标脊线上（双线性抛撒 + 权重归一）。
   s 步长 0.35px、t 步长 0.35px，外侧拉伸也不会漏洞。
4. 目标脊线由**曲率函数**积分出来，弧长和原画**完全相等** —— 同一条尾巴
   不会一档长一档短。puff 额外给半宽乘一条 1.0→1.9→1.45 的膨胀曲线
   （炸毛是毛竖起来，骨头没变粗，所以只放大 t 不放大 s）。

几何对齐
--------
`make_attach_parts._emit` 是按**内容 bbox** 裁剪再缩放到 `sprite_h_rel*head_unit`
的，所以四张图的 bbox 不同就不能共用同一组 pos_rel。本脚本在生成之后
**反解**每一档的 pos_rel / sprite_h_rel，使四档的**根部像素落在同一个模型坐标点**上
—— 切档的时候尾巴根不会跳。relaxed 自己一个像素都不改（它是基准）。
"""
from __future__ import unicode_literals

import argparse
import collections
import io
import json
import math
import os
import sys

import numpy as np
from PIL import Image, ImageFilter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from make_manpu_parts import CROP_MARGIN, bg_color, key_alpha

MAGENTA = (255, 0, 255)
# 四档在 attachments.json 里的 id 和源文件名
BASE_ID = "tail_cat_relaxed"
BASE_SRC = "acc_tail_cat_relaxed.png"


def key_mask(rgb):
    """洋红底 → 不透明掩膜。判据和 cut_from_sheets.key_rgba 同源：
    除了纯洋红，还要认**抗锯齿混色**（G 被压得比 R/B 都低）。"""
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    mag = (r > 150) & (b > 150) & (g < 110) & ((r - g) > 80) & ((b - g) > 80)
    spill = (g < np.minimum(r, b) - 40) & ((r > 60) | (b > 60))
    return ~(mag | spill)


def dist_transform(m):
    """到背景的距离（L∞ 近似）：反复腐蚀，记每个像素活到第几轮。

    没有 scipy，用 PIL 的 MinFilter 迭代。尾巴半宽 ~130px，
    900x1748 上迭代 140 轮约 1 秒，够用。
    """
    cur = (m.astype(np.uint8)) * 255
    d = np.zeros(m.shape, np.int32)
    for _ in range(200):
        img = Image.fromarray(cur, "L").filter(ImageFilter.MinFilter(3))
        cur = np.asarray(img).copy()
        alive = cur > 127
        if not alive.any():
            break
        d[alive] += 1
    return d


def spine_of(m, root, d0, step=6.0, cone=28.0, nray=15):
    """距离变换脊线行走。返回 [(x, y), ...]。

    为什么不用「逐行取质心」：尾巴梢是**横着弯过去**的，按行取质心到了梢部
    会把一整条横段压成一个点，重铺出来梢就没了。按局部方向走就没这个问题。
    """
    d = dist_transform(m).astype(np.float64)
    H, W = m.shape
    pts = [tuple(root)]
    dirv = np.array(d0, np.float64)
    dirv /= np.linalg.norm(dirv)
    p = np.array(root, np.float64)
    for _ in range(4000):
        best, bestv = None, -1e9
        for i in range(nray):
            th = math.radians(-cone + 2.0 * cone * i / float(nray - 1))
            c, s = math.cos(th), math.sin(th)
            nd = np.array([dirv[0] * c - dirv[1] * s,
                           dirv[0] * s + dirv[1] * c])
            q = p + nd * step
            xi, yi = int(round(q[0])), int(round(q[1]))
            if not (0 <= xi < W and 0 <= yi < H):
                continue
            # 直着走优先一点点，免得在粗段里左右画龙
            v = d[yi, xi] - 0.9 * abs(th)
            if v > bestv:
                bestv, best, bestd = v, q, nd
        if best is None or bestv < 1.2:
            break
        p, dirv = best, bestd
        pts.append((float(p[0]), float(p[1])))
    return pts


def resample_poly(pts, step):
    """把折线按等弧长重采样，返回 (点数组, 单位切向数组, 总弧长)。"""
    a = np.array(pts, np.float64)
    seg = np.linalg.norm(np.diff(a, axis=0), axis=1)
    cum = np.concatenate([[0.0], np.cumsum(seg)])
    L = float(cum[-1])
    ss = np.arange(0.0, L + step * 0.5, step)
    x = np.interp(ss, cum, a[:, 0])
    y = np.interp(ss, cum, a[:, 1])
    out = np.stack([x, y], 1)
    t = np.gradient(out, axis=0)
    t /= np.maximum(np.linalg.norm(t, axis=1, keepdims=True), 1e-9)
    return out, t, L


def smooth_poly(pts, k=9):
    a = np.array(pts, np.float64)
    if len(a) < k:
        return a
    ker = np.ones(k) / float(k)
    pad = k // 2
    out = a.copy()
    for c in (0, 1):
        v = np.pad(a[:, c], (pad, pad), mode="edge")
        out[:, c] = np.convolve(v, ker, mode="valid")
    return out


def build_spine(theta_deg, L, root, ds=1.0):
    """按**曲率函数**积分出一条脊线。theta_deg(u) 给的是 u∈[0,1] 处的切向角
    （度，0=向右，90=向下），弧长固定为 L ⇒ 和原画一样长。"""
    n = int(round(L / ds)) + 1
    us = np.linspace(0.0, 1.0, n)
    th = np.radians(np.array([theta_deg(u) for u in us]))
    dx = np.cos(th) * ds
    dy = np.sin(th) * ds
    x = root[0] + np.concatenate([[0.0], np.cumsum(dx)[:-1]])
    y = root[1] + np.concatenate([[0.0], np.cumsum(dy)[:-1]])
    return np.stack([x, y], 1)


def sample_profile(rgb, m, pts, tang, tmax, dt=0.35):
    """沿法线扫出 (s,t) 剖面表。返回 (颜色 [S,T,3], 有效 [S,T], ts)。"""
    H, W = m.shape
    nrm = np.stack([-tang[:, 1], tang[:, 0]], 1)
    ts = np.arange(-tmax, tmax + dt * 0.5, dt)
    px = pts[:, None, 0] + nrm[:, None, 0] * ts[None, :]
    py = pts[:, None, 1] + nrm[:, None, 1] * ts[None, :]
    x0 = np.floor(px).astype(np.int64)
    y0 = np.floor(py).astype(np.int64)
    fx = (px - x0)[..., None]
    fy = (py - y0)[..., None]
    ok = (x0 >= 0) & (x0 < W - 1) & (y0 >= 0) & (y0 < H - 1)
    xc = np.clip(x0, 0, W - 2)
    yc = np.clip(y0, 0, H - 2)
    f = rgb.astype(np.float64)
    mm = m.astype(np.float64)[..., None]
    c = (f[yc, xc] * (1 - fx) * (1 - fy) + f[yc, xc + 1] * fx * (1 - fy) +
         f[yc + 1, xc] * (1 - fx) * fy + f[yc + 1, xc + 1] * fx * fy)
    a = (mm[yc, xc] * (1 - fx) * (1 - fy) + mm[yc, xc + 1] * fx * (1 - fy) +
         mm[yc + 1, xc] * (1 - fx) * fy + mm[yc + 1, xc + 1] * fx * fy)[..., 0]
    # 只认「中心确实在件里」的采样点，免得把洋红拖进来
    hard = m[np.clip(np.rint(py).astype(np.int64), 0, H - 1),
             np.clip(np.rint(px).astype(np.int64), 0, W - 1)]
    return c, (ok & hard & (a > 0.35)), ts


def lay_along(col, val, ts, pts, tang, shape, tscale=None):
    """把剖面表沿目标脊线铺回画布（双线性抛撒 + 权重归一）。"""
    H, W = shape
    nrm = np.stack([-tang[:, 1], tang[:, 0]], 1)
    sc = np.ones(len(pts)) if tscale is None else tscale
    px = pts[:, None, 0] + nrm[:, None, 0] * (ts[None, :] * sc[:, None])
    py = pts[:, None, 1] + nrm[:, None, 1] * (ts[None, :] * sc[:, None])
    acc = np.zeros((H, W, 3), np.float64)
    wgt = np.zeros((H, W), np.float64)
    x0 = np.floor(px).astype(np.int64)
    y0 = np.floor(py).astype(np.int64)
    fx = px - x0
    fy = py - y0
    good = val & (x0 >= 0) & (x0 < W - 1) & (y0 >= 0) & (y0 < H - 1)
    xi = x0[good]
    yi = y0[good]
    gx = fx[good]
    gy = fy[good]
    cc = col[good]
    for ddx, ddy, ww in ((0, 0, (1 - gx) * (1 - gy)), (1, 0, gx * (1 - gy)),
                         (0, 1, (1 - gx) * gy), (1, 1, gx * gy)):
        idx = (yi + ddy) * W + (xi + ddx)
        for ch in range(3):
            np.add.at(acc.reshape(-1, 3)[:, ch], idx, cc[:, ch] * ww)
        np.add.at(wgt.reshape(-1), idx, ww)
    hit = wgt > 1e-6
    out = np.zeros((H, W, 3), np.float64)
    out[hit] = acc[hit] / wgt[hit][..., None]
    return out, hit


def close_pinholes(rgb, m):
    """补 1px 针孔：抛撒后偶尔有单像素没被任何采样点覆盖。"""
    mi = Image.fromarray((m.astype(np.uint8)) * 255, "L")
    closed = np.asarray(mi.filter(ImageFilter.MaxFilter(3))
                        .filter(ImageFilter.MinFilter(3))) > 127
    holes = closed & ~m
    if not holes.any():
        return rgb, m
    f = rgb.copy()
    src = np.where(m[..., None], rgb, 0.0)
    acc = np.zeros_like(src)
    cnt = np.zeros(m.shape, np.float64)
    for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (-1, -1),
                   (1, -1), (-1, 1)):
        acc += np.roll(src, (dy, dx), axis=(0, 1))
        cnt += np.roll(m.astype(np.float64), (dy, dx), axis=(0, 1))
    ok = holes & (cnt > 0)
    f[ok] = acc[ok] / cnt[ok][..., None]
    return f, (m | ok)


# ---------------------------------------------------------------- 目标姿态
#   θ(u)：u 是归一化弧长，返回切向角（度）。0=向右、90=向下、-90=向上。
#   写成函数而不是硬编码点列，是为了「弧长固定 = 同一条尾巴」这条约束。
def _blend(a, b, u, lo, hi):
    if u <= lo:
        return a
    if u >= hi:
        return b
    k = (u - lo) / (hi - lo)
    k = k * k * (3 - 2 * k)                     # smoothstep，免得出现折角
    return a + (b - a) * k


#   ★ 曲率上限是算出来的，不是拍的：曲线坐标 (s,t) 在曲率半径 R < |t| 的地方
#     会**自己折过来**（内侧法线相交）。扫描半宽 tmax≈196px、puff 还要再乘 1.9，
#     所以 R 必须留到 ~500px 以上。R = L / (dθ/du)，L=1766 ⇒ dθ/du < 3.5 rad
#     ⇒ **每 0.1 个弧长单位最多转 20°**。第一版根部 0.3 弧长内转了 150°
#     （R=202px），结果就是根部折出一块方疙瘩 —— 那是折叠，不是绘画问题。
def th_up(u):
    """竖起：先向**外侧**甩出去避开躯干，再立起来，梢部轻轻钩回（问号尾）。

    注意根部**不必**接着 relaxed 的朝向：接的是根部那个**点**（反解几何保证），
    不是切向。真猫尾竖起来时根部本来就朝上。

    ★ 为什么必须向外甩：尾巴挂在 `hip_back`（层 30），**在整个身体后面**。
      尾根的模型坐标是 x≈315，而躯干左缘在 x≈300、裙摆更外到 x≈270 ——
      从尾根直着往上立，整条都藏在躯干背后，画面上只剩肩膀上方露出一小截
      （实测第一版就是这样，/tmp/t_final.png 第 2 格）。
      所以前 28% 弧长先以 −132° 斜向外上方走，把脊线带到 x≈269 的躯干外侧，
      再转成近竖直。VTuber 模型画竖尾都是这么处理的，不是解剖学问题，是遮挡问题。
    ★ 转角速度受曲率上限约束：−132°→−95° 是 37°，摊在 0.28 弧长上
      ⇒ R≈756px > 扫描半宽 196px，不会折叠。（摊在 0.18 上就只有 486px，危险。）
    """
    a = _blend(-132.0, -95.0, u, 0.00, 0.28)
    a = _blend(a, -110.0, u, 0.68, 1.00)
    return a


def th_puff(u):
    """炸毛：和竖起同一套骨架，但**外甩得更多** —— 它的半宽是竖起的两倍，
    不多让出一个身位，内侧那半条会整个插进躯干背后看不见。"""
    a = _blend(-142.0, -100.0, u, 0.00, 0.30)
    a = _blend(a, -114.0, u, 0.70, 1.00)
    return a


def th_tuck(u):
    """夹尾：贴着腿垂下去，后半段向**身体那一侧**（画面右）卷过来。

    ★ 方向别搞反：尾巴挂在胯后偏画面左，身体在它右边。夹尾是把尾巴收向身体，
      所以梢必须朝右卷（θ 变小）。第一版写成 84°→168°（朝左卷），
      放大一看就是尾巴朝着没有身体的那边兜了个圈，很怪。
    """
    a = _blend(84.0, 34.0, u, 0.00, 0.45)
    a = _blend(a, -22.0, u, 0.45, 1.00)         # 全程转 106°，R≈940px
    return a


def puff_scale(u):
    """炸毛的半宽膨胀：**只轻微加宽**，1.0 → 1.25（中段）→ 1.15（梢）。

    ★★★ 2026-10-21 第三十一问：上一版是 1.0→2.0→1.6，用户说「炸毛也错误了，
        **没有毛的感觉了**」。放大一看就明白：毛丝是沿尾巴轴向的细线，
        把剖面**垂直于轴**拉 2 倍，等于把每根毛丝横向拉成 2 倍宽，
        双线性插值再一抹 —— 毛就糊成了一根蓝棒槌。
        实测横向梯度（毛丝清晰度）relaxed 3.298 / up 3.369 / **puff 2.815**，
        低了 15%，和肉眼看到的"糊"完全对得上。

        真实的炸毛（piloerection）不是「尾巴变粗」，是「**毛立起来**」：
        芯几乎不变，毛梢向外支棱出去，剪影变成一圈**毛刺**。
        所以这一版把拉伸压回 1.25 以内（纹理基本不糊），
        体积改由 fur_fringe() 沿剪影**长出真正的毛**来给。
    """
    if u < 0.12:
        base = _blend(1.0, 1.12, u, 0.0, 0.12)
    elif u < 0.5:
        base = _blend(1.12, 1.25, u, 0.12, 0.5)
    else:
        base = _blend(1.25, 1.15, u, 0.5, 1.0)
    return base * (1.0 + 0.03 * math.sin(u * 47.0) + 0.02 * math.sin(u * 113.0))


# 炸毛毛刺的长度包络（像素）：根部短（要接得住身体）、中段最长、梢部次之。
FUR_LEN = (6.0, 30.0, 20.0)
FUR_MAX = 36.0          # 画布留边用的上限
FUR_STEP = 0.62         # 每根毛沿长度方向的步距
FUR_SEED = 20261021


def fur_fringe(out, hit, u_of, seed=FUR_SEED):
    """沿剪影往外「长毛」—— 炸毛的体积感由这一步给，不靠拉伸贴图。

    为什么是这个做法：参考 cgbox / miracle-usausa 两篇尻尾教程的共同口径 ——
    尻尾是「くねくね曲がっている」的细长物，形变要沿**骨架**做；
    而炸毛属于**剪影层面**的变化（毛立起来），不是骨架层面的。
    把两件事分开，纹理就不会被形变糊掉。

    做法：
      ① 取剪影外缘一圈像素；
      ② 每个外缘点求**向外法线**（用模糊后掩膜的梯度，天然垂直于轮廓）；
      ③ 沿法线往外画一根**由粗到细、由实到虚**的毛，长度带噪声；
      ④ 毛色从该点往内 3px 处取，梢部稍微提亮（真毛的梢会透光）。
    """
    H, W = hit.shape
    rng = np.random.RandomState(seed)

    # ① 外缘一圈
    mi = Image.fromarray((hit.astype(np.uint8)) * 255, "L")
    inner = np.asarray(mi.filter(ImageFilter.MinFilter(5))) > 127
    edge = hit & ~inner
    ey, ex = np.nonzero(edge)
    if len(ey) == 0:
        return out, hit

    # ② 向外法线 = 模糊掩膜梯度的反向（梯度指向内部）
    blur = np.asarray(mi.filter(ImageFilter.GaussianBlur(3.0))).astype(np.float64)
    gy, gx = np.gradient(blur)
    nx, ny = -gx[ey, ex], -gy[ey, ex]
    ln = np.hypot(nx, ny)
    ok = ln > 1e-3
    ey, ex, nx, ny, ln = ey[ok], ex[ok], nx[ok], ny[ok], ln[ok]
    nx, ny = nx / ln, ny / ln

    # 稀疏化：每 2 个外缘点长 1 根，再加角度抖动，免得毛像梳子一样齐
    pick = rng.rand(len(ey)) < 0.55
    ey, ex, nx, ny = ey[pick], ex[pick], nx[pick], ny[pick]
    jit = (rng.rand(len(ey)) - 0.5) * 0.85           # ±24°
    cj, sj = np.cos(jit), np.sin(jit)
    nx, ny = nx * cj - ny * sj, nx * sj + ny * cj

    acc = out.copy()
    m2 = hit.copy()
    l0, l1, l2 = FUR_LEN
    for k in range(len(ey)):
        y0, x0 = int(ey[k]), int(ex[k])
        u = u_of[y0, x0]
        # 长度包络：根 l0 → 中 l1 → 梢 l2
        base = l0 + (l1 - l0) * min(1.0, u / 0.45) if u < 0.45 else \
            l1 + (l2 - l1) * ((u - 0.45) / 0.55)
        ln_k = base * (0.35 + 0.95 * rng.rand())
        if ln_k < 2.0:
            continue
        # 毛色：从外缘往内 3px 取，避开抗锯齿边
        sy = int(round(y0 - ny[k] * 3.0)); sx = int(round(x0 - nx[k] * 3.0))
        if not (0 <= sy < H and 0 <= sx < W and hit[sy, sx]):
            sy, sx = y0, x0
        c = acc[sy, sx].copy()
        steps = int(ln_k / FUR_STEP)
        for i in range(steps):
            t = (i + 1) / float(steps)
            px = x0 + nx[k] * (i + 1) * FUR_STEP
            py = y0 + ny[k] * (i + 1) * FUR_STEP
            xi, yi = int(round(px)), int(round(py))
            if not (0 <= xi < W and 0 <= yi < H):
                break
            # 由粗到细：t<0.45 画 2px 宽，之后 1px
            cc = c * (1.0 - 0.10 * t) + 255.0 * (0.10 * t)   # 梢部提亮
            rr = 1 if t < 0.45 else 0
            for dy in range(-rr, rr + 1):
                for dx in range(-rr, rr + 1):
                    yy, xx = yi + dy, xi + dx
                    if 0 <= yy < H and 0 <= xx < W and not m2[yy, xx]:
                        acc[yy, xx] = cc
                        m2[yy, xx] = True
    return acc, m2


# 第四列 = 要不要沿剪影长毛刺（只有炸毛要）
POSES = [
    ("tail_cat_up", "acc_tail_cat_up.png", th_up, None, False),
    ("tail_cat_puff", "acc_tail_cat_puff.png", th_puff, puff_scale, True),
    ("tail_cat_tuck", "acc_tail_cat_tuck.png", th_tuck, None, False),
]


def content_bbox(m):
    ys, xs = np.nonzero(m)
    return int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    ap.add_argument("--character", default="xiaoxun")
    ap.add_argument("--debug-dir", default="")
    a = ap.parse_args()

    base = os.path.join(a.root, "characters", a.character)
    redraw = os.path.join(base, "design", "redraw")
    src_path = os.path.join(redraw, BASE_SRC)
    if not os.path.exists(src_path):
        print("[tail] 没有 %s，跳过" % src_path)
        return 0

    rgb = np.asarray(Image.open(src_path).convert("RGB")).astype(np.float64)
    m = key_mask(rgb)
    H, W = m.shape
    bx0, by0, bx1, by1 = content_bbox(m)

    # 根部 = 内容最顶那一行的中点（尾巴是从胯后往下垂的，顶就是根）
    top = by0 + 2
    xs = np.nonzero(m[top])[0]
    root = (float(xs.mean()), float(top))
    print("[tail] 原画 %dx%d 内容bbox=(%d,%d,%d,%d) 根=(%.0f,%.0f)"
          % (W, H, bx0, by0, bx1, by1, root[0], root[1]))

    raw = spine_of(m, root, (0.08, 1.0))
    sp = smooth_poly(raw, 11)
    pts, tang, L = resample_poly(sp, 1.0)
    # 脊线两头各外延一截（直着延），好把根部切面和梢部的圆帽也扫进来
    #   只向**梢部**外延：梢是个圆帽，最后一个脊线点之外还有半个身位的内容，
    #   不延长就会被削平。根部那头是贴着身体的平切口，一延长反而会把切口
    #   拖成一条毛边（第一版就是这么出的方疙瘩）。
    ext = 30.0
    tail_ext = pts[-1] + tang[-1] * np.arange(1, int(ext) + 1)[:, None]
    pts = np.concatenate([pts, tail_ext], 0)
    tang = np.concatenate([tang, np.repeat(tang[-1:], int(ext), 0)], 0)
    pts, tang, L = resample_poly(pts, 0.35)
    d = dist_transform(m)
    tmax = float(d.max()) * 1.45 + 12.0
    print("[tail] 脊线 %d 点  弧长 %.0fpx  最大半宽 %d  扫描半宽 %.0f"
          % (len(pts), L, d.max(), tmax))

    col, val, ts = sample_profile(rgb, m, pts, tang, tmax)
    # ★ 根部做一个「平切塞子」：原画的根是**水平**切口，而脊线在根部几乎竖直，
    #   第一条扫描线跟切口近乎平行，采到一半就出界了 —— 渲染出来根部是一圈
    #   锯齿毛边。把最前面 PLUG 段换成 s=PLUG 处那条完整剖面的直挤出，
    #   根部就是一个干净的平口（它本来也藏在胯/裙子后面，看不见）。
    PLUG = int(round(22.0 / 0.35))
    if len(col) > PLUG * 2:
        col = np.concatenate([np.repeat(col[PLUG:PLUG + 1], PLUG, 0),
                              col[PLUG:]], 0)
        val = np.concatenate([np.repeat(val[PLUG:PLUG + 1], PLUG, 0),
                              val[PLUG:]], 0)
    print("[tail] 剖面表 %s  有效采样 %d  根部平切塞 %dpx"
          % (str(col.shape[:2]), int(val.sum()), PLUG))

    if a.debug_dir:
        os.makedirs(a.debug_dir, exist_ok=True)
        vis = np.where(m[..., None], rgb, np.array(MAGENTA, np.float64))
        for (x, y) in pts[::6]:
            xi, yi = int(round(x)), int(round(y))
            if 0 <= xi < W and 0 <= yi < H:
                vis[max(0, yi - 2):yi + 3, max(0, xi - 2):xi + 3] = (0, 255, 0)
        Image.fromarray(vis.astype(np.uint8)).save(
            os.path.join(a.debug_dir, "tail_spine.png"))

    # 每档按自己的脊线包络开画布（共用一个大画布会被切掉，而且白耗内存）。
    # 根部像素位置逐档记下来，后面反解几何时用，四档照样对得齐。
    geo = {}
    for pid, fname, thf, tsf, fur in POSES:
        n0 = len(pts)
        us0 = np.linspace(0.0, 1.0, n0)
        sc = None if tsf is None else np.array([tsf(u) for u in us0])
        probe = build_spine(thf, L, (0.0, 0.0), ds=0.35)
        pad = tmax * (1.0 if sc is None else float(sc.max())) + 10.0
        if fur:
            pad += FUR_MAX                     # 毛刺要伸到剪影外面，画布得留够
        mnx, mny = probe[:, 0].min() - pad, probe[:, 1].min() - pad
        mxx, mxy = probe[:, 0].max() + pad, probe[:, 1].max() + pad
        CW = int(math.ceil(mxx - mnx)) + 2
        CH = int(math.ceil(mxy - mny)) + 2
        croot = (-mnx + 1.0, -mny + 1.0)
        tp = build_spine(thf, L, croot, ds=0.35)
        tt = np.gradient(tp, axis=0)
        tt /= np.maximum(np.linalg.norm(tt, axis=1, keepdims=True), 1e-9)
        n = min(len(tp), n0)
        if sc is not None:
            sc = sc[:n]
        out, hit = lay_along(col[:n], val[:n], ts, tp[:n], tt[:n], (CH, CW),
                             tscale=sc)
        out, hit = close_pinholes(out, hit)
        if fur:
            # 每个像素的弧长参数 u（0=根 1=梢），给毛长包络用。
            # 用「离哪个脊线点最近」来算：脊线点本来就是等弧长重采样的，
            # 所以下标 / 总数 就是 u，不用再算测地距离。
            uof = np.zeros((CH, CW), np.float64)
            yy = np.arange(CH)[:, None]
            xx = np.arange(CW)[None, :]
            bestd = np.full((CH, CW), 1e18)
            stride = max(1, n // 240)
            for i in range(0, n, stride):
                dx = xx - tp[i, 0]
                dy = yy - tp[i, 1]
                dd = dx * dx + dy * dy
                upd = dd < bestd
                bestd[upd] = dd[upd]
                uof[upd] = i / float(max(1, n - 1))
            before = int(hit.sum())
            out, hit = fur_fringe(out, hit, uof)
            print("[tail]   炸毛毛刺：%d → %d px（+%d）"
                  % (before, int(hit.sum()), int(hit.sum()) - before))
        img = np.where(hit[..., None], out, np.array(MAGENTA, np.float64))
        Image.fromarray(img.astype(np.uint8), "RGB").save(
            os.path.join(redraw, fname))
        gx0, gy0, gx1, gy1 = content_bbox(hit)
        geo[pid] = (gx0, gy0, gx1, gy1, croot)
        print("[tail] + %-14s %s 内容bbox=(%d,%d,%d,%d) 像素 %d"
              % (pid, fname, gx0, gy0, gx1, gy1, int(hit.sum())))

    # ---- 反解 pos_rel / sprite_h_rel，让四档的根部落在同一个模型坐标点 ----
    # ★★★ 几何必须**完全复刻 make_attach_parts._emit 的口径**，自己另算一套
    #   必错。_emit 的口径是：
    #     ① 内容框 = `key_alpha(rgb,bg) > 0.35` 的 bbox（**不是**本文件的
    #        key_mask —— 两者判据不同，relaxed 上就差 2.5% 的宽高比）；
    #     ② 四周各留 CROP_MARGIN 比例的边，padx/pady 分别按宽/高算；
    #     ③ 贴图 = 这个**加边后的框**缩放到 h1 = sprite_h_rel × 单位长；
    #     ④ 贴图按 att["anchor"] 定位到 pos。
    #   第一版自己用 key_mask 的 bbox + 假设 anchor=[0.5,0.5] 反解，
    #   up/puff 整条飞出画面、tuck 横向偏了 97px。
    tp = os.path.join(base, "design", "attachments.json")
    with io.open(tp, encoding="utf-8") as f:
        tbl = json.load(f, object_pairs_hook=collections.OrderedDict)
    by_id = {x["id"]: x for x in tbl["attachments"]}

    def emit_box(path):
        """复刻 _emit 的内容框（含 CROP_MARGIN 外边）。"""
        im = Image.open(path).convert("RGB")
        arr = np.asarray(im, dtype=np.uint8)
        bgc = bg_color(arr)
        al = key_alpha(arr, bgc)
        ys, xs = np.nonzero(al > 0.35)
        x0, x1, y0, y1 = int(xs.min()), int(xs.max()) + 1, \
            int(ys.min()), int(ys.max()) + 1
        padx = int(round((x1 - x0) * CROP_MARGIN))
        pady = int(round((y1 - y0) * CROP_MARGIN))
        return x0 - padx, y0 - pady, (x1 - x0) + padx * 2, (y1 - y0) + pady * 2

    ba = by_id[BASE_ID]
    bx, by, bwid, bhei = emit_box(src_path)
    kk = float(ba["sprite_h_rel"]) / bhei          # 单位长 / 源像素
    bax, bay = [float(v) for v in ba.get("anchor", [0.5, 0.5])]
    rx0 = ((root[0] - bx) / bwid - bax) * (kk * bwid)
    ry0 = ((root[1] - by) / bhei - bay) * (kk * bhei)
    print("[tail] 基准 relaxed: emit框=(%d,%d,%d,%d) kk=%.8f 根偏移=(%.5f,%.5f)"
          % (bx, by, bwid, bhei, kk, rx0, ry0))
    for pid, fname, _, _, _ in POSES:
        cr = geo[pid][4]
        gx, gy, gw, gh = emit_box(os.path.join(redraw, fname))
        att = by_id[pid]
        # ★ 旧的 source_crop 是给那张**被替换掉的** AI 图配的（截掉画过长的
        #   直杆段）。新图是按弧长生成的，长度本来就对，留着它只会把根截掉。
        if att.pop("source_crop", None) is not None:
            print("[tail]   %s 摘掉过时的 source_crop" % pid)
        ax, ay = [float(v) for v in att.get("anchor", [0.5, 0.5])]
        rx = ((cr[0] - gx) / gw - ax) * (kk * gw)
        ry = ((cr[1] - gy) / gh - ay) * (kk * gh)
        att["sprite_h_rel"] = round(float(kk * gh), 6)
        att["pos_rel"] = [round(float(ba["pos_rel"][0] + rx0 - rx), 6),
                          round(float(ba["pos_rel"][1] + ry0 - ry), 6)]
        att["_tail_note"] = (
            "★ 2026-10-21 第二十九问：这张图是 tools/make_tail_poses.py 从 "
            "acc_tail_cat_relaxed.png **重铺**出来的，不是单独出的 AI 图。"
            "逐像素都是 relaxed 那条尾巴的颜色和毛流，只是沿另一条脊线铺。"
            "pos_rel / sprite_h_rel 是按 _emit 的几何口径反解的，"
            "保证四档**根部落在同一个模型坐标点**。")
        print("[tail] ~ %-14s emit框=(%d,%d,%d,%d) pos_rel=%s h_rel=%.6f"
              % (pid, gx, gy, gw, gh, att["pos_rel"], att["sprite_h_rel"]))
    with io.open(tp, "w", encoding="utf-8") as f:
        f.write(json.dumps(tbl, ensure_ascii=False, indent=2) + "\n")
    print("[tail] attachments.json 已更新")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
