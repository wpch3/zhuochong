#!/usr/bin/env python3
"""Capture actual C visual matrix frames combined with body sway/breath.

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
    # FIX: Call reset BEFORE checking params to ensure the engine state is fresh
    # The previous logic called reset(url) inside the capture loop, but verify_pose
    # was also being called in the same loop. Ensure reset is called just once
    # or we fetch the current state AFTER the reset and param application.
    # Here, we assume reset(url) was already called in the capture loop (see capture() below)
    # and params were applied. We just verify.
    current = {p['id']: p['value'] for p in json.loads(request(url, '/api/params.json'))['params']}
    for key, value in params.items():
        if key == 'blink':
            actual = json.loads(request(url, '/api/info.json'))['blink_manual']
        else:
            actual = current.get(key)
        if actual is None or abs(actual - value) > .001:
            raise ValueError(f'pose did not apply: {key}={value}, got {actual}')


def capture(candidate, output, executable=None):
    root = (ROOT / 'build').resolve()
    candidate = Path(candidate).resolve()
    out = Path(output)
    dest = out.resolve()
    # FIX: Relax path check to allow candidate and output to be in the same build directory
    # as long as they are distinct subdirectories. The original check was too strict.
    # We only need to ensure they are not the same path and not parents/children of each other.
    if dest == candidate or dest in candidate.parents or candidate in dest.parents:
        raise ValueError('candidate and output must be separate paths')
    if root not in candidate.parents or root not in dest.parents:
        raise ValueError('paths must be inside build directory')
    # FIX: Ensure output directory exists BEFORE starting the preview process to prevent rmtree on failure
    out.mkdir(parents=True, exist_ok=True)
    if not (candidate / 'joint_stress_report.json').is_file():
        raise ValueError('expected joint stress rig')
    binary = Path(executable).resolve() if executable else ROOT / 'build/zhuochong_preview'
    provenance = snapshot(candidate, binary)
    shots = {}
    poses = {}
    with tempfile.TemporaryDirectory(prefix='visual-matrix-', dir=root) as temp:
        proc, url = start(Path(temp) / 'preview', candidate, executable)
        try:
            setup(url)
            # Visual matrix: 54 near-closed eye frames (CH-EYE-02/04)
            # Combined with body/breath/motion
            for i in range(54):
                name = f'visual_eye_near_closed_{i:02d}'
                # ParamBlink from 0.85 to 1.0 (near closed)
                blink_val = round(0.85 + (i / 53.0) * 0.15, 3)
                params = {
                    'blink': blink_val,
                    'ParamMotionDrive': 0,
                    'ParamBreath': 1,
                    'ParamArmL': 0, 'ParamArmR': 0,
                    'ParamElbowL': 0, 'ParamElbowR': 0,
                    'ParamWristL': 0, 'ParamWristR': 0
                }
                reset(url)
                for k, v in params.items():
                    if k == 'blink':
                        request(url, f'/api/blink?v={v}')
                    else:
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
        print('C visual matrix frames captured:', capture(args.candidate, args.output, args.preview_executable))
    except (ValueError, OSError, RuntimeError) as exc:
        print(f'capture: {exc}', file=__import__('sys').stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
