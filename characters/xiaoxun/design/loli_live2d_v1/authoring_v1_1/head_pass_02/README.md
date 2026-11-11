# v1.1 head/face separation — pass 02 (superseded WIP)

**Do not rig or continue from this pass. Pass 03 replaces the combined eye stickers with separate sclera, eyeball and eyelash layers.** This revision followed a source-at-native-resolution review after the first pass exposed coordinate/mask mistakes. The earlier `head_pass_01` files remain as history only and are **superseded; do not rig or continue from pass 01**.

## Editable deliverable

Open `xiaoxun_loli_v1_1_head_pass_02.ora` in Krita, GIMP, or another OpenRaster-compatible raster editor. It is a 1280×1920 editable stack with:

- a full-body flat base with an approximate, algorithmically inpainted face area;
- seven full-canvas transparent cutouts grouped above it: whale clip, left/right brow, left/right eye, nose mark, closed-mouth strokes;
- a hidden full-resolution NEW/current v1.1 reference layer.

Matching PNGs, `layer_manifest.json`, `head_pass_composite.png`, `reconstruction_diff.png`, and SHA-256 list are included. This is OpenRaster, **not PSD/PSB**.

## Corrections made after pass 01

- Replotted a source close-up against native 1280×1920 coordinate labels. Pass 01's hand-guessed eye/brow polygons were shifted and cut into neighboring hair; pass 02 puts the eyes and brows over the actual facial features.
- Replaced the large nose and mouth skin patches from pass 01 with small ROI-constrained dark-pixel selections, so pale cheek skin remains on the base. The nose selection is only 13 pixels; mouth strokes are 100 pixels.
- Kept the whale ROI restricted and ignored detached color specks by retaining its largest teal connected component.

The static reassembly has 80 pixels differing by >2 RGB levels, maximum channel difference 50. These metrics are **not improved versus pass 01** (67 pixels / max 41): they are merely bounded registration/compositing diagnostics. The visible first-pass cheek blobs are removed, but this is not an artistic acceptance metric.

## Still WIP — important

- The eyes/brows are cut from the flattened source. The visible fringe overlap and hidden eyelid/skin content cannot be truthfully reconstructed from a single front image; current masks cannot be considered deformation-ready. Eye blinking, iris/pupil/highlight splits and alternate mouth shapes do not exist.
- Base face underpaint is OpenCV Telea interpolation, not hand-painted production art. Replace it with hand-painted continuous underdrawing, refine mask edges in an actual raster editor, and test shifted layers over contrasting backgrounds.
- Hair, head silhouette, ears/neck, jacket, sleeves/cuffs, arms/hands, skirt, legs, socks and shoes are still one flat figure. Their hidden overlap art is not created.
- No PSD/PSB, official Cubism Editor project, ArtMeshes, deformers, physics, `.moc3`, `.model3.json`, or runtime validation exists.

Rebuild/check from the repository root:

```sh
python3 tools/build_loli_v1_1_head_pass.py
python3 tools/check_loli_v1_1_head_pass.py
```

The checks validate structure, nonempty bounds, ORA file correctness and reassembly matching; they do not certify visual quality or official Cubism compatibility. Continue from this pass only after the facial masks and underpainting are manually reviewed and repaired.
