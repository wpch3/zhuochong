# 本地记忆（MEMORY）—— 每个代理开工先读、收工必更新

> 这是项目的**本地记忆主文件**：记录"项目是什么、现在到什么程度、做过哪些决定、哪些是硬性规则"。
> 配套：`TASKS.md`（任务与计划）、`JOURNAL.md`（思考与工作日志）、`LESSONS.md`（教训与陷阱）。
> 规则：**每次工作开始先读本文件与自己上次的日志；结束时必须追加 `JOURNAL.md` 并更新本文件的"当前状态"。**

更新：2026-10-11 ｜ 分支：`arena/b3359546-zhuochong` ｜ 版本：0.1.0

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
| 立绘引擎 | ✅ 数据驱动 rig.json（组/部件/通道曲线/交互区/眨眼五态/视线/换装） |
| 配置体系 | ✅ 5 份配置 + JSON Schema + 精确错误定位，功能默认全关 |
| 测试 | ✅ [测试锁] 96 项单测 + `scripts/selfcheck_all.sh` 六步全绿 |
| 沙箱预览 | ✅ 端口 5173，C 引擎实时渲染，可点击交互 |
| 小寻形态 | 🟡 只有 teen 一形态、全身单图层（手臂/上下半身未分段）；用户要求**重做形象** |
| 拆件与表情 | 🟡 眼睛(睁/闭几何版)、嘴(暗线蒙版)；完整拆件与表情集 = **当前任务** |
| 语音合成 | ✅ [沙箱实测] 本地离线神经语音（Piper 中文音色）：`tools/voice_setup.sh` + `tools/voice_local.py`；试听页 `characters/xiaoxun/voice/samples/index.html`（6 样本，含少女音色小雅与升调变体）；等用户选音色后写 `config/voices.json` 并批量渲染台词 |
| UI | ⬜ 未开始（用户：测试程序不需要 UI 时先做拆件） |
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
