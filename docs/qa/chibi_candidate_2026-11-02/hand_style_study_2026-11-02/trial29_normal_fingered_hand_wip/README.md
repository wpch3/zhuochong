# Trial 29 — normal-fingered hand concept (WIP / rejected for Chibi fit)

- **Purpose**: test whether five clearly separated digits can survive a 45×48 target box, while retaining the required normal-fingered style independently of the mitten style.
- **Original output**: `chibi_normal_fingered_hand_left_trial29_wip.png` (1024×1024, sRGB, opaque gray background/no alpha).
- **Target-box visual probe**: `trial29_target_box_45x48_visual_probe_wip.png` (display enlarged 8× from a 45×48 diagnostic thumbnail; not an engine render and not a sprite).
- **References**: Chibi design sheet and registered small-left source crop, used only as visual references; no reference pixels copied.

## Visual review

At full resolution this image shows one thumb and four distinct fingers. The 45×48 probe also retains visibly separate digits. However, generation interpreted the prompt as a palm-facing, widely spread open hand, with longer/adult-like fingers and a pose unlike the relaxed side-hanging Chibi hand. Its contour and line/shading treatment also diverge from the source. **Rejected for Chibi pose, proportion, and style; retain only as a shape/readability probe.**

The 45×48 probe was made by finding the opaque gray-background subject bounds (RGB difference threshold >18 from the top-left background sample), cropping while retaining that background, LANCZOS-reducing to fit 45×48, centering on an opaque gray 45×48 canvas, then enlarging 8× with nearest-neighbor for inspection. This does not remove a matte or create transparency, but it is only a manual-scale diagnostic—not an exact C renderer/Cubism preview and not production artwork.

## Status and boundaries

`REJECTED_POSE_AND_STYLE_WIP`. It is not an approved normal-fingered hand, source-aligned part, or production asset. No alpha extraction, cuff fit, hidden-wrist fabrication, left/right pairing, rig insertion, or production change was attempted. The normal-fingered style remains required and unfinished; trial24 remains a separate provisional mitten direction. True Cubism authoring remains blocked by the missing approved layered PSD and Cubism Editor environment; see `docs/memory/CHIBI_CUBISM_TRUE_MODEL_AUDIT_2026-11-04.md`.
