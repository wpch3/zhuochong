#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""voice_cloud.py — 云端 TTS 客户端（Azure 语音 / MiniMax），只用标准库。

为什么要有这一层：`voice_render.py` 原来只会 edge-tts，而 edge-tts **没有情绪风格**，
只有语速/音高（REFERENCE_NOTES 第四十二批）。用户要的"情绪听得出来 + 音色更萌"，
在 edge 这条通道上已经顶到天花板了。Azure 的 `mstts:express-as`（cute / shy / …）
和 MiniMax 的 `emotion` 字段才是真能换情绪的两条路。

密钥规矩（和网关同一套，`zgateway.c::zgw_secret`）：
    secret://azure_speech  →  环境变量 ZHUOCHONG_SECRET_AZURE_SPEECH
    secret://minimax       →  环境变量 ZHUOCHONG_SECRET_MINIMAX
**密钥只从环境变量读，永远不写进仓库、不打印、不记日志。**
这个脚本任何时候打印的都只有"指纹"（长度 + 首尾两字 + SHA256 前 8 位），
拿指纹可以核对"我用的是不是你给的那把", 但反推不出密钥。

用法（本机或 GitHub Actions 上跑；Arena 沙箱出网到不了这两家）：
    python3 tools/voice_cloud.py --check                 # 两家都体检：密钥在不在、通不通
    python3 tools/voice_cloud.py --check --provider azure
    python3 tools/voice_cloud.py --say "你回来啦，我等你好久了" --provider azure --style cute
    python3 tools/voice_cloud.py --say "哼，不理你了" --provider minimax --emotion angry
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import urllib.error
import urllib.request
from xml.sax.saxutils import escape

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 和 edge-tts 对齐的输出格式：24kHz / mono / mp3。
# 对齐不是洁癖 —— `voice_render.py` 会把分段的 mp3 拼成一条，
# 没有 ffmpeg 时走二进制拼接，编码参数不一样就会在接缝处咔哒。
AZURE_FORMAT = "audio-24khz-48kbitrate-mono-mp3"
TIMEOUT = 30


# ------------------------------------------------------------------ 密钥

def key_ref_to_env(ref: str) -> str:
    """secret://azure_speech → ZHUOCHONG_SECRET_AZURE_SPEECH（和 C 网关同一规则）。"""
    name = ref[len("secret://"):] if ref.startswith("secret://") else ref
    return "ZHUOCHONG_SECRET_" + name.upper().replace("-", "_")


def fingerprint(key: str) -> str:
    """能核对、反推不出来的指纹。**任何输出里只许出现它，不许出现 key 本身。**"""
    if not key:
        return "（空）"
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()[:8]
    head = key[:2] if len(key) > 8 else "?"
    tail = key[-2:] if len(key) > 8 else "?"
    return "%d 位 / %s…%s / sha256:%s" % (len(key), head, tail, digest)


def get_key(env_name: str) -> str:
    return (os.environ.get(env_name) or "").strip()


def load_provider(pid: str) -> dict:
    p = os.path.join(ROOT, "config", "providers", "%s.json" % pid)
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def load_emotions() -> dict:
    p = os.path.join(ROOT, "config", "emotion_map.json")
    try:
        with open(p, encoding="utf-8") as f:
            return (json.load(f) or {}).get("emotions", {})
    except OSError:
        return {}


# ------------------------------------------------------------------ Azure

def azure_ssml(text: str, voice: str, style: str = "", degree: float = 1.0,
               rate: str = "+0%", pitch: str = "+0Hz", volume: str = "+0%",
               lang: str = "zh-CN") -> str:
    """拼 SSML。

    ★ 踩过的坑写在这里（REFERENCE_NOTES 第四十二批）：
      · `style` 写了个这个音色不支持的值，Azure **不会报错**，而是整个
        `mstts:express-as` 元素被忽略、退回中性 —— 听起来就是"情绪没生效"。
        所以 `--check` 里会把音色支持的 style 列出来，别凭记忆写。
      · `styledegree` 合法区间 0.01~2，超了同样静默退回。
    """
    inner = escape(text)
    inner = ('<prosody rate="%s" pitch="%s" volume="%s">%s</prosody>'
             % (rate, pitch, volume, inner))
    if style:
        deg = max(0.01, min(2.0, float(degree)))
        inner = ('<mstts:express-as style="%s" styledegree="%.2f">%s</mstts:express-as>'
                 % (escape(style, {'"': "&quot;"}), deg, inner))
    return ('<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" '
            'xmlns:mstts="https://www.w3.org/2001/mstts" xml:lang="%s">'
            '<voice name="%s">%s</voice></speak>' % (lang, voice, inner))


