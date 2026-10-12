# 缺口与需求清单（GAPS）—— 还缺什么、需要用户给什么

> 本文件回答三个问题：**现在缺什么？谁来补？需要用户提供什么？**
> 规则：补上一项就改状态并写日期，不删行（留痕）。编号与 `TASKS.md` 对齐。
> 配套：`REQUIREMENTS.md`（要什么）、`WORKFLOW.md`（怎么干）、`PRODUCT_PLAN.md` 第四/八节（原始缺口清单）。

更新：2026-10-11 ｜ 分支：`arena/cc642f66-zhuochong`

---

## 一、现在能跑的（基线，别重复造）

| 能力 | 证据 |
| --- | --- |
| C 桌宠本体 | `dist/windows/x86_64/zhuochong.exe`（370 KB，零依赖）[需真机] |
| 立绘引擎（数据驱动） | `src/core/zrig.c` + `characters/xiaoxun/forms/teen/rig.json`（15 动作） |
| **Live2D 式形变** | `zimg_draw_warp`（逐像素平滑，X/Y 各自曲线）+ curve(root/sine/linear/tip)；**idle 常驻呼吸**；动作 breath / sway |
| 交互 | 18 条规则 `config/interactions.json`；摸头/摸脸/锤击/点击/睡眠唤醒 |
| 眨眼与视线 | 五态机（对齐 Cubism）+ 虹膜跟随 |
| 换形态/换装 | `zpet_set_form` / `zpet_set_outfit`（机制就绪，缺素材） |
| Web UI 第一版 | `web/`（12 fps 轮询 `/api/frame.png`，动作/情绪/形态/服装/缩放/语音面板） |
| 预览 API | `/api/info.json`、`/api/action|express|poke|hover|scale|form|outfit|call|idle|quit`、`/media/<path>`（白名单+越界 404/403） |
| 语音 | 云端晓伊标准定案；38 条台词已渲染；本地 Praat 少女化工具链；音色包安装器 |
| 测试 | `make test` 217 项全通过；`scripts/selfcheck_all.sh` 六步全绿 |
| 参考资料 | 七个项目已查验，结论在 `docs/REFERENCE_NOTES.md` |

---

## 二、缺口（我来补，按优先级）

