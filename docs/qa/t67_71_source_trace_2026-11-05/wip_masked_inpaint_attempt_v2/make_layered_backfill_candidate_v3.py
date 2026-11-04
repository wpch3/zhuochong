#!/usr/bin/env python3
"""WIP3: longer, smoother tapered locks; front clearing remains ROI-only diagnostic, backfill is independent."""
from pathlib import Path
import json, math
from PIL import Image, ImageChops, ImageDraw
BASE=Path(__file__).resolve().parent; ROOT=Path(__file__).resolve().parents[4]
SRC=ROOT/'characters/xiaoxun/forms/teen/sprites/hair_hood_long@2x.png'
POLYS=BASE/'manual_artifact_polygons_v2.json'
CLEAN=BASE/'55_clean_front_alpha_roi_diagnostic_v3.png'; PATCH=BASE/'56_backfill_freeflow_inference_v3.png'; REPORT=BASE/'57_layered_backfill_v3_metrics.json'
S=4; BOXES={'left':(51,849,396,1368),'right':(736,849,1081,1368)}
T=[0,.12,.30,.72,.90,1]
def cubic(P,n=180):
 p0,p1,p2,p3=P;out=[]
 for i in range(n+1):
  t=i/n;u=1-t;out.append((u**3*p0[0]+3*u*u*t*p1[0]+3*u*t*t*p2[0]+t**3*p3[0],u**3*p0[1]+3*u*u*t*p1[1]+3*u*t*t*p2[1]+t**3*p3[1]))
 return out
def w_at(t,ws):
 for i in range(len(T)-1):
  if t<=T[i+1]:
   q=(t-T[i])/(T[i+1]-T[i]);q=q*q*(3-2*q);return ws[i]*(1-q)+ws[i+1]*q
 return ws[-1]
def ribbon(points,ws):
 l=[];r=[];n=len(points)
 for i,(x,y) in enumerate(points):
  j0=max(0,i-1);j1=min(n-1,i+1);dx=points[j1][0]-points[j0][0];dy=points[j1][1]-points[j0][1];ln=max(math.hypot(dx,dy),1e-6);nx=-dy/ln;ny=dx/ln;w=w_at(i/(n-1),ws)
  l.append(((x+nx*w/2)*S,(y+ny*w/2)*S));r.append(((x-nx*w/2)*S,(y-ny*w/2)*S))
 return l+r[::-1]
def offset(points,amount):
 out=[]
 for i,(x,y) in enumerate(points):
  j0=max(0,i-1);j1=min(len(points)-1,i+1);dx=points[j1][0]-points[j0][0];dy=points[j1][1]-points[j0][1];ln=max(math.hypot(dx,dy),1e-6);out.append((x-dy/ln*amount,y+dx/ln*amount))
 return out
def paint(dst,grad,curve,ws):
 pts=cubic(curve);mask=Image.new('L',dst.size,0);ImageDraw.Draw(mask).polygon(ribbon(pts,ws),fill=255)
 body=Image.composite(grad,Image.new('RGBA',dst.size,(0,0,0,0)),mask)
 accents=Image.new('RGBA',dst.size,(0,0,0,0));d=ImageDraw.Draw(accents); mid=max(ws)
 d.line([(x*S,y*S) for x,y in offset(pts,mid*.24)],fill=(132,138,170,85),width=max(2,int(mid*.055*S)),joint='curve')
 d.line([(x*S,y*S) for x,y in offset(pts,-mid*.12)],fill=(235,229,245,105),width=max(2,int(mid*.055*S)),joint='curve')
 accents.putalpha(ImageChops.multiply(accents.getchannel('A'),mask));body.alpha_composite(accents);dst.alpha_composite(body)
source=Image.open(SRC).convert('RGBA'); polys=json.loads(POLYS.read_text(encoding='utf-8'))['polygons']; clean=source.copy();patchfull=Image.new('RGBA',source.size,(0,0,0,0)); roi_count=0;cleared=0;patch_count=0
curves={
 'left':[
  ([(171,190),(160,285),(173,420),(199,530)],[0,28,54,54,33,0]),
  ([(252,220),(241,315),(263,427),(277,526)],[0,14,25,23,11,0]),
  ([(107,220),(107,340),(84,433),(77,520)],[0,11,19,15,6,0]),
 ],
 'right':[
  ([(174,190),(185,285),(172,420),(146,530)],[0,28,54,54,33,0]),
  ([(93,220),(104,315),(82,427),(68,526)],[0,14,25,23,11,0]),
  ([(238,220),(238,340),(261,433),(268,520)],[0,11,19,15,6,0]),
 ]}
