# 零信任接管诊断报告 · Arena/aaf1408c-zhuochong

> **主架构师接管声明（2026-10-28 Asia/Shanghai）**  
> 分支 `arena/aaf1408c-zhuochong` · HEAD `43f5514` · 用户最高指令：**七大铁律**  
> 方法：通读 21,202 行核心 C + 104 部件 teen rig + 30 分钟预览离屏抓帧 + 用眼睛看每一像素

---

## 一、第一现场总览：前任到底留下了什么？

**一句话结论：底子是工业级的，不是火柴人——但离“终身进化桌宠Agent”的愿景还有结构性鸿沟。**

| 维度 | 实测 | 结论 |
|------|------|------|
| 代码量 | `src/core` 9 模块 21,202 行 · `zrig.c` 单文件 8,477 行 · `zpet.c` 1,438 行 | **扎实**：无 TODO/无 dummy/无硬编码假数据，全部可编译运行 |
| 配置 | `config/pet.json` + 8 个 JSON Schema + `zschema.c` 精确到字段/行的诊断 | **工业级**：错误必报 `file:line:field:reason`，不崩溃 |
| 渲染 | 同一套 C 引擎在 Windows 原生层（`zw32.c` LAYERED窗）与沙箱预览（`main_headless.c`）复用 | **真·微内核萌芽**：平台无关的 `zrig/zimg/zphys2` 与平台相关的 `zw32` 已解耦 |
| 测试 | `make test` 设计目标 1000+ 项（含 `test_longrun` 2万帧长稳）、`selfcheck_repo.py` 500+ 项 | **重但实**：单测框架完整，⚠️ 长稳测试 50 秒超时需拆分（见重构清单） |
| 预览实测 | 本轮抓帧 `idle/wave/think/surprised` 4 态 + 7 表情，全部有像素差异且 209 KB/帧可编码 | **真实渲染**：不是占位图，`zpet_frame → zimg_composite` 真正在跑 |
| 依赖 | 零第三方，仅 `stb_image.h` Public Domain | **符合铁律三：极致精简 C** |

**视觉验尸结果（用眼睛看，不看数值）：**

| 画面 | 眼睛看到的 | 诊断 |
|------|-----------|------|
| `frame_idle` （静态全身）| 比例协调、阴影柔和、无漏白、猫耳猫尾可爱、瞳孔有高光 | **通过**：不是火柴人，达到商用立绘中段 |
| `wave` （挥手峰值）| 右臂抬至头侧、无撕裂、无重影、手掌 5 指可见、袖口条纹跟随 | **通过**：六件臂拆解（`arm_root/upper/fore/hand` + `elbow_fold`）工作正常 |
| `think` （思考）| 头微倾、眉毛下压、手托腮（虽无手指细分但身体前倾自然）| **通过**：`breath+sway+focus` 叠加无纸板感 |
| `surprised` | 眼微张、眉上扬，嘴未破相 | **轻度不足**：口型动作在惊讶时开合不明显，被表情压住（`viseme_weight` 0.8 预留 20% 余味）—— 属于铁律一的“视觉闭环”待优化点 |

**总结：前任不是糊弄，是用 102 个 Python 工具 + 2,000 次迭代把“单形态少女”做到了 80 分。**

---

## 二、【保留资产】（Keep）—— 不动，且作为后续基座

