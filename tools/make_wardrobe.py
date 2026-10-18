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

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import clean_baked_residue as cbr                              # noqa: E402


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
    out = np.dstack([np.clip(px, 0, 255), np.asarray(orig)[..., 3]]).astype(np.uint8)
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


def hexrgb(h):
    return [int(h[i:i + 2], 16) for i in (1, 3, 5)]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    ap.add_argument("--character", required=True)
    ap.add_argument("--form", required=True)
    a = ap.parse_args()

    base = os.path.join(a.root, "characters", a.character)
    sprites = os.path.join(base, "forms", a.form, "sprites")
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
    touched = sorted({pid for ot in table["outfits"] for pid in ot["parts"]})
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
        sub = os.path.join(sprites, "outfit_" + ot["id"])
        os.makedirs(sub, exist_ok=True)
        pack = {"schema_version": "1.0", "id": ot["id"], "name": ot["name"],
                "forms": [a.form], "note": ot["note"], "parts": {}}
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
            elif spec["mode"] == "shift":
                pairs = [(hexrgb(x["from"]), hexrgb(x["to"])) for x in spec["map"]]
                hit, tot = shift(src, dst, pairs, float(spec.get("tol", tol)))
                print(f"[衣柜] {ot['id']}/{pid:<14} 换色  命中 {hit}/{tot} "
                      f"= {hit / tot * 100:.0f}%")
            else:
                raise SystemExit(f"[衣柜] {pid} 的 mode={spec['mode']!r} 不认识"
                                 f"（只有 repaint / restyle / shift）")
            pack["parts"][pid] = {"file": f"sprites/outfit_{ot['id']}/{pid}@2x.png"}
        with io.open(os.path.join(outdir, ot["id"] + ".json"), "w",
                     encoding="utf-8") as f:
            json.dump(pack, f, ensure_ascii=False, indent=2)
            f.write("\n")
        print(f"  → outfits/{ot['id']}.json：{len(pack['parts'])} 个部件")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
