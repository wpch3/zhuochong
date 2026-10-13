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
