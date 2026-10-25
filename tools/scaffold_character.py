#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""新角色脚手架：只写**契约**，不造素材（T66.23 / S5 第一步）。

为什么需要这个工具
------------------
"七个人格各有形象"是硬需求，而现在的状态是：小寻有全套（骨架 + 四形态 rig + 挂点表），
另外七个角色只有 `character.json` + `dialogue.json`。想给她们做形象，得照着 xiaoxun
的目录结构手工抄一遍骨架契约 —— 抄漏一根骨的表现是"动作里那段不动"，肉眼几乎看不出来。

所以要有一条**可重复**的路：跑一次工具，得到
  · `characters/<id>/skeleton.json`      —— 引用 `humanoid_v1` 模板的骨契约（39 根骨，
                                             与四个形态、服装、挂点的名字全对齐）
  · `characters/<id>/design/sockets.json` —— 八个挂点（按形态锚点表达，所以四形态共用）
  · 一份**缺口清单**（写进 skeleton.json 的 `todo`）：要哪些图、哪几个形态、哪些表

★ 它**不生成任何美术**。没有素材就是没有素材，宁可让清单写得明明白白，也不拿占位图
  假装"角色做好了"（用户红线）。所以生成出来的骨架带 `"status": "contract_only"`：
  闸会验契约、会要求 todo 非空、会在你做出 rig 之后要求把 status 改成 `full`。

用法
----
    python3 tools/scaffold_character.py --character shenyu            # 写契约
    python3 tools/scaffold_character.py --character shenyu --dry-run  # 只打印，不落盘
    python3 tools/scaffold_character.py --list                        # 谁有契约、谁还是草案
