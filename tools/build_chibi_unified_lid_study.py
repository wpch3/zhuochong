#!/usr/bin/env python3
"""Unapproved experiment: continuous moving lash, rather than crossfaded lids.

Needs the isolated morph-experiment C binary. A thin line derived from the same
moving lash separates into a pain wedge; this tests topology, not finished art.
"""
import argparse
import copy
import json
import math
import shutil
import sys
from pathlib import Path
import numpy as np
from PIL import Image
import build_chibi_pupil_hold_study as pupil


def build(output, branch='thin'):
    if branch not in ('thin', 'duplicate'):
        raise ValueError('branch must be thin or duplicate')
    out = Path(output)
    pupil.build(out)
    try:
        path = out / 'rig.json'
        rig = json.loads(path.read_text(encoding='utf-8'))
        for side in 'lr':
            old = {f'lid_closed_{side}', f'lid_smile_{side}', f'lid_pain_{side}'}
            rig['parts'] = [p for p in rig['parts'] if p['id'] not in old]
            rig['deformers'] = [d for d in rig['deformers'] if d.get('part') not in old]
            lid = next(p for p in rig['parts'] if p['id'] == f'lid_{side}')
            lid['tags'] = ['eyelid', 'eye_keyform_effective_blink', 'eye_closed_morph']
            extra = copy.deepcopy(lid)
            extra['id'] = f'lid_secondary_{side}'
            extra['layer'] += 1
            if branch == 'thin':
                # The second branch is a thin centre-line derived from the SAME
                # moving lash. It starts entirely inside the primary stroke rather
                # than duplicating both lash tips and the thick coloured fill.
                image = np.asarray(Image.open(out / lid['file']).convert('RGBA'))
                h, w = image.shape[:2]
                thin = np.zeros_like(image)
                for x in range(17 if side == 'l' else 20, 84 if side == 'l' else 88):
                    a = image[:, x, 3].astype(float) / 255
                    if a.sum() < 1:
                        continue
                    y = float((np.arange(h) * a).sum() / a.sum())
                    for yy in range(max(0, int(y) - 2), min(h, int(y) + 4)):
                        alpha = max(0.0, min(1.0, 1.5 - abs(yy - y))) * a[yy]
                        thin[yy, x] = (33, 20, 33, round(255 * alpha))
                extra['file'] = f'sprites/lid_secondary_{side}.png'
                Image.fromarray(thin).save(out / extra['file'])
            rig['parts'].append(extra)
            original = next(d for d in rig['deformers'] if d['id'] == f'mesh_lid_{side}')
            clone = copy.deepcopy(original)
            clone['id'] = f'mesh_lid_secondary_{side}'
            clone['part'] = extra['id']
            rig['deformers'].append(clone)
            for ix, part in enumerate((lid, extra)):
                for kind in ('smile', 'pain'):
                    points = []
                    for row in range(5):
                        for col in range(9):
                            t = col / 8 if side == 'l' else 1 - col / 8
                            if kind == 'smile':
                                dy = -5 * math.sin(math.pi * t)
                            else:
                                # Split toward the outer edge; both meet on the inside.
                                dy = ((-3 if branch == 'thin' else -7) if ix == 0 else 7) * (1 - t)
                            points.append({'c': col, 'r': row, 'dy': round(dy, 4)})
                    rig['deformers'].append({'id': f'mesh_{part["id"]}_{kind}', 'part': part['id'],
                        'cols': 8, 'rows': 4, 'param': f'ParamEye{side.upper()}{kind.title()}',
                        'keys': [{'v': 0, 'points': []}, {'v': 1, 'points': points}]})
        path.write_text(json.dumps(rig, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        report = {'visual_acceptance': 'not evaluated', 'branch': branch, 'requires': 'build/zhuochong_eye_morph_experiment',
                  'limits': ['overlapping strokes may darken edges', 'wedge art is provisional',
                             'thin branch derived from moving lash', 'no production rig changes']}
        (out / 'unified_lid_report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        return report
    except BaseException:
        shutil.rmtree(out)
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    parser.add_argument('--branch', choices=('thin', 'duplicate'), default='thin')
    args = parser.parse_args()
    try:
        print(json.dumps(build(args.output, args.branch), ensure_ascii=False, indent=2))
    except (ValueError, OSError, KeyError, StopIteration) as exc:
        print(f'unified lid study: {exc}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
