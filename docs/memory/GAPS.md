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
| ~~G50~~ | ✅ 2026-10-13 **契约与注册表（框架第一块）**：四份契约 —— 能力 `config/capabilities/<id>.json`（15 份）、供应商 `config/providers/<id>.json`（6 份：openai/deepseek/relay_test 网络 + ollama/comfyui/mcp_filesystem 本机）、技能 `skills/<name>/SKILL.md`（**直接采 Agent Skills 规范**，查 super-agent-party 才知道有现成标准，没自造）、任务 `data/tasks/<id>.json`。**能力与供应商解耦**：调用方只说"我要一张图"。校验器 `tools/check_platform.py` 生成 `web/platform.json`。旧的扁平 `config/providers.json` 没删成——C 侧 `zconfig.c` 在读它（路径是拼出来的，grep 文件名查不到，`make check` 才抓到），改成**由校验器从新契约投影生成**，老格式的消费者一行不改而真相只有一份 | 闸门：platform 13/0（`--check` 改成"验证生成物是最新的"）、selfcheck ⑱ 组、web-test 新增 7 项 | 负控六道全判红：声明不存在的能力 / 明文密钥 / 本地供应商声明 api 余额 / 能力 id 与文件名不符 / 改契约不重算投影 / 手改生成物 |
| ~~G51~~ | ✅ 2026-10-13 **网关骨架**：`src/core/zgateway.{c,h}` —— 路由（`zgw_pick`，按能力挑供应商，支持 attempt 降级重试；失败原因分 `NO_SUCH_CAP`/`ALL_DISABLED`/`EXHAUSTED` 三种，因为给用户的指引完全不同）+ 估价（`zgw_estimate`，按量/按次/免费三种口径）+ 三段记账（`zgw_hold_open`→`settle`/`release`，照 one-api `relay/billing` 的预扣-结算-退还；**入账的是实际花费不是预扣额**，失败的请求不扣钱但计失败次数）+ 密钥引用（`zgw_secret_resolve`：`secret://foo-bar` → 环境变量 `ZHUOCHONG_SECRET_FOO_BAR`，**取不到必须失败，绝不返回空串**，装不下要报错不许截断）。路由表不是运行时现算的，是 `tools/check_platform.py` 预先物化成 `config/gateway_routes.json`（照 one-api 的 `Ability` 表做法，**顺序即优先级**，运行时取第一个 enabled 的就是首选）。新端点 **`/api/gateway.json`** 报告每种能力实际路由到谁 + 账本 + 三态 `ready/disabled/missing`；平台面板显示"契约说谁能做"与"网关说现在走谁" | 闸门：test **627/0**（新增 63 项）、smoke **138/0**（新增 19 项）、selfcheck ⑲ 组 9 项、web-test **52/0** | 负控七道全判红：路由不看 enabled / 结算记预扣额 / 密钥失败返回空串 / 退还也扣钱 / 重复结算不拒 / 三态混成"不可用" / 账本不显示花费。**真实 HTTP 调用不在本件内**（那是 G54）——把"选谁/花多少/钥匙在哪"和"怎么发"分开，前者在无网无密钥的机器上就能完整验证 |
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

## G64 云端音色库（2026-10-14 完成主体）

**用户要求**：去掉本地音源；换云端标准音色；要少女/萝莉/青年女性；偏二次元；
能变声调语气和情绪；用户可自己选择和配调；**每个 AI 的声音都不一样，不能同一种生源**。

**已做**：
- 删本地 Piper 全套（`voices/`、`tools/voice_local.py`、`voice_packs.py`、`voice_setup.sh`，9 个文件）。
  删前先 grep 过闸门与 C 源码确认无引用（教训 51 的坑）。
- `config/voicebank/<id>.json` **19 份**音色契约：minimax 8 / azure_speech 9 / edge_tts 2；
  少女 7 / 萝莉 5 / 青年女性 7；二次元向 14。每份带 `emotion_mode` 和可调参数范围。
- `config/voice_cast.json`：角色形态 3 条 + AI 5 条分配，两条硬要求由校验器判红。
- `config/emotion_map.json`：11 种情绪 × 四条通路 + 对应的脸部表情。
- 三份新供应商契约；`tts.speak` 从 missing 变成有供应商。
- `config/voices.json` **降级为生成物**（第四个这么处理的遗留格式），C 侧照常读。
- 面板 `web/components/voicebank.js`：挑音色、调参数、看情绪怎么发。

**还没做（排队）**：
- `tools/voice_render.py` 目前只会 edge-tts，要扩成按 `emotion_mode` 分发的多供应商渲染器。
- 面板上选的音色还存不住（没有写配置的后端接口），重开就回到默认。
- 桌宠 mood 变化时自动切 TTS 情绪，还没接到运行时。
- 试听要真发请求，得等用户配密钥。

## G65 立绘调试台（2026-10-14 完成）

**起因**：用户问"live2 动态立绘做完了吗"，并要求"测试软件先兼容动态立绘功能"。
查下来底层 41 项合规 ✅39/➖4 确实做完了，**但界面只用到 24 个 API 端点里的 9 个** ——
46 个参数、7 个表情、7 个口型、互斥差分、视线、眨眼、暂停，全都没有入口。

**已做**：`web/components/rig.js`
- 动作 18 个（补上 info 里不列出的 idle/sleep）、表情 7 + 取消、口型 7、差分档位 + 整组关
- 开关：暂停动画 / 眨一下 / 视线跟随（在舞台上移鼠标）/ 参数全复位
- 形变器当前量只读显示（光看图分不出裙摆在不在荡）
- 46 个参数按 Live2D 官方前缀分 9 组折叠，滑块实时驱动
- `/api/info.json` 补了 `visemes` / `viseme` / `viseme_weight` 三个字段，
  口型表不再在前端硬编码

**闸**：web-test +27 项、api_smoke +9 项（46 参数逐个设值回读、表情/口型/差分/动作全覆盖）、
selfcheck +1 组（前端参数名与 C 侧 qstr 对照）。

## G66 脸红几乎看不见（2026-10-14 发现，**当天修完**）

`ParamCheek` 满值只带来 27 像素可见变化。接线和方向都是对的
（0→0.25→0.5→0.75→1 对应 0→0→6→16→27 像素，单调递增），所以第一反应是"素材太淡"。

