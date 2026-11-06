# ZhuoPet · 桌宠

> 一个真正能用的 AI 桌面伴侣。原创分层 Live2D 风格模型、会呼吸和眨眼的物理身体、本地大脑、长期记忆、语音、换装，以及可选的云端大模型。

这是从零重写的新项目。仓库根目录下旧的 C 语言桌宠实验（`src/`、`characters/`、`config/` 等）已废弃，只作为参考保留，不参与构建。

---

## 快速开始

```bash
cd zhuopet
npm install
npm run dev          # 开发预览 http://localhost:5173
npm run build        # 类型检查 + 生产构建到 dist/
npm test             # 48 项测试（引擎 / 大脑 / 模型 / UI）
npm run model:check  # 校验模型包（部件、参数、配色、发型）
npm run model:render # 用 resvg 渲染模型状态图和四角色配色图
```

### 桌面端（Electron）

```bash
npm install
npm run dev          # 终端 1：Vite
npm run electron     # 终端 2：Electron 主进程 + 透明桌宠窗口 + 托盘
```

打包：

```bash
npm run dist         # electron-builder：Windows NSIS/portable、macOS dmg、Linux AppImage
```

> 沙箱里为了节省体积，安装时跳过了 Electron 的二进制下载。你本机执行 `npm install` 时会自动下载，`npm run electron` 即可运行。

---

## 她会做什么

### 桌宠本体
- **原创分层模型**：33 个可动部件、16 组参数、9 种表情、9 个动作。头、脸、眼睛、眉毛、嘴、前发、后发、双马尾、猫耳、呆毛、手臂、腿、裙子、猫尾、星星伙伴全部独立分层。
- **物理与生命感**：二阶弹簧驱动的双马尾、呆毛、猫耳、猫尾；呼吸、眨眼状态机、视线跟随鼠标、歪头、重心摆动、被拎起来时腿会晃、睡着时冒 Z。
- **四种发型**：双马尾、长直发、单马尾、短发，随时切换。
- **四种服装配色**：奶油卫衣、午夜水手、樱花居家、薄荷运动。
- **四种形态/角色**：小寻、月见、双喜、小尘，各有性格、说话方式、配色和语音参数。Q 版 / 少女两种头身比。
- **互动**：点头部摸头、点身体戳一下、拖动、双击聊天、右键菜单、摸头连击、投喂、挥手、转圈圈。

### AI 大脑
- **本地大脑**：意图识别 + 情绪 + 长期记忆 + 关系等级，完全离线，不需要任何 Key。
- **记忆**：说「记住，我喜欢草莓牛奶」「我叫小明」，她会真的记住；问「你还记得吗」会复述；说「忘掉…」会删除。
- **情绪**：开心、兴奋、害羞、惊讶、难过、困困、气鼓鼓、喜欢，会随对话变化，并影响表情、语气和动作。
- **主动陪伴**：安静太久会主动搭话；太久不理她会睡着；深夜会提醒你休息。
- **云端（可选）**：任何 OpenAI 兼容接口（OpenAI / Groq / OpenRouter / 本地 Ollama 等），流式输出，失败自动切回本地大脑。

### 语音
- 浏览器语音合成朗读，可选中文音色、语速、音调、音量。
- 浏览器语音输入（Chrome / Edge）。
- 软软的 Web Audio 音效，无外部音频文件。

### 桌面集成
- Electron 透明无边框窗口、始终置顶、托盘菜单、全局快捷键。
- 小窗桌宠模式（`?mode=pet`），可以只显示角色，鼠标穿透。
- 主窗口 + 小窗桌宠双窗口；位置记忆。
- 快捷键：`Ctrl+Alt+Z` 显示/隐藏主窗口，`Ctrl+Alt+T` 鼠标穿透，`Ctrl+Alt+P` 小窗桌宠。

---

## 界面

- **没有多余卡片**：桌面上只有她。顶部是极简状态栏，底部是动作胶囊。
- **说话**：气泡 + 右侧聊天抽屉；消息默认不显示历史，想看才打开。
- **右键菜单**：跟她说话 / 摸摸头 / 挥挥手 / 换个样子 / 她的性格 / 记忆 / 设置 / 暂时隐藏 / 退出。
- **换装栏**：形态、大小、发型、服装、配饰，一键切换。
- **模型工坊**：实时调参、骨骼/网格叠加、表情预设、部件高亮、导出姿态 PNG / 模型 JSON / SVG。
- **设置**：外观、性格、说话、模型与隐私、高级、关于。所有数据只存本机。

