# Loli v1.1 authoring pass 05 — lower-body visible splits (WIP)

Per the agreed order, this continues the complete editable illustration/source-layer stage; it does **not** create PSD/PSB or Cubism output early. The pass builds from pass04 and adds source-visible skirt, left/right leg skin, socks and shoes.

## Editable delivery

Open `xiaoxun_loli_v1_1_authoring_pass_05.ora` in an OpenRaster editor. It is a 1280×1920 stack with 20 source-visible cutout layers, a flat full-body base with approximate inpaint beneath selected source areas, and the hidden NEW/current v1.1 reference.

New lower-body parts:

- `Skirt`
- `Leg_Skin_L`, `Leg_Skin_R`
- `Sock_L`, `Sock_R`
- `Shoe_L`, `Shoe_R`

The earlier 13 parts from pass04 (two teal sleeve-color regions and face/accessory parts) are retained. `layer_review_board.jpg` shows each isolated layer over a checkerboard; `authoring_pass_05_composite.png` is the whole-character reassembly; all layer PNGs, manifest and SHA list are included.

Rebuild and check:

```sh
python3 tools/build_loli_v1_1_lower_body_pass.py
python3 tools/check_loli_v1_1_lower_body_pass.py
```

## Scope and remaining work

The new masks separate only **pixels visible in the selected still**. The skirt and shoe regions use native-coordinate silhouette masks; legs are silhouette-bounded visible source regions, socks use native-coordinate contours. This is not yet a complete overlap-ready lower body: thighs hidden by the skirt and feet/ankles hidden inside shoes have no hand-painted extension; the masks need line-edge/overlap inspection in a paint editor.

The current base fill under the masks is algorithmic OpenCV interpolation, not hand painting. Hair, face outline, neck, jacket body, shirt, cuffs, hands and upper limbs still include large flat sections. Eye whites hidden behind the eyeballs, blink-closed art, mouth interior/visemes and all garment/body hidden overlap remain missing. There are no parameters, meshes, deformers, physics, motion, PSD/PSB, `.cmo3`, `.moc3`, `.model3.json` or runtime validation.

Static reconstruction is 0 pixel difference because the layer masks plus base still account for the original visible pixels. This is a source-registration check only. Do not treat it as art acceptance, motion QA or Cubism readiness. Pass05 is editable source WIP, not the final completed character master.
