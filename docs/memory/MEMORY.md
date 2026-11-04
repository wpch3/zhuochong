# 本地记忆（MEMORY）—— 每个代理开工先读、收工必更新

> 这是项目的**本地记忆主文件**：记录"项目是什么、现在到什么程度、做过哪些决定、哪些是硬性规则"。
> 配套（**记忆区七件套，开工全部要读**）：
> | 文件 | 回答什么问题 |
> | --- | --- |
> | `MEMORY.md`（本文件） | 项目是什么、现在到哪一步、定过哪些决策、硬性规则 |
> | `REQUIREMENTS.md` | **用户说过的每一条要求**（聊天 + 交接 + 规格），逐条编号、落点、状态 |
> | `WORKFLOW.md` | **怎么干活**：开工五步、查证顺序、开发循环、交付标准、禁止事项、环境恢复、文件地图 |
> | `GAPS.md` | **还缺什么、需要用户给什么**、执行顺序 |
> | `TASKS.md` | 任务编号与计划（T1–T16） |
> | `JOURNAL.md` | 每轮的思考与工作日志 |
> | `LESSONS.md` | 踩过的坑（同一个坑掉两次就是失职） |
> | `DECISIONS.md` / `DECISIONS_ARCHIVE.md` | 技术决策逐条留痕（为什么这么选、否过什么） |
> | `REQUEST_LEDGER.md` | **按「第 N 问」记用户每一次提问与交付**（含每轮自查发现） |
> | `POSTMORTEM_ART.md` | 形象线的复盘：工序为什么是「先画完整差分立绘、再拆图层」 |
> | `../FORM_MATRIX.md` | **形象矩阵六条轴**：年龄/取景/姿态/发型/**物种(兽娘)**/**装扮(节日)** |
> | `../REFERENCE_NOTES.md` | 查过的资料与 URL（铁律 4 要求结论必须落这里） |
> 规则：**每次工作开始先读本文件与自己上次的日志；结束时必须追加 `JOURNAL.md` 并更新本文件的"当前状态"。**
> 用户的新要求**当轮就要写进 `REQUIREMENTS.md`**，不许只留在聊天里。

更新：**2026-11-04（T70.2：trial08 全身概念方向仍获用户确认；trial09 用户拒绝、trial10 内部失败；trial11 与 trial12/13 手型尺寸被用户指出偏大；trial14 用户仍嫌偏大而否决；trial15 尺寸方向已由用户明确确认合适；trial16 隔离 source-fit art 自检未通过、留作 failure evidence；trial21–23 迭代未达标；用户后续称手套手基本过关，我选择 trial24 source-fit 作为隔离 QA 的基本形态继续用（非 source art/生产批准）；trial25 左右 hand art 因 opaque RGB checkerboards/比例与画风失败仅存负例；没有生产手层/hidden wrist/C-engine 验收；A66.1–A66.2/T70.1–T70.4；T67.70 眼部仍失败；旧全链基线 1342/33 fail）** ｜ 当前分支：`arena/aaf1408c-zhuochong` ｜ 版本：0.1.0

## 最新状态（2026-11-04）

- **双手型/候选自审**：normal fingered hand 与 mitten 必须同时保留；`small` 名称或 source crop 不证明完整正常手通过。用户授权候选批准由代理判断；不逐轮索要选图。代理目视 trial27–42 全部否决：27–32 尺寸/姿势/风格问题；按侧背视角标准复审后，33–36 目标尺寸能看出约三枚圆指尖，仍因姿势、比例、线稿或袖口未保真而拒绝；37–40 注册 ROI 未含三枚圆指尖；41/42 精确 ROI 编辑仍放大重画袖口、产出 opaque checkerboard。全为 WIP 负例；拒绝继续相同 AI prompt 迭代。左右合规源手件、hidden wrist、cuff、动作/rig 与生产验收仍欠。
- **真正 Cubism 模型研究**：已查官方 PSD 导入、ArtMesh/Editor 建模、MOC3/Model3 导出、SDK/Core 与发布许可，并核对 `CubismWebFramework`。当前 49 个 zrig PNG 引用均存在，但仍无 overlap-complete PSD/手袖来源层；另发现 Chibi 路径的 `rig.json` id 异常写成 `小寻_teen`，生产 rig 受保护，未修。桌宠 Q 版图不是 Live2D 源稿，Editor/Wine 亦缺。官方路线/机器层清单见 `CHIBI_CUBISM_TRUE_MODEL_AUDIT_2026-11-04.md`、`cubism_source_layer_inventory_wip/`、`REFERENCE_NOTES.md` 第七十三批。
- **环境/资产事实**：checkout 为 Linux；`CubismEditor` 未安装；全仓无 `.psd` / `.cmo3` / `.moc3` / `.model3.json`。所以没有制作/导出/官方 Viewer 验证真 Cubism 模型。自研 C `zrig` 不是真 Cubism 模型，官方 Core/SDK 运行时整合仍单独受许可/架构审批限制。
- **下一步门槛**：先取得/制作获批 Chibi 完整分层 PSD，在支持的官方 Cubism Editor 环境建立 `.cmo3` 并导出 `.moc3` / `.model3.json`；之后分别完成双手型的编辑器模型验证与官方 Viewer/SDK 实测。当前官方模型制作任务 T70.5 仅研究完成、模型未开始。
- **验证（trial30–40 后续）**：本轮为图片/QA/文档变更，未重跑 `make test`；最近一次实际 `make test` **2638/0**（编译有已知 `_zperf_probe` unused-function warning）。本轮 `selfcheck_repo.py --quiet` 实跑 **772 项 / 1 fail**，唯一仍是受保护 Teen/Chibi rig 旧 generator fingerprint；未重生 rig，`selfcheck_all.sh` 未运行。hand-style JSON、trial27–40 14 份 local SHA、study root SHA 与各 metrics JSON、`git diff --check` 均过；production Chibi sprites/rig 和 `src/core` diff 为 0。
- **提交/推送**：trial27–29 review 前序提交 `5747ff5176eaf75a29e29be3b422b47d164583fb`、trial30–32/Cubism 初审提交 `4a2b80acff072ae94e7b351faf18fd6381cc35e1`、视角标准/日志更新 `25e5e7f3559f8be3a24473df83d5b0c2b4252e1a` 均已推送。trial33–40 自审与 Cubism inventory 提交 `19956de5b5022b74bb54297466f1884e50df0292`、日志收尾 `d2749428b769a168c908f5bf7a86ffd172bd1f39`、按修订视角准则重新目视及更新各 metrics/SHA 的提交 `a34dfd0a6288270f36e025327a3bb1bed8a35611` 均已推送；最终 `git rev-parse` 与 `git ls-remote` SHA 相同。

