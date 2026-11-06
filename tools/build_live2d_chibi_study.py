#!/usr/bin/env python3
"""Create an isolated Chibi puppet study; off_chain, never writes production sprites.

The generated art is flat, not layered source truth. This builds a limited
prototype from registered redraws; hidden edges and animation require review.
Requires Pillow and numpy.
"""
import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / 'characters/xiaoxun/design/live2d_chibi_2026-11-06'
OUT = ROOT / 'experiments/live2d_chibi_short'


def rgb(name):
    data = np.asarray(Image.open(SRC / name).convert('RGB'), dtype=np.int16)
    if data.shape != (1024, 1024, 3):
        raise ValueError(f'{name}: expected registered 1024x1024 art')
    return data


def mask_polygon(points, blur=1.0):
    im = Image.new('L', (1024, 1024), 0)
    ImageDraw.Draw(im).polygon(points, fill=255)
    if blur:
        im = im.filter(ImageFilter.GaussianBlur(blur))
    return np.asarray(im, dtype=float) / 255


def replace_area(base, source, points):
    m = mask_polygon(points, 2)[..., None]
    return np.rint(base * (1 - m) + source * m).astype(np.int16)


def alpha_key(data):
    # This generated source has a flat bright magenta background. Use hue and
    # luminance together to avoid removing dark purple lines as background.
    r, g, b = [data[..., i].astype(float) for i in range(3)]
    pink = np.clip((np.minimum(r-g, b-g)-35) / 40, 0, 1)
    pink = np.where((r > 70) & (b > 65) & (g < 85), pink, 0)
    alpha = np.rint((1-pink)*255).astype(np.uint8)
    colors = data.astype(np.uint8).copy()
    # Bleed opaque foreground colours over semitransparent contour to reduce
    # magenta contamination. This is not a guarantee of a production matte.
    known = alpha >= 250
    for _ in range(10):
        old, old_colors = known.copy(), colors.copy()
        for dy, dx in ((-1, 0), (1, 0), (0, -1), (0, 1), (-1, -1), (-1, 1), (1, -1), (1, 1)):
            n = np.roll(old, (dy, dx), (0, 1))
            if dy > 0: n[:dy, :] = False
            if dy < 0: n[dy:, :] = False
            if dx > 0: n[:, :dx] = False
            if dx < 0: n[:, dx:] = False
            take = (alpha > 0) & ~known & n
            colors[take] = np.roll(old_colors, (dy, dx), (0, 1))[take]
            known[take] = True
    alpha[(alpha > 0) & ~known] = 0
    result = np.dstack((colors, alpha))
    result[alpha == 0, :3] = 0
    return result


def save_part(name, rgba, box, group, layer, **fields):
    x0, y0, x1, y1 = box
    im = rgba[y0:y1, x0:x1].copy()
    Image.fromarray(im.astype(np.uint8)).save(OUT / 'sprites' / (name + '.png'))
    return {'id': name, 'file': 'sprites/' + name + '.png', 'group': group,
            'pos': [x0, y0], 'anchor': [0, 0], 'layer': layer, **fields}


def diff_feature(source, blank, box):
    x0, y0, x1, y1 = box
    d = np.max(np.abs(source[y0:y1, x0:x1] - blank[y0:y1, x0:x1]), axis=2)
    mask = Image.fromarray(np.where(d > 20, 255, 0).astype('uint8'))
    mask = mask.filter(ImageFilter.MaxFilter(5)).filter(ImageFilter.GaussianBlur(0.7))
    result = np.zeros((1024, 1024, 4), dtype=np.uint8)
    result[y0:y1, x0:x1, :3] = source[y0:y1, x0:x1].astype('uint8')
    result[y0:y1, x0:x1, 3] = np.asarray(mask)
    result[result[..., 3] == 0, :3] = 0
    return result


def differential_cut(source, hidden, box, polygon):
    # An original visible region, NOT recovered hidden art. Diff mask suppresses
    # the underlying character; alpha key removes the magenta background.
    diff = np.max(np.abs(source - hidden), axis=2)
    mask = Image.fromarray(np.where(diff > 24, 255, 0).astype('uint8'))
    mask = mask.filter(ImageFilter.MaxFilter(5)).filter(ImageFilter.GaussianBlur(0.7))
    cut = alpha_key(source)
    a = np.asarray(mask, dtype=float) / 255 * mask_polygon(polygon, 0.6)
    cut[..., 3] = np.rint(cut[..., 3] * a).astype(np.uint8)
    cut[cut[..., 3] == 0, :3] = 0
    return cut


