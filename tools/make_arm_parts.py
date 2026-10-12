#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""make_arm_parts.py - 把两条手臂从躯干上拆成「上臂 + 前臂」四件，并补上袖子底下的夹克。

为什么要重切（G4c）：
  make_body_parts.py 是按**直线**切的：手臂 = x<127 / x>316 的一整块矩形板，
  里头连夹克的侧片一起切走了。那块板一旋转，夹克就跟着歪 → 整块旋转超过 8° 必裂。
  Live2D 的切法是沿**袖子的缝**切：袖子（青色）是一件，夹克身（白色）是另一件。

切法：
  ① 袖子按颜色 flood（种子放在袖子中段），天然停在白夹克的边上；
  ② 袖口以下用「蛇形」逐行跟随（取包含上一行中心的那段连通前景），把袖口 + 手一起带上；
  ③ 在肘部（anchors 的 elbow_*）切成上臂 / 前臂 / 手三件（手腕线是逐行实测的
     袖口下沿，不是 anchors 里按比例算的那条），留 24px 重叠带并做渐隐，
     这样肘部旋转不会出现硬切线。

袖子挪走后躯干会空一块（夹克侧片、下摆条、裙子边），原画里**没有**这些像素 ——
按 D19 必须 AI 重绘：design/redraw/torso_noarms.png（无手臂躯干，已做过各向异性配准 +
逐通道颜色配准），只回贴「被袖子遮住」的那些像素。

输入：sprites/body_full.png、design/anchors.json、design/redraw/torso_noarms.png
输出：sprites/arm_{l,r}_{upper,fore}.png、sprites/seg_torso.png（补全侧片）、sprites/arm_parts.json

用法：
  ~/.imgenv/bin/python tools/make_arm_parts.py --character xiaoxun --form teen
"""
from __future__ import annotations
import argparse, json, os, sys
from collections import deque

import numpy as np
from PIL import Image

TEAL = np.array([108, 180, 192])      # 袖子的青
TEAL_TOL = 150                        # |ΔR|+|ΔG|+|ΔB| 阈值
ELBOW_OVERLAP = 24                    # 肘部重叠带（上下各一半）
WRIST_STUB = 10                       # 手腕：手往袖口里续多高的皮肤（藏在袖子里）
WRIST_STUB_IN = 4                     # 续出来的皮肤要比袖口窄这么多（转手时不许戳出袖子）
SKIN_RUN = 3                          # 连续几行"这一行基本都是肤色"才算袖口到头了
FEATHER = 2                         # 切口羽化半径（像素）
BLEED = 5                           # 躯干切口往外塗り足し的圈数
LINE_RGB = (90, 90, 110)            # 线稿色 #5A5A6E：补出来的衣片也要有轮廓线
LINE_W = 2                          # 轮廓线宽（像素）
SHOULDER_CAP = 46                   # 肩头保留给躯干的高度（像素）


def skin_of(rgb, m):
    """肤色（#FCE4D8 一类）：亮、偏红。青袖 #6CB4C0 的 G/B 高于 R，白夹克 R≈G≈B。"""
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    return m & (r > 205) & (r > b + 12) & (r >= g) & (g > 140)


def wrist_row(rgb, m, y_from, y_to):
    """袖口到头的那一行 = 从肘往下第一次连续 SKIN_RUN 行\"这一行的不透明像素
       有六成以上是肤色\"。手是从袖口里伸出来的，这一行就是手腕。"""
    sk = skin_of(rgb, m)
    run = 0
    for y in range(y_from, y_to):
        tot = int(m[y].sum())
        if tot >= 6 and int(sk[y].sum()) >= tot * 0.6:
            run += 1
            if run >= SKIN_RUN:
                return y - SKIN_RUN + 1
        else:
            run = 0
    return -1


def flood(mask, seed):
    """四邻域 flood fill（沙箱没有 scipy，自己写）。"""
    h, w = mask.shape
    out = np.zeros((h, w), bool)
    q = deque([seed])
    out[seed] = True
    while q:
        y, x = q.popleft()
        for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            ny, nx = y + dy, x + dx
            if 0 <= ny < h and 0 <= nx < w and mask[ny, nx] and not out[ny, nx]:
                out[ny, nx] = True
                q.append((ny, nx))
    return out


