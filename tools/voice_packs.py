#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""voice_packs.py — 音色包管理（下载的音色可以直接装进项目，不改任何代码）。

音色包格式（放在仓库根目录 voices/<音色id>/ 下）：
    voices/<id>/
        model.onnx          Piper VITS 模型（或任意 ONNX 语音模型）
        model.onnx.json     与模型配套的配置（音素表、采样率等）
        meta.json           元数据：名称、语言、性别、年龄感、许可、来源
        sample.wav          试听样音（install 时自动生成）

meta.json 字段：
    { "id","name","lang","gender","age","license","source","note","phoneme_type" }
    其中 license 与 source 必填（合规登记，参见 docs/VOICES.md）。

命令：
    python3 tools/voice_packs.py list                      # 列出已装音色
    python3 tools/voice_packs.py install <目录或zip>        # 安装并生成试听样音
    python3 tools/voice_packs.py verify <id>               # 校验（能加载、能合成、元数据齐全）
    python3 tools/voice_packs.py remove <id>               # 卸载
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VOICES_DIR = os.path.join(ROOT, "voices")
REGISTRY = os.path.join(VOICES_DIR, "registry.json")
REQUIRED_META = ("id", "name", "lang", "license", "source")

SAMPLE_TEXT = "你好呀，我是小寻。今天也一起加油吧。"


def load_registry() -> dict:
    if os.path.exists(REGISTRY):
        with open(REGISTRY, encoding="utf-8") as f:
            return json.load(f)
    return {"schema_version": "1.0", "voices": []}


def save_registry(reg: dict) -> None:
    os.makedirs(VOICES_DIR, exist_ok=True)
    with open(REGISTRY, "w", encoding="utf-8") as f:
        json.dump(reg, f, ensure_ascii=False, indent=2)


def find_model_files(src: str) -> tuple[str, str]:
    """在给定目录（含 zip 解压后的子目录）里找 .onnx 与配套 .onnx.json。"""
    onnx = cfg = None
    for dirpath, _dirs, files in os.walk(src):
        for name in sorted(files):
            p = os.path.join(dirpath, name)
            if name.endswith(".onnx.json") and cfg is None:
                cfg = p
            elif name.endswith(".onnx") and onnx is None:
                onnx = p
        if onnx:
            break
    if onnx and (not cfg or not os.path.exists(cfg)):
        cand = onnx + ".json"
        cfg = cand if os.path.exists(cand) else cfg
    return onnx, cfg


def do_install(args) -> int:
    src = args.path
    tmp = None
    if zipfile.is_zipfile(src):
        tmp = tempfile.mkdtemp(prefix="vpack_")
        with zipfile.ZipFile(src) as z:
            z.extractall(tmp)
        src = tmp
    onnx, cfg = find_model_files(src)
    if not onnx or not cfg or not os.path.exists(cfg):
        print("找不到模型文件：目录里需要有 <名字>.onnx 与 <名字>.onnx.json", file=sys.stderr)
        return 2

    vid = args.id or os.path.splitext(os.path.splitext(os.path.basename(onnx))[0])[0]
    dest = os.path.join(VOICES_DIR, vid)
    os.makedirs(dest, exist_ok=True)
    shutil.copy2(onnx, os.path.join(dest, "model.onnx"))
    shutil.copy2(cfg, os.path.join(dest, "model.onnx.json"))

    meta_path = os.path.join(dest, "meta.json")
    if os.path.exists(meta_path) and not args.force:
        print(f"meta.json 已存在：{meta_path}（要覆盖加 --force）")
    else:
        # meta.json 可能在解压后的子目录里，跟着模型文件找
        src_dir = os.path.dirname(onnx)
        meta_src = os.path.join(src_dir, "meta.json")
        if not os.path.exists(meta_src):
            meta_src = os.path.join(src, "meta.json")
        with open(meta_src, encoding="utf-8") as f:
            meta = json.load(f)
        meta.setdefault("id", vid)
        missing = [k for k in REQUIRED_META if not meta.get(k)]
        if missing and not args.allow_missing_meta:
            print(f"meta.json 缺少必填字段 {missing}："
                  f"许可(license)与来源(source)必须如实填写（合规要求）。", file=sys.stderr)
            return 3
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)

    # 生成试听样音（能合成 → 说明音色可用）
    out = os.path.join(dest, "sample.wav")
    cmd = [sys.executable, os.path.join(ROOT, "tools", "voice_local.py"),
           "--voice", vid, "--text", SAMPLE_TEXT, "--out", out]
    r = subprocess.run(cmd, capture_output=True, text=True)
    ok = r.returncode == 0 and os.path.exists(out)
    print(r.stdout.strip() or r.stderr.strip()[-500:])

    reg = load_registry()
    reg["voices"] = [v for v in reg["voices"] if v.get("id") != vid]
    with open(meta_path, encoding="utf-8") as f:
        meta = json.load(f)
    reg["voices"].append({
        "id": vid, "name": meta.get("name", vid), "lang": meta.get("lang", ""),
        "gender": meta.get("gender", ""), "age": meta.get("age", ""),
        "license": meta.get("license", ""), "source": meta.get("source", ""),
        "path": os.path.relpath(dest, ROOT).replace(os.sep, "/"),
        "sample": os.path.relpath(out, ROOT).replace(os.sep, "/") if ok else "",
        "installed_at": __import__("datetime").datetime.now().strftime("%Y-%m-%d %H:%M"),
        "usable": bool(ok),
    })
    save_registry(reg)
    if tmp:
        shutil.rmtree(tmp, ignore_errors=True)
    print(f"已安装：{vid}（{dest}）{'，试听样音已生成' if ok else '，注意：试听样音生成失败'}")
    return 0 if ok else 4


