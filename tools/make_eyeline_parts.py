#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""make_eyeline_parts.py - 眼线二次拆件（G4m）：把脸上烤死的眼睛挖掉换成眼窝皮肤。

问题（用户 5 倍放大看闭眼时提的）：
  眼睛虽然已经拆成四件（眼眶遮罩 / 眼白 / 眼球 / 眼线），但 **`seg_head` 上仍然
  原封不动画着整只眼睛**——眼白、虹膜、整圈眼线都在。零件只是"又画了一遍"盖在上面。
  于是只要眼睛不是全开：
    · 眼眶一收，底下露出来的是脸上那只**睁着的眼睛**，不是眼皮；
    · 上眼线钉死在脸上，眼皮下滑时它不会跟着走，闭眼永远是"眼线圈 + 一块皮肤"。

做法（D19：被遮挡的地方必须有真画出来的内容）：
  1. 皮肤来源 = 已经配准好的 **AI 重绘闭眼脸补片**（`eye_?_closed.png`，
     `make_eye_closed_parts.py` 的产物，覆盖率 99.5%+、接缝色差 ≤4.5）。
     把补片里那条闭眼线（暗像素）**原地抹掉**（颜色外扩填进来），
     剩下的就是一整块干净的眼窝皮肤。
  2. 挖除范围 = 眼眶开口（socket，alpha>128，不外扩，避免吃到软边外面）
     ∪ 上眼线（lash，外扩 1px）。这两块正好是"睁眼时被零件盖住"的区域，
     所以静止画面一个像素都不会变。
  3. `seg_head` 在这个范围内 **只换 RGB、不动 alpha**（脸不能被挖出洞）。
  4. 顺带把眼眶开口的包围盒写进 `eyeline_parts.json`：
     `make_rig.py` 拿它当"瞳孔收缩"的锚点（眼眶按下沿压扁 = 真闭眼）。

用法：
  ~/.imgenv/bin/python tools/make_eyeline_parts.py --character xiaoxun --form teen
