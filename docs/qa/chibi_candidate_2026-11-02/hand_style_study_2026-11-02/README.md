

## 2026-11-03 isolated arm-rig candidate + real C-engine QA (WIP, not accepted)

This phase creates a test-only arm/hand-style candidate after the trial15 **size direction** approval. It does not promote trial24 AI pixels or approve source art, hidden wrists, motion safety, production assets, or the complete Chibi. The candidate is built by `build_chibi_arm_rig_candidate_wip.py` in a dated isolated output directory; the production tree is copied to a temporary folder for the existing generators. No production `sprites/`, `rig.json`, generator, or `src/core` file was changed.

The `small` pose deliberately uses the exact registered visible source-pixel cutouts in `chibi_small_left_source_pixels_wip.png` / `chibi_small_right_source_pixels_wip.png`, not the generator's median-colour wrist stub. File hashes match the original extracted cutouts, and no hidden-wrist continuation is invented. The `mitten` pose uses separate trial24 AI WIP pixels only as an unapproved comparison. This split makes the missing under-cuff source art visible in motion rather than disguising it with generated fill.

The actual C `zrig` sources were compiled into an isolated harness and rendered through 86 frames: 2 default-idle controls, 58 wrist samples (−70°…+70° every 5°), 18 shoulder/elbow samples, and 8 action samples. Every frame had the expected 848×1360 dimensions and non-empty alpha; style poses were one-hot, requested wrist values unclamped, and requested actions active. Six separate ear/tail accessory parts were hidden for these body-only tests. The ±70° samples are **stress coverage only**, not an approved safe range.

My visual review of the generated motion/detail boards and refreshed neutral/source boards found:

- Coarse shoulder/elbow sweeps visibly move the arms. `wave_both` moves the arms; `heart_hands` does **not** show a distinct heart-hand pose in the sampled frames because required gesture hand art/channels are missing.
- At ±70° the source-only `small` cutouts show visible checkerboard/alpha gaps at the cuff-side wrist boundary. This is expected evidence of missing genuine hidden-wrist art, not something to fill by programmatic hand drawing. Mitten cuff behavior also remains unresolved; no safe angular range is inferred.
- Full-body neutral images are broadly registered, but visible differences remain around face/eye detail, hair contour, garment/arm boundaries, legs and shoes. The face detail board makes eye/eyelash residuals visible. Whole-body pixel counts are uncalibrated diagnostics—not pass scores.
- The source crop board shows the registered visible `small` pixels alongside source and the AI mitten. That crop does not establish hidden-wrist completeness, art approval, or motion safety.
- Follow-up via `build_candidate_c_engine_moderate_wrist_review_wip.py`: rendered 26 more C frames for `−30°…+30°` in 5° steps and opened both 4× close boards. My visual estimate is that source-only `small` starts showing subtle cuff separation around ±10° and a clear checkerboard sliver by ±15°; the 5° sampling only brackets this onset and is not a safe-range gate. Trial24 mitten shows no comparably large open gap in these selected samples, but seam artifacts and unapproved art/hidden-wrist remain. Detailed logs/ROIs are in `candidate_c_engine_moderate_wrist_review_metrics_wip.json`; crop ROIs are calculated from the registered source manifest.

Detailed result and gates: `chibi_arm_rig_candidate_2026-11-03_wip/REVIEW_NOTES_wip.md`. Main boards, per-frame run logs/hashes, neutral metrics and candidate source provenance live in that same directory and its `SHA256SUMS.txt`. Runners and the temporary C harness source are in this study directory. This is a concrete **QA WIP** result only; T70.2 remains incomplete, T70.3 is only feasibility-tested in isolation, and T70.4 remains open. Do not copy any candidate asset into production.

## 2026-11-03 trial25 independent hand-art generation (rejected WIP)

Generated separate viewer-left/right compact mitten concepts from the registered Chibi source and the trial15 size-direction reference. I opened both outputs and checked their actual PNG data. Both failed: they are RGB PNGs with no alpha channel (the checkerboard patterns are opaque pixels), their wrist shafts are long with blunt top cuts, and their heavy outlines/broad smooth shading visibly differ from the finer Chibi source. The thumb nubs point inward and the left/right contours are not exact mirrors, but those isolated positives do not make the art usable. No background removal, source-cuff fit, rig test, or production edit was attempted. Keep the generated originals only as rejection evidence under `trial25_mitten_art_wip/`; full findings and hashes are in `trial25_mitten_art_wip/trial25_review_notes_wip.md` and `trial25_mitten_art_wip/trial25_metrics_wip.json`; input prompt provenance and local hashes are in `trial25_mitten_art_wip/trial25_prompt_record_wip.md` and `trial25_mitten_art_wip/SHA256SUMS.txt`. The compliant source-aligned pair with genuine hidden-wrist art remains outstanding.

