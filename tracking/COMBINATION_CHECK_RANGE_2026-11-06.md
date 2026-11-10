# 肩肘腕角度/表情叠眨眼/手指混合组合检查范围 (2026-11-06)

## 1. 肩肘腕角度组合检查 (Shoulder/Elbow/Wrist Angle Combination)
### 1.1 检查范围 (0-360° 连续)
- **参数维度**：
  - `ParamArmL/R` (肩): -1.0 到 1.0（对应 0-360° 连续映射，步长 0.05，共 41 步）
  - `ParamElbowL/R` (肘): -1.0 到 1.0（对应 0-360° 连续映射，步长 0.05，共 41 步）
  - `ParamWristL/R` (腕): -1.0 到 1.0（对应 0-360° 连续映射，步长 0.05，共 41 步）
  - `ParamMotionDrive` (动作驱动): -1.0 到 1.0（步长 0.1，共 21 步）
  - `ParamBreath` (呼吸): -1.0 到 1.0（步长 0.5，共 5 步）
- **组合矩阵**：
  - 基础组合：肩 × 肘 × 腕 = 41 × 41 × 41 = 68,921 种姿势（每侧）
  - 扩展组合（含 MotionDrive/Breath）：68,921 × 21 × 5 = 7,236,705 种姿势（每侧）
  - **实际采样策略**：
    - 采用 Gray code 或随机采样，覆盖关键临界点（如 -1, -0.5, 0, 0.5, 1）及中间态。
    - 重点检查：CH-SLEEVE-01/02/03 尖角最严重的姿势（如 `ParamArmL=-1, ParamElbowL=-1, ParamWristL=-1, ParamMotionDrive=-1, ParamBreath=1`）。
    - 采样量：每侧 1,024 种关键姿势（对应 1,024 端点混合矩阵）。
- **验证点**：
  - **CH-SLEEVE-01/02/03**：袖侧尖角、衣身口袋残露、肩参覆盖口袋是否消失。
  - **CH-HAND-01/02/03**：指根融合/断离是否在所有角度下修复。
  - **CH-EYE-02/04**：痛眼灰影/楔形是否在所有角度下修复（结合表情）。

### 1.2 采样工具与路径
- **工具**：`tools/capture_chibi_body_joint_matrix.py`（更新为支持 0-360° 连续采样）
- **输出路径**：`build/chibi-rotation-aa-sweep-continuous/`（每侧 1,024 帧）
- **Provenance**：记录 rig、素材、二进制 SHA（`tools/chibi_capture_provenance.py`）

## 2. 表情叠眨眼组合检查 (Expression + Blink Combination)
### 2.1 检查范围
- **表情参数**：
  - `ParamSmileL/R`: 0, 0.5, 1.0（3 步）
  - `ParamPainL/R`: 0, 0.5, 1.0（3 步）
  - `ParamWinkL/R`: 0, 0.5, 1.0（3 步）
- **眨眼参数**：
  - `ParamEyeLOpen/ROpen`: 0, 0.2, 0.3, 0.5, 0.65, 0.7, 0.85, 0.925, 1.0（9 步）
- **组合矩阵**：
  - 基础组合：Smile × Pain × Wink × Blink = 3 × 3 × 3 × 9 = 243 种表情（每侧）
  - **实际采样策略**：
    - 重点检查：CH-EYE-02/04 灰影/楔形最严重的组合（如 Pain=1, Blink=0.85/0.925/1）。
    - 采样量：每侧 54 种关键表情（对应 `tracking/rotation_aa_20261106/poses_eye.json` 的扩展）。
- **验证点**：
  - **CH-EYE-02/04**：单轮廓连续性、痛眼分支平滑过渡、无灰影/楔形。
  - **CH-HAND-01/02/03**：表情叠加时指根是否受影响（如微笑导致指根融合）。
  - **CH-SLEEVE-01/02/03**：表情叠加时袖侧是否受影响（如呼吸导致口袋残露）。

### 2.2 采样工具与路径
- **工具**：`tools/capture_chibi_expression_mix.py`（更新为支持连续表情矩阵）
- **输出路径**：`build/chibi-rotation-aa-eye-continuous/`（每侧 54 帧）
- **Provenance**：记录 rig、素材、二进制 SHA。

## 3. 手指混合/连续组合检查 (All Finger Mix/Continuous Combination)
### 3.1 检查范围
- **手指参数**：
  - `ParamFingerLRing`, `ParamFingerLMiddle`, `ParamFingerLIndex`, `ParamFingerLPinky`, `ParamFingerLThumb`（每根手指 0-1，步长 0.05，共 21 步）
  - 左右手独立（共 10 根手指）
- **组合矩阵**：
  - 基础组合：10 根手指 × 21 步 = 210 种状态（理论上 21^10 种组合，实际采样关键组合）
  - **实际采样策略**：
    - 1,024 端点（Gray code 相邻只改一参，每帧校验十参）
    - 混合矩阵：48 固定 + 20 混合（对应 `tracking/rotation_aa_20261106/poses_matrix.json` 的扩展）
    - 重点检查：CH-HAND-01/02/03 指根融合/断离、CH-SLEEVE-01/02/03 袖侧尖角（手部动作导致）。
- **验证点**：
  - **CH-HAND-01/02/03**：指根补画层是否在所有手指组合下有效。
  - **CH-EYE-02/04**：手指动作是否导致眼线变形（如手遮眼）。
  - **CH-SLEEVE-01/02/03**：手指动作是否导致袖侧尖角（如手伸出导致口袋残露）。

### 3.2 采样工具与路径
- **工具**：`tools/capture_chibi_finger_endpoints.py`、`tools/capture_chibi_visual_matrix.py`
- **输出路径**：`build/chibi-rotation-aa-matrix-continuous/`（1,024 帧）
- **Provenance**：记录 rig、素材、二进制 SHA。

## 4. 执行步骤 (Execution Steps)
1. **更新采样工具**：
   - 修改 `tools/capture_chibi_body_joint_matrix.py`、`tools/capture_chibi_expression_mix.py`、`tools/capture_chibi_finger_endpoints.py`，支持上述组合范围。
2. **构建与采集**：
   - 构建独立二进制 `build/zhuochong_rotation_aa_experiment`。
   - 运行采样工具，生成 `build/chibi-rotation-aa-sweep-continuous/`、`build/chibi-rotation-aa-eye-continuous/`、`build/chibi-rotation-aa-matrix-continuous/`。
3. **目视检查与记录**：
   - 检查所有视觉文件，确认三处问题是否修复。
   - 记录结果至 `tracking/CHIBI_CONTINUOUS_REPAIR_AND_TOOLCHAIN_2026-11-06.md`。
4. **推送仓库**：
   - 提交并推送所有变更及 Provenance 至分支 `arena/05bac0a6-zhuochong`。

## 5. 注意事项 (Notes)
- **不请求真机验收**：在视觉通过前，不进行真机验收。
- **资料留存**：所有失败证据、provenance、报告必须推送仓库。
- **工具链安全**：`scripts/selfcheck_all.sh` 会清理 `build/`，需保护跟踪目录 `tracking/`。

---
*本范围设计基于内部研究文档（`../CHIBI_WEIGHTED_STUDIES_2026-11-06.md`、`../CHIBI_CONTOUR_AND_LAYER_STUDIES_2026-11-06.md`、`../CHIBI_OCCLUSION_FOLLOWUP_2026-11-06.md`）及用户要求（0-360° 连续、1024 端点、表情叠眨眼）。*
