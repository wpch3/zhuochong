#!/usr/bin/env python3
"""Render neutral accessory-excluded C-engine frames and registered source comparisons."""
from __future__ import annotations
import hashlib,json,subprocess
from pathlib import Path
import numpy as np
from PIL import Image,ImageDraw,ImageFont
STUDY=Path(__file__).resolve().parent; OUT=STUDY/'chibi_arm_rig_candidate_2026-11-03_wip'; REPO=STUDY.parents[3]; EXE=Path('/tmp/chibi_candidate_renderer'); FONT=ImageFont.load_default(); SIZE=(848,1360); OFFSET=(140,68); BG=np.array([128,128,128],dtype=np.float64)
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def composite(im):
 a=np.asarray(im.convert('RGBA')).astype(np.float64);al=a[:,:,3:4]/255.;return a[:,:,:3]*al+BG*(1-al)
def checker(size,tile=12):
 w,h=size;im=Image.new('RGB',size,(239,238,243));d=ImageDraw.Draw(im)
 for y in range(0,h,tile):
  for x in range(0,w,tile):
   if (x//tile+y//tile)%2==0:d.rectangle((x,y,x+tile-1,y+tile-1),fill=(216,215,223))
 return im
def panel(im,label,size,scale=1.0):
 v=im.convert('RGBA').resize((round(im.width*scale),round(im.height*scale)),Image.Resampling.LANCZOS);bg=checker(v.size);bg.paste(v,(0,0),v.getchannel('A'));p=Image.new('RGB',size,(248,247,249));x=(size[0]-v.width)//2;y=24+(size[1]-24-v.height)//2;p.paste(bg,(x,y));ImageDraw.Draw(p).text((5,5),label,fill=(30,30,38),font=FONT);return p
def board(path,title,subtitle,panels,cols,pw,ph):
 gap,head=9,48;rows=(len(panels)+cols-1)//cols;o=Image.new('RGB',(gap+cols*(pw+gap),head+gap+rows*(ph+gap)),(248,247,249));d=ImageDraw.Draw(o);d.text((gap,5),title,fill=(30,30,38),font=FONT);d.text((gap,23),subtitle,fill=(76,74,82),font=FONT)
 for i,p in enumerate(panels):o.paste(p,(gap+(i%cols)*(pw+gap),head+gap+(i//cols)*(ph+gap)))
 o.save(path)
def render(style,path):
 args=[str(EXE),str(OUT/'rig_candidate_wip.json'),str(OUT),str(path),style,'0','0','0','none','0.02','0','1'];r=subprocess.run(args,cwd=REPO,text=True,capture_output=True)
 if r.returncode:raise RuntimeError(r.stdout+'\n'+r.stderr)
 log=r.stdout.strip();want=f"styles=({1 if style=='small' else 0},{1 if style=='mitten' else 0})"
 if want not in log or 'active_action=idle' not in log or 'ambient=0 core_hidden=1' not in log:raise RuntimeError(log)
 im=Image.open(path).convert('RGBA')
 if im.size!=SIZE:raise RuntimeError(f'bad output size {im.size}')
 return im.copy(),log
def metrics(src,cand,roi=None):
 a=np.asarray(src.convert('RGBA')).astype(np.int16);b=np.asarray(cand.convert('RGBA')).astype(np.int16)
 if roi:
  x0,y0,x1,y1=roi;a=a[y0:y1,x0:x1];b=b[y0:y1,x0:x1]
 ac=composite(Image.fromarray(a.astype(np.uint8)));bc=composite(Image.fromarray(b.astype(np.uint8)));d=np.abs(ac-bc);ad=np.abs(a[:,:,3]-b[:,:,3]);return {'changed_pixels_max_rgb_gt_8':int((d.max(axis=2)>8).sum()),'rgb_mae_all_channels_gray_composited':round(float(d.mean()),6),'alpha_changed_pixels_gt_8':int((ad>8).sum()),'roi_xyxy':list(roi) if roi else [0,0,SIZE[0],SIZE[1]]}
def main():
 srcpart=Image.open(REPO/'characters/xiaoxun/forms/chibi/sprites/body_full.png').convert('RGBA');source=Image.new('RGBA',SIZE,(0,0,0,0));source.alpha_composite(srcpart,OFFSET);source.save(OUT/'candidate_c_engine_registered_source_canvas_wip.png')
 outputs={};logs={}
 for style in ('small','mitten'):
  im,log=render(style,OUT/f'candidate_c_engine_neutral_core_{style}_wip.png');outputs[style]=im;logs[style]=log
 panels=[]
 for style in ('small','mitten'):
  candidate=outputs[style];over=Image.blend(source,candidate,.5)
  s=composite(source);c=composite(candidate);diff=np.abs(s-c).max(axis=2)>32;heat=np.zeros((SIZE[1],SIZE[0],3),dtype=np.uint8);heat[:]=np.array([128,128,128],dtype=np.uint8);heat[diff]=[235,55,75];heatimg=Image.fromarray(heat,'RGB')
  panels.extend([panel(source,'registered body_full source',(190,320),.22),panel(candidate,f'C core {style}',(190,320),.22),panel(over,f'50% source / C {style}',(190,320),.22),panel(heatimg,f'RGB diff >32 · {style}',(190,320),.22)])
 board(OUT/'candidate_c_engine_neutral_core_source_comparison_review_board_wip.png','C ENGINE NEUTRAL CORE / SOURCE COMPARISON · WIP','Accessory parts hidden; neutral pose; gray-composited RGB threshold map is diagnostic, not an approval score.',panels,4,190,320)
 hand_panels=[];roi_stats={}
 for side,box in (('left',(183,914,272,1006)),('right',(575,914,664,1006))):
  hand_panels.append(panel(source.crop(box),f'{side} · registered source',(230,240),2.0))
  roi_stats[side]={}
  for style in ('small','mitten'):
   hand_panels.append(panel(outputs[style].crop(box),f'{side} · core {style}',(230,240),2.0));roi_stats[side][style]=metrics(source,outputs[style],box)
 board(OUT/'candidate_c_engine_neutral_wrist_source_comparison_review_board_wip.png','C ENGINE NEUTRAL WRIST / CUFF SOURCE CROPS · WIP','2× registered ROI crops; source, small, and mitten are paired by side. No hidden-wrist or safety claim.',hand_panels,3,230,240)
 face=(205,390,650,675);face_panels=[]
 for style in ('small','mitten'):
  face_panels.extend([panel(source.crop(face), 'registered source · face',(320,270),.70),panel(outputs[style].crop(face),f'C core {style} · face',(320,270),.70)])
 board(OUT/'candidate_c_engine_neutral_core_face_source_detail_board_wip.png','C ENGINE NEUTRAL FACE / SOURCE DETAIL · WIP','Same source pixels and neutral C frames; close review aid only.',face_panels,4,320,270)
 rois={'face_eyes':(205,390,650,675),'hair_head':(180,75,665,480),'torso_arms':(190,620,665,1010),'skirt_legs':(210,980,640,1340)}
 allmetrics={style:{'fullframe':metrics(source,outputs[style]),'roi':{k:metrics(source,outputs[style],v) for k,v in rois.items()}} for style in ('small','mitten')}
 result={'status':'isolated QA WIP; descriptive source comparison only','source':{'path':'characters/xiaoxun/forms/chibi/sprites/body_full.png','sha256':sha(REPO/'characters/xiaoxun/forms/chibi/sprites/body_full.png'),'registered_offset_848x1360':list(OFFSET)},'candidate_rig_sha256':sha(OUT/'rig_candidate_wip.json'),'render_conditions':{'style_one_hot':True,'wrist_shoulder_elbow_deg':[0,0,0],'active_action':'idle','ambient':0,'tick_sec':0.02,'frame_scale':1.0,'hidden_part_ids':['acc_ear_cat_l','acc_ear_cat_r','acc_tail_cat_relaxed','acc_tail_cat_up','acc_tail_cat_puff','acc_tail_cat_tuck']},'c_engine_logs':logs,'metrics':allmetrics,'wrist_roi_metrics':roi_stats,'limitations':['gray-composited threshold statistics are not calibrated fidelity gates','small visible hand uses registered exact-source cutouts; hidden wrist continuation is absent','mitten pixels remain unapproved AI WIP','visible eye, cuff, body and contour residuals need source/art review','no motion, occlusion or production acceptance implied']}
 (OUT/'candidate_c_engine_neutral_source_comparison_metrics_wip.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
 print('Rendered neutral accessory-excluded source comparisons; boards and metrics written.')
if __name__=='__main__':main()
