#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把 seg_torso 顶部那条「塗り足し」拆成独立部件 torso_top_fill。

================================ 病因 ================================
第四十八问 (c)：「头后面的错误残留要修复」。

实拍定位（logs/asset_qa/q48_faces_before.png → q48_residue_zoom.png）：
换成 twin / pony 之后，下巴两侧、脖子高度上冒出**青绿色方块 + 褐色污渍 + 粉色碎条**。
再把异色像素反算回切件坐标核对（86%~97% 落在 seg_torso 的料上），来源确认：

  seg_torso 的**顶部 52 行**（切件 y 240~292 / rig y 308~360）不是衣服，
  是抠像分段时给的**塗り足し**：里面混着下巴和嘴的皮肤、一截褐色头发、
  半个鲸鱼发夹，还有一大片阶梯状的青绿色衣领涂抹。
  短发档它整条藏在齐腮鬓发背后，看不见；一换 twin/pony 鬓发向后掠，
  它就直接暴露在脖子两侧 —— 这就是用户说的「头后面的错误残留」。

切线不用猜 —— `tools/make_body_parts.py` 自己写得明明白白：

    seg_torso = 源图 rows [neck_y - ov, legs_top + ov]
    rgba_neck[neck_y-ov : neck_y] = rgba[neck_y]      # ← 颈线那一行向上复制
    # 注释原文：「躯干顶端的重叠带（颈线往上 ov 行）原本是**下巴**。头一转，
    #   这段静止的下巴就从头后面露出来，看着像两个下巴。这里把它换成颈线那一行
    #   向上复制出来的"脖子桩"——最便宜的关节补图，藏在头后面不会被看见。」

所以 seg_torso 的**最上面 ov 行**（本模型 overlap_px = 38，切件 y 240~278）
整条都不是原画，是复制出来的桩；而原画里那一段衣领的真料在 seg_head 里
（seg_head = rows ≤ neck_y + ov，层 180 压在躯干之上）。
「藏在头后面不会被看见」这句话只在**短发**档成立 —— 鬓发一撤，桩子就从
头的剪影外面支出来。所以这一条正是要能单独关掉的那一条，切线取 ov 行，
不多不少：上面全是桩，下面全是原画。

================================ 做法 ================================
**不是删除，是搬家**（LESSONS：擦掉 = 短发档失去塗り足し，是第二次犯的错）：
把这条料整条搬进新部件 `torso_top_fill`（group=chest，layer=99，
压在 seg_torso(100) 正下方），两件同时显示时与原图**逐像素一致**；
只在 hairstyle = long/twin/pony 三档里 hide 掉它。

切线 = body_parts.json 里的 overlap_px（--rows 可覆盖，但默认就该用它）。
**第一版走了弯路**：想靠「找衣服线稿的上沿」自动划线，结果塗り足し里那块
褐色头发实心块本身就是暗的，被当成线稿，左半边一个像素都没搬走
（logs/asset_qa/q48_split_mask.png 第一版留档）。上游既然已经把这条线写在
元数据里了，就不该去图像上重新猜 —— TRUTH-FIRST。

幂等：原件备份在 sprites/_orig/split_torso_top/，每次从备份重切。

用法：
    python3 tools/split_torso_top.py --character xiaoxun --form teen
