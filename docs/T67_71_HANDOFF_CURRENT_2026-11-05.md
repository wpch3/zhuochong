# T67.71 当前交接｜Teen hood-up 长发的袖口/手部遮挡连续性

更新时间：2026-11-05（Asia/Shanghai）
固定工作分支：`arena/aaf1408c-zhuochong`（当前状态：active）
仓库：`/home/user/zhuochong`
本交接写入前 HEAD：`7915730 Archive T67.71 interlocking strand design studies`

> **结论先行：T67.71 仍未修复。没有候选通过局部目视门；没有进行候选确认或真实 C 复验；生产 sprite、rig、generator、engine 均未修改。** 本文是如实交接，不把失败 WIP、静态 mock、C-only 测试或已有交接资源称为修复。

## 1. 本任务要解决什么

修复 Teen `long + hood-up` 组合中，头发层在手臂/袖口后方应连续但烘入了袖口/手形或被清除成透明区域的问题。手臂移动/替换或头发单独显示时，不应露出空洞、错误的袖手残留或不自然的发丝断口。

关键真值/样本：

- 扁平设计源：`characters/xiaoxun/design/sheets/sheet_long_hood.png`（1024×1536 RGB）；其被手/袖遮挡区域没有可恢复的真实发丝像素。
- 提取件：`characters/xiaoxun/design/redraw/sheetcut_hair_hood_long.png`；hair cutout 携带了可见的袖口/手内容。
- 当前目标运行贴图：`characters/xiaoxun/forms/teen/sprites/hair_hood_long@2x.png`（1132×1664 RGBA）。两处 QA ROI 为 left `[51,849,396,1368]`、right `[736,849,1081,1368]`，只是检查区域，不是发丝 mask 或隐藏设计真值。
- 2026-11-04 C 动作/源追踪记录：`docs/qa/t67_71_source_trace_2026-11-04/README.md`、`source_trace_board.png`、`capture_metrics.json`。目标 `acc_hair_hood_long` 在 layer 258；旧袖口/手形烘在该 hair 件内。正常手臂层 138–151，surprised 替换手臂层 319–322。既有动作截图是问题证据，不代表新候选通过。
- `manual_artifact_polygons_v2.json` 仅是可见袖口/手部清理 ROI；会覆盖一些合法头发，不可直接当作发丝外形/新发 alpha。

同造型分层原稿尚未找到。`hair_long_back_v2`、`hair_long_backonly_v1/v2`、pony/twin 等只是不同造型或画风旁证，不得称为目标隐藏真值，也不可直接转成修复像素。

## 2. 用户授权与不可越过的门

用户已授权做一个**新设计提案**，要求不要与现有方案差太远。该授权只允许提出非原像素的新设计，并不等于：

- 恢复/推断出隐藏原始发丝真值；
- 批准任何一个具体候选；
- 允许进入生产 sprite、rig、generator 或 engine。

流程必须保持：隔离候选 → 代理本人看完整上下文和左右细节 → **只有局部目视通过后**才把具体图稿交用户确认 → 用户确认后才进入真实 C 动作/袖口遮挡/转场验证 → 生产改动另行批准。失败候选不能送 C 来“看看会不会好”，静态 registration mock 也不是 C 验证。

## 3. 方案尝试与目前自评

### 已记录并拒绝的早期路线

完整顺序、review board、理由和防重试约束见：
`docs/qa/t67_71_source_trace_2026-11-05/wip_masked_inpaint_attempt_v2/layered_backfill_wip_review.md`

简要索引：

- source-only handoff / 空白注册模板：`105_artist_handoff_reference.png`、`105_artist_handoff_brief.md`、`107_T67_71_registered_artist_template.ora`。这些是交接资源，不是发丝修复。
- 局部 AI、旧 guide、mask/inpaint、手绘 continuation v1–v4 和同目标 lower-hair texture warp v1–v3：均在各自 review 处拒绝；原因为大块/几何片、黑洞/硬顶、直深线、楔口、画风不合或接缝不自然。
- 后续新构成：`strand_weave_v1`、`strand_weave_v2`、`ribbon_cascade_v1`。看过最终板和左右局部/3×图后，分别仍像梳齿、平行扁带、根端漂离/轮廓过齐；均拒绝。SHA：`docs/qa/t67_71_source_trace_2026-11-05/strand_lock_studies_SHA256SUMS.txt`。

### 最近被中断的 `painted_volume_v1`

位置：`docs/qa/t67_71_source_trace_2026-11-05/painted_volume_v1/`。里面有脚本、underlay、清理前层、合成、静态注册 mock、review board 和部分左右 3× crops；当前没有完整 metrics JSON / 单独完整 manifest，脚本依赖 Pillow，当前系统 Python 默认环境不含 Pillow。它不能作为候选交付。

本人已打开 `t67_71_painted_volume_v1_review.png`：新增形状成为单一圆钝的水滴/发团，表面只有少量淡线；根部未自然融入可见发束，静态叠图仍像独立软团而非原发的连续部分。**该版拒绝**。最后一次执行在用户中断后未完成记录文件生成，因此不要把缺失的 metrics/哈希说成已验证，也不要将这组部分文件当成通过候选。review SHA-256：`f45a4653836aae2a4a45d6c68e8deed30dd2adaa855855c6e3afcbed95bad7a4`；underlay SHA-256：`eeb96fa4eddd77287820acbacbf05e817ee92cf48d579642bc0243265420ecd2`；composite SHA-256：`2411545888b09d7a0db21ca1d058134d58a7e3ba6687895e47193f92927749ae`。这几个 hash 仅锁定现存文件，不表示质量通过。

