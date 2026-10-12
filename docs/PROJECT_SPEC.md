# 桌宠项目规格（C 桌面端）

更新：2026-10-11 ｜ 分支：`arena/b3359546-zhuochong`
本文件是**当前有效**的需求规格。旧交接文件 `HANDOVER_RESTART (1).md` 中的技术教程（第七、八节）
与参考项目清单（第二节）继续有效，但**角色与执行顺序以本文件为准**。

---

## 一、结论先行：当前已经做到什么

| 项目 | 状态 | 说明 |
| --- | --- | --- |
| Windows 原生 C 桌宠 | ✅ 可运行（[需真机] 确认观感） | `dist/windows/x86_64/zhuochong.exe`，370 KB，零外部依赖 |
| 分层透明窗 | ✅ 代码完成 | `WS_EX_LAYERED` + `UpdateLayeredWindow` 每帧直推 RGBA |
| 像素级鼠标穿透 | ✅ 代码完成 | `WM_NCHITTEST` 返回 `HTTRANSPARENT`，按角色 alpha 判定（非整窗矩形） |
| 整窗穿透开关 | ✅ 完成 | 托盘菜单 / `Ctrl+Alt+T` |
| 拖动 | ✅ 完成 | 按住角色拖动，松手吸附回屏幕内，位置记忆 |
| 托盘 + 右键菜单 | ✅ 完成 | 形态 / 服装 / 动作 / 缩放 / 穿透 / 置顶 / 打开配置 / 关于 |
| 动作状态机 | ✅ 完成并单测 | 优先级、可中断、过期回退（语义对齐 ds-local-pet） |
| 空闲入睡 | ✅ 完成并单测 | `GetLastInputInfo`，默认 90 秒，任意输入唤醒 |
| 眨眼 | ✅ 完成并单测 | 五态机（等待→闭合0.1s→保持0.05s→睁开0.15s→等待），对齐 Live2D |
| 动态立绘（骨骼/图层） | ✅ 完成 | 数据驱动 rig.json：组、部件、通道曲线、区域、动作 |
| 换装（真换装） | ✅ 机制完成 | `config/outfits/<id>.json` 覆盖部件文件；缺的是新素材 |
| 空闲/悬停/摸头/锤击/抚摸 | ✅ 完成 | 摸头连击 3 次触发开心 |
| 缩放（含托盘与热键） | ✅ 完成 | `Ctrl+Alt+↑/↓`，缩放锚定脚底中心 |
| 配置全部可自定义 | ✅ 完成 | JSON + JSON Schema + 精确到字段的错误提示 |
| 单测与自检脚本 | ✅ 96 项全绿 | `scripts/selfcheck_all.sh` |
| 沙箱预览 | ✅ 运行中 | 用**同一套 C 引擎**渲染，端口 5173（`docs/images/states_preview.png` 是各状态实拍） |
| UI 界面（二次元风格） | ⬜ 未开始 | 按用户指示：先把基础 C 软件做好 |
| AI 角色 7 个 × 4 形态 × 多服装 | ⬜ 未开始 | 小寻已完成 1 形态（短发/中长发设计图已入库） |
| Web 工作区 / API / 语音 / 社交 | ⬜ 未开始 | 功能开关与配置骨架已就位，默认全关 |

---

## 二、角色

### 2.1 小寻（第一个 AI 角色，用户已确认方向）
- 参考图：`小寻.png`（短发基础）、`小寻短发.png`、`小寻长发.png`；均为用户提供。
- 已生成并入库的设计图：
  - `characters/xiaoxun/design/design_sheet_short.png`（短发，纯洋红底，可直接抠图）
  - `characters/xiaoxun/design/design_sheet_midlong.png`（中长发，同上）
- **两种发型都保留**（用户明确要求：中长发和短发都要）。
- 从生成图取样的色卡（与用户参考图一致）：

| 用途 | 色值 | 说明 |
| --- | --- | --- |
| 头发主色 | `#D8D8E8` → `#C9CBE0` | 银紫，发梢渐到淡蓝 `#9FC4E8` |
| 眼睛 | `#4A8FD4` / 高光 `#FFFFFF` | 明亮蓝瞳 |
| 外套主体 | `#FFFFFF` 白 + `#6CB4C0` 青绿袖子 | 棒球外套 |
| 衬衫 | `#FCE8D8` | 奶油米 |
| 裙 | `#3C4860` | 藏青百褶 |
| 袜 | `#F6F2F0` 白 + `#6CB4B4` 双条纹 | 及膝袜 |
| 鞋 | `#6CB4B4` + 白 | 运动鞋 |
| 肤色 | `#FCE4D8` | 浅肤色 |
| 标志物 | 呆毛 + 鲸鱼发夹 | 呆毛参与物理摆动与组层级 |

### 2.2 每个 AI 角色的完整规格（7 个角色通用）
- 角色：deepseek / claude / openai / gemini / qwen / kimi / grok（形象为原创拟人，不照搬商业角色）。
- **每个角色 4 种形态**：少女（teen）/ 萝莉（loli）/ 青年女性（adult）/ Q 版（chibi）。
- **每种形态多套服装**（config/outfits 或角色包 outfits/），可无限添加。
- 形态之间的身高与头身比写在各形态 `rig.json` 的 `canvas`/`origin` 里。