def azure_endpoint(region: str) -> str:
    # ★ 门户里那个 *.api.cognitive.microsoft.com 不是 TTS 端点，拿它发请求会 404。
    return "https://%s.tts.speech.microsoft.com/cognitiveservices/v1" % region


def synth_azure(text: str, voice: str, style: str = "", degree: float = 1.0,
                rate: str = "+0%", pitch: str = "+0Hz", volume: str = "+0%",
                region: str = "", key: str = "") -> bytes:
    region = region or os.environ.get("ZHUOCHONG_AZURE_REGION", "southeastasia")
    key = key or get_key("ZHUOCHONG_SECRET_AZURE_SPEECH")
    if not key:
        raise RuntimeError("没有 ZHUOCHONG_SECRET_AZURE_SPEECH，先设环境变量（见 docs/ops/VOICE_KEYS.md）")
    body = azure_ssml(text, voice, style, degree, rate, pitch, volume).encode("utf-8")
    req = urllib.request.Request(azure_endpoint(region), data=body, method="POST", headers={
        "Ocp-Apim-Subscription-Key": key,
        "Content-Type": "application/ssml+xml",
        "X-Microsoft-OutputFormat": AZURE_FORMAT,
        "User-Agent": "zhuochong-voice",
    })
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        return resp.read()


# ------------------------------------------------------------------ MiniMax

def synth_minimax(text: str, voice_id: str, emotion: str = "",
                  speed: float = 1.0, pitch: int = 0, vol: float = 1.0,
                  model: str = "speech-2.8-hd", key: str = "", group: str = "") -> bytes:
    """MiniMax t2a_v2。

    ★ 两个坑：
      · 返回体里的 `data.audio` 是 **hex 字符串**，不是 base64（拿 base64 解会炸）。
      · 国内站 api.minimaxi.com 与海外站 api.minimax.io **账号/Key/余额都不互通**，
        Key 配错站点会 401，但错误信息看着像"密钥无效"。
    """
    key = key or get_key("ZHUOCHONG_SECRET_MINIMAX")
    group = group or get_key("ZHUOCHONG_SECRET_MINIMAX_GROUP")
    if not key:
        raise RuntimeError("没有 ZHUOCHONG_SECRET_MINIMAX，先设环境变量（见 docs/ops/VOICE_KEYS.md）")
    base = load_provider("minimax").get("base_url", "https://api.minimaxi.com/v1")
    url = base.rstrip("/") + "/t2a_v2"
    if group:
        url += "?GroupId=" + group
    vs = {"voice_id": voice_id, "speed": speed, "vol": vol, "pitch": pitch}
    if emotion:
        vs["emotion"] = emotion
    payload = {
        "model": model,
        "text": text,
        "stream": False,
        "voice_setting": vs,
        # 和 edge-tts / Azure 对齐，拼接才不会咔哒
        "audio_setting": {"sample_rate": 24000, "bitrate": 48000, "format": "mp3", "channel": 1},
    }
    req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"),
                                 method="POST", headers={
        "Authorization": "Bearer " + key,
        "Content-Type": "application/json",
    })
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        doc = json.loads(resp.read().decode("utf-8"))
    base_resp = doc.get("base_resp") or {}
    if base_resp.get("status_code") not in (0, None):
        raise RuntimeError("MiniMax 返回错误 %s：%s"
                           % (base_resp.get("status_code"), base_resp.get("status_msg")))
    hexs = ((doc.get("data") or {}).get("audio") or "")
    if not hexs:
        raise RuntimeError("MiniMax 没返回音频（data.audio 为空）")
    return bytes.fromhex(hexs)


# ------------------------------------------------------------------ 体检