### 能力边界（必须诚实传达）

当前代理已自评：能做源追踪、隔离图层、配准、证据与 C/QA 工作；但经过多轮实际失败，**未证明能独立画出达到原角色笔触和连续性标准的发丝美术**。不能继续把矢量几何、增加锁数、换 alpha 或程序化软化包装成“快完成”。下一位执行者应直接从高质量角色绘制开始；若下一位是代理，也必须先证明具体局部图稿过门，否则继续停留在隔离提案阶段，不得接 C/生产。此判断不是撤销用户的新设计授权，也不是把失败工作称作完成。

## 4. 下一位执行者的工作顺序

1. **开工核对**：读本交接、`docs/memory/WORKFLOW.md` 铁律 0–17、`REQUIREMENTS.md` A69.2–A69.6、T67.71 的 `TASKS.md` 行、最近 `JOURNAL.md`、本交接引用的 WIP review。核对固定分支、HEAD、`git status`，勿恢复/丢弃未知 stash。
2. **先定位真值边界**：在原目标全件、扁平 sheet、生产 sprite 和旧对象 ROI 上看图。被遮挡部分没有同造型隐藏原画；新画必须显式标作“新设计/推断”，不可冒称复原。
3. **准备真实新设计局部稿**：使用注册模板 `107_T67_71_registered_artist_template.ora` 或原画布大小 1132×1664 的透明层。左右后发独立；与当前 hood-up 长发外轮廓、冷灰紫色料、可见发丝线流和线宽接近；需体现连续发束体积、自然根部接合与有变化的发尾/负空间。手/袖前景清理与新发丝 alpha 要分开处理。静态手袖 mock 不可替代可动手臂层。
4. **局部目视门**：至少看完整左右 ROI、1×源、3× clean/static 细节；透明层分别叠白/灰/深底。判据包括：不再读作水滴团/扁板/梳齿；发根接入现有发件；线流/明暗与目标相融；轮廓不平顶/硬切；清理区无手袖异物；alpha 边缘不透洞且不误删合法发丝。任一不合格即拒绝，不能送 C。
5. **用户确认**：只有代理自审通过的具体图稿才交用户看和确认。新设计授权已存在，不用重复问“是否允许新设计”；但不能把授权当成图稿批准。
6. **真实 C 隔离测试**：仅图稿通过且用户确认后，使用临时 rig/sprite 副本。跑 idle、surprised、wave、wave_both、heart_hands 等代表动作、动作进出/关键转场，以及 `ParamHairSway=-1/0/+1` 独立检查；看真实 C 全身与左右袖口局部，分别目标件 only/hidden。不得用静态 mock 或 C-only `make test` 替代此门。
7. **生产门**：真实 C 动作/遮挡/转场门通过后仍需独立生产批准；先审精确 diff，再考虑最小生产接入。

## 5. 禁止重试/误报事项

- 不再重复 `handpainted_continuation_v1–v4`、`same_sprite_warp_v1–v3`、`strand_weave_v1/v2`、`ribbon_cascade_v1` 的几何/纹理路线小修版；不只改宽度、alpha、颜色、线数。
- 不重跑已拒绝的相同 AI guide、扩 mask、Telea/NS inpaint、同 donor remap。
- 不将 `manual_artifact_polygons_v2.json` 叫作头发 mask；不整体 `alpha=255`，不把原色图/透明洞、袖口和手指清理问题混作一个 mask。
- 不把 `painted_volume_v1` 或其他 review/static mock 称为 accepted candidate、隐藏真值或动态修复。
- 不进入真实 C 或生产，除非前置局部目视门/用户确认均满足。

## 6. 验证与仓库状态

- 之前记录的 `make test` 2638 项通过/0失败是 C-only 基线，不是美术验收；本次交接整理未重跑 `make test`。
- 本轮新增交接文档前，HEAD 为 `7915730`；其上已推送的 QA 实验均在 `docs/qa/t67_71_source_trace_2026-11-05/`。未见生产路径修改。`painted_volume_v1/` 是中断后新增的未跟踪 QA WIP，现需随交接归档并标注拒绝/不完整。
- 后续提交和推送只能到当前固定分支 `arena/aaf1408c-zhuochong`，不得切换或重命名分支。

## 7. 主要文件入口

- 当前交接：`docs/T67_71_HANDOFF_CURRENT_2026-11-05.md`
- 失败方法与目视理由：`docs/qa/t67_71_source_trace_2026-11-05/wip_masked_inpaint_attempt_v2/layered_backfill_wip_review.md`
- 注册作者空白模板及来源交接：`docs/qa/t67_71_source_trace_2026-11-05/wip_masked_inpaint_attempt_v2/107_T67_71_registered_artist_template.ora`、`105_artist_handoff_brief.md`
- 真实 C 原始问题证据：`docs/qa/t67_71_source_trace_2026-11-04/`
- 最新几何负例哈希：`docs/qa/t67_71_source_trace_2026-11-05/strand_lock_studies_SHA256SUMS.txt`
- 当前被拒 painterly WIP：`docs/qa/t67_71_source_trace_2026-11-05/painted_volume_v1/`（部分产物，不可作为候选）
