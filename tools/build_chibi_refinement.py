#!/usr/bin/env python3
"""Build an isolated Chibi art/rig refinement, never overwrite source models."""
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
import build_chibi_binding_art as binding
import build_chibi_lid_art as lid
import build_chibi_underlay as torso

ROOT=Path(__file__).resolve().parents[1]
ART=ROOT/'experiments/live2d_chibi_refinement'

def raster(name):
 return np.array(Image.open(BytesIO(resvg_py.svg_to_bytes(svg_path=str(ART/name),width=480,height=512,skip_system_fonts=True))).convert('RGBA'))

def build(output):
 out=Path(output);root=(ROOT/'build').resolve();target=out.resolve()
 if root not in target.parents or out.exists() or out.is_symlink() or not out.parent.is_dir():raise ValueError('output must be a fresh directory inside build')
 fingers={name:binding.render_piece(ART/'fingers.svg',name,True) for name in binding.FINGERS+('palm',)}
 mouth={name:binding.render_piece(ART/'mouth.svg',name) for name in binding.MOUTH}
 wrists=raster('wrist_underpaint.svg');shoulders=raster('shoulder_underpaint.svg');sides=raster('jacket_sides.svg')
 eyelids=np.array(Image.open(BytesIO(resvg_py.svg_to_bytes(svg_path=str(ART/'eyelids.svg'),width=215,height=114,skip_system_fonts=True))).convert('RGBA'))
 yy,xx=np.indices((512,480))
 with tempfile.TemporaryDirectory(prefix='refinement-base-',dir=root) as temp:
  temp=Path(temp);base=temp/'binding';eye=temp/'eye';binding.build(base);lid.build(eye)
  rig=json.loads((base/'rig.json').read_text(encoding='utf-8'));eye_rig=json.loads((eye/'rig.json').read_text(encoding='utf-8'))
  out.mkdir()
  try:
   shutil.copytree(base/'sprites',out/'sprites')
   for name in ('wrist_report.json','joint_report.json','binding_report.json'):
    inherited=json.loads((base/name).read_text(encoding='utf-8'))
    inherited['superseded_by_refinement_report']=True
    (out/name).write_text(json.dumps(inherited,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
   # Repaint the body continuation beneath the original partition.
   original=np.array(Image.open(torso.ORIGINAL).convert('RGBA'));covered=np.zeros((512,480),bool)
   for side in 'lr':covered |= np.array(Image.open(torso.DYNAMIC/f'sprites/arm_{side}.png').convert('RGBA'))[:,:,3]>0
   original[covered]=0;body_img=Image.fromarray(sides);body_img.alpha_composite(Image.fromarray(original));body_img.save(out/'sprites/body.png')
   for side in 'lr':
    mask=(xx<240) if side=='l' else (xx>=240)
    for name in binding.FINGERS:
     arr=fingers[name].copy();arr[~mask]=0;Image.fromarray(arr).save(out/f'sprites/finger_{side}_{name}.png')
    arr=fingers['palm'].copy();arr[~mask]=0;Image.fromarray(arr).save(out/f'sprites/hand_{side}.png')
    arr=wrists.copy();arr[~mask]=0;Image.fromarray(arr).save(out/f'sprites/wrist_under_{side}.png')
    # The cuff occludes the wrist and palm, rather than being painted over by them.
    forearm=next(p for p in rig['parts'] if p['id']=='forearm_'+side);forearm['layer']=21
    # Remove only the two small cut-line spikes extending past the cuff.
    cuff_path=out/forearm['file'];cuff=np.array(Image.open(cuff_path).convert('RGBA'))
    if side=='l':spike=((xx>=80)&(xx<=87)|(xx>=108)&(xx<=115))&(yy>0.52*xx+156)
    else:spike=((xx>=343)&(xx<=356)|(xx>=373)&(xx<=382))&(yy>376-0.46*xx)
    cuff[spike]=0;Image.fromarray(cuff).save(cuff_path)
    # Keep shoulder art covered by the opaque body/upper sleeve at rest.
    sleeve=np.array(Image.open(out/f'sprites/arm_{side}.png').convert('RGBA'))
    body=np.array(Image.open(out/'sprites/body.png').convert('RGBA'))
    arr=shoulders.copy();arr[~(mask&((sleeve[:,:,3]==255)|(body[:,:,3]==255)))]=0
    Image.fromarray(arr).save(out/f'sprites/shoulder_under_{side}.png')
   # One upper contour throughout: no superimposed old mouth line. Fade only
   # the interior and lower outline, not the one shared upper lip.
   rig['parts']=[p for p in rig['parts'] if p['id']!='mouth_rest']
   (out/'sprites/mouth_rest.png').unlink()
   param=next(p for p in rig['params'] if p['id']=='ParamMouthOpenY')
   param['binds']=[]
   for name in binding.MOUTH:
    Image.fromarray(mouth[name]).save(out/f'sprites/mouth_{name}.png')
    if name!='upper_lip':
     # Delay the lower outline, avoiding small double corners.
     param['binds'].append({'part':'mouth_'+name,'param':'alpha','scale':5,'offset':-2 if name=='lower_lip' else -1})
    else:
     upper=next(d for d in rig['deformers'] if d['id']=='mesh_mouth_upper_lip')
     upper['keys']=[{'v':0,'points':[]},{'v':1,'points':[{'c':c,'r':r,'dy':[7.5,-4.5,-8,-4.5,7.5][c]} for r in range(5) for c in range(5)]}]
   # Merge independently authored moving eyelids, aperture, and gaze groups.
   for side in 'lr':
    ids={f'eye_{side}_open',f'eye_{side}_closed',f'sclera_{side}',f'iris_{side}',f'aperture_{side}',f'lid_{side}'}
    rig['parts']=[p for p in rig['parts'] if p['id'] not in ids]
    for p in eye_rig['parts']:
     if p['id'] in ids:
      if p['id'] in (f'sclera_{side}',f'iris_{side}'):p['tags']=['eye_open']
      if p['id']==f'lid_{side}':p['eyelid_travel']=44
      rig['parts'].append(p);shutil.copyfile(eye/p['file'],out/p['file'])
    xoff,width=(0,100) if side=='l' else (110,105)
    Image.fromarray(eyelids[:,xoff:xoff+width]).save(out/f'sprites/lid_{side}.png')
    rig['groups']['iris_'+side]=eye_rig['groups']['iris_'+side]
    # Strip eye-base leftovers below the eyelid without touching the hairline.
    path=out/f'sprites/eye_{side}_open.png';arr=np.array(Image.open(path).convert('RGBA'))
    y,x=np.indices(arr.shape[:2]);remove=((y>=102)&((x>=20)&(x<=82) if side=='l' else (x>=24)&(x<=90)))
    if side=='l':remove |= (x>=86)&(x<=92)&(y>=65)&(y<=79)
    else:remove |= (x>=94)&(x<=104)&(y>=65)&(y<=79)
    arr[remove]=0;Image.fromarray(arr).save(path)
   rig['params'].append(next(p for p in eye_rig['params'] if p['id']=='ParamGazeX'))
   for side in 'lr':
    eye_param='ParamEye'+side.upper()+'Open'
    # Gently flatten the lash in the last quarter; it is not yet a proper closed-lid drawing.
    points=[{'c':c,'r':r,'dy':[-4,-1,1,2.5,3,2.5,1,-1,-4][c]} for r in range(5) for c in range(9)]
    rig['deformers'].append({'id':'mesh_lid_'+side,'part':'lid_'+side,'cols':8,'rows':4,'param':eye_param,
                             'keys':[{'v':0,'points':points},{'v':.25,'points':[]},{'v':1,'points':[]}]})
   (out/'rig.json').write_text(json.dumps(rig,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
   report={'art_sha256':{n:torso.sha(ART/n) for n in ('fingers.svg','mouth.svg','eyelids.svg','wrist_underpaint.svg','shoulder_underpaint.svg','jacket_sides.svg')},
           'source_trial_reports':'wrist_report.json, joint_report.json, binding_report.json record upstream state only',
           'visual_acceptance':'not evaluated','limitations':'redrawn eyes and mirrored hands; eye expression, mouth, joints and finger roots remain experimental'}
   (out/'refinement_report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
   return report
  except BaseException:shutil.rmtree(out);raise

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('output',type=Path);a=p.parse_args()
 try:print(json.dumps(build(a.output),ensure_ascii=False,indent=2))
 except (ValueError,OSError,KeyError,StopIteration) as e:print('refinement:',e,file=sys.stderr);return 1
 return 0
if __name__=='__main__':sys.exit(main())
