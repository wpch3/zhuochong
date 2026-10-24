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

# ── 美术来源（形态级）────────────────────────────────────────────────
# 直到 2026-10-24，这条链的第 1 步写死少女那张设计图、9/10/16 步写死少女那些
# 重绘底图。于是「给另一个形态跑一遍」只能手工敲命令，而三个工具
# （make_eye_closed_parts / make_mouth_open_parts / make_arm_parts）里
# 重绘路径是硬编码的 ⇒ 必然读到少女的脸。
# 现在统一走 tools/form_art.py：有 forms/<形态>/design/form_art.json 就按它，
# 没有就退回少女那套（teen 产物逐字段不变，已实测）。
SHEET_REL="$("$PY" tools/form_art.py --root . --character "$CH" --form "$FM" --sheet)"
echo "美术来源：$SHEET_REL"
rd() {  # rd <逻辑名> [回退值]：解析重绘底图，找不到就用回退（保持旧脚本行为）
  local got
  got="$("$PY" tools/form_art.py --root . --character "$CH" --form "$FM" --redraw "$1" 2>/dev/null)" || got=""
  [ -n "$got" ] || got="${2:-}"
  echo "$got"
}

# rd_opt <逻辑名>：**形态级表说了算**的写法。
#   形态有 design/form_art.json 却没写这个键 → 返回空（调用方跳过这一步）；
#   形态根本没有表（teen）→ 退回角色级旧路径，行为不变。
#   为什么需要：Q 版没有 head_nobrows 的重绘底图，rd() 的回退会拿**少女那张**去抠眉毛，
#   结果是"少女的眉毛长在 Q 版脸上"—— 这正是 T2.2.5 那类跨形态污染。
#   Q 版原画里眉毛是烘在 seg_head 上的（rig 里没有 brow 件），跳过这一步是对的。
rd_opt() {
  local table got
  table="$ROOT/characters/$CH/forms/$FM/design/form_art.json"
  got="$("$PY" tools/form_art.py --root . --character "$CH" --form "$FM" --redraw "$1" 2>/dev/null)" || got=""
  if [ -f "$table" ]; then
    "$PY" - "$table" "$1" <<'PYEOF' || got=""
import json,sys
t=json.load(open(sys.argv[1],encoding='utf-8'))
sys.exit(0 if sys.argv[2] in (t.get("redraw") or {}) else 1)
PYEOF
  fi
  echo "$got"
}

step "1/26 从设计图抠像出 body_full.png（整条流水线的源头）"
# ⚠ 2026-10-21 之前这一步**不在**脚本里，body_full.png 只在最早手跑过一次，
#   于是抠像本身的缺陷（剪影上的描边被吃掉、边缘一圈近白 matte）在仓库里
#   冻了很久，后面 24 步只是忠实地把它往下传 —— 第三十二问的"没有描边"就是它。
#   现在挂进来，改抠像判据能一条链跑到底。
# 几何锁：裁框/缩放写死在 design/body_fit.json，不让 bbox 自然漂移 ——
#   漂一个像素，下游 17 个 JSON 上百个手调坐标全废。
"$PY" tools/prepare_sprites.py --character "$CH" --form "$FM" \
  --sheet "$SHEET_REL"

step "2/26 身体分段（头/躯干/双臂/双腿）"
"$PY" tools/make_body_parts.py --character "$CH" --form "$FM"
# ★ 这一步刚把 seg_torso 重新生成了一遍，sprites/_orig/ 里那几张「原件备份」
#   就过期了。后面 20c/20d 两步是**原地覆盖 seg_torso** 的工具，它们的约定是
#   「永远从 _orig/ 的备份重算」—— 备份不作废，这一轮上游的改动会被整张旧图盖掉
#   （2026-10-22 第四十六问踩到：补腋下时差点把上游重切的躯干还原回去）。
rm -f "characters/$CH/forms/$FM/sprites/_orig/seg_torso"*.png
# 同理：split_torso_top.py 有**自己**的备份目录（覆盖型工具不许共用别人的 _orig/，
# 2026-10-20 的教训），这一轮躯干重切了，它那份备份也必须作废。
rm -rf "characters/$CH/forms/$FM/sprites/_orig/split_torso_top"

step "3/26 手臂四件（上臂/前臂 × 左右，袖下躯干用 AI 重绘补齐）"
"$PY" tools/make_arm_parts.py --character "$CH" --form "$FM"

