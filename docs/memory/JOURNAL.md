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
