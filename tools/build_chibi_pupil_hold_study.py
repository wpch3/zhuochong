#!/usr/bin/env python3
"""Isolated pupil/half-blink study using effective per-eye closure keyforms.

The adjustment is unapproved art: near closure, gaze and expression combinations
must be visually examined, not inferred from its passing technical checks.
"""
import argparse
import json
import shutil
import sys
from pathlib import Path
import build_chibi_extended as base


def build(output):
    out = Path(output)
    base.build(out)
    try:
        path = out / 'rig.json'
        rig = json.loads(path.read_text(encoding='utf-8'))
        for side in 'lr':
            part = next(p for p in rig['parts'] if p['id'] == f'iris_detail_{side}')
            if part.get('eye_side') != side:
                raise ValueError('iris side mismatch')
            part['tags'].append('eye_keyform_effective_blink')
            # The moving and smile lids already use the same open-keyform;
            # keep their shape synchronized with expression-implied closure.
            for lid_kind in ('lid', 'lid_smile'):
                lid = next(p for p in rig['parts'] if p['id'] == f'{lid_kind}_{side}')
                if lid.get('eye_side') != side:
                    raise ValueError('lid side mismatch')
                lid['tags'].append('eye_keyform_effective_blink')
            d = next(d for d in rig['deformers'] if d['id'] == f'mesh_iris_detail_{side}')
            if d.get('param') != f'ParamEye{side.upper()}Open' or (d['cols'], d['rows']) != (1, 1):
                raise ValueError('unexpected iris mesh')
            points = [{'c': c, 'r': row, 'dy': 12} for row in range(2) for c in range(2)]
            d['keys'] = [{'v': 0, 'points': []}, {'v': .2, 'points': []},
                         {'v': .3, 'points': points}, {'v': .5, 'points': points},
                         {'v': 1, 'points': []}]
        path.write_text(json.dumps(rig, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        report = {'visual_acceptance': 'not evaluated', 'max_detail_shift_px': 12,
                  'detail_key_values': [0, .2, .3, .5, 1],
                  'limitations': ['no pupil at approximately 0.7 blink in sampled frames',
                                  'expression and open/closed eyelid handoff unresolved',
                                  'eye-line contour is unchanged']}
        (out / 'pupil_hold_report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        return report
    except BaseException:
        shutil.rmtree(out)
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    try:
        print(json.dumps(build(args.output), ensure_ascii=False, indent=2))
    except (ValueError, OSError, KeyError, StopIteration) as exc:
        print(f'pupil hold study: {exc}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
