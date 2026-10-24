#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""make_eye_closed_parts.py - 用 AI 重绘的「闭眼脸」切出真·闭眼零件（G4r / D19）。

为什么要重做：
  第一版 make_eyelid_parts.py 的眼皮是**从眼睛上方那块皮肤切下来的几何贴片**，
  靠往下滑盖住眼睛。问题是：原画里根本没有"闭着的眼睛"这张画——闭到底时屏幕上
  只剩一块比周围亮的肤色饼 + 一条被眼眶遮罩裁短的睫毛线，用户实拍反馈
  「开心的闭眼错位」。按 D19，原画没有的像素必须 AI 生图重绘。

做法（和张嘴/刘海/眉毛同一条流水线）：
  1. design/redraw/face_eyesclosed.png = 同一张脸、眼睛闭上的 AI 重绘（洋红底）；
  2. 配准：闭眼图里没有虹膜可用，改用**肤色区域的外接框**定初值，
     再在"挖掉眼睛那条带"的脸部做 NCC 网格微调（缩放 + 平移）；
  3. 每只眼睛切一块"盖得住原画睁眼"的补片（眼眶外扩 + 羽化），
     逐通道最小二乘把补片的肤色配到本体上，避免贴上去有色阶；
  4. rig 里用 tags:["eye_closed"]（引擎已有：opacity *= blink），
     和睁眼件交叉淡化 —— 这就是 Live2D 的 ParamEyeLOpen 在贴图版里的等价做法。

输出：sprites/eye_l_closed.png、eye_r_closed.png、eye_closed_parts.json

同一条流水线还切\"笑眼\"（`--variant smile`，底图 design/redraw/face_eyesmile.png）：
  Live2D 的标准做法是**笑眼 = 闭眼的另一种形状**（谷型 ∪ → 山型 ∩），
  官方 Haru 的 F05 表情就是 `ParamEyeLOpen=0(Multiply) + ParamEyeLSmile=1(Add)`，
  所以笑眼件和闭眼件位置、口径完全一样，只是换一张重绘底图。

用法：
  ~/.imgenv/bin/python tools/make_eye_closed_parts.py --character xiaoxun --form teen
  ~/.imgenv/bin/python tools/make_eye_closed_parts.py --character xiaoxun --form teen --variant smile
