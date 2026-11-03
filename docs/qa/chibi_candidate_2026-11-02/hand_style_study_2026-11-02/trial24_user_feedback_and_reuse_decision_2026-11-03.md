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

## Next work item

Continue Stage B/D in isolation from trial24: get an authorized source-aligned wrist continuation (or obtain explicit art approval for a sufficient hidden extent), then verify the actual insert/under-cuff overlap and cuff layering with visible/hidden-layer diagnostics, and inspect the problematic rotated C samples at native and enlarged scales. Do not invent or programmatically paint hand pixels; any missing art remains an explicit gap.
