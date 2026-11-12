# Live2D Cubism tutorial research and Loli v1.1 production gap audit

**Research date:** 2026-11-11 (official Live2D web pages searched and reviewed)  
**Purpose:** save a durable source register and turn the official workflow into the next production gates for Xiaoxun Loli v1.1. Do not commit official tutorial PSDs/sample models into this project without checking the specific material license and attribution requirements.

## Official source register

### Illustration preparation and parts

- **[1. Illustration Processing](https://docs.live2d.com/en/cubism-editor-tutorials/psd/)** — Official Basic Tutorial. It describes splitting hair into bangs/sides/back and painting the hidden portions that movement can expose. For the face it calls for distinct eyelashes, eyeballs and eye whites; white-of-eye art must exist under the iris for eye movement. Mouth preparation separates upper/lower lips and inside-mouth material, with skin-colored coverage so the mouth closes cleanly. The face contour is filled with skin behind the bangs. Neck, torso, arms/hands, skirt and left/right legs are separate construction areas. The page provides learning PSD/sample-model downloads; those are licensed sample materials, not Loli assets.
- **[Notes on PSD Creation](https://docs.live2d.com/en/cubism-editor-manual/precautions-for-psd-data/)** — Import PSD must use PSD/RGB/8-bit/channel/sRGB, avoid duplicate layer names and layer masks, and combine line art, fills, clipping/effects for each imported part into its own layer.
- **[How to create PSDs to import](https://docs.live2d.com/en/cubism-editor-manual/reimport-psd/)** — Keep the material-separation/source file separate from the merged import file; combine groups for import and use distinct layer names.

### Editor modeling and movement

- **[2. Preparing to Move the Illustration](https://docs.live2d.com/en/cubism-editor-tutorials/import/)** — PSD import produces ArtMeshes; an initial mesh needs refinement and must fully enclose its texture. The official examples recommend finer/manual mesh treatment for eyelashes, brows and mouth.
- **[3. Adding Facial Expressions](https://docs.live2d.com/en/cubism-editor-tutorials/expression/)** — Demonstrates eye-open/close, eyelash deformation, clipping the eyeball to the sclera, eyebrow parameterization and mouth open/close with an inside-mouth part.
- **[4. Adding Body Movement](https://docs.live2d.com/en/cubism-editor-tutorials/deformer/)** — Covers Rotation Deformer/Angle Z, Warp Deformer hair swing, arm/body movement, and parameter keyforms.
- **[5. Adding XY Facial Movement](https://docs.live2d.com/en/cubism-editor-tutorials/xy/)** — Uses Warp Deformers for Angle X/Y and adds diagonal shapes; adjust individual parts while considering perspective and inspect interpolated motion, not only endpoints.
- **[6. Creating Animations](https://docs.live2d.com/en/cubism-editor-tutorials/animator/)** — Modeling and animation are separate modes; the model is loaded into Animator for timeline/keyframe/graph editing.
- **[Data for Embedded Use](https://docs.live2d.com/en/cubism-editor-manual/export-moc3-motion3-files/)** — The official Editor exports `.moc3`, `.model3.json`, texture atlases and optional physics/motion-related files; this is not reproducible by renaming a PNG or the project's `rig.json`.

### Tool/system/license constraints

- **[Cubism Editor system requirements](https://www.live2d.com/en/cubism/download/spec/)** — Current requirements list Windows and macOS, not Linux. The sandbox for this project is Linux x86_64. No official Editor binary was found here.
- **[FREE vs PRO comparison](https://www.live2d.com/en/cubism/comparison/)** — FREE has limits including ArtMeshes, motion parameters, parts and export-related features; the required tier depends on the planned model complexity and delivery. Do not assume FREE is unlimited.
- **[SDK Release License](https://www.live2d.com/en/sdk/license/)** and the [Cubism Core manual](https://docs.live2d.com/en/cubism-sdk-manual/cubism-core/) — SDK/Core terms are distinct from Editor use; Cubism Core is proprietary. Recheck applicable terms before runtime integration or publication.
- **[Official tutorial top page](https://docs.live2d.com/en/cubism-editor-tutorials/top/)** also links downloadable example PSDs and sample models. They are learning references only; check and comply with each sample's Free Material License Agreement. They are not sources to merge into Xiaoxun's production assets.

## Production gap audit for Xiaoxun v1.1

### Available now

- Sole approved base: `characters/xiaoxun/design/loli_live2d_v1/concept_front_proportion_v1_1.png`, 1280×1920 flattened RGB concept.
- A border-connected-alpha version that preserves white fabric, plus original/alpha QA.
- `authoring_v1_1/head_pass_03/`: an ORA WIP with 11 visible face/accessory cutouts (left/right sclera, eyeball, eyelashes, brows; nose; closed-mouth ink; whale clip), a flat full-body base, and a hidden approved reference. `authoring_v1_1/authoring_pass_04/` adds two visible teal sleeve-color regions. `authoring_v1_1/authoring_pass_05/` adds skirt, left/right visible legs, socks and shoes, for 20 source-visible layers. `authoring_v1_1/authoring_pass_06/` carries those forward and adds jacket-body panels, front shirt, visible neck, cuffs and hands plus flat estimated overlap fills (32 ORA stack parts total, 28 source-visible and 4 estimated hidden-fill layers). `authoring_v1_1/authoring_pass_07/` adds ROI/color-cut hair pieces (bangs, left/right sides, back/crown, ahoge) and an estimated flat face fill under hair (38 total stack parts). These remain cutout/underfill WIPs; pass01/02 are superseded.
- Tutorial notes, generation/check scripts, isolated-layer boards and static reassembly QA. These are not hand-drawn complete production art.

### Blocking gaps before production-ready illustration

1. **No paint/edit app in the sandbox:** checked `krita`, `gimp`, Inkscape, Photoshop and Wine executables; none are installed. The available official Cubism Editor requirements do not list Linux. This blocks responsible hand-painted cleanup and actual Editor validation here.
2. **No layered master source:** only the flat selected front view exists. No editable PSD/PSB, line-art/fill grouping or original unmerged source to recover covered content from.
3. **No hand-painted hidden art:** restore face/eye whites under irises and lids; closed-eye forms; mouth upper/lower/inner parts and skin coverage; skin/head behind bangs; hair strands/back head behind front hair; neck under hair/collar; garment/arm/hand/skirt/leg overlaps needed by motion.
4. **No whole-body semantic part set:** hair (bangs/sides/back/cowlick), head/ears, neck/torso, sleeves/arms/hands, jacket body/cuffs, shirt, skirt, left/right legs, socks/shoes still share the flat base. User-approved proportions and clothing colors must remain fixed.
5. **No PSD import proof:** final per-part merged layers, unique names, RGB 8-bit sRGB and no layer masks have not been produced/imported in Cubism Editor.
6. **No model build or dynamic QA:** no ArtMeshes, tuned meshes, clipping IDs, deformer hierarchy, parameter keyforms (blink, mouth, Angle XYZ, body), physics, expressions/motions, `.cmo3`, `.moc3`, `.model3.json`, Viewer/SDK runtime validation or visual motion matrix.
7. **No Editor/license environment decision:** need a supported Windows/macOS Cubism Editor host and decide FREE/PRO from the intended model complexity. Runtime SDK/Core licensing is a separate later gate.

## Next production sequence

1. Keep the head pass labelled WIP; do not use automated inpaint as finished underdraw. Continue only bounded visible-region source-pixel separations until a real paint app is available.
2. Use a proper raster editor to manually repair each face layer and paint hidden regions, then make a separate full-body material-separation master. Work from the v1.1 reference only.
3. Export a Cubism-compatible PSD import copy with one uniquely named merged layer per part, RGB/8-bit/sRGB, no masks; preserve the richer editable source separately.
4. On a supported Editor host, import and visually check each ArtMesh/texture, refine eye/lash/mouth meshes, make blink/face/body parameters and test intermediate states and overlap failures.
5. Add physics, expressions and motions only after mesh/keyform quality passes. Save the real `.cmo3`, export required runtime files through the Editor and test the actual model in the intended Viewer/SDK.

## Current production checkpoint

The latest deliverable is an **ORA hair/source-cutout WIP** in `authoring_v1_1/authoring_pass_07/`, with 38 stack parts (pass06's 28 source-visible/4 estimated-fill pieces plus five hair cuts and one estimated face fill). The source now has initial ROI/color selections for bangs, sides, crown/back and ahoge, but the edge board still shows fragments and the fringe/eye boundary needs manual cleanup. The skin fill under hair is flat and incomplete. This is not complete overlap-ready illustration art, PSD/PSB, Editor project or Cubism model. Zero static reconstruction difference validates only source-pixel reassembly, not semantic ownership, edges, hidden art or movement. The official tutorial requires hidden hair portions and face outline under hair to be painted in; pass07 does not meet that requirement. Genuine brush cleanup still needs a raster paint editor, and Cubism Editor needs a supported host later.
