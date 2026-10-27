# 交接文档（给下一个代理）

> **当前任务入口（2026-10-27；分支元数据纠正）**：本文件下方主体是 2026-10-11 的旧交接，分支信息与任务状态已过期。当前 Arena 活动分支为 `arena/8f8b86a5-zhuochong`，HEAD `43f5514`；远端 `arena/ba836be0-zhuochong` 只与该 HEAD 同提交，不能据此切换或重置分支。先读 [`项目整体接手审阅记录`](PROJECT_TAKEOVER_2026-10-27.md) 与 `docs/memory/WORKFLOW.md` 的“铁律 0：用户要求永远排第一”；若处理小寻 T67.7，再读 [`完整交接`](T67_7_HANDOFF_NEXT_AGENT_2026-10-27.md) 与 [`沙箱运行手册`](T67_7_SANDBOX_RUNBOOK.md)。不要照搬下方旧分支指令，也不要把项目缩成美术任务。

更新：2026-10-11 ｜ 分支：`arena/b3359546-zhuochong` ｜ 项目根：仓库根目录
**先读 `docs/PROJECT_SPEC.md`（当前有效规格），再读本文件（怎么继续）。**

---

## 〇、一句话现状

Windows 原生 C 桌宠的**基础软件已经能跑**（透明窗、像素穿透、拖动、托盘、状态机、眨眼、摸头/锤击、
空闲入睡、缩放、换形态/换服装机制、配置与 schema、96 项单测、一键自检、真实引擎的沙箱预览）。
**下一步是素材与 UI**：小寻的完整拆件（表情集/身体分段）、二次元 UI、以及 7 角色 × 4 形态。

---

## 一、立刻可运行的命令

```bash
make test                     # 单元测试（[测试锁]，必须全绿）
make preview                  # 沙箱预览：http://localhost:5173（C 引擎实时渲染）
make win                      # 交叉编译 Windows exe（zig cc，无需装 MinGW）
make pack-win                 # 打包 dist/windows/zhuochong/（exe + config + schemas + characters）
bash scripts/selfcheck_all.sh # 一键自检
bash scripts/fetch_references.sh   # 拉取六个参考项目源码（只查阅，不入库）
```

Windows 运行方式见 `docs/PROJECT_SPEC.md` 第一节表格。

---

## 二、六个参考项目（用户要求：遇到问题先去源码里查，不要凭猜测）

1. BongoCat（C + SDL3 + OpenGL）https://github.com/vladelaina/BongoCat — **AGPL-3.0，只学思路**
2. BongoCat（Rust + Live2D + 全局输入）https://github.com/ayangweb/BongoCat — Apache-2.0
3. ds-local-pet（PySide6）https://github.com/QCYTSN/ds-local-pet — MIT
4. VPet（WPF）https://github.com/LorisYounger/VPet — Apache-2.0
5. airi（Web + Live2D/VRM）https://github.com/moeru-ai/airi — MIT
6. Live2D CubismWebFramework https://github.com/Live2D/CubismWebFramework — 框架源码许可；
   **Cubism Core 为专有，不引入**；年营收超 1000 万日元商用需按 Cubism SDK Release License 授权

已查阅并落地的结论、以及"下一步该查什么"，都写在 `docs/REFERENCE_NOTES.md`（精确到文件与函数）。
拉取脚本：`scripts/fetch_references.sh`。

**规划文档索引（2026-10-17 新增两份，动手前必读对应的那份）**：

