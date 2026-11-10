#!/usr/bin/env python3
"""C rendered-frame regressions for an unapproved effective-blink pupil study."""
import json
import sys
import tempfile
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import build_chibi_extended as base
import build_chibi_pupil_hold_study as study
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


def main():
    (ROOT / 'build').mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='pupil-hold-test-', dir=ROOT / 'build') as work:
        tmp = Path(work)
        old, model = tmp / 'old', tmp / 'model'
        base.build(old)
        report = study.build(model)
        assert report['visual_acceptance'] == 'not evaluated'
        for side in 'lr':
            rig = json.loads((model / 'rig.json').read_text())
            part = next(p for p in rig['parts'] if p['id'] == f'iris_detail_{side}')
            assert 'eye_keyform_effective_blink' in part['tags']
            mesh = next(d for d in rig['deformers'] if d['id'] == f'mesh_iris_detail_{side}')
            assert [k['v'] for k in mesh['keys']] == [0, .2, .3, .5, 1]
        for bad in (model, ROOT / 'experiments/not-allowed'):
            try:
                study.build(bad)
            except ValueError:
                pass
            else:
                raise AssertionError('unsafe output')
        link = tmp / 'escape'
        link.symlink_to(ROOT / 'experiments', target_is_directory=True)
        try:
            study.build(link / 'new')
        except ValueError:
            pass
        else:
            raise AssertionError('symlink escape')
        archive = tmp / 'model.zproj'
        zrig_project.create(model / 'rig.json', archive)
        zrig_project.verify(archive)
        restored = tmp / 'restored'
        zrig_project.unpack(archive, restored)
        results = []
        for i, candidate in enumerate((old, model, restored)):
            proc, url = start(tmp / f'preview-{i}', candidate)
            try:
                setup(url)
                neutral = pose(url, {})
                captured = [neutral]
                for side in 'LR':
                    for closure in (.5, .65):
                        wink = pose(url, {f'ParamEye{side}Open': 1 - closure})
                        smile = pose(url, {f'ParamEye{side}Smile': closure})
                        pain = pose(url, {f'ParamEye{side}Pain': closure})
                        if i > 0:
                            assert np.array_equal(wink, smile) and np.array_equal(wink, pain), (
                                f'{side} {closure}: same effective closure must produce the same C frame')
                        captured.extend((wink, smile, pain))
                if i > 0:
                    # Both eyes simultaneously and max(blink, smile, pain):
                    # a weaker expression cannot override the stronger closure.
                    mixed = pose(url, {'blink': .5, 'ParamEyeLSmile': .65,
                                       'ParamEyeLPain': .3, 'ParamEyeRPain': .5})
                    equivalent = pose(url, {'blink': .5, 'ParamEyeLOpen': .35})
                    assert np.array_equal(mixed, equivalent), 'combined closure / eye isolation mismatch'
                    captured.extend((mixed, equivalent))
                assert np.array_equal(neutral, pose(url, {}))
                results.append(captured)
            finally:
                stop(proc)
        assert np.array_equal(results[0][0], results[1][0]), 'open neutral frame changed'
        assert not np.array_equal(results[0][2], results[1][2]), 'test must exercise smile-driven detail'
        assert all(np.array_equal(a, b) for a, b in zip(results[1], results[2]))
    print('pupil candidate: C smile/pain/wink equivalent closure, old neutral and package round-trip passed; visual acceptance NOT established')


if __name__ == '__main__':
    main()
