#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""voice_local.py — 沙箱内本地合成中文角色语音（Piper VITS + 拼音音素）。

为什么需要它：Piper 的官方中文音素器（g2pW）要联网下载模型，沙箱出网白名单到不了；
本脚本用 pypinyin 生成同样的“声母/韵母/声调”音素序列，直接喂给 ONNX 模型，
所以**不联网也能合成**，可用于预览试听与批量出音频。

音色模型放在 ~/.cache/piper-voices/（.onnx + .onnx.json 成对），例如：
  zh_CN-huayan-medium   华言（温柔女声）
  zh_CN-xiao_ya-medium  小雅（少女感女声）
模型来源为公开 GitHub 仓库中的 Piper 音色（正规音色表，不克隆真人声音）。

用法：
  python3 tools/voice_local.py --voice zh_CN-xiao_ya-medium --text "你好呀" --out /tmp/a.wav
  python3 tools/voice_local.py --voice zh_CN-xiao_ya-medium --text "你好" --out /tmp/b.wav --pitch 1.06
  python3 tools/voice_local.py --render-dialogue --character xiaoxun --root . --voice zh_CN-xiao_ya-medium
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import wave

import numpy as np
import onnxruntime as ort

MODEL_DIR = os.path.expanduser("~/.cache/piper-voices")

# 音素分组边界：声调与停顿之后补一个 PAD（对齐 piper 的 GROUP_END_PHONEMES）
GROUP_END = {"1", "2", "3", "4", "5", "。", "？", "！", ".", "?", "!", "—", "…"}

INITIALS = ["zh", "ch", "sh", "b", "p", "m", "f", "d", "t", "n", "l", "g", "k", "h",
            "j", "q", "x", "r", "z", "c", "s", "y", "w"]

# 文本里可直接当作音素的标点/停顿
PUNCT = set("。，、：；！？…—,.?!:; ")

SENT_SPLIT = re.compile(r"(?<=[。！？!?…；;])")
CLAUSE_SPLIT = re.compile(r"(?<=[，,、：:])")


def load_config(voice: str) -> dict:
    with open(os.path.join(MODEL_DIR, voice + ".onnx.json"), encoding="utf-8") as f:
        return json.load(f)


def split_initial_final(syl: str) -> tuple[str, str]:
    """把 pinyin 音节切成声母 + 韵母（其余部分原样返回）。"""
    for ini in INITIALS:
        if syl.startswith(ini):
            return ini, syl[len(ini):]
    return "", syl


def phonemize(text: str, id_map: dict) -> list[str]:
    """文本 → 音素序列（声母 / 韵母 / 声调 / 标点）。

    关键：必须**整句**交给 pypinyin，它才会用词组做多音字消歧
    （逐字转换会把 银行→yin2 xing2、重复→zhong4 fu4 念错，听起来就是“机械/念错字”）。
    """
    from pypinyin import Style, pinyin

    # 整句转换；非中文字符返回空串，稍后按字符对齐跳过
    readings = pinyin(text, style=Style.TONE3, heteronym=False,
                      neutral_tone_with_five=True,
                      errors=lambda s: [[""]] * len(s))
    out: list[str] = []
    for ch, rd in zip(text, readings):
        if ch in PUNCT:
            if ch in id_map:
                out.append(ch)
            continue
        py = (rd[0] if rd else "") or ""
        py = py.replace("ü", "v").replace("Ü", "v")
        m = re.match(r"^([a-z]+)([1-5])?$", py)
        if not m:
            continue                      # 非中文 / 数字等：跳过（保留标点停顿）
        syl, tone = m.group(1), (m.group(2) or "5")
        ini, fin = split_initial_final(syl)
        if fin not in id_map:             # 罕见韵母兜底
            fin = {"io": "o", "iai": "ai"}.get(fin, fin)
        if fin not in id_map:
            continue
        out.append(ini if ini in id_map else "Ø")
        out.append(fin)
        out.append(tone)
    return out


def phonemes_to_ids(phonemes: list[str], id_map: dict) -> list[int]:
    ids = list(id_map["^"])
    for p in phonemes:
        if p not in id_map:
            continue
        ids.extend(id_map[p])
        if p in GROUP_END:
            ids.extend(id_map["_"])
    ids.extend(id_map["$"])
    return ids


def phonemize_espeak(text: str, cfg: dict) -> list[str]:
    """espeak 类音色（如 huayan）：用 piper 自带的 espeak 桥生成 IPA 音素，不联网。"""
    from piper.phonemize_espeak import EspeakPhonemizer

    voice = cfg.get("espeak", {}).get("voice", "zh")
    groups = EspeakPhonemizer().phonemize(voice, text)
    out: list[str] = []
    for g in groups:
        out.extend(list(g))
    return out


def synth(text: str, voice: str, cfg: dict, sess: ort.InferenceSession,
          length_scale: float | None = None) -> np.ndarray:
    """合成一段音频，返回 float32 单声道波形。"""
    id_map = cfg["phoneme_id_map"]
    if cfg.get("phoneme_type") == "espeak":
        ph = phonemize_espeak(text, cfg)
    else:
        ph = []
        for sent in SENT_SPLIT.split(text):
            for clause in CLAUSE_SPLIT.split(sent):
                clause = clause.strip()
                if clause:
                    ph.extend(phonemize(clause, id_map))
    if not ph:
        return np.zeros(0, dtype=np.float32)
    ids = phonemes_to_ids(ph, id_map)
    infer = cfg.get("inference", {})
    scales = np.array([infer.get("noise_scale", 0.667),
                       length_scale if length_scale else infer.get("length_scale", 1.0),
                       infer.get("noise_w", 0.8)], dtype=np.float32)
    audio = sess.run(None, {
        "input": np.array([ids], dtype=np.int64),
        "input_lengths": np.array([len(ids)], dtype=np.int64),
        "scales": scales,
    })[0]
    return np.asarray(audio).reshape(-1).astype(np.float32)


