#!/usr/bin/env python3
"""Real-C capture of all 32 binary endpoint poses for each hand separately.

This does not claim all 1024 two-hand combinations or continuous poses.
"""
import argparse,itertools,json,shutil,tempfile
from pathlib import Path
from PIL import Image,ImageDraw
from capture_chibi_joint_art import image
from capture_chibi_refinement import setup,save_crop
from capture_chibi_art_review import reset
from capture_chibi_visual_matrix import verify_pose,FINGERS
from chibi_capture_provenance import snapshot,verify_unchanged
from study_underpaint_sampling import ROOT,start,stop,request

def capture(candidate,output,executable=None):
 candidate=Path(candidate).resolve();out=Path(output);dest=out.resolve();root=(ROOT/'build').resolve()
 if root not in candidate.parents or root not in dest.parents or dest==candidate or dest in candidate.parents or candidate in dest.parents:raise ValueError('separate paths inside build required')
 # FIX: Ensure output directory exists BEFORE starting the preview process
 out.mkdir(parents=True, exist_ok=True)
 if not (candidate/'closure_report.json').is_file():raise ValueError('expected closure study')
 binary=Path(executable).resolve() if executable else ROOT/'build/zhuochong_preview'
 provenance=snapshot(candidate,binary)
 shots={};poses={}
 with tempfile.TemporaryDirectory(prefix='finger-endpoints-',dir=root) as tmp:
  proc,url=start(Path(tmp)/'preview',candidate,executable)
  try:
   setup(url)
   for side in 'LR':
    for values in itertools.product((-1,1),repeat=5):
     bits=''.join('1' if v==1 else '0' for v in values);name=f'{side}_{bits}'
     params={f'ParamFinger{side}{n}':v for n,v in zip(FINGERS,values)};reset(url)
     for k,v in params.items():request(url,f'/api/param?id={k}&v={v}')
     request(url,'/api/step?n=3');verify_pose(url,params);shots[name]=image(url);poses[name]=params
  finally:stop(proc)
 after=verify_unchanged(provenance,candidate,binary)
 # out.mkdir() already done above
 try:
  for name,arr in shots.items():
   box=(325,625,410,710) if name[0]=='L' else (610,625,695,710)
   for label,bg in (('light', (247, 247, 247, 255)), ('dark', (38, 43, 49, 255))):save_crop(arr,box,1,out/f'{name}_{label}.png',bg)
  for side in 'LR':
   for label in ('light','dark'):
    # Each tile is an actual enlarged C crop; numbers encode -1 as 0 and +1 as 1.
    names=[n for n in shots if n.startswith(side+'_')];sheet=Image.new('RGB', (255*4,275*8), 'white');draw=ImageDraw.Draw(sheet)
    for i,name in enumerate(names):
     x=(i%4)*255;y=(i//4)*275;draw.text((x+4,y+3),name,fill='black');sheet.paste(Image.open(out/f'{name}_{label}.png'),(x,y+20))
    sheet.save(out/f'{side}_{label}_endpoints.png')
  (out/'poses.json').write_text(json.dumps({'order':list(FINGERS),'poses':poses,'provenance_before_capture':provenance,'provenance_after_capture':after},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 except BaseException as e:
  # FIX: Do NOT rmtree(out) because it is now the persistent tracking directory
  print(f'capture: failed during save phase but output directory preserved: {e}', file=__import__('sys').stderr)
  raise
 return len(shots)

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('candidate');p.add_argument('output');p.add_argument('--preview-executable',type=Path);a=p.parse_args()
 try:print('C single-hand endpoint poses:',capture(a.candidate,a.output,a.preview_executable))
 except (ValueError,OSError,RuntimeError) as e:print('capture:',e,file=__import__('sys').stderr);return 1
 return 0
if __name__=='__main__':raise SystemExit(main())
