#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""肘内侧褶布（arm_*_gusset）—— 修「折肘处像两根管子交叉、有折叠痕迹」。

================================ 病因 ================================
第五十问用户原话：「因为是直角直接翻过来，加上截图1这里有折叠痕迹，
看起来不是很自然」。

按工序先出参考比对图（REF-FIRST）：
  · logs/asset_qa/q50_ref_arm.png —— 把唯一姿势参考
    characters/xiaoxun/design/pose_ref/wave_up.png 的右臂放大 3× 看：
    **折起来的袖子是一整块连续的布**。上臂从肩垂下、肘在最下方兜一个大 U、
    前臂再折回袖口，两根管子之间**没有任何背景**，只有两三条柔和的布褶线。
  · logs/asset_qa/q50_notch_probe.png —— 我们的挥手峰值帧同位置实拍，
    把「夹在两根袖管之间的背景像素」染红：**705 px 的一整个三角缺口**，
    从袖口一路收到两条轮廓线交叉的那个尖点。

所以「折叠痕迹」不是线画错了，是**布少了一块**：真实的袖子在折肘内侧会
堆布（袖子是松的），我们把上臂和前臂切成了两根互不相干的管子，一折起来
中间就露出背景，眼睛读出来就是「一张纸对折」。

================================ 做法 ================================
业界口径（Live2D / 2D 骨骼通用，见 docs/memory/REFERENCE_NOTES.md 第六十四批）：
  · cg-method.com/vtuber/live2d-glue/ ——「グルーは外側だけ固定、内側は
    固定せずに**手動で内側の折れ線を縮める**」：折叠内侧要主动补/压布，
    不能让两件各走各的。
  · saraemi.com/vtuber/2022/02/09/live2d_arm/ ——「関節パーツ自体を
    **肘の形に整形**する」：关节处要有一块随角度变形的料，不是两个圆。

本工具按这个思路补一块**褶布**：

  1. 在**离线**把上臂件、前臂件按挥手定稿姿势摆好（和 elbow_cover.py 同一组
     POSE 常数），量出两管之间真正漏出背景的那片区域（不是拿圆柱模型估的）。
  2. 这片区域往外胀 PAD px（塞到两根管子底下去），颜色用 `nearest_fill`
     从**两边袖子自己的像素**一圈圈推进来 —— 不是刷一块平色，
     所以明暗、笔触和左右两边是连着的。
  3. 把这块布反旋转回「**肘角平分线**」那个局部系，存成一个部件。

  4. 挂法是关键：新建一个组 `elbow_fold_?`，父组是上臂组，枢轴在肘，
     旋转 = **前臂局部旋转的一半**（ParamArm?B 的 scale 取前臂的一半）。
     这是 2D 骨骼里做膝/肘内侧料的标准做法：布夹在两根骨头中间，
     角度自然取平分线，前臂折多少它就跟一半，永远卡在两管之间。
  5. 层 136/137 —— **压在身体之上、上臂(140/141)与前臂(144/145)之下**。
     放最底下的好处：形状做得稍微大一点也不会露馅，多出来的部分
     全被两根管子自己盖住，只有真正缺布的那条缝会显出来。
  6. alpha 绑肘角：伸直(ParamArm?B=0) 完全透明，折到 ~折叠姿势才满。
     **静止画面一个像素都不动。**

幂等：写 arm_parts.json["elbow_gusset"]；签名没变就跳过（--force 强制重做）。

用法：
    python3 tools/elbow_gusset.py --character xiaoxun --form teen [--force]
    python3 tools/elbow_gusset.py --character xiaoxun --form teen --debug
        → logs/asset_qa/q50_gusset_dbg.png（摆位合成 + 红色缺口 + 绿色补布）
