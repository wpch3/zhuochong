# 立绘拆件规范（ART_PARTS）

更新：2026-10-12 ｜ 状态：**执行中（头部眼睛已落地）**
关联：`tools/make_eye_parts.py`、`tools/make_body_parts.py`、`tools/make_rig.py`、`tools/check_assets.py`、
`docs/memory/GAPS.md`（G4 素材重做）、`docs/memory/TASKS.md`

> 这份文档回答三个问题：**要拆成哪些零件**、**每个零件需要引擎具备什么能力**、**怎么验收**。
> 口径对齐 Live2D Cubism 的官方做法（部件/参数命名取自 Cubism Web Framework 源码
> `src/cubismdefaultparameterid.ts`），这样以后要导入/导出 Live2D 模型时不用重新对账。

---

## 〇、一句话结论

**"整体切割"不是拆件。** 把一张图切成方块，只能做"整块平移 + 橡皮管弯曲"；
真正的可动立绘要求**每个零件是一张完整的图**（被别人挡住的部分也要画出来），
再靠**遮罩（clipping mask）**把它裁回该露出的形状。眼球能转、嘴能张到露出口腔，
全靠这件事。我们的引擎已经补上遮罩（2026-10-12），眼睛已按这个标准拆完。

---

## 一、Live2D 标准拆件表（我们照着做的清单）

层序从后往前。"状态"是本仓库的进度；"引擎能力"是这件零件要动起来、引擎必须有的功能。

### 1. 头部（最吃零件数，也最出效果）

| # | 零件 | 为什么要单独一层 | 对应官方参数 | 引擎能力 | 状态 |
| --- | --- | --- | --- | --- | --- |
| 1 | **后发 `hair_back`** | 头转动时后发要晚一拍跟上 | `ParamHairBack` | 形变 + 惯性 | ✅ 2026-10-13（5.9） |
| 2 | 耳 `ear_l/r` | 侧头时露出 | — | 旋转 | ⬜ |
| 3 | 脖子 `neck` | 头转动时脖子不能跟着整块转 | `ParamAngleX/Y/Z` | 旋转枢轴 | 🟡 并在 `seg_head` 里 |
| 4 | 脸底 `face` | 所有五官的底，含腮红 | `ParamCheek` | — | 🟡 并在 `seg_head` 里 |
| 5 | **眼白 `eye_?_base`** | 眼球移开后不能露洞 | — | — | ✅ |
| 6 | **眼眶 `eye_?_socket`** | 只作遮罩，决定眼睛的开口形状 | — | **遮罩** | ✅ |
| 7 | **眼球 `eye_?_ball`**（虹膜+瞳孔+高光） | 眼睛看向哪儿 | `ParamEyeBallX/Y`、`ParamEyeBallForm` | **遮罩 + 位移** | ✅ |
| 8 | **眼线睫毛 `eye_?_lash`** | 压在眼球上，眼球上翻被它盖住 | — | — | ✅ |
| 9 | 上眼睑 `eyelid_?_up` | 真正的"半眯/眯眼"，不是整块淡出 | `ParamEyeLOpen`/`ParamEyeROpen`、`ParamEyeLSmile` | 形变（变形器） | ⬜ 现用闭眼贴图淡化 |
| 10 | 下眼睑 `eyelid_?_dn` | 笑眼时下眼睑上推 | `ParamEyeLSmile`/`ParamEyeRSmile` | 形变 | ⬜ |
| 11 | 眉 `brow_l/r` | 表情的一半信息量在眉毛 | `ParamBrowLY/RY`、`...LX/RX`、`...LAngle/RAngle`、`...LForm/RForm` | 位移 + 旋转 + 形变 | ⬜ |
| 12 | **上唇线 `mouth_open`** + **开口形状 `mouth_mask`** | 开口度 | `ParamMouthOpenY` | **分轴缩放（sy）** | ✅ |
| 13 | **口内 `mouth_cavity`**（上颚/口腔/舌/下唇线） | 张嘴后要有东西露出来 | 随 `ParamMouthOpenY` | **遮罩** | ✅ |
| 14 | 鼻 `nose` | — | — | — | 🟡 并在脸底 |
| 15 | **前发 `hair_front`** / **侧发 `hair_side_l/r`** | 压在脸上，摇头时摆动；额头与脸颊靠 AI 重绘补全（5.4 / 5.9） | `ParamHairFront`、`ParamHairSide`、`ParamHairFluffy` | 形变（curve=tip）+ 两段摆链 | ✅ 前发 / ✅ 侧发 2026-10-13（5.9） |
| 15b | **呆毛 `hair_ahoge`** | 整根露在剪影外，可无损切出；角色的招牌 | `ParamHairFluffy` 一类 | 形变（curve=root） | ✅ |

### 2. 身体

| # | 零件 | 对应官方参数 | 引擎能力 | 状态 |
| --- | --- | --- | --- | --- |
| 16 | 躯干 `torso` | `ParamBodyAngleX/Y/Z`、`ParamBreath` | 形变 | ✅ `seg_torso` |
| 17 | 肩 `shoulder_l/r` | `ParamShoulderY` | 旋转 | ⬜ 并在躯干 |
| 18 | 上臂 `arm_?_upper` | `ParamArmLA/RA` | **旋转枢轴** | ✅ 2026-10-12（见 5.7） |
| 19 | 前臂 `arm_?_fore` | `ParamArmLB/RB` | **旋转枢轴（肘）** | ✅ 2026-10-12（见 5.7） |
| 20 | 手 `hand_l/r` | `ParamHandL/R` | 旋转 | 🟡 并在 `arm_?_fore` 里 |
| 21 | 胸 `bust` | `ParamBustX/Y` | 形变 | ⬜ |
| 22 | 裙/下摆 `skirt` | 随 `ParamBodyAngleX` | 形变（tip 曲线） | ⬜ |
| 23 | 腿 `leg_l/r`、脚 `foot_l/r` | `ParamBaseX/Y` | 旋转 | 🟡 `seg_leg_?` 整条 |

图例：✅ 已拆并接进 rig ｜ 🟡 存在但没拆到位 ｜ ⬜ 没有

---

## 二、每个零件必须满足的三条硬性要求

1. **画全**：被别的零件挡住的部分也要有像素。眼球要画成完整的圆（包括藏在眼皮下的上半部分），
   手臂要画到腋下，裙下的大腿要画出来。缺这部分，一动就露底。
2. **自己是一张独立 PNG**，透明背景，不带别人的像素（眼球图里不能有眼线）。
3. **声明自己的遮罩**：`rig.json` 里写 `"mask": "<遮罩部件 id>"`（或数组 = 多个遮罩取并集，
   见 3.8）。A9 之后遮罩是渲染时当场画的，**不再要求遮罩 layer 更小或与被裁件相邻**；
   仍然禁止：遮罩指向自己、遮罩源自己又挂遮罩（套娃）。

---

## 三、引擎已具备 / 还缺的能力

| 能力 | 用途 | 状态 | 位置 |
| --- | --- | --- | --- |
| 仿射变换（位移/缩放/旋转） | 整块零件动 | ✅ | `zimg_draw()` |
| 网格弯曲（bend + 四种曲线） | 呼吸、侧摆、裙摆、挥手、呆毛 | ✅ | `zimg_draw_warp()` |
| **分轴缩放** `"scale":[sx,sy]` | 嘴的开合（压扁开口形状而不是整体缩小） | ✅ **2026-10-12** | `zrig.c` 部件矩阵 |
| **flap 波形**（0→amp→0 循环） | 嘴型开合，不会把缩放摆成负数 | ✅ **2026-10-12** | `zrig.c` `W_FLAP` |
| 组层级 + 枢轴 + 形变跟随 | 头跟着身体走 | ✅ | `zrig.c` `group_matrix` / `bend_follow` |
| **遮罩（clipping mask）** | 眼球不滑出眼眶、口内不露到脸外 | ✅ **2026-10-12** | `zimg_composite_masked()` + `parts[].mask` |
| **多重遮罩 / 取反遮罩**（≈ 多 clipping + `IsInverted`） | 一个部件被几块形状共同裁；或只在遮罩**外面**显形 | ✅ **2026-10-13** | `"mask":["a","b"]`（并集，≤4）、`"mask_invert":true`；遮罩**渲染时当场画**（`build_maskbuf`），不再要求遮罩与被裁件在图层里相邻 |
| 眨眼五态机 | 自动眨眼 | ✅ | `zrig.c` `blink_update` |
| 视线跟随（眼球） | 眼球看向鼠标 | ✅（标签 `gaze`） | `zrig.c` |
| **动作淡入淡出**（motion fade） | 换动作不再瞬间跳帧 | ✅ **2026-10-12** | `zrig.c` `accumulate_action` + `actions[].fade` |
| **物理摆动**（弹簧惯性） | 甩头时头发晚一拍、停下来还会晃两下 | ✅ **2026-10-12** | `zrig.c` `physics_update` + rig 顶层 `physics` |
| **多段物理摆链**（2~3 段串联） | 发根先甩、发梢再慢半拍，侧发/裙摆才像布料 | ✅ **2026-10-13** | `physics[].driver` 写另一条 physics 的 id；输出可写 `deformer` |
| **关键帧动作曲线**（≈ `.motion3.json`） | 不对称节奏：快速低头 → 停顿 → 缓慢抬起带过冲 | ✅ **2026-10-13** | 通道 `keys:[[t,v],…]` + `interp: linear/smooth/step`，`zrig.c` `eval_keys` |
| **指针跟随（头/上身）** | 等价 Live2D `ParamAngleX/Y/Z` + `ParamBodyAngleX` | ✅ **2026-10-12** | `zrig.c` `zrig_look` + rig 顶层 `look` |
| **自由变形器**（FFD / 网格形变，按控制点拉网格） | 一根呆毛能摆出 S 形；眼睑/嘴形连续变化 | ✅ **2026-10-12** | `zimg.c` `zimg_draw_mesh`（格子拆三角形仿射映射）+ rig 顶层 `deformers` + 通道 `target=形变器 id, param=amount` |
| 旋转变形器（骨骼链：肩→肘→腕） | 抬手、挥手不拉皮 | ✅ **三级（肩→肘→腕）2026-10-13** | `make_arm_parts.py` 切六件 + 组 `arm_?→forearm_?→hand_?`；`ParamHandL/R` ±22°（见 5.12） |
| **命名参数层**（`ParamXxx` 外部直驱） | 脚本 / LLM / 口型 / 测试台滑条统一写一张参数表 | ✅ **2026-10-12** | `zrig.c` `load_params`/`zrig_param_set` + rig 顶层 `params` + `/api/param` |
| **表情叠加**（expression） | 笑着挥手：表情和动作两条轨，互不覆盖 | ✅ **2026-10-12** | `zrig.c` `load_expressions`/`zrig_expression_set` + rig 顶层 `expressions` + `/api/expression` |
| **口型同步**（LipSync） | 说话时嘴跟着语音开合 | ✅ **2026-10-12** | `zpet.c` `lipsync_tick` + `tools/make_lipsync.py` + `/api/speak`；动作里的嘴通道由 `zrig_set_mouth_mute` 让路 |
| **口型音素**（母音識別 / viseme） | 说「あいうえお」时嘴形不同，不只是开合大小 | ✅ **2026-10-13** | `zrig.c` `load_visemes`/`viseme_update` + rig 顶层 `visemes`（音素 → `ParamMouthOpenY`×`ParamMouthForm`）+ `/api/viseme`；包络带 `visemes` 轨时自动走这条路 |

> **合规对照表另开了一份：`docs/LIVE2D_CONFORMANCE.md`** —— 41 个官方标准参数逐条判定、
> model3/motion3/exp3/physics3/pose3 结构对照、以及"哪些现在不做以后补不回来"的风险分级。
> 那份表由 `selfcheck_repo.py check_live2d()` + `test_core.c test_live2d_standard()` 守着，
> 加参数忘了登记会直接判红。
>
> **2026-10-13 起：上表里 Live2D 侧的能力已经全部有对应实现**（部件图层、变形器两级、
> FFD 网格形变、剪贴蒙版含多重/取反、关键帧动作曲线、物理单段与多段摆链、
> 混合模式、Pose 差分、表情层、参数层、LipSync、眨眼/呼吸/视线/motion fade）。
> 剩下的差距不在"能不能做"，而在**素材拆得够不够细**（侧发/后发、眼线、手腕、裙下大腿）
> 和性能细节（我们的遮罩缓冲是整张画布，Live2D 用 256×256 分块）。

### 3.1 新增三块的 rig.json 写法

```jsonc
// ① 动作淡入淡出：写在单个动作里，单位秒。缺省 0.22；0 = 硬切（打击感动作用）
{ "id": "wave", "fade": 0.3, "channels": [ ... ] }

// ② 物理摆动：rig.json 顶层，一条 = 一个部件的一个通道
"physics": [
  { "id": "ahoge_x", "part": "hair_ahoge", "driver": "head", "axis": "x",
    "param": "bend_x", "curve": "root",
    "ratio": 0.5, "stiffness": 42, "damping": 5.0, "max": 8 }
]
// 语义：输入 = 驱动组（含父链、含旋转）带着这个部件跑了多远；
//       acc = stiffness*(ratio*输入 - 位置) - damping*速度；
//       输出 = clamp(位置 - 输入目标, ±max) —— 静止时收敛回 0，只加惯性、不改静止姿势。

// ③ 指针跟随：rig.json 顶层，speed 越大跟得越快（1-exp(-speed*dt) 平滑）
"look": { "speed": 9.0, "groups": {
  "head":  { "rot_deg": 5.0, "dx": 4.0, "dy": 3.0 },
  "chest": { "rot_deg": 1.2, "dx": 1.5, "dy": 1.0 } } }
// /api/gaze?x=&y= 会同时驱动眼球和头/上身，off=1 两者一起归零。

// ④ 命名参数层：rig.json 顶层，一条 = 一个外部可写的参数 + 它写到哪些通道
"params": [
  { "id": "ParamMouthOpenY", "label": "张嘴", "min": 0, "max": 1, "default": 0,
    "binds": [ { "part": "mouth_mask", "param": "sy",    "scale":  0.737 },
               { "part": "mouth_open", "param": "alpha", "scale": -0.55 } ] },
  { "id": "ParamAngleZ", "min": -30, "max": 30, "default": 0,
    "binds": [ { "group": "head", "param": "rot_deg", "scale": 0.5 } ] }
]
// 通道值 = 参数值 × scale，叠在动作之上（位移/旋转累加，alpha 相乘）。
// 引擎另外内建 5 个参数，不用写进 rig 也一定存在，它们直接路由到已有子系统：
//   ParamAngleX / ParamAngleY  → 指针跟随（ParamEyeLOpen/ParamEyeROpen 是 ParamEyeOpen 的别名）
//   ParamEyeOpen               → 眨眼（1=睁 0=闭；reset 交回自动眨眼）
//   ParamEyeBallX / ParamEyeBallY → 眼球
```

```jsonc
// ⑤ 表情层：rig.json 顶层，一条 = 一组参数偏移（只能写 params 里声明过的参数）
"expressions": [
  { "id": "angry", "name": "生气", "fade": 0.22,
    "params": [ { "id": "ParamBrowLAngle", "value": -0.8 },
                { "id": "ParamEyeOpen",    "value": 0.9, "mode": "set" } ] }
]
// mode: add（缺省，叠加）/ set（覆盖：按权重把参数拉到这个值）。
// 表情**不占动作状态机**：挥手动作照常跑完，表情只是叠在上面，带独立淡入淡出。
```

参数层 / 表情层的 HTTP 口子（测试台的滑条与表情按钮都是按它自动生成的，角色加参数不用改前端）：