### P0 —— 不做就不算"软件"
| # | 缺什么 | 为什么要 | 验收 |
| --- | --- | --- | --- |
| G1 (T9.1) | **主工作区骨架**：本地 Web + 事件总线 + 主题系统 + 布局配置 + 组件注册表 | 现在只有桌宠预览页，没有"工作台" | 换主题/改布局不改代码 |
| G2 (T9.2) | **本地 API 网关**：Key 只存本机、统一转发、计量、限流、离线降级 | 多模型对话的前提；Key 安全红线 | 假服务器契约测试 [测试锁] |
| G3 (T9.3) | **Token 计费与用量看板**：价目表、按功能分类、预算告警、导出 | 用户点名要"用量记录" | 一次调用落一条账 |
| G4 | **人物素材重做**：小寻 4 形态（设计图→拆件→rig→表情集） | 现在是单图层，表情/口型全是占位 | 机器验收通过率 100% |
| ~~G4a~~ | ✅ 2026-10-11 前置工具已完成：`tools/make_anchors.py`（锚点标注）、`tools/check_assets.py`（形状/色卡/对位验收，已接入自检第 4 步） | — | 当前素材 53 项检查全过 |
| ~~G4b~~ | ✅ 2026-10-11 **身体分段跑通**：`tools/make_body_parts.py` 把单图层切成 头/躯干/双臂/双腿 6 件（关节留 38px 重叠带 + 颈部脖子桩），`make_rig.py` 自动生成 7 组分段骨架并恢复转头，引擎新增 `bend_follow_at`（整块挂关节的部件按关节点取样） | — | 90 项验收全过：无损切分 0 像素丢失；头-15°/臂±10° 压力姿势关节新增空洞 ≤0 |
| ~~G4d~~ | ✅ 2026-10-12 **引擎遮罩（clipping mask）**：`parts[].mask` / `mask_only`，`zimg_composite_masked()`；加载期校验层序与"遮罩夹层"，遮罩被隐藏时被裁切件一起消失 | — | 单测 5 项（正例+层序反例+找不到+眨眼联动） |
| ~~G4e~~ | ✅ 2026-10-12 **眼睛零件化**：`tools/make_eye_parts.py` 拆出 眼眶(遮罩)/眼白底/眼球(补全成完整圆)/眼线 四件 × 左右，`make_rig.py` 自动接线并新增 `look_around` 动作 | — | 146 项素材验收全过；`logs/preview_check/eye_zoom.png` 眼球位移不出眶 |
| ~~G4f~~ | ✅ 2026-10-12 **嘴零件化**：`tools/make_mouth_parts.py` 造出开口形状(遮罩)+口内(上颚/口腔/舌/下唇)，引擎补**分轴缩放** `"scale":[sx,sy]` 与 **flap 波形**；talk/happy/surprised/hammered/sleep 真的张嘴 | — | 160 项素材验收全过；`logs/preview_check/mouth_strip.png` |
| ~~G4h~~ | ✅ 2026-10-12 **呆毛独立**：`tools/make_hair_parts.py` 无损切出 `hair_ahoge`（切线 y=48，根部 12 行渐隐），9 个动作接了摆动通道（curve=root） | — | 无损切分仍 0 像素差；`logs/preview_check/ahoge_strip.png` |
| ~~G4i~~ | ✅ 2026-10-12 **上眼睑拆件**：`tools/make_eyelid_parts.py` 逐列照眼眶下沿描出眼皮（自带闭眼线 + 逐列取肤色），引擎加 `tags:["eyelid"]`+`eyelid_travel` → `extra_dy += blink×travel`、动作可写 `blink_hold`、`zrig_blink_set_manual` 直控；眨眼从"两张图淡化"变成连续开合（能停在半眯眼）。**顺带把层序改了**：眉 232/233、刘海 240（原来 181/182、188 会被眼皮盖住） | — | 单测 `test_eyelid` 7 项；素材 202 项全过；冒烟 34 项全过；实拍 `logs/preview_check/eyelid_strip.png` |
| ~~G4j~~ | ✅ 2026-10-12 **前发分层 + 额头 AI 重绘**：`tools/make_bangs_parts.py` —— 生图重绘无刘海脸 → 按虹膜质心/瞳距解相似变换（scale 0.8555）→ 只回贴被遮的 11773 像素 → 切出 `hair_front.png`(169×169, layer 183)，摆动 `bend_x + curve:tip`。**这是第一件按 D19 走 AI 重绘的零件** | — | 174 项素材验收全过；静止合成仍 0 像素差；证据 `logs/asset_qa/bangs_pipeline.png`、`logs/preview_check/bangs_strip.png` |
| ~~G4k~~ | ✅ 2026-10-12 **眉毛拆件**：`tools/make_brow_parts.py` —— 再生一张「无眉脸」→ 带旋转的相似变换对齐（残差 1.5px）→ alpha 抠像 + 解混切出 `brow_l/r.png`（锚点中心，layer 181/182）→ 9 个动作接 `dy`/`rot_deg`（对应 `ParamBrowLY/RY`、`ParamBrowLAngle/RAngle`） | — | 188 项素材验收全过；静止合成 0 像素差；证据 `logs/asset_qa/brow_check.png`、`logs/preview_check/brow_strip.png` |
| ~~G4l~~ | ✅ 2026-10-12 **修 surprised 的「补丁带」**：老动作把 `sx/sy` 摊给了眼眶/眼白/眼线这些**矩形小块贴图**，一放大就露出方边（脸上横着一条带）。现在缩放只发给眼球（它被眼眶裁切，放大=瞳孔放大） | — | 修前 `logs/preview_check/old_surprised.png`，修后 `logs/preview_check/brow_strip.png` 第二行 |
| ~~G4o~~ | ✅ 2026-10-12 **闭眼没闭严 + 零件切口阶梯**（用户报"毛边、切割感"）：① 眼眶遮罩按颜色 flood，吃不进眼白下缘的淡蓝和外眼角的白 → 眼皮盖不住（眼眶 27×33 → **46×41**）；② 眼皮自画的闭眼线落在遮罩外被切掉 → 线上移 OVERSHOOT；③ 睫毛原来淡出，半闭时先丢上眼线 → 改成跟眼皮一起下滑（`eyelid_travel = 眼皮 − 6` + 挂遮罩）；④ 刘海按二值掩码切，切口是 0/255 阶梯 → 软切口（硬跳变 **100% → 0%**，半透明 0.1% → 11.2%）；⑤ **`rebuild_parts.sh` 原本没有眼睑步骤**，身体一重切眼皮就过期 → 七步改八步 | — | 202 素材 / 244 单测 / 34 冒烟 全过；抓帧 `logs/asset_qa/blink_zoom.png`（0/0.5/1 三档 4 倍） |
| ~~G4p~~ | ✅ 2026-10-12 **抠像"毛边"查证（结论：不动）**：距离斜坡软 matte + 预乘 LANCZOS 缩放 → 白边光晕 61 → **1197**（LANCZOS 负瓣过冲 ÷ 小 alpha 被放大）；换 BOX → 硬跳变 4% → **25%**（缩放比 0.89 时 BOX ≈ 最近邻）。现用的 bleed + 直接 LANCZOS 才是对的 | — | 对比表见 `docs/ART_PARTS.md` 5.7、`docs/memory/LESSONS.md` |
| ~~G4q~~ | ✅ 2026-10-12 **动画底层三块**（用户："动画底层没有做好立绘做完了也没用"）：① **动作淡入淡出** `actions[].fade`（默认 0.22s，0=硬切）—— 旧动作淡出期继续推进时间轴，按 smoothstep 权重与新动作叠加，不再瞬间跳帧；② **物理摆动** rig 顶层 `physics[]` 弹簧阻尼，输入取驱动组**完整矩阵**（含旋转与父链）带动锚点的位移、输出 `clamp(pos-目标,±max)`（静止必收敛回 0）；③ **指针跟随** rig 顶层 `look{}`，`/api/gaze` 同时驱动眼球与头/上身（≈`ParamAngleX/Y/Z`+`ParamBodyAngleX`），`1-exp(-speed·dt)` 平滑。叠加序：动作 → 跟随 → 物理 | — | 单测 `test_motion_fade`/`test_physics`/`test_look` 共 20 项（总 **264**）；实拍 wave→idle 右手外缘 171→157→145 分三帧回落（无淡入应一帧跳 20px）、hammered 呆毛摆幅 5.5px 震荡收敛、转头头部质心 ±25px 且复位残差 0.1px，`logs/asset_qa/look_follow.png` |
| G4m | **眼线二次拆件**：脸上 `seg_head` 仍画着整圈眼线，眼皮只能在眼眶开口内盖，闭眼放大看仍是"眼线圈 + 一块皮肤" | 需要按 D19 给眼窝 AI 重绘皮肤后把眼线切成独立零件 | 闭眼 5 倍看只剩一条眼缝线 |
| G4c | **关节补图**（手臂与躯干相接处、裙摆下的腿、手指）由 AI 重绘，目前只有重叠带兜底 | 手臂只能用 bend 形变（肩钉死）做动作，**整块旋转超过 ~8° 必裂**；没有肘关节，挥手是"橡皮管"式 | 臂可绕肩旋转 25° 无接缝、有肘关节 |
| G5 | **语音链路收尾**：Windows 播放与混音、每日额度、缓存、多音字回归测试 | 现在只有文件，没有播放链路 | [需真机] 能听见 |
| G6 | 配置迁移器 + 诊断包 + 备份恢复 | 版本升级不炸用户数据 | 旧配置能自动升级 |

