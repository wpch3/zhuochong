#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""clean_neck_residue.py — 擦掉躯干件顶边（下颌两侧）烤进去的碎发残渣。

2026-10-22 第四十六问。把头发换成 twin / pony 之后，脸颊外侧会飘着一小块
灰绿色的碎片（logs/asset_qa/q46_faces_after.png 的 twin/pony 格）。逐层探针
查到它是 **seg_torso 自己的像素**（rig 坐标 (328,311) 处 RGBA=(131,153,162)）：
身体件是从原画整图切出来的，切线沿着短发外沿走，于是短发的发梢和发影被一起
烤进了躯干顶边。短发档有 hair_side_l/r 盖着看不见，头发一扎起来就露馅。

只清 **下颌两侧、领口以上** 这一条带：那里真正该有的东西只有下巴和脖子
（皮肤），其余都是残渣。判据按行走 —— 每行先找皮肤像素，保留
[最左皮肤-3, 最右皮肤+3] 这一段，段外的 alpha 清零。带外一律不碰，所以
领子、拉链、帽子全都安全。

★★★ 这个脚本**故意没有挂进 tools/rebuild_parts.sh**（2026-10-22 第四十六问）。
    擦是能擦干净：213~1900 px 一擦，twin/pony 脸颊外那块灰绿碎片就没了
    （logs/asset_qa/q46_faces_after.png 对照 q46_faces.png）。但同一块料在
    **短发档**是正经的塗り足し —— 它被 hair_side_l/r 压着，头发一摆就该由它
    兜底。擦掉之后 check_assets 立刻判红两条：
        发梢甩 (-12,+0) 身体内部新增空洞 25 px（上限 20）
        发梢甩 (+12,+0) 身体内部新增空洞 72 px（上限 20）
    把保留边距从 3 放到 22（只擦 213 px）能回到基线 4 红，但那时碎块**还在**
    （实拍 logs/asset_qa/q46_blob_keep22.png）—— 两头不讨好。
    正解是把这块料从 seg_torso 里**拆成一个单独部件**（层压在躯干上、归
    hairstyle 互斥组管：短发显示、twin/pony/long 隐藏），不是在共用件上做减法。
    见台账 T46.50。

