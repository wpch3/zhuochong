#!/usr/bin/env python3
"""Make a separate visual-review trial from the closure candidate."""
import argparse,json,shutil,sys
from pathlib import Path
import numpy as np
from PIL import Image,ImageFilter
import build_chibi_closure as base
import build_chibi_binding_art as binding
import build_chibi_underlay as torso

ROOT=Path(__file__).resolve().parents[1]
ART=ROOT/'experiments/live2d_chibi_visual_review/hand_right.svg'
INSET=2

def build(output):
 out=Path(output);base.build(out)
 try:
  img=binding.render_piece(ART,'index',True)
  _,x=np.indices((512,480));img[x<240]=0
  if not np.any(img[:,:,3]):raise ValueError('empty right index')
  Image.fromarray(img).save(out/'sprites/finger_r_index.png')
  counts={}
  for side in 'lr':
   f=out/f'sprites/wrist_under_{side}.png';w=np.array(Image.open(f).convert('RGBA'))
   fore=Image.open(out/f'sprites/forearm_{side}.png').convert('RGBA').getchannel('A')
   # Conservative inset from the opaque cuff boundary; keep what was hidden.
   cover=np.array(fore.filter(ImageFilter.MinFilter(INSET*2+1)))==255
   w[~cover]=0
   if not np.any(w[:,:,3]):raise ValueError('empty wrist underpaint')
   Image.fromarray(w).save(f);counts[side]=int(np.count_nonzero(w[:,:,3]))
  prior=out/'closure_report.json';old=json.loads(prior.read_text());old['superseded_by_visual_review_report']=True;prior.write_text(json.dumps(old,ensure_ascii=False,indent=2)+'\n')
  report={'source':'closure_report.json (upstream state only)','right_hand_sha256':torso.sha(ART),'wrist_inset_pixels':INSET,'wrist_pixels':counts,
          'visual_acceptance':'not evaluated','limitations':'small joint angles only; mixed-pose samples do not exhaust the space'}
  (out/'visual_review_report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
  return report
 except BaseException:shutil.rmtree(out);raise

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('output',type=Path);a=p.parse_args()
 try:print(json.dumps(build(a.output),ensure_ascii=False,indent=2))
 except (ValueError,OSError,KeyError,StopIteration) as e:print('visual review:',e,file=sys.stderr);return 1
 return 0
if __name__=='__main__':raise SystemExit(main())
