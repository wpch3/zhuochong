#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""make_mouth_line_cut.py - 把闭合笑线从头部底图上「剪切」下来（G107）

为什么要有这一步
----------------
旧流水线里 sprites/mouth_open.png 是 tools/make_parts.py 用一个手填的 --mouth 框
**复制**出来的，而 make_parts.py 根本不在 rebuild_parts.sh 里，于是这张图一直是很久
以前某次手工运行留下的陈旧产物。2026-10-15 实测：

  * mouth_open.png 在 body_full 里的落点是 y 252..275；
  * 真正的笑线（find_mouth_line 量出来的）在 y 246..250；
  * **垂直方向零重叠** —— 这张「笑线件」里装的是下巴阴影和一角衣领（右下角那块蓝边）。

更要命的是它是「复制」而不是「剪切」：原来那条笑线始终烙在 seg_head.png 上。张嘴时
口内椭圆只盖得住笑线中段，两端上翘的嘴角高光露在椭圆上方，看起来就像嘴上挂了两撇
小胡子 —— 用户 2026-10-15 反馈的「惊讶时嘴型重合」就是它。

因为淡出的是那张错位的拷贝件，调 ParamMouthOpenY → mouth_open.alpha 的斜率从 -0.9
一路拉到 -3.5 都毫无效果（实测满张嘴时整个嘴区像素最大只差 12/255）。

这一步做的事（真正的剪切）
--------------------------
1. 从**全流程只读、从不被改写**的 sprites/body_full.png 上，按 mouth_parts.json 实测
   的笑线框外扩 PAD 像素取一块；
2. 用「框上沿上一行 ↔ 框下沿下一行」逐列线性插值，算出这块地方底下本来的肤色
   skin_ref；
3. alpha = 该像素与 skin_ref 的色差。按色差而不是按「比肤色暗」来抠，是因为笑线
   **两端的嘴角高光比肤色还亮**，用暗度判据会把高光丢掉（丢了之后闭嘴只剩一条
   直棍，没有弯度也没有嘴角）；
   rgb 用 C' = skin_ref + (C - skin_ref) / alpha 反解，保证 alpha=1 处合成回去就是
   原像素，闭嘴外观与改动前逐像素一致；
4. 把 seg_head.png 上同一块**换成 skin_ref**（擦掉笑线）；
5. 更新 parts_report.json 里 mouth_open.png 的 size/pos，make_rig.py 据此定位。

幂等性
------
剪切源是 body_full.png（全流程只读），擦除目标 seg_head.png 每次 rebuild 都会由
make_body_parts.py 重新生成；即便单独重跑本脚本也安全 —— 第二次擦的是已经插值好的
皮肤，插出来还是同一片皮肤。

