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

## 2026-10-11 10:27
- 做了什么：第九轮：按用户要求把聊天框全部要求完整入库。思考：用户说'做完后才开始工作，不然你又忘了'——根因是过去只在聊天里答、没落文件，换代理即丢。做法：记忆区从四件套扩成七件套。新增 docs/memory/REQUIREMENTS.md（需求总账：A 最高优先级8条 / B 产品范围15条 / C 视觉UI13条 / D 立绘素材15条 / E 语音8条 / F 工作方式14条 / G 变更记录 / H 角色设定8条 / I 安全许可6条，每条标来源[聊天|交接|规格]+落点文件+状态）；新增 docs/memory/WORKFLOW.md（开工五步、七参考项目查证顺序表、开发循环与命令、素材流水线、交付标准与测试标签、收工三件事、汇报格式、十条绝对禁止、环境恢复、文件地图）；新增 docs/memory/GAPS.md（基线能力表 + 缺口 G1-G33 分 P0/P1/P1.5/P2/小修 + 需用户提供 N1-N8 + 执行顺序）。MEMORY.md 头部改成七件套索引并写明'新要求当轮就要写进 REQUIREMENTS.md'，当前状态表同步（217 单测、UI 第一版、warp 形变行）。
- 遇到/修了什么：无阻塞。注意：REQUIREMENTS.md 规定要求变更只能在 G 节登记覆盖关系，不许删行，避免再出现'改过口又忘了'。
- 下一步：记忆区已封存，现在开始干活：① 重编并重启预览让 zimg_draw_warp 生效（当前 :5173 跑的是旧二进制）；② 修 G30/G31（info.json 缺 mood/affection/tier、界面显示 form_name）；③ 素材锚点标注与蒙版验收工具。

## 2026-10-11 10:46
- 做了什么：第九轮（下半场）：记忆区封存后开始干活，主攻'可以做动作的动态立绘'。做了四件事：① 预览服务补状态字段——/api/info.json 增加 mood/affection/tier/tier_name 与 form_names/outfit_names，界面状态片不再是占位数据，形态/服装下拉显示角色包里写的中文名（新增形态不用改前端）；② 实测发现形变方向错了——用每行 alpha 重心量出 sway 的位移峰值在身体中段、头和脚都不动，根因有两个：bend_x 与 bend_y 共用同一个 curve 字段（后写的覆盖先写的），以及 bend_factor 的 t 从顶边算起导致'根部固定'实际固定在头顶；③ 修引擎：zimg 的曲线语义改为'底边是根'并新增 tip 曲线（后发/裙摆/尾巴），zimg_draw_warp 改成 X/Y 各带一条曲线，zrig 拆成 p_bendcx/p_bendcy；补 4 项单测（root 顶端动底端不动 / tip 反过来 / sine 中段最大 / X 的曲线不被 Y 覆盖），测试把一个真 bug 钓出来了——draw_impl 的目标包围盒没有按形变位移扩张，弯出去的那一端会被裁掉，已修；④ 重调动作并让 idle 常驻呼吸：单图层素材下身体弯多少 head 组就要跟随多少（脸部系数 root 0.59 / sine 0.66），否则五官从脸上滑走。
- 遇到/修了什么：实测证据：sway 横移剖面从头到脚单调递减（canvas218 处 -4.49px → 脚部 -0.01px），脚钉死；idle 不点按钮也在动（峰值 33292 像素变化，占画面 9.6%）；头部 2 倍放大图确认眼睛贴脸、无接缝。make test 221 项全绿（新增 4 项），selfcheck_all.sh 六步全绿。
- 下一步：下一步：① 把 bend 跟随系数做成引擎自动计算（现在是手算写进 rig，素材换了要重算）；② 锚点标注 + 蒙版验收工具，为素材重做铺路；③ 工作区骨架 T9.1。

## 2026-10-11 11:19
- 做了什么：第十轮：决定先做底层再做立绘——理由是立绘重做会让手算的跟随系数全部作废，底层做对了素材换几次都不用重算。做了：① 形变跟随从'rig 里手写系数'改成引擎自动计算：groups 支持 bend_follow，部件按**自己所在高度**取父部件的形变位移（比按组枢轴平移更接近 Live2D 的逐顶点形变），rig.json 里删掉所有手算的跟随通道；② 修了一个坐标 bug：group_matrix 的枢轴用的是画布坐标，而部件矩阵是帧坐标，缩放 0.55 时组旋转会绕错点近一倍距离，现在统一到帧坐标；③ make_rig.py 按素材实际情况裁剪动作——检测不到独立头部件就不发 head 的 rot_deg 通道，并在 rig.notes 写明'拆出 head_base.png 后自动恢复'；④ 新增只读查询 zrig_group_offset_x/y、zrig_bend_at、zrig_part_offset_x、zrig_part_pos_y，用于验收与调试。
- 遇到/修了什么：实测：五官相对脸部的横向偏移波动 idle 0.80px / sway 0.99px / breath 1.91px（之前 sway 3.66px），sway 画面变化峰值 43361px 说明动作幅度没缩水；引擎级单测把跟随误差卡在 0.01px 以内。踩坑：对生成器做字符串替换时误改了 part() 的 return，产出 5 个 null 部件且脚本不报错，已写进 LESSONS 第四节。make test 223 项全绿，selfcheck 六步全绿。
- 下一步：下一步：素材侧的两个前置工具——锚点标注（给拆件定关节/挂点）与蒙版验收（形状重合度，不只看颜色），然后才是三版设定图。

## 2026-10-11 11:28
- 做了什么：第十一轮：素材重做的两个前置工具落地（先做工具再画图，否则又是手写坐标那一套）。① tools/make_anchors.py：从剪影自动量关节——先用水平腐蚀把手臂从躯干剥离（否则垂下的手会把'最宽处'拉到手背那行，腰会错判到裙摆以下），膝盖用逐行面积而不是宽度（宽度会被两腿之间的空隙骗到），手臂只在躯干左右两侧且用整段中位数界定边界（否则两条腿被当成手，腕掉到膝盖），眼线按色卡里的瞳色实测且阈值收紧到 50、只在头部上 85% 找（阈值 70 会把青色衣领算进去，眼线被拖到下巴）。产出 anchors.json（头顶/眼线/嘴线/颈/肩/肘/腕/腰/髋/膝/踝/脚底）+ 标注预览图。② tools/check_assets.py：形状 IoU（按 alpha 包围盒归一化后比，否则裁剪缩放差异会被算成形状不符，实测 0.42→0.983）、色卡距离、关节对位、落在身体内、键色/白边残留，53 项检查，退出码可用于 CI，已接进 selfcheck 第 4 步。③ 色卡入库 characters/xiaoxun/design/palette.json（改配色只改这里）。
- 遇到/修了什么：注意工具自身也会错：第一版把参照设计图按文件名排序选成了中长发那张，IoU 看起来只有 0.42，像是素材坏了。结论——验收工具报错时先确认比的是不是同一个对象。当前素材 53 项全过，selfcheck 六步全绿。
- 下一步：下一步：用 anchors 驱动拆件（make_parts 按锚点切分区域），然后出小寻四形态设定图；工作区骨架 T9.1 排在素材之后。

## 2026-10-11 13:13
- 做了什么：JOURNAL
- 遇到/修了什么：第十二轮：身体分段 + 分段骨架
- 下一步：做了什么：① tools/make_body_parts.py 跑通并修了三处实测错误——腿的切线被手的剪影骗到髋部（改成只在躯干 x 范围内数段、连续 8 行、每段够宽）、手臂竖切会带走外套前襟和裙边（改成在'离身行 640'以下按真实剪影抠）、躯干顶端重叠带存的是下巴导致转头出现重影下巴（改成颈线复制出的'脖子桩'）；② make_rig.py 自动识别 body_parts.json，生成 7 组分段骨架（root/chest/head/arm_l/arm_r/leg_l/leg_r），枢轴全部取 anchors.json 的真关节点，层序 腿60/61 < 躯干100 < 臂140/141 < 头180 < 嘴210 < 眼220+，并自动恢复转头通道；③ 引擎新增 groups.*.bend_follow_at：整块挂在关节上的部件（头挂脖子、臂挂肩）按关节点那一行取样，贴在父部件表面的五官仍按自己高度取样，两种语义写进 zrig.h；④ 新增只读查询 zrig_part_follow_y / zrig_part_follow_src，跟随单测改成从 rig 读取跟随源与取样高度（两种骨架同一套断言），并加了'同组五官刚性同步'断言；⑤ check_assets.py 增加分段 4 项检查（部件齐全/无损切分/三处关节压力姿势不露底）。实测：make test 225/0 零告警；验收 90 项 0 不通过（静止合成比原图少 0 像素，颈/肩/髋压力姿势新增空洞 -197/0/-1363）；自检六步全绿；帧耗时 0.028s。沙箱重启清空了 home，按 WORKFLOW 第八节重建 ~/.imgenv 与 ~/.cache/tc/zigenv。

## 2026-10-11 13:21
- 做了什么：JOURNAL
- 遇到/修了什么：第十二轮补记：挥手动作与手臂形变
- 下一步：做了什么：分段跑通后加了单图层时代做不到的 wave（挥手）动作，UI 自动多出一个按钮（动作列表是数据驱动的，zpet 从 rig 读）。第一版用 arm_r 组整块旋转 -26°，洋红底放大后看到两个穿帮：肩口露出锯齿切口、外套前襟那条被甩到身体轮廓外。算了一下能兜住的角度=重叠带38÷肩到手276≈8°，远不够挥手，于是改成对 seg_arm_r 打 bend_x/bend_y + curve=tip（顶边即肩部钉死、越往下位移越大），肩口不再开裂——这正是 Live2D 手臂变形器的做法。实测：右臂外缘最大横移 66px（帧坐标，0.55 缩放），五连拍见 logs/preview_check/wave_strip.png；make test 225/0；素材验收 90 项全过；自检六步全绿。另把 breath/sway/wave 的中文名补进 web/app.js 的 ACTION_NAMES。

## 2026-10-11 16:39
- 做了什么：JOURNAL
- 遇到/修了什么：第十三轮：预览码率与接缝羽化
- 下一步：用户反馈两件事：预览卡顿、挥手有切割重叠痕迹。① 卡顿定位：不是引擎慢，是预览**按帧走网络传 PNG**——原来一帧 287KB，12fps 要 3.4MB/s。做了两层优化：zdeflate 从'只有 RLE'升级成真正的 LZ77（32KB 窗口 + 哈希链，固定 Huffman），一帧 287KB→191KB（标准 zlib 是 151KB），像素完全一致、编码 34ms；新增 zimg_downscale（按 alpha 预乘的盒式缩小）与 /api/frame.png?s= 画质档，50% 档一帧只要 60KB（0.68MB/s@12fps，比原来省 5 倍）；前端改 fetch+blob 并按实测单帧耗时自动升降档，页脚显示 实时 fps / KB每帧 / 当前档位，并提供 自动/50/60/75/100 手选。② 接缝：重叠带原来是硬边，一错位就是一条直切割线；现在头/双臂/双腿的重叠带做 alpha 渐隐（静止时下面压着同样的像素，混合结果不变，无损切分仍然 0 丢失）。③ 挥手幅度按重叠带算出上限（38px ÷ 最低行权重 0.59 ≈ 64）后收到 60，远距离的拖影基本消失。实测：make test 225/0、素材验收 90 项全过、自检六步全绿。

## 2026-10-12 05:18
- 做了什么：第十四轮：按用户要求做『零件化』。① 引擎补上 Live2D 式遮罩：zrig 部件新增 mask/mask_only，zimg 新增 zimg_composite_masked()，加载期校验层序与遮罩夹层，遮罩被眨眼隐藏时被裁切件一起消失；新增 5 项单测（235/0）。② 写 tools/make_eye_parts.py：从整块眼睛贴图还原出 眼眶(遮罩剪影)/眼白底/眼球/眼线 四件 × 左右，眼球被眼皮挡住的上半部分按列补全成完整圆，圆心半径用穷举拟合（盖住虹膜又不溢出眼白）。③ make_rig.py 自动接线这四件（层序 216-219/226-229，眼球 mask=眼眶），老动作里的 eye_open_* 自动摊到四件上，新增 look_around 动作（只有眼球动）。④ 色卡按实测补 3 色（线稿黑/瞳孔深蓝），check_assets 146 项全过。⑤ 写 docs/ART_PARTS.md：Live2D 标准拆件表 23 件 + 官方参数名映射 + 引擎能力清单 + 生产流程 + 下一步顺序。
- 遇到/修了什么：色卡原来只有 16 色，拆出小零件后原画本就有的线稿黑成了主色而被判不过 → 实测后补 3 色而不是放宽阈值；test_core 里写死的 eye_open_left 在拆件后不存在 → 改成自动挑现存 id（eye_l_base → eye_open_left）；沙箱重启清掉了 ~/.imgenv 与 zig，已重建。
- 下一步：① 嘴零件化（口内+上下唇，遮罩裁口内）；② 眉独立；③ 上下眼睑 FFD 取代闭眼贴图；④ G4c 手臂关节补图。顺序见 docs/ART_PARTS.md 第六节。

## 2026-10-12 05:44
- 做了什么：第十四轮（续）：按用户『先做完零件』继续推进头部与头发零件。① 嘴：引擎补分轴缩放（部件 scale 支持 [sx,sy]，通道 sx/sy 相对基准做加法）+ 新波形 flap（0→amp→0，缩放不会摆成负数）；tools/make_mouth_parts.py 按嘴线实测造出开口形状(遮罩, 嘴角比中间晚开)与口内(上颚/口腔/舌/下唇线)——原画没有口腔，这件只能画；make_rig 接 mouth_mask(205, anchor=上唇线中点, scale=[1,0.063]) + mouth_cavity(206, mask)，talk 用 flap 3Hz，happy/surprised/hammered/sleep 各自张法。② 呆毛：tools/make_hair_parts.py 无损切出 hair_ahoge（切线 y=48、根部 12 行渐隐、从 seg_head 抹掉原发丝、登记进 body_parts.json），9 个动作接 bend_x+curve=root 摆动。③ 色卡补 4 个口内设计色（23 色）。④ 单测 237/0，check_assets 167 项全过（含无损切分仍 0 像素差）。⑤ ART_PARTS.md 更新：三类套路（遮罩型/画出来型/无损切出型）、下一步改序。
- 遇到/修了什么：两个坑：嘴部件 anchor=[0.5,0] 时 pos 必须给锚点位置而不是左上角，第一版整体偏了半个嘴宽；make_rig 里用 ch 当循环变量覆盖了画布高度参数。另外实测发现本角色眉毛大半压在刘海下，单独做眉毛收益很低 → 把『前发分层 + 额头补画』提为眉毛的前置(G4j)，下一件改做上下眼睑(G4i)。
- 下一步：① 上下眼睑（遮罩裁眼皮，引擎加 eyelid 标签把眨眼值接到位移）；② 前发/侧发分层 + 额头补画 → 再做眉；③ G4c 手臂关节补图。

## 2026-10-12 06:45
- 做了什么：第十六轮·刘海+额头 AI 重绘（第一件按 D19 做的零件）：①把 seg_head 放大3倍加洋红底交给生图做局部编辑，得到无刘海的脸 logs/asset_qa/head_nobangs.png；②新工具 tools/make_bangs_parts.py：找蓝色虹膜质心→按两眼中点+瞳距解相似变换（scale 0.8555，平移 -18.1/-36.3）→判定被遮额头（原图非肤∧重绘是肤∧眼上沿以上∧剪影内，向脸侧外扩2px吃掉发丝AA边，再补内部窟窿）→只拿补丁四周一圈皮肤做肤色配准（gain 0.80/0.85/0.83 offset 51.3/37.4/39.4）→切出 hair_front.png 169x169(11773px) 并把同一块换成重绘的皮肤+眉毛；③make_rig 接线：bend_x + curve:tip（吊在顶上，和呆毛的 root 相反），9 个动作 0.5~4.0px；④文档：ART_PARTS 新增 5.4 第四套路+流水线顺序警告，REQUIREMENTS 新增 D19/D20，GAPS G4j 标✅并新增 G4k 眉毛
- 遇到/修了什么：①生图不保尺寸也不保构图（912x1166 vs 744x951，脸大17%），必须按虹膜解相似变换再回贴；②第一版肤色配准拿整张脸算，被腮红/下巴阴影带偏，额头发黄→改成只取补丁四周一圈皮肤算 gain+offset；③掩膜不外扩的话刘海一摆，额头留一圈发丝幽灵（抗锯齿边）→向脸侧扩2px并补内部小窟窿；④body_parts.json 的 patches 被追加了三遍→工具改成去重；⑤make_body_parts 会重生成 seg_head 冲掉补画，已在文档写明必须重跑 make_bangs_parts；⑥沙箱又重启，重建 ~/.imgenv 与 ~/.cache/tc/zigenv
- 下一步：眉毛拆件 G4k（额头补全后眉毛已完整，切 brow_l/r + 脸部可见区遮罩，接 ParamBrowLY/Form）→ 眼睑 G4i → 手臂关节 G4c（同样走 AI 重绘：腋下/袖口）

## 2026-10-12 07:07
- 做了什么：第十六轮（续）·眉毛拆件 + 两个老 bug：①再生一张「无眉脸」logs/asset_qa/head_nobrows.png；②新工具 tools/make_brow_parts.py：带旋转的相似变换对齐（残差 1.5px/3 倍坐标）→ 三条判据找眉（比本地皮肤底色暗 + 种子要暖褐 + 横向开运算只留又宽又扁的，再沿暗像素长回完整笔触）→ alpha 抠像 + 解混 C=(src-(1-a)S)/a → 脸上整块换重绘皮肤 → brow_l 53x33 / brow_r 55x14，锚点中心，layer 181/182；③make_rig 接 9 个动作的 dy/rot_deg（ParamBrowLY/RY + Angle）；④层号重排 眉181/182 < 刘海188 < 呆毛190，眉上挑自动滑进刘海底下；⑤色卡补眉色 #784848、#685870（25 色）
- 遇到/修了什么：①**iris_centers 把蓝发梢当成了眼睛**（B-R>70 对发梢也成立，y 差 70px）→ 判据改 R<110 且取成对候选里靠上那一对；刘海那件已按正确虹膜重跑（scale 0.8122，补 9555px）；②AI 重绘两眼差 30px 高度，只缩放不旋转会错十几像素 → 解完整相似变换；③第一版把脸按 alpha 混，留下眉毛鬼影且叠回去偏黑 → 掩膜内整块换皮肤；④只卡暖色会把眉上缘的冷灰描边留在脸上，挑眉变成两条眉 → 种子卡暖色、生长只卡变暗；⑤**发现并修掉老 bug**：surprised 把 sx/sy 摊给眼眶/眼白/眼线这些矩形贴图，一放大就在脸上露出一条横着的方边带（logs/preview_check/old_surprised.png）→ 缩放只发给眼球；⑥pkill -f 会把自己那条命令链一起杀掉，别再用
- 下一步：眼睑 G4i（引擎加 eyelid 标签 + eyelid_travel）→ 手臂关节 G4c（AI 重绘腋下/袖口）→ 侧发/后发

## 2026-10-12 08:21
- 做了什么：眼睑拆件落地（eyelid 标签+行程，眨眼变连续开合）；层序改眉232/233、刘海240；建测试台 web/test.html + tools/api_smoke.py（34 项）；新增 /api/region；修通话姿态被挡
- 遇到/修了什么：修 eye_?_base 没吃遮罩留蓝边；修 call_user/call_reply 被优先级挡住切不到 focus；修冒烟测试自身三处误判（脚点在两腿空隙、短动作读晚了、连击窗口 0.8s）
- 下一步：手臂关节 G4c（AI 重绘腋下/袖口）→ 侧发/后发 → 眼线二次拆件 G4m

## 2026-10-12 09:40
- 做了什么：查"毛边+切割感"：定位到零件切口是二值 alpha（刘海最明显），并抓帧发现眨眼根本没闭严
- 遇到/修了什么：刘海软切口（硬跳变 100%→0%）；眼眶遮罩下延+吃进眼角（27x33→46x41）；闭眼线上移到遮罩内；睫毛改成跟眼皮一起下滑；rebuild_parts.sh 补上眼睑步骤（七步→八步）；抠像维持原样（两版替代方案实测更差）
- 下一步：手臂关节 G4c：AI 重绘腋下/袖口，上臂+前臂+手分件

## 2026-10-12 10:00
- 做了什么：补动画底层第三块：指针跟随（rig 顶层 look 段，/api/gaze 同时驱动眼球+头/上身，1-exp(-speed·dt) 平滑），make_rig.py 写入 head 5°/4px + chest 1.2°/1.5px
- 遇到/修了什么：动作淡入淡出与物理摆动已在 c4f205f 落地；本轮补 test_look 单测（总 264/0），端到端抓帧确认头部质心 ±25px、复位残差 0.1px
- 下一步：G18 命名参数层 + G20 表情叠加，然后回 G4c 手臂拆件

## 2026-10-12 10:12
- 做了什么：命名参数层（G18）：rig.json params[] + 内建 5 参数 + /api/params.json 与 /api/param，zpet/zrig 都接通；测试台滑条按参数表自动生成；make_rig.py 为小寻写入 14 个参数
- 遇到/修了什么：参数层叠加点放在动作与跟随之后、物理之前；apply_chan 抽成公共函数，动作/物理/参数共用同一套通道语义
- 下一步：G20 表情叠加 + G19 LipSync（把 TTS 包络接到 ParamMouthOpenY），然后回 G4c 手臂

## 2026-10-12 10:20
- 做了什么：表情叠加层（G20）：rig.json expressions[]（参数偏移 add/set + fade）、zrig/zpet/HTTP /api/expression、info.json 带表情表、测试台表情按钮；小寻 6 个表情
- 遇到/修了什么：表情只写参数层、不占动作状态机，所以能笑着挥手；加载期校验表情引用的参数必须已声明
- 下一步：G19 LipSync（音频包络→ParamMouthOpenY）或 G21 透け眉，然后回 G4c 手臂拆件

## 2026-10-12 10:56
- 做了什么：透け眉（G21）：眉半透明副本画在刘海之上 + hair_front 遮罩裁切 + 新字段 motion_from 照抄本体通道
- 遇到/修了什么：靠眉形的表情（生气/难过/吃惊）以前完全看不见，现在眉区变化约 1 万像素
- 下一步：G4c 手臂拆件：AI 重绘无手臂躯干 → 回贴被遮像素 → 肩/肘两级关节

## 2026-10-12 13:23
- 做了什么：G4c 手臂拆件落地：AI 重绘无手臂躯干（各向异性四参数配准 sx.470/sy.480/平移5,240，配色误差 12.13）→ 沿袖缝切出上臂/前臂四件（青色 flood + 多段逐行跟随 + 补到轮廓 + 肘部 24px 重叠带只让前臂淡入）→ 躯干挖 40713px/补绘 73px/塗り足し 5 圈渐隐 → rig 加 forearm_l/r 子组与 ParamArmLB/RB，动作 bend_x 按 1°≈6.0px 换算成 rot_deg，挥手改真关节（上臂-52°、前臂-28°±15°@2.2Hz）；check_assets 按真实层级重算并新增「关节不露底(肘)」
- 遇到/修了什么：把三处错判修干净：① 验收合成把预乘 alpha 又乘了一次 alpha（假差 8348px）；② np.roll 做膨胀会绕回画布另一侧（左臂 bbox 撑到满宽）；③ 逐行跟随只认一段，手指缝漏 755px、袖口白条漏 209px；④ 重绘紫边贴进躯干使键色残留 605px（改用 min(R,B)-G>25 判据后为 0）
- 下一步：G19 LipSync（TTS 包络 → ParamMouthOpenY）；立绘侧 G4m 眼线拆件 / 侧发后发；手（G4c2）暂并在前臂

## 2026-10-12 14:03
- 做了什么：修挥手肘关节(大臂-58/前臂-80反向折)、肩头两边各留一份46px、补画区按#5A5A6E描线1412px；check_assets 加「袖下躯干无新窟窿」「切口描线稿」两项(233)
- 遇到/修了什么：纠正验收符号错误：PIL rotate 逆时针 vs 引擎 rot_deg 顺时针，旧25°压力姿势测的是内收(安全)方向；查明 AI 无臂躯干在袖区只有 631px 不透明像素——不是回贴条件丢了，是无袖夹克的边本来就与原袖口重合，故改走留肩头+描线
- 下一步：G4r 闭眼真素材(AI 重绘闭眼脸→配准→切上睑/睫毛)、G4s 张嘴真素材(含口内结构, 双图交叉淡化)

## 2026-10-12 15:12
- 做了什么：G4s 张嘴真素材（AI 重绘张嘴脸→虹膜配准 NCC .925→原分辨率取嘴洞→24x22 含牙18/舌183，motion_from 让口内跟着压扁）；G4r 闭眼真素材（AI 重绘闭眼脸→脸部 NCC .684 配准→软椭圆补片 cover 99.5/99.7、seam 4.5/2.3，eye_open↔eye_closed 交叉淡化）
- 遇到/修了什么：两处配色/配准坑：① 肤色方差太小→最小二乘 gain+offset 病态(解出 gain .15/off 214)把睫毛映射成红杠，改为只解平移且只作用于亮像素；② 用'窗口里的深色像素'定补片框会把眉毛发丝算进去(框 117x68)，改用眼球框外扩
- 下一步：G19 LipSync 接语音；G15 网格顶点形变；侧发/后发拆件

## 2026-10-12 15:30
- 做了什么：审计修 4 处记账/口径错误（GAPS 编号冲突→A系列、证据数字入验收 256 项、ParamMouthOpenY 比例跟 closed_sy 走、rig note 文案）；做完 A4 口型同步（make_lipsync.py + zpet lipsync + zrig_set_mouth_mute + /api/speak + 测试台卡片）
- 遇到/修了什么：test.html 里重复的表情卡片与重复 id；talk flap 与包络叠加会拉伸口内→加嘴通道 mute
- 下一步：A5 网格顶点形变；I/U/E/O 音素级口型素材；侧发/后发拆件

## 2026-10-12 16:18
- 做了什么：加自检与保险体系（selfcheck_repo 42 项 / make asan / 2 万帧长稳 / precommit 钩子 / GitHub CI / make check），ASan 首跑抓出 2 个真内存错并修；做完 A5 网格形变（zimg_draw_mesh 三角仿射 + rig deformers + 呆毛 S 形甩动 + 参数 ParamHairAhogeS）
- 遇到/修了什么：zdeflate 读越界 1 字节（i+best_len 可能等于 n）；测试里手写长度 90 而字面量 89；自检第一次跑就抓到我自己写的重复编号 G28→改 Q1
- 下一步：顶点级遮罩（A5 后半）；I/U/E/O 音素口型；侧发/后发拆件

## 2026-10-12 16:48
- 做了什么：A6 关键帧动作曲线 + G16 多段物理摆链：通道 keys/interp（linear/smooth/step，循环取模，池上限 1024）取代纯波形，示范动作 nod；physics.driver 可串前一条 physics、输出可写 deformer，示范链 head→ahoge_x→ahoge_tip→ahoge_s。验收 test 351/0、selfcheck 44/0、smoke 55/0，证据 logs/asset_qa/a6_nod_keys.jpg
- 遇到/修了什么：（无）
- 下一步：（见 TASKS.md）

## 2026-10-12 17:08
- 做了什么：A7 混合模式（加算/乘算，≈CubismBlendMode）：部件 blend 字段 + zimg blend_px + 遮罩版 composite_masked_blend；程序化腮红/眼高光零件（make_blend_parts.py，12 步重建链）；参数 bind 新增 offset 让「透明度=参数值」；新端点 /api/pause 冻结时钟做确定性抓图。验收 test 363/0、selfcheck 45/0、smoke 59/0、check_assets 284/0
- 遇到/修了什么：（无）
- 下一步：（见 TASKS.md）

## 2026-10-12 17:19
- 做了什么：A8 Pose 互斥部件组（≈pose3.json）：rig poses[] + zrig_pose_set/snap + /api/pose + 测试台差分按钮；示范组 eye_hl_style（圆形/星形/none），星形高光由 make_blend_parts.py 程序化画出。验收 test 384/0、selfcheck 46/0、smoke 64/0。至此 Live2D 对照表只剩顶点级遮罩一项
- 遇到/修了什么：（无）
- 下一步：（见 TASKS.md）

## 2026-10-12 17:30
- 做了什么：A9 遮罩升级：遮罩按需当场渲染（compute_draw_state/draw_state/build_maskbuf 重构），支持多遮罩并集（≤4）、mask_invert 取反、取消图层相邻与层序限制、新增禁止遮罩套娃。验收 test 393/0、asan 0 报错、selfcheck 46/0、smoke 64/0。Live2D 对照表至此全部打勾
- 遇到/修了什么：（无）
- 下一步：（见 TASKS.md）

