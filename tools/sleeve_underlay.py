#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""袖子塗り足し（arm_*_root 重建）—— 修"抬手时上臂变细"。

================================ 病因 ================================
用户第四十四问截图：挥手时右上臂明显比前臂细，像根棍子。

量出来的事实（切件坐标，垂直于肩→肘轴的横截面宽度，logs 见 JOURNAL）：

    上臂 upper∪cap∪root   0%:98  10%:67  20%:66  30%:51  40%:54  50%:58
                          60%:58  70%:62  80%:64  90%:66  100%:65
    前臂 fore             0%:64  10%:64  20%:66  30%:68  40%:75  50%:80 ...

**上臂中段只有 51~58px，比前臂还细** —— 解剖上是反的。

为什么会缺料：原画里手臂垂着，**白色夹克身压在青色袖子上**，袖子被盖住的那一半
在图上根本不存在。切件是照"看得见的青色"切的，于是上臂天生少了一条 6~14px 的月牙。
逐像素验证（沿横截面从袖子往身体方向走）：
    teal(75,159,171) → 夹克轮廓线(98,98,117) → 白色夹克(250,248,243)
袖子的青色在轮廓线处**戛然而止**，后面全是夹克。

Live2D 对这种情况的标准答案就是**塗り足し**：把被挡住的那一截补画出来，
放在遮挡者**下面**的图层 —— 静止时被夹克盖得严严实实（一个像素都看不见），
手臂一转开就自然露出来。我们本来就有这么个件（`arm_*_root`，层 95/96，
在 seg_torso 100 之下），**但它只补到上臂的 20%**，30% 往后一点没有。

更糟的是第二个坑：`make_rig.py` 给它绑了 `root_fade`
    alpha = clamp(1 − 1.29·v + 0.57)
抬手角 **36.9° 就归零**。也就是说唯一能补上臂的那块料，**恰好在抬手时被关掉**。
（当初加淡出是为了躲"大角度时袖根甩出剪影外"的布片 —— 又一次用 alpha 躲几何病，
和 Q41 肩帽淡出同一个错。）

================================ 做法 ================================
重建 `arm_*_root` = ①**肩圆盘内的旧料** ∪ ②**沿整条上臂的补料带**：

  ① 圆盘内：以肩枢轴为心、半径 R_shoulder 的圆内保留原样。
     圆关于自身圆心旋转不变 ⇒ 怎么转都不会甩出剪影外，且头顶还有
     静止的肩球 cap（层 142/143）压着，绝不会穿帮。
  ② 补料带：沿肩→肘轴，每条横截面把袖子的内缘从现在的位置推到
     **目标全宽**（右 33.5px / 左 30.5px，取自 10~20% 与 90~100% 两段
     未被夹克遮挡处的实测值），中间留 overlap 给抗锯齿。
     填色不是涂一块纯色：
       · 底色按同一横截面在袖子内部 4px 处采样（保住既有的明暗过渡）；
       · 最内侧 1.5px 画**轮廓线**，颜色取自同一横截面袖子**外缘的描边**，
         这样补出来的边缘和原画同一支笔；
       · 轮廓线往里 2px 做一道轻微压暗，模拟贴身那侧的阴影。
  圆盘外、补料带外的旧料**一律丢弃** —— 那些正是会甩出剪影的布片。
  这样"不会穿帮"是几何上可证的，不需要再靠 alpha 淡出兜底。

================================ 三条硬规矩（踩过的坑）================
 1. **@2x 必须按自己的分辨率重算**，不许由 1x 放大（rig 实际加载 @2x）。
 2. **搬/裁掩膜一律纯几何**，不与 alpha 阈值求交，否则羽化边会丢像素。
 3. **留 overlap**：补料带要和原袖子重叠 4px 压在一起，不然两边各自抗锯齿，
    合成 alpha = 1−(1−a)² < 1，接缝处会透出背景色。

幂等：写 `arm_parts.json["sleeve_underlay"]`，已存在且参数相同就跳过（--force 强制）。

用法：
    python3 tools/sleeve_underlay.py --character xiaoxun --form teen [--force]
