#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""删掉分段件**塗り足し带里烤进来、而且真的会露出来**的异色残渣。

★ 这一步在修什么（2026-10-19 第二十一问，用户截图里左脸颊外侧那条深红褐横条）

  `seg_torso` 是从 `body_full.png` 上切下来的，切线在下巴附近，再往上多留
  `overlap_px=38` 的塗り足し（のりしろ），好让脑袋一转也不会在脖子处裂缝。
  问题是那条塗り足し带是**原图的逐像素拷贝** —— 原图那个位置画的是
  **鬓发**，于是一片头发被烤进了躯干件里。

  短发档看不出来：真正的 `hair_side_l`（层 245）正盖在上面。
  可是 pony / twin 两档会把鬓发 `hide` 掉换成扎起来的发型，盖子一撤，
  躯干件里那片烤进去的头发就**悬空露在脸颊外面**，读起来就是一条
  莫名其妙的深红褐色块（实测 pony 露 418 px、twin 露 275 px）。

  同一块地方还有 1200 px 左右的淡紫发色，四档都露着。

★ 为什么可以直接删（这是本工具成立的全部理由，改之前务必读懂）

  `check_assets` 有一条**零容忍**的「无损切分」闸：所有分段件叠起来必须
  一个像素不差地盖住 `body_full.png`，`lost == 0`。单看这条，从 `seg_torso`
  上抠掉几百像素应该立刻变红。

  但它算的是**所有分段件叠加之后**的覆盖。而这片烤进去的头发，
  `hair_side_l` / `hair_side_r` 自己也有一份完整的拷贝（它们本来就是那片头发的
  正主，也都在 `body_parts.json` 的分段件清单里）。所以只要删除范围严格限制在
  **「别的分段件也盖着的像素」**，静止合成的覆盖率一点都不会掉。

  这条约束必须留着。删到别的分段件没有的地方去，`无损切分` 当场红。

★ 作用范围只有 `seg_torso` 的**顶端塗り足し带**，这是硬约束
  第一版对所有分段件一视同仁地找"异色"，结果从 `hair_front` 删了 1177 px、
  `hair_side_l/r` 各删了 1100+ px —— **淡紫色在发片里是正主，不是残渣**。
  "异色"这个判据永远是**相对于件本身**的：淡紫出现在躯干件里是烤进来的头发，
  出现在发片里就是头发本身。同理 `seg_foot_r_tip` 的 322 px 是袜子的冷调高光，
  也被误判过。
  所以范围写死成「`seg_torso`，且只在切线以上的塗り足し带内」——
  那是唯一一处"布料件里会混进头发"的结构性位置。要扩范围，先想清楚
  那个件的"正主色"是什么。

★ 三条判据，缺一不可
  1. **异色**：淡紫发色（b−r ≥ 8 且 r > 150）或深褐线稿（r−g > 25、r−b > 15、
     60 < r < 200）。白夹克 b−r=3、青袖 r=91、衣领青 r=111 都够不着，
     不会误伤。皮肤 r>200 也够不着。
  2. **真的会露**：在某一档里，这个件之上没有任何可见件盖住它。
     这一条是用来保护**嘴巴**的 —— 躯干件的塗り足し带里连嘴角线一起拷进来了，
     颜色 (171,128,131) 正好落在"深褐线稿"里，但它永远被 `seg_head`（层 180）
     盖着，不露，所以不删。
  3. **别处有备份**：被另一个分段件盖着（见上面那段）。

★ 删完要把「会变成内部空洞」的像素还回去
  硬删之后 `check_assets` 的「袖下躯干无新窟窿」闸红了（77 / 上限 60）：
  有些残渣像素四周仍然是躯干本体，抠掉就成了件**自己身上**的洞。
  所以删完要用**和那条闸同源的判据**（上下左右四个方向都还有内容 = 内部空洞）
  反查一遍，把这种像素原样还回去，并迭代几轮直到不再产生新洞。

