#!/usr/bin/env bash
# fetch_references.sh - 拉取六个参考项目的源码，供“遇到问题先查源码”使用。
#
# 重要：这些代码只用于**查阅学习**，不进入本仓库、不参与编译。
#       默认克隆到仓库外的缓存目录（可用 REF_DIR 覆盖），AGPL 项目尤其只能看思路。
#
# 用法：bash scripts/fetch_references.sh [目标目录]
set -eu
DEST="${1:-${REF_DIR:-$HOME/.cache/zc-refs}}"
mkdir -p "$DEST"
cd "$DEST"

clone() {
  name="$1"; url="$2"; branch="${3:-}"
  if [ -d "$name/.git" ]; then
    echo "[跳过] $name 已存在"
    return
  fi
  echo "[克隆] $name <- $url"
  if [ -n "$branch" ]; then
    git clone --depth 1 -b "$branch" -q "$url" "$name"
  else
    git clone --depth 1 -q "$url" "$name"
  fi
  du -sh "$name" 2>/dev/null || true
}

echo "参考目录：$DEST"
clone bongocat-sdl      https://github.com/vladelaina/BongoCat                 # AGPL-3.0 只学思路
clone bongocat-tauri    https://github.com/ayangweb/BongoCat                   # Apache-2.0
clone ds-local-pet      https://github.com/QCYTSN/ds-local-pet                 # MIT
clone vpet              https://github.com/LorisYounger/VPet                  # Apache-2.0
clone airi              https://github.com/moeru-ai/airi                       # MIT
clone cubism-web-fw     https://github.com/Live2D/CubismWebFramework           # 框架源码许可；Core 为专有，不引入
echo
echo "完成。查询建议："
echo "  眨眼:        rg -n 'CubismEyeBlink|EyeState' cubism-web-fw/src/effect"
echo "  状态机:      sed -n '1,140p' ds-local-pet/animation/state_machine.py"
echo "  空闲检测:    sed -n '1,80p'  ds-local-pet/awareness/idle_detector.py"
echo "  语音:        ls airi/packages/stage-* airi/services 2>/dev/null || ls airi"
echo "本项目对照结论见 docs/REFERENCE_NOTES.md"
