#!/usr/bin/env python3
"""Capture smile/pain and blink combinations from the actual C renderer."""
import argparse,json,shutil,tempfile
from pathlib import Path
from PIL import Image,ImageDraw
from capture_chibi_joint_art import image
from capture_chibi_refinement import setup,save_crop
from capture_chibi_art_review import reset
from capture_chibi_visual_matrix import verify_pose
from study_underpaint_sampling import ROOT,start,stop,request

def cases():
 out={}
 for side in 'LR':
  for expr in ('Smile','Pain'):
   for val in (.5,.85,1):
    for blink in (0,.25,.5,.75,.85,1):
     name=f'{side}_{expr}_{val}_{blink}';out[name]={f'ParamEye{side}{expr}':val,'blink':blink}
 return out

def capture(candidate,output,executable=None):
 root=(ROOT/'build').resolve();candidate=Path(candidate).resolve();out=Path(output);target=out.resolve()
 if root not in candidate.parents or root not in target.parents or target==candidate or candidate in target.parents or target in candidate.parents:raise ValueError('separate paths inside build required')
 if out.exists() or out.is_symlink() or not out.parent.is_dir():raise ValueError('output must be new')
 if not (candidate/'extended_report.json').is_file():raise ValueError('expected extended study')
 poses=cases();shots={}
 with tempfile.TemporaryDirectory(prefix='expression-blink-',dir=root) as tmp:
  proc,url=start(Path(tmp)/'preview',candidate,executable)
  try:
   setup(url)
   for name,params in poses.items():
    reset(url)
    for k,v in params.items():request(url,f'/api/blink?v={v}' if k=='blink' else f'/api/param?id={k}&v={v}')
    request(url,'/api/step?n=3');verify_pose(url,params);shots[name]=image(url)
  finally:stop(proc)
 out.mkdir()
 try:
  for name,arr in shots.items():
   save_crop(arr,(375,320,640,410),1,out/f'{name}.png',(247,247,247,255))
  for side in 'LR':
   for expr in ('Smile','Pain'):
    sheet=Image.new('RGB',(265*6,110*3),'white');draw=ImageDraw.Draw(sheet)
    for row,val in enumerate((.5,.85,1)):
     for col,blink in enumerate((0,.25,.5,.75,.85,1)):
      name=f'{side}_{expr}_{val}_{blink}';im=Image.open(out/f'{name}.png').resize((265,90))
      x=col*265;y=row*110;draw.text((x+2,y+2),name,fill='black');sheet.paste(im,(x,y+20))
    sheet.save(out/f'{side}_{expr}_sheet.png')
  (out/'poses.json').write_text(json.dumps(poses,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 except BaseException:shutil.rmtree(out);raise
 return len(shots)

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('candidate');p.add_argument('output');p.add_argument('--preview-executable',type=Path);a=p.parse_args()
 try:print('C expression + blink poses:',capture(a.candidate,a.output,a.preview_executable))
 except (ValueError,OSError,RuntimeError) as e:print('capture:',e,file=__import__('sys').stderr);return 1
 return 0
if __name__=='__main__':raise SystemExit(main())
