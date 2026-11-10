# T67.7 小寻 teen 长发返修｜下一代理完整交接

更新：2026-10-27（Asia/Shanghai）
当前工作分支：`arena/ba836be0-zhuochong`（Arena 状态：`active`）
仓库：`/home/user/zhuochong`
沙箱运行手册：[`docs/T67_7_SANDBOX_RUNBOOK.md`](T67_7_SANDBOX_RUNBOOK.md)
计划与审计记录：[`docs/T67_7_REDO_PLAN.md`](T67_7_REDO_PLAN.md)

> **先读本交接，再动任何素材。** 当前任务是长发视觉返修与隔离测试，不是把临时图直接接入生产。不要把自动测试通过说成视觉验收，也不要替用户宣布真机通过。

## 0. 最高优先级：用户要求永远排第一

在遵守平台安全与当前分支规则的前提下，**用户当轮明确要求、纠正、已批准内容和硬性质量标准，永远排在项目施工优先级第一**。旧代理交接、任务表默认顺序、自动化数字、代理偏好或省时方案都不能覆盖用户要求；最新明确纠正优先于旧假设。每轮开工先把用户原话转成“验收条件 + 禁止事项 + 施工顺序”，遇到技术限制要如实说明并给可验证替代路径，不能静默改口径。

### 不可跳步的施工顺序

1. **用户要求与验收门槛**：先读当轮消息和本交接，确认用户指定的基准、要修的问题、禁区及审批点。
2. **真值源与当前状态**：按领域找正确依据（画稿看原设/已批准概念；代码看仓库源码和测试；物理看官方规范与真实运动帧；任务状态看任务台账），先检查分支、工作区、文件和当前预览，不凭记忆覆盖现状。
3. **学习与查证**：查官方文档、教程、可信的参考项目源码或真实视觉参考；记录 URL、日期、结论和适用边界。
4. **隔离制作**：生成物、脚本输出、rig 修改先放 `/tmp` 的副本；不动生产素材，不复用已否决方案。
5. **代理本人目视实际产物**：每一轮都打开真实 PNG/合成帧/预览，不得只看脚本、数字、缩略图或“全绿”。发现问题先放大看图，定位具体接缝/色断，再做局部修复并复看。
6. **自动化回归辅助**：跑适用的测试/素材闸门；失败先查根因。指标只防回归，不代替视觉审美；改闸门时用已知坏例做负控，证明闸确实能红。
7. **用户看实际结果并确认**：提供可查看的完整画面和关键放大图，明确说明仍存问题。用户没批准，不拆下一阶段或接生产。
8. **生产接入与归档**：只有获批后才按最小范围接入；把结论依赖的 QA 证据存入 `docs/qa/`，草稿留 `/tmp`；核对 diff 后才提交当前分支。

### “必须用眼睛看”硬性验收法

- **代理自己必须看**：改完后用图像查看工具打开实际结果，并在汇报里写清楚看到的现象；“已修复”之前必须有可复核的放大图。不得把问题留给用户发现。
- 看图顺序：全身/完整帧 1× → 全帧约 1.5× → 相关部位 4–8×；透明素材至少合成到白、灰、黑/深色底，避免透明 RGB 或背景把边缘问题藏起来。
- 至少检查：原图/原尺寸、透明边缘、整体剪影与比例、发根、左右鬓侧、肩前、胸口、腰/上胯、发梢、身体遮挡后补画区；按改动影响再检查所有关联发型/姿势，不只看自己点名的一处。
- 静止图不能验动态问题；运动类问题必须查看真实渲染的负向/中位/正向帧。任何一帧露缝、穿模、硬切、色块断层或旧件残留都返工。
- before/after 用同一画布、同一比例并排；调色/拼接结论须有实际合成，不可只比 RGB/HSV/Lab 数字。闸门绿但图难看，以图为准继续修；闸门红但视觉正确，查明判据口径并说明，不得盲目调阈值。
- 改 sprite/rig 后必须确认预览重新加载了新素材；必要时停止并重启服务，核对日志里的 root 和角色 rig，防止陈帧误判。

