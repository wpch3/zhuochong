#!/usr/bin/env python3
"""Technical checks for the unapproved weighted sleeve diagnostic fixture."""
import json
import shutil
import sys
import tempfile
from pathlib import Path
import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import build_chibi_weighted_sleeve_study as study
import build_chibi_finger_slide_study as slide
import build_chibi_aligned_eye_study as eye
from capture_chibi_body_joint_matrix import cases as body_cases
import zrig_project
from capture_chibi_refinement import setup
from capture_chibi_joint_art import image
from capture_chibi_visual_matrix import verify_pose
from study_underpaint_sampling import request, start, stop


def main():
    (ROOT / 'build').mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='weighted-sleeve-test-', dir=ROOT / 'build') as work:
        tmp = Path(work)
        model = tmp / 'model'
        report = study.build(model)
        assert report['visual_acceptance'] == 'not evaluated'
        for target in (model, ROOT / 'experiments/not-allowed'):
            try:
                study.build(target)
            except ValueError:
                pass
            else:
                raise AssertionError('must reject unsafe output')
        link = tmp / 'escape'
        link.symlink_to(ROOT / 'experiments', target_is_directory=True)
        try:
            study.build(link / 'no')
        except ValueError:
            pass
        else:
            raise AssertionError('must reject symlink escape')
        try:
            study.build(tmp / 'bad-band', 0)
        except ValueError:
            pass
        else:
            raise AssertionError('must reject bad band')
        rig = json.loads((model / 'rig.json').read_text())
        parts = {p['id']: p for p in rig['parts']}
        deformers = {d['id']: d for d in rig['deformers']}
        for side in 'lr':
            node = deformers[f'sleeve_elbow_{side}']
            weights = node['chain_w']
            assert len(weights) == 9 * 17 and min(weights) == 0 and max(weights) == 1
            assert all(a <= b for a, b in zip(weights, weights[1:]))
            assert parts[f'arm_{side}']['deformer'] == f'sleeve_root_{side}'
            assert f'forearm_{side}' not in parts and f'elbow_under_{side}' not in parts
            assert Image.open(model / parts[f'arm_{side}']['file']).size == (
                report['sides'][side]['source_bbox'][2] - report['sides'][side]['source_bbox'][0],
                report['sides'][side]['source_bbox'][3] - report['sides'][side]['source_bbox'][1])
        assert len(body_cases()) == 33
        finger_model = tmp / 'finger'
        assert slide.build(finger_model)['visual_acceptance'] == 'failed'
        finger_rig = json.loads((finger_model / 'rig.json').read_text())
        for side in 'LR':
            for finger in ('Little', 'Ring', 'Middle', 'Index'):
                p = next(p for p in finger_rig['params'] if p['id'] == f'ParamFinger{side}{finger}')
                assert [b['param'] for b in p['binds']] == ['dx', 'dy']
        eye_model = tmp / 'eye'
        assert eye.build(eye_model)['visual_acceptance'] == 'failed'
        eye_rig = json.loads((eye_model / 'rig.json').read_text())
        assert sum('eye_expression_aligned_fade' in p.get('tags', []) for p in eye_rig['parts']) == 4
        archive = tmp / 'model.zproj'
        zrig_project.create(model / 'rig.json', archive)
        zrig_project.verify(archive)
        restored = tmp / 'restored'
        zrig_project.unpack(archive, restored)
        sequences = []
        copy = tmp / 'preview-executable-copy'
        shutil.copy2(ROOT / 'build/zhuochong_preview', copy)
        for i, (candidate, executable) in enumerate(((model, None), (restored, None), (model, copy))):
            proc, url = start(tmp / f'preview-{i}', candidate, executable)
            try:
                setup(url)
                frames = [image(url)]
                for side in 'LR':
                    params = {f'ParamArm{side}': 1, f'ParamElbow{side}': -1,
                              f'ParamWrist{side}': 1}
                    for key, value in params.items():
                        request(url, f'/api/param?id={key}&v={value}')
                    request(url, '/api/step?n=3')
                    verify_pose(url, params)
                    frames.append(image(url))
                    for key in params:
                        request(url, f'/api/param?id={key}&v=0')
                    request(url, '/api/step?n=3')
                    assert np.array_equal(frames[0], image(url)), 'neutral should restore'
                assert all(not np.array_equal(frames[0], f) for f in frames[1:])
                sequences.append(frames)
            finally:
                stop(proc)
        assert all(np.array_equal(a, b) and np.array_equal(a, c) for a, b, c in zip(*sequences))
    print('study fixtures: safe build, rig structure, C motion/reset, explicit executable and package round-trip passed; visual acceptance NOT established')


if __name__ == '__main__':
    main()
