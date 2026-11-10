# CH-HAND-01 新被遮挡区补画设计 (2026-11-06)

## 1. 目标与根因复盘
- **目标**：解决交错指根融合/断离（CH-HAND-01/02/03）。
- **根因**：
  - 刚体平移/减角/固定根分片/高斯网格/连续指蹼均未解决指根脱开、悬线、融合、无独立深度或梳齿。
  - 隔离 C 动态指层排序导致阈值跳变。
  - 缺乏“新被遮挡区补画”及“独立层序/遮罩”的明确设计。
  - 共享接缝或不同拓扑未被证实。

## 2. 设计方案：新被遮挡区补画 (Overlapping Root Patch Design)
### 2.1 补画逻辑 (ArtMesh Overlap & Hidden Patch)
- **补画区域**：
  - 针对指根交错处（Root Base Intersection），在原 ArtMesh 之外新增“被遮挡区补画层”（Hidden Patch Layer）。
  - 补画层不参与常规参数驱动，仅在特定指根重叠阈值（如 `ParamFingerDepth` 或 `ParamFingerSlide` 超过 ±0.5）时，通过独立层序（Independent Layer Order）或遮罩（Mask）显现。
- **拓扑结构**：
  - **共享接缝 (Shared Seam)**：将相邻指根的 ArtMesh 顶点绑定（Glue）并设权重（Weight），确保在重叠时边缘平滑过渡，不产生断离。
  - **不同拓扑 (Distinct Topology)**：为每根手指设计独立的“根部补画网格”（Root Patch Mesh），与主网格分离，避免高斯场（Gaussian Field）导致的模糊融合。
  - **独立层序 (Independent Layer Order)**：
    - 采用 `zrig` 动态指层序（Dynamic Finger Layer Order）隔离补丁，但不再依赖阈值跳变，而是通过“补画层优先”策略（Patch Layer Priority）确保补画层在重叠时始终位于主网格之上或之下（视视觉需求而定）。
    - 明确层序：`Thumb (Base) > Index (Patch) > Middle (Patch) > Ring (Patch) > Pinky (Patch) > Palm (Base)`。

### 2.2 遮罩与权重配置 (Mask & Weight Configuration)
- **遮罩 (Mask)**：
  - 为补画层配置“根部遮罩”（Root Mask），仅在指根重叠区域激活。
  - 遮罩形状：根据 Live2D Glue 概念，设计为“V”形或“U”形，覆盖指根交错的缝隙。
- **权重 (Weight)**：
  - 顶点权重：指根顶点绑定至“根部补画层”与“主网格”的双重权重（Dual Weight），确保在参数变化时，补画层与主网格同步变形，不产生断裂。
  - 权重分布：指根中心权重 1.0（补画层），边缘权重 0.0（主网格），平滑过渡。

### 2.3 独立层序/遮罩实现 (Implementation)
- **引擎补丁 (Engine Patch)**：
  - 在 `experiments/live2d_chibi_morph_study/rotation_aa/engine.patch` 基础上，增加“补画层优先”逻辑。
  - 修改 `zrig.c` 中的 `draw_impl` 或 `draw_tri`，识别“补画层”标签，并优先绘制。
- **工具链支持 (Toolchain Support)**：
  - 更新 `tools/rig_editor/` 组/网格拖动功能，支持“补画层”的创建与编辑。
  - 更新 `tools/zrig_project.py`，支持导出“补画层”配置。

## 3. 验证策略 (Verification Strategy)
### 3.1 组合检查 (Combination Check)
- **肩肘腕角度 (Shoulder/Elbow/Wrist Angle)**：
  - 扩大检查范围：0-360° 连续（如 `ParamArmL/R`, `ParamElbowL/R`, `ParamWristL/R`）。
  - 重点检查：指根重叠最严重的姿势（如 `ParamArmL=-1, ParamElbowL=-1, ParamWristL=-1`）。
- **表情叠眨眼 (Expression + Blink)**：
  - 检查指根补画层在表情（Smile/Pain）与眨眼（Blink）叠加时的稳定性。
- **全部手指混合/连续组合 (All Finger Mix/Continuous Combination)**：
  - 检查 1024 端点及混合矩阵（48 固定 + 20 混合）下的补画层表现。
  - 重点检查：指根融合是否消失，断离是否修复。

### 3.2 视觉验收 (Visual Acceptance)
- **本人目视放大图**：
  - 确认指根补画层在所有组合姿势下均无融合、断离、悬线、梳齿。
  - 确认共享接缝平滑，不同拓扑清晰。
- **真实 C 采样**：
  - 使用 `tools/capture_chibi_finger_endpoints.py` 采集 1024 端点。
  - 使用 `tools/capture_chibi_visual_matrix.py` 采集混合矩阵。
  - 对比基线（Baseline）与候选（Candidate）的视觉差异。

## 4. 执行步骤 (Execution Steps)
1. **设计补画层 ArtMesh**：
   - 在 `tools/rig_editor/` 中创建“根部补画层”网格。
   - 配置共享接缝顶点绑定与权重。
2. **更新引擎补丁**：
   - 修改 `experiments/live2d_chibi_morph_study/rotation_aa/engine.patch`，增加“补画层优先”逻辑。
3. **构建与采集**：
   - 构建独立二进制 `build/zhuochong_rotation_aa_experiment`。
   - 采集 1024 端点及混合矩阵。
4. **目视检查与记录**：
   - 检查 `build/chibi-rotation-aa-endpoints`、`chibi-rotation-aa-matrix` 等目录下的视觉文件。
   - 记录结果至 `tracking/CHIBI_CONTINUOUS_REPAIR_AND_TOOLCHAIN_2026-11-06.md`。
5. **推送仓库**：
   - 提交并推送所有变更至分支 `arena/05bac0a6-zhuochong`。

## 5. 注意事项 (Notes)
- **不请求真机验收**：在视觉通过前，不进行真机验收。
- **资料留存**：所有失败证据、provenance、报告必须推送仓库。
- **工具链安全**：`scripts/selfcheck_all.sh` 会清理 `build/`，需保护跟踪目录 `tracking/`。

---
*本设计参考 Live2D Glue（重合 ArtMesh 顶点绑定与权重）及内部研究文档（`../CHIBI_WEIGHTED_STUDIES_2026-11-06.md`、`../CHIBI_CONTOUR_AND_LAYER_STUDIES_2026-11-06.md`）。*
