#!/usr/bin/env python3
"""Unapproved continuous eye-contour topology study (requires test C patch).

Two coincident closed contours are independently meshed: smile bends both,
pain separates their outer ends. The archived test patch scales smile by
(1 - pain) as a priority experiment; default engine ignores the tag.
"""
import argparse
import copy
from io import BytesIO
import json
import math
import shutil
import sys
from pathlib import Path
from PIL import Image
import resvg_py
import build_chibi_extended as base
import build_chibi_underlay as torso

ROOT = Path(__file__).resolve().parents[1]
SECONDARY = ROOT / 'experiments/live2d_chibi_morph_study/secondary_lid.svg'


def build(output):
    out = Path(output)
    base.build(out)
    try:
        path = out / 'rig.json'
        rig = json.loads(path.read_text(encoding='utf-8'))
        secondary = Image.open(BytesIO(resvg_py.svg_to_bytes(svg_path=str(SECONDARY),
                                    width=215, height=114, skip_system_fonts=True))).convert('RGBA')
        for side in 'lr':
            closed_id = f'lid_closed_{side}'
            closed = next(p for p in rig['parts'] if p['id'] == closed_id)
            closed['tags'].append('eye_closed_morph')
            extra = copy.deepcopy(closed)
            extra['id'] = f'lid_closed_secondary_{side}'
            extra['file'] = f'sprites/lid_closed_secondary_{side}.png'
            extra['layer'] = closed['layer'] + 1
            x0, x1 = (0, 100) if side == 'l' else (110, 215)
            secondary.crop((x0, 0, x1, 114)).save(out / extra['file'])
            rig['parts'].append(extra)
            remove = {f'lid_smile_{side}', f'lid_pain_{side}'}
            rig['parts'] = [p for p in rig['parts'] if p['id'] not in remove]
            rig['deformers'] = [d for d in rig['deformers'] if d.get('part') not in remove]
            for index, part in enumerate((closed, extra)):
                smile_points = []
                pain_points = []
                width = 100 if side == 'l' else 105
                for row in range(5):
                    for col in range(9):
                        x = col * width / 8
                        # The exposed left eye runs approximately x=13..86;
                        # reverse the corresponding orientation for the right.
                        t = max(0, min(1, (x - (13 if side == 'l' else 19)) / 73))
                        if side == 'r':
                            t = 1 - t
                        smile = 2 - 7 * math.sin(math.pi * t)
                        # Narrow the originally thick closed-lid silhouette as
                        # the pain wedge opens; both contours still converge
                        # continuously to the original line when pain is zero.
                        y = row * 114 / 4
                        pain = (-8 if index == 0 else 8) * (1 - t) - .55 * (y - 65)
                        smile_points.append({'c': col, 'r': row, 'dy': round(smile, 4)})
                        pain_points.append({'c': col, 'r': row, 'dy': round(pain, 4)})
                for kind, points in (('smile', smile_points), ('pain', pain_points)):
                    rig['deformers'].append({'id': f'mesh_{part["id"]}_{kind}', 'part': part['id'],
                        'cols': 8, 'rows': 4, 'param': f'ParamEye{side.upper()}{kind.title()}',
                        'keys': [{'v': 0, 'points': []}, {'v': 1, 'points': points}]})
        path.write_text(json.dumps(rig, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        report = {'visual_acceptance': 'not evaluated', 'engine_tag': 'eye_closed_morph',
                  'secondary_art_sha256': torso.sha(SECONDARY),
                  'limitations': ['requires separate patched engine', 'two overlapping strokes may darken edges',
                                  'pain priority remains experimental', 'open/closed handoff remains']}
        (out / 'morph_eye_report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
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
        print(f'morph eye study: {exc}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
