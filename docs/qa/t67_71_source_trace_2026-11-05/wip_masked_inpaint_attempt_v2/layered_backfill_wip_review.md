# T67.71 — 分层补发 WIP 目视复核（2026-11-05）

**状态：未解决；没有候选通过；未改生产素材、rig 或生成器。** 本记录保存的是失败候选的证据与下一步，不是验收。

## 已知来源与边界

- `characters/xiaoxun/forms/teen/sprites/hair_hood_long@2x.png` 是被测长发精灵；`sheet_long_hood.png` 是角色整张扁平图，不是可还原遮挡后笔触的分层原稿。
- 袖口、手掌、手指和抗锯齿边缘在发件上可见；被遮挡处的真实发束走向、重叠和透明间隙未知。
- `manual_artifact_polygons_v2.json` 圈的是**可见袖口/手部异物定位 ROI**，范围覆盖完整袖口带及手部，但也吃进相邻合法头发。它不是发丝真值，也不是可直接整体清空的清理 mask。
- rig 投影区、可见异物 ROI、推断新发丝 alpha 仍是三类不同的信息。

## 本轮真实视觉试验与否决

1. `43_layered_clean_front_hair_wip.png` + `44_layered_manual_backfill_wip.png`：前发层 alpha 按扩大异物 ROI 清空，后发补片层放在临时 layer 135（手臂 layer 138–145 后方），原件留 layer 258。第一次把新 alpha 裁到异物 ROI，**C 对照拒绝**：补片边界复刻了袖口/手掌剪影，静止/挥手时露出手形白片。仅清前层而不补发的临时对照也出现黑洞。见 `c_layered_backfill_wip/48_base_vs_layered_wip_paired_board.png` 与 `cleanonly_wave.png`。
2. WIP2 `51_backfill_freeflow_inference_v2.png` 不再按异物 ROI 裁发丝；但宽度曲线在局部审阅中形成尖叶/三角几何。真实 C 的 idle、`wave`、`wave_both` 对照仍出现过尖/过宽的露出发片，**拒绝**。见 `54_backfill_v2_isolated_review.png`、`c_layered_backfill_wip/53_base_vs_layered_wip2_paired_board.png`。
3. WIP3 `56_backfill_freeflow_inference_v3.png` 改成长宽度平台、尖端渐收；放大局部仍显人工矢量尖片，与邻接手绘发束质感不合，**在局部风格门拒绝，未送 C**。见 `58_backfill_v3_local_review_board.png`。

## C 复核范围（仅探索，不是验收）

- WIP1/WIP2 与 production base 都由真实 C 引擎输出，分别观察 `idle/rest`、`wave`、`wave_both` 的代表帧。它们不是完整动作矩阵，也未验转场。
- `ParamHairSway` 请求值与 arm action 分开控制：WIP1 另存了请求 −1/0/+1 的探索截图，但这**不证明目标件独立运动**，不能把它当作发束 sway 验收。
- 候选测试 rig 和精灵仅在 `/tmp/t67_71_layered_backfill_c_root` 临时副本；不在工作树生产目录。

## 可复核产物

- 扩大可见异物 ROI：`39_manual_artifact_mask_v2_review.png`；原始像素上下文：`49_raw_source_cuff_hand_crop_review.png`。
- 前层清理 + 分层 WIP 指标：`45_layered_backfill_metrics.json`、`52_layered_backfill_v2_metrics.json`、`57_layered_backfill_v3_metrics.json`。其中 ROI 外字节不变只证明写入范围，不代表局部画面正确。
- WIP1 动作与 sway 探索：`c_layered_backfill_wip/47_c_layered_backfill_exploration_board.png`；base/WIP1：`48_base_vs_layered_wip_paired_board.png`；base/WIP2：`53_base_vs_layered_wip2_paired_board.png`。

## 2026-11-05 追加：后续候选均未过局部门