**调浓度治不了，根因是落点**。把 `make_blend_parts.py` 的 `peak` 从 0.62 提到 0.88、
颜色也加重，素材平均 alpha 从 43 升到 63，可见变化只从 27 升到 41 像素 ——
和按 alpha 估算的 ~400 差了十倍，这才反推去查位置。

诊断手法：把像素差阈值降到 4，看 `np.where` 出来的影响区范围，
再读**最大变化点在底图上的 alpha** —— 读到 10（几乎全透明），当场定性。

> 腮红是 `multiply` 混合，**乘算在透明像素上没有任何效果**。
> 原来的落点 `[311,300] 64×34`，而 `seg_head` 在画布 y=300 的实心范围只有 x 345..491
> （脸是上宽下窄的锥形，y=340 时只剩 386..455）—— 92% 的腮红画在空气上。

**修法**：按瞳孔位置重新定位（`eye_l_ball` 中心 x≈384、`eye_r_ball` x≈457），
尺寸收到 40×22 保证整块压在实心脸上。满值可见变化 **27 → 268 像素**，
最大色差 **34 → 167**，最大变化点底图 alpha=255。

**加闸**（`check_assets.py`「混合零件」组）：腮红的不透明像素必须 ≥80% 落在
`seg_head` 的实心区（alpha>200）上。负控：摆回旧位置 → 覆盖率 8%，红。

---

## G67 立绘交互三件套点不到 + 坐标系用错（2026-10-14 发现并修完）

G65 把参数/表情/口型/差分接进了 UI，但 24 个端点里还剩
`hover` / `region` / `speak` 没有任何界面入口 —— 而这三个恰好是"桌宠"区别于
"立绘播放器"的部分：鼠标靠近会看过来、知道你摸的是头还是脚、说话时嘴跟着动。

修完的四件事：

1. **新组件 `web/components/interact.js`**（舞台交互）：视线跟随开关、区域探针
   （实时显示指向哪个区域 / 会触发什么动作 / 改鼠标光标）、手-锤工具切换、
   台词下拉 + 播放停止 + 口型电平条。

2. **`info.json` 补 `regions` 和 `canvas_w/canvas_h`**（C 侧新增
   `zrig_region_id_at/action_at/cursor_at/rect_at` + `zpet_` 转发）。
   不报这张表，前端只能把 `head/body/feet` 和 `848×1360` 写死，
   rig.json 一改区域就对不上 —— 和当初加 `visemes`/`poses` 是同一个理由。

3. **摸头区域漏了下半张脸**。区域 rect 原本由 `prepare_sprites.py` 按比例估
   （头 = 角色高的 24%，还假设头顶贴着 y=0），实际 head 只到画布 y=310，
   而 `seg_head` 占到 y=385 —— **嘴和下巴落在 body 里，点脸触发的是「摸身体」**。
   改成在 `make_rig.py` 里按 seg_head 真实 bbox 校正（head 到 y=391）。
   加闸 `check_assets.py`「交互区域」组：head 区域必须罩住整张脸，负控能红。

4. **坐标系用错（影响面最大的一条）**。`hover/region/poke` 吃的都是
   **引擎帧缓冲坐标**（= 画布 × pet scale = `info.frame_w/h`），
   而 `stage.js` 一直拿 `img.naturalWidth` 换算 —— 那是**画布 × 画质档 s%**，
   两者只在画质档恰好等于 scale 时相等。画质一降或 `/api/scale` 一改就整体点偏。
   两个组件都改成按 `info.frame_w/h` 换算；web-test 的 stub 故意把
   `naturalWidth` 设成 848×1360（和 frame_w 466 不同），用错立刻红。

顺带修掉的状态泄漏：`api_smoke.py` 的 scale 用例跑完把 1.0 留给了后面所有用例
（也留给预览进程），现在跑完还原成启动值。

## G68 形态分区只有 teen，其余形态在界面上凭空消失（2026-10-14 发现并修完）

**现象**：`characters/xiaoxun/forms/` 只有 `teen/`，而 `config/voice_cast.json` 早就给
teen/loli/adult 三个形态配好了音色。界面上形态下拉只有一项，用户看不出"还规划了另外三个"。

**根因**：`scan_forms()` 只认磁盘上有 `rig.json` 的目录（这是对的 —— 空目录切过去会白屏），
但"规划中"这件事没有任何地方记录。而且 **git 不跟踪空目录**，想靠建空文件夹占位是行不通的。

**修法**：加清单文件 `characters/xiaoxun/forms.json` 声明路线图，`status` 只有 `ready`/`planned`。
引擎 `load_form_roadmap()` 在 `read_form_name()` 之后合并，**以磁盘为准**：清单写 ready 但
没有 rig.json 的，照样降级成 planned（防止清单吹牛）。`info.json` 新增 `form_roadmap`，
而 `forms`/`form_names` **继续只含 ready**，不破坏既有调用方。界面上 planned 的形态灰显、
禁用、鼠标悬停显示"还差什么"。

**顺手修掉的小 bug**：`read_form_name()` 从 `rig.json` 的 `name` 字段取形态显示名，
但那里存的是**角色名**（"小寻"）。三个形态都做完的话，下拉里会三项全叫"小寻"。
现在 forms.json 的名字优先，teen 正确显示成"少女"。

**闸**：`selfcheck_repo.py: check_form_roadmap()` 五项 —— ready 必须真有 rig.json /
磁盘上的必须登记 / planned 不许留半拉子素材 / status 只用两种值。三种坏法都做了负控。
`test_web.js` 另有 5 项：planned 不许进切换下拉、但必须在界面上看得见且禁用。

**不要为 planned 的形态造模板素材**：假素材会被 `check_assets.py` 的 375 项逐条检查，
要么全红要么开后门，而且会混进 LoRA 训练数据。空着才是对的。

---

## G69~G78 P4「实时陪玩」缺口（2026-10-14 登记，尚未动工）

用户 2026-10-14 提的四件新能力，拆成 10 个缺口，全部登记在 `docs/PLATFORM_PLAN.md` 第六节 P4。
这里只记**为什么是缺口**，做法见计划文档。

