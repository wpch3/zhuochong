# Trial 32 — normal-fingered hand concept (WIP / rejected for Chibi fit)

- **Original**: `chibi_normal_fingered_hand_left_trial32_wip.png` (1008×1070, sRGB, opaque gray background/no alpha).
- **45×48 probe**: `trial32_target_box_45x48_visual_probe_wip.png` (360×384, 8× display enlargement; opaque-background visual diagnostic).
- **References**: Chibi design sheet and registered small-left source crop, used as style/pose/scale references only.

## Visual review

The smooth contour is closer to the Chibi source than trial31, and four distinct short finger ends plus a thumb can be seen at original size. At 45×48, the finger tips remain separate, but the narrow long wrist and elongated fingers still read as an adult-like hand; outline and shading are also heavier than the source. **Rejected for proportion/style**, not an approved hand. No reference pixels were copied.

Probe method: ImageMagick `-fuzz 6% -trim +repage` to frame the opaque gray-background subject, LANCZOS fit to 45×48 on an opaque canvas matching the sampled top-left gray, then nearest-neighbor 8× enlargement. This is not a Cubism/C-engine render and not a sprite.

## Boundary

`REJECTED_PROPORTION_AND_STYLE_WIP`. No alpha extraction, cuff fit, right-hand pairing, hidden-wrist completion, rig insertion, or production use. Normal-fingered art remains unfinished and independent from the provisional mitten direction.
