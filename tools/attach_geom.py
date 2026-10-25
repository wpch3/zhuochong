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
                    "torso" = 头顶到腰（长发那类"垂到腰"的件用）
    "pos_unit":     **位置**单独用另一种单位（可选，默认跟 unit 走）。
                    T46.3 双马尾逼出来的：扎头的位置是**头**上的量
                    （"耳朵上方、头侧边"），而辫子的长度是**上半身**的量
                    （"垂到腰"）。chibi 的头占身高 0.47、teen 只占 0.22，
                    两者同用一个单位必然有一头错：用 head 量长度 ⇒ chibi 的
                    辫子长到脚踝；用 torso 量位置 ⇒ chibi 的发根跑到脸中间。

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
    if unit == "torso":
        # 头顶到腰的距离（T46.2 加的第三种单位）。
        # 为什么头发不能用 head 也不能用 body：
        #   · body —— 四个形态共用同一块画布，身高都是 1292，等于**没缩放**
        #     （长发在 teen 上到大腿，在 chibi 上也到大腿，但 chibi 的腿只有那么点长）；
        #   · head —— 长发有近 3 个头高，chibi 的头高是 teen 的 2.2 倍，
        #     照头高缩放会得到 1786px 的头发，比整块画布还长。
        # 「头发垂到腰」这句话里的尺度本来就是**上半身长**，所以直接用它。
        pts = anchors["points"]
        return float(pts["waist"][1]) - float(pts["head_top"][1])
    raise SystemExit("[attach_geom] unit 只能是 head / body / torso，写了 %r" % unit)


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
    # 位置可以用和尺寸不同的单位（见上面 pos_unit 的说明），默认两者相同。
    pu = unit_px(anchors, att["pos_unit"]) if att.get("pos_unit") else u
    rx, ry = pts[ref][0], pts[ref][1]
    dx, dy = att["pos_rel"]
    pos = [int(round(rx + float(dx) * pu + ox)),
           int(round(ry + float(dy) * pu + oy))]
    sh = int(round(float(att["sprite_h_rel"]) * u))
    return pos, sh


def load_skeleton_sockets(char_root, character=None):
    """读骨架里声明的挂点：{id: 父骨 id}（kind:socket 的那些骨）。

    char_root 可以是角色目录，也可以是带 skeleton.json 的目录。没有骨架就返回 {}。
    """
    p = os.path.join(char_root, "skeleton.json")
    if not os.path.exists(p) and character:
        p = os.path.join(os.path.dirname(char_root), character, "skeleton.json")
    if not os.path.exists(p):
        return {}
    with open(p, encoding="utf-8") as f:
        skel = json.load(f)
    return {b["id"]: b.get("parent") for b in skel.get("bones", [])
            if b.get("kind") == "socket"}


def load_sockets(char_root):
    """读角色级 design/sockets.json：{id: 一条挂点定义}。没有这张表就返回 {}。"""
    p = os.path.join(char_root, "design", "sockets.json")
    if not os.path.exists(p):
        return {}
    with open(p, encoding="utf-8") as f:
        table = json.load(f)
    return {x["id"]: x for x in table.get("sockets", [])
            if not x["id"].startswith("_")}


def socket_pos(spec, anchors, ox=0, oy=0):
    """挂点坐标（画布像素，锚点以外的部分）。

    挂点表用「形态锚点 + 相对偏移」表达，和挂件同一套算式 —— 这不是巧合：
    两套几何要是各写一份，早晚会有一处先改、另一处没改，而症状是“配件差几像素”，
    没人会想到去查换算。所以这里复用 resolve()，只是明说挂点自己没有尺寸。
    """
    if "ref" not in spec:
        raise SystemExit(
            "[attach_geom] socket_pos 要的是 design/sockets.json 的条目（ref + pos_rel + unit），"
            "传进来的是已经换算过的 rig sockets 条目（只有 pos）—— 两处都加一次画布偏移会偏两倍")
    return resolve({**spec, "sprite_h_rel": 0.0}, anchors, ox, oy)[0]


def attach_pos(att, socket_spec, anchors, ox=0, oy=0):
    """挂件落点 + 成品高：挂了挂点就 = 挂点 + dpos_rel，否则走老口径。

    dpos_rel 的单位由 socket_unit 给（默认 head），和挂点自己的单位可以不同：
    同一个挂点上放“紧贴的帽檐”和“抬高一点的呆毛夹”，差值表达成头高比例才跨形态成立。
    """
    if socket_spec is None:
        return resolve(att, anchors, ox, oy)
    base = socket_pos(socket_spec, anchors, ox, oy)
    du = unit_px(anchors, att.get("socket_unit") or socket_spec.get("unit", "head"))
    dp = att.get("dpos_rel") or [0.0, 0.0]
    pos = [int(round(base[0] + float(dp[0]) * du)),
           int(round(base[1] + float(dp[1]) * du))]
    # 尺寸与位置是两件事：位置归挂点，尺寸仍由挂件自己的 sprite_h_rel 给。
    # 这里**不能**再走 resolve()：挂了挂点的件往往已经不写 ref 了（位置不需要它），
    # 而 resolve() 会先去校验 ref —— 那是给"自己摆位置"的件用的入口。
    if "sprite_h_rel" in att:
        sh = int(round(float(att["sprite_h_rel"]) *
                       unit_px(anchors, att.get("unit", "head"))))
    else:
        sh = int(att.get("sprite_h", 0))
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
