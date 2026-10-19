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

掩膜怎么来
----------
1. `diff`   = 戴帽图与同发型不戴帽图的逐像素差 > 45。身体、夹克、裙子在两张图里
             一模一样 ⇒ 差分天然把帽子的下沿截在领口，不用手调。
2. `材质`   = 暖白布 ∪ 薄荷青 ∪ 线稿。三者都排掉**紫调**
             （`r-g>12 & b-g>12`）—— 头发不管被照亮还是落在阴影里，
             G 都是三通道里明显最低的那个，布料不会。
             实测不排的话，马尾被照亮那一侧 (223,202,224) 会整块混进「白布」。
3. `种子`   = 戴帽图有、不戴帽图没有的那圈**外凸轮廓**（`opA & ~dilate(opB,3)`）。
             这是确凿无疑的兜帽，拿它当测地重建的起点。
4. 生长     = 在材质区内从种子测地生长。生长走**腐蚀核**，断掉重采样噪点连出来的
             1~2px 细桥；不这么做会顺着夹克一路漏到鞋底（实测 bbox y 到 1479）。
5. 下巴以下只留**外沿带**：兜帽在下半截就是左右两条下垂的布带，
   而夹克的青色领子正好也在差分区里，会在帽口内侧挂出两撮「爪子」。

★ 两个踩过的坑，别再踩：
  · `hair_like()` 不能拿来排头发 —— 它用「离真发 15px 内的弱判据」召回高光，
    而帽口紧挨着头发，于是**白布的冷灰阴影整片被判成头发**，帽体只剩 9732px。
  · 「真发色」判据必须 `& ~teal_like` —— 阴影里的薄荷青内衬 (101,159,162)
    蓝会反超绿，正好落进 `b > g-6`。`teal_like` 的文档里写过这件事，我又踩了一遍。
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

#: 差分阈值。45 是实测下限：再低，重采样噪点会把整件夹克拉进来。
DIFF_T = 45
#: 兜帽下沿的硬限位（模板坐标）。肩线 436 + 124，留足帽子搭在肩上的部分。
YLIM = 560
#: 下巴以下只保留外沿这么宽的一条带（像素）。帽体在这一段就是两条下垂的布带。
RIM_BAND = 55


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


def erode_n(m, px):
    """腐蚀 px 像素（用 k=17 的 MinFilter 迭代，每次 8px）。"""
    cur = m
    done = 0
    while done < px:
        step = min(8, px - done)
        cur = C.erode(cur, 2 * step + 1)
        done += step
    return cur


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


def only_outer_runs(m, from_row):
    """from_row 以下，每行只留**最左和最右**那一段。

    兜帽在下巴以下就是左右两条下垂的布带，中间是脖子和衣领。
    夹克的青色领子也落在差分区里，不剔掉就会在帽口内侧挂出两撮「爪子」
    —— 实测 v5 四档全都有，肉眼一看就是脏东西。
    """
    out = m.copy()
    for y in range(from_row, m.shape[0]):
        runs = row_runs(m[y])
        if len(runs) <= 2:
            continue
        for x0, x1 in runs[1:-1]:
            out[y, x0:x1 + 1] = False
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


def grow(seed, allowed, k=9, maxit=250):
    """测地重建：在 allowed 里从 seed 长到不动点。"""
    cur = seed & allowed
    for i in range(maxit):
        nxt = C.dilate(cur, k) & allowed
        if nxt.sum() == cur.sum():
            return nxt, i
        cur = nxt
    return cur, maxit