### 总体制作质量红线

- 原创高清透明 PNG；不以 SVG、程序形状、低清放大、占位图或临时诊断图冒充成品；不擅自复制参考项目代码、模型或素材。
- 分层件必须是本件自己的完整图，遮挡处也要有足够的补画/重叠；静止与目标运动中都不能露底/露缝。角色色卡、画风和人物比例以用户批准的原设为准。
- 内容与引擎分层、模块化；美术问题优先在素材/挂点/变形路径解决，不为绕过素材问题改核心。生成脚本若会重写生产文件，必须先在 temp root 运行。
- 改动前后查 `git status` 与 diff；不批量 `reset`/`clean`，不顺手提交无关文件。测试通过、沙箱视觉通过、用户批准、生产接入、真机验收是不同门槛，不能合并成一个“完成”。

全局流程的权威详见 `docs/memory/WORKFLOW.md`；美术复盘、拆件规范、模板与参考资料分别见 `docs/memory/POSTMORTEM_ART.md`、`docs/ART_PARTS.md`、`docs/SHEET_PIPELINE.md`、`docs/REFERENCE_NOTES.md`。

## 1. 当前结论（一句话）

T67.7 六件长发仍未完成。用户此前认可了总体造型方向，并要求以批准的全身概念作比例/发流参考、以原装短发作小寻发色唯一基准；重点是用眼睛定位胸前拼接和颜色断层，再做局部修复。前一轮的静止图 `frame_static_long_color_v4.png` 只存在于临时工作区，已无法从当前已检查的 Git 历史恢复。最新可追溯代理分支有旧后发源件 v1/v2 和较早的 T67.39 全身定帧图，但不是这轮六件母稿或 v4。

当前可见的新试稿是 `/tmp/t67_7_candidates/master_rebuild_unapproved_v1.png`（848×1264 RGBA）；它是**新重建的 hair-only 母稿候选**，不是找回的 v4，尚未获用户批准、尚未拆六件、未进 rig。已经向用户展示，等用户目视反馈后才能继续拆件。

## 2. 任务范围与用户已定事项（不可改口径）

- 用户认可的全身概念仅供长发造型、长度和比例参考；**严禁**从概念中抠脸、身体、衣物或皮肤进入母稿/部件。母稿和每个拆件必须只含头发像素。
- 小寻发色以原装短发为唯一基准：浅灰紫主体、蓝/青色发梢、柔和高光。不可调成偏暗钢蓝，不另加粉紫长条。图一留作未来其他角色/配色备选，图二方向最适合本次小寻；本次不混拼两种方向。
- 长发总体造型用户认为基本合适，不得无故重做；重点修胸前细微拼接感、像断开的颜色衔接。不得有刺猬块、硬切边、可见缝、色块突变或透明露底。
- 侧发须从鬓侧沿肩前自然垂至腰/上胯附近；后发在被头、身体遮挡的位置仍要补足，防止摆动露缝。
- 六件 ID 必须分别独立：`acc_hair_long`、`hair_side_l`、`hair_side_r`、`acc_hair_sidelong_l`、`acc_hair_sidelong_r`、`acc_hair_crown_long`。母稿先整体验收，再拆六件；静止拼回通过后才测试动态。
- 不可复用失败碎片或旧失败侧发稿改色拼凑；不可用 `bend_y` 对整片做垂直伸缩。
- 实验只在 `/tmp`；不要改写生产素材/rig。保护 `teen rig`、`body_full.png`、九态眼件、闭眼/笑眼和眉件；不要批量 `reset`、`clean`、覆盖或顺手提交无关改动。
- 透明 PNG 必须原创高清并目视边缘；禁止黑/白/彩边。颜色统计和脚本闸门只能辅助定位，不能替代放大目视。
- 汇报一律中文，明确区分 `[测试锁]`、`[沙箱实测]`、`[需真机]`。Windows 透明窗、点击穿透、拖动手感与真机帧率均不得在沙箱里宣布完成。

## 3. 历史分支核查与 v4 来源（已完成，不要重复找错对象）

