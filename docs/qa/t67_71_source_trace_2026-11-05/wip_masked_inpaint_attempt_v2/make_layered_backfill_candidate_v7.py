#!/usr/bin/env python3
"""WIP7: broad continuous inferred back-hair sheet to cover the clear-only cutout; diagnostic only."""
from pathlib import Path
import json, math
from PIL import Image, ImageChops, ImageDraw, ImageFilter
BASE=Path(__file__).resolve().parent;ROOT=Path(__file__).resolve().parents[4]
SRC=ROOT/'characters/xiaoxun/forms/teen/sprites/hair_hood_long@2x.png';POLY=BASE/'manual_artifact_silhouette_polygons_v3.json'
PATCH=BASE/'97_backfill_broad_sheet_inference_v7.png';CLEAN=BASE/'98_front_clear_v7_diagnostic.png';BOARD=BASE/'99_backfill_v7_style_review.png';REPORT=BASE/'100_backfill_v7_metrics.json'
S=4;BOXES={'left':(51,849,396,1368),'right':(736,849,1081,1368)}
STOPS=[0,.12,.30,.48,.69,.86,1]
SHEETS={
 'left': ([(171,220),(161,302),(178,408),(212,530)],[92,105,126,148,152,136,108]),
 'right': ([(174,220),(187,302),(169,408),(134,530)],[92,105,126,148,152,136,108]),
}

def cubic(P,n=300):
 p0,p1,p2,p3=P;out=[]
 for i in range(n+1):
  t=i/n;u=1-t;out.append((u**3*p0[0]+3*u*u*t*p1[0]+3*u*t*t*p2[0]+t**3*p3[0],u**3*p0[1]+3*u*u*t*p1[1]+3*u*t*t*p2[1]+t**3*p3[1]))
 return out

def interp(t,vals):
 for i in range(len(STOPS)-1):
  if t<=STOPS[i+1]:
   q=(t-STOPS[i])/(STOPS[i+1]-STOPS[i]);q=q*q*(3-2*q);return vals[i]*(1-q)+vals[i+1]*q
 return vals[-1]

def normal(points,i):
 a=max(0,i-1);b=min(len(points)-1,i+1);dx=points[b][0]-points[a][0];dy=points[b][1]-points[a][1];ln=max(math.hypot(dx,dy),1e-6);return -dy/ln,dx/ln

def ribbon(points,widths):
 L=[];R=[]
 for i,(x,y) in enumerate(points):
  nx,ny=normal(points,i);w=interp(i/(len(points)-1),widths);L.append(((x+nx*w/2)*S,(y+ny*w/2)*S));R.append(((x-nx*w/2)*S,(y-ny*w/2)*S))
 return L+R[::-1]

def offset(points,amt):
 return [(x+normal(points,i)[0]*amt,y+normal(points,i)[1]*amt) for i,(x,y) in enumerate(points)]

def field(size,side):
 w,h=size;im=Image.new('RGBA',(w,h));p=im.load()
 stops=[(0,(192,184,207)),(.25,(186,180,205)),(.56,(175,173,199)),(.82,(182,185,212)),(1,(194,198,224))]
 for y in range(h):
  q=y/max(1,h-1)
  for j in range(len(stops)-1):
   if q<=stops[j+1][0]:
    t=(q-stops[j][0])/(stops[j+1][0]-stops[j][0]);t=t*t*(3-2*t);c=[stops[j][1][k]*(1-t)+stops[j+1][1][k]*t for k in range(3)];break
  else:c=list(stops[-1][1])
  for x in range(w):
   u=x/max(1,w-1);cross=1-.055*(2*u-1)**2+2.6*math.exp(-((u-.42)/.16)**2)/255
   p[x,y]=tuple(max(0,min(255,round(v*cross))) for v in c)+(255,)
 return im

