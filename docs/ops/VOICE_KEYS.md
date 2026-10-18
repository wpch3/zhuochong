# 语音密钥怎么拿、往哪填（Azure Dragon HD / MiniMax）

> 回答用户 2026-10-17 的问题：「Azure Dragon HD / MiniMax 密钥去哪里获取？」
>
> **一句话**：两家都是"注册 → 在控制台点一下生成 Key → 把 Key 存进本机环境变量"。
> 我们这边**早就预留好了插口**（`config/providers/*.json` 里写的是 `secret://` 引用，不是明文），
> 你只要把 Key 放进环境变量，网关就能认。**Key 永远不进仓库、不进配置文件、不发给我。**
>
> 本文信息核对于 2026-10-17，价格与区域会变，以官方页面为准（URL 都附在下面）。

---

## 0. 先说结论：按你的场景该选哪个

| | **Azure Dragon HD Flash** | **MiniMax（海螺）** |
|---|---|---|
| 二次元萌音 | **晓伊有 `cute` / `shy` 两个风格**，还有晓悠（童声，`cute`/`story`）、晓双（童声） | 官方音色库直接有「少女音 / 萌妹 / 学妹 / 女童」，**二次元向更现成** |
| 情绪控制 | SSML `mstts:express-as` + `styledegree 0.01~2`（强度可连续调） | 请求里的 `emotion` 字段，7 种（happy/sad/angry/fearful/disgusted/surprised/neutral） |
| 免费额度 | **F0 免费层：每月 50 万字符**（标准 neural）。**但 HD 是另一档计费**，别默认免费 | 新账号实名认证后常有**代金券**（约 ¥15 / 2 个月，活动会变） |
| 价格（2026-10） | 标准 neural **$15~16 / 100 万字符**；**HD $22 / 100 万字符**（2026-03 从 $30 降下来的） | `speech-2.8-hd` **¥3.5 / 万字符**；`speech-2.8-turbo` **¥2.0 / 万字符** |
| 门槛 | **要 Azure 账号 + 绑 Visa/Mastercard**（F0 不扣费，卡只用于身份验证）。国内卡常过不了 | 国内站手机号注册即可；**声音克隆**才要实名认证，普通 TTS 不用 |
| 区域限制 | **Dragon HD Flash 只在 `eastus` / `westeurope` / `southeastasia`（+中国区 `chinanorth3`）**，建站别选错区 | 国内站 `api.minimaxi.com`，海外站 `api.minimax.io`，两边账号独立 |

**我的建议（你在香港）**：
- 想要**最接近"动漫二次元美少女"**又不想折腾绑卡 → **先试 MiniMax**（少女音是官方现成音色）。
- 已经有 Azure 账号或有外币卡 → **Azure Dragon HD Flash 的晓伊 `cute`/`shy`** 质量更稳，
  而且 `styledegree` 能把"萌"的程度调成连续旋钮，和我们已经做好的演出单正好对上。

**花多少钱心里有个数**：小寻现在全量 38 条台词 ≈ **600 字符**。
按 MiniMax HD ¥3.5/万字符算 = **¥0.21 一次全量重渲**；按 Azure HD $22/1M 算 = **$0.013**。
真正费钱的是以后"每句话都实时合成"，那时再按量估算（届时网关的账本会记）。

---

## 1. Azure：拿 Key 的步骤

1. **注册 Azure 账号**：`https://azure.microsoft.com/free`
   —— 需要邮箱 + **信用卡验证**（Visa/Mastercard）。F0 免费层不扣费，卡只用于身份验证。
2. **创建"语音服务"资源**：进 `https://portal.azure.com` → **创建资源** → 搜索 **Speech**
   → 选 Microsoft 的「语音 / Speech」→ **创建**。
   - **区域**：要用 Dragon HD Flash 就**必须**选 `East US` / `West Europe` / **`Southeast Asia`**
     （你在香港，选 **Southeast Asia** 最近）。
   - **定价层**：先选 **F0（免费）**，想用 HD 再升 S0。
3. **复制密钥和区域**：部署完成 → **转到资源** → 左侧「**密钥和终结点**」
   → 复制 **密钥 1**，记下 **位置/区域**（例如 `southeastasia`）。
4. ⚠️ **注意**：页面上那个 `*.api.cognitive.*` 的「终结点」**不是 TTS 端点**。
   TTS 端点是 `https://<区域>.tts.speech.microsoft.com/cognitiveservices/v1`
   —— 这条我们已经写在 `config/providers/azure_speech.json` 里，你只要给区域名。

**官方文档**
- 创建资源与取 Key：`https://learn.microsoft.com/azure/ai-services/speech-service/get-started-text-to-speech`
- HD 音色与风格清单：`https://learn.microsoft.com/azure/ai-services/speech-service/high-definition-voices`
- 配额与限制（F0 每分钟 20 次请求）：`https://learn.microsoft.com/azure/ai-services/speech-service/speech-services-quotas-and-limits`
- 价格：`https://azure.microsoft.com/pricing/details/ai-services/speech-services/`

