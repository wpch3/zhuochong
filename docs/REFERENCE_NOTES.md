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

## 第二十二批（2026-10-15）表情参数：闭眼的三种形状、嘴型与张嘴的关系

用户报「被锤没有 `>_<` 这种闭眼」「惊讶时张嘴和微笑重合」，并要求"不明白去找教程和参考"。
查的是 Live2D 官方标准参数定义，证据等级标在每条后面。

- **★★★ `ParamEyeLSmile` / `ParamEyeRSmile`，范围 0~1，「主要用于闭眼」**
  （niabie.github.io/2019/08/30/cubism笔记 —— 中文 Cubism 笔记，★★；
  与 cg-method.com/vtuber/live2d-blink-lipsync-parameters/ 的标准参数表一致 ★★）。
  → 这反过来确认了上一轮 DC35 的修法（笑眼走 `blink=max(blink,smile)`）是官方路子，不是权宜。

- **★★★ `ParamEyeBallForm`：「为补充皱眉/做鬼脸（顔をしかめる）的表情而弯曲眼睛轮廓的动作」**
  （animaze.us/manual/gettingstarted2djp/jpnparamlist，Animaze 官方手册 ★★★；
  vtsuku.com/animaze-parameter 复述为「目玉を拡大縮小」★）。
  → **`>_<` 这种用力闭眼靠的就是它**：闭眼 + 弯曲眼轮廓（倒 V），而不是普通的 ∪。
  我们的 rig **有** `ParamEyeBallForm` 而且 `surprised` 在用（pulse amp 1.0），
  但 `hammered` 一条眼睛通道都没有 —— 这是 G106。

- **★★★ `ParamMouthForm` 范围 −1 / 0 / 1 = 悲伤 / 中性 / 笑；`ParamMouthOpenY` 0~1 = 闭口 / 张口**
  （cg-method.com 标准参数表 ★★；blog.csdn.net/red_redemption/146077891 复述一致 ★）。
  → 两者是**独立的两轴**：张嘴不会自动把嘴型归中。惊讶时必须**同时**把 `ParamMouthForm` 拉到 0
  或负值，否则"微笑的嘴形"和"张大的嘴"会叠在一起 —— 这是 G107，用户肉眼就看出来了。

- **☆ 表情混合三种算法 Add / Multiply / Override**（docs.live2d.com/en/cubism-sdk-manual/expression/ ★★★）：
  exp3.json 里每个参数可单独选。Add 是默认，Multiply 用于"放大/缩小现有动作"。
  → 我们的 `expressions` 段目前只有覆盖语义，将来做"表情叠在动作上"要补这个区分。

**对我们的直接结论**：闭眼不是一种形状而是**三种** —— ∪（普通闭眼 `eye_*_closed`）、
∩（笑眼 `eye_*_smile`，已有）、**倒 V（痛苦/用力闭眼，素材里没有，要补绘）**。
前两种我们有，第三种缺，所以 `hammered` 才做不出 `>_<`。

---

## 第二十三批（2026-10-15）惊讶 / 瞪大眼的官方口径 —— 直接推翻我们原来的做法

起因：用户实拍反馈「惊讶时眼球会不自然的变大，看着像个怪物一样很怪」。
我们当时 `surprised` 挂的是 `ParamEyeBallForm +1.0`，而这个参数在本 rig 里只绑了
**眼球（虹膜）缩放** sx 0.18 / sy 0.22 —— 等于把瞳孔撑大 18~22%。查下来是**反的**。

- **★★★ 瞪大眼有专用参数 `ParamEyeLWide` / `ParamEyeRWide`，范围 0~1**，
  文档原文：*"Widen the character's left eye **beyond the extents of ParamEyeLOpen**"*
  （saltech.llc/live2d-support，Vodcasto 的 Live2D 参数支持表 ★★）。
  → 「睁得更大」是**眼睛开口**的事，不是**瞳孔大小**的事，两者是不同参数。

- **★★★ Animaze 官方手册**：`ParamEyeLOpen`「默认值 = 眼睛完全睁开；**往 max 方向走，
  映射的是"目を大きく開く"（眼睛瞪大）**；min 到默认值之间才是普通闭眼动作」
  （animaze.us/manual/gettingstarted2d/diveinto ★★★，日文版 jpnparamlist 同）。
  建议区间写成 `0 / 0.75 / 1`（min / default / max）。
  → 官方的瞪大眼做法 = **把 ParamEyeLOpen 的 max 开到 1 以上**，不是放大虹膜。

- **★★★ 惊讶时瞳孔要"变小"，不是变大** —— 两个互相独立的 r/Live2D 帖子都这么写：
  「0.7 默认、**1.0 是眼睛更开 + 瞳孔更小**」（r/Live2D 19dv4la ★）、
  「闭眼 0.0 / 睁眼 1.0 / **extra opened eye + smaller pupil 1.2**」（r/Live2D uxc8wh ★）。
  社区通行做法是把 max 开到 1.2~1.7，超出 1 的那一段专门画"瞪大 + 缩瞳"的形状。

- **★★ shocked 的标准组合** = *Wide eyes, open mouth (slightly), raised eyebrows；
  Motion: Recoil, jump back*（github.com/fagenorn/handcrafted-persona-engine 的
  Live2D 接入指南，emoji→表情映射表 ★★）。

**对我们的直接结论（已落地）**：
1. `surprised` 的眼睛通道从 `ParamEyeBallForm +1.0`（瞳孔放大 18~22%）改成 **−0.45**
   （瞳孔缩到 ~0.92x/0.90x）。幅度是渲 4 档对照图挑的，不是算出来的：
   `logs/asset_qa/surprised_eyes2.png`（待机 / +1.0 / 0.0 / −0.45 / −0.8）。
2. 真正的「瞪大眼」我们**还做不了** —— `ParamEyeLOpen/ROpen` 在本 rig 里是眨眼系统
   合成的，不在 `params` 段里，驱不到 >1；而且没有"瞪大眼"的素材。
   要做就得按官方那条路：加 `ParamEyeLWide` 式参数 + 画超出常态开口的眼形。记为 G110。
3. 顺带注意：我们的 `ParamEyeBallForm` **名字与官方语义不符** —— 官方它是
   「为补充皱眉/做鬼脸而**弯曲眼睛轮廓**」（第二十二批 Animaze 条目），
   我们拿它当"瞳孔缩放"用。改名要动 rig 契约，记在 G110 一起处理。

## 第二十四批（2026-10-15）VRChat / VMC / 歌声合成 / 情绪 TTS —— 四个新需求的官方口径

起因：用户问「能否制作接入 vrchat 以及 3d 模型控制，以及唱歌和对话语气变化等」。
四项分别查官方文档，**最大的发现是前两项其实是同一件事**。

### 一、VRChat OSC（docs.vrchat.com，官方 ★★★）

- **★★★ 端口**：VRChat **收 9000、发 9001**。外部程序往 9000 发、在 9001 收。
  可用命令行改：`--osc=inPort:senderIP:outPort`，默认等价于 `--osc=9000:127.0.0.1:9001`；
  中间填局域网 IP 就能把数据发到另一台机器（`--osc=9000:192.168.1.42:9001`）。
  开关在**动作菜单 Options → OSC → Enabled**，不开什么都收不到。
- **★★★ `/avatar/parameters/<名字>` 只接受 Int / Bool / Float 三种**，
  官方原文：*"If you send a Float value to a parameter defined as Bool in your avatar,
  VRChat will **silently ignore** the message."* —— **类型写错不报错、直接丢**。
  我们的映射表必须带类型字段，而且要有闸，否则会出现"配好了但没反应"的鬼故事。
- **★★ 参数名由 avatar 作者定义，每个模型都不一样**。VRChat 会在
  `%LOCALAPPDATA%Low\VRChat\VRChat\OSC\{userId}\Avatars\{avatarId}.json`
  自动生成配置，里面列全了每个参数的名字/类型/输入输出地址。
  → 所以**必须给用户一个 OSC 监视器**（T32.7），不然他配不出映射表。
  另外换模型时 VRChat 会发 `/avatar/change` 带 avatar id。
- **★★★ VRChat 持续广播的内置参数**（这是白捡的游戏状态信号源）：
  `Viseme`(Int 0–14 口型)、`GestureLeft`/`GestureRight`(Int 0–7)、
  `VelocityX/Y/Z`(Float −1~1)、`Grounded`/`Seated`/`InStation`/`MuteSelf`/`AFK`(Bool)。
  → **A27「实时接取信息并回应」在 VRChat 场景下不用截图、不用 OCR、不用视觉模型**，
  游戏自己把结构化状态按帧送上门，延迟是 UDP 级。这比我们原计划的读屏便宜一个数量级。
- **☆ OSC Trackers**（`/tracking/trackers/1..8/position|rotation`，最多 8 个 + head）
  是喂全身 IK 的，Unity 左手坐标系、+y 向上、1.0f = 1m、欧拉角按 Z→X→Y 应用。
  **2D 立绘用不上，明确不做。**
- ☆ 官方推荐的测试工具：TouchOSC（发）/ Protokol（收）；官方自用的 C# 库是 vrchat/osccore。

### 二、VMC Protocol（protocol.vmc.info / sh-akira，官方 ★★★）

- **★★★ 也是 OSC over UDP** —— 和 VRChat 同一套报文格式。
  **这就是"做一条总线四处通"的根据**：VRChat、VMC、VSeeFace、Warudo、
  bHaptics、TouchOSC 全在 OSC 上，我们只要写一次编解码。
- **★★★ 端口 39539（Marionette 接收方）/ 39540（Performer 发送方）**，现行版本 **V3.1**。
  UTF-8；bundle 允许但要 **< 1500 字节**（别超 MTU）；**未知消息必须忽略**（向前兼容靠这条）。
- **★★★ 三种角色**：Performer（发动作，如 VirtualMotionCapture / VSeeFace）、
  Assistant（补发表情，如 waidayo / face2vmc）、Marionette（接收并应用，如 EVMC4U / VMC4UE / VMC4B）。
  → **我们当 Marionette**：收 `/VMC/Ext/Blend/Val`(名字+值) 驱动小寻的脸。
  骨骼 `/VMC/Ext/Bone/Pos`（Unity HumanBodyBones 名 + 位置 + 四元数）我们是 2D，用不上。
- **★★★ `/VMC/Ext/Blend/Apply` 是提交信号** —— 规范明写：接收方应**先攒住所有
  Blend/Val，收到 Apply 才一次性生效**。按条即时套用会出现撕裂表情。
- **★★ VRM0 ↔ VRM1 表情名不一样，接收侧要转**：
  `Blink_L`↔`blinkLeft`、`Blink_R`↔`blinkRight`、`Sorrow`↔`sad`、
  `I`↔`ih`、`U`↔`ou`、`E`↔`ee`、`O`↔`oh`。规范建议**发送方统一用 VRM0 格式**。
- ☆ 生态里 Godot 4.3+ 有官方受信插件，Blender/UE 都有现成 addon —— 说明协议确实稳定。

### 三、歌声合成 SVS（★★ 结论：和 TTS 是两套东西）

- **★★★ SVS 的输入是 music score（歌词 + 音高/MIDI + 时值），TTS 的输入是 text**
  （DiffSinger，arXiv 2105.02446）。**接口层面就不同** —— 这是 DC43 的根据。
- **★★ DiffSinger**：MIT 许可，4.9k★，原作 MoonInTheRiver，现由 **OpenVPI 团队维护**；
  浅扩散机制 + NSF-HiFiGAN 声码器；PNDM 采样器把 1000 步压到 25 步。
  **OpenUtau 是它的现成图形前端**（需先装 nsf_hifigan 声码器）。
  OpenUtau 侧暴露的表情曲线很全：PITD(音高) / DYN(音量) / GENC(性别/共振峰 ±12 半音) /
  VELC / ENE / BREC(气声) / TENC(紧张度) / VOIC / PEXP / SHFC / 音色曲线。
- **★★ NNSVS**（arXiv 2210.15987）：论文自测 MOS **NNSVS-WORLD v4 = 3.86** vs
  **DiffSinger = 2.90** vs NNSVS-Mel v2 = 3.58。论文同时指出 DiffSinger 保真度高但
  **音高容易不连续/不稳**。→ 真要选引擎时别只看名气。