step "3a/26 袖子塗り足し（把被白夹克盖掉的那半条上臂补回袖根件）"
# 必须排在 make_arm_parts 之后、正圆关节之前（它要按"幸存料"算内缘）。
# 第四十四问：用户「手臂为什么会挥手就变细」。原画里手臂垂着、白夹克身压在青袖子上，
# 被盖住的那半条袖子**在图上根本不存在**，切件照"看得见的青色"切 ⇒ 上臂中段只有
# 51~58px，比前臂（64~80px）还细。Live2D 的标准答案是塗り足し + 放在遮挡者下面的图层。
"$PY" tools/sleeve_underlay.py --character "$CH" --form "$FM"

step "3b/26 正圆关节（肩球 + 肘圆：把关节那一圈做成绕枢轴旋转不变的圆）"
# 必须排在 make_arm_parts 之后、make_rig 之前。第四十一/四十二问连着栽在这：
# 上臂顶端是一刀平切、还高出肩枢轴 63px，一转就扫到胸口；肩帽是不转的扇形，
# 一转就被落在剪影外面；压到躯干底下躲开 ⇒ 肩头直接塌进去。
# 正解是 Live2D 官方那条「関節パーツは腕幅と同じ直径の正円、枢轴＝その中心」。
"$PY" tools/round_arm_sockets.py --character "$CH" --form "$FM"

step "3c/26 手差分件（放松/张开/比心 × 左右，程序化重画）"
# 必须排在 make_arm_parts 之后：腕线、袖口内宽都是从它的产物上实测的。
# 原画那只手是\"摊平的蹼\"（五指等长、没有掌骨），掰是掰不出来的，只能重画；
# 官方口径也是手的差分**换贴图**而不是靠变形器（animator_arms_mtn）。
"$PY" tools/make_hand_parts.py --character "$CH" --form "$FM"

step "3d/26 腕正圆关节（把袖口里的垫片做成以腕枢轴为心的正圆）"
# 必须排在 make_hand_parts 之后：它要读 hand_*_pad 和袖口的实际几何。
# 第四十四问第二处：垫片在袖口以下还留着一截非圆形的料，手一摆就从袖口下面
# 探出一块肉色疙瘩（logs/asset_qa/q44_wrist_before.png）。官方口径「関節パーツは正円」。
"$PY" tools/round_wrist_socket.py --character "$CH" --form "$FM"

step "3e/26 腕半圆塗り足し（手件在腕口补一枚以枢轴为心的正圆）"
# 必须排在 round_wrist_socket 之后：R 取的是同一条「袖口半宽」。
# 第四十六问：张开手的腕桩只有 24px 宽，袖口洞 43px —— 手腕一摆就漏背景
# （logs/asset_qa/q46_tint_junction.png 黄绿之间的洋红）。
"$PY" tools/wrist_bridge.py --character "$CH" --form "$FM"

step "3f/26 裁袖口肉桩（袖管末端那块不跟手转的方料，手一摆就从剪影外探出来）"
# 必须排在最后：它要读**最终**的手件剪影（已含 3e 补的腕半圆）算「手转遍
# 工作区间后永远盖得住」的安全区，再拿它去裁袖管自带的肉色塗り足し。
# 上游 3/26 刚重做过 arm_*_fore，旧备份作废，先删掉（同 seg_torso 的口径）。
rm -f "characters/$CH/forms/$FM/sprites/_orig/arm_l_fore"*.png \
      "characters/$CH/forms/$FM/sprites/_orig/tab_hand_l_pad"*.png \
      "characters/$CH/forms/$FM/sprites/_orig/tab_hand_r_pad"*.png \
      "characters/$CH/forms/$FM/sprites/_orig/arm_r_fore"*.png
"$PY" tools/wrist_tab_trim.py --character "$CH" --form "$FM"

step "4/26 鞋拆件（常态鞋 + 踮脚鞋，顺带把腿件切线以下擦干净）"
"$PY" tools/make_foot_parts.py --character "$CH" --form "$FM"

step "5/26 眼部四件（眼眶/眼白/眼球/眼线）"
"$PY" tools/make_eye_parts.py --character "$CH" --form "$FM"

step "6/26 嘴三件（量嘴线 + 先铺一版几何口内兜底）"
"$PY" tools/make_mouth_parts.py --character "$CH" --form "$FM"

step "7/26 张嘴真素材（AI 重绘张嘴脸 → 虹膜配准 → 取口内）"
"$PY" tools/make_mouth_open_parts.py --character "$CH" --form "$FM"