- 颜色阈值 mask 与完整可见对象轮廓 v3 只作清理诊断；近白扩张 12/18→24/36 px 仅新增 5 px 命中，仍漏白袖带/手部内区。没有通过颜色阈值把异物逐像素分净。
- 分层后发 v4–v7 的局部板（`82_backfill_v4_local_style_review.png`、`86_backfill_v5_local_style_review.png`、`95_backfill_v6_style_review.png`、`99_backfill_v7_style_review.png`）显示几何色片、过尖条带或过宽平涂 sheet；均拒绝，未进 C。AI 局部结果 91/92 未保留裁切上下文，也拒绝。
- **新方法单次测试：`hair_long_back_v2.png` 字面像素纹理转移 v1。** 用 donor crop `[260,430,480,800]`（220×370，选区内近洋红像素 0）产生独立曲线锁 alpha；alpha 不从袖口/手形 mask 派生。产物 `101_hair_long_back_v2_texture_donor_crop.png`、`102_texture_transfer_underlay_v1.png`、`103_texture_transfer_v1_local_review.png`，脚本/metrics 为 `make_hair_long_back_texture_transfer_v1.py`、`104_texture_transfer_v1_metrics.json`。
- **本人放大目视拒绝 v1，止于局部门，不送 C：** donor 的深直线/冰蓝色块与目标局部紫粉、软渐变和线密度不合；复核板中转移结果呈直硬条带、端头截平，且清除手/袖后周边仍有大块未补区域。零洋红像素只是来源检查，不证明纹理/形状匹配。不要继续微调同一 donor crop、宽度或条带遮罩。

## 下一步（阻塞输入）

既有可用来源没有被遮挡后的长发真值：`sheet_long_hood.png` 是扁平图；`hair_long_back_v2.png` 是不同造型的独立后发设计，只能作风格参考，直接像素转移已在局部门失败；目标贴图邻近露出像素不足以可靠确定隐藏发束拓扑，且含衣物/身体残留风险。下一次制作需先取得获批的同造型分层源/隐藏发束原画，或有作者提供的明确补画；再独立标注“异物清理 mask”与“新发丝 alpha”。若没有新来源输入，不再生成相似的猜测条带。局部视觉门通过之前不进真实 C；通过后才跑完整动作与转场矩阵，arm action 与 `ParamHairSway` 分开归因。隐藏源形状仍未知，任务未解决。

## 2026-11-05 追加：作者来源交接资源（非候选）

- 为推进被阻塞的来源输入，而不再猜隐藏发束，新增 `105_artist_handoff_reference.png`（2800×1840）、`105_artist_handoff_brief.md`、`make_t67_71_artist_handoff_sheet.py` 与 `106_artist_handoff_metrics.json`。图板只拼合现存扁平来源、旧 cutout 局部与当前 production 贴图 ROI，并叠加近似源坐标框；没有创建、补画或转移任何头发像素。
- 本人重新打开图板：左侧框准确定位到扁平全身源里的手/袖位置，但原图本身不含其遮挡下的头发像素；中央 cutout 清楚保留袖带和手指；右侧 production ROI 同样显示烘入 hair 件的旧袖口/手像素。其邻接可见头发只能提供风格上下文，框、透明块和异物轮廓都不能证明隐藏发束形状。
- 另外目视检查 `hair_long_back@2x.png`、`hair_hood_pony@2x.png` 与 `hair_hood_twin@2x.png`；轮廓/发束方向均与目标不相同，最多作画风旁证，不作为像素 donor。没有因此制作新候选或启动 C。
- brief 要求交付本造型获批分层作者工程或明确标记的新补画层，分离完整后发与可动手/袖前景、保留坐标注册；依序执行来源核验 → 隔离导出 → 局部目视门 → 真实 C 动作/转场与独立 `ParamHairSway` 矩阵 → 用户批准 → 生产。当前仍没有作者源输入、没有局部门通过，也没有 C 验证或生产改动。

## 2026-11-05 追加：坐标注册的空白作者工作模板（非候选）

