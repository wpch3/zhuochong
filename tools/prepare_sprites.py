#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
prepare_sprites.py - 把 AI 生成的角色设计图处理成立绘部件素材。

输入：characters/<角色>/design/design_sheet_*.png（纯色背景，推荐洋红 #FF00FF）
输出：characters/<角色>/forms/<形态>/sprites/*.png（透明背景）
      以及一份验收报告 JSON（分辨率、透明通道、残留、色卡比对）

规则来自交接文件第五之二节与第八节：
  - 透明背景、无白底/棋盘格残留、边缘干净；
  - 颜色与设定色卡一致（取样比对，超阈值报警）；
  - 统一画布：默认 848x1360，角色脚底落在 origin；
  - 原图另存，不覆盖。

用法：
  python3 tools/prepare_sprites.py --character xiaoxun --form teen \
      --sheet characters/xiaoxun/design/design_sheet_short.png \
      --canvas 848x1360 --height-ratio 0.95 --report /tmp/sprite_report.json
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter

try:
    import numpy as np
    from PIL import Image
except ImportError as e:  # pragma: no cover
    print(f"[错误] 需要 pillow 与 numpy：{e}", file=sys.stderr)
    sys.exit(2)

# 与 rig / 配置保持一致的键色
KEY_COLORS = [(255, 0, 255), (0, 255, 0), (255, 255, 255)]


def load_rgb(path: str) -> Image.Image:
    im = Image.open(path)
    if im.mode != "RGB":
        im = im.convert("RGB")
    return im


def _keyness(rgb: np.ndarray, kind: str) -> np.ndarray:
    """「像不像键色」的单通道度量。键色本身取最大值，正常前景 <= 0。

    洋红键  min(R,B) - G    纯洋红 255 / 肤色 -14 / 线稿 #5A5A6E 0 / 青袖 -100
    绿幕键  G - max(R,B)
    白底键  min(R,G,B)
    这三条都满足「键色 = 两个通道拉满、第三个通道空」的结构，所以同一个
    `a = 1 - (keyness - LO) / (HI - LO)` 斜坡能直接估出覆盖率 a：
    对 C = a·F + (1-a)·K，keyness 是线性的，而正常前景的 keyness ≈ 0，
    于是 keyness(C) ≈ (1-a)·keyness(K) ⇒ a ≈ 1 - keyness(C)/keyness(K)。
    """
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    if kind == "magenta":
        return np.minimum(r, b) - g
    if kind == "green":
        return g - np.maximum(r, b)
    return np.minimum(np.minimum(r, g), b)


def key_out(im: Image.Image, tol: int = 60, despill: int = 1) -> tuple[Image.Image, tuple]:
    """按键色抠透明：软 matte + 解混，**保住角色自己的描边**。

    2026-10-21 重写。旧版为什么必须换掉（第三十二问实测）
    ----------------------------------------------------
    旧版三步都在吃线稿：
      1. `alpha = where(hard_bg, 0, 255)` —— **二值 alpha**，没有过渡带；
      2. `magenta_ish = (r>90)&(b>90)&(g*100 < max(r,b)*62)` —— 线稿 #5A5A6E
         和背景混到 **15%** 就命中，于是轮廓线外侧那半条被判成背景删掉；
      3. 「去彩边」把 `dist<=180` 的像素颜色**用内部干净像素外扩覆盖** ——
         剩下那半条线于是被脸颊的奶油色/夹克的白盖掉。
    加上最后**未预乘**的 LANCZOS 缩放（透明像素还留着洋红 RGB），
    产物就是「描边没了 + 轮廓一圈近白光晕」。实测沿剪影 26 个扫描点，
    模板描边亮度 37~118，旧产物 103~244，**21 个点描边完全消失**；
    下颌一带因此比模板宽 +50~60px（最多 2 倍），用户看到的就是「脸胖」。

    新版做法
    --------
      · 键色取边框**中位数实测值**（AI 图背景其实是 (252,3,238) 不是纯 #FF00FF，
        拿 255 当基准会把整片背景判成 alpha 0.095 的薄雾）；
      · `a = 1 - clip((keyness - LO)/(HI - LO))`，HI = 键色自己的 keyness；
      · 解混 `F = (C - (1-a)K)/a` 还原被背景冲淡的真实颜色（线稿因此变回深色，
        而不是被换成邻居的浅色）；
      · 明确落在容差球里的像素硬清零，避免背景噪声留薄雾。

    ★ 2026-10-12 那次失败（LESSONS「不要再去重写抠像」）踩的是**缩放**那一脚：
      「软 matte + 预乘 LANCZOS」被负瓣过冲打出亮斑。这次把缩放单独做成
      `resize_premultiplied()`，并在反预乘前加 `RGB <= alpha` 的钳位，
      过冲就回不来了。同一套指标复测：白边光晕 494 → 213、硬台阶 5708 → 4895、
      描边与模板的平均偏差 95.6 → 43.5。
    """
    a_in = np.asarray(im).astype(np.int16)
    h, w, _ = a_in.shape
    # 背景色判定：取四条边框采样点的**中位数**。不用四角平均值是因为
    # 表情特写图里角色肩膀会占住下边两角（见 make_face_parts.py），
    # 四角一致的要求会误报；中位数对少量非背景点不敏感。
    border = np.concatenate([
        a_in[2, ::max(1, w // 32)].reshape(-1, 3),
        a_in[h - 3, ::max(1, w // 32)].reshape(-1, 3),
        a_in[::max(1, h // 32), 2].reshape(-1, 3),
        a_in[::max(1, h // 32), w - 3].reshape(-1, 3),
    ]).astype(np.float32)
    key = np.median(border, axis=0)
    close = np.abs(border - key).max(axis=1) < 60
    if close.mean() < 0.25:
        raise SystemExit("[错误] 边框颜色不一致，无法自动抠背景；请提供纯色背景的设计图")
    kr, kg, kb = (float(v) for v in key)
    if kr > 120 and kb > 120 and kg < 120:
        kind = "magenta"
    elif kg > 120 and kr < 120 and kb < 120:
        kind = "green"
    else:
        kind = "white"

    rgb = np.asarray(im).astype(np.float32)
    hi = float(_keyness(key.reshape(1, 1, 3), kind)[0, 0])
    if hi <= 1.0:                       # 非标准键色，退回纯距离法
        hi = 255.0
    lo = hi * 0.10                      # 低于这个 keyness 一律算前景（线稿/深紫都在这下面）
    kn = _keyness(rgb, kind)
    alpha = 1.0 - np.clip((kn - lo) / max(hi - lo, 1.0), 0.0, 1.0)

    dist = np.sqrt(((rgb - key) ** 2).sum(axis=2))
    alpha[dist <= tol] = 0.0            # 明确是背景（抗 AI 图的背景噪声）
    alpha[alpha < 0.04] = 0.0

    # 解混：C = a·F + (1-a)·K  ⇒  F = (C - (1-a)·K)/a
    aa = np.maximum(alpha, 1e-3)[..., None]
    fg = np.clip((rgb - (1.0 - aa) * key) / aa, 0.0, 255.0)
    fg = np.where(alpha[..., None] > 0.999, rgb, fg)

    hard = (alpha > 0.5).astype(np.uint8)
    # 去孤立点：不透明但 8 邻域几乎全透明的像素视为噪点
    for _ in range(2):
        nb = np.zeros_like(hard, dtype=np.int16)
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                if dx == 0 and dy == 0:
                    continue
                nb += np.roll(np.roll(hard, dy, axis=0), dx, axis=1)
        drop = (hard == 1) & (nb <= 1)
        alpha[drop] = 0.0
        hard[drop] = 0
    # 补孤立洞：透明但 8 邻域几乎全不透明
    nb = np.zeros_like(hard, dtype=np.int16)
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            if dx == 0 and dy == 0:
                continue
            nb += np.roll(np.roll(hard, dy, axis=0), dx, axis=1)
    alpha[(hard == 0) & (nb >= 7)] = 1.0

    # 保留主体连通块（去掉漂浮的碎片）；只按硬掩码判，软边跟着主体走
    keep = keep_largest_blob((alpha > 0.35).astype(np.uint8) * 255, min_ratio=0.002)
    alpha[keep == 0] = 0.0

    # 解混 F = (C-(1-a)K)/a 的误差放大倍数是 1/a，所以 alpha 很低的软边会把
    # 背景噪声放大成彩点（实测发梢最外缘 (254,27,203)@a=64 这种粉点 155 个）。
    # 对**这一小撮**像素做颜色外推：拿半径 2 内不透明邻居的均色顶上。
    # ★ 这和旧版那个「去彩边」不是一回事 —— 旧版对 `dist<=180` 的**全不透明**
    #   像素也外推，整条轮廓线因此被脸颊色盖掉；这里只碰 alpha<0.7 且解混后
    #   仍然明显偏键色的像素，线稿（keyness ≈ 0~46 且 alpha=1）碰不到。
    if despill:
        kn_fg = _keyness(fg, kind)
        suspect = (alpha > 0) & (alpha < 0.70) & (kn_fg > 40)
        if suspect.any():
            solid = (alpha > 0.90)[..., None].astype(np.float32)
            acc = np.zeros_like(fg)
            cnt = np.zeros(alpha.shape + (1,), dtype=np.float32)
            for dy in (-2, -1, 0, 1, 2):
                for dx in (-2, -1, 0, 1, 2):
                    if dx == 0 and dy == 0:
                        continue
                    sm_ = np.roll(np.roll(solid, dy, axis=0), dx, axis=1)
                    acc += np.roll(np.roll(fg, dy, axis=0), dx, axis=1) * sm_
                    cnt += sm_
            ok = suspect & (cnt[..., 0] > 0)
            fg = np.where(ok[..., None], acc / np.maximum(cnt, 1.0), fg)

    # 最后一道：解混在低 alpha 处会放大误差，残余的洋红/绿压回灰度
    if despill:
        rr, gg, bb = fg[..., 0], fg[..., 1], fg[..., 2]
        if kind == "magenta":
            bad = (alpha > 0) & ((rr + bb - 2 * gg) > 110)
        elif kind == "green":
            bad = (alpha > 0) & ((2 * gg - rr - bb) > 110)
        else:
            bad = np.zeros(alpha.shape, dtype=bool)
        if bad.any():
            lum = (rr + gg + bb) / 3.0
            fg[..., 0] = np.where(bad, lum, rr)
            fg[..., 1] = np.where(bad, lum, gg)
            fg[..., 2] = np.where(bad, lum, bb)

    rgba = np.dstack([np.clip(fg, 0, 255), np.clip(alpha * 255.0, 0, 255)]).astype(np.uint8)
    return Image.fromarray(rgba, "RGBA"), tuple(int(round(v)) for v in key)


def resize_premultiplied(im: Image.Image, size: tuple[int, int], box=None,
                         resample=Image.LANCZOS) -> Image.Image:
    """预乘后缩放，再反预乘。**直接对直通 alpha 缩放会把透明像素的垃圾 RGB 糊进边缘**
    —— 旧版 body_full 轮廓那一圈近白光晕就是这么来的（透明像素还留着洋红/白底 RGB）。

    LANCZOS 有负瓣，强边缘预乘值会过冲，再除以很小的 alpha 就被放大成亮斑
    （2026-10-12 的坑，见 LESSONS）。所以反预乘前先钳 `RGB <= alpha`，
    并把 alpha < 6 的像素整个清零。
    """
    arr = np.asarray(im.convert("RGBA")).astype(np.float32)
    a = arr[..., 3:4] / 255.0
    pm = np.dstack([arr[..., :3] * a, arr[..., 3]])
    sm = Image.fromarray(np.clip(pm, 0, 255).astype(np.uint8), "RGBA")
    sm = sm.resize(size, resample, box=box)
    out = np.asarray(sm).astype(np.float32)
    al = out[..., 3]
    pr = np.minimum(out[..., :3], al[..., None])     # ★ 钳住负瓣过冲
    al = np.where(al < 6, 0.0, al)
    pr = np.where(al[..., None] < 6, 0.0, pr)
    av = np.maximum(al, 1e-4)[..., None] / 255.0
    rgb = np.clip(np.where(av > 1e-4, pr / av, 0.0), 0, 255)

    # ── 振铃清理 ──────────────────────────────────────────────────────
    # 钳位只保证「反预乘后不超过 255」，管不住**通道之间**的振铃：
    # 洋红→内容的强边上绿通道下冲、红蓝上冲，预乘 (60,5,55)/a=60 反出来就是
    # (255,21,234) 一个粉点。实测 445x1292 的 body_full 上这种点 155 个（洋红）
    # + 196 个（近白），全在发梢最外缘、alpha 16~80。
    # 判据只认「低 alpha + 颜色离不透明邻居特别远」，所以碰不到正常软边，
    # 更碰不到 alpha=1 的线稿。
    # ★ 判据只认「**过冲**」，不认「不一样」：
    #   振铃的特征是比周围所有不透明邻居**更亮**、或**更偏键色**（更饱和的品红/绿）。
    #   而轮廓线稿的特征恰恰相反 —— 它比邻居**更暗**。
    #   先用过「颜色离邻居均值 > 90 就替换」，结果把白袜子旁边的黑描边换成了白，
    #   描边与模板的偏差从 43.5 退回 59.4（2026-10-21 实测），所以必须分方向。
    lum = 0.299 * rgb[..., 0] + 0.587 * rgb[..., 1] + 0.114 * rgb[..., 2]
    sat = rgb[..., 0] + rgb[..., 2] - 2 * rgb[..., 1]        # 品红度（负值 = 偏绿）
    opaque = (al > 230).astype(np.float32)
    acc = np.zeros_like(rgb)
    cnt = np.zeros(al.shape, dtype=np.float32)
    nmax_lum = np.full(al.shape, -1e9, dtype=np.float32)
    nmax_sat = np.full(al.shape, -1e9, dtype=np.float32)
    nmin_sat = np.full(al.shape, 1e9, dtype=np.float32)
    for dy in (-2, -1, 0, 1, 2):
        for dx in (-2, -1, 0, 1, 2):
            if dx == 0 and dy == 0:
                continue
            o = np.roll(np.roll(opaque, dy, axis=0), dx, axis=1)
            acc += np.roll(np.roll(rgb, dy, axis=0), dx, axis=1) * o[..., None]
            cnt += o
            ol = np.roll(np.roll(lum, dy, axis=0), dx, axis=1)
            os_ = np.roll(np.roll(sat, dy, axis=0), dx, axis=1)
            nmax_lum = np.where(o > 0, np.maximum(nmax_lum, ol), nmax_lum)
            nmax_sat = np.where(o > 0, np.maximum(nmax_sat, os_), nmax_sat)
            nmin_sat = np.where(o > 0, np.minimum(nmin_sat, os_), nmin_sat)
    has = cnt > 0
    mean = acc / np.maximum(cnt, 1.0)[..., None]
    too_bright = has & (lum - nmax_lum > 25)
    too_keyed = has & ((sat - nmax_sat > 60) | (nmin_sat - sat > 60))
    fix = (al > 0) & (al < 200) & (too_bright | too_keyed)
    rgb = np.where(fix[..., None], mean, rgb)

    # ── 退化分支：细到没有不透明邻居的地方（呆毛尖、发梢最外缕）──────────
    # 上面那轮只拿 alpha>230 的邻居当替换源。呆毛尖整条宽不到 3px，
    # 半径 2 内一个 alpha>230 的邻居都找不到（实测邻域 alpha 全在 26~161），
    # 于是 body_full(236,16) 那颗 (158,96,255,a=45) 的紫点直接漏网，
    # check_assets 的「无键色垃圾像素」上限是 0，一颗就判红。
    # 这里把门槛放宽到「比自己亮一倍 alpha 的邻居」，仍然只修**过冲**像素。
    soft_src = (al > np.maximum(al * 2.0, 60.0)).astype(np.float32)
    acc2 = np.zeros_like(rgb)
    cnt2 = np.zeros(al.shape, dtype=np.float32)
    smax_sat = np.full(al.shape, -1e9, dtype=np.float32)
    smin_sat = np.full(al.shape, 1e9, dtype=np.float32)
    for dy in (-2, -1, 0, 1, 2):
        for dx in (-2, -1, 0, 1, 2):
            if dx == 0 and dy == 0:
                continue
            # 「邻居 alpha > 本像素 alpha 的两倍」—— 逐像素比较，所以要先 roll 再比
            oa = np.roll(np.roll(al, dy, axis=0), dx, axis=1)
            o = ((oa > np.maximum(al * 2.0, 60.0)).astype(np.float32))
            acc2 += np.roll(np.roll(rgb, dy, axis=0), dx, axis=1) * o[..., None]
            cnt2 += o
            os2 = np.roll(np.roll(sat, dy, axis=0), dx, axis=1)
            smax_sat = np.where(o > 0, np.maximum(smax_sat, os2), smax_sat)
            smin_sat = np.where(o > 0, np.minimum(smin_sat, os2), smin_sat)
    has2 = (cnt2 > 0) & ~has
    mean2 = acc2 / np.maximum(cnt2, 1.0)[..., None]
    fix2 = (al > 0) & (al < 120) & has2 & (
        (sat - smax_sat > 60) | (smin_sat - sat > 60))
    rgb = np.where(fix2[..., None], mean2, rgb)
    return Image.fromarray(np.dstack([rgb, al]).astype(np.uint8), "RGBA")



def keep_largest_blob(alpha: np.ndarray, min_ratio: float = 0.002) -> np.ndarray:
    """只保留最大的若干连通块（面积 >= 最大块 * min_ratio）。"""
    h, w = alpha.shape
    lab = np.zeros((h, w), dtype=np.int32)
    cur = 0
    areas = {}
    idx = np.argwhere(alpha > 0)
    for y, x in idx:
        if lab[y, x]:
            continue
        cur += 1
        stack = [(int(y), int(x))]
        lab[y, x] = cur
        cnt = 0
        while stack:
            cy, cx = stack.pop()
            cnt += 1
            for dy in (-1, 0, 1):
                for dx in (-1, 0, 1):
                    ny, nx = cy + dy, cx + dx
                    if 0 <= ny < h and 0 <= nx < w and alpha[ny, nx] > 0 and lab[ny, nx] == 0:
                        lab[ny, nx] = cur
                        stack.append((ny, nx))
        areas[cur] = cnt
    if not areas:
        return alpha
    biggest = max(areas.values())
    keep = {k for k, v in areas.items() if v >= biggest * min_ratio}
    out = alpha.copy()
    out[~np.isin(lab, list(keep))] = 0
    return out


def magenta_residue(rgba: np.ndarray) -> int:
    """统计仍然“偏洋红”的不透明像素（残留检测，容差之外的漏网像素）。

    ★ 2026-10-21 收紧：旧判据只看 `R+B-2G>90`，把**角色自己的深紫线稿**
    （实测 (48,2,79) / (62,9,102)）整条算成残留 —— LESSONS 2026-10-12 已经
    点过这个名，但判据一直没改。重写抠像后线稿被正确保住，这个指标就从
    24 跳到 1259，全是误报。
    真·键色残留一定是**亮**的（键色 R、B 两个通道接近拉满），线稿是暗的，
    所以加一条亮度下限就能分开。"""
    r, g, b, a = rgba[..., 0].astype(int), rgba[..., 1].astype(int), rgba[..., 2].astype(int), rgba[..., 3]
    m = (a > 60) & ((r + b) - 2 * g > 90) & (r > 150) & (b > 150)
    return int(m.sum())


def bbox_of(alpha: np.ndarray, thr: int = 8):
    ys, xs = np.where(alpha > thr)
    if len(xs) == 0:
        return None
    return int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())


def check_white_residue(rgba: np.ndarray) -> int:
    """统计白底/白 matte 残留（“轮廓一圈近白光晕”的典型特征）。

    ★ 2026-10-21 收紧：旧判据是「近白 + 半透明」，**白夹克和白袜子自己的软边
    全被算成残留**（LESSONS 2026-10-12 已点名）。白 matte 残留与正常软边的
    区别在于**邻居**：正常软边旁边一定有不透明的白色本体，而 matte 残留是
    凭空长在深色/彩色边缘外面的一圈。所以加一条「8 邻域里没有不透明近白像素」。
    """
    r, g, b, a = rgba[..., 0], rgba[..., 1], rgba[..., 2], rgba[..., 3]
    near_white = (r > 235) & (g > 235) & (b > 235)
    semi = (a > 10) & (a < 245)
    solid_white = near_white & (a >= 245)
    nb = np.zeros(a.shape, dtype=bool)
    for dy in (-2, -1, 0, 1, 2):
        for dx in (-2, -1, 0, 1, 2):
            nb |= np.roll(np.roll(solid_white, dy, axis=0), dx, axis=1)
    return int((near_white & semi & ~nb).sum())


def palette_report(rgba: np.ndarray, k: int = 10) -> list[dict]:
    """取样主要颜色（用于与设定色卡比对）。"""
    a = rgba[..., 3]
    px = rgba[a > 200][:, :3]
    if len(px) == 0:
        return []
    px = px[:: max(1, len(px) // 20000)]
    q = (px // 12 * 12)
    cnt = Counter(map(tuple, q.tolist()))
    out = []
    for color, n in cnt.most_common(k):
        out.append({"hex": "#%02X%02X%02X" % color, "share": round(n / len(q), 4)})
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--character", required=True)
    ap.add_argument("--form", required=True)
    ap.add_argument("--sheet", required=True)
    ap.add_argument("--canvas", default="848x1360")
    ap.add_argument("--height-ratio", type=float, default=0.95,
                    help="角色高度占画布高度的比例")
    ap.add_argument("--tol", type=int, default=60)
    ap.add_argument("--out-name", default="body_full.png")
    ap.add_argument("--report", default=None)
    ap.add_argument("--root", default=".")
    ap.add_argument("--fit", default=None,
                    help="几何锁：模板裁框原点与缩放 x0,y0,scale（覆盖 design/body_fit.json）")
    ap.add_argument("--size", default=None, help="配合 --fit 的输出尺寸 WxH")
    ap.add_argument("--no-fit", action="store_true",
                    help="忽略 design/body_fit.json，按 bbox 自动裁（首次定版时用）")
    args = ap.parse_args()

    cw, ch = (int(v) for v in args.canvas.lower().split("x"))
    im = load_rgb(args.sheet)
    rgba_im, key = key_out(im, tol=args.tol)
    arr = np.asarray(rgba_im)

    bb = bbox_of(arr[..., 3])
    if bb is None:
        print("[错误] 抠图后没有不透明像素", file=sys.stderr)
        return 2
    x0, y0, x1, y1 = bb
    char_w, char_h = x1 - x0 + 1, y1 - y0 + 1

    # ── 几何锁（★ 不能让抠图判据的变动把整张图挪位置） ─────────────────
    # 「按抠完的 bbox 裁剪」这条路有个致命性质：**判据一变，bbox 就变**，
    # 整张 body_full 跟着平移，于是 design/anchors.json、17 个切件 JSON 里
    # 上百个像素常数全部错位 —— 而且错得很小、不报错、只是哪儿都对不齐。
    # 2026-10-21 重写抠像时实测：新判据多留了 1724 个不透明像素，
    # 直接按 bbox 裁会横向差 2px。
    # 所以一旦某个角色的 body_full 定版，就把「模板裁框 + 缩放比」写进
    # design/body_fit.json，以后只认它。拟合方法：把候选产物和已定版的
    # body_full 在内部（腐蚀 4 次）逐像素比色差，在 (x0,y0,scale) 上搜最小值
    # —— 小寻实测收敛到 **平均色差 0.21**，±1px 的邻居是 6.6~11.2，
    # 说明这是亚像素级唯一解。
    fit_path = os.path.join(args.root, "characters", args.character, "design", "body_fit.json")
    fit = None
    if args.fit:
        fx, fy, fs = (float(v) for v in args.fit.split(","))
        fw, fh = (int(v) for v in args.size.lower().split("x")) if args.size else (None, None)
        fit = {"box": [fx, fy], "scale": fs, "size": [fw, fh]}
    elif os.path.exists(fit_path) and not args.no_fit:
        with open(fit_path, encoding="utf-8") as f:
            allfit = json.load(f)
        fit = allfit.get(os.path.basename(args.sheet)) or allfit.get(args.form)

    if fit:
        fx, fy = fit["box"]
        fs = float(fit["scale"])
        new_w, new_h = fit["size"]
        scale = fs
        sprite = resize_premultiplied(
            rgba_im, (new_w, new_h),
            box=(fx, fy, fx + new_w / fs, fy + new_h / fs))
        print(f"[几何锁] {os.path.basename(fit_path) if not args.fit else '--fit'}："
              f"模板裁框 ({fx:.2f},{fy:.2f}) 缩放 {fs:.6f} → {new_w}x{new_h}")
    else:
        # 目标高度
        target_h = int(ch * args.height_ratio)
        scale = target_h / char_h
        new_w = max(1, int(round(char_w * scale)))
        new_h = max(1, int(round(char_h * scale)))
        sprite = resize_premultiplied(
            rgba_im, (new_w, new_h), box=(x0, y0, x1 + 1, y1 + 1))

    if new_w > cw:
        raise SystemExit(f"[错误] 角色宽度 {new_w} 超过画布宽度 {cw}")
    out_dir = os.path.join(args.root, "characters", args.character, "forms", args.form, "sprites")
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, args.out_name)
    sprite.save(out_path)

    # 复核：读回来检查
    back = np.asarray(Image.open(out_path).convert("RGBA"))
    bb2 = bbox_of(back[..., 3])
    report = {
        "source": args.sheet,
        "output": out_path,
        "key_color": list(key),
        "canvas": [cw, ch],
        "sprite_size": [back.shape[1], back.shape[0]],
        "scale": round(scale, 4),
        "alpha_bbox": list(bb2) if bb2 else None,
        "transparent_ratio": round(float((back[..., 3] <= 8).mean()), 4),
        "white_residue_pixels": check_white_residue(back),
        "magenta_residue_pixels": magenta_residue(back),
        "palette": palette_report(back),
        # 建议的交互区域（画布坐标）：头顶到下巴约 21% 角色高度
        "suggested_regions": suggest_regions(back.shape[1], back.shape[0], cw, ch),
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if args.report:
        with open(args.report, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
    if report["white_residue_pixels"] > 200:
        print("[警告] 检测到较多白色半透明残留，请检查抠图容差", file=sys.stderr)
    if report["magenta_residue_pixels"] > 200:
        print("[警告] 检测到较多洋红残留（键色未清干净）", file=sys.stderr)
    return 0


def suggest_regions(w: int, h: int, cw: int, ch: int) -> dict:
    """给出摸头/身体/脚部的建议区域（画布坐标，角色居中）。"""
    x = (cw - w) // 2
    head_h = int(h * 0.24)
    body_top = int(h * 0.24)
    body_h = int(h * 0.60)
    feet_top = body_top + body_h
    return {
        "head": [x + int(w * 0.10), 0, int(w * 0.80), head_h],
        "body": [x + int(w * 0.12), body_top, int(w * 0.76), body_h],
        "feet": [x + int(w * 0.12), feet_top, int(w * 0.76), h - feet_top],
        "origin_x": cw // 2,
        "origin_y": h,
        "sprite_w": w,
        "sprite_h": h,
    }


if __name__ == "__main__":
    sys.exit(main())
