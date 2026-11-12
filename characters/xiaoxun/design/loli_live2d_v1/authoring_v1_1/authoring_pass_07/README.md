# Loli v1.1 authoring pass 07 — hair separation WIP

This pass starts the hair pieces from the approved v1.1 source, preserving pass06 and adding a source-visible hair split plus an estimated hidden-face fill. It is **not complete hair art**, not an overlap-approved full illustration, and not PSD/PSB or Cubism.

## Layers and files

- Five new source-visible cuts: `Hair_Back`, `Hair_Side_L`, `Hair_Side_R`, `Hair_Bangs`, `Hair_Ahoge`.
- `Underpaint_FaceBehindHair_WIP` is a flat sampled-color estimate, limited to the current bangs/side-hair coverage. It contains no reconstructed line art or shading.
- `xiaoxun_loli_v1_1_authoring_pass_07.ora`: 1280×1920 ORA containing 38 stack parts (pass06's 32 plus these six), the locked hidden v1.1 reference and an approximate inpaint base.
- `hair_edge_review.jpg` magnifies the new hair selections on checkerboard; `layer_review_board.jpg` shows the complete stack. Composite, difference image, manifest and SHA list are included.

Build/check:

```sh
python3 tools/build_loli_v1_1_hair_pass.py
python3 tools/check_loli_v1_1_hair_pass.py
```

## Inspection and limitations

The current selections are native-coordinate ROI and color masks, not brush-traced finished layers. The review board still shows small isolated edge fragments and uneven boundaries around the side locks/fringe; those require manual cleanup in a raster editor. The fringe mask also needs line-ownership review against brows/eyelids at high zoom. The ahoge root and crown overlaps are only approximated from visible source pixels.

The hidden face fill is flat and does not provide a complete head/skin surface, line art, shading, or a back-hair extension behind the fringe. Ears and the face outline remain fused to the base. The zero-difference static reconstruction, bounds and source RGB checks certify only registration/file structure. No manual brush cleanup, dynamic deformation review, PSD/PSB import, Cubism project/export or runtime validation has been performed.

The sandbox has no installed Krita/GIMP/Photoshop paint UI, so the manual edge-cleanup stage cannot honestly be claimed complete here. Keep this pass labelled WIP and continue to the next parts only as bounded source prep until a real paint editor is available.
