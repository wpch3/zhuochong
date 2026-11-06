# Trial 31 — normal-fingered hand concept (WIP / rejected for style)

- **Original**: `chibi_normal_fingered_hand_left_trial31_wip.png` (992×1072, sRGB, opaque gray background/no alpha).
- **45×48 probe**: `trial31_target_box_45x48_visual_probe_wip.png` (360×384, 8× nearest-neighbor display; diagnostic only).
- **References**: Chibi design sheet and registered small-left source crop, used for visual reference only.

## Visual review

At original size, trial31 makes four finger ends plus a thumb and three deep separations explicit. The actual 45×48 probe still shows distinct digits. However, the output has conspicuously blocky/pixel-art contour steps and a broad, adult-like palm/wrist shaft, unlike the soft fine-line Chibi design sheet. **Rejected for source-style and proportion mismatch**, despite the useful separation result. No pixels were fitted or reused.

Probe method: ImageMagick `-fuzz 6% -trim +repage` to frame the opaque gray-background subject; LANCZOS fit to 45×48 on a sampled-gray opaque canvas; nearest-neighbor 8× enlargement. It is not a renderer output or production sprite.

## Boundary

`REJECTED_STYLE_AND_WRIST_PROPORTION_WIP`. No alpha extraction, cuff fit, viewer-right derivation, hidden-wrist fill, rig insertion, or production use. This trial suggests the finger-gap criterion can survive reduction, but the artwork still fails.