已按结算时间核对远端 Arena 分支头：

| 分支 | 已核头提交 | 时间（UTC） | 备注 |
| --- | --- | --- | --- |
| `arena/b3359546-zhuochong` | `3b5d17b` | 2026-10-11 09:19:53 | 较早 |
| `arena/cc642f66-zhuochong` | `a85c706` | 2026-10-24 19:54:19 | 当前本地 HEAD 的来源 |
| `arena/ba836be0-zhuochong`（远端同名 ref） | `d6fe833` | 2026-10-26 06:43:58 | 检查到的最新代理分支头 |

- 远端 `d6fe833` 中，`d91d03f`（2026-10-25 20:15:04 UTC）是 T67.7 后发专用源件 v1；`2d21610`（2026-10-25 20:22:02 UTC）是 T67.25 后发 v2 拟合接入。该快照另有 `hair_long_back_v2@2x.png` 和 `docs/qa/t67_39_long_hairstyle_after.png`。
- 最新分支 `docs/memory/TASKS.md` 仍将 T67.7“长发重造（五组）”标成 `[~]`。T67.25 的 `[x]` 仅代表一个后发件替换/注册；T67.39 是那条较早整身 rig 的静止复验。它们不是本轮六件母稿，也不是本轮静止 v4。
- 在该最新分支头及其可达历史按已知路径/名称检查，没有找到 `frame_static_long_color_v4.png`、头/胸放大图、`master_haironly_colorlock_v4.png` 或六件临时 PNG。其任务文档引用的 `docs/qa/t67_7_hair_only_candidate.png` 在该分支树中也缺失；T67.25/T67.39 的 QA 图则已跟踪。
- **来源澄清：** `frame_static_long_color_v4.png` 是前一轮代理在本 T67.7 工作中的临时静止测试输出；它不在已检查 Git 分支中。此前没有把它、六件 PNG 和临时 rig 归档到项目。项目 `docs/qa/README.md` 规定“若删掉证据就无法复核结论，证据必须入库 `docs/qa/`”，所以没归档属于工作流程疏漏。不要把这轮的 `master_haironly_colorlock_v4.png` 或远端 v1/v2 说成找回的旧 v4。
- 远端旧图只作历史参考，提取文件在 `/tmp/t67_7_candidates/remote_*`；不复制进生产素材，不当作本轮批准件。
- **分支纪律：**当前本地仍在 `arena/ba836be0-zhuochong`、HEAD `a85c706`。远端同名 ref 在 `d6fe833`。只做过 fetch/只读检查，没有 checkout、merge、reset、push；下一代理继续在当前分支工作，除非用户明确要求，不要把远端快照合并进来。

## 4. 当前文件与工作区状态

### 可用的项目基准

- `characters/xiaoxun/forms/teen/sprites/body_full.png`：原装 teen 全身图，短发颜色/人物比例的基准；只读。
- `characters/xiaoxun/forms/teen/rig.json`：现有 rig；只读，除非后续用户批准正式接入。
- `characters/xiaoxun/design/sheets/sheet_long.png`、仓库根 `小寻长发.png`、`小寻短发.png`：风格/发流/颜色参考，不是可直接抠成成品头发层的素材。
- 用户胸前发参考 `/tmp/arena-coding-uploads/image-1.png`（139×125）和短发颜色参考 `image-2.png`（270×204）：局部图分辨率有限，不可单独用于精确恢复旧 v4。

### 临时区