| 文档 | 管什么 | 什么时候必须读 |
| --- | --- | --- |
| `docs/PHYSICS_PLAN.md` | **物理底座 2.0（T47）**：现状盘点（35 条摆的全参数表）、与官方算法的九行差距表、T47.1~T47.8 的做法与验收 | 碰 `src/core/zrig.c` 的 `zphys` / `physics_update()` 之前 |
| `docs/PRESENCE_PLAN.md` | **生命感（T48~T51）**：三级视线跟随、兽耳娘模式、外设四模式（bongocat 类）、表情五档、12 条可吸收能力排序 | 做跟随 / 外设 / 耳尾 / 表情之前 |
| `docs/AGENT_PLAN.md` | **AI 工作能力（T52~T56）**：MCP 工具层与网关策略、四层记忆与上下文工程、沙箱与长时任务、trace/eval/预算、调度与屏幕感知分级 | 做工具 / 记忆 / 任务机 / 屏幕感知之前 |
| `docs/memory/REQUEST_LEDGER.md` | **需求接收台账**：用户说过的每件事 → 落点 → 状态，含"还欠着的六项" | 每轮开工前扫一眼；用户问"记住了吗"直接给它 |
| `docs/INTERACTION_PLAN.md` | 交互与输入的既有口径（§2.6 键盘与全局输入） | 做 T48 之前先看它，不要另起炉灶 |
| `docs/FORM_MATRIX.md` | 形象矩阵三轴（年龄 / 取景 / 姿态）—— 用户已封板 | 加新形态 / 新取景之前 |

---

## 三、代码地图（先看哪里）

| 文件 | 作用 | 改它之前要知道 |
| --- | --- | --- |
| `src/core/zpet.c` | 桌宠行为大脑（平台无关）：交互、入睡、形态、服装 | Windows 与预览层都用它，改这里两边同时生效 |
| `src/core/zrig.c` | 立绘引擎：组/部件/通道/区域/眨眼/视线 | 结构体是私有的；接口在 `zrig.h` |
| `src/core/zsm.c` | 动作状态机（优先级/可中断/过期） | 语义对齐 ds-local-pet，改动要同步单测 |
| `src/core/zconfig.c` + `schemas/` | 配置加载与校验 | 新增配置项要同时改 schema，否则自检会报缺 schema |
| `src/win32/zw32.c` | 透明窗、穿透、托盘、菜单、热键、拖动、空闲检测 | 这是唯一依赖 Windows API 的文件（除入口外） |
| `src/headless/main_headless.c` | 沙箱预览 HTTP 服务 | 只做"显示与输入"，不许在这里加行为逻辑 |
| `tools/*.py` | 素材流水线：抠图→拆件→生成 rig.json | 坐标全部由脚本量取，**不要手写魔法数字** |
| `tests/test_core.c` | 96 项单测 | 新功能必须补测试，`selfcheck_all.sh` 会卡 |

---

## 四、素材流水线（生成新素材时的标准动作）

```bash
# 1) 生成设计图（纯色背景，推荐洋红 #FF00FF；画布 2:3；全身正面）
#    直接把设计图放进 characters/<角色>/design/
# 2) 抠图 + 缩放 + 落画布 + 验收报告（内含洋红/白边残留检测、色卡取样）
python3 tools/prepare_sprites.py --character xiaoxun --form teen \
    --sheet characters/xiaoxun/design/design_sheet_short.png \
    --canvas 848x1360 --height-ratio 0.95 \
    --report characters/xiaoxun/forms/teen/sprites_report.json
# 3) 拆件（眼睛/嘴/头）。坐标从原图量取（可用 4 倍放大 + 网格图确定）
python3 tools/make_parts.py --character xiaoxun --form teen \
    --eyes "left=96,178,215,246;right=228,178,347,246" \
    --mouth "212,252,256,275" --root .
# 4) 由素材实际尺寸生成 rig.json（坐标自动对齐，不要手改坐标）
python3 tools/make_rig.py --character xiaoxun --form teen --canvas 848x1360 --root . --name 小寻
```

**验收口径**：`sprites_report.json` 里 `magenta_residue_pixels` 与 `white_residue_pixels`
要足够小（当前 48 / 494，阈值 200 / 800，自检脚本会卡）。不通过就重生成，最多三次，仍不通过则记录原因不入库。

### 已知失败路线（旧交接文件第九节，务必不要重复）
1. 从整张图抠眼睛闭合层（残留与横带）→ 本项目的做法：**眼睛单独拆件**（`eye_open_*` / `eye_closed_*`
   由 AI 生成或按几何裁剪），眨眼时交叉淡化；AI 表情集到位后直接换文件即可升级。
