#!/usr/bin/env python3
"""Create an isolated Chibi occlusion and independently drawn hands study."""
import argparse
from io import BytesIO
import json
from pathlib import Path
import shutil
import sys
import numpy as np
from PIL import Image
import resvg_py
import build_chibi_art_review as base
import build_chibi_binding_art as binding
import build_chibi_underlay as torso

ROOT=Path(__file__).resolve().parents[1]
ART=ROOT/'experiments/live2d_chibi_closure'

def raster(name):
 return np.array(Image.open(BytesIO(resvg_py.svg_to_bytes(svg_path=str(ART/name),width=480,height=512,skip_system_fonts=True))).convert('RGBA'))

def build(output):
 out=Path(output);base.build(out)
 try:
  rp=out/'rig.json';rig=json.loads(rp.read_text(encoding='utf-8'))
  wrist=raster('wrist_underpaint.svg');shoulder=raster('shoulder_underpaint.svg');zone=raster('elbow_overlap.svg')
  _,x=np.indices((512,480));body=np.asarray(Image.open(out/'sprites/body.png').convert('RGBA'))
  report_parts={}
  for side in 'lr':
   is_side=x<240 if side=='l' else x>=240
   for name in binding.FINGERS+('palm',):
    path=ART/('hand_left.svg' if side=='l' else 'hand_right.svg')
    img=binding.render_piece(path,name,True);img[~is_side]=0
    if not np.any(img[:,:,3]):raise ValueError('empty hand layer')
    dest=f'hand_{side}' if name=='palm' else f'finger_{side}_{name}'
    Image.fromarray(img).save(out/f'sprites/{dest}.png')
   arm=np.asarray(Image.open(out/f'sprites/arm_{side}.png').convert('RGBA'))
   fore=np.asarray(Image.open(out/f'sprites/forearm_{side}.png').convert('RGBA'))
   # Every newly authored pixel must be hidden at rest by an opaque front part.
   w=wrist.copy();w[~(is_side & (fore[:,:,3]==255))]=0
   sh=shoulder.copy();sh[~(is_side & ((arm[:,:,3]==255)|(body[:,:,3]==255)))]=0
   # Continue the sleeve's own opaque color into a larger hidden overlap.
   el=np.zeros_like(arm);sel=is_side & (zone[:,:,3]>0)
   use_arm=sel & (arm[:,:,3]==255);use_fore=sel & ~use_arm & (fore[:,:,3]==255)
   el[use_arm]=arm[use_arm];el[use_fore]=fore[use_fore]
   for name,img in (('wrist_under',w),('shoulder_under',sh),('elbow_under',el)):
    if not np.any(img[:,:,3]):raise ValueError('empty hidden artwork')
    Image.fromarray(img).save(out/f'sprites/{name}_{side}.png')
   p=next(p for p in rig['parts'] if p['id']=='iris_'+side)
   p['eyelid_travel']=-9
   report_parts[side]={'wrist_hidden_pixels':int(np.count_nonzero(w[:,:,3])),
                       'shoulder_hidden_pixels':int(np.count_nonzero(sh[:,:,3])),
                       'elbow_hidden_pixels':int(np.count_nonzero(el[:,:,3]))}
  rp.write_text(json.dumps(rig,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
  prior=out/'art_review_report.json';p=json.loads(prior.read_text(encoding='utf-8'));p['superseded_by_closure_report']=True;prior.write_text(json.dumps(p,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
  report={'art_sha256':{n:torso.sha(ART/n) for n in ('hand_left.svg','hand_right.svg','wrist_underpaint.svg','shoulder_underpaint.svg','elbow_overlap.svg')},
          'source':'art_review_report.json (upstream state only)','parts':report_parts,'visual_acceptance':'not evaluated',
          'limitations':'independently drawn hands and hidden overlap must be visually checked across poses; iris motion is a trial'}
  (out/'closure_report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
  return report
 except BaseException:shutil.rmtree(out);raise

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('output',type=Path);a=p.parse_args()
 try:print(json.dumps(build(a.output),ensure_ascii=False,indent=2))
 except (ValueError,OSError,KeyError,StopIteration) as e:print('closure trial:',e,file=sys.stderr);return 1
 return 0
if __name__=='__main__':raise SystemExit(main())
