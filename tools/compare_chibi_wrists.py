#!/usr/bin/env python3
"""Capture isolated C wrist poses and compare the unsplit torso trial.

Two baseline instances must agree at the tested fixed states before reporting
pixel differences. Art judgment and other scales/poses remain out of scope.
"""
import argparse
from io import BytesIO
import json
from pathlib import Path
import shutil
import tempfile
import numpy as np
from PIL import Image
import build_chibi_underlay as torso
from study_underpaint_sampling import ROOT,start,stop,frames,request


def sample(url):
 for p in ('/api/pause?on=1','/api/action?id=neutral','/api/param?all=1','/api/blink?v=0','/api/step?n=900','/api/scale?s=0.55'):
  request(url,p)
 poses={'neutral':(0,0,0,0),'left_plus':(1,0,0,0),'left_minus':(-1,0,0,0),
        'right_plus':(0,1,0,0),'right_minus':(0,-1,0,0),
        'both_plus':(1,1,0,0),'both_minus':(-1,-1,0,0),'both_mid':(.5,.5,0,0),
        'mixed':(1,-1,.8,.8),'body_sleeve_wrist':(1,-1,.8,-.8,.7,.6)}
 # Every pose explicitly resets both body channels, to keep the captures independent.
 poses={name:values+(0,)*(6-len(values)) for name,values in poses.items()}
 ids=('ParamWristL','ParamWristR','ParamArmL','ParamArmR','ParamMotionDrive','ParamBreath')
 data={}
 for name,values in poses.items():
  for id,v in zip(ids,values):request(url,f'/api/param?id={id}&v={v}')
  request(url,'/api/step?n=1')
  p=json.loads(request(url,'/api/params.json'));current={item['id']:item['value'] for item in p['params']}
  if any(abs(current[id]-value)>0.001 for id,value in zip(ids,values)):
   raise RuntimeError(f'parameter not applied: {name}')
  data[name]=np.array(Image.open(BytesIO(request(url,'/api/frame.png?s=100'))).convert('RGBA'))
 return poses,data


def compare(candidate,out):
 root=(ROOT/'build').resolve();candidate=Path(candidate).resolve();out=Path(out);target=out.resolve()
 if root not in candidate.parents or root not in target.parents:raise ValueError('candidate/output must be inside build')
 if target==candidate or candidate in target.parents or target in candidate.parents:raise ValueError('candidate and output must be separate')
 if not (candidate/'wrist_report.json').is_file():raise ValueError('not a wrist candidate')
 if out.exists() or out.is_symlink() or not out.parent.is_dir():raise ValueError('output must be a new directory')
 scales=(.35,.55,.8,1.0)
 with tempfile.TemporaryDirectory(prefix='wrist-compare-',dir=root) as tmp:
  tmp=Path(tmp);base=tmp/'base';torso.build(base);sampled=[]
  for i,model in enumerate((base,base,candidate)):
   proc,url=start(tmp/f'preview-{i}',model)
   try:
    capture=frames(url,scales)
    extra=sample(url) if i==2 else None
    sampled.append((capture,extra))
   finally:stop(proc)
  ref,repeat,trial=(x[0] for x in sampled);poses,images=sampled[2][1]
  changed={}
  for scale in scales:
   changed[str(scale)]={}
   for pose in ('neutral','outward','inward'):
    key=(scale,pose);a,b,c=(x[key] for x in (ref,repeat,trial))
    if a.shape!=b.shape or a.shape!=c.shape:raise ValueError('frame size mismatch')
    if np.any(a!=b):raise ValueError(f'baseline not repeatable at {key}')
    changed[str(scale)][pose]=int(np.any(a!=c,axis=2).sum())
  movement={name:int(np.any(images['neutral']!=img,axis=2).sum()) for name,img in images.items() if name!='neutral'}
  if any(v==0 for v in movement.values()):raise ValueError('wrist or combination pose made no visible change')
  report={'baseline_repeat':'equal in 12 tested frames','scale_pose_changed_pixels':changed,
          'pose_parameter_order':['ParamWristL','ParamWristR','ParamArmL','ParamArmR','ParamMotionDrive','ParamBreath'],
          'wrist_values':poses,'wrist_pose_changed_vs_neutral_0.55':movement,
          'scope':'same fixed sequence and selected poses only; no artistic acceptance'}
  out.mkdir()
  try:
   for name,arr in images.items():
    im=Image.fromarray(arr);im.save(out/f'{name}.png')
    for bg,color in (('light',(247,247,247,255)),('dark',(38,43,49,255))):
     c=Image.new('RGBA',im.size,color);c.alpha_composite(im)
     c.crop((170,320,393,400)).resize((1561,560)).convert('RGB').save(out/f'{name}_{bg}.png')
   (out/'metrics.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
   return report
  except BaseException:shutil.rmtree(out);raise

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('candidate');p.add_argument('output');a=p.parse_args()
 try:print(json.dumps(compare(a.candidate,a.output),ensure_ascii=False,indent=2))
 except (ValueError,OSError,RuntimeError) as e:print('wrist comparison:',e);return 1
 return 0
if __name__=='__main__':raise SystemExit(main())