### P1 —— 决定好不好用
| # | 缺什么 | 备注 |
| --- | --- | --- |
| G7 (T10) | 代理编排：任务队列、工具权限、人工确认、失败回放、预算熔断 | |
| G8 (T10.3) | **Skills 注册表 + 技能测试台**：`skills/<id>/skill.json` | 用户点名"AI 能力可扩展" |
| G9 | 生图区 + "拆件候选"流水线与自动验收 | 和 G4 共用验收工具 |
| G10 | 代码区（执行沙箱 + Git 面板 + 一键自检） | |
| G11 | 工作区 RAG（本地索引 + 引用即插入） | |
| G12 (T15/M0.5) | **训练区**：数据集管理、配方、执行器（本机 GPU / SSH / 云）、模型库、评估、合规闸门 | **角色 LoRA 最先做** |
| G13 | 视频区（ffmpeg 链 + 长任务队列） | 沙箱无 ffmpeg，[需真机] |
| G14 | 桌宠动作扩充：双击/甩动/时间问候/道具/话题 | |
| G15 (T12.6) | **部件内细分网格（多控制点）+ 顶点级遮罩** | Live2D 相比我们唯一真正缺的两项 |
| G16 | 物理：布料/头发/尾巴**多段**钟摆（单段弹簧已在 G4q 做完；缺多段串联 + 裙摆/侧发接线） | |
| ~~G18~~ | ✅ 2026-10-12 **命名参数层**：rig.json 顶层 `params[]`（id/label/min/max/default + binds 到组或部件通道，`通道值 = 参数值 × scale`）+ 引擎内建 5 个（ParamAngleX/Y、ParamEyeOpen〔含 L/R 别名〕、ParamEyeBallX/Y，路由到跟随/眨眼/眼球）+ `/api/params.json`、`/api/param?id=&v=|reset=1|all=1`；测试台的滑条按参数表**自动生成**，角色加参数不用改前端。小寻 teen 现有 14 个角色参数（ParamAngleZ/BodyAngleX/Z/Breath/MouthOpenY/MouthForm/Brow×4/ArmLA/ArmRA/HairFront/HairAhoge） | — | 单测 `test_params` 17 项（总 **281**）；冒烟 40 项全过；实测 ParamArmRA −10/0/+10 → 右臂外缘 606/644/681px；对照图 `logs/asset_qa/param_sheet.png` |
| G19 | **LipSync**：`talk` 现在是固定 flap 波形，没接音频包络；要做「TTS 产出 wav → 取 RMS 包络 → 驱动嘴 open」 | 依赖 G5 播放链路 |
| G20 | **表情叠加层**（expression）：在当前动作之上叠一层持续偏移（脸红/眯眼/鼓腮），和动作互不覆盖 | 现在表情是整条动作，叠不上去 |
| G17 (T16.7) | **歌声**：TTS 唱句 + 音高对齐；SVC 产物按音色包接入 | 用户问过"AI 翻唱"，路线已定 |

