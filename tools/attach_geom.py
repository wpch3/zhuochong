# -*- coding: utf-8 -*-
"""挂件几何的**形态无关**解析（T2.2.0 / 2026-10-17）。

为什么要有这个模块
------------------
`design/attachments.json` 是**角色级**的（四个形态共用一份），但它原来写的是
**画布绝对像素**：猫耳 pos [364,178]、尾巴 [318,640]、兜帽 [435,80]，
`sprite_h` 也是绝对值。这些数全是照「少女 teen」量出来的。

把同一张表套到规划中的 chibi（头身比 1:2.5）上算过账：

    挂件              写死的绝对值      按头高缩放应该在      偏差
    tail_cat_relaxed  [318, 640]        [237, 624]            83 px
    tail_cat_up       [288, 716]        [181, 765]           118 px
    ear_cat_l         [364, 178]        [327, 272]           101 px
    ear_cat_r         [474, 178]        [532, 272]           110 px
    平均 92 px —— 而画布总高才 1360。

这不是「需要微调」，是「完全不在身上」。而且 `sprite_h` 绝对值意味着
chibi 那个 517px 高的头上会扣一对 104px 的耳朵，小一半。

做法
----
几何改成**相对形态锚点**表达，三个字段：

    "ref":          形态级 design/anchors.json 的 points 里的一个点名
                    （head_top / eye_line / neck / shoulder / waist / hip / knee / ankle / foot）
    "pos_rel":      [dx, dy]，相对那个点的偏移，单位见 unit
    "sprite_h_rel": 成品高度，单位见 unit
    "unit":         "head" = 这个形态自己的头高（默认，头上的件用）
                    "body" = 这个形态自己的身高（挂在躯干上的长件用）

于是「猫耳在头顶下 0.396 个头高处、高 0.374 个头高」这句话对**任何**头身比
都成立 —— 换形态只要换 anchors.json，挂件表一个字都不用改。
这也正是教程口径：猫耳长度 = 脸高的 1/3（第三十三批），本来就是个比例。

★ 坐标系对账（踩过一次就不想再踩）
  anchors.json 的 points 用的是 **body_full.png 自身的像素坐标**；
  rig 里的画布坐标 = 这个坐标 + 居中偏移 (ox, oy)，
  其中 ox = (画布宽 − 切图宽) // 2，oy = 画布高 − 切图高。
  attachments.json 里原来的 pos 写的是**画布坐标**，所以换算时要先减掉 (ox, oy)。
"""

import json
import os

#: anchors.json 的 points 里允许被 ref 引用的点
VALID_REFS = ("head_top", "eye_line", "mouth_line", "neck", "shoulder",
              "shoulder_l", "shoulder_r", "elbow_l", "elbow_r",
              "wrist_l", "wrist_r", "waist", "hip", "knee", "ankle", "foot")


def load_anchors(form_base):
    """读形态级 design/anchors.json。没有就返回 None（挂件表退回绝对像素模式）。"""
    p = os.path.join(form_base, "anchors.json")
    if not os.path.exists(p):
        p = os.path.join(form_base, "design", "anchors.json")
    if not os.path.exists(p):
        return None
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def unit_px(anchors, unit):
    """把 unit 名字换算成这个形态的像素长度。"""
    meta = anchors["meta"]
    if unit == "body":
        return float(meta["height_px"])
    if unit == "head":
        return float(meta["head_ratio"]) * float(meta["height_px"])
    raise SystemExit("[attach_geom] unit 只能是 head 或 body，写了 %r" % unit)


def resolve(att, anchors, ox=0, oy=0):
    """解析一个挂件的几何，返回 (pos_画布, sprite_h)。

    有 pos_rel 就按形态锚点算；没有就退回表里的绝对 pos / sprite_h
    （向后兼容，但 selfcheck 的 check_form_portable 会把它标红）。
    """
    if "pos_rel" not in att and "sprite_h_rel" not in att:
        return list(att["pos"]), int(att["sprite_h"])
    if anchors is None:
        raise SystemExit(
            "[attach_geom] 挂件 %r 用了相对几何，但这个形态没有 "
            "design/anchors.json —— 相对几何就是靠它定标的" % att.get("id"))
    ref = att.get("ref")
    if ref not in VALID_REFS:
        raise SystemExit(
            "[attach_geom] 挂件 %r 的 ref=%r 不在允许的锚点里：%s"
            % (att.get("id"), ref, "、".join(VALID_REFS)))
    pts = anchors.get("points") or {}
    if ref not in pts:
        raise SystemExit(
            "[attach_geom] 挂件 %r 的 ref=%r 在这个形态的 anchors.json 里没有"
            % (att.get("id"), ref))
    u = unit_px(anchors, att.get("unit", "head"))
    rx, ry = pts[ref][0], pts[ref][1]
    dx, dy = att["pos_rel"]
    pos = [int(round(rx + float(dx) * u + ox)),
           int(round(ry + float(dy) * u + oy))]
    sh = int(round(float(att["sprite_h_rel"]) * u))
    return pos, sh


def canvas_offset(canvas_wh, sprite_wh):
    """画布居中偏移。和 make_rig.build() 里那一行必须完全一致。"""
    cw, ch = canvas_wh
    sw, sh = sprite_wh
    return (cw - sw) // 2, ch - sh


def load_overrides(form_base):
    """形态级覆盖：design/attachments.override.json。

    相对几何能把挂件带到「大致正确」的位置，但换形态不只是等比缩放 ——
    chibi 的手短、adult 的肩宽，个别挂件总会需要单独挪一点。
    没有逃生口的话，人就会回去改角色级那张共用表，于是又把别的形态改坏了。

    格式（按挂件 id 覆盖字段，只写要改的那几个）：
        { "schema_version": "1.0",
          "tail_cat_relaxed": { "pos_rel": [-0.06, -0.14], "unit": "body" },
          "ear_cat_l":        { "sprite_h_rel": 0.42 } }
    """
    p = os.path.join(form_base, "attachments.override.json")
    if not os.path.exists(p):
        p = os.path.join(form_base, "design", "attachments.override.json")
    if not os.path.exists(p):
        return {}
    with open(p, encoding="utf-8") as f:
        d = json.load(f)
    return {k: v for k, v in d.items() if not k.startswith("_")
            and k != "schema_version" and isinstance(v, dict)}


def apply_overrides(att, overrides):
    """把形态级覆盖合并进挂件条目（不改原 dict）。"""
    ov = overrides.get(att.get("id"))
    if not ov:
        return att
    merged = dict(att)
    merged.update(ov)
    return merged