- 为让后续作者输入能直接套准当前 2× 发件，新增 `107_T67_71_registered_artist_template.ora`（1132×1664）和 `107_artist_template_preview.png`。ORA 图层为：空白 clean-hair 草稿、左右独立且空白的后发草稿、仅 ROI 框线的 guide、当前生产 PNG 参考层。参考层默认可见以便定位，但必须在输出前隐藏；橙/蓝框只表示既有 QA crop bounds，不是新发束边界、目标 alpha 或清理 mask。
- 本人打开预览：当前头发仍能看到中间片、左右长发与目标 ROI 里的袖口/手形；两个矩形框覆盖的是检查区域而非推断发丝外形。三个草稿层透明为空，没有任何新增笔触/像素。该文件是制作模板，不是画稿、候选或批准源。
- `make_t67_71_registered_artist_template.py` 生成模板和预览，并结构检查 ORA mimetype/图层顺序/画布、三张空白透明层、reference 像素身份与 merged image；metrics `108_artist_template_metrics.json`。本地无 Krita，故只做容器结构验证，未声称在 Krita 实际打开成功。
- 这一步只降低之后的配准/分层摩擦，不解决隐藏发丝真值。仍需获批同造型分层源或作者明确补画，局部门目视通过前不启动真实 C，也不改生产。

## 2026-11-05 追加：早期 hair-only v1/v2 来源适用性复核（非候选）

- 追看 `characters/xiaoxun/design/redraw/hair_only/hair_long_backonly_v1_raw.png`、`hair_long_backonly_v2_raw.png` 及对应透明处理图；它们属于早期 T67.7 的非 hood-up 长发“髮だけ差分”路线，处理后均为 843×1264。
- 对照板 `109_backonly_source_audit.png`：两侧 target ROI 与两张完整 hair-only 片并列显示。v1 有中心开口、双侧长发和可见绿色边缘杂点；v2 是较连续的中心后发片，色相/材质比此前 `hair_long_back_v2` 更接近目标，可作为**画风旁证**，但中心分缝、外轮廓、发束流向与 hood-up 目标不同，也无目标画布注册。它不能证明袖口/手后隐藏头发的拓扑。
- 结论：两张图都不作目标真值、修复 donor 或候选；该阶段没有转移像素、绘制头发、跑 C 或改生产文件。配套 `109_backonly_source_audit_metrics.json` 记录路径、尺寸、alpha、SHA 与限制，`make_backonly_source_audit.py` 只合成现存图像。后续仍需获批同造型分层源或作者明确补画；不因发现相似画风资源而放宽来源/局部门。

## 2026-11-05 追加：查阅绘制参考并自审新路线（全部拒绝，未进 C）

- **参考核查**：查 Live2D 官方 Illustration Processing 与 Template Tutorial、CLIP STUDIO PAINT 官方/MUGENUP 合并图拆件教程及 Krita 图层手册；结论是被遮挡区域确需在分层前补绘，左右后发/侧发应按可动关系组织；合并图拆件时要新画被遮住背景，并叠回原图检查。官方/社区通用流程不能给出本目标隐藏发丝真值。来源及项目映射已记 `docs/REFERENCE_NOTES.md` 第七十四批。
- **项目/历史搜索**：本轮查看 `hair_back@2x.png`、`hair_crown_long@2x.png`、`design_sheet_midlong.png`、`pose_ref/hair_turn.png`，并重搜 `characters/xiaoxun` 全部 long/hood/hair 素材、Git refs 与 unreachable commit 树。可见项均为不同发型/hood 状态或扁平来源；无 PSD/PSB/KRA/XCF 或同造型作者层。它们只能作通用风格旁证。
- **尝试 A — 同图按列纵向续纹**：`make_author_redraw_inpaint_v1.py` 依两端邻发像素跨 cuff/hand mask 线性补色。本人查看 `111_author_redraw_inpaint_v1_local_review.png`：遮挡区形成明显竖向色污/条带，仍有残余对象痕迹；方法拒绝。产物 110/111/112 是负例，未作为艺术候选进 C。
- **尝试 B — 生成式整发重绘**：输入现 production sprite 后，`113_ai_author_redraw_v1_wip.png` 输出 848×1248 RGB、不含 alpha、白底且整体发型轮廓/发束重新设计。与 113 input target 画布及像素内容不兼容，零像素抽取/转移；`113_ai_author_redraw_v1_metrics.json` 记录拒绝事实。
- **尝试 C — 新画左右后发底片 + 清理前层**：`make_author_backhair_redraw_v1.py` 按“左右独立 back plate 置于实际可动 arm/cuff 后、侧发前置”的新工序做了 114–118 隔离图。本人放大查看 `116_author_backhair_redraw_v1_local_review.png`：新底片显平直硬块，色面/边缘和目标发束不融；clear-front 仍残留若干非发/边缘痕迹；未与真实手臂合成，因此无法通过局部门。拒绝，不送 C、不改 rig/production。
- **诚实判断/停止线**：不是缺少脚本或图层知识，而是高质量新补绘本身需要针对特定笔触做艺术绘制；当前可复核源缺少遮挡后形状，本轮三个自动/半自动做法均没达到局部视觉线。我未遵守 A69.2 的“无同造型来源不再猜画”约束而做了这些 WIP；现明确将其全部列为已拒绝负例，不作进度/通过。为了避免再空转，不再微调这三路，不进 C。下一步若继续绘制，需要获准的原画层，或明确授权一个“新的设计重绘”方向；新重绘只能作为 proposal，需先经本地视觉门/用户确认，绝不能称为隐藏真值。