| 端点 | 作用 |
| --- | --- |
| `GET /api/params.json` | 参数表 + 当前值（内建参数的值每帧回写，能看见自动眨眼在动） |
| `GET /api/viseme?v=A&w=1` | 口型音素（母音識別）：v ∈ SIL/A/I/U/E/O/N，`off`/`-` 松口；w = 这一帧的音量。写错音素名返回 404 |
| `GET /api/param?id=X&v=N` | 写一个参数（超出 min/max 自动夹住；不存在的 id 返回 404） |
| `GET /api/param?id=X&reset=1` | 回默认值（`ParamEyeOpen` 复位 = 交回自动眨眼） |
| `GET /api/param?all=1` | 全部复位 |
| `GET /api/expression?id=X` | 叠一个表情（`off=1` 取消；未知 id 404）；当前表情在 `info.json` 的 `expression` |
| `GET /api/info.json` | 当前角色/形态/服装/动作/缩放/眨眼/表情等全部状态 |
| `GET /api/frame.png` | 当前帧（预览和测试台都靠它） |
| `GET /api/partmesh.json?id=<部件>&max=<点数>` | **逐顶点探针（T66.10b）**：一个部件这一帧**实际会画出去**的网格顶点位移（源图像素，含从别的部件继承来的场）。返回 `cols/rows/n` 与 `dx[]/dy[]`。**单位 = 画布像素**：`k = src->w / img->w` 里 `src` 是按画布缩放过的副本、`img` 是原图，所以 **返回值随 `/api/scale` 变**（默认 0.55；同一个动作在 1.0 下读到的是它的 1/0.55）。量阈值时要么固定画布缩放、要么只做同一次调用内的比值（里布/表布 0.35 就是比值口径）。为什么非有不可：继承是**逐顶点**的，`info.json` 的 `deformers` 只给形变器的驱动量 —— 里布现在自己一张网格都没有（全靠继承表布），只读驱动量会永远是 0，等于「做了但量不出来」 |
| `GET /api/action?id=X[&force=1]` | 触发动作；`force=1` 越过优先级 |
| `GET /api/express?mood=X` | 按心情挑动作（走互动规则表） |
| `GET /api/call?kind=X` | 通话事件（call_start/call_end/call_user_speaking/call_reply） |
| `GET /api/poke?x=&y=[&tool=]` | 点一下（会走区域命中 → 规则匹配 → 兜底 clicked） |
| `GET /api/region?x=&y=[&space=canvas]` | 这个点压在哪个互动区上（含不透明像素命中）。默认帧坐标；`space=canvas` 按画布坐标。答复回报 `space` 与换算后的 `cx/cy` |
| `GET /api/hover?x=&y=&in=` | 指针位置（驱动视线与头部跟随） |
| `GET /api/blink?v=` | 按住眨眼（`v=auto` 交回自动） |
| `GET /api/gaze?x=&y=[&off=1]` | 视线方向 |
| `GET /api/scale?s=` | 整体缩放 |
| `GET /api/pose?group=&id=` | 互斥部件组切档（≈ pose3.json）。`id=none` 或省略 = 整组关掉；组/档位不存在返回 404 |
| `GET /api/pause?on=0\|1` | 冻结/恢复引擎时钟。冻结后连续两帧**逐字节相同** —— 抓对照图、做哈希断言时不会被呼吸/眨眼/物理搅乱 |
| `GET /api/step?n=&dt=` | 冻结状态下**按固定步长空跑** n 帧（`dt` 默认 1/60 秒，n 上限 6000）。冻结时 dt 恒为 0，物理和绑定延迟（`lag`）一步都不走 —— 改了参数只有直连的绑定会动，挂物理/延迟的部件原地不动（T45.11 的里布就是这么"看起来没接上"的）。有了它，"同一起始时刻 + 同一串参数 + 同样多的步数"必然得到同一帧，A/B 对照才真的可比 |
| `GET /api/force?gx=&gy=&wx=&wy=&breeze=&hz=&gust_x=&gust_y=&gust_t=` | **力场（T47.3）**。`gx/gy` 重力方向（像素空间 **Y 向下**，默认 `(0,+1)`；写成 `(0,-1)` 头发就朝天飘）；`wx/wy` 定常风；`breeze` 常驻微风幅度、`hz` 主频；`gust_*` 来一阵风（强度 + 秒数）。**风的量纲是「几个 g」不是像素** —— 内核里 `力 = 重力单位向量 × Acceleration + 风`，所以 `wx=0.3` 已经能把长发吹到输出上限。一个参数都不给 = 只读。返回里的 `wind_x/wind_y` 是**本帧真正喂进内核的合成风**（定常 + 微风 + 阵风），"我设了风"和"风真吹到头发上了"是两件事 |
| `GET /api/ambient?on=0\|1` | 环境摆动总开关。ambient 是**往参数上加偏移**的（裙摆那条 drift 幅度 0.72），开着的时候把参数设成 0 并不是"静止"，推到上限又会被夹住。做对照图、量摆链时先关掉。不给 `on` 直接报 400 |
| `GET /api/physics?on=0\|1` | 物理摆总开关。关掉时所有摆立刻停在目标上、输出归零（不攒滞后，再打开也不会暴冲）。**查接缝时必须先关它**：剖面要的是纯几何对比，物理摆会把两个部件的相对位移搅进来。不给 `on` 直接报 400，不许静默忽略 |
| `GET /api/form[?id=]` / `GET /api/outfit[?id=]` | 切形态 / 切服装 |
| `GET /api/idle?s=` | 伪造空闲秒数（测睡眠用） |
| `GET /api/quit` | 关掉预览进程 |
| `GET /api/speak?id=X` | 播一条口型包络（`voice/lipsync/<X>.json`）；`stop=1` 立刻收嘴；未知 id 404 |
| `GET /api/speech.json` | 台词 + 好感，外加 `lipsync:{active,id,level,remain}` |
| `GET /api/persona.json` | 三层人设合成后的**系统提示词原文** + 预设表 + 八个维度的当前值 + `meeting_todo`（相遇引导还剩几步）。面板上灰框里显示的就是这个 `prompt` 字段，不做二次加工 |
| `GET /api/persona/set?k=&v=` | 按**白名单**改人设并写回 `characters/<id>/persona.json`。只认 `preset` / `trait.<id>`(1~5) / `nickname` / `selfname` / `custom` / `taboo.add` / `taboo.clear` / `meeting.{enabled,user,where,when,how,relation}`，其余键一律 400。"用对话改人设"走的也是这条，面板改不了的模型同样改不了 |

### 3.2 网格形变（A5）怎么写

```jsonc
// rig.json 顶层。cols×rows 是格子数，控制点下标 0..cols / 0..rows。
// points 里写的是 **amount = 1 时这个控制点挪多少源图像素**，没写到的点不动。
"deformers": [
  { "id": "ahoge_s", "part": "hair_ahoge", "cols": 2, "rows": 4,
    "points": [ {"c":0,"r":0,"dx":11,"dy":-1},   // r=0 是素材顶边（毛梢）
                {"c":0,"r":1,"dx":4.5},
                {"c":0,"r":2,"dx":-4},           // 中段反向 → S 形
                {"c":0,"r":3,"dx":-1.5} ] }      // r=rows 是底边（发根，不动）
]
```

驱动方式两种，和别的通道完全一致：

```jsonc
// ① 动作里：target 写形变器 id，param 固定 amount
{ "target": "ahoge_s", "param": "amount", "wave": "sine", "amp": 1.0, "freq": 0.4 }
// ② 参数层：binds 里写 deformer
{ "id": "ParamHairAhogeS", "min": -1, "max": 1, "default": 0,
  "binds": [ { "deformer": "ahoge_s", "scale": 1.0 } ] }
```

- **和 `bend_x` 的区别**：`bend_x` 是一整条曲线把部件整体推歪（只有一个自由度）；
  网格形变是**每个控制点各推各的**，所以能做出 S 形、局部挤压、一边拉长一边收窄。
  这就是 Live2D 的 ワープデフォーマ（自由变形器）在做的事。
- **实现**：每个格子拆成两个三角形做仿射映射（`zimg_draw_mesh`），
  逐目标像素算重心坐标反查源图，所以格子之间不会裂缝；
  控制点全为 0 时自动走普通绘制，**像素级与原来一致**（单测里校了这一条）。
- **边界**：cols/rows 1~16，控制点越界直接加载失败（不许默默画错）；
  位移写的是原始素材像素，换画布缩放时形变量不变。
- 证据：`logs/asset_qa/a5_mesh_ahoge.png`（ParamHairAhogeS = −1/−0.5/0/0.5/1 五档 6×）。

### 3.3 关键帧动作曲线（A6）怎么写

参数化波形（sine/bounce/pulse/decay/flap）只能做**对称、周期**的动作。
真正的动作表演是不对称的——「0.18 秒猛地低头，停 0.24 秒，再用 0.33 秒抬起来并过冲一点」，
这就是 Live2D `.motion3.json` 在干的事：逐关键帧给值，中间插值。

```jsonc
{"id": "nod", "priority": 6, "duration": 1.1, "fade": 0.12, "channels": [
  {"target": "head", "param": "rot_deg", "interp": "smooth",
   "keys": [[0.0, 0.0], [0.18, 9.0], [0.42, 9.5], [0.75, -2.5], [1.1, 0.0]]}
]}
```

- 一条 `keys` 就是 `[[时间秒, 数值], …]`；**写了 keys 就不再看 `wave/amp/freq/phase`**，
  其余字段（target / param / 形变器 amount / 淡化权重）行为完全不变，所以能和波形通道混用。
- `interp`：`smooth`（默认，`z_smoothstep` 缓入缓出）/ `linear`（匀速）/ `step`（阶梯，到点才跳）。
  区间按**半开** `[t_i, t_{i+1})` 取，所以正好踩在关键帧时刻时阶梯插值已经跳过去了。
- 循环动作（`loop:true`）会对**最后一帧的时间**取模回绕；一次性动作在末帧之后保持末值。
- 校验：时间必须递增、每帧至少两个数、全仓关键帧总数 ≤ 1024（`ZRIG_MAX_KEYPOOL`），
  违反直接加载失败；`tools/selfcheck_repo.py` 也会静态拦一遍。
- 证据：`logs/asset_qa/a6_nod_keys.jpg`（`/api/action?id=nod` 连拍 6 帧）。

### 3.4 多段物理摆链（G16）怎么写

一段弹簧只能做「整体晚一拍」。真实的头发/裙摆是**一节带一节**：
根部先被甩出去，梢部又比根部晚半拍，于是摆出 S 形。做法是把第二段的**输入**
接到第一段的**输出**上（而不是再接一次头的位移）：

```jsonc
"physics": [
  {"id": "ahoge_x",   "part": "hair_ahoge", "driver": "head",     "axis": "x",
   "param": "bend_x", "curve": "root", "ratio": 0.5, "stiffness": 42, "damping": 5.0, "max": 8},
  {"id": "ahoge_tip", "part": "hair_ahoge", "driver": "ahoge_x",
   "deformer": "ahoge_s", "ratio": 0.9, "stiffness": 26, "damping": 3.4, "max": 1.0}
]
```

- `driver` 先当组名查，查不到再当**前面已经声明过的** physics id 查；
  写成后面声明的（或拼错）直接加载失败——否则这一帧读到的是上一帧的旧值。
- 第二段的 `stiffness` 要比第一段**软**、`damping` 更小，才会"慢半拍"；
  想要几段就串几段（根→梢顺序声明即可）。
- `"deformer": "<形变器 id>"` 让物理输出直接写进网格形变器的 `amount`（本例 = 呆毛 S 形），
  这就是 Live2D「物理 → 变形器」的接法；不写 `deformer` 时还是走部件通道 `param`。
- 调试：`zrig_phys_output(rig, "ahoge_tip")` 读这一段当前输出。

### 3.5 混合模式（A7）怎么写

```jsonc
{"id": "blush_l",  "file": "sprites/blush_l.png",  "layer": 203, "blend": "multiply", "opacity": 1.0}
{"id": "eye_hl_l", "file": "sprites/eye_hl_l.png", "layer": 219, "blend": "add",
 "mask": "eye_l_socket", "tags": ["gaze", "eye_open"]}
```

- `blend` 只有三种：`normal`（默认）/ `add` 加算 / `multiply` 乘算，写别的**加载失败**。
- 公式（和 Live2D 一致，都**不改目标 alpha**）：
  - 加算 `C = Cd + Cs·As`：只在已经有画面的地方提亮；透明背景上画加算层 = 什么都不会出现。
  - 乘算 `C = Cd·(1 − As + As·Cs)`：只压暗底下的像素，腮红是"透出来"的而不是糊上去的。
- 因为它们不改 alpha，**层号不能是最底层**（底下没东西就等于白画）——`selfcheck_repo.py` 会拦。
- 和遮罩可以叠加：被裁的部件先用普通混合画进 scratch，再由
  `zimg_composite_masked_blend()` 按真正的混合模式合到画面上（眼高光就是这条路径）。
- 开关靠参数：零件 `opacity` 写 1.0，参数 bind 用 **`"offset": -1.0`** 先把 alpha 压到 0，
  于是「最终透明度 = 参数值」。小寻现有 `ParamBlush`（0..1）与 `ParamEyeSparkle`（0..1，默认 0.55），
  表情里 害羞=脸红 0.95、吃惊=高光 1.0、难过=高光 0.18。
- 素材是**程序化画的**（`tools/make_blend_parts.py`，软边椭圆 + 腮红斜线），不走 AI 生图；
  位置/大小/颜色都在那个文件顶部的 `BLUSH` / `HIGHLIGHT` 常量里。
- 证据：`logs/asset_qa/a7_blend.jpg`（冻结时钟后 blush/sparkle 0→1 对照）。
  实测：腮红区 RGB `159.9,186.8,217.0 → 157.8,172.2,201.9`（G/B 掉得比 R 多 = 变暖变粉）、
  高光区 `80.9,104.8,135.7 → 150.5,170.7,195.3`（整体提亮）、**两者 alpha 改变像素数都是 0**。

### 3.8 遮罩升级（A9）：多重遮罩 / 取反 / 不挑层序

以前一帧只有一块遮罩缓冲，谁最后画进去就算谁，所以 rig 里必须保证
「遮罩和被它裁的部件在图层里紧挨着」——这条限制在加 A7 眼高光时真的绊了一次
（星形高光被迫从 222 挪到 234）。现在遮罩改成**用到的时候当场渲染**：

```jsonc
{"id": "eye_hl_l", "mask": "eye_l_socket"}                 // 老写法照旧
{"id": "cheek",    "mask": ["face", "hair_front"]}          // 多个遮罩取并集（≤4）
{"id": "outline",  "mask": "face", "mask_invert": true}     // 只在遮罩外面可见
```

- 遮罩按**当前帧的形变**渲染（跟着网格形变 / 弯曲 / 组矩阵走），和被裁件完全同步。
- 多个遮罩是**并集**：任一遮罩不透明处都可见（Live2D 的多重 clipping 也是这个语义）。
- 取反遮罩 = 对遮罩 alpha 取补；此时遮罩消失不再意味着被裁件消失（正好相反）。
- 遮罩源**自己不能再挂遮罩**（套娃要递归渲染，没必要）——加载直接报错。
- 不再有「层序 / 相邻」限制：遮罩的 layer 比被裁件大也行（单测里就这么跑的）。

### 3.7 Pose 互斥部件组（A8）怎么写

Live2D 的 `pose3.json` 管的是「差分」：一组部件里同一时刻只能有一个露面
（手势、眼高光形状、发型差分）。我们的写法：

```jsonc
"poses": [{
  "id": "eye_hl_style", "fade": 0.3, "default": "round",
  "entries": [
    {"id": "round", "parts": ["eye_hl_l", "eye_hl_r"]},
    {"id": "star",  "parts": ["eye_hl_star_l", "eye_hl_star_r"]}
  ]
}]
```

- 一个档位可以带多个部件（左右眼要一起切），它们的显隐权重同步。
- 切换：`zrig_pose_set(rig, "eye_hl_style", "star")` 或 `GET /api/pose?group=&id=`；
  `id=none` = **整组关掉**（Live2D 得专门放一张透明图，我们直接支持）。
- 淡化是**定长线性**（`fade` 秒），不是指数趋近：0.3 秒就是 0.3 秒，手感可预期。
- 加载期校验：部件必须存在、**一个部件只能归一个档位**、`default` 必须是声明过的档位、
  每组至少两个档位 —— 四条都会让加载失败（`tools/selfcheck_repo.py` 另有静态一遍）。
