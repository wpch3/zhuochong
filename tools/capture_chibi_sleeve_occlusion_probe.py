#!/usr/bin/env python3
"""C visibility probe to distinguish sleeve, body and pocket overlap.

Visibility toggles are diagnostic only; they do not change geometry or masks.
"""
import argparse
import json
import shutil
import tempfile
from pathlib import Path
from capture_chibi_art_review import reset
from capture_chibi_joint_art import image
from capture_chibi_refinement import setup, save_crop
from capture_chibi_visual_matrix import verify_pose
from study_underpaint_sampling import ROOT, request, start, stop


def capture(candidate, output):
    root = (ROOT / 'build').resolve()
    candidate, out = Path(candidate).resolve(), Path(output)
    dest = out.resolve()
    if root not in candidate.parents or root not in dest.parents or candidate == dest or candidate in dest.parents or dest in candidate.parents:
        raise ValueError('separate paths inside build required')
    if out.exists() or out.is_symlink() or not out.parent.is_dir():
        raise ValueError('output must be new')
    if not (candidate / 'joint_stress_report.json').is_file():
        raise ValueError('expected joint stress rig')
    shots, manifest = {}, {}
    with tempfile.TemporaryDirectory(prefix='sleeve-occlusion-', dir=root) as work:
        proc, url = start(Path(work) / 'preview', candidate)
        try:
            setup(url)
            for side in 'LR':
                reset(url)
                params = {f'ParamArm{side}': -1, f'ParamElbow{side}': -1,
                          f'ParamWrist{side}': -1, 'ParamMotionDrive': -1, 'ParamBreath': 1}
                for key, value in params.items():
                    request(url, f'/api/param?id={key}&v={value}')
                request(url, '/api/step?n=3')
                for mode in ('all', 'hide_body', 'hide_arm', 'hide_forearm', 'only_body', 'only_arm', 'only_forearm'):
                    request(url, '/api/part?all=1')
                    verb, _, part = mode.partition('_')
                    if mode != 'all':
                        ident = 'body' if part == 'body' else f'{part}_{side.lower()}'
                        request(url, f'/api/part?id={ident}&vis={0 if verb == "hide" else 2}')
                    else:
                        ident = None
                    verify_pose(url, params)
                    name = f'{side}_{mode}'
                    shots[name] = image(url)
                    manifest[name] = {'parameters': params, 'visibility_mode': mode, 'part': ident}
        finally:
            stop(proc)
    out.mkdir()
    try:
        for name, arr in shots.items():
            box = (290, 450, 570, 720) if name[0] == 'L' else (450, 450, 730, 720)
            for label, bg in (('light', (247, 247, 247, 255)), ('dark', (38, 43, 49, 255))):
                save_crop(arr, box, 1, out / f'{name}_{label}.png', bg)
        (out / 'poses.json').write_text(json.dumps(manifest, indent=2)+'\n', encoding='utf-8')
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
        print('C sleeve occlusion frames:', capture(args.candidate, args.output))
    except (ValueError, OSError, RuntimeError) as exc:
        print(f'sleeve occlusion capture: {exc}', file=__import__('sys').stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
