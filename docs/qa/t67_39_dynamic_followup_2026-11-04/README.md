# T67.39 dynamic follow-up: long-hair occlusion under arm motion (2026-11-04)

**Status: reproduced visual failure in a sampled real-C preview; diagnosis and repair remain open.** This follow-up narrows the earlier fixed-pose T67.39 result. It does not claim that every transparent pixel is wrong, nor that alpha-zero alone is the only cause.

## Reproduction

The running `make preview` server rendered the production Teen assets through the project's C engine at 848×1360 / scale 1.0.

1. Select `hairstyle=long`, `hood_pose=up`; set `ParamHairSway=0`, keep the arm at idle, settle the pose, pause, and capture `teen_long_hood_up_idle_static_c_engine.png`.
2. From the same pose, trigger `surprised`, step 12 frames at 0.05 s, set `ParamHairSway=+1`, step 10 more frames at 0.05 s, and capture `teen_long_hood_up_surprised_c_engine.png`.
3. `idle_vs_surprised_detail.png` places the same torso/hand/hair region side-by-side on magenta to make transparent output visible. It is cropped and enlarged from those C-engine frames; it does not add or redraw character pixels.

The surprised frame reports `ParamArmLA/RA=0.6`, `ParamArmLB=8.35`, `ParamArmRB=8.1`, `ParamSurpriseArmSwap=1`, and `ParamHairSway=1` at the sampled endpoint. The action is still `surprised` when captured. This is one diagnostic pose, not a full motion matrix.

## Visual finding

At rest, the normal arms/cuffs largely coincide with the baked-in locations. In the raised-arm frame, old-position cuff/hand-shaped remnants remain visible near the lower hair, and the hair silhouette has transparent gaps where the old arm/cuff shape was cleared. The isolated `characters/xiaoxun/forms/teen/sprites/hair_hood_long@2x.png` also visibly contains alpha cutouts and remaining non-hair-looking cuff/skin pixels.

This is enough to reject the broad claim that the fixed-pose T67.39 screenshot proves dynamic coverage. It supports the concern in `建议.md` L-01 that moving an occluder can reveal a cutout, but **does not** establish that alpha=0 is the sole cause: residual contamination, pose composition, and per-part motion also need separate tracing. A blanket `alpha == 255` rule for an entire hair texture is not appropriate; designed strand/background transparency is valid.

## Next action / gates

- Re-open the exact source/part mapping and distinguish transparent cutout pixels from surviving baked arm/cuff pixels.
- Find a source-art or approved inpainting/reconstruction path that produces continuous hair only where hair is structurally expected; do not restore the foreign arm, use an unreviewed color-fill, or hide the symptom with an arbitrary offset.
- Re-render idle and arm-raised/surprised poses plus long-hair sway extremes on the same base, and visually inspect full-body and wrist/hair crops. Static coverage alone is insufficient.
- No production sprite, rig, generator, or engine file was edited for this test. Do not treat this QA evidence as a repair or as permission to alter the asset.

The initial evidence board is `idle_vs_surprised_detail.png`; full 848×1360 captures are retained alongside it for context.
