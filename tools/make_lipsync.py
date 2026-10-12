#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""make_lipsync.py - 给每条语音生成「口型包络」（A4 / LipSync）。

引擎侧只认一个东西：一串 0~1 的开口度采样（`values`）+ 帧率（`fps`）。
播放时按时间取样，喂给 `ParamMouthOpenY`，嘴就跟着说话开合。

两种来源：
  1. **音频包络（最准，优先用）**：给 wav 就直接算 RMS 包络。
     沙箱里没有 ffmpeg，mp3 解不开；真机上把 mp3 转成 wav 再跑这个脚本即可
     （`ffmpeg -i x.mp3 -ac 1 -ar 16000 x.wav`）。
  2. **文本节律（没有 wav 时的兜底）**：mp3 的**时长**可以不解码就拿到
     （直接数 MPEG 帧头），再把台词按音节铺进这段时长：
     汉字 = 1 音节，标点 = 停顿（闭嘴），每个音节一个"张—保持—收"的小包。
     这不是音素级口型，但节奏和真实语音对得上，比固定 3Hz flap 自然得多。

产物：characters/<角色>/voice/lipsync/<mp3 同名>.json
      { "id", "text", "dur", "fps", "source", "values":[...] }
      另外写一份 index.json 方便前端列出来。

用法：
  python3 tools/make_lipsync.py --character xiaoxun
  python3 tools/make_lipsync.py --wav 某句.wav --text "你好呀" --out 某句.json
