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
import shutil
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import voice_prosody as vp       # noqa: E402 —— 同目录的演出引擎（纯逻辑，无网络依赖）

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


def _ffmpeg() -> str:
    """Actions 的 ubuntu-latest 自带 ffmpeg；沙箱里没有，所以必须能降级。"""
    return shutil.which("ffmpeg") or ""


def _silence_mp3(path: str, ms: int) -> bool:
    ff = _ffmpeg()
    if not ff:
        return False
    cmd = [ff, "-v", "error", "-f", "lavfi", "-i",
           "anullsrc=channel_layout=mono:sample_rate=24000",
           "-t", f"{ms / 1000.0:.3f}", "-c:a", "libmp3lame", "-b:a", "48k", "-y", path]
    return subprocess.run(cmd, capture_output=True).returncode == 0


def _concat_mp3(parts: list[str], out: str) -> bool:
    """优先用 ffmpeg 的 concat demuxer（统一重编码，接缝最干净）；没有 ffmpeg 就二进制拼。

    二进制拼接对同一编码器同参数的 mp3 是可行的（edge-tts 全部是 24kHz/48kbps/mono），
    代价是段间没有静音、少数播放器会在接缝处轻微咔哒。所以只当兜底。
    """
    ff = _ffmpeg()
    if ff:
        lst = out + ".txt"
        with open(lst, "w", encoding="utf-8") as f:
            for p in parts:
                f.write("file '%s'\n" % os.path.abspath(p).replace("'", "'\\''"))
        rc = subprocess.run([ff, "-v", "error", "-f", "concat", "-safe", "0", "-i", lst,
                             "-c:a", "libmp3lame", "-b:a", "48k", "-y", out],
                            capture_output=True).returncode
        try:
            os.remove(lst)
        except OSError:
            pass
        if rc == 0:
            return True
    with open(out, "wb") as w:
        for p in parts:
            with open(p, "rb") as r:
                w.write(r.read())
    return os.path.getsize(out) > 1024


