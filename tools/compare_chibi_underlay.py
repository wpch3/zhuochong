#!/usr/bin/env python3
"""Compare fresh C previews for a Chibi underlay trial at specified fixed poses.

Starts three private temporary previews (baseline twice, candidate once) and
refuses to report candidate deltas if the two baseline runs differ. Tested
frames are not a guarantee for other poses/scales or a visual acceptance.
"""
import argparse
import json
from pathlib import Path
import tempfile
import numpy as np
from PIL import Image
from study_underpaint_sampling import ROOT,start,stop,frames


def compare(candidate,out):
 candidate=Path(candidate).resolve();out=Path(out);root=(ROOT/'build').resolve()
 if root not in candidate.parents or root not in out.resolve().parents:raise ValueError('candidate and output must be in build')
 if candidate == out.resolve() or candidate in out.resolve().parents or out.resolve() in candidate.parents:
  raise ValueError('candidate and output must be separate')
 if not (candidate/'underlay_report.json').is_file():raise ValueError('not an underlay candidate')
 if out.exists() or out.is_symlink():raise ValueError('output exists')
 if not out.parent.is_dir():raise ValueError('output parent missing')
 scales=(.35,.55,.8,1.0)
 with tempfile.TemporaryDirectory(prefix='chibi-underlay-compare-',dir=root) as tmp:
  tmp=Path(tmp);captures=[]
  for i,study in enumerate((None,None,candidate)):
   p,url=start(tmp/f'preview-{i}',study)
   try:captures.append(frames(url,scales))
   finally:stop(p)
  ref,repeat,trial=captures;result={}
  for scale in scales:
   result[str(scale)]={}
   for pose in ('neutral','outward','inward'):
    key=(scale,pose);a,b,c=(x[key] for x in (ref,repeat,trial))
    if a.shape!=b.shape or a.shape!=c.shape:raise ValueError('C frame size mismatch')
    repeat_count=int(np.any(a!=b,axis=2).sum())
    if repeat_count:raise ValueError(f'baseline repeat differs: {scale} {pose} ({repeat_count})')
    result[str(scale)][pose]=int(np.any(a!=c,axis=2).sum())
  out.mkdir()
  try:
   for pose in ('neutral','outward','inward'):
    for name,arr in (('baseline',ref[(.55,pose)]),('candidate',trial[(.55,pose)])):
     im=Image.fromarray(arr);im.save(out/f'{pose}_{name}.png')
     for bg,color in (('light',(247,247,247,255)),('dark',(38,43,49,255))):
      canvas=Image.new('RGBA',im.size,color);canvas.alpha_composite(im)
      canvas.crop((160,240,410,400)).resize((1250,800)).convert('RGB').save(out/f'{pose}_{name}_{bg}.png')
   report={'scales':list(scales),'poses':{'neutral':0,'outward':1,'inward':-1},
           'baseline_repeat_differences':'zero in all tested frames',
           'candidate_changed_pixels':result,'scope':'fixed C frames, not a visual acceptance'}
   (out/'metrics.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
   return report
  except BaseException:
   import shutil;shutil.rmtree(out);raise

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('candidate');p.add_argument('output');a=p.parse_args()
 try:print(json.dumps(compare(a.candidate,a.output),ensure_ascii=False,indent=2))
 except (OSError,ValueError,RuntimeError) as e:print('comparison failed:',e);return 1
 return 0
if __name__=='__main__':raise SystemExit(main())
