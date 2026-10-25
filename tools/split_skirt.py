#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""split_skirt.py —— 把裙子从 seg_torso 里**整件切出来**（T66.16 / 第六十六问 S3）。

为什么非得切
------------
骨链（回転デフォーマ）在引擎里作用于**整个部件**：一个部件的 A_chain 是它所有网格
形变器 + `parts[].deformer` 那条链的并集，然后和部件矩阵相乘。所以只要裙子还长在
`seg_torso` 上，给裙子插一根转骨 = 把整个上身一起转飞（G66.6 记的就是这条）。
Live2D 的做法本来就是「一件衣服 = 一张アートメッシュ」，裙子有自己的网格、自己的
デフォーマ链。这里就是把烘焙在一起的两件衣服按像素拆开。

判据（缺一不可）
----------------
1. **无损**：裙件 + 掏掉裙子的躯干，按原来的位置合成回去，必须与原图**逐像素相同**
   （含 alpha）。做不到就说明切歪了 —— 边界像素被谁吃掉了一点，一摆动就是一条毛边。
2. **连通**：裙子用**从底行洪泛**取连通域，不是「颜色接近深蓝就算」。后者会把
   兜帽绳子、腰带这些同色的小件一起卷进来（实测：整图颜色阈值法切出来 35709 px，
   真正连通的裙区只有 27380 px）。
3. **幂等**：原件备份在 `sprites/_orig/split_skirt/`，每次从备份重切；
   改上游（body_parts）时 rebuild_parts.sh 会连这份备份一起作废。

产物
----
  sprites/skirt_main.png / skirt_main@2x.png   裙件（layer 96：腿 60/61 之上、躯干 100 之下）
  sprites/seg_torso*.png                      掏掉裙子的躯干
  sprites/body_parts.json                     多一条 skirt_main 条目
  sprites/skirt_split.json                    掩膜指纹 + bbox + 行号（make_rig 拿它对枢轴）

用法
----
  python3 tools/split_skirt.py --character xiaoxun --form teen
  python3 tools/split_skirt.py --character xiaoxun --form teen --force
