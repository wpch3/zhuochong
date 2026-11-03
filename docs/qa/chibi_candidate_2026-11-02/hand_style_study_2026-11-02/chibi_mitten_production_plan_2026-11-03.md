# Chibi `small` / `mitten` 完整制作计划与门禁记录

更新：2026-11-03 ｜ 活动分支：`arena/aaf1408c-zhuochong` ｜ 状态：**制作已启动；隔离原画候选阶段；未进入生产**

## 用户本轮指令与批准范围

- 用户确认 trial15 的手部尺寸“完全合适”，并要求开始完整工作流；批准范围是 **trial15 的尺寸方向**。
- 这不是对 trial15 AI 像素、左右独立手稿、袖下隐藏腕部、source-layer、rig、全身 Chibi、C 引擎或正式生产的自动批准。下面按项目铁律继续隔离制作，并在实际来源件进入生产前保留目视门禁。
- 项目常驻红线：不程序化绘手；不借用 Teen/generic 手；不裁切/描摹用户截图作为贴图；Chibi 真值优先；不改原 cuff/source sprites/rig/generator，直至获准的原画与验收包齐全；静态 QA 不代替眼睛与真实 C 引擎。

## 资料与项目审查（本轮开工前已完成）

### 项目内真值

1. `characters/xiaoxun/design/design_sheet_chibi.png` 与 `characters/xiaoxun/forms/chibi/sprites/body_full.png` 是角色/袖口/肤色的来源真值。
2. `design/anchors.json` 与 `source_crop_manifest.json` 登记了 567×1292 body canvas、左右 wrist anchors 与 cuff/hand ROI；左右现有可见 small hand 测量框约 45×48、45×46 px；源图没有 cuff 下的隐藏腕续画。
3. `docs/qa/chibi_candidate_2026-11-01/hand_style_variants_2026-11-01.json` 已定义两种独立 style 的契约：`hand_style` 只切换 `small` / `mitten`；腕角与 gesture 保持独立；每档严格成对互斥。
4. 当前 Chibi `rig.json` 仍只有 `seg_arm_l/r`，没有独立 small/mitten 手件或 hand-style pose；`make_hand_parts.py` 有意跳过无 Chibi 来源的 pose 图；`make_rig.py` 已有可复用的通用互斥 `poses` parser/renderer 与动作/pose 分轴能力。不能假设整条手臂接入/腕旋和新手件已经完成。

### 项目规范 / 参考

- `docs/memory/WORKFLOW.md` 铁律 0–15：用户要求优先、必须自检和目视、真值与学习优先、整身先行再拆骨、零空洞、衣物前后夹层、隔离测试不等于产品、实际阶段归档。
- `docs/SHEET_PIPELINE.md`：同一角色底图、先完整差分全身再拆件、检查套准；不是从不匹配碎片拼装。
- `docs/ART_PARTS.md` 与 `docs/PART_LAYERING.md`：独立完整图层、运动后显露区域补画、静止重合与边缘多重验收。
- `docs/REFERENCE_NOTES.md` 第七十一批已记录 Live2D 官方 Production Flow、PSD 分层注意和 Pose Settings。要点：补足运动会露出的区域；part source/线稿/填色组织清楚；互斥差分通过独立 pose 组实现。官方语义仅作方法，不代表本项目自动兼容 Cubism 文件。
- 当前阶段不再泛搜外部 hand 素材：审计已确认未发现可直接替代小寻 Chibi 真值的已授权手稿；`design/hands/*raw.png` 画风比例不符，惊讶 SVG 指向 Teen，均排除。

## 制作流水线（阶段、产物与验收条件）

### Stage A — 锁设计与角色真值（本轮完成）

- 目标：保留 trial15 已获认可的手尺寸；固定角色身体、袖口、姿势和源位置；锁左右方向与缩放基准。
- 可复核产物：trial15 full-body 与同位板、source crop manifest、hand-style contract。
- 状态：✅ 尺寸方向获用户认可；其他艺术/工程门禁仍开放。

### Stage B — 左右独立原画与 sleeve/cuff 适配（进行中，隔离）

