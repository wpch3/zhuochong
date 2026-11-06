# Chibi 567×1292 source-locked clean rebuild — failure ledger (2026-11-01)

> Isolated candidate only. This report is distinct from historical 1410/40, 1653/41, and 708/20 runs. It uses the newly explicit `design_sheet_chibi.png` body-fit entry, suppresses Teen-only hand pose artwork and Teen-coordinate face contour generation, and does not modify production sprites or rig.

## Run result

- `pass=false`, `checks=1342`, `failures=34`, `design_iou=0.993492`.
- Candidate rig: 81 parts / 26 actions. Sixteen Chibi hair/hood attachments still have no lawful Chibi cut source and are skipped (see `isolated_rebuild_status.md`).
- 1× source canvas kept at 567×1292; exact four-point crop `[628,101,1416,1891]` from the Chibi design sheet. The source itself is visually cleaner than the tracked damaged body, but the rebuilt model is not acceptable yet.
- `make_hand_parts.py` generates only structural wrist pads for Chibi; it does not import Teen `open/heart` art. Chibi small/mitten and gesture-specific art remain unimplemented; reduced check count is not a pass.
- Raw report: [`asset_qa_source_locked_rebuild_2026-11-01.json`](asset_qa_source_locked_rebuild_2026-11-01.json). Full rebuild log: [`rebuild_source_locked_2026-11-01.log`](rebuild_source_locked_2026-11-01.log).
- Real C engine default snapshot at 1.0: [`engine_default_source_locked_candidate_2026-11-01.png`](engine_default_source_locked_candidate_2026-11-01.png); 3× face close-up: [`engine_face_zoom_source_locked_candidate_2026-11-01.png`](engine_face_zoom_source_locked_candidate_2026-11-01.png). Eye corners/eyelines visibly fail and block release.

## Failures (all thresholds unchanged)

