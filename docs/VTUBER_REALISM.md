# 像 Neuro-sama 一样：顺滑度、AI 自主操作、真骨骼进度

> 2026-10-23 第四十九问三连问的落档。用户原话：
> 「1.怎么做到他们那样顺滑有更有真人感 2.怎么像neuro-sama一样让ai自己操作模型
>   3.真骨骼模型我们的进度到哪了」
>
> 本文三章对应三问。**第 1、2 章是外部资料 + 对我们的差距清单**（每条带 URL），
> **第 3 章是仓库实测的量化答复**（数字全部现查 `rig.json` / `src/core/zrig.c`）。

---

## 一、顺滑和"真人感"是怎么来的（第四十九问①）

先说结论：Neuro-sama 那种"活着"的感觉，**不是模型画得好，也不是帧率高**，
是三件事叠出来的 —— ①**层数够多**（同一时刻有十几条互不同步的小运动在跑）、
②**每一层都带随机**（不许出现可预测的周期）、③**层与层之间错时**
（头先动、身体跟、发梢最后到）。官方教程把这三件事讲得很直白。

### 1.1 官方口径：只动脸 = 机器人

Live2D 官方「クオリティアップ」篇（Cubism 公式）
<https://sites.google.com/cybernoids.jp/cubism2/editor/animator/technic/quality-up>

- 只让脸动，角色就"像机器人"；**脸的 XYZ 必须和身体的 XYZ 一起动**。
- 两者**不能同相**：身体要比头**晚一点**起、晚一点停（ずらし）。
- 动作结束不许"戛然而止"，要有**反动（先往回一点）与刹车（减速）**。

> 对我们：`idle` 里 `ParamAngleX/Z` 与 `ParamBodyAngleX/Y` 已经用了不同
> freq（0.075 / 0.13 / 0.06 / 0.24），所以**不同相是有的**，但那是"频率不同"
> 带来的，不是"同一个动作错开时序"。反动与刹车目前只有 `ease:out`，没有 overshoot。

### 1.2 呼吸和眨眼：Sin 波要"每个周期都变一点"

- サムザップ技術ブログ <https://tech.sumzap.co.jp/entry/live2d_case_study>
  呼吸/眨眼用 Sin 波驱动，但**每过一个周期就随机改一次周期与振幅**，
  否则观众几十秒内就会"数"出节拍。
- Bloomeria 参数优化 <https://bloomeria.jp/blog/live2d-parameter-optimization>
  眨眼全程 **0.15~0.25 秒**，且**闭快开慢**（约 60/40），间隔 **2~5 秒随机**；
  `MouthOpenY > 0.5` 时 `MouthForm` 连动 +0.1~0.2，嘴才不像机械开合。

> 对我们（实查 `src/core/zrig.c`）：
> 眨眼 `closing_s 0.10 / closed_s 0.05 / opening_s 0.15` —— **闭快开慢已经是对的**，
> 间隔 `interval_min_s 2.0 ~ interval_max_s 8.0` 用 `zrand_expo` 指数分布抽（@4289），
> 另有独立的 `sacc_rng` 微扫视（@4567）和 `flick_rng` 头发抖动（@3556~3568，
> 含 0.8~1.3 倍时长、0.65~1.35 倍幅度的随机）。**这三处随机已经有了。**
> 缺的是：**呼吸/待机本身的周期与振幅不随机**（`idle` 的 sine 通道 freq 写死）。

### 1.3 待机不能只有一条

- note ryodist <https://note.com/ryodist/n/nd15bac2226d3>
- 真夜中ブログ <https://mayonaka-blog.com/live2d-motion-howto/>
  待机动作要**准备多条、随机播放**；同一个模式重复 **3~4 次**观众就看出来了。

> 对我们：`actions` 里 `idle` **只有一条**，而且是"请求了就一直循环"。
> ⇒ 这是最划算的一项改进（见 1.6 清单 B）。

### 1.4 分层 + 各层周期互错

