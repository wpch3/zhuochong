#!/usr/bin/env python3
"""Regress unapproved studies and capture provenance, not a visual verdict."""
import hashlib
import json
import sys
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import build_chibi_layered_sleeve_study as layered
import build_chibi_pocket_cover_study as cover
import build_chibi_drawn_pain_branch_study as branch
import capture_chibi_body_joint_matrix as body_capture
import capture_chibi_expression_mix as eye_capture
import zrig_project


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    (ROOT / 'build').mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='cover-branch-test-', dir=ROOT / 'build') as work:
        tmp = Path(work)
        base, pocket, eye = tmp / 'base', tmp / 'pocket', tmp / 'eye'
        layered.build(base)
        assert cover.build(pocket)['visual_acceptance'] == 'not evaluated'
        assert branch.build(eye)['visual_acceptance'] == 'not evaluated'
        a = json.loads((base / 'rig.json').read_text())
        b = json.loads((pocket / 'rig.json').read_text())
        body = next(p for p in a['parts'] if p['id'] == 'body')
        assert body == next(p for p in b['parts'] if p['id'] == 'body')
        assert (base / body['file']).read_bytes() == (pocket / body['file']).read_bytes()
        for side in 'lr':
            part = next(p for p in b['parts'] if p['id'] == f'pocket_cover_{side}')
            pixels = np.asarray(Image.open(pocket / part['file']).convert('RGBA'))
            assert part['group'] == 'body' and part['layer'] == 11
            assert 100 < np.count_nonzero(pixels[:, :, 3]) < 2000
            param = next(p for p in b['params'] if p['id'] == f'ParamArm{side.upper()}')
            assert any(x.get('part') == part['id'] and x.get('param') == 'alpha' and x.get('scale') == -2 and x.get('offset') == -1 for x in param['binds'])
        rig = json.loads((eye / 'rig.json').read_text())
        for side in 'lr':
            part = next(p for p in rig['parts'] if p['id'] == f'lid_branch_{side}')
            assert 'eye_closed_morph' in part['tags']
            assert len([d for d in rig['deformers'] if d.get('part') == part['id']]) == 3
            assert Image.open(eye / part['file']).getbbox()
        for name, model in (('pocket', pocket), ('eye', eye)):
            archive = tmp / f'{name}.zproj'
            zrig_project.create(model / 'rig.json', archive)
            zrig_project.verify(archive)
        for builder, existing in ((cover, pocket), (branch, eye)):
            for unsafe in (existing, ROOT / 'experiments/unsafe-test'):
                try:
                    builder.build(unsafe)
                except ValueError:
                    pass
                else:
                    raise AssertionError('unsafe destination accepted')
        for invalid in ((float('nan'),), (float('inf'),), (.5, .5)):
            try:
                eye_capture.capture(eye, tmp / 'invalid', blinks=invalid)
            except ValueError:
                pass
            else:
                raise AssertionError('invalid blink sequence accepted')
        eye_out, body_out = tmp / 'eye-shots', tmp / 'body-shots'
        executable = ROOT / 'build/zhuochong_eye_morph_experiment'
        assert eye_capture.capture(eye, eye_out, executable, (.925,)) == 18
        assert body_capture.capture(pocket, body_out) == 33
        for output, model, binary in ((eye_out, eye, executable), (body_out, pocket, ROOT / 'build/zhuochong_preview')):
            provenance = json.loads((output / 'provenance.json').read_text())['before_capture']
            assert provenance == {'rig_sha256': digest(model / 'rig.json'), 'preview_executable_sha256': digest(binary)}
            assert json.loads((output / 'poses.json').read_text())
    print('structure, package and sampled C provenance passed; NOT visual acceptance')


if __name__ == '__main__':
    main()