## 2026-10-13 03:55
- 做了什么：侧发两缕 + 后发拆件（`tools/make_sidehair_parts.py`，D19 AI 重绘型）：重绘「无侧发的脸」→ 虹膜配准 scale 0.7701 → 切出 hair_side_l/r（层 245/246）与 hair_back（层 170，画在脸底下）→ 被挡的脸颊/耳/下颌/脖子用重绘像素回贴 + 外扩补缝；rig 接 ParamHairSide / ParamHairSideS / ParamHairBack、形变器 side_l_s/side_r_s、两段摆链 side_?_x → side_?_tip(deformer) 与慢摆 back_x，18 条动作各配幅度。`rebuild_parts.sh` 12 步→13 步。验收 check_assets **319/0**、静止合成少 0 多 48 像素、make test 393/0、整条重建链从 base.png 跑通
- 遇到/修了什么：① `np.roll` 版 dilate 绕圈把零件撑到整头宽 → 改零填充位移；② 软掩码乘在外缘导致合成丢 19 像素 → 软边只做内缘；③ 重绘比原画宽露出补画边（多 371）→ 补画 alpha 夹回原图；④ 脸掩码闭运算造成发丝鬼影 → 改 fill_holes(largest(...)|虹膜圆∪嘴框)；⑤ 塗り足し先铺后挖会涂到脸外 → 先挖再算区域（多 371→48）；⑥ 从 seg_torso 挖发梢多出 72 个窟窿 → 只换颜色不动 alpha；⑦ **grow_colors 取色源写 α>0，把原画里 α=1~4 的纯绿垃圾像素扩成了 88 个亮绿点**（侧发一摆下巴边闪绿点）→ 取色源卡 α>32
- 交付前复查又抓到两件：⑧ **后发摆动曲线写反**（`root` → 头顶剪影在晃，帧 y63~88；改 `tip` 后摆动落到 y110~137 的发尾，scale 4→5）；⑨ 新加的「头发摆动不露底」闸连着改了三版才有效（总数相减 → 逐像素；整件平移 → 按 bend 曲线剪切；全身都数 → 只数剪影内缩 4px 的深处）
- 验收体系新增三道闸：`check_assets` **322 项**（头发摆动不露底 / 无键色垃圾像素）、`selfcheck_repo` **48 项**（切件工具都进了重建链 / 步骤编号连号）；负例验证：挖空左侧发底下的脸 2310px → 摆动闸 128>20 变红而「无损切分」仍 0。`make check` 全绿（48/393/ASan 0/64）
- 下一步：眼线二次拆件 G4m；之后 G4c2（手腕/裙下大腿）；I/U/E/O 音素口型

## 2026-10-13 05:40
- 做了什么：**眼线二次拆件 G4m（真·眨眼）**。① 新工具 `tools/make_eyeline_parts.py`：把 `seg_head` 上「眼眶开口（软权重 α 24~96 过渡）∪ 上眼线（外扩 1px）」那块**只换 RGB 不动 alpha**，皮肤源 = 已配准的闭眼补片 `eye_?_closed.png` 抹掉闭眼线后的眼窝（左换 1313px / 右 1290px，补画外扩只有 1/3 像素）；顺带剪出 `eye_?_lash_up.png`（只留上眼线那条弧）并逐列实测下滑行程（左 21.5 / 右 17.0）。② 引擎 `zrig.c`：新标签 `eye_aperture` + 字段 `aperture_min`（默认 0.06）→ `part_sy *= 1−blink·(1−aperture_min)`；眨眼淡化从线性交叉改成门控斜坡（睁眼件 `clamp((1−blink)·4)`、闭眼件 `clamp((blink−0.75)·4)`）。③ `make_rig.py`：眼眶挂 `eye_aperture`、**锚点挪到开口下沿并同步改 pos**（`zimg_make_matrix` 把 anchor 点放到 pos 上），上眼线改 `eyelid` + 实测行程、不挂遮罩、改用剪过的图。④ `rebuild_parts.sh` 13→14 步，眼线排在侧发**之后**。验收：`check_assets` **338/0**、`make test` **399/0**、`make check` 全绿、四态复拍 `logs/asset_qa/eye_blink_sheet.jpg`（旧上新下）、不冻结连拍抓到自动眨眼帧 `_autoblink.jpg`
- 遇到/修了什么：① 补丁左上角 x=98 < seg_head 的 x=99，负索引切片直接 `ValueError` → 写了 `blit_slices()` 统一裁；② 抹线只抹暗像素 → 线里嵌的**白色高光**成了颜色外扩的源，整条线被填成**一排白方块** → 线整条带状外扩 3px 一起抹；③ 四邻域外扩填横线只能从左右两头爬，留下**灰褐糊痕** → 改按列上下插值；④ 眼眶卡死 `α>128` → 软边那圈原画留下来，闭眼时**988 粒白点** → 改软权重加权替换；⑤ 行程写"开口高×0.85"**滑过头**（眼白露在眼线上方）→ 逐列实测「眼眶下沿−眼线下沿」中位数；⑥ 眼线片里带着**虹膜左右两道描边**，一下滑就拖成"两行灰眼泪" → `trim_lash_top()` 逐列只留第一段连续的墨；⑦ 单测第一版把眼眶锚点放在整张图底边（空白行上），整只眼被"吸"下去 23px → 锚点改到开口下沿（0.618）
- 验收体系新增两道闸：`check_assets`「脸上无残留睁眼」（负例 553+329 / 580+350 变红）、`test_core` 的 `test_eye_aperture`（负例：注释掉压扁两行 → 1281→1281→1281 三条同时红）
- 下一步：G4c2（手腕/裙下大腿）；I/U/E/O 音素口型（T2.1.3）

## 2026-10-13 22:05
- 做了什么：**G4c2 手腕拆件 + 裙下大腿**。① `make_arm_parts.py` 四件臂 → **六件臂**：腕线在该侧**手臂掩码内**从肘往下扫第一段连续肤色得 `wrist_y=666`（`anchors.json` 比例值 708 落在指尖、整列扫被裙腿干扰得 732，都不能用）；`hand_l` pos[0,649] 83×86 / `hand_r` pos[363,649] 82×86，**层 138/139 画在前臂（142/143）底下**，前臂切到 `wrist_y+1`，手件带 `WRIST_STUB=10` 的皮肤续出并按 `erode(前臂掩码, WRIST_STUB_IN=4)` 往里缩。② **裙下大腿的真根因是"躯干扛着大腿"**——`seg_torso` 原先切到 `legs_top+ov=776`，裙摆下那截大腿是画在躯干上的静止副本；改为 `make_body_parts.py` 逐列扫 `thigh_top`（727~741，两腿间空档列必须按最近正常列回填）、`THIGH_EXT=64`/`THIGH_WIDEN=18` 整条大腿归腿件、躯干按同一条线裁掉 148375px、删掉腿件上缘渐隐（否则大腿根透背景）。③ rig：`ParamHandL/R` ±1→±22°、`ParamLegL/R` ±1→`bend_x ±20px(tip)`，5 个动作接手通道 / 4 个接腿通道，`wave` 改成用手腕甩（pulse −16° + sine 20°@2.2Hz），physics 加 `hand_?_lag`（driver=`forearm_?`，ratio .22/stiff 34/damp 4.4/max 9）= 鞭子第三节。④ `tests/test_core.c` 加 `test_group_chain`（三级组链：只转手 / 转前臂 / 转上臂，位移必须一级比一级大，归零回原位）。验收 `check_assets` **358/0**、`make test` **404/0**、`make check` 全绿（48/404/ASan 0/64），整条 `rebuild_parts.sh` 14 步 193s 跑通
- 遇到/修了什么（**腿的动法被实测推翻一次，闸门被自己推翻三次**）：① **腿绕髋旋转走不通**——髋 704 与裙摆下沿 736 两个 pivot 都在**裆侧裙摆下沿正下方**撕出楔形缺口（±4°=109/61、±15°=252/94 像素，`_thigh_gapmap.jpg`），补画只能长在下沿**之上**、缺口却开在下沿**之下**，填不进去 → 改 **bend(tip)**：顶边钉死，±20px 实测 **0 露底**；负控把曲线写成 `root` 立刻漏 708/763 像素，所以 `check_assets` 里连曲线名都静态卡死。② 加宽补画 `THIGH_WIDEN 7→18` **只救外侧不救裆侧**（外侧有裙比腿宽 30px 的余量可藏），目视会误判成修好了。③ **旧「腕」横带闸是假的**：腕线 y=666 正好穿裙摆，整行横带数到的全是裙和腿，读数 −1404 与髋 band 一字不差 → 改按手自己的 bbox 列窗 `[hx−8,hx+hw+8]`。④ **四向 `hole_mask` 测不出"敞口缝"**：袖口与手之间的缝朝外敞开，`WRIST_STUB=0` 照样读 0 → 改**同列上下夹心 `vhole`**；但列窗套整只手又去数**手指缝**（读 135/153，与袖口无关）→ 行窗压到腕线 `[−18,+14]`。⑤ **压力姿势整臂 25° 会把手转出取样框**（框内空白恒 0）→ 末端关节闸必须**只转这只手**。⑥ 塗り足し贴袖口边补，±20° 时皮肤从袖侧探出一小片**飘肉** → 缩进 4px 并把长度降到 10（10·sin20°≈3.4 < 4）；`_wrist_stub_cmp.jpg` 六宫格目视确认。⑦ 改 `seg_torso` 形状必须在 `make_arm_parts.py` 里用同一条 `thigh_top` 再裁一次，否则它按 bbox 整块贴回。⑧ 手件 anchor 挪到腕点时**必须同步改 pos**（`zimg_make_matrix` 是把 anchor 放到 pos 上）。
- 角度/幅度标定（闸值 60 的物理含义）：腕 `hand_l` 10°:6 / 20°:21 / 30°:38 / 40°:49 / **50°:105** / 60°:139；`hand_r` 10°:6 / 20°:25 / 30°:43 / 40°:55 / **50°:130** / 60°:188 → **安全 ≤40°**，现用 ±22° 留一倍余量。腿 bend：10px 0 / 20px 0 / 30px 28 / 40px 44 → **安全 ≤30px**，现用 ±20px。
- 负控（验收闸门本身）：把前臂切到 `wrist_y−12` 留 12px 裸缝 → 腕闸 34/28 **不红**、但「无损切分」红 1 项（静态缺口归无损切分管、旋转缺口归腕闸管，两闸互补）；`WRIST_STUB=0` → 两闸都不红（重叠 2~3px 时静态无洞、旋转洞也只有 16/13）→ 说明腕闸真正把关的是**角度**而不是塗り足し有没有。
- 证据：`logs/asset_qa/_wave_hand_sheet.jpg`（wave 六帧 2× 腕部特写，袖口不动、手在转）、`_wrist_stub_cmp.jpg`、`_thigh_gapmap.jpg`、`_g4c2_param_sheet.jpg`
- 下一步：I/U/E/O 四音素口型（T2.1.3）

## 2026-10-13 23:30
- 做了什么：**Live2D 协议合规专项（G36）**。用户问"小寻对 Live2D 来说是否合格、尽量往标准走、别等跑完了才发现补救不了"，所以先做审计再动手。① 拉**官方口径**核对（不是凭印象）：`Live2D/CubismWebFramework` 的 `src/cubismdefaultparameterid.ts` = 41 个标准参数 ID + HitArea 前缀；`CubismWebSamples/Resources/Haru` 的 `model3.json`（Groups=EyeBlink/LipSync、HitAreas=Head/Body）、`physics3.json`（Input/Output 都是**参数**，Vertices 摆链带 Mobility/Delay/Acceleration/Radius）、`pose3.json`、`cdi3.json`。② 逐条判定写成 `docs/LIVE2D_CONFORMANCE.md`（含"哪些现在不做以后补不回来"的风险分级）。③ 补协议层：**左右眼拆成 `ParamEyeLOpen` / `ParamEyeROpen`**（引擎 `zpart.eye_side` + `blink_l/blink_r` + 两个内建参数；过去是 L/R 都别名到一个 `ParamEyeOpen`，连挤眼睛都做不到）、`ParamBlush → ParamCheek`（标准名，旧名留别名）、新增 `ParamBodyAngleY / ParamShoulderY / ParamBaseX / ParamBaseY / ParamBrowLX / ParamBrowRX / ParamHairFluffy`（都接真通道，不是占位）。④ 新增 `param_groups`（= model3 的 Groups）并让它**真的管用**：`EyeBlink` 决定自动眨眼眨哪只眼、`LipSync` 决定口型写哪个参数（`zpet.c` 改成 `zrig_lipsync_param()`）。⑤ **动作通道可以 `target:"ParamXxx"`**（≈ motion3 曲线写参数）→ 参数表必须在动作之前加载，顺手把 `load_params` 挪到 `load_actions` 前面。验收：`make test` **422/0**、selfcheck **56/0**、smoke **68/0**、`check_assets` 358/0
- 遇到/修了什么（**自己写的闸门连续两次被自己推翻**）：① 第一版"死参数检测"拿两个**不同时刻**的帧相减 → 待机+呼吸的漂移就有十几像素，把 `ParamShoulderY` 的 binds 删空它照样绿 → 改成**同一时间戳再 tick 一次**（dt=0，等价 `/api/pause`）。② dt=0 下弹簧不走，但物理输出 `pos − target` 会随驱动立刻变，**上一个参数留下的摆动偏移污染了全局基准帧**，后面每个参数都显得活着 → 改成**每个参数临测前现拍一张基准**。③ 跟随类（ParamAngleX/Y）是平滑收敛的，dt=0 根本不动 → 单独用 settle 的办法量、阈值取大。④ 改名之后 `api_smoke.py` 里 `if "ParamBlush" in pids` 不成立，这条检查**静悄悄少掉一项**（64→63）而不是变红 → 改成硬断言 + 补"左右眼各一个参数""闭左眼≠闭右眼"两条。⑤ 沙箱这一轮**两次把 `.git` 回退到分支起点**（HEAD=3b5d17b，文件却是最新的）→ `git fetch` + `git reset --mixed 9d87aa7` 对齐；判断依据是 `git status` 突然多出一堆自己没碰过的文件
- 负控：`ParamShoulderY` binds 清空 → 「标准参数不能是死的」红；`EyeBlink` 组只留左眼 → 「应覆盖左右两只眼」红；把右眼件的 `eye_side` 改成 l → 「右眼不能跟着动（470 像素）」红
- 结论（写进 CONFORMANCE）：标准参数 **✅34 / ⬜5（笑眼·眉形·瞳形，都缺素材、结构已留好）/ ➖4（角色无该部件）**；文件结构除 physics 是"部件级而非参数级"外全部等价，且该差异属于**随时能补**（不动素材）
- 下一步：I/U/E/O 四音素口型（T2.1.3，顺带把 `ParamEyeLSmile/RSmile` 的笑眼素材一起排）

## 2026-10-14 01:10
- 做了什么：**I/U/E/O 四音素口型（T2.1.3 / G37）**，并按用户当轮要求「做测试软件要参考那五个桌宠项目、不会的上网找资料、不要闷头做」**先查证后动手**。
  ① 查五个桌宠项目（沙箱里不克隆 3 GB，改用 `gh api .../git/trees/HEAD?recursive=1` 列目录 + `Accept: application/vnd.github.raw` 取单文件）：**airi** 的 `packages/model-driver-lipsync/src/shared/wlipsync/vowel-driver.ts` 给出完整母音驱动策略（赢家+亚军、`amp=min(vol*0.9,1)^0.7`、静默 160ms 保持、attack 50/s + release 30/s 两档指数平滑）；**ayangweb/BongoCat** 的 `bongocat-live2d-playback` 给出动作求值三类样本与**正弦淡化** `0.5-0.5cos(πt)`（我们现在是线性，记为 🟢 待改）；**vladelaina/BongoCat / VPet / ds-local-pet** 逐仓库扫过文件树，确认它们的说话是**序列帧**不是参数模型，口型这块无参考价值（结论写进 REFERENCE_NOTES，避免下次重复翻）。
  ② 上网核官方口径：Live2D《Standard Parameter List》嘴只有 `ParamMouthOpenY`+`ParamMouthForm`，**没有 ParamMouthA/I/U/E/O**；Animaze 的 viseme 映射表也全落在这两个参数上；日文教程明确「母音認識方式 = 事先做好 OpenY×Form 的组合 keyform」。→ **决定不自造五个参数**，改做一张音素表。
  ③ 引擎：`zrig.c` 加音素层（`load_visemes` / `viseme_update` / `zrig_viseme_set|clear|snap`），表在 rig.json 顶层 `visemes`，缺省内建；平滑张开快收口慢，收干净自动 `mouth_mute=0` 把嘴还给动作；加载顺序排在 params/param_groups 之后。
  ④ 素材侧：`ParamMouthForm` 的 bind 从象征性的 ±0.08/0.06 提到 **lip ±0.22 / mask ±0.26 + mask sy −0.045**；上唇线 `mouth_open` 锚点从左上角挪到中点（`pos` 412→434 同步改）。
  ⑤ 语音侧：`make_lipsync.py` 用 pypinyin 取每字韵母 → 母音，写进包络 `visemes` 轨（38/38 条）；`zpet_lipsync_start_v()` 播放时逐帧 `zrig_viseme_set(音素, 包络值)`；端到端实测「电话接通啦，我在听哦。」→ A A E O A。
  ⑥ 测试软件（test.html/test.js）加口型音素面板：音素按钮 + 强度滑杆 + 「念一串 a-i-u-e-o」；`/api/params.json` 补上 `groups`（model3 的 Groups）与 `visemes`，`/api/viseme?v=&w=` 新端点。
- 遇到/修了什么：① 第一版只改参数不改锚点 —— 上唇线锚点在左上角，`sx` 一缩整条线往右平移（看起来像嘴歪了），改中点并同步改 `pos` 才是两边一起咧开；② 幅度不够等于没做（±8% 在 466px 帧上不到 1px）；③ 冻结时钟（dt=0）下平滑走不动 → 加 `zrig_viseme_snap()`，`/api/viseme` 在 `g_frozen` 时自动调用，和 pose 的处理保持一致；④ pypinyin 是可选依赖，裸环境重跑会**静默**抹掉音素轨 → 生成时打警告 + 自检加「口型包络带母音音素轨」，让它变红而不是悄悄降级。
- 负控：把 `visemes` 里 U 改成和 I 一模一样 → 「最接近的两个音素 I/U 也要差 >25px（实际 0）」+「い 要比 う 宽」双红；把 `ParamMouthForm` 的 binds 清空 → 「标准参数不能是死的」+「い 比 う 宽」双红；复原后 450/0。
- 数字：单测 **450/0**（+28）、selfcheck **64/0**（+8）、smoke **78/0**（+10）、ASan 0、check_assets 358/0。证据图 `logs/asset_qa/_viseme_sheet.jpg`（七张嘴，冻结时钟 + 7× 放大）。
- 下一步：表情与口型的叠加口径（说话时做"笑"表情，两边抢 `ParamMouthForm`）；之后是 `ParamEyeLSmile/RSmile` 的笑眼素材。

## 2026-10-13 表情 × 口型的叠加口径（G38）

- 做了什么：先查官方 SDK 的执行序再动手（`icubismupdater.ts`：EyeBlink 200 / Expression 300 /
  Drag 400 / Breath 500 / Physics 600 / **LipSync 700** / Pose 800）→ 把口型层挪到表情之后；
  表情求值重写成 Cubism 的三累加器 `(base + overwrite + additive) × multiply`
  （照 `cubismexpressionmotion.ts` 与 BongoCat 的 `expression.rs`），顺手补上第三种混合
  **multiply**（原来只有 add / set）；音素层**不再回写基础参数**（删掉 `viseme_write()`），
  改成 `param_effective()` 分层合成；`/api/params.json` 每个参数多报
  `expr`（过表情后）和 `effective`（最终）两列；测试台加「表情 × 口型」看板。
- 效果：「笑着说う」的 `ParamMouthForm` 从被抵消的 −0.30 变成 **−0.86**（仍是撅圆的嘴），
  只笑 +0.70、只说う −1.00。证据图 `logs/asset_qa/_expr_viseme_sheet.jpg`（四张嘴特写）。
- 遇到/修了什么：① 官方的 LipSync 是纯加算，但它的 LipSync 组**只含 `ParamMouthOpenY`**；
  我们连 `ParamMouthForm` 一起驱动，加算必然抵消 → 改成"音素落位 + 给表情留 (1−w) 余味"，
  这是有意偏差，已登记进合规表；② 发现一个**自己埋的"跳过即通过"**：
  `load_visemes()` 里写着 `if (vis_mix <= 0) vis_mix = 0.8`，于是把权重设 0 的负控永远红不了
  —— 改成只夹范围不替换 0；③ 冻结时钟（`/api/pause`）下表情淡入走不动，smoke 里刚设上的表情
  等于没设 → 补 `zrig_expression_snap()`，`/api/expression` 在 `g_frozen` 时自动调用
  （和 `zrig_viseme_snap` 同一个理由）；④ 音素层改成分层后，`zrig_param_get` 不再跟着动，
  老断言要改读 `zrig_param_effective`，同时新增一条"音素不许回写基础参数值"。
- 负控（三次，都确认判红）：`viseme_weight=0` → 「笑着说う」红；`viseme_weight=1.0` →
  「表情余味」红；把 `EXPR_MUL` 退化成加算 → 乘算两条红。复原后全绿。
- 数字：单测 **466/0**（+16）、selfcheck **73/0**（+9）、smoke **86/0**（+8）、check_assets 358/0。
- 下一步：笑眼素材 `ParamEyeLSmile` / `ParamEyeRSmile`（补齐合规表的 ⬜5）。

## 2026-10-13（第 N+1 段）用户验收反馈：一直闭眼 + 张嘴了微笑还在（G39）

- 用户在测试台上提了两件事：「小寻一直闭着眼」「张嘴时微笑衔接过慢，张嘴了微笑还在，看着怪」。
  先复现、再定位，最后一共挖出**四个真 bug**（两个属"闭眼"，两个属"嘴"）。
- **① 醒了还闭眼**：`zpet_tick()` 的唤醒分支只清 `sleeping`，没解除睡着时下的强制闭眼；
  更深一层是 `zrig_blink_force(zrig*, int)` 写成了 bool（`on ? 1 : 0`），而字段 `blink_forced`
  是三态（−1 自动 / 0 不闭 / 1 闭），调用方按字段语义传 `-1` 反被当成"闭眼"。
  → setter 改三态，新增唯一唤醒入口 `pet_wake()`（`sleeping=0` + 解除强制 + 恢复自动眨眼），
  `/api/blink` 补 `on=0|1`、缺参数改 400。
- **② 关掉自动眨眼就全闭眼**（抓证据图时撞见）：绘制判断写成
  `if (blink_enabled && blink > 0.001) { 睁眼件淡出；闭眼件淡入 }` —— 关掉自动眨眼后，
  表情里的 `ParamEyeOpen=0.85`（本该只是微微眯）会跳过淡化，闭眼件以 100% 不透明盖住睁眼件。
  查官方 `CubismEyeBlink`：它只 `setParameterValueById`，绘制永远只看参数值，没有 enabled 这回事。
  → 判据只看闭合度。
- **③ 张嘴了微笑还在**：口型接管权重是恒定的 `vis_mix`，于是笑着说一整句时
  `ParamMouthForm` 全程被按在 0.14（停顿时回不到笑、张大嘴时笑嘴角也不让位）。
  → `w = viseme_weight × viseme_activity`，`viseme_activity` = 本帧口型相对默认值用了多大力（0..1）；
  `viseme_weight` 0.8 → 1.0（0.8 是官方给"只驱动开合"定的，我们还驱动嘴形）。
- **④ 说完话嘴角抽一下**（新判据抓出来的）：`zrig_viseme_clear()` 是硬切。
  → 改平滑松口（只把 `vis_weight` 归零，形状一路收回默认，收干净了才释放），
  新增 `zrig_viseme_reset()` 给"换角色/取测试基准"这种要立刻清零的场合；
  再加第二档 release `ZRIG_VIS_RELEASE_OFF = 8.0`（整句松口比音素间的 30/s 慢一档，
  12.0 试过仍有 0.122 的单帧跳变，8.0 才降到 0.12 以下）。
- 实机曲线（笑着说 `call_end_1_base0`，150ms 采样，Form）：
  0.70 → 0.36 → 0.91 → 0.15 → 0.53 → 0.64 → 0.70，约 1.8s 平滑叹回；
  修之前是全程 0.14、到 t=2.00 一帧跳回 0.70。
- 负控四次全部判红后还原：`w` 退回恒定 → 2 项红；`clear` 退回硬切 → 1 项红（跳变 0.700）；
  `force(-1)` 退回 bool → 红；绘制判断加回 `blink_enabled` → 红（整帧差 2825 像素）。
- 数字：单测 **484/0**（+18）、smoke **95/0**（+9）、selfcheck **83/0**（+6）。
  证据图 `logs/asset_qa/_expr_viseme_sheet.jpg` 重拍（嘴部框改成"A vs 闭嘴"差分自动框，
  写死坐标在角色位移后会拍出四张白图）。
- 下一步：笑眼素材 `ParamEyeLSmile` / `ParamEyeRSmile`（补齐合规表的 ⬜5）。

## 2026-10-13（第 N+2 段）笑眼 ParamEyeLSmile / ParamEyeRSmile（G40）

- 先查后做（用户硬要求）：把官方 Haru 的八个 `exp3.json` 全拉下来，**F05 就是笑眼表情**，
  写的是 `ParamEyeLOpen=0 (Multiply)` + `ParamEyeLSmile=1 (Add)` + 眉毛 `0.32`；
  再搜四篇独立的日文建模教程，口径完全一致：**笑眼是"闭着的眼"的另一种形状**，
  做的时候要先把开闭参数打到 0，再把谷型 ∪ 弯成山型 ∩。VPet 那种逐帧 PNG 序列不可抄；
  airi 的 `eye-motions.ts` 其实是扫视间隔分布（留给以后做视线微动）。
- 素材：AI 重绘 `design/redraw/face_eyesmile.png`（同一张脸只改眼睛），然后把
  `make_eye_closed_parts.py` 参数化成 `--variant closed|smile` —— 配准、切补片、肤色平移、
  羽化、覆盖率自检全部复用，只换底图。切出来和闭眼件**同位同尺寸**，覆盖 99.5%/99.7%。
- 引擎：`eye_smile` 标签 + `ParamEyeLSmile/RSmile` 两个内建参数（0..1 默认 0）。三条规矩：
  ① 笑眼隐含闭眼 `blink = max(blink, smile)`；② 谷型闭眼件按 `1−smile` 让位；
  ③ 笑眼件走和闭眼件一样的"最后 25% 淡入"。新增表情 `happy`。
- **踩坑（值得记）：在真 rig 上用像素闸根本测不出"笑眼件到底画没画"。**
  第一版三条负控全部没红：(a) 去掉"笑眼隐含闭眼" → 笑眼补片本来就盖住整只眼，画面一模一样；
  (b) 让笑眼件永不显形 → 眼线件下滑后也在同一位置留一条线，暗像素数几乎不变（131 vs 135）；
  (c) 让闭眼件不让位 → 两条线叠着，像素差异仍然"够大"。
  改法：① 加两个只读查询 `zrig_eye_close/zrig_eye_smile`，把"隐含闭眼"这条用数值断言；
  ② 另起一个**合成 rig**，把睁眼/谷型/山型三张真素材摆在互不重叠的位置，逐块数不透明像素。
  改完三条负控分别判红 2 / 1 / 1 项。
- 数字：单测 **504/0**（+11）、smoke **101/0**（+6）、selfcheck **90/0**（+7）、check_assets **372/0**（+14）。
  合规表 ✅34 → **✅36 / ⬜3 / ➖4**（只剩瞳形 `ParamEyeBallForm` 和眉形 `ParamBrowL/RForm`）。
  `rebuild_parts.sh` 14 步 → 15 步。证据图 `logs/asset_qa/_eye_smile_sheet.jpg`。
- 下一步：18 个动作从部件通道迁到参数通道（合规表里最后一个结构性偏差），
  然后动作 fade 线性 → 正弦。

## 2026-10-13（第 N+3 段）动作通道迁到参数（G41）

- 先查后做：`gh api` 拉 `CubismWebFramework/src/motion/cubismmotion.ts`，第 38~40 行三个常量
  写死了 `.motion3` 曲线的目标只有 `Model` / `Parameter` / `PartOpacity`；再拉官方 Haru 的
  `haru_g_m01.motion3.json` 实测：Parameter 42 条 + PartOpacity 20 条 + Model 1 条，
  参数名几乎和我们的一一对应。**没有"直接写部件位移/旋转/缩放"这种通道。**
