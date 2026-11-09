#!/usr/bin/env python3
"""Experimental anchored finger meshes, retaining the existing separated art.

A linear tip-length gesture rather than a rigid pivot rotation. This is a
bounded diagnostic, not a completed hand illustration or a fist rig.
"""
import argparse
import json
import math
import shutil
import sys
from pathlib import Path
from PIL import Image
import build_chibi_extended as base

# Tip positions in the 480x512 hand source; right art is mirrored about x=230.
TIPS = {'little': (77, 231), 'ring': (72, 231), 'middle': (69, 229), 'index': (66, 225)}


def build(output, distance=2.5):
    if not 0 < distance <= 4:
        raise ValueError('distance must be > 0 and <= 4')
    out = Path(output)
    base.build(out)
    try:
        path = out / 'rig.json'
        rig = json.loads(path.read_text(encoding='utf-8'))
        pieces = {}
        for side in 'lr':
            for name, tip in TIPS.items():
                ident = f'finger_{side}_{name}'
                part = next(p for p in rig['parts'] if p['id'] == ident)
                group = rig['groups'][ident]
                param = next(p for p in rig['params'] if p['id'] == f'ParamFinger{side.upper()}{name.title()}')
                if part['pos'] != [280, 458] or part['anchor'] != [0, 0] or part['group'] != ident:
                    raise ValueError('unexpected finger placement')
                if len(param['binds']) != 1 or param['binds'][0].get('group') != ident:
                    raise ValueError('unexpected finger binding')
                source = out / part['file']
                image = Image.open(source).convert('RGBA')
                box = image.getbbox()
                if image.size != (480, 512) or box is None:
                    raise ValueError('unexpected finger texture')
                image.crop(box).save(source)
                part['pos'] = [280 + box[0], 458 + box[1]]
                param['binds'] = []
                pivot = group['pivot']
                tip_x = tip[0] if side == 'l' else 460 - tip[0]
                vx, vy = 280 + tip_x - pivot[0], 458 + tip[1] - pivot[1]
                length = math.hypot(vx, vy)
                if length < 1:
                    raise ValueError('invalid finger axis')
                ux, uy = vx / length, vy / length
                cols = rows = 8
                points = []
                for row in range(rows + 1):
                    for col in range(cols + 1):
                        x = part['pos'][0] + (box[2] - box[0]) * col / cols
                        y = part['pos'][1] + (box[3] - box[1]) * row / rows
                        t = max(0.0, min(1.0, ((x - pivot[0]) * ux + (y - pivot[1]) * uy) / length))
                        t = t * t * (3 - 2 * t)
                        points.append({'c': col, 'r': row, 'dx': round(distance * ux * t, 5),
                                       'dy': round(distance * uy * t, 5)})
                neg = [dict(p, dx=-p['dx'], dy=-p['dy']) for p in points]
                rig['deformers'].append({'id': f'mesh_{ident}_anchored', 'part': ident, 'cols': cols, 'rows': rows,
                    'param': param['id'], 'keys': [{'v': -1, 'points': neg}, {'v': 0, 'points': []},
                                                   {'v': 1, 'points': points}]})
                pieces[ident] = {'bbox': list(box), 'axis': [round(ux, 5), round(uy, 5)],
                                 'pivot': pivot, 'length': round(length, 5)}
        path.write_text(json.dumps(rig, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        report = {'visual_acceptance': 'not evaluated', 'distance': distance, 'pieces': pieces,
                  'limitations': ['original contours and layer order unchanged', 'length gesture is not a fan or fist',
                                  'thumb remains rigid', 'overlap still needs visual inspection']}
        (out / 'finger_mesh_report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        return report
    except BaseException:
        shutil.rmtree(out)
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    parser.add_argument('--distance', type=float, default=2.5)
    args = parser.parse_args()
    try:
        print(json.dumps(build(args.output, args.distance), ensure_ascii=False, indent=2))
    except (ValueError, OSError, KeyError, StopIteration) as exc:
        print(f'finger mesh study: {exc}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