"""
from __future__ import annotations

import argparse
import io
import json
import os
import shutil
import sys
from collections import deque

import numpy as np
from PIL import Image

NEW_ID = "skirt_main"
SRC_ID = "seg_torso"
# 腿（60/61）之上、seg_torso（100）之下：裙子夹在腿和外套之间。
# 97 是空档（95/96 是两条手臂的根，98/99 是脖子桩和补丁）—— 占 96 会和 arm_r_root 撞层，
# selfcheck 的「层号不重复」当场红。
LAYER = 97
SIG_V = 2
PAD = 14            # のりしろ：往「被别的部件完全盖住」的方向续多少像素（1x）


def navy_mask(a: np.ndarray) -> np.ndarray:
    """裙色族（深蓝）：B 明显高于 R、比白/青都暗。粗筛，连通域在后面收口。"""
    rgb = a[..., :3].astype(int)
    al = a[..., 3]
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    # ⚠ B 要明显高于 **G**，不是只高于 R：青袖（实测 108,192,192 / 84,157,166）的
    #   B 也高于 R，只卡 B>R 会把整条袖子算成裙色；裙子的 B−G 实测 55，青袖 0~9。
    # ⚠ 判据要同时卡 **B−R**、**B−G** 和 **G−R**：
    #   · 青袖（实测 108,192,192 / 84,157,166）的 B 也高于 R ⇒ 只卡 B>R 会把袖子算进来；
    #   · 裙子是**蓝**（B 高出 G 一大截； teen 62,70,102 → B−G=32，Q 版 49,50,107 → 57），
    #     青色是**青**（B≈G，B−G=0~9）；
    #   · 更稳的一条是 G−R：蓝的 G 和 R 差不多（1~8），青的 G 比 R 高 70 以上。
    #   三条一起卡，少女和 Q 版都能用同一套阈值（实测 teen 29415 px / Q 版 27256 px）。
    return (al > 60) & (b > r + 14) & (b > g + 8) & ((g - r) < 40) \
        & (b > 45) & (b < 210) & (r < 160)


def jacket_mask(a: np.ndarray) -> np.ndarray:
    """外套（白夹克 + 青色滚边）的像素。裙区里一个白像素都没有（实测 rows 430-499：
    min-channel>170 的比例是 0），所以这条判据在裙子上是干净的。"""
    rgb = a[..., :3].astype(int)
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    white = rgb.min(2) > 165
    teal = (g > 130) & (b > 130) & (r < 215) & (b > r + 5)
    return white | teal


def skirt_mask(a: np.ndarray) -> np.ndarray:
    """裙子掩膜 = 裙色像素里**形状像裙子的最大连通块**，再按行填内洞。

    ★ 第一版从「最下面 3 行」的裙色像素洪泛取连通域 —— 少女那张躯干裙子一直画到
      底边，能 work；Q 版的躯干连**腿**一起切了，裙子根本不挨着底边 ⇒ 种子为空
      ⇒ 0 像素（实测直接报「找不到裙子」）。所以改成**全图连通分量里挑裙子那块**。
    ★ 光「取最大」不够：裙色像素还有兜帽、腰带、两眼之间的阴影、腿上的暗部。
      判据必须带**几何**——裙子一定在躯干下半段、且是横向一大片：
        · 连通块中心落在 55% 高度以下；
        · 高度 ≥ 12% 图高、宽度 ≥ 22% 图宽。
      实测 Q 版：最大块 27146 px，bnd 行 216~398（躯干高 399）✔；
      若按"最大块"硬取，第一次跑出来的是**袖子/下摆条纹**连成的一整片（因为它
      顺着深色描边爬到青袖子上去了），所以 navy 的判据也收紧了（见 navy_mask）。
    行填只在连通块每行的最左/最右之间补，条件是 alpha>0 **且不是外套色**
    ——外套下摆横着压在裙子上，按行填会把那条青白条纹整段圈进来（Q 版实测：
    裙件里带出薄荷+白的下摆条纹，一摆就把外套下摆撕下来）。
    """
    H, W = a.shape[:2]
    navy = navy_mask(a)
    al = a[..., 3]
    seen = np.zeros((H, W), bool)
    best = np.zeros((H, W), bool)
    best_score = -1.0
    for sy, sx in zip(*np.nonzero(navy)):
        if seen[sy, sx]:
            continue
        comp = []
        q = deque([(int(sy), int(sx))])
        seen[sy, sx] = True
        while q:
            y, x = q.popleft()
            comp.append((y, x))
            for ny, nx in ((y - 1, x), (y + 1, x), (y, x - 1), (y, x + 1)):
                if 0 <= ny < H and 0 <= nx < W and navy[ny, nx] and not seen[ny, nx]:
                    seen[ny, nx] = True
                    q.append((ny, nx))
        ys, xs = np.array([c[0] for c in comp]), np.array([c[1] for c in comp])
        h = ys.max() - ys.min() + 1
        w = xs.max() - xs.min() + 1
        cy = ys.mean()
        looks_like_skirt = (cy > 0.55 * H) and (h >= 0.12 * H) and (w >= 0.22 * W)
        if not looks_like_skirt:
            continue
        if len(comp) > best_score:
            best_score = len(comp)
            best = np.zeros((H, W), bool)
            best[ys, xs] = True
    if best_score < 0:
        return np.zeros((H, W), bool)
    jk = jacket_mask(a)
    m = best.copy()
    for y in range(H):
        xs = np.flatnonzero(best[y])
        if xs.size >= 5:
            x0, x1 = int(xs[0]), int(xs[-1])
            seg = (al[y, x0:x1 + 1] > 0) & ~jk[y, x0:x1 + 1]
            m[y, x0:x1 + 1] = seg
    # ⚠ 兜底再排一次外套色：行填之外，连通块自己也可能顺着描边吃进几个外套像素。
    m &= ~jk
    return m


def grow_ring(arr: np.ndarray, mask: np.ndarray, pad: int = PAD):
    """从 mask 往外长 pad 像素，但**只许长到 alpha==255 的地方**。

    返回 (掩膜含新料, 新增的那一圈)。判据的理由见 underlay()。
    """
    allowed = arr[..., 3] >= 255
    grow = mask.copy()
    for _ in range(pad):
        g2 = grow.copy()
        g2[1:] |= grow[:-1]; g2[:-1] |= grow[1:]
        g2[:, 1:] |= grow[:, :-1]; g2[:, :-1] |= grow[:, 1:]
        grow = g2 & allowed
    return grow, grow & ~mask


def recolor_ring(arr: np.ndarray, src: np.ndarray, ring: np.ndarray,
                 pad: int = PAD):
    """把 ring 里的像素按**最近邻扩散**从 `src` 的不透明像素取色。

    颜色**只从裙子自己身上取**，绝不能把躯干的像素抄进来 —— 第一版允许从
    「掩膜 ∪ 新增区」里取色，结果把外套的白/青整块抄进了裙件，裙件里就长出
    一圈白夹克，一摆连夹克一起甩（截图上白边特别明显）。

    返回 (新图, **真的取到色**的那些点)。扩散够不到的点留在原样、也不算のりしろ：
    它们在原图里是外套自己的像素，抄进裙件就是把别人的料带走。
    """
    H, W = ring.shape
    px = arr.astype(np.int32).copy()
    hole = ring.copy()
    # 取色的**源**只认裙子自己那几个**不透明**的像素（半透明的抗锯齿边不进去，
    # 否则续出来的料会发灰）。然后一层一层往外长：新长出来的点也算源。
    known = src & (arr[..., 3] >= 250)
    if not known.any():
        known = src.copy()
    for _ in range(pad * 4):
        if not hole.any():
            break
        acc = np.zeros(px.shape, np.int32)
        cnt = np.zeros((H, W), np.int32)
        for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            sh = np.roll(known, (dy, dx), (0, 1))
            acc += np.roll(np.where(known[..., None], px, 0), (dy, dx), (0, 1)) * sh[..., None]
            cnt += sh
        fill = hole & (cnt > 0)
        if not fill.any():
            break
        px[fill] = acc[fill] // np.maximum(cnt[fill], 1)[:, None]
        known |= fill
        hole &= ~fill
    keep = ring & ~hole
    out = arr.copy()
    out[keep] = px[keep]
    out[keep, 3] = 255
    return out, keep


def underlay(arr: np.ndarray, mask: np.ndarray, pad: int = PAD):
    """给裙子补**のりしろ**：往「被躯干完全不透明地盖住」的方向续 pad 像素。

    为什么必须补
    ------------
    骨链一转，裙腰那条边会绕着枢轴歪一点。原画里裙子被外套/衬衫盖住的那部分是
    **不存在**的（画师没画），所以裙子一动，它原来占的位置就露出背景 —— 一道
    沿着外套内缘的缝。Live2D 的标准做法就是 塗り足し / のりしろ：往遮挡物的
    底下多画一圈，静止时看不见、动起来顶上去。

    安全性的判据（硬条件）
    ---------------------
    只往**躯干 alpha == 255** 的像素底下续。这样：
      · 静止时那圈料 100% 压在完全不透明的躯干底下 ⇒ 合成结果逐像素不变
        （composite_err 会真的验一遍，不是嘴上说）；
      · 躯干的半透明边（抗锯齿）一个像素都不碰 ⇒ 剪影不会被"续"胖。
    返回 (新掩膜, 改过色的图, 续了多少像素)。
    """
    _, add = grow_ring(arr, mask, pad)
    if not add.any():
        return mask, arr.copy(), 0
    out, keep = recolor_ring(arr, mask, add, pad)
    return (mask | keep), out, int(keep.sum())


def carve_pair(arr1x: np.ndarray, mask1x: np.ndarray, arr2x: np.ndarray | None,
               body_mask1x: np.ndarray | None = None, body_src: np.ndarray | None = None):
    """按 1× 掩膜切开 1× 和 @2x。

    返回 (裙 1x, 躯干 1x, 裙 2x, 躯干 2x, bbox1x)。
    bbox 必须**偶数对齐**（1× 里偶数坐标 → @2x 里 4 的倍数），否则两边的裁框
    错开一像素，渲染时 @2x 的 scale 是 ×0.5，就能在裙腰上看见一条细线。

    ★ 躯干要挖掉的只有 **body_mask1x（原掩膜，不含のりしろ）**：のりしろ 的
      活法就是"伸到躯干底下被它盖住"，躯干在那儿必须**留着**当遮挡物。
      第一版连のりしろ一起挖掉，等于既没遮挡又没补料 —— 实拍在 y=324 整行掉到
      alpha 149~155，肉眼是一条沿着外套内缘的浅缝。

    ★ @2x 的几何仍然用 kron 放大同一张掩膜（保证裁框对齐），但要多剔一类点：
      1× 里 alpha==255 的像素，放大到 @2x 之后它的四个孩子可能有一个是半透明
      的抗锯齿边（实测 14 个点 alpha=247）。那几个点如果算进裙件，静止合成就会
      把 alpha 从 247 抬成 254（剪影胖一丝）。判据和 1× 同口径：**只看 alpha==255**。
    """
    H, W = arr1x.shape[:2]
    ys, xs = np.nonzero(mask1x)
    x0, x1 = int(xs.min()), int(xs.max()) + 1
    y0, y1 = int(ys.min()), int(ys.max()) + 1
    x0 -= x0 % 2
    y0 -= y0 % 2
    x1 += x1 % 2
    y1 += y1 % 2
    x1, y1 = min(W, x1), min(H, y1)

    body_mask = mask1x if body_mask1x is None else body_mask1x
    add1x = mask1x & ~body_mask
    skirt = np.zeros_like(arr1x)
    skirt[mask1x] = arr1x[mask1x]
    # ★ 躯干必须从**没改过色的原图**挖：underlay() 会把 のりしろ 那一圈重新上色，
    #   那份"改色的图"只能给裙件用。第一版两处共用同一份，结果躯干自己那圈也变成
    #   了裙色 —— 而躯干是压在裙子**上面**的遮挡物，它一变深就是裙腰上方凭空多出
    #   一块深蓝、外套下摆被啃出一排锯齿（实拍 Q 版：2627 个像素整体变暗）。
    body = (arr1x if body_src is None else body_src).copy()
    body[body_mask] = 0
    s1 = skirt[y0:y1, x0:x1]
    b1 = body[y0:y1, x0:x1]

    s2 = b2 = None
    if arr2x is not None:
        mb2 = np.kron(body_mask, np.ones((2, 2), bool))
        add2 = np.kron(add1x, np.ones((2, 2), bool))
        m2 = np.kron(mask1x, np.ones((2, 2), bool)) & (mb2 | (arr2x[..., 3] >= 255))
        sk2 = np.zeros_like(arr2x)
        sk2[m2] = arr2x[m2]
        # @2x 的のりしろ也要换成裙子的料：直接用 arr2 的像素，那圈里是**外套**。
        ring2 = m2 & add2
        if ring2.any():
            sk2, _ = recolor_ring(sk2, mb2, ring2)
            sk2[~m2] = 0
        bd2 = arr2x.copy()
        bd2[mb2] = 0
        s2 = sk2[y0 * 2:y1 * 2, x0 * 2:x1 * 2]
        b2 = bd2[y0 * 2:y1 * 2, x0 * 2:x1 * 2]
    return s1, b1, s2, b2, (x0, y0, x1 - x0, y1 - y0)


def composite_err(orig: np.ndarray, skirt: np.ndarray, body: np.ndarray, box) -> int:
    """把掏空的躯干叠回裙件**上面**，与**原图**逐像素比；返回对不上的个数。

    ⚠ 顺序必须是 **躯干在上**：层号 skirt=97、torso=100，画的时候躯干压着裙子。
      第一版写成"裙子在上"，靠着"躯干在裙区被整个挖空"才碰巧等价，所以躯干一
      留下のりしろ（该留的）就整片假红。
    ⚠ 必须用**直通 alpha 的 over 公式**，不是 `src*a + dst*(1-a)` —— 后者是
      预乘口径，用在直通 alpha 图上会把半透明的裙边整体压暗。实测：裙摆边缘
      168~250 的半透明像素全部对不上（402 个），而且**只错在半透明处**，
      不看这条就以为是切歪了。
    ⚠ 也必须用整图口径比，不能只比裁框里：裁框外同样可能被误改。
    """
    x0, y0, w, h = box
    out = orig.astype(np.float64).copy()
    sk = skirt[y0:y0 + h, x0:x0 + w].astype(np.float64)
    base = body[y0:y0 + h, x0:x0 + w].astype(np.float64)
    sa = sk[..., 3:4] / 255.0            # 裙件
    ba = base[..., 3:4] / 255.0          # 躯干（在上）
    oa = ba + sa * (1.0 - ba)
    rgb = (base[..., :3] * ba + sk[..., :3] * sa * (1.0 - ba))
    rgb = np.where(oa > 1e-6, rgb / np.maximum(oa, 1e-6), 0.0)
    out[y0:y0 + h, x0:x0 + w, :3] = rgb
    out[y0:y0 + h, x0:x0 + w, 3] = oa[..., 0] * 255.0
    out = np.clip(out, 0, 255).astype(np.int32)
    ref = orig.astype(np.int32)
    # ⚠ alpha ≈ 0 的像素**不参与比色**：原图在透明区里留着抠像的 RGB 残留
    #   （实测 6.3 万个 alpha=0/1 的像素带着近白/近红的颜色），它们一个都画不出来，
    #   拿它们的 RGB 判"切歪了"是假红。判据只看「看得见的像素」+ alpha 本身。
    vis = (ref[..., 3] > 1) | (out[..., 3] > 1)
    d_a = np.abs(out[..., 3] - ref[..., 3])
    d_rgb = np.abs(out[..., :3] - ref[..., :3]).max(axis=2)
    bad = (d_a > 1) | (vis & (d_rgb > 1))
    return int(bad.sum())       # ±1 = 8 位合成的舍入误差，肉眼不可见


def to_full(crop: np.ndarray, box, shape):
    """把裁过的图贴回整图尺寸（composite_err 用整图口径）。"""
    full = np.zeros(shape, crop.dtype)
    x0, y0, w, h = box
    full[y0:y0 + h, x0:x0 + w] = crop
    return full


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--character", required=True)
    ap.add_argument("--form", required=True)
    ap.add_argument("--root", default=".")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--quiet", action="store_true")
    a = ap.parse_args()

    base = os.path.join(a.root, "characters", a.character, "forms", a.form)
    sp = os.path.join(base, "sprites")
    bpj = os.path.join(sp, "body_parts.json")
    if not os.path.exists(bpj):
        print("[裙件] 缺少 %s（先跑 make_body_parts.py）" % bpj)
        return 2
    with io.open(bpj, encoding="utf-8") as f:
        meta = json.load(f)
    parts = {p["id"]: p for p in meta.get("parts", [])}
    if SRC_ID not in parts:
        print("[裙件] 没有 %s，跳过" % SRC_ID)
        return 0

    sig = {"v": SIG_V}
    if not a.force and meta.get("skirt_split", {}).get("sig") == sig:
        if not a.quiet:
            print("[裙件] 签名未变，跳过（--force 强制重做）")
        return 0

    # —— 备份原件（只备份一次；上游重切躯干时 rebuild_parts.sh 会删掉这份） ——
    orig_dir = os.path.join(sp, "_orig", "split_skirt")
    os.makedirs(orig_dir, exist_ok=True)
    src1 = os.path.join(sp, SRC_ID + ".png")
    bak1 = os.path.join(orig_dir, SRC_ID + ".png")
    if not os.path.exists(bak1):
        shutil.copy2(src1, bak1)
    src2 = os.path.join(sp, SRC_ID + "@2x.png")
    bak2 = os.path.join(orig_dir, SRC_ID + "@2x.png")
    has2 = os.path.exists(src2)
    if has2 and not os.path.exists(bak2):
        shutil.copy2(src2, bak2)

    arr1 = np.asarray(Image.open(bak1).convert("RGBA")).copy()
    arr2 = np.asarray(Image.open(bak2).convert("RGBA")).copy() if has2 else None
    mask = skirt_mask(arr1)
    if mask.sum() < 500:
        print("[裙件] 找不到裙子（掩膜只有 %d px），跳过 —— 形态可能没有裙子" % int(mask.sum()))
        return 0

    mask_base = mask.copy()                 # 原掩膜：躯干要挖的面积（不含のりしろ）
    arr1_ring, n_pad = None, 0
    # —— 三道几何闸（T66.16c）——
    # 掩膜"跑偏"不会报错，只会切出一件很怪的东西（第一次跑 Q 版时它顺着描边爬上
    # 袖子、把外套下摆整条撕下来）。三种跑偏各有判据，装不进这几条就不写盘：
    #   ① 裙子在躯干下半段：掩膜顶行必须在 35% 高度以下；
    #   ② 掩膜里不许有外套色（白/青）：那说明外套被算进裙子了；
    #   ③ 躯干至少留下 55% 的不透明料：切太多就是"看着像裙子、其实是整个人"。
    H0 = arr1.shape[0]
    top_row = int(np.nonzero(mask.any(axis=1))[0][0])
    jk = jacket_mask(arr1)
    if top_row < 0.35 * H0:
        print("[裙件] ✗ 掩膜顶行 %d 只到躯干高度的 %.0f%%，不像裙子（裙子在下半段），不写盘"
              % (top_row, 100.0 * top_row / H0))
        return 4
    bad_jk = int((mask & jk).sum())
    if bad_jk > int(0.01 * mask.sum()):
        print("[裙件] ✗ 掩膜里有 %d 个外套色像素（白/青），切下来就是一整块外套，不写盘" % bad_jk)
        return 4
    keep_frac = float(((arr1[..., 3] > 0) & ~mask_base).sum()) / max(1, int((arr1[..., 3] > 0).sum()))
    if keep_frac < 0.55:
        print("[裙件] ✗ 躯干只剩 %.0f%% 的料（<55%%），这一刀切太狠了，不写盘" % (keep_frac * 100))
        return 4

    mask, arr1_ring, n_pad = underlay(arr1, mask)
    s1, b1, s2, b2, box = carve_pair(arr1_ring, mask, arr2, body_mask1x=mask_base,
                                     body_src=arr1)
    body1 = arr1.copy()
    body1[mask_base] = 0
    err = composite_err(arr1, to_full(s1, box, arr1.shape), body1, box)
    if err:
        print("[裙件] ✗ 切开之后合成不回去：%d 个像素对不上（切歪了，不写盘）" % err)
        return 3
    # @2x 也自查一遍（口径同 1×）
    if arr2 is not None:
        box2 = (box[0] * 2, box[1] * 2, box[2] * 2, box[3] * 2)
        m2b = np.kron(mask_base, np.ones((2, 2), bool))
        body2 = arr2.copy()
        body2[m2b] = 0
        e2 = composite_err(arr2, to_full(s2, box2, arr2.shape), body2, box2)
        if e2:
            print("[裙件] ✗ @2x 合成不回去：%d 个像素" % e2)
            return 3

    Image.fromarray(s1, "RGBA").save(os.path.join(sp, NEW_ID + ".png"))
    if s2 is not None:
        Image.fromarray(s2, "RGBA").save(os.path.join(sp, NEW_ID + "@2x.png"))
    Image.fromarray(body1, "RGBA").save(src1)
    if arr2 is not None:
        m2b = np.kron(mask_base, np.ones((2, 2), bool))
        body2 = arr2.copy()
        body2[m2b] = 0
        Image.fromarray(body2, "RGBA").save(src2)

    # 裙子在画布上的坐标 = 躯干左上角 + 裁框左上角（body_parts 的 pos 是 1× 切图内坐标）
    tp = parts[SRC_ID]
    waist_row = int(np.nonzero(mask.any(axis=1))[0][0])
    hem_row = int(np.nonzero(mask.any(axis=1))[0][-1])
    cx = float(np.nonzero(mask.any(axis=0))[0].mean())
    note = ("裙子从 seg_torso 切出来的独立件（T66.16）：只有它自己能接旋转骨，"
            "否则一转就把上身带飞。层 %d = 腿(60/61)之上、躯干(100)之下" % LAYER)
    entry = {"id": NEW_ID, "file": "sprites/%s.png" % NEW_ID,
             "pos": [tp["pos"][0] + box[0], tp["pos"][1] + box[1]],
             "size": [box[2], box[3]], "group": tp.get("group", "chest"),
             "layer": LAYER, "note": note}
    meta["parts"] = [p for p in meta["parts"] if p["id"] != NEW_ID]
    i = next(i for i, p in enumerate(meta["parts"]) if p["id"] == SRC_ID)
    meta["parts"].insert(i, entry)      # 紧挨着躯干，层序由 layer 字段决定
    meta["parts"].sort(key=lambda p: p["layer"])
    # 掩膜单独存一张（1× 口径）：换装、别的形态复用裙件时要按**同一张**掩膜切，
    # 不然 AI 重绘件的裙边会和原件的掩膜差一两像素，接缝处看得见。
    Image.fromarray((mask.astype(np.uint8) * 255), "L").save(
        os.path.join(sp, "skirt_mask.png"))
    # ★ 再存一张**不含のりしろ**的（= 躯干该挖的面积）。两张都要存：
    #   换装包要按同一张掩膜从**换装自己的躯干图**上切裙件（G66.9），
    #   切件用 mask_full、挖躯干用 mask_base，只存一张就还原不出另一张。
    Image.fromarray((mask_base.astype(np.uint8) * 255), "L").save(
        os.path.join(sp, "skirt_mask_base.png"))
    meta["skirt_split"] = {
        "sig": sig, "id": NEW_ID,
        "pad_px": n_pad,
        "box_1x": list(box),
        "px_1x": int(mask.sum()),
        "rows_1x": [waist_row, hem_row],
        "center_x_1x": round(cx, 1),
        "lossless": 0,
        "why": "骨链（回転デフォーマ）作用于整个部件，裙子必须独立才能接自己的转骨（G66.6）",
    }
    with io.open(bpj, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
        f.write("\n")
    # make_rig 要拿它算骨链枢轴（腰线一行、摆到哪）
    with io.open(os.path.join(sp, "skirt_split.json"), "w", encoding="utf-8") as f:
        json.dump(meta["skirt_split"], f, ensure_ascii=False, indent=2)
        f.write("\n")
    if not a.quiet:
        print("[裙件] %s %dx%d @%s（%d px 1x）；躯干 %.0f%% 的料留给外套；无损校验 0 误差"
              % (NEW_ID, box[2], box[3], [tp["pos"][0] + box[0], tp["pos"][1] + box[1]],
                 int(mask.sum()),
                 100.0 * (1 - mask.sum() / max(1, int((arr1[..., 3] > 0).sum())))))
        print("[裙件] 裙腰第 %d 行、裙摆第 %d 行（1x 切图内），中心 x=%.1f，のりしろ %d px"
              % (waist_row, hem_row, cx, n_pad))
    return 0


if __name__ == "__main__":
    sys.exit(main())
