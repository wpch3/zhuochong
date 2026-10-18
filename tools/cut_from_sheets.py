#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从参考模板切发型件（T46.14）。

和老办法的区别
--------------
老办法：每个发型件都是**单独生成**的一张 AI 图（hair_twin_bunch_v2.png、
hair_pony_back_v2.png、hair_long_back_v2.png……），然后靠手调的 pos_rel /
width_ratio 往头上怼。几张图之间没有任何共同约束，所以：

  · 色相对不上  → 用户说的「拼接痕迹很明显」
  · 结构对不上  → 用户说的「一坨头发缠在一起」「完全不行」

新办法：所有发型件都从 `design/sheets/sheet_<发型>.png` 这**同一张完整差分
立绘**上切下来。同一张图里的像素天然同色、同光照、同几何，拼起来没有缝。
这是 Live2D 官方工序（画师先画完整差分立绘、再拆图层）的下半截，
上半截是 `tools/register_sheets.py`（把模板套准到同一套身体坐标）。

怎么切
------
模板和底图是**像素对齐**的（register_sheets 保证，鞋底都在 y=1479），
所以"这个发型改了什么"可以直接做差：

  back  = 模板不透明 & 底图透明          → 短发剪影之外的新头发（后发/尾巴）
  front = 两边都不透明 & 颜色差很大 & 是发色 → 画在身体/脸上的新头发（长鬓发等）

沿**身体剪影**切开，是 Live2D 的标准切法：静止时接缝正好被身体挡住；
转头时露出来的那一截，靠 back 件的**塗り足し**（向身体内侧延伸补色）兜住。
两片来自同一张画，颜色和线条连续，所以接缝看不见。

坐标
----
模板(1024x1536) → body_full 像素系 的仿射，和 prepare_sprites.py 完全一致：

    s = 1292 / 1453                      （角色高占画布 0.95）
    bf = (sheet - 底图人物bbox左上) * s

