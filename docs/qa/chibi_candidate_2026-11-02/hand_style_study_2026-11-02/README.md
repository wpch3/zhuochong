# Chibi `small` / `mitten` 手型参考板（阶段 WIP）

**状态：研究草稿，不是生产贴图、拆件或引擎验收。** 本阶段仅推进 T70.2 的 Chibi 来源与腕口几何研究；生产 `sprites/`、`rig.json`、生成器和 C 引擎均未修改。

## 本轮做了什么

- 从 Chibi 自有 `characters/xiaoxun/design/design_sheet_chibi.png` 的已锁几何 `[628,101,1416,1891] → 567×1292` 建立 wrist crop 映射；source sheet SHA-256：`496dc41f935d35619da35f6a3a2b8408aeb2646847ac0807334c5a466be5097c`。
- `small_left_source.png` / `small_right_source.png` 是现有 Chibi `body_full.png` 手腕 ROI 原样裁取，只作参考放大，未改原像素。
- `mitten_left_concept.png` / `mitten_right_concept.png` 是脚本绘制的几何轮廓示意，袖口取自 Chibi 源图。它们**不符合“手必须用原画件做部件，禁程序化画手”的既有铁律**，本轮明确拒绝其作为手部美术；仅隔离留存，帮助讨论一体圆掌的占位范围、袖口插入与手腕尺寸。不得作为生产贴图、正式美术参考或 rig 输入。
- `body_full_mitten_preview_wip.png` 和 `hand_style_board_wip.png` 仅用于上下文/几何观察。缩略身份、服装和身体比例未改；mitten 示例明显缺少 Chibi 原画的真实边缘线稿、网点/渐变和暖色阴影，**不是通过的设计稿**。
- 另对两张单手局部进行过一次图像生成测试：`candidate_mitten_left.png` / `candidate_mitten_right.png`。**明确拒绝**：模型把手放大并改了袖口条纹/线稿，不能保持几何与风格；仅留作失败方式记录，绝不进入贴图、正式参考板或 rig。

## 验收边界与下一步

1. 当前资料只证明 source crop 的来源、几何映射和 `small` 原像素；**mitten 原创 Chibi 手件仍然缺失**。不得把脚本草图称为“已画好 mitten”。
2. 新 mitten 必须以合规 Chibi 原画为视觉真值，并保留原画级边缘线稿、色阶/暖影与身份特征；先取得可审阅的画稿，再做左右腕根、袖口条纹/遮挡、1×/@2× 对位和透明 ROI 检查。不能靠给平涂草图补几笔就宣称符合原画。
3. 之后才在隔离 rig 中拆 `hand_l/r_small` 与 `hand_l/r_mitten`，以独立 `hand_style` 选择；不混入 wrist 或 gesture 轴。实际 C 引擎需验证两方向切换、无重影/空洞/尺寸跳变，并检查动作/袖口组合。
4. 当前 full-body Chibi、眼口、发型/兜帽、服装遮挡及动作矩阵仍未通过；本次几何研究不能关闭 A64 / T70.2–T70.4，也不能被表述为整个 Chibi 完工。

## 文件

- `build_hand_style_study.py`：只在本 QA 目录生成来源裁片和明确被拒绝的几何示意，不改生产资产。
- `source_crop_manifest.json`、`study_metrics.json`：来源映射、源图/产物 SHA、像素尺寸与明确限制。
- `SHA256SUMS.txt`：本目录文件完整性清单（不含清单本身）。
