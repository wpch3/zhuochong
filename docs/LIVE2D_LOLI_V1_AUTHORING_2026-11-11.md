# Loli v1.1 Live2D authoring — current state (2026-11-11)

## Current production reference

The user selected `characters/xiaoxun/design/loli_live2d_v1/concept_front_proportion_v1_1.png` (1280×1920 RGB, white background) as the sole current basis for making the custom Live2D character. It has the approved short pleated skirt at a natural waist, untucked shirt over the skirt, and a close leg stance. Preserve it as the **NEW / current reference**.

The original flat `concept_front_keyed.png` (848×1264), `concept_front_raw_magenta.png`, and its two review JPGs remain explicitly marked **OLD / reference only**. Do not use the old v1 as the production art source. Do not white-key the new reference: it contains white clothing on a white/near-white background.

Per the user's request to discard earlier-version work, the old-version placeholder ORA, old face cutouts and algorithmic underpaint, their manifests, and their version-specific build/check scripts have been removed. The old references remain. No editable Loli production source, PSD/PSB, official Cubism project, ArtMeshes, MOC3, model3 JSON, or runtime model currently exists.

The sandbox now has a reference board at `/loli-reference-board.html`, linked from its home page, with unambiguous NEW/current and OLD/reference-only labels.

## Round 01 — transparent-background reference isolation

Created `characters/xiaoxun/design/loli_live2d_v1/authoring_v1_1/reference_v1_1_alpha_edge_connected.png`, plus light/dark reviews and `isolation_metrics.json`. This removes only near-white components connected to the image border, preserving enclosed white clothing; it is not a global white key. On visual checks the white jacket/shirt, hair, legs and both shoes remain. The derivative is still a single flat full-body raster, not semantic part separation or hidden-region redraw. Automated checks confirm 1,878,839 transparent exterior pixels, full-character bounds `(297, 57, 983, 1864)`, exact RGB preservation for opaque pixels and sample white/cream clothing pixels retained. These checks do not certify edge quality; close manual alpha cleanup remains.

Rebuild/check: `python3 tools/isolate_loli_v1_1_reference.py` and `python3 tools/check_loli_v1_1_isolation.py` (Pillow, NumPy, OpenCV). The sandbox reference board links the alpha review and dark-background edge check.

## Round 02 — first editable face/accessory pass (WIP)

Created `characters/xiaoxun/design/loli_live2d_v1/authoring_v1_1/head_pass_01/` and its OpenRaster stack `xiaoxun_loli_v1_1_head_pass_01.ora`. It is 1280×1920 with a visible flat figure base (face-local algorithmic underpaint), a seven-layer cutout group (`Whale_Clip`, `Brow_L`, `Brow_R`, `Eye_L`, `Eye_R`, `Nose`, `Mouth_Closed`), and a hidden full-reference layer. The separate full-canvas PNGs, `layer_manifest.json`, rebuild instructions and SHA-256 list are alongside it. It can be opened in an ORA-compatible editor such as Krita/GIMP; it is **not PSD/PSB**.

Selections were traced in native coordinates from the NEW v1.1 alpha reference; a limited teal ROI mask for the whale clip discards detached specks. Face features were removed from the base alpha and locally filled with OpenCV Telea, so feature layers can be placed above the reconstructed base. Static reassembly QA: 67 pixels differ by >2 RGB levels, max channel difference 41; `tools/check_loli_v1_1_head_pass.py` passes the bounded first-pass checks and ORA structure/reassembly comparison. This is only file/registration QA, **not artistic approval**. A zoomed WIP review showed some eye/brow selection edges include adjacent fringe pixels; those boundaries need manual ownership cleanup.

Scope is intentionally small and clearly unfinished: hair, face silhouette, ears/neck, torso, jacket, sleeves/hands, skirt, legs, socks and shoes remain fused in a single base. The underpaint is algorithmic, visibly approximate, and must be replaced/refined by hand before deformation. No full overlap-complete source, PSD/PSB, Cubism Editor project, ArtMeshes, `.moc3`, `.model3.json`, or runtime validation exists. See `authoring_v1_1/head_pass_01/README.md`.

## Tutorial review and Round 03 — correction of the first face pass

Reviewed the checked-in official workflow notes in `docs/LIVE2D_OFFICIAL_WORKFLOW_AND_TOOLS.md` against the official PSD-preparation and deformer tutorials and the official `Live2D/CubismNativeSamples` README/license. Key practical corrections: (1) define semantic parts and their overlap ownership before selection; (2) inspect each isolated layer in close-up, not just the full-body reconstruction; (3) hidden source pixels absent from the flat reference require hand-painted underdraw; (4) ORA is only an editable staging format, not proof of PSD/PSB or Editor import; (5) deformers cannot fix missing art. NativeSamples documents a renderer for Editor-exported models, not an authoring shortcut, and its README/license distinguishes Native Framework, proprietary Core, and sample materials.

The first head pass exposed genuine mistakes: guessed x-coordinates were wrong, fringe pixels entered brow/eye masks, and large skin-colored patches around nose/mouth created obvious blobs. Pass 01 is now explicitly marked superseded. A source-registered close-up was made and visually checked; pass 02 stores corrected eye/brow selections and small dark-pixel-only nose/mouth selections, with a full-body reassembly. The second reassembly metric is **80 pixels >2 RGB / max channel 50**, versus pass 01's 67/41; it is numerically worse and is reported honestly, not claimed as quality improvement. The face preview no longer has the large cheek blobs, but hidden eye areas and fringe ownership remain unresolved.

Current files: `authoring_v1_1/head_pass_02/xiaoxun_loli_v1_1_head_pass_02.ora`, its `README.md`, `layer_manifest.json`, and seven layer PNGs. `head_pass_01/` is historical/superseded. Automated bounds/ORA/reassembly tests pass, but the cutouts and algorithmic inpaint are not artist-approved. The head silhouette, hair, body and clothing remain flat; no hand-painted overlap completion or Cubism engineering has happened.

## Next work

1. Manually refine eyes/brows and hair-over-face ownership in a real raster editor; create continuous hand-painted underdrawing behind moved features. If no raster editor is available, install/acquire one or keep outputs explicitly WIP rather than inventing pixels by interpolation.
2. Separate head silhouette, bangs/back hair/strands, neck, jacket body/sleeves/cuffs, arms/hands, skirt, legs, socks and shoes into a proper overlap-complete source; hand-paint the hidden regions needed for motion while preserving the selected v1.1 design.
3. Save a reviewed PSD/PSB-capable source, build static reassembly/visibility/edge QA, and compare the complete neutral still to the approved reference.
4. Obtain a supported official Cubism Editor environment; verify PSD/PSB import. Then create ArtMeshes, deformer hierarchy, parameters, physics, expressions/motions; save the official project; export and run-test the actual model. Until that happens, do not claim a real Cubism project/model or runtime validation.

## Official workflow and licensing

- [Illustration Processing](https://docs.live2d.com/en/cubism-editor-tutorials/psd/) — parts and hidden overlap painting.
- [Adding Body Movement / Deformers](https://docs.live2d.com/en/cubism-editor-tutorials/deformer/)
- [Cubism Editor FREE vs PRO](https://www.live2d.com/en/cubism/comparison/)
- [SDK Release License](https://www.live2d.com/en/sdk/license/)

Licenses vary by component and user/publishing context. Editor FREE has limitations; PRO is not universally free. SDK/Core use and publishing have separate terms; Cubism Core is proprietary. Check current agreements before choosing Editor tier, integrating SDKs, or distributing runtime files. No Editor, Core, SDK, or third-party assets are bundled by this work.
