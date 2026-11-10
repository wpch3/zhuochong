# 旋转采样隔离实验结果与复现文档 (2026-11-06)

## 1. 实验目的
隔离 C 旋转采样实验，以逆变换最大奇异值选择 mip，验证近 45° 纯旋转触发 `>=1.4` 半分辨率 mip 的模糊问题。

## 2. 实验配置
- 隔离补丁：`experiments/live2d_chibi_morph_study/rotation_aa/engine.patch`
- 独立二进制：`build/zhuochong_rotation_aa_experiment`
- 采样范围：124 帧双引擎扫描（scale 1, .55, .35）
- 探针：`tests/rotation_aa_experiment_probe.c`、`tests/test_chibi_rotation_sampling_probe.py`、`tools/capture_chibi_rotation_sampling_probe.py`

## 3. 关键结果
- **技术测试通过**：`make test-core-rotation-aa` (2707/0)；`make test-chibi-rotation-aa-experiment` 通过。
- **视觉改善**：
  - 基线左手 wrist `-.32→-.30` 绝对差总和 41,666；实验 11,174。
  - 基线右手 `-.50→-.48` 绝对差总和 38,181；实验 10,165。
  - scale `.55` 基线最大 15,385/14,246；实验最大 2,218/2,210。
  - scale `.35` 基线最大 9,567/7,996；实验最大 840/812。
  - 实验版手指更清楚且去掉突变；连续采样改善明显。
- **未解决问题**：
  - 手指交错根部拓扑/遮挡（CH-HAND-01）仍需检查修复。
  - 痛眼近闭灰影/楔形（CH-EYE-02/04）仍存在。
  - 袖侧口袋残角（CH-SLEEVE-02）仍存在。

## 4. 跟踪目录
所有视觉文件、报告和 provenance 已保存至 `tracking/rotation_aa_20261106/`：
- 视觉对照：`rotation_aa_{L,R}_threshold.png`, `chibi-rotation-aa-comparison.png`, `rotation_aa_smallscale_compare.png`
- 扫描报告：`build/chibi-rotation-aa-sweep{,055,035}/report.json`
- Provenance：`provenance_baseline.json`, `provenance_candidate.json`, `provenance_eye.json`
- 姿态清单：`poses_baseline.json`, `poses_candidate.json`, `poses_endpoints.json`, `poses_matrix.json`, `poses_eye.json`

## 5. 复现步骤
1. 构建隔离实验：`make $(BUILD)/zhuochong_rotation_aa_experiment $(BUILD)/rotation_aa_experiment_probe`
2. 运行核心测试：`make test-core-rotation-aa`
3. 运行采样探针：`make test-chibi-rotation-aa-experiment`
4. 检查跟踪目录 `tracking/rotation_aa_20261106/` 确认文件完整。

## 6. 后续任务
- 持续推进真实 C 可编辑素材/遮挡工作流（动态编辑能力）。
- 修复三处视觉问题（指根融合、痛眼灰影、袖侧残角）。
- 扩大肩肘腕角度、表情叠眨眼、全部手指混合检查。
- 核查自制 Live2D 风格骨骼链接工具及完整任务流。
