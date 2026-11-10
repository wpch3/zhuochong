#!/usr/bin/env python3
"""Render the two repository-authored SVG trials and build isolated C candidates.

Requires resvg-py, Pillow and numpy. Only trusted checked-in SVG is accepted;
not a general SVG upload service. Output must be a new subdirectory of build/.
Neither experiment is approved production art or a Cubism project.
"""
import argparse
from io import BytesIO
import hashlib
import json
from pathlib import Path
import shutil
import sys

import numpy as np
from PIL import Image
import resvg_py
from underpaint_mask import safe_mask
from build_underpaint_trial import build as build_chibi

ROOT=Path(__file__).resolve().parents[1]
ART=ROOT/'experiments/hidden_art_studies'
CHIBI=ROOT/'experiments/live2d_chibi_dynamic'
TEEN=ROOT/'characters/xiaoxun/forms/teen'
EXPECTED={
    'experiments/live2d_chibi_dynamic/rig.json':'d52623e14a7ebedc848ed8dc756b91448efd22b46a290eaa78d4550dbbc7b1e6',
    'experiments/live2d_chibi_dynamic/sprites/body.png':'f0b8aff36743e6f3898ea4725eb5e9f93aa8f78d47a12dd1f17e0102568b7185',
    'experiments/live2d_chibi_dynamic/sprites/arm_l.png':'eccc7418227d5ee14f52df49c5bbaf49d2cdf863e8b9168c36d95cc87839c117',
    'experiments/live2d_chibi_dynamic/sprites/arm_r.png':'f82b6d8a81a6f24f1a0a2f60d44bbc57d2e3a023c2cce01c48aeda2801af8f3f',
    'characters/xiaoxun/forms/teen/rig.json':'66b4692b0e2d217c49a70757d01246a3af6d2ff051c388930372f3c0c3385ebe',
    'characters/xiaoxun/forms/teen/sprites/seg_torso@2x.png':'3d0ae3c02e81fe7c1afc7f856f172b44e1240c5ea50ca15e404a991128b10226',
}

def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def render(p,width,height):
    return Image.open(BytesIO(resvg_py.svg_to_bytes(svg_path=str(p),width=width,height=height,skip_system_fonts=True))).convert('RGBA')

def build(out):
    out=Path(out); root=(ROOT/'build').resolve(); dest=out.resolve()
    if root not in dest.parents: raise ValueError('output must be a new build/ subdirectory')
    if out.exists() or out.is_symlink(): raise ValueError('output already exists')
    if not out.parent.is_dir(): raise ValueError('output parent does not exist')
    for path, expected in EXPECTED.items():
        if sha(ROOT/path)!=expected: raise ValueError(f'source changed; re-review art and coordinates: {path}')
    rig=json.loads((TEEN/'rig.json').read_text(encoding='utf-8'))
    torso=next(p for p in rig['parts'] if p['id']=='seg_torso')
    if torso['pos']!=[282,308] or torso['group']!='chest' or torso['file']!='sprites/seg_torso@2x.png':
        raise ValueError('teen torso layout changed')
    out.mkdir()
    try:
        chibi=render(ART/'chibi/inner_jacket.svg',480,512)
        px=np.array(chibi)
        arms=[np.array(Image.open(CHIBI/f'sprites/arm_{s}.png').convert('RGBA'))[:,:,3] for s in 'lr']
        px[~safe_mask(arms,0)]=0
        patch=out/'chibi_patch.png';Image.fromarray(px).save(patch)
        report=build_chibi(patch,out/'chibi',0)
        teen_png=out/'teen_underarms@2x.png'
        render(ART/'teen/torso_underarms.svg',546,1000).save(teen_png)
        candidate=out/'teen'
        shutil.copytree(TEEN,candidate,symlinks=False)
        shutil.copyfile(teen_png,candidate/'sprites/hidden_torso_underarms@2x.png')
        rig['id']='xiaoxun_teen_hidden_art_trial'
        rig['name']='小寻 · 少女隐藏画稿试验（未验收）'
        rig['parts'].append({'id':'hidden_torso_underarms','file':'sprites/hidden_torso_underarms@2x.png',
                             'group':'chest','layer':97,'pos':[282,308],'anchor':[0,0],
                             'scale':0.5,'scale_1x':1.0,'hires':2})
        (candidate/'rig.json').write_text(json.dumps(rig,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        summary={'source_sha256':EXPECTED,'chibi_svg_sha256':sha(ART/'chibi/inner_jacket.svg'),
                 'teen_svg_sha256':sha(ART/'teen/torso_underarms.svg'),
                 'chibi_candidate_report':report,'teen_png_sha256':sha(teen_png),
                 'approval':'not approved; 0px chibi mask can leak, teen is an unverified extra layer'}
        (out/'report.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        return summary
    except BaseException:
        shutil.rmtree(out)
        raise

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('output',type=Path);a=p.parse_args()
    try:print(json.dumps(build(a.output),ensure_ascii=False,indent=2))
    except (OSError,ValueError,KeyError,StopIteration) as e:print('hidden art study:',e,file=sys.stderr);return 1
    return 0
if __name__=='__main__':sys.exit(main())