def sleeve_mask(rgb, alpha, x0, x1):
    """在 [x0,x1) 这一侧找袖子：先按青色取候选，再从中段 flood。"""
    cand = (np.abs(rgb - TEAL).sum(axis=2) < TEAL_TOL) & alpha
    sub = cand[400:520, x0:x1]
    ys, xs = np.nonzero(sub)
    if len(ys) == 0:
        raise SystemExit(f"[make_arm_parts] x[{x0},{x1}) 里找不到袖子（青色）像素")
    seed = (400 + int(np.median(ys)), x0 + int(np.median(xs)))
    return flood(cand, seed)


def row_runs(row):
    """一行里的所有连通段 [(a, b), ...]（闭区间）。"""
    idx = np.nonzero(row)[0]
    if idx.size == 0:
        return []
    cuts = np.nonzero(np.diff(idx) > 1)[0]
    runs, start = [], 0
    for c in cuts:
        runs.append((int(idx[start]), int(idx[c])))
        start = c + 1
    runs.append((int(idx[start]), int(idx[-1])))
    return runs


def grow_down(mask, alpha, max_run=150, slack=6):
    """从袖子最下面一行往下逐行跟随，把袖口和手一起带上。

    一行里可能有**好几段**（五根手指张开时就是五段），所以不能只跟"包含上一行
    中心的那一段"——那样手指缝两侧会被漏掉，叠回去就少像素（实测漏 755px）。
    这里改成：上一行占住的区间左右各放宽 slack 像素，这一行凡是和它相交的段**全要**。
    再用 max_run 封顶，防止袖口和下摆连在一起时一路跑进躯干。
    """
    h, w = alpha.shape
    m = mask.copy()
    rows = np.nonzero(mask.any(axis=1))[0]
    y = int(rows.max())
    cols = np.nonzero(mask[y])[0]
    lo, hi = int(cols.min()), int(cols.max())
    y += 1
    miss = 0
    while y < h and miss < 6:
        runs = [r for r in row_runs(alpha[y])
                if r[1] >= lo - slack and r[0] <= hi + slack]
        if not runs:
            miss += 1
            y += 1
            continue
        nlo, nhi = min(r[0] for r in runs), max(r[1] for r in runs)
        if nhi - nlo > max_run:          # 和躯干连上了：裁回上一行的范围，别一路吃进去
            nlo, nhi = max(nlo, lo - slack), min(nhi, hi + slack)
        for a, b in runs:
            a, b = max(a, nlo), min(b, nhi)
            if a <= b:
                m[y, a:b + 1] = True
        lo, hi = nlo, nhi
        miss = 0
        y += 1
    return m


def fill_outward(m, alpha, side, limit=40):
    """每一行从袖子的最外侧像素补到人物轮廓外缘。

    袖口的三道白条不是青色，按颜色 flood 吃不到；它们又贴着轮廓（不是内部孔洞），
    所以闭运算也补不回来 —— 实测左右各漏掉一块 ~100px 的楔形。
    手臂在这些行里本来就是画面最外侧的东西，直接按行补到轮廓即可：
    左臂往左补、右臂往右补，并且只补前景像素（手指缝里的背景不要）。
    """
    out = m.copy()
    for y in np.nonzero(m.any(axis=1))[0]:
        fg = np.nonzero(alpha[y])[0]
        xs = np.nonzero(m[y])[0]
        if fg.size == 0 or xs.size == 0:
            continue
        if side == "l":
            a, b = int(fg.min()), int(xs.min())
        else:
            a, b = int(xs.max()) + 1, int(fg.max()) + 1
        if 0 < b - a <= limit:
            out[y, a:b] = alpha[y, a:b]
    return out


def shift(m, dy, dx):
    """不绕回的平移（np.roll 会把左边卷到右边，手臂贴着画布边时会炸）。"""
    out = np.zeros_like(m)
    h, w = m.shape
    ys0, ys1 = max(0, dy), min(h, h + dy)
    xs0, xs1 = max(0, dx), min(w, w + dx)
    out[ys0:ys1, xs0:xs1] = m[ys0 - dy:ys1 - dy, xs0 - dx:xs1 - dx]
    return out


def dilate(mask, n=1):
    m = mask.copy()
    for _ in range(n):
        m = (m | shift(m, 1, 0) | shift(m, -1, 0) | shift(m, 0, 1) | shift(m, 0, -1))
    return m


