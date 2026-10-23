# 供应商大兼容 + 云端/本地双栈 规划（T59）

> 来源：用户 2026-10-18 第七问原话 ——
> 「**之后如果要使用其他的 api 的话可以做更多的兼容吗？比如兼容更多的 api 密钥或者兼容全部的可用的。
> 甚至本地的适配，比如本地的 ai 软件来使用 gpu 或者 cpu 来进行工作，llm，tts，stt，生图，生视频，建模
> 都要做云端和本地的适配，配置够的话可以和云端差不多**」
> 以及「**完整的计划和规划我的想法和话语，必须完整接收和规划，不懂得查教程和资料，不要敷衍我**」。
>
> 这份文档就是那份完整规划。每一节都落到**文件 / 端点 / 显存数字 / 闸门**上，不写"将来支持"。
> 配套的事实与出处在 `docs/REFERENCE_NOTES.md` 第四十五批（全部带 URL）。

---

## 0. 一句话结论

**能。而且这件事在本仓库里不是"新架构"，是"把已经存在的那层铺满"。**
平台层（G50）从一开始就是「**能力契约 × 供应商契约 × 网关路由**」三件套：
`config/capabilities/*.json`（15 种能力）× `config/providers/*.json`（现在 **29 家**）
→ `tools/check_platform.py` 生成 `config/gateway_routes.json`（**76 条路由**）
→ `src/core/zgateway.c` 按 `prefer_local` 策略选一家、预扣额度、失败换下一家。

这一轮做的事：**把供应商从 9 家铺到 29 家、把路由从 19 条铺到 76 条、
把"本地"从"只有 Ollama 和 ComfyUI"铺成 LLM/TTS/STT/生图/生视频/建模六条线都各有本地实现**，
并加了两道新闸把"只做了一半"钉死（见 §6）。

---

## 1. 总体架构：一张能力表，两套腿

```
         ┌──────────────────── 应用层（桌宠 / 立绘 / 语音 / 记忆）────────────────────┐
         │   只说"我要 chat.stream / tts.speak / model3d.generate"，不认识供应商      │
         └───────────────────────────────┬──────────────────────────────────────────┘
                                         │  能力 id（15 种，config/capabilities/）
         ┌───────────────────────────────▼──────────────────────────────────────────┐
         │  网关 zgateway：策略 prefer_local + 敏感内容锁本地 + 预扣/结算/退还         │
         │  决策流水 data/usage.jsonl（每一笔都写"为什么选它"）                        │
         └───────┬───────────────────────────────────────────────┬──────────────────┘
                 │ 本地（local:true, priority 70~90）              │ 云端（local:false, 40~60）
   ┌─────────────▼─────────────┐                     ┌───────────▼──────────────────┐
   │ Ollama / llama.cpp / vLLM │ 对话·写码·看图·向量  │ DeepSeek Kimi GLM 通义 硅基   │
   │ LM Studio                 │                     │ OpenRouter Groq xAI Gemini    │
   │ speaches / whisper.cpp    │ 语音识别             │ Claude(官方形状) MiniMax      │
   │ TTS-WebUI(GPT-SoVITS/     │ 语音合成             │ Azure 语音 / MiniMax 语音     │
   │   IndexTTS2/CosyVoice2)   │                     │ edge-tts（免费保底）           │
   │ ComfyUI（图 / 视频）       │ 生图·生视频          │ OpenAI 图 / 万相 wanx         │
   │ TripoSR / Hunyuan3D       │ 建模                 │ Tripo3D                       │
   └───────────────────────────┘                     └───────────────────────────────┘
```

**为什么能一张表管住这么多家**：业界已经收敛到 **OpenAI 形状**（`POST /v1/chat/completions`
+ `Authorization: Bearer`），换一家 = 换 `base_url` + `api_key` + `model` 三个值。
不只是对话 —— 语音/出图也有对应的标准路径：

