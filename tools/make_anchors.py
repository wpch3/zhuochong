#!/usr/bin/env python3
"""锚点标注：从全身图的剪影自动量取关节位置，产出 anchors.json。

为什么要这个工具：
  拆件、补图、rig 的组枢轴、换装的对位，全都依赖"关节在哪"。
  以前这些数字是手写的（交接文件里反复强调"手写坐标必然对不齐"），
  一旦素材重做就全部作废。这里改成**从素材本身量**：素材换了，重跑即可。

量取方法（只用剪影，不依赖颜色，所以换服装/换发型同样适用）：
  - 逐行统计 alpha 的左右边界与宽度，得到"宽度剖面"。
  - **先把手臂从躯干里剥掉**：手臂比躯干细得多，用水平方向的腐蚀（宽度 2k+1 的最小值滤波）
    就能把细的部分消掉，剩下的才是躯干。腰/髋/肩全部在"躯干剖面"上量，
    否则垂下的手会把最宽处拉到手背那一行（实测会把腰错判到裙摆以下）。
  - 头顶 = 第一行有像素；脚底 = 最后一行有像素；身高 = 两者之差。
  - 颈 = 上部 1/3 内宽度的局部极小（头与肩之间最细的地方）。
  - 肩 = 颈以下躯干宽度首次达到躯干最大宽度 60% 的那一行。
  - 腰 = 肩与 55% 身高之间躯干宽度的局部极小。
  - 髋 = 腰以下躯干宽度的局部极大（裙摆/胯部最宽处）。
  - 膝 = 髋与踝之间偏上处宽度的局部极小。
  - 踝 = 脚底往上 3%~12% 区间里最细处（鞋口）。
  - 肘/腕：在"整体剪影减去躯干"的手臂区域里量——手的最低行即腕，肘取肩与腕之间 55%。
  - 眼睛高度：按色卡里的瞳色实测（找不到色卡才退回"头顶到颈 0.55 处"的估算）。

输出：
  <form>/design/anchors.json   关节点（画布坐标 + 归一化比例，两套都给）
  logs/asset_qa/anchors_preview.png   标注预览图（只给人眼复核，不是素材，不入库）

用法：
  python3 tools/make_anchors.py --character xiaoxun --form teen
  python3 tools/make_anchors.py --image path/to/body.png --out /tmp/a.json
"""
from __future__ import annotations
import argparse, json, os, sys

try:
    from PIL import Image, ImageDraw
    import numpy as np
except ImportError:  # 沙箱里用 ~/.imgenv/bin/python
    print("需要 pillow 与 numpy：python3 -m venv ~/.imgenv && ~/.imgenv/bin/pip install pillow numpy")
    raise


def width_profile(alpha: "np.ndarray", thr: int = 24):
    """每一行的 [左边界, 右边界, 宽度, 中心]；没有像素的行用 -1 填充。"""
    mask = alpha > thr
    rows = []
    for y in range(mask.shape[0]):
        xs = np.flatnonzero(mask[y])
        if xs.size == 0:
            rows.append((-1, -1, 0, -1.0))
        else:
            rows.append((int(xs[0]), int(xs[-1]), int(xs[-1] - xs[0] + 1), float(xs.mean())))
    return rows


def smooth(v, k=9):
    """滑动平均：剪影边缘有锯齿，不平滑会把噪声当成关节。"""
    if k < 3:
        return list(v)
    a = np.asarray(v, dtype=float)
    pad = k // 2
    a = np.pad(a, (pad, pad), mode="edge")
    ker = np.ones(k) / k
    return list(np.convolve(a, ker, mode="valid"))


def local_min(w, lo, hi):
    lo, hi = max(lo, 0), min(hi, len(w))
    if hi - lo < 3:
        return (lo + hi) // 2
    seg = w[lo:hi]
    return lo + int(np.argmin(seg))


def local_max(w, lo, hi):
    lo, hi = max(lo, 0), min(hi, len(w))
    if hi - lo < 3:
        return (lo + hi) // 2
    seg = w[lo:hi]
    return lo + int(np.argmax(seg))


