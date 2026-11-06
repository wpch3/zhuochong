#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""align_redraw.py —— 把一张「AI 重绘底图」配准成本形态 sprites 像素系里的一件素材

为什么必须有这一步
------------------
D19 规定的重绘型零件（无臂躯干、无刘海额头、闭眼脸…）都是**另画一张图**。
AI 出图不保证尺寸、构图、比例：`make_arm_parts.py` 第一件事就是
`fill.shape == body.shape`，尺寸不对直接退出。少女那张 `torso_noarms.png`
是当年手工缩放的（445×1292）；换到 Q 版（头身比 2.14 vs 少女 4.65）完全用不了 ——
同一张重绘贴上去，袖根会长到膝盖。所以要有一条**能重跑**的配准命令。

两段式，各管一件事
------------------
① **剪影 Dice 定尺度 + 平移**（不偏尺度）
   `Dice = 2·|A∩B| / (|A|+|B|)`，A = 重绘的不透明区，B = body_full 躯干带的不透明区。
   交集用 FFT 一次算出所有平移（含分母的窗口能量用积分图）。
   ★ 为什么不直接用边缘互相关：边缘图**归一化方式一换，最优尺度就从 0.47 跳到 0.20 下界**。
     实测把 G 归一化成单位范数、分母取「窗口内 B 的能量」，一个缩到极小的重绘只要
     压在 body 的一条强边上就能拿满分（0.37 > 正解的 0.2x）——这正是 §5.7 记的
     「不归一化会单调偏向小尺度」。Dice 里 |A| 跟着尺度一起长，退化解被自然罚掉。
② **逐像素色差细化四个参数**
   衣服是同一件，领口/兜帽/门襟/扣子/下摆条/裙褶两边都画了。尺度定下来以后，
   色差（截尾均值，只取最好的 55%）比剪影更锐：剪影差 1px 看不出来，色差会立刻跳。
   截尾是必须的 —— 重绘把袖子去掉了，那一片**本来就该不一样**，
   拿全量均值会被它拖偏（"一个标量约束两个自由度"那类错）。
③ 最后做逐通道 gain/offset 配色拟合（只在两边都不透明的带内，截尾去外点），
   免得同一个角色在两件素材上是两个色温。

输出：与 `sprites/body_full.png` **同尺寸**的 RGBA PNG（洋红抠成 alpha，画布外透明），
旁边落 `<out>.align.json` 记录参数 —— 换形态时一眼看出这条参数是不是漂了。

用法：
  python3 tools/align_redraw.py --character xiaoxun --form chibi \\
      --input characters/xiaoxun/forms/chibi/design/redraw/torso_noarms.png \\
      --region torso --out /tmp/torso_aligned.png
