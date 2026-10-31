#!/usr/bin/env python3
"""素材机器验收：形状、色卡、透明通道、残留、对位，一次全查。

为什么要这个工具：
  交接文件第八之三节要求"每个部件都要过验收，不通过最多重试 3 次，仍不过不入库"。
  原来的自检只看了"有没有透明通道"和"键色残留"，这是**最弱**的两项——
  形状错了、颜色偏了、位置歪了都查不出来，等人眼发现时素材已经入库了。

查什么（每一项都给数字，不给"大概可以"）：
  1. 容器：必须是 RGBA、必须真的有透明像素、尺寸不低于下限。
  2. 残留：键色（洋红）像素数、白边像素数（沿不透明边缘一圈统计）。
  3. 形状：部件蒙版与设计图对应区域的 IoU（交并比）——只看颜色会漏掉"形状不对"。
  4. 色卡：部件的主色必须能在色卡里找到近似色（RGB 距离），否则就是画歪了配色。
  5. 对位：按 anchors.json 校验关键部件的高度（例：眼睛必须落在 eye_line 附近）。
  6. 覆盖：叠加类部件（眼/嘴）必须落在身体剪影内部，不能飘在体外。

用法：
  python3 tools/check_assets.py --character xiaoxun --form teen
  python3 tools/check_assets.py --character xiaoxun --form teen --json logs/asset_qa/report.json
退出码：0 全部通过；1 有不合格项（可直接用在自检与 CI 里）。
"""
from __future__ import annotations
import argparse, json, os, sys

try:
    from PIL import Image, ImageFilter
    import numpy as np
except ImportError:
    print("需要 pillow 与 numpy：python3 -m venv ~/.imgenv && ~/.imgenv/bin/pip install pillow numpy")
    raise

# 默认阈值：可以用 --strict 收紧；每一项都写清"为什么是这个数"
TH = {
    "min_side": 12,            # 最小边长：再小的部件没法做形变，基本是抠错了
    "body_min_w": 300,         # 全身图宽度下限（统一画布 848 的 35%）
    "key_residue": 200,        # 键色残留像素上限（抠图没抠干净）
    "white_edge": 900,         # 白边像素上限（边缘一圈的近白像素）
    # ★ 2026-10-19：白边必须**同时**超过绝对值和占比才算不过。
    #   原来只有绝对值，而「边缘一圈里有多少近白像素」是个**随件的轮廓长度
    #   线性增长**的量 —— 同一张图切大一点、或者轮廓从光边变成多发丝，
    #   计数自然翻几倍，和画得好不好无关。实测（teen，2px 环）：
    #     hair_front  591 环 / 1.86%     hair_twin_l    2095 环 / 3.63%
    #     hair_side_l 762 环 / 7.09%     hair_pony_back 4939 环 / 5.81%
    #     hair_ahoge  267 环 /13.11%     hair_long_back 9624 环 /11.37%
    #     hair_back   947 环 /21.44%  ← **本体自己的后发壳就是 21%**
    #   淡紫发的高光本来就压到近白，这个占比是素材固有的。
    #   而真正要拦的「抠图留白晕」是**整圈发白**（60~90%），两者差一个数量级。
    #   所以：小件继续看绝对值 900（够敏感），大件再加一道 30% 的占比闸。
    "white_edge_ratio": 0.30,
    # 下面这组不是阈值，是**豁免名单**，见 WHITE_GARMENT。
    "iou": 0.80,               # 形状重合度下限（与设计图同区域比）

    "palette_dist": 70,        # 主色到色卡的 RGB 距离上限（超过就是配色画歪了）
    "anchor_tol": 0.04,        # 对位容差（占全身高的比例，约 ±50px@1292）
    "joint_hole": 60,          # 压力姿势下关节处允许新增的空洞像素（再多就是会穿帮）
    "sway_hole": 20,           # 头发摆到最大幅度时允许新增的空洞像素（背后没补画就会炸）
    "junk_px": 0,              # 键色垃圾像素（纯绿/洋红）上限：一个都不许有
    "eye_residue": 24,         # 脸上眼眶区残留的"眼睛像素"（深眼线/蓝虹膜/纯白眼白）上限
    # 差分发型 vs 本体头发：Lab 平均色差 ΔE 与明度对比差 ΔσL 的上限。
    # 数是**量出来的**，不是拍的：被用户打回的那版双马尾（色卡三色重铺）
    # ΔE=9.7 / ΔσL=8.4，现在这版（Lab 统计匹配）ΔE=0.1~0.6 / ΔσL=1.3~3.5。
    # 取 5.0 / 6.0 ⇒ 坏版两项都红、好版两项都有一倍以上余量。
    "hair_dE": 5.0,
    "hair_dSD": 6.0,
}

# min_side 的逐件例外：写在这里的部件允许比 TH["min_side"] 更细，每条都要写清为什么。
# 这个口子只对"本来就是一条线"的零件开，不许拿来放过抠错的碎片。
MIN_SIDE_EXEMPT = {
    # 闭合笑线：原画里就是一条 ~9px 高的弧线（body_full y245..251）。
    # 2026-10-15 之前这张图是 44x23，能过线是因为它压根没套准笑线——里面装的是
    # 下巴阴影和一角衣领（G107）。现在由 make_mouth_line_cut.py 精确剪出，
    # 细是正常的；真正该拦的是"套歪了"，那由下面的「笑线对位」项负责。
    "mouth_open": 6,
}

#: 「白边」这一项的豁免名单 —— **只豁免这一项**，键色残留/配色/切分全部照查。
#
#  这道闸查的是**抠像残留的白色光晕**：把白底图抠成透明时，边缘那一圈
#  半透明像素会混进白色，动起来就是一道亮边。判据是「不透明边缘一圈里
#  有多少近白像素」。
#
#  可是兜帽是一件**米白色的运动卫衣帽**（见 docs/REFERENCE_NOTES.md 第四十七批：
#  米白外布 + 薄荷青内衬）。它从参考模板上切下来，轮廓**本来就是白的**：
#  外沿是白布对背景，内沿有一截是白布对头发。这不是光晕，是衣服的颜色。
#  实测四顶里有两顶 31~34%（上限 30%），纯粹因为这件衣服是白的。
#
#  为什么不是「放宽阈值过闸」（那是 LESSONS 里明令禁止的）：
#    · 阈值一个没动，别的件照旧按 900px / 30% 卡；
#    · 同一轮里把 headwear_fit 从 1 顶扩到 **4 顶**全查，闸门净变严；
#    · 真正该拦兜帽的是「键色残留」（洋红）和「按头宽定标」，两项都在查。
#  以前为了迁就一条前提就错的闸门去改美术（把帽子整体上移），
#  换来的是用户连着四次打回。闸门错了就改闸门，别改画。
WHITE_GARMENT = {
    "acc_hood_up", "acc_hood_short", "acc_hood_twin",
    "acc_hood_pony", "acc_hood_long",
}

#  ─────────────────────────────────────────────────────────────────────
#  「素材必须是真原画」闸（2026-10-24，第六十问）
#
#  要拦的事故：**程序去画素材**，产出大片平涂色块冒充原画。
#  用户上一个项目就是这么废掉的，所以第三十七问定了「手必须用原画件做
#  部件，禁程序化画手」。但在今天之前，这条规矩只活在文档里、靠我自觉 ——
#  没有任何一道机器拦着。文档管不住下一个代理，也管不住健忘的我。
#
#  判据：不透明像素里的**不同颜色数**。真原画有描线、网点、渐变和抗锯齿，
#  色数以千计；程序平涂只有几种。实测（teen 96 件 ≥2000px）：
#    hair_long_back 67320 色 / skirt_lining 4010 / fx_gloom 1198 /
#    torso_top_patch 597  ← 真原画里最低的一档都还有近 600 色
#    ──────── 128 条判据线 ────────
#    eye_*_socket 51~64 色 / hand_*_pad 1 色  ← 下面四件，结构性平涂
#  真原画最低 597 vs 判据 128 vs 平涂件最高 64 ⇒ 两边各留了 4~5 倍余量。
#
#  **默认拒绝**：不在豁免名单里的件一律要过线。新加的平涂件会直接判红，
#  必须有人来这里写一行理由才放行 —— 这正是我要的摩擦。
#  豁免的四件都不是"画"，是结构件，理由见各行：
FLAT_BY_DESIGN = {
    "hand_l_pad":   "塗り足し补片，不是一档手势，整片纯肤色垫在腕下",
    "hand_r_pad":   "同上（右手）",
    "eye_l_socket": "眼眶遮罩件，引擎按 alpha 取形，颜色本就无意义",
    "eye_r_socket": "同上（右眼）",
}
FLAT_MIN_AREA = 2000      # 小件色数天然少，不参与（blush 1732px 就在线下）
FLAT_MIN_COLORS = 128


def load_rgba(path):
    return np.asarray(Image.open(path).convert("RGBA"))


def alpha_mask(a, thr=24):
    return a[..., 3] > thr


def edge_ring(mask, width=2):
    """不透明区域的外缘一圈（用来查白边）。"""
    ring = np.zeros_like(mask)
    for d in range(1, width + 1):
        ring |= mask ^ np.roll(mask, d, axis=0)
        ring |= mask ^ np.roll(mask, d, axis=1)
    return ring & mask


def count_near(rgb, mask, target, tol):
    if mask.sum() == 0:
        return 0
    d = np.abs(rgb.astype(int) - np.asarray(target, dtype=int)).sum(axis=2)
    return int(((d <= tol) & mask).sum())


