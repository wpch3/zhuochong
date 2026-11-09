#!/usr/bin/env python3
"""Numerical parent/mesh checks for the isolated layered sleeve candidate."""
import copy
import json
import shutil
import subprocess
import sys
import tempfile
from unittest import mock
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import build_chibi_layered_sleeve_study as study
import zrig_project
from study_underpaint_sampling import start, stop, request
from capture_chibi_refinement import setup
from capture_chibi_joint_art import image
from capture_chibi_visual_matrix import verify_pose
import numpy as np


def write(rig, path):
    (path / 'rig.json').write_text(json.dumps(rig, ensure_ascii=False, indent=2) + '\n')


def main():
    (ROOT / 'build').mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='layered-test-', dir=ROOT / 'build') as work:
        tmp = Path(work)
        model = tmp / 'model'
        report = study.build(model)
        assert report['visual_acceptance'] == 'not evaluated'
        for bad in (model, ROOT / 'experiments/not-allowed'):
            try:
                study.build(bad)
            except ValueError:
                pass
            else:
                raise AssertionError('unsafe output')
        symlink = tmp / 'escape'
        symlink.symlink_to(ROOT / 'experiments', target_is_directory=True)
        try:
            study.build(symlink / 'new')
        except ValueError:
            pass
        else:
            raise AssertionError('symlink escape')
        original_builder = study.stress.build
        def future_input_with_unmirrored_look(target):
            result = original_builder(target)
            path = target / 'rig.json'
            altered = json.loads(path.read_text())
            altered['look'] = {'groups': {'body': {'rot_deg': 3}}}
            path.write_text(json.dumps(altered))
            return result
        unsafe_model = tmp / 'unsafe-look'
        with mock.patch.object(study.stress, 'build', side_effect=future_input_with_unmirrored_look):
            try:
                study.build(unsafe_model)
            except ValueError:
                assert not unsafe_model.exists(), 'failed builder must clean its output'
            else:
                raise AssertionError('unmirrored look must be rejected')
        rig = json.loads((model / 'rig.json').read_text())
        for side in 'lr':
            assert report['sides'][side]['layers'] == [12, 21]
            pairs = {(p, g, channel) for p, g, channel in report['sides'][side]['mirrored_bindings']}
            assert ('ParamBreath', 'body', 'sy') in pairs
            assert ('ParamMotionDrive', 'body', 'rot_deg') in pairs
            assert ('ParamSleeveFollow', f'shoulder_{side}', 'rot_deg') in pairs
        dirs = []
        for weight in (0, .5, 1):
            dest = tmp / f'w{weight}'
            shutil.copytree(model, dest)
            data = copy.deepcopy(rig)
            for d in data['deformers']:
                if d['id'] in ('sleeve_elbow_l', 'sleeve_elbow_r'):
                    d['chain_w'] = [weight] * len(d['chain_w'])
            write(data, dest)
            dirs.append(dest)
        for group_kind in ('shoulder', 'elbow'):
            dest = tmp / group_kind
            shutil.copytree(model, dest)
            data = copy.deepcopy(rig)
            data['deformers'] = [d for d in data['deformers'] if not (
                d['id'].startswith(('sleeve_body_', 'sleeve_shoulder_', 'sleeve_elbow_'))
                or d['id'] in ('mesh_arm_l_weighted', 'mesh_arm_r_weighted',
                               'mesh_forearm_l_weighted', 'mesh_forearm_r_weighted'))]
            for p in data['params']:
                p['binds'] = [b for b in p['binds'] if not b.get('deformer', '').startswith('sleeve_')]
            for side in 'lr':
                for name in ('arm', 'forearm'):
                    ident = f'{name}_{side}'
                    part = next(p for p in data['parts'] if p['id'] == ident)
                    part.pop('deformer')
                    part['group'] = f'{group_kind}_{side}'
                    # A zero keyform guarantees identical mesh resolution for the probe.
                    data['deformers'].append({'id': f'reference_{ident}', 'part': ident,
                        'cols': 8, 'rows': 16, 'param': f'ParamArm{side.upper()}',
                        'keys': [{'v': -1, 'points': []}, {'v': 1, 'points': []}]})
            write(data, dest)
            dirs.append(dest)
        subprocess.run([str(ROOT / 'build/rig_layered_sleeve_probe'), *(str(d) for d in dirs)],
                       cwd=ROOT, check=True)
        archive = tmp / 'model.zproj'
        zrig_project.create(model / 'rig.json', archive)
        zrig_project.verify(archive)
        restored = tmp / 'restored'
        zrig_project.unpack(archive, restored)
        sequences = []
        for i, path in enumerate((model, restored)):
            proc, url = start(tmp / f'preview-{i}', path)
            try:
                setup(url)
                frames = [image(url)]
                params = {'ParamArmL': 1, 'ParamElbowL': -1, 'ParamWristL': 1,
                          'ParamMotionDrive': -1, 'ParamBreath': 1}
                for key, val in params.items():
                    request(url, f'/api/param?id={key}&v={val}')
                request(url, '/api/step?n=3')
                verify_pose(url, params)
                frames.append(image(url))
                assert not np.array_equal(*frames)
                sequences.append(frames)
            finally:
                stop(proc)
        assert all(np.array_equal(a, b) for a, b in zip(*sequences))
    print('layered sleeve: numerical parent/weight checks and C package round-trip passed; visual acceptance NOT established')


if __name__ == '__main__':
    main()