def time_stretch(x: np.ndarray, speed: float, method: str = "wsola") -> np.ndarray:
    """变速不变调。method=wsola 用波形相似叠加（语音更自然，去金属音），phase 用相位声码器兜底。"""
    if abs(speed - 1.0) < 1e-3 or x.size == 0:
        return x
    if method == "wsola":
        try:
            import audiotsm
            from audiotsm.io.array import ArrayReader, ArrayWriter

            reader = ArrayReader(x.reshape(1, -1).astype(np.float32))
            writer = ArrayWriter(channels=1)
            tsm = audiotsm.wsola(channels=1, speed=speed)
            tsm.run(reader, writer)
            return np.asarray(writer.data, dtype=np.float32).reshape(-1)
        except Exception as exc:  # noqa: BLE001 - 装不上就退回相位声码器
            print(f"[提示] WSOLA 不可用（{exc}），改用相位声码器", file=sys.stderr)
    import librosa

    return np.asarray(librosa.effects.time_stretch(x, rate=speed), dtype=np.float32)


def pitch_shift(x: np.ndarray, factor: float, method: str = "resample") -> np.ndarray:
    """把音高与共振峰抬高 factor 倍（少女化）。

    method=resample：只做降采样，音高与共振峰一起抬高，副作用是语速略快（无金属音）；
    method=stretch ：降采样后再变速拉回原长（语速不变，理论上更自然，需 WSOLA）。
    """
    if abs(factor - 1.0) < 1e-3 or x.size == 0:
        return x
    n_out = int(round(x.size / factor))
    src = np.linspace(0, x.size - 1, n_out)
    y = np.interp(src, np.arange(x.size), x).astype(np.float32)
    if method == "stretch":
        y = time_stretch(y, 1.0 / factor, method="wsola")
    return y


def write_wav(path: str, x: np.ndarray, sr: int) -> int:
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    pcm = np.clip(x, -1.0, 1.0)
    pcm = (pcm * 32767.0).astype("<i2")
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(pcm.tobytes())
    return os.path.getsize(path)


def open_voice(voice: str) -> tuple[dict, ort.InferenceSession]:
    cfg = load_config(voice)
    sess = ort.InferenceSession(os.path.join(MODEL_DIR, voice + ".onnx"),
                                providers=["CPUExecutionProvider"])
    return cfg, sess


def load_lines(root: str, character: str) -> list[dict]:
    """收集 dialogue.json 的全部台词（基础 + 好感档位变体）。"""
    with open(os.path.join(root, "characters", character, "dialogue.json"), encoding="utf-8") as f:
        raw = f.read()
    raw = re.sub(r"(?m)^\s*//.*$", "", raw)  # 允许 // 注释
    dlg = json.loads(raw)
    items = []
    for line in dlg.get("lines", []):
        lid = line.get("id", "line")
        for i, t in enumerate(line.get("texts") or []):
            if t.strip():
                items.append({"id": lid, "variant": f"base{i}", "text": t.strip()})
        for tier in line.get("tiers") or []:
            tn = tier.get("tier", 0)
            for i, t in enumerate(tier.get("texts") or []):
                if t.strip():
                    items.append({"id": lid, "variant": f"tier{tn}_{i}", "text": t.strip()})
    return items


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--voice", default="zh_CN-xiao_ya-medium")
    ap.add_argument("--text", default="")
    ap.add_argument("--out", default="")
    ap.add_argument("--pitch", type=float, default=1.0, help="升调系数（1.0 原声）")
    ap.add_argument("--length-scale", type=float, default=0.0)
    ap.add_argument("--render-dialogue", action="store_true")
    ap.add_argument("--character", default="xiaoxun")
    ap.add_argument("--root", default=".")
    ap.add_argument("--shift-method", choices=["resample", "stretch"], default="resample",
                    help="resample=只降采样（无金属音，语速略快）；stretch=变速拉回原长")
    args = ap.parse_args()

    if not os.path.isdir(MODEL_DIR):
        print(f"缺少音色模型目录 {MODEL_DIR}", file=sys.stderr)
        return 2

    cfg, sess = open_voice(args.voice)
    sr = cfg["audio"]["sample_rate"]

    if args.render_dialogue:
        items = load_lines(args.root, args.character)
        outdir = os.path.join(args.root, "characters", args.character, "voice", "lines_" + args.voice)
        for n, it in enumerate(items, 1):
            x = synth(it["text"], args.voice, cfg, sess, args.length_scale or None)
            x = pitch_shift(x, args.pitch, args.shift_method)
            path = os.path.join(outdir, f"{it['id']}_{it['variant']}.wav")
            size = write_wav(path, x, sr)
            print(f"[{n}/{len(items)}] {os.path.basename(path)}  {size // 1024} KB")
        return 0

    x = synth(args.text, args.voice, cfg, sess, args.length_scale or None)
    x = pitch_shift(x, args.pitch, args.shift_method)
    size = write_wav(args.out, x, sr)
    print(f"{args.out}: {size // 1024} KB, {round(x.size / sr, 2)} 秒, 音色 {args.voice}, 升调 {args.pitch}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
