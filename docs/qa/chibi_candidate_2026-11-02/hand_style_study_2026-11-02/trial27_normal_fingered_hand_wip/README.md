# Trial 27 — normal-fingered hand concept (WIP / rejected)

- **Purpose**: explore an independently legible normal-fingered hand, not replace the existing mitten style.
- **Output**: `chibi_normal_fingered_hand_left_trial27_wip.png` (1024×1024, sRGB, opaque background/no alpha).
- **Target-box visual probe**: `trial27_target_box_45x48_visual_probe_wip.png` (display enlarged 8× from an opaque 45×48 diagnostic thumbnail; not an engine render or sprite).
- **References**: Chibi design sheet and registered small-left source crop were visual references only; no source pixels were copied.

## Visual review

Opened the full-resolution output: four distinct fingers and a thumb are visible, but the fingers/hand are elongated and adult-proportioned; linework and shading diverge from the Chibi source. The 45×48 diagnostic probe retains separated digit shapes, but makes the long/slender proportions more obvious. **Rejected as Chibi hand art**; preserve only as a negative style/proportion probe.

The target-box probe locates the opaque subject bounds using an RGB difference threshold (>18 from the top-left gray background sample), crops while retaining the gray background, LANCZOS-reduces to fit 45×48, centers on an opaque gray 45×48 canvas, then enlarges 8× nearest-neighbor for manual inspection. This is a scale diagnostic only—not a C-engine/Cubism render and not production artwork.

## Status

`REJECTED_STYLE_AND_PROPORTION_WIP`. This is neither source art nor a production part. No alpha extraction, cuff fit, hidden-wrist continuation, right-hand derivation, rig insertion, or production use was performed. The normal-fingered style remains required and unfinished; mitten remains independently required.
