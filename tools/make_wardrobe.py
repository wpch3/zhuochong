#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""衣柜：生成换装包（A49 / T45.5~T45.7）。

引擎这边**早就通了** —— `zrig_apply_outfit()` 按部件覆盖 file/pos/scale/layer，
`/api/outfit?id=` 和调试台按钮（web/test.js:185）都在。缺的从来只是素材。
这个脚本就是补素材那一环。

官方对照（Cubism 2《モデルの切り替え方式の検討》）：
  · **テクスチャ方式** —— 「モデル読み込み後、テクスチャ設定命令でテクスチャを切り替えます・
    色変更などが簡単にできる」。`zrig_apply_outfit` 就是这个，三档换装全走它。
  · パーツα方式（按 id 切显隐）= 我们的 `poses`，官方说那是给**腕替え**用的。
  · moc 切り替え方式 = 我们的 `forms/`，官方说**服替え一般用这个**。

★ 两种换色手法，按**件里有几种衣物**选，不许混用：
  1. **程序化**（`mode: "shift"`）：这一件只有一种衣物、且和皮肤不撞色时用。
     实测 `arm_l_upper` = 80.2% 袖青 + 11.1% 袖口青 + 0 皮肤 ⇒ 安全。
     做法是保留明暗差的平移 `out = target + (px − source)`，阴影和高光原样跟着走。
  2. **AI 重绘**（`mode: "repaint"`）：一件里塞了好几种衣物、颜色互相纠缠时用。
     实测 `seg_torso` 里外套白被判成「袜 #F6F2F0」、「外套主体 #F0F0F0」连前六都没进，
     而 `seg_leg_l` 的**腿部皮肤**被判成「衬衫 #FCE8D8」—— **按颜色分不开，会把皮肤一起染了**。
     所以躯干只能整张重画，拿原件当参考图保住姿势与剪影。

★ 重绘件的硬验收：**剪影 IoU ≥ iou_min**（默认 0.97）。对不齐的贴图换上去
  就是身体错位，这条过不了就不许出包。

★ 2026-10-18：比剪影之前，先把**烘进肩膀的鲍勃发梢**从 AI 件上擦掉。
  这些重绘素材是照着**没清理过的** seg_torso 画的，所以 AI 把那两撮蓝发梢
  当成衣服的一部分照抄了下来。rebuild 第 19 步（clean_baked_residue.py）
  把它们从原件上擦掉之后，两边就对不上了（IoU 掉到 0.948）——
  但这不是「身体错位」，是**原件瘦了而重绘件没跟着瘦**。
  照搬同一张发梢掩码再比，闸门量的才是它该量的东西（姿势有没有跑）。
  顺带一提：擦不擦都不影响出包的像素，因为输出 alpha 一律取原件的。
