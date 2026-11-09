#!/usr/bin/env python3
"""Technical tests of unapproved pocket relocation, not a visual verdict."""
import sys
import tempfile
from pathlib import Path
import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'tools'))
sys.path.insert(0, str(ROOT/'tests'))
import build_chibi_layered_sleeve_study as layered
import build_chibi_pocket_split_study as study
from test_chibi_topology_studies import exercise


def main():
    (ROOT/'build').mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='pocket-split-test-', dir=ROOT/'build') as work:
        tmp = Path(work)
        base, model = tmp/'base', tmp/'model'
        layered.build(base)
        info = study.build(model)
        assert info['visual_acceptance'] == 'not evaluated'
        a = np.array(Image.open(base/'sprites/body.png').convert('RGBA'))
        b = np.array(Image.open(model/'sprites/body.png').convert('RGBA'))
        assert np.array_equal(a[:, :, 3], b[:, :, 3])
        diff = np.any(a != b, axis=2)
        assert diff.any()
        allowed = np.zeros(diff.shape, bool)
        allowed[122:178, 135:190] = True
        allowed[122:178, 270:325] = True
        assert not np.any(diff & ~allowed), 'changed body pixels outside reviewed pockets'
        for target in (model, ROOT/'experiments/unsafe-pocket-output'):
            try:
                study.build(target)
            except ValueError:
                pass
            else:
                raise AssertionError('unsafe destination accepted')
        for distance in (0, 13):
            try:
                study.build(tmp/f'invalid-{distance}', distance)
            except ValueError:
                pass
            else:
                raise AssertionError('unsupported distance accepted')
        exercise(model, tmp, 'pocket', None, False)
    print('pocket diagnostic: bounded body edits, alpha, C pose and package round-trip passed; NOT visual acceptance')


if __name__ == '__main__':
    main()