### P1.5 —— 第七轮补充的六项（T16）
| # | 缺什么 | 验收 |
| --- | --- | --- |
| G18 (T16.1) | 多用户档案 Profile（会话/记忆/好感/用量隔离） | 切档案数据不串 |
| G19 (T16.2) | 通知中心与系统通知（长任务、额度告警、角色主动说话） | [需真机]；可一键免打扰 |
| G20 (T16.3) | 国际化 i18n（界面 + 台词 `i18n/<lang>.json`） | 换语言不改代码 |
| G21 (T16.4) | 导入导出与迁移（会话/角色/技能/音色打包） | 跨机器导回功能一致 |
| G22 (T16.5) | 定时与自动化（问候、朋友圈、备份） | 到点执行，失败有日志 |
| G23 (T16.6) | 多设备/远程访问（默认关，鉴权 + 加密） | 开启需二次确认 |

### P2 —— 打磨与合规
| # | 缺什么 |
| --- | --- |
| G24 | 无障碍、护眼、勿扰、专注计时 |
| G25 | 技能/主题/音色/模块的导入导出市场化 |
| G26 | 加密与隐私增强（数据库加密、敏感信息扫描） |
| G27 | 性能与长稳（待机 CPU < 2%、24 h 无泄漏） |
| G28 | 第三方许可登记 `docs/LICENSES.md` + 音色合规闸门 |
| G29 | 安装包、自动更新、卸载清理 |