- 冻结时钟（`/api/pause`）时 dt 恒为 0，淡化走不动 → `/api/pose` 会自动 `zrig_pose_snap()`
  直接到位，抓对照图不用等。
- 证据：`logs/asset_qa/a8_pose.jpg`（round / star / none 三档，同一冻结帧，
  变化像素 116 / 65 / 123，alpha 改变 0）。

### 3.6 抓对照图怎么不被动画搅乱（/api/pause）

以前抓两张图做对比，中间隔着呼吸、眨眼、物理摆动，像素差里全是噪声（实测噪声能到
和效果同一量级）。现在先 `GET /api/pause?on=1` 冻结引擎时钟：

```bash
curl -s "$P/pause?on=1"
curl -s "$P/param?id=ParamBlush&v=0" && curl -s "$P/frame.png" -o off.png
curl -s "$P/param?id=ParamBlush&v=1" && curl -s "$P/frame.png" -o on.png
curl -s "$P/pause?on=0"
```

冻结期间连续两帧**逐字节相同**（冒烟测试里有这条断言），所以两张图的差 = 参数的影响，
不掺别的东西。

### 3.2 口型同步（A4）怎么跑通

```
TTS 产出 mp3 ──► tools/make_lipsync.py ──► voice/lipsync/<id>.json ──► /api/speak?id=<id>
                     │                        {dur, fps, values:[0..1]}        │
                     └── 有 wav 就用真 RMS 包络；没有就按台词音节铺节律        └── 引擎每帧写 ParamMouthOpenY
```

- **包络从哪来**：真机上把 mp3 转 wav（`ffmpeg -i x.mp3 -ac 1 -ar 16000 x.wav`）再跑
  `--wav`，得到的是**真实音量包络**；沙箱里没有 ffmpeg，所以默认走"文本节律"：
  mp3 的**时长不解码也能拿到**（直接数 MPEG 帧头），再把台词按音节铺进这段时长
  （汉字 1 音节、标点闭嘴、每个音节一个"张—保持—收"的小包）。节奏对得上，
  比固定 3Hz 的 `flap` 自然得多。**2026-10-13 起这条管线还会产出音素轨**（见 3.9）。
### 3.9 口型音素（母音識別 / viseme，T2.1.3）✅ 2026-10-13

- **为什么不是五个新参数**：Live2D 官方标准参数表里**没有** `ParamMouthA/I/U/E/O`。
  嘴只有 `ParamMouthOpenY`（0..1）和 `ParamMouthForm`（-1..1，+ 笑 / − 怒），
  あ/い/う/え/お 是这两者的**组合**（官方叫「母音認識方式」）。所以我们加的是一张表，不是五个参数。
- **表在哪**：`rig.json` 顶层 `visemes`（`make_rig.py` 的 `viseme_list()` 生成）。
  | 音素 | OpenY | Form | 形状 |
  | --- | --- | --- | --- |
  | A | 1.00 | 0.00 | 张到最大 |
  | I | 0.22 | +1.00 | 不张，咧到最宽 |
  | U | 0.30 | −1.00 | 小口撅圆 |
  | E | 0.58 | +0.55 | 半开偏宽 |
  | O | 0.88 | −0.70 | 大口撅圆 |
  | N | 0.06 | −0.35 | 闭音 |
- **驱动口径**（学 airi 的 wlipsync vowel driver）：每帧只喂**一个赢家音素 + 当前响度**，
  `zrig_viseme_set(r,"I",0.8)`；引擎做 **attack 50/s、release 30/s** 的两档指数平滑
  （收口比张口慢，否则像开关），收干净后自动把嘴交还给动作。
- **素材侧改了什么**：`ParamMouthForm` 的 bind 从 ±0.08/0.06 提到 **lip ±0.22 / mask ±0.26**，
  并给 mask 加了 **sy −0.045** 的耦合（撅圆时开口更高）；上唇线 `mouth_open` 的锚点
  从左上角挪到**中点**（`pos` 同步从 412 改到 434），否则 sx 一缩整条唇线往右平移。
- **语音侧**：`tools/make_lipsync.py` 用 pypinyin 取每个字的**韵母**→ 母音（`ia→A`、`ong→O`、
  `ie→E`、`i→I`、`u→U`…），写进包络的 `visemes` 轨；引擎 `zpet_lipsync_start_v()` 有音素轨
  就走母音識別，没有就退回只开合。**没装 pypinyin 会打警告并被自检判红**，不会静默降级。
- **闸门**：`test_viseme()`（A/I/U/E/O 两两像素差 > 25px、い 比 う 宽、weight 比例、
  8ms 不许瞬间到位、松口要还嘴）、smoke 10 项、selfcheck 6 项（音素只许写标准嘴参数、
  不许重样、文档要记载）。证据图 `logs/asset_qa/_viseme_sheet.jpg`。

- **为什么要让动作里的嘴让路**：`talk` 动作自己也有 flap 通道，两边叠加会让 `sy`
  超过素材高度（口内被拉伸）。所以口型同步期间 `zrig_set_mouth_mute(rig,1)`，
  嘴完全交给参数层；播完自动解除、参数回默认。
- **边界**：包络 < 2 帧或 fps ≤ 0 直接拒绝；id 只允许 `[A-Za-z0-9_-]`（防 `../` 读任意文件）；
  上限 4096 帧（30fps ≈ 136 秒）。

**实测（scale=1，sleep 定格）**：`ParamArmRA` = −10 / 0 / +10 → 右臂外缘 x = **606 / 644 / 681**
（±38px ≈ scale 4.0 × 10，线性）；`ParamMouthOpenY=1` 嘴真的张开，`ParamAngleZ=30` 头歪 15°，
对照图 `logs/asset_qa/param_sheet.png`。

**表情实测**：6 个表情（微笑/害羞/生气/难过/吃惊/困倦）叠加后画面都变（2.6 万～3.6 万像素），
动作不被顶掉，对照图 `logs/asset_qa/expression_sheet.png`。
**透け眉（G21，已做）**：眉毛本体仍画在刘海底下（层 232/233），另加一份**半透明副本**
（层 241/242，`opacity 0.42`）画在刘海之上，并用 `"mask": "hair_front"` 裁切 ——
所以它**只在被刘海挡住的那块**显形，没被挡的地方不会变深。副本不接任何通道，
靠新字段 `"motion_from": "brow_l"` 照抄本体的全部通道值（动作、参数、表情、形变跟随一起动）：

```jsonc
{ "id": "brow_l_ghost", "file": "sprites/brow_l.png", "layer": 241,
  "opacity": 0.42, "mask": "hair_front", "motion_from": "brow_l" }
```

实测：生气/难过/吃惊三个表情在眉区分别改变 9880 / 10231 / 9885 像素（之前是 0），
对照图 `logs/asset_qa/brow_ghost.png`。

三者的叠加顺序是固定的：**动作（含淡化混合）→ 指针跟随 → 物理**。
所以转头会甩起头发，而头发的惯性不会反过来干扰动作。

---

### 3.10 表情 × 口型的叠加口径（G38）✅ 2026-10-13

- **问题**：笑脸把 `ParamMouthForm` 推向 +（横咧），「う」要推向 −（撅圆），两层抢同一个参数。
- **官方答案**：`CubismWebFramework/src/motion/icubismupdater.ts` 的执行序常量
  —— EyeBlink 200 → **Expression 300** → Drag 400 → Breath 500 → Physics 600 →
  **LipSync 700** → Pose 800。**口型在表情之后，嘴由口型说了算。**
- **我们怎么做**：`param_effective()` = 动作 → 表情（三累加器）→ 口型。
  纯加算（官方写法）会把笑 + う 抵消成 −0.30 的中性嘴 —— 所以改成"口型落位 + 表情留余味"，
  这是有意偏差，已登记在合规表。
- **接管力度随口型用力程度走（2026-10-13 修，G39）**：`w = viseme_weight × viseme_activity`。
  `viseme_activity` = 本帧口型相对默认值用了多大力（0..1）；`viseme_weight` 默认 **1.0**
  （0.8 是官方给"只驱动 `ParamMouthOpenY`"定的，我们还驱动 `ParamMouthForm`，
  残留 20% 的笑在满口型上一眼就能看见）。于是：满力说「う」→ Form **−1.00**（笑不笑都一样，
  口型独占）、小声说「う」(力度 0.25) → **+0.44**（笑意透出来）、停顿 → **+0.70**（表情全额拿回）。
  改之前是恒定权重，笑着说一整句时 Form 全程卡在 0.14 = 用户说的"张嘴了微笑还在"。
- **松口要平滑**：`zrig_viseme_clear()` 是"松口"（`vis_weight→0`，形状一路收回默认，
  收干净了才真正释放），整句松口用慢一档的 `ZRIG_VIS_RELEASE_OFF = 8/s`（音素之间仍是 30/s），
  实测单帧跳变 < 0.12、约 1.8s 叹回表情；要"立刻清零"（换角色 / 取测试基准）用 `zrig_viseme_reset()`。
- **表情混合**：补上 Cubism exp3 的第三种 Blend `multiply`（`mode: "multiply"`），
  求值 `(base + overwrite + additive) × multiply`，和 `CubismExpressionMotion` 一致。
- **怎么看**：测试台「表情 × 口型」面板（组合按钮 + `value / 过表情后 / 最终` 三列实时表），
  或 `/api/params.json` 的同名三列。证据图 `logs/asset_qa/_expr_viseme_sheet.jpg`。

### 3.11 笑眼 `ParamEyeLSmile` / `ParamEyeRSmile`（G40）✅ 2026-10-13

- **官方口径**：笑眼**不是另一种睁眼，是另一种闭眼** —— 谷型 ∪ → 山型 ∩。
  官方 Haru 的 F05 表情写得很直白：`ParamEyeLOpen=0 (Multiply)` + `ParamEyeLSmile=1 (Add)`
  + 眉毛 `ParamBrowL/RY=0.32`。四篇独立的日文建模教程也都强调"做笑眼时要先把开闭参数打到 0"。
- **素材**：AI 重绘一张"山型笑眼脸"`design/redraw/face_eyesmile.png`（同一张脸、只改眼睛），
  走闭眼那条**同一条流水线**切补片：`make_eye_closed_parts.py --variant smile`
  （肤色外接框定初值 → 挖掉眼睛带的脸部 NCC 微调 → 眼球框外扩切补片 → 逐通道肤色平移 → 软椭圆羽化）。
  切出来 `eye_l_smile.png` 57×56 @ (156,177)、`eye_r_smile.png` 57×58 @ (229,172)，
  和闭眼件**同位同尺寸**，覆盖率 99.5% / 99.7%，接缝色差 4.0 / 2.2。
- **引擎**：新标签 `eye_smile` + 内建参数 `ParamEyeLSmile/RSmile`（0..1，默认 0）。
  三条规矩：① **笑眼隐含闭眼** `blink = max(blink, smile)`（调用方推一个参数就够）；
  ② 笑眼涨多少，谷型闭眼件就按 `1 − smile` 让多少（两条睫毛线一起画会叠成一团黑）；
  ③ 笑眼件走和闭眼件一样的"最后 25% 才淡入"斜坡，前 75% 由眼眶压扁表现。
  层号：笑眼件压在同侧所有眼部件之上（左 221 / 右 233）。
- **表情**：新增 `happy`（开心·笑眼）= 笑眼 1.0 + `ParamMouthForm` +1.0 + 眉 +0.32（照 F05）
  + 腮红 0.38 + 眼高光 1.0，fade 0.28s。
- **闸门**：单测 `test_eye_smile()`（真 rig 像素闸 + **合成 rig 结构闸**：三张眼摆在互不重叠的位置，
  逐块数像素）、smoke 6 项、selfcheck 7 项；负控三次（笑眼不隐含闭眼 / 笑眼件不显形 / 闭眼件不让位）全部判红。
  证据图 `logs/asset_qa/_eye_smile_sheet.jpg`（睁眼 / 谷型闭眼 / 山型笑眼 / 单眼笑 / happy 五格）。

### 3.12 动作通道全部迁到参数上（G41）✅ 2026-10-13

- **为什么要改**：官方 `motion3.json` 的曲线 `Target` 只有三种 —— `Parameter`、
  `PartOpacity`、`Model`（`cubismmotion.ts` 第 38~40 行三个常量；实测 Haru 的
  `haru_g_m01.motion3.json` = Parameter 42 条 + PartOpacity 20 条 + Model 1 条）。
  **没有"直接写部件位移/旋转/缩放"这种通道。** 我们以前 18 个动作共 197 条全是这种，
  等于要求调用方知道角色拆了几件。
- **怎么迁**：不重写动作（那些像素/角度是调出来的美术成果），而是**按参数的 bind 系数反算**
  `参数振幅 = 几何振幅 ÷ bind scale`。换算表 = `tools/make_rig.py` 的 `GEO2PARAM`，
  遇到没登记的几何目标**直接报错**。结果 197 → 160 条，全部是 `{"target": "ParamXxx"}`。
- **顺带清掉的脏东西**：① 左右对称的两条通道（侧发 / 两肩 / 两只眼球）换算后归同一个参数，合成一条；
  ② idle/think 里"整只眼在脸上平移"那 24 条逐件通道**直接删** —— 眼部件全在 head 组里，
  组位移本来就带着走；而且那是一张手写清单，新加的笑眼件根本不在里面，眨眼时会掉队。
- **新增 `bias`（直流偏置）**：官方 `CubismBreath` 是 `offset + peak*sin`，`ParamBreath` 值域 0..1，
  纯正弦会被下限 clamp 掉半个周期。breath 动作写 `{"wave":"sine","amp":0.5,"bias":0.5}`。
- **顺带补上 `ParamEyeBallForm`**（标准参数表第 10 项，瞳孔形状）：贴图模型做不出真变形，
  用瞳孔缩放代替（只缩放眼球件 —— 眼白底/眼眶/眼线是矩形小块，一放大就露方边）。
  合规表 ✅36 → **✅37**。
- **口径统一成"参数满格 = 这个动作能做到的最大幅度"**，为此调了几个 bind 系数：
  `ParamBrowL/RY` −3→−5、`ParamBaseX` 1→2、`ParamBaseY` −1→−4、`ParamArmL/RB` ±5→±10、
  `gaze.max_offset` [3,2]→[4,2.5]、`look.groups.head.dy` 3→10。
- **回归证据**：18 个动作 × 7 个时刻逐像素对照，质心位移最大 5.3px，其余 ≤2.2px；
  证据图 `logs/asset_qa/_param_channel_ab.jpg`。

### 3.13 动作淡化换成官方曲线 + 每个动作自带 FadeOutTime（G42）✅ 2026-10-13

**以前**：动作淡入用 `z_smoothstep`（自己挑的 S 曲线），收尾则靠 `W_PULSE` 波形里
一句硬编码——"结束前 0.15 秒乘个衰减"。两处都不是官方口径，而且收尾那句**只管 pulse 一种波形**，
别的波形（decay/bounce/keys）怎么落地全看运气。

**现在**照 `CubismMath.getEasingSine` 与 `CubismMotion.doUpdateParameters` 重写（依据见
`docs/REFERENCE_NOTES.md` 第七批）：

| | 官方 | 我们 |
|---|---|---|
| 淡化曲线 | `getEasingSine(v) = 0.5 − 0.5·cos(vπ)`，`v<0→0`、`v>1→1` | `z_ease_sine()`（`src/core/zc.c`），同式同钳位 |
| 淡入 | `tmpFadeIn = getEasingSine((now − fadeInStart) / FadeInTime)` | `w = z_ease_sine(u)`，`u` 用动作自己的 `fade`（默认 0.22s） |
| 淡出 | `tmpFadeOut = getEasingSine((endTime − now) / FadeOutTime)` | `w *= z_ease_sine((duration − elapsed) / fade_out)`，`fade_out` 默认 0.2s，可在 rig 里按动作写 |
| 循环动作 | `endTime < 0` ⇒ `tmpFadeOut` 恒 1 | `loop` 的 `duration` 传 −1，淡出那一乘被 `tot > 0.0` 挡掉 |

