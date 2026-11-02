# Chibi 外眼角 underlay / carve 追查（WIP，未接生产）

日期：2026-11-02
活动分支：`arena/aaf1408c-zhuochong`
基线：远端 fast-forward 后 `6ad6d8382cf0222864029ee1a5662ac3cadddf24`
来源：`characters/xiaoxun/design/design_sheet_chibi.png` 与 Chibi 自有 redraw/eye 源件。image-29 只作观感参照，未裁成贴图；未借 Teen 素材。正式 `characters/xiaoxun/forms/chibi/sprites/` 和 `rig.json` 未修改。

## 状态摘要

这是针对前一阶段右外眼角残留做的**隔离追查**，不是 Chibi 完成或生产验收。按真实 C 帧逐眼放大目视后，新增 2px lash-fill padding **没有消除**右侧黑色短切口/碎块，拒绝提升；随后查 `seg_head` 透明度与后续清理顺序，发现简单补 alpha 的门控在 eyeline 阶段命中 0px，byte-for-byte 的 `seg_head.png`、`seg_head@2x.png` 与 rig 均与 1px 基线相同。另一个只在内存候选上运行的 clean-head eye-protect overlay 保留了部分边界像素，但目视没有清掉目标痕迹，亦拒绝。

**结论：根因仍未确认，视觉门禁失败，不改生产。** 本轮更有把握的结论是“扩大 lash 软边”和“盲目对当前 seg_head 补透明像素”不是有效修复；需要继续把 C 引擎残留逐像素映射回实际所属部件/层级，而不是扩大 socket、补脸矩形或把小图差异说成通过。

## 实际实施与独立 QA 口径

在同一最新 HEAD、同一合并后的 socket-bound candidate patch 上构建两个隔离完整基线，以及一个 alpha-restore guard 变体：

| 候选 | 工具差异 | 完整链结果 | C 引擎目视 |
|---|---|---|---|
| baseline 1px | 既有 Chibi socket/aperture patch；`make_eyeline_parts` lash dilation = 1 | 27 步完成；1,342 项 / 33 fail；`design_iou=0.9934918477598998` | 真实 C，Chibi、idle、ambient off、freeze `t=0`，帧 466×748；作为这次 A/B 基线，不是验收 |
| lash pad 2px | 仅将 face-underlay 周围 lash 填充 dilation 从 1 提至 2；不扩大 rig socket | 27 步完成；1,342 项 / 33 fail；`design_iou=0.9934918477598998` | 同一 C API 设置。整帧变化 954 px，bbox `(150,251)-(315,309)`；外眼角的黑色短块仍在，视觉不通过，拒绝 |
| alpha restore guard | 仅在 `carve & have` 且头件 alpha ≤24 时尝试恢复闭眼皮肤补片 alpha | 27 步完成；1,342 项 / 33 fail；`design_iou=0.9934918477598998` | `eyeline_parts.json` 两侧 `alpha_restored_px=0`；`seg_head.png` SHA-256 与 1px baseline 同为 `c5300a7576f026b59d6b45d1cd87fd5c09e90a1166fb38939680c8798239177a`，`seg_head@2x.png` 与 rig 也逐字节相同。因此没有重开 C 进程冒充视觉新变化 |

三个 1,342/33 报告是本轮不同完整构建的独立结果，不与历史 1,342/34 来源锁定、1,342/33 hitbox 定向或 1,310/32 眼部聚焦统计合并/相减。失败项仍包括静止拼合、躯干洞、鞋、张嘴真素材、闭眼 seam、腮红、发型接管/配色、腕垫片和 mouth mask 等。

## 根因追查证据与限制

