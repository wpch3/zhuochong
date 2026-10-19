#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从参考模板切发型件（T46.14）。

和老办法的区别
--------------
老办法：每个发型件都是**单独生成**的一张 AI 图（hair_twin_bunch_v2.png、
hair_pony_back_v2.png、hair_long_back_v2.png……），再靠手调的 pos_rel /
width_ratio 往头上怼。几张图之间没有任何共同约束，所以：

  · 色相对不上  → 用户说的「拼接痕迹很明显」
  · 结构对不上  → 用户说的「一坨头发缠在一起」「完全不行」

新办法：所有发型件都从 `design/sheets/sheet_<发型>.png` 这**同一张完整差分
立绘**上切下来。同一张图里的像素天然同色、同光照、同几何，拼起来没有缝。
这是 Live2D 官方工序（画师先画完整差分立绘、再拆图层）的下半截，
上半截是 `tools/register_sheets.py`（把模板套准到同一套身体坐标）。

怎么接进现有流水线
------------------
切出来的每一片，**存成洋红底的 PNG** 放进 `design/redraw/sheetcut_*.png`，
然后在 `attachments.json` 里当普通 source 引用。
这样 `make_attach_parts.py` 一行都不用改 —— 它的抠像、内部补实
（harden_interior）、@2x 高清化全程复用。

几何怎么来
----------
模板(1024x1536) → body_full 像素系 的仿射，和 prepare_sprites.py 完全一致：

    s  = 1360 * 0.95 / 底图人物高      （= 0.889195）
    bf = (sheet - 底图人物bbox左上) * s

