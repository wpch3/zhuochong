# 小寻 vs Live2D 标准：合规对照表

> 口径来源（2026-10-13 实际拉取核对，不是凭印象写的）：
> - 参数全集：`Live2D/CubismWebFramework` → `src/cubismdefaultparameterid.ts`（41 个标准参数 ID + HitArea 前缀）
> - 文件结构：`Live2D/CubismWebSamples` → `Samples/Resources/Haru/Haru.model3.json`、
>   `Haru.physics3.json`、`Haru.pose3.json`、`Haru.cdi3.json`
> - 美术规范：Live2D 官方 / CLIP STUDIO 教程（切件粒度、塗り足し、抗锯齿、预乘 alpha）
>
> 这份表回答一个问题：**把小寻当成一个 Live2D 模型看，它合格吗？** 下面逐条给判定，
> 并且标出"**现在不做、以后补不回来**"的项 —— 那才是真正的风险。

## 零、一句话结论（2026-10-13）

**能力层面：合格。** Live2D 的运行时能力（部件图层、两级以上旋转变形器、FFD 网格形变、
剪贴蒙版含多重/取反、关键帧动作曲线、动作淡入淡出、物理摆链含多段、参数层、表情层、
Pose 互斥组、混合模式、自动眨眼、口型同步）**全部有对应实现并且有闸门守着**。

**协议层面：此前不合格，本轮补齐。** 过去的参数表少了 18 个标准 ID，而且有两个**语义错误**：
左右眼并成一个 `ParamEyeOpen`（Live2D 是 `ParamEyeLOpen` / `ParamEyeROpen` 两个参数，
官方 SDK 的 `EyeBlink` 组就是按这两个走的）、腮红用了自造名 `ParamBlush`（标准名 `ParamCheek`）。
这类"命名空间偏移"正是**跑完了补救不了**的那种错 —— 动作、表情、口型、外部工具全都写死在错名字上。
本轮已改掉并用闸门焊死。

**素材层面：2026-10-13 起 41 项里所有"角色适用"的都已实现。** 笑眼（`ParamEyeLSmile`，G40）、
I/U/E/O 音素口型（G37）、瞳孔形状（`ParamEyeBallForm`，G41）、眉形（`ParamBrowL/RForm`，G45）
依次补齐；其中眉形**没有画新素材**——眉毛本来就是一条横着的网格能表达的形状，
给它铺一张 FFD 网格就够了。剩下的 4 项是角色真的没有那个部件（➖）。

---

## 一、标准参数 41 项逐条对照

状态：✅ 已实现且有闸门 ／ ⬜ 未实现（缺素材，结构上随时能加） ／ ➖ 不适用（角色没有这个部件）

| # | 标准参数 ID | 含义 | 小寻 | 怎么实现的 / 为什么没有 |
| --- | --- | --- | --- | --- |
| 1 | `ParamAngleX` | 头 左右 | ✅ | 引擎内建，走 `look` 子系统（平滑收敛），范围 −30..30 |
| 2 | `ParamAngleY` | 头 上下 | ✅ | 同上 |
| 3 | `ParamAngleZ` | 头 歪头 | ✅ | 绑 `head` 组 `rot_deg × 0.5`（±30 → ±15°，再大颈缝会露） |
| 4 | `ParamEyeLOpen` | 左眼 睁开 | ✅ | **2026-10-13 拆开**：部件带 `eye_side`，引擎按眼别取闭合度 |
| 5 | `ParamEyeROpen` | 右眼 睁开 | ✅ | 同上。闸门会验"闭左眼时右眼 0 像素变化" |
| 6 | `ParamEyeLSmile` | 左眼 笑眼 | ✅ | **2026-10-13 补素材**：AI 重绘"山型 ∩ 笑眼脸"→ 同闭眼那条流水线切补片（`make_eye_closed_parts.py --variant smile`）。内建参数 0..1 默认 0；**笑眼隐含闭眼**（`blink = max(blink, smile)`），谷型闭眼件按 `1−smile` 让位 |
| 7 | `ParamEyeRSmile` | 右眼 笑眼 | ✅ | 同上，左右分家（闸门验"只笑左眼时右眼 0 像素变化"） |
| 8 | `ParamEyeBallX` | 眼球 左右 | ✅ | 内建，驱动 `gaze` 标签部件，被眼眶遮罩裁切 |
| 9 | `ParamEyeBallY` | 眼球 上下 | ✅ | 同上 |
| 10 | `ParamEyeBallForm` | 瞳孔 形状 | ✅ | **2026-10-13 补**：贴图模型做不出真正的瞳形变形，用瞳孔缩放代替 —— `eye_l/r_ball` `sx × 0.18`、`sy × 0.22`（只缩放眼球件，眼白底/眼眶/眼线都是矩形小块，一放大就露方边）。surprised 动作把它推到 1.0 |
| 11 | `ParamBrowLY` | 左眉 上下 | ✅ | `brow_l` `dy × −5`（满格 = surprised 挑眉的幅度） |
| 12 | `ParamBrowRY` | 右眉 上下 | ✅ | `brow_r` `dy × −5` |
| 13 | `ParamBrowLX` | 左眉 左右 | ✅ | **本轮补**：`brow_l` `dx × 4` |
| 14 | `ParamBrowRX` | 右眉 左右 | ✅ | **本轮补**：`brow_r` `dx × 4` |
| 15 | `ParamBrowLAngle` | 左眉 角度 | ✅ | `brow_l` `rot_deg × 7` |
| 16 | `ParamBrowRAngle` | 右眉 角度 | ✅ | `brow_r` `rot_deg × −7` |
| 17 | `ParamBrowLForm` | 左眉 形状 | ✅ | 2026-10-13（G45）：`brow_l_form` 网格（cols=4/rows=2）。官方口径 −1 = しかめ（中段压下）、+1 = 山なり（中段隆起）；**不画新素材** |
| 18 | `ParamBrowRForm` | 右眉 形状 | ✅ | 同上，`brow_r_form`。眉头那一端给得轻一点（brow_l 在 c=4、brow_r 在 c=0） |
| 19 | `ParamMouthForm` | 嘴 形状 | ✅ | 微笑↔撇嘴，绑嘴线部件 |
| 20 | `ParamMouthOpenY` | 嘴 张开 | ✅ | 遮罩分轴缩放 + 口内真素材；`LipSync` 分组指的就是它 |
| 21 | `ParamCheek` | 脸红 | ✅ | **本轮改名**（旧名 `ParamBlush`，已留别名兼容），乘算腮红 alpha |
| 22 | `ParamBodyAngleX` | 上身 左右 | ✅ | `chest` 组 `rot_deg 0.12 + dx 0.35` |
| 23 | `ParamBodyAngleY` | 上身 上下 | ✅ | **本轮补**：`chest` `dy 0.9 + sy −0.004` |
| 24 | `ParamBodyAngleZ` | 上身 倾斜 | ✅ | `chest` `rot_deg × 0.25` |
| 25 | `ParamBreath` | 呼吸 | ✅ | `chest` `sy 0.012 / dy −1.2`，idle 动作里常驻 |
| 26 | `ParamArmLA` | 左上臂 | ✅ | 绕肩 ±60°（真关节，G4c） |
| 27 | `ParamArmRA` | 右上臂 | ✅ | 同上 |
| 28 | `ParamArmLB` | 左前臂 | ✅ | 绕肘 ±50°（G4c） |
| 29 | `ParamArmRB` | 右前臂 | ✅ | 同上 |
| 30 | `ParamHandL` | 左手 | ✅ | 绕腕 ±22°（G4c2，实测安全上限 40°） |
| 31 | `ParamHandR` | 右手 | ✅ | 同上 |
| 32 | `ParamHairFront` | 刘海 摆 | ✅ | `bend_x × 6`，curve `tip` |
| 33 | `ParamHairSide` | 侧发 摆 | ✅ | 左右两缕 + 两段摆链 |
| 34 | `ParamHairBack` | 后发 摆 | ✅ | `bend_x × 5`，画在脸底下 |
| 35 | `ParamHairFluffy` | 头发 蓬松 | ✅ | **本轮补**：刘海 + 呆毛的小幅"底噪"摆动 |
| 36 | `ParamShoulderY` | 肩 上下 | ✅ | **本轮补**：两条手臂组 `dy × −0.8` + 上身 −0.15 |
| 37 | `ParamBustX` | 胸 左右 | ➖ | 角色是校服平胸设定，没有对应可动部件；硬加就是假的 |
| 38 | `ParamBustY` | 胸 上下 | ➖ | 同上 |
| 39 | `ParamBaseX` | 全身 左右 | ✅ | **本轮补**：`root` 组 `dx` |
| 40 | `ParamBaseY` | 全身 上下 | ✅ | **本轮补**：`root` 组 `dy` |
| 41 | `ParamNONE` | 占位 | ➖ | SDK 内部用的空参数，不需要 |

