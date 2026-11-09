#!/usr/bin/env python3
"""Unapproved one-mesh pain-wedge experiment, no production resources changed.

The second branch is embedded in the same sprite and collapsed into the upper
stroke at pain=0. This tests mesh topology; it is not a source-art replacement.
Requires the isolated morph experiment C binary for pain-over-smile priority.
"""
import argparse
import json
import math
import shutil
import sys
from pathlib import Path
import numpy as np
from PIL import Image
import build_chibi_pupil_hold_study as base


def build(output):
    out = Path(output)
    base.build(out)
    try:
        path = out / 'rig.json'
        rig = json.loads(path.read_text(encoding='utf-8'))
        for side in 'lr':
            remove = {f'lid_closed_{side}', f'lid_smile_{side}', f'lid_pain_{side}'}
            rig['parts'] = [p for p in rig['parts'] if p['id'] not in remove]
            rig['deformers'] = [d for d in rig['deformers'] if d.get('part') not in remove]
            lid = next(p for p in rig['parts'] if p['id'] == f'lid_{side}')
            lid['tags'] = ['eyelid', 'eye_keyform_effective_blink', 'eye_closed_morph']
            srcpath = out / lid['file']
            art = np.array(Image.open(srcpath).convert('RGBA'))
            h, w = art.shape[:2]
            # Extract a thin internal line from the actual lash, then place it
            # below the upper stroke with a tapered gap toward the inner corner.
            branch = np.zeros_like(art)
            left, right = (17, 84) if side == 'l' else (21, 88)
            centers = []
            for x in range(w):
                alpha = art[:, x, 3].astype(float) / 255
                centers.append(float((np.arange(h) * alpha).sum() / alpha.sum()) if alpha.sum() else 65.0)
            for x in range(left, right):
                t = (x-left)/(right-left-1)
                if side == 'r': t = 1-t
                gap = round(10*(1-t))
                y = centers[x]
                for yy in range(max(0, int(y)-2), min(h-gap, int(y)+4)):
                    alpha = max(0.0, min(1.0, 1.5-abs(yy-y))) * art[yy,x,3]/255
                    branch[yy+gap,x] = (33, 20, 33, round(255*alpha))
            merged = Image.fromarray(art)
            merged.alpha_composite(Image.fromarray(branch))
            merged.save(srcpath)
            d = next(d for d in rig['deformers'] if d['id'] == f'mesh_lid_{side}')
            existing = d['keys'][0]['points']
            offsets = [next(p['dy'] for p in existing if p['r']==0 and p['c']==col) for col in range(9)]
            d['cols'] = d['rows'] = 16
            closing = []
            pain_flat = []
            smile = []
            for row in range(17):
                for col in range(17):
                    x = col*w/16; y = row*h/16
                    c = min(7, col//2); frac = col/2-c
                    close = offsets[c]*(1-frac)+offsets[c+1]*frac
                    t = max(0, min(1, (x-left)/(right-left-1)))
                    if side == 'r': t = 1-t
                    center = centers[min(w-1, int(x))]
                    # Only the band below the upper stroke is drawn upward.
                    lower = max(0, min(1, (y-(center+2))/10))
                    closing.append({'c':col,'r':row,'dy':round(close,4)})
                    pain_flat.append({'c':col,'r':row,'dy':round(-10*(1-t)*lower,4)})
                    smile.append({'c':col,'r':row,'dy':round(-5*math.sin(math.pi*t),4)})
            d['keys'][0]['points'] = closing
            for kind, zero, full in (('pain', pain_flat, []), ('smile', [], smile)):
                rig['deformers'].append({'id': f'mesh_lid_{side}_{kind}', 'part': lid['id'],
                    'cols':16, 'rows':16, 'param':f'ParamEye{side.upper()}{kind.title()}',
                    'keys':[{'v':0,'points':zero}, {'v':1,'points':full}]})
        path.write_text(json.dumps(rig,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        report={'visual_acceptance':'not evaluated', 'requires':'build/zhuochong_eye_morph_experiment',
                'limitations':['synthetic branch is diagnostic only', 'mesh may fold or squash',
                               'single texture and no real art redraw', 'paint order not independently adjustable']}
        (out/'singlemesh_lid_report.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
        return report
    except BaseException:
        shutil.rmtree(out)
        raise


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output',type=Path)
    args=parser.parse_args()
    try:
        print(json.dumps(build(args.output),indent=2))
    except (ValueError, OSError, KeyError, StopIteration) as exc:
        print(f'singlemesh lid study: {exc}',file=sys.stderr)
        return 1
    return 0


if __name__=='__main__':
    raise SystemExit(main())
