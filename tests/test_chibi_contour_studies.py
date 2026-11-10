#!/usr/bin/env python3
"""Technical checks of unapproved contour studies, not visual verdicts."""
import json
import sys
import tempfile
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import build_chibi_finger_mesh_study as fingers
import build_chibi_whole_hand_study as whole
import build_chibi_webbed_hand_study as webbed
import build_chibi_morph_eye_study as eye
from capture_chibi_art_review import reset
from capture_chibi_expression_mix import cases
from capture_chibi_two_hand_endpoints import gray_codes
from capture_chibi_joint_art import image
from capture_chibi_refinement import setup
from capture_chibi_visual_matrix import verify_pose
from study_underpaint_sampling import start, stop, request
import zrig_project


def capture_params(url, params):
    reset(url)
    for k, v in params.items():
        request(url, f'/api/blink?v={v}' if k == 'blink' else f'/api/param?id={k}&v={v}')
    request(url, '/api/step?n=3')
    verify_pose(url, params)
    return image(url)


def main():
    (ROOT / 'build').mkdir(exist_ok=True)
    assert len(cases()) == 54 and len(cases((.85, .925, 1))) == 54
    codes = gray_codes()
    assert len(codes) == len(set(codes)) == 1024 and set(codes) == set(range(1024))
    assert all((a ^ b).bit_count() == 1 for a, b in zip(codes, codes[1:]))
    with tempfile.TemporaryDirectory(prefix='contour-test-', dir=ROOT / 'build') as work:
        tmp = Path(work)
        for idx, builder in enumerate((fingers, whole, webbed)):
            model = tmp / f'hand{idx}'
            assert builder.build(model)['visual_acceptance'] == 'not evaluated'
            rig = json.loads((model / 'rig.json').read_text())
            archive = tmp / f'hand{idx}.zproj'
            zrig_project.create(model / 'rig.json', archive)
            zrig_project.verify(archive)
            for side in 'LR':
                for finger in ('Little', 'Ring', 'Middle', 'Index'):
                    param = next(p for p in rig['params'] if p['id'] == f'ParamFinger{side}{finger}')
                    assert not param['binds']
            proc, url = start(tmp / f'hand-preview{idx}', model)
            try:
                setup(url)
                neutral = capture_params(url, {})
                for side in 'LR':
                    for finger in ('Little', 'Ring', 'Middle', 'Index', 'Thumb'):
                        param = f'ParamFinger{side}{finger}'
                        moved = capture_params(url, {param: 1})
                        box = (slice(625, 710), slice(325, 410)) if side == 'L' else (slice(625, 710), slice(610, 695))
                        assert not np.array_equal(neutral[box], moved[box]), f'{idx}: no motion {param}'
                assert np.array_equal(neutral, capture_params(url, {})), 'neutral not restored'
            finally:
                stop(proc)
        model = tmp / 'eye'
        assert eye.build(model)['visual_acceptance'] == 'not evaluated'
        archive = tmp / 'eye.zproj'
        zrig_project.create(model / 'rig.json', archive)
        zrig_project.verify(archive)
        restored = tmp / 'eye-restored'
        zrig_project.unpack(archive, restored)
        results = []
        for i, candidate in enumerate((model, restored)):
            proc, url = start(tmp / f'eye-preview{i}', candidate, ROOT / 'build/zhuochong_eye_morph_experiment')
            try:
                setup(url)
                shots = []
                for side in 'LR':
                    pain = f'ParamEye{side}Pain'
                    smile = f'ParamEye{side}Smile'
                    no_smile = capture_params(url, {'blink': 1, pain: 1, smile: 0})
                    both = capture_params(url, {'blink': 1, pain: 1, smile: 1})
                    smile_only = capture_params(url, {'blink': 1, pain: 0, smile: 1})
                    assert np.array_equal(no_smile, both), 'pain=1 must suppress smile mesh in the patched experiment'
                    assert not np.array_equal(no_smile, smile_only), 'pain and smile must have distinct shapes'
                    shots.extend((no_smile, both, smile_only))
                results.append(shots)
            finally:
                stop(proc)
        assert all(np.array_equal(a, b) for a, b in zip(*results))
    print('contour studies: C response, pain-priority probe and package round-trip passed; no visual acceptance')


if __name__ == '__main__':
    main()
