# 参考项目笔记（六个地址 + 实际查阅结论）

> 用户明确要求：遇到问题先去这六个项目的源码里查，不能只看摘要，也不能凭猜测下结论；
> 六个项目解决不了再上网查资料，并记录来源；**不把参考项目源码整体复制进仓库**（AGPL 的尤其只学思路）。
>
> 六个地址见下表。前四个＋第二个 BongoCat 在旧交接文件第二节也有记录。

| # | 项目 | 地址 | 许可 | 本项目实际用到/将用到什么 |
| --- | --- | --- | --- | --- |
| 1 | BongoCat（C + SDL3 + OpenGL） | https://github.com/vladelaina/BongoCat | AGPL-3.0 | 原生透明窗与渲染思路、托盘与品牌图标一致性、"鼠标穿透开/关"开关。**只学思路，不复制代码**（AGPL）。 |
| 2 | BongoCat（Rust + Live2D + 全局输入） | https://github.com/ayangweb/BongoCat | Apache-2.0 | 全局键鼠钩子驱动的反应、动作可重叠播放（优先级表达）、各平台权限流程。第三步做全局输入时参考。 |
| 3 | ds-local-pet（PySide6） | https://github.com/QCYTSN/ds-local-pet | MIT | **已在用**：动作状态机语义（优先级/可中断/过期回退）、`GetLastInputInfo` 空闲检测、素材与代码授权分离。 |
| 4 | VPet（WPF） | https://github.com/LorisYounger/VPet | Apache-2.0 | 桌宠交互语汇：拖动、点击反应、右键菜单、托盘、缩放贴合窗口、触摸分区（头部 30% 摸头）。 |
| 5 | airi（Web + Live2D/VRM） | https://github.com/moeru-ai/airi | MIT | 实时语音四段结构（STT 端点 → turn → 打断 barge-in → 口型）、供应商适配层、多渲染后端舞台抽象。第五步做语音时参考。 |
| 6 | Live2D CubismWebFramework | https://github.com/Live2D/CubismWebFramework | Live2D Open Software License（Cubism Core 为专有，**不引入**） | **已在用**：眨眼状态机的五态时序。注意：年营收超 1000 万日元商用需按 Cubism SDK Release License 取得授权；本项目不引入 Cubism Core，只按公开做法自己实现参数动画。 |

## 实际查阅记录（可复核）

### 1) 眨眼状态机 —— CubismWebFramework `src/effect/cubismeyeblink.ts`
读了源码中的 `setBlinkingSetting(closing, closed, opening)` 与 `updateParameters()` 的状态分支，
确认五态：`EyeStateFirst → EyeStateInterval → EyeStateClosing → EyeStateClosed → EyeStateOpening`。
默认时序（闭合 / 保持 / 睁开）与"间隔随机"的处理方式，被移植为 `src/core/zrig.c` 里的
`blink_update()`（同时也是 `blink` 配置段的字段含义）。

### 2) 动作状态机 —— ds-local-pet `animation/state_machine.py`
读了 `ActionStateMachine.request()` 的判定顺序：
```
if not force:
    if not current.interruptible and candidate.priority <= current.priority: return None
    if candidate.priority < current.priority: return None
```
以及 `update()` 里"到期后进入 `_queued_after` 或 `spec.return_state`"的逻辑。
本项目把它翻写成 C（`src/core/zsm.c` 的 `zsm_request()` / `zsm_update()`），并保留
"同一状态重复请求不重置计时、`force` 可重播"的行为（用于摸头连击与唤醒）。

### 3) 空闲检测 —— ds-local-pet `awareness/idle_detector.py`
`GetLastInputInfo` + `GetTickCount` 求差值、并按 32 位环绕取模（`& 0xFFFFFFFF`）。
C 版见 `src/win32/zw32.c` 主循环里的 `LASTINPUTINFO` 段：差值转秒后交给 `zpet_report_idle()`，
由 `src/core/zpet.c` 判断"超过 90 秒 → sleep、任何输入 → 唤醒"。

### 4) 交互语汇 —— VPet（WPF）
参考其"拖动 / 点击反应 / 右键菜单 / 托盘 / 触摸分区"的组织方式：
- 头部区域 → 摸头，身体 → 抚摸，脚部 → 惊讶（本项目的 `regions` 与 `zpet_poke()`）；
- 拖动 vs 点击用系统拖拽阈值区分（`SM_CXDRAG`），避免"想点一下却把窗口拖走"。
（VPet 为 WPF/C#，本项目为 C/Win32，只借鉴交互定义，不复制代码。）

### 5) 托盘图标与角色一致 —— BongoCat（vladelaina）
该项目的托盘图标与角色形象保持一致。本项目实现为：**从当前帧实时生成 HICON**
（`icon_from_pet()`，32px/16px 各一份，换形态后自动刷新），因此不需要额外维护一套图标文件。

### 6) 透明窗与穿透 —— 综合结论
- 透明：`WS_EX_LAYERED` + `UpdateLayeredWindow(ULW_ALPHA)`，每帧直接推 RGBA（预乘），无需 GDI 双缓。
- 穿透：**不是**整个窗口开 `WS_EX_TRANSPARENT`，而是在 `WM_NCHITTEST` 里用角色 alpha 判定，
  透明处返回 `HTTRANSPARENT`，让鼠标事件落到下面的窗口；这与用户在旧交接文件里的要求一致
  （"角色以外的区域不拦截鼠标"），同时保留"整窗穿透"作为托盘开关（BongoCat 的开关思路）。

## 未决 / 待查（下一步做对应功能前先查这六个项目）
- 全局键鼠钩子：Windows 的 `WH_KEYBOARD_LL` / `RawInput` 取舍与权限流程 → 参考 #2。
- 语音打断（barge-in）与端点检测 → 参考 #5。
- 网格形变（mesh warp）做脸/身体平滑弯曲 → 参考 #6 的参数与形变管线（不用 Cubism Core）。

---

## 拉取与查阅记录（2026-10-11 第二轮：七个项目全部落地）

拉取脚本：`bash scripts/fetch_references.sh`（只查阅，不入库；用完 `clean_references.sh` 删除）
实际目录：`~/.cache/zc-refs/`

| 项目 | 大小 | 本轮实际查验的内容（可复核） |
| --- | --- | --- |
| bongocat-sdl | 11M | 原生透明窗与托盘思路（AGPL，只学思路不复制） |
| bongocat-tauri | 21M | 全局输入钩子与动作重叠播放 |
| ds-local-pet | 210M | 已在用：`animation/state_machine.py`、`awareness/idle_detector.py` |
| vpet | 1.8G | **模组化证据**：`VPet-Simulator.Windows.Interface/Mod/IModInfo.cs`（第三方 Mod 接口）、`Function/CoreMOD.cs`、`VPet.Solution/Models/ModLoader.cs`（Mod 装载）→ 验证"部件/服装可插拔"的工程做法 |
| airi | 948M | **语音流水线证据**：`packages/pipelines-audio/src/speech-pipeline.ts`、`managers/playback-manager.ts`、`llm-streaming-control/`、`timeline.ts`；barge/interrupt 出现在 speech-pipeline 与 playback-manager → 打断与播放队列按此结构实现 |
| cubism-web-fw | 1.4M | **部件与渲染证据**：`src/rendering/cubismrenderer_webgl.ts` 的 `drawMeshWebGL(model, index)`（每个可绘制对象 = 一个网格 + 独立绘制序号）、`cubismclippingmanager.ts`（遮罩/裁剪）、`src/cubismdefaultparameterid.ts`（`ParamAngleX` 等标准参数命名） |
| photocraft | 54M | **图层与选区证据**：`crates/algo/src/selection.rs`、`selection_blur.rs`、`crates/engine/`（图层引擎与填充图层测试）、`assets/icons/layer-mask.svg` → 素材精修（蒙版/选区/图层）参考 |

### 结论一：Live2D 是不是"单独做独立部件"？
**是。** 源码层面的结构是：
1. **每个部件 = 一个独立网格（mesh）**：顶点、三角形索引、UV、绘制序号（`drawMeshWebGL(model, index)` 逐个绘制，顺序由模型决定）；
2. **部件内部还有网格细分级别的形变单元**（deformer 层级：父级旋转/弯曲 → 子级网格 warp），参数（`ParamAngleX` 等）驱动层级逐级变形；
3. **遮罩（clipping）单独管理**（眼睛裁剪、刘海遮罩），与部件绑定；
4. 因此"能不能自然弯曲"取决于**拆件时每个部件是否自带网格**，而不是引擎算法多高级。

