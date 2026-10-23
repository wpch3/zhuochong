#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""手部差分件：**切原画 + 切生图**，不再程序化画手。

为什么是这版（Q37 用户打回重做）
--------------------------------
第一版（Q36）是用胶囊 + 有符号距离场**程序化画**出来的手。用户放大一看：
「手出错了，完全的出错了，完全成怪物了」——确实，那是一坨带四道划痕的肉瘤。
而且我当时否掉原画的理由（"原画那只手是摊平的蹼、五指等长、没有掌骨"）
是**误判**：把 body_full 的手放大 4 倍看，手指修长、有指甲高光、有掌缘阴影，
画得比我程序化画的好得多。

用户的原话是「之前那个参考图的手无法做成部件吗？」—— 能，而且本来就该这么做：

  · 放松档 hand_l / hand_r  = **原画切件**（make_arm_parts.py 已经切好），
    这里只在腕口补一圈塗り足し，别的一个像素都不动。
  · 张开档 / 比心档          = 原画里没有这两个姿势 ⇒ 按原画风格**生图**
    （characters/xiaoxun/design/hands/*_raw.png，以原画的手做风格参考图），
    洋红键出 → 配准到腕枢轴 → 换成工程的线色调色板。

官方口径（docs/REFERENCE_NOTES.md 第五十六批）：
  · 腕/手の差分は**パーツの表示切替**（VISIBLE:PARTS_..._ARM_L_A_001=1），
    不是靠旋转把手指掰开 —— 所以差分必须是**另一张贴图**。
  · 隙間が生じる部分（手と袖の間等）は**描き足し**；関節パーツは**正円**
    ⇒ 每张手件都在腕枢轴上垫一枚半径 WRIST_R 的正圆（袖口下面，看不见）。

方位约定
--------
生图是"指尖朝上、腕口在下"，而原画的手是垂着的（指尖朝下、腕口在上）。
差分件必须和放松档**同一方位**，否则一旦手臂转起来两档就对不上 ——
所以生图统一旋转 180°，腕口朝上、以枢轴为中心贴。挥手时整条手臂转 −160°，
手正好转回"指尖朝上、掌心朝外"，比心时转 +180° 正好立起来。
"""
import argparse
import io
import json
import math
import os
import shutil

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

# ---- 调色板（取自原画 hand_r 的实测众数）----
SKIN = (254, 237, 224)
LINE = (100, 88, 103)          # 工程统一线色（和 make_arm_parts 一致）
WRIST_HW = 22.0                # 腕桩半宽 = 袖口内宽 46 的一半（横向绝不露出袖子）
WRIST_UP = 34.0                # 往袖子里续多长（塞进去的部分，永远看不见）
WRIST_DOWN = 16.0              # 露在袖口下面的那截腕子（下端是半圆＝关节转动面）
PAD = 8                        # 切件四周留白，防旋转时边缘被裁

POSES = ("open", "heart")      # 放松档不在这里生成：它就是原画件本身


def key_magenta(im):
    """洋红键出。阈值不是拍脑袋：生图背景是纯 #FF00FF，边缘抗锯齿像素会混出
    粉紫色，所以用"洋红度"连续量当 alpha，再做去溢色（despill），
    否则手的轮廓上会留一圈粉边（G：键色三坑之一）。"""
    a = np.asarray(im.convert("RGB")).astype(np.float32)
    r, g, b = a[:, :, 0], a[:, :, 1], a[:, :, 2]
    # 洋红度：红蓝都高、绿低
    m = np.clip((np.minimum(r, b) - g) / 180.0, 0.0, 1.0)
    alpha = np.clip(1.0 - m * 1.35, 0.0, 1.0)
    # 去溢色：把绿通道压低造成的紫调拉回来（只对半透明边缘做）
    edge = (alpha > 0.02) & (alpha < 0.98)
    gg = g.copy()
    gg[edge] = np.maximum(g[edge], (r[edge] + b[edge]) * 0.5 * 0.92)
    out = np.dstack([r, gg, b, alpha * 255.0]).astype(np.uint8)
    return Image.fromarray(out, "RGBA")


def line_mask(im):
    """生图里「哪儿是描边」的连续掩膜（0=纯皮，1=纯线）。

    按亮度做软判据，保留抗锯齿灰阶 —— 硬替换（颜色距离阈值）会把线啃出锯齿，
    这是第十八问之后定下的规矩。
    """
    a = np.asarray(im).astype(np.float32)
    lum = a[:, :, :3].mean(axis=2) / 255.0
    # t=1 纯线、t=0 纯皮；0.30~0.62 之间过渡。乘 alpha 是为了不让键出的
    # 半透明边缘（本身就偏暗）被当成描边。
    return np.clip((0.62 - lum) / 0.32, 0.0, 1.0) * (a[:, :, 3] / 255.0)


def wrist_line(al):
    """找腕折线：**不是图的下边**。

    生图为了好看会连着画一小截小臂，直接拿最下面一行当腕口的话，量到的是
    小臂断面（比腕粗），缩放基准就整体偏大 —— 第一版切出来的张开手 207px 高、
    是前臂（116px）的 1.8 倍，就是栽在这。
    腕是整只手**最窄**的地方，所以在下三分之一里找逐行宽度的极小值。
    返回 (腕中心 x, 腕线 y, 腕宽)。
    """
    h, w = al.shape
    rows = []
    for y in range(h):
        xs = np.nonzero(al[y] > 40)[0]
        rows.append((xs.min(), xs.max()) if len(xs) else None)
    ys = [y for y, r in enumerate(rows) if r]
    y_lo = int(ys[0] + (ys[-1] - ys[0]) * 0.62)      # 只在下 38% 找
    best, by = None, ys[-1]
    for y in range(y_lo, ys[-1] + 1):
        if not rows[y]:
            continue
        wdt = rows[y][1] - rows[y][0] + 1
        if best is None or wdt < best:
            best, by = wdt, y
    x0, x1 = rows[by]
    return (x0 + x1) * 0.5, float(by), float(best)


def load_pose(path, target_len):
    """生图 → 键出 → 按**手长**定标 → 压回描边 → 旋 180°（腕口朝上）→ 裁掉腕线
    以下的小臂 → 返回 (RGBA, 腕中心在图中的 (x, y))。

    定标基准是手长（腕折线 → 最远指尖）而不是腕宽：腕宽在生图里受小臂影响大，
    手长才是和骨架对得上的量。

    ★★★ 第五十二问在这个函数里改了两处，都踩过坑：

    ① **定标用欧氏距离，不是垂直距离。** 原来是 `target/(腕线y − 图顶y)`，
       那是垂直投影；手指斜着伸时真正的手长更长，所以「标称 86」的手实测
       只有 75.2 —— 比原画切出来的放松手（81.6）还小了 8%。现在直接用
       「腕中心 → 最远墨迹点」的欧氏距离，和验收那把尺是同一把。

    ② **描边要先在原分辨率取掩膜、按最大值膨胀，再降采样压回去。**
       生图是 896×1200，缩到 ~90px 是 13 倍降采样，LANCZOS 会把 7px 的
       描边平均成 0.5px 的浅灰雾 —— 实测暗线占比 原画手 11.0% vs 生图手
       5.4%（比心档只剩 3.0%）。手就变成「几根没有轮廓的淡色面条」，
       用户第五十二问原话「手指也有点偏细」。
    """
    im = key_magenta(Image.open(path))
    im = im.crop(im.getbbox())
    al = np.asarray(im)[:, :, 3]
    tline = line_mask(im)
    cx, cy, _w = wrist_line(al)
    ys, xs = np.nonzero(al > 40)
    reach = float(np.hypot(xs - cx, ys - cy).max())
    s = target_len / max(1.0, reach)
    nw, nh = max(1, int(round(im.width * s))), max(1, int(round(im.height * s)))

    # 线掩膜：先在原分辨率上按最大值膨胀到「约 1 个目标像素宽」，再降采样。
    # 不膨胀直接 resize 等于把线平均掉；膨胀后再 LANCZOS 仍是抗锯齿的软边。
    k = max(1, min(9, int(round(1.0 / max(s, 1e-6))) | 1))
    tm = Image.fromarray((tline * 255.0).astype(np.uint8), "L")
    for _ in range(2):
        tm = tm.filter(ImageFilter.MaxFilter(k))
    tm = np.asarray(tm.resize((nw, nh), Image.LANCZOS)).astype(np.float32) / 255.0

    im = im.resize((nw, nh), Image.LANCZOS)
    b = np.asarray(im).astype(np.float32)
    t2 = np.clip(tm, 0.0, 1.0)[:, :, None]
    line = np.array(LINE, dtype=np.float32).reshape(1, 1, 3)
    im = Image.fromarray(np.dstack([b[:, :, :3] * (1.0 - t2) + line * t2,
                                    b[:, :, 3]]).astype(np.uint8), "RGBA")
    cx, cy = cx * s, cy * s
    # 腕线以下的小臂不要（袖子自己会画），留 6px 塞进袖口里当塗り足し
    keep = int(min(nh, cy + 6))
    im = im.crop((0, 0, nw, keep))
    im = im.rotate(180, expand=True)                 # 腕口翻到上边
    cx, cy = (im.width - 1) - cx, (im.height - 1) - cy
    return im, (cx, cy)


def rescale_relaxed(sp, armp, factor, report):
    """把**原画切出来的放松手**（hand_l / hand_r）按腕枢轴等比放大。

    ★★★ 第五十二问：用户说「挥手时手掌有点偏小了」。这不是观感问题，是量出来的 ——
    拿切件去和原画 design_sheet_short.png 里那只手做 IoU 配准，最佳落在
    **1.12 倍（IoU 0.874）**；rig 与 sheet 的全局尺度差 1.7%（下巴→眉 113 vs 115），
    折算下来手比身体小约 **10%**。独立佐证：另一位模型看图也判「手掌放大 10%~15%」。

    为什么连放松手一起放：四档手（放松 / 张开 / 比心 / 塗り足し）必须同尺寸，
    否则动作一切档手就会跳一下大小。

    腕口随之涨一成（41 → 45 px），仍窄于袖口内宽 46 px ⇒ 不会从袖子两侧露出来。

    幂等：原件第一次跑时备份进 `_orig/`，以后每次都从备份缩放 —— 单独重跑这个
    工具不会越缩越大（`--force` 式幂等是本仓库工具的硬规矩）。
    """
    orig = os.path.join(sp, "_orig")
    os.makedirs(orig, exist_ok=True)
    AP = {p["id"]: p for p in armp["parts"]}
    for side in ("l", "r"):
        pid = "hand_%s" % side
        p = AP.get(pid)
        if p is None:
            continue
        piv = p.get("pivot")
        if not piv:
            continue
        # 先定 1× 的尺寸，2× 严格取它的两倍 —— make_hires_sprites 以
        # 「2× 必须是 1× 的整半」判定能不能当原生高清用，差 1 px 就整张作废。
        # 备份什么时候该刷新？—— 看 arm_parts.json 里有没有 `hand_scale`。
        # make_arm_parts 重切时会把这个键连同整条记录一起重写掉 ⇒ 没有这个键
        # 就说明手件是**刚切出来的原件**，备份必须跟着换。否则重建链跑完以后，
        # 这里还拿着上一轮的旧手去缩放，新切的手就白切了。
        fresh = "hand_scale" not in p
        bak1 = os.path.join(orig, "relaxed_%s.png" % pid)
        if fresh or not os.path.exists(bak1):
            for suffix in ("", "@2x"):
                cur0 = os.path.join(sp, pid + suffix + ".png")
                if os.path.exists(cur0):
                    shutil.copyfile(cur0, os.path.join(
                        orig, "relaxed_%s%s.png" % (pid, suffix)))
        src1 = Image.open(bak1).convert("RGBA")
        one_w = max(2, int(round(src1.width * factor)))
        one_h = max(2, int(round(src1.height * factor)))
        # ⚠ pos 只能取整，「枢轴 − 放大后的局部腕位」却不是整数，这不到 1 px 的
        #   残差让 check_assets 的「无损切分」从 75 涨到 83 px。试过用 AFFINE
        #   亚像素平移把残差还给图像内容 —— **更差（104 px）**：BICUBIC 重采样
        #   把本来就软的键出边缘又糊了一道，丢的比补的多。就留整数对齐。
        for suffix, mul in (("", 1), ("@2x", 2)):
            cur = os.path.join(sp, pid + suffix + ".png")
            if not os.path.exists(cur):
                continue
            bak = os.path.join(orig, "relaxed_%s%s.png" % (pid, suffix))
            if not os.path.exists(bak):
                shutil.copyfile(cur, bak)
            im = Image.open(bak).convert("RGBA")
            im = im.resize((one_w * mul, one_h * mul), Image.LANCZOS)
            # LANCZOS 会在键出边缘过冲，把洋红背景振回来（实测 hand_r@2x 1 px，
            # check_assets「纯绿/洋红残留」直接判红）。按键色规矩清掉。
            # 判据和 check_assets「无键色垃圾像素」那条**逐字一致**，不是另立一套。
            arr = np.asarray(im).astype(np.int16)
            R, G, B, A = arr[..., 0], arr[..., 1], arr[..., 2], arr[..., 3]
            vis = A > 40
            mag = vis & (R - G > 60) & (B - G > 60) & (R > 150) & (B > 150)
            grn = vis & (G - np.maximum(R, B) > 60)
            # 去溢色而不是抠掉：抠掉会在手的轮廓上留针孔，去溢色只是把绿通道补回来
            arr[..., 1] = np.where(mag, np.maximum(G, (R + B) // 2 - 10), G)
            arr[..., 0] = np.where(grn, np.maximum(R, G - 70), R)
            arr[..., 2] = np.where(grn, np.maximum(B, G - 70), B)
            Image.fromarray(arr.astype(np.uint8), "RGBA").save(cur)
        # 枢轴不动、整件绕枢轴放大 ⇒ 左上角 = 枢轴 − 放大后的局部腕位。
        # ⚠ 必须从**原始 pos** 算：拿已经缩过的 pos 再缩一次，重跑一遍手就会往外跑
        #   （实测第二次跑 pos 从 −5 漂到 −11）。和图一样，位置也要有"原件"。
        src_pos = p.get("hand_scale_src_pos") or list(p["pos"])
        p["hand_scale_src_pos"] = [int(src_pos[0]), int(src_pos[1])]
        lx = (piv[0] - src_pos[0]) * factor
        ly = (piv[1] - src_pos[1]) * factor
        p["pos"] = [int(round(piv[0] - lx)), int(round(piv[1] - ly))]
        p["size"] = [one_w, one_h]
        p["hand_scale"] = round(factor, 4)
        report["checks"].setdefault("relaxed_scale", {})[pid] = round(factor, 4)


def wrist_stub(size, center, half_w, up, down):
    """袖口里那截腕子（塗り足し）。

    官方两条：関節パーツは**正円**（直径=腕幅）、隙間が生じる部分（手と袖の間）は
    **描き足し**。但第一版照着"正圆 r=28"画，手一转圆盘就从袖口下面露出来，
    活像腕上长了个肉球（Q37 实拍第 3 格）。两处要改：
      ① 形状：上半段是方的（塞在袖子里）、下半段才是半圆（关节的转动面），
         半宽取 22 = 袖口内宽 46 的一半，**绝不比袖子宽**，所以横向永远不露边。
      ② 归属：它是"袖の中の腕の続き"，属于**前臂**，不跟着手转 ——
         跟着手转的话手一摆它就跟着甩出去，那正是露肉球的原因。
    """
    d = Image.new("RGBA", size, (0, 0, 0, 0))
    g = ImageDraw.Draw(d)
    x, y = center
    g.rectangle([x - half_w, y - up, x + half_w, y + down - half_w], fill=SKIN + (255,))
    g.pieslice([x - half_w, y + down - 2 * half_w, x + half_w, y + down],
               0, 180, fill=SKIN + (255,))
    return d


def emit(sp_dir, name, rgba, origin, pivot, layer, group, report):
    """落盘 1× 与原生 2×（hires_src 里的会被 make_hires_sprites 当原生采用）。"""
    # 2× 画布必须是**偶数**宽高，否则 1× 不是它的整半，make_hires_sprites 会
    # 以「(133,210) ≠ (132,210)」为由把这张原生 2× 丢掉、改去超分 1× 的那张。
    if rgba.width % 2 or rgba.height % 2:
        pad = Image.new("RGBA", (rgba.width + rgba.width % 2,
                                 rgba.height + rgba.height % 2), (0, 0, 0, 0))
        pad.alpha_composite(rgba, (0, 0))
        rgba = pad
    one = rgba.resize((rgba.width // 2, rgba.height // 2), Image.LANCZOS)
    one.save(os.path.join(sp_dir, name + ".png"))
    hs = os.path.join(sp_dir, "hires_src")
    os.makedirs(hs, exist_ok=True)
    rgba.save(os.path.join(hs, name + "@2x.png"))
    report["parts"].append({
        "id": name, "file": "sprites/%s.png" % name, "group": group, "layer": layer,
        "pos": [int(round(origin[0])), int(round(origin[1]))],
        "size": [one.width, one.height],
        "pivot": [round(pivot[0], 1), round(pivot[1], 1)],
    })
    return one


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--character", default="xiaoxun")
    ap.add_argument("--form", default="teen")
    ap.add_argument("--root", default=".")
    ap.add_argument("--hand-len", type=float, default=90.0, dest="hand_len",
                    help="手长（腕中心 → 最远指尖，1x 像素）。★ Q52 从 86（标称，"
                         "实测只有 75.2）改成 90：原画切出来的放松手量得 81.6，"
                         "而放松手本身还比原画小 10%%（IoU 配准 1.12 倍）⇒ 四档手"
                         "统一做到 ~90。改之前先读 load_pose 的注释")
    ap.add_argument("--relax-scale", type=float, default=1.10, dest="relax_scale",
                    help="原画切件（放松手）放大倍数。1.10 = 量出来的：切件 ÷ 原画 "
                         "= 1/1.12，再折算 rig/sheet 的 1.7%% 全局尺度差")
    args = ap.parse_args()

    base = os.path.join(args.root, "characters", args.character, "forms", args.form)
    sp = os.path.join(base, "sprites")
    design = os.path.join(args.root, "characters", args.character, "design", "hands")
    with io.open(os.path.join(sp, "arm_parts.json"), encoding="utf-8") as f:
        armp = json.load(f)
    AP = {p["id"]: p for p in armp["parts"]}

    report = {"schema_version": "2.0", "parts": [], "checks": {},
              "note": "tools/make_hand_parts.py 产物。放松档=原画切件（只加腕部塗り足し），"
                      "张开/比心档=按原画风格生的图（design/hands/*_raw.png）键出配准而来。"
                      "Q36 那版程序化画的手已废弃——用户原话「完全成怪物了」"}

    # ---- Q52：先把原画切出来的放松手放大到正确尺寸 ----
    # 必须排在后面所有步骤**之前**：⓪ 擦袖口碎片、① 腕桩都要按放大后的手量。
    if abs(args.relax_scale - 1.0) > 1e-6:
        rescale_relaxed(sp, armp, args.relax_scale, report)
        AP = {p["id"]: p for p in armp["parts"]}
        with io.open(os.path.join(sp, "arm_parts.json"), "w", encoding="utf-8") as f:
            json.dump(armp, f, ensure_ascii=False, indent=2)

    # 层号：全部压在上臂（140/141）之下，且**不许和任何部件重号**。
    #   128/129 塗り足し圆盘 → 138/139 原画手（层号由 arm_parts 给，这里不动）
    #   130~133 两个差分档
    # 差分档层号低于原画手没关系：它们是靠 alpha 互斥的，同一时刻只有一张不透明。
    LAY = {("l", "pad"): 128, ("r", "pad"): 129,
           ("l", "open"): 130, ("l", "heart"): 131,
           ("r", "open"): 132, ("r", "heart"): 133}

    for side in ("l", "r"):
        src = AP[f"hand_{side}"]
        piv = src["pivot"]                       # 腕枢轴（切件画布坐标）

        # ---- ⓪ 把原画手件里**袖口的碎片**擦掉 ----
        # 切手的时候连着切进来一小块袖口（青底白条）。静止时它正好盖在袖子上
        # 看不出来，手腕一转就跟着甩出去 —— Q37 实拍 +70° 那格，腕子左下挂着
        # 一块青色（logs/asset_qa/q37_wrist_zoom.png）。
        # 判据选在**颜色**上是安全的：腕线以上本来就只该有皮肤，
        # 青/白/深色一律不是手。幂等：擦过一次之后再跑什么都不会少。
        hp = os.path.join(sp, f"hand_{side}.png")
        him = Image.open(hp).convert("RGBA")
        ax, ay = src["pos"]
        ha = np.asarray(him).astype(np.int16).copy()
        wrow = int(round(piv[1] - ay)) + 3
        band = ha[:max(0, wrow)]
        if band.size:
            r, g, b = band[:, :, 0], band[:, :, 1], band[:, :, 2]
            skin = (r > 205) & (g > 165) & (b > 140) & (r >= g) & (g >= b - 12)
            band[:, :, 3] = np.where(skin, band[:, :, 3], 0)
            ha[:max(0, wrow)] = band
            cleaned = Image.fromarray(ha.astype(np.uint8), "RGBA")
            if np.any(np.asarray(cleaned)[:, :, 3] != np.asarray(him)[:, :, 3]):
                cleaned.save(hp)
                report["checks"].setdefault("cuff_cleaned", []).append(f"hand_{side}")

        # ---- ① 腕部塗り足し：独立的一枚腕桩部件（挂在前臂上）----
        #     **绝不改写原画件**。第一版是把圆盘合进 hand_l.png 再扩框写回去，
        #     结果工具不幂等 —— 第二次跑会把"自己的产物"当原画又包一层，
        #     框越滚越大（82→98→114）。做成独立件就没这个问题，而且一枚圆盘
        #     同时垫在三档手下面，不用复制三遍。
        hw, up, dn = WRIST_HW * 2, WRIST_UP * 2, WRIST_DOWN * 2
        pw, ph = int(hw * 2) + 4, int(up + dn) + 4
        cx0, cy0 = pw / 2.0, up + 2
        pad = wrist_stub((pw, ph), (cx0, cy0), hw, up, dn)
        emit(sp, f"hand_{side}_pad", pad,
             (piv[0] - cx0 / 2.0, piv[1] - cy0 / 2.0), piv,
             LAY[(side, "pad")], f"forearm_{side}", report)

        # ---- ② 生图差分档 ----
        for pose in POSES:
            raw = os.path.join(design, f"hand_{pose}_raw.png")
            im, (wx, wy) = load_pose(raw, target_len=args.hand_len * 2)  # 2× 画布上量
            if side == "l":
                im = im.transpose(Image.FLIP_LEFT_RIGHT)
                wx = (im.width - 1) - wx
            cw2, ch2 = im.width + PAD * 4, im.height + PAD * 4
            canvas = Image.new("RGBA", (cw2, ch2), (0, 0, 0, 0))
            px, py = wx + PAD * 2, wy + PAD * 2
            canvas.alpha_composite(im, (PAD * 2, PAD * 2))
            emit(sp, f"hand_{side}_{pose}", canvas,
                 (piv[0] - px / 2.0, piv[1] - py / 2.0), piv,
                 LAY[(side, pose)], f"hand_{side}", report)

    # ---- 自检：腕线处的手宽必须盖得住袖口 ----
    for p in report["parts"]:
        im = Image.open(os.path.join(sp, p["id"] + ".png")).convert("RGBA")
        al = np.asarray(im)[:, :, 3]
        row = int(round(p["pivot"][1] - p["pos"][1]))
        row = max(0, min(al.shape[0] - 1, row))
        xs = np.nonzero(al[row] > 120)[0]
        p["wrist_w"] = int(xs.max() - xs.min() + 1) if len(xs) else 0
    report["checks"]["wrist_w"] = {p["id"]: p["wrist_w"] for p in report["parts"]}

    # make_rig 按这张表建差分参数（ParamHand{L,R}{Open,Heart}）。
    # 塗り足し圆盘 hand_*_pad 不在表里：它不是一档手势，是一直垫着的补片。
    report["poses"] = {"": "", **{p: p for p in POSES}}
    report["art_base"] = {s2: f"hand_{s2}" for s2 in ("l", "r")}

    out = os.path.join(sp, "hand_parts.json")
    with io.open(out, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print("手部件完成：%d 件（放松=原画件，张开/比心=生图件）" % len(report["parts"]))
    for p in report["parts"]:
        print("  %-14s %3dx%-3d @(%4d,%4d) 腕宽 %d"
              % (p["id"], p["size"][0], p["size"][1], p["pos"][0], p["pos"][1], p["wrist_w"]))


if __name__ == "__main__":
    main()
