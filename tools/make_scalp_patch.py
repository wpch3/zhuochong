#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把 seg_head 的「光头侧脸」补成「画了头发的头」（塗り足し）。

来历（2026-10-18 用户第九问 + 第十问）：
  用户看截图说「耳朵好像长在脸上」「脸消失了一部分」「部件没做完的样子」。
  挖出来的底图 seg_head 是一张**光头**：两只人耳完完整整画着、没有发际线。
  平时被鬓发盖着看不见，一旦换发型（把鬓发收起来扎上去）就全露出来。

  这不是我们自创的坑，教程里写得很清楚，而且是**必做工序**：
    · Live2D 官方 PSD 教程：拆件时「元画で隠れていた部分の描き足しを忘れずに。
      描き足しがないと動かしたときにパーツが分離して見える」
      https://docs.live2d.com/en/cubism-editor-tutorials/psd/
    · daigonozin《髪の毛を簡単に動かす》：「後ろの髪は空いているところを全部塗って、
      **それプラス頭部のレイヤーに直接髪の色を描いてしまいます**。
      これで髪同士レイヤーに隙間ができても、頭部のレイヤーに描いた髪の色が隙間を埋めてくれます」
      https://daigonozin.com/【live2d】髪の毛を簡単に動かす！｜素材の分け方/
    · copainter《VTuber立ち絵と差分の作り方》：AI 生成立ち絵をLive2D化する手順の中で
      「隠れている部分を描き足す。**この工程だけは省略できません**」
      https://blog.copainter.ai/vtuber-standing-character-guide/

这个工具干三件事（都只动 seg_head，不碰任何别的件）：
  ① **抹掉人耳**：耳朵那两块换成 AI 重绘里对应位置的头发；
  ② **补鬓发底下的翼**：make_sidehair_parts 挖走鬓发后留下的那两片"塗り足し"
     是**皮肤色**的，换成头发色 —— 那正是"脸消失一部分"的来源；
  ③ **颅顶铺发色**：发际线以上按垂直渐变混进发基色，发片之间漏缝时
     漏出来的是头发而不是头皮。

用法：
    python3 tools/make_scalp_patch.py --character xiaoxun --form teen
源图不存在就跳过（别的形态还没画，不该因此让整条流水线挂掉）。
"""
import argparse
import io
import json
import os
import sys

# 区域按 seg_head 自身包围盒的比例给，换形态不用改数
EAR_Y = (0.47, 0.84)      # 人耳 + 鬓发翼所在的纵向区间
EAR_X = (0.25, 0.73)      # 这两条竖线以外算"侧面"
DOME_Y = 0.60             # 这一行以上算颅顶（发际线以上）
HAIR_BASE = (201, 199, 216)   # 发基色，和 DC55 色卡的主发色同源


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--character", default="xiaoxun")
    ap.add_argument("--form", default="teen")
    ap.add_argument("--root", default=".")
    ap.add_argument("--redraw", default=None)
    a = ap.parse_args()

    from PIL import Image, ImageFilter
    import numpy as np

    base = os.path.join(a.root, "characters", a.character, "forms", a.form)
    seg_p = os.path.join(base, "sprites", "seg_head.png")
    red_p = a.redraw or os.path.join(a.root, "characters", a.character, "design",
                                     "redraw", "seg_head_scalp.png")
    if not os.path.exists(seg_p):
        print("[scalp] 没有 seg_head.png，跳过")
        return 0
    if not os.path.exists(red_p):
        print("[scalp] 没有重绘源 %s，跳过（%s 形态还没画）" % (red_p, a.form))
        return 0

    # ★ 1× 和 @2x 都要补：rig 引用的其实是 @2x。插在高清化（rebuild 17 步）之前跑
    #   时 @2x 还不存在，这里就只补 1×；单独补跑时两张都在，必须一起补，
    #   否则画面上看到的还是没补画的那张（2026-10-18 实际踩过）。
    targets = [seg_p]
    hi = os.path.join(base, "sprites", "seg_head@2x.png")
    if os.path.exists(hi):
        targets.append(hi)
    rc = 0
    for t in targets:
        rc |= patch_one(t, red_p, Image, ImageFilter, np)
    return rc


def patch_one(seg_p, red_p, Image, ImageFilter, np):
    orig = Image.open(seg_p).convert("RGBA")
    W, H = orig.size
    new = Image.open(red_p).convert("RGBA").resize((W, H), Image.LANCZOS)
    o = np.asarray(orig).astype(float)
    n = np.asarray(new).astype(float)
    yy, xx = np.mgrid[0:H, 0:W]
    fy, fx = yy / float(H), xx / float(W)

    inside = o[..., 3] > 8
    side = (fy >= EAR_Y[0]) & (fy <= EAR_Y[1]) & ((fx < EAR_X[0]) | (fx > EAR_X[1]))
    dome = fy < DOME_Y
    reg = (side | dome) & inside

    # ① + ② 用重绘图的像素换掉耳朵和翼
    use_n = reg & (n[..., 3] > 200)
    m = Image.fromarray((use_n * 255).astype(np.uint8)).filter(
        ImageFilter.GaussianBlur(2.5))
    w = (np.asarray(m).astype(float) / 255.0)[..., None]
    out = o.copy()
    out[..., :3] = o[..., :3] * (1 - w) + n[..., :3] * w

    # 重绘图在翼的最外沿没有内容 —— 那里必须铺发色，不能留肤色
    gap = reg & ~(n[..., 3] > 200)
    mg = Image.fromarray((gap * 255).astype(np.uint8)).filter(
        ImageFilter.GaussianBlur(3.0))
    wg = (np.asarray(mg).astype(float) / 255.0)[..., None]
    out[..., :3] = out[..., :3] * (1 - wg) + np.array(HAIR_BASE, dtype=float) * wg

    # ③ 颅顶铺发色：顶上全是发色，到发际线淡出。发际线以下（脸）一点不碰。
    ramp = np.clip((DOME_Y - fy) / max(1e-6, DOME_Y * 0.55), 0.0, 1.0)
    skin = (o[..., 0] > 225) & (o[..., 1] > 200) & (o[..., 2] > 185)
    wd = (ramp * inside * skin)[..., None] * 0.92
    out[..., :3] = out[..., :3] * (1 - wd) + np.array(HAIR_BASE, dtype=float) * wd

    res = Image.fromarray(np.clip(out, 0, 255).astype(np.uint8), "RGBA")
    res.save(seg_p)
    changed = int(((np.abs(np.asarray(res).astype(int) - o.astype(int))[..., :3]
                    .max(axis=2)) > 6).sum())
    print("[scalp] %s 补画完成：%d 像素被换成头发（耳朵 / 鬓发翼 / 颅顶）"
          % (os.path.basename(seg_p), changed))
    return 0


if __name__ == "__main__":
    sys.exit(main())
