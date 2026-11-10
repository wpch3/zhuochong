#!/usr/bin/env python3
"""Capture eye artwork trial against a repeatable joint-only C baseline."""
import argparse
import json
from pathlib import Path
import shutil
import tempfile
import numpy as np
from PIL import Image
import build_chibi_joint_art as joint
from capture_chibi_joint_art import image
from study_underpaint_sampling import ROOT,start,stop,frames,request

def face(url):
 for p in ('/api/pause?on=1','/api/action?id=neutral','/api/param?all=1','/api/blink?v=0','/api/step?n=900','/api/scale?s=1'):request(url,p)
 result={}
 for name,gaze,blink,mouth in (('center',0,0,0),('left',-1,0,0),('right',1,0,0),('half_blink',1,.5,0),('late_blink',1,.92,0),('closed',1,1,0),('mouth_open',0,0,1)):
  for p in (f'/api/param?id=ParamGazeX&v={gaze}',f'/api/blink?v={blink}',f'/api/param?id=ParamMouthOpenY&v={mouth}','/api/step?n=15'):request(url,p)
  result[name]=image(url)
 return result

def capture(candidate,out):
 root=(ROOT/'build').resolve();candidate=Path(candidate).resolve();out=Path(out);target=out.resolve()
 if root not in candidate.parents or root not in target.parents:raise ValueError('paths must be inside build')
 if target==candidate or candidate in target.parents or target in candidate.parents:raise ValueError('paths must be separate')
 if not (candidate/'eye_report.json').is_file():raise ValueError('need an eye trial')
 if out.exists() or out.is_symlink() or not out.parent.is_dir():raise ValueError('output must be new')
 scales=(.35,.55,.8,1.)
 with tempfile.TemporaryDirectory(prefix='eye-qa-',dir=root) as t:
  t=Path(t);baseline=t/'base';joint.build(baseline);data=[]
  for i,model in enumerate((baseline,baseline,candidate)):
   proc,url=start(t/f'preview-{i}',model)
   try:data.append((frames(url,scales),face(url) if i==2 else None))
   finally:stop(proc)
  a,b,c=[x[0] for x in data];diff={}
  for s in scales:
   key=(s,'neutral')
   if not np.array_equal(a[key],b[key]):raise ValueError('baseline mismatch')
   diff[str(s)]=int(np.any(a[key]!=c[key],axis=2).sum())
  images=data[2][1];changes={k:int(np.any(v!=images['center'],axis=2).sum()) for k,v in images.items() if k!='center'}
  if not all(changes.values()):raise ValueError('eye state had no visible change')
  out.mkdir()
  try:
   for name,arr in images.items():
    im=Image.fromarray(arr)
    for bg,color in (('light',(247,247,247,255)),('dark',(38,43,49,255))):
     b=Image.new('RGBA',im.size,color);b.alpha_composite(im)
     b.crop((365,270,655,425)).resize((1160,620)).convert('RGB').save(out/f'{name}_{bg}.png')
   metrics={'baseline':'joint candidate, repeat neutral frames agree','neutral_changed_pixels':diff,
            'states_changed_vs_center_at_1':changes,'half_blink_changed_vs_right':int(np.any(images['half_blink']!=images['right'],axis=2).sum()),'limits':'new eye art intentionally changes appearance; no visual acceptance'}
   (out/'metrics.json').write_text(json.dumps(metrics,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');return metrics
  except BaseException:shutil.rmtree(out);raise

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('candidate');p.add_argument('output');a=p.parse_args()
 try:print(json.dumps(capture(a.candidate,a.output),ensure_ascii=False,indent=2))
 except (ValueError,OSError,RuntimeError) as e:print('eye capture:',e);return 1
 return 0
if __name__=='__main__':raise SystemExit(main())