| 编号 | 缺口 | 现状证据 |
|---|---|---|
| G69 | 网关只有 `prefer_local` 一种策略，没有真正的云/本地双路由与降级链 | `config/gateway_routes.json` 的 policy 字段只认一个值 |
| G70 | 本地模型没有自定义区块：选模型/调参/显存/量化档全缺 | 供应商列表里 ollama 只是一个 base_url，没有任何可调项 |
| G71 | 没有事件流总线，所有交互都是"用户点一下才动" | `/api` 全是请求-响应，没有事件队列 |
| G72 | 没有实时 STT，`stt.listen` 能力在 gateway 里是 missing | `/api/gateway.json` 实测 |
| G73 | 没有延迟预算，也没测过端到端延迟 | 全仓库 grep 无延迟相关指标 |
| G74 | 角色不会主动开口，只有 idle 动作循环 | `zpet_tick` 里没有发话触发 |
| G75 | 没有屏幕捕获，`vision.describe` 没有图像来源 | 无捕获代码 |
| G76 | 没有输入控制，也没有急停机制 | 无 |
| G77 | 没有联机：状态只存本机单实例 | 无同步层 |
| G78 | 能对话的供应商只有 4 个，其中 relay_test 是测试桩 | `config/providers.json` 9 个里 4 个有 chat 能力 |

**硬约束（用户明确排除）**：G78 扩充供应商时**绝对不要豆包 / 火山引擎 / 火山方舟 / Seed 系列**。
已落静态闸 `check_platform.py`「供应商里没有豆包 / 火山引擎」，扫 48 份配置 9 个关键词，负控验过。

## G79~G82 P4 横切缺口（2026-10-14 审计补登）

用户问「做好计划了还缺什么吗」，查了一遍，发现 P4 那批能力有四个**横切关注点**
没有任何归属 —— 它们不属于 G69~G78 里的任何一个，所以谁都不会顺手做掉。

| 编号 | 缺口 | 为什么是缺口 | 现状证据 |
|---|---|---|---|
| G79 | 统一权限模型 | AI 要看屏幕+控键鼠+读文件+联网+常开麦，攻击面很大 | 全仓库只有 A25.4 一句「逐游戏授权」在管 |
| G80 | 成本熔断 | 实时回路烧钱，现在只有"告警"没有"熔断"，且 G3 还没做 | grep「预算/熔断/上限」在计划里 0 命中 |
| G81 | 性能预算 | 捕获+视觉+STT+TTS+立绘同时跑，桌宠不能卡 | G27 只管待机 CPU < 2%，没管实时模式 |
| ~~G82~~ | ✅ 2026-10-15 **真机验收清单已建** `docs/ACCEPTANCE.md`（AC-01~AC-22，按 窗口输入/语音/立绘/平台长稳/模型训练/游戏三档 六组），每条写明怎么测、什么算过、不过先查什么、**沙箱里做到了哪一步**；`selfcheck_repo.py::check_acceptance` 与 TASKS 的 `[需真机]` 标记双向对账 | — | 562 项自检 0 不通过；负控：删一条 → 报「漏登 T21.4」、删一栏 → 报「AC-15 缺沙箱边界」、给 T22.3 加标记 → 报「漏登 T22.3」 |

**排序约束**：G79 先于 G76（控键鼠）；G80 先于 G72/G75（常开麦与持续捕获）；
G82 尽早 —— 它定义 P4 其余各项"做完了"算什么。

## G83 / G84 Minecraft 协议游玩与游戏档位表（2026-10-14 登记）

用户两次澄清把"玩游戏"切成了三档（REQUIREMENTS A25）：
**网游只看不碰、Minecraft 走协议真玩、本地双人用虚拟手柄真玩**。
原先 G75/G76 按"捕获 + 键鼠"一条路设计，覆盖不了 Minecraft —— 那条路既慢又不准，
而 Minecraft 有现成的协议客户端。所以拆出两个新缺口。

| 编号 | 缺口 | 为什么单独立项 | 关键依据 |
|---|---|---|---|
| G83 | Minecraft 协议游玩（Mineflayer + 技能库 + 代码熔断） | 和 G75 的实现完全不重叠：拿的是结构化世界数据不是像素，动作是代码不是键鼠 | Voyager 实证 63 物品/3.3×；MINDcraft 的参数化命令更可靠（REFERENCE_NOTES 第十五批） |
| G84 | 游戏档位表（游戏 → 最高档位） | 没有这张表，"网游只读"就只是口头约定 | 用户硬要求：网游不可提升；归 G79 权限模型管辖 |

**延迟实测（直接决定架构）**：GPT-4 每动作 **25 秒**，本地 7B **300~500ms**。
所以 Minecraft 陪玩必须**本地做快决策、云端做慢规划** —— 这是 A23 双路由的头号用例，
不是可选优化。

## G85 下半身只有一个摆动参数，18 个动作里 14 个腿是僵的（2026-10-14 发现并修完）

**现象**：上半身 46 个参数演得很细（头/眉/眼/嘴/三段手臂/手），下半身**只有
`ParamLegL/R` 一个左右 bend**，而且 18 个动作里只有 sway/idle/happy/hammered 四个
碰得到腿。角色站着的时候下半身是一根柱子。

**排查中踩的两个坑**（都已记进 LESSONS）：
1. 一开始以为"腿完全不会动"，查动作通道 target 时按组名（leg_l）去 grep，结果 0 命中 ——
   **动作通道打的是参数（ParamLegL）不是组**。按参数名查才看到有 4 条。
2. 实测时拿到"噪声底 = 0"还往下走。**噪声底 0 就是引擎时钟被冻结的铁证**
   （上一个脚本在 404 处崩溃，`pause?on=0` 没执行）。解冻后噪声底是全身 16723 / 腿部 1348。

**修法**（不用拆件 —— 靠 bend 曲线选对作用位置）：
- `curve:"sine"`（两端固定、中段最大）峰值正好落在**膝盖**高度 → `ParamKneeL/R` ±9px
- `curve:"tip"`（顶边固定、底端最大）作用在**脚踝** → `ParamTiptoe` 收 5px
- `ParamWeightShift` 一个参数绑三条：骨盆 `root.dx` ±5px + 两腿中段 sine 反向补偿 ∓4px
- 新动作两个：`shift_weight`（站立微动，freq 0.11 比呼吸 0.28 / 摇摆 0.18 都慢，
  三者不同步才不像机械）、`tiptoe`（踮脚，双膝微屈 + 头发滞后一拍）

**实测**（帧 466×748，腿部区域 y≥402）：
| 对象 | 全身差异 | 腿部差异 | 备注 |
|---|---|---|---|
| 噪声底（idle 连拍） | 16723 | 1348 | 时钟在走 |
| ParamKneeL = 1.0 | 4905 | 4905 | **100% 落在腿部**，sine 峰定位准确 |
| ParamKneeR = 1.0 | 4866 | 4866 | 100% |
| ParamWeightShift = 1.0 | 45087 | 14287 | 32% 在腿，其余是 root 横移带的 |
| ParamTiptoe = 1.0 | 43219 | 15056 | 35%，root 上提带全身 |
| 动作 shift_weight | 49935 | 14824 | 超噪声底 **11.0 倍** |
| 动作 tiptoe | 38686 | 11332 | 超噪声底 **8.4 倍** |

