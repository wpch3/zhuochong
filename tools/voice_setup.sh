#!/usr/bin/env bash
# voice_setup.sh - 安装本地中文语音合成环境（沙箱 / Windows 通用）
#
# 1) 建 Python 虚拟环境并安装 piper-tts（自带 espeak-ng，无需系统依赖）
# 2) 下载中文音色模型（Piper VITS，公开音色表，不克隆真人声音）
# 3) 合成一句验证
#
# 用法：bash tools/voice_setup.sh [venv 目录] [模型目录]
set -euo pipefail

VENV="${1:-$HOME/.cache/ttsenv}"
MODELS="${2:-$HOME/.cache/piper-voices}"
REPO="xiongxiongge1/ai_cartoon_person"        # 仓库内直接存放 Piper 中文音色
BASE="static/tts_models/piper"
VOICES="zh_CN-xiao_ya-medium zh_CN-huayan-medium"

echo "== 1/3 安装 piper-tts =="
[ -d "$VENV" ] || python3 -m venv "$VENV"
"$VENV/bin/pip" install -q --upgrade pip
"$VENV/bin/pip" install -q piper-tts==1.8.0 pypinyin unicode-rbnf
echo "   ok: $VENV"

echo "== 2/3 下载音色模型 =="
mkdir -p "$MODELS"
for v in $VOICES; do
  for ext in onnx onnx.json; do
    f="$MODELS/$v.$ext"
    [ -s "$f" ] && { echo "   已存在 $f"; continue; }
    # 优先走 GitHub API（沙箱白名单内），否则走 raw 地址（一般本机可用）
    if command -v gh >/dev/null 2>&1 && gh auth token >/dev/null 2>&1; then
      curl -sL -H "Authorization: Bearer $(gh auth token)" \
        -H "Accept: application/vnd.github.raw" -o "$f" \
        "https://api.github.com/repos/$REPO/contents/$BASE/$v.$ext"
    else
      curl -sL -o "$f" "https://raw.githubusercontent.com/$REPO/main/$BASE/$v.$ext"
    fi
    echo "   $f  ($(wc -c <"$f") 字节)"
  done
done

echo "== 3/3 验证合成 =="
cd "$(dirname "$0")/.."
"$VENV/bin/python" tools/voice_local.py --voice zh_CN-xiao_ya-medium \
  --text "你好呀，我是小寻。" --out /tmp/voice_setup_check.wav
echo "完成。试听：把 characters/xiaoxun/voice/samples/ 用静态服务器打开。"