"""
from __future__ import annotations

import argparse
import json
import os

import numpy as np
from PIL import Image

SEEDS = 6          # 多起点个数（单起点会卡在斜谷里，见 ② 的注释）
# 不带 anchors.json 时的兜底条带（按身高比例）
BAND = {"torso": (0.40, 0.80), "head": (0.00, 0.34), "full": (0.0, 1.0)}


def band_from_anchors(sp: str, region: str, H: int):
    """从 design/anchors.json 取真实条带（头 = 头顶..脖根，躯干 = 脖根..胯）。

    ★ 写死 0.34H 当"头"是错的：Q 版头占身高 46.8%，写死 0.34 等于告诉配准器
      "把脑袋压进上半截里"，实测直接把 sy 压到 0.31（叠图里脸比身体小一圈、
      整张脸上浮）。条带必须跟着这个形态自己的比例走。
    """
    design = os.path.join(os.path.dirname(sp.rstrip(os.sep)), "design")   # forms/<形态>/design
    p = os.path.join(design, "anchors.json")
    if not os.path.exists(p):
        return None
    try:
        d = json.load(open(p, encoding="utf-8"))
        pts = d["points"]
        hp = float(d.get("meta", {}).get("height_px") or H)
        neck = float(pts["neck"][1]) / hp
    except (OSError, ValueError, KeyError, TypeError):
        return None
    if region == "head":
        return (0.0, neck)
    if region == "torso":
        hip = float(pts["hip"][1]) / hp
        return (neck, hip)
    return None
EPS = 1e-6


# ─────────────────────────────── 抠像 ───────────────────────────────
def key_alpha(rgb: np.ndarray) -> np.ndarray:
    """洋红键出：品红 = 红蓝高、绿低。软 matte，保住抗锯齿边。"""
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    keyness = np.minimum(r, b) - g
    return np.clip(1.0 - (keyness - 12.0) / 90.0, 0.0, 1.0)


def _premul_resize(rgba: Image.Image, size) -> np.ndarray:
    """带预乘的重采样 —— 直接 resize RGBA 会把透明区的洋红渗进边缘。"""
    a = np.asarray(rgba, dtype=np.float32)
    al = a[..., 3:4] / 255.0
    pm = np.dstack([a[..., :3] * al, a[..., 3:4]])
    im = Image.fromarray(np.clip(pm, 0, 255).astype(np.uint8), "RGBA")
    b = np.asarray(im.resize(size, Image.LANCZOS), dtype=np.float32)
    al2 = np.clip(b[..., 3:4] / 255.0, 1e-6, 1.0)
    return np.dstack([np.clip(b[..., :3] / al2, 0, 255), b[..., 3:4]])


def _place(box: np.ndarray, canvas_wh, dy: int, dx: int) -> np.ndarray:
    """把已缩放到目标尺度的 RGBA 数组按 (dy,dx) 放到透明画布上。

    ★ 允许 (dy,dx) 为负、允许越过右/下边界：AI 出图四周留白不同，
      重绘的**画布**比它的**人物**宽得多。要求整块落在画布内会让"人物对齐"
      的解被判成越界（实测正是这样把唯一正确的那组参数试掉的）。
      越界部分直接裁掉 —— 裁掉的只会是留白。
    """
    W, H = canvas_wh
    dy, dx = int(round(dy)), int(round(dx))
    out = np.zeros((H, W, 4), np.float32)
    gh, gw = box.shape[:2]
    y0, y1 = max(0, dy), min(H, dy + gh)
    x0, x1 = max(0, dx), min(W, dx + gw)
    if y1 <= y0 or x1 <= x0:
        return out                     # 整块在画布外：当作"什么都没贴上"
    sy0, sx0 = y0 - dy, x0 - dx
    out[y0:y1, x0:x1] = box[sy0:sy0 + (y1 - y0), sx0:sx0 + (x1 - x0)]
    return out


# ───────────────────────── ① 剪影 Dice 定尺度 ─────────────────────────
def _dice_search(Bm: np.ndarray, A: np.ndarray, B_total: float | None = None):
    """返回 (dice, dy, dx)：画布坐标 = 重绘坐标 + (dy,dx)。

    ★ 分母里的 |B| 必须用**整条带的面积**（常数），不能用"窗口内的面积"。
      用窗口面积时，把重绘压成一条竖线也能拿 0.96：A 很小、B 窗口也很小，
      Dice 看着漂亮，其实什么都没对上（实测 sy 直接被压到 0）。
      改成常数分母 = 拿"重绘盖住了带里多少躯干"当分子，压扁立刻掉分。
    """
    h, w = Bm.shape
    gh, gw = A.shape
    if gh >= h or gw >= w:
        return -1.0, 0, 0
    H = 1 << int(np.ceil(np.log2(h + gh)))
    W = 1 << int(np.ceil(np.log2(w + gw)))
    c = np.fft.irfft2(np.fft.rfft2(Bm, (H, W)) * np.conj(np.fft.rfft2(A, (H, W))), (H, W))
    c = c[: h - gh + 1, : w - gw + 1]
    ii = np.zeros((h + 1, w + 1), np.float64)
    ii[1:, 1:] = np.cumsum(np.cumsum(Bm.astype(np.float64), 0), 1)
    ys = np.arange(c.shape[0])[:, None]
    xs = np.arange(c.shape[1])[None, :]
    win = ii[ys + gh, xs + gw] - ii[ys, xs + gw] - ii[ys + gh, xs] + ii[ys, xs]
    tot = float(Bm.sum()) if B_total is None else B_total
    dice = 2.0 * c / (A.sum() + tot + EPS)
    k = int(np.argmax(dice))
    dy, dx = np.unravel_index(k, dice.shape)
    return float(dice[dy, dx]), int(dy), int(dx)


def _color_cost(Brgb: np.ndarray, Bopaque: np.ndarray, warped: np.ndarray,
                band, keep=0.55):
    """躯干带内逐像素色差的截尾均值（小 = 像）。不重叠的地方不参与。"""
    H, W = Bopaque.shape
    m = (warped[..., 3] > 200) & Bopaque
    m[: int(H * band[0])] = False
    m[int(H * band[1]):] = False
    if m.sum() < 500:
        return 1e9
    d = np.abs(warped[..., :3][m] - Brgb[..., :3][m]).sum(axis=1)
    k = max(1, int(d.size * keep))
    return float(np.partition(d, k - 1)[:k].mean())


def _feature_mask(sp: str, W: int, H: int, pad: int = 22) -> np.ndarray | None:
    """把"本来就该不一样"的地方挖掉：两眼补片框 + 嘴线框（坐标来自 sprites 里的 json）。

    为什么必须有：同一个角色的五张重绘脸（闭眼/笑眼/痛苦/瞪大/张嘴）**只有眼睛和嘴不同**，
    剩下（头发、脸型、肤色）应当逐像素接近。不挖掉就会拿"眼睛不一样"去惩罚正确的配准 ——
    实测四张脸解出来的平移从 (-24,75) 漂到 (30,126)，尺度从 0.47 漂到 0.54，
    全是目标函数在追错误的东西。
    """
    m = np.zeros((H, W), bool)
    got = False
    try:
        eyes = json.load(open(os.path.join(sp, "eye_parts.json"), encoding="utf-8"))["eyes"]
        for e in eyes:
            x, y = e["patch_pos"]; w, h = e["patch_size"]
            m[max(0, y - pad):min(H, y + h + pad), max(0, x - pad):min(W, x + w + pad)] = True
            got = True
    except (OSError, ValueError, KeyError):
        pass
    try:
        line = json.load(open(os.path.join(sp, "mouth_parts.json"), encoding="utf-8"))["line"]
        x0, x1 = int(line["x0"]) - pad, int(line["x1"]) + pad
        y0, y1 = int(line["y0"]) - pad, int(line["y1"]) + 2 * pad
        m[max(0, y0):min(H, y1 + 30), max(0, x0):min(W, x1)] = True
        got = True
    except (OSError, ValueError, KeyError):
        pass
    return m if got else None


# ───────────────── ②'. 差分脸的**特征点**配准（region=face）─────────────────
# 为什么脸不能走剪影 Dice：脸这一带的剪影是"一大团头发 + 肩膀"，几乎是平顶平台，
# 五张同角色差分脸能解出彼此差 60px 的平移（实测 closed ty=30 / 其余 89~109），
# 而且 Dice 只差 0.003 就能换一个答案 —— 目标函数不在看"眼睛在哪"。
# 差分脸之间**唯一可靠、可复现的锚**是眼睛：
#   · 睁眼图（瞪大 / 张嘴）：眼白是一大块近白 + 中间一圈饱和蓝虹膜，检测极稳；
#   · 闭眼图（闭眼 / 笑眼 / 痛苦）：两撇睫毛是唯一"暗且偏暖"的粗笔画。
# 拿到两只眼的中心，两点相似变换（尺度 + 平移）就是**精确解**，没有搜索、没有多起点。


def _cc_blobs(mask: np.ndarray, minpx: int = 200, limit: int = 8):
    """4 邻域连通块，按面积降序返回 dict(n, cx, cy, x0, x1, y0, y1)。"""
    from collections import deque
    h, w = mask.shape
    seen = np.zeros((h, w), bool)
    out = []
    for y0, x0 in np.argwhere(mask):
        if seen[y0, x0]:
            continue
        q = deque([(y0, x0)])
        seen[y0, x0] = True
        ys, xs = [], []
        while q:
            cy, cx = q.popleft()
            ys.append(cy)
            xs.append(cx)
            for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                ny, nx = cy + dy, cx + dx
                if 0 <= ny < h and 0 <= nx < w and mask[ny, nx] and not seen[ny, nx]:
                    seen[ny, nx] = True
                    q.append((ny, nx))
        if len(ys) >= minpx:
            ys = np.asarray(ys)
            xs = np.asarray(xs)
            out.append(dict(n=len(ys), cx=float(xs.mean()), cy=float(ys.mean()),
                            x0=int(xs.min()), x1=int(xs.max()),
                            y0=int(ys.min()), y1=int(ys.max())))
    out.sort(key=lambda d: -d["n"])
    return out[:limit]


def _merge_row_blobs(bl, max_dy: float, max_gap: float):
    """把**同一撇眼睛**被发丝/高光打断的碎块并回去。

    实测 `face_eyesclosed` 的右眼睫毛被一缕头发横断成两截（56px + 59px），
    不并回来的话"成对挑"会挑到同一只眼的两截（间距 121px < 真间距 298px），
    尺度直接算成 1.52 —— 解出来整张脸被放大 3 倍。
    """
    items = [dict(d) for d in bl]
    merged = True
    while merged and len(items) > 1:
        merged = False
        for i in range(len(items)):
            for j in range(i + 1, len(items)):
                a, b = items[i], items[j]
                if abs(a["cy"] - b["cy"]) > max_dy:
                    continue
                gap = max(a["x0"], b["x0"]) - min(a["x1"], b["x1"])
                if gap > max_gap:
                    continue
                n = a["n"] + b["n"]
                out = dict(n=n,
                           cx=(a["cx"] * a["n"] + b["cx"] * b["n"]) / n,
                           cy=(a["cy"] * a["n"] + b["cy"] * b["n"]) / n,
                           x0=min(a["x0"], b["x0"]), x1=max(a["x1"], b["x1"]),
                           y0=min(a["y0"], b["y0"]), y1=max(a["y1"], b["y1"]))
                items[i] = out
                items.pop(j)
                merged = True
                break
            if merged:
                break
    items.sort(key=lambda d: -d["n"])
    return items


def _pick_pair(bl, min_dx: float, max_dy_ratio: float = 0.30,
               max_area_ratio: float = 3.0, min_aspect: float = 0.0):
    """从候选块里挑"一对眼睛"：左右分开、基本同一水平线、大小相近。"""
    best = None
    for i in range(len(bl)):
        for j in range(i + 1, len(bl)):
            a, b = bl[i], bl[j]
            dx = abs(a["cx"] - b["cx"])
            dy = abs(a["cy"] - b["cy"])
            if dx < min_dx or dy > max_dy_ratio * dx:
                continue
            if max(a["n"], b["n"]) > max_area_ratio * min(a["n"], b["n"]):
                continue
            if min_aspect > 0:
                for q in (a, b):
                    wq = max(1, q["x1"] - q["x0"])
                    hq = max(1, q["y1"] - q["y0"])
                    if wq / hq < min_aspect:
                        break
                else:
                    pass
                if any((q["x1"] - q["x0"]) / max(1, q["y1"] - q["y0"]) < min_aspect
                       for q in (a, b)):
                    continue
            if best is None or a["n"] + b["n"] > best[0]:
                best = (a["n"] + b["n"], a, b)
    if best is None:
        return None
    a, b = best[1], best[2]
    return sorted([a, b], key=lambda d: d["cx"])


def face_pair(rgb: np.ndarray, alpha: np.ndarray, verbose: bool = True):
    """在差分脸里找两只眼的中心。返回 (mode, [(x,y),(x,y)], 诊断字符串)。

    睁眼优先用"虹膜中心"（和 sprites/eye_parts.json 的 iris_center 同一个量），
    闭眼退回"睫毛质心"（同一只眼的同一高度，误差几个像素，下游还有逐眼锚定）。
    """
    h, w = alpha.shape
    op = alpha > 0.70
    ys, xs = np.nonzero(op)
    if ys.size == 0:
        raise SystemExit("[align] 差分脸是空的（洋红键出后没有内容）")
    ytop, ybot = int(ys.min()), int(ys.max())
    ch = ybot - ytop
    band = np.arange(h)[:, None] < ytop + ch * 0.62
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    lum = (r + g + b) / 3.0

    # ① 眼白：近白、大块（这只角色眼白 #FDF8F6，头发最亮处也带蓝紫，b−r 会把它们分开）
    sclera = op & band & (r > 230) & (g > 224) & (b > 226) & (r - b > -8) & (r - b < 14)
    bl = _merge_row_blobs(_cc_blobs(sclera, max(800, int(0.0006 * op.sum())), 8),
                          max_dy=ch * 0.06, max_gap=w * 0.05)
    pair = _pick_pair(bl, min_dx=w * 0.15, max_dy_ratio=0.35, max_area_ratio=3.0)
    if pair is not None:
        # 虹膜必须**先按严格的颜色找块、再配给眼白**，不能"在眼白框里取所有偏蓝像素的质心"：
        # 这只角色瞪大眼时眼白上半有一层偏蓝灰的渐变（lum>200），
        # 质心法会把锚点拉到眼白上方 ~40px、虹膜一点没盖住（实测挖完还剩一整圈蓝边）。
        iris_m = op & (b - r > 35) & (lum > 40) & (lum < 190)
        ibl = _cc_blobs(iris_m, max(300, int(0.0002 * op.sum())), 12)
        pts = []
        for q in pair:
            best_ib, best_d = None, None
            for ib in ibl:
                if not (q["x0"] - 8 <= ib["cx"] <= q["x1"] + 8 and
                        q["y0"] - 8 <= ib["cy"] <= q["y1"] + 8):
                    continue
                dd = (ib["cx"] - q["cx"]) ** 2 + (ib["cy"] - q["cy"]) ** 2
                if best_d is None or dd < best_d:
                    best_ib, best_d = ib, dd
            if best_ib is not None and best_ib["n"] > 300:
                pts.append((best_ib["cx"], best_ib["cy"]))
            else:
                pts.append((q["cx"], q["cy"]))
        return "iris", pts, f"眼白 {len(bl)} 块，虹膜 {len(ibl)} 块"

    # ② 闭眼：睫毛是"暗且偏暖"的粗笔画（头发暗部偏蓝，r−b 为负，天然被排除）
    lash = op & band & (lum < 120) & (r - b > 4)
    bl2 = _merge_row_blobs(_cc_blobs(lash, max(120, int(0.00003 * op.sum())), 10),
                           max_dy=ch * 0.05, max_gap=w * 0.06)
    pair2 = _pick_pair(bl2, min_dx=w * 0.15, max_dy_ratio=0.30,
                       max_area_ratio=2.5, min_aspect=1.3)
    if pair2 is None:
        raise SystemExit("[align] 找不到成对的睫毛/眼白，无法按特征配准。候选：\n  "
                         + "\n  ".join(f"{d['n']}px @ ({d['cx']:.0f},{d['cy']:.0f}) "
                                        f"{d['x1']-d['x0']}x{d['y1']-d['y0']}" for d in bl2))
    return "lash", [(q["cx"], q["cy"]) for q in pair2], f"睫毛 {len(bl2)} 块"


def _align_face(B, gen_rgba, sp, W, H, color=True, verbose=True, exclude=None):
    """region=face：两点相似变换 + 脸部色差细调。"""
    G = np.asarray(gen_rgba, dtype=np.uint8)
    rgb = G[..., :3].astype(np.float32)
    mode, gpts, diag = face_pair(rgb, G[..., 3].astype(np.float32) / 255.0, verbose)

    eyes = json.load(open(os.path.join(sp, "eye_parts.json"), encoding="utf-8"))["eyes"]
    bpts = sorted([(float(e["patch_pos"][0] + e["iris_center"][0]),
                    float(e["patch_pos"][1] + e["iris_center"][1])) for e in eyes])
    if len(bpts) != 2 or len(gpts) != 2:
        raise SystemExit("[align] 需要恰好两只眼")
    bd = float(np.hypot(bpts[1][0] - bpts[0][0], bpts[1][1] - bpts[0][1]))
    gd = float(np.hypot(gpts[1][0] - gpts[0][0], gpts[1][1] - gpts[0][1]))
    if gd < 8:
        raise SystemExit("[align] 检测到的两眼间距太小，判据失效")
    s = bd / gd
    tx = 0.5 * (bpts[0][0] + bpts[1][0]) - s * 0.5 * (gpts[0][0] + gpts[1][0])
    ty = 0.5 * (bpts[0][1] + bpts[1][1]) - s * 0.5 * (gpts[0][1] + gpts[1][1])
    if verbose:
        print(f"[align] ① 特征点（{mode}）重绘 {[(round(x),round(y)) for x,y in gpts]} "
              f"→ 画布 {[(round(x),round(y)) for x,y in bpts]}；"
              f"尺度 {s:.4f} 平移 ({tx:.1f},{ty:.1f})  〔{diag}〕")

    band = (0.22, 0.50)
    Bopaque = (B[..., 3] > 200)
    if exclude is not None:
        Bopaque = Bopaque & ~exclude

    def warp_at(sv, txv, tyv):
        ts = (max(8, int(round(gen_rgba.size[0] * sv))),
              max(8, int(round(gen_rgba.size[1] * sv))))
        return _place(_premul_resize(gen_rgba, ts), (W, H), tyv, txv)

    warped = warp_at(s, tx, ty)
    cost0 = _color_cost(B, Bopaque, warped, band, keep=0.6)
    # 细调：只在 ±4% / ±10px 内走（特征解已经精确，细调只为了吃掉 AI 出图的轻微走样）
    best = (cost0, s, tx, ty)
    step_s, step_t = 0.01, 3.0
    for _ in range(10):
        moved = False
        for d in ((step_s, 0, 0), (-step_s, 0, 0), (0, step_t, 0), (0, -step_t, 0),
                  (0, 0, step_t), (0, 0, -step_t)):
            ns, ntx, nty = best[1] + d[0], best[2] + d[1], best[3] + d[2]
            if not (0.96 * s <= ns <= 1.04 * s):
                continue
            if abs(ntx - tx) > 10 or abs(nty - ty) > 10:
                continue
            c = _color_cost(B, Bopaque, warp_at(ns, ntx, nty), band, keep=0.6)
            if c < best[0] - 1e-6:
                best = (c, ns, ntx, nty)
                moved = True
                break
        if not moved:
            step_s *= 0.5
            step_t *= 0.5
            if step_s < 0.002:
                break
    cost1, s, tx, ty = best
    if verbose:
        print(f"[align] ② 脸部色差细调 {cost0:.2f} → {cost1:.2f}")
    warped = warp_at(s, tx, ty)
    gains, offs = (np.ones(3), np.zeros(3))
    if color:
        gains, offs = _fit_color(B, warped, band)
        m = warped[..., 3] > 0
        warped[..., :3][m] = np.clip(warped[..., :3][m] * gains + offs, 0, 255)
    info = {"scale": [round(s, 4), round(s, 4)], "translate": [round(tx, 2), round(ty, 2)],
            "region": "face", "feature": mode, "gen_pair": [[round(x, 1), round(y, 1)] for x, y in gpts],
            "body_pair": [[round(x, 1), round(y, 1)] for x, y in bpts],
            "face_cost": round(cost1, 2), "size": [W, H],
            "gen_size": list(gen_rgba.size),
            "gain": [round(float(v), 3) for v in gains],
            "offset": [round(float(v), 1) for v in offs]}
    return np.clip(warped, 0, 255).astype(np.uint8), info


def _fit_color(body: np.ndarray, warped: np.ndarray, band, keep=0.6):
    """逐通道最小二乘 gain/offset（两边都不透明的带内，截尾去外点）。"""
    H = body.shape[0]
    m = (body[..., 3] > 200) & (warped[..., 3] > 200)
    m[: int(H * band[0])] = False
    m[int(H * band[1]):] = False
    if m.sum() < 2000:
        return np.ones(3), np.zeros(3)
    gains, offs = [], []
    for ch in range(3):
        b = body[..., ch][m].astype(np.float64)
        g = warped[..., ch][m].astype(np.float64)
        k = max(200, int(b.size * keep))
        idx = np.argsort(np.abs(b - g))[:k]
        A = np.stack([g[idx], np.ones_like(g[idx])], 1)
        sol, *_ = np.linalg.lstsq(A, b[idx], rcond=None)
        gains.append(float(np.clip(sol[0], 0.85, 1.15)))
        offs.append(float(np.clip(sol[1], -25, 25)))
    return np.array(gains), np.array(offs)


def align(body: Image.Image, gen: Image.Image, region: str = "torso",
          color: bool = True, verbose: bool = True, exclude=None, sp: str = ""):
    B = np.asarray(body.convert("RGBA")).astype(np.float32)
    H, W = B.shape[:2]
    band = band_from_anchors(sp, region, H) or BAND.get(region, BAND["torso"])
    Bm = (B[..., 3] > 128).astype(np.float32)
    Bm[: int(H * band[0]), :] = 0
    Bm[int(H * band[1]):, :] = 0
    B_total = float(Bm.sum())
    Bopaque = B[..., 3] > 200
    if exclude is not None:
        Bopaque = Bopaque & ~exclude

    if region == "face":
        G0 = np.asarray(gen.convert("RGB"), dtype=np.float32)
        ga0 = key_alpha(G0)
        if float((ga0 < 0.5).mean()) < 0.15:
            raise SystemExit(f"[align] 输入看起来不是洋红底（透明区只占 "
                             f"{float((ga0 < 0.5).mean()):.1%}）—— 拒绝在它上面继续算")
        rgba0 = Image.fromarray(
            np.dstack([G0, (ga0 * 255).astype(np.uint8)]).astype(np.uint8), "RGBA")
        return _align_face(B, rgba0, sp, W, H, color=color, verbose=verbose,
                           exclude=exclude)

    G = np.asarray(gen.convert("RGB"), dtype=np.float32)
    ga = key_alpha(G)
    # ★ 先确认这张图**真的是洋红底**。第一版把 --out 默认成覆盖 --input，
    #   跑一次失败之后再跑就作用在自己写出来的结果上，背景早被抠没了
    #   ⇒ 目标函数从 12 涨到 340，却看不出是自己毁的。
    if float((ga < 0.5).mean()) < 0.15:
        raise SystemExit(f"[align] 输入看起来不是洋红底（透明区只占 "
                         f"{float((ga < 0.5).mean()):.1%}）—— 拒绝在它上面继续算")
    gen_rgba = Image.fromarray(
        np.dstack([G, (ga * 255).astype(np.uint8)]).astype(np.uint8), "RGBA")
    gw0, gh0 = gen_rgba.size

    # ── ① 剪影 Dice 在 1/4 分辨率上粗扫，留前 K 个当起点 ────────────
    # ★ 只留一个最优起点会掉坑：色差目标在 (sy, dy) 上是**斜谷**，
    #   从 Dice 最优点出发的坐标下降会卡在 18.17，而真解是 8.51
    #   （真解要同时把 sy 收小、把整体上移，单轴一步走不过去）。
    down = 4
    Wd, Hd = max(1, W // down), max(1, H // down)
    Bm_d = np.asarray(Image.fromarray((Bm * 255).astype(np.uint8))
                      .resize((Wd, Hd), Image.BILINEAR), dtype=np.float32) / 255.0
    B_total_d = float(Bm_d.sum())

    cands = []
    for sx in np.linspace(0.18, 1.10, 24):
        for sy in np.linspace(0.18, 1.10, 24):
            ts = (max(4, int(round(gw0 * sx / down))),
                  max(4, int(round(gh0 * sy / down))))
            A = (_premul_resize(gen_rgba, ts)[..., 3] > 128).astype(np.float32)
            d, dy, dx = _dice_search(Bm_d, A, B_total_d)
            cands.append((d, sx, sy, dx * down, dy * down))
    if not cands:
        raise SystemExit("[align] 粗扫无解")
    cands.sort(key=lambda c: -c[0])
    if verbose:
        c = cands[0]
        print(f"[align] ① 剪影 Dice {c[0]:.4f} @ 尺度 ({c[1]:.2f},{c[2]:.2f}) "
              f"平移 ({c[3]},{c[4]})  —— 前 {SEEDS} 个都拿去细化")

    def dice_at(sxv, syv):
        ts = (max(4, int(round(gw0 * sxv))), max(4, int(round(gh0 * syv))))
        A = (_premul_resize(gen_rgba, ts)[..., 3] > 128).astype(np.float32)
        return _dice_search(Bm, A, B_total)

    def cost(sxv, syv, dxv, dyv):
        ts = (max(4, int(round(gw0 * sxv))), max(4, int(round(gh0 * syv))))
        box = _premul_resize(gen_rgba, ts)
        return _color_cost(B, Bopaque, _place(box, (W, H), dyv, dxv), band)

    # 去重：尺度相差 <3% 的起点是同一个坑，不重复算
    seeds, seen = [], []
    for c in cands:
        if all(abs(np.log(c[1] / q[0])) + abs(np.log(c[2] / q[1])) > 0.10 for q in seen):
            seeds.append(c)
            seen.append((c[1], c[2]))
        if len(seeds) >= SEEDS:
            break

    best = None
    for dice0, sx, sy, dx, dy in seeds:
        # 尺度按 Dice 细化（剪影口径，和色差口径互补）
        dcur = dice0
        st = 0.03
        for _ in range(9):
            moved = False
            for cand in ((sx + st, sy), (sx - st, sy), (sx, sy + st), (sx, sy - st)):
                d = dice_at(*cand)[0]
                if d > dcur + 1e-5:
                    dcur, (sx, sy) = d, cand
                    moved = True
                    break
            if not moved:
                st *= 0.5
                if st < 0.004:
                    break
        _, dy, dx = dice_at(sx, sy)

        # 色差细化：单轴 + **斜向**（sy-dy、sx-dx 成对走），否则斜谷走不出去
        sx0, sy0, dy0, dx0 = sx, sy, dy, dx
        ccur = cost(sx, sy, dx, dy)
        step_s, step_t = 0.02, 6.0
        for _ in range(14):
            moved = False
            moves = [(step_s, 0, 0, 0), (-step_s, 0, 0, 0), (0, step_s, 0, 0),
                     (0, -step_s, 0, 0), (0, 0, step_t, 0), (0, 0, -step_t, 0),
                     (0, 0, 0, step_t), (0, 0, 0, -step_t),
                     (0, step_s, 0, -step_t), (0, -step_s, 0, step_t),
                     (0, step_s, 0, step_t), (0, -step_s, 0, -step_t),
                     (step_s, 0, -step_t, 0), (-step_s, 0, step_t, 0)]
            for d in moves:
                nsx, nsy = sx + d[0], sy + d[1]
                ndx, ndy = dx + d[2], dy + d[3]
                # 护栏收紧到 ±8% 尺度 / ±24px 平移。
                # ⚠️ 原来给到 ±45% / ±60px，实测同一张图两次跑能解出 sy 0.31 和 0.46
                #   两个答案（色差目标在"平涂皮肤 + 平涂头发"上几乎是平台，梯度很弱，
                #   大范围内它能一路滑）。尺度交给剪影 Dice 定，色差只做"细调"。
                if not (0.92 * sx0 <= nsx <= 1.08 * sx0 and
                        0.92 * sy0 <= nsy <= 1.08 * sy0):
                    continue
                if abs(ndy - dy0) > 24 or abs(ndx - dx0) > 24:
                    continue
                c = cost(nsx, nsy, ndx, ndy)
                if c < ccur - 1e-6:
                    ccur, (sx, sy, dx, dy) = c, (nsx, nsy, ndx, ndy)
                    moved = True
                    break
            if not moved:
                step_s *= 0.5
                step_t *= 0.5
                if step_s < 0.002 and step_t < 0.5:
                    break
        if best is None or ccur < best[0]:
            best = (ccur, sx, sy, dx, dy, dcur)
    best_cost, sx, sy, dx, dy, cur = best
    if verbose:
        print(f"[align] ② 色差细化 → 尺度 ({sx:.4f},{sy:.4f}) 平移 ({dx},{dy}) "
              f"截尾均差 {best_cost:.2f}（Dice {cur:.4f}）")

    ts = (max(4, int(round(gw0 * sx))), max(4, int(round(gh0 * sy))))
    warped = _place(_premul_resize(gen_rgba, ts), (W, H), dy, dx)
    gains, offs = (np.ones(3), np.zeros(3))
    if color:
        gains, offs = _fit_color(B, warped, band)
        m = warped[..., 3] > 0
        warped[..., :3][m] = np.clip(warped[..., :3][m] * gains + offs, 0, 255)
        if verbose:
            print(f"[align]   配色 gain {np.round(gains, 3).tolist()} "
                  f"offset {np.round(offs, 1).tolist()}")

    info = {"scale": [round(sx, 4), round(sy, 4)], "translate": [int(dx), int(dy)],
            "dice": round(cur, 4), "color_cost": round(best_cost, 2),
            "region": region, "size": [W, H], "gen_size": [gw0, gh0],
            "placed": [int(ts[0]), int(ts[1])],
            "gain": [round(float(v), 3) for v in gains],
            "offset": [round(float(v), 1) for v in offs]}
    return np.clip(warped, 0, 255).astype(np.uint8), info


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--character", required=True)
    ap.add_argument("--form", required=True)
    ap.add_argument("--input", required=True, help="待配准的重绘底图（洋红底）")
    ap.add_argument("--root", default=".")
    ap.add_argument("--region", default="torso", choices=tuple(BAND) + ("face",))
    ap.add_argument("--no-color", action="store_true", help="不做配色拟合")
    ap.add_argument("--out", default="", help="输出路径（必须另存，不覆盖源图）")
    ap.add_argument("--qa", default="", help="另存一张叠图供肉眼复核")
    ap.add_argument("--exclude-features", action="store_true",
                    help="按 sprites 的 eye_parts/mouth_parts 框挖掉眼嘴（同一角色的多张差分脸专用）")
    a = ap.parse_args()
    if not a.out:
        raise SystemExit("[align] 必须给 --out：源图（洋红底）是唯一真本，不覆盖")
    if os.path.abspath(a.out) == os.path.abspath(a.input):
        raise SystemExit("[align] --out 不能就是 --input")
    sp = os.path.join(a.root, "characters", a.character, "forms", a.form, "sprites")
    body = Image.open(os.path.join(sp, "body_full.png"))
    gen = Image.open(a.input)
    exc = None
    if a.exclude_features:
        exc = _feature_mask(sp, body.size[0], body.size[1])
        if exc is None:
            raise SystemExit("[align] 要求挖掉眼嘴，但 sprites 里没有 eye_parts/mouth_parts")
    out, info = align(body, gen, a.region, color=not a.no_color, exclude=exc, sp=sp)
    info["exclude_features"] = bool(a.exclude_features)
    Image.fromarray(out, "RGBA").save(a.out)
    with open(a.out + ".align.json", "w", encoding="utf-8") as f:
        json.dump(info, f, ensure_ascii=False, indent=2)
    if a.qa:
        bb = np.asarray(body.convert("RGBA")).astype(np.float32).copy()
        m = out[..., 3] > 128
        bb[..., :3][m] = out[..., :3][m]
        bg = Image.new("RGB", body.size, (236, 241, 246))
        im = Image.fromarray(bb.astype(np.uint8), "RGBA")
        bg.paste(im, (0, 0), im)
        bg.save(a.qa)
    print(f"[align] 写出 {a.out}（{info['size'][0]}x{info['size'][1]}，与 body_full 同尺寸）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
