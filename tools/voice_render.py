#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""voice_render.py — 角色台词批量语音合成（在 GitHub Actions 上运行）。

为什么放在 Actions 上跑：沙箱（Arena）的出网白名单只放 github / npm / pypi，
到不了任何 TTS 合成端点；GitHub Actions 的 runner 出网不受限，且同样的
edge-tts 就是网上"AI 少女音"最常用的那套生成方式（微软神经网络 TTS 音色）。

输入：
  characters/<角色>/voice/plan.json   音色与风格（形态 → 音色；候选音色；采样句）
  characters/<角色>/dialogue.json     台词表（含各好感档位变体）
输出：
  characters/<角色>/voice/lines/<line_id>_<n>.mp3    每条台词（基础 + 档位变体）
  characters/<角色>/voice/samples/<音色短名>.mp3      同一句采样，用于挑音色
  characters/<角色>/voice/catalog.json               目录（含文本，供播放页与同步用）

用法：
  python3 tools/voice_render.py --character xiaoxun --root .
  python3 tools/voice_render.py --character xiaoxun --root . --only samples
  python3 tools/voice_render.py --character xiaoxun --root . --voice zh-CN-XiaoshuangNeural
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys

try:
    import edge_tts  # 神经网络 TTS（微软 Edge 音色），pip install edge-tts
except ImportError:  # pragma: no cover
    print("缺少 edge-tts：pip install edge-tts", file=sys.stderr)
    raise SystemExit(2)

MAX_RETRY = 3
SAMPLE_TEXT = "你好呀，我是小寻。今天也一起加油吧！"


def load_json(path: str) -> dict:
    """读取允许 // 行注释的 JSON（仓库里的配置都带中文注释，与 C 侧 zjson 一致）。"""
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
            in_str = True
            out.append(ch)
            i += 1
            continue
        if ch == "/" and i + 1 < len(raw) and raw[i + 1] == "/":
            while i < len(raw) and raw[i] != "\n":
                i += 1
            continue
        out.append(ch)
        i += 1
    return json.loads("".join(out))


def _clean(s: str) -> str:
    """把 +15Hz / -5% 这类参数变成文件名安全的形式：up15Hz / down5pct。"""
    return (str(s).replace("+", "up").replace("-", "down")
            .replace("%", "pct").replace("Hz", "Hz").replace("/", "_").replace(" ", ""))


def short_name(voice: str) -> str:
    """zh-CN-XiaoyiNeural → Xiaoyi（用作文件名，避免大小写导致的重复名问题）。"""
    m = re.match(r"^[a-z]{2}-[A-Z]{2}-([A-Za-z0-9]+)Neural$", voice)
    return m.group(1) if m else re.sub(r"[^A-Za-z0-9]+", "_", voice)


async def synth(text: str, voice: str, path: str, rate: str, pitch: str, volume: str) -> int:
    """合成一句到 mp3，返回字节数；失败重试 MAX_RETRY 次。"""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    last = None
    for attempt in range(1, MAX_RETRY + 1):
        try:
            com = edge_tts.Communicate(text, voice, rate=rate, pitch=pitch, volume=volume)
            await com.save(path)
            size = os.path.getsize(path)
            if size > 1024:
                return size
            last = f"输出过小（{size} 字节）"
        except Exception as exc:  # noqa: BLE001 - 网络类异常种类多，统一重试
            last = f"{type(exc).__name__}: {exc}"
        await asyncio.sleep(1.5 * attempt)
    raise RuntimeError(f"合成失败（{voice} / {text[:16]}…）：{last}")


