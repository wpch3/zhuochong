#!/usr/bin/env python3
"""按扩大的可见异物 ROI 做手工曲线推断 v3；只写 WIP，非原稿恢复。"""
from __future__ import annotations
import json, math
from pathlib import Path
from PIL import Image, ImageChops, ImageDraw
BASE=Path(__file__).resolve().parent
ROOT=Path(__file__).resolve().parents[4]
SRC=ROOT/'characters/xiaoxun/forms/teen/sprites/hair_hood_long@2x.png'
POLYS=BASE/'manual_artifact_polygons_v2.json'
OUT=BASE/'40_manual_strand_trace_candidate_v3_wip.png'
METRICS=BASE/'41_manual_strand_trace_v3_metrics.json'
BOXES={'left':(51,849,396,1368),'right':(736,849,1081,1368)}
S=4

def cubic(P,n=140):
 p0,p1,p2,p3=P; out=[]
 for i in range(n+1):
  t=i/n; u=1-t
  out.append((u**3*p0[0]+3*u*u*t*p1[0]+3*u*t*t*p2[0]+t**3*p3[0],u**3*p0[1]+3*u*u*t*p1[1]+3*u*t*t*p2[1]+t**3*p3[1]))
 return out

def ribbon_sides(points,widths):
 left=[]; right=[]; n=len(points)
 for i,(x,y) in enumerate(points):
  j0=max(0,i-1); j1=min(n-1,i+1)
  dx=points[j1][0]-points[j0][0]; dy=points[j1][1]-points[j0][1]
  length=max(math.hypot(dx,dy),1e-6); nx=-dy/length; ny=dx/length
  t=i/(n-1); w0,wm,w1=widths
  if t<=.5: q=t*2; w=w0*(1-q)+wm*q
  else: q=(t-.5)*2; w=wm*(1-q)+w1*q
  left.append(((x+nx*w/2)*S,(y+ny*w/2)*S)); right.append(((x-nx*w/2)*S,(y-ny*w/2)*S))
 return left,right

def offset(points,amount):
 out=[]
 for i,(x,y) in enumerate(points):
  j0=max(0,i-1); j1=min(len(points)-1,i+1)
  dx=points[j1][0]-points[j0][0]; dy=points[j1][1]-points[j0][1]
  length=max(math.hypot(dx,dy),1e-6); out.append((x-dy/length*amount,y+dx/length*amount))
 return out

def lerp(a,b,t): return tuple(round(x*(1-t)+y*t) for x,y in zip(a,b))

def make_gradient(size):
 W,H=size; im=Image.new('RGBA',(W*S,H*S)); pix=im.load()
 top=(216,201,225,255); mid=(198,197,224,255); bottom=(174,195,222,255)
 for y in range(H*S):
  t=y/(H*S-1)
  if t<.58: c=lerp(top,mid,t/.58)
  else: c=lerp(mid,bottom,(t-.58)/.42)
  for x in range(W*S): pix[x,y]=c
 return im

def paint_ribbon(canvas,gradient,curve,widths,highlight,shadow,outline):
 pts=cubic(curve)
 l,r=ribbon_sides(pts,widths)
 m=Image.new('L',canvas.size,0); md=ImageDraw.Draw(m); md.polygon(l+r[::-1],fill=255)
 fill=Image.composite(gradient,Image.new('RGBA',canvas.size,(0,0,0,0)),m)
 canvas.alpha_composite(fill)
 d=ImageDraw.Draw(canvas)
 midw=widths[1]
 # Low-contrast contour and one restrained highlight follow the hand-traced curvature.
 for side in (l,r):
  d.line(side,fill=outline,width=max(3,S),joint='curve')
 sh=offset(pts,midw*.27); hi=offset(pts,-midw*.12)
 d.line([(x*S,y*S) for x,y in sh],fill=shadow,width=max(S,int(midw*.055*S)),joint='curve')
 d.line([(x*S,y*S) for x,y in hi],fill=highlight,width=max(S,int(midw*.11*S)),joint='curve')

