#!/usr/bin/env python3
"""Regression checks for the visual-review trial; not visual approval."""
import json,sys,tempfile
from pathlib import Path
import numpy as np
from PIL import Image,ImageFilter
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'))
import build_chibi_visual_review as build
import build_chibi_underlay as torso
import capture_chibi_visual_matrix as matrix
from study_underpaint_sampling import start,stop,request
from capture_chibi_art_review import reset
from capture_chibi_refinement import setup
from capture_chibi_joint_art import image
import zrig_project

def main():
 (ROOT/'build').mkdir(exist_ok=True)
 originals={p:torso.sha(ROOT/p) for p in torso.EXPECTED}
 with tempfile.TemporaryDirectory(prefix='visual-review-test-',dir=ROOT/'build') as temp:
  tmp=Path(temp);model=tmp/'model';report=build.build(model)
  for target in (model,ROOT/'experiments/not-allowed'):
   try:build.build(target)
   except ValueError:pass
   else:raise AssertionError('unsafe output')
  link=tmp/'escape';link.symlink_to(ROOT/'experiments',target_is_directory=True)
  try:build.build(link/'no')
  except ValueError:pass
  else:raise AssertionError('symlink escape')
  rig=json.loads((model/'rig.json').read_text());parts={p['id']:p for p in rig['parts']}
  assert json.loads((model/'closure_report.json').read_text())['superseded_by_visual_review_report']
  for side in 'lr':
   a=np.array(Image.open(model/f'sprites/wrist_under_{side}.png').convert('RGBA'))[:,:,3]
   fore=Image.open(model/f'sprites/forearm_{side}.png').convert('RGBA').getchannel('A')
   cover=np.array(fore.filter(ImageFilter.MinFilter(build.INSET*2+1)))==255
   assert np.any(a) and not np.any((a>0)&~cover)
   assert parts['iris_'+side]['eyelid_travel']==-9
  for side in 'LR':
   for n in matrix.FINGERS:
    p=next(p for p in rig['params'] if p['id']==f'ParamFinger{side}{n}')
    assert abs(p['binds'][0]['scale'])==5
  cases=matrix.scenarios();assert len(cases)==48
  proc,url=start(tmp/'preview',model)
  try:
   setup(url);frames=[]
   for case in ('L_alternating','R_alternating','L_joint_mix_0','R_joint_mix_7','eye_x1_tilt-1_b0.85'):
    reset(url)
    for k,v in cases[case].items():request(url,f'/api/blink?v={v}' if k=='blink' else f'/api/param?id={k}&v={v}')
    request(url,'/api/step?n=3');frames.append(image(url))
   assert all(np.any(frames[0]!=x) for x in frames[1:])
  finally:stop(proc)
  archive=tmp/'model.zproj';manifest=zrig_project.create(model/'rig.json',archive);zrig_project.verify(archive);unpack=tmp/'unpacked';zrig_project.unpack(archive,unpack)
  frames=[]
  for i,src in enumerate((model,unpack)):
   proc,url=start(tmp/f'package-{i}',src)
   try:
    setup(url)
    for p in ('/api/param?id=ParamFingerRIndex&v=1','/api/param?id=ParamElbowR&v=-1','/api/param?id=ParamWristR&v=1','/api/blink?v=0.85','/api/step?n=5'):request(url,p)
    frames.append(image(url))
   finally:stop(proc)
  assert np.array_equal(*frames)
  assert report['visual_acceptance']=='not evaluated'
 assert originals=={p:torso.sha(ROOT/p) for p in torso.EXPECTED}
 print(f'美术复核候选技术检查：安全构建、腕补片范围、原摆幅、混合姿势及 {len(manifest["files"])} 文件工程包通过；不是视觉验收')
if __name__=='__main__':main()
