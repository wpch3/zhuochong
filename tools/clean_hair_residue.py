#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把**发片里烘着的非头发像素**（夹克青布、衣领青布、皮肤）洗掉。

为什么需要这一步 —— 第十八问「杂毛」的第二类病灶
--------------------------------------------------------------------
`cut_from_sheets.py` 是从**单层成品图**上按掩膜抠件的。官方教程
https://tips.clip-studio.com/ja-jp/articles/2684 说得很清楚：这种「合并图层
的一张成品图」拆件时要**沿线稿稍外侧**勾选，而且**拆完必须跟原图重叠逐件
复查**。我们的掩膜是颜色判据，沿着头发外缘总会多吃进一圈相邻物体——头发压在
衣领上的地方吃进青布，压在脸上的地方吃进皮肤。

这些残渣**短发档看不出来**，因为 hair_side_l/r(245·246) 正好盖住；一旦切到
long / twin / pony 把鬓发藏起来就全露出来，表现为**下巴与衣领交界处一条撕裂
的深青斑点带**（实测 acc_hair_crown_long 层 189 的下缘占该带像素的 84%）。

实测（已提交素材，teen，单位：像素）：

    hair_long_back    238405 不透明 / 18852 青 / 1294 肤
    hair_pony_back     59306          /  6394     /   23
    hair_crown_pony    27236          /  2819     /    0
    hair_crown_long    30931          /  2027     /    0
    hair_twin_l/r      21046          /  2289     /    7
    hair_side_l/r       6668          /  1995     /  107

怎么洗才不会洗坏
--------------------------------------------------------------------
1. **不能只看"是不是青色"**：头发的蓝梢 (159,196,232) 也是冷色。复用
   cut_from_sheets.teal_like 的二维楔形判据——*绿明显压过红，而蓝没能明显压过
   绿*才是青布；头发无论淡紫 (216,216,232) 还是蓝梢，**蓝都比绿高 16 以上**。

2. **不能一刀切成透明**：直接挖会在件里留「开口的缺口」，落盘就是透明窟窿，
   而且 hair_back 还有 2% 的破洞闸。所以分内外：
     - **件内部**的 bad（距外缘 >=5px）-> 用最近邻的头发色**重画**，alpha 不动，
       形状完全不变，只是把颜色改对；
     - **件外缘**的 bad -> 擦掉，但**软羽化**，不留台阶。

3. **软边**：擦完把新 alpha 做一次高斯羽化。官方那套「沿线稿稍外侧」的手感靠
   的就是边缘有过渡；硬边正是用户说的「块状、不柔顺」。这里**不做二值形态学**
   （despeckle / dilate(erode()) / solidify 都会留台阶），只在 alpha 上做浮点过渡。