- **★★ 代价（必须提前告诉用户）**：数据量 NNSVS 1–2 小时标注歌声、UTAU <1 小时；
  训练要 GPU（"没 GPU 就是几天不是几小时"）；**DiffSinger 的自动建库流程只支持中文**；
  标注要用 vLabeler / Praat 打音素和时长，或直接用 Opencpop 这类已标注数据集。
- ☆ 公开数据集：OpenSinger（中文 66 人 50h）、PopCS（DiffSinger 自带，中文 1 人 5.9h，需申请）。

### 四、情绪 / 语气 TTS（★★★ 四项里最便宜的一项）

- **★★★ Azure**：`<mstts:express-as style="cheerful" styledegree="...">`，
  **styledegree 官方区间 0.01–2.0，连续可调** —— 正好能接我们 mood 的强度值。
  配套 `<prosody>`/`<break>`/`<emphasis>`/`<phoneme>`/`<say-as>`/`mstts:silence`，
  并支持**逐词时间戳**（做字幕/口型对齐有用）。
  **★★ 坑**：style 清单按语言不同 —— 实测报告里**日语当时只有 chat / cheerful /
  customerservice 三种**。中文支持哪些**必须实测，不许照抄文档总表**。
- **★★★ ElevenLabs v3 / v4**：走 **audio tags**，行内写 `[happy]` `[sad]` `[angry]`
  `[whispers]` `[shouts]` `[laughs]` `[sighs]` `[clears throat]`，可叠加
  （`"[happily][shouts] We did it! [laughs]"`）。
  **★★ 两条硬限制（官方 FAQ 明写）**：① v3/v4 **不支持 SSML `<break>`**，
  停顿用 `...`、强调用**大写**；② 官方原话 *"These tips help guide emotional delivery
  but **do not guarantee** a specific result."* → **不能当确定性接口用**。
  v3 字符上限 5000；v4 Turbo 中位延迟 ~100ms，v3 Conversational ~280ms。
- **★★ 两家的性格正好相反**：**Azure = 数值可复现**（styledegree 是数字，
  同输入同输出）；**ElevenLabs = 表现力强但不可复现**。
  → 适配层对上统一成 `(mood, intensity 0–1)`，对下各自翻译（T35.1）。
- ☆ 开源侧备选：**Chatterbox**（首个带"情绪夸张度"单参数控制的开源 TTS）、
  **IndexTTS-2**（2025-09，**音色与情绪解耦**，可用自然语言描述指定情绪；
  论文里的毫秒级时长控制**公开代码尚未启用**）。
- ⛔ 供应商矩阵仍然**排除豆包 / 火山引擎 / Seed-TTS**（A28，用户硬约束）。

### 五、对照：Project AIRI 做了什么（github.com/moeru-ai/airi，MIT，★★ 用来找我们的缺口）

同类项目里跑得最远的一个（Neuro-sama 方向），拿来对照**不是抄，是看我们漏了什么**：

- 它有而**我们计划里原本没有**的：**OBS/直播产出**、**角色卡 CCv3 导入导出**、
  **插件 SDK（plugin.airi.json）**、**Spine2D / MMD / 立绘(Tachie) 多种模型格式**、
  **浏览器内向量记忆（DuckDB WASM + pgvector）**、Discord / Telegram 接入、
  手柄输入、桌面窗口穿透与悬停淡化。→ 已择优补进 **A40 / T37**。
- 它有而**我们已经计划了**的：Live2D/VRM 双模型、实时语音链（VAD→STT→LLM→TTS）、
  多供应商路由（xsai）、Minecraft 智能体（Mineflayer）、Factorio（RCON + YOLO 视觉）、
  屏幕上下文感知、本地推理（WebGPU / Candle+CUDA/Metal）。→ 对应我们 A23–A27。
- **它的架构和我们相反**：Vue + TypeScript + WebGPU + Electron，一切在浏览器里。
  我们是纯 C + 自研软渲染 + 零依赖。**它的功能清单可以抄，技术选型不能抄** ——
  照它那样做等于推翻 DC26 和整个项目的立身之本。
- ☆ 可借鉴的一个具体细节：它的 Live2D 导入会**先出一份体检报告**
  （列出模型数据、缺失引用、未被引用的资源、每条怎么修）再导入。
  我们的素材重建链也该有这么一份（可并入 T31.10 的孤儿切件闸）。

## 第二十五批（2026-10-15）动漫超分：给 T30.1 找到的唯一一条真 2× 路径

起因：T30.1「素材 2× 重切」开工验前提，发现**没有 2× 的原始素材可用**（DC44）。
按用户 2026-10-15 的要求「如果不能就寻找办法，网上总会有的」上网找，找到了。

- **★★★ Real-ESRGAN 的 anime 专用轻量模型**：`RealESR-AnimeVideo-v3 x4`。
  compact 架构，**ONNX 只有 2.4MB**，CPU 单线程 **14.6 s / 百万输入像素**
  （沙箱 2 核实测；1024×1536 整张 22.6s）。
  常规用法是**超到 4× 再 LANCZOS 下采样到 2×**，顺带把超分引入的噪点压掉。
  许可：模型 reupload 仓库 BSD 3-Clause；Real-ESRGAN 本体（xinntao/Real-ESRGAN）BSD 3-Clause。
- **★★ 它为什么适合我们**：Real-ESRGAN 是**纯卷积超分**，不是生成模型 ——
  几何严格对齐。实测倍率 2.0020/1.9993、bbox 原点偏差 (-1,0)px、轮廓 IoU 0.9938。
  **所以部件坐标直接乘 2 就行，44 件不用重对**。
  对照：`generate_image` 这类生成模型虽然 IoU 也能到 0.988，但**输出分辨率不受控**
  （我们那次 1024×1536 进去、843×1264 出来，反而变小了），做超分根本不对路。
- **★★ 沙箱取模型的坑**：`raw.githubusercontent.com` **不在出网白名单**
  （白名单只有 github.com / codeload.github.com / api.github.com / registry.npmjs.org /
  pypi.org / files.pythonhosted.org）。所以要走
  `https://codeload.github.com/<owner>/<repo>/tar.gz/refs/heads/main` 下整个 tarball 再解。
  `pip install onnxruntime` 走 pypi 没问题（1.31.0，CPU provider）。
- **★★ 分块推理要留 overlap**：整张 1024×1536 一次推理要几 GB 临时内存。
  按 256 的 tile 切、每边多算 16px 再裁掉 —— 不留 overlap 的话块边界上卷积拿不到邻域，
  拼出来有可见接缝。实测 24 块零接缝。
- **★ 副作用要知道**：超分会**忠实放大原图的瑕疵**。我们 design_sheet 边缘本来就有
  抠图残留的发丝杂色（G101 查过，是原画自带的，DC34），超分后更明显。
  切件时的抠图要能吃掉它，否则要退回 1.5×。已写进 DC44 的复查触发。
- ☆ 同类备选（本轮没用）：waifu2x（更老，细节保守）、
  Anime4K（纯 GLSL shader、无需模型，但要 GPU/shader 运行时，我们是 CPU 软渲染，不合适）。

## 第二十六批（2026-10-15）AI 唱歌到底是怎么做的 —— 用户质疑后重查，推翻了我自己的框架

起因：我上一轮答「唱歌 = SVS，要乐谱 + 1–3 小时标注 + GPU」。
用户当场质疑：「**那那些网站上 AI 唱歌的音频和视频怎么来的？我们不能做吗？**」
重查下来**我把问题框错了**（DC45）。网上 AI 唱歌有三条完全不同的路：

### 路线一 ★★★ AI 翻唱 = 换音色（占绝大多数，"AI 孙燕姿"这一类）

**流程固定三步**：① UVR5 / Demucs 从原曲分离人声与伴奏 →
② **RVC / so-vits-svc 把人声换成目标音色** → ③ 混回伴奏。
**★ 关键：旋律、节奏、咬字、情感全部来自原唱歌手，AI 只换了音色。**
所以**不需要乐谱、不需要 MIDI、不需要音素标注** —— 这正是我上一轮漏掉的整个类别。

- **RVC（Retrieval-based Voice Conversion）**：MIT，**38.7k★**，2026-10-15 当天仍在更新。
  基于 VITS + 检索式特征匹配。官方 README 原话：
  **「使用少量数据进行训练也能得到较好结果（推荐至少收集 10 分钟低底噪语音数据）」**
  —— 能这么省是因为有 **~50 小时 VCTK 开源底模**兜底。
  硬件：**推理 4GB 显存 / 训练 6GB**；RTX3060 上 200 轮约 **1–2 小时**。
  实时变声 **90–170ms**（ASIO 下 90ms），官方有 `realtime_gui.py` 和 `RVCRealtimeVST/`。
  CPU 可推理但**慢 10–20×**，训练在 CPU 上不现实（慢 50×+）。
  关键参数：变调（男转女 +12 / 女转男 −12 / 同性 0）、检索特征占比 0.7–0.8
  （越高越像，太高出电音）、音高提取器 RMVPE（最准）/ FCPE（最快）。
- **★★ 核实过的一条反面事实**：网上博客常说"RVC 有 `tools/export_onnx.py`，导出 ONNX 就能脱离 Python"。
  **拉当前仓库树核对：334 个文件里一个 onnx 都没有。** 官方只在 README 里给了
  `rmvpe.onnx`（音高提取器）的下载命令，hubert 和生成器都没有官方 ONNX。
  社区那个 `ji-or-ji/rvc-onnx-realtime` 导出工具 **★0、无 license、2026-10-05 才更新**，
  不能当依赖。→ **结论：RVC 只能当外部进程调，塞不进我们的纯 C 运行时。**
  （该仓库的 CPU 实测可做参考：0.5s 音频块整条流水线 537ms，约 1.07× 实时，离线够用。）
- **so-vits-svc**：数据要 30min–2h、显存 8GB、训练更久。
  第三方 benchmark：说话人相似度 **0.79 / UTMOS 3.95**，均低于 RVC v2 的 **0.85 / 4.19**。
  作者自己的声明值得抄进我们的产品说明：
  **「这个项目是为了让开发者最喜欢的动画角色唱歌而开发的，任何涉及真人的东西都与开发者的意图背道而驰」**。

### 路线二 ★★ 端到端生成（Suno / Udio）

文字 → 整首歌（词曲唱编混全包）。**Suno 没有官方公开 API**，只有第三方转发
（约 **$0.55/首**）；免费档**无商用权**，付费档订阅期内可商用。
2026-09-18 又被 Universal / Sony 起诉，**版权环境不稳定**。
Udio 自 2025-10-29 起**不能下载文件**（UMG 合作后的限制）。
→ 只做可选外部供应商，不作主路径。

### 路线三 ★ SVS 从零合成（我上一轮只讲了这条）

DiffSinger / NNSVS（开源，要乐谱 + 1–3h 标注）、
**ACE Studio / Synthesizer V（商业，有现成音源库，不用自己训练）**。
它解决的是"**没有原唱也能唱**"，这是路线一做不到的事 —— 所以不是没用，是**顺序靠后**。

### ★★ 版权：这一块必须写进产品，不能靠免责声明

- **《民法典》第 1023 条**：自然人声音**参照肖像权保护**。只要生成的声音能被识别到
  特定真人且未经许可，就可能侵权，**与是否直接复制原音频无关**。
- 翻唱还会碰到**词曲著作权**；用原曲分离出的伴奏还会碰到**录音制作者权**
  （中国政法大学陶乾在南都论坛上就是这么拆解"AI 孙燕姿唱《七里香》"的：
  周杰伦作为歌手的表演者权不涉及（表演者无权禁止他人翻唱其表演），
  但**伴奏来自周版录音 → 录音制作者权**，**歌曲本身 → 音乐作品著作权**）。
- **「仅供学习 / 非商用」不免责** —— 声音权属人格权，不以盈利为前提。
- **→ 我们天然在干净的一侧**：小寻是原创虚拟角色，音色来自自家 TTS 通道，
  不碰真人声音权。要守住的是：不内置真人歌手音色、不做"一键 AI 某某"、
  导入第三方模型弹授权提示、输出打 AI 标识（T34.5）。
