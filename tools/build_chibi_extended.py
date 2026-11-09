#!/usr/bin/env python3
"""Build an unapproved half-blink pupil study on the visual-review trial."""
import argparse,copy,json,shutil,sys
from pathlib import Path
from io import BytesIO
import numpy as np
from PIL import Image
import resvg_py
import build_chibi_visual_review as base
import build_chibi_underlay as torso
ROOT=Path(__file__).resolve().parents[1];ART=ROOT/'experiments/live2d_chibi_extended'

def raster(name):
 return np.array(Image.open(BytesIO(resvg_py.svg_to_bytes(svg_path=str(ART/name),width=215,height=114,skip_system_fonts=True))).convert('RGBA'))

def build(output):
 out=Path(output);base.build(out)
 try:
  f=out/'rig.json';r=json.loads(f.read_text(encoding='utf-8'));background=raster('iris_base.svg');detail=raster('iris_detail.svg')
  for side,xoff,w in (('l',0,100),('r',110,105)):
   Image.fromarray(background[:,xoff:xoff+w]).save(out/f'sprites/iris_{side}.png')
   Image.fromarray(detail[:,xoff:xoff+w]).save(out/f'sprites/iris_detail_{side}.png')
   iris=next(p for p in r['parts'] if p['id']==f'iris_{side}');p=copy.deepcopy(iris)
   p.update(id=f'iris_detail_{side}',file=f'sprites/iris_detail_{side}.png',layer=42);r['parts'].append(p)
   points=[{'c':c,'r':row,'dy':10} for row in range(2) for c in range(2)]
   r['deformers'].append({'id':f'mesh_iris_detail_{side}','part':p['id'],'cols':1,'rows':1,'param':f'ParamEye{side.upper()}Open',
    'keys':[{'v':0,'points':[]},{'v':.2,'points':[]},{'v':.5,'points':points},{'v':1,'points':[]}]})
  f.write_text(json.dumps(r,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
  p=out/'visual_review_report.json';prior=json.loads(p.read_text());prior['superseded_by_extended_report']=True;p.write_text(json.dumps(prior,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
  report={'sources':{n:torso.sha(ART/n) for n in ('iris_base.svg','iris_detail.svg')},'visual_acceptance':'not evaluated',
          'limitations':'pupil follows an experimental keyform; finger overlap and large-angle joints remain unresolved'}
  (out/'extended_report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');return report
 except BaseException:shutil.rmtree(out);raise

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('output',type=Path);a=p.parse_args()
 try:print(json.dumps(build(a.output),ensure_ascii=False,indent=2))
 except (ValueError,OSError,KeyError,StopIteration) as e:print('extended study:',e,file=sys.stderr);return 1
 return 0
if __name__=='__main__':raise SystemExit(main())
