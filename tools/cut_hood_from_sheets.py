#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从参考模板切**兜帽**件（T46.17）。

和 `cut_from_sheets.py` 的关系
------------------------------
那个工具切的是**发型**（twin / pony / long），输入是 `sheets/sheet_<发型>.png`。
这个工具切的是**兜帽**，输入是 `sheets/sheet_<发型>_hood.png`，
公共的抠像 / 形态学 / 出件（`emit_piece`）全部 import 复用，不另起一套。

拆成两个文件而不是加个 `--hood` 开关，是因为掩膜逻辑完全不同：
发型件靠「发色」找，兜帽件靠「**戴帽图和不戴帽图的差分** + 布料材质」找。
塞进同一个 `cut_masks` 只会让那个本来就 270 行的函数更难读。

为什么每一档要切**两片**
------------------------
2026-10-19 第十六问的欠账是「兜帽按模板重做」。第一版只切了帽壳，
把它贴回「不戴帽」底图做验收（教程原话：切り分けた後には元絵と
重ねあわせて不足パーツを必ず確認），结果一眼看出问题：

  · short  —— 几乎完美，短发本来就收在帽子里
  · twin / pony / long —— **发尾从帽顶戳出来**

因为戴上兜帽时头发本身的造型是变了的：马尾不再高高扎起，而是从帽口
垂到胸前。光加一片帽壳、不动头发，就是「帽子扣在高马尾上」的穿帮图。

所以每一档切两片：

  hood_<style>      帽壳（白外布 + 薄荷青内衬 + 帽口折边），脸的位置是**镂空**的
  hoodhair_<style>  戴帽时**露在帽子外面**的那段头发（short 档没有，会自动跳过）

戴上兜帽时，原来那套发型件整体 hide 掉，换成这两片。
见 `attachments.json` 的 pose_groups：`hood_pose.up` 负责「戴上时收走谁」，
`hairstyle.<档>.hide_parts` 负责「这个发型不要别档的帽子」——
引擎 `pose_opacity` 对两个组是**相乘**的（zrig.c:4621），
于是「戴帽 ∧ 发型=X」这个与条件不用改一行 C 代码。

掩膜怎么来（2026-10-20 第二十三问整段换掉，详见 `cut_one` 的注释）
------------------------------------------------------------------
**兜帽是一块区域，不是一种颜色。** 旧版逐像素分类「布 vs 头发」再叠九层
补丁滤镜，把帽子削成 9732px 的铁丝圈、下颌留一道平切痕。现在只用几何：

  下颌以上  轮廓里只有「帽子」和「脸口」两样东西（四张模板逐张看过，
            外露的头发一律在下颌以下才从帽口垂出来）
            ⇒ **帽壳 = 剪影 − 脸口**，白布和头发根本不用分。
  脸口      从脸（下颌以上最大的皮肤连通块）在「非薄荷青」里漫延出来的块。
            内衬是一道闭合的拱，天生就是脸口的边界。
            这是全套算法**唯一**的颜色判据。
  下颌以下  从帽口垂下来的两片内衬（连通块，必须接得上帽壳）
            ＋ 外侧白外布（每行从剪影外缘填到内衬为止，左右独立、下沿渐缩）。

★ 三个踩过的坑，别再踩：
  · 收尾只能 `fill_small`，**不能全局 `fill_holes`** —— 帽口下缘一被白外布
    封住，脸口就从「开口」变成「内部空洞」被填实，整张脸切进帽子里
    （pony/long 实测 54697 → 90431 px）。
  · 行填必须左右**分开判断**，否则只有一侧有内衬的行会横贯拉出白色大横条。
  · `hair_like()` 不能拿来排头发 —— 它用「离真发 15px 内的弱判据」召回高光，
    而帽口紧挨着头发，于是**白布的冷灰阴影整片被判成头发**。
    新算法根本不需要排头发，这个坑自动消失了。
