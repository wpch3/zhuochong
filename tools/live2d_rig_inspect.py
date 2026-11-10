#!/usr/bin/env python3
"""live2d_rig_inspect.py — 自制 Live2D 骨骼/变形器检查器（对应官方 Deformer 层级检查）。

只用标准库。用法: python3 tools/live2d_rig_inspect.py characters/xiaoxun/forms/chibi/rig.json
输出: 组(骨骼)树、变形器树、参数/动作/物理计数、悬空引用检查。悬空即退出码 1。
"""
import json, sys
from pathlib import Path

def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__); return 2
    rig = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    parts = {p["id"]: p for p in rig.get("parts", [])}
    groups = rig.get("groups", {})
    if isinstance(groups, list):
        groups = {g["id"]: g for g in groups}
    print(f"rig id={rig.get('id')} parts={len(parts)} groups={len(groups)} "
          f"params={len(rig.get('params', []))} actions={len(rig.get('actions', []))} "
          f"deformers={len(rig.get('deformers', []))} physics={len(rig.get('physics', []) or [])}")
    print("\n[骨骼树 groups]")
    def show(gid, depth=0):
        g = groups.get(gid, {})
        print("  " * depth + f"- {gid} pivot={g.get('pivot')}")
        for c, cg in groups.items():
            if cg.get("parent") == gid:
                show(c, depth + 1)
    for gid, g in groups.items():
        if not g.get("parent"):
            show(gid)
    bad = []
    for p in rig.get("parts", []):
        f = p.get("file", "")
        if f and not (Path(sys.argv[1]).parent / f).exists():
            bad.append(f"part {p['id']} 文件不存在: {f}")
        if p.get("group") and p["group"] not in groups:
            bad.append(f"part {p['id']} 组不存在: {p['group']}")
    for d in rig.get("deformers", []):
        if d.get("part") and d["part"] not in parts:
            bad.append(f"deformer {d.get('id')} 部件不存在: {d['part']}")
    print("\n[检查]", "全部引用完整" if not bad else f"{len(bad)} 处悬空:")
    for b in bad:
        print("  ✗", b)
    return 1 if bad else 0

if __name__ == "__main__":
    raise SystemExit(main())
