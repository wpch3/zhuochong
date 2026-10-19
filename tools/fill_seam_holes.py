#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""给相邻部件**对接处**补塗り足し（のりしろ），消掉合成后露出来的针孔和方块窟窿。

★ 这一步在修什么（2026-10-19 第二十问「还是有块状……甚至有地方没有链接到」）
  把 rig 的件按层序合成之后，在**实体内部**会残留一批透明像素：

      档位      实体面积      内部窟窿
      short     270137 px      3194 px
      pony      301970 px      4370 px
      twin      301246 px      5279 px
      long      336271 px      4036 px

  它们不是"背景"，是两件各自切得干干净净、边缘**正好对上却没有重叠**时露出
  的缝。缝宽 1~3 px，放到屏幕上就是用户说的"块状"——尤其在脸颊右缘
  （seg_head 的边）和 acc_hair_crown_* 的内缘之间，缝被拉成一条直角折线，
  看起来像有人拿橡皮擦出了方块。

★ 为什么是"补"而不是"把边切大一点"
  Live2D 官方和各家拆件教程对这件事是同一个说法：**切り分けたパーツには
  のりしろ（塗り足し）を付けて、隣のパーツの下に潜り込ませる**。
    - https://tips.clip-studio.com/ja-jp/articles/2684
      「切り分けた後には元絵と重ねあわせて不足パーツを必ず確認」
      塗り足しが短いと「頬から髪の毛が生えている」ように見える
    - https://shiroikarasu.net/live2d-part-separation-illustrator-guide/
      のりしろは隣接パーツの**下まで伸ばす**／髪の先端は体レイヤーの下へ潜らせる
    - https://docs.live2d.com/en/cubism-editor-tutorials/psd/
      元画で隠れていた部分の描き足しを忘れずに
  也就是说：缝不能靠"对得更准"来消除（变形一动就又开），只能靠**让下面那件
  多长出来一截**，被上面那件盖住。件会动，所以必须有富余。

★ 做法
  1. 把 hairstyle × hood_pose 所有组合都合成一遍，取「闭运算填得上、但当前
     透明」的像素 = 内部窟窿。各档取并集（件在不同档可见性不同，缝的位置也不同）。
  2. 往外扩 SEAM_GROW px —— 这就是のりしろ的宽度，保证件轻微位移时缝不会重开。
  3. 每个窟窿像素交给**该姿态下可见、且紧邻（2px 内）的件里层序最低的那一个**。
     为什么挑最低的：のりしろ是"下面那件长出来"，补到上面那件会盖住本该露出
     的邻居。挑最低的那件，补出来的像素一定被原来压在它上面的件继续压着，
     只有从缝里才看得见。
     ★ 踩过的坑（必须保留这三条约束，少一条就出事）：
       a) "紧邻"必须卡到 2px。第一版用 7px，acc_tail_cat_up（层 31）这种
          又大又低的件把几百像素外的窟窿全抢走了，补出来直接改了猫尾剪影。
       b) 候选件必须**在产生这个窟窿的那一档里可见**。拿 long 档的缝去补
          只在 pony 档出现的件，等于凭空长肉。
       c) 补出来的像素，必须在**该件可见的每一个姿态**里都落在剪影之内
          （实体 ∪ 窟窿）。只验一个姿态的话，换个姿态盖它的件没了，
          这块补丁就会从轮廓上支出来。
       d) fx_* 特效件不参与 —— 它们本来就是半透明飘浮物，没有"接缝"可言。
  4. 颜色取**合成图上最近的不透明像素**，不是取该件自己的边缘色。
     踩过的坑：早先给 seg_torso 补接缝时用件自己的 nearest_fill，把衣领刷成了
     肉色（件自己最近的边是脖子）。缝两侧长什么样，补进去就该是什么样。
  5. 同一张贴图的 1× 和 @2x 都要补，否则高清档会继续露缝。

★ 形变态也要补（否则静态补干净反而把闸门做红）
  check_assets 的「关节不露底」「头发摆动不露底」两闸算的是
  **形变后的空洞 − 静止时的空洞**。只补静止态，分母小了差值反而变大
  （实测 132/60、31/20）。所以这里把发丝甩动 ±12px 也当成一个"姿态"
  合成进来，把发丝背后本该有脸却没画的地方一并补上 —— 这正是
  docs.live2d.com 的 PSD 教程要求的「元画で隠れていた部分の描き足し」。
  关节带（颈/肩/髋/肘 ±2*overlap_px）则整段排除：那里的露底靠分段件自带的
  38px 重叠带兜着，是另一套机制，接缝补画插手只会把它的基线搅乱。

