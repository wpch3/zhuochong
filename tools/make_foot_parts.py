#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""make_foot_parts.py - 把鞋从腿上拆下来，并做出一张「踮脚姿态的鞋」（T24.5 / G88）。

为什么要拆：
  踮脚（ParamTiptoe）原来只有两条绑定：root.dy 上提 + 两腿 bend_y 下推抵消。
  脚底是钉住了，但鞋本身只是被**纵向压扁 3px**。用户实测反馈「踮脚脚部没有变化」。
  上一轮用图像模拟验过：把正面视角的鞋压缩 8%/14%/22%，看起来只是「踩瘪的鞋」，
  不是「抬起脚跟」。结论是鞋必须另有一张姿态图（G88 → T24.5）。

这一版的关键修正（推翻了上一轮的方向）：
  踮脚时正面视角下鞋**不是变矮，是变高**。把脚看成绕脚尖转 φ 角的刚体、
  相机俯角 θ，则鞋在画面里的纵向长度 = L·sin(θ+φ)，比站平时的 L·sin(θ) **更长**；
  同时鞋尖那块朝向相机的橡胶底面转向下方，白色鞋底带**变窄**。
  所以：鞋身沿地面线纵向拉伸、鞋底带压扁、袜子整体上移 —— 这就是踮脚的鞋。
  （上一轮之所以觉得"做不出来"，是因为方向搞反了，压缩当然只会像踩瘪。）

  正因为这个姿态里**没有任何新露出来的表面**（俯视看不到抬起的鞋跟底面，
  能看见的还是鞋面和鞋头那几块），所以它不属于 D19「被遮挡区域必须 AI 重绘」，
  用已有像素做几何重投影是成立的。AI 重绘试过两轮（见 logs/asset_qa/），
  模型每次都重新构图、改画风、而且照样画成站平的鞋，反而更差。

抬起量 lift 与拉伸倍率是**同一个量**，不能各写各的：
  鞋身拉伸多少，鞋口（= 脚踝）就抬高多少，身体也就升高多少。
  所以这里只有一个控制量 `--lift`，倍率由它推出来，并写进 foot_parts.json
  给 make_rig.py 用（root.dy = -lift，两只脚的组 dy = +lift，净位移 0 = 脚底钉地）。

产出：
  sprites/seg_foot_l.png      常态鞋（从 body_full 原样切下，含一段袜子重叠带）
  sprites/seg_foot_r.png
  sprites/seg_foot_l_tip.png  踮脚鞋（同一批像素按上面的投影关系重采样）
  sprites/seg_foot_r_tip.png
  sprites/foot_parts.json     位置/尺寸/lift/切线/自检数字
  并把 seg_leg_l.png / seg_leg_r.png 切线以下的像素擦掉（鞋归脚件管）。

用法：
  ~/.imgenv/bin/python tools/make_foot_parts.py --character xiaoxun --form teen
  ~/.imgenv/bin/python tools/make_foot_parts.py --character xiaoxun --form teen --qa
