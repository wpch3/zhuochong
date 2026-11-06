# Isolated Chibi arm/hand rig candidate — review notes (WIP)

**Decision: QA-only feasibility candidate; NOT approved for source art, production, or motion safety.** The build and all outputs are isolated under this dated directory. No production Chibi sprite/rig/generator or `src/core` file was changed.

## Inputs and source fidelity boundary

- Candidate builder: `../build_chibi_arm_rig_candidate_wip.py`. It copies the current production Chibi inputs and tools into a temporary directory, runs the existing arm/rig generators there, then writes only this QA candidate. Its output reports 59 parts, 13 groups, 5 pose groups.
- `small` hands in this rig are the exact registered visible source-pixel cutouts from `chibi_small_left_source_pixels_wip.png` and `chibi_small_right_source_pixels_wip.png`. Each replacement sprite hash matches the registered cutout hash; source extraction round-trip identity is true. They stop at the original cuff edge. No hidden wrist is fabricated or procedurally painted.
- `mitten` uses the separate trial24 AI WIP hand parts and exact source cuff as an isolated style comparison. Trial15 size direction is the only user-approved dimension. Trial24 pixels, the mitten silhouette, and this rig remain unapproved.
- The candidate generator's old `make_arm_parts` hand output includes a median-colour wrist stub; it was deliberately replaced in the QA `small` variant so the test does not misrepresent that generated fill as original Chibi art. Therefore the visible source-only hands have no hidden-wrist continuation.

## Real C-engine exercise completed

`../render_candidate_c_engine_preview_wip.c`, `../build_candidate_c_engine_motion_matrix_wip.py`, and `../build_candidate_c_engine_neutral_source_review_wip.py` compile/load the real project C `zrig` sources against this isolated rig. Six separated ear/tail accessory parts were hidden for the body-only matrix.

- **86 frames rendered**: 2 default-idle controls; 58 wrist samples (−70°…+70°, 5° step); 18 shoulder/elbow combinations (0/30/60° × 0/45/90°, both styles); 8 runtime action samples (`wave_both`, `heart_hands`). Every frame was 848×1360 with non-empty alpha; hand-style weights were one-hot; requested wrist values remained unclamped; action requests were active; action geometry channels were absent; accessories were hidden. Logs and per-frame hashes are in `candidate_c_engine_motion_matrix_results_wip.json`.
- **Wrist sweep is stress coverage, not a safe-range result.** The ±70° detail board shows visible checkerboard/alpha gaps at the cuff-side wrist boundary for the exact-source `small` hand; the source hand simply has no pixels under the cuff. The mitten trial also has unresolved cuff/hand edge behavior. These samples do not identify an acceptable angular range and do not establish motion safety.
- `wave_both` visibly moves the arms. `heart_hands` does **not** produce a distinct heart-hand pose in this Chibi candidate; the arms remain down in the sampled frames. This is evidence that gesture hand artwork/channels are still missing, not a successful gesture test.
- Joint matrix demonstrates visible arm response at coarse sample angles only; it is not a full joint-occlusion or outfit-coverage acceptance.

## Moderate wrist boundary follow-up — visual diagnostic only

The next targeted sweep rendered both styles at `−30°…+30°` in `5°` increments (26 C frames total), with both registered hand ROIs shown at 4× nearest-neighbour. ROIs are calculated from `source_crop_manifest.json` plus the registered body-to-canvas offset; they are not hand-entered rig anchors. Boards: `candidate_c_engine_moderate_wrist_small_review_board_wip.png` and `candidate_c_engine_moderate_wrist_mitten_review_board_wip.png`; full frame logs/hashes and derived ROIs: `candidate_c_engine_moderate_wrist_review_metrics_wip.json`.

**My visual estimate from the board:** the source-pixel `small` wrists look seated at 0° and ±5°; a subtle separation is becoming visible around the ±10° samples, and an obvious checkerboard sliver appears by the ±15° samples, with larger displacement/gap at higher samples. Because samples are 5° apart, this is only a visual onset bracket (roughly 10°–15°), not a measured tolerance or safe limit. The trial24 AI mitten has no comparably obvious large open gap in the displayed −30°…+30° samples, but small edge/seam artifacts remain and its art/hidden-wrist are not approved. This side-by-side observation cannot authorize either style or any angle range.

## Neutral source review and direct visual findings

`candidate_c_engine_neutral_core_source_comparison_review_board_wip.png`, `candidate_c_engine_neutral_core_face_source_detail_board_wip.png`, and `candidate_c_engine_neutral_wrist_source_comparison_review_board_wip.png` were opened and inspected after regeneration. Neutral comparison conditions: action idle, wrist/shoulder/elbow zero, ambient off, 0.02 s tick, scale 1.0; the six separated ear/tail parts are hidden.

- At full-body scale the candidate is broadly registered to the source, but the RGB threshold board still shows differences along the hair/head, eyes/face, clothing/arm contours, legs, and shoes. The close face board shows visible eye/eyelash/detail differences. These require source/art review; a low whole-body thumbnail is not proof of source fidelity.
- Registered wrist crops show the exact visible small source hand is recognizably preserved; the AI mitten is a distinct, smoother silhouette and remains unapproved. Static neutral crops cannot prove hidden-wrist completeness or safe motion.
- Neutral gray-composited diagnostic metrics are recorded in `candidate_c_engine_neutral_source_comparison_metrics_wip.json`. They are descriptive pixel counts/MAE, uncalibrated, and explicitly **not** pass scores or acceptance gates.

## Artifacts