## 2026-11-03 user follow-up: reuse decision

User said the mitten hand is basically passing and left reuse to my judgement. I choose **trial24** as the provisional isolated base: on reopening its full-body/4×/7× review board, both hands read as compact rounded mittens at trial15 size, the small nubs face inward, and the original cuff is retained. The parts are real RGBA (46×58 left, 45×58 right; cuff identity records 2,440/2,498 px). These points justify continuing with the basic shape, not promoting AI pixels. Trial25 remains rejected as a raster source (RGB checkerboards, long cut wrist shafts); it is not used for fit or rig. Trial24 source art, hidden-wrist completeness, full-angle safety, and production approval remain open. Follow-up inspection of the 2× RGBA parts found broad alpha already on the top row (left x=21–70/92; right x=25–69/90): the current cuff hides the crop edge, but does not establish complete hidden-wrist art. A new isolated real-C visibility board compares normal, whole-forearm-hidden, and mitten-hidden rendering at −30°/0°/+30°; it supports only the current layer-order observation, not motion safety. A trial26 AI edit tried extending the wrist but again produced opaque RGB checkerboards, so it is retained as a failure and not fitted. Decision record: `trial24_user_feedback_and_reuse_decision_2026-11-03.md`; board/metrics: `trial24_wrist_layer_visibility_board_wip.png` / `trial24_wrist_layer_visibility_metrics_wip.json`; trial26 negative evidence: `trial26_hidden_wrist_art_wip/`.

## 2026-11-04 范围澄清

手型验收必须同时包含两条独立路径：正常、可辨识手指的 `small` 与手套式 `mitten`。当前 small 提取图仅证明源图可见像素被选取，未证明完整手指造型、hidden wrist 或生产拆件已完成；trial24 仍仅为 provisional mitten 基线。

另：用户已要求真正 Live2D Cubism 作者工程/模型。此 study 中的 C `zrig` 渲染和 rig feasibility 不是 Cubism Editor 工程、不是 `.moc3`，不构成 Cubism 兼容性。官方完整作者/导出/运行时边界和本仓库阻塞事实见 `docs/memory/CHIBI_CUBISM_TRUE_MODEL_AUDIT_2026-11-04.md`。本 study 仅为隔离手型研究。

## Trial 27–32 — normal-fingered small-hand probes (2026-11-04; all WIP, none approved)

为落实用户要求的正常有指手与 mitten 双风格并存，生成 viewer-left normal-hand 原创概念探针；只以 Chibi 设定图与 source crop 作视觉参考，没有复制参考像素。六张原图都是 opaque sRGB/no-alpha PNG；无透明提取、生产拆件或 rig 接入。

- `trial27_normal_fingered_hand_wip/`：五指可辨但过长/成人化，线稿/阴影不符 Chibi，拒绝。
- `trial28_normal_fingered_hand_wip/`：全尺寸较短圆，45×48 时指缝变软，读作 paw/mitten，不批准。
- `trial29_normal_fingered_hand_wip/`：小尺寸五指清楚，但变成掌心朝前、手指大幅张开的手势，姿势/比例不符。
- `trial30_normal_fingered_hand_wip/`：侧垂方向较合适，但 45×48 时指间隔变成浅 grooves，读作 mitten，且 wrist 过长。
- `trial31_normal_fingered_hand_wip/`：目标尺寸五指可辨，但输出有明显 pixel-art 边缘、手掌和 wrist 过长，不符 Chibi。
- `trial32_normal_fingered_hand_wip/`：目标尺寸仍能区分指尖，线条较平滑，但成人化细长比例/wrist 和线影仍不匹配 Chibi。

比较板 `trial27_32_normal_hand_target_scale_comparison_wip.png`（指标 `trial27_32_normal_hand_target_scale_comparison_metrics_wip.json`）对照六张 45×48 诊断图；这是已有 WIP 的 QA 拼板，非角色图/非 engine render。各诊断 probe 保留不透明背景，并放大 8×供目视（具体方法、评语、SHA 在子目录 README/metrics/local manifests）；不是真实 C 引擎或 Cubism 渲染，更不是生产部件。不得据此抠底、套袖口、镜像补右手或升生产。normal-fingered art 与左右独立手件仍未完成；trial24 仍单独保留为 provisional mitten 方向。

**迭代边界**：六轮生成未同时满足 Chibi 侧垂姿态、短圆比例、细线画风与 45×48 可辨四指；停止把相同 AI 手部 prompt 当作生产路径，后续应基于获批原画/美术审核或新的可靠来源重新起稿。正常手源稿交接规范见 `chibi_normal_fingered_art_handoff_brief_2026-11-04.md`。真正 Cubism 模型仍受 `docs/memory/CHIBI_CUBISM_TRUE_MODEL_AUDIT_2026-11-04.md` 的 PSD/Editor/SDK 门禁阻塞。
