#!/usr/bin/env python3
"""身体分段拆件：把单图层全身图按锚点切成可独立运动的部件。

为什么要这个：
  现在的小寻是**一整张图**，只能整体弯曲。要做"手臂摆动、重心偏移、裙摆甩动"
  这类动作，必须让身体分段。真正的高质量拆件要 AI 重绘每个部件（含被遮挡处补图），
  那是素材重做的事；在那之前，这个工具用**几何切分 + 关节重叠**先把分段跑通：
  部件之间故意留重叠带，小幅运动时不会露缝（重叠带就是临时的"补图"）。

切分规则（全部来自 anchors.json，不手写数字）：
  head   : 顶部 → 颈下方一点（包含脖子，转头时不会断）
  torso  : 颈上方一点 → 裙摆底（含裙子；手臂那一段从两侧挖掉）
  arm_l/r: 肩上方一点 → 手底下方一点，躯干左右边界之外 + 向内重叠一条
  leg_l/r: 裙摆底上方一点 → 脚底，按中线左右分
层序（从后到前）：leg < torso < arm < head

用法：
  python3 tools/make_body_parts.py --character xiaoxun --form teen
产出：
  sprites/seg_head.png / seg_torso.png / seg_arm_l.png / seg_arm_r.png /
  sprites/seg_leg_l.png / seg_leg_r.png
  sprites/body_parts.json   （每个部件在画布上的位置、所属组、建议层序）
  logs/asset_qa/segments_preview.png （着色预览，人眼复核用，不入库）
"""
from __future__ import annotations
import argparse, json, os, sys

try:
    from PIL import Image
    import numpy as np
except ImportError:
    print("需要 pillow 与 numpy：python3 -m venv ~/.imgenv && ~/.imgenv/bin/pip install pillow numpy")
    raise


def erode_h(mask, k):
    """水平腐蚀：留下"左右各 k 像素都不透明"的点，用来把细的手臂从躯干剥离。"""
    if k <= 0:
        return mask
    out = mask.copy()
    for d in range(1, k + 1):
        out &= np.roll(mask, d, axis=1)
        out &= np.roll(mask, -d, axis=1)
    out[:, :k] = False
    out[:, -k:] = False
    return out


def wide_runs(row, min_w):
    """一行里有几段"够宽"的连续不透明像素。
       只数段数会被 1 像素的描边缝隙骗到（实测 y=715 处有个 1px 缝，
       直接把裙子判成了两条腿），所以必须带最小宽度。"""
    idx = np.flatnonzero(row)
    if idx.size == 0:
        return 0
    parts = np.split(idx, np.where(np.diff(idx) > 1)[0] + 1)
    return sum(1 for b in parts if (b[-1] - b[0] + 1) >= min_w)


def runs_of(row):
    """一行里所有连续不透明段，返回 [(起, 止含)]。"""
    idx = np.flatnonzero(row)
    if idx.size == 0:
        return []
    parts = np.split(idx, np.where(np.diff(idx) > 1)[0] + 1)
    return [(int(b[0]), int(b[-1])) for b in parts]