d-gear <https://d-gear.biz/column/8573>
呼吸 / 眨眼 / 视线 / 口 / 头发 / 体倾**分层制作**，各层**周期互为非整数倍**；
循环动作首尾要接平；全程缓入缓出。

### 1.5 物理：越往末梢越轻、停下要收得住

- shiroikarasu <https://shiroikarasu.net/live2d-physics-settings-guide/>
- saraemi <https://saraemi.com/vtuber/2021/10/30/live2d_buturi/>
  头发 **2~3 段摆锤串联**，越往发梢"越轻"（质量/阻尼递减）；
  配饰比头发**再慢一拍**；动作停下时摆锤要能**收住**，不能一直晃。

> 对我们：`rig.json` 有 **33 条物理摆 + 5 条二阶**（`zphys2`），
> 刘海/侧发/后发/呆毛/尾巴/手滞后都在里面，串联与"末端更轻"已经做了。

### 1.6 我们离"顺滑"还差的五项（按性价比排序）

| # | 差距 | 现状 | 要做成 | 代价 |
|---|------|------|--------|------|
| A | 待机周期固定 | `idle` 各 sine 的 `freq` 写死 | 每个循环末尾按 ±15% 重抽 freq/amp（复用现成的 `zrand_range`） | 小，引擎内 |
| B | 待机只有一条 | 1 条 `idle` | 做 `idle_a/b/c` 三条，播完随机挑下一条（带 fade） | 中，要新动作数据 |
| C | 头体不错时 | 靠频率不同"碰巧"错开 | 身体通道统一加 0.12~0.25s 延迟（官方 ずらし） | 小，通道加 `delay` |
| D | 没有反动/刹车 | 只有 `ease:out` | 给 pulse 通道加 `ease:back`（末端回弹 5~8%） | 小，一个缓动函数 |
| E | 嘴形不连动 | `MouthForm` 独立 | `MouthOpenY>0.5` 时自动 +0.15 | 小 |

> **A/C/D/E 四项都是引擎内的小改动**，B 是内容活。
> 这五项做完，"顺滑"这一问就算交付；在那之前不写"已做到 Neuro 级"这种话。

---

## 二、怎么让 AI 自己操作模型（第四十九问②）

Neuro-sama 这类做法在公开资料里是**成熟且有标准协议**的：模型跑在
VTube Studio 里，AI 侧作为**插件**通过 WebSocket 往模型里灌参数 / 触发快捷键。

### 2.1 VTube Studio 的官方插件协议

<https://github.com/DenchiSoft/VTubeStudio> ／ <https://github.com/DenchiSoft/VTubeStudio/wiki/Plugins>

- 插件连 **WebSocket（默认端口 8001）**，一次性弹窗授权后拿 token。
- 核心三类调用：
  - `HotkeyTriggerRequest` —— 触发模型里做好的动作/表情（≈ 我们的 `/api/action`）
  - `InjectParameterDataRequest` —— 直接写参数值（≈ 我们的 `/api/param`）
  - `ExpressionActivationRequest` —— 开关表情（≈ 我们的 `/api/pose` + 表情）
- 三条硬规矩（照抄过来能少踩坑）：
  1. 自定义参数名 **4~32 字符**，要先 `ParameterCreationRequest` 注册；
  2. `mode:"set"` 同一参数**同时只允许一个插件**写，`mode:"add"` 可以叠加；
     `weight` 0~1 用来和面捕混合，**防止 AI 一写就跳变**；
  3. 注入的值**必须 ≥1 次/秒重发**，否则自动回落到默认值
     —— 这是"AI 控制"与"模型自身待机"能共存的关键机制。

### 2.2 多来源打架怎么办：官方的 6 级优先级

<https://github.com/DenchiSoft/VTubeStudio/wiki/Interaction-between-Animations,-Tracking,-Physics,-etc.>

> P0 默认值 < P1 待机动画 < P2 面捕 < P3 一次性动画 < P4 表情 < P5 物理

