#!/usr/bin/env python3
"""Repeatable real-C visual captures for the combined Chibi trial."""
import argparse
import json
from pathlib import Path
import shutil
import tempfile
import numpy as np
from PIL import Image
from capture_chibi_joint_art import image
from study_underpaint_sampling import ROOT,start,stop,request,frames


def setup(url):
 for path in ('/api/pause?on=1','/api/action?id=neutral','/api/param?all=1',
              '/api/blink?v=0','/api/step?n=900','/api/scale?s=1'):request(url,path)

def collect(url):
 setup(url);result={'neutral':image(url)}
 for v in (0,.05,.1,.2,.25,.5,.75,1):
  request(url,f'/api/param?id=ParamMouthOpenY&v={v}');request(url,'/api/step?n=3');result[f'mouth_{v}']=image(url)
 request(url,'/api/param?all=1');request(url,'/api/step?n=3')
 for v in (0,.25,.5,.75,.92,1):
  request(url,f'/api/blink?v={v}');request(url,'/api/step?n=3');result[f'blink_{v}']=image(url)
 request(url,'/api/blink?v=0');request(url,'/api/step?n=3')
 request(url,'/api/param?id=ParamEyeLOpen&v=0');request(url,'/api/step?n=3');result['wink_left']=image(url)
 request(url,'/api/param?id=ParamEyeLOpen&reset=1');request(url,'/api/step?n=3')
 for side in 'LR':
  for finger in ('Little','Ring','Middle','Index','Thumb'):
   ident=f'ParamFinger{side}{finger}';request(url,f'/api/param?id={ident}&v=1');request(url,'/api/step?n=3')
   result[ident]=image(url);request(url,f'/api/param?id={ident}&v=0');request(url,'/api/step?n=3')
 for v in (-1,0,1):
  for path in (f'/api/param?id=ParamWristL&v={v}',f'/api/param?id=ParamWristR&v={-v}',
               f'/api/param?id=ParamFingerLIndex&v={v}',f'/api/param?id=ParamFingerRThumb&v={-v}',
               f'/api/param?id=ParamArmL&v={v}',f'/api/param?id=ParamArmR&v={v}',
               f'/api/param?id=ParamElbowL&v={v}',f'/api/param?id=ParamElbowR&v={v}', '/api/step?n=3'):request(url,path)
  result[f'combined_{v}']=image(url)
 request(url,'/api/param?all=1');request(url,'/api/blink?v=0');request(url,'/api/step?n=3')
 for v in (-1,1):
  request(url,f'/api/param?id=ParamGazeX&v={v}');request(url,'/api/step?n=3');result[f'gaze_{v}']=image(url)
 request(url,'/api/param?all=1');request(url,'/api/action?id=finger_test');request(url,'/api/step?n=30')
 result['loop_0']=image(url);request(url,'/api/step?n=60');result['loop_1']=image(url)
 return result

def changed(a,b):return int(np.any(a!=b,axis=2).sum())

def save_crop(arr,box,scale,path,bg):
 im=Image.fromarray(arr);canvas=Image.new('RGBA',im.size,bg);canvas.alpha_composite(im)
 coords=tuple(round(v*scale) for v in box);crop=canvas.crop(coords);crop.resize((crop.width*3,crop.height*3)).convert('RGB').save(path)

def capture(candidate,out):
 root=(ROOT/'build').resolve();candidate=Path(candidate).resolve();out=Path(out);target=out.resolve()
 if root not in candidate.parents or root not in target.parents or target==candidate or target in candidate.parents or candidate in target.parents:raise ValueError('paths must be separate and inside build')
 if out.exists() or out.is_symlink() or not out.parent.is_dir():raise ValueError('output must be new')
 if not (candidate/'refinement_report.json').is_file():raise ValueError('expected refinement candidate')
 with tempfile.TemporaryDirectory(prefix='refinement-capture-',dir=root) as tmp:
  proc,url=start(Path(tmp)/'preview',candidate)
  try:
   shots=collect(url);multi=frames(url,(.35,.55,.8,1))
  finally:stop(proc)
 metrics={'finger_pixels':{k:changed(shots['neutral'],v) for k,v in shots.items() if k.startswith('ParamFinger')},
          'mouth_full':changed(shots['mouth_0'],shots['mouth_1']),
          'half_blink':changed(shots['blink_0'],shots['blink_0.5']),
          'closed_blink':changed(shots['blink_0'],shots['blink_1']),
          'wink_left':changed(shots['blink_0'],shots['wink_left']),
          'gaze_extremes':changed(shots['gaze_-1'],shots['gaze_1']),
          'finger_loop':changed(shots['loop_0'],shots['loop_1']),
          'multi_pose_pixels':{str(s):{pose:changed(multi[(s,'neutral')],multi[(s,pose)]) for pose in ('outward','inward')} for s in (.35,.55,.8,1)}}
 out.mkdir()
 try:
  for name,arr in shots.items():
   if name.startswith('ParamFinger'):continue
   box=(465,395,555,450) if name.startswith('mouth') else (375,320,640,410) if name.startswith(('blink','gaze','wink')) else (285,475,740,755)
   for label,bg in (('light',(247,247,247,255)),('dark',(38,43,49,255))):
    save_crop(arr,box,1,out/f'{name}_{label}.png',bg)
  for (scale,pose),arr in multi.items():save_crop(arr,(300,465,730,735),scale,out/f'scale_{scale}_{pose}_dark.png',(38,43,49,255))
  (out/'metrics.json').write_text(json.dumps(metrics,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
  return metrics
 except BaseException:shutil.rmtree(out);raise

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('candidate');p.add_argument('output');a=p.parse_args()
 try:print(json.dumps(capture(a.candidate,a.output),ensure_ascii=False,indent=2))
 except (ValueError,OSError,RuntimeError) as e:print('capture:',e,file=__import__('sys').stderr);return 1
 return 0
if __name__=='__main__':raise SystemExit(main())