---

## 三、目录结构（实际）

```
config/                 ui.json pet.json features.json providers.json voices.json settings.json(自动生成)
schemas/                与 config 一一对应的 JSON Schema
characters/<角色id>/     design/（设计图） forms/<形态id>/{rig.json,sprites/,sprites_report.json}
                         outfits/<服装id>.json
src/core/               zc zjson zschema zimg zdeflate zsm zrig zconfig zpet   ← 平台无关
src/win32/              main_win.c zw32.c                                      ← Windows 表现层
src/headless/           main_headless.c                                        ← 沙箱预览（同一引擎）
src/third_party/        stb_image.h（MIT/PD，登记在 README）
tools/                  prepare_sprites.py make_parts.py make_rig.py
tests/test_core.c       单元测试
scripts/                selfcheck_all.sh fetch_references.sh
docs/                   本文件、HANDOVER.md、ROADMAP.md、REFERENCE_NOTES.md
dist/windows/x86_64/    zhuochong.exe
```

---

## 四、可自定义清单（新增内容不改核心代码）

| 想做什么 | 怎么做 | 验证 |
| --- | --- | --- |
| 换角色 | `config/pet.json` 的 `character.id` | 重启即生效 |
| 换形态 | 加 `characters/<角色>/forms/<新形态>/rig.json`，托盘切换 | `zpet_set_form` 单测覆盖 |
| 换/加服装 | 加 `characters/<角色>/outfits/<id>.json`，列出要替换的部件文件 | `zpet_set_outfit` 单测覆盖 |
| 加动作 | 在 `rig.json` 的 `actions` 里加一条（可含通道曲线、部件覆盖） | 动作自动出现在托盘菜单 |
| 改眨眼节奏 | `rig.json` 的 `blink` 段 | 单测覆盖时序 |
| 改交互区域 | `rig.json` 的 `regions`（画布坐标，含光标类型） | 单测覆盖命中 |
| 加配饰 | 在 `parts` 里加部件并挂到 `head`/`root` 组 | 层级由 `layer` 决定 |
| 加功能模块 | `config/features.json` 加一条（默认关闭 + token 上限） | schema 校验 |
| 加主题 | `config/ui.json` 换主题名与调色板 | schema 校验 |
| 加供应商 | `config/providers.json` 加一条（OpenAI 兼容） | schema 校验；官方直连默认关 |

### 通道（通道曲线）参数
`actions[].channels[]`：`target`（组 id 或部件 id）、`param`（`dx/dy/sx/sy/rot_deg/alpha`）、
`wave`（`sine` 循环晃动 / `bounce` 抬手回落 / `pulse` 进入并保持 / `decay` 阻尼抖动 / `flap` 只朝一个方向的循环开合，用于嘴型）、
`amp`、`freq`、`phase`、`dur`、`ease`（`linear/in/out/in_out/out_back/out_elastic/out_bounce`）。

### 部件标签（tags）
`body / head / eye_open / eye_closed / mouth / hair / accessory / tail / gaze`
- `gaze`：会被视线偏移影响的部件（虹膜拆件后自动获得“视线跟随”能力，无需改代码）。
- `eye_open` 与 `eye_closed` 在眨眼参数下交叉淡化（0 睁 1 闭），因此**眼睛拆件到位即升级**。

---

## 五、测试与验收（必须按此口径汇报）

- [测试锁] `bash scripts/selfcheck_all.sh` 必须全绿：零告警编译、96 项单测、配置/schema、素材透明通道、
  Windows 交叉编译、预览服务返回真实帧。
- [沙箱实测] 沙箱内可验证：状态机时序、眨眼时序、合成像素正确性、命中测试、配置诊断、PNG 编解码、
  exe 的 PE 头/子系统/依赖 DLL。
- [需真机] 必须由用户确认（代理不得代为宣布）：窗口真透明、像素穿透手感、光标形状、
  托盘图标清晰度、动画流畅度、Windows 关机/休眠后的位置持久化。

---

## 六、素材规则（沿用旧交接文件第五之二、八节，摘要）
- 全部视觉素材用高清生图 PNG；禁止 emoji / SVG / 程序画图顶替。
- 透明背景；角色全身画布 848×1360；图标 ≥256×256；表情 ≥512×512。
- 生成图必须过机器验收：分辨率、透明通道、键色（洋红）残留、白边残留、色卡比对、轮廓对齐。
  工具：`tools/prepare_sprites.py`（含残留检测与自动去噪）+ `tools/make_parts.py` + `tools/make_rig.py`。
- 已知失败路线（不要重复，见 `docs/ROADMAP.md` 与旧文件第九节）。

---

## 七、安全与数据
- 全部数据只存本机（`logs/`、后续的 `data/`）；测试阶段只用中转站，官方直连默认关闭。
- API Key 只在本机保存（后续实现 Web 网关时写入 `data/`，不入库）。

---

## 八、许可
- 本项目原创代码。第三方：`stb_image.h`（MIT/Public Domain），登记于 `src/third_party/README.md`。
- 参考项目只学习思路、不复制代码；六个参考项目地址见 `docs/REFERENCE_NOTES.md`（含各自许可）。
