# Chibi C 帧眼缘残留坐标配准（证据归档，未修复）

> **后续状态更新（2026-11-02）：** 子目录 `c_engine_gapfill_followup_2026-11-02/` 已从固定 C 帧 sockets 拟合实际 head-group affine，并映射到 `seg_head@2x` texel；已确认左右侧发在四个候选屏幕窗内 alpha=0。三块隔离补片中右侧两块局部 C 像素清除，左黑线仍残 1px；左灰线并非活动高分辨率透明缺口。完整结论、QA 限制及资产 SHA 见该子目录 README。上一份正文记录的是配准尚未完成时的历史状态，仍保留作时间线，不代表当前状态。生产贴图与 rig 仍未修改。

日期：2026-11-02  
分支：`arena/aaf1408c-zhuochong`  
仓库 HEAD（开始本次归档时）：`6d42dc4f9e2ac6bde241c5ca080c927b131988f1`  
候选：隔离 2px lash-pad 构建 `/tmp/chibi-candidate-20261102`，不是生产素材。生产 `characters/xiaoxun/forms/chibi/` 未修改。

## 结论（本轮实际观察）

1. 在真实 C 引擎截图里，眼周几处短深色/灰色线段可见；把 `seg_head` 单件隔离后，相同线段仍在。`eye_l/r_base` 与 `eye_l/r_lash` 单件隔离帧不含这些线段。当前最稳妥的**层级归属**是它们来自 `seg_head` 的画面贡献（而不是眼白底或上眼线件）。
2. 这仍不等于已经知道应删除哪些 `seg_head` 源像素。右侧上沿黑线、侧发边缘和头部原图的轮廓在数像素范围内相接；目前候选 ROI 还包含可能合法的眼线/头发细节。未建立可安全推广的 carve/alpha 掩膜，未改生成器、生产 PNG 或 rig。
3. 完成了 rig-space 布局配准：候选 `seg_head.png` 为 567×644，rig 部件原点 `[140,68]`；眼件 patch 在 body 坐标分别从 `[1,399]`、`[298,399]` 开始，与 rig 的 `eye_l_base=[141,467]`、`eye_r_base=[438,467]` 对齐。这验证的是静态部件布局，不是任一 C 帧上逐像素恒等的 `screen = source + pos`。
4. 原始探针截图中的屏幕坐标直接记录在 `observed_features.json`。C 帧的 head group 有运行时表达式/姿态；即使时钟冻结、physics/ambient 关闭，`ParamAngleX` 仍报告有效表达式约 `1.7798`。所以不能把 rig 原点简单减掉，伪称已得到精确源像素坐标。下一步需要在同一冻结姿态下拿到实际 group transform，或做可复核的像素注册，再与 aperture/socket/lash/sidehair 掩膜逐像素求交。

## 真实 C 引擎目视证据

- `c_engine_full_scale1.png`：848×1360 C 帧、Chibi、scale 1.0。
- `isolate_seg_head.png`：真实 C `/api/part` 单件隔离帧。
- `isolate_eye_*`、`isolate_hair_side_*`：眼底、上眼线与侧发隔离对照。
- `candidate_dark_pixel_crosscheck.png`：按屏幕坐标放大标出候选深色/灰色小窗；框只是观察 ROI，不是修复 mask。
- `eye_outer_corner_canvas_grid.png`：C 画布坐标每 10px 网格。
- `l/r_coordinate_registered_panels.png`：全画面、`seg_head` 单件与源件坐标上的 aperture/lash 可视化。
- `fixed_pose_*`：再次在冻结 `t=0` 状态采集的同一帧全身/单件对照；`fixed_pose_state.json` 保存当时 API 状态。AngleZ 已抵消到 0，但 AngleX 的 builtin expression 仍非零，故不能称为完全中性头姿。

本轮本人查看了完整脸部坐标网格与双侧放大交叉图。线段确实留在隔离后的 `seg_head` 画面；没有凭这些截图把相邻发丝、眼线或脸缘整片擦掉。候选黑色像素阈值与视觉窗口详见 `observed_features.json`，阈值框只用于定位。

## 可复核坐标与边界

`observed_features.json` 把两类坐标分开：

- **rig/source 布局坐标**：`seg_head` 和眼件的 rig `pos`、PNG 大小、patch 的 body 原点；
- **截图屏幕坐标**：固定图像上的可疑小窗及阈值运行长度。

两者目前没有被合并成一个“精确源像素 mask”。在完全证明图层/姿态变换与像素来源前，不能把某一阈值连通域当成待删区域。旧的 1→2px lash-pad、alpha-restore 与 offline eye-protect 仍按父目录记录的结果拒绝；本轮没有重新宣称 QA 改善。

## 运行态与边界

C 预览使用隔离候选，读取 `/api/info.json` 验证 form=`chibi`、画布 848×1360、scale=1；初始探针关闭 physics/ambient、冻结在 `t=0`。后续复拍先重置参数，再把 AngleZ 抵消并冻结；`fixed_pose_state.json` 保留具体状态，显示 AngleX expression 仍为非零。部件隔离完成后已恢复 `/api/part?all=1`，预览应保持全身显示。

不把 `.cache` 或 `/tmp` 当归档来源：本目录已复制必要截图、复拍帧、方法和观察数据；上层 `SHA256SUMS.txt` 包含本子目录文件的摘要。

## 下一步（仍未完成）

1. 在冻结的确定性姿态中记录 head group 的真实变换（包括 builtin look/AngleX），再配准同帧 C 截图与 `seg_head` 原始纹理；不依赖静态 rig 原点猜测源像素。
2. 把候选截图窗口映射到 `seg_head` 源像素，逐点检查与左右 `carve`、socket、lash、侧发/头缘的交并关系，并通过原图颜色与 alpha 来源追踪。
3. 只做最窄隔离候选，回到真实 C 引擎全脸/全身 A/B 目视；不通过就保留拒绝记录，不接入生产。其余 Chibi 全身拆件、手型/手势、差分发型/兜帽、服装遮挡和动作组合验收仍未完成。
