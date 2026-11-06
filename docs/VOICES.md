# 音色手册（VOICES）—— 下载、安装、训练

更新：2026-10-11 ｜ 相关：`tools/voice_local.py`、`tools/voice_packs.py`、`tools/voice_pitch.py`、`voices/`、`config/voices.json`

> 结论先行：
> 1) **可以自己下载音色**，放进 `voices/<id>/`（或 `voice_packs.py install`）就能用，不用改代码；
> 2) **可以发给我**（放进仓库或聊天上传都行），但大模型文件不建议入库（仓库会变重，且要填许可信息）；
> 3) **软件里做训练功能可行**，但架构上应该做成“语音供应商插件 + 音色包导出”，训练本身需要 GPU，
>    并且只能训练**自己有权利使用的声音**（真人克隆在本项目已被用户明确禁止）。

---

## 1. 现在支持什么格式

| 格式 | 支持情况 | 说明 |
| --- | --- | --- |
| Piper VITS（`.onnx` + `.onnx.json`） | ✅ 直接支持 | `voice_packs.py` 安装即用；`phoneme_type: pinyin` 与 `espeak`（IPA）两条音素路径都已实现 |
| sherpa-onnx / Kokoro / Coqui / VITS 其他导出 | ⬜ 需要适配器 | 结构不同（音素表、输入签名不同），计划按"供应商插件"接入（见第 4 节） |
| 供应商 API（云端，OpenAI 兼容 `/audio/speech`） | ✅ 已实现 | `tools/voice_render.py` + `.github/workflows/voice-render.yml`（云端渲染到仓库） |
| GPT-SoVITS / CosyVoice / Fish-Speech / IndexTTS 本地服务 | ⬜ 计划中 | 以 HTTP 供应商接入（它们自己管模型与训练），桌宠只做客户端 |

## 2. 已试过的中文音色（实测记录）

| 音色 | 基频中位 | 听感 | 结论 |
| --- | --- | --- | --- |
| 小雅 zh_CN-xiao_ya-medium | 241 Hz | 少女偏成年，**用户判定“还是青年女性”** | 保留作兜底，需配合少女化处理 |
| 华言 zh_CN-huayan-medium | 214 Hz | 温柔成年女声 | 用户判定不可用 |
| 超文 zh_CN-chaowen-medium | 133 Hz | 男声 | 不可用于小寻 |
| 云端 晓伊 zh-CN-XiaoyiNeural | 305 Hz | 少女音色（用户认可） | ✅ **已选定为小寻的少女音色（标准，不加偏移）** |
| 云端 晓双/晓萌 | — | 供应商音色表已失效（NoAudioReceived） | 不可用 |

> 参考区间（pyin 实测）：成年女声 ≈165–255 Hz，少女 ≈200–300 Hz，童声 ≈250–400 Hz。

## 3. 少女音的合法来源（按推荐顺序）

### A. 开源模型的年轻女声（推荐先试，可离线、无额度）
| 候选 | 许可 | 特点 | 获取 |
| --- | --- | --- | --- |
| **Kokoro-82M**（zf_xiaobei / zf_xiaoni / zf_xiaoxiao 等中文女声） | Apache-2.0（模型卡） | 82M 参数，CPU 也快，音质自然，中文女声年轻 | HuggingFace `hexgrad/Kokoro-82M`；ONNX 版见社区 `kokoro-onnx` |
| **sherpa-onnx 语音模型库**：`matcha-icefall-zh-baker`（女声）、`vits-icefall-zh-aishell3`（174 说话人，含年轻女声）、`sherpa-onnx-vits-zh-ll` | Apache-2.0（发布仓库） | 数量多、可选说话人，需按说话人逐个试听 | GitHub `k2-fsa/sherpa-onnx` 的 tts-models 发布页 / ModelScope |
| **Piper 其他 zh 音色** | 见各自模型卡 | 目前只有 huayan / xiao_ya / chaowen 三个（都不够少女） | rhasspy/piper-voices |

> ⚠️ **许可提醒（必须核对）**：Piper 的 `xiao_ya` 标注训练数据来自 **Data Baker BZNSYP，Non-commercial**；
> 若将来要商用，需要换成许可允许商用的音色（例如以 Apache-2.0 数据集训练的模型），并在 `meta.json` 里如实登记。
> 「AISHELL-3 / Baker」等数据集的许可也需逐项确认，不确定就不用于商用。