- 目标：分别提供 viewer-left/right 的原创新 mitten artwork；保留同尺寸、同视感、朝内 thumb nub；手根有足够隐藏续画；线稿/肤色/阴影接近 Chibi source。
- 只把 AI 作为原创新稿候选，不把任何 WIP 直接当 source pixel。禁止脚本生成轮廓或借用别形态手件；像素分析脚本只可测量、切取已有 AI pixels、与源 cuff 遮叠。
- cuff 适配：逐侧从 Chibi 原图测 cuff 材料连通区，cuff 仅保留 source RGBA；新手置于 cuff 后方，并核对 source hand 外围没有原小手指/旧轮廓露出。
- 验收包：1× / @2× 左右手透明件、source hand/cuff vs candidate 的 4× 与 8×板、全身对照、像素来源/哈希/目标框与静态 composite 差异。
- Stage B 迭代：trial16 左右生成物 wrist 长短与掌宽不一致，内部拒绝；trial21–23 继续尝试，仍存在左右比例差/多余 wrist 形状或过于镜像的问题。trial24 依据 Chibi `body_full` palette、trial15 批准尺寸方向及注册 hand anchors 做统一比例 source fit；本人检查 1×全身、4× hand/cuff、7× seam 和 2×左右手件后，认为其可作为目前较合适的**用户审阅 WIP**：左右都读作 compact mitten、朝内 nub 可见、尺寸方向一致、source cuff 区 byte-exact，静态未见明显开缝。仍有左掌略宽、右 nub 略显、AI 线影更软的风格差；故不作为最终 source art、不进 rig，等待用户审阅与 source-art 批准。hidden-wrist / 动态未测。

### Stage C — 用户/授权美术确认实际手稿（未完成）

- 用户已批准尺寸方向；尚未看到并批准 source-fitted 左右独立艺术件。交付 Stage B 合格板后提交本人检查与用户审阅。
- 通过前不将 AI WIP 称为原画，不拆分为正式 source layers，不覆盖角色原图或生产 sprite。

### Stage D — Source-aligned parts 与 arm/cuff underlay（待 Stage C）

- 使用批准版绘制/整理：`hand_l/r_small`（保留原 Chibi small 可见像素）与 `hand_l/r_mitten` 独立 PNG；补全被 cuff 遮住、手腕运动可能露出的区域。
- 由 `make_arm_parts.py` 隔离重建上臂/前臂/腕部，保留 cuff 原图；腕根覆盖满足铁律 9/10。依规则校验隐藏 upper/fore 仍连续、没有 alpha 洞、腕袖口层序正确。
- 记录源坐标到 rig 坐标的转换、各自 pivot/anchor、静态无损拼回误差、cuff RGBA 区域 identity 和 1×/@2×产物 hash。

### Stage E — hand_style generator / rig / runtime（待 Stage D）

- 不把 hand style 混入 gesture 或 wrist angle。先复用现有 pose-group visibility 机制：`hand_style` 默认 small，`mitten` / `small` 成对显示左右两件；只有在生产 art 通过后才扩展 `make_hand_parts.py` / `make_rig.py` 输入格式。
- 手的运动仍继承各自 wrist group/anchor；gesture pose 若缺少 Chibi 原画仍禁用，不从 Teen 借件。不可通过只切整条手臂来假装手型切换。
- 先加静态结构测试：parts 文件存在、独立层、恰好一套左右可见、双向切换不残留双手/空洞；小手 style 与既有默认姿态兼容。

### Stage F — 组合验收与生产晋升（待 Stage E）

- 先 source-pixel/composite：默认 small ↔ mitten 双向、cuff seam 目视、原源皮肤/服装没有变形或删失。
- 再 arm/wrist：静止、左右腕旋极值、上臂/肘角度扫；检查腕底隐藏续画、袖口条纹、手不从袖口弹出。
- 再 gesture × outfit × hair/hood（仅已存在且真实可用的 Chibi 状态）：完整身与 wrist close-up 同步截图；检查 small/mitten 切换轴不重置/覆盖 action、装饰或其他状态。
- 真实 C 引擎与自动 QA 是两道独立门；记录所有失败，不跨素材快照相减。全部通过且用户批准实际源件后，才从隔离候选复制/生成到 `characters/xiaoxun/forms/chibi/sprites/` 与 production rig；生产改动单独提交并回滚可追溯。

