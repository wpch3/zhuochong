# Chibi 全链重建与真实引擎验收 — WIP（2026-11-01）

> **状态：未验收、未接入生产。** 较早 `/tmp/zc_chibi_refit_20261101` 为 37 项失败；历史 clean candidate 为 1410 项 / 40 fail（原始报告已丢失，保留 failure-only 摘要）；本轮最新完整来源锁定 rebuild 为 81 部件 / 26 动作、1342 项中 34 fail。之后按 C 引擎/机器 QA 的命中区缺陷，隔离重生 rig 并修复摸头区：同一 1342 项定向 QA 现为 **33 fail**（只修复这一个项目，尚未重跑 27 步 full chain）。真实 C 引擎默认眼角仍明显黑碎边/锯齿，目视不通过；34-fail full-chain 与 33-fail targeted rig 口径必须区分，不能据此宣称全链改善或接入生产。候选贴图/rig 均非发布资产。

## 依据与边界

- 拆件/对位真值：`characters/xiaoxun/design/design_sheet_chibi.png` 与 Chibi 原始全身图；另按本轮用户补发的 Chibi 形象参考复核风格。
- 可爱度指南：`提升桌宠Chibi形象可爱度指南.pdf`。其中建议微调袖口/手部、内八站姿、耳尾蓬松感、猫猫嘴和高光；待机可轻微摇晃、偶尔耳抖或脚部动作；摸头需要表情与耳朵反馈。
- 当前最新来源锁定候选根目录：`/home/user/chibi-candidate-20261101`；本轮 C 引擎预览曾用 port `5188`（已停止）。候选贴图没有复制进生产角色素材目录。当前分支上的生成器代码是 WIP，但正式 `rig.json` 保持原样，因此仓库自检会报告 rig 生成器指纹过期；这是隔离门禁，不得为消掉红项而提前重建生产 rig。
- `/tmp/zc_chibi_refit_20261101` 与 port `5202` 属较早 refit 候选（37 fail），仅作历史回溯；以下旧 wide/tail 截图与观察不代表当前来源锁定候选状态。

## 最新来源锁定候选：本轮证据

- 来源锁定：Chibi `design_sheet_chibi.png`，四点框 `[628,101,1416,1891]`，目标画布 567×1292。
- 全链产物：81 部件 / 26 动作，资产 QA 1342 项中 **34 fail**；还缺 16 个 Chibi 头发/兜帽切件。完整报告 `asset_qa_source_locked_rebuild_2026-11-01.json`、逐项清单 `asset_qa_source_locked_rebuild_summary_2026-11-01.md`、日志 `rebuild_source_locked_2026-11-01.log`。
- 真实 C 引擎 default 全身 + 3×脸部实拍已归档。肉眼可见两眼外角黑碎边/锯齿和眉眼/眼线接缝问题，**视觉不通过**：`engine_default_source_locked_candidate_2026-11-01.png`、`engine_face_zoom_source_locked_candidate_2026-11-01.png`。
- 用户本轮补充的全身参考 image-29 已归档于 `reference_generated/chibi_fullbody_live2d_user_image_29_2026-11-01.png`；只用于身份/整体风格对照，不直接裁切。
- 之后完成一个**定向**命中区修复：头部交互矩形依 `seg_head` bbox 扩至 `[136,711]`，C 引擎实际区间查询通过；候选 1342 项定向 QA 为 33 fail，但未重跑 full chain。证据 `head_hitbox_fix_2026-11-01.md` 与 probe JSON。
- 机器失败数字和图片的详细观察见 `isolated_rebuild_status.md`；不与历史 1410/40 或 37 fail 候选混算。眼部形态学试验结果见 `eye_cleanup_trials/README.md`，两个版本均被拒绝。

## 历史 refit 候选的进展（不是当前候选）

1. 候选 eye parts 抽取改为用 Chibi 眼部颜色/虹膜范围构建紧致眼窝，并生成单独 `carve` 遮罩清理底图中的烘焙眼部；避免把眼眶裁切 halo 拉伸到脸/头发。
2. `make_eye_wide_parts.py` 改为只画相对常态眼白的增量眼白与上睫毛，倍率 `KX=1.04, KY=1.10`，不拉伸独立虹膜、不铺固定底盘；Chibi wide 状态保留常态白眼底件。洋红底合成确认 wide PNG 中心是透明区（alpha=0），不是黑色绘画像素。新增的 16 个纯洋红低 alpha 像素已从候选图清除；最新资产检查中该项已归零。
3. `rebuild_parts.sh` 调整为先生成 `eyeline_parts.json` / 上睫毛件，再生成 wide 件，防止干净重建时误用旧上睫毛缓存。
4. 候选新引擎完成 wide 参数多版实拍。最新 `eye_state_wide_v7_face.png` 相对 v4 收窄为上缘增量，但默认与 wide 都仍可见眼白外缘/眼角接缝，**wide 未通过**；不能以静态分割指标替代引擎观感验收。默认对照为 `eye_state_default_v7_face.png`。
5. 候选完整角色默认态、tail up/puff 和一段 6 秒 idle 采样已存档。默认全身整体比例尚可；relaxed 尾巴在放大后有蓬松体积，idle 有轻微身体摇摆/呼吸，但 tail up 较细且容易被手臂遮挡，puff 轮廓过毛、髋侧有疑似像素线需查原件和合成层级。
6. 已把当前脚本 WIP 与审计材料放进本目录，便于评审/继续接手；不包含候选角色生成贴图。