### B. 云端供应商的正规音色（现用方案）
- 已选定 **晓伊（zh-CN-XiaoyiNeural）**：用 `tools/voice_render.py` 在 GitHub Actions 上渲染，结果自动提交回仓库。
- 换供应商/换音色只改 `characters/xiaoxun/voice/plan.json`，不改代码。

### C. 自己做音色（训练）——见第 5 节

### 🚫 明确禁止
- 克隆任何真人声音（声优、主播、网上的音源）——用户已明确禁止，且存在法律风险；
- 直接使用商业角色的官方语音（版权）；
- 使用没有许可说明的音色包（无法登记来源）。

## 4. 音色包安装（下载即用）

```bash
# 目录或 zip 都可以；会校验能否真合成，并生成 sample.wav 试听
python3 tools/voice_packs.py install ~/Downloads/kokoro_zh_female.zip --id kokoro_zh_female
python3 tools/voice_packs.py list          # 看语言 / 年龄感 / 许可
python3 tools/voice_packs.py verify <id>

# 用新音色合成（psola = 只抬基频、保共振峰，少女化的正确做法）
python3 tools/voice_local.py --voice kokoro_zh_female \
    --text "你好呀，我是小寻。" --out /tmp/a.wav --pitch 1.20 --shift-method psola
```

音色包内含 `model.onnx`、`model.onnx.json`、`meta.json`（必填 `license` 与 `source`）、`sample.wav`。
装好后写进 `config/voices.json` 的 `voice` 字段即可让软件使用。

## 5. 训练自己的音色（说清楚可行性与边界）

**软件里做“音色训练”是可行的，但正确的架构是：训练交给专门的语音项目，桌宠通过插件调用。**

| 方案 | 需要的数据 | 硬件 | 许可 | 适配方式 |
| --- | --- | --- | --- | --- |
| GPT-SoVITS（微调） | 5–30 分钟干净语音 | 6–8GB 显存 GPU | 代码 MIT；**声音必须是自有/已授权** | 训练后导出 ONNX，做适配器；或直接调它的 HTTP 服务 |
| CosyVoice2 / Fish-Speech（零样本） | 3–10 秒参考音频 | 4–8GB 显存 | 同上 | HTTP 供应商插件 |
| IndexTTS2 / F5-TTS | 数秒参考音频 | 4–8GB 显存 | 同上 | HTTP 供应商插件 |
| 本机微调 Piper | 1–2 小时语音 + 文本标注 | CPU 也能，但慢 | 训练数据许可必须可商用（如自行录制） | Piper 官方训练脚本 → 直接产出 `.onnx`（我们的格式原生支持） |

**建议路线（也是我要实现的）**：
1. **语音供应商统一接口**：`config/providers.json` 里每个供应商声明 `tts` 能力（`kind`：`openai_compatible` / `piper_local` / `local_server`），
   自动降级顺序：云端 → 本地服务 → 本地音色包 → 纯文字。
2. **音色包导出规范**（第 4 节格式）：任何训练工具训练完，导出成音色包即可被桌宠使用——**训练与应用解耦**。
3. **训练配方（外部工具）**：`tools/voice_train/` 下提供 GPT-SoVITS / CosyVoice / Piper 三种配方与导出脚本（写清数据要求、命令、许可检查）。
4. **合规闸门**：音色包安装时强制填写 `license` 与 `source`；训练工具在导出时要求声明“声音来源与授权”。

> 沙箱里**做不到**训练：无 GPU、无外网、内存 3GB。训练必须在你的 Windows 机器或有 GPU 的服务器上跑；
> 我能做的是把配方、导出脚本、适配器与验收测试写好，并在你训练完后把音色接进软件。

## 6. 我的建议（当下）

1. **小寻正音用云端晓伊标准**（已按你的决定写进 `config/voices.json`）；
2. 本地兜底用 `xiaoya` + `psola`（只抬基频保共振峰，不再有金属音），断网时仍能出声；
3. 你有空时下载 **Kokoro 中文女声** 或 **sherpa-onnx 的年轻女声** 音色包丢进 `voices/`，我负责适配与验收（如果格式不是 Piper，我写适配器）；
4. 如果你决定训练专属音色，告诉我采集条件（时长、设备、是否自有声音），我把训练配方和导出脚本写好，你在本机跑训练。
