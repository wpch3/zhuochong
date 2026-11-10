#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""make_mouth_open_parts.py - 用 AI 重绘的「张嘴脸」换掉程序画的假口腔（G4s / D19）。

为什么要重做：
  第一版 make_mouth_parts.py 的口内是按配色**算出来**的——一个六边形色块加一条
  红带当舌头。张到一半就是一块深褐斑，没有上颚、没有牙、没有嘴角，用户实拍反馈
  「惊讶的嘴巴位置错误，形状也很怪」。原画里嘴只有一条闭合笑线，口腔在原画里
  **根本不存在**，所以按 D19 必须 AI 生图重绘，不能靠几何拼。

做法（和刘海/眉毛/躯干同一条流水线）：
  1. design/redraw/face_mouthopen.png = 同一张脸、嘴张开的 AI 重绘（洋红底）；
  2. 用**两只虹膜**做相似变换配准（只有缩放+平移，脸没转），再在脸部做 NCC 微调；
  3. 把重绘配准到 body_full 的像素空间，只取**嘴洞**那一块（深色轮廓围起来的区域，
     牙是白的、舌是粉的，都在洞里，按填洞取回来）；
  4. 裁成 mouth_cavity.png（口内，带自己的轮廓线）+ mouth_mask.png（开口形状），
     上沿对齐实测的笑线（所以位置不会偏），宽度不超过笑线宽度。

输出：sprites/mouth_cavity.png、sprites/mouth_mask.png、sprites/mouth_parts.json
      （字段与 make_mouth_parts.py 一致，make_rig.py 不用改读法）

用法：
  ~/.imgenv/bin/python tools/make_mouth_open_parts.py --character xiaoxun --form teen
