#!/usr/bin/env python3
"""Capture actual C single-hand endpoints combined with body sway/breath.

A diagnostic sample, not an exhaustive motion or visual acceptance test.
"""
import argparse
import itertools
import json
import shutil
import tempfile
from pathlib import Path
from PIL import Image
from capture_chibi_art_review import reset
from capture_chibi_joint_art import image
from capture_chibi_refinement import setup, save_crop
# from capture_chibi_visual_matrix import verify_pose, FINGERS  # REMOVED to break circular import
from chibi_capture_provenance import snapshot, verify_unchanged
from study_underpaint_sampling import ROOT, request, start, stop


FINGERS = ('Little', 'Ring', 'Middle', 'Index', 'Thumb')


def verify_pose(url, params):
    current = {p['id']: p['value'] for p in json.loads(request(url, '/api/params.json'))['params']}
    for key, value in params.items():
        if key == 'blink':
            actual = json.loads(request(url, '/api/info.json'))['blink_manual']
        else:
            actual = current[key]
        if actual is None or abs(actual - value) > .001:
            raise ValueError(f'pose did not apply: {key}={value}, got {actual}')


def capture(candidate, output, executable=None):
    candidate = Path(candidate).resolve()
    out = Path(output)
    dest = out.resolve()
    root = (ROOT / 'build').resolve()
    if root not in candidate.parents or root not in dest.parents or dest == candidate or dest in candidate.parents or candidate in dest.parents:
        raise ValueError('separate paths inside build required')
    # FIX: Ensure output directory exists BEFORE starting the preview process to prevent rmtree on failure
    out.mkdir(parents=True, exist_ok=True)
    if not (candidate / 'joint_stress_report.json').is_file():
        raise ValueError('expected joint stress rig')
    binary = Path(executable).resolve() if executable else ROOT / 'build/zhuochong_preview'
    provenance = snapshot(candidate, binary)
    shots = {}
    poses = {}
    with tempfile.TemporaryDirectory(prefix='finger-endpoint-', dir=root) as temp:
        proc, url = start(Path(temp) / 'preview', candidate, executable)
        try:
            setup(url)
            for side in 'LR':
                for values in itertools.product((-1, 1), repeat=5):
                    bits = ''.join('1' if v == 1 else '0' for v in values)
                    name = f'{side}_{bits}'
                    params = {f'ParamFinger{side}{n}': v for n, v in zip(FINGERS, values)}
                    reset(url)
                    for k, v in params.items():
                        request(url, f'/api/param?id={k}&v={v}')
                    request(url, '/api/step?n=3')
                    verify_pose(url, params)
                    shots[name] = image(url)
                    poses[name] = params
        finally:
            stop(proc)
    after = verify_unchanged(provenance, candidate, binary)
    # out.mkdir() is now done earlier with exist_ok=True, so we don't delete it on failure
    try:
        (out / 'full').mkdir(parents=True, exist_ok=True)
        for name, arr in shots.items():
            # The fixed torso crop can cut off outstretched hands. Keep the
            # actual uncropped native C frame as well, including alpha.
            Image.fromarray(arr).save(out / 'full' / f'{name}.png')
            # Save expanded crop for CH-SLEEVE-01/02/03 and CH-HAND-01/02/03 verification
            # Original crop: (290, 450, 730, 720) -> width 440, height 270
            # Expanded crop to include sleeve side and finger roots: (200, 350, 820, 820) -> width 620, height 470
            for label, bg in (('light', (247, 247, 247, 255)), ('dark', (38, 43, 49, 255))):
                # Use expanded crop for visual acceptance verification
                save_crop(arr, (200, 350, 820, 820), 1, out / f'{name}_{label}.png', bg)
        (out / 'poses.json').write_text(json.dumps(poses, indent=2) + '\n', encoding='utf-8')
        (out / 'provenance.json').write_text(json.dumps({'before_capture': provenance, 'after_capture': after}, indent=2) + '\n', encoding='utf-8')
    except BaseException as e:
        # FIX: Do NOT rmtree(out) because it is now the persistent tracking directory
        print(f'capture: failed during save phase but output directory preserved: {e}', file=__import__('sys').stderr)
        raise
    return len(shots)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('candidate')
    parser.add_argument('output')
    parser.add_argument('--preview-executable', type=Path)
    args = parser.parse_args()
    try:
        print('C single-hand endpoint poses captured:', capture(args.candidate, args.output, args.preview_executable))
    except (ValueError, OSError, RuntimeError) as exc:
        print(f'capture: {exc}', file=__import__('sys').stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