## 历史候选验收证据（均为未通过/阶段性截图；不是当前 34-fail 候选）

- `chibi_candidate_default_v9.png` — 候选引擎默认态全身。
- `eye_state_default_v7_face.png` / `eye_state_wide_v7_face.png` — 该历史 refit 候选默认与 wide 脸部 A/B；wide 仍不合格。
- `tail_pose_up.png`、`tail_pose_puff.png`、`tail_pose_matrix.png` — 尾巴四姿态实际引擎截图/矩阵。
- `idle_tail_cycle_zoom.png` — idle 0–6 秒尾部区域采样。
- `asset_qa_latest_partial_2026-11-01.json` — 在当前候选贴图上运行的最新资产检查，`pass=false`、`fail_count=37`、设计 IoU `0.993457835067557`；不是干净全链 rebuild 的结果。
- `full_chain_report_historical.json` — 候选早期完整链 QA 原始报告，`pass=false`、`fail_count=37`。早期与当前失败项数相同不代表根因相同，也不代表缺陷已修复。

## 历史 refit 候选的未解决硬问题（37-fail 历史报告；不是当前来源锁定候选）

### 眼睛与表情

- 最新真实引擎 wide 仍呈明显白环/眼角接缝；黑/白碎点也曾在旧 wide 矩阵出现。继续检查眼窝边界、上睫毛重叠、`seg_head` 残留与 layer 顺序；通过前不能接生产。
- 早期报告闭眼左右接缝色差为 `43.78 / 47.38`（上限 12）；最新 full-chain 尚未复测。
- 口内牙像素为 0；当前开口嘴的纵向范围曾超过下巴。需要核对可爱猫嘴比例、张嘴内容与引擎状态。

### 身体切分与材质

当前候选资产检查的 37 项失败还包括：袖下躯干内部新洞 `1224px`（早期报告曾为 `14439px`，局部底图修复有改善但仍越线）、颈部压力姿势洞 `109px`、摆腿后裙摆露底 `71/76px`；踮脚鞋口实测抬高 `74px`（目标 30px），右鞋触地偏 1px；上臂内缘夹带夹克白；腮红落在透明区域为 0%；头部触摸区未覆盖整个脸；差分发型与本体明度离散差超限。需逐项修底层几何/遮罩，不可用缩小 QA 容差或局部涂补绕过。

### 缺失挂件、尾巴与衣物预留

- Chibi 当前 rig 构建警告跳过 16 个附件切件：`hair_sidelong_l/r`、`hair_crown_twin/pony/long`、`hood_up_twin/pony/long`、`hair_hood_twin/pony/pony_side/long`、`hair_sweep_twin_l/r`、`hair_sweep_pony_l/r`。这些是未完成部件，不应静默当作已覆盖。
- 尾巴四态互斥组已经存在；真实引擎中 relaxed 较软蓬，up 偏窄，puff 易显炸毛且疑有髋侧碎线，尚未按本轮参考图定稿。指南中的“耳尾蓬松感”仍是验收项。
- 设计附件清单现有 12 个位置槽，但服装包目前 `forms` 仅覆盖 Teen；Chibi 没有可用换装包。后续应保留并映射 Chibi 的 `seg_torso`、袖/臂、`skirt_main`/`skirt_lining`、腿与鞋等替换位，不能挪走或删除基础服装部件来腾空。
- idle 采样确认有温和摇摆/呼吸；当前代码里 `api/idle` 只报告闲置时长/睡眠阈值，尚未确认有定时轮换 idle 动作。`ear_twitch`、`shift_weight`、`tiptoe` 等动作存在但主要是显式动作，偶发触发/轮换策略是遗漏项。

## 历史候选当时记录的下一步（现行顺序见 `isolated_rebuild_status.md` 与 34-fail summary）

1. 先修眼角与 wide 合成：看 alpha、底图 carve、睫毛/眼窝层顺序和眼角原画残留；用默认、wide、blink、closed、smile、pain 的真实引擎矩阵复核。
2. 修复或补画缺失附件；审阅 tail up/puff 的源图、注册点和边缘碎线；评估 idle 动作轮换策略。衣物槽只登记/保留，不以空壳贴图冒充完成。
3. 在隔离目录做**干净全链 rebuild**，处理 `hand_*@2x` 尺寸不匹配及所有缺件警告；重新运行完整资产 QA 与 repo 自检，要求明确列出 0 个未解释失败。
4. 通过全链报告与实际引擎目视验收后，才把生成资产接入生产角色目录。之后另行提交完成版；本次 WIP 推送不代表验收通过。
