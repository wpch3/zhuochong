#!/usr/bin/env bash
# fetch_references.sh - 拉取参考项目源码（用户要求：爬下来做参考，用完删除）
#
# 六个桌宠/Live2D 参考项目 + 用户额外指定的 photocraft（Photoshop 开源移植）。
# 重要：这些代码只用于**查阅学习**，不进入本仓库、不参与编译、不复制进项目。
#       默认克隆到仓库外的缓存目录（可用 REF_DIR 或第一个参数覆盖）。
#
# 用法：bash scripts/fetch_references.sh [目标目录]
# 清理：bash scripts/clean_references.sh [目标目录]
set -eu
DEST="${1:-${REF_DIR:-$HOME/.cache/zc-refs}}"
mkdir -p "$DEST"
cd "$DEST"

clone() {
  name="$1"; url="$2"; note="${3:-}"
  if [ -d "$name/.git" ]; then
    echo "[跳过] $name 已存在（$note）"
    return
  fi
  printf "[克隆] %-18s %s  %s\n" "$name" "$url" "$note"
  git clone --depth 1 -q "$url" "$name" || echo "  [警告] 克隆失败（网络或仓库不可达）"
  du -sh "$name" 2>/dev/null || true
}

echo "参考源码目录：$DEST"
echo "（只查阅，不入库；用完请跑 scripts/clean_references.sh 删除）"
echo
# 交接文件第二节的六个
clone bongocat-sdl    https://github.com/vladelaina/BongoCat        "C+SDL3；AGPL-3.0，只学思路不复制"
clone bongocat-tauri  https://github.com/ayangweb/BongoCat          "Rust；全局输入与动作重叠"
clone ds-local-pet    https://github.com/QCYTSN/ds-local-pet        "MIT；状态机与空闲检测（已移植）"
clone vpet            https://github.com/LorisYounger/VPet          "Apache-2.0；交互语汇"
clone airi            https://github.com/moeru-ai/airi              "MIT；语音四段结构"
clone cubism-web-fw   https://github.com/Live2D/CubismWebFramework  "眨眼状态机；Core 为专有，不引入"
# 用户 2026-10-11 额外指定
clone photocraft      https://github.com/storytold/photocraft        "用户提供；Photoshop 开源移植，做素材精修/图层处理时参考"
echo
echo "完成。查询建议："
echo "  眨眼状态机:  rg -n 'CubismEyeBlink|EyeState' cubism-web-fw/src/effect"
echo "  动作状态机:  sed -n '1,140p' ds-local-pet/animation/state_machine.py"
echo "  空闲检测:    sed -n '1,80p'  ds-local-pet/awareness/idle_detector.py"
echo "  语音流水线:  ls airi/packages | head; ls airi/services 2>/dev/null | head"
echo "  图层/选区:   ls photocraft; rg -n 'layer|selection' photocraft -g '!node_modules' | head"
echo "本项目已整理的结论见 docs/REFERENCE_NOTES.md"
