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
import argparse, json, math, os, sys

import attach_geom


AP_MIN = 0.06   # 眼眶开口闭到底时纵向还剩几成（引擎 aperture_min 的默认值也是它）
# 上眼线在闭合度到这个值之前不下滑（引擎 lash_hold）。0.5 = 后半程才滑。
LASH_HOLD = 0.5



# 动作 id → 给人看的名字。少一条不会炸，界面上就显示英文 id。
ACTION_TITLES = {
    "idle": "待机", "breath": "呼吸", "sway": "摇摆", "focus": "专注",
    "nod": "点头", "head_pat": "摸头", "happy": "开心", "sad": "难过",
    "surprised": "惊讶", "hammered": "被锤", "stroke": "抚摸",
    "clicked": "被点", "dragged": "被拖", "talk": "说话", "think": "思考",
    "sleep": "睡觉", "wake": "叫醒",
    "wave": "挥手", "wave_both": "双手挥", "heart_hands": "比心",
    "kirara_jump": "蹦一下", "look_around": "张望", "star_eyes": "星星眼",
    "shift_weight": "换重心", "tiptoe": "踮脚",
    "ear_twitch": "抖耳朵", "tail_swish": "甩尾巴",
}


def _name_actions(actions):
    """给每个动作补上 title。已经自带 title 的不动。"""
    for a in actions:
        if not a.get("title"):
            t = ACTION_TITLES.get(a.get("id", ""))
            if t:
                a["title"] = t
    return actions


def png_size(path):
    """只读 PNG 头部拿宽高（make_rig 跑在系统 python3 上，没有 PIL）。"""
    with open(path, "rb") as f:
        head = f.read(24)
    if len(head) < 24 or head[:8] != b"\x89PNG\r\n\x1a\n":
        return None
    return (int.from_bytes(head[16:20], "big"), int.from_bytes(head[20:24], "big"))


# —— 面部层序表（一处定义，别再散落硬编码）——
#
# 原来 219/222/229/234 这些数字散在两段代码里，各写各的，插一个新件就要人肉
# 找一遍谁和谁撞；2026-10-16 加星形虹膜时发现两只眼的层段**已经没有空位**
# （右眼 229~231 上面紧贴着眉毛 232/233），只能整段重排 —— 所以顺手收口成一张表。
#
# 规则：
#   · 一只眼占 10 个连号（左 216~225 / 右 226~235），插件不用再全表重排；
#   · 同一只眼内部顺序固定：socket < base < ball < ball_star < lid < hl < lash
#     < closed < hl_star < smile；
#   · socket 是遮罩，必须最小（引擎要求遮罩件先画）；
#   · lash 压住 hl（睫毛本来就该盖住高光），closed/smile 压住 lash；
#   · 眉毛被挤到 236/237（make_brow_parts.py 同步改了），刘海仍是 240。
# 眼球微动幅度（归一化视线单位）。标定见 tools/calib_saccade.py。
SACC_AMP = 0.26

# 一只眼的叠放次序（从下往上）。加了两档之后每眼要 12 层，原来的基址 216/226
# 会撞到眉毛（236/237），所以整条带往下挪到 211 起：L 211~222、R 223~234，
# 235 空着、眉毛 236/237 原位不动。层号只受"全局不重复"一条约束（selfcheck 有闸），
# 没有测试硬编码这些数字 —— 挪之前 grep 过 tests/ 和 tools/。
#   wide  夹在 base 和 ball 之间：它顶替的是眼白和上睫毛，虹膜要画在它**上面**
#         （补片里的虹膜已被挖掉，视线还归 eye_*_ball 管）。
#   pain  和 smile 并列放最上：同一条睫毛线的第三种形状（∪ / ∩ / ∧），三选一。
_EYE_ORDER = ("socket", "base", "wide", "ball", "ball_star", "lid",
              "hl", "lash", "closed", "hl_star", "smile", "pain")
FACE_LAYER = {side: {k: b + i for i, k in enumerate(_EYE_ORDER)}
              for side, b in (("l", 211), ("r", 223))}
# ✨ 的层号/混合/标签/动法都搬进 design/effects.json 了（T43.2 / G117）。
# 这里**故意不留** SPARKLE_LAYER0 这类常量：留着就等于源码里还有一份影子配置，
# 改表改不动它，下一个人照着它加漫符就又回到 G117。


# ★★★ Q48：折肘时前臂沿轴线加长多少（1x 画布像素）。
#   参考 wave_up.png 的前/上臂 = 0.87，我们原件是 0.71；前臂 115.8 × 0.22 ≈ 26px
#   补上去正好 141.8/162.4 = 0.873。改这一个数就能整体收放，别在别处再写死。
FORE_LONG_PX = 26.0
# 沿轴加长的行分布（r=0 素材顶边 … r=4 底边）：肘端 0、袖口满额，
# **r=3→r=4 两行同值** ⇒ 袖口那段条纹是刚性平移，不会被拉成椭圆。
FORE_LONG_F = (0.0, 0.15, 0.55, 1.0, 1.0)


def _fore_long_axes(armp):
    """每侧「肘→腕」的单位向量 + 加长量，给 fore_long() 的 hand 组位移用。"""
    out = {}
    if not armp:
        return out
    apart = {q["id"]: q for q in armp.get("parts", [])}
    for side in ("l", "r"):
        fp, hp = apart.get("arm_%s_fore" % side), apart.get("hand_%s" % side)
        if not fp or not hp:
            continue
        ex, ey = fp["pivot"]
        wx, wy = hp["pivot"]
        ln = math.hypot(wx - ex, wy - ey)
        if ln < 1e-6:
            continue
        out[side] = ((wx - ex) / ln, (wy - ey) / ln, FORE_LONG_PX)
    return out


