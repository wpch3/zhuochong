# Chibi 真正 Cubism 模型路线核查（2026-11-04）

状态：**官方路线已查；真实模型未制作；作者/运行时路线需分轨。** 本文件记录官方 Cubism 工作流、开源运行时样例、当前仓库事实与阻塞，不是模型交付或生产批准。

## 结论先行

1. 当前 Chibi / Teen 实现是项目自研 C `zrig`，配置为 `rig.json` + PNG。它可以实现某些 Live2D 类似的功能，但**不是 Cubism 模型**，不能称 `.moc3`，也不能暗示 Cubism Editor/SDK/Core 可加载。
2. 真正 Cubism 模型制作需从有完整分层的 PSD/源图开始，在 Cubism Editor 中导入并成为 ArtMesh，制作网格、变形器、参数 keyform、部件与绘制顺序，再由 Editor 制作 texture atlas 并导出 `.moc3`、`.model3.json` 和纹理；Physics、Pose、Motion 等文件按需导出。
3. 作者制作/导出和桌宠当前 C 运行时是两个独立工作：即使得到真 `.moc3`，`zrig` 也不会因此能加载它。若要在应用运行 Cubism 模型，需要另外采用符合许可的官方 Cubism SDK/Core 或经审查的桥接，并按目标平台/模型特性测试。
4. 当前沙箱为 Linux；`CubismEditor` / `cubism-editor` 命令不存在；全仓未找到 `.psd`、`.cmo3`、`.moc3`、`.model3.json`、`.physics3.json`、`.pose3.json`、`.cdi3.json`。目前没有可直接导入的 Chibi 分层作者源，也没有可验证的 Cubism 成品。因此本轮**不能**诚实产出或声称已完成 `.cmo3` / `.moc3`。
5. 手型要求是两项并行：正常、可辨识手指的 `small` 与独立 `mitten` 都保留；风格选择器与腕部运动、手势分离。现有 `small` 是源图可见手像素的候选 crop，不等同已验收的完整有指生产手件。

## 官方流程研究

### 1. PSD / 部件输入

- 官方“Import PSDs”说明 Cubism Editor 可从 PSD 新建模型；PSD 图层导入后会自动生成 ArtMesh，但初始网格顶点数较少，需要在建模阶段按运动需求继续编辑。
- PSD 必须先按会运动的美术部件合理分层；可用 group 保留部件组织。对小寻 Chibi，后续应从自有完整分层母稿开始，而不是从现有单张 `body_full.png` 假装得到完整分层。
- 源素材必须补足运动时会显露的区域。手腕入袖口处要分别处理袖后、手/前臂与 cuff 前覆盖，并让正常手与 mitten 的左右层独立可控。

### 2. Cubism 建模

- Editor 中的可画对象是 ArtMesh；模型制作涉及网格编辑、参数与 keyform、Deformer 层级、绘制顺序、遮罩、部件和纹理图集。
- 用户所说“骨骼部件”在 Cubism 中不能简单等同于三维骨骼。要做的是 Live2D 的 ArtMesh + 参数化 keyform / Deformer（可含 rotation/warp 及物理链）模型结构；应按官方编辑器的数据语义制作与验收，而非把 `zrig` 的节点/网格直接改名。
- 手型切换应作为独立的部件显隐/参数控制维度；腕角、动作和手势各自独立。是否使用 Cubism Pose group 或独立 style parameter，需在 Editor 项目中按实际 SDK 控制方式验证，不先伪造兼容字段。

### 3. 官方导出与运行

- 官方 “Data for Embedded Use” 将 `.moc3` 定义为应用所用的模型数据，`.model3.json` 负责关联 MOC3、纹理等资源；默认导出包括 `.moc3`、`.model3.json` 和 texture，physics / motion / user data / CDI 等可按需附加。
- 官方 SDK 文档说明 `.moc3` 要交给 Cubism SDK/Core 创建模型实例并渲染；它不是项目自己的 JSON rig 格式。
- `CubismWebFramework` GitHub README 明确要求与 Live2D Cubism Core 配合加载模型，并说明 Core 不包含在该仓库，需要从官方 SDK 包获取。开源 Framework 的代码可供结构/调用流程参考，但它不提供 Core，也不意味着本仓库获得 Core 的使用/再分发权。

## 许可 / 架构边界

