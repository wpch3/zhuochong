#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""voice_prosody.py — 把一句台词翻成「演出单」：谁在什么情绪下、哪里停、哪里重、尾音怎么挑。

为什么需要它（用户 2026-10-17：「语音的情绪变化、语气，我听测试台词都没有变化」）：
  现在 39 条台词走的是 edge-tts 免费通道，**一次调用只能给整句一组 rate/pitch/volume**，
  而且官方 README 明说移除了 SSML style ⇒ 一句话从头到尾一个调子，当然听不出情绪。
  念稿感的根源不是发音，是韵律四要素（节奏 / 停顿 / 重音 / 语调）全被做成了默认值。

这里的解法：
  1) 按标点与意群把一句切成若干段；
  2) 每段单独给 rate / pitch / volume（首段起势、尾段上扬、语气词拖长、关键词加重）；
  3) 段间按标点插静音（气口）；
  4) 整句再叠一层「情绪」偏移（开心更快更高、困倦更慢更低、萌系生气是上扬不是压低）。
  edge-tts 走「分段合成 + 拼接」；Azure 正规通道可以直接出 mstts:express-as 的 SSML；
  MiniMax 走 emotion 参数。三条路都由同一张 config/prosody.json 驱动。

所有数值都在 config/prosody.json 里，**加一种语感 = 加一条配置，不改这个 .py**。

用法：
  python3 tools/voice_prosody.py --selftest
  python3 tools/voice_prosody.py --show "哇！别敲啦，会痛的！" --id hammer_1
  python3 tools/voice_prosody.py --show "我陪着你。" --emotion gentle --ssml --voice zh-CN-XiaoyiNeural
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys

# 句末标点（切段点）与句中标点（切段点，但停顿更短）
END_PUNCT = "。！？…—"
MID_PUNCT = "，、；：,;:"
ALL_PUNCT = END_PUNCT + MID_PUNCT


def load_jsonc(path: str) -> dict:
    """读取允许 // 行注释的 JSON（与 tools/voice_render.py、C 侧 zjson 口径一致）。"""
    with open(path, encoding="utf-8") as f:
        raw = f.read()
    out, in_str, esc, i = [], False, False, 0
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


def load_cfg(root: str = ".") -> dict:
    return load_jsonc(os.path.join(root, "config", "prosody.json"))


# ---------------------------------------------------------------- 情绪判定

def infer_emotion(line_id: str, text: str, cfg: dict) -> tuple[str, str]:
    """返回 (情绪, 依据)。优先级：台词 id 精确命中 > id 前缀 > 文本线索 > neutral。

    为什么 id 优先于文本：台词 id 是我们自己定的（hammer=被锤、pat=被摸），
    比关键词更可靠；文本线索只在 id 没覆盖时兜底。
    """
    hints = cfg.get("line_id_hints", {})
    base_id = re.sub(r"_\d+$", "", line_id or "")
    if line_id and line_id in hints:
        return hints[line_id], f"id 精确命中 {line_id}"
    if base_id and base_id in hints:
        return hints[base_id], f"id 前缀命中 {base_id}"
    for key, emo in hints.items():
        if base_id and base_id.startswith(key):
            return emo, f"id 前缀命中 {key}"
    for cue in cfg.get("text_cues", []):
        for w in cue.get("any", []):
            if w in (text or ""):
                return cue["emotion"], f"文本线索「{w}」"
    return "neutral", "无线索，按平静处理"


# ---------------------------------------------------------------- 切段

def split_segments(text: str, max_chars: int, max_segments: int) -> list[tuple[str, str]]:
    """切成 [(正文, 尾随标点)]。标点单独拿出来是因为它决定停顿时长，但不该被念出来。"""
    segs: list[tuple[str, str]] = []
    buf = ""
    i = 0
    while i < len(text):
        ch = text[i]
        if ch in ALL_PUNCT:
            punct = ch
            # 省略号 / 破折号常常连写，合并成一个
            while i + 1 < len(text) and text[i + 1] == ch:
                punct += text[i + 1]
                i += 1
            if buf.strip():
                segs.append((buf.strip(), punct))
                buf = ""
            elif segs:                      # 标点挨着标点：并到上一段
                segs[-1] = (segs[-1][0], segs[-1][1] + punct)
            i += 1
            continue
        buf += ch
        i += 1
    if buf.strip():
        segs.append((buf.strip(), ""))

    # 过长的段再切一刀（换气）：真人每 8~12 字就会换一次气
    out: list[tuple[str, str]] = []
    for body, punct in segs:
        while len(body) > max_chars:
            cut = max_chars
            out.append((body[:cut], ""))    # 空标点 = 只换气，不是标点停顿
            body = body[cut:]
        out.append((body, punct))

    # 段数封顶：段太多会让拼接处的接缝变明显
    if len(out) > max_segments:
        merged = out[:max_segments - 1]
        tail_body = "".join(b for b, _ in out[max_segments - 1:])
        tail_punct = out[-1][1]
        merged.append((tail_body, tail_punct))
        out = merged
    return out


