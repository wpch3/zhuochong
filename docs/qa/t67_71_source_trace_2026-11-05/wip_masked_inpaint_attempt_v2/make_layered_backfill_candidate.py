#!/usr/bin/env python3
"""切成前发清洁层 + 手工推断后发补片，均 WIP；不碰生产。"""
from pathlib import Path
import json, math
from PIL import Image, ImageChops, ImageDraw
BASE=Path(__file__).resolve().parent; ROOT=Path(__file__).resolve().parents[4]
SRC=ROOT/'characters/xiaoxun/forms/teen/sprites/hair_hood_long@2x.png'
POLYS=BASE/'manual_artifact_polygons_v2.json'
CLEAN=BASE/'43_layered_clean_front_hair_wip.png'; PATCH=BASE/'44_layered_manual_backfill_wip.png'
REPORT=BASE/'45_layered_backfill_metrics.json'; S=4
BOXES={'left':(51,849,396,1368),'right':(736,849,1081,1368)}

def cubic(P,n=140):
 p0,p1,p2,p3=P; o=[]
 for i in range(n+1):
  t=i/n; u=1-t
  o.append((u**3*p0[0]+3*u*u*t*p1[0]+3*u*t*t*p2[0]+t**3*p3[0],u**3*p0[1]+3*u*u*t*p1[1]+3*u*t*t*p2[1]+t**3*p3[1]))
 return o

def width_at(t,widths):
 a,m,b=widths
 if t<.5: q=t*2; return a*(1-q)+m*q
 q=(t-.5)*2; return m*(1-q)+b*q

def ribbon_polygon(points,widths):
 l=[]; r=[]; n=len(points)
 for i,(x,y) in enumerate(points):
  j0=max(0,i-1); j1=min(n-1,i+1); dx=points[j1][0]-points[j0][0]; dy=points[j1][1]-points[j0][1]
  length=max(math.hypot(dx,dy),1e-6); nx=-dy/length; ny=dx/length; w=width_at(i/(n-1),widths)
  l.append(((x+nx*w/2)*S,(y+ny*w/2)*S)); r.append(((x-nx*w/2)*S,(y-ny*w/2)*S))
 return l+r[::-1]

def offset(points,amt):
 o=[]
 for i,(x,y) in enumerate(points):
  j0=max(0,i-1); j1=min(len(points)-1,i+1); dx=points[j1][0]-points[j0][0]; dy=points[j1][1]-points[j0][1]
  le=max(math.hypot(dx,dy),1e-6); o.append((x-dy/le*amt,y+dx/le*amt))
 return o

def lerp(a,b,t): return tuple(round(x*(1-t)+y*t) for x,y in zip(a,b))

def gradient(size):
 W,H=size; im=Image.new('RGBA',(W*S,H*S)); px=im.load()
 top=(211,199,221,255); mid=(194,194,222,255); bot=(171,190,219,255)
 for y in range(H*S):
  t=y/(H*S-1); c=lerp(top,mid,min(t/.62,1)) if t<.62 else lerp(mid,bot,(t-.62)/.38)
  for x in range(W*S): px[x,y]=c
 return im

def strand(canvas,grad,curve,widths,hi,shadow):
 pts=cubic(curve); poly=ribbon_polygon(pts,widths)
 mask=Image.new('L',canvas.size,0); ImageDraw.Draw(mask).polygon(poly,fill=255)
 canvas.alpha_composite(Image.composite(grad,Image.new('RGBA',canvas.size,(0,0,0,0)),mask))
 d=ImageDraw.Draw(canvas); mid=widths[1]
 # Hairline accents are low-contrast and follow curved flow; no black outlines are invented.
 h=offset(pts,-mid*.10); sh=offset(pts,mid*.27)
 d.line([(x*S,y*S) for x,y in h],fill=hi,width=max(S,int(mid*.09*S)),joint='curve')
 d.line([(x*S,y*S) for x,y in sh],fill=shadow,width=max(S,int(mid*.045*S)),joint='curve')

