#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""眼眶区域调和填充（重建链的最后一步）。

为什么要单独一个工具（铁律 19，2026-11-11）
--------------------------------------------
用户看真实引擎帧指出「眼睛两边很乱也很糊」。放大后眼角外侧有几根
**白色尖刺** + 参差不齐的浅紫锯齿。根因不在眼件本身，而在 `seg_head`
上眼眶那一圈：挖眼时是「硬权重换皮 + 邻域生长」，carve 边界外圈必然
留下参差的色阶台阶。前两轮补丁（色调匹配 / 羽化）都只能压淡，压不掉。

按铁律 19 换算法：把整个眼眶（含软边外扩）当作洞，用**边界固定**的
调和内插（Dirichlet Laplace，逐次超松弛）从洞**外一圈真实原肤**求一个
连续曲面填进去。边界值就是外部像素本身 ⇒ 边界 Δ≈0，天然无台阶、无锯齿。

为什么放在链尾
--------------
`seg_head` 在 18/19/20/20b/20d 等步骤里会被反复重写（切眼线、切嘴线、
擦残渣、下颌修补）。在 18 步内做填充会被后面全部冲掉 —— 实测过，填完
再跑一遍链路，锯齿原样回来。所以这里放在**高清化之后、所有写像素的
步骤之后**，直接重写 seg_head.png / seg_head@2x.png。

用法：
  python3 tools/eye_socket_harmonic_fill.py --character xiaoxun --form chibi