def check_one(pid: str, do_net: bool, text: str) -> bool:
    """一家的体检：密钥在不在 → 形状对不对 → 真发一次请求。

    判据是**真合成出 >1KB 的音频**，不是"端点返回 200"。
    这条是 G65 那个教训的同款：接口回 ok 不等于功能生效。
    """
    prov = load_provider(pid)
    env = key_ref_to_env((prov.get("auth") or {}).get("key_ref", ""))
    key = get_key(env)
    ok = True
    print("── %s（%s）" % (prov.get("name", pid), pid))
    print("   密钥环境变量：%s" % env)
    if not key:
        print("   ✗ 没读到。本机先 export，或在 GitHub 仓库 Settings → Secrets 里加同名 secret")
        return False
    print("   ✓ 读到了：%s" % fingerprint(key))
    # 形状体检：Azure 的 key 是 32 位十六进制；MiniMax 是 JWT（三段点分）
    if pid == "azure_speech":
        if len(key) < 30 or any(c not in "0123456789abcdefABCDEF" for c in key):
            print("   ⚠ 形状不像 Azure 语音密钥（通常是 32 位十六进制）——"
                  "别把「终结点 URL」或「资源 ID」当成密钥贴进来了")
            ok = False
        region = os.environ.get("ZHUOCHONG_AZURE_REGION", "southeastasia")
        print("   区域：%s（香港用户建议 southeastasia；HD 档只在部分区域有）" % region)
        print("   端点：%s" % azure_endpoint(region))
    else:
        if key.count(".") != 2:
            print("   ⚠ 形状不像 MiniMax 的 API Key（通常是三段点分的 JWT）")
            ok = False
        if not get_key("ZHUOCHONG_SECRET_MINIMAX_GROUP"):
            print("   · 没设 ZHUOCHONG_SECRET_MINIMAX_GROUP（GroupId）。"
                  "多数账号必须带 GroupId，不带会 401 —— 在控制台和 Key 同一页能看到")
        print("   端点：%s/t2a_v2（国内站；海外账号要把 minimaxi.com 换成 minimax.io）"
              % load_provider("minimax").get("base_url"))
    if not do_net:
        print("   （跳过联网试打；加 --net 才真发一次请求）")
        return ok
    try:
        if pid == "azure_speech":
            audio = synth_azure(text, voice="zh-CN-XiaoyiNeural", style="cute")
        else:
            audio = synth_minimax(text, voice_id="female-shaonv", emotion="happy")
        print("   ✓ 真合成成功：%d 字节" % len(audio))
        if len(audio) < 1024:
            print("   ✗ 但音频太小（<1KB），多半是参数被静默忽略了")
            ok = False
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            detail = exc.read().decode("utf-8", "ignore")[:200]
        except Exception:  # noqa: BLE001
            pass
        print("   ✗ HTTP %s %s  %s" % (exc.code, exc.reason, detail))
        if exc.code in (401, 403):
            print("     → 密钥或区域/站点不对（Azure 看区域，MiniMax 看国内/海外站与 GroupId）")
        ok = False
    except Exception as exc:  # noqa: BLE001
        print("   ✗ %s: %s" % (type(exc).__name__, exc))
        ok = False
    return ok


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="体检：密钥在不在、形状对不对")
    ap.add_argument("--net", action="store_true", help="体检时真发一次合成请求（沙箱里到不了）")
    ap.add_argument("--provider", choices=["all", "azure", "minimax"], default="all")
    ap.add_argument("--say", default="", help="合成一句话")
    ap.add_argument("--out", default="/tmp/voice_cloud_test.mp3")
    ap.add_argument("--voice", default="", help="Azure 音色名 / MiniMax voice_id")
    ap.add_argument("--style", default="", help="Azure 的 express-as style（如 cute / shy）")
    ap.add_argument("--degree", type=float, default=1.0, help="styledegree 0.01~2")
    ap.add_argument("--emotion", default="", help="MiniMax 的 emotion，或桌宠情绪名（会查表换算）")
    ap.add_argument("--rate", default="+0%")
    ap.add_argument("--pitch", default="+0Hz")
    args = ap.parse_args()

    if args.check or not args.say:
        pids = (["azure_speech", "minimax"] if args.provider == "all"
                else ["azure_speech" if args.provider == "azure" else "minimax"])
        allok = True
        for pid in pids:
            allok = check_one(pid, args.net, "小寻在这儿哦") and allok
            print("")
        print("体检结果：%s" % ("两家都就绪" if allok else "有问题，照上面的提示修"))
        return 0 if allok else 1

    # 桌宠情绪名 → 各家的表达方式（config/emotion_map.json 已经有这张表）
    emo = load_emotions().get(args.emotion, {})
    if args.provider == "minimax":
        voice = args.voice or "female-shaonv"
        emotion = emo.get("minimax", args.emotion)
        audio = synth_minimax(args.say, voice, emotion=emotion)
    else:
        voice = args.voice or "zh-CN-XiaoyiNeural"
        style = args.style or emo.get("style", "")
        audio = synth_azure(args.say, voice, style=style, degree=args.degree,
                            rate=args.rate, pitch=args.pitch)
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "wb") as f:
        f.write(audio)
    print("写出 %s（%d 字节）" % (args.out, len(audio)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
