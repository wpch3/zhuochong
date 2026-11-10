# Chibi / Live2D 参考资料充足性审计（2026-11-02）

分支：`arena/aaf1408c-zhuochong`
目的：回答“目前参考项目和资料是否足够”，记录本轮实际检索、可借鉴的方法、许可边界与尚缺的真值源。此文件是学习资料索引，不是素材授权，也不表示 Chibi 已验收。

## 结论：工程参考够用，美术真值不够

**目前资料足以继续推进自研 rig、拆件工具与测试方法；不足以直接完成 Chibi 的新美术和全身验收。** 不需要再扩成一堆泛 Live2D 链接；缺的是针对小寻 Chibi 自己的可审阅参考稿、手型源件与分层/遮挡设计，而不是再抄一个运行时。

分层判定：

| 领域 | 当前资料是否足够 | 判断 / 下一步 |
|---|---|---|
| 渲染、参数、遮罩、网格、物理 | **足够继续自研** | 现有 `LIVE2D_CONFORMANCE.md`、`ART_PARTS.md`、`SKELETON_SYSTEM.md`、Cubism/Inochi 源码阅读记录已覆盖机制。需要按实际 Chibi 视觉症状检索，不再泛读引擎教程。 |
| 设计稿到拆件的方法 | **流程够、Chibi 内容未齐** | `SHEET_PIPELINE.md` 固化了“同一底图先完成全身差分稿，再拆层、套准、验收”；应给 Chibi 同样出自己的完整模板/差分板，不能把 teen 模板或 teen 部件当 Chibi 真值。 |
| `small` / `mitten` 手型 | **不足，是明确阻塞项** | Chibi `sprites/` 当前只有整段 `seg_arm_l/r`，没有独立 hand PNG/手件清单；现有 `design/hands/*_raw.png` 只能作其原设手势参考，不能代替 Chibi 生产贴图。需要按 Chibi 画风与袖口比例制作一张自己的手型板，再拆成独立源件。 |
| 发型、兜帽、衣服遮挡 | **方法够，内容仍欠** | 复用完整差分立绘 + 被遮挡区域补全 + 层序/遮罩思路；对已知 Chibi 长后发混入脸/额头等问题必须重绘源头，不能再用颜色阈值硬挖。 |
| 表情与动作 | **原则够，逐个动作真值不够** | `WORKFLOW.md` REF-FIRST：每种明显姿势先有本角色参考图、测量、离线预演，再接 rig；每项必须固定参数并由 C 引擎实拍，不用代码想象姿势。 |
| 整体验收 | **没有通过** | 最新 source-underlay 候选完整链 QA 是 1342 项 / 33 fail / `pass=false`；这是局部候选快照，不是全身通过。参考资料不能替代修失败项、逐件目视和多状态 C 帧。 |

## 本轮检索与核实记录

检索日期：2026-11-02。使用 GitHub Repository API 搜索 `live2d`、`Live2D SDK`、`2D puppet animation/rigging`、`chibi Live2D`，并读取下列仓库的 README、LICENSE 或具体设计/样例文件。**没有下载或引入外部代码/图片进生产素材。** `GitHub` 仓库搜索未找到一份同时满足“明确开放授权、视觉上匹配小寻 Chibi、可直接用于生产”的手型素材；因此不把搜索结果中的游戏 chibi 立绘或未标授权图片当参考贴图。

### 新增/补充的项目

1. **Live2D 官方 Native Samples** — <https://github.com/Live2D/CubismNativeSamples>
   - README 的 `Samples/Resources/Haru` 实际含 `.moc3`、`.model3.json`、`physics3.json`、`pose3.json`、动作和表情文件；适合核对运行时装配、参数/物理/姿势数据的关系，不是 Chibi 美术教程。
   - 仓库 License 明确区分 Cubism Components 的 Open Software License、Cubism Core 的 Proprietary License、样例模型的 Free Material License；每个样例模型另有使用条款。商业收入门槛及用途须按实时许可文件复核。
   - **方法**：只查结构/行为；不将 Haru 等样例部件裁作小寻素材，不把模型版权与 SDK 代码许可证混为一谈。与本项目“不引入 Cubism Core”的决策一致。