**淡出挂在动作身上，不是挂在"谁接替它"身上**——所以正在淡出的**上一个**动作
（`compute_group_transforms` 的 `prev` 分支）同样要乘它自己的 `fade_out`。
漏掉这一乘会在动作演完那一帧把 pulse 的满值整个闪出来（实测 `ParamArmLA` 0 → 2.667，
持续约 0.2 秒），**这个 bug 是靠逐帧回归采样抓出来的，不是靠眼睛**。

换曲线本身几乎看不出来（smoothstep 与 sine 最大只差 0.0098），**改的是口径不是观感**；
真正改掉观感的是动作级 FadeOutTime：所有波形统一收尾，W_PULSE 里的后门拆掉。
证据图 `logs/asset_qa/_fade_sine_ab.jpg`（左＝两条曲线及其 ×20 差值；
右上＝ head_pat t=0.90 落在淡出窗口内的像素对照；右下＝ surprised 的 `ParamArmLA` 时间序列）。

### 3.14 裙摆摆链（G43）✅ 2026-10-13

**先查官方**：Haru 的 `physics3` 只有前髪/横髪/後ろ髪/**スカーフ**四组，没有裙子；
翻遍 8 个官方示例模型，**Hiyori 有**「スカート　横揺れ」+「スカート　縦揺れ」。
它的做法是本节的样板（依据见 `docs/REFERENCE_NOTES.md` 第八批）：

| | 官方 Hiyori | 我们 |
|---|---|---|
| 拓扑 | **横摆、纵摆两条独立通道**，不是串成多段 | `skirt_x` / `skirt_y` 两条 physics |
| 横摆输入 | `ParamBodyAngleX`(X) + `ParamBodyAngleZ`(Angle)，各 weight 100 | 同上，各 weight 1.0 |
| 纵摆输入 | `ParamBodyAngleY`(X) | 同上 |
| 头部参数 | **一个都不吃**（裙子挂在身上） | 同上，单测盯着 |
| 纵摆手感 | 比横摆钝（mobility 0.8/0.9、delay 0.9/0.6） | 更低刚度 + 更高阻尼比（1.44s/0.78 vs 1.28s/0.66） |

**裙子没有拆成独立部件**。形变器是挂在部件上的网格，可以只动其中几行——
`seg_torso` 是 273×501、裙子占下 42%（y≥290），用 `cols=2, rows=10` 的网格，
`r=0~5` 一个点都不动，`r=6` 正好压在裙腰上当"根"，`r=7~10` 是裙身到裙底。
裙摆荡开后露出来的是早就拆好并重绘过的大腿，不是空洞。

**为此补了两样引擎能力**：

1. **physics 可以吃参数**（≈ 官方 `.physics3` 的 `Input` 数组）。
   以前摆链的输入只能是"某个驱动组移动了多少像素"，而 `ParamBodyAngleX` 绑的是
   `seg_torso.bend_x` —— 弯曲是非仿射的，根本不进组矩阵，拿组位移读不到。
2. **形变器和 bend 不再二选一**，详见下面两个 bug。

**顺带修掉两个一直存在的渲染 bug**（都是做裙摆时撞出来的）：

- **网格形变器把 bend 吃了**：`draw_state` 里是 `if (mesh) … else if (bend) …`。
  部件一旦挂上形变器，它的 `bend_x/bend_y` 就被整个丢弃。
  **G16 的多段摆链正是"第一段写 bend、第二段写形变器"——第一段一直白写**。
  现在按 Live2D 变形器嵌套的语义改成叠加：控制点先按网格位移挪、过矩阵，
  再在目标坐标上叠 bend（和逐像素那套共用同一个 `zimg_bend_factor`）。
  实测同一个 rig、旧引擎 vs 新引擎，头发动作每帧差 8000~10500 像素。
- **一个部件只认第一张网格**：找形变器的循环 `break` 掉了，第二张起静默失效。
  裙摆要横纵两张，不改就只有一张生效。现在累加，并在加载时拦住
  "同部件两张网格尺寸不一样"（尺寸不同没法逐点相加）。

网格行数选 `rows=10` 不是为了裙摆精度，是为了**上身**：网格路径下 bend 曲线
在控制点上采样、格子内线性插值，`rows=5` 时 `u²` 被折成 6 段，上身轮廓有
1000+ 像素偏移；`rows=10` 把它压到百位数。

证据图 `logs/asset_qa/_skirt_ab.jpg`（sway 期间四个时刻，上排物理关、下排开）。
摆链输出现在可以直接读：`/api/info.json` 的 `deformers` 字段。

### 3.15 眉形 ParamBrowLForm / RForm（G45）✅ 2026-10-13 —— 合规表最后两个 ⬜

**没有画新素材。** 合规表原先写的是"要么新素材、要么给眉毛铺 FFD 网格"，
而眉毛本来就是一条横着的细带，网格能表达的形状足够了——
`cols=4, rows=2` 的网格（沿长度 5 列），中段抬起就是「山なり」，压下就是「しかめ」。

**官方口径**（Cubism 手册，见 `docs/REFERENCE_NOTES.md` 第九批）：

- `−1` = 眉をしかめるような寄せる形（皱眉／困扰）
- `+1` = 山なりに眉が上がる形（眉峰隆起／惊讶）
- **「変形」不许带位置移动** —— 上下是 `ParamBrowLY`、左右是 `ParamBrowLX`、
  角度是 `ParamBrowLAngle`，Form 只负责原地改形状

最后那条是硬约束，落成每列 dy = `[+2.3, −1.1, −3.6, −1.1, +2.3]`（眉头那端收到 +1.8）：
中段与两端反号、净和只有形变量的 **0.172**。这条由 `selfcheck ⑯` 按几何核，
不在单测里核——它是配置层的事，selfcheck 看得到每个控制点。

**七个表情都接上了**（Haru 的 exp3 里六个表情在用眉形，我们照办）：
angry −1.0、sad −0.55、shy −0.3、surprise +1.0、happy +0.4、smile +0.3。

**透け眉自动跟随**：`brow_*_ghost` 靠 `motion_from` 抄本体的通道值，
而形变器查找本来就同时认 `motion_from` 源和自己（`cand->part != mi && cand->part != pi`），
所以刘海上那层半透明眉毛的形状跟着一起变，不用另配。

幅度受限于美术结构——这个角色的刘海盖住大半条眉毛，额头上只透出 42% 不透明度的 ghost，
所以 ±1 的全画面差异只有 270 像素左右。这是**设定使然，不是实现没生效**：
单测验证变化全部落在 y 200~260 这条眉毛带内，一个像素都没跑到别处。
证据图 `logs/asset_qa/_brow_form.jpg`。

## 四、生产流程（这就是"Live2D 教程"在我们这边的落法）

Live2D 官方教程的顺序是：**分层画稿 → 导入 → 建网格 → 加变形器/参数 → 绑动作**。
我们没有 PSD 分层原稿（只有一张合成图），所以多一步"还原分层"：

```
① 还原分层   tools/make_body_parts.py   身体按关节切段 + 重叠带羽化（过渡方案）
             tools/make_eye_parts.py    眼睛拆成 眼眶/眼白/眼球/眼线（已达标）
             tools/make_mouth_parts.py  开口形状（遮罩）+ 口内（原画没有，按配色画出来）
             tools/make_hair_parts.py   呆毛（必须排在 make_body_parts 之后跑）
             tools/make_bangs_parts.py  刘海 + 额头 AI 重绘回贴（同样必须排在 make_body_parts 之后）
             ↑ 拆不出来的被遮挡像素 → 用 generate_image 局部重绘（G4c），只回贴被遮区域
② 量关节     tools/make_anchors.py      量出颈/肩/肘/腕/髋/膝/踝，写进 design/anchors.json
③ 生骨架     tools/make_rig.py          由上面两份产物生成 rig.json（禁止手写 rig.json）
④ 机器验收   tools/check_assets.py      尺寸/键色/白边/色卡/IoU/分段无损/关节不露底，共 146 项
⑤ 眼见为实   预览抓帧 → logs/preview_check/*.png，人工看一眼再交付
```

**为什么不直接用 Live2D Cubism 编辑器**：它的运行时是官方 SDK（C++/Web，带依赖与授权条款），
而本项目的硬要求是"纯 C11、零依赖、可商用"。所以我们照搬**它的数据结构与参数命名**
（部件、遮罩、参数 ID），自己实现运行时；将来要吃 `.model3.json` 也只是加一个导入器的事。

---

## 五、已完成的零件（后续零件照着这四种套路做）

### 5.1 眼睛（遮罩型）
| 文件 | 内容 | 在 rig 里 |
| --- | --- | --- |
| `eye_?_socket.png` | 眼眶剪影（纯白+软边） | `layer 211/223`，`mask_only: true` |
| `eye_?_base.png` | 原贴图，眼眶内填成眼白色 | `layer 212/224`，标签 `eye_open` + `eye_not_wide` |
| `eye_?_wide.png` | 真·瞪大眼补片（AI 重绘，**虹膜已挖掉**填眼白） | `layer 213/225`，标签 `eye_wide` + `eye_open` |
| `eye_?_ball.png` | 完整的虹膜圆（上半部分按列补全） | `layer 214/226`，`mask: eye_?_socket`，标签 `gaze` |
| `eye_?_lash.png` | 眼线睫毛 | `layer 218/230`，标签 `eye_not_wide` |
| `eye_?_closed.png` | 谷型 ∪ 闭眼（AI 重绘） | `layer 219/231`，标签 `eye_closed` |
| `eye_?_smile.png` | 山型 ∩ 笑眼（AI 重绘） | `layer 221/233`，标签 `eye_smile` |
| `eye_?_pain.png` | 倒 V ∧ 痛苦闭眼 `>_<`（AI 重绘） | `layer 222/234`，标签 `eye_pain` |

> **层号带的基址是 211（左）/ 223（右），每眼 12 槽**（2026-10-16，T41.2 起）。
> 原来是 216/226 每眼 10 槽，加两档眼形后会撞到眉毛的 236/237，所以整条带往下挪。
> 挪的前提查过：全仓库只有 selfcheck 的「层号不重复」一条闸管这些数字，
> `tests/` 和 `tools/` 里没有硬编码（那些 216/226/230 的命中都是像素坐标）。
>
> **三种闭眼形状互斥**（∪ / ∩ / ∧）：谁涨谁顶上，另两张按 `1 − v` 让掉。
> **瞪大眼是唯一一张"睁着的"补片**：它顶替 `base`/`lash`（靠 `eye_not_wide` 标签），
> 但**不顶替虹膜** —— 补片里的虹膜在切件时就挖掉了，视线照常由 `eye_?_ball` 负责（DC64）。
> 它同时挂 `eye_open`，眨眼时和常态睁眼件走同一条退场曲线（DC63，不能自己写线性淡出）。

实测：虹膜半径 13.4 / 13.6 px，眼眶 27×30 / 25×31 px，眼球可动 ±5/±4 px。
动作 `look_around`：只有眼球动。证据 `logs/preview_check/eye_zoom.png`。

### 5.2 嘴（**AI 重绘口内 + 遮罩分轴缩放**；G4s）
原画只有一条闭合笑线，**没有口腔**——这类零件切不出来。第一版按配色"算"了一个六边形
色块 + 一条红带当舌头，结果张到一半是一块深褐斑，用户实拍反馈「嘴巴位置错误，形状很怪」。
按 D19 重做：**口内必须 AI 生图画出来**，再配准回贴。

| 文件 | 内容 | 在 rig 里 |
| --- | --- | --- |
| `mouth_mask.png` | 开口形状（= 口内剪影，带软边） | `layer 205`，`mask_only`，`anchor [0.5,0]`（上唇线中点），`scale [1, 0.0545]` |
| `mouth_cavity.png` | 口内真素材：上牙列 / 上颚 / 口腔 / 舌 / 嘴角 | `layer 206`，`mask: mouth_mask`，**`motion_from: mouth_mask`** |
| `mouth_open.png` | 原来的闭合笑线，当上唇压在口内上面 | `layer 210`（张嘴时淡出到 0.1） |

做法（`tools/make_mouth_open_parts.py`，5 步）：
1. `design/redraw/face_mouthopen.png` = AI 重绘的「同一张脸、嘴张开成 ah」（洋红底，
   prompt 锁死发色/眼睛/线稿色，只改嘴）；
2. **虹膜配准**：两只虹膜质心定相似变换（只有缩放+平移），再在脸部做 NCC 微调
   （挖掉嘴那一块，因为那里本来就该不一样）——实测 `scale=0.2096`、
   `NCC=0.9252`；
3. **在原始分辨率上取嘴洞**（牙只有十几像素，先缩小再找会被糊掉）：深色轮廓围出的
   连通块 + 填洞（白牙、粉舌都在洞里）；
4. 缩到"不超过笑线宽"（24×22），**上沿对齐实测笑线**（`line.y0..y1`），所以位置不会偏；
5. 写 `mouth_parts.json`（含配准数字与证据计数），`make_rig.py` 直接读。

**半开也要像嘴**：口内加 `motion_from: mouth_mask`，口内图跟着开口形状一起压扁；
否则固定大小的口内被遮罩裁一半，半开时只剩一条黑缝（第一版就是这个毛病）。

张开多少 = `sy` 从 0.0545（闭）撑到 ~0.95（最大 22px）。
`talk` 用 `flap` 3Hz 开合，`happy`/`surprised`/`hammered`/`sleep` 各有自己的张法。
验收数字：口内 429px、牙 18px、舌 183px。
证据 `logs/asset_qa/g4s_mouth_open.png`（0 / 0.3 / 0.6 / 1.0 四档 8× 放大）。

### 5.3 呆毛（无损切出型）
整根都在头部剪影之外，背后没有任何零件 → 直接切，不用补画，是最便宜的一件。
`hair_ahoge.png` 63×60，切线 y=48，根部 12 行渐隐；`layer 190`，组 `head`，
摆动用 `bend_x + curve:"root"`（根在底边）：呼吸 1.6px、侧摆 4px、高兴 7px、被锤 9px。
证据 `logs/preview_check/ahoge_strip.png`。

### 5.4 刘海 + 额头（**AI 重绘型**，这一类最重要）

> 用户 2026-10-12 的原话：**"就用原画拆件会出大问题。"** —— 对的。
> 刘海底下的额头与眉毛，在原画里**一个像素都没有**；抠图抠不出来，程序也算不出来。
> 这一类零件只有一条路：**让 AI 按同一套配色重画，再只把被挡住的那块贴回去。**

做法（`tools/make_bangs_parts.py`，一条命令跑完）：

1. **出重绘图**：把 `seg_head.png` 放大 3 倍、补洋红底，交给生图工具做**局部编辑**。
   prompt 要点 = 只去掉刘海、露出完整额头和两条细眉；脸型/眼睛/发色/鲸鱼发卡/洋红底
   /平涂风格/肤色 `#FCE4D8`、发色 `#D8D8E8` 全部保持不变。产物 `logs/asset_qa/head_nobangs.png`。
2. **对齐**（必做，AI 不保尺寸也不保构图）：两张图各自找虹膜连通块求质心，
   用**两眼中点 + 瞳距**解相似变换（眉毛那一件还要带**旋转**，见 5.5）。
   本次实测 **scale 0.8122、平移 (1.3, 2.0)**（3 倍坐标系）。
   ⚠️ 找虹膜的判据必须卡暗（`R<110`）：这个角色**发梢也是蓝的**、还左右对称，
   第一版把发梢当成了眼睛，位置整整差 70px。
3. **判定"哪里是被挡住的额头"**：原图不是皮肤 ∧ 重绘是皮肤 ∧ 在眼睛上沿以上 ∧ 在头部剪影内。
   再往**脸这一侧**外扩 2px（把发丝的抗锯齿边一起交给刘海零件，否则刘海一摆，
   额头上会留下一圈"发丝幽灵"），并补掉补丁内部的小窟窿。
4. **肤色配准**：只拿**补丁四周那一圈皮肤**算逐通道增益+偏移（第一版拿整张脸算，
   被腮红和下巴阴影带偏，额头发黄）。本次 gain `[0.80, 0.85, 0.83]` / offset `[51.3, 37.4, 39.4]`。
5. **切两件**：`hair_front.png` = 掩膜内的**原画像素**（一刀不改）；
   `seg_head.png` 的同一块换成重绘的皮肤+眉毛。两件是严丝合缝的拼图 →
   **静止合成与原图 0 像素差**，验收照样全绿。

| 文件 | 内容 | 在 rig 里 |
| --- | --- | --- |
| `hair_front.png` | 刘海（132×105，9555 像素） | `layer 188`，组 `head`，`pos [152,100]` |
| `seg_head.png` | 额头被补全的脸（多出 9555 像素皮肤 + 两条完整眉毛） | `layer 180` |

摆动用 `bend_x + curve:"tip"`（**吊在顶上、发梢在下**，和呆毛的 `root` 正好相反）：
呼吸 0.6px、待机 0.9px、侧摆 2.4px、高兴 3.2px、被锤 4.0px。幅度压在 4px 以内，
再大就会把补画区的边界露出来。

证据：`logs/asset_qa/bangs_pipeline.png`（原画→重绘→补全脸→刘海零件→叠回去五连图）、
`logs/preview_check/bangs_strip.png`（实拍摆动）、`sprites/bangs_report.json`（对齐与配准数字）。

⚠️ **流水线顺序**：`make_body_parts.py` 会重新生成 `seg_head.png`，把补画冲掉。
重跑身体分段之后**必须**再跑一次 `make_bangs_parts.py`（它自带"已经补过就跳过"的判断）。


### 5.5 眉毛（AI 重绘 + alpha 抠像型）

眉毛压在额头上，**它底下那块皮肤原画同样没有**。所以再生一张「同一张脸、去掉眉毛」的图
（`logs/asset_qa/head_nobrows.png`），用它补眉毛挪开后露出来的额头。

和刘海那件的三处不同（都是踩出来的）：

1. **对齐要带旋转**。这张重绘图两只眼睛差了 30px 高度，只缩放不转，眉毛会错十几像素。
   现在解的是完整相似变换（缩放+旋转+平移），**对齐残差 1.5px**（3 倍坐标系，折合 0.5px）；
   残差 >12px 直接报错，要求重新生图。
2. **切法是 alpha 抠像，不是硬掩膜**。眉毛笔触本来就是半透明的：
   `a = (底色亮度 − 当前亮度) / 满值`，眉色再按 `C = (src − (1−a)·skin) / a` 解混。
   脸那边**整块**换成重绘皮肤（不是按 a 混 —— 第一版那样做会留一层鬼影、叠回去还偏黑）。
   叠加后 `a·C + (1−a)·S = 原图`，所以静止画面一个像素都不变。
3. **找眉毛不能只看颜色**。额头上还有几根碎发。最后用的判据是三条叠加：
   ① 比「本地皮肤底色」暗（中值模糊估底色）；② 种子要暖褐（R−B>14）；
   ③ **横向开运算**只留「又宽又扁」的那条 —— 竖着的碎发自动出局。
   再从种子沿着「比底色暗」的像素长回完整笔触：眉毛上缘压着一道冷灰描边，
   只卡暖色会把它留在脸上，挑眉时就成了「两条眉毛」。

| 文件 | 内容 | 在 rig 里 |
| --- | --- | --- |
| `brow_l.png` | 画面左眉 53×33（614 像素） | `layer 181`，锚点 `[0.5,0.5]`（绕自己中心转） |
| `brow_r.png` | 画面右眉 55×14（305 像素） | `layer 182`，同上 |

层序：脸 180 < 眉 181/182 < 刘海 188 < 呆毛 190 —— 眉毛往上挑会**自动滑进刘海底下**，
不需要额外遮罩。动作（对应 Live2D `ParamBrowLY/RY` 与 `ParamBrowLAngle/RAngle`）：
惊讶 −4.5px + 外挑 3°、高兴 −2.0px、难过 +1.6px 内八、思考 −2.4px 单边挑、
被锤 +2.6px、说话 −0.8px、睡觉 +1.0px。

证据：`logs/asset_qa/brow_check.png`（去眉 / 贴回 / 挑眉 5px 三连）、
`logs/preview_check/brow_strip.png`（实拍五个动作）、`sprites/brow_report.json`。

### 5.6 闭眼（**AI 重绘真素材 + 交叉淡化**；G4r）
第一版是"几何眼皮"：从眼睛上方切一块皮肤，按 `blink` 往下滑盖住眼睛。问题是
**原画里没有"闭着的眼睛"这张画**——闭到底屏幕上只剩一块比脸亮的肤色饼加一条被眼眶
裁短的睫毛，用户实拍反馈「开心的闭眼错位」。按 D19 改成真素材。

| 文件 | 内容 | 在 rig 里 |
| --- | --- | --- |
| `eye_l_closed.png` / `eye_r_closed.png` | AI 重绘闭眼脸上切下来的补片（闭眼线 + 睫毛 + 周围皮肤） | `layer 221/231`（压在睫毛上面），`tags:["eye_closed"]`，不挂遮罩 |
| 睁眼四件 | 眼眶/眼白/眼球/眼线 | 加 `tags:["eye_open"]`，和闭眼件交叉淡化 |

引擎早就有这对标签（`zrig.c`：`eye_open → opacity *= 1-blink`、
`eye_closed → opacity *= blink`），等价于 Live2D 的 `ParamEyeLOpen` 在贴图版里的做法，
所以这次**没动一行 C 代码**。

做法（`tools/make_eye_closed_parts.py`）：
1. `design/redraw/face_eyesclosed.png` = AI 重绘「同一张脸、眼睛闭上」（洋红底）；
2. **配准没有虹膜可用**（眼睛闭着），改成：暖色肤色块外接框定初值 →
   在"挖掉眼睛那条带"的脸部做两轮 NCC 网格搜索（缩放 0.65~1.3 倍 × 平移 ±24px，
   再细到 1px / ±1%）→ 实测 `scale=0.2055`、`NCC=0.6837`；
3. 补片范围 = **眼球框外扩 13px**（不能拿"窗口里的深色像素"定框：窗口里还有眉毛和
   压过来的发丝，框会一路长到把两只眼连起来）；
4. 配色：**只解平移、且只作用在肤色像素上**。直接最小二乘解 gain+offset 是病态的
   （皮肤取值全挤在 240 附近），实测解出 `gain=0.15 / offset=214`，皮肤对上了，
   睫毛却被映射成**亮红色**——截图里那条"红杠"就是这么来的；
5. 羽化成软椭圆（方补丁的直角边在脸上一眼就看得出来），并自动撑大不透明区域，
   直到盖住原画 99% 以上的眼睛像素。

验收：左眼盖住 99.5%、接缝色差 4.53；
右眼 99.7%、2.26。
证据 `logs/asset_qa/g4r_blink.png`（blink 0 / 0.5 / 1 三联）。
旧的 `make_eyelid_parts.py` 留着当兜底：没有闭眼真素材的角色仍然走几何眼皮。

### 5.7 手臂关节（**AI 重绘 + 真关节型**；G4c）

拆件前手臂是**竖切下来的一整块板**：里面带着一条外套前襟，整块转 8° 以上就会把前襟甩出
身体轮廓，所以 `wave` 只能用网格形变假装（腕部横移封顶 60px，手永远抬不起来）。
真正要抬手，缺的不是引擎，是**袖子底下的那块躯干**——原画里一个像素都没有。

做法（`tools/make_arm_parts.py`，一条命令跑完）：

1. **出重绘图**：把躯干区裁出来交给生图工具，要一张「同一角色同一服装、**双臂完全去掉**、
   洋红底、同一套配色」的无手臂躯干 → `logs/asset_qa/g4c_gen_noarms.png`（928×1147）。
   ⚠️ **本项目的生图工具不做掩膜 inpaint**：把待补区域涂成洋红、要求"只填洋红"，
   模型仍会整张重画（实测袖子变白、裙子变紫）。所以只能"整图重绘 + 事后配准回贴"。
2. **配准**（这一步最难）：AI 重绘的人体**横纵比例都和原画不一样**，单一等比相似变换
   残差 31px（肉眼就是错位）。改成 **sx、sy 各自扫（步长 0.02）+ 平移** 的四参数网格搜索，
   打分用 **FFT 边缘互相关**并除以 `sqrt(Σ Be²)` 归一化（不归一化时分数会单调偏向小尺度，
   实测直接贴到下界 0.520）。结果 **sx 0.470 / sy 0.480 / 平移 (5, 240)**，
   兜帽、抽绳、扣子、下摆条、裙褶目视全部重合 → `logs/asset_qa/g4c_align_check.png`。
   逐通道最小二乘配色 gain `[1.000, 0.938, 0.973]` / offset `[1.2, 17.1, 9.8]`，
   可见区平均通道误差 12.13 → 落盘 `characters/xiaoxun/design/redraw/torso_noarms.png`（445×1292）。
3. **沿袖缝切，不切直线**：① 按袖子的青 `#6CB4C0`（|Δ|<150）flood 出袖子；
   ② 从袖子最后一行往下**逐行跟随**把袖口和手带上——一行里可能有好几段（手指张开就是五段），
   所以要把"上一行区间左右放宽 6px 后相交的**所有**段"都收走（只跟一段时手指缝漏了 755px）；
   ③ 袖口的三道白条不是青色、又贴着轮廓（不算内部孔洞），再按行**补到轮廓外缘**；
   ④ 在肘（`anchors.elbow_*`，y=553）切成上臂/前臂，留 **24px 重叠带**，
   **只让前臂淡入、上臂在带内保持满值**（两件都淡的话 0.5 over 0.5 = 0.75，肘部会透出底）。
3b. **肩头两边各留一份**：原画里肩膀的圆头画在袖子上，整块拿走躯干就剩一条平口。
   所以肩线以下 46px 的袖子**不从躯干挖走**（躯干和手臂各留一份，静止时完全重合）：
   手臂转开后躯干仍有一个圆肩，这是 2D 拆件的标准做法（Live2D 的 `shoulder` 部件同理）。

3c. **补画区要描线稿**：原画每条剪影边上都有一条 `#5A5A6E` 的线；补出来的衣片如果只有
   平涂白，手一抬露出来的就是"纸片剪开"的感觉。所以新产生的那段剪影边按线稿色描回去
   （2px，外圈 0.9 内圈 0.45），实测描了 1412 像素。

4. **躯干补绘 + 塗り足し**：袖子那块（外扩 2px 连抗锯齿边一起）从躯干挖掉，
   能用重绘补的就补（73px，肩头那一小条），补不到的地方把衣片颜色**往外长 5 圈并渐隐**
   （Live2D 素材的标准做法，手臂转开时切口不是一条硬透明边）。
   重绘图是洋红底抠的，边缘有一圈被烤进 RGB 的紫，必须两道判据一起挡：
   离洋红距离 >150 **且** `min(R,B) − G ≤ 25`（品红 = 红蓝高绿低；这角色只有白夹克和青袖，
   不会误伤）。只卡第一条时验收"键色残留"直接挂 605 像素。

| 文件 | 内容 | 在 rig 里 |
| --- | --- | --- |
| `arm_l_upper.png` | 左上臂 92×239 | `layer 140`，组 `arm_l`，枢轴=左肩 `(97, 364)` |
| `arm_l_fore.png` | 左前臂 113×193（2026-10-13 起**不含手**，切到腕线 `wrist_y+1`） | `layer 142`，组 `forearm_l`（父=`arm_l`），枢轴=左肘 `(76.5, 553)` |
| `hand_l.png` | 左手 83×86（含 10px 往袖口里缩的皮肤续出） | `layer 138`（**画在前臂底下**），组 `hand_l`（父=`forearm_l`），枢轴=左腕 `(54.5, 666)` |
| `arm_r_upper.png` | 右上臂 93×239 | `layer 141`，组 `arm_r`，枢轴=右肩 `(346, 364)` |
| `arm_r_fore.png` | 右前臂 119×193（同上，不含手） | `layer 143`，组 `forearm_r`（父=`arm_r`），枢轴=右肘 `(367, 553)` |
| `hand_r.png` | 右手 82×86 | `layer 139`（**画在前臂底下**），组 `hand_r`（父=`forearm_r`），枢轴=右腕 `(390, 666)` |
| `seg_torso.png` | 挖掉袖子（40713px）+ 补绘 73px + 塗り足し | `layer 100` |

参数（命名对齐 Cubism）：`ParamArmLA/RA` = 上臂绕肩 ±10 → **±60°**，
`ParamArmLB/RB` = 前臂绕肘 ±10 → **±50°**，`ParamHandL/R` = 手绕腕 ±1 → **±22°**
（2026-10-13 新增，安全上限实测 40°，见 5.12），正值一律是"往身体外侧抬"。
动作里原来打在 `seg_arm_?` 上的 `bend_x` 全部按 **1° ≈ 6.0px 腕部位移**（肩到腕 344px）
换算成 `rot_deg`，观感不变但变成真关节；在此之上新加了小臂的"鞭梢"延迟
（待机/侧摆/高兴/被锤）和真正的挥手：**上臂 −52°、前臂 −28° 并以 2.2Hz 摆 ±15°**。

**验收数字**（`check_assets.py` 已按四件的真实层级重算，含前臂绕肘的父子复合旋转）：

- 无损切分：静止叠回去与原画 **少 0 像素**（RGB 预乘口径残差 76px，都是指缝里 alpha<50 的抗锯齿点）；
- 压力姿势从 10° 提到 **上臂 25° + 前臂 20°**：肩 **0**、肘 **0** 新增空洞（上限 60）；
- ⚠️ **符号陷阱（2026-10-12 复查发现）**：PIL 的 `rotate` 是画面**逆时针**，
  引擎的 `rot_deg` 是**顺时针**，两者相反。第一版验收脚本按 PIL 符号写的 25°，
  实际测的是"两条手臂往身体内侧转"那个**安全方向**；真正会露馅的是**外展**。
  外展时腋下本来就该露出背景，整体空洞指标判不了，所以改判两件事：
  **躯干自身新增内部空洞 = 0**、**切口描线稿 ≥ 200px**（见 `check_assets` 的
  「袖下躯干无新窟窿」「切口描线稿」两项）；
- 挥手动作：上臂 −58°、前臂**再往回折 −80°**（总 138°，手举到肩上）。
  第一版前臂写 −28°（和大臂同向），等于顺着大臂继续外展，整条手臂还是一根直筒 ——
  用户当场指出"挥手的肘关节呢？"。**肘的方向必须和大臂相反才看得出关节**；
- 键色残留 0 像素，躯干新增带紫像素 **0**（原画自带 57 处不算）。

证据：`logs/asset_qa/g4c_align_check.png`（配准叠图）、`g4c_arm_mask_check.png`（掩码描边）、
`g4c_static_diff.png`（静止差异点位）、`g4c_arm_pose_strip.jpg`（静止/25°/25°+25°/最大 四连）、
`g4c_wave_strip.jpg`（挥手六连拍）、`sprites/arm_parts.json`（pos/size/pivot/自验收数字）。

⚠️ **流水线顺序**：`make_body_parts.py` 会重新生成 `seg_torso.png` 把袖子装回去，
所以 `rebuild_parts.sh` 里手臂是第 2 步（身体之后、眼睛之前）。

### 5.8 边缘质量："毛边"和"切割感"分别是什么，怎么量

用户看到的两类瑕疵，根子完全不同，别混为一谈：

**（一）切割感 = 零件切口是二值 alpha。** 零件从整图上按掩码切下来时，
`alpha = where(mask, 255, 0)`，边界只有 0 和 255 两种值 → 阶梯状。
刘海这一件最明显（它整片压在脸上）：改成"掩码做两遍 3×3 平均 → `clip(x*1.35−0.18)` →
内部拉回 1.0"的软切口后，`hair_front.png` 的**边界硬跳变从 100% 降到 0%**，
半透明像素占比 0.1% → **11.2%**。眼眶遮罩同理（原来是一圈固定 170 的硬边，改成 2px 斜坡）。

**（二）毛边 = 抠像留下的脏色边。** 这一项**查完是虚惊**：现用的
`tools/prepare_sprites.py`（硬掩码 + 被污染边缘像素换成最近的干净色 + LANCZOS 缩放）
在轮廓上本来就有 2.5% 半透明像素、硬跳变只有 4%。试过的两条"更正确"的路都更差：

| 方案 | 硬跳变 | 白边光晕 | 洋红残留 | 半透明 |
| --- | --- | --- | --- | --- |
| 现用（硬掩码 + 换干净色 + 直接 LANCZOS） | 4% | 61 | 6 | 2.5% |
| 距离斜坡软 matte + **预乘** LANCZOS | 4% | **1197** | 372 | 2.6% |
| 同上但换 BOX（无负瓣） | **25%** | 317 | 123 | 1.2% |

原因：LANCZOS 有负瓣，强边缘处预乘值会**过冲**，再除以一个很小的 alpha 就放大成
亮斑/紫斑；换成无负瓣的 BOX 又因为缩放比只有 0.89（支撑 1.1 像素）几乎等于最近邻，
锯齿反而更重。**结论：抠像这块先不动**，`tools/prepare_sprites.py` 维持原样，
力气花在零件切口上。（这段结论同时写进 `docs/memory/LESSONS.md`，别再重做一遍。）

量化这两项的口径（可复现）：
- 半透明占比 = `8 < alpha < 248` 的像素 / 不透明像素；
- 边界硬跳变 = 沿每行/每列第一个 `alpha>235` 的像素，其外侧邻居 `alpha<20` 的比例；
- 白边光晕 = 半透明且比紧邻本体亮 18 且亮度 >225 的像素数（纯白判据会把浅紫发梢误判）；
- 多底验收 = 白 / 灰 (128,128,132) / 黑 (18,18,22) 三底 `alpha_composite` + NEAREST 放大 6~9 倍
  （棋盘格会藏浅色光晕，黑底不会）。

### 5.9 侧发两缕 + 后发（**AI 重绘型·到目前为止最难的一件**；2026-10-13）

目标：左右两缕侧发、以及脑后那一大片后发，各自成为能单独摆动的零件；
**它们盖住的脸颊 / 耳朵 / 下颌 / 脖子由 AI 重绘补全**（D19：被遮挡区必须重绘，不能靠几何抠图）。

成品（`body_parts.json` 自动纳入 `check_assets` 验收）：

| 零件 | 尺寸 @ 身体坐标 | 层 | 像素 | 驱动参数 |
| --- | --- | --- | --- | --- |
| `hair_side_l` | 106×132 @ [99,153] | 245 | 5830 | `ParamHairSide` + `ParamHairSideS` |
| `hair_side_r` | 105×132 @ [243,153] | 246 | 6101 | 同上（反相） |
| `hair_back` | 241×143 @ [102,48] | **170**（画在脸底下） | 13457 | `ParamHairBack` |

#### 怎么切的（`tools/make_sidehair_parts.py`，12/13 步）

1. **重绘**：原画 3 倍 + 洋红底送 `generate_image`，提示词必须写**具体发型名 + 硬边界** ——
   `BOWL-CUT … no strand may touch cheeks / jaw / chin / neck`。
   写"remove the side hair / tuck it behind the ears"一律无效（模型只会把头发挪一点）。
2. **配准**：蓝虹膜（`R<110` 的连通块）解相似变换 → `scale 0.7701`、3 倍坐标平移 `(+15.1,+35.3)`，
   残差 < 1px。
3. **分区**（全部在 `seg_head` 局部坐标里算，`head.y == body.y`）：
   - `face = fill_holes( largest(dilate(暖色∧实心,3), 中轴种子) | feat )`，
     `feat` = 两只虹膜 r26 的圆 ∪ 嘴的矩形（取自 `eye_parts.json` 的 **`iris_center`** 和
     `mouth_parts.json` 的 `anchor_pos/size`）。
   - `hair = (alpha>16) ∧ ¬face ∧ ¬teal ∧ ¬已被别的零件拿走 ∧ (B ≥ R−6) ∧ (y < 脖线+2)`。
   - 左右两缕：从根部切线 `y_root = 虹膜 y − 26 = 174` 往下取连通块，
     再 `fill_holes(闭运算)`、剔青色领子、`dilate 4` 吃回外圈碎发。
   - 后发 = 剪影内、不属于脸也不属于侧发的那一片，**并上补画区里的冷色**之后
     再做一次连通过滤（种子 = 根部以上那部分），否则脖颈阴影会被涂成两个大菱形。
4. **补画回贴**：掩膜内原像素 → 零件；同一块位置换成重绘像素 → `seg_head`；
   补完 `grow_colors` 外扩 8px 填缝，最后 `newhead.alpha = min(newhead.alpha, 原图 alpha)` 夹回剪影。
5. **塗り足し（bleed）**：后发往脸底下多铺 14px，**顺序是先挖再算区域** ——
   `region = dilate(back,14) ∧ (挖完之后仍被脸盖住)`。先铺后挖会把后发涂到脸外，静止画面就露馅。
6. **根部重复像素**：侧发根部往上多带 `BLEED_ROOT=16` 行，这 16 行在 `seg_head` 里**不挖**，
   零件里也留一份。摆动曲线用 `tip`（顶固定、梢摆动），这几行永远不动，切口因此永不外露。
7. **头/躯干重叠带**：发梢垂进 `y>278` 那一段，`seg_torso` 也存了一份半透明副本，
   不处理就会留一条钉死的"幽灵发梢"。但**不能直接挖透明**（躯干会多出窟窿，
   `check_assets` 的"袖下躯干无新窟窿"实测 72 > 上限 60）→ **只换颜色不动 alpha**：
   存 alpha → 挖 → `grow_colors` 把领子/脖子的颜色涂进来 → 还原 alpha。

#### 怎么接到 rig 上（`tools/make_rig.py`）

- 参数：`ParamHairSide`（两缕 `bend_x`，scale 7，curve **tip**）、
  `ParamHairSideS`（驱动形变器 `side_l_s`/`side_r_s` 做 S 形）、
  `ParamHairBack`（`bend_x`，scale 5，curve **tip**，幅度约侧发的 1/3）。
  ⚠ 曲线方向第一版写错过：`zimg_bend_factor` 里 **`tip` = 顶边固定、底端最大**（权重 t²），
  **`root` = 底边固定、顶端最大**（u²）。后发写成 `root` 的结果是**头顶那条剪影在晃**
  （实测摆动集中在帧 y63~88，整个头形在变），改成 `tip` 之后摆动落到 y110~137 的发尾。
  判断口诀：**哪条边钉在身上，就固定哪条边** —— 呆毛根在下沿用 `root`，
  侧发/后发/刘海都是从头顶长下来的，一律 `tip`。
- 形变器：`side_l_s`/`side_r_s`，2×4 网格，四行偏移 `−1.5 / −3.4 / +2.0 / +5.6`（带 dy），
  发梢那一行最大 —— 这就是"一缕头发自己会甩"的形状。
- 物理 **两段摆链**（G16）：
  `head → side_l_x`（ratio .85 / stiff 26 / damp 4.1 / max 16）
  → `side_l_tip`（driver 写前一条 physics 的 id，输出 `"deformer":"side_l_s"`，.12/14/3.0/1.6），
  右边同理；后发 `back_x`（.5/34/4.9/10，慢且稳）。
  ★ 2026-10-22（Q37）调强过：旧值（.55/46/5.4/7 → .85/22/3.0/1.0）实测转一次头，
  发色重心**单调地跟到位、没有过冲也没有回摆** ＝ 头发是粘死的。
  现在同一个转头：侧发滞后 −13px → 过冲 +4px → 1.5s 收敛（`logs/asset_qa/q37_hair_turn.png`）。
- 18 条动作里侧发幅度从 `breath 0.8` 排到 `hammered 6.0`，点头动作用关键帧（A6）压出"甩—回弹"。

#### 验收数字（2026-10-13）

- 静止合成 vs `body_full.png`：**少 0 像素 / 多 48 像素**，RGB 差 >32 的只有 146 px（共同区 248124 px，均差 0.08）。
- `check_assets` **322 项 0 不通过**（部件 36 / 动作 18 / 区域 3 / 组 9）；`make check` 全绿
  （静态自检 48 / 单测 393 / ASan 0 / 冒烟 64）。
- 参数扫描（冻结时钟，`/api/pause?on=1` + `/api/param?id=…&v=…`）：
  `ParamHairSide ±1` 改变 2895/2928 像素，位移自根部 0px 线性长到发梢 3px（帧坐标，帧=画布×0.5495）；
  `ParamHairBack ±1` 改变约 1378 像素。证据图 `logs/asset_qa/_hair_param_zoom.jpg`、
  `_cheek_zoom.jpg`（5 倍：摆开后露出的耳朵与脸颊是重绘出来的）、`_dyn_hammered.jpg`（被敲八连拍）。

#### 这一件踩的坑（**别再犯**）

| 坑 | 症状 | 正解 |
| --- | --- | --- |
| `np.roll` 实现的 `dilate/erode` | 左侧发顶到 x=0，一膨胀绕到右边，零件宽 245（整头那么宽） | 位移必须**零填充**（本文件 `shift()`） |
| 软掩码乘在**外缘** | 原画自带抗锯齿的剪影外缘又软一次 → 合成少 19 像素 | 软边**只做内缘**：`keep = m ∧ ¬dilate(¬m ∧ α>100, 3)` |
| 重绘比原画宽 | 侧发边上露出一条补画边（多 371 像素） | 补画 alpha `min(新, 原)`，锁定掩码也 `∧ (α>16)` |
| 脸掩码做闭运算 | 压在脸上的发丝被当成脸，切出来一堆鬼影 | 禁用闭运算，改 `fill_holes(largest(...) | feat)` |
| 发掩码只取 `α>100` | 外圈碎发（α 16~100）留在脸上变鬼影 | 头发/外扩判据统一 `α>16`，皮肤判据仍 `α>100` |
| **`grow_colors` 取色源写 `α>0`** | 原画里散着几百个 `α=1~4`、RGB 纯绿 `(0,255,0)` 的抠像垃圾像素，肉眼看不见，一旦被当成颜色源往外扩就被重写成 `α=255` 的亮绿点（实测躯干多出 88 个，侧发一摆下巴边上就闪一颗绿点） | **取色源卡 `α>32`**，且后续轮次只把"本轮新填的"加进源集合 |
| 后发曲线写成 `root` | 头顶的剪影在晃（摆动集中在帧 y63~88） | 从头顶长下来的头发一律 `tip`（顶边固定） |

#### 这一件给验收体系加的三道闸（`check_assets` / `selfcheck_repo`）

| 新增检查 | 在哪 | 防的是什么 | 怎么证明它真的会红 |
| --- | --- | --- | --- |
| **头发摆动不露底**（±12px 剪切，逐像素比，只数剪影内缩 4px 以内的"深处"空洞） | `check_assets.py` | 被头发挡住的脸没按 D19 重绘 —— **静止时一个像素都看不出来** | 把左侧发底下的脸整片挖空（2310 px）→ 该项 **128 > 20 变红**，而"无损切分"仍然是 0 |
| **无键色垃圾像素**（可见像素里不许有纯绿/洋红） | `check_assets.py` | 抠像/重绘残留，以及被颜色外扩放大的垃圾像素 | 修 `grow_colors` 之前实测 88 个纯绿像素 |
| **切件工具都进了重建链** + **步骤编号连号** | `selfcheck_repo.py` | 新写的切件工具忘了加进 `rebuild_parts.sh`（零件会静默过期，出过两次） | 把 `make_sidehair_parts.py` 从脚本里去掉即报红 |

三条写法上的讲究，都是这轮踩出来的：
- **逐像素比，不能比总数**：头发一挪会顺手盖住别处的缝，总数相减是个大负数，
  挖了洞照样"通过"（实测 −294 → −285 仍然过）。
- **只数"深处"**：头发本来就长在剪影边上，摆开后外缘露出背景是**正确**的
  （原画那块就是背景，重绘的脸比带发的轮廓窄）。把剪影往里腐蚀 4px 再数，
  清白素材是 7~10 像素，真缺重绘是 128 像素，区分度够。
- **只甩左右**：上下甩是用整行位移模拟的，行与行取整差会在零件自己身上切出 1px 横缝
  （引擎的 bend 是反向采样不会有），那是测试工具的假阳性。

### 5.10 目录里哪些图是"活的"
`sprites/` 里有 34 张图，rig 只引用 29 张；剩下的别当成垃圾删掉：

| 文件 | 状态 |
| --- | --- |
| `body_full.png` | **源图**：所有切件都从它切，必须留 |
| `eye_open_left/right.png`、`eye_closed_left/right.png` | 未拆件角色的**兜底分支**（`make_rig.py` 里 `if not eyes`） |
| `eye_l_lid.png`、`eye_r_lid.png` | 没有闭眼真素材时的**兜底眼皮**（`if not closed`） |
| `seg_arm_l/r.png` | **已被四件臂取代**：`make_body_parts.py` 还在生成，rig 不再引用。留着当对照，不要接回 rig |
| `eye_l/r_lash.png` | **挖脸用的定位图**：rig 现在画的是剪过的 `eye_?_lash_up.png`，但挖眼线那一步要靠这张原图圈范围 |
| `eye_l/r_closed.png` | 双重身份：既是 blink 最后 25% 淡入的闭眼补片，又是**眼窝皮肤的来源**（抹掉线之后） |

### 5.11 眼线二次拆件 → 真·眨眼（**挖脸 + 眼眶压扁 + 眼线下滑**；G4m，2026-10-13）

**病根（先看证据）**：在这一步之前，`seg_head`（脸）上**原封不动画着两只睁开的眼**——
眼白、虹膜、整圈眼线都在。眼部零件只是"在同一个位置又画了一遍"盖住它。
后果有两条，4 倍放大就能看见（`logs/asset_qa/_eye_parts_zoom.jpg`）：

1. 眼眶（遮罩）一收，底下露出来的是**脸上那只睁着的眼**，不是眼皮；
2. 上眼线钉死在脸上，不会随眼皮下滑；只能靠"睁眼图淡出 / 闭眼图淡入"，
   而两张不同的画各 50% 叠起来必然是**一只灰色幽灵眼**（见 `eye_blink_sheet.jpg` 上排）。

**四件套（必须一起上，缺一件都不自洽）**

| 件 | 做法 |
| --- | --- |
| 素材 `tools/make_eyeline_parts.py` | 把 `seg_head` 上「眼眶开口 ∪ 上眼线」那块**只换 RGB、不动 alpha**，换成干净眼窝皮肤 |
| 引擎 `zrig.c` | 新标签 `eye_aperture` + 字段 `aperture_min`：`part_sy *= 1 − blink·(1−aperture_min)` |
| rig `make_rig.py` | 眼眶锚点挪到**开口下沿**、挂 `eye_aperture`；上眼线改 `eyelid` + 实测行程；闭眼补片只在最后 25% 淡入 |
| 闸门 | `check_assets`「脸上无残留睁眼」静态闸 + `test_core` 的 `test_eye_aperture` 引擎闸 |

**皮肤从哪来**：不需要再找 AI 重绘——第 9 步已经有一张**配准好的闭眼脸补片**
（`eye_?_closed.png`）。把补片上那条闭眼线抹掉，剩下的就是现成的眼窝皮肤，
而且天然对齐（同一次 NCC 配准出来的）。三个坑都踩过：

- **只抹"暗像素"会被白点反杀**：闭眼线里嵌着几粒白色高光，亮度高、留下来之后
  颜色外扩反倒以它们为源，把整条线填成**一排白方块**。→ 线要整条**带状外扩 3px** 一起抹。
- **四邻域外扩填不平一条横线**：只能从带子左右两头往里爬，爬出来是一道**灰褐糊痕**。
  → 改成**按列上下插值**（取带子上下两端的皮肤色线性过渡），上下够不着的零星列才退回外扩。
- **眼眶是软边**：卡死 `alpha>128` 会在斜坡那一圈留下原画，闭眼时是**一串白点**（实测 988 粒）。
  → 用软权重 `w = clamp((α−24)/72)` 做加权替换，和眼白被同一张遮罩裁切的权重互补。

**眼眶压扁的两个硬约束**

- **锚点必须放在开口下沿**：`zimg_make_matrix` 是"把 anchor 这个像素点放到 pos 上"，
  所以改锚点**必须同步把 pos 挪到那个点的身体坐标**，否则整只眼会跳位。
  锚点放在整张图的底边（空白行上）会把眼睛整只"吸"下去——`test_eye_aperture` 第一版就这么挂的（下沿跑了 23px）。
- **`aperture_min = 0.06`**：留 6% 而不是 0，免得矩阵退化成零面积。
- **`lash_hold = 0.5`**（2026-10-15 加）：上眼线在闭合度到这个值之前**完全不下滑**，
  之后按 smoothstep 补齐到满行程。两端（0 和 1）的落点和线性行程完全一样。
  为什么要有它：睫毛弧线画在上眼睑线上、内眼角那条尾巴更低，跟着开口一起线性下滑的话，
  半闭时尾巴会压进虹膜 —— 放大看是一个黑钩，瞳孔和高光被吃掉，眼睛变成一条扁平青带
  （用户 2026-10-15 截图）。A/B 留证 `logs/asset_qa/lash_ab.png`，
  前后对比 `logs/asset_qa/eye_ladder.png` → `eye_ladder_fixed.png`。
  **默认 0 = 旧的线性行程**，不写这个字段的 rig 行为不变。

**上眼线的行程不能拍脑袋**：那条弧画在上眼皮**边**上，不在开口最顶端。
拿"开口高 × 0.85"当行程会滑过头，实测变成**眼白露在眼线上方**。
现在由切件工具逐列实测「眼眶下沿 − 眼线下沿」取中位数写进 json：左 21.5px / 右 17.0px。

**还得剪一刀**：切眼睛时「眼线」那片把**虹膜左右两道描边**也带进来了（`_lash_sprite.jpg`）。
不动时它盖在虹膜边上看不出来，一随眼皮下滑就拖到脸颊上，像两行灰眼泪。
→ `trim_lash_top()` 逐列只留**从上往下第一段连续的墨**，另存 `eye_?_lash_up.png`（剪掉 52/56 像素），
原 `eye_?_lash.png` 留着不动（挖脸还要靠它定位眼线）。

**淡化曲线也换了**（`zrig.c`）：

```c
eye_open   *= clamp((1 - blink) * 4, 0, 1);   /* blink<0.75 不掉透明度 */
eye_closed *= clamp((blink - 0.75) * 4, 0, 1); /* 只在最后 25% 淡入 */
```

闭合这件事交给"眼眶压扁 + 眼线下滑"去演，两张图只在**已经几乎重合**（都是下眼睑上一条线）时才交接，
灰幽灵就没有了。

**验收**

| 关卡 | 结果 |
| --- | --- |
| `check_assets` 新闸「脸上无残留睁眼」 | 眼线 0 + 虹膜 0 像素（上限 24）；**负例**：把旧脸换回去 → 553+329 / 580+350 像素，立刻变红 |
| `test_eye_aperture`（引擎） | 可见眼白 1281 → 980 → 667 → 0 单调减少（blink 0 / .25 / .5 / 1）；半闭时下沿只动 ≤4px、上沿下移 >8px；**负例**：注释掉压扁那两行 → 1281→1281→1281，三条断言同时红 |
| 四态复拍 | `logs/asset_qa/eye_blink_sheet.jpg`（上=旧 下=新，1.00/0.75/0.50/0.25/0.00 各一格） |
| 真动画 | `logs/asset_qa/_autoblink.jpg`：不冻结连拍 60 帧抓到自动眨眼那一帧，闭眼干净 |

**重建链顺序**：眼线这一步**必须排在所有会改写 `seg_head` 的工具后面**
（侧发那步会重写 `seg_head`），所以它是第 13 步、紧挨着 `make_rig`。

### 5.12 手腕拆件 + 裙下大腿（**塗り足し缩进式 + bend 代替旋转**；G4c2，2026-10-13）

这一件分两半，**共用一条教训：补画要补在"遮盖件的下面"，不是补在它的边上。**

#### 一、裙下大腿：真根因是"躯干扛着大腿"

抬腿露底，第一反应是"腿画短了，往上补"。错。逐件渲染一看：
`seg_torso` 原先切到 `legs_top+ov = 776`，**裙摆下那截大腿是画在躯干上的静止副本**，
腿件只从 776 开始。腿一动，动的是膝盖以下，大腿留在原地——
不是缺素材，是**那块素材归错了件**。

改法三步（`tools/make_body_parts.py`）：

1. 逐列从裙摆下沿往下扫肤色，求每列的 `thigh_top`（大腿顶边）→ 写进 `body_parts.json`；
   **两腿之间的空档列会一路扫到膝盖**（实测 x=207/208/227/228 给出 864），
   必须按最近的正常列回填，否则闸门的取样带是歪的。
2. 腿件从 `thigh_top − THIGH_EXT(64)` 开始切，整条大腿归腿件；
   躯干按同一条线裁掉（`torso_thigh_trim_px = 148375`）。
   **`make_arm_parts.py` 里重切躯干时要套同一个 `thigh_top`**，
   否则它会把躯干按 bbox 整块贴回去，白改。
3. 腿件上缘原来有渐隐——大腿归了腿件之后必须删掉，不然大腿根半透明直接透背景。

#### 二、腿只能 bend，不能绕髋旋转（实测否决）

旋转试过两个 pivot（髋 704 / 裙摆下沿 736），都在**大腿内侧（裆侧）、裙摆下沿正下方**
撕出楔形缺口（证据：`logs/asset_qa/_thigh_gapmap.jpg`）。原因是几何上的：
补画只能长在下沿**之上**（被裙子盖住的地方），缺口却开在下沿**之下**，填不进去。
把 `THIGH_WIDEN` 从 7 加到 18 只救了外侧——外侧有"裙比腿宽 30px"的余量可藏，
裆侧没有。**目视会误判成修好了，必须用像素统计复核。**

| 腿的动法 | ±4° | ±8° | ±10° | ±15° |
| --- | --- | --- | --- | --- |
| 绕髋旋转（新露底像素） | 109 / 61 | 188 / 95 | 214 / 102 | 252 / 94 |

| 腿的动法 | 10px | 20px | 30px | 40px |
| --- | --- | --- | --- | --- |
| **bend（curve `tip`）** | **0 / 0** | **0 / 0** | 28 / 16 | 44 / 38 |
| bend 写成 `curve:"root"`（负控） | 348 | 708 | 1076 | — |

结论写进 rig：`ParamLegL/R` ±1 → `seg_leg_?` **bend_x ±20px，curve `tip`**。
`tip` 是"顶边钉死、下摆甩"，构造上零缺口；写成 `root` 就是"大腿根甩出裙子"，
一摆 ±20px 就漏 700+ 像素——所以 `check_assets` 里**连曲线名都静态卡死**。

#### 三、手腕：手画在前臂"底下"，塗り足し往里缩

四件臂 → 六件臂。腕线 `wrist_y` 两侧都是 666，求法有两个坑：
**不能用 `anchors.json` 的比例值**（算出 708，落在指尖）；
**也不能在整列 x 范围上扫肤色**（裙子和腿同高，扫出 732）——
必须**在该侧手臂自己的掩码内**从肘往下扫第一段连续肤色（`SKIN_RUN=3`）。

| 做法 | 为什么 |
| --- | --- |
| 手件 layer **138/139**，画在前臂（142/143）**底下** | 手叠在上面时，手腕的塗り足し会盖住袖口；藏在下面，袖口永远在前 |
| 前臂切到 `wrist_y+1`，手件带 `WRIST_STUB=10` 的皮肤续出 | 转手时袖口下不会裂缝 |
| 续出的皮肤按 `erode(前臂掩码, WRIST_STUB_IN=4)` **往里缩 4px** | 贴边补会在 ±20° 时从袖侧探出一小片"飘肉"（`_wrist_stub_cmp.jpg` 左右对照） |
| 静止自检合成**按 layer 排序**再叠 | 不排序会把手叠到袖子上，自检图和真帧不是一回事 |

**塗り足し的通用写法**：续出长度 `L` 与缩进量 `D` 要满足 `L·sin(θmax) < D`。
这里 10·sin20° ≈ 3.4px < 4px，所以转到 ±20° 皮肤仍然完全躲在袖口里。

角度扫描（腕专用闸的读数，上限 60）：

| 转角 | 10° | 20° | 30° | 40° | 50° | 60° |
| --- | --- | --- | --- | --- | --- | --- |
| `hand_l` | 6 | 21 | 38 | 49 | 105 | 139 |
| `hand_r` | 6 | 25 | 43 | 55 | 130 | 188 |

→ **手腕安全幅度 ≤40°**，rig 现用 `ParamHandL/R` ±1 → ±22°，留了一倍余量。
物理上再挂一条 `hand_?_lag`（driver = `forearm_?`，ratio .22 / stiffness 34 / damping 4.4 / max 9），
手就是"上臂→前臂→手"这条鞭子的第三节。

#### 四、这一轮自己抓出来的三个假闸（比零件本身更值钱）

写闸门的人和写零件的人是同一个，**闸门绿了不等于零件对了**。
这三个都是"一直绿、其实什么都没量"：

1. **整行横带会量错部位**。腕线 y=666 正好穿过裙摆，按 `wrist_y ± 2·ov` 取整行，
   数到的全是裙子和腿——读数 −1404，和髋部那条带**一个数字都不差**，这才看出来。
   → 关节带与别的部件同高时，**必须按该部件自己的外接框加列窗**（`[hx−8, hx+hw+8]`）。
2. **四向 `hole_mask` 测不出"敞口缝"**。袖口与手之间的缝**朝外敞开**，
   "左右两边还有身体"的条件根本不成立，把 `WRIST_STUB` 删成 0 照样读 0。
   → 改成**只看同列上下夹心**（`vhole`）。但列窗套整只手又会去数**手指缝**
   （手一转指缝就变形，读 135/153，与袖口松紧毫无关系）→ 行窗压到腕线 `[−18, +14]`。
3. **压力姿势里"整条手臂一起转"会让末端闸失效**。arm 25° 把手整个转出了
   按静止位置取的取样框，框内一片空白，恒为 0。→ **末端关节闸要单独只转该关节。**

**验收一条闸的唯一办法是做负控**：故意把零件改坏，看它红不红。
本轮两次负控：把前臂切到 `wrist_y−12` 留 12px 裸缝 → 腕闸 34/28 不红、
但「无损切分」红了 1 项（静态缺口归无损切分管、旋转缺口归腕闸管，两闸互补）；
`WRIST_STUB=0` → 两闸都不红（重叠 2~3px 时静态无洞、旋转洞也只有 16/13），
说明**腕闸真正把关的是角度，不是塗り足し有没有**——闸值 60 卡在 40° 与 50° 之间。

### 5.13 鞋拆件 + 踮脚姿态图（**几何重采样型 + 参数驱动交叉淡化**；T24.5，2026-10-14）

这是第一件**不靠 AI 重绘**的"换姿态"零件，也是第一次用交叉淡化在两张姿态图之间过渡。

#### 一、先把方向搞对：踮脚的鞋在画面里是**变高**，不是变扁

第一版提示词和第一版引导图都按"鞋被压扁、变短"画——**全错**。
摄像机不是正侧视，是俯角 θ≈37° 的半俯视，鞋的纵向投影 = `L·sin(θ+φ)`。
脚绕趾尖抬起 φ 角，`sin(θ+φ) > sinθ` → **投影变长**。
在图像上，"绕趾尖转 φ" 精确等价于 **以地面线为原点的纵向均匀拉伸 k = sin(θ+φ)/sinθ**，
横向完全不变。所以：

- 鞋身变高 `k×`；
- 白鞋底包边（厚度 d_sole）被压扁（看上去变薄）；
- **鞋口上抬的高度 H = h_shoe·(k−1)，这个 H 就是身体要升起的高度。**

实现成分段线性映射（`tools/make_foot_parts.py: warp_rows`）：按离地距离 `d = G − y` 取源行，
`d' ≤ d_sole·ks` 段用鞋底压扁 `ks=0.65`，以上用鞋身拉伸 `ku=1.2967`，
鞋口以上整体平移 `lift=30`。源图实测：鞋口 `y_shoe=1156`、白带上沿 `y_sole=1276`、
地面 `G=1292`、`D=136`、`d_sole=16`、左右分界 `x_split=218`。

