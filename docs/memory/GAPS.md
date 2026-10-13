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
| ~~G1 (T9.1)~~ | ✅ 2026-10-13 **主工作区骨架**：界面从"写死在 index.html 里的一堆卡片 + 380 行全局 app.js"改成**配置装配**。`web/layout.json` 是唯一装配表（区域 / 顺序 / 每个组件的参数），内核 `web/app.js` 按它**动态加载** `components/<id>.js` 并挂载；组件只认一个宿主门面 `host`（照搬 VPet 的 `IMainWindow`：`api/on/emit/state/el/card/refresh/components/find/theme`），生命周期四个钩子 `mount/onInfo/onSpeech/destroy`；主题 `themes/<id>.json` 是一张 CSS 变量表，写进 `:root`。九个组件：stage / statuschips / actions / moods / appearance / voice / usage / settings / statusbar。**业务逻辑原样搬移，没有重写**，内核里只剩一处 `getElementById`（查区域容器） | 闸门：**新增 `tests/test_web.js`（node + DOM stub，39 项）** 真正挂载全部组件并断言 DOM/区域/顺序/请求 URL/点击坐标换算；selfcheck 新增 ⑰ 组 7 项（layout 引用完整性、组件文件 id 对得上、区域容器存在、主题变量齐平、内核不写死元素）；smoke 新增 4 项（layout/组件脚本/主题文件都能下载、不存在的组件要 404）。`make check` 加挂 `web-test` | 验收实测：把 `side` 倒序 + `usage` 挪到顶栏 + 删掉 `voice`，**一行代码没动**，顺序/区域/挂载三条断言全过。负控：删掉一个组件文件 → selfcheck 与 web-test 同时判红 |
| G2 (T9.2) | **本地 API 网关**：Key 只存本机、统一转发、计量、限流、离线降级 | 多模型对话的前提；Key 安全红线 | 假服务器契约测试 [测试锁] |
| G3 (T9.3) | **Token 计费与用量看板**：价目表、按功能分类、预算告警、导出 | 用户点名要"用量记录" | 一次调用落一条账 |
| G4 | **人物素材重做**：小寻 4 形态（设计图→拆件→rig→表情集） | 现在是单图层，表情/口型全是占位 | 机器验收通过率 100% |
| ~~G4a~~ | ✅ 2026-10-11 前置工具已完成：`tools/make_anchors.py`（锚点标注）、`tools/check_assets.py`（形状/色卡/对位验收，已接入自检第 4 步） | — | 当前素材 53 项检查全过 |
| ~~G4b~~ | ✅ 2026-10-11 **身体分段跑通**：`tools/make_body_parts.py` 把单图层切成 头/躯干/双臂/双腿 6 件（关节留 38px 重叠带 + 颈部脖子桩），`make_rig.py` 自动生成 7 组分段骨架并恢复转头，引擎新增 `bend_follow_at`（整块挂关节的部件按关节点取样） | — | 90 项验收全过：无损切分 0 像素丢失；头-15°/臂±10° 压力姿势关节新增空洞 ≤0 |
| ~~G4d~~ | ✅ 2026-10-12 **引擎遮罩（clipping mask）**：`parts[].mask` / `mask_only`，`zimg_composite_masked()`；加载期校验层序与"遮罩夹层"，遮罩被隐藏时被裁切件一起消失 | — | 单测 5 项（正例+层序反例+找不到+眨眼联动）。**注：层序/夹层两条限制已在 A9（2026-10-13）取消**，遮罩改为按需当场渲染 |
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
| G4r ✅ | ~~**闭眼是几何假造**~~（2026-10-12 修完：AI 重绘闭眼脸 → 脸部 NCC 0.684 配准 → 软椭圆补片，盖住原画眼睛 99.5%/99.7%、接缝色差 4.5/2.3，rig 用 eye_open↔eye_closed 交叉淡化）原问题：（用户 2026-10-12 实拍指出"开心的闭眼错位"）：`make_eyelid_parts.py` 画的是"肤色贴片 + 一条线"，半闭时是一块黑、全闭时是一张比周围亮的圆饼，和脸的明暗/形状都对不上 | 眨眼、开心、困倦全都露馅 | 按 D19 出一张「同一张脸、眼睛闭上」的 AI 重绘，按虹膜/轮廓配准后切出真正的闭眼件（上睑+睫毛线），4 倍放大看不出补丁 |
| G4s ✅ | ~~**张嘴是一个深色椭圆**~~（2026-10-12 修完：AI 重绘张嘴脸 → 虹膜配准 NCC 0.925 → 原分辨率取嘴洞 → 24×22 口内，牙 18px/舌 183px，`motion_from` 让口内跟着压扁）原问题：（用户 2026-10-12 指出"惊讶的嘴巴位置错误，形状也很怪"）：`mouth_mask` 只是把一个椭圆按 sy 拉高，口内没有上颚/牙/舌，位置也偏下 | 惊讶/说话/开心全都是一块黑斑 | 按 D19 出一张「同一张脸、嘴张开」的 AI 重绘，配准后切出 `mouth_open_art`（含口内结构），开口度用两张图交叉淡化 + 遮罩，而不是拉伸椭圆 |
| ~~G4n~~ | ✅ 2026-10-13 **侧发两缕 + 后发拆件**（D19 重绘型，`tools/make_sidehair_parts.py`，`rebuild_parts.sh` 第 12/13 步）：① AI 重绘「无侧发的脸」（提示词必须写具体发型名 BOWL-CUT + 硬边界，写 remove/tuck 无效）→ 虹膜相似变换 scale 0.7701 对齐；② 脸掩码 `fill_holes(largest(dilate(暖色,3),种子) | 虹膜圆∪嘴框)`（**不能用闭运算**，会把发丝连成脸）；③ 切出 `hair_side_l` 106×132/层245、`hair_side_r` 105×132/层246、`hair_back` 241×143/**层170（画在脸底下）**；④ 根部留 16 行重复像素藏切口、后发往脸底下铺 14px 塗り足し（**先挖再算区域**）；⑤ 头/躯干重叠带里的发梢在 `seg_torso` 上**只换颜色不动 alpha**（直接挖会多出 72 个窟窿）；⑥ rig 接 `ParamHairSide`/`ParamHairSideS`/`ParamHairBack` + 形变器 `side_l/r_s` + **两段摆链** `side_?_x → side_?_tip(deformer)` 与慢摆 `back_x` | — | **素材验收 322 项 0 不通过**（部件 36/物理 9/形变器 3；新增「头发摆动不露底」「无键色垃圾像素」两类闸）；静止合成 **少 0 多 48 像素**（共同区 248124，均差 0.08）；`make test` 393/0；证据 `logs/asset_qa/_hair_param_zoom.jpg`、`_cheek_zoom.jpg`、`_dyn_hammered.jpg` |
| ~~G4m~~ | ~~**眼线二次拆件**：脸上 `seg_head` 仍画着整圈眼线~~ **已完成 2026-10-13**：`make_eyeline_parts.py` 把「眼眶开口 ∪ 上眼线」换成干净眼窝皮肤（皮肤源 = 抹掉线的闭眼补片，按列上下插值填），引擎加 `eye_aperture` 标签按 `blink` 压扁眼眶、上眼线改 `eyelid` 实测行程下滑，淡化曲线改成两头让开的门控斜坡 | 见 `docs/ART_PARTS.md` 5.11 | ✅ `check_assets` 新闸 0 残留（负例 553+329 变红）、`test_eye_aperture` 1281→980→667→0、`eye_blink_sheet.jpg` 五态无灰幽灵 |
| ~~G4c~~ | ✅ 2026-10-12 **手臂拆件（真关节）**：`tools/make_arm_parts.py` —— ① AI 重绘「无手臂躯干」→ **各向异性四参数配准**（sx .470 / sy .480 / 平移 5,240；单一等比变换残差 31px 不可用）+ 逐通道配色（误差 12.13）→ `design/redraw/torso_noarms.png`；② 沿袖缝切（青色 flood + 多段逐行跟随 + 补到轮廓）而不是切直线；③ 肘部切两件、24px 重叠带**只让前臂淡入**；④ 躯干挖 40713px、补绘 73px、切口塗り足し 5 圈渐隐；⑤ rig 建 `forearm_l/r` 子组（父=`arm_l/r`，枢轴=肘 553），动作里 `bend_x` 按 1°≈6.0px 换算成 `rot_deg`，新增 `ParamArmLB/RB`，挥手改成上臂 −52°+前臂 −28°±15°@2.2Hz | — | **231 项素材验收全过**（含新项「关节不露底(肘)」）；无损切分 **0 像素**；压力姿势 25°/20° 肩肘各 **0** 新增空洞；角度扫描 25→0、40→2、52→3、70→2、90→147（≤70° 安全）；303 单测 / 46 冒烟全过；证据 `logs/asset_qa/g4c_{align_check,arm_mask_check,static_diff,arm_pose_strip,wave_strip}` |
| ~~G4c2~~ | ✅ 2026-10-13 **手腕拆件 + 裙下大腿**（见 `docs/ART_PARTS.md` 5.12）：① `make_arm_parts.py` 四件臂 → **六件臂**，腕线在**手臂掩码内**从肘往下扫肤色得 `wrist_y=666`（`anchors.json` 的比例值 708 落在指尖、整列扫被裙腿干扰得 732，都不能用）；手件画在前臂**底下**（层 138/139），前臂切到 `wrist_y+1`，手带 `WRIST_STUB=10` 皮肤续出且按 `erode(前臂掩码, WRIST_STUB_IN=4)` **往里缩**（贴边补会在 ±20° 探出"飘肉"）；② **真根因不是腿画短了，是躯干扛着大腿**——`seg_torso` 原先切到 776，裙下那截大腿是画在躯干上的静止副本；改为逐列扫 `thigh_top`（两腿间空档列必须回填）、整条大腿归腿件、躯干按同线裁 148375px、删掉腿件上缘渐隐；③ **腿绕髋旋转实测否决**（裆侧撕口 109~252px，补画只能长在裙摆下沿之上、缺口却在下沿之下）→ 改 **bend（curve `tip`）±20px**，实测 0 露底；④ rig：`ParamHandL/R` ±22°、`ParamLegL/R` bend ±20px、5 个动作接手通道 / 4 个接腿通道、`wave` 用手腕甩两通道；physics 加 `hand_?_lag`（鞭子第三节） | **验收超标达成**：手腕安全 ≤40°（扫描 10°:6 / 20°:21 / 30°:38 / 40°:49 / 50°:105 → 现用 ±22°）；腿不是"抬 15°"而是 bend ±20px 新露底 **0 像素** | `check_assets` **358/0**（新增腕专用闸 + 裙摆接缝闸 + `ParamLegL/R` 必须 tip 曲线）；`make test` **404/0**（新增 `test_group_chain` 三级组链）；smoke 64/0；证据 `logs/asset_qa/_wave_hand_sheet.jpg`、`_wrist_stub_cmp.jpg`、`_thigh_gapmap.jpg`、`_g4c2_param_sheet.jpg` |
| ~~G36~~ | ✅ 2026-10-13 **Live2D 协议合规**（用户问"小寻是否合格、尽量往 Live2D 标准走"）：拉官方 `CubismWebFramework/src/cubismdefaultparameterid.ts`（41 个标准参数）与 `Haru.model3/physics3/pose3.json` 逐条核对，补齐 **ParamEyeLOpen/ParamEyeROpen 左右眼分家**（引擎加 `eye_side`，部件按眼别取闭合度）、`ParamBlush → ParamCheek` 正名（留别名）、新增 `ParamBodyAngleY / ParamShoulderY / ParamBaseX / ParamBaseY / ParamBrowLX / ParamBrowRX / ParamHairFluffy`；新增 `param_groups`（= model3 的 Groups，EyeBlink / LipSync）且**真的管用**（自动眨眼只眨组里列的眼、口型只写组里声明的参数）；动作通道现在可以 `target:"ParamXxx"`（≈ motion3 曲线写参数，参数表因此必须在动作之前加载） | 现状：标准参数 **✅34 / ⬜5（缺素材：笑眼·眉形·瞳形）/ ➖4（角色无该部件）**；physics 仍是部件级而非参数级（功能等价，属"随时能补"） | `docs/LIVE2D_CONFORMANCE.md`（含风险分级）；闸门：selfcheck **56 项**（命名/范围/分组/eye_side/文档覆盖）、`test_live2d_standard` 逐参数推极值比像素（负控：binds 清空 → 红）、smoke **68 项**（含单眼眨眼）；证据 `logs/asset_qa/_l2d_param_sheet.jpg` |
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
| A5 (T12.6，原记作 G15) | ✅ 2026-10-12 **部件内细分网格**（`zimg_draw_mesh` + rig `deformers`，呆毛 2×4 控制点能摆 S 形，单测 14 项 / 冒烟 1 项）；遮罩侧已于 A9 补齐（逐像素裁切 + 多遮罩并集 + 取反 + 跟随形变；Live2D 的 clipping 本身也是光栅级，差别只剩"我们用整张画布缓冲、它用 256×256 分块"这一条性能细节） | Live2D 相比我们唯一真正缺的两项 |
| ~~G16~~ | ✅ 2026-10-13 **多段物理摆链**：`physics[].driver` 可写**前面已声明的另一条 physics id**（输入=上一段这一帧的输出），输出可用 `"deformer":"<id>"` 直接写进网格形变器的 amount。示范链：头动 → `ahoge_x`（发根 bend_x）→ `ahoge_tip`（梢，stiffness 26/damping 3.4）→ `ahoge_s` 形变器 S 形。调试口 `zrig_phys_output()`。**侧发已于 2026-10-13 接上两段摆链**（G4n）；仍缺裙摆（等拆件） | 单测 7 项、静态自检 1 项 |
| ~~A9~~ | ✅ 2026-10-13 **遮罩升级**：遮罩改为**按需当场渲染**（`build_maskbuf` + 抽出的 `compute_draw_state/draw_state`），因此 ① 支持 `"mask":["a","b"]` 多遮罩**并集**（≤4）、② 支持 `"mask_invert":true` 取反遮罩、③ **取消**"遮罩必须和被裁件图层相邻 / layer 更小"的限制（这条限制上一轮真的绊过一次）；新增"遮罩源自己不能再挂遮罩"的校验。遮罩按当前帧形变渲染，与被裁件同步 | 单测 8 项（总 393）、静态自检加严、asan 0 报错 |
| ~~A8~~ | ✅ 2026-10-13 **Pose 互斥部件组**（≈ pose3.json）：rig 顶层 `poses[{id,fade,default,entries:[{id,parts[]}]}]`，同组只有一个档位可见、定长线性淡化、`none` 可整组关掉；加载期四条校验（部件存在／一个部件只能归一档／default 在档位里／至少两档）。示范组 `eye_hl_style`（圆形/星形/无），测试台有差分按钮，`/api/pose?group=&id=`，冻结时钟时自动 `zrig_pose_snap` | 单测 17 项、静态自检 1 项、冒烟 5 项；证据 `logs/asset_qa/a8_pose.jpg` |
| ~~A7~~ | ✅ 2026-10-13 **混合模式**（≈ CubismBlendMode）：部件 `"blend":"add"\|"multiply"`，公式与 Live2D 一致且**不改目标 alpha**；能和遮罩叠用（`zimg_composite_masked_blend`）。新零件：腮红 blush_l/r（乘算）、眼高光 eye_hl_l/r（加算，跟 gaze、被眼眶裁、闭眼淡出），由 `tools/make_blend_parts.py` 程序化画出。新参数 `ParamBlush` / `ParamEyeSparkle`（bind 新增 `offset` 字段）。附带新端点 `/api/pause` 冻结时钟 | 单测 9 项、静态自检 1 项、冒烟 5 项；证据 `logs/asset_qa/a7_blend.jpg` |
| ~~A6~~ | ✅ 2026-10-13 **关键帧动作曲线**（≈ `.motion3.json`）：通道写 `"keys":[[t,v],…]` + `"interp":"linear\|smooth\|step"`，取代只能做对称周期的参数化波形；循环动作对末帧时间取模回绕，一次性动作保持末值；时间倒退/帧格式错/超 1024 帧池直接加载失败。示范动作 `nod`（0.18s 低头 9° → 停 → 抬起过冲 −2.5°） | 单测 7 项、静态自检 1 项、冒烟 3 项；证据 `logs/asset_qa/a6_nod_keys.jpg` |
| ~~A1~~（原记作 G18） | ✅ 2026-10-12 **命名参数层**：rig.json 顶层 `params[]`（id/label/min/max/default + binds 到组或部件通道，`通道值 = 参数值 × scale`）+ 引擎内建 5 个（ParamAngleX/Y、ParamEyeOpen〔含 L/R 别名〕、ParamEyeBallX/Y，路由到跟随/眨眼/眼球）+ `/api/params.json`、`/api/param?id=&v=|reset=1|all=1`；测试台的滑条按参数表**自动生成**，角色加参数不用改前端。小寻 teen 现有 14 个角色参数（ParamAngleZ/BodyAngleX/Z/Breath/MouthOpenY/MouthForm/Brow×4/ArmLA/ArmRA/HairFront/HairAhoge） | — | 单测 `test_params` 17 项（总 **281**）；冒烟 40 项全过；实测 ParamArmRA −10/0/+10 → 右臂外缘 606/644/681px；对照图 `logs/asset_qa/param_sheet.png` |
| ~~A4~~（原记作 G19） | ✅ 2026-10-12 **LipSync**：`tools/make_lipsync.py`（wav→RMS 包络 / 无 wav 时数 MPEG 帧头拿时长 + 台词音节铺节律）→ `voice/lipsync/*.json` → `/api/speak?id=` → 引擎每帧写 `ParamMouthOpenY`，动作里的嘴通道由 `zrig_set_mouth_mute` 让路。38 条台词已生成包络；~~仍缺 I/U/E/O 音素级口型~~ **✅ 2026-10-13 补齐（见 G37）** | 依赖 G5 播放链路 |
| ~~G38~~ | ✅ 2026-10-13 **表情 × 口型的叠加口径**：照官方 `ICubismUpdater` 执行序（EyeBlink 200 / Expression 300 / Drag 400 / Breath 500 / Physics 600 / **LipSync 700** / Pose 800）把口型排在表情之后，「笑着说う」Form 从被抵消的 −0.30 变成 **−0.86**（仍是撅圆）；表情求值重写成 Cubism 的三累加器 `(base+overwrite+additive)×multiply`，补上第三种混合 **multiply**；音素层不再回写基础参数（`viseme_write()` 删除），改为 `param_effective()` 分层合成；`/api/params.json` 每个参数报 `value / expr / effective` 三列，测试台加「表情 × 口型」看板。闸门：单测 2 组（含 3 次负控）、smoke 6 项、selfcheck 9 项 | 查证记录见 `docs/REFERENCE_NOTES.md` 第三批 |
| ~~G39~~ | ✅ 2026-10-13 **用户验收反馈的四个真 bug（测试台实测复现 → 修 → 加闸）**：① **一直闭眼**：`zpet_tick` 的唤醒分支只清了 `sleeping`，没解除睡眠时下的强制闭眼；而且 `zrig_blink_force(r,int)` 当年写成 bool 语义，字段里 −1 表"自动"，调用方写 `force(-1)` 反被当成"闭眼" → 改三态（>0 闭、<=0 取消）+ 新增唯一唤醒入口 `pet_wake()`；② **关掉自动眨眼就全闭眼**：部件淡化判断写成 `blink_enabled && blink>0.001`，关掉自动眨眼后闭眼件不走淡化、以 100% 不透明盖住睁眼件（官方 `CubismEyeBlink` 只写参数、不碰绘制，见 REFERENCE_NOTES 第四批）→ 判据只看闭合度；③ **张嘴了微笑还在**：口型接管权重是恒定的 `vis_mix`，笑着说一整句时 `ParamMouthForm` 全程卡在 0.14 —— 改成 `w = viseme_weight × viseme_activity`（接管力度随本帧口型用力程度缩放），`viseme_weight` 0.8→1.0；④ **说完话嘴角抽一下**：`zrig_viseme_clear()` 是硬切，一帧之内从说话嘴形弹回表情 → 改平滑松口（`vis_weight→0`，形状收干净才释放）+ 新增两档 release（音素间 30/s，整句松口 `ZRIG_VIS_RELEASE_OFF` 8/s）+ 新增 `zrig_viseme_reset()` 给"要立刻清零"的场合 | 闸门：单测 **484/0**（新增 `test_sleep_wake_blink()` 的 3 段含整帧像素闸、`test_expr_viseme_order()` 四条新判据）、smoke **95/0**、selfcheck **83/0**（新增口型接管/松口/眼件淡化 6 项静态闸）；负控四次全部判红后还原 | 证据：`logs/asset_qa/_expr_viseme_sheet.jpg`（四格嘴部特写 + 整句两条曲线）；查证记录 `docs/REFERENCE_NOTES.md` 第四批 |
| ~~G40~~ | ✅ 2026-10-13 **笑眼 `ParamEyeLSmile` / `ParamEyeRSmile`（合规表 ⬜5 → ⬜3）**：先查官方 Haru 的八个 exp3 —— F05 写的是 `ParamEyeLOpen=0(Multiply) + ParamEyeLSmile=1(Add) + 眉 0.32`，再对四篇日文建模教程，口径一致：**笑眼不是另一种睁眼，是另一种闭眼**（谷型 ∪ → 山型 ∩）。于是 AI 重绘「山型笑眼脸」，走闭眼那条同一条流水线 `make_eye_closed_parts.py --variant smile` 切补片（同位同尺寸、覆盖 99.5%/99.7%、接缝色差 4.0/2.2）；引擎加 `eye_smile` 标签 + 两个内建参数，三条规矩：笑眼隐含闭眼（`blink = max(blink, smile)`）、谷型闭眼件按 `1−smile` 让位、笑眼件走同样的最后 25% 淡入斜坡；新增表情 `happy`；`rebuild_parts.sh` 14 步 → 15 步 | 闸门：单测 **504/0**（新增 `test_eye_smile()`，含**合成 rig 结构闸**：三张眼摆开位置逐块数像素）、smoke **101/0**、selfcheck **90/0**、check_assets **372/0**；负控三次全部判红 | 证据 `logs/asset_qa/_eye_smile_sheet.jpg`；查证记录 `docs/REFERENCE_NOTES.md` 第五批 |
| ~~G41~~ | ✅ 2026-10-13 **18 个动作从部件通道迁到参数通道（合规表最后一个结构性偏差 🟠）**：先拉官方源码核实 —— `cubismmotion.ts` 第 38~40 行写死了曲线目标只有 `Model` / `Parameter` / `PartOpacity` 三种，实测 Haru 的 `haru_g_m01.motion3.json` = Parameter 42 + PartOpacity 20 + Model 1，**没有"直接写部件几何"这一类**。迁法不是重写动作，而是按参数 bind 系数反算 `参数振幅 = 几何振幅 ÷ scale`（换算表 `tools/make_rig.py` 的 `GEO2PARAM`，漏登记就报错）；197 条几何通道 → 160 条参数通道。顺带：左右对称通道合一、删掉 24 条"整只眼在脸上平移"的逐件通道（head 组位移本来就带着走，而且新加的笑眼件不在那张手写清单里）、新增 `bias` 直流偏置（官方 CubismBreath 的 offset，让 ParamBreath 这种 0..1 单向参数能用正弦驱动）、补上标准参数 `ParamEyeBallForm`（瞳孔缩放）与扩展参数 `ParamBaseRot`（全身倾斜）| 闸门：单测 **523/0**（新增 `test_action_param_channels()`，含"拿故意写几何通道的合成 rig 反验计数器"）、smoke **107/0**、selfcheck **97/0**、check_assets **372/0**；三次负控（计数器不自增 / 忽略 bias / 静音不管参数通道）全判红 | 回归：18 动作 × 7 时刻逐像素对照，质心位移 ≤5.3px；证据 `logs/asset_qa/_param_channel_ab.jpg`。合规表 ✅36 → **✅37 / ⬜2 / ➖4** |
| ~~G37~~ | ✅ 2026-10-13 **口型音素（母音識別 / T2.1.3）**：`rig.json` 的 `visemes` 表（音素 → `ParamMouthOpenY`×`ParamMouthForm`，官方标准表里没有 ParamMouthA/I/U/E/O，所以不自造参数）+ `viseme_update()` 两档平滑（attack 50/s、release 30/s，学 airi 的 wlipsync vowel driver）+ `/api/viseme` + 包络音素轨（pypinyin 取韵母）。闸门：`test_viseme()` / smoke 10 项 / selfcheck 6 项 | 查证记录见 `docs/REFERENCE_NOTES.md` 第二批 |
| ~~A2~~（原记作 G20） | ✅ 2026-10-12 **表情叠加层**：rig.json 顶层 `expressions[]`（一组参数偏移，mode add/set，自带 fade），`/api/expression?id=|off=1`，info.json 带 `expression` + 表情表，测试台表情按钮自动生成。小寻 teen 现有 6 个：微笑/害羞/生气/难过/吃惊/困倦。表情**不占动作状态机**（能"笑着挥手"） | — | 单测 `test_expression` 17 项（总 **298**）；冒烟 46 项全过；对照图 `logs/asset_qa/expression_sheet.png` |
| ~~A3~~（原记作 G21） | ✅ 2026-10-12 **透け眉**：眉的半透明副本（层 241/242、opacity 0.42）画在刘海之上并用 `mask:"hair_front"` 裁切，只在被刘海挡住处显形；引擎新增 `motion_from` 字段让副本照抄本体的全部通道（动作/参数/表情/形变跟随一起动，不用重写通道） | — | 单测 `test_motion_from` 5 项（总 **303**）；生气/难过/吃惊眉区变化 9880/10231/9885 像素（原来 0）；对照图 `logs/asset_qa/brow_ghost.png` |
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
| ~~Q1~~ | ✅ 2026-10-12 **自检与保险体系**：`tools/selfcheck_repo.py`（41 项静态核对）+ `make asan`（ASan/UBSan，首跑抓出 2 个真内存错）+ 2 万帧长稳单测 + `scripts/precommit.sh` 钩子 + `.github/workflows/ci.yml`；一条命令 `make check` |
| G27 | 性能与长稳（待机 CPU < 2%、24 h 无泄漏；**单进程 2 万帧已过，24h 仍 [需真机]**） |
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

1. **动画底层**：G4q（淡入淡出/物理/跟随）+ G18 参数层 + G20 表情层 + G21 motion_from 已完成；**G4c 手臂真关节已完成**（2026-10-12）→ 只剩 **G19 LipSync**（TTS 包络写 `ParamMouthOpenY`，依赖 G5 播放链路）与 **G15 网格顶点级编辑**；立绘侧 **侧发/后发（G4n）、眼线二次拆件（G4m）、手腕+裙下大腿（G4c2）都已完成（2026-10-13）**，**I/U/E/O 四音素口型（T2.1.3，G37）与表情×口型叠加口径（G38）也已完成（2026-10-13）**，
   下一件 = **笑眼素材 `ParamEyeLSmile`/`ParamEyeRSmile`**（补齐 CONFORMANCE 的 ⬜5），随后 18 个动作从部件通道迁到参数通道、动作 fade 线性→正弦。
2. **素材工具先行**（G4 前置）：锚点标注工具 + 蒙版验收工具，再出设定图。
3. **工作区骨架 G1 + 网关 G2 + 计费 G3**（M2/M3 里程碑）。
4. **训练区 G12**（角色 LoRA 优先，解决素材风格一致的根问题）。
5. 其余按 P1 / P1.5 / P2 顺序推进。
| ~~G42~~ | ✅ 2026-10-13 **动作淡化换官方曲线 + 每个动作自带 FadeOutTime**：淡入原来用自选的 `z_smoothstep`，收尾靠 `W_PULSE` 里硬写的"结束前 0.15 秒"，两处都不是官方口径、而且收尾只管 pulse 一种波形。查 `CubismMath.getEasingSine`（`cubismmath.ts:107`）= `0.5 − 0.5·cos(πt)` 带两端钳位，`cubismmotion.ts:417-430` 用它分别算 `tmpFadeIn` / `tmpFadeOut` 再相乘，`endTime < 0`（循环）不淡出。照此新增 `z_ease_sine()`、动作加 `fade_out` 字段（默认 0.2s），W_PULSE 的后门拆掉。**过程中抓到一个真 bug**：只给"当前动作"加淡出、漏掉 `prev` 分支（正在淡出的旧动作），动作演完那一帧会把 pulse 满值整个闪出来（`ParamArmLA` 0 → 2.667 持续 0.2s）——逐帧回归采样抓到的，眼睛看不出来 | 闸门：单测 **535/0**（新增 `test_action_fade_sine()` 11 项，含"演完后不许有鬼影"）、smoke **109/0**（真实时钟下尾窗实测 中段峰 2.34 → 0.17）、selfcheck **104/0**（新增 ⑭ 组 7 项静态闸，盯调用点防偷偷换回 smoothstep）、check_assets 372/0；三道运行时负控 + 一道静态闸负控全判红 | 回归：18 动作 × 7 时刻，残留差异全部有机制解释（@0.1 是淡入换曲线、head_pat @0.9 是新淡出窗口），`wave` / `surprised` 原有的尾部偏差随鬼影一起消失。证据 `logs/asset_qa/_fade_sine_ab.jpg` |
| ~~G43~~ | ✅ 2026-10-13 **裙摆接摆链**：先翻官方 8 个示例模型的 physics3，发现 Haru 根本没给裙子做物理，**Hiyori 有**「スカート横揺れ/縦揺れ」——裙子不是串成多段，而是**横摆、纵摆两条独立通道**，输入只吃 `ParamBodyAngleX/Y/Z`、一个头部参数都不吃，纵摆比横摆钝。照此配了 `skirt_x` / `skirt_y`。裙子**没有拆成独立部件**：形变器本来就是挂在部件上的网格，`cols=2,rows=10` 让 r=0~5 不动、r=6 当裙腰、r=7~10 是裙身裙底。为此补了 **physics 参数输入**（≈ 官方 Input 数组）——原来只能读驱动组位移，而 `ParamBodyAngleX` 绑的是 `seg_torso.bend_x`，弯曲非仿射、不进组矩阵，读不到 | 闸门：单测 **553/0**（新增 `test_mesh_bend_coexist()` + `test_skirt_physics()` 共 18 项）、smoke **112/0**、selfcheck **112/0**、check_assets 372/0；四道负控全判红（mesh/bend 互斥 / 只认第一张网格 / physics 忽略参数输入 / 让裙摆去吃头部参数） | 证据 `logs/asset_qa/_skirt_ab.jpg`；`/api/info.json` 新增 `deformers` 字段让摆链输出可观测 |
| ~~G43b~~ | ✅ 2026-10-13 **两个渲染 bug（做裙摆时撞出来的）**：① `draw_state` 里网格形变器和 bend 是 `if/else` 互斥，部件一挂形变器 `bend_x/bend_y` 就被整个丢掉——**G16 多段摆链正是"第一段写 bend、第二段写形变器"，第一段一直白写**；② 找形变器的循环 `break` 掉了，同一部件上的第二张网格起静默失效。按 Live2D 变形器嵌套语义改成叠加（新函数 `zimg_draw_mesh_bend_blend`），并在加载时拦住"同部件两张网格尺寸不同" | 实测同一个 rig、旧引擎 vs 新引擎，head_pat/nod/sway 每帧差 7926~10540 像素 | selfcheck 新增 ⑮ 组 7 项静态闸盯死两条退化路径 |
| G44 | ⬜ **physics 输出也参数化**：官方摆链的 Output 是写回一个参数（`ParamSkirt`，Type Angle、Scale 1.434），再由美术把那个参数绑到形变器；我们现在直接写形变器 `amount`，少一层间接，动作/表情就没法手 K 裙摆。纯增量、不影响素材，等真需要"动作里手写裙摆曲线"时再做 | — | 依据见 REFERENCE_NOTES 第八批 |
| ~~G45~~ | ✅ 2026-10-13 **眉形 `ParamBrowLForm` / `ParamBrowRForm`（合规表最后两个 ⬜）**：原记作"缺素材"，实际**不用画新素材**——眉毛是一条横着的细带，`cols=4/rows=2` 的网格就能表达「山なり ↔ しかめ」。官方口径查 `Haru.cdi3.json`（「左眉　変形」）+ Cubism 手册（−1 皱眉 / +1 山形）；社区教程方向互相矛盾，以官方为准。关键约束是**「変形」不许带位置移动**（上下/左右/角度各有参数），落成每列 dy `[+2.3,−1.1,−3.6,−1.1,+2.3]`、净和仅形变量的 0.172。七个表情全部接上（照 Haru 的 exp3，六个表情都在用眉形）。透け眉 ghost 靠 `motion_from` + 形变器同时认 mi/pi 自动跟随 | 闸门：单测 **564/0**（新增 `test_brow_form()` 11 项，含"变化必须全部落在 y200~260 这条眉毛带内"）、selfcheck **118/0**（新增 ⑯ 组 6 项按几何核"变形不带位移"）；三道负控全判红（网格改成整体平移 / 表情不接眉形 / 形变器 bind 不写 amount） | **合规表 ✅37 → ✅39 / ⬜0 / ➖4**：41 项里凡是这个角色适用的全部实现且有闸门。证据 `logs/asset_qa/_brow_form.jpg` |
| 注 | ⚠️ **编号撞号**：`G19` 在本表里出现过两次——"LipSync"那个早已改记作 **A4（✅ 2026-10-12）**，`G19 (T16.2)` 是**通知中心**（未做，需真机）。执行顺序那一节里"只剩 G19 LipSync"是过时表述，LipSync 已完成（`tools/make_lipsync.py` 出 30fps 包络 + 音素序列，39 条台词在库，`viseme_source: pinyin_finals`） | — | 2026-10-13 核对时发现 |
| G50 | **契约与注册表（框架第一块）**：四份契约 —— 能力 `config/capabilities/<id>.json`、供应商 `config/providers/<id>.json`、技能 `skills/<name>/SKILL.md`（Agent Skills 规范）、任务 `data/tasks/<id>.json`。要点是**能力与供应商解耦**：调用方只说"我要一张图"，不说"我要调 OpenAI" | 载入器 + 校验闸门 | P0 |
| G51 | **网关骨架**：路由（按能力挑供应商）+ 用量记账 + 密钥引用（`secret://`，密钥只在本机、不入库）+ 统一代理出口。参考 `songquanpeng/one-api` | — | P0 |
| G52 | **资源区骨架**：`data/workspaces/` 工作区、`data/files/` 文件区（带索引与校验和）、`data/memory/` 记忆区三层（profile / episodic / working）。全部只存本机 | — | P0 |
| G53 | **任务机**：队列 + 状态机（queued/running/waiting_user/done/failed/cancelled）+ 可中断 + 可回放 | — | P0 |
| G54 | chat.completion 打通（OpenAI 兼容协议 + 本地 ollama）+ 聊天框 UI | — | P1 |
| G55 | **余额与用量**：真实记账落 `data/usage.jsonl`，替掉工作台现在的占位用量卡 | — | P1 |
| G56 | skills 装载（Agent Skills 规范）+ 技能面板 | — | P1 |
| G57 | image / video / model3d 能力接入（含本地 ComfyUI） | — | P2 |
| G58 | code.generate + code.execute（沙盒执行，参考 `KroMiose/nekro-agent`） | — | P2 |
| G59 | **MCP 适配器**：`provider.kind = "mcp"`，把 MCP server 的 tools 映射成能力 —— 接一次拿到整个生态（官方 servers ★91210） | — | P2 |
| G60 | 任务分解与子代理（agent 带独立 workspace + 受限能力集） | — | P2 |
| G61 | 记忆区三层 + 向量检索（时间衰减 + 重要度加权） | — | P3 |
| G62 | **思考循环**：内部独白 / 空闲时主动话题 / 引用记忆可回溯 / 失败反思写回 —— 用户说的"真正的思考载入" | — | P3 |
| G63 | 人格层接到立绘：已有的 41 项标准参数 + 7 表情 + 18 动作就是现成的表达通道 | — | P3 |