- 本轮参考资料审计已归档：运行时、网格、遮罩与绑定方法资料足以继续自研；Chibi 自身全身差分稿、合规 `small/mitten` 手型设计板和组合验收仍不足。
- 资料报告：`docs/memory/CHIBI_LIVE2D_REFERENCE_AUDIT_2026-11-02.md`；canonical 索引是 `docs/REFERENCE_NOTES.md`（第六十八批审计、T70.2 cuff 方法和第七十一批官方拆件/来源资格复核）。A66.1 是参考审计，A66.2 是持续按铁律查方法、隔离制作并本人目视的流程提醒（A59 已被既有 Live2D 铁律占用）；执行任务 T70.1–T70.4。
- 当前 Chibi 配置驱动隔离全链为 **1,342 项 / 33 fail / pass=false**。眼缘 underlay 局部工作不是全身通过；生产素材/rig 未因这次审计变更。
- 最新 `tools/selfcheck_repo.py`：772 项、1 项生成器指纹失败（Teen 与 Chibi 生产 `rig.json` 过期）；其余 771 项通过。`roadmap_status.py --fix` 已修正 ROADMAP 进度 630/245/22→630/245/24。完整 `scripts/selfcheck_all.sh` 仍失败：核心编译有既存 `_zperf_probe` unused warning；teen asset QA 有 8 项失败（armpit mask×2、forearm palette×2、long-hair @2× white-edge×1、85px reconstruction delta×1、twin-hair coverage×2）；但单测 2638/0、API/e2e 342/0、schema、Windows build 与 preview 均通过。未重生受保护生产 rig；自检生成的 tracked Windows exe 已恢复。
- 后续仍需按用户要求完成整身拆件、差分发型/兜帽、眼口、small/mitten 独立手型、服装遮挡、动作和真实 C 引擎组合验收；不得用 Teen 手件或红圈截图裁成生产贴图。
- 本轮继续 Chibi `small/mitten` 腕口研究，目录 `docs/qa/chibi_candidate_2026-11-02/hand_style_study_2026-11-02/`。程序化轮廓按“禁程序化画手”铁律拒绝。AI trial 02/03 失败，04/05 未批准；来源审计排除不合 Chibi 的 generic raw hands 与实际指向 Teen 的 surprised SVG。`extract_chibi_small_hands_reference.py` 从 Chibi `body_full` ROI 精确保留原 RGB/alpha 提取左右可见 small hands；袖下隐藏腕部未补，非 rig-ready part。trial 06 的源 cuff fit（45×43 hand cutouts，source cuff 2,440/2,498 RGBA identity）4×目视失败，见腕口缝隙/暖影/线稿差。用户之后要求“做出这份原画”：trial 07 两方案中 option 2 被用户选作概念方向；检查发现手偏大且双袖口浅纹被简化成单纹，trial-07 source-cuff hand fit 同样失败。基于 trial07 与设定表生成的 trial 08 已打开全身图及 4× wrist board：手缩小、双条纹可见恢复、手腕衔接观感改善，但仍是 AI redraw，手部有两条分指线且 cuff 不是源像素。用户现明确回复 trial 08“非常好，符合了”，因此视觉概念方向获确认；它仍是 AI redraw/WIP，不是 source-pixel 原画或生产件批准。trial08 手像素直接 source-cuff fit 已目视失败（底对齐有明显间隙，袖口对齐则手太短/轮廓过弱）。随后用两张独立 trial09 hand-art study 做 source hand-box 等比试装：左 44×48、右 39×46；源袖口层 2,440/2,498 RGBA pixels 分别精确验证。助手近景检查未见明显静态 cuff 缝，但用户全身审阅明确拒绝 trial09：手在源位置显得太小且不自然、观感差；用户结论优先，trial09 仅保留失败证据、不得复用。trial10 以更宽的左右 AI 单手研究稿做 source-cuff 静态试装，重新打开 4×板与全身 preview 后发现孤立大图入源框后仍压成偏小轮廓，左侧凸方向不自然、右侧叶赘余，内部判失败。为停止继续在源框里硬塞 AI blob，trial11 直接在全身画布修改：双手明显放大，掌体更宽圆钝，左右小 thumb nub 朝身体内侧；与 trial08 的同位全身/3×局部板已本人目视，手明显偏大，用户也明确指出“手确实偏大了”。随后做 trial12/13 两个减小尺寸的全身方向，比较板同列 08/11/12/13 和相同位置左右局部。trial12/13 减小后用户仍反馈“偏大”，且本人目视二者仍明显大于08。trial14 虽回到 trial08 的整体手型 footprint，用户仍反馈“偏大”，故明确否决。随后生成 trial15，双手相对 trial14 进一步缩小；已打开 trial15 原图及 08/11/13/14/15 同位比较板，目视尺寸更小且保留圆钝轮廓与朝内 nub。用户现确认 trial15 的尺寸方向“完全合适”，但仅尺寸获批。随后生成 trial16 左右独立 AI hand art 并套到 Chibi 原 cuff/测量框，制作 source-fit 预览与局部 board。本人重开目视后判艺术门不通过：viewer-left 偏长、viewer-right 偏宽，两边轮廓不一致；线稿/阴影与 source Chibi 不匹配。精确 source cuff mask 保留，但仅为静态试装，未做 hidden-wrist 动画。trial16 只作失败过程证据，不进生产。trial21–23 新手稿迭代仍未达标：左右比例不配或过于镜像。trial24 使用更紧凑的左右 AI mitten 做 source-fit；本人重开 1×全身、4×/7×接缝和2×左右手件后认为尺寸方向正确、左右均读作圆掌 mitten、朝内 nub 可见、静态无明显开缝，源 cuff 像素 byte-exact；但左掌略宽、右 nub 略显、线影仍较 Chibi 源软，故先作为待审 WIP；用户后续称“手基本过关”，本轮决定沿用 trial24 基本形态继续隔离验证，但不等于完整 source-art/hidden-wrist/生产批准。原创 source-aligned mitten art、左右正式层、hidden-wrist 动态覆盖、hand_style 与 wrist/gesture 组合和 C 引擎验收仍未完成；production sprites/rig/generator 未改。制作计划与 WIP 证据见 study 目录。
- **trial24 hidden-wrist follow-up**：重新检查两侧 2×透明 hand parts，y=0 顶行即有宽近水平 alpha 边界（左 x=21–70/92、右 x=25–69/90）；静态 cuff 遮挡不构成 hidden-wrist 完整证据。实际补腕/源件批准与动态露底仍未通过；细节见 GAPS/JOURNAL 与 `trial24_user_feedback_and_reuse_decision_2026-11-03.md`。
- **新隔离复查**：真实 C `zrig` 新渲 9 帧，±30°/0°分别看 normal、hide full forearm、hide mitten；正常样帧接缝目视仍连着，藏 forearm 则露出手件上缘，说明层序/可见性而非腕部补画已验收。trial26 左右延腕编辑仍是 opaque RGB checkerboard，拒绝/no chroma-key/no fit；事实见 trial24 layer board/metrics 与 `trial26_hidden_wrist_art_wip/`。`make test` 本轮 2638/0；未跑 full selfcheck，production 无改动。

