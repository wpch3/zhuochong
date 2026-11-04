#!/usr/bin/env python3
"""WIP5 inferred hair backfill: long uninterrupted sheets without exposed local tips; never production."""
from pathlib import Path
import json, math
import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFilter
BASE=Path(__file__).resolve().parent; ROOT=Path(__file__).resolve().parents[4]
SRC=ROOT/'characters/xiaoxun/forms/teen/sprites/hair_hood_long@2x.png'
MASK=BASE/'manual_artifact_silhouette_polygons_v3.json'
PATCH=BASE/'84_backfill_freeflow_inference_v5.png'; CLEAN=BASE/'85_front_artifact_clear_v5_diagnostic.png'; BOARD=BASE/'86_backfill_v5_local_style_review.png'; REPORT=BASE/'87_layered_backfill_v5_metrics.json'
S=4; BOXES={'left':(51,849,396,1368),'right':(736,849,1081,1368)}
STOPS=[0,.10,.26,.48,.72,.90,1]
CURVES={
 'left':[
   ([(179,238),(162,326),(176,430),(196,532)],[48,55,68,76,86,91,96]),
   ([(111,242),(96,330),(91,430),(85,532)],[18,21,24,27,29,28,25]),
   ([(246,242),(257,330),(269,430),(282,532)],[16,19,22,25,27,26,23]),
 ],
 'right':[
   ([(166,238),(183,326),(169,430),(149,532)],[48,55,68,76,86,91,96]),
   ([(234,242),(249,330),(254,430),(260,532)],[18,21,24,27,29,28,25]),
   ([(111,242),(96,330),(84,430),(63,532)],[16,19,22,25,27,26,23]),
 ]}

def cubic(P,n=240):
 p0,p1,p2,p3=P;out=[]
 for i in range(n+1):
  t=i/n;u=1-t;out.append((u**3*p0[0]+3*u*u*t*p1[0]+3*u*t*t*p2[0]+t**3*p3[0],u**3*p0[1]+3*u*u*t*p1[1]+3*u*t*t*p2[1]+t**3*p3[1]))
 return out

def smooth_width(t,ws):
 for i in range(len(STOPS)-1):
  if t<=STOPS[i+1]:
   q=(t-STOPS[i])/(STOPS[i+1]-STOPS[i]);q=q*q*(3-2*q);return ws[i]*(1-q)+ws[i+1]*q
 return ws[-1]

def ribbon(points,ws):
 left=[];right=[]
 for i,(x,y) in enumerate(points):
  j0=max(0,i-1);j1=min(len(points)-1,i+1);dx=points[j1][0]-points[j0][0];dy=points[j1][1]-points[j0][1];length=max(math.hypot(dx,dy),1e-6);nx=-dy/length;ny=dx/length;w=smooth_width(i/(len(points)-1),ws)
  left.append(((x+nx*w/2)*S,(y+ny*w/2)*S));right.append(((x-nx*w/2)*S,(y-ny*w/2)*S))
 return left+right[::-1]

def offset(points,amount):
 out=[]
 for i,(x,y) in enumerate(points):
  j0=max(0,i-1);j1=min(len(points)-1,i+1);dx=points[j1][0]-points[j0][0];dy=points[j1][1]-points[j0][1];length=max(math.hypot(dx,dy),1e-6);out.append((x-dy/length*amount,y+dx/length*amount))
 return out

def make_gradient(size,side,idx):
 w,h=size;im=Image.new('RGBA',(w,h));px=im.load()
 # Samples intentionally stay within the target's cool lavender hair palette; values are
 # interpolated, not copied from a neighboring region or used as hidden-shape truth.
 if side=='left': top=(196,188,210);mid=(177,174,199);bottom=(187,191,216)
 else: top=(194,187,208);mid=(176,173,198);bottom=(187,192,217)
 for y in range(h):
  q=y/max(h-1,1)
  if q<.60:
   t=q/.60;color=[top[k]*(1-t)+mid[k]*t for k in range(3)]
  else:
   t=(q-.60)/.40;color=[mid[k]*(1-t)+bottom[k]*t for k in range(3)]
  for x in range(w):
   # Slight darker shoulders and gentle center bloom; keep the contrast restrained.
   u=x/max(w-1,1);shoulder=1-.08*(2*u-1)**2;glow=2.0*math.exp(-((u-.46)/.21)**2)
   px[x,y]=tuple(max(0,min(255,round(c*shoulder+glow))) for c in color)+(255,)
 return im

