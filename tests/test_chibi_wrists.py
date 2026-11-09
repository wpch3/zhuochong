#!/usr/bin/env python3
"""Chibi wrist provenance, project, fixed pose and actual C action tests."""
import json
from pathlib import Path
import sys
import tempfile
import numpy as np
from PIL import Image
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
import build_chibi_wrists as wrists
import build_chibi_underlay as torso
import compare_chibi_wrists as ab
import zrig_project
from study_underpaint_sampling import start,stop,request


def main():
 (ROOT/'build').mkdir(exist_ok=True)
 before={p:torso.sha(ROOT/p) for p in torso.EXPECTED};art_before=torso.sha(wrists.SVG)
 with tempfile.TemporaryDirectory(prefix='wrist-test-',dir=ROOT/'build') as t:
  tmp=Path(t);out=tmp/'candidate';report=wrists.build(out)
  try:wrists.build(out);raise AssertionError('overwrote candidate')
  except ValueError:pass
  try:wrists.build(ROOT/'experiments'/'not-allowed');raise AssertionError('outside build')
  except ValueError:pass
  link=tmp/'link';link.symlink_to(ROOT/'experiments',target_is_directory=True)
  try:wrists.build(link/'not-allowed');raise AssertionError('symlink escaped')
  except ValueError:pass
  rig=json.loads((out/'rig.json').read_text());assert len(rig['parts'])==15
  for side in 'lr':
   assert report['parts'][side]['neutral_arm_rgba_equal'] and report['parts'][side]['hidden_skin_pixels']>0
   sleeve=Image.open(out/f'sprites/arm_{side}.png').convert('RGBA')
   hand=Image.open(out/f'sprites/hand_{side}.png').convert('RGBA')
   hidden=Image.open(out/f'sprites/wrist_under_{side}.png').convert('RGBA')
   assert not np.any((np.asarray(hidden)[:,:,3]>0)&(np.asarray(sleeve)[:,:,3]!=255))
   composed=hidden.copy();composed.alpha_composite(sleeve);composed.alpha_composite(hand)
   assert np.array_equal(np.asarray(composed),np.asarray(Image.open(torso.DYNAMIC/f'sprites/arm_{side}.png').convert('RGBA')))
   assert rig['groups']['wrist_'+side]['parent']=='shoulder_'+side
  comparison=ab.compare(out,tmp/'qa')
  assert comparison['scale_pose_changed_pixels']['1.0']['neutral']==0
  assert comparison['scale_pose_changed_pixels']['0.55']['neutral']>0
  assert all(value>0 for value in comparison['wrist_pose_changed_vs_neutral_0.55'].values())
  try:ab.compare(out,tmp/'qa');raise AssertionError('overwrote QA')
  except ValueError:pass
  z=tmp/'study.zproj';manifest=zrig_project.create(out/'rig.json',z);assert len(manifest['files'])==16
  zrig_project.verify(z);unpacked=tmp/'unpacked';zrig_project.unpack(z,unpacked)
  for f in manifest['files']:assert (unpacked/f['path']).read_bytes()==(out/f['path']).read_bytes()
  runs=[]
  for i,model in enumerate((out,unpacked)):
   proc,url=start(tmp/f'preview-{i}',model)
   try:
    poses,imgs=ab.sample(url);runs.append(imgs)
    for path in ('/api/param?all=1','/api/action?id=wrist_test','/api/blink?v=0'):request(url,path)
    values=[]
    for n in (1,15,15,15,15):
     request(url,f'/api/step?n={n}')
     params=json.loads(request(url,'/api/params.json'))
     values.append(next(p['effective'] for p in params['params'] if p['id']=='ParamWristL'))
    assert max(values)-min(values)>.25, f'wrist action did not animate: {values}'
   finally:stop(proc)
  for pose in runs[0]:assert np.array_equal(runs[0][pose],runs[1][pose]),f'roundtrip C mismatch {pose}'
 assert before=={p:torso.sha(ROOT/p) for p in torso.EXPECTED} and art_before==torso.sha(wrists.SVG)
 print('手腕试验：隔离重建、RGBA 对照、多比例 C 与左右/组合动作、16 文件项目往返通过；视觉待验收')
if __name__=='__main__':main()