def erode(mask, n=1):
    return ~dilate(~mask, n)


def soft(mask, feather=FEATHER):
    """二值掩码 → 软边 alpha（和其它拆件脚本同一套配方）。"""
    from PIL import ImageFilter
    im = Image.fromarray((mask.astype(np.float32) * 255).astype(np.uint8))
    for _ in range(feather):
        im = im.filter(ImageFilter.BoxBlur(1))
    a = np.asarray(im).astype(np.float32) / 255.0
    a = np.clip(a * 1.35 - 0.18, 0.0, 1.0)
    a[mask & (a > 0.75)] = 1.0
    return a


def bleed(rgb, have, into, rounds=5):
    """塗り足し：把已有像素的颜色往 into 区域里长几圈，
    免得零件的软边底下露出透明（Live2D 素材的标准做法）。"""
    out_rgb = rgb.copy()
    cur = have.copy()
    grown = np.zeros_like(have)
    dist = np.zeros(have.shape, np.float32)
    for r in range(1, rounds + 1):
        ring = dilate(cur, 1) & ~cur & into
        if not ring.any():
            break
        acc = np.zeros(rgb.shape, np.float32)
        cnt = np.zeros(have.shape, np.float32)
        for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nb = shift(cur, dy, dx)
            nbrgb = np.dstack([shift(out_rgb[..., c], dy, dx) for c in range(3)])
            use = ring & nb
            acc[use] += nbrgb[use]
            cnt[use] += 1
        ok = ring & (cnt > 0)
        out_rgb[ok] = (acc[ok] / cnt[ok][:, None]).astype(rgb.dtype)
        dist[ok] = r
        cur = cur | ok
        grown |= ok
    return out_rgb, grown, dist


