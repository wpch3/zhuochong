# Chibi 外眼角 socket 限界试验（WIP，未接生产）

日期：2026-11-02
活动分支：`arena/aaf1408c-zhuochong`
候选来源：隔离目录 `/home/user/chibi-candidate-20261101`
仓库基线：开工时 `508f588`（工作树干净）
状态：**完整 27 步候选已重建并由真实 C 引擎复拍；画面左侧外眼角有改善，右侧仍见方块/短线残留；本人目视未通过，不进生产。**

## 目标与来源边界

本试验只针对 Chibi 眼角碎边候选根因，不覆盖整个 Chibi 的完成验收。继续以 Chibi 自有设计稿/源件和既有拆件管线为素材来源；用户 image-29 只供身份、比例和眼型观感对照，未直接裁切；没有借用 Teen 贴图；正式 `characters/xiaoxun/forms/chibi/sprites/` 与正式 `rig.json` 均未修改。

前一轮量出候选 `eye_*_socket.png` 有像素落在测得的源眼 aperture 之外（左 1,489 px、右 2,354 px）。这是 socket 扩张可能吸入眼外白/蓝色碎片的线索，不是先验确认的唯一根因。本轮在隔离版 `tools/make_eye_parts.py` 中把 Chibi `eye_color`、`interior`、`sock_m` 限定在 `aperture` 内，避免扩大可见 socket；完整增量在 `candidate_make_eye_parts.patch`。该 patch 与 2026-11-01 已归档的上睫毛 ROI 试验合并成候选工具差异；不表示这些改动已合入正式工具。

## 真正重建的依赖链

先前快速试验虽重生了眼件，却没有重跑依赖 `eye_parts.json` 的 `make_sidehair_parts.py`，所以 sidehair 的五官保护区仍是旧值。此次从 Chibi 设定稿起在隔离候选执行完整 `tools/rebuild_parts.sh xiaoxun chibi`（27 步），依序重建 sidehair、`seg_head`、眼线/脸部修补、@2× 贴图与 rig；随后重启项目 C 预览服务，切换到 Chibi、关闭自动动作并冻结时间，再抓实际渲染帧。完整 stdout/stderr 见 `full_rebuild_27_steps.log`。

正式 rig 确实使用 `eye_*_socket@2x.png` 及 `eye_*_lash_up@2x.png`；候选 rig 对应条目、socket 与 lash @2× 件均随本目录归档。不能用只重生 1×、未刷新 sidehair/@2×/rig 或未重启的画面评价本候选。

## 本人 C 引擎目视

- `engine_chibi_fullbody_after.png` 是隔离候选真实 C 引擎默认全身帧；`engine_face_zoom_after_5x.png` 是同帧脸部最近邻放大。
- `engine_face_before_after.png` 将上轮已归档的真实 C 引擎帧与本轮完整重建后的帧按相同窗口并排。可见两侧外眼角的大块碎边有所收敛，尤其画面左侧；但画面右侧仍留有黑色矩形短块/切口，局部仍不够干净。主弧改善不等于眼角通过。
- `engine_part_isolations.png` 是 C 引擎分层隔离：单独看新生成的 sidehair 是窄发片；隔离 `seg_head` 仍看得到少量眼缘/角部暗碎边。结合隐藏 lash、sidehair 或 head 的前轮实验，现阶段不能把残留简单归因于单个 lash 或单缕头发。后续重点追查源眼 carve / `make_eyeline_parts.py` 的 `seg_head` 补肤边界和眼角附近层级；未经局部候选与 C 实拍，不盲目扩大 socket 或形态学半径。

本人判断：这是可见 WIP 改善，但**整个脸部视觉门禁仍失败**；需要继续定位和处理右侧残留，并重新做全脸/全身检查。

## QA 口径与当前门禁

完整 27 步候选末尾 `asset_qa_report.json`：**1,342 项，33 项失败，`design_iou=0.9934918477598998`，退出码 1**。失败覆盖静止拼合差额、躯干内部洞、鞋抬高/触地、张嘴真素材、闭眼接缝、腮红、差分发型接管/配色、结构性腕垫片与平色 mouth mask 等；不是眼部聚焦报告。该数字仅描述本次完整候选，不宣称相对其他轮次的连续改善；与历史 1,342/34 全链、1,342/33 定向摸头、1,310/32 眼部聚焦的范围/构建批次不得混算。

QA 未清零、视觉未通过、缺件及手型未完成，不能把候选接入生产，也不能将本阶段称为整个 Chibi 完成。独立 `small` / `mitten`、`hand_style`、全身差分发型/兜帽、服装遮挡、动作与真实 C 引擎组合矩阵仍是总任务门禁的一部分。

## 可复核文件

- `candidate_make_eye_parts.patch`：候选拆眼脚本相对开工仓库脚本的完整差异（含先前上睫毛 ROI 试验和本次 aperture 限界）。
- `candidate_eye_parts.json`、`candidate_eyeline_parts.json`、`candidate_sidehair_report.json`：构建报告/几何元数据。
- `candidate_rig_eye_layers.json`：rig 中眼部与腮红部件的文件、遮罩、层级、缩放字段。
- `candidate_eye_*_socket*.png`、`candidate_eye_*_lash_up@2x.png`、`candidate_seg_head.png`：本次候选输入/输出抽样；不属于正式资产。
- `engine_chibi_fullbody_after.png`、`engine_face_zoom_after_5x.png`、`engine_face_before_after.png`、`engine_part_isolations.png`：真实 C 引擎目视证据。
- `asset_qa_report.json`：完整候选资产 QA 明细。
- `full_rebuild_27_steps.log`：候选流水线记录。
- `SHA256SUMS.txt`：以上归档文件哈希。

下一步应针对 `seg_head` 眼角 carve 与 source aperture 做更窄的成因验证，先出同源局部 overlay/隔离 C 实拍；若修正，必须再跑完整依赖链、重启 C 并由本人检查脸部。生产素材仍保持不动。