高优先级**覆盖**低优先级，但交接一律**淡入淡出**，不许硬切；
表情只能驱动"模型里已经做出来的参数"。

### 2.3 别人家的 LLM 接法（可直接参照的实现）

- `astrbot_plugin_vtube_studio` <https://github.com/menglimi/astrbot_plugin_vtube_studio>
  把 VTS 能力包成 LLM **工具**：`vts_trigger_hotkey` / `vts_set_expression` /
  `vts_inject_parameter` / `vts_move_model`；并规定**每条回复最多带 1 个"自主 L2D 标签"**
  —— 这条很重要，不然模型会在一句话里连甩五个动作。
- `pyvts` <https://github.com/Genteki/pyvts> —— Python 侧的最小实现，适合抄协议。
- VTube Studio MCP server <https://deepwiki.com/hkopenai/vtube-studio-plugin-mcp-server>
  —— 把 40+ 个 VTS 操作封成 MCP 工具给任意 LLM 用。

### 2.4 对我们：接口已经有了，缺的是"仲裁"和"协议"

| 能力 | VTS 的做法 | 我们现在 | 结论 |
|------|-----------|---------|------|
| 触发动作 | `HotkeyTriggerRequest` | `/api/action?id=wave&force=1` | ✅ 等价 |
| 写参数 | `InjectParameterDataRequest` | `/api/param?id=X&v=…` | ✅ 等价 |
| 切表情/姿态 | `ExpressionActivationRequest` | `/api/pose?group=…&id=…` | ✅ 等价 |
| 混合权重 | `weight` 0~1 + `mode:set/add` | ❌ 没有，写了就是硬覆盖 | **缺** |
| 超时回落 | 不重发 1s 后自动回默认 | ❌ `/api/param` 会**粘住** | **缺**（已知坑） |
| 优先级仲裁 | 6 级 + 淡入淡出 | 动作有 `priority`/`fade`，但参数注入不参与 | **半缺** |
| LLM 工具协议 | 插件 SDK / MCP | ❌ 完全没有 | **缺** |

**所以第②问的答复是**：我们的"手"已经长好了（三个 API 齐全、动作 24 条、
表情 9 个），缺的是**手腕上的那层仲裁**和**让 LLM 知道怎么用这只手的协议**。
落地顺序建议：

1. **G54 先通**（网关现在只会"选谁"，还不会真的发请求）——
   没有它，LLM 根本还没连上来，谈"自己操作模型"是空的。见 `docs/PLATFORM_PLAN.md`。
2. `/api/param` 加 `weight` 与 **TTL 自动回落**（照抄 VTS 的 1 秒规则，
   顺手治掉我们"参数会粘住"的老毛病）。
3. 参数注入纳入**优先级 + 淡入淡出**仲裁（照抄 6 级表）。
4. 定义 **LLM 工具集**（`zc_play_action` / `zc_set_expression` / `zc_inject_param`），
   并规定"每条回复最多 1 个自主动作标签"。

---

## 三、"真骨骼模型"我们到哪了（第四十九问③）

**量化答复（2026-10-23 现查 `characters/xiaoxun/forms/teen/rig.json`）：**

| 项目 | 数量 | 说明 |
|------|------|------|
| 部件 | **100** | 全部来自原画切件，无程序化绘制件 |
| 骨骼组 | **13** | 最深链 **4 级**：`root → chest → arm_r → forearm_r → hand_r` |
| 参数 | **78** | 臂/手 17、发/尾/饰 15、眼 11、头体角 6、口型 3、腿脚 2、其它 24 |
| 形变器 | **25** | 网格形变（袖口收窄、前臂加长、肘折痕等），引擎上限 32 |
| 动作 | **24** | `idle/wave/wave_both/nod/think/sleep/heart_hands/…` |
| 物理摆 | **33 条 + 5 条二阶** | 刘海/侧发/后发/呆毛/尾巴/手滞后/躯干跟随 |
| 表情 | **9** | |
| 互斥姿态组 | **4** | 发型 / 兜帽 / 尾巴 / 眼高光 |
| 命中区域 | **3** | 头/身/尾，供点击交互 |
| 物理步频 | **60 Hz** | `ZRIG_PHYS_FPS`，与官方 Calculate FPS 默认值一致 |