- **T70.2 handoff brief**：含 body_full 注册 ROI/小手框、cuff 真值、隐藏腕部、左右独立层、来源禁项与审核交付包；其后已补注 trial07/08 概念进展、trial08 direct-fit 失败、用户拒绝 trial09、trial10 内部失败、用户指出 trial11/12/13 偏大；trial14 被用户指出仍偏大；trial15 尺寸方向获用户确认；trial16 AI source-fit art 自检未通过、仅留 WIP 证据。它仍是规格单而非画稿或生产批准。
- **T70.2 时间预估（估算，不是承诺）**：trial15 的尺寸方向已获用户确认，source art 门仍未通过；trial16 source-fit 配对因左右形态/画风不一致而内部拒绝。下一步继续做一对风格与尺寸一致的独立 Chibi mitten 源稿、hidden-wrist 补画与静态 cuff 审核，之后再进 rig/engine。Chibi sprites 仍只有 `seg_arm_l/r.png`，无 hand parts / `hand_style`；`make_hand_parts.py` 对 Chibi 仅出腕垫片。获批完整原画后，首个隔离 C 引擎双向切换约 2–4 个专注工作日，完整组合矩阵约再加 1–3 天；不包括全身 QA 其余问题。细分估算在 hand-study README。
- **Trial25 续（2026-11-03）**：本轮新生成的独立左右 mitten 图经原尺寸目视和 PNG header 核实，均为无 alpha 的 RGB opaque checkerboard；腕部过长/顶端硬切，描边阴影与 Chibi 不符。已明确拒绝，仅留于 `.../trial25_mitten_art_wip/` 作为负例。此事实没有关闭原画/hidden-wrist/artist approval 门禁；不允许抠假透明或用这些图接生产。
- **Trial24 续（2026-11-03）**：用户认为“（手套）手基本过关”，让我自行决定是否沿用。我重开 trial24 full-body/4×/7× board，选择 trial24 RGBA source-fit pair (46×58 / 45×58; source cuff byte-exact 2440/2498 px) 为隔离 QA 的基本形态继续用。Trial25 opaque RGB 源图不复用。该选择仅支持继续验证，不等于来源画稿、袖下 hidden-wrist 完整、动作安全、最终像素批准或生产晋升。

