# 外部平台连接可行性审查（P2.2）

更新：2026-10-24。本文按官方文档对 Twitch 与 Discord 做一次能力/权限/运维比较，作为未来可选集成方案；不代表平台账号已接入、OAuth 已申请、消息已读取或功能已实现。实施前要重新核对当时版本的 API、政策和应用审核要求。

## 1. 先把“实时接收”拆成不同事情

1. **接收平台事件**：Twitch 聊天消息、关注/订阅等；Discord 指令/消息事件。
2. **决定是否回应**：选消息、限流、去重、上下文和安全过滤；即便收到了事件也不必让 AI 自动回复。
3. **向平台发消息**：写入聊天是独立的发言权限，不应随读取授权自动开启。
4. **平台管理动作**：禁言、改标题、发公告、创建投票等是高影响写操作，完全独立、默认关闭、逐次授权。

建议使用 P0.3 的统一事件/队列协议，平台适配器只负责验证授权、规范化和传递事件；LLM 不直接连平台 API。

## 2. Twitch：最贴近“直播实时信息接收”的候选

### 官方接口路径
- EventSub 的 WebSocket transport 可向客户端推送订阅事件；官方文档说明客户端先连接、再创建事件订阅。`channel.chat.message` 是聊天消息事件；WebSocket 适合桌面端主动连出，不必为了基础接收开放公网回调服务器。
- 接收聊天事件需要聊天身份授权。官方 EventSub 文档给出 `user:read:chat`；聊天机器人认证文档区分安装式机器人和云端机器人。对本地桌面伴侣，若仅代表用户自身账号读/写，较小的路线是用户授权的安装式聊天身份；若要以独立 bot 账号代表机器人，则要更多 bot/频道授权，复杂度更高。
- 发消息走 Helix Send Chat Message，是独立写操作，需要 `user:write:chat`；不同 token 流程/身份需要的授权组合不同。发送消息长度、身份和限速受 Twitch API 规则约束。不要为只读功能预先申请发送权限。
- EventSub 通知至少一次投递，可能重复；须用 event/message ID 去重。WebSocket 有连接、订阅数量/成本限制，需处理 welcome/keepalive/reconnect/revocation。

### 建议分期
1. **Twitch T1 只读连接**：用户明确选择频道并授权最小 `user:read:chat`；只在用户启动的会话/预览中接收，默认不生成公开回复；显示连接指示、当前频道、授权范围和停止按钮。
2. **Twitch T2 草稿回复**：AI 只生成本地回复草稿，用户逐条确认后发送；回复与事件 ID 关联，限制频率/长度、去重、勿扰、成本。
3. **Twitch T3 可选自动回复（需单独评审）**：必须额外显式开启、有频道范围、话题/安全过滤、速率/预算上限和全局停止开关；先做小范围影子模式/人工批准，不因订阅/打赏自动提升权限。
4. **暂不纳入**：禁言/封禁、改标题、投票、奖励兑换执行、声音板等直播控制。它们不是“收聊天”所必需，需另做特权权限、平台规则和误操作治理审查。

### 本地桌面实现的边界
- 使用用户的 OAuth 授权流程；不要在聊天/仓库/普通日志存 token。令牌安全存储、过期刷新、撤销后清理由权限设计处理。
- 优先使用官方 WebSocket EventSub，而不是抓取 Twitch 网页、浏览器 DOM 或模拟登录。
- 没有公网 callback 的桌面版可评估 EventSub WebSocket；不得为了收事件擅自要求用户配置公网端口/隧道。

## 3. Discord：可做显式交互，读取服务器聊天有额外门槛

### 官方接口路径
- Discord Gateway 是基于持久 WebSocket 的实时事件通道；订阅哪些事件由 intents 控制。
- **读取服务器任意消息正文并做自由聊天**需要 `MESSAGE_CONTENT` privileged intent；符合验证条件的 app 需在 Developer Portal 启用并可能需要申请审核。即便已安装 bot，也不能把消息内容权限当成默认可得。
- Discord application commands/interactions 可提供更窄的“用户主动调用”入口（如 slash command），无需持续监听所有频道自然语言；安装位置和 OAuth scopes / bot permissions 仍需用户选择与平台授权。
- 交互响应有时限；Gateway/HTTP API 都有速率限制和 429 处理要求；消息正文读取、写入、管理权限需分开申请。
- Discord bot 是独立应用身份，不应模拟用户账号自助登录、冒充用户发言或使用 self-bot 方式读取私人聊天。DM/语音/社交SDK能力有自身审批/访问限制，不能当作普通 bot scope 可直接使用。