**对照"真骨骼"的完成度：**

- ✅ **有真骨骼层级**：父子组 + 枢轴，旋转在父组局部系里累乘（`group_matrix()`），
  这就是 Live2D 的 Deformer/ArtMesh 树那套。
- ✅ **有网格形变器**：25 个，顶点上限 289/个，可与骨骼旋转叠加。
- ✅ **有物理**：摆锤串联 + 二阶，60Hz 固定步长。
- ✅ **有参数化驱动与动作混合**：`priority` + `fade_in/fade_out` + 交叉淡化 `xfades`。
- ⚠️ **半缺：蒙皮（skinning）**。我们是"切件刚体 + 网格形变补缝"，
  不是顶点权重蒙皮；关节处靠**正圆关节件 + 塗り足し**遮掩（官方 2D 做法也是这个），
  但做新动作时要人工补件，不像骨骼蒙皮那样自动。
- ❌ **缺：IK**。现在摆姿势是**正向解算**（给角度算落点）。
  第四十八问那次"手不许动、只改前臂长度"，我是**手算三角形**反推上臂角度的
  —— 这件事本来应该由 IK 做。有了 IK，"把手放到脸颊边"就是一句话的事。
- ❌ **缺：曲面/弯曲形变器链**（Live2D 的 Rotation Deformer 嵌套 Warp Deformer），
  我们的形变器是平铺的，不能嵌套。
- ❌ **缺：参数自动生成的中间形（4 点插值以上）**，现在多数是线性或手写关键点。

**一句话**：骨骼树、形变器、物理、动作混合这四样**是真的、能跑、有闸门守着**；
**IK 和蒙皮是真缺口**，而 IK 正是下一个该补的 —— 它直接决定"摆一个新姿势"
要花十分钟还是花一整轮。

---

## 四、动起来要自然：关节折叠与头发动态（第五十问）

### 4.1 为什么挥手"有机械感"——两条可量化的病根

**病根一：单脉冲 + `ease:out` 做大角度关节旋转。**
`ease:out` 是前重曲线，0.2s 就走完一半行程。实拍
`logs/asset_qa/q50_wave_elbow_before.png`（6 格 3×）：f12（0.20s）前臂已经转过
49%，**整根小臂横着伸到画面右侧、手在最远端** —— 眼睛读到的就是"一根杆扫过
一个直角"。业界口径完全一致：

- 官方クオリティアップ：动作要有**反動（先往反方向一点）**和**刹车（过冲后回落）**，
  各部位**错开时序（ずらし）**，不能同时起同时停。
- <https://note.com/candyyamada/n/na004e9fdd742>：ぎこちない的根因通常是
  **曲线太直线**，变化剧烈处要加密关键帧、强弱不等间隔。
- <https://miracle-usausa-nurse.com/paint/499/>：挥手时
  **手首は肘より少し遅らせる**（のこし／後追い，动画 12 原则）。
- <https://note.com/marunaru82/n/n03aea05f41d0>：备一个
  **前腕を潰す伸縮パラメータ**，甩的过程中把前臂缩短，
  「軌道が小さいほど滑らかに上がって見える」。

**我们的改法（已实装，`tools/make_rig.py` 的 `wave` / `wave_both`）：**

| 通道 | 起步 | 曲线要点 |
|---|---|---|
| 肩 `arm_r.rot_deg` | 0.00s | 反動 +1.4° → 过冲 −7.8° → 落 −6.89° |
| 肘 `forearm_r.rot_deg` | **+0.10s** | 过冲 −141° → 回弹 −134.12°（刹车） |
| 前臂伸缩 `ParamForeLongR` | 0.14s | 甩程中**缩到 −1.0（−26px）**，到位后伸到 +1.05 |
| 同侧抬肩 `ParamShoulderRY` | **+0.06s** | 过冲 9.3 → 落 8.67 |
| 腕 `hand_r.rot_deg` | **+0.18s** | 鞭梢最末节，过冲 −19° → 落 −15° |

