#!/usr/bin/env python3
"""Natural-eye build, C frame and package checks; never a beauty verdict."""
import json
import shutil
from pathlib import Path
import sys
import tempfile
import numpy as np
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'))
import build_chibi_eye_natural as natural
import build_chibi_underlay as torso
import capture_chibi_eye_natural as cap
import zrig_project
from capture_chibi_joint_art import image
from study_underpaint_sampling import start,stop,request


def main():
 (ROOT/'build').mkdir(exist_ok=True)
 before={p:torso.sha(ROOT/p) for p in torso.EXPECTED}
 with tempfile.TemporaryDirectory(prefix='natural-test-',dir=ROOT/'build') as temp:
  tmp=Path(temp);model=tmp/'model';report=natural.build(model)
  for bad in (model,ROOT/'experiments/not-allowed'):
   try:natural.build(bad)
   except ValueError:pass
   else:raise AssertionError('unsafe output')
  link=tmp/'escape';link.symlink_to(ROOT/'experiments',target_is_directory=True)
  try:natural.build(link/'not-allowed')
  except ValueError:pass
  else:raise AssertionError('symlink escape')
  rig=json.loads((model/'rig.json').read_text());ids=[p['id'] for p in rig['parts']]
  assert len(ids)==len(set(ids))==46
  assert not any(p['id'] in ('ParamEyeLOpen','ParamEyeROpen') for p in rig['params'])
  for side in 'lr':
   for kind in ('closed','smile','pain'):assert f'lid_{kind}_{side}' in ids
   iris=next(p for p in rig['parts'] if p['id']=='iris_'+side)
   assert iris['mask']=='aperture_'+side and 'eye_open_early_fade' in iris['tags']
   assert 'eye_open_early_fade' in next(p for p in rig['parts'] if p['id']=='sclera_'+side)['tags']
   assert 'eye_open_pose_fade' in next(p for p in rig['parts'] if p['id']=='lid_'+side)['tags']
   assert next(p for p in rig['parts'] if p['id']=='aperture_'+side)['eyelid_travel']==-5
  proc,url=start(tmp/'run',model)
  try:
   shots=cap.collect(url)
   for a,b in [('blink_0','blink_0.5'),('blink_0.5','blink_1'),('blink_0','wink_L'),('blink_0','wink_R'),('gaze_-1_blink_0','gaze_1_blink_0'),('head_half_0','head_half_1')]:assert np.any(shots[a]!=shots[b]),(a,b)
   # Closed/smile/pain line must actually be drawn on each side, not merely a change caused by iris removal.
   for side,x0,x1 in [('L',390,490),('R',525,630)]:
    for name in (f'wink_{side}',f'Smile_{side}_1',f'Pain_{side}_1'):
     crop=shots[name][365:397,x0:x1,:]; assert ((crop[:,:,0]<100)&(crop[:,:,1]<100)&(crop[:,:,2]<100)&(crop[:,:,3]>200)).sum()>20,name
  finally:stop(proc)
  # The isolated candidate has no installed expressions. Add a synthetic one only
  # in a temporary copy, and compare it to equivalent manual eye parameters.
  fixture=tmp/'expression-fixture';shutil.copytree(model,fixture)
  path=fixture/'rig.json';obj=json.loads(path.read_text())
  obj['expressions']=[{'id':f'close_{i}','fade':0,'params':[{'id':f'ParamEye{s}Open','value':v,'mode':'set'} for s in 'LR']} for i,v in enumerate((0,.08,.5))]
  path.write_text(json.dumps(obj,ensure_ascii=False),encoding='utf-8')
  proc,url=start(tmp/'expr-run',fixture)
  try:
   for i,v in enumerate((0,.08,.5)):
    request(url,'/api/expression?off=1');cap.setup(url)
    for s in 'LR':request(url,f'/api/param?id=ParamEye{s}Open&v={v}')
    request(url,'/api/step?n=5');manual=image(url)
    cap.setup(url);request(url,f'/api/expression?id=close_{i}');request(url,'/api/step?n=5');expression=image(url)
    assert np.array_equal(manual,expression),f'expression mismatch at {v}'
    request(url,'/api/expression?off=1');cap.setup(url);request(url,f'/api/blink?v={1-v}');request(url,'/api/step?n=5');blink=image(url)
    assert np.array_equal(manual,blink),f'blink mismatch at {v}'
  finally:stop(proc)
  archive=tmp/'model.zproj';manifest=zrig_project.create(model/'rig.json',archive);zrig_project.verify(archive);unpack=tmp/'unpacked';zrig_project.unpack(archive,unpack)
  results=[]
  for i,src in enumerate((model,unpack)):
   proc,url=start(tmp/f'roundtrip-{i}',src)
   try:
    cap.setup(url)
    for path in ('/api/param?id=ParamFingerLIndex&v=1','/api/param?id=ParamArmR&v=-1','/api/param?id=ParamGazeX&v=0.8','/api/blink?v=0.92','/api/step?n=15'):request(url,path)
    results.append(image(url))
   finally:stop(proc)
  assert np.array_equal(*results)
  assert report['visual_acceptance']=='not evaluated'
 assert before=={p:torso.sha(ROOT/p) for p in torso.EXPECTED}
 print(f'自然眼试验：安全、双眼/单眼/表情参数、组合及 {len(manifest["files"])} 文件项目包 C 帧往返通过；不代表美术验收')
if __name__=='__main__':main()