**四件产物**（画布坐标，源图↔画布偏移 +(200,68)）：

| 部件 | pos | layer | 说明 |
|---|---|---|---|
| `seg_foot_l` | [346,1180] | 62 | 常态鞋（左） |
| `seg_foot_l_tip` | [346,1150] | 64 | 踮脚鞋（左），比常态高 30px |
| `seg_foot_r` | [418,1180] | 63 | 常态鞋（右） |
| `seg_foot_r_tip` | [418,1150] | 65 | 踮脚鞋（右） |

两张姿态图的**鞋底都钉在 y=1291**（画布 1359），鞋口正好差 30px。这两条是机器校的。

#### 二、腿件要擦像素，更要**裁画布**（这一条差点漏掉）

鞋原本画在 `seg_leg_*` 里。拆出去之后腿件切线（源图 `y_cut=1150`，画布 1218）以下要擦干净，
留 38px 袜子重叠带给鞋盖住。**但只擦像素是不够的——画布也必须裁到切线。**

因为引擎的 bend 曲线是按**贴图画布**铺 0..1 的，不是按解剖位置：

| | 画布 731..1360（只擦像素） | 画布 731..1218（裁掉） |
|---|---|---|
| 脚踝那条线的 t | 0.774 | **1.000** |
| `ParamLegL` 的 tip 曲线 t² | 0.59 → 摆腿 20px 只剩 **11.6px**（少 42%） | 1.00 → **20px**，和拆件前一样 |
| `ParamKnee` 的 sine 曲线 | 0.65 → 屈膝把脚**抬离地面 2.9px** | **0** → 屈膝不动脚 |