四条通道全部由 `wave:"pulse"` 改成 `interp:"smooth"` + `keys`（引擎
`zrig.c::eval_channel_keys` 原生支持）。`wave_both` 同套曲线镜像到左臂，
并**整体晚 0.05s** —— 两只手严丝合缝同相本身就是机械感的来源。

### 4.2 "折叠痕迹"＝折肘时两根管子之间漏背景

REF-FIRST：把唯一姿势参考 `characters/xiaoxun/design/pose_ref/wave_up.png`
的右臂放大 3×（`logs/asset_qa/q50_ref_arm.png`）——
**折起来的袖子是一整块连续的布**，两根管子之间没有任何背景，只有两三条柔和布褶。
我们则是两根互不相干的管子，实拍 `logs/asset_qa/q50_notch_probe.png`
把"夹在两管之间的背景像素"染红：**705 px 的一整个三角缺口**。

业界正解不是"把线画好看一点"，而是**补布**：

- <https://cg-method.com/vtuber/live2d-glue/>：グルー只固定外侧，
  **内侧要手动把折线调短**（＝堆布、压缩），全周绑定一定崩。
- <https://saraemi.com/vtuber/2022/02/09/live2d_arm/>：沿参数打键
  **把关节件整形成肘形**，关节不是一个静态圆。
- <https://coconala.com/blogs/2995247/413880>：关节只画正圆
  「このままだとロボット感」。

**我们的实现：`tools/elbow_gusset.py`（肘内侧褶布）**

1. 离线按定稿姿势摆好上臂/前臂/手，**量出真实缺口**（不是拿圆柱模型估）；
2. 颜色用 `nearest_fill` 从袖身自己的像素推进来，
   并剔除描边与袖口白条**及其 3px 邻域**（否则补出一块带条纹的深蓝补丁）；
3. 反旋转回**角平分线**局部系，挂在新组 `elbow_fold_?`
   （父组＝上臂、枢轴＝肘、**转角 = 前臂局部转角的一半**）——
   布夹在两根骨头中间，角度天然取平分线，这是 2D 骨骼做膝/肘内侧料的标准做法；
4. 层 136/137 垫在两根管子**底下**：多出来的余量全被管子自己盖住，
   只有真正缺布的那条缝会显出来；
5. alpha 绑肘角，**v=7.02（肘 126°）才开始淡入、7.15 满**。
   上沿必须低于手摆正弦的谷值 7.17，否则举着手那两秒补布会跟着正弦一闪一闪。

配套：肘补件（`elbow_cover.py`，抹掉上臂扎进前臂肚子的残线）下移到 146/147、
半径 ×1.14→×1.45；肘折线（`elbow_crease.py`，画前臂剪影边）升到 148/149，
**两件分工明确**：下面那件抹线，上面那件画线。

### 4.3 头发动态：我们已经有什么、还差什么

**已有（`characters/xiaoxun/forms/teen/rig.json`，实测）：**

| 机制 | 条数 | 覆盖 |
|---|---|---|
| 一阶摆（`physics`） | 33 条，其中**头发 8 条** | 呆毛 / 刘海 / 左右侧发 / 后发，侧发与后发各做了**发根+发梢两段串联** |
| 二阶粒子摆（`physics2`，Live2D 式 4 粒子链） | 5 条 | 呆毛、长发、双马尾 ×2、高马尾；每粒子有 `radius/mobility/delay/acceleration` |
| 自主飘动（`ambient` + `ParamHairSway`） | 1 条 drift（amp 0.92、0.19Hz）→ **7 条绑定** | 刘海/左右侧发/后发 + 3 个发梢形变器，**每件不同延迟（0→0.30s）⇒ 风从一侧扫到另一侧** |
| 场力（`forces`） | gravity (0,1)、breeze amp 0.03 / 0.11Hz | 重力与微风常驻 |

