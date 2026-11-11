# Loli v1.1 head / face — pass 03 (semantic-separation WIP)

This iteration follows the official Cubism tutorial's separation scheme more closely. Pass 01 and pass 02 are retained as history but marked superseded; do not rig either earlier set.

## Editable stack

Open `xiaoxun_loli_v1_1_head_pass_03.ora` in an OpenRaster editor. It is a 1280×1920 stack with a flat full-body base, a grouped 11-layer face/accessory pass, and a hidden full-resolution NEW/current v1.1 reference. The separated layers are:

- `EyeWhite_L` / `EyeWhite_R` — hand-bounded, near-neutral white sclera pixels;
- `EyeBall_L` / `EyeBall_R` — source pixels within a traced iris/eyeball contour, including its pupil and highlights;
- `Eyelash_L` / `Eyelash_R` — dark pixels inside a traced upper-eyelash band;
- `Brow_L` / `Brow_R` — dark eyebrow pixels inside narrow hand-bounded regions;
- `Nose` — tiny dark nose mark;
- `Mouth_Closed` — source dark pixels of the closed-mouth strokes;
- `Whale_Clip` — ROI-restricted teal accessory selection.

Full-canvas PNG layers, `layer_manifest.json`, `head_pass_composite.png`, `layer_review_board.jpg` (isolated layers on a checkerboard), `reconstruction_diff.png`, and `SHA256SUMS.txt` accompany the ORA. ORA is editable staging material, **not PSD/PSB**.

## What changed after tutorial review

The official material-preparation tutorial separates hair into bangs/sides/back and eyes into eyelashes, eyeballs and eye whites; it explicitly requires hidden-region fill. It also describes upper/lower lips plus an inner-mouth layer, and the next tutorial covers Editor import and ArtMesh editing. Accordingly, this pass replaces the incorrect combined `Eye_L` / `Eye_R` stickers from pass 02 with 6 semantic eye layers. The facial selections are now inspected as isolated transparent cutouts, not only as a full character composite.

Static registered reassembly is pixel-identical to the alpha reference (0 RGB/alpha difference). This means only that the selected source pixels plus base pixels cover the original without a static compositing gap. It says **nothing** about whether a moving eye exposes missing art or whether a selection belongs to the intended semantic part.

## Still not ready for deformation

- In the isolated-layer review, the sclera/lash/brow masks still show small stray or antialiased pixels and include source art that is already overlapped by bangs. Hand cleanup and explicit layer ownership review remain necessary.
- The flat source has no hidden eye-white or eyelid pixels behind the iris, no closed-eye redraw, no split upper/lower lips or inside-mouth art, and no painted face underdraw behind the fringe. OpenCV inpaint on the base is only temporary approximate filler; it is not hand-painted production art.
- Bangs, side/back hair, head outline/ears, neck, torso, jacket, sleeves/cuffs, hands, skirt, legs, socks, and shoes remain fused in the flat base.
- No PSD/PSB, Cubism Editor project, ArtMeshes, deformer hierarchy, parameters/keyforms, physics, `.moc3`, `.model3.json`, or runtime test is included.

Rebuild/check from repository root:

```sh
python3 tools/build_loli_v1_1_head_pass.py
python3 tools/check_loli_v1_1_head_pass.py
```

These tests validate expected layer names, nonempty bounds, ORA structure, and exact registered still reconstruction. They do not certify semantic masks, overlap-complete art, motion readiness, or Cubism compatibility. The next proper art task is manual cleanup and hand-painted hidden-region completion in a raster editor, then review each layer while toggling/offsetting it.
