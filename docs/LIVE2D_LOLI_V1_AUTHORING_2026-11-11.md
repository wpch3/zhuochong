# Loli v1 Cubism authoring — progress log (2026-11-11)

## Selected source and first saved step

The user selected the original Loli v1 concept. Its flat source remains `characters/xiaoxun/design/loli_live2d_v1/concept_front_keyed.png` (848×1264). A first general layer scaffold was created at `characters/xiaoxun/design/loli_live2d_v1/cubism_source/`: an 848×1360 OpenRaster with 69 transparent part placeholders and one locked reference. The placeholders were never presented as artwork.

## Face cutout pass 01

`characters/xiaoxun/design/loli_live2d_v1/cubism_source/face_pass_01/` now contains seven actual raster cutout layers: whale clip, two brows, two eyes, nose, and closed mouth. The masks were hand traced from the accepted image (the clip also uses color thresholding). Source pixels are retained in those cutout layers. Matching holes in the base are filled by OpenCV Telea inpainting; this is approximate occlusion underpaint, not human-finished art. Visual review caught and fixed an initial brow-selection misregistration and reduced the inpaint mask to prevent smearing adjacent hair/lash lines. The current aligned reconstruction differs at only 87 RGB pixels by more than two levels, with max channel difference 57; this is a structural comparison and not art approval.

Rebuild/check:

```sh
python3 tools/build_loli_face_pass.py
python3 tools/check_loli_face_pass.py
```

Requires Pillow, NumPy, and OpenCV. The web inspector is served by the existing C engine at `/loli-authoring.html`. It toggles layers, shows a reference overlay, permits temporary pixel nudges/drag for cutout QA, and exports a review PNG. Those offsets do not create Cubism parameters or motion. A link to the inspector is also on the sandbox home page.

## Current visual and production limits

This first pass isolates only small facial parts. Hair, ears, face outline, neck, torso, jacket, sleeves, hands, skirt, legs, socks, and shoes remain fused in the flat base. The selection edges and algorithmic inpaint need close visual cleanup, and the source still lacks a full set of hidden/overlap underdraws. The included ORA is editable OpenRaster, **not** PSD/PSB, not a Cubism Editor project, and not a runtime model. The flat base remains unsuitable for meaningful body/hair deformation.

## Next sequence

1. Use the new sandbox inspector for layer and edge review; then continue art separation from the accepted source: full face/scalp, bangs, side/back hair and ears, with hand-painted skin/hair underdraws. Keep the reference hidden and locked.
2. Split neck, torso, jacket body/sleeves, arms/hands, skirt, legs, socks, shoes. Build overlapping pieces with deliberately painted hidden regions; test each group at small offsets in the inspector, then replace approximate inpaint patches with painted cleanup.
3. Keep an editable layered art source and an approved flat reconstruction before importing. The ORA is a work-in-progress interchange file; Cubism Editor's PSD workflow must be verified against the eventual layered PSD.
4. The previous environment probe found no Cubism Editor or desktop paint application executable installed. Do not claim an Editor import, official project, export, or runtime test until such a tool is actually available and those steps have run.
5. Only after Editor access and finished art: import PSD; build and inspect ArtMeshes, deformers, parameters, physics, expressions/motions; save the official project; export and run-check the real output. Check component-specific current licensing before using Editor tiers or redistributing runtime SDK/Core output.

## Official references checked earlier

- [Illustration Processing](https://docs.live2d.com/en/cubism-editor-tutorials/psd/) — split hair/face/body; complete hidden parts; PSD prep recommendations.
- [Adding Body Movement / Deformers](https://docs.live2d.com/en/cubism-editor-tutorials/deformer/)
- [Cubism Editor FREE vs PRO](https://www.live2d.com/en/cubism/comparison/)
- [SDK Release License](https://www.live2d.com/en/sdk/license/)