# ---------------------------------------------------------------- 演出单

def plan_line(text: str, emotion: str, cfg: dict, profile_id: str = "moe_shoujo") -> dict:
    """把一句话排成演出单。返回 {emotion, profile, segments:[...]}。"""
    prof = cfg["profiles"][profile_id]
    emo = cfg["emotions"].get(emotion) or cfg["emotions"]["neutral"]
    lim = cfg.get("_restraint", {})
    max_rate = lim.get("max_abs_rate_pct", 30)
    max_pitch = lim.get("max_abs_pitch_hz", 45)
    pauses = cfg.get("pauses_ms", {})
    max_pause = int(cfg.get("_restraint", {}).get("max_pause_ms", 700))

    segs = split_segments(text, prof.get("breath_every_chars", 11), prof.get("max_segments", 8))
    n = len(segs)
    out = []
    for idx, (body, punct) in enumerate(segs):
        rate = prof["base_rate_pct"] + emo["rate_pct"]
        pitch = prof["base_pitch_hz"] + emo["pitch_hz"]
        vol = prof["base_volume_pct"] + emo["volume_pct"]
        marks = []

        # ① 尾段上扬：疑问句与萌系句尾都往上挑，并且稍微拖一点
        if idx == n - 1:
            rise = prof.get("end_rise_hz", 0) + emo.get("end_rise_bonus_hz", 0)
            if "？" in punct or "?" in punct:
                rise += 6
                marks.append("疑问上扬")
            pitch += rise
            rate += prof.get("end_rise_rate_pct", 0)
            marks.append("句尾")

        # ② 语气词拖长：呀 / 啦 / 哦 / 呐…… 这些字是萌感的主要承载
        if body and body[-1] in prof.get("particles", []):
            rate += prof.get("particle_rate_pct", 0)
            marks.append(f"语气词「{body[-1]}」拖长")

        # ③ 关键词加重
        hit = [w for w in prof.get("emphasis_words", []) if w in body]
        if hit:
            vol += prof.get("emphasis_volume_pct", 0)
            rate += prof.get("emphasis_rate_pct", 0)
            marks.append("重音：" + "/".join(hit[:2]))

        # ④ 首段起势：开头的感叹/疑问词要有一点冲劲，否则整句像从半截开始
        if idx == 0 and n > 1 and (punct in ("！", "!") or body[:1] in ("哇", "诶", "咦", "欸")):
            pitch += 6
            vol += 4
            marks.append("起势")

        # ⑤ 气口：标点决定停顿长度，情绪再缩放（开心更赶、困倦更拖）
        if idx == n - 1:
            gap = 0
        elif punct:
            gap = int(round(pauses.get(punct, pauses.get(punct[:1], pauses.get("_default", 160)))
                            * emo.get("pause_scale", 1.0)))
            gap = min(gap, max_pause)   # 戏剧停顿的公开区间是 400~700ms，再长就是卡顿不是表演
        else:
            gap = min(int(round(prof.get("breath_ms", 160) * emo.get("pause_scale", 1.0))), max_pause)

        out.append({
            "text": body + (punct if punct not in ("", None) else ""),
            "speak": body,
            "punct": punct,
            "rate_pct": max(-max_rate, min(max_rate, int(round(rate)))),
            "pitch_hz": max(-max_pitch, min(max_pitch, int(round(pitch)))),
            "volume_pct": max(-30, min(30, int(round(vol)))),
            "gap_ms": gap,
            "marks": marks,
        })
    return {"emotion": emotion, "profile": profile_id, "text": text, "segments": out}


# ---------------------------------------------------------------- 各家 payload

def to_edge(sheet: dict) -> list[dict]:
    """edge-tts：每段一次调用（它没有 style，只能这么做），gap_ms 用静音补。"""
    return [{
        "text": s["speak"] + (s["punct"] if s["punct"] else ""),
        "rate": f"{s['rate_pct']:+d}%",
        "pitch": f"{s['pitch_hz']:+d}Hz",
        "volume": f"{s['volume_pct']:+d}%",
        "gap_ms": s["gap_ms"],
    } for s in sheet["segments"]]


def _xml_escape(s: str) -> str:
    return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
             .replace('"', "&quot;"))


