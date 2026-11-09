#!/usr/bin/env python3
"""Layer-preserving, group-parent-mirrored weighted sleeve stress study.

Two textures share one continuous deformation and retain their original draw
layers. Group transforms are duplicated into deformer nodes for THIS fixed rig,
whose root is static. Not a general group-space deformer implementation.
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
        raise ValueError('band must be an integer in 1..100')
    out = Path(output)
    stress.build(out)
    try:
        path = out / 'rig.json'
        rig = json.loads(path.read_text(encoding='utf-8'))
        groups = rig['groups']
        if groups['root'].get('parent') or groups['body'].get('parent') != 'root':
            raise ValueError('unexpected group hierarchy')
        mirrored_groups = {'root', 'body', 'shoulder_l', 'shoulder_r', 'elbow_l', 'elbow_r'}
        if rig.get('physics') or rig.get('ambient'):
            raise ValueError('unreviewed physics/ambient can affect mirrored transforms')
        if mirrored_groups.intersection(rig.get('look', {}).get('groups', {})):
            raise ValueError('look-driven mirrored group is not copied')
        for chain in rig.get('physics2', []):
            if chain.get('driver') and chain.get('part') in ('arm_l', 'arm_r', 'forearm_l', 'forearm_r'):
                raise ValueError('physics driver depends on sleeve part placement')
            if any(o.get('part') in ('arm_l', 'arm_r', 'forearm_l', 'forearm_r') for o in chain.get('outputs', [])):
                raise ValueError('direct physics output on split sleeve is not mirrored')
        sleeve_parts = {'arm_l', 'arm_r', 'forearm_l', 'forearm_r'}
        for action in rig['actions']:
            if any(c.get('target') in mirrored_groups | sleeve_parts for c in action.get('channels', [])):
                raise ValueError('direct group or sleeve action is not mirrored')
            if action.get('part_overrides') or action.get('overrides'):
                raise ValueError('unreviewed action part overrides')
        if any(b.get('group') == 'root' for p in rig['params'] for b in p.get('binds', [])):
            raise ValueError('root is not static')
        if any(b.get('part') in sleeve_parts for p in rig['params'] for b in p.get('binds', [])):
            raise ValueError('direct sleeve part binding is not mirrored')
        summary = {}
        for side in 'lr':
            names = {'body': f'sleeve_body_{side}', f'shoulder_{side}': f'sleeve_shoulder_{side}',
                     f'elbow_{side}': f'sleeve_elbow_{side}'}
            if groups[f'shoulder_{side}'].get('parent') != 'body' or groups[f'elbow_{side}'].get('parent') != f'shoulder_{side}':
                raise ValueError('unexpected sleeve group hierarchy')
            for group in names:
                if groups[group].get('inherit', 'full') != 'full' or groups[group].get('bend_follow'):
                    raise ValueError('unsupported group inheritance')
            upper_path = out / f'sprites/arm_{side}.png'
            lower_path = out / f'sprites/forearm_{side}.png'
            upper = Image.open(upper_path).convert('RGBA')
            lower = Image.open(lower_path).convert('RGBA')
            if upper.size != (480, 512) or lower.size != upper.size:
                raise ValueError('unexpected sleeve textures')
            box = Image.alpha_composite(upper, lower).getbbox()
            if not box:
                raise ValueError('empty sleeve')
            upper.crop(box).save(upper_path)
            lower.crop(box).save(lower_path)
            upper_part = next(p for p in rig['parts'] if p['id'] == f'arm_{side}')
            lower_part = next(p for p in rig['parts'] if p['id'] == f'forearm_{side}')
            if (upper_part['group'], lower_part['group'], upper_part['pos'], lower_part['pos']) != (
                    f'shoulder_{side}', f'elbow_{side}', [280, 458], [280, 458]):
                raise ValueError('unexpected sleeve placement')
            for part in (upper_part, lower_part):
                part.update(group='root', pos=[280 + box[0], 458 + box[1]],
                            anchor=[0, 0], deformer=names['body'])
            rig['parts'] = [p for p in rig['parts'] if p['id'] != f'elbow_under_{side}']
            cols, rows = 8, 16
            elbow = groups[f'elbow_{side}']['pivot']
            weights = []
            for row in range(rows + 1):
                y = 458 + box[1] + (box[3] - box[1]) * row / rows
                w = max(0.0, min(1.0, (y - (elbow[1] - band)) / (2 * band)))
                weights.extend([round(w, 6)] * (cols + 1))
            rig['deformers'].extend([
                {'id': names['body'], 'pivot': groups['body']['pivot']},
                {'id': names[f'shoulder_{side}'], 'pivot': groups[f'shoulder_{side}']['pivot'], 'parent': names['body']},
                {'id': names[f'elbow_{side}'], 'pivot': elbow, 'parent': names[f'shoulder_{side}'], 'chain_w': weights},
            ])
            for part in (upper_part, lower_part):
                rig['deformers'].append({'id': f'mesh_{part["id"]}_weighted', 'part': part['id'],
                                         'cols': cols, 'rows': rows, 'parent': names[f'elbow_{side}'], 'points': []})
            bindings = []
            for param in rig['params']:
                mirrored = []
                for b in param.get('binds', []):
                    if b.get('group') in names:
                        if b.get('param') not in ('dx', 'dy', 'sx', 'sy', 'rot_deg'):
                            raise ValueError('unsupported group channel')
                        clone = dict(b)
                        clone['deformer'] = names[clone.pop('group')]
                        mirrored.append(clone)
                        bindings.append([param['id'], b['group'], b['param']])
                param['binds'].extend(mirrored)
            summary[side] = {'bbox': list(box), 'layers': [upper_part['layer'], lower_part['layer']],
                             'mirrored_bindings': bindings, 'mesh': [cols, rows]}
        path.write_text(json.dumps(rig, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        report = {'purpose': 'isolated fixed-rig diagnostic', 'visual_acceptance': 'not evaluated',
                  'band_half_width': band, 'sides': summary,
                  'limitations': ['root must stay static', 'mirrored bindings are not a general parent transform implementation',
                                  'two draw layers may expose a filtered cut', 'cuff and fingers remain rigid']}
        (out / 'layered_sleeve_report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
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
        print(f'layered sleeve study: {exc}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