- ⚠ **一个还没查清的问题**：拿商业 TTS 的输出去训练衍生 RVC 模型，
  **是否违反该 TTS 的服务条款**？没查到定论 → T34.2a，动手前必须先读条款。

### 视频那一半是怎么来的

用户问的"视频"，虚拟歌姬那一类就是 **Live2D / VRM 模型 + 音频驱动口型**——
**这正是我们 A39 / T36（音频特征流：RMS 包络 + F0 + 起音）要做的东西**。
真人脸的那一类才需要 Wav2Lip / SadTalker 这类对口型模型。
→ 换句话说，**"AI 唱歌视频"的视频侧，我们本来就在做，而且做完 T36 就有了。**

## 第二十七批（2026-10-15）neuro-sama 到底怎么做的 + 人格漂移是架构问题

起因：用户问「计划够完整吗？还有什么缺漏？能不能像 neurosama 一样模仿人，
设置几种变量、工作模式、模仿人的模式等等？需要吗？还是说有更好的办法」。

### 一、★★★ neuro-sama 的真实架构（Lin-Guanguo 的技术调研 + Fandom + Vedal 直播口径）

- **★★★ 人格烤在权重里，不在 prompt 里。** v2（2022，GPT-3 API）时代人格**完全靠 prompt**；
  v3+（2023 中）换成**自己微调的开源小模型**，早期 2025 Vedal 口径是 **2B 参数 / q2_k 量化**。
  换了之后 **system prompt 只用来给情境**（"你现在在玩 Minecraft""你在跟 Evil 说话"），
  **不再定义人格**。
- **★★★ 为什么非微调不可** —— 社区复刻项目 kimjammer/Neuro 的关键发现：
  **对齐过的基座模型会抵抗 prompt 里要求的性格**（要它凶、要它毒舌，它会软回去）。
  **这是 prompt 路线的硬天花板**，微调是在权重层面覆盖对齐。
- **★★ 2B + q2_k 是激进的小**：说明 Vedal 把**推理延迟**（直播要 1–3s 出话）排在能力之前。
  硬件 i9-10900K + RTX4090 + 128GB，**自托管**（他说过上云延迟不可接受）。
- **★★★ 记忆分两种**（Vedal 直播里开过文件）：**core（永不遗忘**：她写过 LIFE、谁是谁、
  Evil 生日那档事）/ **standard（几周后就没了）**。
  **Neuro 自己从短期里挑哪些存进长期**，Vedal 偶尔进去清理。
- **★★★ 她会自己开口**：社区观察到有 **attention span / boredom 机制** ——
  一段时间没有新输入就主动说点什么。
- **★★★ 话轮有专门机制**：一个**可调 delay** 判断"对方说完了没"；
  如果对方在延迟内又开口，**她会收回自己准备说的话**。
- **★★ 唱歌是完全独立的模型**，而且**说话模型会打断唱歌模型**（印证第二十六批）。
- **★★ Evil Neuro 是独立程序 + 独立记忆**，不是一个程序的两个人格开关。
- **★★★ 动作走 typed action protocol（VedalAI/neuro-sdk，WebSocket）**：
  游戏**注册 action schema + 上报当前状态**，模型只回**action 名 + JSON**，
  **游戏自己负责校验和执行**。原则一句话：
  *"keep the main model's output simple, typed, and easy to validate;
  move execution into game-specific downstream systems"*。
  → 这正是我们该抄的分层（T38.13）：OSC 总线、游戏三档、skills 共用一层，而不是各写各的。
- **★★ 持续学习其实是"批量重训"**：直播(只推理) → 收集转录 → **Vedal 人工筛** →
  离线微调 → 下次直播上线。**瓶颈是人工筛选**，没有在线学习，也没公开怎么防灾难性遗忘。
- ☆ 社区重建项目 Open-LLM-VTuber：管线部分（LLM+TTS+STT+Live2D）谁都能拼起来，
  **人格 100% 靠 prompt、没有记忆** —— 调研原话：「**管线是容易的那部分**，差异在别处」。

### 二、★★★ 人格漂移（persona drift）是架构性的，不是工程没做好

- **★★★ PersonaGym 基准（Deng et al. 2024）**：
  **10 轮对话 90%+ 人格一致性 → 100+ 轮掉到 60–70%**。
  **没有对抗输入、没有记忆投毒，就是正常聊天**，纯粹由上下文累积造成。
  机理：人格定义待在 system prompt 里，对话越长，它在总注意力里占比越低。
- **★★★ context rot：上下文不是越大越好**，过载反而让模型分不清轻重，
  鲜活的角色会塌成"通用助手腔"。社区测出的稳定甜点区是 **8K–16K tokens**。
  → **"把所有记忆都塞进去"是错的方向。**
- **★★ 产品侧数据**（第三方 30/60 天测试，口径不严谨但量级可信）：
  Character.AI 30 天事实召回 **~15%**（会话间重置），Kindroid **~80%**（结构化 backstory + pinned）；
  另一组测试 Nomi 25 条植入事实记住 23 条。
  Character.AI 的结构性限制：persona 字段免费档约 150 词，pinned memories 每会话上限 15 条。
- **★★★ 业界共识的解法 = 分层 + 每轮重锚**：
  `L0 SOUL（不可变身份，每次会话重新注入，永远钉在 context 顶部）` /
  `L1 CORE（常青事实，不衰减）` / `L2 WORKING（日志，随时间衰减）` / `L3 SESSION（瞬时）`。
  三条机理：**身份重锚**对抗注意力稀释、**时间衰减**压低旧记忆影响、**分层**把
  "必须留"和"可以淡"在数据层面隔开（因为模型自己做不到这个隔离）。
- **★★ 检索 vs 重建**：检索回答的是"你以前说过什么"（新旧并存、互相矛盾），
  重建回答的是"这件事现在的状态是什么"（旧状态被取代）。**伴侣类产品要的是后者。**

### 三、★★ 主动性（proactive agent）已经有成熟范式

- **★★★ heartbeat 模式**：`wake → observe → reason → act`，不值得行动就继续睡、零输出。
  好处是不用维持长驻上下文（贵且脆）。
- **★★★ 主动性 5 级**：L0 纯反应 / L1 定时 / L2 事件触发 / L3 信号（阈值）/
  **L4 机会触发（agent 自己判断现在是不是好时机）**。L4 要额外的元推理层 + 熔断器。
- **★★★ 自主边界的通行规则**：
  **可逆且在内部的** → 可自主；**不可逆或触及外部**（发外部邮件、改别人日程、公开发帖）
  → **草拟后等确认**。原文：*"Most platform failures come from over-stepping this line."*
- **★★ 反打扰工程**：工作时段尊重、**24 小时内容哈希去重**、自适应间隔、
  **idle-time utilization（只在空闲做主动动作，天然限流）**、崩溃后能恢复。
- **★★ 可观测性是主动型产品的第一原则**（而非附加项）：
  被动 AI 答错你下次不问就是了；**主动 AI 答错时它已经打扰你了**。
  要能查"她为什么现在开口"（决策回调：should_respond + reasoning + sleep 时长 + 理由）。
- **★★ 清华 + 面壁的开源 Proactive Agent** 给了评估口径四件套：
  **需求遗落 / 静默应答 / 正确检测 / 错误检测**。
- ☆ 可参考实现：`leomariga/ProactiveAgent`（Python，决策引擎可换：AI 判断 / 阈值 / 自定义函数）。

## 第二十四批（2026-10-16）：物理为什么会抖 / 星星眼与卖萌动作官方怎么做

### ★★★ 物理必须固定步长 —— 官方源码与注释（直接推翻我们原来的写法）

来源 `https://raw.githubusercontent.com/Live2D/CubismNativeFramework/develop/src/Physics/CubismPhysics.cpp`
（Live2D 官方 Native Framework，develop 分支，2026-10-16 取）

```cpp
const csmFloat32 MaxDeltaTime = 5.0f;          // 累计超过这么多就直接丢弃

void CubismPhysics::Evaluate(CubismModel* model, csmFloat32 deltaTimeSeconds)
{
    _currentRemainTime += deltaTimeSeconds;
    if (_currentRemainTime > MaxDeltaTime) _currentRemainTime = 0.0f;

    physicsDeltaTime = (_physicsRig->Fps > 0.0f) ? 1.0f / _physicsRig->Fps
                                                 : deltaTimeSeconds;
    while (_currentRemainTime >= physicsDeltaTime) {
        previous = current;                                  // 存上一步输出
        float inputWeight = physicsDeltaTime / _currentRemainTime;
        //   输入线性插值：cache = inputCache*(1-w) + value*w
        UpdateParticles(..., physicsDeltaTime, ...);          // 定步积分
        _currentRemainTime -= physicsDeltaTime;
    }
    const float alpha = _currentRemainTime / physicsDeltaTime;
    Interpolate(model, alpha);        // out = previous*(1-alpha) + current*alpha
}
```

官方对这段的注释原文（日/英并列）：

> 「この仕様は**補間範囲を逸脱したことが原因の震えたような見た目**を回避を目的にしている。」
> "The purpose of this specification is to avoid the **quivering appearance** caused by
>  deviations from the interpolation range."

**「震えたような見た目」＝ 发抖的观感**，正是用户 2026-10-16 报的"左右轻微抽搐"。
配套还有 `CubismPhysics::Stabilization()`（docs.live2d.com/en/cubism-sdk-manual/stabilize-physics/），
用途是**模型刚显示出来那一帧**先把物理稳住，避免初始参数非默认值时炸开。

业界同一套：Gaffer on Games《Fix Your Timestep!》的 accumulator 模式
（`https://gafferongames.com/post/fix_your_timestep/`，并给出 `frameTime > 0.25` 的上限防"死亡螺旋"）、
Unity 的 `FixedUpdate`/`Maximum Allowed Timestep`、Unreal 的 substepping、Box2D 的 `MAX_STEPS`。

**我们之前错在哪**：`physics_update` 是 `dt = now - phys_last; if (dt>0.1) dt=0.1;` 后**单步**显式欧拉。
实测（真实角色，同一真实时刻对 60fps 基准）：2.5fps 时 `ahoge_x` ×3.6、`hand_r_lag` ×11.3。
注意 `REFERENCE_NOTES` 第 1000 行早就记过「物理参数和 FPS 绑死，换 FPS 必须重调，
我们的物理是按真实 dt 积分的，这条要注意别写成按帧」—— **当时只看到一半**：
按真实 dt 积分是对的，但必须是**定步长的真实 dt**，不是整帧一步。

### ★★★ 星星眼（きらきら目 / しいたけ目）

- **归一个参数，别各占一个** —— Live2D 创作者 kawase（`https://x.com/kawase1234567/status/1747491216227516567`）：
  「■きらきら目・ハート目は→ 同時発動しないので**同一パラメにまとめる**」。
  同帖还给了另外三档的口径：**驚き目 → 開閉に +1.2**、にやにや目 → 瞳変形 +1、ジト目 → 瞳変形 −1。
  （和第二十三批的 `ParamEyeLWide` 结论一致：瞪大眼走"开闭超过 1"，不是放大瞳孔。）
- **差分的标准做法**（`https://surume1ka.com/archives/2207` ★★）：
  新参数 **min 0 / max 1 / default 0**；差分件用**不透明度** 0%↔100% 切；
  **差分件必须 clipping 到白眼 ID**，并且在「目 開閉」参数上**也打键**，这样闭眼时差分跟着闭。
- **要闪烁才"生动"**（`https://note.com/zombiefff/n/nf2758894e049` ★★）：
  Sway1 = 按正负值**缩放**部件；Sway2 = **warp 变形**做上下左右突出的"キラキラ"；
  物理 input 接「开闭 / 笑 / 呼吸 / 角度 XYZ」制造随机，output 分配给 Sway1/Sway2，
  **特别注意 Sway2 的 max 输出**（闪烁强度就靠它）。
- 静态贴图只是第一步：社区把 sparkle eyes 列为标配表情差分之一
  （`https://note.com/moimoi_sp/n/n267967b33084`）。