2. **Inochi Creator** — <https://github.com/Inochi2D/inochi-creator>（BSD-2-Clause；格式/运行时见 <https://github.com/Inochi2D/inochi2d>）
   - 开源 2D puppet 编辑器；已核 README 和源码树，存在 PSD 导入、自动网格、轮廓网格与网格编辑器等模块。适合观察艺术家如何检查层、改网格、设置变形，不与本仓库 `rig.json` / C 渲染器直接兼容。
   - **方法**：借鉴“先有可见网格/图层，再编辑变形”的作者工作台思路；不能照搬其文件格式或把编辑器引入 C 核心。BSD 只说明代码许可，不自动授权 README 中署名的模型/图片。

3. **Iki** — <https://github.com/zeikar/iki>（MIT，2026-11-02 检索时 README 明示 early-stage）
   - 本轮新增读取 `packages/editor/AUTO-RIG.md`、editor README 和插件说明。它从角色命名的层图生成 `.iki`，提供 rig-plan/report、测量器、越界 clamp/refusal；插件把“artist 生成 → critic 按 rubric 找问题 → 改图/重跑”的闭环显式化。自动 rig 设计写明哪些参数是从两个自有角色盲测选出，哪些仍是 provisional，不把默认值伪装成普适常数。
   - **适用方法**：每个候选参数逐项变更、固定极值渲染、打乱候选做盲评；报告要区分“可接受并 clamp”与“结构不可能而拒绝”；生成图之外再设 critic/rubric 复检。
   - **限制**：项目很新，自己的 `.iki` / WebGL 格式和图像生成插件不符合当前 C-only、原创素材及不引入 Cubism Core 的边界。MIT 代码许可证不等于插件生成图像天然可作商业素材。本项目只借测量/报告/双人盲评方法，不复制代码、提示词或角色资产。

4. **Umamo** — <https://github.com/umamoorg/umamo>（GPL-3.0；README 明确 alpha/early development）
   - README 声称面向 `.cmo3` / `.moc3` 导入导出的跨平台 2D puppet 建模编辑器；同时明确当前 alpha 可能破坏项目，建议先备份副本，动画仍是远期目标。
   - **适用方法**：仅当将来需要检查“作者界面如何呈现图层、网格、参数”时，在副本中做探索性试用。禁止把 GPL 实现并入本项目或把它当 production asset pipeline 的稳定依赖；当前没有必要为了 Chibi 工单安装它。

### 已有资料中最该继续用的内容

- `docs/SHEET_PIPELINE.md`：全身差分立绘先行、同底图套准、完整衣服/身体保持不变、通过差分取新件，是造型/兜帽/服装线的首要方法。
- `docs/ART_PARTS.md` 与 `docs/PART_LAYERING.md`：部件独立、遮挡者下留足塗り足し、遮罩与层序、源素材验收。
- `docs/WORKFLOW`（`docs/memory/WORKFLOW.md`）：TRUTH-FIRST、动作 REF-FIRST、先拿领域真值源，改后逐姿势复拍。
- `docs/LIVE2D_CONFORMANCE.md`、`docs/SKELETON_SYSTEM.md`：参数、物理、deformer、运行时结构参考；已存在的功能不要重复开发。
- 最新眼缘根因证据：`docs/qa/chibi_candidate_2026-11-02/head_underlay_source_keep_2026-11-02/`。它只能证明 underlay 小修和局部 C A/B，不是全身艺术参考或资产总验收。

## 由资料导出的制作方法