也就是说"头发会动、会滞后、会行波、发梢更软"这几条**已经做到了**，
符合 <https://shiroikarasu.net/live2d-physics-settings-guide/> 与
<https://saraemi.com/vtuber/2021/10/30/live2d_buturi/> 的 2~3 段串联口径。

**还差四项（已登记为任务，按性价比排序）：**

1. **短发四件还停在一阶两段**，长发/马尾已经升级成 4 粒子链 —— 把
   `hair_front/side_l/side_r/back` 也迁到 `physics2`，发梢能做出"甩过去再回弹"。
2. **`forces.wind` 恒为 (0,0)**：引擎有风场但从没吹过。缺一个**阵风发生器**
   （随机脉冲 + 衰减），这是户外感/生气的主要来源。
3. **头发只认头**（`driver: head`）：跳跃、转身、弯腰时身体带动的那一下没有传过去；
   应让 `chest`/`root` 的加速度也参与输入。
4. **没有碰撞**：大幅摇头时侧发会穿过肩膀和兜帽。Live2D 的常规做法是给
   发梢件加一条"不许越过肩线"的夹限（按角度 clamp），不需要真碰撞。

## 参考链接汇总（本文引用，均已实访）

1. <https://sites.google.com/cybernoids.jp/cubism2/editor/animator/technic/quality-up>
2. <https://tech.sumzap.co.jp/entry/live2d_case_study>
3. <https://bloomeria.jp/blog/live2d-parameter-optimization>
4. <https://note.com/ryodist/n/nd15bac2226d3>
5. <https://mayonaka-blog.com/live2d-motion-howto/>
6. <https://d-gear.biz/column/8573>
7. <https://shiroikarasu.net/live2d-physics-settings-guide/>
8. <https://saraemi.com/vtuber/2021/10/30/live2d_buturi/>
9. <https://github.com/DenchiSoft/VTubeStudio> ／ <https://github.com/DenchiSoft/VTubeStudio/wiki/Plugins>
10. <https://github.com/DenchiSoft/VTubeStudio/wiki/Interaction-between-Animations,-Tracking,-Physics,-etc.>
11. <https://github.com/menglimi/astrbot_plugin_vtube_studio>
12. <https://github.com/Genteki/pyvts>
13. <https://deepwiki.com/hkopenai/vtube-studio-plugin-mcp-server>
14. <https://docs.live2d.com/en/cubism-editor-manual/physics-operation/>
15. <https://docs.live2d.com/en/cubism-sdk-manual/motion/>
16. <https://coconala.com/blogs/2995247/413880>（关节只画正圆＝ロボット感）
17. <https://saraemi.com/vtuber/2022/02/09/live2d_arm/>（把关节件整形成肘形）
18. <https://cg-method.com/vtuber/live2d-glue/>（グルー只固定外侧、内侧折线调短）
19. <https://note.com/marunaru82/n/n03aea05f41d0>（前腕を潰す伸縮パラメータ）
20. <https://miracle-usausa-nurse.com/paint/499/>（手首は肘より遅らせる＝のこし）
21. <https://note.com/candyyamada/n/na004e9fdd742>（ぎこちない＝カーブが直線的すぎる）
22. <https://kw-nmnm.hatenablog.com/entry/2018/11/06/203151>（肘デフォーマ的放置与键数）
23. <https://shiroikarasu.net/live2d-physics-settings-guide/>（头发 2~3 段串联）
24. <https://saraemi.com/vtuber/2021/10/30/live2d_buturi/>（越往发梢越轻）
25. <https://github.com/Open-LLM-VTuber/Open-LLM-VTuber>（最接近的开源对标）
26. <https://github.com/zeikar/iki>（MIT 的 JSON 2D 骨骼格式 + MCP 自动绑定）
27. <https://github.com/Inochi2D/inochi2d>（BSD-2 开放 puppet 标准）
