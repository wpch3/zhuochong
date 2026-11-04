# Trial 28 — compact normal-fingered hand concept (WIP / not approved)

- **Purpose**: make the normal-fingered `small` style more distinguishable from the separately retained mitten style.
- **Output**: `chibi_normal_fingered_hand_left_trial28_wip.png` (1024×1024, sRGB, opaque pale-gray background/no alpha).
- **Target-box visual probe**: `trial28_target_box_45x48_visual_probe_wip.png` (display enlarged 8× from an opaque 45×48 diagnostic thumbnail; not an engine render or sprite).
- **References**: Chibi design sheet and registered small-left source crop were style/proportion references only; no source pixels were copied.

## Visual review

Opened the 1024×1024 result. Compared with trial27, its palm and fingers are shorter and rounder; thumb and four digit lobes are distinguishable at original size. The 45×48 diagnostic probe was then opened: finger clefts soften and the shape reads as a paw/mitten rather than an unmistakably normal-fingered hand. The outline and smooth shading also remain heavier/softer than the Chibi source. **Not approved; keep only as a shape-study WIP.**

The target-box probe locates the opaque subject bounds using an RGB difference threshold (>18 from the top-left gray background sample), crops while retaining the gray background, LANCZOS-reduces to fit 45×48, centers on an opaque gray 45×48 canvas, then enlarges 8× nearest-neighbor for manual inspection. This is a scale diagnostic only—not an exact C-engine/Cubism render and not production artwork.

## Status and boundaries

`NORMAL_FINGERED_SHAPE_STUDY_WIP_NOT_APPROVED`. Keep separate from trial24 mitten; do not substitute it for either style. No alpha extraction/chroma key, source-cuff fitting, hidden-wrist fabrication, mirror/crop to create the right hand, rig insertion, or production edit was performed. Normal-fingered art, the left/right pair, cuff/hidden-wrist layers, user review, and actual Cubism modeling remain open; see `docs/memory/CHIBI_CUBISM_TRUE_MODEL_AUDIT_2026-11-04.md`.