- Live2D 官方 SDK 页面说明 Core 按 Proprietary Software License 发布，未放在 GitHub 仓库；官方 SDK 包提供 Core。
- 官方 SDK Release License 页面说明：可在开发/验证阶段获取 SDK 开发；发布含 Cubism SDK 的内容时需要按发布许可流程处理。页面同时列出个人/小规模主体的一般豁免及“Expandable Application”例外。本项目具有可自定义/可扩展角色内容的方向，不能由代理在此作法律归类；发布前需逐条核对当时有效条款，必要时向 Live2D 确认。
- **本轮不集成 Cubism Core、不打包 Core、不声称 `zrig` 兼容 `.moc3`。** “用官方 Editor 创作模型”与“把官方 Core 放进产品运行时”是不同决定；后者仍受已有架构/授权门禁约束，不能由制作模型的请求自动推导出授权。

## 官方与参考项目清单

1. Live2D 官方 PSD 导入手册：<https://docs.live2d.com/en/cubism-editor-manual/psd-import/>。
2. Live2D 官方嵌入导出手册：<https://docs.live2d.com/en/cubism-editor-manual/export-moc3-motion3-files/>。
3. Live2D 官方文件类型：<https://docs.live2d.com/en/cubism-editor-manual/file-type-and-extension/>。
4. Live2D 官方 Cubism SDK for Web（Core 边界）：<https://docs.live2d.com/en/cubism-sdk-manual/cubism-sdk-for-web/>。
5. Live2D 官方 SDK Release License：<https://www.live2d.com/en/sdk/license/>。
6. Live2D 官方 `CubismWebFramework`：<https://github.com/Live2D/CubismWebFramework>。Framework 与 Core 分开；仅用于研究加载层边界/公开 Framework 源码。
7. 仓库已有 `CubismWebSamples` / Haru 样例资产审计在 `docs/memory/CHIBI_LIVE2D_REFERENCE_AUDIT_2026-11-02.md`；可参考 `model3.json`、physics、pose、motion 的装配关系，不复制样例美术/模型到小寻。

对应索引已追加至 `docs/REFERENCE_NOTES.md` 第七十三批。

## 可执行的分阶段路线

### 阶段 A：源稿门（未完成）

- 取得/制作小寻 Chibi 的完整可分层 PSD/同等可导入源图，保留原始设计真值、完整遮挡下内容、袖口夹层与左右对称/非对称差异。
- 同一模型工程必须包含正常有指 `small` 与圆钝 `mitten` 两组左右独立手件；不得把 `small` 当“未确认”的别名，也不得把 mitten 合并覆盖 small。
- 对源 PSD 图层、角色来源、隐藏腕补画和 AI/人工绘制 provenance 做哈希与视觉验收。现有 study WIP 与生产 PNG 均不能直接冒充完整 PSD。

### 阶段 B：官方 Editor 建模（未开始）

- 在有许可证/可用 Cubism Editor 的环境从 PSD 新建 `.cmo3`；编辑 ArtMesh 网格、Deformer/keyforms、参数、部件绘序、必要遮罩、Physics/Pose；逐项目视中性帧和极值。
- 至少让 `small` / `mitten` 互斥可切换，两个 style 都能分别接受 wrist motion 与 gestures；逐项覆盖 Chibi 发型、兜帽、服装遮挡与全身动作。
- 记录 Editor 版本、工程来源、对象/参数清单、导出设置、截图、错误/修复和 SHA；不要将运行时仿真截图当 Editor 导出验证。

### 阶段 C：官方导出与 Viewer 载入（未开始）

- 由 Cubism Editor 导出 `.moc3` + `.model3.json` + texture atlas，按实际模型需要导出 `.physics3.json`、`.pose3.json`、motions/expressions 等。
- 用官方 Cubism Viewer 或 SDK sample 做实际加载，检查参数、姿势、层序、左右 hand style、动作与纹理。保留可复查证据；仅看到文件扩展名或 JSON 能解析不算模型验收。

### 阶段 D：产品运行时决策（未批准）

- 选择保持 `zrig` 自研路线（只运行自有 `rig.json`/PNG，不运行 `.moc3`），或另外评估符合许可的 Cubism SDK/Core adapter。任何 Core 下载、集成、分发、发布均需独立 license/架构审批与平台兼容测试。
- 在该决策完成前，Chibi 的实际 Cubism 模型可以作为独立建模/导出交付物，但不得宣称当前桌宠 C 引擎已运行它。

## 本轮实际执行 / 未执行

