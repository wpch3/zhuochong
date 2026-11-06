#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把手臂的两个关节做成「正圆关节」（第四十二问）。

★★★ 为什么要有这一步
------------------------------------------------------------------
用户第四十一/四十二问连着打回同一处：挥手时右肩**整块塌进去**，手臂像从胸口
长出来的；之前还甩出过尖角布片和一条压在夹克上的青色楔形。

把四件分色摆进 rig 坐标一看就明白（logs/asset_qa/q42_parts.png）：

  · `arm_*_upper`（旋转件）顶端是**一刀平切**，而且整整高出肩枢轴 63px，
    是一根尖刺。绕肩一转，尖刺就扫到胸口 ⇒ 第四十一问那条青色楔形。
  · `arm_*_cap`（肩帽，group=chest **不转**）是个半径 64 的扇形，静止时和袖子
    拼在一起看不出来；手臂转开后它原地不动 ⇒ 第四十一问那块尖角布片。
  · Q41 我把 upper 压到躯干底下（97/98）躲楔形 —— 袖根被夹克盖住，手臂只能
    从胸侧露头 ⇒ 第四十二问用户说的「肩头内缩」。

三个病象、同一个病根：**关节处的图形不是"绕枢轴旋转不变"的**。

教程口径（Live2D 官方「関節パーツは腕幅と同じ直径の**正円**、枢轴＝その中心」，
`make_rig.py` 2440 行注释早写过）：关节那一圈必须是**以枢轴为圆心的圆**；
圆内的料归**不转的那一侧**，圆外的归**转的那一侧**。于是无论转多少度：
  – 圆内那块永远在原地 ⇒ 肩头不会塌、也不会被甩出去变布片；
  – 圆外那块的根部是一段正好贴着圆的弧 ⇒ 转到哪都严丝合缝。

★★★ 这个脚本干的事（幂等）
------------------------------------------------------------------
  肩：  upper 里「圆内 ∪ 枢轴以上」的像素 → 搬进 **cap**（静止的"肩球"）
        upper 自己**往圆里多留 overlap 一圈**（重叠带）再被 cap 压住
  肘：  upper 下端超出 disc(肘) 的方角 → 删（静止时被前臂盖着，看不出来）
        fore 上端超出 disc(肘) 的方角 → 删 ⇒ 两个半圆共心，折肘时肘永远是圆的

★★★ 两个坑（都踩过，别再踩）
------------------------------------------------------------------
 1. **必须留重叠带**。硬切成两半时两边各自抗锯齿，合成 alpha
    = 1-(1-a)(1-a) < 1，接缝处透出背景色 —— 实拍 q42_socket.png 肩上那条洋红缝。
 3. **搬件/裁件一律纯几何，不要和 alpha 掩膜求交**。拿 alpha>8 当闸门时，
    alpha 1~8 的羽化边既没被搬走也没被留下 —— 直接丢了。后果不是"看不见的
    一点点"：袖根塗り足し（layer 95/96 画在躯干底下）的边缘少了那层半透明遮挡，
    check_assets「袖根静止时完全藏住」当场红 91/48 px。像素守恒要的是
    **每个像素都有去处**。
 2. **@2x 要按自己的分辨率重算，不能拿 1x 缩放**。rig 真正加载的是 @2x；
    第一版我把新尺寸的 1x 图 resize 进**旧尺寸**的 @2x 画布，肩球整体错位，
    于是袖子上横着一道洋红弧（q42_gash2.png 右格）。现在两档各算各的。