**合计：✅ 39 ／ ⬜ 0 ／ ➖ 4（角色不适用：`ParamTere`、`ParamBustY` 等，角色没有这些部件）**

> 2026-10-13：最后两个 ⬜（眉形）清掉，**41 项里凡是这个角色适用的，全部实现且有闸门**。
> 「変形」类参数有一条官方约束值得单列：**只改形状，不带位置移动**
> （上下归 `ParamBrowLY`、左右归 `ParamBrowLX`、角度归 `ParamBrowLAngle`）。
> 这条在 `tools/selfcheck_repo.py` ⑯ 组里按几何核：中段位移必须与两端反号，
> 且 `|Σdy| / Σ|dy| < 0.25`（现值 0.172）。

### 我们在标准表之外的扩展（每一个都必须登记在这里）

| 扩展参数 | 为什么标准表里没有 |
| --- | --- |
| `ParamLegL` / `ParamLegR` | 标准表压根没有腿参数。我们做的是"裙下大腿 bend"，顶边钉死 ±20px |
| `ParamKneeL` / `ParamKneeR` | 膝盖屈伸。不用拆件 —— `bend_y` 配 `curve:"sine"`（两端固定、中段最大），峰值正好落在膝盖高度，±9px |
| `ParamWeightShift` | 重心左右。一个参数三条 bind：骨盆 `root.dx` ±5px + 两腿中段 `sine` 反向补偿 ∓4px。真人站着重心一直在挪 |
| `ParamHipDrop` | 胯下沉 / 屈膝承重。`chest.dy` +2px + 两腿 `curve:"root"`（底固定、顶最大）+2px → 上身起伏、**脚踝那一行纹丝不动**。官方《4.添加身体动作》要求"身体上下运动时脚不能离开地面"，上下起伏一律用它，别用 `ParamBaseY`（那条会把整个人平移） |
| `ParamTiptoe` | 踮脚。`root.dy` 上提 7px + 两腿 `curve:"tip"`（顶固定、底最大，作用在脚踝）收 5px。裙摆下沿不动所以不露底 |
| `ParamHairAhoge` / `ParamHairAhogeS` | 标准只有 Front/Side/Back/Fluffy，呆毛是这个角色的招牌 |
| `ParamHairSideS` | 侧发的 S 形（FFD），和整体摆动分开 |
| `ParamEyeSparkle` | 眼高光强弱（加算图层），用来演"眼里的光灭了" |
| `ParamEyeOpen` | 两眼一起开合的便捷入口（引擎内建，L/R 之外的额外一个） |
| `ParamBaseRot` | **2026-10-13 补**：全身倾斜。标准表只有 `ParamBodyAngleZ`（上身），而"被摸头 / 被拖拽"时要整个人（含腿）一起晃，所以另立一个绑 `root` 组 `rot_deg × 0.5` |
| `ParamStarEye` | **2026-10-16 补**：星星眼总闸（0→1）。一条参数三件事：常态虹膜 `alpha × −1`（淡出）、星形虹膜 `alpha × 1 offset −1`（淡入）、8 颗 ✨ 同样 `×1 offset −1`（放行）。官方没有这个参数，但差分件切换的做法是官方的（[surume1ka](https://surume1ka.com/archives/2207)：新参数 min0/def0/max1，用不透明度 0↔100 切）。另见 [@kawase1234567](https://x.com/kawase1234567/status/1747491216227516567)：きらきら目和ハート目不会同时发动，**应当收进同一个参数**，所以这里是一条总闸而不是每种眼睛一条 |
| `ParamMouthX` | **2026-10-16 补（T44.2）**：嘴左右 −1~1 = 单边嘴角。不是 Live2D 标准表的名字，取自 Animaze《複雑な口角形状の Live2D モデル作成方法》的扩展参数表（[animaze.us](https://www.animaze.us/manual/gettingstarted2djp/extparam2d)），原文口径「口角を『クイッ』と上げるような、左右の位置を調整するパラメータ」「頬も同様に口の動きに合わせて少し上がるように」。**为什么不复用 `ParamMouthForm`**：Form 已经被口型同步占满（visemes 里 I=+1.0 / U=−1.0 / O=−0.7 / N=−0.35），而且引擎口径是口型层覆盖、表情只拿 (1−w) 的余味 —— 挂在 Form 上的微表情一说话就被压掉。**我们的偏差**：官方做法是 mesh 变形器把一侧嘴角拉高，我们只有整件变换，所以用 `rot_deg ±8°` 代替，`dx` 压到 ±1.5px 只做支点错觉（实测扫描 `logs/asset_qa/mouthx_sweep.png`：平移一大就变成「嘴整个滑到一边」的缺陷）。官方 PerfectSync 把 Left/Right Mouth Corner 列在 ★ 最低推荐档（[juku.live2dcs.jp](https://juku.live2dcs.jp/en/course/course-18/)） |
| `ParamAccTailSwing` | **2026-10-16 补（T45.2b）**：猫尾自主摆动 −1~1，由 `idle` 的慢正弦（0.21Hz ≈ 4.8 秒一个来回）驱动，同时绑网格形变器 `tail_s`（S 形鞭动）与根部 `rot_deg ±3.2°`。**我们和官方的实现差异（重要）**：Live2D 社区的标准配方是「把**呼吸**加进尻尾物理演算的**输入**，尻尾就会常にゆらゆら」（[伊糖だねこ](https://note.com/itodaneko/n/n3b5e2ada3f4b)）—— 那在官方引擎成立，因为**官方物理输出的是摆角**。我们的物理输出的是**滞后量** `pos − target`（`src/core/zrig.c:3013`），呼吸只有 0.28Hz、摆锤完全跟得上 ⇒ 差值≈0，**实测只摆 0.3 帧像素**。所以在本引擎「自己动」必须有独立驱动源，物理只负责在它之上叠二次滞后。换成动作通道后实测 **6.2 帧像素 / 11.3 画布像素**，波形是干净正弦 |
| `ParamEarLAngle` `ParamEarRAngle` | **2026-10-16 补（T45.3）**：猫耳角度 −1~1，−1=飞机耳（向后低平）、+1=竖起前倾，绑耳根 `rot_deg ±26°`（锚点 `[0.5,1.0]` 就是耳根，★「あまり**根本を動かしてしまうと猫耳自体が浮いて見えてしまう**」—— 耳根不能平移，只能绕它转）。**为什么是连续参数而不是差分件**：官方/社区做法就是一条「耳揺れ」参数 −30~30，「−30で耳が下がる、30ではピンと張る」（[otimusya24](https://otimusya24.com/nekomimi-lve2d/)）；这点和尾巴相反 —— 尾巴的竖起/炸毛是**形状**变了（炸毛宽 3 倍），耳朵只是**角度**变了。情绪映射走 rig 的 `mood_params`（第三张情绪表）：直立=快乐/警觉、飞机耳=害怕或生气、前倾=好奇。⚠ 旋转正负号是**实测翻过来的**，第一版 happy 摊平 angry 竖起，正好对调 |
| `ParamAccEarL` `ParamAccEarR` | 猫耳挂件开关，0=摘 1=戴。同 `ParamAccTailCat` 的差分件口径 |
| （表）`mood_swing` | **2026-10-16（T45.2f）第四张情绪表**：情绪 → `[频率倍率, 幅度倍率]`，作用在上面四条摆动参数上。引擎 `zrig_apply_mood_swing()`，和 `blink.mood_rate`、`poses[].mood_map`、`mood_params` 并列，口径一致 —— **查不到的情绪不动**。只乘 `amp` 不乘 `bias`（bias 是静态姿态偏置，一起放大会让尾巴整条歪出去）。切换时做**相位补偿** `tshift' = t − (m₀/m₁)(t − tshift)`，否则改频率会当场跳相、t 大的时候等于尾巴瞬移。★ 这张表 2026-10-16 之前是**死表**：只躺在 design/attachments.json 里，生成器不搬、rig 里没有、引擎不认识，「生气快甩」「专注慢大摇」两条词汇从没交付过。靠确定性探针 `tools/probe_swing.c` 发现（11 种情绪峰峰值全是 6.4）。已设闸 `selfcheck_repo.check_no_dead_tables` |
| `ParamAccTailRelaxedSwing` `ParamAccTailUpSwing` `ParamAccTailPuffSwing` `ParamAccTailTuckSwing` | **2026-10-16 补（T45.2c / T45.2f）**：猫尾三种姿态各自的摆动参数，由 `idle` 正弦驱动，同绑各自的网格形变器与根部 `rot_deg`。**一个参数两用**：`bias` 给静态外倾角（竖起 −15.6°、炸毛 −13.8°，不倾就会被外套挡住、像从腋下长出来），`amp` 给摆幅。三组数值按猫行为学分开：放松 0.21Hz/±3.2°（慢而大）、竖起 0.55Hz/±3.2°（兴奋是尖端颤）、炸毛 1.35Hz/±1.3°（僵直发抖不是摇摆）。姿态本身走 `rig.poses` 互斥组 `tail_pose`（官方パーツα方式），四种形状差太远、几何变形做不出来。**2026-10-16 补第四姿态 `tuck`（夹紧·示弱）** 0.16Hz/±1.4°、形变器只给 0.34 倍 —— 恐惧是**冻结**不是慢摆；`bias −0.55` 做静态内收。补它的理由：在此之前 11 种情绪有 6 种全映射到 `relaxed`，sad/shy 和 neutral 长得一模一样。**★ 值域不是 ±1**：按 `mood_swing` 的最大幅度倍率反推撑开（relaxed 取 ±2.25）。摆动基准幅度本来就顶着 ±1，情绪想放大 1.8 倍时会被 clamp 削平 —— 实测症状是"缩小的倍率都对、放大的倍率全变成 1.00"，一半对一半错最难发现 |
| `ParamSkirtSway` | **2026-10-17 补（T45.9）**：裙摆的**自主**摆动。标准表里只有 `ParamBodyAngleX/Y/Z`，没有「布自己在动」这一层。★ 为什么非加不可：裙摆原本**只靠物理输入**（`ParamBodyAngleX`+`Z`），而本引擎物理输出的是**滞后量 pos−target** 不是摆角，待机时身体几乎不动 ⇒ 滞后量≈0 ⇒ 布是死的。实测 idle 60 秒形变峰峰值 **0.0599**、频率 **0.058Hz**（17 秒一个来回）。这正是 Live2D 社区说的「入力が小さいと振り子が 0 に吸着する」。接上自主通道后峰峰值 **1.2779**、0.133Hz。★ **两级形变器**：`skirt_sway_x`（裙身，rows 6~10）+ `skirt_hem_x`（下摆，rows 8~10，幅度约三成），下摆绑定带 `lag 0.11` ⇒ 裙身先走、下摆后到。依据是官方/社区对「幅のある布」的口径：**複数階層のワープデフォーマ、振り子は親→子**（单层变形路径会把形状拧歪）；以及「硬い」的头号成因「揺れが1段しかない」。★ 频率 0.13Hz / 延迟 0.11s，**刻意和尾巴（0.21Hz / 0.17s）错开** —— 教程口径「軽いものほど揺れやすく、早く収まる」，全身用同一组数会让所有东西同拍子摆 |
| （表）`ambient` | **2026-10-17（T45.9）本引擎扩展**：rig 顶层的**环境摆动通道**，不属于任何动作，按**绝对时刻**求值。官方没有对应概念 —— Live2D 的待机晃动要么是 motion 曲线（属于某个 motion），要么是物理。★ 为什么必须提升出来：这些通道原本写在 `idle.channels` 里，而待机动作有四个会轮换，实测 `breath` 时裙摆幅度 **0.0000**（布料整个冻住）；而且动作通道按「动作内经过时间」求值，一换动作就从 0 重来 ⇒ **相位跳回原点**。改成 ambient 之后四个待机动作下摆动连续，换 7 次动作单帧最大跳变 0.0335°。引擎侧复用 `zaction` 壳 + `load_channels()`（和动作共用同一套通道语义）。闸：`selfcheck_repo.check_ambient_sway` |
| （表）`tail_flick` | **2026-10-17（T45.2g）第五张情绪表**：情绪 → `[间隔下限秒, 间隔上限秒, 幅度, 单次时长秒]`。前四张表改的是「摆动长什么样」，这张改的是「它**多久自己动一次、动多狠**」。引擎 `zrig_apply_mood_flick()` + `accumulate_tail_flick()`，口径同前四张 —— **查不到的情绪不动**。★ 官方没有对应概念：Live2D 的待机晃动一律由 motion 曲线或物理驱动，都是**周期**的；自发事件只有「自动眨眼」一处（`CubismEyeBlink` 的随机间隔）。我们把眨眼那套搬给了尾巴，依据是行为学而不是引擎惯例 —— de Mouzon 2023 实测猫被忽视时平均摆尾 13.98 秒、被搭理时 0.39 秒，摆尾是**阵发事件**不是匀速节拍（见 REFERENCE_NOTES 第三十四批）。抽动波形是急出缓回的 `exp(−4.2u)·sin(1.6πu)·(1−u⁴)`，峰值归一到 1.0；每起一次再随机方向、力度 ±35%、时长 ±25% |
| （波形）`drift` | **2026-10-17（T45.2g）本引擎扩展，官方没有**：三条**不可通约**频率的正弦叠加（比例 1 : 1/φ : φ，φ=黄金比），两两之比都是无理数 ⇒ 准周期、**永不精确重复**。权重 0.62/0.26/0.12 按和归一 ⇒ `|输出| ≤ amp`，不会撞值域被 clamp。为什么要它：单条 `sine` 的尾巴实测 60 秒 12 个峰、幅度标准差 **0.000015°**、变异系数 0.0005% —— 是节拍器。换 `drift` 后变异系数 **38.4%**。动画教科书管单条正弦叫「stiff pendulum swing」，要靠「C 形曲线↔S 形曲线反复切换」才有柔软感 |
| （绑定）`bind.lag` | **2026-10-17（T45.2g）本引擎扩展**：参数绑定可以读**lag 秒之前**的参数值。实现的是动画的 wave principle —— 尾巴分段、每段比上一段延迟 2~3 帧，相位差 `φ = 2πfΔt`。★ 为什么做在**时域**而不是写一个相位偏移：相位偏移只对正弦成立，而自发抽动是非周期脉冲；时域延迟一个字段同时管住慢摆和抽动。Live2D 对应的是**多段物理摆链**各自的 Delay/Acceleration，我们的物理输出是滞后量而不是摆角（见本表 `ParamAccTailSwing` 行），所以慢输入推不动，必须另开这条。实测根→梢互相关峰值在 0.167 秒（设定 0.17）。闸：`selfcheck_repo.check_swing_headroom` 要求带形变器的摆动件必须有 lag |
| `ParamAccTailCat` | **2026-10-16 补（T45.2）**：猫尾挂件开关，0=摘掉 1=戴上。官方标准表里没有挂件概念 —— Live2D 的做法是 `pose3.json` 的**差分组**（一组部件同一时刻只露一个），我们这里是单件开关，走的是同一套差分件口径（[surume1ka](https://surume1ka.com/archives/2207)：新参数 min0/def0/max1，用不透明度 0↔100 切），所以**绑 `alpha` 而不是把部件从 rig 里删掉**。尾巴本体不靠这个参数动，动的是物理链 `tail_x → tail_tip（驱动网格形变器 tail_s）→ tail_y`；曲线用 `BEND_TIP`，依据是 `src/core/zimg.h:93` 原文「顶边固定，越往下位移越大 —— 后发、裙摆、**尾巴**这类吊在上面的部件」。实测摆动 11.9 帧像素 / 21.6 画布像素，带阻尼（~0.7s 稳定）|
| `ParamSparkle1` `ParamSparkle2` `ParamSparkle3` `ParamSparkle4` `ParamSparkle5` `ParamSparkle6` `ParamSparkle7` `ParamSparkle8` | **2026-10-16 补**：第 N 颗 ✨ 的生命周期。一颗一个参数，0→1 走完 = 放大出现→缩小消失（`alpha ×1 offset −1` 与 `sx`/`sy ×0.55 offset −0.55` 合在同一条参数上）。**不许八颗共用一条** —— [カワナミ](https://kw-nmnm.hatenablog.com/entry/2019/12/18/000000)（Live2D 讲师）的做法是 28 颗 ✨ 配 28 个参数，共用会让它们整齐划一地闪，一眼假。素材只有一张 `fx_sparkle.png`，大中小靠 `scale` 复制（官方讲座「キラキラ1・2・3」要求三种大小混用） |

> 闸门：`tools/selfcheck_repo.py` 的「自定义参数都已登记」会把**没写进这张表**的新参数判红。
> 这就是防"命名慢慢跑偏"的那道锁。


### ⚠ 左右的口径（接外部驱动前必须先对这一条）

我们的 `eye_l_*` = **画面左侧**那只眼（= 角色自己的右眼），`ParamEyeLOpen` 关的就是它
（证据：`logs/asset_qa/_l2d_param_sheet.jpg` 第 1 格，画面左眼闭、右眼睁）。
整条素材链（`make_eye_parts.py` / `anchors.json` / 层号）都按"画面左右"命名，统一且自洽。

Live2D 社区里这个口径两种都有（按角色视角 vs 按画面），**不存在绝对标准答案**，
但接任何外部工具（面捕、VTube Studio、现成 motion）之前必须先确认对方的口径：
对不上就是整张脸左右反 —— 这类错一旦混进动作文件就很难查。
我们的选择写在这里备查，要换口径只需在 `make_rig.py` 里把 `eye_side` 取反，素材不用动。

---

### 口型音素（あいうえお）：为什么不是五个新参数

**官方标准参数表里没有 `ParamMouthA/I/U/E/O`。** 查证结论（2026-10-13）：

| 来源 | 结论 |
| --- | --- |
| Live2D 官方《标准参数列表》 | 嘴只有两项：`ParamMouthOpenY` 0..1、`ParamMouthForm` -1..1（**+ 笑 / − 怒**） |
| Live2D 教程（母音認識方式） | あいうえお = 给「开合 × 嘴形」事先做好几组 keyform，按识别到的母音切换；`ParamMouthForm` 本身**不是母音参数** |
| Animaze（FaceRig 后继）的 viseme→Live2D 映射表 | 每个 viseme 也都落到 `ParamMouthOpenY` + `ParamMouthForm` 两个标准参数上 |
| airi `packages/model-driver-lipsync` | 每帧只取**一个赢家母音 + 当前响度**，再加 attack/release 平滑，而不是五个口型一起加权 |

所以我们做的是一张**音素 → 标准参数取值**的表（rig.json 顶层 `visemes`），
而不是自造五个参数。换角色换表，引擎不用改。

| 音素 | 读音 | `ParamMouthOpenY` | `ParamMouthForm` | 形状 |
| --- | --- | --- | --- | --- |
| SIL | 静默 | 0.00 | 0.00 | 闭嘴 |
| A | あ / a | 1.00 | 0.00 | 张到最大，嘴形中性 |
| I | い / i | 0.22 | +1.00 | 几乎不张，横向咧到最宽 |
| U | う / u | 0.30 | −1.00 | 小口撅圆 |
| E | え / e | 0.58 | +0.55 | 半开偏宽 |
| O | お / o | 0.88 | −0.70 | 大口撅圆 |
| N | ん / m・n | 0.06 | −0.35 | 基本闭上，嘴角收住 |

驱动方式：`zrig_viseme_set(r, "I", 0.8)` —— **音素给嘴形，权重给音量**；
引擎按 attack 50/s、release 30/s 做指数平滑（收口比张口慢，否则像开关），
收干净后自动把嘴交还给动作（`mouth_mute` 归 0）。
预览端点 `/api/viseme?v=A&w=1`，测试台有一排按钮和「念一串 a-i-u-e-o」。

证据：`logs/asset_qa/_viseme_sheet.jpg`（冻结时钟 + 7× 放大的七张嘴）；
闸门：`test_viseme()` 要求 A/I/U/E/O **两两像素差 > 25px**，且 い 必须比 う 宽。

### 表情和口型抢同一个参数时谁说了算（执行序）

笑着说「う」：笑脸要把 `ParamMouthForm` 推向 +（横咧），「う」要把它推向 −（撅圆）。
两层写同一个参数，**谁后跑谁说了算**。官方的答案写在
`CubismWebFramework/src/motion/icubismupdater.ts` 的执行序常量里
（`CubismUpdateScheduler` 按这个号排序，不是按 `addUpdatableList` 的调用顺序）：

| 序号 | 官方更新器 | 小寻对应 | 实现 |
| --- | --- | --- | --- |
| 200 | EyeBlink | 自动眨眼状态机 | `zrig_blink_*`（五态） |
| 300 | Expression | 表情层（两条轨 + 淡入淡出） | `expr_apply()` |
| 400 | Drag（视线跟随） | `/api/gaze` + 跟随平滑 | `zrig_gaze_*` |
| 500 | Breath | 呼吸 | `ParamBreath` 通道 |
| 600 | Physics | 物理摆链（多段） | `zrig_physics_*` |
| **700** | **LipSync** | **口型音素层** | `param_effective()` 里的音素段 |
| 800 | Pose | 互斥组淡化 | `zrig_pose_*` |

所以我们的一帧是：**动作（含 fade）→ Pose → 参数 + 表情 → 口型 → 跟随 → 物理**，
口型排在表情之后 —— 这一条有单测守着（`test_expr_viseme_order()`）。

**一处有意偏差，必须登记：官方 LipSync 是纯加算，我们是「按用力程度接管 + 松手时平滑还嘴」。**

| | 官方 | 小寻 | 为什么 |
| --- | --- | --- | --- |
| 写法 | `addParameterValueById(id, v, 0.8)`（`lappmodel.ts`） | `v = viseme + (表情后的值 − 默认值) × (1 − w)` | 官方的 LipSync 组**只含 `ParamMouthOpenY`**（单调开合，加算不会打架）；我们把 `ParamMouthForm` 也纳入音素层（五张嘴必须有嘴形），纯加算会让「笑(+0.7) + う(−1.0)」抵消成 −0.3 的中性嘴，口型白做 |
| 接管权重 | 固定 0.8 | `w = viseme_weight × viseme_activity(本帧)`；`viseme_weight` 默认 **1.0** | 0.8 是官方给"只驱动开合"定的；我们还驱动嘴形，残留 20% 的笑在满口型上肉眼可见 |
| 力度调制 | 无（恒定） | `viseme_activity = max_k \|vis_cur_k − 默认\| ÷ 该参数到边界的距离`，夹 0..1：静音 SIL = 0、小声 = 按比例、满力「あ」= 1 | **2026-10-13 修的真 bug**：恒定权重下笑着说一整句，`ParamMouthForm` 全程被按在 0.14，停顿时也回不到笑、张大嘴时笑嘴角也不让位，看着就是"张嘴了微笑还在" |
| 松口 | 无（停了就不写） | 两档 release：音素之间 `ZRIG_VIS_RELEASE` = 30/s，**整句说完 `ZRIG_VIS_RELEASE_OFF` = 8/s** | 整句收尾比音素切换慢一档，嘴形"叹"回表情；同一档速度下收尾仍会被看成一次抽动 |
| 清空语义 | — | `zrig_viseme_clear()` = 平滑松口（只把 `vis_weight` 归零，形状一路收回默认，收干净了才真正释放）；`zrig_viseme_reset()` = 立刻清零（换角色 / 换形态 / 测试取基准） | 原来 `clear()` 是硬切，说完话一帧之内从说话嘴形弹回表情 = 嘴角抽一下 |
| 结果 | 嘴形被表情拖走 | 满力说「う」：笑和不笑都是 **−1.00**（口型独占）；小声说「う」（力度 0.25）：**+0.44**（笑意透出来）；停顿：**+0.70**（表情全额拿回） | 力度决定谁说了算 |

实测（`/api/params.json` 的 `value` / `expr` / `effective` 三列，冻结时钟）：

| 状态 | `ParamMouthForm` 参数值 | 过表情后 | 最终 | `ParamMouthOpenY` 最终 |
| --- | --- | --- | --- | --- |
| 中性 | 0.00 | 0.00 | 0.00 | 0.00 |
| 只笑 | 0.00 | +0.70 | **+0.70** | 0.00 |
| 只说 う（满力） | 0.00 | 0.00 | **−1.00** | 0.30 |
| 笑着说 う（满力） | 0.00 | +0.70 | **−1.00** | 0.30 |
| 笑着说 う（力度 0.25） | 0.00 | +0.70 | **+0.44** | 0.08 |

笑着说一整句（`call_end_1_base0`，150ms 采样，实机）：

| t(s) | 0.00 | 0.15 | 0.46 | 0.76 | 1.22 | 1.52 | 1.82 | 1.97+ |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 音素 | SIL | A | I | A | A | SIL | SIL | — |
| `OpenY` | 0.00 | 0.49 | 0.16 | 0.82 | 0.24 | 0.08 | 0.00 | 0.00 |
| `Form` | **0.70** | 0.36 | **0.91** | **0.15** | 0.53 | 0.64 | **0.70** | 0.70 |

（修之前这一行是「Form 全程 0.14，到 t=2.00 一帧跳回 0.70」。）

证据图 `logs/asset_qa/_expr_viseme_sheet.jpg`（四张嘴的特写 + 整句的两条曲线）；
闸门：`test_expr_viseme_order()`（满力时笑/不笑的 Form 必须相等、小声时必须透出笑、
满力「あ」不许带嘴角、松口 40 帧单帧跳变 < 0.12 且末值回到 +0.70）、
`test_expression_blend()`（Add / Multiply / Overwrite 三种混合的算术）、
`api_smoke.py` 的 4 项、`selfcheck_repo.py` 的 13 项静态闸。
负控做过五次：`viseme_weight=0` → 判红、`=1.0` 恒定 → 判红、
把 `EXPR_MUL` 退化成加算 → 判红、`w` 退回恒定 `vis_mix`（去掉力度调制）→ 判红 2 项、
`viseme_clear` 退回硬切 → 判红（单帧跳变 0.700）。

**表情三种 Blend 的算术**（照 `CubismExpressionMotion::calculateExpressionParameters`，
也和 BongoCat 的 `evaluate_expression_parameter` 一致）：三个累加器
`overwrite = 基准值`、`additive = 0`、`multiply = 1`，逐层按淡入权重 `w` 线性混，
最后 `(overwrite + additive) × multiply`。我们的两条轨（当前表情 `w`、上一个表情 `1−w`）
就是按这个口径算的。

## 二、文件结构对照（model3 / motion3 / exp3 / physics3 / pose3 …）

| Live2D 文件 | 作用 | 小寻怎么对应 | 判定 |
| --- | --- | --- | --- |
| `.moc3` + 纹理图集 | 模型本体 | 我们是**一张张 PNG + rig.json**（没有图集打包） | 等价。图集是 GPU 优化，桌宠规模用不上 |
| `.model3.json` `FileReferences` | 把各文件串起来 | `rig.json` 一个文件全包 | 等价 |
| `.model3.json` `Groups` | `EyeBlink` / `LipSync` 两组 | **本轮补** `rig.json` 的 `param_groups` | ✅ 而且**不是摆设**：自动眨眼只眨组里列的眼，口型只写组里声明的参数（改组名会改行为，有单测守着） |
| `.model3.json` `HitAreas` | `Head` / `Body` 点击区 | `regions`（head / body / feet 三块，各自带动作与光标） | 等价且更强（我们多一层"点了触发哪个动作"） |
| `.motion3.json` | 关键帧动作曲线，目标是**参数** | `actions[].channels[].target = "ParamXxx"`，**2026-10-13 起 18 个动作全部如此** | ✅ 协议打通（见下面「动作通道」）。差异：我们是 `linear/smooth/step`，官方是贝塞尔；可后加，属于纯增量 |
| `.exp3.json` | 表情（参数偏移，Add/Multiply/Overwrite） | `expressions[].params[].mode = add / set(=overwrite) / multiply` | ✅ 三种混合都有，求值照 `CubismExpressionMotion` 的三累加器 |
| `.physics3.json` | 摆动：**参数 → 参数**，带 Vertices 摆链 | `physics[]`：**部件/形变器 → 位移**，driver 可串另一条 physics（多段摆链） | 功能等价，**语义不同**（见下） |
| `.pose3.json` | 互斥部件组 + 淡入淡出 | `poses[]`（眼高光形状差分在用） | 等价 |
| `.cdi3.json` | 编辑器显示信息（参数中文名/分组） | 参数的 `label` 字段 + `/api/params.json` | 等价（测试台的滑条就是它长出来的） |
| `.userdata3.json` | 自定义元数据 | 暂无需求 | ➖ |

### 动作通道：只能打在参数上（2026-10-13 完成迁移）

官方 `motion3.json` 里每条曲线的 `Target` **只有三种取值**
（`CubismWebFramework/src/motion/cubismmotion.ts` 第 38~40 行的三个常量）：

| Target | 含义 | 我们的对应 |
| --- | --- | --- |
| `Parameter` | 打在参数上 | `{"target": "ParamXxx", ...}` ← 现在 160 条通道全是这种 |
| `PartOpacity` | 打在部件不透明度上 | `{"target": "<部件 id>", "param": "alpha"}`（仍然允许） |
| `Model` | 只认 `Opacity` / `EyeBlink` / `LipSync` 三个特殊 id | 我们用 `dim` / `blink_hold` / `mouth_mute` 表达 |

**没有"直接写部件位移/旋转/缩放"这一类**。我们以前有（18 个动作共 197 条），
2026-10-13 全部迁走：

- 迁法不是重写动作 —— 那些像素/角度是美术调出来的成果。而是**按参数的 bind 系数反算**：
  `参数振幅 = 几何振幅 ÷ bind scale`。换算表在 `tools/make_rig.py` 的 `GEO2PARAM`，
  **出现没登记的几何目标就直接报错**（新动作请直接写参数，换算表只是守门人）。
- 顺带清掉两类脏东西：① 左右对称的两条通道（侧发/两肩/两眼球）换算后是同一个参数，合成一条；
  ② idle/think 里"整只眼在脸上平移"那 24 条逐件通道直接删 —— 眼部件全在 head 组里，
  组位移本来就带着它们走，再逐件写一遍等于动两次，而且新加的零件（比如笑眼件）
  不会出现在那张手写清单里，眨眼时就会掉队。
- 新增 `bias` 字段（直流偏置）：官方 `CubismBreath` 是 `offset + peak*sin`，
  `ParamBreath` 值域 0..1，纯正弦会被下限 clamp 掉半个周期。breath 动作写
  `{"wave":"sine","amp":0.5,"bias":0.5}`。
- 为此调整了几个 bind 系数，口径统一成"**参数满格 = 这个动作能做到的最大幅度**"：
  `ParamBrowL/RY` −3→−5、`ParamBaseX` 1→2、`ParamBaseY` −1→−4、`ParamArmL/RB` ±5→±10、
  `gaze.max_offset` [3,2]→[4,2.5]、`look.groups.head.dy` 3→10
  （跟随和动作写的是同一个参数，幅度体系也必须是同一套 —— 官方就是这么做的）。
- **回归证据**：18 个动作 × 7 个时刻逐像素对照，质心位移最大 5.3px（breath 的呼吸起伏）、
  横向最大 5.0px（stroke/focus 的 `head.dx → ParamAngleX` 连带了头部旋转，Live2D 语义，更自然），
  其余 ≤2.2px。证据图 `logs/asset_qa/_param_channel_ab.jpg`。
- **闸门**：`zrig_action_geom_channels()` 必须返回 0；单测还拿一个**故意写几何通道的合成 rig**
  反向验证这个计数器不是永远返回 0。

### physics 的语义差异（唯一一处"做法不同"，已评估可后补）

- Live2D：`Input(参数) → 摆链顶点 → Output(参数)`，物理的产物是**参数值**，再由美术自己绑的形变器放大。
- 我们：`driver(组/另一条 physics) → 弹簧 → 部件位移 / 形变器 amount`。

对最终画面是等价的（都能做"发根先甩、发梢慢半拍"），差别在**可移植性**：
从 Cubism 搬一份 `.physics3.json` 过来需要一层转换。
**风险评级：低** —— 这是引擎内部管线，改它不需要重做任何素材，也不影响参数命名。
真要接，加一条 `"output": {"param": "ParamHairFront"}` 即可，属于纯增量。

---

### 动作的淡入淡出：曲线和时长都按官方来（2026-10-13）

| | 官方（`CubismMotion` / `CubismMath`） | 我们（`src/core/zrig.c` `compute_group_transforms`） |
|---|---|---|
| 缓动曲线 | `getEasingSine(v) = 0.5 − 0.5·cos(vπ)`，两端钳 0/1 | `z_ease_sine()`，同式同钳位 |
| 淡入 | `getEasingSine((now − fadeInStart) / FadeInTime)` | 动作的 `fade`（默认 0.22s） |
| 淡出 | `getEasingSine((endTime − now) / FadeOutTime)` | 动作的 `fade_out`（默认 0.2s） |
| 循环动作 | `endTime < 0` ⇒ 不淡出 | `loop` 时 `duration` 传 −1，淡出乘法被 `tot > 0.0` 挡掉 |
| 权重合成 | 每个 motion 各算 `fadeIn × fadeOut`，按队列逐个 `v = src + (val−src)·w` 覆盖 | 我们是**累加**模型，所以新旧两个动作仍保持 `w` / `1−w` 互补，再各乘自己的 `fade_out` |

**最后一行是刻意的偏差，记在这里**：官方是"插值覆盖"，权重不必互补；
我们是"把各通道的值加到参数上"，互补权重才不会超量。等将来真上 motion queue
（多动作并存、优先级抢占）再换插值模型，那是另一件事，不在本轮。

**淡出属于动作自己**，不属于"接替它的那个动作"——所以正在淡出的旧动作也要乘它自己的
`fade_out`。三道静态闸（`tools/selfcheck_repo.py` ⑭ 组）盯着调用点，
防的是"函数还在、调用处偷偷换回 smoothstep"这种单测抓不到的退化。

---

### physics 的输入输出：输入已经参数化，输出还没有（2026-10-13）

官方 `.physics3.json` 的一组摆链长这样：

```
Input :  [{Source: ParamBodyAngleX, Type: X,     Weight: 100},
          {Source: ParamBodyAngleZ, Type: Angle, Weight: 100}]
Output:  [{Destination: ParamSkirt, Type: Angle, Scale: 1.434, Weight: 100}]
Vertices: v0(0,0) mobility 1   delay 1   accel 1   radius 0
          v1(0,10) mobility 0.9 delay 0.6 accel 1.5 radius 10
```

**输入**：2026-10-13 起我们也支持参数输入（`physics[].input` 数组，
对应官方的 `Input`），裙摆两条就是这么接的。原来只能"读某个驱动组的位移"，
碰上 `ParamBodyAngleX → seg_torso.bend_x` 这种只改形状不改组矩阵的参数就读不到。
组驱动的写法保留，两种可以共存（头发仍走组驱动）。

**输出**：我们仍然直接写部件通道或形变器 `amount`，官方是写回一个参数
（`ParamSkirt`）再由美术把那个参数绑到形变器上。差别是**多一层间接**：
官方那层让动作/表情也能手 K 裙摆。这项列为 **GAPS G44**，纯增量，不影响现有素材。

**顶点参数的对应**：官方用 `mobility / delay / acceleration / radius` 描述摆，
我们用 `stiffness / damping / ratio / max`。两者都能表达"摆长决定固有频率、
阻尼决定晃几下"，换算不是一一对应，但有个好用的口径——
**阻尼比 = damping / (2·√stiffness)**（Inochi2D 的 `critDamp = 2·sqrt(g/L)` 同一回事）。
现在的取值：头发 0.40（晃得欢）、裙摆横摆 0.66、裙摆纵摆 0.78（布料更钝）。

---

## 三、美术/素材规范对照

| 规范 | 官方说法 | 小寻 | 闸门 |
| --- | --- | --- | --- |
| 拆件粒度 | 前发/后发/侧发、轮廓、眉、眼（睫毛/眼睑/瞳/眼白）、口（上下唇/齿/口内）、上半身/左右臂/左右腿 | 38 件：眼 5×2、嘴 3、眉 2+2 透け、发 5、臂 6、腿 2、躯干/头… | `check_assets` 358 项 |
| 塗り足し（bleed） | 切件边缘必须往外补色，否则转动露底 | 全部切口都有；**手腕这种要往遮盖件里缩**（`erode(掩码,4)`） | 关节不露底闸（肩/肘/腕/髋/裙摆） |
| 被遮挡区域 | 必须画出来（不是透明） | AI 重绘 6 张（袖下躯干、无刘海额头、闭眼脸、张嘴脸、无侧发脸、无眉脸） | 「袖下躯干有料」「脸上无残留睁眼」 |
| 抗锯齿 / 软边 | 切件必须保留软边，硬阈值会有锯齿 | 软掩码只做内缘 + 2px 羽化 | 边缘质量闸（毛边/切割感） |
| 预乘 alpha | 设反会"发黑/发光" | 全程直通 alpha（非预乘），渲染端一致 | 合成差异闸（静止拼回 0 像素差） |
| 层序 | 固定层序，遮罩不必相邻 | 60~246 连续编号；A9 之后遮罩当场渲染 | 「层号不重复」 |
| 锚点 | 关节处，不能放图片角 | 肩/肘/腕/髋各自实测 | 「改 anchor 必须同步改 pos」已成教训条目 |

---

## 四、风险分级：哪些现在不做就补不回来

| 风险 | 项 | 状态 |
| --- | --- | --- |
| 🔴 **补不回来**（会污染全部动作/表情/外部接口） | 参数命名空间与语义（左右眼拆分、`ParamCheek` 正名、取值范围对齐官方） | **本轮已做**，并用 `selfcheck`（静态）+ `test_core`（运行时）双闸焊死 |
| 🔴 **补不回来** | 素材的拆件结构（挡住的地方必须有画、关节两侧要塗り足し） | 已做：眼/嘴/眉/发/臂/腕/腿全部拆到位 |
| ~~🟠 代价大~~ ✅ | 动作改成"写参数"而不是"写部件通道" | **2026-10-13 已完成**：18 个动作 197 条几何通道 → 160 条参数通道，`zrig_action_geom_channels()` 恒为 0（单测 + selfcheck 双闸）。见下面「动作通道」一节 |
| 🟢 随时能补 | physics 的参数级 I/O、motion3 贝塞尔、cdi3 导出（~~exp3 multiply~~ 2026-10-13 已补） | 纯增量，不动素材 |
| ~~🟢 随时能补~~ ✅ | ~~笑眼~~ / ~~眉形~~ / ~~瞳孔形状~~ / ~~I·U·E·O 口型~~ | **全部做完**。眉形 2026-10-13 清掉，形变器 `brow_l_form`/`brow_r_form` 在 `/api/info.json` 里能读到当前量 |

---

## 五、这份表由谁守着（不是写完就过期的文档）

1. `tools/selfcheck_repo.py` → `check_live2d()`：
   参数命名、取值范围、`param_groups`、眼部件 `eye_side`、**以及"每个参数都要在本文件里出现"**。
   新加一个参数却忘了写进这张表 → 直接判红。
2. `tests/test_core.c` → `test_live2d_standard()`：
   把 36 个标准参数逐个推到极值**渲染对比像素**，一个像素都不动的就是死参数（负控验证过：
   把 `ParamShoulderY` 的 binds 删空 → 红）。外加"闭左眼时右眼必须 0 像素变化"。
3. `tests/test_core.c` → `test_action_drives_param()`：动作通道写参数这条路不能回退。

> 写这三道闸的时候自己踩了两个坑，记下来免得重犯：
> ① 拿两个**不同时刻**的帧相减，待机动作和呼吸的漂移就有十几像素，足以把"死参数"盖过去 →
> 必须用同一个时间戳再 tick 一次（dt=0，等价 `/api/pause`）。
> ② dt=0 时弹簧不走，但物理输出 `pos − target` 会随驱动立刻变 →
> **上一个参数留下的摆动偏移会污染全局基准帧**，所以每个参数都要现拍一张基准。

## 实测回归（2026-10-14）

合规表说"实现了"，不等于"外面点得到、点了真有反应"。这次拿真服务逐项打了一遍：

**像素级**（`frame.png?s=100` 前后比，冻结时钟噪声 = 0 像素）：

| 组 | 项数 | 结果 |
|---|---|---|
| 参数（bind 类：歪头/上身/眼/眉/嘴/臂） | 10 | 10 动了（最小 34 px，最大 36802 px） |
| 表情 | 6 | 6 动了 |
| 口型 viseme | 4 | 4 动了 |
| 互斥差分 | 2 | 2 动了 |
| 眨眼 | 1 | 动了 |
| look 类（ParamAngleX/Y、gaze）+ 动作 | 6 | 6 动了（走时钟，需等收敛） |

**接口级**（`tools/api_smoke.py`，已固化成闸）：46 个参数逐个设值回读全部到位；
7 个表情、7 个口型、3 个差分档位、18 个动作（含 info 里不列出的 idle/sleep）全部可驱动。

### 两个踩坑记录（判读方法本身的坑）

1. **冻结时钟下 look 类参数不收敛是设计使然**，不是 bug。`ParamAngleX/Y` 走 look 子系统
   按 `dt` 平滑，冻结时 `pet_now()` 固定 → `dt=0` → 不动。而 bind 类参数走
   `compute_group_transforms`，不依赖 dt，冻结下照常生效。**测这两类要分开。**
2. **不冻结时 idle 呼吸本身就有 17000+ 像素的噪声底**，眼睛/眉毛/口型这些几十到几百像素的
   真实变化会被完全淹没。量噪声底再定判定线，否则会把好的判成坏的（这次就误判了 5 项）。

### 29 项里最后那一项（2026-10-14 当天补完）

- `ParamCheek`（脸红）接线和方向都对（0→27 px 单调递增），但**满值只有 27 像素可见变化**。
  起初判成"素材太淡"，其实是**落点在脸轮廓外**：腮红走 `multiply`，
  而乘算在透明像素上没有任何效果。`seg_head` 在画布 y=300 的实心范围只有 x 345..491
  （脸是上宽下窄的锥形），腮红却摆在 `[311,300]` 64×34 —— 92% 画在空气上。
  按瞳孔位置重新定位后 **27 → 268 像素，最大色差 34 → 167**。详见 GAPS G66。

  至此 29 项实测全部有效。

### 鼠标交互层（2026-10-14 补，对应 Live2D 的 HitTest / Focus）

| 能力 | 官方对应 | 本仓实现 | 实测 |
|---|---|---|---|
| 命中测试 | `HitTest(areaName, x, y)` | `/api/region?x=&y=` → `{region,action,cursor}` | head/body/feet 三区，网格采样 16 点全部命中且不串台 |
| 视线聚焦 | `SetDragging(x,y)` / `focus()` | `/api/hover?x=&y=&in=` | 指到右上角 → `ParamAngleX=25.18`、`ParamEyeBallX=0.84`；`in=0` 后眼球回 0.00 |
| 口型同步 | `LipSync` 音量驱动 | `/api/speak?id=` → 包络走 `zrig_viseme_set` | 电平序列 0.03~0.81 真实波动，峰值帧嘴张开 |

两个和官方不同、但有意为之的地方：

1. **命中测试要求该点是不透明像素**（`zimg_hit_test` 阈值 16），
   所以矩形内的透明角落不响应。好处是透明边角不会乱变光标；
   代价是**矩形中心不一定命中** —— 角色是非凸形状，feet 的矩形中心正好落在两腿之间。
   验收闸因此改成"矩形内网格采样至少命中一次"而不是"中心命中"。

2. **坐标系是引擎帧缓冲**（= 画布 × pet scale = `info.frame_w/h`），
   不是画布坐标，也不是前端图片的 `naturalWidth`（那是帧缓冲 × 画质档 `s%`）。
   详见 LESSONS 67。
