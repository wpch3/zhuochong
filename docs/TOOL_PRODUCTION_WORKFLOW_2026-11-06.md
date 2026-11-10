# 工具链、资料、工作流与视觉验收 (2026-11-06)

## 1. 工具链与资料
- **隔离实验补丁**：`experiments/live2d_chibi_morph_study/rotation_aa/engine.patch`
- **独立二进制**：`build/zhuochong_rotation_aa_experiment`
- **采样探针**：`tests/rotation_aa_experiment_probe.c`, `tests/test_chibi_rotation_sampling_probe.py`, `tools/capture_chibi_rotation_sampling_probe.py`
- **编辑器动态能力**：`tools/rig_editor/` (已更新父子连线/枢轴拖动)、`tests/test_rig_editor*`、`web/test.html`
- **项目打包**：`tools/zrig_project.py` (v1)
- **跟踪目录**：`tracking/rotation_aa_20261106/` (视觉文件、报告、provenance、姿态清单)

## 2. 工作流
1. **构建与测试**：
   - `make test-core-rotation-aa` (2707/0)
   - `make test-chibi-rotation-aa-experiment`
   - `make test-rig-editor test-zrig-project`
2. **采集与保存**：
   - 运行采样探针采集 124 帧双引擎扫描（scale 1, .55, .35）
   - 保存视觉对照、报告、provenance 至跟踪目录
   - 更新错误索引 `docs/memory/ERROR_INDEX.md`
3. **编辑器动态编辑**：
   - 载入模型素材文件夹
   - 编辑部件位置、组连接、参数绑定、网格关键形态
   - 导出 `.zproj` v1 工程快照
   - 真实 Chromium 浏览器端到端测试（已通过）
4. **视觉验收**：
   - 目视对照基线/候选（手指更清楚、突变去掉）
   - 确认三处问题未完全解决（指根融合、痛眼灰影、袖侧残角）
   - 不在视觉通过前请求真机验收

## 3. 关键结果
- **技术测试**：全部通过（2707/0）
- **视觉改善**：
  - scale 1: 基线 41,666/38,181 → 实验 11,174/10,165
  - scale .55: 基线 15,385/14,246 → 实验 2,218/2,210
  - scale .35: 基线 9,567/7,996 → 实验 840/812
- **未解决问题**：
  - CH-HAND-01: 指根融合/断离
  - CH-EYE-02/04: 痛眼灰影/楔形
  - CH-SLEEVE-02: 袖侧口袋残角

## 4. 后续任务
- 扩大肩肘腕角度、表情叠眨眼、全部手指混合检查
- 核查自制 Live2D 风格骨骼链接工具及完整任务流
- 持续推进真实 C 可编辑素材/遮挡工作流
- 视觉通过后请求真机验收

## 5. 提交与推送
- 提交所有变更至分支 `arena/05bac0a6-zhuochong`
- 推送至远端并验证 SHA