拆件前腿件画布底边正好是鞋底（t=1 落在地面），所以这两条曲线本来就是对的；
是"擦了像素没裁画布"把 t=1 推到了地面以下 142px 的空白里，**同一个上游，两处毛病**。
裁完之后 `body_parts.json` 里的 `size` 要写回去（`make_foot_parts.py` 负责），
否则 `make_rig.py` 和 `check_assets.py` 摆位置全错。

实测（预览 `/api/param?id=ParamLegL`，scale 0.55）：v −1→+1，
袜（画布 y1190~1210）横移 36.4 画布 px、鞋横移 **40.0 画布 px** = 满额 ±20px，
两者在 38px 重叠带里的 4px 差动被鞋完全盖住（逐像素量过：重叠带内腿件外露 **0** 像素）。

#### 三、rig 怎么接：钉地靠反向补偿，换图靠 xfade

```
ParamTiptoe  →  root.dy −30  +  foot_l.dy +30  +  foot_r.dy +30
                （腿**不再**拉伸；鞋口自己长高 30px，正好接住升上去的脚踝）
groups.foot_l = {parent: leg_l, bend_follow: seg_leg_l, bend_follow_at: 1218}
xfades: {param: ParamTiptoe, in: [0.40,0.60], from: seg_foot_l, to: seg_foot_l_tip}
```

