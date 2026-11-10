#!/usr/bin/env python3
"""Technical regression for the isolated closure study, not visual approval."""
import json,sys,tempfile
from pathlib import Path
import numpy as np
from PIL import Image
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'))
import build_chibi_closure as build
import build_chibi_underlay as torso
import capture_chibi_art_review as cap
from study_underpaint_sampling import start,stop,request
from capture_chibi_joint_art import image
from capture_chibi_refinement import setup
import zrig_project

def main():
 (ROOT/'build').mkdir(exist_ok=True)
 originals={p:torso.sha(ROOT/p) for p in torso.EXPECTED}
 with tempfile.TemporaryDirectory(prefix='closure-test-',dir=ROOT/'build') as temp:
  tmp=Path(temp);model=tmp/'model';report=build.build(model)
  for target in (model,ROOT/'experiments/not-allowed'):
   try:build.build(target)
   except ValueError:pass
   else:raise AssertionError('unsafe output')
  link=tmp/'escape';link.symlink_to(ROOT/'experiments',target_is_directory=True)
  try:build.build(link/'not-allowed')
  except ValueError:pass
  else:raise AssertionError('symlink escape')
  rig=json.loads((model/'rig.json').read_text());parts={p['id']:p for p in rig['parts']}
  read=lambda n:np.asarray(Image.open(model/f'sprites/{n}.png').convert('RGBA'))[:,:,3]
  for side in 'lr':
   arm,body,fore=read('arm_'+side),read('body'),read('forearm_'+side)
   for name,cover in [('wrist_under',fore==255),('shoulder_under',(arm==255)|(body==255)),('elbow_under',(arm==255)|(fore==255))]:
    alpha=read(name+'_'+side);assert np.any(alpha) and not np.any((alpha>0)&~cover),(name,side)
   assert parts['iris_'+side]['eyelid_travel']==-9
   assert 'eye_open_early_fade' not in parts['iris_'+side]['tags']
   for finger in ('little','ring','middle','index','thumb'):
    assert np.any(read('finger_'+side+'_'+finger))
    assert rig['groups'][f'finger_{side}_{finger}']['parent']=='wrist_'+side
  assert (build.ART/'hand_left.svg').read_text()!=(build.ART/'hand_right.svg').read_text()
  proc,url=start(tmp/'run',model)
  try:
   shots=cap.collect(url)
   for a,b in [('blink_0','blink_0.5'),('blink_0.5','blink_1'),('combined_-1','combined_1')]:assert np.any(shots[a]!=shots[b])
   for side in 'LR':
    for name in ('Little','Ring','Middle','Index','Thumb'):
     assert np.any(shots[f'finger_{side}_{name}_-1']!=shots[f'finger_{side}_{name}_1'])
    for joint in ('Arm','Elbow','Wrist'):
     assert np.any(shots[f'joint_{side}_{joint}_-1']!=shots[f'joint_{side}_{joint}_1'])
  finally:stop(proc)
  archive=tmp/'candidate.zproj';manifest=zrig_project.create(model/'rig.json',archive);zrig_project.verify(archive);unpack=tmp/'unpacked';zrig_project.unpack(archive,unpack)
  frames=[]
  for i,src in enumerate((model,unpack)):
   proc,url=start(tmp/f'package-{i}',src)
   try:
    setup(url)
    for p in ('/api/param?id=ParamFingerLIndex&v=1','/api/param?id=ParamElbowR&v=-1','/api/param?id=ParamGazeX&v=0.8','/api/blink?v=0.85','/api/step?n=5'):request(url,p)
    frames.append(image(url))
   finally:stop(proc)
  assert np.array_equal(*frames)
  assert report['visual_acceptance']=='not evaluated'
 assert originals=={p:torso.sha(ROOT/p) for p in torso.EXPECTED}
 print(f'独立修画候选技术检查通过：十指/关节响应、静态隐藏约束、安全路径和 {len(manifest["files"])} 文件工程包；非美术验收')
if __name__=='__main__':main()
