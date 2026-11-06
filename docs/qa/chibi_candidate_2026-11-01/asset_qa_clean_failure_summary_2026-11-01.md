# Clean Chibi candidate QA — 40 failures (2026-11-01)

> Reconstructed from the final QA console output for `/tmp/zc_chibi_clean_20261101/`; this is a failure-only extract, **not** the original 1410-item JSON report. Candidate was not accepted or copied into production.

**Summary:** `pass=false`, 1410 checks, 40 failed. Candidate rig: 85 parts / 26 motions. Exact source report was in temporary storage and is no longer available; this extract preserves each failed check and reported measurement.

## Failed checks

| # | Part / area | Check | Measured result |
|---:|---|---|---|
| 1 | `arm_l_gusset` | 色卡 | 最远主色距离 84（`#889898` 占比 8%） |
| 2 | `arm_l_gusset@2x` | 色卡 | 最远主色距离 84（`#889898` 占比 8%） |
| 3 | `arm_l_root` | 色卡 | 最远主色距离 71（`#489898` 占比 8%） |
| 4 | `arm_r_gusset` | 色卡 | 最远主色距离 96（`#989898` 占比 13%） |
| 5 | `arm_r_gusset@2x` | 色卡 | 最远主色距离 96（`#989898` 占比 15%） |
| 6 | `armpit_mask` | 灰度遮罩有有效范围 | 取值 `[0,0]`，预期 `0..255` |
| 7 | `分段` | 无损切分 | 静止合成比原图少 407 像素 |
| 8 | `鞋` | 踮脚鞋口抬高=30px (left) | 实测 73px，rig `root.dy` 按 30px 配套 |
| 9 | `鞋` | 踮脚鞋口抬高=30px (right) | 实测 74px，rig `root.dy` 按 30px 配套 |
| 10 | `arm_l_upper` | 袖片内缘没夹带夹克白 | 越界行 5（上限 2），单行最大越界 7px（上限 4）；设计值 0/0 |
| 11 | `arm_r_upper` | 袖片内缘没夹带夹克白 | 越界行 5（上限 2），单行最大越界 2px（上限 4）；设计值 0/0 |
| 12 | `嘴部` | 口内有牙 | 牙 0 像素（下限 5） |
| 13 | `闭眼` | 闭眼接缝 (left) | 色差 48.26（上限 12） |
| 14 | `闭眼` | 闭眼接缝 (right) | 色差 48.41（上限 12） |
| 15 | `分段` | 袖下躯干无新窟窿 | 躯干自身新增内部空洞 20,259 像素（上限 60） |
| 16 | `分段` | 头发摆动不露底 (-12,0) | 新增内部空洞 341 像素（上限 20） |
| 17 | `分段` | 头发摆动不露底 (+12,0) | 新增内部空洞 250 像素（上限 20） |
| 18 | `分段` | 关节不露底 (wrist left) | 手单独转 ±20° 后腕部新增空洞 99 像素（上限 60） |
| 19 | `分段` | 关节不露底 (wrist right) | 手单独转 ±20° 后腕部新增空洞 100 像素（上限 60） |
| 20 | `分段` | 裙摆接缝不露底 (leg -20px) | 新露底 70 像素（上限 60） |
| 21 | `分段` | 裙摆接缝不露底 (leg +20px) | 新露底 73 像素（上限 60） |
| 22 | `嘴部` | 张到最大不越过下巴 | 嘴下沿 body_full y=557，下巴 y=284；越过下巴 |
| 23 | `交互区域` | 摸头区域罩住整张脸 | head hitbox x196..649 y0..718；`seg_head` x140..707 y68..712，脸部外沿落在 body 区 |
| 24 | `腮红_l` | 压在实心脸上 | 0% 不透明像素落在 `seg_head` 实心区（要求 ≥80%） |
| 25 | `腮红_r` | 压在实心脸上 | 0% 不透明像素落在 `seg_head` 实心区（要求 ≥80%） |
| 26 | `hair_twin_l` | 与本体头发同源配色 | 平均色差 ΔE=3.1（上限 5），明度对比差 ΔσL=9.0（上限 6） |
| 27 | `hair_twin_r` | 与本体头发同源配色 | 平均色差 ΔE=3.1（上限 5），明度对比差 ΔσL=9.0（上限 6） |
| 28 | `hair_pony_back` | 与本体头发同源配色 | 平均色差 ΔE=3.1（上限 5），明度对比差 ΔσL=10.3（上限 6） |
| 29 | `hair_long_back` | 与本体头发同源配色 | 平均色差 ΔE=3.0（上限 5），明度对比差 ΔσL=8.3（上限 6） |
| 30 | `hairstyle:twin` | 藏 `hair_back` 有件接管 | 差分件覆盖 0.0%（下限 45%）；露出透明背景 0.05%（上限 2%） |
| 31 | `hairstyle:twin` | 藏 `hair_side_l` 有件接管 | 差分件覆盖 0.0%（下限 45%）；露底 0.00% |
| 32 | `hairstyle:twin` | 藏 `hair_side_r` 有件接管 | 差分件覆盖 0.0%（下限 45%）；露底 0.23% |
| 33 | `hairstyle:twin` | 藏 `torso_top_fill` 有件接管 | 差分件覆盖 0.0%（下限 45%）；露底 0.42% |
| 34 | `hairstyle:pony` | 藏 `hair_back` 有件接管 | 差分件覆盖 1.6%（下限 45%）；露底 0.05% |
| 35 | `hairstyle:pony` | 藏 `hair_side_l` 有件接管 | 差分件覆盖 0.0%（下限 45%）；露底 0.00% |
| 36 | `hairstyle:pony` | 藏 `hair_side_r` 有件接管 | 差分件覆盖 3.7%（下限 45%）；露底 0.24% |
| 37 | `hairstyle:pony` | 藏 `torso_top_fill` 有件接管 | 差分件覆盖 0.0%（下限 45%）；露底 0.42% |
| 38 | `hand_l_pad` | 素材真伪 | 991 色 / 6172px；判据视作结构性平涂补片 |
| 39 | `hand_r_pad` | 素材真伪 | 904 色 / 6092px；判据视作结构性平涂补片 |
| 40 | `mouth_mask` | 素材真伪 | 不透明区 3894px 仅 1 种颜色；最低要求 128 种，实测原画基准约 597 色 |

## Additional rebuild warnings (not part of the 40 checks)

缺少 16 项 Chibi 挂件切件产物：`hair_sidelong_l/r`、`hair_crown_twin/pony/long`、`hood_up_twin/pony/long`、`hair_hood_twin/pony/pony_side/long`、`hair_sweep_twin_l/r`、`hair_sweep_pony_l/r`。重建器因此跳过这些挂件；应从验收过的 Chibi 来源补齐，不可使用 Teen 模板。