> ### ★★★ 开工先读这四样（2026-10-25 加第四样）
> 0. **`docs/ENGINE_AUDIT_2026-10-25.md`** —— 底层体检 + Live2D 工序对位 + P0/P1/P2 优化清单。
>    **动引擎之前先读它**，别再从零讨论"要不要网格形变"。
> 1. **`WORKFLOW.md` 零章铁律 0–16** —— 尤其**铁律 3 TRUTH-FIRST**（动手前先拿到
>    **这个领域的真值源**；"先出参考图"只是**动作/姿势类**的真值源，别的领域
>    看**第十三章 方法对位表**）、**铁律 5**（多指标 + 叠图验收）与 Live2D 专项**铁律 9–11**（底层零空洞、关节衣物夹层、跨关节柔性链）与**铁律 12**（标准→实现→陷阱闭环）。
> 2. **`WORKFLOW.md` 第十一章 自欺陷阱清单** —— 十条都真发生过，交付前对照一遍。
> 3. **`REQUEST_LEDGER.md` 最后两问** —— 用户最近在意什么、上一轮欠了什么。

---

## 一、项目一句话
拟人化桌面 AI 伴侣：**Windows 原生 C 桌宠（透明小窗 + 动态立绘）** + （后续）Web 主工作区 +
多家大模型 API + 语音 + 社交。全部内容可自定义、可添加、模块化，不改核心代码。

## 二、用户是谁、怎么沟通
- 用户是中文母语，要求**中文汇报**；喜欢看"实际能跑的东西"而不是计划。
- 用户明确要求：**代理要有思考和记忆**（本目录就是为此存在）；**遇到问题先去六个参考项目源码里查**，
  查不到再上网并记录来源。
- 用户明确要求：**不替用户宣布真机项完成**；不擅自改方向、不擅自删旧文件。
- 用户明确要求：角色/形态/服装/配饰/UI/功能模块**全部可自定义、可添加、模块化**（最高优先级）。

