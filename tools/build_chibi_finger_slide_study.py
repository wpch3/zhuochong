#!/usr/bin/env python3
"""Rejected rigid-translation diagnostic for independent Chibi fingers.

This deliberately tests an alternative to rotation, not a finished finger rig.
It produces detached/fused contours and must not be promoted as a repair.
"""
import argparse
import json
import shutil
import sys
from pathlib import Path
import build_chibi_extended as base


def build(output, distance=2.0):
    if not 0 < distance <= 4:
        raise ValueError('distance must be > 0 and <= 4 canvas pixels')
    out = Path(output)
    base.build(out)
    try:
        path = out / 'rig.json'
        rig = json.loads(path.read_text(encoding='utf-8'))
        for side in 'LR':
            for finger in ('Little', 'Ring', 'Middle', 'Index'):
                p = next(p for p in rig['params'] if p['id'] == f'ParamFinger{side}{finger}')
                if len(p['binds']) != 1 or p['binds'][0].get('param') != 'rot_deg':
                    raise ValueError('unexpected finger binding')
                group = p['binds'][0]['group']
                p['binds'] = [{'group': group, 'param': 'dx',
                               'scale': distance * (-1 if side == 'L' else 1)},
                              {'group': group, 'param': 'dy', 'scale': distance * .7}]
        path.write_text(json.dumps(rig, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        report = {'distance': distance, 'purpose': 'isolated translation diagnostic',
                  'visual_acceptance': 'failed', 'failure': 'disconnected/fused contours in mixed endpoints',
                  'thumb': 'unchanged'}
        (out / 'finger_slide_report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
        return report
    except BaseException:
        shutil.rmtree(out)
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    parser.add_argument('--distance', type=float, default=2.0)
    args = parser.parse_args()
    try:
        print(json.dumps(build(args.output, args.distance), ensure_ascii=False, indent=2))
    except (ValueError, OSError, KeyError, StopIteration) as exc:
        print(f'finger slide study: {exc}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
