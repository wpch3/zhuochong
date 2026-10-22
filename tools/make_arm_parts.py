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
ROOT_CAP_EXT = 26                   # 肩帽向上多画这么多像素（见下方「第五刀」注释）
# ---- 袖根关节圆盘 ----
# ★★★ 2026-10-21 第二十八问：半径改成按**袖子宽度**算，不再按上臂长度算。
#   教程（さらえみ／Live2D モデラー, https://saraemi.com/vtuber/2022/02/09/live2d_arm/）：
#     「**関節パーツは正円**で、**上腕・前腕の幅と同じ**直径サイズです。
#       関節パーツと重ねて、上腕や前腕の線がズレていると失敗しやすいです。」
#   ⇒ 直径 = 手臂宽度，也就是 **R = 袖宽 / 2**。
#   原来写的 `R = arm_len * 0.52 ≈ 99px`，而袖宽只有 50~68px（半宽 25~34px）——
#   圆盘比袖子胖了**三倍**。圆盘绕自己的圆心转，剪影恒定不动，静止时靠
#   「躯干 ∪ 袖子」一起盖住；一抬手袖子让开，**原来被袖子盖住的那半块就
#   永久暴露**，于是腋下多出一牙青色半月（用户截图 1，放大图 /tmp/u1_arm4.png）。
#   半径收到半个袖宽以后，圆盘整个藏在「袖子 ∪ 躯干」的交集里，转到哪都不露。
ROOT_SMOOTH_K = 5
# 袖根塗り足し的上色/收边（2026-10-21 第三十三问）
ROOT_BLEED_ROUNDS = 56     # 颜色从袖子往里扩散的圈数（补绘最远 ~46px）
ROOT_SHADE_DIST = 24.0     # 往身体里走多远衰减到 ROOT_SHADE
ROOT_BLUR_K = 3            # ぼかし半径（note.com:「肩の付け根はぼかし処理」）
ROOT_FADE_END = 34.0       # 靠肘那一端的渐隐长度，避免一条垂直臂轴的硬切       # 袖根塗り足し的磨圆核（开运算），见 root_fill
ROOT_DISC_W = 0.58                  # R = 袖宽 × 这个系数（0.5 = 正好半宽，留一点のりしろ）
ROOT_DISC_K = 0.52                  # 上限：R 不许超过这么多倍上臂长（保险，正常用不到）
ROOT_LAYER = {"l": 95, "r": 96}     # **画在躯干(100)底下**：静止时被夹克完全盖住

# ---- 肩の関節パーツ（shoulder cap）----
# 第三十五问：用户指出「肩部和肘关节等连接处没做」。查过的资料口径一致
# （REFERENCE_NOTES 第五十四/五十五批）：
#   · 「関節パーツは**正円**で、直径＝腕幅」（saraemi / kw-nmnm）
#   · 「腕の付け根は**肩のパーツの下に**、多少描きすぎるくらい描く」（shiroikarasu）
#   · 「肩の付け根は**ぼかし**処理」（同上）
# 也就是说：肩这里**必须有一个属于身体、不跟着胳膊转的件**压在胳膊上面，
# 胳膊的切口藏在它下面。以前没有这个件，胳膊（层 140/141）直接画在夹克上，
# 一转就露出那条笔直的切口 + 一个纸片三角（用户附图 q35_1.png）。
CAP_SCALE = 1.45                    # 肩キャップ半径下限 = 1.45 × 関節R
CAP_MARGIN = 4.0                    # 实际半径按「袖子在枢轴上方那截（塔）」自测 + 这个余量
CAP_PAST = 0.30                     # 关节线往**远端**多盖 0.30R，免得切口正好压在边界上
CAP_FEATHER = 3.5                   # 边缘羽化（「肩の付け根はぼかし」）
CAP_LAYER = {"l": 142, "r": 143}    # 在上臂(140/141)之上、前臂(144/145)之下

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
        near = [r for r in row_runs(alpha[y])
                if r[1] >= lo - slack and r[0] <= hi + slack]
        # ★★★ 2026-10-21 第三十二问：slack 只许用来跟\"同一段横移\"，
        #   绝不能用来把**另一段**拉进来。
        #   左袖下沿 y=640 这一行有两段：手臂 (36,87) 和躯干 (96,339)。
        #   躯干那段的起点 96 正好 == hi+slack(90+6)，擦着边被收进来，
        #   span 变成 36..339 触发 max_run 夹紧 → 窗口被写回 [lo-6, hi+6]，
        #   **每行加宽 12px**；60 行之后窗口已有 300 宽，整条裙子和腿
        #   都被当成"手臂"切走（实测 hand_l 从 81×82 涨到 206×567，
        #   arm_l_fore 从 85×131 涨到 354×203，check_assets 连爆 3 条）。
        #   所以先只要**真重叠**的段；真·横移（没有任何真重叠）时才回退用 slack。
        runs = [r for r in near if r[1] >= lo and r[0] <= hi] or near
        if not runs:
            miss += 1
            y += 1
            continue
        nlo, nhi = min(r[0] for r in runs), max(r[1] for r in runs)
        if nhi - nlo > max_run:          # 和躯干连上了：沿用上一行的窗口，别借机变宽
            nlo, nhi = lo, hi
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