`anchors.json` 的 points 用的就是 body_full 像素系，所以每片的
pos_rel / sprite_h_rel 都是**量出来的**，不是手调的。
注意 `_emit` 会给内容框四周各留 CROP_MARGIN，所以 sprite 高 = 内容框高 × 1.08。
"""
from __future__ import annotations

import argparse
import collections
import io
import json
import os
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

SHEET_CANVAS = (1024, 1536)
HEIGHT_RATIO = 0.95           # 与 prepare_sprites.py 的 --height-ratio 一致
TARGET_CANVAS = (848, 1360)   # 与 prepare_sprites.py 的 --canvas 一致
CROP_MARGIN = 0.04            # 与 make_manpu_parts.CROP_MARGIN 一致（_emit 用它留白）
MAGENTA = (255, 0, 255)

#: 塗り足し：back 件向身体内侧延伸多少像素（模板坐标）。
#: 依据：头左右转到极限时后发相对身体的横向位移约 0.08 个头宽
#: ≈ 22px(body_full) ≈ 25px(模板)。取 40 留足余量。
BLEED = 40

#: 每个发型切哪几片、落到哪个槽、层号多少。
#: 槽沿用 attachments.json 里已有的（见 docs/ART_PARTS.md 的层序表）。
PLAN = {
    "twin": [
        ("hair_twin_back_l", "head_side_hair", "back_l"),
        ("hair_twin_back_r", "head_side_hair", "back_r"),
        ("hair_twin_crown", "head_crown_tied", "scalp"),
    ],
    "pony": [
        ("hair_pony_back", "body_back_pony", "back"),
        ("hair_pony_crown", "head_crown_tied", "scalp"),
    ],
    "long": [
        ("hair_long_back", "body_back_hair", "back"),
        ("hair_long_crown", "head_crown_tied", "scalp"),
        ("hair_long_side_l", "head_side_long", "side_l"),
        ("hair_long_side_r", "head_side_long", "side_r"),
    ],
}


def log(m: str) -> None:
    print(m)


# ------------------------------------------------------------ 掩膜小工具
def _m(b):
    return Image.fromarray((b.astype(np.uint8)) * 255)


def _a(i):
    return np.asarray(i) > 127


def dilate(b, k):
    return _a(_m(b).filter(ImageFilter.MaxFilter(k)))


def erode(b, k):
    return _a(_m(b).filter(ImageFilter.MinFilter(k)))


def dark_junk_like(a):
    """**暗到不可能是头发**的那些像素 —— 藏青裙子、鞋底、深色线稿块。

    ★ 2026-10-19 第二十二问新增。马尾那条卷尾垂在裙子前面，切件时
      裙子的藏青 (55,64,93) 顺着发缕边缘混进了后发件；它躲得过
      `teal_like`（绿不压红）也躲得过 `skin_like`，于是原样落盘，
      渲染出来就是淡紫发缕上趴着三块**纯黑**（用户九轮里反复点名的"碎块"）。

    判据是量出来的，不是拍的：三张模板里**头发自身**像素的 max 通道
    最小值都是 **151**（p0.1 也是 151）——头发在这套配色里永远是亮的。
    取 130 当上限，离头发的下界还有 21 的余量。

    ★ 光有亮度不够，还要区分「**线稿**」和「**色块**」：
      头发自己的分缕线、发梢的描边也是暗的（紫褐 (111,76,119) 那一类），
      把它们一起重画掉，发缕之间的分界会糊成一坨。
      两者的差别是**粗细**不是颜色 —— 线稿是 1~3px 的细线，色块是实心片。
      所以先 `erode(dark, 5)` 再 `dilate` 回去：细线被腐蚀干净，
      只有**至少 5px 粗**的暗区留下来。
      实测三张模板：误伤头发**本体 0 像素**，发缘 2px 圈只碰到 0.9~2.2%。

    第一版用的是 `max<100 且 g>=r`（想用"绿压红"认藏青裙子），
    漏掉了真正的元凶 —— 马尾压在袖口上那一片的暗紫 **(75,59,103)**
    （r>g，躲过了 g>=r；max=103，躲过了 100）。改成粗细判据之后一网打尽。

    而且 `bad` 这条链路是**用邻近发色重画、不删像素**，
    最坏结果只是边缘软一点，不会挖洞。
    """
    mx = np.maximum(np.maximum(a[..., 0], a[..., 1]), a[..., 2])
    dark = mx < 130
    return dilate(erode(dark, 5), 5) & dark


def teal_like(a):
    """夹克的薄荷青 —— 哪怕落在阴影里也要认得出来。

    这是切鬓发时唯一真正难缠的干扰物。为什么不能只看"是不是青色"：

      · 平光处的袖子 (91,191,181)：绿压红 +100、蓝比绿低 10，一眼就是青的；
      · **阴影处**的袖子 (108,170,174)：绿压红还有 +62，但**蓝已经反超绿 4**。
        `hair_like` 的 `b > g - 6` 放它过去了，于是整条袖子被当成头发切下来
        （实测长发鬓发件 227x802，下半截全是袖子）。

    头发无论淡紫 (216,216,232) 还是蓝梢 (159,196,232)，**蓝都比绿高 16 以上**；
    青色无论明暗，蓝比绿最多高几点。所以判据是个二维楔形：
    **绿明显压过红（偏绿），而蓝没能明显压过绿** —— 那就是青布，不是头发。
    中性的高光（R≈G≈B）绿不压红，不会被误伤。
    """
    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    #  ★ 2026-10-19 二修：原判据 `b - g < 12` 只认得**袖子**，认不出
    #    **兜帽内衬和衣领**。实测长发后发件里按 `g-r>25` 分桶：
    #        b-g ∈ [0,12)  6061 px  典型色 (129,181,188)  ← 旧判据只抓到这桶
    #        b-g ∈ [12,25) 8138 px  典型色 (111,161,179)  ← **更大的一桶，全漏了**
    #    漏掉的这 8138 px 就是渲染图上脖子和衣领那一片深青色脏块。
    #    放宽到 25 会不会误伤蓝发梢？不会，但**必须配一条亮度闸**：
    #        蓝发梢 (159,196,232)：b-g=36，本来就在 25 以外；
    #        但阴影里的蓝发梢会往下掉，所以再加 b<210 兜底 ——
    #        衣领青 b=179 < 210 判为青布；蓝发梢 b=232 > 210 保住。
    #  ★ 再补一条 r < 150：放宽到 b-g<25 之后，**被夹克反光染绿的头发**
    #    （像 (150,185,195)）会被误伤 —— 实测 pony 鬓发覆盖率从 28.8% 掉到 17%，
    #    长发前侧两片被削掉六成。衣领青是**暗**的（r=111），反光的头发是**亮**的，
    #    用 r<150 把两者分开；旧的 b-g<12 那一支不加亮度闸（那是确凿的青布）。
    return (g - r > 30) & ((b - g < 12) | ((b - g < 25) & (b < 210) & (r < 150)))


def keep_big(m, min_px=1500, max_parts=400):
    """只留下**够大的**连通块，碎渣一律丢掉。

    和 `keep_rooted` 的分工：`keep_rooted` 要求和发根相连，适合后发/马尾
    那种一定从头上垂下来的件；但鬓发在**肩膀处会被衣服切断**
    （头发从夹克后面钻出来，中间隔着一段青布，去青色之后就断了），
    此时按"连不连得到发根"筛会把整条发缕当孤儿丢掉。
    所以这里改按**面积**筛：是不是一撮头发，看的是它有多大，不是它挂在哪。

    没有 scipy，自己做连通域：每次挑一个剩余像素当种子，在块内反复膨胀到收敛。
    为了不在 1536x1024 的整幅上跑 MaxFilter，每次先裁到剩余掩膜的 bbox。

    ★★★ 2026-10-19 第二十二问：`max_parts` 原来是 **12**，这是一条
        **静默丢件**的 bug，不是性能旋钮。种子按 `np.nonzero` 的第一个像素挑，
        也就是**从上往下**扫；只要上方先凑够 12 个连通块，循环就退出了，
        **下方剩下的块一个都不再检查，无论多大**。
        实测 sheet_pony：马尾末端那个内卷（y790~927，7415px，远超 min_px=3000）
        就是这样没的 —— 它在图上最靠下，名额早被上面的碎块用完。
        病征特别迷惑人：同一份 `back` 掩膜，按左右半边切出来的 `back_r`
        **保住了**卷尾（右半边碎块少，12 个名额够用），整片切的 `back` 丢了。
        于是双马尾（用 back_l/back_r）看着正常、马尾（用 back）尾巴少一截，
        看起来像"某个发型特有的问题"，其实是计数上限。
        现在改成**跑到 rem 为空为止**，上限抬到 400 纯粹当死循环保险，
        真顶到了就打警告 —— 宁可慢，不可无声无息地少画一块头发。
    """
    out = np.zeros_like(m)
    rem = m.copy()
    hit_cap = True
    for _ in range(max_parts):
        ys, xs = np.nonzero(rem)
        if not len(ys):
            hit_cap = False
            break
        y0, y1, x0, x1 = ys.min(), ys.max() + 1, xs.min(), xs.max() + 1
        sub = rem[y0:y1, x0:x1]
        seed = np.zeros_like(sub)
        seed[ys[0] - y0, xs[0] - x0] = True
        while True:
            grown = dilate(seed, 31) & sub
            if grown.sum() == seed.sum():
                break
            seed = grown
        if seed.sum() >= min_px:
            out[y0:y1, x0:x1] |= seed
        rem[y0:y1, x0:x1] &= ~seed
    if hit_cap and rem.any():
        log("    [警告] keep_big 连通块数顶到上限 %d，仍剩 %d px 未检查 —— "
            "可能又在静默丢件，把 max_parts 调大" % (max_parts, int(rem.sum())))
    return out


def skin_like(a):
    """底图的**皮肤**。用来把「脸前面的头发」和「脸后面的头发」分开。

    动漫肤色 (250,220,205)：R 明显最高、G 次之、B 最低，R−B 在 20~90 之间。
    米白衬衫 (250,245,235) 的 R−B 只有 15，挡在外面；
    夹克的薄荷青 G≳B，也挡在外面。
    """
    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    return (r > 195) & (r > g + 8) & (g >= b) & (r - b > 20) & (r - b < 95)


def despeckle(b, k=5, grow=7):
    """去细线噪点，但用核心把原始掩膜里挨着核心的部分**召回**。

    直接开运算会把发梢和呆毛一起削掉（实测双马尾头顶整片丢失），
    所以开完之后再按核心去召回。
    """
    core = _a(_m(b).filter(ImageFilter.MinFilter(k)).filter(ImageFilter.MaxFilter(k)))
    return dilate(core, grow) & b


def key_rgba(path):
    a = np.asarray(Image.open(path).convert("RGB")).astype(np.float32)
    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    mag = (r > 150) & (b > 150) & (g < 110) & ((r - g) > 80) & ((b - g) > 80)
    return a, ~mag


def hair_like(a):
    """发色判据：**滞后阈值**（强判据定种子，弱判据补高光）。

    单一阈值两头都堵不上，实测过：

      · `b > r + 5`（严）—— 头顶的**高光带是近中性色**（R≈G≈B），整片过不了，
        crown 件只剩 2169px，切出来是空的。
      · `b > r + 1`（松）—— 白袜子 (250,250,252) 和**白夹克的冷灰阴影**
        (约 200,205,215) 全被判成头发，底图发掩膜一路蔓延到 y=1150，
        于是长鬓发被 `~base_hair` 整条减掉。

    所以分两档：
      强 `b > r + 8`  —— 一定是头发，当种子；
      弱 `b > r + 1`  —— 包含高光，但也混进白衣服；
    取「弱判据里**离强种子 15px 以内**的部分」。高光带紧挨着实色发丝，收得进来；
    胸口那片夹克阴影离头发远，收不进来。
    """
    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    not_teal = b > g - 6          # 薄荷青是 G≳B，蓝发梢是 B>G
    strong = (b > r + 8) & (b > 120) & not_teal
    weak = (b > r + 1) & (b > 120) & not_teal
    return weak & dilate(strong, 31)


def solidify(b, k=17):
    """把"筛子一样"的颜色掩膜补成实心块。

    ★ 为什么必须有这一步：头发上的**高光是近中性色**（R≈G≈B，甚至 R>B），
      过不了 `b > r+5` 的色相判据，于是发色掩膜内部布满麻点和细缝，
      直接拿去切件，切出来的头顶是一张麻脸（实测 crown 件全是洞）。

    用**大核闭运算**（先膨胀后腐蚀）。试过两条更"正统"的路，都不行：

      · 四向围死判据（`maximum.accumulate` 那套）：全身图上会出事 ——
        袜子鞋子那点杂色和头发隔着大半张图，四向判据把它们之间
        整片身体判成"内部空洞"（twin_back_r 从 191x539 暴涨到 303x1283）。
      · PIL 的 `ImageDraw.floodfill`：**PIL 13.0.0 在 "L" 模式上一个像素都不填**
        （实测填 0 个，solidify 直接返回整张图）。自己写的边界传播是对的，
        但 200 轮 MaxFilter(63) 要 **125 秒**。

    实测 k=17 的闭运算**完全覆盖**边界传播的结果（少 0 像素），
    只多 2.7% 的圆角，耗时 1.2 秒 —— 快 100 倍且判据等价。
    头发高光造成的缝隙本来就只有十几像素宽，用不着全图洪水。
    """
    return erode(dilate(b, k), k)


def fill_holes(m):
    """补上被件**完全包住**的洞，外轮廓一个像素都不动。

    为什么需要它：收尾硬排把衣领/袖口/手从掩膜里剔掉之后，它们原来占的位置
    就成了洞。件落盘时 `where(m, rgb, MAGENTA)` 会把洞写成洋红 ⇒ 透明窟窿，
    闸门实测「露出透明背景 19.11%」。而 Live2D 官方的说法是被遮住的部分
    **必须补画**，所以这里要把洞填回去、再让 `nearest_fill` 用**周围的发色**
    给它上色（颜色源会特意排除洞本身，否则又把衣领的颜色抹回去了）。

    为什么不用 `solidify`（闭运算）补：闭运算是先膨胀再腐蚀，**会把外轮廓
    一起改圆、改方**，正是用户说的「块状、没有柔顺流线的感觉」的来源之一。
    这里改用「从画布外缘灌水」——灌不到的自由像素就是洞，外轮廓完全不受影响。
    """
    ys, xs = np.nonzero(m)
    if len(xs) == 0:
        return m
    x0, x1 = int(xs.min()), int(xs.max())
    y0, y1 = int(ys.min()), int(ys.max())
    # 只在件的 bbox + 1px 边框里灌水，省掉整张画布的迭代
    sub = m[y0:y1 + 1, x0:x1 + 1]
    pad = np.zeros((sub.shape[0] + 2, sub.shape[1] + 2), bool)
    pad[1:-1, 1:-1] = sub
    free = ~pad
    seed = np.zeros_like(pad)
    seed[0, :] = True
    seed[-1, :] = True
    seed[:, 0] = True
    seed[:, -1] = True
    seed &= free
    prev = -1
    guard = 4 * (pad.shape[0] + pad.shape[1])
    while int(seed.sum()) != prev and guard > 0:
        prev = int(seed.sum())
        seed = dilate(seed, 3) & free
        guard -= 1
    filled = ~seed                      # 灌不到的 = 件本体 + 洞
    out = m.copy()
    out[y0:y1 + 1, x0:x1 + 1] = filled[1:-1, 1:-1]
    return out


def nearest_fill(rgb, src, steps):
    """把 src 为真处的颜色向外扩散（最近邻补色），用于塗り足し。

    返回 `(out, have)` —— **第二个返回值是真正被填到的集合**，必须拿它去定
    塗り足し的范围，不能另外用 `dilate(src, 2*steps+1)` 圈。两者不是一回事：
    这里的颜色只沿 4 邻域传播（曼哈顿距离），而 dilate 是 3x3（切比雪夫距离），
    于是**对角方向上有一圈像素被圈成了实心、却从来没被填过色**，
    保留着原图在那个位置的内容（线稿、眼睛、藏青裙子）——
    画面上就是发束根部那几块突兀的黑色楔形。（2026-10-19 实测）
    """
    out = rgb.copy()
    have = src.copy()
    for _ in range(steps):
        grown = dilate(have, 3)
        new = grown & ~have
        if not new.any():
            break
        acc = np.zeros_like(out)
        cnt = np.zeros(out.shape[:2], np.float32)
        for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            acc += np.roll(np.where(have[..., None], out, 0.0), (dy, dx), (0, 1))
            cnt += np.roll(have, (dy, dx), (0, 1)).astype(np.float32)
        ok = new & (cnt > 0)
        if not ok.any():
            break
        out[ok] = acc[ok] / np.maximum(cnt[ok], 1.0)[:, None]
        have = have | ok
    return out, have


def keep_rooted(m, root_rows=40):
    """只保留从**发根**连通出去的那一块，丢掉游离碎片。

    切件难免留下几块和主体不相连的碎屑（套准残留、模板上别处的同色物件）。
    它们本身像素不多，despeckle 也滤不掉（够厚），但**会把件的 bbox 撑大**，
    于是在画面上变成一块浮在身体旁边的灰方块（实测马尾右肩外侧那块）。

    发根一定在件的最上面几行（后发/马尾/双马尾都是从头上垂下来的），
    所以拿最上面 root_rows 行当种子，在掩膜内部反复膨胀到收敛。
    没有 scipy，这是最省事的连通域。
    """
    ys = np.nonzero(m.any(axis=1))[0]
    if not len(ys):
        return m
    seed = m & (np.arange(m.shape[0])[:, None] <= ys[0] + root_rows)
    if not seed.any():
        return m
    while True:
        grown = dilate(seed, 9) & m
        if grown.sum() == seed.sum():
            return grown
        seed = grown


# ------------------------------------------------------------ 切掩膜
def cut_masks(style, design, base_a, base_op, hairline, eyeline, head_cx,
              kneeline, shoulder, chinline, headw, skin):
    sp = os.path.join(design, "sheets", "sheet_%s.png" % style)
    sa, sop = key_rgba(sp)
    yy0 = np.arange(SHEET_CANVAS[1])[:, None] * np.ones((1, SHEET_CANVAS[0]), np.int32)

    # ★ 底图发掩膜按**肩线**截断。原因：白夹克的冷灰阴影（约 200,205,215）
    #   在色相上**就是发色**，颜色判据分不开（实测底图发掩膜一路蔓延到 y=1152，
    #   于是长鬓发被 `~base_hair` 整条减掉）。但底图是短发——按定义不可能有
    #   头发垂到肩线以下，所以这里用几何约束，比继续调颜色阈值可靠。
    bh_all = solidify(despeckle(hair_like(base_a) & base_op & (yy0 <= shoulder))) & base_op
    # 膝盖线兜底：头发再长也到不了小腿。不设这条线的话，
    # 白袜子和球鞋高光会被当成发色参与补实。
    sh_all = solidify(despeckle(hair_like(sa) & sop & (yy0 <= kneeline))) & sop

    # 这个发型相对短发改了哪些像素。阈值 18：淡紫发压在白夹克上最大通道差只有 34。
    diff = (np.abs(sa - base_a).max(axis=2) > 18) & sop
    # ★ 差分只用来圈**范围**，不用来当掩膜。
    #   平涂区域两张图颜色一样，diff 近乎 0；拿 diff 当掩膜切出来是镂空的
    #   （实测长鬓发只剩阴影部分）。先把稀疏的 diff 膨胀成实心块当"改动区"，
    #   再在这个区里取**实心的发色掩膜**，才是件该包含的像素。
    region = dilate(despeckle(diff, 3, 5), 21)

    yy = np.arange(SHEET_CANVAS[1])[:, None] * np.ones((1, SHEET_CANVAS[0]), np.int32)
    xx = np.ones((SHEET_CANVAS[1], 1), np.int32) * np.arange(SHEET_CANVAS[0])[None, :]

    #   整张**脸**（含五官）。头壳要减它，后发件在头部那一段也要减它。
    #   先按下巴线截断再闭运算 —— 肤色遍布全身，不截的话会一路长到脚踝。
    face = solidify(skin & (yy0 <= chinline), 61) & (yy0 <= chinline)

    out = {}
    # ① 剪影之外的新头发 —— 后发 / 尾巴。
    #    ★ 这里**不加颜色判据**：短发剪影之外本来就是空的，模板在那里画了东西，
    #      就只可能是头发。加 sh_all 反而会被高光带打出洞。
    #    套准残留会在身体轮廓外留一圈 1~3px 的描边，必须用 despeckle 滤掉，
    #    否则整条身体边缘都会被当成"剪影外的新头发"（实测件高涨到全身 1453px）。
    #    ★ 剪影外也要硬排**薄荷青**和**肤色**。套准做到亚像素级了，但模板和底图
    #      在肩头、手背这些地方仍有几像素的差，于是夹克领子和手指会沿着剪影
    #      外缘漏出一小条 —— 它们随后被 `nearest_fill` 的塗り足し当作颜色源
    #      往里扩散 40px，在件里画出一圈青色衣领和肉色手指（件在层 57/58
    #      被身体挡着，静止时看不见，**一摆动就露馅**）。
    outside = despeckle(sop & ~dilate(base_op, 5) & (yy <= kneeline)
                        & ~teal_like(sa) & ~skin_like(sa), 9, 11)
    #    ★★ 只取"剪影之外"是**错的**，这是「拼接痕迹」的头号来源。
    #       底图剪影是**短发**的身体轮廓。双马尾/马尾垂下来的时候会压在肩膀和
    #       手臂上 —— 那一段落在剪影**之内**，于是被 `~dilate(base_op,5)` 剜掉，
    #       件上出现一串大洞；紧接着 `nearest_fill` 去补这些洞，从几十像素外
    #       抓颜色，补出一条条横向拖影。实测源切片 `sheetcut_hair_pony_back.png`
    #       整条尾巴中段都是这种拖影（见 2026-10-19 的 /tmp/src.png）。
    #       这些件在层 57/58/160，本来就画在身体**后面**，多画的部分会被身体盖住，
    #       所以"剪影内的那一段"直接补进来即可，没有任何副作用。
    #       ★ 补进来的这一段**只取下巴以下**。头部那一圈不能补：那里要减掉
    #         底图自己的头发(`~dilate(bh_all,5)`)，减完会在发际线附近留下一串
    #         孤立碎片，而 `keep_rooted` 的种子取的是掩膜最上面 40 行 ——
    #         种子正好落在这些碎片上，于是下面整条头发被当成"没生根"丢光
    #         （实测长发后发件从 594x989 缩成 301x451）。
    inside_new = (hair_like(sa) & ~teal_like(sa) & sop & region
                  & (yy > chinline) & (yy <= kneeline))
    back = solidify(despeckle(outside | inside_new, 3, 7), 17) & sop
    # ★ 碎片过滤要在**并上头皮之前**做。顺序反了的话，长发的头皮和它外侧的
    #   发丝之间只要有一两像素的缝，keep_rooted 就会把下面整条头发全丢掉
    #   （实测件从 594x1005 缩成 155x137，只剩一个头盖骨）。
    #    ★ 改按**面积**筛而不是按"连不连得到发根"筛。补进剪影内的那一段之后，
    #      件在肩膀处可能被衣服分成两段（上面是从头垂下的、下面是压在手臂上的），
    #      按发根筛会把下半段整条丢掉。
    out["back_l"] = keep_big(back & (xx < head_cx), 3000)
    out["back_r"] = keep_big(back & (xx >= head_cx), 3000)
    back = keep_big(back, 3000)
    if style == "long":
        # ★ 披发这一档还要带上**后脑那片头皮**。只取"剪影之外"的话，
        #   件是从耳朵高度才开始的，上面空着一截 —— 藏掉本体的齐腮鬓发之后
        #   那里背后没东西垫，露出透明背景（闸门实测 3.04%，上限 2%）。
        #   件在层 58（整个身体之后），头皮这块本来就被脑袋挡着，多画无害；
        #   而且这才是 Live2D 里「後ろ髪」该有的样子 —— 它是从发旋开始的一整片，
        #   不是半路接上去的一截。扎发那两档不能这么做：它们是左右两件，
        #   各自带一片头皮会在脑后重叠。
        #   ★ 要减掉脸：`sh_all` 是闭运算过的发掩膜，蓝眼睛和鲸鱼发夹都过得了
        #     发色判据，不减的话件里会躺着一张脸（层 58 看不见，但一样是脏的）。
        back = back | (sh_all & dilate(base_op, 9) & (yy <= shoulder)
                       & ~dilate(face, 11))
    out["back"] = back
    out["_base_hair"] = bh_all

    # ② 剪影之内、底图那里没发、模板这里有发 —— 画在身体和脸上的新头发
    front = despeckle(sop & base_op & sh_all & ~dilate(bh_all, 5), 3, 7)
    out["front_l"] = front & (xx < head_cx)
    out["front_r"] = front & (xx >= head_cx)

    # ③ 眼线以上、改动区内的整片头顶 —— 扎起来之后变了形的头顶。
    #    用户说过四轮「扎发造型头顶必须跟着变」，只加尾巴 = 短发挂挂件。
    #    取实心（sh_all）而不是 diff，范围由 region 限定，所以不会把没改的刘海也换掉。
    # ③ 头壳：模板里**整颗头上的头发**，去掉盖在脸上的那部分。
    #    ★ 这一件是这轮的重点。上一版只切了「发际线以上一小块」，
    #      底图那颗短发的后脑壳（hair_back，层 170）和齐腮鬓发原封不动留着，
    #      于是画面上是「一颗短发脑袋 + 挂了两根辫子」——
    #      用户原话「短发的造型和双马尾合在一起了，非常不对劲」。
    #      用户已经重复五轮的「**发型是整体**」说的就是这个：
    #      前髪 / 横髪 / 後ろ髪要一起换，不能只加不减。
    #    ★ 为什么减掉 `skin`：脸前面的头发要放在**眼睛之上**的层（245/246），
    #      脸后面的头发放在**眼睛之下**的层（187~189）。同一件横跨两边的话，
    #      要么盖住眼睛（第十一问判过死），要么鬓发被脸压住。
    #      所以这里按"盖没盖住皮肤"把它劈成两件，各走各的层。
    #    ★ 要减掉的是整张**脸**，不是"皮肤"。只减皮肤的话，眼睛（蓝虹膜）、
    #      眉毛、嘴都留在里面 —— 蓝虹膜 B 远大于 R，**过得了发色判据**，
    #      于是头壳件里赫然躺着两只眼睛（实测，见 /tmp/chk.png 那一版）。
    #      `solidify(skin, 61)` 用大核闭运算把五官的洞填回脸里，得到整张脸。
    #    ★ 下界收到下巴线（不再 +40），否则会吃到衣领的薄荷青。
    #      （先按下巴线截断再闭运算 —— 肤色遍布全身，手和腿也是肤色，
    #        不截的话"脸区"会一路长到脚踝，把整条鬓发都减掉。）
    #    ★ 头壳**不用发色判据**，改用「头部剪影减去脸」。
    #      理由：滞后阈值出来的掩膜天生是带孔的（高光是近中性色，`weak` 够不着），
    #      `despeckle` 只去小岛、不补大孔，直接落盘就是一张斑驳的白板
    #      —— 这正是上一刀渲染出来头顶一块白补丁的原因。
    #      而在"下巴以上 + 身体剪影以内"这个框里，画面上除了脸就只有头发：
    #      耳朵是皮肤（已并进 face），脖子在下巴以下，衣领更在下面。
    #      所以直接取剪影即可，**实心、无孔、一次成型**。
    #      `erode(sop, 5)` 是为了啃掉套准后留在剪影外缘的 2~3px 洋红毛边。
    scalp = erode(sop, 5) & dilate(base_op, 9) & (yy <= chinline) & ~dilate(face, 11)
    scalp = despeckle(scalp, 5, 9)
    #    ★ 顶部要避开呆毛 —— 它在层 190 有自己的物理摆链，件里再带一根静止的，
    #      一甩头就会露出两根。取**首个宽度 ≥60px 的扫描行**当颅顶，
    #      上面那根独苗就是呆毛。
    widths = scalp.sum(axis=1)
    rows = np.nonzero(widths >= 60)[0]
    if len(rows):
        scalp = scalp & (yy >= rows[0])
    #    ★ 下巴**稍下**那一截也要带上：底图的齐腮鬓发(hair_side_l/r)下沿在下巴
    #      以下，三档都把它藏了，件只切到下巴线的话那一小段没人接管
    #      （闸门实测 pony 左侧接管率只有 27%，下限 45%）。
    #      这一段不能再用"剪影减脸"的实心法（下面是脖子和衣领，会被整片切进来），
    #      所以改用发色判据 + 硬排薄荷青。
    jaw = (dilate(base_op, 9) & (yy > chinline) & (yy <= chinline + 80)
           & hair_like(sa) & ~teal_like(sa))
    scalp = scalp | despeckle(jaw, 3, 7)
    out["scalp"] = scalp

    # ④ 鬓发：剪影**之内**、脸两侧垂下来的那两缕（长发档一路垂到胸口）。
    #    上界取发际线下方一点（底图的 hair_side_* 从那里开始，要能接上，
    #    不然藏掉本体鬓发之后那一段会空出来）；
    #    横向留出 0.22 个头宽的中心带，把刘海本体让给原件（它在层 240 没变过）。
    #    不需要防眼睛：眼睛那里 sh_all 本来就是 false（眼睛不是头发）。
    #    ★ 避开刘海只在**眼线以上**做。原来按"离中线 0.22 个头宽"一刀切，
    #      结果把鬓发本身切断了 —— 模板里鬓发是贴着太阳穴往下走的，
    #      上半截离中线很近（实测长发右侧只剩 23x47）。
    #    ★ 上界改成**下巴线**（原来是发际线 +40）。下巴以上已经由上面那块
    #      实心头壳整片接管了，再切一遍只会制造一条横缝；而且头壳在层 187~189、
    #      鬓发在 247~251，同一片像素画两遍、还跨着眼睛层，接缝必然看得见。
    #      所以这一件现在只管**下巴以下**：长发垂到胸口的那两缕。
    #      留 15px 和头壳叠一叠，免得中间漏出一条背景。
    side_top = chinline - 15
    #    ★ 下界按档位分：扎起来的发型，脸侧只剩到下巴的短鬓；
    #      披着的长发才一路垂到胸口。
    side_bottom = kneeline if style == "long" else chinline + 60
    #    ★ 下巴以下必须再过一道「这里到底改没改」的闸。原因：白夹克的冷灰阴影
    #      在色相上就是发色，而它和发缕**是连着的**，keep_rooted 拦不住 ——
    #      上一版切出来的长鬓发，下半截是一整块夹克（实测 218x770 里有一半是
    #      青灰色的袖子）。下巴**以上**不能用这道闸：那里底图本来就有头发，
    #      发压发的 diff 近乎 0，一交就把鬓发上半截切没了（LESSONS 232）。
    #      下巴**以下**底图是衣服，模板只要画了头发，diff 必然显著
    #      （淡紫发 216,216,232 vs 白夹克 250,245,235，最大通道差 34）。
    #    ★ 不能用 `sh_all`（它是 solidify 过的）：闭运算会把发缕**之间**那几道
    #      青色缝一起糊死，整条袖子当场变成头发。这里用未闭运算的原始发色掩膜，
    #      只在最后补一次小孔。
    side = hair_like(sa) & sop & region & (yy > side_top) & (yy <= side_bottom)
    side = solidify(despeckle(side, 3, 7), 9) & sop
    #    ★ 开运算 k=7：抹掉袖口、手指那些 3~4px 的描边线。它们不是青色
    #      （深灰），躲得过 teal_like，但闭运算把它们并进了大块里。
    side = dilate(erode(side, 7), 7)
    #    ★ 求连通要在**不受剪影限制**的掩膜上做，最后再与剪影相交。
    #      反过来的话，发缕只要有一段跑到底图剪影之外（模板的头发比底图的头宽，
    #      一定会有），keep_rooted 就在那里断掉、下面整条丢光。
    #      顺带白捡一条好处：白夹克那些被误判成发色的冷灰阴影和头发不连通，
    #      这一步自动把它们剔掉了，不用再去调颜色阈值。
    #    ★ 三步的**顺序**是踩出来的，不能换：
    #      ① 先在**还带着青色**的掩膜上求连通 —— 发缕是从夹克后面钻出来的，
    #         中间隔着一段肩部青布，先去青色再求连通，整条发缕会被当孤儿丢掉；
    #      ② 再去青色；
    #      ③ 最后按**面积**筛，不是按"连不连得到发根"筛 —— 去完青色，
    #         发缕和头之间本来就断开了（那一段确实被衣服挡着）。
    #      ★ 2026-10-19 第二十问补一刀：**开运算必须排在"去青"之前**。
    #        原来的顺序是「去青 → 开运算」，而发缕穿过夹克肩部那一段是跟青布
    #        **交织**的（实测 sheet_long 那一带每行 36 个发像素、32 个青像素）。
    #        去完青，发缕在那一段碎成几条几像素宽的细丝，紧跟着的开运算 k=9
    #        把细于 9px 的一律抹平 —— **整条发缕被拦腰切断**。
    #        落到成品上就是 sheetcut_hair_long_side_l 第 119~153 行整行纯洋红，
    #        渲染出来两侧的头发垂到胸口就齐刷刷断掉、下面悬空
    #        （用户第二十问截图「甚至有地方没有链接到」）。
    #        参考图 sheet_long 里这条发缕是**完整连续**的，所以这不是原画的问题。
    #      改成「开运算 → 去青 → 闭运算」：开运算作用在**完整**的发缕上，
    #        不会截断；去青只挖掉混进来的青像素；最后用同样口径的闭运算
    #        把去青留下的细缝接回去（发缕本来就该是实心的一条）。
    for key, half in (("side_l", xx < head_cx), ("side_r", xx >= head_cx)):
        m = keep_rooted(side & half) & dilate(base_op, 7)
        m = dilate(erode(m, 9), 9)          # 开：去碎渣（此时发缕还是完整的）
        m = m & ~teal_like(sa)              # 去青：只挖青像素
        m = erode(dilate(m, 9), 9) & ~teal_like(sa)   # 闭：把去青造成的细缝接回去
        m = keep_big(m, min_px=1500)
        #    件太小就干脆不要：扎发那两档下巴以下压根没有前发，
        #    勉强切出来的那点东西全是衣领碎渣。
        out[key] = m if m.sum() >= 3000 else np.zeros_like(m)

    # ⑤ 头顶：**用几何圈区域、区域内全取**，同样不加颜色判据。
    #    颜色判据在这里必败 —— 头顶高光是成片的近中性色带（不是细缝），
    #    闭运算填不上，切出来一张麻脸（实测 crown 件全是大块空洞）。
    #    而眼线以上、头部横向范围内，画面上除了头发没有别的东西；
    #    就算多盖到一点额头，件在层 239、刘海在 240，也被盖住。
    #    ★ 下界必须切在**发际线**，不能切到眼线：头顶件在层 239，而眼睛在
    #      211~234、刘海在 240 —— 切到眼线会把眼睛整个盖住（硬伤，见第十一问）。
    #      发际线以下交给底图原有的刘海件，塗り足し再向下延 40px 藏在刘海后面。
    crown = sop & dilate(base_op, 9) & (yy <= hairline + 24) & (np.abs(xx - head_cx) <= 170)
    #    ★ 上界要切在**颅顶**，把呆毛让出去：呆毛是独立部件（层 190）、挂着自己的
    #      摆动物理，被层 239 的头顶件盖住就不动了，而且两根呆毛画得稍有出入
    #      就会露出双影。判据用"第一条宽度 ≥60px 的扫描行" —— 呆毛是一根
    #      ~25px 的细尖，颅顶是 220px 的圆顶，这条线把两者分得干干净净。
    rows = crown.sum(axis=1)
    wide = np.nonzero(rows >= 60)[0]
    if len(wide):
        crown = crown & (yy >= int(wide[0]))
    out["crown"] = crown

    # ------------------------------------------------------------------
    # ⑥ ★ 收尾：统一硬排杂物 + 连通筛（2026-10-19 加）
    #
    #    依据是 ClipStudio 官方那篇「把一张合并图层的成品图切成 Live2D 部件」
    #    和 castcraft 的检查清单，两处都写了同一件事：
    #        「すべてのパーツを結合したあとは、**ゴミが残っていないかチェック**
    #          してから書き出しましょう」
    #    —— 切完**必须**再查一遍有没有残渣，这一步是工序的一部分，不是可选项。
    #
    #    为什么非要放在最后、而不是在各自的掩膜里排：
    #      · 上面每一片都各自排过青色了，但排的是**输入**掩膜；
    #        之后还要走 solidify / dilate-erode / despeckle，
    #        闭运算会把排掉的像素**重新圈回来**（它只看形状不看颜色）。
    #      · 而 `emit_piece` 取塗り足し的颜色源是 `erode(m, 3)` ——
    #        只要掩膜里混进一个衣领像素，它就会被当成颜色源往外扩散 40px，
    #        在件里画出一整片衣领形状。实测长发后发件里混进了
    #        衣领 + 兜帽 + 两只袖口 + 两只手，外加满屏横向涂抹带。
    #    所以硬排必须是**形态学之后、落盘之前**的最后一道。
    #
    #    排完会打碎出一堆孤儿碎片（原来靠衣领连在一起的发缕），
    #    再过一遍 `keep_big` 收掉 —— 这些碎片正是渲染图上那些「杂毛」。
    #    ★ 2026-10-19 二修：杂物分**两类**处理，不能一律删。
    #      · 离主体远的独立碎片（衣领色块、半只手）⇒ **删掉**，那是真垃圾；
    #      · 紧贴着头发、嵌在件**内部或边缘**的杂物（压在发丝下的衣领）⇒
    #        **保住形状、只换颜色**。
    #      为什么不能也删：删了之后件的边缘会被啃出一个**开口的缺口**
    #      （不是封闭的洞，所以 `fill_holes` 的灌水法抓不到），落盘就是
    #      透明窟窿 —— 闸门实测「露出透明背景 19.11%」，上限才 2%。
    #      而这正是 Live2D 官方 PSD 教程反复强调的那件事：
    #      被别的东西遮住的部分**要补画**，不是留空。
    #      所以这里只把远碎片剔掉，贴身杂物留在掩膜里，
    #      由 `emit_piece` 拿**干净发色**把它重画一遍（见那边的 `bad` 参数）。
    bad = teal_like(sa) | skin_like(sa) | dark_junk_like(sa)
    for key in list(out.keys()):
        m = out[key]
        if m is None or not m.any():
            continue
        before = int(m.sum())
        core = keep_big(m & ~bad, min_px=800)      # 干净头发的主体
        if not core.any():
            continue
        m2 = m & dilate(core, 3)                   # 保形：贴着主体的杂物留下
        after = int(m2.sum())
        #    安全阀：万一判据误伤导致件几乎没了，就保留原件并报警，
        #    宁可留点脏东西，也不要交一个空件上去（空件 = 发型直接消失）。
        if after < before * 0.35:
            log("    [警告] %s 硬排后只剩 %d/%d(%.0f%%)，判据可能误伤，保留原件"
                % (key, after, before, 100.0 * after / max(before, 1)))
        else:
            if after != before:
                log("    %s 去掉远碎片 %d → %d (剔 %d px)；贴身杂物 %d px 保形重画"
                    % (key, before, after, before - after, int((m2 & bad).sum())))
            out[key] = m2
    out["_bad"] = bad
    return sa, sop, out


# ------------------------------------------------------------ 落盘
def emit_piece(pid, mask, sa, redraw, bbox, scale, unit, anchors, bleed_into=None, bad=None):
    """把一片掩膜裁成洋红底 PNG，并算出 pos_rel / sprite_h_rel。"""
    if mask.sum() < 400:
        return None
    rgb = sa
    m = mask
    #  ★ 先把嵌在件里的杂物（衣领/袖口/手）用**周围的干净发色**重画掉。
    #    形状一个像素都不改 —— 改形状会啃出透明缺口，见 cut_masks 收尾那段注释。
    #    颜色源特意排除杂物本身，否则等于把衣领的颜色又抹回去。
    #    ★ 2026-10-19 第二十二问：取色源还要再排掉**线稿**。
    #      原来只排 `bad`（青布/皮肤/暗色块），剩下的"干净头发"里混着
    #      发缕之间那些暗紫分缕线 (75,59,103)。`nearest_fill` 是**最近邻**，
    #      一块被重画的区域只要最近的干净像素恰好是条线稿，整片就被刷成
    #      那个暗紫 —— 实测马尾压在袖口上那一片（源切片局部 x150 y690 一带）
    #      被刷出 100px/格 的实心暗块，渲染出来就是卷尾上趴着的几粒"黑渣"。
    #      画师口径同源（CLIP STUDIO 官方 making，森倉円）：补画发丝要
    #      「髪色の**明るいところや暗いところから**スポイトして描く」——
    #      取的是**发色**的明暗两端，不是描线的颜色。
    #      阈值取 **150**：三张模板里头发本体像素的 max 通道最小值都是 **151**，
    #      `< 150` 的发身像素实测 **0 个** —— 所以这条等价于
    #      「取色源必须是**真正的发色像素**」，而不是"躲开很暗的东西"。
    #      （第一版设 130，漏掉了 (102,82,147) 这种**实心紫**块：max=147 刚好
    #        卡在 130 和 151 之间，被当成合法发色拿去当源，往外抹了一大片；
    #        再经 `recolor_match` 的 Lab 统计匹配拉伸对比，落到画面上就是
    #        (60,59,85) 的**纯黑渣**。查的时候要盯**补色的源**，不是模板那一点的颜色。）
    #      留了兜底：排完要是没源了，就退回只排 bad。
    line_art = np.maximum(np.maximum(sa[..., 0], sa[..., 1]), sa[..., 2]) < 150
    if bad is not None and (m & bad).any():
        dirty = m & bad
        src = erode(m & ~bad & ~line_art, 3)
        if not src.any():
            src = erode(m & ~bad, 3)
        if src.any():
            probe = dirty.copy()
            rad = 0
            while probe.any() and rad < 200:
                probe = erode(probe, 3)
                rad += 1
            rgb, _ = nearest_fill(sa, src, rad + 8)
            log("    %s 杂物重画 %d px（最深 %d px）" % (pid, int(dirty.sum()), rad))
    if bleed_into is not None:
        # 塗り足し：往身体内侧长 BLEED px，补上最近邻颜色。
        # Live2D 官方：被遮住的部分必须补画，否则一动起来就 disconnected。
        #
        # ★ 颜色的**源**要先往里收 1px。掩膜最外面那一圈像素是头发和白夹克
        #   在原图上的**混色**（抗锯齿），拿它当源会把一圈白边扩散出去
        #   （实测 hair_long_back@2x 白边 1369px，闸门上限 900）。
        #   收 1px 之后那一圈自己也变成"待填"，会被里面干净的发色盖掉。
        # ★ 先补洞：硬排杂物留下的窟窿要用**周围的发色**填回来。
        #   颜色源 `erode(m, 3)` 取的是**补洞之前**的掩膜 —— 洞里原本是
        #   衣领/袖口/手，拿它当源就等于把杂物的颜色又抹回去了。
        holed = fill_holes(m)
        holes = holed & ~m
        # ★ 同上：塗り足し往外长的颜色也不许从线稿上取，否则件的外沿
        #   会拖出一圈暗紫。排完没源了就退回原来的口径。
        src = erode(m & ~line_art, 3)
        if not src.any():
            src = erode(m, 3)
        steps = BLEED + 1
        if holes.any():
            # 洞要靠最近邻一圈圈爬进去，步数不够的话洞心会留洋红。
            # 按洞的最大半径估步数：反复腐蚀直到洞消失，次数即半径。
            probe = holes.copy()
            rad = 0
            while probe.any() and rad < 200:
                probe = erode(probe, 3)
                rad += 1
            steps = max(steps, rad + 8)
        rgb, filled = nearest_fill(rgb, src, steps)
        m = holed | (filled & bleed_into)

    ys, xs = np.nonzero(m)
    x0, x1, y0, y1 = int(xs.min()), int(xs.max()), int(ys.min()), int(ys.max())
    sub = np.where(m[y0:y1 + 1, x0:x1 + 1, None],
                   rgb[y0:y1 + 1, x0:x1 + 1],
                   np.array(MAGENTA, np.float32))
    Image.fromarray(sub.astype(np.uint8), "RGB").save(
        os.path.join(redraw, "sheetcut_%s.png" % pid))

    cw, chh = x1 - x0 + 1, y1 - y0 + 1
    # _emit 会给内容框四周各留 CROP_MARGIN ⇒ sprite 高 = 内容框高 × (1+2m)
    sprite_h = chh * (1.0 + 2.0 * CROP_MARGIN) * scale
    cx = ((x0 + x1 + 1) / 2.0 - bbox[0]) * scale
    cy = ((y0 + y1 + 1) / 2.0 - bbox[1]) * scale
    ref = "head_top"
    rx, ry = anchors["points"][ref]
    return {
        "sprite_file": "sheetcut_%s.png" % pid,
        "ref": ref,
        "pos_rel": [round((cx - rx) / unit, 6), round((cy - ry) / unit, 6)],
        "sprite_h_rel": round(sprite_h / unit, 6),
        "width_ratio": 1.0,
        "px": [x0, y0, x1, y1],
        "content_px": [cw, chh],
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--character", default="xiaoxun")
    ap.add_argument("--form", default="teen")
    ap.add_argument("--styles", default="twin,pony,long")
    ap.add_argument("--debug-dir", default="")
    a = ap.parse_args()

    design = os.path.join("characters", a.character, "design")
    redraw = os.path.join(design, "redraw")
    form = os.path.join("characters", a.character, "forms", a.form)

    base_p = os.path.join(design, "design_sheet_short.png")
    base_a, base_op = key_rgba(base_p)
    ys, xs = np.nonzero(base_op)
    bbox = (int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max()))
    char_h = bbox[3] - bbox[1] + 1
    scale = (TARGET_CANVAS[1] * HEIGHT_RATIO) / char_h

    with io.open(os.path.join(form, "design", "anchors.json"), encoding="utf-8") as fh:
        anchors = json.load(fh)
    unit = anchors["meta"]["head_ratio"] * anchors["meta"]["height_px"]

    # 发际线 / 眼线 / 头心，换算回模板坐标
    hairline = int(round(bbox[1] + (163 - 68) / scale))
    eyeline = int(round(bbox[1] + anchors["points"]["eye_line"][1] / scale))
    head_cx = (bbox[0] + bbox[2] + 1) / 2.0
    kneeline = int(round(bbox[1] + anchors["points"]["knee"][1] / scale))
    shoulder = int(round(bbox[1] + anchors["points"]["shoulder"][1] / scale))
    chinline = int(round(bbox[1] + anchors["points"]["neck"][1] / scale))
    skin = skin_like(base_a) & base_op
    # 头宽 = 发际线~眼线之间最宽的那一行（底图剪影）
    _rows = base_op[hairline:eyeline + 1]
    headw = 1
    for r in _rows:
        ix = np.nonzero(r)[0]
        if len(ix):
            headw = max(headw, int(ix[-1] - ix[0]))

    log("底图人物 bbox %s 高 %d → body_full 缩放 %.6f" % (str(bbox), char_h, scale))
    log("head unit %.1fpx  发际线 y=%d  眼线 y=%d  头心 x=%.1f（模板坐标）\n"
        % (unit, hairline, eyeline, head_cx))

    yy_all = (np.arange(SHEET_CANVAS[1])[:, None]
              * np.ones((1, SHEET_CANVAS[0]), np.int32))
    geom = collections.OrderedDict()
    dbg = {}
    for style in [s.strip() for s in a.styles.split(",") if s.strip()]:
        sa, sop, masks = cut_masks(style, design, base_a, base_op,
                                   hairline, eyeline, head_cx, kneeline,
                                   shoulder, chinline, headw, skin)
        dbg[style] = masks
        for pid, slot, key in PLAN[style]:
            mk = masks[key]
            # 塗り足し往哪里长，取决于这件**在不在身体前面**。
            #   · body_back_* (层 57/58) 在整个身体之后 ⇒ 补到哪儿都被挡住，
            #     可以沿着整个人物剪影补，接缝藏得最干净。
            #   · head_side_hair (层 160/161) 在手臂(143)和躯干(100)**之上** ⇒
            #     补到肩膀上就直接画在夹克上了。实测双马尾两束根部的肩头
            #     各糊着一块灰方块，就是这么来的。这一档只许补到**肩线以上**
            #     （那里有后发壳 170 和头壳 180 压在上面，藏得住）。
            if not key.startswith("back"):
                bleed = None
            elif slot == "head_side_hair":
                # 这一档在手臂(143)/躯干(100)**之上**，补到衣服上就直接看见了。
                # 「肩线以上」还不够紧 —— 下巴到肩膀之间是裸露的脖子和衣领，
                # 实测两束发根的肩头各糊着一块横向涂抹的深灰（线稿颜色被
                # nearest_fill 推出去 40px 的结果）。
                # 收紧成「只补到**底图自己的头发**底下」：那块区域必定被
                # hair_back(170) / seg_head(180) / hair_side(245,246) 压住，
                # 一个像素都露不出来，而塗り足し要的"动起来别断开"照样满足。
                bleed = dilate(masks["_base_hair"], 5)
            else:
                bleed = dilate(base_op, 3)
            info = emit_piece(pid, mk, sa, redraw, bbox, scale, unit, anchors, bleed,
                              bad=masks.get("_bad"))
            if info is None:
                log("  %-20s %-18s 掩膜太小(%d px)，跳过" % (pid, slot, mk.sum()))
                continue
            info["slot"] = slot
            geom[pid] = info
            log("  %-20s %-18s 内容 %dx%d  pos_rel [%+.4f,%+.4f]  h_rel %.4f"
                % (pid, slot, info["content_px"][0], info["content_px"][1],
                   info["pos_rel"][0], info["pos_rel"][1], info["sprite_h_rel"]))

    gp = os.path.join(design, "sheets", "cut_geometry.json")
    with io.open(gp, "w", encoding="utf-8") as fh:
        json.dump({
            "_note": ("由 tools/cut_from_sheets.py 量出来的发型件几何。"
                      "全部来自参考模板，没有一个数是手调的 —— "
                      "手调常数本来就是在替\"碎片之间没有共同约束\"擦屁股。"),
            "scale_sheet_to_bodyfull": round(scale, 6),
            "head_unit_px": unit,
            "pieces": geom,
        }, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    log("\n几何写到 %s（%d 片）" % (gp, len(geom)))

    if a.debug_dir:
        os.makedirs(a.debug_dir, exist_ok=True)
        for style, masks in dbg.items():
            vis = np.asarray(Image.open(base_p).convert("RGB")).copy()
            vis[masks["back"]] = [255, 60, 60]
            vis[masks["front_l"] | masks["front_r"]] = [60, 210, 60]
            vis[masks["crown"]] = [60, 120, 255]
            Image.fromarray(vis).save(os.path.join(a.debug_dir, "cut_%s.png" % style))
        log("调试图 → %s" % a.debug_dir)
    return 0


if __name__ == "__main__":
    sys.exit(main())
