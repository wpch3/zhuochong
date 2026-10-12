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


def param_list(mouth=None, has_brows=True, head_is_part=True, jointed_arms=False):
    """角色级命名参数（名字对齐 Live2D 标准参数表）。

    每条 = 一个参数 + 它写到哪些通道；引擎按 `通道值 = 参数值 × scale` 叠在动作之上，
    所以 scale 就是"参数开到最大时这条通道动多少"（像素或度）。
    """
    out = []
    if head_is_part:
        out.append({"id": "ParamAngleZ", "label": "头 歪头", "min": -30.0, "max": 30.0,
                    "default": 0.0,
                    "binds": [{"group": "head", "param": "rot_deg", "scale": 0.5}],
                    "note": "±30 → 实际 ±15°，再大颈部接缝会露"})
    out += [
        {"id": "ParamBodyAngleX", "label": "上身 左右", "min": -10.0, "max": 10.0,
         "default": 0.0,
         "binds": [{"group": "chest", "param": "rot_deg", "scale": 0.12},
                   {"group": "chest", "param": "dx", "scale": 0.35}]},
        {"id": "ParamBodyAngleZ", "label": "上身 倾斜", "min": -10.0, "max": 10.0,
         "default": 0.0,
         "binds": [{"group": "chest", "param": "rot_deg", "scale": 0.25}]},
        {"id": "ParamBreath", "label": "呼吸", "min": 0.0, "max": 1.0, "default": 0.0,
         "binds": [{"group": "chest", "param": "sy", "scale": 0.012},
                   {"group": "chest", "param": "dy", "scale": -1.2}]},
    ]
    if mouth:
        # 张嘴：开口形状（遮罩）压高 + 上唇线淡出。scale 取 talk 动作里实测的幅度。
        out.append({"id": "ParamMouthOpenY", "label": "张嘴", "min": 0.0, "max": 1.0,
                    "default": 0.0,
                    "binds": [{"part": "mouth_mask", "param": "sy", "scale": 0.737},
                              {"part": "mouth_open", "param": "alpha", "scale": -0.55}],
                    "note": "口型同步（LipSync）接进来时写的就是这个参数"})
        out.append({"id": "ParamMouthForm", "label": "嘴形 笑/扁", "min": -1.0, "max": 1.0,
                    "default": 0.0,
                    "binds": [{"part": "mouth_open", "param": "sx", "scale": 0.08},
                              {"part": "mouth_mask", "param": "sx", "scale": 0.06}]})
    if has_brows:
        out += [
            {"id": "ParamBrowLY", "label": "左眉 上下", "min": -1.0, "max": 1.0, "default": 0.0,
             "binds": [{"part": "brow_l", "param": "dy", "scale": -3.0}]},
            {"id": "ParamBrowRY", "label": "右眉 上下", "min": -1.0, "max": 1.0, "default": 0.0,
             "binds": [{"part": "brow_r", "param": "dy", "scale": -3.0}]},
            {"id": "ParamBrowLAngle", "label": "左眉 角度", "min": -1.0, "max": 1.0, "default": 0.0,
             "binds": [{"part": "brow_l", "param": "rot_deg", "scale": 7.0}]},
            {"id": "ParamBrowRAngle", "label": "右眉 角度", "min": -1.0, "max": 1.0, "default": 0.0,
             "binds": [{"part": "brow_r", "param": "rot_deg", "scale": -7.0}]},
        ]
    if jointed_arms:
        # G4c 拆件后手臂是真关节：上臂绕肩、前臂绕肘。正值 = 往身体外侧抬。
        # 画面 y 轴朝下，所以顺时针为正 → 左臂（画面左）抬手是正、右臂是负。
        out += [
            {"id": "ParamArmLA", "label": "左臂 抬起", "min": -10.0, "max": 10.0, "default": 0.0,
             "binds": [{"group": "arm_l", "param": "rot_deg", "scale": 6.0}],
             "note": "绕肩旋转，±10 → ±60°（袖下躯干已 AI 补绘，转开不露洞）"},
            {"id": "ParamArmRA", "label": "右臂 抬起", "min": -10.0, "max": 10.0, "default": 0.0,
             "binds": [{"group": "arm_r", "param": "rot_deg", "scale": -6.0}]},
            {"id": "ParamArmLB", "label": "左小臂 弯曲", "min": -10.0, "max": 10.0, "default": 0.0,
             "binds": [{"group": "forearm_l", "param": "rot_deg", "scale": 5.0}],
             "note": "绕肘旋转，±10 → ±50°；肘部 24px 重叠带兜底"},
            {"id": "ParamArmRB", "label": "右小臂 弯曲", "min": -10.0, "max": 10.0, "default": 0.0,
             "binds": [{"group": "forearm_r", "param": "rot_deg", "scale": -5.0}]},
        ]
    else:
        out += [
        {"id": "ParamArmLA", "label": "左臂 摆动", "min": -10.0, "max": 10.0, "default": 0.0,
         "binds": [{"part": "seg_arm_l", "param": "bend_x", "scale": -4.0, "curve": "tip"}],
         "note": "手臂只有形变没有肘关节（G4c 未做），上限按 ±40px 给"},
        {"id": "ParamArmRA", "label": "右臂 摆动", "min": -10.0, "max": 10.0, "default": 0.0,
         "binds": [{"part": "seg_arm_r", "param": "bend_x", "scale": 4.0, "curve": "tip"}]},
        ]
    out += [
        {"id": "ParamHairFront", "label": "刘海 摆动", "min": -1.0, "max": 1.0, "default": 0.0,
         "binds": [{"part": "hair_front", "param": "bend_x", "scale": 6.0, "curve": "tip"}]},
        {"id": "ParamHairAhoge", "label": "呆毛 摆动", "min": -1.0, "max": 1.0, "default": 0.0,
         "binds": [{"part": "hair_ahoge", "param": "bend_x", "scale": 10.0, "curve": "root"}]},
    ]
    return out