def cut(mask_full, rgba, region_mask):
    """按蒙版取出一块，并裁到内容包围盒；返回 (图像, (x0,y0))。"""
    m = region_mask & mask_full
    ys, xs = np.where(m)
    if ys.size == 0:
        return None, (0, 0)
    y0, y1, x0, x1 = int(ys.min()), int(ys.max()) + 1, int(xs.min()), int(xs.max()) + 1
    sub = rgba[y0:y1, x0:x1].copy()
    sub[..., 3] = np.where(m[y0:y1, x0:x1], sub[..., 3], 0)
    return Image.fromarray(sub, "RGBA"), (x0, y0)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--character", required=True)
    ap.add_argument("--form", required=True)
    ap.add_argument("--root", default=".")
    ap.add_argument("--overlap", type=float, default=0.030,
                    help="关节重叠带占身高的比例（默认 3%%，约 39px@1292）")
    ap.add_argument("--preview", default="logs/asset_qa/segments_preview.png")
    args = ap.parse_args()

    base = os.path.join(args.root, "characters", args.character, "forms", args.form)
    sprites = os.path.join(base, "sprites")
    body_path = os.path.join(sprites, "body_full.png")
    anchors_path = os.path.join(base, "design", "anchors.json")
    if not os.path.exists(anchors_path):
        print(f"缺少 {anchors_path}，先跑 tools/make_anchors.py")
        return 2

    rgba = np.asarray(Image.open(body_path).convert("RGBA")).copy()
    alpha = rgba[..., 3]
    mask = alpha > 24
    H, W = mask.shape
    with open(anchors_path, encoding="utf-8") as f:
        A = json.load(f)
    P = {k: (v[0], v[1]) for k, v in A["points"].items()}
    h = A["meta"]["height_px"]
    ov = int(h * args.overlap)

    neck_y = int(P["neck"][1])
    shoulder_y = int(P["shoulder"][1])
    hip_y = int(P["hip"][1])
    wrist_y = int(P["wrist_l"][1])
    bottom = int(A["meta"]["bottom"])

    # 躯干的左右边界（取肩到髋之间的中位数，避免某一行腐蚀失败带偏）
    torso = erode_h(mask, A["meta"].get("torso_erode_k", max(8, int(W * 0.055))))
    tls, trs = [], []
    for y in range(shoulder_y, hip_y):
        xs = np.flatnonzero(torso[y])
        if xs.size:
            tls.append(int(xs[0])); trs.append(int(xs[-1]))
    TL = int(np.median(tls)) if tls else 0
    TR = int(np.median(trs)) if trs else W - 1

    # 裙摆底：髋往下第一行"躯干范围内分成两段"的地方（两腿分开）。
    # 注意必须**只在躯干 x 范围内**数段数：垂在两侧的手也是独立的一段，
    # 不排除掉的话第一行就满足条件，裙子会被从髋部劈成两半（实测踩过）。
    legs_top = hip_y + int(h * 0.08)
    min_leg_w = max(6, int(W * 0.06))     # 一条腿至少这么宽
    streak_need = 8                        # 要连续这么多行都成立，才算真的分开了
    streak = 0
    for y in range(hip_y, min(bottom, int(P["knee"][1]))):
        if wide_runs(mask[y, TL:TR + 1], min_leg_w) >= 2:
            streak += 1
            if streak >= streak_need:
                legs_top = y - streak_need + 1
                break
        else:
            streak = 0

    ys = np.arange(H)[:, None]
    xs = np.arange(W)[None, :]
    center_x = int(round((P["hip"][0] + P["foot"][0]) / 2.0))

    # 手臂从哪一行开始离开身体（剪影里出现"手臂|身体|手臂"三段）。
    # 这一行以下的手臂可以按真实轮廓抠（不会带走衣服和裙边）；
    # 以上手臂和外套是连在一起画的，只能竖切，靠重叠带兜底。
    arm_top = max(0, shoulder_y - ov)
    arm_bot = min(H - 1, wrist_y + ov)
    split_y = arm_bot + 1
    streak = 0
    for y in range(shoulder_y, arm_bot + 1):
        rs = [t for t in runs_of(mask[y]) if t[1] - t[0] >= 4]
        if len(rs) >= 3 and rs[0][1] < TL and rs[-1][0] > TR:
            streak += 1
            if streak >= 6:
                split_y = y - 5
                break
        else:
            streak = 0

    armL = np.zeros_like(mask)
    armR = np.zeros_like(mask)
    torso_excl = np.zeros_like(mask)
    pad = 2                      # 抠真实轮廓时外扩两像素，别把描边的半透明边丢了
    for y in range(arm_top, arm_bot + 1):
        if y < split_y:                       # 贴合段：竖切 + 向内重叠一条
            armL[y, :TL + ov + 1] = True
            armR[y, max(0, TR - ov):] = True
            torso_excl[y, :TL] = True
            torso_excl[y, TR + 1:] = True
        else:                                 # 分离段：手臂就是躯干两侧那几段剪影
            for a, b in runs_of(mask[y]):
                if b < TL:
                    armL[y, max(0, a - pad):b + 1 + pad] = True
                elif a > TR:
                    armR[y, max(0, a - pad):b + 1 + pad] = True
            torso_excl[y] = armL[y] | armR[y]

    regions = {
        # 头：到颈下方一点（含脖子），转头时根部不会断
        "seg_head":  (ys <= neck_y + ov),
        # 躯干：颈上方一点 → 裙摆下方一点；手臂那两块让出去
        "seg_torso": (ys >= neck_y - ov) & (ys <= legs_top + ov) & ~torso_excl,
        "seg_arm_l": armL,
        "seg_arm_r": armR,
        # 腿：裙摆上方一点 → 脚底，按中线分左右
        "seg_leg_l": (ys >= legs_top - ov) & (xs < center_x) & ~armL & ~armR,
        "seg_leg_r": (ys >= legs_top - ov) & (xs >= center_x) & ~armL & ~armR,
    }

    layers = {"seg_leg_l": 60, "seg_leg_r": 61, "seg_torso": 100,
              "seg_arm_l": 140, "seg_arm_r": 141, "seg_head": 180}
    groups = {"seg_leg_l": "leg_l", "seg_leg_r": "leg_r", "seg_torso": "chest",
              "seg_arm_l": "arm_l", "seg_arm_r": "arm_r", "seg_head": "head"}

    out = {"schema_version": "1.0", "source": "sprites/body_full.png",
           "image_size": [W, H], "overlap_px": ov,
           "cut_lines": {"neck": neck_y, "shoulder": shoulder_y, "hip": hip_y,
                         "legs_top": legs_top, "wrist": wrist_y, "arm_split": split_y,
                         "torso_left": TL, "torso_right": TR, "center_x": center_x},
           "patches": ["颈部重叠带=颈线复制出的脖子桩（避免转头露出重影下巴）"],
           "parts": []}
    preview = np.zeros((H, W, 4), dtype=np.uint8)
    tint = {"seg_head": (255, 120, 140), "seg_torso": (120, 200, 255),
            "seg_arm_l": (255, 210, 120), "seg_arm_r": (180, 255, 140),
            "seg_leg_l": (200, 150, 255), "seg_leg_r": (255, 170, 220)}

    # 躯干顶端的重叠带（颈线往上 ov 行）原本是**下巴**。头一转，这段静止的
    # 下巴就从头后面露出来，看着像两个下巴。这里把它换成颈线那一行向上复制
    # 出来的"脖子桩"——最便宜的关节补图，藏在头后面不会被看见。
    rgba_neck = rgba.copy()
    mask_neck = mask.copy()
    stub_top = max(0, neck_y - ov)
    if neck_y < H:
        rgba_neck[stub_top:neck_y] = rgba[neck_y]
        mask_neck[stub_top:neck_y] = mask[neck_y]

    for pid, reg in regions.items():
        src_rgba, src_mask = (rgba_neck, mask_neck) if pid == "seg_torso" else (rgba, mask)
        img, (x0, y0) = cut(src_mask, src_rgba, reg)
        if img is None:
            print(f"  跳过 {pid}（这块没有像素）")
            continue
        path = os.path.join(sprites, pid + ".png")
        img.save(path)
        out["parts"].append({
            "id": pid, "file": f"sprites/{pid}.png",
            "pos": [x0, y0], "size": [img.width, img.height],
            "group": groups[pid], "layer": layers[pid],
        })
        m = reg & src_mask
        preview[m] = (*tint[pid], 210)
        print(f"  {pid:10s} {img.width:4d}x{img.height:4d}  左上 ({x0},{y0})")

    out["parts"].sort(key=lambda p: p["layer"])
    with open(os.path.join(sprites, "body_parts.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    # 预览：切分着色图（人眼复核，不入库）
    pv = Image.new("RGBA", (W, H), (240, 242, 248, 255))
    pv.alpha_composite(Image.fromarray(np.asarray(Image.open(body_path).convert("RGBA"))))
    pv.alpha_composite(Image.fromarray(preview, "RGBA"))
    pp = os.path.join(args.root, args.preview)
    os.makedirs(os.path.dirname(pp), exist_ok=True)
    pv.convert("RGB").save(pp, quality=92)

    print(f"手臂离身行 {split_y}（此行以下按真实轮廓抠，以上竖切）")
    print(f"切线：颈 {neck_y} 肩 {shoulder_y} 髋 {hip_y} 裙摆底 {legs_top} 腕 {wrist_y}；"
          f"躯干 x [{TL},{TR}]；重叠 {ov}px")
    print(f"写出 {os.path.join(sprites,'body_parts.json')}")
    print(f"预览（不入库）：{args.preview}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
