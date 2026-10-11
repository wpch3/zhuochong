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


def build(parts, sprite, canvas, name, cw, ch, head_is_part=False,
          seg=None, anchors=None):
    sp_w, sp_h = sprite["sprite_size"]
    ox = (cw - sp_w) // 2
    oy = ch - sp_h
    by_name = {p["name"]: p for p in parts["parts"]}
    # 分段素材（tools/make_body_parts.py 的产物）在场时，身体不再是一张整图，
    # 形变通道要打到躯干那一段上。
    body_id = "seg_torso" if seg else "body_full"

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

    # 关节点（画布坐标）：有 anchors.json 就用实测值，没有就退回比例估算。
    # 骨架枢轴必须落在真关节上，否则一转头就像在转盘子。
    def apt(key, ratio_y, ratio_x=0.5):
        if anchors and key in anchors.get("points", {}):
            x, y = anchors["points"][key]
            return [ox + int(round(x)), oy + int(round(y))]
        return [ox + int(sp_w * ratio_x), oy + int(sp_h * ratio_y)]

    neck_pt = apt("neck", 0.26)
    hip_pt = apt("hip", 0.545)
    waist_pt = apt("waist", 0.51)
    sh_l = apt("shoulder_l", 0.28, 0.22)
    sh_r = apt("shoulder_r", 0.28, 0.78)
    neck_y = neck_pt[1]
    chest_y = waist_pt[1]
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
    if seg:
        # 分段身体：位置由 make_body_parts.py 从素材量出，这里只做画布平移。
        tag_of = {"seg_head": ["head_base"], "seg_torso": ["body"],
                  "seg_arm_l": ["arm"], "seg_arm_r": ["arm"],
                  "seg_leg_l": ["leg"], "seg_leg_r": ["leg"]}
        body_parts_list = [{
            "id": sp["id"],
            "file": sp["file"],
            "group": sp["group"],
            "layer": sp["layer"],
            "pos": [ox + sp["pos"][0], oy + sp["pos"][1]],
            "anchor": [0, 0],
            "tags": tag_of.get(sp["id"], ["body"]),
            "note": "分段部件（make_body_parts.py 切出，关节处有重叠带兜底）",
        } for sp in seg["parts"]]
    else:
        body_parts_list = [body_part]
    parts_list = body_parts_list + [
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
    # 注意：当前素材是单图层全身图，五官是贴在上面的独立部件。
    #   身体弯曲时五官必须跟着走，否则眼睛会从脸上滑走——这件事由引擎的
    #   groups.*.bend_follow 自动完成（按组枢轴所在高度取同一条曲线的权重），
    #   所以这里**不要**再手写跟随通道，写了会动两次。
    actions = [
        {"id": "breath", "priority": 1, "duration": 0, "loop": True, "return_state": "idle",
         "channels": [
             {"target": body_id, "param": "bend_y", "wave": "sine", "amp": -3.2, "freq": 0.28,
              "curve": "sine"},
         ]},
        {"id": "sway", "priority": 2, "duration": 0, "loop": True, "return_state": "idle",
         "channels": [
             {"target": body_id, "param": "bend_x", "wave": "sine", "amp": 10, "freq": 0.18,
              "curve": "root"},
             {"target": body_id, "param": "bend_y", "wave": "sine", "amp": -4, "freq": 0.36,
              "curve": "sine"},
             {"target": "head", "param": "rot_deg", "wave": "sine", "amp": 1.2, "freq": 0.18},
         ]},
        {"id": "idle", "priority": 0, "loop": True, "interruptible": True,
         "channels": [
             # 常驻呼吸：不点任何按钮，角色也一直是活的（幅度刻意很小，久看不晕）
             {"target": body_id, "param": "bend_y", "wave": "sine", "amp": -2.0, "freq": 0.24,
              "curve": "sine"},
             # 极慢的重心左右移动，避免"站成雕像"
             {"target": body_id, "param": "bend_x", "wave": "sine", "amp": 2.6, "freq": 0.06,
              "curve": "root"},
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

    # ---- 分段素材才有的次级动作：手臂摆动、重心移动 ----
    # 幅度刻意保守：关节处只有 3% 身高的重叠带兜底，摆太大会露接缝。
    # 等画出真正的关节补图（GAPS G4）再放大。
    if seg:
        def add(action_id, chans):
            for a in actions:
                if a["id"] == action_id:
                    a["channels"].extend(chans)

        def arm(side, param, amp, freq, phase=0.0, wave="sine", **kw):
            """手臂通道。**整块旋转手臂会在肩膀露接缝**：手臂是竖切下来的，
               里面带着一条外套前襟，转 26° 时那条会甩到身体轮廓外面（实测）。
               所以手臂一律用网格形变 bend：curve=tip 表示顶边（肩）钉死、
               越往下位移越大——和 Live2D 的手臂变形器同一个思路，肩膀永远不裂。"""
            tgt = f"seg_arm_{side}" if param.startswith("bend") else f"arm_{side}"
            c = {"target": tgt, "param": param, "wave": wave, "amp": amp, "freq": freq}
            if param.startswith("bend"):
                c["curve"] = "tip"
            if phase:
                c["phase"] = phase
            c.update(kw)
            return c

        # 待机：手臂跟着重心极慢地荡，相位比身体晚一点（次级动作的惯性感）
        add("idle", [arm("l", "bend_x", 2.2, 0.06, 0.12),
                     arm("r", "bend_x", 2.2, 0.06, 0.12),
                     arm("l", "dy", 0.6, 0.24, 0.18),
                     arm("r", "dy", 0.6, 0.24, 0.18)])
        # 呼吸：肩胛随胸腔起伏
        add("breath", [arm("l", "dy", 1.0, 0.28, 0.15),
                       arm("r", "dy", 1.0, 0.28, 0.15),
                       arm("l", "bend_x", 1.5, 0.28, 0.15),
                       arm("r", "bend_x", 1.5, 0.28, 0.15)])
        # 左右摇摆：手臂甩得比身体晚一点，幅度比身体小（次级动作）
        add("sway", [arm("l", "bend_x", 7.0, 0.18, 0.06),
                     arm("r", "bend_x", 7.0, 0.18, 0.06)])
        # 开心：整个人跳起来时手臂有滞后
        add("happy", [arm("l", "bend_x", -9.0, 0.0, 0.0, wave="bounce", dur=0.5),
                      arm("r", "bend_x", 9.0, 0.0, 0.0, wave="bounce", dur=0.5)])
        # 被敲：手臂跟着抖
        add("hammered", [arm("l", "bend_x", 10.0, 2.6, 0.0, wave="decay", dur=0.7),
                         arm("r", "bend_x", 10.0, 2.6, 0.0, wave="decay", dur=0.7)])

        # 挥手：单图层时代做不到的动作（没有独立手臂，一抬就整张图跟着转）。
        # 同样用 bend：肩膀钉死，手往外甩 + 往上抬，再叠一个快速左右摆。
        actions.append({
            "id": "wave", "priority": 6, "duration": 2.4, "return_state": "idle",
            "interruptible": False,
            "channels": [
                {"target": "seg_arm_r", "param": "bend_x", "wave": "pulse",
                 "amp": 92.0, "curve": "tip", "dur": 2.4, "ease": "out"},
                {"target": "seg_arm_r", "param": "bend_y", "wave": "pulse",
                 "amp": -78.0, "curve": "tip", "dur": 2.4, "ease": "out"},
                {"target": "seg_arm_r", "param": "bend_x", "wave": "sine",
                 "amp": 26.0, "curve": "tip", "freq": 1.8, "dur": 2.4},
                {"target": "head", "param": "rot_deg", "wave": "sine",
                 "amp": 2.0, "freq": 0.8, "dur": 2.4},
                {"target": "root", "param": "dy", "wave": "sine",
                 "amp": -2.0, "freq": 1.6, "dur": 2.4},
            ],
            "part_overrides": {"mouth_open": {"opacity": 0.8}},
        })

    # ---- 组（骨架）。枢轴=真关节点；bend_follow=跟着谁的网格形变走 ----
    # bend_follow 的取样高度有两种语义，别搞混：
    #   不写 bend_follow_at → 每个部件按**自己所在的高度**取样。贴在父部件表面的
    #       东西（五官贴在脸上、徽章贴在衣服上）用这个，弯曲时不会从表面滑走。
    #   写了 bend_follow_at → 整组按**关节点那一行**取样。整块挂在关节上的部件
    #       （头挂在脖子、手臂挂在肩膀）用这个，整块刚性跟着关节走。
    if seg:
        groups = {
            "root": {"pivot": [cw // 2, ch], "parent": ""},
            "chest": {"pivot": [hip_pt[0], hip_pt[1]], "parent": "root"},
            "head": {"pivot": [neck_pt[0], neck_pt[1]], "parent": "chest",
                     "bend_follow": body_id, "bend_follow_at": neck_pt[1]},
            "arm_l": {"pivot": sh_l, "parent": "chest",
                      "bend_follow": body_id, "bend_follow_at": sh_l[1]},
            "arm_r": {"pivot": sh_r, "parent": "chest",
                      "bend_follow": body_id, "bend_follow_at": sh_r[1]},
            "leg_l": {"pivot": [hip_pt[0] - int(sp_w * 0.08), hip_pt[1]], "parent": "root"},
            "leg_r": {"pivot": [hip_pt[0] + int(sp_w * 0.08), hip_pt[1]], "parent": "root"},
        }
    else:
        groups = {
            "root": {"pivot": [cw // 2, ch], "parent": ""},
            "chest": {"pivot": [cw // 2, chest_y], "parent": "root", "bend_follow": body_id},
            "head": {"pivot": [cw // 2, neck_y], "parent": "chest", "bend_follow": body_id},
        }

    rig = {
        "schema_version": "1.0",
        "id": f"{name}_teen",
        "name": name,
        "canvas": {"w": cw, "h": ch},
        "origin": [cw // 2, ch],
        "ground_line": ch - 8,
        "groups": groups,
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


    # 素材没有独立头部时，去掉所有作用在 head 组上的旋转通道（见 main 里的说明）
    if not head_is_part:
        for a in rig["actions"]:
            a["channels"] = [
                c for c in a["channels"]
                if not (c.get("target") == "head" and c.get("param") == "rot_deg")
            ]
        rig["notes"] = (rig.get("notes", "") +
                        " 头部未拆件：已省略 head 组的 rot_deg 通道，"
                        "拆出 head_base.png 后重跑 make_rig.py 自动恢复。").strip()
    return rig


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
    # 分段素材与关节点（有就用，没有就按老路子出单图层骨架）
    seg = anchors = None
    seg_path = os.path.join(base, "sprites", "body_parts.json")
    anchor_path = os.path.join(base, "design", "anchors.json")
    if os.path.exists(seg_path):
        with open(seg_path, encoding="utf-8") as f:
            seg = json.load(f)
        missing = [sp["id"] for sp in seg["parts"]
                   if not os.path.exists(os.path.join(base, sp["file"]))]
        if missing:
            print(f"警告：分段部件缺图 {missing}，退回单图层骨架", file=sys.stderr)
            seg = None
    if os.path.exists(anchor_path):
        with open(anchor_path, encoding="utf-8") as f:
            anchors = json.load(f)
    # 头是不是独立部件？决定能不能发"头部旋转"通道。
    # 单图层全身图里，头是画在身体上的：这时让 head 组转动，只会把贴在上面的
    # 五官转走（看起来像眼睛在脸上滑），所以生成器直接不发 rot_deg。
    # 等拆件产出 head_base.png（或任何带 head_base 标签的部件）后，自动恢复。
    head_is_part = any(
        n.startswith(("head_base", "head.")) for n in (p["name"] for p in parts["parts"])
    )
    if seg and any(sp["id"] == "seg_head" for sp in seg["parts"]):
        head_is_part = True          # 分段素材里头是独立一张图，可以放心转头
    rig = build(parts, sprite, args.canvas, args.name, cw, ch, head_is_part,
                seg=seg, anchors=anchors)
    out = os.path.join(base, "rig.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(rig, f, ensure_ascii=False, indent=2)
    print(f"写出 {out}：部件 {len(rig['parts'])} 动作 {len(rig['actions'])} "
          f"区域 {len(rig['regions'])} 组 {len(rig['groups'])}"
          f"{'（分段身体）' if seg else '（单图层身体）'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