"""
import argparse
import io
import json
import math
import os

import numpy as np

from PIL import Image

# ★★★ Q51：从 136/137（垫在两根袖管**底下**）提到 150/151（压在**最上面**）。
#   垫在底下时，上臂自己的内侧描边和前臂近端的描边照样画在布的上面 ——
#   用户第五十一问截图里那条「肘关节的深色线」就是这两条描边并排躺在袖子中间。
#   官方做法本来就是把関節パーツ**压在上面**盖住接缝
#   （https://saraemi.com/vtuber/2022/02/09/live2d_arm/ 「関節パーツで整形」、
#    https://palkaloid.com/931/live2d-diary-2/ 「前腕と二の腕の切れ目が目立つ」）。
LAYER_GUSSET = {"l": 136, "r": 137}   # 褶布：填洞，必须垫在两根管子**底下**
LAYER_SEAM   = {"l": 150, "r": 151}   # 盖布：盖线，必须压在两根管子**之上**
SIG_V = 2
# —— 挥手定稿姿势（绝对角，离竖直向下）——和 elbow_cover.py / make_rig 同源 ——
POSE = {"r": (21.69, 153.73), "l": (-22.12, -152.17)}


def load(p):
    return Image.open(p).convert("RGBA")


def wrap180(d):
    while d > 180.0:
        d -= 360.0
    while d < -180.0:
        d += 360.0
    return d


def rot_fwd(dx, dy, deg):
    """按「离竖直向下的角」约定把向量转 +deg（和 atan2(dx,dy) 同号）。"""
    c, s = math.cos(math.radians(deg)), math.sin(math.radians(deg))
    return dx * c + dy * s, -dx * s + dy * c


def rot_inv(dx, dy, deg):
    c, s = math.cos(math.radians(deg)), math.sin(math.radians(deg))
    return dx * c - dy * s, dx * s + dy * c


def place_rot(canvas_shape, img, pos, center, deg, box):
    """把 img 绕 center（画布坐标，含 box 偏移前的绝对像素）转 deg 贴到画布上。

    返回 (rgb[H,W,3] float, alpha[H,W] float 0~1)，最近邻取样。
    """
    H, W = canvas_shape
    a = np.array(img).astype(np.float32)
    ih, iw = a.shape[0], a.shape[1]
    yy, xx = np.mgrid[0:H, 0:W]
    # 画布像素 → 绝对像素
    ax = xx + box[0]
    ay = yy + box[1]
    dx, dy = ax - center[0], ay - center[1]
    sx, sy = rot_inv(dx, dy, deg)
    sx = sx + center[0] - pos[0]
    sy = sy + center[1] - pos[1]
    ix = np.rint(sx).astype(np.int64)
    iy = np.rint(sy).astype(np.int64)
    ok = (ix >= 0) & (ix < iw) & (iy >= 0) & (iy < ih)
    ix = np.clip(ix, 0, iw - 1)
    iy = np.clip(iy, 0, ih - 1)
    rgb = a[iy, ix, :3]
    al = a[iy, ix, 3] / 255.0 * ok
    return rgb, al


def nearest_fill(rgb, known, target, rounds=64):
    out = rgb.astype(np.float32).copy()
    have = known.copy()
    todo = target & ~have
    for _ in range(rounds):
        if not todo.any():
            break
        acc = np.zeros(out.shape, np.float32)
        cnt = np.zeros(have.shape, np.float32)
        for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            sh = np.roll(np.roll(out, dy, 0), dx, 1)
            sm = np.roll(np.roll(have, dy, 0), dx, 1)
            acc += sh * sm[..., None]
            cnt += sm
        new = todo & (cnt > 0)
        if not new.any():
            break
        out[new] = acc[new] / cnt[new][:, None]
        have |= new
        todo &= ~new
    return out


def box_blur(rgb, mask, rounds):
    out = rgb.astype(np.float32).copy()
    for _ in range(int(rounds)):
        acc = out.copy()
        for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1),
                       (1, 1), (1, -1), (-1, 1), (-1, -1)):
            acc += np.roll(np.roll(out, dy, 0), dx, 1)
        acc /= 9.0
        out[mask] = acc[mask]
    return out


def dilate(mask, r):
    m = mask.copy()
    for _ in range(int(r)):
        m |= np.roll(m, 1, 0) | np.roll(m, -1, 0) | np.roll(m, 1, 1) | np.roll(m, -1, 1)
    return m


def dilate_dir(mask, ux, uy, n):
    """只往 (±ux,±uy) 这一个方向胀 n 像素（各向异性）。

    ★ 为什么不能各向同性地胀：补布的**远端**（靠袖口那一头）是靠袖口自己
    盖住的；往远端多胀一圈，肘角一旦偏离定稿姿势，袖口转走，那一圈就露在
    背景里（logs/asset_qa/q50_gusset_fade.png 的 f36/f40）。
    往**垂直于角平分线**的两侧胀才安全 —— 那两侧永远是两根袖管，管子宽
    34px，胀 6px 怎么偏都还在管子底下。
    """
    m = mask.copy()
    for t in range(1, int(n) + 1):
        dx, dy = int(round(ux * t)), int(round(uy * t))
        m |= np.roll(np.roll(mask, dy, 0), dx, 1)
        m |= np.roll(np.roll(mask, -dy, 0), -dx, 1)
    return m


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--character", required=True)
    ap.add_argument("--form", required=True)
    ap.add_argument("--pad", type=float, default=9.0,
                    help="缺口往外胀几像素（1x）—— 塞进两根管子底下的量")
    ap.add_argument("--feather", type=float, default=4.0,
                    help="边缘羽化几像素（1x）")
    ap.add_argument("--reach", type=float, default=1.06,
                    help="补布最远到肘→腕距离的几倍（袖口附近就该收住）")
    ap.add_argument("--blur", type=int, default=2)
    ap.add_argument("--tol", type=float, default=78.0,
                    help="色源容差（RGB 欧氏距离）：离袖身中位色多远还算布料")
    ap.add_argument("--tip-fade", type=float, default=13.0, dest="tip_fade",
                    help="远端（袖口那头）往回羽化几像素（1x）—— 定稿角度以外"
                         "那一两帧就算探出头，也只是一层很淡的雾，不是硬边三角")
    ap.add_argument("--shade", type=float, default=1.0,
                    help="折缝里的布比外面暗一点（乘这个系数，靠近缝底最暗）。"
                         "★ Q51 改回 1.0：0.94 那 6% 让这块布在袖子中间读成"
                         "「另一块绿色的东西」，用户第五十一问第一句就是冲它来的")
    # ★★★ Q51 新增：接缝描边。缺口（漏背景）只是病的一半，另一半是
    #   **两根管子各自的描边并排躺在袖子中间**，那才是用户指的「深色的线」。
    ap.add_argument("--seam", type=float, default=4.0,
                    help="接缝描边往外胀几像素（1x）—— 要比描边自己宽，"
                         "还要留出肘角抖动时的余量")
    ap.add_argument("--ink-lum", type=float, default=118.0, dest="ink_lum",
                    help="亮度低于这个值算描边（袖身中调 ~165、阴影 ~138、描边 ~60）")
    ap.add_argument("--seam-reach", type=float, default=2.0, dest="seam_reach",
                    help="接缝带最远到肘→腕距离的几倍（要够到两管贴合段的顶端）")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--debug", action="store_true")
    ap.add_argument("--quiet", action="store_true")
    a = ap.parse_args()

    base = os.path.join("characters", a.character, "forms", a.form)
    sprites = os.path.join(base, "sprites")
    apj = os.path.join(sprites, "arm_parts.json")
    if not os.path.exists(apj):
        print("[褶布] 没有 arm_parts.json，跳过")
        return 0
    with io.open(apj, encoding="utf-8") as f:
        meta = json.load(f)
    parts = {p["id"]: p for p in meta["parts"]}

    sig = {"v": SIG_V, "pad": a.pad, "feather": a.feather,
           "reach": a.reach, "blur": a.blur, "pose": POSE,
           "seam": a.seam, "ink_lum": a.ink_lum, "seam_reach": a.seam_reach,
           "shade": a.shade}
    if not a.force and meta.get("elbow_gusset", {}).get("sig") == sig:
        if not a.quiet:
            print("[褶布] 签名未变，跳过（--force 强制重做）")
        return 0

    K = 2                       # 全程 @2x
    done = {}
    dbg_tiles = []
    for side in ("l", "r"):
        up = parts.get("arm_%s_upper" % side)
        fo = parts.get("arm_%s_fore" % side)
        hp = parts.get("hand_%s" % side)
        if not up or not fo or not hp:
            continue
        sx, sy = up["pivot"]
        ex, ey = fo["pivot"]
        wx, wy = hp["pivot"]
        u0 = math.degrees(math.atan2(ex - sx, ey - sy))
        f0 = math.degrees(math.atan2(wx - ex, wy - ey))
        L = math.hypot(wx - ex, wy - ey)
        au, af = POSE[side]
        dU = au - u0                       # 上臂净转角
        dF = af - f0                       # 前臂净转角（绝对）
        dFl = dF - dU                      # 前臂**局部**转角（相对上臂组）
        th = dFl / 2.0                     # 褶布组转角 = 前臂局部的一半

        # —— 局部系里两条轴的方向（见文件头推导）——
        d_sh = wrap180((u0 + 180.0) - th)      # 朝肩
        d_wr = wrap180((f0 + dFl) - th)        # 朝腕
        bis = (d_sh + d_wr) / 2.0
        half = abs(wrap180(d_sh - d_wr)) / 2.0

        # —— 摆位合成（@2x，绝对像素坐标）——
        R = L * a.reach + 30.0
        box = (int((ex - R) * K), int((ey - R) * K),
               int((ex + R) * K) + 1, int((ey + R) * K) + 1)
        W, H = box[2] - box[0], box[3] - box[1]
        # 肩绕自己转 dU 之后肘跑到哪
        edx, edy = rot_fwd(ex - sx, ey - sy, dU)
        e2 = (sx * K + edx * K, sy * K + edy * K)     # @2x 绝对
        s2 = (sx * K, sy * K)

        layers = []
        for pt, ctr, deg in ((up, s2, dU), (fo, e2, dU + dFl), (hp, e2, dU + dFl)):
            img = load(os.path.join(base, pt["file"].replace(".png", "@2x.png")))
            p2 = (pt["pos"][0] * K, pt["pos"][1] * K)
            if pt is up:
                rgb, al = place_rot((H, W), img, p2, s2, dU, box)
            else:
                # 前臂/手：先跟上臂转 dU（绕肩），再绕**转后的肘** 转 dFl。
                # 两步合成一步：绕肩转 dU 等价于把件平移+旋转，这里直接用
                # 「绕肩 dU」的结果坐标系再绕 e2 转 dFl —— 等价于绕肩转 dU
                # 之后整体再绕 e2 转 dFl，正是骨骼层级的定义。
                rgb1, al1 = place_rot((H, W), img, p2, s2, dU, box)
                tmp = np.zeros((H, W, 4), np.uint8)
                tmp[..., :3] = rgb1.clip(0, 255).astype(np.uint8)
                tmp[..., 3] = (al1 * 255).astype(np.uint8)
                rgb, al = place_rot((H, W), Image.fromarray(tmp),
                                    (box[0], box[1]), e2, dFl, box)
            layers.append((rgb, al))

        comp_rgb = np.zeros((H, W, 3), np.float32)
        comp_a = np.zeros((H, W), np.float32)
        for rgb, al in layers:
            comp_rgb = comp_rgb * (1 - al)[..., None] + rgb * al[..., None]
            comp_a = comp_a + al * (1 - comp_a)
        solid = comp_a > 0.6

        # —— 真正漏背景的那片：扇区内 + 行/列都被夹住 ——
        ecx, ecy = e2[0] - box[0], e2[1] - box[1]
        yy, xx = np.mgrid[0:H, 0:W]
        rad = np.hypot(xx - ecx, yy - ecy)
        ang = np.degrees(np.arctan2(xx - ecx, yy - ecy))     # 同 atan2(dx,dy)
        bis_w = wrap180(bis + th + dU)       # 平分线在**画面**里的角
        dang = np.abs(((ang - bis_w + 180.0) % 360.0) - 180.0)
        sector = (dang <= half + 8.0) & (rad <= L * a.reach * K)

        hole = (~solid) & sector
        # 行/列双向夹住：左右都有料 且 上下都有料
        trap = np.zeros_like(hole)
        for r in range(H):
            idx = np.where(solid[r])[0]
            if len(idx) < 2:
                continue
            row = hole[r]
            cs = np.where(row)[0]
            if len(cs) == 0:
                continue
            keep = (cs > idx.min()) & (cs < idx.max())
            trap[r, cs[keep]] = True
        trap2 = np.zeros_like(hole)
        for c in range(W):
            idx = np.where(solid[:, c])[0]
            if len(idx) < 2:
                continue
            rs = np.where(hole[:, c])[0]
            if len(rs) == 0:
                continue
            keep = (rs > idx.min()) & (rs < idx.max())
            trap2[rs[keep], c] = True
        gap = (trap | trap2) & sector

        # ★★★ Q51：接缝描边 —— 用户真正指的那条「肘关节的深色线」。
        #   病理：上臂件的内侧描边 + 前臂件近端的描边，折起来之后**并排躺在
        #   袖子中间**。两条都是原画的外剪影线（2~3px 的深蓝），在伸直姿势里
        #   它们是合法的轮廓，一折起来就成了横穿袖子的双实线。
        #   参考图 characters/xiaoxun/design/pose_ref/wave_up.png 的折袖
        #   （logs/asset_qa/q51_ref_fold.png）：整只折袖是**一整块连续的布**，
        #   深色描边只在外剪影上，里面只有几笔很淡的褶皱影。
        #   判据（几何，不猜颜色长相）：
        #     ink      = 亮度 < ink_lum 的像素（描边）
        #     interior = 四周 r 圈之内全是袖料 ⇒ 不是外剪影，是**内部**的线
        #     seam     = ink & interior & 在两管夹角扇区内
        lum_c = comp_rgb.mean(2)

        def erode(m, r):
            o = m.copy()
            for _ in range(int(r)):
                o &= (np.roll(o, 1, 0) & np.roll(o, -1, 0)
                      & np.roll(o, 1, 1) & np.roll(o, -1, 1))
            return o

        # 「两根管子贴在一起的那一段」才算接缝。第一版只按角度扇区收口，
        # 结果**袖口罗纹的深蓝条**也在扇区里（它沿前臂轴，正好 dang≈half），
        # 被当成接缝盖掉了一半（logs/asset_qa/q51_seam_v1.png）。
        # 正确判据是分层的：离上臂件和前臂件**都**只有几像素的地方＝贴合段；
        # 袖口只挨着前臂，手件整个排除。
        up_m = layers[0][1] > 0.6
        fo_m = layers[1][1] > 0.6
        hd_m = layers[2][1] > 0.6
        # ★ 「布」= 袖料 + 缺口。缺口那片背景是**褶布件在底下填掉的**，
        #   所以贴着缺口的那两条描边同样是「袖子中间的线」，一样要盖。
        #   第二版只用 solid 当布，贴缺口的描边被 interior 判成外剪影放过了，
        #   结果两管分开的那一段线还在（logs/asset_qa/q51_seam_v3.png 红点）。
        cloth = solid | gap
        c = int(round(4.0 * K))
        contact = ((dilate(up_m, c) & dilate(fo_m, c))
                   | dilate(gap, int(round(6.0 * K)))) & ~dilate(hd_m, 2 * K)
        interior = erode(cloth, int(round(a.seam * K)) + 3)
        seam = (solid & (lum_c <= a.ink_lum) & interior & contact
                & (rad <= L * a.seam_reach * K) & (dang <= half + 22.0))
        # 胀开之后仍然**不许碰外剪影**：永远给剪影留 3px 不动
        seam_d = dilate(seam, int(round(a.seam * K))) & erode(cloth, 3)

        if gap.sum() < 60 and seam.sum() < 40:
            if not a.quiet:
                print("[褶布] %s 侧既没缺口（%d px）也没接缝线（%d px），跳过"
                      % (side, gap.sum(), seam.sum()))
            continue
        if not a.quiet:
            rs = rad[seam] / K if seam.any() else np.array([0.0])
            print("[褶布] %s 侧：缺口 %d px，接缝描边 %d px（离肘 %.0f~%.0f px，"
                  "胀开后 %d px）" % (side, gap.sum(), seam.sum(),
                                      rs.min(), rs.max(), seam_d.sum()))

        # 垂直于角平分线的两侧各胀 pad px（塞到两根管子底下），
        # 沿平分线方向（远端/近端）只胀 1px 封边。
        ux, uy = math.cos(math.radians(bis_w)), -math.sin(math.radians(bis_w))
        want = dilate(dilate_dir(gap, ux, uy, int(round(a.pad * K))), 1)
        want &= rad <= L * a.reach * K
        # ★ 不变式：**补布不许改剪影**。胀出来的部分只允许落在
        #   「缺口本身」或「已经被袖子盖住的地方」；凡是胀到背景里的
        #   （袖口外沿、手指缝）一律丢掉 —— 否则静止姿势边上会多出一块布。
        want &= (gap | solid)

        # —— 颜色：从两边袖子自己的像素推进来 ——
        #   ★ 只许用「袖身布料」当色源。第一版直接拿 solid 当色源，结果缺口上沿
        #   最近的不透明像素是**袖口罗纹的深蓝描边和白条**，补出来一块带条纹的
        #   深蓝补丁（logs/asset_qa/q50_gusset_on.png 第一版）。
        #   判据不猜「像不像袖子」，而是：先从前臂件内部取袖身中位色
        #   （掐掉最暗 18%＝描边、最亮 18%＝高光/白条），再按色距收口。
        near = solid & (rad <= (L * max(a.reach, a.seam_reach) + 20) * K)
        lum_all = comp_rgb.mean(2)
        if near.sum() > 200:
            lo, hi = np.percentile(lum_all[near], [18, 82])
            body = near & (lum_all >= lo) & (lum_all <= hi)
        else:
            body = near
        med = np.median(comp_rgb[body], axis=0) if body.sum() else np.array([120., 190., 195.])
        dist = np.sqrt(((comp_rgb - med[None, None, :]) ** 2).sum(2))
        # 描边(最暗)和袖口白条(最亮)**连同它们周围 3px** 一起剔除 —— 第二版只按
        # 色距收口，白条边上那圈过渡色还是被吸进来，补出来一片带横纹的浅色带。
        # ★★★ Q51：暗的那头只掐**描边**（绝对阈值 ink_lum），不要连袖子自己的
        #   阴影一起掐。第一版按 18 百分位掐，折缝周围全是阴影布、全被判成
        #   「色源不可用」，于是补布只能拿中调/亮调填 —— 补出来比周边袖子
        #   亮 5%（实测 ΔRGB=[9.9,9.5,7.4]，距离 15.6），在袖子中间就是
        #   用户说的「那块绿色的东西」。shade 旋钮救不了：ramp 的 mean(t)=0.914，
        #   拧到 0.84 也只把距离从 15.6 压到 8.0。
        bad = dilate(near & ((lum_all < a.ink_lum) | (lum_all > hi)), 3)
        known = near & ~bad & (dist <= a.tol)
        if known.sum() < 200:
            known = near & (dist <= a.tol)
        if known.sum() < 200:
            known = near
        flat = nearest_fill(comp_rgb, known, want)
        # 褶布是一片平整的布，不该有条纹：只在补布范围内多抹几轮
        flat = box_blur(flat, want, max(a.blur, 6))
        flat = box_blur(flat, want | known, a.blur)
        # —— 折缝底部的布在阴影里：越靠近两管交叉点越暗（线性到 1.0）——
        if a.shade < 0.999:
            t = np.clip(rad / max(1.0, L * a.reach * K), 0.0, 1.0)
            k = a.shade + (1.0 - a.shade) * t
            flat = flat * k[..., None]

        # —— 羽化：只在「不贴着袖子」的那一侧软化 ——
        fe = max(1.0, a.feather * K)
        inner = want.copy()
        for _ in range(int(fe)):
            inner &= (np.roll(inner, 1, 0) & np.roll(inner, -1, 0)
                      & np.roll(inner, 1, 1) & np.roll(inner, -1, 1))
        soft = want.astype(np.float32)
        edge = want & ~inner
        soft[edge] = 0.55
        soft = np.where(solid & want, 1.0, soft)      # 压在袖子底下的部分不羽化
        # —— 远端软收 ——
        #   ★ 只收「胀出去的余量」，**缺口本身一律不透明**。第一版连缺口一起
        #   收，袖口下面那条真缺口变成 35% 半透明，定稿姿势上看就是一条
        #   发白的雾边（logs/asset_qa/q50_gusset_fade.png 第二轮 f72）。
        #   余量平时藏在袖子底下，偏角时探出来也只是一层淡雾。
        if a.tip_fade > 0.5 and want.any():
            r_far = float(rad[want].max())
            ramp = np.clip((r_far - rad) / max(1.0, a.tip_fade * K), 0.0, 1.0)
            marg = want & ~gap
            soft = np.where(marg, soft * (0.30 + 0.70 * ramp), soft)

        # ★★★ Q51：**接缝盖布**是另一件，层不一样，不能和褶布混在一张图里。
        #   褶布填的是「漏背景的洞」，只有从洞里才看得见 ⇒ 必须垫在两根管子
        #   **底下**（层 136/137），放上面就会把袖口、剪影一起糊掉
        #   （logs/asset_qa/q51_seam_v2.png 整片蓝雾）。
        #   盖布盖的是「横躺在袖子中间的描边」，只有压在两根管子**上面**
        #   才盖得住（层 150/151）。两件分工、各归各层。
        fe2 = max(1, int(round(a.feather * K)))
        soft2 = np.zeros((H, W), np.float32)
        prev = seam.copy()
        soft2[prev] = 1.0
        for i in range(1, fe2 + 1):
            nxt = dilate(prev, 1) & seam_d
            ring = nxt & ~prev
            soft2[ring] = 1.0 - i / float(fe2 + 1)
            prev = nxt
        want2 = seam_d & (soft2 > 0.004)
        # 顶端渐隐，别让盖布戛然而止、露出半截线头
        if a.tip_fade > 0.5 and seam.any():
            r_far2 = float(rad[seam].max())
            ramp2 = np.clip((r_far2 + 2 * K - rad) / max(1.0, a.tip_fade * K), 0.0, 1.0)
            soft2 = soft2 * ramp2
        flat2 = nearest_fill(comp_rgb, known & ~dilate(seam, 1), want2)
        flat2 = box_blur(flat2, want2, max(1, a.blur))

        posed = np.zeros((H, W, 4), np.float32)
        posed[..., :3] = flat
        posed[..., 3] = soft * 255.0 * want
        posed2 = np.zeros((H, W, 4), np.float32)
        posed2[..., :3] = flat2
        posed2[..., 3] = soft2 * 255.0 * want2

        # —— 反旋转回「角平分线」局部系：p_local = R⁻¹(p_posed − e2) + e_rest ——
        netdeg = dU + th
        er = (ex * K, ey * K)
        Rl = L * max(a.reach, a.seam_reach) + 24.0
        lbox = (int((ex - Rl) * K), int((ey - Rl) * K),
                int((ex + Rl) * K) + 1, int((ey + Rl) * K) + 1)
        LW, LH = lbox[2] - lbox[0], lbox[3] - lbox[1]
        yy2, xx2 = np.mgrid[0:LH, 0:LW]
        lx = xx2 + lbox[0] - er[0]
        ly = yy2 + lbox[1] - er[1]
        px, py = rot_fwd(lx, ly, netdeg)
        px = np.rint(px + e2[0] - box[0]).astype(np.int64)
        py = np.rint(py + e2[1] - box[1]).astype(np.int64)
        ok = (px >= 0) & (px < W) & (py >= 0) & (py < H)
        px = np.clip(px, 0, W - 1)
        py = np.clip(py, 0, H - 1)
        def emit(src, pid, layer, note):
            """把摆位图反旋转回局部系、切件、写盘、登记到 arm_parts.json。"""
            loc = src[py, px].copy()
            loc[..., 3] *= ok
            out = loc.clip(0, 255).astype(np.uint8)
            ys, xs = np.where(out[..., 3] > 2)
            if len(ys) == 0:
                return None
            x0, x1 = int(xs.min()), int(xs.max()) + 1
            y0, y1 = int(ys.min()), int(ys.max()) + 1
            x0 -= (x0 + lbox[0]) % K
            y0 -= (y0 + lbox[1]) % K
            x1 += (-(x1 + lbox[0])) % K
            y1 += (-(y1 + lbox[1])) % K
            crop = Image.fromarray(out).crop((x0, y0, x1, y1))
            crop.save(os.path.join(sprites, pid + "@2x.png"))
            crop.resize((crop.width // K, crop.height // K),
                        Image.LANCZOS).save(os.path.join(sprites, pid + ".png"))
            entry = {"id": pid, "file": "sprites/%s.png" % pid,
                     "group": "elbow_fold_%s" % side, "layer": layer,
                     "pos": [(x0 + lbox[0]) // K, (y0 + lbox[1]) // K],
                     "size": [crop.width // K, crop.height // K],
                     "pivot": [ex, ey], "note": note}
            for i, p in enumerate(meta["parts"]):
                if p["id"] == pid:
                    meta["parts"][i] = entry
                    break
            else:
                meta["parts"].append(entry)
            return entry

        crop = emit(posed, "arm_%s_gusset" % side, LAYER_GUSSET[side],
                    "肘内侧褶布（Q50）：参考图 wave_up.png 的折臂是**一整块连续的布**，"
                    "我们两根管子之间会漏出背景三角（logs/asset_qa/q50_notch_probe.png "
                    "红色 705px）。这块布按定稿姿势量出缺口、用两边袖子自己的像素填出来，"
                    "挂在 elbow_fold_? 组（转角 = 前臂的一半 = 角平分线）、"
                    "层 136/137 垫在两根管子**底下**，伸直时 alpha=0。")
        if crop is None:
            continue
        seam_entry = emit(posed2, "arm_%s_seam" % side, LAYER_SEAM[side],
                          "肘接缝盖布（Q51）：折起来之后，上臂件的内侧描边和前臂件"
                          "近端的描边**并排躺在袖子中间**，读起来就是用户第五十一问"
                          "截图里那条「肘关节的深色线」。参考图 wave_up.png 的折袖"
                          "里面只有几笔淡褶皱、深色线只在外剪影上。这件按定稿姿势"
                          "找出「被袖料包住的描边像素」（两管贴合段内，排除袖口罗纹"
                          "和手），用两边袖子自己的颜色盖掉，层 150/151 压在"
                          "两根管子**之上**，外剪影永远留 3px 不碰，伸直时 alpha=0。")
        done[side] = {"gap_px_2x": int(gap.sum()), "fill_px_2x": int(want.sum()),
                      "seam_px_2x": int(seam.sum()),
                      "seam_fill_px_2x": int(want2.sum()),
                      "seam_r_px": [round(float(rad[seam].min()) / K, 1),
                                    round(float(rad[seam].max()) / K, 1)]
                      if seam.any() else [0, 0],
                      "half_deg": round(half, 2), "bis_deg": round(bis, 2),
                      "theta_half": round(th, 2), "net_deg": round(netdeg, 2),
                      "size": crop["size"], "pos": crop["pos"],
                      "seam_size": seam_entry["size"] if seam_entry else None,
                      "seam_pos": seam_entry["pos"] if seam_entry else None}
        if not a.quiet:
            print("[褶布] %s 侧：缺口 %d px → 褶布 %d px @%s%s；"
                  "接缝描边 %d px（离肘 %.0f~%.0f px）→ 盖布 %d px @%s%s"
                  % (side, gap.sum(), want.sum(), crop["size"], crop["pos"],
                     seam.sum(), rad[seam].min() / K if seam.any() else 0,
                     rad[seam].max() / K if seam.any() else 0, want2.sum(),
                     seam_entry["size"] if seam_entry else "-",
                     seam_entry["pos"] if seam_entry else ""))

        if a.debug:
            vis = np.zeros((H, W, 3), np.uint8)
            vis[...] = 255
            vis = (vis * (1 - comp_a)[..., None]
                   + comp_rgb * comp_a[..., None]).astype(np.uint8)
            vis[want] = (0.45 * vis[want] + 0.55 * np.array([0, 200, 0])).astype(np.uint8)
            vis[gap] = [255, 0, 0]
            vis[want2] = (0.35 * vis[want2] + 0.65 * np.array([255, 160, 0])).astype(np.uint8)
            vis[seam] = [255, 0, 255]
            dbg_tiles.append(Image.fromarray(vis))

    if done:
        meta["elbow_gusset"] = {"sig": sig, "sides": done}
        with io.open(apj, "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)
            f.write("\n")
        if not a.quiet:
            print("[褶布] 写回 %s" % apj)
    if a.debug and dbg_tiles:
        os.makedirs("logs/asset_qa", exist_ok=True)
        w = sum(t.width for t in dbg_tiles) + 8 * (len(dbg_tiles) + 1)
        h = max(t.height for t in dbg_tiles) + 16
        sheet = Image.new("RGB", (w, h), (24, 24, 24))
        x = 8
        for t in dbg_tiles:
            sheet.paste(t, (x, 8))
            x += t.width + 8
        sheet.save("logs/asset_qa/q50_gusset_dbg.png")
        print("[褶布] 调试图 logs/asset_qa/q50_gusset_dbg.png")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