def paint(dst,side,idx,curve,ws,size):
 points=cubic(curve);shape=Image.new('L',(size[0]*S,size[1]*S),0);ImageDraw.Draw(shape).polygon(ribbon(points,ws),fill=255)
 grad=make_gradient((size[0]*S,size[1]*S),side,idx)
 # Render an ultra-soft inner shade and highlight, clipped to the lock's organic silhouette.
 accents=Image.new('RGBA',grad.size,(0,0,0,0));d=ImageDraw.Draw(accents)
 maxw=max(ws)
 shade_color=(128,130,158,26 if idx==0 else 18);light_color=(238,232,247,30 if idx==0 else 23)
 d.line([(x*S,y*S) for x,y in offset(points,maxw*.29)],fill=shade_color,width=max(2,int(maxw*.075*S)),joint='curve')
 d.line([(x*S,y*S) for x,y in offset(points,-maxw*.08)],fill=light_color,width=max(2,int(maxw*.07*S)),joint='curve')
 # One fine, low-contrast strand line gives the brushed painted finish without hard black ink.
 if idx==0:
  d.line([(x*S,y*S) for x,y in offset(points,maxw*.12)],fill=(151,150,177,23),width=max(2,int(1.25*S)),joint='curve')
 accents.putalpha(ImageChops.multiply(accents.getchannel('A'),shape))
 body=Image.composite(grad,Image.new('RGBA',grad.size,(0,0,0,0)),shape);body.alpha_composite(accents);dst.alpha_composite(body)

source=Image.open(SRC).convert('RGBA');maskdata=json.loads(MASK.read_text(encoding='utf-8'))['objects'];clean=source.copy();patch_full=Image.new('RGBA',source.size,(0,0,0,0));counts={}
for side,box in BOXES.items():
 x0,y0,x1,y1=box;size=(x1-x0,y1-y0);base=source.crop(box);mask=Image.new('L',(size[0]*S,size[1]*S),0);d=ImageDraw.Draw(mask)
 for key in ('cuff','hand'):
  d.polygon([(x*S,y*S) for x,y in maskdata[side][key]],fill=255)
 mask=mask.resize(size,Image.Resampling.LANCZOS);front=base.copy();front.putalpha(ImageChops.multiply(base.getchannel('A'),ImageChops.invert(mask)));clean.paste(front,(x0,y0))
 work=Image.new('RGBA',(size[0]*S,size[1]*S),(0,0,0,0))
 for idx,(curve,widths) in enumerate(CURVES[side]):paint(work,side,idx,curve,widths,size)
 patch=work.resize(size,Image.Resampling.LANCZOS);patch_full.alpha_composite(patch,(x0,y0))
 counts[side]={'front_alpha_cleared':sum(v>0 for v in mask.tobytes()),'backfill_alpha_gt24':sum(v>24 for v in patch.getchannel('A').tobytes())}
PATCH.parent.mkdir(parents=True,exist_ok=True);patch_full.save(PATCH);clean.save(CLEAN)
# Local style gate board: source, isolated inferred locks on matte, and layered context.
TW,TH=690,1038;board=Image.new('RGB',(TW*3+48,(TH+58)*2),(244,242,247));draw=ImageDraw.Draw(board)
for row,(side,box) in enumerate(BOXES.items()):
 x0,y0,x1,y1=box;orig=source.crop(box);matte=Image.new('RGBA',orig.size,(239,239,244,255));matte.alpha_composite(orig)
 patch=patch_full.crop(box);pm=Image.new('RGBA',patch.size,(239,239,244,255));pm.alpha_composite(patch)
 front=clean.crop(box);layer=Image.new('RGBA',front.size,(0,0,0,0));layer.alpha_composite(patch);layer.alpha_composite(front)
 comp=Image.new('RGBA',orig.size,(239,239,244,255));comp.alpha_composite(layer)
 for col,(im,label) in enumerate(zip((matte.convert('RGB'),pm.convert('RGB'),comp.convert('RGB')),('source on matte','inferred patch alone','candidate backfill behind cleaned foreground'))):
  x=12+col*(TW+12);y=42+row*(TH+58);board.paste(im.resize((TW,TH),Image.Resampling.LANCZOS),(x,y));draw.text((x+3,y-24),f'{side}: {label}',fill=(30,25,40))
board.save(BOARD)
rep={'task':'T67.71','status':'WIP5 inferred backfill only; not source truth, not visually accepted, not production','source':str(SRC.relative_to(ROOT)),'mask_basis':'manual visible cuff/hand silhouette v3 for the foreground diagnostic; its boundary remains under review','backfill_method':'three broad curved ribbons with continuous soft lavender shading and low-contrast painted strand accents; no source pixel copy, inpainting, or arbitrary displacement','geometry':'hidden strand paths are new inference; left/right correspondences are a design hypothesis, not recovered source','palette':'restrained interpolation from sampled cool target-hair colors and same-piece style reference','order':'local amplified visual/style review required before any C integration','counts':counts,'outputs':[str(PATCH.relative_to(ROOT)),str(CLEAN.relative_to(ROOT)),str(BOARD.relative_to(ROOT))]}
REPORT.write_text(json.dumps(rep,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');print(json.dumps(rep,ensure_ascii=False,indent=2))
