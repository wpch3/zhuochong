#!/usr/bin/env python3
"""Capture deterministic real-C eye poses. Images are evidence, not visual approval."""
import argparse
import json
from pathlib import Path
import shutil
import tempfile
from PIL import Image
from study_underpaint_sampling import ROOT, start, stop, request
from capture_chibi_joint_art import image
from capture_chibi_refinement import setup, save_crop, changed


def collect(url):
 setup(url); shots={'neutral':image(url)}
 # Dense samples near closure reveal cross-fade artifacts rather than only endpoints.
 for v in (0,.25,.5,.75,.8,.85,.88,.9,.92,.95,.98,1):
  request(url,f'/api/blink?v={v}');request(url,'/api/step?n=3');shots[f'blink_{v}']=image(url)
 for side in 'LR':
  setup(url);request(url,f'/api/param?id=ParamEye{side}Open&v=0');request(url,'/api/step?n=3');shots[f'wink_{side}']=image(url)
  for kind in ('Smile','Pain'):
   for v in (.5,1):
    setup(url);request(url,f'/api/param?id=ParamEye{side}{kind}&v={v}');request(url,'/api/step?n=3');shots[f'{kind}_{side}_{v}']=image(url)
 for gaze in (-1,1):
  for blink in (0,.5,.92,1):
   setup(url);request(url,f'/api/param?id=ParamGazeX&v={gaze}');request(url,f'/api/blink?v={blink}');request(url,'/api/step?n=3');shots[f'gaze_{gaze}_blink_{blink}']=image(url)
 setup(url);request(url,'/api/action?id=head_test');request(url,'/api/blink?v=0.5')
 for i in range(4):
  request(url,'/api/step?n=20');shots[f'head_half_{i}']=image(url)
 # One C engine step per sample, closing and reopening at controlled increments.
 setup(url)
 for i in range(41):
  v=(i if i<=20 else 40-i)/20
  request(url,f'/api/blink?v={v}');request(url,'/api/step?n=1');shots[f'sweep_{i:02d}']=image(url)
 return shots


def collect_auto(url):
 # Sample a real autonomous blink, not a hand-authored easing curve.
 # Check every C step even while idle, so the closing phase is not skipped.
 setup(url);request(url,'/api/blink?on=1');request(url,'/api/blink?v=auto')
 frames=[];values=[];active=False;ready=False
 for _ in range(1600):
  request(url,'/api/step?n=1')
  blink=json.loads(request(url,'/api/info.json'))['blink']
  # Manual hold may have left the automatic state machine partway through a
  # blink. Wait for an actually open frame before recording the next cycle.
  if not ready:
   if blink<=0.001:ready=True;frames=[image(url)];values=[blink]
   continue
  if blink>0.001:active=True
  if active:
   frames.append(image(url));values.append(blink)
   if blink<=0.001:return frames,values
 raise RuntimeError('automatic blink did not finish within sampling budget')


def capture(candidate,output):
 root=(ROOT/'build').resolve();candidate=Path(candidate).resolve();out=Path(output);dest=out.resolve()
 if root not in candidate.parents or root not in dest.parents or dest==candidate or dest in candidate.parents or candidate in dest.parents:raise ValueError('paths must be separate and inside build')
 if out.exists() or out.is_symlink() or not out.parent.is_dir():raise ValueError('output must be new')
 if not (candidate/'eye_natural_report.json').is_file():raise ValueError('expected natural eye candidate')
 with tempfile.TemporaryDirectory(prefix='eye-natural-capture-',dir=root) as tmp:
  proc,url=start(Path(tmp)/'preview',candidate)
  try:
   shots=collect(url);auto_frames,auto_values=collect_auto(url)
  finally:stop(proc)
 out.mkdir()
 try:
  for name,arr in shots.items():
   if name.startswith('sweep_'):continue
   for bgname,bg in (('light',(247,247,247,255)),('dark',(38,43,49,255))):
    save_crop(arr,(375,320,640,410),1,out/f'{name}_{bgname}.png',bg)
  sequence=[]
  for i in range(41):
   frame=Image.fromarray(shots[f'sweep_{i:02d}']);canvas=Image.new('RGBA',frame.size,(247,247,247,255));canvas.alpha_composite(frame)
   sequence.append(canvas.crop((375,320,640,410)).convert('RGB'))
  sequence[0].save(out/'controlled_blink.gif',save_all=True,append_images=sequence[1:],duration=40,loop=0,optimize=True)
  sequence=[]
  for arr in auto_frames:
   frame=Image.fromarray(arr);canvas=Image.new('RGBA',frame.size,(247,247,247,255));canvas.alpha_composite(frame)
   sequence.append(canvas.crop((375,320,640,410)).convert('RGB'))
  # Deliberately slowed for inspection; auto_values retain the original sample order.
  sequence[0].save(out/'auto_blink_slow.gif',save_all=True,append_images=sequence[1:],duration=100,loop=0,optimize=True)
  (out/'auto_blink_values.json').write_text(json.dumps(auto_values,indent=2)+'\n',encoding='utf-8')
  Image.fromarray(shots['neutral']).save(out/'neutral_full.png')
  metrics={'half_blink':changed(shots['blink_0'],shots['blink_0.5']), 'closed_blink':changed(shots['blink_0'],shots['blink_1']),
           'wink_L':changed(shots['blink_0'],shots['wink_L']), 'wink_R':changed(shots['blink_0'],shots['wink_R']),
           'gaze_extremes':changed(shots['gaze_-1_blink_0'],shots['gaze_1_blink_0'])}
  (out/'metrics.json').write_text(json.dumps(metrics,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
  return metrics
 except BaseException:shutil.rmtree(out);raise


def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('candidate');p.add_argument('output');a=p.parse_args()
 try:print(json.dumps(capture(a.candidate,a.output),ensure_ascii=False,indent=2))
 except (ValueError,OSError,RuntimeError) as e:print('capture:',e,file=__import__('sys').stderr);return 1
 return 0
if __name__=='__main__':raise SystemExit(main())