def expression_list(mouth=None, has_brows=True, head_is_part=True):
    """表情集。每条 = 一组参数偏移（mode 缺省 add，set 为覆盖），fade 是淡入淡出秒数。

    只用 param_list 里声明过的参数（引擎加载时会校验），所以改表情不用动 C 代码。
    """
    def P(pid, value, mode=None):
        d = {"id": pid, "value": value}
        if mode:
            d["mode"] = mode
        return d

    def brows(ly, ry, la=0.0, ra=0.0):
        if not has_brows:
            return []
        out = [P("ParamBrowLY", ly), P("ParamBrowRY", ry)]
        if la or ra:
            out += [P("ParamBrowLAngle", la), P("ParamBrowRAngle", ra)]
        return out

    def mform(v):
        return [P("ParamMouthForm", v)] if mouth else []

    def mopen(v):
        return [P("ParamMouthOpenY", v)] if mouth else []

    out = [
        {"id": "smile", "name": "微笑", "fade": 0.3,
         "params": brows(0.25, 0.25) + mform(0.7) + [P("ParamEyeOpen", 0.85, "set")]},
        {"id": "shy", "name": "害羞", "fade": 0.35,
         "params": brows(-0.3, -0.3) + mform(0.35)
                   + [P("ParamEyeOpen", 0.7, "set")]
                   + ([P("ParamAngleZ", -4.0)] if head_is_part else [])},
        {"id": "angry", "name": "生气", "fade": 0.22,
         "params": brows(-0.7, -0.7, -0.8, -0.8) + mform(-0.7)
                   + [P("ParamEyeOpen", 0.9, "set")]},
        {"id": "sad", "name": "难过", "fade": 0.4,
         "params": brows(-0.45, -0.45, 0.7, 0.7) + mform(-0.5)
                   + [P("ParamEyeOpen", 0.75, "set")]},
        {"id": "surprise", "name": "吃惊", "fade": 0.12,
         "params": brows(0.9, 0.9) + mopen(0.55)
                   + [P("ParamEyeOpen", 1.0, "set"), P("ParamEyeBallY", -0.15)]},
        {"id": "sleepy", "name": "困倦", "fade": 0.5,
         "params": brows(-0.2, -0.2) + mopen(0.15)
                   + [P("ParamEyeOpen", 0.3, "set"), P("ParamEyeBallY", 0.2)]},
    ]
    return out


