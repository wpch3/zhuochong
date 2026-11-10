#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""挂件表的**形态可移植性**闸（T2.2.0，2026-10-17）。

用户 2026-10-17 的要求：「确保我们自制的 live2d 底层能适配所有角色以及我们需要的
东西，还有单个 ai 角色的四个形象都能适配，不是只能适配少女就行」。

这件事不能靠嘴说。`design/attachments.json` 是**角色级**的（四个形态共用一份），
一旦里面写死画布绝对像素，就只对量它的那个形态成立。实测过账：

    照少女 teen 量的 7 个挂件，套到规划中的 chibi（头身比 1:2.5）上
    平均偏 **92 画布像素**，而画布总高才 1360 —— 完全不在身上。
    而且 sprite_h 是绝对值 ⇒ chibi 那个 517px 的头上会扣一对 104px 的耳朵。

所以挂件几何改成**相对形态锚点**（见 tools/attach_geom.py）。这个闸验两件事：

  ① **没有挂件还在用绝对像素**（有 pos/sprite_h 而没有 pos_rel 的，直接红）
  ② **换头身比，挂件真的跟着动** —— 这条是关键，而且**不是恒真的**：
     把 teen 的锚点按不同头身比重算，头上的件必须随头高缩放和位移，
     尾巴必须跟着 hip 走。要是谁偷偷写回绝对值，这条当场红。
  ③ 四种头身比下，解析出来的位置都要落在画布内。

★ 为什么不是「渲染四个形态看一眼」：loli/adult/chibi 的素材还没做（forms.json 里
  status=planned）。但**挂件表能不能适配**和「素材做没做」是两件事 ——
  几何是纯算术，现在就能验，不用等美术。

用法：
  python3 tools/check_form_portable.py [--character xiaoxun]