## 用户授权“贴近现有方案”的新设计重绘后续（2026-11-05；仍未通过）

用户随后明确授权新设计提案，但要求不要和目前方案有太大出入。记录为 A69.4：此授权允许作新设计，不构成原像素恢复、隐藏真值或对具体候选/生产的批准。故本节 119 起的设计实验属于用户授权之后的 WIP；110–118 仍是授权之前的偏离约束负例，不追溯改成合法来源。

- **119 全头发 AI study：拒绝**。`119_backhair_strand_redesign_study.png` 输出完整后视头发造型、对称分缝和大轮廓，而输入/目标只是局部袖手 ROI。离目标过远，不抽取任何像素，不作 donor。
- **122/123 局部 AI proposal：拒绝**。使用 120 左右 crop 作为注册参考，生成 `122_left_backhair_local_redraw_proposal.png`、`123_right_backhair_local_redraw_proposal.png`，并检查 `124_ai_local_redraw_alignment_review.png`。局部更贴近发色，但黑色袖口/手部沟痕被带入候选；单纯按原有 alpha 贴回还使对象内透明槽继续透空。不是候选。
- **133/134 cleaned-guide proposal：拒绝**。把 cuff/hand 区先遮成灰紫引导形再生成，黑线有所减少但发板扩大为大块面，细线与原发束比例不符；区域内置换幅度过大。
- **139–161 alpha-mask 修正/strand proposal：拒绝**。先发现源 alpha 在 cuff stripes/hand mark 内有透明洞；原 alpha 截板会留下黑色洞，故将手袖 silhouette 与旧 alpha 联合。对象边缘 mask 2px 时污染残留；扩张到 18px 后，v5 clean-guide 仍像平板硬板。改用细线多 strand 的 v6 (`158`–`162`) 后，本人打开完整图 `160_clean_hair_composite_redraw_v6_wip.png`、board `161_backhair_local_redraw_v6_review.png`，并 3× 放大右 ROI：其色材较接近，但新板有一条横向平顶、内侧白楔/尖角和右下暗痕，不能保证手臂动作时边缘自然。拒绝，不进 C。
- **163–167 OpenCV inpaint + alpha union：拒绝**。Telea / Navier-Stokes 在 broadened cuff/hand mask上虽能补 RGB，联合 alpha 后仍出现明显几何云团/色块，不是发束画法。review `166_inpaint_alpha_union_review_v3.png` 记录。
- **结论/下一步**：已试局部 AI、干净 guide、alpha-hole 修复与两类 inpainting；截至 v6，没有通过局部目视的提案。此处真实工作不是更换 script 名称，而是熟悉原角色笔触的画师做连续细束、轮廓收口并保持与现有宽侧发小幅接续。已明确暂停同类自动生成/微调，不送真实 C。用户的“新设计提案”授权已经有效，无需重问授权；需要的是能达到美术质量的作者手工层。之后用户确认实际图稿和本地目视过门后，才进入 C 动作/转场，生产另审批。
- **验证边界**：所有编号 119–167 均是隔离 QA / guide / 负例；局部 mock 中复用的旧手袖只检查坐标，不是实际可动手臂或 C 验证。未修改 production sprite / rig / generator / engine。