def to_ssml(sheet: dict, voice: str, cfg: dict) -> str:
    """Azure 正规通道：mstts:express-as（style + styledegree）+ prosody + break。"""
    emo_id = sheet["emotion"]
    style = cfg.get("style_map", {}).get(emo_id, "")
    degree = cfg["emotions"].get(emo_id, {}).get("style_degree", 1.0)
    body = []
    for s in sheet["segments"]:
        body.append(
            f'<prosody rate="{s["rate_pct"]:+d}%" pitch="{s["pitch_hz"]:+d}Hz" '
            f'volume="{s["volume_pct"]:+d}%">{_xml_escape(s["speak"])}'
            f'{_xml_escape(s["punct"])}</prosody>')
        if s["gap_ms"]:
            body.append(f'<break time="{s["gap_ms"]}ms"/>')
    inner = "".join(body)
    if style:
        inner = (f'<mstts:express-as style="{style}" styledegree="{degree}">'
                 f'{inner}</mstts:express-as>')
    return ('<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" '
            'xmlns:mstts="https://www.w3.org/2001/mstts" xml:lang="zh-CN">'
            f'<voice name="{voice}">{inner}</voice></speak>')


def to_minimax(sheet: dict, cfg: dict) -> dict:
    """MiniMax：整句一个 emotion + speed/pitch/vol（它不吃分段，取各段均值）。"""
    segs = sheet["segments"]
    avg_rate = sum(s["rate_pct"] for s in segs) / max(1, len(segs))
    avg_pitch = sum(s["pitch_hz"] for s in segs) / max(1, len(segs))
    return {
        "emotion": cfg.get("minimax_map", {}).get(sheet["emotion"], "neutral"),
        "speed": round(1.0 + avg_rate / 100.0, 3),
        "pitch": int(round(avg_pitch / 10.0)),       # MiniMax 的 pitch 是 -12~12 的档
        "vol": 1.0,
    }


def sheet_for(line_id: str, text: str, cfg: dict, profile_id: str = "moe_shoujo",
              emotion: str | None = None) -> dict:
    emo, why = (emotion, "调用方指定") if emotion else infer_emotion(line_id, text, cfg)
    sheet = plan_line(text, emo, cfg, profile_id)
    sheet["why"] = why
    sheet["line_id"] = line_id
    return sheet


# ---------------------------------------------------------------- 自检

