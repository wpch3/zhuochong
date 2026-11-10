#!/usr/bin/env python3
"""Capture the eye, hand and joint review poses from the C renderer."""
import argparse
import json
from pathlib import Path
import shutil
import tempfile
from PIL import Image
from capture_chibi_joint_art import image
from capture_chibi_refinement import setup, save_crop, changed
from capture_chibi_eye_natural import collect_auto
from study_underpaint_sampling import ROOT,start,stop,request,frames


def reset(url):
 request(url,'/api/action?id=neutral');request(url,'/api/param?all=1');request(url,'/api/blink?v=0');request(url,'/api/step?n=3')

def collect(url):
 setup(url);shots={'neutral':image(url)}
 for v in (0,.5,.65,.75,.8,.85,.88,.9,.92,.95,.98,1):
  request(url,f'/api/blink?v={v}');request(url,'/api/step?n=3');shots[f'blink_{v}']=image(url)
 for side in 'LR':
  for kind in ('Smile','Pain'):
   for v in (0,.5,.75,.85,.9,1):
    reset(url);request(url,f'/api/param?id=ParamEye{side}{kind}&v={v}');request(url,'/api/step?n=3');shots[f'{kind}_{side}_{v}']=image(url)
  reset(url);request(url,f'/api/param?id=ParamEye{side}Open&v=0');request(url,'/api/step?n=3');shots[f'wink_{side}']=image(url)
 for v in (-1,0,1):
  reset(url)
  for side in 'LR':
   for name in ('Little','Ring','Middle','Index','Thumb'):
    request(url,f'/api/param?id=ParamFinger{side}{name}&v={v}')
   request(url,f'/api/param?id=ParamWrist{side}&v={v}')
   request(url,f'/api/param?id=ParamElbow{side}&v={v}')
   request(url,f'/api/param?id=ParamArm{side}&v={v}')
  request(url,'/api/step?n=3');shots[f'combined_{v}']=image(url)
  for side in 'LR':
   for name in ('Little','Ring','Middle','Index','Thumb'):
    reset(url);request(url,f'/api/param?id=ParamFinger{side}{name}&v={v}');request(url,'/api/step?n=3');shots[f'finger_{side}_{name}_{v}']=image(url)
 for side in 'LR':
  for joint in ('Arm','Elbow','Wrist'):
   for v in (-1,0,1):
    reset(url);request(url,f'/api/param?id=Param{joint}{side}&v={v}');request(url,'/api/step?n=3');shots[f'joint_{side}_{joint}_{v}']=image(url)
 for smile,blink in ((.5,.5),(.85,.75),(.85,.92),(1,.92)):
  reset(url);request(url,f'/api/param?id=ParamEyeLSmile&v={smile}');request(url,f'/api/blink?v={blink}');request(url,'/api/step?n=3');shots[f'smile_combo_{smile}_{blink}']=image(url)
 reset(url);request(url,'/api/action?id=head_test');request(url,'/api/param?id=ParamEyeLSmile&v=0.85');request(url,'/api/param?id=ParamEyeRSmile&v=0.85')
 for i in range(4):
  request(url,'/api/step?n=20');shots[f'head_smile_{i}']=image(url)
 for gaze in (-1,1):
  for blink in (.5,.85,.92):
   reset(url);request(url,f'/api/param?id=ParamGazeX&v={gaze}');request(url,f'/api/blink?v={blink}');request(url,'/api/step?n=3');shots[f'gaze_{gaze}_blink_{blink}']=image(url)
 for action in ('finger_test','elbow_test'):
  reset(url);request(url,f'/api/action?id={action}')
  for i in range(12):
   request(url,'/api/step?n=3');shots[f'loop_{action}_{i:02d}']=image(url)
 return shots


