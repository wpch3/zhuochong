#!/usr/bin/env python3
"""WIP6: one continuous inferred back-hair sheet with restrained painted folds; diagnostic only."""
from pathlib import Path
import json, math
from PIL import Image, ImageChops, ImageDraw, ImageFilter
BASE=Path(__file__).resolve().parent; ROOT=Path(__file__).resolve().parents[4]
SRC=ROOT/'characters/xiaoxun/forms/teen/sprites/hair_hood_long@2x.png'
POLY=BASE/'manual_artifact_silhouette_polygons_v3.json'
PATCH=BASE/'93_backfill_single_sheet_inference_v6.png'; CLEAN=BASE/'94_front_clear_v6_diagnostic.png'; BOARD=BASE/'95_backfill_v6_style_review.png'; REPORT=BASE/'96_backfill_v6_metrics.json'
S=4; BOXES={'left':(51,849,396,1368),'right':(736,849,1081,1368)}
WIDTH_STOPS=[0,.12,.30,.52,.72,.88,1]
SHEETS={
 'left': ([(184,222),(159,314),(177,420),(210,503)],[42,47,66,79,76,48,15]),
 'right': ([(161,222),(187,314),(173,420),(139,503)],[42,47,66,79,76,48,15]),
}

def cubic(P,n=260):
 p0,p1,p2,p3=P;out=[]
 for i in range(n+1):
  t=i/n;u=1-t;out.append((u**3*p0[0]+3*u*u*t*p1[0]+3*u*t*t*p2[0]+t**3*p3[0],u**3*p0[1]+3*u*u*t*p1[1]+3*u*t*t*p2[1]+t**3*p3[1]))
 return out

def width_at(t,vals):
 for i in range(len(WIDTH_STOPS)-1):
  if t<=WIDTH_STOPS[i+1]:
   q=(t-WIDTH_STOPS[i])/(WIDTH_STOPS[i+1]-WIDTH_STOPS[i]);q=q*q*(3-2*q);return vals[i]*(1-q)+vals[i+1]*q
 return vals[-1]

def offset(points,amount):
 out=[]
 for i,(x,y) in enumerate(points):
  a=max(0,i-1);b=min(len(points)-1,i+1);dx=points[b][0]-points[a][0];dy=points[b][1]-points[a][1];ln=max(math.hypot(dx,dy),1e-5);out.append((x-dy/ln*amount,y+dx/ln*amount))
 return out

def polygon(points,widths):
 l=[];r=[]
 for i,(x,y) in enumerate(points):
  a=max(0,i-1);b=min(len(points)-1,i+1);dx=points[b][0]-points[a][0];dy=points[b][1]-points[a][1];ln=max(math.hypot(dx,dy),1e-5);nx=-dy/ln;ny=dx/ln;w=width_at(i/(len(points)-1),widths)
  l.append(((x+nx*w/2)*S,(y+ny*w/2)*S));r.append(((x-nx*w/2)*S,(y-ny*w/2)*S))
 return l+r[::-1]

def grad_field(size,side):
 w,h=size
 stops=[(0,(196,188,210)),(.34,(184,179,204)),(.68,(175,174,198)),(1,(189,194,219))]
 im=Image.new('RGBA',(w,h));p=im.load()
 for y in range(h):
  q=y/max(h-1,1)
  for i in range(len(stops)-1):
   if q<=stops[i+1][0]:
    t=(q-stops[i][0])/(stops[i+1][0]-stops[i][0]);t=t*t*(3-2*t);c=[round(stops[i][1][k]*(1-t)+stops[i+1][1][k]*t) for k in range(3)];break
  else:c=list(stops[-1][1])
  for x in range(w):
   u=x/max(w-1,1);shoulder=1-.05*(2*u-1)**2;center_glow=2.5*math.exp(-((u-.45)/.25)**2);p[x,y]=tuple(max(0,min(255,round(v*shoulder+center_glow))) for v in c)+(255,)
 return im

