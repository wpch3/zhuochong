# Chibi C 帧眼缘透明缺口配准与隔离补片 WIP

日期：2026-11-02

分支：`arena/aaf1408c-zhuochong`

记录时仓库 HEAD：`b7fc1d292ce958697cda8090e2b15c7f581048db`。证据基线：此前生成的 Chibi 隔离全链候选；C 运行态 baseline `5177`，补片候选 `5179`（精确资产 SHA 随档）。活动仓库生产 `characters/xiaoxun/forms/chibi/sprites/` 与 `rig.json` **未修改**。

> 这是对上一份 `coordinate_mapping_2026-11-02/README.md` 的后续更新。上一份记录的是当时仍缺少屏幕到源 texel 变换的状态；本目录补上了固定 C 帧仿射配准、实际 `seg_head@2x` 源像素检查和侧发隔离结果。它仍只是局部 WIP，不是 Chibi 或该眼缘的生产验收。

## 已确认的事实

- 在真实 C 引擎中把 Chibi 切换完成后，physics/ambient 关闭、scale=1、gaze off、参数 reset、暂停 `t=0`，以 head-group 四个 socket 的 rig 坐标到屏幕坐标做最小二乘 affine fit。最大 socket 残差约 **0.00198 px**。逆变换后减去运行时 `seg_head` 的 `[140,68]`，再乘 2，得到当前真正采样的 `seg_head@2x.png` texel 坐标。
- C 画面里四个观察窗中，右外眼角上沿横线、右下短边、左侧黑短线均对应 `seg_head` 的透明/低 alpha 贡献；同窗 `hair_side_l/r` 隔离图在 alpha 上全为 0。右上/右下/左黑短线不归于侧发件，也不命中已知 eye `carve/socket/lash` 覆盖。
- 使用同一 Chibi 自有 `eye_l_closed.png` / `eye_r_closed.png` 的 `clean_skin()` 结果作 donor，只在定位的 alpha≤24 像素补回，不扩大 eye socket、不裁用户红圈图、不借 Teen 贴图。候选只保存在本目录的 WIP PNG，不进生产。
- C 目视：右上横线局部暗像素数 **29→0**；右下短边 **7→0**。左侧黑短线 **10→1**，最左缘仍有 1 个暗像素，所以这项未通过。放大图未见明显矩形补丁，但一个局部清除效果不能代替生产验收。
- 左侧上方的灰色短标记另行核查后发现：其 1× 源图有透明像素，但实际活动的 `seg_head@2x` 在对应位置 alpha 已有 64–255，候选没有任何 C 像素变化。它不是已证实的透明缺口；最终 WIP 已把这 5 个无效 1×试改恢复为基线，不将其冒充成功修复。
- 眼底和睫毛单件 A/B SHA 完全相同；head-only A/B 95 屏幕像素改变，集中在邻近眼缘。整帧 A/B 改变 1504 像素，明显多于局部 head-only 差异，剩余全帧差异原因未明；不得把它们归因于贴片。

## 隔离候选范围与局部审计

当前随档案提供的 `candidate_seg_head_wip.png` / `candidate_seg_head_wip@2x.png` 仅用于复核，不应覆盖生产文件。三块尝试恢复的 1×区域（半开坐标，seg_head 贴图局部）：

| C 观察窗 | 1× seg_head ROI | 2× 实际纹理 ROI | donor | C 局部结果 |
|---|---:|---:|---|---|
| 左黑短线 `[289,536,299,537)` | `[145,470,156,472)` | `[290,940,312,944)` | `eye_l_closed`，clean donor `[32,90,43,92)` | 10 个暗屏幕像素只剩 1 个；暂不通过 |
| 右上横线 `[555,518,570,520)` | `[411,447,426,449)` | `[822,894,852,898)` | `eye_r_closed`，`[114,67,129,69)` | 29 个暗像素清到 0；C 放大未见方块 |
| 右下短边 `[553,533,557,535)` | `[409,462,413,464)` | `[818,924,826,928)` | `eye_r_closed`，`[112,82,116,84)` | 7 个暗像素清到 0；C 放大未见方块 |

