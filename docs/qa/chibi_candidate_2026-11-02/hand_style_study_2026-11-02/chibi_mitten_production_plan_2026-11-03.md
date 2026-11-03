

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