def paint_layer(dst,side,size,curve,widths):
 pts=cubic(curve);m=Image.new('L',(size[0]*S,size[1]*S),0);ImageDraw.Draw(m).polygon(ribbon(pts,widths),fill=255)
 # Subtle edge soften; keep crisp alpha at sprite scale.
 m=m.filter(ImageFilter.GaussianBlur(.22*S));body=Image.composite(field(m.size,side),Image.new('RGBA',m.size,(0,0,0,0)),m)
 # Broad low-contrast painted folds, following the same smooth flow as the sheet.
 a=Image.new('RGBA',m.size,(0,0,0,0));d=ImageDraw.Draw(a);wmax=max(widths)
 d.line([(x*S,y*S) for x,y in offset(pts,-wmax*.31)],fill=(126,127,157,27),width=int(10*S),joint='curve')
 d.line([(x*S,y*S) for x,y in offset(pts,-wmax*.12)],fill=(148,146,174,21),width=int(2*S),joint='curve')
 d.line([(x*S,y*S) for x,y in offset(pts,wmax*.02)],fill=(238,234,247,48),width=int(5*S),joint='curve')
 d.line([(x*S,y*S) for x,y in offset(pts,wmax*.17)],fill=(153,151,178,20),width=int(1.4*S),joint='curve')
 d.line([(x*S,y*S) for x,y in offset(pts,wmax*.33)],fill=(235,231,246,23),width=int(2*S),joint='curve')
 a.putalpha(ImageChops.multiply(a.getchannel('A'),m));body.alpha_composite(a);dst.alpha_composite(body)

src=Image.open(SRC).convert('RGBA');objects=json.loads(POLY.read_text(encoding='utf-8'))['objects'];front=src.copy();patchfull=Image.new('RGBA',src.size,(0,0,0,0));counts={}
for side,box in BOXES.items():
 x0,y0,x1,y1=box;size=(x1-x0,y1-y0);crop=src.crop(box);mask=Image.new('L',(size[0]*S,size[1]*S),0);d=ImageDraw.Draw(mask)
 for k in ('cuff','hand'):d.polygon([(x*S,y*S) for x,y in objects[side][k]],fill=255)
 mask=mask.resize(size,Image.Resampling.LANCZOS);fc=crop.copy();fc.putalpha(ImageChops.multiply(crop.getchannel('A'),ImageChops.invert(mask)));front.paste(fc,(x0,y0))
 curve,widths=SHEETS[side];work=Image.new('RGBA',(size[0]*S,size[1]*S),(0,0,0,0));paint_layer(work,side,size,curve,widths);patch=work.resize(size,Image.Resampling.LANCZOS);patchfull.alpha_composite(patch,(x0,y0))
 counts[side]={'front_clear_mask_px_gt0':sum(v>0 for v in mask.tobytes()),'backfill_alpha_gt24':sum(v>24 for v in patch.getchannel('A').tobytes())}
patchfull.save(PATCH);front.save(CLEAN)
TW,TH=690,1038;board=Image.new('RGB',(TW*3+48,(TH+58)*2),(244,242,247));d=ImageDraw.Draw(board)
for row,(side,box) in enumerate(BOXES.items()):
 o=src.crop(box);mat=Image.new('RGBA',o.size,(239,239,244,255));mat.alpha_composite(o);p=patchfull.crop(box);pm=Image.new('RGBA',p.size,(239,239,244,255));pm.alpha_composite(p)
 layer=Image.new('RGBA',o.size,(0,0,0,0));layer.alpha_composite(p);layer.alpha_composite(front.crop(box));comp=Image.new('RGBA',o.size,(239,239,244,255));comp.alpha_composite(layer)
 for col,(im,label) in enumerate(((mat.convert('RGB'),'source'),(pm.convert('RGB'),'broad inferred sheet alone'),(comp.convert('RGB'),'sheet behind cleaned foreground'))):
  x=12+col*(TW+12);y=42+row*(TH+58);board.paste(im.resize((TW,TH),Image.Resampling.LANCZOS),(x,y));d.text((x+3,y-24),f'{side}: {label}',fill=(30,25,40))
board.save(BOARD)
report={'task':'T67.71','status':'WIP7 broad inferred back-hair sheet; unknown geometry, not production or accepted','source':str(SRC.relative_to(ROOT)),'inference':'broad continuous hair surface deliberately extends beyond the visible cuff/hand cutout so source hair remains a separate layer in front','style':'soft cool-lavender gradient and low-contrast painted folds; shape is newly inferred, not sourced or texture-transferred','mask':'manual visible-object silhouette v3 used only for diagnostic foreground clearing; it is still separately reviewable','outputs':[str(PATCH.relative_to(ROOT)),str(CLEAN.relative_to(ROOT)),str(BOARD.relative_to(ROOT))],'counts':counts}
REPORT.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');print(json.dumps(report,ensure_ascii=False,indent=2))
