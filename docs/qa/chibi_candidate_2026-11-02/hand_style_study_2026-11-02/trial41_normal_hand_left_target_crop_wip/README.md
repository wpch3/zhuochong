# Trial 41 — viewer-left target-crop edit (rejected WIP)

A focused edit of the exact source-pixel viewer-left hand ROI, presented at 8× nearest-neighbour solely as a diagnostic reference. The intent was to change the hand silhouette in the small target crop while preserving the source cuff and side/back hanging pose; this is not a production source layer.

**Agent review: reject.** The model expanded the cuff/arm far beyond the registered crop, changed its striped fabric and outline, produced oversized adult-length digits, and rendered the checkerboard as opaque RGB pixels. Although several digits are visible, it does not preserve the Chibi target scale, source cuff, or line weight. No thresholding, background removal, fitting, mirroring, or rig insertion was performed.

- Source ROI: `body_full.png` `[62,878,107,926]` (45×48); reference display is 360×384 RGBA nearest-neighbour enlargement.
- Output: 992×1058 RGB, no alpha.
- This is diagnostic negative evidence only. Never use the opaque checkerboard as transparency or a production asset.
