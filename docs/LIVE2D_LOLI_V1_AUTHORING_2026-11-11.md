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

## Official web tutorial review and Round 04 — semantic eye split

This turn used web search on official Live2D pages, then read the returned official tutorial content rather than relying on the previous summary. `docs/LIVE2D_OFFICIAL_WORKFLOW_AND_TOOLS.md` now records the concrete specifications and links. Key findings: the PSD preparation tutorial calls for hair split into bangs/sides/back with the hidden regions painted in; eyes separated into eyelashes, eyeball and whites; upper/lower lips and an inner-mouth piece; skin-colored fill behind hair/around mouth; and neck/body/arms/hand/skirt/left-right legs as distinct areas. The import tutorial requires meshes to enclose the texture and describes hand refinement for brows/lashes/mouth. PSD import requirements include RGB, 8-bit/channel, sRGB, unique layer names, no layer masks, and line/fill/effects merged per source part. The facial expression tutorial demonstrates eyelash open/close, sclera clipping, eyebrow deformation, and mouth opening/closing; the deformer tutorial describes rotation/warp hierarchy and keyed movement. Direct links are in the workflow doc.

Round 01 had guessed facial coordinates, mixed fringe into eye/brow layers and cut broad skin patches. Round 02 corrected some coordinates and removed cheek patches but kept each whole eye as a single sticker, still contrary to the official split. Both are preserved as historical, explicitly superseded ORA files. In this turn, Round 03 (current) divides both eyes into `EyeWhite`, `EyeBall`, and `Eyelash` layers, narrows brows to the primary stroke, and retains nose/closed-mouth/whale clip as separate layers. It has an 11-part face group, 13-layer ORA stack, full-canvas PNGs, SHA manifest and rebuild/check scripts under `authoring_v1_1/head_pass_03/`.

Static registered reconstruction has 0 pixel difference because the masks plus base still account for all original source pixels. **That is not proof of proper semantic ownership or motion readiness.** I inspected the isolated layer review board; some masks still contain antialiased fringe/line fragments and the reference supplies no hidden eye-white, closed-eye, inner-mouth, or skin-under-bangs artwork. Base underpaint remains OpenCV interpolation, not hand-painted art. No PSD/PSB or Cubism model was created. The container has no Krita/GIMP executable, so hand-painted work must wait until an actual raster editor is available; do not disguise that gap with algorithmic fill.

## Official source archive, gap audit and Round 05 — garment-region start

Saved a durable official source register at `docs/LIVE2D_TUTORIAL_RESEARCH_2026-11-11.md`, with tutorial links, paraphrased workflow notes, current resource inventory, blockers and a staged plan. It records that tutorials 1–6, import PSD requirements, FREE/PRO, sample data/license boundaries, export, and supported Editor OS were checked. Official Editor system requirements list Windows/macOS, not this Linux sandbox; neither Krita nor GIMP nor Wine is installed. We must not describe interpolation as hand-painted underdraw.

Round 05 starts a narrowly scoped garment cutout in `authoring_v1_1/authoring_pass_04/`: the pass03 face stack plus `JacketSleeve_Teal_L/R`, two ROI-clipped source-visible teal fabric regions. The white cuff stripes/cuffs/hands are not part of these regions; hidden arm overlaps and entire rest of body remain flat. A 13-part/15-layer ORA and isolated-layer board are included. Static reassembly is 0 pixel difference (coverage only, not artistic or motion QA). The sleeves are an exact registered visible-color split, not complete sleeves or rig-ready artwork. The tutorial registry and gap audit identify the next exact unblock: a supported raster paint app for manual edge repair and hidden-region painting, followed by an officially supported Cubism Editor host for actual import/model validation.

## Next work

1. Manually refine eyes/brows, sleeve boundaries and hair-over-face ownership in a real raster editor; create continuous hand-painted underdrawing behind moved features. If no raster editor is available, acquire/install one or keep outputs explicitly WIP rather than inventing pixels by interpolation.
2. Separate head silhouette, bangs/back hair/strands, neck, jacket body/sleeves/cuffs, arms/hands, skirt, legs, socks and shoes into a proper overlap-complete source; hand-paint the hidden regions needed for motion while preserving the selected v1.1 design.
3. Save a reviewed PSD/PSB-capable source, build static reassembly/visibility/edge QA, and compare the complete neutral still to the approved reference.
4. Obtain a supported official Cubism Editor environment; verify PSD/PSB import. Then create ArtMeshes, deformer hierarchy, parameters, physics, expressions/motions; save the official project; export and run-test the actual model. Until that happens, do not claim a real Cubism project/model or runtime validation.

## Official workflow and licensing

- [Illustration Processing](https://docs.live2d.com/en/cubism-editor-tutorials/psd/) — parts and hidden overlap painting.
- [Adding Body Movement / Deformers](https://docs.live2d.com/en/cubism-editor-tutorials/deformer/)
- [Cubism Editor FREE vs PRO](https://www.live2d.com/en/cubism/comparison/)
- [SDK Release License](https://www.live2d.com/en/sdk/license/)

Licenses vary by component and user/publishing context. Editor FREE has limitations; PRO is not universally free. SDK/Core use and publishing have separate terms; Cubism Core is proprietary. Check current agreements before choosing Editor tier, integrating SDKs, or distributing runtime files. No Editor, Core, SDK, or third-party assets are bundled by this work.