原件备份进 sprites/_orig/（若已存在则沿用，不覆盖）。
用法：python tools/clean_neck_residue.py --character xiaoxun --form teen [--force]
"""
import argparse
import io
import json
import os

import numpy as np
from PIL import Image


def skin_mask(a):
    r = a[:, :, 0].astype(int)
    g = a[:, :, 1].astype(int)
    b = a[:, :, 2].astype(int)
    al = a[:, :, 3].astype(int)
    return (al > 60) & (r > 165) & (r >= g + 6) & (g >= b - 6) & (b < 235)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--character", required=True)
    ap.add_argument("--form", required=True)
    ap.add_argument("--band", type=int, default=46,
                    help="从躯干件顶边往下算，清理带有多少行（1× 像素）")
    ap.add_argument("--keep", type=int, default=3, help="皮肤两侧各留几 px")
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args()

    base = os.path.join("characters", a.character, "forms", a.form)
    sprites = os.path.join(base, "sprites")
    bpj = os.path.join(sprites, "body_parts.json")
    if not os.path.exists(bpj):
        print("[neck] 缺 body_parts.json，跳过")
        return 0
    with io.open(bpj, encoding="utf-8") as f:
        BJ = json.load(f)

    sig = {"band": a.band, "keep": a.keep, "v": 5}
    if BJ.get("neck_residue", {}).get("sig") == sig and not a.force:
        print("[neck] 已清过顶边残渣，跳过（--force 强制）")
        return 0

    orig_dir = os.path.join(sprites, "_orig")
    if not os.path.isdir(orig_dir):
        os.makedirs(orig_dir)

    stats = {}
    for s in (1, 2):
        suf = "" if s == 1 else "@2x"
        f_t = os.path.join(sprites, "seg_torso%s.png" % suf)
        if not os.path.exists(f_t):
            continue
        bak = os.path.join(orig_dir, "seg_torso_necksrc%s.png" % suf)
        if not os.path.exists(bak):
            Image.open(f_t).convert("RGBA").save(bak)
        # 永远从备份重算：--force 换参数重跑不会在自己上一次的结果上再来一遍
        im = Image.open(bak).convert("RGBA")
        arr = np.array(im)
        sk = skin_mask(arr)
        H, W = arr.shape[:2]
        band = min(a.band * s, H - 1)
        keep_px = a.keep * s

        # 带内合法的东西只有「下巴 + 脖子」这一块皮肤（领子的尖角在带以下）。
        # 所以：从带底那行的皮肤出发做连通生长，长到的才留，其余全是残渣。
        grow = np.zeros((H, W), bool)
        grow[band] = sk[band]
        skc = sk.copy()
        for _ in range(3):  # 先把线稿造成的 1~2px 断口闭合，免得生长被卡住
            skc[1:] |= skc[:-1] & sk[1:]
            skc[:-1] |= skc[1:] & sk[:-1]
        for _ in range(max(80, band)):
            nxt = grow.copy()
            nxt[1:] |= grow[:-1]
            nxt[:-1] |= grow[1:]
            nxt[:, 1:] |= grow[:, :-1]
            nxt[:, :-1] |= grow[:, 1:]
            nxt &= skc
            if nxt.sum() == grow.sum():
                break
            grow = nxt
        keep = grow.copy()
        for _ in range(keep_px + 1):  # 给线稿/抗锯齿留一圈余量
            nxt = keep.copy()
            nxt[1:] |= keep[:-1]
            nxt[:-1] |= keep[1:]
            nxt[:, 1:] |= keep[:, :-1]
            nxt[:, :-1] |= keep[:, 1:]
            keep = nxt
        drop = np.zeros((H, W), bool)
        drop[:band] = (arr[:band, :, 3] > 0) & ~keep[:band]

        # ★ 擦之前先问一句：擦完会不会在件**里面**留洞。
        #   第一版直接擦，check_assets 立刻判红两条：「躯干自身新增内部空洞
        #   88px（上限 60）」「发梢甩 ±12 后身体内部新增空洞 72px（上限 20）」。
        #   —— 残渣里有一部分是夹在下巴和衣领**之间**的，擦掉就是个窟窿，
        #   头发一摆就露背景。那部分不是"飘在脸外的碎块"，留着也看不见。
        #   判据：擦完之后仍然被实体四面围住的透明像素，一律收回不擦。
        solid = (arr[:, :, 3] > 0) & ~drop
        dn = np.cumsum(solid[::-1], 0)[::-1] > 0
        lf = np.cumsum(solid, 1) > 0
        rt = np.cumsum(solid[:, ::-1], 1)[:, ::-1] > 0
        # 不要求"上面也有实体"：这一条带的上方本来就是脑袋（另一个件），
        # 件自己当然没有料。只要**下、左、右**还被实体围着，这个像素就是
        # 夹在下巴和衣领之间的夹心，擦了会变成窟窿 —— 收回。
        # 真正要擦的那块碎渣探在脸颊外侧，它的外侧一侧是空的，过不了这一关。
        enclosed = drop & dn & lf & rt
        for _ in range(3):   # 洞的边缘也一起收回，免得留一圈锯齿薄边
            nxt = enclosed.copy()
            nxt[1:] |= enclosed[:-1]
            nxt[:-1] |= enclosed[1:]
            nxt[:, 1:] |= enclosed[:, :-1]
            nxt[:, :-1] |= enclosed[:, 1:]
            enclosed = nxt & drop
        drop &= ~enclosed
        cut = int(drop.sum())
        arr[drop, 3] = 0
        Image.fromarray(arr).save(f_t)
        stats[suf or "1x"] = cut
        print("[neck] seg_torso%s 擦掉顶边残渣 %d px" % (suf, cut))

    BJ["neck_residue"] = {
        "sig": sig, "cut_px": stats,
        "note": "tools/clean_neck_residue.py：躯干顶边（下颌两侧、领口以上）"
                "烤进来的碎发/发影残渣，扎头发时会飘在脸颊外"}
    with io.open(bpj, "w", encoding="utf-8") as f:
        f.write(json.dumps(BJ, ensure_ascii=False, indent=2))
        f.write(u"\n")
    print("[neck] 完成")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
