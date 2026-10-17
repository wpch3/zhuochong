#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""make_arm_parts.py - 把两条手臂从躯干上拆成「上臂 + 前臂」四件，并补上袖子底下的夹克。

为什么要重切（G4c）：
  make_body_parts.py 是按**直线**切的：手臂 = x<127 / x>316 的一整块矩形板，
  里头连夹克的侧片一起切走了。那块板一旋转，夹克就跟着歪 → 整块旋转超过 8° 必裂。
  Live2D 的切法是沿**袖子的缝**切：袖子（青色）是一件，夹克身（白色）是另一件。

切法：
  ① 袖子按颜色 flood（种子放在袖子中段），天然停在白夹克的边上；
  ② 袖口以下用「蛇形」逐行跟随（取包含上一行中心的那段连通前景），把袖口 + 手一起带上；
  ③ 在肘部（anchors 的 elbow_*）切成上臂 / 前臂 / 手三件（手腕线是逐行实测的
     袖口下沿，不是 anchors 里按比例算的那条），留 24px 重叠带并做渐隐，
     这样肘部旋转不会出现硬切线。

袖子挪走后躯干会空一块（夹克侧片、下摆条、裙子边），原画里**没有**这些像素 ——
按 D19 必须 AI 重绘：design/redraw/torso_noarms.png（无手臂躯干，已做过各向异性配准 +
逐通道颜色配准），只回贴「被袖子遮住」的那些像素。

输入：sprites/body_full.png、design/anchors.json、design/redraw/torso_noarms.png
输出：sprites/arm_{l,r}_{upper,fore}.png、sprites/seg_torso.png（补全侧片）、sprites/arm_parts.json

用法：
  ~/.imgenv/bin/python tools/make_arm_parts.py --character xiaoxun --form teen
"""
from __future__ import annotations
import argparse, json, os, sys
from collections import deque

import numpy as np
from PIL import Image

TEAL = np.array([108, 180, 192])      # 袖子的青
TEAL_TOL = 150                        # |ΔR|+|ΔG|+|ΔB| 阈值
ELBOW_OVERLAP = 24                    # 肘部重叠带（上下各一半）
WRIST_STUB = 10                       # 手腕：手往袖口里续多高的皮肤（藏在袖子里）
WRIST_STUB_IN = 4                     # 续出来的皮肤要比袖口窄这么多（转手时不许戳出袖子）
SKIN_RUN = 3                          # 连续几行"这一行基本都是肤色"才算袖口到头了
FEATHER = 2                         # 切口羽化半径（像素）
BLEED = 5                           # 躯干切口往外塗り足し的圈数
LINE_RGB = (90, 90, 110)            # 线稿色 #5A5A6E：补出来的衣片也要有轮廓线
LINE_W = 2                          # 轮廓线宽（像素）
# ---- 袖根塗り足し（G108：上臂看着太细）----
ROOT_TARGET_Q = 0.80                # 目标袖宽 = 上臂逐行宽度的 80 分位
ROOT_EXT_MAX = 46                   # 单行最多往身体里补多少像素
ROOT_TOP_RAMP = 40                  # 顶端这么多行内把补绘量从 0 渐渐加满（不留水平直边）
ROOT_SHADE = 0.90                   # 补到最里侧时的明度系数（内侧背光，略压暗）
ROOT_CLEAR_SEAM = 0                 # 0 = **不要**抹上臂贴图里那条袖缝线（试过，静止帧会坏）
ROOT_LAYER = {"l": 95, "r": 96}     # **画在躯干(100)底下**：静止时被夹克完全盖住

SEAM_KEEP = 2       # 袖片内缘：最内侧青色之外再留几像素（袖缝线本身要留）
SEAM_TRIM_MAX = 4   # 单行最多裁几个**实心**像素；超了这一行就不裁（误伤保险）
SEAM_SOLID = 0.35   # 判"实心"的 alpha 阈值：羽化尾巴不算进上限，但会跟着一起裁
SEAM_CUFF_SKIP = 36 # 前臂：腕上这么多行不裁（袖口那三道白条就在这儿，没有内缘青色可依）


def skin_of(rgb, m):
    """肤色（#FCE4D8 一类）：亮、偏红。青袖 #6CB4C0 的 G/B 高于 R，白夹克 R≈G≈B。"""
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    return m & (r > 205) & (r > b + 12) & (r >= g) & (g > 140)


def wrist_row(rgb, m, y_from, y_to):
    """袖口到头的那一行 = 从肘往下第一次连续 SKIN_RUN 行\"这一行的不透明像素
       有六成以上是肤色\"。手是从袖口里伸出来的，这一行就是手腕。"""
    sk = skin_of(rgb, m)
    run = 0
    for y in range(y_from, y_to):
        tot = int(m[y].sum())
        if tot >= 6 and int(sk[y].sum()) >= tot * 0.6:
            run += 1
            if run >= SKIN_RUN:
                return y - SKIN_RUN + 1
        else:
            run = 0
    return -1