### ★★ 卖萌动作：官方是"手臂差分"，不是把手臂硬转过去

同一篇模型制作记（`https://note.com/moimoi_sp/n/n267967b33084`）把
**arm variations（手臂差分）和表情差分并列**，都是在 CLIP STUDIO 阶段**另画一套**再导入。
对我们就是 D19：没画过的角度必须 AI 重绘。
我们的硬边界：`ParamArmRA → arm_r.rot_deg × −6.0`，参数 ±1 ⇒ **只有 ±6°**；
举手到脸前需要肩 ~140°、肘 ~90°，硬转必然撞 G103 折痕且袖子露馅。

## 第二十五批（2026-10-16）：星星眼到底由几层组成 —— 用户打回两版 AI 出图之后补的功课

**用户的三条更正**（2026-10-16，看到我生成的金色星星之后）：
① **小寻的瞳孔是蓝色的**（配色表 `眼 #4A8FD4`），我生成金色星星是错的；
② **「星星眼」不只是眼睛变成星星，还要加上星星的特效**（画面上的 ✨）；
③ 他给的参考截图是**干物妹小埋（Q 版）**，要求「把眼泪去掉、眼睛更有动漫少女的感觉、去掉 Q 版形象」。

### ★★★ 结论先行：星星眼是**三层**，不是一张贴图

| 层 | 是什么 | 我们的落点 |
|---|---|---|
| L1 **星形瞳孔** | 虹膜被五角星取代 | 换 `eye_{l,r}_ball` → 新 Pose 档位 |
| L2 **眼内闪光** | 多层高光 + 碎钻状反光点（这层决定"像不像动漫少女的眼睛"） | 画进 L1 贴图 / 或拆成独立高光件 |
| L3 **画面闪光特效** | 脸周围飘的 ✨，有大有小、此起彼伏 | **新部件组 + 每颗一个参数**，见下方做法 |

我原来只做了 L1，而且颜色还错了 —— 两版都被打回是应该的。

### ★★★ L3 闪光特效的标准做法（这是最有用的一条）

来源 `https://kw-nmnm.hatenablog.com/entry/2019/12/18/000000`（カワナミ，Live2D 讲师、
alive2019 登坛者，Live2D Advent Calendar 2019 第 18 天）★★★

> キラキラエフェクト：動きとしては「**拡大・縮小**」と「**不透明度**」の２つです。
> これはパラメータを分けずに**１つに集約**しました。パラメータを端から端まで動かす間に
> 「**拡大しながら現れる→縮小しながら消える**」という１サイクルが回るようにつけてあります。
> あとは調整用の**回転デフォーマ**を置いて大きさを変えつつ散らします。
> キラキラは変にまとめるとランダムに見えづらいかなぁと思い、
> **１つにつき１つのパラメータで制御**しています。**その数28個。**

拆成我们能直接落地的四条：
1. 一颗闪光只需要两个通道：**scale + alpha**，而且**合并到一个参数**上
   （参数 0→1 走完 = 放大出现 → 缩小消失，一个完整生命周期）。
2. 每颗闪光**各自一个参数**，不要共用 —— 共用了就会整齐划一地闪，一眼假。
   原作者用了 **28 颗 28 个参数**。
3. 大小与散布用**旋转 deformer** 调，不靠手摆坐标。
4. **素材只要一张**，其余靠复制 + 变形（原文："キラキラエフェクトもコピペするので素材自体はひとつだけ"）。

对我们：`zrig` 的 `params` + `deformers` + 动作通道（sine/pulse，各给不同 `phase`）
正好够用，**不需要新引擎能力**，这是纯配置活。

### ★★ 商业成品的交互口径（抄它的触发条件与可调项）

`https://booth.pm/ja/items/5711516`（【Live2Dアイテム】キラキラエフェクト，¥300）★★
- 触发：**「笑顔で目を見開いたときに」キラキラエフェクトが表示される** ——
  笑 + 睁大眼 才出，不是随时在闪。
- 可调：**尺寸、位置、颜色**都能从表情文件编辑器改；还有「キラキラタイプ切り替え」
  （闪光样式切换）和「ぼかし」（模糊）开关。
- **默认色是蓝色**（`色変更用(初期設定青)`）—— 对小寻（蓝瞳）正好，不用改设计。

### ★★ Live2D 官方讲座站有一整门「キラキラ」课

`https://juku.live2dcs.jp/movie/movie-251/` 「エフェクトの作り方 ～キラキラ編～
③キラキラエフェクトの作り方【#Live2DJUKU】」（本编要会员）★★
大纲公开：**PSD 数据结构 / キラキラ1 的构造 / キラキラ2 的构造 / キラキラ3 的构造 /
ほわ效果的构造 / 改色方法 / motion 设置**。
→ 印证了上面"一张素材 + 多种构造 + 可改色"的路子，也说明**三种不同形状的闪光**
（大星、小星、光点）混用才自然，别只放一种。
YouTube 有 ダイジェスト：`https://www.youtube.com/watch?v=9o-Z1ZZOX3E`

### ★★ L1/L2 的画法要点（为什么我前两版"不像动漫少女的眼睛"）

- 社区对眼睛的**标准拆件**是：上睫毛 / 白眼 / 瞳 / **瞳的高光** / 下眼睑 / 睫毛
  （`https://oekaki-zukan.com/articles/44668`、`https://note.com/kamibukuro_0/n/n12d9227a6d56`）。
  差分件（きらきら目・ハート目）**要画得超出脸的范围**，靠 clipping 裁，不要自己卡边。
- 「瞳を主役にしたキラキラ」的 AI 出图口径（`https://x.com/mugi_AI_Art/article/2070809387925680319`）：
  正向 `large sparkling eyes, crystal-like highlights in her eyes, tiny star reflections,
  glossy eyelashes, soft light particles around her face, shallow depth of field`；
  负向 `distorted eyes, excessive highlights, messy sparkles, overexposure, cheap glitter effect`。
  **"星形闪光"的准确说法是 `star-shaped sparkles`**，"光粒"是 `floating light particles`。
- 另一条反复出现的提醒：**キラキラ不指定位置就会散得到处都是**，
  要写 `around her face` / `around the character` 限定范围。

### ☆ 顺带确认：Live2D 本身没有粒子系统

`https://community.live2d.com/discussion/194/`（官方论坛，Live2D 中之人回复）：
想在"眼睛层和眼皮层之间"插 Unity 粒子做不到，官方建议要么把模型复制一份遮挡，
要么**干脆把效果画成图片再建模**。社区十年来的共识也是后者。
→ 我们走"画成素材 + 参数驱动"这条，和官方建议一致，不用纠结引擎要不要上粒子系统。

## 第二十六批（2026-10-16）：情绪特效到底是什么东西 —— 用户提出"小阴云/小雨云/小太阳"之后补的功课

用户问："除了更多的表情、情绪表达、动作、神情之外，我觉得我们可以做更多的动态特效，
比如小阴云、小雨云、小太阳什么什么的情绪特效或者其他的表达特效，你觉得怎么样？"

查完的结论：**这不是我们发明的东西，它有专门的名字、有成套的词汇表、有固定的画法。**

### 一、它叫「漫符（まんぷ / manpu）」，是日本漫画的一套视觉语言

来源：
- `https://dic.nicovideo.jp/a/%E6%BC%AB%E7%AC%A6`（ニコニコ大百科，最全的分类）
- `https://aidco.jp/manpu/`（为什么人能看懂记号 —— 认知角度）
- `https://www.irasutoya.com/2015/06/blog-post_275.html`（いらすとや 的成套免费素材，可当形状参考）
- `https://booth.pm/ja/items/4895970`（BOOTH 的 40 个漫符图标集，商业成品的取舍可参考）

定义：**把感情或状态视觉化的符号**。「サルでも描けるまんが教室」里给的定义是
"感情や感覚を視覚化した、漫画ならではの符号"；夏目房之介学术上叫「形喩」。
关键认知依据（aidco）：**人脑识别图形比识别文字快**，所以一个汗滴顶一句"他很慌"。
—— 这正是桌宠需要的：**不用说话就能让人读懂她现在什么心情**。

### 二、常用漫符清单（按"我们该不该做"排序）

| 漫符 | 含义 | 位置 | 动法 | 我们的优先级 |
|---|---|---|---|---|
| **キラキラ / 星** | 开心、闪耀、决めポーズ | 脸周围散布 | 缩放+淡入淡出，各闪各的 | **已做**（T39） |
| **汗** | 焦り・困惑・紧张 | 太阳穴 / 头顶斜上放射 2~3 个 | 冒出 → 下滑 → 消失 | ★★★ 最常用 |
| **怒りマーク（青筋 💢）** | 生气（轻→重都能用） | 太阳穴 / 后脑 | 跳出 + 轻微脉动 | ★★★ |
| **暗雲 / 落ち込み線** | 低落、沮丧 —— **用户说的"小阴云"** | 头顶 | 云飘 + 竖线垂下 | ★★★ |
| **ZZZ / 鼻チョウチン** | 睡着、犯困 | 头顶斜上 | 逐个浮起放大消失 | ★★★（配合 sleepy） |
| **音符（8分音符）** | 心情好、哼歌 | 头侧斜上 | 飘起 + 左右摇 | ★★ |
| **ハート** | 好感、喜欢 | 脸周围 / 眼里 | 浮起 + 缩放脉动 | ★★ |
| **？ / ！ / ！？** | 疑问 / 惊讶 / 懵了 | 头顶 | 弹出（Q 弹） | ★★ |
| **湯気** | 怒到顶点、也可表示害羞发热 | 头顶放射 | 向上飘散 | ★★ |
| **電球** | 灵光一闪 | 头顶 | 亮一下 + 放射线 | ★★ |
| **垂れ線 / 青ざめ** | 不安、脸色发白 | 额头 / 眼周 | 竖线落下 | ★ |
| **ぐるぐる目** | 混乱、晕 | 眼睛里 | 旋转 | ★（**官方注：能做但很贵**，见下） |
| **集中線** | 强调、冲击 | 整屏 | 瞬间出现 | ★（全屏特效，另一套机制） |
| **揺れ線** | 发抖（冷/怕/怒） | 贴着身体 | 高频小抖 | ★ |
| **涙 / よだれ** | 哭 / 馋 | 眼角 / 嘴角 | 流下 | ★ |

**"小太阳"不在传统漫符里** —— 它更接近「後光／フラッシュ」那一类（背景发光）。
可以做，但口径上归「背景特效」而不是「漫符」，实现方式也不同（见下第四节）。

### 三、Live2D 里怎么做（和我们星星眼的做法**完全一致**，不需要新发明）

来源：`https://surume1ka.com/archives/2213`、`https://surume1ka.com/archives/2207`、
`https://note.com/itodaneko/n/ne16209ddafb5`、`https://note.com/moimoi_sp/n/n267967b33084`

- **新参数 min 0 / default 0 / max 1，用不透明度 0↔100 切** —— 和我们 `ParamStarEye` 一样。
- **差分件 clipping 到白眼 ID**，就会跟着闭眼自然消失（我们用的是 `mask: eye_?_socket`）。
- 想要"瞬间切换不要半透明中间态"，可以改用**描画顺 499↔500** 而不是不透明度。
- **★★★ 官方负荷惯例**：「１つの描画オブジェクト・デフォーマに多くのパラメーターを割り当てると
  動作に負荷がかかってしまいます。基本的に、**パラメータの割り当ては2つ、
  どうしても必要なときは3つまで**」—— 一个部件最多绑 2 个参数，极限 3 个。
  **我们的 `fx_sparkle_i` 正好是 2 个（总闸 ParamStarEye + 自己的 ParamSparkleN），卡在线上。**
  以后设计漫符件要照这个数守着。
- **★★ 互斥的收进同一参数，能同时出现的各给各的**（kawase）：
  「きらきら目・ハート目**同時発動しない**ので同一パラメにまとめる」
  「**涙目は上記差分と併用したい**ので個別パラメにする」
  → 对我们：眼内差分（星/心/ぐるぐる/><）**一条参数**；
    头顶漫符（汗/怒/云/音符）**各一条**，因为"又慌又生气"是合理的。