"""
from __future__ import annotations
import argparse, json, math, os, struct, sys, unicodedata, wave

FPS = 30.0

# ---------------- MP3：只数帧头拿时长，不解码 ----------------
_BITRATE = {  # (version, layer) -> 索引表
    (3, 1): [0, 32, 64, 96, 128, 160, 192, 224, 256, 288, 320, 352, 384, 416, 448],
    (3, 2): [0, 32, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320, 384],
    (3, 3): [0, 32, 40, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320],
    (2, 1): [0, 32, 48, 56, 64, 80, 96, 112, 128, 144, 160, 176, 192, 224, 256],
    (2, 2): [0, 8, 16, 24, 32, 40, 48, 56, 64, 80, 96, 112, 128, 144, 160],
}
_BITRATE[(2, 3)] = _BITRATE[(2, 2)]
_SRATE = {3: [44100, 48000, 32000], 2: [22050, 24000, 16000], 0: [11025, 12000, 8000]}


def mp3_duration(path):
    """数 MPEG 音频帧头算时长（秒）。CBR/VBR 都行，不需要解码。"""
    data = open(path, "rb").read()
    i = 0
    if data[:3] == b"ID3":                      # 跳过 ID3v2
        size = ((data[6] & 0x7F) << 21) | ((data[7] & 0x7F) << 14) | \
               ((data[8] & 0x7F) << 7) | (data[9] & 0x7F)
        i = 10 + size
    total = 0.0
    n = len(data)
    while i + 4 <= n:
        if data[i] != 0xFF or (data[i + 1] & 0xE0) != 0xE0:
            i += 1
            continue
        ver = (data[i + 1] >> 3) & 3            # 3=MPEG1 2=MPEG2 0=MPEG2.5
        layer = (data[i + 1] >> 1) & 3          # 3=LayerI 2=II 1=III
        if ver == 1 or layer == 0:
            i += 1
            continue
        lay = {3: 1, 2: 2, 1: 3}[layer]
        vkey = 3 if ver == 3 else 2
        bi = (data[i + 2] >> 4) & 0xF
        si = (data[i + 2] >> 2) & 3
        if bi in (0, 15) or si == 3:
            i += 1
            continue
        bitrate = _BITRATE[(vkey, lay)][bi] * 1000
        srate = _SRATE[ver][si]
        pad = (data[i + 2] >> 1) & 1
        spf = 384 if lay == 1 else (1152 if (lay == 2 or ver == 3) else 576)
        if lay == 1:
            flen = (12 * bitrate // srate + pad) * 4
        else:
            flen = (spf // 8) * bitrate // srate + pad
        if flen <= 4:
            i += 1
            continue
        total += spf / float(srate)
        i += flen
    return total


# ---------------- wav：真·RMS 包络 ----------------
def wav_envelope(path, fps=FPS):
    with wave.open(path, "rb") as w:
        nch, sw, sr, nfr = w.getnchannels(), w.getsampwidth(), w.getframerate(), w.getnframes()
        raw = w.readframes(nfr)
    if sw != 2:
        raise SystemExit("[lipsync] 只支持 16bit wav（ffmpeg -acodec pcm_s16le）")
    n = len(raw) // 2
    samples = struct.unpack("<%dh" % n, raw[:n * 2])
    if nch > 1:
        samples = [sum(samples[i:i + nch]) / nch for i in range(0, n - nch + 1, nch)]
    step = max(1, int(sr / fps))
    vals = []
    for i in range(0, len(samples), step):
        chunk = samples[i:i + step]
        if not chunk:
            break
        rms = math.sqrt(sum(float(v) * v for v in chunk) / len(chunk))
        vals.append(rms)
    if not vals:
        return [0.0], nfr / float(sr)
    srt = sorted(vals)
    hi = srt[int(len(srt) * 0.95)] or 1.0
    vals = [min(1.0, (v / hi) ** 0.7) for v in vals]
    return vals, nfr / float(sr)


# ---------------- 文本节律 ----------------
PAUSE = {"，": 0.5, "、": 0.4, "。": 0.9, "！": 0.9, "？": 0.9, "…": 0.8, "—": 0.5,
         ",": 0.5, ".": 0.8, "!": 0.8, "?": 0.8, "~": 0.3, " ": 0.2}


def syllables(text):
    """把台词拆成 [('s', 权重) / ('p', 停顿权重)]；汉字 1 音节，英文按 3 字母 1 音节。"""
    out, word = [], 0
    for ch in text:
        if ch in PAUSE:
            if word:
                out += [("s", 1.0)] * max(1, round(word / 3.0)); word = 0
            out.append(("p", PAUSE[ch]))
        elif unicodedata.category(ch).startswith("L") and ord(ch) < 128:
            word += 1
        elif ord(ch) > 0x2E80:                  # CJK
            if word:
                out += [("s", 1.0)] * max(1, round(word / 3.0)); word = 0
            out.append(("s", 1.0))
        elif ch.isdigit():
            out.append(("s", 1.0))
    if word:
        out += [("s", 1.0)] * max(1, round(word / 3.0))
    return out or [("s", 1.0)]


def text_envelope(text, dur, fps=FPS, seed=0):
    units = syllables(text)
    total_w = sum(w for _, w in units) or 1.0
    head, tail = dur * 0.06, dur * 0.08         # 前后留一点静音
    body = max(0.1, dur - head - tail)
    n = max(2, int(round(dur * fps)))
    vals = [0.0] * n
    t = head
    h = seed * 2654435761 & 0xFFFFFFFF
    for kind, w in units:
        span = body * (w / total_w)
        if kind == "s":
            h = (h * 1103515245 + 12345) & 0x7FFFFFFF
            amp = 0.55 + 0.45 * ((h >> 8) % 1000) / 999.0     # 每个音节开口不一样
            a, hold = span * 0.35, span * 0.25                 # 张 / 保持 / 收
            rel = span - a - hold
            for k in range(n):
                tt = k / fps - t
                if tt < 0 or tt > span:
                    continue
                if tt < a:
                    v = amp * (tt / a) ** 0.7
                elif tt < a + hold:
                    v = amp
                else:
                    v = amp * max(0.0, 1.0 - (tt - a - hold) / max(rel, 1e-3)) ** 1.3
                vals[k] = max(vals[k], v)
        t += span
    for _ in range(2):                          # 轻微平滑，去掉台阶
        vals = [vals[0]] + [(vals[i - 1] + 2 * vals[i] + vals[i + 1]) / 4.0
                            for i in range(1, n - 1)] + [vals[-1]]
    vals[0] = vals[-1] = 0.0
    return [round(min(1.0, max(0.0, v)), 3) for v in vals]


def write_env(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    json.dump(obj, open(path, "w", encoding="utf-8"), ensure_ascii=False)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--character")
    ap.add_argument("--root", default=".")
    ap.add_argument("--fps", type=float, default=FPS)
    ap.add_argument("--wav")
    ap.add_argument("--text", default="")
    ap.add_argument("--out")
    args = ap.parse_args()

    if args.wav:
        vals, dur = wav_envelope(args.wav, args.fps)
        out = args.out or (os.path.splitext(args.wav)[0] + ".json")
        write_env(out, {"id": os.path.basename(out)[:-5], "text": args.text,
                        "dur": round(dur, 3), "fps": args.fps, "source": "wav_rms",
                        "values": [round(v, 3) for v in vals]})
        print(f"口型包络（音频）→ {out}：{dur:.2f}s / {len(vals)} 帧")
        return

    if not args.character:
        raise SystemExit("用法：--character <角色>  或  --wav <文件>")
    cdir = os.path.join(args.root, "characters", args.character)
    cat_path = os.path.join(cdir, "voice", "catalog.json")
    if not os.path.exists(cat_path):
        raise SystemExit(f"[lipsync] 找不到语音目录清单：{cat_path}（先跑 voice_render.py）")
    cat = json.load(open(cat_path, encoding="utf-8"))
    outdir = os.path.join(cdir, "voice", "lipsync")
    index, ok, miss = [], 0, 0
    for ln in cat.get("lines", []):
        mp3 = os.path.join(args.root, ln["file"]) if not os.path.isabs(ln["file"]) else ln["file"]
        base = os.path.splitext(os.path.basename(mp3))[0]
        if not os.path.exists(mp3):
            miss += 1
            continue
        dur = mp3_duration(mp3)
        if dur <= 0.05:
            miss += 1
            continue
        vals = text_envelope(ln.get("text", ""), dur, args.fps, seed=abs(hash(base)) % 9973)
        write_env(os.path.join(outdir, base + ".json"),
                  {"id": base, "line": ln["id"], "text": ln.get("text", ""),
                   "dur": round(dur, 3), "fps": args.fps, "source": "text_rhythm",
                   "values": vals})
        index.append({"id": base, "line": ln["id"], "text": ln.get("text", ""),
                      "dur": round(dur, 3)})
        ok += 1
    json.dump({"character": args.character, "fps": args.fps, "count": len(index),
               "items": index},
              open(os.path.join(outdir, "index.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    avg = sum(i["dur"] for i in index) / max(1, len(index))
    print(f"口型包络（文本节律）：{ok} 条 → {outdir}，平均时长 {avg:.2f}s"
          + (f"；{miss} 条缺音频跳过" if miss else ""))


if __name__ == "__main__":
    main()
