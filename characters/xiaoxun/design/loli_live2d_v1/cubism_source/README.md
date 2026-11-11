# Loli v1 Cubism source scaffold (WIP)

This is an **authoring scaffold only**. The OpenRaster file has 69 empty transparent drawing placeholders and a single flattened reference image at 55% opacity. It does not contain 69 separated character parts or repaired occluded artwork.

- `xiaoxun_loli_cubism_source_v1.ora` — editable layer/group container, 848×1360.
- `layer_manifest.json` — layer intent and limitations.
- `reference_front_848x1360.png` — accepted flat concept on a registered transparent canvas; source artwork retains native 848×1264 size and is offset by 48 pixels from the canvas top.
- `template_preview.jpg` — review composite.

**Not included:** PSD/PSB, Cubism Editor project, ArtMeshes, deformers, parameters, physics, motions/expressions, MOC3, model3 JSON, or runtime validation. Do not use the flattened reference as a production ArtMesh/export.

Regenerate from the selected source with `python3 tools/make_loli_cubism_template.py`; run `python3 tools/check_loli_cubism_template.py` afterward. Both tools require Pillow. Read `docs/LIVE2D_LOLI_V1_AUTHORING_2026-11-11.md` for verified official workflow links and licensing caveats.
