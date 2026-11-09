#!/usr/bin/env python3
"""Combined C rig and project round-trip regression; not visual acceptance."""
import json
from pathlib import Path
import sys
import tempfile
import numpy as np
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'))
import build_chibi_refinement as refine
import build_chibi_underlay as torso
import capture_chibi_refinement as capture
import zrig_project
from study_underpaint_sampling import start,stop,request
from capture_chibi_joint_art import image

def main():
 (ROOT/'build').mkdir(exist_ok=True)
 before={p:torso.sha(ROOT/p) for p in torso.EXPECTED}
 with tempfile.TemporaryDirectory(prefix='refine-test-',dir=ROOT/'build') as tmp:
  tmp=Path(tmp);model=tmp/'model';report=refine.build(model)
  for bad in (model,ROOT/'experiments/not-allowed'):
   try:refine.build(bad)
   except ValueError:pass
   else:raise AssertionError('unsafe output')
  link=tmp/'escape';link.symlink_to(ROOT/'experiments',target_is_directory=True)
  try:refine.build(link/'not-allowed')
  except ValueError:pass
  else:raise AssertionError('symlink escape')
  rig=json.loads((model/'rig.json').read_text());ids={p['id'] for p in rig['parts']}
  assert len(rig['parts'])==40 and 'mouth_rest' not in ids and 'mouth_upper_lip' in ids
  assert len([p for p in rig['params'] if p['id'] in ('ParamEyeLOpen','ParamEyeROpen')])==0 # engine built-ins
  for side in 'lr':
   assert rig['groups']['wrist_'+side]['parent']=='elbow_'+side
   assert next(p for p in rig['parts'] if p['id']=='iris_'+side)['mask']=='aperture_'+side
   assert next(p for p in rig['parts'] if p['id']=='lid_'+side)['eyelid_travel']==44
  proc,url=start(tmp/'run',model)
  try:
   shots=capture.collect(url)
   capture.setup(url);rest=image(url)
   answer=json.loads(request(url,'/api/viseme?v=A&w=1'));request(url,'/api/step?n=3');voiced=image(url)
   assert answer['open']>0.9 and np.any(rest!=voiced), 'A viseme must move the mouth'
   request(url,'/api/viseme?v=off')
   for side in 'LR':
    for finger in ('Little','Ring','Middle','Index','Thumb'):
     assert np.any(shots['ParamFinger'+side+finger]!=shots['neutral'])
   for a,b in [('mouth_0','mouth_0.1'),('mouth_0.1','mouth_1'),('blink_0','blink_0.5'),('blink_0.5','blink_1'),('blink_0','wink_left'),('gaze_-1','gaze_1'),('loop_0','loop_1'),('combined_-1','combined_1')]:
    assert np.any(shots[a]!=shots[b]),(a,b)
  finally:stop(proc)
  archive=tmp/'model.zproj';manifest=zrig_project.create(model/'rig.json',archive);zrig_project.verify(archive)
  unpack=tmp/'unpacked';zrig_project.unpack(archive,unpack);results=[]
  for i,src in enumerate((model,unpack)):
   proc,url=start(tmp/f'roundtrip-{i}',src)
   try:
    capture.setup(url)
    for path in ('/api/param?id=ParamFingerLIndex&v=1','/api/param?id=ParamArmR&v=-1',
                 '/api/param?id=ParamMouthOpenY&v=0.25','/api/param?id=ParamGazeX&v=0.8',
                 '/api/blink?v=0.5','/api/step?n=15'):request(url,path)
    results.append(image(url))
   finally:stop(proc)
  assert np.array_equal(*results)
  assert report['visual_acceptance']=='not evaluated'
  assert json.loads((model/'binding_report.json').read_text())['superseded_by_refinement_report']
 assert before=={p:torso.sha(ROOT/p) for p in torso.EXPECTED}
 print(f'Chibi 合并试验：安全、十指、口眼、组合和 {len(manifest["files"])} 文件项目包 C 帧往返通过；不是美术验收')
if __name__=='__main__':main()