`bend_follow` 是必须的：腿是 bend_x 摆的，bend 只作用于它自己那张贴图，
不跟随的话一摆腿鞋就留在原地。取样线必须 = 切线。

**xfade 的曲线照抄 Live2D SDK 的 `CubismPose::DoFade`**（Phi=0.5、BackOpacityThreshold=0.15）：
淡出件 `a1 = 1 − w`，若 `(1−a1)(1−w) > 0.15` 则抬到 `a1 = 1 − 0.15/(1−w)`。
中点 w=0.5 时 a1=**0.70**，两件合起来盖住 **0.85**；线性淡化只有 0.75，**会漏 25% 背景**
（桌宠是透明窗口，漏的就是桌面）。单测里真渲染一帧量过这个 0.85。

**窗口为什么收到 [0.40,0.60]**：两张鞋的鞋口差 30px，交叠期一定看得见双轮廓
（官方《创建有姿势切换的动态》也只说"尽量减少"，办法是重叠区尽量小 + 轮廓羽化）。
窗口越窄，参数扫过它的时间越短。按引擎自己的波形公式复算（60fps）：

| 窗口 | 扫过的帧数 | 时长 |
|---|---|---|
| [0.25,0.75] | 6 帧 | 100ms |
| **[0.40,0.60]** | **3 帧** | **50ms** |
| [0.45,0.55] | 1 帧 | 17ms |