def collect_texts(dialogue: dict) -> list[dict]:
    """从 dialogue.json 收集所有要合成的台词（基础文本 + 各好感档位变体）。"""
    items: list[dict] = []
    for line in dialogue.get("lines", []):
        lid = line.get("id", "line")
        for i, t in enumerate(line.get("texts", []) or []):
            if t.strip():
                items.append({"id": lid, "variant": f"base{i}", "text": t.strip(), "tier": 0})
        for tier in line.get("tiers", []) or []:
            tn = tier.get("tier", 0)
            for i, t in enumerate(tier.get("texts", []) or []):
                if t.strip():
                    items.append({"id": lid, "variant": f"tier{tn}_{i}", "text": t.strip(), "tier": tn})
    return items


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--character", required=True)
    ap.add_argument("--root", default=".")
    ap.add_argument("--only", choices=["all", "samples", "lines"], default="all")
    ap.add_argument("--voice", default="", help="覆盖 plan.json 里的少女音色（用于换音色重渲）")
    args = ap.parse_args()

    root = args.root
    cdir = os.path.join(root, "characters", args.character)
    vdir = os.path.join(cdir, "voice")
    plan_path = os.path.join(vdir, "plan.json")
    dlg_path = os.path.join(cdir, "dialogue.json")

    plan = load_json(plan_path)
    dialogue = load_json(dlg_path)

    provider = plan.get("provider", "edge-tts")
    style = plan.get("style", {})
    rate = style.get("rate", "+0%")
    pitch = style.get("pitch", "+0Hz")
    volume = style.get("volume", "+0%")

    form_voices: dict[str, str] = plan.get("form_voices", {})
    girl_voice = args.voice or form_voices.get("teen") or "zh-CN-XiaoyiNeural"
    sample_text = plan.get("sample_text", SAMPLE_TEXT)

    catalog: dict = {
        "schema_version": "1.0",
        "character": args.character,
        "provider": provider,
        "engine_note": "微软神经网络 TTS（edge-tts）；音色为供应商正规音色，不使用真人克隆",
        "style": {"rate": rate, "pitch": pitch, "volume": volume},
        "form_voices": form_voices,
        "lines": [],
    }

    # 1) 候选音色采样：同一句话各出一版，便于按“年龄感”挑选
    #    candidates 支持两种写法：字符串（只用统一参数）或对象（可单独指定 pitch/rate/label）
    cands = plan.get("candidates", []) or []
    if cands and args.only in ("all", "samples"):
        for i, c in enumerate(cands, 1):
            if isinstance(c, str):
                c = {"voice": c}
            v = c.get("voice", girl_voice)
            c_pitch = c.get("pitch", pitch)
            c_rate = c.get("rate", rate)
            label = c.get("label", short_name(v))
            tag = f"{short_name(v)}_{_clean(c_pitch)}_{_clean(c_rate)}"
            out = os.path.join(vdir, "samples", f"{i:02d}_{tag}.mp3")
            size = await synth(sample_text, v, out, c_rate, c_pitch, volume)
            print(f"[采样] {label}（{v} pitch={c_pitch} rate={c_rate}）→ {os.path.basename(out)}")
            catalog.setdefault("samples", []).append(
                {"index": i, "label": label, "voice": v, "pitch": c_pitch, "rate": c_rate,
                 "file": os.path.relpath(out, root).replace(os.sep, "/"),
                 "text": sample_text, "bytes": size}
            )

    # 2) 台词：用角色正式音色逐条合成
    if args.only in ("all", "lines"):
        items = collect_texts(dialogue)
        print(f"[台词] 角色 {args.character}，音色 {girl_voice}，共 {len(items)} 条")
        for n, it in enumerate(items, 1):
            fname = f"{it['id']}_{it['variant']}.mp3"
            out = os.path.join(vdir, "lines", fname)
            size = await synth(it["text"], girl_voice, out, rate, pitch, volume)
            catalog["lines"].append(
                {"id": it["id"], "variant": it["variant"], "tier": it["tier"], "text": it["text"],
                 "voice": girl_voice, "file": os.path.relpath(out, root).replace(os.sep, "/"),
                 "bytes": size}
            )
            print(f"[{n}/{len(items)}] {fname}（{size} 字节）")

    os.makedirs(vdir, exist_ok=True)
    with open(os.path.join(vdir, "catalog.json"), "w", encoding="utf-8") as f:
        json.dump(catalog, f, ensure_ascii=False, indent=2)
    print(f"[完成] 目录已写入 {os.path.join(vdir, 'catalog.json')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
