#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""voice_pitch.py — 音色“少女化”处理：抬音高 + 抬共振峰，语速可选。

原理（这也是网上做“少女音”的常规后处理）：
  1) 重采样把音高与共振峰一起抬高（人听起来像“更小的人”）；
  2) 再用相位声码器把时长拉回原长（音高不变），于是“音高更高、共鸣腔更小、语速不变”。
  这样比单纯调 pitch 更接近真实的少女音色，不会变成“成年女声念高音”。

自带测量：用 pyin 估计基频中位数（F0），少女区间参考：
  成年女声 ≈ 165–255 Hz，少女 ≈ 200–300 Hz，童声 ≈ 250–400 Hz。

用法：
  python3 tools/voice_pitch.py --in a.wav --out b.wav --factor 1.25
  python3 tools/voice_pitch.py --in a.wav --out b.wav --target-f0 260
  python3 tools/voice_pitch.py --in a.wav --measure
"""
from __future__ import annotations

import argparse
import os
import sys
import wave

import numpy as np

try:
    import librosa
    import soundfile as sf
except ImportError:  # pragma: no cover
    print("需要 librosa 与 soundfile：pip install librosa soundfile", file=sys.stderr)
    raise SystemExit(2)


def read_wav(path: str) -> tuple[np.ndarray, int]:
    with wave.open(path, "rb") as w:
        sr = w.getframerate()
        n = w.getnframes()
        ch = w.getnchannels()
        raw = w.readframes(n)
    x = np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0
    if ch > 1:
        x = x.reshape(-1, ch).mean(axis=1)
    return x, sr


def write_wav(path: str, x: np.ndarray, sr: int) -> int:
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    pcm = (np.clip(x, -1.0, 1.0) * 32767.0).astype("<i2")
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(pcm.tobytes())
    return os.path.getsize(path)


def median_f0(x: np.ndarray, sr: int) -> float:
    """基频中位数（只统计有声音帧）。"""
    f0, voiced, _ = librosa.pyin(x, fmin=80, fmax=500, sr=sr, frame_length=1024)
    vals = f0[np.isfinite(f0)]
    if vals.size == 0:
        return 0.0
    return float(np.median(vals))


def youthify(x: np.ndarray, sr: int, factor: float, tempo: float = 1.0) -> np.ndarray:
    """音高+共振峰 ×factor（时长不变），再用 tempo 调整语速（>1 更快）。

    注意 resample 的方向：把 orig_sr 设成 sr*factor、target_sr 设成 sr 才是“降采样”，
    播放时音高与共振峰一起抬高（像共鸣腔变小），再用 time_stretch(rate=1/factor) 把时长拉回。
    """
    if abs(factor - 1.0) > 1e-3:
        up = librosa.resample(x, orig_sr=int(round(sr * factor)), target_sr=sr,
                              res_type="soxr_hq" if _has_soxr() else "kaiser_best")
        up = np.asarray(up, dtype=np.float32)
        x = _stretch(up, 1.0 / factor)
    if abs(tempo - 1.0) > 1e-3:
        x = _stretch(x, tempo)
    return x


def _stretch(x: np.ndarray, speed: float) -> np.ndarray:
    """变速不变调：优先 WSOLA（波形相似叠加，语音最自然），失败退回相位声码器。"""
    try:
        from audiotsm import wsola
        from audiotsm.io.array import ArrayReader, ArrayWriter

        reader = ArrayReader(x.reshape(1, -1).astype(np.float32))
        writer = ArrayWriter(channels=1)
        wsola(channels=1, speed=speed).run(reader, writer)
        return np.asarray(writer.data, dtype=np.float32).reshape(-1)
    except Exception as exc:  # noqa: BLE001
        print(f"[提示] WSOLA 不可用（{exc}），改用相位声码器", file=sys.stderr)
    return np.asarray(librosa.effects.time_stretch(x, rate=speed), dtype=np.float32)


def _has_soxr() -> bool:
    try:
        import soxr  # noqa: F401
        return True
    except ImportError:
        return False


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", required=True)
    ap.add_argument("--out", default="")
    ap.add_argument("--factor", type=float, default=0.0, help="音高+共振峰倍数（1.25 = 抬高 25%）")
    ap.add_argument("--target-f0", type=float, default=0.0, help="目标基频中位数（Hz），自动算 factor")
    ap.add_argument("--tempo", type=float, default=1.0, help="语速倍数（>1 更快）")
    ap.add_argument("--measure", action="store_true", help="只测量基频，不处理")
    args = ap.parse_args()

    x, sr = read_wav(args.inp)
    f0 = median_f0(x, sr)
    print(f"输入 {os.path.basename(args.inp)}: 时长 {len(x)/sr:.2f}s，基频中位数 {f0:.1f} Hz")

    if args.measure:
        return 0

    factor = args.factor
    if args.target_f0 > 0:
        if f0 <= 0:
            print("无法测量基频，请改用 --factor", file=sys.stderr)
            return 3
        factor = args.target_f0 / f0
    if factor <= 0:
        print("需要 --factor 或 --target-f0", file=sys.stderr)
        return 2

    y = youthify(x, sr, factor, args.tempo)
    out = args.out or args.inp.replace(".wav", f"_y{factor:.2f}.wav")
    size = write_wav(out, y, sr)
    f0b = median_f0(y, sr)
    print(f"输出 {os.path.basename(out)}: 音高×{factor:.3f} 语速×{args.tempo:.2f}，"
          f"基频 {f0:.0f}→{f0b:.0f} Hz，时长 {len(y)/sr:.2f}s，{size//1024} KB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