"""
from __future__ import annotations
import argparse, json, os

import numpy as np
from PIL import Image

SKIN = (252, 228, 216)
MARGIN = 9          # 眼眶外扩多少像素（要盖住原画的上睫毛和眼角）
LASH_EXT = 26       # 补片再往外让这么多像素给**重绘的闭眼睫毛**
#   ★ 闭眼的睫毛比虹膜宽：只按眼球框外扩时，睫毛两端会被补片边界横着切一刀，
#     最终帧里是一根"方块睫毛"（沙箱实拍 /tmp/rig_closed_left_zoom.png 第一张）。
#     多让 14px，alpha 仍由"原画这里是皮肤或线稿"那条判据把关，
#     所以多出来的面积不会把头发糊上来。
FEATHER = 7         # 边缘羽化宽度（软椭圆）

# 各档眼形的切法。闭眼/笑眼/痛苦眼都是「一条睫毛线 + 一片皮肤」，框按**眼球**外扩就够
# （眨到底时 eye_open 件已经淡没了，补片只要盖住虹膜那一小块）；
# 瞪大眼不一样：它要顶替**整只睁着的眼**（眼白 + 上下眼线都抬高了），框得大一圈。
# 注意不能直接用 eye_parts.json 的 patch 框（117x68）：那张画布大半是空白，真正的
# 眼眶墨迹只有 48x42，按 patch 框外扩会一路探到脸外的洋红背景上，补片盖不满直接报错。
VARIANTS = {
    #            底图                    中文名   框     额外外扩(x, y)  挖虹膜
    "closed": ("face_eyesclosed.png", "闭眼",     "ball",  (0, 0),   False),
    "smile":  ("face_eyesmile.png",   "笑眼",     "ball",  (0, 0),   False),
    "pain":   ("face_eyespain.png",   "痛苦闭眼", "ball",  (4, 2),   False),
    "wide":   ("face_eyeswide.png",   "瞪大眼",   "ball",  (13, 11), True),
}


def skin_mask(rgb, keep):
    """暖色皮肤：白夹克 R≈G≈B、头发偏蓝，都要排掉，否则外接框会变成整张图。"""
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    return keep & (r > 205) & ((r - b) > 18) & ((r - b) < 70) & (g < r) & (g > r - 45)


def sclera_color(sprite_path):
    """从角色**自己的常态眼件**里取眼白色。

    不能在重绘补片里就地采样：补片四角有浅紫头发（低饱和、亮度也 >212）和腮红，
    中位数会被带成粉紫色——第三版就是这么填出一个粉色大饼的。
    """
    try:
        a = np.array(Image.open(sprite_path).convert("RGBA")).astype(np.int32)
    except OSError:
        return np.array([236., 228., 236.], np.float32)
    rgb, ok = a[..., :3], a[..., 3] > 200
    sat = rgb.max(axis=2) - rgb.min(axis=2)
    m = ok & (sat < 20) & (rgb.mean(axis=2) >= 215)
    if m.sum() < 40:
        return np.array([236., 228., 236.], np.float32)
    return np.median(rgb[m], axis=0).astype(np.float32)


def erase_iris(patch, alpha_ok, ball_size, sclera):
    """把 AI 瞪大眼里画死的虹膜抠掉、填成眼白，让原来的 eye_*_ball 继续管视线。

    为什么要挖：补片带着虹膜，瞪大眼期间视线就不动了——眼球件（tags:["gaze"]）被盖住。
    Live2D 里 ParamEyeLWide 是形变眼眶、虹膜照样跟着 ParamEyeBallX 走，贴图版要等价，
    补片就只能提供**眼白和眼线**。顺带正好对上 2026-10-15 的验收意见
    「眼球不自然变大像个怪物」：真·瞪大 = 眼眶开得更大、虹膜**原尺寸**。

    判据为什么是几何的，两版颜色/行扫描都翻了车，记在这里免得再试：
      v1「B>140 且 B−R>45」：补片缩到 0.21 倍后虹膜被邻域平均、又叠了肤色配色的暖偏移，
         蓝色退成灰紫，1182px 的盘只逮到 406px，留了一块灰盘。
      v2「逐行取眼白最左/最右，中间非眼白的就是虹膜」：浅紫头发亮度也 ≥212，
         被当成眼白，行填充把上睫毛一起吃了，还填成了粉色。
    现在的做法：虹膜盘**就在补片正中**（补片框是按 ball_pos 居中切的），
    所以直接按眼球尺寸画个椭圆填掉，只避开皮肤。尺寸不依赖任何检测，不会跑偏；
    质心用宽松的蓝色判据微调一下，检测失败就退回正中（退化也只是回到几何中心）。
    """
    hh, ww = patch.shape[:2]
    r, g, b = patch[..., 0], patch[..., 1], patch[..., 2]
    lum = patch.mean(axis=2)
    skin = skin_mask(patch.astype(np.int32), alpha_ok)
    yy = np.arange(hh)[:, None].astype(np.float32)
    xx = np.arange(ww)[None, :].astype(np.float32)
    cy, cx = (hh - 1) / 2.0, (ww - 1) / 2.0
    # 质心微调：中心三分之一区域里偏蓝的像素
    core = (np.abs(xx - cx) < ww * 0.33) & (np.abs(yy - cy) < hh * 0.33)
    blue = alpha_ok & core & ((b - r) > 20) & ~skin
    if blue.sum() > 80:
        ys, xs = np.nonzero(blue)
        cy, cx = float(ys.mean()), float(xs.mean())
    # 椭圆半径：实测 AI 画的虹膜是 27x31，常态眼球 31x30 —— 两者差不多大，
    # 所以略大于眼球一点点就够（多出来的那 1~2px 是抗锯齿边，留着会显脏）。
    # 第三版按 ball/2*1.35 挖，横向超了 1.5 倍，把下眼睑和整圈眼白全吃了。
    rx = ball_size[0] * 0.5 * 1.08
    ry = ball_size[1] * 0.5 * 1.18
    d2 = ((xx - cx) / rx) ** 2 + ((yy - cy) / ry) ** 2
    iris = alpha_ok & ~skin & (d2 <= 1.0)
    if iris.sum() < 150:
        return patch, 0
    fill = sclera
    # 边缘软一点：按到椭圆边界的距离做 1.5px 过渡
    t = np.clip((1.0 - np.sqrt(d2)) / 0.06, 0.0, 1.0) * (alpha_ok & ~skin)
    out = patch * (1 - t[..., None]) + fill[None, None, :] * t[..., None]
    return out, int(iris.sum())


def _scale_rgba(rgb, a, kx: float, ky: float):
    """按 (kx,ky) 各向异性重采样一张已预乘的补片（避免透明边渗色）。"""
    pm = np.dstack([rgb * a[..., None], a * 255.0])
    im = Image.fromarray(np.clip(pm, 0, 255).astype(np.uint8), "RGBA")
    im = im.resize((max(4, int(round(rgb.shape[1] * kx))),
                    max(4, int(round(rgb.shape[0] * ky)))), Image.LANCZOS)
    arr = np.asarray(im).astype(np.float32)
    a2 = arr[..., 3] / 255.0
    rgb2 = np.clip(arr[..., :3] / np.maximum(a2[..., None], 1e-3), 0, 255)
    return rgb2, a2


def _dilate(mask, n):
    """二值膨胀（不用 scipy）：n 圈 4 邻域。"""
    m = mask.copy()
    for _ in range(n):
        g = m.copy()
        g[1:, :] |= m[:-1, :]
        g[:-1, :] |= m[1:, :]
        g[:, 1:] |= m[:, :-1]
        g[:, :-1] |= m[:, 1:]
        m = g
    return m


def _isolate_eye(alpha, eye_zone, pad=10):
    """只保留"与眼眶连通、且在眼眶外扩 pad 像素内"的那一块 alpha。

    为什么用几何而不是颜色：这只角色的眼白、头发、虹膜都是紫调亮色
    （实测 eye_l_base 231,213,227；重绘里"眼白"与"头发"采样几乎同色），
    颜色判据全都会误伤。碎块在几何上和眼睛主体不连通，一判一个准。
    """
    from collections import deque
    h, w = alpha.shape
    allow = _dilate(eye_zone, pad)
    solid = (alpha > 0.35) & allow
    if not solid.any():
        return alpha
    # 从眼眶中心起 flood，只留连通的那块
    ys, xs = np.nonzero(eye_zone)
    seed = (int(np.clip(ys.mean(), 0, h - 1)), int(np.clip(xs.mean(), 0, w - 1)))
    if not solid[seed]:
        ys, xs = np.nonzero(solid)
        seed = (int(ys[0]), int(xs[0]))
    keep = np.zeros_like(solid)
    q = deque([seed]); keep[seed] = True
    while q:
        cy, cx = q.popleft()
        for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            ny, nx = cy + dy, cx + dx
            if 0 <= ny < h and 0 <= nx < w and solid[ny, nx] and not keep[ny, nx]:
                keep[ny, nx] = True
                q.append((ny, nx))
    # 软边（alpha 在 0.35 以下的那圈羽化）跟着连通块一起留
    keep = _dilate(keep, 3)
    out = np.where(keep & allow, alpha, 0.0).astype(np.float32)
    return out


def _dark_blob_centroid(rgb, mask, min_px=40):
    """在 mask 里找最大的那块暗色连通块，返回其质心 (x,y) 与像素数；找不到返回 None。

    暗色 = 睫毛/眼线（lum<155）。取**最大连通块**而不是全部暗像素：
    窗口里还压着头发的外轮廓线，一起算会把质心拽到头发上。
    """
    from collections import deque
    lum = rgb[..., :3].mean(axis=2) if rgb.shape[-1] >= 3 else rgb
    m = (lum < 155) & mask
    if m.sum() < min_px:
        return None
    h, w = m.shape
    seen = np.zeros_like(m, bool)
    best = None
    ys, xs = np.nonzero(m)
    for y0, x0 in zip(ys, xs):
        if seen[y0, x0]:
            continue
        q = deque([(y0, x0)]); seen[y0, x0] = True
        pts = []
        while q:
            cy, cx = q.popleft(); pts.append((cy, cx))
            for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                ny, nx = cy + dy, cx + dx
                if 0 <= ny < h and 0 <= nx < w and m[ny, nx] and not seen[ny, nx]:
                    seen[ny, nx] = True; q.append((ny, nx))
        if best is None or len(pts) > len(best):
            best = pts
    if best is None or len(best) < min_px:
        return None
    a = np.array(best, np.float64)
    return float(a[:, 1].mean()), float(a[:, 0].mean()), len(best)


def warp_box(rd_rgba, s, tx, ty, box):
    """把重绘图按 (缩放 s, 平移 tx,ty) 采样到 body 空间的 box=(x0,y0,x1,y1)。
    只算这一块，所以可以在网格搜索里跑几千次。"""
    x0, y0, x1, y1 = box
    im = Image.fromarray(rd_rgba, "RGBA")
    # 输出 (u,v) → 输入：x_in = (u + x0)/s + tx
    m = (1.0 / s, 0.0, x0 / s + tx, 0.0, 1.0 / s, y0 / s + ty)
    out = im.transform((x1 - x0, y1 - y0), Image.AFFINE, m, resample=Image.BICUBIC)
    a = np.array(out)
    return a[..., :3].astype(np.float32), a[..., 3]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--character", required=True)
    ap.add_argument("--form", required=True)
    ap.add_argument("--root", default=".")
    ap.add_argument("--variant", default="closed", choices=tuple(VARIANTS),
                    help="closed = 谷型闭眼（ParamEyeLOpen=0），smile = 山型笑眼（ParamEyeLSmile=1），"
                         "pain = >_< 痛苦闭眼（ParamEyeL/RPain=1），wide = 真·瞪大眼（ParamEyeL/RWide=1）")
    args = ap.parse_args()
    variant = args.variant
    src_name, label, box_from, (ex_x, ex_y), want_erase = VARIANTS[variant]
    base = os.path.join(args.root, "characters", args.character, "forms", args.form)
    sp = os.path.join(base, "sprites")
    # 形态级优先（forms/<形态>/design/redraw/<名>.png → 角色级），见 tools/form_art.py。
    # 原来写死角色级目录 ⇒ 给 Q 版跑这条命令会读到**少女那张闭眼脸**，
    # 配准照样能收敛（都是同一张脸的两代画风），但补片贴上去就是另一个人的眼。
    import form_art
    redraw = os.path.join(args.root, form_art.redraw_for(
        args.root, args.character, args.form, src_name[:-4]))

    body = np.array(Image.open(os.path.join(sp, "body_full.png")).convert("RGBA"))
    H, W = body.shape[:2]
    brgb = body[..., :3].astype(np.float32)
    bkeep = body[..., 3] > 128

    rd = np.array(Image.open(redraw).convert("RGBA"))
    rgb_h, rgb_w = rd.shape[:2]
    rrgb = rd[..., :3].astype(np.int32)
    r_, g_, b_ = rrgb[..., 0], rrgb[..., 1], rrgb[..., 2]
    magenta = (np.minimum(r_, b_) - g_ > 60) & (r_ > 140) & (b_ > 140)
    rkeep = (rd[..., 3] > 128) & ~magenta
    rd_rgba = np.dstack([rd[..., :3], (rkeep * 255).astype(np.uint8)]).astype(np.uint8)

    eyes = {e["side"]: e for e in
            json.load(open(os.path.join(sp, "eye_parts.json"), encoding="utf-8"))["eyes"]}

    # ---- 0. 配准 ----
    # 有 align_redraw 的 .align.json 时**不要**直接信恒等映射：那张图的四参数是拿
    # 全脸（含头发/五官）解出来的，眼睛那一块本来就该不一样，泛函对它并不敏感 ——
    # 实测同一套五张差分脸解出的 y 平移能差 60px，闭眼弧线就跑到眼睛上方去了。
    # 正确做法：把 align 的解当**种子**，再用本工具自己的 NCC（脸部、挖掉眼睛带）
    # 在 ±10% 尺度 / ±12px 平移里收一遍。既不会跑到别的架构上去，也不会各解各的。
    pre = form_art.aligned_info(redraw)
    # 底图如果**本来就是画布尺寸**（align_redraw 的输出），那就是恒等映射，
    # 不能再套任何配准：套一次就是把已经对齐的脸推走。
    # 判据用尺寸 —— 比"有没有 sidecar"更可靠（sidecar 也可能配在原始尺寸上）。
    ident = (pre is not None and Image.open(redraw).size == (W, H))
    if pre is not None and "broken" in pre:
        raise SystemExit(f"[{label}] 侧车文件坏了：{pre['broken']}")

    el, er = eyes["l"], eyes["r"]
    eye_y = (el["patch_pos"][1] + er["patch_pos"][1]) / 2.0
    fx0 = int(min(el["patch_pos"][0], er["patch_pos"][0]) - 20)
    fx1 = int(max(el["patch_pos"][0] + el["patch_size"][0],
                  er["patch_pos"][0] + er["patch_size"][0]) + 20)
    fy0, fy1 = int(eye_y - 70), int(eye_y + 120)
    fx0, fy0 = max(0, fx0), max(0, fy0)
    fx1, fy1 = min(W, fx1), min(H, fy1)
    ref = brgb[fy0:fy1, fx0:fx1].mean(axis=2)
    refm = bkeep[fy0:fy1, fx0:fx1].copy()
    refm[max(0, int(eye_y - 20) - fy0):int(eye_y + 75) - fy0, :] = False   # 挖掉眼睛带

    def ncc_at(ss, txx, tyy):
        cur, ca = warp_box(rd_rgba, ss, txx, tyy, (fx0, fy0, fx1, fy1))
        m = refm & (ca > 128)
        if m.sum() < 800:
            return -1.0
        cm = cur.mean(axis=2)
        a = ref[m] - ref[m].mean(); bq = cm[m] - cm[m].mean()
        return float((a * bq).sum() / (np.sqrt((a * a).sum() * (bq * bq).sum()) + 1e-6))

    if ident:
        # 底图已经是画布尺寸（align_redraw 的输出）⇒ 恒等映射。
        # ⚠️ 这条分支是**被实测逼出来的**：先试过"拿 align 的解当种子再 NCC 收一遍"，
        #   结果 NCC 把 ty 又推了 43px，采样窗口下缘滑到青色衣领上
        #   （把重绘图按最终映射裁出来看过，图里明明白白一块领子 + 一块洋红底），
        #   最终帧里睫毛变成一根方块。已经对齐的图不许再动。
        s, tx, ty, ncc = 1.0, 0.0, 0.0, 1.0
        print(f"[{label}] 底图已是画布尺寸（align_redraw 输出，色差 "
              f"{(pre.get('color_cost') or pre.get('face_cost') or '?')}）→ 恒等映射，不再配准")
    elif pre is not None:
        sc = pre.get("scale") or [1.0, 1.0]
        tr = pre.get("translate") or [0.0, 0.0]
        s0 = float(np.sqrt(max(sc[0], 1e-6) * max(sc[1], 1e-6)))
        tx0, ty0 = -float(tr[0]) / s0, -float(tr[1]) / s0
        ncc, s, tx, ty = ncc_at(s0, tx0, ty0), s0, tx0, ty0
        for ds in np.linspace(-0.10, 0.10, 9):
            ss = s0 * (1 + ds)
            for ddy in range(-12, 13, 3):
                for ddx in range(-12, 13, 3):
                    v = ncc_at(ss, tx0 + ddx / ss, ty0 + ddy / ss)
                    if v > ncc:
                        ncc, s, tx, ty = v, ss, tx0 + ddx / ss, ty0 + ddy / ss
        for ds in np.linspace(-0.01, 0.01, 5):
            ss = s * (1 + ds)
            for ddy in (-2, -1, 0, 1, 2):
                for ddx in (-2, -1, 0, 1, 2):
                    v = ncc_at(ss, tx + ddx / ss, ty + ddy / ss)
                    if v > ncc:
                        ncc, s, tx, ty = v, ss, tx + ddx / ss, ty + ddy / ss
        print(f"[{label}] 用 align_redraw 的解当种子（尺度 {sc}、平移 {tr}），"
              f"NCC 收到 {ncc:.3f}")
    else:
        # ---- 初值：两张图的"脸"（肤色块）外接框 ----
        bk_head = bkeep.copy(); bk_head[300:, :] = False      # 只要头那一段（手和腿也是皮肤）
        bs = skin_mask(brgb.astype(np.int32), bk_head)
        rs = skin_mask(rrgb, rkeep)
        def bbox(m):
            ys, xs = np.nonzero(m)
            return xs.min(), ys.min(), xs.max(), ys.max()
        bx0, by0, bx1, by1 = bbox(bs)
        rx0, ry0, rx1, ry1 = bbox(rs)
        s0 = (bx1 - bx0) / float(rx1 - rx0)
        bcx, bcy = (bx0 + bx1) / 2.0, (by0 + by1) / 2.0
        rcx, rcy = (rx0 + rx1) / 2.0, (ry0 + ry1) / 2.0

        best = None
        for s in np.linspace(s0 * 0.65, s0 * 1.30, 17):
            for dy in range(-24, 25, 3):
                for dx in range(-24, 25, 3):
                    tx = rcx - (bcx + dx) / s
                    ty = rcy - (bcy + dy) / s
                    v = ncc_at(s, tx, ty)
                    if best is None or v > best[0]:
                        best = (v, s, tx, ty)
        ncc, s, tx, ty = best
        bs_, btx, bty = s, tx, ty
        for ds in np.linspace(-0.01, 0.01, 5):
            ss = bs_ * (1 + ds)
            for dy in np.arange(-2, 2.01, 1.0):
                for dx in np.arange(-2, 2.01, 1.0):
                    txx = rcx - (bcx + dx) / ss
                    tyy = rcy - (bcy + dy) / ss
                    v = ncc_at(ss, txx, tyy)
                    if v > ncc:
                        ncc, s, tx, ty = v, ss, txx, tyy

    out = {"source": f"design/redraw/{src_name}（AI 重绘{label}脸）",
           "register": {"scale": round(s, 4), "ncc": round(ncc, 4),
                        "tx": round(float(tx), 3), "ty": round(float(ty), 3),
                        "seeded_by": ("identity" if ident else
                                      ("align_redraw" if pre is not None else "skin_bbox"))},
           "eyes": []}

    for side in ("l", "r"):
        e = eyes[side]
        # ---- 补片范围 = 眼球框外扩 MARGIN（眼球框来自 eye_parts.json，身体坐标）----
        # 不能拿"窗口里的深色像素"定框：那个窗口里还有眉毛和压过来的发丝，
        # 框会一路长到把两只眼连起来（实测 dark bbox 117x68 = 整个窗口）。
        gx0, gy0 = e["ball_pos"]
        gw, gh = e["ball_size"]
        if box_from == "patch":
            # 瞪大眼：框 = 整个眼眶，而且上缘要多让 ex_y（上眼线被抬高了）
            qx0, qy0 = e["patch_pos"]; qw, qh = e["patch_size"]
            ax0 = max(0, qx0 - ex_x); ax1 = min(W, qx0 + qw + ex_x)
            ay0 = max(0, qy0 - ex_y * 2); ay1 = min(H, qy0 + qh + ex_y)
        else:
            ax0 = max(0, gx0 - MARGIN - 4 - LASH_EXT - ex_x)
            ax1 = min(W, gx0 + gw + MARGIN + 4 + LASH_EXT + ex_x)
            ay0 = max(0, gy0 - MARGIN - 4 - LASH_EXT - ex_y)
            ay1 = min(H, gy0 + gh + MARGIN + 4 + LASH_EXT + ex_y)
        if want_erase:
            # 瞪大眼的补片要顶替**整只被撑开的眼**（眼白 + 抬高的上睫毛）。
            # 只按眼球框外扩是不够的：AI 把这只眼画成"瞳孔偏下、睫毛高高抬起"，
            # 实测睫毛在虹膜中心上方 87px、而框只有 ±76px ⇒ 睫毛被顶边横切，
            # 渲出来的惊讶态是一圈白 + 一圈蓝残边。
            # 这里在**重绘图里量出这只眼的真实范围**（近白眼白 ∪ 偏暖暗睫毛），
            # 再按配准参数换算回画布坐标，把框撑到能整只装下。
            cxb = (gx0 + gw * 0.5)
            cyb = (gy0 + gh * 0.5)
            sep = abs(eyes["r"]["ball_pos"][0] - eyes["l"]["ball_pos"][0]) or gw
            half_rx = max(40.0, sep * 0.42) / s        # 重绘图像素
            half_ry = max(60.0, gh * 1.45) / s
            cxr, cyr = cxb / s + tx, cyb / s + ty
            x0r, x1r = int(max(0, cxr - half_rx)), int(min(rgb_w, cxr + half_rx))
            y0r, y1r = int(max(0, cyr - half_ry)), int(min(rgb_h, cyr + half_ry))
            sub = rrgb[y0r:y1r, x0r:x1r]
            if sub.size:
                sr, sg, sb = sub[..., 0], sub[..., 1], sub[..., 2]
                slum = (sr + sg + sb) / 3.0
                eye_m = (((sr > 232) & (sg > 228) & (sb > 230) & (np.abs(sr - sb) < 16)) |
                         ((slum < 125) & (sr - sb > 4)))
                if eye_m.sum() > 200:
                    yy, xx = np.nonzero(eye_m)
                    bx0 = (x0r + xx.min() - tx) * s
                    bx1 = (x0r + xx.max() + 1 - tx) * s
                    by0 = (y0r + yy.min() - ty) * s
                    by1 = (y0r + yy.max() + 1 - ty) * s
                    ax0 = int(max(0, min(ax0, bx0 - 6)))
                    ax1 = int(min(W, max(ax1, bx1 + 6)))
                    ay0 = int(max(0, min(ay0, by0 - 6)))
                    ay1 = int(min(H, max(ay1, by1 + 6)))
        box = (ax0, ay0, ax1, ay1)
        # 要盖住的"原画眼睛" = 眼球框再放一点（睫毛和眼角），不含眉毛/头发
        eye_zone = np.zeros((ay1 - ay0, ax1 - ax0), bool)
        eye_zone[max(0, gy0 - 6 - ay0):gy0 + gh + 6 - ay0,
                 max(0, gx0 - 6 - ax0):gx0 + gw + 6 - ax0] = True
        # ---- 用"睫毛质心"把这个补片钉到这只眼睛上（逐眼校正）----
        # 四张差分脸的全局配准只到"大概对"，实测采样窗口下缘会滑到衣领上
        # （放大重绘图确认过：窗口里出现了青色领子和洋红底）。
        # 逐眼锚定把"重绘里这块睫毛"和"原画里这块睫毛"的质心对到一起，
        # 一像素一像素都是可核对的，不依赖任何全局猜测。
        #   重绘那一侧：把补片框映射回重绘图，找其中最大的暗块（睫毛）
        rx0, ry0 = box[0] / s + tx, box[1] / s + ty
        rx1, ry1 = box[2] / s + tx, box[3] / s + ty
        ix0, iy0 = max(0, int(rx0)), max(0, int(ry0))
        rr = rrgb[iy0:max(iy0 + 1, int(ry1)), ix0:max(ix0 + 1, int(rx1))]
        blob = _dark_blob_centroid(rr, np.ones(rr.shape[:2], bool)) if rr.size else None
        if blob is not None:
            gxr, gyr = blob[0] + ix0, blob[1] + iy0
            #   原画那一侧：眼球框外扩一点，取那里的暗块（睫毛/眼线）
            tgt_rgb = brgb[ay0:ay1, ax0:ax1]
            tmask = np.zeros(tgt_rgb.shape[:2], bool)
            m0y, m1y = max(0, gy0 - 6 - ay0), min(tgt_rgb.shape[0], gy0 + gh + 12 - ay0)
            m0x, m1x = max(0, gx0 - 6 - ax0), min(tgt_rgb.shape[1], gx0 + gw + 6 - ax0)
            tmask[m0y:m1y, m0x:m1x] = True
            tb = _dark_blob_centroid(tgt_rgb, tmask)
            if tb is not None:
                bx_, by_ = tb[0] + ax0, tb[1] + ay0
                ntx, nty = gxr - bx_ / s, gyr - by_ / s
                # 只接受小修正（<20px 画布），否则说明暗块认错对象了
                if abs(ntx - tx) * s < 20 and abs(nty - ty) * s < 20:
                    tx, ty = ntx, nty
        patch, pa = warp_box(rd_rgba, s, tx, ty, box)
        if (pa > 128).mean() < 0.9:
            raise SystemExit(f"[eye_{variant}] {side} 眼补片在重绘图里没盖满（配准失败？）")
        hh, ww = patch.shape[:2]
        n_iris = 0
        if want_erase:
            # ⚠️ 必须在肤色配色之前挖：配色的权重按亮度走，会把暖偏移糊到虹膜上
            patch, n_iris = erase_iris(patch, pa > 128, (gw, gh),
                                       sclera_color(os.path.join(sp, f"eye_{side}_base.png")))
            if n_iris < 150:
                raise SystemExit(f"[eye_{variant}] {side} 眼没找到虹膜（只 {n_iris} px）："
                                 "重绘图的眼白没围成一圈，或瞳色对不上色卡（DC55）")
        if want_erase:
            # 眼白**尺寸归一**：AI 把"瞪大"画成了整只眼放大（重绘眼白 114x118 画布像素，
            # 本体眼眶只有 104x87），照抄就是脸颊上一块白圆角矩形（沙箱实拍
            # /tmp/f_surprise.png、/tmp/surprise_zoom2.png）。
            # 正确处理：把补片各向异性缩到「眼白 = 本体眼眶 x1.06」，并以**眼球中心**为锚。
            # 虹膜早就在上一步挖掉了，缩放大小时虹膜由 eye_<side>_ball 负责，不受影响。
            whites = ((patch[..., 0] > 232) & (patch[..., 1] > 228) & (patch[..., 2] > 230)
                      & (pa > 0.5))
            if whites.sum() > 400:
                ys_, xs_ = np.nonzero(whites)
                sw = xs_.max() - xs_.min() + 1
                sh = ys_.max() - ys_.min() + 1
                aw, ah = e.get("aperture_size") or (gw, gh)
                kx = float(np.clip(aw * 1.06 / max(1, sw), 0.55, 1.15))
                ky = float(np.clip(ah * 1.06 / max(1, sh), 0.55, 1.15))
                if abs(kx - 1) > 0.02 or abs(ky - 1) > 0.02:
                    scx = (xs_.min() + xs_.max()) / 2.0
                    scy = (ys_.min() + ys_.max()) / 2.0
                    patch, pa = _scale_rgba(patch, pa.astype(np.float32), kx, ky)
                    hh, ww = patch.shape[:2]
                    ax0 = int(round(gx0 + gw / 2.0 - scx * kx))
                    ay0 = int(round(gy0 + gh / 2.0 - scy * ky))
                    ax0 = max(0, min(W - ww, ax0))
                    ay0 = max(0, min(H - hh, ay0))
                    ax1, ay1 = ax0 + ww, ay0 + hh
                    eye_zone = np.zeros((hh, ww), bool)
                    eye_zone[max(0, gy0 - 6 - ay0):min(hh, gy0 + gh + 6 - ay0),
                             max(0, gx0 - 6 - ax0):min(ww, gx0 + gw + 6 - ax0)] = True
                    print(f"  眼白归一到本体眼眶：{sw}x{sh} → 缩放 ({kx:.3f},{ky:.3f}) "
                          f"→ {ww}x{hh} @ ({ax0},{ay0})")

        tgt = brgb[ay0:ay1, ax0:ax1]
        bk_box = bkeep[ay0:ay1, ax0:ax1]

        # ---- 逐通道最小二乘配色：只用"两边都是皮肤"的像素，别把头发和睫毛算进去 ----
        both_skin = (skin_mask(patch.astype(np.int32), pa > 128)
                     & skin_mask(tgt.astype(np.int32), bk_box))
        # ⚠️ 皮肤像素的取值范围很窄（都在 240 上下），直接最小二乘解 gain+offset 是**病态**的：
        # 实测解出 gain=0.15 / offset=214，皮肤是对上了，但睫毛那种暗像素被映射成亮红色
        # （40*0.15+214=246，而绿通道只到 123）——截图里那条"红杠"就是这么来的。
        # 正确做法（cel 风格专用）：
        #   · 只解**平移**（gain 固定 1），把两张图的肤色均值对齐；
        #   · 而且只把这个平移**作用在肤色像素上**：睫毛/线稿这种暗像素原样保留
        #     （AI 出图时 prompt 已经锁死了线稿色，本来就是对的）。
        gain = [1.0, 1.0, 1.0]; off = [0.0, 0.0, 0.0]
        if both_skin.sum() > 60:
            for c in range(3):
                X = patch[..., c][both_skin]; Y = tgt[..., c][both_skin]
                off[c] = float(np.clip(Y.mean() - X.mean(), -45, 45))
        lum_p = patch.mean(axis=2)
        w = np.clip((lum_p - 130.0) / 50.0, 0.0, 1.0)[..., None]   # 亮=皮肤才改色
        patch = patch + w * np.array(off, np.float32)[None, None, :]
        patch = np.clip(patch, 0, 255)

        # ---- 羽化成一个软椭圆：方补丁的直角边在脸上一眼就看得出来 ----
        yy = np.arange(hh)[:, None].astype(np.float32)
        xx = np.arange(ww)[None, :].astype(np.float32)
        cy, cx = (hh - 1) / 2.0, (ww - 1) / 2.0
        rad = np.sqrt(((xx - cx) / (ww / 2.0)) ** 2 + ((yy - cy) / (hh / 2.0)) ** 2)
        k = FEATHER / max(ww, hh) * 2.0
        alpha = np.clip((1.0 - rad) / max(k, 1e-3) + 0.35, 0, 1)
        alpha *= (pa > 128)
        alpha *= bk_box                       # 不要糊到脸外面去
        # ⚠️ 曾经试过"按冷色判头发、把冷色像素的 alpha 清零"——**不行**：
        #   这角色的眼白本身就带紫（实测 eye_l_base 中位色 231,213,227、
        #   重绘脸的"眼白"和"头发"采样几乎同色），按色相判会把眼白一起挖掉
        #   （闭眼左眼覆盖率当场从 97.3% 掉到 71.9%，瞪大眼左眼掉到 10.0%）。
        #
        # 现在的口径：**让原画当裁判** —— 补片只许盖在"原画这里是皮肤或线稿"的地方。
        #   重绘里的头发位置和原画差几像素，补片椭圆就把一撮蓝紫发糊到脸颊上
        #   （放大图里那道蓝楔子）。按原画分类：暖色亮 = 皮肤、暗 = 睫毛/线稿，
        #   其余（原画这里是头发/背景）= 不许盖。判据用**原画**的像素，
        #   所以完全不受"重绘的眼白也带紫"影响。
        _t_r = tgt[..., 0]; _t_b = tgt[..., 2]; _t_lum = tgt.mean(axis=2)
        body_skin = (_t_r > 200) & (_t_r > _t_b + 8)
        body_line = _t_lum < 150
        #   eye_zone 里一律放行：那只睁着的眼睛的虹膜是**紫调亮色**，
        #   既不算暖皮肤也不算暗线稿，不放行就直接盖不住（覆盖率 97%→86%）。
        alpha = np.where(body_skin | body_line | eye_zone, alpha, 0.0).astype(np.float32)

        # ---- 清掉"孤岛"：只留和眼眶连通的那一块 ----
        # 两个真实症状（放大图看过）：① 闭眼/痛苦档在左外眼角带出一撮重绘的
        #   蓝发（它贴着原画头发那圈暗线，按肤色/线稿分类都拦不住）；
        #   ② 瞪大眼那件四周散着一圈点状碎屑。
        # 两者都是"和眼睛主体不连通的碎块"，几何上就能干净地去掉，
        # 不用再猜颜色。
        alpha = _isolate_eye(alpha, eye_zone, pad=10)

        if want_erase:
            # 瞪大眼还要**按眼眶形状裁一刀**：AI 把眼白画得比本体高一半
            # （实测重绘眼白 114x118 画布像素，本体眼眶 104x87），
            # 直接照抄会在脸颊上糊出一块白色圆角矩形（沙箱实拍 /tmp/f_surprise.png）。
            # 裁剪形状用**本体自己的眼件**（eye_<side>_base 的 alpha = 眼眶墨迹），
            # 膨胀 8px 当作"抬高的上眼线"，形状与本体同源，不用再猜。
            #   ★ 不能用补片框那个椭圆：它是矩形适配，眼白一大就露白。
            base_img = np.array(Image.open(os.path.join(sp, f"eye_{side}_base.png"))
                                .convert("RGBA"))
            bm_canvas = np.zeros((H, W), bool)
            px, py = e["patch_pos"]
            bh, bw = base_img.shape[:2]
            x1c, y1c = min(W, px + bw), min(H, py + bh)
            bm_canvas[py:y1c, px:x1c] = base_img[:y1c - py, :x1c - px, 3] > 40
            bm_canvas = _dilate(bm_canvas, 8)
            aperture = bm_canvas[ay0:ay1, ax0:ax1]
            if aperture.sum() > 200:
                alpha = alpha * aperture.astype(np.float32)

        # 覆盖检查：原画的**整只眼睛**必须被 alpha≥0.9 的部分盖住。
        #   ⚠️ 以前只查"深色像素（lum<165）"。虹膜下半是浅蓝（亮度 200+），
        #   查不到 ⇒ 覆盖率照样报 97.3%，可最终帧里眼睛下缘还留着一牙蓝虹膜
        #   （沙箱实拍 /tmp/rig_closed_left_zoom.png 一眼就看见）。
        #   真值源改成**睁眼件自己的 alpha**（eye_<side>_ball.png）：那是"原画这块是不是眼睛"
        #   的权威定义，不依赖颜色。
        must = np.zeros(tgt.shape[:2], bool)
        try:
            _ball = np.asarray(Image.open(os.path.join(sp, f"eye_{side}_ball.png"))
                               .convert("RGBA"))[..., 3]
            bx0, by0 = e["ball_pos"]
            bh, bw = _ball.shape
            ox, oy = bx0 - ax0, by0 - ay0
            sx0, sy0 = max(0, -ox), max(0, -oy)
            dx0, dy0 = max(0, ox), max(0, oy)
            cw = min(bw - sx0, ww - dx0); chh = min(bh - sy0, hh - dy0)
            if cw > 0 and chh > 0:
                must[dy0:dy0 + chh, dx0:dx0 + cw] |= _ball[sy0:sy0 + chh, sx0:sx0 + cw] > 128
        except (OSError, KeyError):
            pass
        dark = ((tgt.mean(axis=2) < 165) & eye_zone) | must
        dark &= bk_box
        for _ in range(6):
            cover = float((alpha[dark] > 0.9).mean()) if dark.sum() else 1.0
            if cover > 0.995:
                break
            alpha = np.clip(alpha * 1.25, 0, 1) * (pa > 128) * bk_box   # 把不透明区域撑大一点
        cover = float((alpha[dark] > 0.9).mean()) if dark.sum() else 1.0

        img = np.zeros((hh, ww, 4), np.uint8)
        img[..., :3] = patch.round().astype(np.uint8)
        img[..., 3] = (alpha * 255).round().astype(np.uint8)
        fn = f"eye_{side}_{variant}.png"
        Image.fromarray(img, "RGBA").save(os.path.join(sp, fn))

        edge = (alpha > 0.05) & (alpha < 0.95) & both_skin
        seam = float(np.abs(patch - tgt)[edge].mean()) if edge.sum() else 0.0
        out["eyes"].append({
            "side": side, "file": fn, "pos": [ax0, ay0], "size": [ww, hh],
            "gain": [round(v, 4) for v in gain], "offset": [round(v, 2) for v in off],
            "checks": {"cover_ratio": round(cover, 4), "seam_mean_abs": round(seam, 2),
                       "opaque_px": int((alpha > 0.9).sum()),
                       "iris_erased_px": n_iris},
        })
        print(f"{label} {side}: {ww}x{hh} @ 身体({ax0},{ay0})  盖住原画眼睛 {cover*100:.1f}%  "
              f"接缝色差 {seam:.1f}")

    json.dump(out, open(os.path.join(sp, f"eye_{variant}_parts.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    print(f"配准 scale={s:.4f} NCC={ncc:.3f} → sprites/eye_{variant}_parts.json")


if __name__ == "__main__":
    main()
