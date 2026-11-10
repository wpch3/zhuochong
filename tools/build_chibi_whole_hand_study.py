#!/usr/bin/env python3
"""Flatten each hand into a shared continuous texture and use local mesh fields.

Exploratory alternative: five Gaussian tip fields sum on one 16x16 mesh.
No per-finger occlusion or physically plausible curl is implied.
"""
import argparse
import json
import math
import shutil
import sys
from pathlib import Path
from PIL import Image
import build_chibi_extended as base

TIPS = {'little': (77, 231), 'ring': (72, 231), 'middle': (69, 229),
        'index': (66, 225), 'thumb': (98, 227)}


def build(output, distance=2.0, sigma=3.5, padding=0):
    if not 0 < distance <= 4 or not 1 <= sigma <= 8 or not isinstance(padding, int) or not 0 <= padding <= 4:
        raise ValueError('distance must be in (0,4], sigma in [1,8], padding in 0..4')
    out = Path(output)
    base.build(out)
    try:
        path = out / 'rig.json'
        rig = json.loads(path.read_text(encoding='utf-8'))
        summary = {}
        for side in 'lr':
            hand = next(p for p in rig['parts'] if p['id'] == f'hand_{side}')
            parts = [next(p for p in rig['parts'] if p['id'] == f'finger_{side}_{name}') for name in TIPS]
            if any(p['pos'] != [280, 458] or p['anchor'] != [0, 0] for p in parts + [hand]):
                raise ValueError('unexpected hand placement')
            merged = Image.new('RGBA', (480, 512))
            for part in sorted(parts + [hand], key=lambda p: p['layer']):
                src = Image.open(out / part['file']).convert('RGBA')
                if src.size != merged.size:
                    raise ValueError('unexpected hand sprite size')
                merged.alpha_composite(src)
            box = merged.getbbox()
            if not box:
                raise ValueError('empty hand')
            box = (max(0, box[0]-padding), max(0, box[1]-padding),
                   min(480, box[2]+padding), min(512, box[3]+padding))
            merged.crop(box).save(out / f'sprites/whole_hand_{side}.png')
            hand.update(file=f'sprites/whole_hand_{side}.png', pos=[280 + box[0], 458 + box[1]])
            rig['parts'] = [p for p in rig['parts'] if p not in parts]
            for name, tip in TIPS.items():
                param = next(p for p in rig['params'] if p['id'] == f'ParamFinger{side.upper()}{name.title()}')
                if len(param['binds']) != 1 or param['binds'][0].get('group') != f'finger_{side}_{name}':
                    raise ValueError('unexpected finger binding')
                param['binds'] = []
                pivot = rig['groups'][f'finger_{side}_{name}']['pivot']
                tx, ty = 280 + (tip[0] if side == 'l' else 460 - tip[0]), 458 + tip[1]
                vx, vy = tx - pivot[0], ty - pivot[1]
                length = math.hypot(vx, vy)
                if length < 1:
                    raise ValueError('invalid finger axis')
                # Tangential tip motion; avoid mirrored sign reversals that
                # would otherwise make hands swing in opposite local directions.
                ux, uy = -vy / length, vx / length
                pts = []
                for row in range(17):
                    for col in range(17):
                        x = hand['pos'][0] + (box[2] - box[0]) * col / 16
                        y = hand['pos'][1] + (box[3] - box[1]) * row / 16
                        w = math.exp(-((x-tx)**2 + (y-ty)**2) / (2*sigma*sigma))
                        pts.append({'c': col, 'r': row, 'dx': round(ux*distance*w, 5),
                                    'dy': round(uy*distance*w, 5)})
                negative = [dict(p, dx=-p['dx'], dy=-p['dy']) for p in pts]
                rig['deformers'].append({'id': f'mesh_whole_{side}_{name}', 'part': hand['id'],
                    'cols': 16, 'rows': 16, 'param': param['id'],
                    'keys': [{'v': -1, 'points': negative}, {'v': 0, 'points': []},
                             {'v': 1, 'points': pts}]})
            summary[side] = {'bbox': list(box), 'mesh': [16, 16]}
        path.write_text(json.dumps(rig, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        report = {'visual_acceptance': 'not evaluated', 'distance': distance, 'sigma': sigma, 'padding': padding, 'sides': summary,
                  'limitations': ['flattened hand cannot independently reorder fingers', 'tip fields overlap',
                                  'no depth/curl', 'rasterization changes neutral']}
        (out / 'whole_hand_report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        return report
    except BaseException:
        shutil.rmtree(out)
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    parser.add_argument('--distance', type=float, default=2.0)
    parser.add_argument('--sigma', type=float, default=3.5)
    args = parser.parse_args()
    try:
        print(json.dumps(build(args.output, args.distance, args.sigma), ensure_ascii=False, indent=2))
    except (ValueError, OSError, KeyError, StopIteration) as exc:
        print(f'whole hand study: {exc}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