def capture(candidate,output,auto=False):
 root=(ROOT/'build').resolve();candidate=Path(candidate).resolve();out=Path(output);dest=out.resolve()
 if root not in candidate.parents or root not in dest.parents or dest==candidate or dest in candidate.parents or candidate in dest.parents:raise ValueError('paths must be separate and inside build')
 if out.exists() or out.is_symlink() or not out.parent.is_dir():raise ValueError('output must be new')
 if not (candidate/'art_review_report.json').is_file():raise ValueError('expected art review candidate')
 with tempfile.TemporaryDirectory(prefix='art-review-capture-',dir=root) as tmp:
  proc,url=start(Path(tmp)/'preview',candidate)
  try:
   shots=collect(url);multi=frames(url,(.35,.55,.8,1))
   auto_frames,auto_values=collect_auto(url) if auto else (None,None)
  finally:stop(proc)
 out.mkdir()
 try:
  for name,arr in shots.items():
   if name.startswith('loop_'):continue
   if name.startswith(('blink','Smile','Pain','wink','gaze','head_smile','smile_combo')):box=(375,320,640,410)
   elif name.startswith('finger_L'):box=(325,625,405,710)
   elif name.startswith('finger_R'):box=(620,625,700,710)
   elif name.startswith('joint_'):
    side,kind=name.split('_')[1:3]
    boxes={'L':{'Arm':(325,460,465,565),'Elbow':(350,550,460,640),'Wrist':(325,625,410,710)},
           'R':{'Arm':(555,460,695,565),'Elbow':(560,550,670,640),'Wrist':(610,625,695,710)}}
    box=boxes[side][kind]
   else:box=(285,465,740,755)
   for label,bg in (('light',(247,247,247,255)),('dark',(38,43,49,255))):
    save_crop(arr,box,1,out/f'{name}_{label}.png',bg)
  for action in ('finger_test','elbow_test'):
   sequence=[]
   for i in range(12):
    frame=Image.fromarray(shots[f'loop_{action}_{i:02d}']);canvas=Image.new('RGBA',frame.size,(38,43,49,255));canvas.alpha_composite(frame)
    sequence.append(canvas.crop((300,465,730,735)).convert('RGB'))
   sequence[0].save(out/f'{action}_slow.gif',save_all=True,append_images=sequence[1:],duration=150,loop=0,optimize=True)
  for (scale,pose),arr in multi.items():
   save_crop(arr,(300,465,730,735),scale,out/f'scale_{scale}_{pose}_dark.png',(38,43,49,255))
  if auto:
   sequence=[]
   for arr in auto_frames:
    frame=Image.fromarray(arr);canvas=Image.new('RGBA',frame.size,(247,247,247,255));canvas.alpha_composite(frame)
    sequence.append(canvas.crop((375,320,640,410)).convert('RGB'))
   sequence[0].save(out/'auto_blink_slow.gif',save_all=True,append_images=sequence[1:],duration=100,loop=0,optimize=True)
   (out/'auto_blink_values.json').write_text(json.dumps(auto_values,indent=2)+'\n',encoding='utf-8')
  Image.fromarray(shots['neutral']).save(out/'neutral_full.png')
  metrics={'half_blink':changed(shots['blink_0'],shots['blink_0.5']),'closed':changed(shots['blink_0'],shots['blink_1']),
           'combined':changed(shots['combined_-1'],shots['combined_1']),
           'finger_motion':{f'{s}{n}':changed(shots[f'finger_{s}_{n}_-1'],shots[f'finger_{s}_{n}_1']) for s in 'LR' for n in ('Little','Ring','Middle','Index','Thumb')}}
  (out/'metrics.json').write_text(json.dumps(metrics,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
  return metrics
 except BaseException:shutil.rmtree(out);raise


def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('candidate');p.add_argument('output');p.add_argument('--auto',action='store_true',help='also sample a full real automatic blink (can take minutes)');a=p.parse_args()
 try:print(json.dumps(capture(a.candidate,a.output,a.auto),ensure_ascii=False,indent=2))
 except (ValueError,OSError,RuntimeError) as e:print('capture:',e,file=__import__('sys').stderr);return 1
 return 0
if __name__=='__main__':raise SystemExit(main())
