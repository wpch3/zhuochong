# T67.71 艺术来源交接单（仅定位请求，不是重建）

**状态：阻塞输入用交接资源。** 这不是发丝候选、不是隐藏拓扑草图，也没有任何像素被本文件补画、转移或推断。没有候选通过局部视觉门；未进入真实 C；未改生产素材、rig、生成器。

## 目标与实物依据

目标是 Teen 长发 + hood-up 组合里，手臂/袖口遮挡处的后层发丝应连续，移动手臂时不出现空洞、袖口/手形残留或错误遮挡。

- 扁平原图：`characters/xiaoxun/design/sheets/sheet_long_hood.png`（1024×1536 RGB）。它能显示可见的头发、手与袖口，但被手/袖遮住的头发像素不存在于图中。
- 提取件：`characters/xiaoxun/design/redraw/sheetcut_hair_hood_long.png`；其 hair cutout 把袖口/手的一部分一起带入。
- 当前运行件：`characters/xiaoxun/forms/teen/sprites/hair_hood_long@2x.png`（1132×1664 RGBA）。左右 ROI `[51,849,396,1368]` 与 `[736,849,1081,1368]` 只用于查验，**不是**异物 mask 或目标发束 alpha。
- C 引擎来源链及大图/局部源证据：`../../t67_71_source_trace_2026-11-04/README.md`、`source_trace_board.png`、`capture_metrics.json`。真实 C 的动作矩阵已经证明静态旧袖口/手形随 hair 件出现；隐藏目标件后，动作中的真实手臂仍在。当前 `acc_hair_hood_long` 位于 layer 258，正常手臂在 138–151，惊讶替换件在 319–322。额外目视核对了 `hair_long_back@2x.png`、`hair_hood_pony@2x.png`、`hair_hood_twin@2x.png`：它们各自的发型轮廓/走向与目标不同，只能作画风旁证，不能证明这处隐藏发丝真值，也未抽像素转移。后续发现并目视核查早期 T67.7 `hair_long_backonly_v1/v2`（源自非 hood-up 长发路线）：v2 颜色/材质更接近，但中心分缝、连续中片、轮廓和发束走向仍不匹配；v1 还有中心开口与可见绿色边缘杂点。比较图 `109_backonly_source_audit.png` 只用于记录来源适用性，两个文件均不是目标隐藏发丝真值或修复 donor。
- 本单配图 `105_artist_handoff_reference.png`：左图为扁平上下文与近似回映 ROI；中央为旧 raw cutout 局部；右侧为当前 production sprite 局部（带 alpha 棋盘）。框只定位证据，不能用来推定隐藏头发轮廓。图中无候选。

## 请提供的可审阅来源资源

首选：本造型获批的分层作者工程（PSD/KRA 或等价可编辑分层源），并标出以下部分的关系：

1. **连续的后层长发**：在手/袖口后方补全被遮挡区域，左右两侧分别绘制，不镜像假设；保留与当前可见发束连续的自然走向、色相/明暗、边缘和负空间。
2. **可动手臂/袖口前景**：手、袖、袖口必须是独立可控的真实前景部件，不能烘入头发图层。后发应在结构需要处连续，手臂移动/隐藏时也不能露透明洞。
3. **必要的头发前层**：若发束需要压在某些动作层前，应明确给出前层/后层关系和遮挡边；不能用同一张含旧静态手形的 hair PNG 代替。
4. **配准导出**：保留原画坐标/画布注册，交付可编辑工程及透明 RGBA 导出；另附图层名、画布尺寸、导出比例和对齐变换。若没有原作者分层源，可交作者明确标注为“新补画”的隔离修复层，并由项目方审阅其设计走向；不可称作恢复出来的原像素。

不需要、也不接受：透明棋盘格被烘入 RGB、靠 `alpha=255` 填满整图、仅清掉手袖而留下洞、沿手/袖剪影描出新头发、未经审阅的镜像对称、拿不同造型的后发像素直接冒充隐藏真值。

## 后续制作与验收顺序

0. **来源接收**：核对角色/发型/兜帽造型、许可/作者来源、编辑图层、坐标注册与原始/导出 SHA。源不明确则停止。
1. **隔离制作**：把作者层导出到独立 QA 目录；保持完整画布与 RGBA；不覆盖 `characters/xiaoxun/forms/teen/sprites/`，不改 rig/生成器。
2. **代理局部目视门**：本人查看整件、全身合成、左右 ROI 的 100%/200%/400% 放大与浅/深底。逐项判断发丝连续、自然流向、色相/明暗、线密度、边缘与抗锯齿、透明负空间、异物是否完全移出头发。局部不合格即拒绝并停止；不能为进 C 而调阈值或把失败候选叫进度。
3. **真实 C 隔离验证**：仅局部门通过后，将副本装进真实 C。保持动作与 `ParamHairSway` 分开：idle、surprised、wave、wave_both、heart_hands 代表态；动作进出与关键转场；`ParamHairSway=-1/0/+1` 独立扫；目标件 only/hidden、正常层序与全身/局部同步抓图。检查不同手臂高度下的遮挡边、洞、旧残留、穿插与 sway 归因。动作/转场失败就退回局部或源层，不准进生产。
4. **生产候选门**：只有来源可追溯、局部目视与真实 C 动作/转场矩阵均通过，并经用户批准后，才讨论生产替换；届时先审精确 diff，再更新生产 QA/清单。

## 本轮已完成和未完成

- 已将源链、错误像素归属、当前 ROI 与严格门顺序整理成一页图板和本单，方便作者/美术提供明确来源输入。
- **核心修复尚未推进到通过**：新审的 `hair_long_backonly_v1/v2` 是较早非 hood-up 的长发单独素材；v2 仅为较接近的画风/材质旁证，不提供目标隐藏形状。没有发现新的同造型分层头发真值；本单不是作者补画，也不声称发丝问题已解决。
- 下一步只在收到获批分层源或作者明确补画资源后，按上述第 0 步开始；在此之前不继续生成相似猜测条带，也不进入 C。

## 可复核文件

- `105_artist_handoff_reference.png` — source-only 图板，2800×1840；
- `make_t67_71_artist_handoff_sheet.py` — 图板生成器，只合成现存来源/ROI，不绘制候选；
- `106_artist_handoff_metrics.json` — source/target/hash、ROI、状态及 no-inference 声明；
- `107_T67_71_registered_artist_template.ora` — 1132×1664 OpenRaster 空白工作模板：含空白 `Clean hair plate`、左右独立 back-hair 空图层、仅 ROI 框线的 guide，以及可见但标记为不可导出的当前生产参考图。没有新头发像素、没有批准来源、不得直接导出为修复；作者只在空白草稿层中创作，提交前须另做局部视觉门。
- `107_artist_template_preview.png` 与 `108_artist_template_metrics.json` — 模板预览及图层/尺寸/透明空层/参考像素身份的结构核验。已验证 ORA ZIP 结构、canvas 尺寸、图层顺序、空层透明和 reference/merged 像素；当前环境无 Krita，尚未由图像编辑器实际打开验证。
- `make_t67_71_registered_artist_template.py` — 模板生成与结构核验脚本；仅依据当前生产 PNG 建坐标模板，不绘制或推断发丝。
- `109_backonly_source_audit.png`、`109_backonly_source_audit_metrics.json`、`make_backonly_source_audit.py` — 比较当前目标左右 ROI 与早期 hair-only v1/v2 的来源适用性；只作画风/形状差异记录，不是候选或验收。v2 不是同造型真值，不能转移像素。
- `SHA256SUMS.txt` — 本目录归档哈希。
