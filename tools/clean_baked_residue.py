#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""clean_baked_residue.py —— 把烘进**别的部件**里的头发/衣领残留擦掉

★ 这个工具修的是一个藏了很多轮的真 bug（2026-10-18 用户第十三问点出来的
  「脸没做干净，有错误残留」，以及第十一问的「两处头发变形眼睛旁边的」）。

怎么回事
--------
眼部差分件（eye_?_base / _wide / _closed / _smile / _pain）是从**整张脸**上
按矩形切下来的补片。矩形一框就把眼睛**外侧的那缕鬓发连同发梢的蓝色**一起
框进去了 —— eye_l_base 里有 41.7% 的像素是头发。

这些补片的层号是 212~234，**压在 seg_head(180) 之上**。于是：

* 发型切到 long / twin / pony，我们把 hair_side_l/r 收起来了，
  **眼睛旁边却还留着两缕从补片里渗出来的头发**，一直垂到下巴 —— 就是用户
  截图里下颌两侧那两撮蓝色碎发。
* 更糟的是这两缕头发跟着**眼睛的形变器**动：眨一次眼，脸颊旁边的头发跟着
  抽一下。用户第十一问说的「两处头发变形眼睛旁边的」就是它，当时我误判成
  鬓发挂件的问题，改错了地方。

做法
----
不按矩形裁（裁了会把眼睛周围的皮肤和阴影一起裁掉，补片边缘就露马脚），
而是**按颜色挑头发**，并且只在**远离眼球**的地方挑：

* 头发是淡紫/蓝梢 ⇒ 蓝通道明显高于红通道（B − R > 4）；
  皮肤是奶油粉 ⇒ B − R ≈ −50；眼白 B − R ≈ 1；睫毛是暗褐 ⇒ 负的。
* 虹膜也是蓝的（B − R ≈ +140），所以用一个以**虹膜中心**为心的椭圆把眼睛
  整个保护起来，椭圆外才开始擦，边界上做软过渡。

擦掉之后露出来的是 seg_head 上**已经补画过**的头皮/鬓发底色
（tools/make_scalp_patch.py 的产物），或者 bob 档本来就盖在上面的
hair_side_l/r —— 两种情况都接得上。

同一个毛病还有另外两处（都是用户第十三问截图里下巴两侧那两撮蓝色碎发）
--------------------------------------------------------------------
* **seg_torso 的肩上烘着鲍勃头的发梢。** 身体分段是沿着外轮廓切的，原画里
  垂到肩上的那两缕侧发**连同蓝色发梢**一起留在了躯干件上（实测 5155 像素）。
  bob 档看不出来 —— hair_side_l/r(245·246) 正好盖在上面；一旦收起鬓发，
  它们就从下颌两侧支棱出来。擦法同上：按颜色挑（头发 B≥G 且 B≫R，
  青色衣领 B<G，所以分得开），擦完的洞如果四周还是衣服就就近填，
  在轮廓外的直接变透明。
* **seg_head 的下边缘挂着一条锯齿状的衣领。** 头件层 180 压在躯干 100 之上，
  于是这条**带台阶的烂边**盖在了躯干那条干净的衣领上。更要命的是它跟着
  **头部**走：一低头，衣领就跟着头动。按「脖子以下只留皮肤」清掉
  （皮肤 R−B>22，青色衣领/白衬衫都是负的或接近 0，分得干净）。

排在流水线哪一步
----------------
必须排在所有生成/改写眼部件的工具**之后**（make_eye_parts、
make_eye_closed_parts 的四个 variant、make_eyeline_parts），也要排在
make_body_parts / make_arm_parts / make_scalp_patch **之后**（它们会重写
seg_head / seg_torso），并且排在**高清化之前** —— @2x 是从 1× 升采样来的，
顺序反了 @2x 就是脏的。工具本身是幂等的：@2x 已经存在时也会一并洗一遍。

