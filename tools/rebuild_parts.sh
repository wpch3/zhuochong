#!/usr/bin/env bash
# rebuild_parts.sh - 从设计图把所有零件重新切一遍（顺序不能换）
#
# 为什么要有这个脚本：
#   make_body_parts.py 会重新生成 seg_head.png / seg_torso.png 和 body_parts.json，
#   把后面几步补进去的东西（手臂拆件挖掉的袖子、呆毛切口、AI 重绘的额头、
#   拆走的眉毛）全部冲掉。
#   所以只要动了身体分段，后面几步必须按这个顺序重跑一遍。
#
#   新步骤插在哪：只要不改 seg_* 的工具，排在「高清化」之前都行 ——
#   高清化那步会给每个 1× 件配一张 @2x，漏在它后面的新件就没有高清版，
#   selfcheck 的「高清切件全量启用」会判红。
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

step "1/25 身体分段（头/躯干/双臂/双腿）"
"$PY" tools/make_body_parts.py --character "$CH" --form "$FM"

step "2/25 手臂四件（上臂/前臂 × 左右，袖下躯干用 AI 重绘补齐）"
"$PY" tools/make_arm_parts.py --character "$CH" --form "$FM"

step "3/25 鞋拆件（常态鞋 + 踮脚鞋，顺带把腿件切线以下擦干净）"
"$PY" tools/make_foot_parts.py --character "$CH" --form "$FM"

step "4/25 眼部四件（眼眶/眼白/眼球/眼线）"
"$PY" tools/make_eye_parts.py --character "$CH" --form "$FM"

step "5/25 嘴三件（量嘴线 + 先铺一版几何口内兜底）"
"$PY" tools/make_mouth_parts.py --character "$CH" --form "$FM"

step "6/25 张嘴真素材（AI 重绘张嘴脸 → 虹膜配准 → 取口内）"
"$PY" tools/make_mouth_open_parts.py --character "$CH" --form "$FM"

step "7/25 呆毛（无损切出）"
"$PY" tools/make_hair_parts.py --character "$CH" --form "$FM"

step "8/25 刘海 + 额头（AI 重绘回贴）"
"$PY" tools/make_bangs_parts.py --character "$CH" --form "$FM" \
      --redraw characters/xiaoxun/design/redraw/head_nobangs.png

step "9/25 眉毛（AI 重绘 + alpha 抠像）"
"$PY" tools/make_brow_parts.py --character "$CH" --form "$FM" \
      --redraw characters/xiaoxun/design/redraw/head_nobrows.png

step "10/25 闭眼真素材（AI 重绘闭眼脸 → 脸部 NCC 配准 → 切补片）"
"$PY" tools/make_eye_closed_parts.py --character "$CH" --form "$FM"

step "11/25 笑眼真素材（同一条流水线，底图换成山型 ∩ 的笑眼脸）"
"$PY" tools/make_eye_closed_parts.py --character "$CH" --form "$FM" --variant smile

step "12/25 痛苦闭眼 >_< 与真·瞪大眼（同一条流水线的第三、第四张重绘底图）"
"$PY" tools/make_eye_closed_parts.py --character "$CH" --form "$FM" --variant pain
"$PY" tools/make_eye_closed_parts.py --character "$CH" --form "$FM" --variant wide

step "13/25 上眼睑（没有闭眼真素材时的兜底方案）"
"$PY" tools/make_eyelid_parts.py --character "$CH" --form "$FM"

step "14/25 混合模式零件（腮红·乘算 / 眼高光·加算，程序化画出来的）"
"$PY" tools/make_blend_parts.py --character "$CH" --form "$FM"

step "15/25 侧发两缕 + 后发（AI 重绘无侧发的脸 → 虹膜配准 → 挖发补脸）"
"$PY" tools/make_sidehair_parts.py --character "$CH" --form "$FM" \
      --redraw characters/xiaoxun/design/redraw/head_nosidehair.png

step "16/25 头皮塗り足し（seg_head 是张光头：抹掉人耳 / 鬓发翼换发色 / 颅顶铺发基色）"
# ⚠ 必须排在 14 步**之后**：那一步挖走鬓发才会在 seg_head 上留下「只在被盖住时
#   才成立」的肤色翼。也必须排在 15/16 步**之前**（它们同样改 seg_head）。
#   Live2D 官方 PSD 教程：元画で隠れていた部分の描き足しを忘れずに。
#   不补画就收鬓发 = 第九问被打回的「人耳裸露在脸颊」。
"$PY" tools/make_scalp_patch.py --character "$CH" --form "$FM"