def main():
    (OUT / 'sprites').mkdir(parents=True, exist_ok=True)
    original, blank, closed, mouth, noears, notail = [rgb(n) for n in
        ('short_base.png', 'face_blank.png', 'eyes_closed.png', 'mouth_open.png', 'no_ears.png', 'no_tail.png')]
    lpoly = [(316, 75), (440, 75), (449, 203), (397, 243), (311, 225)]
    rpoly = [(584, 75), (711, 75), (713, 225), (626, 243), (575, 203)]
    tpoly = [(578, 686), (757, 686), (757, 847), (572, 847)]
    base = replace_area(blank, noears, lpoly)
    base = replace_area(base, noears, rpoly)
    base = replace_area(base, notail, tpoly)
    keyed = alpha_key(base)
    parts = []
    tail = differential_cut(original, notail, (570, 675, 760, 850), tpoly)
    parts.append(save_part('tail', tail, (570, 675, 760, 850), 'tail', 0))
    parts.append(save_part('body', keyed, (280, 458, 760, 970), 'body', 10))
    for side, poly, box in [('l', lpoly, (310, 75, 450, 245)), ('r', rpoly, (575, 75, 715, 245))]:
        ear = differential_cut(original, noears, box, poly)
        parts.append(save_part('ear_'+side, ear, box, 'ear_'+side, 20))
    parts.append(save_part('head', keyed, (290, 35, 730, 466), 'head', 30))
    for side, box in [('l', (390, 286, 490, 400)), ('r', (525, 286, 630, 400))]:
        parts.append(save_part('eye_'+side+'_open', diff_feature(original, blank, box), box,
                               'head', 40, tags=['eye_open'], eye_side=side))
        parts.append(save_part('eye_'+side+'_closed', diff_feature(closed, blank, box), box,
                               'head', 41, tags=['eye_closed'], eye_side=side))
    nose_box = (497, 379, 525, 407)
    mouth_box = (480, 405, 542, 445)
    parts.append(save_part('nose', diff_feature(original, blank, nose_box), nose_box, 'head', 40))
    parts.append(save_part('mouth_rest', diff_feature(original, blank, mouth_box), mouth_box, 'head', 40))
    parts.append(save_part('mouth_speak', diff_feature(mouth, blank, mouth_box), mouth_box, 'head', 41))
    rig = {
        'schema_version': '1.0', 'id': 'xiaoxun_live2d_chibi_study', 'name': '小寻 · Chibi 骨骼试装',
        'canvas': {'w': 1024, 'h': 1024}, 'origin': [512, 1024], 'ground_line': 946,
        'groups': {'root': {'pivot': [512, 946], 'parent': ''},
                   'body': {'pivot': [512, 706], 'parent': 'root'},
                   'tail': {'pivot': [595, 720], 'parent': 'body'},
                   'head': {'pivot': [512, 457], 'parent': 'body'},
                   'ear_l': {'pivot': [382, 170], 'parent': 'head'},
                   'ear_r': {'pivot': [642, 170], 'parent': 'head'}},
        'blink': {'enabled': True, 'closing_s': .1, 'closed_s': .08, 'opening_s': .15,
                  'interval_min_s': 2.5, 'interval_max_s': 6},
        'parts': parts,
        'params': [{'id': 'ParamMouthOpenY', 'label': '张嘴', 'min': 0, 'max': 1, 'default': 0, 'binds': []}],
        'param_groups': [{'name': 'EyeBlink', 'ids': ['ParamEyeLOpen', 'ParamEyeROpen']},
                         {'name': 'LipSync', 'ids': ['ParamMouthOpenY']}],
        'xfades': [{'id': 'mouth', 'param': 'ParamMouthOpenY', 'in': [0, 1], 'from': 'mouth_rest', 'to': 'mouth_speak'}],
        'actions': [
            {'id': 'idle', 'title': '待机', 'priority': 0, 'loop': True, 'channels': []},
            {'id': 'sway', 'title': '摇摆试装', 'priority': 2, 'loop': True, 'channels': [
                {'target': 'body', 'param': 'rot_deg', 'wave': 'sine', 'amp': 1, 'freq': .18},
                {'target': 'head', 'param': 'rot_deg', 'wave': 'sine', 'amp': 1.5, 'freq': .18, 'phase': .08},
                {'target': 'ear_l', 'param': 'rot_deg', 'wave': 'sine', 'amp': 2, 'freq': .18, 'phase': .12},
                {'target': 'ear_r', 'param': 'rot_deg', 'wave': 'sine', 'amp': -2, 'freq': .18, 'phase': .12},
                {'target': 'tail', 'param': 'rot_deg', 'wave': 'sine', 'amp': 3, 'freq': .18, 'phase': .2}]},
            {'id': 'head_test', 'title': '头部试装', 'priority': 2, 'loop': True,
             'channels': [{'target': 'head', 'param': 'rot_deg', 'wave': 'sine', 'amp': 3, 'freq': .25}]},
            {'id': 'ear_test', 'title': '猫耳试装', 'priority': 2, 'loop': True, 'channels': [
                {'target': 'ear_l', 'param': 'rot_deg', 'wave': 'sine', 'amp': 4, 'freq': .25},
                {'target': 'ear_r', 'param': 'rot_deg', 'wave': 'sine', 'amp': -4, 'freq': .25}]},
            {'id': 'tail_test', 'title': '尾巴试装', 'priority': 2, 'loop': True,
             'channels': [{'target': 'tail', 'param': 'rot_deg', 'wave': 'sine', 'amp': 5, 'freq': .25}]},
            {'id': 'talk', 'title': '说话试装', 'priority': 2, 'loop': True,
             'channels': [{'target': 'ParamMouthOpenY', 'param': 'value', 'wave': 'flap', 'amp': 1, 'freq': 2}]},
        ],
        'regions': [{'id': 'head', 'rect': [310, 90, 710, 465], 'cursor': 'hand', 'action': 'idle'},
                    {'id': 'body', 'rect': [340, 465, 680, 720], 'cursor': 'hand', 'action': 'idle'}],
    }
    (OUT / 'rig.json').write_text(json.dumps(rig, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print('Built experimental live2d-style chibi study at', OUT)


if __name__ == '__main__':
    main()
