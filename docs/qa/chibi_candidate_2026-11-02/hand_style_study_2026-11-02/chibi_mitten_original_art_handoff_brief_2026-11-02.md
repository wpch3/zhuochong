# Chibi `mitten` 原画交接单（来源/结构 brief，不是画稿）

**状态：需求约束与来源测量说明；不是新手稿、生产素材或用户批准。** 本文不绘制手形、不描摹 AI 轮廓，也不复用用户标记截图像素；目的是让下一张合规 Chibi 原画一次性满足拆件/引擎前置条件。

**后续概念进展（2026-11-03）：** 用户先选择 AI 全身 trial07 option 2 作为概念方向，随后明确确认 trial08 全身视觉概念“非常好，符合了”；这只批准视觉方向。trial08 像素直接抽取套入 source cuff 的尝试目视失败（有缝或手过短）。trial09 左右独立 AI hand-art source-cuff fit 后由用户明确拒绝：全身源位置上的手显得过小且不自然/观感差。尽管 source cuff 层的 RGBA 身份验证通过，不能据此声称手件验收；trial09 仅作为失败证据保留，禁止复用/晋升。随后 trial10 尝试较宽的 AI silhouette，但本人目视其 fit 入原源框后仍过小且左右侧凸不自然，内部判失败，用户未审阅。trial11 全身概念曾把双手放大并朝内 thumb-nub，用户反馈“手确实偏大了”；trial12/13 减小后用户仍指出“偏大”。trial14 将双手控制在 trial08 可见手型的整体 footprint 内或略小，但用户看后仍反馈“偏大”，因此 trial14 尺寸被否决，仅留作对照。之后制作 trial15：相对 trial14 再明显缩小双手，同时保留圆钝 mitten 与小型朝内 thumb nub。08/11/13/14/15 同位比较板已生成；用户现明确认可 trial15 尺寸“完全合适”，据此解除“全身尺寸方向未确认前不拆件”的前置阻塞；但这只批准尺寸方向，不自动批准 trial15 AI 像素、source-aligned 原画、左右拆层或生产接入。现已进入隔离源件制作流程；trial16 AI 源袖 fit 板已由本人打开，发现候选左右画风/轮廓不一致，尚不合艺术门，继续修整并目视。无论用户选定哪个全身概念，它都不是 source art、拆件或生产批准；后续仍需独立 source-cuff/hidden-wrist 检查。trial09/10 仍是失败证据，不复用。以上均不能替代此 brief 要求的 source-aligned 原画、左右透明层、hidden-wrist 补全或生产批准。记录与检查板见同目录 `README.md` 与 trial07/08/09/10/11/12/13/14/15 metrics。

**Trial25 generation result (2026-11-03):** Two independent left/right mitten concepts were generated with the Chibi source sheet, source cuff/hand crops, and trial15 size-direction crops as visual references. Native-resolution inspection found that both files are RGB PNGs with no alpha; their checkerboard-looking backgrounds are opaque pixels. Both also have overly long narrow wrist shafts ending in blunt cuts, and their heavy plum outlines/broad smooth shading differ from the finer source treatment. Inward nub direction and distinct left/right contours are present, but the trial fails as hand artwork. Originals, file facts, and failure notes are retained under `trial25_mitten_art_wip/`; no cleanup or cuff fitting was attempted. This negative WIP does not change the approval boundary or satisfy the source-art handoff.

## 先锁角色真值

- 主视觉源：`characters/xiaoxun/design/design_sheet_chibi.png`，登记 body-fit 框 `[628,101,1416,1891] → 567×1292`；角色脸、发型、身体比例、服装、袖口条纹与配色均保持不变。
- 静止小手像素基线：`characters/xiaoxun/forms/chibi/sprites/body_full.png`（567×1292；SHA-256 `a1d19edbf84a6b8a902ab81e84a464a478b79c3e0a0c81f040321b33c115b1ff`）。原画已经有左右 small；其 visible pixels 可对照，但 cuff 下方隐藏腕部并不存在于该纹理。
- 注册腕口 ROI：左 `[43,846,132,938]`，右 `[435,846,524,938]`（均为 body_full 中 exclusive XYXY）。small 手测量框（含 1px 原轮廓 margin）：左 ROI 内 `[19,32,64,80]` / 45×48，右 `[27,34,72,80]` / 45×46；对应 body_full 区域左 `[60,876,109,928]`、右 `[460,878,509,928]`。
- 当前 source-only small cutouts `chibi_small_left_source_pixels_wip.png` / `chibi_small_right_source_pixels_wip.png` 仅用作像素级可见手形基准；源 RGBA round-trip 已验证。隔离 C `zrig` 在 −30°…+30° / 5°步长的目视 follow-up 显示：small 在 ±5°仍看似贴合，约 ±10°出现细微分离，±15°见明显棋盘格 sliver（仅视觉 bracket，不是安全角）。手稿需补足被袖口遮住、旋腕后会露出的 wrist 内容，但不能把该缺失误称为已有源像素。