- **ぐるぐる目可以做成动画，但很贵**（moimoi：「これらはアニメーションさせることもできますが、
  結構コストがかかるので、要望がない限りやりません」）→ 我们先做静态，别一上来就做旋转。

### 四、★★ 意外收获：官方说表情就是「加算差分」，我这轮的修法方向是对的

`https://docs.live2d.com/en/cubism-editor-manual/facial-expression-system/`
官方「Facial Expression Mechanism」给的表就是 **Default / Expression / Difference 三列**，
并且写明：**"This difference value is added to the parameter value of the motion created
separately. The standard setting is Add"**。
官方还专门有一节「Parameters to Note → Opening and closing of eyes」：
左右眼开闭默认 1.0、表情值设 0.8，那么**加进眨眼动作的是 −0.2 这个差值**。

→ 也就是说**官方默认就是"在眨眼之上叠加一个差值"，从来不是"把眼开合钉死"**。
我们原来六个表情全写 `mode:"set"` 属于偏离官方口径，2026-10-16 改成 `multiply`
（引擎三种模式 add/set/multiply 都支持，multiply 和 add 都能保住眨眼）。
**结论登记在 DC58，这条外部证据是事后补上的 —— 当时是靠真机实测发现的，不是靠查文档。**

### 五、"小太阳"这类背景特效是另一套机制

漫符是**贴在角色身上/旁边的小图**，和角色同一个坐标系、跟着头动。
"小太阳 / 后光 / 下雨" 这类是**整屏或大面积的背景层**，口径上要分开：
- 漫符 → `fx_*` 部件，挂在 `head` 组里跟着头转。
  **（我本来写的是"我们现在的 ✨ 没挂 head 组，是个缺陷，记 G117"—— 查了 rig.json，
  八颗 ✨ 的 group 全是 `head`，和 `seg_head`/`eye_l_ball` 一样。结论错，已撤。
  按 A33：下结论之前先查。这条留着当正面例子。）**
  真正要注意的是**头顶空间**：`seg_head` 的 pos.y = 68，整只角色在 848×1360 画布上
  头顶只剩 68px；漫符要是画在头顶上方会顶出画布。实测见下。
- 背景特效 → 需要一个**画布级的特效层**（在所有部件之下或之上），现在引擎没有这个概念。
  Live2D 社区的做法是"把效果画成图片再建模"（`https://community.live2d.com/discussion/194/`，
  官方明确说 Live2D 本身没有粒子系统）。所以不需要粒子引擎，但需要一个**背景层的位置约定**。

## 第二十七批（2026-10-16）：待机与细微表情 —— 用户「细微表情也要做上」之后补的功课

### 一、★★★ 官方《提高动态质量的技巧》里最便宜的几条

`https://docs.live2d.com/en/cubism-editor-tutorials/motion-hint/`
（中文版 `docs.live2d.com/zh-CHS/cubism-editor-tutorials/motion-hint/`）

1. **只转脸不转身 = 机器人**。脸动的时候身体 X/Z 也要跟着动。
2. **脸和身体完全同步 = 机器人**。要按惯性**错开时间**：
   「顔を振り向くことで体が後からついてくる」。
3. **反动与刹车**：「人间は瞬时に动きを止めることができません」——
   手臂会越过目标一点、再退回来一点才停。
4. **★★★「人在转脸或改变视线时，经常会先眨眼」**
   （"Humans often blink when they turn their faces or change the direction of their eyes"）。
   —— 这条极便宜、效果极好。**我们引擎里已经有了**（`LOOK_BLINK_DIST/CHANCE/COOLDOWN`，
   位移 0.45 触发、55% 概率、1.2s 冷却），本轮核对确认，不用重做。
5. **「微妙な眉毛の動きを細かくつけてあげると良い」** —— 正是 A48 要的东西，官方自己点名了。
6. **待机要\"静\"，动起来要动得看得出来**：「待機中は静止させ、動かす時はハッキリと」。

### 二、★★★ 瞳孔微动（マイクロサッカード）

`https://cgbox.jp/2019/07/25/live2d-memoto/`
- 原话：**「人の眼球は静止していることはありません」** ——
  所以给瞳孔设常驻的微小游移（アイドリングモーション）能明显增加真实感。
- **反面警告（很重要）**：「やりすぎると、違和感がでますし、**常に慌てている印象になる**」。
  → 幅度必须是**亚像素到 1 像素**级别。我们的视线满量程只有 `max_offset = 4.0 × 2.5` 像素，
    所以归一化幅度 0.26 ≈ **1.0px**，这是**实测标定**出来的（`tools/calib_saccade.py`），不是拍的。
- 另一条：睫毛要和视线一起动，视线位移用**变形器**而不是直接绑原画部件。

### 三、★★ 待机动作不能只有一条

`https://note.com/ryodist/n/nd15bac2226d3`
- 判据写得很好用：
  **自然** =「常に変化が起きており、大なり小なり同じパターンが**3～4 回以上繰り返されていない**もの」
  **机械** =「あまり変化が起きず、同じパターンを繰り返すもの」
- 做法：**复制待机动作、微调出几条，随机轮播**（不是把单条做长）。
- 警告：「動かないと違和感を覚える」「**動きすぎると目に付く**」——
  别为了"自然"就加大动作幅度，正解是**多条小变化**。

### 四、★★ 官方自动眨眼本来就该带随机

`https://docs.live2d.com/en/cubism-sdk-tutorials/eyeblink/`
- 官方组件参数是 **Mean（平均间隔）+ Maximum Deviation（最大偏差）**，
  并明说：固定周期「the cycle will be uniform, which is **unnatural**」。
- **我们引擎已经做了，而且更进一步**：`interval_exponential` 走指数分布
  （`zrand_expo`），比"均值 ± 偏差"更接近真实的泊松过程。本轮核对确认，不用重做。

### 五、本轮据此的取舍

查完发现**官方那几条便宜招里，我们已经有两条**（转视线眨眼、眨眼间隔随机），
真正缺的只有**瞳孔微动**，所以本轮只做它 —— 它同时结清了 T39.3 剩下的那半（虹膜 Sway）。
剩下的（身体跟随错时、反动刹车、多条待机轮播、眉毛细微动作）排进 T44。


## 第二十八批：单边嘴角 / 抿嘴 到底有没有标准通道（T44.1）

T44.1 要回答的是「哪些微表情现在根本没有通道」。眉毛那边查下来是齐的，
嘴这边不确定，所以专门查了一轮：官方标准参数表里**没有**任何单边嘴角参数，
那业界是怎么做的？

**① Animaze《复杂口角形状的 Live2D 模型制作方法》**
`https://www.animaze.us/manual/gettingstarted2djp/extparam2d`
给了一张**扩展**参数表（标准表之外的）：

| 用途 | ID | 范围 |
|---|---|---|
| 上唇 | `ParamLipUpper` | −1 ~ 1 |
| 下唇 | `ParamLipUnder` | −1 ~ 1 |
| 舌头 | `ParamTongue` | 0 ~ 1 |
| 嘴宽 | `ParamMouthSize` | −1 ~ 1 |
| **嘴 左右** | **`ParamMouthX`** | **−1 ~ 1** |
| 鼓腮 | `ParamPuffCheeks` | 0 ~ 1 |

关键在 `ParamMouthX` 的原文说明：**「口角を『クイッ』と上げるような、左右の位置を
調整するパラメータになります。よりアニメチックな表情が再現できます」**，
做法是「[+1.0] で左側に、[−1.0] で右側に移動し、**口角が少し上がるような形状**を
作成します。**頬も同様に口の動きに合わせて少し上がるように**調整します」。

→ **这是本批最重要的一条**：业界做"坏笑 / 不以为然"那种单边嘴角，**不是**造一对
`MouthCornerL/R`，而是用**一个** `ParamMouthX`（嘴整体左右偏）顺带把偏过去那侧的
嘴角带高。一个参数办两件事，正好对上官方"一个表情最多 2 个参数、不得已才 3 个"的
负荷惯例（第二十六批）。**我们要做单边嘴角，就按这条做。**

**② 旧 Live2D 论坛《简单的嘴部做法》里的专业档 deformer 清单**
`https://forum.live2d.com/discussion/533/簡単な口の作り方-パーツ切り替え方式`
列了职业做法会拆的变形器，其中确有左右独立的：
**「口の非対称デフォーマ、口の片側だけ大きく変形させる」「口角Lデフォーマ / 口角Rデフォーマ、
口の端を上下させる」**。→ 左右独立是存在的，但属于"职业档全套"，
和 ParamMouthX 是两条成本差很远的路。

**③ 官方 PerfectSync 讲座给了优先级**
`https://juku.live2dcs.jp/en/course/course-18/`
把表情参数按推荐度排成 ★★ / ★ 两档。**「Left/Right Mouth Corner Up/Down」、
「Mouth Width Left/Right」、「Duck Lips」、「Mouth Smile」全在 ★（最低档）**；
★★ 档是「Jaw Open/Close」「Lips Open/Close」「Tongue Out」「Cheek Puff」。
→ **单边嘴角按官方自己的排序就是锦上添花**，不该排在 T44 前面。

**④ 反向提示：片眼笑不值得做**
`https://cgbox.jp/2020/04/14/live2d-smile/`：「デフォルトで左右の目の笑顔が設定されて
いますが、**片目だけ笑顔になることは稀だと思うので**、僕は新しくパラメータを作っちゃいます」
—— 作者宁可把 `ParamEyeLSmile`/`RSmile` 合成一个。
→ 我们已经有左右独立的笑眼，**不用再往"单边"方向加东西**，够用了。

**⑤ 口角连动的现成配方** `https://bloomeria.jp/blog/live2d-parameter-optimization`：
`MouthOpenY ≥ 0.5` 时把 `MouthForm` 带 +0.1~0.2，说话时嘴角自然上扬。
→ 这条便宜，可以直接进 T44.6。


## 第二十九批：眨眼频率到底该怎么随情绪变（T44.2）

T44.2 要让眨眼跟着情绪走，但"生气该眨多快"不能拍脑袋。查的是生理/心理学那边的实测。

**① 基线：成人约 15~20 次/分**
`http://www.nips.ac.jp/kaoninchi/pdf/2013/1.pdf`（自然科学研究機構 生理学研究所）：
「我々ヒトは 1 分間に 15-20 回ほど瞬きをしています。眼球を潤すという生理的機能のためには、
1 分間に 3-4 回で十分」——即**大部分眨眼不是为了湿润眼球**，是脑在做信息切分。
`https://fukami-ganka.jp/blink-role/` 同样给 15~20 次/分。

**② 增多的条件：怒り・興奮・緊張・難しい課題**
`https://www.brh.co.jp/publication/journal/082/research_2`（中野珠実）：
「まばたきの頻度は精神状態によって大きく変動し、**怒っている時や緊張している時などは
非常に多くなる**。また、**難しい課題に向かう時も急激に増加する**」。
社会心理学那边给了更老的出处 `https://www.jstage.jst.go.jp/article/jssp/12/3/12_KJ00003724740/_pdf`：
Ponder & Kennedy (1927) 发现怒り/興奮で瞬目が増える；
**不安・神経症傾向と瞬目率に高い正の相関**（Harris et al. 1966；山田・宮田 1986）。

**③ 减少的条件：视觉专注（≠ 动脑）**
`https://fukami-ganka.jp/blink-role/`：读书约 10 次/分、电脑约 6 次/分、手机/游戏约 5 次/分，
**降到常态的 1/4 以下**。`https://kenko.sawai.co.jp/mirai/202502.html` 特意点出这对矛盾：
「ゲームに集中しているときはまばたきが減るけれど、**仕事で難しい問題に頭を悩ましている
ときはまばたきが増えます**」。
→ **盯着看 = 减少，动脑 = 增加**。桌宠的 `think` 属后者，所以我们给的是 1.3 而不是 0.7。

**④ 困倦不是"眨得少"，是"眨得慢而久"**
`https://www.jstage.jst.go.jp/article/jjppp/40/1/40_2205si/_pdf`（福田恭介《自発性まばたき研究の 40 余年》）：
45 分钟 vigilance 任务里**瞬目率随时间递增**，与「覚醒水準の低下」挂钩。
→ 所以 `sleepy` 给的是 `rate 1.15 + closed_scale 3.0`（次数略增、每次闭得久），
**不是**直觉上的"困了就少眨"。这条如果不查就会做反。

