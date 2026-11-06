#!/usr/bin/env python3
"""tts_probe.py —— 在你自己的电脑上测试中转站的语音合成（TTS）。

只用 Python 标准库，不需要安装任何包。key 只从环境变量读取，脚本不保存也不打印 key。

用法（Windows PowerShell 示例）：
  $env:ZC_RELAY_BASE_URL = "https://api.ohmygpt.com/v1"
  $env:ZC_RELAY_KEY      = "你的新key"
  python tools\\tts_probe.py

可选环境变量：
  ZC_TTS_MODEL   语音模型名，默认 tts-1（会先从 /models 列表里找语音模型供你选）
  ZC_TTS_VOICE   音色名，默认 alloy（具体可用音色以中转站文档为准）
  ZC_TTS_TEXT    要合成的测试文字

输出：
  1. /models 中可能的语音模型列表
  2. 合成请求的 HTTP 状态、返回类型、字节数
  3. 成功时保存为 tts_probe_out.<扩展名>，可直接播放听效果
  4. 若返回的是 JSON（而非音频），打印其字段名，用于判断是否带逐词时间戳

把整段输出（不含 key）发给我即可。
"""
import json
import os
import sys
import urllib.error
import urllib.request

TEXT = os.environ.get("ZC_TTS_TEXT", "你好呀，今天也要好好照顾自己哦。我会一直陪着你的。")
MODEL = os.environ.get("ZC_TTS_MODEL", "tts-1")
VOICE = os.environ.get("ZC_TTS_VOICE", "alloy")
TIMEOUT = 60


def need(name):
    v = os.environ.get(name, "").strip()
    if not v:
        print(f"[缺少] 环境变量 {name} 未设置。请先在本机设置后再运行。")
        sys.exit(1)
    return v


def request(url, key, body=None):
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, method="POST" if body is not None else "GET")
    req.add_header("Authorization", "Bearer " + key)
    if body is not None:
        req.add_header("Content-Type", "application/json")
    return urllib.request.urlopen(req, timeout=TIMEOUT)


def main():
    base = need("ZC_RELAY_BASE_URL").rstrip("/")
    key = need("ZC_RELAY_KEY")
    print(f"[信息] 接口地址：{base}")
    print(f"[信息] 测试模型：{MODEL}，音色：{VOICE}")

    # 1) 列出语音相关模型
    print("\n== 1. 查询模型列表 ==")
    try:
        with request(base + "/models", key) as r:
            data = json.loads(r.read().decode("utf-8", "replace"))
        ids = [m.get("id", "") for m in data.get("data", [])]
        hits = [i for i in ids if any(k in i.lower() for k in ("tts", "speech", "audio", "voice"))]
        print(f"[结果] 模型总数 {len(ids)}，语音相关：{hits if hits else '未找到'}")
    except urllib.error.HTTPError as e:
        print(f"[失败] /models 返回 HTTP {e.code}：{e.reason}")
    except Exception as e:
        print(f"[失败] 无法访问 /models：{type(e).__name__}: {e}")

    # 2) 合成一句话
    print("\n== 2. 语音合成请求 ==")
    body = {"model": MODEL, "input": TEXT, "voice": VOICE, "response_format": "mp3"}
    try:
        with request(base + "/audio/speech", key, body) as r:
            ctype = r.headers.get("Content-Type", "")
            raw = r.read()
        print(f"[结果] HTTP 200，Content-Type={ctype}，字节数={len(raw)}")
        if ctype.startswith("audio/") or ctype == "application/octet-stream":
            out = "tts_probe_out.mp3"
            with open(out, "wb") as f:
                f.write(raw)
            print(f"[成功] 音频已保存为 {out}，请播放听效果。")
        else:
            try:
                js = json.loads(raw.decode("utf-8", "replace"))
                print("[注意] 返回的是 JSON，不是音频。顶层字段：", list(js.keys()))
                print("       若含 timestamps / alignment / words 字段，说明支持逐词时间戳。")
            except Exception:
                print("[注意] 返回既不是音频也不是 JSON，前 200 字节：", raw[:200])
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")[:300]
        print(f"[失败] HTTP {e.code}：{e.reason}")
        print("       返回内容（前 300 字符，已去掉可能的 key）：", detail)
    except Exception as e:
        print(f"[失败] 请求异常：{type(e).__name__}: {e}")


if __name__ == "__main__":
    main()