用法：  python3 tools/round_arm_sockets.py --character xiaoxun --form teen
流水线位置：make_arm_parts.py（3/26）之后、make_rig.py 之前。
"""
import argparse
import io
import json
import os

import numpy as np
from PIL import Image


def load(path):
    return Image.open(path).convert("RGBA")


def mask_of(im, thr=8):
    return np.array(im.getchannel("A")).astype(int) > thr


def part_by_id(parts, pid):
    for p in parts:
        if p["id"] == pid:
            return p
    return None


def geom(shape, pos, s):
    """该贴图每个像素在 1x body_full 坐标里的 (X, Y)。s=1 或 2（@2x）。"""
    h, w = shape
    ys, xs = np.mgrid[0:h, 0:w]
    return xs / float(s) + pos[0], ys / float(s) + pos[1]


def measure_radius(im, pos, pivot, axis, band=6.0):
    """量关节线上袖子的横截面：枢轴到边缘的最大距离。"""
    m = mask_of(im)
    X, Y = geom(m.shape, pos, 1)
    dx, dy = X - pivot[0], Y - pivot[1]
    along = dx * axis[0] + dy * axis[1]
    perp = np.abs(dx * -axis[1] + dy * axis[0])
    sel = m & (np.abs(along) <= band)
    return float(perp[sel].max()) if sel.any() else None


def files_of(part):
    """返回 [(相对路径, 分辨率倍数)]，1x 和 @2x 都在。"""
    rel = part["file"]
    out = [(rel, 1)]
    rel2 = rel.replace(".png", "@2x.png")
    out.append((rel2, 2))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--character", required=True)
    ap.add_argument("--form", required=True)
    ap.add_argument("--margin", type=float, default=2.0,
                    help="关节圆半径在实测横截面之上再放宽几像素")
    ap.add_argument("--overlap", type=float, default=4.0,
                    help="重叠带宽度（1x 像素）。必须 >0，见文件头坑 1")
    ap.add_argument("--force", action="store_true", help="忽略幂等标记重跑")
    a = ap.parse_args()

    base = os.path.join("characters", a.character, "forms", a.form)
    apj = os.path.join(base, "sprites", "arm_parts.json")
    if not os.path.exists(apj):
        print("[socket] 没有 arm_parts.json，跳过")
        return
    with io.open(apj, encoding="utf-8") as f:
        rep = json.load(f)
    parts = rep["parts"]
    if rep.get("round_socket") and not a.force:
        print("[socket] 已做过正圆关节，跳过（幂等）")
        return

    done = {}
    for side in ("l", "r"):
        up = part_by_id(parts, "arm_%s_upper" % side)
        fo = part_by_id(parts, "arm_%s_fore" % side)
        cp = part_by_id(parts, "arm_%s_cap" % side)
        if not (up and fo and cp):
            continue
        sh = up["pivot"]
        el = fo["pivot"]
        axis = np.array([el[0] - sh[0], el[1] - sh[1]], float)
        axis /= np.hypot(*axis)

        im_up1 = load(os.path.join(base, up["file"]))
        im_fo1 = load(os.path.join(base, fo["file"]))
        r_sh = (measure_radius(im_up1, up["pos"], sh, axis) or 32.0) + a.margin
        r_el = max(measure_radius(im_up1, up["pos"], el, axis) or 29.0,
                   measure_radius(im_fo1, fo["pos"], el, axis) or 0.0) + a.margin

        # 新 cap 画布的 1x bbox：老 cap ∪ 要搬过来的像素
        # ★ 两档分辨率都要量：@2x 上有些边缘像素在 1x 缩放后低于阈值，
        #   只按 1x 定 bbox 会差 1~2px，写 @2x 时越界（第一版就是这么崩的）。
        im_cp1 = load(os.path.join(base, cp["file"]))
        bx0, by0 = cp["pos"][0], cp["pos"][1]
        bx1 = cp["pos"][0] + im_cp1.width
        by1 = cp["pos"][1] + im_cp1.height
        for s in (1, 2):
            suf = "" if s == 1 else "@2x"
            f_up = os.path.join(base, up["file"].replace(".png", suf + ".png"))
            if not os.path.exists(f_up):
                continue
            m = mask_of(load(f_up), thr=0)
            X, Y = geom(m.shape, up["pos"], s)
            dx, dy = X - sh[0], Y - sh[1]
            tc = m & (((dx * dx + dy * dy) <= r_sh * r_sh) |
                      ((dx * axis[0] + dy * axis[1]) < 0.0))
            ys, xs = np.nonzero(tc)
            bx0 = min(bx0, up["pos"][0] + xs.min() / float(s))
            by0 = min(by0, up["pos"][1] + ys.min() / float(s))
            bx1 = max(bx1, up["pos"][0] + (xs.max() + 1) / float(s))
            by1 = max(by1, up["pos"][1] + (ys.max() + 1) / float(s))
        nx0, ny0 = int(np.floor(bx0)), int(np.floor(by0))
        nx1, ny1 = int(np.ceil(bx1)) + 1, int(np.ceil(by1)) + 1

        stat = {}
        for s in (1, 2):                      # ★ 两档分辨率各算各的（坑 2）
            suf = "" if s == 1 else "@2x"
            f_up = os.path.join(base, up["file"].replace(".png", suf + ".png"))
            f_fo = os.path.join(base, fo["file"].replace(".png", suf + ".png"))
            f_cp = os.path.join(base, cp["file"].replace(".png", suf + ".png"))
            if not (os.path.exists(f_up) and os.path.exists(f_fo)):
                continue
            im_up, im_fo, im_cp = load(f_up), load(f_fo), load(f_cp)
            # ★★★ 搬件/裁件一律**纯几何**，不要再和 alpha 掩膜求交。
            #   第一版拿 alpha>8 的二值掩膜当闸门，alpha 1~8 的羽化边既没被搬走
            #   也没被留下 —— 直接丢了。后果：袖根塗り足し（layer 95/96，画在躯干
            #   底下）的边缘少了那层半透明遮挡，check_assets「袖根静止时完全藏住」
            #   当场红 91/48 px。像素守恒要的是**每个像素都有去处**。
            m_up = mask_of(im_up, thr=0)     # 只有"有颜色"的像素需要搬
            m_fo = mask_of(im_fo, thr=0)

            X, Y = geom(m_up.shape, up["pos"], s)
            dxs, dys = X - sh[0], Y - sh[1]
            rr = dxs * dxs + dys * dys
            along_sh = dxs * axis[0] + dys * axis[1]
            to_cap = m_up & ((rr <= r_sh * r_sh) | (along_sh < 0.0))
            # 转动件：圆内留 overlap 一圈（被 cap 压着），其余照旧
            # ★ keep 必须是**纯几何**：和 alpha 掩膜求交会把羽化边（alpha 1~8）
            #   既不搬走也不留下 = 丢像素（见文件头坑 3）。
            keep_up = ~((rr <= (r_sh - a.overlap) ** 2) | (along_sh < -a.overlap))
            # 肘：超出 disc(肘) 的方角删掉
            dxe, dye = X - el[0], Y - el[1]
            past_el = (dxe * axis[0] + dye * axis[1]) > 0.0
            keep_up &= ~(past_el & ((dxe * dxe + dye * dye) > r_el * r_el))

            Xf, Yf = geom(m_fo.shape, fo["pos"], s)
            dxf, dyf = Xf - el[0], Yf - el[1]
            before_el = (dxf * axis[0] + dyf * axis[1]) < 0.0
            keep_fo = ~(before_el & ((dxf * dxf + dyf * dyf) > r_el * r_el))

            # ★ 先从**原图**把要搬的像素抠出来（下一步就要把它们从上臂清掉了）
            W, H = int((nx1 - nx0) * s), int((ny1 - ny0) * s)
            moved = np.zeros((H, W, 4), np.uint8)
            src = np.array(im_up)
            my, mx = np.nonzero(to_cap)
            moved[my + int((up["pos"][1] - ny0) * s),
                  mx + int((up["pos"][0] - nx0) * s)] = src[my, mx]

            # 落盘：上臂 / 前臂（清掉各自不要的部分）
            for im, keep, path in ((im_up, keep_up, f_up), (im_fo, keep_fo, f_fo)):
                al = np.array(im.getchannel("A"))
                al[~keep] = 0
                im.putalpha(Image.fromarray(al))
                im.save(path)

            # 落盘：新 cap = 搬来的料（下） + 老 cap（上，原样保留）
            new_cap = Image.fromarray(moved)
            new_cap.alpha_composite(im_cp, (int((cp["pos"][0] - nx0) * s),
                                            int((cp["pos"][1] - ny0) * s)))
            new_cap.save(f_cp)
            stat[s] = (int(to_cap.sum()), int(keep_up.sum()), int(keep_fo.sum()))

        cp["pos"] = [nx0, ny0]
        cp["size"] = [nx1 - nx0, ny1 - ny0]
        cp["note"] = ("静止的「肩球」：关节正圆以内 + 枢轴以上的袖料都归它（第四十二问）。"
                      "不跟着手臂转 ⇒ 抬手时肩头既不会塌、也不会被甩成布片")
        done[side] = {"r_shoulder": round(r_sh, 1), "r_elbow": round(r_el, 1),
                      "overlap": a.overlap, "moved_px_1x": stat.get(1, [0])[0]}
        print("[socket] %s 肩圆 R=%.1f 肘圆 R=%.1f 重叠 %.0fpx  搬进 cap %d px(1x)"
              % (side, r_sh, r_el, a.overlap, stat.get(1, [0])[0]))

    rep["round_socket"] = done
    with io.open(apj, "w", encoding="utf-8") as f:
        json.dump(rep, f, ensure_ascii=False, indent=1)
    print("[socket] 写回 %s" % apj)


if __name__ == "__main__":
    main()