- 迁法：不重写动作（那 197 条的像素/角度是美术调出来的），而是按参数的 bind 系数反算
  `参数振幅 = 几何振幅 ÷ scale`。换算表放 `make_rig.py` 的 `GEO2PARAM`，**漏登记就报错** ——
  它同时是换算器和守门人。结果 197 → 160 条，全是 `{"target":"ParamXxx"}`。
- 顺带清掉：左右对称通道合一；24 条"整只眼在脸上平移"的逐件通道直接删（眼部件都在 head 组里，
  组位移本来就带着走；而且那是手写清单，上一段新加的笑眼件压根不在里面 —— 这就是逐件写的代价）。
- 顺带补：`bias` 直流偏置（官方 CubismBreath 的 offset，让 0..1 的 ParamBreath 能用正弦驱动）、
  标准参数 `ParamEyeBallForm`（瞳孔缩放，合规表 ✅36 → ✅37）、扩展参数 `ParamBaseRot`（全身倾斜）。
- **踩坑一（最耗时）：回归比对的采样程序一次性把时钟跳 2 秒，结果测了半天的都是"动作还没动"的帧。**
  原因：动作切换的淡入权重是在 `zrig_tick` 内部发现"动作变了"那一刻才起算的（`fade_t0 = 本次 tick 的 now`），
  一次跳 2 秒 → 第一帧 u=0 → 权重 0。改成 1/60 逐帧推进后，挥手才真的把手举起来。
  改之前我甚至以为"wave 动作坏了"。
- **踩坑二：新加的 bind 连带会打穿既有断言。** 给 `ParamBodyAngleX` 加了胸组的 `dx 0.1` 之后，
  "五官要刚性跟住身体形变"那条红了（偏差正好 1.0px = 胸组平移量）。
  结论：参数的主力 bind 和点缀 bind 不能乱加 —— `bend_x` 已经表达了"上身左右"，再叠一层平移就是重复。
- **踩坑三：胸组的 `sy` 缩放是放大器。** `ParamBodyAngleY` 原来绑 `chest.sy -0.004`，动作用到满格时
  上身被拉伸 4%，770px 高的上身顶端跑掉 30px。降到 -0.001。
- 数字：单测 **523/0**（+19）、smoke **107/0**（+6）、selfcheck **97/0**（+7）、check_assets 372/0。
  回归：18 动作 × 7 时刻，质心位移最大 5.3px（breath 的呼吸起伏），横向最大 5.0px
  （stroke/focus 的 `head.dx → ParamAngleX` 连带头部旋转，Live2D 语义，更自然），其余 ≤2.2px。
- 下一步：动作 fade 线性 → 正弦 `0.5−0.5cos(πt)`。


## 2026-10-13（第 N+4 段）动作淡化对齐官方：getEasingSine + 每动作 FadeOutTime（G42）

**先查后做**（用户硬要求）：这件的权威不在那五个桌宠，而在 Live2D 官方运行时。
`gh api` 取 `CubismWebFramework/src/math/cubismmath.ts` → `getEasingSine(v) = 0.5 − 0.5cos(vπ)`，
两端钳 0/1；`cubismmotion.ts:417-430` 用它分别算 `tmpFadeIn` / `tmpFadeOut`，
`endTime < 0`（循环）时 `tmpFadeOut` 恒 1，最后 `weight × fin × fout`。
第四批记过 BongoCat `motion/weight.rs` 也是 `0.5−0.5cos(π·progress)` —— 现在知道**它抄的是官方**。

**改了三处**：① `z_ease_sine()` 进 `zc.c`，`compute_group_transforms` 的淡入换掉 smoothstep；
② 动作加 `fade_out` 字段（默认 0.2s），非循环动作结束前整段按官方公式收，循环动作不收；
③ 拆掉 `W_PULSE` 里硬写的"结束前 0.15 秒回零"——那是只给一种波形开的后门。

**抓到一个真 bug（本段最大收获）**：改完跑逐帧回归，发现 `surprised` 在 t=0.90
（动作刚演完）`ParamArmLA` 从 0 跳到 **2.667** 并持续约 0.2 秒。原因是淡出只加在"当前动作"上，
漏了 `prev` 分支——动作演完的那一刻它变成"正在淡出的旧动作"，走的是另一条累加路径。
官方的 FadeOutTime 是挂在 motion 自己身上的，两条路径都得乘。补上后，
`wave` 原有的 0.262 尾部偏差也跟着消失（同一个病）。
**先把这条写成单测看它判红（鬼影 2.629），再修**，不是修完补测。

**闸门**：单测 535/0、smoke 109/0、selfcheck 104/0、check_assets 372/0。
负控四道：动作级淡出不生效 / ease_sine 实现退回 smoothstep / 循环动作也淡出（连带打穿 4 项既有断言）/
静态闸把调用点换回 smoothstep —— 全部判红后还原。

**顺带回答了用户的问题**（"除了这五个桌宠还需要什么类型的参考项目"）：
九个候选全部 `gh api` 验证可达，写进 `docs/REFERENCE_NOTES.md` 第七批第 3 节并排了优先级，
头两个是 `Inochi2D/inochi2d`（开源的 Live2D 等价引擎，和我们在做的事最同构）和
`guansss/pixi-live2d-display`（motion queue / 优先级抢占的完整实现）。

## 2026-10-13（第 N+5 段）裙摆摆链 + 两个渲染 bug（G43 / G43b）

**先查后做**：原计划叫"裙摆接多段摆链"，查完官方发现**方向就不对**。
翻了 8 个官方示例模型的 `physics3`：Haru 只有三组头发 + 一条围巾，根本没给裙子做物理；
**Hiyori 有**「スカート　横揺れ」+「スカート　縦揺れ」——裙子不是串成多段，
而是**横摆、纵摆两条独立通道**，输入只吃 `ParamBodyAngleX/Y/Z`、一个头部参数都不吃，
纵摆比横摆钝。Mao 的ローブ（长袍）也是 X/Y 分两组，可见是布料的通用写法。
照这个把计划改了。

**裙子没拆件**。形变器本来就是挂在部件上的网格，能只动其中几行：
`seg_torso` 273×501、裙子占下 42%，`cols=2,rows=10` 的网格里 r=0~5 一个点都不动，
r=6 正好压在裙腰上当"根"。裙摆荡开露出来的是早就拆好重绘过的大腿。

**为此补了 physics 参数输入**（≈ 官方的 `Input` 数组）。原来摆链只能读"驱动组移动了
多少像素"，而 `ParamBodyAngleX` 绑的是 `seg_torso.bend_x` —— 弯曲是非仿射的、
不进组矩阵，组驱动根本读不到。这项同时把合规表的「physics 参数级 I/O」做掉一半
（输出参数化留作 G44）。

**撞出两个一直存在的渲染 bug（本段最大收获）**：
① `draw_state` 里网格形变器和 bend 是 `if/else` **互斥**，部件一挂形变器 bend 就被整个丢掉——
**G16 的多段摆链正是"第一段写 bend、第二段写形变器"，所以第一段一直白写**；
② 找形变器的循环 `break` 掉了，同部件第二张网格起静默失效（裙摆要横纵两张，不改只有一张生效）。
按 Live2D 变形器嵌套语义改成叠加。实测同一个 rig、旧引擎 vs 新引擎，
head_pat/nod/sway 每帧差 7926~10540 像素——**这是以前一直丢掉的头发摆动**。

**负控四道全判红**，其中有一道第一次没红：测"第二张网格没被丢"时我只比了
`A+B ≠ 只有B`，而掉了 B 的实现会退化成"只有 A"，照样不等于 B。改成三个值互比才抓住。
**判据写松 = 负控不红，又犯一次。**

**顺带**：`/api/info.json` 加了 `deformers` 字段（摆链实时输出）。
加它是因为 smoke 里"验证裙摆收敛"用整帧 hash 做不到——idle 一直在跑，
画面永远不会完全静止。有了数值就能精确断言（实测 0.043 → 0.0000）。

**闸门**：单测 553/0、smoke 112/0、selfcheck 112/0、check_assets 372/0。

**中途沙箱又重置了一次**：HEAD 退回会话基线 `3b5d17b`，工作区文件却是最新的。
`git reset --mixed 3afc90f` 对回去，工作区一个字没丢。
识别特征是 `git status` 里冒出一堆**自己这轮根本没碰过**的文件。

## 2026-10-13（第 N+6 段）眉形 ParamBrowL/RForm：合规表最后两个 ⬜ 清掉（G45）

**先核对，发现排期条目是错的**：清单上写着"下一件 = G19 LipSync 接 TTS 包络"，
查库发现 **LipSync 2026-10-12 就做完了**（记作 A4）——`tools/make_lipsync.py` 出
30fps 包络 + 音素序列，39 条台词在库，`viseme_source: pinyin_finals`。
GAPS 里 `G19` 这个号被用了两次（另一个是"通知中心"），已在表里标注撞号。
真正剩下的最后两个 ⬜ 是**眉形**。

**原以为要画新素材，其实不用**。合规表自己写的是"要么新素材、要么给眉毛铺 FFD 网格"，
而眉毛就是一条横着的细带，`cols=4/rows=2` 的网格足够表达「山なり ↔ しかめ」。

**查官方**：`Haru.cdi3.json` 确认显示名是「左眉　変形」；Haru 的 8 个 exp3 里
**六个在用眉形**，都是和上下/角度叠着用。±1 的方向社区教程**互相矛盾**，
以官方 Cubism 手册为准：−1 = しかめ（皱起）、+1 = 山なり（隆起）。
最有价值的一条是官方反复强调的 **「変形」不许带位置移动**——
眉毛四个自由度正交分解（上下/左右/角度/形状），Form 带净位移就会和前三个打架。

**这条约束落成了可核的数值闸**，而且**放在 selfcheck 而不是单测里**：
它是配置层的事（看得到每个控制点），判据是"中段与两端反号 + |Σdy|/Σ|dy| < 0.25"，
现值 0.172。单测那边只管运行时：参数在、改画面、**变化全部落在 y200~260 这条眉毛带内**。

**透け眉自动跟上了**：一度怀疑 ghost 没跟随（所有眉参数的 binds 里确实只有本体），
查下去发现 ghost 走的是 `motion_from`，而形变器查找本来就同时认 `mi` 和 `pi`
（`cand->part != mi && cand->part != pi`）——所以刘海上那层也跟着变形。**虚惊一场，但值得记**：
看 binds 表下结论太早了，得把 motion_from 这条路也算上。

**幅度受美术结构限制**：刘海盖住大半条眉毛，额头只透出 42% 不透明度的 ghost，
±1 的全画面差异只有 270 像素。这是设定使然，不是没生效——单测能证明变化确实发生且只在眉毛带内。

**闸门**：单测 564/0、selfcheck 118/0。三道负控全判红（网格改成整体平移 /
表情不接眉形 / 形变器 bind 不写 amount，最后这道连带打穿 5 项）。

**合规表 ✅37 → ✅39 / ⬜0 / ➖4** —— 41 项里凡是这个角色适用的，全部实现且有闸门。

**又踩了一次"测像素前要冻结时钟"**：第一版扫描用 `tick(100.0+k)`，每帧推进 1 秒，
idle 和 physics 全在动，差异糊成全身 54643 像素。改成同一时刻 + 两次预热 tick 后，
差异干净地落回眉毛那 270 像素。**这个坑今年已经踩第三次了。**

## 2026-10-13（第 N+7 段）主工作区骨架 G1：界面改成配置装配

**又先核对了一遍排期**：清单上的"下一件 = G15 网格顶点级编辑"同样是过时条目——
**A5（原记作 G15）2026-10-12 就完成了**。加上上一段发现的 G19，连着两条"下一件"都是
陈年笔误。动画底层的风险分级表里 🔴/🟠 已全部清空，只剩 🟢 纯增量，
所以按用户主线（"基础软件 UI + 可做动作的动态立绘"）转向 UI。

**先查 VPet**（F15 硬要求）。`MainPlugin.cs` 的插件基类短到可以全文读完：
一个 `PluginName`、一个宿主引用 `IMainWindow MW`、六个固定生命周期钩子。
`IMainWindow` 是个**大门面**，把设置/数据核心/所有聊天 API/**所有三方插件**/资源
全暴露给插件。三条直接照搬：组件只认门面、生命周期固定、插件之间能互相发现。

**重构**：`index.html` 瘦成四个区域容器，`app.js` 从 380 行业务变成 ~230 行内核
（注册表 / 动态加载 / 事件总线 / 主题 / 统一轮询），九个组件各自一个文件。
**业务逻辑是原样搬过去的，没有重写** —— 没有浏览器可验证的情况下，重写等于赌博。

**没有浏览器怎么保证没搞坏？** 写了 `tests/test_web.js`：一个 ~90 行的 DOM stub，
把内核和九个组件在 node 里真的跑一遍。连"script 插进 head 就执行"都模拟了，
所以"按 layout 动态加载组件"这条路是真的走过的。39 项断言覆盖：
装配结果、挂载区域、**挂载顺序**、推 info 后各组件的更新、点按钮发出的请求 URL、
**立绘点击坐标的换算**（显示 100×300 → 帧 445×1292，点 (50,150) 应得 (222,646)）、
主题变量真的写进 `:root`、以及布局写错时**就地报错而不是整页白屏**。

**验收实测**：把 `side` 倒序、`usage` 挪到顶栏、删掉 `voice`，一行代码没动，
"顺序一致/区域正确/挂载成功"三条断言照样全过。

**CSS 的坑**：组件化多出了"区域容器"和"插槽"两层 DOM，会把原来的 grid/flex 父子关系打断。
用 `display: contents` 让这两层对布局**完全透明**，一条规则解决，既有排版一个字没改。

**负控**：删掉 `components/moods.js` → selfcheck 判红 + web-test 判红。
第一次跑负控时 web-test 是**崩溃**（TypeError）而不是判红，加了个 `slotOf()`
兜底才变成干净的失败项 —— 测试自己也得扛得住被测对象缺失。

**中途沙箱第三次重置**（HEAD 退回 `3b5d17b`，`build/` 和 `~/.imgenv` 全没了），
`git reset --mixed ddfedba` 对回去，工作区一个字没丢。

## 2026-10-13（第 N+8 段）全能桌宠平台：框架计划 + G50 契约与注册表

用户提出了平台级愿景（API 连接 / token 余额 / 聊天 / 任务 / 三个资源区 / 代理 /
skills / 生图生视频生代码生建模 / 本地与网络 AI / 陪伴 / neuro-sama 模仿项目 /
"真正的思考载入"），并且明确**"这个是计划先把框架做好才行"**。

**先查**（F15 硬要求）。用户点名的"neurosama 的模仿开源项目"查到了，
而且**我们已经在参考的 `moeru-ai/airi` 就是**（★50347，README 第一句就是
"Re-creating Neuro-sama"）。另外找到 `heshengtao/super-agent-party`
（自称 "Self hosted neuro sama"，功能面和用户要求几乎一一对应）、
`elizaOS/eliza`（"agentic operating system"）、`KroMiose/nekro-agent`
（沙盒执行 + 工作区编排 + 长期记忆）。六个仓库全部 `gh api` 实测可达。

**最有价值的一条发现：skills 不用自造格式。** super-agent-party 的 `skills/` 用的
就是 Agent Skills 规范（`SKILL.md` + YAML frontmatter + `assets/` + `references/`），
连"造技能的技能"都有。采标准 = 整个生态的技能包能直接放进来用。

**计划成文**：`docs/PLATFORM_PLAN.md` —— 七层分层、四份契约、三个资源区、
里程碑 P0~P3、范围边界。最关键的是第零节那条总原则：
**"2027 年以内 AI 能做到的所有事"是列不完的，所以框架不能去列它** ——
能力必须是注册出来的，加一种新能力不改内核。

**入库**：REQUIREMENTS 新增 A9~A21（用户原话逐条）、GAPS 新增 G50~G63、TASKS 新增 T20 系列。

**动手第一块 G50**：
- 15 份能力契约 `config/capabilities/*.json`（用户点名的生图/生视频/生代码/生建模全在内）
- 6 份供应商契约 `config/providers/*.json`：openai / deepseek / relay_test（网络）
  + ollama / comfyui / mcp_filesystem（本机）
- `config/gateway.json`：代理出口、路由策略、记账账本
- `tools/check_platform.py`：校验 + 生成 `web/platform.json`
- 新组件 `components/platform.js`：界面上能看见能力 × 供应商矩阵

**顺手清掉一处概念打架**：`config/providers.json`（旧的扁平清单，只有 base_url 和
model，没有能力声明/定价/余额）和新契约目录会并存成两套。查了一遍**没有任何代码在读它**
（只有文档提到），于是把三条供应商迁进新契约后删掉旧文件。

**负控四道全判红**：供应商声明不存在的能力 / 契约里写明文密钥 /
本地供应商却声明 api 余额 / 能力 id 与文件名不一致。
另外还有一道"改了契约但忘了重新生成清单" —— selfcheck 也判红。

**★ 上面那句"没有任何代码在读它"是错的，`make -s check` 当场打脸。**
`tests/test_core.c:400` 判红：`供应商 3 个` 变成 0 个。真相是 `src/core/zconfig.c`
里写的是 `load_one_json(c, "providers.json", ...)` —— **路径是拼出来的**，
grep 全路径或 `config/providers.json` 永远命中不了。

**没有选"恢复旧文件"（那就退回两套并存），也没有选"改 C 代码读新目录"（动运行时有风险）。**
走第三条路：**旧文件从此是生成物** —— `tools/check_platform.py` 从新契约投影出
老格式的 `config/providers.json`，C 侧一行不改，而真相只有一份。
投影时 `kind` 要映射：C 只认 `openai_compatible/official/local`，
新契约的 `comfyui`/`mcp` 投成 `local`，原值留在 `kind_ext`（C 忽略未知字段）。

**顺带堵上一个更阴的洞**：原先 `--check` 的语义是"跳过生成"，
于是"改了契约但忘记重算投影"能一路绿灯过闸。改成**算出应有内容、与磁盘比对、
不一致判红**。两道新负控都红了：改契约不重算 / 手改生成物。
platform 从 11 项涨到 **13 项**。

**闸门**：platform **13/0**、selfcheck 128/0、web-test 44/0、smoke 119/0、**test 564/0**。

---

## 第 N+9 段（2026-10-13）：G51 网关骨架

**先查后做**（用户硬要求）：`gh api` 翻 one-api 的 `model/ability.go`、`relay/adaptor/interface.go`、
`relay/billing/billing.go`、`controller/channel-billing.go`，再看 airi 的 provider 协议。
结论写进 REFERENCE_NOTES 第十二批。**查出来的东西当场改了两处设计**：

1. **路由表改成预计算的**。本来打算运行时遍历 `config/providers/` 挑供应商，
   看到 one-api 的 `Ability` 表才意识到那是每次请求都做一遍的活儿。
   改成 `tools/check_platform.py` 物化出 `config/gateway_routes.json`，**顺序即优先级**。
2. **余额契约推倒重来**。G50 里写的是 `balance: {mode, path}`，
   查 `channel-billing.go` 才发现四家四种算法（DeepSeek 直接给、OpenRouter 和
   credit_grants 要减、OpenAI 订阅式要查两个端点）。改成 `{mode, endpoint, pick, minus?}`。
   要是没查就写完了，等接第二家的时候才会发现表达不了。

**做出来的东西**：`src/core/zgateway.{c,h}`，四件事都是纯决策、不碰网络——
路由（三种失败原因分开报）、估价（按量/按次/免费）、三段记账、密钥引用。
真实 HTTP 调用**故意不在这件里**（G54 才做）：把"选谁/花多少/钥匙在哪"和"怎么发"切开，
前者在一台没网、没密钥的机器上就能完整验证，这也是它能有 63 项单测的原因。

新端点 `/api/gateway.json` 报告"每种能力现在实际会走谁"，三态 `ready/disabled/missing`
——**三态是故意分开的**：全关着要说"去设置里打开"，没接入要说"还没接"，
统一说"不可用"的话用户不知道该干什么。平台面板把它和契约并排显示。

**负控十一道全判红**：路由不看 enabled / 结算记预扣额 / 密钥失败返回空串 /
退还也扣钱 / 重复结算不拒 / 三态混成"不可用" / 账本不显示花费 /
删 enabled 检查（源码闸）/ 把它注释掉（源码闸不能被注释骗）/
密钥失败路径 return 0（源码闸）/ 路由表顺序打乱（生成端）。

**自己写的闸自己先踩了一个**：selfcheck 的剥注释函数不认字符串字面量，
`zgateway.c` 里的 `"secret://"` 当中那个 `//` 被当成行注释，把后面半行吃掉，
于是两条好端端的闸判红。修法是遇到 `"` 就整段保留（含转义）。

**闸门**：test **627/0**（+63）、smoke **138/0**（+19）、selfcheck **136/0**（+8）、
web-test **52/0**（+6）、platform 14/0。

## 第 N+10 段 · 语音整体换血（2026-10-14）

用户要求去掉本地音源、换云端标准音色，并点名少女/萝莉/青年女性、二次元、要有情绪、
用户可调、**每个 AI 声音不同且不同源**。

**先查后做**（用户硬要求）：查了 edge-tts README、Azure Voice Gallery / SSML 文档 /
HD 音色公告、MiniMax 音色表、火山与 Fish 的定价与协议，共 8 处来源，落在
REFERENCE_NOTES 第十三批。最关键的一条是 **edge-tts 做不了情绪**（官方移除 custom SSML），
这直接决定了不能把它当主力，也决定了情绪必须抽象成四种 mode 由网关翻译。

**删**：`voices/` 全套 + 三个本地脚本，9 个文件。删前 grep 过闸门和 C 源码确认无引用。

**建**：19 份音色契约 + 分配表 + 情绪映射表 + 三家供应商契约 + 一个面板。
沿用 providers 那套"契约是真相、老文件降级成生成物"的手法，
`config/voices.json` 是第四个这样处理的文件 —— C 侧 `zconfig.c:311` 不用改一行。

**闸门**：check_platform 14→31 项（含用户两条硬要求各一项）、selfcheck 136→144、
test_web 52→65、test_core 627（供应商数 6→9 同步改）。
共做了 8 道负控：AI 共用嗓子 / 同源 / 界面粉饰"无情绪" / 清单字段名写错 /
本地声源删一半 / 手改生成物 / 情绪映射漏通路 —— 全部判红，还原后全绿。

**没做完**：渲染器还只会 edge-tts；面板选的音色存不住；mood→情绪还没接运行时。
这三项记在 G64 尾部。

## 第 N+11 段 · 回答"立绘做完了吗"并补齐测试软件（2026-10-14）

用户问 live2 动态立绘做完没有，要求没做完先别做别的，测试软件先兼容立绘功能。

**查下来**：底层确实做完了（合规表 41 项 ✅39/➖4，🔴🟠 风险全清）。
**但测试软件只用到 24 个端点里的 9 个** —— 46 个参数、7 表情、7 口型、差分、视线、
眨眼、暂停全都没有界面入口。这就是用户说的"兼容"缺口。

补了 `web/components/rig.js` 立绘调试台，并给 `/api/info.json` 加了 visemes 字段
（口型表不再前端硬编码）。

**过程中抓到的真问题**：前端参数名靠猜，`viseme` 和 `pause` 两个端点都写错，
而且都静默返回 ok。其中 pause 写错导致我在冻结的服务上测了半小时，
差点误判 ParamAngleX 坏了。已落成 selfcheck 的跨语言参数名闸（三道负控）。

**实测回归**：冻结时钟噪声 0 的条件下，23 项 bind 类能力全部驱动得动；
走时钟的 6 项（look + 动作）也全部驱动得动。46 个参数逐个设值回读全部到位。
唯一不达标的是脸红（满值仅 27 像素变化，素材太淡），记 G66。

闸：selfcheck 144→146、web-test 65→92、api_smoke 139→147、test_core 627 不变。

---

## 第 N+12 段 · 把脸红挪回脸上，把交互三件套接进界面（2026-10-14）

接着上一段的遗留 G66 往下做，顺带把 UI 端点覆盖率的缺口收掉。

**G66 脸红**。素材不是抠图，是 `make_blend_parts.py` 程序化画的软边椭圆。
先按"太淡"去治，把 peak 0.62→0.88、颜色加重，平均 alpha 43→63，
可见变化只从 27 升到 41 像素 —— **和按 alpha 估的 ~400 差十倍**，倍数对不上才去查落点。
把像素差阈值降到 4，读出最大变化点在底图上的 alpha 只有 10：腮红画在脸轮廓外了。
`seg_head` 在画布 y=300 的实心范围只有 x 345..491（脸是锥形，越往下越窄），
而腮红摆在 `[311,300]` 64×34 —— 92% 在空气上，而 multiply 乘不动透明像素。
按瞳孔位置重新定位（40×22，压在实心脸上），满值 **27 → 268 像素**，色差 **34 → 167**。

**G67 交互三件套**。24 个端点里还剩 `hover`/`region`/`speak` 没有界面入口，
而这三个正是"桌宠"和"立绘播放器"的区别。新增 `web/components/interact.js`，
并给 `info.json` 补上 `regions`（id/action/cursor/rect）和 `canvas_w/canvas_h`，
免得前端把区域名和画布尺寸写死。

查区域时发现**摸头区域漏了下半张脸**：rect 是按比例估的（头 = 角色高 24%，
还假设头顶贴 y=0），实际只到画布 y=310 而脸画到 385 —— 点嘴巴触发的是「摸身体」。
改成按 seg_head 真实 bbox 校正。

最有价值的一条是**坐标系**：`hover/region/poke` 吃的是引擎帧缓冲坐标
（画布 × pet scale = `info.frame_w/h`），而 `stage.js` 一直拿 `img.naturalWidth` 换算
—— 那是帧缓冲 × 画质档 `s%`。画质档恰好 100 时碰巧相等，所以一直没暴露。
画质一降或 `/api/scale` 一改就整体点偏。两个组件都改掉了。
动手前查了 airi 的 `useLive2DEyeFocusFor`，它把显示矩形 / renderScale / 模型缩放
分得很清，印证了这个判断（REFERENCE_NOTES 第十四批）。

**新加的闸都做了负控**（这是铁律，一次就绿等于闸没工作）：
- `check_assets`「腮红压在实心脸上」≥80% —— 摆回旧位置 → 8%，红
- `check_assets`「摸头区域罩住整张脸」—— 退回 y=310，红
- `test_web`「poke 坐标按 info.frame_w/h 换算」—— stub 的 naturalWidth 故意设成
  848×1360，退回用它 → 报 "实际 424,680 ← 用成 naturalWidth 了"
- `api_smoke`「区域中心能命中自己」第一版就抓到真情况：feet 的矩形中心落在
  两腿之间的空隙上（alpha=0）。对非凸形状要求中心命中不合理，改成网格采样 + 不串台。

**踩的坑**：`make -s` 只建 test_core 不建预览（白查十几分钟，新字段一直是空数组）；
`/api/scale` 的参数名是 `s` 不是 `v`（差点第三次栽在参数名上）；
`frame.png?s=` 是相对**帧缓冲**的百分比不是相对画布；
api_smoke 的 scale 用例跑完不还原，把 1.0 漏给后面所有用例。

闸：selfcheck 146 不变、test_core 627 不变、web-test **92→109**、
api_smoke **147→175**、check_assets **372→375**、check_platform 32 不变。

## 2026-10-14（续）形态分区 + 把「计划不能忘」落成闸（G68 / T20.8 / T22）

**用户要求**：补形态分区（teen 之外先空白，做好了再加）；回答 AI 模型选型五问；
把「代理云端和本地 / 本机玩游戏 / 陪伴联机 / neuro-sama 式实时回应 / 本地模型自定义区块」
写进计划；**绝对不要豆包**；「我们所有的计划不能忘」。

**做了什么**
1. **形态分区（G68）**：新建 `characters/xiaoxun/forms.json` 路线图（teen=ready，
   loli/adult/chibi=planned）。引擎加 `load_form_roadmap()`，**以磁盘为准**合并。
   `info.json` 新增 `form_roadmap`，`forms`/`form_names` 继续只含 ready（向后兼容）。
   界面上 planned 灰显禁用、悬停说明还差什么。
   顺手修掉：`read_form_name()` 拿 rig.json 的 `name`（其实是角色名"小寻"）当形态名，
   四形态做完会全叫"小寻"；现在 forms.json 优先，teen 正确显示"少女"。
2. **计划落盘**：REQUIREMENTS 新增 A23~A28（代理云端/本地、本地模型自定义区块、
   本机玩游戏、陪伴联机、实时接取信息、供应商矩阵与排除豆包）；
   PLATFORM_PLAN 新增 **P4 实时陪玩** 里程碑（G69~G78，含依赖关系）；
   GAPS 新增 G68 与 G69~G78 缺口表；TASKS 新增 T20.8 与 T21.1~T21.10。