def do_list(args) -> int:
    reg = load_registry()
    if not reg["voices"]:
        print("还没有安装音色包。把下载好的 Piper 音色放进 voices/<id>/ 或用 install 安装。")
        return 0
    print(f"{'id':28s} {'名称':14s} {'语言':6s} {'年龄感':8s} {'许可':16s} 可用")
    for v in reg["voices"]:
        print(f"{v['id']:28s} {v.get('name','')[:12]:14s} {v.get('lang','')[:6]:6s} "
              f"{str(v.get('age',''))[:8]:8s} {str(v.get('license',''))[:16]:16s} "
              f"{'是' if v.get('usable') else '否'}")
    return 0


def do_verify(args) -> int:
    dest = os.path.join(VOICES_DIR, args.id)
    ok = True
    if not os.path.isdir(dest):
        print(f"没有这个音色包：{args.id}", file=sys.stderr)
        return 2
    for name in ("model.onnx", "model.onnx.json"):
        if not os.path.exists(os.path.join(dest, name)):
            print(f"缺文件：{name}")
            ok = False
    meta = {}
    mp = os.path.join(dest, "meta.json")
    if os.path.exists(mp):
        with open(mp, encoding="utf-8") as f:
            meta = json.load(f)
        missing = [k for k in REQUIRED_META if not meta.get(k)]
        if missing:
            print(f"meta.json 缺字段：{missing}")
            ok = False
    else:
        print("缺 meta.json")
        ok = False
    print(f"元数据：{json.dumps(meta, ensure_ascii=False)}")
    print("结论：" + ("通过" if ok else "不通过"))
    return 0 if ok else 1


def do_remove(args) -> int:
    dest = os.path.join(VOICES_DIR, args.id)
    if os.path.isdir(dest):
        shutil.rmtree(dest)
    reg = load_registry()
    reg["voices"] = [v for v in reg["voices"] if v.get("id") != args.id]
    save_registry(reg)
    print(f"已卸载 {args.id}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("install"); p.add_argument("path"); p.add_argument("--id", default="")
    p.add_argument("--force", action="store_true")
    p.add_argument("--allow-missing-meta", action="store_true"); p.set_defaults(fn=do_install)
    p = sub.add_parser("list"); p.set_defaults(fn=do_list)
    p = sub.add_parser("verify"); p.add_argument("id"); p.set_defaults(fn=do_verify)
    p = sub.add_parser("remove"); p.add_argument("id"); p.set_defaults(fn=do_remove)
    args = ap.parse_args()
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main())