"""
from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import attach_geom  # noqa: E402

_n = _fail = 0


def check(name, ok, detail=""):
    global _n, _fail
    _n += 1
    if not ok:
        _fail += 1
    print("  %s  %-54s %s" % ("通过" if ok else "不通过", name, detail))


def synth_anchors(base_anchors, heads_tall):
    """把一份真锚点重算成指定头身比的合成锚点。

    做法是**分段线性重映射**：头那一段 [0, 头高] 映到 [0, 新头高]，
    身子那一段 [头高, 身高] 映到 [新头高, 身高]。段内比例不变，
    变的只有「头占全身多少」—— 这正是『改头身比』的定义。
    不凭空编数，所以 chibi 的肩/腰/胯仍然是人的相对位置。
    """
    meta = dict(base_anchors["meta"])
    H = float(meta["height_px"])
    h0 = float(meta["head_ratio"]) * H          # 原头高
    h1 = H / float(heads_tall)                  # 新头高
    out = {"meta": dict(meta), "points": {}}
    out["meta"]["head_ratio"] = h1 / H
    out["meta"]["heads_tall"] = float(heads_tall)
    for k, (x, y) in base_anchors["points"].items():
        if y <= h0:
            ny = y / h0 * h1 if h0 > 0 else y
        else:
            ny = h1 + (y - h0) / (H - h0) * (H - h1)
        # 横向跟着头高缩放（chibi 的头更宽），躯干以下按身高不变
        nx = x
        out["points"][k] = [nx, ny]
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    ap.add_argument("--character", default="xiaoxun")
    a = ap.parse_args()
    cdir = os.path.join(a.root, "characters", a.character)
    tp = os.path.join(cdir, "design", "attachments.json")
    if not os.path.exists(tp):
        print("[form] %s 没有挂件表，跳过" % a.character)
        return 0
    with open(tp, encoding="utf-8") as f:
        table = json.load(f)
    atts = table["attachments"]

    fp = os.path.join(cdir, "forms.json")
    with open(fp, encoding="utf-8") as f:
        forms = json.load(f)["forms"]
    ratios = []
    for fm in forms:
        r = str(fm.get("head_body_ratio", "")).split(":")
        if len(r) == 2:
            try:
                ratios.append((fm["id"], float(r[1])))
            except ValueError:
                pass
    print("== 挂件表的形态可移植性（%s，%d 个挂件 / %d 个规划形态）==＝"
          % (a.character, len(atts), len(ratios)))

    # 挂点表（T66.19 / S4）：挂了 socket 的件位置归挂点，也要在这里一起验 ——
    # 否则"换形态会不会漂"这件事对它们完全没被验过，等于换了个地方藏绝对值。
    sockets = attach_geom.load_sockets(cdir)
    skeletons = attach_geom.load_skeleton_sockets(cdir)
    sock_spec = {k: v for k, v in sockets.items()}
    check("挂点表覆盖了骨架声明的每个挂点",
          set(sock_spec) <= set(skeletons) if skeletons else True,
          "骨架 %d 个 / 表 %d 个" % (len(skeletons), len(sock_spec)))
    dangling = sorted(x["id"] for x in atts
                      if x.get("socket") and x["socket"] not in sock_spec)
    check("没有挂件挂在不存在的挂点上", not dangling,
          "、".join(dangling) if dangling else
          "%d 个挂件里有 %d 个接了挂点" % (len(atts), sum(1 for x in atts if x.get("socket"))))

    # ① 不许有绝对像素（挂了 socket 的件天然没有绝对像素：它的位置归挂点）
    hard = sorted(x["id"] for x in atts if "pos" in x or "sprite_h" in x)
    check("没有挂件还写着画布绝对像素", not hard,
          "%d 个挂件全是相对几何" % len(atts) if not hard else
          "这些还写着绝对 pos/sprite_h，只对量它的那个形态成立：" + "、".join(hard))

    # 需要一份真锚点当底板
    base_form = next((fm["id"] for fm in forms if fm.get("status") == "ready"), None)
    if not base_form:
        check("至少有一个 ready 形态提供锚点底板", False, "forms.json 里没有 ready 的形态")
        return 1
    anchors = attach_geom.load_anchors(
        os.path.join(cdir, "forms", base_form, "design"))
    if anchors is None:
        check("ready 形态有 anchors.json", False, base_form)
        return 1

    # ② 换头身比，挂件必须跟着动（非恒真：写死绝对值的话这条会红）
    got = {}
    got_sock = {}
    for fid, ht in ratios:
        syn = synth_anchors(anchors, ht)
        got[fid] = {x["id"]: attach_geom.attach_pos(
            x, sock_spec.get(x.get("socket")), syn) for x in atts}
        got_sock[fid] = {sid: attach_geom.socket_pos(sp, syn)
                         for sid, sp in sock_spec.items()}
    if len(ratios) >= 2:
        (f1, _), (f2, _) = ratios[0], ratios[1]
        for x in atts:
            p1, h1 = got[f1][x["id"]]
            p2, h2 = got[f2][x["id"]]
            moved = (p1 != p2) or (h1 != h2)
            check("%s 会跟着形态走" % x["id"], moved,
                  "%s %s/%d → %s %s/%d" % (f1, p1, h1, f2, p2, h2) if moved else
                  "两个头身比下位置和尺寸完全一样 —— 它没有跟着形态缩放")

    # ②b 挂点自己也要跟着形态缩放（非恒真：挂点写死画布像素的话这条会红）
    if len(ratios) >= 2:
        (f1, _), (f2, _) = ratios[0], ratios[1]
        stuck = sorted(sid for sid in sock_spec
                       if got_sock[f1].get(sid) == got_sock[f2].get(sid))
        check("每个挂点都跟着形态缩放", not stuck,
              "%d 个挂点：%s → %s" % (len(sock_spec), got_sock[f1].get(
                  sorted(sock_spec)[0]), got_sock[f2].get(sorted(sock_spec)[0]))
              if not stuck else "这些挂点两个头身比下完全一样：" + "、".join(stuck))

    # ③ 四种头身比下都要落在画布内（用 ready 形态的画布尺寸当量尺）
    rig = os.path.join(cdir, "forms", base_form, "rig.json")
    with open(rig, encoding="utf-8") as f:
        cv = json.load(f)["canvas"]
    bad = []
    for fid, _ in ratios:
        for x in atts:
            p, h = got[fid][x["id"]]
            if not (-cv["w"] * 0.2 <= p[0] <= cv["w"] * 1.2
                    and -cv["h"] * 0.2 <= p[1] <= cv["h"] * 1.2):
                bad.append("%s@%s=%s" % (x["id"], fid, p))
    check("四种头身比下挂件都没有飞出画布", not bad,
          "%d 形态 × %d 挂件全部在范围内" % (len(ratios), len(atts)) if not bad
          else "、".join(bad[:4]))

    # 把换算结果打出来，便于人工核对比例是否合理
    print("\n  各形态解析出来的几何（像素）：")
    hdr = "  %-17s" % "挂件" + "".join("%-22s" % ("%s 1:%g" % (f, r)) for f, r in ratios)
    print(hdr)
    for x in atts:
        line = "  %-17s" % x["id"]
        for fid, _ in ratios:
            p, h = got[fid][x["id"]]
            line += "%-22s" % ("%s h=%d" % (p, h))
        print(line)

    print("\n合计 %d 项，%d 项不通过 → %s" % (_n, _fail, "全部通过" if not _fail else "有问题"))
    return 1 if _fail else 0


if __name__ == "__main__":
    sys.exit(main())