def cut_one(style, design, chin, head_cx):
    """切一档，返回 {'hood': mask, 'hair': mask, 'A': rgba}。"""
    down_p, hood_p = SHEETS[style]
    A, op_a = C.key_rgba(os.path.join(design, hood_p))
    B, op_b = C.key_rgba(os.path.join(design, down_p))
    h, w = op_a.shape
    yy = np.arange(h)[:, None] * np.ones((1, w), np.int32)

    r, g, b = A[..., 0], A[..., 1], A[..., 2]
    diff = np.abs(A[:, :, :3].astype(np.int16)
                  - B[:, :, :3].astype(np.int16)).sum(2) > DIFF_T

    # ★ 紫调 = 头发（含被照亮的、落阴影的）和洋红反锯齿边；布料不会这样
    purple = (r - g > 12) & (b - g > 12)
    white = (np.minimum(np.minimum(r, g), b) > 150) & (r >= b - 4) & (~purple)
    teal = C.teal_like(A)
    dark = (np.maximum(np.maximum(r, g), b) < 150) & (~purple)
    skin = C.skin_like(A)
    # ★ 必须 & ~teal：阴影里的内衬 b 会反超 g，否则整圈内衬被当头发排掉
    hairc = (b > r + 6) & (b > 120) & (b > g - 6) & (~teal)

    allowed = (op_a & diff & (white | teal | dark)
               & (~skin) & (~hairc) & (yy <= YLIM))
    core = C.dilate(C.erode(allowed, 3), 3) & allowed       # 断 1~2px 噪点桥
    seed = op_a & (~C.dilate(op_b, 3)) & (yy <= YLIM)
    hood, _it = grow(seed, core)
    hood = C.dilate(hood, 5) & allowed
    hood, sizes = keep_parts(hood, 1200, box=(280, 40, 760, YLIM))
    hood = fill_small(hood, 900)

    # 下巴以下只留外沿带 + 每行只留最左最右那段：
    # 帽子在这一段只有两条下垂的布带，中间那两撮「爪子」是夹克的青领子。
    outer = row_fill(hood)
    rim = outer & ~erode_n(outer, RIM_BAND)
    hood = hood & (rim | (yy <= chin))
    hood = only_outer_runs(hood, chin)
    # ★★★ 下颌线以下**只留外布，内衬一律不要**（2026-10-19 补）。
    #   上面那条「只留外沿带」在帽子下半截失效：那里帽壳本来就窄，
    #   erode_n(outer, 55) 把整段吃光 ⇒ 全部算外沿 ⇒ 帽口内侧的薄荷青
    #   跟着留下来，渲染出来是下巴两边几片青色三角碎片 + 一道平切口
    #   （第一次实拍 logs/asset_qa/hood_zoom.png 一眼可见）。
    #   判据不靠阈值靠物理：下颌以下只看得见兜帽**搭在肩上的外面**，
    #   内衬被脸和脖子挡住，本来就不该出现。
    hood = hood & ~(teal & (yy > chin))
    # 去掉上一步切出来的零碎（孤立 1~2px 牙口），再按连通块筛
    hood = C.dilate(C.erode(hood, 3), 3) & hood
    # ★ 阈值只能给到 200：清掉「爪子」之后，下巴以下那两条下垂的布带
    #   就和主体断开了（原来它们是靠爪子连着的）。给 600 会把两条布带一起滤掉，
    #   帽子只剩一个光环，不像搭在肩上的兜帽 —— 实测内容框从 308x410 缩到 308x305。
    hood, _ = keep_parts(hood, 200, box=(280, 40, 760, YLIM))
    # ★★★ 下颌以下再单独筛一次连通块（2026-10-19 补）。
    #   上面那个 200 的阈值是为了保住「搭在肩上的两条下垂布带」，
    #   但它同时放行了一堆几百像素的碎渣 —— 渲染出来是下巴两侧的
    #   白/青三角片（twin/pony/long 三顶都有，short 那顶碰巧没有）。
    #   分区筛：下颌以上照旧（帽壳是一整块，不会误伤），
    #   下颌以下只留成规模的布带，碎渣一律丢。
    _above = hood & (yy <= chin)
    _below, _bs = keep_parts(hood & (yy > chin), 300,
                             box=(280, chin, 760, YLIM))
    hood = _above | _below
    # ★★★ 最后整体按连通块收口（2026-10-19 补）。
    #   成品兜帽是**一整块**：白外布 + 薄荷青罗纹内衬在帽口处本来就相连。
    #   上一版留下的残渣全是**和主体断开**的小块 —— 帽口内侧几片青三角、
    #   帽顶外面几粒白渣（见 logs/asset_qa/hood_sprites.png 第一版）。
    #   所以判据不是"多大算渣"而是"连不连得上主体"：只留最大的那一块。
    #   阈值给 3000 作下限兜底（真·主体两万多像素，差着一个量级）。
    #   ★ 只能"丢小块"不能"只留最大块"：pony / long 两顶的帽壳本来就被
    #     帽口开口分成两三大块，只留最大的会掉一半（实测 26541 -> 12906）。
    hood, _fs = keep_parts(hood, 1200, box=(280, 40, 760, YLIM))

    # 戴帽时露在帽子外面的头发 = **帽子整个剪影之外**的发色像素。
    # 剪影要用 row_fill 不能用 fill_holes（马蹄形不闭合，见函数注释）。
    # ★ row_fill 会把**帽口的开口**也算进剪影，所以只在下巴以上生效：
    #   上半截要挡住的是帽口里的刘海（底图本来就有，不该重复切）；
    #   下半截必须放行，不然从帽口垂下来的发尾会被整条腰斩
    #   —— 实测双马尾件高度从 1149 掉到 378。
    hood_sil = C.dilate(row_fill(hood) & (yy <= chin + 30), 5)
    # ★ 要一条**饱和度闸**：夹克胸口那对白抽绳、夹克前襟的冷白边，
    #   都落在 `hair_like` 的弱判据里（b 比 r 高一两点）且紧挨着长发，
    #   会被召回成「头发」。头发哪怕高光处也有 10 以上的色差，白绳只有 2~4。
    sat = (np.maximum(np.maximum(r, g), b) - np.minimum(np.minimum(r, g), b))
    hairm = (op_a & C.hair_like(A) & (~teal) & (~skin)
             & (sat >= 6) & (~hood_sil))
    hairm = C.despeckle(hairm, 5, 9)
    hairm, hsizes = keep_parts(hairm, 1500)
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
    head_cx = (bbox[0] + bbox[2] + 1) / 2.0
    C.log("底图 bbox %s  缩放 %.6f  下巴 y=%d（模板坐标）" % (str(bbox), scale, chin))

    geom = collections.OrderedDict()
    dbg = {}
    for style in [s.strip() for s in a.styles.split(",") if s.strip()]:
        cut = cut_one(style, design, chin, head_cx)
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