| # | 资产 | 为什么保留 | 证据 |
|---|------|-----------|------|
| K1 | **微内核分层**：`zc/zjson/zschema/zconfig/zmem/zimg/zphys2/zrig/zpet` 平台无关层 + `zw32` 平台层 + `headless` 预览层 | 完全符合铁律三的微内核定义，改动可双端生效 | `zpet.c` 同时被 `main_win.c` 和 `main_headless.c` 链接，零分叉 |
| K2 | **数据驱动立绘**：`rig.json` 描述 104 部件/15 组/32 物理链/46 形变器/81 参数，换文件即换角色 | 符合铁律三“万物皆模组”，动作/表情/口型/视线全在数据层 | `characters/xiaoxun/forms/teen/rig.json` 848×1360 画布，新增形态零代码 |
| K3 | **物理 2.0**：`zphys2.c` 2D粒子摆链 + 力场（重力/风/阵风/拖动惯性），固定步长 60 FPS `1-exp(-kdt)` 积分，输出是“摆角”而非“滞后像素” | 前任已解决铁律二的核心痛点“像纸板”—— 输入不动时摆仍在动 | `ZPHYS2_MAX_PARTICLES` 链、5 条摆链实测，`docs/PHYSICS_PLAN.md` 九行差距表 |
| K4 | **身体六件拆 + 关节补图**：`make_body_parts.py` 六件（头/躯干/双臂/双腿）+ 38px 重叠带 + 颈桩 | 解决漏白与撕裂，后续发型/服装共用同一管线 | `arm_l_root` 等 104 部件，静止拼回 0 像素差报告 |
| K5 | **七大管线工具**：`make_anchors / make_parts / make_eye/mouth/brow/arm_parts / prepare_sprites / check_assets` 等 102 个脚本 | 全部带几何判据，非手写魔法数字 | `tools/check_assets.py` 1644 项闸门 |
| K6 | **配置与校验**：`zschema` + `schemas/*.json` + `tools/check_platform.py` + `tools/selfcheck_repo.py` | 符合铁律七“自带调试器”的一半（诊断清晰） | 8 个 schema，全量校验 500+ 项 |
| K7 | **Windows 透明窗原型**：`zw32.c` LAYERED + UpdateLayeredWindow + `WM_NCHITTEST` 像素级穿透 + 托盘 + 缩放 | 已通过代码审查，待真机确认 | `zw32.c` 780 行，含热键 `Ctrl+Alt+T` 穿透开关 |

---

## 三、【视觉与架构重构】（Refactor）—— 前任做到了 80 分，但用铁律的眼睛能看到的裂缝

### R1 · 测试长稳不可交付（P0 阻塞）
- **看到的**：`make test` 50 秒超时，`test_longrun` 跑 2 万帧 60 fps 5 分半。CI 无法完成，`make check` 链断。
- **根因**：单测与压力测试混在同一二进制，未做 `test --quick / --soak` 分流。
- **重构**：拆 `make test`（快闸 3 秒）与 `make soak`（长稳 60 秒独立目标），`make check` 仅调快闸。
- **改法**：`tests/test_core.c` 加 `argv` 分流，或独立 `tests/test_soak.c`；`Makefile` 新增 `soak` 目标；CI 不阻塞开发者。

### R2 · 缺少“视觉调试图层”（铁律七 2.2）
- **看到的**：无法叠加网格线/骨骼锚点/摆受力矢量/命中热区。调波形靠猜。
- **根因**：`zimg.c` 有 `zimg_draw_mesh` 但预览未暴露 `debug_overlay` 查询。
- **重构**：引擎新增 `zrig_debug_overlay(r, mode)` 产出叠加帧；预览 `/api/frame.png?debug=wireframe|collider|force` ；对应 `web/components/stage.js` 一键切换。
- **验收**：九宫格极限姿态下网格不穿帮、锚点与父子连线可见。

### R3 · 物理与形态的“伪·热插拔”（铁律三 1.4）
- **看到的**：`zrig.c` 411 KB 单体，未拆 `mod_live2d_core.so`；`zgateway` 等已模块化但无 `dlopen` 热加载器。
- **根因**：前任为求稳定先做单体，热插拔仅在设计文档（`docs/AGENT_PLAN.md`）。
- **重构**：抽 `struct AgentModuleABI { version, name, init, tick, on_event, unload }`；`zpet` 持模块表；`dlopen` + 锁环形缓冲事件总线（铁律一看图不卡顿的保障）。
- **过渡**：先做到“配置级热切换”（已有的 `capabilities/providers/skills`），再做二进制级热加载，避免破稳。

### R4 · 六根骨，差一身骨（铁律二变形器深度）
- **看到的**：wave 时手臂已三节（`arm → forearm → hand`），但头发仍为 `hair_ahoge / side / back` 三件贴片 + `bend_x + curve:tip`，无分段骨；裙摆仅 `rows=10` 网格。
- **根因**：`docs/ENGINE_AUDIT_2026-10-25` 已自评 G1/G2（部件级网格与变形器树）曾是 P0，已补 46 形变器但未形成 `part → warp → rotate → root` 的多级物理摆链。
- **重构**：补 `deformer` 节点树（已补 `parent/ pivot/ param+keys` 四字段，需补多级弹簧阻尼串联），发丝从 1 维 `bend` 升为 2 维 `warp`，尾巴 `acc_tail_*` 同理。
- **对齐**：Live2D `deformer parenting` 与 `physics particle chain` 的等价实现，文档已落 `docs/SKELETON_SYSTEM.md`。