for side,box in BOXES.items():
 x0,y0,x1,y1=box;size=(x1-x0,y1-y0);base=source.crop(box);hi=Image.new('L',(size[0]*S,size[1]*S),0);d=ImageDraw.Draw(hi)
 for poly in polys[side]:d.polygon([(x*S,y*S) for x,y in poly],fill=255)
 roi=hi.resize(size,Image.Resampling.LANCZOS);cleared_crop=base.copy();cleared_crop.putalpha(ImageChops.multiply(base.getchannel('A'),ImageChops.invert(roi)));clean.paste(cleared_crop,(x0,y0))
 cleared+=sum(a!=b for a,b in zip(base.getchannel('A').tobytes(),cleared_crop.getchannel('A').tobytes()));roi_count+=sum(v>0 for v in roi.tobytes())
 grad=Image.new('RGBA',(size[0]*S,size[1]*S));px=grad.load();top=(209,199,225,255);bottom=(179,190,220,255)
 for y in range(size[1]*S):
  q=y/(size[1]*S-1);c=tuple(round(a+(b-a)*q) for a,b in zip(top,bottom))
  for x in range(size[0]*S):px[x,y]=c
 work=Image.new('RGBA',(size[0]*S,size[1]*S),(0,0,0,0))
 for curve,ws in curves[side]:paint(work,grad,curve,ws)
 patch=work.resize(size,Image.Resampling.LANCZOS);patchfull.alpha_composite(patch,(x0,y0));patch_count+=sum(v>24 for v in patch.getchannel('A').tobytes())
# WIP diagnostic invariant: only front layer is cleared in broad ROI; backfill is intentionally not ROI-clipped.
diff=ImageChops.difference(source,clean);allowed=Image.new('L',source.size,0)
for side,box in BOXES.items():
 x0,y0,x1,y1=box;size=(x1-x0,y1-y0);hi=Image.new('L',(size[0]*S,size[1]*S),0);d=ImageDraw.Draw(hi)
 for poly in polys[side]:d.polygon([(x*S,y*S) for x,y in poly],fill=255)
 allowed.paste(hi.resize(size,Image.Resampling.LANCZOS),(x0,y0))
outside=ImageChops.multiply(ImageChops.invert(allowed.point(lambda v:255 if v else 0)),ImageChops.lighter(ImageChops.lighter(diff.getchannel('R'),diff.getchannel('G')),ImageChops.lighter(diff.getchannel('B'),diff.getchannel('A'))))
if outside.getbbox():raise SystemExit(f'clean changed outside diagnostic ROI: {outside.getbbox()}')
clean.save(CLEAN);patchfull.save(PATCH)
rep={'task':'T67.71','status':'split-layer WIP3 inference only, not recovered source or production','front_diagnostic':str(CLEAN.relative_to(ROOT)),'backfill':str(PATCH.relative_to(ROOT)),
 'front_roi':'broad visible cuff/hand ROI includes adjacent legal hair; clearing it entirely is diagnostic only and not an acceptable final removal mask',
 'backfill_roi_relation':'independent manually traced alpha; not clipped by projection or artifact ROI',
 'layer_hypothesis':'front hair layer 258 and inferred backfill behind arms at 135','front_alpha_pixels_cleared':cleared,'roi_pixels':roi_count,'backfill_alpha_gt24_pixels':patch_count,
 'negative_space':'three separated locks with smooth width plateaus and tapered ends; transparent gaps retained','style':'local smooth gradient guided by sampled same-asset hair colors; no neighbor pixel copy or displacement',
 'geometry':'all hidden paths inferred; left/right mirroring is an assumption, not source truth','outside_roi_byte_identity':'front diagnostic only, asserted exact','production_changes':False}
REPORT.write_text(json.dumps(rep,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps({k:rep[k] for k in ('status','front_alpha_pixels_cleared','roi_pixels','backfill_alpha_gt24_pixels')},ensure_ascii=False,indent=2))
