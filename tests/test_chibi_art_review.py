#!/usr/bin/env python3
"""Technical checks for the isolated art candidate; not visual acceptance."""
import json
import shutil
from pathlib import Path
import sys
import tempfile
import numpy as np
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'))
import build_chibi_art_review as build
import build_chibi_eye_natural as natural
import build_chibi_underlay as torso
import capture_chibi_art_review as cap
import zrig_project
from capture_chibi_joint_art import image
from capture_chibi_refinement import setup,save_crop
from PIL import Image
from study_underpaint_sampling import start,stop,request


def main():
 (ROOT/'build').mkdir(exist_ok=True)
 originals={p:torso.sha(ROOT/p) for p in torso.EXPECTED}
 upstream=[ROOT/'experiments/live2d_chibi_eye_natural'/n for n in ('apertures.svg','eyelids.svg','closed_lids.svg','expression_lids.svg')]
 upstream+=list((ROOT/'experiments/live2d_chibi_refinement').glob('*.svg'))
 upstream_hash={p:torso.sha(p) for p in upstream}
 with tempfile.TemporaryDirectory(prefix='art-review-test-',dir=ROOT/'build') as temp:
  tmp=Path(temp);model=tmp/'model';report=build.build(model)
  for target in (model,ROOT/'experiments/not-allowed'):
   try:build.build(target)
   except ValueError:pass
   else:raise AssertionError('unsafe destination')
  link=tmp/'escape';link.symlink_to(ROOT/'experiments',target_is_directory=True)
  try:build.build(link/'not-allowed')
  except ValueError:pass
  else:raise AssertionError('symlink escape')
  rig=json.loads((model/'rig.json').read_text());parts={p['id']:p for p in rig['parts']}
  assert len(parts)==len(rig['parts'])==46
  assert json.loads((model/'eye_natural_report.json').read_text())['superseded_by_art_review_report']
  for side,pivot in [('l',[400,595]),('r',[621,595])]:
   assert rig['groups']['elbow_'+side]['pivot']==pivot
   assert rig['groups']['wrist_'+side]['parent']=='elbow_'+side
   elbow=np.asarray(Image.open(model/f'sprites/elbow_under_{side}.png').convert('RGBA'))[:,:,3]
   arm=np.asarray(Image.open(model/f'sprites/arm_{side}.png').convert('RGBA'))[:,:,3]
   assert np.any(elbow) and not np.any((elbow>0)&(arm!=255))
   assert 'eye_aperture_fast_close' in parts['aperture_'+side]['tags']
   assert parts['iris_'+side]['eyelid_travel']==-5 and 'eye_open_early_fade' not in parts['iris_'+side]['tags']
   lid=next(d for d in rig['deformers'] if d['id']=='mesh_lid_'+side)
   smile=next(d for d in rig['deformers'] if d['id']=='mesh_lid_smile_'+side)
   assert smile['part']=='lid_smile_'+side and smile['keys']==lid['keys'] and smile['param']==lid['param']
   for n in ('little','ring','middle','index','thumb'):assert rig['groups'][f'finger_{side}_{n}']['parent']=='wrist_'+side
  proc,url=start(tmp/'run',model)
  try:
   shots=cap.collect(url)
   for a,b in [('blink_0','blink_0.5'),('blink_0.5','blink_1'),('blink_0','wink_L'),('blink_0','wink_R'),('combined_-1','combined_1'),('Smile_L_0','Smile_L_1'),('loop_finger_test_00','loop_finger_test_11'),('loop_elbow_test_00','loop_elbow_test_11')]:assert np.any(shots[a]!=shots[b]),(a,b)
   for side in 'LR':
    for name in ('Little','Ring','Middle','Index','Thumb'):
     assert np.any(shots[f'finger_{side}_{name}_-1']!=shots[f'finger_{side}_{name}_1']),(side,name)
    for joint in ('Arm','Elbow','Wrist'):
     assert np.any(shots[f'joint_{side}_{joint}_-1']!=shots[f'joint_{side}_{joint}_1']),(side,joint)
  finally:stop(proc)
  # Candidate currently has no named expressions. Use temporary test-only
  # expressions to compare their effect to the same direct eye parameters.
  fixture=tmp/'expression-fixture';shutil.copytree(model,fixture);path=fixture/'rig.json';obj=json.loads(path.read_text())
  cases=[('close',f'ParamEye{s}Open',v) for s in 'LR' for v in (0,.15,.5)]
  cases += [('smile',f'ParamEye{s}Smile',v) for s in 'LR' for v in (.5,.85,1)]
  obj['expressions']=[{'id':f'e{i}','fade':0,'params':[{'id':param,'value':v,'mode':'set'}]} for i,(_,param,v) in enumerate(cases)]
  path.write_text(json.dumps(obj,ensure_ascii=False),encoding='utf-8')
  proc,url=start(tmp/'expr-run',fixture)
  try:
   setup(url)
   for i,(_,param,v) in enumerate(cases):
    request(url,'/api/expression?off=1');cap.reset(url);request(url,f'/api/param?id={param}&v={v}');request(url,'/api/step?n=5');manual=image(url)
    cap.reset(url);request(url,f'/api/expression?id=e{i}');request(url,'/api/step?n=5');expr=image(url)
    assert np.array_equal(manual,expr),(param,v)
  finally:stop(proc)
  # Golden screenshots from the previous candidate were rendered before the
  # new opt-in aperture tag existed. Its untagged rig must remain unchanged.
  old=tmp/'old-model';natural.build(old);proc,url=start(tmp/'old-run',old)
  try:
   setup(url)
   old_neutral=image(url)
   for x0,x1 in ((350,460),(560,670)):
    assert np.array_equal(old_neutral[550:640,x0:x1],shots['neutral'][550:640,x0:x1]),'neutral elbow seam changed'
   for v in (.5,.75,.8,.85,.88,.92,.95,1):
    request(url,f'/api/blink?v={v}');request(url,'/api/step?n=3')
    snap=tmp/'old.png';save_crop(image(url),(375,320,640,410),1,snap,(247,247,247,255))
    golden=ROOT/'experiments/live2d_chibi_eye_natural/qa_pose'/f'blink_{v}_light.png'
    assert np.array_equal(np.asarray(Image.open(snap)),np.asarray(Image.open(golden))),f'old rig changed at blink {v}'
  finally:stop(proc)
  archive=tmp/'art.zproj';manifest=zrig_project.create(model/'rig.json',archive);zrig_project.verify(archive);unpack=tmp/'unpacked';zrig_project.unpack(archive,unpack);results=[]
  for i,src in enumerate((model,unpack)):
   proc,url=start(tmp/f'package-{i}',src)
   try:
    setup(url)
    for p in ('/api/param?id=ParamFingerLIndex&v=1','/api/param?id=ParamElbowR&v=-1','/api/param?id=ParamGazeX&v=0.8','/api/blink?v=0.85','/api/step?n=5'):request(url,p)
    results.append(image(url))
   finally:stop(proc)
  assert np.array_equal(*results)
  assert report['visual_acceptance']=='not evaluated'
 assert originals=={p:torso.sha(ROOT/p) for p in torso.EXPECTED}
 assert upstream_hash=={p:torso.sha(p) for p in upstream}
 print(f'美术候选技术检查：安全构建、双眼与笑眼表达、十指和关节、{len(manifest["files"])} 文件项目包往返通过；未做美术验收')
if __name__=='__main__':main()
