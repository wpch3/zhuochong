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
> 规则：**每次工作开始先读本文件与自己上次的日志；结束时必须追加 `JOURNAL.md` 并更新本文件的"当前状态"。**
> 用户的新要求**当轮就要写进 `REQUIREMENTS.md`**，不许只留在聊天里。

更新：2026-10-11 ｜ 分支：`arena/cc642f66-zhuochong` ｜ 版本：0.1.0

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
| 测试 | ✅ [测试锁] **217 项**单测 + `scripts/selfcheck_all.sh` 六步全绿 |
| 沙箱预览 | ✅ 端口 5173，C 引擎实时渲染，可点击交互；**Web UI 第一版已接入**（`web/` + `/api/*`） |
| 小寻形态 | 🟡 只有 teen 一形态、全身单图层（手臂/上下半身未分段）；用户要求**重做形象** |
| 拆件与表情 | 🟡 眼睛(睁/闭几何版)、嘴(暗线蒙版)；完整拆件与表情集 = **当前任务** |
| 软件形态 | 🟡 规划完成（`docs/PRODUCT_PLAN.md`）：三进程（桌宠 C / 本地 Web 工作区 / 本地网关）+ 三张注册表（skills / providers / modules）；缺口清单与里程碑已列 |
| 语音合成 | ✅ [沙箱实测] 本地离线神经语音（Piper 中文音色）：`tools/voice_setup.sh` + `tools/voice_local.py`；试听页 `characters/xiaoxun/voice/samples/index.html`（6 样本，含少女音色小雅与升调变体）；等用户选音色后写 `config/voices.json` 并批量渲染台词 |
| UI | 🟡 **第一版可用**（`web/index.html|app.css|app.js`：12fps 轮询 + 动作/情绪/形态/服装/缩放/语音面板）；二次元美术资源与两套主题包未做 |
| 形变（Live2D 式） | ✅ `zimg_draw_warp` 逐像素平滑形变 + `bend_x/bend_y` 通道 + curve(root/sine/linear)；动作 15 个（含 breath / sway） |
| 其余 6 角色 × 4 形态 | ⬜ 未开始 |

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