"""
import argparse
import json
import math
import os
import sys

try:
    from PIL import Image
except ImportError:  # pragma: no cover
    sys.stderr.write("需要 Pillow：pip install pillow\n")
    raise


# ---------------------------------------------------------------- 小工具
def load_rgba(path):
    im = Image.open(path).convert("RGBA")
    return im, im.load(), im.size


def clamp(v, lo, hi):
    return lo if v < lo else (hi if v > hi else v)


class Plate(object):
    """一张切件 + 它在"切件坐标系"里的左上角位置，支持按绝对坐标取样。"""

    def __init__(self, path, pos, scale=1):
        self.im, self.px, (self.w, self.h) = load_rgba(path)
        self.x0 = pos[0] * scale
        self.y0 = pos[1] * scale
        self.scale = scale

    def at(self, x, y):
        """x/y 是**已乘 scale** 的绝对坐标；越界返回全透明。"""
        ix = int(round(x)) - self.x0
        iy = int(round(y)) - self.y0
        if 0 <= ix < self.w and 0 <= iy < self.h:
            return self.px[ix, iy]
        return (0, 0, 0, 0)

    def alpha(self, x, y):
        return self.at(x, y)[3]


def unit(dx, dy):
    L = math.hypot(dx, dy)
    return (dx / L, dy / L), L


# ---------------------------------------------------------------- 主流程
def build_side(sprites_dir, parts, joints, side, scale, target_w, overlap,
               r_shoulder, origin_pos=None, verbose=True):
    """返回 (新的 root 图像, 左上角位置(未除 scale), 统计)。scale ∈ {1,2}。"""
    suf = "@2x" if scale == 2 else ""

    def ppath(pid):
        return os.path.join(sprites_dir, "%s%s.png" % (pid, suf))

    up_id = "arm_%s_upper" % side
    rt_id = "arm_%s_root" % side
    cap_id = "arm_%s_cap" % side

    # ★ 本脚本**原地覆盖** arm_*_root，所以第一次跑先把原件存进 sprites/_orig/，
    #   以后每次都从原件重算 —— 否则换参数重跑会在自己上一次的结果上再补一层。
    orig_dir = os.path.join(sprites_dir, "_orig")
    if not os.path.isdir(orig_dir):
        os.makedirs(orig_dir)
    orig_root = os.path.join(orig_dir, "%s%s.png" % (rt_id, suf))
    if not os.path.exists(orig_root):
        Image.open(ppath(rt_id)).convert("RGBA").save(orig_root)
        print("  原件备份 → %s" % orig_root)
    root_pos = (origin_pos or {}).get(rt_id, parts[rt_id]["pos"])

    upper = Plate(ppath(up_id), parts[up_id]["pos"], scale)
    root = Plate(orig_root, root_pos, scale)
    cap = Plate(ppath(cap_id), parts[cap_id]["pos"], scale)

    sh = [joints["shoulder_joint"][side][0] * scale,
          joints["shoulder_joint"][side][1] * scale]
    el = [joints["elbow_joint"][side][0] * scale,
          joints["elbow_joint"][side][1] * scale]
    (ux, uy), L = unit(el[0] - sh[0], el[1] - sh[1])

    # 内侧法线：指向身体（躯干中心 x）。切件坐标里身体中心 x ≈ 216（rig 416 − 200）。
    body_cx = 216.0 * scale
    n1 = (-uy, ux)
    mid = (sh[0] + ux * L * 0.5, sh[1] + uy * L * 0.5)
    n_in = n1 if (mid[0] + n1[0] - body_cx) ** 2 < (mid[0] - n1[0] - body_cx) ** 2 else (-n1[0], -n1[1])

    TW = target_w * scale
    OV = overlap * scale
    R = r_shoulder * scale

    # 先扫一遍，确定要画的像素集合与颜色
    paint = {}          # (x,y) -> (r,g,b,a)
    keep = {}           # 圆盘内保留的旧料
    step = 0.5
    f = 0.0
    nseg = int(L / step) + 1
    for i in range(nseg + 1):
        f = (i * step) / L
        if f > 1.02:
            break
        cx = sh[0] + ux * L * f
        cy = sh[1] + uy * L * f

        # 1) 内缘 = **改完之后还会留下的料**（upper ∪ cap ∪ 旧 root∩肩圆盘）的最内侧。
        #    ★坑（第一版踩过）：这里如果把整块旧 root 算进来，f≈20% 那一段会因为
        #    "旧 root 已经够宽"而跳过补料，可旧 root 在圆盘外的部分随后又被丢弃
        #    ⇒ 当场在上臂 20% 处开一个 48px 的腰。只能按幸存料算。
        t_in = None
        t = 0.0
        while t <= 60 * scale:
            x = cx + n_in[0] * t
            y = cy + n_in[1] * t
            in_disc = (x - sh[0]) ** 2 + (y - sh[1]) ** 2 <= R * R
            if (upper.alpha(x, y) > 24 or cap.alpha(x, y) > 24
                    or (in_disc and root.alpha(x, y) > 24)):
                t_in = t
            t += 0.5
        if t_in is None:
            continue

        # 2) 外缘描边色（这条横截面上，袖子外侧最外那 2px 的颜色）
        line_col = None
        t = 0.0
        while t <= 60 * scale:
            x = cx - n_in[0] * t
            y = cy - n_in[1] * t
            if upper.alpha(x, y) > 128:
                line_col = upper.at(x, y)
            t += 0.5
        if line_col is None:
            line_col = (70, 110, 130, 255)

        # 3) 底色：袖子**内部**取样。
        #    ★坑（第一版踩过）：只往里 2px 取样，正好落在内缘那条深色描边上
        #    （原画里夹克的轮廓线被切进了袖子件），整条补料被涂成近黑 (25,45,66)。
        #    必须往里走到真正的袖面，并要求"够亮"才认。
        base = None
        best = None
        d = 5.0
        while d <= 26.0:
            c = upper.at(cx + n_in[0] * (t_in - d * scale),
                         cy + n_in[1] * (t_in - d * scale))
            if c[3] > 200:
                lum = 0.3 * c[0] + 0.6 * c[1] + 0.1 * c[2]
                if best is None or lum > best[0]:
                    best = (lum, c)
                if lum >= 150:           # 袖面青色 ≈ (105,190,190) → lum≈170
                    base = c
                    break
            d += 1.0
        if base is None:
            base = best[1] if best else (100, 180, 185, 255)

        if TW - t_in < 0.5:
            continue  # 这一段本来就够宽

        # 4) 画补料带：从 t_in−OV 一直到 TW
        t = t_in - OV
        while t <= TW:
            x = cx + n_in[0] * t
            y = cy + n_in[1] * t
            depth = (t - (t_in - OV)) / max(1e-6, (TW - (t_in - OV)))   # 0..1
            edge_d = TW - t                                            # 距新边缘
            if edge_d <= 1.5 * scale:
                # 轮廓线：用袖子自己的描边色，边缘 0.5px 做羽化
                a = 255 if edge_d > 0.5 * scale else 150
                col = (line_col[0], line_col[1], line_col[2], a)
            else:
                # 贴身那侧略压暗（最多 10%），模拟阴影
                k = 1.0 - 0.10 * clamp(depth, 0.0, 1.0)
                col = (int(base[0] * k), int(base[1] * k), int(base[2] * k), 255)
            for ddx in (-0.35, 0.0, 0.35):
                for ddy in (-0.35, 0.0, 0.35):
                    paint[(int(round(x + ddx)), int(round(y + ddy)))] = col
            t += 0.5

    # 5) 圆盘内的旧料原样保留（纯几何，不与 alpha 求交）
    rx0, ry0 = root.x0, root.y0
    for iy in range(root.h):
        for ix in range(root.w):
            c = root.px[ix, iy]
            if c[3] == 0:
                continue
            X, Y = ix + rx0, iy + ry0
            if (X - sh[0]) ** 2 + (Y - sh[1]) ** 2 <= R * R:
                keep[(X, Y)] = c

    merged = dict(paint)
    merged.update(keep)      # 圆盘内旧料优先（那是原画，不是我补的）
    if not merged:
        return None, None, {}

    xs = [p[0] for p in merged]
    ys = [p[1] for p in merged]
    x0, x1 = min(xs), max(xs)
    y0, y1 = min(ys), max(ys)
    W, H = x1 - x0 + 1, y1 - y0 + 1
    out = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    op = out.load()
    for (X, Y), c in merged.items():
        op[X - x0, Y - y0] = c
    stat = {"painted_px": len(paint), "kept_px": len(keep),
            "size": [W, H], "pos": [x0, y0]}
    if verbose:
        print("  [%s] %s 补料 %d px / 圆盘内保留 %d px → %dx%d @(%d,%d)"
              % (side, "1x" if scale == 1 else "@2x",
                 len(paint), len(keep), W, H, x0, y0))
    return out, (x0, y0), stat


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--character", required=True)
    ap.add_argument("--form", required=True)
    ap.add_argument("--target-w-r", type=float, default=33.5,
                    help="右臂袖子内缘目标半宽（切件 1x 像素）")
    ap.add_argument("--target-w-l", type=float, default=30.5)
    ap.add_argument("--overlap", type=float, default=4.0)
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args()

    base = os.path.join("characters", a.character, "forms", a.form)
    sprites = os.path.join(base, "sprites")
    jpath = os.path.join(sprites, "arm_parts.json")
    J = json.load(open(jpath, encoding="utf-8"))
    parts = {p["id"]: p for p in J["parts"]}

    sig = {"target_w_r": a.target_w_r, "target_w_l": a.target_w_l,
           "overlap": a.overlap, "v": 1}
    if J.get("sleeve_underlay", {}).get("sig") == sig and not a.force:
        print("[sleeve_underlay] 已经做过且参数相同，跳过（--force 强制重做）")
        return 0

    rs = {"l": J["round_socket"]["l"]["r_shoulder"],
          "r": J["round_socket"]["r"]["r_shoulder"]}
    # 原件（_orig/）对应的 pos：第一次跑就是当前 pos；之后从 sleeve_underlay.orig_pos 取
    orig_pos = J.get("sleeve_underlay", {}).get("orig_pos") or {
        "arm_l_root": list(parts["arm_l_root"]["pos"]),
        "arm_r_root": list(parts["arm_r_root"]["pos"]),
    }
    report = {"sig": sig, "orig_pos": orig_pos, "sides": {}}
    for side in ("l", "r"):
        print("[sleeve_underlay] %s 臂" % side)
        tw = a.target_w_r if side == "r" else a.target_w_l
        res1 = build_side(sprites, parts, J, side, 1, tw, a.overlap, rs[side], orig_pos)
        res2 = build_side(sprites, parts, J, side, 2, tw, a.overlap, rs[side], orig_pos)
        img1, pos1, st1 = res1
        img2, pos2, st2 = res2
        if img1 is None:
            print("  跳过（没有要补的料）")
            continue
        # @2x 的左上角必须是 1x 的两倍：取两者并集后统一对齐
        want2 = (pos1[0] * 2, pos1[1] * 2)
        if pos2 != want2 or (img2.size[0], img2.size[1]) != (img1.size[0] * 2, img1.size[1] * 2):
            # 把 @2x 贴进"严格 2 倍"的画布，保证 rig 的 scale=0.5 对得上
            canvas = Image.new("RGBA", (img1.size[0] * 2, img1.size[1] * 2), (0, 0, 0, 0))
            canvas.alpha_composite(img2, (pos2[0] - want2[0], pos2[1] - want2[1]))
            img2 = canvas
            print("    @2x 对齐到严格 2 倍画布 %dx%d" % img2.size)
        rid = "arm_%s_root" % side
        img1.save(os.path.join(sprites, rid + ".png"))
        img2.save(os.path.join(sprites, rid + "@2x.png"))
        parts[rid]["pos"] = [pos1[0], pos1[1]]
        parts[rid]["size"] = [img1.size[0], img1.size[1]]
        parts[rid]["note"] = ("袖根塗り足し（G108 + Q44 全长补料）：原画里袖子被白色夹克身"
                              "盖掉的那一半在图上根本不存在，这里按横截面把内缘推到全宽补回来；"
                              "层 95/96 在躯干之下 ⇒ 静止时一个像素都看不见，抬手才露出来。"
                              "几何上只含『肩圆盘内 + 上臂管内』两块，怎么转都不会甩出剪影外，"
                              "所以 Q44 起**不再做 alpha 淡出**")
        report["sides"][side] = {"1x": st1, "2x": st2}
    J["sleeve_underlay"] = report
    json.dump(J, open(jpath, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print("[sleeve_underlay] 写回 %s" % jpath)
    return 0


if __name__ == "__main__":
    sys.exit(main())
