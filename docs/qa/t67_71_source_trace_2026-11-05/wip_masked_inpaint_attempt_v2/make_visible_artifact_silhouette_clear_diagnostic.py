#!/usr/bin/env python3
"""Isolated diagnostic: clear only manually traced visible cuff/hand silhouettes; never production."""
from pathlib import Path
import json
import numpy as np
from PIL import Image, ImageDraw

BASE = Path(__file__).resolve().parent
ROOT = Path(__file__).resolve().parents[4]
SRC = ROOT / 'characters/xiaoxun/forms/teen/sprites/hair_hood_long@2x.png'
POLY = BASE / 'manual_artifact_polygons_v2.json'
MASK_OUT = BASE / '72_visible_artifact_silhouette_candidate_mask.png'
BOARD_OUT = BASE / '73_visible_artifact_silhouette_clear_diagnostic.png'
REPORT_OUT = BASE / '74_visible_artifact_silhouette_clear_diagnostic_metrics.json'
BOXES = {'left': (51, 849, 396, 1368), 'right': (736, 849, 1081, 1368)}
SCALE = 4

src = Image.open(SRC).convert('RGBA')
a = np.asarray(src).copy()
polygons = json.loads(POLY.read_text(encoding='utf-8'))['polygons']
fullmask = np.zeros(a.shape[:2], dtype=np.uint8)
side_counts = {}
for side, (x0, y0, x1, y1) in BOXES.items():
    # Supersampling makes the object boundary antialiased; polygons were broadened to include
    # the visibly identified cuff bands, palm, fingers, and their outline, but may include hair.
    hi = Image.new('L', ((x1-x0)*SCALE, (y1-y0)*SCALE), 0)
    draw = ImageDraw.Draw(hi)
    for poly in polygons[side]:
        draw.polygon([(int(x*SCALE), int(y*SCALE)) for x, y in poly], fill=255)
    local = hi.resize((x1-x0, y1-y0), Image.Resampling.LANCZOS)
    lm = np.asarray(local, dtype=np.uint8)
    fullmask[y0:y1, x0:x1] = np.maximum(fullmask[y0:y1, x0:x1], lm)
    side_counts[side] = {
        'silhouette_mask_pixels_gt_127': int((lm > 127).sum()),
        'silhouette_mask_pixels_gt_0': int((lm > 0).sum()),
        'source_nonzero_alpha_under_mask_gt_127': int(((a[y0:y1, x0:x1, 3] > 0) & (lm > 127)).sum()),
    }

# This is a diagnostic-only alpha clear. Fractional boundary coverage retains antialiasing.
out = a.copy()
out[:, :, 3] = (a[:, :, 3].astype(np.uint16) * (255 - fullmask.astype(np.uint16)) // 255).astype(np.uint8)
mask_img = Image.fromarray(fullmask, 'L')
mask_img.save(MASK_OUT)
clear = Image.fromarray(out, 'RGBA')
# Invariant: pixels outside both reviewed silhouette boxes are byte-identical.
allowed = np.zeros(a.shape[:2], dtype=bool)
for x0, y0, x1, y1 in BOXES.values():
    allowed[y0:y1, x0:x1] = True
changed = np.any(np.asarray(clear) != a, axis=2)
if np.any(changed & ~allowed):
    raise SystemExit('diagnostic unexpectedly changed pixels outside the two reviewed ROIs')

# Native source / silhouette overlay / clear-only on matte, with both sides kept separate.
thumb_w, thumb_h = 690, 1038
board = Image.new('RGB', (thumb_w*3 + 48, (thumb_h+58)*2), (244, 242, 247))
d = ImageDraw.Draw(board)
for row, (side, box) in enumerate(BOXES.items()):
    x0, y0, x1, y1 = box
    original = src.crop(box)
    localmask = Image.fromarray(fullmask[y0:y1, x0:x1], 'L')
    matte = Image.new('RGBA', original.size, (239, 239, 244, 255)); matte.alpha_composite(original)
    tint = Image.new('RGBA', original.size, (255, 35, 25, 0)); tint.putalpha(localmask.point(lambda p: p * 110 // 255))
    overlay = Image.alpha_composite(matte, tint).convert('RGB')
    clipped = clear.crop(box)
    clear_matte = Image.new('RGBA', clipped.size, (239, 239, 244, 255)); clear_matte.alpha_composite(clipped)
    panels = [matte.convert('RGB'), overlay, clear_matte.convert('RGB')]
    labels = ['source on matte', 'red = full visible-object silhouette candidate', 'clear-only diagnostic; no backfill']
    for col, (im, label) in enumerate(zip(panels, labels)):
        im = im.resize((thumb_w, thumb_h), Image.Resampling.LANCZOS)
        x, y = 12 + col*(thumb_w+12), 42 + row*(thumb_h+58)
        board.paste(im, (x, y)); d.text((x+3, y-24), f'{side}: {label}', fill=(30,25,40))
board.save(BOARD_OUT)
report = {
    'task': 'T67.71',
    'status': 'isolated diagnostic only; not production and not accepted repair',
    'source': str(SRC.relative_to(ROOT)),
    'mask_basis': 'manual_artifact_polygons_v2 full visible cuff-and-hand silhouette; includes reviewed margins and may overlap legitimate hair',
    'intent': 'remove only source-visible cuff/hand foreign object silhouette for review; hidden hair shape remains unknown; no fill or neighbor sampling',
    'edge_handling': '4x supersampled polygon rasterization with fractional alpha clearance at the boundary',
    'changed_pixels_outside_reviewed_boxes': int((changed & ~allowed).sum()),
    'side_counts': side_counts,
    'outputs': [str(MASK_OUT.relative_to(ROOT)), str(BOARD_OUT.relative_to(ROOT))],
    'warning': 'This does not establish what was behind the visible object and may erase adjacent legitimate hair where the manual silhouette is broad. Do not use as production input before visual approval and separate backfill inference.'
}
REPORT_OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
print(json.dumps(report, ensure_ascii=False, indent=2))
