#!/usr/bin/env python3
"""Reproducible isolated C comparisons for the shoulder/elbow/wrist trial.

A repeat baseline must agree before candidate differences are reported. These
captures do not establish visual approval or guarantee untested poses.
"""
import argparse
from io import BytesIO
import json
from pathlib import Path
import shutil
import tempfile
import numpy as np
from PIL import Image
import build_chibi_wrists as wrist
from study_underpaint_sampling import ROOT,start,stop,frames,request

IDS=('ParamElbowL','ParamElbowR','ParamWristL','ParamWristR','ParamArmL','ParamArmR','ParamMotionDrive','ParamBreath')
POSES={'neutral':(0,0,0,0,0,0,0,0),'elbow_l_min':(-1,0,0,0,0,0,0,0),
       'elbow_l_max':(1,0,0,0,0,0,0,0),'elbow_r_min':(0,-1,0,0,0,0,0,0),
       'elbow_r_max':(0,1,0,0,0,0,0,0),'elbows_min':(-1,-1,0,0,0,0,0,0),
       'elbows_mid':(.5,.5,0,0,0,0,0,0),'elbows_max':(1,1,0,0,0,0,0,0),
       'combined':(1,-1,1,-1,.8,-.8,.7,.6)}

def image(url):return np.array(Image.open(BytesIO(request(url,'/api/frame.png?s=100'))).convert('RGBA'))
def pose_frames(url):
 for path in ('/api/pause?on=1','/api/action?id=neutral','/api/param?all=1','/api/blink?v=0','/api/step?n=900','/api/scale?s=0.55'):request(url,path)
 result={}
 for name,values in POSES.items():
  for id,v in zip(IDS,values):request(url,f'/api/param?id={id}&v={v}')
  request(url,'/api/step?n=1');p=json.loads(request(url,'/api/params.json'));current={x['id']:x['value'] for x in p['params']}
  if any(abs(current[id]-v)>.001 for id,v in zip(IDS,values)):raise ValueError(f'pose not applied {name}')
  result[name]=image(url)
 return result

def action_frames(url):
 for p in ('/api/param?all=1','/api/action?id=elbow_test','/api/blink?v=0'):request(url,p)
 samples=[];images=[]
 for _ in range(9):
  request(url,'/api/step?n=15');params=json.loads(request(url,'/api/params.json'))['params']
  samples.append({x['id']:x['effective'] for x in params if x['id'] in IDS});images.append(image(url))
 for id in ('ParamElbowL','ParamElbowR','ParamWristL','ParamWristR'):
  if max(x[id] for x in samples)-min(x[id] for x in samples)<.2:raise ValueError('action channel did not move: '+id)
 return samples,images

def capture(candidate,out):
 root=(ROOT/'build').resolve();candidate=Path(candidate).resolve();out=Path(out);target=out.resolve()
 if root not in candidate.parents or root not in target.parents:raise ValueError('paths must be inside build')
 if target==candidate or candidate in target.parents or target in candidate.parents:raise ValueError('paths must be separate')
 if not (candidate/'joint_report.json').is_file() or (candidate/'eye_report.json').exists():raise ValueError('need an isolated joint trial, not eye trial')
 if out.exists() or out.is_symlink() or not out.parent.is_dir():raise ValueError('output must be new with existing parent')
 scales=(.35,.55,.8,1.0)
 with tempfile.TemporaryDirectory(prefix='joint-qa-',dir=root) as temp:
  t=Path(temp);base=t/'base';wrist.build(base);results=[]
  for i,model in enumerate((base,base,candidate)):
   proc,url=start(t/f'preview-{i}',model)
   try:
    f=frames(url,scales);poses=pose_frames(url) if i==2 else None
    action=action_frames(url) if i==2 else None;results.append((f,poses,action))
   finally:stop(proc)
  a,b,c=(v[0] for v in results);changed={}
  for s in scales:
   changed[str(s)]={}
   for name in ('neutral','outward','inward'):
    key=(s,name)
    if not np.array_equal(a[key],b[key]):raise ValueError(f'baseline mismatch: {key}')
    changed[str(s)][name]=int(np.any(a[key]!=c[key],axis=2).sum())
  poses=results[2][1];movement={k:int(np.any(v!=poses['neutral'],axis=2).sum()) for k,v in poses.items() if k!='neutral'}
  if not all(movement.values()):raise ValueError('at least one pose has no change')
  samples,action=results[2][2]
  out.mkdir()
  try:
   for name,arr in list(poses.items())+[(f'action_{i:02}',arr) for i,arr in enumerate(action)]:
    im=Image.fromarray(arr)
    for bg,color in (('light',(247,247,247,255)),('dark',(38,43,49,255))):
     b=Image.new('RGBA',im.size,color);b.alpha_composite(im)
     b.crop((155,255,410,405)).resize((1275,750)).convert('RGB').save(out/f'{name}_{bg}.png')
   report={'baseline':'prior wrist candidate, 12 fixed baseline frames identical','scale_pose_changed_pixels':changed,
           'pose_parameter_order':IDS,'poses':POSES,'pose_changed_pixels_0.55':movement,'action_samples':samples,
           'limits':'only fixed states, not a measure of artistic quality'}
   (out/'metrics.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
   return report
  except BaseException:shutil.rmtree(out);raise

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('candidate');p.add_argument('output');a=p.parse_args()
 try:print(json.dumps(capture(a.candidate,a.output),ensure_ascii=False,indent=2))
 except (ValueError,OSError,RuntimeError) as e:print('joint capture:',e);return 1
 return 0
if __name__=='__main__':raise SystemExit(main())