def flood(mask, seed):
    """四邻域 flood fill（沙箱没有 scipy，自己写）。"""
    h, w = mask.shape
    out = np.zeros((h, w), bool)
    q = deque([seed])
    out[seed] = True
    while q:
        y, x = q.popleft()
        for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            ny, nx = y + dy, x + dx
            if 0 <= ny < h and 0 <= nx < w and mask[ny, nx] and not out[ny, nx]:
                out[ny, nx] = True
                q.append((ny, nx))
    return out


def sleeve_mask(rgb, alpha, x0, x1):
    """在 [x0,x1) 这一侧找袖子：先按青色取候选，再从中段 flood。"""
    cand = (np.abs(rgb - TEAL).sum(axis=2) < TEAL_TOL) & alpha
    sub = cand[400:520, x0:x1]
    ys, xs = np.nonzero(sub)
    if len(ys) == 0:
        raise SystemExit(f"[make_arm_parts] x[{x0},{x1}) 里找不到袖子（青色）像素")
    seed = (400 + int(np.median(ys)), x0 + int(np.median(xs)))
    return flood(cand, seed)


def row_runs(row):
    """一行里的所有连通段 [(a, b), ...]（闭区间）。"""
    idx = np.nonzero(row)[0]
    if idx.size == 0:
        return []
    cuts = np.nonzero(np.diff(idx) > 1)[0]
    runs, start = [], 0
    for c in cuts:
        runs.append((int(idx[start]), int(idx[c])))
        start = c + 1
    runs.append((int(idx[start]), int(idx[-1])))
    return runs


def grow_down(mask, alpha, max_run=150, slack=6):
    """从袖子最下面一行往下逐行跟随，把袖口和手一起带上。

    一行里可能有**好几段**（五根手指张开时就是五段），所以不能只跟"包含上一行
    中心的那一段"——那样手指缝两侧会被漏掉，叠回去就少像素（实测漏 755px）。
    这里改成：上一行占住的区间左右各放宽 slack 像素，这一行凡是和它相交的段**全要**。
    再用 max_run 封顶，防止袖口和下摆连在一起时一路跑进躯干。
    """
    h, w = alpha.shape
    m = mask.copy()
    rows = np.nonzero(mask.any(axis=1))[0]
    y = int(rows.max())
    cols = np.nonzero(mask[y])[0]
    lo, hi = int(cols.min()), int(cols.max())
    y += 1
    miss = 0
    while y < h and miss < 6:
        runs = [r for r in row_runs(alpha[y])
                if r[1] >= lo - slack and r[0] <= hi + slack]
        if not runs:
            miss += 1
            y += 1
            continue
        nlo, nhi = min(r[0] for r in runs), max(r[1] for r in runs)
        if nhi - nlo > max_run:          # 和躯干连上了：裁回上一行的范围，别一路吃进去
            nlo, nhi = max(nlo, lo - slack), min(nhi, hi + slack)
        for a, b in runs:
            a, b = max(a, nlo), min(b, nhi)
            if a <= b:
                m[y, a:b + 1] = True
        lo, hi = nlo, nhi
        miss = 0
        y += 1
    return m


def fill_outward(m, alpha, side, limit=40):
    """每一行从袖子的最外侧像素补到人物轮廓外缘。

    袖口的三道白条不是青色，按颜色 flood 吃不到；它们又贴着轮廓（不是内部孔洞），
    所以闭运算也补不回来 —— 实测左右各漏掉一块 ~100px 的楔形。
    手臂在这些行里本来就是画面最外侧的东西，直接按行补到轮廓即可：
    左臂往左补、右臂往右补，并且只补前景像素（手指缝里的背景不要）。
    """
    out = m.copy()
    for y in np.nonzero(m.any(axis=1))[0]:
        fg = np.nonzero(alpha[y])[0]
        xs = np.nonzero(m[y])[0]
        if fg.size == 0 or xs.size == 0:
            continue
        if side == "l":
            a, b = int(fg.min()), int(xs.min())
        else:
            a, b = int(xs.max()) + 1, int(fg.max()) + 1
        if 0 < b - a <= limit:
            out[y, a:b] = alpha[y, a:b]
    return out


def shift(m, dy, dx):
    """不绕回的平移（np.roll 会把左边卷到右边，手臂贴着画布边时会炸）。"""
    out = np.zeros_like(m)
    h, w = m.shape
    ys0, ys1 = max(0, dy), min(h, h + dy)
    xs0, xs1 = max(0, dx), min(w, w + dx)
    out[ys0:ys1, xs0:xs1] = m[ys0 - dy:ys1 - dy, xs0 - dx:xs1 - dx]
    return out


