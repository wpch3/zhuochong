#!/usr/bin/env python3
"""Build an isolated Chibi jacket-underlay experiment, never production art.

Resvg/Pillow/numpy required. The SVG is trusted project art. This removes the
previous procedural stripe layer, then puts independently drawn artwork behind
the original body partition. Neutral C equality is NOT assumed or guaranteed.
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

ROOT=Path(__file__).resolve().parents[1]
DYNAMIC=ROOT/'experiments/live2d_chibi_dynamic'
ORIGINAL=ROOT/'experiments/live2d_chibi_human_blackline_seam/sprites/body.png'
SVG=ROOT/'experiments/live2d_chibi_underlay_art/jacket_sides.svg'
EXPECTED={
 'experiments/live2d_chibi_dynamic/rig.json':'d52623e14a7ebedc848ed8dc756b91448efd22b46a290eaa78d4550dbbc7b1e6',
 'experiments/live2d_chibi_dynamic/sprites/body.png':'f0b8aff36743e6f3898ea4725eb5e9f93aa8f78d47a12dd1f17e0102568b7185',
 'experiments/live2d_chibi_dynamic/sprites/arm_l.png':'eccc7418227d5ee14f52df49c5bbaf49d2cdf863e8b9168c36d95cc87839c117',
 'experiments/live2d_chibi_dynamic/sprites/arm_r.png':'f82b6d8a81a6f24f1a0a2f60d44bbc57d2e3a023c2cce01c48aeda2801af8f3f',
 'experiments/live2d_chibi_human_blackline_seam/sprites/body.png':'15c746f038f52890433caacd1c4031df9d5b4fe1e5511090eea556e688077625',
}

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def build(out):
 out=Path(out);dest=out.resolve();scratch=(ROOT/'build').resolve()
 if scratch not in dest.parents:raise ValueError('output must be a new build subdirectory')
 if out.exists() or out.is_symlink():raise ValueError('output exists; refusing to overwrite')
 if not out.parent.is_dir():raise ValueError('output parent missing')
 for p,h in EXPECTED.items():
  if sha(ROOT/p)!=h:raise ValueError(f'source changed: {p}')
 rig=json.loads((DYNAMIC/'rig.json').read_text(encoding='utf-8'))
 body=next(p for p in rig['parts'] if p['id']=='body')
 if body['file']!='sprites/body.png' or body['pos']!=[280,458]:raise ValueError('body layout changed')
 paths=[Path(p['file']) for p in rig['parts']]
 if any(p.is_absolute() or '..' in p.parts or not p.parts or p.parts[0]!='sprites' for p in paths):raise ValueError('unsafe source path')
 src=Image.open(ORIGINAL).convert('RGBA');arms=[Image.open(DYNAMIC/f'sprites/arm_{s}.png').convert('RGBA') for s in 'lr']
 raw=np.array(src); covered=np.zeros((512,480),bool)
 for arm in arms:covered |= np.array(arm)[:,:,3]>0
 raw[covered]=0
 original_partition=Image.fromarray(raw)
 recomposed=original_partition.copy()
 for arm in arms:recomposed.alpha_composite(arm)
 if not np.array_equal(np.array(recomposed),np.array(src)):raise ValueError('neutral source partition does not match')
 art=Image.open(BytesIO(resvg_py.svg_to_bytes(svg_path=str(SVG),width=480,height=512,skip_system_fonts=True))).convert('RGBA')
 if not art.getbbox():raise ValueError('empty artwork')
 body_out=art.copy();body_out.alpha_composite(original_partition)
 before=Image.open(DYNAMIC/'sprites/body.png').convert('RGBA'); changed=np.any(np.array(before)!=np.array(body_out),axis=2)
 if not changed.any():raise ValueError('candidate body unchanged')
 out.mkdir()
 try:
  for path in set(paths):
   dest=out/path;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(DYNAMIC/path,dest)
  body_out.save(out/'sprites/body.png');art.save(out/'underlay.png')
  rig['id']='xiaoxun_live2d_chibi_underpaint_trial';rig['name']='小寻 · 遮挡补画候选'
  (out/'rig.json').write_text(json.dumps(rig,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
  report={'source_sha256':EXPECTED,'art_svg_sha256':sha(SVG),'art_png_sha256':sha(out/'underlay.png'),
          'source_partition_neutral_equal':True,'changed_body_pixels':int(changed.sum()),
          'neutral_render_verified':False,'visual_acceptance':'not evaluated'}
  (out/'underlay_report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
  return report
 except BaseException:
  shutil.rmtree(out);raise

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('output',type=Path);a=p.parse_args()
 try:print(json.dumps(build(a.output),ensure_ascii=False,indent=2))
 except (ValueError,OSError,KeyError,StopIteration) as e:print('Chibi underlay:',e,file=sys.stderr);return 1
 return 0
if __name__=='__main__':sys.exit(main())
