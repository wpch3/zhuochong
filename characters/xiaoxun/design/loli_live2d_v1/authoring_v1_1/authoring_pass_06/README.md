# Loli v1.1 authoring pass 06 — upper-body cutout and overlap-fill WIP

This pass continues the editable illustration stage from the approved v1.1 reference. It is **not a completed character master, not PSD/PSB, and not a Cubism project/model**.

## What is here

- `xiaoxun_loli_v1_1_authoring_pass_06.ora`: standalone 1280×1920 ORA with the 20 pass05 visible layers carried forward, eight new upper-body visible-source cutouts, four estimated hidden-fill layers and a flat approximate-inpaint base.
- New source-visible cutouts: `Jacket_Body_L/R`, `Shirt_Front`, `Neck`, `Cuff_L/R`, `Hand_L/R`.
- Estimated underfills: `Underpaint_Shirt_WIP`, `Underpaint_Jacket_WIP`, `Underpaint_Hand_L_WIP`, `Underpaint_Hand_R_WIP`. These are coordinate/shape-guided flat fills restricted to current overlap footprints. They are not brush-painted line art or texture and have not been tested under model deformation.
- `upper_body_edge_review.jpg` is an enlarged transparency-board review of these new parts and fills. `layer_review_board.jpg` shows the full 32-part stack. `authoring_pass_06_composite.png` and `reconstruction_diff.png` show static registration to the source. The `layer_manifest.json` and `SHA256SUMS.txt` record scope and integrity.

Rebuild and run the structural/pixel check from the repository root:

```sh
python3 tools/build_loli_v1_1_upper_body_pass.py
python3 tools/check_loli_v1_1_upper_body_pass.py
```

## Edge review notes and limits

The source-pixel masks were inspected on checkerboard boards and bounded to traced ROIs. The neutral source reassembles exactly (0 changed pixels above 2 RGB levels, max channel difference 0), and the checker verifies ORA structure, dimensions, bounds, and current metric. This only proves static source registration and file integrity.

Visible source strokes at the jacket/pocket/zipper seams still need manual line-ownership cleanup; the neck/hand contours need close painting-app inspection. The hidden shirt/jacket/hand fills are flat approximations, not enough to support arbitrary motion. The neck still has no skin continuation safely painted behind the hair because the hair has not yet been separated from the flattened base. The hands remain source cutouts, not articulated upper-arm/forearm/hand parts. Jacket collar/facings and the main sleeve/cuff seam still need full semantic separation. Hair/back-head, face outline/ears, eyelid/closed-eye and mouth interior art are also unfinished.

The sandbox lacks a raster paint editor; do not describe these fills as hand-painted or the edges as fully approved. The next actual art-acceptance gate remains manual high-zoom edge cleanup and hidden-region painting in a supported raster editor, followed by review at representative offsets. No PSD/PSB or Cubism work should begin until the complete illustration is visually accepted.