def dilate(mask, n=1):
    m = mask.copy()
    for _ in range(n):
        m = (m | shift(m, 1, 0) | shift(m, -1, 0) | shift(m, 0, 1) | shift(m, 0, -1))
    return m


def erode(mask, n=1):
    return ~dilate(~mask, n)


def soft(mask, feather=FEATHER):
    """二值掩码 → 软边 alpha（和其它拆件脚本同一套配方）。"""
    from PIL import ImageFilter
    im = Image.fromarray((mask.astype(np.float32) * 255).astype(np.uint8))
    for _ in range(feather):
        im = im.filter(ImageFilter.BoxBlur(1))
    a = np.asarray(im).astype(np.float32) / 255.0
    a = np.clip(a * 1.35 - 0.18, 0.0, 1.0)
    a[mask & (a > 0.75)] = 1.0
    return a


def bleed(rgb, have, into, rounds=5):
    """塗り足し：把已有像素的颜色往 into 区域里长几圈，
    免得零件的软边底下露出透明（Live2D 素材的标准做法）。"""
    out_rgb = rgb.copy()
    cur = have.copy()
    grown = np.zeros_like(have)
    dist = np.zeros(have.shape, np.float32)
    for r in range(1, rounds + 1):
        ring = dilate(cur, 1) & ~cur & into
        if not ring.any():
            break
        acc = np.zeros(rgb.shape, np.float32)
        cnt = np.zeros(have.shape, np.float32)
        for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nb = shift(cur, dy, dx)
            nbrgb = np.dstack([shift(out_rgb[..., c], dy, dx) for c in range(3)])
            use = ring & nb
            acc[use] += nbrgb[use]
            cnt[use] += 1
        ok = ring & (cnt > 0)
        out_rgb[ok] = (acc[ok] / cnt[ok][:, None]).astype(rgb.dtype)
        dist[ok] = r
        cur = cur | ok
        grown |= ok
    return out_rgb, grown, dist


def root_fill(body, up, side, hidden):
    """袖根塗り足し（G108）：把上臂的袖子往身体里多画一截，**画在躯干底下**。

    为什么要补：袖子是沿袖缝切的，上臂露出来的只有夹克身**没盖住**的那一条，
    逐行宽度从肩头的 23px 长到肘部的 68px。手臂一抬，这条楔形整个转出来，
    肩那头细得像根棍子（用户原话"上臂看起来很细十分不平衡"）。
    真实的袖子在夹克身底下还有一截，那一截必须补出来。

    为什么安全：补出来的像素全部落在 `hidden`（躯干不透明区 ∪ 袖子自己）里，
    而且这件的层号 95/96 **低于躯干 100**，静止时一个像素都看不见
    —— 不是靠"看不出来"，是靠遮挡关系保证，静止合成差不会变。

    怎么补：逐行把宽度补到 80 分位宽（≈肘部宽度），顶端 ROOT_TOP_RAMP 行做
    smoothstep 渐入，免得转出来是一条水平直边。颜色取袖缝内侧 6px 的中位色
    （避开 2px 线稿），往里渐暗到 ROOT_SHADE，最后在新的内缘描一道线稿。
    """
    H, W = up.shape
    rows = np.nonzero(up.any(axis=1))[0]
    if rows.size == 0:
        return np.zeros((H, W), bool), body[..., :3].copy(), 0.0
    y0 = int(rows.min())
    edges, widths = {}, []
    for y in rows:
        rs = row_runs(up[y])
        if not rs:
            continue
        # **取整行跨度，不是最长那一段**：袖子一行常常被口袋线/下摆条切成两段
        # （实测 y=480 是 (320,331)+(333,377)）。按最长段取起点，补绘就会压到
        # 另一段真袖子上，静止时直接在袖子中间糊出一条平色带（第一版就这么错的）。
        a, b = min(r[0] for r in rs), max(r[1] for r in rs)
        edges[int(y)] = (a, b)
        widths.append(b - a + 1)
    target = float(np.percentile(widths, ROOT_TARGET_Q * 100.0))
    ext = np.zeros((H, W), bool)
    rgb = body[..., :3].copy()
    for y, (a, b) in edges.items():
        d = min(ROOT_EXT_MAX, int(round(target - (b - a + 1))))
        if d <= 0:
            continue
        t = min(1.0, (y - y0) / float(ROOT_TOP_RAMP))
        d = int(round(d * (t * t * (3.0 - 2.0 * t))))      # smoothstep
        if d <= 0:
            continue
        if side == "r":                                     # 右臂往左（身体里）补
            src = body[y, a + 1:a + 7, :3]
            x0, x1 = max(0, a - d), a
            ramp = np.linspace(1.0, ROOT_SHADE, x1 - x0)[::-1]
        else:                                               # 左臂往右补
            src = body[y, max(0, b - 6):b, :3]
            x0, x1 = b + 1, min(W, b + 1 + d)
            ramp = np.linspace(1.0, ROOT_SHADE, x1 - x0)
        if src.size == 0 or x1 <= x0:
            continue
        col = np.median(src.astype(np.float32), axis=0)
        rgb[y, x0:x1] = np.clip(col[None, :] * ramp[:, None], 0, 255).astype(rgb.dtype)
        ext[y, x0:x1] = True
    ext &= erode(hidden, 2)              # 软边也要藏住：先把遮挡区往里收 2px
    # 新内缘描线稿：转出来之后这条就是袖子的剪影边，没有线会像一块色块
    full = ext | up
    rim = (full & ~erode(full, LINE_W)) & ext
    rim_s = (full & ~erode(full, LINE_W + 1)) & ext
    ln = np.array(LINE_RGB, np.float32)
    for mask, k in ((rim_s, 0.45), (rim, 0.9)):
        if mask.any():
            cur = rgb[mask].astype(np.float32)
            rgb[mask] = (cur * (1 - k) + ln * k).astype(rgb.dtype)
    return ext, rgb, target