step "8/26 呆毛（无损切出）"
"$PY" tools/make_hair_parts.py --character "$CH" --form "$FM"

step "9/26 刘海 + 额头（AI 重绘回贴）"
"$PY" tools/make_bangs_parts.py --character "$CH" --form "$FM" \
      --redraw "$(rd head_nobangs characters/xiaoxun/design/redraw/head_nobangs.png)"

step "10/26 眉毛（AI 重绘 + alpha 抠像）"
BROW_RD="$(rd_opt head_nobrows)"
if [ -n "$BROW_RD" ]; then
  "$PY" tools/make_brow_parts.py --character "$CH" --form "$FM" --redraw "$BROW_RD"
else
  echo "跳过：本形态没有 head_nobrows 重绘底图（眉毛烘在原画里，rig 不拆眉件）"
fi

step "11/26 闭眼真素材（AI 重绘闭眼脸 → 脸部 NCC 配准 → 切补片）"
"$PY" tools/make_eye_closed_parts.py --character "$CH" --form "$FM"

step "12/26 笑眼真素材（同一条流水线，底图换成山型 ∩ 的笑眼脸）"
"$PY" tools/make_eye_closed_parts.py --character "$CH" --form "$FM" --variant smile

step "13/26 痛苦闭眼 >_< 与真·瞪大眼（痛苦=第三张重绘底图；瞪大=原画眼件仿射撑开）"
"$PY" tools/make_eye_closed_parts.py --character "$CH" --form "$FM" --variant pain
# 瞪大眼**不走 AI 重绘**：那张图画成了"整只眼放大"（眼白 127x136 vs 本体眼眶 104x87），
# 照抄=脸颊一块白圆角矩形，缩回去又变成重画一遍眼白。Live2D 的 ParamEyeLWide 本来
# 就是"把同一张眼件的顶点往上拉"，所以这里用原画眼件各向异性放大 (1.12, 1.20)。
"$PY" tools/make_eye_wide_parts.py --character "$CH" --form "$FM"

step "14/26 上眼睑（没有闭眼真素材时的兜底方案）"
"$PY" tools/make_eyelid_parts.py --character "$CH" --form "$FM"

step "15/26 混合模式零件（腮红·乘算 / 眼高光·加算，程序化画出来的）"
"$PY" tools/make_blend_parts.py --character "$CH" --form "$FM"

step "16/26 侧发两缕 + 后发（AI 重绘无侧发的脸 → 虹膜配准 → 挖发补脸）"
"$PY" tools/make_sidehair_parts.py --character "$CH" --form "$FM" \
      --redraw "$(rd head_nosidehair characters/xiaoxun/design/redraw/head_nosidehair.png)"

step "17/26 头皮塗り足し（seg_head 是张光头：抹掉人耳 / 鬓发翼换发色 / 颅顶铺发基色）"
# ⚠ 必须排在 14 步**之后**：那一步挖走鬓发才会在 seg_head 上留下「只在被盖住时
#   才成立」的肤色翼。也必须排在 15/16 步**之前**（它们同样改 seg_head）。
#   Live2D 官方 PSD 教程：元画で隠れていた部分の描き足しを忘れずに。
#   不补画就收鬓发 = 第九问被打回的「人耳裸露在脸颊」。
"$PY" tools/make_scalp_patch.py --character "$CH" --form "$FM"

step "18/26 眼线二次拆件（最后跑：脸上那只睁眼挖成眼窝皮肤，必须排在所有改 seg_head 的工具之后）"
"$PY" tools/make_eyeline_parts.py --character "$CH" --form "$FM"

step "19/26 闭合笑线剪切（把笑线从 seg_head 上剪下来，必须排在所有改 seg_head 的工具之后）"
"$PY" tools/make_mouth_line_cut.py --character "$CH" --form "$FM"

step "20/26 擦掉烘进别的部件里的残留（眼部差分件里的侧发 / 躯干肩上的鲍勃发梢 / 头件下缘的烂衣领）"
# ⚠ 必须排在所有改 seg_head / seg_torso / eye_* 的工具**之后**、高清化**之前**：
#   后者由 1× 生成 @2x，放在它前面擦，两个分辨率天然一致（自己在 @2x 上再跑一遍
#   同样的阈值会得到**不同**的结果 —— 2026-10-18 实测，抗锯齿过渡带宽一倍）。
"$PY" tools/clean_baked_residue.py --character "$CH" --form "$FM" | tail -4

