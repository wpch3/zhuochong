#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""make_sidehair_parts.py - 把侧发（左右两缕垂在脸旁的头发）和后发（头顶那一整团）拆成独立零件。

为什么要拆这两件：
  到 A9 为止，引擎已经有了「网格形变 + 多段摆链 + 关键帧曲线」，但**头发只有呆毛和刘海
  两件在动**，整个脑袋的轮廓还是一块死贴图。侧发是全身摆幅最大的零件（Live2D 的
  サイドヘア），后发是「头一转，整团头发慢半拍」的那一件（後ろ髪）—— 拆完这两件，
  头部才算有「发量」。

两件的切法完全不同（对应 docs/ART_PARTS.md 五、里的两种套路）：

  侧发 = **AI 重绘型**。它压在脸颊/下颌/脖子上，底下的脸在原画里一个像素都没有
         （用户 D19：被遮挡区域必须 AI 生图重绘）。所以要一张「把侧发去掉、露出
         整张脸 + 耳朵 + 脖子」的重绘图，按虹膜对齐后，把侧发占掉的那块换成重绘像素。
  后发 = **剪影外无损切出型**。头顶那团头发在脸的**外面**，背后什么都没有，
         纯几何切就够。它画在脸**下面**（层 170），再往脸底下多铺一圈「塗り足し」
         （发色往内扩 BLEED_IN 像素，被脸挡住看不见），这样摆动时不会露出背景。

坑（都踩过）：
  * 侧发的发梢垂进了「头/躯干重叠带」（y>278 那一段 seg_head 与 seg_torso 各存了一份
    半透明副本）。只从 seg_head 里挖，发梢会在躯干那份副本里留下一个不动的「幽灵梢」。
    → 掩码同时作用在两张图上，零件像素直接取 body_full.png（原画，alpha 完整）。
  * 侧发根部要留 BLEED_ROOT 行「重复像素」：这几行在 seg_head 里**不挖掉**，
    零件里也有一份。摆动曲线用 tip（顶固定、梢摆动），所以这几行永远不动，
    切口因此永远不会露出来。
  * 重绘图的脸比原画窄的地方，补画会留下一条透明缝。→ 补完之后做 GROW_PX 像素的
    颜色外扩（把补丁边上的皮肤往外涂），保证摆到最大幅度也不会露底。

用法：
  ~/.imgenv/bin/python tools/make_sidehair_parts.py --character xiaoxun --form teen \
      --redraw characters/xiaoxun/design/redraw/head_nosidehair.png