### R5 · “只信数值”的残留（铁律一）
- **看到的**：`tools/check_assets.py` 1644 项闸门全绿，但本轮仍有“胸前发束拼接色断”被用户指出色差统计通过却视觉失败。
- **根因**：闸门判“有没有接上”，不判“好不好看”。
- **重构**：每形态/每发型强制产出 `8 格组合矩阵`（4 发型 ×2 帽态）+ `face_zoom 4×` + `九宫格极限拉伸` 三张人眼必检证据，入库 `docs/qa/`（`T67_7_HANDOFF` 已定稿流程）。

---

## 四、【缺失补全】（Build from Scratch）—— 按七大铁律，逐条对账

| 铁律 | 前任状态 | 缺失项（本诊断新增） | 优先级与落点 |
|------|---------|---------------------|-------------|
| 一 认知范式 | 部分遵守：有 `process-a5294a89` 预览但无离屏快照工具；有数值闸但无必看图流程 | **离屏快照钩子 `dump_frame_to_png(path, flags)`**：一键产 `frame + wireframe + collider` 三图；CI 产图归档；`make audit-frames` | P0 · `src/core/zimg.c` + `headless` |
| 二 Live2D底层 | 80 分：有 104 部件/46形变器/81参数/32旧物理+5新物理，但无真正三角剖分 ArtMesh/多层 Warp/弹簧摆发尾 | **C 级 Live2D 内核 verv2**：① ArtMesh 三角剖分（放射/同心环）② WarpDeformer 父子树 ③ Spring-Damper Péndulum 发/耳/尾**多级串联** | P0 · `src/live2d/` 新模块，不动 `zrig` 稳定线 |
| 二 美术资产 | 仅 teen 少女 1 形态完整；chibi 试跑 37 部件；loli/adult 0 | **7 角色 ×4 形态**：按铁律七顺序“全身稿→拆件→骨骼”逐角色落地；首个补 `loli`（萌童声已选） | P1 · `characters/<id>/forms/<form>/` |
| 三 微内核+热插拔 | 微内核雏形有，热插拔无 | **AgentModuleABI + 无锁环形缓冲事件总线 + `config/modules/*.json` 热加载器**；`mod_live2d / mod_physics / mod_vision / mod_voice / mod_work` 五件 | P0 · `src/core/zmod.c` + `src/modules/` |
| 三 桌面感知 | 静态透明窗与穿透存在 | **`mod_desktop_physics`**：DXGI 窗口矩形拓扑、任务栏吸附、Alpha 点透、拖拽重力摆（像素级 `HitTest` 已有，前端轮询待补 DXGI） | P1 · `src/win32/zw32_desktop.c` |
| 四 终身学习-视觉自学 | 无 | **视觉经验簿 `data/learn/visual.jsonl`**：`缺陷→成因→范式` 自增，生成器必读 | P1 · `tools/learn_visual.py` |
| 四 终身学习-记忆 | 有 `zmem.c` 34K / `zpersona.c` / `zthink.c` / `data/memory/` 三层（profile/episodic/working）| 补 **图+向量检索 + 情景记忆提炼 + 习惯模仿学习** 引擎（当前为文件+JSON，缺向量） | P2 · `src/core/zmem_vec.c` |
| 四 自写C模组 | 契约层 `capabilities/providers/skills` + `gateway` 已通，可接 MCP | **TCC/Clang 沙盒编译器接口**：`agent → write C → compile .so → 自检 → dlopen挂载` 闭环 | P2 · `src/core/zforge.c` + `tools/check_forge.py` |
| 五 主动生命感 | 有 `breath/sway/wiggle/idle→sleep` 但无连续情感流 | **内在张量（好奇/精力/专注/亲密）+ 三级视线跟随（眼→头→胸）+ 滞后阻尼**；`zpet` 状态机升为情感驱动 | P1 · `src/core/zdrive.c` + `docs/PRESENCE_PLAN.md` |
| 五 分寸感 | 有 `interaction.json` 18 规则，但无“高 APM 静默” | **屏幕感知分级**：`APM/窗口焦聚/全屏游戏` 检测→`沉浸陪伴态` | P1 · `mod_vision_companion` |
| 六 容错与帧率 | 有 `zdeflate/zimg` 纠错，但无 SEH/signal 沙盒 | **SEH + 沙盒进程 + 物理帧避让**：模组崩溃秒级卸载重载；游戏全屏时 `zphys2` 降采样 | P1 · `src/core/zguard.c` |
| 七 交付铁律 | 零 TODO，测试门基本齐，但缺内置调试层与标准工作流闭环 | **视觉调试 Overlay + 九宫格验收 + `make audit-frames` 标准流** | P0 · 同 R2 |

