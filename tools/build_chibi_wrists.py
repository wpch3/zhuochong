#!/usr/bin/env python3
"""Build a reversible Chibi wrist/hand split with new hidden skin artwork.

Inputs are fixed repository sources; output must be a new build subdirectory.
This is an experiment, not a finished illustration or Cubism project.
"""
import argparse
from io import BytesIO
import json
from pathlib import Path
import shutil
import sys
import tempfile

import numpy as np
from PIL import Image
import resvg_py
import build_chibi_underlay as torso
from build_dynamic_chibi import bind,parameter

ROOT=Path(__file__).resolve().parents[1]
SVG=ROOT/'experiments/live2d_chibi_wrist_study/wrist_underpaint.svg'
TORSO_SVG_SHA='584fe08e508bd563f095772190b38b6997fb96c8a90cb137c97940e92137f202'

def build(out):
 out=Path(out);scratch=(ROOT/'build').resolve();resolved=out.resolve()
 if scratch not in resolved.parents:raise ValueError('output must be a new build subdirectory')
 if out.exists() or out.is_symlink():raise ValueError('output exists')
 if not out.parent.is_dir():raise ValueError('output parent missing')
 if torso.sha(torso.SVG)!=TORSO_SVG_SHA:raise ValueError('torso art changed; re-review wrists and positions')
 with tempfile.TemporaryDirectory(prefix='wrist-base-',dir=scratch) as temp:
  temp=Path(temp);base=temp/'base';torso_report=torso.build(base)
  rig=json.loads((base/'rig.json').read_text(encoding='utf-8'))
  wrist=np.array(Image.open(BytesIO(resvg_py.svg_to_bytes(svg_path=str(SVG),width=480,height=512,skip_system_fonts=True))).convert('RGBA'))
  yy,xx=np.indices((512,480));reports={};pieces={}
  for side in 'lr':
   arm=Image.open(base/f'sprites/arm_{side}.png').convert('RGBA');arr=np.array(arm)
   boundary=(0.52*xx+156 if side=='l' else 376-0.46*xx)
   select=yy >= boundary
   # The cuff's dark rim crosses the diagonal at a few pixels. Keep those
   # near-boundary dark/teal fragments on the stationary cuff, not on skin.
   dark=np.min(arr[:,:,:3],axis=2)<125
   teal=arr[:,:,1].astype(np.int16)>arr[:,:,0].astype(np.int16)+8
   select &= ~((yy < boundary+3)&(dark|teal))
   hand=arr.copy();hand[~select]=0
   sleeve=arr.copy();sleeve[select]=0
   extension=wrist.copy();allowed=(sleeve[:,:,3]==255)&((xx<240) if side=='l' else (xx>=240))
   extension[~allowed]=0
   if not np.any(hand[:,:,3]) or not np.any(extension[:,:,3]):raise ValueError('empty hand or wrist extension')
   # A distinct wrist extension part is below the cuff. At rest all its pixels
   # are occluded by a fully opaque sleeve; native RGBA remains exact.
   recomposed=Image.fromarray(extension);recomposed.alpha_composite(Image.fromarray(sleeve));recomposed.alpha_composite(Image.fromarray(hand))
   if not np.array_equal(np.array(recomposed),arr):raise ValueError('source arm split fails neutral composition')
   pieces[side]=(sleeve,hand,extension)
   reports[side]={'hand_pixels':int(np.count_nonzero(hand[:,:,3])),
                  'sleeve_pixels':int(np.count_nonzero(sleeve[:,:,3])),
                  'hidden_skin_pixels':int(np.count_nonzero(extension[:,:,3])),
                  'neutral_arm_rgba_equal':True}
  for side,pivot,direction in (('l',[380,663],1),('r',[640,663],-1)):
   rig['groups']['wrist_'+side]={'pivot':pivot,'parent':'shoulder_'+side}
   for p in rig['parts']:
    if p['id']=='arm_'+side:p['layer']=12
   rig['parts'] += [
    {'id':'wrist_under_'+side,'file':f'sprites/wrist_under_{side}.png','group':'wrist_'+side,'pos':[280,458],'anchor':[0,0],'layer':11},
    {'id':'hand_'+side,'file':f'sprites/hand_{side}.png','group':'wrist_'+side,'pos':[280,458],'anchor':[0,0],'layer':13}]
   rig['params'].append(parameter('ParamWrist'+side.upper(),('左' if side=='l' else '右')+'手腕',-1,1,0,
                                   [bind('wrist_'+side,'rot_deg',direction*6)]))
  rig['actions'].append({'id':'wrist_test','title':'手腕小摆（试验）','priority':2,'loop':True,'channels':[
   {'target':'ParamWristL','param':'value','wave':'sine','amp':.8,'freq':.3},
   {'target':'ParamWristR','param':'value','wave':'sine','amp':.8,'freq':.3,'phase':.5}]})
  # Preserve the preview's expected candidate identity; specific report and
  # page text distinguish this from the older occlusion-limited trial.
  out.mkdir()
  try:
   shutil.copytree(base/'sprites',out/'sprites')
   for side,(sleeve,hand,extension) in pieces.items():
    for name,rgba in ((f'arm_{side}',sleeve),(f'hand_{side}',hand),(f'wrist_under_{side}',extension)):
     Image.fromarray(rgba).save(out/f'sprites/{name}.png')
   (out/'rig.json').write_text(json.dumps(rig,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
   report={'torso_svg_sha256':TORSO_SVG_SHA,'wrist_svg_sha256':torso.sha(SVG),
           'torso_body_sha256':torso.sha(base/'sprites/body.png'),
           'source_sha256':torso_report['source_sha256'], 'parts':reports,
           'cut_lines':['y >= 0.52*x + 156','y >= 376 - 0.46*x'],
           'rim_rule':'dark/teal fragments within 3px of cut remain on cuff',
           'wrist_pivots':{'l':[380,663],'r':[640,663]},'rotation_degrees':6,
           'neutral_c_verified':False,'visual_acceptance':'not evaluated'}
   (out/'wrist_report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
   return report
  except BaseException:shutil.rmtree(out);raise

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('output',type=Path);args=p.parse_args()
 try:print(json.dumps(build(args.output),ensure_ascii=False,indent=2))
 except (ValueError,OSError,KeyError,StopIteration) as e:print('wrist trial:',e,file=sys.stderr);return 1
 return 0
if __name__=='__main__':sys.exit(main())