## 要交付的原画内容

1. **先给完整 Chibi 全身图**：同一角色、相同衣着/袖口/比例，在自然放松姿势下呈现左右 mitten 方案；与原 small 全身并排检查。此整身稿必须先由用户/授权美术审阅确认，确认后才拆手件。
2. **左右分别设计**：提供 left/right 独立手形，不默认镜像代替。轮廓方向可以是圆钝、弱分指/连袖感；具体形态以获准设计为准，不能从这份 brief 或 AI trial 06/07/08 自动推成定稿。
3. **独立透明手件和隐藏腕部**：每侧 `hand_l_mitten` / `hand_r_mitten` 各自作为可追溯图层；腕根向 sleeve opening 内有足够绘制/线色延伸，腕角扫动时无断腕、透明缝或空底。隐在袖内的部分要与袖/前后 cuff 分层逻辑配合。
4. **袖口不随 AI 概念重画**：原 Chibi teal cuff、乳白条纹、外轮廓与接缝是来源真值。新手应被自然遮入原 cuff，而不是改袖口尺寸、条纹宽度或袖口角度去迁就候选手。左右 sleeve/cuff 如需艺术修正，必须作为独立、明确批准的原画差分提交，不从本 brief 默许更改。
5. **保持 Chibi 原画质感**：照源图核对线条粗细/边缘像素、肤色层次、阴影密度与手在全身的实际尺寸；颜色数值从源 small 手像素抽样只作对照，最终按原画目视匹配，不把分析样本当硬编码调色板。

## 已知负例，不要复刻

- AI full-body trial 06 改画脸/发、比例、衣裙鞋和 cuff；仅可作“圆钝形状方向”参考。其 45×43 hand-only 像素 fit 虽逐侧保留 source cuff RGBA（左 2,440、右 2,498 个 cuff pixels），4× 检查仍有 wrist opening 外缘空隙/不均、暖浅 seam 与线稿密度差；不是接缝验收，也不是获批手件。
- AI full-body trial 07 option 2 是用户选定的概念方向，但检查发现手偏大且袖口被重画成单条浅纹；按源 cuff 拟合手件又出现明显腕口间隔。trial 08 将手缩小、恢复双条纹，用户随后确认其视觉方向“非常好，符合了”；但它仍是 AI redraw，袖口非源像素，放大可见细微分指线。当前可以作为已确认的设计方向进行隔离试装，不能直接作为生产源图。详细证据见 hand-style study README 和 trial-07/08 metrics、review boards。
- trial 04/05 同样是未批准 AI 候选；不得取它们改变过的 cuff 或身体细节。
- 用户红圈截图只可作抽象形状提示；禁止截图裁片、描摹其轮廓/像素或将其当作 production texture。
- 禁止程序化画手；禁止用 Teen/generic raw hands 代替 Chibi。

## 审核交付包（未齐不得开 production integration）

- 同姿势完整全身小巧手/mitten 对照图；清洁、无 UI/红圈遮挡；可审阅左右袖口与全身比例。
- 获批后 source-layer 文件：原图版本/哈希、左右 hand layer、hidden-wrist fill、cuff 前后覆盖层关系与 source-to-part 坐标/锚点说明。
- 1× 与 @2× 手件、单手/双手 wrist close-ups、全身合成对照；先由用户/授权美术确认，再进入隔离 `make_hand_parts.py` / `make_rig.py`。
- 工程验收仍独立：small ↔ mitten 双向恰一组可见；`hand_style` 与 wrist angle/gesture pose 分轴；测试袖口与衣物遮挡、静止/旋腕极值/wave/heart/surprised，再到真实 C 引擎视觉矩阵。通过前绝不接生产。

## 对应记录

- 来源裁切与方法：`source_crop_manifest.json`、`chibi_small_hand_source_extraction_metrics.json`。
- trial 06 像素 fit 的失败判读：`mitten_trial_06_source_cuff_metrics.json`、`chibi_mitten_trial_06_source_cuff_candidate_board_wip.png`。
- 项目铁律/任务：`docs/memory/WORKFLOW.md` 铁律 0–15、`docs/memory/TASKS.md` T70.2–T70.4、`docs/qa/chibi_candidate_2026-11-01/hand_style_variants_2026-11-01.json`。
