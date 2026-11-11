# Loli v1.1 Live2D authoring — current state (2026-11-11)

## Current production reference

The user selected `characters/xiaoxun/design/loli_live2d_v1/concept_front_proportion_v1_1.png` (1280×1920 RGB, white background) as the sole current basis for making the custom Live2D character. It has the approved short pleated skirt at a natural waist, untucked shirt over the skirt, and a close leg stance. Preserve it as the **NEW / current reference**.

The original flat `concept_front_keyed.png` (848×1264), `concept_front_raw_magenta.png`, and its two review JPGs remain explicitly marked **OLD / reference only**. Do not use the old v1 as the production art source. Do not white-key the new reference: it contains white clothing on a white/near-white background.

Per the user's request to discard earlier-version work, the old-version placeholder ORA, old face cutouts and algorithmic underpaint, their manifests, and their version-specific build/check scripts have been removed. The old references remain. No editable Loli production source, PSD/PSB, official Cubism project, ArtMeshes, MOC3, model3 JSON, or runtime model currently exists.

The sandbox now has a reference board at `/loli-reference-board.html`, linked from its home page, with unambiguous NEW/current and OLD/reference-only labels.

## Next work

1. Start a **new** editable art-source pipeline from the selected v1.1 reference. Keep the white jacket/shirt whites intact while creating transparency; manually redraw/segment edges instead of applying a white color key.
2. Create real separated, overlap-complete parts and hand-painted underdraw for face, eyes, brows, mouth, hair strands/whale clip, neck, jacket body/sleeves/cuffs, arms/hands, skirt, legs, socks, and shoes. Preserve the approved body proportions and neutral close stance. The reference itself is flat art and is never a model ArtMesh.
3. Save source layers and manifests in a new v1.1-specific directory, build a static reassembly/visibility/edge QA board, and verify the complete still matches the approved reference before progressing.
4. Obtain a supported official Cubism Editor environment; verify that it imports the layered PSD/PSB. Then create ArtMeshes, deformer hierarchy, parameters, physics, expressions/motions; save the official project; export and run-test the actual model. Until that happens, do not claim a real Cubism project/model or runtime validation.

## Official workflow and licensing

- [Illustration Processing](https://docs.live2d.com/en/cubism-editor-tutorials/psd/) — parts and hidden overlap painting.
- [Adding Body Movement / Deformers](https://docs.live2d.com/en/cubism-editor-tutorials/deformer/)
- [Cubism Editor FREE vs PRO](https://www.live2d.com/en/cubism/comparison/)
- [SDK Release License](https://www.live2d.com/en/sdk/license/)

Licenses vary by component and user/publishing context. Editor FREE has limitations; PRO is not universally free. SDK/Core use and publishing have separate terms; Cubism Core is proprietary. Check current agreements before choosing Editor tier, integrating SDKs, or distributing runtime files. No Editor, Core, SDK, or third-party assets are bundled by this work.