- 仅在隔离目录重建 head 依赖步骤并保存 `make_eyeline_parts` 后、`make_mouth_line_cut` 后、`clean_baked_residue` 后、`clean_hair_residue` 后及 `clean_head_backing` 后的 `seg_head` 快照。按相邻快照比较，`clean_head_backing` 阶段改变 9,664 个 alpha 像素；在其 eye-patch 带内 1,126 / 1,613 px 发生 alpha 差异（左右）。这只是定位线索，不证明所有像素都是视觉残留根因。
- 用临时 `eye_keep` 变体离线重跑 clean-head：保留了 935 px alpha，其中左右 eye-patch 带分别 305 / 630 px；并排图上目标黑色短线仍可见，且没有以真实 C 验证，故拒绝将这段逻辑接入生成器。
- source-eye 的 5–12px dark-halo 诊断显示候选碎片与相邻侧发/头缘混在一起，不足以安全定义一个外扩矩形。未把 ROI 外扩大、未更改可见 lash，也未从 Teen 拿 mask。
- `diagnostic_*` 图以颜色覆层标注 source aperture、lash、alpha 变化或候选像素；这些颜色仅是调试可视化，不是候选生产材质。

## 本人真实 C 目视

本人查看 `c_engine_face_baseline_vs_2px.png` 与 `c_engine_outer_corners_baseline_vs_2px.png`。上眼弧和脸部整体基本保持；新增 padding 没有消除右眼外角处仍可见的黑/灰色短切口，左右细节也未达到干净、稳定的 Chibi 眼缘要求。全身外观不能替代局部放大验收；因此**继续失败**。真实帧分别为 `c_engine_baseline_1px_fullbody.png` 与 `c_engine_lash_pad_2px_fullbody.png`。

## 本轮坐标配准补档

新增 `coordinate_mapping_2026-11-02/`，已把 C 全帧、`seg_head` 与眼底/上眼线/侧发隔离帧、左右坐标配准面板、屏幕 ROI 放大图、固定时刻复拍、观察坐标 JSON 和运行态说明复制入库。当前确认可见线段来自 `seg_head` 的 C 画面贡献，但**还未映射到精确源 texel，也未锁定与 sidehair/carve 的重叠归属**；红框不是修补 mask。文件内分开记录了 rig-space 部件原点与屏幕坐标，提醒 head group 的有效 `ParamAngleX` 非零，不能直接用 rig pos 当像素平移。没有改生产贴图/rig，也没有升级候选。

## 可复核文件

- `coordinate_mapping_2026-11-02/README.md`、`observed_features.json` 和配套 PNG：本轮坐标证据、可复核的候选屏幕 ROI、方法与尚未解决的映射限制。
- `rejected_lash_pad_2px.patch`、`rejected_alpha_restore_guard.patch`、`rejected_clean_head_eye_keep.patch`：只归档未采纳候选差异。
- `full_rebuild_*_1px.log` / `full_rebuild_*_2px.log` / `full_rebuild_alpha_restore_guard.log` 与三个 `asset_qa_full_chain_*.json`：每次完整候选链与对应报告。
- `candidate_seg_head_*`、`candidate_eye_parts.json`、`candidate_eyeline_parts_*.json`、socket/carve/lash 及 rig 实际引用的 `lash_up@2x`：隔离输出抽样。
- `c_engine_*`：本轮默认全身和同窗口 before/after / 外角放大 / 差异图。
- `diagnostic_*`：head 阶段 alpha 变化、offline eye-protect A/B、source fringe 掩膜。
- `SHA256SUMS.txt`：目录内证据完整性清单。

## 下一步

继续在隔离 candidate 将真实 C 残留与 `seg_head`、lash、sidehair、socket/carve 的**实际屏幕到源图坐标**逐像素配准；在没有证明候选掩膜只包含需要清理的 Chibi 眼缘前，不改 ROI/alpha。随后只采纳一个最窄候选，重新跑全依赖链、QA、@2×/rig，并重启真实 C 做全脸/全身目视。 QA未清零、缺件/双手型/手势/服装遮挡/发型兜帽与动作组合未完成、用户确认未到之前，生产 Chibi 贴图与 rig 保持不动。