def erode_h(mask: "np.ndarray", k: int) -> "np.ndarray":
    """水平腐蚀：只保留"左右各 k 个像素都不透明"的点。
       手臂细、躯干宽，所以这一步能把手臂从剪影里剥掉。"""
    if k <= 0:
        return mask
    out = mask.copy()
    for d in range(1, k + 1):
        out &= np.roll(mask, d, axis=1)
        out &= np.roll(mask, -d, axis=1)
    out[:, :k] = False
    out[:, -k:] = False
    return out


def runs_width(mask: "np.ndarray"):
    """每行的宽度（左右边界之差）与中心；空行给 0 / -1。"""
    w, c = [], []
    for y in range(mask.shape[0]):
        xs = np.flatnonzero(mask[y])
        if xs.size == 0:
            w.append(0); c.append(-1.0)
        else:
            w.append(int(xs[-1] - xs[0] + 1)); c.append(float(xs.mean()))
    return w, c


def head_and_neck(w, top, bottom, wmax):
    """找「头团」和「颈」，**不用任何头身比常数**（T2.2.5，2026-10-17）。

    原来这里写的是 `neck = 宽度在 [身高15%, 身高40%] 区间里的最小值`。
    这对少女(1:4.65)成立，对 Q 版(1:2.5)当场失效：
      · Q 版的颈在身高 46% 处，**根本不在窗口里**；
      · 窗口开头正好是呆毛那根细尖，argmin 直接落在呆毛上 ——
        实测把 1292px 高的 Q 版读成「6.69 头身」（真值约 2.2），
        颈、肩、腰、胯、肘、腕跟着全错（左右肘甚至量成同一个点）。

    剖面的形状本身是和头身比无关的：
        细尖（呆毛）→ 头团（宽）→ 颈（窄）→ 肩（宽）
    所以改成按**形状**找，不按比例找：
      ① 跳过宽度不到最大宽度 1/4 的行 —— 呆毛、发丝这类细尖不算头团；
      ② 从那里开始，第一个「之后掉下去 ≥ prom」的峰 = 头团最宽处；
      ③ 峰之后第一个「之后涨回来 ≥ prom」的谷 = 颈。
    prom（突出度）取最大宽度的 7%，是相对量，同样与头身比无关。

    返回 (solid_top, head_peak, neck)。
    """
    prom = max(6.0, wmax * 0.07)
    y = top
    while y < bottom and w[y] < wmax * 0.25:
        y += 1
    solid_top = min(y, bottom)
    peak = solid_top
    y = solid_top
    while y < bottom:
        if w[y] > w[peak]:
            peak = y
        elif w[peak] - w[y] >= prom:
            break
        y += 1
    valley = min(y, bottom)
    while y < bottom:
        if w[y] < w[valley]:
            valley = y
        elif w[y] - w[valley] >= prom:
            break
        y += 1
    return solid_top, peak, valley