**连带改动**：`ZRIG_MAX_PARAMS` 48 → 64（加完 4 个参数共 50 个，撞上限导致
rig 加载失败、形态回退）。`make_rig.py` 的通道转换器新增"参数直写"通路 ——
原先只认几何通道，而 `ParamWeightShift` 绑三条 bind 没法用几何写法表达。
判据仍是"target 必须是 param_list 登记过的 id"，写错名字照样拦。

### 后半段：新参数得真用起来（2026-10-14 续五）

加完参数当时就留了个尾巴 —— **新的 4 个参数只有 `shift_weight`/`tiptoe` 两个
新动作在用，14 个老动作一条都没接**。等于买了工具没开封。

补法是在 `make_rig.py` 的 `to_param_channels()` 调用**之前**加一张集中表
`LOWER_EXTRA`（动作 id → 追加通道），而不是逐个去改上面的动作定义。三个理由：
`wave`/`look_around` 是动态拼出来的没有字面量可改；集中成表幅度能横向比
（都是陪衬，不能喧宾夺主）；将来整体调强弱改一处。

补了 8 个：wave（重心压支撑腿）、surprised（急促屈膝）、sad（重心塌陷）、
think（单腿承重）、talk（轻微重心挪动）、sleep（极慢摇晃+膝软）、
look_around（重心跟视线、慢半拍）、head_pat（被按住微沉）。
判定**不该动**所以没补的 6 个：nod / focus / breath / stroke / clicked / dragged。

**量这件事本身花的功夫比改代码多** —— 判据连废两版，详见 LESSONS 78/79：
- 第一版「比 idle 噪声底 ≥2.0 倍」：负对照 `nod`/`focus`/`clicked`（根本没有腿部
  通道）照样测出 1.5~1.7 倍，`stroke` 更是 5.3 倍。**它量的是"切换动作"的扰动**。
- 第二版「剥掉通道做 A/B」判据对了，但 `sleep` 报 +1%「基本没用」—— 实为
  **指标饱和**：sleep 相对 idle 基准帧，腿部变化像素 28745 = 腿区角色像素 27137 的
  **106%**，顶到天花板了，再动也加不上去。
- 终版：**一次性动作**用「相对 idle 基准帧的峰值差」，**循环动作**用「自方差」
  （基准帧取自动作进行中，量的是这个状态下身体还动不动）。

**终版实测**（同一二进制、同一采样，唯一变量是那 25 条通道）：

| 动作 | 类型 | 补之前 | 补之后 | 净增 | 判定 |
|---|---|---|---|---|---|
| nod（负对照） | 一次性 | 5917 | 6045 | +128 (+2%) | **这就是测量误差底** |
| wave | 一次性 | 9567 | 11550 | +1983 (+21%) | 有效（绝对值 15× 误差底） |
| surprised | 一次性 | 6805 | 8154 | +1349 (+20%) | 有效（10× 误差底） |
| sad | 一次性 | 5154 | 7625 | +2471 (+48%) | 有效 |
| think | 一次性 | 5265 | 7399 | +2134 (+41%) | 有效 |
| talk | 循环 | 5157 | 7243 | +2086 (+40%) | 有效 |
| look_around | 循环 | 5131 | 7959 | +2828 (+55%) | 有效 |
| head_pat | 一次性 | 5036 | 7219 | +2183 (+43%) | 有效 |
| **sleep** | 循环·自方差 | **734 (3%)** | **7583 (28%)** | **10.3 倍** | **八个里最强** |

sleep 那行是整轮最大的教训：**饱和的指标把效果最好的一个报成了最差的**。
参照系：idle 自方差 7004、sway 11028，sleep 的 7583 落在两者之间，合理。

调过一次参：surprised 原本 knee 0.30/0.35s 只有 +?%（第一版判据下 1.7×），
加到 0.48/0.50s。受惊是全身反应，腿僵着就假了，这个动作幅度就该比别的大。


## G86 眨眼和视线/转头完全无关（2026-10-14 发现，未做）

Live2D 官方《提高动态质量的技巧》第 4 条：**"人在转脸或换视线时经常眨眼"**
（https://docs.live2d.com/zh-CHS/cubism-editor-tutorials/motion-hint/）。

我们现在的眨眼是**纯随机定时器**（`blink_imin/imax` 区间内抽一个间隔），
和 `look_around`、gaze 跟随、头部转动一概无关。引擎里已经有现成的
`zrig_blink_trigger()`，接上去成本很低。

做法建议：视线横向位移超过阈值、或 `look_around` 每段转向开始时，
以一定概率触发一次眨眼（不要每次都眨，否则又变机器人）。

## G87 闭眼时眼型没有横向收窄（2026-10-14 发现，试过一版已撤回）

同一份官方教程的眨眼视频字幕原话：
**"Making the shape slightly narrower horizontally when the eye is closed
than when open makes it easy to create a natural blink"**。

**本轮试过 `aperture_narrow`（眼眶遮罩随 blink 横向收 12%），已撤回**：
实测虹膜宽度 0.25/0.40/0.55 三档都是 123px，**一点没变**。
因为我们是遮罩裁切，虹膜 31×30 离遮罩左右边缘很远，收 6% 够不到它，
只削到了眼白外角（变化 1500~2400 像素，肉眼看不出）。

要真做到，得把眼部件的 `anchor` 从 `[0,0]`（左上角）改成各自中心，
再让整组 eye_open 随 blink 横向缩 —— 锚点一动 `pos` 必须同步改到那个点的
身体坐标（`zimg_make_matrix` 是把 anchor 这个像素点放到 pos 上），
属 `make_rig.py` 的结构性改动。

⚠ **不要看到官方那句话就再加一次 aperture_narrow** —— 那条路已经验证过走不通。

## G88 踮脚 ✅ **2026-10-14 全部做完**（标题原为"脚部拆件经模拟验证后否决"——该结论已被推翻）