def shoulder_joint(up, sh_anchor, side):
    """真·肩关节中心（画布坐标）+ 关节圆半径。

    ★★★ 2026-10-21 第三十一问：这是挥手一直做不对的**根因**。
        `make_anchors.py` 里 shoulder_l/r 写的是
            prof[shoulder][0] / prof[shoulder][1]
        也就是**剪影在肩线那一行的最外侧边缘像素** —— 那是轮廓线上的点，
        根本不是关节。而隔壁 elbow_l/r 用的是 arm_x()（手臂横截面中心），
        所以肘一直是对的、肩一直是错的。
        实测：旧枢轴 (546,432) 画出来**半个圆在身体外面的空气里**，
        以袖宽为直径的关节圆只有 51% 落在「躯干∪袖子」里，
        剩下 1649px 全在背景上 —— 绕这么个点转袖子，
        转出来必然是一条直切边加一个楔子（用户第三十一问附图 4）。

    教程口径（五个独立来源一致）：
      · saraemi.com/vtuber/2022/02/09/live2d_arm/
        「関節パーツは**正円**で、上腕・前腕の**幅と同じ直径**サイズ」
      · kw-nmnm.hatenablog.com/entry/2018/11/06/203151
        「上腕の肘部分は**半円状**に」「肩の回転や手首の回転にも応用が効く」
      · note.com/shumi_log/n/n8172d73024aa
        「肘部分は"ほぼ"**半円状**に変形…**回転時に輪郭が自然につながる**ため」
      · coconala.com/blogs/2995247/413880
        「**関節を回転軸の中心にあわせて綺麗な円形に描く**…回転させてもズレず」
      · blog.adglobe.co.jp/entry/2024/07/26/100000
        「腕を上げた時の**円形の回り込み**をできるだけきれいに作る」

    所以关节中心必须是「那个正圆的圆心」。这里按解剖学口径反求：
      ① R = 上臂逐行宽度的 80 分位 ÷ 2（= 教程说的「腕の幅」的一半）；
      ② 关节行 = 肩峰（旧 anchor 的那一行）往下**一个臂半径**；
      ③ 关节 x = **让圆与袖子外轮廓相切** ⇒ x = 外缘 ∓ R。

    ★★★ 2026-10-21 第三十三问：③ 本来写的是「该行袖子横截面的**中点**」，
        这条是错的，而且错得隐蔽 —— 它就是这一轮「手臂断裂/割裂」的根因。

        这件衣服是**插肩袖**，肩头那一截袖子**大半压在白夹克身底下**。
        实测右臂逐行跨度：
            y=360 宽 18 ／ y=400 宽 41 ／ y=480 宽 58 ／ y=553（肘）宽 65
        肩头「看得见的袖子」只有 18px，而真实上臂有 65px 宽。
        拿**可见跨度的中点**当圆心，圆心就被推到身体外侧，
        以真实臂宽为直径的那个圆**有 14% 落在背景的空气里**
        （实测：左 86.6% / 右 86.0% 在 body 剪影内，其余是白底）。

        后果正是用户说的三件事：
          · 那 14% 没有任何件能盖 ⇒ 胳膊一抬，肩窝**破一个缺口**（断裂）；
          · 上臂顶端只能切直边（圆盘填不满）⇒ 一个平角戳出夹克（割裂）；
          · 枢轴偏外 ⇒ 同角度下远端扫过的弧更长（错位）。

        改成**与外轮廓相切**后，圆盘 **100.0% 落在 body 剪影内**（两侧都是）：
          · 圆盘可整个填实成袖色，藏在夹克底下（层 95/96 < 躯干 100），
            静止合成一个像素都不变；
          · 上臂顶端收成以该圆心为心的**半圆帽**，转任何角度剪影不变。
        即 saraemi「関節パーツは正円で、腕の幅と同じ直径」+
        coconala「関節を回転軸の中心にあわせて綺麗な円形に描く」的做法。

    返回 (jx, jy, R)：R 一并返回，免得调用方各算各的再对不上。
    """
    rows = np.nonzero(up.any(axis=1))[0]
    if rows.size == 0:
        return (float(sh_anchor[0]), float(sh_anchor[1]), 1.0)
    widths, span = [], {}
    for y in rows:
        xs = np.nonzero(up[y])[0]
        span[int(y)] = (int(xs.min()), int(xs.max()))
        widths.append(xs.max() - xs.min() + 1)
    R = float(np.percentile(widths, ROOT_TARGET_Q * 100.0)) / 2.0
    jy = int(round(float(sh_anchor[1]) + R))
    # 该行要是空的（极端体型），就往下找最近的有内容的一行
    if jy not in span:
        cand = [y for y in span if y >= jy]
        if not cand:
            return (float(sh_anchor[0]), float(sh_anchor[1]), R)
        jy = min(cand)
    lo, hi = span[jy]
    jx = (hi - R) if side == "r" else (lo + R)
    print("  肩关节 %s: 肩峰y=%d + 臂半径%.1f → 关节(%.0f,%d)"
          "  [与外轮廓 x=%d 相切；旧口径取可见中点 %.0f ⇒ 圆盘 14%% 戳到空气里]"
          % (side, float(sh_anchor[1]), R, jx, jy,
             hi if side == "r" else lo, (lo + hi) / 2.0))
    return (jx, float(jy), R)