def selftest(root: str = ".") -> int:
    cfg = load_cfg(root)
    fails: list[str] = []

    def ck(name: str, ok: bool, detail: str = "") -> None:
        print(("  通过  " if ok else "  不通过  ") + name + ("  " + detail if detail else ""))
        if not ok:
            fails.append(name)

    # ① 切段后把字拼回去，必须和原文一致（不许吞字、不许多字）
    cases = ["哇！别敲啦，会痛的！", "摸这么多次…我、我会害羞的啦！",
             "你好呀，我是小寻。今天也一起加油吧！", "再这样我要生气了哦！",
             "咚——！好痛呀，你是想把我敲成扁扁的吗？"]
    ok = True
    for t in cases:
        sheet = plan_line(t, "neutral", cfg)
        got = "".join(s["speak"] + s["punct"] for s in sheet["segments"])
        if got != t.strip():
            ok = False
            print(f"    原文={t!r} 拼回={got!r}")
    ck("切段不吞字（拼回去 == 原文）", ok, f"{len(cases)} 句")

    # ② 同一句，不同情绪必须给出不同参数 —— 这正是用户说「听不出变化」的那条
    base = plan_line("再这样我要生气了哦！", "neutral", cfg)
    diff = 0
    for emo in ("happy", "angry", "sad", "sleepy", "shy"):
        other = plan_line("再这样我要生气了哦！", emo, cfg)
        if [(s["rate_pct"], s["pitch_hz"], s["volume_pct"], s["gap_ms"]) for s in base["segments"]] != \
           [(s["rate_pct"], s["pitch_hz"], s["volume_pct"], s["gap_ms"]) for s in other["segments"]]:
            diff += 1
    ck("五种情绪都和平静不一样", diff == 5, f"{diff}/5")

    # ③ 一句话内部也要有起伏（多段时至少两种参数组合），否则还是念稿
    flat = []
    for t in cases:
        sheet = plan_line(t, "happy", cfg)
        if len(sheet["segments"]) > 1:
            combos = {(s["rate_pct"], s["pitch_hz"], s["volume_pct"]) for s in sheet["segments"]}
            if len(combos) < 2:
                flat.append(t)
    ck("句内有起伏（多段句至少两种参数）", not flat, f"平的：{flat[:2]}" if flat else "")

    # ④ 克制：参数不许越过上限（过度表演＝另一种不像人）
    lim = cfg["_restraint"]
    bad = []
    for emo in cfg["emotions"]:
        for t in cases:
            for s in plan_line(t, emo, cfg)["segments"]:
                if (abs(s["rate_pct"]) > lim["max_abs_rate_pct"]
                        or abs(s["pitch_hz"]) > lim["max_abs_pitch_hz"]
                        or s["gap_ms"] > lim.get("max_pause_ms", 700)):
                    bad.append((emo, s["rate_pct"], s["pitch_hz"], s["gap_ms"]))
    ck("参数都在克制上限内", not bad, f"越界：{bad[:2]}" if bad else
       f"rate≤{lim['max_abs_rate_pct']}% pitch≤{lim['max_abs_pitch_hz']}Hz "
       f"停顿≤{lim.get('max_pause_ms', 700)}ms")

    # ⑤ 情绪判定：几条已知台词必须判对
    expect = [("hammer_1", "哇！别敲啦，会痛的！", "surprised"),
              ("hammer_2", "再这样我要生气了哦！", "angry"),
              ("pat_combo", "摸这么多次…我、我会害羞的啦！", "shy"),
              ("", "好困…我先眯一会儿。", "sleepy")]
    wrong = [(i, t, infer_emotion(i, t, cfg)[0], e) for i, t, e in expect
             if infer_emotion(i, t, cfg)[0] != e]
    ck("已知台词的情绪判对", not wrong, f"判错：{wrong[:2]}" if wrong else f"{len(expect)} 条")

    # ⑥ 负向对照：把情绪表改平，第②条必须红（闸不是空转的）
    import copy
    flatcfg = copy.deepcopy(cfg)
    for k in flatcfg["emotions"]:
        flatcfg["emotions"][k].update({"rate_pct": 0, "pitch_hz": 0, "volume_pct": 0,
                                       "pause_scale": 1.0, "end_rise_bonus_hz": 0})
    same = all(
        [(s["rate_pct"], s["pitch_hz"]) for s in plan_line("再这样我要生气了哦！", "happy", flatcfg)["segments"]]
        == [(s["rate_pct"], s["pitch_hz"]) for s in plan_line("再这样我要生气了哦！", e, flatcfg)["segments"]]
        for e in ("angry", "sad"))
    ck("负向对照：情绪表调平后确实分不出来", same, "闸有效")

    # ⑦ SSML 结构完整
    s = to_ssml(sheet_for("hammer_2", "再这样我要生气了哦，真的会哭给你看！", cfg),
                "zh-CN-XiaoyiNeural", cfg)
    ck("Azure SSML 带 express-as 与 break",
       "mstts:express-as" in s and "<break" in s and s.endswith("</speak>"))

    print(f"\n合计 7 项，{len(fails)} 项不通过 → " + ("全部通过" if not fails else "有问题"))
    return 1 if fails else 0


def main() -> int:
    ap = argparse.ArgumentParser(description="台词 → 演出单（情绪 / 分段 / 停顿 / 重音）")
    ap.add_argument("--root", default=".")
    ap.add_argument("--show", help="要排的台词")
    ap.add_argument("--id", default="", help="台词 id（用于推断情绪）")
    ap.add_argument("--emotion", help="强制指定情绪")
    ap.add_argument("--profile", default="moe_shoujo")
    ap.add_argument("--ssml", action="store_true", help="同时打印 Azure SSML")
    ap.add_argument("--voice", default="zh-CN-XiaoyiNeural")
    ap.add_argument("--json", action="store_true", help="输出 JSON")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()

    if a.selftest:
        return selftest(a.root)
    if not a.show:
        ap.error("要么 --selftest，要么 --show <台词>")

    cfg = load_cfg(a.root)
    sheet = sheet_for(a.id, a.show, cfg, a.profile, a.emotion)
    if a.json:
        print(json.dumps(sheet, ensure_ascii=False, indent=2))
        return 0
    print(f"台词：{a.show}")
    print(f"情绪：{sheet['emotion']}（{sheet['why']}） ｜ 语感档：{sheet['profile']}")
    print(f"{'段':<3}{'文本':<16}{'语速':>6}{'音高':>8}{'音量':>6}{'停顿':>7}  标注")
    for i, s in enumerate(sheet["segments"], 1):
        print(f"{i:<3}{s['text']:<16}{s['rate_pct']:+5d}%{s['pitch_hz']:+7d}Hz"
              f"{s['volume_pct']:+5d}%{s['gap_ms']:>6}ms  {'、'.join(s['marks'])}")
    if a.ssml:
        print("\nSSML：\n" + to_ssml(sheet, a.voice, cfg))
        print("\nMiniMax：" + json.dumps(to_minimax(sheet, cfg), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