def measure(img: "Image.Image", eye_rgb=None):
    a = np.asarray(img.convert("RGBA"))[..., 3]
    prof = width_profile(a)
    ys = [y for y, r in enumerate(prof) if r[2] > 0]
    if not ys:
        raise SystemExit("素材里没有不透明像素，无法量取锚点")
    top, bottom = ys[0], ys[-1]
    h = bottom - top + 1
    w = smooth([r[2] for r in prof], 11)
    cx = [r[3] for r in prof]

    # 躯干剖面：把手臂腐蚀掉再量，否则垂下的手会把"最宽处"拉到手背那一行
    mask = a > 24
    torso_k = max(8, int(img.width * 0.055))      # 手臂宽度量级，随画幅自适应
    torso = erode_h(mask, torso_k)
    tw_raw, tc = runs_width(torso)
    tw = smooth(tw_raw, 11)
    tmax = max(tw) if tw else 1

    # 颈：按剖面形状找（见 head_and_neck），不按身高比例开窗
    wmax_all = max(w) if w else 1.0
    solid_top, head_peak, neck = head_and_neck(w, top, bottom, wmax_all)
    # 防呆：颈必须落在「头占全身 8%~60%」这个极宽的生理区间里（1:1.7 ~ 1:12 都容得下）。
    # 越界说明剖面不是人形（或素材坏了），退回老式窗口，至少不产出离谱的数。
    if not (top + h * 0.08 <= neck <= top + h * 0.60):
        neck = local_min(w, top + int(h * 0.15), top + int(h * 0.40))

    # ★ 颈以下的点一律按**身子那一段**定标（body = 脚底 − 颈），不按总身高。
    #   总身高里含着头，而头正是形态之间差别最大的部分：
    #   用总身高开窗 = 把少女的头身比写死进了工具。
    body = max(bottom - neck, 1)
    # ★ 下面这些系数不是重新调的，是把老系数**换了个单位**：
    #   老代码写的是「总身高 h 的百分之几」，而 h 里含着头 —— 等于把少女的头身比
    #   写死进了工具。换算关系：少女 body/h = 1014/1292 = 0.7849，
    #   所以 0.10h ≡ 0.1272·body，0.02h ≡ 0.0247·body，以此类推。
    #   换完少女的锚点**逐字段不变**（有回归比对），其它头身比则不再被头拖偏。
    #   腿那一段同理，用 leg = 脚底 − 胯 定标（少女 leg/h = 587/1292 = 0.4543）。
    #   这些系数当初是在少女身上调出来的，换单位只是让它们可移植，
    #   不代表对 Q 版就是最优 —— 其它形态要看渲染图复核。
    shoulder = neck + round(body * 0.050296)
    for y in range(neck, min(neck + round(body * 0.362919), len(tw))):
        if tw[y] >= tmax * 0.60:
            shoulder = y
            break
    # 腰：肩往下，躯干最细处
    waist = local_min(tw, shoulder + round(body * 0.127219), neck + round(body * 0.426036))
    # 髋：腰往下躯干最宽处（裙摆/胯）
    hip = local_max(tw, waist + round(body * 0.024655), neck + round(body * 0.617357))
    # 踝：脚底往上，窗口按**腿那一段**取（腿长在形态之间差别也很大）
    leg = max(bottom - hip, 1)
    ankle = local_min(w, bottom - round(leg * 0.264055), bottom - round(leg * 0.064736))
    # 膝：用"逐行不透明像素数"（面积）找，膝盖处比大腿细。
    #     用宽度（左右边界之差）会被两腿之间的空隙骗到，所以这里必须用面积。
    area = smooth(list(mask.sum(axis=1).astype(float)), 11)
    knee = local_min(area, hip + int((ankle - hip) * 0.45), hip + int((ankle - hip) * 0.85))
    # 眼睛高度：优先**按瞳色实测**（色卡里的"眼睛"色），找不到才退回比例估算。
    # 比例估算在大眼二次元角色上会偏高——这张图实测差了约 60px，
    # 足以让"眼部对位"验收误判，所以能测就不要猜。
    eye = top + int((neck - top) * 0.55)
    if eye_rgb is not None:
        rgb_all = np.asarray(img.convert("RGB"))
        # 只在头部的上 85% 里找，并且用很紧的色差阈值：
        # 衣领/帽衬/袖子也是青蓝色，放宽一点就会把眼线拖到下巴以下（实测 205 → 265）。
        lo = top
        hi = max(top + 1, top + int((neck - top) * 0.85))
        d_eye = np.abs(rgb_all[lo:hi].astype(int) - np.asarray(eye_rgb, int)).sum(axis=2)
        hit = (d_eye < 50) & (a[lo:hi] > 24)
        rows = np.asarray(smooth(list(hit.sum(axis=1).astype(float)), 7))
        if rows.sum() >= 30:
            # 取"瞳色最集中的那一行"再在它附近做重心，而不是整段取重心——
            # 领口、发梢、发饰也带蓝色，整段重心会被拖到下巴附近（实测偏了 40px）。
            peak = int(np.argmax(rows))
            win = max(6, int((hi - lo) * 0.12))
            a0, a1 = max(0, peak - win), min(len(rows), peak + win + 1)
            seg = rows[a0:a1]
            ys_idx = np.arange(lo + a0, lo + a1)
            eye = int(round(float((ys_idx * seg).sum() / max(seg.sum(), 1e-6))))

    def center_at(y):
        y = int(np.clip(y, 0, len(cx) - 1))
        if cx[y] >= 0:
            return cx[y]
        for dy in range(1, 40):
            for yy in (y - dy, y + dy):
                if 0 <= yy < len(cx) and cx[yy] >= 0:
                    return cx[yy]
        return float(a.shape[1]) / 2.0

    # 手臂 = 躯干左右两侧多出来的那部分（只在"肩到髋下一点"的带内找，
    #        否则鞋子和腿的轮廓也会被当成手）。
    body_cx = float(np.mean([c for c in tc if c >= 0])) if any(c >= 0 for c in tc) else img.width / 2.0
    arms = np.zeros_like(mask)
    arm_band = list(range(shoulder, min(bottom, hip + round(body * 0.127219))))
    # 躯干的左右边界取整段的中位数：某一行腐蚀失败（比如只剩一条腿）不会带偏判断，
    # 否则两条腿会被当成"躯干外侧的手"，腕就掉到膝盖去了。
    tls = [int(np.flatnonzero(torso[y])[0]) for y in arm_band if torso[y].any()]
    trs = [int(np.flatnonzero(torso[y])[-1]) for y in arm_band if torso[y].any()]
    TL = int(np.median(tls)) if tls else 0
    TR = int(np.median(trs)) if trs else mask.shape[1] - 1
    for y in arm_band:
        row = mask[y].copy()
        row[TL:TR + 1] = False            # 躯干那一段剔掉，剩下的才是两侧的手臂
        arms[y] = row
    arm_rows = [y for y in arm_band if arms[y].sum() >= 3]
    hand_bottom = max(arm_rows) if arm_rows else hip
    wrist = int(hand_bottom - body * 0.025483)                      # 腕≈手底往上一点
    elbow = int(shoulder + (wrist - shoulder) * 0.55)        # 肘取肩腕之间 55%

    def arm_x(y, side):
        y = int(np.clip(y, 0, arms.shape[0] - 1))
        xs = np.flatnonzero(arms[y])
        if xs.size == 0:
            return prof[y][0] if side < 0 else prof[y][1]
        xs_side = xs[xs < body_cx] if side < 0 else xs[xs > body_cx]
        if xs_side.size == 0:
            return float(xs.mean())
        return float(xs_side.mean())

    left_edge = [prof[y][0] for y in range(shoulder, hip) if prof[y][2] > 0]
    right_edge = [prof[y][1] for y in range(shoulder, hip) if prof[y][2] > 0]

    # 嘴线：眼线到颈之间 0.75 处（人脸比例，二次元同样适用；实测误差 <5px）
    mouth = int(eye + (neck - eye) * 0.75)
    pts = {
        "head_top":  [center_at(top), top],
        "eye_line":  [center_at(eye), eye],
        "mouth_line": [center_at(mouth), mouth],
        "neck":      [center_at(neck), neck],
        "shoulder":  [center_at(shoulder), shoulder],
        "shoulder_l": [prof[shoulder][0] if prof[shoulder][2] > 0 else center_at(shoulder), shoulder],
        "shoulder_r": [prof[shoulder][1] if prof[shoulder][2] > 0 else center_at(shoulder), shoulder],
        "elbow_l":   [arm_x(elbow, -1), elbow],
        "elbow_r":   [arm_x(elbow, +1), elbow],
        "wrist_l":   [arm_x(wrist, -1), wrist],
        "wrist_r":   [arm_x(wrist, +1), wrist],
        "waist":     [center_at(waist), waist],
        "hip":       [center_at(hip), hip],
        "knee":      [center_at(knee), knee],
        "ankle":     [center_at(ankle), ankle],
        "foot":      [center_at(bottom), bottom],
    }
    meta = {
        "height_px": h,
        "torso_erode_k": torso_k,
        "top": top,
        "bottom": bottom,
        "head_ratio": round((neck - top) / float(h), 4),      # 头身比的倒数：头占全身的比例
        "heads_tall": round(h / float(max(neck - top, 1)), 2),  # 几头身（剪影口径：含呆毛）
        # 「头」有两种口径，两个都记下来，谁用谁说清楚：
        #   heads_tall      = 剪影顶（呆毛尖）→ 颈。挂件的 unit=head 用的是它。
        #   heads_tall_solid= 发团顶（跳过细尖）→ 颈。描述"这个角色看上去几头身"更准。
        # Q 版的呆毛占了身高 10%，两个口径能差 0.5 头身，混用必错。
        "solid_top": int(solid_top),
        "heads_tall_solid": round(h / float(max(neck - solid_top, 1)), 2),
    }
    return pts, meta