anchors.json 的 points 用的就是 body_full 像素系，所以每个件的
pos_rel / sprite_h_rel 都是**量出来的**，不是手调的。
"""
from __future__ import annotations

import argparse
import io
import json
import os
import sys

import numpy as np
from PIL import Image, ImageFilter

SHEET_CANVAS = (1024, 1536)
HEIGHT_RATIO = 0.95          # 与 prepare_sprites.py 的 --height-ratio 一致
TARGET_CANVAS = (848, 1360)  # 与 prepare_sprites.py 的 --canvas 一致

#: 每个发型要切哪几件，以及落到哪个槽。
#: 槽号与层号沿用 attachments.json 里已有的（见 docs/ART_PARTS.md）。
PLAN = {
    "twin": [
        ("hair_twin_back", "body_back_hair", "back"),
        ("hair_twin_front_l", "head_side_long", "front_l"),
        ("hair_twin_front_r", "head_side_long", "front_r"),
        ("hair_twin_crown", "head_crown_tied", "crown"),
    ],
    "pony": [
        ("hair_pony_back", "body_back_pony", "back"),
        ("hair_pony_front_l", "head_side_long", "front_l"),
        ("hair_pony_front_r", "head_side_long", "front_r"),
        ("hair_pony_crown", "head_crown_tied", "crown"),
    ],
    "long": [
        ("hair_long_back", "body_back_hair", "back"),
        ("hair_long_front_l", "head_side_long", "front_l"),
        ("hair_long_front_r", "head_side_long", "front_r"),
        ("hair_long_crown", "head_crown_tied", "crown"),
    ],
}

#: 塗り足し：back 件向身体内侧延伸多少像素（模板坐标）。
#: 依据：头部左右转到极限时，后发相对身体的横向位移约 0.08 个头宽 ≈ 22px(body_full)
#: ≈ 25px(模板)。取 40 留足余量。
BLEED = 40


def log(msg: str) -> None:
    print(msg)


# ---------------------------------------------------------------- 掩膜工具
def _m(b: np.ndarray) -> Image.Image:
    return Image.fromarray((b.astype(np.uint8)) * 255)


def _a(i: Image.Image) -> np.ndarray:
    return np.asarray(i) > 127


def dilate(b: np.ndarray, k: int) -> np.ndarray:
    return _a(_m(b).filter(ImageFilter.MaxFilter(k)))


def erode(b: np.ndarray, k: int) -> np.ndarray:
    return _a(_m(b).filter(ImageFilter.MinFilter(k)))


def despeckle(b: np.ndarray, k: int = 5, grow: int = 7) -> np.ndarray:
    """去掉细线噪点，但把核心周围的原始像素收回来（保住发梢的尖细部分）。

    直接做开运算会把发梢和呆毛一起削掉（实测双马尾头顶整片丢失），
    所以开完之后再用核心去**召回**原始掩膜里挨着核心的部分。
    """
    core = _a(_m(b).filter(ImageFilter.MinFilter(k)).filter(ImageFilter.MaxFilter(k)))
    return dilate(core, grow) & b


def key_rgba(path: str):
    """洋红键抠像，返回 (rgb float32, 不透明掩膜)。"""
    a = np.asarray(Image.open(path).convert("RGB")).astype(np.float32)
    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    mag = (r > 150) & (b > 150) & (g < 110) & ((r - g) > 80) & ((b - g) > 80)
    return a, ~mag


def hair_like(a: np.ndarray) -> np.ndarray:
    """发色判据：冷色相、不太暗、不是青。

    小寻的头发是淡紫 (216,216,232) → 蓝梢 (159,196,232)，共同点是 **B > R**。
    身上其它东西都不满足：
      夹克白 (250,245,235) B−R=−15 ／ 奶油衬衫 B−R=−25 ／ 皮肤 B−R≪0
      藏青裙 B−R=+40 但 B=80 太暗 ／ 薄荷青 (91,191,181) 被 B>G−6 挡掉（青是 G≳B）
    用色相而不是亮度窗口，是因为头发上有近白的高光和压暗的阴影，
    卡亮度会把整片头顶丢掉（实测双马尾 keep 从 y=32 掉到 y=193）。
    """
    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    return (b > r + 1) & (b > 120) & (b > g - 6)


def nearest_fill(rgb: np.ndarray, src: np.ndarray, steps: int = 60):
    """把 src 为真处的颜色向外扩散（最近邻补色），用于塗り足し。"""
    out = rgb.copy()
    have = src.copy()
    for _ in range(steps):
        if have.all():
            break
        grown = dilate(have, 3)
        new = grown & ~have
        if not new.any():
            break
        # 四邻域取已有颜色的均值
        acc = np.zeros_like(out)
        cnt = np.zeros(out.shape[:2], np.float32)
        for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            sh = np.roll(np.where(have[..., None], out, 0.0), (dy, dx), (0, 1))
            shm = np.roll(have, (dy, dx), (0, 1)).astype(np.float32)
            acc += sh
            cnt += shm
        ok = new & (cnt > 0)
        out[ok] = (acc[ok] / np.maximum(cnt[ok], 1)[:, None])
        have = have | ok
        if not ok.any():
            break
    return out, have


# ---------------------------------------------------------------- 主流程
def cut_one(style: str, design: str, base_a, base_op, bbox, scale, hairline, dbg):
    sp = os.path.join(design, "sheets", "sheet_%s.png" % style)
    yy = np.arange(SHEET_CANVAS[1], dtype=np.int32)[:, None] * np.ones(
        (1, SHEET_CANVAS[0]), np.int32)
    sa, sop = key_rgba(sp)

    bh_all = hair_like(base_a) & base_op
    sh_all = despeckle(hair_like(sa) & sop)

    # 这个发型相对短发改了哪些像素。
    # ★ 阈值必须压到 18：淡紫头发 (216,216,232) 压在白夹克 (250,245,235) 上
    #   最大通道差只有 34，用 36 会把长鬓发整条漏掉，只剩阴影部分（切出来是破的）。
    diff = (np.abs(sa - base_a).max(axis=2) > 18) & sop

    # ① 剪影之外的新头发 —— 后发 / 尾巴。
    #    不需要颜色判据：底图那里本来就是透明的，多出来的只可能是头发。
    back = sop & ~dilate(base_op, 3) & sh_all

    # ② 剪影之内、底图那里**不是头发**、模板这里**是头发** —— 画在身体和脸上的新头发
    #    （长鬓发垂到胸口、马尾甩到肩前都属于这一类）
    #    ★ 这里**不能**再交 diff：平涂区域两张图颜色一样，diff 近乎 0，
    #      交完切出来是一片破洞（实测长鬓发只剩阴影部分）。
    #      判据是"模板有发、底图没发"，本身就足够；diff 只用来判断这个档位
    #      到底改没改（见下面的 changed 统计）。
    front = sop & base_op & sh_all & ~dilate(bh_all, 5)
    front = despeckle(front, 3, 7)

    # ③ 发际线以上的整片头顶 —— 扎起来之后变了形的头顶，**整片替换**。
    #    用户说过四轮「扎发造型头顶必须跟着变」，只加尾巴 = 短发挂挂件。
    #    同样取实心区域而不是 diff：diff 只能圈出线稿和高光，是镂空的。
    crown = sop & base_op & sh_all & (yy <= hairline)
    crown = despeckle(crown, 3, 7)

    changed = int((diff & (back | front | crown)).sum())
    return sa, sop, back, front, crown, changed


def to_bf(mask, rgb, bbox, scale):
    """把模板坐标的一片掩膜 + 颜色，裁到内容框并缩放到 body_full 像素系。"""
    ys, xs = np.nonzero(mask)
    if len(ys) == 0:
        return None
    x0, x1, y0, y1 = xs.min(), xs.max(), ys.min(), ys.max()
    sub_rgb = rgb[y0:y1 + 1, x0:x1 + 1]
    sub_m = mask[y0:y1 + 1, x0:x1 + 1]
    rgba = np.dstack([sub_rgb, np.where(sub_m, 255.0, 0.0)]).astype(np.uint8)
    im = Image.fromarray(rgba, "RGBA")
    nw = max(1, int(round(im.width * scale)))
    nh = max(1, int(round(im.height * scale)))
    im = im.resize((nw, nh), Image.LANCZOS)
    # 内容框左上角在 body_full 像素系里的位置
    bx = (x0 - bbox[0]) * scale
    by = (y0 - bbox[1]) * scale
    return im, bx, by, nw, nh


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--character", default="xiaoxun")
    ap.add_argument("--form", default="teen")
    ap.add_argument("--styles", default="twin,pony,long")
    ap.add_argument("--debug-dir", default="")
    a = ap.parse_args()

    design = os.path.join("characters", a.character, "design")
    form = os.path.join("characters", a.character, "forms", a.form)
    sprites = os.path.join(form, "sprites")
    os.makedirs(sprites, exist_ok=True)

    base_p = os.path.join(design, "design_sheet_short.png")
    base_a, base_op = key_rgba(base_p)
    ys, xs = np.nonzero(base_op)
    bbox = (int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max()))
    char_h = bbox[3] - bbox[1] + 1
    scale = (TARGET_CANVAS[1] * HEIGHT_RATIO) / char_h

    with io.open(os.path.join(form, "design", "anchors.json"), encoding="utf-8") as fh:
        anchors = json.load(fh)
    unit = anchors["meta"]["head_ratio"] * anchors["meta"]["height_px"]

    log("底图人物 bbox %s  高 %d  → body_full 缩放 %.6f" % (str(bbox), char_h, scale))
    # 发际线：anchors 没有这个点，按头部实测常数换算回模板坐标。
    # 画布 y=163 是发际线（见 tools/make_hood_part.py 的 HAIRLINE_Y），
    # body_full y = 画布 y − 68，再除以缩放回到模板坐标。
    hairline = int(round(bbox[1] + (163 - 68) / scale))
    log("head unit = %.1f px（body_full 像素系）  发际线在模板 y=%d\n" % (unit, hairline))

    out = {}
    for style in a.styles.split(","):
        style = style.strip()
        if not style:
            continue
        sa, sop, back, front, crown, changed = cut_one(
            style, design, base_a, base_op, bbox, scale, hairline, a.debug_dir)
        log("%-6s  后发 %6d px   前发 %6d px   头顶 %6d px   其中真改过 %6d px"
            % (style, back.sum(), front.sum(), crown.sum(), changed))
        out[style] = dict(sa=sa, sop=sop, back=back, front=front, crown=crown)

    if a.debug_dir:
        os.makedirs(a.debug_dir, exist_ok=True)
        for style, d in out.items():
            vis = np.asarray(Image.open(base_p).convert("RGB")).copy()
            vis[d["back"]] = [255, 60, 60]
            vis[d["front"]] = [60, 210, 60]
            vis[d["crown"]] = [60, 120, 255]
            Image.fromarray(vis).save(os.path.join(a.debug_dir, "cut_%s.png" % style))
        log("\n调试图写到 %s" % a.debug_dir)
    return 0


if __name__ == "__main__":
    sys.exit(main())
