#!/usr/bin/env python3
"""Build a fresh isolated Chibi relaxed-eye and blinking study."""
import argparse
from io import BytesIO
import json
from pathlib import Path
import shutil
import sys
import numpy as np
from PIL import Image
import resvg_py
import build_chibi_refinement as refine
import build_chibi_underlay as torso

ROOT=Path(__file__).resolve().parents[1]
ART=ROOT/'experiments/live2d_chibi_eye_natural'

def raster(name):
 return np.array(Image.open(BytesIO(resvg_py.svg_to_bytes(svg_path=str(ART/name),width=215,height=114,skip_system_fonts=True))).convert('RGBA'))

def build(output):
 out=Path(output)
 # Refinement builder validates and creates the output without touching sources.
 refine.build(out)
 try:
  rig=json.loads((out/'rig.json').read_text(encoding='utf-8'));aperture=raster('apertures.svg');lids=raster('eyelids.svg');closed_lids=raster('closed_lids.svg')
  expressions=np.array(Image.open(BytesIO(resvg_py.svg_to_bytes(svg_path=str(ART/'expression_lids.svg'),width=215,height=228,skip_system_fonts=True))).convert('RGBA'))
  for side,xoff,width in [('l',0,100),('r',110,105)]:
   white=aperture[:,xoff:xoff+width].copy();mask=white.copy();mask[:,:,:3]=255
   for name,img in (('sclera',white),('aperture',mask),('lid',lids[:,xoff:xoff+width])):
    Image.fromarray(img).save(out/f'sprites/{name}_{side}.png')
   mask_part=next(p for p in rig['parts'] if p['id']==f'aperture_{side}')
   # Lift the closing aperture slightly as well as compressing it, so its
   # lower edge meets the lid. The existing eyelid tag uses per-eye blink.
   # Bottom edge is y=104 in local eye coordinates; anchors are normalized.
   mask_part.update(anchor=[0,104/114],pos=[390 if side=='l' else 525,390],
                    tags=['eye_aperture','eyelid'],eyelid_travel=-5)
   lid=next(p for p in rig['parts'] if p['id']==f'lid_{side}')
   lid['pos']=[390 if side=='l' else 525,283];lid['eyelid_travel']=33;lid['tags']=['eyelid','eye_open','eye_open_pose_fade']
   Image.fromarray(closed_lids[:,xoff:xoff+width]).save(out/f'sprites/lid_closed_{side}.png')
   rig['parts'].append({'id':f'lid_closed_{side}','file':f'sprites/lid_closed_{side}.png',
       'group':'head','pos':[390 if side=='l' else 525,283],'anchor':[0,0],
       'layer':45,'tags':['eyelid','eye_closed'],'eye_side':side,'eyelid_travel':33})
   for index,kind in enumerate(('smile','pain')):
    Image.fromarray(expressions[index*114:(index+1)*114,xoff:xoff+width]).save(out/f'sprites/lid_{kind}_{side}.png')
    rig['parts'].append({'id':f'lid_{kind}_{side}','file':f'sprites/lid_{kind}_{side}.png',
        'group':'head','pos':[390 if side=='l' else 525,283],'anchor':[0,0],
        'layer':46,'tags':['eyelid','eye_'+kind],'eye_side':side,'eyelid_travel':33})
   iris=next(p for p in rig['parts'] if p['id']==f'iris_{side}');iris['pos'][1]-=2
   iris['tags'].append('eye_open_early_fade')
   next(p for p in rig['parts'] if p['id']==f'sclera_{side}')['tags'].append('eye_open_early_fade')
   d=next(x for x in rig['deformers'] if x['id']=='mesh_lid_'+side)
   vals=[-10,-8,-3,3,5,3,-2,-6,-8]
   if side=='r':vals=vals[::-1]
   closed=[{'c':c,'r':r,'dy':vals[c]} for r in range(5) for c in range(9)]
   d['keys']=[{'v':0,'points':closed},{'v':.4,'points':[]},{'v':1,'points':[]}]
  (out/'rig.json').write_text(json.dumps(rig,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
  prior_path=out/'refinement_report.json'
  prior=json.loads(prior_path.read_text(encoding='utf-8'))
  prior['superseded_by_eye_natural_report']=True
  prior_path.write_text(json.dumps(prior,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
  report={'art_sha256':{n:torso.sha(ART/n) for n in ('apertures.svg','eyelids.svg','closed_lids.svg','expression_lids.svg')},
          'source_report':'refinement_report.json (upstream state only)', 'visual_acceptance':'not evaluated',
          'limitations':'near-closed iris and sclera fade may look pale; lid transition and simplified smile/pain art still need visual review'}
  (out/'eye_natural_report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
  return report
 except BaseException:shutil.rmtree(out);raise

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('output',type=Path);a=p.parse_args()
 try:print(json.dumps(build(a.output),ensure_ascii=False,indent=2))
 except (ValueError,OSError,KeyError,StopIteration) as e:print('natural eye trial:',e,file=sys.stderr);return 1
 return 0
if __name__=='__main__':sys.exit(main())