step "17/25 眼线二次拆件（最后跑：脸上那只睁眼挖成眼窝皮肤，必须排在所有改 seg_head 的工具之后）"
"$PY" tools/make_eyeline_parts.py --character "$CH" --form "$FM"

step "18/25 闭合笑线剪切（把笑线从 seg_head 上剪下来，必须排在所有改 seg_head 的工具之后）"
"$PY" tools/make_mouth_line_cut.py --character "$CH" --form "$FM"

step "19/25 擦掉烘进别的部件里的残留（眼部差分件里的侧发 / 躯干肩上的鲍勃发梢 / 头件下缘的烂衣领）"
# ⚠ 必须排在所有改 seg_head / seg_torso / eye_* 的工具**之后**、高清化**之前**：
#   后者由 1× 生成 @2x，放在它前面擦，两个分辨率天然一致（自己在 @2x 上再跑一遍
#   同样的阈值会得到**不同**的结果 —— 2026-10-18 实测，抗锯齿过渡带宽一倍）。
"$PY" tools/clean_baked_residue.py --character "$CH" --form "$FM" | tail -4

step "20/25 切件高清化（每个件生成 2× 的 @2x，make_rig 会自动改用并把 scale 乘 0.5）"
# 先空跑一遍 make_rig 刷新「rig 引用了哪些件」这张表：高清化只给引用到的件做 @2x，
# 而它读的是上一次的 rig.json。上一步新增了部件时不刷新，新件就会漏掉 @2x
# （2026-10-15 加 arm_*_root 时实测漏了 2 个，被 selfcheck 的「全量启用」闸抓到）。
python3 tools/make_rig.py --character "$CH" --form "$FM" >/dev/null
"$PY" tools/make_hires_sprites.py --character "$CH" --form "$FM"

step "21/25 星星眼差分件（星形虹膜 + ✨ 素材，AI 源图抠像；整组可选）"
# ⚠ 必须排在高清化**之后**（2026-10-16 用户打回第一版之后改的顺序）：
# 星形件不再自己配色，而是拿**常态虹膜那张贴图**当底、只把星形区域点亮，
# 所以 1× 要用 eye_?_ball.png、2× 要用 eye_?_ball@2x.png —— 后者是上一步的产物。
# 这样星以外的像素和常态件逐像素相同，切换时不会变色也不会变锐度。
"$PY" tools/make_star_eye_parts.py --character "$CH" --form "$FM"
"$PY" tools/make_manpu_parts.py --character "$CH" --form "$FM"

step "22/25 兜帽整形（按头部实测几何把画出来的兜帽削到该有的厚度 + 算放置参数）"
"$PY" tools/make_hood_part.py --character "$CH" --form "$FM" \
  --source acc_hood_cute_v6.png
"$PY" tools/make_attach_parts.py --character "$CH" --form "$FM"
"$PY" tools/make_wardrobe.py --character "$CH" --form "$FM"

step "23/25 外套前襟下摆的几何（量出哪几列是前襟、哪几行是下摆，给 make_rig 定网格）"
"$PY" tools/make_jacket_parts.py --character "$CH" --form "$FM"

step "24/25 裙子里布（从躯干件上复制裙摆 → 压暗当裏地；@2x 同掩码原样切）"
# ⚠ 必须排在高清化（20 步）**之后**：里布的 @2x 不走超分，而是把 1× 的掩码放大两倍
# 再从 seg_torso@2x.png 上切 —— 那张图是上一步的产物。顺序反了就只有 1× 没有 @2x。
"$PY" tools/make_skirt_parts.py --character "$CH" --form "$FM"

step "25/25 生成 rig 并验收"
python3 tools/make_rig.py --character "$CH" --form "$FM"
"$PY" tools/check_assets.py --character "$CH" --form "$FM" | tail -3
rm -rf tools/__pycache__
echo
echo "全部零件已重建。重开预览才会生效：先 stop 再 ./build/zhuochong_preview --port 5173 --root ."
