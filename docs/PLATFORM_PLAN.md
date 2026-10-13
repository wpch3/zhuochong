# 全能桌宠平台 · 框架计划

> 用户 2026-10-13 的要求（原话要点）：桌宠要有 **API 连接功能**，含 **token 余额识别、
> 日常聊天、任务处理、工作区、文件区、记忆区**，可兼容 **代理功能**、**skills**，
> 以及 **生图 / 生视频 / 生代码 / 生建模**，**本地 AI 和网络 AI 都要兼容**，
> "反正到 2027 年以内 AI 能做到的所有事情和功能都要加进去"，以及**陪伴功能**，
> 包括 **neuro-sama 的模仿开源项目功能**，做到**真正的思考载入**。
> **"但是这个是计划先把框架做好才行。"**
>
> 这份文档就是那个框架计划。实施进度见 `docs/memory/TASKS.md` 的 T20 系列与
> `docs/memory/GAPS.md` 的 G5x 系列。

---

## 零、这份计划的一条总原则

**"2027 年以内 AI 能做到的所有事"是列不完的清单 —— 所以框架不能去列它。**

框架要做的是：让"加一种新能力"这件事**不需要改框架**。
具体落成三条硬规矩（和用户 A1「不改核心代码就能新增内容」是同一条）：

1. **能力是注册出来的，不是写死的。** 新增"生 3D 模型"只是多一份能力清单文件，
   内核一行不改。
2. **供应商和能力解耦。** 同一个"生图"能力，底下可以是 OpenAI、本地 ComfyUI、
   或者还没出生的某家 2027 年的服务；换供应商不影响调用方。
3. **一切外部调用都经过网关。** 记账、限额、重试、密钥、脱敏只在一个地方做，
   不散落在每个功能里。

---

## 一、分层：七层，每层只认下一层的契约

```
┌──────────────────────────────────────────────────────────────┐
│ L7 表现层    web/ 组件 + layout.json（✅ G1 已完成）              │
│              桌宠立绘 / 聊天框 / 工作区 / 文件区 / 设置面板         │
├──────────────────────────────────────────────────────────────┤
│ L6 人格层    角色设定 · 情绪 · 好感 · 主动行为 · 陪伴节律           │
│              （立绘与动作已完成；"思考载入"在这一层落地）            │
├──────────────────────────────────────────────────────────────┤
│ L5 智能体层  任务分解 → 计划 → 执行 → 反思；多步骤、可中断、可回放    │
│              skills（Agent Skills 规范）· 代理（agent/子代理）      │
├──────────────────────────────────────────────────────────────┤
│ L4 能力层    capability：chat / image / video / code / model3d /  │
│              tts / stt / embed / rerank / vision / websearch …   │
│              **能力是注册项，不是枚举常量**                        │
├──────────────────────────────────────────────────────────────┤
│ L3 供应商层  provider：openai / anthropic / gemini / deepseek /   │
│              ollama / llamacpp / comfyui / 本机脚本 / MCP server  │
│              每个 provider 声明：支持哪些能力、定价、余额怎么查       │
├──────────────────────────────────────────────────────────────┤
│ L2 网关层    路由 · 重试 · 并发 · 配额 · **用量记账** · 密钥保管    │
│              （参考 one-api 的多供应商分发，但只跑在本机）           │
├──────────────────────────────────────────────────────────────┤
│ L1 资源层    工作区 workspace · 文件区 files · 记忆区 memory ·     │
│              沙盒 sandbox（执行生成的代码/脚本）                    │
└──────────────────────────────────────────────────────────────┘
```

**L4 与 L3 的分界是整个框架的关键。** 调用方永远说"我要一张图"（能力），
从不说"我要调 OpenAI"（供应商）。供应商是网关按策略挑的。

---

## 二、四份契约（框架的全部骨头）

框架本身就是这四份 JSON 契约 + 校验它们的闸门。其余都是填内容。

### 2.1 能力 `config/capabilities/<id>.json`

```jsonc
{
  "id": "image.generate",
  "name": "生成图片",
  "kind": "generate",            // generate | transform | analyze | stream
  "input":  { "prompt": "text", "size": "enum?", "ref_images": "file[]?" },
  "output": { "images": "file[]" },
  "unit":   "image",             // 计量单位：token / image / second / call
  "ui":     { "panel": "gallery", "icon": "image" }
}
```