def root_fill(body, up, side, hidden, pivot=None, arm_len=None,
              elbow=None, joint_r=None):
    """袖根塗り足し（G108）：把上臂的袖子往身体里多画一截，**画在躯干底下**。

    ★★★ 2026-10-20 第二十七问（G121）：补出来的这块必须**收进以肩关节为
        圆心的圆盘里**，这是这一版唯一的、也是最要紧的改动。

        用户第二十七问截图 1/2（放大件 /tmp/u1_arm.png）：一挥手，肩膀底下
        多出**第二条袖子** —— 一大块青色楔形斜指右下、顶边是一条硬直线，
        和真正抬起来的那条袖子叠在一起，肘部还有一道线稿横穿过去。
        把 arm_r_root + arm_r_upper 单独合成放大（/tmp/a_upper.png）坐实：
        重影就是这件袖根塗り足し。

        它为什么会露出来：上一版是**逐行**把袖子往身体里补，一路补到肘部
        （实测件 98x334，也就是整条上臂那么长）。整件挂在 `arm_*` 组上，
        绕**肩关节**转；离枢轴越远的行，转动时扫过的弧越长。
        肩那头几乎不动（藏得住），肘那头转 58° 直接从夹克边上甩出来 ——
        它的层号 96 比躯干 100 低，可躯干只盖得住自己剪影里的那部分。

        正解是几何上的：**绕一个点转，以这个点为圆心的圆盘是不变量**。
        把塗り足し限制在肩关节周围半径 R = 0.52×上臂长 的圆盘里，
        无论转多少度，这块都还在同一个圆盘里 —— 既不可能扫出躯干，
        又正好把转开后露出来的肩窝填满。教程说的
        「腕の付け根は肩のパーツの下に十分な範囲を描いておく（回転させても
        隙間ができない）」（shiroikarasu.net/live2d-part-separation-
        illustrator-guide/）讲的就是**付け根**——肩关节那一圈，不是整条上臂。

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
    rgb = body[..., :3].copy()
    yy_d = np.arange(H)[:, None] - float(pivot[1] if pivot is not None else 0)
    xx_d = np.arange(W)[None, :] - float(pivot[0] if pivot is not None else 0)
    if pivot is not None and arm_len:
        # ★ G121：补绘区 = **以肩关节为圆心的整个圆盘**（减去袖子自己），
        #   而不是上一版「逐行往身体里加 d 像素」。
        #   为什么要填满整个圆盘：转动时露出来的是肩窝，补一条竖带只能填住
        #   竖直那一截，斜着抬手就在左下角留个硬角（/tmp/arm_sh6.png 第 3、4 格）。
        #   圆盘填实以后，关节处的剪影本身就是个圆 —— 这正是教程里
        #   「袖根画成圆帽」的做法，转任何角度都是同一个圆。
        # ★ 2026-10-21：R = 袖宽/2（教程口径），再用「上臂长 × K」兜个上限。
        #   `target` 就是袖子逐行宽度的 80 分位，正是教程说的「上腕の幅」。
        R = min(float(target) * ROOT_DISC_W, float(arm_len) * ROOT_DISC_K)
        # ★★★ 2026-10-21 第三十三问：圆盘半径必须**和关节那个圆严格同一个数**。
        #   以前这里自己算一遍（target×0.58），主流程里 yoke 又算一遍
        #   （80 分位÷2），两个数差 1~2px —— 上臂被裁成半圆帽的那条弧
        #   和袖根补出来的那条弧**对不齐**，中间留一道 1~2px 的透明月牙。
        #   转起来就是用户说的「割裂」里那条亮缝。统一成同一个 R，再加 2px
        #   のりしろ（shiroikarasu：「多少描きすぎるくらいでちょうど良い」）。
        if joint_r:
            R = float(joint_r) + 2.0
        print("  袖根圆盘 %s: 关节R=%.1f → 补绘R=%.1f（袖宽80分位 %.1f）"
              % (side, float(joint_r or 0.0), R, target))
        #   ★ 这里必须 `& ~up` 而不是 `& ~dilate(up, 1)`：留 1px 缝的话，
        #     下面描线稿的 `full = ext | up` 会沿着这条缝也算出一圈"剪影边"，
        #     在青袖**正中间**糊出一道深色线，看上去就是两条袖子叠着
        #     （/tmp/arm_sh6.png 第二版 2~4 格）。贴齐了才只有外沿一条线。
        # ★★★ 2026-10-21 第二十九问：圆盘 → **胶囊**（圆盘 ∪ 沿臂轴的等宽带）。
        #   实测上臂逐行宽度从肩头 **2px** 一路长到肘部 58px —— 是个尖楔子，
        #   而真实上臂是肩最宽、向肘微收。闸门 w_top/w_fore 只有 0.57~0.59，
        #   用户连着两轮说「上臂比前臂细」。
        #   上一版只补了肩关节那一个圆盘（R≈33px，实测只加宽 15~20px），
        #   补的位置对、量差得远：从肩到肘整条上臂在夹克身底下都还有半截袖子，
        #   那半截才是 shiroikarasu 教程说的「**袖の中の腕の続き**」：
        #     「腕を上げたときに見える**脇の下**と、**袖の中の腕の続き**は
        #       あらかじめ描いておく」
        #     （https://shiroikarasu.net/live2d-part-separation-illustrator-guide/）
        #   所以补绘区 = 以肩为圆心的圆盘 **∪** 沿「肩→肘」轴线、半宽 R 的带子，
        #   也就是一条胶囊。它仍然整条落在 `erode(hidden,2)` 里（夹克身盖得住），
        #   层 95/96 还在躯干 100 之下 ⇒ 静止时一个像素都看不见。
        #   ★ 为什么不会重现第二十七问那块「第二条袖子」：那一版 R=99px，比袖子
        #     胖三倍，胶囊的半宽现在 = 袖宽×0.58，**横向不超过袖子自己的剪影**，
        #     抬手时露出来的只是把细楔子补成了等宽，不会多出一牙。
        if elbow is not None:
            ax = float(elbow[0]) - float(pivot[0])
            ay = float(elbow[1]) - float(pivot[1])
            alen = max(1e-6, float(np.hypot(ax, ay)))
            ax, ay = ax / alen, ay / alen
            along = xx_d * ax + yy_d * ay            # 沿臂轴
            perp = np.abs(xx_d * (-ay) + yy_d * ax)  # 离臂轴的距离
            band = (along >= 0.0) & (along <= alen) & (perp <= R)
            # ★★★ 2026-10-21 第三十三问·第五刀：**肩帽向上扩圈**。
            #   症状：闸门「关节不露底(颈)」压力姿势多出 70px 新洞；
            #   渲染 sh+25° 贴脸看（logs/asset_qa/q33_hole_AB.png 下排右格），
            #   肩头靠脖子那侧露出一块约 10x9 的**真窟窿**（红色标出）。
            #   根因：袖子的肩帽最高点离肩枢轴 **53px**，而关节圆盘按教程口径
            #   只有 R=34（= 袖宽/2）。圆盘之外的那 19px 一旦转起来就没人垫底 ——
            #   躯干在那儿只有 alpha=101 的抗锯齿边，手臂自己又整块转走了。
            #   修法（shiroikarasu.net/live2d-part-separation-illustrator-guide/：
            #   「**腕の付け根は肩のパーツの下に十分な範囲を描いておく**
            #     （回転させても隙間ができない）」「多少描きすぎるくらいでちょうど良い」）：
            #   把袖根件在**肩侧半边**（along<0）补成一个半径 R+ROOT_CAP_EXT 的半圆盘。
            #   为什么转到哪都有效：它和关节同圆心，**圆绕自己的圆心转形状不变**，
            #   任意角度覆盖的区域完全一样（saraemi 那条「関節パーツは正円」是同一个道理）。
            #   为什么静止看不见：整块仍然 `& erode(hidden, 2)`（躯干∪袖子盖得住），
            #   而且这件层号 95/96 在躯干 100 之下。
            cap = ((xx_d * xx_d + yy_d * yy_d) <= (R + ROOT_CAP_EXT) ** 2) & (along < 0.0)
        else:
            band = np.zeros((H, W), bool)
            cap = np.zeros((H, W), bool)
        # ★ 再叠一层「逐行补到目标宽」：胶囊的半宽是从**臂轴**量的，而臂轴
        #   （肩→肘锚点连线）偏在袖子内侧，于是胶囊的内边界刚好停在夹克外沿上
        #   —— 实测 l 侧 row408：袖子 x85..127、躯干自 x125 起、胶囊止于 x125，
        #   **一个像素都没伸进夹克底下**，比值只从 0.59 爬到 0.61。
        #   原画里袖子被白夹克前襟挡住的那一截压根没画（画师只画可见部分），
        #   这正是 shiroikarasu 说的要预先补出来的「袖の中の腕の続き」。
        #   所以逐行往身体内侧补到 `target`（袖宽 80 分位 ≈ 肘部宽），
        #   补出来的还是只落在 `erode(hidden,2)` 里 ⇒ 静止时依旧全藏住。
        #   顶端 ROOT_TOP_RAMP 行 smoothstep 渐入，不留水平硬边（第二十七问的坑）。
        rowfill = np.zeros((H, W), bool)
        for y, (ea, eb) in edges.items():
            d = int(round(float(target) - (eb - ea + 1)))
            if d <= 0:
                continue
            d = min(ROOT_EXT_MAX, d)
            t = min(1.0, max(0.0, (y - y0) / float(ROOT_TOP_RAMP)))
            d = int(round(d * (t * t * (3.0 - 2.0 * t))))
            if d <= 0:
                continue
            if side == "r":
                rowfill[y, max(0, ea - d):ea] = True
            else:
                rowfill[y, eb + 1:min(W, eb + 1 + d)] = True
        disc = (xx_d * xx_d + yy_d * yy_d) <= R * R
        ext = (disc | cap | band | rowfill) & erode(hidden, 2) & ~up
        # ★★★ 2026-10-21 第二十九问（自查发现，用户没点名）：把补出来这块的
        #   **内侧轮廓磨圆**。抬手实拍（/tmp/armpit.png，wave 第 100 帧放大 2×）
        #   能看见肩头是一条**直的斜切边**，中间还有一个折角 —— 那是
        #   `rowfill` 按「补到 target 宽」留下的、平行于臂轴的直边，
        #   和圆盘边界撞出来的拐点。静止时它藏在夹克身底下看不见，
        #   手一抬整条转出来，就成了肩上一道生硬的折线。
        #   参考 saraemi.com/vtuber/2022/02/09/live2d_arm/：
        #   「関節パーツは正円で」「線がズレていると失敗しやすい」——
        #   关节附近的轮廓要是圆的，不能有角。
        #   开运算（先腐蚀后膨胀）只会**去掉**像素，不会新增 ⇒ 「袖根静止
        #   露出 0」那道闸不可能被它弄红；它专门削掉凸角和毛刺。
        #   ★★★ 2026-10-21 第三十三问：开运算**必须把关节圆盘豁免掉**。
        #   实测旧版 arm_r_root 成品只有 2582px，是一道**细月牙**，根本不是圆盘：
        #   圆心取错 ⇒ 圆盘 14% 在背景上 ⇒ `& erode(hidden,2)` 先切掉一大片，
        #   剩下的窄条再被 K=5 的开运算整段抹平。于是「转出来的肩窝」没人填，
        #   就是用户说的**断裂**。圆心修正之后圆盘 100% 在身体内，这里再把
        #   `disc` 和 `band` 一起列进豁免，保证圆盘**整个**留下来。
        ext = dilate(erode(ext, ROOT_SMOOTH_K), ROOT_SMOOTH_K) \
            | (ext & (band | disc | cap))
    else:
        ext = np.zeros((H, W), bool)
        for y, (a, b) in edges.items():
            d = min(ROOT_EXT_MAX, int(round(target - (b - a + 1))))
            if d <= 0:
                continue
            t = min(1.0, (y - y0) / float(ROOT_TOP_RAMP))
            d = int(round(d * (t * t * (3.0 - 2.0 * t))))
            if d <= 0:
                continue
            x0, x1 = (max(0, a - d), a) if side == "r" else (b + 1, min(W, b + 1 + d))
            ext[y, x0:x1] = True
    # ---- 上色：从袖子**自己**往里扩散 + ぼかし（2026-10-21 第三十三问）-------
    # 旧做法是「逐行取袖缝内侧 6px 的中位色，再按列做线性 ramp」。
    # 肉眼看成品件（logs/asset_qa/q33_uppers.png 第三格 arm_l_root）：
    # 整块补绘是一条条**横向色带**，每一行一个平色 —— 原画袖子的明暗是斜的，
    # 逐行取色把它切成了阶梯。手臂一抬，这块从夹克底下转出来，
    # 就是用户说的「像另一片布贴在袖子下面」（割裂）。
    #
    # 正解：把袖子自己的像素往补绘区里**扩散**（bleed 是四邻域平均，
    # 天然带平滑），再按「离袖子多远」统一压暗 —— 明暗走向就跟着原画走，
    # 不会出现横档。最后在补绘区内做一次小半径模糊，
    # 即 note.com/shumi_log/n/n8172d73024aa 说的「**肩の付け根はぼかし処理**」。
    # 取样源要**避开袖缝那条 2px 深线**：直接拿 up 当源，bleed 会把线稿色
    # 一路摊进整片补绘，出来就是一块明显发暗发绿的布（第一版实测如此）。
    # 往里腐蚀 3px 取「干净的袖子内部」，扩散出来的才是袖子本色。
    src_ok = erode(up & (body[..., 3] > 200), 3)
    if not src_ok.any():
        src_ok = up & (body[..., 3] > 200)
    if ext.any() and src_ok.any():
        # ★★★ 2026-10-22 第三十五问：into 必须**连带袖子那 3px 边缘环**。
        #   bleed 是逐圈往 `into` 里长的；src_ok 已经往里腐蚀了 3px，它和补绘区
        #   之间隔着一圈「袖子边缘」——那圈不在 into 里，第一轮 ring 就是空集、
        #   直接 break，于是整块补绘**原封不动保留原画的夹克白**。
        #   实测件 arm_r_root 中位色 (250,248,244) ＝ 纯白，而袖子是 (114,188,192)：
        #   抬手时腋下露出来的就是一块白板（logs/asset_qa/q35_attr_root.png 红色那块）。
        #   把边缘环放进 into，让颜色能"走过去"；rgb 仍然只在 ext 里被改写，
        #   袖子本身一个像素不动。
        _into = ext | (up & ~src_ok)
        filled, _grown, bdist = bleed(rgb, src_ok, _into, rounds=ROOT_BLEED_ROUNDS)
        f = np.clip(bdist / ROOT_SHADE_DIST, 0.0, 1.0)[..., None]
        shaded = np.clip(filled.astype(np.float32) * (1.0 - (1.0 - ROOT_SHADE) * f),
                         0, 255)
        rgb[ext] = shaded[ext].astype(rgb.dtype)
        # ぼかし：只在补绘区内部平均，边界不动（边界要留给下面描线稿）
        k = ROOT_BLUR_K
        inner = erode(ext, 2)
        if inner.any():
            acc = np.zeros(rgb.shape, np.float32)
            cnt = np.zeros(ext.shape, np.float32)
            base_f = rgb.astype(np.float32)
            for dy in range(-k, k + 1):
                for dx in range(-k, k + 1):
                    sm = shift(ext | src_ok, dy, dx)
                    sv = np.dstack([shift(base_f[..., c], dy, dx) for c in range(3)])
                    acc[sm] += sv[sm]
                    cnt[sm] += 1.0
            ok = inner & (cnt > 0)
            rgb[ok] = (acc[ok] / cnt[ok][:, None]).astype(rgb.dtype)
    # 新内缘描线稿：转出来之后这条就是袖子的剪影边，没有线会像一块色块
    #   只在**圆盘外沿**描线：靠身体里侧那一段将来可能转成剪影边，要线；
    #   贴着袖子的那一侧已经有原画的袖缝线了，再描一道就是双线。
    full = ext | up
    rim = (full & ~erode(full, LINE_W)) & ext
    rim_s = (full & ~erode(full, LINE_W + 1)) & ext
    ln = np.array(LINE_RGB, np.float32)
    for mask, k in ((rim_s, 0.45), (rim, 0.9)):
        if mask.any():
            cur = rgb[mask].astype(np.float32)
            rgb[mask] = (cur * (1 - k) + ln * k).astype(rgb.dtype)
    # ---- 靠肘那一端渐隐（2026-10-21 第三十三问）----------------------------
    # 胶囊是「圆盘 ∪ 沿臂轴的等宽带」，带子在肘那头是**一刀切平**的：
    # 抬到 -100° 时那条垂直臂轴的直边整条转出来，在袖子底下拉出一条硬边
    # （logs/asset_qa/q33_sh2_new.png 第三格）。
    # 这一端在静止时本来就被夹克和前臂压着，渐隐掉不会少东西。
    fade = np.ones((H, W), np.float32)
    if pivot is not None and elbow is not None and arm_len:
        _ax = float(elbow[0]) - float(pivot[0])
        _ay = float(elbow[1]) - float(pivot[1])
        _al = max(1e-6, float(np.hypot(_ax, _ay)))
        _along = (xx_d * (_ax / _al) + yy_d * (_ay / _al))
        fade = np.clip((_al - _along) / ROOT_FADE_END, 0.0, 1.0).astype(np.float32)
        fade = fade * fade * (3.0 - 2.0 * fade)        # smoothstep
    return ext, rgb, target, fade


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

    # ---- 肩关节圆 + 插肩育克归位（2026-10-21 第三十一问）----
    # ★★★ 这件青袖是**插肩袖(raglan)**：袖片的"顶点"其实在脖子根，不在肩关节。
    #   以前整片袖子（连育克）都挂在 arm_* 组上绕肩转，于是一抬手，
    #   那条笔直的插肩缝整个甩到空中 —— 就是用户附图 4 里肩上那道
    #   **刀切直边加一个楔子**。
    #   教程口径（kw-nmnm / しゅみ / saraemi / しららぎ / adglobe 五家一致）：
    #     「上腕の肩側は**半円状**に」「関節パーツは**正円**で腕幅と同じ直径」
    #     「**関節を回転軸の中心にあわせて綺麗な円形に描く**」
    #   所以：关节圆**以上**的育克不属于胳膊，留给躯干当静止件；
    #   胳膊那半边的顶端收成**以关节为圆心的半圆帽**，转任何角度剪影都是圆的。
    SJ, JOINT_R, CAP, CAP_R = {}, {}, {}, {}
    half_ov = ELBOW_OVERLAP // 2
    xx_all = np.arange(W)[None, :]
    for side in ("l", "r"):
        ey = int(pts[f"elbow_{side}"][1])
        up_only = arms[side] & (yy_all <= ey + half_ov)
        jx, jy, R = shoulder_joint(up_only, pts[f"shoulder_{side}"], side)
        sj = (jx, jy)
        SJ[side], JOINT_R[side] = sj, R
        ax = float(pts[f"elbow_{side}"][0]) - sj[0]
        ay = float(pts[f"elbow_{side}"][1]) - sj[1]
        al_ = max(1e-6, float(np.hypot(ax, ay)))
        ax, ay = ax / al_, ay / al_
        dx = xx_all - sj[0]
        dy = yy_all - sj[1]
        along = dx * ax + dy * ay
        disc = (dx * dx + dy * dy) <= R * R
        # ★★★ 2026-10-21 第三十三问：育克只取**靠脖子那一侧**。
        #   插肩袖的袖片顶点在脖子根，会甩出去的是**内侧**那条长楔子
        #   （离枢轴远）；外侧那顶肩帽紧贴枢轴，转起来几乎不动，
        #   本来就该跟着胳膊走。
        #   更要命的是几何后果：把外侧肩帽也留给躯干，它会**从上方把
        #   被清空的袖子区封成一个闭合洞** —— 于是
        #   `clean_baked_residue` 的「四面围死的洞一律补实」把它拿最近邻
        #   （就是这块育克的青色）填成 alpha=255，躯干上凭空多出
        #   139(l)/195(r) 个不跟手臂转的青像素；不让它填，又变成
        #   check_assets「袖下躯干无新窟窿」的 390 px。两条闸互相顶死，
        #   根子就在"外侧肩帽不该留给躯干"。
        #   只留内侧之后，清空区朝外侧一直通到剪影边缘，不再是闭合洞。
        inboard = (xx_all < sj[0]) if side == "r" else (xx_all > sj[0])
        if os.environ.get("ZC_ARM_OLD_YOKE"):
            # A/B 回退开关：恢复旧的「整片育克都留给躯干」。
            # 判决证据 logs/asset_qa/q33_yoke_ab2.png（11x 贴脸）与
            # q33_hole_AB.png（洋红底 + 红色标窟窿）—— 旧行为在 sh+25° 下
            # 肩头裂成两块、中间一道白缝，已判负。留着只为将来复现对照。
            inboard = np.ones_like(inboard)
        yoke = arms[side] & (along < 0.0) & ~disc & inboard
        arms[side] = arms[side] & ~yoke
        print("  插肩育克 %s: 关节(%.0f,%.0f) R=%.1f → %d px 留给躯干（不跟着胳膊转）"
              % (side, sj[0], sj[1], R, int(yoke.sum())))

        # ---- 肩の関節パーツ：以关节为圆心的半圆帽，归躯干（静止），压在上臂之上 ----
        #   形状必须是**圆**：圆绕自己的圆心转形状不变 ⇒ 帽子底下的胳膊
        #   转到任何角度，交界处都是同一条弧，不会裂、不会露直边。
        #   只取关节线**以上**那半边（along <= +CAP_PAST·R）：下半边是胳膊
        #   自己的肉，留给它转；上半边是肩膀，本来就不该跟着胳膊甩。
        dist_j = np.sqrt(dx * dx + dy * dy)
        #   半径不能拍脑袋：袖子在关节线**上方**还有一截（肩头那座"塔"）。
        #   帽子要是比它矮，一转塔尖就从帽沿戳出来，变成一根青色尖刺（实拍见
        #   logs/asset_qa/q35_cap_after_mag.png 的 ArmRA 3/6/10）。
        #   所以半径 = 塔的最远点 + 余量，按左右各自量。
        _prox = arms[side] & (along <= CAP_PAST * R)
        _tower = float(dist_j[_prox].max()) if _prox.any() else 0.0
        cap_r = max(CAP_SCALE * R, _tower + CAP_MARGIN)
        cap_a = np.clip((cap_r - dist_j) / CAP_FEATHER, 0.0, 1.0)
        cap_a = cap_a * np.clip((CAP_PAST * R - along) / CAP_FEATHER, 0.0, 1.0)
        CAP[side] = np.where(alpha, cap_a, 0.0).astype(np.float32)
        CAP_R[side] = cap_r
        print("  肩キャップ %s: 塔高 %.1f → 半径 %.1f（=%.2f×R）→ %d px 归躯干、层 %d"
              % (side, _tower, cap_r, cap_r / R, int((CAP[side] > 0.5).sum()),
                 CAP_LAYER[side]))

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
        sh_pt = SJ[side]
        report.setdefault("shoulder_joint", {})[side] = [round(sh_pt[0], 1),
                                                         round(sh_pt[1], 1)]
        arm_len = float(np.hypot(pts[f"elbow_{side}"][0] - sh_pt[0],
                                 pts[f"elbow_{side}"][1] - sh_pt[1]))
        el_pt = (float(pts[f"elbow_{side}"][0]), float(pts[f"elbow_{side}"][1]))
        ext, ext_rgb, ext_target, ext_fade = root_fill(
            body, up_mask, side, hidden, pivot=sh_pt, arm_len=arm_len,
            elbow=el_pt, joint_r=JOINT_R[side])
        if ext.any():
            ea = soft(ext)
            ea[erode(ext, 1)] = 1.0
            ea = ea * ext_fade
            ys, xs = np.nonzero(ea > 0.004)
            ebox = (int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1)
            name = f"arm_{side}_root"
            cut(ext_rgb, ea, ebox).save(os.path.join(sp, name + ".png"))
            report["parts"].append({
                "id": name, "file": f"sprites/{name}.png",
                "pos": [ebox[0], ebox[1]],
                "size": [ebox[2] - ebox[0], ebox[3] - ebox[1]],
                "group": f"arm_{side}", "layer": ROOT_LAYER[side],
                "pivot": [float(sh_pt[0]), float(sh_pt[1])],
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
        # ---- 肘关节正圆（2026-10-21 第三十三问）----------------------------
        # 教程口径（kw-nmnm.hatenablog.com/entry/2018/11/06/203151）：
        #   「上腕の肘部分は**半円状**に、前腕の切れ目は**半円の真ん中を突っ切る形**に」
        # 也就是说：肘这里**两件都要盖满同一个正圆**，切口从圆心穿过去。
        # 旧版是拿 `elbow_y ± 12` 一条**水平直线**切的，前臂只盖到肘圆的 63.9%
        # （左 64.7%）—— 前臂一弯，圆的下半圈有三分之一没人画，就是缺口。
        #
        # ★ 圆心必须和 rig 的旋转枢轴是**同一个点**，否则圆不是旋转不变量。
        #   所以这里把量出来的圆心写进 arm_parts.json 的 elbow_joint，
        #   make_rig.py 优先读它（和 shoulder_joint 一个待遇），
        #   不再用 anchors 里那个按比例估的 elbow_*（右侧实测偏外 3px）。
        exs = np.nonzero(m[elbow_y])[0]
        if exs.size:
            ejx = float(exs.min() + exs.max()) / 2.0
            ejr = float(exs.max() - exs.min() + 1) / 2.0
        else:
            ejx, ejr = float(pts[f"elbow_{side}"][0]), 20.0
        el_joint = (ejx, float(elbow_y))
        eldx = np.arange(W)[None, :] - ejx
        eldy = np.arange(H)[:, None] - float(elbow_y)
        elbow_disc = ((eldx * eldx + eldy * eldy) <= ejr * ejr) & m
        report.setdefault("elbow_joint", {})[side] = [round(ejx, 1), float(elbow_y)]
        print("  肘关节 %s: 圆心(%.0f,%d) R=%.1f  [anchors 给的是 (%.0f,%d)]"
              % (side, ejx, elbow_y, ejr,
                 float(pts[f"elbow_{side}"][0]), int(pts[f"elbow_{side}"][1])))

        up_rgb = body[..., :3].copy()
        if ext.any() and ROOT_CLEAR_SEAM:
            seam = ext & dilate(up_mask, LINE_W + 2) & ~up_mask
            up_rgb[seam] = ext_rgb[seam]
            report["checks"].setdefault("seam_cleared_px", {})[side] = int(seam.sum())
        # ★ 第三十五问：上腕の肘は**半円状**に描く（REFERENCE_NOTES 第五十四批）。
        #   原来是一刀直横切（yy <= elbow_y + half），前臂一弯，上臂末端那条
        #   直边就从肘圆底下探出来，肘看着像两段水管平口对接（实拍 q35_joints.png）。
        #   改成：关节线以上照旧 + 关节线以下**只留肘圆内**的部分 ⇒ 末端收成半圆。
        #   像素依旧是重叠复制（前臂也有这一圈），静止合成不变。
        upper_keep = m & ((yy_col <= elbow_y) | elbow_disc)
        for seg, keep in (("upper", upper_keep),
                          # 前臂 = 肘线**以下** ∪ 整个肘关节圆 ⇒ 近端同样收成半圆。
                          #   上臂留下半圆、前臂留上半圆，两片合起来永远是**整圆**，
                          #   前臂转到任何角度，肘这里的轮廓都还是那个圆（圆绕自己
                          #   的圆心转形状不变）。原来多留的 12px 直带会在大角度
                          #   （ArmRB−8/−10）甩出一条直边，见 q35_elbow_neg.png。
                          ("fore",  (m & (yy_col >= elbow_y) | elbow_disc)
                                    & (yy_col <= wrist_y + 1)),
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
                # ★ 肘圆**整圈满值**：淡入带是给"直线切口"用的，而肘这里的切口
                #   是圆，圆内要是半透明，前臂一弯就在肘上糊出一块浅色月牙
                #   （两件各 0.5，over 起来 0.75，底下躯干透出来）。
                #   静止时它正压在上臂同样的像素上（层 142/143 > 140/141），
                #   颜色一模一样 ⇒ 合成差不变。
                a[elbow_disc] = orig_a[elbow_disc]
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
                # 枢轴 = 真·肩关节（不是 anchors 那个肩峰轮廓点）
                joint, grp, lay = sh_pt, f"arm_{side}", layer[side]
                note = "上臂：绕肩旋转"
            elif seg == "fore":
                joint, grp, lay = el_joint, f"forearm_{side}", layer[side] + 4
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

    # ---- 落盘：肩の関節パーツ ----
    # 它用的是**原画自己的像素**，静止时正压在上臂同样的位置上 ⇒ 合成差为 0；
    # 一旦胳膊转起来，它留在原地，胳膊的根部切口就永远藏在它下面。
    for side in ("l", "r"):
        ca = CAP.get(side)
        if ca is None or not (ca > 0.004).any():
            continue
        ys, xs = np.nonzero(ca > 0.004)
        box = (int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1)
        name = f"arm_{side}_cap"
        cut(body[..., :3], ca, box).save(os.path.join(sp, name + ".png"))
        sj = SJ[side]
        report["parts"].append({
            "id": name, "file": f"sprites/{name}.png",
            "pos": [box[0], box[1]], "size": [box[2] - box[0], box[3] - box[1]],
            "group": "chest", "layer": CAP_LAYER[side],
            "pivot": [float(sj[0]), float(sj[1])],
            "note": ("肩の関節パーツ：以肩关节为圆心、半径 %.2f×R 的半圆帽，"
                     "属于身体（不跟手臂转），画在上臂之上。"
                     "胳膊的根部切口藏在它下面 ⇒ 转到任何角度都看不到直切边"
                     % (CAP_R[side] / JOINT_R[side])),
        })
        report["checks"].setdefault("shoulder_cap", {})[side] = {
            "radius": round(CAP_R[side], 1),
            "px": int((ca > 0.5).sum()), "layer": CAP_LAYER[side],
        }

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
    _bm = diff.max(axis=2) > 12
    if os.environ.get("ZC_ARM_DIFF_DUMP"):
        _v = (body[..., :3].astype(np.float32) * orig_a[..., None] * 0.35).astype(np.uint8)
        _v[_bm] = (255, 0, 0)
        Image.fromarray(_v).save(os.environ["ZC_ARM_DIFF_DUMP"])
        _ys, _xs = np.nonzero(_bm)
        if _ys.size:
            print("  [dump] bbox x %d..%d y %d..%d" % (_xs.min(), _xs.max(), _ys.min(), _ys.max()))
            import collections
            _c = collections.Counter((int(y) // 50 * 50) for y in _ys)
            print("  [dump] 按 y 段:", sorted(_c.items())[:40])
    bad = int(_bm.sum())
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