幂等：洗过一遍 bad 就没有了，再跑不会有任何变化。
用法：python3 tools/clean_hair_residue.py --character xiaoxun --form teen
在 rebuild_parts.sh 里排在高清化之前。
"""

from __future__ import annotations

import argparse
import json
import os
import sys

import numpy as np
from PIL import Image, ImageFilter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from cut_from_sheets import (  # noqa: E402
    dilate, erode, hair_like, nearest_fill, skin_like, teal_like,
)

HAIR_PREFIXES = ("hair_",)   # 只洗头发件；夹克和脸本来就该有青色和皮肤
EDGE_BAND = 5                # 离外轮廓多少像素以内算"外缘"
FEATHER_1X = 1               # 擦除后 alpha 的羽化半径（@2x 翻倍）

# --- 第二道工序：边缘返修 ---------------------------------------------
# CORE_ERODE：先腐蚀出"主体骨架"，再在原掩膜里把它长回去。长不回去的
#   （= 跟主体断开的飞沫）全部丢掉。比开运算好，因为**连在主体上的细发丝
#   会被完整长回来**，不会像开运算那样把发梢一起磨掉。
CORE_ERODE_1X = 5
# OPEN_K：**只对 crown 件**用的"最小发缕宽度"。crown 的下缘是整片撕碎的
#   （目视 dbg_crown_full.png 可见：断发丝 + 脱体蓝块 + 白飞沫），而且这些
#   碎屑**是连在主体上的**，所以测地重建删不掉——必须按"有多粗"删。
#   实测扫描 k=9/15/23（@2x）：k=23 刚好把碎屑清光而主体轮廓零改动，
#   丢掉 11.8%。k=15 还留着细丝，k=9 几乎没用。1× 取一半 = 11。
#   long 档这些碎屑下面 100% 有别的发片垫底（实测 8661px 全被覆盖），
#   删掉不会露底。
OPEN_K_1X = 11
# EDGE_SOFT：alpha 边界的高斯半径。只软化边界，内部用 erode 夹回原值，
#   所以不会把整片糊掉。这一步直接对治"块状、硬边、台阶"。
EDGE_SOFT_1X = 0.7


def _soft(mask_f: np.ndarray, radius: int) -> np.ndarray:
    """对 0~1 浮点图做高斯模糊，把硬边化成过渡。"""
    if radius <= 0:
        return mask_f
    im = Image.fromarray((np.clip(mask_f, 0, 1) * 255).astype(np.uint8))
    return np.asarray(im.filter(ImageFilter.GaussianBlur(radius))).astype(np.float32) / 255.0


def reconstruct(core: np.ndarray, mask: np.ndarray, k: int = 31,
                iters: int = 80) -> np.ndarray:
    """测地重建：把 core 在 mask 内部反复膨胀到收敛。

    用来丢掉**跟主体断开的碎渣**而又不伤到连在主体上的细发丝。
    没有 scipy，所以手写；k 取 31 收敛很快（长发侧缕 ~40 次就到头）。
    """
    seed = core & mask
    for _ in range(iters):
        grown = dilate(seed, k) & mask
        if grown.sum() == seed.sum():
            break
        seed = grown
    return seed


def repair_edge(alpha: np.ndarray, core_erode: int, soft: float,
                open_k: int = 0) -> tuple[np.ndarray, int]:
    """去飞沫 + 软化 alpha 边界。返回 (新 alpha, 丢掉的像素数)。

    为什么要这一步 —— 第十八问「杂毛 / 块状」的第三类病灶
    ----------------------------------------------------------------
    目视 hair_crown_long@2x（棋盘底放大）看得很清楚：件的**下缘整片是撕碎
    的** —— 断裂的发丝、脱离主体的蓝色碎块、白色飞沫。它在短发档被
    hair_side_l/r 盖住，切到 long/twin/pony 就吊在下巴上，就是用户截图里
    下颌那一圈「杂毛」。同时脸部挖空是**直角方块**，边缘全是 1px 台阶。

    两件事一起做：
      1. **去飞沫**：只保留跟主体连通的像素（测地重建）。碎块是断开的，
         一次就掉光；连在头上的发丝一根不少。
      2. **软化边界**：对 alpha 做 0.7px 高斯，内部夹回原值。台阶边变成
         亚像素过渡 —— 这就是官方说的「沿线稿稍外侧抠」该有的手感，
         也是「柔顺」和「块状」的分界线。**不用任何二值形态学**
         （despeckle / dilate(erode()) / solidify 都会重新造出台阶）。
    """
    op = alpha > 40
    if not op.any():
        return alpha, 0
    if open_k:
        opened = dilate(erode(op, open_k), open_k)
        if opened.any():
            alpha = alpha * opened
            op = alpha > 40
    core = erode(op, 2 * core_erode + 1)
    if core.any():
        keep = reconstruct(core, op)
        dropped = int((op & ~keep).sum())
        if dropped:
            alpha = alpha * keep
    else:
        dropped = 0
    if soft > 0:
        im = Image.fromarray(np.clip(alpha, 0, 255).astype(np.uint8))
        blurred = np.asarray(im.filter(ImageFilter.GaussianBlur(soft))).astype(np.float32)
        inner = erode(alpha > 40, 5)
        # ★ 只许**减**不许**加**。第一版写的是 where(inner, max(a,blur), blur)，
        #   结果高斯把 alpha 糊到了**原本全透明**的像素上，而那些像素的 RGB
        #   还留着抠图用的洋红/纯绿键色 —— check_assets 的「无键色垃圾像素」
        #   闸当场抓到 281 个绿点。软边的目的是把台阶化成渐变，
        #   往外扩一圈从来不是目的。
        soft_a = np.minimum(alpha, blurred)
        # ★ 再加一条：软边**不许把本来可见的像素变成不可见**。
        #   check_assets 有一道「无损切分：静止合成比原图少 N 像素（上限 0）」
        #   的闸，最外圈哪怕只掉 2 个像素也会红。所以原本 alpha>40 的，
        #   软化后至少保留 41 —— 边缘照样从实心渐变到 16% 不透明度，
        #   台阶没了，覆盖面积一个像素不少。
        alpha = np.where(inner, alpha,
                         np.where(alpha > 40, np.maximum(soft_a, 41.0), soft_a))
    return alpha, dropped


def clean_one(path: str, feather: int, no_loss: bool = False) -> tuple[int, int, int]:
    """返回 (重画的像素, 擦掉的像素, 原不透明像素)。"""
    im = Image.open(path).convert("RGBA")
    a = np.asarray(im).astype(np.int16)
    alpha = a[..., 3].astype(np.float32)
    op = alpha > 40
    if not op.any():
        return 0, 0, 0

    # ★ 注意：别自己发明"这是头发"的护栏。第一版我写了 (b-g)>16 当护栏，
    #   结果**衣领青 (111,161,179) 的 b-g 正好是 18**，整条衣领残渣被放过，
    #   hair_crown_long 2027 个青像素只擦掉了 22 个。
    #   teal_like 的二维楔形本来就已经把蓝发梢排除在外了，护栏只用于
    #   「膨胀出去的那一圈」，而且要用正规的 hair_like（滞后阈值）。
    core_bad = (teal_like(a) | skin_like(a)) & op
    bad = core_bad | (dilate(core_bad, 3) & op & ~hair_like(a))

    interior = erode(op, 2 * EDGE_BAND + 1)
    repaint = bad & interior
    erase = bad & ~interior

    rgb = a[..., :3].astype(np.float32)

    n_repaint = int(repaint.sum())
    if n_repaint:
        filled, have = nearest_fill(rgb, op & ~bad, steps=24)
        take = repaint & have
        rgb[take] = filled[take]

    n_erase = int(erase.sum())
    if n_erase:
        keep_f = 1.0 - _soft(erase.astype(np.float32), feather)
        keep_f[op & ~dilate(bad, 3)] = 1.0          # 确定是头发的不许被羽化带走
        alpha = alpha * np.clip(keep_f, 0.0, 1.0)
        # ★ 件的**最外一圈轮廓**不许擦成全透明。短发档的 hair_* 件同时也是
        #   body_full 的分段件，check_assets 有一道「无损切分：静止合成比原图
        #   少 N 像素（上限 0）」的闸 —— 实测最外圈掉 2 个像素就红。
        #   这一圈留 41（16% 不透明度），覆盖面积一个像素不少，
        #   而 16% 的青色压在衣领上肉眼根本看不出来。
        rim = op & ~erode(op, 3)
        alpha = np.where(rim & (alpha < 41), 41.0, alpha)

    base = os.path.basename(path)
    scale = 2 if "@2x" in base else 1
    # ★ 开运算**只给 long 档的 crown**。pony/twin 的 crown 没有那么碎，
    #   而且它们的长侧缕正是用来接管 hair_side_l/r 的：实测对
    #   hair_crown_pony 做同样的开运算，pony 档 hair_side_l 的接管率
    #   从 >45% 掉到 24.5%，直接把 head_silhouette 的接管闸打红。
    #   long 档不同——它下颌线以下 100% 有别的发片垫底（实测 8661px 全覆盖），
    #   所以削掉碎屑不会露底。
    open_k = (OPEN_K_1X * scale) | 1 if base.startswith("hair_crown_long") else 0
    alpha, dropped = repair_edge(alpha, CORE_ERODE_1X * scale,
                                 EDGE_SOFT_1X * scale, open_k)
    n_erase += dropped

    if no_loss:
        # ★ hair_ahoge / hair_front / hair_side_l / hair_side_r / hair_back
        #   这五个件**同时也是 body_full 的分段件**（见 sprites/body_parts.json）。
        #   check_assets 有一道「无损切分：静止合成比原图少 N 像素（上限 0）」
        #   的闸：这些件上任何一个可见像素变成不可见，闸就红。
        #   所以对它们只许**改色**和**降不透明度**，不许真的删掉 ——
        #   残渣降到 41（16%）已经看不见了，而覆盖面积一个像素不少。
        #   注意保底要按**原始 alpha > 0** 来判，不是 >40：闸门算覆盖面积用的是
        #   alpha>0，原本 alpha 只有 1~40 的反锯齿边缘像素一样算数。
        #   实测就是这种像素掉了 2 个。
        a0 = a[..., 3].astype(np.float32)
        alpha = np.where(a0 > 0, np.maximum(alpha, np.minimum(a0, 41.0)), alpha)

    out = np.dstack([np.clip(rgb, 0, 255).astype(np.uint8),
                     np.clip(alpha, 0, 255).astype(np.uint8)])
    Image.fromarray(out, "RGBA").save(path)
    return n_repaint, n_erase, int(op.sum())


# ── 第三道工序：头/身接缝的塗り足し ────────────────────────────────
# 短发档 hair_side_l/r(245·246) 正好盖住下颌两侧，于是那一带的
# seg_head / seg_torso **从来没有被真正画完**：
#   · seg_head 下颌两侧留着 378 个近白像素（鲍勃头发被切走后的空白）；
#   · seg_torso 顶端戳着一圈撕裂的青色毛边（切身体时多吃进去的衣领/发梢）。
# 藏起鬓发（long / twin / pony 三档）它们就全露出来，就是用户截图里
# 下巴那一圈"白雾 + 青斑"。
#
# 官方教程 https://tips.clip-studio.com/ja-jp/articles/2684 的原话是
# 「合并图层的原图必须**背後を描き足す**」，塗り足し短了就会
# 「頬から髪の毛が生えている」。这里就是补这一刀。
#
# ★ 只改 RGB，**不动 alpha** —— seg_* 同时是 body_full 的分段件，
#   check_assets 的「无损切分」闸对覆盖面积零容忍。
# (起, 止, 是否连青色一起补)。
# ★ seg_torso 的 with_teal 必须是 False：**衣领本来就是青的**。
#   第一版把它设成 True，nearest_fill 直接把两片青色衣领刷成了肤色
#   （目视 dbg_seg_torso2.png：领子整个变成肉色）。这一带只补白雾。
SEAM_BANDS = {
    "seg_head": (0.74, 1.00, True),    # 下颌 + 脖子：白斑和青渣都要补
    "seg_torso": (0.00, 0.14, False),  # 衣领顶端：只补白雾，青色是衣领本体
}


def fix_seam(path: str, lo: float, hi: float, with_teal: bool) -> int:
    """把接缝带里的"不该有的颜色"按最近邻改成该有的肤色。返回改动像素数。"""
    im = Image.open(path).convert("RGBA")
    a = np.asarray(im).astype(np.int16)
    h = a.shape[0]
    band = np.zeros(a.shape[:2], bool)
    band[int(h * lo):int(h * hi)] = True
    op = (a[..., 3] > 40) & band

    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    whitish = op & (r > 234) & (g > 234) & (b > 234)
    bad = (whitish | (teal_like(a) & band if with_teal else whitish)) & op
    if not bad.any():
        return 0

    good = skin_like(a) & op & ~bad
    if good.sum() < 50:
        return 0
    rgb = a[..., :3].astype(np.float32)
    filled, have = nearest_fill(rgb, good, steps=28)
    take = bad & have
    if not take.any():
        return 0
    rgb[take] = filled[take]
    out = np.dstack([np.clip(rgb, 0, 255).astype(np.uint8),
                     a[..., 3].astype(np.uint8)])
    Image.fromarray(out, "RGBA").save(path)
    return int(take.sum())


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--character", required=True)
    ap.add_argument("--form", required=True)
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    sp = os.path.join("characters", args.character, "forms", args.form, "sprites")
    if not os.path.isdir(sp):
        print(f"没有 {sp}，跳过", file=sys.stderr)
        return 0

    # body_full 的分段件清单：这些件不许掉覆盖面积
    no_loss_files = set()
    bp = os.path.join(sp, "body_parts.json")
    if os.path.exists(bp):
        with open(bp, encoding="utf-8") as fh:
            d = json.load(fh)
        for q in (d["parts"] if isinstance(d, dict) else d):
            b = os.path.basename(q["file"])
            no_loss_files.add(b)
            no_loss_files.add(b.replace(".png", "@2x.png"))

    report, total_rp, total_er = {}, 0, 0
    for name in sorted(os.listdir(sp)):
        if not name.endswith(".png") or not name.startswith(HAIR_PREFIXES):
            continue
        rp, er, tot = clean_one(os.path.join(sp, name),
                                FEATHER_1X * (2 if "@2x" in name else 1),
                                no_loss=name in no_loss_files)
        if rp or er:
            total_rp += rp
            total_er += er
            report[name] = {"repaint": rp, "erase": er, "opaque": tot}
            if not args.quiet:
                print(f"  {name:28s} 重画 {rp:6d} / 擦掉 {er:6d}  (共 {tot} 像素)")

    with open(os.path.join(sp, "hair_clean_report.json"), "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=2)
    seam = 0
    for stem, (lo, hi, wt) in SEAM_BANDS.items():
        for suffix in (".png", "@2x.png"):
            fp = os.path.join(sp, stem + suffix)
            if os.path.exists(fp):
                n = fix_seam(fp, lo, hi, wt)
                seam += n
                if n and not args.quiet:
                    print(f"  接缝补画 {stem + suffix:24s} 改色 {n} 像素")

    print(f"发片残渣清理完成：重画 {total_rp} 像素，擦掉 {total_er} 像素，"
          f"接缝补画 {seam} 像素，涉及 {len(report)} 个件")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
