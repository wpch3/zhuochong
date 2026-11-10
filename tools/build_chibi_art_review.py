#!/usr/bin/env python3
"""Build a separate hand, joint and eye art-review candidate."""
import argparse
from io import BytesIO
import json
from pathlib import Path
import shutil
import sys
import numpy as np
from PIL import Image
import resvg_py
import build_chibi_eye_natural as natural
import build_chibi_binding_art as binding
import build_chibi_underlay as torso

ROOT=Path(__file__).resolve().parents[1]
ART=ROOT/'experiments/live2d_chibi_art_review'

def raster(name,w,h):
 return np.array(Image.open(BytesIO(resvg_py.svg_to_bytes(svg_path=str(ART/name),width=w,height=h,skip_system_fonts=True))).convert('RGBA'))

def build(output):
 out=Path(output);natural.build(out)
 try:
  rigpath=out/'rig.json';rig=json.loads(rigpath.read_text(encoding='utf-8'))
  exp=raster('expression_lids.svg',215,228)
  elbow=raster('elbow_underpaint.svg',480,512)
  yy,xx=np.indices((512,480))
  for side,xoff,width in (('l',0,100),('r',110,105)):
   mask=(xx<240) if side=='l' else (xx>=240)
   source=ART/('fingers_left.svg' if side=='l' else 'fingers_right.svg')
   for name in binding.FINGERS+('palm',):
    piece=binding.render_piece(source,name,True);piece[~mask]=0
    if not np.any(piece[:,:,3]):raise ValueError('empty finger art')
    dest=f'finger_{side}_{name}' if name!='palm' else f'hand_{side}'
    Image.fromarray(piece).save(out/f'sprites/{dest}.png')
   # Center each elbow pivot on the sleeve at its cut rather than offsetting
   # it toward the jacket; all its child wrist/finger groups follow it.
   rig['groups']['elbow_'+side]['pivot']=[400 if side=='l' else 621,595]
   img=elbow.copy();arm=np.asarray(Image.open(out/f'sprites/arm_{side}.png').convert('RGBA'))
   img[~mask | (arm[:,:,3]!=255)]=0
   if not np.any(img[:,:,3]):raise ValueError('empty joint underpaint')
   Image.fromarray(img).save(out/f'sprites/elbow_under_{side}.png')
   for index,kind in enumerate(('smile','pain')):
    Image.fromarray(exp[index*114:(index+1)*114,xoff:xoff+width]).save(out/f'sprites/lid_{kind}_{side}.png')
   # Smile art shares the upper-lid outline, so it needs the same blink
   # deformation when smile and a separate blink are combined.
   mesh=next(d for d in rig['deformers'] if d['id']==f'mesh_lid_{side}')
   smile_mesh=json.loads(json.dumps(mesh));smile_mesh.update(id=f'mesh_lid_smile_{side}',part=f'lid_smile_{side}')
   rig['deformers'].append(smile_mesh)
   part=next(p for p in rig['parts'] if p['id']==f'aperture_{side}')
   part['eyelid_travel']=-8;part['tags'].append('eye_aperture_fast_close')
   for kind in ('iris','sclera'):
    part=next(p for p in rig['parts'] if p['id']==f'{kind}_{side}')
    part['tags']=[t for t in part['tags'] if t!='eye_open_early_fade']
    if kind=='iris':
     part['tags'].append('eyelid');part['eyelid_travel']=-5
  rigpath.write_text(json.dumps(rig,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
  report={'art_sha256':{n:torso.sha(ART/n) for n in ('fingers_left.svg','fingers_right.svg','elbow_underpaint.svg','expression_lids.svg')},
          'source':'eye_natural_report.json (upstream state only)','visual_acceptance':'not evaluated',
          'limitations':'near-closed iris sliver, smile transitions, near-mirrored hands and limited joint travel still require visual review'}
  prior=out/'eye_natural_report.json';obj=json.loads(prior.read_text());obj['superseded_by_art_review_report']=True;prior.write_text(json.dumps(obj,ensure_ascii=False,indent=2)+'\n')
  (out/'art_review_report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
  return report
 except BaseException:shutil.rmtree(out);raise

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('output',type=Path);a=p.parse_args()
 try:print(json.dumps(build(a.output),ensure_ascii=False,indent=2))
 except (ValueError,OSError,KeyError,StopIteration) as e:print('art review:',e,file=sys.stderr);return 1
 return 0
if __name__=='__main__':sys.exit(main())
