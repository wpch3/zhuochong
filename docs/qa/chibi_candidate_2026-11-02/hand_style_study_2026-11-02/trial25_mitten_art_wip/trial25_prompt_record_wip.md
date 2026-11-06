# Trial25 image-generation prompt provenance (WIP)

The generator returned the two files listed below. These are the exact prompt texts passed to the image-generation tool in this session; the tool did not provide a model/version identifier in its result. The references were passed as visual inputs, not edited or copied as pixels.

## Viewer-left output

Output: `trial25_viewer_left_hand_concept_wip.png`

References, in order:
1. `docs/qa/chibi_candidate_2026-11-02/hand_style_study_2026-11-02/source_left_cuff_hand.png`
2. `docs/qa/chibi_candidate_2026-11-02/hand_style_study_2026-11-02/trial15_viewer_left_hand_reference_wip.png`
3. `characters/xiaoxun/design/design_sheet_chibi.png`

Prompt:

> Create ONE isolated 2D anime character hand asset on a truly transparent background. This is a non-production WIP art study for the Chibi character shown in the references. Match the source character's soft cel-painted finish, dark plum thin outer contour, pale peach skin, restrained warm blush/shadow and small-scale rounded proportions; do not redesign the character. Only the viewer-left arm's hand and a short, complete wrist continuation extending upward from it; wrist opening at the top must be fully painted so it can tuck beneath an existing cuff, but do NOT draw any sleeve, cuff, clothing, arm beyond the short wrist, or background. Hand is a compact short-wide rounded mitten, no separated fingers, no finger creases, one tiny inward-facing thumb nub on the RIGHT edge of the image (toward the character's center when placed on viewer-left). Front/three-quarter neutral relaxed pose, hanging downward, silhouette compact like the approved trial15 hand size direction, no accessories, no text, no border, no cast shadow. Preserve clean contour and restrained source-like shading. Output a single asset only, not a sheet or collage.

## Viewer-right output

Output: `trial25_viewer_right_hand_concept_wip.png`

References, in order:
1. `docs/qa/chibi_candidate_2026-11-02/hand_style_study_2026-11-02/source_right_cuff_hand.png`
2. `docs/qa/chibi_candidate_2026-11-02/hand_style_study_2026-11-02/trial15_viewer_right_hand_reference_wip.png`
3. `characters/xiaoxun/design/design_sheet_chibi.png`

Prompt:

> Create ONE isolated 2D anime character hand asset on a truly transparent background. This is a non-production WIP art study for the Chibi character shown in the references. Match the source character's soft cel-painted finish, dark plum thin outer contour, pale peach skin, restrained warm blush/shadow and small-scale rounded proportions; do not redesign the character. Only the viewer-right arm's hand and a short, complete wrist continuation extending upward from it; wrist opening at the top must be fully painted so it can tuck beneath an existing cuff, but do NOT draw any sleeve, cuff, clothing, arm beyond the short wrist, or background. Hand is a compact short-wide rounded mitten, no separated fingers, no finger creases, one tiny inward-facing thumb nub on the LEFT edge of the image (toward the character's center when placed on viewer-right). Front/three-quarter neutral relaxed pose, hanging downward, silhouette compact like the approved trial15 hand size direction, no accessories, no text, no border, no cast shadow. Preserve clean contour and restrained source-like shading. This hand should be drawn as its own anatomically plausible counterpart with slightly different natural contour, not a mirrored duplicate. Output a single asset only, not a sheet or collage.

## Outcome

Despite the request for transparency, the delivered PNGs are RGB with no alpha. This mismatch is recorded in `trial25_metrics_wip.json`; the actual images failed and were not used as parts.