source=Image.open(SRC).convert('RGBA')
polydata=json.loads(POLYS.read_text(encoding='utf-8'))
polys=polydata['polygons']
# Curves start/end at observed visible hair boundaries. Direction and hidden course are inferred.
# Left/right paths are designed as approximate mirror mates; this symmetry is an explicit assumption.
curves={
 'left':[
  ([(164,246),(184,286),(205,323),(188,372)],(7,40,32),(239,233,247,255),(150,148,177,230),(123,118,147,190)),
  ([(150,260),(154,318),(126,382),(92,441)],(5,31,1),(235,229,245,245),(156,153,182,220),(128,123,151,180)),
  ([(228,281),(226,337),(247,396),(258,443)],(4,29,1),(242,237,249,245),(158,153,183,220),(130,125,154,180)),
  ([(188,366),(177,395),(173,423),(166,447)],(24,31,1),(226,228,242,245),(151,154,184,220),(123,126,154,180)),
 ],
 'right':[
  ([(181,246),(161,286),(140,323),(157,372)],(7,40,32),(239,233,247,255),(150,148,177,230),(123,118,147,190)),
  ([(195,260),(191,318),(219,382),(253,441)],(5,31,1),(235,229,245,245),(156,153,182,220),(128,123,151,180)),
  ([(117,281),(119,337),(98,396),(87,443)],(4,29,1),(242,237,249,245),(158,153,183,220),(130,125,154,180)),
  ([(157,366),(168,395),(172,423),(179,447)],(24,31,1),(226,228,242,245),(151,154,184,220),(123,126,154,180)),
 ]
}
result=source.copy(); all_region=Image.new('L',source.size,0); region_px=0; new_alpha_px=0
for side,box in BOXES.items():
 x0,y0,x1,y1=box; size=(x1-x0,y1-y0)
 if size!=(345,519): raise SystemExit(f'crop mapping changed: {side} {size}')
 hi=Image.new('L',(size[0]*S,size[1]*S),0); md=ImageDraw.Draw(hi)
 for poly in polys[side]: md.polygon([(x*S,y*S) for x,y in poly],fill=255)
 roi=hi.resize(size,Image.Resampling.LANCZOS)
 base=source.crop(box); cleared=base.copy()
 cleared.putalpha(ImageChops.multiply(base.getchannel('A'),ImageChops.invert(roi)))
 work=Image.new('RGBA',(size[0]*S,size[1]*S),(0,0,0,0)); grad=make_gradient(size)
 for curve,widths,high,shadow,outline in curves[side]: paint_ribbon(work,grad,curve,widths,high,shadow,outline)
 layer=work.resize(size,Image.Resampling.LANCZOS)
 layer.putalpha(ImageChops.multiply(layer.getchannel('A'),roi))
 composed=Image.alpha_composite(cleared,layer)
 patch=Image.composite(composed,base,roi)
 result.paste(patch,(x0,y0)); all_region.paste(roi,(x0,y0))
 region_px += sum(v>0 for v in roi.tobytes())
 new_alpha_px += sum(v>24 for v in layer.getchannel('A').tobytes())
# Exact byte assertion outside the manually reviewed visible-artifact ROI.
diff=ImageChops.difference(source,result)
allowed=all_region.point(lambda v:255 if v>0 else 0)
outside=ImageChops.multiply(ImageChops.invert(allowed),ImageChops.lighter(ImageChops.lighter(diff.getchannel('R'),diff.getchannel('G')),ImageChops.lighter(diff.getchannel('B'),diff.getchannel('A'))))
if outside.getbbox(): raise SystemExit(f'changed outside ROI: {outside.getbbox()}')
result.save(OUT)
sb=source.tobytes(); rb=result.tobytes(); sa=source.getchannel('A').tobytes(); ra=result.getchannel('A').tobytes()
metrics={'task':'T67.71','status':'manual reconstruction inference v3; WIP only, source geometry unknown',
 'source':str(SRC.relative_to(ROOT)),'candidate':str(OUT.relative_to(ROOT)),
 'mask':'manual_artifact_polygons_v2.json; expanded visible cuff/hand artifact ROI, not hair segmentation; no rig-mask intersection',
 'changed_alpha_pixels':sum(a!=b for a,b in zip(sa,ra)),
 'changed_rgba_pixels':sum(sb[i:i+4]!=rb[i:i+4] for i in range(0,len(sb),4)),
 'roi_nonzero_pixels':region_px,'new_strand_alpha_px_gt24':new_alpha_px,
 'outside_roi_byte_identity':'asserted exact',
 'negative_space':'separate ribbons; no global fill; transparent gaps retained between strokes',
 'geometry':'curves trace adjacent visible flow direction; hidden path and mirrored L/R symmetry are explicit inference assumptions',
 'production_changes':False,
 'manual_curves_local_345x519':{s:[{'curve':c[0],'widths':c[1]} for c in curves[s]] for s in curves},
 'gate':'must pass local visual review before any C render; no claim of recovered source'}
(BASE/'41_manual_strand_trace_v3_metrics.json').write_text(json.dumps(metrics,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps({k:metrics[k] for k in ('status','changed_alpha_pixels','changed_rgba_pixels','roi_nonzero_pixels','new_strand_alpha_px_gt24','outside_roi_byte_identity')},ensure_ascii=False,indent=2))
