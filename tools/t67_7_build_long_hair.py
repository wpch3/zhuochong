#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""T67.7 小寻 teen 长发四件构建（全帧自然 alpha 拆件 + 裁紧 + 去噪 + @2x 预乘）。

流水线（2026-10-27 隔离 testroot 验证通过，静止拼回零差异、ParamHairSway 三帧根定梢甩）：
  1. 读获批母稿（仅头发像素），迭代最近邻填色清除纯黑噪点（lum<45 的不透明像素；
     真赛璐璐线稿亮度在 78~107，不受影响），并补内部 alpha 空洞。
  2. 羽化去除母稿呆毛（生产独立 hair_ahoge 件保留）。
  3. 统一温和仿射到 848x1360 画布（以旧 acc_hair_long 内容框为几何真值，四件同源、零横拉）。
  4. back=母稿全 alpha 保自然外剪影；crown/sidelong 用旧长发件的连续 alpha 剪影当权重
     （自然丝缕边，压脖子/手臂处无矩形硬缝）。
  5. 逐件按 alpha 包围盒裁紧（不删任何头发像素，只去透明边），使 bend 按头发真实高度归一化；
     写 @2x 预乘 PNG，并打印四件 pos/anchor/scale 供 rig 接线（本脚本不自动改任何 rig.json）。

安全：必须显式 --out-sprites，绝不默认写生产目录。生产接入需另经用户批准。
用法：
  python tools/t67_7_build_long_hair.py \
    --master characters/xiaoxun/source/t67_7_master_haironly_v2_final.png \
    --rig characters/xiaoxun/forms/teen/rig.json \
    --out-1x /tmp/work/1x --out-sprites /tmp/zc-xxxx/.../sprites