def build(parts, sprite, canvas, name, cw, ch, head_is_part=False,
          seg=None, anchors=None, eyes=None, mouth=None, lids=None, armp=None):
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
                  "arm_l_upper": ["arm"], "arm_l_fore": ["arm"],
                  "arm_r_upper": ["arm"], "arm_r_fore": ["arm"],
                  "seg_leg_l": ["leg"], "seg_leg_r": ["leg"],
                  "hair_ahoge": ["hair"], "hair_front": ["hair"],
                  "brow_l": ["brow"], "brow_r": ["brow"]}
        seg_src = list(seg["parts"])
        if armp:
            # G4c：整条手臂（seg_arm_l/r）作废，换成上臂 + 前臂四件真关节零件
            seg_src = [sp for sp in seg_src if sp["id"] not in ("seg_arm_l", "seg_arm_r")]
            seg_src += [dict(sp, note="手臂拆件（make_arm_parts.py：袖缝切 + 肘关节）")
                        for sp in armp["parts"]]
        body_parts_list = [{
            "id": sp["id"],
            "file": sp["file"],
            "group": sp["group"],
            "layer": sp["layer"],
            "pos": [ox + sp["pos"][0], oy + sp["pos"][1]],
            "anchor": [0, 0],
            "tags": tag_of.get(sp["id"], ["body"]),
            "note": sp.get("note", "分段部件（make_body_parts.py 切出，关节处有重叠带兜底）"),
        } for sp in seg_src]
        # 眉毛要绕自己中心转（挑眉/皱眉），所以锚点放中心、pos 换成中心点
        size_of = {sp["id"]: sp.get("size") for sp in seg["parts"]}
        for bp_ in body_parts_list:
            if bp_["id"].startswith("brow_") and size_of.get(bp_["id"]):
                bw, bh = size_of[bp_["id"]]
                bp_["anchor"] = [0.5, 0.5]
                bp_["pos"] = [bp_["pos"][0] + bw // 2, bp_["pos"][1] + bh // 2]
    else:
        body_parts_list = [body_part]
    # 眼睛：拆成 Live2D 式四件（眼眶遮罩 / 眼白底 / 眼球 / 眼线），
    # 眼球单独可动并被眼眶裁切；没有拆件产物时退回整块贴图。
    eye_parts = []
    eye_ball_ids = []
    if eyes:
        base_layer = {"l": 216, "r": 226}
        for e in eyes["eyes"]:
            side = e["side"]
            L = base_layer[side]
            px, py = e["patch_pos"]
            bx, by = e["ball_pos"]
            sid = f"eye_{side}"
            eye_parts += [
                {"id": f"{sid}_socket", "file": f"sprites/{e['socket']}", "group": "head",
                 "layer": L, "pos": [ox + px, oy + py], "anchor": [0, 0],
                 "tags": [], "mask_only": True,
                 "note": "眼眶：只当遮罩用，不出现在画面上（Live2D 的 clipping mask）"},
                {"id": f"{sid}_base", "file": f"sprites/{e['base']}", "group": "head",
                 "layer": L + 1, "pos": [ox + px, oy + py], "anchor": [0, 0],
                 "tags": [], "mask": f"{sid}_socket",
                 # 眼白也要被眼眶裁住：它比眼眶大一圈，不裁的话闭眼时眼皮盖不住那一圈，
                 # 眼睛底下会留一条蓝边（实测）。脸上本来就画着同样的眼睛，裁掉不丢东西。
                 "note": "眼白底：眼球移开也不会露洞；同样由眼眶裁切"},
                {"id": f"{sid}_ball", "file": f"sprites/{e['ball']}", "group": "head",
                 "layer": L + 2, "pos": [ox + bx, oy + by], "anchor": [0, 0],
                 "tags": ["gaze"], "mask": f"{sid}_socket",
                 "note": f"眼球：完整的圆（被眼皮挡住的部分已补全），"
                         f"可动范围 ±{e['travel'][0]}/±{e['travel'][1]}px，由眼眶裁切"},
            ]
            # 上眼睑（make_eyelid_parts.py 的产物）：藏在眼眶上面，按 blink 下滑。
            lid = next((p for p in (lids or {}).get("lids", []) if p["side"] == side), None)
            if lid:
                eye_parts.append(
                    {"id": f"{sid}_lid", "file": f"sprites/{lid['file']}", "group": "head",
                     "layer": L + 3, "pos": [ox + lid["pos"][0], oy + lid["pos"][1]],
                     "anchor": [0, 0], "tags": ["eyelid"], "mask": f"{sid}_socket",
                     "eyelid_travel": lid["travel"],
                     "note": f"上眼睑：静止时被眼眶遮罩挡住，blink=1 时下滑 {lid['travel']}px 盖满眼眶"})
            # 睫毛跟着眼皮一起往下走（Live2D 的做法：上睫毛本来就长在眼皮上）。
            #   · 之前是"淡出"：半闭时眼睛先丢掉上眼线，像眼眶被擦掉（实测 blink=0.4 的帧）；
            #   · 之后试过"不动 + 被眼皮盖住"：闭眼时睫毛留在最上面，底下一大片空白皮肤，
            #     读起来像翻白眼。
            #   · 现在是跟着下滑并挂眼眶遮罩：闭到底时它正好落在眼眶下沿 = 那条闭眼线；
            #     溢出眼眶的部分被遮罩裁掉，眼角那截由脸上的原画顶着，不会缺。
            # 行程比眼皮少几像素：眼皮要盖过下沿（OVERSHOOT），睫毛要停在下沿上。
            lash_travel = max(2, int(lid["travel"]) - 6) if lid else 0
            lash_part = {"id": f"{sid}_lash", "file": f"sprites/{e['lash']}", "group": "head",
                         "layer": L + 4, "pos": [ox + px, oy + py], "anchor": [0, 0],
                         "tags": ["eyelid"] if lid else ["eye_open"],
                         "note": "眼线睫毛：跟着眼皮下滑，闭到底时就是那条闭眼线"}
            if lid:
                lash_part["eyelid_travel"] = lash_travel
                lash_part["mask"] = f"{sid}_socket"
            eye_parts.append(lash_part)
            eye_ball_ids.append(f"{sid}_ball")
    else:
        eye_parts = [
            part("eye_open_left.png", "head", ["eye_open", "gaze"], 220),
            part("eye_open_right.png", "head", ["eye_open", "gaze"], 221),
        ]
    # 嘴：开口形状（遮罩）+ 口内。原画没有口腔，口内是 make_mouth_parts.py 画出来的；
    # 张开多少 = 压缩遮罩的 sy（锚点在上唇线，所以是往下张开）。
    mouth_parts = []
    if mouth:
        # 这两件的 anchor 是 [0.5, 0]（上唇线中点），所以 pos 要给锚点所在的位置，
        # 给左上角会整体偏半个嘴宽——第一版就是这么偏的。
        mx, my = mouth.get("anchor_pos", mouth["pos"])
        mx, my = int(round(mx)), int(round(my))
        mouth_parts = [
            {"id": "mouth_mask", "file": f"sprites/{mouth['mask']}", "group": "head",
             "layer": 205, "pos": [ox + mx, oy + my], "anchor": [0.5, 0],
             "scale": [1.0, mouth["closed_sy"]], "tags": ["mouth"], "mask_only": True,
             "note": f"开口形状：锚点在上唇线，sy={mouth['closed_sy']} 是闭嘴，"
                     f"sy≈0.85 是张到最大（{mouth['open_h']}px）"},
            {"id": "mouth_cavity", "file": f"sprites/{mouth['cavity']}", "group": "head",
             "layer": 206, "pos": [ox + mx, oy + my], "anchor": [0.5, 0],
             "tags": ["mouth"], "mask": "mouth_mask",
             "note": "口内（上颚/口腔/舌/下唇线），被开口形状裁切；自己不缩放"},
        ]
    parts_list = body_parts_list + mouth_parts + [
        part("mouth_open.png", "head", ["mouth"], 210, "上唇线（闭合笑线），压在口内上面"),
    ] + eye_parts
    # 透け眉（眉毛透过刘海）：动漫立绘的常规做法 —— 眉毛本体画在刘海底下（层 232/233），
    # 再把同一张图的半透明副本画在刘海之上（层 241/242），并用 hair_front 当遮罩，
    # 所以它**只在被刘海挡住的那块**显形。副本靠 motion_from 照抄本体的通道值，
    # 挑眉/皱眉/表情一起动，不用在每个动作里再写一遍通道。
    brow_ghosts = []
    if any(p["id"] == "brow_l" for p in body_parts_list) and \
       any(p["id"] == "hair_front" for p in body_parts_list):
        for side, lay in (("l", 241), ("r", 242)):
            srcp = next(x for x in body_parts_list if x["id"] == f"brow_{side}")
            brow_ghosts.append({
                "id": f"brow_{side}_ghost",
                "file": srcp["file"],
                "group": srcp["group"],
                "layer": lay,
                "pos": list(srcp["pos"]),
                "anchor": list(srcp["anchor"]),
                "opacity": 0.42,
                "tags": ["brow"],
                "mask": "hair_front",
                "motion_from": f"brow_{side}",
                "note": "透け眉：眉毛的半透明副本，被刘海遮罩裁切，只在刘海覆盖处显形；"
                        "通道值照抄 brow_" + side,
            })
    parts_list = parts_list + brow_ghosts
    if not eyes:
        # 没拆件的旧素材才用"整张闭眼图淡入"的老办法
        parts_list = parts_list + [
            part("eye_closed_left.png", "head", ["eye_closed"], 230, "闭眼：与睁眼交叉淡化"),
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
         "blink_hold": 0.95,
         "part_overrides": {}},
        {"id": "happy", "priority": 7, "duration": 1.6, "return_state": "idle",
         "interruptible": False,
         "channels": [
             {"target": "root", "param": "dy", "wave": "bounce", "amp": -22.0, "dur": 0.45, "ease": "out_back"},
             {"target": "root", "param": "dy", "wave": "bounce", "amp": -12.0, "dur": 0.5, "ease": "out_back"},
             {"target": "head", "param": "rot_deg", "wave": "bounce", "amp": 5.0, "dur": 0.5},
         ],
         "blink_hold": 0.78,
         "part_overrides": {"mouth_open": {"opacity": 0.85}}},
        {"id": "sad", "priority": 3, "loop": True, "interruptible": True, "return_state": "idle",
         "channels": [
             {"target": "head", "param": "dy", "wave": "pulse", "amp": 6.0, "dur": 0.5, "ease": "out"},
             {"target": "head", "param": "rot_deg", "wave": "sine", "amp": 1.0, "freq": 0.12},
         ],
         "blink_hold": 0.32,
         "part_overrides": {}},
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
         "blink_hold": 0.7,
         "part_overrides": {"mouth_open": {"opacity": 0.35}}},
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
         "blink_hold": 1.0,
         "part_overrides": {}},
    ]

    # ---- 分段素材才有的次级动作：手臂摆动、重心移动 ----
    # 幅度刻意保守：关节处只有 3% 身高的重叠带兜底，摆太大会露接缝。
    # 等画出真正的关节补图（GAPS G4）再放大。
    if seg:
        def add(action_id, chans):
            for a in actions:
                if a["id"] == action_id:
                    a["channels"].extend(chans)

        # 肩到腕 = 708-364 = 344px：手臂整块绕肩转 1° 时腕部横移 344*π/180 ≈ 6.0px。
        # 老动作的幅度都是按"腕部位移多少像素"调出来的，这里按这个系数换算成角度，
        # 观感完全一致，差别只在于现在是真关节在转、不是网格在拉。
        DEG_PER_PX = 180.0 / (3.14159265358979 * 344.0)

        def arm(side, param, amp, freq, phase=0.0, wave="sine", **kw):
            """手臂通道。

            G4c 之前：手臂是竖切下来的一整块，里面带着一条外套前襟，整块转 26°
            那条会甩到身体轮廓外（实测），所以只能用网格形变 bend（curve=tip，
            肩部钉死、越往下位移越大）。
            G4c 之后：袖下躯干已 AI 补绘、沿袖缝切成上臂+前臂两级关节，
            于是 bend 通道一律换成绕肩的真旋转 —— 和 Live2D 的手臂旋转变形器一致。"""
            if armp and param.startswith("bend"):
                # bend_x 正向 = 手往画面右边推；绕肩顺时针（正角）会把手往左带，
                # 所以换算要取负号。bend_y（上下推）没有等价旋转，退回竖向位移。
                if param == "bend_x":
                    return {"target": f"arm_{side}", "param": "rot_deg", "wave": wave,
                            "amp": round(-amp * DEG_PER_PX, 3), "freq": freq,
                            **({"phase": phase} if phase else {}), **kw}
                param, amp = "dy", amp * 0.5
            tgt = f"seg_arm_{side}" if param.startswith("bend") else f"arm_{side}"
            c = {"target": tgt, "param": param, "wave": wave, "amp": amp, "freq": freq}
            if param.startswith("bend"):
                c["curve"] = "tip"
            if phase:
                c["phase"] = phase
            c.update(kw)
            return c

        def fore(side, amp, freq=0.0, wave="sine", **kw):
            """前臂通道（绕肘）。正值 = 往身体外侧甩，左右镜像。"""
            c = {"target": f"forearm_{side}", "param": "rot_deg", "wave": wave,
                 "amp": amp if side == "l" else -amp, "freq": freq}
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

        if armp:
            # 有肘关节之后才做得出来的次级动作：小臂比上臂晚半拍（鞭梢效应）
            add("idle", [fore("l", 0.8, 0.06, phase=0.28), fore("r", 0.8, 0.06, phase=0.28)])
            add("sway", [fore("l", 2.4, 0.18, phase=0.22), fore("r", 2.4, 0.18, phase=0.22)])
            add("happy", [fore("l", 14.0, 0.0, wave="bounce", dur=0.5),
                          fore("r", 14.0, 0.0, wave="bounce", dur=0.5)])
            add("hammered", [fore("l", 9.0, 2.6, wave="decay", dur=0.7),
                             fore("r", 9.0, 2.6, wave="decay", dur=0.7)])
            # 吓一跳：两只手一起向外抬 + 小臂抬起护在身前（以前只能抖一抖）
            add("surprised", [
                {"target": "arm_l", "param": "rot_deg", "wave": "pulse",
                 "amp": 16.0, "dur": 0.9, "ease": "out"},
                {"target": "arm_r", "param": "rot_deg", "wave": "pulse",
                 "amp": -16.0, "dur": 0.9, "ease": "out"},
                fore("l", 22.0, 0.0, wave="pulse", dur=0.9, ease="out"),
                fore("r", 22.0, 0.0, wave="pulse", dur=0.9, ease="out"),
            ])

        # 挥手：单图层时代做不到的动作（没有独立手臂，一抬就整张图跟着转）。
        # 同样用 bend：肩膀钉死，手往外甩 + 往上抬，再叠一个快速左右摆。
        # 幅度上限是算出来的：手臂内侧那条重叠带 38px，它在最低一行（离身行）
        # 的形变权重是 0.59，所以 amp ≤ 38/0.59 ≈ 64 才不会把重叠带甩出兜底范围。
        # 想要更大的动作必须先补关节图（GAPS G4c）。
        wave_channels = [
            {"target": "seg_arm_r", "param": "bend_x", "wave": "pulse",
             "amp": 60.0, "curve": "tip", "dur": 2.4, "ease": "out"},
            {"target": "seg_arm_r", "param": "bend_y", "wave": "pulse",
             "amp": -45.0, "curve": "tip", "dur": 2.4, "ease": "out"},
            {"target": "seg_arm_r", "param": "bend_x", "wave": "sine",
             "amp": 14.0, "curve": "tip", "freq": 1.8, "dur": 2.4},
        ]
        if armp:
            # 真关节版挥手。**肘必须往回折，不能顺着大臂继续转**：
            # 画面 y 轴朝下 → 正角=顺时针；右臂往外抬是负角。
            # 第一版把前臂也写成 -28°，等于顺着大臂继续外展，整条手臂还是一根直筒
            # （用户："挥手的肘关节呢？"）。手要举到头侧，前臂相对大臂要再转 ~80°，
            # 大臂 -58° + 前臂 -80° = 手腕总转 138°，正好是"举手挥"的姿势。
            wave_channels = [
                {"target": "arm_r", "param": "rot_deg", "wave": "pulse",
                 "amp": -58.0, "dur": 2.4, "ease": "out"},
                {"target": "forearm_r", "param": "rot_deg", "wave": "pulse",
                 "amp": -80.0, "dur": 2.4, "ease": "out"},
                {"target": "forearm_r", "param": "rot_deg", "wave": "sine",
                 "amp": 14.0, "freq": 2.2, "dur": 2.4},
                {"target": "arm_l", "param": "rot_deg", "wave": "pulse",
                 "amp": 6.0, "dur": 2.4, "ease": "out"},
            ]
        actions.append({
            "id": "wave", "priority": 6, "duration": 2.4, "return_state": "idle",
            "interruptible": False,
            "channels": wave_channels + [
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
        if armp:
            # 前臂挂在上臂下面：枢轴 = 肘关节（anchors 实测），父组旋转自动继承
            el_l = apt("elbow_l", 0.428, 0.172)
            el_r = apt("elbow_r", 0.428, 0.825)
            groups["forearm_l"] = {"pivot": el_l, "parent": "arm_l"}
            groups["forearm_r"] = {"pivot": el_r, "parent": "arm_r"}
    else:
        groups = {
            "root": {"pivot": [cw // 2, ch], "parent": ""},
            "chest": {"pivot": [cw // 2, chest_y], "parent": "root", "bend_follow": body_id},
            "head": {"pivot": [cw // 2, neck_y], "parent": "chest", "bend_follow": body_id},
        }

    # 眼睛拆件后，老动作里写的 eye_open_left/right 要摊到四个零件上：
    # 眼眶（遮罩）必须和眼白底、眼线一起动，否则遮罩不跟手，裁切就错位了。
    if eyes:
        expand = {
            "eye_open_left":  [f"eye_l_{k}" for k in ("socket", "base", "ball", "lid", "lash")],
            "eye_open_right": [f"eye_r_{k}" for k in ("socket", "base", "ball", "lid", "lash")],
        }
        for a in actions:
            chans = []
            for c in a.get("channels", []):
                if c.get("target") in expand:
                    targets = expand[c["target"]]
                    # 缩放只给眼球！眼白底/眼眶/眼线都是**矩形小块贴图**，
                    # 一放大就会把贴图的方边露出来（surprised 里那条横着的"补丁带"就是这么来的）。
                    # 眼球被眼眶裁切，放大只会看起来像瞳孔放大，安全。
                    if c.get("param") in ("sx", "sy"):
                        targets = [t for t in targets if t.endswith("_ball")]
                    for nid in targets:
                        c2 = dict(c)
                        c2["target"] = nid
                        chans.append(c2)
                else:
                    chans.append(c)
            a["channels"] = chans
            ov = a.get("part_overrides")
            if ov:
                nov = {}
                for k, v in ov.items():
                    if k in expand:
                        for nid in expand[k]:
                            nov[nid] = v
                    else:
                        nov[k] = v
                a["part_overrides"] = nov
        # 新动作：眼球左右看（Live2D 的 ParamEyeBallX/Y 对应物）。
        # 只有眼球动，眼白与眼线不动——这正是拆件的意义。
        tl = min(e["travel"][0] for e in eyes["eyes"])
        tv = min(e["travel"][1] for e in eyes["eyes"])
        look = {"id": "look_around", "priority": 3, "duration": 4.0, "loop": False,
                "interruptible": True, "return_state": "idle", "channels": []}
        for e in eyes["eyes"]:
            bid = f"eye_{e['side']}_ball"
            look["channels"] += [
                {"target": bid, "param": "dx", "wave": "sine", "amp": float(tl), "freq": 0.45},
                {"target": bid, "param": "dy", "wave": "sine", "amp": float(tv) * 0.5,
                 "freq": 0.9, "phase": 0.25},
            ]
        look["channels"] += [
            {"target": "head", "param": "rot_deg", "wave": "sine", "amp": 1.5, "freq": 0.45},
        ]
        actions.append(look)

    # 张嘴的动作：只动遮罩的 sy，口内自己不变形（Live2D 的 ParamMouthOpenY 就是这么做的）
    if mouth:
        closed = mouth["closed_sy"]
        def open_to(v):
            """把"张到 v（0~1）"换算成通道增量：实际 sy = 基准 + 增量"""
            return round(v - closed, 3)
        by_id = {a["id"]: a for a in actions}
        if "talk" in by_id:
            by_id["talk"]["channels"].append(
                {"target": "mouth_mask", "param": "sy", "wave": "flap",
                 "amp": open_to(0.80), "freq": 3.0})
        if "happy" in by_id:
            by_id["happy"]["channels"].append(
                {"target": "mouth_mask", "param": "sy", "wave": "bounce",
                 "amp": open_to(0.55), "dur": 1.2, "ease": "out"})
        if "surprised" in by_id:
            by_id["surprised"]["channels"].append(
                {"target": "mouth_mask", "param": "sy", "wave": "pulse",
                 "amp": open_to(0.95), "dur": 0.12, "ease": "out"})
        if "hammered" in by_id:
            by_id["hammered"]["channels"].append(
                {"target": "mouth_mask", "param": "sy", "wave": "decay",
                 "amp": open_to(0.70), "dur": 0.8, "freq": 2.0})
        if "sleep" in by_id:
            by_id["sleep"]["channels"].append(
                {"target": "mouth_mask", "param": "sy", "wave": "sine",
                 "amp": open_to(0.30), "freq": 0.12})

    # 呆毛：根在底边，所以曲线用 root（底固定、梢摆动）。它是目前唯一一件
    # 能无损切下来的头发零件，先让它动起来（规格 H3）。
    if any(p["id"] == "hair_ahoge" for p in parts_list):
        ah = {
            "breath":    {"wave": "sine", "amp": 1.6, "freq": 0.3},
            "idle":      {"wave": "sine", "amp": 1.2, "freq": 0.22},
            "sway":      {"wave": "sine", "amp": 4.0, "freq": 0.35},
            "happy":     {"wave": "bounce", "amp": 7.0, "dur": 1.4, "ease": "out"},
            "surprised": {"wave": "decay", "amp": 8.0, "dur": 0.8, "freq": 2.4},
            "head_pat":  {"wave": "sine", "amp": 5.0, "freq": 1.1},
            "hammered":  {"wave": "decay", "amp": 9.0, "dur": 1.0, "freq": 3.0},
            "wave":      {"wave": "sine", "amp": 3.0, "freq": 1.2},
            "sleep":     {"wave": "sine", "amp": 1.0, "freq": 0.1},
        }
        by_id2 = {a["id"]: a for a in actions}
        for aid, spec in ah.items():       # 别用 ch 当变量名，那是画布高度
            if aid in by_id2:
                c = {"target": "hair_ahoge", "param": "bend_x", "curve": "root"}
                c.update(spec)
                by_id2[aid]["channels"].append(c)

    # 刘海：吊在头顶、发梢在下，所以曲线用 tip（顶固定、下摆动）。
    # 它底下的额头是 AI 重绘补出来的（make_bangs_parts.py），所以敢让它动；
    # 幅度压在 4px 以内，再大就会把补画区的边缘露出来。
    if any(p["id"] == "hair_front" for p in parts_list):
        fr = {
            "breath":    {"wave": "sine", "amp": 0.6, "freq": 0.26},
            "idle":      {"wave": "sine", "amp": 0.9, "freq": 0.20},
            "sway":      {"wave": "sine", "amp": 2.4, "freq": 0.33},
            "happy":     {"wave": "bounce", "amp": 3.2, "dur": 1.4, "ease": "out"},
            "surprised": {"wave": "decay", "amp": 3.8, "dur": 0.8, "freq": 2.2},
            "head_pat":  {"wave": "sine", "amp": 2.6, "freq": 1.1},
            "hammered":  {"wave": "decay", "amp": 4.0, "dur": 1.0, "freq": 2.8},
            "wave":      {"wave": "sine", "amp": 1.4, "freq": 1.2},
            "sleep":     {"wave": "sine", "amp": 0.5, "freq": 0.1},
        }
        by_id3 = {a["id"]: a for a in actions}
        for aid, spec in fr.items():
            if aid in by_id3:
                chan = {"target": "hair_front", "param": "bend_x", "curve": "tip"}
                chan.update(spec)
                by_id3[aid]["channels"].append(chan)

    # 眉毛：Live2D 的 ParamBrowLY/RY（上下）+ ParamBrowLAngle/RAngle（倾角）。
    # 眉下的皮肤是 AI 重绘补出来的（make_brow_parts.py），所以敢让它动；
    # 往上挑会自动滑进刘海底下（层序：脸 180 < 眉 181/182 < 刘海 188）。
    if any(p["id"] == "brow_l" for p in parts_list):
        brow = {
            "surprised": [("dy", {"wave": "decay", "amp": -4.5, "dur": 0.9, "freq": 2.0}, 1.0),
                          ("rot_deg", {"wave": "decay", "amp": 3.0, "dur": 0.9, "freq": 2.0}, -1.0)],
            "happy":     [("dy", {"wave": "bounce", "amp": -2.0, "dur": 1.2, "ease": "out"}, 1.0)],
            "sad":       [("dy", {"wave": "sine", "amp": 1.6, "freq": 0.25}, 1.0),
                          ("rot_deg", {"wave": "sine", "amp": 2.5, "freq": 0.25}, 1.0)],
            "think":     [("dy", {"wave": "sine", "amp": -2.4, "freq": 0.3}, 1.0),
                          ("rot_deg", {"wave": "sine", "amp": 2.0, "freq": 0.3}, -1.0)],
            "focus":     [("dy", {"wave": "sine", "amp": 0.9, "freq": 0.4}, 1.0)],
            "talk":      [("dy", {"wave": "sine", "amp": -0.8, "freq": 1.8}, 1.0)],
            "head_pat":  [("dy", {"wave": "sine", "amp": -1.4, "freq": 1.0}, 1.0)],
            "hammered":  [("dy", {"wave": "decay", "amp": 2.6, "dur": 1.0, "freq": 3.0}, 1.0)],
            "sleep":     [("dy", {"wave": "sine", "amp": 1.0, "freq": 0.1}, 1.0)],
            "idle":      [("dy", {"wave": "sine", "amp": -0.4, "freq": 0.18}, 1.0)],
        }
        by_id4 = {a["id"]: a for a in actions}
        for aid, chans in brow.items():
            if aid not in by_id4:
                continue
            for pid, sign in (("brow_l", 1.0), ("brow_r", -1.0)):
                for param, spec, asym in chans:
                    cc = {"target": pid, "param": param}
                    cc.update(spec)
                    # 只有倾角左右反号（两条眉对称地挑/皱），上下是同向的
                    if param == "rot_deg":
                        cc["amp"] = spec["amp"] * sign * asym
                    parts_ok = True
                    if parts_ok:
                        by_id4[aid]["channels"].append(cc)

    rig = {
        "schema_version": "1.0",
        "id": f"{name}_teen",
        "name": name,
        "canvas": {"w": cw, "h": ch},
        "origin": [cw // 2, ch],
        "ground_line": ch - 8,
        "groups": groups,
        "gaze": {"max_offset": [3.0, 2.0]},
        # 指针跟随：眼睛看过去的同时，头和上身也跟着转一点
        # （Live2D 的 ParamAngleX/Y + ParamBodyAngleX）。
        # 幅度刻意保守：头 5° + 4px，上身 1.2° + 1.5px —— 再大就"摇头晃脑"了。
        "look": {
            "speed": 9.0,
            "groups": {
                "head": {"rot_deg": 5.0, "dx": 4.0, "dy": 3.0},
                "chest": {"rot_deg": 1.2, "dx": 1.5, "dy": 1.0},
            },
        },
        "blink": {
            "enabled": True,
            "closing_s": 0.10, "closed_s": 0.05, "opening_s": 0.15,
            "interval_min_s": 2.0, "interval_max_s": 8.0, "interval_exponential": False,
            "note": "参数与 Live2D CubismEyeBlink 的五态机一致：等待 → 闭合 → 保持 → 睁开",
        },
        "parts": parts_list,
        "regions": regions,
        "actions": actions,
        # 物理摆动（引擎的 physics 段）：头一动，头发自己甩。
        # 输入 = 部件锚点经过 head 组完整矩阵（含旋转和父链）之后的位移，
        # 输出 = 摆尖落后/过冲的那点距离，静止时收敛回 0。
        # 这样任何动作（不管作者有没有写头发通道）都会带起头发，
        # 而且停下来之后还会自己晃两下 —— 这就是"活"的来源。
        "physics": [
            {"id": "ahoge_x", "part": "hair_ahoge", "driver": "head", "axis": "x",
             "param": "bend_x", "curve": "root",
             "ratio": 0.5, "stiffness": 42, "damping": 5.0, "max": 8,
             "note": "呆毛左右甩：根在底边，所以曲线用 root"},
            {"id": "ahoge_y", "part": "hair_ahoge", "driver": "head", "axis": "y",
             "param": "bend_y", "curve": "root",
             "ratio": 0.45, "stiffness": 55, "damping": 6.0, "max": 5,
             "note": "呆毛上下点头"},
            {"id": "bangs_x", "part": "hair_front", "driver": "head", "axis": "x",
             "param": "bend_x", "curve": "tip",
             "ratio": 0.3, "stiffness": 65, "damping": 7.5, "max": 4,
             "note": "刘海吊在额头上，发梢在下 → 曲线 tip，幅度要小"},
        ],
        # 命名参数层（对齐 Live2D 的 ParamXxx）：外部（脚本 / LLM / 口型 / 测试台滑条）
        # 只认参数名，不用知道角色内部拆了几件。内建的 ParamAngleX/Y、ParamEyeOpen、
        # ParamEyeBallX/Y 由引擎注册，这里补角色自己的那些。
        "params": param_list(mouth=mouth,
                             has_brows=any(p["id"] == "brow_l" for p in parts_list),
                             head_is_part=head_is_part,
                             jointed_arms=bool(armp)),
        # 表情层（Live2D 的 expression）：一组参数偏移，叠在当前动作之上。
        # 和动作是两条轨 —— 可以"笑着挥手"，不用为每种组合再做一个动作。
        "expressions": expression_list(mouth=mouth,
                                       has_brows=any(p["id"] == "brow_l" for p in parts_list),
                                       head_is_part=head_is_part),
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
    # 手臂拆件（tools/make_arm_parts.py 的产物：上臂/前臂四件 + 补绘过的躯干）
    armp = None
    arm_path = os.path.join(base, "sprites", "arm_parts.json")
    if seg and os.path.exists(arm_path):
        with open(arm_path, encoding="utf-8") as f:
            armp = json.load(f)
        miss = [a["id"] for a in armp["parts"]
                if not os.path.exists(os.path.join(base, a["file"]))]
        if miss:
            print(f"警告：手臂拆件缺图 {miss}，退回整条手臂 bend", file=sys.stderr)
            armp = None
    # 眼部拆件（tools/make_eye_parts.py 的产物）
    eyes = None
    eye_path = os.path.join(base, "sprites", "eye_parts.json")
    if os.path.exists(eye_path):
        with open(eye_path, encoding="utf-8") as f:
            eyes = json.load(f)
        miss = [k for e in eyes["eyes"] for k in ("socket", "base", "ball", "lash")
                if not os.path.exists(os.path.join(base, "sprites", e[k]))]
        if miss:
            print(f"警告：眼部拆件缺图 {miss}，退回整块眼睛贴图", file=sys.stderr)
            eyes = None
    # 上眼睑拆件（tools/make_eyelid_parts.py 的产物）
    lids = None
    lid_path = os.path.join(base, "sprites", "eyelid_parts.json")
    if os.path.exists(lid_path):
        with open(lid_path, encoding="utf-8") as f:
            lids = json.load(f)
        if not all(os.path.exists(os.path.join(base, "sprites", l["file"])) for l in lids["lids"]):
            print("警告：眼睑缺图，眨眼退回交叉淡化", file=sys.stderr)
            lids = None
    # 头是不是独立部件？决定能不能发"头部旋转"通道。
    # 单图层全身图里，头是画在身体上的：这时让 head 组转动，只会把贴在上面的
    # 五官转走（看起来像眼睛在脸上滑），所以生成器直接不发 rot_deg。
    # 等拆件产出 head_base.png（或任何带 head_base 标签的部件）后，自动恢复。
    head_is_part = any(
        n.startswith(("head_base", "head.")) for n in (p["name"] for p in parts["parts"])
    )
    if seg and any(sp["id"] == "seg_head" for sp in seg["parts"]):
        head_is_part = True          # 分段素材里头是独立一张图，可以放心转头
    # 嘴部零件（tools/make_mouth_parts.py 的产物）
    mouth = None
    mouth_path = os.path.join(base, "sprites", "mouth_parts.json")
    if os.path.exists(mouth_path):
        with open(mouth_path, encoding="utf-8") as f:
            mouth = json.load(f)
        if not all(os.path.exists(os.path.join(base, "sprites", mouth[k]))
                   for k in ("mask", "cavity")):
            print("警告：嘴部零件缺图，跳过口内", file=sys.stderr)
            mouth = None
    rig = build(parts, sprite, args.canvas, args.name, cw, ch, head_is_part,
                seg=seg, anchors=anchors, eyes=eyes, mouth=mouth, lids=lids, armp=armp)
    out = os.path.join(base, "rig.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(rig, f, ensure_ascii=False, indent=2)
    print(f"写出 {out}：部件 {len(rig['parts'])} 动作 {len(rig['actions'])} "
          f"区域 {len(rig['regions'])} 组 {len(rig['groups'])}"
          f"{'（分段身体）' if seg else '（单图层身体）'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
