# Trial 30 — normal-fingered hand concept (WIP / rejected at target scale)

- **Original**: `chibi_normal_fingered_hand_left_trial30_wip.png` (1008×1070, sRGB, opaque gray background/no alpha).
- **45×48 probe**: `trial30_target_box_45x48_visual_probe_wip.png` (360×384, display enlarged 8×; opaque diagnostic, not an engine render or sprite).
- **References**: Chibi design sheet and registered small-left source crop; visual pose/style/scale references only, no source pixels copied.

## Visual review

The full-resolution image has a relaxed downward orientation and a compact-looking hand, but it includes a long wrist shaft and adult-like palm/finger proportions. After reduction to the registered hand box, the separations between the four fingers become shallow grooves; it reads as a mitten/paw rather than a normal hand. Line weight/shading also remain heavier and smoother than the Chibi source. **Rejected as Chibi normal-hand art.**

Probe method: ImageMagick `-fuzz 6% -trim +repage` to frame the opaque gray-background subject, LANCZOS fit to 45×48, center on a 45×48 opaque canvas using the sampled top-left gray, then nearest-neighbor 8× enlargement. This is only a visual diagnostic, not a production crop, C-engine render, or Cubism render.

## Boundary

`REJECTED_TARGET_SCALE_READABILITY_AND_PROPORTION_WIP`. No alpha extraction, cuff fit, right-hand pairing, hidden-wrist art, rig insertion, or production use. Keep normal-fingered style independent from the still-provisional mitten direction.
