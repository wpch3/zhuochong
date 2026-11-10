# CH-SLEEVE-01/02/03 逐部件隐藏确认及新拓扑设计 (2026-11-06)

## 1. 目标与根因复盘
- **目标**：解决大角袖侧尖角、衣身口袋残露、肩参覆盖口袋（CH-SLEEVE-01/02/03）。
- **根因**：
  - 单层连续网格丢原前后层序且父子次序不匹配。
  - 遮挡定位表明小青三角是衣身口袋局部露出（CH-SLEEVE-02）。
  - 肩参覆盖中立不改像素但目标青角消失，右肩 -1/肘 +1/body +1 时口袋被整段抹掉（CH-SLEEVE-03）。
  - 内部研究文档（`../CHIBI_OCCLUSION_FOLLOWUP_2026-11-06.md`）记录了“完整背层与前层渐进交接试验”失败（内侧青色三角仍可见，435 像素差）。
  - Live2D Part Palette（绘制顺序决定遮挡）提示层序是关键。

## 2. 设计方案：逐部件隐藏确认及新拓扑设计 (Component Hiding & New Topology)
### 2.1 逐部件隐藏确认 (Component Hiding Verification)
- **确认逻辑**：
  - **分离衣身前片/袖轮廓/权重变形**：通过隐藏特定部件（Arm, Forearm, Body, Pocket）来定位尖角来源。
  - **工具支持**：使用 `tools/capture_chibi_body_joint_matrix.py` 采集 33 身体叠关节及 48 混合固定帧，逐帧隐藏确认。
  - **验证点**：
    - 隐藏 `arm_l`：尖角是否消失？（若消失，则源于上袖）
    - 隐藏 `forearm_l`：尖角是否消失？（若消失，则源于前袖）
    - 隐藏 `body`：口袋是否消失？（若消失，则源于衣身）
    - 隐藏 `pocket`：尖角是否消失？（若消失，则源于口袋残露）
- **记录**：将确认结果记录至 `tracking/CH-SLEEVE_COMPONENT_HIDING_VERIFICATION_2026-11-06.json`（或类似文件）。

### 2.2 新拓扑设计 (New Topology Design)
- **拓扑结构**：
  - **分离衣身前片与袖轮廓**：将衣身前片（Body Front）与袖轮廓（Sleeve Outline）分离，避免单层连续网格导致的层序丢失。
  - **权重变形调整**：重新设计权重变形（Weight Deformation），确保肩参（ParamArm/Elbow/Wrist）变化时，口袋与袖侧不发生错误遮挡。
  - **补画接缝**：在衣身口袋与袖侧交界处设计“补画接缝”（Patch Seam），确保在旋转极值时无尖角露出。
  - **父子次序匹配**：确保父子组（Parent-Child Group）次序与绘制顺序（Part Palette）一致。
- **独立层序/遮罩**：
  - **层序**：`Body (Base) > Pocket (Patch) > Sleeve Backing (Base) > Sleeve Front (Patch) > Arm/Forearm (Base)`。
  - **遮罩**：配置“袖侧遮罩”（Sleeve Side Mask），仅在肩参/肘参/腕参特定范围内激活，防止口袋被抹掉。

### 2.3 独立层序/遮罩实现 (Implementation)
- **引擎补丁**：
  - 在 `experiments/live2d_chibi_morph_study/rotation_aa/engine.patch` 基础上，增加“袖侧层序优先”逻辑。
  - 修改 `zrig.c` 中的 `draw_impl`，识别“袖侧补画层”标签，并确保在肩参/肘参/腕参变化时优先绘制。
- **工具链支持**：
  - 更新 `tools/rig_editor/`，支持“袖侧补画层”的创建与编辑。
  - 更新 `tools/zrig_project.py`，支持导出“袖侧补画层”配置。

## 3. 验证策略 (Verification Strategy)
### 3.1 组合检查 (Combination Check)
- **肩肘腕角度 (Shoulder/Elbow/Wrist Angle)**：
  - 扩大检查范围：0-360° 连续（如 `ParamArmL/R`, `ParamElbowL/R`, `ParamWristL/R`）。
  - 重点检查：口袋残露与袖侧尖角最严重的姿势（如 `ParamArmL=-1, ParamElbowL=-1, ParamWristL=-1, ParamMotionDrive=-1, ParamBreath=1`）。
- **全部手指混合/连续组合 (All Finger Mix/Continuous Combination)**：
  - 检查 1024 端点及混合矩阵下的袖侧表现。
  - 重点检查：袖侧尖角是否消失，口袋是否完整。

### 3.2 视觉验收 (Visual Acceptance)
- **本人目视放大图**：
  - 确认袖侧无尖角、口袋无残露、层序正确。
  - 确认补画接缝平滑，不同拓扑清晰。
- **真实 C 采样**：
  - 使用 `tools/capture_chibi_body_joint_matrix.py` 采集 33 身体叠关节。
  - 使用 `tools/capture_chibi_visual_matrix.py` 采集混合矩阵。
  - 对比基线（Baseline）与候选（Candidate）的视觉差异。

## 4. 执行步骤 (Execution Steps)
1. **逐部件隐藏确认**：
   - 在 `tools/rig_editor/` 中实现隐藏功能，并采集确认数据。
2. **设计拓扑 ArtMesh**：
   - 创建“分离衣身前片”、“袖轮廓”、“补画接缝”网格。
   - 配置权重变形与父子次序。
3. **更新引擎补丁**：
   - 修改 `experiments/live2d_chibi_morph_study/rotation_aa/engine.patch`，增加“袖侧层序优先”逻辑。
4. **构建与采集**：
   - 构建独立二进制 `build/zhuochong_rotation_aa_experiment`。
   - 采集 33 身体叠关节及混合矩阵。
5. **目视检查与记录**：
   - 检查 `build/chibi-rotation-aa-sleeve` 等目录下的视觉文件。
   - 记录结果至 `tracking/CHIBI_CONTINUOUS_REPAIR_AND_TOOLCHAIN_2026-11-06.md`。
6. **推送仓库**：
   - 提交并推送所有变更至分支 `arena/05bac0a6-zhuochong`。

## 5. 注意事项 (Notes)
- **不请求真机验收**：在视觉通过前，不进行真机验收。
- **资料留存**：所有失败证据、provenance、报告必须推送仓库。
- **工具链安全**：`scripts/selfcheck_all.sh` 会清理 `build/`，需保护跟踪目录 `tracking/`。

---
*本设计参考 Live2D Part Palette（绘制顺序决定遮挡）及内部研究文档（`../CHIBI_OCCLUSION_FOLLOWUP_2026-11-06.md`）。*
