# zhuochong（桌宠）

**拟人化桌面 AI 伴侣与模块化 AI 工作软件**：以纯 C11/Win32 桌宠和自研 2D 立绘引擎为桌面陪伴入口，同时规划本地 Web 工作区、统一模型网关、语音、多模态、代理与可扩展能力包。项目不依赖 Live2D Cubism Runtime；“Live2D”是制作与交互参考，不代表 `.moc3` / Cubism SDK 兼容。

## 项目不止是立绘

- **桌面陪伴**：C11 核心、Win32 窗口、配置驱动的角色/动作/互动/形变；独立的角色个性、好感与对白系统。
- **连续性与思考节奏**：`zpersona` 合成人设，`zthink` 以可解释、确定性的规则选择回应节奏和主动开口时机，`zmem` 提供本地追加式长期记忆机制。它们是软件行为层，不是绘图功能的附属品。
- **对话与模型接入**：能力/供应商声明式配置、路由、额度预扣与记账、C 侧对话转发；当前支持范围和限制以 `docs/PROVIDER_PLAN.md`、代码及任务台账为准。
- **语音与表现**：TTS/口型/语气演出配置和工具；实时语音、音频设备行为及真机听感仍需按任务状态验收。
- **全能工作流方向**：主工作区、文件与项目上下文、代理编排、Skills、代码执行隔离、图像/视频/3D 生成、训练与评估、多角色协作、自动化和多模态输入。它们并非全部已经实现；规划边界和实现状态分别见 `docs/` 与 `docs/memory/TASKS.md`。
- **安全与尊重**：隐私、权限、勿扰、主动频率和审批有单独设计约束。未授权的屏幕/麦克风采集、外发或高影响操作不得由角色人设或模型自行开启。

核心原则是：陪伴角色要有可追溯的身份与连续性，软件能力要可扩展且受权限约束；两者通过清楚的接口协作，而不是把所有功能塞进立绘循环。

## 仓库结构

| 路径 | 内容 |
| --- | --- |
| `src/core/` | 平台无关 C 核心：角色、rig/渲染、记忆、人设、思考节奏、网关、对话转发与配置校验 |
| `src/win32/` | Windows 原生桌宠窗口与系统集成 |
| `src/headless/` | 使用同一 C 核心的沙箱预览/API 服务 |
| `web/` | 预览产品原型、测试台及 UI 组件 |
| `characters/`、`config/`、`schemas/` | 角色包、能力/供应商/功能配置及其契约 |
| `tools/`、`tests/`、`scripts/` | 资产流水线、质量闸门、测试和维护工具 |
| `docs/` | 产品规格、架构计划、验收记录与代理工作记忆；开始任务前查对应文档和 `docs/memory/` |

## 开发与验证

```bash
make test       # C 核心单元测试
make selfcheck  # 仓库、配置、记忆与契约静态自检
make web-test   # Web 内核与产品视图测试
make check      # 自检、零告警、单测、ASan/UBSan、冒烟与 Web 测试
make preview    # C 引擎沙箱预览，绑定 0.0.0.0:5173
make win        # 交叉编译 Windows 可执行文件（需要仓库工具链中的 zig）
```

运行预览时通过 Arena Live Preview 查看，不要在浏览器代码中写死 `localhost`。自动化结果、沙箱实测和 Windows 真机验收是不同门槛；不得把测试全绿说成视觉或真机验收通过。

## 当前任务与交接

- 总体产品进度与次序：[`docs/ROADMAP.md`](docs/ROADMAP.md)
- 实现任务与未完成项：[`docs/memory/TASKS.md`](docs/memory/TASKS.md)、[`docs/memory/GAPS.md`](docs/memory/GAPS.md)
- 项目行为与隐私边界：[`docs/COMPANIONSHIP_PLAN.md`](docs/COMPANIONSHIP_PLAN.md)、[`docs/PRIVACY_PERMISSIONS_PLAN.md`](docs/PRIVACY_PERMISSIONS_PLAN.md)
- 代理/Skills/工作软件：[`docs/AGENT_PLAN.md`](docs/AGENT_PLAN.md)、[`docs/PLATFORM_PLAN.md`](docs/PLATFORM_PLAN.md)、[`docs/PRODUCT_PLAN.md`](docs/PRODUCT_PLAN.md)
- 当前素材任务的历史交接：[`docs/T67_7_HANDOFF_NEXT_AGENT_2026-10-27.md`](docs/T67_7_HANDOFF_NEXT_AGENT_2026-10-27.md)；其中的分支、临时目录与进程状态是交接时快照，必须以当前 Arena 消息、`git status` 和实际文件为准。
- 代理工作规则与持久记忆：[`docs/memory/WORKFLOW.md`](docs/memory/WORKFLOW.md)、[`docs/memory/MEMORY.md`](docs/memory/MEMORY.md)、[`docs/memory/REQUEST_LEDGER.md`](docs/memory/REQUEST_LEDGER.md)。

## 第三方

项目原创 C 代码。第三方 `src/third_party/stb_image.h` 的许可说明见 `src/third_party/README.md`。参考项目只用于学习并记录来源，不把其代码、模型或美术资产直接复制进仓库。