首批登记（用户点名的全在内）：
`chat.completion`、`chat.stream`、`image.generate`、`image.edit`、`video.generate`、
`code.generate`、`code.execute`、`model3d.generate`、`tts.speak`、`stt.listen`、
`embed.text`、`vision.describe`、`web.search`、`file.read`、`memory.recall`。

### 2.2 供应商 `config/providers/<id>.json`

```jsonc
{
  "id": "openai",
  "name": "OpenAI",
  "base_url": "https://api.openai.com/v1",
  "auth": { "type": "bearer", "key_ref": "secret://openai" },   // 密钥不入库
  "local": false,
  "capabilities": [
    { "cap": "chat.completion", "model": "gpt-4o-mini",
      "price": { "in": 0.15, "out": 0.6, "per": 1000000, "currency": "USD" } },
    { "cap": "image.generate", "model": "gpt-image-1",
      "price": { "unit": 0.04, "per": 1, "currency": "USD" } }
  ],
  "balance": { "mode": "api", "path": "/dashboard/billing/credit_grants" }
}
```

`balance.mode` 三选一，**这就是"token 余额识别"**：
- `api` —— 供应商有余额接口，直接查；
- `ledger` —— 没有接口，用本机账本倒推（充值额 − 已用额）；
- `none` —— 本地模型，不计费（`ollama` / `llamacpp` / `comfyui` 走这条）。

### 2.3 技能 `skills/<name>/SKILL.md` —— **直接采用 Agent Skills 规范**

```markdown
---
name: office-export
description: 把对话结论导出成 Word/Excel。当用户要"导出报告/做表格"时使用。
---
# Office Export
## 步骤
1. ...
```

**不自造格式**：`super-agent-party` 用的就是这套（见 `docs/REFERENCE_NOTES.md` 第十一批），
整个 Claude Skills 生态的技能包可以直接放进 `skills/` 目录用。
目录里可带 `assets/`（模板）与 `references/`（规格），正文只写"怎么做"。

### 2.4 任务 `data/tasks/<id>.json`（运行时产物，不入库）

```jsonc
{
  "id": "t_20261013_001", "title": "把这周的日志整理成周报",
  "state": "running",            // queued | running | waiting_user | done | failed | cancelled
  "steps": [
    { "n": 1, "do": "file.read", "args": {...}, "state": "done", "cost": {...} },
    { "n": 2, "do": "chat.completion", "state": "running" }
  ],
  "workspace": "ws_weekly", "cost_total": { "tokens": 12840, "cny": 0.31 }
}
```

---

## 三、资源区：工作区 / 文件区 / 记忆区

三者都落在 `data/` 下，**只存本机**（用户 B12 硬要求），`.gitignore` 掉。

| 区 | 路径 | 是什么 | 谁在用 |
| --- | --- | --- | --- |
| 工作区 | `data/workspaces/<ws>/` | 一个任务/项目的上下文容器：文件、对话、产物、历史 | L5 智能体 |
| 文件区 | `data/files/` + 索引 `files.jsonl` | 用户投进来的素材与生成产物，带标签/来源/校验和 | 全部层 |
| 记忆区 | `data/memory/` | 三层：`profile`（长期事实）/ `episodic`（对话片段）/ `working`（当前上下文） | L6 人格层 |

**记忆区的三层划分**是"真正的思考载入"的地基：
长期事实决定它"认识你"，情景记忆决定它"记得上次那件事"，
工作记忆决定它"现在在想什么"。检索用向量（`embed.text` 能力）+ 时间衰减 + 重要度加权。

---

## 四、"真正的思考载入" —— 落成可验收的四件事

这句话容易变成空话，所以拆成四个**能看见、能测**的东西：

1. **思考是可见的**：每次回应前产出一段 `thought`（内部独白），
   UI 上可折叠查看，不混进台词。
2. **思考是连续的**：空闲时也在跑（低频），产出"主动话题"候选，
   而不是只有你说话它才醒 —— 这是陪伴感的来源（neuro-sama 的核心观感）。
