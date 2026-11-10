#!/usr/bin/env python3
"""Experimental continuous sleeve mesh for the exaggerated joint stress rig.

Not a release rig. The single weighted elbow node does not solve every joint,
body-parent transforms, or overlapping layer-order requirements. Capture and
inspect actual rendered combinations before drawing any conclusions.
"""
import argparse
import json
import shutil
import sys
from pathlib import Path
from PIL import Image
import build_chibi_joint_stress as stress


def build(output, band=45):
    if not isinstance(band, int) or not 1 <= band <= 100:
        raise ValueError('band must be an integer between 1 and 100 canvas pixels')
    out = Path(output)
    # The underlying builder validates the output and refuses existing paths.
    stress.build(out)
    try:
        path = out / 'rig.json'
        rig = json.loads(path.read_text(encoding='utf-8'))
        sides = {}
        for side in 'lr':
            group = rig['groups']
            shoulder = group[f'shoulder_{side}']['pivot']
            elbow = group[f'elbow_{side}']['pivot']
            upper = Image.open(out / f'sprites/arm_{side}.png').convert('RGBA')
            lower = Image.open(out / f'sprites/forearm_{side}.png').convert('RGBA')
            if upper.size != (480, 512) or lower.size != upper.size:
                raise ValueError('unexpected sleeve artwork dimensions')
            merged = Image.alpha_composite(upper, lower)
            box = merged.getbbox()
            if not box:
                raise ValueError('empty sleeve')
            merged.crop(box).save(out / f'sprites/arm_{side}.png')
            part = next(p for p in rig['parts'] if p['id'] == f'arm_{side}')
            if part['pos'] != [280, 458] or part['group'] != f'shoulder_{side}':
                raise ValueError('unexpected sleeve placement')
            # Upper and lower sleeves used different draw layers. The shared
            # layer is necessarily a compromise; it is not neutral-equivalent.
            part.update(group='body', pos=[280 + box[0], 458 + box[1]],
                        anchor=[0, 0], layer=21, deformer=f'sleeve_root_{side}')
            rig['parts'] = [p for p in rig['parts']
                            if p['id'] not in (f'forearm_{side}', f'elbow_under_{side}')]
            cols, rows = 8, 16
            weights = []
            for row in range(rows + 1):
                y = 458 + box[1] + (box[3] - box[1]) * row / rows
                w = max(0.0, min(1.0, (y - (elbow[1] - band)) / (2 * band)))
                weights.extend([round(w, 6)] * (cols + 1))
            rig['deformers'].extend([
                {'id': f'sleeve_root_{side}', 'pivot': shoulder},
                {'id': f'sleeve_elbow_{side}', 'pivot': elbow,
                 'parent': f'sleeve_root_{side}', 'chain_w': weights},
                {'id': f'sleeve_mesh_{side}', 'part': f'arm_{side}',
                 'cols': cols, 'rows': rows, 'parent': f'sleeve_elbow_{side}', 'points': []},
            ])
            for kind, node in (('Arm', 'root'), ('Elbow', 'elbow')):
                param = next(p for p in rig['params'] if p['id'] == f'Param{kind}{side.upper()}')
                if len(param['binds']) != 1 or param['binds'][0]['param'] != 'rot_deg':
                    raise ValueError('unexpected joint binding')
                param['binds'].append({'deformer': f'sleeve_{node}_{side}',
                                       'param': 'rot_deg', 'scale': param['binds'][0]['scale']})
            sides[side] = {'source_bbox': list(box), 'shoulder': shoulder, 'elbow': elbow,
                           'mesh': [cols, rows], 'weight_min': min(weights), 'weight_max': max(weights)}
        path.write_text(json.dumps(rig, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        report = {'purpose': 'diagnostic only', 'visual_acceptance': 'not evaluated',
                  'band_half_width': band, 'sides': sides,
                  'limitations': ['different sleeve layer order', 'deformer outside body group transform',
                                  'cuff and hand still rigid', 'not a general skinning editor']}
        (out / 'weighted_sleeve_report.json').write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        return report
    except BaseException:
        shutil.rmtree(out)
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    parser.add_argument('--band', type=int, default=45)
    args = parser.parse_args()
    try:
        print(json.dumps(build(args.output, args.band), ensure_ascii=False, indent=2))
    except (ValueError, OSError, KeyError, StopIteration) as exc:
        print(f'weighted sleeve study: {exc}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