async def synth_sheet(sheet: dict, voice: str, path: str) -> int:
    """按演出单逐段合成再拼起来 —— edge-tts 没有 style，这是让一句话内部有起伏的唯一办法。

    任何一段失败就整句退回「一次调用」的老路子（宁可平，不可缺）。
    """
    segs = vp.to_edge(sheet)
    if len(segs) == 1 and not segs[0]["gap_ms"]:
        s0 = segs[0]
        return await synth(s0["text"], voice, path, s0["rate"], s0["pitch"], s0["volume"])

    tmp = tempfile.mkdtemp(prefix="prosody_")
    parts: list[str] = []
    try:
        for i, sg in enumerate(segs):
            fp = os.path.join(tmp, "%02d.mp3" % i)
            await synth(sg["text"], voice, fp, sg["rate"], sg["pitch"], sg["volume"])
            parts.append(fp)
            if sg["gap_ms"]:
                gp = os.path.join(tmp, "%02d_gap.mp3" % i)
                if _silence_mp3(gp, sg["gap_ms"]):
                    parts.append(gp)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        if not _concat_mp3(parts, path):
            raise RuntimeError("拼接失败")
        return os.path.getsize(path)
    except Exception as exc:  # noqa: BLE001
        print(f"[降级] 分段合成失败（{exc}），退回整句一次合成：{sheet['text'][:14]}…", file=sys.stderr)
        avg_r = sum(x["rate_pct"] for x in sheet["segments"]) // max(1, len(sheet["segments"]))
        avg_p = sum(x["pitch_hz"] for x in sheet["segments"]) // max(1, len(sheet["segments"]))
        return await synth(sheet["text"], voice, path, f"{avg_r:+d}%", f"{avg_p:+d}Hz", "+0%")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


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
    ap.add_argument("--only", choices=["all", "samples", "lines", "demo", "ab"], default="all")
    ap.add_argument("--prosody", choices=["on", "off"], default="on",
                    help="on=按 config/prosody.json 排演出单分段合成（默认）；off=老的整句一次合成")
    ap.add_argument("--profile", default="", help="语感档，默认取 plan.json 的 prosody.profile")
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

    # 语感表（用户 2026-10-17：「情绪变化、语气都没有变化」）。读不到就退回老路子，不阻断合成。
    use_prosody = args.prosody == "on"
    pcfg: dict = {}
    profile_id = args.profile or plan.get("prosody", {}).get("profile", "moe_shoujo")
    if use_prosody:
        try:
            pcfg = vp.load_cfg(root)
            if profile_id not in pcfg.get("profiles", {}):
                print(f"[警告] 语感档 {profile_id} 不在 config/prosody.json 里，退回 moe_shoujo",
                      file=sys.stderr)
                profile_id = "moe_shoujo"
        except Exception as exc:  # noqa: BLE001
            print(f"[警告] 读不到 config/prosody.json（{exc}），本次按整句一次合成", file=sys.stderr)
            use_prosody = False

    failed: list[dict] = []
    catalog: dict = {
        "schema_version": "1.0",
        "character": args.character,
        "provider": provider,
        "engine_note": "微软神经网络 TTS（edge-tts）；音色为供应商正规音色，不使用真人克隆",
        "style": {"rate": rate, "pitch": pitch, "volume": volume},
        "prosody": {"enabled": use_prosody, "profile": profile_id if use_prosody else ""},
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
            try:
                size = await synth(sample_text, v, out, c_rate, c_pitch, volume)
            except Exception as exc:  # noqa: BLE001 - 某个音色失效不该拖垮整批
                print(f"[跳过] {label}（{v}）：{exc}", file=sys.stderr)
                failed.append({"kind": "sample", "label": label, "voice": v, "error": str(exc)[:200]})
                continue
            print(f"[采样] {label}（{v} pitch={c_pitch} rate={c_rate}）→ {os.path.basename(out)}")
            catalog.setdefault("samples", []).append(
                {"index": i, "label": label, "voice": v, "pitch": c_pitch, "rate": c_rate,
                 "file": os.path.relpath(out, root).replace(os.sep, "/"),
                 "text": sample_text, "bytes": size}
            )

    # 2) 台词：用角色正式音色逐条合成
    if args.only in ("all", "lines"):
        items = collect_texts(dialogue)
        print(f"[台词] 角色 {args.character}，音色 {girl_voice}，共 {len(items)} 条"
              f"，语感 {'开（' + profile_id + '）' if use_prosody else '关（整句一次合成）'}")
        emo_count: dict[str, int] = {}
        for n, it in enumerate(items, 1):
            fname = f"{it['id']}_{it['variant']}.mp3"
            out = os.path.join(vdir, "lines", fname)
            sheet = None
            try:
                if use_prosody:
                    sheet = vp.sheet_for(it["id"], it["text"], pcfg, profile_id)
                    size = await synth_sheet(sheet, girl_voice, out)
                else:
                    size = await synth(it["text"], girl_voice, out, rate, pitch, volume)
            except Exception as exc:  # noqa: BLE001
                print(f"[跳过] {fname}：{exc}", file=sys.stderr)
                failed.append({"kind": "line", "id": it["id"], "variant": it["variant"],
                               "error": str(exc)[:200]})
                continue
            rec = {"id": it["id"], "variant": it["variant"], "tier": it["tier"], "text": it["text"],
                   "voice": girl_voice, "file": os.path.relpath(out, root).replace(os.sep, "/"),
                   "bytes": size}
            if sheet:
                emo_count[sheet["emotion"]] = emo_count.get(sheet["emotion"], 0) + 1
                rec["emotion"] = sheet["emotion"]
                rec["emotion_why"] = sheet["why"]
                rec["segments"] = [{"text": x["text"], "rate_pct": x["rate_pct"],
                                    "pitch_hz": x["pitch_hz"], "volume_pct": x["volume_pct"],
                                    "gap_ms": x["gap_ms"], "marks": x["marks"]}
                                   for x in sheet["segments"]]
            catalog["lines"].append(rec)
            tag = f"[{sheet['emotion']}]" if sheet else ""
            print(f"[{n}/{len(items)}] {fname} {tag}（{size} 字节）")
        if emo_count:
            catalog["emotion_histogram"] = emo_count
            print("[情绪分布] " + "  ".join(f"{k}×{v}" for k, v in sorted(emo_count.items())))

    # 3) 情绪对照样本：同一句话 × 多种情绪，用来一耳朵听出"语气到底有没有变"
    if args.only in ("all", "demo"):
        demo_line = plan.get("prosody", {}).get(
            "demo_text", "今天也一起加油吧，我就在这儿，一直陪着你。")
        demos = plan.get("prosody", {}).get(
            "demo_emotions", ["neutral", "happy", "shy", "angry", "sad", "sleepy"])
        print(f"[对照] 同一句 × {len(demos)} 种情绪：{demo_line}")
        for emo in demos:
            out = os.path.join(vdir, "demo", f"{emo}.mp3")
            try:
                sheet = vp.sheet_for("", demo_line, pcfg, profile_id, emotion=emo)
                size = await synth_sheet(sheet, girl_voice, out)
            except Exception as exc:  # noqa: BLE001
                print(f"[跳过] demo/{emo}：{exc}", file=sys.stderr)
                failed.append({"kind": "demo", "emotion": emo, "error": str(exc)[:200]})
                continue
            catalog.setdefault("demo", []).append(
                {"emotion": emo, "text": demo_line, "voice": girl_voice,
                 "file": os.path.relpath(out, root).replace(os.sep, "/"), "bytes": size,
                 "segments": [{"text": x["text"], "rate_pct": x["rate_pct"],
                               "pitch_hz": x["pitch_hz"], "gap_ms": x["gap_ms"]}
                              for x in sheet["segments"]]})
            print(f"[对照] {emo} → {size} 字节")

    # 4) A/B 对照：同一句话，语感关 vs 语感开。用户说"听不出变化"，这组就是用来回答这句的。
    if args.only in ("all", "ab") and pcfg:
        ab_list = plan.get("prosody", {}).get("ab") or [
            {"id": "", "text": plan.get("prosody", {}).get(
                "demo_text", "今天也一起加油吧，我就在这儿，一直陪着你。"), "note": "中性长句"},
            {"id": "hammer_1", "text": "咚——！好痛呀，你是想把我敲成扁扁的吗？", "note": "惊讶"},
            {"id": "pat_combo", "text": "摸这么多次…我、我会害羞的啦！", "note": "害羞"},
            {"id": "mood_joy_1", "text": "今天好开心呀！", "note": "开心"},
            {"id": "wake_1", "text": "唔…我没有睡着哦。", "note": "迷糊"},
        ]
        print(f"[A/B] 语感关 vs 语感开，共 {len(ab_list)} 组")
        for i, ab in enumerate(ab_list, 1):
            txt = ab["text"]
            sheet = vp.sheet_for(ab.get("id", ""), txt, pcfg, profile_id,
                                 emotion=ab.get("emotion"))
            rec = {"index": i, "id": ab.get("id", ""), "text": txt, "note": ab.get("note", ""),
                   "emotion": sheet["emotion"], "voice": girl_voice,
                   "segments": [{"text": x["text"], "rate_pct": x["rate_pct"],
                                 "pitch_hz": x["pitch_hz"], "volume_pct": x["volume_pct"],
                                 "gap_ms": x["gap_ms"], "marks": x["marks"]}
                                for x in sheet["segments"]]}
            try:    # 关：老路子，整句一次合成，参数就是 plan.json 里的 +0/+0/+0
                off = os.path.join(vdir, "ab", f"{i:02d}_off.mp3")
                rec["bytes_off"] = await synth(txt, girl_voice, off, rate, pitch, volume)
                rec["file_off"] = os.path.relpath(off, root).replace(os.sep, "/")
                on = os.path.join(vdir, "ab", f"{i:02d}_on.mp3")
                rec["bytes_on"] = await synth_sheet(sheet, girl_voice, on)
                rec["file_on"] = os.path.relpath(on, root).replace(os.sep, "/")
            except Exception as exc:  # noqa: BLE001
                print(f"[跳过] ab/{i:02d}：{exc}", file=sys.stderr)
                failed.append({"kind": "ab", "index": i, "error": str(exc)[:200]})
                continue
            catalog.setdefault("ab", []).append(rec)
            print(f"[A/B] {i:02d} {ab.get('note','')} {sheet['emotion']} "
                  f"关 {rec['bytes_off']} / 开 {rec['bytes_on']} 字节")

    catalog["failed"] = failed
    os.makedirs(vdir, exist_ok=True)
    with open(os.path.join(vdir, "catalog.json"), "w", encoding="utf-8") as f:
        json.dump(catalog, f, ensure_ascii=False, indent=2)
    print(f"[完成] 目录已写入 {os.path.join(vdir, 'catalog.json')}"
          f"（失败 {len(failed)} 项）")
    # 全部失败才算失败（单个音色/台词失败不阻断整批，失败明细写在 catalog.failed）
    ok = len(catalog.get("samples", [])) + len(catalog.get("lines", []))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