本项目的等价实现（已落地，代码可查）：
- 部件独立拆分 + 层级（rig.json 的 groups/parts/layer）＝ 第 1、2 点的简化；
- **`zimg_draw_warp`（逐像素平滑形变）**＝ 网格形变的连续等价实现（无分段接缝）；
- **`bend_x`/`bend_y` 通道 + curve（root/sine/linear/**tip**）** ＝ 参数驱动形变。
  曲线语义（2026-10-11 实测校正）：**底边是根**（人物站在地上）。
  `root`=底固定、顶端位移最大（身体侧摆）；`sine`=两端固定、中段最大（呼吸）；
  `linear`=线性；`tip`=顶固定、底端最大（后发/裙摆/尾巴）。
  X 与 Y **各有独立曲线**（早期共用一个字段，后写的通道会覆盖先写的，导致侧摆变成"中段鼓包"）；
- 尚缺"部件内细分网格（多控制点）"与"顶点级遮罩"，已列入 `PRODUCT_PLAN.md` 缺口（T12.6）。

### 结论二：本地与云端的分工（"AI 模仿动漫角色唱歌"）
- 那些视频用的是 **歌声转换（SVC）**：So-VITS-SVC / RVC 训练目标音色，再把歌声转成该音色；或 DiffSinger 直接合成歌声。**本地完全可以跑**（GPU 4–8 GB），云端只是算力替代。
- **合规红线不变**：不能克隆真人声音、不能拿商业角色音源训练（见 `docs/TRAINING.md` 第六节）。
- "小寻会唱歌"的正确路线：用自己的音色模型 → TTS 唱句 + 音高对齐，或用 SVC 转换自有录音。见 `TRAINING.md` 第十节。


---

## 2026-10-13（第二批查证）口型音素：先翻五个桌宠项目的源码，再上网

用户要求：**做测试软件 / 新功能之前先参考那五个桌宠项目，不会的上网找资料，不要闷头做。**
本轮做 I/U/E/O 四音素口型（T2.1.3），查证过程如下（沙箱里克隆 3 GB 不现实，
改用 `gh api repos/<owner>/<repo>/git/trees/HEAD?recursive=1` 列目录 + `-H "Accept: application/vnd.github.raw"` 取单文件）。

| 项目 | 查的文件 | 拿到什么 | 用在哪 |
| --- | --- | --- | --- |
| **airi**（moeru-ai/airi，MIT） | `packages/model-driver-lipsync/src/shared/wlipsync/vowel-driver.ts`、`src/live2d/index.ts`、`README.md` | 母音驱动的**完整策略**：raw AEIOU**S** → 五母音（S 当静默并入 I）；`amp = min(volume*0.9,1)^0.7`；每帧只取**赢家 + 亚军**（上限 0.7 / 0.35）而不是五个口型一起糊；静默判据 `amp<0.04 or winner<0.05` 且带 **160 ms 保持**；平滑是**张开 50/s、回落 30/s 的两档指数**，末了 `≤0.01 归零` | 我们的 `viseme_update()`：attack 50 / release 30、收干净自动松口；`zrig_viseme_set(音素, 权重)` 就是"赢家母音 + 当前响度"这套口径 |
| **BongoCat（Rust）**（ayangweb/BongoCat，Apache-2.0） | `crates/bongocat-live2d-playback/src/motion/{sample.rs,weight.rs}` | ① 动作求值要分三种样本：**参数样本按曲线权重缩放、部件不透明度不缩放、模型级（eyeBlink/lipSync）另算**；② 淡入淡出用 `0.5-0.5*cos(πt)` 的**正弦**权重，不是线性——"线性像机器被关掉，正弦才像动作结束" | 记进待办：我们的动作淡化目前是线性，改正弦是 🟢 级小改（已登记在 CONFORMANCE 第四节） |
| **BongoCat（C+SDL3）**（vladelaina/BongoCat，AGPL） | 仓库树（526 文件）全文件名扫描 | 没有 lip/mouth/viseme 相关实现（它是键鼠驱动的贴图切换，不是参数模型） | 结论：这条路线对音素口型无参考价值，**不再反复翻**（AGPL 也不能抄） |
| **VPet**（LorisYounger/VPet，Apache-2.0） | 仓库树（7652 文件）扫描 | 同样没有 viseme/mouth 参数层：VPet 的说话是**序列帧动画**，不是参数驱动 | 结论：口型这块不参考它；它的价值仍在交互语汇与 Mod 接口 |
| **ds-local-pet**（QCYTSN/ds-local-pet，MIT） | 仓库树 + `animation/clip.py` | 只有动画片段调度，没有口型 | 同上 |

网络资料（白名单内可达的部分 + 搜索摘要，URL 均记录在此）：

| 来源 | 结论 |
| --- | --- |
| Live2D 官方《Standard Parameter List》 `https://docs.live2d.com/en/cubism-editor-manual/standard-parameter-list/` | 嘴只有 `ParamMouthForm`（-1..1，**+ 笑 / − 怒**）与 `ParamMouthOpenY`（0..1）；**没有** `ParamMouthA/I/U/E/O` |
| Animaze（FaceRig 后继）《Live2D Model Requirements & Animation Standards》 `https://www.animaze.us/manual/gettingstarted2d/paramlist` | 整张 viseme→Live2D 映射表都落在 `ParamMouthOpenY` + `ParamMouthForm` 上（AA/AH/AO/OY/EH/IH/EY/W/M/N/CH/FV…）；`ParamMouthSize`、`ParamLipUpper/Under`、`ParamTooth`、`ParamTongue` 都标注为**非标准扩展** |
| Live2D 制作向教程（母音認識方式） `https://shiroikarasu.net/live2d-blink-lipsync-setting-guide-2026/` | 口型同步两种方式：**音量连动**（只动 OpenY）与**母音認識**（事先做好 あいうえお 的 OpenY×Form 组合 keyform 再切换）；并明说 **ParamMouthForm 不是母音参数本身** |
| pixi-live2d-display 的口型实践 `https://github.com/itorr/itorr/issues/7` | 社区常见做法仍是只驱动 `ParamMouthOpenY`（频谱 0–700 Hz 求均值）；要更细就得自己做母音 | 

**采纳结论**：不自造 `ParamMouthA/I/U/E/O`，改为一张「音素 → 标准参数取值」表（`rig.json` 的 `visemes`），
驱动口径学 airi（赢家母音 + 响度 + 两档平滑）。详见 `docs/LIVE2D_CONFORMANCE.md`。


## 2026-10-13（第三批查证）表情 × 口型抢同一个参数：先查官方 SDK 的执行序

用户要求（已重申两次）：**动手做之前先翻那五个桌宠项目，查不到的上网找资料，不要闷头做。**
本轮要定的是"笑着说う，嘴听谁的"，查证路径和结论如下
（仍是 `gh api .../git/trees/HEAD?recursive=1` 列树 + `-H "Accept: application/vnd.github.raw"` 取单文件，不整克隆）。

| 来源（全部为只读查证，不复制代码） | 文件 | 拿到的关键结论 |
| --- | --- | --- |
| **Live2D/CubismWebFramework**（官方 SDK，Live2D Open Software License） | `src/motion/icubismupdater.ts` | **执行序枚举**：`EyeBlink=200`、`Expression=300`、`Drag=400`、`Breath=500`、`Physics=600`、**`LipSync=700`**、`Pose=800`；`CubismUpdateScheduler` 按 `_executionOrder` 排序执行 → **口型排在表情之后** |
| 同上 | `src/motion/cubismexpressionmotion.ts` | exp3 的 `Blend` 三值 `Add` / `Multiply` / `Overwrite`；缺省 `DefaultAdditiveValue=0.0`、`DefaultMultiplyValue=1.0`；`calculateExpressionParameters` 维护 **三个累加器**并按 `fadeWeight` 线性混，最后 `(overwrite + additive) × multiply` |
| 同上 | `src/motion/cubismlipsyncupdater.ts` | `onLateUpdate` 对 `_lipSyncIds` 逐个 `addParameterValueById(id, value)`；**官方 LipSync 组只含 `ParamMouthOpenY`** |
| **Live2D/CubismWebSamples** | `Samples/TypeScript/Demo/src/lappmodel.ts` | 旧写法 `_model.addParameterValueById(_lipSyncIds.at(i), value, 0.8)` → **官方 LipSync 权重就是 0.8**；新版已改用 `CubismUpdateScheduler` + 各 `*Updater`，`addUpdatableList` 的**调用顺序不是执行顺序** |
| **ayangweb/BongoCat**（Apache-2.0，只学思路） | `crates/bongocat-live2d-playback/src/expression.rs` | `evaluate_expression_parameter(id, base, layers)` 是**纯函数**：`overwrite=base / additive=0 / multiply=1`，逐层 `x += (next − x) * layer.weight`，返回 `(overwrite + additive) * multiply`；`Blend` 缺省 `Add`；刻意不碰 Cubism Core，由调用方回写 |
| vladelaina/BongoCat、VPet、ds-local-pet | 仓库树扫描 | 仍然没有表情层/混合模式实现（贴图切换或序列帧路线）→ 这三个对本题无参考价值，**不再翻** |

**采纳与偏差**：

1. 执行序照搬：我们的一帧 = 动作 → Pose → 参数 + 表情 → **口型** → 跟随 → 物理。
2. 表情求值照搬三累加器，并补上第三种混合 `multiply`（原先只有 add / set）。
3. **一处有意偏差**：官方 LipSync 是 `addParameterValueById(id, v, 0.8)` 纯加算，
   那是因为官方的 LipSync 组只驱动 `ParamMouthOpenY`（单调开合，加算不会打架）。
   我们把 `ParamMouthForm` 也纳入音素层（五张嘴必须有嘴形），纯加算会让
   「笑(+0.7) + う(−1.0)」抵消成 −0.3 的中性嘴。改成
   `v = 音素值 + (表情后的值 − 默认值) × (1 − viseme_weight)`，`viseme_weight` 默认仍取官方的 **0.8**。
   登记在 `docs/LIVE2D_CONFORMANCE.md`（「表情和口型抢同一个参数时谁说了算」一节），
   并有 `test_expr_viseme_order()` + 3 次负控守着。
4. 测试台的分层看板（`value / 过表情后 / 最终` 三列）思路取自 airi devtools 的分层显示：
   调参数时能看见每一层各自贡献了多少，而不是只看最终一个数。

## 2026-10-13（第四批查证）验收反馈的三件事：眨眼开关的语义、口型接管力度、整句松口

> 背景：用户在测试台上看到两件事 ——「小寻一直闭眼」「张嘴时微笑衔接过慢，张嘴了微笑还在」。
> 按既定规矩，动手前先翻五个桌宠项目和官方 SDK，不闷头改。

### 1. `blink_enabled` 到底该管到哪一层（官方 CubismEyeBlink）

- `Live2D/CubismWebFramework` → `src/effect/cubismeyeblink.ts`
  （`gh api repos/Live2D/CubismWebFramework/contents/src/effect/cubismeyeblink.ts`）：
  `updateParameters()` 的状态机是 `First → Interval → Closing → Closed → Opening`
  （和我们的五态一一对应），**最后一步只是**
  `for (...) model.setParameterValueById(this._parameterIds[i], parameterValue)`。
  也就是说官方的眨眼器**只写参数**，写完就不管了；画成什么样是 `CubismModel.update()`
  按参数值算的，**和"眨眼器开没开"没有任何关系**。官方甚至没有 enabled 开关：
  不想自动眨眼就不把 `CubismEyeBlinkUpdater` 加进调度器（`lappmodel.ts:298-303`）。
- 结论（本轮据此修的 bug）：`blink_enabled` 只能管"自动眨眼的定时器要不要跑"，
  **绝不能出现在"这一帧眼睛画成什么样"的判断里**。我们原来的
  `if (r->blink_enabled && blink > 0.001) { 睁眼件淡出；闭眼件淡入 }` 违反了这一条：
  关掉自动眨眼以后，任何把闭合度推离 0 的东西（表情的 `ParamEyeOpen=0.85`、手动按住、
  动作的 `blink_hold`）都会跳过淡化，闭眼件以 100% 不透明盖住睁眼件 → **一上表情就全闭眼**。
- 另一处值得抄的做法：`lappmodel.ts:685` 在播动作时调
  `motion.setEffectIds(this._eyeBlinkIds, this._lipSyncIds)` —— 官方把"眨眼参数"和
  "口型参数"单独标出来，让 motion 曲线对它们**让路**而不是硬覆盖。
  这正是我们 `blink_hold`（动作只抬不压闭合度）和 `zrig_set_mouth_mute`（动作嘴通道让路）
  在做的事，口径一致，保留。

### 2. 口型接管力度要不要随"这一帧嘴用了多大力"变（五个桌宠项目 + airi）

- 五个桌宠项目里只有 **airi** 有口型层：`model-driver-lipsync/.../vowel-driver.ts`
  的做法是「赢家母音 + 响度」两路 —— 母音决定**写哪张嘴**，响度决定**写多重**，
  小声时参数幅度本来就小。它没有"表情层"，所以不存在抢参数的问题。
- 我们有表情层，于是把"响度"这一路翻译成**接管权重**：
  `w = viseme_weight × viseme_activity`，`viseme_activity` = 本帧口型相对默认值用了多大力（0..1）。
  静音 SIL=0（表情全额拿回嘴）、小声=按比例（笑意透出来）、满力「あ」=1（口型独占）。
  这是官方没有的扩展，已登记进 `docs/LIVE2D_CONFORMANCE.md` 的偏差表。
- `viseme_weight` 从官方 LipSync 的 0.8 调到 **1.0**：0.8 是官方给"只驱动 `ParamMouthOpenY`"
  定的，我们还驱动 `ParamMouthForm`，残留 20% 的笑在满口型上肉眼可见（用户看到的就是这个）。

### 3. 整句说完怎么收口（没有现成答案，取 airi 的两档思路自己定）

- airi 的 vowel driver 只有一组 attack/release（50 / 30 每秒）用于**音素之间**切换，
  整句结束靠"静默 160ms 保持 + 响度归零"自然收，它的嘴只有开合、收得快也看不出。
- 我们收的是嘴形（Form 从 −1.0 回 +0.70 跨度 1.7），同样 30/s 收尾仍是 0.267 的单帧跳变，
  肉眼就是"抽一下"。于是加第二档 **`ZRIG_VIS_RELEASE_OFF = 8.0`**（整句松口专用，
  比音素间慢近四倍），实测单帧跳变降到 < 0.12，约 1.8s 平滑叹回表情。
  12.0 试过仍有 0.122 的跳变，所以定 8.0。

## 2026-10-13（第五批查证）笑眼 `ParamEyeLSmile` / `ParamEyeRSmile` 怎么做

> 规矩照旧：先翻五个桌宠项目和官方 SDK 的真实数据，再上网看做模型的人怎么说。

### 1. 官方模型里笑眼到底怎么用（Live2D/CubismWebSamples 的 Haru）

`gh api repos/Live2D/CubismWebSamples/contents/Samples/Resources/Haru/expressions/F0x.exp3.json`
把八个表情全拉下来，眼睛相关的写法是：

| 表情 | 眼睛部分 | 读出来的意思 |
| --- | --- | --- |
| **F05** | `ParamEyeLOpen=0 (Multiply)`、**`ParamEyeLSmile=1 (Add)`**、右眼同、`ParamBrowL/RY=0.32 (Add)` | **笑眼 = 先把眼睛关到 0，再把笑眼开到 1**，眉毛抬 0.32 |
| F04 / F07 / F08 | `ParamEyeLOpen=0.8 / 0.89 (Multiply)` | 眯眼是**乘**出来的（不管此刻眨眼到哪一步，乘一下就行） |
| F06 | `ParamEyeLOpen=2 (Multiply)` | 瞪大：官方自己会把参数推到 1 以外 |

→ 这就是我们这次的实现依据：笑眼不是"另一种睁眼"，是**另一种闭眼**。
我们让笑眼自己隐含闭眼（`blink = max(blink, smile)`），调用方推一个参数就够，
官方那种"两个参数一起写"的写法也照样成立（`max` 不会把眼睛又睁开）。

### 2. 做模型的人怎么说（四篇独立教程口径一致）

- 伊糖だねこ《Live2D練習記録③ 目》 https://note.com/itodaneko/n/n7d73fd172f6d
  —— 「笑顔の目は閉じている状態になるので、笑顔を作るときは**開閉のパラメータは 0 に合わせておきます**」。
- するめいか《目の作り方を解説》 https://surume1ka.com/archives/2226
  —— 「**目の開閉パラメータ値 0.0（閉眼）の状態で**、笑顔のパラメータに紐づけて下さい」。
- 愛《谷型の閉じ目から『笑顔の閉じ目』を作る手順》 https://note.com/hoshinotomoshibi/n/n0538bd256cf1
  —— 标题即结论：**谷型（∪）闭眼 → 山型（∩）笑眼**，睫毛、下睫毛、白目、卧蚕逐个往山型弯。
- CGbox《基本の表情！綺麗に笑顔を作る方法》 https://cgbox.jp/2020/04/14/live2d-smile/
  —— 参数范围 0~1、两点キー；另提到"笑眼时还要不要眨眼"是取舍（我们选"笑眼期间不再被眨眼打断"）。
- 官方标准参数表 https://docs.live2d.com/en/cubism-editor-manual/standard-parameter-list/
  —— `ParamEyeLSmile` **min 0 / default 0 / max 1**，"Make smiley eye when +"。

→ 贴图版的等价做法：**再 AI 重绘一张"山型笑眼脸"，走闭眼那条同样的流水线切补片**
（`tools/make_eye_closed_parts.py --variant smile`），位置、配准、肤色对齐、羽化全部复用，
只是底图换一张。切出来两件 57×56 / 57×58，和闭眼件**同位同尺寸**。

### 3. 五个桌宠项目的做法（确认没有可抄的参数层）

- **VPet**（`gh api repos/LorisYounger/VPet/git/trees/HEAD?recursive=1`）：
  `mod/0000_core/pet/vup/Default/Happy/1/循环A_000_125.png` …… 每种情绪一整套**逐帧 PNG 序列**
  （文件名尾数就是帧时长 ms）。印证了"2D 桌宠的笑眼普遍是另画一张，不是把睁眼变形"，
  但它没有参数层，没法抄口径。
- **airi**：`packages/stage-ui-live2d/src/utils/eye-motions.ts` 里不是笑眼，是**扫视（saccade）间隔分布** ——
  `EYE_SACCADE_INT_P` 用累积概率挑 0~3200ms 的间隔。这个以后做视线微动（G4 跟随）时直接能用。
- bongocat-sdl / bongocat-tauri / ds-local-pet：确认无表情参数层（第二批已扫过，不再重复翻）。

## 2026-10-13（第六批查证）动作曲线只能打在什么上？

> 这一批是为"18 个动作从部件通道迁到参数通道"查的。

### 1. 官方把答案写死在三个常量里

`gh api repos/Live2D/CubismWebFramework/contents/src/motion/cubismmotion.ts`

```ts
const TargetNameModel = 'Model';
const TargetNameParameter = 'Parameter';
const TargetNamePartOpacity = 'PartOpacity';
```

`parse()` 里只认这三个，其它一律 `CubismLogWarning('Unable to get segment type from Curve!')`。
`doUpdateParameters()` 按这三类**分段顺序处理**（Model 段 → Parameter 段 → PartOpacity 段）：

- `Model` 段只认三个特殊 id：`Opacity`、`EyeBlink`、`LipSync`
  （前两个是给眨眼/口型"让路"用的系数，不是画面本身）。
- `Parameter` 段：`model.getParameterIndex(curve.id)` → 写参数值。
- `PartOpacity` 段：同样按 id 找，写部件不透明度。

→ **结论：Live2D 的动作不能直接写"某个部件挪几个像素"。** 位移/旋转/缩放只能是
参数经过变形器（ワープデフォーマ / 回転デフォーマ）产生的结果。
我们的 `actions[].channels` 以前 197 条全是"写部件几何"，这是**唯一一个结构性偏差**，
这一轮清掉了。

### 2. 官方动作数据长什么样（拿真文件数一遍）

`Samples/Resources/Haru/motions/haru_g_m01.motion3.json`（`Duration 2.9 / Fps 30 / CurveCount 63`）：

| Target | 条数 | 例子 |
| --- | --- | --- |
| `Parameter` | **42** | ParamAngleX/Y/Z、ParamBodyAngleX/Y/Z、ParamArmLA/RA/LB/RB、ParamBrow*、ParamMouthForm/OpenY、ParamHairFront、ParamBreath、ParamEyeBallX/Y… |
| `PartOpacity` | 20 | `Part01Core`、`Part01Eye001`、`Part01Mouth001`… |
| `Model` | 1 | `Opacity` |

曲线段类型统计：bezier 60 / linear 63 / stepped 20（`Meta.AreBeziersRestricted = true`）。
→ 我们现在是 `linear / smooth / step`，贝塞尔属于后补的纯增量项（合规表里记在 🟢）。

→ 另一个收获：官方参数名表和我们的命名**几乎一一对应**，说明前面几轮"对齐标准参数名"
的方向是对的，`ParamArmLA/LB` 这种我们照搬的名字在官方模型里就是这么用的。

### 3. 官方的 ParamBreath 是怎么被驱动的

`CubismBreath`（`src/effect/cubismbreath.ts`）：`value = offset + peak * sin(t * 2π / cycle)`，
默认那组参数就是 `ParamBreath, offset 0.5, peak 0.5, cycle 3.2345, weight 0.5` —— **0..1 的单向值**。
我们的波形通道以前只有振幅没有偏置，纯正弦会被 `ParamBreath` 的下限 clamp 掉半个周期，
所以这轮给通道加了 `bias` 字段（就是官方的 offset）。


---

## 第七批（2026-10-13）：动作淡入淡出的官方口径

### 1. 缓动曲线只有一条：`getEasingSine`

`Live2D/CubismWebFramework/src/math/cubismmath.ts:107`

```ts
static getEasingSine(value: number): number {
  if (value < 0.0) return 0.0;
  else if (value > 1.0) return 1.0;
  return 0.5 - 0.5 * Math.cos(value * Math.PI);
}
```

官方动作的淡入淡出**只用这一条**。我们原来用的是 `smoothstep = t²(3−2t)`，
两者最大只差 0.0098（t≈0.25 处 0.15625 vs 0.146447）——肉眼完全看不出，
但没有理由保留第二种口径，已统一换掉。
（第四批记的 BongoCat `motion/weight.rs` 的 `0.5−0.5cos(π·progress)` 其实就是这条，
**它抄的是官方**；所以该照的源头是 Cubism 而不是 BongoCat。）

### 2. 淡入和淡出是两个独立权重，相乘

`cubismmotion.ts:417-430`：

```ts
const tmpFadeIn  = this._fadeInSeconds <= 0.0 ? 1.0
  : CubismMath.getEasingSine((userTimeSeconds - entry.getFadeInStartTime()) / this._fadeInSeconds);
const tmpFadeOut = (this._fadeOutSeconds <= 0.0 || entry.getEndTime() < 0.0) ? 1.0
  : CubismMath.getEasingSine((entry.getEndTime() - userTimeSeconds) / this._fadeOutSeconds);
```

要点三条：

1. **FadeOutTime 挂在 motion 身上**，不是挂在"下一个动作"身上——
   一个动作怎么收尾，由它自己说了算。
2. **`getEndTime() < 0` 就不淡出**，这正是循环动作（loop）的表示法。
3. 最终 `paramWeight = this._weight * fin * fout`（`:564`），
   每条曲线还能用 `curve.fadeInTime / fadeOutTime` 覆盖整段的值（`:542-559`），
   没写（<0）就用整段的 `tmpFadeIn / tmpFadeOut`。曲线级的 fade 我们暂不做，
   记在这里备查。

写参数时官方是 `v = sourceValue + (value - sourceValue) * fadeWeight`（`:535`）——
**插值覆盖**，不是累加。我们是累加模型，这处差异已登记在
`docs/LIVE2D_CONFORMANCE.md` 的「动作的淡入淡出」表里。

### 3. 还该参考哪些项目（回答"除了那五个桌宠还需要什么类型"）

五个桌宠项目（bongocat-sdl / bongocat-tauri / ds-local-pet / vpet / airi）能回答的是
**"桌宠该长什么样、交互怎么接"**；回答不了**"等价于 Live2D 的引擎内部该怎么写"**，
也回答不了训练、网关、计费这些后端问题。按我们还没做完的模块各补一个对口的参考，
下面九个**全部已验证可达**（`gh api repos/...`，2026-10-13 实测）：

| 仓库 | ★ | 许可 | 对口我们的哪一块 |
|---|---|---|---|
| **`Inochi2D/inochi2d`** | 1811 | BSD-2 | **最同构的一个**：开源的 Live2D 等价引擎，deformer / physics / 参数系统全部开源可读（Live2D 本体只开源 runtime，不开源编辑器那套数据结构）。我们做 G15 网格顶点级编辑、裙摆多段摆链时该先读它 |
| `guansss/pixi-live2d-display` | 1508 | MIT | 第三方 Live2D 运行时：**motion queue / 优先级抢占**的完整实现，正是我们「累加模型 → 插值覆盖模型」那一步要参考的 |
| `EsotericSoftware/spine-runtimes` | 5316 | 专有许可（只读思路） | 2D 骨骼 / 网格 / IK 的工业级做法，对两级手臂往上加 IK 有用 |
| `DragonBones/DragonBonesCPP` | 434 | MIT | C++ 的 2D 骨骼运行时，和我们同语言，数据结构可直接对照 |
| **`DanielSWolf/rhubarb-lip-sync`** | 2650 | 需确认 | 从音频提 A–H 口型，**G19「LipSync 接 TTS 包络」最对口的参考** |
| `rhasspy/piper` | 11299 | MIT | 本地 TTS。音色被否过两次（见 LESSONS），但它的**音素时间轴输出**对口型有用 |
| `SillyTavern/SillyTavern` | 34397 | AGPL-3.0 | 角色卡 / 世界书 / 记忆的成熟形态，对人格与记忆区。**AGPL，只读思路不抄代码** |
| `kohya-ss/sd-scripts` | 7242 | Apache-2.0 | 训练区 G12 的 LoRA 事实标准实现 |
| `songquanpeng/one-api` | 37132 | MIT | 网关 G2 / 计费 G3：多家 LLM 的渠道管理、配额与计费，整套都做好了 |

排序即优先级：**Inochi2D 和 pixi-live2d-display 是动画底层还没做完那部分的首选**，
rhubarb 在排到 G19 时读，其余按模块排期到了再读。

**查证方式不变**：`gh api repos/<owner>/<repo>/git/trees/HEAD?recursive=1` 列文件 →
grep 定位 → `contents/<path>` 取单文件，不整克隆；读到的结论连同 URL 回写本文件。


---

## 第八批（2026-10-13）：裙子的物理该怎么做

### 1. 先翻遍官方示例，看谁给裙子做了物理

`gh api repos/Live2D/CubismWebSamples/...`，8 个模型的 `PhysicsDictionary`：

| 模型 | 组数 | 名字 |
|---|---|---|
| Haru | 4 | 前髪 / 横髪 / 後ろ髪 / **スカーフ** |
| **Hiyori** | 11 | 前髪 / 後ろ髪 / リボン髪 / **スカート　横揺れ** / **スカート　縦揺れ** / リボン体 / 胸揺れ / サイドアップ左右 / 横髪左右 |
| Mao | 16 | …帽子つば / 帽子リボン / 羽 / パーカーひも / 首飾り / **ローブ揺れ** / **ローブ揺れY** |
| Natori | 11 | …燕尾揺れ / 懐中時計腰 / 腰のチェーン |
| Ren | 16 | 体X / 重心 / 体Y / 肩 / …襟ひも / ネックレス / **ジャケット** |
| Rice | 9 | 後髪ABC / 左右横髪 / 前髪 / 頭リボン / 胸リボン / 腰リボン |
| Mark | 1 | 髪揺れ |
| Wanko | 4 | お椀揺れ / 揺れ / 右耳 / 左耳 |

**Haru 这种"只给头发 + 一条围巾"的最常见；真给裙子做物理的是 Hiyori**，
而且 Mao 的ローブ（长袍）也是 **X 和 Y 分成两组**——这是布料的通用写法。

### 2. Hiyori 的裙子怎么配的（本轮直接照抄的拓扑）

```
## スカート　横揺れ
   IN  ParamBodyAngleX  type=X      weight=100
   IN  ParamBodyAngleZ  type=Angle  weight=100
   OUT ParamSkirt       type=Angle  vIdx=1 scale=1.434 weight=100
    v0 pos=(0,0)  mob=1   delay=1   accel=1   radius=0
    v1 pos=(0,10) mob=0.9 delay=0.6 accel=1.5 radius=10

## スカート　縦揺れ
   IN  ParamBodyAngleY  type=X      weight=100
   OUT ParamSkirt2      type=Angle  vIdx=1 scale=1.306 weight=100
    v1 pos=(0,10) mob=0.8 delay=0.9 accel=2   radius=10
```

读出四条结论：

1. **裙子不是"串成多段"，是横摆、纵摆两条独立通道。** 原计划"裙摆接多段摆链"
   按这个改成了两条单段。
2. **输入只有身体参数，一个头部参数都没有**（对比头发是 `ParamAngleX/Z` 60 +
   `ParamBodyAngleX/Z` 40）。裙子挂在身上，摇头不该带起裙摆——已写成单测。
3. **纵摆比横摆钝**：mobility 0.8 vs 0.9、delay 0.9 vs 0.6、accel 2 vs 1.5。
4. 摆长（v1 的 y）是布料长度的量纲：裙子/围巾 10、头发 8、**胸揺れ只有 3**。

### 3. Inochi2D 的阻尼口径（比裸写 damping 好用）

`Inochi2D/inochi2d` `source/inochi2d/nodes/legacy/simplephysics.d`：

```d
float lengthRatio = driver.finalGravity / driver.finalLength;
float critDamp = 2 * sqrt(lengthRatio);
float dd = -lengthRatio * sin(angle);
dd -= dAngle * driver.finalAngleDamping * critDamp;
```

它把阻尼表示成**相对临界阻尼的比例**（`angleDamping × 2√(g/L)`），而不是裸系数。
好处是这个数直接读得懂：<1 会回弹、=1 不回弹。我们的弹簧是
`acc = k(target−pos) − c·vel`，对应 **阻尼比 = c / (2√k)**。
照这个口径回头看自己的参数：头发 0.40、裙摆横摆 0.66、裙摆纵摆 0.78 ——
布料比头发钝，和 Hiyori 的 mobility/delay 差异方向一致。
（Inochi2D 还有 `SpringPendulum`，摆长也能伸缩，我们暂时用不上。）


---

## 第九批（2026-10-13）：眉形「変形」参数

### 1. 官方对 `ParamBrowLForm` 的定义

`Haru.cdi3.json`（参数显示名表）：

| Id | Name | 组 |
|---|---|---|
| `ParamBrowLY` / `ParamBrowRY` | 左眉／右眉　上下 | 眉毛 |
| `ParamBrowLX` / `ParamBrowRX` | 左眉／右眉　左右 | 眉毛 |
| `ParamBrowLAngle` / `ParamBrowRAngle` | 左眉／右眉　角度 | 眉毛 |
| **`ParamBrowLForm` / `ParamBrowRForm`** | **左眉／右眉　変形** | 眉毛 |

Haru 的 8 个 exp3 里**六个在用眉形**，而且都是和上下/角度叠着用：

```
F02: BrowY −1,   BrowForm +1
F03: BrowY −1,   BrowX −1, BrowRAngle −1, BrowForm −1
F04: BrowY −0.56, BrowAngle +0.35,        BrowForm −0.74
F08:                                      BrowForm −0.33   （只动变形）
```

### 2. ±1 的方向：社区说法不一，以官方手册为准

搜到的教程里方向**互相矛盾**（有说 −1 生气的，也有说 +1 生气的），
所以以官方 Cubism 手册（`sites.google.com/cybernoids.jp/cubism2/...`）为准：

> 「－１」のときに眉を**しかめるような寄せる形**、「１」のときに**山なりに眉が上がる形**に変形させます。

即 **−1 = 皱眉／聚拢，+1 = 山形隆起**。多数第三方教程（困り眉 ↔ 驚き眉／眉山が上がる）
与这条一致，少数相反的属于作者自定，不跟。

### 3. 最有用的一条：「変形」不许带位置移动

官方手册和多篇教程反复强调同一件事：

> パラメータを設定する時のコツは『上下』『左右』は別のパラメータで設定する作業なので、
> **眉全体の位置が左右上下に移動しない範囲で変形を行う**事

也就是说眉毛的四个自由度是**正交分解**的：上下 = `BrowY`、左右 = `BrowX`、
角度 = `BrowAngle`、形状 = `Form`。Form 的网格如果带净位移，就会和前三个打架
（表情里叠起来会跑位）。我们把这条落成了可核的数值闸：
**中段位移与两端反号，且 `|Σdy| / Σ|dy| < 0.25`**（`selfcheck ⑯`）。

官方手册还提到另一条值得记的工程经验：眉毛的多个动作要**分散到描画オブジェクト和
デフォーマ上**（变形记在网格上、角度/位置记在变形器上），
原因是组合爆炸——"３つの動きを描画オブジェクトとデフォーマに分散させると、
３＋３＋９ で１５パターンで済む"。我们的结构正好是这样：
`Form` 走网格形变器，`Y/X/Angle` 走部件通道。


---

## 第十批（2026-10-13）：桌宠软件的界面怎么做成可扩展的

### 1. VPet 的插件模型（`LorisYounger/VPet`，直接照搬了它的结构）

`VPet-Simulator.Windows.Interface/MainPlugin.cs` —— 插件基类短到可以全文抄在这里：

```csharp
public abstract class MainPlugin {
    public abstract string PluginName { get; }
    public IMainWindow MW;                       // 宿主门面
    public MainPlugin(IMainWindow mainwin) { MW = mainwin; }
    public virtual void LoadPlugin() { }         // 固定生命周期钩子
    public virtual void GameLoaded() { }
    public virtual void EndGame() { }
    public virtual void Save() { }
    public virtual void Setting() { }            // 每个插件自带设置入口
    public virtual void LoadDIY() { }
}
```

`IMainWindow.cs` 是那个**门面**，它给插件暴露：游戏设置、宠物加载器列表、
**所有可用聊天 API**、当前 TalkBox、数据核心、**所有三方插件**（插件之间能互相发现）、
图片/文件资源、以及"显示设置页面（带 page 参数）""设置缩放""保存设置"这些动作。

三条直接搬过来的结论：

1. **组件只认一个宿主门面对象**，不去 import 别的组件、也不直接摸全局 DOM。
   我们的 `host` 就是 `IMainWindow`：`api() / on,emit / state / el,card / refresh() /
   components() / find() / theme(),setTheme()`。
2. **生命周期是固定的几个钩子**，不是自由注册。我们取了 `mount / onInfo / onSpeech / destroy`
   四个 —— `onInfo` 对应 VPet 的 `GameLoaded`（状态到了再填充自己）。
3. **插件之间要能互相发现**（VPet 的"所有三方插件"）。`host.components()` / `host.find(id)`。

`IModInfo.cs` 那边还有一条：模组带 `Name / Author / Intro / Path`，**元信息和实现分开**。
我们的组件也带 `id / title`，布局表里显示用的就是它。

### 2. 为什么是"配置装配"而不是"写死在 HTML 里"

VPet 的模组、airi 的多渲染后端舞台抽象，解决的是同一个问题：
**不改核心代码就能加东西**（这正是用户 A1 那条硬要求）。落到我们这儿：

- `web/layout.json` = 唯一的装配表（哪些组件、哪个区域、什么顺序、给什么参数）
- `web/components/<id>.js` = 组件自己 `ZC.register({...})`
- `web/themes/<id>.json` = 一张 CSS 变量表

加一个卡片 = 放一个文件 + 在 layout 里写一行，`index.html` 和 `app.js` 都不用动。

### 3. 没有浏览器怎么测界面

沙箱里没有浏览器，但 node 有。`tests/test_web.js` 用一个 ~90 行的 DOM stub
（createElement / appendChild / classList / querySelectorAll / dataset / style）
把 `app.js` 和九个组件**真的跑一遍**：按 layout 装配、推一次 `info`、点几个按钮，
断言 DOM 结构、挂载区域、挂载顺序、发出去的请求 URL 和换算后的点击坐标。
脚本标签的"插进 head 就执行"也模拟了，所以**内核按配置动态加载组件**那条路是真的走过的。


---

## 第十一批（2026-10-13）：全能桌宠平台的框架该怎么搭

用户这轮要的是"API 连接 / token 余额 / 聊天 / 任务 / 工作区 / 文件区 / 记忆区 /
代理 / skills / 生图生视频生代码生建模 / 本地与网络 AI 都兼容 / 陪伴 /
neuro-sama 模仿开源项目 / 真正的思考载入"，并且明确**先把框架做好**。
下面是动手前查的六个项目（`gh api` 2026-10-13 实测全部可达）。

| 仓库 | ★ | 许可 | 看它什么 |
| --- | --- | --- | --- |
| `moeru-ai/airi` | 50347 | MIT | **就是 neuro-sama 的开源重建**（README 原话 "Re-creating Neuro-sama"）。用户点名的那类项目，我们从第四批起就在参考 |
| `heshengtao/super-agent-party` | 2733 | AGPL-3.0 | 自称 "Self hosted neuro sama"。**功能面和用户要求几乎一一对应**；skills 目录结构直接可借鉴（只看结构，AGPL 不抄实现） |
| `elizaOS/eliza` | 19586 | MIT | 自称 "agentic operating system" |
| `KroMiose/nekro-agent` | 1142 | — | "集 Claude Code 沙盒执行、工作区编排、长期记忆" —— 和我们的 L1/L5 完全对口 |
| `songquanpeng/one-api` | 37134 | MIT | 多供应商分发与计费 |
| `modelcontextprotocol/servers` | 91210 | — | MCP 工具生态 |

### 1. skills 的格式：不要自造，Agent Skills 已是事实标准

`super-agent-party` 的 `skills/` 目录：

```
skills/skill-creator/SKILL.md          ← 连"造技能的技能"都有
skills/find-skills/SKILL.md
skills/officeCLI/SKILL.md
skills/sap-extension-creator/
    SKILL.md
    assets/node-template/...           ← 可带模板
    references/node-entry-spec.md      ← 可带规格文档
```

`SKILL.md` 的头部是 YAML frontmatter：

```markdown
---
name: skill-creator
description: Guide for creating effective skills. This skill should be used when
             users want to create a new skill ... 
license: Complete terms in LICENSE.txt
---
# Skill Creator
## About Skills
Skills are modular, self-contained packages that extend Claude's capabilities ...
### Concise is Key
The context window is a public good. ...
```

三条要点：
1. **`description` 要写"什么时候该用它"**，不是"它是什么" —— 因为模型是靠这句话决定要不要加载。
2. **正文是给模型看的操作手册**，不是给人看的介绍。
3. **上下文是公共资源**（原文 "The context window is a public good"）：
   skill 的元信息常驻、正文按需加载，所以描述要短、正文要分文件。

结论：我们的 `skills/<name>/SKILL.md` **直接采用这套**，整个 Claude Skills 生态的技能包可以原样放进来。

### 2. eliza 的插件装载（`packages/agent/src/runtime/plugin-types.ts`）

关键字段：`dropInRecords`（丢进目录就装）、`installRecords`、
`corePluginNames`（核心插件不可卸）、`denyList`（黑名单）、`pluginsToLoad`、
`accepted/skipped`。插件从 package 的 `exports` 解析入口。

学到的：**装载要区分"核心/第三方"，要有黑名单，要记录"装了什么、跳过了什么"**。
我们的 provider / capability 注册表照这个思路：`enabled` 开关 + 校验时报告"跳过了谁"。

### 3. 为什么能力要和供应商解耦

`one-api` 的本质就是"一个接口后面挂 N 家供应商"。我们把它推到能力粒度：
调用方说 `image.generate`，不说"调 OpenAI"。好处有三个，都直接对应用户的要求：

- **本地与网络都兼容**（A17）：同一个能力，底下可以是 ComfyUI 也可以是 OpenAI；
- **token 余额识别**（A10）：余额是**供应商**的属性（`balance.mode`：api / ledger / none），
  本地供应商天然 `none`；
- **"2027 年以内所有事"**（A18）：新能力只是多一份契约文件，内核不改。

---

## 第十二批（2026-10-13）：网关怎么做（G51 动手前查的）

动手写 `zgateway` 之前查的，全部来自实际源码而不是猜。

### `songquanpeng/one-api`（★37134，MIT）—— 路由表是**预计算的反向索引**

`model/ability.go`：

```go
type Ability struct {
    Group     string  // 用户组
    Model     string  // 模型名
    ChannelId int     // 渠道（= 我们的供应商）
    Enabled   bool
    Priority  *int64
}
func GetRandomSatisfiedChannel(group, model string, ignoreFirstPriority bool) (*Channel, error)
```

要点三条，我们全都照搬了：

1. **路由不是每次请求去遍历配置算的**，而是维护一张 `(group, model) → channel` 的索引表。
   我们对应的是 `config/gateway_routes.json`，由 `tools/check_platform.py` 从契约物化，
   **顺序即优先级**，运行时取第一个 enabled 的就是首选。
2. **按 priority 分层**：先取最高优先级的那批，组内随机。
   我们是单机单用户，不需要随机负载均衡，所以组内按 id 稳定排序——
   **稳定比随机重要**，否则同样的配置每次路由到不同的家，问题没法复现。
3. `ignoreFirstPriority` 是**重试时降级**用的：首选那批全挂了才往下走。
   我们对应 `zgw_pick(..., attempt, ...)`，attempt 递增就是依次降级。

`relay/adaptor/interface.go` 的 `Adaptor` 接口九个方法，分四段：
`Init` → `GetRequestURL`/`SetupRequestHeader`/`ConvertRequest` → `DoRequest` → `DoResponse`（返回 `usage`）。
**`usage` 是从响应里出来的**，所以记账只能在响应之后——这就是为什么要有预扣。

`relay/billing/billing.go`：**预扣 / 结算 / 退还三段式**。

```go
func ReturnPreConsumedQuota(ctx, preConsumedQuota int64, tokenId int)      // 退还
func PostConsumeQuota(ctx, tokenId, quotaDelta, totalQuota int64, ...)     // 结算
```

关键细节：**结算入账的是实际用量，预扣只是占位**。
我们的 `zgw_hold_settle(g, id, tin, tout, actual)` 入的是 `actual` 而不是 `h->estimated`，
单测和 selfcheck 各有一道闸盯着这件事（写错的话用户会按估算值被扣钱）。

### 余额查询：**没有统一标准，四家四种算法**

`controller/channel-billing.go` 里实测到的端点与算法：

| 家 | 端点 | 怎么算 |
|---|---|---|
| DeepSeek | `/user/balance` | 直接取 `balance_infos[0].total_balance` |
| OpenRouter | `/api/v1/credits` | `total_credits − total_usage` |
| credit_grants 式 | `/dashboard/billing/credit_grants` | `total_granted − total_used` |
| OpenAI 订阅式 | `/v1/dashboard/billing/subscription` + `/usage` | `hard_limit_usd − total_usage/100`（**要两个端点**） |

→ 这条直接推翻了 G50 里 `balance: {mode, path}` 的设计：一个 `path` 表达不了减法，
也表达不了"从哪个字段取"。改成 `{mode, endpoint, pick, minus?, currency}`，
校验器强制 `mode=api` 必须给 `endpoint` + `pick`，还会拦住继续用老 `path` 的写法。
**OpenAI 订阅式要两个端点，当前契约表达不了，记为已知限制**（它那个端点新账号还常 404，
所以更该支持"查不到就退回 ledger"）。

### `moeru-ai/airi` —— 插件**不持有**供应商，只向宿主查询

`packages/plugin-sdk/.../resources/providers/index.ts`：

```ts
export const protocolListProvidersEventName =
  'proj-airi:plugin-sdk:apis:protocol:resources:providers:list-providers'
export const protocolListProviders = defineInvokeEventa<{ name: string }[]>(...)
```

供应商发现是一条**控制面 RPC**，插件声明权限后向宿主要列表。
和我们 L4/L3 分界是同一个主张：**调用方不知道也不该知道底下是谁**。

## 第十三批 · 云端 TTS 音源选型（2026-10-14）

起因：用户要求**去掉本地音源**，换成**云端标准音色**，要有**少女/萝莉/青年女性**、
偏**二次元**、能**变声调语气和情绪**、**每个 AI 声音都不一样且不能同一种生源**。
本地 Piper 方案此前已被用户两次否掉（"机械音"），这次整块删除。

### edge-tts（现用的免费通道）
- `github.com/rany2/edge-tts` README 原话：**"Support for custom SSML was removed because
  Microsoft prevents the use of any SSML that could not be generated by Microsoft Edge itself"**
  —— 服务端只接受单个 `<voice>` 里的单个 `<prosody>`。
  **结论：edge-tts 永远做不了 style/情绪**，只有 rate / volume / pitch 三个旋钮。
  想"用 SSML 注入 style 绕过去"是死路，不要试。
- `ai-daily.tech/p/edge-tts-pipeline/`：`--list-voices` 共 **322 个音色，中文只有 14 个**
  （普通话 8 + 粤语 3 + 台普 3）。普通话女声实际只有晓晓（温暖）、晓伊（活泼/卡通）、
  辽宁小北（东北）、陕西小妮（陕西）—— 挑不出"萝莉"和"御姐"。
- `smartsub.linxiaodong.com/guides/tts/edge-tts`：它是**逆向接口**，**2025-12 曾大规模断供**，
  原文不建议作主力。→ 必须有降级链，不能只靠它。
- 负值参数要写成 `--rate=-50%`（等号不能省，否则被当成另一个 flag）。

### Azure Speech（定为主力）
- Voice Gallery（speech.azure.cn）+ `docs.azure.cn/.../speech-synthesis-markup-voice`：
  情绪走 SSML 的 `<mstts:express-as style="..." styledegree="..." role="...">`。
- zh-CN 带 style 的音色：XiaoxiaoNeural（19 种 style）、XiaoyiNeural（9 种）、
  XiaohanNeural（10 种）、**XiaomoNeural（12 种 style + Role：Boy/Girl/YoungAdultFemale/
  OlderAdultFemale/SeniorFemale —— 一把嗓子能演三个形态）**、XiaoshuangNeural（儿童音，但只有 chat）。
- **Multilingual 系列**（≈91 种语言，同一把嗓子说中/日/英）：XiaoxiaoMultilingual、
  **XiaoyouMultilingual（angelic/child，含 cute）**、XiaoshuangMultilingual（cute and lovely, child）。
- `learn.microsoft.com/.../high-definition-voices`：**DragonHD Flash 最贴二次元** ——
  `zh-CN-Xiaoyi:DragonHDFlashLatestNeural` 有 **cute / shy / nervous / complaining**；
  还支持副语言标签 `laughter / breathing / sighing / yawning`。只支持 zh-CN 和 en-US。
- 额度：**每月 50 万字符免费**，之后约 15~16 美元/百万字符。

### MiniMax（定为二次元首选）
- `s.apifox.cn` 音色表 + 阿里云百炼文档：**v2 的音色名直接就是人设** ——
  `lovely_girl 萌萌女童`、`qiaopi_mengmei 俏皮萌妹`、`diadia_xuemei 嗲嗲学妹`、
  `danya_xuejie 淡雅学姐`、`wumei_yujie 妩媚御姐`、`bingjiao_didi 病娇弟弟`；
  v1 有 `female-shaonv 少女` / `female-yujie 御姐` / `female-tianmei 甜美`。
- 情绪是**请求体字段**：`voice_setting: {voice_id, speed, vol, pitch, emotion}`，
  `emotion` 直接写 `happy`/`sad`/`angry` 等。比 SSML 简单得多。
- 额度：每月 1 万字符免费，之后约 39 元/月档。

### 其他（备查，未采用）
- `developer.volcengine.com/articles/7628812881848434738`：火山豆包 Doubao-Seed-TTS 2.0
  走 WebSocket 流式、指令式情感控制，音色 150 元/年 —— 延迟最低，将来做实时对话可以回看。
- Fish Audio：情感用**文本内嵌标签** `[excited]` / `[whispering]`，约 0.003 元/千字符。
  注意 **Fish Speech 模型协议是 CC BY-NC-SA，不可商用**，只有云端 API 能用。
- `shengwang.cn/blog/blogdetail/2026-TTS-evaluation/`：开源模型横评（Higgs Audio V2 情感最强、
  Kokoro-82M 最快、F5-TTS 是 MIT 可商用）—— 用户已要求去掉本地音源，仅存档。

### 落到代码里的结论
**各家表达情绪的方式完全不同，必须在网关里翻译**。抽象成 `emotion_mode` 四类
（与余额查询的四种算法同构）：

| mode | 机制 | 代表 |
|---|---|---|
| `prosody` | 只有 rate/pitch/volume，**做不了真情绪** | edge_tts |
| `style` | SSML `<mstts:express-as style= styledegree= role=>` | azure_speech |
| `emotion` | 请求体 `voice_setting.emotion:"happy"` | minimax |
| `inline_tag` | 文本里嵌 `[excited]` | fish_audio |

映射表落在 `config/emotion_map.json`：每种情绪给出四条通路，外加它对应桌宠脸上的哪个表情。

---

## 第十四批 · 鼠标交互与坐标系（2026-10-14，做 G67 舞台交互时查）

做「鼠标移到立绘上 → 角色看过来 / 知道指到了哪个部位」之前，先看参考项目怎么处理
**屏幕坐标 → 模型坐标** 这一步。这正是本轮踩坑最深的地方。

### airi（`moeru-ai/airi`）
- `packages/stage-ui-live2d/src/composables/live2d/eye-tracking.ts` →
  `useLive2DEyeFocusFor()`，把光标位置换算成 `Live2DModel.focus(x, y)` 的入参：

  ```
  x: (source.x - canvasRect.left + eyeOffset.x) * renderScale
  ```

  **要点：拿 `canvasRect`（显示矩形）定位，再乘 `renderScale`（渲染缩放）。**
  它同时区分三个量 —— 显示矩形 `canvasRect`、渲染缩放 `renderScale`、
  模型自身缩放 `normalizedScale × scale`。三者是独立的，不能互相替代。
- 鼠标无效时它 `return { x: 1000, y: 1000 }` —— 给一个**远离画面的坐标**让视线自然回正，
  而不是 `(0,0)`（那是画面左上角，角色会往左上角瞪着）。
  我们这边是另一条路：`/api/hover?in=0` 显式告诉引擎"移出去了"，实测眼球回 0.00。
- 它的组件测试 `InteractiveArea.browser.test.ts` 用 `vitest/browser` 的 `userEvent` 真点，
  而不是手搓假事件 —— 我们没有浏览器环境，等价做法是本轮加的
  「poke 的 x/y 必须等于 info.frame_w/h 换算值」这条断言（见 tests/test_web.js）。

### 落到本仓的结论
参考项目印证了本轮实测出来的坑：**显示尺寸、渲染缓冲尺寸、模型缩放是三个不同的量**。
对应到我们的实现：

| 量 | 在本仓是什么 | 取值 |
|---|---|---|
| 显示矩形 | `img.getBoundingClientRect()` | 随窗口变 |
| 渲染缓冲 | `info.frame_w/frame_h` = 画布 × pet scale | 466×748（scale 0.55） |
| 图片尺寸 | `img.naturalWidth` = 帧缓冲 × 画质档 `s%` | s=55 时 256×411 |
| 画布 | `info.canvas_w/canvas_h`，regions 的 rect 用它 | 848×1360 |

`/api/hover`、`/api/region`、`/api/poke` 吃的都是**渲染缓冲坐标**。
所以换算必须是 `(ev.clientX - rect.left) / rect.width * info.frame_w`，
**不能**用 `img.naturalWidth`（它还带着画质档的缩放）。
2026-10-14 之前 `stage.js` 就是用 naturalWidth 的，画质档恰好是 100 时碰巧对。

---

## 第十五批 · AI 玩「我的世界」与本地/局域网双人陪玩（2026-10-14）

> **⚠️ 本批在用户第一次澄清后写就，结论已被第二次澄清修正 —— 看完请接着看本批末尾的「④ 修正」。**
> 第一次澄清（当时的理解）：游戏范围限定在我的世界 / 本地双人 / 局域网双人，网游不在名单内。
> 第二次澄清（**最终口径**）：网游**不是排除**，而是只能「陪伴聊天 + 实时读屏回应对话」，
> 不代打；其他游戏才可以真正游玩。下面 ①②③ 的技术调研全部仍然有效，
> 只有"网游怎么办"这一条变了。

用户（第一次澄清）把游戏范围限定成：**我的世界、本地双人、局域网双人**；
网络竞技游戏（英雄联盟一类）当时理解为不在名单内。查了一圈，这个限定把技术路线
从"最难的那条"换成了"最成熟的那条" —— 下面的结论直接改写了 A25。

### ① Minecraft 不需要屏幕捕获，走协议就行

- **Mineflayer**（Node.js，`PrismarineJS/mineflayer`）：用 **TCP/IP Minecraft 协议**
  以**一个普通玩家客户端**的身份登录服务器，拿到的是**结构化世界数据**
  （方块、实体、背包、聊天），动作是 `bot.dig()` / `bot.chat()` / pathfinder 寻路。
  **不装 mod、不读屏幕、不模拟键鼠。** Java 版任意服务器可用。
  来源：https://dev.to/gaiaai/building-an-ai-powered-minecraft-agent-with-gaia-4afe
  （含最小可跑代码：`createBot({host:"localhost",port:25565,username:"Gaiabot"})` + `pathfinder`）
- **Voyager**（NVIDIA/MineDojo，GPT-4，论文 2305.16291，站点 https://voyager.minedojo.org/）：
  证明了"**代码即动作空间**"这条路 —— LLM 直接生成调用 Mineflayer 的 JavaScript，
  跑成功的代码存进**技能库**复用。成绩：63 种独特物品（基线 <20，3.3×）、
  科技树解锁快 15.3×、技能库能迁移到新世界。**不微调、不训练**，纯 prompt + 环境反馈迭代。
- **MINDcraft**（开源，bot 名 Andy）：在 Voyager 之后做的工程化版本。关键改进是
  **参数化命令**（让模型输出 `!collectBlocks("oak_log", 1)` 而不是现写一段代码），
  可靠性高得多；复杂行为才进"写代码模式"。
  来源：https://blogs.novita.ai/blog/mindcraft-unleashing-novita-ai-llm-api-in-minecraft/
- **已有现成 MCP 服务器**把 Mineflayer 包成 LLM 可调工具（移动/挖掘/合成/背包/聊天），
  Claude 这类模型可直接驱动。来源：https://mcpmarket.com/server/minecraft-ai-bot
  → **和我们已有的 `mcp_filesystem` 供应商是同一条路**，G59（MCP 适配器）做完就能接。

### ② 实测延迟数字（直接印证了「云端+本地双路由」的必要性）

- **Voyager 的 GPT-4 每个动作要 25 秒**（API 往返 + 代码生成），
  "makes realtime games impossible without local LLM fallbacks"；
  **本地 llama2-7b 在消费级 GPU 上同类任务决策 300~500ms**。
  来源：https://theneuralbase.com/ai-for-gaming/learn/advanced/minedojo-voyager/
- 这正是 A23 要的东西：**快决策（走位、躲怪、应答）必须本地模型**，
  **慢规划（造房子、定目标）才交给云端**。不是二选一，是分工。
- GPT-3.5 比 GPT-4 差 **5.7 倍**（发现物品数）→ 本地小模型只适合做"快而浅"的那半。

### ③ 坑（抄作业前先知道）

- **生成的 JS 代码默认没有沙箱**，模型写出死循环或崩溃代码会把 bot 卡死；
  Voyager 自带的错误恢复不够，会"反复试同一个错误做法，一直烧 API 额度"。
  → 必须有执行超时 + 失败计数 + 熔断（对应我们的 A30 成本熔断、G80）。
- 持续跑 Voyager 级别的探索，**API 费用轻松上千美元**。→ 又一次指向本地优先。
- 技能库里的代码会调用**目标引擎里不存在的 API**，跨引擎迁移要重写 20~40%。
  → 我们只做 Minecraft，不碰这个问题；但"技能库"这个设计可以照搬到 G56 skills。

### ④ 对本地双人 / 局域网双人的结论

- Minecraft 的局域网联机（"对局域网开放"）本质还是个 Minecraft 服务器，
  **Mineflayer 一样能以第二个玩家身份加入** → 「AI 陪你玩」和「陪伴联机」在这里是同一件事。
- 非 Minecraft 的本地双人游戏（手柄分屏那种）才需要走"屏幕捕获 + 虚拟手柄"，
  那是第二优先级，而且 **用虚拟手柄（vgamepad 一类）比模拟键鼠更贴合"第二个玩家"**。
- 关于网游：**见下面 ④ 的修正**，不是排除而是锁在只读档。

### ④ 修正（用户第二次澄清，2026-10-14，**最终口径**）

用户原话：「不是完全禁止网游，而是让他们可以在网游也陪伴聊天和实时屏幕操作
进行回应对话，懂了吗？而其他的可以真正的游玩。」

所以上面 ①②③ 讲的 Mineflayer / Voyager / 虚拟手柄这些**真玩**的路子，
适用范围是**我的世界与本地双人**；网游走的是另一条完全不同的路：

- **网游 = 只读**：读屏 + 看懂画面 + 实时开口回应，**零输入**。
  这条路不需要 Mineflayer，也不需要虚拟手柄 —— 它要的是 A27 的实时回路，
  而且正好是 neuro-sama 最出名的场景（看着别人玩并实时解说）。
- 反作弊与封号风险**并没有消失**，而是被"根本不碰输入"这个设计绕开了：
  档一在代码层面就不接输入通道，所以不存在"误开开关"的可能。
- 最终落地：`config/game_tiers.json` 三档表 + `check_platform.py` 七项闸，
  英雄联盟一类 `locked: true`，界面上不提供提升开关。详见 REQUIREMENTS A25。

---

## 第十六批 · Live2D 官方教程站（2026-10-14，用户给的链接）

> ### ⚠ 先更正一条作废结论
> 之前几轮的工作笔记里记着「`docs.live2d.com` 不可达」。**这条是错的，现在能访问。**
> 本轮用 `fetch_page` 把 `https://docs.live2d.com/zh-CHS/cubism-editor-tutorials/top/`
> 整页读下来了。后续不要再以"官网上不去"为由跳过查证。
>
> **而且 YouTube 视频也能"看"** —— `fetch_page` 对 youtube.com/watch 会返回
> 标题、时长、简介和**完整字幕（英文）**。10 分钟的教程视频拿回了全文逐字稿。
> 看不了的是画面本身（没有视频解码），但教程的口述内容一字不差。

### 教程站结构（哪些有用、哪些只是视频壳）

| 分类 | 形态 | 对我们有没有用 |
|---|---|---|
| 初学者教程（眨眼 / 口型 / 以图形记忆） | **纯 YouTube 视频**，页面几乎没正文 | 要靠字幕 |
| 基础教程 6 讲（PSD 加工→导入→表情→身体动作→脸部 XY→动态） | 同上 | 同上 |
| 嵌入用教程 6 讲（模型准备→物理→动态表情→导出→Viewer） | 同上 | 对导出 moc3/motion3 有参考价值 |
| **提高动态质量的技巧** | **纯图文 + GIF，无视频依赖** | ★ 直接可用，见下 |
| 参数控制器 4 讲（IK） | 视频 | 暂不需要 |
| 手册站 `cubism-editor-manual` | 图文为主 | ★ 技术细节都在这 |

### ★「提高动态质量的技巧」全文要点（图文页，已核对原文）

来源 https://docs.live2d.com/zh-CHS/cubism-editor-tutorials/motion-hint/

1. **脸动必须带着身体动** —— "如果只转动脸部，则会看起来像一个机器人"。
2. **脸和身体不能同时到位** —— "转动脸部，身体会在稍后跟随"。要留惯性时间差。
   → 我们已经在做：`look_around` 的重心通道 `phase: 0.18`（慢半拍）。
3. **后坐力 / 踩刹车** —— "人类无法立即停止动作……想停下来时，会稍微向前一点，
   再返回一点"。对应我们的 `out_back` ease。
   → **本轮修的「点击卡顿」正是它的反面教材**：动作不该停完还挂着空转。
4. **人在转脸或换视线时经常眨眼**。
   → 我们目前眨眼纯粹是随机定时器，和视线/转头完全无关。**待做，见 GAPS。**
5. **动作要有张弛** —— "等待时要安静地移动，动作时则需要明显"。
   → 和我们"下半身是陪衬、幅度压在 0.5 以内"的口径一致。
6. **按角色调整** —— 年轻女性角色"大幅度移动整个身体、添加歪头等可爱动作"；
   成年男性"沉稳、不要晃动、抑制歪头频率"。形态分区做 loli/adult 时直接套用。

### ★ 眨眼教程视频字幕要点（10:03，Live2D JUKU 官方）

来源 https://www.youtube.com/watch?v=ewkcJDcJZYI （字幕经 fetch_page 取回）

- 眼睛拆三件：**睫毛 / 瞳孔 / 眼白**；"把睫毛在眼角、眼皮等不同位置**细分**，
  更容易做出好看的眨眼"。→ 我们已经拆到 socket/base/ball/lash/closed/smile 六件。
- 闭眼关键帧的做法：选中眼部所有 ArtMesh（**但要把眼球排除**，"左眼球在眨眼时不动"），
  在 `EyeL open/close` 参数两端打键。→ 印证我们"眼球不参与闭合、只被眼眶裁切"的做法是对的。
- **★ "Making the shape slightly narrower horizontally when the eye is closed
  than when open makes it easy to create a natural blink"** ——
  闭眼时眼型要比睁眼时**横向略窄**。

  **本轮试过、已撤回**：我照这条加了 `aperture_narrow`（眼眶遮罩随 blink 横向收 12%），
  实测**虹膜宽度一点没变**（0.25~0.70 各档都是 123px）。原因是我们用的是**遮罩裁切**，
  而虹膜（31×30）离遮罩左右边缘很远，收 6% 根本够不到它，只削到眼白外角。
  官方那个做法是在**网格上形变整个眼型**，遮罩方案复现不了。
  要真做到得把眼部件的锚点从左上角改到各自中心再整体缩 —— 属生成器改动，
  留作 GAPS，不在本轮硬凑。**不要看到这条就再加一次 aperture_narrow。**

---

## 第十七批 · Live2D 官方手册与基础教程（2026-10-14，接第十六批）

> ### ⚠ 更正第十六批的一个说法
> 第十六批写了「基础教程 6 讲全是 YouTube 视频壳，页面几乎没正文」。
> **这句话过头了。** 实际情况是分两种：
> - **《10分钟就能看懂的眨眼》这类速成课** = 真·纯视频壳（只能靠字幕）
> - **基础教程 6 讲** = 视频 + **完整图文「视频回顾」**，每一步都有文字和配图
> - **嵌入用教程 6 讲** = 纯视频壳，而且视频在 **bilibili** 不是 YouTube
> - **手册站 `cubism-editor-manual`** = 纯图文，技术细节都在这里
>
> 结论：**要技术细节就去手册站，不要去教程站**。

### ★《4. 添加身体动作》图文回顾要点（基础教程，有全文）

来源 https://docs.live2d.com/zh-CHS/cubism-editor-tutorials/deformer/

- **两种变形器分工**：**旋转变形器**（红条）专做旋转，"主要用于脖子、手臂、腿部"；
  **弯曲变形器**（灰框）做网格变换。
  → 对应我们的 `groups`（枢轴旋转）与 `deformers`（网格），分工一致。
- 头部旋转变形器的枢轴**放在下巴位置**。我们 `head.pivot` 用的是颈关节 y=346，同一量级。
- **★「身体的倾斜应该变换为绘制一个弧线，而不是水平平行移动」** ——
  我们 `ParamBodyAngleZ → chest.rot_deg` 是真旋转（弧线）✓；
  `ParamBodyAngleX → seg_torso.bend_x` 是水平错切，属另一条轴，不冲突。
- **「如果脚浮起，将很难添加动态，所以让脚变换，以确保它们不会离开地面」** ——
  核对过：`ParamBodyAngleY` 只动 `seg_torso.bend_y` + `chest.dy/sy`，
  腿挂在 `root` 下不受影响，**脚不会离地** ✓。
- 手臂参数范围建议 `-30 / 0 / 30`；抬手时还要顺带调粗细（我们没做手臂粗细）。

### ★★ 官方物理模型规格（手册站，对应我们的 G44）

来源 https://docs.live2d.com/en/cubism-editor-manual/physics-operation/
　　　https://docs.live2d.com/en/cubism-editor-manual/physical-operation-setting/
　　　（Cubism 2 中文手册 sites.google.com/cybernoids.jp/cubism2 讲得最直白）

官方把摇摆建模成**单摆**，四个可调量：

| 官方项 | 含义 | 官方建议值 |
|---|---|---|
| Duration（摇动速度） | 越小摆得越快 | — |
| **Ease of swinging（揺れやすさ）** | 越大，小输入也摆得大 | **0.7 ~ 0.99** |
| Reaction time（反应时间） | 1=标准，>1 更灵敏 | 1 |
| Speed of convergence（收敛速度） | 1=标准，>1 收得快 | 1 |

Cubism 2 的更物理化的三个量：**质量**（越大摆幅越大）、**距离**＝根部到梢的长度
（越大摆得越慢）、**减衰率**（越大收得越快）。

**我们现有 13 条 physics 的字段**：`stiffness` / `damping` / `ratio` / `max` / `curve`。
对应关系：`stiffness` ≈ Duration 的倒数、`damping` ≈ 减衰率/收敛速度、
`ratio` ≈ 单位移动量（输出缩放）、`max` ≈ 输出上限。**缺 Reaction time（反应灵敏度）**，
多段摆靠 `driver` 串联（`ahoge_tip.driver = ahoge_x`）已经实现了官方说的"多段摆锤"。

**★ 两条可直接用的工程经验**：
1. **计算 FPS 默认 60**（Cubism 5.0 beta1 起从 30 改成 60）。物理参数和 FPS 绑死，
   换 FPS 必须重调。我们的物理是按真实 dt 积分的，这条要注意别写成按帧。
2. **「Output Maximum 超过 100% 会导致动作抽搐（choppiness）」** ——
   摆的幅度超出了参数量程，摆到了没有形变的区域。
   → 这正是我们 `max` 字段的作用；**调物理时要盯住输出有没有顶到 max**，
   顶住了就该降 `ratio` 而不是加大 `max`。
3. 多输入时有**影响度（影響度）**权重，且"从列表**下面**的项开始算起"；
   两个输入各 100% 会叠成 150% 之类，要留余量防止摆到极限。

---

## 第十八批 · 立绘之外的功能模块（2026-10-14，用户要求"需要教程的都找一下"）

用户列的清单：桌宠程序 / UI 美化 / 代理 / skills / 云端 / 陪伴 / 游戏 /
生图生视频生代码。本批先把**最能改变设计决策**的两块查了（代理+skills、桌宠窗口），
其余在下面列了"还欠什么"。

### ★★ 一、代理与 skills 的工程规矩（对应 A9~A21 / G50~G63 / T20）

来源：
- https://www.useparagon.com/blog/how-to-optimize-tool-calling
- https://mlflow.org/articles/ai-agent-tool-use-best-practices-for-practitioners/
- https://axiomstudio.ai/blog/agent-skills-what-they-are-how-to-write-best-practice-guide
- https://orchestrator.dev/blog/2026-10-09-agentic-workload-design-patterns/
- https://dev.to/ljhao/5-agent-design-patterns-every-developer-needs-to-know-in-2026-17d8

**带数字的结论（可以直接当设计约束用）**：

| 结论 | 数字 | 对我们的意义 |
|---|---|---|
| 单个 agent 的工具数上限 | **5~7 个**，超过后"路由决策明显变差" | 我们 gateway 19 条路由不能一股脑塞给模型，**必须按任务过滤** |
| 上下文质量开始劣化的点 | **填到 25% 就开始降**，建议常驻 60~80% | 记忆区设计要主动压缩，不是填满为止 |
| 多 agent 的代价 | **约为单次对话的 15 倍 token** | 只对"可并行且高价值"的活儿才拆多 agent |
| Plan-and-Execute vs ReAct | 完成率 92% vs 85%，**快 3.6 倍**，但 token 3000~4500 vs 2000~3000 | 复杂任务用前者，闲聊陪伴用后者 |
| Reflection（自我复核） | HumanEval 91% vs 80% | 生代码场景值得加一轮自检 |

**架构规矩（和我们已有的 A29/A30 对得上，可以互相印证）**：
- **权限必须落在 harness 代码里，不能写在 prompt 里** —— "prompt 级的限制是可以被绕过的"。
  → 正是我们 A29（G79）的做法，官方口径支持。**而且这条印证了"网游只读档必须在代码层不接输入通道"**（A25 档一），写进提示词是不够的。
- **每个 session 要有步数 / token / 时间 / 工具调用次数的硬预算** → 我们 A30（G80）成本熔断。
- 工具要 **idempotent（可重复调用无副作用）**，失败要返回**结构化错误**而不是空成功。
- 写/删/花钱的操作要有**人工批准闸**。
- **skills 的反模式清单**（直接拿来当我们 skills 区的设计检查表）：
  隐藏状态依赖（"用常用那个路径"）、两个 skill 抢同一件事、
  只包一个函数的"假 skill"（那应该是 tool）、**只写成功路径不定义失败模式**、
  吞掉错误、把所有参考文档内联进去（应该按需加载）、触发范围无边界、没有评测集。

### ★★ 二、桌宠窗口：透明 / 置顶 / 点击穿透（对应桌宠程序本体）

来源：
- https://crabnebula.dev/blog/building-a-desktop-pet-with-tauri/（Tauri 官方生态的完整教程，带可用配置）
- https://www.edgedrop.app/blog/electron-versus-tauri-for-overlay-utilities（选型对照表）
- https://dev.to/manasightgg/why-i-chose-tauri-v2-for-a-desktop-overlay-in-2026-597h
- https://github.com/Scyyyy4/deskpet（Tauri 2 + React 的桌宠，可读源码）

**Tauri vs Electron 实测对照**：

| 维度 | Electron | Tauri |
|---|---|---|
| 二进制体积 | 80~150 MB | **5~15 MB** |
| 空闲内存 | 100~200 MB | **30~80 MB** |
| 透明窗口 | 成熟 | 支持，边角情况处理得少 |
| 点击穿透 | **成熟**（`setIgnoreMouseEvents(true,{forward:true})`） | 支持但实战验证少 |
| 跨平台一致性 | 高（自带 Chromium） | 低（各系统 webview 不同） |

**★ 最关键的一条坑**：**两家都没有"按区域"的点击穿透**。
Tauri 不提供 per-region hit-testing，实战做法是
**Rust 里以 ~60fps 轮询鼠标位置，判断是否落在 UI 面板上，再切换
`set_ignore_cursor_events`**（编译后的紧循环，不是 JS，开销可接受）。
→ 我们自己做窗口层时要预留这条：**"立绘的不透明区域才吃点击"这件事得自己算**，
而我们已经有 `/api/region` 和逐像素 alpha，判定数据是现成的。

Tauri 可用配置（原文照抄）：`alwaysOnTop / transparent / decorations:false /
resizable:false / visibleOnAllWorkspaces / macOSPrivateApi:true`。

### 还欠什么（下次按这个清单继续）

- **UI 美化**：还没查。建议查"桌宠/VTuber 风格的 UI kit"和毛玻璃/圆角规范。
- **云端**：还没查。重点是 A23 双路由的具体切换判据（已有第十五批的延迟数字打底：
  云端 GPT-4 每动作 25 秒 vs 本地 llama2-7b 300~500ms）。
- **陪伴 / neuro-sama 式实时**：第十五批已有部分（事件流、低延迟回路），
  还缺"主动发言的触发策略"和"实时 STT 选型"。
- **生图 / 生视频 / 生代码**：还没查。生代码可先用上面 Reflection 那条（91% vs 80%）。

## 第十九批 · 姿势切换与交叉淡变（2026-10-14，做 T24.5 踮脚换鞋时查）

做"同一个部位两张姿态图"这件事之前先查的官方口径。结论直接落进了
`src/core/zrig.c` 的 `xfades` 和 `docs/ART_PARTS.md` 5.13。

### 1）《创建有姿势切换的动态》（Cubism 编辑器手册，2020-07-03，纯图文）

<https://docs.live2d.com/zh-CHS/cubism-editor-manual/change-pose/>

- 要切换姿势，**两件准备**：① 在模型数据上把要切换的部件**分离**成独立部件；
  ② 在动画里给这些部件打 **Live2D 部件显示** 关键帧（显示 100 / 隐藏 0，
  要显示的那件把键打在第 0 帧）。三件以上同理。
- 嵌入场景（Original Workflow）还要在 Viewer 里生成 **pose3.json**。
- **"通过交叉淡变使手臂的显示切换更清晰"** 一节（这节是我们要的）：
  嵌入模型里做交叉淡变时，**两件网格重叠的部分会很显眼**（官方示例是肘/肩接缝）。
  减少办法分两栏——
  - *拆 PSD 时*：**重叠区域尽可能小** + **模糊（羽化）重叠纹理的轮廓**；
  - *建模时*：**加变形来减少重叠范围**。
  - 自查方法：把要切换的图形网格 opacity 设成 50%，换个背景色用肉眼看重叠。
- → 我们的落法：窗口收窄到 `in:[0.40,0.60]`（扫过只 3 帧 ≈50ms），
  重叠带 38px 且被鞋完全盖住（逐像素量过外露 0）。官方只说"尽量减少"，
  **没有"彻底消除"的办法**，所以我们也到此为止，不再加"淡出件同步拉伸"之类的机械。

### 2）SDK《About Pose》—— 运行时到底怎么淡

<https://docs.live2d.com/en/cubism-sdk-manual/pose/>

- 运行时**不直接写部件不透明度**，而是改写**同 ID 的参数**。
- `CubismPose::DoFade` 的两个官方常量：**Phi = 0.5**、**BackOpacityThreshold = 0.15**。
- 推导（Phi=0.5）：隐藏件 `a1 = 1 − newOpacity`；
  若 `backOpacity = (1−a1)(1−newOpacity) > 0.15`，抬到 `a1 = 1 − 0.15/(1−newOpacity)`；
  且 `a1` 只能**单调变暗**（`if (opacity > a1) opacity = a1`）。
- **中点 newOpacity=0.5 → a1 = 0.70，总覆盖 0.85，背景最多漏 15%。**
  我们原先设想的线性交叉淡化在中点只盖 0.75（**漏 25%**）——桌宠是透明窗口，
  漏的就是桌面。所以 `zrig_xfade_hidden()` 照抄了这条曲线，单测里真渲染一帧量到 0.85。

### 3）《检视器面板》—— 部件级还能设什么

<https://docs.live2d.com/en/cubism-editor-manual/inspector-palette/>

部件级可设 opacity / 乘算色 / 屏幕色 / 描绘顺序；**5.3 起部件支持 Offscreen drawing**
（开了之后部件内部物件互相重叠不再影响整体不透明度）——
正是"两件鞋重叠时整体透明度失真"的同类问题，官方的解法是离屏合成。
我们目前靠 Pose 曲线把总覆盖抬到 0.85 绕过去；真要做到 1.00 得上离屏合成（记在 GAPS）。

### 4）顺带更正一条旧结论

以前笔记里写过"`docs.live2d.com` 不可达" —— **那是错的，现在逐页都能抓到正文**。
同理 **YouTube 也能"看"**：`fetch_page` 对 `youtube.com/watch` 会返回标题 / 时长 /
简介 / **完整英文字幕**，看不了的只是画面。**否定结论会过期，隔一轮要复查**（LESSONS 81）。

## 第二十批 · 把第十八批欠的四块补完（2026-10-15）

> **先立一条规矩（A33 配套）：每条结论标证据等级。**
> 后面几批混了官方文档和二手评测，不标等级的话，过两周就分不清哪条是硬的。
>
> | 等级 | 含义 | 能拿来做什么 |
> |---|---|---|
> | **★★★ 官方文档/规范** | 厂商自己的手册、SDK 文档、设计规范 | 可以直接照着实现 |
> | **★★ 论文/公开基准** | 有方法学、可复现的测量 | 可以用来定架构和阈值 |
> | **★ 厂商宣传页** | 自己报自己的数 | 只能当上限参考，必须自测 |
> | **☆ 二手评测/博客** | 第三方转述，数字常互相打架 | 只能用来列候选名单 |
>
> 本批里 UI 那一节是 ★★★，其余多为 ★/☆ —— **凡是 ★ 以下的都不算定案，真机实测之前不许写进设计**。

### 1）桌面 UI 规格（★★★ 微软官方）

- 《Geometry in Windows 11》<https://learn.microsoft.com/en-us/windows/apps/design/signature-experiences/geometry>
  **圆角三档**：顶层容器（窗口 / 对话框 / Flyout）**8px**；页内元素（按钮 / 列表背板）**4px**；
  直角相交处 **0px**；窗口贴边或最大化时不圆角。Tooltip 因为小，用 4px。
  全局资源两个：`ControlCornerRadius`(4) / `OverlayCornerRadius`(8)。
  **嵌套规则：内层比外层小 2px（8 → 6 → 4）**，不要圆角直角混搭。
- 《System backdrops (Mica/Acrylic)》<https://learn.microsoft.com/en-us/windows/apps/windows-app-sdk/system-backdrop-controller>
  **Mica = 不透明材质**，只采样一次桌面壁纸，**为性能设计**，用于窗口底层/标题栏；
  **Acrylic = 半透明毛玻璃**（高斯模糊 + 噪点），**只用于临时性、点击即消的面**（Flyout、右键菜单）。
  → 对我们的意义：桌宠**主窗口**是透明贴图窗，不吃 Mica；但**聊天气泡 / 设置面板 / 托盘菜单**
  应该按 Acrylic 的口径做（半透明 + 模糊 + 浅色描边），圆角 8px，内层控件 4px。
- Glassmorphism 的三要素（☆ 综述，和上面官方口径一致）：**不全不透明 + 背景必须模糊 + 浅色半透明描边**；
  模糊是为了让压在上面的文字可读 —— 只降透明度不模糊会糊字。

### 2）本地 / 云端双路由的判据（A23，★★ 论文 + ☆ 工程博客）

- 论文《Efficient Routing of Inference Requests across LLM Instances in Cloud-Edge Computing》
  <https://arxiv.org/html/2507.15553v1> 的对照表（同一套负载）：
  | 策略 | 平均质量↑ | 平均响应↓ | 平均成本↓ | 综合↑ |
  |---|---|---|---|---|
  | 全云 | 0.5736 | 1.06s | 1.13e-4 | 0.667 |
  | 全本地 | 0.4207 | 3.97s | 9.00e-6 | 0.333 |
  | 随机 | 0.4361 | 2.36s | 5.71e-5 | 0.383 |
  | **论文的路由器** | 0.5462 | 1.11s | 7.36e-5 | **0.752** |
  **要点：全本地的响应时间是全云的 3.7 倍**（本地模型小但机器弱），所以"本地优先"不是无脑优先。
- 工程侧三家博客（☆，但三家结构一致，可信度相对高）给的都是**同一套三支柱**：
  ① **敏感数据 → 强制本地**（本地不可用就报错，不许偷偷上云）；
  ② **复杂/长上下文 → 云端**（阈值例子：>512 token 或任务类型属 reasoning/code/tool-use）；
  ③ **本地忙/云端故障 → 互相兜底**（GPU 利用率阈值例子 85%/90%）。
  路由器本身必须轻（"路由决策 <1ms"），**不能再调一次 LLM 来决定路由**。
- 语音链路的延迟预算（☆ 但数字自洽，可作设计靶子）：
  ASR 30~50ms → 路由 ~1ms → LLM TTFT 80~120ms（本地 7B）/150~300ms（云端 70B）→ TTS 50ms
  = 本地路 **~170ms**、云端路 **~400ms**；交互式语音的公认上限是 **LLM 段 <150ms、总 <500ms**。
- → 落到我们的 `gateway`：现在的 `prefer_local` 只是"有本地就用本地"。真正的双路由要加三个输入：
  **敏感标记、预估 token 数、本地负载**，并且把每次决策**记账**（用于事后调阈值）。目标分流 70~85% 走本地。

### 3）实时 STT（A26 / neuro-sama 式回路，★★ 论文 + ☆ 评测）

- **Whisper 本身不是流式模型**（★★：官方 repo 讨论 + 论文都这么说），所有"流式 Whisper"都是
  把它改成**分块批处理**：攒一段 → 整段推理 → 拼接。
- 论文 Whisper-Streaming <https://arxiv.org/html/2307.14743>（★★，有方法学）：
  A40 上英语平均延迟 **3.3s**（MinChunkSize 1s），德语 4.4s、捷克语 4.8s；
  **VAD 开关的结论**：原声（少停顿）关 VAD 延迟更低；口译/多停顿场景开 VAD，WER 好 2~3%、延迟只多 0.1s。
- 实现选型（☆ 评测，数字互相打架，只用来列候选）：
  `faster-whisper`（CTranslate2，int8，**自带 Silero VAD**）在 NVIDIA 上快；
  `whisper.cpp`（纯 C，CUDA/Metal/Vulkan，`--stream`）在 Apple/嵌入式和"不想要 Python"的场景赢。
  多家都提到 **large-v3-turbo / distil 系列**是实时档的常用选择。
- **真正的低延迟要换模型族**：原生流式 ASR（NeMo FastConformer 这类 cache-aware 流式）
  能做到 80~320ms 的 lookahead、稳定 100~200ms 感知延迟；Whisper 系天花板在 ~500ms 以上。
- → 对我们的意义：桌宠的"听到就回应"**不需要字幕级准确**，先用
  `faster-whisper small/turbo + Silero VAD`（本地、离线、无 API 费），
  把**端点检测（说完没有）**做好比把 WER 压低重要；真机实测不达标再考虑原生流式模型。

### 4）TTS 供应商矩阵（补第十三批的欠账，★ 厂商页 + ☆ 评测）

**⚠ 这一节的数字互相打架，必须按证据等级读**：同一个 ElevenLabs Flash v2.5，
有说 **75ms**（厂商口径）、有说 **135ms**（某第三方台架）、有说 **~400ms**（IVR 场景实测）、
还有一家按"整段音频生成完"口径测出 **46 秒**。原因在于**口径不同**：
TTFB（第一个字节）/ TTFA（第一段可播音频）/ 整段完成，差 300~500ms 很正常。

| 供应商 | 口径最乐观的 TTFB/TTFA | 价位（每百万字符） | 备注 |
|---|---|---|---|
| Cartesia Sonic | ~40~90ms | ~$38/百万 | 公认最快档，表现力弱一些 |
| ElevenLabs Flash v2.5 / v3 | 75ms（厂商）~400ms（实测） | $25~$180 | 表现力和多语最强，v3 有 inline 情绪标签 |
| Deepgram Aura-2 | ~150~200ms | ~$30 | 可本地/VPC 部署 |
| Azure Neural / HD | 200~500ms | $16 / $30 | 140+ 语言，企业合规，免费额度 500K 字符/月 |
| OpenAI gpt-4o-mini-tts | 200~400ms | ~$15 | 和我们已有的 OpenAI 通道同一套鉴权 |
| MiniMax Speech-02 | ~150ms | ~$100 | **中文强**，国内可用 |
| Fish Audio S2 | — | ~$15 | 克隆质量口碑好，性价比高 |
| 开源 Kokoro / Chatterbox | 自托管 | $0 | 纯本地档的候选 |

**（按用户硬要求：豆包 / 火山引擎 / Seed-TTS 一律不进这张表，已有静态闸挡住。）**

- 公认的**生产可用线：TTFA < 150ms**；>300ms 在对话里会听出明显停顿。
- **厂商报的都是 TTS 这一段**，端到端还要叠 STT + LLM + 网络握手 —— 我们自己的
  `voice_render` 要量的是**从用户说完到第一声出来**，不是厂商那个数。
- → 现行口径不变（云端标准音色，DC12）；这张表只决定**下一步接哪几家**：
  先接 Azure（免费额度大、合规、中文可用）+ OpenAI（鉴权复用），
  低延迟档留 Cartesia 的位置，中文表现力档留 MiniMax 的位置。

### 5）生图 / 生视频（A19 的本地档，☆ 二手为主）

- **ComfyUI 有现成的 HTTP API**：`POST /prompt`（排队一个 workflow JSON）+ WebSocket 看进度，
  client_id 用 UUID。这是把"生图"接进桌宠最省事的一条路 —— 不用自己写推理栈，
  用户本机装 ComfyUI 即可（示例代码见
  <https://baeseokjae.github.io/posts/comfyui-workflow-ai-image-generation-guide-2026/>）。
- **显存档位**（多家口径一致，可信）：6GB 只能 SD1.5；8GB 跑 SDXL（要 `--lowvram`，1024² 约 30s）；
  **12GB 是舒适下限**（SDXL FP16 / FLUX GGUF Q5）；16GB 跑 FLUX dev FP8；24GB 才谈视频模型。
  SDXL + ControlNet + IP-Adapter 这种组合要 **13~14GB**。
- **视频生成**：自托管（Wan 2.x / HunyuanVideo）**要 24GB+ 显存**，桌宠用户机器普遍达不到；
  云端 API 的价位区间是 **$0.02~0.20 / 秒**（Hailuo/Wan 最便宜档 ~$0.02~0.04，
  Kling ~$0.05~0.10，Runway Gen-4.5 ~$0.12~0.20），10 秒片子大约 $0.2~2。
- → 结论（见 DECISIONS DC19）：**生图支持"本机 ComfyUI + 云端 API"两条路；生视频只走云端 API**，
  并且在 UI 上**先给显存体检**（低于 12GB 直接建议走云端），避免用户点一下等 5 分钟出个糊图。

### 还欠什么（这张清单每批都要更新，不许留"还没查"）

- ~~UI 美化~~ ✅ 本批第 1 节（Fluent 官方口径）。
- ~~云端双路由判据~~ ✅ 本批第 2 节（论文对照表 + 三支柱 + 延迟预算）。
- ~~实时 STT 选型~~ ✅ 本批第 3 节。
- ~~生图 / 生视频~~ ✅ 本批第 5 节。**生代码**仍欠（可先用第十八批 Reflection 那条：80%→91%）。
- **仍欠**：主动发言的触发策略（neuro-sama 式"什么时候插话"）；多人联机同步的具体协议（A24）。

## 第二十一批（2026-10-15）四家 AI 的品牌色 —— 为 A22 的主题定制取证

都是为了 `web/themes/{deepseek,gemini,grok,gpt}.json` 的配色，每条都给出处。

### DeepSeek
- `https://brandfetch.com/deepseek.com` —— 品牌色 **#4D6BFE**（Dodger Blue）+ #FFFFFF。
- `https://www.wikidata.org/wiki/Q131983933` —— 官方 logo 条目，sRGB **4D6BFE**，
  并记了一条有意思的：logo 描绘的是 **Balaenoptera musculus（蓝鲸）**。
  小寻头上的鲸鱼发卡正好是同一个意象，这套主题因此叫"深海蓝鲸"。
- `https://oh-my-design.kr/design-systems/deepseek` —— 更细的 token：
  brand #4d6bfe / 主按钮 **#1a1615（暖近黑，不是蓝）** / 文字 #1e232c / 页面 #f9f8f8 /
  占位 #8691a1 / 链接 #234792 / 圆角 **8px**；并明确 **"别拿 #4d6bfe 做大面积填充"**，
  它只该出现在强调和 chip 文字上。主题文件照这条做了：底色走纸白，蓝只在描边和强调。

### Gemini（继承 Google）
- `https://colorcode.tools/brands/google`、`https://getbrandscan.com/brands/google` ——
  蓝 **#4285F4** / 红 **#EA4335** / 黄 **#FBBC05**（新版写 #FBBC04）/ 绿 **#34A853**，
  正文近黑 **#202124**，浅灰面 #F1F3F4，Material 按钮圆角 **4px**。
- `https://zonalogo.com/logo-google-gemini` —— 明确写了 **Gemini 没有单独发布固定调色板**，
  它继承 Google 这套，UI 里常以渐变/多色呈现。所以主题里四色都用上了，
  圆角从 4px 放宽到 12px（桌宠界面太方会发硬）。

### Grok / xAI
- `https://www.makr.io/design/color/brand-colors` —— xAI 条目就两个色：**#000000 / #FFFFFF**。
- `https://www.designyourway.net/blog/xai-logo/` —— 官方单色黑白，
  另记了一个衍生强调色 Dodger Blue #2196F3（非官方主色）。
  主题因此是四套里**唯一的深色默认**，靠黑白灰层次 + 2px 硬圆角，几乎不上彩。

### GPT / OpenAI
- `https://colorbase.in/brands/openai` —— **#000000 / #10A37F / #FFFFFF / #202123**。
- `https://www.loftlyy.com/en/openai` —— 同样三色；并记了 2025 改版引入 OpenAI Sans，
  整体偏灰蓝中性色。
- `https://brandpalettes.com/openai-color-codes/` —— 只认黑 #000000 一个色。
  三处口径有差异（青绿到底算不算品牌色），主题取折中：浅色底 + 青绿作唯一强调色。