def param_list(mouth=None, has_brows=True, head_is_part=True, jointed_arms=False,
               has_blend=False, has_side=False, has_legs=False,
               body_id="seg_torso", has_eyeballs=False, foot_lift=None,
               star_eyes=None, fx_table=None, hand_forms=None,
               slim_parts=(), long_axes=None,
               elbow_parts=(), gusset_parts=()):
    """角色级命名参数（名字对齐 Live2D 标准参数表）。

    每条 = 一个参数 + 它写到哪些通道；引擎按 `通道值 = 参数值 × scale` 叠在动作之上，
    所以 scale 就是"参数开到最大时这条通道动多少"（像素或度）。
    """
    # ✨ 的颗数：ParamMouthForm 的「笑门」要给每颗各写一条绑定，所以得先知道有几颗。
    fx_table = fx_table or {}
    fx_spark = fx_table.get("sparkle")
    n_sparkle = (len(star_eyes["sparkle"]["instances"])
                 if star_eyes and star_eyes.get("sparkle") else 0)

    def fx_gate_binds(param_id):
        """某个参数作为"门"要挂的特效绑定。系数来自 design/effects.json 的 gates，
        源码里不再出现 2.0 / -1.0 这种字面量 —— 加一种漫符只改表。"""
        out_b = []
        for eff in fx_table.values():
            n = n_sparkle if eff["id"] == "sparkle" else 0
            if not n:
                continue
            for g in eff.get("gates", []):
                if g["param"] != param_id:
                    continue
                out_b += [{"part": f"fx_{eff['id']}_{i}", "param": "alpha",
                           "scale": g["scale"], "offset": g["offset"]}
                          for i in range(1, n + 1)]
        return out_b
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
         "binds": [{"group": "root", "param": "dy", "scale": -7.0}],
         "note": "满格 = 跳起 70px；happy 两段弹跳叠起来是 4.86。"
                 "倍率原来是 −4（满格才 40px），芳文跳写了 −120px 却被**悄悄削成 40px** ——"
                 "实拍鞋底只离地 22px(预览)，和声明的 120 对不上。"
                 "★ 修法是改**倍率**不是改行程：Live2D 标准参数的值域是对外契约"
                 "（外部 .motion3/.exp3 推进来的幅度按 ±10 算），放宽行程等于毁约；"
                 "−4→−7 后满格 70px，动作里写的是像素、换算后自动落在 ±10 内。"
                 "另在 selfcheck 加了「动作幅度不许超出参数行程」拦同类静默削平"},
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
                    # 上唇线的淡出斜率 -3.5：张到 ~29% 时笑线就要彻底消失（alpha 被
                    # zrig 钳在 0..1）。原来是 -0.9，满张时还剩 10%，笑线两端上翘的
                    # 嘴角露在口内椭圆上方，像挂了两撇小胡子（G107）。
                    # 注意：2026-10-15 以前调这个值是**没有效果**的 —— 那时 mouth_open.png
                    # 是一张错位的旧拷贝件（body_full y252..275，而笑线在 y246..250），
                    # 真正的笑线还烙在 seg_head 上。先有 make_mouth_line_cut.py 把笑线
                    # 真正剪下来，这条斜率才管用。
                    "binds": [{"part": "mouth_mask", "param": "sy",
                               "scale": round(0.95 - mouth["closed_sy"], 3)},
                              {"part": "mouth_open", "param": "alpha", "scale": -3.5},
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
                              {"part": "mouth_mask", "param": "sy", "scale": -0.045}]
                              # ✨ 的「笑门」：T39.5 的另一半。商业成品的口径是
                              # 「笑顔で目を見開いたときに」才显示（BOOTH 5711516），
                              # 不是开了星星眼就一直闪。scale 2.0 / offset -1.0 =
                              # 嘴角 0 完全不出、0.25 出一半、>=0.5 满亮（之后夹紧），
                              # 正好覆盖表情的 0.6 与动作 pulse 的 0.8 两条入口。
                              + fx_gate_binds("ParamMouthForm")})
        # 单边嘴角（坏笑 / 不以为然 / 忍笑）。T44.1 盘点的结论是：**不造一对
        # MouthCornerL/R**，照 Animaze《复杂口角形状的 Live2D 模型制作方法》的
        # 扩展参数表走一个 ParamMouthX —— 原文口径是「口角を『クイッ』と上げる
        # ような、左右の位置を調整するパラメータ」，即嘴整体左右偏 + 顺带把偏过去
        # 那侧的嘴角带高，「頬も同様に口の動きに合わせて少し上がるように」。
        # 一个参数办两件事，正好卡住官方"一个表情最多 2 个参数"的负荷惯例。
        #
        # 为什么不能复用 ParamMouthForm（T44.1 第 ⑦ 条）：Form 已经被口型同步
        # 占满了（visemes 里 I=+1.0 / U=-1.0 / O=-0.7 / N=-0.35），而且引擎口径是
        # 口型层覆盖、表情只拿 (1-w) 的余味（src/core/zrig.c viseme 段）——
        # 挂在 Form 上的微表情一说话就被压掉。所以必须自带通道。
        #
        # 符号约定：**+1 = 嘴向画面右移，画面右侧那个嘴角上扬**；-1 反之。
        # 幅度**实测定的**（2026-10-16 做了四档扫描，留证 logs/asset_qa/mouthx_sweep.png）：
        # 平移 ±1.5px + 旋转 ±8°。扫描结论是 **平移越大越像"嘴整个滑到一边"**（是缺陷
        # 不是表情），**抬一侧嘴角全靠旋转**，所以平移压到只够制造"支点在一侧"的错觉。
        # ⚠ 诚实边界：闭嘴时这张脸的嘴只有 16×3 px（466px 帧上），±8° 只改到 29~43 个
        # 像素，缩到真实观看尺寸基本看不出来 —— 见 G121 / T44.3。
        out.append({"id": "ParamMouthX", "label": "嘴 左右（单边嘴角）",
                    "min": -1.0, "max": 1.0, "default": 0.0,
                    "binds": [{"part": "mouth_mask", "param": "dx", "scale": 1.5},
                              {"part": "mouth_mask", "param": "rot_deg", "scale": 8.0},
                              {"part": "mouth_open", "param": "dx", "scale": 1.5},
                              {"part": "mouth_open", "param": "rot_deg", "scale": 8.0},
                              # 脸颊跟着嘴角走：上扬那侧抬、另一侧略沉。
                              # 两侧反号 = 整块颊部随嘴倾斜，这正是真人坏笑的样子，
                              # 不是"两边一起抬"（那是咧嘴笑，归 ParamMouthForm）。
                              {"part": "blush_r", "param": "dy", "scale": -1.6},
                              {"part": "blush_l", "param": "dy", "scale": 1.6}],
                    "note": "单边嘴角：Animaze 扩展参数表 ParamMouthX。"
                            "mouth_cavity 靠 motion_from=mouth_mask 自动跟随，不用单列。"
                            "不要用 ParamMouthForm 代替 —— 那条被口型同步占着"})
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
        #
        # ★ Q36「手臂要能做到所有人类能做到的动作」⇒ 行程按**人体关节活动度**给满，
        #   不是按"现有动作够用"给。旧表 ±10 只到 ±60°，手举不过肩，
        #   芳文跳那种双臂上举成 V 根本做不出来（参数被 clamp 在 10）。
        #   ★ Q36 二改：放宽 min/max 是**错的**，要改的是 scale。
        #   Live2D 标准参数的值域是**对外契约** —— 外部 .motion3/.exp3 把
        #   ParamArmLA 推到 10 就是"举满"。我们把行程改成 ±30，等于告诉外部文件
        #   "推到 10 只有三分之一"，外来动作全部变成半身不遂；selfcheck 的
        #   「标准参数取值范围符合官方惯例」拦的就是这个。
        #   所以：行程回到 ±10，把倍率从 6 提到 18（±10 × 18 = ±180°，同样做得到
        #   芳文跳的双臂上举）。动作源码里写的仍然是"多少度"，GEO2PARAM 自动换算；
        #   只有 test_core 里几条按**参数值**写死的阈值要跟着改单位（已同步）。
        #   医学活动度：肩屈曲/外展 180°、伸展 60°；肘屈曲 145°；腕掌屈 80°/背屈 70°。
        # ★★★ Q38（2026-10-22）袖根塗り足し要**随抬手角度淡出**。
        #
        #   病象：把挥手照参考图改成「整条手臂斜举到 −115°」之后，右腋下挂出一块
        #   青色布片（logs/asset_qa/q38_armpit_vs_ref.png 右格 vs 左格参考图）。
        #   分件染色实拍（q38_flap_tint.png / q38_tint_after.png：红=arm_r_root
        #   黄=arm_r_cap 蓝=arm_r_upper）坐实元凶是 **arm_r_root**。
        #
        #   为什么不能只靠裁几何：`arm_*_root` 挂在 arm_* 组上绕**肩**转，而肩关节
        #   本来就坐在躯干剪影的**边界**上（实测：躯干外的袖根像素最近的离肩只有 5px）。
        #   所以无论把它裁到多小的圆盘，只要抬手角度够大，圆盘朝下那半边就会转到
        #   夹克外面变成一块悬空的布。离线逐角度统计（armsim2）：
        #       半径 52/62（本轮已裁过的）  −40°:554px  −70°:859px  −115°:1975px
        #       半径 36/40（再砍一刀）      −40°:273px  −70°:568px  −115°:1021px
        #   —— 砍几何只能减半，减不掉。
        #
        #   正解是**它本来就不该在那个角度出现**。这件的职责是「手臂转开后补住肩窝、
        #   别让上臂在肩那头细得像根棍子」，那是**小角度**才有的缺口；抬到 90° 以上，
        #   袖子自己的根部已经整个盖住关节了。离线开关对照 q38_root_on_off.png：
        #   0° 开关两版**逐像素相同**（静止时它本来就被躯干压着），−115° 关掉那版
        #   干净利落，和参考图 wave_out.png 的腋下一致。
        #
        #   实现：引擎的部件级 alpha 是**每条绑定各自 clamp 到 [0,1] 再相乘**
        #   （src/core/zrig.c:3460 `p_alpha[part] *= ZC_CLAMP(1.0 + v, 0, 1)`，
        #   v = scale×参数值 + offset），所以一条线性绑定就能做出「平台 + 斜坡」：
        #       角 ≤  8°（参数 0.44）→ 1+v ≥ 1 → clamp 回 1.0，整段不变
        #       角 = 22°（参数 1.22）→ 1+v = 0   → 全透明
        #   解出 scale = −1/(1.22−0.44) = −1.29、offset = −0.44×scale = +0.57。
        #
        #   ★ 窗口为什么收在 8~22°（试了三版才定）：
        #     ① 50~92° 实拍（q38_root_fade_live.png 旧版第三格 −70°）腋下留下一块
        #        **半透明紫斑** —— 袖根淡到 0.52 时和背景混色，成了鬼影；
        #     ② 20~45° 还剩一条淡紫细痕（−32° 那格）；
        #     ③ 逐角度量「袖根真正露在躯干+袖子+肩帽之外的面积」：
        #          0° 0px  −5° 0  −10° 33  −15° 115  −20° 212  −30° 401  −40° 554  −50° 667
        #        半透明只有落在**露出面积≈0**的角度区间才看不见，所以斜坡必须整个
        #        放在 22° 以内：最糟的一帧（15°、alpha 0.5）只有 115px 画布像素
        #        ≈ 35 个预览像素，肉眼无法分辨。
        #     离线小角度对照 q38_root_small_angles.png：−15~−55° 开关两版几乎一样，
        #     有袖根那版下缘反而多一圈锯齿凸起（erode(hidden,2) 啃出来的边）。
        #   ★ 为什么不干脆删掉这件：≤8° 的微动（待机呼吸、look_around 的手臂跟随）
        #     它 100% 被躯干压着，是「转开一点点也绝不露缝」的兜底；真正的代价为零。
        #   两条手臂都是「参数为正 = 抬起」（左臂 scale +18、右臂 −18），所以
        #   同一组系数通用；往身后摆（参数为负）时 v 更大，clamp 后仍是 1.0 —— 
        #   那个方向缺口最大，袖根必须留着。
        #   （若这一形态没切出袖根件，后面 3700 行那段「绑定引用了不存在的部件就剪掉」
        #     的收尾会自动把这条删掉，这里不用再判一次。）
        # ★★★ Q44（2026-10-22 第四十四问）**袖根不再淡出**，和 Q42 撤掉肩帽淡出同理。
        #
        #   旧绑定：alpha = clamp(1 − 1.29·v + 0.57) ⇒ 抬手角 **36.9° 就归零**。
        #   当初（Q38）加它是为了躲"大角度时袖根甩出剪影外的布片"——又一次
        #   **用 alpha 躲几何病**。代价是：唯一能补上臂的那块料，恰好在抬手时被关掉。
        #
        #   用户第四十四问截图「手臂为什么会挥手就变细」，量下来上臂中段只有 44~46px、
        #   前臂 71~93px。两个原因叠在一起：
        #     ① 原画里袖子被白夹克盖住的那一半根本没画（切件天生缺料）；
        #     ② 仅有的那块补料（arm_*_root）被这条 fade 关掉了。
        #
        #   现在 `tools/sleeve_underlay.py` 把袖根重建成了两块**几何上不可能穿帮**的料：
        #     · 肩圆盘内（绕自身圆心旋转不变，且头上还压着静止的肩球 cap）；
        #     · 沿上臂轴的"管内"补料带（跟着袖子一起转，永远就在袖子该在的位置）。
        #   圆盘外、管外的旧料（正是会甩出去的那些）已经丢弃 ⇒ 不需要 alpha 兜底了。
        def root_fade(part_id):
            return []

        # ★★★ Q41（2026-10-22）肩帽 arm_*_cap 也要随抬手角度淡出 —— 和袖根同病同治。
        #
        #   病象：Q40 把挥手从 −115° 抬到 −130° 之后，用户截图一眼看出右腋下挂着
        #   **一块带尖角的薄荷色布片**（logs/asset_qa/q41_user_zoom.png A 格）。
        #   我上一轮只裁了上半身的框去验收，没看全身，漏了。
        #
        #   分件染色实拍坐实元凶（logs/asset_qa/q41_tint_zoom.png，
        #   红=seg_torso 绿=arm_r_root 蓝=arm_r_upper **黄=arm_r_cap**）：
        #   黄色那块整个甩到了夹克剪影外面 —— 肩帽是绕肩转的圆盘，抬手角度一大，
        #   圆盘朝下那半边就转到腋下空档里，和袖根 arm_*_root 是**同一个几何病**
        #   （肩枢轴坐在躯干剪影边界上，见上面 Q38 那段）。
        #
        #   为什么敢淡掉：逐角度做了「有帽 / 无帽」对照（q41_capsweep.png 两行六格）
        #   并量了**无帽时的封闭空洞**（洪水填充判连不到画面边缘的背景像素）：
        #       角度    20°  40°  60°  90° 115° 130°
        #       空洞     9px  7px  7px  8px  6px  7px   ← 全是抗锯齿噪点，没有真洞
        #       帽子探出 78   95   82   47   51   88
        #   —— 20~130° 这一段**肩窝根本不靠它兜**（袖子自己的根部已经盖住了），
        #   它只是在往外贴面积；到 90° 以上就贴成了那块尖角布片。
        #   和袖根一样保留小角度的兜底（Q35 加它是为了小角度转开时别露肩窝），
        #   只把大角度关掉：
        #       角 ≤  80°（参数 4.444）→ 1+v ≥ 1 → clamp 回 1.0，整段不变
        #       角 = 110°（参数 6.111）→ 1+v = 0   → 全透明
        #   解出 scale = −1/(6.111−4.444) = **−0.60**、offset = −4.444×(−0.6) = **+2.667**。
        #   斜坡放在 80~110°：这一段帽子还被袖子压着（露出面积小），半透明看不出来；
        #   往身后摆（参数为负）时 v 更小、clamp 后仍是 1.0，缺口最大的那个方向照常留着。
        # ★★★ Q42：肩帽**不再淡出**。
        #   Q41 给它加过 alpha 淡出（80°满额→110°归零）来躲那块尖角布片，
        #   但 round_arm_sockets.py 之后它已经不是"会被落在外面的扇形"，
        #   而是**静止的肩球**（关节正圆以内 + 枢轴以上的袖料都归它）。
        #   淡掉它 = 把肩头削掉 ⇒ 正是用户第四十二问骂的"肩头内缩"。保持常显。
        def cap_fade(part_id):
            return []

        # ★★★ Q51：肘折线 arm_*_crease 整件删除。
        #   Q44 做它的理由是「前臂近端是新切口、原画那儿没描边，折起来会和
        #   上臂糊成一团」，于是**补了一条线**。第五十一问用户指着截图说这条线
        #   「不应该存在」，REF-FIRST 复核参考图 wave_up.png 的折袖也确实没有：
        #   折袖是一整块连续的布，深色线只在外剪影上。
        #   现在的分工是反过来的 —— tools/elbow_gusset.py 出的褶布件压在
        #   最上面（层 150/151），把折起来之后横躺在袖子中间的描边**盖掉**。
        # ★★★ Q45：前臂「折起时收窄」的网格形变器（ワープデフォーマ）。
        #   用户第四十五问放大图：挥手时前臂是「吊在袖口下面的一只大拳套」。
        #   分件染色实拍（logs/asset_qa/q45_tint.png，前臂染红/上臂染蓝）坐实：
        #     前臂件 116 长 × 75 宽（1.55:1，参考图是 150×55 = 2.7:1），
        #     肘内角 32° 时两根管子的轴线间距只有 34px，而两件半宽加起来 80px
        #     ⇒ **前臂整条盖在上臂上**（上臂只剩 1151px 可见），必然糊成一坨。
        #   几何病要用几何治：折肘时把前臂按轴线**横向收窄**（肘端 0%、袖口 17%），
        #   肘关节那一行一个像素都不动（要和上臂末端的正圆严丝合缝）。
        def fore_slim(part_id):
            if part_id not in (slim_parts or ()):
                return []
            return [{"deformer": part_id + "_slim", "scale": 1.0}]

        # ★★★ Q48：前臂沿轴**加长**（和 fore_slim 同族，一个管粗细一个管长短）。
        #   两条绑定一起走，缺一不可：
        #     ① 形变器 arm_?_fore_long —— 袖管沿肘→腕轴线拉长（肘端 0、袖口满额）
        #     ② hand_? 组 dx/dy      —— 手跟着袖口往外挪同样的距离
        #   手件是前臂组的子组，dx/dy 写在前臂的局部系里（group_matrix 先乘父矩阵），
        #   所以这里填的是**静止姿势下**肘→腕的单位向量 × 位移，折肘后自动跟着转。
        def fore_long(part_id, hand_group, side):
            axis = (long_axes or {}).get(side)
            if not axis or part_id not in (slim_parts or ()):
                return []
            ux, uy, dpx = axis
            return [{"deformer": part_id + "_long", "scale": 1.0},
                    {"group": hand_group, "param": "dx", "scale": round(ux * dpx, 3)},
                    {"group": hand_group, "param": "dy", "scale": round(uy * dpx, 3)}]

        # ★★★ Q48：肘关节补件 arm_*_elbow 的 alpha，也绑肘角。
        #   病根（分件染色 + 离线摆位实测，见 tools/elbow_cover.py 开头）：
        #   round_arm_sockets 把两件在肘处都切成了「以枢轴为心、r≈34.7 的同心半圆」，
        #   **外轮廓没问题**，问题是前臂一转 141°，圆内一半是上臂的料、一半是前臂的料，
        #   内侧两条袖管边线还交成一个尖角 —— 这就是用户说的「折叠一样的痕迹」。
        #   斜坡放在肘角 45°~99°（v 2.5~5.5）：伸直/小角度 0，折到挥手那档 1。
        #   heart_hands 的肘角是负的（−7.3）⇒ 恒为 0，反向折肘时不会冒出来。

        def elbow_fade(part_id):
            if part_id not in (elbow_parts or ()):
                return []
            return [{"part": part_id, "param": "alpha",
                     "scale": 0.3333, "offset": -1.8333}]

        # ★★★ Q50：肘内侧褶布（tools/elbow_gusset.py 出的件）。
        #   参考图 wave_up.png 的折臂是一整块连续的布，我们两根管子之间会漏背景。
        #   这块布垫在两根管子**底下**（层 136/137），挂在 elbow_fold_? 组上
        #   （转角 = 前臂局部转角的一半 = 角平分线），所以永远卡在两管之间。
        #   alpha 比肘补件还晚显形：折到 ~110° 才开始、定稿姿势 (|v|≈7.45) 满。
        #   伸直与小幅度弯肘（打招呼的 idle 摆手）一个像素都不加。
        def gusset_fade(part_id):
            if part_id not in (gusset_parts or ()):
                return []
            return [{"part": part_id, "param": "alpha",
                     # 引擎口径（zrig.c:3463）：alpha = clamp(1 + scale·v + offset)。
                     # 第一版写 0.556/−3.389 ⇒ v=4.3 就开始显、6.1 就满 ——
                     # 实拍 f30(0.50s) 肘才折到 106°、两根管子还没并拢，
                     # 补布直接飘在背景里（q50_wave_after_series.png 第二格）。
                     # 缺口是「两管并拢之后才存在」的东西，所以卡到深折才显：
                     #   v=7.02（肘 126.4°）起 → v=7.15（肘 128.7°）满。
                     # 上沿为什么卡在 7.15：定稿姿势 v=7.45，叠着 ±5° 的
                     # 手摆正弦 ⇒ 稳态 v∈[7.17,7.73]。淡入必须在 7.17 **之前**
                     # 收完，否则举着手的那两秒补布会跟着正弦一闪一闪。
                     # 带宽为什么这么窄：补布的形状是按**定稿折角**量出来的，
                     # 肘每偏离 1°，远端就有 ~2px 探到管子外面。实拍
                     # f38(0.63s) 用 6.75 起步时肘才 125°，一块淡三角直接
                     # 飘在背景里。把起点推到 126.4°（差 8° 以内）+ 远端
                     # 13px 软收 ⇒ 过渡只剩约 1 帧、且是一层淡雾。
                     "scale": 7.692, "offset": -55.0}]

        out += [
            {"id": "ParamArmLA", "label": "左臂 抬起", "min": -10.0, "max": 10.0, "default": 0.0,
             "binds": [{"group": "arm_l", "param": "rot_deg", "scale": 18.0}]
                      + root_fade("arm_l_root") + cap_fade("arm_l_cap"),
             "note": "绕肩旋转，±10 → ±180°（人的肩就是 180°：手能举到头顶正上方）。"
                     "肩关节靠两件东西兜住：① 躯干不留任何袖子像素"
                     "（G102：留了就是一块不跟着转的青色三角）；② `arm_*_root` 袖根塗り足し"
                     "画在躯干底下（G108），转开后补上关节、上臂不至于细得像棍子；"
                     "③ arm_*_cap 肩帽盖住肩窝（Q35）"},
            {"id": "ParamArmRA", "label": "右臂 抬起", "min": -10.0, "max": 10.0, "default": 0.0,
             "binds": [{"group": "arm_r", "param": "rot_deg", "scale": -18.0}]
                      + root_fade("arm_r_root") + cap_fade("arm_r_cap")},
            {"id": "ParamArmLB", "label": "左小臂 弯曲", "min": -10.0, "max": 10.0, "default": 0.0,
             "binds": [{"group": "forearm_l", "param": "rot_deg", "scale": 18.0}]
                      + ([{"group": "elbow_fold_l", "param": "rot_deg", "scale": 9.0}]
                         if "arm_l_gusset" in (gusset_parts or ()) else [])
                      + elbow_fade("arm_l_elbow")
                      + gusset_fade("arm_l_gusset") + gusset_fade("arm_l_seam"),
             "note": "绕肘旋转，±10 → ±180°。"
                     "**这里写的是画面上看见的 2D 投影角，不是解剖屈曲角**："
                     "人的肘屈曲极限 145°，但画里小臂往镜头方向折时有透视缩短，"
                     "正面看见的夹角会超过 145° —— Q38 在参考图 "
                     "characters/xiaoxun/design/pose_ref/wave_up.png 上实测："
                     "肩(455,315)→肘(495,475)→腕(487,352)，投影夹角 170°。"
                     "倍率 14.5（±145°）封顶时这个姿势根本摆不出来，所以提到 18.0；"
                     "动作源码写的仍是度数，GEO2PARAM 自动换算，既有动作角度不变"},
            {"id": "ParamArmRB", "label": "右小臂 弯曲", "min": -10.0, "max": 10.0, "default": 0.0,
             "binds": [{"group": "forearm_r", "param": "rot_deg", "scale": -18.0}]
                      + ([{"group": "elbow_fold_r", "param": "rot_deg", "scale": -9.0}]
                         if "arm_r_gusset" in (gusset_parts or ()) else [])
                      + elbow_fade("arm_r_elbow")
                      + gusset_fade("arm_r_gusset") + gusset_fade("arm_r_seam")},
            # G4c2：手是第三节（绕腕转）。Live2D 标准参数表里就叫 ParamHandL/R。
            {"id": "ParamHandL", "label": "左手腕", "min": -3.2, "max": 3.2, "default": 0.0,
             "binds": [{"group": "hand_l", "param": "rot_deg", "scale": 22.0}],
             "note": "绕腕旋转 ±70°（掌屈 80°/背屈 70°，取小的那头）。"
                     "手件往袖子里续了 16px 的腕柄，柄的半对角 20.6px < 袖口半宽 22.5px，"
                     "**任何角度都缩在袖口里**，所以大角度也不会露腕"},
            {"id": "ParamHandR", "label": "右手腕", "min": -3.2, "max": 3.2, "default": 0.0,
             "binds": [{"group": "hand_r", "param": "rot_deg", "scale": -22.0}]},
            # ★★★ Q45：单侧抬肩。ParamShoulderY 是**双肩共用**（binds 里 arm_l/arm_r/chest
            #   各一条）而且量程只够 ±8px，挥手要抬的是**举手那一侧**、幅度 26px，
            #   所以单开一个。为什么需要它：我们这张原画是「大头短臂」——
            #   整条臂只有 1.0 个头高（参考图 1.6 个），肘贴着身子时手最高只能到肩高。
            #   真人举手打招呼时同侧肩本来就会上提（waterarena「抬手侧肩要略上抬」），
            #   抬 26px（0.1 头高）就把手送到了下巴—锁骨之间，肘还留在身侧。
            #   肩帽 arm_*_cap 挂在 chest 组上、不跟着抬 ⇒ 肩窝不会露（实拍 q45_lift.png）。
            {"id": "ParamShoulderRY", "label": "右肩 上提", "min": -10.0, "max": 10.0,
             "default": 0.0,
             "binds": [{"group": "arm_r", "param": "dy", "scale": -3.0}],
             "note": "只抬右肩，±10 → ±30px；双肩一起抬仍然走 ParamShoulderY"},
            {"id": "ParamShoulderLY", "label": "左肩 上提", "min": -10.0, "max": 10.0,
             "default": 0.0,
             "binds": [{"group": "arm_l", "param": "dy", "scale": -3.0}]},
            # ★★★ Q45：前臂收窄（见上面 fore_slim 的注释）。0 = 原件，1 = 收窄到位。
            #   为什么**不**直接绑肘角 ParamArmRB：heart_hands 的肘角是**负的**
            #   （−7.28），绑上去会让它反过来变胖。折肘的动作自己点名要收窄最稳妥。
            {"id": "ParamForeSlimR", "label": "右前臂 收窄", "min": 0.0, "max": 1.5,
             "default": 0.0, "binds": fore_slim("arm_r_fore"),
             "note": "折肘时前臂横向收窄（肘端不动、袖口收 17%），避免前臂压在上臂上糊成一坨"},
            {"id": "ParamForeSlimL", "label": "左前臂 收窄", "min": 0.0, "max": 1.5,
             "default": 0.0, "binds": fore_slim("arm_l_fore")},
            # ★★★ 2026-10-23 第四十八问：前臂**沿轴加长**。
            #   用户原话：「肘关节的位置有一些折叠一样的痕迹，看起来不是很自然，
            #   而且小臂有一些偏短」。先按要求对着参考模板目视比对
            #   （logs/asset_qa/q48_arm_ab2.png：参考图按头宽 213→109 缩到我们的
            #   尺度，与挥手峰值帧同比例并排）：
            #       参考 wave_up.png  上臂 173 / 前臂 150 ⇒ 前/上 = **0.87**
            #       我们            上臂 162 / 前臂 116 ⇒ 前/上 = **0.71**
            #   —— 前臂相对短 18%，折起来就是「吊在袖口下的一只拳套」。
            #   原画是一条垂着的胳膊，肘的切点由原画决定、改不了；能改的是
            #   **折肘时把前臂沿自己的轴线拉长 26px（+22%）**：116→142 ⇒ 0.87。
            #   这不是歪招：Live2D 的ワープデフォーマ本来就干这个，而且只在折肘
            #   那一刻生效，静止画面一个像素都不动。
            {"id": "ParamForeLongR", "label": "右前臂 伸缩", "min": -1.2, "max": 1.2,
             "default": 0.0, "binds": fore_long("arm_r_fore", "hand_r", "r"),
             "note": "折肘时前臂沿肘→腕轴线拉长 26px（+22%），手件同步外移；"
                     "0 = 原件，静止画面零改动。**负值 = 缩短**，用来做挥手甩过程中的透视收缩（marunaru「前腕を潰して回転軌道を小さくする」）"},
            {"id": "ParamForeLongL", "label": "左前臂 伸缩", "min": -1.2, "max": 1.2,
             "default": 0.0, "binds": fore_long("arm_l_fore", "hand_l", "l")},
        ]
    else:
        out += [
        {"id": "ParamArmLA", "label": "左臂 摆动", "min": -10.0, "max": 10.0, "default": 0.0,
         "binds": [{"part": "seg_arm_l", "param": "bend_x", "scale": -4.0, "curve": "tip"}],
         "note": "手臂只有形变没有肘关节（G4c 未做），上限按 ±40px 给"},
        {"id": "ParamArmRA", "label": "右臂 摆动", "min": -10.0, "max": 10.0, "default": 0.0,
         "binds": [{"part": "seg_arm_r", "param": "bend_x", "scale": 4.0, "curve": "tip"}]},
        # 纵向那一路也要有参数：挥手（wave）这类动作用 bend_y 把手抬起来。
        # 拆了件的形态走肘关节（ParamArmLB/RB = 前臂旋转），没拆件的就只能整条弯。
        {"id": "ParamArmLB", "label": "左臂 抬起（未拆件：整条弯）", "min": -10.0, "max": 10.0,
         "default": 0.0,
         "binds": [{"part": "seg_arm_l", "param": "bend_y", "scale": 4.0, "curve": "tip"}]},
        {"id": "ParamArmRB", "label": "右臂 抬起（未拆件：整条弯）", "min": -10.0, "max": 10.0,
         "default": 0.0,
         "binds": [{"part": "seg_arm_r", "param": "bend_y", "scale": 4.0, "curve": "tip"}]},
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
            {"id": "ParamHipDrop", "label": "胯 下沉（屈膝承重）", "min": -6.0, "max": 6.0,
             "default": 0.0,
             "binds": [{"group": "chest", "param": "dy", "scale": 2.0},
                       {"part": "seg_leg_l", "param": "bend_y", "scale": 2.0, "curve": "root"},
                       {"part": "seg_leg_r", "param": "bend_y", "scale": 2.0, "curve": "root"}],
             "note": "+1 胯下沉 2px、腿顶跟着下来 2px、脚踝 0 —— 和 ParamBaseY 的区别是"
                     "它**不动脚**。上下起伏一律用这条，别用 ParamBaseY。"
                     "行程 Q36 从 ±1 开到 ±6：满格才 2px 的话跳跃的预蹲根本看不出来，"
                     "实拍 ±6（胯沉 12px）腰没撕、裙子跟着沉，是安全的"},
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
            # T46.1 第二段。教程把「揺れが1段しかない」列为"头发看着硬"的头号病因：
            # 「髪全体が棒のように一体で動いていると硬く見える ⇒ 根元と毛先で分けて
            #   2段にすると、毛先が遅れて動くようになり一気に自然になる」
            # （shiroikarasu 症状C 原因1）。后发**最该做多段** —— 多家教程一致：
            # 前髪・横髪は1段で十分、後ろ髪とツインテールは多段（2~3段、长的 4 段）。
            {"id": "ParamHairBackS", "label": "后发 S 形甩动（第二段·发梢）",
             "min": -1.0, "max": 1.0, "default": 0.0,
             "binds": [{"deformer": "back_s", "scale": 1.0}]},
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
    if star_eyes:
        n = len(star_eyes["sparkle"]["instances"])
        # 星星眼开关：一个参数同时做三件事 —— 常态虹膜淡出、星形虹膜淡入、
        # ✨ 开门。alpha 通道在引擎里是**相乘**累加的（apply_chan 的 P_ALPHA），
        # 所以 ✨ 的最终透明度 = 开门(本参数) × 这一颗的生命周期(ParamSparkleN)，
        # 两个参数各管各的，不用再造一个"合成"通道。
        out.append({
            "id": "ParamStarEye", "label": "星星眼 0/1", "min": 0.0, "max": 1.0,
            "default": 0.0,
            "binds": [{"part": "eye_l_ball", "param": "alpha", "scale": -1.0},
                      {"part": "eye_r_ball", "param": "alpha", "scale": -1.0},
                      {"part": "eye_l_ball_star", "param": "alpha",
                       "scale": 1.0, "offset": -1.0},
                      {"part": "eye_r_ball_star", "param": "alpha",
                       "scale": 1.0, "offset": -1.0}]
                     + fx_gate_binds("ParamStarEye"),
            "note": "0 = 常态蓝瞳，1 = 五角星瞳 + 脸周围 ✨；中间值是交叉淡化",
        })
        # 每颗闪光一个参数：0 = 缩到 SPARK_MIN 且全透明，1 = 原尺寸且全亮。
        # scale 的 offset 把基准压到 SPARK_MIN，于是参数就是整条生命周期的进度。
        SPARK_MIN = fx_spark["param"]["min_scale"]
        _pfx = fx_spark["param"]["prefix"]
        _plb = fx_spark["param"]["label"]
        _d0, _d1 = fx_spark["param"]["default_from_phase"]
        for i, inst in enumerate(star_eyes["sparkle"]["instances"], 1):
            g = round(1.0 - SPARK_MIN, 4)
            out.append({
                "id": f"{_pfx}{i}", "label": _plb.replace("{i}", str(i)),
                "min": 0.0, "max": 1.0,
                # 默认值按这一颗的相位错开：别的动作接管时参数停在默认值上，
                # 八颗一样大就又变成"整齐划一"了。
                "default": round(_d0 + _d1 * inst["phase"], 3),
                "binds": [{"part": inst["id"], "param": "alpha",
                           "scale": 1.0, "offset": -1.0},
                          {"part": inst["id"], "param": "sx",
                           "scale": g, "offset": -g},
                          {"part": inst["id"], "param": "sy",
                           "scale": g, "offset": -g}],
                "note": f"{inst['size_class']}；idle / star_eyes 里以 "
                        f"freq={inst['freq']} phase={inst['phase']} 驱动",
            })
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
    if hand_forms:
        # ★ Q36 手の差分。官方口径（sites.google.com/cybernoids.jp … animator_arms_mtn）：
        #   「腕や手の差分は**パーツ表示切替**で」—— 手不是靠扭变形器掰出来的，
        #   是**另画一只手换上去**。castcraft.live/blog/464 的做法是切换参数 0→1、
        #   每档不透明度 0%/100%。
        #   引擎的 alpha 通道是**相乘**的（apply_chan 的 P_ALPHA：p_alpha *= 1+v）：
        #   差分件基础 opacity=1，先用 offset −1 压成全透明，参数开到 1 才浮出来；
        #   同一个参数再给常态手挂一条 scale −1，于是任何时刻**只有一只手可见**。
        LBL = {"open": "张开（挥手/打招呼）", "heart": "比心", "fist": "握拳"}
        for form in hand_forms:
            for side in ("l", "r"):
                out.append({
                    "id": f"ParamHand{side.upper()}{form.capitalize()}",
                    "label": ("左手 " if side == "l" else "右手 ") + LBL.get(form, form),
                    "min": 0.0, "max": 1.0, "default": 0.0,
                    "binds": [{"part": f"hand_{side}_{form}", "param": "alpha",
                               "scale": 1.0, "offset": -1.0},
                              {"part": f"hand_{side}", "param": "alpha", "scale": -1.0}],
                    "note": "0=常态手，1=这一档；动作里用 pulse 整段拉满（官方：不要在动作中途切手）",
                })
    if has_legs:
        # ★ Q36 腿脚**真关节**。在这之前 leg_*/foot_* 四个组虽然在骨骼树里，
        #   却没有任何参数绑它们的 rot_deg —— 腿只会「网格弯曲」（bend_x/bend_y），
        #   髋和踝是死的。人的腿是「髋→膝→踝」三节，少了髋的回转，
        #   抬腿、踢腿、跳跃收腿全做不出来。
        for side in ("l", "r"):
            sidecn = "左" if side == "l" else "右"
            out.append({
                "id": f"ParamHip{side.upper()}", "label": f"{sidecn}髋 前后摆",
                "min": -10.0, "max": 10.0, "default": 0.0,
                "binds": [{"group": f"leg_{side}", "param": "rot_deg", "scale": 0.9}],
                "note": "整条腿绕髋回转 ±9°；正=往画面右摆。裙子盖着髋，角度再大会露接缝",
            })
            out.append({
                "id": f"ParamAnkle{side.upper()}", "label": f"{sidecn}踝 回转",
                "min": -10.0, "max": 10.0, "default": 0.0,
                "binds": [{"group": f"foot_{side}", "param": "rot_deg", "scale": 1.2}],
                "note": "脚掌绕踝 ±12°：跳跃绷脚尖、落地勾脚",
            })
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


# 表情里的 ParamEyeOpen 一律用 **multiply**，不许用 set（2026-10-16）。
#   set 会把这个参数钉死，眨眼驱动再也推不动它 —— 实测挂上任一表情之后
#   /api/blink?v=1 完全没反应，小寻从此一眼不眨（logs/asset_qa/smile_blink.png）。
#   multiply 是 Live2D expression3 的标准三种模式之一（zrig.c:1818 认 add/set/multiply）：
#   「微笑时眯一点」= 乘 0.85，睁着时 1.0×0.85=0.85，眨眼压到 0 时 0×0.85=0 —— 照样闭得上。
#   闸门：selfcheck「表情不许把眼睛开合钉死」。
def expression_list(mouth=None, has_brows=True, head_is_part=True, has_blend=False,
                    has_smile_eyes=False, has_star=False,
                    has_pain_eyes=False, has_wide_eyes=False):
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
         "params": brows(0.25, 0.25, lf=0.3, rf=0.3) + mform(0.7) + [P("ParamEyeOpen", 0.85, "multiply")]
                   + blush(0.22) + sparkle(0.75)},
        {"id": "shy", "name": "害羞", "fade": 0.35,
         "params": brows(-0.3, -0.3, -0.6, -0.6, lf=-0.3, rf=-0.3) + mform(0.35)
                   + [P("ParamEyeOpen", 0.7, "multiply")]
                   + blush(0.95) + sparkle(0.8)
                   + ([P("ParamAngleZ", -4.0)] if head_is_part else [])},
        {"id": "angry", "name": "生气", "fade": 0.22,
         "params": brows(-0.7, -0.7, -0.8, -0.8, lf=-1.0, rf=-1.0) + mform(-0.7)
                   + [P("ParamEyeOpen", 0.9, "multiply")] + blush(0.45) + sparkle(0.3)},
        {"id": "sad", "name": "难过", "fade": 0.4,
         "params": brows(-0.45, -0.45, 0.7, 0.7, lf=-0.55, rf=-0.55) + mform(-0.5)
                   + [P("ParamEyeOpen", 0.75, "multiply")] + blush(0.0) + sparkle(0.18)},
        {"id": "surprise", "name": "吃惊", "fade": 0.12,
         "params": brows(0.9, 0.9, lf=1.0, rf=1.0) + mopen(0.55)
                   + [P("ParamEyeBallY", -0.15)]
                   # 真·瞪大眼（Live2D 标准 ParamEyeLWide/RWide）：换一张眼眶开得更大的
                   # 补片，虹膜**保持原尺寸**。2026-10-15 验收「眼球不自然变大像个怪物」
                   # 说的就是反过来做（把虹膜吹大）的下场，不能再犯。
                   + ([P("ParamEyeLWide", 1.0, "set"), P("ParamEyeRWide", 1.0, "set")]
                      if has_wide_eyes else [])
                   + sparkle(1.0)},
        {"id": "sleepy", "name": "困倦", "fade": 0.5,
         "params": brows(-0.2, -0.2) + mopen(0.15)
                   + [P("ParamEyeOpen", 0.3, "multiply"), P("ParamEyeBallY", 0.2)]
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
    # 痛（>_<）：倒 V 闭眼 + 眉头压低 + 嘴角下撇。被戳/被捶时用。
    if has_pain_eyes:
        out.append(
            {"id": "pain", "name": "痛（>_<）", "fade": 0.14,
             "params": brows(-0.85, -0.85, -0.5, -0.5, lf=-0.9, rf=-0.9) + mform(-0.8)
                       + mopen(0.25)
                       + [P("ParamEyeLPain", 1.0, "set"), P("ParamEyeRPain", 1.0, "set")]
                       + blush(0.5) + sparkle(0.2),
             "note": "痛苦闭眼：闭眼线的第三种形状（∪ / ∩ / ∧），口径同笑眼"})
    # 星星眼（T39）：**状态型**表情 —— 设上就一直是星星眼，直到切别的表情或 off。
    # 想要"亮一下再收回去"的那种演出，用同名动作（/api/action?id=star_eyes）。
    # 这里只把眼睛那一摊设满，嘴和脸红给得克制，这样它能和 happy/shy 叠着用。
    if has_star:
        out.append(
            {"id": "star_eyes", "name": "星星眼", "fade": 0.25,
             "params": brows(0.4, 0.4, lf=0.5, rf=0.5) + mform(0.6)
                       + [P("ParamStarEye", 1.0, "set"),
                          P("ParamEyeBallForm", 0.3)]
                       + blush(0.4) + sparkle(1.0),
             "note": "L1 星形瞳 + L2 眼内碎钻（画进贴图）+ L3 脸周围 ✨；"
                     "✨ 的闪烁由 idle 的 ParamSparkle1..N 驱动。"
                     "这里**故意不写 ParamEyeOpen** —— 见下方注释"})
        # 为什么表情里不能 set ParamEyeOpen=1（2026-10-16 真机踩出来的）：
        # 表情是**状态**，挂上去就一直生效。拿 "set" 把 ParamEyeOpen 钉在 1，
        # 眨眼驱动就再也推不动它了 —— 实测挂上星星眼之后 /api/blink?v=1 完全
        # 没反应，小寻从此一眼不眨地瞪着你（logs/asset_qa/star_eye_blink.png
        # 的 star_shut 格和 star_open 格一模一样）。用户上一轮打回惊讶表情的
        # 原话就是「看着像个怪物一样很怪」，一个永不眨眼的状态正是同一类毛病。
        # 「睁大眼」确实是星星眼的一部分（booth.pm/ja/items/5711516：
        # 笑顔で目を見開いたときに），但那是**一瞬间**的演出，归动作管 ——
        # 动作 star_eyes 只持续 3.4 秒，在那 3.4 秒里钉住 EyeOpen 没有副作用。
    return out


def attach_emit(rig, base, base_root):
    """把挂件（耳饰 / 尾饰 / 装饰品）挂进 rig（A49 / T45）。

    口径完全延续 T43.2 的特效表：**层号、父组、锚点、曲线、物理系数、开关参数
    全部来自 design/attachments.json，本函数一个字面量都不持有**。
    加一个挂件 = 表里加一条 + 放一张素材，不改这个文件。

    几何来自 sprites/attach_parts.json（切件器 make_attach_parts.py 的产物，
    带成品的真实宽高）；语义来自 design/attachments.json。两份都在才挂 ——
    整组可选，缺了就当没这回事，其余一切照旧（差分件该有的性质）。

    ★ 为什么挂件不能复用 ✨ 那条路径：✨ 是**散布型**，一张素材铺 N 片、
    不接物理、只被情绪门控开关；挂件是**一件一个部件**，要接物理链和网格
    形变器，还要跟着父组一起动。两者只有「键色 + 重铺」那一段是共用的。
    """
    ap = os.path.join(base, "sprites", "attach_parts.json")
    tp = os.path.join(base_root, "design", "attachments.json")
    if not (os.path.exists(ap) and os.path.exists(tp)):
        return
    with open(ap, encoding="utf-8") as f:
        cut = json.load(f)
    with open(tp, encoding="utf-8") as f:
        table = json.load(f)
    # 形态级锚点 + 画布居中偏移：挂件几何是**相对这个形态的头高/身高**表达的
    # （T2.2.0）。同一张角色级挂件表要能套在 teen/loli/adult/chibi 四个形态上 ——
    # 写绝对像素的话，照少女量的 [364,178] 放到 chibi（头身比 1:2.5）上平均偏
    # 92 画布像素，而画布总高才 1360，也就是「完全不在身上」。
    anchors = attach_geom.load_anchors(os.path.join(base, "design"))
    _ovr = attach_geom.load_overrides(os.path.join(base, "design"))
    _bp = os.path.join(base, "sprites", "body_parts.json")
    _ox = _oy = 0
    if os.path.exists(_bp):
        with open(_bp, encoding="utf-8") as f:
            _sz = json.load(f)["image_size"]
        _ox, _oy = attach_geom.canvas_offset(
            (rig["canvas"]["w"], rig["canvas"]["h"]), _sz)
    slots = {x["id"]: x for x in table["slots"]}
    geom = {x["id"]: x for x in cut["attachments"]}
    flick_extra = []     # wave=flick 的挂件参数：只偶尔抽一下，不进 ambient

    for att in table["attachments"]:
        g = geom.get(att["id"])
        if g is None:
            print(f"警告：挂件 {att['id']} 没有切件产物，跳过", file=sys.stderr)
            continue
        if not os.path.exists(os.path.join(base, g["file"])):
            print(f"警告：挂件 {att['id']} 缺图 {g['file']}，跳过", file=sys.stderr)
            continue
        slot = slots[att["slot"]]          # 没有兜底：槽不存在就 KeyError 当场炸
        pid = f"acc_{att['id']}"
        w, h = g["size"]

        # —— 部件 ——（@2x 走 DC48 的末尾高清口径：文件指 @2x，scale 减半）
        hi = g["file"].replace(".png", "@2x.png")
        use_hi = os.path.exists(os.path.join(base, hi))
        rig["parts"].append({
            "id": pid,
            "file": hi if use_hi else g["file"],
            "group": slot["group"],
            "layer": int(att.get("layer", slot["layer"])),
            "pos": attach_geom.resolve(
                attach_geom.apply_overrides(att, _ovr), anchors, _ox, _oy)[0],
            # 锚点与曲线可以被**挂件自己**覆盖：同一个槽里，垂下的尾巴尾根在顶边、
            # 竖起的尾巴尾根在底边，曲线也必须跟着反过来（tip ↔ root）。
            "anchor": list(att.get("anchor", slot["anchor"])),
            "tags": list(att.get("tags", [])),
            "note": f"{att.get('label', att['id'])}（挂件，槽 {att['slot']}）："
                    f"{slot.get('note', '')}",
            "scale_1x": 1.0,
            **({"scale": 0.5, "hires": 2} if use_hi else {}),
        })

        # —— 开关参数 ——（DC59 差分件口径：min0 / max1，0=摘掉 1=戴上）
        # ★ 进了 pose 互斥组的挂件**不发**这条参数：显隐归姿态组管
        #   （`/api/pose?group=X&id=none` 整组关掉），再发一条就是两套开关打架，
        #   而且三个姿态 deepcopy 出来会撞同一个参数 id。
        # 进了互斥组的挂件没有开关参数（显隐归姿态组管），表里也就不必写 param。
        pr = att.get("param")
        if att.get("pose_group"):
            pr = None
        if pr:
            rig["params"].append({
                "id": pr["id"], "label": pr["label"],
                "min": 0.0, "max": 1.0, "default": float(pr["default"]),
                "binds": [{"part": pid, "param": "alpha",
                           "scale": 1.0, "offset": -1.0}],
                "note": "挂件开关：0 = 摘掉、1 = 戴上。走 DC59 差分件口径，"
                        "不是把部件删掉而是把不透明度压到 0。"
                        "★ offset 必须是 −1：引擎的 alpha 是**乘性**的 —— "
                        "zrig.c:2764 `p_alpha *= clamp(1.0 + v, 0, 1)`。"
                        "少了 offset 时 v=参数值∈[0,1] ⇒ 因子 clamp(1..2)≡1，"
                        "开关怎么拨都摘不掉。配方见 zrig.c:1305 的注释："
                        "scale 1 + offset −1 ⇒ 透明度 = 参数值。",
            })

        # —— 自主摆动（T45.2b）——
        # 本引擎物理输出的是**滞后量**（zrig.c:3013 `pos - target`），不是摆角，
        # 所以慢输入（呼吸 0.28Hz）推不出位移 —— 实测只有 0.3px。
        # 「自己动」必须有驱动源：一条参数 + 动作通道的慢正弦，
        # 物理链在它**之上**再叠二次滞后（梢比根慢半拍）。
        sw = att.get("swing")
        if sw:
            swp = sw["param"]
            # 形变器是可选的：尾巴有（S 形鞭动），耳朵没有（只需要绕耳根转）。
            binds = []
            _dfm = (att.get("physics") or {}).get("deformer")
            if _dfm and sw.get("deformer_scale"):
                # tip_lag：形变器（= 尾巴**梢**）读的是参数 lag 秒**之前**的值。
                # 动画教科书的 wave principle —— 尾巴分段、每段比上一段延迟
                # 2~3 帧，相位差 φ=2πfΔt。根和梢同相位推 = 僵硬的钟摆；
                # 错开之后形状在 C 形和 S 形之间来回变，这才是「柔软」的来源。
                # 做在时域而不是写死一个相位偏移：相位偏移只对正弦成立，
                # 而自发抽动是非周期脉冲，时域延迟对任何波形都对。
                _b = {"deformer": _dfm["id"], "scale": float(sw["deformer_scale"])}
                if sw.get("tip_lag"):
                    _b["lag"] = float(sw["tip_lag"])
                binds.append(_b)
            if sw.get("root_rot_deg"):
                binds.append({"part": pid, "param": "rot_deg",
                              "scale": float(sw["root_rot_deg"])})
            if not binds:
                raise SystemExit(f"[make_rig] 挂件 {att['id']} 的 swing 一条绑定都没有")
            mo = sw["motion"]
            # ★ 值域要按 mood_swing 的**最大幅度倍率**撑开，不能照抄表里写的 ±1。
            #   摆动的基准幅度本来就顶着 ±1，情绪想把它放大 1.8 倍时会被 clamp 削平 ——
            #   实测：表里 angry amp×1.8 / think amp×2.2，探针量出来都是 ×1.00，
            #   而所有 <1 的倍率（0.5/0.6/0.9）都正常。**只有放大那一侧坏了**，
            #   这种"一半对一半错"的症状最容易被当成生效了。
            #   bias 不参与缩放，所以中心点取 bias，上下各留 amp×最大倍率。
            _amax = max([1.0] + [float(v[1]) for k, v in
                                 (table.get("mood_swing") or {}).items()
                                 if not k.startswith("_")
                                 and isinstance(v, (list, tuple)) and len(v) >= 2])
            # 自发抽动（tail_flick）也要算进值域 —— 它是**叠加**在摆动之上的，
            # 顶到 clamp 就会被削平（T45.2f 刚栽过：放大倍率全被削成 ×1.00，
            # 而且缩小的那一半还是对的，症状是"一半对一半错"，极难发现）。
            # ×1.35：引擎每起一下还会再抖 ±35%，峰值按**上界**留。
            _fmax = max([0.0] + [float(v[2]) for k, v in
                                 (table.get("tail_flick") or {}).items()
                                 if not k.startswith("_")
                                 and isinstance(v, (list, tuple)) and len(v) >= 4])
            _fa = _fmax * float(sw.get("flick_scale", 1.0)) * 1.35
            # wave=flick 的件没有 ambient 周期波，自然也没有 bias/freq：
            # 值域只需覆盖"抽一下"的峰值。
            if mo["wave"] == "flick":
                _b, _a = 0.0, 0.0
            else:
                _b, _a = float(mo["bias"]), abs(float(mo["amp"])) * _amax
            _lo = min(float(swp["min"]), _b - _a - _fa) - 0.05
            _hi = max(float(swp["max"]), _b + _a + _fa) + 0.05
            rig["params"].append({
                "id": swp["id"], "label": swp["label"],
                "min": round(_lo, 3), "max": round(_hi, 3),
                "default": float(swp["default"]),
                "binds": binds, "note": sw["note"]})
            # ★ 摆动通道进 **ambient**，不进任何动作（T45.9）。
            #   以前写进 idle.channels，实测的后果：待机动作有四个会轮换，
            #   切到 breath 时裙摆幅度直接 0.0000、尾巴只剩身体带动；
            #   而且动作通道按"动作内经过时间"求值，一换动作相位就跳回原点。
            #   环境摆动按绝对时刻求值，动作怎么切都连续。
            #   swing.motion.action 保留只为向后兼容，这里只校验它存在。
            if not any(x["id"] == mo["action"] for x in rig["actions"]):
                raise SystemExit(f"[make_rig] 挂件 {att['id']} 的 swing.motion.action="
                                 f"{mo['action']!r} 在 actions 里不存在")
            # wave=flick ⇒ 这条不是"一直在摆"，而是"偶尔抽一下"，
            # 交给 tail_flick 那套机制（各参数独立排班、每下的力度/时长/方向都抖）。
            # 为什么要分两条路：ambient 是无限循环的**周期**波，表达不了"偶发"；
            # 猫耳曾经硬用 pulse 波去凑，结果 freq 没人读、值冲到 0.14 就永远卡住
            # （实测 30 秒纹丝不动）。现在引擎在加载时会直接拒绝 ambient 里的 pulse/decay。
            if mo["wave"] == "flick":
                flick_extra.append(swp["id"])
            else:
                rig.setdefault("ambient", []).append({
                    "target": swp["id"], "wave": mo["wave"],
                    "amp": float(mo["amp"]), "bias": float(mo["bias"]),
                    "freq": float(mo["freq"])})

        if att.get("pose_group"):
            pg = next((x for x in table.get("pose_groups", [])
                       if x["id"] == att["pose_group"]), None)
            if pg is None:
                raise SystemExit(f"[make_rig] 挂件 {att['id']} 指向不存在的 "
                                 f"pose_group {att['pose_group']!r}")
            grp = next((x for x in rig.setdefault("poses", [])
                        if x["id"] == pg["id"]), None)
            if grp is None:
                grp = {"id": pg["id"], "fade": float(pg["fade"]),
                       "default": pg["default"], "entries": [], "note": pg["note"]}
                # 情绪 → 档位（T45.2d）。表在 attachments.json 的 mood_pose 里，
                # 这里只是搬运；引擎按它在 zpet_express() 里自动切。
                mp = (table.get("mood_pose") or {}).get(pg["id"])
                if mp:
                    grp["mood_map"] = {k: v for k, v in mp.items()
                                       if not k.startswith("_")}
                rig["poses"].append(grp)
            ent = next((e for e in grp["entries"]
                        if e["id"] == att["pose_id"]), None)
            if ent is None:
                ent = {"id": att["pose_id"], "parts": []}
                grp["entries"].append(ent)
            ent["parts"].append(pid)

        ph = att.get("physics")
        if not ph:
            continue

        # —— 网格形变器 ——
        # 表里只给每一行的振幅 amp[]，逐点展开在这里做：整条一起平移会像根棍子，
        # 分行反向才有鞭感（和呆毛 ahoge_s / 侧发 side_l_s 同一套写法）。
        # 单张网格写 deformer，多张写 deformers（长发是 3 段：根走部件 bend、
        # 中段和发梢各一张网格）。★ 同一部件上的多张网格**必须同尺寸** ——
        # 引擎是逐点相加后再采样的，尺寸不符直接拒载整份 rig（教训 191）。
        dfms = ph.get("deformers") or ([ph["deformer"]] if ph.get("deformer") else [])
        if len({(d["cols"], d["rows"]) for d in dfms}) > 1:
            raise SystemExit(
                f"[make_rig] 挂件 {att['id']} 的多张网格尺寸不一样："
                f"{[(d['id'], d['cols'], d['rows']) for d in dfms]} —— "
                f"同一部件上的网格要逐点相加，必须同尺寸")
        for dfm in dfms:
            amp = dfm["amp"]
            if len(amp) != dfm["rows"] + 1:
                raise SystemExit(
                    f"[make_rig] 挂件 {att['id']} 的 deformer.amp 有 {len(amp)} 项，"
                    f"rows={dfm['rows']} 需要 {dfm['rows'] + 1} 项"
                    f"（网格是 rows+1 条横线）")
            rig["deformers"].append({
                "id": dfm["id"], "part": pid,
                "cols": dfm["cols"], "rows": dfm["rows"],
                "note": dfm["note"],
                "points": [{"c": c, "r": r, "dx": round(float(v), 3)}
                           for r, v in enumerate(amp)
                           for c in range(dfm["cols"] + 1) if abs(v) > 1e-9],
            })

        # —— 物理链 ——
        # 第一段的 driver 是父组；后面每段的 driver 是上一段的 id
        # （zrig.c:210 多段摆 G16：driver 写另一条 physics 的 id 时，
        #   输入就是上一段的输出，而且下标必须比自己小，所以顺序不能乱）。
        # —— 物理 2.0 的摆链（T47.2）——
        # 挂件表里写 "chain" 就走新内核（输出摆角），写 "segments" 走旧的弹簧摆。
        # 两边可以并存一阵子（DC67），但同一个部件别同时挂两套，会叠加。
        ch_ = ph.get("chain")
        if ch_:
            ent = {"id": ch_["id"], "part": pid}
            if "driver" in ch_:
                ent["driver"] = ch_["driver"]
            for k in ("input", "angle_input", "input_max", "input_rate"):
                if k in ch_:
                    ent[k] = ch_[k]
            ent["particles"] = ch_["particles"]
            outs = []
            for o_ in ch_["outputs"]:
                e = dict(o_)
                # 部件通道要带形变曲线：和旧摆一样，取挂件/插槽声明的那条
                if "param" in e and "curve" not in e:
                    e["curve"] = att.get("curve", slot["curve"])
                outs.append(e)
            ent["outputs"] = outs
            ent["note"] = ch_["note"]
            rig.setdefault("physics2", []).append(ent)

        for seg_ in ph.get("segments", []):
            e = {"id": seg_["id"], "part": pid}
            # input（参数直驱）优先于 driver（跟某个组）—— 引擎也是这个优先级
            # （zrig.c:1050「有它就不看 driver」）。悬垂挂件靠它混入呼吸，
            # 这样静止时也一直在晃（社区做法，见 attachments.json 的 note）。
            if "input" in seg_:
                e["input"] = seg_["input"]
            else:
                e["driver"] = seg_["driver"]
            if "axis" in seg_:
                e["axis"] = seg_["axis"]
            if "param" in seg_:
                e["param"] = seg_["param"]
                e["curve"] = att.get("curve", slot["curve"])
            if "deformer" in seg_:
                e["deformer"] = seg_["deformer"]
            e.update({k: seg_[k] for k in ("ratio", "stiffness", "damping", "max")})
            e["note"] = seg_["note"]
            rig["physics"].append(e)

    # 情绪 → 参数值（T45.3）。和 blink.mood_rate（T44.2）、poses[].mood_map（T45.2d）
    # 并列的第三张情绪表。只搬运，不在这里解释语义。
    mps = table.get("mood_params") or {}
    known = {p["id"] for p in rig["params"]}
    out = {}
    for pid_, m in mps.items():
        if pid_.startswith("_"):
            continue
        if pid_ not in known:
            raise SystemExit(f"[make_rig] mood_params 提到了不存在的参数 {pid_!r}")
        out[pid_] = {k: float(v) for k, v in m.items() if not k.startswith("_")}
    if out:
        rig["mood_params"] = out

    # pose_groups[].extra_parts（T45.10）：把**既有部件**也塞进某个档位。
    # 用处：兜帽戴上时呆毛要消失（教程「帽子をかぶったらアホ毛を消す」）。
    # 做成互斥组的一个档位，而不是另写一条「戴上→关呆毛」的联动规则 ——
    # 联动规则是第二个需要同步的地方，迟早会和本体对不上（死表那一类病）。
    for _pg in table.get("pose_groups", []):
        _ex = _pg.get("extra_parts")
        if not _ex:
            continue
        _grp = next((x for x in rig.get("poses", []) if x["id"] == _pg["id"]), None)
        if _grp is None:
            raise SystemExit(f"[make_rig] pose_group {_pg['id']!r} 写了 extra_parts，"
                             f"但这个组里一个挂件都没有（组不会被建出来）")
        for _eid, _parts in _ex.items():
            for _p in _parts:
                if not any(x["id"] == _p for x in rig["parts"]):
                    raise SystemExit(f"[make_rig] pose_group {_pg['id']!r} 的 "
                                     f"extra_parts 引用了不存在的部件 {_p!r}")
            _ent = next((e for e in _grp["entries"] if e["id"] == _eid), None)
            if _ent is None:
                _ent = {"id": _eid, "parts": []}
                _grp["entries"].append(_ent)
            _ent["parts"] += [p for p in _parts if p not in _ent["parts"]]

    # pose_groups[].hide_parts（T46.3 第二版）：这一档生效时要**藏起来**的既有部件。
    # extra_parts 是"这一档多显示谁"，hide_parts 是"这一档要收走谁"。
    # 为什么两者都要：侧发（hair_side_l/r）在 bob 和 long 两档里都得露，
    # 而官方 pose3.json 的语义下**一个部件只能归一个档位** —— 照官方做就得把
    # 同一绺侧发复制成两份美术资源。藏的写法避免了复制，引擎侧见 pose_opacity。
    for _pg in table.get("pose_groups", []):
        _hd = _pg.get("hide_parts")
        if not _hd:
            continue
        _grp = next((x for x in rig.get("poses", []) if x["id"] == _pg["id"]), None)
        if _grp is None:
            raise SystemExit(f"[make_rig] pose_group {_pg['id']!r} 写了 hide_parts，"
                             f"但这个组里一个挂件都没有（组不会被建出来）")
        for _eid, _parts in _hd.items():
            # ★ 和 extra_parts 不同，这里**允许本形态没有这个部件**：
            #   hide 说的是"这一档要把谁收走"，而 chibi 这类简化形态本来就没有侧发，
            #   没有的东西不用收。硬报错会逼着每个形态维护一份自己的 hide 名单
            #   （那就是 G117 要消灭的"第二份会长歪的表"）。
            _have = [p for p in _parts if any(x["id"] == p for x in rig["parts"])]
            _miss = [p for p in _parts if p not in _have]
            if _miss:
                print(f"  ⚠ 本形态没有 {_miss} —— 档位 {_eid!r} 的 hide 名单跳过它们")
            if not _have:
                continue
            _parts = _have
            _ent = next((e for e in _grp["entries"] if e["id"] == _eid), None)
            if _ent is None:
                _ent = {"id": _eid, "parts": []}
                _grp["entries"].append(_ent)
            _ent.setdefault("hide", [])
            _ent["hide"] += [p for p in _parts if p not in _ent["hide"]]
            # 同一档位不许既显示又藏同一个部件（自相矛盾，引擎会乘出 w(1-w)）
            _bad = sorted(set(_ent["hide"]) & set(_ent.get("parts", [])))
            if _bad:
                raise SystemExit(f"[make_rig] pose_group {_pg['id']!r} 的档位 "
                                 f"{_eid!r} 既显示又隐藏同一个部件：{_bad}")

    # 情绪 → 摆动倍率（T45.2f）。**第四张情绪表**。
    # ★ 这张表以前写在 design/attachments.json 里但**这里没有搬运代码** ——
    #   生成器不读、rig 里没有、引擎不认识。它是一张死表：看着像配置，
    #   实际只起到注释作用，「生气时尾巴快速甩」「专注时慢而大」从没交付过。
    #   发现靠 tools/probe_swing.c：11 种情绪跑出来峰峰值全是 6.4、频率全是 0.21Hz。
    #   ⇒ 教训：设计表加了新顶层字段，必须同时确认**生成器搬运 + 引擎解析 + 闸门盯着**
    #     三处都有，否则就是在 JSON 里写日记。selfcheck 的 check_mood_swing 就是那道闸。
    msw = table.get("mood_swing") or {}
    swing_ids = [pr["id"] for pr in rig["params"]
                 if pr["id"].endswith("Swing") and pr["id"].startswith("ParamAcc")]
    moods = {k: [float(v[0]), float(v[1])]
             for k, v in msw.items()
             if not k.startswith("_") and isinstance(v, (list, tuple)) and len(v) >= 2}
    if swing_ids and moods:
        rig["mood_swing"] = {
            "params": sorted(swing_ids),
            "moods": moods,
            "_note": "情绪 → [频率倍率, 幅度倍率]。只乘 amp 不乘 bias；"
                     "切换时引擎做相位补偿（zrig.c zrig_apply_mood_swing）。"
                     "查不到的情绪不动 —— 和另外三张情绪表同口径。",
        }

    # 情绪 → 自发抽动（T45.2g）。**第五张情绪表**。
    # mood_swing 改的是"摆动长什么样"，这张改的是"它多久自己动一次、动多狠"。
    # 为什么非要有：一条定频定幅的正弦，60 秒 12 个峰幅度标准差 0.000015° ——
    # 那是节拍器。行为学上摆尾是阵发事件（de Mouzon 2023：被忽视时平均摆
    # 13.98 秒，被搭理时 0.39 秒），所以"自己决定什么时候甩"必须单独做。
    tfl = table.get("tail_flick") or {}
    flick_moods = {k: [float(v[0]), float(v[1]), float(v[2]), float(v[3])]
                   for k, v in tfl.items()
                   if not k.startswith("_")
                   and isinstance(v, (list, tuple)) and len(v) >= 4}
    # 每条参数自己的力度系数：四种姿态的 root_rot_deg 差 14 倍，
    # 同一个 amp 直接套会让竖起的尾巴抽出去半屏。
    fsc = {a["swing"]["param"]["id"]: float(a["swing"].get("flick_scale", 1.0))
           for a in table.get("attachments", []) if a.get("swing")}
    # 只会抽动、不会周期摆的参数（猫耳）也要进 flick 名单。
    _ids_all = sorted(set(swing_ids) | set(flick_extra))
    if _ids_all and flick_moods:
        _ids = _ids_all
        rig["tail_flick"] = {
            "params": _ids,
            "scale": [round(fsc.get(i, 1.0), 3) for i in _ids],
            "moods": flick_moods,
            "_note": "情绪 → [间隔下限秒, 间隔上限秒, 幅度, 单次时长秒]。"
                     "名单里既有会周期摆的（尾巴四姿态），也有**只会偶尔抽一下**的"
                     "（猫耳 L/R，它们不进 ambient）。两者共用同一套排班器，"
                     "但每条参数各排各的班，所以左右耳不会一起抖。"
                     "引擎每起一下还会再抖力度 ±35%、时长 ±25%、方向随机 —— "
                     "没有两下是一样的。查不到的情绪不动，和另外四张情绪表同口径。"
                     "scale 和 params 同序，是每条参数自己的力度系数。",
        }

    # 「抖耳朵 / 甩尾巴」不在这里注入通道 —— 它们靠 action.flick_trigger
    # 去点既有的自发抽动机制（见动作定义处的说明）。
    # 但要确认：角色真有这些挂件时按钮才该存在，否则点了没反应比没按钮更糟。
    _fl = set(rig.get("tail_flick", {}).get("params", []))
    _need = {"ear_twitch": "ParamEar", "tail_swish": "ParamAccTail"}
    rig["actions"] = [a for a in rig.get("actions", [])
                      if a.get("id") not in _need
                      or any(x.startswith(_need[a["id"]]) for x in _fl)]


def build(parts, sprite, canvas, name, cw, ch, head_is_part=False,
          seg=None, anchors=None, eyes=None, mouth=None, lids=None, armp=None,
          closed=None, blendp=None, eyeline=None, smile_eyes=None,
          pain_eyes=None, wide_eyes=None, footp=None,
          star_eyes=None, base=None, fx_table=None, skirtp=None, jacketp=None,
          handp=None, skirtx=None):
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
    # ★★★ 2026-10-21 第三十一问：anchors 里的 shoulder_l/r 是**剪影外缘**不是关节
    #   （make_anchors.py 写的是 prof[shoulder][0]/[1]）。make_arm_parts.py 会按
    #   教程口径「関節は腕幅と同じ直径の正円、その中心」反求真关节并写进
    #   arm_parts.json，有就用它 —— 肩枢轴落在关节上，挥手才不会甩出直切边。
    if armp and armp.get("shoulder_joint"):
        _sj = armp["shoulder_joint"]
        if "l" in _sj:
            sh_l = [ox + int(round(_sj["l"][0])), oy + int(round(_sj["l"][1]))]
        if "r" in _sj:
            sh_r = [ox + int(round(_sj["r"][0])), oy + int(round(_sj["r"][1]))]
        print("[rig] 肩枢轴用 arm_parts.shoulder_joint: l=%s r=%s" % (sh_l, sh_r))
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
                  "arm_l_root": ["arm"], "arm_r_root": ["arm"],
                  "seg_leg_l": ["leg"], "seg_leg_r": ["leg"],
                  "hair_ahoge": ["hair"], "hair_front": ["hair"],
                  "hair_side_l": ["hair"], "hair_side_r": ["hair"],
                  "hair_back": ["hair"],
                  "brow_l": ["brow"], "brow_r": ["brow"]}
        seg_src = list(seg["parts"])
        if armp:
            # G4c：整条手臂（seg_arm_l/r）作废，换成上臂 + 前臂四件真关节零件
            seg_src = [sp for sp in seg_src if sp["id"] not in ("seg_arm_l", "seg_arm_r")]
            arm_src = armp["parts"]
            # ★ Q37：**原画那两只手留着**（放松档就是它）。
            #   Q36 把它们换成程序化画的手是错的 —— 用户原话"完全成怪物了"。
            #   make_hand_parts.py 现在只出 ① 腕部塗り足し圆盘 ② 张开/比心两档生图件，
            #   三者和原画手同组、同枢轴，靠 alpha 互斥。
            seg_src += [dict(sp, note="手臂拆件（make_arm_parts.py：袖缝切 + 肘关节）")
                        for sp in arm_src]
            if handp:
                seg_src += [dict(sp) for sp in handp["parts"]]
        if skirtp:
            # T45.11：裙子里布。官方手册「スカートなどは手前の面と奥の面で
            # **足を挟むように**画像を分けておく」⇒ 里布层 50 < 腿 60/61 < 躯干 100。
            # 组跟躯干同一个（chest）：里布本来就是裙子的一部分，
            # 身体平移/旋转时必须和表布**完全同步**，只有形变器那一层才差开。
            seg_src += [dict(sp, group=sp.get("group", "chest")) for sp in skirtp["parts"]]
            tag_of.update({sp["id"]: ["body", "skirt"] for sp in skirtp["parts"]})
        if footp:
            # T24.5：鞋从腿件上拆下来，常态/踮脚两张姿态图各一件（交叉淡化切换）
            seg_src += list(footp["parts"])
            tag_of.update({"seg_foot_l": ["leg", "foot"], "seg_foot_r": ["leg", "foot"],
                           "seg_foot_l_tip": ["leg", "foot"],
                           "seg_foot_r_tip": ["leg", "foot"]})
        # ★★★ Q42（2026-10-22）上臂回到躯干**之上**（140/141），靠「正圆关节」兜底。
        #
        #   Q41 我把上臂压到躯干底下（97/98）躲开胸口那条青色楔形 —— 治标，而且
        #   当场制造了更难看的新病：袖根被夹克盖住，手臂只能从**胸侧**露头，
        #   用户第四十二问一句话点破：「我说的是你的肩头呢？内缩了吗？」
        #
        #   真正的毛病在**切件形状**，不在层序：`arm_*_upper` 的顶端是一刀平切、
        #   还高出肩枢轴 63px（logs/asset_qa/q42_parts.png 四件分色图里那根蓝色尖刺），
        #   绕肩一转当然扫到胸口。正解是 `tools/round_arm_sockets.py`：
        #   把关节那一圈做成**以枢轴为圆心的正圆**，圆内的料归不转的 cap（静止肩球）、
        #   圆外的归旋转的上臂 —— 这就是 Live2D 官方「関節パーツは腕幅と同じ直径の
        #   正円、枢轴＝その中心」的做法（本文件 2440 行注释早就写过这条）。
        #   件改对了，层序就不用再绕路，照旧 140/141 画在躯干之上，肩头才在。
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
        smiles = {e["side"]: e for e in (smile_eyes or {}).get("eyes", [])}
        pains = {e["side"]: e for e in (pain_eyes or {}).get("eyes", [])}
        wides = {e["side"]: e for e in (wide_eyes or {}).get("eyes", [])}
        stars = {e["side"]: e for e in (star_eyes or {}).get("eyes", [])}
        for e in eyes["eyes"]:
            side = e["side"]
            LY = FACE_LAYER[side]
            L = LY["socket"]
            px, py = e["patch_pos"]
            bx, by = e["ball_pos"]
            sid = f"eye_{side}"
            # 眼线已挖掉（脸上不再画着睁眼）时，眼眶就能当"开口"用：
            # 按 blink 纵向压扁，被它裁切的眼白/眼球/高光跟着被切掉 = 眼睛真的合上。
            el = next((x for x in (eyeline or {}).get("eyes", []) if x["side"] == side), None)
            sock = {"id": f"{sid}_socket", "file": f"sprites/{e['socket']}", "group": "head",
                    "layer": LY["socket"], "pos": [ox + px, oy + py], "anchor": [0, 0],
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
                 "layer": LY["base"], "pos": [ox + px, oy + py], "anchor": [0, 0],
                 "tags": ((["eye_open"] if closed else [])
                          + (["eye_not_wide"] if side in wides else [])),
                 "mask": f"{sid}_socket",
                 # 眼白也要被眼眶裁住：它比眼眶大一圈，不裁的话闭眼时眼皮盖不住那一圈，
                 # 眼睛底下会留一条蓝边（实测）。脸上本来就画着同样的眼睛，裁掉不丢东西。
                 "note": "眼白底：眼球移开也不会露洞；同样由眼眶裁切"},
                {"id": f"{sid}_ball", "file": f"sprites/{e['ball']}", "group": "head",
                 "layer": LY["ball"], "pos": [ox + bx, oy + by], "anchor": [0, 0],
                 "tags": ["gaze", "eye_open"] if closed else ["gaze"], "mask": f"{sid}_socket",
                 "note": f"眼球：完整的圆（被眼皮挡住的部分已补全），"
                         f"可动范围 ±{e['travel'][0]}/±{e['travel'][1]}px，由眼眶裁切"},
            ]
            # 星形虹膜（T39.1 / L1+L2）：和常态虹膜同位置同轮廓的差分件。
            # 这是日文教程里的标准「きらきら目差分」做法 —— 不改眼球几何，
            # 只拿另一张贴图原地盖上去，用不透明度 0↔100 切（见 ParamStarEye）。
            #   · motion_from 照抄常态虹膜的通道值 → 视线、瞳孔缩放一起跟着走，
            #     不用把 GEO2PARAM 里那四条绑定再抄一遍（抄一遍就是 DC41 说的多入口）；
            #   · tags 仍带 gaze/eye_open：这两件事是引擎按标签逐件算的，不走通道。
            st = stars.get(side)
            if st:
                eye_parts.append(
                    {"id": f"{sid}_ball_star", "file": st["file"],
                     "group": "head", "layer": LY["ball_star"],
                     "pos": [ox + bx, oy + by], "anchor": [0, 0],
                     "tags": ["gaze", "eye_open"] if closed else ["gaze"],
                     "mask": f"{sid}_socket", "motion_from": f"{sid}_ball",
                     "note": "星形虹膜（星星眼 L1+L2：五角星瞳 + 眼内碎钻高光）。"
                             "ParamStarEye=0 时全透明、常态虹膜露出来；=1 时反过来"})
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
                     "layer": LY["lid"], "pos": [ox + lid["pos"][0], oy + lid["pos"][1]],
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
                         "layer": LY["lash"], "pos": [ox + px, oy + py], "anchor": [0, 0],
                         "tags": (["eyelid"] if lid else ["eye_open"])
                                + (["eye_not_wide"] if side in wides else []),
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
                lash_part["tags"] = ["eyelid"] + (["eye_not_wide"] if side in wides else [])
                if el.get("lash_file"):
                    lash_part["file"] = f"sprites/{el['lash_file']}"
                lash_part["eyelid_travel"] = el.get("lash_travel") or round(ap_h * (1.0 - AP_MIN), 1)
                # 延迟到后半程再滑（引擎 lash_hold）：半闭时睫毛压进虹膜会出现黑钩、
                # 瞳孔被吃掉（2026-10-15 用户截图 + logs/asset_qa/lash_ab.png 的 A/B）。
                # 两端不变：闭合度 0 不动、闭合度 1 仍是满行程落在闭眼线上。
                lash_part["lash_hold"] = LASH_HOLD
                lash_part.pop("mask", None)
                lash_part["note"] = ("上眼线：脸上的眼线已挖除，这条线在闭合度 "
                                     f"{LASH_HOLD} 之后滑 {lash_part['eyelid_travel']}px，"
                                     "闭到底 = 那条闭眼线")
            eye_parts.append(lash_part)
            # 闭眼真素材：AI 重绘的闭眼脸切下来的补片，blink=1 时完全盖住原画的眼睛。
            # 引擎里 tags:["eye_closed"] 就是 opacity *= blink（与 eye_open 交叉淡化），
            # 等价于 Live2D 的 ParamEyeLOpen 在贴图版里的做法。
            if cl:
                eye_parts.append(
                    {"id": f"{sid}_closed", "file": f"sprites/{cl['file']}", "group": "head",
                     "layer": LY["closed"], "pos": [ox + cl["pos"][0], oy + cl["pos"][1]],
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
                     "layer": LY["smile"],
                     "pos": [ox + sm["pos"][0], oy + sm["pos"][1]],
                     "anchor": [0, 0], "tags": ["eye_smile"],
                     "note": f"笑眼（AI 重绘·盖住原画眼睛 {sm['checks']['cover_ratio']*100:.1f}%，"
                             f"接缝色差 {sm['checks']['seam_mean_abs']}）：ParamEyeL/RSmile=1 时显形"})
            # 痛苦闭眼 >_<：同一条流水线的第三张重绘底图，倒 V 的闭眼线。
            # 口径和笑眼一字不差（引擎里 pain 涨多少，closed 和 smile 就让多少）。
            pn = pains.get(side)
            if pn:
                eye_parts.append(
                    {"id": f"{sid}_pain", "file": f"sprites/{pn['file']}", "group": "head",
                     "layer": LY["pain"],
                     "pos": [ox + pn["pos"][0], oy + pn["pos"][1]],
                     "anchor": [0, 0], "tags": ["eye_pain"],
                     "note": f"痛苦闭眼 >_<（AI 重绘·盖住原画眼睛 "
                             f"{pn['checks']['cover_ratio']*100:.1f}%，"
                             f"接缝色差 {pn['checks']['seam_mean_abs']}）：ParamEyeL/RPain=1 时显形"})
            # 真·瞪大眼：唯一一张"睁着的"重绘补片。它顶替常态的眼白(base)和上睫毛(lash)，
            # 虹膜已在切件时挖掉，视线照旧由 eye_*_ball 负责（层号排在它上面）。
            wd = wides.get(side)
            if wd:
                eye_parts.append(
                    {"id": f"{sid}_wide", "file": f"sprites/{wd['file']}", "group": "head",
                     "layer": LY["wide"],
                     "pos": [ox + wd["pos"][0], oy + wd["pos"][1]],
                     # 同时挂 eye_open：这张画的是**睁着的**眼，眨眼时必须和常态睁眼件
                     # 走同一条退场曲线，否则眨到一半两张上眼线各半透明，糊成重影。
                     "anchor": [0, 0], "tags": ["eye_wide", "eye_open"],
                     "note": f"瞪大眼（AI 重绘·挖掉虹膜 "
                             f"{wd['checks'].get('iris_erased_px', 0)}px）：ParamEyeL/RWide=1 时顶替"
                             f"常态眼白与上睫毛，虹膜仍是 {sid}_ball"})
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
        # 层号全部来自 FACE_LAYER（见文件上方那张表）：高光在虹膜之上、睫毛之下。
        # 层号只要唯一就行：A9 之后遮罩是渲染时当场画的，
        # 不再要求"遮罩和被裁件在图层里挨着"（这条限制以前逼着我们挪层号）。
        for side in ("l", "r"):
            lay, starlay = FACE_LAYER[side]["hl"], FACE_LAYER[side]["hl_star"]
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
    # ✨ 闪光特效（星星眼 L3，T39.1b/T39.1c）。
    #
    # 做法照 Live2D 讲师カワナミ 的《キラキラエフェクト》（REFERENCE_NOTES 第二十五批）：
    #   · **素材只有一张**，大中小和散布全靠复制 + 变形（scale / rot_deg）；
    #   · 一颗闪光只要 scale + alpha 两条通道，合并到**一个**参数上
    #     （参数 0→1 走完 = 放大出现 → 缩小消失一个生命周期）；
    #   · **每颗各自一个参数，不许共用** —— 共用会整齐划一地闪，一眼假。
    #     原作者为此用了 28 颗 28 个参数；我们 8 颗 8 个参数，另外把每颗的
    #     振荡频率也取成两两不同（见 star_eye_parts.json 的 freq），
    #     这样跑久了也不会重新对齐。
    # 层号在 300+：这是"画在人物前面的演出效果"，不属于任何五官。
    if star_eyes and star_eyes.get("sparkle"):
        sk = star_eyes["sparkle"]
        _fx = (fx_table or {})["sparkle"]
        _lay0, _grp = _fx["layer0"], _fx["anchor"]["group"]
        _blend, _tags = _fx["blend"], list(_fx["tags"])
        for i, inst in enumerate(sk["instances"]):
            parts_list.append({
                "id": inst["id"], "file": sk["file"],
                "group": _grp, "layer": _lay0 + i,
                "pos": [ox + inst["pos"][0], oy + inst["pos"][1]],
                "anchor": [0.5, 0.5],          # 锚点在正中：缩放是"从中心胀开"
                "scale": inst["scale"], "rot_deg": inst["rot_deg"],
                # ⚠ 不能用加算：zimg_blend 的 ADD 保留目标 alpha（oa = da），
                # 画在**透明背景**上等于没画。✨ 恰恰飘在人物剪影外面，
                # 第一版写 add 的结果是八颗全看不见（实测）。普通混合即可 ——
                # 素材本身就是白芯蓝尖的发光图，不靠混合模式发光。
                # fx_eye_open：跟着眨眼变淡但**不会全灭**（引擎 FX_EYE_OPEN_FLOOR=0.45）。
                # 这是 T39.5「目を見開いたときに」的一半 —— 眼睛闭上时 ✨ 不该还在满亮。
                # 刻意不用 eye_open（那条会归零）：眨一次眼 0.3s，硬门会让一圈 ✨
                # 整体熄掉再亮起来，看着像渲染故障。
                "opacity": 1.0, "blend": _blend, "tags": _tags,
                "note": f"闪光 {inst['size_class']}（加算）：默认全透明，"
                        f"ParamStarEye 开门、ParamSparkle{i + 1} 管这一颗的生命周期",
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
    def sparkle_cycle(se):
        """八颗闪光的生命周期通道。挂在 idle 上 = 星星眼一开就在闪。

        为什么是正弦而不是 pulse：pulse 是一次性的，idle 要一直循环。
        amp/bias 取 0.62/0.38 → 取值范围 [−0.24, 1.0]，负的那段被 alpha 的
        ZC_CLAMP 压成全透明 —— 于是每颗有约四分之一个周期是**完全不在**的，
        看起来才像"闪一下又没了"，而不是八个灯一起呼吸。
        每颗的 freq 两两不同（star_eyes_parts.json 里定死），所以跑多久都不会重新对齐。
        """
        if not se:
            return []
        _fx = (fx_table or {}).get("sparkle")
        if not _fx:
            return []
        _m, _p = _fx["motion"], _fx["param"]["prefix"]
        return [{"target": f"{_p}{i}", "wave": _m["wave"],
                 "amp": _m["amp"], "bias": _m["bias"],
                 "freq": inst["freq"], "phase": inst["phase"]}
                for i, inst in enumerate(se["sparkle"]["instances"], 1)]

    # ---- 动作的中文名 ----
    # 为什么名字写在这里而不是界面里：测试台是脚手架，正式软件的 UI 要整个重做
    # （用户 2026-10-24 明确要求）。界面层存的文案换一次 UI 就得重写一遍，
    # 数据层存的不用。引擎把它经 info.json 的 action_names 原样送出去，
    # 谁来画界面都拿得到同一套名字。
    # 漏了名字不会报错，只是界面上显示英文 id —— 这就是 2026-10-24
    # 截图里 nod / wave_both / kirara_jump 等 8 个按钮露出英文的原因。
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
             # ★ Q37：待机也要有"头在慢慢转"这件事，否则头发物理（输入=头的位移）
             #   一整天都是零输入。频率 0.11Hz 刻意和身体的 0.18Hz **不成整数比**，
             #   两条正弦慢慢错相位 ⇒ 看不出循环（这是待机动画不显得机械的老办法）。
             {"target": "ParamAngleX", "wave": "sine", "amp": 5.0, "freq": 0.11,
              "phase": 0.4},
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
             # idle 的头部微转（Q37）。比 sway 更小更慢 —— 它是"没人理我"时的底噪，
             # 只要够把发梢推动 2~3px 就行，多了会像在摇头晃脑。
             {"target": "ParamAngleX", "wave": "sine", "amp": 2.2, "freq": 0.075,
              "phase": 0.15},
             {"target": "eye_open_left", "param": "dy", "wave": "sine", "amp": 0.5, "freq": 0.2},
             {"target": "eye_open_right", "param": "dy", "wave": "sine", "amp": 0.5, "freq": 0.2},
         ] + sparkle_cycle(star_eyes)},
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
         # ⚠ 这里**不能**再写 blink_hold：blink_hold 是**阶跃**生效的（动作一开始
         # 闭合度立刻变 0.95），而 EyeSmile 是 pulse（0.3s 才爬到 1、收尾先退场），
         # 两条曲线不同步 → 动作头 0.3 秒和尾 0.15 秒各露出一段"眼睛闭着但没在笑"
         # 的谷型 ∪ 闭眼。用户 2026-10-15 验收"抚摸时不是 ∩ 形笑眼"报的就是它
         # （实测时间线：0.00~0.28s ∪、0.30~0.86s ∩、1.01s 又 ∪）。
         # 正解：闭眼交给笑眼自己——引擎 accumulate 里有 blink = max(blink, smile)，
         # 闭合度天然跟着同一条 pulse 走，两头严丝合缝（官方 Haru F05 也是
         # EyeOpen 和 EyeSmile 在同一个表情里一起淡入，不是分两套时序）。
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
             # 开心要的是 ∩∩ 笑眼，不是"半闭着的睁眼"。原来只写 blink_hold 0.78
             # 而没有笑眼通道 —— 0.78 落在"睁眼件还没淡出、闭眼件还没淡入"的那
             # 段里，画出来是一只压扁的、没有瞳孔的眼睛（2026-10-15 实测，见
             # logs/asset_qa/eye_ladder.png 的 0.2/0.3 两格）。改成和摸头同一套：
             # blink_hold 0.95 + EyeSmile 1.0，山型笑眼顶替谷型闭眼。
             {"target": "ParamEyeLSmile", "wave": "pulse", "amp": 1.0, "dur": 0.30, "ease": "out"},
             {"target": "ParamEyeRSmile", "wave": "pulse", "amp": 1.0, "dur": 0.30, "ease": "out"},
         ],
         # ⚠ 这里**不能**再写 blink_hold：blink_hold 是**阶跃**生效的（动作一开始
         # 闭合度立刻变 0.95），而 EyeSmile 是 pulse（0.3s 才爬到 1、收尾先退场），
         # 两条曲线不同步 → 动作头 0.3 秒和尾 0.15 秒各露出一段"眼睛闭着但没在笑"
         # 的谷型 ∪ 闭眼。用户 2026-10-15 验收"抚摸时不是 ∩ 形笑眼"报的就是它
         # （实测时间线：0.00~0.28s ∪、0.30~0.86s ∩、1.01s 又 ∪）。
         # 正解：闭眼交给笑眼自己——引擎 accumulate 里有 blink = max(blink, smile)，
         # 闭合度天然跟着同一条 pulse 走，两头严丝合缝（官方 Haru F05 也是
         # EyeOpen 和 EyeSmile 在同一个表情里一起淡入，不是分两套时序）。
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
             # 惊讶时的眼睛：**瞳孔略缩**，不是放大（2026-10-15 用户反馈"眼球不自然变大，像个怪物"）。
             # 原来这里写的是 eye_open_* 的 sx +0.18 / sy +0.22 四条部件通道，换算到
             # ParamEyeBallForm 刚好是 +1.0 —— 而这个参数在本 rig 里只绑了眼球缩放，
             # 于是虹膜被撑大 18~22%，整只眼睛鼓出来。
             # 官方/社区口径正好相反：shocked = 眼睛**开得更大** + 瞳孔**变小** + 挑眉 + 张嘴
             #   · saltech.llc Live2D 参数表：ParamEyeLWide「Widen the eye beyond ParamEyeLOpen」
             #     —— 瞪大眼有专门的参数，不是靠放大瞳孔；
             #   · Animaze 官方手册：ParamEyeLOpen 往 max 方向才是"目を大きく開く"；
             #   · r/Live2D 两个独立帖子都写 "extra opened eye + smaller pupil"。
             # 我们暂时没有"瞪大眼"的素材和参数（ParamEyeLOpen/ROpen 由眨眼系统合成，
             # 不在 params 里，驱不到 >1），所以只做能做对的那一半：瞳孔缩小。
             # 幅度 -0.45 是渲 4 档对照图挑的（logs/asset_qa/surprised_eyes2.png）：
             # -0.8 偏呆滞、0.0 没表情、-0.45 露白稍多、读得出"吓一跳"又不怪。
             # 写成**参数级**一条而不是部件级四条：四条经 GEO2PARAM 换算后会合并成同一个
             # ParamEyeBallForm，幅度靠 amp/scale 反推，改起来极易算错（嘴那边就是这么翻车的）。
             {"target": "ParamEyeBallForm", "wave": "pulse", "amp": -0.45, "dur": 0.2},
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
             # ⚠ 这个动作是 loop，blink_hold 会一直按着，所以**绝对不能**停在
             # 0.2~0.8 那段半闭区间：那段里睁眼件还在、闭眼件还没来，眼睛是一条
             # 没有瞳孔的扁青带，而且一按就是好几秒 —— 用户 2026-10-15 报的
             # "眼睛还是会卡住"就是它（实测：stroke 期间眼高长时间停在 16~24px，
             # 其它动作都能回到 33px）。被抚摸要的是"舒服地眯眼笑"，正解是山型
             # 笑眼件（和摸头同一套），不是把睁眼压扁。
             # pulse = dur 内升到 amp 然后一直保持（见 zrig.c 的 W_PULSE），
             # 所以 0.35s 升上去之后整个 loop 都维持笑眼。
             {"target": "ParamEyeLSmile", "wave": "pulse", "amp": 1.0, "dur": 0.35, "ease": "out"},
             {"target": "ParamEyeRSmile", "wave": "pulse", "amp": 1.0, "dur": 0.35, "ease": "out"},
         ],
         # ⚠ 这里**不能**再写 blink_hold：blink_hold 是**阶跃**生效的（动作一开始
         # 闭合度立刻变 0.95），而 EyeSmile 是 pulse（0.3s 才爬到 1、收尾先退场），
         # 两条曲线不同步 → 动作头 0.3 秒和尾 0.15 秒各露出一段"眼睛闭着但没在笑"
         # 的谷型 ∪ 闭眼。用户 2026-10-15 验收"抚摸时不是 ∩ 形笑眼"报的就是它
         # （实测时间线：0.00~0.28s ∪、0.30~0.86s ∩、1.01s 又 ∪）。
         # 正解：闭眼交给笑眼自己——引擎 accumulate 里有 blink = max(blink, smile)，
         # 闭合度天然跟着同一条 pulse 走，两头严丝合缝（官方 Haru F05 也是
         # EyeOpen 和 EyeSmile 在同一个表情里一起淡入，不是分两套时序）。
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
            # 大臂 -58° + 前臂 -98° = 手腕总转 156°。
            # Q36 复核：总角 138° 时前臂离竖直还差 42°，整条胳膊像个"<"；
            # 人挥手时前臂基本是竖的（用户附图 q36_wave.png 量出来约 20°），
            # 所以前臂从 -80 加到 -98（肘内角 98°，人的肘屈曲极限 145°，够用）。
            # Q36 复核（对照用户附图 logs/asset_qa/user/q36_wave.png）：
            #   真人挥手是"**肘抬到肩高**、前臂竖起来"，上臂 −58° 时肘还在腰侧，
            #   整条胳膊像个趴着的 7。改 −72° 后肘落在 (679,506) ≈ 肩高，
            #   手落在 (719,397) ≈ 头侧，和照片一致。
            # 时序（Q36 二次复核后改）：**肘先折、肩后抬、腕最慢**。
            #   第一版写成肩 0.9 / 肘 1.3（肩先抬），实拍 logs/asset_qa/q36_final_wave.png
            #   第 1 帧整条胳膊甩成一条横杠，手指戳到 x=464（画布只有 466 宽）——
            #   肩(523)+上臂162+前臂116+手70 = 871 > 画布 848，**伸直的横臂本来就装不下**。
            #   人挥手也不是先把胳膊甩平：肘几乎同时就折起来，手走的是贴着身体的内弧。
            #   所以把前臂提到 dur 0.7（领先）、上臂 1.0、手腕 1.6 ——
            #   "手首は肘より半拍遅れる"（官方《手を振るモーション》）说的是腕对肘，
            #   这条仍然成立（1.6 > 0.7），只是肩不再领跑。
            # ======== Q38 重做：角度不是我估的，是从参考图上量的 ========
            # 用户判死刑：\"你自己空白无参考做出的挥手动作完全不符合一个人能做出的动作\"。
            # 新工序：先用小寻自己的短发底图生一张挥手参考图，再在图上量角、照着写 rig。
            #   参考图 characters/xiaoxun/design/pose_ref/wave_up.png（1024×1536 原生）
            #   打网格肉眼读点（logs/asset_qa/q38_wave_up_grid.png）：
            #       肩 (455,315) → 肘 (495,475) → 腕口 (487,352) → 手心 (495,280)
            #   ⇒ 上臂与竖直夹角 atan2(40,160)  = **14°**（几乎贴着身子垂着）
            #     前臂与竖直夹角 atan2(-8,-123) = **4°**（竖着，略往里）
            #     肘的画面投影夹角                = **170°**（小臂整条折回来贴着大臂）
            #     手心比肩**高 35px**、只在肩外侧 40px —— 手是在**耳朵边上**，不是伸在外面。
            #
            # 对照旧值 arm_r −72° / forearm_r −88°：上臂被抬到离水平只差 18°，
            # 162px 的上臂把肘甩到体侧 154px 外，手自然落在离脑袋一臂远的地方 ——
            # 那是\"路牌\"/交警手势，不是打招呼。资料也是这么说的：
            #   pixiv 百科「手を振る」：**離れた相手**にだけ肘を伸ばして腕ごと大きく振る；
            #   近くの相手には**肘を曲げて手首を回転させながらひらひら**。
            #   桌宠永远是\"近くの相手\"⇒ 主动力在肘和腕，不在肩。
            #   copainter 姿势表同款口径：「右腕を肩より上に上げ、手のひらをカメラに向けて開く、
            #   左腕は体側」＋ 崩れやすい点「手首が逆に曲がる」。
            # 肩只留 18°（参考图 14° + 一点点抬肩：waterarena「手を上げる側の肩は
            # 少しだけ上がる」），其余行程全部交给肘。
            # ★ 两张参考图量完之后的取舍（过程留证在 logs/asset_qa/q38_*）：
            #   pose_ref/wave_up.png  = 近距离招手（肘折 170°、手在耳边）。
            #     量出来 肩(455,315)→肘(495,475)→腕(487,352)、上臂 165px。
            #     **我们的贴图做不了这个姿势**：肘折到 170° 等于让前臂整条压在
            #     上臂上，而这件是蓬松的运动卫衣袖 —— 两层蓬松量叠在一起，
            #     渲染出来是个"拳击手套"（实拍 logs/asset_qa/q38_elbow_zoom.png
            #     3× 放大，肘上一坨带台阶的肉瘤）。加肘关节帽也救不回来
            #     （logs/asset_qa/q38_elbowcap_sim.png：圆盘越大越把白夹克像素
            #     拽进来，而且原画的明暗方向和折起来之后对不上）。
            #   pose_ref/wave_out.png = 大幅度挥手（肘近乎伸直、整条手臂斜举）。
            #     用薄荷袖掩码做 PCA 量主轴：肩(450,367)→袖口(669,149)，
            #     **与竖直夹角 135°、长度 308px ≈ 上臂165+前臂123**，即肘只弯 10~20°。
            #     这一路**没有任何对折**，四个角度的离线合成都干净
            #     （logs/asset_qa/q38_waveout_sim.png），所以挥手走这一版。
            #   资料也对得上 —— pixiv 百科「手を振る」：**離れた相手には肘を伸ばして
            #   腕ごと大きく振る**；桌宠在屏幕里跟人打招呼，正是这一种。
            #   copainter 的姿势口径「右腕を肩より上に上げ、手のひらをカメラに向けて開く、
            #   左腕は体側」也全部满足（手掌差分 ParamHandROpen=1 朝正面）。
            #
            # 为什么不是旧版的 −72°/−88°（用户判"完全不符合一个人能做出的动作"）：
            #   −72° 把大臂停在离水平只差 18° 的地方、肘再折 88°，整条胳膊是个
            #   躺倒的"L"——人只有在指路或当交警时才摆这个造型。参考图里**没有
            #   任何一张**是肩停在水平、肘折直角的。
            # ======== Q40 再修：上一轮"量"的方式不对，这一轮重量 ========
            # 用户 Q39 判：手臂仍不合参考图（T46.35）。Q38 我是拿**整条袖子掩膜做 PCA**
            # 量的 —— 那条轴把肩根的喇叭口（袖子在肩上摊开的那一摊）也算了进去，
            # 读出来的"135°/肘弯 10~20°"是假的（LESSONS 321：单指标 = 假对齐）。
            #
            # 这一轮按 WORKFLOW 第十章（动作类的真值源 = 参考图）重走：
            #   ① 连通域把袖子从身体青色里切出来（洪水填充，种子点在袖管上）；
            #   ② 沿主轴每 6px 切一刀，取每刀横截面的 2~98 百分位中点 ⇒ 中线；
            #   ③ 只取**靠手那 60%**（避开肩根喇叭口）做直线拟合。
            #   量得：参考 wave_out.png = **44.8°**（相对竖直向上），
            #         直线残差 均 1.3px / 最大 2.9px（袖长 255px）
            #         ⇒ 参考里的手臂是**伸直的**，Q39 我写的"肘明显弯"是错的。
            #   同一把尺子量我们的渲染帧：**渲染角 = 165° − |命令角|**
            #   （原画手臂在 rot=0 时本来就外张约 15°，所以不是 180−x）。
            #
            # 那为什么最后取 −130（渲染 34.9°）而不是对齐 44.8° 的 −120？
            #   因为**参考图和我们的身体比例不一样**：参考图是张短脖子构图，
            #   肩只在下巴下 0.17 个头高；我们的骨架是 0.48 个头高。
            #   按头宽把参考配准过来算：它的袖口落在我们 rig 坐标 (698,228)，
            #   从我们肩 (523,464) 看过去方向 36.4°、距离 294px —— 比我们
            #   上臂 162 + 前臂 116 = 278 的臂长还远，**够不着**。
            #   实测各角度的指尖高度（渲染帧，发顶 y=35）：
            #       −115(现) −61px ／ −120 −67 ／ −126 −55 ／ −130 −50 ／ −135 −42
            #   参考是 **+20px（指尖在发顶之上）**⇒ 我们连手臂竖直都只到 −16px，
            #   "手举过头顶"这条**在这套比例下物理上做不到**，只能取最接近的。
            #   叠图（logs/asset_qa/q40_ghost.png，把参考按头宽缩放后染红压上去）：
            #       −120 手臂和红影之间一道明显楔形空隙；−130 基本重合。
            #   ⇒ 取 −130：**手的落点优先**（用户点名的是"手不够高"），
            #     臂向差 10° 是两套比例的必然代价，不是姿势错。
            # ★★★ Q42（2026-10-22 第四十二问）改成**近距离打招呼**：肘折起、手到脸侧。
            #
            #   用户原话：「哪里有你这样的手臂动作，这不是人做的出来的？？？」
            #   —— 说的是 Q40 定的那根**从腋下斜插上去的直棍**。
            #
            #   Q40 错在**选错了参考图**：我拿 `pose_ref/wave_out.png` 量，量得
            #   "手臂是直的（残差 0.5%）"，于是把肘拉直到 4°。但那张是**远距离**
            #   大幅挥手。桌宠是**近距离**打招呼，真值源是另一张
            #   `pose_ref/wave_up.png`——而且我自己的参考笔记早写过这条
            #   （dic.pixiv.net/a/手を振る：「遠距離では肘を伸ばして大きく、
            #   近距離では肘を曲げて手首をひらひら」）。
            #
            #   重量 wave_up.png（teal 掩膜连通域 + 行剖面，logs/asset_qa/q42_refarm.png）：
            #     上臂 肩(520,345)→肘(548,470)：相对竖直 **12°**（几乎垂着）
            #     前臂 肘→腕(560,355)：相对竖直 **175°**（几乎竖直向上）
            #     ⇒ 肘屈曲 ≈165°，手落在**脸颊高度、紧贴头侧**，掌心朝前。
            #
            #   为什么不照搬 12°/165°：我们的臂长比例和参考图不一样 ——
            #   参考 上臂:前臂 ≈ 153:146（0.95），我们是 **162.4:116（0.71）**。
            #   前臂短那么多，上臂垂着折到极限也只能把手送到胸口高度
            #   （正向解：肩(523,464) + 162.4∠12° + 116∠175° ⇒ 腕 (567,507)，
            #   比肩还低 43px）。所以只能二选一，取**手的落点**（用户看的是手）：
            #     上臂抬到 A_u=110°（命令 −95）、肘折 70°（命令 −70，前臂竖直）
            #     ⇒ 肘 rig(670,395)、腕 rig(664,279) = 帧 (365,153)，手在**眼睛高度、
            #       头的右侧**，掌心朝前 —— 和参考图的读感一致（q42_poses.png 六格对比，
            #       Au110/f70 那格 vs 右下角参考图）。
            #   肘内角 110°（人的屈曲极限 145°），上臂外展 110°（极限 180°），都做得到。
            # ★★★ Q43（2026-10-22 第四十三问）**又被打回，这次是姿势的"结构"**。
            #
            #   用户原话：「就算参考图规格不一样，你能把手臂做成截图一也是够*的了，
            #   你的眼睛看不到东西了？右边的截图这么规范的挥手，你看不到吗？
            #   ……那你连个正常人的结构都做不了吗？」
            #
            #   Q42 的 A_u=110° 错在哪（看 logs/asset_qa/q43_sweep.png 最后一格）：
            #     110° 是**上臂抬到水平以上**，肘尖甩到身体右侧外 60px、与肩同高，
            #     手离头发边缘还隔着 100px 的空当 —— 读起来是"把胳膊横着伸出去"，
            #     不是"在脸边打招呼"。2D 切件没有透视收缩，横着的上臂就是一根长棍。
            #
            #   参考图 wave_up.png 真正的结构（重量，logs/asset_qa/q43_ref_grid.png）：
            #     肩(500,310) → 肘(566,470) → 腕(576,320)
            #     · 上臂离竖直只有 22°，**肘贴在腰侧**（横向只离开肩 66px）
            #     · 前臂几乎竖直（176°），**贴着身体侧缘**立起来
            #     · 肘内角仅 26° —— 折得很紧，手因此能送到脸颊高度
            #     ⇒ 一句话：**窄 V 字、贴着身子**，不是"大"字。
            #
            #   比例差多少（这是事实，但不是做成横棍的借口）：
            #     参考 上臂 173 / 前臂 150 / 头高 160 ⇒ 整条臂 = 2.0 个头高（7.4 头身）
            #     我们 上臂 162 / 前臂 116 / 头高 270 ⇒ 整条臂 = 1.0 个头高（5 头身）
            #   照搬 22°/26° 会把手停在胸口（前向解 ⇒ 腕 rig(592,498)，比肩还低 34px），
            #   所以要在**保住"窄 V 贴身"这个结构**的前提下，把上臂多抬一点换手的高度。
            #
            #   姿势扫描（q43_sweep.png / q43_sweep2.png / q43_finalists.png，
            #   六档 A_u × A_f 实拍 + 参考图同比例同肩位并排 q43_vs_ref.png）：
            #     A_u=15~30  手只到胸口，且前臂整条压在上臂上，袖子叠成一坨 ✗
            #     A_u=45~52  手到下巴，已经像样
            #     A_u=68~75  手到鼻眼高度、紧挨头侧，肘仍在身体边缘 ✓
            #     A_u=110    （Q42）横棍 ✗
            #   ⇒ 定 **A_u=70°、A_f=209°**（肘内角 41°，人的屈曲极限 145° 内）：
            #     肘 rig(675,519)=帧(371,285) 只比躯干边缘外探约 55px、在肩下 55px；
            #     腕 rig(619,412)，手掌落在**嘴/鼻高度、头右侧一指宽**，掌心朝前。
            #   手掌单独回正到竖直（A_h=188°）：前臂往内倾了 29°，手跟着倾就成了
            #   "手背朝人"，所以腕上补 +21° 把掌心摆正 —— 参考图里掌心是正对镜头的。
            wave_channels = [
                # ★★★ Q44（第四十四问）把上臂从 A_u=70° 压回 **38°**。
                #   Q43 选 70° 的理由是"手要够到脸边"，但实拍放大一看
                #   （logs/asset_qa/q44_pose_cands.png 四格）那是**上臂横着伸出去**：
                #   肘落在躯干剪影外 **104px**，整条胳膊像根横棍挑着个球 —— 正是用户
                #   第四十三问点名禁止的「肘甩出躯干外」。
                #   逐档实测（肘超出躯干 / 腕低于下巴，单位 rig px）：
                #       A_u= 70 → +104 / +81     A_u= 48 → +63 / +117
                #       A_u= 58 →  +85 / +99     A_u= 38 → **+36 / +135**
                #       A_u= 30 →   +9 / +152
                #   取 **38°**：上臂基本贴着身体垂下、肘只探出 36px（袖子自身就有
                #   半个身宽的厚度，视觉上就是"肘贴着腰"），手指仍能抬到下巴旁边。
                #   （再往下压到 30° 肘是进去了，但前臂整条压在上臂上成了"双筒袖"。）
                # ★★★ Q45（第四十五问）又被打回：用户放大图里挥手的右臂是
                #   「吊在袖口下面的一只大拳套，外加一根像断了的杆」。
                #
                #   这次是**分件染色实拍**查出来的（前臂红 / 上臂蓝 / 肩帽黄，
                #   logs/asset_qa/q45_tint.png、q45_pieces.png）：
                #     · 前臂件本身是「胖袖筒 + 条纹袖口」，116 长 × 75 宽 = 1.55:1
                #       （参考图的前臂是 150 × 55 = 2.7:1）
                #     · Q44 的肘内角 32° ⇒ 两根管子的轴线间距只有 34px，
                #       而两件半宽加起来 80px ⇒ 前臂整条盖在上臂上，
                #       上臂只剩 1151px 可见 —— 那根"断了的杆"就是被压剩的上臂
                #     · 肘端的正圆（r=34.8）连着袖口一起吊在下面 = "拳套"
                #   ⇒ 结论：**这张原画的袖子太粗，32° 的窄 V 物理上读不出来**。
                #
                #   三处一起改（张开 + 收窄 + 抬肩，logs/asset_qa/q45_grid.png 实拍选型）：
                #     ① 肘内角 32° → **48°**（A_u=34 / A_f=166）：扫描实测上臂可见
                #        像素 1151 → 1656，前臂不再压在上臂上
                #     ② 前臂沿轴线收窄 17%（ParamForeSlimR + arm_r_fore_slim 形变器）
                #     ③ 同侧肩上提 26px（ParamShoulderRY）把手送到下巴—锁骨之间
                #   选型实测（lift=−26、内角 48°）：
                #       A_u=28 → 肘出躯干 +10px / 腕 y=472
                #       A_u=34 → 肘出躯干 **+28px（0.12 头宽）** / 腕 y=460  ← 取这档
                #       A_u=40 → 肘出躯干 +45px / 腕 y=448
                #   参考图自己的肘也离身 0.29 头宽，我们这档比参考还贴身，
                #   既满足「肘不许甩出躯干外」，又把手抬到了脸下方。
                # ★★★ Q48（第四十八问）：**前臂加长 26px + 上臂收回 12.1°**。
                #   用户：「肘关节的位置有一些折叠一样的痕迹，看起来不是很自然，
                #   而且小臂有一些偏短。」先对着参考模板目视比对
                #   （logs/asset_qa/q48_arm_ab2.png 同比例并排 / q48_elbow_tint.png
                #    分件染色实拍：红=上臂 蓝=前臂 绿=肩帽）：
                #     · 参考＝**闭合的发卡**：上臂几乎垂着、小臂折上来贴着它，
                #       外轮廓一条连续的 U，肘在最下方是个圆转弯。
                #     · 我们＝**大开口的勾**：上臂斜甩出去 34°、小臂又短又胖，
                #       两件在肘处交成尖角。
                #   几何差（同一把尺子）：参考 前/上 = 150/173 = 0.87，
                #   我们 116/162 = 0.71 —— 小臂相对短 18%，这才是「偏短」的根。
                #   改法（**手的落点一点不动**，用户点名「手不要再动」）：
                #     ① 前臂沿轴加长 26px（ParamForeLongR）⇒ 116→142 = 0.87
                #     ② 手要留在原地，解三角形（肩-肘-腕 162.4 / 141.8 / 125.1
                #        ⇒ 肩夹角 57.4°、SW 方向 79.1°）得 **A_u = 21.7°**
                #        ⇒ 肘从切件 (413,531) 收到 (383,547)：**往身上收 30px**，
                #          正是第四十三问要的「肘贴着身子、不许甩出躯干外」。
                #     ③ 肘内角 180 − (153.7 − 21.7) = **48.0°**，和 Q45 实拍
                #        选型定下来的安全值一致，不会回到「双筒袖」那档。
                # 肩：抬到 A_u=21.7°（静止 14.8° ⇒ 命令 −6.89）。近端先动 ⇒ dur 最短。
                # ★★★ Q50（第五十问）：这一段从「单脉冲」改写成**关键帧曲线**。
                #   用户：「挥手动作就是有种机械感，因为是直角直接翻过来」。
                #   实拍 logs/asset_qa/q50_wave_elbow_before.png 六格证实：
                #   f12（0.20s）前臂**整根横着伸到右边**、手在最远端 —— 一根杆
                #   扫过直角，这就是机械感的来源。三条教程口径一致：
                #     · 官方クオリティアップ：要有**反動（先往回一点）与刹车**，
                #       脸和身体同动但**错开时序（ずらし）**。
                #     · miracle-usausa-nurse.com/paint/499/：腕振りは
                #       **「のこし／後追い」** —— 手首は肘より遅れて着く
                #       （アニメーション 12 原則）。
                #     · note.com/marunaru82：**前腕を潰して回転軌道を小さくする**，
                #       「軌道が小さいほど滑らかに上がって見える」。
                #     · note.com/candyyamada：ぎこちない＝**カーブが直線的すぎる**，
                #       变化大的地方要多打键。
                #   所以四条曲线各自错时、各自带反动，不再是同一条 ease:out。
                # 肩：先**下沉 1.4°** 当反动（0.08s），再抬过头 −7.8°，回落到 −6.89°。
                {"target": "arm_r", "param": "rot_deg", "interp": "smooth",
                 "keys": [[0.0, 0.0], [0.08, 1.4], [0.30, -5.2], [0.45, -7.8],
                          [0.64, -6.5], [0.85, -6.89]]},
                # 前臂伸缩：**甩的过程里先缩 1.0（−26px）**，到位之后再伸到 +1.0。
                #   这就是 2D 里替代"透视收缩"的办法：横扫那一瞬间杆最短，
                #   手离身体最近，看上去就不是一根棍子划过去。
                {"target": "ParamForeLongR", "interp": "smooth",
                 "keys": [[0.0, 0.0], [0.14, -0.75], [0.34, -1.0], [0.55, -0.35],
                          [0.72, 0.72], [0.88, 1.05], [1.05, 1.0]]},
                # 同侧肩上提 26px（8.67 × 3.0）：比上臂**晚 0.06s** 起步（ずらし）。
                {"target": "ParamShoulderRY", "interp": "smooth",
                 "keys": [[0.0, 0.0], [0.06, 0.0], [0.42, 7.4], [0.58, 9.3],
                          [0.78, 8.67]]},
                # 前臂收窄：跟着"折到位"走，比折肘再晚一点点。
                {"target": "ParamForeSlimR", "interp": "smooth",
                 "keys": [[0.0, 0.0], [0.10, 0.0], [0.50, 0.55], [0.80, 1.0]]},
                # 肘：折到 A_f=153.7°（命令 −134.12）= 内角 48°，前臂斜竖起来。
                #   （Q48 前是 A_f=166°/命令 −132；上臂收回 12.1° 之后前臂要跟着
                #     多折 2.1°，手才落在同一个点上。）
                # 参考图 wave_up.png 量出来的肘内角就是 26°（肩(500,310)-肘(566,470)-
                # 腕(576,320)）—— 教科书式挥手本来就是"把前臂几乎折回来贴着上臂"。
                # dur 比肩长 = 慢半拍（saraemi「末端は遅れる」）。
                #   Q50：改成关键帧 —— **比肩晚 0.10s 起步**（のこし），中段
                #   用 smooth 插值自己带缓入缓出，0.78s 折过头到 −141°，
                #   再回弹到 −134.12° 停住（刹车）。横扫那一段配合上面的
                #   ParamForeLongR 负值，杆是**缩着**过去的。
                {"target": "forearm_r", "param": "rot_deg", "interp": "smooth",
                 "keys": [[0.0, 0.0], [0.10, -3.0], [0.26, -30.0], [0.44, -86.0],
                          [0.62, -124.0], [0.78, -141.0], [0.95, -132.0],
                          [1.12, -134.12]]},
                # 前臂只做很小的摆（±5°）：近距离打招呼主行程在**手腕**，
                # 前臂大摆会把手甩离脸侧，又变回"大幅挥"。
                {"target": "forearm_r", "param": "rot_deg", "wave": "sine",
                 "amp": 5.0, "freq": 1.6, "dur": 2.4},
                # 抬手那侧的肩膀要略上提（waterarena），用躯干微侧倾代替。
                {"target": "ParamBodyAngleZ", "wave": "pulse",
                 "amp": -6.4, "dur": 0.9, "ease": "out"},
                {"target": "arm_l", "param": "rot_deg", "wave": "pulse",
                 "amp": 4.0, "dur": 2.4, "ease": "out"},
            ]
            if has_hands:
                # G4c2：手腕是第三节。挥手时手掌比小臂再晚一点、摆得更大，
                # 这就是"鞭梢"的最后一节 —— 没有它，举起来的手是一块硬板。
                wave_channels += [
                    # ★ Q36：挥手要摊开手掌。官方做法是**换一张手的贴图**
                    #   （不是把握着的手掰开）：dur 0.1 = 几乎瞬切，然后整段保持，
                    #   动作收尾随 fade_out 一起退 —— 符合「不要在动作中途切手」。
                    {"target": "ParamHandROpen", "wave": "pulse",
                     "amp": 1.0, "dur": 0.10, "ease": "out"},
                    # 腕 ★★★ 2026-10-23 第四十七问重做（用户截图：手腕折断）。
                    #   原来写的是 +21°「把掌心摆正到竖直」—— 这个目标本身就是错的：
                    #   手是接在前臂末端的，**它该跟着前臂的方向走**，不是跟着画面竖直走。
                    #   前臂一斜，手还强行摆竖直，腕口就是一道折角。
                    #   静态几何量出来（切件坐标，不靠肉眼）：
                    #     右前臂轴（肘 364.5,553 → 腕 390,666）= −77.3°
                    #     hand_r_open 自带轴（腕枢轴 → 中指尖）   = −92.0°
                    #   ⇒ 手件**天生就比前臂外偏 14.7°**，rot=0 时就已经歪了；
                    #     再加 +21 脉冲 + 16 正弦 + 9 跟随滞后 = 峰值外折 **约 60°**，
                    #     人的腕关节尺偏极限才 25~30°（online.xknowledge.co.jp/37415/）。
                    #   所以脉冲改成 **−15°**：正好抵掉手件自带的 14.7°，让手严丝合缝
                    #   接着前臂；摆幅 16 → 12，峰值偏角落在 ±12°（自然范围内）。
                    #   证据：logs/asset_qa/q47_wrist_sweep.png 六档扫描，
                    #   −40° 那一档（≈ 本次定稿）手才是"接着小臂往上"的。
                    #   Q50：腕是鞭梢最后一节 —— 再晚 0.18s 起步，并且过冲 4°
                    #   再收回（miracle-usausa「手首の動きが肘より少し遅れる」）。
                    {"target": "hand_r", "param": "rot_deg", "interp": "smooth",
                     "keys": [[0.0, 0.0], [0.18, 0.0], [0.55, -8.0],
                              [0.88, -19.0], [1.10, -13.6], [1.30, -15.0]]},
                    {"target": "hand_r", "param": "rot_deg", "wave": "sine",
                     "amp": 12.0, "freq": 2.2, "phase": 0.18, "dur": 2.4},
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

        # ======== 双手挥手（第四十六问用户点名新增）========
        #
        # 口径：**把单手挥手的那套定案值整体镜像到左臂**，一个数都不重新拍脑袋。
        #   单手那套（Q43~Q45 四轮实拍定下来的）：
        #     上臂 A_u=34°（命令 −19，dur 0.45）、肩上提 26px（ParamShoulderRY 8.67）
        #     肘 A_f=166°（命令 −132，dur 0.70）、前臂收窄 1.0（ParamForeSlimR）
        #     腕 +21° 回正 + ±16° ひらひら（dur 0.9 / freq 2.2）
        #   左臂是镜像的：旋转角取反（rot_deg 正负相反），而**抬肩/收窄/张开手
        #   这三个是标量幅度，左右同号**。
        #
        # 两处**故意不做成完全镜像**：
        #   ① 手腕的相位差 0.18 vs 0.30 —— 两只手严丝合缝同相是机械感的来源，
        #      真人两手挥的节奏总差半拍（saraemi「左右で差をつける」）。
        #   ② 躯干不做 ParamBodyAngleZ 侧倾：单手挥是往抬手那侧让，
        #      双手挥两侧都抬，侧倾就成了多余的扭动。换成 ParamHipDrop 的
        #      上下起伏（和单手挥同一条曲线）+ 头部小幅点头。
        #
        # 为什么不复用 wave 的 part_overrides：mouth_open 0.8 照抄（打招呼要出声），
        # 另外两眼加 Smile 0.55 —— 双手挥是更兴奋的打招呼，眯眼笑是标配表情。
        if armp:
            # ★★★ Q48：两侧一起吃「前臂加长 + 上臂收回」。
            #   左臂**不能抄右臂的数**：原画里两条垂着的胳膊角度本来就不一样
            #   （右 上臂 162.4 / 前臂 115.8；左 上臂 166.4 / 前臂 114.9）。
            #   各自按「手不动、前臂 +26px」解三角形：
            #     右 A_u 33.8°→21.7°（−19 → −6.89）、A_f→153.7°（−134.12），内角 48.0°
            #     左 A_u 33.6°→22.1°（+19 → +7.49）、A_f→−152.2°（+134.15），内角 50.0°
            # ★★★ Q50：和单手挥手一样，从「单脉冲 ease:out」改成**关键帧曲线**。
            #   单脉冲的前重曲线 0.2s 就走完一半行程 ⇒ 整根前臂横扫过直角，
            #   这就是用户说的「直角直接翻过来」的机械感（证据
            #   logs/asset_qa/q50_wave_elbow_before.png）。
            #   右臂逐字照抄单手版；左臂镜像取反，并**整体晚 0.05s**（ずらし）
            #   —— 两只手严丝合缝同相本身就是机械感的来源。
            _WB_DT = 0.05       # 左臂整体延后（左右不同相）
            def _kl(keys, gain=1.0):
                """左臂：时间整体 +_WB_DT，幅度乘 gain（镜像的取负 gain）。"""
                return [[round(t + (_WB_DT if t > 0 else 0.0), 3), round(v * gain, 3)]
                        for t, v in keys]
            _K_SHO = [[0.0, 0.0], [0.08, 1.4], [0.30, -5.2], [0.45, -7.8],
                      [0.64, -6.5], [0.85, -6.89]]
            _K_ELB = [[0.0, 0.0], [0.10, -3.0], [0.26, -30.0], [0.44, -86.0],
                      [0.62, -124.0], [0.78, -141.0], [0.95, -132.0],
                      [1.12, -134.12]]
            _K_LONG = [[0.0, 0.0], [0.14, -0.75], [0.34, -1.0], [0.55, -0.35],
                       [0.72, 0.72], [0.88, 1.05], [1.05, 1.0]]
            _K_SHY = [[0.0, 0.0], [0.06, 0.0], [0.42, 7.4], [0.58, 9.3],
                      [0.78, 8.67]]
            _K_SLIM = [[0.0, 0.0], [0.10, 0.0], [0.50, 0.55], [0.80, 1.0]]
            _K_WRI = [[0.0, 0.0], [0.18, 0.0], [0.55, -8.0], [0.88, -19.0],
                      [1.10, -13.6], [1.30, -15.0]]
            wave_both_channels = [
                # —— 右臂：和单手挥手逐字一致 ——
                {"target": "arm_r", "param": "rot_deg",
                 "interp": "smooth", "keys": _K_SHO},
                {"target": "ParamShoulderRY", "interp": "smooth", "keys": _K_SHY},
                {"target": "ParamForeSlimR", "interp": "smooth", "keys": _K_SLIM},
                {"target": "ParamForeLongR", "interp": "smooth", "keys": _K_LONG},
                {"target": "forearm_r", "param": "rot_deg",
                 "interp": "smooth", "keys": _K_ELB},
                {"target": "forearm_r", "param": "rot_deg", "wave": "sine",
                 "amp": 5.0, "freq": 1.6, "dur": 2.4},
                # —— 左臂：角度镜像取反（终值 +7.49 / +134.15，比值 1.087 / 1.000），
                #   幅度类（抬肩/收窄/加长）同号，时间整体 +0.05s ——
                {"target": "arm_l", "param": "rot_deg",
                 "interp": "smooth", "keys": _kl(_K_SHO, -1.087)},
                {"target": "ParamShoulderLY", "interp": "smooth",
                 "keys": _kl(_K_SHY, 1.0)},
                {"target": "ParamForeSlimL", "interp": "smooth",
                 "keys": _kl(_K_SLIM, 1.0)},
                {"target": "ParamForeLongL", "interp": "smooth",
                 "keys": _kl(_K_LONG, 1.0)},
                {"target": "forearm_l", "param": "rot_deg",
                 "interp": "smooth", "keys": _kl(_K_ELB, -1.0002)},
                {"target": "forearm_l", "param": "rot_deg", "wave": "sine",
                 "amp": -5.0, "freq": 1.6, "dur": 2.4},
            ]
            if has_hands:
                wave_both_channels += [
                    {"target": "ParamHandROpen", "wave": "pulse",
                     "amp": 1.0, "dur": 0.10, "ease": "out"},
                    {"target": "ParamHandLOpen", "wave": "pulse",
                     "amp": 1.0, "dur": 0.10, "ease": "out"},
                    # ★ 腕角与单手版同一套口径（第四十七问）：脉冲 = 抵掉手件自带的
                    #   轴向偏差，让手接着前臂。**左右不对称**是对的 ——
                    #   右：前臂 −77.3° / hand_r_open −92.0° ⇒ 外偏 14.7° ⇒ 脉冲 −15；
                    #   左：前臂 −100.5° / hand_l_open −88.3° ⇒ 内偏 12.2° ⇒ 脉冲 +12。
                    #   （原画里两条胳膊垂下来的角度本来就不一样，镜像抄数会歪。）
                    # Q50：腕也改关键帧 —— 比肘再晚 0.18s（のこし＝鞭梢最末节）
                    {"target": "hand_r", "param": "rot_deg",
                     "interp": "smooth", "keys": _K_WRI},
                    {"target": "hand_r", "param": "rot_deg", "wave": "sine",
                     "amp": 12.0, "freq": 2.2, "phase": 0.18, "dur": 2.4},
                    {"target": "hand_l", "param": "rot_deg",
                     "interp": "smooth", "keys": _kl(_K_WRI, -0.8)},
                    {"target": "hand_l", "param": "rot_deg", "wave": "sine",
                     "amp": -12.0, "freq": 2.2, "phase": 0.30, "dur": 2.4},
                ]
            actions.append({
                "id": "wave_both", "priority": 6, "duration": 2.4,
                "return_state": "idle", "interruptible": False,
                "channels": wave_both_channels + [
                    {"target": "head", "param": "rot_deg", "wave": "sine",
                     "amp": 1.6, "freq": 1.6, "dur": 2.4},
                    {"target": "head", "param": "dy", "wave": "sine",
                     "amp": 1.2, "freq": 1.6, "dur": 2.4},
                    {"target": "ParamHipDrop", "wave": "sine",
                     "amp": 1.2, "freq": 1.6, "dur": 2.4},
                    {"target": "ParamEyeLSmile", "wave": "pulse",
                     "amp": 0.55, "dur": 0.5, "ease": "out"},
                    {"target": "ParamEyeRSmile", "wave": "pulse",
                     "amp": 0.55, "dur": 0.5, "ease": "out"},
                    {"target": "ParamHairAhoge", "wave": "sine",
                     "amp": 0.3, "freq": 1.2},
                    {"target": "ParamHairSide", "wave": "sine",
                     "amp": 0.2857, "freq": 1.2},
                ],
                "part_overrides": {"mouth_open": {"opacity": 0.8}},
            })

        if armp and has_hands:
            # ======== 比心（Q36 用户点名）========
            # 手腕落点是按两节连杆反算的，不是拍脑袋：
            #   肩 (523,464)、上臂 162px、前臂 116px，要把手送到胸口 (470,600)
            #   ⇒ 目标距离 146 ⇒ 余弦定理 肩夹角 43.9°、方向角 +21.3°
            #   ⇒ 上臂 −22.6°、前臂相对 +119.6°（肘内角 120°，人能做）。
            #   前臂横过胸口后手是"指向左上"的，心会倒过来，所以腕再回折 −52°
            #   （人的腕掌屈 80°，52° 在范围内），心便立起来、略带倾斜 —— 和真人比心一样。
            actions.append({
                "id": "heart_hands", "priority": 6, "duration": 2.8,
                "return_state": "idle", "interruptible": False,
                "channels": [
                    # ↓ 角度不是估的：正向运动学搜 (上臂,前臂,腕) 使
                    #   ①心形中心落在胸口 ②手世界角≈180°（指尖朝上，心才立得正）。
                    #   右：目标 (470,552) → 实际 (473,549)，离正立 0°
                    #   左：目标 (378,552) → 实际 (374,549)
                    #   肘 131° < 人的极限 145°、腕 55° < 70°，都做得到。
                    {"target": "arm_r", "param": "rot_deg", "wave": "pulse",
                     "amp": -6.0, "dur": 0.45, "ease": "out"},
                    {"target": "forearm_r", "param": "rot_deg", "wave": "pulse",
                     "amp": 131.0, "dur": 0.50, "ease": "out"},
                    {"target": "hand_r", "param": "rot_deg", "wave": "pulse",
                     "amp": 55.0, "dur": 0.55, "ease": "out"},
                    {"target": "arm_l", "param": "rot_deg", "wave": "pulse",
                     "amp": 2.0, "dur": 0.50, "ease": "out"},
                    {"target": "forearm_l", "param": "rot_deg", "wave": "pulse",
                     "amp": -127.0, "dur": 0.55, "ease": "out"},
                    {"target": "hand_l", "param": "rot_deg", "wave": "pulse",
                     "amp": -55.0, "dur": 0.6, "ease": "out"},
                    # 手型换成"心"
                    {"target": "ParamHandRHeart", "wave": "pulse",
                     "amp": 1.0, "dur": 0.12, "ease": "out"},
                    {"target": "ParamHandLHeart", "wave": "pulse",
                     "amp": 1.0, "dur": 0.12, "ease": "out"},
                    # 心跳：手往前送两下 + 上身跟着轻轻一顿
                    {"target": "hand_r", "param": "rot_deg", "wave": "sine",
                     "amp": 4.0, "freq": 1.1, "phase": 0.25},
                    # 上身：ParamBodyAngleZ ±10 → chest.rot_deg ×0.25，
                    # 5.6 = 1.4° 的轻微侧顿（chest.rot_deg 没进 GEO2PARAM，直接写参数）
                    {"target": "ParamBodyAngleZ", "wave": "sine",
                     "amp": 5.6, "freq": 1.1},
                    # 表情：歪头 + 笑眼 + 脸红
                    {"target": "head", "param": "rot_deg", "wave": "pulse",
                     "amp": 6.0, "dur": 0.6, "ease": "out"},
                    {"target": "ParamEyeLSmile", "wave": "pulse", "amp": 1.0,
                     "dur": 0.35, "ease": "out"},
                    {"target": "ParamEyeRSmile", "wave": "pulse", "amp": 1.0,
                     "dur": 0.35, "ease": "out"},
                    {"target": "ParamCheek", "wave": "pulse", "amp": 0.9,
                     "dur": 0.5, "ease": "out"},
                    {"target": "ParamHairSide", "wave": "sine", "amp": 0.22, "freq": 0.9},
                ],
                "part_overrides": {"mouth_open": {"opacity": 0.45}},
            })

            # ======== 芳文跳（きららジャンプ）========
            # 用户要它来"体检"全身骨骼：一个动作同时动到 根/胸/头/双肩/双肘/双腕/
            # 双髋/双膝/双踝/头发/裙子 —— 哪一节是死的立刻看得出来。
            # 资料（dic.pixiv.net「きららジャンプ」）：主角团一排同时起跳、镜头偏下、
            # 姿势各异、常有人高举双手；jstage 的两脚跳跃研究：起跳相
            # 髋/膝/踝先屈后伸，落地反过来。时间线（总 2.0s）：
            #   0.00~0.30 预蹲（髋沉、膝屈、手臂后摆）
            #   0.30~1.10 腾空（root 抬 80px、双臂上举成 V、绷脚尖）
            #   1.10~2.00 落地回弹
            actions.append({
                "id": "kirara_jump", "priority": 7, "duration": 2.0,
                "return_state": "idle", "interruptible": False,
                # airborne：鞋底纵向净位移 px —— 这个动作就是要离地。
                # 数值由 selfcheck_repo 按通道幅度×绑定复算，对不上就红。
                "airborne": 60,
                "channels": [
                    # ======== 起跳的相位（Q36 二次复核重写）========
                    # 第一版是两条 bounce 波叠出来的：实拍（12 帧 ×0.12s 测鞋底）
                    #   0.12s 就到顶、0.48s 已经落地，而双臂 1.6s 才举到位 ——
                    #   **等于先落地再举手**，而且只离地 40px(整身 1360)，根本看不出在跳。
                    # 波形天生是对称的单拱，做不出"蹲-蹬-飘-落-缓冲"这种不对称节奏，
                    # 所以这几条改成**关键帧通道**（引擎已支持，≈ Live2D 的 .motion3）。
                    # 相位表按两脚跳跃的生物力学分段（股関節・膝・足関節 屈曲→伸展）。
                    # 高度卡着**画布上边**定，这是硬约束：静止时头顶（呆毛尖）离画布
                    # 上边只有 40px(预览)＝73px(rig)，腾空 120px 时实拍头顶 y=0 ——
                    # 被切平的其实不是手而是**呆毛**。所以腾空封顶 60px、留 13px 余量。
                    # 想跳得更高只能把整张画布加高重切，不是调这里能解决的（记在待办）。
                    #   0.00–0.26 预蹲（胯沉、膝屈、脚不离地）
                    #   0.26–0.52 蹬伸（踝跖屈、髋膝伸直）
                    #   0.52–0.86 滞空（最高点 −120px，约一个头的高度）
                    #   0.86–1.06 落地
                    #   1.06–1.40 缓冲蹲 → 站直
                    {"target": "root", "param": "dy", "interp": "smooth",
                     "keys": [[0.0, 0.0], [0.26, 0.0], [0.52, -47.0], [0.69, -60.0],
                              [0.86, -47.0], [1.04, 0.0], [2.0, 0.0]],
                     "note": "滞空弧线：上行 0.43s、下行 0.35s（下落比上抛略快，像有重力）"},
                    # 预蹲 + 落地缓冲。ParamHipDrop 的行程是 ±1，顶格就是最深的蹲。
                    {"target": "ParamHipDrop", "interp": "smooth",
                     "keys": [[0.0, 0.0], [0.22, 4.5], [0.42, -1.2], [0.65, 1.5],
                              [0.88, 0.3], [1.08, 3.6], [1.35, 0.6], [1.75, 0.0]],
                     "note": "预蹲 4.5（=胯沉 9px）→ 蹬伸 −1.2（腿绷直拉长，squash&stretch 的 stretch）"
                             "→ 滞空 1.5（空中膝盖是收着的）"
                             "→ 落地缓冲 3.6 → 站直"},
                    # —— 双臂上举成 V（芳文跳的标志）。举臂要和腾空同相：
                    #    预蹲时先往后下摆一点（反蓄力），0.72s 举到顶、落地后才放下。
                    #    上臂 150°＝举过头顶往外张 30°，人的肩屈曲极限 180°，做得到。
                    {"target": "arm_l", "param": "rot_deg", "interp": "smooth",
                     "keys": [[0.0, 0.0], [0.22, -14.0], [0.58, 104.0], [0.72, 134.0],
                              [1.25, 132.0], [1.75, 30.0], [2.0, 0.0]]},
                    {"target": "arm_r", "param": "rot_deg", "interp": "smooth",
                     "keys": [[0.0, 0.0], [0.22, 14.0], [0.58, -104.0], [0.72, -134.0],
                              [1.25, -132.0], [1.75, -30.0], [2.0, 0.0]]},
                    # 肘略带一点弯（完全笔直像木偶），落地时再甩一下
                    {"target": "forearm_l", "param": "rot_deg", "interp": "smooth",
                     "keys": [[0.0, 0.0], [0.3, -8.0], [0.75, 18.0], [1.25, 15.0],
                              [1.8, 4.0], [2.0, 0.0]]},
                    {"target": "forearm_r", "param": "rot_deg", "interp": "smooth",
                     "keys": [[0.0, 0.0], [0.3, 8.0], [0.75, -18.0], [1.25, -15.0],
                              [1.8, -4.0], [2.0, 0.0]]},
                    # 手摊开（欢呼的手不能是握着的）
                    {"target": "ParamHandLOpen", "wave": "pulse",
                     "amp": 1.0, "dur": 0.12, "ease": "out"},
                    {"target": "ParamHandROpen", "wave": "pulse",
                     "amp": 1.0, "dur": 0.12, "ease": "out"},
                    {"target": "hand_l", "param": "rot_deg", "wave": "sine",
                     "amp": 16.0, "freq": 1.1, "phase": 0.25},
                    {"target": "hand_r", "param": "rot_deg", "wave": "sine",
                     "amp": 16.0, "freq": 1.1, "phase": 0.25},
                    # —— 腿：预蹲时微内收 → 滞空外张并收起 → 落地回正
                    # ★ Q37 自查：滞空那一帧 ±3.2° 会让两条小腿在画面上**绞在一起**
                    #   （实拍 logs/asset_qa/q37_ankle.png 第二格），收到 ±1.8°。
                    {"target": "leg_l", "param": "rot_deg", "interp": "smooth",
                     "keys": [[0.0, 0.0], [0.24, 0.9], [0.69, -1.8], [1.04, 0.5],
                              [1.4, 0.0]]},
                    {"target": "leg_r", "param": "rot_deg", "interp": "smooth",
                     "keys": [[0.0, 0.0], [0.24, -0.9], [0.69, 1.8], [1.04, -0.5],
                              [1.4, 0.0]]},
                    # —— 踝：蹬地跖屈（绷脚尖）→ 落地背屈吃冲击
                    # ★ Q37 自查收窄（原来 ±11°）：脚件是绕踝做**画面内旋转**，
                    #   而袜口是一条平口横切、鞋领盖不住转出来的那一侧 ——
                    #   超过 ±5° 袜子边就会错出一截白台阶（扫参数图
                    #   logs/asset_qa/q37_ankle_sweep.png：0/±3 干净，±7 起明显）。
                    #   这和第三十五问肘关节是同一个病（LESSONS 312：两边都要收半圆），
                    #   根治要重做脚件的袜口 → 留账 T46.31；在那之前**行程压在安全区内**，
                    #   绝不让画面出现错位（用户第三十三问：不许断裂/割裂/错位）。
                    {"target": "foot_l", "param": "rot_deg", "interp": "smooth",
                     "keys": [[0.0, 0.0], [0.26, 2.0], [0.60, -4.0], [0.86, -3.4],
                              [1.04, 1.6], [1.35, 0.0]]},
                    {"target": "foot_r", "param": "rot_deg", "interp": "smooth",
                     "keys": [[0.0, 0.0], [0.26, -2.0], [0.60, 4.0], [0.86, 3.4],
                              [1.04, -1.6], [1.35, 0.0]]},
                    # —— 头/脸：抬头 + 笑眼 + 张嘴欢呼
                    {"target": "head", "param": "rot_deg", "wave": "sine",
                     "amp": -3.0, "freq": 0.5},
                    {"target": "ParamEyeLSmile", "wave": "pulse", "amp": 1.0,
                     "dur": 0.35, "ease": "out"},
                    {"target": "ParamEyeRSmile", "wave": "pulse", "amp": 1.0,
                     "dur": 0.35, "ease": "out"},
                    {"target": "ParamCheek", "wave": "pulse", "amp": 0.7,
                     "dur": 0.4, "ease": "out"},
                    # —— 头发/裙子：腾空时整个人往上走，发梢和裙摆要慢半拍再跟上
                    {"target": "ParamHairFluffy", "wave": "bounce",
                     "amp": 0.85, "dur": 1.5, "ease": "out"},
                    {"target": "ParamHairBack", "wave": "bounce",
                     "amp": -0.7, "dur": 1.3, "ease": "out"},
                    {"target": "ParamHairBackS", "wave": "sine",
                     "amp": 0.45, "freq": 0.75, "phase": 0.3},
                    {"target": "ParamHairFront", "wave": "bounce",
                     "amp": -0.5, "dur": 1.2, "ease": "out"},
                    # 裙摆/外套**不在这里写**：摆动参数由物理 2.0 的摆链驱动，
                    # 挂到动作上的话一切走别的待机动作就僵住（selfcheck
                    # 「摆动参数没有被挂进动作里」拦的就是这个）。腾空时裙子
                    # 自己会被 root 的位移甩起来。
                ],
                "part_overrides": {"mouth_open": {"opacity": 0.9}},
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
            # 前臂挂在上臂下面：枢轴 = 肘关节，父组旋转自动继承
            # ★★★ 2026-10-21 第三十三问：优先用 make_arm_parts 量出来的
            #   elbow_joint（= 肘线上袖子横截面的中点，也就是肘关节正圆的**圆心**）。
            #   anchors 里的 elbow_* 是按身高比例估的，右侧实测偏外 3px；
            #   枢轴和圆心只要不重合，那个圆就不再是旋转不变量，
            #   前臂一弯肘外侧就会啃进去一牙（用户说的「割裂」）。
            el_l = apt("elbow_l", 0.428, 0.172)
            el_r = apt("elbow_r", 0.428, 0.825)
            _ej = armp.get("elbow_joint") or {}
            if _ej.get("l"):
                el_l = [ox + float(_ej["l"][0]), oy + float(_ej["l"][1])]
            if _ej.get("r"):
                el_r = [ox + float(_ej["r"][0]), oy + float(_ej["r"][1])]
            if _ej:
                print("[rig] 肘枢轴用 arm_parts.elbow_joint: l=%s r=%s" % (el_l, el_r))
            groups["forearm_l"] = {"pivot": el_l, "parent": "arm_l"}
            groups["forearm_r"] = {"pivot": el_r, "parent": "arm_r"}
            # ★★★ Q50：肘内侧褶布的「角平分线」组。
            #   父组是**上臂**、枢轴同肘，转角由 ParamArm?B 绑成前臂的一半
            #   （前臂 scale ∓18 → 这里 ∓9）。布夹在两根骨头中间，角度天然
            #   取平分线：前臂折多少它跟一半，永远卡在两管之间不会穿帮。
            #   没有褶布件就不建组（空组会被 check_assets 判废）。
            if any(p["id"] in ("arm_l_gusset", "arm_r_gusset")
                   for p in armp.get("parts", [])):
                for _s, _el in (("l", el_l), ("r", el_r)):
                    if any(p["id"] == "arm_%s_gusset" % _s
                           for p in armp.get("parts", [])):
                        groups["elbow_fold_%s" % _s] = {
                            "pivot": _el, "parent": "arm_%s" % _s}
            # G4c2：手挂在前臂下面，枢轴 = 袖口下沿那条实测的腕线（make_arm_parts 量的）
            for hp in armp["parts"]:
                if hp["id"] in ("hand_l", "hand_r"):
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
            # ★ Q37：原来「左顾右盼」只动眼球 + 歪头 1.5° —— 头**根本不转**。
            #   后果有两层：① 光转眼珠不转头，本身就不像人；
            #   ② 头发的物理输入是"头这一帧被带着走了多少像素"，头不动 ⇒
            #      输入恒为 0 ⇒ 头发永远是死的（用户："动一下头头发顺着头飘"）。
            #   补一条真正的摇头：±17°，**比眼球晚 0.13 个周期**——
            #   官方/教程口径都是「視線が先、頭が後」（眼睛先锁定目标，头再跟上去）。
            # Q38：17° → 22°。参考图 characters/xiaoxun/design/pose_ref/hair_turn.png
            # （"头转过去、头发顺势甩出来"那张）画的是 25° 上下的侧转，
            # 实拍我们 17° 时发缘摆幅只有 18~21px（≈头宽 13~15%，
            # logs/asset_qa/q38_hair_sway.png 三格），看得见但偏含蓄。
            # 头发的滞后是物理算出来的，**驱动角越大、甩出来的幅度越大**，
            # 所以这里直接把驱动量提到参考那个量级（仍远低于 ParamAngleX ±30 的量程）。
            {"target": "ParamAngleX", "wave": "sine", "amp": 22.0, "freq": 0.45,
             "phase": 0.13},
            # 头转过去的时候下巴也略抬一点，转头才有体积感（不是平面旋转）
            {"target": "ParamAngleY", "wave": "sine", "amp": 4.0, "freq": 0.9,
             "phase": 0.3},
        ]
        actions.append(look)

    # 星星眼（T39 / AC-34）：一次完整的"哇——"表演。
    # 和表情 star_eyes 的分工：表情是**状态**（设上就一直是星星眼），
    # 动作是**一段演出**（亮起来 → 保持 → 收回去），自己会回 idle。
    # 节奏参考日文教程里キラキラ的用法：不是常亮，而是"笑着睁大眼的那一下"才出现。
    if star_eyes:
        actions.append({
            "id": "star_eyes", "priority": 6, "duration": 3.4,
            "return_state": "idle", "interruptible": True, "fade": 0.15,
            "channels": [
                # 开门曲线：0.28s 亮满（out_back 会小过冲一下，像"啪"地点亮），
                # 中间保持，最后 0.6s 收回去。
                {"target": "ParamStarEye", "interp": "smooth",
                 "keys": [[0.0, 0.0], [0.28, 1.0], [2.8, 1.0], [3.4, 0.0]]},
                # 眼睛睁大一点点 + 瞳孔略放大：星星要有地方放
                {"target": "ParamEyeOpen", "interp": "smooth",
                 "keys": [[0.0, 0.0], [0.3, 0.25], [2.8, 0.2], [3.4, 0.0]]},
                {"target": "ParamEyeBallForm", "interp": "smooth",
                 "keys": [[0.0, 0.0], [0.3, 0.35], [2.8, 0.3], [3.4, 0.0]]},
                {"target": "ParamMouthForm", "wave": "pulse", "amp": 0.8,
                 "dur": 0.45, "ease": "out"},
                {"target": "ParamMouthOpenY", "interp": "smooth",
                 "keys": [[0.0, 0.0], [0.3, 0.28], [2.6, 0.22], [3.4, 0.0]]},
                {"target": "ParamCheek", "wave": "pulse", "amp": 0.7,
                 "dur": 0.5, "ease": "out"},
                {"target": "ParamEyeSparkle", "wave": "pulse", "amp": 1.0,
                 "dur": 0.35, "ease": "out"},
                # 身体：轻轻往前探一下 + 歪头（卖萌的标准姿态），再加一点弹跳
                {"target": "ParamAngleZ", "interp": "smooth",
                 "keys": [[0.0, 0.0], [0.5, -5.0], [1.7, 4.0], [2.9, -2.0], [3.4, 0.0]]},
                {"target": "head", "param": "dy", "wave": "sine",
                 "amp": 1.6, "freq": 1.1, "dur": 3.4},
            ],
        })

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

            # ── 兽耳 / 尾巴的「点播」动作（T63.2，用户 2026-10-24 点名）──
            # 为什么要有：耳朵抖和尾巴甩平时都是**自发**的（tail_flick 排班，
            # neutral 情绪下 5~14 秒才一次）。想确认"到底会不会动"，盯着屏幕
            # 等十几秒还不一定撞上 —— 修好了也看不出来，坏了也发现不了。
            # 给一个能主动点的按钮，就从"等它发生"变成"让它发生"。
            # 这不只是测试工具：命令她抖抖耳朵本来就该是产品里的一个动作。
            # fade 0.05：抽动的峰值落在**第 72 毫秒**，而默认淡入是 220 毫秒 ——
            # 等淡入走完，这一下早抖完了，实测峰值被削掉 3.2 倍（0.528 → 0.167）。
            # 这跟 tiptoe 那条注释是同一个坑：**短促动作的峰值不能比淡入还早**。
            # 抽动本来就该是"啪"的一下，淡入给 0.05 秒就够接住，不会有突变感。
            {"id": "ear_twitch", "priority": 6, "duration": 0.6, "fade": 0.05,
             "return_state": "idle", "flick_trigger": "ParamEar",
             "note": "抖耳朵。decay = 急出缓回的阻尼振荡，和 tail_flick 自发抽动"
                     "同一个形（exp 包络 × 正弦），所以点出来的和自己抖的看着是"
                     "**同一只猫**。左右**故意错开**：真猫一只一只地抖，"
                     "两只同时等幅抖是机械玩具。右耳 dur 短一点、幅度小一点，"
                     "freq 也差一档，叠在一起不会出现对称的节拍。",
             # ★ 耳朵**不由这个动作的通道去画**，而是 flick_trigger 点一下
             #   既有的自发抽动机制。三个理由：
             #   ① 兽耳是可选挂件（"每种可一键关"），没挂猫耳时参数根本不存在；
             #   ② 摆动参数写进动作通道会违反 T45.9 红线（一换待机动作就停）；
             #   ③ 点出来的那一下和它自己抖的**走同一段代码**，不会一眼假。
             "channels": [
                 # 抖耳朵时头会跟着微微一动 —— 官方《クオリティアップのヒント》：
                 # 局部动而身体完全不动，看着就是贴图在动，不是生物在动。
                 {"target": "ParamAngleZ", "wave": "decay", "amp": 1.4,
                  "freq": 2.2, "dur": 0.7},
             ]},
            {"id": "tail_swish", "priority": 6, "duration": 0.9, "fade": 0.08,
             "return_state": "idle", "flick_trigger": "ParamAccTail",
             "note": "甩尾巴。四种尾巴姿态只有挂着的那个可见，所以四条都写上；"
                     "幅度系数照抄 tail_flick 的 flick_scale —— 四种姿态的 "
                     "root_rot_deg 差 14 倍，同一个 amp 会让竖起的尾巴甩出半个屏幕。",
             # 同上：尾巴交给 flick_trigger，不在动作通道里写摆动参数。
             "channels": [
                 {"target": "ParamAngleZ", "wave": "decay", "amp": 0.8,
                  "freq": 1.5, "dur": 1.2},
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
        ("root", "dy"):             ("ParamBaseY", -7.0),
        ("root", "rot_deg"):        ("ParamBaseRot", 0.5),
        (body_id, "bend_x"):        ("ParamBodyAngleX", 1.0),
        (body_id, "bend_y"):        ("ParamBodyAngleY", 0.4),
        ("arm_l", "dy"):            ("ParamShoulderY", -0.8),
        ("arm_r", "dy"):            ("ParamShoulderY", -0.8),
        ("arm_l", "rot_deg"):       ("ParamArmLA", 18.0),
        ("arm_r", "rot_deg"):       ("ParamArmRA", -18.0),
        # ★ 没做手臂拆件的形态（新形态刚起步时就是这样）：整条手臂只有 bend，
        #   param_list() 那边已经有对应的退路参数（ParamArmLA/RA 绑 seg_arm_*.bend_x），
        #   这里必须跟着给一条，否则动作表里的 seg_arm_*.bend_x 找不到参数，
        #   make_rig 直接退出 —— Q 版第一次跑就卡在这（2026-10-17）。
        **({} if armp else {("seg_arm_l", "bend_x"): ("ParamArmLA", -4.0),
                            ("seg_arm_r", "bend_x"): ("ParamArmRA", 4.0),
                            ("seg_arm_l", "bend_y"): ("ParamArmLB", 4.0),
                            ("seg_arm_r", "bend_y"): ("ParamArmRB", 4.0)}),
        ("forearm_l", "rot_deg"):   ("ParamArmLB", 18.0),
        ("forearm_r", "rot_deg"):   ("ParamArmRB", -18.0),
        ("hand_l", "rot_deg"):      ("ParamHandL", 22.0),
        ("hand_r", "rot_deg"):      ("ParamHandR", -22.0),
        # ★ Q36 腿脚真关节（髋回转 / 踝回转）
        ("leg_l", "rot_deg"):       ("ParamHipL", 0.9),
        ("leg_r", "rot_deg"):       ("ParamHipR", 0.9),
        ("foot_l", "rot_deg"):      ("ParamAnkleL", 1.2),
        ("foot_r", "rot_deg"):      ("ParamAnkleR", 1.2),
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
        # 必须和上面 ParamMouthOpenY 的 bind scale 一致，否则部件级通道换算出来的
        # 参数幅度会被放大/缩小。目前用到这条的两个动作（talk / surprised）都在
        # MOUTH_MERGE 里被手写曲线整体替换，换算结果不进 rig，但口径仍要对齐。
        ("mouth_open", "alpha"):    ("ParamMouthOpenY", -3.5),
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
    hand_forms = [f for f, suf in (handp or {}).get("poses", {}).items() if suf]
    PARAMS = param_list(mouth=mouth,
                        has_brows=any(p["id"] == "brow_l" for p in parts_list),
                        head_is_part=head_is_part,
                        jointed_arms=bool(armp),
                        has_blend=bool(blendp),
                        has_side=any(p["id"] == "hair_side_l" for p in parts_list),
                        has_legs=any(p["id"] == "seg_leg_l" for p in parts_list),
                        body_id=body_id,
                        has_eyeballs=any(p["id"] == "eye_l_ball" for p in parts_list),
                        foot_lift=(footp["lift_px"] if footp else None),
                        star_eyes=star_eyes, fx_table=fx_table,
                        hand_forms=hand_forms,
                        # Q45：有前臂件才有收窄形变器（上面 rig["deformers"] 那段
                        # 和这里用的是同一个判据：arm_?_fore + hand_? 都在）
                        slim_parts=tuple(
                            "arm_%s_fore" % s for s in ("l", "r")
                            if any(p["id"] == "arm_%s_fore" % s
                                   for p in (armp or {}).get("parts", []))
                            and any(p["id"] == "hand_%s" % s
                                    for p in (armp or {}).get("parts", []))),
                        # Q48：前臂加长要知道「肘→腕」这条轴的方向（静止姿势）
                        long_axes=_fore_long_axes(armp),
                        # Q48：肘关节补件（tools/elbow_cover.py 出的件）
                        elbow_parts=tuple(
                            p["id"] for p in (armp or {}).get("parts", [])
                            if p["id"].endswith("_elbow")),
                        # Q50：肘内侧褶布（tools/elbow_gusset.py 出的件）
                        gusset_parts=tuple(
                            p["id"] for p in (armp or {}).get("parts", [])
                            # Q51：盖线的 arm_?_seam 和填洞的 arm_?_gusset
                            # 共用同一条 alpha 曲线（同一个「折到位了没有」判据）
                            if p["id"].endswith(("_gusset", "_seam"))))
    PARAM_IDS = {q["id"] for q in PARAMS}
    # ★ Q36：裙摆/外套下摆这两个参数是在**本函数后半段**（里布、下摆模块）才
    #   append 进去的，可动作表在这里就要校验。素材在 = 参数一定会生成，
    #   所以提前登记，否则芳文跳里让裙子飘的那条通道会被当"缺素材"丢掉。
    if skirtp:
        PARAM_IDS.add("ParamSkirtSway")
    if jacketp:
        PARAM_IDS.add("ParamJacketSway")

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

    # ★ 2026-10-17（T2.2.5 新形态压力测试）：下面这些参数是**跟着素材走**的 ——
    #   素材（侧发/前发/眉毛/笑眼/星星眼/漫符…）没切出来，param_list() 就不会生成它们。
    #   但动作表是全角色共用的，照样会往这些参数上打通道。
    #   少女（素材齐）一条都不会命中这张表；新形态素材还没补齐时，
    #   命中的通道**丢掉并打印清单**，而不是让整个 rig 生不出来。
    #   不在这张表里的目标仍然按老规矩硬报错（防手滑写错参数名）。
    OPTIONAL_PARAM_IDS = {
        "ParamHairSide", "ParamHairFront", "ParamHairAhoge",
        "ParamBrowLY", "ParamBrowRY", "ParamBrowLAngle", "ParamBrowRAngle",
        "ParamBrowLForm", "ParamBrowRForm",
        "ParamEyeLSmile", "ParamEyeRSmile", "ParamEyeStar", "ParamEyePain",
        "ParamEyeWide", "ParamCheek", "ParamTear",
        # ★ Q36：裙摆/外套下摆/后发第二段也是"素材在才有"的参数
        #   （裙子里布、夹克下摆、后发分段各由各自的 make_*_parts.py 产出）。
        #   芳文跳要让它们一起飘，所以动作表里写了；素材没齐的形态丢掉即可。
        "ParamSkirtSway", "ParamJacketSway", "ParamHairBack", "ParamHairBackS",
        "ParamHairFluffy",
    }
    dropped_ch = {}

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

                # 本形态没有这件素材 → 参数不存在 → 丢掉这条通道（见 OPTIONAL_PARAM_IDS）
                if prop is None and tgt in OPTIONAL_PARAM_IDS:
                    dropped_ch.setdefault(tgt, []).append(a["id"])
                    continue

                key = (tgt, prop)
                if key in GEO2PARAM and GEO2PARAM[key][0] not in WRITABLE_PARAM_IDS \
                        and GEO2PARAM[key][0] in OPTIONAL_PARAM_IDS:
                    dropped_ch.setdefault(GEO2PARAM[key][0], []).append(a["id"])
                    continue
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
    if dropped_ch:
        # 素材没齐的形态会走到这里。清单必须打出来，否则「动作变少了」会变成哑故障。
        print("  ⚠ 本形态缺素材，丢掉了这些动作通道（补齐素材后自动恢复）：")
        for pid in sorted(dropped_ch):
            print(f"      {pid:<18} ← {len(dropped_ch[pid])} 条（{','.join(sorted(set(dropped_ch[pid])))}）")

    # —— 高清切件（T30.1）：有 @2x 就改用它，scale 乘 0.5 ——
    #
    # 为什么放在这里而不是 part() 里：parts_list 有十几处构造点
    # （part() 只是其中一个，还有眼/嘴/眉/发/鞋各自直接拼 dict 的地方）。
    # DC41 的教训是"一个行为有几条入口，修一条不等于修好"，
    # 所以统一在**组装完成之后、写出之前**扫一遍，只有这一个落点，漏不了。
    #
    # 画布坐标完全不动：pos 还是画布坐标，anchor 是比例，
    # 变的只有素材像素密度和与之配套的 scale。
    #
    # ⚠ 标量 scale 和数组 scale 在引擎里语义**不同**，换算方式也不同（G111）：
    #   · 标量 `"scale": s`  → zrig 的 p->scale，通道是**乘性**的：
    #       最终 = s × p_s   → s 减半 + 素材翻倍 = 任何 p_s 下都等价，绑定不用动。
    #   · 数组 `"scale": [sx,sy]` → zrig 的 p->scale_x/scale_y，通道是**加性**的
    #       （compute_draw_state: part_sy = scale_y + (p_sy - 1.0)）：
    #       scale_y 减半了，但绑定里的增量还是 1x 口径 → **位移整整放大 2 倍**。
    # T30.1 当时只减了 scale，没动绑定，于是嘴张到最大从 22px 变成 41px，
    # 下沿直接越过下巴长到脖子上（用户第三次验收截图）。所以这里必须一起减。
    hires_used = 0
    hires_additive = set()          # 换了 @2x 且 scale 是数组 → 绑定增量要跟着减半
    if base:
        for _p in parts_list:
            _f = _p.get("file", "")
            if not _f.endswith(".png") or _f.endswith("@2x.png"):
                continue
            _cand = _f[:-4] + "@2x.png"
            if not os.path.exists(os.path.join(base, _cand)):
                continue
            _p["file"] = _cand
            _sc = _p.get("scale", 1.0)
            # 把 1× 口径的 scale 留在件上：闸门要验的是「几何没变」，
            # 也就是 scale == scale_1x × 0.5。以前闸门直接写死"必须等于 0.5"，
            # 那等于假设所有件的 1× scale 都是 1.0 —— 闪光件 1× 就是 0.68/0.45
            # （一张素材复制成大中小），立刻误报（2026-10-16 实测）。
            _p["scale_1x"] = _sc if not isinstance(_sc, list) else list(_sc)
            if isinstance(_sc, list):
                _p["scale"] = [round(_sc[0] * 0.5, 6), round(_sc[1] * 0.5, 6)]
                hires_additive.add(_p["id"])
            else:
                _p["scale"] = round(_sc * 0.5, 6)
            _p["hires"] = 2         # 自述：素材像素密度 ×2，几何口径已按 2 换算过
            hires_used += 1
        if hires_used:
            print(f"[rig] 高清切件 {hires_used}/{len(parts_list)} 个用上 @2x（scale ×0.5）")

    # —— 加性通道的绑定跟着减半（G111）——
    # 落点只有这一个：绑定全在 PARAMS 里，动作/表情经 to_param_channels 之后
    # 一律是参数级通道（下面那条断言就是守这个前提的）。
    if hires_additive:
        _halved = 0
        for _pr in PARAMS:
            for _b in _pr.get("binds", []):
                if _b.get("param") in ("sx", "sy") and _b.get("part") in hires_additive:
                    _b["scale"] = round(_b["scale"] * 0.5, 6)
                    _b["hires_halved"] = True       # 闸门按这个标记查有没有漏
                    _halved += 1
        # 负向断言：万一哪天有人把部件级 sx/sy 写回动作轨，这里立刻拦住，
        # 不要等到用户看见一张拖到下巴的嘴才发现（DC41：一个行为多条入口）。
        for _a in actions:
            for _c in _a.get("channels", []):
                _t = str(_c.get("target", ""))
                if "." in _t:
                    _pid, _ch = _t.split(".", 1)
                    if _ch in ("sx", "sy") and _pid in hires_additive:
                        raise SystemExit(
                            f"[make_rig] 动作 {_a['id']} 直接写了 {_t}，"
                            f"而 {_pid} 是 @2x 加性缩放件 —— 这条通道不会被减半换算，"
                            f"请改成参数级通道")
        print(f"[rig]   其中 {len(hires_additive)} 个是数组 scale（加性通道），"
              f"已把 {_halved} 条 sx/sy 绑定一并减半")

    rig = {
        "schema_version": "1.0",
        "id": f"{name}_teen",
        "name": name,
        "canvas": {"w": cw, "h": ch},
        "origin": [cw // 2, ch],
        "ground_line": ch - 8,
        "groups": groups,
        # 眼球左右 ±4px / 上下 ±2.5px：满格 ParamEyeBallX/Y = look_around 动作的幅度。
        # micro = 眼球微动（マイクロサッカード）。cgbox「目の動きのクオリティアップ」：
        #   「人の眼球は静止していることはありません」—— 瞳孔常驻微游移能明显提升"活着"的感觉；
        #   同篇反面警告「やりすぎると…常に慌てている印象になる」。
        # amp 的单位是归一化视线（±1 = max_offset 的 4.0px），所以 amp 0.25 ≈ ±1.0px。
        # 具体取值是**实测标定**出来的，不是拍的：见 tools/calib_saccade.py 的输出。
        "gaze": {"max_offset": [4.0, 2.5],
                 "micro": {"amp": SACC_AMP, "gap_min": 0.45,
                           "gap_max": 1.60, "speed": 16.0}},
        # 指针跟随：眼睛看过去的同时，头和上身也跟着转一点
        # （Live2D 的 ParamAngleX/Y + ParamBodyAngleX）。
        # 幅度刻意保守：头 5° + 4px，上身 1.2° + 1.5px —— 再大就"摇头晃脑"了。
        "look": {
            "speed": 9.0,
            # 反动/刹车。Live2D 官方《クオリティアップのヒント》：
            # 「反動、ブレーキを付ける —— 人間はピタッと瞬時に動きをとめることができません」
            # 0.30 ⇒ 阻尼比 0.70，欠阻尼但只冲过约 4.6%：看得出是活的，不会像果冻。
            "overshoot": 0.30,
            "groups": {
                # dy 10：ParamAngleY 满格 = 头上下 10px = surprised 缩脖子那下的幅度。
                # 动作和指针跟随写的是同一个参数，幅度也必须是同一套（官方就是这么做的）。
                "head": {"rot_deg": 5.0, "dx": 4.0, "dy": 10.0},
                # lag_s：身子比头**晚 0.10 秒**到。同一篇官方技巧的第一条 ——
                # 「顔XYZと体XYZを慣性を意識してタイミングをずらす。
                #   顔と体がまったく同じタイミングで動くと、やはりロボットのように見えます」
                # 在这之前头和胸读的是同一瞬间的值，正是那句话说的机器人。
                "chest": {"rot_deg": 1.2, "dx": 1.5, "dy": 1.0, "lag_s": 0.10},
            },
        },
        "blink": {
            "enabled": True,
            "closing_s": 0.10, "closed_s": 0.05, "opening_s": 0.15,
            "interval_min_s": 2.0, "interval_max_s": 8.0, "interval_exponential": False,
            # 眨眼频率随情绪漂移（T44.2）。基线 [2,8]s = 均值 5s = 12 次/分，
            # 比成人实测的 15~20 次/分稍慢一点 —— 这是**故意的**：大森ら(1997)
            # 的对人认知实验发现"眨眼多的人"会被评价为缺乏力动性、诚实性与亲近感，
            # 桌宠常态该偏少。情绪倍率就在这个基线上浮动。
            # 依据逐条见 docs/REFERENCE_NOTES.md 第二十九批，摘要：
            #   · 怒り/興奮 → 非常に多くなる（Ponder & Kennedy 1927；中野珠実）
            #   · 緊張・不安 → 増える，不安傾向と瞬目率に高い正の相関（Harris 1966）
            #   · 難しい課題に向かう時も急激に増加（≠ 盯着看，那是减少）
            #   · 覚醒水準の低下（疲労）→ 瞬目率は増加、かつ一回が長くなる
            #     ⇒ sleepy 不是"眨得少"，是"眨得慢而久"，所以给 closed_scale
            "mood_rate": {
                "angry":    {"rate": 1.70},
                "surprise": {"rate": 1.50},
                "shy":      {"rate": 1.40},
                "think":    {"rate": 1.30},
                "sad":      {"rate": 1.20},
                "sleepy":   {"rate": 1.15, "closed_scale": 3.0},
                # 亲近感那一侧反过来压：少眨眼 = 从容、可信（大森ら 1997）
                "affection": {"rate": 0.80},
                "smile":    {"rate": 0.90},
                "happy":    {"rate": 1.00},
                "cute":     {"rate": 1.00},
                "neutral":  {"rate": 1.00},
            },
            "note": "参数与 Live2D CubismEyeBlink 的五态机一致：等待 → 闭合 → 保持 → 睁开",
        },
        "parts": parts_list,
        "regions": regions,
        "actions": _name_actions(actions),
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
            # ★ 呆毛的左右甩**已经迁到物理 2.0**（T47.2），见下面的 rig["physics2"]。
            #   旧的 ahoge_x / ahoge_tip 两条弹簧摆删掉了：它们输出的是"滞后量"，
            #   人一停下就恒等于 0。上下点头（ahoge_y）还留在旧内核上 ——
            #   那是纵向弹跳，2D 摆链沿重力方向本来就不产生摆角，换过去没有意义。
            {"id": "ahoge_y", "part": "hair_ahoge", "driver": "head", "axis": "y",
             "param": "bend_y", "curve": "root",
             "ratio": 0.62, "stiffness": 40, "damping": 5.1, "max": 9,
             "note": "呆毛上下点头（Q37 调强：.45/55/6.0/5 → .62/40/4.6/9，"
                     "点头时呆毛要能甩出来）"},
            # G4c2：手腕滞后（物理输入 = 腕点被前臂组带着走了多少像素）。
            # 这是"鞭梢"的最后一节：大臂带小臂、小臂带手，手永远慢半拍。
            {"id": "hand_l_lag", "part": "hand_l", "driver": "forearm_l", "axis": "x",
             "param": "rot_deg",
             "ratio": 0.22, "stiffness": 34, "damping": 4.4, "max": 6,
             "note": "手腕跟随滞后：部件锚点就在腕上，所以 rot_deg 绕腕转"},
            {"id": "hand_r_lag", "part": "hand_r", "driver": "forearm_r", "axis": "x",
             "param": "rot_deg",
             "ratio": 0.22, "stiffness": 34, "damping": 4.4, "max": 6,
             "note": "第四十七问：上限 9 → 6。滞后是叠在腕角上的，"
                     "9° 会把峰值推出人的尺偏极限"},
            {"id": "bangs_x", "part": "hair_front", "driver": "head", "axis": "x",
             "param": "bend_x", "curve": "tip",
             "ratio": 0.5, "stiffness": 44, "damping": 5.6, "max": 9,
             "note": "刘海吊在额头上，发梢在下 → 曲线 tip，幅度要小。"
                     "Q37 从 .3/65/7.5/4 调强：前髪は1段で十分但不能是死的"},
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
        # ★ 力场（T47.3）。官方叫 Meta.EffectiveForces，只有 gravity/wind 两个常量；
        # breeze 是我们加的"常驻微风"——角色站着不动也有的那一点点空气流动。
        # ★ 量纲说清楚：风以"几个 g"计（内核里 力 = 重力单位向量 × Acceleration + 风），
        #   所以 0.03 看着小，其实已经是重力的 3%，发梢 10 秒能走 15px（无风时 8.9px）。
        # ★ Y 轴向下：重力是 (0, +1) 不是 (0, −1)。
        "forces": {
            "gravity": [0, 1],
            "wind": [0, 0],
            "breeze": {"amp": 0.03, "hz": 0.11},
        },
        # ★★ 物理 2.0 的摆链（T47.2）：官方那种 2D 粒子链，输出是**摆角**。
        # 和上面那张 physics 表的区别，一句话：
        #   physics  输出 = pos − target（滞后量）⇒ 输入不动，输出必然是 0 ⇒ 人一静止就死了；
        #   physics2 输出 = 摆相对重力的角度      ⇒ 重力常在，呼吸那点微动也能一直推着它晃。
        # 四个旋钮的名字照抄官方编辑器（DC70）：
        #   radius=長さ  mobility=揺れやすさ(0.7~0.99)  delay=反応速度  acceleration=収束の速さ
        "physics2": [
            {
                "id": "ahoge2", "part": "hair_ahoge", "driver": "head",
                # 歪头时呆毛要往反方向倒一点（官方 Input Type=Angle 的用法）。
                # 权重只给 0.3：头本身已经转了 ParamAngleZ×0.5，这里只补"头发没跟上"的那份。
                "angle_input": [{"param": "ParamAngleZ", "weight": 0.3}],
                # 呼吸混进物理输入 —— 社区那条著名配方。它在官方引擎成立、在旧内核不成立
                # （旧的输出是滞后量，0.28Hz 的呼吸摆锤完全跟得上，差值≈0，实测只摆 0.3px）。
                # 换成摆角之后它才真的有用：这是"静止时也活着"的唯一来源（T47.3 的风是第二个）。
                "input": [{"param": "ParamBreath", "wx": 1.4, "wy": -0.8}],
                # 输入限幅 = 官方 Normalization 在像素空间的等价物。
                # 没有它的话，参数一瞬跳（比如调试端点把 ParamAngleX 从 −30 打到 +30）
                # 发根单帧瞬移上百像素，摆会被甩过头顶转圈（实测单帧 179°）。
                "input_max": 20, "input_rate": 300,
                "particles": [
                    {"radius": 0, "note": "根：钉在发根，被头带着走"},
                    {"radius": 30, "mobility": 0.95, "delay": 1.2, "acceleration": 1.0},
                    {"radius": 20, "mobility": 0.92, "delay": 1.08, "acceleration": 1.2},
                ],
                "outputs": [
                    {"particle": 1, "param": "bend_x", "curve": "root",
                     "scale": 1.1, "max": 8,
                     "note": "整根呆毛左右甩。max 8 和旧的 ahoge_x 一样，"
                             "所以同一个转头动作下的像素行程是同量级的"},
                    {"particle": 2, "deformer": "ahoge_s", "scale": 0.06, "max": 2.6,
                     "note": "梢再慢半拍，甩出 S 形（旧的 ahoge_tip 干的活）。"
                             "★ 上限 2.6 = 实测满量程摇头峰值 1.98 的 1.3 倍，"
                             "不是 1.0 —— 1.0 时一次满量程摇头会让呆毛梢"
                             "贴顶 0.40 秒，那 0.40 秒里它在画面上是静止的"
                             "（2026-10-18 T46.3 顺手查出来的，和长发/双马尾/马尾同病）"},
                ],
                "note": "呆毛（T47.2 第一条迁过来的链）。短、硬、反应快 —— "
                        "教程口径「固い髪は反応速度を大きく」",
            },
        ],
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
                                       has_pain_eyes=any(p["id"].endswith("_pain")
                                                         for p in parts_list),
                                       has_wide_eyes=any(p["id"].endswith("_wide")
                                                         for p in parts_list),
                                       has_smile_eyes=any(p["id"].endswith("_smile")
                                                          for p in parts_list),
                                       has_star=bool(star_eyes)),
    }


    # —— 前臂「折起时收窄」网格形变器（Q45，A5 = ワープデフォーマ）——
    # 为什么要收窄：见 param_list() 里 fore_slim() 的注释（前臂 1.55:1 太粗，
    # 折起来整条压在上臂上）。做法是沿**前臂自己的轴线**（肘→腕这条线，不是图片
    # 中心线）按行横向压缩：
    #     r=0 肘关节     0%   —— 必须和上臂末端的正圆严丝合缝，一个像素都不能动
    #     r=1           10%
    #     r=2           15%   —— 最窄处在前臂中段（真人的前臂也是这里最细）
    #     r=3           12%
    #     r=4 袖口       6%   —— **袖口几乎不缩**：手件往袖子里续的腕柄半对角 20.6px
    #                            只比袖口半宽 22.5px 小 2px，缩多了腕柄就从袖口左边
    #                            探出来变成一条白边（10× 实拍 q45_cuff.png 验过）。
    #   压缩中心取**该行的肘→腕轴线**（不是图片中心线）：手是另一组、不跟着缩，
    #   轴心对不齐的话袖口会横着甩开，手看上去就和袖子错位。
    # 控制点位移写的是**源素材（@2x）像素**，引擎按 src->w/img->w 自动折算。
    if armp:
        _fore_f = (0.0, 0.10, 0.15, 0.12, 0.06)
        _apart = {q["id"]: q for q in armp.get("parts", [])}
        for _side in ("l", "r"):
            _fp = _apart.get("arm_%s_fore" % _side)
            _hp = _apart.get("hand_%s" % _side)
            if not _fp or not _hp:
                continue
            _px, _py = _fp["pos"]
            _w1, _h1 = _fp["size"]
            _ex, _ey = _fp["pivot"][0] - _px, _fp["pivot"][1] - _py   # 肘（局部 1x）
            _wx, _wy = _hp["pivot"][0] - _px, _hp["pivot"][1] - _py   # 腕（局部 1x）
            if abs(_wy - _ey) < 1e-6:
                continue
            _slope = (_wx - _ex) / (_wy - _ey)
            _pts = []
            for _r, _f in enumerate(_fore_f):
                if _f <= 0.0:
                    continue
                _cx2 = 2.0 * (_ex + (_h1 * _r / 4.0 - _ey) * _slope)  # 该行轴线 x（@2x）
                for _c in range(3):
                    _dx = (_cx2 - (2.0 * _w1) * _c / 2.0) * _f
                    if abs(_dx) > 0.05:
                        _pts.append({"c": _c, "r": _r, "dx": round(_dx, 2)})
            rig["deformers"].append(
                {"id": "arm_%s_fore_slim" % _side, "part": "arm_%s_fore" % _side,
                 "cols": 2, "rows": 4,
                 "note": "前臂折起时沿肘→腕轴线横向收窄（肘端 0%、袖口 17%）；"
                         "0 = 原件，静止画面零改动",
                 "points": _pts})

            # —— Q48：同一件上再挂一张「沿轴加长」网格 ——
            #   收窄管粗细、加长管长短；一个部件的多张 deformer 在引擎里是
            #   **逐点累加**的（zrig.c draw 那段不是择一）。
            #   r=0 是素材顶边（在肘枢轴**之上**、与上臂重叠的那一截）：权重 0
            #   ⇒ 肘关节那一圈正圆一个像素都不动，折起来才不会裂缝。
            _ln = math.hypot(_wx - _ex, _wy - _ey)
            _ux, _uy = (_wx - _ex) / _ln, (_wy - _ey) / _ln
            _lpts = []
            for _r, _f in enumerate(FORE_LONG_F):
                if _f <= 0.0:
                    continue
                _dx = 2.0 * _ux * FORE_LONG_PX * _f
                _dy = 2.0 * _uy * FORE_LONG_PX * _f
                for _c in range(3):
                    _lpts.append({"c": _c, "r": _r,
                                  "dx": round(_dx, 2), "dy": round(_dy, 2)})
            rig["deformers"].append(
                {"id": "arm_%s_fore_long" % _side, "part": "arm_%s_fore" % _side,
                 "cols": 2, "rows": 4,
                 "note": "前臂折起时沿肘→腕轴线加长 %.0fpx（肘端 0、袖口满额，"
                         "袖口条纹那一格刚性平移）；0 = 原件，静止画面零改动"
                         % FORE_LONG_PX,
                 "points": _lpts})

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
        # —— 后发的第二段（T46.1）——
        # 为什么后发要单独一张网格、而且列数比侧发多：
        #   ① 后发是**有宽度的一整片**（量出来 x303..542 × y116..258，和脑袋同宽），
        #      教程明确「幅の大きいもの（後ろ髪・スカート）は変形パスだと形が歪む ⇒
        #      複数階層のワープデフォーマで作る」—— 和裙摆同一条路子；
        #   ② 后发的 ベジェ 分割，教程给的是 3×3（侧发 2×3、刘海 3×2）——
        #      比侧发多一列，因为要让左右两边的发量各走各的。
        # 行号：r=0 是素材顶边 = **发根/头顶剪影，一个像素都不许动**
        #（第一版把后发的 bend 写成 root 时整个头形在晃，教训已记在上面）。
        # 形状：中段 r1/r2 往一边、发梢 r3/r4 往另一边 = 一条 S。多段振り子的口径是
        #「振り子の一番下が毛先の動き、一番上が根元の動き」。
        # ★ 实测过的约束（见 LESSONS）：这个形态的「后发」其实是一顶**短发壳**，
        #   量出来 y116..258，而**露在外面的部分全在 y128..223** —— 也就是说它
        #   承担的是**头顶和脸侧的剪影**，y224 以下整段被脸和身体盖住。
        #   所以上面那几行一个像素都不能动（动了就是头型在晃，不是头发在飘），
        #   能摆的只有脸侧那一截下沿。rows 取 6 就是为了让 **y187 这条线落在网格行上**
        #   （r=3），把"固定区/可摆区"的分界线压在真实网格行上
        #   （裙摆那次的教训：峰值和分界必须落在真实网格行，否则会鼓在中间）。
        _BKS = {4: 2.5, 5: 7.0, 6: 12.0}     # 行 → 横位移（只有下沿三行）
        rig["deformers"].append(
            {"id": "back_s", "part": "hair_back", "cols": 3, "rows": 6,
             "note": "后发第二段（下沿）：r0~r3（头顶到 y187）全固定——那一段是头部剪影；"
                     "只有脸侧露出来的下沿甩动。最外两列比中列多甩一点，"
                     "中列整片藏在脑袋后面",
             "points": [
                 {"c": c, "r": r,
                  "dx": round(v * (1.0 if c in (0, 3) else 0.72), 3),
                  **({"dy": round(abs(v) * 0.10, 3)} if r == 6 else {})}
                 for r, v in _BKS.items() for c in (0, 1, 2, 3)
             ]})
        rig["physics"] += [
            # ★ Q37 调强（用户："动一下头，头发就顺着头飘着的那种自然效果"）。
            #   原来是 ratio .55 / stiff 46 / damp 5.4 / max 7 —— 实测一次满量程
            #   转头，发色重心单调地跟到位、**没有过冲也没有回摆**，等于头发是粘死的。
            #   三个数一起改才有"飘"：
            #     ratio↑  跟随量更大（头走 10px，发梢目标走 8.5px）
            #     stiff↓  ω=√26≈5.1rad/s（周期 1.2s）＝慢半拍才追上
            #     damp↓   ζ=3.6/(2√26)=0.35 ＜1 ⇒ **欠阻尼**，会过冲再荡回来，
            #             这正是"飘"的物理定义；教程口径「収束の速さ 0.4 前後でなめらか」
            #   max 7→16：7px 在 246px 宽的脑袋上肉眼基本看不见。
            {"id": "side_l_x", "part": "hair_side_l", "driver": "head", "axis": "x",
             "param": "bend_x", "curve": "tip",
             "ratio": 0.85, "stiffness": 26, "damping": 4.1, "max": 16,
             "note": "左侧发第一段：整缕跟着头甩，根固定所以曲线用 tip"},
            {"id": "side_l_tip", "part": "hair_side_l", "driver": "side_l_x",
             "deformer": "side_l_s",
             # ★ ratio 0.12 不是 1.0：第一段的输出是**像素**，第二段写进的是
             # **形变器量**（side_l_s 的满量程 1.0 ≈ 发梢甩出一个身位）。旧值 0.85
             # 等于拿 8px 去喂一个量程 1 的通道 ⇒ 永远贴在限幅上＝方波＝看着是
             # "硬生生跳一下"。物理 2.0 的链早就是这么标定的（outputs.scale 0.05~0.06）。
             "ratio": 0.12, "stiffness": 14, "damping": 3.0, "max": 1.6,
             "note": "左侧发第二段（梢）：串在第一段后面，比发根再慢半拍"},
            {"id": "side_r_x", "part": "hair_side_r", "driver": "head", "axis": "x",
             "param": "bend_x", "curve": "tip",
             "ratio": 0.85, "stiffness": 26, "damping": 4.1, "max": 16,
             "note": "右侧发第一段（数值同左侧，Q37 调强）"},
            {"id": "side_r_tip", "part": "hair_side_r", "driver": "side_r_x",
             "deformer": "side_r_s",
             "ratio": 0.12, "stiffness": 14, "damping": 3.0, "max": 1.6,
             "note": "右侧发第二段（梢）"},
            # —— 后发 ——
            {"id": "back_x", "part": "hair_back", "driver": "head", "axis": "x",
             "param": "bend_x", "curve": "tip",
             "ratio": 0.5, "stiffness": 34, "damping": 4.9, "max": 10,
             "note": "后发第一段（根）：整团壳慢半拍地晃（Q37 从 .22/72/8.0/3.5 调强；"
                     "幅度大了会从脸边上露出来，所以 max 只给到 10px＝头宽的 4%）"},
            # T46.1 后发第二段（梢）。串在 back_x 后面，和呆毛/侧发同一套写法。
            # 数值刻意**比侧发更钝**：教程口径「固い髪＝反応速度を大きく、
            # ボブや長い後ろ髪などゆったりした揺れ＝反応速度を小さく」，
            # 而且「軽いものほど揺れやすく早く収まる」—— 后发是最重的一团。
            #   侧发梢 stiffness 22 / damping 3.0 → 后发梢 15 / 3.4
            #   （ω=√15≈3.9rad/s，周期 1.6s；ζ=3.4/(2×3.87)=0.44，
            #     正好落在社区推荐的「収束の速さ 0.4 前後でなめらか」）
            {"id": "back_tip", "part": "hair_back", "driver": "back_x",
             "deformer": "back_s",
             "ratio": 0.10, "stiffness": 11, "damping": 2.8, "max": 1.4,
             "note": "后发第二段（梢）：串在 back_x 后面，比发根再慢一拍；"
                     "比侧发更软更慢（头发越重越慢）"},
        ]
        # —— 头发的自主飘动（第四十七问 / T46.56）——
        # ★ 病因和裙摆 T45.9 **一模一样**，当时只修了裙子，头发漏掉了：
        #   短发四件（刘海 hair_front / 侧发 hair_side_l,r / 后发 hair_back）
        #   的物理**只有 driver: head** 一个输入源，而本引擎物理输出的是
        #   「滞后量 pos − target」。待机时头几乎不动 ⇒ 滞后量 ≈ 0 ⇒ 头发是死的。
        #   实测（2026-10-23，idle 3 秒）：发团质心只晃 2.9px、左右边界各 2.0px，
        #   那 2px 还是头自己在动带出来的 —— 头发**自身没有任何飘动**。
        #   （挂件发型 long/twin/pony/ahoge 不受影响：它们走 physics2 摆链，
        #     链上已经混了 ParamBreath 当常驻输入，所以一直在轻轻飘。）
        # ★ 做法照搬裙摆那条成熟路子：一条自己的参数 + ambient drift 波，
        #   物理链照旧挂着，在这个自主飘动**之上**再叠头部带动的滞后。
        # ★ 波形用 drift 不用 sine：单条定频正弦是节拍器（T45.2g）。
        #   drift = 0.62·sin(ωt) + 0.26·sin(0.618ωt) + 0.12·sin(1.618ωt)，
        #   三条不可公度 ⇒ 肉眼看不出周期，像真的在被风吹。
        # ★ 频率：教程口径「軽いものほど揺れやすく、早く収まる」。
        #     尾巴（轻毛）0.21Hz ＞ **头发 0.19Hz** ＞ 裙子（厚百褶呢）0.13Hz
        # ★ 四件给**不同的 lag**（行波延迟）而不是同一个数：全身揺れ物同拍子摆
        #   是机械感的第二大来源。风从左脸扫到右脸、再到后发，所以
        #     侧发左 0 → 刘海 0.04 → 侧发右 0.09 → 后发 0.13 秒
        #   发梢那级（网格形变器）再各自多压半拍 ⇒ 发根先走、发梢后到。
        _have = {q["id"] for q in rig["parts"]}
        _dfms = {q["id"] for q in rig.get("deformers", [])}
        _hair_sway = []
        for _pid, _sc, _lg, _df, _dsc, _dlg in (
                ("hair_side_l", 7.2, 0.00, "side_l_s", 0.25, 0.17),
                ("hair_front",  3.0, 0.04, None,       0.0,  0.0),
                ("hair_side_r", 6.8, 0.09, "side_r_s", 0.22, 0.26),
                ("hair_back",   4.2, 0.13, "back_s",   0.17, 0.30)):
            if _pid not in _have:
                continue
            _hair_sway.append({"part": _pid, "param": "bend_x",
                               "scale": _sc, "curve": "tip", "lag": _lg})
            if _df and _df in _dfms:
                _hair_sway.append({"deformer": _df, "scale": _dsc, "lag": _dlg})
        # ★ 2026-10-24：**没有独立短发件的形态（Q 版）也要有这个参数**。
        #   Q 版头发整块烘焙在 seg_head 上（T2.2.5），四件短发一个都不存在 ⇒
        #   旧写法 `if _hair_sway:` 会把参数整个跳过，而四条挂件发型的 physics2
        #   摆链 input 里还写着 ParamHairSway ⇒ 引擎逐条校验失败、**整份 rig 拒载**，
        #   `/api/form?id=chibi` 静默退回少女（用户在界面上看到的就是"切不过去"）。
        #   这个参数的职责本来就有两半：①推短发件 ②当摆链的"风"输入。
        #   形态没有第一半时，第二半照旧要有 —— 所以 binds 允许为空。
        #   ★ 不能拿挂件发型件顶上第一半：那几件的 bend_x 是 physics2 的输出通道，
        #     同一通道再挂一条参数绑定就是两套内核叠加（selfcheck 有专门一条红线）。
        _hair_acc = ("acc_hair_long", "acc_hair_twin_l", "acc_hair_twin_r",
                     "acc_hair_pony", "acc_hair_pony_back")
        _need_wind = _hair_sway or any(q in _have for q in _hair_acc)
        if _need_wind:
            rig["params"].append({
                "id": "ParamHairSway", "label": "头发飘动",
                "min": -1.0, "max": 1.0, "default": 0.0,
                "binds": _hair_sway,
                "note": "头发自己飘：一条参数推四件短发（刘海/左右侧发/后发），"
                        "每件带不同的行波延迟 ⇒ 风从一侧扫到另一侧，"
                        "发梢那级再慢半拍。物理链 bangs_x/side_?_x/back_x "
                        "照旧挂着，在这个自主飘动之上再叠摇头带来的滞后。"
                        "幅度（侧发满格 7.2px ≈ 头宽的 3%）：第一版给 5.4px，实拍发梢\n"
                        "只摆 5.9px，肉眼要盯着才看得出来 ⇒ 提到 7.2px；\n"
                        "再大就会从脸侧甩出去，参考 "
                        "「意外と揺れを控えめにした方が自然に見える」"
                        + ("" if _hair_sway else
                           "。★ 本形态没有独立短发件（头发烘焙在 seg_head 上），"                           "所以这条参数的 binds 是空的：它只作为挂件发型四条摆链的"                           "风输入存在（ambient 照旧在推它），画面靠 physics2 输出。"),
            })
            rig.setdefault("ambient", []).append(
                {"target": "ParamHairSway", "wave": "drift",
                 "amp": 0.92, "bias": 0.0, "freq": 0.19})

    # ★ T66.16b：下面这一段（眉形/裙摆网格/裙摆参数/里布/外套下摆）原来**嵌在
    #   「有没有独立侧发件」那个 if 里面**。Q 版头发烘焙在 seg_head 上、没有
    #   hair_side_l ⇒ 整段被跳过 ⇒ 裙子切出来了却没有 ParamSkirtSway、没有网格，
    #   裙件成了孤儿部件（引擎当场拒载：deformers 里 skirt_root 既没 part 也没 parent）。
    #   判据换成「裙件（或躯干）在不在」，和短发件彻底解耦。
    if (skirtx or {}).get("id", "seg_torso") in {p["id"] for p in rig["parts"]}:
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
        # 数值表按**躯干**的行号写（躯干高 500、网格 10 行 ⇒ 行 r = y/50），
        # 因为这几个数是按"裙腰在躯干第 6 行"调出来的。裙子切出去之后网格挂在
        # 裙件上（裙件只有 222 行高），行号必须按几何重算 —— 否则同样一张表
        # 落到裙件上就变成"裙子中段才开始摆、裙腰狂摆"（第一版忘了换算，
        # 实拍裙腰整条横着滑出去）。
        _SKX_T = {6: 0.5, 7: 1.8, 8: 4.2, 9: 7.0, 10: 10.0}     # 横摆：越往下甩得越远
        _SKY_T = {6: 0.2, 7: 0.7, 8: 1.6, 9: 2.6, 10: 3.8}      # 纵摆：上下滞后
        # 下摆第二段：只有最下两行。数值取第一段同行的 ~30%——
        # 它是**叠加**在第一段之上的"再多甩一点"，不是替代。
        _SKHEM_T = {8: 0.6, 9: 1.9, 10: 3.4}

        def _remap(tbl, rows=10):
            """躯干行号 → 网格挂的那个部件自己的行号（没拆件时就是原样）。"""
            if not skirtx:
                return dict(tbl)
            top = float(skirtx["box_1x"][1])
            h = float(skirtx["box_1x"][3])
            thi = float(next(q for q in seg["parts"] if q["id"] == "seg_torso")["size"][1])
            out = {}
            for r, v in tbl.items():
                y = thi * r / rows
                nr = int(round((y - top) / max(1.0, h) * rows))
                nr = max(0, min(rows, nr))
                out[nr] = v if nr not in out else max(out[nr], v)
            return out

        _SKX, _SKY, _SKHEM = _remap(_SKX_T), _remap(_SKY_T), _remap(_SKHEM_T)
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
        # ★ T66.16（第六十六问 S3）：裙子已经从 seg_torso 里切出来了（tools/split_skirt.py）。
        #   网格跟着裙件走 —— 这是能不能给裙子接旋转骨的前提：骨链作用于**整个部件**，
        #   裙子还长在躯干上的时候给裙子插一根转骨，转起来会把整个上身带飞（G66.6）。
        _SKP = (skirtx or {}).get("id", "seg_torso")
        rig["deformers"] += [
            {"id": "skirt_sway_x", "part": _SKP, "cols": 2, "rows": 10,
             "note": "裙摆横摆：裙腰(r=6)固定，越往下甩得越远，中列比两侧多一点",
             "points": [
                 {"c": c, "r": r, "dx": round(v * (1.08 if c == 1 else 1.0), 3),
                  **({"dy": round(v * 0.09, 3)} if r == 10 else {})}
                 for r, v in _SKX.items() for c in (0, 1, 2)
             ]},
            # 第二段：**只有下摆**（最下两行）的额外横摆。
            # 教程里「服/头发看着硬」的头号原因就是「揺れが1段しかない —— 髪全体が
            # 棒のように一体で動いていると硬く見える」，解法是「根元と毛先で分けて
            # 2段にする」。幅のある布（スカート・後ろ髪）官方也明确建议用
            # **複数階層のワープデフォーマ**而不是单层变形路径（单层会把形状拧歪）。
            # 这一段由同一条参数驱动，但绑定带 lag（T45.2g 的行波延迟）⇒ 下摆比
            # 裙身慢半拍，这就是「親→子」的振り子顺序在本引擎里的等价写法。
            {"id": "skirt_hem_x", "part": _SKP, "cols": 2, "rows": 10,
             "note": "下摆第二段：只有最下两行再多甩一点，比裙身慢半拍（见参数 "
                     "ParamSkirtSway 的 lag）。幅度只有第一段的三成——"
                     "布越重越不该多摆，而且教程口径是「宁可摆小一点」",
             "points": [
                 {"c": c, "r": r, "dx": round(v * (1.06 if c == 1 else 1.0), 3)}
                 for r, v in _SKHEM.items() for c in (0, 1, 2)
             ]},
            {"id": "skirt_sway_y", "part": _SKP, "cols": 2, "rows": 10,
             "note": "裙摆纵摆：上下滞后，裙底顺带略微张开/收拢（布料的伞效应）",
             "points": [
                 {"c": c, "r": r, "dy": round(v * (1.1 if c == 1 else 1.0), 3),
                  **({"dx": round(v * (-0.32 if c == 0 else 0.32), 3)}
                     if (c != 1 and r >= 8) else {})}
                 for r, v in _SKY.items() for c in (0, 1, 2)
             ]},
        ]
        # ★ 裙件继承上身弯曲（T66.16）：切出去之后它不再吃 seg_torso 的 bend_x，
        #   不动的话上身一歪，裙腰和躯干之间就裂开一道横向的缝。
        #   系数不是 1.0 —— bend 曲线是 f(t)=(1−t)²，按**部件自己的高度**归一化。
        #   躯干上裙腰在 t≈0.56 处（f≈0.19），裙件上裙腰在 t≈0（f=1），
        #   所以裙件的 scale 取 0.19 才能让两边在裙腰处走出**同一个位移**。
        #   （这就是"把父部件的形变按高度摊到子部件"的手算版本；引擎的
        #     bend_follow 只能给刚性平移，做不出这个梯度。）
        if skirtx and _SKP != "seg_torso":
            for _pid, _geo, _sc, _cv in (("ParamBodyAngleX", "bend_x", 0.19, "root"),
                                         ("ParamBodyAngleY", "bend_y", 0.35, "sine")):
                for _q in rig["params"]:
                    if _q["id"] == _pid:
                        _q.setdefault("binds", []).append(
                            {"part": _SKP, "param": _geo, "scale": _sc, "curve": _cv})
                        _q["note"] = (_q.get("note", "") +
                                      "；裙件（%s）按高度摊到 %.2f 的同类形变" % (_SKP, _sc))

        rig["physics"] += [
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
            {"id": "skirt_x", "part": _SKP, "deformer": "skirt_sway_x",
             "input": [{"param": "ParamBodyAngleX", "weight": 1.0},
                       {"param": "ParamBodyAngleZ", "weight": 1.0}],
             "ratio": 0.12, "stiffness": 24, "damping": 6.5, "max": 1.0,
             "note": "裙摆横摆：上身左右倾/旋转带动，裙腰不动、裙底甩出去"},
            {"id": "skirt_y", "part": _SKP, "deformer": "skirt_sway_y",
             "input": [{"param": "ParamBodyAngleY", "weight": 1.0}],
             "ratio": 0.055, "stiffness": 19, "damping": 6.8, "max": 1.0,
             "note": "裙摆纵摆：上身上下起伏时裙摆滞后一拍，比横摆更钝"},
        ]
        # —— 裙摆的自主摆动（T45.9）——
        # ★ 为什么非加这条参数不可：裙摆原本**只靠物理输入**（ParamBodyAngleX/Z）。
        #   本引擎物理输出的是**滞后量 pos−target** 不是摆角，待机时身体几乎不动
        #   ⇒ 滞后量≈0 ⇒ 裙子是死的。实测 idle 60 秒 skirt_sway_x 峰峰值 0.0599、
        #   频率 0.058Hz（17 秒一个来回）。这正是尾巴 T45.2b 得出过的结论，
        #   当时只修了尾巴，裙摆漏掉了。Live2D 社区把这个症状叫
        #   「入力が小さいと振り子が 0 に吸着する」。
        # ★ 波形用 drift 不用 sine：同 T45.2g —— 单条定频正弦是节拍器。
        # ★ 参数差异化（教程：軽いものほど揺れやすく、早く収まる）：
        #     尾巴（轻毛）0.21Hz / 梢延迟 0.17s
        #     裙子（厚百褶呢）0.13Hz / 下摆延迟 0.11s —— 更慢、更小、延迟更短
        #   全身的揺れ物用同一组数 = 所有东西同拍子摆，是机械感的第二大来源。
        rig["params"].append({
            "id": "ParamSkirtSway", "label": "裙摆摆动",
            "min": -1.15, "max": 1.15, "default": 0.0,
            "binds": [
                {"deformer": "skirt_sway_x", "scale": 1.0},
                {"deformer": "skirt_hem_x", "scale": 1.0, "lag": 0.11},
            ],
            "note": "裙摆自己摆：一条参数推两级形变器，下摆那级带 0.11 秒行波延迟 "
                    "⇒ 裙身先走、下摆后到（動画の wave principle，也是 Live2D "
                    "「複数階層デフォーマ・親→子」的等价写法）。"
                    "物理链 skirt_x/skirt_y 照旧挂着，在这个自主摆动**之上**"
                    "再叠身体带动的滞后。幅度刻意压小——教程口径是"
                    "「意外と揺れを控えめにした方が自然に見える」",
        })
        # —— 裙子里布（T45.11）——
        # 里布不是"再摆一次"，而是**比表布摆得少**：差出来的那一条就是露出来的里子。
        # 幅度口径：里布跟到表布的 LIN_FOLLOW，再加一段延迟 ⇒ 甩出去的瞬间露得最多，
        # 停下来又收回去（布料的回り込み）。note.com/morris_343 的做法是把
        # 「スカート裏の全面の曲面」挂在主裙摆曲面的子级，这里是同一条参数两条形变器。
        if skirtp and seg:
            LIN_FOLLOW = 0.35
            LIN_ROWS = 4
            _lin = skirtp["parts"][0]
            # 两个盒子都取**身体图坐标**（*_parts.json 里的 pos/size），
            # 这样才能把里布的行号换算成表布形变器的行号。
            _tp = next(q for q in seg["parts"] if q["id"] == "seg_torso")
            _ty, _th = _tp["pos"][1], _tp["size"][1]
            _ly, _lh = _lin["pos"][1], _lin["size"][1]

            def _skirt_dx(r_float):
                """表布在躯干第 r 行（浮点）处的横向位移 = 第一段 + 下摆第二段。"""
                def _interp(tbl):
                    ks = sorted(tbl)
                    if r_float <= ks[0]:
                        return 0.0 if r_float < ks[0] else tbl[ks[0]]
                    if r_float >= ks[-1]:
                        return tbl[ks[-1]]
                    for a_, b_ in zip(ks, ks[1:]):
                        if a_ <= r_float <= b_:
                            t = (r_float - a_) / (b_ - a_)
                            return tbl[a_] * (1 - t) + tbl[b_] * t
                    return 0.0
                return _interp(_SKX) + _interp(_SKHEM)

            _pts = []
            for r in range(LIN_ROWS + 1):
                y_abs = _ly + _lh * r / LIN_ROWS
                r_torso = (y_abs - _ty) / _th * 10.0
                dx = round(_skirt_dx(r_torso) * LIN_FOLLOW, 3)
                for c in range(3):
                    _pts.append({"c": c, "r": r,
                                 "dx": round(dx * (1.06 if c == 1 else 1.0), 3)})
            rig["deformers"].append(
                {"id": "lining_sway_x", "part": _lin["id"], "cols": 2, "rows": LIN_ROWS,
                 "note": f"里布横摆：只跟到表布同高度位移的 {LIN_FOLLOW:.0%}，"
                         f"差额就是露出来的那条里子（表布 10px 时露 {10 * (1 - LIN_FOLLOW):.1f}px）",
                 "points": _pts})
            # ★ 按**名字**取 ParamSkirtSway，不要写 rig["params"][-1] ——
            #   「最后一个参数就是我刚 append 的那个」这种默认一旦在中间插进
            #   别的参数就会静默跑偏（第四十七问加 ParamHairSway 时当场踩中：
            #   里布的绑定被挂到头发飘动那条参数上去了）。
            _sk = next(q for q in rig["params"] if q["id"] == "ParamSkirtSway")
            _sk["binds"].append(
                {"deformer": "lining_sway_x", "scale": 1.0, "lag": 0.2})
            _sk["note"] += (
                "；里布（skirt_lining）同参数驱动，跟随系数 "
                f"{LIN_FOLLOW}、延迟 0.2s —— 甩出去时露出里子，收回来又藏回去")
            rig["physics"].append(
                {"id": "lining_x", "part": _lin["id"], "deformer": "lining_sway_x",
                 "input": [{"param": "ParamBodyAngleX", "weight": 1.0},
                           {"param": "ParamBodyAngleZ", "weight": 1.0}],
                 "ratio": 0.05, "stiffness": 18, "damping": 7.2, "max": 1.0,
                 "note": "里布的身体带动：比表布(skirt_x 0.12/24/6.5)更钝 —— "
                         "它夹在腿和表布中间，受的风小、摩擦大"})

        # —— 外套前襟下摆（T45.12）——
        # 做法和裙摆同源但**刻意更小**：note.com/majohope 的原话是
        # 「上着の揺れ。少し重い素材のイメージなので、**あまり揺らさないようにした**」。
        # 不切件：nnwarks「腕より後ろの服パーツを個別に揺らすのは非推奨、
        # 境目が飛び出しがち」—— 我们的原画又是烘焙的，切出来必然留洞。
        # 所以摆动做在躯干的网格上，**只推下摆那几行、只推前襟那两片的列**，
        # 中间开襟露出来的衬衫和裙腰一个像素都不动。
        # 几何（哪几行是下摆、哪几列是前襟）由 make_jacket_parts.py 量出来写进
        # jacket_parts.json —— 共用层里不许写死形态专属的数字（教训 128）。
        if jacketp and seg:
            JAC_AMP = 8.0          # 下摆最大横移（形变器单位）。裙摆同处是 10.0+3.4
            # ★ 网格尺寸不能自己挑：**同一部件上的多张网格要逐点相加，引擎要求同尺寸**
            #   （zrig 加载期会直接判错「6x34 vs 2x10」并拒载整份 rig）。
            #   所以这里照抄躯干上已有的那几张（裙摆用的 2x10）。
            _tdef = next((d for d in rig["deformers"] if d.get("part") == "seg_torso"), None)
            JAC_COLS = int(_tdef["cols"]) if _tdef else 2
            JAC_ROWS = int(_tdef["rows"]) if _tdef else 10
            _hem = jacketp["hem"]
            _tw, _th2 = _hem["torso_size"]
            _top, _bot2 = float(_hem["band_top"]), float(_hem["band_bottom"])
            _pan = [(float(q["x0"]), float(q["x1"])) for q in _hem["panels"]]
            # 过渡宽度要按**两片前襟之间的空当**来定，不能按列距 ——
            # 列只有 2 列时列距是半个躯干宽，照它取过渡会把中间的衬衫/裙腰
            # 一起推走（第一版实测中列权重 0.6，开襟处的扣子跟着平移）。
            _gap = min((b[0] - a[1]) for a, b in zip(_pan, _pan[1:])) if len(_pan) > 1 else _tw
            _edge = max(2.0, _gap * 0.3)

            def _wx(x):
                """这一列推不推：落在前襟上（或紧挨着）就推满，开襟中间不推。

                ★ 不做线性过渡：列只有 3 条，整条前襟都夹在「躯干外沿」和
                  「正中」之间，一做过渡，网格点上的值被打折，前襟内部
                  插值出来只剩两三成（第一版实测外沿只推到 3.4 而不是 8.0）。
                  改成二值之后，位移场就是「外沿最大 → 正中为 0」的线性梯度 ——
                  这恰好也是布的样子：靠外的襟摆甩得远，靠门襟的那侧被扣住。
                """
                for x0_, x1_ in _pan:
                    if x0_ - _edge <= x <= x1_ + _edge:
                        return 1.0
                return 0.0

            # 峰值行取**下摆底边之上最近的那条网格线**（teen: y=400.8，下摆底边 423）。
            # 于是 y 400~423 那段 —— 正好是棒球外套的**罗纹下摆**（teal 条纹那条）——
            # 位移从峰值衰减回 0：橡筋罗纹本来就贴着身体不该甩，鼓起来的是它上面的布。
            # 再往下（裙子那段）衰减量已经很小，不会把裙子拖着走。
            _row_h = _th2 / JAC_ROWS
            _peak_r = max(1, int(_bot2 // _row_h))
            _jpts = []
            for r in range(JAC_ROWS + 1):
                y = _row_h * r
                if y <= _top or r > _peak_r:
                    continue
                wy = (y - _top) / max(1.0, _row_h * _peak_r - _top)
                for c in range(JAC_COLS + 1):
                    dx = JAC_AMP * _wx(_tw * c / JAC_COLS) * wy
                    if abs(dx) > 1e-6:
                        _jpts.append({"c": c, "r": r, "dx": round(dx, 3)})
            rig["deformers"].append(
                {"id": "jacket_hem_x", "part": "seg_torso",
                 "cols": JAC_COLS, "rows": JAC_ROWS,
                 "note": f"外套前襟下摆横摆：腰线(y={_top:.0f})钉住、罗纹上沿"
                         f"(r={_peak_r}) 推到最大 {JAC_AMP}，再往下回零 —— "
                         f"罗纹和裙子不跟着走。中间开襟那一列恒为 0。"
                         f"幅度约为裙摆的六成：上着は重い素材",
                 "points": _jpts})
            rig["params"].append({
                "id": "ParamJacketSway", "label": "外套下摆摆动",
                "min": -1.0, "max": 1.0, "default": 0.0,
                "binds": [{"deformer": "jacket_hem_x", "scale": 1.0, "lag": 0.16}],
                "note": "外套下摆自己摆。比裙摆慢、比裙摆小：教程口径「上着は少し重い素材"
                        "なのであまり揺らさない」。lag 0.16 让它比裙摆（0.11）更迟钝，"
                        "两件衣服就不会同拍子动。摆动做在躯干的网格上而不是切件上："
                        "原画是烘焙的，切出来会留洞，教程也不建议把腕より後ろ的衣服"
                        "单独切开摆（境目が飛び出しがち）",
            })
            rig["physics"].append(
                {"id": "jacket_x", "part": "seg_torso", "deformer": "jacket_hem_x",
                 "input": [{"param": "ParamBodyAngleX", "weight": 1.0},
                           {"param": "ParamBodyAngleZ", "weight": 1.0}],
                 "ratio": 0.06, "stiffness": 30, "damping": 7.0, "max": 1.0,
                 "note": "外套下摆的身体带动：比裙摆(0.12/24/6.5)**幅度更小、刚度更高** —— "
                         "厚实的棒球外套，甩不远也停得快"})
            # 频率同样要和别人错开：猫耳 0.085 / **外套 0.105** / 裙摆 0.13 / 尾巴 0.21。
            # 幅度也最小（0.5，裙摆 0.72）—— 重的布摆得又小又慢。
            rig.setdefault("ambient", []).append(
                {"target": "ParamJacketSway", "wave": "drift",
                 "amp": 0.5, "bias": 0.0, "freq": 0.105})

        # 进 ambient 而不是 idle：见上面挂件摆动处的说明（T45.9）。
        rig.setdefault("ambient", []).append(
            {"target": "ParamSkirtSway", "wave": "drift",
             "amp": 0.72, "bias": 0.0, "freq": 0.13})


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


def prune_dead_param_refs(rig):
    """删掉物理输入里指向「本形态根本没有声明过的参数」的引用。

    ★ 2026-10-24（第六十一问）Q 版整份 rig 装不进引擎的真因：
      `prune_dangling` 只清理**部件/组**层面的悬空引用，参数层面漏了。
      Q 版缺 `hair_side_*` / `hair_front` / `hair_back`（头发整块烘焙在 seg_head 上，
      见 T2.2.5），于是 `ParamHairSway` 的四条绑定全被删、参数本身也被删 ——
      但**四条 physics2 摆链的 input 里还写着 ParamHairSway**。
      引擎在 zrig.c:1278 逐条校验 `physics2[].input[].param`，指不到就**整份拒绝加载**：
        `chibi/rig.json:4462 physics2[longhair2] input[1] 的参数 'ParamHairSway' 不存在`
      ⇒ `/api/form?id=chibi` 静默失败，画面退回少女。这类悬空引用只在
      「素材缺一半」的形态里出现，而新建形态永远从缺一半开始。

    ★ 为什么只扫物理、不扫表情/口型/情绪表：
      表情和眨眼/视线用的一批参数（ParamEyeOpen / ParamEyeBallY / ParamEyeLWide /
      ParamEyeLSmile / ParamEyeRPain …）是**引擎内置的虚拟参数**，不在 rig.params 里
      声明也是合法的（teen 的表情表就整片引用它们，而那些表情真的能挂上）。
      拿"在不在 params 里"去筛表情，会把 teen 13 条表情值当场删光 —— 实测过。
      物理链没有这种例外：input 只能是真实声明的参数（引擎逐条校验）。
      参数真的被删掉时（dead 集合），其余各处的引用由 prune_dangling 原本那段收拾。
    """
    defined = {q["id"] for q in rig.get("params", [])}
    dropped = []

    def _keep(lst, where):
        out = []
        for it in lst or []:
            nm = it.get("param") if isinstance(it, dict) else None
            if isinstance(nm, str) and nm not in defined:
                dropped.append(f"{where}→{nm}")
                continue
            out.append(it)
        return out

    for f in rig.get("physics", []) or []:
        if isinstance(f.get("input"), list):
            f["input"] = _keep(f["input"], f"physics:{f.get('id')}")
    for ch in rig.get("physics2", []) or []:
        for k in ("input", "angle_input"):
            if isinstance(ch.get(k), list):
                ch[k] = _keep(ch[k], f"physics2:{ch.get('id')}.{k}")

    if dropped:
        print(f"  ⚠ 本形态缺素材：删掉 {len(dropped)} 条悬空参数引用"
              f"（{', '.join(dropped[:6])}{' …' if len(dropped) > 6 else ''}）")


def emit_bone_chains(rig, base):
    """把已经是「平铺网格」的头发/尾巴接成**真正的骨链**（第六十六问 S2）。

    为什么非做不可
    --------------
    引擎上一轮已经能做变形器树（节点有 pivot + rot + parent，父包住子），
    但 rig 里**一件都没用**：25 个网格全部平铺挂在自己那个部件上、没有父子关系。
    表现是「头发能整块弯一下」，做不出 Live2D 那种「发根先动、发梢慢半拍追」的分层。

    这里按 Live2D 的标准结构插两层 **回転デフォーマ（旋转骨）**：
        hair_side_l_root（根，绕发根转） → hair_side_l_mid（中段，绕发中段转） → side_l_s（网格 S 形）
    并让部件显式挂到链尾（parts[].deformer）—— 这就是"每根骨都能独立驱动"的接线方式。

    三条硬约束（都踩过或算过）
    --------------------------
    1. **父节点必须先声明**（引擎加载时校验 parent 下标 < 子下标），所以追加完新节点后
       做一次稳定拓扑排序。不改父子关系的前提下顺序本来就只有一种，排序是幂等的。
    2. **只给"独立部件"接旋转骨**。裙摆的网格挂在 seg_torso 上，而 A_chain 会作用于
       **整个部件** —— 给裙子接一根旋转骨，转起来会把整个上身带飞（G66.6）。裙子得先拆件
       才能做骨链，这一轮不做，只记缺口。
    3. **静止必须是恒等**：新节点的 dx/dy/rot 默认 0、sx/sy 默认 1，引擎里恒等节点直接跳过
       ⇒ 不推参数时画面一个像素都不变（这条由 test_rig_zero_regress 之外的 md5 对比 + 单测守）。
    """
    parts = {p["id"]: p for p in rig.get("parts", [])}
    defs = {d["id"]: d for d in rig.get("deformers", [])}
    params = {q["id"]: q for q in rig.get("params", [])}
    new_nodes, binds = [], []

    def rect(pid):
        """部件在画布上的矩形（左上角 + 尺寸）。素材是 @2x，scale 已经在 part 里。"""
        p = parts.get(pid)
        if not p:
            return None
        sp = os.path.join(base, p.get("file", ""))
        wh = png_size(sp) if os.path.exists(sp) else None
        if not wh:
            return None
        sc = float(p.get("scale", 1.0) or 1.0)
        w, h = wh[0] * sc, wh[1] * sc
        ax, ay = (p.get("anchor") or [0.0, 0.0])[:2]
        x, y = p.get("pos", [0.0, 0.0])[:2]
        x0, y0 = x - w * ax, y - h * ay
        return (x0, y0, w, h)

    def add_chain(pid, mesh_ids, name, fy=0.55, root_fy=0.03, bind_param=None,
                  root_scale=0.0, mid_scale=0.0, mid_bind_param=None, mid_lag=0.08):
        """给一个部件插「根 → 中段」两根旋转骨，并把它的网格挂到中段下面。"""
        rc = rect(pid)
        if rc is None:
            return 0
        x0, y0, w, h = rc
        # ★ 先确认真有网格要挂，再建节点：没有任何网格的链是**非法结构** ——
        #   纯变换节点既没有 part 也没有 parent 时，引擎会判「它影响不到任何部件」
        #   并且**整份 rig 拒载**（Q 版第一次跑就撞上：skirt_main 切出来了，
        #   但 Q 版没有裙摆网格，skirt_root 于是成了孤儿节点 → chibi 加载失败）。
        if not any(d in defs and defs[d].get("part") == pid for d in mesh_ids):
            return 0
        cx = x0 + w * 0.5
        rid, mid = name + "_root", name + "_mid"
        # root_fy：发根在顶部（0.03），尾巴挂在髋部所以根在底部（0.97）——
        #   绕错一端的话，转起来是"尾巴尖钉住、整条尾甩身体"，看着像脱臼。
        new_nodes.append({"id": rid, "pivot": [round(cx, 1), round(y0 + h * root_fy, 1)],
                          "note": "%s 的根骨：绕发根/挂接点转，梢部才会被带起来" % name})
        new_nodes.append({"id": mid, "pivot": [round(cx, 1), round(y0 + h * fy, 1)],
                          "parent": rid,
                          "note": "%s 的中段骨：比根慢半拍，做出分层摆动" % name})
        n = 0
        for d in mesh_ids:
            if d in defs and defs[d].get("part") == pid:
                defs[d]["parent"] = mid
                defs[d]["note"] = (defs[d].get("note", "") +
                                   "；挂在中段骨 %s 下（S2 骨链）" % mid)
                n += 1
        if n:
            # 部件点名的是**链的根**。为什么不是中段：引擎要求"纯变换节点（没有 part、
            # 没有 parent）必须被某个部件点名"，根节点正好是这种节点；点中段的话
            # 根没人引用 → 整份 rig 拒绝加载（实测：`hair_ahoge_root` 既没有 part
            # 也没有 parent → teen 加载失败并静默退回 chibi）。
            # 链的标记是"从部件点名的节点往上走 + 从挂在它身上的网格往上走"取并集，
            # 所以点根和点中段算出来的链是同一整条。
            parts[pid]["deformer"] = rid
            parts[pid]["note"] = (parts[pid].get("note", "") +
                                  "；骨链 %s→%s（S2）" % (rid, mid))
        # 绑定顺序 = 从根到梢：根骨（无 lag）→ 中段骨（带 lag）→ 原有的网格（梢）。
        #   为什么中段必须有 lag：没有它根和梢**同相位**被推，看着就是一根刚性钟摆，
        #   而不是「根先动、梢追上来」的软组织（动画的 wave principle）。
        #   selfcheck 里有一条闸专门盯这个（梢部形变带行波延迟），尾巴那四条就是被它抓出来
        #   才补上的。
        if bind_param and bind_param in params and root_scale:
            binds.append((bind_param, rid, root_scale, 0.0))
        if (mid_bind_param or bind_param) in params and mid_scale:
            binds.append((mid_bind_param or bind_param, mid, mid_scale, mid_lag))
        return n

    made = 0
    # —— 侧发：根 + 中段 —— 由 ParamHairSide（整缕跟头甩）与 ParamHairSideS（S 形）分头驱动
    # 角度标定：侧发缕高约 132px，根骨绕顶端转、中段骨绕 55% 处转。
    #   θ 每 1° 在梢部约 2.2px（128px × sin1°），所以 2.6° + 5.2° ≈ 11px 的梢部位移，
    #   和原有 bend_x 的 7px 叠在一起是"看得见但不夸张"。第一版给 1.2/2.4 只有 5px，
    #   在 466px 宽的帧里几乎看不出来（截了图才发现）—— 角度的量级要按**像素**反算。
    made += add_chain("hair_side_l", ["side_l_s"], "hair_side_l",
                      bind_param="ParamHairSide", root_scale=-2.6,
                      mid_bind_param="ParamHairSideS", mid_scale=-5.2)
    made += add_chain("hair_side_r", ["side_r_s"], "hair_side_r",
                      bind_param="ParamHairSide", root_scale=2.6,
                      mid_bind_param="ParamHairSideS", mid_scale=5.2)
    # —— 后发：同上，但参数分开（后发比侧发更重、更钝） ——
    made += add_chain("hair_back", ["back_s"], "hair_back", fy=0.5,
                      bind_param="ParamHairBack", root_scale=-2.0,
                      mid_bind_param="ParamHairBackS", mid_scale=-4.0)
    # —— 呆毛：一根骨头从根甩到梢 ——
    made += add_chain("hair_ahoge", ["ahoge_s"], "hair_ahoge", fy=0.5,
                      bind_param="ParamHairAhoge", root_scale=5.0,
                      mid_bind_param="ParamHairAhogeS", mid_scale=4.0)
    # —— 尾巴：四种姿态各一根链（姿态件互斥，链条各归各的） ——
    for pose, param in (("relaxed", "ParamAccTailRelaxedSwing"), ("up", "ParamAccTailUpSwing"),
                        ("puff", "ParamAccTailPuffSwing"), ("tuck", "ParamAccTailTuckSwing")):
        # 尾巴没有单独的"梢"参数，根和中段吃同一个旋钮（比例 1:2，中段甩得更开）
        made += add_chain("acc_tail_cat_" + pose, ["tail_%s_s" % pose], "tail_" + pose,
                          fy=0.5, root_fy=0.97, bind_param=param,
                          root_scale=1.4, mid_scale=3.0, mid_lag=0.1)
    # —— 裙子（T66.16 / S3）：切出来之后才能接自己的转骨 ——
    #   ★ 顺序不能反：骨链作用于**整个部件**，裙子还长在 seg_torso 上的时候给裙子
    #     插一根转骨，转起来会把整个上身带飞（G66.6 记的就是这条）。
    #   root 在**裙腰**（piece 顶边往下 4%）—— 绕错端的话裙腰会跟着甩、裙摆钉住，
    #   看着像裙子从腰上撕下来。角度按像素反算：裙件高 ~222px，1° ≈ 3.9px，
    #   1.2°+2.6° 在裙摆处约 14px，比网格那套（10+3.4px）略大一点，合起来是
    #   "裙腰几乎不动、裙摆明显甩"。
    if "skirt_main" in parts:
        made += add_chain("skirt_main", ["skirt_sway_x", "skirt_hem_x", "skirt_sway_y"],
                          "skirt", fy=0.55, root_fy=0.04,
                          bind_param="ParamSkirtSway", root_scale=1.2,
                          mid_scale=2.6, mid_lag=0.11)
    if not made:
        return 0

    rig.setdefault("deformers", []).extend(
        {k: v for k, v in nd.items()} for nd in new_nodes)

    # 稳定拓扑排序：父节点必须排在子节点前面（引擎加载时逐条校验）。
    dl = rig["deformers"]
    order = {d["id"]: i for i, d in enumerate(dl)}
    out, placed = [], set()
    sys.setrecursionlimit(10000)

    def place(node):
        if node["id"] in placed:
            return
        par = node.get("parent")
        if par:
            pn = next((d for d in dl if d["id"] == par), None)
            if pn is not None:
                place(pn)
        if node["id"] not in placed:
            placed.add(node["id"])
            out.append(node)

    for nd in dl:
        place(nd)
    if len(out) != len(dl):        # 理论上不会，防御：成环就保持原样，让引擎去报错
        out = dl
    rig["deformers"] = out

    # 绑定：加到**已存在**的参数上（不新建参数，避免多一个没人用的旋钮）
    # 插到**最前面**，但要保持「根→中段」的先后：逐条 insert(0) 会把后插的排到前面
    # （第一版就这么把 mid 排到了 root 前面，闸当场报 'tail_up_root 没有 lag'）。
    # 所以同一个参数的链式绑定整体倒序插入。
    by_param = {}
    for param_id, node_id, scale, lag in binds:
        by_param.setdefault(param_id, []).append((node_id, scale, lag))
    for param_id, items in by_param.items():
        q = params.get(param_id)
        if q is None:
            continue
        for node_id, scale, lag in reversed(items):
            b = {"deformer": node_id, "param": "rot_deg", "scale": scale}
            if lag:
                b["lag"] = lag
            q.setdefault("binds", []).insert(0, b)
    return len(new_nodes)


def prune_dangling(rig):
    """把指向「本形态不存在的部件/组」的绑定清掉，连带清掉因此空掉的参数。

    ★ 2026-10-17（T2.2.5 新形态压力测试）：引擎 zrig.c 装载时会逐条校验 bind 的
      part/group 指得到指不到，指不到就**整份 rig 拒绝加载**（Q 版第一次进引擎：
      `params[ParamHairFront] part 'hair_front' 不存在` → 预览直接退回少女）。
      param_list() 是按「素材齐了」写的，新形态素材是一件一件补上来的，
      中间状态必然有悬空绑定。这里统一收口：
        · 绑定指不到 → 删这条绑定
        · 一个参数的绑定被删光（原来有） → 删这个参数，并把动作/ambient/表情/姿态里
          引用它的通道一并删掉，免得留下指向空气的曲线
      素材齐全的形态（少女）一条都删不掉 —— rig.json 逐字段不变，已实测。
    """
    part_ids = {q["id"] for q in rig.get("parts", [])}
    grp = rig.get("groups", {})
    grp_ids = set(grp) if isinstance(grp, dict) else {g["id"] for g in grp}

    def ok(b):
        if "part" in b and b["part"] not in part_ids:
            return False
        if "group" in b and b["group"] not in grp_ids:
            return False
        return True

    # 先扫一遍全树：任何「带 part/group 字段、但指不到」的条目整条删掉
    #（physics / deformers / xfades / poses.entries.parts / regions … 都走这条，
    #  不用一处处点名 —— 点名的写法上一轮就漏了 physics，引擎照样拒载）。
    dropped_items = []

    def sweep(node, path):
        if isinstance(node, dict):
            for k, v in list(node.items()):
                if k == "parts" and isinstance(v, list) and all(isinstance(x, str) for x in v):
                    node[k] = [x for x in v if x in part_ids]
                elif k in ("from", "to") and isinstance(v, str) and v not in part_ids \
                        and path.endswith("xfades"):
                    pass        # 整条 xfade 由下面的列表删除处理
                elif isinstance(v, (dict, list)):
                    sweep(v, f"{path}.{k}")
        elif isinstance(node, list):
            keep = []
            for it in node:
                bad = isinstance(it, dict) and (
                    (isinstance(it.get("part"), str) and it["part"] not in part_ids)
                    or (isinstance(it.get("group"), str) and it["group"] not in grp_ids)
                    or (path.endswith("xfades") and (it.get("from") not in part_ids
                                                     or it.get("to") not in part_ids)))
                if bad:
                    dropped_items.append(f"{path}:{it.get('id', it.get('part', '?'))}")
                    continue
                sweep(it, path)
                keep.append(it)
            node[:] = keep

    for key in ("physics", "physics2", "deformers", "xfades", "poses", "regions",
                "actions", "visemes", "expressions", "ambient", "param_groups"):
        if key in rig:
            sweep(rig[key], key)

    dropped_params, dropped_binds = [], 0
    keep_params = []
    for pm in rig.get("params", []):
        binds = pm.get("binds")
        if binds:
            good = [b for b in binds if ok(b)]
            dropped_binds += len(binds) - len(good)
            if not good:
                dropped_params.append(pm["id"])
                continue
            pm["binds"] = good
        keep_params.append(pm)
    if not dropped_params and not dropped_binds and not dropped_items:
        # ★ 部件/组全都在，不代表参数引用是对的（Q 版就是这么坏的）——
        #   参数这一层的清理无条件跑一遍。
        prune_dead_param_refs(rig)
        return
    if dropped_items:
        print(f"  ⚠ 本形态缺素材：删掉 {len(dropped_items)} 条指向空部件的条目"
              f"（{', '.join(dropped_items[:6])}{' …' if len(dropped_items) > 6 else ''}）")
    if not dropped_params and not dropped_binds:
        rig["params"] = keep_params
        prune_dead_param_refs(rig)
        return
    rig["params"] = keep_params
    dead = set(dropped_params)

    for a in rig.get("actions", []):
        a["channels"] = [c for c in a.get("channels", []) if c.get("target") not in dead]
    if isinstance(rig.get("ambient"), list):
        rig["ambient"] = [c for c in rig["ambient"] if c.get("target") not in dead]
    for e in rig.get("expressions", []):
        e["params"] = [q for q in e.get("params", []) if q.get("id") not in dead]
    for ps in rig.get("poses", []):
        for st in ps.get("states", []):
            if isinstance(st.get("params"), list):
                st["params"] = [q for q in st["params"] if q.get("id") not in dead]
    if isinstance(rig.get("param_groups"), list):
        for pg in rig["param_groups"]:
            if isinstance(pg.get("params"), list):
                pg["params"] = [q for q in pg["params"] if q not in dead]
    for key in ("mood_params", "mood_swing"):
        v = rig.get(key)
        if isinstance(v, dict):
            for mk in list(v):
                if isinstance(v[mk], list):
                    v[mk] = [q for q in v[mk]
                             if (q.get("id") if isinstance(q, dict) else q) not in dead]

    print(f"  ⚠ 本形态缺素材：删掉 {dropped_binds} 条悬空绑定"
          + (f"、{len(dropped_params)} 个因此空掉的参数（{','.join(dropped_params)}）"
             if dropped_params else ""))
    # 参数删完之后，物理/ambient/动作里可能还点名指着它们 —— 最后一并清掉。
    prune_dead_param_refs(rig)


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
    base_root = os.path.join(args.root, "characters", args.character)   # 角色级 design/（特效表在这里）
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
    # ★ Q36 手差分件（tools/make_hand_parts.py：放松/张开/比心 × 左右，程序化重画）
    handp = None
    hand_path = os.path.join(base, "sprites", "hand_parts.json")
    if armp and os.path.exists(hand_path):
        with open(hand_path, encoding="utf-8") as f:
            handp = json.load(f)
        miss = [a["id"] for a in handp["parts"]
                if not os.path.exists(os.path.join(base, a["file"]))]
        if miss:
            print(f"警告：手差分缺图 {miss}，退回底图切出来的手", file=sys.stderr)
            handp = None
    # 脚拆件（tools/make_foot_parts.py 的产物：常态鞋 + 踮脚鞋各两件）
    # 裙子里布（tools/make_skirt_parts.py 的产物：表布复制 + 乘法压暗）
    skirtp = None
    skirt_path = os.path.join(base, "sprites", "skirt_parts.json")
    if os.path.exists(skirt_path):
        with open(skirt_path, encoding="utf-8") as f:
            skirtp = json.load(f)
        miss = [a["id"] for a in skirtp["parts"]
                if not os.path.exists(os.path.join(base, a["file"]))]
        if miss:
            print(f"警告：裙子里布缺图 {miss}，跳过里布", file=sys.stderr)
            skirtp = None

    # 裙件拆件（tools/split_skirt.py 的产物：裙子从 seg_torso 里切出来 + のりしろ）
    skirtx = None
    skx_path = os.path.join(base, "sprites", "skirt_split.json")
    if os.path.exists(skx_path):
        with open(skx_path, encoding="utf-8") as f:
            skirtx = json.load(f)
        if not os.path.exists(os.path.join(base, "sprites", skirtx["id"] + ".png")):
            print("警告：裙件贴图不在，退回「裙子长在躯干上」的老结构", file=sys.stderr)
            skirtx = None

    # 外套前襟下摆（tools/make_jacket_parts.py 的产物：下摆带复制 + 压暗 = 裾断面の影）
    jacketp = None
    jacket_path = os.path.join(base, "sprites", "jacket_parts.json")
    if os.path.exists(jacket_path):
        with open(jacket_path, encoding="utf-8") as f:
            jacketp = json.load(f)
        if "hem" not in jacketp:
            print("警告：jacket_parts.json 里没有 hem 几何，跳过外套下摆摆动", file=sys.stderr)
            jacketp = None

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

    # 痛苦闭眼 / 瞪大眼真素材（make_eye_closed_parts.py --variant pain|wide 的产物）。
    # 和笑眼一样整组可选：没有 json 就退回"没有这一档"，rig 里连参数都不出现。
    pain_eyes, wide_eyes = None, None
    for _key, _name in (("pain", "pain_eyes"), ("wide", "wide_eyes")):
        _p = os.path.join(base, "sprites", f"eye_{_key}_parts.json")
        if not os.path.exists(_p):
            continue
        with open(_p, encoding="utf-8") as f:
            _j = json.load(f)
        if all(os.path.exists(os.path.join(base, "sprites", c["file"])) for c in _j["eyes"]):
            if _name == "pain_eyes":
                pain_eyes = _j
            else:
                wide_eyes = _j

    # 星星眼差分件（tools/make_star_eye_parts.py 的产物）：星形虹膜 + ✨ 素材。
    # 整组可选 —— 没有这份 json 时 rig 里就没有 ParamStarEye / star_eyes，
    # 其余一切照旧（这是差分件该有的性质）。
    star_eyes = None
    se_path = os.path.join(base, "sprites", "star_eye_parts.json")
    if os.path.exists(se_path):
        with open(se_path, encoding="utf-8") as f:
            star_eyes = json.load(f)
        need = [e["file"] for e in star_eyes["eyes"]] + [star_eyes["sparkle"]["file"]]
        miss = [k for k in need if not os.path.exists(os.path.join(base, k))]
        if miss:
            print(f"警告：星星眼差分件缺图 {miss}，整组跳过", file=sys.stderr)
            star_eyes = None

    # 声明式特效表（T43.2 / G117）。✨ 的层号、参数名、门控、动法原来全写死在
    # 本文件里，现在只从这张表读。**没有兜底默认值** —— 表缺了就炸，
    # 免得源码里又藏一份影子配置（那正是 G117 要消灭的东西）。
    fx_table = {}
    fx_path = os.path.join(base_root, "design", "effects.json")
    if os.path.exists(fx_path):
        with open(fx_path, encoding="utf-8") as f:
            for e in json.load(f)["effects"]:
                fx_table[e["id"]] = e
    if star_eyes and "sparkle" not in fx_table:
        raise SystemExit(f"[make_rig] 有 ✨ 差分件但 {fx_path} 里没有 id=sparkle —— "
                         f"特效的几何/动法必须在表里声明（T43.2）")

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
                base=base,
                seg=seg, anchors=anchors, eyes=eyes, mouth=mouth, lids=lids, armp=armp,
                closed=closed, blendp=blendp, eyeline=eyeline, smile_eyes=smile_eyes,
                pain_eyes=pain_eyes, wide_eyes=wide_eyes,
                star_eyes=star_eyes,
                fx_table=fx_table,
                footp=footp, skirtp=skirtp, jacketp=jacketp, handp=handp,
                skirtx=skirtx)
    attach_emit(rig, base, base_root)   # 挂件（A49 / T45）：表在就挂，不在就当没有
    nbone = emit_bone_chains(rig, base)  # S2（第六十六问）：头发/尾巴接成真正的骨链
    if nbone:
        print(f"  骨链：新增 {nbone} 个旋转节点，网格改为挂在链尾")
    prune_dangling(rig)                 # 素材没齐的形态：清掉指向不存在部件的绑定

    out = os.path.join(base, "rig.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(rig, f, ensure_ascii=False, indent=2)
    print(f"写出 {out}：部件 {len(rig['parts'])} 动作 {len(rig['actions'])} "
          f"区域 {len(rig['regions'])} 组 {len(rig['groups'])}"
          f"{'（分段身体）' if seg else '（单图层身体）'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
