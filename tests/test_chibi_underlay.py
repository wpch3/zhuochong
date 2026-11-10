#!/usr/bin/env python3
"""Rebuild, project roundtrip, and exercise isolated C underlay candidate."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import numpy as np
from PIL import Image
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
import build_chibi_underlay as art
import compare_chibi_underlay as ab
import zrig_project
from study_underpaint_sampling import start,stop,frames


def main():
 (ROOT/'build').mkdir(exist_ok=True)
 before={p:art.sha(ROOT/p) for p in art.EXPECTED}
 with tempfile.TemporaryDirectory(prefix='chibi-underlay-test-',dir=ROOT/'build') as t:
  tmp=Path(t);candidate=tmp/'candidate';report=art.build(candidate)
  assert report['source_partition_neutral_equal'] and report['changed_body_pixels']>0
  try:art.build(candidate);raise AssertionError('overwrote output')
  except ValueError:pass
  try:art.build(ROOT/'experiments'/'forbidden-candidate');raise AssertionError('unsafe output')
  except ValueError:pass
  outside=tmp/'outside-link';outside.symlink_to(ROOT/'experiments',target_is_directory=True)
  try:art.build(outside/'forbidden');raise AssertionError('symlink escaped build')
  except ValueError:pass
  rig=json.loads((candidate/'rig.json').read_text());sprite_paths={p['file'] for p in rig['parts']}
  for p in sprite_paths-{'sprites/body.png'}:assert (candidate/p).read_bytes()==(art.DYNAMIC/p).read_bytes()
  # Verify source-resolution neutral composite; no extrapolation to C scales.
  orig=Image.open(art.ORIGINAL).convert('RGBA');combined=Image.open(candidate/'sprites/body.png').convert('RGBA')
  for side in 'lr':combined.alpha_composite(Image.open(candidate/f'sprites/arm_{side}.png').convert('RGBA'))
  assert np.array_equal(np.asarray(orig),np.asarray(combined))
  metrics=ab.compare(candidate,tmp/'comparison');assert metrics['candidate_changed_pixels']['1.0']['neutral']==0
  assert metrics['candidate_changed_pixels']['0.55']['neutral']>0
  try:ab.compare(candidate,tmp/'comparison');raise AssertionError('comparison overwrote output')
  except ValueError:pass
  archive=tmp/'trial.zproj';manifest=zrig_project.create(candidate/'rig.json',archive)
  assert len(manifest['files'])==12;zrig_project.verify(archive);unpacked=tmp/'unpacked';zrig_project.unpack(archive,unpacked)
  for f in manifest['files']:assert (candidate/f['path']).read_bytes()==(unpacked/f['path']).read_bytes()
  observations=[]
  for i,model in enumerate((candidate,unpacked)):
   proc,url=start(tmp/f'engine-{i}',model)
   try:
    observations.append(frames(url,(.55,)))
    if i==0:subprocess.run([sys.executable,str(ROOT/'tools/capture_dynamic_chibi.py'),'--port',url.rsplit(':',1)[-1],
                            '--out',str(tmp/'runtime-qa')],cwd=ROOT,check=True,timeout=60,stdout=subprocess.DEVNULL)
   finally:stop(proc)
  for key in observations[0]:assert np.array_equal(observations[0][key],observations[1][key]),f'project roundtrip C frame {key}'
 assert before=={p:art.sha(ROOT/p) for p in art.EXPECTED}
 print('Chibi 侧片：源不变、隔离构建、多比例 C 对照、动作物理及 12 文件工程往返 C 帧一致；视觉未验收')
if __name__=='__main__':main()
