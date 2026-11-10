#!/usr/bin/env python3
"""Structural/C checks for rejected topology studies, NOT a visual verdict."""
import json
import sys
import tempfile
from pathlib import Path
import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import build_chibi_layered_sleeve_study as layered
import build_chibi_sleeve_backing_study as backing
import build_chibi_unified_lid_study as eye
import capture_chibi_hand_occlusion_probe as hand_probe
import zrig_project
from capture_chibi_art_review import reset
from capture_chibi_joint_art import image
from capture_chibi_refinement import setup
from capture_chibi_visual_matrix import verify_pose
from study_underpaint_sampling import request, start, stop


def pose(url, params):
    reset(url)
    for key, value in params.items():
        request(url, f'/api/blink?v={value}' if key == 'blink' else f'/api/param?id={key}&v={value}')
    request(url, '/api/step?n=3')
    verify_pose(url, params)
    return image(url)


def exercise(path, tmp, label, executable, eye_test):
    archive = tmp / f'{label}.zproj'
    zrig_project.create(path / 'rig.json', archive)
    zrig_project.verify(archive)
    restored = tmp / f'{label}-restored'
    zrig_project.unpack(archive, restored)
    sequences = []
    for index, model in enumerate((path, restored)):
        proc, url = start(tmp / f'{label}-preview-{index}', model, executable)
        try:
            setup(url)
            if eye_test:
                a = pose(url, {'blink': .925, 'ParamEyeLPain': .5})
                b = pose(url, {'blink': 1, 'ParamEyeLPain': 1})
                c = pose(url, {'blink': 1, 'ParamEyeLPain': 1, 'ParamEyeLSmile': 1})
                assert np.array_equal(b, c), 'isolated C patch suppresses smile at full pain'
            else:
                a = pose(url, {})
                b = pose(url, {'ParamArmL': 1, 'ParamElbowL': -1,
                               'ParamWristL': 1, 'ParamMotionDrive': -1})
                c = pose(url, {})
                assert np.array_equal(a, c), 'neutral must be restored'
            assert not np.array_equal(a, b), 'pose must affect actual C frame'
            sequences.append((a, b, c))
        finally:
            stop(proc)
    assert all(np.array_equal(a, b) for a, b in zip(*sequences)), 'package round-trip'


def main():
    (ROOT / 'build').mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='topology-test-', dir=ROOT / 'build') as work:
        tmp = Path(work)
        base, sleeve, lid = tmp / 'base', tmp / 'sleeve', tmp / 'lid'
        layered.build(base)
        report = backing.build(sleeve)
        assert report['visual_acceptance'] == 'not evaluated'
        for side in 'lr':
            a = Image.open(base / f'sprites/arm_{side}.png').convert('RGBA')
            b = Image.open(base / f'sprites/forearm_{side}.png').convert('RGBA')
            assert np.array_equal(np.array(Image.alpha_composite(a, b)),
                                  np.array(Image.open(sleeve / f'sprites/arm_{side}.png')))
            front = np.array(Image.open(sleeve / f'sprites/forearm_{side}.png'))
            start = report['sides'][side]['front_start_row']
            assert not front[:start + 1, :, 3].any()
            assert front[-1, :, 3].any()
        assert eye.build(lid)['visual_acceptance'] == 'not evaluated'
        rig = json.loads((lid / 'rig.json').read_text())
        for side in 'lr':
            for part_id in (f'lid_{side}', f'lid_secondary_{side}'):
                part = next(p for p in rig['parts'] if p['id'] == part_id)
                assert 'eye_open' not in part['tags'] and 'eye_closed_morph' in part['tags']
                assert len([d for d in rig['deformers'] if d.get('part') == part_id]) == 3
            assert not any(p['id'] in {f'lid_closed_{side}', f'lid_pain_{side}',
                                       f'lid_smile_{side}'} for p in rig['parts'])
        for builder, existing in ((backing, sleeve), (eye, lid)):
            for unsafe in (existing, ROOT / 'experiments/unsafe-test'):
                try:
                    builder.build(unsafe)
                except ValueError:
                    pass
                else:
                    raise AssertionError('unsafe destination accepted')
        hand_output = tmp / 'hand-probe'
        assert hand_probe.capture(lid, hand_output) == 42
        manifest = json.loads((hand_output / 'poses.json').read_text())
        assert len(manifest) == 42 and manifest['L_alternating_hide_hand']['hidden'] == 'hand_l'
        assert not np.array_equal(np.array(Image.open(hand_output / 'L_alternating_hide_none_light.png')),
                                  np.array(Image.open(hand_output / 'L_alternating_hide_hand_light.png')))
        try:
            hand_probe.capture(lid, hand_output)
        except ValueError:
            pass
        else:
            raise AssertionError('hand capture must not overwrite evidence')
        exercise(sleeve, tmp, 'sleeve', None, False)
        exercise(lid, tmp, 'lid', ROOT / 'build/zhuochong_eye_morph_experiment', True)
    print('topology studies: structure, isolated C response and package round-trip passed; NOT visual acceptance')


if __name__ == '__main__':
    main()
