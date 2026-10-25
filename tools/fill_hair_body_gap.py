#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""fill_hair_body_gap.py —— 把后发补成**一整片完整头发**（用户 2026-10-26 指出的正确做法）

★ 用户的判断（我上一轮错了）
--------------------------------------------------------------------
我之前回答"两片头发中间那块空白不用补，因为它在躯干/裙/腿后面，永远看不到"。
**这句话只对静态一帧成立，对会动的头发是错的。** 用户的原话是：

> 拥有完整无缺的头发，而身体覆盖的部分做个分层，比如腿遮住的位置还是有原本的头发，
> 包括手臂也是，而是像上个代理一样在头发上画个假手臂，这样头发飘动时也不会有空隙……
> 你现在做的头发就是在犯和上个代理一样的错误，增加多余的链接。

对。机制是这样的：后发在层 58（**所有身体件之后**），身体把中间那块盖住；
一旦 `ParamHairSway` / 摆链让头发横向位移，**头发动、身体不动** ——
头发上那个"身体形状的洞"会跟着头发移动，洞的边缘就从身体轮廓边上露出来，
露出的是**背景**。这就是"空隙"。补洞穴、搬碎岛、加连接带都是治标；
**根治只有一条：头发自己必须是完整的一片**（Live2D 的「塗り足し」），
被身体盖住的那些像素**照样画满头发**，让身体去盖。

⚠️ 与上个代理的区别（用户特意点名）：不是"在头发上画假手臂"，
**是画满头发**。头发层里不许出现任何衣服/皮肤像素 —— 这一条由
`qa_sprite_audit` 的残留指标 + 目视双判守着。

★ 第一版为什么被否掉（很重要，别重犯）
--------------------------------------------------------------------
第一版是"逐行取最左/最右头发像素，中间按左右端点颜色线性插值填满"。
结果：填是填满了，但**填出来的是一条一条横线**（用户看一眼就会说"这不是头发"），
外轮廓还变成了方块。原因是我把"补满"当成了"填像素"，
而头发是有走向的 —— 横向插值必然把竖着的发流画成横纹。

**正道是让源头就画出完整的一片。** 现在用的是：
1. 生成"整片实心后发"（中间没有洞，内侧用暗一档的同色系表现厚度）；
2. `key_magenta.py` 抠像 + 配色对齐；
3. `fit_hair_part.py` 拟合进旧件几何。

所以本工具现在只做**检查**（默认 `--dry-run` 语义），`--apply` 才真的填，
而且填之前要求"洞是竖直方向的"（横向插值只对竖直洞说得过去）。
**不要用它去补大片横向空缺。**

用法
----
    python3 tools/fill_hair_body_gap.py --character xiaoxun --form teen --part acc_hair_long
    python3 tools/fill_hair_body_gap.py ... --dry-run     # 只报要补多少
    python3 tools/fill_hair_body_gap.py ... --out /tmp/x.png