"""
from __future__ import annotations
import argparse, json, os, sys

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from make_bangs_parts import components, iris_centers   # noqa: E402


# ⚠ 不能用 make_bangs_parts 里的 dilate/erode：它们是 np.roll 实现的，**会绕圈**。
# 刘海不贴图边所以没事；侧发左边那缕一直顶到 x=0，一膨胀就绕到右边去了，
# 结果左侧发零件把右侧发也吃了进去（第一版切出来的零件宽 244，整个头那么宽）。
def shift(m, dy, dx):
    out = np.zeros_like(m)
    H, W = m.shape
    y0, y1 = max(0, dy), min(H, H + dy)
    x0, x1 = max(0, dx), min(W, W + dx)
    if y0 < y1 and x0 < x1:
        out[y0:y1, x0:x1] = m[y0 - dy:y1 - dy, x0 - dx:x1 - dx]
    return out


def dilate(m, r=1):
    out = m.copy()
    for _ in range(r):
        acc = out.copy()
        for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            acc |= shift(out, dy, dx)
        out = acc
    return out


def erode(m, r=1):
    return ~dilate(~m, r)

SCALE      = 3      # 对齐时放大的倍数（和 make_bangs_parts 一致）
BLEED_ROOT = 16     # 侧发根部往上多带几行「重复像素」（切口藏在里面）
BLEED_IN   = 14     # 后发往脸底下多铺几像素「塗り足し」
GROW_PX    = 8      # 补画之后往外涂几像素，补上重绘比原画窄留下的缝
LAYER      = {"hair_back": 170, "hair_side_l": 245, "hair_side_r": 246}


def fill_holes(mask):
    """把 mask 内部的空洞填掉（从四边灌水，灌不到的空白就是洞）。"""
    free = ~mask
    out = np.zeros(mask.shape, bool)
    stack = []
    H, W = mask.shape
    for x in range(W):
        for y in (0, H - 1):
            if free[y, x] and not out[y, x]:
                out[y, x] = True; stack.append((y, x))
    for y in range(H):
        for x in (0, W - 1):
            if free[y, x] and not out[y, x]:
                out[y, x] = True; stack.append((y, x))
    while stack:
        y, x = stack.pop()
        for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            v, u = y + dy, x + dx
            if 0 <= v < H and 0 <= u < W and free[v, u] and not out[v, u]:
                out[v, u] = True; stack.append((v, u))
    return ~out


def largest(mask, seeds_mask):
    """取与 seeds_mask 相连的那些连通块（不是只取最大的，碎发丝也要带上）。"""
    out = np.zeros(mask.shape, bool)
    for pts in components(mask, 1):
        arr = np.zeros(mask.shape, bool)
        ys = np.array([p[0] for p in pts]); xs = np.array([p[1] for p in pts])
        arr[ys, xs] = True
        if (arr & seeds_mask).any():
            out |= arr
    return out


def soft_mask(mask, passes=2, gain=1.35, bias=0.18):
    """二值掩码 → 约 2px 软边（和刘海那件同一套，避免出现"剪刀印"）。"""
    m = mask.astype(np.float32)
    for _ in range(passes):
        acc = m.copy()
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                if dy or dx:
                    acc += shift(m, dy, dx)
        m = acc / 9.0
    m = np.clip(m * gain - bias, 0.0, 1.0)
    m[mask & (m > 0.75)] = 1.0
    return m


def grow_colors(rgba, region, steps):
    """把 rgba 里已有颜色往 region 内的透明像素外扩 steps 圈（最近邻取平均）。

    ⚠ 取色源必须卡 alpha > SRC_A（不是 > 0）。原画里散着几百个 alpha=1~4 的
    「垃圾像素」（抠像残留，RGB 是纯绿 (0,255,0) 之类），肉眼完全看不见，
    但只要被当成颜色源往外扩，就会被重新写成 alpha=255 的亮绿点。
    实测：躯干那一步扩出了 88 个纯绿像素，侧发一摆就在下巴边上闪一颗绿点。
    """
    SRC_A = 32
    out = rgba.copy()
    alpha = out[..., 3] > SRC_A
    for _ in range(steps):
        tgt = region & ~(out[..., 3] > 0)
        if not tgt.any():
            break
        acc = np.zeros(out.shape[:2] + (3,), np.float32)
        cnt = np.zeros(out.shape[:2], np.float32)
        for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            sh_a = shift(alpha, dy, dx)
            sh_c = np.dstack([shift(out[..., c], dy, dx) for c in range(3)]).astype(np.float32)
            acc += np.where(sh_a[..., None], sh_c, 0)
            cnt += sh_a
        take = tgt & (cnt > 0)
        for c in range(3):
            out[..., c] = np.where(take, (acc[..., c] / np.maximum(cnt, 1)).round(), out[..., c])
        out[..., 3] = np.where(take, 255, out[..., 3])
        alpha = alpha | take          # 新填的才加进取色源，垃圾像素始终不算
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--character", required=True)
    ap.add_argument("--form", required=True)
    ap.add_argument("--redraw", required=True, help="AI 重绘的「无侧发」头（洋红底）")
    ap.add_argument("--root", default=".")
    ap.add_argument("--root-y", type=int, default=0,
                    help="侧发根部切线（seg_head 局部 y）；0 = 按虹膜自动算")
    ap.add_argument("--force", action="store_true", help="已经拆过也重切")
    args = ap.parse_args()

    base = os.path.join(args.root, "characters", args.character, "forms", args.form)
    sp = os.path.join(base, "sprites")
    bp_path = os.path.join(sp, "body_parts.json")
    with open(bp_path, encoding="utf-8") as f:
        bp = json.load(f)
    have = {p["id"] for p in bp["parts"]}
    if "hair_side_l" in have and not args.force:
        print("侧发/后发已经拆过（body_parts.json 里有 hair_side_l），跳过")
        return 0

    pos_of = {p["id"]: p["pos"] for p in bp["parts"]}
    head_pos = pos_of["seg_head"]
    torso_pos = pos_of["seg_torso"]
    head = Image.open(os.path.join(sp, "seg_head.png")).convert("RGBA")
    torso = Image.open(os.path.join(sp, "seg_torso.png")).convert("RGBA")
    body = Image.open(os.path.join(sp, "body_full.png")).convert("RGBA")
    W, H = head.size
    ha = np.array(head).astype(int)
    hal, hrgb = ha[..., 3], ha[..., :3]

    # ---------------------------------------------------------- 1) 对齐重绘图
    src_big = Image.new("RGBA", (W, H), (255, 0, 255, 255))
    src_big.alpha_composite(head)
    src_big = src_big.convert("RGB").resize((W * SCALE, H * SCALE), Image.LANCZOS)
    gen = Image.open(args.redraw).convert("RGB")
    (sx0, sy0, _), (sx1, sy1, _) = iris_centers(np.array(src_big).astype(int))
    (gx0, gy0, _), (gx1, gy1, _) = iris_centers(np.array(gen).astype(int))
    k = (((sx1 - sx0) ** 2 + (sy1 - sy0) ** 2) ** 0.5
         / ((gx1 - gx0) ** 2 + (gy1 - gy0) ** 2) ** 0.5)
    g2 = gen.resize((int(round(gen.width * k)), int(round(gen.height * k))), Image.LANCZOS)
    dx = (sx0 + sx1) / 2 - ((gx0 + gx1) / 2) * k
    dy = (sy0 + sy1) / 2 - ((gy0 + gy1) / 2) * k
    big = Image.new("RGB", src_big.size, (255, 0, 255))
    big.paste(g2, (int(round(dx)), int(round(dy))))
    aligned = np.array(big.resize((W, H), Image.LANCZOS)).astype(int)
    # 洋红底判据要宽：缩放之后边界上是"洋红 + 内容"的混合色（像 (200,120,200)），
    # 只卡纯洋红会把一圈粉边当成内容贴到脸上（第一版脸颊外面就是一圈粉）。
    # 判完再把"内容"往里收 2px，把混了洋红的过渡带整条扔掉（despill）。
    gen_bg = ((aligned[..., 0] - aligned[..., 1] > 40)
              & (aligned[..., 2] - aligned[..., 1] > 40))
    gen_bg = ~erode(~gen_bg, 3)
    iris_y = (sy0 + sy1) / 2 / SCALE
    y_root = args.root_y or int(round(iris_y - 26))

    # ---------------------------------------------------------- 2) 分区
    solid = hal > 100
    warm = (hrgb[..., 0] > hrgb[..., 2] + 18) & (hrgb[..., 0] > 200)      # 皮肤
    teal = ((hrgb[..., 1] - hrgb[..., 0] > 55) & (hrgb[..., 2] - hrgb[..., 1] < 20))  # 衣领
    hairish = hrgb[..., 2] >= hrgb[..., 0] - 6        # 发色家族（淡紫/蓝梢/线稿都偏冷）
    # 五官保护区：眼睛（以虹膜为心的圆）和嘴在原画里也是冷色，光看颜色会被当成
    # 头发切走。位置直接取 make_eye_parts / make_mouth_parts 已经量出来的数，
    # 不靠"填洞"去兜 —— 填洞会从外眼角的缝里漏出去（第一版整只眼睛都被切走了）。
    yy = np.arange(H)[:, None] * np.ones((1, W))
    xx = np.ones((H, 1)) * np.arange(W)[None, :]
    feat = np.zeros((H, W), bool)
    for ix, iy in ((sx0 / SCALE, sy0 / SCALE), (sx1 / SCALE, sy1 / SCALE)):
        feat |= (xx - ix) ** 2 + (yy - iy) ** 2 < 26 ** 2
    mpj = os.path.join(sp, "mouth_parts.json")
    if os.path.exists(mpj):
        with open(mpj, encoding="utf-8") as f:
            mj = json.load(f)
        mx = mj["anchor_pos"][0] - head_pos[0]
        my = mj["anchor_pos"][1] - head_pos[1]
        feat |= ((abs(xx - mx) < mj["size"][0] / 2 + 8)
                 & (abs(yy - my) < mj["size"][1] / 2 + 8))
    # 脸 = 皮肤往外涨 3px（把下颌那条线稿包进来）后填洞，再并上五官保护区。
    # 这里**不能**用闭运算：闭运算会把"发丝缝里露出来的脸颊"连成一整片，于是压在
    # 脸上的那几缕发丝全被判成脸，侧发一摆脸颊上就是一片锯齿鬼影（踩过）。
    seed = (warm & solid & (np.arange(H)[:, None] > y_root)
            & (abs(np.arange(W)[None, :] - W // 2) < 20))
    face = fill_holes(largest(dilate(warm & solid, 3), seed) | feat)
    # 刘海/呆毛已经是独立零件，别再切进来
    taken = np.zeros((H, W), bool)
    for pid in ("hair_front", "hair_ahoge"):
        if pid in have:
            im = np.array(Image.open(os.path.join(sp, pid + ".png")).convert("RGBA"))
            px, py = pos_of[pid][0] - head_pos[0], pos_of[pid][1] - head_pos[1]
            sub = taken[py:py + im.shape[0], px:px + im.shape[1]]
            sub |= im[:sub.shape[0], :sub.shape[1], 3] > 8
    rows = np.arange(H)[:, None] * np.ones((1, W), int)
    # 下边界：发梢最低到脖子切线稍下一点，再往下就是夹克的白边/青边了（也偏冷，
    # 只靠颜色分不开）。neck 来自 make_body_parts 量出的切线。
    y_floor = int(bp.get("cut_lines", {}).get("neck", H - 40)) + 2 - head_pos[1]
    # 注意用 hal>16 而不是 solid(>100)：剪影最外面那圈碎发丝是半透明的，
    # 只切 solid 的话它们会留在脸上，侧发一摆就是一圈锯齿鬼影（踩过）。
    hair = (hal > 16) & ~face & ~teal & ~taken & hairish & (rows < y_floor)
    hair = erode(dilate(hair, 1), 1)                 # 去掉零碎噪点

    cx = (sx0 + sx1) / 2 / SCALE
    cols = np.ones((H, 1), int) * np.arange(W)[None, :]
    band = hair & (rows >= y_root) & (rows < y_root + 6)
    lock_l = largest(hair & (rows >= y_root) & (cols < cx), band & (cols < cx))
    lock_r = largest(hair & (rows >= y_root) & (cols >= cx), band & (cols >= cx))
    # 后发只要"和头顶那团连着"的部分：下摆里混着夹克的白边/青边（它们也偏冷，
    # 颜色分不开），不做连通过滤的话后发零件里会飘着几块白菱形（踩过）。
    back = largest(hair & ~lock_l & ~lock_r, hair & (rows < max(0, y_root - 40)))
    if lock_l.sum() < 500 or lock_r.sum() < 500:
        print(f"没找到侧发（左 {int(lock_l.sum())} 右 {int(lock_r.sum())} 像素），跳过")
        return 1

    # ---------------------------------------------------------- 3) 侧发：补画 + 切件
    # 往脸这一侧外扩 2px：原画里发丝压着皮肤的那圈抗锯齿像素要一起交给侧发零件，
    # 否则侧发一摆，脸颊上会留下一圈发丝幽灵（刘海那件踩过同样的坑）。
    # 补画区与零件区用的是同一个掩码，所以静止时严丝合缝。
    # 先把每缕实心化：发丝之间漏出来的那点脸颊也一起算进侧发的地盘，
    # 否则补画补出来的是一片"筛子"，侧发一摆就是满脸麻点。
    lock_l = fill_holes(erode(dilate(lock_l, 3), 3)) & ~teal & (hal > 16)
    lock_r = fill_holes(erode(dilate(lock_r, 3), 3)) & ~teal & (hal > 16)
    grow = dilate(lock_l | lock_r, 4) & (hal > 16) & ~taken & ~feat
    lock_l = (grow & dilate(lock_l, 5) & ~lock_r) | lock_l
    lock_r = (grow & ~lock_l) | lock_r
    occl = (lock_l | lock_r)
    band_sk = dilate(occl, 6) & ~occl & warm & solid & ~gen_bg
    if band_sk.sum() < 150:
        band_sk = solid & warm & ~gen_bg
    gain, off = np.ones(3), np.zeros(3)
    for c in range(3):
        a_v = hrgb[..., c][band_sk].astype(float)
        b_v = aligned[..., c][band_sk].astype(float)
        if len(a_v) > 50 and b_v.std() > 1.0:
            g = float(np.clip(a_v.std() / b_v.std(), 0.8, 1.25))
            gain[c], off[c] = g, a_v.mean() - g * b_v.mean()
        elif len(a_v) > 10 and b_v.mean() > 1:
            gain[c] = a_v.mean() / b_v.mean()
    fixed = np.clip(aligned * gain + off, 0, 255).round().astype(np.uint8)

    newhead = np.array(head).copy()
    for c in range(3):
        newhead[..., c] = np.where(occl & ~gen_bg, fixed[..., c], newhead[..., c])
    newhead[..., 3] = np.where(occl, np.where(gen_bg, 0, 255),
                               newhead[..., 3]).astype(np.uint8)
    # 重绘比原画窄的地方会留透明缝 → 往外涂 GROW_PX 像素
    newhead = grow_colors(newhead, occl, GROW_PX)
    # 补画区的 alpha 夹回原图：重绘的脸/脖子比原画宽，不夹的话会从侧发边上露出来
    # （合成比原图**多**出几百像素，静止画面就能看见一条补画的边）。
    newhead[..., 3] = np.where(occl, np.minimum(newhead[..., 3], hal),
                               newhead[..., 3]).astype(np.uint8)

    # 补画区里重绘图画的是**头发**的那部分（耳朵上方那一截），归后发，不归脸；
    # 否则侧发一摆，那截头发会钉在脸上不动。
    nr = newhead[..., 0].astype(int); ng = newhead[..., 1].astype(int)
    nbl = newhead[..., 2].astype(int)
    nb = (nbl >= nr - 6) & ~((ng - nr > 55) & (nbl - ng < 20))   # 冷色但不是青绿衣领
    # 加完之后**再过一次连通**：脖子阴影在重绘里也是冷色，不过滤的话会有两小块
    # 杂色混进后发，再被塗り足し吹成两个菱形色块（踩过，见 logs/asset_qa）。
    back = largest(back | (occl & ~gen_bg & nb & (newhead[..., 3] > 0) & (rows < y_floor)),
                   back & (rows < y_root))

    back = (dilate(back, 2) & (hal > 16) & ~taken & ~occl) | back
    # 后发：从脸上挖掉（它改画在脸下面），再往脸底下铺一圈塗り足し
    back_rgba = np.zeros((H, W, 4), np.uint8)
    back_rgba[..., :3] = newhead[..., :3]
    back_rgba[..., 3] = np.where(back, newhead[..., 3], 0)
    newhead[..., 3] = np.where(back, 0, newhead[..., 3])
    # 塗り足し只铺在"挖完之后脸还盖着"的地方：铺到脸外面去就会在静止画面上
    # 露出一圈多出来的头发（合成比原图多像素）。
    region = dilate(back, BLEED_IN) & (newhead[..., 3] > 200)
    back_rgba = grow_colors(back_rgba, region, BLEED_IN)

    Image.fromarray(newhead).save(os.path.join(sp, "seg_head.png"))

    # ---------------------------------------------------------- 4) 写零件图
    bimg = np.array(body).astype(int)
    BH, BW = bimg.shape[:2]
    out_parts = []

    def put(pid, mask_head, extra_rows=0):
        """把 head 局部掩码换算到 body 坐标，取原画像素写成零件。"""
        m = np.zeros((BH, BW), bool)
        ys, xs = np.nonzero(mask_head)
        m[ys + head_pos[1], xs + head_pos[0]] = True
        if extra_rows:                                   # 根部重复像素（切口藏在里面）
            top = int(ys.min())
            add = np.zeros((H, W), bool)
            add[max(0, top - extra_rows):top] = hair[max(0, top - extra_rows):top]
            add &= dilate(mask_head, extra_rows + 2)
            ys2, xs2 = np.nonzero(add)
            m[ys2 + head_pos[1], xs2 + head_pos[0]] = True
        # 软边只做在**内缘**（切开实心内容的那一侧）。外缘是原画自己的剪影边，
        # body_full 的 alpha 本来就是抗锯齿好的，再乘一次软掩码会把它吃掉
        # —— 合成就会比原图少像素（check_assets 的"无损切分"直接红）。
        keep = m & ~dilate(~m & (bimg[..., 3] > 100), 3)
        softm = np.where(keep, 1.0, soft_mask(m))
        px = np.zeros((BH, BW, 4), np.uint8)
        px[..., :3] = bimg[..., :3]
        px[..., 3] = np.clip(bimg[..., 3] * softm, 0, 255).round().astype(np.uint8)
        ys, xs = np.nonzero(px[..., 3] > 0)
        y0, y1, x0, x1 = int(ys.min()), int(ys.max()) + 1, int(xs.min()), int(xs.max()) + 1
        Image.fromarray(px[y0:y1, x0:x1]).save(os.path.join(sp, pid + ".png"))
        out_parts.append({"id": pid, "file": f"sprites/{pid}.png",
                          "pos": [x0, y0], "size": [x1 - x0, y1 - y0],
                          "group": "head", "layer": LAYER[pid]})
        return m

    body_l = put("hair_side_l", lock_l, BLEED_ROOT)
    body_r = put("hair_side_r", lock_r, BLEED_ROOT)

    bk = np.zeros((BH, BW, 4), np.uint8)
    ys, xs = np.nonzero(back_rgba[..., 3] > 0)
    bk[ys + head_pos[1], xs + head_pos[0]] = back_rgba[ys, xs]
    ys, xs = np.nonzero(bk[..., 3] > 0)
    y0, y1, x0, x1 = int(ys.min()), int(ys.max()) + 1, int(xs.min()), int(xs.max()) + 1
    Image.fromarray(bk[y0:y1, x0:x1]).save(os.path.join(sp, "hair_back.png"))
    out_parts.append({"id": "hair_back", "file": "sprites/hair_back.png",
                      "pos": [x0, y0], "size": [x1 - x0, y1 - y0],
                      "group": "head", "layer": LAYER["hair_back"]})

    # ---------------------------------------------------------- 5) 躯干重叠带里的那半份发梢
    # 发梢垂到了 y>neck 的“头/躯干重叠带”里：那一段 seg_torso 也存了一份半透明副本，
    # 不处理的话侧发一摆，躯干那份副本就是一条钉在原地的幽灵发梢。
    # 但**不能直接挖透明**：躯干被挖出窟窿，check_assets 的“袖下躯干无新窟窿”会红
    # （实测 72 > 上限 60）。正确做法是只换颜色不动 alpha：把四周的衣领/脖子颜色
    # 涂进来（发梢背后本来就是领子），躯干依旧是完整一张图。
    lock_body = (body_l | body_r)
    ta = np.array(torso)
    sub = lock_body[torso_pos[1]:torso_pos[1] + ta.shape[0],
                    torso_pos[0]:torso_pos[0] + ta.shape[1]]
    cut = int((sub & (ta[..., 3] > 0)).sum())
    keep_a = ta[..., 3].copy()
    ta[..., 3] = np.where(sub, 0, ta[..., 3])
    ta = grow_colors(ta, sub, 12)
    ta[..., 3] = keep_a
    Image.fromarray(ta).save(os.path.join(sp, "seg_torso.png"))

    # ---------------------------------------------------------- 6) 登记 + 报告
    bp["parts"] = [p for p in bp["parts"] if p["id"] not in LAYER] + out_parts
    for note in ("侧发已拆件（左右各一缕），脸颊/下颌/脖子由 AI 重绘补全（make_sidehair_parts.py）",
                 "后发已拆件，画在脸下面，往脸底下铺了塗り足し（make_sidehair_parts.py）"):
        if note not in bp.setdefault("patches", []):
            bp["patches"].append(note)
    with open(bp_path, "w", encoding="utf-8") as f:
        json.dump(bp, f, ensure_ascii=False, indent=2)

    rep = {
        "redraw": args.redraw,
        "align": {"scale": round(float(k), 4), "dx": round(float(dx), 1),
                  "dy": round(float(dy), 1)},
        "root_y": int(y_root), "bleed_root": BLEED_ROOT, "bleed_in": BLEED_IN,
        "grow_px": GROW_PX,
        "px": {"side_l": int(lock_l.sum()), "side_r": int(lock_r.sum()),
               "back": int(back.sum()), "torso_band_cut": cut},
        "skin_gain": [round(float(v), 4) for v in gain],
        "skin_offset": [round(float(v), 2) for v in off],
        "parts": out_parts,
    }
    with open(os.path.join(sp, "sidehair_report.json"), "w", encoding="utf-8") as f:
        json.dump(rep, f, ensure_ascii=False, indent=2)
    print(f"对齐 scale={k:.4f} 平移=({dx:.1f},{dy:.1f}) 根部切线 y={y_root}")
    print(f"侧发 左 {int(lock_l.sum())} / 右 {int(lock_r.sum())} 像素，"
          f"后发 {int(back.sum())} 像素，躯干重叠带挖掉 {cut} 像素")
    for p in out_parts:
        print(f"  {p['id']:<12} {p['size'][0]}x{p['size'][1]} @ {p['pos']} 层 {p['layer']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
