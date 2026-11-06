#!/usr/bin/env python3
"""WIP2: broad ROI is used only to clear the old front for composition probing; inferred backfill is independent of that ROI."""
from pathlib import Path
import json, math
from PIL import Image, ImageChops, ImageDraw
BASE=Path(__file__).resolve().parent; ROOT=Path(__file__).resolve().parents[4]
SRC=ROOT/'characters/xiaoxun/forms/teen/sprites/hair_hood_long@2x.png'
POLYS=BASE/'manual_artifact_polygons_v2.json'
CLEAN=BASE/'50_clean_front_alpha_masked_roi_test_only.png'
PATCH=BASE/'51_backfill_freeflow_inference_v2.png'
REPORT=BASE/'52_layered_backfill_v2_metrics.json'
S=4; BOXES={'left':(51,849,396,1368),'right':(736,849,1081,1368)}

def cubic(P,n=180):
 p0,p1,p2,p3=P; out=[]
 for i in range(n+1):
  t=i/n;u=1-t
  out.append((u**3*p0[0]+3*u*u*t*p1[0]+3*u*t*t*p2[0]+t**3*p3[0],u**3*p0[1]+3*u*u*t*p1[1]+3*u*t*t*p2[1]+t**3*p3[1]))
 return out

def w_at(t,w):
 a,m,b=w
 if t<.5:q=t*2;return a*(1-q)+m*q
 q=(t-.5)*2;return m*(1-q)+b*q

def ribbon(points,widths):
 l=[];r=[];n=len(points)
 for i,(x,y) in enumerate(points):
  j0=max(0,i-1);j1=min(n-1,i+1);dx=points[j1][0]-points[j0][0];dy=points[j1][1]-points[j0][1];ln=max(math.hypot(dx,dy),1e-6)
  nx=-dy/ln;ny=dx/ln;w=w_at(i/(n-1),widths)
  l.append(((x+nx*w/2)*S,(y+ny*w/2)*S));r.append(((x-nx*w/2)*S,(y-ny*w/2)*S))
 return l+r[::-1]

def offset(points,amount):
 out=[]
 for i,(x,y) in enumerate(points):
  j0=max(0,i-1);j1=min(len(points)-1,i+1);dx=points[j1][0]-points[j0][0];dy=points[j1][1]-points[j0][1];ln=max(math.hypot(dx,dy),1e-6)
  out.append((x-dy/ln*amount,y+dx/ln*amount))
 return out

def paint_ribbon(dst,grad,curve,widths):
 pts=cubic(curve);mask=Image.new('L',dst.size,0);ImageDraw.Draw(mask).polygon(ribbon(pts,widths),fill=255)
 body=Image.composite(grad,Image.new('RGBA',dst.size,(0,0,0,0)),mask)
 accent=Image.new('RGBA',dst.size,(0,0,0,0));d=ImageDraw.Draw(accent);m=widths[1]
 sh=offset(pts,m*.25);hi=offset(pts,-m*.14)
 d.line([(x*S,y*S) for x,y in sh],fill=(126,133,168,115),width=max(2,int(m*.075*S)),joint='curve')
 d.line([(x*S,y*S) for x,y in hi],fill=(235,229,244,145),width=max(2,int(m*.075*S)),joint='curve')
 accent.putalpha(ImageChops.multiply(accent.getchannel('A'),mask));body.alpha_composite(accent)
 dst.alpha_composite(body)

source=Image.open(SRC).convert('RGBA');polys=json.loads(POLYS.read_text(encoding='utf-8'))['polygons']
clean=source.copy(); patchfull=Image.new('RGBA',source.size,(0,0,0,0)); removed=0;roi_count=0;patch_count=0
# These hand-drawn locks are inferred flow only. They are deliberately not clipped to the cuff/hand ROI.
curves={
 'left':[
  ([(174,190),(183,285),(210,397),(198,528)],(2,88,1)),
  ([(250,225),(235,318),(264,424),(278,527)],(1,36,0)),
  ([(111,224),(108,344),(83,433),(77,520)],(1,30,0)),
 ],
 'right':[
  ([(171,190),(162,285),(135,397),(147,528)],(2,88,1)),
  ([(95,225),(110,318),(81,424),(67,527)],(1,36,0)),
  ([(234,224),(237,344),(262,433),(268,520)],(1,30,0)),
 ]}
