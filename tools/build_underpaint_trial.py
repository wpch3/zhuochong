#!/usr/bin/env python3
"""Apply a transparent patch behind the sleeves to a NEW isolated study.

Never modifies the source or existing output. The mask is defined by the
source's fully opaque arm pixels, not by a browser-supplied mask. Requires
Pillow and numpy. This validates neutral compositing, not artistic quality.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sys
import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'experiments/live2d_chibi_dynamic'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build(patch_path, out):
    patch_path, out = Path(patch_path), Path(out)
    resolved, root = out.resolve(), ROOT.resolve()
    scratch = (ROOT / 'build').resolve()
    exp = (ROOT / 'experiments').resolve()
    valid_scratch = scratch in resolved.parents
    valid_experiment = resolved.parent == exp and resolved.name.startswith('live2d_chibi_underpaint_')
    if not (valid_scratch or valid_experiment) or resolved == SOURCE.resolve():
        raise ValueError('output must be a new build subdirectory or a named underpaint experiment')
    if out.exists() or out.is_symlink():
        raise ValueError('output already exists; refusing to overwrite')
    if patch_path.stat().st_size > 10_000_000:
        raise ValueError('patch too large')
    rig = json.loads((SOURCE/'rig.json').read_text(encoding='utf-8'))
    if rig.get('id') != 'xiaoxun_live2d_chibi_dynamic_study':
        raise ValueError('unexpected source study')
    with Image.open(patch_path) as p:
        if p.format != 'PNG' or p.size != (480,512):
            raise ValueError('expected a 480×512 transparent PNG patch')
        patch = p.convert('RGBA')
    body = Image.open(SOURCE/'sprites/body.png').convert('RGBA')
    arms = [Image.open(SOURCE/f'sprites/arm_{side}.png').convert('RGBA') for side in ('l','r')]
    if body.size != patch.size or any(a.size != patch.size for a in arms):
        raise ValueError('source dimensions changed')
    pixels = np.asarray(patch)
    allowed = (np.asarray(arms[0])[...,3] == 255) | (np.asarray(arms[1])[...,3] == 255)
    touched = pixels[...,3] > 0
    if not touched.any():
        raise ValueError('empty patch')
    if np.any(touched & ~allowed):
        raise ValueError('patch contains pixels not fully occluded by a neutral arm')
    result = Image.alpha_composite(body, patch)
    before = body.copy(); after = result.copy()
    for arm in arms:
        before.alpha_composite(arm); after.alpha_composite(arm)
    if not np.array_equal(np.asarray(before),np.asarray(after)):
        raise ValueError('patch changes the neutral RGBA composite')
    changed = np.any(np.asarray(body) != np.asarray(result),axis=2)
    if not changed.any():
        raise ValueError('patch does not change the body')
    if np.any(changed & ~allowed):
        raise ValueError('body changed outside the allowed area')
    paths = [Path(p['file']) for p in rig['parts']]
    if any(p.is_absolute() or '..' in p.parts or not p.parts or p.parts[0] != 'sprites' for p in paths):
        raise ValueError('unsafe source sprite path')
    # Atomic directory creation; output is never an existing model.
    out.mkdir(parents=False, exist_ok=False)
    try:
        for path in set(paths):
            dest = out/path; dest.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(SOURCE/path,dest)
        result.save(out/'sprites/body.png')
        rig['id'] = 'xiaoxun_live2d_chibi_underpaint_trial'
        rig['name'] = '小寻 · 遮挡补画候选'
        (out/'rig.json').write_text(json.dumps(rig,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        yy,xx = np.nonzero(changed)
        report = {'source':str(SOURCE.relative_to(ROOT)), 'patch_sha256':sha(patch_path),
                  'source_rig_sha256':sha(SOURCE/'rig.json'), 'source_body_sha256':sha(SOURCE/'sprites/body.png'),
                  'source_arm_sha256':{side:sha(SOURCE/f'sprites/arm_{side}.png') for side in ('l','r')},
                  'patch_nontransparent_pixels':int(touched.sum()), 'changed_body_pixels':int(changed.sum()),
                  'changed_bbox':[int(xx.min()),int(yy.min()),int(xx.max()+1),int(yy.max()+1)],
                  'neutral_rgba_equal':True, 'visual_acceptance':'not evaluated'}
        (out/'underpaint_report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    except BaseException:
        shutil.rmtree(out)
        raise
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('patch'); parser.add_argument('output')
    args=parser.parse_args()
    try: print(json.dumps(build(args.patch,args.output),ensure_ascii=False,indent=2))
    except (ValueError,OSError,KeyError,TypeError) as e:
        print('Underpaint trial error:',e,file=sys.stderr); return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