**⑤ ★ 反面警告：眨眼多会让角色显得不可信、不亲近**
同一篇社会心理学论文引大森ら(1997)：给被试看「まばたき 79 回/分」与「10 回/分」两段视频，
结果**眨眼多的人物被评价为缺乏力動性・誠実性，親近性にも欠ける**。
→ 两个后果：(a) 桌宠基线要**偏少**，我们取 [2,8]s（均值 5s = 12 次/分），
比真人的 15~20 慢，是**故意的**；(b) `affection`/`smile` 要**反过来压**到 0.8/0.9 ——
亲昵那一侧靠少眨眼换从容感。

**⑥ 恋爱情境的量级参考** `https://motekudoki.hatenablog.jp/entry/2024/11/11/104340`：
常态约 20 次/分，在好感对象面前升到 30 次以上 ≈ **1.5 倍**。
→ 我们最高档 `angry 1.70` 定在这个量级附近，没有离谱放大。


## 第三十批：Live2D 官方的「换装」三种方式（T45.5~T45.7，2026-10-16）

动手前先查的那一步 —— 结论是**我们要的机制引擎里早就有了**，差点自己重造一遍。

### 官方的决策表（直接回答了"三档怎么做"）

`https://sites.google.com/cybernoids.jp/cubism2/info/genga/model_change`
《モデルの切り替え方式の検討》把换装方式分成几类，并明说各自用在哪：

| 官方方式 | 官方原话 | 我们的对应 |
|---|---|---|
| **moc 切り替え方式** | 「**服替えは一般的にこの方式を使います**」 | `forms/`（整套换 rig） |
| **パーツα方式** | 「**腕の切り替えには一般的にこの方式を使います**」 | `rig.poses`（互斥部件组，已有 `eye_hl_style`） |
| **テクスチャ方式** | 「モデル読み込み後、テクスチャ設定命令でテクスチャを切り替えます・**色変更などが簡単にできる**」 | **`zrig_apply_outfit()`** ← 我们三档全走这条 |

### 为什么"按颜色换色"行不通 —— 官方早就写明了

`https://sites.google.com/cybernoids.jp/cubism2/editor/modeler/models/avatar`
《03. アバターモデル》：
> 色変更することを考慮して切り分けを行います。…**色替えは描画オブジェクト単位で設定しますので、
> 服と肌が一つの描画オブジェクトですと、まとめて色変更されてしまいます**。

**我们实测完全印证**：`seg_torso` 里外套的白被最近邻判成「袜 #F6F2F0」(22.5%)、
「外套主体 #F0F0F0」连前六都没进；`seg_leg_l` 的**腿部皮肤**被判成「衬衫 #FCE8D8」(34.4%)。
⇒ 按颜色分不开衣物，程序化换色会把皮肤一起染了。官方的解法是「カラーグループ設定」（色组），
我们的解法是**按件分工**：单一衣物的件程序化换色，多衣物纠缠的件 AI 整张重绘。

### 换装要给"更大的衣服"留余地

`https://sites.google.com/cybernoids.jp/cubism2/tutorials/user_tutorials/costume_change`
《コスチューム着せ替えを想定したモデリングのコツ》：
> レイヤーとレイヤー（テクスチャとテクスチャ）の間が近すぎる場合は、
> **今の形よりも大きなコスチュームへの変更が難しくなります**。

⇒ 这条直接决定了我们的闸怎么设：**换件不能卡 IoU**。实测粗针织开衫换棒球夹克
外长 12.0%，那不是 bug，开衫本来就厚。真正会露洞的是**内缩**（我们卡 5%，实测 0.1%）。

### 三个以上衣装差分怎么切

`https://creatorsforum.live2d.com/t/topic/2921`：一条参数打三个键、每个键登记一套衣装
（避免"手变四条"的叠加问题）；或每套一条不透明度参数 + exp3 控制。

### Cubism 4.2 的乘算色/屏幕色（我们**没有**，记下来备查）

`https://docs.live2d.com/en/cubism-sdk-manual/multiply-color-screen-color-web/`
按 Drawable 设 `setDrawableMultiplyColor()` / `setDrawableScreenColor()`，可运行时改。
这是比"预生成贴图"更灵活的换色路线（能做拾色器让用户自选颜色），
但**前提仍是衣服和皮肤已经分成不同 Drawable** —— 对我们来说那是 T45.6 之后的事。


## 第三十一批：Live2D 的尻尾与獣耳（T45.2b / T45.3，2026-10-16）

用户打回第一版尾巴时的原话：「**live2d有教程吧。做参考别这样乱作了**」。这批就是补这一课。

### 尻尾的做法

- **多段振り子（多段摆）** —— `https://note.com/itodaneko/n/n3b5e2ada3f4b`
  （伊糖だねこ《Live2D練習記録⑧ ー 猫耳と尻尾・物理演算 ー》）：
  > 尻尾の揺れは長いパーツなので**多段振り子**にしています。入力設定に尻尾を振る
  > パラメータだけでなく、**呼吸のパラメータを追加することで、常に尻尾がゆらゆらする**
  > ようになっています。

  又：多段振り子では「毛先の動きから段階的に大きい動きをつけ」「**毛先の動きが1番下、
  根元が1番上**になるように並べ」。

- **分段数** —— `https://x.com/Haruhi_Vtuber/status/1883822197846028374`（はるひ-Live2D）：
  > しっぽ全体を**９つのパラメータ**で分け、しっぽの先にかけて**段階的に速く揺れる**ように
  > 調整しています。ループモーション用の**空のパラメータ**を作って、全て物理演算で動かしています。

- **变形路径点数** —— `https://note.com/moimoi_sp/n/n5310a594e40d`（もいもい）：
  尻尾は「変形パスからスキニングにして、物理演算で調整」「**変形パスで4,5点打ちます**」。

- **XY 要分开两条摆** —— `https://note.com/asasinstudio/n/nb8c9c8feb081`（朝sin）：
  > 極論 **XY方向で別々のパラメータを用意し物理演算でもXY別々の振り子**を用意し割り振れば良い。
  > おすすめは**回転＋ワープデフォーマ**。回転デフォーマだけでXYを作るのはおすすめ出来ません。

### ★★★ 一条**不能照搬**的配方（本仓库的关键偏差）

「把呼吸加进物理**输入**，尾巴就会常にゆらゆら」这条在**官方引擎成立**，因为
**官方 physics 的输出是摆角（绝对位置）**。

**我们的引擎输出的是「滞后量」**：`src/core/zrig.c:3013`
```c
ph->out_cur = ZC_CLAMP(ph->pos - target, -ph->max, ph->max);
```
呼吸只有 0.28Hz，摆锤完全跟得上 ⇒ `pos − target ≈ 0`。**实测照抄后只摆 0.3 帧像素。**

⇒ 在本引擎里「自己动」必须有**独立驱动源**（动作通道的慢正弦），物理只负责在它**之上**
叠二次滞后。改过来之后实测 **6.2 帧像素 / 11.3 画布像素**，波形是干净正弦。
这条差异已写进 `docs/LIVE2D_CONFORMANCE.md`。

### 獣耳的做法（T45.3 的依据，先存着）

- `https://vtuberkaibougaku.site/2021/09/27/live2d-nekomimi/`：耳朵用三层形变器
  （眨眼用 1 个 + 摇晃用 2 个）；**「あまり根本を動かしてしまうと猫耳自体が浮いて見えてしまう」**
  —— 耳根不要动，否则耳朵像是浮在头上。摇晃「1つ目のデフォーマには大きい動作、
  2つ目には先っぽの方の揺れ」。
- `https://note.com/itodaneko/n/n3b5e2ada3f4b`：猫耳「主に**眉毛の動き**に連動して動かす」，
  输入种别用**角度**（这样耳形会跟着眉形走）。
- `https://otimusya24.com/nekomimi-lve2d/`：另一派把耳朵连动到**瞬き**；
  参数「耳揺れ」取 −30~30，「−30で耳が下がる、30ではピンと張る」。
- `https://note.com/himono_vtuber/n/ne6f7c0fdfdaa`：獣耳的素材要拆成
  **・前面 ・奥 ・中のふさふさ** 三片。

### 画风口径（这次返工的真正原因）

用户：「**色彩光影以及画风要更加符合小寻的形态，还是太像简笔画了**」。
实测她的素材**根本不是平涂**：`hair_front` 4762 色 / `hair_back` 5026 色 /
`seg_torso` 25828 色，全是**柔和渐变厚涂**。
⇒ DC55「AI 出图须按色卡重铺」的口径**只适用于漫符那类平面符号**；
挂件要和身体长在一起，强行重铺 = 把渐变压成几个平色 = 用户说的「画风都不一样」。


## 第三十二批：猫尾的解剖与情绪语言（T45.2c，2026-10-16）

用户打回第二版尾巴：「**猫尾巴不是这样的吗？为什么尾巴的尾部这么尖，很乖吗，而且很难看。
猫的尾巴可以自由的摇晃、操控，做出情绪的表达，有炸毛，有立起尾巴，有自然摇晃，
有生气的摇晃等等等等**」，并附了真猫照片。

### 一、解剖：猫尾不是锥形

我做成了**锥形尖梢**。看真猫照片（橘猫竖尾、虎斑卧姿等）：
**通体近等粗，梢部钝圆**，粗细约为长度的 1/7。锥形尖梢是蜥蜴/老鼠的尾巴，不是猫的。

### 二、尾巴是一套**离散姿态语言**，不是一根会晃的装饰

多来源一致（`https://petcookco.com/blog/posts/cat-tail-language` 8 种、
`https://heromamapet.com/blog/cattail/` 10 种、`https://jandan.net/p/106099` 9 种、
`https://zhuanlan.zhihu.com/p/668382954`）：

| 姿态 | 含义 | 原文摘要 |
|---|---|---|
| **高高竖起** | 开心、自信、有安全感 | 「貓咪**少數明確表達正面情緒**的方式」「迎接你回家」 |
| **竖起+问号钩** | 友善邀请 | 「该陪朕玩儿了」 |
| **竖起+尖端颤抖** | 极度兴奋 | 「非常開心…也可能是氣味標記的前兆」 |
| **缓慢大幅摇** | 专注锁定 | 「當貓專注於一個東西的時候…接下來它就要『貓撲』啦」 |
| **快速甩/拍地** | 烦躁→生气→攻击 | 「大幅度的左右擺動，通常都是代表很生氣，準備進入攻擊階段」 |
| **炸毛** | 惊吓、极度紧张 | 「豎起身體的毛髮讓自己看起來更龐大」，伴「齜牙和哈氣」「飛機耳」「拱背」 |
| **夹紧贴腹** | 恐惧、示弱 | 「藏進雙腿間…極度沒有安全感」 |
| **轻拍地面** | 「我听到了但不想动」 | 「節奏慢、力道小，通常還是放鬆狀態」 |

**★ 一条反直觉的**（和狗相反，要防止做反）：
`https://blog.sina.com.cn/s/blog_9cfc15710101a0b5.html`
> 狗摇尾巴不一定是高兴，**猫摇尾必定是发怒也不对**。猫摇尾巴大多时间表达的感情是
> ——**矛盾、左右为难**。……一旦它拿定主意，它的尾巴便立即停止摇摆了。

⇒ 「摇摆」本身是**犹豫/纠结**，幅度与速度才区分烦躁与愤怒。

### 三、耳朵也是情绪通道（T45.3 用）

`https://jandan.net/p/106099`：「**耳朵直立**表示很快乐或很警觉；**向后或者低平**（飞机耳）
表示被吓到或很生气。」`https://zhuanlan.zhihu.com/p/668382954`：「當一隻貓**往前**豎起耳朵時，
有時候是代表對眼前的人事物感到**相當好奇**。」

### 四、实现口径：三种形状差太远，必须走差分件