| # | Part/area | Check | Measured result | Status |
|---:|---|---|---|---|
| 1 | `arm_l_gusset@2x` | 色卡 | 最远主色距离 76（#589898 占比 7%） | Open |
| 2 | `arm_l_root` | 色卡 | 最远主色距离 71（#489898 占比 12%） | Open |
| 3 | `armpit_mask` | 灰度遮罩有有效范围 | 取值 [0,0]，预期 0..255 | Open |
| 4 | `分段` | 无损切分 | 静止合成比原图少 1343 像素 | Open |
| 5 | `鞋` | 踮脚鞋鞋口抬高=30px(l) | 实测抬高 73px，rig 的 root.dy 按 30px 配套 | Open |
| 6 | `鞋` | 常态鞋触地(r) | 鞋底在 y=1290，地面 y=1291 | Open |
| 7 | `鞋` | 踮脚鞋鞋口抬高=30px(r) | 实测抬高 74px，rig 的 root.dy 按 30px 配套 | Open |
| 8 | `真素材` | 口内有牙 | 牙 0 像素（下限 5） | Open |
| 9 | `真素材` | 闭眼接缝(l) | 接缝色差 45.48（上限 12） | Open |
| 10 | `真素材` | 闭眼接缝(r) | 接缝色差 47.92（上限 12） | Open |
| 11 | `分段` | 袖下躯干无新窟窿 | 躯干自身新增内部空洞 21261 像素（上限 60） | Open |
| 12 | `分段` | 头发摆动不露底(-12,+0) | 发梢甩 (-12,+0) 后身体内部新增空洞 226 像素（上限 20） | Open |
| 13 | `分段` | 头发摆动不露底(+12,+0) | 发梢甩 (+12,+0) 后身体内部新增空洞 373 像素（上限 20） | Open |
| 14 | `分段` | 裙摆接缝不露底(腿 -20px) | 腿摆 -20px 后裙摆下 24px 带内新露底 69 像素（上限 60） | Open |
| 15 | `分段` | 裙摆接缝不露底(腿 +20px) | 腿摆 +20px 后裙摆下 24px 带内新露底 75 像素（上限 60） | Open |
| 16 | `嘴部` | 张到最大不越过下巴 | 嘴下沿 body_full y=559，下巴 y=283（越过去就是用户说的"嘴巴位置偏下"/一条拖到脖子的黑块） | Open |
| 17 | `交互区域` | 摸头区域罩住整张脸 | head 区域 x196..649 y0..718，而 seg_head 占 x140..707 y68..712（露在外面的部分会被判成 body，点脸变成摸身体） | Open |
| 18 | `混合零件` | 腮红_l 压在实心脸上 | 0% 的不透明像素落在 seg_head 的实心区上（要求 ≥80%；multiply 画在透明处等于没画） | Open |
| 19 | `混合零件` | 腮红_r 压在实心脸上 | 0% 的不透明像素落在 seg_head 的实心区上（要求 ≥80%；multiply 画在透明处等于没画） | Open |
| 20 | `差分发型` | hair_twin_l 与本体头发同源配色 | 平均色差 ΔE=5.1（上限 5.0）、明度对比差 ΔσL=9.8（上限 6.0）；基准 = hair_back/hair_side_l/hair_side_r/hair_front | Open |
| 21 | `差分发型` | hair_twin_r 与本体头发同源配色 | 平均色差 ΔE=5.1（上限 5.0）、明度对比差 ΔσL=9.8（上限 6.0）；基准 = hair_back/hair_side_l/hair_side_r/hair_front | Open |
| 22 | `差分发型` | hair_pony_back 与本体头发同源配色 | 平均色差 ΔE=5.0（上限 5.0）、明度对比差 ΔσL=11.0（上限 6.0）；基准 = hair_back/hair_side_l/hair_side_r/hair_front | Open |
| 23 | `差分发型` | hair_long_back 与本体头发同源配色 | 平均色差 ΔE=4.9（上限 5.0）、明度对比差 ΔσL=9.1（上限 6.0）；基准 = hair_back/hair_side_l/hair_side_r/hair_front | Open |
| 24 | `头部几何` | 藏hair_back有件接管 | hairstyle:twin 档自带的差分件盖住了它的 0.0%（下限 45%；接管者只能是这一档自己的件，不算碰巧垫在底下的本体），露出透明背景 0.03%（上限 2%） | Open |
| 25 | `头部几何` | 藏hair_side_l有件接管 | hairstyle:twin 档自带的差分件盖住了它的 0.0%（下限 45%；接管者只能是这一档自己的件，不算碰巧垫在底下的本体），露出透明背景 0.00%（上限 2%） | Open |
| 26 | `头部几何` | 藏hair_side_r有件接管 | hairstyle:twin 档自带的差分件盖住了它的 0.0%（下限 45%；接管者只能是这一档自己的件，不算碰巧垫在底下的本体），露出透明背景 0.13%（上限 2%） | Open |
| 27 | `头部几何` | 藏torso_top_fill有件接管 | hairstyle:twin 档自带的差分件盖住了它的 0.0%（下限 45%；接管者只能是这一档自己的件，不算碰巧垫在底下的本体），露出透明背景 0.24%（上限 2%） | Open |
| 28 | `头部几何` | 藏hair_back有件接管 | hairstyle:pony 档自带的差分件盖住了它的 1.6%（下限 45%；接管者只能是这一档自己的件，不算碰巧垫在底下的本体），露出透明背景 0.04%（上限 2%） | Open |
| 29 | `头部几何` | 藏hair_side_l有件接管 | hairstyle:pony 档自带的差分件盖住了它的 0.0%（下限 45%；接管者只能是这一档自己的件，不算碰巧垫在底下的本体），露出透明背景 0.00%（上限 2%） | Open |
| 30 | `头部几何` | 藏hair_side_r有件接管 | hairstyle:pony 档自带的差分件盖住了它的 4.4%（下限 45%；接管者只能是这一档自己的件，不算碰巧垫在底下的本体），露出透明背景 0.13%（上限 2%） | Open |
| 31 | `头部几何` | 藏torso_top_fill有件接管 | hairstyle:pony 档自带的差分件盖住了它的 0.0%（下限 45%；接管者只能是这一档自己的件，不算碰巧垫在底下的本体），露出透明背景 0.24%（上限 2%） | Open |
| 32 | `素材真伪` | hand_l_pad 仍是结构性平涂 | 769 色 / 6968px —— 豁免理由：塗り足し补片，不是一档手势，整片纯肤色垫在腕下 | Open |
| 33 | `素材真伪` | hand_r_pad 仍是结构性平涂 | 691 色 / 7031px —— 豁免理由：同上（右手） | Open |
| 34 | `素材真伪` | mouth_mask 是真原画不是平涂色块 | 不透明区 3894px 里只有 1 种颜色（真原画最低一档 ~597 色，判据 128）；若确属结构件请到 FLAT_BY_DESIGN 写明理由 | Open |

## Visual gate and next repair order

1. Rebuild eye/base/lash carving from the Chibi source, remove baked eye remnants, and inspect default/wide/blink/closed in C at 3×. Do not broaden thresholds.
2. Correct the source-derived head/torso and arm overlap geometry; the candidate has 21,261 new torso holes and 1,343 pixels missing from the static composite.
3. Rework mouth interior/teeth and its lower bound against the face/chin; verify closed and open states in-engine.
4. Re-register blush, hitbox, shoes, hair color/pose takeovers, tail and hoodie combinations; source the 16 absent parts only from accepted Chibi-specific references.
5. Implement distinct `small` and `mitten` Chibi hand pieces under an independent `hand_style` selector; keep hand pose/wrist motion separate. No Teen hand pieces are permitted.
6. Require zero unexplained asset failures and zero missing attachment warnings, then run the full real-engine matrix. Nothing from this candidate enters production before both gates and user approval.

> Machine QA is not aesthetic acceptance. The observed C frame has obvious black/jagged fragments at both outer eye corners, an uneven brow/eye seam, and other face cut artifacts; this candidate fails visual review and remains isolated.
