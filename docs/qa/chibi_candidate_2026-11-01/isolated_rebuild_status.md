# Chibi 隔离重建状态 — 2026-11-01

## 当前结论（最新候选）

**仍未验收、未接入生产。** 2026-11-01 完整 Chibi 来源锁定隔离重建显式使用 `design_sheet_chibi.png`、四点裁框 `[628,101,1416,1891]`，保持 567×1292；Chibi 流程不再调用 Teen 专属脸缘 ROI 或借用 Teen `open/heart` 手势图。该 27 步 full-chain 产物为 81 部件 / 26 动作，`check_assets.py` 1342 项中 **34 项失败**，缺 16 项 Chibi 头发/兜帽切件。随后仅定向重生 rig 修复摸头交互区，1342 项同阈值目标 QA 现为 **33 fail**，这是局部结果，不是完整全链重建。完整报告、日志、targeted 结果、C 引擎图均已归档于本目录。

本人已查看真实 C 引擎默认帧及脸部放大：双眼外角仍有明显黑色碎边/锯齿，眼线/眉眼接缝不自然，候选**视觉不通过**；早期 1px/2px 形态学 lash 清理试验也未通过，已回滚，见 `eye_cleanup_trials/README.md`。2026-11-01 后续重新检查 C rig 实际路径，查明实际使用 `eye_*_lash_up@2x.png`；此前只改 1×、未重建 eyeline 与 @2×，故 C 仍显示旧图。本轮隔离候选已按 eye→eyeline→hires→rig 依赖链完整重生成并重启 C：主弧更干净，但外眼角仍见小碎边/切口，仍**视觉不通过**。聚焦 QA 1310 项/32 fail，不是全链，不与 1342/34、1342/33 直接比较；对照/分层证据见 `eye_lash_pipeline_trial_2026-11-01/`。全链失败仍有静止拼合少 1343px、躯干新洞 21,261px、口内无牙且越过下巴等。定向修复摸头区确已通过同一 hitbox 检查，但其余失败按 targeted JSON 逐项列出。上一份 1410/40 和 37 fail 都是不同历史候选，不得混算或误称改善已验收。

候选贴图、rig 均未接入生产；未完成发型/兜帽/手型/衣物与全动作 C 引擎矩阵。所有 QA 失败清零、缺件来源补正、`small/mitten` 与手势轴独立实现、短/长发/双马尾/兜帽及关键动作组合目视通过并经用户确认前，不得接入生产。

## 本轮实现及验证

- 重建保留 Chibi `body_full` 几何锁、仓库原有 Chibi `sprites/attach_parts.json` 的 11 项与 `rebuild_parts.sh` 的 Chibi 附件/衣柜跳过保护；没有把 Teen 附件生成导入 Chibi，也没有用 Teen 参考图补缺。
- `tools/fill_seam_holes.py` 改为只缓存缩放后切件的局部 RGBA，并在合成时裁剪 ROI，避免逐部件缓存整张 567×1292 画布。旧/新实现对 101 个 rig 部件的层图 RGBA、alpha 遮罩及 ±12 px 摆动逐像素一致；28 个 pose 合成的 alpha mask 无差异，量化 RGB 最大差 1。隔离全链中该步骤成功结束（约 199 秒）。
- 优化已移入仓库工具，新增 `tests/test_fill_seam_memory.py` 与 `make asset-tool-test`；先前以 `/tmp/zc_chibi_work_env/bin/python` 运行通过。`git diff --check` 与 `python3 tools/roadmap_status.py` 通过；ROADMAP/TASKS 计数已对齐。
- 本轮活动 checkout 验证：`make -s test` 2638/0，`make -s asset-tool-test` 通过；带隔离 Pillow/Numpy 的 `make selfcheck` 771 项中 1 项失败，唯一失败为正式 Teen/Chibi `rig.json` 生成器指纹过旧（隔离门禁下未重建正式 rig）。本轮新增 hitbox 静态保护后复测为 772 项中 1 项失败，唯一失败仍为正式 Teen/Chibi rig 指纹过旧。`git diff --check`、`python3 tools/roadmap_status.py` 通过；未跑完整 `make check`。
- 用户本轮新传全身 image-29 已归档并与 C 引擎图目视对照：发型/服装身份线索一致，reference 眼型更圆润且外角更干净；低分辨率截图仅作风格参考，不直接裁切。全身参考和记录见 `reference_generated/README.md`。
- **实际 C 引擎修复**：`tools/make_rig.py` 的 head interaction X 原先沿用粗略 suggested rect `[196,649)`，未覆盖 `seg_head [140,707]`。现改为真实 bbox 并向外留 4px，head 区域 `[136,711]`，下巴交接规则不变。定向同阈值 QA `1342/34 → 1342/33`，摸头区项由 fail 转 pass；C API 在 scale=1.0 对左/右边缘命中点 180、690、705 返回 `head/head_pat`，透明控制点 150 仍为空。证据 `head_hitbox_fix_2026-11-01.md` 与 `head_hitbox_engine_probe_2026-11-01.json`。该结果只重生 rig+定向 QA，不是 27 步 full-chain。
- 眼睫 1px/2px 形态学清理实际 C 试验均未修好碎边，2px 还使上眼线变厚，已回滚所有这次试验代码，未进入生产；失败证据与下一步改法见 `eye_cleanup_trials/README.md`。
- 本轮用户选择了双马尾 Live2D Chibi 参考选项 2，图已保存为 `reference_generated/chibi_twin_tails_live2d_v2.png`。目视：恰好两束、两个清楚的发束根、发色和服装与角色参考一致；但头发与尾巴体积偏大/偏蓬，整体头身略偏幼圆，须作为概念目标而非生产素材。截图 25/26/27 仍是负例。
- 注意：选项生成工具重置了其输出父目录和 `/tmp` 的部分临时内容；已从上传暂存区恢复 image-23 至 image-27 原图。旧的已选短/长概念图文件以及原始 `/tmp` QA JSON 本轮不可访问；已据日志保留失败摘要。后续生成选项必须写入独立空目录，再手工归档，避免影响其他证据。

