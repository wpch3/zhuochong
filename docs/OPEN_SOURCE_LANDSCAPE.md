# 同类开源项目调研（2026-10-23，第五十问）

> 口径：第十八问「不会的先查资料、结论带 URL 落档」。本文只收**实访过**的仓库，
> 每条写清"它解决了什么 / 我们能抄什么 / 我们和它的差别"。
> 原始链接另存一份在 `docs/REFERENCE_NOTES.md` 第六十四批。

## 0. 一句话结论

- **功能对标**：`Open-LLM-VTuber` 是目前最接近"Neuro-sama 式 AI 桌宠"的开源实现，
  它证明了我们这条路（本地优先 + 可插拔供应商 + 桌宠模式）是成立的；
  但它的**立绘是别人家的 Live2D 模型**，渲染靠官方 Web SDK。
- **引擎对标**：`Inochi2D`（BSD-2，D 语言）和 `iki`（MIT，TS/WebGL2）是和
  `src/core/zrig.c` 同一层的东西。**`iki` 的定位和我们几乎重合**
  （纯 JSON 模型格式 + schema + spring 物理 + 自带 MCP 让 AI 绑模型），
  是最值得逐条对表的参照物。
- **我们独有**：从**原画 PNG 自动切件 → 自动绑骨 → 自动验收（check_assets 1558 项）**
  这条全自动流水线，上面两类项目都没有 —— 他们假设"模型是人在 Cubism 里做好的"。

## 1. AI × VTuber × 桌宠（应用层）

| 项目 | 栈 | 关键能力 | 对我们的意义 |
|---|---|---|---|
| **[Open-LLM-VTuber](https://github.com/Open-LLM-VTuber/Open-LLM-VTuber)** 14.2k★ | Python FastAPI + Electron | 语音打断、视觉感知、Live2D 表情映射、**桌宠模式＝透明背景/全局置顶/鼠标穿透**；ASR/TTS/LLM 全可换、可全离线；后端 MIT | **最接近的对标**。桌宠模式的三件套（透明窗/置顶/点击穿透）是我们桌面端要抄的；它 v1.2.0 把前端换成官方 Live2D Web SDK 以支持 Cubism 5 —— 我们没有这个包袱（自研 zrig，格式自有） |
| [Open-LLM-VTuber-Web](https://github.com/Open-LLM-VTuber/Open-LLM-VTuber-Web) | Electron/React | 上面的前端 | 前端分层（桌宠窗 / 设置窗）可参照 |
| [Soul-of-Waifu](https://github.com/jofizcd/Soul-of-Waifu) | Python | Live2D/VRM + 本地 LLM | 本地模型区块的 UI 参考 |
| [LLM-Live2D-Desktop-Assitant](https://github.com/ylxmf2005/LLM-Live2D-Desktop-Assitant) | Electron | 读屏 / 剪贴板 / 唤醒词 | "感知桌面"这类主动触发源 |
| [xkk6663/Mao](https://github.com/xkk6663/Mao) | — | **统一 12-phase 状态总线 + 可插拔 Agent 适配器**，桌宠本身无状态、只认 phase | 和我们"网关决策 → 表现层"的分层同构，**phase 枚举可直接借鉴**给 mood/动作仲裁 |
| [suntianc/ViviPet](https://github.com/suntianc/ViviPet) | — | Agent Adapter 开 `:18765`，用**语义事件**控宠 | 比"直接调 API 设参数"更高一层的接口形态，对应我们 T46.61 的"LLM 工具协议" |
| [lmy375/ai-pet](https://github.com/lmy375/ai-pet) | Tauri2 + Rust + PIXI | 多 agent 群聊 + **心跳自发**（没人理也会自己说话） | 陪伴感的关键机制（G69~G78 那条线） |
| [qiyueblues/zhuomianling](https://github.com/qiyueblues/zhuomianling) / [x380kkm/Live2DPet](https://github.com/x380kkm/Live2DPet) / [MARS-HX/Live2DPet-modern](https://github.com/MARS-HX/Live2DPet-modern) / [git2968/Desktop-pet](https://github.com/git2968/Desktop-pet) | Electron / Python | 中文桌宠；`Desktop-pet` 带 MCP + Vosk 离线语音 | 中文语境下的交互习惯样本 |

选型矩阵（HuggingFace 讨论串
<https://discuss.huggingface.co/t/an-ai-streaming-buddy-like-neuro-sama/172830>）：
**Open-LLM-VTuber（最开箱）＞ AIRI ＞ ChatdollKit（Unity/3D）＞ Pipecat（纯语音管线）**。

## 2. 2D 骨骼 / 木偶引擎（和 `zrig.c` 同层）

| 项目 | 许可 | 栈 | 有而我们没有 | 我们有而它没有 |
|---|---|---|---|---|
| **[Inochi2D](https://github.com/inochi2d/inochi2d)** 1.8k★ | BSD-2 | D 语言，另有 Rust 的 [inox2d](https://github.com/Inochi2D/inox2d) | 开放 puppet 标准 + 配套编辑器（inochi-creator / inochi-session）、成熟的网格编辑 | 自动切件/自动绑骨/闸门体系；它**不兼容 .moc3**，生态要自己从零搭 |
| **[iki](https://github.com/zeikar/iki)** | MIT | TypeScript + WebGL2 | **schema 校验的纯 JSON 模型格式**、warp-mesh、stencil 遮罩、**spring-chain 物理**、`@ikijs/mcp`——**让 AI 直接从按图层命名的 PNG 自动绑定** | 我们的 rig.json 也是纯 JSON，但多了动作系统/表情/互斥组/1558 项验收；它的 MCP 绑定链路正是我们 T46.61 要做的形态 |
| [rigby2d](https://github.com/jaisurya-dev-art/rigby2d) | — | Spine 格式编辑器 | **IK / path / physics 约束** + MCP server | 我们 ❌ 缺 IK（T46.62 已登记） |
| [Anim2D](https://github.com/turtlegameworks/Anim2D) | — | — | 轻量骨骼动画 | — |

## 3. 下一步怎么用这些结论

1. **桌面端**（未开工）：直接照 `Open-LLM-VTuber` 的桌宠三件套
   （透明背景 / 全局置顶 / 鼠标穿透）定需求，不要自己发明。
2. **AI 自驱**（T46.61，前置 G54）：接口形态参照 `ViviPet` 的**语义事件**
   与 `Mao` 的 **phase 总线**，而不是让 LLM 直接写参数值。
3. **引擎补课**（T46.62）：IK 看 `rigby2d`，物理链与 JSON schema 看 `iki`，
   网格/遮罩看 `Inochi2D`。
4. **不抄的部分**：他们的模型都靠人在 Cubism/编辑器里手工绑；
   我们这条"原画 → 自动切件 → 自动绑骨 → 自动验收"的链路是自己的护城河，
   继续沿 `docs/SHEET_PIPELINE.md` 走。
