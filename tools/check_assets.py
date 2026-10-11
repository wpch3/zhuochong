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
    from PIL import Image
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
    "iou": 0.80,               # 形状重合度下限（与设计图同区域比）
    "palette_dist": 70,        # 主色到色卡的 RGB 距离上限（超过就是配色画歪了）
    "anchor_tol": 0.04,        # 对位容差（占全身高的比例，约 ±50px@1292）
    "joint_hole": 60,          # 压力姿势下关节处允许新增的空洞像素（再多就是会穿帮）
}


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
    for fn in files:
        path = os.path.join(sprites, fn)
        pid = fn[:-4]
        im = Image.open(path)
        add(pid, "容器", im.mode in ("RGBA", "LA"), f"模式 {im.mode}")
        a = load_rgba(path)
        rgb, m = a[..., :3], alpha_mask(a)
        add(pid, "透明通道", (a[..., 3] == 0).any(), f"全透明像素 {int((a[...,3]==0).sum())}")
        add(pid, "不是空图", m.sum() > 0, f"不透明像素 {int(m.sum())}")
        side_ok = min(a.shape[0], a.shape[1]) >= th["min_side"]
        if pid == "body_full":
            side_ok = side_ok and a.shape[1] >= th["body_min_w"]
        add(pid, "尺寸", side_ok, f"{a.shape[1]}x{a.shape[0]}")

        key = count_near(rgb, m, (255, 0, 255), 120)
        add(pid, "键色残留", key <= th["key_residue"], f"{key} 像素（上限 {th['key_residue']}）")
        ring = edge_ring(m)
        white = count_near(rgb, ring, (255, 255, 255), 24)
        add(pid, "白边", white <= th["white_edge"], f"{white} 像素（上限 {th['white_edge']}）")

        if palette:
            doms = dominant_colors(rgb, m)
            worst, worst_c = 0, None
            for (r, g, b, share) in doms:
                if share < 0.06:          # 占比太低的颜色（抗锯齿过渡色）不参与判定
                    continue
                dist = min(abs(r - pr) + abs(g - pg) + abs(b - pb) for pr, pg, pb, _ in palette)
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
        miss = [sp["id"] for sp in bp["parts"]
                if not os.path.exists(os.path.join(base, sp["file"]))]
        add("分段", "部件齐全", not miss, f"{len(bp['parts'])} 个部件" + (f"，缺 {miss}" if miss else ""))

        def compose(angles):
            """按层序叠出整个人；angles 按组给旋转角（度，绕锚点）。"""
            c = Image.new("RGBA", (SW, SH), (0, 0, 0, 0))
            piv = {"head": AP["neck"], "arm_l": AP["shoulder_l"], "arm_r": AP["shoulder_r"],
                   "chest": AP["hip"], "leg_l": AP["hip"], "leg_r": AP["hip"]}
            for sp in sorted(bp["parts"], key=lambda q: q["layer"]):
                im = Image.open(os.path.join(base, sp["file"])).convert("RGBA")
                lay = Image.new("RGBA", (SW, SH), (0, 0, 0, 0))
                lay.paste(im, tuple(sp["pos"]))
                ang = angles.get(sp["group"], 0.0)
                if ang:
                    px, py = piv[sp["group"]]
                    lay = lay.rotate(ang, resample=Image.BICUBIC, center=(float(px), float(py)))
                c.alpha_composite(lay)
            return np.asarray(c)[..., 3] > 24

        if not miss:
            body_m = alpha_mask(load_rgba(os.path.join(base, "sprites", "body_full.png")))
            flat = compose({})
            lost = int((body_m & ~flat).sum())
            # 静止时把部件叠回去，必须和原图一模一样：少一块就是切丢了东西
            add("分段", "无损切分", lost == 0, f"静止合成比原图少 {lost} 像素")

            def holes(a, y0, y1):
                """这一段里的"内部空洞"：透明、但上下左右都还有身体。"""
                sl = a[max(0, y0):min(SH, y1)]
                if sl.size == 0:
                    return 0
                up = np.maximum.accumulate(sl, 0); dn = np.maximum.accumulate(sl[::-1], 0)[::-1]
                lf = np.maximum.accumulate(sl, 1); rt = np.maximum.accumulate(sl[:, ::-1], 1)[:, ::-1]
                return int(((~sl) & up & dn & lf & rt).sum())

            # 压力姿势：远超实际动作（头 ≤5°、手臂 ≤2°），关节处仍然不能露底
            pose = compose({"head": -15.0, "arm_l": 10.0, "arm_r": -10.0})
            for label, y in (("颈", int(AP["neck"][1])), ("肩", int(AP["shoulder"][1])),
                             ("髋", int(AP["hip"][1]))):
                d = holes(pose, y - ov * 2, y + ov * 2) - holes(flat, y - ov * 2, y + ov * 2)
                add("分段", f"关节不露底({label})", d <= th["joint_hole"],
                    f"压力姿势新增空洞 {d} 像素（上限 {th['joint_hole']}）")

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