"""
import argparse, json, os
import numpy as np
from PIL import Image, ImageFilter
from scipy import ndimage

CW, CH = 848, 1360
SX, SY, TX, TY = 0.9768, 0.7704, 9.1, 24.7          # 母稿->画布仿射（旧 acc_hair_long 框拟合）
IDMAP = {
    "t677_hair_long_back": "acc_hair_long",
    "t677_hair_crown_long": "acc_hair_crown_long",
    "t677_hair_sidelong_l": "acc_hair_sidelong_l",
    "t677_hair_sidelong_r": "acc_hair_sidelong_r",
}
OLD_WEIGHT = {
    "t677_hair_crown_long": "acc_hair_crown_long",
    "t677_hair_sidelong_l": "acc_hair_sidelong_l",
    "t677_hair_sidelong_r": "acc_hair_sidelong_r",
}


def despeckle(master, lum_thr=45.0, iters=20):
    """迭代最近邻填色清除纯黑噪点（保留 alpha 与线稿），并补内部 alpha 空洞。"""
    m = master.copy()
    op = m[..., 3] > 40
    inv = ~op
    lab, n = ndimage.label(inv)
    border = set(np.r_[lab[0, :], lab[-1, :], lab[:, 0], lab[:, -1]].tolist())
    hole = np.isin(lab, [l for l in range(1, n + 1) if l not in border])
    if hole.any():
        _, (iy, ix) = ndimage.distance_transform_edt(hole, return_indices=True)
        for c in range(4):
            m[..., c] = np.where(hole, m[..., c][iy, ix], m[..., c])
    for _ in range(iters):
        op2 = m[..., 3] > 40
        sel = op2 & (m[..., :3].mean(2) < lum_thr)
        if not sel.any():
            break
        _, (iy, ix) = ndimage.distance_transform_edt(sel, return_indices=True)
        for c in range(3):
            m[..., c] = np.where(sel, m[..., c][iy, ix], m[..., c])
    return m


def drop_ahoge(m, H, W):
    yy, xx = np.indices((H, W))
    ah = (xx >= 378) & (xx <= 502) & (yy >= 28) & (yy <= 120)
    w = np.array(Image.fromarray((ah * 255).astype(np.uint8)).filter(
        ImageFilter.GaussianBlur(6))).astype(float) / 255.0
    m = m.copy()
    m[..., 3] = (m[..., 3].astype(float) * (1.0 - w)).astype(np.uint8)
    return m


def to_canvas(m, W, H):
    im = Image.fromarray(m).resize((int(round(W * SX)), int(round(H * SY))), Image.LANCZOS)
    cv = Image.new("RGBA", (CW, CH), (0, 0, 0, 0))
    cv.paste(im, (int(round(TX)), int(round(TY))), im)
    return np.array(cv)


def old_coverage(rig, rig_dir, pid):
    pr = next(p for p in rig["parts"] if p["id"] == pid)
    im = np.array(Image.open(os.path.join(rig_dir, pr["file"])).convert("RGBA"))
    Hh, Ww = im.shape[:2]
    ax, ay = pr["anchor"]
    sc, pos = pr["scale"], pr["pos"]
    cov = np.zeros((CH, CW), float)
    ys, xs = np.nonzero(im[..., 3] > 8)
    wgt = im[ys, xs, 3].astype(float) / 255.0
    cx = ((xs - ax * Ww) * sc + pos[0]).astype(int)
    cy = ((ys - ay * Hh) * sc + pos[1]).astype(int)
    ok = (cx >= 0) & (cx < CW) & (cy >= 0) & (cy < CH)
    cov[cy[ok], cx[ok]] = np.maximum(cov[cy[ok], cx[ok]], wgt[ok])
    return np.array(Image.fromarray((cov * 255).astype(np.uint8)).filter(
        ImageFilter.GaussianBlur(2))).astype(float) / 255.0


def premul2x(crop):
    a = crop.astype(float)
    al = a[..., 3:4] / 255.0
    pm = np.concatenate([a[..., :3] * al, a[..., 3:4]], 2)
    im = Image.fromarray(np.clip(pm, 0, 255).astype(np.uint8)).resize(
        (crop.shape[1] * 2, crop.shape[0] * 2), Image.LANCZOS)
    b = np.array(im).astype(float)
    al2 = np.maximum(b[..., 3:4] / 255.0, 0.25)
    rgb = np.clip(b[..., :3] / al2, 0, 255)
    return Image.fromarray(np.concatenate([rgb, b[..., 3:4]], 2).astype(np.uint8), "RGBA")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--master", required=True)
    ap.add_argument("--rig", required=True, help="生产 rig.json（取旧件自然 alpha 真值）")
    ap.add_argument("--out-1x", required=True)
    ap.add_argument("--out-sprites", required=True, help="输出 @2x 目录（显式指定，禁止生产默认）")
    args = ap.parse_args()
    os.makedirs(args.out_1x, exist_ok=True)
    os.makedirs(args.out_sprites, exist_ok=True)

    master = np.array(Image.open(args.master).convert("RGBA"))
    H, W = master.shape[:2]
    assert (W, H) == (848, 1264), (W, H)
    clean = drop_ahoge(despeckle(master), H, W)
    mc = to_canvas(clean, W, H)
    master_a = mc[..., 3].astype(float) / 255.0

    rig = json.load(open(args.rig))
    rig_dir = os.path.dirname(args.rig)
    pieces = {"t677_hair_long_back": mc}
    for name, oldpid in OLD_WEIGHT.items():
        w = old_coverage(rig, rig_dir, oldpid)
        o = mc.copy().astype(float)
        o[..., 3] = master_a * 255.0 * np.clip(w, 0, 1)
        pieces[name] = np.clip(o, 0, 255).astype(np.uint8)

    rig_write = {}
    for name, full in pieces.items():
        ys, xs = np.nonzero(full[..., 3] > 8)
        x0, x1, y0, y1 = xs.min(), xs.max() + 1, ys.min(), ys.max() + 1
        crop = full[y0:y1, x0:x1]
        Image.fromarray(crop).save(os.path.join(args.out_1x, name + ".png"))
        premul2x(crop).save(os.path.join(args.out_sprites, name + "@2x.png"))
        rig_write[IDMAP[name]] = {"file": f"sprites/{name}@2x.png",
                                  "pos": [int(x0), int(y0)], "anchor": [0, 0], "scale": 0.5}
        print(f"{name:24s} bbox x[{x0},{x1}] y[{y0},{y1}] {crop.shape[1]}x{crop.shape[0]}")

    recon = np.zeros((CH, CW), float)
    for full in pieces.values():
        recon = np.maximum(recon, full[..., 3].astype(float) / 255.0)
    print("画布拼回平均差:", float(np.abs(recon - master_a).mean()))
    print("\nrig 接线（人工复核后写入，脚本不改 rig.json）:")
    print(json.dumps(rig_write, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