## 历史 clean candidate：40 项失败概况（非当前来源锁定候选）

逐项判据及测量值见 `asset_qa_clean_failure_summary_2026-11-01.md`。该历史候选主要失败：色卡 5 项，`armpit_mask` 空；静止合成少 407 px；躯干新洞 20,259 px、头发摆动洞 341/250 px、腕洞 99/100 px、裙摆接缝洞 70/73 px；鞋口抬高 73/74 px（目标 30）；袖片夹带夹克白；张嘴无牙且越过下巴；闭眼接缝色差约 48（上限 12）；摸头区域未覆盖脸，腮红位于透明区；发型接管/配色、手垫和 mouth mask 真伪检查未过。完整 full-chain 的 34 项失败读取 `asset_qa_source_locked_rebuild_summary_2026-11-01.md`；摸头区局部修复后 33 fail 的 targeted 结果见 `asset_qa_targeted_hitbox_rerun_2026-11-01.json`。两者不能混称为全链改善。

重建日志另报告缺少 16 项 Chibi 挂件切件：`hair_sidelong_l/r`、`hair_crown_twin/pony/long`、`hood_up_twin/pony/long`、`hair_hood_twin/pony/pony_side/long`、`hair_sweep_twin_l/r`、`hair_sweep_pony_l/r`。未有正确来源时，不能用 Teen 图生成。

## 新增手型要求（2026-11-01，T67.69）

用户要求同时保留此前选定的小巧手与本轮红圈标出的手套感/连袖感手型。截图已归档至 `reference_generated/chibi_hand_mitten_user_marked_2026-11-01.jpg`；双手型隔离契约见 `hand_style_variants_2026-11-01.json`。只读核对发现现有 Chibi rig 只有 `seg_arm_l/r`，无 `hand_*` 独立部件；Teen 的 hand_parts 不能替代 Chibi 来源。后续需在 Chibi 设定稿上确认腕根/袖口，再在隔离候选生成两套左右手件、实现独立 `hand_style` 切换，并目视实际 C 引擎中比例、袖口遮挡/连续性和动作表现。该要求尚未实现或验收，不是生产资产。

## 下一步（按依赖顺序）

1. 使用 image-24 作为 Live2D Chibi 比例/风格锚点、项目设定稿保持身份；保留已选短/长参考记录，并为双马尾/高马尾/兜帽关系准备 Chibi 专用来源。逐图目视检查比例、发束数量/根部、帽兜关系、服装与整体风格，汇报优缺点。错误参考 image-25/26/27 只能记为负例。
2. 以通过目视的同源 Chibi 全身图切出 crown/back/side/sweep/hood parts；检查 ROI 不夹带身体、袖口或手，并重算配准与调色。以 Chibi 设定稿复核腕根/袖口，隔离生成 `hand_l/r_small` 与 `hand_l/r_mitten` 两套部件及独立 `hand_style` 选择器；不得用 Teen 贴图替代。
3. 对照 34-fail full-chain summary 继续修复身体/关节底层几何、眼口/鞋/衣袖/腮红与差分发型/手型，不放宽 QA 阈值；摸头区 X 范围已在定向目标里修复，须在后续 full-chain 再回归。建立干净隔离候选重跑全链，留存新的完整 JSON 与日志。
4. 要求资产 QA 零失败、零缺件警告后，用实际 C 引擎验收短/长发/双马尾与兜帽组合，以及默认、blink/closed/wide、摸头、踮脚、挥手、比心/惊讶、裙摆/尾巴关键姿态；手型小巧/手套感两档均检查比例、腕口遮挡及袖口连续。全数通过后才讨论接入生产和提交。

## 历史候选（不要混算）

- `/tmp/zc_chibi_work_20261101/` 曾把 Teen 附件链引入 Chibi，清单从 11 变 27；`hair_hood_long` 源 ROI 带手和袖口，该路线作废。
- 最早隔离尝试在 `fill_seam_holes.py` 被系统终止，随后 1653 项中 41 项失败。
- `/tmp/zc_chibi_refit_20261101/` 有另一份 37 项失败记录，说明见本目录 `README.md`。这些结果与最新 40 项失败候选不混为一谈。

## 最新范围纠正（2026-11-04）

- Chibi 手型必须并存：正常、有可辨识手指的 `small` 与独立 `mitten`。名称 `small` 或旧源像素 crop 不能自动视为已完成正常有指手；生产手件与腕部/手势解耦门仍开放。
- 真正 Cubism 模型另有作者工程门：自研 C `zrig` 不等于 `.moc3`。当前 Linux checkout 无 Cubism Editor，也无 Chibi PSD/CMO3/MOC3/Model3；官方制作、导出、Core/许可路线见 `docs/memory/CHIBI_CUBISM_TRUE_MODEL_AUDIT_2026-11-04.md`。不得以功能类比声称 Cubism 合规或兼容。
