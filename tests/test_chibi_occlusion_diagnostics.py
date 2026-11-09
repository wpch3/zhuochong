#!/usr/bin/env python3
"""C regression checks for rejected eye, sleeve and finger diagnostics."""
import json
import sys
import tempfile
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
sys.path.insert(0, str(ROOT / 'tests'))
import build_chibi_extended as base
import build_chibi_layered_sleeve_study as sleeves
import build_chibi_singlemesh_lid_study as eye
import capture_chibi_sleeve_occlusion_probe as probe
from test_chibi_topology_studies import exercise
from capture_chibi_art_review import reset
from capture_chibi_joint_art import image
from capture_chibi_refinement import setup
from capture_chibi_visual_matrix import verify_pose
from study_underpaint_sampling import start, stop, request


def depths(model, tmp, label, executable):
    proc, url = start(tmp / label, model, executable)
    try:
        setup(url)
        reset(url)
        frames = [image(url)]
        for value in (.0660, .0673):
            request(url, f'/api/param?id=ParamFingerLRing&v={value}')
            request(url, '/api/step?n=3')
            verify_pose(url, {'ParamFingerLRing': value})
            frames.append(image(url))
        return frames
    finally:
        stop(proc)


def main():
    (ROOT/'build').mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='occlusion-diag-test-', dir=ROOT/'build') as work:
        tmp = Path(work)
        model, sleeve, single = tmp/'model', tmp/'sleeve', tmp/'single'
        base.build(model)
        sleeves.build(sleeve)
        assert eye.build(single)['visual_acceptance'] == 'not evaluated'
        rig = json.loads((single/'rig.json').read_text())
        for side in 'lr':
            assert not any(p['id'] in (f'lid_closed_{side}', f'lid_smile_{side}', f'lid_pain_{side}', f'lid_secondary_{side}') for p in rig['parts'])
            deforms = [d for d in rig['deformers'] if d.get('part') == f'lid_{side}']
            assert len(deforms) == 3 and all((d['cols'], d['rows']) == (16, 16) for d in deforms)
        exercise(single, tmp, 'single', ROOT/'build/zhuochong_eye_morph_experiment', True)
        output = tmp/'sleeve-occlusion'
        assert probe.capture(sleeve, output) == 14
        manifest = json.loads((output/'poses.json').read_text())
        assert len(manifest) == 14 and manifest['L_only_body']['part'] == 'body'
        assert (output/'L_only_body_light.png').is_file() and (output/'R_hide_forearm_dark.png').is_file()
        try:
            probe.capture(sleeve, output)
        except ValueError:
            pass
        else:
            raise AssertionError('must not overwrite prior evidence')
        ordinary = depths(model, tmp, 'ordinary', ROOT/'build/zhuochong_preview')
        trial = depths(model, tmp, 'trial', ROOT/'build/zhuochong_finger_depth_experiment')
        assert np.array_equal(ordinary[0], trial[0]), 'neutral draw order should remain unchanged'
        a = np.any(ordinary[1] != ordinary[2], axis=2)[625:710, 325:410].sum()
        b = np.any(trial[1] != trial[2], axis=2)[625:710, 325:410].sum()
        assert b > a, f'crossing the artificial depth threshold should expose pop ({a}/{b})'
        for builder, path in ((base, model), (eye, single), (sleeves, sleeve)):
            try:
                builder.build(path)
            except ValueError:
                pass
            else:
                raise AssertionError('existing destination must not be overwritten')
        print(f'occlusion diagnostics: C depth pop baseline {a} vs experimental {b} pixels; package and isolation passed; no visual acceptance')


if __name__ == '__main__':
    main()