step "20b/26 发片残渣 + 边缘返修（切件时多吃进去的衣领青布/皮肤、撕碎的发梢、硬台阶边）"
# ⚠ 同样必须排在高清化**之前**：@2x 由 1× 派生，先洗 1× 两个分辨率才天然一致。
# 这一步对治第十八问的「所有发型都有杂毛 / 长发块状不柔顺」：
#   ① 发片里烘着的青布和皮肤 —— 内部按最近邻重画、外缘软羽化擦除；
#   ② hair_crown_long 下缘整片撕碎的发梢 —— 按"最小发缕宽度"开运算清掉；
#   ③ 所有发片的 alpha 硬台阶 —— 亚像素羽化，这是"柔顺"和"块状"的分界；
#   ④ seg_head 下颌 / seg_torso 衣领顶的塗り足し —— 短发档被鬓发盖住、
#      从没画完的地方，换发型后全露出来。
"$PY" tools/clean_hair_residue.py --character "$CH" --form "$FM" | tail -3

step "20c/26 脸的轮廓线（按模板把下颌/脸颊的主線补回 seg_head）"
# ⚠ 必须排在**所有**改 seg_head 的工具之后（2/9/16/17/18/19/20/20b）、高清化之前。
# 第三十二问实测：模板下颌线亮度 34~88，产物最暗 237~253 —— 一条线都没有，
# 脸一路"胖"到塗り足し的外沿（y=328 那行脸宽 48px → 97.8px，+104%）。
# 成因是 15 步把横髪从 seg_head 上挖走时，长在「脸↔头发」交界上的主線
# 跟着头发一起走了。短发档被 hair_side_l/r 盖住看不出来，twin/pony/long 全露。
# Live2D 官方：のりしろ要留，但「主線が無いパーツの分かれ目」才该模糊 ——
# 有主線的地方必须是实的，所以这里是"塗り足し保持 + 其上另画线"，不是裁掉塗り足し。
"$PY" tools/draw_face_contour.py --character "$CH" --form "$FM"

step "20c/26 腋下描き足し（把抬臂后会露底的腋窝补进躯干）"
# 必须排在 clean_baked_residue / trim_exposed_residue 之后：那两步会把
# 「只在被盖住时才成立」的料当残渣清掉，补在它们前面等于白补。
# 也必须排在高清化之前：这一步同时写 1× 和 @2x，之后高清化会重算 @2x，
# 两条路都带着补料，不冲突。
# 第四十六问 kirara_jump 全身巡检：手臂抬起时白夹克侧缘与青袖子之间
# 裂开楔形背景（logs/asset_qa/q46_armpit_cmp.png 上下对照）。
"$PY" tools/armpit_patch.py --character "$CH" --form "$FM"

step "21/26 切件高清化（每个件生成 2× 的 @2x，make_rig 会自动改用并把 scale 乘 0.5）"
# 先空跑一遍 make_rig 刷新「rig 引用了哪些件」这张表：高清化只给引用到的件做 @2x，
# 而它读的是上一次的 rig.json。上一步新增了部件时不刷新，新件就会漏掉 @2x
# （2026-10-15 加 arm_*_root 时实测漏了 2 个，被 selfcheck 的「全量启用」闸抓到）。
python3 tools/make_rig.py --character "$CH" --form "$FM" >/dev/null
"$PY" tools/make_hires_sprites.py --character "$CH" --form "$FM"

step "22/26 星星眼差分件（星形虹膜 + ✨ 素材，AI 源图抠像；整组可选）"
# ⚠ 必须排在高清化**之后**（2026-10-16 用户打回第一版之后改的顺序）：
# 星形件不再自己配色，而是拿**常态虹膜那张贴图**当底、只把星形区域点亮，
# 所以 1× 要用 eye_?_ball.png、2× 要用 eye_?_ball@2x.png —— 后者是上一步的产物。
# 这样星以外的像素和常态件逐像素相同，切换时不会变色也不会变锐度。
"$PY" tools/make_star_eye_parts.py --character "$CH" --form "$FM"
"$PY" tools/make_manpu_parts.py --character "$CH" --form "$FM"

step "23/26 兜帽整形（按头部实测几何把画出来的兜帽削到该有的厚度 + 算放置参数）"
"$PY" tools/make_hood_part.py --character "$CH" --form "$FM" \
  --source acc_hood_cute_v6.png
"$PY" tools/make_attach_parts.py --character "$CH" --form "$FM"
"$PY" tools/make_wardrobe.py --character "$CH" --form "$FM"

