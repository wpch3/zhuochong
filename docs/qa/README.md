# docs/qa —— **验收证据**（入库）

## 为什么要有这个目录

`logs/` 在 `.gitignore` 里（第 11 行：`logs/`），所以放在 `logs/asset_qa/` 下的证据图
**从来没有进过库**。2026-10-26 工作区被还原、本地未跟踪文件全部丢失，才发现
"我在 JOURNAL 里写了『证据图已随提交入库』"是**假的** —— 那些图一张都没提交。

于是定一条规矩：

| 目录 | 用途 | 入不入库 |
|---|---|---|
| `logs/` | **一次性草稿**：调参中间产物、随手截图、试跑输出 | 不入（可随时丢） |
| `docs/qa/` | **验收证据**：任何"已修 / 已达标"的结论所依赖的图与数据 | **必须入** |

判据很简单：**如果删掉它，某个结论就无法复核** → 它就属于 `docs/qa/`。

## 现在这里有什么

- `sprite_audit_teen.json` —— 素材体检基线（T67.2）。`selfcheck` 与 `make audit-sprites`
  都以它为基准；它是"重画前后只许降不许升"的那个"前"。
- `live2d_mask_intersection_2026-10-31.png` —— 引擎用两个错位矩形遮罩真实渲染的像素图；只露出交叠区，作为 T67.8 多遮罩交集证据。
- `live2d_teen_eye_clipping_2026-10-31.png` —— teen 真实 rig 睁眼 / 半闭 / 闭眼渲染；核对眼眶 mask 继续贴合，不出界。
- `live2d_teen_hairstyle_hood_matrix_2026-10-31.png` —— teen 真实 rig 四种发型（短发 / 长发 / 双马尾 / 高马尾）× 兜帽戴/不戴静帧回归（较早一轮）。
- `live2d_teen_hood_shadow_engine_short_down_2026-10-31.png` / `live2d_teen_hood_shadow_engine_short_up_2026-10-31.png` —— 预览引擎 `/api/frame.png` 原始全身帧（未裁切、未拼图）；配套 `live2d_teen_hood_shadow_states_2026-10-31.json` 记录逐帧 `/api/info.json` 姿态、冻结参数与 SHA-256。
- `live2d_teen_hood_inner_shadow_full_2026-10-31.png` —— 同一短发姿势与冻结时刻，hood down/up 全身对照；API 姿态状态已逐张核对。
- `live2d_teen_hood_inner_shadow_detail_2026-10-31.png` —— 同一引擎的兜帽内沿与头发局部放大对照，确认软乘算阴影只在 hood-up 显示。
- `live2d_teen_hood_shadow_hairstyles_2026-10-31.png` —— API 状态已核对的 hood-up 四发型 + short hood-down 控制图；用于检查兼容性与隐藏行为。
- `live2d_teen_neck_details_2026-10-31.json` 及 `live2d_teen_neck_details_{engine,detail,motion_engine,motion_detail}_2026-10-31.png` —— T67.9 ② teen 引擎真实渲染证据：中立全身、颈部近景，以及头转/躯干倾斜检查；细节图为原帧裁切放大。
- `live2d_teen_shoe_contrast_2026-10-31.json` 及同前缀 `engine/detail/tiptoe_engine/tiptoe_detail` PNG —— T67.9 ⑤ Teen 真实引擎静态与 tiptoe 峰值验收；JSON 记录近白率前后值、鞋底/鞋口几何检查和逐张 SHA-256。
- `live2d_teen_longhair_centerlock_2026-10-31.json` 及同前缀 `engine/detail/owner_hidden_engine/owner_hidden_detail` PNG —— T67.9 ⑥淡青块真实引擎复现与逐件隐藏归属对照；确认来源是 `acc_hair_long`（long back-hair），并与 `sheet_long.png` 原画核对。不是 stray clothing；长发本体形状优化继续由 T67.7 跟踪。
- `live2d_chibi_baseline_2026-10-31.json`、`live2d_chibi_baseline_engine_2026-10-31.png` 与 `live2d_chibi_baseline_face_detail_2026-10-31.png` —— Chibi/Q 版现有 rig 的真实 C 引擎预修复基线。几何/资产机检 0 失败，但脸侧/刘海边缘有明显碎线，明确标记为**未视觉验收**，不作为完成证据。
- `live2d_chibi_regen_source_audit_2026-10-31.json` 与 `live2d_chibi_regen_source_ab_2026-10-31.png` —— Q/chibi 全版重生成的隔离源头试产证据：对比当前 567×1292 碎裂底图与按已记录四点框从 `design_sheet_chibi.png` 重新抠出的 569×1292 连续底图。**只验证源头候选，不代表重建 rig/切件完成或通过。**
- `live2d_visual_work_plan_2026-10-31.md`、`live2d_teen_visual_audit_2026-10-31.json` —— 2026-10-31 Teen 真实 C 引擎目视审查、缺陷排序与后续修复计划；这是未完成项的审查记录，不是验收通过证明。长发全身/单件、袖子近景、三套衣服、四种动作和 bones-only 证据均有 SHA-256。
- `live2d_teen_audit_longhair_full_2026-10-31.png` / `live2d_teen_audit_longhair_isolated_2026-10-31.png` —— Teen 长发全身及 `acc_hair_long` 单件隔离真实渲染；确认两侧黑/青/白条状杂边仍属于长发件，T67.7 未关闭。
- `live2d_teen_audit_wave_sleeve_detail_2026-10-31.png` —— Teen wave 高举手臂的袖管/夹克接缝真实近景；用于 T67.6、T67.35、T31.15 修复前定位。
- `live2d_teen_audit_outfit_matrix_2026-10-31.png` / `live2d_teen_audit_motion_matrix_2026-10-31.png` —— Teen 三套衣服静帧与 wave/surprised/tiptoe/heart_hands 代表帧；仅为审查范围证据，不代表所有组合已通过。
- `live2d_teen_audit_surprised_bones_2026-10-31.png` —— Teen surprised 第 54 帧真实 bones-only 叠图；配合审计 JSON 中 `/api/bones.json` 关节数据，证明本次抽查未见断链，但不作为全骨架验收。
- `live2d_teen_cheek_paramcheek_ab_2026-10-31.png` —— Teen 真实渲染 ParamCheek=0/1 放大对照；用于确认降峰值、去斜线后腮红随参数平滑出现。
- `live2d_teen_cheek_paramcheek_on_2026-10-31.png` —— ParamCheek=1 全身静帧；核对腮红在整身尺度不过浓、不像贴纸。
- `live2d_teen_mouthform_corner_full_abc_2026-10-31.png` —— teen 真实引擎全身 ParamMouthForm −1/0/+1；检查整身状态无副作用。
- `live2d_teen_mouthform_corner_closed_detail_abc_2026-10-31.png` —— 同一真实帧的闭口嘴部放大；检查笑形抬角、怒形压角、中心不漂。
- `live2d_teen_mouthform_corner_open_detail_abc_2026-10-31.png` —— ParamMouthOpenY=0.65 下 Form −1/0/+1；检查口内与开口遮罩同步、不露接缝。
- `t67_*.png` —— 2026-10-26 这一轮各条结论的对照图（长发换源头前后、两腿间薄片归属、
  尾巴四档可见性、体检误报现场……）。文件名里的 `t67_NN` 对应 `docs/memory/TASKS.md` 的任务号。