### 小修（随手就能做，别积压）
| # | 缺什么 | 位置 |
| --- | --- | --- |
| ~~G30~~ | ✅ 2026-10-11 已修：`/api/info.json` 增加 `mood`/`affection`/`tier`/`tier_name` | `src/headless/main_headless.c` |
| ~~G31~~ | ✅ 2026-10-11 已修：增加 `form_names`/`outfit_names`，界面显示角色包里写的中文名（新增形态不改前端） | `main_headless.c` + `web/app.js` |
| G32 | `send_png` 用 `/tmp` 固定文件名，同秒并发有碰撞风险 | `src/headless/main_headless.c` |
| ~~G34~~ | ✅ 2026-10-12 **互动/动作测试台**：`web/test.html`（手点：动作/互动/滑杆/零件表/日志 + 一键自动测试）与 `tools/api_smoke.py`（命令行 34 项，判据是"画面真的变了"）；新增 `/api/region`；自检升到 7 步、`make smoke` | `web/test.*`、`tools/api_smoke.py`、`scripts/selfcheck_all.sh` |
| ~~G35~~ | ✅ 2026-10-12 **通话姿态切不过去**：`call_user_speaking → focus`（优先级 2）被正在放的 `talk`（优先级 4）挡掉，表现是"对面说话了，她还在讲话姿势"。`config/interactions.json` 的 call_user/call_reply 两条加 `"force": true` | `config/interactions.json` |
| G33 | 本地 Praat 样音 `local5_praat_1.10/1.20/1.32`（267/284/315 Hz）还没进试听页 21–23 | `characters/xiaoxun/voice/samples/index.html` |

---

## 三、需要用户提供 / 确认的（我做不了的）

| # | 需要什么 | 为什么卡我 | 用户怎么给 |
| --- | --- | --- | --- |
| N1 | **挑本地音色**：试听 `local5_praat_1.10 / 1.20 / 1.32`（267 / 284 / 315 Hz）选一档，或判"仍不行" | 本地兜底音色定不下来 | 听完回一个档位号 |
| N2 | **GPU 机器跑训练**（角色 LoRA / 音色模型 / SVC） | 沙箱无 GPU、无外网大文件 | 在自己机器按 `docs/TRAINING.md` 执行 |
| N3 | **Kokoro / 其它高质量中文女声模型文件** | GitHub 只返 LFS 指针（134 B），沙箱拉不到 | 从 HuggingFace `hexgrad/Kokoro-82M` 下载后用 `tools/voice_packs.py install` 装入 |
| N4 | **中转站选型**（zenmux.ai / crun.ai / easyrouter.io 或其它）+ 测试额度 | 网关与多模型对话没法实测 | 给一个 base_url + 模型名（Key 自己填本机，别发聊天框） |
| N5 | **两套 UI 风格的设计稿确认**（A 柔和手绘 / B Q 版糖果） | 交接要求"先出设计稿再实现" | 看稿后回 A / B / 都要 |
| N6 | **小寻四形态的设定确认**（萝莉 / 青年女性 / Q 版的头身比与差异） | 素材重做要先锁设定 | 回一句比例要求即可 |
| N7 | **真机验收**：透明窗、穿透、托盘、动效观感、音频播放 | 代理不许替用户宣布完成 | 在 Windows 上跑 `dist/windows/x86_64/zhuochong.exe` |
| N8 | 是否删除仓库里的旧交接文件（`docs/HANDOVER_XIAOXUN.md` 等） | 不擅自删旧文件 | 一句"删"或"留" |

**安全红线**：任何 API Key、密码、Token 都**不要发到聊天框**，只写进本机 `.env`（历史上泄露过一次，`.env` 已不入库）。

---

## 四、执行顺序（我接下来按这个走，除非用户改）

1. **动画底层**：G4q 三块 + G18 参数层已完成 → next 是 **G20 表情叠加**（在动作之上叠持续偏移）与 **G19 LipSync**（TTS 包络写 ParamMouthOpenY），再回 G4c 手臂拆件。
2. **素材工具先行**（G4 前置）：锚点标注工具 + 蒙版验收工具，再出设定图。
3. **工作区骨架 G1 + 网关 G2 + 计费 G3**（M2/M3 里程碑）。
4. **训练区 G12**（角色 LoRA 优先，解决素材风格一致的根问题）。
5. 其余按 P1 / P1.5 / P2 顺序推进。
