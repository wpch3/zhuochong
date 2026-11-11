# Loli v1 face cutout pass 01 — WIP

This pass turns seven previously named placeholders into real raster cutout layers: `Whale_Clip`, `Brow_L`, `Brow_R`, `Eye_L`, `Eye_R`, `Nose`, and `Mouth_Closed`. Selections are hand-traced polygons (the whale clip uses a tight teal color mask), and each layer preserves source pixels from the user-selected flat concept. The base image has only those selected regions filled by OpenCV Telea inpainting, to provide approximate pixels behind movable facial pieces.

## Files

- `xiaoxun_loli_face_pass_01.ora` — editable OpenRaster with the cleaned base, seven cutout layers, and a hidden reference layer.
- `Base_Face_Underpaint_WIP.png`, `Whale_Clip.png`, `Brow_*.png`, `Eye_*.png`, `Nose.png`, `Mouth_Closed.png` — full-canvas aligned RGBA layers at 848×1360; source artwork sits at y=48 without scaling.
- `face_pass_composite.png` — all parts aligned over the base, for visual comparison.
- `reference_front_848x1360.png` — the accepted flat reference, unchanged, in the same registration.
- `reconstruction_diff.png` — per-pixel RGB difference visualization against that reference.
- `layer_manifest.json`, `SHA256SUMS.txt` — scope, limitations, and checksums.

## Important limits

This is an **initial facial cutout pass**, not finished production art. The inpainted underdraw is algorithmic and visibly approximate at close inspection; it has not been hand-painted or tested under deformation. Hair, ears, face silhouette, neck, torso, jacket, sleeves, hands, skirt, legs, socks, and shoes remain fused in the flat base. Some selection edges need manual cleanup. Do not import this as a finished Cubism character or call it a PSD/Cubism project/runtime model.

Rebuild with `python3 tools/build_loli_face_pass.py` and check with `python3 tools/check_loli_face_pass.py`; both need Pillow, NumPy, and OpenCV. The repo sandbox's C preview provides the layer-toggle/nudge review page at `/loli-authoring.html`; nudging is only a static QA aid, not Cubism motion.