def paint_sheet(dst,side,curve,widths,size):
 pts=cubic(curve);mask=Image.new('L',(size[0]*S,size[1]*S),0);ImageDraw.Draw(mask).polygon(polygon(pts,widths),fill=255)
 # A very slight edge softening reproduces the source's antialiased painted contour without a blurry halo.
 mask=mask.filter(ImageFilter.GaussianBlur(.28*S))
 fill=Image.composite(grad_field(mask.size,side),Image.new('RGBA',mask.size,(0,0,0,0)),mask)
 # Restrained fold shading: two thin, curved strokes sampled from the same asset's low-contrast linework.
 accent=Image.new('RGBA',mask.size,(0,0,0,0));d=ImageDraw.Draw(accent);wmax=max(widths)
 d.line([(x*S,y*S) for x,y in offset(pts,-wmax*.22)],fill=(132,130,159,25),width=max(2,int(2.2*S)),joint='curve')
 d.line([(x*S,y*S) for x,y in offset(pts,wmax*.05)],fill=(238,233,247,38),width=max(2,int(3.0*S)),joint='curve')
 d.line([(x*S,y*S) for x,y in offset(pts,wmax*.18)],fill=(151,149,177,21),width=max(2,int(1.3*S)),joint='curve')
 accent.putalpha(ImageChops.multiply(accent.getchannel('A'),mask));fill.alpha_composite(accent);dst.alpha_composite(fill)

src=Image.open(SRC).convert('RGBA');arr=src;objects=json.loads(POLY.read_text(encoding='utf-8'))['objects'];front=src.copy();patchfull=Image.new('RGBA',src.size,(0,0,0,0));counts={}
for side,box in BOXES.items():
 x0,y0,x1,y1=box;size=(x1-x0,y1-y0);crop=src.crop(box);mask=Image.new('L',(size[0]*S,size[1]*S),0);dr=ImageDraw.Draw(mask)
 for k in ('cuff','hand'):dr.polygon([(x*S,y*S) for x,y in objects[side][k]],fill=255)
 mask=mask.resize(size,Image.Resampling.LANCZOS);clean=crop.copy();clean.putalpha(ImageChops.multiply(crop.getchannel('A'),ImageChops.invert(mask)));front.paste(clean,(x0,y0))
 work=Image.new('RGBA',(size[0]*S,size[1]*S),(0,0,0,0));curve,widths=SHEETS[side];paint_sheet(work,side,curve,widths,size);piece=work.resize(size,Image.Resampling.LANCZOS);patchfull.alpha_composite(piece,(x0,y0))
 counts[side]={'front_alpha_clear_mask_pixels_gt0':sum(v>0 for v in mask.tobytes()),'patch_alpha_gt24':sum(v>24 for v in piece.getchannel('A').tobytes())}
patchfull.save(PATCH);front.save(CLEAN)
# Local visual gate board: original, patch isolated, and patch behind foreground after diagnostic clear.
TW,TH=690,1038;board=Image.new('RGB',(TW*3+48,(TH+58)*2),(244,242,247));d=ImageDraw.Draw(board)
for row,(side,box) in enumerate(BOXES.items()):
 orig=src.crop(box);matte=Image.new('RGBA',orig.size,(239,239,244,255));matte.alpha_composite(orig)
 patch=patchfull.crop(box);patchmatte=Image.new('RGBA',patch.size,(239,239,244,255));patchmatte.alpha_composite(patch)
 layer=Image.new('RGBA',orig.size,(0,0,0,0));layer.alpha_composite(patch);layer.alpha_composite(front.crop(box));comp=Image.new('RGBA',orig.size,(239,239,244,255));comp.alpha_composite(layer)
 for col,(im,label) in enumerate(((matte.convert('RGB'),'original source'),(patchmatte.convert('RGB'),'single inferred sheet alone'),(comp.convert('RGB'),'single sheet behind diagnostic foreground'))):
  x=12+col*(TW+12);y=42+row*(TH+58);board.paste(im.resize((TW,TH),Image.Resampling.LANCZOS),(x,y));d.text((x+3,y-24),f'{side}: {label}',fill=(30,25,40))
board.save(BOARD)
report={'task':'T67.71','status':'WIP6 inferred single-sheet backfill; not recovered source, not production, pending visual rejection/approval','source':str(SRC.relative_to(ROOT)),'hidden_region':'occluded hair geometry remains unknown','geometry':'one continuous smooth sheet inferred behind each full cuff/hand silhouette; left/right flow is manually guided, not recovered','appearance':'cool lavender palette with subtle target-inspired gradient and low-contrast painted folds; no source pixel copy, generic inpaint, or arbitrary displacement','clear_mask':'manual visible-object silhouette v3 used only for local diagnostic and remains separately reviewable','outputs':[str(PATCH.relative_to(ROOT)),str(CLEAN.relative_to(ROOT)),str(BOARD.relative_to(ROOT))],'counts':counts}
REPORT.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');print(json.dumps(report,ensure_ascii=False,indent=2))
