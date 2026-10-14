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


AP_MIN = 0.06   # 眼眶开口闭到底时纵向还剩几成（引擎 aperture_min 的默认值也是它）


def png_size(path):
    """只读 PNG 头部拿宽高（make_rig 跑在系统 python3 上，没有 PIL）。"""
    with open(path, "rb") as f:
        head = f.read(24)
    if len(head) < 24 or head[:8] != b"\x89PNG\r\n\x1a\n":
        return None
    return (int.from_bytes(head[16:20], "big"), int.from_bytes(head[20:24], "big"))


def param_list(mouth=None, has_brows=True, head_is_part=True, jointed_arms=False,
               has_blend=False, has_side=False, has_legs=False,
               body_id="seg_torso", has_eyeballs=False, foot_lift=None):
    """角色级命名参数（名字对齐 Live2D 标准参数表）。

    每条 = 一个参数 + 它写到哪些通道；引擎按 `通道值 = 参数值 × scale` 叠在动作之上，
    所以 scale 就是"参数开到最大时这条通道动多少"（像素或度）。
    """
    out = []
    if head_is_part:
        out.append({"id": "ParamAngleZ", "label": "头 歪头", "min": -30.0, "max": 30.0,
                    "default": 0.0,
                    "binds": [{"group": "head", "param": "rot_deg", "scale": 0.5},
                              # 歪头时上身跟着带一点。Live2D 官方《提高动态质量的技巧》
                              # 第 1 条：「如果只转动脸部，则会看起来像一个机器人」。
                              # ParamAngleX/Y 走 look 系统本来就同时给 head 和 chest
                              # （head.rot 5.0 / chest.rot 1.2），唯独 AngleZ 是普通参数、
                              # 只绑了 head —— 20 个动作里 12 个用 AngleZ，于是歪头时
                              # 身体纹丝不动（用户 2026-10-14 反馈"光是头在动，身体没联动"）。
                              # 比例照抄 look 里已经调好的 1.2/5.0 = 0.24：0.5 × 0.24 = 0.12。
                              {"group": "chest", "param": "rot_deg", "scale": 0.12}],
                    "note": "±30 → 实际 ±15°，再大颈部接缝会露；"
                            "上身跟 0.12（= look 里 chest/head 的 0.24 比例）"})
    out += [
        # 躯干左右摆：网格弯曲是主力（腰以上越来越偏），胸组的平移/旋转是配角。
        # 满格 10 = 原 sway 动作的幅度（bend_x 10px）。
        {"id": "ParamBodyAngleX", "label": "上身 左右", "min": -10.0, "max": 10.0,
         "default": 0.0,
         "binds": [{"part": body_id, "param": "bend_x", "scale": 1.0, "curve": "root"}],
         "note": "只驱动躯干网格弯曲（满格 = 腰以上最多偏 10px）。"
                 "不再叠胸组的平移/旋转：bend 已经表达了同一件事，"
                 "再叠一层会让五官相对身体形变多走一个固定量（单测的刚性跟随会红）"},
        {"id": "ParamBodyAngleZ", "label": "上身 倾斜", "min": -10.0, "max": 10.0,
         "default": 0.0,
         "binds": [{"group": "chest", "param": "rot_deg", "scale": 0.25}]},
        # Live2D 标准表里的"身体上下"。正值=上身往前压低（整体下沉并略压扁），
        # 负值=挺起来。只动上身组，腿不跟着走。
        {"id": "ParamBodyAngleY", "label": "上身 上下", "min": -10.0, "max": 10.0,
         "default": 0.0,
         "binds": [{"part": body_id, "param": "bend_y", "scale": 0.4, "curve": "sine"},
                   {"group": "chest", "param": "dy", "scale": 0.25},
                   {"group": "chest", "param": "sy", "scale": -0.001}],
         "note": "满格 10 = 躯干纵向弯 4px + 胸组下沉 2.5px + 压扁 1%"},
        # 肩上下（耸肩）。两条手臂组一起升降，上身跟一点点，不然肩膀会从袖子里脱出。
        {"id": "ParamShoulderY", "label": "肩 上下", "min": -10.0, "max": 10.0,
         "default": 0.0,
         "binds": [{"group": "arm_l", "param": "dy", "scale": -0.8},
                   {"group": "arm_r", "param": "dy", "scale": -0.8},
                   {"group": "chest", "param": "dy", "scale": -0.15}]},
        # 全身位移（Live2D 的 ParamBaseX/Y）：根组平移，用来做"整个人往旁边挪一点"。
        {"id": "ParamBaseX", "label": "全身 左右", "min": -10.0, "max": 10.0,
         "default": 0.0,
         "binds": [{"group": "root", "param": "dx", "scale": 2.0}],
         "note": "满格 = 整个人横移 20px（被敲飞那下用到 14px）"},
        {"id": "ParamBaseY", "label": "全身 上下", "min": -10.0, "max": 10.0,
         "default": 0.0,
         "binds": [{"group": "root", "param": "dy", "scale": -4.0}],
         "note": "满格 = 跳起 40px；happy 两段弹跳叠起来是 8.5"},
        # 全身旋转。Live2D 标准表里没有这一项（整体倾斜通常靠 ParamBodyAngleZ），
        # 我们的\"被摸头 / 被拖拽\"要整个人晃，所以登记为扩展参数（见合规表第二节）。
        {"id": "ParamBaseRot", "label": "全身 倾斜", "min": -10.0, "max": 10.0,
         "default": 0.0,
         "binds": [{"group": "root", "param": "rot_deg", "scale": 0.5}]},
        # 官方 CubismBreath 就是拿 offset + peak*sin 驱动这个参数（0..1），
        # 所以 breath 动作写的是 {amp 0.5, bias 0.5}，而不是 ±1 的双向正弦。
        {"id": "ParamBreath", "label": "呼吸", "min": 0.0, "max": 1.0, "default": 0.0,
         "binds": [{"group": "chest", "param": "sy", "scale": 0.004},
                   {"group": "chest", "param": "dy", "scale": -0.8}],
         "note": "满格 = 胸腔拉伸 0.4% + 上浮 0.8px；拉伸作用在整个上身组上，"
                 "1% 就能把头顶推走 8px，所以这个系数必须小"},
    ]
    if mouth:
        # 张嘴：开口形状（遮罩）压高 + 上唇线淡出。scale 取 talk 动作里实测的幅度。
        out.append({"id": "ParamMouthOpenY", "label": "张嘴", "min": 0.0, "max": 1.0,
                    "default": 0.0,
                    # 比例要跟着素材走：参数 1.0 = 张到最大（和 surprised 同一口径），
                    # 写死 0.737 的话换一套嘴素材就对不上了（closed_sy 变了）。
                    "binds": [{"part": "mouth_mask", "param": "sy",
                               "scale": round(0.95 - mouth["closed_sy"], 3)},
                              {"part": "mouth_open", "param": "alpha", "scale": -0.9},
                              {"part": "mouth_open", "param": "sy", "scale": 0.144}],
                    "note": "口型同步（LipSync）接进来时写的就是这个参数"})
        # 嘴形：Live2D 标准口径 —— + 是咧开（笑 / い・え），- 是撅圆（怒 / う・お）。
        # 母音口型就是靠它和 ParamMouthOpenY 的组合摆出来的（见 rig 的 visemes 段），
        # 所以幅度必须够大，象征性的 ±8% 在 466px 的帧上只有半个像素，等于没做。
        out.append({"id": "ParamMouthForm", "label": "嘴形 笑/扁", "min": -1.0, "max": 1.0,
                    "default": 0.0,
                    "binds": [{"part": "mouth_open", "param": "sx", "scale": 0.22},
                              {"part": "mouth_mask", "param": "sx", "scale": 0.26},
                              # 撅圆时开口要略高一点（う/お 是小而圆，不是小而扁）
                              {"part": "mouth_mask", "param": "sy", "scale": -0.045}]})
    if has_brows:
        out += [
            # scale 定在 -5：满格 = 眉毛上下 5px = surprised 那下挑眉的幅度。
            # （定小了动作迁到参数通道后会顶到 ±1 被 clamp，挑眉就挑不起来。）
            {"id": "ParamBrowLY", "label": "左眉 上下", "min": -1.0, "max": 1.0, "default": 0.0,
             "binds": [{"part": "brow_l", "param": "dy", "scale": -5.0}]},
            {"id": "ParamBrowRY", "label": "右眉 上下", "min": -1.0, "max": 1.0, "default": 0.0,
             "binds": [{"part": "brow_r", "param": "dy", "scale": -5.0}]},
            {"id": "ParamBrowLAngle", "label": "左眉 角度", "min": -1.0, "max": 1.0, "default": 0.0,
             "binds": [{"part": "brow_l", "param": "rot_deg", "scale": 7.0}]},
            # Live2D 标准表的「左眉／右眉 変形」。官方 Cubism 手册的口径：
            # −1 = 眉をしかめるような寄せる形（皱眉／困扰），
            # +1 = 山なりに眉が上がる形（眉峰隆起／惊讶）。
            # 关键约束（官方手册 + 多篇教程一致）：**変形 不许带位置移动** ——
            # 上下归 ParamBrowLY、左右归 ParamBrowLX、角度归 ParamBrowLAngle，
            # Form 只负责"原地改形状"，所以网格两端往下、中段往上，整体重心基本不动。
            {"id": "ParamBrowLForm", "label": "左眉 变形", "min": -1.0, "max": 1.0,
             "default": 0.0,
             "binds": [{"deformer": "brow_l_form", "scale": 1.0}]},
            {"id": "ParamBrowRForm", "label": "右眉 变形", "min": -1.0, "max": 1.0,
             "default": 0.0,
             "binds": [{"deformer": "brow_r_form", "scale": 1.0}]},
            {"id": "ParamBrowLX", "label": "左眉 左右", "min": -1.0, "max": 1.0,
             "default": 0.0,
             "binds": [{"part": "brow_l", "param": "dx", "scale": 4.0}]},
            {"id": "ParamBrowRX", "label": "右眉 左右", "min": -1.0, "max": 1.0,
             "default": 0.0,
             "binds": [{"part": "brow_r", "param": "dx", "scale": 4.0}]},
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
             "binds": [{"group": "forearm_l", "param": "rot_deg", "scale": 10.0}],
             "note": "绕肘旋转，±10 → ±100°；挥手那下肘要折 80° 再叠 14° 的摆"},
            {"id": "ParamArmRB", "label": "右小臂 弯曲", "min": -10.0, "max": 10.0, "default": 0.0,
             "binds": [{"group": "forearm_r", "param": "rot_deg", "scale": -10.0}]},
            # G4c2：手是第三节（绕腕转）。Live2D 标准参数表里就叫 ParamHandL/R。
            {"id": "ParamHandL", "label": "左手腕", "min": -1.0, "max": 1.0, "default": 0.0,
             "binds": [{"group": "hand_l", "param": "rot_deg", "scale": 22.0}],
             "note": "绕腕旋转 ±22°；手往袖子里续了 14px 皮肤，转开不露腕"},
            {"id": "ParamHandR", "label": "右手腕", "min": -1.0, "max": 1.0, "default": 0.0,
             "binds": [{"group": "hand_r", "param": "rot_deg", "scale": -22.0}]},
        ]
    else:
        out += [
        {"id": "ParamArmLA", "label": "左臂 摆动", "min": -10.0, "max": 10.0, "default": 0.0,
         "binds": [{"part": "seg_arm_l", "param": "bend_x", "scale": -4.0, "curve": "tip"}],
         "note": "手臂只有形变没有肘关节（G4c 未做），上限按 ±40px 给"},
        {"id": "ParamArmRA", "label": "右臂 摆动", "min": -10.0, "max": 10.0, "default": 0.0,
         "binds": [{"part": "seg_arm_r", "param": "bend_x", "scale": 4.0, "curve": "tip"}]},
        ]
    if has_legs:
        # G4c2 裙下大腿：腿**不绕髋旋转**，用 bend（顶边=裙子里的大腿根钉死，越往下摆幅越大）。
        #   实测：绕髋转哪怕 4°，裙摆内侧也会豁出 109 像素背景（大腿内侧那条边几乎是竖的，
        #   一转就从裙摆下让出一条缝）；bend 到脚踝位移 20px 时新露底 **0 像素**。
        #   Live2D 里裙装角色的腿也是这么做的：形变器钉在裙摆下沿。
        out += [
            {"id": "ParamLegL", "label": "左腿 摆动", "min": -1.0, "max": 1.0, "default": 0.0,
             "binds": [{"part": "seg_leg_l", "param": "bend_x", "scale": 20.0, "curve": "tip"}],
             "note": "±20px（脚踝处），裙摆下沿不动"},
            {"id": "ParamLegR", "label": "右腿 摆动", "min": -1.0, "max": 1.0, "default": 0.0,
             "binds": [{"part": "seg_leg_r", "param": "bend_x", "scale": 20.0, "curve": "tip"}]},
            # ---- 下半身表现力（2026-10-14）。原先腿只有一个 bend_x，18 个动作里
            #      只有 4 个碰得到腿，角色等于"上半身在演、下半身是根柱子"。
            #      这里补三件事：膝盖、重心、踮脚。都不用拆件 —— 靠 bend 曲线选对位置：
            #        curve=sine → 两端固定、中段最大 = 膝盖
            #        curve=tip  → 顶边固定、底端最大 = 脚踝
            {"id": "ParamKneeL", "label": "左膝 屈伸", "min": -1.0, "max": 1.0, "default": 0.0,
             "binds": [{"part": "seg_leg_l", "param": "bend_y", "scale": 9.0, "curve": "sine"}],
             "note": "sine 的峰正好落在膝盖高度。+1 膝盖上提 9px（屈膝），−1 下压（绷直）"},
            {"id": "ParamKneeR", "label": "右膝 屈伸", "min": -1.0, "max": 1.0, "default": 0.0,
             "binds": [{"part": "seg_leg_r", "param": "bend_y", "scale": 9.0, "curve": "sine"}]},
            # 屈膝承重（G98，2026-10-15）：上下起伏时**脚必须钉在地上**。
            # 官方《4.添加身体动作》写死的一条就是"身体上下运动时，脚不能离开地面"。
            # 原来挥手的起伏走的是 ParamBaseY（root.dy，整个人平移），
            # 等于连脚一起浮起来，只能靠在动作上声明 airborne 让闸放行 —— 那是权宜。
            #
            # 这条参数走人真实的做法：胯往下沉 → 腿顶跟着下来 → 脚踝那一行不动。
            # 用 root 曲线（底边固定、顶端最大）：脚件是刚性跟随腿在切线处的形变的，
            # 而 root 曲线在切线（=腿件底边）处正好是 0，所以鞋底净位移是 0。
            {"id": "ParamHipDrop", "label": "胯 下沉（屈膝承重）", "min": -1.0, "max": 1.0,
             "default": 0.0,
             "binds": [{"group": "chest", "param": "dy", "scale": 2.0},
                       {"part": "seg_leg_l", "param": "bend_y", "scale": 2.0, "curve": "root"},
                       {"part": "seg_leg_r", "param": "bend_y", "scale": 2.0, "curve": "root"}],
             "note": "+1 胯下沉 2px、腿顶跟着下来 2px、脚踝 0 —— 和 ParamBaseY 的区别是"
                     "它**不动脚**。上下起伏一律用这条，别用 ParamBaseY"},
            {"id": "ParamWeightShift", "label": "重心 左右", "min": -1.0, "max": 1.0,
             "default": 0.0,
             "binds": [{"group": "root", "param": "dx", "scale": 5.0},
                       {"part": "seg_leg_l", "param": "bend_x", "scale": -4.0, "curve": "sine"},
                       {"part": "seg_leg_r", "param": "bend_x", "scale": -4.0, "curve": "sine"}],
             "note": "真人站着重心一直在左右微调。一个参数同时驱动骨盆横移与两腿中段补偿"},
            # 踮脚：身体升高，**脚底必须留在地面上**，差额由小腿伸展吸收。
            #
            # ⚠ 这里原本两条绑定是同号的（root.dy -7 加上两腿 bend_y -5），
            # 结果不是踮脚而是**整个人连脚一起浮空 12px**（实测角色最底行
            # 1359 → 1347）。用户反馈"踮脚脚部没有变化"，根子有一半在这 ——
            # 脚相对身体确实没变化，因为它跟着整个人一起飘起来了。
            #
            # 正确的数：root 上提 7px，腿的底端就要**往下推 7px 抵消**，
            # 净位移 0 = 脚底钉在地上。tip 曲线 f(t)=t² 的权重分布正好合适：
            #   t=0   髋   -7 + 0    = -7    （跟着身体升）
            #   t=0.76 踝  -7 + 4.04 = -2.96 （升 3px）
            #   t=1.0 鞋底 -7 + 7    =  0    （钉住）
            # 鞋子那一段（t 0.76~1.0）因此被纵向压缩约 3px —— 这个前缩
            # 正是正面视角下"脚跟抬起"的读感，不需要额外拆件。
            # ⚠ 2026-10-14 第二次改口径（T24.5）：有了踮脚鞋真素材之后，
            #   "腿底端下推抵消"这条**作废**。原因见下面 else 分支的注释。
            (
                {"id": "ParamTiptoe", "label": "踮脚", "min": 0.0, "max": 1.0, "default": 0.0,
                 "binds": [{"group": "root", "param": "dy", "scale": -float(foot_lift)},
                           {"group": "foot_l", "param": "dy", "scale": float(foot_lift)},
                           {"group": "foot_r", "param": "dy", "scale": float(foot_lift)}],
                 "note": "整体上提 %.0fpx；两只脚的组同量下压抵消 = 鞋底钉在地面。"
                         "鞋本身换成踮脚姿态图（seg_foot_*_tip，鞋身纵向拉长 %.0fpx、"
                         "鞋底带压扁），鞋口因此正好抬到抬高后的脚踝上 —— "
                         "腿不再需要拉伸" % (foot_lift, foot_lift)}
                if foot_lift else
                # 没有踮脚鞋素材时的老做法：身体上提、腿的底端往下推同样多抵消。
                # 脚底是钉住了，但鞋只是被压扁 3px，用户实测反馈"踮脚脚部没有变化"。
                # 两条绑定必须**异号等量**（曾经同号 → 整个人连脚浮空 12px）。
                {"id": "ParamTiptoe", "label": "踮脚", "min": 0.0, "max": 1.0, "default": 0.0,
                 "binds": [{"group": "root", "param": "dy", "scale": -7.0},
                           {"part": "seg_leg_l", "param": "bend_y", "scale": 7.0, "curve": "tip"},
                           {"part": "seg_leg_r", "param": "bend_y", "scale": 7.0, "curve": "tip"}],
                 "note": "整体上提 7px + 腿底端下推 7px 抵消 = 脚底钉在地面；"
                         "鞋段被压缩约 3px（没有踮脚鞋素材时的退路）"}
            ),
        ]
    out += [
        {"id": "ParamHairFront", "label": "刘海 摆动", "min": -1.0, "max": 1.0, "default": 0.0,
         "binds": [{"part": "hair_front", "param": "bend_x", "scale": 6.0, "curve": "tip"}]},
        {"id": "ParamHairAhoge", "label": "呆毛 摆动", "min": -1.0, "max": 1.0, "default": 0.0,
         "binds": [{"part": "hair_ahoge", "param": "bend_x", "scale": 10.0, "curve": "root"}]},
        # A5：同一根呆毛的 S 形甩动，靠网格形变器（不是整体平移/倾斜）
        {"id": "ParamHairAhogeS", "label": "呆毛 S 形甩动", "min": -1.0, "max": 1.0,
         "default": 0.0, "binds": [{"deformer": "ahoge_s", "scale": 1.0}]},
        # Live2D 标准表里的 ParamHairFluffy（ふわふわ）：一根滑条让整头头发轻轻飘，
        # 幅度刻意比单件参数小一截 —— 它是"底噪"，不是动作。
        {"id": "ParamHairFluffy", "label": "头发 蓬松飘动", "min": -1.0, "max": 1.0,
         "default": 0.0,
         "binds": [{"part": "hair_front", "param": "bend_x", "scale": 2.0, "curve": "tip"},
                   {"part": "hair_ahoge", "param": "bend_x", "scale": 4.0, "curve": "root"}]},
    ]
    if has_side:
        # 侧发/后发（Live2D 的 ParamHairSide / ParamHairBack）。
        # ⚠ 曲线语义（zimg_bend_factor）：tip = **顶边固定、底端最大**（t²），
        #   root = 底边固定、顶端最大（u²）。
        #   侧发吊在太阳穴上、发梢在下 → tip；
        #   后发同样是从头顶长下来的，**头顶那条边就是脑袋的剪影，绝对不能动** → 也用 tip。
        #   第一版把后发写成 root，实测摆动集中在头顶（帧 y63~88），整个头形在晃。
        out += [
            {"id": "ParamHairSide", "label": "侧发 摆动", "min": -1.0, "max": 1.0,
             "default": 0.0,
             "binds": [{"part": "hair_side_l", "param": "bend_x", "scale": 7.0,
                        "curve": "tip"},
                       {"part": "hair_side_r", "param": "bend_x", "scale": 7.0,
                        "curve": "tip"}]},
            {"id": "ParamHairSideS", "label": "侧发 S 形甩动", "min": -1.0, "max": 1.0,
             "default": 0.0,
             "binds": [{"deformer": "side_l_s", "scale": 1.0},
                       {"deformer": "side_r_s", "scale": 1.0}]},
            {"id": "ParamHairBack", "label": "后发 摆动", "min": -1.0, "max": 1.0,
             "default": 0.0,
             "binds": [{"part": "hair_back", "param": "bend_x", "scale": 5.0,
                        "curve": "tip"}]},
        ]
    if has_blend:
        # A7 混合模式：腮红走乘算、眼高光走加算（见 make_blend_parts.py）
        out += [
            {"id": "ParamCheek", "label": "脸红 浓淡", "min": 0.0, "max": 1.0, "default": 0.0,
             # 零件基础 opacity 是 1，alpha 通道用 offset −1 先把它压到全透明，
             # 于是「最终透明度 = 参数值」。参数 0 = 完全看不见。
             "binds": [{"part": "blush_l", "param": "alpha", "scale": 1.0, "offset": -1.0},
                       {"part": "blush_r", "param": "alpha", "scale": 1.0, "offset": -1.0}]},
            {"id": "ParamEyeSparkle", "label": "眼高光 强弱", "min": 0.0, "max": 1.0,
             "default": 0.55,
             "binds": [{"part": "eye_hl_l", "param": "alpha", "scale": 1.0, "offset": -1.0},
                       {"part": "eye_hl_r", "param": "alpha", "scale": 1.0, "offset": -1.0},
                       {"part": "eye_hl_star_l", "param": "alpha", "scale": 1.0, "offset": -1.0},
                       {"part": "eye_hl_star_r", "param": "alpha", "scale": 1.0, "offset": -1.0}]},
        ]
    if has_eyeballs:
        # 标准参数表的"瞳孔形状"。贴图模型做不出真正的变形，就用瞳孔缩放代替：
        # +1 = 瞳孔睁圆放大（吓一跳），-1 = 缩成一点（惊恐/呆滞）。
        # 只缩放眼球件 —— 眼白底/眼眶/眼线都是矩形小块贴图，一放大就露方边。
        out.append({"id": "ParamEyeBallForm", "label": "瞳孔 放大/缩小",
                    "min": -1.0, "max": 1.0, "default": 0.0,
                    "binds": [{"part": "eye_l_ball", "param": "sx", "scale": 0.18},
                              {"part": "eye_r_ball", "param": "sx", "scale": 0.18},
                              {"part": "eye_l_ball", "param": "sy", "scale": 0.22},
                              {"part": "eye_r_ball", "param": "sy", "scale": 0.22}],
                    "note": "surprised 动作把它推到 1.0"})
    return out