用法：~/.imgenv/bin/python tools/make_mouth_line_cut.py --character xiaoxun --form teen
"""
from __future__ import annotations

import argparse
import json
import os

import numpy as np
from PIL import Image

PAD = 3           # 笑线框外扩像素：两端白高光比暗线本体各宽/高 1~2px
A_LO = 3.0        # 与肤色的色差 <= A_LO 视作纯皮肤 → 全透明（挡住肤色渐变的噪声）
A_HI = 16.0       # 色差 >= A_HI 视作线上像素 → 全不透明
A_GAMMA = 0.85    # alpha 曲线，略微提亮中间调，让羽化边不至于太虚
UNMIX_MIN = 0.12  # alpha 低于此值不做反解（除法会炸）


def skin_ref_block(arr: np.ndarray, x0: int, x1: int, y0: int, y1: int) -> np.ndarray:
    """用框上下各一行逐列线性插值，还原这块地方「本来的皮肤」。

    嘴周围是一片平缓的肤色渐变，上下两行之间线性插值足够贴；用整张图的平均肤色反而
    会在下巴阴影那一侧留下一块亮斑。
    """
    top = arr[y0 - 1, x0:x1 + 1, :].astype(np.float64)        # (W,4)
    bot = arr[y1 + 1, x0:x1 + 1, :].astype(np.float64)        # (W,4)
    h = y1 - y0 + 1
    t = ((np.arange(h, dtype=np.float64) + 1.0) / (h + 1.0))[:, None, None]
    return top[None, :, :] * (1.0 - t) + bot[None, :, :] * t  # (H,W,4)


def tighten(rgba: np.ndarray):
    """裁掉四周全透明的行列，返回 (裁后图, (dx,dy))。"""
    a = rgba[..., 3]
    ys, xs = np.nonzero(a > 0)
    if len(ys) == 0:
        return rgba, (0, 0)
    y0, y1 = int(ys.min()), int(ys.max())
    x0, x1 = int(xs.min()), int(xs.max())
    return rgba[y0:y1 + 1, x0:x1 + 1, :], (x0, y0)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--character", required=True)
    ap.add_argument("--form", required=True)
    ap.add_argument("--root", default=".")
    args = ap.parse_args()

    base = os.path.join(args.root, "characters", args.character, "forms", args.form)
    sp = os.path.join(base, "sprites")

    body_path = os.path.join(sp, "body_full.png")
    head_path = os.path.join(sp, "seg_head.png")
    mouth_json = os.path.join(sp, "mouth_parts.json")
    bodyparts_json = os.path.join(sp, "body_parts.json")
    report_json = os.path.join(sp, "parts_report.json")

    for p in (body_path, head_path, mouth_json, bodyparts_json, report_json):
        if not os.path.exists(p):
            raise SystemExit(f"[mouth_line_cut] 缺少输入：{p}")

    with open(mouth_json, encoding="utf-8") as f:
        mouth = json.load(f)
    line = mouth["line"]

    with open(bodyparts_json, encoding="utf-8") as f:
        bodyparts = json.load(f)
    seg_head = next((p for p in bodyparts["parts"] if p["id"] == "seg_head"), None)
    if seg_head is None:
        raise SystemExit("[mouth_line_cut] body_parts.json 里找不到 seg_head")
    hx, hy = seg_head["pos"]          # seg_head 在 body_full 里的左上角

    body = np.asarray(Image.open(body_path).convert("RGBA")).astype(np.float64)
    head = np.asarray(Image.open(head_path).convert("RGBA")).copy()

    # ---- 1. 笑线框外扩 ----
    x0 = int(line["x0"]) - PAD
    x1 = int(line["x1"]) + PAD
    y0 = int(line["y0"]) - PAD
    y1 = int(line["y1"]) + PAD
    H, W = body.shape[0], body.shape[1]
    if not (1 <= x0 and x1 < W - 1 and 1 <= y0 and y1 < H - 1):
        raise SystemExit(f"[mouth_line_cut] 笑线框贴边了：x{x0}..{x1} y{y0}..{y1}")

    # ---- 2. 还原这块地方本来的皮肤 ----
    skin = skin_ref_block(body, x0, x1, y0, y1)               # (H,W,4)
    crop = body[y0:y1 + 1, x0:x1 + 1, :]                      # (H,W,4)

    # ---- 3. 按色差抠出笑线（暗线 + 两端亮高光都要留住）----
    d = np.abs(crop[..., :3] - skin[..., :3]).max(axis=2)     # (H,W)
    alpha = np.clip((d - A_LO) / (A_HI - A_LO), 0.0, 1.0) ** A_GAMMA

    rgb = crop[..., :3].copy()
    m = alpha >= UNMIX_MIN
    if m.any():
        safe = np.where(m, alpha, 1.0)[..., None]   # alpha 太小的地方不参与除法
        unmix = skin[..., :3] + (crop[..., :3] - skin[..., :3]) / safe
        rgb[m] = np.clip(unmix[m], 0.0, 255.0)

    cut = np.empty(crop.shape, dtype=np.uint8)
    cut[..., :3] = np.round(rgb).astype(np.uint8)
    cut[..., 3] = np.round(alpha * 255.0).astype(np.uint8)
    cut, (dx, dy) = tighten(cut)

    # ---- 4. 把 seg_head 上同一块换成皮肤（擦掉笑线）----
    sx0, sy0 = x0 - hx, y0 - hy
    sx1, sy1 = x1 - hx, y1 - hy
    if not (0 <= sx0 and sx1 < head.shape[1] and 0 <= sy0 and sy1 < head.shape[0]):
        raise SystemExit(f"[mouth_line_cut] 笑线不在 seg_head 范围内：{sx0}..{sx1} / {sy0}..{sy1}")
    before = head[sy0:sy1 + 1, sx0:sx1 + 1, :].astype(np.float64).copy()
    head[sy0:sy1 + 1, sx0:sx1 + 1, :] = np.round(skin).astype(np.uint8)
    erased = float(np.abs(before - skin).max())

    # ---- 5. 落盘 ----
    Image.fromarray(cut, "RGBA").save(os.path.join(sp, "mouth_open.png"))
    Image.fromarray(head, "RGBA").save(head_path)

    pos = [x0 + dx, y0 + dy]
    size = [int(cut.shape[1]), int(cut.shape[0])]
    with open(report_json, encoding="utf-8") as f:
        report = json.load(f)
    entry = next((p for p in report["parts"] if p["name"] == "mouth_open.png"), None)
    if entry is None:
        entry = {"name": "mouth_open.png"}
        report["parts"].append(entry)
    entry["size"] = size
    entry["pos"] = pos
    entry["note"] = "由 make_mouth_line_cut.py 从 body_full 精确剪下（不是 make_parts.py 的旧复制件）"
    with open(report_json, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    trace = {
        "tool": "make_mouth_line_cut.py",
        "source": "sprites/body_full.png",
        "line": line,
        "pad": PAD,
        "cut_box": {"x0": x0, "x1": x1, "y0": y0, "y1": y1},
        "mouth_open": {"pos": pos, "size": size},
        "seg_head_origin": [hx, hy],
        "erased_max_delta": round(erased, 2),
        "alpha": {"lo": A_LO, "hi": A_HI, "gamma": A_GAMMA, "unmix_min": UNMIX_MIN},
        "note": "笑线已从 seg_head 擦除并剪成 mouth_open.png；张嘴时淡出的就是原件本身",
    }
    with open(os.path.join(sp, "mouth_line_cut.json"), "w", encoding="utf-8") as f:
        json.dump(trace, f, ensure_ascii=False, indent=2)

    print(f"笑线剪切：body_full x{x0}..{x1} y{y0}..{y1} → mouth_open.png "
          f"{size[0]}x{size[1]} @ {pos}")
    print(f"  seg_head 对应块已填平（擦前后最大色差 {erased:.1f}），"
          f"不透明像素 {int((cut[...,3] > 0).sum())} 个")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