补片只在相应源窗口中对 baseline alpha≤24 且 clean donor alpha>0 的位置拷贝 donor RGBA；2×贴图用同一 donor 的最近邻 2× lift。实际改动：1× 20/29/8 px，2× 38/97/18 px。完整连续坐标、alpha 直方图、socket matrix、屏幕 A/B 统计和纹理 SHA 在 `screen_to_texture_map.json`。

## QA 与当前边界

对已构建的隔离候选执行了一次 `tools/check_assets.py --character xiaoxun --form chibi` 快照，结果 **1342 项、33 fail、design_iou=0.9934918477598998**。这是本次局部 WIP 后的独立 asset-check 快照，**不是 27 步依赖链重建**；不得与历史 1342/34 来源锁定、1342/33 hitbox 定向、1310/32 眼部聚焦或其他完整隔离重建口径混算，也不能宣称 QA 连续改善。完整 JSON 见 `asset_qa_check_assets_snapshot.json`。

未找到“是哪一步首次产生这些 alpha 缺口”的可复核中间快照；当前只确认缺口存在于隔离全链产物的活动 `seg_head@2x`，并在 clean closed-eye donor 中有肤色像素。故没有把补丁接入 `clean_head_backing.py` 或 `tools/rebuild_parts.sh`，也没有重建生产 rig。全身拆件、`small/mitten` 独立 hand_style、open/heart 手势、发型/兜帽、表情、服装遮挡、动作组合均未因本次局部诊断而验收或关闭。

## 本人 C 引擎目视结论

本人逐窗看过 `C_frame_gapfill_crosscheck.png` 以及 baseline/candidate 全身和 `seg_head` 隔离帧：右上与右下透明缺口被皮肤底补住，边缘没有明显矩形块；左黑短线大部分淡出但尚残一个屏幕像素；左灰标记仍在且本轮没有动。整帧其他差异未解释。因此当前结论为：**三个映射点中的两个局部视觉改善已证实，左侧未完成；所有贴图与 rig 仍保持生产不变。**

## 文件

- `analyze_evidence.py`：从随档截图、socket 状态和隔离纹理重算坐标/差异报告与放大图；运行：`python <本脚本路径>`（需 Pillow、NumPy）。
- `screen_to_texture_map.json`：affine、精确屏幕→seg_head 1×/2×坐标、alpha 直方图、donor 覆盖、逐窗 C 前后像素计数、full/head A/B 统计、QA 口径及限制。
- `C_frame_gapfill_crosscheck.png`：本人复核过的真实 C 局部前后对照；洋红框仅为观察屏幕窗，不是源图修补范围。
- `baseline_full.png` / `candidate_full.png`、`baseline_seg_head_isolation.png` / `candidate_seg_head_isolation.png`：固定姿态 C 截帧。
- `isolate_*` / `candidate_isolate_*`：左右眼底、睫毛、侧发真实 C 引擎隔离帧，用以复核归属与 alpha 为空。
- `baseline_seg_head_unmodified*` / `candidate_seg_head_wip*`：隔离候选的 active 1×/2×纹理基线与 WIP；不是生产文件。
- `donor_eye_*_closed.png`、`source_eye_*_parts.json`、`seg_head_rig_entry.json`：donor 与坐标复算所用 Chibi 来源/元数据。
- `baseline_runtime_state.json` / `candidate_runtime_state.json`：C API 固定状态和 sockets/params。
- `asset_qa_check_assets_snapshot.json`：本次独立资产 QA 原始 JSON。
- `SHA256SUMS.txt`：本目录所有证据文件校验和（不含本清单自身）。

## 下一步

1. 找到 alpha 缺口在完整生成链中的首个来源阶段；不是在 `seg_head` 终稿做一次性补片后就当成根因解决。
2. 检查左黑短线最后 1px 是否应由面部底图延伸，先做窄候选 C A/B，不为追求阈值而扩大肤色边界；左灰标记继续按真实高分辨率源图归属判断，不直接擦除。
3. 若局部候选完整通过本人全脸目视，再把最窄规则接入生成器、重跑完整依赖链和 QA、验证 1×/@2×/rig；完整 Chibi 项目仍继续覆盖全身拆件、两种手型、差分发型/兜帽、表情、衣服遮挡与动作组合。