删除后给 1px 软边（只减不加），避免留下锯齿硬口。
幂等：删过的像素下一轮不再满足判据 1。
"""
from __future__ import annotations

import argparse
import json
import os
import sys

import numpy as np
from PIL import Image, ImageFilter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import head_silhouette as hs  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _norm(v, d):
    if v is None:
        return (d, d)
    if isinstance(v, (list, tuple)):
        return (float(v[0]), float(v[1]))
    return (float(v), float(v))


def _place(base, p, W, H):
    im = Image.open(os.path.join(base, p["file"])).convert("RGBA")
    sx, sy = _norm(p.get("scale"), 1.0)
    if (sx, sy) != (1.0, 1.0):
        im = im.resize((max(1, int(im.width * sx)), max(1, int(im.height * sy))),
                       Image.LANCZOS)
    ax, ay = _norm(p.get("anchor"), 0.0)
    ox = int(round(p["pos"][0] - ax * im.width))
    oy = int(round(p["pos"][1] - ay * im.height))
    lyr = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    lyr.paste(im, (ox, oy))
    return np.asarray(lyr, dtype=np.float64) / 255.0, (ox, oy, im.width, im.height)


def _foreign(rgb255, alpha):
    """异色判据：烤进来的淡紫发色 / **蓝发梢** / 深褐线稿。

    ★★★ 2026-10-21 第三十一问：原判据 `(b-r)>=8 & r>150` 只抓得住**淡紫**
        那一端，**抓不住蓝发梢**。实测躯干件顶端烤进去的蓝是
        (111,122,160) / (160,182,216) / (199,218,246) 这一串 ——
        最深的那头 r=111，够不着 `r>150`，于是整片蓝原样留在件里。
        用户第三十一问原话「twin 这个后面有点蓝色的」说的就是它：
        短发档被 hair_side_l/r（层 245）正好盖住，twin/pony 把鬓发 hide 掉
        以后，躯干件里这片蓝就悬空露在肩头，上缘还是躯干件顶边那条
        **刀切水平线**（实测 rig y=308，单行跳变 +26/+20 px）。
        对照三张参考模板的同一块（logs/asset_qa/q31_sheet_jaw3.png）：
        short 档那里是一整幕发丝，**twin / pony 两档是洋红（空的）**——
        也就是说删干净、露出透明才是对的。

    为什么 `b > g` 这一条不能省：青袖 #5BBFB5=(91,191,181) 和衣领青
    (111,191,181) 的 b−r 高达 +90，光看 b−r 必然误伤整条袖子；
    但它们是**绿压蓝**（g>b），而头发是**蓝压绿**。实测分得干干净净。
    裙藏青 (55,64,93) 虽然也 b>g，但它在 y≈700 以下，
    压根不在本工具的作用带（seg_torso 顶端塗り足し带）里。
    """
    r, g, b = rgb255[..., 0], rgb255[..., 1], rgb255[..., 2]
    on = alpha > 0.5
    hairish = on & ((b - r) >= 8) & (r > 150)
    # 蓝发梢：蓝显著高于红、且**蓝压绿**（把青袖/衣领那一族排掉）
    bluetip = on & ((b - r) >= 25) & ((b - g) >= 10) & (r < 190)
    darkish = on & ((r - g) > 25) & ((r - b) > 15) & (r > 60) & (r < 200)
    return (hairish | bluetip), darkish


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--character", default="xiaoxun")
    ap.add_argument("--form", default="teen")
    ap.add_argument("--quiet", action="store_true")
    a = ap.parse_args()

    def log(m):
        if not a.quiet:
            print(m)

    base = os.path.join(ROOT, "characters", a.character, "forms", a.form)
    rig = json.load(open(os.path.join(base, "rig.json"), encoding="utf-8"))
    W, H = int(rig["canvas"]["w"]), int(rig["canvas"]["h"])
    parts = sorted(rig["parts"], key=lambda q: float(q.get("layer", 0)))

    # 分段件清单（跟 check_assets「无损切分」用的是同一份）
    bpp = os.path.join(base, "sprites", "body_parts.json")
    if not os.path.exists(bpp):
        log("  没有 body_parts.json，跳过。")
        return 0
    bp = json.load(open(bpp, encoding="utf-8"))
    seg_ids = {sp["id"] for sp in bp["parts"]}
    for extra in ("arm_parts.json", "foot_parts.json"):
        pth = os.path.join(base, "sprites", extra)
        if os.path.exists(pth):
            seg_ids |= {sp["id"] for sp in json.load(open(pth, encoding="utf-8"))["parts"]}
    seg_ids &= {p["id"] for p in parts}

    cache = {p["id"]: _place(base, p, W, H) for p in parts}

    # 每一档里「这个件之上盖着什么」—— 用来判断残渣是不是真的会露出来
    groups = {g["id"]: [e["id"] for e in g["entries"]] for g in rig.get("poses", [])}
    combos = [{"hairstyle": a_, "hood_pose": b_}
              for a_ in ["none"] + groups.get("hairstyle", [])
              for b_ in ["down"] + [h for h in groups.get("hood_pose", []) if h != "down"]]
    vis_by = [(c, hs.visible_ids(rig, c)) for c in combos]

    # ★ 只处理 seg_torso，且只在切线以上的塗り足し带内（理由见文件头）。
    TARGETS = ("seg_torso",)
    ap_pts = json.load(open(os.path.join(base, "design", "anchors.json"),
                            encoding="utf-8"))["points"]
    ys_scale = float(H) / float(bp["image_size"][1])
    neck_y = int(round(float(ap_pts["neck"][1]) * ys_scale))
    band_lo = neck_y - int(bp["overlap_px"]) * 2
    band_hi = neck_y + int(bp["overlap_px"])
    band = np.zeros((H, W), dtype=bool)
    band[max(0, band_lo):min(H, band_hi), :] = True
    log(f"  作用范围：seg_torso 的塗り足し带 y[{band_lo}..{band_hi}]"
        f"（颈线 {neck_y}、overlap {bp['overlap_px']}）")

    report = {}
    total = 0
    for p in parts:
        pid = p["id"]
        if pid not in TARGETS or pid not in seg_ids:
            continue
        arr, (ox, oy, pw, ph) = cache[pid]
        mine = arr[..., 3] > 0.5
        if not mine.any():
            continue
        rgb255 = arr[..., :3] * 255.0
        hairish, darkish = _foreign(rgb255, arr[..., 3])
        foreign = hairish | darkish
        if not foreign.any():
            continue

        # 判据 2：某一档里它之上没有任何可见件盖住
        lay = float(p.get("layer", 0))
        exposed = np.zeros((H, W), dtype=bool)
        for c, vis in vis_by:
            if pid not in vis:
                continue
            cov = np.zeros((H, W), dtype=bool)
            for q in parts:
                if q["id"] in vis and float(q.get("layer", 0)) > lay:
                    cov |= cache[q["id"]][0][..., 3] > 0.5
            exposed |= mine & ~cov

        # 判据 3：别的分段件也盖着这些像素（删了也不会丢覆盖）
        backup = np.zeros((H, W), dtype=bool)
        for q in parts:
            if q["id"] != pid and q["id"] in seg_ids:
                backup |= cache[q["id"]][0][..., 3] > 0.5

        # ★★★ 2026-10-19 第二十二问：判据 3 **取消**（`backup` 只留着打日志）。
        #   它原本要求"别的分段件也盖着"，怕删出覆盖缺口把
        #   `无损切分`（零容忍）做红。实测是多虑：去掉之后删 275 px，
        #   `check_assets` 依旧 **1176/0**。
        #   而留着它的代价是真的：残渣里**悬在身体轮廓之外**的那一块
        #   （左脸颊外侧，pony 270 px / twin 138 px）恰恰没有任何
        #   别的分段件垫底，于是永远被豁免 —— 那正是用户第二十一问
        #   截图里指的那条深褐横条，上一轮只清掉了它"贴着身体"的一半。
        #   判据 2（这像素真的会露出来）已经足以保证安全：删掉的
        #   都是某一档里**画面最上层**的异色像素，删完那里本来就该是空的。
        junk = foreign & exposed & band
        n = int(junk.sum())
        if n == 0:
            continue

        # —— 写回贴图（1× 和 @2x 都要）——
        sx, sy = _norm(p.get("scale"), 1.0)
        ys, xs = np.nonzero(junk)
        rel_x, rel_y = xs - ox, ys - oy
        stem, ext = os.path.splitext(p["file"])
        files = [(p["file"], 1.0)]
        if stem.endswith("@2x"):
            sib = stem[:-3] + ext
            if os.path.exists(os.path.join(base, sib)):
                files.append((sib, 0.5))
        else:
            sib = stem + "@2x" + ext
            if os.path.exists(os.path.join(base, sib)):
                files.append((sib, 2.0))
        for fn, mul in files:
            fp = os.path.join(base, fn)
            im = Image.open(fp).convert("RGBA")
            arr2 = np.asarray(im).copy()
            cut = np.zeros(arr2.shape[:2], dtype=bool)
            r = max(1, int(round(mul / max(sx, 1e-6))))
            fx = rel_x / max(1e-6, sx) * mul
            fy = rel_y / max(1e-6, sy) * mul
            for dy in range(r):
                for dx in range(r):
                    px = np.round(fx).astype(int) + dx
                    py = np.round(fy).astype(int) + dy
                    ok = ((px >= 0) & (px < arr2.shape[1])
                          & (py >= 0) & (py < arr2.shape[0]))
                    if ok.any():
                        cut[py[ok], px[ok]] = True
            # ★ 把"抠掉会变成内部空洞"的像素还回去。
            #    判据跟 check_assets「袖下躯干无新窟窿」同源：
            #    上下左右四个方向都还有内容的透明像素 = 件自己身上的洞。
            def inner_holes(mk):
                up = np.maximum.accumulate(mk, 0)
                dn = np.maximum.accumulate(mk[::-1], 0)[::-1]
                lf = np.maximum.accumulate(mk, 1)
                rt = np.maximum.accumulate(mk[:, ::-1], 1)[:, ::-1]
                return (~mk) & up & dn & lf & rt
            mk0 = arr2[..., 3] > 40
            base_holes = inner_holes(mk0)
            for _ in range(6):
                newh = inner_holes(mk0 & ~cut) & ~base_holes
                if not newh.any():
                    break
                cut &= ~newh
            # 硬删 + 1px 软边（只减不加）
            soft = np.asarray(Image.fromarray((cut * 255).astype("uint8"))
                              .filter(ImageFilter.GaussianBlur(1.0))).astype(np.float64) / 255.0
            al = arr2[..., 3].astype(np.float64) / 255.0
            al = np.minimum(al, 1.0 - soft)
            al[cut] = 0.0
            arr2[..., 3] = (al * 255.0).clip(0, 255).astype(np.uint8)
            Image.fromarray(arr2).save(fp)
        report[pid] = {"junk_px": n,
                       "hair_like": int((hairish & exposed & backup).sum()),
                       "dark_line": int((darkish & exposed & backup).sum())}
        total += n
        log(f"    {pid:22s} 删残渣 {n:5d} px"
            f"（淡紫发 {report[pid]['hair_like']} / 深褐线稿 {report[pid]['dark_line']}）")

    log(f"  合计删掉露在外面的异色残渣 {total} px，涉及 {len(report)} 个件")
    json.dump({"total_px": total, "parts": report},
              open(os.path.join(base, "sprites", "trim_residue_report.json"),
                   "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
