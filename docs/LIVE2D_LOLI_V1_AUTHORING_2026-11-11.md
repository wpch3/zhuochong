# Loli v1 Cubism authoring — first saved step (2026-11-11)

## Current deliverable

`characters/xiaoxun/design/loli_live2d_v1/cubism_source/` contains:

- `xiaoxun_loli_cubism_source_v1.ora` — editable OpenRaster scaffold at 848×1360.
- `layer_manifest.json` — layer IDs, intended part/group, state, source checksum, registration, and limitations.
- `reference_front_848x1360.png` — accepted flattened v1 placed at native pixel size with 48 transparent pixels above it.
- `template_preview.jpg` — visual check of that reference canvas.

The ORA contains 69 transparent placeholder drawing layers plus one 55%-opacity flattened reference. It is a practical organizer for subsequent painting, **not** completed layered art, PSD/PSB, a Cubism Editor project, MOC3, or an animation-ready/verified model. No automatic segmentation or fabricated hidden art was added. The existing concept itself remains 848×1264 and is unchanged.

## Reproduction and checks

```sh
python3 tools/make_loli_cubism_template.py
python3 tools/check_loli_cubism_template.py
```

Both scripts require Pillow. The scaffold was generated using the session's temporary Pillow environment and validated with the same environment. Validation checks ORA archive structure, canvas registration, 69 fully transparent placeholder layers, reference pixel identity, merged preview, and clear WIP/non-model status. It is a structural check, not an artistic or Cubism validation. `python3 -m py_compile tools/make_loli_cubism_template.py tools/check_loli_cubism_template.py` checks syntax.

## Official guidance verified this round

Live2D's official illustration-processing tutorial describes splitting hair, face, and body, adding hidden parts/underdrawing to avoid gaps during movement, and separating face components such as eyes, lashes, whites, brows, nose, mouth, and ears. It explicitly recommends Photoshop or CLIP STUDIO PAINT for PSD preparation and warns that other tools may not always read/write correctly. The official deformer tutorial then covers rotation/warp deformers, face tilt, hair swing, arm and body movement.

- [Illustration Processing](https://docs.live2d.com/en/cubism-editor-tutorials/psd/)
- [Adding Body Movement / Deformers](https://docs.live2d.com/en/cubism-editor-tutorials/deformer/)
- [Cubism Editor FREE vs PRO](https://www.live2d.com/en/cubism/comparison/)
- [SDK Release License](https://www.live2d.com/en/sdk/license/)

Licensing is component-specific. Cubism Editor FREE has feature and eligible-user/commercial restrictions; PRO is not universally free. Live2D SDK downloads are available for development under the applicable agreements, but publishing content using the SDK can require a publication license/payment, with stated individual/small-scale exemptions and exclusions. Cubism Core is proprietary, not an open-source component. Review current agreements for the eventual author's/user's status and target use before choosing Editor tier or distributing runtime output. This project has not added an Editor, Core, SDK binaries, or third-party assets.

## Next work

1. Turn the chosen flat concept into actual painted, occlusion-complete, editable parts. Keep the reference locked and excluded from export. Do not call the blank layer names real parts.
2. Create and visually inspect a layered PSD/PSB in an appropriate editor, preserving a source copy and meaningful layer names. Since no art editor or Cubism Editor was found on PATH/common install locations in this environment, do not claim native-app acceptance until tested in the official editor.
3. Import the real layered PSD into Cubism Editor, build meshes/deformers/parameters/physics/expressions, save the official project, export, and test the exported model in a compatible official/runtime viewer before calling it a Cubism model.