幂等：补过的像素下一轮就不再是窟窿，重复跑结果不变。
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

# のりしろ宽度（1× 像素）。取 3 —— 这个数是被闸门逼出来的，别往回调：
# 取 1 px 时静态档的缝补上了，但「关节不露底(颈)」和「头发摆动不露底」两闸反而
# 变红（132/60、27/20）。原因是件一变形，1 px 的余量就被拉开，缝重新裂开；
# 而静态基线已经补干净了，于是"形变后**新增**的空洞"这个差值反而变大。
# のりしろ本来就是为"件会动"准备的，扩到 3 px 让补出来的像素真正**潜到邻件下面**，
# 变形时才扯不开。再大就没必要了：所有补出来的像素都被 safe 约束卡在剪影内，
# 继续加只是把邻件底下涂得更厚。
SEAM_GROW = 3
# 闭运算口径：判定「这是被实体包围的内部窟窿」而不是「人物外面的背景」。
# 取 9 —— 比最宽的缝（3 px）大一圈，又小于任何一处真正的镂空（腋下、发丝间隙）。
CLOSE_K = 9
# 单个窟窿连通块超过这个面积就不补：那不是接缝，是真的缺件，
# 硬补会糊出一坨色块，必须回上游去修（本轮长发断缕就是这种，已在切件器修掉）。
MAX_BLOB = 400
# 发丝甩动的模拟幅度，跟 check_assets 的「头发摆动压力测试」对齐（±12px）。
SWAY = 12
# 关节带半宽 = 2 × body_parts.overlap_px，跟 check_assets 的 ov*2 对齐。
JOINT_BAND = 2


def _norm(v, d):
    if v is None:
        return (d, d)
    if isinstance(v, (list, tuple)):
        return (float(v[0]), float(v[1]))
    return (float(v), float(v))


def _dilate(m, k):
    return np.asarray(Image.fromarray((m * 255).astype("uint8"))
                      .filter(ImageFilter.MaxFilter(k))) > 127


def _erode(m, k):
    return np.asarray(Image.fromarray((m * 255).astype("uint8"))
                      .filter(ImageFilter.MinFilter(k))) > 127


def _blobs(mask):
    """手写连通域（本机没有 scipy）。返回 [(面积, ys, xs), ...]。"""
    h, w = mask.shape
    lab = np.zeros((h, w), dtype=np.int32)
    out = []
    cur = 0
    ys0, xs0 = np.nonzero(mask)
    for sy, sx in zip(ys0.tolist(), xs0.tolist()):
        if lab[sy, sx]:
            continue
        cur += 1
        stack = [(sy, sx)]
        lab[sy, sx] = cur
        pts = []
        while stack:
            y, x = stack.pop()
            pts.append((y, x))
            for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                ny, nx = y + dy, x + dx
                if 0 <= ny < h and 0 <= nx < w and mask[ny, nx] and not lab[ny, nx]:
                    lab[ny, nx] = cur
                    stack.append((ny, nx))
        ys = np.array([p[0] for p in pts])
        xs = np.array([p[1] for p in pts])
        out.append((len(pts), ys, xs))
    return out


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


def _pose_combos(rig):
    """hairstyle × hood_pose 的所有组合（含「都不选」的基础档），再乘上发丝甩动。"""
    groups = {g["id"]: [e["id"] for e in g["entries"]] for g in rig.get("poses", [])}
    hair = ["none"] + groups.get("hairstyle", [])
    hood = ["down"] + [h for h in groups.get("hood_pose", []) if h != "down"]
    out = []
    for a in hair:
        for b in hood:
            for dx in (0, -SWAY, SWAY):
                out.append({"hairstyle": a, "hood_pose": b, "sway": dx,
                            "hide": ()})
    # ★ 再加一组「藏件场景」，照着 check_assets 的「藏X有件接管」闸的做法来：
    #   某一档会把 hair_back 之类的本体件藏掉，藏掉之后**背后必须有东西**。
    #   不把这种场景算进来的话，补缝会把 own 撑大、把 rest 的分母缩小，
    #   剩下那点 rest 按比例反而更空（实测 1.90% → 2.58%，闸门越补越红）。
    #   把它当成一个正经姿态合成一遍，背后缺的像素就会被正常派给低层件补上。
    for g in rig.get("poses", []):
        for ent in g.get("entries", []):
            hid = tuple(ent.get("hide") or ())
            if hid:
                out.append({"hairstyle": ent["id"] if g["id"] == "hairstyle" else "none",
                            "hood_pose": "down", "sway": 0, "hide": hid})
    return out


