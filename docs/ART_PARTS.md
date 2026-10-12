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
| 1 | 后发 `hair_back` | 头转动时后发要晚一拍跟上 | `ParamHairBack` | 形变 + 惯性 | ⬜ |
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
| 12 | 上唇/下唇 `lip_up`/`lip_dn` | 开口度与口型 | `ParamMouthOpenY`、`ParamMouthForm` | 形变 | 🟡 只有"张嘴"一张贴图 |
| 13 | 口内（舌/齿/口腔） `mouth_in` | 张嘴后要有东西露出来 | 随 `ParamMouthOpenY` | **遮罩** | ⬜ |
| 14 | 鼻 `nose` | — | — | — | 🟡 并在脸底 |
| 15 | 前发 `hair_front` / 侧发 `hair_side` | 压在脸上，摇头时摆动 | `ParamHairFront`、`ParamHairSide`、`ParamHairFluffy` | 形变 | ⬜ |

### 2. 身体

| # | 零件 | 对应官方参数 | 引擎能力 | 状态 |
| --- | --- | --- | --- | --- |
| 16 | 躯干 `torso` | `ParamBodyAngleX/Y/Z`、`ParamBreath` | 形变 | ✅ `seg_torso` |
| 17 | 肩 `shoulder_l/r` | `ParamShoulderY` | 旋转 | ⬜ 并在躯干 |
| 18 | 上臂 `arm_?_upper` | `ParamArmLA/RA` | **旋转枢轴** | 🟡 `seg_arm_?` 是整条手臂 |
| 19 | 前臂 `arm_?_fore` | `ParamArmLB/RB` | **旋转枢轴（肘）** | ⬜ ← 现在做不出"抬手"的根因 |
| 20 | 手 `hand_l/r` | `ParamHandL/R` | 旋转 | ⬜ |
| 21 | 胸 `bust` | `ParamBustX/Y` | 形变 | ⬜ |
| 22 | 裙/下摆 `skirt` | 随 `ParamBodyAngleX` | 形变（tip 曲线） | ⬜ |
| 23 | 腿 `leg_l/r`、脚 `foot_l/r` | `ParamBaseX/Y` | 旋转 | 🟡 `seg_leg_?` 整条 |

图例：✅ 已拆并接进 rig ｜ 🟡 存在但没拆到位 ｜ ⬜ 没有

---

## 二、每个零件必须满足的三条硬性要求

1. **画全**：被别的零件挡住的部分也要有像素。眼球要画成完整的圆（包括藏在眼皮下的上半部分），
   手臂要画到腋下，裙下的大腿要画出来。缺这部分，一动就露底。
2. **自己是一张独立 PNG**，透明背景，不带别人的像素（眼球图里不能有眼线）。
3. **声明自己的遮罩与层序**：`rig.json` 里写 `"mask": "<遮罩部件 id>"`，
   且遮罩部件的 `layer` 必须小于被裁切部件（否则加载直接报错，不会悄悄画错）。

---

## 三、引擎已具备 / 还缺的能力

| 能力 | 用途 | 状态 | 位置 |
| --- | --- | --- | --- |
| 仿射变换（位移/缩放/旋转） | 整块零件动 | ✅ | `zimg_draw()` |
| 网格弯曲（bend + 四种曲线） | 呼吸、侧摆、裙摆、挥手 | ✅ | `zimg_draw_warp()` |
| 组层级 + 枢轴 + 形变跟随 | 头跟着身体走 | ✅ | `zrig.c` `group_matrix` / `bend_follow` |
| **遮罩（clipping mask）** | 眼球不滑出眼眶、口内不露到脸外 | ✅ **2026-10-12** | `zimg_composite_masked()` + `parts[].mask` |
| 眨眼五态机 | 自动眨眼 | ✅ | `zrig.c` `blink_update` |
| 视线跟随 | 眼球看向鼠标 | ✅（标签 `gaze`） | `zrig.c` |
| 自由变形器（FFD，按控制点拉网格） | 眼睑开合、嘴形连续变化 | ⬜ | 下一步 |
| 旋转变形器（骨骼链：肩→肘→腕） | 抬手、挥手不拉皮 | ⬜ | G4c 之后 |
| 物理摆动（头发/裙子惯性） | 甩头时头发晚一拍 | ⬜ | 可用简化弹簧 |

---

## 四、生产流程（这就是"Live2D 教程"在我们这边的落法）

Live2D 官方教程的顺序是：**分层画稿 → 导入 → 建网格 → 加变形器/参数 → 绑动作**。
我们没有 PSD 分层原稿（只有一张合成图），所以多一步"还原分层"：

```
① 还原分层   tools/make_body_parts.py   身体按关节切段 + 重叠带羽化（过渡方案）
             tools/make_eye_parts.py    眼睛拆成 眼眶/眼白/眼球/眼线（已达标）
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

## 五、眼睛零件（已完成，可作为后续零件的模板）

产物（`characters/xiaoxun/forms/teen/sprites/`）：

| 文件 | 内容 | 在 rig 里 |
| --- | --- | --- |
| `eye_?_socket.png` | 眼眶剪影（纯白+软边） | `layer 216/226`，`mask_only: true`（只当遮罩，不画） |
| `eye_?_base.png` | 原贴图，眼眶内填成眼白色 | `layer 217/227` |
| `eye_?_ball.png` | 完整的虹膜圆（上半部分按列补全） | `layer 218/228`，`mask: eye_?_socket`，标签 `gaze` |
| `eye_?_lash.png` | 眼线睫毛 | `layer 219/229` |

实测数据（`sprites/eye_parts.json`）：虹膜半径 13.4 / 13.6 px，眼眶 27×30 / 25×31 px，
眼球可动范围 ±5/±4 px（允许被眼眶裁掉一点——这正是遮罩的意义）。
新动作 `look_around`：只有眼球在动，眼白与眼线不动。

验收证据：`logs/preview_check/eye_zoom.png`（8 帧眼球位移，瞳孔始终压在眼眶内）。

---

## 六、下一步顺序（按"看得见的收益 / 风险"排）

1. **嘴**：`mouth_in`（口腔+舌+齿）+ 上下唇，用遮罩裁口内 → 说话时真的会张口，不再只是贴一张"张嘴图"。
2. **眉**：两条眉独立 + 位移/旋转 → 表情立刻有层次（成本最低、收益最大的一件）。
3. **眼睑**：上下眼睑独立 + FFD → 半眯眼、笑眼；此时才能退掉"闭眼贴图淡化"。
4. **手臂关节（G4c）**：上臂/前臂/手分开 + 重绘腋下与袖口 → 真正的抬手；目前挥手幅度被卡在 60px。
5. **头发**：前发/侧发/后发 + 简化弹簧 → 动起来才像活的。

每一件的验收关卡都一样：`make test` 全绿 → `check_assets` 全过 → 预览抓帧人工看 → 才算入库。
