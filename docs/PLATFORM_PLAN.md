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
  "priority": 40,
  "balance": { "mode": "api", "endpoint": "/dashboard/billing/credit_grants",
               "pick": "total_granted", "minus": "total_used", "currency": "USD" }
}
```

`balance.mode` 三选一，**这就是"token 余额识别"**：
- `api` —— 供应商有余额接口，直接查；
- `ledger` —— 没有接口，用本机账本倒推（充值额 − 已用额）；
- `none` —— 本地模型，不计费（`ollama` / `llamacpp` / `comfyui` 走这条）。

**`api` 模式为什么不是一个 URL 就够**（G51 查 one-api 的 `channel-billing.go` 实测，
见 REFERENCE_NOTES 第十二批）：四家四种算法——DeepSeek 直接给 `balance_infos[0].total_balance`，
OpenRouter 和 credit_grants 式要 `总额 − 已用`，OpenAI 订阅式还要查两个端点。
所以写成 `endpoint` + `pick`（取哪个字段）+ 可选 `minus`（要减的字段）。
校验器强制 `mode=api` 必须给 `endpoint` 和 `pick`，并拦住继续用老 `path` 的写法。
**已知限制**：OpenAI 订阅式那种"两个端点"当前表达不了，等真要接的时候再扩。

`priority` 是路由用的（越大越优先）。本机的给 90，所以 `prefer_local` 策略下它们天然排前面。

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

### 2.5 网关 `src/core/zgateway.{c,h}`（G51 ✅ 2026-10-13）

L2 层的落地。四件事，**全是纯决策，不碰网络**：

| 做什么 | 函数 | 要点 |
|---|---|---|
| 路由 | `zgw_pick(g, cap, attempt, &why)` | `attempt` 递增 = 依次降级重试；失败原因分三种 |
| 估价 | `zgw_estimate(route, tin, tout)` | 按量 / 按次（`price_per=0`）/ 免费（本机或 `free`） |
| 记账 | `zgw_hold_open` → `_settle` / `_release` | 预扣只占位，**结算入账的是实际值**；失败不扣钱但计失败数 |
| 密钥 | `zgw_secret_resolve("secret://x", ...)` | → 环境变量 `ZHUOCHONG_SECRET_X`；**取不到必须失败** |

两个设计决定值得记住：

**① 路由表是生成物，不是运行时算的。**
`tools/check_platform.py` 把 `config/providers/*.json` 物化成 `config/gateway_routes.json`，
**顺序即优先级**，运行时取第一个 `enabled` 的就是首选。
照 one-api 的 `Ability` 表做法（见 REFERENCE_NOTES 第十二批）——
路由是每次请求都要做的事，不该每次去遍历契约目录。
与 one-api 的唯一差别：它同优先级内**随机**（多用户负载均衡），
我们按 id **稳定**排序——单机单用户下可复现比均衡重要。

**② 失败原因必须分三种，因为给用户的话完全不同。**

| 原因 | 界面该说什么 |
|---|---|
| `ZGW_NO_SUCH_CAP` | 这功能还没接入 |
| `ZGW_ALL_DISABLED` | 有供应商，但都没开 → **去设置里打开** |
| `ZGW_EXHAUSTED` | 候选都试过了 → 换个说法或稍后再试 |

统一说"不可用"的话，用户不知道该干什么。`/api/gateway.json` 按这三态报告，
平台面板直接照它显示。

**范围边界**：真实 HTTP 调用**不在 G51 里**，是 G54。
把"选谁 / 花多少 / 钥匙在哪"和"怎么发出去"切开，前者在一台没网、
没配任何密钥的机器上就能完整验证——这是它能有 63 项单测的原因。

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
- [x] **G50 契约与注册表**：四份 schema + 加载器 + 校验闸门（能力/供应商注册表）—— ✅ 2026-10-13，15 能力 + 6 供应商
- [x] G51 网关骨架：路由 + 记账 + 密钥引用（不含真实请求）—— ✅ 2026-10-13，`src/core/zgateway.{c,h}`，63 项单测
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

**P4 实时陪玩**（2026-10-14 新增，对应 A23~A27）
- [ ] G69 双路由网关：`prefer_local` / `prefer_cloud` / `local_only` / `cloud_only` 四策略 + 自动降级链（A23）
- [ ] G70 本地模型自定义区块：列模型 / 调参 / 显存估算 / 量化档 / 拉取删除（A24）
- [ ] G71 事件流总线：弹幕·语音·屏幕·通知统一入队，带优先级与节流（A27.1 / A27.6）
- [ ] G72 实时 STT + 打断：麦克风常开、边说边转写、中途能插话（A27.2 / A27.5）
- [ ] G73 低延迟回路：端到端延迟预算 < 1.5s，实测写进文档（A27.3）
- [ ] G74 主动发言：空闲时按屏幕/时间/记忆自己开口（A27.4）
- [ ] G75 屏幕捕获 + 游戏状态理解（A25.1 / A25.2）
- [ ] G76 输入控制 + 急停热键 + 逐游戏授权（A25.3 / A25.4 / A25.5）
- [ ] G77 陪伴联机：状态同步 + 多人识别 + 局域网直连 + 设备转场（A26）
- [ ] G78 供应商矩阵扩充（A28.1；**豆包/火山永不纳入**，已有静态闸）

依赖关系：G69 是 P4 的地基（其余都要经过网关）；G71 是 G72/G74/G75 的汇流点；
G76 必须等 G75 能稳定识别状态之后才做，否则是瞎操作。

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