def preview(img, pts, out_path):
    """标注预览：只用于人眼复核（不是 UI 素材，不入库）。"""
    im = img.convert("RGBA")
    bg = Image.new("RGBA", im.size, (240, 242, 248, 255))
    bg.alpha_composite(im)
    d = ImageDraw.Draw(bg)
    for name, (x, y) in pts.items():
        x, y = float(x), float(y)
        d.line([(x - 14, y), (x + 14, y)], fill=(220, 40, 90, 255), width=2)
        d.line([(x, y - 14), (x, y + 14)], fill=(220, 40, 90, 255), width=2)
        d.text((x + 16, y - 7), name, fill=(20, 20, 30, 255))
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    bg.convert("RGB").save(out_path, quality=95)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--character")
    ap.add_argument("--form")
    ap.add_argument("--image", help="直接指定一张全身 PNG（优先于 --character/--form）")
    ap.add_argument("--root", default=".")
    ap.add_argument("--out", help="输出 anchors.json 路径")
    ap.add_argument("--preview", default="logs/asset_qa/anchors_preview.png")
    args = ap.parse_args()

    if args.image:
        src = args.image
        out = args.out or os.path.splitext(src)[0] + ".anchors.json"
    else:
        if not (args.character and args.form):
            ap.error("要么给 --image，要么同时给 --character 与 --form")
        base = os.path.join(args.root, "characters", args.character, "forms", args.form)
        src = os.path.join(base, "sprites", "body_full.png")
        out = args.out or os.path.join(base, "design", "anchors.json")

    img = Image.open(src)
    eye_rgb = None
    if args.character:
        pal = os.path.join(args.root, "characters", args.character, "design", "palette.json")
        if os.path.exists(pal):
            with open(pal, encoding="utf-8") as f:
                for c in json.load(f).get("colors", []):
                    if c.get("name") == "眼睛":
                        h = c["hex"].lstrip("#")
                        eye_rgb = (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))
    pts, meta = measure(img, eye_rgb)
    data = {
        "schema_version": "1.0",
        "source": src,
        "canvas_note": "坐标是这张图自身的像素坐标；rig 里的画布坐标 = 这里的坐标 + 居中偏移",
        "meta": meta,
        "points": {k: [round(v[0], 1), int(v[1])] for k, v in pts.items()},
        "ratios": {k: [round(v[0] / img.width, 4), round(v[1] / img.height, 4)] for k, v in pts.items()},
    }
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    preview(img, pts, os.path.join(args.root, args.preview))
    print(f"写出 {out}")
    print(f"  身高 {meta['height_px']}px，约 {meta['heads_tall']} 头身")
    for k in ("head_top", "eye_line", "neck", "shoulder", "waist", "hip", "knee", "ankle", "foot"):
        print(f"  {k:10s} y={pts[k][1]:5d}  x={pts[k][0]:7.1f}")
    print(f"预览图（人眼复核用，不入库）：{args.preview}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