---

## 架构

```
zhuopet/
├─ src/
│  ├─ assets/character.svg        # 原创分层角色（所有部件、可动组、表情差分）
│  ├─ model/
│  │  ├─ xiaoxun.model.json       # 模型包：部件、pivot、z-order、参数、表情、动作
│  │  ├─ palettes.json            # 四角色配色
│  │  ├─ engine.ts                # 弹簧物理、眨眼、视线、情绪、动作状态机
│  │  ├─ applyPose.ts             # 把 Pose 写进 SVG transform / opacity
│  │  └─ types.ts
│  ├─ ai/
│  │  ├─ brain.ts                 # 本地大脑：意图、记忆、情绪、回复
│  │  └─ provider.ts              # OpenAI 兼容流式接口
│  ├─ store/usePetStore.ts        # zustand + localStorage 持久化
│  ├─ components/                 # 桌面、聊天、设置、模型工坊、换装、菜单
│  ├─ utils/                      # 语音合成、音效
│  └─ styles.css                  # 设计系统
├─ electron/                      # 主进程、preload、托盘图标
├─ scripts/                       # 模型校验/渲染、无头浏览器 QA
├─ tests/                         # 48 项测试
├─ public/models/xiaoxun/         # 可下载的模型包（构建时同步）
└─ docs/                          # 模型格式、设计、QA
```

### 渲染管线

1. `character.svg` 里每个可动部件是一个 `<g data-part="...">`，带 `data-eyeball` / `data-mouth` / `data-hairstyle` 标记。
2. `CharacterSvg` 把 SVG 注入一次，之后每帧只改 `transform` 和 `opacity`，不触发 React 重渲染。
3. `PetEngine` 以固定子步长积分弹簧，计算姿态 `Pose`。
4. `applyPose` 把 `Pose` 写成 SVG 变换：绕关节旋转、头部九轴、视线、眨眼差分、嘴型差分、腮红、马尾/呆毛/猫尾物理。
5. 配色通过 CSS 变量注入，切换角色/服装是即时的，不需要重新加载图片。

### 模型格式

参数命名与 Live2D Cubism 的 `Param*` 约定对齐（`ParamAngleX/Y/Z`、`ParamEyeOpen`、`ParamMouthOpen`、`ParamArmLA/RA`、`ParamTwinL/R`、`ParamAhoge`、`ParamBreath`…），但这是**原创的分层 SVG 模型格式**，不是 Live2D 官方 `.moc3`。详见 [`docs/MODEL_FORMAT.md`](docs/MODEL_FORMAT.md)。

---

## 测试与 QA

- `npm test`：48 项，覆盖弹簧稳定性、眨眼/睡眠/说话/挥手、意图识别、记忆抽取/回忆/遗忘、情绪、模型包完整性、完整 UI 流程（打开聊天、发消息、记忆、设置、模型工坊、首次引导）。
- `npm run model:check`：模型包静态校验。
- `node scripts/qa-browser.mjs`：无头 Chromium 真实浏览器 QA，检查布局溢出、控制台错误、聊天/换装/设置/模型工坊、移动端适配，并导出截图到 `docs/qa/`。
- 视觉 QA 证据：`docs/qa/qa_*.png`、`docs/qa/model_states.png`、`docs/qa/model_palettes.png`。

---

## 隐私

- 没有账号、没有埋点、没有上传。
- 聊天、记忆、设置只存在浏览器 `localStorage`（桌面端在 Electron 的 userData）。
- 只有你自己填写云端 API Key 并开启开关时才会联网；Key 只存本机，导出备份时自动清空。
- 语音合成使用浏览器内置能力，不发送音频到第三方。

---

## 已知边界

- 模型是原创 SVG 分层模型，不是 Live2D Cubism 官方格式；不包含任何 Live2D 官方素材或 `.moc3`。
- 云端大模型需要你提供 OpenAI 兼容的 API Key；不填也能用本地大脑。
- 浏览器语音合成依赖系统音色，Chrome / Edge 的中文音色最完整。
- 沙箱内没有安装 Electron 二进制；桌面端功能代码已就绪，需在本机 `npm install` 后运行。

角色、模型、代码均为本项目原创。
