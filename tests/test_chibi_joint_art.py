#!/usr/bin/env python3
"""Regression for joint/eye experiments; no artistic acceptance implied."""
from io import BytesIO
import json
from pathlib import Path
import sys
import tempfile
import numpy as np
from PIL import Image
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'))
import build_chibi_joint_art as joint
import build_chibi_eye_art as eye
import build_chibi_wrists as wrist
import build_chibi_underlay as torso
import capture_chibi_joint_art as capture
import capture_chibi_eye_art as eye_capture
import zrig_project
from study_underpaint_sampling import request,start,stop

def main():
 (ROOT/'build').mkdir(exist_ok=True)
 before={p:torso.sha(ROOT/p) for p in torso.EXPECTED}
 face_before={name:torso.sha(torso.DYNAMIC/'sprites'/name) for name in eye.FACE_SOURCES}
 with tempfile.TemporaryDirectory(prefix='joint-test-',dir=ROOT/'build') as temp:
  t=Path(temp);prior=t/'prior';wrist.build(prior);candidate=t/'joint';report=joint.build(candidate)
  for func in (joint.build,eye.build):
   try:func(candidate);raise AssertionError('overwrote candidate')
   except ValueError:pass
   try:func(ROOT/'experiments'/'not-allowed');raise AssertionError('wrote outside build')
   except ValueError:pass
   link=t/'link'
   if not link.exists():link.symlink_to(ROOT/'experiments',target_is_directory=True)
   try:func(link/'not-allowed');raise AssertionError('symlink escape')
   except ValueError:pass
  rig=json.loads((candidate/'rig.json').read_text());assert len(rig['parts'])==21
  for side in 'lr':
   assert report['parts'][side]['hand_cleanup_pixels']>0
   assert report['parts'][side]['elbow_art_pixels']>0 and report['parts'][side]['shoulder_art_pixels']>0
   hand=np.array(Image.open(candidate/f'sprites/hand_{side}.png').convert('RGBA'))
   original=np.array(Image.open(prior/f'sprites/hand_{side}.png').convert('RGBA'))
   assert np.array_equal(hand[:,:,3],original[:,:,3])
   yy,xx=np.indices(hand.shape[:2]);d=yy-(.52*xx+156 if side=='l' else 376-.46*xx)
   span=(xx>=84)&(xx<=108) if side=='l' else (xx>=354)&(xx<=378)
   assert not np.any(np.any(hand!=original,axis=2)&~(span&(d>=0)&(d<=3)))
   elbow=Image.open(candidate/f'sprites/elbow_under_{side}.png').convert('RGBA')
   elbow.alpha_composite(Image.open(candidate/f'sprites/arm_{side}.png').convert('RGBA'))
   elbow.alpha_composite(Image.open(candidate/f'sprites/forearm_{side}.png').convert('RGBA'))
   assert np.array_equal(np.array(elbow),np.array(Image.open(prior/f'sprites/arm_{side}.png').convert('RGBA')))
   assert rig['groups']['wrist_'+side]['parent']=='elbow_'+side
   shoulder=np.array(Image.open(candidate/f'sprites/shoulder_under_{side}.png').convert('RGBA'))[:,:,3]>0
   old_arm=np.array(Image.open(prior/f'sprites/arm_{side}.png').convert('RGBA'))[:,:,3]
   body=np.array(Image.open(prior/'sprites/body.png').convert('RGBA'))[:,:,3]
   assert not np.any(shoulder&~((body==255)|(old_arm==255)))
  qa=capture.capture(candidate,t/'qa');assert all(qa['pose_changed_pixels_0.55'].values())
  for model,n in ((candidate,22),(t/'eye',28)):
   if n==28:
    eye_report=eye.build(model);assert eye_report['changes_neutral_likeness']
    eye_qa=eye_capture.capture(model,t/'eye-qa')
    assert eye_qa['states_changed_vs_center_at_1']['left']>0
    assert eye_qa['states_changed_vs_center_at_1']['closed']>0
    assert 'half_blink_changed_vs_right' in eye_qa
    r=json.loads((model/'rig.json').read_text());assert len(r['parts'])==27
    for side in 'lr':
     iris=next(x for x in r['parts'] if x['id']=='iris_'+side)
     assert iris['mask']=='aperture_'+side and 'eye_open' in iris['tags']
   archive=t/f'{n}.zproj';manifest=zrig_project.create(model/'rig.json',archive)
   assert len(manifest['files'])==n
   zrig_project.verify(archive);unpacked=t/f'unpacked-{n}';zrig_project.unpack(archive,unpacked)
   result=[]
   for i,m in enumerate((model,unpacked)):
    proc,url=start(t/f'run-{n}-{i}',m)
    try:
     captures=capture.pose_frames(url)
     if n==28:
      for val in (-1,0,1):
       request(url,f'/api/param?id=ParamGazeX&v={val}');request(url,'/api/step?n=1')
       captures[f'gaze{val}']=capture.image(url)
      assert np.any(captures['gaze-1']!=captures['gaze1'])
      request(url,'/api/blink?v=1');request(url,'/api/step?n=15');captures['blink_closed']=capture.image(url)
      assert np.any(captures['gaze1']!=captures['blink_closed'])
     result.append(captures)
    finally:stop(proc)
   for name in result[0]:assert np.array_equal(result[0][name],result[1][name]),f'roundtrip {n} {name}'
 assert before=={p:torso.sha(ROOT/p) for p in torso.EXPECTED}
 assert face_before=={name:torso.sha(torso.DYNAMIC/'sprites'/name) for name in eye.FACE_SOURCES}
 print('Chibi 肩肘腕/眼试验：安全构建、源/alpha 约束、C 动作、遮罩和两类项目包往返通过；不代表视觉验收')
if __name__=='__main__':main()