3. **「不能忘」落成闸**：`check_plan_traceability()` 做需求↔缺口↔任务双向追溯。
   **第一次跑就挖出 16 个 GAPS 登记过却从来没进排期的老缺口**，全部补登成 T22.1~T22.16。
4. **禁豆包双闸**：`check_platform.py` 扫 config 48 份；`selfcheck_repo.py` 扫 src/web/config
   全部源码。关键词覆盖 doubao/volcengine/volces/byteplus/seed-tts/豆包/火山引擎/火山方舟。

**负控（每道闸都验过会红）**：谎报 loli=ready → 红；清单删掉 teen → 红；
给 planned 的 chibi 建目录 → 红；加一条没落点的需求 I99 → 红；加一个没排期的缺口 G99 → 红；
往 `zpet.c` 注释塞 volcengine → 红；加个假的火山供应商 json → 红。全部还原后 0 项不通过。

**闸门数字变化**：selfcheck 146→**155**、web-test 109→**116**、check_platform 32→**33**，
test_core 627 / asan 627 / api_smoke 175 不变。`make -s check` 全绿。

**沙箱重置第六次**：HEAD 退回分支基点 `3b5d17b`，`git ls-files sprites` 只剩 7 条（磁盘 49）。
照旧 `git fetch origin` + `git reset --mixed origin/<branch>` + `checkout -- dist/.../zhuochong.exe` 修好，
`--mixed` 不动工作树所以本轮改动没丢。

## 2026-10-14（续二）游戏范围两次澄清 + 下半身骨骼（G83/G84/G85）

**用户澄清一**：游戏范围是我的世界 / 本地双人 / 局域网双人，英雄联盟等网游不在名单。
**用户澄清二（以此为准）**：不是完全禁止网游 —— 网游可以**陪伴聊天 + 实时看屏幕回应对话**，
只是不代打；**其他游戏可以真正游玩**。

**查资料（不闷头做，REFERENCE_NOTES 第十五批）**：
- Mineflayer 走 **Minecraft 协议**，AI 以一个普通玩家身份登录，拿结构化世界数据，
  **不装 mod、不截屏、不模拟键鼠**。Voyager（GPT-4）实证 63 种物品 / 科技树快 15.3×。
- MINDcraft 的**参数化命令**（`!collectBlocks("oak_log",1)`）比现写代码可靠得多。
- 已有现成 MCP 服务器包装 Mineflayer → 和我们的 G59 MCP 适配器是同一条路。
- **延迟实测：GPT-4 每动作 25 秒，本地 7B 300~500ms** → 直接印证 A23 双路由不是可选优化，
  而是 Minecraft 陪玩的前提（本地做快决策、云端做慢规划）。
- 坑：生成代码默认无沙箱，会"反复试同一个错法、一直烧额度" → 必须限时 + 失败计数 + 熔断。

**计划改动**：A25 重写成**三档模式** —— 档一观战陪聊（所有游戏含网游，零输入，
代码层面就没有输入通道）／档二 Minecraft 协议游玩／档三本地双人虚拟手柄。
新增 A25.15 游戏档位表（网游条目不可提升）。A26 增补：Minecraft 局域网世界本质就是服务器，
Mineflayer 能以第二个玩家加入 → 「陪你玩」与「陪伴联机」在这里是同一件事。
里程碑新增 G83（MC 协议游玩）/ G84（档位表），GAPS 与 TASKS 同步。

**下半身骨骼（G85）**：上半身 46 参数演得很细，下半身只有一个左右 bend，
18 个动作里 14 个腿是僵的。不拆件修完 —— 靠选对 bend 曲线：
sine 峰落膝盖、tip 落脚踝。新增 ParamKneeL/R、ParamWeightShift（一参数绑三条 bind）、
ParamTiptoe，新动作 shift_weight / tiptoe。
实测 ParamKneeL 像素差 **100% 落在腿部**；动作 shift_weight 超噪声底 **11.0 倍**、
tiptoe **8.4 倍**。连带把 `ZRIG_MAX_PARAMS` 48→64（50 个参数撞上限会导致形态加载失败）。

**两个排查教训**：噪声底量到 0 不是干净是**时钟冻结**（上个脚本 404 崩溃没解冻）；
动作通道打在**参数**上不在组上，按组名 grep 会误判成"腿没有任何动作"。

**闸门**：selfcheck 155 / test_core 627 / asan 627 / api_smoke 175 / web-test 116 /
check_platform 33，`make check` 全绿。

## 2026-10-14（续三）游戏档位表落地（G84 配置层）

用户再次强调「不是完全禁止网游，而是让他们可以在网游也陪伴聊天和实时屏幕操作
进行回应对话，而其他的可以真正的游玩」。A25 上一轮已按此改写成三档模式，
这一轮把 A25.15 的档位表从文档变成**可执行的约束**：

- `config/game_tiers.json`：3 档（观战陪聊 / 协议游玩 / 手柄游玩）、
  4 类别（网络竞技 / 网络休闲 / 开放协议沙盒 / 本地双人）、7 个游戏条目。
  档一 `input: "none"` 且 forbidden 列全三种输入；档三 requires 列急停/限频/显式授权。
  `default_tier: 1` —— 不在表里的游戏一律按最安全那档。
- `tools/check_platform.py` 新增七项闸：默认档最安全 / 档一真零输入 /
  网游类别锁死 / 游戏不得越类别上限 / 英雄联盟单独钉一遍 / 档位引用有定义 /
  档三带齐安全前提。
- **负控四种改坏法全部判红**：lol 提到档三、网游类别解锁、档一偷开键盘口、
  默认档改成档三。

闸门：check_platform 33 → **40**，其余不变，`make check` 全绿。
仍待做：界面上的档位开关与运行时强制执行，归 G79 权限模型。

## 2026-10-14（续四）本轮全部打断点与追加指令的完整时间线（防断代）

用户要求：「把我之前所有打断你之后的额外添加对话包括打断的全部都记上，
不要出现操作断代。」下面按发生顺序记全，包括**被推翻的中间结论** ——
断代最常见的形态不是"漏做"，而是"文档里留着一个已经作废的说法，
后来的人照着它做"。

### 时间线

| # | 打断时我正在做 | 用户当时追加的话 | 我怎么调整 | 手头的活收尾了吗 |
|---|---|---|---|---|
| 0 | （上一轮结束）形态分区 + 计划追溯闸 | —— | —— | ✅ 提交 `bea8f76` |
| 1 | 回答"计划做了吗/还缺什么"，并开始做立绘下半身 | 「我说的是我的世界以及本地双人，局域网双人等游戏，网络游戏像英雄联盟等不在名单内。」 | 停下立绘，先查 Minecraft 接入资料（第十五批），按"排除网游"改写 A25/A26 | ✅ 立绘后续完成，见 #4 |
| 2 | 落盘调研、改写 A25/A26 | 重复了 #1 的问题与游戏范围 | 继续同一方向，补 GAPS/TASKS/里程碑 | ✅ |
| 3 | 同步里程碑 G75/G76 + 新增 MC 专项 | **「等会不是完全禁止网游，而是让他们可以在网游也陪伴聊天和事实屏幕操作进行回应对话，懂了吗？而其他的可以真正的游玩」** | **推翻 #1 的理解**，A25 重写成三档模式 | ✅ |
| 4 | —— | —— | 完成下半身骨骼 G85（4 参数 + 2 动作，实测入档） | ✅ 提交 `a71cc17` |
| 5 | （已交付后）用户再次强调同一条 | 同 #3 原话 | 把档位从文档变成可执行约束：`config/game_tiers.json` + 七项闸 + 四种负控 | ✅ 提交 `3b6f90f` |
| 6 | —— | 「把我之前所有打断你之后的额外添加对话包括打断的全部都记上，不要出现操作断代」 | 核对全部收尾情况 + 写本节 + 修掉一处真断代 | ✅ 本节 |

### 关键：游戏范围的理解演变（**被推翻的中间结论**）

这是本轮唯一一处真正的断代风险，必须记清楚，否则看 git 历史会困惑：

1. **初版（我写的，无用户输入）**：A25「在本机玩游戏」泛泛而谈，
   附风险备注"联网对战里模拟输入可能违反用户协议甚至封号 —— 默认关闭"。
2. **第一次澄清后（已作废）**：理解成"网游被排除"，写了
   `A25.10 **不做网络竞技游戏**（英雄联盟一类）—— 用户明确排除`，
   并在调研笔记里写了"网游被排除后，反作弊与封号风险这两条顾虑整个消失"。
3. **第二次澄清后（最终口径，现行）**：网游**不是排除**，而是**锁死在档一（只读陪聊）**：
   读屏 + 看懂 + 实时开口回应，零输入。其他游戏才真玩。
   → A25 整条重写成三档；`A25.10` 这个编号现在是"生成代码必须限时熔断"，
   不再是"不做网游"。

**已消除的断代**：`docs/REFERENCE_NOTES.md` 第十五批是在第 2 阶段写的，
开头说"网络竞技游戏明确不在名单内"、末尾说"网游被排除后风险消失"。
本轮已在该批**开头加警示框、末尾加「④ 修正」节**，写明 ①②③ 的技术调研仍有效、
只有"网游怎么办"这一条变了，并指向最终口径。

### 本轮全部追加指令的落点（逐条可查）

| 用户追加的要求 | 落点 | 状态 |
|---|---|---|
| 代理云端和本地 | A23 / G69 / T21.1 | 已排期 |
| 本机玩游戏 | A25 三档 / G75·G76·G83·G84 / T21.7·21.8·21.11·21.12 | 配置层已落地，运行时待 G79 |
| 陪伴联机 | A26（含 A26.5 与 MC 合流）/ G77 / T21.9 | 已排期 |
| neuro-sama 式实时接取信息回应 | A27 / G71~G74 / T21.3~T21.6 | 已排期 |
| 本地模型自定义区块 | A24 / G70 / T21.2 | 已排期 |
| 扩充供应商、**绝不要豆包** | A28 / G78 / T21.10 + 双闸 | 闸已生效 |
| 网游只陪聊不代打、其他真玩 | A25 档一 + `config/game_tiers.json` + 七项闸 | 已落地，四种负控验过 |
| 形态分区先空白 | `characters/xiaoxun/forms.json` + G68 + 五项闸 | 已完成 |
| 所有计划不能忘 | `check_plan_traceability()` 四项闸 | 已生效，挖出 16 个漏排期缺口 |
| 继续动态立绘骨骼部件 | G85 下半身 / T22.17 | 已完成，实测入档 |

**核对结论**：工作树干净，三个提交 `bea8f76` / `a71cc17` / `3b6f90f` 全部已推送，
与远端一致。每个打断点手头的活都已收尾，无遗留半成品。

## 2026-10-14 续五：给老动作补下半身，以及两次被自己的判据骗过去

上一轮加完 `ParamKneeL/R`、`ParamWeightShift`、`ParamTiptoe` 四个参数，
但只有两个新动作在用，**14 个老动作一条没接**。这轮把尾巴收掉。

**改法**：`make_rig.py` 里加一张集中表 `LOWER_EXTRA`（动作 id → 追加通道），
在 `to_param_channels()` 调用前统一追加。没有逐个去改动作定义，因为
`wave`/`look_around` 是动态拼出来的、没有字面量可改。补了 8 个动作共 25 条通道，
判定不该动的 6 个（nod/focus/breath/stroke/clicked/dragged）没补。

**这轮真正花时间的是"怎么证明它有效"，判据连废两版：**

第一版「腿部变化 ≥ idle 噪声底 2.0 倍」，一测 7 个有效，很好看。
但 7 个数值整整齐齐挤在 2.0~2.2 倍，不对劲。拿三个**没有任何下半身通道**的
动作做负对照：nod 1.7×、focus 1.5×、clicked 1.5×、**stroke 5.3×**。
判据当场废掉 —— 它量的是"切换动作"的扰动，整个身体一平移，腿的像素自然跟着变。

第二版改成真 A/B（剥掉通道重启再测，唯一变量就是那 25 条）。判据对了，
但 `sleep` 报 **+1%「基本没用」**，八个里垫底。查了一下才发现是**指标饱和**：
sleep 的腿部变化像素 28745 = 腿区角色像素 27137 的 **106%**，顶到天花板了。
循环动作换成自方差（基准帧取自动作进行中）后反转：**734 → 7583，10.3 倍，
八个里最强的一个，被误判成了最弱**。

终版结果（负对照 nod 的 A/B 差值 +128 像素 = 测量误差底）：
wave +1983 / surprised +1349 / sad +2471 / think +2134 / talk +2086 /
look_around +2828 / head_pat +2183 / **sleep 10.3 倍**。全部有效。
中途按第一版判据把 surprised 的屈膝从 0.30/0.35s 调到 0.48/0.50s —— 这个调整
事后看是对的（受惊是全身反应，腿僵着就假），留着了。

**落地的保险**：光把教训写进 LESSONS 不够，下次换个场景还会重犯。
新增 `tools/measure_motion.py`，把负对照、饱和检查、循环/一次性分流、
周期防呆四件事做成工具的强制部分；再加一道 selfcheck 闸盯着这四件不许被拆，
四种拆法逐个验红并精确点名。WORKFLOW 里写死「改完动作必须用它验，
不要自己临时写脚本」。

**插曲**：沙箱本轮中途第八次重置（HEAD 退回分支基点、build/ 和 ~/.imgenv 消失），
`git fetch + reset --mixed` 修复，工作树改动全部幸存。
另外 `pkill -f "[z]huochong_preview"` 把自己的 bash 杀了 —— 同一条命令行后半段
有未加括号的同名字符串，`[z]` 技巧只防住 pkill 自身。改用 stop_process。

## 2026-10-14 续六：修点击卡顿 + 对照 Live2D 官方教程

用户反馈三件事 + 一个问题。逐条：

**① "被点击时有个错误的中途卡顿，眼睛很怪"（已修）**
引擎层逐帧探针（直接 link zrig.c 跑 60fps 步进，不受取帧速率限制）查出来：
clicked 声明 0.55s，但 bounce(dur 0.28) 到点归零、decay 包络在 0.28s 已衰到
0.1 度 —— **后面 0.27 秒角色完全不动**，而且 interruptible:false 这段再点没反应。
审计全部动作，同样毛病还有 happy / hammered / **tiptoe（上一轮我自己写的）**。
四个一起改，并加了 selfcheck 闸 check_action_dead_time 盯住（两种坏法负控验红）。

中途走过一段弯路：先怀疑是"眨眼被动作压制、动作一结束猛眨一次"，
数据看着也像（动作期间 blink 恒为 0，结束后 2 帧就眨）。换了 7 个不同预热时长
重测才发现 7 次里有 2 次眨眼发生在动作期间 —— **眨眼是自由运行的，第一个结论是错的**。
一组数据能讲通一个故事，不代表那就是真的。

**② "踮脚高度有了，但鞋子没有往地垫的动画"（确认属实，未做）**
`leg_l/leg_r` 各只有一个整段部件，**没有 foot/ankle 组**，没有任何部件能绕脚尖转。
好消息是 `make_anchors.py` 已经算出 ankle/foot 锚点，切件数据现成。记 G88 / T24.1。

**③ 待机循环 / 自动睡眠 / 唤醒 —— 用户确认没问题。**

**④ Live2D 官方教程站（用户给的链接）**
★ **更正一条作废结论**：笔记里记着"docs.live2d.com 不可达"，**是错的，能访问**。
而且 `fetch_page` 对 YouTube 会返回**完整字幕** —— 10 分钟的官方眨眼教程
拿到了全文逐字稿。前几轮"查不到只能推断"的前提根本不成立（LESSONS 81）。
已写入 REFERENCE_NOTES 第十六批。

照官方《提高动态质量的技巧》第 4 条"人在转脸或换视线时经常眨眼"，
实装了转视线带眨眼（阈值 0.45 + 55% 概率 + 1.2 秒冷却）。
实测视线不动 30 秒眨 5 次、来回扫视线眨 14 次（≈28 次/分钟，落在真人活跃区间）。
冷却是实测加的 —— 没有它一次大幅扫视会反复越过阈值，30 秒眨 29 次，看着抽搐。

照官方"闭眼时眼型横向略窄"加的 `aperture_narrow` **实测无效、已撤回**
（遮罩裁切够不到虹膜），记 G87 并写明别重走。

## 2026-10-14 续七：颈部滑移（用户发现，我的量法看不见）

用户反馈"颈部会横向整体错误细微的位移，包括颈部附近的兜帽位置"，
并直接问"这些你都不能查询到吗？我在测试网关很容易就看到了"。

**我确实查不到，因为量法不对**（LESSONS 84）。此前所有实测量的是
"幅度够不够"（整帧/分区像素差），而这是"各部分一不一致"的问题，
分区像素差会把差异平均掉。第一次尝试用"横带重心"更是方向就错了。

换成**逐行水平位移剖面**（相邻行位移应连续，跳变=接缝）一跑就现形：
头部恒定 −4.74px，躯干顶边 −5.08px，**跳变 0.40px**。

**根因**：躯干贴图顶边 y=308 其实是脖子和衣领，但 `bend_x` 的 root 曲线
`f(t)=(1-t)²` 在 t=0 给满额形变 → 衣领成了全身动得最多的地方，比头还多；
头则按颈关节 y=346 那一行刚性平移，只拿 0.854 倍。

**修法**：新增 `bend_hold_above`（形变平台线）。渲染时平台线以上的行
共用平台线处的形变量。引擎加 `zimg_draw_warp_blend_t()`，老函数保留为
0 平台的包装，**没改任何既有调用方签名**。生成器给 seg_torso 写 346。
实测滑移 0.34px → 0.04px（8.5 倍）。加闸 `check_neck_seam()`，两种坏法验红。

把 `--profile` 模式固化进 `measure_motion.py`（含时钟冻结 + try/finally 解冻），
然后拿它把整条剖面跑完，**又发现另外三四处接缝**（G90/T24.4）——
说明这类缺陷一直都在，只是之前没有能看见它们的工具。

**教程部分**：又读了基础教程《4. 添加身体动作》（有完整图文回顾）和官方物理手册。
★ 更正第十六批的说法："基础教程全是视频壳"过头了 —— 速成课才是纯视频，
基础教程 6 讲有图文回顾，嵌入用教程是纯视频（且在 bilibili），
**技术细节都在手册站**。官方物理模型规格（单摆四参数 + "输出超 100% 会抽搐"
+ 多段摆 + 计算 FPS 默认 60）已写进第十七批，对应 G44。
核对结论：我们的变形器分工、身体倾斜走弧线、上下动作时脚不离地 —— 都对得上。

## 2026-10-14 续八：摸头脖子抽长 + 歪头时身体是刚体（两个都是用户发现的）

**① 摸头（G91）**：用户说"不应该脖子伸长而是微微歪头一脸开心享受"。完全正确。
生成器里 head_pat 写的是 `head.dy = -7.0` —— 字面意义上把头往上平移 7px，
而 look 配置里胸只跟 0.7px，净抽长 6.3px。引擎层实测颈长峰值 **-9.48px**。
改成歪头（ParamAngleZ 绕颈关节转，不改颈长）+ 微沉 + 笑眼/脸红/笑嘴，
实测 **-9.48 → +3.23px**（头微沉，被摸时的自然反应）。

拦路问题：`ParamEyeLSmile/RSmile` 是引擎内建参数，不在 rig.json 的 params 里，
生成器的 `to_param_channels` 不认会直接报错。加了 `BUILTIN_PARAM_IDS` 白名单（9 个）。

**② 身体联动（G92）**：用户说"光是头在动，身体没联动不自然"。
Live2D 官方《提高动态质量的技巧》第 1 条一字不差：「如果只转动脸部，
则会看起来像一个机器人」—— 用户是自己看出来的，和官方说法撞上了。

根因查得很干净：`ParamAngleX/Y` 是内建、走 look 系统本来就同时写 head 和 chest；
**唯独 `ParamAngleZ` 只绑了 head**，而 20 个动作里 19 个有头部通道、
其中 **15 个身体完全不动**，这 15 个里 12 个用的正是 AngleZ。

没有去手工改 15 个动作（那是我上一轮 LOWER_EXTRA 的做法，而且那次我自己
埋了 tiptoe 死时间的 bug），而是给 ParamAngleZ 补一条 `chest.rot_deg×0.12`
绑定 —— **一行数据**。比例照抄 look 里已经调好的 1.2/5.0 = 0.24（LESSONS 86）。

A/B 实测（逐行位移剖面）：胸部段从**精确的 0.00px**（刚体）变成平均 5.88px，
腰部自然递减，过胸枢轴后还会反向 +2.58px。

两道闸 `check_head_body_link()`，六项断言、三种拆法逐个验红。171 → 179 项。

## 2026-10-14 续九：踮脚——修了浮空 bug，否决了拆件方案

接着 T24.1 做脚部拆件。按流程先查数据，结果查出一个**比"没拆件"更根本的 bug**。

**① 整个人浮空（已修）**
`ParamTiptoe` 的 `root.dy=-7` 和 `seg_leg_*.bend_y=-5` **同号**，
两个一起往上 → 不是踮脚，是**整个人连脚浮空 12px**（实测最底行 1359→1347）。
用户说的"踮脚脚部没有变化"字面成立：脚跟着整个人飘走了。
改成异号等量（bend_y=+7，tip 曲线底端权重 1.0 正好抵消）→
**Tiptoe=0/1 最底行都是 1359，脚底精确钉住**，身体照升，差额由小腿伸展吸收。
新闸 `check_tiptoe_grounded()`（异号 + 等量 + tip 曲线），负控验红。

**② 脚部拆件（否决）**
动手前先做图像模拟：把鞋段以鞋底为锚压缩 2%/8%/14%/22% 拼对照图。
结论：8% 看不出，**14%/22% 只是把鞋压扁了，像"踩瘪的鞋"不是"抬脚跟"**。
根因是鞋子**正面视角**（鞋底着地段 x164~207 vs 脚踝 x166~201，左右对称），
平面内纵向压缩给不出抬跟读感，平面内旋转读成崴脚。
→ 撤销 T24.1 的拆件部分，转成 **T24.5：AI 重绘踮脚姿态的鞋**（D19）。
脚踝切线验过了（anchors 的 ankle y=1142 正落在鞋口上沿），将来有素材可直接用。

十分钟的模拟省掉了一次 240 秒重建 + 一堆接缝债，而且避免了交付一个
**更难看**的版本（LESSONS 89）。

闸门 188/627/627/175/116 全绿。

## 2026-10-14 续十：上身惯性滞后，顺带挖出后发摆动一直是哑的

**① 惯性滞后（G93，做完）**
官方第 2 条"转动脸部，身体会在稍后跟随"。G92 让身体跟了，但是**同步**跟的。
加一条物理 `torso_follow_head`（input=ParamAngleZ → seg_torso.bend_x）。
能和 G92 的瞬时绑定共存是因为物理输出是 `pos - target`（纯滞后量，静止归零）。
实测阶跃时瞬间落后 2.47px、1.3s 归零；真实动作里 idle 0.03px（安静）、
nod 峰值 1.90px（明显）—— 正好是官方说的"动作要有张弛"。
闸 `check_torso_inertia()` 把阻尼比 ζ 钉在 0.4~1.2，负控验红。

**② 意外挖出 G94：物理超上限被静默丢掉**
加完上面那条，单测红了「裙摆纵摆峰值 0.000」。查出 `ZRIG_MAX_PHYS = 12`
而 rig 早就声明了 13 条 —— **第 13 条 `back_x`（后发摆动）一直是哑的**，
而且它是全场最大的摆（look_around 峰值 1.77px）。解析循环只是"装满就不装了"，
一句报错都没有。负控：上限 12 时 back_x/skirt_y 都是 0.0000，24 时分别 1.77/0.13。

修两处：上限 12→24；**超限改成硬报错**。
加闸 `check_engine_caps()` 扫三个 `#define` 宏和 rig 对应数组长度比对，
并要求留 15% 余量。现状 physics 14/24、params 41/64、parts 40/64。

**这个洞是碰巧挤掉了一个有单测的条目才暴露的** —— 如果挤掉的是别的，
它会一直在那（LESSONS 90）。

闸门 204/627/627/175/116 全绿。

## 2026-10-14 续十一：查剩余接缝，查出自己上一轮埋的洞

接 T24.4 查剩下三四处接缝。结论比预期好也比预期坏。

**① 三处"接缝"其实都不是接缝（LESSONS 92）**
肉眼三联对照图确认：肩部无可见接缝（差异图只是整体位移的边缘），
裙摆下沿只有一条抗锯齿边线。那个最大的 +2.35px 是**剖面工具的误报** ——
画布 y 727~796 同时有裙摆（不动）和双手（跟手臂动 5.66px），
互相关把两者混在一起了。剖面是筛查线索不是判决，必须肉眼复核。

中途还走错一步：为避开物理干扰改成"跑 3 秒收敛再冻结"，结果 settle 期间
idle 也在跑，两次取帧落在不同呼吸相位，跳变从 3 处暴涨到 32 处全是噪声。
正解是**冻结时钟 + 关物理**，为此给引擎加了 `/api/physics?on=` 开关
（关掉时所有摆停在目标上、输出归零，再打开不暴冲；不给 on 报 400）。

**② ★ 查着查着发现 G89 的修复是半残的（G95 / LESSONS 91）**
`bend_hold_above` 我上一轮**只接了 warp 绘制路径**。而部件挂没挂形变器是
**运行期按 amount 是否为 0 动态切换**的 —— 冻结时钟时物理不积分、
裙摆 amount 恒为 0，永远走 warp，所以当时测出来一片大好。
真实运行时裙子一摆就走网格路径，**平台丢失，颈部滑移原样回来**。

"为了降噪而冻结时钟"这个动作本身，正好绕开了有 bug 的那条路径。

修法：新增 `zimg_draw_mesh_bend_blend_t()`，控制点求曲线时同样钳 tb；
两处 fallback 也改成带平台的版本。图元级实测 warp 降 5.00 / mesh 降 4.50
（差 10%，来自网格分段线性近似，不是 bug）。

**单测加了 3 条**（tests/test_core.c）：平台在 warp 生效、在 mesh 也生效、
两者降幅等量（相对容差 15%）。两条路各自拆掉都验红并点名。627 → 630。

补了 `/api/physics` 的端点文档（selfcheck 的"端点都有文档"闸当场抓到我漏写）。

闸门 204/630/630/175/116 全绿。

## 2026-10-14 续十二：踮脚换鞋做成了，顺手捡回被"擦像素没裁画布"吞掉的 42%

接着 T24.5。这一轮的主线是"把一条自己亲手否掉的路重新捡回来"。

**① 先承认方向搞反了（这是全部的起点）**
上一轮用 `tiptoe_mock.png` 模拟"纵向压缩鞋子"，得到一堆踩瘪的鞋，于是写下
"脚部拆件已否决"。这个否决**前提就是错的**：相机是俯角 θ≈37° 的半俯视，
鞋的纵向投影 = L·sin(θ+φ)，脚尖抬起 φ 之后**投影变长**——踮脚的鞋在画面里
是**变高**，不是变扁。方向一反过来，拆件方案立刻成立，而且在图像上
"绕趾尖转 φ" 精确等价于"以地面线为原点的纵向均匀拉伸 k=sin(θ+φ)/sinθ"，
是一个纯几何重采样，连 AI 重绘都不需要。

**② 两次 generate_image 都废了，改手算**
按 D19 试过 AI 重绘踮脚的鞋：给参考图、给几何引导图、给详细美术指导，
两次都自行重构图、改袜型、漂移画风。**"保持构图只改透视"这类任务不要再丢给生图模型。**
产物已删。改写 `tools/make_foot_parts.py` 做分段线性重采样，0.6 秒出四件鞋，
鞋底压扁 0.65、鞋身拉伸 1.2967、抬高 30px，两张姿态图鞋底同在 y=1291。

**③ ★ 本轮最大的收获不是踮脚，是"擦像素没裁画布"（LESSONS 93）**
腿件切线以下的像素擦掉之后，画布还留在地面下方 142px 的空白里。
而引擎的 bend 曲线是按**贴图画布**铺 0..1 的，于是脚踝那条线从 t=1.000
掉到 0.774，**两处毛病同时出现且都不报错**：摆腿时脚只走 11.6px（原本 20px，少 42%）、
屈膝把整只脚抬离地面 2.9px。裁掉画布两处一起修好，实测摆腿恢复满额 40px 行程。
"画布底边正好是鞋底"这种白捡的对齐，以前从没人写下来——现在写进 ART_PARTS 5.13 + 闸门。

**④ 交叉淡化照抄官方曲线，不自己发明**
查了《创建有姿势切换的动态》和 SDK《About Pose》：运行时改的是参数不是部件 alpha，
`CubismPose::DoFade` 的常量是 Phi=0.5、BackOpacityThreshold=0.15，
中点淡出件留 **0.70**、总覆盖 **0.85**。我原本打算写线性——那样中点只盖 0.75，
**漏 25% 背景**，桌宠是透明窗口，漏的就是桌面。单测真渲染一帧量到 0.85，
负控（换成线性）量到 0.753，一眼分得开。