> **★ 读这一节先看这段。** 下面保留了当天的完整推演过程，但其中**两个中间结论已作废**：
> ① "改成 root.dy 与腿 bend_y 异号等量就算修好了" —— 只钉住了脚底，鞋本身没变化；
> ② "脚部拆件已否决" —— 否决的前提（踮脚时鞋会变扁）本身就是错的，
>    正确物理是**鞋在画面里变高**（俯角 θ≈37°，绕趾尖转 φ ≡ 纵向拉伸 k=sin(θ+φ)/sinθ）。
> **最终实现见 TASKS T24.5 与 `docs/ART_PARTS.md` 5.13**：鞋拆四件 + 参数驱动交叉淡化。
> 保留下文是为了记住"方向搞反会把一条对的路否掉"这件事，**不是让人照着做**。


用户实测："踮脚高度有了，只不过脚部的模型没有变化，没有出现鞋子往地垫的动画"。
**确认属实**：`leg_l`/`leg_r` 两组各只有一个整段部件 `seg_leg_l`/`seg_leg_r`，
**没有 foot / ankle / shoe 组**。`ParamTiptoe` 能做的只有 root 上提 7px +
两腿 `bend_y` 用 tip 曲线（底端形变），**没有任何部件可以绕脚尖旋转**，
所以不可能出现"脚跟抬起、鞋底与地面成角"的效果。

好消息：`tools/make_anchors.py:227-230` **已经算出 `ankle` 和 `foot` 两个锚点**，
在脚踝处切件的数据是现成的。

做法：
1. `make_body_parts.py` 把 `seg_leg_*` 在 ankle 线切成小腿 + `seg_foot_*`（带重叠带）
2. `make_rig.py` 加 `foot_l`/`foot_r` 组，**pivot 放在脚尖**，parent 为 `leg_l`/`leg_r`
3. `ParamTiptoe` 增绑 `foot_*.rot_deg`（脚跟抬起 = 绕脚尖转）
4. 脚踝背面转出来的楔形缺口若露底，按 D19 走 AI 重绘补片

成本：要跑 `bash tools/rebuild_parts.sh xiaoxun teen`（≈240s）。

---

### ★ 2026-10-14 复查结论（覆盖上面的计划，上面那段保留作为背景）

**① 先查出一个比"没拆件"更根本的 bug，已修。**

`ParamTiptoe` 的两条绑定原本是**同号**的：
`root.dy = -7`（整体上提）+ `seg_leg_*.bend_y = -5`（tip 曲线，底端满额），
两个一起往上 → **不是踮脚，是整个人连脚一起浮空 12px**。
引擎实测角色最底行 **1359 → 1347**。

「脚部没有变化」这句话有一半就出在这：脚相对身体确实没变化，因为它跟着整个人飘走了。

改成异号等量（`bend_y = +7`，tip 曲线底端权重 1.0 正好抵消）后实测
**Tiptoe=0 和 1 的最底行都是 1359，脚底精确钉在地面**，身体照常升高，
差额由小腿伸展吸收 —— 这才是踮脚。

新闸 `check_tiptoe_grounded()`：root.dy 与两腿 bend_y 必须**异号、等量、tip 曲线**。
负控（改回 -5.0）已验红。

**② 脚部拆件：做了图像模拟，结论是不做。**

拆件的目的是让鞋子能独立压缩/旋转出"抬脚跟"。动手之前先用图像模拟
验证了这个想法（`logs/asset_qa/tiptoe_mock.png`，把鞋段以鞋底为锚压缩
2% / 8% / 14% / 22% 四档）：

- 8%：几乎看不出变化，等于白拆
- **14% / 22%：鞋子只是被压扁了，读起来像"踩瘪的鞋"，不是"抬起脚跟"**

根因是**鞋子是正面视角画的**（实测鞋底着地段 x164~207 对脚踝 x166~201，
左右基本对称 = 正对镜头）。正面视角下，2D 平面内的纵向压缩给不出抬跟的读感，
平面内旋转则读成"崴脚"。

**真要做抬脚跟，必须 AI 重绘踮脚姿态的鞋**（D19：被遮挡区域必须重绘 ——
鞋底翻起来会露出原画里根本不存在的鞋底面）。那是独立的一块素材活，
不在本轮。拆件本身（切脚踝线、建 foot 组）在没有新素材的前提下**不产生价值**，
所以撤销 T24.1 的"拆件"部分。

脚踝切线本身是验过的：`anchors.json` 的 `ankle y=1142` 正好落在鞋口上沿
（`logs/asset_qa/leg_cutline.png`），将来真要拆，这条线可以直接用。

## G89 颈部/兜帽横向滑移（2026-10-14 用户实测反馈，已修完）

**现象**：用户反馈"颈部会横向整体错误细微的位移，包括颈部附近的兜帽位置"，
并指出"我在测试网关很容易就看到了"。

**根因**（逐行位移剖面实测出来的）：
- `seg_torso` 贴图顶边在画布 **y=308**，但那一段其实是**脖子和衣领/兜帽**
- `ParamBodyAngleX → seg_torso.bend_x` 用 `root` 曲线，`f(t)=(1-t)²`，
  **t=0（顶边）时系数 1.0，拿满额形变**
- 而 `head` 组是 `bend_follow_at=346`（颈关节），按**那一行**的量做**刚性整体平移**，
  只拿到 `f(0.0758)=0.854`
- 结果：**衣领比它上面的头、下面的胸都移动得多，自己"鼓"出来一块**

**实测（ParamBodyAngleX 满格 10）**：
| 画布 y | 修前 | 修后 |
|---|---|---|
| 305（头部最后一行） | −4.68 | −4.68 |
| **309（躯干顶边）** | **−5.08（跳变 0.40）** | **−4.76（跳变 0.08）** |
| 316 / 327 / 342 | −4.96 / −4.89 / −4.76 | −4.73 / −4.75 / −4.74 |
| 349 以下 | 正常错切 | 正常错切（保留） |

衣领整段从"斜坡"变成"与头齐平的平台"，**相对滑移 0.34px → 0.04px，8.5 倍改善**。

**修法**：给部件加 `bend_hold_above`（形变平台线，画布 y）。
渲染时 `if (t < bend_tmin) t = bend_tmin;` —— 平台线以上的行共用平台线处的形变量。
生成器给 `seg_torso` 写上 `bend_hold_above = neck_pt[1] = 346`。

引擎新增 `zimg_draw_warp_blend_t()`（带平台的版本），老函数保留为 0 平台的包装，
**没有改动任何既有调用方的签名**（tests 里 4 处 `zimg_draw_warp` 不受影响）。