"""
import argparse
import json
import os
import sys

TEMPLATE_CHAR = "xiaoxun"          # humanoid_v1 的参考实现（骨名/父子/挂点都从它来）


def load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
        f.write("\n")


def build_skeleton(tpl, char_id, name):
    """从模板骨架派生出这个角色的骨架契约。

    只搬**骨名/父子/kind/required/chains**这几样 —— 它们是"语义"，跨角色通用；
    不搬任何坐标（pivot 在各形态的 rig.json 里，是量出来的，不是设计的）。
    """
    bones = []
    for b in tpl["bones"]:
        nb = {"id": b["id"], "parent": b["parent"], "kind": b["kind"],
              "required": b["required"]}
        if b.get("note"):
            nb["note"] = b["note"]
        bones.append(nb)
    sk = {
        "schema_version": tpl.get("schema_version", "1.0"),
        "character": char_id,
        "skeleton": tpl.get("skeleton", "humanoid_v1"),
        "status": "contract_only",
        "canvas": tpl.get("canvas", [848, 1360]),
        "_note": (
            "本文件由 tools/scaffold_character.py 从 %s 的 humanoid_v1 契约派生，"
            "**不是**美术资产清单。骨名/父子/挂点与模板一字不差，所以四个形态、"
            "换装、挂点、动作都能直接复用。status=contract_only 表示：契约齐了，"
            "素材还没有；做出第一个形态的 rig 之后把它改成 full（闸会检查这一步）。"
            % TEMPLATE_CHAR),
        "bones": bones,
        "waivers": tpl.get("waivers", []),
        "forms": tpl.get("forms", {}),
        "chains": tpl.get("chains", []),
        "todo": [
            "四个形态的素材：forms/{teen,loli,midlong,chibi}/sprites/（拆件 PNG，带 alpha）",
            "每个形态的 design sheet + anchors.json（锚点由 tools/make_anchors.py 量出来）",
            "每个形态跑一次 tools/make_rig.py 得到 rig.json，再把 status 改成 full",
            "design/wardrobe.json + outfits/*.json（服装包；先做常服一套）",
            "design/attachments.json（挂件表：猫耳/尾巴/发饰，走挂点）",
            "voice/ + dialogue.json 接线（口型包由 tools/make_lipsync.py 生成）",
        ],
        "_name": name,
    }
    return sk


FORMS = [("teen", "少女"), ("loli", "萝莉"), ("adult", "青年女性"), ("chibi", "Q 版")]


def build_forms(char_id, name):
    """形态路线图：四条都写 planned。

    ★ 故意**不写** head_body_ratio：那是要拿 anchors.json 量出来的实测值，
      没量就填等于编数据（xiaoxun 就被"设计稿 1:6 / 实测 1:4.65"坑过一次）。
      引擎侧读的是 status：planned 的显示成灰色卡片，点了给提示，不会白屏。
    """
    return {
        "schema_version": "1.0",
        "_note": (
            "形态路线图（由 tools/scaffold_character.py 生成）。四条都是 planned —— "
            "这个角色的形态一个都还没做。做好一个 = 素材进 forms/<id>/ + 生成 rig.json，"
            "再把这里的 status 改成 ready；闸会自动开始管它。**不要为 planned 造假素材**。"
            "head_body_ratio 要等 anchors.json 量出来再填，不预先编。"),
        "character": char_id,
        "forms": [{"id": fid, "name": fname, "status": "planned",
                   "note": "%s的%s形态，素材未开始（见 skeleton.json 的 todo）" % (name, fname)}
                  for fid, fname in FORMS],
    }


def build_sockets(tpl_sockets, char_id):
    """挂点表：位置用**形态锚点**表达（ref + pos_rel + unit），所以四个形态共用一份。

    新角色如果头身比例和模板差很多，pos_rel 要重标（这是唯一需要按角色调的地方，
    而且它只影响"配饰挂在哪"，不影响骨和动作）。
    """
    out = {
        "schema_version": tpl_sockets.get("schema_version", "1.0"),
        "_note": (
            "命名挂点表，由 tools/scaffold_character.py 从 %s 派生。位置按形态锚点表达，"
            "四形态共用；如果新角色的头身比例差得多，改这里的 pos_rel 就行，"
            "不用碰骨架（骨是语义，位置是数据）。" % TEMPLATE_CHAR),
        "_fields": tpl_sockets.get("_fields", {}),
        "sockets": [],
    }
    for s in tpl_sockets.get("sockets", []):
        out["sockets"].append({
            "id": s["id"],
            "ref": s["ref"],
            "pos_rel": s["pos_rel"],
            "unit": s["unit"],
            # 老实写清这些数字是从哪个角色抄来的：换成新角色后必须按本角色
            # 各形态的 anchors.json 重标（挂件会跟着偏，但骨与动作不受影响）。
            "inherited_from": TEMPLATE_CHAR,
            "note": s.get("note", ""),
        })
    _ = char_id
    return out


def survey(root):
    """谁有骨架契约、谁还是草案。**不许有人是隐形的**（这是用户反复强调的一条）。"""
    cdir = os.path.join(root, "characters")
    rows = []
    for name in sorted(os.listdir(cdir)):
        d = os.path.join(cdir, name)
        if not os.path.isdir(d):
            continue
        skp = os.path.join(d, "skeleton.json")
        cp = os.path.join(d, "character.json")
        row = {"id": name, "skeleton": os.path.isfile(skp), "status": "-", "forms": []}
        if row["skeleton"]:
            try:
                sk = load(skp)
                row["status"] = sk.get("status", "full")
            except Exception:                       # noqa: BLE001
                row["status"] = "（骨架解析失败）"
        fdir = os.path.join(d, "forms")
        if os.path.isdir(fdir):
            row["forms"] = sorted(f for f in os.listdir(fdir)
                                  if os.path.isfile(os.path.join(fdir, f, "rig.json")))
        if row["status"] == "-" and os.path.isfile(cp):
            try:
                row["status"] = "draft（只有人设，%s）" % (load(cp).get("status") or "status 未写")
            except Exception:                       # noqa: BLE001
                row["status"] = "draft"
        rows.append(row)
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    ap.add_argument("--character")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--force", action="store_true", help="覆盖已有的 skeleton.json")
    a = ap.parse_args()
    root = os.path.abspath(a.root)

    if a.list or not a.character:
        rows = survey(root)
        print("角色目录一览（谁的契约齐了、谁还是草案）")
        for r in rows:
            print("  %-10s %-22s forms=%s"
                  % (r["id"], r["status"], ",".join(r["forms"]) or "无"))
        n_full = sum(1 for r in rows if r["status"] == "full")
        n_contract = sum(1 for r in rows if r["status"] == "contract_only")
        n_draft = len(rows) - n_full - n_contract
        print("\n合计 %d 个角色：契约+素材 %d、只有契约 %d、还是草案 %d"
              % (len(rows), n_full, n_contract, n_draft))
        if n_draft:
            print("（草案 = 只有人设，没有骨架契约；这些角色的形象还没有开工，**不是**做完了）")
        return 0

    cid = a.character
    if not os.path.isdir(os.path.join(root, "characters", cid)):
        print("[scaffold] 没有这个角色目录：characters/%s" % cid)
        return 2
    tbase = os.path.join(root, "characters", TEMPLATE_CHAR)
    tpl = load(os.path.join(tbase, "skeleton.json"))
    tpl_sockets = load(os.path.join(tbase, "design", "sockets.json"))
    name = cid
    cp = os.path.join(root, "characters", cid, "character.json")
    if os.path.isfile(cp):
        name = load(cp).get("name") or cid

    sk = build_skeleton(tpl, cid, name)
    sockets = build_sockets(tpl_sockets, cid)

    skp = os.path.join(root, "characters", cid, "skeleton.json")
    socp = os.path.join(root, "characters", cid, "design", "sockets.json")
    fmp = os.path.join(root, "characters", cid, "forms.json")
    if os.path.exists(skp) and not a.force:
        print("[scaffold] 已经有 skeleton.json（要覆盖请加 --force）：%s" % skp)
        return 2

    if a.dry_run:
        print(json.dumps({"skeleton": sk, "sockets": sockets},
                         ensure_ascii=False, indent=1)[:2000])
        return 0
    save(skp, sk)
    save(socp, sockets)
    if not os.path.exists(fmp) or a.force:
        save(fmp, build_forms(cid, name))
    print("[scaffold] 写出 %s（%d 根骨，其中挂点 %d）"
          % (os.path.relpath(skp, root), len(sk["bones"]),
             sum(1 for b in sk["bones"] if b["kind"] == "socket")))
    print("[scaffold] 写出 %s（%d 个挂点）"
          % (os.path.relpath(socp, root), len(sockets["sockets"])))
    print("[scaffold] 写出 %s（四形态全部 planned）" % os.path.relpath(fmp, root))
    print("[scaffold] 还缺（写在 skeleton.json 的 todo 里，闸会盯着它）")
    for t in sk["todo"]:
        print("  · " + t)
    print("[scaffold] ★ 没有生成任何美术。素材要真画，占位图不算。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