"""
from __future__ import annotations
import argparse, json, os, sys

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from make_sidehair_parts import dilate, grow_colors   # noqa: E402

DARK_LUM = 168      # 补片里低于这个亮度的算"闭眼线"，要抹掉
LINE_PAD = 3        # 闭眼线往外扩几像素一起抹（线里嵌着白色高光，不扩就会被它填满）
GROW_IT  = 16       # 抹掉之后往里填几圈颜色


def inpaint_harmonic(chan, hole, max_iter=4000, tol=0.02):
    """边界固定（Dirichlet）的调和内插：解 Laplace 方程填洞。

    `chan` 灰阶通道，`hole` 要填的 bool 掩膜。洞外的像素是**边界条件**，
    逐次超松弛迭代到收敛。因为边界值就是外侧真实像素，填出来的曲面在边界处
    严格连续，不会出现色阶带或锯齿边 —— 这是"梯度域修复"在不需要解
    Poisson 方程时最稳的一种退化形式。
    """
    out = chan.astype(np.float64).copy()
    m = hole.astype(bool)
    if not m.any():
        return out
    pad = np.pad(out, 1, mode="edge")
    known = pad[1:-1, 1:-1]  # 仅为保持维度
    # 初值：用洞外均值，收敛更快
    if (~m).any():
        out[m] = float(out[~m].mean())
    # 四邻域和（洞内像素每次用最新值，Gauss-Seidel + SOR）
    w = 1.75
    h, wd = out.shape
    for _ in range(max_iter):
        prev = out.copy()
        up = np.roll(out, 1, 0)
        dn = np.roll(out, -1, 0)
        lf = np.roll(out, 1, 1)
        rt = np.roll(out, -1, 1)
        avg = (up + dn + lf + rt) / 4.0
        out = np.where(m, out + w * (avg - out), out)
        if np.abs(out - prev)[m].max() < tol:
            break
    return out


def luminance(rgb):
    return (0.299 * rgb[..., 0] + 0.587 * rgb[..., 1] + 0.114 * rgb[..., 2])


def clean_skin(patch):
    """闭眼补片 → 干净的眼窝皮肤（把那条闭眼线和睫毛抹掉）。

    填法是**按列上下插值**，不是四邻域外扩：
      · 闭眼线是一条横带，四邻域外扩只能从带子的左右两头往里爬，
        爬出来是一道灰褐色的糊痕（实测）；
      · 线里还嵌着几粒白色高光，亮度高、不在暗像素里，外扩时反倒以它们为源，
        把整条线填成一排白方块（实测第一版）。
    所以：先把线**整条带状外扩**一起判掉，再对每一列取带子上下两端的皮肤色做线性插值；
    上下有一端够不着（贴着补片边缘）就退回四邻域外扩兜底。
    """
    a = patch.astype(int)
    rgb, al = a[..., :3], a[..., 3]
    line = (al > 24) & (luminance(rgb) < DARK_LUM)
    line = dilate(line, LINE_PAD) & (al > 24)
    out = a.copy()
    h, w = line.shape
    left = np.zeros_like(line)
    for x in range(w):
        col = np.nonzero(line[:, x])[0]
        if col.size == 0:
            continue
        y0, y1 = col.min(), col.max()
        top = y0 - 1
        bot = y1 + 1
        ok_t = top >= 0 and al[top, x] > 160 and not line[top, x]
        ok_b = bot < h and al[bot, x] > 160 and not line[bot, x]
        if ok_t and ok_b:
            c0 = rgb[top, x].astype(float)
            c1 = rgb[bot, x].astype(float)
            n = bot - top
            for y in range(y0, y1 + 1):
                t = (y - top) / float(n)
                out[y, x, :3] = np.round(c0 * (1.0 - t) + c1 * t)
        elif ok_t or ok_b:
            c = rgb[top, x] if ok_t else rgb[bot, x]
            out[y0:y1 + 1, x, :3] = c
        else:
            left[y0:y1 + 1, x] = True
    if left.any():                      # 兜底：上下都够不着的零星列
        out[..., 3] = np.where(left, 0, out[..., 3])
        out = grow_colors(out, left, GROW_IT)
    out[..., 3] = a[..., 3]             # alpha 还原（只换颜色）
    return out, int(line.sum())


def blit_slices(dst_shape, sh, sw, x0, y0):
    """把一张 sh×sw 的小图贴到 dst_shape 上时，双方各自要用的切片。
    （x0/y0 可能是负的：眼眶补丁的左上角就比 seg_head 还靠左 1 像素。）"""
    H, W = dst_shape[:2]
    dy0, dx0 = max(0, y0), max(0, x0)
    dy1, dx1 = min(H, y0 + sh), min(W, x0 + sw)
    if dy0 >= dy1 or dx0 >= dx1:
        return None, None
    sy0, sx0 = dy0 - y0, dx0 - x0
    return ((slice(dy0, dy1), slice(dx0, dx1)),
            (slice(sy0, sy0 + (dy1 - dy0)), slice(sx0, sx0 + (dx1 - dx0))))


def trim_lash_top(lash_rgba):
    """只留上眼线那条弧，剪掉顺着虹膜往下画的两条竖线。

    切眼睛时「眼线」那一片把虹膜左右两道描边也带进来了（见 _lash_sprite.jpg）。
    眼线不动的时候它们正好盖在虹膜边上看不出来；一旦随眨眼往下滑，
    两道竖线就拖到脸颊上，像两行灰眼泪（实测 0.25 那格）。
    做法：逐列从上往下找**第一段连续的墨**（允许 1 像素的抗锯齿断点），留它，下面全扔。
    """
    out = lash_rgba.copy()
    a = out[..., 3]
    h, w = a.shape
    cut = 0
    for x in range(w):
        col = np.nonzero(a[:, x] > 24)[0]
        if col.size == 0:
            continue
        y = int(col[0])
        end = y
        gap = 0
        while y + 1 < h:
            y += 1
            if a[y, x] > 24:
                end = y
                gap = 0
            else:
                gap += 1
                if gap > 1:
                    break
        cut += int((a[end + 1:, x] > 0).sum())
        out[end + 1:, x, 3] = 0
    return out, cut


def measure_lash_travel(ap_m, lash_rgba, abox):
    """上眼线要往下滑多少像素，才正好落在眼眶开口的下沿（= 闭眼那条线的位置）。

    不能拍脑袋写"开口高 × 0.85"：眼线那条弧画在上眼皮**边上**，不是开口最顶端，
    拿开口高当行程会滑过头 —— 实测眼白反而露在眼线上方（见 _eye_states 0.25 那格）。
    这里逐列量「眼眶下沿 − 眼线下沿」，取中间 60% 列的中位数，稳。
    """
    a = lash_rgba.astype(int)
    lum = luminance(a[..., :3])
    dark = (a[..., 3] > 80) & (lum < 140)
    x0, _y0, x1, _y1 = abox
    lo = x0 + int((x1 - x0) * 0.2)
    hi = x1 - int((x1 - x0) * 0.2)
    d = []
    for x in range(lo, max(hi, lo + 1)):
        col = np.nonzero(ap_m[:, x])[0]
        dc = np.nonzero(dark[:, x])[0]
        if col.size and dc.size:
            d.append(int(col.max()) - int(dc.max()))
    if not d:
        return 2.0
    return float(max(2.0, round(float(np.median(d)), 1)))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--character", required=True)
    ap.add_argument("--form", required=True)
    ap.add_argument("--root", default=".")
    args = ap.parse_args()

    base = os.path.join(args.root, "characters", args.character, "forms", args.form)
    sp = os.path.join(base, "sprites")
    bp_path = os.path.join(sp, "body_parts.json")
    eyes_path = os.path.join(sp, "eye_parts.json")
    closed_path = os.path.join(sp, "eye_closed_parts.json")
    for p in (bp_path, eyes_path, closed_path):
        if not os.path.exists(p):
            print(f"缺少 {p}（先跑 rebuild_parts.sh 前面的步骤）")
            return 2
    with open(bp_path, encoding="utf-8") as f:
        bp = json.load(f)
    with open(eyes_path, encoding="utf-8") as f:
        eyes = json.load(f)
    with open(closed_path, encoding="utf-8") as f:
        closed = json.load(f)

    pos_of = {p["id"]: p["pos"] for p in bp["parts"]}
    hx, hy = pos_of["seg_head"]
    head = np.array(Image.open(os.path.join(sp, "seg_head.png")).convert("RGBA")).astype(int)
    H, W = head.shape[:2]

    report = {"source": "eye_?_closed.png（AI 重绘闭眼脸补片，抹掉闭眼线后当眼窝皮肤）",
              "eyes": []}
    for e in eyes["eyes"]:
        side = e["side"]
        cl = next((c for c in closed["eyes"] if c["side"] == side), None)
        if not cl:
            print(f"没有 {side} 眼的闭眼补片，跳过")
            continue
        px, py = e["patch_pos"]                    # 眼眶/眼线补丁在身体坐标里的位置
        sock = np.array(Image.open(os.path.join(sp, e["socket"])).convert("RGBA"))[..., 3]
        lash_rgba = np.array(Image.open(os.path.join(sp, e["lash"])).convert("RGBA"))
        lash = lash_rgba[..., 3]

        # 1) 挖除范围（身体坐标 → seg_head 局部坐标）
        carve = np.zeros((H, W), bool)
        ph, pw = sock.shape
        dreg, sreg = blit_slices(head.shape, ph, pw, px - hx, py - hy)
        if dreg is None:
            print(f"{side} 眼的补丁落在 seg_head 外面，跳过")
            continue
        # 眼眶是软边（2px 斜坡）。卡死 alpha>128 的话，斜坡那一圈原画会留下来，
        # 闭眼时就是一串白点（实测 988 粒）。所以挖除用**软权重**：
        # alpha≥96 全换，24~96 线性过渡 —— 和眼白/眼球被同一张遮罩裁切的权重互补。
        ap_m = (sock > 96)
        wsock = np.clip((sock.astype(float) - 24.0) / 72.0, 0.0, 1.0)
        wmap = np.zeros((H, W), float)
        wmap[dreg] = np.maximum(wmap[dreg], wsock[sreg])
        wmap[dreg] = np.maximum(wmap[dreg], dilate(lash > 40, 1)[sreg].astype(float))
        # Chibi's socket is a deliberately tight sclera aperture. It does not span
        # the full original iris silhouette, so carving only socket+lash leaves the
        # baked dark upper iris on seg_head (which reads as a second black lash).
        # Use the eye-source segmentation's full aperture as a separate face-cleanup
        # mask; it is never attached as a visible rig part or used to clip the pupil.
        if args.form == "chibi" and e.get("carve"):
            cimg = np.array(Image.open(os.path.join(sp, e["carve"])).convert("RGBA"))
            full_eye = dilate(cimg[..., 3] > 24, 1)
            wmap[dreg] = np.maximum(wmap[dreg], full_eye[sreg].astype(float))
        carve = wmap > 0.004

        # 2) 皮肤来源：闭眼补片抹掉闭眼线
        cim = np.array(Image.open(os.path.join(sp, cl["file"])).convert("RGBA"))
        skin, line_px = clean_skin(cim)
        cx, cy = cl["pos"]
        sk = np.zeros((H, W, 4), int)
        chh, cww = skin.shape[:2]
        dreg2, sreg2 = blit_slices(head.shape, chh, cww, cx - hx, cy - hy)
        if dreg2 is not None:
            sk[dreg2] = skin[sreg2]
        have = sk[..., 3] > 160                    # 补片里足够实的地方才敢用

        # 3) 只换 RGB、不动 alpha
        head_before = head.copy()
        use = carve & have & (head[..., 3] > 0)
        wfin = np.where(use, wmap, 0.0)
        for c in range(3):
            head[..., c] = np.round(head[..., c] * (1.0 - wfin) + sk[..., c] * wfin)
        if args.form == "chibi" and use.any():
            # 接缝收口（2026-11-10 新版实拍：额前出现浅色矩形接缝）：闭眼重绘补片的
            # 肤色与 seg_head 原肤有系统偏差，硬权重换皮后在 carve 边界留下矩形边。
            # ①色调匹配：用 carve 外圈原肤 vs 内沿新肤的均值差（钳 ±16）整体校正新肤；
            # ②边缘羽化：把换皮权重做 2 次 3x3 模糊，在 dilate(use,2) 内与原图渐变混合。
            ring = dilate(use, 4) & ~use & (head_before[..., 3] > 0)
            inner = use & ~dilate(~use, 2)
            if ring.any() and inner.any():
                for c in range(3):
                    delta = float(head_before[..., c][ring].mean() - head[..., c][inner].mean())
                    delta = max(-16.0, min(16.0, delta))
                    head[..., c] = np.clip(head[..., c].astype(float) + delta * use, 0, 255).round()
            wf = wfin.astype(np.float32)
            for _ in range(2):
                acc = wf.copy()
                for dy2 in (-1, 0, 1):
                    for dx2 in (-1, 0, 1):
                        if dy2 or dx2:
                            acc += np.roll(np.roll(wf, dy2, 0), dx2, 1)
                wf = acc / 9.0
            region = dilate(use, 2)
            for c in range(3):
                mixed = head_before[..., c] * (1.0 - wf) + head[..., c] * wf
                head[..., c] = np.where(region, np.round(mixed), head[..., c])
        # 补片没盖到的零星角落：拿刚写进去的皮肤往外涂
        rest = carve & ~have & (head[..., 3] > 0)
        if rest.any():
            tmp = head.copy()
            keep_a = tmp[..., 3].copy()
            tmp[..., 3] = np.where(rest, 0, tmp[..., 3])
            # The Chibi eyelash tips sit farther outside the closed-eye redraw than
            # the teen template; an 8px frontier left dark original lash cores alive.
            # The mask is confined to the socket + extracted lash, so grow far enough
            # to fill the *entire* uncovered region rather than keeping baked strokes.
            tmp = grow_colors(tmp, rest, 40)
            tmp[..., 3] = keep_a
            head = tmp

        # 3b) 收口：眼眶开口核心区（sock>96）里**一粒**原画的眼线/虹膜都不许剩。
        # 上面是按"位置"挖（socket 的 alpha 斜坡），这里再按"颜色"兜一道 ——
        # 闭眼补片自己就带着几粒没擦净的睫毛根，grow_colors 还可能把它们摊开；
        # 眼眶一收，这几粒就从眼皮底下浮出来成了"脸上画着一只睁眼"。
        # 判据故意比 check_assets 的闸**更严**（亮度 135 vs 闸的 120、
        # 蓝差 20/100 vs 闸的 25/110），留出余量，不是为了刚好过闸。
        core = np.zeros((H, W), bool)
        core[dreg] = ap_m[sreg]
        core &= head[..., 3] > 0
        _lum = 0.299 * head[..., 0] + 0.587 * head[..., 1] + 0.114 * head[..., 2]
        bad = core & ((_lum < 135)
                      | ((head[..., 2] - head[..., 0] > 20) & (head[..., 2] > 100)))
        if bad.any():
            tmp = head.copy()
            keep_a = tmp[..., 3].copy()
            tmp[..., 3] = np.where(bad, 0, tmp[..., 3])
            tmp = grow_colors(tmp, bad, 10)
            tmp[..., 3] = keep_a
            head = tmp
            print(f"  {side} 眼眶收口：洗掉残留的眼线/虹膜 {int(bad.sum())} 像素")

        # 3c) ★ 2026-11-11 铁律19 改算法：眼眶外圈的和连续填充。
        # 上面 2/3 步是「硬权重换皮 + 邻域生长」，在 carve 边界外圈留下一圈
        # 参差不齐的浅紫/白色锯齿 —— 引擎里就是眼角那几根白色尖刺（用户说的
        # "眼睛两边很乱"）。捕丁这条路已经走过两轮（羽化、色调匹配）都没干净。
        # 新做法：把整个眼眶（含 3px 软边外扩）当作用户掩膜，用**边界固定**的
        # 调和内插（Laplace 方程，逐次超松弛）从该区域**外一圈的真实原肤**
        # 求一个连续曲面填进去。边界值就是外部原肤本身 ⇒ 边界处 Δ≈0，
        # 天然没有台阶、没有锯齿、没有色差带。
        _eye_fill = dilate(carve, 3) & (head[..., 3] > 0)
        if _eye_fill.any():
            _ys, _xs = np.nonzero(_eye_fill)
            _y0, _y1 = int(_ys.min()), int(_ys.max()) + 1
            _x0, _x1 = int(_xs.min()), int(_xs.max()) + 1
            _sub = head[_y0:_y1, _x0:_x1].astype(np.float64)
            _m = _eye_fill[_y0:_y1, _x0:_x1]
            for _c in range(3):
                _sub[..., _c] = inpaint_harmonic(_sub[..., _c], _m)
            head[_y0:_y1, _x0:_x1] = np.clip(np.round(_sub), 0, 255).astype(np.uint8)

        ys, xs = np.nonzero(ap_m)
        abox = [int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1]
        travel = measure_lash_travel(ap_m, lash_rgba, abox)
        # 上眼线单独存一张"只剩上沿"的，给 rig 用；原 lash 留着不动（挖脸还要用它）
        lash_top, cut_px = trim_lash_top(lash_rgba)
        if args.form == "chibi":
            # ★重做路线（铁律 19，2026-11-10）：眼线此前已修两轮（碎岛清理+闭运算
            # 接桥）仍在引擎里留眼角竖条/黑点，用户明令弃补丁重做。新路线=只保留
            # 主弧：对 alpha>24 做 8 连通标记，只留最大连通块，其余卫星块整块
            # 删除（原画上睫毛本就是一条连续弧，卫星块是阈值切割的产物）。
            _m = lash_top[..., 3] > 24
            _lab = np.zeros(_m.shape, np.int32)
            _sizes = [0]
            _dq = []
            for _yy, _xx in np.argwhere(_m):
                if _lab[_yy, _xx]:
                    continue
                _cur = len(_sizes)
                _sizes.append(0)
                _dq = [(_yy, _xx)]
                _lab[_yy, _xx] = _cur
                while _dq:
                    _y, _x = _dq.pop()
                    _sizes[_cur] += 1
                    for _dy in (-1, 0, 1):
                        for _dx in (-1, 0, 1):
                            _ny, _nx = _y + _dy, _x + _dx
                            if 0 <= _ny < _m.shape[0] and 0 <= _nx < _m.shape[1] \
                                    and _m[_ny, _nx] and not _lab[_ny, _nx]:
                                _lab[_ny, _nx] = _cur
                                _dq.append((_ny, _nx))
            if len(_sizes) > 2:
                _big = int(np.argmax(_sizes))
                _drop = (_lab != _big) & _m
                if _drop.any():
                    lash_top[..., 3] = np.where(_drop, 0, lash_top[..., 3])
                    print(f"  {side} 眼线重做：删卫星块 {int(_drop.sum())} 像素，只留主弧 {_sizes[_big]} 像素")
        lash_file = f"eye_{side}_lash_up.png"
        Image.fromarray(lash_top.astype(np.uint8)).save(os.path.join(sp, lash_file))
        report["eyes"].append({
            "side": side,
            "patch_pos": [px, py],
            "aperture_box": abox,                  # 眼眶开口在 patch 里的包围盒
            "socket_size": [int(pw), int(ph)],     # 眼眶图尺寸（make_rig 换算锚点用）
            "lash_travel": travel,                 # 上眼线要下滑多少才落到眼眶下沿
            "lash_file": lash_file,                # 剪掉虹膜描边后的上眼线（rig 用这张）
            "lash_cut_px": cut_px,
            "carved_px": int(use.sum()),
            "filled_px": int(rest.sum()),
            "line_px": line_px,
        })
        print(f"  {side} 眼：换皮肤 {int(use.sum())} 像素（补画外扩 {int(rest.sum())}），"
              f"闭眼线抹掉 {line_px} 像素，眼眶开口 {abox}")

    Image.fromarray(head.astype(np.uint8)).save(os.path.join(sp, "seg_head.png"))
    with open(os.path.join(sp, "eyeline_parts.json"), "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    note = "脸上的眼白/虹膜/上眼线已挖掉换成眼窝皮肤（make_eyeline_parts.py，G4m）"
    if note not in bp.setdefault("patches", []):
        bp["patches"].append(note)
        with open(bp_path, "w", encoding="utf-8") as f:
            json.dump(bp, f, ensure_ascii=False, indent=2)
    print("写出 sprites/eyeline_parts.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
