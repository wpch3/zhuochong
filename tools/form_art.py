#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""form_art.py —— 形态级美术入口表（一张表决定「这个形态用哪张设计图、哪几张重绘」）

为什么要有它
------------
到 2026-10-24，`tools/rebuild_parts.sh` 的第 1 步写死
`characters/xiaoxun/design/design_sheet_short.png`，第 9/10/16 步写死
`characters/xiaoxun/design/redraw/head_nobangs.png` 这类**少女专用**路径。
结果是：Q 版能跑的那半条链路只能靠手工一条条敲命令，
而且 `make_eye_closed_parts.py` / `make_mouth_open_parts.py` /
`make_arm_parts.py` 三处干脆把重绘路径写死在代码里（`design/redraw/xxx.png`），
换一个形态必然读到**少女的脸**。

这正是 T2.2.5 那条「新形态压力测试」的延伸：工具链要么形态无关，
要么就会在 loli / adult 上再栽一次。本模块把「美术来源」抽成一张表：

    characters/<角色>/forms/<形态>/design/form_art.json
    {
      "schema_version": "1.0",
      "sheet": "design/design_sheet_chibi.png",       // 相对角色目录
      "redraw": {                                      // 可选，形态级覆盖
        "torso_noarms":    "forms/chibi/design/redraw/torso_noarms.png",
        "face_eyesclosed": "forms/chibi/design/redraw/face_eyesclosed.png"
      }
    }

查找顺序（`redraw_for`）：形态级 `design/redraw/<name>.png` → 表里显式写的
→ 角色级 `design/redraw/<name>.png`（少女那套，向后兼容）。

**没有这张表也照常工作**：`sheet_for` 退回旧的写死路径，`redraw_for`
退回角色级目录 —— 所以 teen 的行为一个像素都不会变（已实测：重跑
`rebuild_parts.sh xiaoxun teen`，产物逐字段相同）。

命令行用法（`rebuild_parts.sh` 就是这么调的）：

    python3 tools/form_art.py --root . --character xiaoxun --form chibi --sheet
    python3 tools/form_art.py --root . --character xiaoxun --form chibi --redraw head_nobangs
"""
from __future__ import annotations

import argparse
import json
import os

# 旧口径：少女那张图。没有 form_art.json 的形态都用它 —— 保证向后兼容。
LEGACY_SHEET = "design/design_sheet_short.png"


def _table(root: str, character: str, form: str) -> dict:
    p = os.path.join(root, "characters", character, "forms", form, "design", "form_art.json")
    if not os.path.exists(p):
        return {}
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError) as e:                       # 坏配置要说人话，不能静默
        raise SystemExit(f"[form_art] 读不了 {p}：{e}")


def sheet_for(root: str, character: str, form: str) -> str:
    """这个形态的**设计图**（相对于仓库根）。"""
    t = _table(root, character, form)
    rel = t.get("sheet") or LEGACY_SHEET
    if not os.path.isabs(rel):
        rel = os.path.join("characters", character, rel)
    full = os.path.join(root, rel)
    if not os.path.exists(full):
        raise SystemExit(f"[form_art] {character}/{form} 的设计图不存在：{full}")
    return rel


def redraw_for(root: str, character: str, form: str, name: str,
               must: bool = True) -> str | None:
    """这个形态的**重绘底图**（AI 重绘的脸/无臂躯干…）。

    顺序：形态级 design/redraw/<name>.png → form_art.json 里显式写的 → 角色级。
    `must=False` 时找不到返回 None（工具自己决定要不要报错）。
    """
    char_dir = os.path.join(root, "characters", character)
    form_rel = os.path.join("characters", character, "forms", form,
                            "design", "redraw", f"{name}.png")
    if os.path.exists(os.path.join(root, form_rel)):
        return form_rel

    t = _table(root, character, form)
    explicit = (t.get("redraw") or {}).get(name)
    if explicit:
        rel = explicit if os.path.isabs(explicit) else os.path.join("characters", character, explicit)
        if os.path.exists(os.path.join(root, rel)):
            return rel
        raise SystemExit(f"[form_art] {character}/{form} 的 form_art.json 指向了"
                         f"不存在的重绘底图：{explicit}")

    base_rel = os.path.join("characters", character, "design", "redraw", f"{name}.png")
    if os.path.exists(os.path.join(root, base_rel)):
        return base_rel
    if must:
        raise SystemExit(f"[form_art] 缺重绘底图 {name}：{character}/{form} 和角色级都没有。"
                         f"（D19：被遮挡的像素必须重绘，不能凭空补）")
    return None


def aligned_info(path: str) -> dict | None:
    """这张重绘底图**是否已经被 align_redraw.py 预配准过**（同目录有 .align.json）。

    有 sidecar 就意味着这张图的画布 = `sprites/body_full.png` 的画布、
    人物已经在正确的像素位置上，调用方**必须跳过自己的配准**：
    再套一次缩放/平移只会把已经对齐的脸推走（实测 Q 版闭眼脸就是这么
    掉到 NCC=0.109 的：重绘画布 1024×1024、人物只占中间一小块，
    而工具假设"红图里的脸框 ≈ 身体里的脸框"，这个假设对整张重绘成立、
    对**预配准过的图**反而不成立，因为它已经被缩放过了）。
    """
    for cand in (path + ".align.json", os.path.splitext(path)[0] + ".align.json"):
        if os.path.exists(cand):
            try:
                with open(cand, encoding="utf-8") as f:
                    return json.load(f)
            except (OSError, ValueError):
                return {"broken": cand}
    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    ap.add_argument("--character", required=True)
    ap.add_argument("--form", required=True)
    ap.add_argument("--sheet", action="store_true")
    ap.add_argument("--redraw", default="", help="重绘底图的逻辑名，如 head_nobangs")
    a = ap.parse_args()
    if a.sheet:
        print(sheet_for(a.root, a.character, a.form))
        return 0
    if a.redraw:
        p = redraw_for(a.root, a.character, a.form, a.redraw, must=False)
        if not p:
            return 1
        print(p)
        return 0
    ap.error("要么 --sheet，要么 --redraw <名字>")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
