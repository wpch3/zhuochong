#!/usr/bin/env python3
"""Build an isolated, deliberately limited C-rig facial study from registered artwork.

Requires Pillow and numpy. It does NOT overwrite the existing chibi form. The
body is a single flat image: this is a facial-animation study, not a finished
model or a substitute for layered source art. off_chain: writes only to the
isolated experiments/chibi_face_study directory, never production sprites.
"""
from pathlib import Path
import json
import numpy as np
from PIL import Image, ImageFilter

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / 'characters/xiaoxun/design/chibi'
OUT = ROOT / 'experiments/chibi_face_study'


def rgb(path):
    return np.asarray(Image.open(path).convert('RGB'), dtype=np.int16)


def feature(source, underpaint, box, name):
    x0, y0, x1, y1 = box
    a = source[y0:y1, x0:x1]
    b = underpaint[y0:y1, x0:x1]
    # Difference only within an explicitly registered face ROI.  Grow slightly
    # over anti-aliased edges, then feather; this is not hidden-part recovery.
    diff = np.max(np.abs(a - b), axis=2)
    mask = Image.fromarray(np.where(diff > 18, 255, 0).astype('uint8'))
    mask = mask.filter(ImageFilter.MaxFilter(5)).filter(ImageFilter.GaussianBlur(0.7))
    rgba = np.dstack((a.astype('uint8'), np.asarray(mask)))
    rgba[rgba[:, :, 3] == 0, :3] = 0
    Image.fromarray(rgba).save(OUT / 'sprites' / (name + '.png'))
    return {'id': name, 'file': 'sprites/' + name + '.png', 'group': 'figure',
            'pos': [x0, y0], 'anchor': [0, 0], 'layer': 10}


def main():
    (OUT / 'sprites').mkdir(parents=True, exist_ok=True)
    original = rgb(SRC / 'production_concept_2026-11-06.png')
    base = rgb(SRC / 'rebuild_2026-11-06/face_underpaint.png')
    closed = rgb(SRC / 'rebuild_2026-11-06/eyes_closed.png')
    speaking = rgb(SRC / 'rebuild_2026-11-06/mouth_open.png')
    if any(im.shape != original.shape for im in (base, closed, speaking)) or original.shape != (1042, 1008, 3):
        raise ValueError('registered inputs must all be 1008x1042 RGB images')
    # Distance from the sampled background, rather than a magenta hue test:
    # dark purple outline/loose strands can have a similar hue to the key.
    # The background itself varies by less than 10 RGB units in the corners.
    bg = np.median(base[:100, :100].reshape(-1, 3), axis=0)
    distance = np.linalg.norm(base.astype(float) - bg, axis=2)
    alpha_f = np.clip((distance - 10) / 50, 0, 1)
    r, g, b = (base[:, :, i].astype(float) for i in range(3))
    # Suppress saturated *bright* pink spill while preserving the dark ink
    # of the fine hair silhouette, which also has a purple hue.
    pink = np.clip((np.minimum(r - g, b - g) - 35) / 50, 0, 1)
    pink = np.where((r > 130) & (b > 90), pink, 0)
    alpha = np.rint(alpha_f * (1 - pink) * 255).astype('uint8')
    # Copy the nearest solid foreground color into the soft contour. Direct
    # mathematical unmixing was unstable on dark ink against this nonuniform
    # generated background and produced a visible green fringe. Color bleed
    # only changes partially transparent pixels, not the solid artwork.
    colors = base.astype('uint8').copy()
    known = alpha >= 250
    for _ in range(12):
        old_known, old_colors = known.copy(), colors.copy()
        for dy, dx in ((-1, 0), (1, 0), (0, -1), (0, 1),
                       (-1, -1), (-1, 1), (1, -1), (1, 1)):
            neighbor = np.roll(old_known, (dy, dx), (0, 1))
            if dy > 0: neighbor[:dy, :] = False
            if dy < 0: neighbor[dy:, :] = False
            if dx > 0: neighbor[:, :dx] = False
            if dx < 0: neighbor[:, dx:] = False
            take = (alpha > 0) & ~known & neighbor
            colors[take] = np.roll(old_colors, (dy, dx), (0, 1))[take]
            known[take] = True
    alpha[(alpha > 0) & ~known] = 0
    rgba = np.dstack((colors, alpha))
    rgba[alpha == 0, :3] = 0
    Image.fromarray(rgba).save(OUT / 'sprites/base.png')
    parts = [{'id': 'base', 'file': 'sprites/base.png', 'group': 'figure',
              'layer': 0, 'pos': [0, 0], 'anchor': [0, 0]}]
    for side, box in [('l', (357, 318, 477, 450)), ('r', (531, 318, 651, 450))]:
        eye = feature(original, base, box, 'eye_' + side + '_open')
        eye.update(tags=['eye_open'], eye_side=side)
        parts.append(eye)
        eye = feature(closed, base, box, 'eye_' + side + '_closed')
        eye.update(tags=['eye_closed'], eye_side=side, layer=11)
        parts.append(eye)
    parts.append(feature(original, base, (492, 420, 517, 448), 'nose'))
    parts.append(feature(original, base, (475, 443, 538, 488), 'mouth_rest'))
    p = feature(speaking, base, (475, 443, 538, 488), 'mouth_speak')
    p['layer'] = 11
    parts.append(p)
    rig = {
        'schema_version': '1.0', 'id': 'xiaoxun_chibi_face_study', 'name': '小寻 · 面部试作',
        'canvas': {'w': 1008, 'h': 1042}, 'origin': [504, 1042], 'ground_line': 1000,
        'groups': {'root': {'pivot': [504, 1042], 'parent': ''},
                   'figure': {'pivot': [504, 1000], 'parent': 'root'}},
        'blink': {'enabled': True, 'closing_s': 0.10, 'closed_s': 0.08,
                  'opening_s': 0.15, 'interval_min_s': 2.5, 'interval_max_s': 6.0},
        'parts': parts,
        'params': [{'id': 'ParamMouthOpenY', 'label': '张嘴', 'min': 0, 'max': 1,
                    'default': 0, 'binds': []}],
        'xfades': [{'id': 'mouth', 'param': 'ParamMouthOpenY', 'in': [0, 1],
                    'from': 'mouth_rest', 'to': 'mouth_speak'}],
        'actions': [
            {'id': 'idle', 'title': '待机', 'priority': 0, 'loop': True, 'channels': []},
            {'id': 'sway', 'title': '整体摇摆（试作）', 'priority': 2, 'loop': True,
             'channels': [{'target': 'figure', 'param': 'rot_deg', 'wave': 'sine', 'amp': 1.5, 'freq': 0.2}]},
            {'id': 'talk', 'title': '说话（试作）', 'priority': 2, 'loop': True,
             'channels': [{'target': 'ParamMouthOpenY', 'param': 'value', 'wave': 'flap', 'amp': 1, 'freq': 2}]},
        ],
        'regions': [{'id': 'head', 'rect': [260, 80, 750, 500], 'cursor': 'hand', 'action': 'idle'},
                    {'id': 'body', 'rect': [325, 500, 680, 780], 'cursor': 'hand', 'action': 'idle'}],
    }
    (OUT / 'rig.json').write_text(json.dumps(rig, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print('Built experimental face study in', OUT)


if __name__ == '__main__':
    main()
