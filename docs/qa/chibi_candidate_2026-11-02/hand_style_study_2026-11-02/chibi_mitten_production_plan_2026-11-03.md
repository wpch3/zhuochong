

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