**⑤ 量"50 毫秒的重影"把量法换掉了（LESSONS 94）**
轮询取帧一次 45ms，根本采不到 3 帧的瞬态。把 `eval_channel_wave` 和
`ZEASE_OUT_BACK` 在 Python 里逐行复刻，解析算出窗宽对照表
（[0.25,0.75]=6 帧 / **[0.40,0.60]=3 帧 ≈50ms** / [0.45,0.55]=1 帧）。
复刻的过程里顺手发现 **bounce+out_back 的峰值只停 48ms** ——
这才是"换了鞋贴图却看不出踮脚"的真因。改成 pulse 之后实测抬起 ≥14px 持续 **693ms**。

**⑥ 又抓到一个浮空 3px（LESSONS 96）**
pulse 改完后发现动作期间画面最底行 747→744：tiptoe 里还挂着一条 `ParamBaseY`，
那是给 happy 跳跃用的参数（走 root.dy、不补偿脚，满格 40px）。
**不能给 ParamBaseY 加补偿**（happy 本来就该跳起来），只能在动作那层删掉它。
于是把这条做成闸：`check_feet_on_ground` 对**每个动作**复算鞋底净位移，
默认必须站稳，要离地的动作自己写 `"airborne": <px>` 且数字要对得上。

**⑦ 闸门与负对照**
新增/改写 4 道 selfcheck + 2 道防断代闸（276 项）、10 项素材闸（415 项）、23 条单测（653 项）。
8 个数据负控 + 1 个引擎负控全部如期变红。`make -s check` 2 分 17 秒全绿。

**⑧ 作废口径已就地改写**（用户要求："被推翻的中间结论也要记"）
GAPS G88 标题、TASKS T24.1/T24.5 三处旧说法已改写成"⚠ 这条作废，别照着做 + 正确口径"，
而不是删掉——保留是为了记住"方向搞反会把一条对的路否掉"。

- 下一步：第十三批 TTS 调研补进 REFERENCE_NOTES；`docs/ACCEPTANCE.md`（T23.4）；
  第十八批欠的四块（UI 美化 / 云端双路由判据 / 实时 STT / 生图生视频）；
  立绘侧只剩 🟢 纯增量（G44 physics 参数化、motion3 贝塞尔段、cdi3 导出、motion queue）。

## 2026-10-15 续十三：第二十批调研入库 + 真机验收清单 + 结论编号撞车

- 打断点：上一轮末 HEAD `66b8d0b`（A33 结论登记表）。本轮开工时**沙箱已是第十一次干净状态**，
  `~/.imgenv` 与 `build/` 又没了（未重建 —— 本轮没动 C 代码和素材）。
- 用户追加的话：无（延续 2026-10-15 的「下结论之前先查、再三检查」）。
- 做了什么：
  ① **编号撞车并当场改掉**：结论表原本编 `D01~D16`，与 REQUIREMENTS 的立绘需求系列 `D1~D20`
     （D19 = 被遮挡区必须 AI 重绘）**重名**。全表改成 `DC##`，闸里三处正则同步改，
     教训记为 LESSONS 98（新开编号前先查字母有没有主人）。
  ② **REFERENCE_NOTES 第二十批**：把第十八批欠的四块补完 —— 桌面 UI（Fluent 官方：
     圆角 8/4/0、嵌套每层小 2px、Mica 给底层 / Acrylic 只给瞬态面）、本地↔云端双路由
     （论文对照表：全本地质量 0.42/响应 3.97s vs 全云 0.57/1.06s，路由器综合分 0.752 最高；
     三支柱判据 + 语音链路延迟预算）、实时 STT（Whisper 不是流式模型；
     Whisper-Streaming 论文英语平均延迟 3.3s；VAD 的取舍）、TTS 供应商矩阵（补第十三批欠账）、
     生图生视频（ComfyUI `POST /prompt` + 显存档位；视频自托管要 24GB+）。
     **同时立了「证据等级 ★★★/★★/★/☆」的规矩** —— 这批里 TTS 延迟数字三家互相打架
     （75ms / 135ms / 400ms，口径不同），不标等级过两周就分不清哪条硬。
  ③ **新增 DC17~DC20**（本轮调研产生的有后果结论：STT 选型 / 双路由三支柱 /
     生图双路·生视频只走云端 / UI 按 Fluent 口径）。写 DC19 时闸抓到我把"负控"字段名
     加了括号说明导致认不出来 —— **闸干了它该干的事**，改回标准字段名。
  ④ **`docs/ACCEPTANCE.md`（T23.4 / G82）**：TASKS 里 22 处 `[需真机]` → AC-01~AC-22，
     六组（窗口输入 / 语音 / 立绘 / 平台长稳 / 模型训练 / 游戏三档），每条四栏
     （怎么测 / 算过 / 不过先查 / **沙箱边界**）。新闸 `check_acceptance` 双向对账。
     顺手把 TASKS 里两处"说明文字里的 `[需真机]`"改成"真机标记"，让对账判据能写成全称式。
  ⑤ **T25.5 回填**：DC21~DC26（先底层后立绘 / 口型用音素表 / edge-tts 不做主力 /
     契约是真相 / 不做网络竞技游戏 / 自研 zrig）。DC26 的选型理由翻不到当年证据，
     照 T25.5 的规矩标了「证据已佚」。
- 负控（本轮四次，全部如期报红后还原）：删 AC-09 整条 → 报「漏登 T21.4」；
  删 AC-15 的「沙箱边界」栏 → 报「AC-15 缺沙箱边界」；给 T22.3 加 `[需真机]` 不登记 →
  报「漏登 T22.3」；DC19 负控字段名加括号 → 报「DC19 缺负控」。
- 自检：**380 → 600 项，0 不通过**（+24 check_decisions 新条目、+196 check_acceptance）。
  本轮未跑 `make -s check` 全套：没动 C 代码与素材，`build/` 重置后也没了。
- 是否收尾：**是**。下一轮接：① 第二十批里标 ✅ 可做却还没做的两条负控
  （gateway 三条伪造请求验路由落点 / `check_platform.py` 加圆角白名单）；
  ② 仍欠的调研：主动发言触发策略、多人联机同步协议（A24）、生代码；
  ③ AC-20/AC-22 里"现在就能用静态闸验"的两条（代码层不存在输入通道 / 网游进不了档三）。

## 2026-10-15 续十四：把"现在就能做"的三条负控补上 + 双路由沙盘

- 打断点：上一轮末 HEAD `537dff4`。用户问了一句"这条规则有没有用、合不合理"，
  并让继续下一轮 —— 评价写在回复里，这里只记工程动作。
- 做了什么（都是上一轮 DECISIONS 里写明"可做但本轮没做"的欠账）：
  ① **G99 真双路由**：`zgw_route_for()` 三支柱（敏感 / 复杂长 / 忙故障），
     阈值从 `config/gateway.json` 的 `routing.rules` 物化进路由表（DC24 的老做法），
     每次决策记 `reason_hits[]` + `picks_local/cloud`，`zgw_local_share()` 给分流占比。
     新端点 `/api/route` 是纯决策沙盘，不发任何网络请求。
  ② **界面上能拨的 `route` 卡片**（用户的优先级是 UI）：三个开关 + 两个滑杆，
     实时显示落点/理由/分流占比，理由翻成人话。
  ③ **Fluent 圆角闸**：`web/app.css` 的 18/16/14/12/10 统一成 8/6/4（药丸 999px 保留），
     `config/ui.json` 的 `corner_radius` 从 18 改 8 —— **契约自己原来就不合规**。
  ④ **"代码层面不存在输入通道"闸**（AC-20）：全仓扫 11 个注入 API 关键词。
- 负控（六次，全部如期报红后还原）：敏感分支偷加上云 fallback → test_core 两项红；
  CSS `--radius: 13px` → 红；源码塞 `SendInput` → 红；把探测器正则改成 `SendInputXX` →
  **自检项**红（教训 99）；另两次是上一轮遗留的复查。
- 自己踩的坑：
  · **又用了 `pkill -f`**（自己记过"会杀自己"），命令连带自己一起死，`config` 还原没跑到。
  · 面板里 `host.api("/route?…")` 少了 `/api` 前缀 —— 真服务上会 404，**是新加的 web 测试抓到的**。
  · `tests/test_web.js` 的假 DOM 没有 `classList.toggle`，顺手补齐（stub 要贴着真 DOM，
    不能让组件迁就 stub）。
- 闸门：selfcheck 600 / test_core **653 → 666** / smoke **175 → 183** / web-test **116 → 124** /
  check_platform **40 → 43**，`make -s check` 全绿。
- 是否收尾：**是**。下一轮接：① 用 `data/usage.jsonl` 的真实记账重标那三个阈值（DC18 复查触发）；
  ② "任务类型自动判重活"的分类器（现在 heavy 靠调用方传）；③ 仍欠的调研：主动发言触发策略、
  多人联机同步协议（A24）、生代码。

## 2026-10-15 续十五：按用户授权校准 A33 + 自动判重活

- 打断点：上一轮末 HEAD `237b629`。**用户授权**：「你可以自行判断我的规则，
  做出边界以及优化，不用完全被这个约束。继续下一步。」
- 校准（落成 **A34**，A33 正文继续有效）：
  ① "再三检查" → **"至少两种不同方式"**（负控 / 独立来源 / 另一路径重算，占一种）；
  ② **只有"有后果的结论"进表**（关掉一条路 / 别人会照着做 / 写进契约或闸门），
     可逆又便宜的直接做；
  ③ **用户的指令不是我的结论** —— 不做负控去反驳用户偏好，不许用"我检查过了"推翻它；
  ④ 反稀释：selfcheck **分两栏报**（工程事实 243 / 文档纪律 52），闸**按规则计数**
     而不是"条目 × 字段"（324 → 16 项）；⑤ 登记表 ≤40 条；
  ⑥ 负控写"不适用"的必须给**替代检验** —— 这条当场抓出 DC12/DC17 两条是我自己糊弄的，已补。
  **折叠计数后把六次负控逐条重跑**（删字段 / 改状态 / 否决类写"没做" / 删 AC 条 /
  给 T22.3 加标记 / 负控写不适用），全部照常报红 —— 折叠没有削弱检出能力。
- 工程（补 DC18 自己写明的缺口）：`zgw_classify()` 按**关键词三类 + 长度**判重活，
  `/api/route?q=` 接上，面板加了输入框可以直接打字试。
- 负控三次：① 分类器一律判重活 → 四项红；② 阈值 600 改 60 → **第一次没红**
  （测试只钉了上边界），补 500 字节用例后再改就红 —— 教训 100「阈值要从两边钉」；
  ③ 面板 `/route` 少了 `/api` 前缀（上一轮）同类问题已有闸。
- 自己又发现一处：新需求本来写成 **A33b**，而可追溯性闸的正则只认 `A\d+`，
  **编号带后缀就会被闸漏掉** —— 改成 A34 才被纳入（119 条需求全部可追溯）。
- 闸门：selfcheck 295（分栏 243/52）/ test_core **666 → 683** / smoke **183 → 186** /
  web-test **124 → 127** / check_platform 43。
- 是否收尾：**是**。下一轮接：① 路由决策写进 `data/usage.jsonl`（现在只在内存计数）；
  ② 仍欠的调研：主动发言触发策略、多人联机同步协议（A24）、生代码；
  ③ 立绘侧 🟢 增量（G44 physics 参数化、motion3 贝塞尔段）。

## 2026-10-15 续十六：G90 查完 —— 最大的那处"接缝"是误报

用户问"live2d 立绘的情况怎么样了"，顺手把挂着的 G90 收掉。

**先汇报现状**（实测，不是回忆）：部件 44 / 动作 20 / 参数 41 / 物理摆 14 /
形变器 7 / 分组 13 / 交叉淡化 2；`check_assets --character xiaoxun --form teen`
= 415 项 0 不通过。二十个动作逐帧抓图拼了张总览：`logs/asset_qa/actions_sheet.png`。
（`sleep` 那格看着发灰是对的 —— 动作里写了 `"dim": 0.35`。）

**G90 的过程值得记**：
1. 先想用"物理开/关"做对照 → **空转**，工具自己关了物理（教训 102）。
2. 改成出图看 → `hip_seam.png` 一眼就清楚：**那不是裂缝，是裙摆压着腿的自由边**（教训 101）。
3. 判据修了：`row_material()` 按两侧平均色距分"真接缝 / 自由边"，阈值 40
   （实测同材质 5/9/27，异材质 66，取中间），合成图负控 0.0 / 275 / None。
4. 四个参数全跑一遍：真接缝最大 **0.45 帧px ≈ 0.82 画布px**，不到一个像素 → **不改**（DC28）。

这轮没写一行引擎代码，结论是"不用改" —— 但这个结论是**查出来的**，
不是想出来的。按 A33，否决类结论门槛最高，所以 DC28 里专门写了
"如果反过来会怎样"（给腿绑参数的三条代价）和两条复查触发。

## 2026-10-15 续十七：按欠账顺序清三项（真 bug → 落盘 → 引擎缺口）

用户说"继续下面的任务，不要跳过任务"。按欠账表顺序走，一轮清了三项。

**① `/api/region`（真 bug）**。老笔记写的是"未渲染过一帧全返回空"，
实测**症状记错了**：真实情况是同一个请求在首帧前后给两种答案（渲染前按画布坐标、
渲染后按帧坐标，两种都 200）。根因是 `zrig_frame_to_canvas` 在 `fb == NULL`
时退化成 1:1。修法见 DC29 + 教训 103。闸：test_core 3 项、smoke 4 项，负控红。

**② 路由决策落盘**（T26 / DC30）。`data/usage.jsonl` 每次决策追一行，
顺手补了 `no_candidate` 这个理由 —— 不记"没候选"会让分母偏小、本地占比虚高。
配套 `tools/usage_report.py`（`--sweep` 能反算阈值）。
在这个沙箱里真实流水全是 `no_candidate`（一家供应商都没接），
所以工具是拿合成样本验的：512→61.5%、1024→84.0% 落进目标区间。

**③ G97 `bend_hold_below`**。上平台的镜像，warp 和 mesh 两条路都接了
（上次只接一条，吃过"颈部修复只在裙子不动时有效"的亏）。
现有腿件**不改**，继续走"切掉"那条路，理由写在 GAPS 里。

闸门：selfcheck 295→**302**、test_core 683→**696**、smoke 186→**193**、
web-test 127→**129**。`make -s check` 全绿 175s。

## 2026-10-15 续十八：G98 —— 挥手不再把脚拎起来

`wave` 的上下起伏原来走 `ParamBaseY`（root.dy 整个人平移），只能靠在动作上声明
`"airborne": 2` 让闸放行。这轮改成人真实的做法：**胯下沉、腿顶跟着、脚踝不动**。

新参数 `ParamHipDrop`：`chest.dy +2` + 两腿 `bend_y +2 curve:root`。
关键在曲线选对 —— 脚件刚性跟随腿在切线处的形变，root 曲线在切线处正好是 0。

路上撞到两件事，都记下来：
1. 动作通道**只能打在参数上**（make_rig 自己卡的，对齐 Live2D 的 .motion3 口径）。
   我一开始直接写 `chest.dy` 通道，生成器当场拒绝。
2. 改完 rig.json **必须重启预览**才生效 —— 第一次测出来还是 2px，差点以为改法不对。
   （这条老早就记过，还是又踩了一次。）

实测：脚底振幅 2px → **0px**，头顶 5px、裙摆下沿 9px 照常动（负控：只量脚底的话，
"把动作删光"和"改对了"读数一样）。留证 `logs/asset_qa/wave_feet.png`。

`clicked` 的 6px **保留** —— 被戳弹一下就是要离地的，和 happy 同类，不是权宜。

---

## 续十九（2026-10-15）用户报三个观感问题：脸扭曲 / 眼睛卡住 / 动作时糊

用户发来两张截图（点击时 514×666、静止 362×644）并问"能看到截图吗""还能看到其他问题吗"。
**能看到。** 这一轮全程照 A33 办：先验前提、再做负控、结论带可复算的数字。

**先推翻自己**：上一轮记的"stroke 时脸部锐度 −40%"是错的。那个测法在画布上框死一个
矩形量梯度能量，头一动框里的内容就换了。改成互相关配准 + 把脸拆成眼区/嘴鼻区两块后：
嘴鼻区 idle −7.4% / clicked −7.0% / stroke −10.6% / head_pat −11.1% —— 全在噪声里；
只有眼区在 stroke(−37%)、head_pat(−34%) 掉，而这俩正是把眼睛按住半闭的动作。
**引擎没有"动作时变糊"这回事。**（DC32）

**模糊的真凶是前端**：`stage.js` 每帧请求 `/api/frame.png?s=60`（自动档第二级），
拿到 279×448 的图，再被 CSS 拉到 ~680px 高。同样显示成 424×680：引擎原生渲染眼区
锐度 1641，先渲 466×748 再 bilinear 缩放只剩 850（**−48%**）。
而且换档会连带改变图片固有尺寸 —— 用户那两张截图裙宽 **155px 正好等于 s=75 档**、
147px 是同档再被窗口缩 5%，这就是他说的"轻微扭曲"。三个负控都做了：
帧尺寸恒定（7 动作×14 帧全 466×748）、静态旋转平移不掉锐度、裙宽 1:1 命中档位。

**眼睛卡住的真凶是 blink_hold 停在交叉淡化区**：`stroke` 是 loop 且 `blink_hold=0.7`，
`happy` 0.78 —— 这段里睁眼件还在、闭眼件还没来，叠出一条没有瞳孔的扁青带，
而且 loop 会一直按着。顺带发现上眼线随闭合度线性下滑 21.5px 会压进虹膜（那个黑钩）。
修法：两个动作改成 `blink_hold 0.95 + 山型笑眼`（和摸头同一套）；引擎加 `lash_hold`，
半闭前睫毛不动、后半程 smoothstep 补齐，**全闭落点和以前完全一样**。
瞳孔像素 0.5 档 24→34、0.6 档 36→43。（DC33）

**三个闸都做了变异检验**：改回线性 → test_core 红 2；`nativePct` 写死 60 → web-test 红 2；
rig 改回 hold 0.7 → selfcheck 红 3。`make -s check` 全绿 **2m49s**。

**用户还问"还能看到其他问题吗"** —— 又查了两条怀疑，**都不是问题**（DC34）：
① 发丝白边：把原画降到帧的有效分辨率再比，原画 6.34% vs 我们的帧 4.36%，我们更少 ——
是原画自带的描边 + 显示分辨率不够。**注意这条如果不降采样直接比，会得出完全相反的结论**
（原画原尺寸只有 0.87%）。② `wave` 手臂像被拉长：量袖子像素，全程只变 +2.6%，
缩略图看走眼了。

**还欠一件**：G100 闭合度 0.2 附近的灰幽灵（真实眨眼只路过 0.1s，收窄阈值有
"眼白露在眼线上方"的已知代价），修法和触发条件都写在 G100 里。


## 续二十（2026-10-15）笑眼返工、挥手定位、本地不降级、四套 AI 主题

**用户这轮给了四件事**：① 本地必须正常分辨率与帧率（要能放大到整个桌面还清晰），降级只许
用于远程预览，并问"要测试本地了吗还是继续制作"；② UI 配色与装饰按 deepseek/gemini/grok/gpt
定制、完全可自定义且模块化，问"这些都还记得吧"；③ 验收反馈：抚摸不是 ∩ 笑眼 + 偶发脸部错误、
连点大小不变 ✅、动作中脸没问题 ✅ 但挥手"部件和链接都没做好"；④ 确认没问题就继续修。

**笑眼：我连错两次才找对。**
第一次怀疑贴图 —— 看了 `eye_*_smile.png`，本来就是漂亮的 ∩，排除。
第二次怀疑睫毛件没让位，还真给 `zrig.c` 加了 `TAG_EYELID` 让位的代码，`make test` 全绿。
**变异检验救了一命**：把改动撤掉，两版渲染像素差 max=3、变化像素 **0** —— 笑眼补片不透明，
本来就盖住睫毛，那段代码零效果。已撤回。
第三次才找对：用户点的是**摸头**（气泡"再摸一下下就好～" = `pat_head_2`），
而 `blink_hold` 是阶跃生效、`EyeSmile` 是 0.3s 的 pulse，两条曲线不同步 ——
动作头 0.3 秒和尾 0.15 秒各露一段"闭着眼但没在笑"的 ∪。去掉三个动作的 `blink_hold`，
闭合度交给 `blink = max(blink, smile)` 自己跟，问题帧 4→0 / 2→0。

**顺带挖出一个真缺陷**：`blink_enabled=0` 时 `zrig_blink_update` 提前 return，
`blink_hold` 整段够不到 —— 意味着用户一关自动眨眼，连"睡觉"动作的闭眼都失效。
这个缺陷还正好让我第一版闸永远绿（假闸），是做变异检验时才暴露的。

**挥手：定位了，没修。** 原以为是前臂 −80° 超过 G4c 标定的 70° 安全角，一扫发现
**上臂 −12° 就已经露底**（格子实心率 100%→14.2%），不是阈值问题 ——
躯干腋下那块**根本没有素材**。翻 G4c 的记录："躯干挖 40713px、补绘 **73px**"，
等于当时只羽化了切口没真补。这是素材级返工（G102/T31.1），本轮不半途动它。

**本地不降级**已做：`stage.js` 加 `isLocalHost()`，本地走 `QUALITY_SCALES=[1.0]`、
`tuneQuality()` 直接 return、解开 `max-height`、吃满视口高度；web-test +9 项，
两个变异（去掉不降级、把 e2b.app 误判成本地）都能判红。
但**素材上限仍是 848×1360**（切件时降采样掉了源图一半细节），要真正铺满桌面得走 T30.1。

**四套 AI 主题**已做：品牌色全部联网核实（第二十一批），DeepSeek 的 logo 竟然就是蓝鲸，
和小寻的鲸鱼发卡撞上了。装饰层（图标/纹样/角标）还没做，排在 T29。

**这轮的方法论教训**（LESSONS 109~112）：一次就绿的闸要当坏闸查；变异检验必须跑在
用户实际触发的那条路径上；`pgrep -f` 第三次把自己杀掉；诊断脚本不许写死 scale
（用户早把预览调到 1.2 了，我的 crop 全裁到画外）；动作期间取两帧做像素对比基本不成立。

## 续二十一（2026-10-15）渲染与 PNG 双线并行：T30.2 + T30.3 做完

**打断点**：用户说"继续你说的下一步吧" → 上一轮排好的顺序是 T30.2 渲染多线程 →
T30.1 素材 2× 重切 → T31 躯干补绘。本轮做完 T30.2，并把原本排在后面的 **T30.3 一起做了**
（理由见下：量完才发现 PNG 比渲染还贵）。

**做了什么**
1. `zimg` 加 `clip_y0/clip_y1` 行裁剪，四个会写 dst 的函数都尊重它；
   `zrig_frame` 按行带切，每带一个线程跑完整层序，带缓冲（scratch/maskbuf）每带一份、起线程前预分配。
2. 量完渲染才发现**真正的大头是 PNG**（91.5ms vs 渲染 30.8ms）。拆开：滤波 17 + deflate 72，
   其中 adler32 每字节两次取模就占 14.3ms。于是 T30.3 顺势做掉：
   滤波和 deflate 都按行带并行（段末补空 stored 块对齐，按字节拼接 = pigz 的做法），
   adler32 改延迟取模，`send_png` 从"写 /tmp 再读回来再 remove"改成内存编码。
3. 顺手修了两个自己写出来的 bug：`zimg_new` 没初始化 clip（`z_alloc` 是裸 malloc）、
   单线程路径没重置带缓冲的 clip（会让 y 靠下的带遮罩部件整个消失）。

**数字**（2 核沙箱）：渲染 1.66×，PNG 2.17×，端到端 1.0 档 7.0→12.1fps、1.2 档 5.2→9.1fps、
0.55 档 24→42.9fps。闸：selfcheck 307→**322**、test_core 717→**766**、smoke 194→**202**，
web-test 144、platform 43，`make -s check` 2m35s 全绿。

**被推翻/修正的中间结论**（按规矩必须记）
- ❌ "composite 的 clip 是必需的，变异会判红" —— 真 rig 上**不红**，因为带遮罩的部件全在第 0 带内。
  改成 zimg 层单元负控才成立。
- ❌ "4 线程足够暴露 clip 没重置的 bug" —— 不够，第 0 带 `[0,340)` 包住了眼睛，要 8 线程。
- ❌ "smoke 连跑三次 202/0 全绿 = 新代码没问题" —— **测的是旧二进制**：上一轮残留的预览进程
  占着 `build/zhuochong_preview`，`make` 因 `Text file busy` 静默失败，而裸跑 `api_smoke.py`
  连的正是那个残留进程（它不 `--spawn` 就不自己起服务）。清掉进程 + 用 `--spawn` 才测到真东西。
- ❌ 第一版 `draw_rect` 单测"判红"曾被我当成代码问题 —— 实际是**我自己把矩阵 m[3]/m[4] 写串**，
  行列式=0，`draw_impl` 直接 return。查了才敢下结论。

**收尾状态**：工作树提交并推送；预览进程用 start_process 重起（新二进制，0.0.0.0:5173）。

**下一步**（顺序不变）：T30.1 素材按源图 1696×2528 重切 → T31 躯干腋下补绘（G102/G103/G104）。
T30.5（脏矩形）和 T30.6（WebSocket 推流）新登记为待办，但要先想清楚怎么保住"并行==串行"那条闸。

---

## 续二十一（2026-10-15）T31.7 / T31.8：两个"用户看得见"的毛病，根因都不在我以为的地方

**做了什么**：按用户批准的"先做纯逻辑"，收掉 T31.7（张嘴时嘴上两撇小胡子）和
T31.8（台词气泡不消失）。两条都修完并加了闸，`make -s check` 全绿。

**T31.7 —— 我上一轮的归因是错的，这一轮把它推翻了**

上一轮写进 GAPS 的归因是「`surprised` 缺 `ParamMouthForm`，微笑嘴型没压回 0」。
这一轮先按计划去调 `mouth_open.alpha` 的 bind scale，渲对照网格一看：
**四行（−0.9/−2.0/−2.6/−3.5）肉眼完全一样**。逐字节量，满张时最大只差 12/255。
→ 改了等于没改，归因站不住。

接着做逐件消去（44 个部件逐个摘掉渲一帧，量天线框里的像素变化）+ 贡献差分，
一路查到素材本身：`sprites/mouth_open.png` 在 body_full 的落点是 **y252..275**，
而实测笑线在 **y246..250**，**垂直方向零重叠** —— 这张"笑线件"里装的是下巴阴影和
一角衣领（放大看右下角有一块蓝边）。它由 `tools/make_parts.py` 切出，
而那个脚本**根本不在 `rebuild_parts.sh` 里**，所以一直停在很久以前的坐标。
更要命的是它是"复制"不是"剪切"：原笑线始终烙在 `seg_head.png` 上，
张嘴时口内椭圆只盖得住笑线中段，两端上翘的嘴角高光露在椭圆上方 = 那两撇小胡子。

修法：新增 `tools/make_mouth_line_cut.py`（重建链第 16 步），从**只读的** `body_full.png`
按实测笑线框精确剪出 `mouth_open.png`（28×9 @ [208,244]），同一块在 `seg_head.png` 上
用上下边界逐列插值填平；alpha 按**色差**而不是暗度抠（两端嘴角高光比肤色还亮，
按暗度会把高光丢掉，闭嘴就只剩一根直棍）。笑线归位之后再把斜率改 −3.5。
实测：闭嘴改前改后**平均差 0.29**（弯度与高光原样），满张**最大差 145**（胡子清掉）。

**T31.8 —— 两层 bug 叠加，只修一层没用**

① 引擎 `zpet_last_line()` 返回的是"最后说过的那句"，`run_rule` 只在 `zinteract_speak`
返回非 0 时才覆写，冷却被吞时旧句**原封不动留着**；
② 前端 `onSpeech` 每次轮询（~80ms）都 `clearTimeout` + 重设 4500ms 隐藏计时，
而 `line` 一直是同一句 → 计时被无限推后，**气泡永远不会消失**。

修法：`zpet` 加 `last_line_at/seq/rule`；`run_rule` 在"台词被冷却吞掉 **且** 这次是另一条
规则"时清句（同一条规则连点不清，否则自己打断自己）；`/api/speech.json` 加 `seq`/`age`
（栈缓冲 640→832B）；前端只认 `seq` 变化，`age` 用来接"已经说了一会儿"的句子。

**加的闸（全部做过负控）**