for side,box in BOXES.items():
 x0,y0,x1,y1=box;size=(x1-x0,y1-y0);base=source.crop(box)
 hi=Image.new('L',(size[0]*S,size[1]*S),0);d=ImageDraw.Draw(hi)
 for poly in polys[side]:d.polygon([(x*S,y*S) for x,y in poly],fill=255)
 roi=hi.resize(size,Image.Resampling.LANCZOS)
 cleared=base.copy();cleared.putalpha(ImageChops.multiply(base.getchannel('A'),ImageChops.invert(roi)));clean.paste(cleared,(x0,y0))
 alpha_removed=sum(a!=b for a,b in zip(base.getchannel('A').tobytes(),cleared.getchannel('A').tobytes()));removed+=alpha_removed;roi_count+=sum(v>0 for v in roi.tobytes())
 # Two-tone hair palette sampled from visible hair in this exact asset; smooth vertical gradient, not copied pixels.
 grad=Image.new('RGBA',(size[0]*S,size[1]*S));px=grad.load()
 top=(211,201,226,255);bottom=(177,189,219,255)
 for y in range(size[1]*S):
  t=y/(size[1]*S-1);c=tuple(round(a+(b-a)*t) for a,b in zip(top,bottom))
  for x in range(size[0]*S):px[x,y]=c
 work=Image.new('RGBA',(size[0]*S,size[1]*S),(0,0,0,0))
 for curve,widths in curves[side]:paint_ribbon(work,grad,curve,widths)
 patch=work.resize(size,Image.Resampling.LANCZOS)
 patchfull.alpha_composite(patch,(x0,y0));patch_count+=sum(v>24 for v in patch.getchannel('A').tobytes())
# The diagnostic clean-only change stays within the visible-artifact ROI; that ROI is not used as backfill alpha.
diff=ImageChops.difference(source,clean);allowed=Image.new('L',source.size,0)
for side,box in BOXES.items():
 x0,y0,x1,y1=box;size=(x1-x0,y1-y0);hi=Image.new('L',(size[0]*S,size[1]*S),0);d=ImageDraw.Draw(hi)
 for poly in polys[side]:d.polygon([(x*S,y*S) for x,y in poly],fill=255)
 allowed.paste(hi.resize(size,Image.Resampling.LANCZOS),(x0,y0))
outside=ImageChops.multiply(ImageChops.invert(allowed.point(lambda v:255 if v else 0)),ImageChops.lighter(ImageChops.lighter(diff.getchannel('R'),diff.getchannel('G')),ImageChops.lighter(diff.getchannel('B'),diff.getchannel('A'))))
if outside.getbbox():raise SystemExit(f'front changed outside test ROI: {outside.getbbox()}')
clean.save(CLEAN);patchfull.save(PATCH)
rep={'task':'T67.71','status':'split-layer WIP2 only; hidden hair is inferred, not recovered','front_test_layer':str(CLEAN.relative_to(ROOT)),'inferred_backfill':str(PATCH.relative_to(ROOT)),
 'visible_artifact_roi':'manual_artifact_polygons_v2; includes adjacent legal hair, therefore broad clearing is diagnostic only and not a valid final removal mask',
 'backfill_roi_relation':'none: independent freeflow curves extend beyond the artifact ROI; ribbon alpha is not clipped to it',
 'layer_hypothesis':'existing front layer 258 plus new inferred layer behind arms at 135',
 'front_alpha_pixels_cleared':removed,'front_outside_roi_byte_identity':'asserted exact','roi_pixels':roi_count,'backfill_alpha_gt24_pixels':patch_count,
 'negative_space':'separate tapered locks and gaps remain; curves are not a source reconstruction',
 'palette':'smooth vertical gradient sampled as color guidance from visible hair in the same sprite; no neighboring pixel copy or displacement',
 'geometry':'manual Bézier inference; exact hidden courses, overlap, and left/right equivalence unknown',
 'production_changes':False,'candidate_gate':'C compositing + local visual review; reject if edge, join, or motion is visibly inconsistent'}
REPORT.write_text(json.dumps(rep,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps({k:rep[k] for k in ('status','front_alpha_pixels_cleared','roi_pixels','backfill_alpha_gt24_pixels','backfill_roi_relation')},ensure_ascii=False,indent=2))