- **已执行**：查官方 PSD 导入、MOC3/embedded export、文件类型、Web SDK/Core、SDK Release License 文档；核查 Live2D 官方 Web Framework README；在仓库搜索 Cubism 文件；确认 Linux 环境无 CubismEditor 可执行文件；更新双手型契约与非兼容声明。
- **未执行**：没有 PSD/CMO3/MOC3 可编辑源；没有启动 Cubism Editor；没有绘制/重做生产艺术；没有导出或加载模型；没有集成 Core/SDK；没有做全身 Cubism 模型 QA。
- **下一步阻塞**：先得到 approved Chibi 分层源稿/PSD，再在支持的 Cubism Editor 环境创建 `.cmo3`。当前沙箱不具备该应用或源工程，因此此项本轮不能靠自研 C 代码替代。

## 2026-11-04 follow-up — refreshed source-readiness inventory

After fast-forwarding the active branch to `dad05a95beafdc2aea0b46e597d1461bd4bc148b`, I re-audited the actual Chibi tree rather than assuming the earlier file inventory was current:

- No `*.psd`, `*.cmo3`, `*.moc3`, `*.model3.json`, physics/pose/CDI Cubism files exist in the checkout. `CubismEditor`, `cubism-editor`, `wine`, and `wine64` are not installed on this Linux runner.
- `characters/xiaoxun/design/chibi/README.md` explicitly says its `desktop_pet_base_2026-10-31.png` and side-walk reference are **desktop-pet design references**, not Live2D Chibi sources or production sprites. They are not valid substitutes for an approved Live2D source PSD.
- The Live2D Chibi source manifest `characters/xiaoxun/forms/chibi/design/form_art.json` points to `design/design_sheet_chibi.png`; it does not name a layered PSD. The sheet is a flattened 1024×1024 image. `sprites/body_full.png` is a 567×1292 flattened RGBA source-derived body image; the production cutouts include `seg_arm_l.png` / `seg_arm_r.png` (100×230 each), separate face/hair/garment/accessory PNGs, but the current Chibi rig lists only `seg_arm_l/r` for arms and there are no Chibi hand/cuff PNGs or `hand_parts.json`.
- The current Chibi subtree therefore has usable *rendered/cutout components* but is not a verified layered authoring master: the tree lacks a normal-fingered/mitten left-right pair, genuine hidden-wrist continuation, and explicit cuff-front/back source layers. Existing redraw fragments are not one complete, approved PSD with proven overlap coverage.
- I did not automatically recombine the sprite cutouts into a PSD or label such an assembly a Cubism source: crop edges and omitted underlap could become visible in deformation, and no Editor is available to validate any generated PSD. No Core/SDK was downloaded or integrated.

This updates the blocker from “no Chibi material at all” to the more precise state: **many Chibi PNG cutouts exist, but there is no approved complete layered source project and no official Editor runtime here**. Next model-authoring gate is an approved, overlap-complete layered Chibi PSD (including both hand styles) plus an environment that runs official Cubism Editor; only then start `.cmo3` editing and exported `.moc3` / `.model3.json` verification.

## 2026-11-04 continued work — machine-readable current-layer inventory

To move the source audit forward without pretending the existing `zrig` is Cubism, I inventoried the actual current `characters/xiaoxun/forms/chibi/rig.json` file references and image metadata. The WIP report is `docs/qa/chibi_candidate_2026-11-02/cubism_source_layer_inventory_wip/README.md`; the full JSON includes each file SHA-256, dimensions, alpha bounds, canvas position, group, existing zrig order, and parameter IDs/ranges.

- **Verified snapshot:** 49 `rig.json` parts; all 49 referenced image files currently exist. Group counts: head 34, chest 7, each foot 2, and each arm/leg 1. The file also contains 43 parameters, 26 deformers, 19 `physics` records and 5 `physics2` records; these remain proprietary `zrig` records, not Cubism Editor objects.
- **New identity anomaly:** despite living under `forms/chibi` and using a `form_art.json` that points to `design_sheet_chibi.png`, the current Chibi `rig.json` identifies itself as `小寻_teen`. Do not carry that metadata into any Cubism project until the source/generator discrepancy is resolved. The production rig is protected; this audit did not edit it.
- The inventory confirms the important boundary: **all current referenced cutouts existing does not equal a complete layer master**. There are still only `seg_arm_l/r`, no independent hand/cuff layers or hand parts manifest, no hidden-wrist continuation, and no verified underlap-complete PSD. The report proposes how to translate *verified future source layers* into Editor ArtMeshes; it does not auto-map zrig z-order, parameters, deformers, or physics into Cubism.
- This inventory is explicitly `wip_source_inventory_not_psd_not_cubism_model`. No PSD/CMO3/MOC3 was generated, no source asset/rig/Core was changed, and no Cubism Editor/Viewer test occurred.