"""
from __future__ import annotations

import argparse
import io
import json
import os
import sys
import sys

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import clean_baked_residue as cbr                              # noqa: E402


sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import split_skirt as sp_skirt      # noqa: E402  （recolor_ring / DARK 共用一份实现）
import make_skirt_parts as sp_skirt_parts  # noqa: E402

DARK = sp_skirt_parts.DARK


def unhaired(mask: np.ndarray, scale: int) -> np.ndarray:
    """比剪影时把**肩膀那条带**排除掉。

    躯干的换装重绘素材是照着\"没清理过的\" seg_torso 画的，所以 AI 把烘在肩上的
    那两撮鲍勃发梢当成衣服一起抄了下来。rebuild 第 19 步
    （clean_baked_residue.py）把它们从原件上擦掉之后，AI 件就比原件多出 13718
    个像素，IoU 从 0.977 掉到 0.948 —— 这不是\"身体错位\"，是\"原件瘦了\"。

    ★ 为什么不照着 clean_baked_residue 再算一遍发梢掩码？试过，不行：
      那套判据是**认颜色**的（淡紫发身 / 蓝发梢），而换装件本来就是**改了颜色**
      的（midnight 是深蓝一套），深蓝衣料会被当成蓝发梢整片吃掉 —— 实测多削
      7643 像素，两个肩头被咬出三角缺口，IoU 反而只回到 0.960。
    ★ 所以改成\"按位置\"排除：发梢按定义只会落在 clean_baked_residue 划定的
      肩带（TORSO_HAIR_MAX_Y 以上）里。去掉这条带之后，**清理前后算出来的
      IoU 一模一样，都是 0.9778** —— 正好证明差额全在带子里、带子外面纹丝未动。
      带子以下 0.97 的闸原封不动，该拦的照样拦。
    """
    out = mask.copy()
    out[:int(cbr.TORSO_HAIR_MAX_Y * scale)] = False
    return out


def key_magenta(rgb: np.ndarray) -> np.ndarray:
    """洋红底 → 覆盖度 0..1（和 check_assets.py:741 的残留闸同一套判据）。"""
    r, g, b = (rgb[..., i].astype(int) for i in range(3))
    mag = (r - g > 60) & (b - g > 60) & (r > 150) & (b > 150)
    return (~mag).astype(np.float64)


def skirt_alpha(src_path: str, sc: int):
    """躯干原件的**完整剪影**：已挖空的躯干 alpha ∪ 裙子那块（T66.16 之后必须补回来）。

    ★ 为什么 IoU 不能拿挖空后的躯干当参照：`split_skirt.py` 把裙子从 seg_torso 里
      切走了，而 AI 重绘素材是照着**拆件前**那张画的 —— 它还带着裙子。不补回来
      IoU 会掉到 0.68，闸门报"身体错位"，其实一个像素都没错位（midnight 实测 0.6823）。
      这和 2026-10-18 擦发梢那次是同一类问题：**参照物和被测物必须描述同一个形状**。
    ★ 补回来的那块用 `skirt_mask.png`（含のりしろ）而不是 base：换装躯干先按"完整剪影"
      出包，紧接着 `cut_outfit_skirt()` 会用 base 掩膜挖干净并把裙子切成独立件。
    """
    m = os.path.join(os.path.dirname(src_path), "skirt_mask.png")
    if not os.path.exists(m):
        return None
    mm = np.asarray(Image.open(m).convert("L")) > 0
    return np.kron(mm, np.ones((sc, sc), bool)) if sc > 1 else mm


def repaint(src_path, ai_path, out_path, iou_min, mode="repaint",
            grow_max=0.03, shrink_max=0.06):
    """AI 重绘件：键洋红 → 缩到原件的**精确尺寸** → 按模式核剪影。

    两种模式，判据不一样 —— 这是实测逼出来的分家：
      · **repaint（换色）**：只改颜色，剪影该一动不动 ⇒ 卡 IoU。
        实测 midnight 外长 2.2% / 内缩 0.2%，IoU 0.977。
      · **restyle（换件 / 整套）**：换成别的衣服，**剪影本来就会变**。
        实测 cocoa（粗针织开衫换棒球外套）外长 8.4% —— 开衫就是比夹克厚，
        这不是 bug。官方也这么说：「レイヤー間が近すぎると**今の形よりも
        大きなコスチュームへの変更が難しくなります**」，意思就是换装要留长大的余地。
        所以 restyle 卡的是**外长上限**和**内缩上限**，不是 IoU。

    ★ 剪影一律用**原件的** alpha，不用 AI 的键色结果：原件边缘是切件器精修过的，
      AI 那圈抗锯齿噪声直接用会让剪影发毛。
    ★ 但这样一来，AI **没画到**的那部分（内缩区）就会在身上留洋红斑 ——
      所以内缩区要做最近邻补色。cocoa 内缩 2.9%，不补就是一身紫点。
    """
    orig = Image.open(src_path).convert("RGBA")
    ai = Image.open(ai_path).convert("RGB")
    if ai.size != orig.size:
        ai = ai.resize(orig.size, Image.LANCZOS)   # 生成模型常常换个分辨率回来
    n = np.asarray(ai).astype(np.uint8)
    B = key_magenta(n) > 0.5
    A = np.asarray(orig)[..., 3] > 128
    if os.path.basename(src_path).startswith("seg_torso"):
        sc = 2 if "@2x" in src_path else 1
        A, B = unhaired(A, sc), unhaired(B, sc)
        sf = skirt_alpha(src_path, sc)
        if sf is not None and sf.shape == A.shape:
            A = A | sf            # 参照物补回"已经切出去的那条裙子"（见 skirt_alpha 的说明）
    inter = float((A & B).sum())
    iou = inter / float((A | B).sum())
    grow = float((B & ~A).sum()) / float(A.sum())
    shrink = float((A & ~B).sum()) / float(A.sum())
    if mode == "repaint":
        if iou < iou_min:
            raise SystemExit(f"[衣柜] {os.path.basename(out_path)} 剪影 IoU {iou:.4f} "
                             f"< {iou_min} —— 换色不该改剪影，换上去会身体错位")
    else:
        if grow > grow_max or shrink > shrink_max:
            raise SystemExit(
                f"[衣柜] {os.path.basename(out_path)} restyle 外长 {grow:.1%} "
                f"(上限 {grow_max:.0%}) / 内缩 {shrink:.1%} (上限 {shrink_max:.0%})"
                f" —— 超了就不是『换了件衣服』而是『换了个身体』")

    # 内缩区补色：从最近的已画像素扩散过去，补完不许再有洋红
    px = n.astype(np.int16)
    # ★ 补色的「洞」不止是纯洋红，**还要算上洋红的抗锯齿边**。
    #   第一版只排除严格洋红，结果扩散时把边上那圈半洋红的紫色吸了进来，
    #   cocoa 的肩膀上糊了一片紫斑（既有教训：最外圈半透明像素颜色不可信）。
    _r, _g, _b = (n[..., i].astype(int) for i in range(3))
    contam = (_r - _g > 25) & (_b - _g > 25) & (_r > 110) & (_b > 110)
    hole = A & (~B | contam)
    if hole.any():
        for _ in range(64):
            if not hole.any():
                break
            # ★ 补色的**来源**也要先腐蚀一圈。第二版只把污染像素算进「洞」，
            #   但扩散时仍然从紧挨洞的像素取色 —— 那一圈恰恰是半洋红的。
            #   先腐蚀 1 px 再取，紫斑才干净。
            src = ~hole & A
            er = src.copy()
            for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                er &= np.roll(src, (dy, dx), (0, 1))
            src = er if er.any() else src
            acc = np.zeros(px.shape, np.int32)
            cnt = np.zeros(px.shape[:2], np.int32)
            for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                sh = np.roll(np.where(src[..., None], px, 0), (dy, dx), (0, 1))
                sm = np.roll(src, (dy, dx), (0, 1))
                acc += sh * sm[..., None]
                cnt += sm
            fill = hole & (cnt > 0)
            if not fill.any():
                break
            px[fill] = (acc[fill] // np.maximum(cnt[fill], 1)[:, None])
            hole = hole & ~fill
    # 扩散够不到的孤立洞（被洋红包围的小坑）用**原件同位置的像素**兜底 ——
    # 几何完全一样，原图那个点就是正确内容，比继续猜一个颜色靠谱。
    rest = A & (key_magenta(np.clip(px, 0, 255).astype(np.uint8)) < 0.5)
    if rest.any():
        px[rest] = np.asarray(orig)[..., :3][rest]
    # ★ alpha 要按**参照剪影 A** 出，不能只看原件的 alpha：原件（seg_torso）在
    #   T66.16 之后已经把裙子那块挖空了，照抄它的 alpha 会把这套衣服画好的裙子
    #   一起抹成透明 —— 换上去就是"裙子变成一个大洞、后面露出大腿"
    #   （Q 版/少女都实测过：piece 只剩 26268 px，皮肤从洞里透出来）。
    alpha_out = np.asarray(orig)[..., 3].copy()
    alpha_out[A] = 255
    out = np.dstack([np.clip(px, 0, 255), alpha_out]).astype(np.uint8)
    left = int((A & (key_magenta(out[..., :3]) < 0.5)).sum())
    if left:
        raise SystemExit(f"[衣柜] {os.path.basename(out_path)} 补色后身上还有 "
                         f"{left} 个洋红像素")
    if rest.any():
        print(f"      （{int(rest.sum())} 个孤立洞用原件像素兜底）")
    # ★ 最后一道：连**偏**洋红都不许剩。严格判据放得过去的半洋红边
    #   会在肩膀上糊成紫斑，肉眼一看就穿帮，但严格闸测不出来。
    fr, fg, fb = (out[..., i].astype(int) for i in range(3))
    tinted = int((((fr - fg > 25) & (fb - fg > 25) & (fr > 110) & (fb > 110)) & A).sum())
    if tinted > A.sum() * 0.001:
        raise SystemExit(f"[衣柜] {os.path.basename(out_path)} 身上还有 {tinted} 个"
                         f"偏洋红像素（上限 {int(A.sum() * 0.001)}）—— 补色没补干净")
    Image.fromarray(out, "RGBA").save(out_path)
    return iou, grow, shrink


def shift(src_path, out_path, pairs, tol):
    """程序化换色：保明暗差的平移。

    `out = target + (px − source)` —— 平移而不是替换，所以这一块衣物原本的
    阴影、高光、布料褶皱的明暗关系**原样保留**。直接把整块涂成目标色会变成一张贴纸。
    """
    im = Image.open(src_path).convert("RGBA")
    a = np.asarray(im).astype(int)
    rgb, al = a[..., :3], a[..., 3]
    srcs = np.array([p[0] for p in pairs], float)
    tgts = np.array([p[1] for p in pairs], float)
    d = np.abs(rgb[:, :, None, :] - srcs[None, None, :, :]).sum(axis=3)
    nn = d.argmin(axis=2)
    hit = (d.min(axis=2) < tol) & (al > 0)
    out = rgb.astype(float).copy()
    for i in range(len(pairs)):
        m = hit & (nn == i)
        if m.any():
            out[m] = np.clip(rgb[m] - srcs[i] + tgts[i], 0, 255)
    Image.fromarray(np.dstack([out, al]).astype(np.uint8), "RGBA").save(out_path)
    return int(hit.sum()), int((al > 0).sum())


def cap_from_torso(src_path, out_path, pairs, tol, torso_path, off):
    """肩の関節パーツ（arm_*_cap）的换装：它一件里有两种布。

    肩帽是从原画整片切下来的，**71% 是外套（白）、25% 是袖子（青）**。
    袖子那部分按和 arm_*_upper 一样的映射换色就行；外套那部分不能留着白 ——
    midnight 套装的外套在肩部是 (60,78,122) 深藏青，白帽子会变成一块肩章。
    外套那部分的几何和 `seg_torso` **完全重合**（同一张原画切的），
    所以直接去**这一套自己的躯干**同位置取色，颜色、明暗、褶皱全都跟着换装走。
    """
    hit, tot = shift(src_path, out_path, pairs, tol)
    cap = np.asarray(Image.open(out_path).convert("RGBA")).astype(int)
    rgb, al = cap[..., :3].copy(), cap[..., 3]
    tor = np.asarray(Image.open(torso_path).convert("RGBA")).astype(int)
    H, W = al.shape
    oy, ox = int(off[1]), int(off[0])
    sub = np.zeros((H, W, 4), int)
    sy0, sx0 = max(0, oy), max(0, ox)
    sy1, sx1 = min(tor.shape[0], oy + H), min(tor.shape[1], ox + W)
    if sy1 > sy0 and sx1 > sx0:
        sub[sy0 - oy:sy1 - oy, sx0 - ox:sx1 - ox] = tor[sy0:sy1, sx0:sx1]
    # 「外套那部分」= 原件里接近白的像素（默认套装的外套就是白的）
    src0 = np.asarray(Image.open(src_path).convert("RGBA")).astype(int)
    jacket = (al > 0) & (src0[..., :3].min(axis=2) > 170) & (sub[..., 3] > 128)
    rgb[jacket] = sub[..., :3][jacket]
    Image.fromarray(np.dstack([rgb, al]).astype(np.uint8), "RGBA").save(out_path)
    return hit, tot, int(jacket.sum())


def hexrgb(h):
    return [int(h[i:i + 2], 16) for i in (1, 3, 5)]



def cut_outfit_skirt(sprites: str, sub: str, part_file: str) -> dict:
    """把**这一套换装自己的**裙件切出来，并把裙子的面积从换装躯干上挖掉（G66.9）。

    为什么必须做
    ------------
    裙子在 T66.16 已经从 seg_torso 里独立成 `skirt_main`（层 97，躯干 100）。换装包的
    `seg_torso@2x` 还是**拆件前**那张画 —— 裙子烘焙在躯干里。直接换上去：① 那层静态裙
    （层 100）压在裙件（层 97）上面 ⇒ 裙摆骨链等于失效；② 裙件一摆就从静态裙的边上
    探出来 ⇒ 两层裙子。

    做法（不重画任何素材）
    --------------------
    用 `split_skirt.py` 存下的**同一张掩膜、同一个框**，从换装自己的躯干图上切：
      · 切件用 `skirt_mask.png`（含のりしろ），のりしろ 那圈按**这套自己的**裙色重新取色
        （换装的裙子可能是酒红/可可色，抄原件的深蓝会露一条蓝边）；
      · 挖躯干用 `skirt_mask_base.png`（不含のりしろ）—— 躯干在这儿要**留着当遮挡物**。
    里布不重算形状：形状取原件里布的 alpha（同一套几何，逐像素一样），颜色按同一套
    `DARK` 压暗，从**这套的**裙件上取。

    返回：{"skirt_main": {...}, "skirt_lining": {...}}（要塞进换装包的 parts 里）
    """
    sp = sprites
    split_p = os.path.join(sp, "skirt_split.json")
    if not os.path.exists(split_p):
        return {}
    with io.open(split_p, encoding="utf-8") as f:
        split = json.load(f)
    sid = split["id"]
    box = split["box_1x"]
    m_full_p = os.path.join(sp, "skirt_mask.png")
    m_base_p = os.path.join(sp, "skirt_mask_base.png")
    if not (os.path.exists(m_full_p) and os.path.exists(m_base_p)):
        print("[衣柜] 缺 skirt_mask.png / skirt_mask_base.png，跳过裙件（先跑 split_skirt.py）")
        return {}
    m_full = np.asarray(Image.open(m_full_p).convert("L")) > 0
    m_base = np.asarray(Image.open(m_base_p).convert("L")) > 0

    torso_out = os.path.join(sub, "seg_torso@2x.png")
    if not os.path.exists(torso_out):
        print("[衣柜] 本套没有 seg_torso@2x.png，跳过裙件")
        return {}
    a2 = np.asarray(Image.open(torso_out).convert("RGBA")).copy()
    H, W = a2.shape[:2]
    if (H, W) != (m_full.shape[0] * 2, m_full.shape[1] * 2):
        print(f"[衣柜] 换装躯干 {W}x{H} 和掩膜 {m_full.shape[1]}x{m_full.shape[0]} 不是两倍关系，跳过裙件")
        return {}
    m2f = np.kron(m_full, np.ones((2, 2), bool))
    m2b = np.kron(m_base, np.ones((2, 2), bool))

    # —— 裙件：按换装自己的画切，のりしろ 用换装自己的裙色重取 ——
    # ⚠ 1× 里 alpha==255 的像素放大到 @2x 之后，四个孩子里可能有一个是半透明的
    #   抗锯齿边（实测 17 个 alpha≈247）。那几个点算进裙件、再合成回去就会把 alpha
    #   从 247 抬成 254 —— 和 split_skirt.carve_pair() 同一条判据：**只看 alpha==255**。
    m2f = m2f & (m2b | (a2[..., 3] >= 255))
    sk2 = np.zeros_like(a2)
    sk2[m2f] = a2[m2f]
    ring = m2f & ~m2b
    if ring.any():
        sk2, _ = sp_skirt.recolor_ring(sk2, m2b, ring)
        sk2[~m2f] = 0
    x0, y0, w, h = box
    piece2 = sk2[y0 * 2:(y0 + h) * 2, x0 * 2:(x0 + w) * 2]
    piece_p = os.path.join(sub, sid + "@2x.png")
    Image.fromarray(piece2, "RGBA").save(piece_p)

    # —— 躯干挖掉裙子（只挖 mask_base）——
    body2 = a2.copy()
    body2[m2b] = 0
    Image.fromarray(body2, "RGBA").save(torso_out)

    # —— 验收：挖完的躯干 + 裙件 必须还原成**换装原图**（逐像素）——
    out = body2.astype(np.float64).copy()
    b2 = body2[y0 * 2:(y0 + h) * 2, x0 * 2:(x0 + w) * 2].astype(np.float64)
    s2 = piece2.astype(np.float64)
    ba = b2[..., 3:4] / 255.0
    sa = s2[..., 3:4] / 255.0
    oa = ba + sa * (1.0 - ba)
    rgb = (b2[..., :3] * ba + s2[..., :3] * sa * (1.0 - ba)) / np.maximum(oa, 1e-6)
    out[y0 * 2:(y0 + h) * 2, x0 * 2:(x0 + w) * 2, :3] = np.where(oa > 1e-6, rgb, 0.0)
    out[y0 * 2:(y0 + h) * 2, x0 * 2:(x0 + w) * 2, 3] = oa[..., 0] * 255.0
    out = np.clip(out, 0, 255).astype(np.int32)
    ref = a2.astype(np.int32)
    vis = (ref[..., 3] > 1) | (out[..., 3] > 1)
    bad = int((((np.abs(out[..., 3] - ref[..., 3]) > 1) |
                (vis & (np.abs(out[..., :3] - ref[..., :3]).max(2) > 1)))).sum())
    if bad:
        raise SystemExit(f"[衣柜] {os.path.basename(sub)} 裙件切歪了：合成回去 {bad} 个像素对不上")
    print(f"[衣柜] 裙件 {piece2.shape[1]}x{piece2.shape[0]} @2x，のりしろ {int(ring.sum())} px，"
          f"无损 0 误差")

    parts = {sid: {"file": "sprites/outfit_%s/%s@2x.png" % (os.path.basename(sub)[7:], sid)}}

    # —— 里布：形状取原件里布的 alpha，颜色从这套的裙件上压暗 ——
    lin1_p = os.path.join(sp, "skirt_lining.png")
    lin2_p = os.path.join(sp, "skirt_lining@2x.png")
    linj_p = os.path.join(sp, "skirt_parts.json")
    bpj_p = os.path.join(sp, "body_parts.json")
    if os.path.exists(lin1_p) and os.path.exists(linj_p) and os.path.exists(bpj_p):
        with io.open(linj_p, encoding="utf-8") as f:
            lin = json.load(f)["parts"][0]
        with io.open(bpj_p, encoding="utf-8") as f:
            bp = {p["id"]: p for p in json.load(f)["parts"]}
        lpos, lsize = lin["pos"], lin["size"]
        ppos = bp[sid]["pos"]
        off = ((lpos[0] - ppos[0]) * 2, (lpos[1] - ppos[1]) * 2)
        # 1× 的里布掩膜，放大两倍后与裙件对齐
        lm = np.asarray(Image.open(lin1_p).convert("RGBA"))[..., 3] > 0
        lm2 = np.kron(lm, np.ones((2, 2), bool))
        h2, w2 = lsize[1] * 2, lsize[0] * 2
        if lm2.shape != (h2, w2):
            print(f"[衣柜] 里布掩膜 {lm2.shape[::-1]} 和尺寸 {(w2, h2)} 对不上，跳过里布")
        elif off[1] + h2 > piece2.shape[0] or off[0] + w2 > piece2.shape[1]:
            print("[衣柜] 里布框超出裙件，跳过里布")
        else:
            crop_src = piece2[off[1]:off[1] + h2, off[0]:off[0] + w2].copy()
            canvas = np.zeros_like(crop_src)
            canvas[lm2] = crop_src[lm2]
            # 压暗（同一套 DARK / 反射光口径，见 make_skirt_parts.build）
            ys = np.nonzero(lm2.any(axis=1))[0]
            ylo, yhi = int(ys[0]), int(ys[-1])
            kk = np.full(lm2.shape, DARK, np.float32)
            band = max(1, int(round((yhi - ylo + 1) * sp_skirt_parts.BOUNCE_BAND)))
            for i in range(band):
                kk[yhi - i] = DARK + sp_skirt_parts.BOUNCE_MAX * (1.0 - i / band)
            rgbc = np.clip(canvas[..., :3].astype(np.float32) * kk[..., None], 0, 255)
            canvas[..., :3] = rgbc.astype(np.uint8)
            canvas[..., 3] = np.where(lm2, canvas[..., 3], 0)
            lin_name = "skirt_lining@2x.png"
            Image.fromarray(canvas, "RGBA").save(os.path.join(sub, lin_name))
            parts["skirt_lining"] = {
                "file": "sprites/outfit_%s/%s" % (os.path.basename(sub)[7:], lin_name)}
            print(f"[衣柜] 里布 {canvas.shape[1]}x{canvas.shape[0]} @2x"
                  f"（形状沿用原件，颜色取自本套裙件）")
    return parts


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    ap.add_argument("--character", required=True)
    ap.add_argument("--form", required=True)
    a = ap.parse_args()

    base = os.path.join(a.root, "characters", a.character)
    sprites = os.path.join(base, "forms", a.form, "sprites")
    # 重绘素材：**形态级优先**，没有才退回角色级（同 tools/form_art.py 的口径）。
    # 以前只认角色级 —— 给 Q 版跑一遍会拿少女那张重绘躯干去贴，剪影 IoU 0.898，
    # 而更糟的是它还会把 teen 已经生成的换装包覆写掉。
    redraw = os.path.join(base, "forms", a.form, "design", "redraw")
    if not os.path.isdir(redraw):
        redraw = os.path.join(base, "design", "redraw")
    tp = os.path.join(base, "design", "wardrobe.json")
    if not os.path.exists(tp):
        print("[衣柜] 没有 %s，跳过" % tp)
        return 0
    with io.open(tp, encoding="utf-8") as f:
        table = json.load(f)
    iou_min = float(table.get("iou_min", 0.97))
    tol = float(table.get("shift_tol", 90))

    outdir = os.path.join(base, "outfits")
    os.makedirs(outdir, exist_ok=True)

    # ★ default 包**自动从 rig 现状生成**，不手写。
    #   既有的 outfits/default.json 烂过一次 —— 它还在引用上一代单图层 rig 的
    #   body_full.png / eye_open_left.png，换装换不回原装（引擎报「部件不在本形态中」）。
    #   手写的清单一定会和生成物脱节，让它跟着 rig 走就再也不会过期。
    rig_path = os.path.join(base, "forms", a.form, "rig.json")
    touched = {pid for ot in table["outfits"]
               if (ot.get("forms") is None or a.form in ot["forms"])
               for pid in ot["parts"]}
    # ★ 裙子（T66.16b）：`wardrobe.json` 里写的是 `seg_torso`，但裙子切出去之后
    #   换装包还会动到 `skirt_main` / `skirt_lining`（由 cut_outfit_skirt 自动切）。
    #   default 包必须把它们也列上，否则「换成 midnight 再换回常服」会剩一条酒红裙子。
    if os.path.exists(os.path.join(sprites, "skirt_split.json")):
        touched |= {"skirt_main", "skirt_lining"}
    touched = sorted(touched)
    if os.path.exists(rig_path) and touched:
        with io.open(rig_path, encoding="utf-8") as f:
            rig = json.load(f)
        byid = {p["id"]: p for p in rig["parts"]}
        miss = [k for k in touched if k not in byid]
        if miss:
            raise SystemExit(f"[衣柜] wardrobe.json 提到了 rig 里没有的部件：{miss}")
        dflt = {"schema_version": "1.0", "id": "default", "name": "常服（棒球外套）",
                "forms": [a.form],
                "note": "★ 由 tools/make_wardrobe.py 自动生成，不要手改。"
                        "只列「别的服装会动到的部件」的原始贴图，用来换回原装。",
                "parts": {k: {"file": byid[k]["file"]} for k in touched}}
        with io.open(os.path.join(outdir, "default.json"), "w", encoding="utf-8") as f:
            json.dump(dflt, f, ensure_ascii=False, indent=2)
            f.write("\n")
        print(f"[衣柜] default.json 自动重建：{len(touched)} 个部件")

    for ot in table["outfits"]:
        # 这套衣服的**重绘素材**属于哪个形态：不在列表里就整套跳过。
        # 换装包的 parts 里存的是**另一个形态的**贴图坐标，硬上就是身体错位。
        of = ot.get("forms")
        if of is not None and a.form not in of:
            print(f"[衣柜] {ot['id']}：素材属于 {of}，本形态 {a.form} 跳过")
            continue
        sub = os.path.join(sprites, "outfit_" + ot["id"])
        os.makedirs(sub, exist_ok=True)
        pack = {"schema_version": "1.0", "id": ot["id"], "name": ot["name"],
                "forms": list(ot.get("forms") or [a.form]), "note": ot["note"],
                "parts": {}}
        for pid, spec in ot["parts"].items():
            src = os.path.join(sprites, pid + "@2x.png")
            if not os.path.exists(src):
                raise SystemExit(f"[衣柜] 原件不在：{src}")
            dst = os.path.join(sub, pid + "@2x.png")
            if spec["mode"] in ("repaint", "restyle"):
                ai = os.path.join(redraw, spec["source"])
                if not os.path.exists(ai):
                    print(f"[衣柜] {ot['id']}/{pid}: 缺重绘素材 {spec['source']}，跳过")
                    continue
                iou, grow, shrink = repaint(
                    src, ai, dst, iou_min, spec["mode"],
                    float(spec.get("grow_max", 0.03)),
                    float(spec.get("shrink_max", 0.06)))
                print(f"[衣柜] {ot['id']}/{pid:<14} {spec['mode']:<7} "
                      f"IoU={iou:.4f} 外长={grow:.1%} 内缩={shrink:.1%}")
            elif spec["mode"] == "cap":
                pairs = [(hexrgb(x["from"]), hexrgb(x["to"])) for x in spec["map"]]
                tor = os.path.join(sub, "seg_torso@2x.png")
                if not os.path.exists(tor):
                    raise SystemExit(f"[衣柜] {pid} 要先有本套的 seg_torso@2x.png"
                                     f"（把 seg_torso 排在 {pid} 前面）")
                bp = byid[pid]["pos"] if pid in byid else None
                tp2 = byid["seg_torso"]["pos"]
                if bp is None:
                    raise SystemExit(f"[衣柜] rig 里没有 {pid}")
                off = ((bp[0] - tp2[0]) * 2, (bp[1] - tp2[1]) * 2)
                hit, tot, jk = cap_from_torso(src, dst, pairs, float(spec.get("tol", tol)),
                                              tor, off)
                print(f"[衣柜] {ot['id']}/{pid:<14} 关节帽 袖色命中 {hit}/{tot}"
                      f" = {hit / tot * 100:.0f}%，外套 {jk} px 取自本套躯干")
            elif spec["mode"] == "shift":
                pairs = [(hexrgb(x["from"]), hexrgb(x["to"])) for x in spec["map"]]
                hit, tot = shift(src, dst, pairs, float(spec.get("tol", tol)))
                print(f"[衣柜] {ot['id']}/{pid:<14} 换色  命中 {hit}/{tot} "
                      f"= {hit / tot * 100:.0f}%")
            else:
                raise SystemExit(f"[衣柜] {pid} 的 mode={spec['mode']!r} 不认识"
                                 f"（只有 repaint / restyle / shift）")
            pack["parts"][pid] = {"file": f"sprites/outfit_{ot['id']}/{pid}@2x.png"}
        # ★ T66.16b / G66.9：裙子已经独立成件（层 97）。换装躯干里还烘焙着那条裙子，
        #   不切出来就是"静态裙压住裙件 + 摆开时两层裙子"。切件用同一张掩膜，
        #   所以换装的裙色/花纹原样跟过去，不需要重画任何素材。
        if "seg_torso" in pack["parts"]:
            extra = cut_outfit_skirt(sprites, sub, pack["parts"]["seg_torso"]["file"])
            pack["parts"].update(extra)
        with io.open(os.path.join(outdir, ot["id"] + ".json"), "w",
                     encoding="utf-8") as f:
            json.dump(pack, f, ensure_ascii=False, indent=2)
            f.write("\n")
        print(f"  → outfits/{ot['id']}.json：{len(pack['parts'])} 个部件")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
