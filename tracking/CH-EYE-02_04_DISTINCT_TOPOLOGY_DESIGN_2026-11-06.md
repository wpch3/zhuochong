# CH-EYE-02/04 不同拓扑尝试设计 (2026-11-06)

## 1. 目标与根因复盘
- **目标**：解决痛眼近闭灰影/楔形及单网格不保证单轮廓（CH-EYE-02/04）。
- **根因**：
  - 不同形状眼线交叉淡化、同源双闭线+pain 优先、推迟变形仍有非重合双线。
  - 持续睫线复制或窄线分支仍粗重或碎裂。
  - 单网格烘入同一睫线并压合仍有灰线/断续。
  - 官方来源（Live2D Blink 设置与表情教程）仅为概念参考，Reddit 讨论（Clipping Mask 边缘白边与层级问题）提示层级嵌套错误导致双重剪切。
  - 内部研究文档（`../CHIBI_OCCLUSION_FOLLOWUP_2026-11-06.md`）记录了“不断裂的睫线 + 痛眼分支试验”失败（完整复制双线粗重、窄线细碎模糊）。

## 2. 设计方案：不同拓扑尝试 (Distinct Topology Design)
### 2.1 持续可见睫线拓扑 (Continuous Visible Lid Topology)
- **拓扑结构**：
  - **单线连续性**：将移动睫线（Mobile Lid）设计为从睁眼形（Open Shape）到闭眼形（Closed Shape）的连续单线（Single Continuous Line），不进行末段交叉透明。
  - **开度网格驱动**：以开度网格（Aperture Mesh）从睁到闭驱动，确保中间态（Intermediate State）无断裂。
  - **顶点绑定**：将睫线顶点绑定至 `ParamEyeLOpen`/`ParamEyeROpen`，并确保在 `eye_keyform_effective_blink` 标签下读取最终闭合量补数。
- **补画与遮罩**：
  - **独立层序**：将睫线层置于眼白层之上，痛眼分支层置于睫线层之下（或根据视觉需求调整）。
  - **遮罩**：配置“眼线遮罩”（Lid Mask），仅在痛眼形态（Pain Shape）激活时，通过遮罩显现痛眼分支，避免交叉淡化。

### 2.2 痛眼分支拓扑 (Pain Branch Topology)
- **拓扑结构**：
  - **分叉原画**：不再复制主线，而是设计可配准的单线/分叉原画拓扑（Alignable Single/Branch Original Art）。
  - **连续接缝**：确保痛眼分支与主睫线在接缝处（Seam）平滑过渡，不产生楔形（Wedge Shape）或灰影（Ghost Shadow）。
  - **权重配置**：痛眼分支顶点权重仅在 `ParamPain` 激活时生效，其余状态权重为 0。
- **验证策略**：
  - **表情叠眨眼**：检查 smile+pain+blink 组合下的拓扑稳定性。
  - **近闭眼**：检查 0.85–1.0 闭合量下的单轮廓表现。
  - **左右单眼/Gaze**：检查左右眼独立及视线追踪下的拓扑一致性。

### 2.3 独立层序/遮罩实现 (Implementation)
- **引擎补丁**：
  - 在 `experiments/live2d_chibi_morph_study/rotation_aa/engine.patch` 基础上，增加“痛眼分支优先”逻辑（Pain Branch Priority），但不再依赖透明度交叉。
  - 修改 `zrig.c` 中的 `draw_impl`，识别“痛眼分支”标签，并确保在 pain 激活时优先绘制。
- **工具链支持**：
  - 更新 `tools/rig_editor/`，支持“痛眼分支”拓扑的创建与编辑。
  - 更新 `tools/zrig_project.py`，支持导出“痛眼分支”配置。

## 3. 验证策略 (Verification Strategy)
### 3.1 组合检查 (Combination Check)
- **表情叠眨眼 (Expression + Blink)**：
  - 扩大检查范围：smile+pain+blink 组合（0/.5/1 × blink 0/.5/1 与 .85/.925/1）。
  - 重点检查：痛眼分支在不同表情下的稳定性。
- **近闭眼 (Near-Closed Eye)**：
  - 检查 0.85–1.0 闭合量下的单轮廓表现。
  - 重点检查：灰影（Ghost Shadow）与楔形（Wedge Shape）是否消失。
- **左右单眼/Gaze (Single Eye/Gaze)**：
  - 检查左右眼独立及视线追踪下的拓扑一致性。

### 3.2 视觉验收 (Visual Acceptance)
- **本人目视放大图**：
  - 确认睫线连续、无断裂、无灰影、无楔形。
  - 确认痛眼分支与主睫线平滑过渡。
- **真实 C 采样**：
  - 使用 `tools/capture_chibi_expression_mix.py` 采集 54 帧表情矩阵。
  - 使用 `tools/capture_chibi_visual_matrix.py` 采集近闭眼矩阵。
  - 对比基线（Baseline）与候选（Candidate）的视觉差异。

## 4. 执行步骤 (Execution Steps)
1. **设计拓扑 ArtMesh**：
   - 在 `tools/rig_editor/` 中创建“持续可见睫线”与“痛眼分支”网格。
   - 配置单线连续性与分叉原画拓扑。
2. **更新引擎补丁**：
   - 修改 `experiments/live2d_chibi_morph_study/rotation_aa/engine.patch`，增加“痛眼分支优先”逻辑。
3. **构建与采集**：
   - 构建独立二进制 `build/zhuochong_rotation_aa_experiment`。
   - 采集 54 帧表情矩阵及近闭眼矩阵。
4. **目视检查与记录**：
   - 检查 `build/chibi-rotation-aa-eye` 等目录下的视觉文件。
   - 记录结果至 `tracking/CHIBI_CONTINUOUS_REPAIR_AND_TOOLCHAIN_2026-11-06.md`。
5. **推送仓库**：
   - 提交并推送所有变更至分支 `arena/05bac0a6-zhuochong`。

## 5. 注意事项 (Notes)
- **不请求真机验收**：在视觉通过前，不进行真机验收。
- **资料留存**：所有失败证据、provenance、报告必须推送仓库。
- **工具链安全**：`scripts/selfcheck_all.sh` 会清理 `build/`，需保护跟踪目录 `tracking/`。

---
*本设计参考 Live2D Blink 设置与表情教程（仅为概念参考）、Reddit 讨论（Clipping Mask 边缘白边与层级问题）及内部研究文档（`../CHIBI_OCCLUSION_FOLLOWUP_2026-11-06.md`）。*