step "24/26 外套前襟下摆的几何（量出哪几列是前襟、哪几行是下摆，给 make_rig 定网格）"
"$PY" tools/make_jacket_parts.py --character "$CH" --form "$FM"

step "25/26 裙子里布（从躯干件上复制裙摆 → 压暗当裏地；@2x 同掩码原样切）"
# ⚠ 必须排在高清化（20 步）**之后**：里布的 @2x 不走超分，而是把 1× 的掩码放大两倍
# 再从 seg_torso@2x.png 上切 —— 那张图是上一步的产物。顺序反了就只有 1× 没有 @2x。
"$PY" tools/make_skirt_parts.py --character "$CH" --form "$FM"

step "25d/26 颈部脖子桩拆件（seg_torso 顶部 overlap 行 → torso_top_fill）"
# ⚠ 必须排在高清化（21 步）**之后**：它直接从 seg_torso@2x 上切，自己写 1× 和 @2x，
#   排在前面会被高清化用 1× 重算的 @2x 盖掉，无损切分就不成立了。
# ⚠ 必须排在 make_rig **之前**：它往 body_parts.json 里加了一个新部件。
# 第四十八问(c)：这 38 行是 make_body_parts 拿颈线复制出来的桩，短发档藏在头后面，
# 换长发/双马尾/高马尾就从脖子两侧支出来（青绿方块 + 褐色污渍）。
"$PY" tools/split_torso_top.py --character "$CH" --form "$FM"

# ★★★ 第五十一问：原来这里有一步 25e「肘折线」（工具 elbow_crease.py），
#   专门在前臂近端画一条深色轮廓线。用户截图指着它说「肘关节那一条深色的线…
#   他不应该存在」—— 对照参考图 wave_up.png 的折袖（logs/asset_qa/q51_ref_fold.png）
#   也确实如此：整只折袖是一整块连续的布，深色线只在外剪影上。
#   该步骤与那个工具已整个删除，不要再加回来。

step "25e/26 肘关节补件（折肘时内侧两半料的拼缝 + 交叉尖角）"
# ⚠ 必须排在高清化之后、make_rig 之前（读 @2x、写新部件进 arm_parts.json）。
# 第四十八问(b)：外轮廓本来就是对的（两件在肘处是同心等半径半圆），
# 病在圆内 —— 只盖内侧扇区，外侧剪影一个像素都不碰。
"$PY" tools/elbow_cover.py --character "$CH" --form "$FM"

step "25f/26 肘内侧褶布 + 接缝盖布（层 150/151，压在两根袖管之上）"
# ★ Q51 补漏：tools/elbow_gusset.py 是第五十问新建的，一直**没进重建链**，
#   全量重建一次这件就没了（arm_parts.json 是重新生成的）。
# 它干两件事：①填两根管子之间漏背景的缺口；②盖掉折起来之后横躺在袖子
#   中间的两条描边（上臂内侧 + 前臂近端）。必须排在 elbow_cover 之后。
"$PY" tools/elbow_gusset.py --character "$CH" --form "$FM"

step "26/26 生成 rig 并验收"
python3 tools/make_rig.py --character "$CH" --form "$FM"

# 25b 接缝塗り足し（のりしろ）。必须排在 make_rig **之后** —— 它要按 rig 的
# 层序和放置参数把件合成起来，才知道哪两件对接处漏了。只改像素不改几何，
# 所以不用回头重跑 make_rig。
"$PY" tools/fill_seam_holes.py --character "$CH" --form "$FM" --quiet

# 25c 擦掉塗り足し带里烤进来、换发型后会悬空露出来的异色残渣。
#     ★★★ 必须在流水线里，不能只当一次性修补跑完就提交贴图 ——
#     2026-10-19 的教训：第二十一问用它删掉的 274 px 在 commit b0858f3 里，
#     但工具没接进来，第二十二问重建一次就被**原样还原**了，
#     用户截图里那条深褐横条于是又回来了（pony 270 px / twin 138 px）。
#     凡是"改贴图"的工具都必须挂在重建链上，否则下一次 rebuild 就是回滚。
#     排在 fill_seam_holes 之后：先补缝、再擦残渣，顺序反了补缝会把残渣摊开。
"$PY" tools/trim_exposed_residue.py --character "$CH" --form "$FM" | tail -2

"$PY" tools/check_assets.py --character "$CH" --form "$FM" | tail -3
rm -rf tools/__pycache__
echo
echo "全部零件已重建。重开预览才会生效：先 stop 再 ./build/zhuochong_preview --port 5173 --root ."
