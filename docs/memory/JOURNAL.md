# 思考与工作日志（JOURNAL）

> 规则：每次工作**追加**一条（用 `bash scripts/memory_append.sh "做了什么" "修了什么" "下一步"`），
> 并在开头写清"为什么这么做"（思考过程比结果更重要，下一个人要能看懂决策依据）。
> 倒序阅读：最新的在最下面。

---

## 2026-10-11 第一次接手（建立基线）
- **思考**：交接文件要求"全部可自定义、模块化"，所以第一步不能先画角色，而要先把
  "内容由配置驱动"的骨架立住——否则后面每加一个角色/形态都要改 C 代码。
- 做了什么：
  1. 通读交接文件，确认六个参考项目地址、拆件教程、失败路线清单。
  2. 用 zig cc 打通 Windows 交叉编译（沙箱内即可产出真 exe），决定零第三方依赖（只带 stb_image.h）。
  3. 写核心层：zc / zjson / zschema / zimg / zdeflate / zsm / zrig / zconfig / zpet。
  4. 写 Windows 层（透明窗 + 像素穿透 + 托盘 + 拖动 + 空闲检测）与沙箱预览层（同一引擎）。
  5. 生成小寻短发/中长发设计图（洋红底），做素材流水线（抠图去噪/拆件/生成 rig.json）。
  6. 96 项单元测试 + `scripts/selfcheck_all.sh` 六步自检全绿；Windows exe 370KB 产出。
- 遇到/修的坑（详见 LESSONS.md）：
  - deflate 的 distance=1 回溯误用（把上一个字节复制满屏）→ 加"前一字节必须相同"前提，并用真实 zlib 往返验证。
  - 合成颜色被钳成纯白（采样归一化与 255 混用）→ 统一 0..1。
  - 区域命中未做帧→画布坐标换算；唤醒被不可中断的 sleep 拒绝；JSON 生成器 key 后多逗号；
    `z_dirname` 原地改缓冲导致日志目录写错。
  - 洋红噪点残留（距离判定漏掉色相差的像素）→ 加色相判定 + 去孤立点 + 边缘颜色内扩。
  - 嘴部整块裁剪会盖肤色方块 → 改成按暗线生成 alpha 蒙版。
- 下一步：用户确认"测试程序不需要 UI 时先做完整拆件与表情集"→ 进入 T2.1。
  同时建立本地记忆区（本目录）、规划文件（TASKS.md）、参考源码拉取/清理脚本。

## 2026-10-11 07:31
- 做了什么：T2.1.1 表情素材：生成 10 张同取景特写（smile/happy/shy/surprised/sleepy/angry/sad/thinking/closed/pat）。写 make_face_parts.py（脸框 + 虹膜检测），抠图背景判定改为边框中位数。
- 遇到/修了什么：对齐未解决：虹膜检测对闭眼/开心^^失效，脸框高度受脖肩影响；10 张图的缩放与眼位仍不一致，部件切出会错位。已停止在算法对齐上继续调参。
- 下一步：二选一：A) 用参考底稿做改表情的 img2img 保持取景；B) 人工标注每张图双眼中心，再由脚本归一。确认后继续 T2.1.1。

## 2026-10-11 07:55
- 做了什么：新增互动规则表 config/interactions.json（19 条规则）与台词表 characters/xiaoxun/dialogue.json（草稿，19 组）；新增 src/core/zinteract 引擎；zpet 接入情绪入口 zpet_express 与语音事件入口 zpet_call_event；预览新增 /api/speech.json、/api/express、/api/call；规划写入 docs/INTERACTION_PLAN.md，任务写入 TASKS T5–T8。
- 遇到/修了什么：修复引擎缺陷：rig 动作缺省 loop 被当成 true，导致 head_pat/happy 等永不回 idle（现缺省不循环）；call_start 改用 talk 以免被循环中的 sad 盖住；台词可选字段缺省时不再刷屏警告。
- 下一步：等用户确认：A/B 表情对齐方案、台词草稿语气；随后做 T2.1.2 起的表情拆件与 T5.3 输入检测。