## 本轮实际产物与状态

- 视觉方向与对照：`chibi_mitten_original_fullbody_concept_trial_15_wip.png`、`chibi_mitten_trial_15_fullbody_size_comparison_board_wip.png`；trial15 size 用户明确确认。
- 隔离源件试装：trial16 的失败证据，以及当前 trial24 `build_mitten_trial24_sourcefit_wip.py`、`trial24_sourcefit_candidate_parts/`、`body_full_trial24_mitten_sourcefit_preview_wip.png`、`chibi_mitten_trial24_sourcefit_review_board_wip.png`、`mitten_trial24_sourcefit_metrics.json`。trial21–23 的单手 AI WIP 留作形态迭代过程记录。
- 本人重新打开 trial24 review board、全身 preview 和两侧 2×透明手件后的判断：尺寸方向遵从 trial15；左右都是紧凑圆掌 mitten、朝内 nub 可辨；选中的源 cuff 区 byte-exact，静态未见明显开缝。仍有左掌略宽、右侧 nub 略显、轮廓/阴影比 Chibi 源更软的问题；仅推进到用户审阅 WIP，不是完成 source art。动态 hidden-wrist 与实际引擎未测试。
- `characters/xiaoxun/forms/chibi/sprites/`、Chibi `rig.json` 与生成器尚未修改。当前处于 **T70.2 批准尺寸、继续原创手稿阶段**；T70.3 / T70.4 未完成。

## 2026-11-03 status correction and reuse decision after user feedback

- **Plan provenance correction:** `git show 817bbf1:<this file>` confirms the complete Stage A–F plan existed at commit `817bbf1`. The current file at `4f2e742` had been rewritten to an 18-line Stage E probe, dropping the plan body; the previously reported Stage A–F content was not present in the active file. This section restores the verified 73-line plan from `817bbf1` and preserves the later Stage E feasibility, moderate-sweep, and trial25 addenda. No claim is made that the plan body remained present during the intervening commits.
- **User feedback:** “（手套）手基本过关，你自行判断是否沿用。” I interpret this as allowing reuse of the basic mitten silhouette, not as approval of every bitmap or the production asset.
- **Agent decision:** carry forward **trial24** as the provisional isolated mitten-shape base. It is the registered source-fit pair at the user-approved trial15 size direction, has actual RGBA transparent parts (46×58 left / 45×58 right), and its source cuff pixels were recorded byte-exact. The user has now said the mitten hand is basically acceptable. Do **not** reuse trial25 RGB checkerboard images as artwork: those are a failed attempt with no alpha and overlong wrist shafts; retain them only as negative reference evidence.
- **Approval boundary:** the feedback supports continuing with trial24's basic hand form in isolated QA. It does not establish source-art fidelity, hidden-wrist completeness, motion safety, explicit final approval of pixel files, or production authorization. Stage B can continue from trial24; Stage C/D art and cuff/underlay gates remain open until actual hand/wrist coverage is independently checked and the user/authorized artist approves the complete source-aligned package.
- **Hidden-wrist edge spot-check:** on re-opening the 2× RGBA parts, alpha exists on row 0 across x=21–70/92 px (viewer-left) and x=25–69/90 px (viewer-right), so each crop reaches a broad near-horizontal edge at its top. The current source cuff hides it in the registered neutral view and existing ±30° samples; that is not proof of complete under-cuff art or motion safety. This turn only inspected existing files, did not rerender C or change hand pixels. The edge remains a documented art/coverage gap.

---

## 2026-11-03 feasibility-only Stage E probe: isolated candidate rendered through real C zrig

This is a bounded engineering probe, **not approval to skip Stages C–D** and not a production implementation. The test candidate remains under `chibi_arm_rig_candidate_2026-11-03_wip/`; `build_chibi_arm_rig_candidate_wip.py` runs the current arm/rig generators against a temporary copy of the production inputs, then overlays trial24 AI parts as a separate unapproved QA pose. No production Chibi asset, rig, generator, or engine source was edited.

