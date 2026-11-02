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

更新：**2026-11-03（T70.2：trial 08 全身视觉方向获用户确认；trial 08 direct hand-fit 失败；trial 09 被用户拒绝；trial 10 更宽 mitten 仍在源位置过小/不自然、内部判失败；需要用户/美术给出可接受的全身手型方向；无生产手层/隐藏腕部/C-engine 验收；A66.1–A66.2/T70.1–T70.4；T67.70 眼部仍失败；旧全链基线 1342/33 fail）** ｜ 当前分支：`arena/aaf1408c-zhuochong` ｜ 版本：0.1.0

## 最新状态（2026-11-03）

- 本轮参考资料审计已归档：运行时、网格、遮罩与绑定方法资料足以继续自研；Chibi 自身全身差分稿、合规 `small/mitten` 手型设计板和组合验收仍不足。
- 资料报告：`docs/memory/CHIBI_LIVE2D_REFERENCE_AUDIT_2026-11-02.md`；canonical 索引是 `docs/REFERENCE_NOTES.md`（第六十八批审计、T70.2 cuff 方法和第七十一批官方拆件/来源资格复核）。A66.1 是参考审计，A66.2 是持续按铁律查方法、隔离制作并本人目视的流程提醒（A59 已被既有 Live2D 铁律占用）；执行任务 T70.1–T70.4。
- 当前 Chibi 配置驱动隔离全链为 **1,342 项 / 33 fail / pass=false**。眼缘 underlay 局部工作不是全身通过；生产素材/rig 未因这次审计变更。
- 最新静态自检：772 项、1 项既有生成器指纹失败（Teen 与 Chibi `rig.json` 过期）；其余 771 项通过。未为压绿门禁重生受保护生产 rig。`roadmap_status.py` 一致，`git diff --check` 通过。
- 后续仍需按用户要求完成整身拆件、差分发型/兜帽、眼口、small/mitten 独立手型、服装遮挡、动作和真实 C 引擎组合验收；不得用 Teen 手件或红圈截图裁成生产贴图。
- 本轮继续 Chibi `small/mitten` 腕口研究，目录 `docs/qa/chibi_candidate_2026-11-02/hand_style_study_2026-11-02/`。程序化轮廓按“禁程序化画手”铁律拒绝。AI trial 02/03 失败，04/05 未批准；来源审计排除不合 Chibi 的 generic raw hands 与实际指向 Teen 的 surprised SVG。`extract_chibi_small_hands_reference.py` 从 Chibi `body_full` ROI 精确保留原 RGB/alpha 提取左右可见 small hands；袖下隐藏腕部未补，非 rig-ready part。trial 06 的源 cuff fit（45×43 hand cutouts，source cuff 2,440/2,498 RGBA identity）4×目视失败，见腕口缝隙/暖影/线稿差。用户之后要求“做出这份原画”：trial 07 两方案中 option 2 被用户选作概念方向；检查发现手偏大且双袖口浅纹被简化成单纹，trial-07 source-cuff hand fit 同样失败。基于 trial07 与设定表生成的 trial 08 已打开全身图及 4× wrist board：手缩小、双条纹可见恢复、手腕衔接观感改善，但仍是 AI redraw，手部有两条分指线且 cuff 不是源像素。用户现明确回复 trial 08“非常好，符合了”，因此视觉概念方向获确认；它仍是 AI redraw/WIP，不是 source-pixel 原画或生产件批准。trial08 手像素直接 source-cuff fit 已目视失败（底对齐有明显间隙，袖口对齐则手太短/轮廓过弱）。随后用两张独立 trial09 hand-art study 做 source hand-box 等比试装：左 44×48、右 39×46；源袖口层 2,440/2,498 RGBA pixels 分别精确验证。助手近景检查未见明显静态 cuff 缝，但用户全身审阅明确拒绝 trial09：手在源位置显得太小且不自然、观感差；用户结论优先，trial09 仅保留失败证据、不得复用。trial10 依照“更宽、更有力的手型”重新生成左右 AI 单手研究稿并作 source-cuff 静态试装，重新打开 4×板与全身 preview 后发现：孤立大图在源框内仍压成偏小轮廓，左手侧凸方向不自然、右手侧叶赘余，全身仍不合格；trial10 内部判失败，仅保留证据。原创 source-aligned mitten art、左右独立生产层、hidden-wrist 动态覆盖、hand_style 与 wrist/gesture 组合和真实 C 引擎验收仍未完成；production sprites/rig/generator 未改。不要继续 AI blob 试装/微调；需用户或美术提供/确认全身可接受的手型与相对尺寸方向。研究输出、metrics 与 SHA 在隔离 study 目录。

- **T70.2 handoff brief**：含 body_full 注册 ROI/小手框、cuff 真值、隐藏腕部、左右独立层、来源禁项与审核交付包；其后已补注 trial 07/08 概念进展、trial08 direct-fit 失败、用户对 trial09 fullbody fit 的拒绝，以及 trial10 更宽 silhouette 仍失败。它仍是规格单而非画稿或生产批准。
- **T70.2 时间预估（估算，不是承诺）**：可查看用户确认视觉方向的 trial08 全身 WIP，以及已拒绝的 trial09、trial10 source-cuff failure studies。合格 source-aligned、含袖下隐藏腕部的原画仍是日历阻塞项；现阶段还需明确可接受的全身手型/尺寸方向，缺此输入无法估日期。Chibi sprites 仍只有 `seg_arm_l/r.png`，无 hand parts / `hand_style`；`make_hand_parts.py` 对 Chibi 仅出腕垫片。获批后首个隔离 C 引擎双向切换约 2–4 个专注工作日，完整组合矩阵约再加 1–3 天；不包括全身 QA 其余问题。细分估算在 hand-study README。

> ### ★★★ 开工先读这四样（2026-10-25 加第四样）
> 0. **`docs/ENGINE_AUDIT_2026-10-25.md`** —— 底层体检 + Live2D 工序对位 + P0/P1/P2 优化清单。
>    **动引擎之前先读它**，别再从零讨论"要不要网格形变"。
> 1. **`WORKFLOW.md` 零章铁律 0–15** —— 尤其**铁律 3 TRUTH-FIRST**（动手前先拿到
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
| **Chibi 双手型（T67.69 / A62）** | 🟡 `small/mitten` 契约和红圈参考已归档。最新候选只由 Chibi 源生成基础手/结构腕垫片；流水线现明确禁止 Teen open/heart 生图进入 Chibi，并省略无 Chibi 来源的 pose-only 参数通道。左右 small/mitten 独立贴图、`hand_style` 选择器与 Chibi 手势图仍未实现。旧 v6 `small/sleeve` 708 项 QA 20 fail、静止差 1768px，不计完成。后续需按 Chibi 来源做独立腕口/手势实引擎视觉回归，Teen 贴图不可代替。详见 `docs/CHIBI_HANDSTYLE_PROGRESS_2026-11-01.md`。 |
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