| 闸 | 项数 | 负控结果 |
|---|---|---|
| `check_assets.py` 笑线对位 / 已剪走 | 2 | 放回旧 seg_head → 红（残留 36 像素）；落点改回旧值 → 红 |
| `selfcheck_repo.py` 剪切在链上 / 斜率两处一致 / 满张能归零 | 3 | — |
| `test_core.c` 闭嘴满显 / 半张归零 / 满张归零 | 3 | 斜率改回 −0.9 → 红在 0.550 / 0.100 两个预测值 |
| `api_smoke.py` G105 五项 | 5 | 关掉清句分支 → 气泡停在「再摸一下下就好～」 |
| `test_web.js` G105 七项 | 7 | 去掉 seq 判断 → "多排了 5 次计时" |

闸门计数：selfcheck 322→**325**，test_core 766→**770**，smoke 202→**207**，
web-test 144→**152**，check_assets 415→**417**。

**顺手修掉的一条假绿闸**：`test_core.c::test_mask` 借 `mouth_open.png` 当遮罩夹具，
素材一改尺寸就碎。换成测试里合成的 44×23 实心块后，还暴露出旧写法两个真问题 ——
`zrig_frame` 第二个参数是**缩放**不是时间（开合两次量用了不同缩放），
以及动作通道是**淡入**的、请求完只跳一帧量到的是半路值。旧断言能过纯属巧合（见 DC40）。

**被推翻的中间结论（按"不要操作断代"记下）**
1. ❌「胡子是 `mouth_open`（上唇笑线）的嘴角翘尖」→ 实测它在满张时贡献 ≤12/255。
2. ❌「胡子来自 `mouth_cavity`」→ 6× 图读反了；贡献差分显示 cavity 画的是干净椭圆。
3. ❌「cavity 素材顶部白条带两端出尖」→ 逐行量 cavity 与 mask 轮廓**完全相同**，0 行越界。
4. ✅ 真因 = `seg_head` 上没擦掉的原笑线 + 错位的拷贝件。

**记账**：GAPS G105 改已修、G107 归因作废并补真因行；TASKS 勾 T31.7/T31.8、新增
T31.9 `[需真机]`；ACCEPTANCE +AC-26/AC-27；DECISIONS +DC39（改了系数画面不变 = 落点错了）
+DC40（测试不许借生产素材当夹具）；LESSONS +113/114/115。

**收尾状态**：`make -s check` 全绿；工作树提交并推送。

**下一步**（顺序不变）：T30.1 素材按源图 1696×2528 重切 → T31 躯干腋下补绘
（G102/G103/G104/G108 同一批，因为 G108 与 G102 是同一刀）→ T31.6（`>_<` 倒 V 闭眼件，
要 AI 重绘）。

---

## 续二十二（2026-10-15）用户二次验收打回两条：惊讶的眼睛、以及 G105 只修了一条入口

**沙箱先出了一次状况**：跨轮重置，`build/` 没了、预览进程没了，而且 HEAD 退回分支基点
`3b5d17b`，152 个文件被显示成"已修改"。先核实远端分支确实指向上一轮推的 `e0e326b`、
产物也都在磁盘上，再用 `git reset --mixed e0e326b` 对齐（只移 ref+索引，不碰工作树），
单独还原 `dist/windows/x86_64/zhuochong.exe`，重建二进制起服务。工作树回到 0 改动。

**问题一：惊讶时瞳孔被放大（G109）**

用户原话「眼睛的眼球会不自然的变大…看着像个怪物一样很怪」。核对 rig：`surprised` 挂
`ParamEyeBallForm +1.0`，而这个参数在本 rig 里**只绑了眼球缩放**（sx 0.18 / sy 0.22），
实测峰值 **1.180 / 1.220**。

按用户要求上网查官方口径（REFERENCE_NOTES 第二十三批），发现我们**方向搞反了**：
- 瞪大眼有专用参数 `ParamEyeLWide`，"widen **beyond the extents of** ParamEyeLOpen"；
- Animaze 官方：`ParamEyeLOpen` 往 **max** 方向才是"目を大きく開く"；
- r/Live2D 两个独立帖子都写 shocked = "extra opened eye **+ smaller pupil**"。

改法：把四条含糊的部件级通道（换算后合并成 ParamEyeBallForm +1.0）换成**一条参数级**
`ParamEyeBallForm −0.45`，峰值 **0.919 / 0.901**。幅度是渲 4 档对照图挑的，不是算的。
真正的「瞪大眼」我们还做不了（没参数也没素材），登记为 **G110 / T31.12**。

**问题二：G105 只修了一条入口（DC41）**

用户原话「摸头后，点了很多次被捶还是没有转跳」，截图里动作栏已经是 `hammered`、
气泡却还挂着「再摸一下下就好～」。上一轮我把清句修在 `run_rule` 里，而**调试台的动作
按钮走的是 `/api/action` → `zpet_action_request`，完全绕过 `run_rule`**。
沙箱并排一量：`/api/poke` 清空正常（seq 8→9），`/api/action` **seq 冻在 10 不动**。

数了一下 `zrig_action_request` 在 `zpet.c` 里有 **6 处**调用，`run_rule` 只是其中之一 ——
**我只堵了六分之一**。改法：加 `last_line_action`（产出这句话的那个动作），
清句改挂到 `zpet_action_request`，两个例外不清：
`talk`（伴随说话的动作，`voice.js` 播音前就会请求它；`call_reply` 的 owner 也记成 `talk`）、
以及"请求的就是这句台词自己的动作"（连点同一个按钮不自断）。
自动回 idle / hover 切 focus 走的是 `zrig_action_request`，不经过这里，气泡能活满 4.5 秒。

**顺手做的记账整理**：`check_decisions` 的反膨胀闸（≤40 条）红了（41 条）。
按它的指引建了 `docs/memory/DECISIONS_ARCHIVE.md`，把 **DC07~DC11**（2026-10-14 那簇
踮脚/交叉淡化实现细节，主题已交付 + 全仓库外部零引用）搬过去，36 条。
同时加了 4 条闸盯住归档本身 —— 归档条目四栏要齐、不许与主表重号、
**用户硬约束（DC12~DC16）与四条 🔁 反面教材（DC01~DC04）永不归档**、主表要留指路牌。
没有这几条闸，"超了就归档"很容易滑成"超了就删掉"，而用户要的是**被推翻的也要留着**。

**闸门计数**：selfcheck 325→**330**（+1 瞳孔 +4 归档），test_core 770→**772**，
smoke 207→**211**，web-test 152，check_assets 417。

**负控（每条新闸都做了）**
| 改动 | 打回原状后 |
|---|---|
| 瞳孔 −0.45 → +1.0 | selfcheck 红；test_core 红在 **1.180/1.220** |
| 关掉 `zpet_action_request` 清句 | smoke 精确红在「（action 路径）切到别的动作要当场清句」一条，其余三条仍绿 |

**记账**：GAPS +G109/+G110 + G105-返工2；TASKS +T31.11(勾)/+T31.12，T31.8 补返工说明；
DECISIONS +DC41，DC07~DC11 归档；REFERENCE_NOTES 第二十三批；ACCEPTANCE +AC-28、
AC-27 补"两条入口要分别试"；LESSONS +116/117。

**下一步**（原顺序不变）：T30.1 素材按源图 1696×2528 重切 → G102/G103/G104/G108
躯干腋下补绘（同一刀）→ T31.6 `>_<` 倒 V 闭眼件 + T31.12 瞪大眼眼形（同一批 AI 重绘）。

## 续二十三（2026-10-15）用户问「VRChat / 3D / 唱歌 / 语气」+ 还能加什么

**用户原话**：「能否制作接入vrchat以及3d模型控制，以及唱歌和对话语气变化等。
还有什么功能可以加进计划？」后接「继续下一步吧」。

**沙箱又重置了一次**（本轮第二次）：HEAD 退回基点 `3b5d17b`、`build/` 空、预览进程没了。
按既定手段处理：`git ls-remote` 核实远端 = `638e1f9` → `git fetch` + `git reset --mixed`
→ 只剩 `dist/windows/x86_64/zhuochong.exe` 一个文件差异 → 单文件 `git checkout --` → 0 改动。
`make -s build/zhuochong_preview` 6.7s 重建，预览重新起在 5173。

**四项都查了官方文档再答**（第二十四批，A33 要求）。关键发现：

1. **前两项是同一件事** —— VRChat、VMC、VSeeFace、Warudo 全走 OSC over UDP，
   同一套报文。写一次约三百行纯 C 编解码就全通了 → **A35 一条 OSC 总线 / T32**。
   附带白捡两样：VRChat 每帧广播 `Viseme`/`Gesture*`/`Velocity*`/`Grounded`/`AFK`，
   **A27 的读屏在 VRChat 场景下不用截图不用 OCR**；VMC 的 BlendShape 直接驱动小寻的脸，
   **等于白捡一套面捕**，我们一行面部追踪代码都不写。
2. **3D 自渲：我准备的否决被自己的实测推翻了** —— 详见 DC42 与 LESSONS 118。
   第一版基准 5 秒/帧，正好"证实"了我的预设，复查发现是基准错了（随机顶点 → 巨型三角形）。
   改对之后：带纹理带描边 **116.7ms**，对照 2D 的 30.8ms，**贵 4 倍而已**。
   结论从"做不到"改成"**可行，但排在 2D 主线之后，拦路的是工程量不是帧率**"。
   基准源码入库 `tools/bench/bench_soft3d.c`，可复跑。
3. **唱歌：TTS 唱不了，这是接口层面的事**（DC43）。SVS 的输入是 music score
   （歌词+音符+时值），TTS 的输入是 text，没有逐音符 F0 入口就不可能唱准调。
   分三档：**S1 跟唱对口型（先做，几乎白送）** / S2 外挂 DiffSinger·NNSVS（要 GPU+训练音源）/
   S3 实时合成（不做）。另有一条"TTS 变调拼旋律"的廉价路，但本地音色已因机械音
   被用户否过两次，**不自作主张，等用户点头**（T34.4）。
4. **语气是四项里最便宜的** —— Azure `mstts:express-as` 的 **styledegree 0.01–2.0 连续可调**
   正好接 mood 强度；ElevenLabs v3/v4 走 audio tags 但**不支持 SSML break 且官方声明
   不保证生效**。两家性格相反（Azure 可复现 / ElevenLabs 表现力强），适配层统一成
   `(mood, intensity)` → T35。

**自提的两条**（拆需求时掉出来的）：
- **A39 / T36 音频驱动表演** —— 做一个 RMS+F0+起音的音频特征流，
  TTS 口型、唱歌跟唱、用户麦克风反应、系统音频摇摆**四个效果共用一个底座**。
  现在的口型是"播完统一 flap"的假口型，本来就该换。**当前性价比最高的一条。**
- **A40 / T37 候补池** —— 拿 Project AIRI 的功能清单对照着找我们的缺口，
  择优补了五条：OBS 接入（近乎零成本，我们本来就是 HTTP 服务）、桌宠窗口基本功
  （置顶/穿透/托盘/热键 —— "桌宠"二字的地基，现在还停在预览网页）、
  角色卡 CCv3、情绪与关系持久化、立绘整图切换。

**记账**：REQUIREMENTS +A35~A40；TASKS +T32~T37；DECISIONS +DC42/DC43（38 条，未超 40）；
REFERENCE_NOTES +第二十四批；LESSONS +118/119。

**下一步没有变**（用户要求插队后要把原顺序报一遍）：
**T30.1 素材按源图 1696×2528 重切** → G102/G103/G104/G108 躯干腋下补绘（同一刀）
→ T31.6 `>_<` 倒 V 闭眼件 + T31.12 瞪大眼眼形（同一批 AI 重绘）。
新进来的 T32~T37 **排在这条主线之后**，不插队 —— 用户的第一优先级原话仍然是
「先做好基础软件。ui，可以做动作的动态立绘」。

### 续二十三·续（同日）T30.1 开工即证伪，改道超分

接着上面那段，开始做 T30.1。**开工第一件事验前提，前提塌了**（DC44 / LESSONS 120）：
拆件基准 `design_sheet_short.png` 只有 1024×1536（人物 500×1452），
根目录 1696×2528 的 `小寻.png` 是**另一个姿势**的白底参考图（渲四联图一眼看出：
外套敞开度、手臂角度、衬衫领子都不同），现行降采样率是 0.8892 不是 0.5。

量了"取消降采样"能拿到的全部收益：像素 +12.4% / **锐度 +7.8%**，
而且两边放到 2.0 档都糊 —— **不解决用户要的"放大到整个桌面仍清晰"**。
按用户「做不出来就上网找办法」的要求去找，找到 Real-ESRGAN anime v3 x4（ONNX 2.4MB，
CPU 22.6s/张）。五项换基准判据（动手前定的）全过：倍率 2.0020/1.9993、
bbox 原点偏差 (-1,0)px、轮廓 IoU 0.9938、前景 NCC 0.9821 → **部件坐标乘 2 即可**。
锐度 +33.3%。

过程里栽了两次，都是度量自己的错：
① 3D 基准第一版 5 秒/帧（随机顶点连出巨型三角形）；
② 超分度量第一版 NCC 0.921「不通过」（把透明区的 RGB 也算进相关系数了）。
**两次都是"数字支持了我的预设"**，查完才发现是量错。都写进闸了。

本轮交付：`tools/upscale_sheet.py`（含五项判据 + 模型 sha256 校验）、
`design_sheet_short_x2.png`（2048×3072）、4 条新闸（3 个负控验过）。
T30.1 拆成 a~e 五步，**a/b 已完成，c/d/e（坐标系切 density）下一轮做** ——
那是最危险的一步，要先把 density 一致性闸写好再动手。

### 续二十四（2026-10-15）用户质疑「网上 AI 唱歌怎么来的」—— 我的框架被推翻

用户原话：「那那些网站上 ai 唱歌的音频和视频怎么来的？我们不能做吗？先回答讨论这个」。

**我上一轮把问题框错了**（DC45 / LESSONS 121）。我答的是"唱歌 = SVS，要乐谱 +
1–3 小时标注 + GPU"，这条路本身存在，但**网上绝大多数 AI 唱歌根本不走它**——
走的是**换音色**：UVR5/Demucs 分离人声伴奏 → RVC 把人声换成目标音色 → 混回伴奏。
旋律节奏咬字情感全部来自原唱，**不需要乐谱、不需要标注，训练数据 10 分钟**。
我算出来的成本高了一个量级。

错因很具体：我查的是"唱歌在技术上怎么实现"（→ 进了合成那条路），
没查"市面上的成品是怎么做出来的"（→ 才会发现主流绕过了合成）。

查的时候顺手掐掉了自己的第二个念头：「RVC 导出 ONNX 就能塞进我们纯 C（反正刚为超分
引进了 onnxruntime）」。**拉 RVC 当前仓库树核对：334 个文件里一个 onnx 都没有**，
官方只给了 `rmvpe.onnx`，社区那个导出工具 ★0 无 license。
→ 只能当外部进程调。这个念头如果不查就写进计划，下一轮就是一笔烂账。

**一个还不错的闭环**：小寻音色已定案走云端 TTS → 用 TTS 生成 10 分钟说话音频 →
训 RVC → 小寻会唱歌，音色和平时说话一致，且不碰任何真人声音权。
**但前置是 T34.2a：先读 Azure/OpenAI 条款，确认拿 TTS 输出训衍生模型是否违规。**
没查到定论之前不许默认可以。

版权这块单独立了 A37.6 / T34.5：民法典 1023 条声音参照肖像权，
"非商用"不免责；小寻是原创角色 + 自家 TTS 音色，本来就在干净的一侧，别自己走过去。

记账：DC43 加边界更正 + 新建 DC45（登记表 40 条，卡在上限，下次再加要先归档）；
A37 大改 + 新增 A37.5/A37.6；T34 从 4 条扩到 8 条；REFERENCE_NOTES 第二十六批；
LESSONS 121。**主线顺序未变**：T30.1c/d/e → G102/G103/G104/G108 → T31.6+T31.12。

### 续二十五（2026-10-15）用户问「计划够完整吗」—— 盘出一个结构性缺口

用户原话：「确定我们的计划够完整吗？还有什么缺漏的功能吗？就这些就够了吗？
除了我们的计划ai还能做什么？能不能像neurosama一样模仿人，而且设置几种变量，
工作模式，模仿人的模式等等等等，需要吗？还是说有更好的办法以及功能」。

**按结构盘（不是按条数盘）**：能力 6 / 基础设施 6 / 场景 3 / 流程 3 / 候补 1，
**「她是谁、她什么时候自己动」= 0**。关键词体检：性格/话轮/遗忘/衰减/persona/自己决定
在 REQUIREMENTS 里各 0 次。**但要说准**：A19 表格里有"L6 人格层"、A27.4 有"主动发言"，
所以是**在册但只有一行、从没展开**，不是完全没有（LESSONS 122）。

**对"要不要做几种模式"的回答：方向对，形式不对。** 互斥模式开关有三个必然的坑
（人不是开关式的 / 2^N 组合爆炸 / 切换时记忆人格继承说不清）。
更好的办法 = **连续状态变量 + 用户可存的 preset**；真要第二人格就开第二实例
（Neuro 和 Evil Neuro 就是两个独立程序 + 两份独立记忆，不是一个程序的开关）。

**查 neuro-sama 查出一条对我们有后果的事实（DC46）**：她的人格**烤在权重里**
（微调 2B/q2_k），prompt 只给情境；非微调不可的原因是**对齐过的基座模型会抵抗
prompt 里要求的性格**（kimjammer 的发现）。而我们走云端 API，**微调默认是关的** ——
所以人格只能靠工程撑：L0 魂每轮重锚 + 分层记忆 + 衰减。
而且 **drift 必须可量**：PersonaGym 的数字是 10 轮 90%+、100 轮掉到 60–70%，
我们要比这个好、好多少要有数字（T38.2 是 T38 的第一个闸）。

另一条值得抄的是 **Neuro SDK 的 typed action protocol**：下游注册 action schema +
上报状态，模型只回 action 名 + JSON，**下游负责校验执行**。
→ 我们的 OSC 总线(T32) / 游戏三档(A25) / skills **应该共用这一层**（T38.13），
否则每接一个外设就重写一遍。

记账：归档 DC05/DC06 腾位（主表 39 条）→ 新建 DC46；
新增 A41（人格与主体性）/ A42（主动性）/ A43（记忆生命周期）/ A44（话轮与打断）；
新增 T38（14 项）；REFERENCE_NOTES 第二十七批；LESSONS 122。

**主线顺序仍未变**：T30.1c/d/e → G102/G103/G104/G108 → T31.6+T31.12。
T38 和 2D 主线是两条线，不抢素材那条的工。

### 续二十六（2026-10-15）规划轮：审计 + 重写路线图 + 给它上闸

用户：「行就按照你的计划步骤来，然后要把我们现在的这些想法全部规划好记录好再开始下一步吧」
（= 同意 T38 不插队、按原主线顺序；先把规划做扎实再开工）。

**一、审计记录**：把用户 10-11 至今提过的 **42 件事逐条查落点 → 42/42 全有归宿**。
两个"没命中"是我关键词写错（「本地与网络双兼容」= A23 + prefer_local；
「音色持久化」= A22.5 + T13.1/T13.2，且已完成）。**没有东西只停在对话里。**

**二、但规划是坏的**：`docs/ROADMAP.md` 最后改于 10-11，一个 T 编号都不提，
还写着「身体分段 ⬜」「嘴待拆 AEIOU」——早做完了。
而 TASKS 已到 **32 大项 / 245 项 / 完成 41（16%）**，没有总视图。

**三、重写 ROADMAP** 成真正的总视图：7 个阶段 M1~M7 + 横切，
每阶段写明包含哪些 T、为什么排这个位置、完成判据是什么；
另加「明确不做」八条（每条带出处）和「等真机清单」。
**M1 立绘站得住（18/58）= 当前**，执行顺序 T30.1c/d/e → G102/G103/G104/G108 → T31.6+T31.12。

**四、给它上闸**（这是关键，否则四天后又过期）：
新增 `tools/roadmap_status.py`（可 `--fix` 自动改数字），接进 selfcheck：
每个大项都要排进某个阶段 / 不许排不存在的任务 / 写的进度数字要和 TASKS 实际一致。
**三条改坏负控全部精确报红。** 另外自己抓到一次：阶段正则第一版只匹配加粗的
`**M1**`，8 个阶段只盖住 1 个，全绿但没管住 —— 改完立刻多查出 M4/M7 两处错。

**五、顺手修掉一个命名冲突**：记忆分层原来叫 T0/T1/T2/T3，和任务编号 T2/T3 撞车
（脚本把"T0 魂"当成了任务编号）。统一改成 **L0~L3**，涉及 5 个文件。

记账：归档 DC22 腾位 → 新建 DC47；LESSONS 123；selfcheck 336（+1）。
**下一轮开工 T30.1c：切 density 坐标系，先写"density 前后一致"的闸再动手。**

### 续二十七（2026-10-15）T30.1 落地：切件链零改动，锐度 +96%

开工 T30.1c，**第一件事是数改动面，数完把原方案否了**（DC48 / LESSONS 124）：
原计划「整条切件链切到 2× 坐标系」，但坐标散在 17 个 JSON、上百个字段名里，
`*_px` 里还混着距离和统计量，逐个判断必漏。

**换成**：切件链一行不改，末尾加一步 `make_hires_sprites.py` 给每个件生成 `@2x`，
`make_rig` 发现就改用并把 `scale` 乘 0.5。画布坐标系完全不动，
rig 里所有像素常数（travel/lift/pivot/hold 线、硬编码的 `DEG_PER_PX` 344）一个没动。
—— 顺带更正：上一轮我在 T30.1d 备注里写「344 要跟着换算」，**那是错的**，
它是画布坐标下的常数，坐标系不变就不该动。

过程：
1. **先验渲染管线吃不吃得下** —— 只改 4 个脸部件，1.0 档锐度 ×1.947、
   四档性能全在 ±1% 噪声内，确认"缩小采样会走样"的担心不成立。
2. 全量 44 件：锐度 0.55/1.0/1.2/2.0 档 = **+81% / +95% / +96% / +48%**，
   耗时 +1.6%~13%，入库 +2.9MB。
3. **check_assets 自己抓出 21 个键色垃圾像素** —— 超分把原本躲在 alpha<40 的
   洋红残留抬上来了，正是 DC44 复查触发条件②预言的。按和 check_assets 完全一致的
   口径做了抑制（3×3 邻域非键色均值重填，两轮后仍是键色的清 alpha）。
4. 首跑 53 个件里 **11 个 rig 根本不用**，白占 2.09MB（body_full@2x 一个 1.6MB）。
   改成只做 rig 引用的 42 个，配兜底闸防漏。
5. 进重建链（17 → 18 步）+ 4 条新闸，三条改坏负控全部精确报红。

记账：归档 DC31 腾位 → 新建 DC48；TASKS T30.1c/d/e 重写成 c/e/f/g/h；
LESSONS 124；selfcheck **340**（+4）；check_assets **711**（@2x 也进了检查面）。
—— ⚠ 上一轮这里先写成「417 → 788」，**两个数都是错的**：拿 `git archive HEAD` 解到
`/tmp/base2` 跑同一条命令，高清化前后**都是 711**（@2x 的检查是并进已有条目里的，
不是新增条目）。这是 LESSONS 120「交接摘要会把错误数字洗成事实」的现场复发，
当轮就地改掉。

**下一步：G102/G103/G104/G108 躯干腋下补绘**（G102 和 G108 同一刀）。

## 2026-10-15 续二十八：肩关节这一刀（G102 + G108）

接上一轮的 T30.1，按原定顺序做躯干腋下。结果**两条缺陷的归因都被推翻了**。

**① G102 不是"没补绘"，是我们自己故意留的（DC49 / LESSONS 125）**
缺陷表写着"躯干挖 40713px 只补绘 73px"，读起来像 AI 重绘画得不够。
去查那 73 是怎么算的 → `make_arm_parts.py` 里有一行 `& (y > sh_y + SHOULDER_CAP)`，
`SHOULDER_CAP=46`，挖袖子时**特意给躯干留了袖子顶端 46 行**。
那是青色袖子，不跟手臂转 → 抬手时肩上一块悬空的青色三角，底边还是直线。
**用户说的"部件和链接没做好"就是它**（渲染留证 `g102_armswing.png`）。
代码注释给的理由「整块拿走肩膀就成平口」从没验过，而且是错的：
三格对照渲一次就看出来，拿走之后露出来的是夹克自己的圆肩 + 袖窿。
至于"补绘 73px"——重绘图 `torso_noarms.png` 画的无袖夹克轮廓比袖缝**还窄 2~4px**，
本来就没有可补的像素。改完静止合成差 **440 → 321**（比以前更贴原画）。

**② G108 不动切线，加一件压在身体底下（DC50 / LESSONS 126）**
缺陷表的修法是"改袖缝切线把三角肌还给上臂"。切线是一刀两面，会同时破坏 ① 和静止帧。
改成新增 `arm_{l,r}_root` 袖根塗り足し：逐行补到 80 分位袖宽（左 57 / 右 63px），
顶端 40 行 smoothstep 渐入，**层 95/96 画在躯干 100 底下**。
静止时闸测 **0 像素可见**，静止合成差一点没变；手臂一转就补上关节。
上臂上半段中位宽 **l 38→56 / r 40→62**，与前臂之比 **0.61/0.58 → 0.89/0.89**。

**③ 两个自己造的坑**
- "取最长那段"：袖子一行常被口袋线切成两段，按最长段的起点往里补，
  压到了另一段真袖子上 → 静止帧糊出平色带。改取整行跨度（LESSONS 127）。
  同一个坑这个文件里早就踩过一次并写了注释，我又踩了一遍。
- 手痒想把上臂贴图里那条袖缝线也抹掉（它从剪影边变成了袖子中间的线），
  静止帧立刻露出一圈毛糙麻点 → **否掉**，`ROOT_CLEAR_SEAM = 0` 和理由留在代码里。
  静止忠实 > 动起来干净。

**④ 闸与负控**
check_assets 新增"肩关节"一类 8 项（躯干上没留袖子 / 袖根静止完全藏住 /
袖根画在躯干底下 / 上臂上半段不比前臂细太多，各 ×2 侧），
**四条改坏负控全部精确命中**（1274·1310 / 层号为假 / 0.61·0.58 / 露出 47px）。
顺带被上一轮的 @2x 闸抓到一个真问题：新增部件在高清化那步之前不存在于 rig.json，
`make_hires_sprites` 的引用表是上一次的 → 漏做 @2x。
重建链第 17 步前加一次 make_rig 空跑刷新引用表。

**⑤ 顺手更正两处旧记账**
- `ParamArmLA` 的 note 写着"袖下躯干已 AI 补绘，转开不露洞"——假的，改掉。
- 上一轮 JOURNAL 写 "check_assets 417 → 788"，**两个数都是错的**：
  拿 `git archive HEAD` 解出来跑同一条命令，高清化前后都是 **711**。当轮就地改。

记账：GAPS G102/G108 标 ✅；TASKS T31.1/T31.5 标 [x]（都写了"归因换了"）；
归档 DC23 腾位 → 新建 **DC49/DC50**；LESSONS 125/126/127；新增 **AC-31**（待真机）；
check_assets 711 → **747**；selfcheck 340；`make -s check` 全绿。

**下一步：T31.2 / G103 —— 肘部 −80° 的硬折痕**（袖子上网格形变，项目已有 deformers）。

## 续二十九（2026-10-15）：用户第三次验收的三件事 —— 嘴 / 惊讶嘴形 / 袖缝白边

**打断点**：上一轮刚交付肩关节（G102+G108，`44d6a85`）并说"下一步 T31.2/G103 肘部硬折痕"，
用户直接贴了三张截图插队：① 张嘴表情"嘴巴位置偏下了一点"；② 惊讶"这个嘴巴"（配图）；
③ 肩部放大图，问"是否需要再检测一次……白色夹着的那道衣袖连线是否自然，白色的那点有点突兀"。
按规矩先修 bug，修完把原顺序重报一遍（用户 2026-10-15 的硬要求）。

**沙箱这一轮被重建过一次**（`process-2584242c` 没了、`build/` 丢了、HEAD 退回 `3b5d17b`），
照老办法 `git fetch` + `git reset --mixed 44d6a85` + 单文件 `git checkout --` 还原 exe，重建 venv。

**① 和 ② 是同一个根因，不是两件事。**
先把三张截图在沙箱 1:1 复现（`logs/asset_qa/mouth_now.png`），惊讶那条竖长黑块一模一样。
然后量嘴部几何，算出 `ParamMouthOpenY=1` 时开口 **40.6px**，而 1x 时代的设计值是 **20.9px**。
查 zrig 源码发现 `scale` 有两种语义（标量乘性 / 数组加性），T30.1 换 @2x 时只减了部件 `scale`、
没减加性通道的绑定 ⇒ 形变 ×2。`git show` 三个 commit 的 rig.json 把回归点钉死在 `d83e7a5`。