"""
from __future__ import annotations
import argparse, json, os, sys

import numpy as np
from PIL import Image, ImageFilter

SOLE_SQUASH = 0.65      # 鞋底带压扁到多少（朝向相机的那个面转下去了）
SOCK_PAD = 6            # 切线放在鞋口上沿再往上几像素（切在纯白袜子上，切痕看不见）
EDGE_MARGIN = 3         # 左右各留几像素（含描边与抗锯齿边）
LAYER = {"seg_foot_l": 62, "seg_foot_r": 63,
         "seg_foot_l_tip": 64, "seg_foot_r_tip": 65}


def load_rgba(path):
    return np.array(Image.open(path).convert("RGBA")).astype(np.float64)


def shoe_masks(rgba):
    """鞋面（青绿）与描边（深色）的掩膜。袜子是纯白、腿是肤色，都排得掉。"""
    r, g, b, a = rgba[..., 0], rgba[..., 1], rgba[..., 2], rgba[..., 3]
    op = a > 60
    teal = op & (g > r + 15) & (b > r) & (g < 230)
    dark = op & (r < 150) & (g < 160) & (b < 175)
    white = op & (r > 225) & (g > 225) & (b > 218)
    return op, teal, dark, white


def refine_teen_shoe_contrast(rgba, sides, ground):
    """按原画边界加深袜鞋分界，并给白鞋头/鞋底一层克制的冷灰阴影。

    视觉真值是 design_sheet_short.png 与项目色卡：袜子仍保持 #F6F2F0，鞋带、鞋舌、
    青绿鞋面和轮廓不改；只在检测到的鞋口描边上加深原有线稿，并对鞋头/鞋底的近白
    像素作渐变调色。阴影起点按 shoe_top 到 sole_top 的比例定位，不依赖固定画布坐标。
    """
    out = rgba.copy().astype(np.float64)
    target = np.array([220.0, 220.0, 228.0])  # 近线稿色的淡冷灰，不把白鞋涂成彩色
    line_color = np.array([90.0, 90.0, 110.0])  # 项目线稿色卡 #5A5A6E
    h, w = out.shape[:2]
    yy, xx = np.mgrid[:h, :w]
    for s in sides:
        x0, x1 = s["x0"], s["x1"]
        y_shoe, y_sole = s["y_shoe"], s["y_sole"]
        if y_sole <= y_shoe:
            continue

        # 只压鞋头与外底的近白，不触碰袜子、鞋带与鞋舌。起点落在鞋面下方 56% 处，
        # 到鞋底的阴影权重从 45% 软升至 55%，保留中央高光与原画的白鞋观感。
        toe_start = y_shoe + int(round((y_sole - y_shoe) * 0.56))
        rgb = out[..., :3]
        alpha = out[..., 3]
        near_white = ((alpha > 60) & (rgb[..., 0] > 225) &
                      (rgb[..., 1] > 225) & (rgb[..., 2] > 218) &
                      (xx >= x0) & (xx < x1) & (yy >= toe_start))
        if near_white.any():
            ramp = np.clip((yy - toe_start) / max(1, ground - toe_start), 0.0, 1.0)
            weight = 0.45 + 0.10 * ramp
            out[..., :3][near_white] = (
                rgb[near_white] * (1.0 - weight[near_white, None]) +
                target * weight[near_white, None])

        # 沿用原图已有弧形，不新造一条几何线：将鞋口灰线和抗锯齿边拉向线稿色，
        # 强化袜子 / 鞋舌的层次。限定在鞋口附近和鞋宽内部，避免加重袜筒外轮廓。
        lum = out[..., :3].mean(axis=2)
        chroma = out[..., :3].max(axis=2) - out[..., :3].min(axis=2)
        seam = ((alpha > 60) & (lum < 235) & (chroma < 55) &
                (xx >= x0 + 8) & (xx < x1 - 8) &
                (yy >= y_shoe - 2) & (yy <= y_shoe + 2))
        out[..., :3][seam] = out[..., :3][seam] * 0.50 + line_color * 0.50
    return np.clip(out, 0, 255)


def find_shoe_top(teal, dark, x0, x1, y_from, y_to):
    """从脚踝往下扫，第一行出现成片鞋像素的位置 = 鞋口上沿。"""
    for y in range(y_from, y_to):
        if int(teal[y, x0:x1].sum()) + int(dark[y, x0:x1].sum()) >= 6:
            return y
    return -1


def find_sole_top(teal, white, op, x0, x1, y_from, y_to):
    """鞋底白带的上沿：往上数最后一段「白色占绝对多数且几乎没有青绿」的区间。"""
    best = -1
    for y in range(y_to - 1, y_from, -1):
        n = int(op[y, x0:x1].sum())
        if n < 12:
            continue
        w = int(white[y, x0:x1].sum())
        t = int(teal[y, x0:x1].sum())
        if w >= 0.55 * n and t <= 0.12 * n:
            best = y
        elif best >= 0:
            break
    return best


def warp_rows(src, y_top_dst, y_bot, ground, y_shoe, d_sole, ks, ku, lift):
    """按「绕脚尖旋转」的纵向重投影，把 src（整张 body 图）采样成踮脚姿态的一块。

    目的行 yd（body 绝对坐标）→ 源行 ys：
      · 鞋底带（离地 d' ≤ d_sole·ks）：d = d'/ks        —— 压扁
      · 鞋身  （再往上）              ：d = d_sole + (d'-d_sole·ks)/ku  —— 拉长
      · 袜子  （鞋口以上）            ：ys = yd + lift  —— 整体刚性上移
    三段在接点处连续（分段线性），所以不会有台阶。
    采样用预乘 alpha 的线性插值，避免边缘出现黑边/彩边。
    """
    h_dst = y_bot - y_top_dst
    w = src.shape[1]
    out = np.zeros((h_dst, w, 4), dtype=np.float64)
    pre = src.copy()
    pre[..., :3] *= (pre[..., 3:4] / 255.0)
    sole_h = d_sole * ks
    for i in range(h_dst):
        yd = y_top_dst + i
        dp = ground - yd
        if dp <= sole_h:
            d = dp / ks
        else:
            d = d_sole + (dp - sole_h) / ku
        ys = ground - d
        if ground - d >= y_shoe:
            pass                      # 鞋段：用上面算出来的 ys
        else:
            ys = yd + lift            # 袜段：刚性上移
        y0 = int(np.floor(ys))
        f = ys - y0
        if y0 < 0 or y0 + 1 >= src.shape[0]:
            continue
        row = pre[y0] * (1.0 - f) + pre[y0 + 1] * f
        out[i] = row
    al = out[..., 3:4]
    rgb = np.where(al > 0.5, out[..., :3] / np.maximum(al / 255.0, 1e-6), 0.0)
    res = np.concatenate([np.clip(rgb, 0, 255), np.clip(al, 0, 255)], axis=2)
    return res


def crisp(img: Image.Image) -> Image.Image:
    """纵向重采样会让线稿发虚，补一道轻锐化（只锐化颜色，alpha 不动）。"""
    r, g, b, a = img.split()
    rgb = Image.merge("RGB", (r, g, b)).filter(
        ImageFilter.UnsharpMask(radius=1.2, percent=60, threshold=2))
    r2, g2, b2 = rgb.split()
    return Image.merge("RGBA", (r2, g2, b2, a))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--character", required=True)
    ap.add_argument("--form", required=True)
    ap.add_argument("--root", default=".")
    ap.add_argument("--lift", type=float, default=30.0,
                    help="踮脚抬起量（像素）。鞋身拉伸、身体上提、脚组下压都用这一个数")
    ap.add_argument("--qa", action="store_true", help="另存一张对照图到 logs/asset_qa/")
    args = ap.parse_args()

    base = os.path.join(args.root, "characters", args.character, "forms", args.form)
    sp_dir = os.path.join(base, "sprites")
    body_path = os.path.join(sp_dir, "body_full.png")
    seg_path = os.path.join(sp_dir, "body_parts.json")
    if not os.path.isfile(body_path) or not os.path.isfile(seg_path):
        print("缺 body_full.png 或 body_parts.json，先跑 make_body_parts.py", file=sys.stderr)
        return 2
    with open(seg_path, encoding="utf-8") as f:
        seg = json.load(f)
    previous_foot_report = None
    previous_foot_path = os.path.join(sp_dir, "foot_parts.json")
    if os.path.isfile(previous_foot_path):
        try:
            with open(previous_foot_path, encoding="utf-8") as f:
                previous_foot_report = json.load(f)
        except (OSError, ValueError):
            previous_foot_report = None
    legs = {p["id"]: p for p in seg["parts"] if p["id"] in ("seg_leg_l", "seg_leg_r")}
    if len(legs) != 2:
        print("body_parts.json 里没有两条腿，放弃", file=sys.stderr)
        return 2
    x_split = int(seg["cut_lines"]["center_x"])

    body = load_rgba(body_path)
    H, W = body.shape[0], body.shape[1]
    op, teal, dark, white = shoe_masks(body)
    ground = H                                   # 地面 = 图的底边（脚底就贴在这）
    anchors_path = os.path.join(base, "design", "anchors.json")
    ankle_y = 1142
    if os.path.isfile(anchors_path):
        with open(anchors_path, encoding="utf-8") as f:
            ankle_y = int(round(json.load(f)["points"]["ankle"][1]))

    sides = []
    for sid, (sx0, sx1) in (("l", (0, x_split)), ("r", (x_split, W))):
        sub = op[:, sx0:sx1]
        rows = np.where(sub[ankle_y:].any(axis=1))[0]
        if len(rows) == 0:
            print("第 %s 只脚找不到像素" % sid, file=sys.stderr)
            return 2
        y_shoe = find_shoe_top(teal, dark, sx0, sx1, ankle_y, H)
        y_sole = find_sole_top(teal, white, op, sx0, sx1, y_shoe, H)
        cols = np.where(op[y_shoe:, sx0:sx1].any(axis=0))[0]
        x0 = max(sx0, sx0 + int(cols.min()) - EDGE_MARGIN)
        x1 = min(sx1, sx0 + int(cols.max()) + 1 + EDGE_MARGIN)
        bot = int(np.where(op[:, x0:x1].any(axis=1))[0].max())
        sides.append(dict(side=sid, x0=x0, x1=x1, y_shoe=y_shoe, y_sole=y_sole, bottom=bot))

    # 两只脚用同一条切线与同一个 lift：左右不同会在正面看出高低脚
    y_shoe = min(s["y_shoe"] for s in sides)
    y_sole = min(s["y_sole"] for s in sides)
    lift = float(args.lift)
    y_cut = y_shoe - SOCK_PAD                     # 腿件擦到这条线为止
    overlap = int(round(lift)) + 8                # 脚件往上多带这么多袜子（盖住腿件退上去留的缝）
    y_top_flat = y_cut - overlap
    y_top_tip = y_top_flat - int(round(lift))

    D = ground - y_shoe
    d_sole = ground - y_sole
    ks = SOLE_SQUASH
    ku = (D + lift - d_sole * ks) / (D - d_sole)

    # The reference artwork intentionally keeps socks white; only the Teen sneaker's
    # toe/outsole receive a cool shadow, and the existing collar ink is strengthened.
    foot_source = body
    shoe_finish = None
    if args.character == "xiaoxun" and args.form == "teen":
        foot_source = refine_teen_shoe_contrast(body, sides, ground)
        shoe_finish = {
            "reference": "design/design_sheet_short.png + design/palette.json",
            "scope": "shoe toe and outsole only; sock, tongue, laces, teal panels unchanged",
            "toe_shadow_target": "#DCDCE4",
            "toe_shadow_blend": [0.45, 0.55],
            "collar_ink_target": "#5A5A6E",
            "method": "recolor existing neutral collar ink; do not invent new geometry",
        }

    out_parts, checks = [], {}
    qa_tiles = []
    for s in sides:
        x0, x1 = s["x0"], s["x1"]
        flat = foot_source[y_top_flat:ground, x0:x1].copy()
        flat_img = Image.fromarray(np.clip(flat, 0, 255).astype(np.uint8), "RGBA")
        tipw = warp_rows(foot_source, y_top_tip, ground, ground, y_shoe, d_sole, ks, ku, lift)
        tip_img = crisp(Image.fromarray(
            np.clip(tipw[:, x0:x1], 0, 255).astype(np.uint8), "RGBA"))

        fid = "seg_foot_%s" % s["side"]
        tid = fid + "_tip"
        flat_img.save(os.path.join(sp_dir, fid + ".png"))
        tip_img.save(os.path.join(sp_dir, tid + ".png"))
        out_parts += [
            {"id": fid, "file": "sprites/%s.png" % fid,
             "pos": [x0, y_top_flat], "size": list(flat_img.size),
             "group": "foot_%s" % s["side"], "layer": LAYER[fid],
             "note": "常态鞋（原画切下，往上多带 %d px 袜子当重叠带）" % overlap},
            {"id": tid, "file": "sprites/%s.png" % tid,
             "pos": [x0, y_top_tip], "size": list(tip_img.size),
             "group": "foot_%s" % s["side"], "layer": LAYER[tid],
             "note": "踮脚鞋（鞋身×%.3f 纵向拉伸、鞋底带×%.2f 压扁、袜段上移 %d px）"
                     % (ku, ks, int(round(lift)))},
        ]

        # --- 自检：两张图各自的「鞋口」「触地行」要对得上设计意图 ---
        fa = np.array(flat_img)[..., 3] > 60
        ta = np.array(tip_img)[..., 3] > 60
        f_bot = int(np.where(fa.any(axis=1))[0].max()) + y_top_flat
        t_bot = int(np.where(ta.any(axis=1))[0].max()) + y_top_tip
        f_top_shoe = find_shoe_top(teal, dark, x0, x1, ankle_y, H)
        # Geometry is invariant under the color-only shoe finish. Measure the tip shoe
        # edge from the unmodified source warp so darker AA ink is not mistaken for a
        # one-pixel change in the collar position.
        tip_geom = warp_rows(body, y_top_tip, ground, ground,
                             y_shoe, d_sole, ks, ku, lift)
        tt = np.array(tip_geom[:, x0:x1]).astype(np.float64)
        _, t_teal, t_dark, _ = shoe_masks(tt)
        t_top_shoe = -1
        for y in range(tt.shape[0]):
            if int(t_teal[y].sum()) + int(t_dark[y].sum()) >= 6:
                t_top_shoe = y + y_top_tip
                break
        checks["foot_" + s["side"]] = {
            "x": [x0, x1], "shoe_top": s["y_shoe"], "sole_top": s["y_sole"],
            "flat_bottom": f_bot, "tip_bottom": t_bot,
            "flat_shoe_top": f_top_shoe, "tip_shoe_top": t_top_shoe,
            "collar_rise": f_top_shoe - t_top_shoe,
            "flat_px": int(fa.sum()), "tip_px": int(ta.sum()),
        }
        if args.qa:
            qa_tiles.append((flat_img, tip_img))

    # --- 腿件：切线以下的像素交给脚件，自己擦干净，并**连画布一起裁掉** ---
    #
    # 裁掉这一步不是为了省几 KB —— 引擎的 bend 曲线（root/tip/sine）是按
    # **贴图画布**的 0..1 铺的，不是按画面上的解剖位置。腿件原本画布底边
    # 正好落在鞋底（t=1 = 地面），所以：
    #   · ParamLegL 的 tip 曲线在鞋底拿满额 20px —— 摆腿时整只脚跟着走；
    #   · ParamKnee 的 sine 曲线在鞋底是 0 —— 屈膝不会把脚拔离地面。
    # 只擦像素、不裁画布的话，画布底边还留在地面下方 142px 的空白里，
    # 脚踝那条线就从 t=1.000 掉到 t=0.774：tip 只剩 0.59（摆腿 20px→11.6px，
    # 少 42%），sine 反倒涨到 0.65（屈膝把脚抬起 2.9px，人就浮空了）。
    # 两处毛病同一个上游：画布边界 ≠ 解剖边界。裁到切线，语义就回来了。
    erased, crop_h = {}, {}
    for lid, lp in legs.items():
        p = os.path.join(args.root, "characters", args.character, "forms", args.form,
                         lp["file"])
        im = Image.open(p).convert("RGBA")
        a = np.array(im)
        ly = y_cut - lp["pos"][1]                 # 切线换算到腿件自身坐标
        prior_erased = 0
        if (previous_foot_report and
                int(previous_foot_report.get("cut", {}).get("leg_cut_y", -1)) == y_cut):
            prior_erased = int(previous_foot_report.get("legs_erased_px", {}).get(lid, 0))
        if 0 <= ly < a.shape[0]:
            erased_now = int((a[ly:, :, 3] > 60).sum())
            # Re-running on already-clean legs should not erase the historical source count.
            # Keep the prior count when the cutline is unchanged; a full rebuild from the
            # upstream body parts will repopulate erased_now directly.
            erased[lid] = erased_now or prior_erased
            a = a[:ly]                            # 连画布一起裁到切线
            Image.fromarray(a, "RGBA").save(p)
            crop_h[lid] = int(a.shape[0])
            lp["size"] = [int(a.shape[1]), int(a.shape[0])]
        else:
            # The leg canvas may already end exactly at the cutline on an idempotent run.
            erased[lid] = prior_erased
            crop_h[lid] = int(a.shape[0])
    # 裁过之后 body_parts.json 里记的尺寸就过期了，必须写回去 ——
    # make_rig.py 和 check_assets.py 都按它摆位置，不同步就全错。
    with open(seg_path, "w", encoding="utf-8") as f:
        json.dump(seg, f, ensure_ascii=False, indent=2)
        f.write("\n")

    rep = {
        "schema_version": "1.0",
        "source": "sprites/body_full.png",
        "note": "踮脚鞋 = 已有像素按「绕脚尖旋转 + 俯角投影」重采样，不是 AI 重绘："
                "这个姿态没有新露出的表面，所以不走 D19。",
        "lift_px": lift,
        "ground_y": ground,
        "cut": {"ankle_y": ankle_y, "shoe_top": y_shoe, "sole_top": y_sole,
                "leg_cut_y": y_cut, "sock_overlap_px": overlap,
                "flat_top": y_top_flat, "tip_top": y_top_tip, "x_split": x_split},
        "warp": {"sole_squash": ks, "upper_stretch": round(ku, 4),
                 "formula": "d'=d_sole*ks+(d-d_sole)*ku（离地距离分段线性），lift=总增量"},
        "legs_erased_px": erased,
        "legs_cropped_h": crop_h,
        "parts": out_parts,
        "checks": checks,
        "shoe_finish": shoe_finish,
    }
    with open(os.path.join(sp_dir, "foot_parts.json"), "w", encoding="utf-8") as f:
        json.dump(rep, f, ensure_ascii=False, indent=2)
        f.write("\n")

    if args.qa and qa_tiles:
        pad, z = 12, 3
        wsum = sum(t[0].width + t[1].width for t in qa_tiles) + pad * 5
        hmax = max(max(t[0].height, t[1].height) for t in qa_tiles)
        sheet = Image.new("RGBA", (wsum, hmax + pad * 2), (255, 0, 255, 255))
        x = pad
        for a_, b_ in qa_tiles:
            sheet.alpha_composite(a_, (x, pad + hmax - a_.height)); x += a_.width + pad
            sheet.alpha_composite(b_, (x, pad + hmax - b_.height)); x += b_.width + pad
        qa_dir = os.path.join(args.root, "logs", "asset_qa")
        os.makedirs(qa_dir, exist_ok=True)
        sheet.resize((sheet.width * z, sheet.height * z), Image.LANCZOS).convert("RGB") \
             .save(os.path.join(qa_dir, "foot_parts.png"))

    print("鞋口 y=%d 鞋底带 y=%d 切线 y=%d ｜ lift=%.1f 拉伸 ku=%.3f 压扁 ks=%.2f"
          % (y_shoe, y_sole, y_cut, lift, ku, ks))
    for k, v in checks.items():
        print("  %s 触地 常态%d/踮脚%d  鞋口抬高 %d px  像素 %d/%d"
              % (k, v["flat_bottom"], v["tip_bottom"], v["collar_rise"],
                 v["flat_px"], v["tip_px"]))
    print("  腿件擦掉像素：%s" % erased)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
