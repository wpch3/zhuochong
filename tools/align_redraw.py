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
BAND = {"torso": (0.40, 0.80), "head": (0.00, 0.34), "full": (0.0, 1.0)}
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
          color: bool = True, verbose: bool = True):
    B = np.asarray(body.convert("RGBA")).astype(np.float32)
    H, W = B.shape[:2]
    band = BAND.get(region, BAND["torso"])
    Bm = (B[..., 3] > 128).astype(np.float32)
    Bm[: int(H * band[0]), :] = 0
    Bm[int(H * band[1]):, :] = 0
    B_total = float(Bm.sum())
    Bopaque = B[..., 3] > 200

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
                if not (0.60 * sx0 <= nsx <= 1.45 * sx0 and
                        0.60 * sy0 <= nsy <= 1.45 * sy0):
                    continue
                if abs(ndy - dy0) > 60 or abs(ndx - dx0) > 60:
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
    ap.add_argument("--region", default="torso", choices=tuple(BAND))
    ap.add_argument("--no-color", action="store_true", help="不做配色拟合")
    ap.add_argument("--out", default="", help="输出路径（必须另存，不覆盖源图）")
    ap.add_argument("--qa", default="", help="另存一张叠图供肉眼复核")
    a = ap.parse_args()
    if not a.out:
        raise SystemExit("[align] 必须给 --out：源图（洋红底）是唯一真本，不覆盖")
    if os.path.abspath(a.out) == os.path.abspath(a.input):
        raise SystemExit("[align] --out 不能就是 --input")
    sp = os.path.join(a.root, "characters", a.character, "forms", a.form, "sprites")
    body = Image.open(os.path.join(sp, "body_full.png"))
    gen = Image.open(a.input)
    out, info = align(body, gen, a.region, color=not a.no_color)
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
