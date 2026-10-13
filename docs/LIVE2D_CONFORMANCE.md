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

**素材层面：部分合格，缺的都是"还没画"，不是"结构错了"。** 缺 笑眼（`ParamEyeLSmile`）、
眉形（`ParamBrowLForm`）、I/U/E/O 音素口型 —— 这三项都要新素材，但**加进来不需要动结构**。

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
| 6 | `ParamEyeLSmile` | 左眼 笑眼 | ⬜ | **要新素材**（弯月形笑眼）。用现有闭眼件假冒＝灰幽灵，不做 |
| 7 | `ParamEyeRSmile` | 右眼 笑眼 | ⬜ | 同上 |
| 8 | `ParamEyeBallX` | 眼球 左右 | ✅ | 内建，驱动 `gaze` 标签部件，被眼眶遮罩裁切 |
| 9 | `ParamEyeBallY` | 眼球 上下 | ✅ | 同上 |
| 10 | `ParamEyeBallForm` | 瞳孔 形状 | ⬜ | 要新素材（猫瞳/竖瞳差分），优先级低 |
| 11 | `ParamBrowLY` | 左眉 上下 | ✅ | `brow_l` `dy × −3` |
| 12 | `ParamBrowRY` | 右眉 上下 | ✅ | `brow_r` `dy × −3` |
| 13 | `ParamBrowLX` | 左眉 左右 | ✅ | **本轮补**：`brow_l` `dx × 4` |
| 14 | `ParamBrowRX` | 右眉 左右 | ✅ | **本轮补**：`brow_r` `dx × 4` |
| 15 | `ParamBrowLAngle` | 左眉 角度 | ✅ | `brow_l` `rot_deg × 7` |
| 16 | `ParamBrowRAngle` | 右眉 角度 | ✅ | `brow_r` `rot_deg × −7` |
| 17 | `ParamBrowLForm` | 左眉 形状 | ⬜ | 眉形变化要么新素材、要么给眉毛铺 FFD 网格。**结构上随时能加**（A5 已有网格形变器） |
| 18 | `ParamBrowRForm` | 右眉 形状 | ⬜ | 同上 |
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

**合计：✅ 34 ／ ⬜ 5（都缺素材） ／ ➖ 4（角色不适用）**

### 我们在标准表之外的扩展（每一个都必须登记在这里）

| 扩展参数 | 为什么标准表里没有 |
| --- | --- |
| `ParamLegL` / `ParamLegR` | 标准表压根没有腿参数。我们做的是"裙下大腿 bend"，顶边钉死 ±20px |
| `ParamHairAhoge` / `ParamHairAhogeS` | 标准只有 Front/Side/Back/Fluffy，呆毛是这个角色的招牌 |
| `ParamHairSideS` | 侧发的 S 形（FFD），和整体摆动分开 |
| `ParamEyeSparkle` | 眼高光强弱（加算图层），用来演"眼里的光灭了" |
| `ParamEyeOpen` | 两眼一起开合的便捷入口（引擎内建，L/R 之外的额外一个） |

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

## 二、文件结构对照（model3 / motion3 / exp3 / physics3 / pose3 …）

| Live2D 文件 | 作用 | 小寻怎么对应 | 判定 |
| --- | --- | --- | --- |
| `.moc3` + 纹理图集 | 模型本体 | 我们是**一张张 PNG + rig.json**（没有图集打包） | 等价。图集是 GPU 优化，桌宠规模用不上 |
| `.model3.json` `FileReferences` | 把各文件串起来 | `rig.json` 一个文件全包 | 等价 |
| `.model3.json` `Groups` | `EyeBlink` / `LipSync` 两组 | **本轮补** `rig.json` 的 `param_groups` | ✅ 而且**不是摆设**：自动眨眼只眨组里列的眼，口型只写组里声明的参数（改组名会改行为，有单测守着） |
| `.model3.json` `HitAreas` | `Head` / `Body` 点击区 | `regions`（head / body / feet 三块，各自带动作与光标） | 等价且更强（我们多一层"点了触发哪个动作"） |
| `.motion3.json` | 关键帧动作曲线，目标是**参数** | `actions[].channels[].keys`，**本轮起 `target` 可以直接写 `ParamXxx`** | ✅ 协议打通。差异：我们是 `linear/smooth/step`，官方是贝塞尔；可后加，属于纯增量 |
| `.exp3.json` | 表情（参数偏移，Add/Multiply/Overwrite） | `expressions[].params[].mode = add / set` | 基本等价（缺 multiply，需要时再加） |
| `.physics3.json` | 摆动：**参数 → 参数**，带 Vertices 摆链 | `physics[]`：**部件/形变器 → 位移**，driver 可串另一条 physics（多段摆链） | 功能等价，**语义不同**（见下） |
| `.pose3.json` | 互斥部件组 + 淡入淡出 | `poses[]`（眼高光形状差分在用） | 等价 |
| `.cdi3.json` | 编辑器显示信息（参数中文名/分组） | 参数的 `label` 字段 + `/api/params.json` | 等价（测试台的滑条就是它长出来的） |
| `.userdata3.json` | 自定义元数据 | 暂无需求 | ➖ |

### physics 的语义差异（唯一一处"做法不同"，已评估可后补）

- Live2D：`Input(参数) → 摆链顶点 → Output(参数)`，物理的产物是**参数值**，再由美术自己绑的形变器放大。
- 我们：`driver(组/另一条 physics) → 弹簧 → 部件位移 / 形变器 amount`。

对最终画面是等价的（都能做"发根先甩、发梢慢半拍"），差别在**可移植性**：
从 Cubism 搬一份 `.physics3.json` 过来需要一层转换。
**风险评级：低** —— 这是引擎内部管线，改它不需要重做任何素材，也不影响参数命名。
真要接，加一条 `"output": {"param": "ParamHairFront"}` 即可，属于纯增量。

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
| 🟠 代价大 | 动作改成"写参数"而不是"写部件通道" | 通道已支持 `target:"ParamXxx"`；现有 18 个动作仍写部件（能跑、可逐个迁移） |
| 🟢 随时能补 | physics 的参数级 I/O、motion3 贝塞尔、exp3 multiply、cdi3 导出 | 纯增量，不动素材 |
| 🟢 随时能补 | 笑眼 / 眉形 / 瞳孔形状 / I·U·E·O 口型 | 画了就能挂，结构已经留好 |

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