**这一轮自己推翻了自己两次，两次都是量错不是算错**：
- 第一次：探针写成 `tick → set_param → frame`，渲出来是**上一拍**的参数，
  量到"OpenY=1 只有 23px"，差点据此否掉正确的算术。补一次 `tick` 就对上了（LESSONS 129）。
- 第二次：第一遍按"@2x + 有 sx/sy 绑定"扫出 **9 条**受影响，其中 4 条是眼球。
  按语义重扫（只有数组 scale 才受影响）**自纠为 3 条，全在嘴上**；眼球是标量 scale，不受影响。
  好在当轮就自己抓住了，没写进结论。

**③ 查出来是我们自己的切件缺陷，不是原画、也不是背景。**
先排除两个猜测：原画袖内缘是「白→1~2px 暗缝线→青」没有滚边；那道白的 RGB 虽然恰好等于
预览背景斜纹的两色，但渲染帧同位置 alpha=255。最后靠**层属消去法**定案：
把 `arm_r_upper` 的 opacity 调 0，白点立刻变青 ⇒ 白来自上臂贴图自身
（`soft()` 羽化 2px 把夹克白切了进来，95%~100% 的行都有）。

**修 ③ 的时候踩了一个很值钱的坑**：`seam_trim` 判青色写的 `g - r > 20`，
在 uint8 上**回绕**（夹克白 235−238 = 253 > 20 → 白被判成青），整条裁剪一行没执行，
而 747 项闸**照样全绿**（那时还没有一条闸去问"裁了没有"）。
`seam_trim_px` 报 96/44 时我差点当成"裁了一点点"。加完后置条件闸 + 负控才揪出来（LESSONS 128）。

**数字**：
- 嘴：开口 40.6→**20.9px**，下沿 canvas 357→337（下巴 340）；talk 34→17.6px。
- 袖缝：白楔 surprised 155→**13px**、wave 80→**5px**；`seam_trim_px` l 805/235、r 768/226。
- 静止帧：`static_diff_px` 321→**421**，"无损切分"仍 **0 像素丢失**；20 个动作全扫，
  唯一报警的 `nod` 复核后是检测器把下巴阴影当成了嘴（假阳性）。
- 闸：check_assets **747 → 756**（嘴 5 + 袖缝 4），selfcheck 340，`make -s check` 全绿。
  两组闸各做一次负控，都精确复现坏数字（40.6px/y=289；越界行 222/68/226/68）。

记账：GAPS **G111/G112** 标 ✅；TASKS **T31.13/T31.14** 标 [x]；
归档 **DC21 / DC32** 腾两个位 → 新建 **DC51/DC52**；LESSONS **128/129/130**；
新增 **AC-32**（待真机）；ART_PARTS **5.15**；ROADMAP 计数 `--fix`。

**下一步（回到被插队前的原顺序，不改排序）**：
1. **T31.2 / G103 —— 肘部 −80° 的硬折痕**（袖子上网格形变，项目已有 deformers）；
2. T31.3 / G104 额头浅色弧线到底是什么；
3. T31.6 / G106（`>_<` 倒 V 痛苦闭眼）+ T31.12 / G110（真·瞪大眼），两件都要 AI 重绘眼形，同一批做；
4. 其余在册：T31.4 手部贴图偏糊、T31.10 孤儿切件脚本通用闸、T30.5/T30.6、T26、G96、G100。

---

## 续三十（2026-10-16）：抽搐的两个真因，以及星星眼/卖萌动作的规划

**用户这一轮给了六张截图 + 三件事**：① 嘴修好了、惊讶不过下巴了（AC-32 的两条过了），
但**测试台状态会左右轻微抽搐**，问正不正常；② 手臂没大问题了（AC-32 第三条过）；
③ 新需求：星星眼（截图 6）、三个卖萌动作（截图 3/4/5）、更多生动表情动作；
最后一句"规划好后继续下一步吧"。

### 一、抽搐查到两个真因，都不是"云端帧率低"那么简单

我一开始的假设是"云端预览才 2.5fps，慢摆动被采样成台阶"。**先查才发现这只对一部分。**

1. 先量 idle 的水平位移：0.55 档头部质心在 229.3~233.5 之间走（幅度 4.2px），
   2.5fps 下逐帧差 ≤0.59px，30fps 下 ≤0.06px —— **轨迹是平滑的**，引擎没抖。
2. 但发现一个反常：**同一个 t=0.40，用 dt=0.4 走出来是 232.6957，用 dt=0.033 走出来是 232.9325**。
   画面不是时间 t 的纯函数 ⇒ 有按 dt 积分的状态。顺着挖到 `physics_update`。
3. **G113 = 物理摆用整帧 dt 单步显式欧拉**（`if (dt > 0.1) dt = 0.1;` 然后积一大步）。
   实测同一真实时刻 t=2.0 对 60fps 基准：`ahoge_x` 0.1983 → **0.7188（×3.6）**、
   `hand_r_lag` 0.0175 → **0.1914（×11.3）**、`side_l_x` ×2.8。
4. 查官方源码定修法（`CubismNativeFramework/src/Physics/CubismPhysics.cpp`）：
   累加器 + `1/Fps` 定步 + 输入线性插值 + 输出按余量插值，`MaxDeltaTime = 5.0`。
   **官方注释里那句话直接对上了用户的用词**：
   「この仕様は補間範囲を逸脱したことが原因の**震えたような見た目**を回避を目的にしている」。
5. **G114 = 测试台状态行会左右跳**。用户原话是"测试台**状态**会左右轻微抽搐"，
   "状态"两个字指的是那一行胶囊。`web/test.html` 七个 `.pill` 是 `inline-block` + 比例字体，
   内容每 600ms 刷一次，最左边的 `动作 idle` ↔ `动作 surprised` 一变长，
   **右边六个全被推着走**。改成 `.pillrow`（flex + 按 `data-w` 定 min-width + tabular-nums）。
6. 还有**第三个因素，但它不是 bug**：云端预览本身就只有 ~2.5fps
   （`stage.js` 的 `tuneQuality` 在 frameMs>220ms 时把 minInterval 推到 166ms，加 RTT 约 300ms）。
   这一条只能靠本机验，已写进 AC-33 的"不过先查"。

### 二、这一轮踩的三个坑（都已写进 LESSONS 131~133）

- **指标选错差点把结论带反**：修完以后拿"整帧平均像素差"验证，得到 5.7109 → 5.7307
  （基本没变），差点据此认为物理不是真因。整帧差被身体慢摆淹没了。
  换成"物理输出的逐帧跳变"立刻显出 −43%~−79%。
- **新闸自己撞了 DC40**：第一版测试直接加载生产 rig，理由"假 rig 弹簧太温和看不出过冲"
  是**没试就下的结论**。改成合成夹具（刚度照抄真实量程 22/42/65/72）。
- **合成夹具第一次跑，修后的引擎照样红** —— 因为我给夹具的驱动比真实激烈 15~30 倍。
  阈值最后是在**同一夹具上量修前/修后两组数**定的，不是拍的。

### 三、闸与负控

- `test_core` 772 → **781**（G113 组 9 项）。负控：旧引擎 + 最终闸门 → **6 项全红**，
  实测值与记录的修前值**逐位相同**（jitter 0.1483/0.5179/0.1576/0.0967、
  dt=0.1 偏 128%、dt=0.4 偏 452%）。
- `test_web` 152 → **171**（G114 组 19 项）。负控：撤回 `.pillrow` → 红。
- `selfcheck` 340 项全绿（中途红过 5 项，全部是它替我抓出来的，见下）。

### 四、selfcheck 这一轮救了我四次

写完记账跑 selfcheck，一次性抓到：① **TASKS 编号重复** —— 我拿 T32~T35 写新规划，
而这四个号早被 OSC/VRM/唱歌/语气占了，改到 T39~T42；② DC53 的"证据"栏因为写成
"证据（可复算）："而匹配不上四栏格式；③ DECISIONS 超 40 条上限（本轮加 2 条只归档 1 条，
补归档 DC29）；④ 两处 `[需真机]` 没登记进 ACCEPTANCE（补 AC-33 / AC-34）。
**这正是"保险要能拦住自己"的意义**。

### 五、新需求的规划（已全部入库，不是口头承诺）

- **A45 / G115 / T39 星星眼**：先把现状和目标的差距量清楚 ——
  我们已有的 `eye_hl_style` 切的是**高光点**（`eye_hl_star_l@2x.png` = 40×40、
  172 个不透明像素、纯白），用户要的是**整只虹膜变金星**（现虹膜 62×60、蓝 (80,122,158)）。
  两者不是一回事，**必须新画素材**。官方口径（REFERENCE_NOTES 第二十四批）：
  闪亮眼/爱心眼互斥 → 归一个参数（= 我们的 Pose 组）；差分件要 clip 到眼眶并跟着闭眼；
  **要用 physics 驱动闪烁**，否则只是贴了张静态星星。
- **A46 / G116 / T40 卖萌动作**：硬边界量出来了 —— `ParamArmRA → rot_deg × −6.0`，
  参数 ±1 ⇒ **只有 ±6°**，而举手到脸前要肩 ~140°、肘 ~90°。
  官方做法是**手臂差分**（另画一套），不是把现有袖子硬转过去。
- **A47 / T41**：情绪强弱两档（截图 3 的捂嘴惊讶 vs 截图 4 的炸毛惊讶），
  前提是先补齐三样缺的眼形素材（G106 `>_<`、G110 瞪大眼、G115 星星眼），**合并成一批 AI 重绘**。

### 六、下一步顺序（已写进 ROADMAP M1，不再变）

1. T31.2 / G103 肘部 −80° 硬折痕（T40 要用到大角度手臂，这条是它的前置）
2. T31.6 + T31.12 + **T39.1** 三样眼形素材**同一批 AI 重绘**
3. T39.2~T39.4 星星眼挂 Pose + 闪烁
4. T40.1 角度扫描 → T40.2~T40.5 卖萌动作
5. T41 情绪强弱两档
6. 在册其余：T31.3 额头弧线、T31.4 手部偏糊、T31.10 孤儿切件脚本闸、T30.5/T30.6、T26、G96、G100

## 续三十一（2026-10-16）：星星眼落地 —— 管道全绿但画面是空的

**做完的**：T39.1 / T39.1b / T39.1c / T39.2 / T39.4 五项（T39.3 完成一半），
外加顺手修掉一个**和星星眼无关的老 bug**：六个表情全都让小寻不眨眼。

### 一、素材：AI 的图不能原样用（→ DC55）

`design/redraw/eye_star_iris.png`（2048²，蓝色五角星瞳，用户在两个候选里选的 option 2）
和 `fx_sparkle.png`。新工具 `tools/make_star_eye_parts.py`。两处栽跟头都是"看了才知道"：

1. **颜色**：`check_assets` 判红 —— 虹膜外圈 `#181878` 离色卡最近色 L1=100，闸阈 70。
   没有放宽闸，而是加 `IRIS_RAMP`（9 站全取自 `palette.json`）把明暗结构重铺到色卡上。
2. **尺寸**：第一版进引擎糊成一团蓝饼 —— 原图里星和底靠 **1px 描边**分开，
   2048→27 之后那条线不存在了。改成把星形分割出来（洪水填充亮区 + 开运算），
   星内映射到梯的 `[0.50,1.0]`、星外压到 `[0,0.34]`，**靠明暗读形**；
   再加一道 gamma 1.7 免得整颗星白成一片。碎钻高光 `t>0.80` 豁免不被压暗。

### 二、真机截图：两只空眼球，零闪光

这是本轮最该记的一段。素材闸 798 项全绿、`make_rig` 56 部件、预览正常启动 ——
**全链没有一处报错**，截图出来却是空的。两个真因都在"素材之后、画面之前"：

- **`motion_from` 连 alpha 一起抄**（`p_alpha[mi]`，和它自己的注释矛盾）→ 星形虹膜
  照抄了"常态虹膜被淡成 0"这件事，两张图一起消失。改成 `p_alpha[pi]`。（DC56）
- **加算不写目标 alpha**（`zimg.c:76` `oa = da`）→ 8 颗 ✨ 飘在剪影外的透明背景上，
  一颗都画不出来。改 `normal`。（DC57）

还撞了一次引擎静态上限：104 条绑定 > `ZRIG_MAX_BINDS 96`，预览直接 exit 3
（项目规矩是上限撞了就改大，不许静默截断）→ 256 / 96 / 96。

### 三、顺手发现：挂上任何表情，小寻就再也不眨眼了（→ DC58）

验星星眼闭眼时顺手测了一下眨眼，发现 `smile` 挂上之后 `/api/blink?v=1` 毫无反应。
一查 **6 个表情全中**，全是 `ParamEyeOpen` + `mode:"set"`。`set` 覆盖掉基准值，
眨眼驱动写进去的 0 被顶回来。改成 `multiply`（Live2D expression3 的标准三模式之一），
"微笑时眯一点" = ×0.85，眨眼压到 0 时 0×0.85=0，照样闭得上。8 个表情逐个复测通过。

### 四、判据与证据

- 星形读得出来：**星内外亮度差 108.3 / 106.5**（三次重跑逐位相同；原定的"数角点"
  判据在 2~5 之间乱跳，已废弃 —— 见 LESSONS 135）。
- 闭眼不穿帮：虹膜 124 → **15** px；常态档 ✨ **0** px，开启后 8242。
- **不动老档**：同一引擎分别加载 HEAD 旧 rig 与新 rig，t=0~3.0 共 61 个时刻逐像素比，
  **差异 0 像素、最大通道差 0**。
- 新增四道闸：素材侧「星内外亮度差 ≥30」「星形占虹膜 15%~55%」，
  selfcheck 侧「特效件不许加算」「表情不许把眼开合 set 死」；
  单测侧 `test_motion_from` 加差分件用例（负控：旧引擎下 27559 → 0，红）。
- `make -s check` **退出码 0**：selfcheck 342 / test_core 784 / asan 784 / smoke 211 /
  web-test 171，另 `check_assets` 798。全链 `rebuild_parts.sh` 19 步跑通（1m59s）。

### 五、自己的两个错（LESSONS 134 / 136）

1. **拿"工具链全绿"当交付依据** —— 差点就这么交了，是截图救的。
2. **用 `grep | head` 判闸绿不绿** —— smoke 的失败行排在第 20 行之后被 `head` 吃掉，
   我据此报了"五个闸全绿"，是错的。判通过只认退出码。

### 六、下一步（原顺序不变）

1. **T39.3 剩下的一半**：L1 星形瞳自己的 Sway（现在是静态的）；**T39.5** 触发条件
   （笑 + 睁大眼才出 ✨，现在是手动挂）。
2. T31.6 + T31.12 + T41.2 三样眼形素材同一批 AI 重绘。
3. T40.1 角度扫描 → T40.2~T40.5 卖萌动作。
4. T41 情绪强弱两档。
5. 在册其余：T31.3 额头弧线、T31.4 手部偏糊、T31.10 孤儿切件脚本闸、T30.5/T30.6、T26、G96、G100。

## 续三十二（2026-10-16）：星星眼返工到第三版 + 情绪特效（漫符）立项

**用户两件事**：① 打回星星眼配色；② 提出想做"小阴云、小雨云、小太阳"这类情绪特效，
并问我觉得怎么样、还需要什么、底层要不要做、更全面的计划是什么。

### 一、星星眼从第一版到第三版

- **v1（被打回）**：从 AI 图重铺整只虹膜，星外压到色卡梯最暗段换取对比度。
  闸绿了（星内外差 108.3），眼睛黑成一坨。用户：「像眼睛突然黑了……反而没看到星星」。
- **中途自己绊了一跤**：为了"客观"算了个蓝像素亮度均值，结论是**星版更亮** —— 和肉眼完全相反。
  掩膜在两张图上选到的像素集不同，均值不可比。**指标撒谎，判图只能看图**（教训 131）。
  改用"缩到用户真实观看尺寸 + 并排 + 9× nearest"，一眼看出问题，留证 `logs/asset_qa/star_eye_atsize.png`。
- **v2**：改成以常态虹膜贴图为底、星外一个像素不碰，星内按色卡梯提亮。黑的问题没了，
  但在 4× 下看，星在虹膜**下半截本来就亮**的地方糊掉了 —— 从"太黑"过矫到"太淡"。
- **v3（现在）**：① 星内亮度改成 `max(绝对映射, 当地底色 + 0.24)`，保证对**当地**底色永远有台阶；
  ② 加**深色描边**（#2C2939，1× 画 1px / 2× 画 2px）。
  注意这和"源图自带的 1px 描边"不是一回事：那条在 2048px 上画、缩到 31px 就没了；
  这条**在最终分辨率上画**，缩放吃不掉 —— 之前"细线到 27px 就消失"的教训被我误推广了一步。
- **判据也跟着改**：加描边后"描边画得越好、原指标越红"（28.5 撞下限 30）。
  没有松闸，而是承认判据定义过期，拆成两个台阶各自量 + 新增反向闸 `ground_kept`（星外保真，实测 100%）。
  → DC59、DC60。
- 闸门：check_assets 798、`make check` exit 0（342/784/784/211/171）。提交 `5c2f5f9`。

### 二、情绪特效立项（T43）

按用户「决定要做就先找好教程和参考」的要求，先查后答，写成 `REFERENCE_NOTES.md` 第二十六批：
- 用户想要的东西有正式名字：**漫符（まんぷ）**，日漫的一套视觉语言，清单/画法/Live2D 接法全现成。
- Live2D 里的做法和我们星星眼**一模一样**（参数 0/0/1 + 不透明度切 + clip 到母件）→ **不需要新引擎能力**。
- 意外收获：官方「Facial Expression Mechanism」白纸黑字写表情是 **Add 差分**、
  还专门拿眼开合举例说"加进眨眼动作的是 −0.2 这个差值"。
  → 我上一轮改掉 `set` 的那个判断（DC58）和官方口径对上了，但当时是靠真机实测发现的，**不是靠查文档**。
- **自己纠了一个错**：本来要记 G117「✨ 没挂 head 组」，查了 rig.json 发现八颗全是 `group:"head"`，结论撤回。
  按 A33 的规矩，这条当正面例子留在文档里。
- 真正要补的底层三样：**G117** 特效件硬编码（要声明式表）、**G118** 静态上限扛不住
  （部件 56/96、参数 51/96，一批漫符就顶死）、**G119** 没有画布级背景层（"小太阳"要用）。
- 实测约束：头顶净空只有 **65px**（角色包围盒 y 从 65 起），正上方塞不下云；
  但左右各有 **200px** 空白，而漫符经典位置本来就是「頭の右上もしくは左上」→ 一律走斜上角。
- `eval_keys` 在循环动作里会 `fmod` 整条曲线循环 → "持续上飘/连续旋转"用关键帧斜坡就能做，**不用新增波形**。
- T43 拆 7 项写进 TASKS，并排进 ROADMAP（被「有任务但没排期」的闸逮到一次，教训 134）。

### 三、下一步顺序（按用户要求重报，未改动主线）

T39.3 剩余（虹膜 Sway）+ T39.5 触发条件 → T31.6/G106 + T31.12/G110 + T41.2 三样眼形素材同批 AI 重绘
→ T40.1 角度扫描 → T40.2~T40.5 卖萌动作 → T41 情绪强弱两档 →
T31.3 / T31.4 / T31.10 / T30.5 / T30.6 / T26 / G96 / G100。
**T43 排在 T41 之后**，但 T43.1（抬上限）和 T43.2（声明式表）是纯工程不依赖素材，
可以插在等 AI 出图的空档里做。**T31.2 是否降级仍未判定。**

## 续三十三（2026-10-16）：细微表情立项 + 眼球微动落地

用户：「那就继续，但是细微表情也要做上，我之前说的都记在计划和记忆好之后就工吧」。
—— 这是对我上一条汇报的**纠正**：我写过一句「比做十个细微表情划算得多」，
用户的意思是**两样都要，不是二选一**。已登记 A48，并在条目里写明这句纠正的来历，防止我以后再拿性价比压它。

### 一、先记账（用户明确要求"记好之后就工"）
- `REQUIREMENTS.md` **A48 细微表情**：写清它和 A47.1（情绪强弱）、T43（漫符）**是三件不同的事** ——
  强弱是音量旋钮、漫符是外挂符号、微表情是"幅度小但自成语义"的脸部变化。三条硬要求：
  在真实观看尺寸下看得出来、能和现有表情叠加、**要有无人触发的自动那一层**。
- `TASKS.md` **T44**（7 项）+ 排进 ROADMAP。
- 期间 HEAD 又退回分支点 `3b5d17b`（已知现象），按既定修法 `fetch` + `reset --mixed 3ba4c5a` 拉回，
  工作树文件完好。

### 二、查（T44.0，用户 F 系列硬要求：不许闷头做）
`REFERENCE_NOTES.md` 第二十七批。**最大的收获是发现有两件事不用做**：
- 官方《提高动态质量的技巧》第 4 条「人在转脸或改变视线时经常会先眨眼」
  —— 引擎里 `LOOK_BLINK_DIST/CHANCE/COOLDOWN` 早就实现了。
- 官方自动眨眼要「Mean + Maximum Deviation」避免周期固定
  —— 我们的 `interval_exponential` 用指数分布，比官方建议还更接近真实。
核对成本是两条 grep，省下两次重复造轮子（教训 136）。
真正缺的只有**瞳孔微动**，而它正好就是 T39.3 剩下的那半（虹膜 Sway）。

### 三、做：眼球微动（マイクロサッカード）
依据 cgbox「人の眼球は静止していることはありません」，反面警告「やりすぎると常に慌てている印象になる」。
- 做成**引擎级**而不是星星眼专属：`gaze.micro{amp,gap_min,gap_max,speed}`，
  每 0.45~1.60s 换一个微小目标、以 16/s 快速趋近（眼跳是"跳"不是"飘"）。
- **幅度是实测标定的**，新建 `tools/calib_saccade.py`：视线满量程只有 4.0×2.5px，
  扫 amp 得 0.26 → 峰值 **1.00px**、RMS 0.53px，落在目标带 0.8~1.2px。
- 三条刻意的设计：① 不走 `look_cx`，微动是眼球的事不该带着脑袋晃；
  ② 不回写 `gaze_x`，底噪不许污染读数（否则"我设 0.5 怎么读出来 0.53"会变常驻 bug）；
  ③ **用自己的随机流 `sacc_rng`** 而不是蹭 `r->rng` —— 后者在喂眨眼，混进去会把眨眼
  的整条随机序列挪位，表现为"改 A 挂 B"的最难查故障（DC61）。
- 闸 9 项（784 → 793），**双向**：变异 amp→0.50 判红（1.98px 太慌）、变异 amp→0 判红（等于没做）；
  另有负控"摘掉 gaze.micro 必须完全静止"，防止它偷偷变成默认行为。
- 视觉复验踩了个坑：直接连拍三帧相减得到**全画布 72% 像素变化**，
  因为预览在实时跑、待机动画混进了差分。`/api/pause?on=1` 冻结后收敛到 **1139px、
  全在两只眼睛范围内**（教训 135）。证据 `logs/asset_qa/eye_saccade.png`。

### 四、下一步（顺序未改）
T39 全部完成（8/8）。接 **T39.5 触发条件** →
T31.6/G106 + T31.12/G110 + T41.2 三样眼形素材同批 AI 重绘 → T40.1 角度扫描 →
T40.2~T40.5 卖萌动作 → T41 → T43/T44（T43.1 抬上限 + T43.2 声明式表 + T44.1 盘参数
是同一个前置，可插在等出图的空档一起做）。**T31.2 是否降级仍未判定。**

## 续三十四（2026-10-16）：T39.5 ✨ 触发条件 —— 星星眼至此全部完成

用户「继续吧」。按既定顺序做 T39.5：✨ 不能"开了就一直闪"，
商业成品的口径是「笑顔で目を見開いたときに」才显示（BOOTH 5711516）。

### 先实测确认问题在不在
冻结画面后量：星星眼开着时，**睁眼 3732 px / 完全闭眼 3732 px，一个像素没少**。
确认 ✨ 确实和脸上发生什么毫无关系。
（第一次量忘了冻结，得到"剪影外 15888 → 40429"这种离谱数字 —— 教训 135 是我自己上一轮刚写的，
这轮又踩了一次。已在 LESSONS 里补了一句"自己写的坑要先查自己的记录"。）

### 做法：两道门
- **笑门**：`ParamMouthForm` 绑 ✨ 的 alpha（引擎里 alpha 是相乘累加，所以天然是 AND）。
  `scale 2.0 / offset −1.0` ⇒ 嘴角 0 全灭、0.25 出一半、≥0.5 满亮。
  门限 0.5 是**照着两条入口选的**：表情设 0.6、动作 pulse 到 0.8，都落在满亮区。
- **眼门**：新标签 `fx_eye_open`，闭眼变暗但留地板 `FX_EYE_OPEN_FLOOR=0.45`。
  **刻意不用现成的 `eye_open`**（那条会归零）：一次眨眼 0.3s、其中 0.12s 会触发硬门，
  一圈 ✨ 整体熄掉再亮起来，每 2~8 秒一次 —— 那不是表情是渲染故障（DC62）。

### 过程中纠的两件事
1. **忘了重编译**：改完 zrig.c 只跑了 `gcc -fsyntax-only`，预览还是旧二进制，
   于是第一次测出来"门完全没生效"。差点去改代码找不存在的 bug。
2. **度量选错**：用 `|frame − base|` 把 RGB 和 alpha 混在一起算，
   得出"半笑 93%"这种说不通的数。改成**只量剪影外的 alpha 通道**之后
   立刻对上设计值：不笑 0 像素 / 半笑 51.8% / 笑 100% / 闭眼 46.9%。
   —— 又一次印证教训 131：自己造的指标会撒谎，要选物理意义明确的量。

### 闸
新增 6 项（793 → 799），三次变异全红：拆掉笑门（不笑也亮 0.77）、
地板设 1.0（闭眼不变暗）、地板设 0（闭眼全灭）。
为此给引擎加了 `zrig_part_draw_opacity()` —— 原来的 `zrig_part_channel(…,"alpha")`
只看得到绑定那一半，看不见标签类调制，拿它测这个功能会假绿。
证据 `logs/asset_qa/sparkle_trigger.png`。

### 范围决定（显式记录，不许悄悄丢）
T39.5 原文还有后半句「特效的尺寸/位置/颜色要可调」。**不在本任务做**，
并进 **T43.2 的声明式特效表** —— 这三样现在硬编码在 `make_star_eye_parts.py` 里，
正是那张表要解决的问题，在 T39 里再实现一遍等于同一件事写两遍。
已在 T43.2 的备注里写明"含原 T39.5 的后半句"，不会掉。

**T39 星星眼 8/8 全部完成。**

### 下一步（顺序未改）
T31.6/G106（`>_<` 倒 V 闭眼）+ T31.12/G110（真·瞪大眼）+ T41.2（情绪两档眼形）
**三样同批 AI 重绘** → T40.1 角度扫描 → T40.2~T40.5 卖萌动作 → T41 →
T43/T44（T43.1 抬上限 + T43.2 声明式表 + T44.1 盘参数，可插在等出图的空档一起做）。
**T31.2 是否降级仍未判定。**


## 续三十五（2026-10-16）：抬上限 + 两档新眼形

**用户**：「继续吧」（承接上轮报的顺序：三样眼形素材同批 AI 重绘，等图空档插 T43.1/T44.1）。

**做了什么**

1. **T43.1 抬引擎静态上限**（上一轮开的头，本轮结清）。`PARTS 96→192`、
   `PARAMS 96→160`、`BINDS 256→512`。代价实测：`sizeof(zrig)` 617248→748064 字节、
   VmRSS 12800→12876 KB。顺带补了 selfcheck 一直缺的 `ZRIG_MAX_BINDS` 闸（342→345）。
   **自绊一跤**：注释里第一版写的代价数字是我估的（"1.21→2.35 MB"），差了近 9 倍 → 教训 139。
2. **T41.2 两档眼形**（= T31.6 `>_<` + T31.12 真·瞪大眼）。两张 AI 重绘脸
   （`face_eyespain.png` / `face_eyeswide.png`，用现成的 `face_eyesmile.png` 当参考图改画，
   保证配准对得上）→ 切件流水线从 2 档扩到 4 档 → 引擎加 4 个内建参数、3 个标签 →
   rig 层号每眼 10 槽扩到 12 槽、基址 216/226 挪到 211/223 → 表情 `pain` 新增、
   `surprise` 改走真·瞪大。
3. **`>_<` 出了两版选一版**：v2 的笔画更锐但横向跑出补片框（补片宽 57px 是按基线眼宽定的），
   切出来会被削断；选了跨度与基线一致的 v1。判据是量出来的不是看出来的。
