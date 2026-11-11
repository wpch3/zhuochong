# v1.1 head/face separation — pass 01 (WIP)

This is the first **actual editable-layer pass** from the user's selected NEW/current v1.1 reference. It is deliberately limited to a small facial/accessory area; it is not finished source art and is not a Live2D model.

## Editable deliverable

Open `xiaoxun_loli_v1_1_head_pass_01.ora` in Krita, GIMP, or another OpenRaster-compatible raster editor. The full-size 1280×1920 stack contains:

- visible `00 Figure base with approximate face underpaint (WIP; body/hair still flat)`;
- a `20 Face cutouts - WIP` group containing `Whale_Clip`, `Brow_L`, `Brow_R`, `Eye_L`, `Eye_R`, `Nose`, and `Mouth_Closed` as separate full-canvas transparent PNG layers;
- a hidden, locked-in-purpose reference copy named `NEW v1.1 full reference - locked, hidden`.

The matching PNGs can also be edited/replaced directly. `head_pass_composite.png` is the current static reassembly; `reconstruction_diff.png` is a numeric RGB difference visualization against the transparent v1.1 source, not an art-quality assessment. `layer_manifest.json` records source, selections, current status, file bounds/metrics and restrictions. `SHA256SUMS.txt` records file hashes.

## What was done

- Face/accessory cutouts were selected in native 1280×1920 coordinates from the v1.1 isolated-alpha reference; white fabric was not color-keyed.
- A feature-local approximate underpaint was made beneath the isolated cutouts using OpenCV Telea inpainting. The base alpha was correspondingly reduced under each extracted feature so the isolated feature layer can sit above it.
- The whale clip uses a small ROI-limited teal selection and keeps only its largest connected component to avoid an unrelated detached speck.
- Reassembly check: 67 pixels differ by more than 2 RGB levels; maximum channel difference is 41. This is a registration/compositing sanity check only, not proof of a clean edge or acceptable inpaint.

Rebuild and check from the repository root:

```sh
python3 tools/build_loli_v1_1_head_pass.py
python3 tools/check_loli_v1_1_head_pass.py
```

## Honest limitations / next art pass

- `Base_Figure_Face_Underpaint_WIP.png` is still one flat character for all hair, head silhouette, ears/neck, body, jacket, sleeves, hands, skirt, legs, socks and shoes. Their hidden overlap regions are **not** painted yet.
- Facial selections are first-pass source-pixel masks, not carefully hand-redrawn final art. Because the reference's fringe crosses facial areas, some source-visible hair pixels occur at the eye/brow selection edges; refine ownership and cleanup by zoomed manual review before deformation.
- Inpainted regions are algorithmic approximations, visibly not guaranteed seamless. Replace with hand-painted underdraw and repair any seams/stray pixels in a raster editor. Do not deform this pass as production art.
- There are no blinking eye states, iris/pupil layers, mouth shapes, hair-strand layers, full-body part set, PSD/PSB, Cubism Editor project, ArtMeshes, deformers, physics, `.moc3`, `.model3.json`, or runtime validation here.
- Do not call this ORA a PSD or call it Cubism. A proper layered PSD/PSB still needs to be created/import-checked in the official Editor when that environment is available.