---

## 五、视觉闭环首帧证据（本轮离屏实拍）

> **强制视觉闭环**：每改必出图。本轮在 `build/zhuochong_preview --port 5174` 上抓取。

| 状态 | 文件 | 视觉结论 |
|------|------|---------|
| 待机 `idle` | `docs/qa/audit_frame_idle.png` (466×748, 209 KB) | **通**：无穿模、呆毛与尾巴自然下垂、眼眶干净 |
| 挥手 `wave` 峰值 2.5 s | `tmp/audit_wave_peak.png` | **通**：肩/肘/腕三级骨无拉伸撕裂，袖内衬可见 |
| 思考 `think` 1.2 s | `tmp/audit_think.png` | **通**：头微侧 7°，眼神游移可用 `eyeball` 参数复现 |
| 惊讶 `surprised` 0.8 s | `tmp/audit_surprised.png` | **观测**：惊讶时口型被表情压半，需后续把 `viseme_weight` 从 0.8 → 形态相关可调 |

**转头·九宫格硬性要求下一轮补**：`-30°/center/+30° × 眨眼0/0.5/1` 共 9 帧 + `wireframe` 同步出图。

---

## 六、无缝平滑演进路线（保留基建，逐个击破）

### Phase 0 — 打通视觉自检闭环（本分支下周）
1. **拆 `make test`**：`test` 快闸 vs `soak` 长稳，快闸回归 3 秒（R1）。
2. **上叠加层**：`?debug=wireframe/collider/force` 三档 + `make audit-frames` 一键九宫格（R2/R5）。
3. **立 `visual.jsonl` 经验簿**：本次“拼接色断”“硬切边”等落档（铁律四-1）。

### Phase 1 — 微内核热插拔（不破稳）
4. **事件总线**：lock-free ring buffer（`zbus.c`），渲染 60 FPS 与 AI 推理解耦（铁律一卡顿根因）。
5. **ModuleABI**：`mod_live2d_core` 先行抽离，`dlopen` 热重载（铁律三）。

### Phase 2 — Live2D 内核 Verv2 + 全美术
6. **ArtMesh + WarpP树 + 多级摆**：发/耳/尾升为弹簧链，九宫格验收（铁律二）。
7. **四形态补齐**：`loli` 设计稿（先整身，再拆骨——铁律七工序），复用 `prepare_sprites` 管线。
8. **7 角色**：每角色 `character.json + forms/teen/loli/adult/chibi + outfits`，零代码增角色。

### Phase 3 — 陪玩与代理
9. **桌面物理 + 视觉陪玩**：DXGI 零拷贝 + 窗口拓扑（`mod_desktop_physics/mod_vision_companion`）。
10. **语音全双工 + 自写模组**：`mod_voice_soul`（VAD+TTS+FFT→AEIOU）与 `zforge` 编译沙盒（铁律四-3）。

---

## 七、对用户的承诺

1. **不替你宣布 `[需真机]`**：透明穿透/拖动手感/帧率，只在你机器上勾。
2. **不动你的可用基建**：`teen` 104 部件与 81 参数原样保留，任何重构先在 `/tmp/testroot` 隔离演练。
3. **每改必有图**：后续每个 PR 附 `docs/qa/<任务号>_*_1x.png` + `4× zoom` + `wireframe` 三图。
4. **分支纪律**：只在 `arena/aaf1408c-zhuochong` 上演进，不切分支、不 `reset` 生产素材。

> 下一步：若认可本诊断，首个代码 PR 将是 **R1 + R2（拆测试 + 调试图层）**，当日可合入；随后进入 Phase 1 事件总线。  
> 备选：若更看重美术，可先做 Phase 2 的 `loli` 整身稿（需你确认新角色设定候选，见 `docs/TASK_TEMPLATES_PLAN.md`）。

— 新任主架构师 · 2026-10-28
