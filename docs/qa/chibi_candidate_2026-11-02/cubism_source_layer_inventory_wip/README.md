# Chibi Cubism source-layer inventory (WIP; not a Cubism model)

**Purpose:** record the current Chibi `rig.json` image references as a starting inventory for a future Editor PSD. This is not a PSD, `.cmo3`, `.moc3`, model approval, or proof the current cutouts contain complete overlap.

## Verified current tree facts

- `rig.json` references **49 parts**, all 49 referenced image files currently exist. Groups: `arm_l` 1, `arm_r` 1, `chest` 7, `foot_l` 2, `foot_r` 2, `head` 34, `leg_l` 1, `leg_r` 1.
- Existing rig metadata contains 43 parameter definitions, 26 deformers, 19 `physics` records and 5 `physics2` records. These are **zrig data, not Cubism Editor objects**.
- Canvas `848×1360`, origin `[424, 1360]`. `body_full.png` is 567×1292 RGBA; it is a rendered source-derived composite, not a layered authoring file.
- **Identity anomaly:** this path is `forms/chibi`, and `form_art.json` references Chibi design sheet, but the current `rig.json` reports id `小寻_teen`. Resolve before authoring/packaging a Cubism project.
- There are no independent approved normal/mitten hand parts, hidden-wrist continuations, cuff front/back layers, or complete approved layered PSD. The current arm layers are only `seg_arm_l` and `seg_arm_r`.

## Proposed use (future editor work)

- Treat each verified source layer as a possible ArtMesh input only after the actual full-body source is reconstructed with hidden overlap closed. Preserve the listed source pixel SHA/positions as provenance, not as an automatic editor import manifest.
- Do not equate zrig `layer` integers with Cubism draw order. Review occlusion, masks, mesh edges and cuff overlap in Cubism Editor.
- Re-author Cubism parameters/keyforms, warp/rotation deformers and physics in Editor. The current 43 parameters and zrig deformation data are references only; they cannot be loaded as Cubism objects.
- Required pre-editor input: a complete overlap-closed PSD with separate left/right normal fingers and mitten, under-cuff wrist continuation, and explicit cuff-front/back or equivalent overlap.
- Required true-model completion: save `.cmo3`, export `.moc3` + `.model3.json`/textures, and inspect in official Viewer. Core/SDK use remains a separately licensed/runtime decision.

## Full inventory