def cut(rgb, alpha_f, box):
    """按 box=(x0,y0,x1,y1) 裁出 RGBA 图。"""
    x0, y0, x1, y1 = box
    out = np.zeros((y1 - y0, x1 - x0, 4), np.uint8)
    out[..., :3] = rgb[y0:y1, x0:x1]
    out[..., 3] = (alpha_f[y0:y1, x0:x1] * 255).round().astype(np.uint8)
    return Image.fromarray(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--character", required=True)
    ap.add_argument("--form", required=True)
    ap.add_argument("--root", default=".")
    args = ap.parse_args()
    base = os.path.join(args.root, "characters", args.character, "forms", args.form)
    sp = os.path.join(base, "sprites")
    body = np.array(Image.open(os.path.join(sp, "body_full.png")).convert("RGBA"))
    H, W = body.shape[:2]
    rgb = body[..., :3].astype(int)
    alpha = body[..., 3] > 16

    anchors = json.load(open(os.path.join(base, "design", "anchors.json"), encoding="utf-8"))
    pts = anchors["points"]
    redraw_path = os.path.join(args.root, "characters", args.character,
                               "design", "redraw", "torso_noarms.png")
    if not os.path.exists(redraw_path):
        raise SystemExit(f"[make_arm_parts] 缺少 AI 重绘底图：{redraw_path}（D19：被遮挡像素必须重绘）")
    fill = np.array(Image.open(redraw_path).convert("RGBA"))
    if fill.shape[:2] != (H, W):
        raise SystemExit("[make_arm_parts] 重绘底图尺寸必须与 body_full.png 一致")

    bp_path = os.path.join(sp, "body_parts.json")
    bp = json.load(open(bp_path, encoding="utf-8"))
    torso = next(p for p in bp["parts"] if p["id"] == "seg_torso")

    report = {"schema_version": "1.0", "source": "sprites/body_full.png",
              "redraw": "design/redraw/torso_noarms.png",
              "elbow_overlap_px": ELBOW_OVERLAP, "parts": [], "checks": {}}
    arms = {}
    yy_all = np.arange(H)[:, None]
    for side, (x0, x1) in (("l", (0, 150)), ("r", (300, W))):
        m = grow_down(sleeve_mask(rgb, alpha, x0, x1), alpha)
        # 袖口的白条不是青色，flood 吃不到；它贴着轮廓所以也不算"内部孔洞"。
        # 肘部以下做一次形态学闭运算（只在前景里补），把这种开口缺块补回来。
        # 只在肘以下做：上臂内侧紧挨着夹克，闭运算会把夹克的凹处也吃进来。
        close = erode(dilate(m, 6), 6) & (alpha > 0) & (yy_all > int(pts[f"elbow_{side}"][1]))
        arms[side] = fill_outward(m | close, alpha, side)

    # ---- 躯干：袖子那块换成 AI 重绘的夹克侧片 ----
    # 挖袖子时**肩头那一截不挖**：原画里肩膀的圆头是画在袖子上的，
    # 整块拿走以后躯干的肩膀就是一条平口（用户反馈"这个分割"）。
    # 让躯干和手臂各留一份肩头（静止时手臂盖在上面、一模一样；
    # 手臂转开后躯干仍有一个圆肩），这是 2D 拆件里标准的"关节两边各留一份"。
    sh_y = int(pts["shoulder"][1])
    occ = dilate(arms["l"] | arms["r"], 2) & (np.arange(H)[:, None] > sh_y + SHOULDER_CAP)
    # 重绘图是洋红底抠出来的，边缘有一圈被烤进 RGB 的紫：这种像素一律不要，
    # 贴进去会直接把 check_assets 的"键色残留"打挂（实测 299/631 是紫边）。
    fr = fill[..., 0].astype(np.int32); fg_ = fill[..., 1].astype(np.int32); fb = fill[..., 2].astype(np.int32)
    key_d = np.sqrt(((fill[..., :3].astype(np.float32) - np.array([255.0, 0.0, 255.0])) ** 2).sum(axis=2))
    # 被洋红污染的像素一律：红蓝都明显高于绿（品红 = R、B 高、G 低）。
    # 角色这块只有白夹克（R≈G≈B）和青袖（G≥R），所以这条判据不会误伤。
    purple = (np.minimum(fr, fb) - fg_) > 25
    have = (fill[..., 3] > 200) & (key_d > 150.0) & ~purple
    newbody = body.copy()
    paste = occ & have
    newbody[..., :3][paste] = fill[..., :3][paste]
    newbody[..., 3][paste] = 255
    lost = occ & ~have                      # 重绘也没有的（袖子外侧本来就是背景）
    newbody[..., 3][lost] = 0
    # 剩下的空洞边缘往外长 5 圈颜色，保证手臂转开时切口不是硬透明边
    keep = newbody[..., 3] > 16
    newbody[..., :3], grown, dist = bleed(newbody[..., :3], keep, lost, rounds=BLEED)
    # 边缘往外长的这几圈做渐隐，手臂转开时看着像衣片自然收边
    newbody[..., 3][grown] = np.clip(255.0 * (1.0 - (dist[grown] - 1.0) / BLEED), 0, 255).astype(np.uint8)

    # ---- 给补出来的衣片描线稿 ----
    # 原画每一条剪影边上都有一条深紫灰的线；补画区如果只有平涂白，
    # 手臂一抬，露出来的就是"纸片剪开"的感觉（用户反馈的"这个分割"）。
    # 所以把新产生的那段剪影边按原画的线稿色描回去。
    solid = newbody[..., 3] > 128
    near_cut = dilate(arms["l"] | arms["r"], 8)          # 只描新切出来的边
    rim = solid & ~erode(solid, LINE_W) & near_cut
    rim_soft = solid & ~erode(solid, LINE_W + 1) & near_cut
    ln = np.array(LINE_RGB, np.float32)
    for mask, k in ((rim_soft, 0.45), (rim, 0.9)):
        if mask.any():
            cur = newbody[..., :3][mask].astype(np.float32)
            newbody[..., :3][mask] = (cur * (1 - k) + ln * k).astype(np.uint8)
    report["checks"]["outline_px"] = int(rim.sum())
    # 裙摆下沿（G4c2）：躯干只到裙子为止，裙子下面那截大腿归腿件。
    # make_body_parts 已经按列量好了线，这里必须用**同一条**，
    # 否则这一步把大腿又原样贴回躯干，腿一抬接缝处就是一段钉死的大腿。
    tt = bp.get("thigh_top")
    if tt:
        tta = np.array(tt, int)
        tta[tta < 0] = H
        torso_trim = np.arange(H)[:, None] >= tta[None, :]
        newbody[..., 3][torso_trim] = 0
        report["checks"]["torso_thigh_trim_px"] = int(torso_trim.sum())
    tx, ty = torso["pos"]
    tw, th = torso["size"]
    Image.fromarray(newbody[ty:ty + th, tx:tx + tw]).save(os.path.join(sp, "seg_torso.png"))
    report["checks"]["torso_filled_px"] = int(paste.sum())
    report["checks"]["torso_cleared_px"] = int(lost.sum())

    # ---- 六件手臂（上臂 / 前臂 / 手 × 左右）----
    layer = {"l": 140, "r": 141}
    hand_layer = {"l": 138, "r": 139}       # 手画在**前臂底下**：袖口要压住手腕那截补画
    for side in ("l", "r"):
        m = arms[side]
        elbow_y = int(pts[f"elbow_{side}"][1])
        half = ELBOW_OVERLAP // 2
        orig_a = (body[..., 3] / 255.0).astype(np.float32)
        yy_col = np.arange(H)[:, None]
        # 手腕 = 袖口到头的那一行（逐行实测，不用 anchors 里按比例算的 708：
        # 那条线落在指尖上，照它切会把半只手留在前臂上）
        wrist_y = wrist_row(rgb, m, elbow_y + 20, H)
        if wrist_y < 0:
            raise SystemExit(f"[make_arm_parts] {side} 侧找不到袖口下沿（手腕），别往下切了")
        # 手往袖子里续一截皮肤（塗り足し）：手腕一转，袖口下面才不会露出背景。
        # 只在"袖子本来就不透明"的范围里续，静止时完全被袖口压住。
        hand_rgb = body[..., :3].copy()
        stub = np.zeros((H, W), bool)
        # 续出来的皮肤要**缩在袖口里面**：贴着袖口边补的话，手一转那一条就从
        # 袖子侧面戳出来，成了一小块飘在外面的肉色（实测 ±20° 时左右各一片）。
        inner = erode(m, WRIST_STUB_IN)
        top_rows = np.arange(wrist_y, min(H, wrist_y + 4))
        for x in range(W):
            if not m[top_rows, x].any():
                continue
            cols = hand_rgb[top_rows, x][m[top_rows, x]]
            c = np.median(cols, axis=0)
            for y in range(max(0, wrist_y - WRIST_STUB), wrist_y):
                if inner[y, x] and body[y, x, 3] >= 250:
                    hand_rgb[y, x] = c
                    stub[y, x] = True
        for seg, keep in (("upper", m & (yy_col <= elbow_y + half)),
                          ("fore",  m & (yy_col >= elbow_y - half) & (yy_col <= wrist_y + 1)),
                          ("hand",  (m & (yy_col >= wrist_y)) | stub)):
            # 把原画自己的抗锯齿边一起抓进来，掩码内严格保留原 alpha，
            # 只在往外多扩的 2px 上做软边 —— 这样静止合成能逐像素还原
            grab = dilate(keep, 2) & (body[..., 3] > 0)
            if seg == "hand":
                grab = (grab | stub) & ~(yy_col < wrist_y - WRIST_STUB)
            sa = soft(dilate(grab, 2))
            sa[grab] = 1.0
            a = orig_a * sa
            if seg == "hand":
                a[stub] = 1.0
            # 肘部重叠带：**只让前臂淡入**，上臂在带内保持满值当底，
            # 这样 over 合成仍然是满的（两件都淡的话 0.5 over 0.5 = 0.75，会露底）
            if seg == "fore":
                yy = np.arange(H)[:, None].astype(np.float32)
                a = a * np.clip((yy - (elbow_y - half)) / ELBOW_OVERLAP, 0.0, 1.0)
            ys, xs = np.nonzero(a > 0.004)
            box = (int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1)
            img = cut(hand_rgb if seg == "hand" else body[..., :3], a, box)
            name = f"arm_{side}_{seg}" if seg != "hand" else f"hand_{side}"
            img.save(os.path.join(sp, name + ".png"))
            if seg == "upper":
                joint, grp, lay = pts[f"shoulder_{side}"], f"arm_{side}", layer[side]
                note = "上臂：绕肩旋转"
            elif seg == "fore":
                joint, grp, lay = pts[f"elbow_{side}"], f"forearm_{side}", layer[side] + 2
                note = "前臂：绕肘旋转（父组＝上臂）"
            else:
                wx = np.nonzero(m[wrist_y])[0]
                joint = (float(wx.mean()) if wx.size else float(box[0] + box[2]) / 2.0,
                         float(wrist_y))
                grp, lay = f"hand_{side}", hand_layer[side]
                note = (f"手：绕腕旋转（父组＝前臂）；往袖子里续了 {WRIST_STUB}px 皮肤，"
                        f"画在前臂底下，静止时被袖口压住")
            report["parts"].append({
                "id": name, "file": f"sprites/{name}.png",
                "pos": [box[0], box[1]], "size": [box[2] - box[0], box[3] - box[1]],
                "group": grp, "layer": lay,
                "pivot": [float(joint[0]), float(joint[1])],
                "note": note,
            })
            if seg == "hand":
                report["checks"].setdefault("wrist_y", {})[side] = int(wrist_y)
                report["checks"].setdefault("hand_stub_px", {})[side] = int(stub.sum())

    # ---- 验收：四件叠回去 + 新躯干，和原画静止帧必须一样 ----
    comp = np.zeros((H, W, 4), np.float32)
    def over(dst, src_rgb, src_a):
        a = src_a[..., None]
        dst[..., :3] = src_rgb * a + dst[..., :3] * (1 - a)
        dst[..., 3:] = a + dst[..., 3:] * (1 - a)
        return dst
    for lid in ("seg_leg_l", "seg_leg_r"):
        lp = next((q for q in bp["parts"] if q["id"] == lid), None)
        if not lp:
            continue
        li = np.array(Image.open(os.path.join(sp, lid + ".png")).convert("RGBA"))
        lx, ly = lp["pos"]
        lb = np.zeros((H, W, 4), np.float32)
        lb[ly:ly + li.shape[0], lx:lx + li.shape[1], :3] = li[..., :3]
        lb[ly:ly + li.shape[0], lx:lx + li.shape[1], 3] = li[..., 3] / 255.0
        comp = over(comp, lb[..., :3], lb[..., 3])
    comp = over(comp, newbody[..., :3].astype(np.float32), (newbody[..., 3] / 255.0).astype(np.float32))
    for p in sorted(report["parts"], key=lambda q: q["layer"]):   # 必须按层序叠：手在袖子底下
        im = np.array(Image.open(os.path.join(sp, os.path.basename(p["file"]))).convert("RGBA"))
        x, y = p["pos"]
        h, w = im.shape[:2]
        layerbuf = np.zeros((H, W, 4), np.float32)
        layerbuf[y:y + h, x:x + w, :3] = im[..., :3]
        layerbuf[y:y + h, x:x + w, 3] = im[..., 3] / 255.0
        comp = over(comp, layerbuf[..., :3], layerbuf[..., 3])
    orig_a = (body[..., 3] / 255.0).astype(np.float32)
    # comp[...,:3] 累加出来已经是预乘 alpha 的值，原图要乘一次 alpha 才同口径
    diff = np.abs(comp[..., :3] - body[..., :3].astype(np.float32) * orig_a[..., None])
    bad = int((diff.max(axis=2) > 12).sum())
    report["checks"]["static_diff_px"] = bad
    if os.environ.get("ARM_DEBUG"):
        Image.fromarray(newbody).save("/tmp/g4c_newbody.png")
        dm = (diff.max(axis=2) > 12)
        Image.fromarray((dm * 255).astype(np.uint8)).save("/tmp/g4c_diffmap.png")
        print("  [debug] 差异分布：", {f"y{y0}-{y1}": int(dm[y0:y1].sum())
              for y0, y1 in ((0, 330), (330, 560), (560, 760), (760, 1292))})
    report["checks"]["arm_px"] = {s: int(arms[s].sum()) for s in arms}
    json.dump(report, open(os.path.join(sp, "arm_parts.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    print(f"手臂拆件完成：4 件；躯干补了 {report['checks']['torso_filled_px']} 像素、"
          f"清掉 {report['checks']['torso_cleared_px']} 像素；静止合成差 {bad} 像素")
    for p in report["parts"]:
        print(f"  {p['id']:14s} pos={p['pos']} size={p['size']} pivot={p['pivot']} layer={p['layer']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