To prevent generated pixels being misrepresented as source art, the candidate `small` pose replaces the generator's median-colour wrist stub with the registered source-pixel small-hand cutouts. Their hashes match the source extraction outputs, but the original Chibi sheet contains no under-cuff continuation; the candidate intentionally has no hidden wrist. The mitten pose is trial24 WIP only. The distinction is explicit in candidate metrics and notes.

The real C `zrig` sources were compiled and used for an accessory-excluded 86-frame matrix: 2 idle controls, 58 wrist samples (−70°…+70° in 5° steps), 18 shoulder/elbow samples, and 8 action samples. Structural/runtime assertions passed for dimensions, alpha, one-hot style, unclamped wrist inputs, active requested action, and hidden separated ears/tails. This is a **feasibility result**, not a complete gesture × outfit/hair matrix or a safety result. The ±70° endpoints are stress samples only.

**本人目视的关键结论：**

- `wave_both` visibly moves the arms. `heart_hands` does not produce a distinct heart-hand pose in sampled frames; the necessary Chibi gesture hand art/channels are missing.
- The exact-source `small` hand reveals checkerboard/alpha gaps at extreme wrist stress angles because hidden-wrist art is absent. The AI mitten's cuff transition is also unresolved. Do not patch this with programmatic hand art or infer a safe wrist range.
- Neutral C render is broadly registered to source but shows visible face/eye, hair-contour, outfit/arm, leg and shoe discrepancies. Source overlays and uncalibrated diagnostics are retained as WIP, not pixel-fidelity gates.
- Keep all production gates open: compliant approved left/right mitten source art; hidden-wrist completion; art/source review; gesture-specific hand art; full source-to-part/cuff verification; outfit/hair/occlusion matrix; user and production approval.

The exact boards, logs, hashes, metrics, scripts, and limitations are listed in `chibi_arm_rig_candidate_2026-11-03_wip/REVIEW_NOTES_wip.md` and the hand-study README. This probe changes the observed status from “no isolated C-engine exercise” to “limited feasibility matrix completed”; it does **not** close T70.2, T70.3, or T70.4.

### 2026-11-03 follow-up: moderate wrist boundary bracket (diagnostic, not safety)

To refine the earlier ±70° stress observation without proposing a safe range, rendered 26 additional C frames for both styles from −30° to +30° in 5° steps. The registered wrist ROIs are computed from `source_crop_manifest.json` and the body-to-canvas registration, then enlarged 4× nearest-neighbour in `candidate_c_engine_moderate_wrist_small_review_board_wip.png` and `candidate_c_engine_moderate_wrist_mitten_review_board_wip.png`.

本人目视估计：exact-source `small` 看起来在 0/±5°仍贴合；±10°附近开始出现细微分离，±15°采样可见清楚的棋盘格 sliver。该范围只是 5°采样下的视觉起点 bracket，不是误差容限、安全角或验收。trial24 AI mitten 在所示 ±30°样本中未见同等明显的大开缝，但仍有细小边缘问题，且 AI 手稿/hidden-wrist 未批准。对应原始运行 log/hash/ROI 位于 candidate 的 `candidate_c_engine_moderate_wrist_review_metrics_wip.json`；所有结果只用于定位缺件，不授权绘制/改写手稿或接生产。

### 2026-11-03 trial25 isolated hand-art probe (rejected)

Following the last source-aligned art gap, I generated a distinct left/right pair using the registered Chibi sheet, source cuff/hand crops, and trial15 size-direction reference as visual references. This was an isolated concept probe only: no reference pixels were cut into the new images, and trial15 still authorizes size direction only.

I opened both outputs and verified their file data. They are RGB PNGs (left 1024×1024, right 912×1150) with no alpha channel; the apparent checkerboard patterns are part of the opaque RGB images. Both have overly long narrow wrist shafts ending in blunt top cuts, and the heavy uniform plum outlines/broad smooth shading do not match the finer Chibi source treatment. Inward thumb orientation and non-identical left/right silhouettes are present, but the candidate fails transparency, proportion, and source-style checks. Preserve only as negative WIP evidence in `trial25_mitten_art_wip/`; do not remove backgrounds, fit to cuffs, or test in rig. The source-aligned approved art and genuine hidden-wrist continuation remain unmade. No production gates are closed.