- `/tmp/t67_7_candidates/master_rebuild_unapproved_v1.png`：当前向用户展示的新 hair-only 母稿候选；848×1264 RGBA，仅候选，未批准。SHA-256：`13488baf23169915e107f7eecf9ac6805d08bd51c8464707ef1704267880e675`。
- `/tmp/t67_7_candidates/master_haironly_colorlock_v4.png`：与上项校验值相同的同一张新试稿早期命名，**名字里的 v4 不表示历史静止图 v4**；后续汇报优先使用 `master_rebuild_unapproved_v1.png`。
- `/tmp/t67_7_candidates/testroot/`：本轮补齐的隔离运行副本，含 `characters/xiaoxun/`、`web/`、`data/`、`config/`、`schemas/`、`tools/`，来自当前本地基线，不含本轮母稿候选，也不是已批准的候选 rig。尚未用服务以该 root 启动验证；需要候选预览时可按运行手册用仓库 `build/zhuochong_preview` 的 `--root` 指向它。所有试验输出仍须留在 temp。
- `/tmp/t67_7_candidates/remote_*`：从远端 `d6fe833` 只读提取的 v1/v2、后发 sprite、T67.39 QA 图；历史对照，不是生产素材。
- 前文提过的 `/tmp/t67_7_candidates/concept_xiaoxun_longhair_fullbody_v1.png` 当前文件系统中未找到。用户已在先前会话视觉批准该概念方向；找不到临时源文件不等于用户撤销批准。无需要求用户重传；按仓库参考和既有批准结论继续，若重新生成概念只可作为新稿并标明。

### 当前 repo 状态（本次交接上传范围）

- 当前分支状态为 `active`，本地 HEAD 基于 `a85c706`。本次交接只上传项目文档：`docs/HANDOVER.md`、`docs/REFERENCE_NOTES.md`、`docs/memory/WORKFLOW.md`、`docs/T67_7_REDO_PLAN.md`、本 handoff 与 sandbox runbook；不要因此误把临时试稿当成项目素材。
- teen 生产 PNG、`rig.json`、眼件/眉件没有因本轮分支审计或新试稿而改写；没有做生产接入。后续改动仍需逐文件审查并只提交用户批准范围。
- 5173 预览服务当前运行在仓库根（进程工具 ID `process-a5294a89`，C 预览 `--root /home/user/zhuochong --port 5173 --bind 0.0.0.0`），不是临时候选预览。`/` 和 `/test.html` 返回 HTTP 200。不要另起同端口服务。
- **`[测试锁]` 本轮文档交接时实际运行：** `make -s selfcheck` 为 544 项、0 不通过；`make -s test` 为 1058 项、0 失败；`make -s web-test` 的 web 内核 262 项、产品视图 20 项均为 0 失败。web 测试 stderr 中的故意异常/404/缺组件日志属于负向用例，命令退出码为 0。未运行 `make -s asan`、`make -s smoke` 或完整 `make -s check`，不可声称这些通过。
- **`[沙箱实测]`** 当前仓库根预览返回 `/` 与 `/test.html` HTTP 200；这是短发/仓库基线服务，不是新母稿的沙箱拼回验收。
- **`[需真机]`** 本轮未做 Windows 真机验证；相关项保持未完成。

### T67.7 完成/未完成任务台账

| 工作项 | 状态 | 证据/下一门槛 |
| --- | --- | --- |
| 用户要求、色彩基准、保护范围与六件 ID 汇总 | 已完成记录 | 本文件第 0、2 节、`docs/REFERENCE_NOTES.md` 与 `docs/memory/WORKFLOW.md` 铁律 0；用户验收优先 |
| Live2D 长发变形/物理教程核对 | 已完成记录 | `docs/REFERENCE_NOTES.md` T67.7 小节；只能参考结构，不得把本仓库 `physics2` 误称 Cubism |
| Python 图像环境恢复 | 已完成 | `/home/user/.imgenv/bin/python` 可导入 Pillow/NumPy/SciPy；若后续沙箱重建，按运行手册复装 |
| 最近代理分支只读审计与历史文件提取 | 已完成 | `d6fe833` v1/v2、T67.39 图均只在 `/tmp/t67_7_candidates/remote_*` 做参考；未 checkout/merge/push |
| 当前新 hair-only 母稿候选制作并向用户展示 | **试稿完成，视觉批准未完成** | `/tmp/t67_7_candidates/master_rebuild_unapproved_v1.png`；不能作为历史 v4 或六件成品 |
| 找回旧 `frame_static_long_color_v4.png` 与旧六件/临时 rig | **未完成且当前 Git 无法恢复** | 不得声称已恢复；上一轮未归档属于流程疏漏 |
| 新母稿用户目视批准 | **未完成，当前阻塞** | 用户没批准前不拆件；按反馈修图并重新展示 |
| 六件独立素材重建 | **未开始/未完成** | `acc_hair_long`、`hair_side_l/r`、`acc_hair_sidelong_l/r`、`acc_hair_crown_long`；必须同源、只含头发像素 |
| 临时 rig 静止拼回与接缝修复 | **未开始/未完成** | 全身 1×/1.5× + 头/胸/腰放大，透明 PNG 在白/灰/深底检查；具体断点先目视定位再局部修 |
| 六件动态/物理测试 | **未开始/未完成** | `ParamHairSway` 负向/中位/正向帧；静止截图不能代替运动验收，不用整片 `bend_y` |
| 用户批准的 QA 证据归档 | **未完成** | 验收结论依赖的图/数据入 `docs/qa/`；仅草稿留 `/tmp` |
| 生产素材/rig 接入 | **未开始；未获授权** | 先用户批准静态与动态候选，再评估最小接入；保护 teen 原画/眼件/眉件 |
| Windows 真机透明窗/穿透/拖拽/帧率 | **未完成 `[需真机]`** | 只能由用户真机验证，代理不代签完成 |

