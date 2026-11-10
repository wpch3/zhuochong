#!/usr/bin/env python3
"""Technical regression for a still-unapproved experimental pupil study."""
import json,sys,tempfile
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'))
import build_chibi_extended as build
import build_chibi_underlay as torso
import zrig_project
from study_underpaint_sampling import start,stop,request
from capture_chibi_joint_art import image
from capture_chibi_refinement import setup

def main():
 (ROOT/'build').mkdir(exist_ok=True)
 originals={p:torso.sha(ROOT/p) for p in torso.EXPECTED}
 with tempfile.TemporaryDirectory(prefix='extended-test-',dir=ROOT/'build') as temp:
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
  assert json.loads((model/'visual_review_report.json').read_text())['superseded_by_extended_report']
  for s in 'lr':
   a=parts['iris_'+s];b=parts['iris_detail_'+s]
   for key in ('pos','group','mask','eye_side','eyelid_travel','tags'):assert a[key]==b[key]
   d=next(d for d in rig['deformers'] if d['id']==f'mesh_iris_detail_{s}')
   assert d['param']==f'ParamEye{s.upper()}Open' and [k['v'] for k in d['keys']]==[0,.2,.5,1]
   assert all(p['dy']==10 for p in d['keys'][2]['points'])
  archive=tmp/'model.zproj';manifest=zrig_project.create(model/'rig.json',archive);zrig_project.verify(archive);unpack=tmp/'unpack';zrig_project.unpack(archive,unpack)
  frames=[]
  for i,src in enumerate((model,unpack)):
   proc,url=start(tmp/f'preview-{i}',src)
   try:
    setup(url);seq=[]
    for blink in (0,.5,.85,1,0):
     request(url,f'/api/blink?v={blink}');request(url,'/api/step?n=3');seq.append(image(url))
    assert np.array_equal(seq[0],seq[-1]) and not np.array_equal(seq[0],seq[1])
    frames.append(seq)
   finally:stop(proc)
  assert all(np.array_equal(a,b) for a,b in zip(*frames))
  assert report['visual_acceptance']=='not evaluated'
 assert originals=={p:torso.sha(ROOT/p) for p in torso.EXPECTED}
 print(f'瞳孔试验技术检查：安全构建、双眼分层、C 帧及 {len(manifest["files"])} 文件工程包往返通过；不构成视觉验收')
if __name__=='__main__':main()
