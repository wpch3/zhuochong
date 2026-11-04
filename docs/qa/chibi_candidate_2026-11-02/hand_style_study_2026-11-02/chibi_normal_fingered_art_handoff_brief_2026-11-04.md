# Chibi normal-fingered hand — source-art handoff brief (2026-11-04)

**Status:** specification/diagnostic only; no artwork is approved by this brief. This complements (does not replace) `chibi_mitten_original_art_handoff_brief_2026-11-02.md`. The normal-fingered style and the independent `mitten` style must both remain in the workflow.

## Goal

Create the Chibi character’s relaxed, small normal hand as a distinct alternative to the rounded mitten. At the registered small-hand box (viewer-left 45×48 px; viewer-right 45×46 px), it must unmistakably read as a fingered hand without becoming an adult hand or a splayed gesture. Because the source pose shows the outer/back of a side-hanging hand, require **at least three clearly distinct rounded fingertip lobes** and anatomically plausible thumb/edge cues; the fourth finger may overlap naturally in this view. Do not demand four fully separated fingers if that contradicts the source angle.

## Reference and pose

- Character/style truth: `characters/xiaoxun/design/design_sheet_chibi.png` and the source-registered Chibi `body_full`/small-hand crop.
- Resting pose truth: hands hang beside the thighs in the Chibi standing design. Keep the wrist axis close to vertical, fingers pointing down and gently relaxed, palm turned toward the body and the outer/back side toward the viewer. Do not use the raised, palm-forward, wave, or fan-spread pose from failed probes.
- `characters/xiaoxun/design/chibi/desktop_pet_base_2026-10-31.png` is explicitly a desktop-pet design reference, not the source for the Live2D Chibi hand. Do not copy Teen/generic hands or user screenshot pixels.

## Visual acceptance checklist

1. **Digit read at target size:** at least three rounded fingertip lobes remain distinctly readable, with real silhouette notches rather than faint crease marks; the fourth finger may partially overlap naturally from this outer/back view. A small thumb/side-digit cue should be plausible for the pose, not a mitten seam. Evaluate at 45×48/45×46 and on the full-body registration, not only enlarged concept resolution. A vague paw or two-pronged mitten still fails.
2. **Chibi proportions:** short, soft, compact palm/fingers; wrist insertion is not a long adult forearm. Preserve the trial15-approved small-hand size direction; do not enlarge the hand to make the gaps readable.
3. **Source style:** fine, light contour and restrained warm shading matching the source Chibi. No heavy contour, pixel-art edge treatment, photoreal anatomy, nails/wrinkles/jewelry, or soft blurry blob shading.
4. **Rest pose:** hand hangs naturally at the side, not open toward the camera, widely splayed, or posed as a gesture.
5. **Left/right authenticity:** provide separate viewer-left and viewer-right source art with their own anatomy/orientation; do not mirror one side to invent the other.
6. **Layer completeness:** include authorized under-cuff wrist continuation and enough overlap to test the existing cuff-front/back plan. Preserve hand-style independence from wrist rotation and gesture channels.

## Re-review of existing WIPs after correcting the view criterion (2026-11-04)

The revised rule does **not** require four fully separated fingers. I re-opened the target-size boards and exact source-ROI boards under the side/back hanging-view criterion:

- Trials 33–36 show roughly three rounded digit tips at diagnostic scale, so they are **not** rejected merely for a naturally obscured fourth finger. They still fail as Chibi candidates: 33/34 are open/front-facing, adult-long isolated hands with mismatched rendering and no cuff registration; 35/36 redraw the cuff, enlarge the wrist/hand, and have heavy/inconsistent linework with no source-registered layer.
- Trials 37–40 still fail the target-scale registration gate: exact source hand ROIs show only cuff/upper palm or crease-like strokes, not three separated rounded fingertip lobes; 37–39 are shifted/oversized and 40 also redraws unrelated face/clothing detail.

Thus all trial33–40 remain rejected for specific view/style/registration/source reasons—not for forcing a four-finger silhouette. Per-trial record is in each `metrics.json` under `post_rubric_review`.

## Required review package before rig/model work

- Source/provenance note and approvals; separate left/right artwork; genuine transparency verified from file data; exact dimensions/anchors; full-body source-aligned view; target-size and 4× detail comparisons; hashes.
- After the art gate, verify cuff/hidden-wrist coverage and normal↔mitten exclusivity in an isolated rig, keeping wrist movement and gesture independent. For true Cubism work, include these parts in the overlap-complete approved PSD and test them through Cubism Editor/Viewer; the C `zrig` is not a Cubism model.
- No production use until visual review, runtime tests, user/authorized-art approval, and source/QA gates all pass.

## Negative evidence / stop signal

Trials 27–32 are retained under `trial27_normal_fingered_hand_wip/` through `trial32_normal_fingered_hand_wip/`. At least one criterion failed in each: adult/elongated proportions, target-scale paw/mitten reading, palm-forward/splayed pose, collapsed clefts, pixel-art styling, or mismatch with source linework. Comparison board: `trial27_32_normal_hand_target_scale_comparison_wip.png`. Do not fit, crop to transparency, mirror, recolor into source art, or insert any of these images into a rig. Six failed prompt probes show that repeating similar unconstrained generation is not a reliable art pipeline; use an approved original drawing or obtain new art direction before the next art attempt.