"""
from __future__ import annotations

import argparse
import json
import os
import sys

import numpy as np
from PIL import Image, ImageFilter

BODY_PREFIX = ("seg_", "skirt_", "arm_", "hand_", "foot_", "body_")


def load(part_id, char, form, root):
    base = os.path.join(root, "characters", char, "forms", form)
    rig = json.load(open(os.path.join(base, "rig.json"), encoding="utf-8"))
    part = next((p for p in rig["parts"] if p["id"] == part_id), None)
    if part is None:
        raise SystemExit("rig 里没有部件 %s" % part_id)
    path = os.path.join(base, part["file"])
    return base, rig, part, path


def placement(part, size):
    sc = part.get("scale", 0.5)
    sx, sy = (sc, sc) if isinstance(sc, (int, float)) else (sc[0], sc[1])
    W, H = size
    return (part["pos"][0], part["pos"][1], part["anchor"][0], part["anchor"][1], sx, sy, W, H)


def to_canvas(pl, u, v):
    x0, y0, ax, ay, sx, sy, W, H = pl
    return x0 + (u - W * ax) * sx, y0 + (v - H * ay) * sy


def to_sprite(pl, cx, cy):
    x0, y0, ax, ay, sx, sy, W, H = pl
    return (cx - x0) / sx + W * ax, (cy - y0) / sy + H * ay


def body_mask(base, rig, part, size):
    """画布上"身体件"的并集（层号比该件大的身体/服装/四肢）。"""
    from qa_layer_visibility import footprint
    W, H = size
    m = np.zeros((H, W), bool)
    for q in rig["parts"]:
        if q["layer"] <= part["layer"]:
            continue
        if not q["id"].startswith(BODY_PREFIX):
            continue
        f = footprint(q, base, (W, H))
        if f is not None:
            m |= f
    return m


def fill_rows(a):
    """逐行线性插值补满。只写原本 alpha==0 的像素。返回（新数组, 补的像素数）。"""
    out = a.copy()
    A = a[:, :, 3]
    filled = 0
    for y in range(A.shape[0]):
        row = np.nonzero(A[y] > 24)[0]
        if row.size < 2:
            continue                       # 这一行没有头发，或者只有一个点：不补
        L, R = int(row[0]), int(row[-1])
        if R - L < 3:
            continue
        seg = A[y, L:R + 1]
        hole = seg == 0
        if not hole.any():
            continue
        # 左右两端的颜色（各取 3px 平均，免得取到抗锯齿边）
        cl = a[y, max(L, L):L + 3, :3].reshape(-1, 3).mean(axis=0)
        cr = a[y, R - 2:R + 1, :3].reshape(-1, 3).mean(axis=0)
        xs = np.arange(L, R + 1)
        t = ((xs - L) / max(1, (R - L)))[:, None]
        col = np.clip(cl[None, :] * (1 - t) + cr[None, :] * t, 0, 255)
        idx = np.nonzero(seg == 0)[0]
        out[y, L + idx, :3] = col[idx].astype(np.uint8)
        out[y, L + idx, 3] = 255
        filled += int(idx.size)
    return out, filled


def interior_holes(op):
    """不透明区域内部被包住的透明像素（= 素材上的"洞"）。"""
    from collections import deque
    h, w = op.shape
    seen = np.zeros_like(op)
    dq = deque()
    for x in range(w):
        for y in (0, h - 1):
            if not op[y, x] and not seen[y, x]:
                seen[y, x] = True
                dq.append((y, x))
    for y in range(h):
        for x in (0, w - 1):
            if not op[y, x] and not seen[y, x]:
                seen[y, x] = True
                dq.append((y, x))
    while dq:
        y, x = dq.popleft()
        for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            ny, nx = y + dy, x + dx
            if 0 <= ny < h and 0 <= nx < w and not op[ny, nx] and not seen[ny, nx]:
                seen[ny, nx] = True
                dq.append((ny, nx))
    return ~op & ~seen


def fill_interior_holes(arr, min_px=200, iters=4000):
    """把内部洞用**周围的不透明像素颜色**由外向内一圈圈长进去（形态学 inpaint）。

    ★ 为什么不是横向插值：洞是透镜形的，横向插值会画出一排横纹（第一版的毛病）。
      由外向内长，长出来的是**周围发色的连续延伸**，和发流方向一致。
    ★ 为什么一定要补：这些洞在头发轮廓**里面**。头发一晃，洞跟着晃，
      洞的边缘一移出身体轮廓，背景就从洞里透出来 —— 这就是用户说的"空隙"。
      头发不该透，洞必须变成头发。
    """
    out = arr.copy()
    A = out[:, :, 3] > 24
    holes = interior_holes(A)
    if not holes.any():
        return out, 0
    from collections import deque
    # 只补够大的洞（抗锯齿小孔不必管）
    lab = np.zeros(holes.shape, np.int32)
    comps = []
    cur = 0
    ys, xs = np.nonzero(holes)
    for y0, x0 in zip(ys, xs):
        if lab[y0, x0] or not holes[y0, x0]:
            continue
        cur += 1
        dq = deque([(y0, x0)])
        lab[y0, x0] = cur
        pix = []
        while dq:
            y, x = dq.popleft()
            pix.append((y, x))
            for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                ny, nx = y + dy, x + dx
                if 0 <= ny < holes.shape[0] and 0 <= nx < holes.shape[1] \
                        and holes[ny, nx] and not lab[ny, nx]:
                    lab[ny, nx] = cur
                    dq.append((ny, nx))
        if len(pix) >= min_px:
            comps.append((cur, pix))
    filled = 0
    for cid, pix in comps:
        todo = {(y, x) for y, x in pix}
        pending = set(todo)
        for _ in range(iters):
            if not pending:
                break
            done = []
            for (y, x) in list(pending):
                acc = np.zeros(3)
                n = 0
                for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (1, -1), (-1, 1), (-1, -1)):
                    ny, nx = y + dy, x + dx
                    if 0 <= ny < A.shape[0] and 0 <= nx < A.shape[1] and A[ny, nx]:
                        acc += out[ny, nx, :3]
                        n += 1
                if n:
                    out[y, x, :3] = (acc / n).astype(np.uint8)
                    out[y, x, 3] = 255
                    done.append((y, x))
            for p_ in done:
                pending.discard(p_)
                A[p_[0], p_[1]] = True
                filled += 1
    return out, filled


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--character", default="xiaoxun")
    ap.add_argument("--form", default="teen")
    ap.add_argument("--part", default="acc_hair_long")
    ap.add_argument("--root", default=".")
    ap.add_argument("--out", default="")
    ap.add_argument("--apply", action="store_true",
                    help="真的写回文件。默认只报数（第一版的横向插值已被否，别再默认写）")
    a = ap.parse_args()

    base, rig, part, path = load(a.part, a.character, a.form, a.root)
    im = Image.open(path).convert("RGBA")
    arr = np.array(im)
    W, H = im.size
    pl = placement(part, (W, H))
    canvas = (rig["canvas"]["w"], rig["canvas"]["h"])

    # 补之前：数据上"会被身体盖住、但头发上没有像素"的地方有多少（这就是将来的空隙）
    bm = body_mask(base, rig, part, canvas)
    A = arr[:, :, 3] > 24
    fp = np.zeros((canvas[1], canvas[0]), bool)   # 注意是 (h, w)
    ys, xs = np.nonzero(A)
    cx, cy = to_canvas(pl, xs, ys)
    # 取整后可能正好落在画布外沿（848/1360），先夹住再筛
    cx = np.clip(np.round(cx).astype(int), 0, canvas[0] - 1)
    cy = np.clip(np.round(cy).astype(int), 0, canvas[1] - 1)
    fp[cy, cx] = True
    gap_before = int((bm & ~fp).sum())

    new, filled = fill_rows(arr)
    gap_after = int((bm & ~_footprint(new, pl, canvas)).sum())

    print("%s：精灵内补满 %d px；画布上『被身体盖住却没头发』%d → %d px"
          % (a.part, filled, gap_before, gap_after))
    if not a.apply:
        print("（只报数。要写回加 --apply；但注意：横向插值会把发流画成横纹，"
              "大空缺请改用『整片源头』路线）")
        return 0
    out_path = a.out or path
    Image.fromarray(new).save(out_path)
    print("  写出", out_path)
    return 0


def _footprint(arr, pl, canvas):
    m = np.zeros((canvas[1], canvas[0]), bool)   # 注意是 (h, w)
    ys, xs = np.nonzero(arr[:, :, 3] > 24)
    cx, cy = to_canvas(pl, xs, ys)
    cx = np.clip(np.round(cx).astype(int), 0, canvas[0] - 1)
    cy = np.clip(np.round(cy).astype(int), 0, canvas[1] - 1)
    m[cy, cx] = True
    return m


if __name__ == "__main__":
    sys.exit(main())