def viseme_list(mouth=None):
    """口型音素表：音素 → 标准参数取值。

    依据（2026-10-13 查证）：
      - Live2D 官方标准参数表只有 ParamMouthOpenY(0..1) 与 ParamMouthForm(-1..1)，
        且 ParamMouthForm 是「+ 笑 / - 怒」的嘴形，不是母音参数本身；
      - 母音要靠两者组合，业界（Animaze 的 viseme→Live2D 映射表）也是这么做的。
    数值按我们自己的素材标定过：い 不张嘴但最宽，う 小而圆，お 大而圆。
    """
    if not mouth:
        return []
    def v(vid, open_y, form, note):
        return {"id": vid, "note": note,
                "params": {"ParamMouthOpenY": open_y, "ParamMouthForm": form}}
    return [
        v("SIL", 0.00,  0.00, "静默：闭嘴"),
        v("A",   1.00,  0.00, "あ：张到最大，嘴形中性"),
        v("I",   0.22,  1.00, "い：几乎不张，横向咧到最宽"),
        v("U",   0.30, -1.00, "う：小口撅圆"),
        v("E",   0.58,  0.55, "え：半开偏宽"),
        v("O",   0.88, -0.70, "お：大口撅圆"),
        v("N",   0.06, -0.35, "ん / m・n 闭音：基本闭上，嘴角收住"),
    ]