**仅作历史背景的远端状态：**`d91d03f` 的 T67.7 v1 是后发源件候选；`2d21610` 的 T67.25 `[x]` 只表示单一后发件拟合/接入；T67.39 `[x]` 是旧整身 rig 的静止复验。远端任务表仍将整个 T67.7 六组长发重造标为 `[~]`。这些完成项不转移为本轮六件任务已完成。

**全项目任务状态的唯一索引**仍是本分支当下可见的 `docs/memory/TASKS.md`、`GAPS.md`、`REQUEST_LEDGER.md`、`REQUIREMENTS.md`、`MEMORY.md` 与最新 `JOURNAL.md`；本 handoff 对 T67.7 做完整交接，不复制整份产品 backlog。注意当前本地 HEAD `a85c706` 早于远端 `d6fe833`，跨分支状态必须带提交号和时间，不能混成当前工作树事实。

## 4.2 查资料、学教程、看参考项目的做法

**学习先行是开工前置步骤，不是遇到失败才补做。** 但要按领域取真值源，不能拿一类参考替代另一类：画稿看用户批准的角色原设与同类发型实图；分层/变形看 Live2D 官方文档与成熟模型制作教程；工程行为看仓库实现、测试和参考项目源码；产品交互看真实产品运行结果。

### 推荐查证流程

1. 先读本仓库既有结论，避免重犯已否决路线：`docs/memory/WORKFLOW.md`、`docs/memory/POSTMORTEM_ART.md`、`docs/ART_PARTS.md`、`docs/SHEET_PIPELINE.md`、`docs/REFERENCE_NOTES.md`，再读 `docs/memory/LESSONS.md`、`GAPS.md` 与 `REQUEST_LEDGER.md` 相关段落。
2. 先找官方/原始来源；搜索关键词要具体到待解问题（例如 Live2D long hair deformer, hair part overlap, mesh skinning, alpha edge keying），优先官方手册、官方教程、原始项目源码。`image_search` 用来观察发束结构/比例，不可把陌生角色参考直接当小寻素材。
3. 在沙箱可用时用网页搜索与页面读取工具核对文档；如果需要读 GitHub 源码，按 `docs/memory/WORKFLOW.md` 使用 `bash scripts/fetch_references.sh` 或 `gh api` 只取相关树/文件。缓存放仓库外 `~/.cache/zc-refs/`，只取所需文件；用完按需 `bash scripts/clean_references.sh`。不要把整个参考仓库/大数据集放入项目。
4. 记录每个影响方案的来源：标题、准确 URL、访问时间、引用到的章节/文件/函数、得到的具体结论、如何用于本仓库、适用边界/许可证；追加到 `docs/REFERENCE_NOTES.md`，涉及实现时在代码注释/任务记录中链接。不得只写“查过教程”。
5. 依据外部教程前先确认其模型/引擎语义与本仓库是否相同。此仓库是自有 C sprite rig / mesh deformer / `physics2`，不是原生 Cubism `.moc3`；可以吸收根到梢、分段、延迟和遮挡等结构思想，不能称接口兼容或照抄数值。
6. 看到了参考后仍须回到用户批准的原设和实际本项目画面。参考只能帮助回答“结构怎么做”，不能推翻用户指定的颜色、比例、画风或已经否决的方案。

