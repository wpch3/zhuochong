# Trial 42 — viewer-right target-crop edit (rejected WIP)

A focused edit of the exact source-pixel viewer-right hand ROI, presented at 8× nearest-neighbour solely as a diagnostic reference. The intent was to edit the compact source box while preserving the source cuff and side/back hanging pose; this is not a production source layer.

**Agent review: reject.** The model expanded the arm/cuff, altered the cuff fabric and proportions, enlarged the hand, and returned an opaque RGB checkerboard. The hand does show multiple lobes, but the result is oversized, too smooth/heavy in outline, and not registered to the Chibi source. No thresholding, background removal, fitting, mirroring, or rig insertion was performed.

- Source ROI: `body_full.png` `[462,880,507,926]` (45×46); reference display is 360×368 RGBA nearest-neighbour enlargement.
- Output: 1024×1047 RGB, no alpha.
- This is diagnostic negative evidence only. Never use the opaque checkerboard as transparency or a production asset.