**闸**：`check_neck_seam()` —— 凡是被 bend 驱动、又被某个组当 `bend_follow` 源的部件，
必须写 `bend_hold_above` 且落在部件纵向范围内。两种坏法（删掉值 / 写到贴图外）已验红。

**为什么我自己没查出来**：之前的实测脚本都在量"动作幅度够不够大"（整帧/分区像素差），
**量的是"有没有动"，而不是"各部分动得一不一致"**。
一致性要用**逐行位移剖面**（相邻行的位移应当连续，跳变=接缝）。
已把这个方法加进 `tools/measure_motion.py` 的 `--profile` 模式。

## G90 剩下那几处跳变查完了：一处是误报，其余低于可见阈值（2026-10-14 发现，2026-10-15 查完）

修完颈部（G89）后用 `measure_motion.py --profile` 跑剖面，`ParamBodyAngleX=10` 下
还剩四处跳变，最大的一处 **+2.35px 在"躯干底边与腿交界"**。当时写着"先确认不是量法问题"。

**查的过程（两次走弯路，都记下来）**：

1. 第一次想用"物理开 / 关"做对照 —— **这个对照是空转的**：
   `measure_motion.py` 第 219 行自己就把物理关了，我那两次跑的是同一个状态。
   凡是"拿旋钮做对照"，先确认那个旋钮没被工具内部改掉。
2. 第二次直接看图（`logs/asset_qa/hip_seam.png`，A/B + 差分，胯部 ×3）：
   **那处根本不是裂缝，是一条自由边** —— 裙摆下沿压着大腿，
   裙子跟上身走、腿站着不动，本来就该相对错开（真人侧身也是这样）。
   原来的判据"位移跳变 = 接缝"在这里是**误报**。

**判据已修**（`measure_motion.py` 新增 `row_material()`）：跳变分两类 ——
两侧**同材质**（同一块皮肤/同一件衣服被切开）才是真接缝；两侧**不同材质**
（藏青裙 ↔ 肤色腿）是自由边，预期如此。阈值取平均色距 40：
实测同材质三处是 5 / 9 / 27，异材质是 66，取中间而不是贴着 27。
负控：合成图喂进去，肤色↔肤色 = 0.0（判真接缝）、藏青↔肤色 = 275（判自由边）、全透明 = None 不参与。

**四个参数跑完的结论**（`--jump 0.25`，帧行×0.55 = 画布 y）：

| 参数 | 真接缝（同材质） | 自由边（预期） |
|---|---|---|
| ParamBodyAngleX=10 | 3 处，最大 **0.35 帧px** | 1 处（裙摆↔腿，2.35） |
| ParamAngleZ=10 | 3 处，最大 **0.45 帧px** | 2 处 |
| ParamAngleX=10 | **0 处** | 0 处 |
| ParamBodyAngleY=10 | 0 处 | 5 处 |

**最大的真接缝 0.45 帧px ≈ 0.82 画布px —— 不到一个像素，肉眼看不见。**
所以**不改**（理由与"如果反过来会怎样"见 DECISIONS DC28）。

## G91 摸头把脖子抽长 + 没有开心表情（2026-10-14 用户反馈，已修完）

用户原话："摸头的时候不应该脖子伸长而是微微歪头一脸开心享受对不对？" —— 对。

**根因**：生成器里 `head_pat` 写的是 `head.dy = -7.0`（pulse 保持），
**字面意义上把整个头往上平移 7 像素**。而 look 配置里 `head.dy=10 / chest.dy=1`，
胸只跟 0.7px → 净脖子抽长 6.3px。引擎层实测 **颈长峰值 -9.48px**。

**改法**：
- 去掉上平移，改成 `ParamAngleZ` pulse 11（歪头，走 head.rot_deg 绕颈关节转，**不改颈长**）
- 头顺着手的力道微沉：`head.dy` 取正 2.0（原来是 -7.0）
- 一脸享受：`ParamEyeLSmile/RSmile` = 1.0（山型笑眼顶替谷型闭眼）
  + `ParamCheek` 0.6（脸红）+ `ParamMouthForm` 0.85（嘴角上扬）

**实测**：颈长峰值 **-9.48px（抽长）→ +3.23px（微沉，被摸时的自然反应）**。

顺手解决的拦路问题：`ParamEyeLSmile/RSmile` 是**引擎内建参数**（zrig.c 的
`param_add_builtin`），不写进 rig.json 的 params，所以生成器的
`to_param_channels` 不认、会直接 SystemExit 拒绝。
在 make_rig.py 加了 `BUILTIN_PARAM_IDS` 白名单（9 个），和 zrig.c 保持一致。

## G92 歪头时身体是刚体（2026-10-14 用户反馈，已修完）

用户原话："光是头在动，身体没联动不自然"。
Live2D 官方《提高动态质量的技巧》第 1 条一字不差：
**「如果只转动脸部，则会看起来像一个机器人」**。

**根因**（查出来比想象的更干净）：
- `ParamAngleX/Y` 是**引擎内建**、走 look 系统，本来就同时写 head 和 chest
  （`head.rot 5.0 / chest.rot 1.2`，比例 0.24）
- **`ParamAngleZ` 是普通参数，只绑了 `head.rot_deg×0.5`，胸部分量为 0**
- 而 20 个动作里 **19 个有头部通道、其中 15 个身体完全不动**，
  这 15 个里 12 个用的正是 AngleZ

**改法**：给 `ParamAngleZ` 加第二条绑定 `chest.rot_deg × 0.12`。
比例 0.12/0.5 = **0.24，照抄 look 里已经调好的 chest/head 比**，口径一致。

**A/B 实测**（ParamAngleZ=30，逐行位移剖面）：

| 画布 y | 剥离胸部分量 | 有耦合 |
|---|---|---|
| 175~349（头） | −6.5 | −6.0 |
| **393~567（胸）** | **+0.00（精确的刚体）** | **−6.5 ~ −5.0** |
| 611~698（腰） | 0.00 | −3.92 → −1.58 |
| 742~785（胯下，过枢轴） | 0.00 | **+2.58（反向，正确）** |

胸部段平均净增 **5.88px**，而修之前是**精确的 0.00px**。

**为什么选这条路而不是手工给 15 个动作补身体通道**：见 LESSONS 86。

**闸**：`check_head_body_link()`，三种拆法（删胸绑定 / 加回上平移 / 删开心表情）
已逐个验红。selfcheck 171 → 179 项。

## G93 上身追头的惯性滞后（2026-10-14，已做完）

