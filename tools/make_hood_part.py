# -*- coding: utf-8 -*-
"""兜帽素材整形：把画出来的兜帽**按头部实测几何**削到该有的厚度，并算出放置参数。

为什么要有这一步
────────────────
兜帽连着改了五版，前四版用户的判语都是「太大」「太难看」，第五版的原话是
「能不能做可爱点，像截图5这个就是参考，不要兔耳朵」。复盘下来，造型好不好看
和\u201c提示词写得好不好\u201d关系不大，决定性的是三个**绝对尺寸**：

  ① 内开口要**框住整张脸和刘海**（开口比头窄 ⇒ 变成头盔/修女帽）
  ② 外轮廓 ÷ 头宽 控制在 1.35~1.45（出图模型画出来的布边普遍厚一倍，
     直接用就是 2.2 倍头宽的巨蛋 —— 这正是\u201c太大\u201d的来源）
  ③ 帽顶只比头顶高 5~15px，下摆落在肩线上

出图模型控不住这三个数，但本仓库**全部实测已知**（头顶 y=116、下颌 y=345、
头宽 246、头心 x=423）。所以分工改成：
  · 形状/笔触/蕾丝 —— 交给画（acc_hood_cute_v5.png，洋红底）
  · 尺寸/厚度/位置 —— 这个脚本按头部几何**算**出来

做法是把\u201c外轮廓\u201d整体内缩 TRIM 像素（内开口和蕾丝原样不动），于是布边变薄、
开口相对变大，再按开口宽度定标到头宽。Live2D 官方学园也有一课专讲
フードの作り方（https://juku.live2dcs.jp/en/course/course-55/），要点同样是
\u201c按头的实际剪影定开口\u201d。

★ 明确不画兔耳 / 猫耳 / 任何耳状凸起（用户两次点名否掉）。
"""
import argparse
import os
import sys

try:
    import numpy as np
    from PIL import Image, ImageFilter
except ImportError:  # pragma: no cover
    print("需要 pillow + numpy")
    sys.exit(1)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# ── 头部实测几何（画布 1×，teen）──────────────────────────
HEAD_CX = 423.0
HEAD_TOP = 116.0
HEAD_JAW = 345.0
HEAD_W = 246.0
HAIRLINE_Y = 163.0

# 外轮廓内缩多少（源图像素）。卫衣帽的布边本来就不厚，默认不削。
TRIM = 0

# 定标：内开口宽度 ÷ 头宽。0.84 = 开口比头略窄，帽沿**压住两侧头发各 20px**，
# 这正是\u201c戴上了\u201d的观感；给到 1.0 以上头发全露在外面，像顶着一个圈。
OPEN_OVER_HEAD = 0.84
# 开口上下沿落在哪（画布 y）。★ 纵横**分开**定标是必须的：
#   出图模型画的帽口是个 1.75:1 的长椭圆（照着长脸画的），而这个角色的
#   脸+刘海只有约 1.05:1。按等比缩放，要么开口太窄夹住脸，要么帽子从
#   头顶 67px 上方一直垂到胸口。竖着压扁 ~27% 之后才贴头。
OPEN_TOP_Y = 134.0      # 发际线 163 之上 29px ⇒ 整片刘海露在开口里
OPEN_BOTTOM_Y = 400.0   # 下颌 345 之下 55px ⇒ 帽口在衣领处收口
CROWN_TOP_Y = 66.0      # anchors 的 head_top（呆毛尖）画布 y=68，留 2px 余量


def _flood_from_border(mask):
    """返回 mask 中**和画面边缘连通**的部分（4 邻域）。用来把\u201c背景洋红\u201d和
    \u201c开口里的洋红\u201d分开 —— 开口不和边缘连通。"""
    h, w = mask.shape
    out = np.zeros_like(mask)
    stack = []
    for x in range(w):
        for y in (0, h - 1):
            if mask[y, x] and not out[y, x]:
                out[y, x] = True
                stack.append((y, x))
    for y in range(h):
        for x in (0, w - 1):
            if mask[y, x] and not out[y, x]:
                out[y, x] = True
                stack.append((y, x))
    while stack:
        y, x = stack.pop()
        for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            ny, nx = y + dy, x + dx
            if 0 <= ny < h and 0 <= nx < w and mask[ny, nx] and not out[ny, nx]:
                out[ny, nx] = True
                stack.append((ny, nx))
    return out