def _sways(pid, dx):
    """哪些件跟着甩：鬓发/后发/侧垂发这些挂在头上的长件。"""
    if dx == 0:
        return False
    return (pid.startswith("hair_side") or pid == "hair_back"
            or pid.startswith("acc_hair_sidelong") or pid in ("acc_hair_long",)
            or pid.startswith("acc_hair_twin") or pid == "acc_hair_pony")


def _nearest_color(rgb, opaque, targets):
    """给 targets 里每个像素取**合成图上最近的不透明像素**的颜色。

    逐步膨胀 opaque 并记录"这一圈是从哪一轮长出来的"，等价于一次
    多源 BFS 距离变换；没有 scipy，这样写最省事也够快（窟窿只有几千像素）。
    """
    h, w = opaque.shape
    filled = opaque.copy()
    col = rgb.copy()
    need = targets & ~filled
    for _ in range(24):
        if not need.any():
            break
        grown = _dilate(filled, 3) & ~filled
        if not grown.any():
            break
        ys, xs = np.nonzero(grown)
        # 四邻里已有颜色的平均值
        acc = np.zeros((len(ys), 3))
        cnt = np.zeros((len(ys), 1))
        for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            ny = np.clip(ys + dy, 0, h - 1)
            nx = np.clip(xs + dx, 0, w - 1)
            ok = filled[ny, nx]
            acc[ok] += col[ny[ok], nx[ok]]
            cnt[ok, 0] += 1
        cnt[cnt == 0] = 1
        col[ys, xs] = acc / cnt
        filled |= grown
        need = targets & ~filled
    return col


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
    all_parts = sorted(rig["parts"], key=lambda q: float(q.get("layer", 0)))

    # 关节带整段不补：那里的露底由分段件自带的 overlap_px 重叠带负责，
    # 跟 check_assets「关节不露底」闸是配套的一套机制。接缝补画插进去会把
    # 那个闸的静止基线搅乱（实测颈部 60 → 132），而且本来也不是用户看到的块状。
    # 会被某一档 hide 掉的件，不参与接缝补画。
    # 「藏X有件接管」闸量的是**被藏件自己的面积**里有多少露了底；把被藏件补大，
    # 等于把那个闸的分母撑大（实测 hair_back 补了 1141px，long 档 1.90% → 2.20%
    # 直接越过 2% 上限）。而且补了也会被藏掉，本来就没意义。
    hidden_ids = set()
    for g in rig.get("poses", []):
        for ent in g.get("entries", []):
            hidden_ids.update(ent.get("hide") or [])

    joint_ok = np.ones((H, W), dtype=bool)

    # 被藏件**所占的那块地方**也整片不补。
    # 「藏X有件接管」闸算的是 hole = (X 的面积 − 这一档自己的件) 里有多少没背衬，
    # 而且只合成 layer < X 的件当背衬。给 acc_hair_long（层 58）补缝会把
    # 「这一档自己的件」撑大 → 分母 rest 缩小 → 剩下那点按比例更空，
    # 实测 1.90% → 2.58%，补得越多闸越红。把被藏件的地盘整片划出去，
    # 这个闸就原样保持基线；那块在后脑勺，本来也不是用户看到的块状。
    try:
        bp = json.load(open(os.path.join(base, "sprites", "body_parts.json"),
                            encoding="utf-8"))
        ap = json.load(open(os.path.join(base, "design", "anchors.json"),
                            encoding="utf-8"))["points"]
        ov = int(bp["overlap_px"]) * JOINT_BAND
        sw, sh = bp["image_size"]
        ys = float(H) / float(sh)
        for name in ("neck", "shoulder", "shoulder_l", "shoulder_r", "hip",
                     "elbow_l", "elbow_r"):
            if name not in ap:
                continue
            y = int(round(float(ap[name][1]) * ys))
            joint_ok[max(0, y - ov):min(H, y + ov), :] = False
        log(f"  关节带排除：overlap {bp['overlap_px']}px ×{JOINT_BAND} → "
            f"{int((~joint_ok[:, 0]).sum())} 行不补")
    except (OSError, KeyError, ValueError) as e:
        log(f"  （读不到关节锚点，全图都补：{e}）")


    cache = {}
    for p in all_parts:
        cache[p["id"]] = _place(base, p, W, H)
    by_all = {p["id"]: p for p in all_parts}
    hid_area = np.zeros((H, W), dtype=bool)
    for pid in hidden_ids:
        if pid in by_all:
            hid_area |= cache[pid][0][..., 3] > 0.5
    if hid_area.any():
        joint_ok &= ~hid_area
        log(f"  被藏件地盘排除：{len(hidden_ids)} 个件，{int(hid_area.sum())} px 不补")

    # ---- 1. 逐姿态合成，记下每一档的实体、窟窿、可见件 ----
    per = {}
    scenes = []
    for picks in _pose_combos(rig):
        vis = hs.visible_ids(rig, picks)
        comp = np.zeros((H, W, 3))
        al = np.zeros((H, W))
        vis = vis - set(picks["hide"])
        for p in all_parts:
            if p["id"] not in vis:
                continue
            arr = cache[p["id"]][0]
            if _sways(p["id"], picks["sway"]):
                arr = np.roll(arr, picks["sway"], axis=1)
            pa = arr[..., 3]
            comp = arr[..., :3] * pa[..., None] + comp * (1 - pa[..., None])
            al = pa + al * (1 - pa)
        op = al > 0.5
        hl = _erode(_dilate(op, CLOSE_K), CLOSE_K) & ~op
        # 大块的不是接缝，是真缺件 —— 不补，留给上游（本轮长发断缕就是这种）
        keep = np.zeros_like(hl)
        for n, ys, xs in _blobs(hl):
            if n <= MAX_BLOB:
                keep[ys, xs] = True
        key = (f"{picks['hairstyle']}/{picks['hood_pose']}/{picks['sway']:+d}"
               + (f"/-{'+'.join(picks['hide'])}" if picks["hide"] else ""))
        per[key] = (int(hl.sum()), int(keep.sum()))
        # ★ rgb 必须存 uint8。存 float64 的话 33 个场景就是 900MB，
        #   沙箱直接 OOM kill（exit 137，日志只留下第一行）。
        scenes.append({"key": key, "sway": picks["sway"],
                       "vis": vis, "op": op, "holes": keep,
                       "rgb": (comp * 255.0).clip(0, 255).astype(np.uint8),
                       "allow": op | keep})
    for k, (tot, kept) in per.items():
        log(f"    {k:14s} 内部窟窿 {tot:5d} px，其中接缝级 {kept:5d} px")

    if not any(s["holes"].any() for s in scenes):
        log("  没有要补的接缝。")
        return 0

    # ---- 2. 约束 c：每个件在它**可见的所有姿态**里的允许区取交集 ----
    #        补出来的像素落在交集里，才保证任何一档的剪影都不会被改。
    safe = {}
    for p in all_parts:
        pid = p["id"]
        sc = [s for s in scenes if pid in s["vis"]]
        if not sc:
            continue
        m = sc[0]["allow"].copy()
        for s in sc[1:]:
            m &= s["allow"]
        safe[pid] = m

    # ---- 3. 逐姿态把窟窿派给「可见 + 紧邻 2px + 层序最低」的件 ----
    near_k = SEAM_GROW * 2 + 1            # 2px 邻域
    assign = {}
    skipped = 0
    for s in scenes:
        # のりしろ：窟窿外扩 SEAM_GROW px，让补出来的像素潜到邻件下面
        left = _dilate(s["holes"], near_k) & s["allow"] & joint_ok
        s["assigned"] = np.zeros((H, W), dtype=bool)
        for p in all_parts:                            # 已按 layer 升序
            if not left.any():
                break
            pid = p["id"]
            if (pid.startswith("fx_") or pid not in s["vis"]
                    or pid in hidden_ids):
                continue                               # 约束 b + d + 被藏件
            pa = cache[pid][0][..., 3] > 0.5
            if _sways(pid, s["sway"]):
                # 甩动档里这件已经挪走了，邻接要按**挪过去之后**的位置判，
                # 否则会把"发丝原来盖着、现在露出来的洞"又派回给发丝自己。
                pa = np.roll(pa, s["sway"], axis=1)
            if not pa.any():
                continue
            near = _dilate(pa, near_k) & left          # 约束 a
            near &= safe.get(pid, np.zeros((H, W), bool))   # 约束 c
            if near.any():
                assign[pid] = assign.get(pid, np.zeros((H, W), bool)) | near
                s["assigned"] |= near
                left &= ~near
        skipped += int(left.sum())
    if skipped:
        log(f"    （{skipped} px 没有安全的归属，跳过不补）")

    grow = np.zeros((H, W), dtype=bool)
    for m in assign.values():
        grow |= m
    log(f"  判定为接缝并安全归属 {int(grow.sum())} px")

    # ---- 4. 颜色：**在哪一档发现的缝，就从哪一档的合成图上取色** ----
    #        踩过的坑：第一版统一从 none/down 档取色，而 acc_hair_twin_* 在那一档
    #        根本不可见，取到的是短发档那个位置的皮肤/背景色，补进去把双马尾的
    #        平均色拉歪了 ——「与本体头发同源配色」闸直接红（ΔE 7.5 / 上限 5.0）。
    #        缝两侧在那一档长什么样，补进去就该是什么样。
    col = np.zeros((H, W, 3))
    colset = np.zeros((H, W), dtype=bool)
    for s in scenes:
        want = s["assigned"] & ~colset
        if not want.any():
            continue
        cs = _nearest_color(s["rgb"].astype(np.float64) / 255.0, s["op"], want)
        col[want] = cs[want]
        colset |= want

    # ---- 5. 写回贴图（1× 和 @2x 都要） ----
    by = {p["id"]: p for p in all_parts}
    total = 0
    for pid, mask in sorted(assign.items(), key=lambda kv: -int(kv[1].sum())):
        p = by[pid]
        ox, oy, pw, ph = cache[pid][1]
        sx, sy = _norm(p.get("scale"), 1.0)
        ys, xs = np.nonzero(mask)
        rel_x = xs - ox
        rel_y = ys - oy
        files = [(p["file"], 1.0)]
        stem, ext = os.path.splitext(p["file"])
        if stem.endswith("@2x"):
            sib = stem[:-3] + ext
            if os.path.exists(os.path.join(base, sib)):
                files.append((sib, 0.5))
        else:
            sib = stem + "@2x" + ext
            if os.path.exists(os.path.join(base, sib)):
                files.append((sib, 2.0))
        n_written = 0
        for fn, mul in files:
            fp = os.path.join(base, fn)
            im = Image.open(fp).convert("RGBA")
            arr = np.asarray(im).copy()
            # canvas → 该贴图自己的像素网格
            fx = rel_x / max(1e-6, sx) * mul
            fy = rel_y / max(1e-6, sy) * mul
            r = max(1, int(round(mul / max(sx, 1e-6))))
            hit = 0
            for dy in range(r):
                for dx in range(r):
                    px = np.round(fx).astype(int) + dx
                    py = np.round(fy).astype(int) + dy
                    ok = (px >= 0) & (px < arr.shape[1]) & (py >= 0) & (py < arr.shape[0])
                    if not ok.any():
                        continue
                    c = (col[ys[ok], xs[ok]] * 255.0).clip(0, 255).astype(np.uint8)
                    arr[py[ok], px[ok], :3] = c
                    arr[py[ok], px[ok], 3] = 255
                    hit += int(ok.sum())
            Image.fromarray(arr).save(fp)
            n_written = max(n_written, hit)
        total += int(mask.sum())
        log(f"    {pid:24s} layer {p.get('layer'):>4}  补 {int(mask.sum()):5d} px")
    log(f"  合计塗り足し {total} px，涉及 {len(assign)} 个件")

    rep = os.path.join(base, "sprites", "seam_fill_report.json")
    json.dump({"grow_px": SEAM_GROW, "close_k": CLOSE_K, "max_blob": MAX_BLOB,
               "per_pose": {k: {"holes": v[0], "seam": v[1]} for k, v in per.items()},
               "filled_px": total,
               "parts": {k: int(v.sum()) for k, v in assign.items()}},
              open(rep, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