"""
from __future__ import annotations
import argparse, json, os
from collections import deque

import numpy as np
from PIL import Image

SKIN = (252, 228, 216)
WIDTH_RATIO = 1.00      # 开口最大宽度 / 笑线宽度
FEATHER = 1             # 边缘羽化圈数


# ---------- 小工具（无 scipy，自己写） ----------
def flood(mask, seed):
    h, w = mask.shape
    out = np.zeros_like(mask)
    if not mask[seed]:
        return out
    q = deque([seed]); out[seed] = True
    while q:
        y, x = q.popleft()
        for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            ny, nx = y + dy, x + dx
            if 0 <= ny < h and 0 <= nx < w and mask[ny, nx] and not out[ny, nx]:
                out[ny, nx] = True; q.append((ny, nx))
    return out


def clusters(mask, min_px=40):
    """返回 [(像素数, 质心y, 质心x, 掩码), ...]，按大小降序。"""
    seen = np.zeros_like(mask); out = []
    ys, xs = np.nonzero(mask)
    for y, x in zip(ys, xs):
        if seen[y, x]:
            continue
        c = flood(mask & ~seen, (int(y), int(x)))
        seen |= c
        n = int(c.sum())
        if n >= min_px:
            cy, cx = np.nonzero(c)
            out.append((n, float(cy.mean()), float(cx.mean()), c))
    out.sort(key=lambda t: -t[0])
    return out


def fill_holes(mask):
    """填掉被 mask 包住的洞（牙齿是白的，不能漏）。"""
    h, w = mask.shape
    free = ~mask
    out = np.zeros_like(mask)
    q = deque()
    for x in range(w):
        for y in (0, h - 1):
            if free[y, x] and not out[y, x]:
                out[y, x] = True; q.append((y, x))
    for y in range(h):
        for x in (0, w - 1):
            if free[y, x] and not out[y, x]:
                out[y, x] = True; q.append((y, x))
    while q:
        y, x = q.popleft()
        for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            ny, nx = y + dy, x + dx
            if 0 <= ny < h and 0 <= nx < w and free[ny, nx] and not out[ny, nx]:
                out[ny, nx] = True; q.append((ny, nx))
    return mask | ~out


def soften(mask, rounds=2):
    f = mask.astype(np.float32)
    for _ in range(rounds):
        p = np.pad(f, 1, mode="edge")
        f = (p[:-2, 1:-1] + p[2:, 1:-1] + p[1:-1, :-2] + p[1:-1, 2:] + p[1:-1, 1:-1] * 4) / 8.0
    f = np.clip(f * 1.35 - 0.18, 0, 1)
    f[mask] = np.maximum(f[mask], 0.85)
    return f


def find_mouth(rgb, keep, cx, cy, half_w, half_h):
    """在窗口里找**张开的口内**（暗红）：返回 (cx, cy, n) 或 None。

    为什么要单独找：张嘴脸的配准如果只看整脸（眼睛/头发/肤色），嘴这一小块
    权重极低，解出来的平移对嘴并不敏感 —— 实测 Q 版张嘴脸按眼白配准后，
    口的中心还在原画嘴线上方 ~50px，于是"取口内"的窗口整个落在衣领上，
    mouth_cavity 切出来的是一块青色夹克（渲出来就是嘴上一个青方块）。
    口的暗红（R−B 大、亮度 <195）在这张图上独一无二，腮红是浅粉（亮度 >210），
    眼白/皮肤也不满足，一判一个准。
    """
    h, w = rgb.shape[:2]
    x0, x1 = int(max(0, cx - half_w)), int(min(w, cx + half_w))
    y0, y1 = int(max(0, cy - half_h)), int(min(h, cy + half_h))
    if x1 - x0 < 6 or y1 - y0 < 6:
        return None
    sub = rgb[y0:y1, x0:x1]
    kp = keep[y0:y1, x0:x1]
    r, g, b = sub[..., 0], sub[..., 1], sub[..., 2]
    lum = (r + g + b) / 3.0
    m = kp & (r - b > 28) & (r - g > 8) & (lum < 196) & (r > 70)
    if m.sum() < 60:
        return None
    ys, xs = np.nonzero(m)
    return (float(xs.mean()) + x0, float(ys.mean()) + y0, int(m.sum()))


def iris_centers_redraw(rgb, keep):
    """在重绘图里找两只虹膜：蓝得发深、成团、左右各一。"""
    r, g, b = rgb[..., 0].astype(int), rgb[..., 1].astype(int), rgb[..., 2].astype(int)
    blue = keep & (b > r + 30) & (b > 110) & (r < 190) & (g < b - 10)
    ys, xs = np.nonzero(keep)
    y0, y1 = ys.min(), ys.max(); x0, x1 = xs.min(), xs.max()
    band = np.zeros_like(blue)
    band[int(y0 + (y1 - y0) * 0.30):int(y0 + (y1 - y0) * 0.65),
         int(x0 + (x1 - x0) * 0.15):int(x0 + (x1 - x0) * 0.85)] = True
    cs = clusters(blue & band, min_px=300)
    if len(cs) < 2:
        raise SystemExit("[mouth_open] 重绘图里找不到两只虹膜（蓝色团块不足）")
    cs = sorted(cs[:4], key=lambda t: -t[0])[:2]
    cs.sort(key=lambda t: t[2])                      # 按 x 排序：左、右
    return (cs[0][2], cs[0][1]), (cs[1][2], cs[1][1])


def warp(rd_rgb, rd_a, shape, s, tx, ty):
    """把重绘图按 (缩放 s、平移) 采样到 body 空间；输出 rgb + alpha。"""
    H, W = shape
    im = Image.fromarray(np.dstack([rd_rgb, rd_a]).astype(np.uint8), "RGBA")
    # PIL 的 AFFINE 是 输出→输入 的矩阵
    m = (1.0 / s, 0.0, tx, 0.0, 1.0 / s, ty)
    out = im.transform((W, H), Image.AFFINE, m, resample=Image.BICUBIC)
    a = np.array(out)
    return a[..., :3].astype(np.int32), a[..., 3]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--character", required=True)
    ap.add_argument("--form", required=True)
    ap.add_argument("--root", default=".")
    args = ap.parse_args()
    base = os.path.join(args.root, "characters", args.character, "forms", args.form)
    sp = os.path.join(base, "sprites")
    # 形态级优先（见 tools/form_art.py）：Q 版的嘴是另一张嘴，不能拿少女的重绘去配准。
    import form_art
    redraw = os.path.join(args.root, form_art.redraw_for(
        args.root, args.character, args.form, "face_mouthopen"))

    body = np.array(Image.open(os.path.join(sp, "body_full.png")).convert("RGBA"))
    H, W = body.shape[:2]
    brgb = body[..., :3].astype(np.int32)

    rd = np.array(Image.open(redraw).convert("RGBA"))
    rrgb = rd[..., :3].astype(np.int32)
    r_, g_, b_ = rrgb[..., 0], rrgb[..., 1], rrgb[..., 2]
    magenta = (np.minimum(r_, b_) - g_ > 60) & (r_ > 140) & (b_ > 140)
    keep = (rd[..., 3] > 128) & ~magenta

    # ---- 1. 配准 ----
    # 底图若已被 align_redraw.py 预配准（同目录有 .align.json），画布 = body_full、
    # 人物已在正确位置 ⇒ 恒等映射，**不许再套一次缩放平移**（会把脸推走）。
    pre = form_art.aligned_info(redraw)
    # 底图如果**本来就是画布尺寸**（align_redraw 的输出），那就是恒等映射，
    # 不能再套任何配准：套一次就是把已经对齐的脸推走。
    # 判据用尺寸 —— 比"有没有 sidecar"更可靠（sidecar 也可能配在原始尺寸上）。
    ident = (pre is not None and Image.open(redraw).size == (W, H))
    if pre is not None and "broken" in pre:
        raise SystemExit(f"[张嘴] 侧车文件坏了：{pre['broken']}")
    mouthp_old = json.load(open(os.path.join(sp, "mouth_parts.json"), encoding="utf-8"))
    line = mouthp_old["line"]
    mcx = (line["x0"] + line["x1"]) / 2.0
    mtop = line["y0"] + (line["y1"] - line["y0"]) * 0.5
    fx0, fx1 = int(mcx - 70), int(mcx + 70)
    fy0, fy1 = int(mtop - 110), int(mtop + 35)
    face_box = (slice(max(0, fy0), fy1), slice(max(0, fx0), fx1))
    ref = brgb[face_box].mean(axis=2)
    refm = (body[..., 3][face_box] > 128)
    refm[int(mtop - 12 - max(0, fy0)):int(mtop + 30 - max(0, fy0)),
         int(mcx - 26 - max(0, fx0)):int(mcx + 26 - max(0, fx0))] = False   # 挖掉嘴

    def ncc_of(ss, ttx, tty):
        wr, wa = warp(rrgb, (keep * 255).astype(np.uint8), (H, W), ss, ttx, tty)
        cur = wr[face_box].mean(axis=2)
        m = refm & (wa[face_box] > 128)
        if m.sum() < 500:
            return -1.0
        a = ref[m] - ref[m].mean(); bq = cur[m] - cur[m].mean()
        return float((a * bq).sum() / (np.sqrt((a * a).sum() * (bq * bq).sum()) + 1e-6))

    if ident:
        # 底图已经是画布尺寸（align_redraw 按**眼睛**解出来的），整体不动；
        # 但"嘴"必须自己再对一次：同一张 AI 图里眼睛对上了不等于嘴对上了
        # （实测张嘴脸的眼-嘴距离比原画短 40~60px）。
        # 所以这里只做**嘴这一个特征**的平移校正，其余像素原封不动。
        s, tx, ty, ncc = 1.0, 0.0, 0.0, 1.0
        hit = find_mouth(rrgb, keep, mcx, mtop, 120, 150)
        if hit is None:
            raise SystemExit("[张嘴] 已配准的底图里找不到暗红口内（判据失效？）")
        gx, gy, gn = hit
        tx = gx - mcx
        ty = gy - (mtop + 12)
        print(f"[张嘴] 底图已是画布尺寸 → 整体恒等，"
              f"口内实测 ({gx:.0f},{gy:.0f}) → 嘴部平移校正 ({tx:+.1f},{ty:+.1f})px（{gn}px）")
    elif pre is not None:
        # 有 align_redraw 的解就当种子（±6% 尺度 / ±10px 平移），再用本工具自己的
        # NCC 收一遍。**不能直接用恒等映射**：那张四参数是整脸解的，
        # 嘴这一圈本来就是差异区，解出来的平移未必对口腔足够准（实测张嘴脸
        # 的 x 平移 21px 与闭眼脸 -12px 差 30px 以上，硬套会把口内取到下唇外）。
        sc = pre.get("scale") or [1.0, 1.0]
        tr = pre.get("translate") or [0.0, 0.0]
        s0 = float(np.sqrt(max(sc[0], 1e-6) * max(sc[1], 1e-6)))
        tx0, ty0 = -float(tr[0]) / s0, -float(tr[1]) / s0
        ncc, s, tx, ty = ncc_of(s0, tx0, ty0), s0, tx0, ty0
        for ds in np.linspace(-0.06, 0.06, 9):
            ss = s0 * (1 + ds)
            for ddy in range(-10, 11, 2):
                for ddx in range(-10, 11, 2):
                    v = ncc_of(ss, tx0 + ddx / ss, ty0 + ddy / ss)
                    if v > ncc:
                        ncc, s, tx, ty = v, ss, tx0 + ddx / ss, ty0 + ddy / ss
        print(f"[张嘴] 用 align_redraw 的解当种子（尺度 {sc}、平移 {tr}），"
              f"NCC 收到 {ncc:.3f}")
    else:
        eyes = json.load(open(os.path.join(sp, "eye_parts.json"), encoding="utf-8"))["eyes"]
        be = {}
        for e in eyes:
            be[e["side"]] = (e["patch_pos"][0] + e["iris_center"][0],
                             e["patch_pos"][1] + e["iris_center"][1])
        bl, br = be["l"], be["r"]
        rl, rr = iris_centers_redraw(rrgb, keep)
        d_body = ((br[0] - bl[0]) ** 2 + (br[1] - bl[1]) ** 2) ** 0.5
        d_rd = ((rr[0] - rl[0]) ** 2 + (rr[1] - rl[1]) ** 2) ** 0.5
        s = d_body / d_rd
        mb = ((bl[0] + br[0]) / 2.0, (bl[1] + br[1]) / 2.0)
        mr = ((rl[0] + rr[0]) / 2.0, (rl[1] + rr[1]) / 2.0)
        tx, ty = mr[0] - mb[0] / s, mr[1] - mb[1] / s

        # ---- 2. 脸部 NCC 微调（排除嘴那一块，因为那里本来就该不一样）----
        best = None
        for ds in (-0.03, -0.015, 0.0, 0.015, 0.03):
            ss = s * (1 + ds)
            for dy in range(-5, 6):
                for dx in range(-5, 6):
                    ttx = mr[0] - (mb[0] + dx) / ss
                    tty = mr[1] - (mb[1] + dy) / ss
                    v = ncc_of(ss, ttx, tty)
                    if best is None or v > best[0]:
                        best = (v, ss, ttx, tty)
        ncc, s, tx, ty = best

    mw = line["x1"] - line["x0"] + 1
    wrgb, walpha = warp(rrgb, (keep * 255).astype(np.uint8), (H, W), s, tx, ty)

    # ---- 3. 取嘴洞：在**原始分辨率**上取（牙只有十几像素，先缩小再找会被糊掉）----
    # body→redraw：x_rd = x_body / s + tx
    def to_rd(x, y):
        return x / s + tx, y / s + ty
    rx0, ry0 = to_rd(mcx - 34, mtop - 10)
    rx1, ry1 = to_rd(mcx + 34, mtop + 46)
    rx0, ry0, rx1, ry1 = (max(0, int(rx0)), max(0, int(ry0)),
                          min(rd.shape[1], int(rx1)), min(rd.shape[0], int(ry1)))
    sub_rgb = rrgb[ry0:ry1, rx0:rx1]
    sub_ok = keep[ry0:ry1, rx0:rx1]
    lum = sub_rgb.mean(axis=2)
    dark = sub_ok & (lum < 170)
    cs = clusters(dark, min_px=int(300 / max(s, 1e-3) ** 0 ))
    if not cs:
        raise SystemExit("[mouth_open] 配准后在嘴的位置找不到张开的口（深色区域太小）")
    cy0 = (mtop + 12 - ty * s) / 1.0
    ccy = (mtop + 14) / s + ty - ry0          # 预期嘴心（重绘像素坐标）
    ccx = mcx / s + tx - rx0
    cs.sort(key=lambda t: ((t[1] - ccy) ** 2 + (t[2] - ccx) ** 2) ** 0.5 - t[0] * 0.002)
    hole = fill_holes(cs[0][3])
    ys, xs = np.nonzero(hole)
    oy0, oy1, ox0, ox1 = ys.min(), ys.max(), xs.min(), xs.max()
    art = np.zeros((oy1 - oy0 + 1, ox1 - ox0 + 1, 4), np.uint8)
    art[..., :3] = sub_rgb[oy0:oy1 + 1, ox0:ox1 + 1]
    soft = soften(hole[oy0:oy1 + 1, ox0:ox1 + 1], 2)
    art[..., 3] = (soft * 255).round().astype(np.uint8)
    native = (art.shape[1], art.shape[0])

    # ---- 4. 缩到"不超过笑线宽"，上沿对齐笑线 ----
    tw = max(10, int(round(mw * WIDTH_RATIO)))
    th = max(8, int(round(art.shape[0] * tw / art.shape[1])))
    cav = Image.fromarray(art, "RGBA").resize((tw, th), Image.LANCZOS)
    ca = np.array(cav)
    a = ca[..., 3].astype(np.float32) / 255.0
    ca[..., 3] = (np.clip(a * 1.25 - 0.12, 0, 1) * 255).round().astype(np.uint8)
    cav = Image.fromarray(ca, "RGBA")
    pos = [int(round(mcx - tw / 2.0)), int(round(mtop))]

    # 开口形状 = 口内的剪影（同尺寸），rig 里当遮罩用
    mask_im = np.zeros_like(ca)
    mask_im[..., :3] = 255
    mask_im[..., 3] = ca[..., 3]
    Image.fromarray(mask_im, "RGBA").save(os.path.join(sp, "mouth_mask.png"))
    cav.save(os.path.join(sp, "mouth_cavity.png"))

    # ---- 5. 证据（D20）----
    lum2 = ca[..., :3].mean(axis=2)
    op = ca[..., 3] > 128
    top = op.copy(); top[int(th * 0.45):] = False
    bot = op.copy(); bot[:int(th * 0.55)] = False
    teeth = int(((lum2 > 190) & top).sum())
    tongue = int((((ca[..., 0].astype(int) - ca[..., 2]) > 25) & (lum2 > 90) & bot).sum())
    rep = {
        "source": ("design/redraw/face_mouthopen.png（AI 重绘张嘴脸）+ "
                   + ("align_redraw 预配准" if pre is not None else "虹膜配准")),
        "line": line,
        "mask": "mouth_mask.png", "cavity": "mouth_cavity.png",
        "pos": pos, "anchor_pos": [mcx, float(mtop)],
        # closed_sy = 闭嘴时遮罩的纵向压缩比。**必须是 0**：
        #   设成 1.2/th（≈0.04）时，闭嘴状态仍留 1px 高的缝，口内从那道缝里露出来，
        #   最终帧里嘴角挂着一小点红色（沙箱实拍 /tmp/g_states.png 的闭眼/笑眼格）。
        #   闭嘴的嘴线本来就烘在原画 body_full 上，遮罩压到 0 不会丢东西。
        "size": [tw, th], "open_h": th, "closed_sy": 0.0,
        "colors": mouthp_old.get("colors", {}),
        "register": {"scale": round(s, 4), "ncc": round(ncc, 4),
                     "seeded_by": ("identity" if ident else
                                   ("align_redraw" if pre is not None else "iris"))},
        "native_px": list(native), "checks": {"cavity_px": int(op.sum()), "teeth_px": teeth, "tongue_px": tongue,
                   "width_px": tw, "height_px": th},
        "note": "口内是 AI 重绘的真素材（含上颚/牙/舌/嘴角），不是几何色块；"
                "开口大小 = 压缩 sy，口内跟着一起压（motion_from=mouth_mask），"
                "所以半开时是一张压扁的嘴而不是一条黑缝。",
    }
    json.dump(rep, open(os.path.join(sp, "mouth_parts.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    print(f"张嘴零件完成：配准 scale={s:.4f} NCC={ncc:.3f}；"
          f"口内 {tw}x{th}（{op.sum()}px，牙 {teeth}px、舌 {tongue}px）→ pos={pos}")


if __name__ == "__main__":
    main()