**Dragon HD Flash 上和我们有关的中文音色**（2026-10 官方表）

| 音色 | 支持的风格 |
|---|---|
| `zh-CN-Xiaoyi:DragonHDFlashLatestNeural` | **cute**、**shy**、gentle、nervous、complaining、angry、sad、strict |
| `zh-CN-Xiaoyou:DragonHDFlashLatestNeural` | **cute**、chat、cheerful、story、poetry-reading、angry、sad |
| `zh-CN-Xiaoshuang:DragonHDFlashLatestNeural` | chat（童声） |
| `zh-CN-Xiaoxiao2:DragonHDFlashLatestNeural` | 20 种（affectionate / curious / whispering / tired …） |

★ **晓双、晓悠在 edge 免费通道上是不存在的**（我们实测返回 0 字节），
**但在 Azure Dragon HD 上有** —— 这是换过去的一个实在好处。

---

## 2. MiniMax：拿 Key 的步骤

1. **选站点**（两边账号、Key、余额都**不互通**）：
   - 国内：`https://platform.minimaxi.com` → 端点 `https://api.minimaxi.com/v1/t2a_v2`
   - 海外：`https://platform.minimax.io` → 端点 `https://api.minimax.io/v1/t2a_v2`
2. 注册登录后进 **账户管理 → 接口密钥**（`user-center/basic-information/interface-key`）
   → **创建新的密钥** → **复制保存**（⚠️ 只显示一次，关掉就看不到了）。
3. 充值：按量计费从余额扣。TTS `speech-2.8-hd` **¥3.5/万字符**、`speech-2.8-turbo` **¥2.0/万字符**。
4. **声音克隆才需要实名认证**（个人/企业），我们**不做克隆**（I6 合规线），所以这步可以跳过。
   —— 但实名认证常附赠代金券，想白嫖可以做。

**官方文档**
- 接口概览 / 取 Key：`https://platform.minimaxi.com/docs/api-reference/api-overview`
- 同步语音合成 T2A：`https://platform.minimaxi.com/docs/api-reference/speech-t2a-http`
- 系统音色 id 表：`https://platform.minimaxi.com/docs/faq/system-voice-id`
- 价格：`https://platform.minimaxi.com/docs/guides/pricing-paygo`

**我们要用的音色**：`config/voicebank/mm_shaonv.json` 里已经写死 `voice_id = female-shaonv`（官方「少女音色」）。
拿到 Key 之后我会按你的耳朵再从「萌妹 / 学妹 / 女童」里挑对照。

---

## 3. 拿到 Key 之后往哪填（**不要发给我，也不要写进任何文件**）

我们的网关只认**环境变量**，规则是 `secret://xxx` → `ZHUOCHONG_SECRET_XXX`
（`src/core/zgateway.c::zgw_secret_resolve`，取不到就明确报错，**绝不会拿空串硬发请求**）。

| 供应商 | 配置里的引用 | 你要设的环境变量 | 必填？ |
|---|---|---|---|
| Azure 语音 | `secret://azure_speech` | **`ZHUOCHONG_SECRET_AZURE_SPEECH`** | 是 |
| Azure 区域 | — | `ZHUOCHONG_AZURE_REGION`（默认 `southeastasia`） | 否（不是秘密） |
| MiniMax | `secret://minimax` | **`ZHUOCHONG_SECRET_MINIMAX`** | 是 |
| MiniMax GroupId | — | `ZHUOCHONG_SECRET_MINIMAX_GROUP` | **多数账号必填**，不带会 401 |

### 3.0 ★ 推荐这条：放进 GitHub 仓库 Secrets（渲染在 Actions 上跑）

**为什么**：合成必须联网，而 Arena 沙箱的出网白名单只放 github / npm / pypi
—— 我这边**打不到任何 TTS 端点**。这仓库的语音一直是在 GitHub Actions 上渲的
（`.github/workflows/voice-render.yml`，渲完直接把 mp3 提交回分支，我就能读到、你也能直接听）。
所以密钥放仓库 Secrets 是最顺的一条路：**你不用把密钥给任何人，我也不经手。**

1. 打开 `https://github.com/wpch3/zhuochong/settings/secrets/actions`
2. 点 **New repository secret**，按上表的名字**逐个**加：
   - `ZHUOCHONG_SECRET_AZURE_SPEECH`
   - `ZHUOCHONG_SECRET_MINIMAX`
   - `ZHUOCHONG_SECRET_MINIMAX_GROUP`（MiniMax 控制台里和 Key 同一页）
3. 加完告诉我一声，我去 Actions 手动触发 `voice-render`，选 `provider = azure`（或 `minimax`），
   它会**先体检密钥再开渲**，渲完把样音提交回分支。

