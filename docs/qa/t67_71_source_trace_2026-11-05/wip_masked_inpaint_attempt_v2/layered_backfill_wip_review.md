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