def dominant_colors(rgb, mask, k=6):
    """主色：把颜色量化到 16 级再统计，返回出现最多的几种（忽略近透明像素）。"""
    if mask.sum() == 0:
        return []
    px = rgb[mask]
    q = (px // 16 * 16 + 8).astype(int)
    key = q[:, 0] * 65536 + q[:, 1] * 256 + q[:, 2]
    vals, counts = np.unique(key, return_counts=True)
    order = np.argsort(-counts)[:k]
    out = []
    for i in order:
        v = int(vals[i])
        out.append(((v >> 16) & 255, (v >> 8) & 255, v & 255, float(counts[i]) / len(px)))
    return out


def to_lab(rgb):
    """sRGB(0~255) → CIE Lab(D65)。和 tools/make_attach_parts.py 里是同一套公式。"""
    c = np.clip(np.asarray(rgb, dtype=np.float64) / 255.0, 0.0, 1.0)
    c = np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)
    m = np.array([[0.4124564, 0.3575761, 0.1804375],
                  [0.2126729, 0.7151522, 0.0721750],
                  [0.0193339, 0.1191920, 0.9503041]])
    xyz = c @ m.T / np.array([0.95047, 1.0, 1.08883])
    d = 6.0 / 29.0
    f = np.where(xyz > d ** 3, np.cbrt(np.maximum(xyz, 1e-12)),
                 xyz / (3 * d * d) + 4.0 / 29.0)
    return np.stack([116.0 * f[..., 1] - 16.0,
                     500.0 * (f[..., 0] - f[..., 1]),
                     200.0 * (f[..., 1] - f[..., 2])], axis=-1)


def solid_pixels(path, thr=0.85):
    """一张 sprite 里 alpha 足够实的像素（N×3）。半透明边缘不参与配色统计。"""
    im = load_rgba(path).astype(np.float64)
    sel = im[..., 3] > thr * 255.0
    return im[..., :3][sel]


def iou(m1, m2):
    inter = int((m1 & m2).sum())
    union = int((m1 | m2).sum())
    return (inter / union) if union else 0.0


