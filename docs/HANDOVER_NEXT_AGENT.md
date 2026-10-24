# 交接文件（给下一位代理）—— 语音与小寻工作（2026-10-11）

> 读这份文件前，先读 `HANDOVER_RESTART (1).md`（唯一执行依据）和 `docs/VOICE_PLAN.md`（语音规划与用户决定）。
> 本文件只记录**当前状态、已确认的决定、阻塞点和下一步**。用户很不满意上一位代理的拖延，请直接动手，少问，多给可验证的结果。
>
> **2026-10-17 补**：本文件是**语音线**的交接。立绘/动画线请改读 `docs/HANDOVER.md`，
> 并按需补读两份新规划：`docs/PHYSICS_PLAN.md`（物理底座 2.0 = T47，含现状盘点与七步改造）、
> `docs/PRESENCE_PLAN.md`（T48 外设模式 / T49 三级视线跟随 / T50 兽耳娘与情绪耳尾 / T51 表情扩充，
> 以及从桌宠与 AI VTuber 项目里挑出的 12 条可吸收能力）。

## 1. 分支与 PR

- 分支：`arena/b3359546-zhuochong`（只能用这个分支，不能切换或新建）。
- PR：https://github.com/wpch3/zhuochong/pull/1（目标 `main`）。PR 未合并。
- 最新提交：`1f9e46a`（用户上传的 `tts_probe_out.mp3`，是一段男声测试音频，不要用它做音色）。
- `make test`：217/217 通过（截至 `49bf3c2`）。`scripts/selfcheck_all.sh` 六步全绿（截至 `49bf3c2`）。之后的改动只涉及文档、`.gitignore` 和 `tools/tts_probe.py`，没有重新跑自检。

## 2. 用户已确认的决定（不要改）

1. **测试中转：OhMyGPT**，地址 `https://api.ohmygpt.com/v1`，兼容 OpenAI 接口。正式供应商候选是阿里云百炼；但引擎层必须**兼容所有供应商**，不能写死。
2. **音色：小寻要的是少女音**，对应设定里的“少女”形态（16 岁左右），**普通话**（不是粤语，不是台湾口音，不是成年女声），风格：**温柔、大方、贤惠、智慧**，二次元少女感。要自然，不要刻板。
3. **同步方式：句级同步为默认**（每句先合成，播放时文字同时出现，播完再出下一句，Neuro-sama 的做法）。逐字高亮只在供应商真的返回时间戳时启用，不做估算。
4. **开关**：语音出声默认**关闭**。需要：总开关 `voice.output.enabled`、每句出声开关、每日字符上限（默认 **2000 字符/天**，可在配置里改，超出后自动退回纯文字）、语音通话回应开关。
5. **性格**：接受“标签 → 原创二次元化”。7 个 AI 角色（深语、拂晓、星璇、双晞、通琳、月见、闪电）的性格和台词仍是 `draft`，用户还没正式确认。
6. **不能克隆任何真人声音**（包括声优、配音演员、网上音源）。用户问过“开源音色”和“大肥鱼音色”，结论：不能用。合法来源只有：供应商正规音色（需看其服务条款）、或本人/已授权本人的录音。

## 3. 阻塞点（已确认，不要重复尝试）

- **沙箱连不上 `api.ohmygpt.com`**（SSL 握手失败，`SSL_ERROR_SYSCALL`）。沙箱的网络白名单只有 github.com、codeload.github.com、api.github.com、registry.npmjs.org、pypi.org、files.pythonhosted.org。这一点代理无法修改。**因此在沙箱里无法实测 TTS。**
- **沙箱里没有 `ZC_RELAY_BASE_URL` / `ZC_RELAY_KEY` 环境变量**（用户说已设置在 Arena 里，但沙箱进程里查不到）。不要假设它们存在。
- **测试 key 的处理（非常重要）**：
  - 用户在聊天里发过两个 key，又在 `.gitignore` 里误提交过一个 key（已在 `17f96e0` 删除，但仍在 Git 历史里）。用户说已作废并更换，但**历史中的 key 仍然有泄露风险**，需要提醒用户。
  - **绝对不要**把 key 写进任何文件、不要提交、不要在聊天里要 key、不要在输出里回显 key。
  - 不要尝试用聊天里出现过的 key 发请求。用户明确要求“不要浪费我的时间”，但安全规则优先。
- **`.env` 文件**：用户曾把 key 写进仓库根目录 `.env` 并被提交（`3d089d7`），后被删除（`20839ad`）。`.gitignore` 现在已忽略 `.env`。

## 4. 用户的本机测试（进行中）

