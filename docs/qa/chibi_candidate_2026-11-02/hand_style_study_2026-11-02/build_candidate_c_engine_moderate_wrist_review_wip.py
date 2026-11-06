#!/usr/bin/env python3
"""Render close source/mitten wrist crops at moderate angles; diagnostic only."""
from __future__ import annotations
import hashlib,json,subprocess,tempfile
from pathlib import Path
from PIL import Image,ImageDraw,ImageFont
STUDY=Path(__file__).resolve().parent
OUT=STUDY/'chibi_arm_rig_candidate_2026-11-03_wip'
REPO=STUDY.parents[3]
SRC=REPO/'src'
EXE=Path(tempfile.gettempdir())/'chibi_candidate_renderer'
FONT=ImageFont.load_default()
ANGLES=list(range(-30,31,5))
CANVAS=(848,1360)
def registered_rois():
 manifest=json.loads((STUDY/'source_crop_manifest.json').read_text(encoding='utf-8'))
 body_w,body_h=manifest['body_full_size']
 offset=((CANVAS[0]-body_w)//2,CANVAS[1]-body_h)
 rois={}
 for side,record in manifest['source_crops'].items():
  x0,y0,x1,y1=record['body_full_roi_xyxy_exclusive']
  rois[side]=(x0+offset[0],y0+offset[1],x1+offset[0],y1+offset[1])
 return rois
ROIS=registered_rois()
def checker(size,tile=12):
 w,h=size;im=Image.new('RGB',size,(239,238,243));d=ImageDraw.Draw(im)
 for y in range(0,h,tile):
  for x in range(0,w,tile):
   if (x//tile+y//tile)%2==0:d.rectangle((x,y,x+tile-1,y+tile-1),fill=(216,215,223))
 return im
def compile_renderer():
 subprocess.run(['cc','-std=c11','-O2','-pthread',f'-I{SRC/"core"}',str(STUDY/'render_candidate_c_engine_preview_wip.c'),*map(str,sorted((SRC/'core').glob('*.c'))),'-lm','-pthread','-ldl','-o',str(EXE)],cwd=REPO,check=True)
def render(style,angle,path):
 args=[str(EXE),str(OUT/'rig_candidate_wip.json'),str(OUT),str(path),style,str(angle),'0','0','none','0.02','0','1']
 p=subprocess.run(args,cwd=REPO,text=True,capture_output=True)
 if p.returncode:raise RuntimeError(p.stdout+'\n'+p.stderr)
 log=p.stdout.strip();expected=f"styles=({1 if style=='small' else 0},{1 if style=='mitten' else 0})"
 if expected not in log or 'active_action=idle' not in log or 'ambient=0 core_hidden=1' not in log:raise RuntimeError(log)
 im=Image.open(path).convert('RGBA')
 if im.size!=(848,1360) or im.getchannel('A').getbbox() is None:raise RuntimeError('invalid C frame')
 return im.copy(),log,hashlib.sha256(path.read_bytes()).hexdigest()
def crop_panel(im,angle,size=(740,414)):
 crops=[]
 for side,box in ROIS.items():
  crop=im.crop(box).resize((356,368),Image.Resampling.NEAREST)
  bg=checker(crop.size);bg.paste(crop,(0,0),crop.getchannel('A'));crops.append((side,bg))
 p=Image.new('RGB',size,(248,247,249));d=ImageDraw.Draw(p)
 d.text((5,4),f'wrist {angle:+d}° · registered 89×92 ROIs · 4× nearest',fill=(30,30,38),font=FONT)
 for i,(side,crop) in enumerate(crops):
  x=8+i*368;y=25;p.paste(crop,(x,y));d.text((x,y+370),side,fill=(30,30,38),font=FONT)
 return p
def make_board(style,panels):
 cols=3;pw,ph=740,414;gap,head=8,48;rows=(len(panels)+cols-1)//cols
 out=Image.new('RGB',(gap+cols*(pw+gap),head+gap+rows*(ph+gap)),(248,247,249));d=ImageDraw.Draw(out)
 d.text((gap,5),f'C ENGINE · {style.upper()} MODERATE WRIST CLOSE REVIEW · WIP',fill=(30,30,38),font=FONT)
 d.text((gap,23),'−30°…+30° in 5° samples; each tile shows both registered wrists. Visual diagnostic only; not a safe-range or acceptance test.',fill=(76,74,82),font=FONT)
 for i,p in enumerate(panels):out.paste(p,(gap+(i%cols)*(pw+gap),head+gap+(i//cols)*(ph+gap)))
 path=OUT/f'candidate_c_engine_moderate_wrist_{style}_review_board_wip.png';out.save(path);return path

def main():
 compile_renderer()
 results={'status':'isolated diagnostic only; no angle safety or art acceptance','candidate_rig_sha256':hashlib.sha256((OUT/'rig_candidate_wip.json').read_bytes()).hexdigest(),'angles_deg':ANGLES,'render_conditions':{'shoulder_elbow_deg':[0,0],'action':'idle','ambient':0,'tick_sec':0.02,'frame_scale':1.0,'separated_ear_tail_parts_hidden':True},'rois_xyxy':ROIS,'styles':{}}
 with tempfile.TemporaryDirectory(prefix='chibi_wrist_detail_') as td:
  tmp=Path(td)
  for style in ('small','mitten'):
   panels=[];records=[]
   for angle in ANGLES:
    im,log,digest=render(style,angle,tmp/f'{style}_{angle:+03d}.png')
    panels.append(crop_panel(im,angle));records.append({'angle_deg':angle,'sha256':digest,'log':log})
   board=make_board(style,panels)
   results['styles'][style]={'review_board':board.name,'samples':records,'limitations':['pixel positions move normally under rotation; visual review, not an automated gap gate','trial24 mitten remains unapproved AI WIP' if style=='mitten' else 'exact source hand pixels stop at the source cuff; no hidden-wrist pixels exist']}
 path=OUT/'candidate_c_engine_moderate_wrist_review_metrics_wip.json';path.write_text(json.dumps(results,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 print('Rendered 26 isolated C frames across ±30° at 5° intervals; moderate wrist detail boards written.')
if __name__=='__main__':main()
