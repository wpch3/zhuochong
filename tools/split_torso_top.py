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
**不是删除，是搬家 + 重画**（LESSONS：擦掉 = 短发档失去塗り足し，是第二次犯的错）：
把这条料整条搬进新部件 `torso_top_fill`（group=chest，layer=99，
压在 seg_torso(100) 正下方），两件同时显示时与原图**逐像素一致**；
只在 hairstyle = long/twin/pony 三档里 hide 掉它。

切线 = body_parts.json 里的 overlap_px（--rows 可覆盖，但默认就该用它）。
**第一版走了弯路**：想靠「找衣服线稿的上沿」自动划线，结果塗り足し里那块
褐色头发实心块本身就是暗的，被当成线稿，左半边一个像素都没搬走
（logs/asset_qa/q48_split_mask.png 第一版留档）。上游既然已经把这条线写在
元数据里了，就不该去图像上重新猜 —— TRUTH-FIRST。

★★★ 为什么还要「重画」，不能只是搬走然后藏起来 ——
   第一版就是「搬走 + 三档 hide」，实拍（logs/asset_qa/q48_chin_mag.png，
   洋红底＝透明）当场打脸：下巴和衣领之间**裂开两个大洞**，衣领顶边还变成
   一条平切线。原因是这条桩**不是纯垃圾**，它同时兼着「衣领往上的延伸」：
   原画里衣领的上沿被鬓发盖着，画师根本没画过，分段工具拿颈线一смear 就当它有了。
   所以正解是把这条桩**按干净的那一行重画**：

     torso_top_fill[r] = seg_torso[切线下 --src 行]   （逐列竖直复制）
     alpha 自下而上线性淡出到 0                        （官方：付け根はぼかす）

   为什么源行要取切线**下面** --src 行而不是切线那一行：切线那一行（= 颈线）
   在原画里正压着鬓发，brown/蓝发梢全在上面 —— 分段工具当年就是栽在这。
   躯干下面那几行早被 20/20b/25c 三步清过残渣，是干净的衣领。
   重画之后这条件在任何发型下都能**一直显示**，不需要 hide，也就没有洞。

★★★ 第四轮（SIG_V=10）：重画还要**限制在"真的会破洞"的那几列**。
   第三版（SIG_V=9）把整条 133px 宽的顶条都重画了，8× 实拍
   （logs/asset_qa/q48_neck_zoom8.png 第 2/3 格）看到下巴两侧**一片青色雾扇**：
   那是衣领的青色被竖着拉到了"本来就该是背景"的地方 —— 鬓发撤走之后，
   下巴外侧就是空气，不是衣服。往背景该在的地方糊东西，正是自己写在
   LESSONS 里禁止的那种"把图做丑"的修法。
   真正需要补的只有**被剪影围住的那一小片**（下巴底 ↔ 衣领顶之间）。
   所以这一版先算一张 need 掩膜：拿当前 rig.json 把每个发型档**在没有
   torso_top_fill 的情况下**合成一遍，从画布四边洪泛，取"被围住的透明像素"
   并集，再向外扩 --need-pad 像素当のりしろ，最后只在这张掩膜内重画。
   掩膜外一律保持原件的 alpha（短发档那条塗り足し一点没少）。
   没有 rig.json 时（第一次全量重建）退回整条重画并打印提醒。

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

NEW_ID = "torso_top_fill"       # ①原封不动的那条塗り足し：短发档显示、扎起来就藏
PATCH_ID = "torso_top_patch"    # ②重画的衣领顶边：只补"真会破洞"的地方，四档常显
SRC_ID = "seg_torso"
LAYER = 99                      # seg_torso 是 100，压在它正下方
PATCH_LAYER = 98                # 再低一层，两件同时在场时不互相抢
SIG_V = 10


def _flood_outside(op, np):
    """从画布四边灌水，返回"能从画布外走到"的透明像素掩膜。"""
    from collections import deque
    H, W = op.shape
    seen = np.zeros_like(op)
    q = deque()
    for x in range(W):
        for y in (0, H - 1):
            if not op[y, x] and not seen[y, x]:
                seen[y, x] = True
                q.append((y, x))
    for y in range(H):
        for x in (0, W - 1):
            if not op[y, x] and not seen[y, x]:
                seen[y, x] = True
                q.append((y, x))
    while q:
        y, x = q.popleft()
        for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            ny, nx = y + dy, x + dx
            if 0 <= ny < H and 0 <= nx < W and not op[ny, nx] and not seen[ny, nx]:
                seen[ny, nx] = True
                q.append((ny, nx))
    return seen


