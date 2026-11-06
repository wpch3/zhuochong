#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""voice_manifest.py — 生成 web/voice_manifest.json（界面用的语音清单）。

数据来源：characters/<角色>/voice/catalog.json（由 voice_render.py 生成），
只保留文件真实存在的条目，避免界面出现点不开的语音。
"""
from __future__ import annotations

import argparse
import json
import os
import re


def load_json(path: str) -> dict:
    with open(path, encoding="utf-8") as f:
        raw = f.read()
    out, in_str, esc = [], False, False
    i = 0
    while i < len(raw):
        ch = raw[i]
        if in_str:
            out.append(ch)
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            i += 1
            continue
        if ch == '"':
            in_str = True; out.append(ch); i += 1; continue
        if ch == "/" and i + 1 < len(raw) and raw[i + 1] == "/":
            while i < len(raw) and raw[i] != "\n":
                i += 1
            continue
        out.append(ch); i += 1
    return json.loads("".join(out))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--character", default="xiaoxun")
    ap.add_argument("--root", default=".")
    ap.add_argument("--out", default="web/voice_manifest.json")
    args = ap.parse_args()

    root = args.root
    cat_path = os.path.join(root, "characters", args.character, "voice", "catalog.json")
    manifest: dict = {"schema_version": "1.0", "character": args.character, "engine": "", "note": "", "lines": []}
    if os.path.exists(cat_path):
        cat = load_json(cat_path)
        manifest["engine"] = cat.get("provider", "")
        manifest["note"] = cat.get("engine_note", "")
        for item in cat.get("lines", []):
            f = item.get("file", "")
            if f and os.path.exists(os.path.join(root, f)) and os.path.getsize(os.path.join(root, f)) > 1024:
                manifest["lines"].append({"id": item["id"], "variant": item.get("variant", ""),
                                          "text": item.get("text", ""), "file": f})
    if not manifest["lines"]:
        manifest["note"] = "还没有渲染好的语音；先运行 tools/voice_render.py（或本地合成）后再生成清单。"

    out_path = os.path.join(root, args.out)
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=1)
    print(f"已写入 {out_path}：{len(manifest['lines'])} 条语音")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