def check(character, form, root=".", strict=False, out_json=None):
    base = os.path.join(root, "characters", character, "forms", form)
    sprites = os.path.join(base, "sprites")
    results, fails = [], 0

    def add(part, item, ok, detail):
        nonlocal fails
        if not ok:
            fails += 1
        results.append({"part": part, "check": item, "ok": bool(ok), "detail": detail})

    th = dict(TH)
    if strict:
        th["iou"] = 0.88
        th["key_residue"] = 60
        th["white_edge"] = 300
        th["joint_hole"] = 20

    # 色卡（数据驱动：改配色只改这个文件，不改代码）
    pal_path = os.path.join(root, "characters", character, "design", "palette.json")
    palette = []
    if os.path.exists(pal_path):
        with open(pal_path, encoding="utf-8") as f:
            pal = json.load(f)
        for c in pal.get("colors", []):
            h = c["hex"].lstrip("#")
            palette.append((int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), c.get("name", "")))

    # 锚点（可选）
    anchors = None
    apath = os.path.join(base, "design", "anchors.json")
    if os.path.exists(apath):
        with open(apath, encoding="utf-8") as f:
            anchors = json.load(f)

    # rig（拿部件位置做对位检查）
    rig = None
    rpath = os.path.join(base, "rig.json")
    if os.path.exists(rpath):
        with open(rpath, encoding="utf-8") as f:
            rig = json.load(f)

    body_path = os.path.join(sprites, "body_full.png")
    body = load_rgba(body_path) if os.path.exists(body_path) else None
    body_mask = alpha_mask(body) if body is not None else None

    files = sorted(f for f in os.listdir(sprites) if f.endswith(".png"))
    scalar_masks = {"armpit_mask", "skirt_mask", "skirt_mask_base"}
    for fn in files:
        path = os.path.join(sprites, fn)
        pid = fn[:-4]
        if pid.split("@")[0] in scalar_masks:
            # 这些是单通道形变/遮挡权重图，不是可见贴图；L 模式且无 alpha 是正确格式。
            im = Image.open(path)
            arr = np.asarray(im)
            add(pid, "灰度遮罩格式", im.mode == "L",
                f"模式 {im.mode}（mask map 预期 L）")
            add(pid, "灰度遮罩有有效范围", arr.min() == 0 and arr.max() == 255,
                f"取值 [{int(arr.min())},{int(arr.max())}]，预期 0..255")
            continue
        im = Image.open(path)
        add(pid, "容器", im.mode in ("RGBA", "LA"), f"模式 {im.mode}")
        a = load_rgba(path)
        rgb, m = a[..., :3], alpha_mask(a)
        add(pid, "透明通道", (a[..., 3] == 0).any(), f"全透明像素 {int((a[...,3]==0).sum())}")
        add(pid, "不是空图", m.sum() > 0, f"不透明像素 {int(m.sum())}")
        side_ok = min(a.shape[0], a.shape[1]) >= MIN_SIDE_EXEMPT.get(pid, th["min_side"])
        if pid == "body_full":
            side_ok = side_ok and a.shape[1] >= th["body_min_w"]
        add(pid, "尺寸", side_ok, f"{a.shape[1]}x{a.shape[0]}")

        key = count_near(rgb, m, (255, 0, 255), 120)
        add(pid, "键色残留", key <= th["key_residue"], f"{key} 像素（上限 {th['key_residue']}）")
        ring = edge_ring(m)
        white = count_near(rgb, ring, (255, 255, 255), 24)
        rlen = int(ring.sum())
        wratio = white / max(rlen, 1)
        add(pid, "白边",
            (pid.split("@")[0] in WHITE_GARMENT
             or white <= th["white_edge"] or wratio <= th["white_edge_ratio"]),
            f"{white} 像素（上限 {th['white_edge']}）、"
            f"占边缘一圈 {wratio * 100:.1f}%（上限 {th['white_edge_ratio'] * 100:.0f}%，"
            f"环长 {rlen}）"
            + ("【白色衣料，本项豁免】" if pid.split("@")[0] in WHITE_GARMENT else ""))

        if palette:
            # ★ 差分发型（recolor_match 切出来的）的配色权威**另加一份：本体头发自己**。
            #   原因：色卡闸比的是"主色离色卡某一格有多远"，而色卡只有 3 格头发色
            #   （主色/暗部/蓝梢）。一件保留了柔和渐变的头发，必然有大量落在两格之间的
            #   中间调 —— 把它压到"每个主色都贴着某一格"才算过，等于逼着切件器把
            #   渐变重铺成平色，那正是 2026-10-18 被用户打回的那版双马尾的做法。
            #   本体头发贴图是已入库、已过验收的成品，拿它当第二份权威是说得通的：
            #   "挂件的颜色得能在角色自己的头发里找得到"。真正判"同不同源"的是
            #   下面的 ΔE 闸（整条分布比），色卡闸在这里只负责拦"画成另一个色系"。
            auth = palette
            pool = None
            if pid.split("@")[0] in ("hair_twin_l", "hair_twin_r",
                                     "hair_pony_back", "hair_long_back"):
                acc_ = []
                for hn in ("hair_back.png", "hair_side_l.png", "hair_side_r.png",
                           "hair_front.png"):
                    hp = os.path.join(sprites, hn)
                    if not os.path.exists(hp):
                        continue
                    ha = load_rgba(hp)
                    acc_.append(ha[..., :3][alpha_mask(ha)].astype(np.int32))
                if acc_:
                    pool = np.concatenate(acc_)[::3]      # 抽样，够用且快
            doms = dominant_colors(rgb, m)
            worst, worst_c = 0, None
            for (r, g, b, share) in doms:
                if share < 0.06:          # 占比太低的颜色（抗锯齿过渡色）不参与判定
                    continue
                dist = min(abs(r - pr) + abs(g - pg) + abs(b - pb) for pr, pg, pb, _ in auth)
                if pool is not None and dist > th["palette_dist"]:
                    # 色卡只有 3 格头发色，而保留渐变的发束必然有一堆**落在两格之间**
                    # 的中间调。这里改问一句更实在的话："这个颜色在角色**自己的头发**
                    # 里存在吗？"存在（池子里有 ≥0.3% 的像素离它 ≤70）就算过。
                    # 这不是放水：把判据从"贴着色卡某一格"换成"本体头发里真有这个颜色"，
                    # 恰恰是 2026-10-18 那次返修的核心 —— 要的是同源，不是平色。
                    dd = np.abs(pool - np.array([r, g, b])).sum(axis=1)
                    if float((dd <= th["palette_dist"]).mean()) >= 0.003:
                        dist = 0
                if dist > worst:
                    worst, worst_c = dist, (r, g, b, share)
            add(pid, "色卡", worst <= th["palette_dist"],
                f"最远主色距离 {worst}" + (f"（#{worst_c[0]:02X}{worst_c[1]:02X}{worst_c[2]:02X}"
                                        f" 占比 {worst_c[3]:.0%}）" if worst_c else ""))

        # 叠加类部件：必须落在身体剪影里（飘在体外 = 位置错）
        if rig and body_mask is not None and pid != "body_full":
            part_def = next((p for p in rig.get("parts", []) if p.get("id") == pid), None)
            body_def = next((p for p in rig.get("parts", []) if p.get("id") == "body_full"), None)
            if part_def and body_def:
                px, py = part_def["pos"]
                bx, by = body_def["pos"]
                ox, oy = int(px - bx), int(py - by)   # 部件相对身体图的偏移
                h, w = m.shape
                sub = np.zeros_like(body_mask)
                y0, x0 = max(oy, 0), max(ox, 0)
                y1, x1 = min(oy + h, body_mask.shape[0]), min(ox + w, body_mask.shape[1])
                if y1 > y0 and x1 > x0:
                    sub[y0:y1, x0:x1] = m[y0 - oy:y1 - oy, x0 - ox:x1 - ox]
                    inside = int((sub & body_mask).sum())
                    total = int(sub.sum())
                    ratio = inside / total if total else 0.0
                    add(pid, "落在身体内", ratio >= 0.95, f"{ratio:.1%} 的像素在身体剪影内")

                    # 形状：与身体同区域的 IoU（叠加件应当紧贴底图轮廓所在区域）
                    if pid.startswith(("eye", "mouth")) and anchors:
                        ey = anchors["points"].get("eye_line", [0, 0])[1]
                        hgt = anchors["meta"]["height_px"]
                        cy = (y0 + y1) / 2.0
                        tol = hgt * th["anchor_tol"]
                        label = "眼线" if pid.startswith("eye") else "嘴线"
                        ref = ey if pid.startswith("eye") else \
                            anchors["points"].get("mouth_line", [0, ey + hgt * 0.085])[1]
                        add(pid, f"对位({label})", abs(cy - ref) <= tol,
                            f"部件中心 y={cy:.0f}，参考 {ref:.0f}，容差 ±{tol:.0f}")

    # 全身图与设计图的形状比对（IoU）
    design = None
    dpath = os.path.join(root, "characters", character, "design")
    if body is not None and os.path.isdir(dpath):
        # 参照图必须是"这张全身图真正的来源"：短发/中长发是两张设计图，
        # 按文件名排序会拿错（IoU 会掉到 0.45，看起来像素材坏了，其实是比错了对象）。
        src_sheet = None
        rep_path = os.path.join(base, "sprites_report.json")
        if os.path.exists(rep_path):
            with open(rep_path, encoding="utf-8") as f:
                src_sheet = json.load(f).get("source")
        cand = [f for f in os.listdir(dpath) if f.startswith("design_sheet") and f.endswith(".png")]
        pick = None
        if src_sheet and os.path.exists(os.path.join(root, src_sheet)):
            pick = os.path.join(root, src_sheet)
        elif cand:
            pick = os.path.join(dpath, sorted(cand)[0])
        if pick:
            d = load_rgba(pick)
            drgb = d[..., :3]
            # 设计图是洋红底：键色之外的就是人物
            dm = np.abs(drgb.astype(int) - np.array([255, 0, 255])).sum(axis=2) > 150
            # 精灵图是从设计图里裁剪 + 缩放来的，直接整图比会把"位置和缩放差异"
            # 算成形状不符（实测 IoU 只有 0.42）。正确做法：两边都按 alpha 包围盒
            # 归一化到同一尺寸，再比形状。
            def bbox_crop(mask_arr):
                ys, xs = np.where(mask_arr)
                if ys.size == 0:
                    return None
                return mask_arr[ys.min():ys.max() + 1, xs.min():xs.max() + 1]

            dcrop, bcrop = bbox_crop(dm), bbox_crop(body_mask)
            if dcrop is None or bcrop is None:
                v = 0.0
            else:
                dimg = Image.fromarray((dcrop * 255).astype(np.uint8)).resize(
                    (bcrop.shape[1], bcrop.shape[0]), Image.NEAREST)
                v = iou(bcrop, np.asarray(dimg) > 127)
            design = v
            add("body_full", "形状(与设计图 IoU)", v >= th["iou"],
                f"IoU {v:.3f}（下限 {th['iou']}，参照 {os.path.basename(pick)}）")

    # ------------------------------------------------ 分段身体（有才查）
    seg_path = os.path.join(base, "sprites", "body_parts.json")
    anchor_path = os.path.join(base, "design", "anchors.json")
    if os.path.exists(seg_path) and os.path.exists(anchor_path):
        with open(seg_path, encoding="utf-8") as f:
            bp = json.load(f)
        with open(anchor_path, encoding="utf-8") as f:
            AP = json.load(f)["points"]
        SW, SH = bp["image_size"]
        ov = bp["overlap_px"]
        seg_parts = list(bp["parts"])
        # 手臂拆件（make_arm_parts.py）在场时，整条 seg_arm_l/r 作废，
        # 验收必须按 rig 实际用的四件（上臂/前臂）来叠，否则查的是过期素材。
        arm_path = os.path.join(base, "sprites", "arm_parts.json")
        armp = None
        if os.path.exists(arm_path):
            with open(arm_path, encoding="utf-8") as f:
                armp = json.load(f)
            seg_parts = [sp for sp in seg_parts
                         if sp["id"] not in ("seg_arm_l", "seg_arm_r")] + armp["parts"]
        # ★ Q36 手差分件（make_hand_parts.py）：手已经是**重绘件**，不再是 body_full
        #   的切片。静止合成要用常态手（hand_l/hand_r），张开/比心两档是另一套姿态，
        #   静止时透明度为 0，不叠。
        hand_path = os.path.join(base, "sprites", "hand_parts.json")
        handp = None
        if os.path.exists(hand_path):
            with open(hand_path, encoding="utf-8") as f:
                handp = json.load(f)
            # ⚠ 必须**原位替换**，不能追加到末尾：compose() 是按列表顺序叠的，
            #   追加 = 手画在袖子上面，和 rig 里的层序（手 138/139 < 袖 144/145）相反。
            #   那样一转腕，袖子里那截腕柄会反过来盖住袖子，判据就在袖子内部
            #   数出一片根本不存在的"洞"（实测 109px，坐标全在袖子里 y=649~675）。
            hnew = {q["id"]: q for q in handp["parts"]}
            seg_parts = [hnew.get(sp["id"], sp) for sp in seg_parts]
        # 鞋拆件（make_foot_parts.py）在场时，腿件切线以下已经被擦空，
        # 静止合成必须把**常态鞋**叠回去，否则"无损切分"会凭空少掉两只鞋。
        # 踮脚鞋（*_tip）不叠：它是同一个部位的另一套姿态，静止时 xfade 权重为 0。
        foot_path = os.path.join(base, "sprites", "foot_parts.json")
        footp = None
        if os.path.exists(foot_path):
            with open(foot_path, encoding="utf-8") as f:
                footp = json.load(f)
            seg_parts = seg_parts + [q for q in footp["parts"]
                                     if not q["id"].endswith("_tip")]
        miss = [sp["id"] for sp in seg_parts
                if not os.path.exists(os.path.join(base, sp["file"]))]
        add("分段", "部件齐全", not miss, f"{len(seg_parts)} 个部件" + (f"，缺 {miss}" if miss else ""))

        # ★ 第三十一问：肩枢轴以 arm_parts.shoulder_joint（真关节）为准，
        #   anchors 的 shoulder_l/r 只是剪影外缘，不能当枢轴。
        _SJ = (armp or {}).get("shoulder_joint") or {}
        _shl = _SJ.get("l", AP["shoulder_l"])
        _shr = _SJ.get("r", AP["shoulder_r"])
        piv = {"head": AP["neck"], "arm_l": _shl, "arm_r": _shr,
               "chest": AP["hip"], "leg_l": AP["hip"], "leg_r": AP["hip"],
               "forearm_l": AP.get("elbow_l", _shl),
               "forearm_r": AP.get("elbow_r", _shr)}
        parent = {"forearm_l": "arm_l", "forearm_r": "arm_r"}   # 前臂挂在上臂下面
        if footp:
            # 脚挂在腿下面，枢轴取脚踝（静止合成用不到角度，但组链必须完整）
            piv["foot_l"] = piv["foot_r"] = AP["ankle"]
            parent["foot_l"], parent["foot_r"] = "leg_l", "leg_r"
        if armp:
            # G4c2：手挂在前臂下面，枢轴 = make_arm_parts 实测的腕线
            for q in armp["parts"]:
                if q["id"].startswith("hand_"):
                    sd = q["id"].split("_")[1]
                    piv[f"hand_{sd}"] = q["pivot"]
                    parent[f"hand_{sd}"] = f"forearm_{sd}"

        # ★★★ Q50：**静止时引擎根本不画的差分件，离线合成也不许画。**
        #   引擎口径（zrig.c:3463）：alpha = clamp(1 + Σ(scale·参数 + offset))。
        #   肘折线 / 肘补件 / 肘内侧褶布这三件的 alpha 都绑在肘角上，参数取
        #   默认值（0）时算出来 ≤0 ⇒ **一个像素都不显**。
        #   离线合成器原先不认这条，照画不误：褶布是一块按折肘姿势量出来的
        #   大楔形布，摊在伸直的手臂旁边，和袖子一起把背景围出一圈，
        #   「关节不露底(肘)」直接报 882 px 假空洞。
        #   这不是调阈值 —— 阈值还是 60 —— 是把**离线合成对齐引擎的真实行为**。
        _zero_rest = set()
        try:
            _rigj = json.load(open(os.path.join(base, "rig.json"), encoding="utf-8"))
            _pdef = {q["id"]: float(q.get("default", 0.0)) for q in _rigj.get("params", [])}
            _acc = {}
            for q in _rigj.get("params", []):
                v = float(q.get("default", 0.0))
                for b in q.get("binds", []):
                    if b.get("part") and b.get("param") == "alpha":
                        _acc.setdefault(b["part"], 0.0)
                        _acc[b["part"]] += float(b.get("scale", 1.0)) * v + float(b.get("offset", 0.0))
            _zero_rest = {k for k, v in _acc.items() if 1.0 + v <= 0.001}
        except Exception:
            _zero_rest = set()

        def compose(angles, offsets=None):
            """按层序叠出整个人；angles 按组给旋转角（度，绕锚点）。
               子组（前臂）要先绕自己的关节转，再跟着父组绕父关节转。
               offsets 按**部件 id** 给像素平移（头发摆动压力测试用）。
               静止 alpha=0 的差分件（_zero_rest）跳过 —— 引擎也不画。"""
            offsets = offsets or {}
            c = Image.new("RGBA", (SW, SH), (0, 0, 0, 0))
            for sp in sorted(seg_parts, key=lambda q: q["layer"]):
                if sp["id"] in _zero_rest:
                    continue
                im = Image.open(os.path.join(base, sp["file"])).convert("RGBA")
                if sp["id"] in offsets:
                    # 按引擎的 bend 曲线 tip 来剪切：顶边（发根）不动，
                    # 越往下位移越大（权重 t²，和 zimg_bend_factor 一致）。
                    # 整件平移是假的压力测试：那会把钉死在头皮上的发根也挪走。
                    ox, oy = offsets[sp["id"]]
                    arr = np.asarray(im).copy()
                    hgt = arr.shape[0]
                    outa = np.zeros_like(arr)
                    for r in range(hgt):
                        t = r / max(1, hgt - 1)
                        kx, ky = int(round(ox * t * t)), int(round(oy * t * t))
                        rr = r + ky
                        if not (0 <= rr < hgt):
                            continue
                        if kx >= 0:
                            outa[rr, kx:] = arr[r, :arr.shape[1] - kx] if kx else arr[r]
                        else:
                            outa[rr, :kx] = arr[r, -kx:]
                    im = Image.fromarray(outa)
                lay = Image.new("RGBA", (SW, SH), (0, 0, 0, 0))
                lay.paste(im, tuple(sp["pos"]))
                g = sp["group"]
                while g:
                    ang = angles.get(g, 0.0)
                    if ang:
                        px, py = piv[g]
                        lay = lay.rotate(ang, resample=Image.BICUBIC,
                                         center=(float(px), float(py)))
                    g = parent.get(g, "")
                c.alpha_composite(lay)
            return np.asarray(c)[..., 3] > 24

        if not miss:
            body_m = alpha_mask(load_rgba(os.path.join(base, "sprites", "body_full.png")))
            flat = compose({})
            lost_m = body_m & ~flat
            # ★ Q37：手的放松档**换回原画件**了（用户："之前那个参考图的手无法做成
            #   部件吗？"）。Q36 那版程序化重画的手被判"完全成怪物"，整个作废。
            #   所以这条"无损切分"对手**重新适用** —— 不再扣除任何重绘区，
            #   手腕那一块和身上别处一个标准：切丢一个像素就是红。
            lost = int(lost_m.sum())
            # 静止时把部件叠回去，必须和原图一模一样：少一块就是切丢了东西
            add("分段", "无损切分", lost == 0,
                f"静止合成比原图少 {lost} 像素")

        # ★ Q37 手部件的四条不变量。方案变了，判据跟着变：
        #     放松档 = 原画件（上面"无损切分"已经在守它）
        #     塗り足し = 独立部件 hand_{side}_pad，挂**前臂**组（袖の中の腕の続き）
        #     差分档 = hand_{side}_{open,heart}（生图，腕口按原画手对齐）
        #   所以这里守的是"差分件接得上袖口"+"塗り足し真的在袖子里"。
        if not miss and handp:
            hand_imgs = {q["id"]: load_rgba(os.path.join(base, q["file"]))
                         for q in handp["parts"]}
            armp_parts = (armp or {}).get("parts", [])
            for side in ("l", "r"):
                art_id = handp["art_base"][side]
                art_q = next((z for z in armp_parts if z["id"] == art_id), None)
                art_m = (alpha_mask(load_rgba(os.path.join(base, art_q["file"])))
                         if art_q else None)
                art_area = int(art_m.sum()) if art_m is not None else 0
                # 腕线 = 原画手件里**最窄**的那一行（＝袖口位置），现量不写死
                wline = None
                if art_m is not None:
                    rows = art_m.sum(axis=1)
                    top = art_q["pos"][1]
                    cand = [(int(rows[y]), y) for y in range(min(14, art_m.shape[0]))
                            if rows[y] > 0]
                    if cand:
                        wline = top + min(cand)[1]
                pad_q = next(z for z in handp["parts"] if z["id"] == f"hand_{side}_pad")
                pad_m = alpha_mask(hand_imgs[pad_q["id"]])
                # ① 塗り足し必须挂在**前臂**组上。Q37 实拍教训：挂在 hand 组上
                #    它会跟着手转，手一摆就甩出袖口变成一颗肉球
                #    （logs/asset_qa/q37_hand_check.png 改型前第 3 格）。
                add("手", f"hand_{side}_pad 挂前臂组", pad_q["group"] == f"forearm_{side}",
                    f"组={pad_q['group']}（官方口径：袖の中の腕の続き属前臂，"
                    f"挂手上会跟着手转甩出袖口）")
                # ② 塗り足し不许比袖口内宽还宽：宽了就会从袖子边上冒出来
                fore = [z for z in armp_parts if z["id"] == f"arm_{side}_fore"]
                cuff_w = 0.0
                if fore and wline:
                    fm = alpha_mask(load_rgba(os.path.join(base, fore[0]["file"])))
                    fy = wline - fore[0]["pos"][1] - 2     # 腕线往上 2px＝袖口里
                    if 0 <= fy < fm.shape[0]:
                        cuff_w = float(fm[fy].sum())
                add("手", f"hand_{side}_pad 不超袖口", pad_q["size"][0] <= cuff_w + 2,
                    f"塗り足し宽 {pad_q['size'][0]}px，袖口内宽 {cuff_w:.0f}px"
                    f"（宽了转腕时会从袖子边上露出来）")
                # ③ 塗り足し要真的塞进袖子：顶边高过腕线 ≥10px
                if wline:
                    add("手", f"hand_{side}_pad 塞进袖子", pad_q["pos"][1] <= wline - 10,
                        f"顶边 y={pad_q['pos'][1]}，腕线 y={wline}"
                        f"（至少塞 10px，转腕时才不露断面）")
                # ④ 差分档：面积不许缩水成一根棍，且腕口要和原画手对得上
                for pose in sorted(k for k in handp["poses"] if k):
                    pid = f"hand_{side}_{pose}"
                    q = next(z for z in handp["parts"] if z["id"] == pid)
                    m = alpha_mask(hand_imgs[pid])
                    area = int(m.sum())
                    add("手", f"{pid} 面积够", art_area and area >= art_area * 0.55,
                        f"差分件 {area}px / 原画手 {art_area}px = "
                        f"{area / max(art_area, 1) * 100:.0f}%（下限 55%）")
                    # 腕口宽度要落在原画腕宽的 ±45% 内：
                    # 生图件会连着画一小截小臂，定标搞错就会整只手放大 1.8 倍（Q37 踩过）
                    ww = handp["checks"]["wrist_w"][pid]
                    base_w = handp["checks"]["wrist_w"][f"hand_{side}_pad"]
                    add("手", f"{pid} 腕口对得上",
                        0.45 * base_w <= ww <= 1.45 * base_w,
                        f"腕口宽 {ww}px vs 原画腕宽 {base_w}px"
                        f"（差太多＝定标时把小臂断面当腕口量了）")

            # —— 鞋拆件（T24.5）：踮脚这件事全靠三条不变量撑着，机器来校 ——
            #   ① 两张姿态图都必须**触地**（鞋底在同一行）——否则踮脚变浮空；
            #   ② 踮脚鞋的鞋口要比常态鞋正好高 lift（身体也升 lift，两边才对得上）；
            #   ③ 腿件切线以下必须擦干净，且常态鞋往上盖过切线至少 lift
            #      （不然身体升起来时腿和鞋之间会裂开一条缝）。
            if footp:
                lift = float(footp["lift_px"])
                gy = int(footp["ground_y"]) - 1
                cutline = int(footp["cut"]["leg_cut_y"])
                for side in ("l", "r"):
                    ck = footp["checks"]["foot_" + side]
                    add("鞋", f"常态鞋触地({side})", ck["flat_bottom"] == gy,
                        f"鞋底在 y={ck['flat_bottom']}，地面 y={gy}")
                    add("鞋", f"踮脚鞋触地({side})", ck["tip_bottom"] == gy,
                        f"鞋底在 y={ck['tip_bottom']}，地面 y={gy}（差一行就是踮脚时脚离地）")
                    add("鞋", f"踮脚鞋鞋口抬高={lift:.0f}px({side})",
                        abs(ck["collar_rise"] - lift) <= 1.0,
                        f"实测抬高 {ck['collar_rise']}px，rig 的 root.dy 按 {lift:.0f}px 配套")
                for lid, fl in (("seg_leg_l", "l"), ("seg_leg_r", "r")):
                    lp = next((q for q in bp["parts"] if q["id"] == lid), None)
                    if not lp:
                        continue
                    la = load_rgba(os.path.join(base, lp["file"]))[..., 3] > 24
                    ly = cutline - lp["pos"][1]
                    bot = lp["pos"][1] + la.shape[0]
                    left = int(la[max(0, ly):].sum()) if ly < la.shape[0] else 0
                    add("鞋", f"腿件切线以下已清空({fl})", left == 0,
                        f"{lid} 在 y≥{cutline} 还剩 {left} 像素（鞋归脚件管）")
                    # 画布也要裁到切线：引擎的 bend 曲线按**贴图画布**铺 0..1，
                    # 画布探到地面以下的话，脚踝那条线就不是 t=1 了 ——
                    # tip 从 1.00 掉到 0.59（摆腿少 42%），sine 从 0 涨到 0.65
                    # （屈膝把整只脚抬离地面）。这两个毛病同一个上游。
                    add("鞋", f"腿件画布裁到切线({fl})", bot <= cutline,
                        f"{lid} 画布底边 y={bot}，切线 y={cutline}"
                        f"（多出来的 {bot - cutline}px 空白会把 bend 曲线的 t=1 推到地底下）")
                for q in footp["parts"]:
                    if q["id"].endswith("_tip"):
                        continue
                    over = cutline - q["pos"][1]
                    add("鞋", f"常态鞋盖过切线≥{lift:.0f}px({q['id'][-1]})", over >= lift,
                        f"只盖过 {over}px；身体升 {lift:.0f}px 时腿脚之间会裂缝")

            # —— 肩关节三件套（G102/G108，2026-10-15）——
            #   ① 躯干上不许再留袖子：留了就是那块不跟着手臂转的青色三角（用户报的
            #      "部件和链接没做好"）。判据写成"躯干压在上臂芯区的像素"，
            #      比数青色像素稳：帽檐内衬也是青的，数颜色会误伤。
            #   ② 袖根件静止时必须**一个像素都看不见**（靠遮挡关系，不是靠"看不出来"）。
            #   ③ 上臂上半段不许再细过前臂太多（G108 用户原话"上臂看起来很细十分不平衡"）。
            if armp and all(any(q["id"] == f"arm_{s}_root" for q in armp["parts"])
                            for s in ("l", "r")):
                def _ero(m, n):
                    out = m.copy()
                    for _ in range(n):
                        o = out.copy()
                        o[1:, :] &= out[:-1, :]; o[:-1, :] &= out[1:, :]
                        o[:, 1:] &= out[:, :-1]; o[:, :-1] &= out[:, 1:]
                        out = o
                    return out

                def _plate(pid):
                    q = next(p for p in seg_parts if p["id"] == pid)
                    a = load_rgba(os.path.join(base, q["file"]))[..., 3]
                    buf = np.zeros((SH, SW), np.uint8)
                    buf[q["pos"][1]:q["pos"][1] + a.shape[0],
                        q["pos"][0]:q["pos"][0] + a.shape[1]] = a
                    return buf, q

                def _rowspan(m, rows):
                    out = []
                    for y in rows:
                        idx = np.nonzero(m[y])[0]
                        if idx.size:
                            out.append(int(idx.max() - idx.min() + 1))
                    return np.array(out) if out else np.array([0])

                torso_a, torso_q = _plate("seg_torso")
                for side in ("l", "r"):
                    up_a, _ = _plate(f"arm_{side}_upper")
                    rt_a, rt_q = _plate(f"arm_{side}_root")
                    fo_a, _ = _plate(f"arm_{side}_fore")
                    core = _ero(up_a > 200, 6)
                    keep = int(((torso_a > 128) & core).sum())
                    add("肩关节", f"躯干上没留袖子({side})", keep <= 40,
                        f"躯干压在上臂芯区 {keep} 像素（上限 40）"
                        f"——留下来的那块不跟手臂转，抬手就是一块悬空的青色")
                    # ★★★ Q42：遮挡者里要算上 **arm_*_cap（肩球）**。
                    #   round_arm_sockets.py 把「关节正圆以内 + 枢轴以上」的袖料
                    #   从 upper 搬进了 cap（层 142/143，恒在袖根 95/96 和躯干 100
                    #   之上、且 Q42 起不再淡出），所以这块遮挡**换了件承担**。
                    #   不把它算进来，这条就会在\"实际一个像素都没露\"的情况下报
                    #   91/48 px —— 判据本身过时了，不是素材坏了。
                    #   （实测：算上 cap 后两侧都正好 0。）
                    cap_a, _ = _plate(f"arm_{side}_cap")
                    show = int(((rt_a > 40) & ~(torso_a > 200) & ~(up_a > 200)
                                & ~(cap_a > 200)).sum())
                    add("肩关节", f"袖根静止时完全藏住({side})", show == 0,
                        f"袖根露出 {show} 像素（必须 0：它是补画的，"
                        f"只能靠夹克/袖子/肩球压住）")
                    add("肩关节", f"袖根画在躯干底下({side})",
                        rt_q["layer"] < torso_q["layer"],
                        f"袖根层 {rt_q['layer']} < 躯干层 {torso_q['layer']}"
                        f"（反过来静止时就直接糊在夹克上）")
                    rows = np.nonzero((up_a > 128).any(axis=1))[0]
                    frows = np.nonzero((fo_a > 128).any(axis=1))[0]
                    if rows.size and frows.size:
                        half = rows[:len(rows) // 2]
                        w_top = float(np.median(_rowspan((up_a > 128) | (rt_a > 128), half)))
                        w_fore = float(np.median(_rowspan(fo_a > 128, frows)))
                        r = w_top / w_fore if w_fore else 0.0
                        add("肩关节", f"上臂上半段不比前臂细太多({side})", r >= 0.80,
                            f"上臂上半段中位 {w_top:.0f}px / 前臂中位 {w_fore:.0f}px = {r:.2f}"
                            f"（下限 0.80；没补袖根时是 0.57~0.60，用户一眼就看出来了）")

            # —— 袖缝内缘不许夹带夹克白（G112，2026-10-15）——
            # 症状：手臂一转开，白夹克和青袖之间多出一道白边，像裂了条缝（用户第三次验收截图3）。
            # 根因：切袖子时 soft() 往外羽化 2px，把夹克那边的白像素一起切进了袖片；
            # 静止时它正压在夹克上看不出来，一转就跟着甩出来。
            # 不变量 = make_arm_parts.seam_trim 的后置条件：**袖片里任何实心像素，
            # 都不许比这一行最内侧的青色再往里超过 SEAM_KEEP(2) 像素。**
            # 为什么要有这条闸：那个 bug 第一次修的时候因为 uint8 回绕静默失效了
            # （白的 g-r 算成 253 > 20 → 白被判成青），747 项全绿但一个像素没裁。
            if armp:
                _KEEP, _CUFF = 2, 36
                _wr = (armp.get("checks") or {}).get("wrist_y") or {}
                for side, _inner_right in (("l", True), ("r", False)):
                    for seg in ("upper", "fore"):
                        pid = f"arm_{side}_{seg}"
                        q = next((p for p in armp["parts"] if p["id"] == pid), None)
                        if not q:
                            continue
                        im = load_rgba(os.path.join(base, q["file"]))
                        aa = im[..., 3]
                        c3 = im[..., :3].astype(np.int16)   # ⚠ 必须转 int：uint8 相减会回绕
                        _r, _g, _b = c3[..., 0], c3[..., 1], c3[..., 2]
                        tl = (_g - _r > 20) & (_b - _r > 10) & (_g > 120)
                        ylim = (_wr.get(side, 10 ** 9) - _CUFF) if seg == "fore" else 10 ** 9
                        bad = worst = 0
                        for y in range(aa.shape[0]):
                            if q["pos"][1] + y > ylim:
                                continue
                            sol = aa[y] >= 90
                            if sol.sum() < 4:
                                continue
                            t = np.nonzero(tl[y] & sol)[0]
                            if t.size == 0:
                                continue
                            xs = np.nonzero(sol)[0]
                            over = int((xs > t.max() + _KEEP).sum()) if _inner_right \
                                else int((xs < t.min() - _KEEP).sum())
                            if over:
                                bad += 1
                                worst = max(worst, over)
                        add("肩关节", f"袖片内缘没夹带夹克白({pid})", bad <= 2 and worst <= 4,
                            f"越界行 {bad}（上限 2），单行最大越界 {worst}px（上限 4）"
                            f"——设计值 0/0；没裁时 4 件都是 95%~100% 的行越界")

            def hole_mask(a, y0, y1):
                """这一段里的"内部空洞"掩码：透明、但上下左右都还有身体。"""
                sl = a[max(0, y0):min(SH, y1)]
                if sl.size == 0:
                    return np.zeros((0, 0), bool)
                up = np.maximum.accumulate(sl, 0); dn = np.maximum.accumulate(sl[::-1], 0)[::-1]
                lf = np.maximum.accumulate(sl, 1); rt = np.maximum.accumulate(sl[:, ::-1], 1)[:, ::-1]
                return (~sl) & up & dn & lf & rt

            def holes(a, y0, y1):
                return int(hole_mask(a, y0, y1).sum())

            # —— AI 重绘真素材的质量门禁（D20：证据数字必须被机器校，不能只写在报告里）——
            mp_path = os.path.join(base, "sprites", "mouth_parts.json")
            if os.path.exists(mp_path):
                mpj = json.load(open(mp_path, encoding="utf-8"))
                ck = mpj.get("checks", {})
                reg = mpj.get("register", {})
                if reg:
                    add("真素材", "张嘴配准", reg.get("ncc", 0) >= 0.85,
                        f"虹膜配准 NCC {reg.get('ncc')}（下限 0.85）")
                    add("真素材", "口内有牙", ck.get("teeth_px", 0) >= 5,
                        f"牙 {ck.get('teeth_px', 0)} 像素（下限 5）")
                    add("真素材", "口内有舌", ck.get("tongue_px", 0) >= 30,
                        f"舌 {ck.get('tongue_px', 0)} 像素（下限 30）")
                    line_y = mpj.get("line", {}).get("y0", 0)
                    dy = abs(mpj.get("anchor_pos", [0, 0])[1] - (line_y + 2))
                    add("真素材", "张嘴对齐笑线", dy <= 3.0,
                        f"上沿离嘴线 {dy:.1f} 像素（上限 3）")
            ec_path = os.path.join(base, "sprites", "eye_closed_parts.json")
            if os.path.exists(ec_path):
                ecj = json.load(open(ec_path, encoding="utf-8"))
                add("真素材", "闭眼配准", ecj.get("register", {}).get("ncc", 0) >= 0.6,
                    f"脸部 NCC {ecj.get('register', {}).get('ncc')}（下限 0.6）")
                for ey in ecj.get("eyes", []):
                    c = ey["checks"]
                    add("真素材", f"闭眼盖住原画({ey['side']})", c["cover_ratio"] >= 0.99,
                        f"盖住 {c['cover_ratio']*100:.1f}%（下限 99%）")
                    add("真素材", f"闭眼接缝({ey['side']})", c["seam_mean_abs"] <= 12.0,
                        f"接缝色差 {c['seam_mean_abs']}（上限 12）")

            # —— 袖下躯干完整性（手臂外展方向才看得见的东西）——
            # 注意符号：PIL 的 rotate 是**画面逆时针**，引擎的 rot_deg 是顺时针，
            # 两者相反。下面的 25° 压力姿势按 PIL 符号写的是「两条手臂往身体内侧转」，
            # 那个方向是安全方向；真正会露馅的是**外展**（右臂 PIL 正角 / 左臂 PIL 负角）。
            # 外展时腋下本来就该露出背景，所以不能用整体空洞来判，改判两件事：
            #   ① 躯干自己不能被挖出新窟窿；② 新切口必须描了线稿（否则是"纸片剪开"感）。
            if armp:
                tor = next((q for q in bp["parts"] if q["id"] == "seg_torso"), None)
                if tor:
                    ta = load_rgba(os.path.join(base, tor["file"]))
                    tx, ty = tor["pos"]
                    th_, tw_ = ta.shape[:2]
                    ba = load_rgba(os.path.join(base, "sprites", "body_full.png"))[ty:ty + th_, tx:tx + tw_]
                    def inner_holes(mk):
                        up = np.maximum.accumulate(mk, 0); dn = np.maximum.accumulate(mk[::-1], 0)[::-1]
                        lf = np.maximum.accumulate(mk, 1); rt = np.maximum.accumulate(mk[:, ::-1], 1)[:, ::-1]
                        return (~mk) & up & dn & lf & rt
                    newh = int((inner_holes(alpha_mask(ta)) & ~inner_holes(alpha_mask(ba))).sum())
                    add("分段", "袖下躯干无新窟窿", newh <= th["joint_hole"],
                        f"躯干自身新增内部空洞 {newh} 像素（上限 {th['joint_hole']}）")
                ol = int(armp.get("checks", {}).get("outline_px", 0))
                add("分段", "切口描线稿", ol >= 200, f"补画区描了 {ol} 像素线稿（下限 200）")

            # 压力姿势：远超实际动作，关节处仍然不能露底。
            # 手臂拆件前只能转 10°（整条手臂一块板，再多就露切口）；
            # 拆件后袖下躯干已补绘、肘部有 24px 重叠带，按挥手的真实幅度 25° 压。
            if armp:
                pose = compose({"head": -15.0, "arm_l": 25.0, "arm_r": -25.0,
                                "forearm_l": 20.0, "forearm_r": -20.0,
                                "hand_l": 20.0, "hand_r": -20.0})
            else:
                pose = compose({"head": -15.0, "arm_l": 10.0, "arm_r": -10.0})
            bands = [("颈", int(AP["neck"][1])), ("肩", int(AP["shoulder"][1])),
                     ("髋", int(AP["hip"][1]))]
            if armp:
                bands.append(("肘", int(AP["elbow_l"][1])))
            for label, y in bands:
                d = holes(pose, y - ov * 2, y + ov * 2) - holes(flat, y - ov * 2, y + ov * 2)
                add("分段", f"关节不露底({label})", d <= th["joint_hole"],
                    f"压力姿势新增空洞 {d} 像素（上限 {th['joint_hole']}）")

            # —— 头发摆动压力测试 ——（教训：静止 0 像素差只是及格线）
            # 侧发/后发一摆，背后那块脸颊/耳朵/脖子就得有东西；没按 D19 重绘补画
            # 或者塗り足し铺得不够，静止时一点看不出来，动起来才露底。
            # 这里把头发零件整体平移到**超过实际摆幅**的距离，再数新增空洞。
            sway_ids = [sp["id"] for sp in seg_parts
                        if sp["id"].startswith("hair_side") or sp["id"] == "hair_back"]
            if sway_ids:
                y_lo, y_hi = 0, int(AP["neck"][1]) + ov * 2
                base_hm = hole_mask(flat, y_lo, y_hi)
                # 只数「身体里面深处」的洞：头发本来就长在剪影边上，一摆开，
                # 外缘那一两像素露出背景是**正确**的（原画里那块就是背景，
                # 重绘的脸比带发的轮廓窄）。把剪影往里腐蚀 4px 再数，
                # 剩下的才是"背后该有脸却没画"的真漏洞。
                body_in = Image.fromarray(
                    ((flat[max(0, y_lo):min(SH, y_hi)]) * 255).astype(np.uint8))
                deep = np.array(body_in.filter(ImageFilter.MinFilter(9))) > 127
                # 只甩左右：上下甩是用整行位移模拟的，行与行的取整差会在零件
                # **自己身上**切出 1px 横缝（引擎的 bend 是反向采样，不会有），
                # 那是测试工具的假阳性，不是素材的问题。
                for dx, dy in ((-12, 0), (12, 0)):
                    m = compose({}, {i: (dx, dy) for i in sway_ids})
                    # 必须**逐像素**比：头发一挪会顺手盖住别处的缝，拿总数相减
                    # 会被这几百像素的负数吃掉（实测挖了个 3x3 的洞照样"通过"）。
                    d = int((hole_mask(m, y_lo, y_hi) & ~base_hm & deep).sum())
                    add("分段", f"头发摆动不露底({dx:+d},{dy:+d})",
                        d <= th["sway_hole"],
                        f"发梢甩 ({dx:+d},{dy:+d}) 后身体内部新增空洞 {d} 像素"
                        f"（上限 {th['sway_hole']}）")

            # —— 手腕（G4c2）：手转 20°，袖口和手之间不能豁开 ——
            #   不能拿"髋 ± 2ov"那种整行横带来数：腕线 y=666 正好落在裙摆上，
            #   数出来的全是裙子和腿的事（实测 -1404，跟手腕一点关系没有）。
            #   这里只在**手自己那一小块**（手的外接框往外放 8px）里数内部空洞。
            for q in (armp["parts"] if armp else []):
                if not q["id"].startswith("hand_"):
                    continue
                hx, hy = q["pos"]
                hw, hh = q["size"]
                wy = int(q["pivot"][1])
                # 只看腕线上下这一小段。放到整只手上就变成在数**手指缝**了
                # （手一转指缝形状就变，实测 135 像素，跟袖口严不严毫无关系）。
                y0w, y1w = wy - 18, wy + 14
                colm = np.zeros((SH, SW), bool)
                colm[:, max(0, hx - 8):min(SW, hx + hw + 8)] = True
                sl = slice(max(0, y0w), min(SH, y1w))

                def vhole(a):
                    """袖口和手之间豁开的缝：只看**同一列上下都还有身体**。
                       不能用四向的 hole_mask —— 手一转，缝是朝外敞开的，
                       左右那两条\"还有身体\"的条件根本不成立，缝再大也数不出来
                       （实测：把袖子里那截皮肤删掉，四向判据照样是 0）。"""
                    b = a[sl]
                    up = np.maximum.accumulate(b, 0)
                    dn = np.maximum.accumulate(b[::-1], 0)[::-1]
                    return (~b) & up & dn

                # 压力姿势要**只转这只手**：整条手臂一起转的话，手早就转出这个框了，
                # 框里一片空白，数出来当然是 0（第一版就是这么假过的）。
                dw = 0
                where = ""
                for sgn in (20.0, -20.0):
                    hp = compose({q["group"]: sgn})
                    dm = vhole(hp) & ~vhole(flat) & colm[sl]
                    n = int(dm.sum())
                    if n > dw:
                        dw = n
                        yy, xx = np.where(dm)
                        # 把洞的位置一起报出来：没有坐标就只能靠猜，
                        # 第三十六问在这条上白跑过一轮（G4c2）
                        where = (f"；转 {sgn:+.0f}° 时洞在 y={int(yy.min()) + y0w}"
                                 f"~{int(yy.max()) + y0w}、x={int(xx.min())}~{int(xx.max())}")
                add("分段", f"关节不露底(腕 {q['id'][-1]})", dw <= th["joint_hole"],
                    f"手单独转 ±20° 后腕部新增空洞 {dw} 像素（上限 {th['joint_hole']}）{where}")

            # —— 裙摆接缝（G4c2）：腿一摆，裙摆下沿那条缝不能漏背景 ——
            # 腿是 bend（顶边=裙子里的大腿根钉死、越往下摆幅越大），所以这里用
            # 和引擎一样的 t² 剪切来压，而不是整件平移/旋转。
            #   口径：只数"**静止时是身体、现在变背景**"的像素，而且只在裙摆下沿
            #   往下 24px 这条带里数 —— 腿摆开之后两腿之间的空档本来就该变大，
            #   那是合法的，不能算露底。
            tt_list = bp.get("thigh_top")
            leg_ids = [sp["id"] for sp in seg_parts if sp["id"].startswith("seg_leg_")]
            if tt_list and leg_ids:
                tta = np.array(tt_list, int)
                band = np.zeros((SH, SW), bool)
                for xx in np.flatnonzero(tta > 0):
                    band[tta[xx]:tta[xx] + 24, xx] = True
                for dx in (-20, 20):
                    m = compose({}, {i: (dx, 0) for i in leg_ids})
                    d = int((band & flat & ~m).sum())
                    add("分段", f"裙摆接缝不露底(腿 {dx:+d}px)", d <= th["joint_hole"],
                        f"腿摆 {dx:+d}px 后裙摆下 24px 带内新露底 {d} 像素"
                        f"（上限 {th['joint_hole']}）")
                # 曲线写反是会反复犯的错（hair_back 就犯过一次）：
                # root = 底边固定、**顶端**摆 → 裙子里的大腿根直接甩出裙摆。
                # 实测 root 曲线摆 ±20px 就漏 708/763 像素，所以这里静态卡死。
                if rig:
                    for pr in rig.get("params", []):
                        if pr["id"] not in ("ParamLegL", "ParamLegR"):
                            continue
                        okc = all(b.get("curve") == "tip" for b in pr.get("binds", [])
                                  if b.get("param") == "bend_x")
                        add("分段", f"{pr['id']} 用 tip 曲线", okc,
                            "腿的 bend 必须 tip（裙摆下沿钉死）；写 root 会把大腿根甩出裙子")

            # —— @2x 换算必须连绑定一起换（G111，2026-10-15）——
            # T30.1 把切件换成 @2x 时只把部件的 scale 乘了 0.5，**没动参数绑定**。
            # 对标量 scale 没事（zrig 里通道是乘性的：s×p_s，s 减半 + 素材翻倍 = 等价），
            # 但 `scale:[sx,sy]` 走的是加性通道（part_sy = scale_y + (p_sy-1)），
            # 基准减半了、增量没减 ⇒ **实际形变整整放大 2 倍**。
            # 后果：嘴张到最大从 21px 变成 41px，下沿长到下巴以下（用户第三次验收截图1/2）。
            if rig:
                _pm = {p["id"]: p for p in rig.get("parts", [])}
                for pr in rig.get("params", []):
                    for b in pr.get("binds", []):
                        if b.get("param") not in ("sx", "sy"):
                            continue
                        p = _pm.get(b.get("part") or "")
                        if not p or not isinstance(p.get("scale"), list):
                            continue           # 标量 scale 是乘性的，@2x 不影响
                        if not p.get("hires"):
                            continue           # 没换 @2x 的件不用换算
                        add("嘴部", f"@2x 加性绑定已换算({pr['id']}→{p['id']}.{b['param']})",
                            bool(b.get("hires_halved")),
                            "数组 scale 的部件换成 @2x 之后，sx/sy 绑定必须同步减半"
                            "（make_rig 会打 hires_halved 标记）；漏了就是形变翻倍")

            # —— 嘴张到最大不许长过下巴（G111 的美术口径闸）——
            # 上面那条管的是\"换算有没有做\"，这条管\"做出来的嘴好不好看\"：
            # 两条都要，因为换算可以对、数值仍然可以被人手调歪。
            if rig and body_mask is not None:
                _pm = {p["id"]: p for p in rig.get("parts", [])}
                mk = _pm.get("mouth_mask")
                if mk and isinstance(mk.get("scale"), list):
                    _h = load_rgba(os.path.join(base, mk["file"])).shape[0]
                    _bd = 0.0
                    for pr in rig.get("params", []):
                        if pr["id"] != "ParamMouthOpenY":
                            continue
                        for b in pr.get("binds", []):
                            if b.get("part") == "mouth_mask" and b.get("param") == "sy":
                                _bd = b["scale"] * pr.get("max", 1.0)
                    open_h = _h * (mk["scale"][1] + _bd)
                    add("嘴部", "张到最大的开口高度合理", 16.0 <= open_h <= 26.0,
                        f"开口 {open_h:.1f}px（区间 16~26；1x 素材的设计值 20.9，"
                        f"@2x 漏换算时是 40.6）")
                    # 下巴线现量：中轴那一列、嘴线以下第一段连续肤色的末行。
                    sk = body
                    _sm = ((sk[..., 3] > 200) & (sk[..., 0] > 235) & (sk[..., 1] > 195)
                           & (sk[..., 1] < 245) & (sk[..., 2] > 170) & (sk[..., 2] < 238))
                    _col = np.nonzero(_sm[:, 210:232].sum(1) >= 14)[0]
                    _col = _col[(_col > 253) & (_col < 340)]
                    if _col.size:
                        chin = int(_col[0])
                        for _y in _col:
                            if _y - chin > 3:
                                break
                            chin = int(_y)
                        # 画布 y → body_full y：画布底对齐身体底，所以偏移 = 画布高 − 身体高
                        _oy = int(rig["canvas"]["h"]) - int(body.shape[0])
                        bottom = mk["pos"][1] - _oy + open_h
                        add("嘴部", "张到最大不越过下巴", bottom <= chin,
                            f"嘴下沿 body_full y={bottom:.0f}，下巴 y={chin}"
                            f"（越过去就是用户说的\"嘴巴位置偏下\"/一条拖到脖子的黑块）")

            # —— 键色垃圾像素 ——（教训：alpha=1 的纯绿像素被颜色外扩重写成亮绿点）
            # 纯绿 / 洋红这两种颜色在小寻的色卡里根本不存在，出现就是抠像或重绘的残留。
            junk_total, junk_where = 0, []
            for fn in sorted(os.listdir(os.path.join(base, "sprites"))):
                if not fn.endswith(".png"):
                    continue
                aj = load_rgba(os.path.join(base, "sprites", fn)).astype(int)
                Rj, Gj, Bj, Aj = aj[..., 0], aj[..., 1], aj[..., 2], aj[..., 3]
                vis = Aj > 40
                nj = int((vis & (Gj - np.maximum(Rj, Bj) > 60)).sum()
                         + (vis & (Rj - Gj > 60) & (Bj - Gj > 60) & (Rj > 150) & (Bj > 150)).sum())
                if nj:
                    junk_total += nj
                    junk_where.append(f"{fn}:{nj}")
            # —— 脸上不许再画着一只睁开的眼 ——（G4m：眼线二次拆件的静态闸）
            # 眨眼是靠"眼眶开口压扁 + 上眼线下滑"做的；只要 seg_head 的眼眶区里
            # 还留着原画的眼线/虹膜/眼白，眼眶一收就会把它露出来（实测半闭那一帧
            # 脸上浮着一只睁着的眼）。所以这里直接查像素。
            el_path = os.path.join(sprites, "eyeline_parts.json")
            if os.path.exists(el_path):
                with open(el_path, encoding="utf-8") as f:
                    el_js = json.load(f)
                head_arr = load_rgba(os.path.join(sprites, "seg_head.png")).astype(int)
                hx, hy = next(q["pos"] for q in bp["parts"] if q["id"] == "seg_head")
                for e in el_js.get("eyes", []):
                    side = e["side"]
                    px, py = e["patch_pos"]
                    sock_a = load_rgba(os.path.join(sprites, f"eye_{side}_socket.png"))[..., 3]
                    ph, pw = sock_a.shape
                    y0, x0 = py - hy, px - hx
                    sy0, sx0 = max(0, -y0), max(0, -x0)
                    y0, x0 = max(0, y0), max(0, x0)
                    y1 = min(head_arr.shape[0], y0 + ph - sy0)
                    x1 = min(head_arr.shape[1], x0 + pw - sx0)
                    reg = head_arr[y0:y1, x0:x1]
                    m = sock_a[sy0:sy0 + (y1 - y0), sx0:sx0 + (x1 - x0)] > 96
                    R, G, B, A = reg[..., 0], reg[..., 1], reg[..., 2], reg[..., 3]
                    lum = 0.299 * R + 0.587 * G + 0.114 * B
                    vis = m & (A > 40)
                    dark = vis & (lum < 120)                       # 眼线
                    blue = vis & (B - R > 25) & (B > 110)          # 虹膜
                    n_eye = int(dark.sum() + blue.sum())
                    add("眼部", f"脸上无残留睁眼({side})", n_eye <= th["eye_residue"],
                        f"seg_head 眼眶开口里还剩眼线 {int(dark.sum())} + 虹膜 "
                        f"{int(blue.sum())} 像素（上限 {th['eye_residue']}）")

            # —— 闭合笑线必须是「剪切」不是「复制」——（G107 的静态闸）
            # 2026-10-15 之前 sprites/mouth_open.png 是 tools/make_parts.py 用手填的框
            # 复制出来的，而 make_parts.py 根本不在 rebuild_parts.sh 里，于是它一直停在
            # 很久以前的旧坐标：实测落在 body_full y252..275，而真正的笑线在 y246..250，
            # **垂直零重叠** —— 那张"笑线件"里装的是下巴阴影和一角衣领。
            # 更要命的是原来那条笑线始终烙在 seg_head 上：张嘴时口内椭圆只盖得住中段，
            # 两端上翘的嘴角露在椭圆上方，像挂了两撇小胡子（用户反馈的"惊讶时嘴型重合"）。
            # 这两条闸分别盯住"剪对了地方"和"原件真的擦掉了"，少一条都能让它复发。
            mp_path = os.path.join(sprites, "mouth_parts.json")
            rp_path = os.path.join(sprites, "parts_report.json")
            if os.path.exists(mp_path) and os.path.exists(rp_path):
                with open(mp_path, encoding="utf-8") as f:
                    mp_js = json.load(f)
                with open(rp_path, encoding="utf-8") as f:
                    rp_js = json.load(f)
                ln = mp_js.get("line")
                mo = next((q for q in rp_js.get("parts", [])
                           if q.get("name") == "mouth_open.png"), None)
                if ln and mo:
                    mx0, my0 = mo["pos"]
                    mx1 = mx0 + mo["size"][0] - 1
                    my1 = my0 + mo["size"][1] - 1
                    covers = (mx0 <= ln["x0"] and mx1 >= ln["x1"]
                              and my0 <= ln["y0"] and my1 >= ln["y1"])
                    add("嘴部", "笑线件套准笑线",
                        covers,
                        f"mouth_open 覆盖 x{mx0}..{mx1} y{my0}..{my1}，"
                        f"实测笑线 x{ln['x0']}..{ln['x1']} y{ln['y0']}..{ln['y1']}"
                        f"{'' if covers else ' ← 没套住，等于没剪到笑线'}")

                    # 擦除判据：seg_head 上原笑线那一块不能再有"明显偏离周围肤色"的像素。
                    # 用色差而不是暗度 —— 笑线两端的嘴角高光比肤色还亮，只看暗度会漏掉。
                    hd = load_rgba(os.path.join(sprites, "seg_head.png")).astype(float)
                    hx2, hy2 = next(q["pos"] for q in bp["parts"] if q["id"] == "seg_head")
                    ex0, ey0 = ln["x0"] - hx2, ln["y0"] - hy2
                    ex1, ey1 = ln["x1"] - hx2, ln["y1"] - hy2
                    if 1 <= ex0 and ex1 < hd.shape[1] - 1 and 1 <= ey0 and ey1 < hd.shape[0] - 1:
                        top = hd[ey0 - 1, ex0:ex1 + 1, :3]
                        bot = hd[ey1 + 1, ex0:ex1 + 1, :3]
                        hh = ey1 - ey0 + 1
                        t = ((np.arange(hh, dtype=float) + 1.0) / (hh + 1.0))[:, None, None]
                        ref = top[None] * (1 - t) + bot[None] * t
                        blk = hd[ey0:ey1 + 1, ex0:ex1 + 1, :3]
                        dev = np.abs(blk - ref).max(axis=2)
                        n_left = int((dev > 24).sum())
                        add("嘴部", "笑线已从底图剪走",
                            n_left <= 8,
                            f"seg_head 原笑线区还剩 {n_left} 个偏离肤色>24 的像素"
                            f"（上限 8，最大偏离 {dev.max():.0f}）")

            # —— 乘算/加算零件必须压在底图的实心区上 ——（G66 的静态闸）
            # 腮红走 multiply、眼高光走 additive，这两种混合模式在**透明背景上是无效果的**：
            # 乘算乘不动 alpha=0 的像素，加算加在空气上也看不见。
            # 2026-10-14 实测踩过：腮红摆在画布 [311,300]，而 seg_head 在 y=300 的实心范围
            # 只有 x 345..491 —— 大半块画在脸轮廓外，满值腮红只带来 27 像素可见变化，
            # 表情 shy 用到 0.95 都看不出脸红。接口全绿、单测全绿，只有看图才发现。
            # —— 摸头区域必须罩住整张脸 ——（G67 的静态闸）
            # 区域 rect 原本是**按比例估**的（头 = 角色高的 24%，还假设头顶贴着 y=0），
            # 2026-10-14 实测：head 只到画布 y=310，而 seg_head 占到 y=385 ——
            # 嘴和下巴落在 body 里，点脸触发的是「摸身体」而不是「摸头」。
            # 接口全绿（region 确实返回了 body），只有把区域和素材几何摆一起比才看得出。
            hd_r = next((q for q in (rig or {}).get("regions", [])
                         if q.get("id") == "head"), None)
            hd_p = next((q for q in (rig or {}).get("parts", [])
                         if q.get("id") == "seg_head"), None)
            if hd_r and hd_p:
                hx0, hy0 = hd_p["pos"]
                ha = load_rgba(os.path.join(sprites, "seg_head.png"))[..., 3]
                hx1, hy1 = hx0 + ha.shape[1], hy0 + ha.shape[0]
                rx, ry, rw, rh = hd_r["rect"]
                inside = (rx <= hx0 and ry <= hy0 and rx + rw >= hx1 and ry + rh >= hy1)
                add("交互区域", "摸头区域罩住整张脸", inside,
                    f"head 区域 x{rx}..{rx + rw} y{ry}..{ry + rh}，"
                    f"而 seg_head 占 x{hx0}..{hx1} y{hy0}..{hy1}"
                    f"（露在外面的部分会被判成 body，点脸变成摸身体）")

            # —— 腮红必须压在实心脸上 ——（G66 的静态闸）
            # 腮红走 multiply，而**乘算在透明像素上是无效果的**：乘不动 alpha=0 的地方。
            # 2026-10-14 踩过：腮红摆在画布 [311,300]，但 seg_head 在 y=300 的实心范围
            # 只有 x 345..491（脸是上宽下窄的锥形），大半块画在轮廓外 —— 满值腮红只带来
            # 27 像素可见变化，表情 shy 吃到 0.95 都看不出脸红。
            # 接口返回 ok、单测全绿、参数回读也正确，只有渲染出来逐像素比才看得见。
            # 只查腮红：眼高光(highlight/star)压的是眼球不是脸，底图不同，不适用这条。
            bpj = os.path.join(sprites, "blend_parts.json")
            if os.path.exists(bpj):
                with open(bpj, encoding="utf-8") as f:
                    blend_js = json.load(f)
                head_a = load_rgba(os.path.join(sprites, "seg_head.png"))[..., 3]
                # 注意取 rig.json 的 pos：bp(seg_parts.json) 里的 pos 是**切图内坐标**，
                # 而 blend_parts.json 的 pos 是画布坐标，两者不能直接相减。
                hd = next((q for q in (rig or {}).get("parts", [])
                           if q.get("id") == "seg_head"), None)
                hx, hy = (hd["pos"] if hd else [0, 0])
                HH, HW = head_a.shape
                for side, cfg in (blend_js.get("blush") or {}).items():
                    part_a = load_rgba(os.path.join(root, "characters", character,
                                                    "forms", form, cfg["file"]))[..., 3]
                    ph, pw = part_a.shape
                    lx, ly = cfg["pos"][0] - hx, cfg["pos"][1] - hy   # 换到 seg_head 局部坐标
                    if lx < 0 or ly < 0 or lx + pw > HW or ly + ph > HH:
                        add("混合零件", f"腮红_{side} 在脸的画幅内", False,
                            f"腮红框换算到 seg_head 后是 [{lx},{ly}]+{pw}x{ph}，"
                            f"越出了 {HW}x{HH} 的脸部画幅")
                        continue
                    own = part_a > 24
                    if not own.any():
                        add("混合零件", f"腮红_{side} 非空", False, "整块腮红都是透明的")
                        continue
                    under = head_a[ly:ly + ph, lx:lx + pw] > 200
                    cover = float((own & under).sum()) / float(own.sum())
                    add("混合零件", f"腮红_{side} 压在实心脸上", cover >= 0.80,
                        f"{cover * 100:.0f}% 的不透明像素落在 seg_head 的实心区上"
                        f"（要求 ≥80%；multiply 画在透明处等于没画）")
                    if character == "xiaoxun" and form == "teen":
                        nonzero = int((part_a > 0).sum())
                        semitransparent = int(((part_a > 0) & (part_a < 255)).sum())
                        soft_ratio = semitransparent / max(1, nonzero)
                        peak = int(part_a.max())
                        add("混合零件", f"腮红_{side} 峰值柔边，无硬划痕",
                            peak <= 110 and soft_ratio >= 0.99,
                            f"alpha 峰值 {peak}/255、半透明占非透明像素 {soft_ratio:.1%}"
                            "（避免小尺寸时高对比划线抢过模板的淡腮红）")

            # —— 差分发型必须和本体头发**同源配色**（2026-10-18 用户打回）——
            # 用户看第一眼就说「色彩和形态完全不一样非常的违和」，而当时
            # 519 项自检 + 878 项单测全绿 —— 因为**没有一项在比颜色**。
            # 这条就是补那一刀：把挂件和本体头发都转进 CIE Lab，比两件事
            #   ① 平均色差 ΔE（Lab 欧氏距离）——"是不是同一个发色"；
            #   ② 明度标准差之差 ΔσL ——"发质/对比度像不像"（一件被压成平色的
            #      头发，平均色可能还对，σ 一定塌下去）。
            # 负向对照（必做）：把 git 里那版坏双马尾拿来跑，ΔE=9.7、ΔσL=8.4，
            # 两项都越线；现在这版 ΔE=0.1、ΔσL=2.1。闸门设在 5.0 / 6.0。
            hair_ref = [n for n in ("hair_back.png", "hair_side_l.png",
                                    "hair_side_r.png", "hair_front.png")
                        if os.path.exists(os.path.join(sprites, n))]
            hair_add = [n for n in ("hair_twin_l.png", "hair_twin_r.png",
                                    "hair_pony_back.png", "hair_long_back.png")
                        if os.path.exists(os.path.join(sprites, n))]
            if hair_ref and hair_add:
                ref_px = np.concatenate(
                    [solid_pixels(os.path.join(sprites, n)) for n in hair_ref])
                ref_lab = to_lab(ref_px)
                for n in hair_add:
                    got = solid_pixels(os.path.join(sprites, n))
                    if len(got) < 256:
                        continue
                    lab = to_lab(got)
                    dE = float(np.linalg.norm(lab.mean(axis=0) - ref_lab.mean(axis=0)))
                    dSD = abs(float(lab[:, 0].std() - ref_lab[:, 0].std()))
                    add("差分发型", f"{n[:-4]} 与本体头发同源配色",
                        dE <= th["hair_dE"] and dSD <= th["hair_dSD"],
                        f"平均色差 ΔE={dE:.1f}（上限 {th['hair_dE']}）、"
                        f"明度对比差 ΔσL={dSD:.1f}（上限 {th['hair_dSD']}）"
                        f"；基准 = {'/'.join(x[:-4] for x in hair_ref)}")

            add("素材", "无键色垃圾像素", junk_total <= th["junk_px"],
                f"纯绿/洋红残留 {junk_total} 像素（上限 {th['junk_px']}）"
                + ("，" + "、".join(junk_where[:4]) if junk_where else ""))

    # ——（T46.8）头部几何：藏件不许露底、头饰按实测头宽定标 ——
    #   2026-10-18 第九问打回的四个缺陷（人耳裸露在脸颊、后发壳平切口横在颧骨、
    #   发丝碎片、剪影缺一块）在既有闸门里**一项都查不出来**，因为它们查的是
    #   单个零件自己的像素，而这里坏掉的是**零件之间的遮挡关系**。
    #   量法、实测值和阈值余量写在 tools/head_silhouette.py 的文档串里。
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import head_silhouette as _hs
        _hs.ROOT = os.path.abspath(root)
        for r in _hs.hide_backing(character, form):
            add("头部几何",
                f"藏{r['part']}有件接管", r["ok"],
                f"{r['group']}:{r['entry']} 档自带的差分件盖住了它的 "
                f"{r['cover'] * 100:.1f}%（下限 {r['need'] * 100:.0f}%；"
                f"接管者只能是这一档自己的件，不算碰巧垫在底下的本体），"
                f"露出透明背景 {r['hole'] * 100:.2f}%"
                f"（上限 {r['max_hole'] * 100:.0f}%）")
        for r in _hs.headwear_fit(character, form):
            add("头部几何", f"{r['part']}按头宽定标", r["ok"],
                f"外宽 {r['width_px']} / 头部剪影宽 {r['head_width_px']} = "
                f"{r['ratio']:.2f} 倍（许可 1.10~1.40）；帽顶 y={r['top_y']}、"
                f"头顶 y={r['head_top_y']}（不许比头顶低 12 像素以上）")
    except Exception as _e:                                  # pragma: no cover
        add("头部几何", "头部几何闸可运行", False, "跑挂了：%s" % _e)

    # ---------------------------------------- 素材必须是真原画（见 FLAT_BY_DESIGN）
    try:
        import glob as _glob
        flat_n = 0
        for _p in sorted(_glob.glob(os.path.join(sprites, "*@2x.png"))):
            _pid = os.path.basename(_p)[:-len("@2x.png")]
            if _pid in {"armpit_mask", "skirt_mask", "skirt_mask_base"}:
                continue  # 单通道遮罩不是一张“原画精灵”，不参与色数判断。
            _im = load_rgba(_p)
            _m = alpha_mask(_im)
            _area = int(_m.sum())
            if _area < FLAT_MIN_AREA:
                continue
            _rgb = _im[:, :, :3][_m].astype(np.uint32)
            _c = int(len(np.unique((_rgb[:, 0] << 16) | (_rgb[:, 1] << 8) | _rgb[:, 2])))
            if _pid in FLAT_BY_DESIGN:
                # 豁免件也要查：万一哪天它**变花**了，说明有人拿它当画布画了东西
                add("素材真伪", f"{_pid} 仍是结构性平涂", _c < FLAT_MIN_COLORS,
                    f"{_c} 色 / {_area}px —— 豁免理由：{FLAT_BY_DESIGN[_pid]}")
                continue
            flat_n += 1
            add("素材真伪", f"{_pid} 是真原画不是平涂色块", _c >= FLAT_MIN_COLORS,
                f"不透明区 {_area}px 里只有 {_c} 种颜色（真原画最低一档 ~597 色，"
                f"判据 {FLAT_MIN_COLORS}）；若确属结构件请到 FLAT_BY_DESIGN 写明理由")
        add("素材真伪", "受检件数不为零", flat_n > 0,
            f"查了 {flat_n} 件（≥{FLAT_MIN_AREA}px，不含 {len(FLAT_BY_DESIGN)} 件豁免）")
    except Exception as _e:                                  # pragma: no cover
        add("素材真伪", "素材真伪闸可运行", False, "跑挂了：%s" % _e)

    report = {
        "character": character, "form": form,
        "thresholds": th,
        "pass": fails == 0, "fail_count": fails,
        "design_iou": design,
        "items": results,
    }
    if out_json:
        os.makedirs(os.path.dirname(out_json), exist_ok=True)
        with open(out_json, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
    return report


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--character", required=True)
    ap.add_argument("--form", required=True)
    ap.add_argument("--root", default=".")
    ap.add_argument("--strict", action="store_true", help="收紧阈值（新素材入库前用）")
    ap.add_argument("--json", dest="out_json", default="logs/asset_qa/report.json")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()
    rep = check(args.character, args.form, args.root, args.strict, args.out_json)
    if not args.quiet:
        last = None
        for it in rep["items"]:
            if it["part"] != last:
                print(f"\n[{it['part']}]")
                last = it["part"]
            print(f"  {'通过' if it['ok'] else '不通过'}  {it['check']:14s} {it['detail']}")
        print(f"\n合计 {len(rep['items'])} 项，{rep['fail_count']} 项不通过 → "
              f"{'全部通过' if rep['pass'] else '需要重做（最多重试 3 次，仍不过不入库）'}")
        print(f"报告：{args.out_json}")
    return 0 if rep["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