竖起 / 垂下 / 炸毛的轮廓完全不同（炸毛宽度是常态的 3 倍），**几何变形做不出来**。
走官方**パーツα方式**（按 id 切部件显隐，第三十批已记：官方说这是**腕替え**那一类的做法），
对应我们的 `rig.poses` 互斥组。

---

## 第三十三批：猫耳**画在头上的什么位置、画多大** —— 以及怎么自检

来由：猫耳的位置和大小被用户连着打回**四次**。第四次的原话是
「位置大小完全错误。你自己也检测一下，然后学习和参考教程以及网络上的资料。」
这是两条独立要求，缺一不可：**先自己量**，**再对着教程量**。
前三次我都只做了第三件事（凭印象改），所以一直收敛不了。

### 一、大小：猫耳长 = 脸高的 **1/3**（两家独立口径一致）

`https://medibangpaint.com/en/use/2023/05/cute-animal-ears/`
> The ideal ear length ratio in cats is **one third** of the face length.
> Set the ratio of ear length to face length to **two-thirds for rabbits,
> one-third for cats and one-half for foxes**.

`https://note.com/kakaman/n/n1971710751c2`（「ケモミミの描き方」）同口径：
> Rabbit: About 2/3 of the face's vertical length ／ Fox: About 1/2 ／
> **Cat: About 1/3 of the face's vertical length (smaller ears)**
> …ears that are too long might make the entire illustration look
> **vertically stretched**, which could look less appealing.

⇒ 兔 2/3、狐 1/2、**猫 1/3**。我们实测脸高 227 画布px ⇒ 目标露出高 **76px**。
⇒ 也解释了用户为什么说「像兔耳」：旧版露出高/脸高 = **0.65**，正好踩在兔耳档。

### 二、耳根悬空的**唯一原因**：画在头发之上而不是插进头部

`https://kiri-hana.com/minikyara-nekomimi/`（这篇有 NG/OK 对照图，说得最死）
> ### 耳が浮いて見えるのは「髪の上」に描いてしまうから
> 猫耳はあくまで**頭部に生えているパーツ**なので…まず頭のアタリ（丸）に耳をつける
> 意識が必要です。その上で、**髪を耳の根元に重ねる**ように描くことで、自然な一体感が
> 生まれます。髪の上に耳を「乗せる」のではなく、頭のラインに沿って「**差し込む**」
> イメージで描く
> - NG例：耳が**髪のアウトライン**に沿って配置されており、浮いて見える
> - OK例：耳が**頭の丸み**に沿って描かれており、自然に見える

★ 这正是我们的 bug，而且是**层号**问题不是坐标问题：
头顶那片头发是 `hair_back`（层 170），`hair_front`(240) 从 y=163 才开始、只管刘海。
猫耳原本在 **185/186 ⇒ 整只画在 hair_back 之上** = 教科书式的「髪の上に乗せる」。
修法：新开槽 `head_in_hair`，层 **165/166**（在 hair_back 之下，144~169 整段空着）。

### 三、左右位置：「11 時と 1 時」

同篇 `kiri-hana.com`：
> 正面顔の場合、頭の円を時計に見立てると、**11時と1時の位置**に配置するとバランスが
> 良くなります。頭の丸みに沿わせて**耳の根本を傾ける**ことで、自然な立体感が生まれます。

⇒ 头中心 ± 头半宽·sin30°。实测头中心 x=419、最宽 246 ⇒ 耳心 **364 / 474**。

`https://atam-academy.com/blog/6709/`（猫の顔）补一条间距口径：
> 真上ではなく少し左右に離し、**耳と耳の間隔を耳１つ分**ほど空けるとバランスが取れます。

⚠ 这条是画**猫本体的圆脸**用的。猫娘的头被头发撑宽，照搬会让两耳超出头的剪影 ——
我们实测取 11/1 时位，两耳总跨度 / 头最宽 = **0.78**，落在惯例 0.75~1.0 内。

### 四、形状与角度

`https://atam-academy.com/blog/50779/`：
> 猫耳の基本シルエットは、**少し平べったい正三角形**に近い形状です。
> 耳の正面は真正面ではなく、**少し外側を向く**イメージで描きましょう。

`https://medibangpaint.com/en/use/2023/05/cute-animal-ears/`：
> If you draw them vertically, the ears will look like **headbands**, which is not good.
> Most animals have their ears **tilted forward**.

`https://note.com/kakaman/n/n1971710751c2`：
> actual animal ears are attached gently from the back of the head toward the front and
> are **tilted slightly forward**.… Be aware of the position where the **bangs and back
> hair separate**（前髪と後ろ髪が分かれる位置を意識する）

`https://atam-academy.com/blog/30576/`：
> **接地面を直線ではなく、頭部の丸みに合わせた曲線（カーブ）で描く**ことで、
> 実際に生えている感覚をリアルに再現できます。
> 人間と動物の耳が両方ある「4つ耳」の状態を避けるため、通常は**人間の耳を描きません**。

★「髪の分かれ目を利用する」实测印证：发团剖面顶点在画布 x=425（中分缝两侧各有一个发量高点），
和头中心 419 基本重合 —— 这个头确实有明确的分缝可以利用。

### 五、兽耳的情绪表现（补第三十二批的猫行为学，这次是**作画**口径）

`https://atam-academy.com/blog/30576/`：

| 情绪 | 耳的状态 | 原文要点 |
|---|---|---|
| 喜び（リラックス） | 自然、耳先ゆるやかに**外側** | 「少し開くように描きます」 |
| 怒り（威嚇） | **イカ耳**、横〜後ろへペタン | 「シルエットを**平らに**するイメージ」 |
| 悲しみ | 力が抜け**垂れ下がる** | 「怒りのときよりも**力なく**垂らす」 |
| 驚き（警戒） | **垂直に近く**上へスッと | 「耳の穴を正面に向ける」 |

⚠ 怒和悲**都是倒下但方向不同**（怒=横～後ろ、悲=前or横且更无力）。
我们只有一条角度参数，做不出方向差，只能用幅度差近似（angry −0.90 / sad −0.55）——
这是**已知的简化**，要做全得拆差分件。

### 六、把以上口径变成可执行的闸门

落到 `tools/qa_head_accessory.py`（对着跑起来的预览量，退出码 0/1）：

| 判据 | 区间 | 出处 |
|---|---|---|
| 露出高 / 脸高 | 0.26~0.40（教程值 .333） | 一、medibang + kakaman |
| 耳根压在头发下的比例 | ≥ 80% | 二、kiri-hana |
| 两耳总跨度 / 头最宽 | ≤ 1.02 | 三、11時/1時 |
| 单耳 宽/高 | 0.60~1.05 | 四、「少し平べったい正三角形」 |
| 耳尖离画布顶 | > 2px | 旋转时别被切 |

**量法上踩过的四个坑**（脚本里都绕开了，细节见其 docstring）：
1. 逐列取最高不透明像素求"头发表面" ⇒ **呆毛的细尖被当成发团**，发顶读成 y=66（真值 ≈115）。
   脸高是所有判据的分母，这里错一次全表跟着错。⇒ 先做 ±7px 水平腐蚀。
2. 开关前后两帧直接做差 ⇒ **混进尾巴和呆毛**，包围盒能跨到 y=746。⇒ 每档连拍 6 帧取均值。
3. 耳朵躲在**半透明发梢**后会把合成 alpha 顶过阈值 ⇒ 整条发缘被判成耳朵。
   ⇒ 判据改成强跃变：戴上 α≥200 **且** 摘掉 α≤60。
4. 几粒抗锯齿杂点就能把耳高从 95 读成 171。⇒ 连通域标记只留最大两块。

## 第三十四批：尾巴怎么动才像活的 —— 行为学的「阵发」与动画的「行波」（T45.2g，2026-10-17）

**起因**：用户说「我的意思是让尾巴像真正的动物一样能让桌宠自由操控……更自然更真实的活动」。
先按纪律**自己量**：拿确定性探针跑 60 秒，当时的尾巴是 12 个正峰、幅度**全部 3.2279°**、
标准差 0.000015°、变异系数 0.0005%，一个周期的自相关 0.982，物理链横向位移全程 0.000。
**那是节拍器，不是动物。** 带着这个结论去查资料。

### A. 行为学：猫尾的运动是**阵发事件**，不是持续节拍

- **★ 最硬的一条实测数字** `https://blog.catcognition.com/why-do-cats-wag-their-tails/`
  转述 de Mouzon et al. 2023（Université Paris Nanterre，发表于 *Animals*，12 只猫的
  先导研究）：猫在**人忽视它**时平均摆尾 **13.98 秒**，而人与它说话并打手势时只有
  **0.39 秒**。同页：「Lateral tail movements correlated with frustrating situations,
  not positive interactions」。
  ⇒ 摆尾是**被事件触发**的，默认状态不是一直在摇。同一篇还指出猫的侧向摆尾
  **不等于**狗的高兴摇尾，对应的是挫折/冲突/高度专注。
- **★ 升级链（这决定了"频度和力度要一起涨"）**
  `https://perfectpetinsurance.co.uk/pet-advice/cat-tail-language/`：
  「a slow sway means focus or indecision, a twitching tip means concentration or early
  irritation, a fast side-to-side lash means anger or frustration, a floor thump means
  the cat wants something to stop…**Speed rises as tolerance falls**」。
  `https://meowant.com/blogs/cat-facts/cat-tail-language-interpretation-guide`
  把它写成明确的三级：**① The Tip Twitch（只有尾梢最后一截动）→ ② The Swish（整条像钟摆）
  → ③ Thump/Lash（拍地）**。
- **★ 最常见的那一档是"尾尖抽动"，不是整条摆**
  `https://petsignal.ai/signals/cat-tail-flicking-lying-down`：「Tip-only movement is the
  calmest entry on the scale — and the version owners see most while a cat is lying down.
  When just the last inch or two twitches… **Think of it as attention leaking out of the
  tail.**」
- **★ 炸毛是非自主的**（所以 puff 的抖应当"突发"而不是"渐强"）
  `https://petfel.com/why-do-cats-wag-their-tails/`：「A puffed tail is triggered by the
  **sympathetic nervous system** and happens automatically under fear or threat」；
  同页：尾巴有 **18~23 节尾椎**。`https://kittysupps.com/...`：1994 年解剖研究，尾巴有
  **6 对肌肉**，SDL/SVL 收缩产生玩耍或躁动时那种「rapid, strong tail flicks」。
- 放松时的慢摆是**不规则**的：`https://petsignal.ai/signals/cat-wagging-tail-purring`
  「Slow sway or sweep：**loose, irregular**, the whole tail drifts side to side」。

### B. 动画原理：行波（wave principle）与跟随（follow-through）

- **★ 相位差有公式** `https://grokipedia.com/page/follow_through_and_overlapping_action`：
  「In technical implementations, such as procedural animation systems, phase shifts are
  generated to drive oscillatory behaviors… **φ = 2πfΔt** where f is the frequency of the
  motion and Δt is the time lag between components」。
  同页：「a running animal's tail lagging behind its torso before catching up, creating a
  **wave-like chain of reactions**」。
- **★ 分段延迟的具体帧数** `https://iwanttobeananimator.wordpress.com/2017/09/03/tutorial-09-how-to-animate-a-tail/`：
  「go back to animate the rest of the tail, **one section at the time**… **Each section
  will have a delay of 2/3 frames compared to the previous section**」；而且
  「each part would **first react** to the movement of the part that drags it, **moving in
  the opposite direction**」—— 延迟大到一定程度，下一段起步时是**反向**的。
- **★ 为什么单条正弦看着假（正中我们的 bug）**
  `https://www.artemisiacollege.com/feeds/blog/follow-through-overlapping-action-animation`：
  「**breaking the curve**, a technique where a shape shifts from a **C-curve into an
  S-curve and back again** as it moves. This constant reshaping gives soft materials —
  hair, tails, capes — that flexible, alive quality **rather than a stiff pendulum swing**」。
  同页还给了"尾巴尖的轨迹 rarely travels in a straight line，typically arcs through an
  **S-curve**, reversing direction as it slows"。
