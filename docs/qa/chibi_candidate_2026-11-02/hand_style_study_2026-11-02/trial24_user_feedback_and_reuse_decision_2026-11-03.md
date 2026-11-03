# Trial24 mitten user feedback and reuse decision (WIP)

## User feedback received

User: “继续任务，（手套）手基本过关，你自行判断是否沿用。依旧牢记铁律和基础事项”

## Agent decision

**Reuse trial24 as the provisional mitten-shape base for isolated QA. Do not reuse trial25 RGB hand images as part assets.** This is a decision to continue from trial24's basic form, not to promote its AI pixels or close production gates.

## Why trial24 is the better base

- Its registered source-fit review board (`chibi_mitten_trial24_sourcefit_review_board_wip.png`) shows both hands as compact rounded mitten palms, with small inward-facing nubs, at the trial15-approved size direction. I reopened the board during this continuation: full-body placement reads small; the close crops show both wrists entering the original striped cuffs; the 7× joins retain the source cuff but still show small edge/shading differences.
- Actual isolated parts are RGBA (`identify`): viewer-left is 46×58 px, viewer-right 45×58 px; 2× derivatives are 92×116 and 90×116. Trial24 metrics record source cuff pixel equality at 2,440 / 2,498 pixels.
- The actual C-engine WIP already exercised trial24 at the displayed wrist samples; its moderate sweep showed no comparably large open gap in the selected ±30° samples, while small edge artifacts remain. This is not a safety limit or a motion approval.
- Trial25 images are RGB without alpha (1024×1024 and 912×1150); their checkerboard patterns are opaque pixels, and the wrist shafts are long with blunt top cuts. Keep those images as negative references only.

## Approval and production boundary

The user's wording supports the basic mitten hand form. It does **not** approve exact AI pixel art, hidden-wrist completeness, source-fidelity, all wrist angles, hand gesture art, generator/rig changes, or production integration. Trial24 remains a WIP base. Keep Chibi production sprites/rig/generators untouched.

## Follow-up layer-edge check

After choosing trial24, I reopened the two @2× isolated RGBA hand parts and rechecked the existing moderate C-engine board. ImageMagick's alpha scan found occupied pixels already on row 0 across x=21–70 (viewer-left, 92×116) and x=25–69 (viewer-right, 90×116). Visually, each part meets a broad, nearly horizontal top boundary at the canvas edge. The current source cuff covers that boundary in the registered neutral view and the existing ±30° sampled board; this is **not** evidence that a complete hidden wrist exists or that larger rotations/layer shifts cannot expose the edge. Treat it as an explicit hidden-wrist/under-cuff art gap, not something to repair with code. No new C frames were rendered and no hand pixels were changed.

## Isolated C visibility follow-up and trial26 art probe

- Added and ran `render_candidate_c_engine_wrist_layer_visibility_wip.c` through the actual isolated C `zrig`: 9 samples at wrist −30°, 0°, +30°, each in normal, whole-forearm-hidden, and mitten-hidden mode. The new board, runner logs/frame hashes, and limitations are in `trial24_wrist_layer_visibility_board_wip.png` and `trial24_wrist_layer_visibility_metrics_wip.json`.
- On the board, the normal mode keeps the hand visually joined beneath the original cuff at these three samples, though minor edge/shading differences remain. Hiding the mitten leaves the original forearm/cuff alone; hiding the entire forearm exposes the hand's upper/cropped boundary. This validates only the candidate layer ordering/visibility. There is no separately toggled cuff-front part in this candidate; `arm_*_fore` hides the full sleeve, not just the cuff. Three samples are not a motion safety or art-acceptance result.
- Tried trial26 AI edits to extend the wrist from the existing trial24 hand, with true transparency requested. Both outputs are RGB with opaque checkerboards, and the shapes deviate (left too broad/elongated, right too tall/narrow with a hard seam). I rejected them and did not chroma-key, matte-remove, fit, or insert them. Prompt, metrics, screenshots, and local SHA manifest are in `trial26_hidden_wrist_art_wip/`.

## Next work item

Continue Stage B/D in isolation from trial24: obtain an authorized source-aligned wrist continuation (or explicit art approval for sufficient hidden extent), then verify insert depth, the real cuff-front/back layering, and rotated C samples at native/enlarged scales. Do not invent or programmatically paint hand pixels; any missing art remains an explicit gap. The trial26 failure reinforces that generated alpha must be inspected, not assumed.