2. 用生成的闭眼图覆盖底板（擦不干净）→ 同上。
3. 羽化椭圆眼皮（边缘色差）→ 禁止。
4. 颜色分割抠袖/抠部件 → 碎片、缺肩部；必须**单独生成部件**。

---

## 五、下一步（按用户既定计划）

1. **素材与 UI 拆分（当前）**：
   - 小寻少女形态：生成 表情集（平静/微笑/开心/害羞/生气/难过/惊讶/思考/困倦/说话 AEIOU/
     半闭/全闭/眯眼）与头部、身体分段（前后发、手臂、上下半身、关节补图）、呆毛、鲸鱼发夹。
   - 每个部件入库前必须跑第 4 节的流水线与验收。
   - 眼睛拆件 → 拆出虹膜并打 `gaze` 标签 → 视线跟随**自动生效**（代码已就绪）。
2. **二次元 UI**：按旧交接文件第五节的"两套风格（柔和手绘 / Q 版糖果）"出设计稿 → 用户确认 → 再实现。
   实现方式是 `config/ui.json` + 生成图资源；**不得使用 emoji / 程序画图 / SVG**。
3. **其余 6 个角色 × 4 形态**：每个角色一包，复用同一 rig 结构与骨骼命名。
4. **语音**（airi 的四段结构）、**社交**（每项独立开关，默认全关）、**Web 工作区 + API 网关 + Token 记录**（只存本机）。
5. **物理底座 2.0（T47，2026-10-17 新立，优先级被用户顶到很高）**：
   现在的摇物是 1D 弹簧、输出"滞后像素"，**输入不动就彻底不动** —— 用户已经指出
   「目前还没有真实的物理效果」，这个判断是对的。换成官方口径的 2D 粒子摆链，
   顺序是 T47.1 内核 → T47.2 输出适配 → T47.3 重力与风，详见 `docs/PHYSICS_PLAN.md`。
6. **生命感三件（T49 三级跟随 / T50 兽耳娘与情绪耳尾 / T51 生气等表情）** 与
   **T48 外设模式（bongocat 类键盘/手柄）**，详见 `docs/PRESENCE_PLAN.md`。

---

## 六、约束与纪律（用户明确要求）

- **全部可自定义**：新增角色/形态/服装/配饰/动作/主题/模块都不改核心代码；改配置文件即可。
- 每个配置文件带 `schema_version`；错误必须能指出"文件 + 行 + 字段 + 原因"，不能崩溃也不能静默忽略。
- 功能模块默认**全部关闭**，每个可设 token 上限。
- 只做原创形象，不照搬商业角色；参考项目不复制代码（尤其 AGPL 的第 1 项）。
- 汇报必须标测试标签：`[测试锁] / [沙箱实测] / [需真机]`；**不替用户宣布真机项完成**。
- 预览只通过 Arena 预览面板打开，不给外部拼接域名。

---

## 七、当前已知限制 / 欠账（下一个代理必须知道）

1. 小寻的 `body_full.png` 是**整身单张**图层：手臂、上下半身尚未分段，因此挥手、弯腰、走动做不了。
   `rig.json` 里已为 `chest` / `head` 组预留了父子结构与全部动作，**只需要拆件后替换部件文件**。
2. `eye_closed_*.png` 目前是"由上眼睑弧线压扁"得到的几何占位（可见但不如手绘），
   表情集到位后替换文件即可，配置不用改。
3. `mouth_open.png` 是嘴部整块裁剪（张嘴占位），说话动作靠透明度闪烁；后续应按 AEIOU 拆 5 张嘴。
4. 只有 1 个形态（teen）：萝莉/青年女性/Q 版需要各自重绘并各建一个 `forms/<id>/` 目录。
5. 服装机制可用，但除 `default`（常服，等价于原图）外还没有新素材。
6. UI 界面（气泡、按钮、图标、托盘菜单的美化）全部未开始；托盘菜单目前使用系统原生控件。
7. 真机项未验证：透明窗、穿透手感、光标、托盘图标、动画流畅度、Windows 持久化。
8. 沙箱预览的日志曾出现"无法打开日志文件"（已修：`z_dirname` 会原地修改缓冲，别复用同一路径变量）。