"""
import argparse
import io
import json
import os
import shutil
import sys

import numpy as np

from PIL import Image

NEW_ID = "torso_top_fill"
SRC_ID = "seg_torso"
LAYER = 99                      # seg_torso 是 100，压在它正下方
SIG_V = 6


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--character", required=True)
    ap.add_argument("--form", required=True)
    ap.add_argument("--rows", type=int, default=0,
                    help="顶部多少行（1x）搬走；0 = 用 body_parts.json 的 overlap_px")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--quiet", action="store_true")
    a = ap.parse_args()

    base = os.path.join("characters", a.character, "forms", a.form)
    sprites = os.path.join(base, "sprites")
    bpj = os.path.join(sprites, "body_parts.json")
    with io.open(bpj, encoding="utf-8") as f:
        meta = json.load(f)
    parts = {p["id"]: p for p in meta["parts"]}
    if SRC_ID not in parts:
        print("[顶条拆件] 没有 %s，跳过" % SRC_ID)
        return 0

    sig = {"v": SIG_V, "rows": a.rows}
    if not a.force and meta.get("torso_top_split", {}).get("sig") == sig:
        if not a.quiet:
            print("[顶条拆件] 签名未变，跳过（--force 强制重做）")
        return 0

    K = 2
    orig_dir = os.path.join(sprites, "_orig", "split_torso_top")
    os.makedirs(orig_dir, exist_ok=True)
    src2 = os.path.join(sprites, SRC_ID + "@2x.png")
    bak2 = os.path.join(orig_dir, SRC_ID + "@2x.png")
    if not os.path.exists(bak2):
        shutil.copy2(src2, bak2)
    im = Image.open(bak2).convert("RGBA")
    arr = np.array(im)
    H, W = arr.shape[:2]
    A = arr[..., 3] > 30
    lum = arr[..., :3].astype(np.float32).mean(2)

    ov = int(meta.get("overlap_px", 0) or 0)
    rows = a.rows if a.rows > 0 else ov
    if rows <= 0:
        print("[顶条拆件] body_parts.json 没有 overlap_px，又没给 --rows，跳过")
        return 0
    band = rows * K
    strip = A.copy()
    strip[band:] = False

    if strip.sum() < 50:
        print("[顶条拆件] 顶条几乎没有料（%d px），跳过" % strip.sum())
        return 0

    # —— 写两张图：顶条 / 掏掉顶条的躯干 ——
    top = arr.copy()
    top[..., 3] = np.where(strip, arr[..., 3], 0)
    body = arr.copy()
    body[..., 3] = np.where(strip, 0, arr[..., 3])

    ys, xs = np.where(strip)
    x0, x1 = int(xs.min()), int(xs.max()) + 1
    y0, y1 = int(ys.min()), int(ys.max()) + 1
    x0 -= x0 % K
    y0 -= y0 % K
    x1 += (-x1) % K
    y1 += (-y1) % K
    tcrop = Image.fromarray(top[y0:y1, x0:x1])
    tcrop.save(os.path.join(sprites, NEW_ID + "@2x.png"))
    tcrop.resize((tcrop.width // K, tcrop.height // K),
                 Image.LANCZOS).save(os.path.join(sprites, NEW_ID + ".png"))
    Image.fromarray(body).save(src2)
    Image.fromarray(body).resize((W // K, H // K), Image.LANCZOS).save(
        os.path.join(sprites, SRC_ID + ".png"))

    sp = parts[SRC_ID]
    entry = {"id": NEW_ID, "file": "sprites/%s.png" % NEW_ID,
             "group": sp.get("group", "chest"), "layer": LAYER,
             "pos": [sp["pos"][0] + x0 // K, sp["pos"][1] + y0 // K],
             "size": [tcrop.width // K, tcrop.height // K],
             "pivot": sp.get("pivot"),
             "note": "seg_torso 顶部的塗り足し（下巴/脖子/衣领的描き足し）单独成件。"
                     "两件都显示时与原图逐像素一致；长发/双马尾/高马尾三档 hide 掉它，"
                     "否则鬓发一撤它就露在脖子两侧（第四十八问 (c) 的「头后错误残留」）"}
    meta["parts"] = [p for p in meta["parts"] if p["id"] != NEW_ID]
    i = next(i for i, p in enumerate(meta["parts"]) if p["id"] == SRC_ID)
    meta["parts"].insert(i, entry)
    meta["torso_top_split"] = {
        "sig": sig, "px_2x": int(strip.sum()), "px_1x": int(strip.sum()) // 4,
        "pos": entry["pos"], "size": entry["size"],
        "rows_1x": rows, "overlap_px": ov,
        "why": "seg_torso 顶部 overlap_px 行 = make_body_parts 复制颈线做出来的"
               "脖子桩，不是原画；原画那一段衣领在 seg_head 里"}
    with io.open(bpj, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
    if not a.quiet:
        print("[顶条拆件] %s %dx%d @%s，搬走 %d px(1x)，切线 = 顶部 %d 行"
              "（overlap_px=%d）"
              % (NEW_ID, entry["size"][0], entry["size"][1], entry["pos"],
                 strip.sum() // 4, rows, ov))
    return 0


if __name__ == "__main__":
    sys.exit(main())