"""
from __future__ import annotations

import argparse
import collections
import io
import json
import os
import sys

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cut_from_sheets as C  # noqa: E402

#: 发型 → (不戴帽的那张, 戴帽的那张)
SHEETS = {
    "short": ("design_sheet_short.png", "sheets/sheet_short_hood.png"),
    "twin": ("sheets/sheet_twin.png", "sheets/sheet_twin_hood.png"),
    "pony": ("sheets/sheet_pony.png", "sheets/sheet_pony_hood.png"),
    "long": ("sheets/sheet_long.png", "sheets/sheet_long_hood.png"),
}

#: 每档切哪几片、落到哪个槽。`None` = 这一档这片可能是空的（short 没有外露头发）。
PLAN = {
    "short": [("acc_hood_short", "head_over_hair", "hood")],
    "twin": [("acc_hood_twin", "head_over_hair", "hood"),
             ("hair_hood_twin", "head_side_hair", "hair")],
    "pony": [("acc_hood_pony", "head_over_hair", "hood"),
             ("hair_hood_pony", "head_side_hair", "hair")],
    "long": [("acc_hood_long", "head_over_hair", "hood"),
             ("hair_hood_long", "head_side_hair", "hair")],
}

#: 兜帽下沿的硬限位（模板坐标）。肩线 436 + 124，留足帽子搭在肩上的部分。
YLIM = 560
#: 闭合薄荷青内衬用的膨胀核。9 = 罗纹之间最宽的缝（实测 6px）再加余量；
#: 多出来的 4px 同时就是帽口内沿的**塗り足し**，正好压住一点头发。
TEAL_CLOSE = 9
#: 线稿判据。max(r,g,b) < 170。150 太松：long 档的白外布会从线稿的
#: 淡处漏进夹克（实测生长 2404 -> 16754 px）；185 又会把布料的冷灰阴影
#: 当线稿，白外布长不出来。
LINE_T = 170
#: 白外布生长的防漏闸。四档实测 1789~2772 px，给 8000 还漏就是线稿破了口。
WHITE_LEAK = 8000


def comps(m):
    """八连通连通域。工程环境没有 scipy，手写。"""
    h, w = m.shape
    seen = np.zeros_like(m)
    out = []
    ys, xs = np.nonzero(m)
    for y0, x0 in zip(ys, xs):
        if seen[y0, x0]:
            continue
        q = collections.deque([(y0, x0)])
        seen[y0, x0] = True
        cur = [(y0, x0)]
        while q:
            y, x = q.popleft()
            for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1),
                           (1, 1), (1, -1), (-1, 1), (-1, -1)):
                ny, nx = y + dy, x + dx
                if 0 <= ny < h and 0 <= nx < w and m[ny, nx] and not seen[ny, nx]:
                    seen[ny, nx] = True
                    q.append((ny, nx))
                    cur.append((ny, nx))
        out.append(cur)
    return out


def keep_parts(m, min_px, box=None):
    """留下够大的连通块（可再限定必须落在某个框里）。"""
    out = np.zeros_like(m)
    kept = []
    for c in comps(m):
        if len(c) < min_px:
            continue
        ys = [p[0] for p in c]
        xs = [p[1] for p in c]
        if box is not None:
            x0, y0, x1, y1 = box
            if min(xs) < x0 or max(xs) > x1 or min(ys) < y0 or max(ys) > y1:
                continue
        for y, x in c:
            out[y, x] = True
        kept.append(len(c))
    return out, sorted(kept, reverse=True)


def fill_small(m, maxa=900):
    """填掉小内部空洞；脸那个大洞留着（兜帽是镂空的）。"""
    holes = C.fill_holes(m) & ~m
    out = m.copy()
    for c in comps(holes):
        if len(c) < maxa:
            for y, x in c:
                out[y, x] = True
    return out



def row_runs(row):
    """一行里的连续段，返回 [(x0, x1), ...]。"""
    ix = np.nonzero(row)[0]
    if len(ix) == 0:
        return []
    cuts = np.nonzero(np.diff(ix) > 1)[0]
    out = []
    s = 0
    for c in cuts:
        out.append((int(ix[s]), int(ix[c])))
        s = c + 1
    out.append((int(ix[s]), int(ix[-1])))
    return out



def row_fill(m):
    """逐行把最左到最右之间填满 —— 得到兜帽的**整个剪影**（含脸的开口）。

    不能用 `fill_holes`：马蹄形在下巴那里是**开口**的，脸不是封闭的洞，
    填不住。结果就是「帽外头发」把帽口里的刘海也算了进去。
    """
    out = np.zeros_like(m)
    for y in range(m.shape[0]):
        ix = np.nonzero(m[y])[0]
        if len(ix):
            out[y, ix[0]:ix[-1] + 1] = True
    return out



def flood(seed, allowed):
    """在 allowed 里从 seed 漫延到不动点（4/8 连通，k=3 膨胀迭代）。"""
    cur = seed & allowed
    while True:
        nxt = C.dilate(cur, 3) & allowed
        if nxt.sum() == cur.sum():
            return nxt
        cur = nxt


def cut_one(style, design, chin, eyeline, head_cx):
    """切一档，返回 {'hood': mask, 'hair': mask, 'A': rgba}。

    ★★★ 2026-10-20 第二十三问整段重写。旧版的做法和它的下场
    ------------------------------------------------------------------
    旧版把兜帽当成「一种颜色」来找：先拿「暖白布 ∪ 薄荷青 ∪ 线稿 且 非紫调」
    当材质区，再从外凸轮廓测地生长，最后叠了**九层补丁滤镜**去毛刺
    （keep_parts 三遍 + only_outer_runs + 外沿带 + 下颌以下去青 + 开运算
    + 分区再筛）。每一层都是上一轮为了挡一个毛刺加的，叠完的结果是：

      · 帽壳只剩 9732 px 的**铁丝圈**，中间镂空，头发从帽顶透出来；
      · `hood & ~(teal & (yy > chin))` 这一句把下颌以下的**薄荷青内衬整片删掉**，
        而那两片内衬正是帽口敞开的内里、一直垂到肩线 —— 删掉它，
        切口就正好落在下颌那条水平线上，渲染出来是一道横贯脸颊的**平切痕**。
        用户第十一次打回发型/兜帽，指的就是这道痕。

    教训（LESSONS 251）：**兜帽是一块区域，不是一种颜色。**
    颜色判据只配用来找「区域的边界」，不配用来逐像素判定归属。

    新算法：两条几何事实，零颜色分类
    ------------------------------------------------------------------
    1. **下颌以上**，轮廓里只有「帽子」和「脸口」两样东西 —— 四张戴帽模板
       逐张看过，外露的头发一律在下颌以下才从帽口垂出来。
       所以  **帽壳 = 剪影 − 脸口**。白布和头发根本不用分，
       因为头发全在脸口里，而脸口是整块减掉的。

    2. **脸口** = 从脸出发、在「非内衬」区域里漫延出来的连通块。
       薄荷青内衬是一道**闭合的拱**（从左下颌绕过头顶到右下颌），
       天然就是脸口的边界。这是全套算法唯一的颜色判据，
       而薄荷青和画面里任何东西都不像，不会误判。
       种子取「下颌以上最大的皮肤连通块」= 脸，不用手填坐标。
       `dilate(teal, 9)` 既闭合罗纹之间的缝，又顺带给了 4px のりしろ
       —— 帽口内沿多盖 4px 头发，正是教程要的「塗り足し」。

    3. **下颌以下**：帽子 = 从帽口垂下来的两片薄荷青内衬
       （取连通块、必须接得上帽壳）＋ 外侧那条白外布
       （每行从剪影外缘往里填到内衬为止，左右两侧各自独立）。
       白外布**沿线稿生长**：帽子的白和夹克的白是一个颜色、分不开，
       但它们之间有一道线稿，那就是边界（教程「線画のやや外側を選択」）。
       这段白布压在底图**同一件白夹克**上，就算填宽了也看不出来；
       真正要紧的是它的外缘必须**和剪影重合**，不能在背景上留直边。

    ★ 两个必须记住的坑
      · 收尾只能 `fill_small`（填小洞），**绝不能全局 `fill_holes`**：
        白外布一填，帽口下缘就被封住，脸口从「开口」变成「内部空洞」
        被整个填实 —— pony/long 两档实测直接把整张脸切进帽子里
        （件 54697 → 90431 px）。
      · 白外布**不能按行填**。「每行从剪影外缘填到内衬为止」收口是硬生生
        一刀，肩膀上留两个白方块；而且某一行只有一侧有内衬时，
        `trow[0]` / `trow[-1]` 会落在同一侧，横贯整行拉出白色大横条。
    """
    down_p, hood_p = SHEETS[style]
    A, op_a = C.key_rgba(os.path.join(design, hood_p))
    h, w = op_a.shape
    yy = np.arange(h)[:, None] * np.ones((1, w), np.int32)

    r, g, b = A[..., 0], A[..., 1], A[..., 2]
    sil = C.fill_holes(op_a)
    teal = C.teal_like(A)
    skin = C.skin_like(A)

    # --- 1) 脸口 ------------------------------------------------------
    allowed = sil & (~C.dilate(teal, TEAL_CLOSE)) & (yy <= chin)
    faces = sorted([c for c in comps(skin & (yy <= chin) & sil) if len(c) > 2000],
                   key=len, reverse=True)
    if not faces:
        raise SystemExit("%s：下颌以上找不到脸（皮肤连通块全部 < 2000px）" % style)
    seed = np.zeros_like(op_a)
    for y, x in faces[0]:
        seed[y, x] = True
    hole = C.fill_holes(flood(seed & allowed, allowed))

    # --- 2) 下颌以上：剪影 − 脸口 --------------------------------------
    hood = sil & (yy <= chin) & (~hole)

    # --- 3) 下颌以下：垂下来的内衬 + 外侧白布 ---------------------------
    anchor = C.dilate(hood, 5)
    lining = np.zeros_like(op_a)
    for c in comps(teal & (yy > chin) & (yy <= YLIM) & op_a):
        if len(c) >= 300 and any(anchor[y, x] for y, x in c):
            for y, x in c:
                lining[y, x] = True
    lining = C.dilate(lining, 5) & op_a          # 连线稿一起带上
    hood = hood | lining

    # 白外布：**沿线稿测地生长**，不是按行填。
    # 教程原话「線画のやや外側を選択してくりぬく」—— 兜帽的白和夹克的白
    # 是同一个颜色，分不开；但它们之间有一道线稿，那就是边界。
    # 从帽壳下沿的白出发，在「白 ∧ 离线稿 3px 以外」里长到不动点，
    # 线稿自然把它挡在夹克外面，收口是布料本来的形状，没有直角、没有平切。
    # ★ 曾经用「每行从剪影外缘填到内衬为止」，收口是硬生生一刀，
    #   渲染出来是肩膀上两个白方块（logs/asset_qa 早期 hood_pieces.png 可见）。
    mx = np.maximum(np.maximum(r, g), b)
    mn = np.minimum(np.minimum(r, g), b)
    line = mx < LINE_T
    allow_w = (op_a & (mn > 140) & (~teal) & (~C.dilate(line, 3))
               & (yy > chin - 6) & (yy <= YLIM))
    sd = C.erode(hood, 3) & allow_w & (yy < chin + 14)
    gw = flood(sd, allow_w)
    if gw.sum() > WHITE_LEAK:
        # 线稿有缺口，白布一路漏进夹克。宁可少一块也不要糊一片。
        C.log("    %s：白外布生长 %d px 超过 %d，判定漏进夹克，放弃这一段"
              % (style, int(gw.sum()), WHITE_LEAK))
    else:
        hood = hood | (C.dilate(gw, 7) & op_a & (yy <= YLIM))   # 把线稿边吃回来
    hood = hood & sil
    hood = fill_small(hood, 1500)                 # ★ 只填小洞，脸口必须留着
    hood, sizes = keep_parts(hood, 1200)


    # 戴帽时帽子**没盖住**的那段头发。上边界卡在**眼线**，不是整个帽子剪影。
    #
    # ★★★ 2026-10-20 第二十三问改（原来卡在 `chin + 30`）。
    #   卡在下巴，等于把**帽口里**的头发整片排掉。可戴帽时发型档已经把
    #   `hair_side_l/r` 藏了（发型要换整颗头），它自己的鬓发件也被
    #   `hood_pose.up` 藏了 —— 脸颊两侧于是**什么都没有**，渲染出来是
    #   两个黑色三角洞（实拍 /tmp/z_twin_up.png，twin / pony / long 三档都有）。
    #   教程原话：のりしろ要伸到相邻部件**之下**。所以帽外头发必须一路
    #   补到帽口里、压在兜帽内沿底下，而不是在帽口处齐齐切断。
    #   上边界取眼线：眼线以上是刘海，底图 `hair_front` 本来就有，
    #   再切一份会和底图的刘海重影；眼线以下才是需要补的鬓发。
    hood_sil = C.dilate(row_fill(hood) & (yy <= eyeline), 5)
    # ★★★ 2026-10-22 第四十六问：帽口**里面**那段刘海要切进来。
    #   上面那条注释（第二十三问）说「眼线以上是刘海，底图 hair_front 本来就有，
    #   再切一份会和底图的刘海重影」—— 这个前提**已经不成立了**：
    #   第二十四问起，三档发型的 hide 名单里就有 `hair_front`（发型要换整颗头），
    #   而帽子立起来时自己的头壳件 `acc_hair_crown_*` 又被 `hood_pose.up` 藏掉，
    #   于是额头上**一根头发都没有** —— 实拍 logs/asset_qa/q46_hoodbangs.png：
    #   none+hood_up 有刘海，twin+hood_up 是个光额头。
    #   帽口内沿以内、不是帽布也不是皮肤的那块冷色，就是刘海，切给发片。
    inner = hood_sil & (~C.dilate(hood, 3))
    above = (yy > eyeline) | inner
    # ★ 要一条**饱和度闸**：夹克胸口那对白抽绳、夹克前襟的冷白边，
    #   都落在 `hair_like` 的弱判据里（b 比 r 高一两点）且紧挨着长发，
    #   会被召回成「头发」。头发哪怕高光处也有 10 以上的色差，白绳只有 2~4。
    sat = (np.maximum(np.maximum(r, g), b) - np.minimum(np.minimum(r, g), b))
    hairm = (op_a & C.hair_like(A) & (~teal) & (~skin)
             & (sat >= 6) & ((~hood_sil) | inner))
    hairm = C.despeckle(hairm, 5, 9)
    hairm, hsizes = keep_parts(hairm, 1500)

    # ★★★ 2026-10-20 第二十四问续：**沿线稿把发帘补成整条**。
    #   上面那条 `sat >= 6` 的闸是为了挡住胸口白抽绳，代价是把发缕上
    #   **近白的高光带**一并挡掉 —— 长发档实测被切成 9 段
    #   （/tmp/z_longparts.png：鬓发一段、胸前一段、外侧帘子又一段，
    #   中间整块亮面是空的）。用户明令「头发不许有断缺」。
    #
    #   解法和白外布同一套：**测地生长**，不是放宽颜色阈值。
    #   以上面切出来的发片作种子，在「线稿以内 ∧ 冷色 ∧ 非肤非青」里
    #   长到不动点。三条闸各有分工：
    #     · `~dilate(line, 3)` —— 教程「線画のやや外側を選択」，
    #       线稿就是发缕和夹克的边界；
    #     · `b >= r` —— 淡紫发哪怕最亮的高光也还是冷的（b−r 中位 +26~+46），
    #       而白衬衫 −31、白抽绳 −33、米白前襟 −3，一条就分开了。
    #       单靠线稿挡不住：发帘压在白前襟上，两者之间没有线。
    #       （实测不加这条，整片前襟被吃进来，件 97k → 136k，
    #        见 /tmp/z_longgrow.png。）
    #     · 下半身 `~dilate(teal, 13)` —— 袖口罗纹、下摆白条紧挨薄荷色，
    #       和发帘只隔一条很淡的线，会被顺着吃掉一长条；离薄荷 6px 以外
    #       就安全。只在 YLIM 以下生效，免得把帽口内衬边上的鬓发削掉。
    #   长发 9 段 → 5 段，剩下的 5 段是**原画本来的遮挡**
    #   （手臂压住发帘、裙子压住腿间那一缕），不是切漏。
    allow = (op_a & (~teal) & (~skin) & (~C.dilate(line, 3)) & (~hood)
             & above & (b >= r)
             & (~(C.dilate(teal, 13) & (yy > YLIM))))
    grown = flood(hairm & allow, allow) | hairm

    #   ★ 光靠生长还不够：生长的边界是**颜色阈值划出来的**，发缕背光那一侧
    #     会被撕出锯齿毛边（实拍 /tmp/z_hlsprite.png：发帘内侧像撕开的纸，
    #     而模板里它是一条光滑的缕）。贴回身上就是夹克前襟上两摊粉色碎斑。
    #     所以第二步换个层面问：**线稿把画面切成一个个格子，这个格子整体
    #     算不算头发**。判归属用颜色（格内 45% 以上是发色，或 50% 以上被
    #     上一步的生长覆盖），但**边界只由线稿决定** —— 于是边缘天然光滑，
    #     和原画完全重合。教程原话「線画のやや外側を選択してくりぬく」。
    hairish = C.hair_like(A) | ((b >= r + 4) & (sat >= 5))
    cellmask = (op_a & (~C.dilate(line, 3)) & (~hood) & (~teal) & (~skin)
                & above)
    sel = np.zeros_like(op_a)
    for c in comps(cellmask):
        if len(c) < 40:
            continue
        cy = np.array([q[0] for q in c])
        cx = np.array([q[1] for q in c])
        if hairish[cy, cx].mean() >= 0.45 or grown[cy, cx].mean() >= 0.5:
            sel[cy, cx] = True
    #   `dilate(line, 3)` 把发缕之间的分隔线连同两侧各 1px 一起挖掉了，
    #   不补回来，件里就是一条条白沟。3px 闭运算刚好把这条沟填上，
    #   外轮廓只圆 3px（不是以前那个把轮廓改方的 17 方核）。
    hairm = C.solidify(sel, 7)
    hairm = C.dilate(hairm, 3) & op_a & (~teal) & (~hood)
    hairm = hairm | (C.fill_holes(hairm) & (~hairm) & op_a)
    #   ★ 门槛别降到 300：300px 的碎屑会落在膝盖那么远的地方，
    #     内容框被它一撑就从 549x525 变成 548x1090，件白大一倍。
    hairm, hsizes = keep_parts(hairm, 1200)
    # 填洞**只填不透明的洞**：发缕之间的缝隙是洋红背景，填了会在件里糊出紫红块。
    hairm = hairm | (C.fill_holes(hairm) & (~hairm) & op_a)

    return {"A": A, "op": op_a, "hood": hood, "hair": hairm,
            "sizes": sizes, "hsizes": hsizes}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--character", default="xiaoxun")
    ap.add_argument("--form", default="teen")
    ap.add_argument("--styles", default="short,twin,pony,long")
    ap.add_argument("--debug-dir", default="")
    a = ap.parse_args()

    design = os.path.join("characters", a.character, "design")
    redraw = os.path.join(design, "redraw")
    form = os.path.join("characters", a.character, "forms", a.form)

    base_a, base_op = C.key_rgba(os.path.join(design, "design_sheet_short.png"))
    ys, xs = np.nonzero(base_op)
    bbox = (int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max()))
    scale = (C.TARGET_CANVAS[1] * C.HEIGHT_RATIO) / (bbox[3] - bbox[1] + 1)
    with io.open(os.path.join(form, "design", "anchors.json"), encoding="utf-8") as fh:
        anchors = json.load(fh)
    unit = anchors["meta"]["head_ratio"] * anchors["meta"]["height_px"]
    chin = int(round(bbox[1] + anchors["points"]["neck"][1] / scale))
    eyeline = int(round(bbox[1] + anchors["points"]["eye_line"][1] / scale))
    head_cx = (bbox[0] + bbox[2] + 1) / 2.0
    C.log("底图 bbox %s  缩放 %.6f  下巴 y=%d  眼线 y=%d（模板坐标）"
          % (str(bbox), scale, chin, eyeline))

    geom = collections.OrderedDict()
    dbg = {}
    for style in [s.strip() for s in a.styles.split(",") if s.strip()]:
        cut = cut_one(style, design, chin, eyeline, head_cx)
        dbg[style] = cut
        C.log("  %-6s 帽壳 %6d px %s   帽外头发 %6d px %s"
              % (style, int(cut["hood"].sum()), cut["sizes"],
                 int(cut["hair"].sum()), cut["hsizes"]))
        for pid, slot, key in PLAN[style]:
            mk = cut[key]
            if mk.sum() < 2000:
                C.log("    %-18s 掩膜 %d px，这一档没有这片，跳过" % (pid, int(mk.sum())))
                continue
            info = C.emit_piece(pid, mk, cut["A"], redraw, bbox, scale, unit, anchors)
            if info is None:
                continue
            info["slot"] = slot
            info["style"] = style
            geom[pid] = info
            C.log("    %-18s %-16s 内容 %dx%d  pos_rel [%+.4f,%+.4f]  h_rel %.4f"
                  % (pid, slot, info["content_px"][0], info["content_px"][1],
                     info["pos_rel"][0], info["pos_rel"][1], info["sprite_h_rel"]))

    gp = os.path.join(design, "sheets", "hood_geometry.json")
    with io.open(gp, "w", encoding="utf-8") as fh:
        json.dump({
            "_note": ("由 tools/cut_hood_from_sheets.py 量出来的兜帽件几何。"
                      "全部来自套准后的参考模板，没有一个数是手调的。"),
            "scale_sheet_to_bodyfull": round(scale, 6),
            "head_unit_px": unit,
            "pieces": geom,
        }, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    C.log("\n几何写到 %s（%d 片）" % (gp, len(geom)))

    if a.debug_dir:
        os.makedirs(a.debug_dir, exist_ok=True)
        from PIL import ImageDraw
        cells = []
        for style, cut in dbg.items():
            arr = cut["A"][:, :, :3].astype(np.uint8)
            h, w = cut["hood"].shape
            ck = (((np.arange(h)[:, None] // 16) + (np.arange(w)[None, :] // 16)) % 2)
            bg = np.where(ck[..., None] == 0,
                          np.array([70, 70, 80], np.uint8),
                          np.array([100, 100, 112], np.uint8))
            out = np.where((cut["hood"] | cut["hair"])[..., None], arr, bg)
            out = out.astype(np.uint8).copy()
            out[cut["hair"]] = (out[cut["hair"]] * 0.75
                                + np.array([90, 160, 255]) * 0.25).astype(np.uint8)
            cells.append((style, Image.fromarray(out).crop((230, 30, 820, 1240))))
        wq, hq = cells[0][1].size
        o = Image.new("RGB", (wq * len(cells), hq + 22), (20, 20, 20))
        d = ImageDraw.Draw(o)
        for i, (n, im) in enumerate(cells):
            o.paste(im, (i * wq, 22))
            d.text((i * wq + 6, 5), "%s  (blue tint = hair outside hood)" % n,
                   fill=(255, 255, 0))
        p = os.path.join(a.debug_dir, "hood_pieces.png")
        o.save(p)
        C.log("调试图 → %s" % p)
    return 0


if __name__ == "__main__":
    sys.exit(main())