用法：python3 tools/clean_baked_residue.py --character xiaoxun --form teen
"""
import argparse
import json
import os
import sys

try:
    import numpy as np
    from PIL import Image, ImageFilter
except ImportError:  # pragma: no cover
    print("需要 pillow + numpy：python3 -m venv ~/.imgenv && ~/.imgenv/bin/pip install pillow numpy")
    sys.exit(1)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 补片坐标 → 画布坐标。make_rig 里是同一个常数（实测 rig.pos − json.pos 恒为此值）
PATCH_TO_CANVAS = (200, 68)

# 眼球保护椭圆的**半轴**（画布 1× 像素）。
#
# ★ 2026-10-19 修正：原来写的是 40×35，**把全尺寸当成半轴了，大了 2.5 倍**。
#   注释说"眼睛连睫毛大约 45×40"是**全尺寸**，半轴该是 ~23×20。
#   40×35 的椭圆竖直覆盖 70px，而补片本身只有 68px 高 ——
#   等于整片都在保护区里，于是这个清洁器**一根头发都没擦掉**：
#   实测 eye_l_base 里仍有 31% 的像素满足它自己的发色判据 B−R>4。
#
#   后果直到发型轴做出来才暴露：这些烘进眼部补片的头发在层 212~234，
#   短发档被 hair_side_l/r(245·246) 正好盖住，看不出来；
#   long/twin/pony 三档把鬓发一藏，它们就全露出来，
#   而且跟着眼睛的形变器动 —— 就是用户第十八问说的"所有头发都有杂毛"。
#
#   现在的值按**实测**定：眼白主块 31×28（eye_l）/ 34×27（eye_r），
#   半轴 16×14；取 20×17 给睫毛留余量，羽化 6 ⇒ 实际保护到 ~52×44（全尺寸），
#   眼睛连睫毛完全罩住，再往外的鬓发全部放开。
KEEP_AX, KEEP_AY = 20.0, 17.0
KEEP_FEATHER = 6.0      # 椭圆外多少像素内从"全保护"渐变到"可擦"
# B−R 在这段区间里从"不是头发"渐变到"是头发"。
# ★ 2026-10-19 修正：原来是 4→14，**太宽**。这里的鬓发实测是偏灰的淡紫
#   (206,195,214)，B−R 只有 8 ⇒ hairness 只有 0.4 ⇒ 只擦掉四成不透明度，
#   **留下一层半透明的头发残影**。渲染出来就是脸侧和下巴那一圈白雾
#   （用户第十八问截图里最显眼的那个）。半擦比不擦更糟：不擦至少是实心头发，
#   半擦是一层雾。
#   皮肤 B−R ≈ −50、眼白 ≈ 0，离 2 还远；眼球本身有保护椭圆兜着，
#   所以把上界压到 7 是安全的 —— B−R≥7 的一律整个擦掉，不留残影。
HAIR_T0, HAIR_T1 = 2.0, 7.0


def _load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def iris_centers(sdir):
    """两只眼睛虹膜中心的画布坐标（1×）。"""
    ep = _load(os.path.join(sdir, "eye_parts.json"))
    out = {}
    for e in ep["eyes"]:
        px, py = e["patch_pos"]
        ix, iy = e["iris_center"]
        out[e["side"]] = (px + ix + PATCH_TO_CANVAS[0], py + iy + PATCH_TO_CANVAS[1])
    return out


def collect_targets(sdir):
    """[(文件名, 补片左上角画布坐标)]，只收**真的框进了头发**的那些件。"""
    t = []
    ep = _load(os.path.join(sdir, "eye_parts.json"))
    for e in ep["eyes"]:
        px, py = e["patch_pos"]
        t.append((e["base"], (px + PATCH_TO_CANVAS[0], py + PATCH_TO_CANVAS[1])))
    for name in ("eye_wide_parts", "eye_closed_parts", "eye_smile_parts", "eye_pain_parts"):
        p = os.path.join(sdir, name + ".json")
        if not os.path.exists(p):
            continue
        for e in _load(p)["eyes"]:
            px, py = e["pos"]
            t.append((e["file"], (px + PATCH_TO_CANVAS[0], py + PATCH_TO_CANVAS[1])))
    return t


def clean(path, origin, irises, scale=1):
    """擦掉一张补片里的头发像素。origin/irises 都是 1× 画布坐标。"""
    im = Image.open(path).convert("RGBA")
    a = np.asarray(im).astype(np.float32)
    h, w = a.shape[:2]
    R, G, B, A = a[..., 0], a[..., 1], a[..., 2], a[..., 3]

    xs = (np.arange(w, dtype=np.float32) / scale) + origin[0]
    ys = (np.arange(h, dtype=np.float32) / scale) + origin[1]
    X = xs[None, :]
    Y = ys[:, None]

    # 眼球保护：两个椭圆取并集，边界软过渡
    keep = np.zeros((h, w), np.float32)
    for cx, cy in irises.values():
        d = np.sqrt(((X - cx) / KEEP_AX) ** 2 + ((Y - cy) / KEEP_AY) ** 2)
        # d<=1 完全保护；d 到 1+feather/KEEP_AX 之间线性放开
        soft = np.clip((1.0 + KEEP_FEATHER / KEEP_AX - d) / (KEEP_FEATHER / KEEP_AX), 0.0, 1.0)
        keep = np.maximum(keep, soft)

    hairness = np.clip((B - R - HAIR_T0) / (HAIR_T1 - HAIR_T0), 0.0, 1.0)
    cut = hairness * (1.0 - keep)
    newA = A * (1.0 - cut)

    removed = float((A > 60).sum() and ((A > 60) & (newA <= 60)).sum())
    a[..., 3] = newA
    Image.fromarray(a.clip(0, 255).astype(np.uint8), "RGBA").save(path)
    return int(removed), int((A > 60).sum())


# ── 躯干件肩上的发梢 / 头件下边缘的烂衣领 ──────────────────────────────
# 躯干件在画布上的左上角（make_body_parts 的产物；这里按 rig 的实测值写死，
# 和 PATCH_TO_CANVAS 一样属于"分段几何"常量，变了闸门会抓）
TEAL_HUE = 0.72          # 青衣领 vs 蓝发梢的色相分界（见 _hair_mask）
TEAL_LUMA = 150.0        # 同上，衣领那条青还必须够暗才算衣领
TORSO_ORIGIN = (282, 308)
HEAD_ORIGIN = (299, 68)
TORSO_HAIR_MAX_Y = 80       # 只在躯干件顶部这么多行里找发梢（再往下是衣服本身）
TORSO_HAIR_SEED_Y = 42      # 这条线以上一定是头发；往下只认**连着它**的部分
TORSO_HAIR_GROW = 12        # 测地膨胀步数 = 发梢最多能往下延多少像素
HEAD_SKIN_CUT_Y = 334       # 画布坐标：这条线以下的头件只留皮肤
HEAD_SKIN_RB = 22           # R−B 大于它算皮肤（青领/白衬衫都远低于此）


def _box_blur(img, r):
    """半径 r 的均值模糊（跑两遍近似高斯）。Pillow 的 GaussianBlur 不吃 float 图。"""
    out = img.astype(np.float32)
    for _ in range(2):
        pad = np.pad(out, ((r, r), (0, 0)), mode="edge")
        cs = np.cumsum(pad, axis=0)
        out = (np.vstack([cs[2 * r:], ]) - np.vstack([np.zeros((1, cs.shape[1]), np.float32), cs[:-2 * r - 1]])) / (2 * r + 1)
        pad = np.pad(out, ((0, 0), (r, r)), mode="edge")
        cs = np.cumsum(pad, axis=1)
        out = (cs[:, 2 * r:] - np.hstack([np.zeros((cs.shape[0], 1), np.float32), cs[:, :-2 * r - 1]])) / (2 * r + 1)
    return out


def _nearest_fill(rgb, keep, rounds=64):
    """最近邻补洞：洞的边界一圈一圈往里长，每个像素抄**已知邻居**的平均。

    比"多尺度模糊"强在不会把青色衣领和白衬衫糊成一摊米灰色 —— 色块边界留得住。
    前提是先把发梢的**深色描边**也算进洞里（见 clean_torso），
    否则那圈黑线会被一路抄进衣领，补出几道黑痕。
    """
    out = rgb.astype(np.float32).copy()
    k = keep.astype(np.float32)
    for _ in range(rounds):
        pad = np.pad(k, 1)
        cnt = (pad[:-2, 1:-1] + pad[2:, 1:-1] + pad[1:-1, :-2] + pad[1:-1, 2:] +
               pad[:-2, :-2] + pad[:-2, 2:] + pad[2:, :-2] + pad[2:, 2:])
        fillable = (k < 0.5) & (cnt >= 1)
        if not fillable.any():
            break
        for ch in range(3):
            p = np.pad(out[..., ch] * k, 1)
            acc = (p[:-2, 1:-1] + p[2:, 1:-1] + p[1:-1, :-2] + p[1:-1, 2:] +
                   p[:-2, :-2] + p[:-2, 2:] + p[2:, :-2] + p[2:, 2:])
            out[..., ch] = np.where(fillable, acc / np.maximum(cnt, 1), out[..., ch])
        k = np.where(fillable, 1.0, k)
    return out, k


def _soft_inpaint(rgb, keep, radii=(4, 10, 24, 56)):
    """多尺度加权模糊补洞：洞里填的是周围**保留像素**的柔和平均。

    试过两种更"聪明"的补法，都更难看：
      · 八邻域迭代平均 —— 把头发的深色描边也平均进来，补出一团黑斑；
      · 顺着列从下往上抄 —— 抄出一条条竖白道（下面正好是白衬衫）。
    这一片本来就在下颌阴影里、而且大半被头发压着，**柔和过渡**比"猜对花纹"
    重要得多。
    """
    c = (rgb * keep[..., None]).astype(np.float32)
    w = keep.astype(np.float32)
    out = rgb.astype(np.float32).copy()
    done = keep.copy()
    for r in radii:
        if done.all():
            break
        cb = np.dstack([_box_blur(c[..., i], r) for i in range(3)])
        wb = _box_blur(w, r)
        ok = (~done) & (wb > 0.05)
        if ok.any():
            val = cb / np.maximum(wb, 1e-6)[..., None]
            out = np.where(ok[..., None], val, out)
            done = done | ok
    return out, done.astype(np.float32)


def _dilate(m):
    p = np.pad(m, 1)
    return (p[:-2, 1:-1] | p[2:, 1:-1] | p[1:-1, :-2] | p[1:-1, 2:] |
            p[:-2, :-2] | p[:-2, 2:] | p[2:, :-2] | p[2:, 2:] | m)


def _erode1(m, scale=1):
    """腐蚀 scale 像素（用来打断 1px 宽的细线，团状区域只掉一圈）。"""
    im = Image.fromarray((m * 255).astype(np.uint8))
    for _ in range(max(1, int(scale))):
        im = im.filter(ImageFilter.MinFilter(3))
    return np.asarray(im) > 128


def _regrow(seed, host, rounds):
    """把 seed 在 host 内部测地膨胀回去。"""
    g = seed.copy()
    for _ in range(rounds):
        g = _dilate(g) & host
    return g


def _hair_mask(a, scale, max_y_sprite=None, seed_y_sprite=None, grow=12):
    """按颜色 + 测地膨胀框出'烘进来的头发'。

    ★ 纯颜色阈值分不开蓝发梢和深青衣领内沿（B−G 13 vs 29、R−G −75 vs −37 重叠），
      所以先用颜色取基底，再从'一定是头发'的那一片做测地膨胀 —— 长条形的衣领线
      连不进来。这条是 2026-10-18 第十三问调了一整轮才摸出来的。
    """
    R, G, B, A = a[..., 0], a[..., 1], a[..., 2], a[..., 3]
    sat = a[..., :3].max(axis=2) - a[..., :3].min(axis=2)
    base = (A > 40) & (B - G >= 8) & (B - R > 10) & (sat > 16) & (B > 150)
    if max_y_sprite is not None:
        base[int(max_y_sprite * scale):, :] = False
    if seed_y_sprite is None:
        hair = base
    else:
        seed = base.copy()
        seed[int(seed_y_sprite * scale):, :] = False
        hair = seed
        for _ in range(grow * scale):
            hair = _dilate(hair) & base
        # 铁证是头发的蓝（B 比 G 高 20 以上）直接收 ——
        # 不这么补一刀的话，肩角上会剩几片没和种子连通的碎发。
        strong = (A > 40) & (B - G > 20) & (B - R > 40)
        if max_y_sprite is not None:
            strong[int(max_y_sprite * scale):, :] = False
        # ★ 2026-10-18 补第二刀：上面那句原注释写着"青领的 B−G 是负的，不可能
        #   命中"—— 对**亮面**青领 (107,182,179) 成立，对衣领**内沿的深青**
        #   (101,142,155) 不成立，它的 B−G 有 +24，整条领口上缘 98 个像素全被
        #   当成头发擦掉了（"无损切分"少 69 像素、发梢甩动露底 67 像素，都是它）。
        #   颜色再怎么调都分不开（实测 B−G / B−R / G−R 三项都重叠），**形状能**：
        #   衣领内沿是一条 1px 宽的线，碎发是团。先腐蚀 1px 把线打断，再在
        #   strong 内部长回来 —— 实测领口带命中 98→0，发梢带 4018→3771（留住 94%）。
        #   这和本函数开头那条"长条形的衣领线连不进来"是同一个思路。
        strong = _regrow(_erode1(strong, scale), strong, 4 * scale)
        hair = hair | strong
    for _ in range(2 * scale):
        hair = _dilate(hair) & (A > 0)
    # 发丝的**深色描边**和淡到不够判据的抗锯齿边：颜色上不算头发，
    # 留着会被补洞一路抄进衣领，补出几道黑痕
    luma = 0.299 * R + 0.587 * G + 0.114 * B
    near = hair.copy()
    for _ in range(3 * scale):
        near = _dilate(near)
    # ★ 必须把**青色衣领**排除在外（G−R 大）：衣领自己的深色描边也满足 luma<150，
    #   连它一起吃掉的话，补洞会把旁边的皮肤色一路抄过来，在领口糊出几条土灰竖条
    #   （2026-10-18 实测过，见 /tmp/torso_now.png 那一版）。
    not_teal = (G - R) <= 20
    edge = near & (A > 0) & not_teal & (B >= R - 4) & \
        ((luma < 150) | ((B - G >= 3) & (B - R > 4)))
    # ★ 最后一道：按**色相**把青衣领整个否掉。
    #   蓝发梢和深青领在 B−G / B−R / G−R 上都重叠，但 (G−R)/(B−R) 这一项
    #   （= 色相在青↔蓝之间的位置）分得很开 —— 实测衣领上缘 900 个像素中位
    #   0.839（p05 0.741），肩上发梢 5920 个像素中位 0.473（p95 0.763）。
    #   淡紫发身是 0.0、蓝发梢 0.51、深青领 0.84，闸设在 0.72。
    #   少了这一刀，领口上缘那条深青会顺着测地膨胀被当成头发连走，
    #   擦完在两个肩角上各留一道 13px 的缺口。
    #   ★ 光比色相不行，还得**同时暗**：发梢最亮的那一圈青蓝（luma ~202）
    #     色相也在 0.72 以上，只卡色相会把脖子两侧一大片发丝全留下来
    #     （实测擦除量 3376→1930，肩上残着一圈青蓝碎发）。衣领那条深青
    #     luma 中位 124 / p90 137，所以再加一刀 luma < 150：
    #     衣领保住 851/900，发梢只误放 85/5920（1.4%）。
    teal = (B > R) & ((G - R) > TEAL_HUE * (B - R)) & (luma < TEAL_LUMA)
    return (hair | edge) & (~teal)


def _save_with_2x(path1, before, after, changed):
    """写 1× 并**由 1× 派生 @2x**，而不是在 @2x 上把同一套算法再跑一遍。

    ★ 2026-10-18 实测教训：同样的阈值跑在 @2x 上结果完全不同 —— @2x 的抗锯齿
      过渡带宽一倍，落进\"淡到不够判据的发丝边缘\"那条的像素多得多，于是衣领被
      啃掉一大片、补洞把暗部抄上来，1× 看着干净、@2x 一塌糊涂（而渲染用的正是
      @2x）。两套分辨率各判各的 = 两个不同的结果，这本身就是 bug。
      现在只在 1× 上做判定，@2x 仅在**被改动的那一小片**里用 1× 的结果覆盖，
      其余像素原封不动 —— 高清细节该留的都留着。
    """
    Image.fromarray(after.clip(0, 255).astype(np.uint8), "RGBA").save(path1)
    p2 = path1.replace(".png", "@2x.png")
    if not os.path.exists(p2):
        return 0, 0
    big = np.asarray(Image.open(p2).convert("RGBA")).astype(np.float32)
    h2, w2 = big.shape[:2]
    up = np.asarray(Image.fromarray(after.clip(0, 255).astype(np.uint8), "RGBA")
                    .resize((w2, h2), Image.LANCZOS)).astype(np.float32)
    m = Image.fromarray((changed.astype(np.uint8) * 255), "L").resize(
        (w2, h2), Image.BILINEAR).filter(ImageFilter.MaxFilter(3))
    mk = (np.asarray(m).astype(np.float32) / 255.0)[..., None]
    mk = np.clip(mk * 1.6, 0.0, 1.0)
    out2 = big * (1.0 - mk) + up * mk
    before2 = big[..., 3]
    Image.fromarray(out2.clip(0, 255).astype(np.uint8), "RGBA").save(p2)
    return int(((before2 > 60) & (out2[..., 3] <= 60)).sum()), int((before2 > 60).sum())


def torso_masks(ta, scale, deep=None, arm_void=None):
    """躯干件要擦掉 / 要补回的两张掩码（连同补色后的 RGB）。

    单独拆成函数，是因为 **tools/make_wardrobe.py 要用同一套判据**：换装重绘
    素材是照着没清理过的躯干画的，肩上一样烘着发梢。两边各算各的就会差出
    几千像素，剪影闸会误判成\"身体错位\"。
    """
    t_hair = _hair_mask(ta, scale, TORSO_HAIR_MAX_Y, TORSO_HAIR_SEED_Y,
                        TORSO_HAIR_GROW)
    # 浮在衣服上方、和衣服主体不连通的深色碎屑一并清掉
    solid = ta[..., 3] > 40
    strip = int(TORSO_HAIR_MAX_Y * scale)
    grown = solid.copy()
    grown[:strip, :] = False
    for _ in range(strip + 40):
        nxt = _dilate(grown) & solid
        if nxt.sum() == grown.sum():
            break
        grown = nxt
    islands = solid & (~grown)
    islands[strip:, :] = False
    t_hair = t_hair | islands

    trgb = ta[..., :3].copy()
    newTA = np.where(t_hair, 0.0, ta[..., 3])
    A = ta[..., 3]
    # 哪些洞该补回来？—— **四面都被衣服围住**的才补。
    # 试过"这一列衣服从哪行开始、以下都补"，结果脖子左右两侧那片飘在身体轮廓
    # **外面**的头发也被判成要补，补出来是两坨蓝灰斑（用户截图里下巴旁那两块）。
    # 四向封闭判据能把"真洞"（衣领里被头发压住的）和"身体外面"干净分开。
    g = (A > 40) & (~t_hair)
    up = np.maximum.accumulate(g, axis=0)
    down = np.maximum.accumulate(g[::-1], axis=0)[::-1]
    lf = np.maximum.accumulate(g, axis=1)
    rt = np.maximum.accumulate(g[:, ::-1], axis=1)[:, ::-1]
    target = g | (t_hair & up & down & lf & rt)
    if deep is not None:
        # ★ 还要补\"虽然不被衣服四面围住、但确实在**身体剪影深处**\"的那些。
        #   肩膀外缘那一片发梢，原画里一半压在衣服上、一半探到衣服轮廓外面。
        #   四向封闭判据只认得压在衣服上的那一半，剩下的擦完就是透明。
        #   静止时看不出来（侧发正盖着），**头发一摆就露底** ——
        #   check_assets 的「头发摆动不露底」实测 +17 像素，正好卡在上限 20 上。
        #   判据和那条闸自己用的一样：body_full 剪影往里腐蚀 4px（MinFilter(9)，
        #   和 check_assets.py 里数"深处空洞"用的那句一字不差），
        #   里面的一律补成衣服色；外缘那一圈不补（那里原画本来就是背景，
        #   头发摆开**应该**露出背景）。
        target = target | (t_hair & deep)
    # 取色只从**实心**像素取：alpha 1~40 那圈是抠像留下的半透明毛边，
    # 颜色不可信（实测抄到过 (191,127,191) 的洋红毛边，补出 5 个洋红点）。
    rgbf, filled = _nearest_fill(trgb, newTA > 40.0)
    hole = t_hair & (newTA < 40) & target & (filled > 0.5)

    # ★ 收尾之一：**本来就被挖空、而且四面被躯干围死**的洞，一律补实。
    #   第 15 步把侧发从躯干的重叠带里挖了出去（4418 像素，那块归
    #   hair_side_l/r 管）。挖出来的缺口原本一路通到躯干件的上边沿，
    #   不算\"内部空洞\"；上面那条 deep 补色把缺口**上沿**堵上之后，
    #   它就变成了一个封闭的洞 —— check_assets 的「袖下躯干无新窟窿」
    #   实测 176 像素（上限 60）。
    #   补它既对又划算：Live2D 官方 PSD 教程说被遮住的部分必须描き足し
    #   （docs.live2d.com/en/cubism-editor-tutorials/psd/），躯干在头发底下
    #   那块本来就该画着衣服，而不是留个透明洞等头发一摆就穿帮。
    #   这一条**不**加 deep 限制：被四面围死本身就比\"在剪影深处\"更强，
    #   而那片缺口恰恰贴着原画里头发的轮廓走，deep（剪影内缩 4px）一个都圈不住
    #   （实测 176 个里命中 0 个）。全躯干统共只有 307 个这样的像素，
    #   全在肩颈带和裙摆上，离腋下、袖口那些**该透明**的地方十万八千里。
    #   判据用 alpha>24，和 check_assets 数窟窿时用的阈值一致。
    # ★★★ 2026-10-21 第三十三问：**手臂件底下那片是故意挖空的，不许当洞补**。
    #   make_arm_parts 会把整条袖子从躯干上清掉（occ），因为袖子归 arm_*_upper /
    #   arm_*_fore（层 140~143，画在躯干 100 之上）。那片透明是设计，不是缺陷。
    #   本轮把肩关节圆心修正之后，插肩育克留给躯干的那一小块青色和清空区贴到了
    #   一起，于是「四向封闭」判据在肩头圈出一个新的闭合区，拿最近邻的**青色**
    #   填实成 alpha=255 —— 躯干上凭空多出 139(l)/195(r) 个不跟手臂转的青像素，
    #   正是 check_assets「躯干上没留袖子」那条闸要抓的「抬手就悬空的青色」。
    #   （实测：make_arm_parts 刚写出时 l=0 r=0，跑完这个工具变成 139/195。）
    #   所以补洞一律避开手臂芯区。
    if arm_void is not None:
        filled = np.where(arm_void, 0.0, filled)
    gap = np.zeros(t_hair.shape, bool)
    for _ in range(3):
        cur = ((ta[..., 3] > 24) & (~t_hair)) | hole | gap
        up2 = np.maximum.accumulate(cur, axis=0)
        dn2 = np.maximum.accumulate(cur[::-1], axis=0)[::-1]
        lf2 = np.maximum.accumulate(cur, axis=1)
        rt2 = np.maximum.accumulate(cur[:, ::-1], axis=1)[:, ::-1]
        enc = (~cur) & up2 & dn2 & lf2 & rt2 & (filled > 0.5)
        if not (enc & (~gap)).any():
            break
        gap = gap | enc

    # ★ 收尾之二：把擦完剩下的**单像素麻点**补回去。
    #   发丝的深描边和高光边偶尔会在衣领轮廓上孤零零地点掉一两个像素
    #   （实测 9 个，分布在 y283~286 的三处），它们不满足"四向封闭"所以
    #   上面那条补不到，但留着就是"无损切分"闸上的 9 个洞。
    #   判据是**八邻域里至少 6 个还在**——只可能补回孤立麻点，
    #   成片的区域（邻域缺口多）一个都补不回来，不会把发梢又放回来。
    for _ in range(2):
        kept = ((ta[..., 3] > 40) & (~t_hair)) | hole | gap
        cnt = np.zeros(kept.shape, np.int16)
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                if dy or dx:
                    cnt += np.roll(np.roll(kept, dy, 0), dx, 1).astype(np.int16)
        pit = (ta[..., 3] > 40) & (~kept) & (cnt >= 6) & (filled > 0.5)
        if not pit.any():
            break
        hole = hole | pit
    return t_hair, hole, gap, trgb, rgbf


def _arm_void(sprites_dir, ta, scale):
    """手臂件（上臂/前臂/手）在躯干件坐标系里的芯区。

    这片是 make_arm_parts 故意从躯干上清掉的 —— 袖子由 arm_*（层 140~143）
    画在躯干之上。补洞类规则必须绕开它，否则补出来的像素不跟手臂转。
    往里腐蚀 3px：部件最外一圈是软边，留给接缝补画，别一刀切太狠。
    """
    ap = os.path.join(sprites_dir, "arm_parts.json")
    if not os.path.exists(ap):
        return None
    try:
        with open(ap, encoding="utf-8") as fh:
            d = json.load(fh)
    except Exception:
        return None
    void = np.zeros(ta.shape[:2], bool)
    # arm_parts.json 的 pos 和 body_parts.json 一样是 **body_full 坐标**，
    # 而 TORSO_ORIGIN 是**画布坐标** —— 差一个 PATCH_TO_CANVAS=(200,68)。
    oy = int(round((TORSO_ORIGIN[1] - PATCH_TO_CANVAS[1]) * scale))
    ox = int(round((TORSO_ORIGIN[0] - PATCH_TO_CANVAS[0]) * scale))
    hgt, wid = ta.shape[:2]
    for q in d.get("parts", []):
        if not (q["id"].endswith("_upper") or q["id"].endswith("_fore")
                or q["id"].startswith("hand_")):
            continue
        fp = os.path.join(sprites_dir,
                          os.path.basename(q["file"]).replace(
                              ".png", ".png" if scale == 1 else "@2x.png"))
        if not os.path.exists(fp):
            continue
        a = np.asarray(Image.open(fp).convert("RGBA"))[..., 3] > 200
        if not a.any():
            continue
        for _ in range(3 * scale):          # 腐蚀，别把软边也圈进来
            # 不能用 np.roll：它会绕回，hand_l 的 pos 是 x=0，贴着边
            pa = np.pad(a, 1, constant_values=False)
            a = (pa[1:-1, 1:-1] & pa[:-2, 1:-1] & pa[2:, 1:-1]
                 & pa[1:-1, :-2] & pa[1:-1, 2:])
        y0 = int(round(q["pos"][1] * scale)) - oy
        x0 = int(round(q["pos"][0] * scale)) - ox
        ys0, xs0 = max(0, y0), max(0, x0)
        ys1 = min(hgt, y0 + a.shape[0])
        xs1 = min(wid, x0 + a.shape[1])
        if ys1 <= ys0 or xs1 <= xs0:
            continue
        void[ys0:ys1, xs0:xs1] |= a[ys0 - y0:ys1 - y0, xs0 - x0:xs1 - x0]
    return void


def clean_body_seam(sprites_dir, scale=1):
    """同时修躯干件和头件在**下颌—衣领**这一带互相烘错的内容。

    病灶（2026-10-18 第十三问逐件归因得到）：
      · seg_torso 肩膀上烘着鲍勃头的蓝发梢 —— 换成长发/马尾后它还在，
        就是用户截图里下巴旁边那两撮；
      · seg_head 下缘挂着一截**衣领 + 蓝发梢**，层 180 压在躯干 100 的
        干净衣领上，而且跟着头一起动。
    两边都擦掉会在下颌和衣领之间露出一个真空洞 —— 因为那一片原画里**只有头发**。

    ★ 解法不是'凭空补画'，而是**搬运**：seg_head 下缘那截衣领是货真价实的原画，
      位置也正好压在躯干的洞上。于是先把它按画布坐标贴进 seg_torso，再把
      seg_head 下缘整个剪掉。剩下的零星缺口才用最近邻补洞收尾。
    """
    tp = os.path.join(sprites_dir, "seg_torso.png" if scale == 1 else "seg_torso@2x.png")
    hp = os.path.join(sprites_dir, "seg_head.png" if scale == 1 else "seg_head@2x.png")
    ta = np.asarray(Image.open(tp).convert("RGBA")).astype(np.float32)
    ha = np.asarray(Image.open(hp).convert("RGBA")).astype(np.float32)
    tA0 = ta[..., 3].copy()
    hA0 = ha[..., 3].copy()

    # ── 头件：下颌线以下分三类 ──────────────────────────────
    hh, hw = ha.shape[:2]
    hys = (np.arange(hh, dtype=np.float32) / scale) + HEAD_ORIGIN[1]
    below = (hys[:, None] >= HEAD_SKIN_CUT_Y - 14.0) & np.ones((1, hw), bool)
    hR, hG, hB, hA = ha[..., 0], ha[..., 1], ha[..., 2], ha[..., 3]
    h_hair = _hair_mask(ha, scale) & below
    h_skin = ((hR - hB) > HEAD_SKIN_RB) & (hA > 40)
    # 衣领/衬衫：既不是皮肤也不是头发，且在下颌线以下
    h_cloth = (hA > 40) & below & (~h_skin) & (~h_hair)

    # ── 躯干：肩上的发梢 ────────────────────────────────────
    # body_full 的剪影（往里腐蚀 4px）映射到躯干件坐标系，交给 torso_masks
    deep = None
    bfp = os.path.join(sprites_dir, "body_full.png")
    if os.path.exists(bfp):
        bf = np.asarray(Image.open(bfp).convert("RGBA"))[..., 3] > 24
        er = np.asarray(Image.fromarray((bf * 255).astype(np.uint8))
                        .filter(ImageFilter.MinFilter(9))) > 127
        if scale != 1:
            er = np.asarray(Image.fromarray((er * 255).astype(np.uint8)).resize(
                (er.shape[1] * scale, er.shape[0] * scale), Image.NEAREST)) > 127
        # 躯干件在 body_full 里的左上角 = 画布原点 − 画布偏移(200,68)
        oy = int(round((TORSO_ORIGIN[1] - 68) * scale))
        ox = int(round((TORSO_ORIGIN[0] - 200) * scale))
        deep = np.zeros(ta.shape[:2], bool)
        hgt, wid = ta.shape[:2]
        sub = er[oy:oy + hgt, ox:ox + wid]
        deep[:sub.shape[0], :sub.shape[1]] = sub
    t_hair, hole, gap, trgb, rgbf = torso_masks(ta, scale, deep,
                                                arm_void=_arm_void(sprites_dir, ta, scale))
    newTA = np.where(t_hair, 0.0, ta[..., 3])
    # gap 是**原本就透明**的洞，alpha 得现给（hole 那些是擦掉又补回，取原值）
    newTA = np.where(gap, 255.0, newTA)
    trgb = np.where(gap[..., None], rgbf, trgb)

    # ── 试过、放弃了：把头件那截衣领\"搬运\"到躯干的洞上 ──────────
    # 思路是对的（那是货真价实的原画，位置也正好压在洞上），但实测只有 ~150
    # 像素能搬 —— 因为那一带 seg_head 里**也**是头发，不是衣领。而这 150 像素
    # 取自头件的**阴影侧**，贴过去在躯干的亮青领上糊出两块深色硬斑，比洞还难看。
    # 结论：这片区域原画里就没有衣领，只能靠下面的最近邻补洞收尾。
    moved = 0
    th, tw = ta.shape[:2]

    # ── 还剩的零星缺口：补洞（掩码由 torso_masks 一并算好） ──
    newTA = np.where(hole, ta[..., 3], newTA)
    trgb = np.where(hole[..., None], rgbf, trgb)

    out = np.dstack([trgb, newTA])
    _save_with_2x(tp, ta, out, (t_hair | hole))

    # ── 头件：下颌线以下的\"别人家的东西\"剪掉（带 6px 软过渡） ───────
    # 病灶是**衣领**：它在层 180，压着躯干层 100 那条干净的衣领，还跟着头转。
    # ★ 剪的范围走过两个极端，都不行：
    #   · cut = ~h_skin（只留皮肤）—— 连下颌两侧垂下来的几丝头发也剪了。
    #     那几丝 hair_side_l/r 够不到（框到 y284 就结束），躯干也没有，
    #     于是\"无损切分\"闸上剩 9 个洞。
    #   · cut = h_cloth（只剪衣领）—— 头发全留下，脖子两侧和衣领上糊着
    #     一片青蓝碎发，正是用户第十三问截图里指出来的那种脏东西。
    # ★ 定稿判据：**只剪有人在下面接着的**。衣领一律剪（躯干那条是原画，
    #   比头件这截干净）；头发只在**躯干确实盖得到**的地方剪 —— 剪掉的
    #   每一个像素都有躯干顶着，剪不掉的那几个正好是躯干轮廓外、谁也不管的，
    #   留在头件上既不脏（它们本来就是侧发的发梢）又把洞堵上了。
    t_cov = np.zeros(ha.shape[:2], bool)
    dr = int(round((HEAD_ORIGIN[1] - TORSO_ORIGIN[1]) * scale))
    dc = int(round((HEAD_ORIGIN[0] - TORSO_ORIGIN[0]) * scale))
    th_, tw_ = ta.shape[:2]
    rr = np.arange(hh) + dr
    cc = np.arange(hw) + dc
    vr = (rr >= 0) & (rr < th_)
    vc = (cc >= 0) & (cc < tw_)
    if vr.any() and vc.any():
        sub = newTA[np.ix_(rr[vr], cc[vc])] > 40
        t_cov[np.ix_(vr, vc)] = sub
    ramp = np.clip((hys[:, None] - (HEAD_SKIN_CUT_Y - 6.0)) / 6.0, 0.0, 1.0)
    cut = (h_cloth | (h_hair & t_cov)).astype(np.float32) * ramp
    hout = ha.copy()
    hout[..., 3] = hA * (1.0 - cut)
    _save_with_2x(hp, ha, hout, cut > 0.002)
    ha = hout

    return ([int(((tA0 > 60) & (newTA <= 60)).sum()), int((tA0 > 60).sum()), moved],
            [int(((hA0 > 60) & (ha[..., 3] <= 60)).sum()), int((hA0 > 60).sum())])


def drop_detached_islands(sdir, min_keep=300):
    """把分段身体件上**和本体断开的小碎岛**整块删掉。

    ★★★ 2026-10-21 第二十八问。用户第 ②③ 条（黑边 / 消失的区块）里，
      换发型之后脸两侧那层"白毛边"，有一半出在这儿：

      `seg_head.png` 一共 6 个连通块 —— 本体 22348px，另外 5 块合起来才 128px，
      分别趴在 **x1..5（80px）** 和 **x242..247（45px）**，也就是贴着图幅
      最左和最右的边，y 都在 174~190（耳朵高度）。它们是底图鲍勃发最外侧
      的发梢，第 15 步 `make_sidehair_parts.py` 挖鬓发时没挖干净剩下的。
      短发档有 `hair_side_l/r` 压在上面看不见；一换发型那两件被隐藏，
      这两撮 2~4px 宽、离脸 200px 远的碎毛就**孤零零浮在脸旁边**。
      `seg_torso.png` 同样有一块 248px 的竖条浮在顶边 (x69..76, y0..41)。

      为什么这里可以用"连通块 + 大小"一刀切（台账里明明记着
      「碎块不许用最大连通块/大小阈值」）：那条教训是对**头发件**说的 ——
      一缕头发完全可以被身体剪影切成几段，断开不等于垃圾。
      但 `seg_*` 是**分段身体件**，按定义就是一整块连续的皮肉/布料，
      不存在"合法的飞地"。判据和对象是配套的，不能跨着用。
    """
    import collections
    hits = []
    for fname in sorted(os.listdir(sdir)):
        if not fname.startswith("seg_") or not fname.endswith(".png"):
            continue
        if "@2x" in fname:
            continue
        p1 = os.path.join(sdir, fname)
        a = np.asarray(Image.open(p1).convert("RGBA")).copy()
        m = a[..., 3] > 8
        if not m.any():
            continue
        H, W = m.shape
        lab = np.zeros((H, W), np.int32)
        sizes = [0]
        cur = 0
        for y0, x0 in np.argwhere(m):
            if lab[y0, x0]:
                continue
            cur += 1
            n = 0
            dq = collections.deque([(y0, x0)])
            lab[y0, x0] = cur
            while dq:
                y, x = dq.popleft()
                n += 1
                for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    ny, nx = y + dy, x + dx
                    if 0 <= ny < H and 0 <= nx < W and m[ny, nx] and not lab[ny, nx]:
                        lab[ny, nx] = cur
                        dq.append((ny, nx))
            sizes.append(n)
        if cur <= 1:
            continue
        big = int(np.argmax(sizes))
        limit = max(min_keep, 0.01 * sizes[big])
        kill = np.zeros((H, W), bool)
        killed = 0
        for i in range(1, cur + 1):
            if i != big and sizes[i] < limit:
                kill |= (lab == i)
                killed += sizes[i]
        if not killed:
            continue
        a[..., 3][kill] = 0
        Image.fromarray(a, "RGBA").save(p1)
        p2 = os.path.join(sdir, fname.replace(".png", "@2x.png"))
        if os.path.exists(p2):
            b = np.asarray(Image.open(p2).convert("RGBA")).copy()
            k2 = np.asarray(Image.fromarray((kill * 255).astype(np.uint8))
                            .resize((b.shape[1], b.shape[0]), Image.NEAREST)) > 127
            b[..., 3][k2] = 0
            Image.fromarray(b, "RGBA").save(p2)
        hits.append((fname, cur - 1, killed, sizes[big]))
        print("  %-16s 删掉 %d 个断开的小碎岛共 %5d px（本体 %d px）"
              % (fname, cur - 1, killed, sizes[big]))
    if not hits:
        print("  分段件上没有断开的碎岛")
    return hits


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--character", default="xiaoxun")
    ap.add_argument("--form", default="teen")
    ap.add_argument("--no-head-cut", action="store_true",
                    help="不动 seg_head 下缘（留它的衣领压在躯干补过的地方上）")
    args = ap.parse_args()

    sdir = os.path.join(ROOT, "characters", args.character, "forms", args.form, "sprites")
    if not os.path.exists(os.path.join(sdir, "eye_parts.json")):
        print("没有 eye_parts.json，跳过")
        return 0

    irises = iris_centers(sdir)
    print("虹膜中心（画布 1×）：", {k: (round(v[0], 1), round(v[1], 1)) for k, v in irises.items()})

    report = []
    for fname, origin in collect_targets(sdir):
        for suffix, scale in ((".png", 1), ("@2x.png", 2)):
            p = os.path.join(sdir, fname.replace(".png", suffix))
            if not os.path.exists(p):
                continue
            removed, total = clean(p, origin, irises, scale)
            pct = 100.0 * removed / max(1, total)
            print("  %-24s 擦掉 %5d / %5d 像素 (%.1f%%)" % (os.path.basename(p), removed, total, pct))
            if scale == 1:
                report.append({"file": fname, "origin": list(origin),
                               "removed_px": removed, "total_px": total, "removed_pct": round(pct, 2)})

    islands = drop_detached_islands(sdir)

    body = []
    if os.path.exists(os.path.join(sdir, "seg_torso.png")):
        t, h = clean_body_seam(sdir, 1)
        print("  seg_torso       擦掉 %5d / %6d（@2x 由 1× 派生）" % (t[0], t[1]))
        print("  seg_head        擦掉 %5d / %6d（@2x 由 1× 派生）" % (h[0], h[1]))
        body.append({"file": "seg_torso.png", "removed_px": t[0], "total_px": t[1]})
        body.append({"file": "seg_head.png", "removed_px": h[0], "total_px": h[1]})

    out = os.path.join(sdir, "eye_clean_report.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump({"note": "烘进别的部件里的头发/衣领残留已擦除（tools/clean_baked_residue.py）",
                   "body": body,
                   "keep_ellipse": [KEEP_AX, KEEP_AY], "feather": KEEP_FEATHER,
                   "hair_threshold_b_minus_r": [HAIR_T0, HAIR_T1],
                   "iris_centers": {k: [round(v[0], 2), round(v[1], 2)] for k, v in irises.items()},
                   "parts": report}, f, ensure_ascii=False, indent=2)
    print("写出", os.path.relpath(out, ROOT))
    return 0


if __name__ == "__main__":
    sys.exit(main())