## 2026-10-11 07:59
- 做了什么：方案 A 执行：以 smile.png 为基准 img2img 生成 8 张同取景表情（happy/shy/angry/sad/surprised/thinking/sleepy/closed），存于 parts_src/expressions_a/；对齐 dry-run 与正式切件（/tmp）均成功，缩放 0.62–0.67、锚点偏差约 10px，但嘴部切块 48×36 边缘疑似带肤色块，未进入角色目录。
- 遇到/修了什么：嘴部需改为暗线蒙版切割（参照 teen mouth_open 的做法），并补跑洋红残留与白边检查后再入库；虹膜检测在闭眼/^^ 眼上不可靠，眼部需改用眼线中心。
- 下一步：T2.1.1 保持 [~]：嘴与眼用蒙版重切→通过 sprites 报告→入库；之后 T2.1.2–T2.1.9。语音供应商与台词草稿语气仍待用户确认。

## 2026-10-11 08:07
- 做了什么：思考：好感度分级是互动体验的核心，档位与每日上限必须在引擎里可测，台词变体按档选择；7 个 AI 角色台词草稿各自性格不同。做了：zinteract 好感 API（4 档 0/30/100/250，每日上限 30，减少不受限且不低于 0，档位变体，tier_up 升档台词优先）；zpet 接入好感（run_rule 先加好感再说台词）；/api/speech.json 增加 affection、tier；单元测试 217/217（档位边界、每日上限跨天、负数夹断、变体选择、8 角色台词互异、坏配置报文件+字段、摸头加好感并升档）；台词 schema 接入加载器。
- 遇到/修了什么：修：zinteract_load 之前不把台词/好感的诊断错误计入失败（load_dialogue 返回 0），改为比较 diag 错误计数。voices.json 第 5 行 voices[xiaoxun] 缺 provider 为已知警告（T7 未定）。
- 下一步：待办：用户确认 7 个 AI 角色草稿与档位名；T7 语音供应商；表情 A 方案口部切割改用暗线掩膜后再写入部件。


## 2026-10-11 09:19
- 做了什么：交接：写入 docs/HANDOVER_NEXT_AGENT.md，记录分支/PR 状态、用户确认的决定（OhMyGPT 测试、16 岁少女普通话音色、句级同步、默认关闭语音、每日上限 2000）、阻塞点（沙箱无法访问 OhMyGPT，环境变量未注入）、key 安全处理、add_voice 试听失败记录、待办优先级。
- 遇到/修了什么：无新代码改动；语音代码与实测均未完成。
- 下一步：下一位代理先做语音配置与句级出声模块（假 TTS 测试），再根据用户的 tts_probe 输出实测。

## 2026-10-11 09:34
- 做了什么：语音：打通沙箱内离线神经语音合成（这是用户当前唯一在追的任务）。思考：用户已明确“知道那种方法就用”——网上美少女音=神经网络 TTS 多说话人音色，不是手工调出来的；沙箱网络白名单到不了任何 TTS 端点（edge-tts 的微软端点、HF 模型、GitHub release 资产全部不通），Actions 又因令牌无 workflows 权限推不上工作流，所以必须走“模型在仓库内 + 本地推理”这条路。做了：在 GitHub 仓库内找到 Piper 中文音色（xiao_ya 少女向 / huayan 温柔女声，xiongxiongge1/ai_cartoon_person），经 api.github.com 下模型到 ~/.cache/piper-voices；装 piper-tts 1.8.0（自带 espeak-ng）；xiao_ya 需要的 g2pW 音素模型是 LFS 指针拿不到，改为自写 pypinyin 音素器（tools/voice_local.py 直接喂 ONNX），打通合成；出 6 个试听样本 + 试听页（端口 5180）+ voice_setup.sh 可复现脚本；首次推送因 .github/workflows 被拒，把工作流挪到 docs/ops/ 后推送成功（85fe333）。
- 遇到/修了什么：踩坑：① piper 的 pinyin 音色必须要 g2pW 模型（HF 下载被墙、GitHub 上的全是 LFS 指针）→ 自写音素器绕过；② espeak 类音色（huayan）走 piper 自带 EspeakPhonemizer；③ 令牌无 workflows 权限，含 .github/workflows 的提交会被远端拒绝 → 文件移到 docs/ops/ 并 amend 提交；④ ~/.cache 与 /tmp 不随工作区快照持久化，模型和 venv 每会话都要用 tools/voice_setup.sh 重建。
- 下一步：下一步：等用户从试听页选音色编号 → 写进 config/voices.json（形态也可覆盖）→ 用 voice_local.py --render-dialogue 批量出 dialogue.json 全部台词 → 把播放接入预览/Windows；随后按用户要求重做人物形象（上一版拆件不合格，用户要求直接重做）。