#### 四、动作波形：姿势类要用 pulse，不能用 bounce

`bounce = amp·sin(π·ease(t/dur))`，配 out_back 时峰值出现在 95ms，
**v>0.95 只持续 48ms** —— 鞋刚换完就换回去，姿势根本读不出来。
改成 `pulse`（冲上去**保持**，收尾交给动作自己的 `fade_out`）：
`ParamTiptoe/KneeL/KneeR` dur 0.35、`ease=out`（`param_effective` 会把值钳到
`[vmin,vmax]`，所以 out_back 的过冲反正会被削平，用 out 更干净）。
实测抬起 ≥14px **持续 693ms**，全程画面最底行恒为 747（钉地不变量成立）。

同时删掉了 tiptoe 里的 `ParamBaseY` 通道：那是给 happy 跳跃用的参数（走 `root.dy`、
**不补偿脚**，满格 40px），叠在踮脚上实测最底行 747→744，整个人浮空 3px。
官方《4.添加身体动作》写死的一条是"身体上下时脚不能离地"。

#### 五、这件事新加的闸（全部做过负对照）

`check_assets.py`（→415 项）：常态鞋/踮脚鞋都触地、鞋口抬高 = `lift_px`、
腿件切线以下清空、**腿件画布裁到切线**、常态鞋盖过切线 ≥ lift。

`selfcheck_repo.py`（→276 项）：
- `check_foot_switch`：两件齐全 / 层序（踮脚件在上）/ 同组 / `bend_follow` 与取样线 /
  xfade 的 param·from·to / 窗口又窄又在量程内（≤0.30）。
- `check_feet_on_ground`：**每个动作**按"通道幅度 × 该参数对鞋底的纵向系数"复算净位移，
  系数 = `root.dy` + `foot_*.dy` + `Σ seg_leg_*.bend_y × 曲线在取样线处的值`。
  要离地的动作必须写 `"airborne": <px>` 且数字对得上
  （happy 34 / hammered 8 / clicked 6 / sleep 4 / wave 2）。
- `check_tiptoe_grounded` 改写：有鞋拆件时断言"root.dy 与两只 foot 组 dy 等量异号
  且 = 素材的 lift_px"，并且 **ParamTiptoe 上不许再有腿的 bend_y**（旧口径已作废）。
- `check_neck_seam` 补方向判定：root 曲线（跟随件在上）要 `bend_hold_above` 平台；
  tip 曲线（跟随件在下）要求源贴图在取样线以下**已登记切掉**，且不许写平台。

`tests/test_core.c`（→653 项）：`test_xfade` 23 项，含真渲染一帧量中点合成不透明度。

### 5.14 肩关节（**不动切线，加一件压在身体底下**；G102+G108，2026-10-15）

这一节记的是"关节处露底/变细"的通用解法，腿、脖子以后照抄。

**病状两条，用户同一句话报出来的（"挥手的部件和链接没做好"）：**
- 抬手时右肩外侧跳出一块**悬空的青色三角**，底边是一条直线；
- 上臂（肩到肘）细得像根棍子，和小臂粗细不成比例。

**病因也是两条，而且都不是"素材没画"：**
1. `make_arm_parts.py` 原来有 `SHOULDER_CAP = 46`，挖袖子时**特意给躯干留了
   袖子顶端 46 行**，理由是"整块拿走肩膀就成平口"。留下的是青色袖子，
   它不跟手臂转 —— 那块三角就是它。**而"平口"这个理由是错的**：
   整条拿走之后露出来的是夹克自己的圆肩 + 袖窿
   （右肩外缘 y=330→332 / 340→333 / 360→328 / 400→315）。
2. 袖子是沿袖缝切的，上臂露出来的只有夹克身没盖住的那一条，
   逐行宽度从肩头 23px 长到肘部 68px。手臂一抬，整条楔形转出来就是"棍子"。

**解法：**
- G102 = 删掉 `SHOULDER_CAP`，整条袖子都归手臂。躯干的袖窿轮廓由
  `rim` 那段线稿描边补上。静止合成与原画的差 440 → **321**。
- G108 = **不要去改袖缝切线**（切线一刀两面，会同时破坏 G102 和静止帧），
  改成**加一件** `arm_{l,r}_root`（`root_fill()`）：
  - 逐行把袖宽补到**上臂行宽的 80 分位**（左 57 / 右 63px），到肘部自然收敛到 0；
  - 顶端 40 行 `smoothstep` 渐入，**不留水平直边**（否则转出来是一条硬边）；
  - 颜色取袖缝内侧 6px 的中位色（避开 2px 线稿），往里渐暗到 0.90，新内缘描线稿；
  - **层 95/96，画在躯干 100 底下** → 静止时 100% 被夹克压住。
  - 上臂上半段中位宽 l 38→56 / r 40→62，与前臂之比 **0.61/0.58 → 0.89/0.89**。

**三条必须记住的边界：**
- **"藏住"要靠遮挡关系，不是靠"看不出来"**。闸的判据是
  "这件的像素里没有被躯干或袖子盖住的有几个"，答案必须是 **0**。
- **逐行取"最长那一段"是错的**：袖子一行常被口袋线/下摆条切成两段
  （实测 y=480 是 (320,331)+(333,377)），按最长段的起点往里补会压到另一段真袖子上。
  要取**整行跨度**。
- **不要顺手去抹上臂贴图里那条袖缝线**。补了袖根之后它确实从剪影边变成了
  袖子中间的线，但一抹静止帧内缘就露出一圈毛糙麻点
  （`logs/asset_qa/g108_seam_ab.png`）。**静止帧忠实于原画优先于"动起来更干净"**。
  代码里留了 `ROOT_CLEAR_SEAM = 0` 和这段理由。

**闸（`check_assets.py` 的"肩关节"一类，8 项，四条负控全部精确命中）：**
`躯干上没留袖子(l/r)` ≤40px（负控 1274/1310）、`袖根静止时完全藏住(l/r)` =0（负控 47px）、
`袖根画在躯干底下(l/r)`（负控 层 145<100 为假）、
`上臂上半段不比前臂细太多(l/r)` ≥0.80（负控 0.61/0.58）。

**还没修的：** 肘部 −80° 的硬折痕（G103）—— 袖子要上网格形变，不在这一刀里。


## 六、下一步顺序（按"看得见的收益 / 风险"排）

1. ~~嘴~~ ✅ 2026-10-12（见 5.2）
2. ~~呆毛~~ ✅ 2026-10-12（见 5.3）
3. ~~前发 + 额头补画~~ ✅ 2026-10-12（见 5.4，**第一件 AI 重绘零件**）
4. ~~眉毛~~ ✅ 2026-10-12（见 5.5）
5. ~~上下眼睑~~ ✅ 2026-10-12（见 5.6；引擎加了 `eyelid` 标签 + `blink_hold`）
6. ~~手臂关节（G4c）~~ ✅ 2026-10-12（见 5.7；抬手上限从 8° 提到 70°）

7. ~~侧发两缕 + 后发~~ ✅ 2026-10-13（见 5.9；重绘脸颊/耳/下颌 + 两段摆链）

8. ~~眼线拆件（G4m）~~ ✅ 2026-10-13（见 5.11；脸上的睁眼已挖成眼窝皮肤，
   眨眼改成"眼眶压扁 + 眼线下滑"，灰幽灵消失）

9. ~~手腕 / 裙下大腿（G4c2）~~ ✅ 2026-10-13（见 5.12；四件臂 → 六件臂，
   手腕 ±22°（安全 ≤40°）；裙下大腿归位到腿件，腿改 bend ±20px 零露底）

10. ~~I/U/E/O 四个音素口型（T2.1.3）~~ ✅ 2026-10-13（见 3.9；不是加五个新参数，
    而是一张「音素 → `ParamMouthOpenY` × `ParamMouthForm`」表 + 两档平滑；
    `ParamMouthForm` 的 bind 从象征性的 ±8% 提到 ±22/26% 并把上唇线锚点挪到中点，
    い/え 真能咧开、う/お 真能撅圆）

11. ~~表情与口型的叠加口径~~ ✅ 2026-10-13（见 3.10；口型排在表情之后，
    表情补上 multiply 混合）

12. ~~验收反馈的四个真 bug（G39）~~ ✅ 2026-10-13：① 睡醒还闭眼（`blink_force` 当年写成 bool，
    −1「交回自动」被当成真）；② 关掉自动眨眼就全闭眼（绘制判断里混进了 `blink_enabled`，
    闭眼件跳过淡化直接盖住睁眼件）；③ 张嘴了微笑还在（口型接管权重恒定 → 改成随
    `viseme_activity` 缩放，权重 0.8→1.0，满力说话口型独占、小声时笑意透出来）；
    ④ 说完话嘴角抽一下（`viseme_clear` 硬切 → 平滑松口 + 整句专用 release 8/s，
    另给"要立刻清零"的场合留 `viseme_reset`）。证据图 `logs/asset_qa/_expr_viseme_sheet.jpg`

13. ~~笑眼素材（`ParamEyeLSmile` / `ParamEyeRSmile`）~~ ✅ 2026-10-13（见 3.11；
    AI 重绘山型 ∩ 笑眼脸 → 闭眼那条流水线 `--variant smile`；笑眼隐含闭眼、谷型闭眼件让位；
    新表情 happy。合规表 ✅34 → **✅36**，只剩瞳形/眉形两类共 3 项缺素材）

14. ~~18 个动作从部件通道迁到参数通道~~ ✅ 2026-10-13（见 3.12；197 条几何通道 → 160 条参数通道，
    合规表里最后一个结构性偏差 🟠 清掉；顺带补 `ParamEyeBallForm`，✅36 → **✅37**）

15. ~~动作 fade 换官方正弦 + 每个动作自带 FadeOutTime~~ ✅ 2026-10-13（见 3.13；
    `z_ease_sine = 0.5−0.5cos(πt)` 对齐 `CubismMath.getEasingSine`，
    收尾从"W_PULSE 里硬写 0.15 秒"升成动作级 `fade_out`，循环动作不收尾；
    顺带修掉一个淡出中的旧动作会闪满值的鬼影 bug）

16. ~~裙摆接摆链~~ ✅ 2026-10-13（见 3.14；照 Hiyori 做成横摆+纵摆两条独立通道，
    physics 新增参数输入，顺带修掉"形变器吃掉 bend"和"只认第一张网格"两个渲染 bug）

17. ~~眉形 ParamBrowL/RForm~~ ✅ 2026-10-13（见 3.15；合规表最后两个 ⬜ 清掉 → **✅39 / ⬜0 / ➖4**，
    41 项里凡是这个角色适用的全部实现且有闸门。不需要新素材）

18. ~~鞋拆件 + 踮脚姿态图（T24.5）~~ ✅ 2026-10-14（见 5.13；四件鞋 + 参数驱动交叉淡化，
    引擎加 `xfades`；顺带修掉"只擦像素不裁画布"导致的摆腿少 42%、屈膝把脚抬离地面两处毛病）

19. **下一件：网格顶点级编辑（G15）**，之后是 physics 输出参数化（G44）、
    motion3 贝塞尔段、cdi3 导出。
    （注：排期里一度写着"LipSync 接 TTS 包络 G19"——**那件 2026-10-12 就做完了**，
    记作 A4：`tools/make_lipsync.py` 出 30fps 包络 + 音素序列，39 条台词在库。
    GAPS 里 G19 这个号是"通知中心"，两者撞号，已在 GAPS 里标注。）

每一件的验收关卡都一样：`make test` 全绿 → `check_assets` 全过 →
`make smoke`（互动/动作端到端）全过 → 预览抓帧人工看 → 才算入库。

### 5.15 嘴的开口量 & 袖缝内缘（**@2x 换算要连绑定一起换 / 边界定在目标色最内侧**；G111+G112，2026-10-15）

这一节是两件事，但共同的教训只有一条：**"看不见"不等于"没问题"**。
两处毛病在静止帧上都是 0 像素可见，一动就全跑出来了。

#### A. 嘴 —— `scale` 有两种语义，换高清素材时只减一半是错的

`zrig` 的 `compute_draw_state` 里：

```c
part_sx = p->scale_x + (r->p_sx[mi] - 1.0);        /* 数组 scale：加性 */
part_sy = p->scale_y + (r->p_sy[mi] - 1.0);
zimg_make_matrix(lm, pos_x, pos_y, p->scale * part_sx, p->scale * part_sy, ...);
/*                                 ↑ 标量 scale：乘性                     */
```

- 标量 `"scale": s`：最终 = `s × p_s`。素材 ×2 + `s ÷2` ⇒ **任意 `p_s` 下都等价**，绑定不用动。
- 数组 `"scale": [sx,sy]`：最终 = `scale_y + (p_sy − 1)`。基准 ÷2 了、增量还是 1x 口径
  ⇒ **形变整整 ×2**。

T30.1（`d83e7a5`）只做了前半句，于是：

| | 素材高 | 基准 sy | OpenY=1 的 bind | 开口 |
|---|---|---|---|---|
| 1x（`415486d`） | 22px | 0.0545 | 0.895 | **20.9px** ✅ |
| @2x 漏换算（`d83e7a5`） | 44px | 0.02725 | 0.895 | **40.6px** ✗ |
| @2x 换算对（本轮） | 44px | 0.02725 | **0.4475** | **20.9px** ✅ |

开口的锚点 `anchor=[0.5, 0]` 钉在笑线中点（canvas y=316）、**只往下长**，
所以开口一翻倍，下沿就从 337 掉到 357 —— 下巴在 **340**，于是成了一条压到脖子上的黑块。
talk(amp 0.833) 同理：34px vs 17.6px，嘴的视觉中心下移 ~8px = 用户说的"偏下一点"。

落点只有一个：`make_rig.py` 的 @2x 段。它现在同时做三件事 ——
换 `file`、减 `scale`、**减数组 scale 件上的 sx/sy 绑定并打 `hires_halved` 标记**，
另外有一条断言拦住"动作轨直接写部件级 sx/sy"（那条路绕得过换算）。

#### B. 袖缝 —— 羽化出来的外侧像素属于邻居，不属于自己

切袖子原来是「青色掩码 → dilate 2 → `soft()` 羽化 2」，于是袖片内缘**带了 2px 夹克白**
（95%~100% 的行都有）。静止时它正压在夹克上，一个像素都看不出来；手臂一转就跟着甩出去，
在白夹克和青袖之间显出一道亮白细条。

定性过程值得记（LESSONS 130）：颜色证据只能缩小嫌疑（那道白的 RGB 恰好等于预览背景
斜纹的两色之一，一度判成"漏背景"），**最后靠层属消去法定的案** ——
把 `arm_r_upper` 的 opacity 调成 0，那几个白点立刻变青。

修法 `seam_trim()`：逐行取**最内侧青色**，往内再留 `SEAM_KEEP=2`px 线稿
（那条暗缝线原画就有，转开后读作袖子上的折痕；**抹掉它试过并否掉了**，见 5.14），
再往内一律裁掉。两条保险：

- `cap` 只数**实心**像素（alpha ≥ 0.35）。拿"所有 alpha>0"去数，羽化尾巴能长到 6~8px，
  几乎每行都超限 → 整条袖子只裁 9px，等于没裁。
- 前臂腕上 `SEAM_CUFF_SKIP=36` 行整段不碰 —— 袖口那三道白条没有"内缘青色"可依，
  裁了会把袖口咬掉（实测静止合成少 8px，闸直接红）。

判"是不是青色"必须用**色相**（`g-r>20 && b-r>10 && g>120`），不能用到 `TEAL` 的曼哈顿距离：
灰过渡像素 `(191,178,181)` 到 `TEAL` 只有 96，用距离会被当成青色，裁不干净。
而且做减法前**必须 `.astype(int)`** —— uint8 回绕让白的 `g-r` 算成 253，整条逻辑静默失效（LESSONS 128）。

效果：白楔 surprised **155px→13px**、wave **80px→5px**（残留是单像素抗锯齿）；
静止合成差 321→**421**，"无损切分"仍然 **0 像素丢失**。
