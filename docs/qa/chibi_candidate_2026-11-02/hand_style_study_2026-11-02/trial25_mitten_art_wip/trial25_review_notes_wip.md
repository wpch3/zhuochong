# Trial25 independent mitten hand art study — WIP review

**Decision: reject as source art / transparent hand parts; retain only as a documented failed generation.** No image was cleaned, cut out, recolored, resampled, or fitted to the source cuff. No rig/C-engine test was performed. Nothing from this trial may enter production.

## Inputs and scope

Generated two separate hand concepts using the registered Chibi `design_sheet_chibi.png`, the corresponding source cuff/hand crop, and the approved trial15 size-direction crop as visual references. The prompt asked for compact left/right mitten silhouettes, inward-facing thumb nubs, Chibi-like shading, and a short hidden-wrist continuation. Trial15 approval remains size-direction only; it does not approve generated pixels. The reference images were not used as pixel sources.

## Actual outputs

- `trial25_viewer_left_hand_concept_wip.png` — 1024×1024 PNG, SHA-256 `ae620dc048fb5ee8d336217a26fe922e025d363dbfb8cdea34de7d13cc3b1136`
- `trial25_viewer_right_hand_concept_wip.png` — 912×1150 PNG, SHA-256 `4e3e7b0d3913807d6d89d2e707bcb386c3c2499c93088cc63b7fdcebce07ddd7`

## Inspection and observed failure

Both images were opened at native resolution. PNG headers report color type 2 (RGB), not color type 6 (RGBA); `identify` reports `srgb` channels with no alpha. Thus the checkerboard-looking backgrounds are **opaque RGB pixels**, not transparency. The left image corner sample at `(0,0)` is `srgb(52,11,47)`; the right is `srgb(197,198,197)`. They are not cutout-ready transparent parts.

Visual inspection:

- Both generated forms have a very long, narrow forearm/wrist shaft compared with the compact hand size target, ending in a blunt visible top cut. That does not establish hidden-wrist continuity under the source cuff.
- The inward thumb nub is on the intended inner edge in each output, and the two silhouettes are not identical mirrors. This limited shape success does not offset the failures.
- Their heavy uniform dark-plum outlines and smooth, broad gradients differ from the Chibi source's finer, softer line/shadow treatment. The generated pair does not read as source-aligned Chibi art.

**Outcome:** preserve the originals as negative evidence only. Do not run chroma-key, matte removal, source-cuff fitting, or C-engine insertion on these files; doing so would disguise the non-transparent output and would not fix the style/proportion mismatch. A compliant source-aligned pair with genuinely complete hidden wrists remains outstanding.

## Reproducible checks

```sh
identify -format '%f: %m %wx%h %[channels]\\n' trial25_*_concept_wip.png
sha256sum trial25_*_concept_wip.png
```

Metrics: `trial25_metrics_wip.json`. This trial is a failed isolated art-generation attempt, not an acceptance review or production asset.