Live2D 官方《提高动态质量的技巧》第 2 条：**「转动脸部，身体会在稍后跟随」** ——
脸和身体**同时**到位仍然像机器人。G92 把身体接上了，但身体是**同步**跟的。

**做法**：加一条物理 `torso_follow_head`，
`input: [{param: ParamAngleZ, weight: 1.0}]` → 输出 `seg_torso.bend_x`。

**为什么能和 G92 那条瞬时绑定共存而不重复计数**：物理的输出是 `pos - target`，
即**纯滞后量**，静止时自动归零（zrig.c physics_update 的注释写了
"只加惯性，不会永久吹偏"）。稳态倾斜由绑定给，物理只补转头过程中的追赶。

参数：`ratio 0.10, stiffness 22, damping 5.5, max 3.0`。
ω=√22≈4.7rad/s（周期 1.34s，远慢于头发），ζ=5.5/(2√22)=0.586（收得干净、一点点回弹）。
对照：呆毛 stiffness 42 ζ=0.39（更弹），手腕 34/4.4。

**实测**（阶跃 ParamAngleZ→25）：静止 0.011≈0 → 瞬间落后 −2.47px → 1.3s 内归零。
**各动作里的真实量级**，正好符合官方"动作要有张弛"：

| 动作 | 惯性峰值 | 平均 |
|---|---|---|
| idle | −0.25px | 0.03 |
| sway | −0.17px | 0.05 |
| look_around | −0.28px | 0.15 |
| head_pat | −1.17px | 0.35 |
| nod | **+1.90px** | 0.62 |

闸 `check_torso_inertia()`：输入必须是 ParamAngleZ、输出在躯干、
**阻尼比 ζ 必须落在 0.4~1.2**（太小一直晃、太大等于没惯性）、stiffness 必须低于呆毛。
负控（damping 调到 1.0 → ζ=0.107）验红。

## G94 ★ 物理条数超过引擎上限会被静默丢掉（2026-10-14 意外挖出，已修）

加 G93 那条物理时单测红了「裙摆纵摆实际峰值 0.000」。查出来：

**`ZRIG_MAX_PHYS` 是 12，而 rig 里早就声明了 13 条。**
解析循环写的是 `for (i = 0; i < n && r->nphys < ZRIG_MAX_PHYS; ++i)` ——
**超出的直接丢掉，一句报错都没有。**

也就是说第 13 条 **`back_x`（后发摆动）一直是哑的**，而且它是全场最大的一个摆
（look_around 时峰值 **1.77px**，比裙摆 0.13、躯干 0.26 都大）。
从头到尾没有任何征兆，直到我再加一条把 skirt_y 也挤掉，单测才红出来。

负控实测：
| | 上限 12 | 上限 24 |
|---|---|---|
| back_x | **0.0000 哑** | **1.7713 活** |
| skirt_y | **0.0000 哑** | 0.1319 活 |

**两处修**：
1. `ZRIG_MAX_PHYS` 12 → 24
2. **超限改成硬报错**（`if (n > ZRIG_MAX_PHYS) zdiag_error(...)`），不再静默截断

**闸** `check_engine_caps()`：扫 `ZRIG_MAX_PHYS / PARAMS / PARTS` 三个宏，
断言 rig 的声明数不超上限**且留 15% 余量**（快顶满就提前报，不等撞上）。
负控（上限改回 12）验红两项。

现状：physics 14/24（58%）、params 41/64（64%）、parts 40/64（63%）。

## G95 ★ 形变平台在网格路径上丢失（2026-10-14，我上一轮自己埋的，已修）

G89 加的 `bend_hold_above`（颈部形变平台）**只接了 warp 那条绘制路径**，
网格路径 `zimg_draw_mesh_bend_blend` 完全没有它。

**为什么当时没发现**：`st->dg`（网格）只在形变器 `amount ≠ 0` 时才非空，
而我验收时是**冻结时钟**状态 —— 冻结时 `physics_update` 第一行就因 `dt<=0` 返回，
裙摆形变器 amount 恒为 0，于是走的是 warp 路径，平台生效，测出来一片大好。

**真实后果**：正常运行时裙子一摆，`amount≠0` → 走网格路径 → 平台丢失，
**颈部滑移原样回来**。也就是"颈部修复只在裙子不动的时候有效"。

**修法**：新增 `zimg_draw_mesh_bend_blend_t()`，在控制点求曲线时同样钳 `tb`；
两处 fallback（参数非法、控制点没挪）也改成调 `zimg_draw_warp_blend_t` 带上平台。
老函数保留为 tmin=0 的包装，没改既有调用方签名。

**验证**（图元级，直接测两条绘制路径）：
| | 无平台 | 有平台 | 降幅 |
|---|---|---|---|
| warp 路径 | 59.50 | 54.50 | **−5.00** |
| mesh 路径 | 59.00 | 54.50 | **−4.50** |

两条路降幅相差 10%，来自网格的分段线性近似（10 行控制点 vs 逐像素），
不是 bug。单测判据因此用**相对容差 15%**。

**单测**（tests/test_core.c，3 条）：平台在 warp 上生效、在 mesh 上也生效、
两者降幅等量。三条都做了负控：单独拆掉任一条路的平台都会红，而且点名到具体那条。

**这个坑的一般形态见 LESSONS 91。**

## G96 · 部件离屏合成（Offscreen drawing）——交叉淡化的总覆盖还差那 15%

交叉淡化中点我们按官方 `CubismPose::DoFade` 把总覆盖抬到 **0.85**（线性只有 0.75），
官方 BackOpacityThreshold 就是 0.15，**这 15% 是设计上留的，不是 bug**。
真要做到 1.00，官方的办法是部件级 **Offscreen drawing**（Cubism 5.3 起，
见 REFERENCE_NOTES 第十九批《检视器面板》）：部件内部先离屏合成好，再整体上一次不透明度。

我们的渲染器目前是逐部件直接 alpha_composite。要上离屏合成得：
给 `zrig` 的组加一个 `offscreen: true`，渲染时先把组内部件画进一张临时 RGBA，
再按组不透明度合成到主画布。工作量不大，但会多一次全画布分配，
**等到真有"整组一起淡入淡出"的需求（换装？形态切换？）再做。**

现状不影响桌宠：那 15% 只在 50ms 的交叠窗里出现，且鞋后面就是透明桌面。

## G97 · 引擎的 `bend_hold_below` ✅ 2026-10-15 补上了