| zrig order | part id | group | source file | size | alpha bbox | SHA-256 |
|---:|---|---|---|---:|---|---|
| 30 | `acc_tail_cat_relaxed` | `chest` | `characters/xiaoxun/forms/chibi/sprites/acc_tail_relaxed@2x.png` | 252×820 | `[7, 27, 246, 792]` | `91c62f3a9338…` |
| 31 | `acc_tail_cat_up` | `chest` | `characters/xiaoxun/forms/chibi/sprites/acc_tail_up@2x.png` | 228×960 | `[0, 2, 228, 927]` | `07665025e75d…` |
| 32 | `acc_tail_cat_puff` | `chest` | `characters/xiaoxun/forms/chibi/sprites/acc_tail_puff@2x.png` | 362×860 | `[0, 30, 362, 831]` | `7b1a5bf8649d…` |
| 33 | `acc_tail_cat_tuck` | `chest` | `characters/xiaoxun/forms/chibi/sprites/acc_tail_tuck@2x.png` | 254×808 | `[6, 0, 248, 781]` | `87fdec634e82…` |
| 50 | `skirt_lining` | `chest` | `characters/xiaoxun/forms/chibi/sprites/skirt_lining.png` | 312×98 | `[0, 0, 312, 98]` | `297cbfd8e500…` |
| 57 | `acc_hair_pony` | `head` | `characters/xiaoxun/forms/chibi/sprites/hair_pony_back@2x.png` | 756×1708 | `[0, 61, 756, 1659]` | `a3065e2ca435…` |
| 58 | `acc_hair_long` | `head` | `characters/xiaoxun/forms/chibi/sprites/hair_long_back@2x.png` | 882×2192 | `[0, 2, 882, 2192]` | `a657f436ef69…` |
| 60 | `seg_leg_l` | `leg_l` | `characters/xiaoxun/forms/chibi/sprites/seg_leg_l.png` | 149×307 | `[0, 0, 149, 307]` | `e7d6ce9fd96a…` |
| 61 | `seg_leg_r` | `leg_r` | `characters/xiaoxun/forms/chibi/sprites/seg_leg_r.png` | 171×305 | `[0, 0, 171, 305]` | `a04af4cfea11…` |
| 62 | `seg_foot_l` | `foot_l` | `characters/xiaoxun/forms/chibi/sprites/seg_foot_l.png` | 101×140 | `[1, 0, 101, 140]` | `0624e52e8bab…` |
| 63 | `seg_foot_r` | `foot_r` | `characters/xiaoxun/forms/chibi/sprites/seg_foot_r.png` | 127×140 | `[0, 0, 126, 140]` | `c4c6cc50e008…` |
| 64 | `seg_foot_l_tip` | `foot_l` | `characters/xiaoxun/forms/chibi/sprites/seg_foot_l_tip.png` | 101×170 | `[1, 0, 101, 170]` | `fe281434a25e…` |
| 65 | `seg_foot_r_tip` | `foot_r` | `characters/xiaoxun/forms/chibi/sprites/seg_foot_r_tip.png` | 127×170 | `[0, 0, 126, 170]` | `d196706f2a5f…` |
| 97 | `skirt_main` | `chest` | `characters/xiaoxun/forms/chibi/sprites/skirt_main.png` | 320×183 | `[0, 0, 320, 183]` | `3c36f974b3a3…` |
| 100 | `seg_torso` | `chest` | `characters/xiaoxun/forms/chibi/sprites/seg_torso.png` | 326×399 | `[0, 0, 326, 399]` | `95f822976934…` |
| 140 | `seg_arm_l` | `arm_l` | `characters/xiaoxun/forms/chibi/sprites/seg_arm_l.png` | 100×230 | `[0, 0, 99, 230]` | `a736fd252c6b…` |
| 141 | `seg_arm_r` | `arm_r` | `characters/xiaoxun/forms/chibi/sprites/seg_arm_r.png` | 100×230 | `[1, 0, 100, 230]` | `c0777d86baba…` |
| 160 | `acc_hair_twin_l` | `head` | `characters/xiaoxun/forms/chibi/sprites/hair_twin_l@2x.png` | 442×1360 | `[0, 48, 442, 1348]` | `a0c9a8dfaefa…` |
| 161 | `acc_hair_twin_r` | `head` | `characters/xiaoxun/forms/chibi/sprites/hair_twin_r@2x.png` | 442×1360 | `[0, 48, 442, 1348]` | `8b240c5f7e5e…` |
| 165 | `acc_ear_cat_l` | `head` | `characters/xiaoxun/forms/chibi/sprites/acc_ear_l@2x.png` | 382×452 | `[12, 14, 370, 438]` | `e7d5c5de33ae…` |
| 166 | `acc_ear_cat_r` | `head` | `characters/xiaoxun/forms/chibi/sprites/acc_ear_r@2x.png` | 382×452 | `[12, 14, 370, 438]` | `257154200c6e…` |
| 180 | `seg_head` | `head` | `characters/xiaoxun/forms/chibi/sprites/seg_head.png` | 567×644 | `[0, 105, 567, 643]` | `786bfae5d814…` |
| 190 | `hair_ahoge` | `head` | `characters/xiaoxun/forms/chibi/sprites/hair_ahoge.png` | 121×117 | `[0, 0, 121, 117]` | `74fd14fc40ac…` |
| 203 | `blush_l` | `head` | `characters/xiaoxun/forms/chibi/sprites/blush_l.png` | 40×22 | `[1, 1, 39, 21]` | `cdc6dde75c75…` |
| 204 | `blush_r` | `head` | `characters/xiaoxun/forms/chibi/sprites/blush_r.png` | 40×22 | `[1, 1, 39, 21]` | `cdc6dde75c75…` |
| 205 | `mouth_mask` | `head` | `characters/xiaoxun/forms/chibi/sprites/mouth_mask.png` | 45×24 | `[0, 0, 45, 24]` | `be0d799bc558…` |
| 206 | `mouth_cavity` | `head` | `characters/xiaoxun/forms/chibi/sprites/mouth_cavity.png` | 45×24 | `[0, 0, 45, 24]` | `7f309ff9b415…` |
| 210 | `mouth_open` | `head` | `characters/xiaoxun/forms/chibi/sprites/mouth_open.png` | 51×16 | `[0, 0, 51, 16]` | `b7427e942d76…` |
| 211 | `eye_l_socket` | `head` | `characters/xiaoxun/forms/chibi/sprites/eye_l_socket.png` | 264×151 | `[111, 0, 231, 151]` | `b50eb7b16eec…` |
| 212 | `eye_l_base` | `head` | `characters/xiaoxun/forms/chibi/sprites/eye_l_base.png` | 264×151 | `[0, 0, 264, 151]` | `31aaa8a89d2c…` |
| 213 | `eye_l_wide` | `head` | `characters/xiaoxun/forms/chibi/sprites/eye_l_wide.png` | 296×181 | `[3, 0, 296, 181]` | `ab481642bf20…` |
| 214 | `eye_l_ball` | `head` | `characters/xiaoxun/forms/chibi/sprites/eye_l_ball.png` | 77×77 | `[2, 1, 76, 75]` | `071791b8c415…` |
| 217 | `eye_hl_l` | `head` | `characters/xiaoxun/forms/chibi/sprites/eye_hl_l.png` | 13×13 | `[1, 1, 12, 12]` | `78a6167f408d…` |
| 218 | `eye_l_lash` | `head` | `characters/xiaoxun/forms/chibi/sprites/eye_l_lash.png` | 264×151 | `[117, 8, 223, 96]` | `dbe96b35e7f3…` |
| 219 | `eye_l_closed` | `head` | `characters/xiaoxun/forms/chibi/sprites/eye_l_closed.png` | 155×155 | `[23, 23, 132, 132]` | `b635291738c7…` |
| 220 | `eye_hl_star_l` | `head` | `characters/xiaoxun/forms/chibi/sprites/eye_hl_star_l.png` | 20×20 | `[1, 1, 19, 19]` | `a47e988117d3…` |
| 221 | `eye_l_smile` | `head` | `characters/xiaoxun/forms/chibi/sprites/eye_l_smile.png` | 155×155 | `[23, 23, 132, 132]` | `48f8cf011e73…` |
| 222 | `eye_l_pain` | `head` | `characters/xiaoxun/forms/chibi/sprites/eye_l_pain.png` | 163×159 | `[27, 25, 136, 134]` | `cc57aa5411d8…` |
| 223 | `eye_r_socket` | `head` | `characters/xiaoxun/forms/chibi/sprites/eye_r_socket.png` | 265×151 | `[33, 0, 147, 151]` | `435eea70fb3c…` |
| 224 | `eye_r_base` | `head` | `characters/xiaoxun/forms/chibi/sprites/eye_r_base.png` | 265×151 | `[0, 0, 265, 151]` | `e038bdc44f1e…` |
| 225 | `eye_r_wide` | `head` | `characters/xiaoxun/forms/chibi/sprites/eye_r_wide.png` | 297×181 | `[0, 0, 285, 181]` | `76200f9e5062…` |
| 226 | `eye_r_ball` | `head` | `characters/xiaoxun/forms/chibi/sprites/eye_r_ball.png` | 77×77 | `[1, 1, 76, 76]` | `25b10e672fe3…` |
| 229 | `eye_hl_r` | `head` | `characters/xiaoxun/forms/chibi/sprites/eye_hl_r.png` | 13×13 | `[1, 1, 12, 12]` | `78a6167f408d…` |
| 230 | `eye_r_lash` | `head` | `characters/xiaoxun/forms/chibi/sprites/eye_r_lash.png` | 265×151 | `[38, 0, 146, 94]` | `b9571a3de6e7…` |
| 231 | `eye_r_closed` | `head` | `characters/xiaoxun/forms/chibi/sprites/eye_r_closed.png` | 155×155 | `[23, 23, 132, 132]` | `9906fd116e05…` |
| 232 | `eye_hl_star_r` | `head` | `characters/xiaoxun/forms/chibi/sprites/eye_hl_star_r.png` | 20×20 | `[1, 1, 19, 19]` | `a47e988117d3…` |
| 233 | `eye_r_smile` | `head` | `characters/xiaoxun/forms/chibi/sprites/eye_r_smile.png` | 155×155 | `[23, 23, 132, 132]` | `fe4de667b495…` |
| 234 | `eye_r_pain` | `head` | `characters/xiaoxun/forms/chibi/sprites/eye_r_pain.png` | 163×159 | `[27, 25, 136, 134]` | `12a287072051…` |
| 252 | `acc_hood_up` | `head` | `characters/xiaoxun/forms/chibi/sprites/acc_hood_up@2x.png` | 1480×1880 | `[48, 59, 1430, 1820]` | `779a4e547382…` |
