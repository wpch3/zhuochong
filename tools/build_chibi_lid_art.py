#!/usr/bin/env python3
"""Build an isolated, unapproved moving-lid and aperture experiment."""
import argparse
from io import BytesIO
import json
from pathlib import Path
import shutil
import sys
import numpy as np
from PIL import Image
import resvg_py
import build_chibi_eye_art as eye
import build_chibi_underlay as torso

ROOT = Path(__file__).resolve().parents[1]
ART = ROOT / 'experiments/live2d_chibi_binding_art/eyelids.svg'

def build(output):
    out = Path(output)
    # eye.build checks the output path before creating any files.
    eye.build(out)
    try:
        rig = json.loads((out / 'rig.json').read_text(encoding='utf-8'))
        art = np.array(Image.open(BytesIO(resvg_py.svg_to_bytes(svg_path=str(ART), width=215, height=114, skip_system_fonts=True))).convert('RGBA'))
        for side, xoff, width in [('l', 0, 100), ('r', 110, 105)]:
            p = out / f'sprites/eye_{side}_open.png'
            arr = np.array(Image.open(p).convert('RGBA'))
            y, x = np.indices((114, width))
            remove = (y >= 47) & (y <= 102) & ((x >= 15) & (x <= 85) if side == 'l' else (x >= 20) & (x <= 93))
            arr[remove] = 0
            Image.fromarray(arr).save(p)
            Image.fromarray(art[:, xoff:xoff+width]).save(out / f'sprites/lid_{side}.png')
            op = next(p for p in rig['parts'] if p['id'] == f'eye_{side}_open')
            op.pop('tags', None); op['layer'] = 43
            rig['parts'] = [p for p in rig['parts'] if p['id'] != f'eye_{side}_closed']
            mask = next(p for p in rig['parts'] if p['id'] == f'aperture_{side}')
            # Anchors are fractions of sprite dimensions, not pixel coordinates.
            mask.update(tags=['eye_aperture'], eye_side=side, anchor=[0, 105/114],
                        pos=[390 if side == 'l' else 525, 391], aperture_min=.03)
            sclera = next(p for p in rig['parts'] if p['id'] == f'sclera_{side}')
            sclera.pop('tags', None); sclera['mask'] = f'aperture_{side}'
            iris = next(p for p in rig['parts'] if p['id'] == f'iris_{side}')
            iris.pop('tags', None)
            rig['parts'].append({'id':f'lid_{side}', 'file':f'sprites/lid_{side}.png',
                'group':'head', 'pos':[390 if side == 'l' else 525, 286], 'anchor':[0,0],
                'layer':44, 'tags':['eyelid'], 'eye_side':side, 'eyelid_travel':38})
        (out/'rig.json').write_text(json.dumps(rig, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
        report = {'eyelid_art_sha256':torso.sha(ART), 'visual_acceptance':'not evaluated',
                  'limitations':'experimental redrawn eye; thick sliding lash, gaps and lower-eye fragments; no expression-specific eyelids'}
        (out/'lid_report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
        return report
    except BaseException:
        shutil.rmtree(out)
        raise

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    try:
        print(json.dumps(build(args.output), ensure_ascii=False, indent=2))
    except (ValueError, OSError, KeyError, StopIteration) as exc:
        print('lid trial:', exc, file=sys.stderr)
        return 1
    return 0
if __name__ == '__main__':
    sys.exit(main())