"""
from __future__ import annotations

import argparse
import json
import os

import numpy as np
from PIL import Image

GROW = 4            # 挖除区在 socket 掩膜外再外扩多少像素（吃掉锯齿带）
FEATHER = 3         # 填充区与外部原肤的过渡宽度
TOL = 0.02
MAX_ITER = 3000


def dilate(m: np.ndarray, r: int) -> np.ndarray:
    out = m.copy()
    for _ in range(max(0, r)):
        cur = out.copy()
        out = cur.copy()
        out[1:, :] |= cur[:-1, :]
        out[:-1, :] |= cur[1:, :]
        out[:, 1:] |= cur[:, :-1]
        out[:, :-1] |= cur[:, 1:]
    return out


def inpaint_harmonic(chan, hole):
    """占位：真正的填充改用 body_full 原脸像素（见 fill_image）。"""
    return chan.astype(np.float64)


def _source_skin(sprites, head_hw, head_pos):
    """从 body_full（原画同源整图）里取一张与 seg_head 同坐标系的皮肤图。

    为什么用真源而不是插值（铁律 19，2026-11-11）：眼眶这块在插值路线下
    试过单尺度 SOR、多尺度金字塔、8 方向径向三种，分别产出 NaN / 乱码花纹 /
    斜向条纹 —— 洞太宽，任何内插都会把周围的头发/眼线色一起摊进来。
    而 body_full 是**同一张原画**的全图，眼孔位置在那里本来就是完好的皮肤
    （原画只把眼睛画在 eye_* 件里）。直接搬过来就是真原画像素，边界天然接上。
    """
    p = os.path.join(sprites, "body_full.png")
    if not os.path.exists(p):
        return None
    im = Image.open(p).convert("RGBA")
    # body_full 与画布同坐标系（rig pos 之外）；seg_head 在画布里的 pos
    hx, hy = head_pos
    H, W = head_hw
    canvas = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    # body_full 的放置位置：与 seg_head 同一画布坐标原点
    canvas.paste(im, (-hx, -hy))
    return np.asarray(canvas).astype(np.float64)


def build_hole(sprites: str, head_hw: tuple[int, int]) -> np.ndarray:
    """按 eyeline_parts.json 里的眼眶信息，在 seg_head 坐标系里重建 hole 掩膜。"""
    ep = json.load(open(os.path.join(sprites, "eyeline_parts.json"),
                        encoding="utf-8"))
    H, W = head_hw
    hole = np.zeros((H, W), bool)
    for e in ep.get("eyes", []):
        sock_img = e.get("socket_file") or \
            f"eye_{e['side']}_socket.png"
        p = os.path.join(sprites, sock_img)
        if not os.path.exists(p):
            continue
        sock = np.asarray(Image.open(p).convert("RGBA"))[..., 3]
        px, py = e["patch_pos"]
        ph, pw = sock.shape
        # 眼眶软边（alpha>24）就算要挖掉的范围
        m = sock > 24
        ys, xs = np.nonzero(m)
        if not len(ys):
            continue
        y0, y1 = int(ys.min()), int(ys.max()) + 1
        x0, x1 = int(xs.min()), int(xs.max()) + 1
        sub = m[y0:y1, x0:x1]
        # 贴到 seg_head 坐标
        gy0, gx0 = py + y0, px + x0
        gy1, gx1 = gy0 + sub.shape[0], gx0 + sub.shape[1]
        sy0, sx0 = max(0, gy0), max(0, gx0)
        sy1, sx1 = min(H, gy1), min(W, gx1)
        if sy1 <= sy0 or sx1 <= sx0:
            continue
        hole[sy0:sy1, sx0:sx1] |= sub[sy0 - gy0:sy1 - gy0,
                                      sx0 - gx0:sx1 - gx0]
    return hole


def fill_image(path: str, hole: np.ndarray, scale: int,
               src: np.ndarray | None = None,
               head_pos: tuple[int, int] = (0, 0)) -> tuple[int, float]:
    im = Image.open(path).convert("RGBA")
    arr = np.asarray(im).astype(np.float64)
    H, W = arr.shape[:2]
    h = hole
    if h.shape != arr.shape[:2]:
        hi = Image.fromarray((h * 255).astype(np.uint8), "L").resize(
            (W, H), Image.NEAREST)
        h = np.asarray(hi) > 127
    h = dilate(h, GROW)
    h &= arr[..., 3] > 0
    if not h.any():
        return 0, 0.0
    if src is None:
        return 0, 0.0
    s = src
    if s.shape[:2] != arr.shape[:2]:
        si = Image.fromarray(np.clip(s[..., :3], 0, 255).astype(np.uint8), "RGB")
        si = si.resize((W, H), Image.LANCZOS)
        s = np.dstack([np.asarray(si).astype(np.float64),
                       np.asarray(Image.fromarray(
                           np.clip(s[..., 3], 0, 255).astype(np.uint8), "L"
                       ).resize((W, H), Image.LANCZOS)).astype(np.float64)])
    ys, xs = np.nonzero(h)
    y0, y1 = int(ys.min()), int(ys.max()) + 1
    x0, x1 = int(xs.min()), int(xs.max()) + 1
    sub = arr[y0:y1, x0:x1, :3]
    m = h[y0:y1, x0:x1]
    src_sub = s[y0:y1, x0:x1, :3]
    src_ok = s[y0:y1, x0:x1, 3] > 200
    use = m & src_ok
    for c in range(3):
        sub[..., c] = np.where(use, src_sub[..., c], sub[..., c])
    # 只用原画像素，不做任何插值/羽化 —— 边界两侧都是同一张原画，本就连着。
    arr[y0:y1, x0:x1, :3] = np.clip(np.round(sub), 0, 255)
    arr[y0:y1, x0:x1, 3] = np.where(m, 255, arr[y0:y1, x0:x1, 3])
    Image.fromarray(arr.astype(np.uint8), "RGBA").save(path)
    # 接缝指标：洞边界内侧 2px 与外侧 2px 的均值差
    inner = h & ~dilate(~h, 2) & (arr[..., 3] > 0)
    outer = dilate(h, 2) & ~h & (arr[..., 3] > 0)
    seam = 0.0
    if inner.any() and outer.any():
        seam = float(abs(arr[..., :3][inner].mean() - arr[..., :3][outer].mean()))
    return int(use.sum()), seam


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--character", required=True)
    ap.add_argument("--form", required=True)
    ap.add_argument("--root", default=".")
    a = ap.parse_args()
    base = os.path.join(a.root, "characters", a.character, "forms", a.form)
    sp = os.path.join(base, "sprites")
    head1 = os.path.join(sp, "seg_head.png")
    head2 = os.path.join(sp, "seg_head@2x.png")
    if not os.path.exists(head1):
        print("[eye-fill] 没有 seg_head，跳过")
        return 0
    hw = Image.open(head1).size[::-1]
    rig = json.load(open(os.path.join(base, "rig.json"), encoding="utf-8"))
    head_pos = (0, 0)
    for pt in rig.get("parts", []):
        if pt.get("id") == "seg_head":
            head_pos = (int(round(pt["pos"][0])), int(round(pt["pos"][1])))
            break
    src = _source_skin(sp, hw, head_pos)
    hole = build_hole(sp, hw)
    if not hole.any():
        print("[eye-fill] 眼眶掩膜为空，跳过")
        return 0
    n1, s1 = fill_image(head1, hole, 1, src, head_pos)
    n2, s2 = fill_image(head2, hole, 2, src, head_pos) if os.path.exists(head2) else (0, 0.0)
    print(f"[eye-fill] seg_head 眼眶填充 {n1} 像素（@2x {n2}），"
          f"接缝均差 1x={s1:.1f} / 2x={s2:.1f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