def seam_trim(a, rgb, side, y_max=None, keep=SEAM_KEEP, cap=SEAM_TRIM_MAX):
    """袖片内缘别把夹克白一起切走（G112）。

    症状：手臂一转开，白夹克和青袖之间多出一道**白边**，像衣袖和身体之间裂了条缝
    （用户第三次验收截图3）。先定位是哪一层画的 —— 把 arm_r_upper 的 opacity 调成 0，
    那几个白像素立刻变青 ⇒ **白是上臂贴图自己带的**，不是背景、不是躯干。
    再查原画：body_full 的袖内缘是「白夹克 → 1~2px 暗缝线 → 青」，**没有白色滚边**
    （y=420: x315=(248,246,244) / x316=(80,98,103) / x318=(108,186,191)）。
    所以这 2px 白是 soft() 把掩码往外羽化 2px 时顺手带上的夹克像素：
    静止时它正压在夹克上，一个像素都看不出来；手臂一转就跟着甩出来。

    做法：逐行找这一行**最内侧的青色**，往内再留 keep 像素（袖缝线要留着，
    它在原画里就有，转开后读作袖子上的折痕），再往内的一律裁掉。
    判青用色相（g-r>20 且 b-r>10）而不是到 TEAL 的曼哈顿距离 —— 灰过渡像素
    (191,178,181) 到 TEAL 只有 96，用距离会被当成青色，裁不干净（试过）。
    两条保险（都踩过坑）：
      · cap 只数**实心**像素（alpha ≥ SEAM_SOLID）。拿"所有 alpha>0 的像素"去数，
        羽化尾巴能长到 6~8px，几乎每一行都超限 → 整条袖子只裁掉 9px，等于没裁。
      · y_max：前臂的袖口那三道白条没有"内缘青色"可依，一裁就把袖口咬掉
        （实测静止合成少 8px，闸直接红）。所以腕上 SEAM_CUFF_SKIP 行整段不碰。
    """
    # ⚠ 必须先转 int：body[...,:3] 是 uint8，g - r 会**无符号回绕**
    # （夹克白 g=235 r=238 → 235-238 = 253 > 20 → 白被判成青色，整条裁剪静默失效，
    #   闸还是全绿 —— 747 项里没有一项管得着"裁了没有"）。
    rgb = rgb.astype(np.int16)
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    teal = (g - r > 20) & (b - r > 10) & (g > 120)
    out = a.copy()
    xs_idx = np.arange(a.shape[1])
    n = 0
    for y in np.nonzero((a > 0.016).any(axis=1))[0]:
        if y_max is not None and y > y_max:
            continue
        row = a[y] > 0.016
        solid = a[y] >= SEAM_SOLID
        if solid.sum() < 4:
            continue
        t = np.nonzero(teal[y] & solid)[0]
        if t.size == 0:
            continue
        if side == "l":                       # 画面左臂：外缘在左，内缘在右
            cl = row & (xs_idx > min(a.shape[1] - 1, int(t.max()) + keep))
        else:                                 # 画面右臂：内缘在左
            cl = row & (xs_idx < max(0, int(t.min()) - keep))
        if int((cl & solid).sum()) > cap or not cl.any():
            continue
        out[y][cl] = 0.0
        n += int(cl.sum())
    return out, n