- Motion boards: `candidate_c_engine_default_idle_controls_review_board_wip.png`, `candidate_c_engine_small_wrist_sweep_review_board_wip.png`, `candidate_c_engine_mitten_wrist_sweep_review_board_wip.png`, `candidate_c_engine_shoulder_elbow_matrix_review_board_wip.png`, `candidate_c_engine_action_pose_review_board_wip.png`, `candidate_c_engine_wrist_extremes_4x_detail_review_board_wip.png`, `candidate_c_engine_moderate_wrist_small_review_board_wip.png`, `candidate_c_engine_moderate_wrist_mitten_review_board_wip.png`.
- Neutral/source boards: `candidate_c_engine_neutral_core_source_comparison_review_board_wip.png`, `candidate_c_engine_neutral_core_face_source_detail_board_wip.png`, `candidate_c_engine_neutral_wrist_source_comparison_review_board_wip.png`.
- Data: `candidate_metrics.json`, `candidate_c_engine_motion_matrix_results_wip.json`, `candidate_c_engine_neutral_source_comparison_metrics_wip.json`, `candidate_c_engine_moderate_wrist_review_metrics_wip.json`, `rig_candidate_wip.json`, `arm_parts_candidate_wip.json`, plus per-file `SHA256SUMS.txt`.

## Project test status (not all-green)

- `make test`: **2,638 passed, 0 failed**. Compilation emitted one existing warning at `src/core/zimg.c:62` for unused `_zperf_probe`.
- `bash scripts/selfcheck_all.sh` was run with Pillow/NumPy and Zig 0.17.0 available. Windows cross-compile succeeded and the 342-case API/e2e smoke passed, but the overall script exited nonzero: static repository gate found stale generator fingerprints on the production Chibi/teen `rig.json`; asset QA reported 8 pre-existing findings (all-zero armpit masks ×2, bent-forearm palette ×2, long-hair @2× white edge ×1, 85-pixel static reconstruction delta ×1, twin-hair coverage/hide checks ×2). Do not change unrelated production assets or suppress these failures as part of this hand candidate.
- The selfcheck generated/replaced tracked Windows build outputs; those files were restored from Git. Final working-tree checks found no production sprite/rig/generator/engine modifications.

## Remaining gates

1. Obtain/approve compliant original left/right mitten artwork and genuine hidden-wrist continuation; no programmatic hand drawing and no Teen/screenshot pixels.
2. Resolve the visible cuff/hidden-wrist transition and inspect hand art at source scale and high magnification.
3. Supply/approve actual gesture hand art and independently test `hand_style × gesture × wrist angle × outfit/hair`; the current 8 action samples are only runtime checks.
4. Reconcile the neutral source discrepancies, complete full-body Chibi visual/occlusion review, then rerun the full project QA. User approval and separate production approval remain required.

## Subsequent user feedback and reuse decision (2026-11-03)

The user said the mitten hand is basically passing and delegated whether to reuse it. I choose the existing **trial24** RGBA source-fit pair as the provisional `mitten` shape for continued isolated QA; it is compact, follows the trial15 size direction, has inward nubs, and overlays the registered source cuff. The exact cuff identity checks remain 2,440/2,498 px. The user feedback supports the basic visual form, but not source-art fidelity, hidden-wrist completeness, all-angle motion safety, final approval of the exact AI pixels, or production integration. The previously tested moderate C sweep showed no comparably large open gap in the selected ±30° samples but did show minor edge/seam artifacts; that remains only a sampled visual observation. Trial25 opaque RGB checkerboard images are not used as the hand parts.

## Follow-up hidden-wrist boundary check (2026-11-03)

I reopened the @2× isolated trial24 parts after the reuse decision. Their occupied alpha begins at image row 0 and spans x=21–70 (viewer-left 92×116) and x=25–69 (viewer-right 90×116), yielding broad, nearly horizontal top boundaries at the crop edge. The registered static cuff hides these boundaries, and the existing moderate ±30° samples do not establish what happens outside the sampled poses. This is an explicit hidden-wrist/under-cuff art gap, not evidence of a complete wrist. No new C frames or hand pixels were produced in this check.

## C-engine layer-visibility follow-up (2026-11-03)

A separate runner rendered 9 additional trial24 `mitten` samples at −30°/0°/+30° under three layer modes: normal, whole `arm_l_fore`/`arm_r_fore` hidden, and both trial24 mitten parts hidden. The board/metrics live one directory up as `trial24_wrist_layer_visibility_board_wip.png` and `trial24_wrist_layer_visibility_metrics_wip.json`.

本人目视：the normal columns retain a visually joined hand/cuff in these three samples, with small edge/shading differences. Hiding the mitten leaves the original forearm/cuff layer; hiding the forearm exposes the hand artwork boundary. This confirms only visibility/layer ordering in the isolated candidate. There is no independent `cuff_front` toggle here—hiding `arm_*_fore` removes the complete sleeve. These three poses do not establish full hidden-wrist art or safe angles.

## Trial26 wrist-extension edit (rejected)

Two image edits of the trial24 @2× parts were requested to add a modest wrist continuation with true transparency. Both results instead contain opaque RGB checkerboards. The viewer-left wrist is too broad/elongated; the viewer-right shaft is too tall/narrow with a hard join. The originals and failure facts are archived under `../trial26_hidden_wrist_art_wip/`. They were not matte-removed, fit, or inserted into C.

Until these gates close, keep every candidate file isolated and describe the work only as a rendered QA WIP. No production integration is authorized by these results.