def expression_list(mouth=None, has_brows=True, head_is_part=True, has_blend=False,
                    has_smile_eyes=False):
    """表情集。每条 = 一组参数偏移（mode 缺省 add，set 为覆盖），fade 是淡入淡出秒数。

    只用 param_list 里声明过的参数（引擎加载时会校验），所以改表情不用动 C 代码。
    """
    def P(pid, value, mode=None):
        d = {"id": pid, "value": value}
        if mode:
            d["mode"] = mode
        return d

    def brows(ly, ry, la=0.0, ra=0.0, lf=0.0, rf=0.0):
        if not has_brows:
            return []
        out = [P("ParamBrowLY", ly), P("ParamBrowRY", ry)]
        if la or ra:
            out += [P("ParamBrowLAngle", la), P("ParamBrowRAngle", ra)]
        # 変形（眉形）：Haru 的 exp3 里六个表情都在用，和上下/角度叠着给层次
        if lf or rf:
            out += [P("ParamBrowLForm", lf), P("ParamBrowRForm", rf)]
        return out

    def mform(v):
        return [P("ParamMouthForm", v)] if mouth else []

    def mopen(v):
        return [P("ParamMouthOpenY", v)] if mouth else []

    def blush(v):
        """脸红（乘算腮红）。没有腮红零件时自动留空。"""
        return [P("ParamCheek", v, "set")] if has_blend else []

    def sparkle(v):
        """眼高光（加算）。情绪低落时眼里的光会变弱——这是最省力的\"演技\"。"""
        return [P("ParamEyeSparkle", v, "set")] if has_blend else []

    out = [
        {"id": "smile", "name": "微笑", "fade": 0.3,
         "params": brows(0.25, 0.25, lf=0.3, rf=0.3) + mform(0.7) + [P("ParamEyeOpen", 0.85, "set")]
                   + blush(0.22) + sparkle(0.75)},
        {"id": "shy", "name": "害羞", "fade": 0.35,
         "params": brows(-0.3, -0.3, lf=-0.3, rf=-0.3) + mform(0.35)
                   + [P("ParamEyeOpen", 0.7, "set")]
                   + blush(0.95) + sparkle(0.8)
                   + ([P("ParamAngleZ", -4.0)] if head_is_part else [])},
        {"id": "angry", "name": "生气", "fade": 0.22,
         "params": brows(-0.7, -0.7, -0.8, -0.8, lf=-1.0, rf=-1.0) + mform(-0.7)
                   + [P("ParamEyeOpen", 0.9, "set")] + blush(0.45) + sparkle(0.3)},
        {"id": "sad", "name": "难过", "fade": 0.4,
         "params": brows(-0.45, -0.45, 0.7, 0.7, lf=-0.55, rf=-0.55) + mform(-0.5)
                   + [P("ParamEyeOpen", 0.75, "set")] + blush(0.0) + sparkle(0.18)},
        {"id": "surprise", "name": "吃惊", "fade": 0.12,
         "params": brows(0.9, 0.9, lf=1.0, rf=1.0) + mopen(0.55)
                   + [P("ParamEyeOpen", 1.0, "set"), P("ParamEyeBallY", -0.15)]
                   + sparkle(1.0)},
        {"id": "sleepy", "name": "困倦", "fade": 0.5,
         "params": brows(-0.2, -0.2) + mopen(0.15)
                   + [P("ParamEyeOpen", 0.3, "set"), P("ParamEyeBallY", 0.2)]
                   + blush(0.0) + sparkle(0.12)},
    ]
    # 开心（眯眼笑）：照官方 Haru 的 F05 表情 —— ParamEyeLOpen=0(Multiply) + ParamEyeLSmile=1(Add)
    # + 眉毛抬 0.32。笑眼本身就是"闭着的眼"，所以这里不再写 ParamEyeOpen
    # （引擎里 blink = max(blink, smile) 已经隐含了闭眼）。
    if has_smile_eyes:
        out.append(
            {"id": "happy", "name": "开心（笑眼）", "fade": 0.28,
             "params": brows(0.32, 0.32, lf=0.4, rf=0.4) + mform(1.0)
                       + [P("ParamEyeLSmile", 1.0, "set"), P("ParamEyeRSmile", 1.0, "set")]
                       + blush(0.38) + sparkle(1.0),
             "note": "笑眼 = 山型闭眼（Live2D 标准做法），参考官方 Haru 的 F05"})
    return out


