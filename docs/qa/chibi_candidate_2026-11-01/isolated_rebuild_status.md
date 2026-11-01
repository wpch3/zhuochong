# Chibi 隔离重建状态 — 2026-11-01

## 当前结论（最新候选）

**仍未验收、未接入生产。** 最新干净隔离候选曾位于 `/tmp/zc_chibi_clean_20261101/`；其生成链完整结束，rig 为 85 个部件、26 个动作，`check_assets.py` 检查 1410 项、40 项失败。2026-11-01 交接核对时该临时目录已不存在，完整原始 JSON 报告也不可访问；失败明细已从运行输出抄录到 [`asset_qa_clean_failure_summary_2026-11-01.md`](asset_qa_clean_failure_summary_2026-11-01.md)。该 WIP 进度及所需参考已提交到当前分支，但提交不代表 QA 通过或接入生产。

候选贴图、rig 均未接入生产。本候选未做 C 引擎目视验收。所有失败项清零、缺件来源补正、短/长发/双马尾/兜帽组合与关键动作矩阵通过前，不得接入生产。

## 本轮实现及验证

- 重建保留 Chibi `body_full` 几何锁、仓库原有 Chibi `sprites/attach_parts.json` 的 11 项与 `rebuild_parts.sh` 的 Chibi 附件/衣柜跳过保护；没有把 Teen 附件生成导入 Chibi，也没有用 Teen 参考图补缺。
- `tools/fill_seam_holes.py` 改为只缓存缩放后切件的局部 RGBA，并在合成时裁剪 ROI，避免逐部件缓存整张 567×1292 画布。旧/新实现对 101 个 rig 部件的层图 RGBA、alpha 遮罩及 ±12 px 摆动逐像素一致；28 个 pose 合成的 alpha mask 无差异，量化 RGB 最大差 1。隔离全链中该步骤成功结束（约 199 秒）。
- 优化已移入仓库工具，新增 `tests/test_fill_seam_memory.py` 与 `make asset-tool-test`；`PYTHON_IMG=/tmp/zc_chibi_work_env/bin/python make -s asset-tool-test` 通过。`git diff --check` 与 `python3 tools/roadmap_status.py` 通过；ROADMAP/TASKS 计数已对齐。
- 本轮用户选择了双马尾 Live2D Chibi 参考选项 2，图已保存为 `reference_generated/chibi_twin_tails_live2d_v2.png`。目视：恰好两束、两个清楚的发束根、发色和服装与角色参考一致；但头发与尾巴体积偏大/偏蓬，整体头身略偏幼圆，须作为概念目标而非生产素材。截图 25/26/27 仍是负例。
- 注意：选项生成工具重置了其输出父目录和 `/tmp` 的部分临时内容；已从上传暂存区恢复 image-23 至 image-27 原图。旧的已选短/长概念图文件以及原始 `/tmp` QA JSON 本轮不可访问；已据日志保留失败摘要。后续生成选项必须写入独立空目录，再手工归档，避免影响其他证据。

## 40 项失败概况

逐项判据及测量值见 failure summary。主要失败：色卡 5 项，`armpit_mask` 空；静止合成少 407 px；躯干新洞 20,259 px、头发摆动洞 341/250 px、腕洞 99/100 px、裙摆接缝洞 70/73 px；鞋口抬高 73/74 px（目标 30）；袖片夹带夹克白；张嘴无牙且越过下巴；闭眼接缝色差约 48（上限 12）；摸头区域未覆盖脸，腮红位于透明区；发型接管/配色、手垫和 mouth mask 真伪检查未过。

重建日志另报告缺少 16 项 Chibi 挂件切件：`hair_sidelong_l/r`、`hair_crown_twin/pony/long`、`hood_up_twin/pony/long`、`hair_hood_twin/pony/pony_side/long`、`hair_sweep_twin_l/r`、`hair_sweep_pony_l/r`。未有正确来源时，不能用 Teen 图生成。

## 新增手型要求（2026-11-01，T67.69）

用户要求同时保留此前选定的小巧手与本轮红圈标出的手套感/连袖感手型。截图已归档至 `reference_generated/chibi_hand_mitten_user_marked_2026-11-01.jpg`；双手型隔离契约见 `hand_style_variants_2026-11-01.json`。只读核对发现现有 Chibi rig 只有 `seg_arm_l/r`，无 `hand_*` 独立部件；Teen 的 hand_parts 不能替代 Chibi 来源。后续需在 Chibi 设定稿上确认腕根/袖口，再在隔离候选生成两套左右手件、实现独立 `hand_style` 切换，并目视实际 C 引擎中比例、袖口遮挡/连续性和动作表现。该要求尚未实现或验收，不是生产资产。

## 下一步（按依赖顺序）

1. 使用 image-24 作为 Live2D Chibi 比例/风格锚点、项目设定稿保持身份；保留已选短/长参考记录，并为双马尾/高马尾/兜帽关系准备 Chibi 专用来源。逐图目视检查比例、发束数量/根部、帽兜关系、服装与整体风格，汇报优缺点。错误参考 image-25/26/27 只能记为负例。
2. 以通过目视的同源 Chibi 全身图切出 crown/back/side/sweep/hood parts；检查 ROI 不夹带身体、袖口或手，并重算配准与调色。以 Chibi 设定稿复核腕根/袖口，隔离生成 `hand_l/r_small` 与 `hand_l/r_mitten` 两套部件及独立 `hand_style` 选择器；不得用 Teen 贴图替代。
3. 对照 failure summary 修复身体/关节底层几何、眼口/鞋/衣袖/腮红/触摸区与差分发型/手型，不放宽 QA 阈值；建立全新隔离候选重跑全链，重新留存原始 JSON 与日志。
4. 要求资产 QA 零失败、零缺件警告后，用实际 C 引擎验收短/长发/双马尾与兜帽组合，以及默认、blink/closed/wide、摸头、踮脚、挥手、比心/惊讶、裙摆/尾巴关键姿态；手型小巧/手套感两档均检查比例、腕口遮挡及袖口连续。全数通过后才讨论接入生产和提交。

## 历史候选（不要混算）

- `/tmp/zc_chibi_work_20261101/` 曾把 Teen 附件链引入 Chibi，清单从 11 变 27；`hair_hood_long` 源 ROI 带手和袖口，该路线作废。
- 最早隔离尝试在 `fill_seam_holes.py` 被系统终止，随后 1653 项中 41 项失败。
- `/tmp/zc_chibi_refit_20261101/` 有另一份 37 项失败记录，说明见本目录 `README.md`。这些结果与最新 40 项失败候选不混为一谈。
