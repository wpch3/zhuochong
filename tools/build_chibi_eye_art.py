#!/usr/bin/env python3
"""Build a separate redrawn eye-aperture trial; never overwrite original art.

This intentionally changes the eyes at rest and is not an approved likeness.
Other facial parts remain the old flattened pieces.
"""
import argparse
from io import BytesIO
import json
from pathlib import Path
import shutil
import sys
import tempfile
import numpy as np
from PIL import Image
import resvg_py
import build_chibi_joint_art as joint
import build_chibi_underlay as torso
from build_dynamic_chibi import bind,parameter
ROOT=Path(__file__).resolve().parents[1];ART=joint.ART
FACE_SOURCES={'eye_l_open.png':'c240f152c4d74b63de287be6df0e379e2d53924e92dbb6f14e3b6b9eed17053b',
              'eye_r_open.png':'746c30f1bfbcec6e9379f25be109792bdc7000e4e72cda62cb759cc2a8ccdcdc',
              'eye_l_closed.png':'ba4f17903a47b2543ec76580c8c5b34962a1a042dbb5b84856c762a86e9f872f',
              'eye_r_closed.png':'7d61179a60c7cfa7930eea2845a11d95d6fe19f55b9f5ded5ca8eec0dfa66021',
              'mouth_rest.png':'fafe8da00ea71ab45c037f9d581283615f69c500c935c60247e1022a4147cffd',
              'mouth_speak.png':'7696881e61cb522d41cab572c41c4e95d600671bc33bb1764bef6d0be6acb4fe'}

def raster(name):
 return np.array(Image.open(BytesIO(resvg_py.svg_to_bytes(svg_path=str(ART/name),width=215,height=114,skip_system_fonts=True))).convert('RGBA'))

def build(output):
 out=Path(output);root=(ROOT/'build').resolve();resolved=out.resolve()
 if root not in resolved.parents:raise ValueError('output must be inside build')
 if out.exists() or out.is_symlink() or not out.parent.is_dir():raise ValueError('output must be a new directory with existing parent')
 for name,h in FACE_SOURCES.items():
  if torso.sha(torso.DYNAMIC/'sprites'/name)!=h:raise ValueError(f'source face artwork changed: {name}; manual review required')
 apertures=raster('eye_apertures.svg');irises=raster('iris_redraw.svg')
 with tempfile.TemporaryDirectory(prefix='eye-source-',dir=root) as t:
  base=Path(t)/'base';joint.build(base);rig=json.loads((base/'rig.json').read_text(encoding='utf-8'))
  out.mkdir()
  try:
   shutil.copytree(base/'sprites',out/'sprites')
   for side,xoff,width in (('l',0,100),('r',110,105)):
    p=out/f'sprites/eye_{side}_open.png';eye=np.array(Image.open(p).convert('RGBA'));y,_=np.indices((114,width))
    white=apertures[:,xoff:xoff+width].copy();selected=(white[:,:,3]>128)&(y>=64)
    if not selected.any():raise ValueError('empty eye aperture')
    eye[selected]=0;iris=irises[:,xoff:xoff+width].copy();white[y<64]=0
    mask=apertures[:,xoff:xoff+width].copy();mask[:,:,:3]=255
    for name,arr in ((f'eye_{side}_open',eye),(f'iris_{side}',iris),(f'sclera_{side}',white),(f'aperture_{side}',mask)):
     Image.fromarray(arr).save(out/f'sprites/{name}.png')
    pos=[390 if side=='l' else 525,286];rig['groups']['iris_'+side]={'pivot':pos,'parent':'head'}
    next(p for p in rig['parts'] if p['id']=='eye_'+side+'_open')['layer']=42
    next(p for p in rig['parts'] if p['id']=='eye_'+side+'_closed')['layer']=43
    rig['parts'] += [
     {'id':'sclera_'+side,'file':f'sprites/sclera_{side}.png','group':'head','pos':pos,'anchor':[0,0],'layer':40,'tags':['eye_open'],'eye_side':side},
     {'id':'aperture_'+side,'file':f'sprites/aperture_{side}.png','group':'head','pos':pos,'anchor':[0,0],'layer':40,'mask_only':True},
     {'id':'iris_'+side,'file':f'sprites/iris_{side}.png','group':'iris_'+side,'pos':pos,'anchor':[0,0],'layer':41,'tags':['eye_open'],'eye_side':side,'mask':'aperture_'+side}]
   rig['params'].append(parameter('ParamGazeX','眼球横向试验',-1,1,0,[bind('iris_l','dx',3),bind('iris_r','dx',3)]))
   (out/'rig.json').write_text(json.dumps(rig,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
   for report in ('joint_report.json','wrist_report.json'):shutil.copyfile(base/report,out/report)
   report={'source_face_sha256':FACE_SOURCES,'art_sha256':{n:torso.sha(ART/n) for n in ('eye_apertures.svg','iris_redraw.svg')},
           'changes_neutral_likeness':True,'limitations':'flat redrawn eye, lash/hair still attached, blink uses old frame crossfade; not approved'}
   (out/'eye_report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
   return report
  except BaseException:shutil.rmtree(out);raise

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('output',type=Path);a=p.parse_args()
 try:print(json.dumps(build(a.output),ensure_ascii=False,indent=2))
 except (ValueError,OSError,KeyError,StopIteration) as e:print('eye trial:',e,file=sys.stderr);return 1
 return 0
if __name__=='__main__':sys.exit(main())