def _erode(mask, px):
    """二值腐蚀 px 像素（拿 PIL 的 MinFilter 攒，比纯 numpy 循环快一个量级）。"""
    im = Image.fromarray((mask * 255).astype(np.uint8), "L")
    k, left = 9, px
    while left > 0:
        step = min(4, left)
        size = step * 2 + 1
        im = im.filter(ImageFilter.MinFilter(size))
        left -= step
    return np.asarray(im) > 127


def _bbox(mask):
    ys, xs = np.nonzero(mask)
    return int(xs.min()), int(xs.max()), int(ys.min()), int(ys.max())


def _match_jacket(arr, fabric, sprites_dir):
    """量出\"把帽子的青/白拉到夹克本体同色\"要乘的系数。"""
    tp = os.path.join(sprites_dir, "seg_torso.png")
    if not os.path.exists(tp):
        return (1.0, 1.0, 1.0), (1.0, 1.0, 1.0)
    t = np.asarray(Image.open(tp).convert("RGBA")).astype(float)
    tR, tG, tB, tA = t[..., 0], t[..., 1], t[..., 2], t[..., 3]
    jt = (tA > 200) & (tG - tR > 40) & (tG - tB > 0)
    jw = (tA > 200) & (np.minimum(np.minimum(tR, tG), tB) > 215)
    hR, hG, hB = arr[..., 0], arr[..., 1], arr[..., 2]
    ht = fabric & (hG - hR > 25)
    hw = fabric & (np.minimum(np.minimum(hR, hG), hB) > 215)
    def ratio(src, dst_m, dst, src_m):
        if src_m.sum() < 50 or dst_m.sum() < 20:
            return 1.0
        return float(dst[dst_m].mean()) / max(1e-3, float(src[src_m].mean()))
    teal = tuple(ratio(h, jt, d, ht) for h, d in ((hR, tR), (hG, tG), (hB, tB)))
    white = tuple(ratio(h, jw, d, hw) for h, d in ((hR, tR), (hG, tG), (hB, tB)))
    return teal, white


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--character", default="xiaoxun")
    ap.add_argument("--form", default="teen")
    ap.add_argument("--source", default="acc_hood_cute_v5.png")
    ap.add_argument("--out", default="acc_hood_cute.png")
    ap.add_argument("--trim", type=int, default=None)
    a = ap.parse_args()

    rd = os.path.join(ROOT, "characters", a.character, "design", "redraw")
    sp = os.path.join(ROOT, "characters", a.character, "forms", a.form, "sprites")
    src = os.path.join(rd, a.source)
    im = Image.open(src).convert("RGB")
    arr = np.asarray(im).astype(int)
    R, G, B = arr[..., 0], arr[..., 1], arr[..., 2]
    mag = (R > 170) & (B > 170) & (G < 130)

    bg_mag = _flood_from_border(mag)
    hole = mag & (~bg_mag)
    filled = ~bg_mag                      # 布面 + 开口
    trim = TRIM if a.trim is None else a.trim
    kept = _erode(filled, trim) if trim > 0 else filled
    fabric = (~mag) & kept

    # 抽绳是两根细条，拖在帽身下面老远。按\"行宽突然掉到主体的 35% 以下\"
    # 自动找到它们的起点并裁掉 —— 夹克本体胸口已经画了一对抽绳，再叠一对
    # 就是两套；而且带着它们定标会把整顶帽子拉长到胸口。
    rows = fabric.sum(axis=1)
    body = rows.max()
    ys_all = np.nonzero(rows)[0]
    cut = ys_all.max() + 1
    for y in range(ys_all.max(), ys_all.min(), -1):
        if rows[y] >= body * 0.35:
            cut = y + 1
            break
    fabric[cut:, :] = False
    hole = hole & kept
    hole[cut:, :] = False

    teal_fix, white_fix = _match_jacket(arr, fabric, sp)
    out = arr.astype(float).copy()
    # 和夹克本体对色：出图模型给的青偏鲜、白偏冷，两件衣服摆一起一眼能看出
    # 不是一套。按**实测均值**逐通道拉齐（青→夹克青、白→夹克白），
    # 中间调用权重软过渡，不会压掉布褶的明暗。
    oR, oG, oB = out[..., 0], out[..., 1], out[..., 2]
    tw = np.clip((oG - oR - 15.0) / 25.0, 0.0, 1.0) * fabric
    for c, k in enumerate(teal_fix):
        out[..., c] = out[..., c] * (1.0 - tw) + out[..., c] * k * tw
    ww = np.clip((np.minimum(np.minimum(oR, oG), oB) - 180.0) / 30.0, 0.0, 1.0) \
        * fabric * (1.0 - tw)
    for c, k in enumerate(white_fix):
        out[..., c] = out[..., c] * (1.0 - ww) + out[..., c] * k * ww
    out = np.clip(out, 0, 255)
    out[~fabric] = (255, 0, 255)
    Image.fromarray(out.astype(np.uint8), "RGB").save(os.path.join(rd, a.out))

    cx0, cx1, cy0, cy1 = _bbox(fabric)
    hx0, hx1, hy0, hy1 = _bbox(hole)
    cw, ch = cx1 - cx0 + 1, cy1 - cy0 + 1
    ow, oh = hx1 - hx0 + 1, hy1 - hy0 + 1

    # ── 纵横分开定标（见文件头）────────────────────────────
    sx = (HEAD_W * OPEN_OVER_HEAD) / float(ow)
    sy = (OPEN_BOTTOM_Y - OPEN_TOP_Y) / float(oh)
    cw_c, ch_c = cw * sx, ch * sy
    sprite_w, sprite_h = cw_c * 1.08, ch_c * 1.08   # build_one 四周各留 4%
    # build_one 算宽是 w1 = h1 * bw/bh * width_ratio，反解出 width_ratio
    width_ratio = sprite_w / (sprite_h * cw / float(ch))
    content_top = OPEN_TOP_Y - (hy0 - cy0) * sy
    # ★ 帽顶必须盖过**呆毛尖**（anchors 的 head_top，画布 y=68），不是盖过颅顶。
    #   戴上兜帽本来就会把呆毛压在帽子里；露在外面一截反而像帽子顶在脑门上。
    #   selfcheck_repo 的「兜帽顶盖过头顶」就是量这个（容差 3px）。
    #   够不着就整顶往上挪 —— 开口跟着上移几像素，对脸的位置没有可见影响。
    if content_top > CROWN_TOP_Y:
        shift = content_top - CROWN_TOP_Y
        content_top -= shift
        open_top = OPEN_TOP_Y - shift
    else:
        open_top = OPEN_TOP_Y
    sprite_top = content_top - ch_c * 0.04
    content_cx = HEAD_CX + ((cx0 + cx1) / 2.0 - (hx0 + hx1) / 2.0) * sx

    unit = 278.0
    print("[hood] 源 %s：内容 %dx%d（抽绳从第 %d 行裁掉），开口 %dx%d"
          % (a.source, cw, ch, cut, ow, oh))
    print("[hood] 削边 %dpx，对色 teal×(%.3f,%.3f,%.3f) white×(%.3f,%.3f,%.3f)"
          % ((trim,) + tuple(teal_fix) + tuple(white_fix)))
    print("[hood] 定标 sx=%.4f sy=%.4f ⇒ 开口 %.0fx%.0f（头宽 %.0f 的 %.2f 倍）、"
          "外轮廓宽 %.0f（头宽的 %.2f 倍）"
          % (sx, sy, ow * sx, oh * sy, HEAD_W, OPEN_OVER_HEAD, cw_c,
             cw_c / HEAD_W))
    print("[hood] 帽顶 y=%.0f（头顶 %.0f 之上 %.0f）、开口 y=%.0f~%.0f"
          "（发际线 %.0f、下颌 %.0f）、下摆 y=%.0f"
          % (content_top, HEAD_TOP, HEAD_TOP - content_top, open_top,
             open_top + (OPEN_BOTTOM_Y - OPEN_TOP_Y), HAIRLINE_Y, HEAD_JAW,
             content_top + ch_c))
    print("[hood] → attachments.json：pos_rel [%.6f, %.6f]  sprite_h_rel %.6f"
          "  width_ratio %.4f  （sprite %.0fx%.0f）"
          % ((content_cx - 416.0) / unit, (sprite_top - 68.0) / unit,
             sprite_h / unit, width_ratio, sprite_w, sprite_h))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