def need_mask(base, body_1x, np, Image, pad, quiet=False):
    """算出"去掉 torso_top_fill 之后、各发型档真的会破洞"的像素（seg_torso@2x 坐标系）。

    做法：拿**当前** rig.json 把每个发型档合成一遍（跳过 torso_top_fill，
    并把 seg_torso 换成已经掏掉顶条的 body），从画布四边洪泛，
    取"被剪影围住的透明像素"的并集，再向外扩 pad 像素当のりしろ。
    返回 None = 没法算（没有 rig.json / 结构对不上），调用方退回整条重画。
    """
    rig_path = os.path.join(base, "rig.json")
    if not os.path.exists(rig_path):
        return None
    with io.open(rig_path, encoding="utf-8") as f:
        rig = json.load(f)
    cw = int(rig.get("canvas", {}).get("w", 0))
    ch = int(rig.get("canvas", {}).get("h", 0))
    if cw <= 0 or ch <= 0:
        return None
    by = {p["id"]: p for p in rig.get("parts", [])}
    if SRC_ID not in by:
        return None
    groups = rig.get("poses", []) or []
    member, dflt = {}, {}
    for g in groups:
        for e in g.get("entries", []) or []:
            for pid in (e.get("parts") or []):
                member.setdefault(pid, set()).add(g["id"])
            if e.get("id") == g.get("default"):
                dflt[g["id"]] = set(e.get("parts") or [])
    hs = next((g for g in groups if g["id"] == "hairstyle"), None)
    if hs is None:
        return None

    cache = {}
    def layer_of(p):
        """把一个部件画到画布上，返回 (alpha 数组, 放置左上角)。"""
        pid = p["id"]
        if pid in cache:
            return cache[pid]
        if pid == SRC_ID:
            im = Image.fromarray(body_1x)
        else:
            im = Image.open(os.path.join(base, p["file"])).convert("RGBA")
            sc = p.get("scale", 1.0)
            sx, sy = ((float(sc[0]), float(sc[1])) if isinstance(sc, (list, tuple))
                      else (float(sc), float(sc)))
            if (sx, sy) != (1.0, 1.0):
                im = im.resize((max(1, int(im.width * sx)), max(1, int(im.height * sy))),
                               Image.LANCZOS)
        ax, ay = p.get("anchor", [0, 0])
        ox = int(round(p["pos"][0] - ax * im.width))
        oy = int(round(p["pos"][1] - ay * im.height))
        cache[pid] = (np.array(im)[..., 3], ox, oy)
        return cache[pid]

    need = np.zeros((ch, cw), bool)
    for e in hs.get("entries", []) or []:
        hide = set(e.get("hide") or [])
        own = set(e.get("parts") or [])
        op = np.zeros((ch, cw), bool)
        for p in rig.get("parts", []):
            pid = p["id"]
            if pid in (NEW_ID, PATCH_ID) or pid in hide:
                continue
            gs = member.get(pid, set())
            if gs and not all((pid in own) if gid == hs["id"] else (pid in dflt.get(gid, set()))
                              for gid in gs):
                continue
            al, ox, oy = layer_of(p)
            h, w = al.shape
            x0, y0 = max(0, ox), max(0, oy)
            x1, y1 = min(cw, ox + w), min(ch, oy + h)
            if x1 <= x0 or y1 <= y0:
                continue
            op[y0:y1, x0:x1] |= al[y0 - oy:y1 - oy, x0 - ox:x1 - ox] > 110
        enc = (~op) & (~_flood_outside(op, np))
        need |= enc
    if not need.any():
        return None
    for _ in range(max(0, int(pad))):
        g2 = need.copy()
        g2[1:] |= need[:-1]; g2[:-1] |= need[1:]
        g2[:, 1:] |= need[:, :-1]; g2[:, :-1] |= need[:, 1:]
        need = g2
    # 换算到 seg_torso@2x 的像素坐标：画布 1x → 减去 seg_torso 的落点 → ×2
    sp = by[SRC_ID]
    ax, ay = sp.get("anchor", [0, 0])
    sw, sh = body_1x.shape[1], body_1x.shape[0]
    ox = int(round(sp["pos"][0] - ax * sw))
    oy = int(round(sp["pos"][1] - ay * sh))
    sub = np.zeros((sh, sw), bool)
    x0, y0 = max(0, ox), max(0, oy)
    x1, y1 = min(cw, ox + sw), min(ch, oy + sh)
    if x1 > x0 and y1 > y0:
        sub[y0 - oy:y1 - oy, x0 - ox:x1 - ox] = need[y0:y1, x0:x1]
    out = np.repeat(np.repeat(sub, 2, axis=0), 2, axis=1)
    if not quiet:
        print("[顶条拆件] need 掩膜：%d px(1x) 真会破洞（扩 %d px 后）"
              % (int(sub.sum()), pad))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--character", required=True)
    ap.add_argument("--form", required=True)
    ap.add_argument("--src", type=int, default=14,
                    help="重画的源行取切线下方多少行（1x）—— 切线那一行在原画里"
                         "压着鬓发，是脏的")
    ap.add_argument("--smooth", type=int, default=10,
                    help="源行横向平滑半径（1x）—— 不平滑会拉出竖条纹")
    ap.add_argument("--gamma", type=float, default=2.4,
                    help="alpha 淡出曲线；>1 = 顶部消失得更快。2.4 是实拍选型定的"
                         "（1.35 在下巴两侧留了一片看得见的青雾，q48_gamma_ab.png）")
    ap.add_argument("--need-pad", type=int, default=6, dest="need_pad",
                    help="need 掩膜向外扩张的像素（1x），0 = 不限制（整条重画）")
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

    sig = {"v": SIG_V, "rows": a.rows, "src": a.src, "gamma": a.gamma,
           "smooth": a.smooth, "need_pad": a.need_pad}
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

    # —— 重画：逐列把「切线下 src 行」那一行竖直复制上去，alpha 往上淡出 ——
    #   · **轮廓**取切线那一行（= 躯干留下来的第一行）：顶条和本体严丝合缝，
    #     不会在肩头鼓出一条横带（第二版栽在这：源行比切线宽十几个像素，
    #     下巴底下多出一条带竖条纹的浅色横带，见 q48_faces_final 第一版）。
    #   · **颜色**取切线下方 src 行（干净衣领）；那一行在某列是空的就横向
    #     取最近的有色列补上。
    src = min(H - 1, band + a.src * K)
    crow = arr[src, :, :3].astype(np.float32)
    chas = arr[src, :, 3] > 30
    if chas.any():
        idx = np.arange(W)
        good = idx[chas]
        nearest = good[np.abs(idx[:, None] - good[None, :]).argmin(1)]
        crow = crow[nearest]
    # 源行里带着线稿和衣领的明暗，直接竖着拉会变成一片**竖条纹**
    #   （第三版就是这样，q48_band_3way.png 第 3 列那片条纹雾）。
    #   横向做一次箱式平滑，拉上去就是一片柔和的底色 —— 它只是"藏在头和头发
    #   后面的底"，不需要细节，官方对塗り足し的要求也只是"别露底"。
    if a.smooth > 0:
        k = int(a.smooth) * K
        pad = np.pad(crow, ((k, k), (0, 0)), mode="edge")
        acc = np.zeros_like(crow)
        for o in range(2 * k + 1):
            acc += pad[o:o + W]
        crow = acc / float(2 * k + 1)
    arow = arr[band, :, 3].astype(np.float32) if band < H else np.zeros(W, np.float32)
    fill = np.zeros((band, W, 4), np.float32)
    fill[..., :3] = crow[None, :, :]
    ramp = (np.arange(band, dtype=np.float32) / max(1.0, band - 1.0))  # 0(顶)→1(底)
    ramp = ramp ** a.gamma
    fill[..., 3] = arow[None, :] * ramp[:, None]

    # —— 只在"真的会破洞"的地方重画（见文件头 SIG_V=10 那一段）——
    #   下巴两侧在 twin/pony 档本来就该是空气；往那儿糊衣领的青色＝把图做丑。
    #   所以顶条最终拆成**两件**：
    #     ① torso_top_fill  = 原封不动的塗り足し，短发档显示、扎起头发就藏
    #        （它在短发档不是垃圾：发梢甩动时露出来的就是它）
    #     ② torso_top_patch = 重画的衣领顶边，只覆盖 need 掩膜那一小片，四档常显
    #        （不藏 ⇒ 扎起头发也不会在下巴和衣领之间裂洞）
    nm = None
    if a.need_pad > 0:
        body_probe = np.array(im).copy()
        body_probe[:band, :, 3] = 0
        body_1x = np.array(Image.fromarray(body_probe).resize(
            (W // K, H // K), Image.LANCZOS))
        try:
            nm = need_mask(base, body_1x, np, Image, a.need_pad, a.quiet)
        except Exception as exc:                      # noqa: BLE001
            print("[顶条拆件] need 掩膜算不出来（%s），退回整条重画" % exc)
            nm = None
        if nm is None and not a.quiet:
            print("[顶条拆件] 没有可用的 rig.json ⇒ 整条重画（首次全量重建时正常）")
    patch = np.clip(fill, 0, 255).astype(np.uint8)
    if nm is not None:
        patch[..., 3] = np.where(nm[:band], patch[..., 3], 0)

    # —— 写三张图：原顶条 / 重画补丁 / 掏掉顶条的躯干 ——
    def save_piece(rgba_band, pid):
        """把 band 区域里的一片内容存成独立部件，返回 (pos, size, px) 或 None。"""
        m = rgba_band[..., 3] > 30
        if m.sum() < 50:
            return None
        ys, xs = np.where(m)
        x0, x1 = int(xs.min()), int(xs.max()) + 1
        y0, y1 = int(ys.min()), int(ys.max()) + 1
        x0 -= x0 % K
        y0 -= y0 % K
        x1 += (-x1) % K
        y1 += (-y1) % K
        cut = np.zeros_like(rgba_band)
        cut[m] = rgba_band[m]
        cr = Image.fromarray(cut[y0:y1, x0:x1])
        cr.save(os.path.join(sprites, pid + "@2x.png"))
        cr.resize((cr.width // K, cr.height // K),
                  Image.LANCZOS).save(os.path.join(sprites, pid + ".png"))
        return (x0 // K, y0 // K), (cr.width // K, cr.height // K), int(m.sum())

    orig_band = np.array(im)[:band].copy()            # ①原封不动的塗り足し
    got_fill = save_piece(orig_band, NEW_ID)
    got_patch = save_piece(patch, PATCH_ID)
    if got_fill is None:
        print("[顶条拆件] 顶条几乎没有料，跳过")
        return 0
    body = np.array(im).copy()            # 躯干本体：从**原件**掏掉顶部 band 行
    body[:band, :, 3] = 0
    Image.fromarray(body).save(src2)
    Image.fromarray(body).resize((W // K, H // K), Image.LANCZOS).save(
        os.path.join(sprites, SRC_ID + ".png"))

    sp = parts[SRC_ID]
    meta["parts"] = [p for p in meta["parts"] if p["id"] not in (NEW_ID, PATCH_ID)]
    i = next(i for i, p in enumerate(meta["parts"]) if p["id"] == SRC_ID)
    entries = []
    for pid, lay, got, note in (
            (NEW_ID, LAYER, got_fill,
             "seg_torso 顶部那条塗り足し（make_body_parts 复制颈线做出来的脖子桩）"
             "单独成件。短发档它藏在鬓发后面、发梢甩动时正好顶住，所以**短发档必须显示**；"
             "长发/双马尾/高马尾三档把鬓发撤走，它就露成脖子两侧的青绿碎渣 ⇒ 那三档 hide。"
             "（第四十八问 (c)）"),
            (PATCH_ID, PATCH_LAYER, got_patch,
             "重画的衣领顶边：原画里衣领上沿一直被鬓发盖着、画师没画过，"
             "所以上面那件一藏，下巴和衣领之间就裂洞。这件按切线下方的干净衣领重画"
             "（轮廓借切线行、颜色借干净行 + 横向平滑 + 向上淡出），"
             "**只覆盖各发型档真的会破洞的那一小片**（need 掩膜），四档常显。"
             "（第四十八问 (c) 第四轮）")):
        if got is None:
            continue
        (px, py), (pw, ph), _n = got
        entries.append({"id": pid, "file": "sprites/%s.png" % pid,
                        "group": sp.get("group", "chest"), "layer": lay,
                        "pos": [sp["pos"][0] + px, sp["pos"][1] + py],
                        "size": [pw, ph], "pivot": sp.get("pivot"), "note": note})
    for e in reversed(entries):
        meta["parts"].insert(i, e)
    meta["torso_top_split"] = {
        "sig": sig, "rows_1x": rows, "overlap_px": ov,
        "fill": {"pos": entries[0]["pos"], "size": entries[0]["size"],
                 "px_1x": got_fill[2] // 4},
        "patch": ({"pos": entries[-1]["pos"], "size": entries[-1]["size"],
                   "px_1x": got_patch[2] // 4} if got_patch else None),
        "why": "seg_torso 顶部 overlap_px 行 = make_body_parts 复制颈线做出来的"
               "脖子桩，不是原画；原画那一段衣领在 seg_head 里。"
               "拆成两件：原料（可藏）+ 重画补丁（常显，只补真会破洞的地方）"}
    with io.open(bpj, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
    if not a.quiet:
        print("[顶条拆件] %s %dx%d @%s（%d px 1x）；%s"
              % (NEW_ID, entries[0]["size"][0], entries[0]["size"][1],
                 entries[0]["pos"], got_fill[2] // 4,
                 ("%s %dx%d @%s（%d px 1x）"
                  % (PATCH_ID, entries[-1]["size"][0], entries[-1]["size"][1],
                     entries[-1]["pos"], got_patch[2] // 4))
                 if got_patch else "没有补丁（need 掩膜为空）"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