source=Image.open(SRC).convert('RGBA'); pdoc=json.loads(POLYS.read_text(encoding='utf-8'))
clean=source.copy(); patch_full=Image.new('RGBA',source.size,(0,0,0,0)); region_full=Image.new('L',source.size,0)
curves={
 'left':[
  ([(165,247),(188,287),(205,338),(177,449)],(8,76,2),(240,235,247,235),(142,144,176,205)),
  ([(145,265),(145,330),(119,396),(91,445)],(5,38,1),(236,232,247,225),(148,147,179,195)),
  ([(234,282),(229,343),(251,399),(260,446)],(4,39,1),(242,238,250,220),(151,148,181,190)),
 ],
 'right':[
  ([(180,247),(157,287),(140,338),(168,449)],(8,76,2),(240,235,247,235),(142,144,176,205)),
  ([(200,265),(200,330),(226,396),(254,445)],(5,38,1),(236,232,247,225),(148,147,179,195)),
  ([(111,282),(116,343),(94,399),(85,446)],(4,39,1),(242,238,250,220),(151,148,181,190)),
 ]
}
alpha_removed=0; patch_px=0; roi_px=0
for side,box in BOXES.items():
 x0,y0,x1,y1=box; size=(x1-x0,y1-y0)
 if size!=(345,519): raise SystemExit(f'crop mapping changed {side}: {size}')
 hi=Image.new('L',(size[0]*S,size[1]*S),0); md=ImageDraw.Draw(hi)
 for poly in pdoc['polygons'][side]: md.polygon([(x*S,y*S) for x,y in poly],fill=255)
 roi=hi.resize(size,Image.Resampling.LANCZOS)
 base=source.crop(box); cleared=base.copy(); cleared.putalpha(ImageChops.multiply(base.getchannel('A'),ImageChops.invert(roi)))
 clean.paste(Image.composite(cleared,base,roi),(x0,y0))
 grad=gradient(size); work=Image.new('RGBA',(size[0]*S,size[1]*S),(0,0,0,0))
 for curve,widths,hi_color,sh_color in curves[side]: strand(work,grad,curve,widths,hi_color,sh_color)
 patch=work.resize(size,Image.Resampling.LANCZOS); patch.putalpha(ImageChops.multiply(patch.getchannel('A'),roi))
 patch_full.alpha_composite(patch,(x0,y0)); region_full.paste(roi,(x0,y0))
 alpha_removed += sum(a!=b for a,b in zip(base.getchannel('A').tobytes(),cleared.getchannel('A').tobytes()))
 patch_px += sum(v>24 for v in patch.getchannel('A').tobytes()); roi_px += sum(v>0 for v in roi.tobytes())
# Clean front layer changes only within visible artifact polygons.
diff=ImageChops.difference(source,clean); allowed=region_full.point(lambda v:255 if v>0 else 0)
out=ImageChops.multiply(ImageChops.invert(allowed),ImageChops.lighter(ImageChops.lighter(diff.getchannel('R'),diff.getchannel('G')),ImageChops.lighter(diff.getchannel('B'),diff.getchannel('A'))))
if out.getbbox(): raise SystemExit(f'clean front changed outside ROI: {out.getbbox()}')
clean.save(CLEAN)
# Write the patch image and exact front edit after all checks.
patch_full.save(PATCH)
cb=source.tobytes(); fb=clean.tobytes()
report={'task':'T67.71','status':'split-layer manual reconstruction WIP; not source recovery or production','clean_front':str(CLEAN.relative_to(ROOT)),'backfill_patch':str(PATCH.relative_to(ROOT)),
 'mask':'manual_artifact_polygons_v2 visible cuff/hand ROI only; it includes some neighboring hair and does not define target hair geometry',
 'layer_hypothesis':'clean front retains existing layer 258 and alpha-clears foreign limb pixels; backfill patch will be tested behind arms at layer 135',
 'clean_alpha_pixels_removed':alpha_removed,'backfill_alpha_pixels_gt24':patch_px,'roi_pixels':roi_px,
 'front_outside_roi_byte_identity':'asserted exact','negative_space':'patch contains separated curved ribbons with transparent gaps; no whole-canvas fill',
 'geometry':'manual curves use adjacent visible flow as style/anchor; hidden paths, internal overlaps, and mirrored L/R correspondence are inference',
 'production_changes':False,'curves_local_345x519':{s:[{'curve':c[0],'widths':c[1]} for c in curves[s]] for s in curves},
 'next_gate':'review isolated patch and C-composited frames before any further work; reject if transitions show gaps, blobs, or style mismatch'}
REPORT.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps({k:report[k] for k in ('status','clean_alpha_pixels_removed','backfill_alpha_pixels_gt24','roi_pixels','front_outside_roi_byte_identity')},ensure_ascii=False,indent=2))
