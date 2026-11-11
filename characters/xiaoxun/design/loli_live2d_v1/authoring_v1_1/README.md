# Loli v1.1 authoring — round 01

## First preparatory result

`reference_v1_1_alpha_edge_connected.png` is a transparent-background **review derivative** of the user-selected v1.1 reference. The source image itself is immutable and remains the current NEW reference in the parent directory.

The extraction removes only near-white pixels belonging to connected components that touch the image border. It deliberately keeps enclosed near-white areas as foreground so the white jacket and shirt are not removed by a global white key. Current thresholds, pixel counts, bounding box, source hash, and output hash are in `isolation_metrics.json`.

## Files

- `reference_v1_1_alpha_edge_connected.png` — 1280×1920 RGBA, one complete flat character image with exterior background made transparent.
- `review_light.jpg`, `review_dark.jpg` — edge checks on light and dark fields.
- `isolation_metrics.json`, `SHA256SUMS.txt` — method, measurements, limitations and hashes.

Rebuild with `python3 tools/isolate_loli_v1_1_reference.py` (Pillow, NumPy and OpenCV required); validate with `python3 tools/check_loli_v1_1_isolation.py`.

## Not yet production artwork

This is not semantic segmentation, not separated hair/face/clothing layers, and not hand-painted hidden-region completion. The clothing and character are still fused into one flat image. The boundary is an automated first pass and needs visual edge cleanup; do not use this as a Cubism ArtMesh or claim it is a PSD/PSB, Cubism Editor project, MOC3, or runtime model.