def build(parts, sprite, canvas, name, cw, ch, head_is_part=False,
          seg=None, anchors=None, eyes=None, mouth=None, lids=None, armp=None,
          closed=None, blendp=None, eyeline=None, smile_eyes=None, footp=None):
    sp_w, sp_h = sprite["sprite_size"]
    ox = (cw - sp_w) // 2
    oy = ch - sp_h
    by_name = {p["name"]: p for p in parts["parts"]}
    # 分段素材（tools/make_body_parts.py 的产物）在场时，身体不再是一张整图，
    # 形变通道要打到躯干那一段上。
    body_id = "seg_torso" if seg else "body_full"

    def part(img_name, group, tags, layer, order_note="", anchor=(0, 0)):
        # anchor 不是左上角时 pos 要跟着挪：pos 给的是“锚点落在画布哪里”，
        # 只改 anchor 不改 pos 会整体偏掉半个零件（第一版嘴就是这么偏的）。
        p = by_name[img_name]
        w, h = p["size"]
        return {
            "id": img_name.replace(".png", ""),
            "file": f"sprites/{img_name}",
            "group": group,
            "layer": layer,
            "pos": [round(ox + p["pos"][0] + w * anchor[0], 2),
                    round(oy + p["pos"][1] + h * anchor[1], 2)],
            "anchor": [anchor[0], anchor[1]],
            "tags": tags,
            "note": order_note,
        }

    # 区域（画布坐标）：底稿来自 sprites_report.json 的建议区域，但那份是**按比例估**的
    # （头 = 角色高的 24%，还假设头顶贴着 y=0），和真实几何对不上。
    # 2026-10-14 实测：head 区域只到画布 y=310，而 seg_head 实际占 y 68..385 ——
    # 下半张脸（嘴、下巴）点下去触发的是 body 的 stroke「摸身体」而不是 head_pat「摸头」。
    # 摸头是桌宠最核心的交互，这里改成按 seg_head 的真实 bbox 校正上下界。
    reg = sprite["suggested_regions"]
    head_rect = list(reg["head"])
    body_rect = list(reg["body"])
    seg_head_def = next((sp for sp in (seg or {}).get("parts", [])
                         if sp["id"] == "seg_head"), None)
    if seg_head_def and seg_head_def.get("size"):
        # seg_parts.json 的 pos 是切图内坐标，+oy 才是画布坐标（和上面 body_parts_list 同一套换算）
        head_top = oy + seg_head_def["pos"][1]
        head_bot = head_top + seg_head_def["size"][1]
        # 下巴往下留 6px 余量再交给 body；head 的 x 保持建议值（要罩住比脸更宽的头发）
        chin = int(round(head_bot)) + 6
        head_rect[1] = min(head_rect[1], int(round(head_top)))
        head_rect[3] = chin - head_rect[1]
        body_rect[3] = body_rect[1] + body_rect[3] - chin      # 先用旧底边算出高
        body_rect[1] = chin
    regions = [
        {"id": "head", "rect": head_rect, "action": "head_pat", "cursor": "hand"},
        {"id": "body", "rect": body_rect, "action": "stroke", "cursor": "hand"},
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
                  "hair_side_l": ["hair"], "hair_side_r": ["hair"],
                  "hair_back": ["hair"],
                  "brow_l": ["brow"], "brow_r": ["brow"]}
        seg_src = list(seg["parts"])
        if armp:
            # G4c：整条手臂（seg_arm_l/r）作废，换成上臂 + 前臂四件真关节零件
            seg_src = [sp for sp in seg_src if sp["id"] not in ("seg_arm_l", "seg_arm_r")]
            seg_src += [dict(sp, note="手臂拆件（make_arm_parts.py：袖缝切 + 肘关节）")
                        for sp in armp["parts"]]
        if footp:
            # T24.5：鞋从腿件上拆下来，常态/踮脚两张姿态图各一件（交叉淡化切换）
            seg_src += list(footp["parts"])
            tag_of.update({"seg_foot_l": ["leg", "foot"], "seg_foot_r": ["leg", "foot"],
                           "seg_foot_l_tip": ["leg", "foot"],
                           "seg_foot_r_tip": ["leg", "foot"]})
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
        # 躯干的形变平台：颈线以上不再继续加大形变。
        #
        # 躯干贴图的顶边（y=308）其实是**脖子和衣领**，而 bend_x 用的 root 曲线
        # 恰好把最大形变给了顶边（f(t)=(1-t)^2，t=0 时满额）。头则是按颈关节
        # 那一行（bend_follow_at=346）做刚性平移、只拿到 0.854 倍。
        # 于是衣领比它上面的头、下面的胸都移动得多，自己"鼓"出来一块 ——
        # 用户 2026-10-14 实测反馈"颈部会横向整体错误细微的位移，包括兜帽"。
        # 逐行位移剖面实测：头部恒定 -4.74px，躯干顶边 -5.08px，跳变 0.40px。
        #
        # 写上颈线之后，颈线以上的行共用颈线处的形变量，和头完全同步，滑移归零。
        for bp_ in body_parts_list:
            if bp_["id"] == body_id:
                bp_["bend_hold_above"] = neck_pt[1] if seg else neck_y
                bp_["note"] = (bp_.get("note", "") +
                               f"；颈线 y={bp_['bend_hold_above']} 以上形变不再加大"
                               "（衣领跟着头走，不然脖子会横向滑移）")
        # 下平台（G97，2026-10-15 引擎补上）：和上面那条互为镜像 ——
        # 跟随件挂在**下面**时（脚跟着腿、手跟着前臂），取样线以下的源贴图
        # 会被 tip 曲线越掰越远，而跟随件自己是刚性平移的，交界处就裂开。
        #
        # 现在的腿件走的是另一条路：make_foot_parts.py 把踝线以下整个裁掉，
        # 没有贴图就没有冲突。两条路**二选一**（selfcheck 里有闸拦重复按压），
        # 这里只把口子留出来：切件表里写 `hold_below`，就会落到 rig.json 上。
        hold_below = {sp["id"]: sp.get("hold_below") for sp in seg_src
                      if sp.get("hold_below")}
        for bp_ in body_parts_list:
            hb = hold_below.get(bp_["id"])
            if hb:
                bp_["bend_hold_below"] = hb
                bp_["note"] = (bp_.get("note", "") +
                               f"；{hb} 以下形变不再加大（跟随件在下面，交给它自己画）")
        # 眉毛要绕自己中心转（挑眉/皱眉），所以锚点放中心、pos 换成中心点
        size_of = {sp["id"]: sp.get("size") for sp in seg["parts"]}
        for bp_ in body_parts_list:
            if bp_["id"].startswith("brow_") and size_of.get(bp_["id"]):
                bw, bh = size_of[bp_["id"]]
                bp_["anchor"] = [0.5, 0.5]
                bp_["pos"] = [bp_["pos"][0] + bw // 2, bp_["pos"][1] + bh // 2]
        # G4c2 手：锚点挪到腕关节上（anchor 是**比例**，zimg_make_matrix 把锚点放到 pos 上）。
        # 这样部件级 rot_deg（物理摆用的就是部件级）也绕手腕转，而不是绕图片左上角
        # —— 绕左上角转的话手会被甩到小腹上。
        if armp:
            src_of = {sp["id"]: sp for sp in armp["parts"]}
            for bp_ in body_parts_list:
                q = src_of.get(bp_["id"])
                if not q or not bp_["id"].startswith("hand_"):
                    continue
                hw, hh = q["size"]
                ax = (float(q["pivot"][0]) - q["pos"][0]) / max(1, hw)
                ay = (float(q["pivot"][1]) - q["pos"][1]) / max(1, hh)
                bp_["anchor"] = [round(ax, 4), round(ay, 4)]
                bp_["pos"] = [ox + int(round(q["pivot"][0])), oy + int(round(q["pivot"][1]))]
    else:
        body_parts_list = [body_part]
    # 眼睛：拆成 Live2D 式四件（眼眶遮罩 / 眼白底 / 眼球 / 眼线），
    # 眼球单独可动并被眼眶裁切；没有拆件产物时退回整块贴图。
    eye_parts = []
    eye_ball_ids = []
    if eyes:
        base_layer = {"l": 216, "r": 226}
        # 笑眼件要压在同侧所有眼部件之上（含星形高光 222/234），所以单独给层号
        smile_layer = {"l": 223, "r": 235}
        smiles = {e["side"]: e for e in (smile_eyes or {}).get("eyes", [])}
        for e in eyes["eyes"]:
            side = e["side"]
            L = base_layer[side]
            px, py = e["patch_pos"]
            bx, by = e["ball_pos"]
            sid = f"eye_{side}"
            # 眼线已挖掉（脸上不再画着睁眼）时，眼眶就能当"开口"用：
            # 按 blink 纵向压扁，被它裁切的眼白/眼球/高光跟着被切掉 = 眼睛真的合上。
            el = next((x for x in (eyeline or {}).get("eyes", []) if x["side"] == side), None)
            sock = {"id": f"{sid}_socket", "file": f"sprites/{e['socket']}", "group": "head",
                    "layer": L, "pos": [ox + px, oy + py], "anchor": [0, 0],
                    "tags": [], "mask_only": True,
                    "note": "眼眶：只当遮罩用，不出现在画面上（Live2D 的 clipping mask）"}
            ap_h = 0
            if el:
                aw, ah = el.get("socket_size", [0, 0])
                ax0, ay0, ax1, ay1 = el["aperture_box"]
                ap_h = ay1 - ay0
                if aw and ah:
                    # ⚠ zimg_make_matrix 是把 anchor 这个像素点放到 pos 上，
                    #    所以改锚点必须同步把 pos 挪到那个点的身体坐标，否则整只眼会跳位。
                    acx, acy = (ax0 + ax1) * 0.5, float(ay1)
                    sock["anchor"] = [round(acx / aw, 5), round(acy / ah, 5)]
                    sock["pos"] = [ox + px + acx, oy + py + acy]
                    sock["tags"] = ["eye_aperture"]
                    sock["aperture_min"] = AP_MIN
                    sock["note"] = (f"眼眶开口（{ax1-ax0}×{ap_h}px）：当遮罩用，"
                                    f"锚点在开口下沿，blink=1 时压到 6% = 上眼皮合下来")
            eye_parts += [
                sock,
                {"id": f"{sid}_base", "file": f"sprites/{e['base']}", "group": "head",
                 "layer": L + 1, "pos": [ox + px, oy + py], "anchor": [0, 0],
                 "tags": ["eye_open"] if closed else [], "mask": f"{sid}_socket",
                 # 眼白也要被眼眶裁住：它比眼眶大一圈，不裁的话闭眼时眼皮盖不住那一圈，
                 # 眼睛底下会留一条蓝边（实测）。脸上本来就画着同样的眼睛，裁掉不丢东西。
                 "note": "眼白底：眼球移开也不会露洞；同样由眼眶裁切"},
                {"id": f"{sid}_ball", "file": f"sprites/{e['ball']}", "group": "head",
                 "layer": L + 2, "pos": [ox + bx, oy + by], "anchor": [0, 0],
                 "tags": ["gaze", "eye_open"] if closed else ["gaze"], "mask": f"{sid}_socket",
                 "note": f"眼球：完整的圆（被眼皮挡住的部分已补全），"
                         f"可动范围 ±{e['travel'][0]}/±{e['travel'][1]}px，由眼眶裁切"},
            ]
            # 上眼睑：
            #   · 有 AI 重绘的「闭眼脸」时（eye_closed_parts.json）→ 走交叉淡化，
            #     不再需要几何眼皮（那东西闭到底就是一块比脸亮的肤色饼）；
            #   · 没有时退回老方案：从眼睛上方切一块皮肤往下滑。
            cl = next((c for c in (closed or {}).get("eyes", []) if c["side"] == side), None)
            lid = None if cl else next(
                (p for p in (lids or {}).get("lids", []) if p["side"] == side), None)
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
            if el and ap_h:
                # 眼线挖干净以后，上眼线必须跟着眼皮下滑（脸上没有备份了）。
                # 不挂眼眶遮罩：遮罩自己在压扁，挂上去会把下滑的眼线一起吃掉。
                # 行程由切件工具逐列实测（眼眶下沿 − 眼线下沿 的中位数）写在 json 里：
                # 拿"开口高"当行程会滑过头 —— 眼线那条弧画在上眼皮边上，不在开口最顶端，
                # 实测会变成"眼白露在眼线上方"（_eye_states 0.25 那格）。
                lash_part["tags"] = ["eyelid"]
                if el.get("lash_file"):
                    lash_part["file"] = f"sprites/{el['lash_file']}"
                lash_part["eyelid_travel"] = el.get("lash_travel") or round(ap_h * (1.0 - AP_MIN), 1)
                lash_part.pop("mask", None)
                lash_part["note"] = ("上眼线：脸上的眼线已挖除，这条线随 blink 下滑 "
                                     f"{lash_part['eyelid_travel']}px，闭到底 = 那条闭眼线")
            eye_parts.append(lash_part)
            # 闭眼真素材：AI 重绘的闭眼脸切下来的补片，blink=1 时完全盖住原画的眼睛。
            # 引擎里 tags:["eye_closed"] 就是 opacity *= blink（与 eye_open 交叉淡化），
            # 等价于 Live2D 的 ParamEyeLOpen 在贴图版里的做法。
            if cl:
                eye_parts.append(
                    {"id": f"{sid}_closed", "file": f"sprites/{cl['file']}", "group": "head",
                     "layer": L + 5, "pos": [ox + cl["pos"][0], oy + cl["pos"][1]],
                     "anchor": [0, 0], "tags": ["eye_closed"],
                     "note": f"闭眼（AI 重绘·盖住原画眼睛 {cl['checks']['cover_ratio']*100:.1f}%，"
                             f"接缝色差 {cl['checks']['seam_mean_abs']}）：blink=1 时完全显形"})
            # 笑眼真素材：同一条流水线、同一个位置，只是底图换成"山型笑眼"的重绘脸。
            # Live2D 的标准做法就是"笑眼 = 闭眼的另一种形状"（官方 Haru 的 F05：
            # ParamEyeLOpen=0 Multiply + ParamEyeLSmile=1 Add），所以它压在闭眼件之上，
            # 由 tags:["eye_smile"] 按 ParamEyeL/RSmile 淡入、同时把谷型闭眼件让掉。
            sm = smiles.get(side)
            if sm:
                eye_parts.append(
                    {"id": f"{sid}_smile", "file": f"sprites/{sm['file']}", "group": "head",
                     "layer": smile_layer[side],
                     "pos": [ox + sm["pos"][0], oy + sm["pos"][1]],
                     "anchor": [0, 0], "tags": ["eye_smile"],
                     "note": f"笑眼（AI 重绘·盖住原画眼睛 {sm['checks']['cover_ratio']*100:.1f}%，"
                             f"接缝色差 {sm['checks']['seam_mean_abs']}）：ParamEyeL/RSmile=1 时显形"})
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
                     f"sy≈0.95 是张到最大（{mouth['open_h']}px）"},
            {"id": "mouth_cavity", "file": f"sprites/{mouth['cavity']}", "group": "head",
             "layer": 206, "pos": [ox + mx, oy + my], "anchor": [0.5, 0],
             "scale": [1.0, mouth["closed_sy"]], "tags": ["mouth"], "mask": "mouth_mask",
             "motion_from": "mouth_mask",
             "note": "口内（牙/上颚/舌/嘴角，AI 重绘的真素材）。motion_from=mouth_mask："
                     "口内跟着开口形状一起压扁，所以半开时是一张压扁的嘴，"
                     "而不是把整张口内图裁掉下半截（那样半开只剩一条黑缝）"},
        ]
    parts_list = body_parts_list + mouth_parts + [
        part("mouth_open.png", "head", ["mouth"], 210,
             "上唇线（闭合笑线），压在口内上面。锚点在上唇线中点，"
             "所以 ParamMouthForm 改宽度时是两边一起张/收，不是整条线平移",
             anchor=(0.5, 0.0)),
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
    # A7 混合模式零件（tools/make_blend_parts.py 画的，不是从立绘上抠的）：
    #   腮红 = 乘算（multiply）：只压暗底下的皮肤，不会糊一层不透明的粉膜；
    #   眼高光 = 加算（add）：只在已有画面上提亮，透明背景上不会凭空多个白点。
    # 位置用的是画布坐标（blend_parts.json 里直接写死），所以不再加 ox/oy。
    if blendp:
        for side, lay in (("l", 203), ("r", 204)):
            b = blendp["blush"][side]
            parts_list.append({
                "id": f"blush_{side}", "file": b["file"], "group": "head", "layer": lay,
                "pos": list(b["pos"]), "anchor": [0, 0], "opacity": 1.0,
                "blend": "multiply", "tags": [],
                "note": "腮红（乘算）：默认全透明，由 ParamCheek / 害羞表情推上来",
            })
        # 层号挑在眼球（218/228）之上、睫毛（220/230）之下：
        # 睫毛本来就该压住高光，眉毛在 232/233，别撞。
        # 层号只要唯一就行：A9 之后遮罩是渲染时当场画的，
        # 不再要求"遮罩和被裁件在图层里挨着"（这条限制以前逼着我们挪层号）。
        for side, lay, starlay in (("l", 219, 222), ("r", 229, 234)):
            st = blendp.get("star", {}).get(side)
            if st:
                parts_list.append({
                    "id": f"eye_hl_star_{side}", "file": st["file"], "group": "head",
                    "layer": starlay,
                    "pos": list(st["pos"]), "anchor": [0, 0], "opacity": 1.0,
                    "blend": "add", "tags": ["gaze", "eye_open"],
                    "mask": f"eye_{side}_socket",
                    "note": "星形高光（加算）：Pose 组 eye_hl_style 的另一个档位",
                })
            hl = blendp["highlight"][side]
            parts_list.append({
                "id": f"eye_hl_{side}", "file": hl["file"], "group": "head", "layer": lay,
                "pos": list(hl["pos"]), "anchor": [0, 0], "opacity": 1.0,
                "blend": "add", "tags": ["gaze", "eye_open"],
                "mask": f"eye_{side}_socket",
                "note": "眼高光（加算）：跟着眼球走、被眼眶裁切、闭眼时随睁眼件一起淡出",
            })
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
        # 关键帧曲线动作（≈ Live2D 的 .motion3）：这条不是波形，而是逐帧给值。
        # 波形做不出"快速下点 → 停顿 → 慢慢抬回"这种不对称节奏。
        {"id": "nod", "priority": 6, "duration": 1.1, "return_state": "idle",
         "interruptible": False, "fade": 0.12,
         "channels": [
             {"target": "head", "param": "rot_deg", "interp": "smooth",
              "keys": [[0.0, 0.0], [0.18, 9.0], [0.42, 9.5], [0.75, -2.5], [1.1, 0.0]],
              "note": "低头 9°，停一下，抬起时过冲 -2.5° 再回正"},
             {"target": "head", "param": "dy", "interp": "smooth",
              "keys": [[0.0, 0.0], [0.18, 4.0], [0.42, 4.0], [0.8, -1.0], [1.1, 0.0]]},
             {"target": "chest", "param": "dy", "interp": "linear",
              "keys": [[0.0, 0.0], [0.25, 2.0], [0.7, 0.0], [1.1, 0.0]]},
         ]},
        # 摸头：微微歪头 + 一脸开心享受。
        #
        # 原来这里是 head.dy = -7.0（pulse 保持）——**字面意义上把整个头往上平移
        # 7 像素**，而胸只跟 0.7px（look 配置 head.dy=10 vs chest.dy=1），
        # 净效果就是脖子凭空抽长 6.3px。用户 2026-10-14 实测反馈
        # "摸头的时候不应该脖子伸长而是微微歪头一脸开心享受"，完全正确。
        #
        # 现在：歪头蹭过去（ParamAngleZ，走 head.rot_deg 绕颈关节转，不改变颈长），
        # 头顺着手的力道微沉一点点（head.dy 取正 = 往下，幅度只有原来的 2/7），
        # 再配上笑眼 + 脸红 + 嘴角上扬。blink_hold 0.95 配 EyeSmile=1 会让
        # 山型笑眼顶替谷型闭眼，画出来就是 ∩∩ 的享受脸（见 zrig.c 的交叉淡化）。
        {"id": "head_pat", "priority": 6, "duration": 1.0, "return_state": "idle",
         "interruptible": False,
         "channels": [
             {"target": "ParamAngleZ", "wave": "pulse", "amp": 11.0, "dur": 0.40, "ease": "out_back"},
             {"target": "head", "param": "dy", "wave": "pulse", "amp": 2.0, "dur": 0.40, "ease": "out_back"},
             {"target": "head", "param": "dy", "wave": "sine", "amp": 1.2, "freq": 3.5, "dur": 1.0},
             {"target": "ParamEyeLSmile", "wave": "pulse", "amp": 1.0, "dur": 0.30, "ease": "out"},
             {"target": "ParamEyeRSmile", "wave": "pulse", "amp": 1.0, "dur": 0.30, "ease": "out"},
             {"target": "ParamMouthForm", "wave": "pulse", "amp": 0.85, "dur": 0.35, "ease": "out"},
             {"target": "ParamCheek", "wave": "pulse", "amp": 0.60, "dur": 0.40, "ease": "out"},
         ],
         "blink_hold": 0.95,
         "part_overrides": {}},
        {"id": "happy", "priority": 7, "duration": 1.45, "return_state": "idle",
         "interruptible": False,
         # airborne：鞋底纵向净位移 px（蹦起来 —— 这个动作就是要离地）—— check_feet_on_ground 会按
         # 通道幅度×参数绑定复算一遍，对不上就红，防的是"后来有人把幅度调大了"。
         "airborne": 34,
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
             {"target": "mouth_open", "param": "alpha", "wave": "pulse", "amp": -0.9, "dur": 0.25},
         ]},
        {"id": "hammered", "priority": 9, "duration": 0.7, "return_state": "idle",
         "interruptible": False,
         # airborne：鞋底纵向净位移 px（被砸：整个人往下陷）—— check_feet_on_ground 会按
         # 通道幅度×参数绑定复算一遍，对不上就红，防的是"后来有人把幅度调大了"。
         "airborne": 8,
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
        # ⚠ duration 必须贴着通道真实结束的时间写。
        # 这里原本是 0.55，但 bounce(dur 0.28) 到点归零、decay 的包络
        # 7*exp(-6t/0.4) 在 0.28s 已衰到 0.1 度 —— 后面 0.27 秒（将近一半）
        # 角色完全不动，然后"啪"地切回 idle。用户反馈的"点击时中途卡顿"
        # 就是这段死时间（2026-10-14 实测修正）。
        {"id": "clicked", "priority": 4, "duration": 0.34, "return_state": "idle",
         "interruptible": False,
         # airborne：鞋底纵向净位移 px（被戳一下的小跳）—— check_feet_on_ground 会按
         # 通道幅度×参数绑定复算一遍，对不上就红，防的是"后来有人把幅度调大了"。
         "airborne": 6,
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
             {"target": "mouth_open", "param": "alpha", "wave": "pulse", "amp": -0.75, "dur": 0.12, "ease": "out"},
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
         # airborne：鞋底纵向净位移 px（坐下去，重心下沉）—— check_feet_on_ground 会按
         # 通道幅度×参数绑定复算一遍，对不上就红，防的是"后来有人把幅度调大了"。
         "airborne": 4,
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

        has_hands = bool(armp) and any(q["id"].startswith("hand_") for q in armp["parts"])
        has_legs_p = any(q["id"] == "seg_leg_l" for q in parts_list)

        def hand(side, amp, freq=0.0, wave="sine", **kw):
            """手腕通道（绕腕）。正值 = 往身体外侧翻，左右镜像。"""
            c = {"target": f"hand_{side}", "param": "rot_deg", "wave": wave,
                 "amp": amp if side == "l" else -amp, "freq": freq}
            c.update(kw)
            return c

        def leg(side, amp, freq=0.0, wave="sine", **kw):
            """腿通道：bend_x（裙摆下沿钉死、脚踝摆幅最大），不是旋转。"""
            c = {"target": f"seg_leg_{side}", "param": "bend_x", "wave": wave,
                 "amp": amp, "freq": freq, "curve": "tip"}
            c.update(kw)
            return c

        if has_hands:
            # 手腕是整条手臂的最后一节，永远比小臂再晚一点（二级惯性）
            add("idle", [hand("l", 1.2, 0.06, phase=0.42), hand("r", 1.2, 0.06, phase=0.42)])
            add("sway", [hand("l", 3.5, 0.18, phase=0.34), hand("r", 3.5, 0.18, phase=0.34)])
            add("happy", [hand("l", 12.0, 0.0, wave="bounce", dur=0.5),
                          hand("r", 12.0, 0.0, wave="bounce", dur=0.5)])
            add("hammered", [hand("l", 11.0, 2.6, wave="decay", dur=0.7),
                             hand("r", 11.0, 2.6, wave="decay", dur=0.7)])
            add("surprised", [hand("l", 14.0, 0.0, wave="pulse", dur=0.9, ease="out"),
                              hand("r", 14.0, 0.0, wave="pulse", dur=0.9, ease="out")])
        if has_legs_p:
            # 腿：重心一偏，两条腿跟着让一点（同向，幅度比上身小得多）。
            # 用 bend 不用旋转：裙摆下沿那一排像素必须钉死，否则接缝处漏背景。
            add("idle", [leg("l", 1.2, 0.06, phase=0.2), leg("r", 1.2, 0.06, phase=0.2)])
            add("sway", [leg("l", 6.0, 0.18, phase=0.12), leg("r", 6.0, 0.18, phase=0.12)])
            add("happy", [leg("l", -7.0, 0.0, wave="bounce", dur=0.5),
                          leg("r", 7.0, 0.0, wave="bounce", dur=0.5)])
            add("hammered", [leg("l", 8.0, 2.6, wave="decay", dur=0.7),
                             leg("r", 8.0, 2.6, wave="decay", dur=0.7)])

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
            if has_hands:
                # G4c2：手腕是第三节。挥手时手掌比小臂再晚一点、摆得更大，
                # 这就是"鞭梢"的最后一节 —— 没有它，举起来的手是一块硬板。
                wave_channels += [
                    {"target": "hand_r", "param": "rot_deg", "wave": "pulse",
                     "amp": -16.0, "dur": 2.4, "ease": "out"},
                    {"target": "hand_r", "param": "rot_deg", "wave": "sine",
                     "amp": 20.0, "freq": 2.2, "phase": 0.18, "dur": 2.4},
                ]
        actions.append({
            "id": "wave", "priority": 6, "duration": 2.4, "return_state": "idle",
            "interruptible": False,
            # 挥手时的上下起伏：**不许整个人平移**。
            # 原来这里写的是 root.dy ±2px，等于连脚一起浮起来，只能靠声明
            # "airborne": 2 让闸放行 —— 官方《4.添加身体动作》写死的那条是
            # "身体上下运动时，脚不能离开地面"，所以那是权宜，不是设计（G98）。
            #
            # 改成人真实的做法：**胯往下沉、膝盖吃掉这段行程、脚底钉在地上**。
            #   chest.dy        上半身（躯干+头+手臂）跟着节奏起伏
            #   seg_leg_*.bend_y + root 曲线（底边固定、顶端最大）
            #                   腿顶跟着胯走、脚踝那一行纹丝不动
            # 脚件是刚性跟随腿在切线处的形变的，root 曲线在切线处正好是 0，
            # 所以这样加完鞋底净位移仍然是 0 —— 不用再声明 airborne。
            "channels": wave_channels + [
                {"target": "head", "param": "rot_deg", "wave": "sine",
                 "amp": 2.0, "freq": 0.8, "dur": 2.4},
                {"target": "ParamHipDrop", "wave": "sine",
                 "amp": 1.0, "freq": 1.6, "dur": 2.4},
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
        if footp:
            # 脚：挂在腿下面的独立组（T24.5）。
            # 关键是 bend_follow —— 腿是用 bend_x 摆的（ParamLegL 在脚踝处 ±20px），
            # 而 bend 只作用于**那张贴图自己**。鞋拆出去以后如果不跟着腿的形变走，
            # 一摆腿鞋就留在原地，脚踝直接错开十几像素。
            # 取样高度写在切线上（bend_follow_at = 腿件被擦掉的那一行）：
            # 整只鞋按切线处的形变量做**刚性**平移，和腿的最后一行严丝合缝。
            # 这和头/肩用 bend_follow_at 挂在关节上是同一套做法。
            fcut = oy + int(footp["cut"]["leg_cut_y"])
            for side in ("l", "r"):
                groups[f"foot_{side}"] = {
                    "pivot": [ox + int(round((footp["checks"][f"foot_{side}"]["x"][0] +
                                              footp["checks"][f"foot_{side}"]["x"][1]) / 2)),
                              fcut],
                    "parent": f"leg_{side}",
                    "bend_follow": f"seg_leg_{side}",
                    "bend_follow_at": fcut,
                }
        if armp:
            # 前臂挂在上臂下面：枢轴 = 肘关节（anchors 实测），父组旋转自动继承
            el_l = apt("elbow_l", 0.428, 0.172)
            el_r = apt("elbow_r", 0.428, 0.825)
            groups["forearm_l"] = {"pivot": el_l, "parent": "arm_l"}
            groups["forearm_r"] = {"pivot": el_r, "parent": "arm_r"}
            # G4c2：手挂在前臂下面，枢轴 = 袖口下沿那条实测的腕线（make_arm_parts 量的）
            for hp in armp["parts"]:
                if hp["id"].startswith("hand_"):
                    side = hp["id"].split("_")[1]
                    groups[f"hand_{side}"] = {
                        "pivot": [ox + float(hp["pivot"][0]), oy + float(hp["pivot"][1])],
                        "parent": f"forearm_{side}"}
    else:
        groups = {
            "root": {"pivot": [cw // 2, ch], "parent": ""},
            "chest": {"pivot": [cw // 2, chest_y], "parent": "root", "bend_follow": body_id},
            "head": {"pivot": [cw // 2, neck_y], "parent": "chest", "bend_follow": body_id},
        }

    # 眼睛拆件后，老动作里写的 eye_open_left/right 要摊到四个零件上：
    # 眼眶（遮罩）必须和眼白底、眼线一起动，否则遮罩不跟手，裁切就错位了。
    if eyes:
        # 有闭眼真素材时没有 *_lid 这个部件，换成 *_closed（它也要跟着一起位移，
        # 否则偏头/挤眼的时候闭眼补片会掉队）。
        tail = ("socket", "base", "ball", "closed", "lash") if closed else \
               ("socket", "base", "ball", "lid", "lash")
        expand = {
            "eye_open_left":  [f"eye_l_{k}" for k in tail],
            "eye_open_right": [f"eye_r_{k}" for k in tail],
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

    # ---- 下半身动作（2026-10-14）。按上面 GEO2PARAM 的要求「新动作直接写参数」。
    #      原先 18 个动作里只有 sway/idle/happy/hammered 四个碰腿，而且只有一个
    #      左右 bend，所以角色站着时下半身是完全僵的。补两个：
    #        shift_weight —— 站立微动（真人站着重心一直在两腿间挪）
    #        tiptoe       —— 踮脚（开心/期待时用）
    if has_legs_p:
        actions += [
            {"id": "shift_weight", "priority": 2, "duration": 0, "loop": True,
             "return_state": "idle",
             "note": "重心在两腿间缓慢移动，膝盖交替轻屈。"
                     "频率 0.11 比呼吸(0.28)和摇摆(0.18)都慢，三者不会同步成机械感",
             "channels": [
                 {"target": "ParamWeightShift", "wave": "sine", "amp": 0.75, "freq": 0.11},
                 # 两膝反相：重心在哪边，哪边腿绷直、另一边放松
                 {"target": "ParamKneeL", "wave": "sine", "amp": 0.45, "freq": 0.11},
                 {"target": "ParamKneeR", "wave": "sine", "amp": -0.45, "freq": 0.11},
                 # 上半身跟着重心有一点延迟（phase 比下半身晚），不然像整块板子在平移
                 {"target": "ParamBaseRot", "wave": "sine", "amp": 0.5, "freq": 0.11,
                  "phase": 0.12},
                 {"target": "ParamBodyAngleX", "wave": "sine", "amp": 3.0, "freq": 0.11,
                  "phase": 0.08},
                 {"target": "ParamAngleZ", "wave": "sine", "amp": 1.2, "freq": 0.11,
                  "phase": 0.2},
                 {"target": "ParamHairSide", "wave": "sine", "amp": 0.18, "freq": 0.11,
                  "phase": 0.3},
             ]},
            # 2026-10-14（T24.5）：踮起的那三条从 bounce 改成 pulse。
            # bounce = sin(π·ease(u))，用 out_back 时峰值落在 u≈0.13 —— 实算
            # ParamTiptoe 只有 **48 毫秒** 站在 0.95 以上，剩下 0.65 秒都在往下掉。
            # 以前鞋没有姿态图，看不出来；现在鞋真的换了一张图，一闪而过就白做了。
            # pulse = 冲上去**保持**，收尾交给动作自己的 fade_out（官方 FadeOutTime
            # 就是干这个的）→ 0.35 秒踮起、0.7 秒保持、0.2 秒落回。
            {"id": "tiptoe", "priority": 7, "duration": 1.05, "return_state": "idle",
             "note": "踮脚尖：踮起时双膝微屈，头发与呆毛有一拍滞后；"
                     "踮起用 pulse（冲上去保持），落回交给 fade_out",
             "channels": [
                 {"target": "ParamTiptoe", "wave": "pulse", "amp": 1.0, "dur": 0.35,
                  "ease": "out_back"},
                 {"target": "ParamKneeL", "wave": "pulse", "amp": 0.5, "dur": 0.35,
                  "ease": "out_back"},
                 {"target": "ParamKneeR", "wave": "pulse", "amp": 0.5, "dur": 0.35,
                  "ease": "out_back"},
                 # 这里原来还有一条 ParamBaseY（全身上下）。删了：
                 # ParamBaseY 走的是 root.dy，**脚也跟着飞**（它本来就是给
                 # happy 的跳跃用的，满格 40px）。踮脚的升高已经由 ParamTiptoe
                 # 给了（root -30 + 两只脚 +30，鞋钉在地上），再叠 BaseY 等于
                 # 让人整个浮起来 8px —— 实测动作期间画面最底行 747→744。
                 # 官方《添加身体动作》写死的那条："身体上下时脚不能离地"。
                 {"target": "ParamAngleZ", "wave": "bounce", "amp": 3.0, "dur": 0.9},
                 {"target": "ParamArmLA", "wave": "bounce", "amp": 0.18, "freq": 0.0,
                  "dur": 0.8},
                 {"target": "ParamArmRA", "wave": "bounce", "amp": 0.18, "freq": 0.0,
                  "dur": 0.8},
                 {"target": "ParamHairAhoge", "wave": "bounce", "amp": 0.6, "dur": 1.0},
                 {"target": "ParamHairSide", "wave": "bounce", "amp": 0.4, "dur": 1.0},
             ]},
        ]

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

    # 侧发：两缕垂在脸旁的头发，摆幅全身最大（它底下的脸颊/下颌是 AI 重绘补出来的，
    # 所以敢让它甩）。后发是整团扣在头上的壳，只跟着慢半拍地晃一点点。
    if any(p["id"] == "hair_side_l" for p in parts_list):
        side = {
            "breath":    {"wave": "sine", "amp": 0.8, "freq": 0.24},
            "idle":      {"wave": "sine", "amp": 1.3, "freq": 0.19},
            "sway":      {"wave": "sine", "amp": 3.6, "freq": 0.31},
            "happy":     {"wave": "bounce", "amp": 4.8, "dur": 1.4, "ease": "out"},
            "surprised": {"wave": "decay", "amp": 5.4, "dur": 0.9, "freq": 2.2},
            "head_pat":  {"wave": "sine", "amp": 3.6, "freq": 1.0},
            "hammered":  {"wave": "decay", "amp": 6.0, "dur": 1.0, "freq": 2.8},
            "wave":      {"wave": "sine", "amp": 2.0, "freq": 1.2},
            "sleep":     {"wave": "sine", "amp": 0.6, "freq": 0.1},
            "nod":       {"keys": [[0.0, 0.0], [0.25, -2.2], [0.6, 1.6], [1.1, 0.0]],
                          "interp": "smooth"},
        }
        back = {
            "breath":    {"wave": "sine", "amp": 0.3, "freq": 0.24},
            "idle":      {"wave": "sine", "amp": 0.5, "freq": 0.18},
            "sway":      {"wave": "sine", "amp": 1.6, "freq": 0.30},
            "happy":     {"wave": "bounce", "amp": 1.9, "dur": 1.4, "ease": "out"},
            "surprised": {"wave": "decay", "amp": 2.2, "dur": 0.9, "freq": 2.0},
            "head_pat":  {"wave": "sine", "amp": 1.5, "freq": 1.0},
            "hammered":  {"wave": "decay", "amp": 2.6, "dur": 1.0, "freq": 2.6},
            "wave":      {"wave": "sine", "amp": 0.9, "freq": 1.2},
            "sleep":     {"wave": "sine", "amp": 0.25, "freq": 0.1},
        }
        by_id4 = {a["id"]: a for a in actions}
        for aid, spec in side.items():
            if aid in by_id4:
                for pid in ("hair_side_l", "hair_side_r"):
                    ch2 = {"target": pid, "param": "bend_x", "curve": "tip"}
                    ch2.update(spec)
                    by_id4[aid]["channels"].append(ch2)
        for aid, spec in back.items():
            if aid in by_id4:
                ch2 = {"target": "hair_back", "param": "bend_x", "curve": "tip"}
                ch2.update(spec)
                by_id4[aid]["channels"].append(ch2)

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

    # —— 左右眼分家（Live2D 标准 ParamEyeLOpen / ParamEyeROpen）——
    # 引擎按 eye_side 决定这件看左眼还是右眼的闭合度；不写就只能两眼一起眨。
    # 按下划线分词取 l/r/left/right，避免把 eye_hl_l 里的 "hl" 误判成左。
    for _p in parts_list:
        _tok = _p["id"].split("_")
        if _tok[0] != "eye":
            continue
        if "l" in _tok or "left" in _tok:
            _p["eye_side"] = "l"
        elif "r" in _tok or "right" in _tok:
            _p["eye_side"] = "r"

    # ------------------------------------------------------------------
    # 动作通道 → 参数通道（Live2D 合规：.motion3 的曲线只能打在参数上）
    # ------------------------------------------------------------------
    # 官方 motion3.json 的 Curve.Target 只有三种：Model（Opacity/EyeBlink/LipSync）、
    # Parameter、PartOpacity —— **没有"直接写部件位移/旋转/缩放"这种通道**
    # （CubismWebFramework/src/motion/cubismmotion.ts 第 38~40 行的三个常量，
    #  实测 Haru 的 haru_g_m01.motion3.json：Parameter 42 条 + PartOpacity 20 条 + Model 1 条）。
    #
    # 上面那些动作是按"这个零件挪几个像素"调出来的，数值本身是美术成果，不能丢；
    # 所以这里不重写动作，而是把每条几何通道按**参数的 bind 系数反算**成参数值：
    #
    #     参数振幅 = 几何振幅 ÷ bind scale
    #
    # 换完之后 rig.json 里就只剩参数通道了，对外接口（LLM/脚本/测试台）也从
    # "你得知道角色拆了几件"变成"你只要会写 ParamXxx"。
    #
    # 新动作请**直接写参数**；这张表只是一次性换算 + 守门人：
    # 出现没有登记的几何目标就直接报错，防止几何通道偷偷长回来。
    GEO2PARAM = {
        # (目标, 几何量): (参数 id, bind scale)
        ("head", "rot_deg"):        ("ParamAngleZ", 0.5),
        # 头的平移走 ParamAngleX/Y：它们是内建参数，没有 bind，
        # "scale" 来自 look.groups.head（dx 4.0 / dy 10.0，再除以参数满量程 30）。
        ("head", "dx"):             ("ParamAngleX", 4.0 / 30.0),
        ("head", "dy"):             ("ParamAngleY", -10.0 / 30.0),
        ("chest", "dy"):            ("ParamBodyAngleY", 0.25),
        ("root", "dx"):             ("ParamBaseX", 2.0),
        ("root", "dy"):             ("ParamBaseY", -4.0),
        ("root", "rot_deg"):        ("ParamBaseRot", 0.5),
        (body_id, "bend_x"):        ("ParamBodyAngleX", 1.0),
        (body_id, "bend_y"):        ("ParamBodyAngleY", 0.4),
        ("arm_l", "dy"):            ("ParamShoulderY", -0.8),
        ("arm_r", "dy"):            ("ParamShoulderY", -0.8),
        ("arm_l", "rot_deg"):       ("ParamArmLA", 6.0),
        ("arm_r", "rot_deg"):       ("ParamArmRA", -6.0),
        ("forearm_l", "rot_deg"):   ("ParamArmLB", 10.0),
        ("forearm_r", "rot_deg"):   ("ParamArmRB", -10.0),
        ("hand_l", "rot_deg"):      ("ParamHandL", 22.0),
        ("hand_r", "rot_deg"):      ("ParamHandR", -22.0),
        ("seg_leg_l", "bend_x"):    ("ParamLegL", 20.0),
        ("seg_leg_r", "bend_x"):    ("ParamLegR", 20.0),
        ("brow_l", "dy"):           ("ParamBrowLY", -5.0),
        ("brow_r", "dy"):           ("ParamBrowRY", -5.0),
        ("brow_l", "rot_deg"):      ("ParamBrowLAngle", 7.0),
        ("brow_r", "rot_deg"):      ("ParamBrowRAngle", -7.0),
        ("hair_ahoge", "bend_x"):   ("ParamHairAhoge", 10.0),
        ("hair_front", "bend_x"):   ("ParamHairFront", 6.0),
        ("hair_side_l", "bend_x"):  ("ParamHairSide", 7.0),
        ("hair_side_r", "bend_x"):  ("ParamHairSide", 7.0),
        ("hair_back", "bend_x"):    ("ParamHairBack", 5.0),
        ("mouth_mask", "sy"):       ("ParamMouthOpenY", round(0.95 - mouth["closed_sy"], 3) if mouth else 0.895),
        ("mouth_open", "alpha"):    ("ParamMouthOpenY", -0.9),
        ("mouth_open", "sy"):       ("ParamMouthOpenY", 0.144),
        # 眼球：左右/上下走 gaze（max_offset 4.0 / 2.5），缩放走瞳孔形状参数
        ("eye_l_ball", "dx"):       ("ParamEyeBallX", 4.0),
        ("eye_r_ball", "dx"):       ("ParamEyeBallX", 4.0),
        ("eye_l_ball", "dy"):       ("ParamEyeBallY", 2.5),
        ("eye_r_ball", "dy"):       ("ParamEyeBallY", 2.5),
        ("eye_open_left", "dx"):    ("ParamEyeBallX", 4.0),
        ("eye_open_right", "dx"):   ("ParamEyeBallX", 4.0),
        ("eye_open_left", "sx"):    ("ParamEyeBallForm", 0.18),
        ("eye_open_right", "sx"):   ("ParamEyeBallForm", 0.18),
        ("eye_open_left", "sy"):    ("ParamEyeBallForm", 0.22),
        ("eye_open_right", "sy"):   ("ParamEyeBallForm", 0.22),
        ("eye_l_ball", "sx"):       ("ParamEyeBallForm", 0.18),
        ("eye_r_ball", "sx"):       ("ParamEyeBallForm", 0.18),
        ("eye_l_ball", "sy"):       ("ParamEyeBallForm", 0.22),
        ("eye_r_ball", "sy"):       ("ParamEyeBallForm", 0.22),
    }
    # 直接删掉的通道：整只眼（眼眶+眼白+睫毛）在脸上平移。
    # 这件事本来就该由 head 组的位移带着走（眼部件全在 head 组里），
    # 动作里再逐件写一遍等于动两次；而且新加的零件（比如笑眼件）不会出现在这张
    # 手写清单里 —— 笑眼件没有这条通道，眨眼时就会掉队。幅度只有 0.5~1.5px，删掉看不出来。
    # （动作定义里写的是 eye_open_left/right，上面那段会先摊到五个零件上，
    #   所以这里按摊开后的零件名列。）
    GEO_DROP = {("eye_open_left", "dy"), ("eye_open_right", "dy")} | {
        (f"eye_{_s}_{_k}", _p)
        for _s in ("l", "r")
        for _k in ("socket", "base", "lid", "closed", "lash", "smile")
        for _p in ("dx", "dy", "sx", "sy")
    }
    # 一个动作里几条嘴通道原本分写（遮罩高度 / 上唇线透明度 / 开口高度），
    # 换算后它们是同一个 ParamMouthOpenY，波形却不一样，不能简单相加（会 clamp 成 1.0）。
    # 这几个动作手工给一条合并后的曲线。
    MOUTH_MERGE = {
        "talk":      {"wave": "flap", "amp": 0.833, "freq": 3.0},
        "surprised": {"wave": "pulse", "amp": 1.0, "dur": 0.25, "ease": "out"},
    }
    # 呼吸动作额外挂一条官方口径的 ParamBreath：CubismBreath 输出的是
    # offset + peak*sin（0..1 的单向值），所以写 {amp 0.5, bias 0.5} 而不是双向正弦。
    # 它驱动胸腔的起伏与纵向缩放，躯干的弯曲由上面换算出来的 ParamBodyAngleY 负责。
    BREATH_CH = {"target": "ParamBreath", "wave": "sine", "amp": 0.5, "bias": 0.5, "freq": 0.28}

    # 参数表提前算一次：下面的通道转换要用它判断"这个 target 是不是参数名"，
    # 返回字典里也要用。param_list 是纯函数，提前调用没有副作用。
    PARAMS = param_list(mouth=mouth,
                        has_brows=any(p["id"] == "brow_l" for p in parts_list),
                        head_is_part=head_is_part,
                        jointed_arms=bool(armp),
                        has_blend=bool(blendp),
                        has_side=any(p["id"] == "hair_side_l" for p in parts_list),
                        has_legs=any(p["id"] == "seg_leg_l" for p in parts_list),
                        body_id=body_id,
                        has_eyeballs=any(p["id"] == "eye_l_ball" for p in parts_list),
                        foot_lift=(footp["lift_px"] if footp else None))
    PARAM_IDS = {q["id"] for q in PARAMS}

    # 引擎自己注册的内建参数（zrig.c 的 param_add_builtin 那一串）。
    # 它们不写进 rig.json 的 params 里，但动作通道可以直接打 —— 引擎解析
    # target 时走的是 param_find()，内建和声明的参数在同一张表里。
    # ⚠ 这份名单必须和 zrig.c 保持一致，selfcheck 的 check_builtin_params() 盯着。
    BUILTIN_PARAM_IDS = {
        "ParamAngleX", "ParamAngleY", "ParamEyeOpen", "ParamEyeLOpen",
        "ParamEyeROpen", "ParamEyeLSmile", "ParamEyeRSmile",
        "ParamEyeBallX", "ParamEyeBallY",
    }
    WRITABLE_PARAM_IDS = PARAM_IDS | BUILTIN_PARAM_IDS

    def to_param_channels(acts):
        n_in = n_out = 0
        for a in acts:
            out_ch, seen = [], set()
            mouth_merged = False
            for c in a.get("channels", []):
                n_in += 1
                tgt, prop = c.get("target"), c.get("param")
                if (tgt, prop) in GEO_DROP:
                    continue

                # 已经是参数通道的直接放行 —— 上面 GEO2PARAM 的注释说了
                # 「新动作请直接写参数」，这里就是那条路。判据是 target 真的是
                # param_list() 里登记过的参数 id，所以写错名字仍然会被下面拦住。
                if prop is None and tgt in WRITABLE_PARAM_IDS:
                    out_ch.append(dict(c))
                    n_out += 1
                    continue

                key = (tgt, prop)
                if key not in GEO2PARAM:
                    raise SystemExit(
                        f"[make_rig] 动作 {a['id']} 的通道 {tgt}.{prop} 没有对应的参数；"
                        f"请先在 param_list() 里给它一个参数再加动作"
                        f"（Live2D 的动作只能打在参数上）")
                pid, scale = GEO2PARAM[key]
                if pid == "ParamMouthOpenY" and a["id"] in MOUTH_MERGE:
                    if mouth_merged:
                        continue
                    mouth_merged = True
                    nc = {"target": "ParamMouthOpenY"}
                    nc.update(MOUTH_MERGE[a["id"]])
                    out_ch.append(nc)
                    continue
                nc = {"target": pid}
                for k, v in c.items():
                    if k in ("target", "param", "curve", "strips"):
                        continue        # curve/strips 是 bind 的属性，跟着参数走
                    if k == "amp":
                        nc["amp"] = round(v / scale, 4)
                    elif k == "keys":
                        nc["keys"] = [[t, round(val / scale, 4)] for t, val in v]
                    else:
                        nc[k] = v
                # 左右对称的两条（侧发 / 两肩 / 两只眼球）换算后完全一样，
                # 合成一条就够——它们本来就归同一个参数。
                sig = tuple(sorted((k, tuple(map(tuple, v)) if k == "keys" else v)
                                   for k, v in nc.items()))
                if sig in seen:
                    continue
                seen.add(sig)
                out_ch.append(nc)
            if a["id"] == "breath":
                out_ch.insert(0, dict(BREATH_CH))
            a["channels"] = out_ch
            n_out += len(out_ch)
        return n_in, n_out

    # ------------------------------------------------------------------
    # 下半身陪衬通道（2026-10-14）
    # ------------------------------------------------------------------
    # 上面那批动作是按"上半身怎么演"调出来的，腿基本没管 —— 结果 14 个动作
    # 下半身完全僵着。人不是这样的：挥手会把重心压到支撑腿，受惊会屈膝，
    # 思考时会单腿承重，站着发呆重心一直在两腿间慢慢挪。
    #
    # 这里集中补，而不是逐个去改上面的定义，原因有三：
    #   · wave / look_around 是动态拼出来的，没有固定的字面量可改
    #   · 集中成一张表，幅度好横向对比（都是陪衬，不能喧宾夺主）
    #   · 将来要整体调强调弱，改一处就行
    # 幅度一律压在 0.5 以内（参数满量程是 1.0）—— 下半身是伴奏不是主旋律。
    if has_legs_p:
        W, KL, KR = "ParamWeightShift", "ParamKneeL", "ParamKneeR"
        LOWER_EXTRA = {
            # 挥手：重心压到支撑腿（挥右手→压左腿），另一腿放松微屈
            "wave": [
                {"target": W,  "wave": "pulse", "amp": -0.40, "dur": 0.5, "ease": "out"},
                {"target": KR, "wave": "pulse", "amp": 0.22, "dur": 0.5, "ease": "out"},
                {"target": W,  "wave": "sine",  "amp": 0.10, "freq": 0.42},
            ],
            # 受惊：一个急促的屈膝（人吓到会明显矮一截），然后弹回。
            # 这里幅度比别的动作大 —— 受惊是全身反应，腿僵着就假了。
            # 0.30/0.35s 实测只有噪声底 1.7 倍（看不太出来），加到 0.48/0.5s。
            "surprised": [
                {"target": KL, "wave": "bounce", "amp": 0.48, "dur": 0.50, "ease": "out_back"},
                {"target": KR, "wave": "bounce", "amp": 0.48, "dur": 0.50, "ease": "out_back"},
                {"target": W,  "wave": "bounce", "amp": -0.24, "dur": 0.55},
            ],
            # 难过：重心塌下去并偏向一侧，膝盖一直松着
            "sad": [
                {"target": KL, "wave": "pulse", "amp": 0.26, "dur": 0.6, "ease": "out"},
                {"target": KR, "wave": "pulse", "amp": 0.20, "dur": 0.6, "ease": "out"},
                {"target": W,  "wave": "pulse", "amp": 0.22, "dur": 0.8, "ease": "out"},
                {"target": W,  "wave": "sine",  "amp": 0.08, "freq": 0.09},
            ],
            # 思考：单腿承重（想事情时的典型站姿），重心缓慢游移
            "think": [
                {"target": W,  "wave": "pulse", "amp": 0.34, "dur": 0.7, "ease": "out"},
                {"target": KL, "wave": "pulse", "amp": 0.24, "dur": 0.7, "ease": "out"},
                {"target": W,  "wave": "sine",  "amp": 0.12, "freq": 0.13},
            ],
            # 说话：很轻的重心小挪动，频率跟着语速走
            "talk": [
                {"target": W,  "wave": "sine", "amp": 0.14, "freq": 0.33},
                {"target": KL, "wave": "sine", "amp": 0.08, "freq": 0.33, "phase": 0.5},
                {"target": KR, "wave": "sine", "amp": -0.08, "freq": 0.33, "phase": 0.5},
            ],
            # 站着睡：极慢的摇晃 + 膝盖发软，频率比呼吸还慢
            "sleep": [
                {"target": W,  "wave": "sine",  "amp": 0.26, "freq": 0.05},
                {"target": KL, "wave": "pulse", "amp": 0.18, "dur": 1.2, "ease": "out"},
                {"target": KR, "wave": "pulse", "amp": 0.18, "dur": 1.2, "ease": "out"},
                {"target": KL, "wave": "sine",  "amp": 0.07, "freq": 0.05, "phase": 0.3},
            ],
            # 环顾：重心跟着视线方向挪，比头慢半拍
            "look_around": [
                {"target": W,  "wave": "sine", "amp": 0.20, "freq": 0.45, "phase": 0.18},
                {"target": KL, "wave": "sine", "amp": 0.09, "freq": 0.45, "phase": 0.18},
                {"target": KR, "wave": "sine", "amp": -0.09, "freq": 0.45, "phase": 0.18},
            ],
            # 被摸头：被按住会往下沉一点，膝盖跟着软
            "head_pat": [
                {"target": KL, "wave": "pulse", "amp": 0.20, "dur": 0.35, "ease": "out_back"},
                {"target": KR, "wave": "pulse", "amp": 0.20, "dur": 0.35, "ease": "out_back"},
            ],
        }
        _patched = 0
        for _a in actions:
            _ex = LOWER_EXTRA.get(_a["id"])
            if _ex:
                _a.setdefault("channels", []).extend(_ex)
                _patched += 1
        if _patched != len(LOWER_EXTRA):
            _miss = sorted(set(LOWER_EXTRA) - {a["id"] for a in actions})
            raise SystemExit(f"[make_rig] 下半身陪衬表里有动作不存在：{_miss}")
        print(f"  下半身陪衬：给 {_patched} 个动作补了腿部通道")

    _n_in, _n_out = to_param_channels(actions)
    print(f"  动作通道：{_n_in} 条几何通道 → {_n_out} 条参数通道"
          f"（≈ Live2D .motion3 的 Parameter 曲线）")

    rig = {
        "schema_version": "1.0",
        "id": f"{name}_teen",
        "name": name,
        "canvas": {"w": cw, "h": ch},
        "origin": [cw // 2, ch],
        "ground_line": ch - 8,
        "groups": groups,
        # 眼球左右 ±4px / 上下 ±2.5px：满格 ParamEyeBallX/Y = look_around 动作的幅度。
        "gaze": {"max_offset": [4.0, 2.5]},
        # 指针跟随：眼睛看过去的同时，头和上身也跟着转一点
        # （Live2D 的 ParamAngleX/Y + ParamBodyAngleX）。
        # 幅度刻意保守：头 5° + 4px，上身 1.2° + 1.5px —— 再大就"摇头晃脑"了。
        "look": {
            "speed": 9.0,
            "groups": {
                # dy 10：ParamAngleY 满格 = 头上下 10px = surprised 缩脖子那下的幅度。
                # 动作和指针跟随写的是同一个参数，幅度也必须是同一套（官方就是这么做的）。
                "head": {"rot_deg": 5.0, "dx": 4.0, "dy": 10.0},
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
        # —— 网格形变器（A5，≈ Live2D 的 ワープデフォーマ）——
        # 呆毛被切成 2×4 共 15 个控制点。amount=1 时：梢往右 11px、
        # 中段往左 4px、根不动 —— 一根 S 形曲线，整体平移/倾斜做不出这个效果。
        # 行号 r=0 是素材顶边（毛梢），r=4 是底边（发根，固定）。
        "deformers": [
            {"id": "ahoge_s", "part": "hair_ahoge", "cols": 2, "rows": 4,
             "note": "呆毛 S 形甩动：梢与中段朝相反方向，根固定",
             "points": [
                 {"c": 0, "r": 0, "dx": 11.0, "dy": -1.0},
                 {"c": 1, "r": 0, "dx": 11.0, "dy": -1.5},
                 {"c": 2, "r": 0, "dx": 11.0, "dy": -1.0},
                 {"c": 0, "r": 1, "dx": 4.5}, {"c": 1, "r": 1, "dx": 4.5},
                 {"c": 2, "r": 1, "dx": 4.5},
                 {"c": 0, "r": 2, "dx": -4.0}, {"c": 1, "r": 2, "dx": -4.0},
                 {"c": 2, "r": 2, "dx": -4.0},
                 {"c": 0, "r": 3, "dx": -1.5}, {"c": 1, "r": 3, "dx": -1.5},
                 {"c": 2, "r": 3, "dx": -1.5}
             ]},
        ],
        "physics": [
            # 上身追赶头部的惯性（Live2D 官方《提高动态质量的技巧》第 2 条：
            # 「转动脸部，身体会在稍后跟随」—— 脸和身体同时到位仍然像机器人）。
            #
            # 为什么能和 ParamAngleZ→chest.rot_deg 那条瞬时绑定共存而不打架：
            # 物理的输出是 `pos - target`，也就是**纯滞后量**，静止时自动归零
            # （见 zrig.c physics_update 的注释"只加惯性，不会永久吹偏"）。
            # 所以稳态倾斜由那条绑定给，这里只补转头过程中的"追赶"。
            #
            # 参数取值：ω=√22≈4.7rad/s（周期 1.34s，比头发慢得多，躯干是重的），
            # 阻尼比 ζ=5.5/(2×4.69)=0.59 —— 收得干净、只留一点点回弹。
            # 对照：呆毛 ω=6.5 ζ=0.39（更弹），手腕 stiffness 34 damping 4.4。
            {"id": "torso_follow_head", "part": body_id,
             "param": "bend_x", "curve": "root",
             "input": [{"param": "ParamAngleZ", "weight": 1.0}],
             "ratio": 0.10, "stiffness": 22, "damping": 5.5, "max": 3.0,
             "note": "上身追赶头部的惯性滞后；输出是 pos-target，静止归零"},
            {"id": "ahoge_x", "part": "hair_ahoge", "driver": "head", "axis": "x",
             "param": "bend_x", "curve": "root",
             "ratio": 0.5, "stiffness": 42, "damping": 5.0, "max": 8,
             "note": "呆毛左右甩：根在底边，所以曲线用 root"},
            # G16 多段摆：第二段的输入是第一段的输出（不是头的位移），
            # 输出写进 S 形网格形变器 → 发根先动、发梢再慢半拍地甩出 S 形。
            {"id": "ahoge_tip", "part": "hair_ahoge", "driver": "ahoge_x",
             "deformer": "ahoge_s",
             "ratio": 0.9, "stiffness": 26, "damping": 3.4, "max": 1.0,
             "note": "呆毛第二段（梢）：串在 ahoge_x 后面，驱动 S 形形变器"},
            {"id": "ahoge_y", "part": "hair_ahoge", "driver": "head", "axis": "y",
             "param": "bend_y", "curve": "root",
             "ratio": 0.45, "stiffness": 55, "damping": 6.0, "max": 5,
             "note": "呆毛上下点头"},
            # G4c2：手腕滞后（物理输入 = 腕点被前臂组带着走了多少像素）。
            # 这是"鞭梢"的最后一节：大臂带小臂、小臂带手，手永远慢半拍。
            {"id": "hand_l_lag", "part": "hand_l", "driver": "forearm_l", "axis": "x",
             "param": "rot_deg",
             "ratio": 0.22, "stiffness": 34, "damping": 4.4, "max": 9,
             "note": "手腕跟随滞后：部件锚点就在腕上，所以 rot_deg 绕腕转"},
            {"id": "hand_r_lag", "part": "hand_r", "driver": "forearm_r", "axis": "x",
             "param": "rot_deg",
             "ratio": 0.22, "stiffness": 34, "damping": 4.4, "max": 9},
            {"id": "bangs_x", "part": "hair_front", "driver": "head", "axis": "x",
             "param": "bend_x", "curve": "tip",
             "ratio": 0.3, "stiffness": 65, "damping": 7.5, "max": 4,
             "note": "刘海吊在额头上，发梢在下 → 曲线 tip，幅度要小"},
        ],
        # 命名参数层（对齐 Live2D 的 ParamXxx）：外部（脚本 / LLM / 口型 / 测试台滑条）
        # 只认参数名，不用知道角色内部拆了几件。内建的 ParamAngleX/Y、ParamEyeOpen、
        # ParamEyeBallX/Y 由引擎注册，这里补角色自己的那些。
        "params": PARAMS,
        # 表情层（Live2D 的 expression）：一组参数偏移，叠在当前动作之上。
        # 和动作是两条轨 —— 可以"笑着挥手"，不用为每种组合再做一个动作。
        # Pose（≈ Live2D pose3.json）：一组互斥差分，同一时刻只有一个档位可见。
        # 这里是眼高光的形状差分（圆形 / 星形 / 无），切换带淡入淡出。
        "poses": ([{
            "id": "eye_hl_style", "fade": 0.3, "default": "round",
            "entries": [
                {"id": "round", "parts": ["eye_hl_l", "eye_hl_r"]},
                {"id": "star", "parts": ["eye_hl_star_l", "eye_hl_star_r"]},
            ],
            "note": "眼高光形状差分；切 none 可以整组关掉（死鱼眼）",
        }] if (blendp and blendp.get("star")) else []),
        # xfade（T24.5）：参数驱动的两张姿态图交叉淡化。和 Pose 同一件事，
        # 区别是驱动源 —— Pose 要"切一下"，xfade 跟着参数值走，所以能和
        # 动作曲线（ParamTiptoe 的 bounce）同步，踮起来和落回去各淡一次。
        # 淡化窗口取参数量程的中段 [0.40,0.60]：两头留出纯常态/纯踮脚，
        # 中间那段两张图都在（淡出件按官方 Pose 曲线抬不透明度，背景透出 ≤15%）。
        # 窗口为什么这么窄：两张姿态图的鞋口差 30px，交叠期一定能看出双轮廓
        # （官方《创建有姿势切换的动态》也只说"尽量减少"，没法消掉）。
        # 窗口越窄，参数扫过它的时间越短 —— 实测踮脚动作里交叠只占 0.1 秒上下。
        "xfades": ([{
            "id": f"foot_{side}_tiptoe", "param": "ParamTiptoe", "in": [0.40, 0.60],
            "from": f"seg_foot_{side}", "to": f"seg_foot_{side}_tip",
            "note": "常态鞋 → 踮脚鞋（鞋身拉长 %.0fpx、鞋底带压扁）" % footp["lift_px"],
        } for side in ("l", "r")] if footp else []),
        # 参数分组（= model3.json 的 "Groups"）：告诉外部驱动"哪些参数归自动眨眼/口型管"。
        # Live2D SDK 就是靠这张表决定 CubismEyeBlink / CubismLipSync 去写哪几个参数的。
        "param_groups": [
            {"name": "EyeBlink", "ids": ["ParamEyeLOpen", "ParamEyeROpen"]},
            {"name": "LipSync", "ids": ["ParamMouthOpenY"]},
        ],
        # 口型音素表（Live2D 的「母音認識方式」）。官方标准参数里没有
        # ParamMouthA/I/U/E/O —— あ/い/う/え/お 是「开多大 × 嘴形」的组合，
        # 所以这里是一张组合表，而不是五个自造参数。引擎按它平滑地摆嘴形。
        # 口型层压过表情的上限权重。真正的接管力度 = 这个数 × 这一帧的口型用力程度，
        # 所以停顿时表情会自己回来、说完是连续过渡。满力说话时取 1.0：
        # 张着嘴就别再挂着笑的嘴角（官方固定 0.8 是因为它的 LipSync 只管 OpenY）。
        "viseme_weight": 1.0,
        "visemes": viseme_list(mouth=mouth),
        "expressions": expression_list(mouth=mouth,
                                       has_brows=any(p["id"] == "brow_l" for p in parts_list),
                                       head_is_part=head_is_part,
                                       has_blend=bool(blendp),
                                       has_smile_eyes=any(p["id"].endswith("_smile")
                                                          for p in parts_list)),
    }


    # —— 侧发/后发的网格形变器与摆链（A5 + G16）——
    # 侧发是两条“根在上、梢在下”的长条：r=0 是素材顶边（发根，固定），
    # r=4 是底边（发梢）。amount=1 时中段往左、梢往右 = 一条 S，和整体倾斜不一样。
    if any(p["id"] == "hair_side_l" for p in rig["parts"]):
        for pid in ("hair_side_l", "hair_side_r"):
            tag = pid[-1]
            rig["deformers"].append(
                {"id": f"side_{tag}_s", "part": pid, "cols": 2, "rows": 4,
                 "note": "侧发 S 形甩动：发根固定，中段与发梢反向",
                 "points": [
                     {"c": 0, "r": 1, "dx": -1.4}, {"c": 1, "r": 1, "dx": -1.6},
                     {"c": 2, "r": 1, "dx": -1.4},
                     {"c": 0, "r": 2, "dx": -3.2}, {"c": 1, "r": 2, "dx": -3.6},
                     {"c": 2, "r": 2, "dx": -3.2},
                     {"c": 0, "r": 3, "dx": 1.8}, {"c": 1, "r": 3, "dx": 2.2},
                     {"c": 2, "r": 3, "dx": 1.8},
                     {"c": 0, "r": 4, "dx": 5.4, "dy": 1.0},
                     {"c": 1, "r": 4, "dx": 5.8, "dy": 1.2},
                     {"c": 2, "r": 4, "dx": 5.4, "dy": 1.0},
                 ]})
        # 裙摆的两张网格：seg_torso 是 273x501，裙子占下 42%（y>=290）。
        # rows=5 → 控制点行落在 y = 0 / 100 / 200 / 301 / 401 / 501，
        # r=0~2 是上身（一个点都不动），r=3 正好压在裙腰上（当"根"），
        # r=4/5 是裙身和裙底 —— 所以**裙子不用拆成独立部件**，
        # 一张挂在躯干上的网格就能只摆裙摆。裙底下的大腿早就拆出来并重绘过了，
        # 裙摆荡开露出来的是真大腿，不是空洞。
        # rows=10 不是为了裙摆本身的精度，是为了**上身的 bend**：
        # 网格路径下 bend 曲线是在控制点上采样、格子内线性插值的，
        # rows=5 时 u² 曲线被折成 6 段，上身轮廓会有 1000+ 像素的偏移；
        # rows=10 把这个误差压到百位数。行 y = 501*r/10，裙腰(y≈300) 正好落在 r=6。
        _SKX = {6: 0.5, 7: 1.8, 8: 4.2, 9: 7.0, 10: 10.0}       # 横摆：越往下甩得越远
        _SKY = {6: 0.2, 7: 0.7, 8: 1.6, 9: 2.6, 10: 3.8}        # 纵摆：上下滞后
        # —— 眉形（ParamBrowL/RForm）——
        # 合规表最后两个 ⬜。不需要新素材：眉毛本来就是一条横着的网格能表达的形状。
        # brow_l 的眉头在右端（c=4，靠中线），brow_r 的眉头在左端（c=0）——
        # 眉头那一侧给得比眉尾轻一点，+1 时才像"眉峰在中后段隆起"而不是整条拱桥。
        for _pid, _inner in (("brow_l", 4), ("brow_r", 0)):
            _amp = {0: 2.3, 1: -1.1, 2: -3.6, 3: -1.1, 4: 2.3}
            _amp[_inner] = 1.8                      # 眉头端收一点
            rig["deformers"].append(
                {"id": f"{_pid}_form", "part": _pid, "cols": 4, "rows": 2,
                 "note": "眉形：+1 中段隆起（山なり/惊讶），−1 中段下压（しかめ/困扰）；"
                         "只改形状不挪位置，上下/左右/角度另有参数",
                 "points": [{"c": c, "r": r, "dy": round(v, 3)}
                            for c, v in _amp.items() for r in (0, 1, 2)]})
        rig["deformers"] += [
            {"id": "skirt_sway_x", "part": "seg_torso", "cols": 2, "rows": 10,
             "note": "裙摆横摆：裙腰(r=6)固定，越往下甩得越远，中列比两侧多一点",
             "points": [
                 {"c": c, "r": r, "dx": round(v * (1.08 if c == 1 else 1.0), 3),
                  **({"dy": round(v * 0.09, 3)} if r == 10 else {})}
                 for r, v in _SKX.items() for c in (0, 1, 2)
             ]},
            {"id": "skirt_sway_y", "part": "seg_torso", "cols": 2, "rows": 10,
             "note": "裙摆纵摆：上下滞后，裙底顺带略微张开/收拢（布料的伞效应）",
             "points": [
                 {"c": c, "r": r, "dy": round(v * (1.1 if c == 1 else 1.0), 3),
                  **({"dx": round(v * (-0.32 if c == 0 else 0.32), 3)}
                     if (c != 1 and r >= 8) else {})}
                 for r, v in _SKY.items() for c in (0, 1, 2)
             ]},
        ]
        rig["physics"] += [
            {"id": "side_l_x", "part": "hair_side_l", "driver": "head", "axis": "x",
             "param": "bend_x", "curve": "tip",
             "ratio": 0.55, "stiffness": 46, "damping": 5.4, "max": 7,
             "note": "左侧发第一段：整缕跟着头甩，根固定所以曲线用 tip"},
            {"id": "side_l_tip", "part": "hair_side_l", "driver": "side_l_x",
             "deformer": "side_l_s",
             "ratio": 0.85, "stiffness": 22, "damping": 3.0, "max": 1.0,
             "note": "左侧发第二段（梢）：串在第一段后面，比发根再慢半拍"},
            {"id": "side_r_x", "part": "hair_side_r", "driver": "head", "axis": "x",
             "param": "bend_x", "curve": "tip",
             "ratio": 0.55, "stiffness": 46, "damping": 5.4, "max": 7,
             "note": "右侧发第一段"},
            {"id": "side_r_tip", "part": "hair_side_r", "driver": "side_r_x",
             "deformer": "side_r_s",
             "ratio": 0.85, "stiffness": 22, "damping": 3.0, "max": 1.0,
             "note": "右侧发第二段（梢）"},
            # —— 裙摆（G43）——
            # 照官方 Hiyori 的 physics3：裙子不是"串成多段"，而是**横摆和纵摆两条
            # 独立通道**（「スカート　横揺れ」/「スカート　縦揺れ」）。
            #   横摆 IN = ParamBodyAngleX(X) + ParamBodyAngleZ(Angle)，各 weight 100
            #   纵摆 IN = ParamBodyAngleY(X)，weight 100
            #   两条都不吃头部参数 —— 裙子挂在身上，摇头不该让它动。
            # 纵摆比横摆钝（官方 mobility 0.8/0.9、delay 0.9/0.6），这里体现为
            # 更小的刚度 + 更大的阻尼比。
            #
            # 输入必须是**参数**而不是驱动组：ParamBodyAngleX 绑的是
            # seg_torso.bend_x，弯曲是非仿射的、根本不进组矩阵，拿组位移读不到。
            {"id": "skirt_x", "part": "seg_torso", "deformer": "skirt_sway_x",
             "input": [{"param": "ParamBodyAngleX", "weight": 1.0},
                       {"param": "ParamBodyAngleZ", "weight": 1.0}],
             "ratio": 0.12, "stiffness": 24, "damping": 6.5, "max": 1.0,
             "note": "裙摆横摆：上身左右倾/旋转带动，裙腰不动、裙底甩出去"},
            {"id": "skirt_y", "part": "seg_torso", "deformer": "skirt_sway_y",
             "input": [{"param": "ParamBodyAngleY", "weight": 1.0}],
             "ratio": 0.055, "stiffness": 19, "damping": 6.8, "max": 1.0,
             "note": "裙摆纵摆：上身上下起伏时裙摆滞后一拍，比横摆更钝"},
            {"id": "back_x", "part": "hair_back", "driver": "head", "axis": "x",
             "param": "bend_x", "curve": "tip",
             "ratio": 0.22, "stiffness": 72, "damping": 8.0, "max": 3.5,
             "note": "后发：整团壳只慢半拍地晃一点点（幅度大了会从脸边上露出来）"},
        ]

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
    # 脚拆件（tools/make_foot_parts.py 的产物：常态鞋 + 踮脚鞋各两件）
    footp = None
    foot_path = os.path.join(base, "sprites", "foot_parts.json")
    if seg and os.path.exists(foot_path):
        with open(foot_path, encoding="utf-8") as f:
            footp = json.load(f)
        miss = [a["id"] for a in footp["parts"]
                if not os.path.exists(os.path.join(base, a["file"]))]
        if miss:
            print(f"警告：脚拆件缺图 {miss}，退回\"腿底端拉伸\"的老踮脚", file=sys.stderr)
            footp = None

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
    # 闭眼真素材（tools/make_eye_closed_parts.py 的产物；有它就不用几何眼皮）
    closed = None
    cl_path = os.path.join(base, "sprites", "eye_closed_parts.json")
    if os.path.exists(cl_path):
        with open(cl_path, encoding="utf-8") as f:
            closed = json.load(f)
        if not all(os.path.exists(os.path.join(base, "sprites", c["file"]))
                   for c in closed["eyes"]):
            closed = None

    # 笑眼真素材（make_eye_closed_parts.py --variant smile 的产物）：山型 ∩ 的闭眼
    smile_eyes = None
    sm_path = os.path.join(base, "sprites", "eye_smile_parts.json")
    if os.path.exists(sm_path):
        with open(sm_path, encoding="utf-8") as f:
            smile_eyes = json.load(f)
        if not all(os.path.exists(os.path.join(base, "sprites", c["file"]))
                   for c in smile_eyes["eyes"]):
            smile_eyes = None

    # 眼线二次拆件（tools/make_eyeline_parts.py 的产物）：脸上的眼睛已经挖成眼窝皮肤，
    # 这时眨眼才敢用"压扁眼眶"（底下露出来的是皮肤，不是脸上那只睁着的眼）。
    eyeline = None
    el_path = os.path.join(base, "sprites", "eyeline_parts.json")
    if os.path.exists(el_path):
        with open(el_path, encoding="utf-8") as f:
            eyeline = json.load(f)
        if not eyeline.get("eyes"):
            eyeline = None

    # A7 混合模式零件（tools/make_blend_parts.py 的产物）
    blendp = None
    blend_path = os.path.join(base, "sprites", "blend_parts.json")
    if os.path.exists(blend_path):
        with open(blend_path, encoding="utf-8") as f:
            blendp = json.load(f)
        files = [v["file"] for g in ("blush", "highlight") for v in blendp[g].values()]
        if not all(os.path.exists(os.path.join(base, f)) for f in files):
            print("警告：腮红/高光缺图，跳过混合模式零件", file=sys.stderr)
            blendp = None

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
                seg=seg, anchors=anchors, eyes=eyes, mouth=mouth, lids=lids, armp=armp,
                closed=closed, blendp=blendp, eyeline=eyeline, smile_eyes=smile_eyes,
                footp=footp)
    out = os.path.join(base, "rig.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(rig, f, ensure_ascii=False, indent=2)
    print(f"写出 {out}：部件 {len(rig['parts'])} 动作 {len(rig['actions'])} "
          f"区域 {len(rig['regions'])} 组 {len(rig['groups'])}"
          f"{'（分段身体）' if seg else '（单图层身体）'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
