#!/usr/bin/env python3
"""Technical checks for the rejected high-res hand diagnostic, not visual approval."""
import json
import sys
import tempfile
from pathlib import Path
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'tools'), str(ROOT / 'tests')]
import build_chibi_hires_hand_study as study
from test_chibi_topology_studies import exercise


def main():
    (ROOT / 'build').mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='hires-hand-test-', dir=ROOT / 'build') as temp:
        tmp = Path(temp)
        model = tmp / 'model'
        report = study.build(model)
        assert report['visual_acceptance'] == 'not evaluated'
        assert len(report['source_sha256']) == 3
        rig = json.loads((model / 'rig.json').read_text())
        for side in 'lr':
            for name in ('palm', 'little', 'ring', 'middle', 'index', 'thumb'):
                ident = f'hand_{side}' if name == 'palm' else f'finger_{side}_{name}'
                part = next(p for p in rig['parts'] if p['id'] == ident)
                assert part['scale'] == .5 and part['pos'] == [280, 458] and part['anchor'] == [0, 0]
                with Image.open(model / part['file']) as im:
                    assert im.size == (960, 1024) and im.getbbox()
            for finger in ('Little', 'Ring', 'Middle', 'Index', 'Thumb'):
                param = next(p for p in rig['params'] if p['id'] == f'ParamFinger{side.upper()}{finger}')
                assert any(b.get('group') == f'finger_{side}_{finger.lower()}' and b.get('param') == 'rot_deg' for b in param['binds'])
        for unsafe in (model, ROOT / 'experiments/unsafe-hires-hand'):
            try:
                study.build(unsafe)
            except ValueError:
                pass
            else:
                raise AssertionError('unsafe destination accepted')
        exercise(model, tmp, 'hires', None, False)
    print('high-res hand structure, C response and package round-trip passed; NOT visual acceptance')


if __name__ == '__main__':
    main()