## 三、当前状态（每个代理收工必须更新这一节）
| 项 | 状态 |
| --- | --- |
| C 桌宠基础软件 | ✅ 可运行，`dist/windows/x86_64/zhuochong.exe`（370KB，x86_64 GUI，零依赖） |
| 立绘引擎 | ✅ 数据驱动 rig.json（组/部件/通道曲线/交互区/眨眼五态/视线/换装/**弯曲形变**） |
| 配置体系 | ✅ 5 份配置 + JSON Schema + 精确错误定位，功能默认全关 |
| 测试 | 🟡 本轮 `make test` **2638/0**、`make asset-tool-test` 通过。带隔离 Pillow/Numpy 的 `make selfcheck` 772 项中 1 项失败，唯一项是 Teen/Chibi 正式 rig 的生成器指纹旧（按门禁不提前重建生产 rig）；未跑完整 `make check`。新的 Chibi 来源锁定候选 QA 1342 项中 **34 项失败**；旧候选 1410/40 是另一套结果；不宣称全仓或 Chibi 通过。 |
| 沙箱预览 | ✅ 端口 5173，C 引擎实时渲染，可点击交互；**Web UI 第一版已接入**（`web/` + `/api/*`） |
| 测试台 | ✅ `http://localhost:5173/test.html`（手点：17 个动作 / 四种互动 / 眨眼·视线·缩放滑杆 / 零件表 / 请求日志 / 一键自动测试）；命令行同判据 `make smoke`（`tools/api_smoke.py`，**86 项**）；2026-10-13 加了**口型音素面板**（A/I/U/E/O 按钮 + 强度滑杆 + 念一串 a-i-u-e-o）与**「表情 × 口型」分层看板**（组合按钮 + `参数值 / 过表情后 / 最终` 三列实时表）；smoke 现 **86 项** |
| **素材配准线（第六十一问）** | ✅ `tools/align_redraw.py`：AI 重绘 → 本形态像素系（剪影 Dice 定尺度 + 截尾色差细化 + 逐通道配色），Q 版无臂躯干实测色差 **8.19**、叠图重合；`tools/form_art.py` 做形态级设计图/重绘解析（`aligned_info` 让预配准底图跳过二次配准）。**四个面部件工具已改走 form_art**；Q 版 8 张重绘已入库 |
| **Q 版素材链（T67.67/T67.70）** | 🟡 完整来源锁定 27 步 rebuild：Chibi `design_sheet_chibi.png` + 框 `[628,101,1416,1891]`、567×1292；rig 81 部件/26 动作，1342 项 **34 fail**，缺 16 个 Chibi 挂件。摸头 hitbox 修复后的定向 QA 为 1342 项 **33 fail**，未重跑 full chain。最新眼睫隔离试验查明 C rig 指向 `eye_*_lash_up@2x.png`；只重生 1× 是依赖链漏步。补跑 eye→eyeline→@2x→rig 并重启 C 后，主弧更干净，但外眼角仍有小碎边；定向快照 1310 项 **32 fail**（不是全链，不能与 1342/34、1342/33 相减）。image-29 SHA 已核，作为身份/比例/画风参考而非贴图源。手型、发型/兜帽/衣物和动作矩阵尚未完成；无候选接生产。证据见 `docs/qa/chibi_candidate_2026-11-01/eye_lash_pipeline_trial_2026-11-01/`；历史候选不混算。 |
| **Chibi 参考分流（铁律 13 / T67.68）** | 🟡 image-23 桌宠、image-24 Live2D 锚点、image-25/26/27 负例分开保存；本轮用户选择短发 2、长发 1、双马尾 2 的概念参考并已逐图目视，见 `reference_generated/README.md`。兜帽关系还未验收；概念图不是生产素材。 |
| **Chibi 双手型（T67.69 / A62 / A68.5）** | 🟡 `small` 明确为正常可辨识手指手，`mitten` 是独立手套手，两者必须并存；`small/mitten` 契约和参考已归档。最新候选只由 Chibi 源生成基础手/结构腕垫片；流水线现明确禁止 Teen open/heart 生图进入 Chibi，并省略无 Chibi 来源的 pose-only 参数通道。左右 small/mitten 独立贴图、`hand_style` 选择器与 Chibi 手势图仍未实现。旧 v6 `small/sleeve` 708 项 QA 20 fail、静止差 1768px，不计完成。后续需按 Chibi 来源做独立腕口/手势实引擎视觉回归，Teen 贴图不可代替。详见 `docs/CHIBI_HANDSTYLE_PROGRESS_2026-11-01.md`。 |
| **仓库持久化（铁律 14/15，A63/A65）** | 🟢 新来源锁定候选、失败明细、眼睫依赖链实拍/JSON/patch 与 hash 已归档至 `docs/qa/`；更新 WORKFLOW/REQUIREMENTS/TASKS/GAPS/JOURNAL/LESSONS/REQUEST_LEDGER/MEMORY。阶段 WIP `14cde6b` 已推送并核远端 SHA；不代表全链 QA 通过或接入生产。 |
| 小寻形态 | 🟡 `teen` 完整（rig：**部件 94 / 动作 23 / 组 13 / 参数 71**，手臂已三节拆件 + 原画手件 + 四档发型 + 兜帽四形态 + 猫耳猫尾）；`chibi` 进行中；loli/adult 未开 |
| 拆件与表情 | 🟡 眼睛(睁/闭几何版)、嘴(暗线蒙版)；完整拆件与表情集 = **当前任务** |
| 软件形态 | 🟡 规划完成（`docs/PRODUCT_PLAN.md`）：三进程（桌宠 C / 本地 Web 工作区 / 本地网关）+ 三张注册表（skills / providers / modules）；缺口清单与里程碑已列 |
| 语音合成 | ✅ [沙箱实测] 本地离线神经语音（Piper 中文音色）：`tools/voice_setup.sh` + `tools/voice_local.py`；试听页 `characters/xiaoxun/voice/samples/index.html`（6 样本，含少女音色小雅与升调变体）；等用户选音色后写 `config/voices.json` 并批量渲染台词 |
| UI | 🟡 **第一版可用**（`web/index.html|app.css|app.js`：12fps 轮询 + 动作/情绪/形态/服装/缩放/语音面板）；二次元美术资源与两套主题包未做 |
| 形变（Live2D 式） | ✅ `zimg_draw_warp` 逐像素平滑形变 + `bend_x/bend_y` 通道 + curve(root/sine/linear)；动作 15 个（含 breath / sway） |
| 其余 7 角色 × 4 形态 | ⬜ 未开始（`characters/*/` 只有 `character.json`+`dialogue.json`，**无 forms/**） |
| **物种轴（兽娘）** | 🟡 小寻=猫娘已做；其余 7 个角色的物种**已定并写进 `character.json` 的 `species` 段**，件未做（T47） |
| **装扮轴（节日）** | ⬜ 六套万圣节装扮已设计插槽与规矩，未动工（T48） |
| **关键路径提醒** | 🔴 **G54：网关只会"选谁"，还不会"发请求"** —— 人设/对白/路由等上层能力全卡在它后面 |

## 四、关键决策（已定，不要反复）
1. **技术栈**：纯 C11 + Win32，零第三方依赖（只带 `stb_image.h`）；Windows 用 `zig cc` 交叉编译。
2. **透明与穿透**：`WS_EX_LAYERED + UpdateLayeredWindow`；穿透用 `WM_NCHITTEST` 按角色 alpha
   返回 `HTTRANSPARENT`（像素级），整窗穿透作为托盘开关（`Ctrl+Alt+T`）。
3. **立绘方案**：方法 A——AI 生成部件 PNG + 代码实现 2D 骨骼/仿射形变（不依赖 Live2D 编辑器，
   不引入 Cubism Core）。
4. **眨眼**：五态机（对齐 Live2D CubismEyeBlink）；用 `eye_open`/`eye_closed` 部件交叉淡化，
   因此**表情集到位后自动升级**，不需要改代码。
5. **表情实现**：每个表情 = 一组部件（眼/眉/嘴）的可见性组合，由 rig.json 的 `part_overrides`
   驱动；不把表情烧进整身图。
6. **素材流水线**：AI 生成 → `tools/prepare_sprites.py` 抠图去噪 → `make_parts.py` 拆件 →
   `make_rig.py` 生成 rig.json。**坐标一律由脚本量取，不手写魔法数字。**
7. **发型归类**（用户 2026-10-11 决定）：短发与中长发**都当作发型部件**，属于同一形态内的可换部件。
8. **功能模块**：`config/features.json` 声明，默认全部关闭，可设 token 上限。
9. **数据**：全部只存本机（`logs/`、后续 `data/`）；测试阶段只用中转站，官方直连默认关闭。
10. **参考项目**：只学思路不复制代码（BongoCat-C 是 AGPL）；源码拉到仓库外缓存，用完可删。
11. **音色（2026-10-11 用户定案）**：小寻少女形态 = 云端 **晓伊 zh-CN-XiaoyiNeural 标准版**（不加音调偏移）；
    本地兜底 = 音色包 `xiaoya` + **TD-PSOLA**（只抬基频、保共振峰、时长不变）。音色包机制见 `voices/`；
    手册见 `docs/VOICES.md`。**本地缺真正的少女音色底子**（Piper 只有 3 个中文音色且都偏成年），
    需要用户下载新音色包或训练专属音色。
12. **角色参考图（2026-10-11 用户提供，根目录）**：`小寻.png`（1696×2528）、`小寻短发.png`（1280×1280）、
    `小寻长发.png`（1696×2528），均为**白底**。定位＝**设定参考 + img2img 底稿 + 角色 LoRA 训练数据**，
    **不是素材**（白底无透明通道、尺寸不一，不能直接进 `sprites/`）。已登记 `characters/xiaoxun/design/reference.json`。
13. **训练区（2026-10-11 用户要求）**：软件要能**训练音色模型与 AI 模型**。架构＝训练交给成熟开源工具（kohya /
    LLaMA-Factory / GPT-SoVITS / Piper 官方），软件做"数据集 → 配方 → 执行器（本机 GPU / 远程 SSH / 云 GPU）
    → 模型库 → 评估 → 一键应用"的编排，全流程强制合规声明与 model card。详见 `docs/TRAINING.md`、任务 T15。
    **优先级：角色 LoRA 最先做**——它是"四形态拆件风格一致 + 取景锁死"的根本解法。

## 五、硬性规则（违反即返工）
- 中文汇报与中文注释；注释解释"为什么"，不写废话。
- 新增配置项必须同时写/改 `schemas/*.schema.json`，否则自检会报"缺少 schema"。
- 新增功能必须补单测；`bash scripts/selfcheck_all.sh` 必须全绿才能交付。
- 素材必须过机器验收（透明通道 / 洋红残留 / 白边 / 分辨率 / 色卡），不通过就重生成，最多 3 次。
- 禁止 emoji、禁止用程序画图或 SVG 顶替视觉素材（UI 阶段实现时）。
- 汇报必须标 `[测试锁] / [沙箱实测] / [需真机]`；真机项由用户确认。
- 预览只通过 Arena 预览面板打开，不给外部拼接域名。

**Live2D 专项铁律（详见 `WORKFLOW.md` 零章 9–11）**：
1. **零空洞切件**：底层部件被可动上层遮住时，遮挡区必须延续真实纹理并补完整；禁止用 `alpha=0` 挖洞。只允许真实外轮廓 / 设计透明区透明。
2. **袖口 / 领口前后夹层**：衣物后片—肢体根部—高层前覆盖边构成遮挡，或在肢体根部做自然渐隐并插入足量；禁止肉色断腕 / 断颈压在衣物边缘。
3. **跨关节柔性链**：长发、披肩等跨头颈胸的长件不得整件 100% 刚绑 head；使用分段链 / 渐变权重，头顶约 1.0、肩部过渡约 0.5、末端物理摆动，再以实渲染验收。

## 六、参考项目（六个 + 用户额外指定的 1 个）
见 `docs/REFERENCE_NOTES.md`（含地址、许可、已查阅结论）。速查：
1. vladelaina/BongoCat（C+SDL3，AGPL，只学思路） 2. ayangweb/BongoCat（Rust，Apache-2.0）
3. QCYTSN/ds-local-pet（MIT，状态机/空闲检测已移植） 4. LorisYounger/VPet（Apache-2.0，交互语汇）
5. moeru-ai/airi（MIT，语音四段结构） 6. Live2D/CubismWebFramework（眨眼状态机；Core 不引入）
7. **storytold/photocraft**（用户 2026-10-11 提供：Photoshop 开源移植项目）——
   做素材精修/图层处理时参考它的实现思路，而不是引入 Photoshop。

## 七、文件地图（改代码前先看这里）
- 行为大脑：`src/core/zpet.c`（Windows 与预览共用）
- 立绘引擎：`src/core/zrig.c`（接口 `zrig.h`）
- 状态机：`src/core/zsm.c` ｜ 配置：`src/core/zconfig.c` + `schemas/`
- Windows 层：`src/win32/{main_win.c,zw32.c}` ｜ 预览层：`src/headless/main_headless.c`
- 素材工具：`tools/{prepare_sprites.py,make_parts.py,make_rig.py}`
- 记忆区：`docs/memory/` ｜ 规格：`docs/PROJECT_SPEC.md` ｜ 交接：`docs/HANDOVER.md`

14. **Live2D 的本质（2026-10-11 已查源码）**：每个部件是**独立网格** + 独立绘序 + 遮罩 + 参数驱动的形变层级（deformer）。
    本项目等价实现：rig.json 的部件/层级 + `zimg_draw_warp`（逐像素平滑形变）+ `bend_x/bend_y` 通道（curve=root/sine/linear）。
    **拆件必须每个部件独立、且带自己的形变信息**；缺的只有"部件内细分网格"和"顶点级遮罩"（T12.6）。
    形变曲线语义（2026-10-11 实测定稿）：**底边是根**。root=底固定顶端最大（侧摆）、sine=中段最大（呼吸）、
    linear=线性、tip=顶固定底端最大（后发/裙摆/尾巴）；**X 与 Y 各自带曲线**，不共用。
    单图层素材下，身体 bend 多少，head 组就要跟随多少（脸部系数：root 0.59 / sine 0.66），否则五官会从脸上滑走。
15. **歌声（2026-10-11）**：网上"AI 模仿动漫角色唱歌"= SVC（So-VITS-SVC / RVC）或 DiffSinger，**本地可跑（需 GPU）**；
    合规红线：只能用自有/已授权音源；本项目先做"TTS 唱句 + 音高对齐"，SVC 产物按音色包接入。
16. **参考项目（2026-10-11 第二轮）**：七个全部拉取（~/.cache/zc-refs：bongocat-sdl/-tauri、ds-local-pet、vpet、airi、
    cubism-web-fw、photocraft），关键文件已查验并写入 `docs/REFERENCE_NOTES.md`（含 VPet 的 Mod 接口、airi 的语音流水线、
    Cubism 的 drawMeshWebGL/参数 id、photocraft 的 selection/图层）。
17. **完全自定义（2026-10-11）**：已在 `docs/PRODUCT_PLAN.md` 第七节给出**逐项矩阵**（改哪个文件、是否已实现、怎么验证）；
    新增 i18n/多档案/通知/导入导出/自动化/远程访问 六项缺口（T16）。

18. **物种轴（兽娘，2026-10-22 第三十九问用户定）**：**每个 AI 角色一种基础兽娘**，
    物种是角色自带属性、跨四个形态不变，因此**不乘进形象矩阵**，只乘角色数。
    小寻=猫娘(已做)、深语=鹿娘、拂晓=小熊猫娘、星璇=狐娘、双晞=狼娘、通琳=羊娘、
    月见=兔娘、闪电=猞猁娘。**每种都要能一键关回纯人类少女**。
    已写进八个 `characters/<id>/character.json` 的 `species` 段（机器可读，防遗忘）。
    做法与硬约束见 `docs/FORM_MATRIX.md` 轴 5 + `docs/REFERENCE_NOTES.md` 第五十八批。
19. **装扮轴（节日，2026-10-22 同上）**：天使/恶魔/女巫/吸血鬼/南瓜/幽灵六套，
    **纯叠加件 + 参数差分**，关掉必须逐像素回到原样；先做 pumpkin+ghost 跑通流水线。
20. **TRUTH-FIRST 真值先行（2026-10-22 第三十九问立、第四十问收窄）**：
    原则只有一条 —— **先拿到这个领域的真值源再动手**，真值源按领域取
    （九个领域见 `WORKFLOW.md` 第十三章方法对位表）。用户第四十问原话：
    「代码就是代码的，图画是图画的，底层是底层的，软件是软件的，骨骼是骨骼的，
    **每一个应该都有对应的方法，不要被这一个办法固化了**」。
    其中**动作/姿势类**的真值源 = 参考图，流程 REF-FIRST：**必须先有参考**
    （先查资料带 URL → 用角色自己的底图生成参考图并入库 → 在图上人工读点量角 →
    FK 预演 → 离线模拟 → 落 rig → **实拍并与参考图叠图**）。
    用户原话：「你自己空白无参考做出的挥手动作完全不符合一个人能做出的动作」、
    「先做参考图再做底层，这样会节省很多功夫，不用绕这么多弯子」。
    **只对齐一个数字不算对齐**（LESSONS 321：一个标量约束不了两个自由度）。

---

## 当前状态速览（2026-10-30）

- **当前分支 / 基线**：`arena/aaf1408c-zhuochong`；用户新增的 Live2D 铁律 9–11 已落入 `WORKFLOW.md`，并同步到 `ART_PARTS.md`、本文件、需求总账、请求台账与日志。
- **近期立绘验收**：小寻 teen surprised 的腕口接缝按最新截图进一步收口，手部尺寸约 +8%、局部腕根向袖口内再下移 2 px；实际 5199 服务保持睁眼惊讶峰值。证据 `docs/qa/t31_25_wrist_join_detail.png` 与 `t31_25_surprised_{peak,wireframe,bones,nine_grid}.png`；happy/talk/wave 回归图 `t31_25_regression_happy_talk_wave.png`。该实例是当前验收记录，不替代未来按铁律 9–11 审核其他角色 / 素材。
- **最近门禁**：`make selfcheck` 751/0、`make test` 2617/0、`make smoke` 342/0（本轮腕口微调后）。
- **全局铁律编号**：0–12 已固定；9–11 为 Live2D 专项规则，12 为 Reference-Driven Development，之后只追加，不挪用既有编号。

## 历史状态快照（2026-10-25 第六十四问收工）

- **可模组化已落地**：`tools/mod_lint.py`（内容包/模组包契约，`--all-characters` 1710 项 0 红、
  `--self-test` 14 个坏包全部判红）已进 `make check`；引擎上限收口到 `zrig.h`
  （`ZRIG_FORM_CAP 64 / ZRIG_OUTFIT_CAP 128 / ZRIG_ACTION_CAP 96`），`zpet` 撞上限不再静默丢。
  计划表在 `../PRODUCT_PLAN.md` 第九节，任务在 `TASKS.md` T65。
- **眼件羽化**：Q 版闭/笑/痛三张补片原来是硬切边（半透明 0 px、接缝色差恒 0.0 的假绿），
  已改成沿最终轮廓重铺 5px 软边 + 两条硬自检；重出后半透明 2192/2018 px、色差 3.8~5.7、覆盖 100%。
  瞪大眼另有灰白晕（G65.1），暂保持原样等网格形变。
- **569 底图**：结论**暂不切**（更软但黑边一起放大；黑边是管线级老账，teen 最差）。
  下一步是抠图边缘管线 T65.8，不是换图。
- **下一轮优先级**：T65.8 边缘管线 → G65.2 补片低频亮度 → T65.4 模组装载器 → T64.14 变形器树进 rig。

### S2 交付（2026-10-25，第六十五问续）

- **骨链真的接上了**：`tools/make_rig.py::emit_bone_chains()` 给侧发/后发/呆毛/四条尾巴插
  `root → mid → mesh` 两层旋转骨，中段绑定带 `lag`（根先动、梢慢半拍）。
  teen 网格骨绑定 **18/103**（上一轮是 0/103）、chibi **9/47**。
- 验收：`test_bone_chains()` 5 条断言（刚装载严格恒等 / 变换 == 绑定系数×参数最终值 /
  梢 2.0× 根 / 只推根骨整缕也挪）+ `check_skeleton` 新增「形态必须有骨链」闸（负控 14 例）。
  证据 `logs/asset_qa/s2_bone_chain.png`（侧发梢 −1/0/+1 三档，剪影左缘位移 5.0px）。
- 门禁：`make -s test` **1114/0**、`make -s check`「== 全部保险都过了 ==」、骨架 496/0、selfcheck 576/0。
- **下一步**：裙摆拆件后接链（G66.6 / T66.16）→ 小臂袖子网格骨（T66.17）→
  父级逐顶点位移传子（G58.8 / T66.10）→ 参数层统一接线（T66.4）。

