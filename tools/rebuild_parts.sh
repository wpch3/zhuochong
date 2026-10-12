#!/usr/bin/env bash
# rebuild_parts.sh - 从设计图把所有零件重新切一遍（顺序不能换）
#
# 为什么要有这个脚本：
#   make_body_parts.py 会重新生成 seg_head.png / seg_torso.png 和 body_parts.json，
#   把后面几步补进去的东西（手臂拆件挖掉的袖子、呆毛切口、AI 重绘的额头、
#   拆走的眉毛）全部冲掉。
#   所以只要动了身体分段，后面几步必须按这个顺序重跑一遍。
#
# 用法：bash tools/rebuild_parts.sh [角色] [形态]
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
CH="${1:-xiaoxun}"
FM="${2:-teen}"
PY=""
for cand in "${ZC_PYTHON:-}" "$HOME/.imgenv/bin/python" python3; do
  [ -n "$cand" ] || continue
  if "$cand" -c "import PIL, numpy" >/dev/null 2>&1; then PY="$cand"; break; fi
done
[ -n "$PY" ] || { echo "找不到带 pillow+numpy 的 python（装：python3 -m venv ~/.imgenv && ~/.imgenv/bin/pip install pillow numpy）"; exit 1; }

step() { printf "\n=== %s ===\n" "$1"; }

step "1/13 身体分段（头/躯干/双臂/双腿）"
"$PY" tools/make_body_parts.py --character "$CH" --form "$FM"

step "2/13 手臂四件（上臂/前臂 × 左右，袖下躯干用 AI 重绘补齐）"
"$PY" tools/make_arm_parts.py --character "$CH" --form "$FM"

step "3/13 眼部四件（眼眶/眼白/眼球/眼线）"
"$PY" tools/make_eye_parts.py --character "$CH" --form "$FM"

step "4/13 嘴三件（量嘴线 + 先铺一版几何口内兜底）"
"$PY" tools/make_mouth_parts.py --character "$CH" --form "$FM"

step "5/13 张嘴真素材（AI 重绘张嘴脸 → 虹膜配准 → 取口内）"
"$PY" tools/make_mouth_open_parts.py --character "$CH" --form "$FM"

step "6/13 呆毛（无损切出）"
"$PY" tools/make_hair_parts.py --character "$CH" --form "$FM"

step "7/13 刘海 + 额头（AI 重绘回贴）"
"$PY" tools/make_bangs_parts.py --character "$CH" --form "$FM" \
      --redraw characters/xiaoxun/design/redraw/head_nobangs.png

step "8/13 眉毛（AI 重绘 + alpha 抠像）"
"$PY" tools/make_brow_parts.py --character "$CH" --form "$FM" \
      --redraw characters/xiaoxun/design/redraw/head_nobrows.png

step "9/13 闭眼真素材（AI 重绘闭眼脸 → 脸部 NCC 配准 → 切补片）"
"$PY" tools/make_eye_closed_parts.py --character "$CH" --form "$FM"

step "10/13 上眼睑（没有闭眼真素材时的兜底方案）"
"$PY" tools/make_eyelid_parts.py --character "$CH" --form "$FM"

step "11/13 混合模式零件（腮红·乘算 / 眼高光·加算，程序化画出来的）"
"$PY" tools/make_blend_parts.py --character "$CH" --form "$FM"

step "12/13 侧发两缕 + 后发（AI 重绘无侧发的脸 → 虹膜配准 → 挖发补脸）"
"$PY" tools/make_sidehair_parts.py --character "$CH" --form "$FM" \
      --redraw characters/xiaoxun/design/redraw/head_nosidehair.png

step "13/13 生成 rig 并验收"
python3 tools/make_rig.py --character "$CH" --form "$FM"
"$PY" tools/check_assets.py --character "$CH" --form "$FM" | tail -3
rm -rf tools/__pycache__
echo
echo "全部零件已重建。重开预览才会生效：先 stop 再 ./build/zhuochong_preview --port 5173 --root ."
