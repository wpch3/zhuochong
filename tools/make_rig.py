#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""make_rig.py - 生成 forms/<形态>/rig.json（立绘骨架配置）。

输入：
  sprites/parts_report.json  由 make_parts.py 生成（部件尺寸与在全身图中的位置）
  sprites_report.json        由 prepare_sprites.py 生成（全身图尺寸、建议区域）
输出：
  characters/<角色>/forms/<形态>/rig.json

这样拆件与骨架永远对齐：坐标由脚本从实际素材量取，不手写魔法数字。
"""
from __future__ import annotations
import argparse, json, os, sys


def build(parts, sprite, canvas, name, cw, ch):
    sp_w, sp_h = sprite["sprite_size"]
    ox = (cw - sp_w) // 2
    oy = ch - sp_h
    by_name = {p["name"]: p for p in parts["parts"]}

    def part(img_name, group, tags, layer, order_note=""):
        p = by_name[img_name]
        return {
            "id": img_name.replace(".png", ""),
            "file": f"sprites/{img_name}",
            "group": group,
            "layer": layer,
            "pos": [ox + p["pos"][0], oy + p["pos"][1]],
            "anchor": [0, 0],
            "tags": tags,
            "note": order_note,
        }

    # 区域（画布坐标）：来自 sprites_report.json 的建议区域
    reg = sprite["suggested_regions"]
    regions = [
        {"id": "head", "rect": reg["head"], "action": "head_pat", "cursor": "hand"},
        {"id": "body", "rect": reg["body"], "action": "stroke", "cursor": "hand"},
        {"id": "feet", "rect": reg["feet"], "action": "surprised", "cursor": "hand"},
    ]

    neck_y = oy + int(sp_h * 0.26)      # 颈部：约在头部下缘
    chest_y = oy + int(sp_h * 0.36)
    body_part = {
        "id": "body_full",
        "file": "sprites/body_full.png",
        "group": "root",
        "layer": 100,
        "pos": [ox, oy],
        "anchor": [0, 0],
        "tags": ["body"],
        "note": "全身（待 AI 拆件：手臂/上下半身/关节补图）",
    }
    parts_list = [
        body_part,
        part("mouth_open.png", "head", ["mouth"], 210, "口型 A：说话时按通道闪烁"),
        part("eye_open_left.png", "head", ["eye_open", "gaze"], 220),
        part("eye_open_right.png", "head", ["eye_open", "gaze"], 221),
        part("eye_closed_left.png", "head", ["eye_closed"], 230, "闭眼：眨眼时与睁眼交叉淡化"),
        part("eye_closed_right.png", "head", ["eye_closed"], 231),
    ]

    # 网格形变（Live2D 式）的曲线语义：**底边是根**（人物站在地上）。
    #   root = 底边固定、越往上位移越大（身体侧摆，头跟着走）
    #   sine = 两端固定、中段最大（呼吸、弯腰）
    #   tip  = 顶边固定、越往下越大（后发、裙摆、尾巴这类吊着的部件）
    # 注意：当前素材是单图层全身图，五官是贴在上面的独立部件，
    #   所以身体弯多少，head 组就要跟着位移多少，否则眼睛会从脸上滑走。
    #   跟随量 = amp x f(u)，脸部 u≈0.77 → root:0.59、sine:0.66。
    actions = [
        {"id": "breath", "priority": 1, "duration": 0, "loop": True, "return_state": "idle",
         "channels": [
             {"target": "body_full", "param": "bend_y", "wave": "sine", "amp": -3.2, "freq": 0.28,
              "curve": "sine"},
             # 脸跟着胸腔一起起伏（-3.2 x 0.66 ≈ -2.1），方向必须与身体一致
             {"target": "head", "param": "dy", "wave": "sine", "amp": -2.1, "freq": 0.28},
         ]},
        {"id": "sway", "priority": 2, "duration": 0, "loop": True, "return_state": "idle",
         "channels": [
             {"target": "body_full", "param": "bend_x", "wave": "sine", "amp": 10, "freq": 0.18,
              "curve": "root"},
             {"target": "body_full", "param": "bend_y", "wave": "sine", "amp": -4, "freq": 0.36,
              "curve": "sine"},
             {"target": "head", "param": "rot_deg", "wave": "sine", "amp": 1.2, "freq": 0.18},
             # 10 x 0.59 ≈ 5.9：五官跟上身体的横摆
             {"target": "head", "param": "dx", "wave": "sine", "amp": 5.9, "freq": 0.18},
             {"target": "head", "param": "dy", "wave": "sine", "amp": -2.6, "freq": 0.36},
         ]},
        {"id": "idle", "priority": 0, "loop": True, "interruptible": True,
         "channels": [
             # 常驻呼吸：不点任何按钮，角色也一直是活的（幅度刻意很小，久看不晕）
             {"target": "body_full", "param": "bend_y", "wave": "sine", "amp": -2.0, "freq": 0.24,
              "curve": "sine"},
             # 极慢的重心左右移动，避免"站成雕像"
             {"target": "body_full", "param": "bend_x", "wave": "sine", "amp": 2.6, "freq": 0.06,
              "curve": "root"},
             {"target": "head", "param": "dy", "wave": "sine", "amp": -1.3, "freq": 0.24},
             {"target": "head", "param": "dx", "wave": "sine", "amp": 1.5, "freq": 0.06},
             {"target": "head", "param": "rot_deg", "wave": "sine", "amp": 0.7, "freq": 0.13, "phase": 0.3},
             {"target": "eye_open_left", "param": "dy", "wave": "sine", "amp": 0.5, "freq": 0.2},
             {"target": "eye_open_right", "param": "dy", "wave": "sine", "amp": 0.5, "freq": 0.2},
             {"target": "eye_closed_left", "param": "dy", "wave": "sine", "amp": 0.5, "freq": 0.2},
             {"target": "eye_closed_right", "param": "dy", "wave": "sine", "amp": 0.5, "freq": 0.2},
         ]},
        {"id": "focus", "priority": 2, "loop": True, "interruptible": True, "return_state": "idle",
         "channels": [
             {"target": "head", "param": "dy", "wave": "sine", "amp": 1.2, "freq": 0.3},
             {"target": "head", "param": "dx", "wave": "sine", "amp": 2.0, "freq": 0.17},
         ]},
        {"id": "head_pat", "priority": 6, "duration": 1.0, "return_state": "idle",
         "interruptible": False,
         "channels": [
             {"target": "head", "param": "dy", "wave": "pulse", "amp": -7.0, "dur": 0.35, "ease": "out_back"},
             {"target": "head", "param": "dy", "wave": "sine", "amp": 2.0, "freq": 3.5, "dur": 1.0},
         ],
         "part_overrides": {
             "eye_open_left": {"opacity": 0.0}, "eye_open_right": {"opacity": 0.0},
             "eye_closed_left": {"opacity": 1.0}, "eye_closed_right": {"opacity": 1.0},
         }},
        {"id": "happy", "priority": 7, "duration": 1.6, "return_state": "idle",
         "interruptible": False,
         "channels": [
             {"target": "root", "param": "dy", "wave": "bounce", "amp": -22.0, "dur": 0.45, "ease": "out_back"},
             {"target": "root", "param": "dy", "wave": "bounce", "amp": -12.0, "dur": 0.5, "ease": "out_back"},
             {"target": "head", "param": "rot_deg", "wave": "bounce", "amp": 5.0, "dur": 0.5},
         ],
         "part_overrides": {
             "eye_open_left": {"opacity": 0.0}, "eye_open_right": {"opacity": 0.0},
             "eye_closed_left": {"opacity": 1.0}, "eye_closed_right": {"opacity": 1.0},
             "mouth_open": {"opacity": 0.85},
         }},
        {"id": "sad", "priority": 3, "loop": True, "interruptible": True, "return_state": "idle",
         "channels": [
             {"target": "head", "param": "dy", "wave": "pulse", "amp": 6.0, "dur": 0.5, "ease": "out"},
             {"target": "head", "param": "rot_deg", "wave": "sine", "amp": 1.0, "freq": 0.12},
         ],
         "part_overrides": {"eye_open_left": {"opacity": 0.7}, "eye_open_right": {"opacity": 0.7}}},
        {"id": "surprised", "priority": 6, "duration": 0.9, "return_state": "idle",
         "interruptible": False,
         "channels": [
             {"target": "head", "param": "dy", "wave": "bounce", "amp": -10.0, "dur": 0.35, "ease": "out_back"},
             {"target": "eye_open_left", "param": "sx", "wave": "pulse", "amp": 0.18, "dur": 0.2},
             {"target": "eye_open_right", "param": "sx", "wave": "pulse", "amp": 0.18, "dur": 0.2},
             {"target": "eye_open_left", "param": "sy", "wave": "pulse", "amp": 0.22, "dur": 0.2},
             {"target": "eye_open_right", "param": "sy", "wave": "pulse", "amp": 0.22, "dur": 0.2},
             {"target": "mouth_open", "param": "alpha", "wave": "pulse", "amp": -0.55, "dur": 0.25},
         ]},
        {"id": "hammered", "priority": 9, "duration": 0.85, "return_state": "idle",
         "interruptible": False,
         "channels": [
             {"target": "root", "param": "dx", "wave": "decay", "amp": 14.0, "freq": 3.2, "dur": 0.7},
             {"target": "root", "param": "dy", "wave": "decay", "amp": 8.0, "freq": 4.0, "dur": 0.7},
             {"target": "head", "param": "rot_deg", "wave": "decay", "amp": 7.0, "freq": 2.6, "dur": 0.7},
         ],
         "part_overrides": {"mouth_open": {"opacity": 0.7}}},
        {"id": "stroke", "priority": 5, "loop": True, "interruptible": True, "return_state": "idle",
         "channels": [
             {"target": "root", "param": "rot_deg", "wave": "sine", "amp": 1.6, "freq": 0.45},
             {"target": "head", "param": "dx", "wave": "sine", "amp": 3.0, "freq": 0.45},
         ],
         "part_overrides": {
             "eye_open_left": {"opacity": 0.25}, "eye_open_right": {"opacity": 0.25},
             "eye_closed_left": {"opacity": 0.75}, "eye_closed_right": {"opacity": 0.75},
             "mouth_open": {"opacity": 0.35},
         }},
        {"id": "clicked", "priority": 4, "duration": 0.55, "return_state": "idle",
         "interruptible": False,
         "channels": [
             {"target": "root", "param": "dy", "wave": "bounce", "amp": -6.0, "dur": 0.28},
             {"target": "head", "param": "rot_deg", "wave": "decay", "amp": 3.5, "freq": 3.0, "dur": 0.4},
         ]},
        {"id": "dragged", "priority": 5, "loop": True, "interruptible": True, "return_state": "idle",
         "channels": [
             {"target": "root", "param": "rot_deg", "wave": "sine", "amp": 3.0, "freq": 0.4},
             {"target": "head", "param": "dy", "wave": "sine", "amp": 2.5, "freq": 0.8},
         ],
         "part_overrides": {"mouth_open": {"opacity": 0.6}}},
        {"id": "talk", "priority": 4, "loop": True, "interruptible": True, "return_state": "idle",
         "channels": [
             {"target": "mouth_open", "param": "alpha", "wave": "pulse", "amp": -0.5, "dur": 0.12, "ease": "out"},
             {"target": "mouth_open", "param": "sy", "wave": "sine", "amp": 0.12, "freq": 3.0},
             {"target": "head", "param": "dy", "wave": "sine", "amp": 1.2, "freq": 0.5},
         ]},
        {"id": "think", "priority": 3, "loop": True, "interruptible": True, "return_state": "idle",
         "channels": [
             {"target": "head", "param": "rot_deg", "wave": "pulse", "amp": -5.0, "dur": 0.6, "ease": "out"},
             {"target": "head", "param": "dx", "wave": "sine", "amp": 1.2, "freq": 0.2},
             {"target": "eye_open_left", "param": "dx", "wave": "sine", "amp": 1.5, "freq": 0.25},
             {"target": "eye_open_right", "param": "dx", "wave": "sine", "amp": 1.5, "freq": 0.25},
         ]},
        {"id": "sleep", "priority": 8, "loop": True, "interruptible": False, "dim": 0.35,
         "channels": [
             {"target": "head", "param": "dy", "wave": "sine", "amp": 3.0, "freq": 0.11},
             {"target": "head", "param": "rot_deg", "wave": "sine", "amp": 2.0, "freq": 0.07},
             {"target": "root", "param": "dy", "wave": "pulse", "amp": 4.0, "dur": 1.2, "ease": "out"},
         ],
         "part_overrides": {
             "eye_open_left": {"opacity": 0.0}, "eye_open_right": {"opacity": 0.0},
             "eye_closed_left": {"opacity": 1.0}, "eye_closed_right": {"opacity": 1.0},
         }},
    ]

    return {
        "schema_version": "1.0",
        "id": f"{name}_teen",
        "name": name,
        "canvas": {"w": cw, "h": ch},
        "origin": [cw // 2, ch],
        "ground_line": ch - 8,
        "groups": {
            "root": {"pivot": [cw // 2, ch], "parent": ""},
            "chest": {"pivot": [cw // 2, chest_y], "parent": "root"},
            "head": {"pivot": [cw // 2, neck_y], "parent": "chest"},
        },
        "gaze": {"max_offset": [3.0, 2.0]},
        "blink": {
            "enabled": True,
            "closing_s": 0.10, "closed_s": 0.05, "opening_s": 0.15,
            "interval_min_s": 2.0, "interval_max_s": 8.0, "interval_exponential": False,
            "note": "参数与 Live2D CubismEyeBlink 的五态机一致：等待 → 闭合 → 保持 → 睁开",
        },
        "parts": parts_list,
        "regions": regions,
        "actions": actions,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--character", required=True)
    ap.add_argument("--form", required=True)
    ap.add_argument("--canvas", default="848x1360")
    ap.add_argument("--root", default=".")
    ap.add_argument("--name", default="小寻")
    args = ap.parse_args()
    cw, ch = (int(v) for v in args.canvas.lower().split("x"))
    base = os.path.join(args.root, "characters", args.character, "forms", args.form)
    with open(os.path.join(base, "sprites", "parts_report.json"), encoding="utf-8") as f:
        parts = json.load(f)
    with open(os.path.join(base, "sprites_report.json"), encoding="utf-8") as f:
        sprite = json.load(f)
    rig = build(parts, sprite, args.canvas, args.name, cw, ch)
    out = os.path.join(base, "rig.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(rig, f, ensure_ascii=False, indent=2)
    print(f"写出 {out}：部件 {len(rig['parts'])} 动作 {len(rig['actions'])} 区域 {len(rig['regions'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