上平台 `bend_hold_above` 解决"跟随件在上面"（头跟躯干）；反过来"跟随件在下面"
（脚跟腿、手跟前臂）以前**没有对应的下平台**，只能靠 `make_foot_parts.py`
把腿件切线以下整个裁掉来回避 —— 第三种跟随关系一出现这个洞就会暴露。

现在两条都有了，互为镜像：

| 字段 | 作用 | 典型用法 |
|---|---|---|
| `bend_hold_above` | 这条画布线**以上**共用线处形变量 | 躯干：颈线以上跟着头走 |
| `bend_hold_below` | 这条画布线**以下**共用线处形变量 | 腿：踝线以下交给鞋件画 |

落点：`zimg.c:draw_impl` 的 `bend_tmax` 钳位（warp 与 mesh **两条路都接了**，
上一次只接一条的教训见 LESSONS）、`zrig.c` 解析 `bend_hold_below`、
`make_rig.py` 切件表写 `hold_below` 就会落到 rig.json 上。

**现有腿件仍然走"切掉"那条路，不改**：已经切干净了，多一条平台线就多一处要对齐的
参数（切线挪了平台线不会自动跟着挪）。selfcheck 里加了闸拦"既切掉又写下平台"。

测试：`test_core` 用 TIP 曲线（顶固定、底端最大）验底行被按住 **且平台线以上不受影响**
（只压一头才叫平台，整块按死是另一种 bug）；负控把钳位去掉 → 立刻红。

## G98 · `wave` 的 `airborne` ✅ 2026-10-15 改成"膝盖吃掉"；`clicked` 保留

`check_feet_on_ground` 要求会离地的动作显式声明幅度。原先五个声明里有两个是权宜：

| 动作 | 原 px | 现在 | 性质 |
|---|---|---|---|
| happy | 34 | 34 | 真跳跃 ✅ 设计如此 |
| hammered | 8 | 8 | 被砸下陷 ✅ 设计如此 |
| sleep | 4 | 4 | 坐下去 ✅ 设计如此 |
| clicked | 6 | **6（保留）** | 被戳一下的小跳 —— 见下 |
| wave | 2 | **0（已改）** | 挥手起伏，本该"膝盖吃掉、脚不动" |

**wave 怎么改的**：原来走 `ParamBaseY`（= `root.dy`，整个人平移），连脚一起浮。
新增参数 `ParamHipDrop`（胯下沉 / 屈膝承重）：

```
chest.dy        +2.0        上半身跟着节奏起伏
seg_leg_*.bend_y +2.0 root  腿顶跟着胯下来、脚踝那一行不动
```

关键是 `curve: root`（底边固定、顶端最大）—— 脚件是刚性跟随腿在**切线处**的形变的，
而 root 曲线在切线（腿件底边）处正好等于 0，所以鞋底净位移是 0，`airborne` 可以直接删掉。

**实测**（重启预览后，46 帧逐帧量最底不透明行）：

| 动作 | 脚底振幅 | 头顶振幅 | 裙摆下沿振幅 |
|---|---|---|---|
| idle | 0 px | 6 px | 0 px |
| wave（改前） | **2 px** | — | — |
| wave（改后） | **0 px** | 5 px | 9 px |

脚不动、上身照样在动 —— 这条负控很重要，不然"把起伏删光"也能让脚不动。
留证：`logs/asset_qa/wave_feet.png`（六帧特写，红线=当帧最底行）。

**clicked 的 6px 保留**：被戳一下弹一下是**故意要离地**的，和 happy 同类，
不是量法问题。复查触发：真机上用户觉得"戳一下跳得太夸张"就调小。

## G99 · `prefer_local` 只是"有本地就用本地"，不是真双路由（2026-10-15，已做完）

**原来的样子**：`config/gateway.json` 的 `routing.strategy = prefer_local`，
运行时 `zgw_pick()` 按优先级取第一个 enabled 的。它回答不了两个要命的问题 ——
"这条请求带隐私标记"和"本地显卡正忙"。更糟的是：**本地那条关掉时它会安静地滑到云端**，
对普通请求没问题，对带隐私标记的请求就是事故。

**做法**（判据抄自 REFERENCE_NOTES 第二十批，结论登记在 DC18）：
新增 `zgw_route_for(g, cap, req, &why, &reason)`，三支柱按**不可颠倒的次序**判：

1. **敏感 → 强制本地**。本地不可用时返回 `ZGW_SENSITIVE_NO_LOCAL`，**不退而求其次**。
   这是整个函数里唯一一个"宁可功能不可用"的分支。
2. **复杂 / 长 → 云端**：`tokens_est > rules.tokens_cloud`(512) 或 `task == HEAVY`。
3. **忙 / 故障 → 互相兜底**：本地负载 ≥ `local_busy_pct`(85) 溢出到云端；
   云端 `cloud_down` 时退回本地。

阈值不写死在代码里：`config/gateway.json` 的 `routing.rules` 是契约，
`tools/check_platform.py` 把它物化进 `config/gateway_routes.json`（DC24 的老做法）。
每次决策记一笔 `reason_hits[]` + `picks_local/cloud`，`zgw_local_share()` 给出本地分流占比
—— 调研给的目标区间是 **0.70~0.85**，长期偏离说明**阈值不对**，而不是用户变了。

新端点 **`/api/route`**（`?cap=&sensitive=&tokens=&load=&cloud_down=&heavy=`）是个纯决策沙盘：
不发任何网络请求，在没有密钥、没有显卡的机器上也能把规则验到底。

| 实测（本地全关、云端全开的"最诱惑局面"） | 结果 |
|---|---|
| `sensitive=1` | **(拒绝)** `reason=sensitive_blocked` |
| 同一局面、同一能力，只是不带 sensitive | `deepseek` `reason=only_choice` |
| `tokens=4000` | `deepseek` `reason=long_cloud` |

闸门：`test_core` **653 → 666**；负控 = 在敏感分支偷偷加一句上云 fallback
（别人最容易"顺手贴心"的那种改动）→ 两项立刻判红。

**还欠**：① 阈值是抄来的，要用 `data/usage.jsonl` 的真实记账重标（DC18 的复查触发）；
② ~~没有"自动判重活"的分类器~~ ✅ 2026-10-15 补上 `zgw_classify()`（关键词三类 + 长度 600 字节，
   见 DC27；端点加 `?q=`，面板上可以直接打字试）；
③ 路由决策没写进账本文件，只在内存里计数。
