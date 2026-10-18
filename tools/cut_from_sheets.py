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
        ("hair_twin_crown", "head_crown_tied", "crown"),
    ],
    "pony": [
        ("hair_pony_back", "body_back_pony", "back"),
        ("hair_pony_crown", "head_crown_tied", "crown"),
    ],
    "long": [
        ("hair_long_back", "body_back_hair", "back"),
        ("hair_long_crown", "head_crown_tied", "crown"),
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


def nearest_fill(rgb, src, steps):
    """把 src 为真处的颜色向外扩散（最近邻补色），用于塗り足し。"""
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
    return out


# ------------------------------------------------------------ 切掩膜
def cut_masks(style, design, base_a, base_op, hairline, eyeline, head_cx,
              kneeline, shoulder):
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

    out = {}
    # ① 剪影之外的新头发 —— 后发 / 尾巴。
    #    ★ 这里**不加颜色判据**：短发剪影之外本来就是空的，模板在那里画了东西，
    #      就只可能是头发。加 sh_all 反而会被高光带打出洞。
    #    套准残留会在身体轮廓外留一圈 1~3px 的描边，必须用 despeckle 滤掉，
    #    否则整条身体边缘都会被当成"剪影外的新头发"（实测件高涨到全身 1453px）。
    back = despeckle(sop & ~dilate(base_op, 5) & (yy <= kneeline), 9, 11)
    out["back"] = back
    out["back_l"] = back & (xx < head_cx)
    out["back_r"] = back & (xx >= head_cx)

    # ② 剪影之内、底图那里没发、模板这里有发 —— 画在身体和脸上的新头发
    front = despeckle(sop & base_op & sh_all & ~dilate(bh_all, 5), 3, 7)
    out["front_l"] = front & (xx < head_cx)
    out["front_r"] = front & (xx >= head_cx)

    # ③ 眼线以上、改动区内的整片头顶 —— 扎起来之后变了形的头顶。
    #    用户说过四轮「扎发造型头顶必须跟着变」，只加尾巴 = 短发挂挂件。
    #    取实心（sh_all）而不是 diff，范围由 region 限定，所以不会把没改的刘海也换掉。
    # ③ 头顶：**用几何圈区域、区域内全取**，同样不加颜色判据。
    #    颜色判据在这里必败 —— 头顶高光是成片的近中性色带（不是细缝），
    #    闭运算填不上，切出来一张麻脸（实测 crown 件全是大块空洞）。
    #    而眼线以上、头部横向范围内，画面上除了头发没有别的东西；
    #    就算多盖到一点额头，件在层 239、刘海在 240，也被盖住。
    #    ★ 下界必须切在**发际线**，不能切到眼线：头顶件在层 239，而眼睛在
    #      211~234、刘海在 240 —— 切到眼线会把眼睛整个盖住（硬伤，见第十一问）。
    #      发际线以下交给底图原有的刘海件，塗り足し再向下延 40px 藏在刘海后面。
    crown = sop & dilate(base_op, 9) & (yy <= hairline + 24) & (np.abs(xx - head_cx) <= 170)
    out["crown"] = crown
    return sa, sop, out


# ------------------------------------------------------------ 落盘
def emit_piece(pid, mask, sa, redraw, bbox, scale, unit, anchors, bleed_into=None):
    """把一片掩膜裁成洋红底 PNG，并算出 pos_rel / sprite_h_rel。"""
    if mask.sum() < 400:
        return None
    rgb = sa
    m = mask
    if bleed_into is not None:
        # 塗り足し：往身体内侧长 BLEED px，补上最近邻颜色。
        # Live2D 官方：被遮住的部分必须补画，否则一动起来就 disconnected。
        grown = dilate(m, BLEED * 2 + 1) & bleed_into & ~m
        rgb = nearest_fill(sa, m, BLEED)
        m = m | grown

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

    log("底图人物 bbox %s 高 %d → body_full 缩放 %.6f" % (str(bbox), char_h, scale))
    log("head unit %.1fpx  发际线 y=%d  眼线 y=%d  头心 x=%.1f（模板坐标）\n"
        % (unit, hairline, eyeline, head_cx))

    geom = collections.OrderedDict()
    dbg = {}
    for style in [s.strip() for s in a.styles.split(",") if s.strip()]:
        sa, sop, masks = cut_masks(style, design, base_a, base_op,
                                   hairline, eyeline, head_cx, kneeline, shoulder)
        dbg[style] = masks
        for pid, slot, key in PLAN[style]:
            mk = masks[key]
            bleed = dilate(base_op, 3) if key.startswith("back") else None
            info = emit_piece(pid, mk, sa, redraw, bbox, scale, unit, anchors, bleed)
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
