#!/usr/bin/env python3
"""Capture explicit mixed poses using the actual C preview, for human review.

Each pose is reset and its exact parameter values are recorded. A sampled
matrix is not an exhaustive test or an automated aesthetic judgment.
"""
import argparse,itertools,json,shutil,tempfile
from pathlib import Path
from PIL import Image
from capture_chibi_joint_art import image
from capture_chibi_refinement import setup,save_crop
from capture_chibi_art_review import reset
from chibi_capture_provenance import snapshot,verify_unchanged
from study_underpaint_sampling import ROOT,start,stop,request

FINGERS=('Little','Ring','Middle','Index','Thumb')

def verify_pose(url,params):
 current={p['id']:p['value'] for p in json.loads(request(url,'/api/params.json'))['params']}
 for key,value in params.items():
  if key=='blink':
   actual=json.loads(request(url,'/api/info.json'))['blink_manual']
  else:actual=current[key]
  if actual is None or abs(actual-value)>.001:raise ValueError(f'pose did not apply: {key}={value}, got {actual}')

def scenarios():
 out={}
 for side in 'LR':
  for k,values in {'neutral':(0,0,0,0,0),'alternating':(-1,1,-1,1,-1),'alternating_reverse':(1,-1,1,-1,1),
                   'index_spread':(0,0,-1,1,0),'index_close':(0,0,1,-1,0),
                   'thumb_spread':(0,0,0,0,1),'thumb_close':(0,0,0,0,-1)}.items():
   out[f'{side}_{k}']={f'ParamFinger{side}{n}':v for n,v in zip(FINGERS,values)}
  for j,(arm,elbow,wrist) in enumerate(itertools.product((-1,1),repeat=3)):
   out[f'{side}_joint_mix_{j}']={f'ParamArm{side}':arm,f'ParamElbow{side}':elbow,f'ParamWrist{side}':wrist,
     **{f'ParamFinger{side}{n}':v for n,v in zip(FINGERS,(1,-1,1,-1,1))}}
 for x in (-1,1):
  for y in (-1,1):
   for b in (.5,.75,.85):out[f'eye_x{x}_tilt{y}_b{b}']={'ParamGazeX':x,'ParamHeadTilt':y,'blink':b}
 for side in 'LR':
  for b in (.5,.75,.85):out[f'{side}_smile_b{b}']={f'ParamEye{side}Smile':.85,'blink':b,'ParamGazeX':1 if side=='L' else -1}
 return out

def capture(candidate,output,executable=None):
 candidate=Path(candidate).resolve();out=Path(output);dest=out.resolve();root=(ROOT/'build').resolve()
 if root not in candidate.parents or root not in dest.parents or dest==candidate or dest in candidate.parents or candidate in dest.parents:raise ValueError('separate paths inside build required')
 if out.exists() or out.is_symlink() or not out.parent.is_dir():raise ValueError('output must be new')
 if not (candidate/'closure_report.json').exists():raise ValueError('expected closure candidate')
 binary=Path(executable).resolve() if executable else ROOT/'build/zhuochong_preview'
 provenance=snapshot(candidate,binary)
 cases=scenarios();shots={};sweep=[];sweep_values=[]
 with tempfile.TemporaryDirectory(prefix='visual-matrix-',dir=root) as tmp:
  proc,url=start(Path(tmp)/'preview',candidate,executable)
  try:
   setup(url)
   for name,params in cases.items():
    reset(url)
    for k,v in params.items():request(url,f'/api/blink?v={v}' if k=='blink' else f'/api/param?id={k}&v={v}')
    request(url,'/api/step?n=3');verify_pose(url,params);shots[name]=image(url)
   # Sample an interpolated, reversible mixed pose, not an engine action.
   reset(url)
   for i in list(range(11))+list(range(9,0,-1)):
    v=round(-1+i*.2,3);params={}
    for side in 'LR':
     params.update({f'ParamArm{side}':v,f'ParamElbow{side}':-v,f'ParamWrist{side}':v})
     params.update({f'ParamFinger{side}{n}':v*(1 if j%2 else -1) for j,n in enumerate(FINGERS)})
    for k,val in params.items():request(url,f'/api/param?id={k}&v={val}')
    request(url,'/api/step?n=3');verify_pose(url,params);sweep.append(image(url));sweep_values.append(params)
  finally:stop(proc)
 after=verify_unchanged(provenance,candidate,binary)
 out.mkdir()
 try:
  for name,arr in shots.items():
   if name.startswith('eye_') or '_smile_' in name:box=(375,320,640,410)
   elif name[0]=='L':box=(325,625,410,710) if 'joint' not in name else (325,460,465,710)
   else:box=(610,625,695,710) if 'joint' not in name else (555,460,695,710)
   for label,bg in (('light',(247,247,247,255)),('dark',(38,43,49,255))):save_crop(arr,box,1,out/f'{name}_{label}.png',bg)
  for label,bg in (('light',(247,247,247,255)),('dark',(38,43,49,255))):
   sequence=[]
   for arr in sweep:
    frame=Image.fromarray(arr);canvas=Image.new('RGBA',frame.size,bg);canvas.alpha_composite(frame)
    sequence.append(canvas.crop((300,460,730,715)).convert('RGB'))
   sequence[0].save(out/f'mixed_sweep_{label}.gif',save_all=True,append_images=sequence[1:],duration=140,loop=0,optimize=True)
  (out/'poses.json').write_text(json.dumps({'fixed':cases,'mixed_sweep':sweep_values,'provenance_before_capture':provenance,'provenance_after_capture':after},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 except BaseException:shutil.rmtree(out);raise
 return len(cases)

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('candidate');p.add_argument('output');p.add_argument('--preview-executable',type=Path);a=p.parse_args()
 try:print('C frames captured:',capture(a.candidate,a.output,a.preview_executable))
 except (ValueError,OSError,RuntimeError) as e:print('capture:',e,file=__import__('sys').stderr);return 1
 return 0
if __name__=='__main__':raise SystemExit(main())
