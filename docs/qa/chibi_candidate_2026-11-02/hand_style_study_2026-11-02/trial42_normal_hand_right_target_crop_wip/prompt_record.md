# Trial 42 prompt and provenance

- Date: 2026-11-04
- Method: edit the exact viewer-right Chibi `body_full` target-hand ROI; input is `source_roi_8x_reference_wip.png`, created by a pure crop of `[462,880,507,926]` and 8× nearest-neighbour enlargement. The enlargement adds no artwork.
- Output: `trial42_right_hand_edit_wip.png` (1024×1047 RGB, opaque; checkerboard is painted pixels).

Exact generation prompt:

> Edit only the supplied cropped reference into a hand-study WIP for the viewer-right Chibi hand. Preserve the exact crop composition: keep the existing teal-and-cream striped cuff at the top/left in the same position, keep its fine dark plum outline and gentle watercolor shading, and continue the tiny relaxed hand directly below it. This is an outer/back-side view of a small hand hanging beside the thigh, not a palm-forward gesture. At the crop's target scale show at least three short, clearly separated rounded fingertip lobes pointing down; the fourth finger may naturally overlap and be partly hidden. Keep the hand compact and soft, no long wrist, no splayed fingers, no visible nails, no realistic wrinkles, no glove seam. Match the source's thin delicate linework and pale warm skin. Preserve transparent regions as transparent; do not draw a checkerboard, new background, body, face, or other clothing. Do not alter the cuff design. This image is a diagnostic concept only, not production art.

- Agent verdict: rejected. The model redrew/enlarged cuff and arm, with wrong target scale/line weight and opaque checkerboard. No fit, extraction, or production use.
