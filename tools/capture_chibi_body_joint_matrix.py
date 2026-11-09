#!/usr/bin/env python3
"""Capture actual C joint extremes combined with body sway/breath.

A diagnostic sample, not an exhaustive motion or visual acceptance test.
"""
import argparse
import itertools
import json
import shutil
import tempfile
from pathlib import Path
from capture_chibi_art_review import reset
from capture_chibi_joint_art import image
from capture_chibi_refinement import setup, save_crop
from capture_chibi_visual_matrix import verify_pose
from study_underpaint_sampling import ROOT, request, start, stop


def cases():
    result = {'neutral': {}}
    for side, (arm, elbow, wrist), body in itertools.product(
            'LR', itertools.product((-1, 1), repeat=3), (-1, 1)):
        key = f'{side}_a{arm}_e{elbow}_w{wrist}_body{body}'
        result[key] = {f'ParamArm{side}': arm, f'ParamElbow{side}': elbow,
                       f'ParamWrist{side}': wrist, 'ParamMotionDrive': body, 'ParamBreath': 1}
    return result


def capture(candidate, output):
    root = (ROOT / 'build').resolve()
    candidate = Path(candidate).resolve()
    out = Path(output)
    dest = out.resolve()
    if root not in candidate.parents or root not in dest.parents or dest == candidate or dest in candidate.parents or candidate in dest.parents:
        raise ValueError('separate paths inside build required')
    if out.exists() or out.is_symlink() or not out.parent.is_dir():
        raise ValueError('output must be new')
    if not (candidate / 'joint_stress_report.json').is_file():
        raise ValueError('expected joint stress rig')
    shots = {}
    poses = cases()
    with tempfile.TemporaryDirectory(prefix='body-joint-', dir=root) as temp:
        proc, url = start(Path(temp) / 'preview', candidate)
        try:
            setup(url)
            for name, params in poses.items():
                reset(url)
                for k, v in params.items():
                    request(url, f'/api/param?id={k}&v={v}')
                request(url, '/api/step?n=3')
                verify_pose(url, params)
                shots[name] = image(url)
        finally:
            stop(proc)
    out.mkdir()
    try:
        for name, arr in shots.items():
            for label, bg in (('light', (247, 247, 247, 255)), ('dark', (38, 43, 49, 255))):
                save_crop(arr, (290, 450, 730, 720), 1, out / f'{name}_{label}.png', bg)
        (out / 'poses.json').write_text(json.dumps(poses, indent=2) + '\n', encoding='utf-8')
    except BaseException:
        shutil.rmtree(out)
        raise
    return len(shots)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('candidate')
    parser.add_argument('output')
    args = parser.parse_args()
    try:
        print('C body/joint poses captured:', capture(args.candidate, args.output))
    except (ValueError, OSError, RuntimeError) as exc:
        print(f'capture: {exc}', file=__import__('sys').stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