### 本任务已查的权威/可复核来源

- Live2D 官方 [Adding Body Movement](https://docs.live2d.com/en/cubism-editor-tutorials/deformer/)：前/侧/后发按运动区域组织；发梢产生形变，不把整张发片当整片垂直拉伸。
- Live2D 官方 [Adding XY Facial Movement](https://docs.live2d.com/en/cubism-editor-tutorials/xy/)：前、左侧、右侧、后发分别考虑变形器与父子关系；纵长部件可参考 2×3 网格分区。
- Live2D 官方 [Skinning](https://docs.live2d.com/en/cubism-editor-manual/skinning/)：先建立 mesh/deformer 父子层级，再沿发根到发梢处理 skinning；需逐项检视形变；不要据此声称本仓库实现了 Cubism skinning。
- Live2D 官方 [Physics Settings](https://docs.live2d.com/en/cubism-editor-tutorials/physical-calculation-settings/)：多段摆链的结构参考；实际参数要按新图和当前引擎目视/实测。
- CLIP STUDIO 官方 [Live2D 用イラストのパーツ分け](https://tips.clip-studio.com/ja-jp/articles/2684)：线稿边界、分层切件的参考；更多项目化结论已存 `docs/SHEET_PIPELINE.md` 与 `docs/REFERENCE_NOTES.md`。

### 项目级参考仓库（只学结构，不挪代码/素材）

| 项目 | 入口/许可证 | 适合研究 |
| --- | --- | --- |
| [BongoCat C/SDL](https://github.com/vladelaina/BongoCat) | AGPL-3.0 | 原生窗口、渲染和输入结构；许可证限制严格，只学习，不复制代码/素材 |
| [BongoCat Tauri](https://github.com/ayangweb/BongoCat) | Apache-2.0 | 跨平台输入、动作组织、模型切换 |
| [ds-local-pet](https://github.com/QCYTSN/ds-local-pet) | MIT | Python 桌宠状态机、闲置与交互组织 |
| [VPet](https://github.com/LorisYounger/VPet) | Apache-2.0 | 桌宠交互、模组/插件和用户可见行为 |
| [airi](https://github.com/moeru-ai/airi) | MIT | Web/桌面 AI VTuber 架构、语音管线和 Live2D 集成边界 |
| [CubismWebFramework](https://github.com/Live2D/CubismWebFramework) | Live2D Open Software License；Cubism Core 专有 | 官方框架调用顺序、网格/参数/遮罩实现；框架开源不等于 Core 可自由再分发 |
| [photocraft](https://github.com/storytold/photocraft) | 使用前逐次核对仓库许可证 | 图层/选区/蒙版与图像编辑实现；只作工具思路参考，不复制 UI、代码或素材 |

更大的参考地图与具体源码路径在 `docs/memory/WORKFLOW.md` 的“查证顺序”和 `docs/REFERENCE_NOTES.md`（包含 MinikoMew 等用户点名参考）。每次引用先复核当前许可证与版本；不复制第三方艺术资产、模型或代码。外部搜索结果不能只看摘要，能读原始文档/代码就读原文，并把不确定性写明。

## 5. 继续施工的严格顺序

1. 先查看 `master_rebuild_unapproved_v1.png` 的原尺寸、透明底、白底/深底放大图；核对发流、左右束衔接、发梢、颜色断层、边缘溢色、透明区是否只有头发。与短发基准并置，不能只看数值。
2. 等用户对这张**新母稿**作目视确认/修改指示。当前还没有获准拆件；不要先做六件或暗中当成通过。
3. 获准后，在 `/tmp` 的独立 teen rig 副本上按自然遮挡关系拆六件；每件仅取自已批准 hair-only 母稿。隐藏遮挡区需合理补足，留足自然重叠，不得复制失败旧碎片。
4. 静止拼回后至少输出全身、头部放大、胸前/腰部放大三张；白/深底都检查。重点用眼睛定位真实缝隙和色块断点，再针对具体区域做修复；不得全局盲目套色。
5. 静止无缝并获得用户确认后，再做六件独立参数/网格测试，测试 `ParamHairSway` 负向/中位/正向帧；每个状态目视检查是否露缝、穿模、硬切或锁片漂移。静态截图不算动态通过。
6. 用户明确批准后才讨论生产接入。若某结论依赖特定帧图/颜色对照/QA 数据，放入 `docs/qa/` 并说明对应任务号；中间草稿仍放 `/tmp`。入库证据不自动代表生产接入批准。
7. 真机运行、透明窗/像素穿透、拖拽手感和实际帧率均留给用户；标 `[需真机]`。

## 6. 给下一代理的禁区清单

- 不要把远端 `d6fe833` 当成当前工作树或直接 checkout/reset 到它。
- 不要声称找回了旧 v4；不要把新母稿、远端 v1/v2、T67.39 定帧图相互混称。
- 不要要求用户重新上传旧 v4/已看过的概念图；Git 中没有旧 v4，应直接诚实说明并按获批方向产出一个明确命名的新候选。
- 不要在仓库正式目录运行 `tools/rebuild_parts.sh`、会覆写 sprites 的生成器或 `apply_hair_only.py`。先确认脚本的 `--root` 是否真能指向 temp；不支持时，把必要的源码/数据复制到 `/tmp` 再运行。
- 不要因为 `make test`、`selfcheck` 或色彩统计通过，就宣称头发视觉验收通过。
- 不要修改 teen `body_full.png`、九态眼件、闭眼/笑眼、眉件或核心 C 引擎来绕过头发素材问题。
- 不要把测试台当产品 UI，也不要把沙箱预览当 Windows 真机验收。

## 7. 本轮交接文件

- **完整交接（主文件）**：`docs/T67_7_HANDOFF_NEXT_AGENT_2026-10-27.md`（本文件；仓库内路径）。
- **沙箱运行教程**：`docs/T67_7_SANDBOX_RUNBOOK.md`：项目级构建、Live Preview、隔离 testroot、自动回归与目视验收步骤。
- **施工计划与审计**：`docs/T67_7_REDO_PLAN.md`：设计、验收门槛、环境恢复与历史分支核查。
- `docs/HANDOVER.md` 顶部已设置当前任务入口，指向以上交接与运行手册。

## 8. 给下一代理的性格与思维设定（可直接转交）

> **性格设定：**认真、耐心、主动、谨慎、诚实，以用户目标和视觉质量为中心；不敷衍、不虚报，也不擅自把任务改成自己更方便的方向。遇到问题先查证和看实际结果，能自行解决的先做；只在确实被阻塞或存在关键歧义时才向用户确认。
>
> **思维设定：**先把用户最新要求拆成验收清单和禁止事项；再找该领域的真值源、查官方教程/参考项目并记录出处；在 `/tmp` 隔离制作；本人打开实际图像/预览，按全画面到放大细节逐处检查、定位后修复；然后跑适用的自动测试；给用户看真实结果并等批准；最后才考虑生产接入和证据归档。数字、测试全绿、旧交接和 AI 默认都不能代替用户要求与本人目视。每次汇报分清已完成、未完成、阻塞和证据，不把静态结果说成动态通过，也不把沙箱说成真机。

## 9. 用户给下一代理的话（可直接转发）

> 我的要求永远排第一。请先看清实际结果、查找可信资料，按交接里的顺序一步一步做；每次修改后亲自检查图像和预览，发现问题就定位并修正，不要拿数字或“测试全绿”代替验收，也不要让我重复说明已经确认过的要求。
