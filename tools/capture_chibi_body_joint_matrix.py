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
from PIL import Image
from capture_chibi_art_review import reset
from capture_chibi_joint_art import image
from capture_chibi_refinement import setup, save_crop
# from capture_chibi_visual_matrix import verify_pose  # REMOVED to break circular import
from chibi_capture_provenance import snapshot, verify_unchanged
from study_underpaint_sampling import ROOT, request, start, stop


def verify_pose(url, params):
    current = {p['id']: p['value'] for p in json.loads(request(url, '/api/params.json'))['params']}
    for key, value in params.items():
        if key == 'blink':
            actual = json.loads(request(url, '/api/info.json'))['blink_manual']
        else:
            actual = current[key]
        if actual is None or abs(actual - value) > .001:
            raise ValueError(f'pose did not apply: {key}={value}, got {actual}')


FINGERS = ('Little', 'Ring', 'Middle', 'Index', 'Thumb')


def cases():
    result = {'neutral': {}}
    # 0-360° continuous mapping: -1.0 to 1.0 with step 0.05 (41 steps)
    # Total combinations per side: 41^3 = 68,921
    # Key sampling: 1,024 critical poses (Gray code or random sampling covering extremes)
    # For execution, we use a subset of 1,024 key poses per side as per COMBINATION_CHECK_RANGE_2026-11-06.md
    # Parameters: ParamArm, ParamElbow, ParamWrist, ParamMotionDrive, ParamBreath
    import random
    random.seed(42) # Fixed seed for reproducibility
    
    # Generate 1,024 key poses per side (L/R)
    # Range: -1.0 to 1.0 (0-360° continuous mapping)
    steps = [i/20.0 for i in range(-20, 21)] # 41 steps: -1.0, -0.95, ..., 1.0
    
    for side in 'LR':
        # Neutral base
        result[f'{side}_neutral'] = {f'ParamArm{side}': 0, f'ParamElbow{side}': 0,
                                     f'ParamWrist{side}': 0, 'ParamMotionDrive': 0, 'ParamBreath': 1}
        
        # Generate 1,024 key poses
        # Using a deterministic selection from the 68,921 combinations
        # Focus on extremes and critical transitions (CH-SLEEVE-01/02/03, CH-HAND-01/02/03)
        count = 0
        # Sample extremes first
        extremes = [(-1, -1, -1), (-1, 1, 1), (1, -1, 1), (1, 1, -1), (0, 0, 0)]
        for arm, elbow, wrist in extremes:
            for body in [-1, 0, 1]:
                if count >= 1024: break
                key = f'{side}_a{arm}_e{elbow}_w{wrist}_body{body}'
                result[key] = {f'ParamArm{side}': arm, f'ParamElbow{side}': elbow,
                               f'ParamWrist{side}': wrist, 'ParamMotionDrive': body, 'ParamBreath': 1}
                count += 1
        
        # Fill remaining with random combinations within the 0-360° continuous range
        while count < 1024:
            arm = random.choice(steps)
            elbow = random.choice(steps)
            wrist = random.choice(steps)
            body = random.choice([-1, -0.5, 0, 0.5, 1])
            key = f'{side}_a{arm:.2f}_e{elbow:.2f}_w{wrist:.2f}_body{body}'
            if key not in result:
                result[key] = {f'ParamArm{side}': arm, f'ParamElbow{side}': elbow,
                               f'ParamWrist{side}': wrist, 'ParamMotionDrive': body, 'ParamBreath': 1}
                count += 1
    return result


def capture(candidate, output, executable=None):
    root = (ROOT / 'build').resolve()
    candidate = Path(candidate).resolve()
    out = Path(output)
    dest = out.resolve()
    if root not in candidate.parents or root not in dest.parents or dest == candidate or dest in candidate.parents or candidate in dest.parents:
        raise ValueError('separate paths inside build required')
    # FIX: Ensure output directory exists BEFORE starting the preview process to prevent rmtree on failure
    out.mkdir(parents=True, exist_ok=True)
    if not (candidate / 'joint_stress_report.json').is_file():
        raise ValueError('expected joint stress rig')
    binary = Path(executable).resolve() if executable else ROOT / 'build/zhuochong_preview'
    provenance = snapshot(candidate, binary)
    shots = {}
    poses = cases()
    with tempfile.TemporaryDirectory(prefix='body-joint-', dir=root) as temp:
        proc, url = start(Path(temp) / 'preview', candidate, executable)
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
        print('C body/joint poses captured:', capture(args.candidate, args.output, args.preview_executable))
    except (ValueError, OSError, RuntimeError) as exc:
        print(f'capture: {exc}', file=__import__('sys').stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