- **尾巴通常是被带动的，不该自己发力**
  `https://www.animationmentor.com/blog/follow-through-and-overlapping-action-the-12-basic-principles-of-animation/`：
  「Make sure the tail always feels like it's along for the ride. The tail should **never
  lead** the action… should never feel like it can exert any energy of its own」。
  ⚠ **但猫是例外**：猫尾有 6 对肌肉、`大部分尾部动作是自主的`（petfel 同上），
  所以桌宠的尾巴要**两种来源都有** —— 被身体带动的跟随（物理链）＋ 它自己决定的抽动。
  我们现在两条都有：物理链做跟随，`tail_flick` 做自主。
- 社区的一句总结（r/animation）：「**Sine waves. Seriously.** If you understand how to
  impart the motion of a sine wave, combined with the C, S, and Backwards C shapes, you can
  animate any tail or tentacle movement」—— 正弦不是错的，**错的是只有一条**。

### C. 由此定下的三条做法（都已实现并实测）

| 问题 | 依据 | 做法 | 实测 |
|---|---|---|---|
| 12 个峰一模一样 | 「loose, irregular」 | 新波形 `drift` = 三条**不可通约**频率（比例 1 : 1/φ : φ）的正弦叠加，准周期、永不重复 | 幅度变异系数 0.0005% → **38.4%**，一周期自相关 0.982 → **0.681** |
| 尾巴不会自己决定动 | de Mouzon 2023 的 13.98s vs 0.39s；升级链 | 第五张情绪表 `tail_flick`：情绪 → [间隔, 幅度, 时长]，引擎自发起一次急出缓回的脉冲 | 11 种情绪的次数与峰值全部落在解析期望内（angry 34 次/6.71°，sleepy 3 次/1.03°） |
| 根和梢同相位 = 僵硬钟摆 | φ=2πfΔt；每段延迟 2~3 帧；C 形↔S 形 | 绑定新增 `lag` 字段，**时域**延迟（对非周期的抽动也成立，相位偏移做不到） | 根→梢互相关峰值在 **0.167 秒**（设定 0.17） |

## 第三十五批：衣服怎么分件、怎么摆才不"硬"（T45.9，2026-10-17）

**起因**：用户要做服装组件化（原话「主要是服装也有组件的话更生动一点，
虽然工程量更大，但是我觉得值得」）。先按纪律自己检测：
66 个部件里**一件独立衣物都没有** —— 衣服整个烘焙在 `seg_torso` / `seg_leg_*` /
`arm_*` 的贴图里，`/api/outfit` 换的只是这些件的贴图。
唯一"会动"的是 `skirt_sway_x/y` 两个形变器，实测 idle 60 秒峰峰值 **0.0599**、
频率 **0.058Hz**（17 秒一个来回）—— 等于不动。

另外**查对了一件事**：我本来以为胸前那两条是抽绳（drawstring），
放大源图 8 倍看，它们是外套**前襟的接缝线**（上下贯通的直线），
青色圆点是按扣。这件衣服没有自由垂下的抽绳。原定的"抽绳→兜帽→下摆"
顺序里第一项不成立。

### A. 分件：按"要动的单位"分，不是按"画着好看"分

- `https://www.issoh.co.jp/tech/details/4935/`：「基準は**動かす単位で分ける**こと。
  …分けなかった箇所は後から動かせず、**PSDの作り直し**になります」。
- `https://note.com/kamibukuro_0/n/n12d9227a6d56`（服のパーツ分け）：
  「違う布の場合はとりあえず分けると無難」「**別々に揺れたらかわいいパーツ**を
  分けていくイメージ」「服のボタンなども分かれているとありがたい」
  「スカートの**裏側**もあれば、裏側が見えるように揺らします」。
- `https://d-gear.biz/column/243`：「髪、リボン、袖、**フード**、アクセサリーなどは、
  **揺らす部分と固定する部分を分けて考えます**。全部を細かく動かそうとすると、
  見た目は豪華でも**制作と調整が重くなります**」。
- 官方 Cubism2 教程 `https://sites.google.com/cybernoids.jp/cubism2/tutorials/user_tutorials/kazuya1`：
  「**スカートと足の重なり順** —— スカートなどは手前の面と奥の面で**足を挟むように**
  画像を分けておきます」（摆起来时前后可见范围会变）。

### B. 揺れ：幅のある布要**多层形变器**，细长物才用变形路径

- `https://cgbox.jp/2020/12/05/live2d-shake-part/`（按部件讲揺らし方）：
  「スカートなどの場合、**変形パスを使用すると、形状が歪んでしまいます**。
  …**複数階層のワープデフォーマ**を作って揺れを作りましょう」；
  リボン系は逆に**変形パス**が向く。
- `https://cgbox.jp/2020/12/05/live2d-some-deform/`：多层的具体做法 ——
  「振り子の順番は**親→子**になるように設定してください。
  スカート揺れ2…親デフォーマのパラメータ／スカート揺れ1…子デフォーマのパラメータ」。
- **★ 诊断表（直接命中我们的状态）** `https://shiroikarasu.net/live2d-physics-not-working-fix/`
  症状C「硬い・カクつく」的三个原因：
  1. **揺れが1段しかない** ——「髪全体が**棒のように一体で動いている**と硬く見えます。
     **根元と毛先で分けて2段にする**と、毛先が遅れて動くようになり、一気に自然になります」
  2. **すべてのパーツが同じ設定** ——「全部が同じタイミングで揺れて**機械的に見えます**。
     **軽いものほど揺れやすく、早く収まる**ように差をつけます」
  3. プレビューのフレームレートが低いだけ（设置是对的）
  同页还有一条流程建议：「最初は**前髪・後ろ髪の2つだけ**で十分。
  最初から全部に設定すると、**破綻したときの切り分けが難しくなります**」。
- **★ 摆锤"吸着"是官方仕様**（我们裙摆症状的名字）
  `https://creatorsforum.live2d.com/t/topic/3734`（官方论坛回答）：
  「物理演算の仕様として、**入力が小さいと振り子が 0 に吸着する**というものがあります。
  回避方法は、・**入力を大きくする** ・「長さ」を長くする
  ・入力に X,Y,Z のいずれかの「角度」を追加して 5～10% だけ設定する」。
- **幅度宁小勿大** `https://note.com/monn_11/n/n6f9a671479bd`：
  「たくさん揺らした方が豪華に見えるのでは？と思うこともあるのですが、
  実際に動かしてみると、**意外と揺れを控えめにした方が自然に見える**ことが多い」
  「**首の動きに少し遅れてついてくるくらい**の自然な揺れ方を意識して」。
- 物理摆的三个基本量（`https://cg-method.com/vtuber/live2d-physics-settings/`）：
  長さ=小さいと速い／揺れやすさ=目安 0.7〜0.99／収束の速さ=1 が標準；
  **最大出力が 100% を超えるとパラメータ範囲を振り切ってカクつく**
  （`https://castcraft.live/blog/464/`）—— 和我们 T45.2f 的 clamp 坑是同一件事。

### C. 由此定下的做法（已实现并实测）

| 问题 | 依据 | 做法 | 实测 |
|---|---|---|---|
| 裙摆只靠物理输入，待机时身体几乎不动 ⇒ 布是死的 | 「入力が小さいと振り子が 0 に吸着する」 | 加自主参数 `ParamSkirtSway`，由 `drift` 波推 | 峰峰值 0.0599 → **1.2779**，0.058Hz → 0.133Hz |
| 一段式 = 整条像棍子 | 「揺れが1段しかない」「複数階層のワープデフォーマ、親→子」 | 拆两级：裙身 `skirt_sway_x` + 下摆 `skirt_hem_x`，下摆绑定带 `lag 0.11` | 根→梢互相关峰值 **0.117 秒** |
| 全身同拍子摆 | 「軽いものほど揺れやすく、早く収まる」 | 裙 0.13Hz/0.11s 对尾巴 0.21Hz/0.17s，刻意错开；并设闸禁止频率撞车 | 闸 `check_ambient_sway` |
| 幅度 | 「意外と揺れを控えめにした方が自然」 | 下摆横移 **2.5px**（裙宽 173px 的 1.4%）；身体真的摇时物理层再加到 3 倍 | 静止 1.10 → 身体 ±10° 时 3.16 |

## 第三十六批：兜帽（戴上/摘下）怎么做（T45.10，2026-10-17）

**官方有一门专课**：`https://juku.live2dcs.jp/en/course/course-55/`「フードの作り方」，
两章的小节标题本身就是一份清单：

> #1 素材分けとデフォーマ構造：素材の分け方／デフォーマ構造／顔と体のXYの動き
> #2 フード切り替えの動き：フードの切り替えの動き／**反動用のパラメータ拡張**／
> **髪を隠すマスク**／切り替えポイントの設定／**描画順の切り替え**／内側素材の切り替え／
> **髪をおさえる動き**／紐の回り込み／腕周りの動き

直接可用的四条：

- **① 切换方式用パーツα方式，不是几何变形。** 官方手册
  `https://sites.google.com/cybernoids.jp/cubism2/info/genga/model_change`：
  「一般的には服替えに **moc切り替え方式**、腕替えに **パーツα方式** を使います」。
  「摘下」和「戴上」形状差太远，变形做不出来 —— 和我们猫尾四姿态同样的理由。
  我们的 `rig.poses` 就是パーツα方式（一个互斥组同时只亮一个档位）。
- **② 要有遮罩，别让头发从帽子里支棱出来。**
  `https://game.deaf-ray.com/live2d-model-expression-clothing/` 转的四步配方：
  「①フード用に一枚マスク用の画像を作ります ②作ったマスクに隠したいパーツを
  すべてマスクをかけます ③フードしてる状態でフードからはみ出さないように調整します
  ④フードを外したときにパーツが表示されるようにマスクを拡大して完了です」。
  同一条还见于 `https://twiman.net/user/1554022262030073856/1707235392003645704`：
  「髪の毛がフードの中からはみ出すのを防ぐため、**マスク素材を用意しておくと良い**。
  フード裏地をマスク素材にするのもOK」。
- **③ 戴上帽子要连带关掉呆毛/发饰。**
  `https://kxn4t.hatenablog.com/entry/2026/01/26/163232`（VRChat 侧，但逻辑一样）：
  「**帽子をかぶったらアホ毛を消す**」；同页还有一张很好的联动表：
  「フード ... オンで髪をカット、おさげやベレー帽をオフ」「耳あて ... オンでフード、
  ベレー帽をオフ」—— 也就是**互斥与联动要做成一张表**，不要散落成若干条规则。
- **④ 描画順要跟着切。** 戴上之后兜帽必须盖住头发，官方课把它单列一节。
  我们这边等价于层号：兜帽进 `head_over_hair` 槽（层 250），在
  `hair_front(240)` / `hair_side(245,246)` 之上。

另外一条**反面经验**（社区，`https://creatorsforum.live2d.com/t/topic/2550`）：
有人想「フードONのときだけ髪の物理を抑制」，结论是
「Live2D の仕様上、**物理演算に条件を付けた動きの分岐はできない**」，
最后只能做两个模型切换。—— 我们的引擎没有这条限制（物理是我们自己写的），
但这说明「兜帽状态要不要影响头发物理」是个真实存在的难点，先记下。

### 由此定下的做法（已实现）

| 条目 | 做法 |
|---|---|
| 切换 | `rig.poses` 互斥组 `hood_pose`，fade 0.35（比尾巴 0.28 慢，戴帽子有分量） |
| 「不许支棱出来」 | 不另做遮罩素材，改用**互斥组本身**：`down` 档位里塞呆毛 + 两只猫耳，`up` 档位里只有兜帽 ⇒ 戴上时三样一起收 |
| 描画順 | 槽 `head_over_hair`，层 250，压在所有头发之上；素材中间留脸的开口（透明） |
| 尺寸 | 全部量出来：脸宽 **147 画布px**（逐行量肤色，不是带耳朵的 242）⇒ 开口取 1.15 倍 = 169 ⇒ 成品 **359×400**，开口顶落在额头（发团顶下 51px），下沿到肩线 |
| 物理 | 只跟随不自摆：ratio 0.22 / 刚度 **74**（猫耳 52、尾巴 18）/ 行程 3px。布越厚越贴头越不该晃，而且它和脸挨着，晃大了穿帮 |
