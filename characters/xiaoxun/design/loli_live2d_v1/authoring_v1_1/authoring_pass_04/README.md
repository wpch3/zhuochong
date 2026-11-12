# Loli v1.1 authoring pass 04 — first visible garment-region cutouts (WIP)

This is a new, editable 1280×1920 OpenRaster stack based only on the selected v1.1 reference. It carries the pass03 semantic face layers forward and adds two source-visible teal sleeve-color-region layers.

## Deliverable

Open `xiaoxun_loli_v1_1_authoring_pass_04.ora` in an OpenRaster-compatible raster editor. It has 13 source-pixel cutouts plus a flat base and a hidden NEW/current reference layer:

- pass03 face/accessory pieces: left/right eye whites, eyeballs and upper lashes; brows; nose; closed-mouth strokes; whale clip;
- `JacketSleeve_Teal_L` and `JacketSleeve_Teal_R`: teal fabric-color selections from manually traced sleeve regions, cut from the same source image.

See `layer_review_board.jpg` for isolated transparent layers and `head_pass_composite.png` for the full static reassembly. PNG layers, source/manifest, static diff and SHA-256 list are included.

Rebuild/check:

```sh
python3 tools/build_loli_v1_1_head_pass.py --with-sleeves
python3 tools/check_loli_v1_1_head_pass.py --pass04
```

## Scope limits

The new sleeve layers are **visible teal fabric regions, not complete rig-ready sleeves**. The white cuff stripes, cuffs, hands, upper-arm overlap behind the jacket, and hidden fabric behind torso/skin remain on the flat base. The color/ROI selection also needs close edge cleanup. No hidden sleeve/arm underdraw is painted; any OpenCV base fill is approximate interpolation. Do not rotate/deform these sleeve pixels as production art.

The full static reassembly check reports 0 pixel difference. This only confirms the original registered pixels are represented in the base and visible cutout layers. It does not prove part ownership, fill hidden by other parts, or moving-edge quality. The base is still a single flat figure outside the selected face/sleeve areas. No finished body/garment layer set, PSD/PSB, official Editor import, `.cmo3`, `.moc3` or runtime test is present.

Pass04 advances the visible source-layer inventory, but the next real art gate is still manual cleanup and hand-painted overlap-complete art in an actual raster editor. The sandbox currently has no Krita/GIMP executable; official Cubism Editor requirements list Windows/macOS, not the Linux authoring container.
