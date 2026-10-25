#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""qa_sprite_audit.py —— 素材体检：把"看着不对劲"变成四个能数的指标

★ 为什么要有这个工具（T67.2）
--------------------------------------------------------------------
这一轮（第七问）查出来的四个大毛病，全部是**素材层**的，而且全部是我**用眼睛**
看出来之后才去数出来的：

    长发不完整  → 平涂多边形拼块 + 1~2px 亮缝 1.93% + 发尾等高切齐
    手臂残留    → 发件里烤着袖口/手/衬衫（被洗成淡薄荷 / 淡肉 / 近白）
    兜帽、鞋    → 近白像素 46%（白鞋白袜之间没有暗线）

问题在于：这些数**每次都要现写脚本**。下一个人接手时，他不知道该数什么，
就会像我上一轮那样，先怀疑层级、怀疑换装、怀疑遮罩，绕一大圈才回到素材。
所以把四件事固化下来，跑一条命令就能出：

    1. 近白 / 低饱和 占比        —— "洗过的残留"、"白斑"
    2. 1~2px 亮缝 / 暗线 条数    —— 拼块接缝、硬折线
    3. 轮廓上的**直边最长跑长**  —— 抠图的直切边、一刀切发尾
    4. 内部空洞面积              —— "不完整"是被挡还是本身缺
    5. 躯体色残留（皮肤/青布/衬衫白，**含被洗淡的版本**）—— G66.24 的真凶

用法
----
    python3 tools/qa_sprite_audit.py                       # 体检 teen 全部精灵
    python3 tools/qa_sprite_audit.py --form chibi
    python3 tools/qa_sprite_audit.py --only hair_ --json out.json
    python3 tools/qa_sprite_audit.py --overlay logs/asset_qa/audit   # 出标注图

退出码：0 正常；1 有文件越线（配合 --fail 使用）。

阈值口径 —— **校准过的，不是拍脑袋**（2026-10-26，见 docs/ART_PARTS.md 与 GAPS G66.25）
--------------------------------------------------------------------------
只有两条能当硬闸（其余只报不判）：

    hole%        > 1.5   内部空洞（发/尾放宽到 3.0，见 TH_KIND 注释）。先腐蚀 5x5 再数（1~3px 的裂缝会被削掉，
                         4px 以上的"缺了一块"才留下），再过 >=30px 连通块
    straight_run > 150px 有机形（发/四肢/尾）轮廓上的笔直长边 = 切图
                         眼/布/fx 不设闸：它们本来就是直边多边形

**为什么别的不能当闸**（每条都有目视反例，别再把它们接成 CI）：

    near_white / edge_near_white  arm_r_cap 47% —— 白袖子本来就是白的，不是缺陷
    seam                          发丝高光天生"两侧暗中间亮"，全库 p50 4%
    residue（躯体色）             幽灵件被洗淡后与发丝高光同色域（T67.3 已证伪）
    edge_touch                    43/99 件贴边，多数是**故意**裁到 bbox 的

颜色类指标只用来**排序找线索**，判案必须 `--overlay` 出图用眼睛看。
这是这一轮最贵的一课：三个颜色指标我一开始全接成了闸，一跑 80/99 越线，
逐张看过去全是误伤 —— 数字好看，案子判错。

基线回归（真正该接进 CI 的那个）
--------------------------------------------------------------------------
    python3 tools/qa_sprite_audit.py --update-baseline logs/asset_qa/sprite_audit_teen.json
    python3 tools/qa_sprite_audit.py --fail --baseline  logs/asset_qa/sprite_audit_teen.json