def cut(rgb, alpha_f, box):
    """按 box=(x0,y0,x1,y1) 裁出 RGBA 图。"""
    x0, y0, x1, y1 = box
    out = np.zeros((y1 - y0, x1 - x0, 4), np.uint8)
    out[..., :3] = rgb[y0:y1, x0:x1]
    out[..., 3] = (alpha_f[y0:y1, x0:x1] * 255).round().astype(np.uint8)
    return Image.fromarray(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--character", required=True)
    ap.add_argument("--form", required=True)
    ap.add_argument("--root", default=".")
    args = ap.parse_args()
    base = os.path.join(args.root, "characters", args.character, "forms", args.form)
    sp = os.path.join(base, "sprites")
    body = np.array(Image.open(os.path.join(sp, "body_full.png")).convert("RGBA"))
    H, W = body.shape[:2]
    rgb = body[..., :3].astype(int)
    alpha = body[..., 3] > 16

    anchors = json.load(open(os.path.join(base, "design", "anchors.json"), encoding="utf-8"))
    pts = anchors["points"]
    redraw_path = os.path.join(args.root, "characters", args.character,
                               "design", "redraw", "torso_noarms.png")
    if not os.path.exists(redraw_path):
        raise SystemExit(f"[make_arm_parts] 缺少 AI 重绘底图：{redraw_path}（D19：被遮挡像素必须重绘）")
    fill = np.array(Image.open(redraw_path).convert("RGBA"))
    if fill.shape[:2] != (H, W):
        raise SystemExit("[make_arm_parts] 重绘底图尺寸必须与 body_full.png 一致")

    bp_path = os.path.join(sp, "body_parts.json")
    bp = json.load(open(bp_path, encoding="utf-8"))
    torso = next(p for p in bp["parts"] if p["id"] == "seg_torso")

    report = {"schema_version": "1.0", "source": "sprites/body_full.png",
              "redraw": "design/redraw/torso_noarms.png",
              "elbow_overlap_px": ELBOW_OVERLAP, "parts": [], "checks": {}}
    arms = {}
    yy_all = np.arange(H)[:, None]
    for side, (x0, x1) in (("l", (0, 150)), ("r", (300, W))):
        m = grow_down(sleeve_mask(rgb, alpha, x0, x1), alpha)
        # 袖口的白条不是青色，flood 吃不到；它贴着轮廓所以也不算"内部孔洞"。
        # 肘部以下做一次形态学闭运算（只在前景里补），把这种开口缺块补回来。
        # 只在肘以下做：上臂内侧紧挨着夹克，闭运算会把夹克的凹处也吃进来。
        close = erode(dilate(m, 6), 6) & (alpha > 0) & (yy_all > int(pts[f"elbow_{side}"][1]))
        arms[side] = fill_outward(m | close, alpha, side)

    # ---- 躯干：袖子那块换成 AI 重绘的夹克侧片 ----
    # G102/DC36：这里**整条袖子都要拿走，一个像素都不留给躯干**。
    #
    # 旧做法是"肩头 SHOULDER_CAP=46 行不挖"，理由写的是"原画里肩膀的圆头画在袖子上，
    # 整块拿走躯干的肩膀就成了一条平口"。**这个理由当时没验，而且是错的** ——
    # 留下来的那 46 行是**青色袖子**，它不跟着手臂转，手臂一抬就变成肩膀上
    # 悬空的一块青色三角（底边还是条直线），正是用户说的"部件和链接没做好"。
    # 实测把整条袖子拿走之后，露出来的是夹克自己的肩线：
    # 右肩外缘 y=330→332 / y=340→333 / y=360→328 / y=400→315，是一条**圆肩 + 袖窿**的曲线，
    # 不是平口（留证 logs/asset_qa/g102_torso_variants.png 三格对比）。
    # 静止时手臂画在躯干上面（层 140/141 > 100），这块照样被袖子盖住，合成不变。
    occ = dilate(arms["l"] | arms["r"], 2)
    # 重绘图是洋红底抠出来的，边缘有一圈被烤进 RGB 的紫：这种像素一律不要，
    # 贴进去会直接把 check_assets 的"键色残留"打挂（实测 299/631 是紫边）。
    fr = fill[..., 0].astype(np.int32); fg_ = fill[..., 1].astype(np.int32); fb = fill[..., 2].astype(np.int32)
    key_d = np.sqrt(((fill[..., :3].astype(np.float32) - np.array([255.0, 0.0, 255.0])) ** 2).sum(axis=2))
    # 被洋红污染的像素一律：红蓝都明显高于绿（品红 = R、B 高、G 低）。
    # 角色这块只有白夹克（R≈G≈B）和青袖（G≥R），所以这条判据不会误伤。
    purple = (np.minimum(fr, fb) - fg_) > 25
    have = (fill[..., 3] > 200) & (key_d > 150.0) & ~purple
    newbody = body.copy()
    paste = occ & have
    newbody[..., :3][paste] = fill[..., :3][paste]
    newbody[..., 3][paste] = 255
    lost = occ & ~have                      # 重绘也没有的（袖子外侧本来就是背景）
    newbody[..., 3][lost] = 0
    # 剩下的空洞边缘往外长 5 圈颜色，保证手臂转开时切口不是硬透明边
    keep = newbody[..., 3] > 16
    newbody[..., :3], grown, dist = bleed(newbody[..., :3], keep, lost, rounds=BLEED)
    # 边缘往外长的这几圈做渐隐，手臂转开时看着像衣片自然收边
    newbody[..., 3][grown] = np.clip(255.0 * (1.0 - (dist[grown] - 1.0) / BLEED), 0, 255).astype(np.uint8)

    # ---- 给补出来的衣片描线稿 ----
    # 原画每一条剪影边上都有一条深紫灰的线；补画区如果只有平涂白，
    # 手臂一抬，露出来的就是"纸片剪开"的感觉（用户反馈的"这个分割"）。
    # 所以把新产生的那段剪影边按原画的线稿色描回去。
    solid = newbody[..., 3] > 128
    near_cut = dilate(arms["l"] | arms["r"], 8)          # 只描新切出来的边
    rim = solid & ~erode(solid, LINE_W) & near_cut
    rim_soft = solid & ~erode(solid, LINE_W + 1) & near_cut
    ln = np.array(LINE_RGB, np.float32)
    for mask, k in ((rim_soft, 0.45), (rim, 0.9)):
        if mask.any():
            cur = newbody[..., :3][mask].astype(np.float32)
            newbody[..., :3][mask] = (cur * (1 - k) + ln * k).astype(np.uint8)
    report["checks"]["outline_px"] = int(rim.sum())
    # 裙摆下沿（G4c2）：躯干只到裙子为止，裙子下面那截大腿归腿件。
    # make_body_parts 已经按列量好了线，这里必须用**同一条**，
    # 否则这一步把大腿又原样贴回躯干，腿一抬接缝处就是一段钉死的大腿。
    tt = bp.get("thigh_top")
    if tt:
        tta = np.array(tt, int)
        tta[tta < 0] = H
        torso_trim = np.arange(H)[:, None] >= tta[None, :]
        newbody[..., 3][torso_trim] = 0
        report["checks"]["torso_thigh_trim_px"] = int(torso_trim.sum())
    tx, ty = torso["pos"]
    tw, th = torso["size"]
    Image.fromarray(newbody[ty:ty + th, tx:tx + tw]).save(os.path.join(sp, "seg_torso.png"))
    report["checks"]["torso_filled_px"] = int(paste.sum())
    report["checks"]["torso_cleared_px"] = int(lost.sum())

    # ---- 六件手臂（上臂 / 前臂 / 手 × 左右）+ 两件袖根 ----
    layer = {"l": 140, "r": 141}
    hand_layer = {"l": 138, "r": 139}       # 手画在**前臂底下**：袖口要压住手腕那截补画
    torso_solid = newbody[..., 3] > 200
    for side in ("l", "r"):
        m = arms[side]
        elbow_y = int(pts[f"elbow_{side}"][1])
        half = ELBOW_OVERLAP // 2
        # G108 袖根：先补，再和上臂一起切（补出来的那块是独立一件，层 95/96）
        up_mask = m & (np.arange(H)[:, None] <= elbow_y + half)
        hidden = torso_solid | dilate(m, 2)
        ext, ext_rgb, ext_target = root_fill(body, up_mask, side, hidden)
        if ext.any():
            ea = soft(ext)
            ea[erode(ext, 1)] = 1.0
            ys, xs = np.nonzero(ea > 0.004)
            ebox = (int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1)
            name = f"arm_{side}_root"
            cut(ext_rgb, ea, ebox).save(os.path.join(sp, name + ".png"))
            report["parts"].append({
                "id": name, "file": f"sprites/{name}.png",
                "pos": [ebox[0], ebox[1]],
                "size": [ebox[2] - ebox[0], ebox[3] - ebox[1]],
                "group": f"arm_{side}", "layer": ROOT_LAYER[side],
                "pivot": [float(pts[f"shoulder_{side}"][0]), float(pts[f"shoulder_{side}"][1])],
                "note": "袖根塗り足し（G108）：袖子在夹克身底下的那一截，层 95/96 画在躯干下面，"
                        "静止时完全被夹克盖住，手臂转开后补上肩关节、让上臂不再细得像棍子",
            })
            report["checks"].setdefault("root_ext_px", {})[side] = int(ext.sum())
            report["checks"].setdefault("root_target_w", {})[side] = round(ext_target, 1)
        orig_a = (body[..., 3] / 255.0).astype(np.float32)
        yy_col = np.arange(H)[:, None]
        # 手腕 = 袖口到头的那一行（逐行实测，不用 anchors 里按比例算的 708：
        # 那条线落在指尖上，照它切会把半只手留在前臂上）
        wrist_y = wrist_row(rgb, m, elbow_y + 20, H)
        if wrist_y < 0:
            raise SystemExit(f"[make_arm_parts] {side} 侧找不到袖口下沿（手腕），别往下切了")
        # 手往袖子里续一截皮肤（塗り足し）：手腕一转，袖口下面才不会露出背景。
        # 只在"袖子本来就不透明"的范围里续，静止时完全被袖口压住。
        hand_rgb = body[..., :3].copy()
        stub = np.zeros((H, W), bool)
        # 续出来的皮肤要**缩在袖口里面**：贴着袖口边补的话，手一转那一条就从
        # 袖子侧面戳出来，成了一小块飘在外面的肉色（实测 ±20° 时左右各一片）。
        inner = erode(m, WRIST_STUB_IN)
        top_rows = np.arange(wrist_y, min(H, wrist_y + 4))
        for x in range(W):
            if not m[top_rows, x].any():
                continue
            cols = hand_rgb[top_rows, x][m[top_rows, x]]
            c = np.median(cols, axis=0)
            for y in range(max(0, wrist_y - WRIST_STUB), wrist_y):
                if inner[y, x] and body[y, x, 3] >= 250:
                    hand_rgb[y, x] = c
                    stub[y, x] = True
        # 【试过并否掉】把上臂贴图里那条袖缝线抹掉（ROOT_CLEAR_SEAM=1）。
        # 动机是对的：补了袖根之后，这条线从剪影边变成了袖子中间的一条线。
        # 但实测**静止帧会坏**：那条线下面压着的是躯干被 bleed 渐隐过的切口，
        # 线一抹，内缘立刻露出一圈毛糙的浅色麻点（留证
        # logs/asset_qa/g108_seam_ab.png 第三格，对照第一格原画）。
        # 静止帧必须逐像素忠实于原画，这条优先级更高 —— 保留袖缝线，
        # 手臂转开后它读作袖子上的一道折痕（原画袖子本来就有折线）。
        up_rgb = body[..., :3].copy()
        if ext.any() and ROOT_CLEAR_SEAM:
            seam = ext & dilate(up_mask, LINE_W + 2) & ~up_mask
            up_rgb[seam] = ext_rgb[seam]
            report["checks"].setdefault("seam_cleared_px", {})[side] = int(seam.sum())
        for seg, keep in (("upper", m & (yy_col <= elbow_y + half)),
                          ("fore",  m & (yy_col >= elbow_y - half) & (yy_col <= wrist_y + 1)),
                          ("hand",  (m & (yy_col >= wrist_y)) | stub)):
            # 把原画自己的抗锯齿边一起抓进来，掩码内严格保留原 alpha，
            # 只在往外多扩的 2px 上做软边 —— 这样静止合成能逐像素还原
            grab = dilate(keep, 2) & (body[..., 3] > 0)
            if seg == "hand":
                grab = (grab | stub) & ~(yy_col < wrist_y - WRIST_STUB)
            sa = soft(dilate(grab, 2))
            sa[grab] = 1.0
            a = orig_a * sa
            if seg == "hand":
                a[stub] = 1.0
            # 肘部重叠带：**只让前臂淡入**，上臂在带内保持满值当底，
            # 这样 over 合成仍然是满的（两件都淡的话 0.5 over 0.5 = 0.75，会露底）
            if seg == "fore":
                yy = np.arange(H)[:, None].astype(np.float32)
                a = a * np.clip((yy - (elbow_y - half)) / ELBOW_OVERLAP, 0.0, 1.0)
            if seg in ("upper", "fore"):
                _ymax = (wrist_y - SEAM_CUFF_SKIP) if seg == "fore" else None
                a, _trim = seam_trim(a, body[..., :3], side, y_max=_ymax)
                report["checks"].setdefault("seam_trim_px", {}).setdefault(side, {})[seg] = _trim
            ys, xs = np.nonzero(a > 0.004)
            box = (int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1)
            src_rgb = hand_rgb if seg == "hand" else (up_rgb if seg == "upper" else body[..., :3])
            img = cut(src_rgb, a, box)
            name = f"arm_{side}_{seg}" if seg != "hand" else f"hand_{side}"
            img.save(os.path.join(sp, name + ".png"))
            if seg == "upper":
                joint, grp, lay = pts[f"shoulder_{side}"], f"arm_{side}", layer[side]
                note = "上臂：绕肩旋转"
            elif seg == "fore":
                joint, grp, lay = pts[f"elbow_{side}"], f"forearm_{side}", layer[side] + 2
                note = "前臂：绕肘旋转（父组＝上臂）"
            else:
                wx = np.nonzero(m[wrist_y])[0]
                joint = (float(wx.mean()) if wx.size else float(box[0] + box[2]) / 2.0,
                         float(wrist_y))
                grp, lay = f"hand_{side}", hand_layer[side]
                note = (f"手：绕腕旋转（父组＝前臂）；往袖子里续了 {WRIST_STUB}px 皮肤，"
                        f"画在前臂底下，静止时被袖口压住")
            report["parts"].append({
                "id": name, "file": f"sprites/{name}.png",
                "pos": [box[0], box[1]], "size": [box[2] - box[0], box[3] - box[1]],
                "group": grp, "layer": lay,
                "pivot": [float(joint[0]), float(joint[1])],
                "note": note,
            })
            if seg == "hand":
                report["checks"].setdefault("wrist_y", {})[side] = int(wrist_y)
                report["checks"].setdefault("hand_stub_px", {})[side] = int(stub.sum())

    # ---- 验收：四件叠回去 + 新躯干，和原画静止帧必须一样 ----
    comp = np.zeros((H, W, 4), np.float32)
    def over(dst, src_rgb, src_a):
        a = src_a[..., None]
        dst[..., :3] = src_rgb * a + dst[..., :3] * (1 - a)
        dst[..., 3:] = a + dst[..., 3:] * (1 - a)
        return dst
    # 层序必须和 rig 一致：腿 60/61 → **袖根 95/96** → 躯干 100 → 手 138/139 → 袖子 140+。
    # 袖根画在躯干底下，这里要是照旧"先躯干后所有拆件"，补出来的那块就会盖在夹克上面，
    # 静止合成差会假性爆掉（也就看不出真的回归了）。
    stack = []
    for lid in ("seg_leg_l", "seg_leg_r"):
        lp = next((q for q in bp["parts"] if q["id"] == lid), None)
        if not lp:
            continue
        stack.append((lp["layer"], os.path.join(sp, lid + ".png"), lp["pos"]))
    for p in report["parts"]:
        stack.append((p["layer"], os.path.join(sp, os.path.basename(p["file"])), p["pos"]))
    torso_layer = int(torso["layer"])
    for lay, path, pos in sorted(stack, key=lambda q: q[0]):
        if lay > torso_layer and not report["checks"].get("_torso_done"):
            comp = over(comp, newbody[..., :3].astype(np.float32),
                        (newbody[..., 3] / 255.0).astype(np.float32))
            report["checks"]["_torso_done"] = True
        im = np.array(Image.open(path).convert("RGBA"))
        x, y = pos
        h, w = im.shape[:2]
        layerbuf = np.zeros((H, W, 4), np.float32)
        layerbuf[y:y + h, x:x + w, :3] = im[..., :3]
        layerbuf[y:y + h, x:x + w, 3] = im[..., 3] / 255.0
        comp = over(comp, layerbuf[..., :3], layerbuf[..., 3])
    if not report["checks"].pop("_torso_done", False):
        comp = over(comp, newbody[..., :3].astype(np.float32),
                    (newbody[..., 3] / 255.0).astype(np.float32))
    else:
        report["checks"].pop("_torso_done", None)
    orig_a = (body[..., 3] / 255.0).astype(np.float32)
    # comp[...,:3] 累加出来已经是预乘 alpha 的值，原图要乘一次 alpha 才同口径
    diff = np.abs(comp[..., :3] - body[..., :3].astype(np.float32) * orig_a[..., None])
    bad = int((diff.max(axis=2) > 12).sum())
    report["checks"]["static_diff_px"] = bad
    if os.environ.get("ARM_DEBUG"):
        Image.fromarray(newbody).save("/tmp/g4c_newbody.png")
        dm = (diff.max(axis=2) > 12)
        Image.fromarray((dm * 255).astype(np.uint8)).save("/tmp/g4c_diffmap.png")
        print("  [debug] 差异分布：", {f"y{y0}-{y1}": int(dm[y0:y1].sum())
              for y0, y1 in ((0, 330), (330, 560), (560, 760), (760, 1292))})
    report["checks"]["arm_px"] = {s: int(arms[s].sum()) for s in arms}
    json.dump(report, open(os.path.join(sp, "arm_parts.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    print(f"手臂拆件完成：4 件；躯干补了 {report['checks']['torso_filled_px']} 像素、"
          f"清掉 {report['checks']['torso_cleared_px']} 像素；静止合成差 {bad} 像素")
    for p in report["parts"]:
        print(f"  {p['id']:14s} pos={p['pos']} size={p['size']} pivot={p['pivot']} layer={p['layer']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