| 能力 | OpenAI 形状的标准路径 | 本仓库能力 id |
|---|---|---|
| 对话 / 流式 | `POST /v1/chat/completions` | `chat.completion` `chat.stream` |
| 文本向量 | `POST /v1/embeddings` | `embed.text` |
| 语音合成 | `POST /v1/audio/speech` | `tts.speak` |
| 语音识别 | `POST /v1/audio/transcriptions` | `stt.listen` |
| 生成图片 | `POST /v1/images/generations` | `image.generate` |
| 模型发现 | `GET /v1/models` | （探活用） |

所以 `kind: "openai_compatible"` 这一类供应商**一个适配器全覆盖**；
形状不同的（Claude 的 `/v1/messages`、MiniMax 的 `t2a_v2`、ComfyUI 的 `/prompt`、
Tripo3D 的异步 task）才需要单写适配器，它们在契约里标 `kind: official / tts / comfyui / local_script`。

---

## 2. 云端供应商清单（现已登记 16 家）

> 全部 `enabled:false` 起步、密钥一律写 `secret://xxx` 引用（DC80：真钥匙只存 env / GitHub Secrets，
> 配置文件里**只准出现引用**，`check_platform.py` 有正则在盯）。
> 价格字段只用于**路由排序**，不当账单；真实扣费以各家账单为准。

