#!/usr/bin/env python3
"""Inspect the hand with individual layers hidden at mixed-finger poses.

Uses the C preview's visibility probe: hiding a part does not change masks or
parameters. These images diagnose occlusion, not hidden-art completeness.
"""
import argparse
import json
import shutil
import tempfile
from pathlib import Path
from capture_chibi_art_review import reset
from capture_chibi_joint_art import image
from capture_chibi_refinement import setup, save_crop
from capture_chibi_visual_matrix import FINGERS, verify_pose
from study_underpaint_sampling import ROOT, request, start, stop


def capture(candidate, output):
    root = (ROOT / 'build').resolve()
    candidate = Path(candidate).resolve()
    out = Path(output)
    target = out.resolve()
    if root not in candidate.parents or root not in target.parents or target == candidate or target in candidate.parents or candidate in target.parents:
        raise ValueError('separate paths inside build required')
    if out.exists() or out.is_symlink() or not out.parent.is_dir():
        raise ValueError('output must be new')
    if not (candidate / 'extended_report.json').is_file():
        raise ValueError('expected extended rig')
    shots, poses = {}, {}
    with tempfile.TemporaryDirectory(prefix='hand-occlusion-', dir=root) as work:
        proc, url = start(Path(work) / 'preview', candidate)
        try:
            setup(url)
            for side in 'LR':
                for label, values in (('neutral', (0, 0, 0, 0, 0)),
                                      ('alternating', (-1, 1, -1, 1, -1)),
                                      ('reverse', (1, -1, 1, -1, 1))):
                    request(url, '/api/part?all=1')
                    reset(url)
                    params = {f'ParamFinger{side}{name}': v for name, v in zip(FINGERS, values)}
                    for key, val in params.items():
                        request(url, f'/api/param?id={key}&v={val}')
                    request(url, '/api/step?n=3')
                    verify_pose(url, params)
                    for hidden in ('none', 'hand') + tuple(n.lower() for n in FINGERS):
                        request(url, '/api/part?all=1')
                        part = f'hand_{side.lower()}' if hidden == 'hand' else f'finger_{side.lower()}_{hidden}'
                        if hidden != 'none':
                            request(url, f'/api/part?id={part}&vis=0')
                        verify_pose(url, params)
                        name = f'{side}_{label}_hide_{hidden}'
                        shots[name] = image(url)
                        poses[name] = {'params': params, 'hidden': None if hidden == 'none' else part}
        finally:
            stop(proc)
    out.mkdir()
    try:
        for name, frame in shots.items():
            box = (325, 625, 410, 710) if name.startswith('L_') else (610, 625, 695, 710)
            for label, bg in (('light', (247, 247, 247, 255)), ('dark', (38, 43, 49, 255))):
                save_crop(frame, box, 1, out / f'{name}_{label}.png', bg)
        (out / 'poses.json').write_text(json.dumps(poses, indent=2) + '\n', encoding='utf-8')
    except BaseException:
        shutil.rmtree(out)
        raise
    return len(shots)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('candidate')
    p.add_argument('output')
    a = p.parse_args()
    try:
        print('C hand occlusion frames:', capture(a.candidate, a.output))
    except (ValueError, OSError, RuntimeError) as exc:
        print(f'hand occlusion capture: {exc}', file=__import__('sys').stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