- 脚本：`tools/tts_probe.py`（仓库里已提交，只用 Python 标准库，只从环境变量读 key，不打印 key）。
- 用户在 Windows PowerShell 本机运行：先设置环境变量，再 `python tts_probe.py`。
- 用户要求的是“本机测试”，所以**真实结果要等用户把输出发回来**。在此之前，不要声称 TTS 已测试通过。
- 用户之前的报错都是 PowerShell 写法问题：`$env:ZC_RELAY_KEY = "..."` 必须带双引号；文件路径是 `D:\test\tts_probe.py`，不是 `tools\`。

## 5. 音色试听（失败记录，不要重复同样的方式）

- 用平台的 `add_voice` 工具做了 4 组试听（voice-00 到 voice-03）。用户都不接受：
  - voice-00、voice-01：不是少女音。
  - voice-02：没有明确反馈，但用户没有接受。
  - voice-03：粤语、成年女性音色。
- **`add_voice` 工具无法指定年龄、普通话**，只能靠性别和 `use_case`，效果不可控。不要再用这个工具盲目试听小寻的音色。
- 注意：`add_voice` 返回信息里会写“the user selected a voice”，这只是工具的提示语，**不等于用户真的选中**。以用户的口头反馈为准。
- 正确的做法：用 `tts_probe.py` 在用户本机对 OhMyGPT 的可用音色逐个合成同一段普通话，每个保存为文件，由用户自己挑。需要 OhMyGPT 的音色名单（沙箱查不到，要由用户本机运行后反馈）。

## 6. 尚未完成的工作（按优先级）

1. **语音链路代码（沙箱内可以做，不依赖网络）**：
   - `config/voices.json` 增加 `voice.output`（enabled 默认 false、per_line、daily_char_limit 默认 2000）和 `voice.call` 配置，并写 schema。
   - 在 `src/core/` 增加语音输出模块：句级切分 → 调用 TTS 适配层 → 播放队列。TTS 适配层接口要通用（OpenAI 兼容 `/audio/speech`，以及其他供应商），用**假 TTS 服务**做单元测试（超时、限速、额度耗尽、开关关闭）。
   - 每日额度计数必须跨天重置，且超限后不出声但仍显示文字。
   - 测试覆盖：开关关闭时不调用 TTS；超过 2000 字符后退回文字；句切分正确；失败不影响文字显示。
   - Windows 播放部分标记 [需真机]，不能声称完成。
2. **语音同步文字**：句级同步先做。逐字高亮做成可选项，供应商无时间戳时禁用。
3. **OhMyGPT 实测**：等用户的 `tts_probe.py` 输出。根据输出判断：是否支持 `/audio/speech`、返回音频格式、是否带时间戳字段。
4. **角色台词二次元化**：按用户要求，给 7 个 AI 角色和小寻重写台词和性格（原创，标签级参考：傲娇、元气、温柔姐姐、三无、腹黑、天然呆等）。小寻性格：温柔、大方、贤惠、智慧，少女感。之后仍保持 `status: draft`，等用户确认。
5. **表情方案 A**：`parts_src/expressions_a/` 的 8 张图 + `parts_src/expressions/smile.png` 已由 `tools/make_face_parts.py` 重新对齐，输出在 `forms/teen/sprites/expression_parts_a/`。九个目标情绪（含 body 派生 calm 基准）+ 独立 closed 眨眼帧；报告 10 项（9 张生成图 + 1 body reference），9/9 对齐成功，眼件 75×52、洋红残留 0。已修复脸框连到身体造成的蓝发夹/衣服误检。静态预览可看同目录 `preview_contact_sheet.png`。这些尚未接入 rig/`part_overrides`；下一步应做运行时切换与真机/目视验收，而非再运行旧版抠图。
6. **清理**：`~/.cache/zc-refs/`（约 3 GB 参考仓库）在不再需要时删除，并在 JOURNAL 记录。

## 7. 环境与工具

- Python：仓库工具用 `~/.imgenv`（pillow/numpy）；如果消失，`python3 -m venv <dir> && <dir>/bin/pip install pillow numpy`。
- zig（Windows 交叉编译）：`~/.cache/tc/zigenv`，如果消失，`python3 -m venv <dir> && <dir>/bin/pip install ziglang==0.17.0`。
- `make clean` 会删除 `dist/`，之后必须 `make win`。
- 预览：`make preview`（5173 端口，必须绑定 0.0.0.0）。用 `start_process` 启动，名称 “Pet preview”。当前运行中的预览进程可能已经停止，启动前先检查。
- `scripts/memory_append.sh` 必须带三个参数运行；**不要不带参数运行**，否则会写入空条目。
- 自检：`bash scripts/selfcheck_all.sh`，必须全绿才能交付。

## 8. Git 操作注意

- 用 `git pull --ff-only origin arena/b3359546-zhuochong` 同步；不要强推，不要切换分支。
- 用户会直接在 GitHub 上提交（例如 `.env`、`.gitignore`、上传的 mp3），本地要先 fetch 再拉取，避免覆盖。
- PR 合并或关闭前必须先确认用户要求。

## 9. 用户的不满（请务必注意）

- 用户多次指出：我说了却没做完，拖延，浪费时间，重复问同样的问题。**不要再空谈，先做能做的（语音代码、交接、测试脚本），再给结果。**
- 用户不满意我擅自试听错误音色，也不满意我说了“完成”却没有完成。**只在有可验证结果时才报告完成**，并标明哪些是 [测试锁]、[沙箱实测]、[需真机]。
- 用户要求用中文报告。