| id | 家 | base_url | 能力 | 备注（踩过的坑） |
|---|---|---|---|---|
| `openai` | OpenAI | `https://api.openai.com/v1` | 对话/图/编辑/向量 | 参照系 |
| `deepseek` | DeepSeek | `https://api.deepseek.com/v1` | 对话/写码 | 也提供 Anthropic 形状 `/anthropic` |
| `moonshot` | Kimi | `https://api.moonshot.cn/v1` | 对话/写码/看图 | 国内 `.cn` / 海外 `.ai` **账号余额不互通** |
| `zhipu` | 智谱 GLM | `https://open.bigmodel.cn/api/paas/v4` | 对话/看图 | ★ 结尾**不是** `/v1`，按默认拼法会 404；glm-4-flash 免费档 |
| `dashscope` | 阿里百炼/通义 | `…/compatible-mode/v1` | 对话/看图/向量/图/**视频** | 海外站 `dashscope-intl`；视频走万相 wanx |
| `siliconflow` | 硅基流动 | `https://api.siliconflow.cn/v1` | 对话/向量/图/**STT/TTS** | ★ 一把钥匙四类能力，性价比最高的"单钥匙"选择 |
| `openrouter` | OpenRouter | `https://openrouter.ai/api/v1` | 对话/看图 | 一把钥匙几百个模型；余额要 `total_credits − total_usage` |
| `groq` | Groq | `https://api.groq.com/openai/v1` | 对话/STT | ★ 路径是 `/openai/v1`；卖点是**首字延迟**，桌宠体感最吃这个 |
| `xai` | Grok | `https://api.x.ai/v1` | 对话/看图 | UI 已有 grok 皮肤，供应商补齐 |
| `gemini` | Google | `…/v1beta/openai` | 对话/看图/向量 | Google 自带 OpenAI 兼容端点，不必单写 kind |
| `anthropic` | Claude | `https://api.anthropic.com/v1` | 对话/看图 | ★ **不是** OpenAI 形状：`/v1/messages`、`x-api-key`、`anthropic-version` |
| `minimax_chat` | MiniMax 文本 | `https://api.minimaxi.com/v1` | 对话 | 和语音共用一把 Key |
| `minimax` | MiniMax 语音 | 同上 | TTS | 二次元音色最全；返回 `data.audio` 是 **hex 不是 base64** |
| `azure_speech` | Azure 语音 | `https://{region}.tts.speech…` | TTS | 晓伊 cute/HD Flash；建议 region=`southeastasia` |
| `edge_tts` | Edge 免费通道 | wss | TTS | 免费保底，**做不了情绪**（无 SSML style） |
| `tripo3d` | Tripo3D | `https://api.tripo3d.ai/v2/openapi` | 建模 | 异步任务：提交拿 task_id 再轮询 |
| `relay_test` | 中转站模板 | （示例） | 对话 | 给"第三方中转 Key"留的模板：改 base_url 即可 |

**明确排除**：字节跳动系（豆包 / 火山方舟）—— DC13，用户 2026-10-14 原话「绝对不要豆包」。
这是**产品决策不是技术限制**，写在这里是为了下一个接手的人别"顺手补全"。

### 2.1 用户自带中转站 / 自定义 Key 怎么接

一条 `relay_test` 模板足够：复制成 `config/providers/<你的名字>.json`，
改 `base_url` + `auth.key_ref` + `capabilities[].model` 三处即可（`kind` 保持 `openai_compatible`）。
路由表会在下一次 `python3 tools/check_platform.py` 时自动把它编进去。
这就是"兼容全部可用的"的现实答案：**不是枚举所有家，而是让任何一家都能用三行配置接进来**。

---

## 3. 本地供应商清单（现已登记 9 家）

| id | 软件 | 默认端口 | 能力 | 最低显存 / 怎么量 |
|---|---|---|---|---|
| `ollama` | Ollama | 11434 | 对话/写码/看图/向量 | Q4_K_M ≈ **0.55~0.7GB / 1B 参数**：7B≈5GB、14B≈9GB、32B≈19GB |
| `llama_cpp` | llama-server | 8080 | 对话/写码/向量 | 同上；**CPU 也能跑**（7B 约 3 tok/s） |
| `lmstudio` | LM Studio | 1234 | 对话/向量 | 同上；GUI 派，**不能 headless** |
| `vllm` | vLLM | 8002 | 对话 | 吃 safetensors 不吃 GGUF；预占显存，同模型比 llama.cpp **多 ~4GB** |
| `speaches` | speaches | 8000 | **TTS + STT** | CPU int8 可跑；6GB 显存可上 large-v3 |
| `whisper_cpp` | whisper.cpp | 8081 | STT | 纯 CPU 实时；模型 q5 约 0.6GB |
| `tts_webui` | TTS-WebUI | 7778 | TTS（萌系） | IndexTTS2≈8GB / CosyVoice2-0.5B≈4GB / GPT-SoVITS 更小 |
| `comfyui` / `comfyui_video` | ComfyUI | 8188 | 生图 / 生视频 | 见 §4 表 |
| `triposr` / `hunyuan3d` | TripoSR / Hunyuan3D | 8085 / 8084 | 建模 | 6GB / 10GB（形状）·21GB（贴图）·29GB（全流程） |

### 3.1 两个会咬人的实现细节（已写进各自的 note）

1. **whisper.cpp 的服务端默认不在 `/v1/audio/transcriptions`**，必须
   `whisper-server … --inference-path /v1/audio/transcriptions`，否则 OpenAI SDK 打不中；
   而且不显式传 `language=zh` 时它**默认当英文**。
2. **端口会撞**：speaches 默认 8000、vLLM 默认也是 8000、llama-server 8080。
   契约里已经把 vLLM 挪到 8002、whisper.cpp 挪到 8081，避免"两个服务抢一个端口，
   网关探活成功但请求打错家"这种最难查的故障。

---

## 4. 硬件档位：到底"配置够"是多够

> 用户的原话是「**配置够的话可以和云端差不多**」。这句话要诚实拆开回答：
> **文本/语音：真的能差不多；生图：能接近；生视频/建模：本地是"能出"，不是"等质"。**

| 档位 | 典型硬件 | 对话 | 语音（TTS/STT） | 生图 | 生视频 | 建模 |
|---|---|---|---|---|---|---|
| **A 纯 CPU** | 任意 16GB 内存 | 7B Q4 ≈3 tok/s，够短句 | whisper.cpp 实时、Piper/Kokoro 可用 | ✗（分钟级） | ✗ | ✗（TripoSR 可回落 CPU，很慢） |
| **B 6~8GB 显存** | RTX 3060 / 4060 | 7~8B Q4 流畅（40~60 tok/s） | faster-whisper large-v3 + GPT-SoVITS | SDXL / Flux-schnell Q4 | Wan2.2 5B 480p（ComfyUI 卸载） | TripoSR（6GB） |
| **C 12~16GB** | 3060 12G / 4070 / 4080 | 14B Q4 舒服 | IndexTTS2（8GB）情绪解耦 | Flux dev FP8 | Wan2.2 14B GGUF Q4/Q5 480~720p；LTX-2 FP8 | Hunyuan3D 形状(10GB) |
| **D 24GB** | 3090 / 4090 | 32B Q4 | 全部 | Flux dev BF16 | Wan2.2 14B 720p 舒服 | Hunyuan3D 低显存模式(~15GB) |
| **E 32GB+** | 5090 / 专业卡 | 32B+ 长上下文 | 全部 | 全部 | LTX-2 全质量 | Hunyuan3D 全流程(29GB) |

**判断口径（写进 `hardware.min_vram_gb` 字段，网关按它过滤候选）**：
显存不够的供应商**不进候选表**，而不是"选了再失败"—— 失败重试会让桌宠卡住几十秒，
而候选过滤是零成本的。探活与档位检测放在 `tools/provider_probe.py`（T59.2，见 §7）。

### 4.1 "差不多"的实话

* **对话**：7~14B 的本地模型在"日常陪聊 + 情绪回应"上和云端旗舰差距**不大**；
  差距出现在长链推理、代码、冷门知识 —— 所以路由策略是 `prefer_local` + 
  "超过 token 阈值 / 标为重活"就上云（`gateway.json` 的 `tokens_cloud` / `heavy_cloud`）。
* **语音**：本地 IndexTTS2 / GPT-SoVITS 在**音色像不像**上已经追平甚至超过云端（可克隆），
  但**稳定性**（长句不崩、数字读法、多音字）云端更好。所以默认云端、本地做隐私/断网兜底。
* **生图**：本地 SDXL/Flux 和云端差距主要在**出图时间**（8GB 卡一张 1024² 要十几秒）。
* **生视频 / 建模**：本地能出，但一段 5 秒 480p 在 4090 上也要**几分钟**，
  Hunyuan3D 全流程要 29GB。所以这两项的定位是**离线预生成**（待机动画、手办预览），
  不进实时交互路径 —— 这一点必须写明白，不能让用户以为"点一下就有视频"。

---

## 5. 密钥与隐私（和已有规矩一致，不另起炉灶）

* **DC80**：密钥只走环境变量 / GitHub Secrets，配置里只写 `secret://x` → 读 `ZHUOCHONG_SECRET_X`。
  `check_platform.py` 用正则拦 `sk-…` / `AIza…` / `ghp_…` 明文。
* **敏感内容锁本地**：`gateway.json` 的 `sensitive_local_only` —— 标了敏感的请求
  本地不可用时**直接拒绝**，绝不偷偷上云（`ZGW_R_SENSITIVE_BLOCKED`）。
* **一把钥匙多条能力**：MiniMax 的文本与语音、硅基的四类能力共用同一把 Key ——
  配置页按"钥匙"而不是按"能力"组织，少让用户填几次（T59.3 UI）。
* **协议风险登记**（DC14 的延伸）：
  * Hunyuan3D 2.x = Tencent Hunyuan 3D Community License，**不适用欧盟/英国/韩国**，
    月活 >100 万需另行授权，输出不得用于训练其他模型 ⇒ 权重**不进分发包**，只做可选外挂。
  * IndexTTS **2.5 改成了 Bilibili Model License**，要用必须钉 **2.0**（Apache-2.0）。
  * Wan2.1/2.2 = Apache-2.0；TripoSR / TRELLIS = MIT；LTX-2.x = 自家社区协议（逐条读）。

---

## 6. 这一轮已经落地的闸门（没有闸的计划等于没写）

| 闸 | 在哪 | 拦什么 |
|---|---|---|
| 路由表没顶到引擎上限 | `selfcheck_repo.py` | `ZGW_MAX_ROUTES` 旧值 64 < 现有 76 条路由 ⇒ **静默丢弃**后几条（恰好是本地建模/视频）。现已提到 192，用量超 80% 就报红 |
| 每种能力都有云端和本地两条腿 | `selfcheck_repo.py` | "只做了一半"的双栈。4 种按设计单边（联网搜索/执行代码/读文件/记忆）写在白名单里，每条注明原因 |
| 供应商字段齐全 / 能力引用一致 / 余额口径 / 无明文密钥 | `check_platform.py` | 老闸，29 家全过 |
| 本地供应商余额必须 `none` | `check_platform.py` | 本地不该有"余额"这种概念 |

---

## 6.5 真链路（G54，2026-10-23 做完第一段）

前面六节讲的都是"选谁"。这一节是"怎么发"。
在这之前，整条线到路由表就断了 —— **人设提示词一个字节都没出过门**。

### 落到哪两个文件

| 文件 | 干什么 |
|---|---|
| `src/core/zhttp.{c,h}` | 自带 HTTP/1.1 客户端（零依赖）。URL 拆解、超时、体积上限、`Content-Length` 与 `chunked` 两种响应体、Linux/winsock 双实现、11 种错误码配人话 |
| `src/core/zrelay.{c,h}` | 中继层。选路 → 查接入点 → 校接口族 → 取密钥 → 拼体 → 真发 → 解析 → 记账 |

路由表多了 `endpoints` 段（29 条，`tools/check_platform.py` 生成）：
每家的 `base_url` / `auth_type` / `key_ref` / `auth_header` / `chat_path` / `kind`。
`zgw_endpoint_find()` 查不到就返回 NULL，**调用方不许自己拼一个默认地址** ——
猜出来的地址要么连不上，要么连到不该连的地方去。

### 现在能真连的是哪几家

只有**本地明文栈**：ollama `:11434/v1`、llama.cpp `:8080/v1`、LM Studio `:1234/v1`、
vLLM `:8000/v1`，加 ComfyUI / speaches / whisper.cpp。
这恰好也是「断网也能用」那条线的落点 —— 第一条真链路落在这儿是合适的。

**云端 16 家一家都连不上，因为还没有 TLS。** 见下。

### TLS：这一轮为什么没做，以及两条后路

本机没有 OpenSSL 开发头（`/usr/include/openssl/ssl.h` 不存在，
`pkg-config openssl` 也查不到），`-lssl -lcrypto` 必然链接失败。

**做不了就老实说做不了。** `zhttp` 对 `https://` 直接返回 `ZHTTP_E_TLS`，
话是「还不支持 https（本版只连本地明文服务），**不会把密钥明文发出去**」。

**绝不接受的做法是"先降级成 http 把功能跑通"** —— 那等于把 API key
和用户说的每一句话明文发到公网上。功能没打通是进度问题，密钥泄露是事故。

两条后路，做的时候挑一条：

1. **运行期 `dlopen` libssl ← 2026-10-23 查完，选这条**。
   关键事实：**缺的只是开发头，不是库本身**。本机 `/usr/lib/x86_64-linux-gnu/libssl.so.3`
   和 `libcrypto.so.3` 都在（`ctypes.util.find_library('ssl')` 也能找到）——
   这意味着这条路**在当前沙箱里就能完整验证**，不是纸上谈兵。
   做法：自己声明用到的那十几个函数原型（OpenSSL 3.x 的 ABI 是稳定的），
   `dlopen` + `dlsym` 取地址，拿不到就退回现在的 `ZHTTP_E_TLS` 行为。
   好处是依然零编译期依赖、安全更新跟着系统走、不用自己背密码学代码；
   用户机器上有就用、没有就把话说清楚（"你这台机器没装 OpenSSL，
   云端模型用不了，本地的照常"）。
   坏处是不同发行版 `.so` 名字不一样（要探 `libssl.so.3`/`libssl.so.1.1`/`libssl.so`
   几个候选），Windows 要另走 schannel 或带一份 dll。
   **证书校验不许省**：`SSL_CTX_set_default_verify_paths` + `SSL_set1_host`
   + `SSL_get_verify_result`，三样缺一样都等于没验 —— 不验证书的 https
   和明文 http 在中间人面前没有区别。
2. **塞一份单文件 TLS 实现进 `src/third_party/`**（项目已有先例：`stb_image.h`）。
   好处是到处都能编、行为一致；坏处是**密码学代码自己背着**，
   出了 CVE 要自己跟 —— 对一个桌宠项目来说这个担子偏重。
   作为后备：万一 (1) 在某些目标机器上探不到库，再考虑。

在 TLS 做完之前，**云端那条线是哑的**，设置界面必须如实这么显示，
不能让用户填了 key 之后对着一个永远转圈的按钮发呆。

### 四条红线（都在 send 之前）

密钥取不到不发 / 接口族对不上不发 / https 不降级 / 请求体显式 `stream:false`。
外加一条收到响应之后的：**HTTP 200 不等于成功**，OpenAI 系错误体
`{"error":{…}}` 常常带 200 回来，先验 `error` 再取 content。

细节和那个"降级会绕过隐私标记"的洞，记在 `docs/memory/GAPS.md` 的 G54 正文。

---

## 7. 任务拆解（进 TASKS）

| 编号 | 事 | 状态 |
|---|---|---|
| **T59.1** | 供应商契约铺满：云端 16 + 本地 9（共 29 家 / 76 条路由）+ 两道新闸 | ✅ 2026-10-18 |
| **T59.7** | **真链路第一段**：`zhttp` + `zrelay` + `/api/chat`（含 dry-run）；只接 `openai_compatible`、只连本地明文栈 | ✅ 2026-10-23 |
| **T59.8** | **TLS**（二选一：运行期 `dlopen` libssl / 单文件实现进 `src/third_party/`）—— 没它云端 16 家全是哑的 | 待做，**云端线的唯一卡点** |
| **T59.2** | `tools/provider_probe.py`：`--check` 离线体检（端点形状/端口冲突/能力缺腿）、`--net` 探活、`--hw` 按显存给出"你这台机器能开哪几家" | 待做 |
| **T59.3** | 设置界面「钥匙串」：按钥匙而非按能力组织；本地服务一键探活（绿灯/灰灯）；每条能力显示"现在会走谁" | 待做 |
| **T59.4** | 适配器补齐：`anthropic`(messages) / `tripo3d`(异步 task) / `comfyui`(prompt+history 轮询) / `dashscope`(万相) 四个非 OpenAI 形状 | 待做 |
| **T59.5** | 本地引擎自启与健康检查：进程托管（起不来要说清楚为什么）、显存不足时自动降档（14B→7B→云端） | 待做 |
| **T59.6** | 离线模式演练：拔网线跑一遍全链路（对话→TTS→口型→立绘），把"断网后哪些功能退化成什么样"写成验收表 | 待做 |

---

## 8. 验收口径

1. `python3 tools/check_platform.py --check` 全绿，且 `config/gateway_routes.json`
   与契约一致（生成物不许手改）。
2. `selfcheck_repo.py` 的「路由表没顶到引擎上限」「每种能力都有云端和本地两条腿」两条为绿。
3. 任取一种能力，能在 `gateway_routes.json` 里找到**至少一条本地、一条云端**候选
   （`web.search` / `code.execute` / `file.read` / `memory.recall` 四条按设计单边，白名单内）。
4. 新接一家 OpenAI 兼容供应商的成本 = **新建一个 json 文件 + 跑一次生成器**，不改 C 代码。
   （这一条是本节的核心主张，T59.2 的 `--check` 会把它变成可执行断言。）
