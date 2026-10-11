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

## 2026-10-11 09:50
- 做了什么：语音：云端微软少女音色跑通（这是用户最急的点）。思考：用户否掉'年龄感'两次，说'你到底能不能行'；行业做法就是用带少女音色的神经 TTS。行动：① 用户补了 workflows 权限后，把 .github/workflows/voice-render.yml 真正推上去并跑通 Actions（沙箱读不到 Actions 日志域名，改成失败时把日志提交回仓库 ci-logs/，注意 logs/ 被 .gitignore 忽略导致第一次白提交）；② 定位失败原因：edge-tts 锁 7.2.8 版本会失败，放开版本即可合成；晓双/晓萌音色已失效（NoAudioReceived），脚本已改为单个音色失败不阻断整批；③ 云端产出：晓伊 5 版样本（0/+15/+30/+45Hz、+30Hz 慢5%）+ 38 条台词全部渲染，结果由 Actions 自动提交回分支；④ 本地另有一条离线路线（Piper + 少女化），修好 resample 方向后实测 267/288/304 Hz，与云端形成对照。
- 遇到/修了什么：踩坑：① .gitignore 忽略 logs/，CI 回传日志必须换目录（已改 ci-logs/）；② edge-tts 单个音色失效会让整批中断（已容错）；③ 沙箱读不到 results-receiver.actions.githubusercontent.com 的日志下载域名，只能靠回传；④ 本地 resample 方向搞反会降音高（已修，纯音验证 234→264.5/286.7/305.5 Hz）。
- 下一步：下一步：等用户从试听页选编号 → 写 config/voices.json → 用选定音色重渲全部台词 → 接播放链路；随后重做人物形象。

## 2026-10-11 10:05
- 做了什么：语音与规划：本地音色的真正解法 + 产品总规划。思考：用户明确否掉小雅/华言（都是青年女性），并问'本地还有什么办法/能不能自己下载音色/能不能做训练功能'。判断：本地缺的不是算法而是少女音色的底子模型，正确解法=①音色包机制（下载即装）②少女化用 TD-PSOLA（只抬基频保共振峰）③训练走外部工具+音色包导出。做了：① tools/voice_local.py 新增 TD-PSOLA（实测 238→284/321Hz，时长不变，无金属音）与音色包路径查找；② 新增 tools/voice_packs.py（install/list/verify/remove，zip 或目录、自动生成试听样音、强制登记 license/source）+ voices/ 目录与 README + registry.json；实测装好 xiaoya 与 chaowen 两个包（chaowen 实测 133Hz 是男声，坐实'本地缺少女音'）；③ config/voices.json 定案：云端晓伊标准（用户选定）+ 本地 xiaoya+psola 兜底；④ docs/VOICES.md（音色手册：支持格式、实测记录、合法来源清单 Kokoro/sherpa-onnx、训练可行性与边界、合规红线）；⑤ docs/PRODUCT_PLAN.md（三进程架构 + 15 个功能分区 + 20 项缺口清单 P0-P2 + M1-M6 里程碑）；TASKS 追加 T9-T14。
- 遇到/修了什么：踩坑与结论：① pyworld 在沙箱编译不了 → 改用纯 numpy 的 TD-PSOLA（索引映射版，第一版按时间映射导致基频反而降低，改按索引比例映射后正确）；② 音色包 install 需支持 zip 内子目录与子目录里的 meta.json（已修）；③ 试听页不能引用服务器根目录之外的音频 → 把音色包样音复制进 samples/；④ Piper 只有 3 个中文音色且都不够少女，本地必须靠用户下载新音色包或训练。
- 下一步：下一步：等用户在试听页选（云端标准已定；本地可试 16/17/18 PSOLA 三档）→ 用选定音色重渲台词并接播放链路；随后按用户命令做人物重做（先出 3 版设定图给用户挑）+ 按 T9 起做工作区骨架。

## 2026-10-11 10:07
- 做了什么：规划：训练区（音色模型 + AI 模型）正式加入；角色模板定位定案。思考：用户要求'让工具成为完整工具'，所以训练必须是软件的一等公民；同时用户两次问根目录模板要不要用，必须给确定答复。做了：① 核对三张参考图（1696×2528 / 1280×1280，白底），定案=设定参考+img2img 底稿+LoRA 训练数据，不是素材，登记 characters/xiaoxun/design/reference.json；② 写 docs/TRAINING.md（六类训练、执行器三选一、数据集管理、模型库与 model card、评估指标、硬件预算、合规硬规则、与生图/语音/对话/工作区衔接、T15.1-T15.10）；③ PRODUCT_PLAN 加第 16 节 + 缺口 11b + train/ 目录 + M0.5 里程碑；④ TASKS 追加 T15；⑤ MEMORY 增加第 11-13 条关键决策。
- 遇到/修了什么：结论：沙箱无 GPU/外网，训练只能在用户机器或云上跑；沙箱内负责配方、数据脚本、导出适配器、评估与单测。训练区最先做'角色 LoRA'，因为它能一次性解决历史两大痛点：拆件风格不一致与取景漂移。
- 下一步：下一步：① 用户选本地 PSOLA 档位（试听页 16/17/18）；② 出 3 版小寻少女形态设计图给用户挑；③ 按 T9.1/T9.2 起做工作区骨架与本地网关；④ 按 T15.7 准备角色 LoRA 的数据集清单与配方（等用户本机 GPU）。

## 2026-10-11 10:21
- 做了什么：第八轮：把用户五个追问逐条落到仓库。思考：用户反复问同一批问题=必须写进文件而不是只在聊天回答。做了：① 七个参考项目全部拉取（~/.cache/zc-refs，含 vpet 1.8G / airi 948M）并逐个查验关键源码，结论写入 docs/REFERENCE_NOTES.md（Cubism 的 drawMeshWebGL=每部件独立网格+独立绘序+遮罩+deformer 层级；VPet 的 IModInfo/CoreMOD/ModLoader=模组化工程做法；airi pipelines-audio=语音流水线与打断；photocraft selection/图层=素材精修参考）；② 'AI 模仿动漫角色唱歌'=SVC（So-VITS-SVC/RVC/DiffSinger），本地可跑需 GPU，红线=自有/授权音源，写入 docs/TRAINING.md 第十节，并给出 TTS 唱句+音高对齐的最小可用路线（T16.7）；③ PRODUCT_PLAN 增加第七节“完全自定义矩阵”（18 项逐条对应文件与验证）与 6 项新缺口（多档案/通知/i18n/导入导出/定时自动化/远程访问），TASKS 追加 T16；④ MEMORY 增加第 14-17 条关键决策。
- 遇到/修了什么：无阻塞；沙箱无法验证的仍标注[需真机]。Cubism 框架里没有独立 deformer 文件（形变在 model 层由参数驱动），已按实际结构描述，未编造。
- 下一步：下一步：① 素材重做（先写锚点标注与蒙版验收工具，再出三版设定图）；② 按 T9.1/T9.2 做工作区骨架与本地网关；③ 本地音色继续走 Praat 少女化与音色包（等用户选 16/17/18 与 16-20 对比）。