3. **思考是有据的**：每段思考记录它引用了哪几条记忆、哪几个文件，可回溯。
4. **思考是会反思的**：任务失败后写一条教训进记忆区，下次同类任务读得到。

---

## 五、兼容面（"本地也行、网络也行"怎么落地）

| 要兼容的东西 | 做法 |
| --- | --- |
| 网络 AI | provider 清单 + OpenAI 兼容协议（绝大多数服务都兼容这一套） |
| 本地 AI | 同一份 provider 契约，`local: true`、`balance.mode: none`；ollama / llama.cpp / ComfyUI |
| **MCP** | 一个 `provider.kind = "mcp"` 的适配器：把 MCP server 的 tools 映射成能力。**接一次，白嫖整个 MCP 生态**（官方 servers 仓库 ★91k） |
| 代理（网络代理） | 网关层统一出口：`config/gateway.json` 的 `proxy` 字段，所有 provider 共用 |
| 代理（AI agent） | L5 的子代理：一个 agent 就是"带独立 workspace + 受限能力集"的任务执行者 |
| OpenAI 兼容的第三方中转 | 就是普通 provider，填 `base_url` 即可（one-api / new-api 这类） |

---

## 六、里程碑（框架优先，功能后填）

**P0 框架骨架**（当前）
- [x] L7 组件化（G1）
- [ ] **G50 契约与注册表**：四份 schema + 加载器 + 校验闸门（能力/供应商注册表）
- [ ] G51 网关骨架：路由 + 记账 + 密钥引用（不含真实请求）
- [ ] G52 资源区骨架：workspace / files / memory 的目录契约与索引
- [ ] G53 任务机：队列 + 状态机 + 可中断 + 回放

**P1 接通第一条真链路**
- [ ] G54 chat.completion 打通（OpenAI 兼容 + ollama 本地），聊天框 UI
- [ ] G55 余额与用量：真实记账落 `data/usage.jsonl`，替掉现在的占位卡
- [ ] G56 skills 装载（Agent Skills 规范）+ 技能面板

**P2 多模态与智能体**
- [ ] G57 image/video/model3d 能力接入（含本地 ComfyUI）
- [ ] G58 code.generate + code.execute（沙盒，参考 nekro-agent）
- [ ] G59 MCP 适配器
- [ ] G60 任务分解与子代理

**P3 陪伴与思考**
- [ ] G61 记忆区三层 + 向量检索
- [ ] G62 思考循环（内部独白 / 主动话题 / 反思写回）
- [ ] G63 把人格层接到立绘表情与动作（已有的 41 项参数是现成的表达通道）

---

## 七、范围边界（这轮**不做**什么，免得摊成空壳）

- 不做云端账号体系 —— 一切只在本机（用户 B12）。
- 不做模型训练（那是 T15/G12 的事，另有计划 `docs/TRAINING.md`）。
- 不在沙箱里接真实外部 API（出网白名单只有 github/pypi/npm），
  **框架用假 provider 跑通，真 key 在用户机器上填**。
- 不复制 AGPL 代码（super-agent-party 是 AGPL，只看结构不抄实现）。

---

## 八、这份计划凭什么说是"照着做过功课的"

逐条参考见 `docs/REFERENCE_NOTES.md` 第十一批，核心五个：

| 参考 | 看它什么 |
| --- | --- |
| `moeru-ai/airi` ★50347 MIT | **就是 neuro-sama 的开源重建**（用户点名的那类项目）。看它的模块切分与陪伴设计 |
| `heshengtao/super-agent-party` ★2733 AGPL | 自称 "self-hosted neuro sama"，功能面与用户要求几乎一一对应；**skills 目录结构直接可借鉴** |
| `elizaOS/eliza` ★19586 MIT | 自称 "agentic operating system"：插件 drop-in 装载、核心/第三方分区、denyList |
| `KroMiose/nekro-agent` ★1142 | 沙盒执行 + 工作区编排 + 长期记忆 —— 和 L1/L5 完全对口 |
| `songquanpeng/one-api` ★37134 MIT | 多供应商分发与计费的成熟做法 |
| `modelcontextprotocol/servers` ★91210 | MCP 工具生态；兼容它等于一次接入拿到全部 |