GitHub 的 Secrets 是单向的：存进去之后**连你自己都看不到原文**，
日志里出现也会被自动打成 `***`。我们的 workflow 还多做了一层 ——
密钥只经 `env:` 注入，**绝不出现在 `run:` 的命令行里**（命令行会原样进日志）。

### 3.1 或者只在你本机用

**Windows（你的目标平台）**：
```powershell
setx ZHUOCHONG_SECRET_AZURE_SPEECH "你的密钥1"
setx ZHUOCHONG_SECRET_MINIMAX      "你的API Key"
# setx 写的是永久变量，设完要重开终端/重启程序才读得到
```

**Linux / macOS**（或仓库根目录的 `.env`，**`.gitignore` 已经忽略它**）：
```bash
export ZHUOCHONG_SECRET_AZURE_SPEECH="..."
export ZHUOCHONG_SECRET_MINIMAX="..."
```

**Azure 还要一个区域**（不是秘密）：默认吃 `southeastasia`（香港离它最近），
要改就设 `ZHUOCHONG_AZURE_REGION`。注意门户页面上那个 `*.api.cognitive.microsoft.com`
**不是 TTS 端点**，真正的端点是 `https://<区域>.tts.speech.microsoft.com/cognitiveservices/v1`。

### 3.2 填完先体检（不打印密钥，只打印指纹）

```bash
python3 tools/voice_cloud.py --check            # 看两家密钥在不在、形状对不对
python3 tools/voice_cloud.py --check --net      # 再真发一次合成请求（本机要能联网）
python3 tools/voice_cloud.py --say "你回来啦，我等你好久了" --provider azure --style cute --out /tmp/t.mp3
```

体检输出长这样 —— **只有指纹，没有密钥**：

```
── Azure 语音服务（azure_speech）
   密钥环境变量：ZHUOCHONG_SECRET_AZURE_SPEECH
   ✓ 读到了：32 位 / 9f…c1 / sha256:7907c793
   区域：southeastasia
```

指纹的用处：你一眼能核对"它用的是不是我给的那把"，而这串东西反推不出密钥。
它还会做形状体检 —— Azure 密钥是 32 位十六进制、MiniMax 是三段点分的 JWT，
**把「终结点 URL」当密钥贴进去**这种最常见的错，体检这一步就拦住了。

### 安全红线（已经是仓库纪律，不是建议）
1. **Key 只存本机**（环境变量或被忽略的 `.env`）。历史上这仓库被误提交过一次 `.env`，教训记在
   `docs/HANDOVER_NEXT_AGENT.md`。
2. **不要在聊天里把 Key 发给我**。我不需要它也能把代码写好 —— 渲染在你本机或你自己的 CI 跑。
3. 万一泄露：Azure 在「密钥和终结点」页点**重新生成密钥**；MiniMax 在接口密钥页**删除重建**。
4. 我们这边的 `--only` 渲染脚本**不会把 Key 写进 catalog 或日志**。

---

## 4. 填完之后我这边要做什么（已经写好，等 Key）

1. `config/providers/azure_speech.json` / `minimax.json` 的 `enabled` 改 `true`，跑
   `python3 tools/check_platform.py` 重新物化路由表（`config/voices.json` 是生成物，不手改）。
2. 渲染器的 provider 分支**已经写完了**（2026-10-18）：客户端在 `tools/voice_cloud.py`
   （纯标准库，Azure 走 `mstts:express-as` + `styledegree`，MiniMax 走 `emotion` 字段，
   注意它返回的 `data.audio` 是 **hex 不是 base64**），
   渲染器用 `--provider azure|minimax --cloud-voice … --cloud-style …` 切过去，
   输出格式和 edge-tts 对齐（24kHz/mono/mp3），所以分段拼接不会在接缝处咔哒。
3. 用**同一份语感表**重渲一次，和现在的 edge 版并排放进试听页，你直接 A/B。
4. 按你选的音色写进 `config/voice_cast.json`（T58.1），每个角色各自记一档。

**没有 Key 也不会卡住**：edge-tts 这条免费通道继续是默认，
`config/emotion_map.json` 的回退链保证"有密钥用密钥、没密钥退 edge"，
离线时还能退本地音色 —— 这是 DC18「云端 + 本地双路由」定下的口径。

---

## 5. 顺带回答一个你可能会问的

**「不给钱有没有办法做出二次元萌音？」** 有，但都要你本机有显卡：
- **IndexTTS2**（B 站，Apache-2.0，约 8GB 显存）：音色与情感**解耦**，8 维情感向量 + 强度旋钮；
- **CosyVoice2-0.5B**（阿里，Apache-2.0，约 4GB）：直接用自然语言指令控语气。

⚠️ **IndexTTS-2.5（2026-08）换成了 Bilibili Model License，不再是 Apache** ⇒ 要用就钉死 2.0 版本。
这条路排在 **T58.3**，等你有一台带显卡的机器再做；到时候全离线、不花钱、不依赖任何云。