重画一张图之后，`hole% / straight_run / edge_near_white% / seam% / residue%`
**只许降不许升**（容差见 TOL）。升了就必须解释 —— 这比任何绝对阈值都可靠，
因为它比的是同一张图的前后，不是"别人的头发"和"你的头发"。
"""

import argparse
import glob
import json
import os
import sys
from collections import deque

import numpy as np
from PIL import Image, ImageFilter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# ---- 阈值（与文档同源；改这里要顺手改 docs） ----
# ★ 校准结果（2026-10-26，逐张目视核对过下面四个样本之后定的）：
#   只有两条指标可以当**硬闸**，其余一律"只报不判"：
#     hole_pct      内部空洞 —— eye_r_base 那个 681px 的"洞"其实是发丝间 1px 裂缝，
#                  所以腐蚀必须上 5x5：3x3 只削到 303px，仍会误报
#     straight_run  有机形（发/四肢/尾）轮廓上的笔直长边 ——
#                   acc_hair_sidelong_r 248px = 一根切下来的细条；hair_back 136px = 右侧被切齐
#   不能当硬闸的（都有反例，眼睛已核）：
#     near_white / edge_near_white —— arm_r_cap 47% 的白袖子**本身就是白的**，不是缺陷；
#                                    白袜子同理（G66.29 要修的是"没暗线"而不是"白"）
#     seam                         —— 发丝高光天然就是"两侧暗、中间亮"，p50 4%
#     residue(躯体色)              —— 幽灵件被洗淡后与发丝高光同色域（T67.3 实测证伪）
#   所以颜色类指标只用来**排序找线索**，判案必须 `--overlay` 出图用眼睛看。
TH_KIND = {
    # 有机形：轮廓本该是曲线，出现长直边 = 切图
    # 发件松到 3.0：发绺之间天然会有 8~10px 厚的"缝"（新长发候选件 1.62% 全是这种，
    # 目视核过 logs/asset_qa/t67_7_haironly_holes.png）—— 这不是"缺了一块"。
    # 真要缺一块会是整段没有，远大于 3%。
    "hair":  {"hole_pct": 3.0, "straight_run": 150},
    "limb":  {"hole_pct": 1.5, "straight_run": 150},
    "tail":  {"hole_pct": 3.0, "straight_run": 150},
    # 几何形：眼件/布料本来就是直边多边形，只判空洞
    "face":  {"hole_pct": 1.5, "straight_run": None},
    "cloth": {"hole_pct": 1.5, "straight_run": None},
    "fx":    {"hole_pct": 1.5, "straight_run": None},
    "body":  {"hole_pct": 1.5, "straight_run": None},
}
# 兼容旧接口：给外部脚本读"默认值"时不至于 KeyError
TH = {"near_white_pct": 8.0, "seam_pct": 1.0, "straight_run": 150,
      "hole_pct": 1.5, "residue_pct": 0.4}

# 已知欠账：越线但**已经知道原因、已经排进任务**。放行，但每次都会打印出来提醒，
# 不是把警报关掉。清空条件写在理由里。
KNOWN = {
    # 2026-10-26：空的。上一条欠账（acc_hair_sidelong_r 直边 248px）已经还清 ——
    # 那条直边其实就是**一块不连通的碎发岛**的切边（T67.26 把它搬回后发层后，
    # 直边 248 → 101px，同时两腿之间那缕头发也不再画在大腿上了）。
    # 这条记录留着当先例：闸报出来的"怪数字"，根因经常在别处。
}

BODY_TAGS = ("hair_", "acc_hair_", "head", "brow", "eye", "mouth", "blush")


def _load(path):
    im = Image.open(path).convert("RGBA")
    return np.asarray(im).astype(np.int32), im.size


def _holes(alpha_bool):
    """从四边泛洪，剩下的透明像素 = 被包围的内部空洞。"""
    h, w = alpha_bool.shape
    seen = np.zeros_like(alpha_bool, bool)
    dq = deque()
    transparent = ~alpha_bool
    for x in range(w):
        for y in (0, h - 1):
            if transparent[y, x] and not seen[y, x]:
                seen[y, x] = True
                dq.append((y, x))
    for y in range(h):
        for x in (0, w - 1):
            if transparent[y, x] and not seen[y, x]:
                seen[y, x] = True
                dq.append((y, x))
    while dq:
        y, x = dq.popleft()
        for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            ny, nx = y + dy, x + dx
            if 0 <= ny < h and 0 <= nx < w and transparent[ny, nx] and not seen[ny, nx]:
                seen[ny, nx] = True
                dq.append((ny, nx))
    return transparent & ~seen


def _longest_straight_run(alpha_bool):
    """轮廓的"直边最长跑长"：同一列（行）连续多少行（列）共享同一个最外沿像素。

    画出来的曲线，最外沿 x 会逐行变化；**切图**出来的边，几百行都是同一个 x。
    这是"一刀切"最省事的机器判据。
    """
    best = 0
    h, w = alpha_bool.shape
    # 左沿：每行最左的不透明 x
    left = []
    for y in range(h):
        xs = np.nonzero(alpha_bool[y])[0]
        left.append(int(xs[0]) if len(xs) else -1)
    run, prev = 0, None
    for v in left:
        if v >= 0 and v == prev:
            run += 1
            best = max(best, run)
        else:
            run = 1 if v >= 0 else 0
        prev = v
    # 上沿：每列最上的不透明 y
    top = []
    for x in range(w):
        ys = np.nonzero(alpha_bool[:, x])[0]
        top.append(int(ys[0]) if len(ys) else -1)
    run, prev = 0, None
    for v in top:
        if v >= 0 and v == prev:
            run += 1
            best = max(best, run)
        else:
            run = 1 if v >= 0 else 0
        prev = v
    return best


def _residue_mask(rgb, alpha_bool):
    """躯体色残留：皮肤（含被洗淡的淡肉）、青布（含淡薄荷）、衬衫白（中性近白）。

    ★ 关键在"洗淡的版本"：`clean_hair_residue.py` 当初只认饱和色，
      于是被漂白的袖口 (228,249,252) 与手掌 (232,214,206) 全部漏判（G66.24）。
      这里三条判据都**不要求饱和**，只要色相方向对。
    头发是冷紫（R>G，B≥R），所以"绿压红"的薄荷与"红>绿>蓝"的暖肉都不会误伤。
    """
    R, G, B = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    V = rgb.max(axis=2)
    mn = rgb.min(axis=2)
    S = np.where(V > 0, (V - mn) / np.maximum(V, 1), 0)

    mint = (G > R + 8) & (B >= G - 2) & (V > 200)          # 淡薄荷袖口
    warm = (R > G + 6) & (G > B + 4) & (V > 190)           # 肤色 / 洗淡的手掌
    shirt = (V > 246) & (S < 0.045)                        # 衬衫白（中性近白）
    return alpha_bool & (mint | warm | shirt), {
        "mint": int((alpha_bool & mint).sum()),
        "warm": int((alpha_bool & warm).sum()),
        "shirt": int((alpha_bool & shirt).sum()),
    }


def _big_components(mask, min_px=200, top=3):
    """连通块过滤：返回（只含大块的掩膜, [{px,bbox}, ...] top3）。

    为什么必须过滤：发丝的白色高光本身就是零散小白点，不过滤的话"残留"永远 20%+，
    这个数就失去意义。真正要抓的是**成片的**躯体（手/袖口/衬衫），
    它们一定连成几千像素的块。
    """
    h, w = mask.shape
    label = np.zeros((h, w), np.int32)
    seen = mask.copy()
    comps = []
    cur = 0
    ys, xs = np.nonzero(mask)
    for y0, x0 in zip(ys, xs):
        if not seen[y0, x0]:
            continue
        cur += 1
        dq = deque()
        dq.append((y0, x0))
        seen[y0, x0] = False
        n = 0
        miny, maxy, minx, maxx = y0, y0, x0, x0
        pix = []
        while dq:
            y, x = dq.popleft()
            n += 1
            pix.append((y, x))
            if y < miny: miny = y
            if y > maxy: maxy = y
            if x < minx: minx = x
            if x > maxx: maxx = x
            for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                ny, nx = y + dy, x + dx
                if 0 <= ny < h and 0 <= nx < w and seen[ny, nx]:
                    seen[ny, nx] = False
                    dq.append((ny, nx))
        if n >= min_px:
            comps.append({"px": n, "bbox": [minx, miny, maxx, maxy]})
            for y, x in pix:
                label[y, x] = 1
    comps.sort(key=lambda c: -c["px"])
    return label.astype(bool), comps[:top]


def _boundary(op):
    """轮廓像素：不透明、且 4 邻域里有一个透明（1px 边界）。"""
    inner = op.copy()
    inner[1:, :] &= op[:-1, :]
    inner[:-1, :] &= op[1:, :]
    inner[:, 1:] &= op[:, :-1]
    inner[:, :-1] &= op[:, 1:]
    return op & ~inner


def _kind(name):
    """素材类别。不同类别的"直边/近白"含义完全不同，必须分开定阈值。"""
    n = name
    if n.startswith(("hair_", "acc_hair_")):
        return "hair"
    if n.startswith(("acc_ear_", "acc_tail_")):
        return "tail"
    if n.startswith(("eye_", "brow_", "mouth_", "blush_", "eyelid", "eyeline")):
        return "face"
    if n.startswith(("arm_", "hand_", "seg_leg", "seg_foot", "foot_")):
        return "limb"
    if n.startswith(("skirt_", "jacket_", "torso_top", "outfit_", "acc_hood_")):
        return "cloth"
    if n.startswith(("fx_", "manpu_")):
        return "fx"
    return "body"


def audit_one(path):
    a, size = _load(path)
    rgb = a[..., :3]
    A = a[..., 3]
    op = A > 24
    n_op = int(op.sum())
    if n_op < 200:
        return None
    V = rgb.max(axis=2)
    mn = rgb.min(axis=2)
    S = np.where(V > 0, (V - mn) / np.maximum(V, 1), 0)

    near_white = op & (V > 236) & (S < 0.10)
    L = rgb.mean(axis=2)
    # 亮缝：比左右各 2px 都亮 >10，且左右都是不透明（拼块接缝）
    lp = np.roll(L, 2, 1)
    rp = np.roll(L, -2, 1)
    seam = op & (L - lp > 10) & (L - rp > 10) & np.roll(op, 2, 1) & np.roll(op, -2, 1)
    dark = op & (lp - L > 18) & (rp - L > 18) & np.roll(op, 2, 1) & np.roll(op, -2, 1)

    holes = _holes(op)
    # ★ 空洞必须先"开运算"再判，光过连通块不够：
    #   eye_r_base 有个 681px 的"大洞"，一画出来才知道是**发丝之间 1px 宽、100px 高的裂缝**
    #   （红色细线贯穿鬓发，见 logs/asset_qa/t67_2_hole_crack.png）——连通块过滤拦不住它。
    #   做法：先腐蚀 1px（1px 缝立刻消失，真缺块不会），再要求 >=30px。
    #   腐蚀用 5x5（不是 3x3）：实测 3x3 只把裂缝从 681px 削到 303px（宽 2~3px 的缝仍在），
    #   换成 5x5 后 eye_r_base 掉到 0.17%、全库最高只剩 0.98%（hair_side_l）——
    #   这时"洞"才真的等于">=4px 厚的一块没了"。
    holes = np.asarray(Image.fromarray((holes * 255).astype(np.uint8))
                       .filter(ImageFilter.MinFilter(5))) > 128
    holes, _hole_comps = _big_components(holes, min_px=30, top=3)
    n_hole = int(holes.sum())

    res, res_parts = _residue_mask(rgb, op)
    # 只留**大块**：散落的白色高光不该算残留，成片的"幽灵手/衬衫"才算。
    # 这条是 G66.24 出口条件里的"连通块 >200px"，在这里先落地成体检口径。
    res, comps = _big_components(res, min_px=200, top=3)

    # 是否被画布边裁掉（贴边不透明）
    edge_touch = bool(op[0, :].any() or op[-1, :].any() or op[:, 0].any() or op[:, -1].any())

    kind = _kind(os.path.basename(path))
    # 边界近白：**白边/无描线**的真判据。
    # 之前在整块上数 near_white，白外套、白袜子必然 100%，这个数就废了；
    # 而"制作后缺陷"里的白边只在**轮廓上**成立，所以只数 1px 边界。
    bnd = _boundary(op)
    nb = int(bnd.sum())
    edge_nw = float((bnd & near_white).sum()) / nb if nb else 0.0
    return {
        "file": os.path.basename(path),
        "kind": kind,
        "size": "%dx%d" % size,
        "opaque": n_op,
        "near_white_pct": round(100.0 * near_white.sum() / n_op, 2),
        "edge_near_white_pct": round(100.0 * edge_nw, 2),
        "seam_pct": round(100.0 * seam.sum() / n_op, 2),
        "dark_pct": round(100.0 * dark.sum() / n_op, 2),
        "hole_pct": round(100.0 * n_hole / n_op, 2),
        "straight_run": _longest_straight_run(op),
        "residue_pct": round(100.0 * res.sum() / n_op, 2),
        "residue": res_parts,
        "residue_blocks": comps,
        "edge_touch": edge_touch,
        "_masks": {"residue": res, "near_white": near_white},
    }


def flag(r):
    """只报**硬闸**越线（其余指标在表里照常打印，但不参与判定）。"""
    th = TH_KIND.get(r.get("kind"), TH_KIND["body"])
    out = []
    if th.get("hole_pct") is not None and r["hole_pct"] > th["hole_pct"]:
        out.append("空洞%.2f%%" % r["hole_pct"])
    if th.get("straight_run") is not None and r["straight_run"] > th["straight_run"]:
        out.append("直边%dpx" % r["straight_run"])
    return out


def known_reason(r):
    return KNOWN.get(r["file"], "")


# 基线回归：同一件重画之后，这些指标**必须不变差**
GATED = ("hole_pct", "straight_run", "edge_near_white_pct", "seam_pct", "residue_pct")
TOL = {"hole_pct": 0.5, "straight_run": 20, "edge_near_white_pct": 3.0,
       "seam_pct": 0.5, "residue_pct": 2.0}


def compare_baseline(rows, base_path):
    """把当前结果和基线 JSON 比一比。返回（退化列表, 改善列表）。"""
    with open(base_path, encoding="utf-8") as fh:
        base = {s["file"]: s for s in json.load(fh)["sprites"]}
    worse, better = [], []
    for _, r, _, _ in rows:
        b = base.get(r["file"])
        if not b:
            continue
        for k in GATED:
            d = r[k] - b[k]
            if d > TOL[k]:
                worse.append((r["file"], k, b[k], r[k]))
            elif d < -TOL[k]:
                better.append((r["file"], k, b[k], r[k]))
    return worse, better


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--character", default="xiaoxun")
    ap.add_argument("--form", default="teen")
    ap.add_argument("--only", default="")
    ap.add_argument("--json", default="")
    ap.add_argument("--overlay", default="", help="把残留/近白标成红/黄的目录")
    ap.add_argument("--fail", action="store_true", help="有件越线就返回 1")
    ap.add_argument("--baseline", default="", help="和这份 JSON 基线比，退化就返回 1")
    ap.add_argument("--update-baseline", default="", help="把当前结果存成基线再退出")
    args = ap.parse_args()

    d = os.path.join(ROOT, "characters", args.character, "forms", args.form, "sprites")
    files = sorted(glob.glob(os.path.join(d, "*@2x.png")))
    if args.only:
        files = [f for f in files if args.only in os.path.basename(f)]
    if not files:
        print("没有找到精灵：", d)
        return 2

    if args.overlay:
        os.makedirs(args.overlay, exist_ok=True)

    rows, bad = [], 0
    for f in files:
        r = audit_one(f)
        if not r:
            continue
        name = r["file"].replace("@2x.png", "")
        hits = flag(r)
        if hits and not known_reason(r):
            bad += 1            # 已知欠账不计入"越线"，但仍打印
        rows.append((len(hits), r, hits, f))
        if args.overlay:
            a, _ = _load(f)
            vis = a[..., :3].copy()
            vis[r["_masks"]["residue"]] = [255, 0, 0]
            vis[r["_masks"]["near_white"] & ~r["_masks"]["residue"]] = [255, 220, 0]
            out = os.path.join(args.overlay, name + "_audit.png")
            Image.fromarray(vis.astype(np.uint8)).save(out)

    rows.sort(key=lambda t: -t[0])
    print("%-26s %-11s %7s %7s %7s %6s %6s %7s  %s" %
          ("部件", "尺寸", "不透明", "近白%", "亮缝%", "直边", "空洞%", "残留%", "标记"))
    print("-" * 118)
    for n_hit, r, hits, _ in rows:
        mark = " ".join(hits) if hits else ""
        print("%-26s %-11s %7d %7.2f %7.2f %6d %6.2f %7.2f  %s" %
              (r["file"].replace("@2x.png", ""), r["size"], r["opaque"],
               r["near_white_pct"], r["seam_pct"], r["straight_run"],
               r["hole_pct"], r["residue_pct"],
               mark + ("（已知欠账）" if known_reason(r) else "")))
    print("-" * 118)
    print("共 %d 件，%d 件越线（其中 %d 件属已知欠账，见 KNOWN）"
          % (len(rows), bad, sum(1 for _, r, _, _ in rows if flag(r) and known_reason(r))))

    if args.json:
        clean = [{k: v for k, v in r.items() if not k.startswith("_")} for _, r, _, _ in rows]
        with open(args.json, "w", encoding="utf-8") as fh:
            json.dump({"form": args.form, "thresholds": TH, "sprites": clean},
                      fh, ensure_ascii=False, indent=1,
                      default=lambda o: o.item() if hasattr(o, "item") else str(o))
        print("JSON →", args.json)

    if args.update_baseline:
        clean = [{k: v for k, v in r.items() if not k.startswith("_")} for _, r, _, _ in rows]
        with open(args.update_baseline, "w", encoding="utf-8") as fh:
            json.dump({"form": args.form, "thresholds": TH_KIND, "sprites": clean},
                      fh, ensure_ascii=False, indent=1,
                      default=lambda o: o.item() if hasattr(o, "item") else str(o))
        print("基线已更新 →", args.update_baseline)

    if args.baseline:
        worse, better = compare_baseline(rows, args.baseline)
        print("\n相对基线 %s：" % args.baseline)
        if better:
            print("  改善 %d 处（重画有成效）：" % len(better))
            for f_, k, a, b in better[:10]:
                print("    %-34s %-20s %.2f → %.2f" % (f_, k, a, b))
        if worse:
            print("  退化 %d 处（必须解释）：" % len(worse))
            for f_, k, a, b in worse[:10]:
                print("    %-34s %-20s %.2f → %.2f" % (f_, k, a, b))
        if not worse and not better:
            print("  无变化")
        if worse:
            return 1

    return 1 if (args.fail and bad) else 0


if __name__ == "__main__":
    sys.exit(main())