## 2026-11-05 续作：隔离手绘连续层与同目标纹理网格试验（全部未过局部门）

用户最新要求是确认未完成就继续制作，且不能把已失败的 AI/inpaint/扩 mask 换名重跑。先重读当前 branch、工作区、`WORKFLOW.md` 铁律、A69.4 与本节旧负例；`make test` 基线为 2638/0（C-only，不是图像验收）。本轮没有恢复仍保留的旧 stash；当前生产精灵、rig、generator 均未改。

### 隔离手绘线条试验（handpainted_continuation_v1–v4）

- 新建 `docs/qa/t67_71_source_trace_2026-11-05/handpainted_continuation_v1..v4/`：由手工指定左右独立的 Bézier 线流和渐变、单独导出后发层；与已拒绝的 image-generation、OpenCV inpaint、18px mask 膨胀不同，没有 AI 或清理扩张。异物清理仍用单独 polygon mask；新发 alpha 没有从手/袖轮廓复制。
- 本人打开每轮 review board 与 3× ROI 后全部拒绝：v1 是浮离既有发件的细小交叉丝；v2/v3 的尖叶形大面与黑洞不连贯；v4 虽改成低对比宽板和较直的向下流线，3× 仍呈独立几何片，和已有边缘发束的连接/线密度不足。遮挡物 trace v3 也留下可见轮廓痕迹；采用较宽的 manual polygon v2 后只解决清理覆盖，仍会擦掉一部分邻接头发，不能单独当发丝 alpha。四轮均未通过局部风格门、不送 C。

### 同目标精灵纹理网格（same_sprite_warp_v1–v3）

- 新建 `same_sprite_warp_v1..v3/`。与 `hair_long_back_v2.png` 外形不同的旧 donor 试验有别，此次只以目标 `hair_hood_long@2x.png` 本身下段可见后发作**新设计纹理参考**，将 fully-opaque source patch 经 2-D remap 放进另行手绘的局部后发轮廓；没有拿手/袖 silhouette 作发丝 mask。它仍是重建假设，不是 hidden truth。
- v1 因 donor crop 含透明边/underlying RGB，3× review 可见黑洞和硬切；v2 限定全不透明样本并修正 alpha，黑洞消失但顶边是明显水平硬切；v3 将根部延入现有侧发下方并对顶/尾做渐隐。本人逐项看 `same_sprite_warp_v3_review.png` 与保存的左右 3× clean/static crops，纹理与现发色材更接近，但新增板仍读作一片独立的大面，内侧有一条过直且突出的深色竖线，和手袖前景相交处局部成楔口；静态 mock 只用于注册查看，不是实际 C 手臂。v3 仍拒绝，不送 C。不要继续微调同一 remap 区域或遮罩宽度。

### 本轮结论 / 下一步门

这是实际的隔离绘制与 texture-remap 试作，但没有一项成为可交付候选。用户授权的新设计范围仍有效；这些形状仅能称为新设计 WIP，不能说成原像素或隐藏真值。局部目视门不通过，所以没有启动真实 C 动作、转场、`ParamHairSway` 分离验证，也没有任何生产接入。记录真实困难：脚本能套准、但当前合成形状仍有明显“板/片”读感，无法靠调宽度/alpha/换同 donor 局部达到角色原画级质量。后续继续工作须采用真正有新增艺术结构依据的方案（不可再重复已失败的同形几何板/同源 remap），并先把左右全件及放大图看过；不得把寻画师建议或本记录本身当作核心修复。

**可复核文件**：`handpainted_continuation_v1..v4/` 各自 script/metrics/review/composite；`same_sprite_warp_v1..v3/` 各自 script/metrics/underlay/review/static mock；v3 左右 clean/static 3× crops。统一 SHA 清单：`docs/qa/t67_71_source_trace_2026-11-05/continuation_experiments_SHA256SUMS.txt`。