4. **挖虹膜判据翻了两版**（颜色阈值 → 逐行眼白包夹 → 确定性几何椭圆）→ 教训 142。
5. **眨眼重影**：第一版 `wide *= (1−blink)` 线性淡出，blink=0.5 时两条上眼线各半透明
   糊成重影。引擎里闭眼/睁眼交接**本来就是错开硬交接**的（0.45 出 / 0.55 进），
   我没去读就自己写了个线性的 → DC63、教训 143。改成给补片挂 `eye_open` 标签复用那条曲线。

**被推翻的中间结论（按用户要求也要记）**

- 「瞪大眼补片的框按 `eye_parts.json` 的 `patch_size`（117×68）外扩」—— 错。
  那张画布大半是空白，真正的眼眶墨迹只有 48×42；按 patch 框外扩会一路探到脸外的
  洋红背景上，补片盖不满直接报错。改成按 `ball_pos` 居中大幅外扩，83×78。
- 「AI 画的虹膜比常态眼球大很多，椭圆要放到 1.35 倍」—— 错。实测 AI 虹膜 **27×31**，
  常态眼球 31×30，几乎同尺寸。1.35 倍横向超了 1.5 倍，把下眼睑和整圈眼白全吃了。
  改成 1.08/1.18。

**验证**：`make -s check` exit 0（selfcheck 345 / test_core 809 / asan 809 /
smoke 211 / web 171），`check_assets` 826 项全过。新闸 `test_eye_variants` 10 项，
五枪变异全部命中各自断言。留证 `logs/asset_qa/eye_variants.png`。

**没做的 / 拆出去的**：`ParamEyeBallForm` 改名（官方语义是"弯曲眼睛轮廓"，
我们当"瞳孔缩放"用）从 T31.12 拆成 **T31.16**，单独一轮做。
T44.1 盘参数本轮没动（眼形占满了），仍在队列里。


## 续三十六（2026-10-16）：回答"抽搐是不是云端的问题"

**用户**：星星眼和 `>_<` 都认可了；问"测试台的眼睛/视线/脑袋跟随会有轻微抽搐，
是云端的问题吗？还是说不是问题？"。另外指出我把进程标签写成了"卓虫预览"
（`zhuochong` = **桌宠**，我打了同音错字）。

**结论：是预览通道的问题，不是动画的问题。** 按三步查的：

1. **姿态函数无辜**。跟随平滑是 `k = 1 − exp(−speed·dt)`，按时间算。
   同一段时间用 10/30/60fps 和抖动帧间隔推到同一绝对时刻 t=1.0，
   `look_x` = 0.89972681 / 0.89985007 / 0.89987096 / 0.89985450，最大差 1.4e-4。
2. **通道才是瓶颈**。满尺寸一帧 PNG 190.1 KB，10fps = 1.86 MB/s；
   本地出帧中位 25.4ms（服务端不慢），本地链式上限 40fps，
   而测试台写死 `setInterval(refresh, 100)` 自己把上限按在 10fps。
3. **刷新循环有两个缺口**：没有在途保护（链路一慢就往浏览器连接队列里堆请求）、
   没有顺序保护（`onload` 无条件 `img.src = next.src`，旧帧后到会让画面倒退）。

**修了什么**：抽出 `web/frameloop.js`（纯逻辑、依赖注入、可单测）——
在途保护 + 丢弃迟到帧 + 按 `<img>` 实际显示宽度要图；轮询 100→33ms 试探，
真正的节流交给在途保护；hover 90→60ms（视线要跟手）、region 90→250ms（只是个标签）。
实测带宽 190.1→98.8 KB/帧，降 48%。闸 `test_web` 171→188，四枪变异全红。

**自绊一跤（教训 144）**：第一版 harness 把 `zrig_tick(r, now)` 当成传增量，
三档固定帧率全返回 0，看起来像"引擎有 bug"。差点据此下结论。
实际是测量装置错了。异常数字支持我想要的结论时，恰恰最该怀疑它。

**诚实边界**：本地并发实测**没有复现出乱序**（4 轮 × 6 并发全顺序），
所以"旧帧后到"是按代码缺口补的保护，不是实测到的现象，GAPS 和 TASKS 里都写明了。
云端剩下的不平滑是带宽决定的，**要本机跑原生桌宠才能看真实手感** ——
原生路径直接渲到窗口，不走 PNG 不走网络，根本没有这条链路。


## 续三十七（2026-10-16）：T44.2 两条微表情通道，外加一次自我纠错

**做了什么**

1. **`ParamMouthX`（单边嘴角）**。T44.1 查到的做法是不造 `MouthCornerL/R`，
   用一个 Animaze 扩展表的 `ParamMouthX` 顺带抬起一侧嘴角。实现成
   `mouth_open`/`mouth_mask` 的 `dx ±1.5px + rot_deg ±8°`、`blush_l/r` 的 `dy ±1.6px` 反号。
   幅度不是拍的，是**四档扫描**出来的（`logs/asset_qa/mouthx_sweep.png`）：
   抬嘴角靠旋转，平移一大就变成「嘴整个滑到一边」的缺陷。
2. **眨眼随情绪漂移**。`blink.mood_rate` 表 + `zrig_blink_set_mood()` +
   `zpet_express()` 接线。倍率全部有出处（第二十九批），
   **其中 2 条如果按直觉做会做反**（sleepy 是「慢而久」不是「少」；
   think 是动脑所以增加，不是盯着看所以减少）。
   180 秒实测：常态 11.0 次/分 → angry 19.3 / affection 8.7 / think 14.7，
   sleepy 单次闭眼 0.177s vs 常态 0.077s。

**一个没做到的（G121，写明了没藏）**：单边嘴角**闭嘴时真实尺寸看不出来**。
屏幕上那张嘴闭着时只有 16×3 px，±8° 只改 33 个像素。加幅度不解决 ——
四档扫描的像素变化量是 32/29/32/43，而且越加越像缺陷。
**张嘴说话时是够的（66 像素，清楚可读）。**
办法已经查到（职业档的「口角L/Rデフォーマ」≈ 我们这套引擎的差分件），
归 T44.3 和 T31 的出图批次并一轮。

**自我纠错（教训 146）**：上一轮 T44.1 我写「眨眼频率随机早就有，
`interval_exponential` 指数分布，比官方更进一步」。这轮打开 rig.json 一看是 `false` ——
**引擎支持，我们关着**，实跑的是均匀分布。我当时 grep 到调用点就下了结论，
没看配置。已在 TASKS 里原地纠正。
（顺带：查完发现均匀分布反而是对的，正好等于官方 CubismEyeBlink 的
「Mean 5s ± Deviation 3s」，所以**不改**，但理由和我原先写的完全不是一回事。）

**还踩了一脚**：中途用 `/tmp/mr_head.py` 跑 make_rig.py 做对照，
脚本按 `__file__` 定位数据目录，在 /tmp 下找不到输入，**静默产出一个 6 部件的空壳 rig**
并覆盖了工作树。幸好先 `cp` 了备份。同一时间 HEAD 又退回了分支点（已知沙箱现象），
两件事叠在一起一度看着像「rig.json 被改烂了」。按既定 recipe
（`git fetch` + `git reset --mixed <远端 sha>`）恢复，rig.json 的真实 diff 只有 76 行。

**闸**：test_core 809→822（+13），五枪变异全中（去 rate / 去 closed_scale /
未知情绪不回落 / 旋转改小 / 脸颊同号）。selfcheck 345/0（新增 `ParamMouthX`
的合规对照表条目）。`make -s check` exit 0。


## 续三十八（2026-10-16）：T43.2 声明式特效表，G117 关掉

✨ 原来是这么做的：8 颗的坐标/尺寸/旋转/频率/相位是 `make_star_eye_parts.py` 里的一张
字面量元组表，层号 `SPARKLE_LAYER0 = 300`、部件名 `f"fx_sparkle_{i}"`、
参数名 `f"ParamSparkle{i}"`、门控系数 `2.0 / -1.0`、动法 `amp 0.62 bias 0.38`
散落在 `make_rig.py` 的四个地方。要上四种漫符就得照抄四遍。

现在全部搬进 `characters/xiaoxun/design/effects.json`。两个生成器：
切件器加了 `load_effect()`（`SPARKLES` 变成空壳 `[]`），
`make_rig.py` 删了 `SPARKLE_LAYER0`、加了 `fx_gate_binds()`，所有字面量换成读表。

**验收口径是"迁完输出必须逐字节相同"，达成了** —— `rig.json` 和 `star_eye_parts.json`
两个 `diff -q` 都静默通过。

**五枪表生效验证**：改 `layer0` → 层号跟着变；改 `param.prefix` → 参数名跟着变；
改 `gates[1].scale` → MouthForm 笑门的系数跟着变；改 `motion.amp` → idle 通道跟着变；
删 3 片 → 部件与参数从 8 降到 5。

第 5 枪一开始**没过** —— 删了 3 片但片数还是 8。查出来是数据流有两段：
`effects.json` →（切件器）→ `star_eye_parts.json` →（make_rig）→ `rig.json`，
片数走第一段，只跑 make_rig 当然不动。重跑切件器就对了。
这是个会咬人的隐性约定，已写进 T43.2 / T43.3 的备注和教训 149。

**反向闸（教训 148）**：这类重构的特有失败模式是"表迁好了，下次有人又在代码里塞字面量"。
所以 selfcheck 新增一节 10 项（345→355），除了查表本身（字段齐全、
blend 必须 normal 照 DC57、freq 两两不同、尺寸档要混用），
还**反向查源码里不许再出现** `SPARKLE_LAYER0` / `f"fx_sparkle_{i}"` / `f"ParamSparkle{i}"`，
且切件器的 `SPARKLES` 必须恰好是 `[]`。三枪变异全中。
（查之前先把注释行剥掉，否则讲解这件事的注释会把自己判红 —— 这个坑踩过。）

**下一步 T43.3** 起第一批漫符素材（汗 / 💢 / 暗雲 / ZZZ）。接线方式已经就绪：
加一种 = `effects.json` 里加一条 + 一张素材，不用动生成器。

## 续三十九（2026-10-16）T43.3 第一批漫符素材

做了四种漫符（manpu，漫画里那套符号化情绪记号）：**汗 / 怒りマーク 💢 / 暗雲 / ZZZ**。

**出图**：`generate_image` 四张并行，一律洋红底、尺寸 1254²，照 `fx_sparkle.png` 的规格，
落 `characters/xiaoxun/design/redraw/fx_{sweat,anger,gloom,zzz}.png`。

**切件器** `tools/make_manpu_parts.py`（新）：键洋红 → 裁包围盒 → **按色卡重铺** → 出 1×/@2x
→ 写 `manpu_parts.json`。和 `make_star_eye_parts.py` 的分工：那边管「一张素材铺很多片」的
散布型（✨），这边管「一个符号就是一张图」的。几何/颜色/位置**全在 effects.json**，
脚本里没有任何一种漫符的名字 —— 加第五种 = 表里加一条 + 放一张图，不改 .py。

**踩的两个坑**（已写进 LESSONS 150/151）：
1. 第一版按亮度百分位插值重铺，💢 的红整片变淡粉。实测红占 79.6% 像素、p2=24/p98=78
   ⇒ t=0.96 被映到白。改成**按亮度聚类**后红回来了（主色 `#E0484A` 占 52%）。
2. 新写的反向闸把自己判红了：`strip_prose` 先剥 `#` 再 parse，docstring 里的 `#2C2939`
   截断字符串 → SyntaxError → 回退 → 没剥成。改成先 parse 再用 tokenize 剥。

**位置**：第一版四个全挤在右上角（汗/💢/ZZZ 三个重叠）。按「要能两两并发」重排 ——
汗在左太阳穴、💢 在右太阳穴、暗雲左斜上、ZZZ 右斜上；脚本核过**四个两两零重叠、
全部在画布内**。头顶净空只有 65px，所以斜上角那两个的 v 不能低于 −0.05。

**色卡**：只有 💢 需要暖色，原 16 色全冷色系。按「只补不改」补了一条
`#E0484A 漫符 怒りマーク赤`，理由写进 palette.json 的 note。其余三种全复用既有颜色。

**闸门**：`check_effects_table` 从 10 项扩到 ~20 项，新增漫符组专查（原图在不在 / recolor
梯度 at 递增 / **每一站都必须是色卡上的颜色** / 切件器里不许写死漫符名字和颜色）；
「尺寸档位混用」那条改成只对 ≥3 片的散布型生效（漫符一个符号一张图，本来就该一个大小）。
`rebuild_parts.sh` 接上漫符切件器。

selfcheck **389/0**（工程 332 + 文档 57）、test_core 822、asan 822、smoke 211、web 188，
`make -s check` exit 0（176s）。check_assets **910/0**，色卡闸过。

**还没做**：rig 接线（这批件现在只是躺在 sprites/ 里，画面上还不会出现）= T43.4。
留证 `logs/asset_qa/manpu_placed.png`（贴到真实渲染帧上的位置核对图）。

## 续四十（2026-10-16）澄清「尾巴」的误会 + A49 挂件插槽系统 + 猫尾上身

**先是一场我造成的误会**。上一轮收尾我写「**尾巴**（需真机）：T31.16 改名、T41.4 / T42.3 /
T44.8 本机复验」—— 我拿「尾巴」当「遗留任务」的黑话在用。用户读成了小寻身上的尾巴，
回「意思就是尾巴不能做吗？应该可以做啊」，下一句才点明是「耳饰品，尾饰品，以及服装变化
和装饰品」。写进 LESSONS 152：**在做虚拟角色的项目里，身体部位的词不许拿来当项目管理黑话**。

顺带查出同一句话里的第二个错：我把 **T31.16 和 T44.7 也归进了「需真机」**，可它俩原文
**根本没标 [需真机]** —— 一条纯改名、一条纯接线，沙箱都能做。「把几件事并成一句话说」
最容易顺手给它们安上同一个属性。

**A49 挂件插槽系统**（REQUIREMENTS 入库，ROADMAP 排进第 9 位，TASKS 开 T45.1~T45.8）。
可行性是**查出来的不是估的**：
- `hair_ahoge` 已经是一条完整的悬垂附件（2 段物理链 + 2×4 网格 S 形变器），尾巴照抄即可；
- 层号 0~59 整段空着 —— **那里才是「身体之后」**。（我第一版写进 A49 的「66~94」是错的，
  那段在腿 60~65 **之上**，尾巴放那儿会盖住腿。当轮就改了。）
- `src/core/zimg.h:93` 原文：`BEND_TIP` 顶边固定、越往下位移越大 ——
  「后发、裙摆、**尾巴**这类吊在上面的部件」。**引擎当初就是按尾巴设计的。**

**分两类，成本差一个数量级**：加法类（耳饰/尾饰/装饰品）机器基本现成；
替换类（服装变化）**阻塞于 D19** —— 衣服现在烤在 `seg_torso` / `arm_*` 的像素里，
换件要先重绘被盖住的衬衫和身体，应与 T31 并一个出图批次。唯一不阻塞的是「换色」。

**T45.1 插槽表** `design/attachments.json`：`slots[]`（插槽=位置）+ `attachments[]`（挂件=内容）。
切件器 `tools/make_attach_parts.py` **保长宽比**（漫符那个压成正方，尾巴 1:4 压不得），
键色与色卡重铺直接 import `make_manpu_parts` 不重写。`make_rig.py` 加 `attach_emit()`，
一个挂件字面量都不持有。

**T45.2 猫尾**：成品 131×520，主色 `#D8D8E8`(58%) 和头发同色。物理三段 +
网格形变器。**实测摆动 11.9 帧像素 / 21.6 画布像素**，带阻尼（~0.7s 稳定）。

两次返工都写进教训了：**153** 第一版照抄呆毛系数，C 层三项判定全"是"但摆幅只有自身
长度的 1.3%，渲染出来根本看不见 ——「会动」和「看得出在动」差两个数量级，
判据必须是**相对自身尺寸的比例**而不是"非零"。
**154** 形变器读数恒为 0，差点去改实现；先拿呆毛做负控发现**也是 0** ⇒ 坏的是测量方法
（该用 `zrig_deform_amount()` 不是 `zrig_part_channel(...,"amount")`）。

闸门：selfcheck **389/0**、test_core 822、asan 822、smoke 211、web 188，`make -s check` exit 0（206s）。
新参数 `ParamAccTailCat` 已同时登记 `selfcheck_repo.py` 扩展表与 `LIVE2D_CONFORMANCE.md`。
留证 `logs/asset_qa/tail_on.png`。

## 续四十一（2026-10-16）服装三档 —— 机制早就有，缺的是素材

用户「服装三档都做，继续下一步」。

**先查后做，结果省了一整套轮子**：`zrig_apply_outfit()` / `zpet_set_outfit()` /
`/api/outfit?id=` / 调试台按钮（`web/test.js:185`）**全都在**，`outfits/default.json` 也在。
三档缺的从来只是素材。（LESSONS 155：别把"角色没启用"当成"引擎没有"。
我还是在读 `zrig.c` 的**错误分支文案**「服装素材解码失败」时才发现它的。）

**官方调研**（REFERENCE_NOTES 第三十批）。Cubism 2《モデルの切り替え方式の検討》
是一张现成的决策表，和我开的三档正好对上：moc 切替 = 整套（官方说"服替え一般用这个"）、
パーツα = 换件（官方说"腕替え用这个"）、テクスチャ方式 = 换色（官方原话"色変更などが簡単にできる"）。
而《アバターモデル》那页直接写明「**服と肌が一つの描画オブジェクトですと、
まとめて色変更されてしまいます**」—— 正是我们的处境。

**我更正了上一轮一个错判**：我说过"换件阻塞于 D19，要先重绘被盖住的身体"。
**前提错了** —— D19 只在要**拆开**现有衣服、露出底下时成立；而换装是**整件替换贴图**，
AI 直接画一张完整的"穿着新衣服的躯干"，没有"被盖住的部分"需要重绘。三档都不阻塞。

**实测定了分工口径**（不是拍脑袋）：`seg_torso` 里外套白被最近邻判成「袜」(22.5%)、
「外套主体」连前六都没进；`seg_leg_l` 的**腿部皮肤**被判成「衬衫」(34.4%)
⇒ 按颜色分不开，程序化换色会染到皮肤。而 `arm_l_upper` = 80.2% 袖青 + 11.1% 袖口青
+ **0 个皮肤像素** ⇒ 安全。所以：**单一衣物的件程序化保明暗平移，多衣物纠缠的件 AI 整张重绘。**

**交付**：`design/wardrobe.json` + `tools/make_wardrobe.py` + 两套新衣服。
- **midnight（夜航）** = 换色档：外套白→深蓝、滚边→米、衬衫→浅粉、裙→酒红，
  袜条纹与鞋程序化跟成藕紫。IoU 0.977。
- **cocoa（可可）** = 换件档：棒球夹克→奶油粗针织开衫、衬衫→焦糖高领、百褶裙→棕灯芯绒。
  **这是真换衣服不是改色。**
- `outfits/default.json` 改成**从 rig 现状自动生成** —— 它烂过一次（还在引用上一代
  单图层 rig 的 `body_full.png`，换装换不回原装）。手写清单一定会和生成物脱节。

**三个教训**：155 先查引擎；**156 判据选错了**（换件卡 IoU 是错的，外长 12% 是开衫
本来就厚，该卡的是内缩 —— 闸判红时先怀疑三分钟前拍的判据，别先怀疑跑了很久的东西）；
**157 抗锯齿边从两头骗过键色判据**（既不算洞、又被当成填充来源，补了三次才干净，
残留 501→35）。

**验收**：往返换装干净 —— 原装 vs 换回原装平均像素差 4.8，而同一套衣服隔 1.2s 的
基线抖动是 4.3（做了基线对照才敢说"干净"）。预览零报错。
selfcheck **391/0**、test_core 822、asan 822、smoke 211、web 188，`make -s check` exit 0。
留证 `logs/asset_qa/wardrobe.png`。

## 续四十二（2026-10-16）猫尾返工：用户打回，查教程重做

用户看了第一版尾巴，原话：「**不够精致生动，并且画风都不一样，这个尾巴只是测试还是什么？
尾巴要有自然摆动，而且太粗了，位置也不对，这个是什么动物的尾巴**」「**live2d有教程吧。
做参考别这样乱作了**」。

**四条全中，而且我一条都没自查出来。** 我上一轮的验收全是机制指标（IoU、摆幅、重叠、
闸门 910/0），**一条美术指标都没有**（LESSONS 158）。提示词写的是 cat、出来的是
husky，我自己没看出来。

### 查了教程（REFERENCE_NOTES 第三十一批）

多段振り子（伊糖だねこ）、9 段分割且梢比根快（はるひ）、変形パス 4~5 点（もいもい）、
XY 分两条摆（朝sin）、獣耳三层形变器且耳根不许动（vtuberkaibougaku）。

**★ 其中一条不能照搬，这是本轮最有价值的发现**：社区标准配方是「把**呼吸**加进尻尾
物理演算的**输入**，尻尾就会常にゆらゆら」。我照做了，**实测只摆 0.3 帧像素**。
查 `zrig.c:3013` 才明白：**官方物理输出的是摆角，我们输出的是滞后量 `pos − target`**。
呼吸只有 0.28Hz，摆锤完全跟得上 ⇒ 差值≈0。改成动作通道的慢正弦（0.21Hz）驱动一条
`ParamAccTailSwing`、物理在其上叠二次滞后之后，实测 **6.2 帧像素 / 11.3 画布像素**，
波形是干净正弦。差异已写进 `LIVE2D_CONFORMANCE.md`。

### 画风：我把"有色卡"误读成"平涂"，毒害了三次出图

三版提示词我都写「纯平涂 / 两个色阶 / 不许渐变 / 深色硬描边」。用户说「还是太像简笔画了」
之后才去量 —— `hair_front` **4762 色**、`seg_torso` **25828 色**，**她根本是柔和渐变厚涂**。
色卡只是主色参考，不是渲染方式（LESSONS 159）。

连带推翻了一条自己的口径：**DC55「AI 出图须按色卡重铺」只适用于漫符那类平面符号**。
挂件要和身体长在一起，强行重铺 = 把渐变压成几个平色 = 用户说的「画风都不一样」。
`make_attach_parts.py` 的 `recolor` 改成可选。

### 保留渐变带出的抠图问题（LESSONS 160）

不重铺就得自己处理抗锯齿边，残留闸报 852 px 紫边。补了两轮都压不干净，主色还被洗成
淡粉、覆盖率掉到 33%。根因是 **alpha 估计器选错**：`key_alpha` 的欧氏距离法对柔边
**系统性高估**（30% 白压洋红，距离法给 0.57，真值 0.30）。洋红底有解析解 ——
背景 G=0，`a = 1 − ((R+B)/2 − G)/255`，代回正好 0.30。换完主色 `#F8F9FA`，紫边消失。

### 成品

素材 836→864×1821 洋红底、成品 124×560，**7275 色渐变保住**，银紫基底渐变到青蓝梢
（和她发梢同源）。静止自主摆动 6.2 帧像素。`make -s check` exit 0，selfcheck 391/0。
留证 `logs/asset_qa/tail_v3.png`。

**动物定了猫**，理由写在 TASKS T45.3：尾巴词汇量最大（竖起/慢摇/快拍/炸毛），
桌宠的尾巴是情绪显示器，这一条压倒其他候选。

## 续四十三（2026-10-16）猫尾第三次返工：查猫，不只查 Live2D

用户附真猫照片打回：「**猫尾巴不是这样的吗？为什么尾巴的尾部这么尖，很乖吗，
而且很难看。猫的尾巴可以自由的摇晃、操控，做出情绪的表达，有炸毛，有立起尾巴，
有自然摇晃，有生气的摇晃等等等等。以及耳朵会抖动等**」。

**两个错，根子是同一个**（LESSONS 161）：我查了三批 Live2D 教程（怎么绑物理、
怎么分段、怎么接呼吸），**一次都没查过猫尾本身**。
1. 形状做成**锥形尖梢** —— 真猫尾通体近等粗、梢部钝圆，粗细约长度的 1/7。
   锥形尖梢是蜥蜴和老鼠的尾巴。
2. 把尾巴理解成「一个会晃的装饰」—— 它其实是**一套离散姿态语言**。
   讽刺的是我选猫的理由就写着「尾巴是情绪显示器」，**写进去了却没按它做**。

### 查了猫（REFERENCE_NOTES 第三十二批）

8~10 种尾巴姿态，多来源一致：竖起=自信打招呼、问号钩=邀请玩、尖端颤=极度兴奋、
慢大摇=锁定猎物、快甩拍地=烦躁到愤怒、炸毛=惊吓、夹紧=恐惧。
**一条反直觉的**：「猫摇尾必定是发怒也不对，猫摇尾巴大多时间表达的是**矛盾、左右为难**，
一旦它拿定主意，尾巴便立即停止摇摆」—— 和狗相反，差点做反。
耳朵同理：直立=快乐/警觉、**飞机耳**=害怕或生气、往前倾=好奇（留给 T45.3）。

### 实现

三种轮廓差太远（炸毛宽度是常态 3 倍），**几何变形做不出来**，走官方パーツα方式 =
我们的 `rig.poses` 互斥组。三张新素材（relaxed / up / puff），一个 `tail_pose` 组，
`/api/pose?group=tail_pose&id=...` 切换，fade 0.28。

每种姿态的摆动按行为学分开：放松 0.21Hz/±3.2°（慢而大）、竖起 0.55Hz/±3.2°
（兴奋是尖端颤不是大摆）、炸毛 1.35Hz/±1.3°（僵直发抖）。

**静态外倾用 bias 实现**（LESSONS 162）：竖起的尾巴笔直向上会被外套挡住、像从腋下
长出来。part 没有静态 `rot_deg` 字段，但动作通道本来就有 `bias` ——
`rot_deg = root_rot_deg × (bias + amp·sin)`，一条参数同时给静态倾角和摆幅。
竖起 `20° × (−0.78 ± 0.16)`。**想加字段之前先看现有动态通道有没有直流分量。**

### 连带

- `ZRIG_MAX_PHYS` **24 → 48**：三姿态各 3 段摆链 = 9 条，直接顶到 23/24 = 96%。
- 姿态件层号错开 30/31/32：互斥组里只有一个会露面，但「层号不重复」那道闸不认识
  姿态组，而且让它认识不划算 —— 真有两件同层同时亮就是 bug。
- make_rig 支持挂件覆盖 `anchor` / `curve` / `layer`：同一个槽里，垂下的尾根在顶边
  （curve=tip），竖起的尾根在底边（curve=root），必须反过来。
- 进了姿态组的挂件**不再发**单独的开关参数（显隐归组管，`id=none` 整组关掉）。

`make -s check` exit 0，selfcheck 391/0。留证 `logs/asset_qa/tail_poses.png`。

**还没做**：`mood_pose` / `mood_swing` 两张表已经写进 `attachments.json` 并带了依据，
但**还没接到引擎** —— 现在只能手动 `/api/pose` 切，情绪变了尾巴不会自己变。归 T45.2d。

## 续四十四（2026-10-16）尾巴尺寸校准 + T45.2d 情绪接线

用户：「可以，但是尾巴是不是太大了？还是说这样就合适了？或者是有其他的形态？」

**两层判断错**（LESSONS 163）：① 他看到的是**炸毛**姿态 —— 我上一轮测试循环切到 puff
就停在那儿没复位，他以为那是常态。**测试改了全局状态要复位。**
② 真正太粗的是**默认那根**：笔画 86px = 前臂(62px)的 **1.39 倍**，而真猫尾粗细≈前肢粗细。
炸毛只是在过粗的底子上再粗 1.29 倍才显夸张 —— 按比例算其实**炸得不够**（真猫是 3 倍）。

**拿身上的部件当尺**：relaxed 调到 63px = **1.02×前臂**、长 378 = 躯干+头(630)的 **0.60**，
两个数都落在真猫比例上。炸毛保持，现在是常态的 1.76 倍（动漫惯例 2 倍左右）。

### T45.2d 情绪 → 姿态（本轮主交付）

照 `blink.mood_rate`（T44.2）的样子做：`zpose` 加 `mood_map[]`、`load_poses()` 解析
`poses[].mood_map`、新增 `zrig_pose_apply_mood()`，在 `zpet_express()` 里紧跟
`zrig_blink_set_mood` 调用 —— 同样放在 `match_rule` 之前，且与「有没有对应动作规则」无关
（think 这种没动作的情绪照样该换尾巴）。

**一条口径**：查不到的情绪**不动当前档位**，不是回默认。没写 = 这个情绪跟这个部位无关，
而不是"要把它复位"。

实测七种情绪走 `/api/express?mood=`，尾巴全部按表自动切：
neutral/angry/sleepy → relaxed，happy/affection/cute → up，surprise → puff。

`make -s check` exit 0，selfcheck 391/0。留证 `logs/asset_qa/tail_mood.png`。