1. **先锁角色真值**：以 `characters/xiaoxun/design/design_sheet_chibi.png`、Chibi 自己的 `body_full` 与 anchors 为形状/比例/颜色基线；外部样例只讲机制，不覆盖身份与比例。
2. **先出 Chibi 全身差分设计板**：至少统一正面静止、自然站姿、双手与袖口放大、手腕连接、衣服/兜帽遮挡关系；如同一姿势改变手型，保持脸、衣服、腿、透视和身体比例完全一致。稿子通过目视后才切件。
3. **`small` 与 `mitten` 是两套 Chibi 原创源件**：保留 Chibi 当前小手作为 `small` 基准；新画 `mitten`，不要将 teen 手件贴入。每只手都要左右镜像/真实翻转验证、腕口足够覆盖袖口、保留线稿和阴影层级。
4. **把选择轴拆开**：`hand_style` 只选手件风格；手腕角度/动作由现有腕组与动作通道驱动；open/heart 等姿势是另一维。生成状态矩阵时逐个覆盖 `hand_style × gesture × wrist angle × outfit`，禁止把“换手型”实现成“换整条手臂/强制挥手动作”。具体 rig/API 设计先审现有 `poses` / override 能力和可组合性，再决定最小 schema。
5. **先源图后工程**：分出前臂/手件，补全袖口下被遮部分；所有坐标由 anchors/socket 探针求出，不手写位置猜测。静止合成和抬腕/转腕扫角度须无缝；每个 style 的 @2× 与 1× 同时验收。
6. **动作按真值验**：每个新手势先用 Chibi 自己的全身图出姿态参考，读肩/肘/腕/掌方向，再做 FK/离线预演；最后相同参数、服装与时刻下在 C 引擎截图，并看全身和腕口特写。
7. **故障分层归档**：保留素材 QA 与运行时 C 目视两个独立门。`check_assets` 失败项先分类并复测；不同素材快照的计数不作趋势相减。新项目的任何自动 rig 只能当候选生成器，必须跑本仓库的资产 QA 与 C engine。

## 尚缺资料 / 需要的输入

- **项目内缺少 Chibi 手型设计稿**：新建一张 Chibi 自有 `small` / `mitten` 参考板（前/背/侧或足以定义腕口与手掌厚度的角度），并保存进 `characters/xiaoxun/forms/chibi/design/`；这比搜任意“Q版手”网络图更能保证身份、袖口、线稿一致。
- **缺 Chibi 全身差分稿的完整验收快照**：将要做的姿势或兜帽/服装状态画在同一底图上，保存原始输入、套准参数、叠图差分和批准版本哈希。
- **缺端到端 hand-style 组合门**：当前 Chibi rig 只有 `seg_arm_l/r`，没有独立 hand parts 或 `hand_style`。在 source art ready 之后补 schema/生成器/rig 切换、无损合成、腕部角度扫和 C-frame A/B。
- **外部方面暂无一个可安全替代自有素材的 hand asset 项目**。如未来发现明确授权且与角色风格匹配的手部教材，只用作结构参考，并记录许可证/具体页面，不直接裁作生产图。

## 下次开工顺序

1. 对照当前 C 头部补丁提交与全链 33 项失败表，更新当前基线状态；修整 Chibi 全身角色板和手型板，不能从 teen 迁入手件。
2. 建立 `small` / `mitten` 原创 Chibi 手件，再将 wrist 与 gesture 维度解耦。
3. 继续兜帽/发型/服装遮挡与动作组合，逐类解决 QA failure；最终做完整 C engine A/B、@2×与完整链验收。

## 检索范围与限制

本轮项目检索用 GitHub API（仅访问 GitHub 域名）及仓库 README/LICENSE/具体设计文档；没有为本次工作访问 GitHub 以外站点，也没有下载/保留外部模型图片。此前存在的 Live2D 官方手册、绘画/动作文章链接仍见 `docs/memory/REFERENCE_NOTES.md` 历史批次。外部官方站在后续需要核最新规范时，再按允许访问的来源或用户可打开的官方资料核实，避免把旧教程版本当当前真值。
