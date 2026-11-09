#!/usr/bin/env python3
"""Build a rejected opt-in eye-fade fixture; needs the archived engine patch.

Only for comparison of the failed alternative. Without the patch the engine
ignores the new tags, and this is just the old behavior.
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
        found = set()
        for part in rig['parts']:
            if part['id'] in {f'lid_{kind}_{side}' for kind in ('closed', 'smile') for side in 'lr'}:
                part['tags'].append('eye_expression_aligned_fade')
                found.add(part['id'])
        if len(found) != 4:
            raise ValueError('expected both closed and smile eye parts')
        path.write_text(json.dumps(rig, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        report = {'visual_acceptance': 'failed', 'failure': 'misaligned closed/pain silhouettes ghost during fade',
                  'engine_patch': 'experiments/live2d_chibi_extended/rejected/aligned_eye/engine.patch',
                  'without_patch': 'tag has no effect'}
        (out / 'aligned_eye_report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
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
        print(f'aligned eye study: {exc}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