### 建议分期
1. **Discord D1 命令式主动交互**：用户在服务器或私聊中显式调用应用命令；只请求必要的 `applications.commands` / 必要安装权限，不读取无关频道历史。
2. **Discord D2 频道消息触发**：仅在用户/服务器管理员明确安装并配置的指定频道工作；如需要读取自由文本，先核对当前 `MESSAGE_CONTENT` intent 申请/审核政策，再申请最小权限。
3. **Discord D3 自主聊天/语音**：暂不排期，需分别核验社交 SDK、语音权限、用户同意、隐私和平台规则，不能与 slash command 一起默认上线。

## 4. 两个平台的比较与建议

| 维度 | Twitch | Discord |
| --- | --- | --- |
| 与直播实时聊天的契合 | 高：EventSub 明确提供 `channel.chat.message` | 中：Gateway 可以推事件，但读取任意正文需要 privileged intent；命令式交互范围更小 |
| 桌面端本地连接路线 | EventSub WebSocket 可主动连接，减少公网服务依赖 | Gateway WebSocket 可用，但需 bot app 与 token；Interactions 可只在用户主动调用时触发 |
| 最小可行首步 | 用户授权后只读单频道事件 | Slash commands / 明确提及，不监听全部自然消息 |
| 主要审批/权限风险 | 读写 scope、bot身份/频道授权、自动回复限速/内容安全 | Message Content privileged intent、server install权限、token/频道边界 |
| 当前建议 | 若目标确定是直播互动，先只读预览，后加人工批准回复 | 先做命令触发；服务器自由聊天另列待审核事项 |

**建议排序**：平台事件适配器作为可选连接能力，不是桌宠启动依赖；若用户目标是 Neuro 式直播互动，优先审查 Twitch EventSub 只读原型。Discord 命令交互后续再评估。平台完全未选定前，不写平台专属代码。

## 5. 所有平台共用的安全/产品要求

- 每个平台、账号、频道/服务器、读/写/管理能力分开启停；默认全部断开。
- 连接时列出申请的 OAuth scopes/intents 和原因；超出当前功能的权限不请求；撤销后停止订阅、清除令牌、取消队列。
- 事件消息是不可信输入，可能含提示注入、恶意链接或个人信息；只能进入隔离的上下文，不可授权工具。
- 发送前显示账号/频道/正文；至少初期采用人工批准；回复中的提及、链接、附件和敏感内容需额外校验。
- 事件去重、过期、积压、断线重连、授权撤销、平台限流、队列洪水和重复回复纳入自动测试。
- 公开回复与本地桌宠台词分开配置；用户暂停桌宠不代表允许平台自动继续说话。
- 不保存无关消息历史；只保留处理当前事件所需的最短上下文；不以赞助/订阅价值自动提高隐私权限。

## 6. P2.2 验收拆分

**规划审查（本次完成到文档层）**：Twitch 与 Discord 的实时接收机制、必要授权、平台差异、审批/限速/重复事件、分期和非目标已核对并记录。

**实现前必须再次审查**：官方文档版本、OAuth redirect/PKCE和本地token存储、应用审核资格、ToS/隐私/数据留存、频道/服务器管理员同意、测试账号与撤销流程。

**第一版测试（若获批准）**：假平台事件和本地模拟先覆盖去重/乱序/限速/断线/撤销/过期；再用测试频道验证只读；读写分别测试；自动回复默认关；测试结束删除授权和事件日志。

**未包含**：平台账号注册、OAuth客户端申请、真实授权、消息收发、直播控制、模型调用。此文档不要求用户现在连接账号。

## 7. 官方资料（核对日期：2026-10-24）

- Twitch EventSub 订阅类型与 `channel.chat.message`：<https://dev.twitch.tv/docs/eventsub/eventsub-subscription-types/>
- Twitch Chat OAuth：<https://dev.twitch.tv/docs/chat/authenticating/>
- Twitch EventSub WebSocket：<https://dev.twitch.tv/docs/eventsub/handling-websocket-events>
- Twitch EventSub 总览（投递/订阅）：<https://dev.twitch.tv/docs/eventsub/>
- Twitch Helix API reference（Send Chat Message）：<https://dev.twitch.tv/docs/api/reference>
- Discord Gateway events/intents：<https://discord.com/developers/docs/events/gateway>
- Discord Interactions receiving/responding：<https://discord.com/developers/docs/interactions/receiving-and-responding>
- Discord OAuth2 scopes：<https://discord.com/developers/docs/topics/oauth2>
- Discord rate limits：<https://discord.com/developers/docs/topics/rate-limits>

本文是截至核对日的可行性判断，不替代对 Developer Terms、平台政策、应用审核要求及当地隐私法规的法律/合规审查。
