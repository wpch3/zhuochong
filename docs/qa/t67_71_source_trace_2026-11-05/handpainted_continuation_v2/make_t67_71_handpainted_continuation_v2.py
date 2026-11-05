#!/usr/bin/env python3
"""Isolated T67.71 new-design study: hand-painted continuous back-hair sheet with tapered detail strands.

This is a proposed continuation, not recovered hidden source art. It uses no
AI output, donor pixels, inpainting, or broad mask expansion. The cuff/hand
silhouette is a separate cleanup guide; the newly painted rear strands are
an independent layer. Nothing writes to production assets.
"""
from __future__ import annotations
import hashlib, json, math
from pathlib import Path
from PIL import Image, ImageDraw, ImageFilter

ROOT=Path(__file__).resolve().parents[4]
OUT=Path(__file__).resolve().parent
SRC=ROOT/'characters/xiaoxun/forms/teen/sprites/hair_hood_long@2x.png'
POLY=ROOT/'docs/qa/t67_71_source_trace_2026-11-05/wip_masked_inpaint_attempt_v2/manual_artifact_polygons_v2.json'
ROIS={'left':(51,849,396,1368),'right':(736,849,1081,1368)}
S=4

# Piecewise cubic centerlines and nonuniform width stations (ROI-local pixels).
# They intentionally follow the existing downward hair flow and taper into
# staggered ends; these are an original proposal, not inferred source geometry.
DESIGN={
 'left':[
  {'name':'continuous_back_sheet','curves':[
    ((150,220),(157,251),(180,282),(199,310)),
    ((199,310),(224,345),(226,390),(216,432)),
    ((216,432),(207,475),(228,521),(223,565)),
  ],'widths':[(0,1),(0.10,18),(0.22,43),(0.42,66),(0.60,72),(0.76,58),(0.90,30),(1,0)],'shade':0},
  {'name':'inner_tapered_strand','curves':[
    ((161,244),(177,274),(201,303),(207,333)),
    ((207,333),(218,370),(211,405),(218,441)),
    ((218,441),(230,480),(247,513),(248,548)),
  ],'widths':[(0,0),(0.18,9),(0.40,15),(0.62,14),(0.84,8),(1,0)],'shade':1},
  {'name':'soft_edge_filament','curves':[
    ((189,275),(207,303),(228,333),(232,366)),
    ((232,366),(236,402),(232,431),(245,462)),
    ((245,462),(257,488),(265,512),(260,536)),
  ],'widths':[(0,0),(0.22,4),(0.52,5),(0.80,3),(1,0)],'shade':2},
 ],
 'right':[
  {'name':'continuous_back_sheet','curves':[
    ((195,220),(188,251),(165,282),(145,310)),
    ((145,310),(120,345),(118,390),(128,432)),
    ((128,432),(137,475),(116,521),(121,565)),
  ],'widths':[(0,1),(0.10,18),(0.22,43),(0.42,66),(0.60,72),(0.76,58),(0.90,30),(1,0)],'shade':0},
  {'name':'inner_tapered_strand','curves':[
    ((183,244),(167,274),(143,303),(137,333)),
    ((137,333),(126,370),(133,405),(126,441)),
    ((126,441),(114,480),(98,513),(97,548)),
  ],'widths':[(0,0),(0.18,9),(0.40,15),(0.62,14),(0.84,8),(1,0)],'shade':1},
  {'name':'soft_edge_filament','curves':[
    ((155,275),(137,303),(116,333),(112,366)),
    ((112,366),(108,402),(112,431),(99,462)),
    ((99,462),(87,488),(79,512),(84,536)),
  ],'widths':[(0,0),(0.22,4),(0.52,5),(0.80,3),(1,0)],'shade':2},
 ]
}

# Light cool-lilac hair paint with a faint warm root and blue-violet tips.
COLORS={
 'left':((238,219,232),(218,216,235),(191,211,231)),
 'right':((238,219,232),(217,215,234),(190,210,230)),
}

def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def cubic(p0,p1,p2,p3,t):
 u=1-t
 return (u*u*u*p0[0]+3*u*u*t*p1[0]+3*u*t*t*p2[0]+t*t*t*p3[0],
         u*u*u*p0[1]+3*u*u*t*p1[1]+3*u*t*t*p2[1]+t*t*t*p3[1])
def sample_curves(curves,n_each=70):
 pts=[]
 for j,c in enumerate(curves):
  for k in range(n_each+1):
   if j and k==0: continue
   pts.append(cubic(*c,k/n_each))
 return pts
def interp(stations,t):
 for (a,va),(b,vb) in zip(stations,stations[1:]):
  if t<=b:
   q=(t-a)/(b-a) if b>a else 0
   q=q*q*(3-2*q)
   return va+(vb-va)*q
 return stations[-1][1]
def ribbon_edges(points,widths):
 left=[];right=[];n=len(points)
 for i,p in enumerate(points):
  t=i/(n-1);w=max(0,interp(widths,t))/2
  p0=points[max(0,i-1)];p1=points[min(n-1,i+1)]
  dx=p1[0]-p0[0];dy=p1[1]-p0[1];L=math.hypot(dx,dy) or 1
  nx=-dy/L;ny=dx/L
  left.append((p[0]+nx*w,p[1]+ny*w));right.append((p[0]-nx*w,p[1]-ny*w))
 return left,right
def rgb_mix(a,b,t): return tuple(round(a[i]*(1-t)+b[i]*t) for i in range(3))
def make_ribbon(canvas,side,roi,lock,idx):
 x0,y0,_,_=roi; pts=sample_curves(lock['curves']); left,right=ribbon_edges(pts,lock['widths'])
 # Render a tight local patch at 4x then downsample for clean antialiasing.
 allx=[p[0] for p in left+right]; ally=[p[1] for p in left+right]
 bx0=max(0,math.floor(x0+min(allx)-4)); by0=max(0,math.floor(y0+min(ally)-4))
 bx1=min(canvas.width,math.ceil(x0+max(allx)+4)); by1=min(canvas.height,math.ceil(y0+max(ally)+4))
 pw,ph=bx1-bx0,by1-by0
 if pw<=0 or ph<=0:return
 mask=Image.new('L',(pw*S,ph*S),0); md=ImageDraw.Draw(mask)
 poly=[((x0+x-bx0)*S,(y0+y-by0)*S) for x,y in left+right[::-1]]
 md.polygon(poly,fill=255)
 # A single hand-painted color field, softly graded along the lock and shaded
 # toward its edges; not copied from another sprite.
 bbox=mask.getbbox()
 if not bbox:return
 top,mid,bot=COLORS[side]
 paint=Image.new('RGBA',mask.size,(0,0,0,0)); pp=paint.load();mp=mask.load()
 mx0,my0,mx1,my1=bbox; h=max(1,my1-my0); w=max(1,mx1-mx0)
 for yy in range(my0,my1):
  t=max(0,min(1,(yy-my0)/max(1,h-1)))
  if t<.48:c=rgb_mix(top,mid,t/.48)
  else:c=rgb_mix(mid,bot,(t-.48)/.52)
  for xx in range(mx0,mx1):
   if not mp[xx,yy]:continue
   edge=min(xx-mx0,mx1-1-xx)/max(1,w/2); edge=max(0,min(1,edge))
   shade=(1-edge)*.14
   rgb=tuple(round(v*(1-shade)+[157,159,190][i]*shade) for i,v in enumerate(c))
   paint.putpixel((xx,yy),rgb+(mp[xx,yy],))
 d=ImageDraw.Draw(paint)
 # Fine ink-like edge accents: sparse, variable-weight, low-contrast, tapered.
 for edge_id,edge in enumerate((left,right)):
  line=[((x0+x-bx0)*S,(y0+y-by0)*S) for x,y in edge[::2]]
  col=(105,105,132,95 if edge_id==0 else 70)
  d.line(line,fill=col,width=(2 if idx==0 else 1)*S,joint='curve')
 # A single soft glint ribbon and selected, irregular inner accents.
 offsets=((-0.18,0.11),(-0.31,0.04),(-0.05,0.09))
 off,opacity=offsets[idx]
 glint=[]
 for i,p in enumerate(pts):
  t=i/(len(pts)-1);w=max(0,interp(lock['widths'],t))/2
  p0=pts[max(0,i-1)];p1=pts[min(len(pts)-1,i+1)]
  dx=p1[0]-p0[0];dy=p1[1]-p0[1];L=math.hypot(dx,dy) or 1
  nx=-dy/L;ny=dx/L
  glint.append(((x0+p[0]+nx*w*off-bx0)*S,(y0+p[1]+ny*w*off-by0)*S))
 col=(255,247,249,142 if idx==0 else 105)
 d.line(glint,fill=col,width=(3 if idx==0 else 2)*S,joint='curve')
 if idx==0:
  for curve,color,width in [
   (lock['curves'][1],(143,145,174,125),1.0),
   (lock['curves'][2],(243,239,247,145),1.2),
  ]:
   q=[]
   q.extend(cubic(*curve,k/35) for k in range(36))
   d.line([((x0+x-bx0)*S,(y0+y-by0)*S) for x,y in q],fill=color,width=round(width*S),joint='curve')
 # Composite the rendered raster patch back onto the full-canvas layer.
 patch=paint.resize((pw,ph),Image.Resampling.LANCZOS)
 canvas.alpha_composite(patch,(bx0,by0))

def object_mask(size,roi,objects):
 x0,y0,x1,y1=roi;w=x1-x0;h=y1-y0
 # Draw traced object silhouette at 4x for antialiasing, then very slight 1px
 # edge protection to avoid leaving a dark source fringe. No broad dilation.
 big=Image.new('L',(w*S,h*S),0);d=ImageDraw.Draw(big)
 for polygon in objects:
  d.polygon([(round(x*S),round(y*S)) for x,y in polygon],fill=255)
 m=big.resize((w,h),Image.Resampling.LANCZOS).filter(ImageFilter.MaxFilter(3))
 full=Image.new('L',size,0);full.paste(m,(x0,y0));return full

def checkboard(size,cell=24):
 im=Image.new('RGBA',size,(40,43,51,255));d=ImageDraw.Draw(im)
 for y in range(0,size[1],cell):
  for x in range(0,size[0],cell):
   if (x//cell+y//cell)%2:d.rectangle((x,y,x+cell-1,y+cell-1),fill=(58,61,70,255))
 return im

def main():
 src=Image.open(SRC).convert('RGBA'); objs=json.loads(POLY.read_text())['polygons']
 plate=Image.new('RGBA',src.size,(0,0,0,0)); clean=src.copy(); regions={}
 for side,roi in ROIS.items():
  # paint only within a restrained registered local crop; transparent layer is full-canvas for easy C alignment later
  layer=Image.new('RGBA',src.size,(0,0,0,0))
  for i,lock in enumerate(DESIGN[side]):make_ribbon(layer,side,roi,lock,i)
  plate.alpha_composite(layer)
  m=object_mask(src.size,roi,objs[side]); a=clean.getchannel('A');
  from PIL import ImageChops
  clean.putalpha(ImageChops.multiply(a,ImageChops.invert(m)))
  regions[side]={'roi_xyxy':list(roi),'removed_visible_object_pixels':sum(v>0 for v in m.tobytes()),'painted_ribbons':len(DESIGN[side]),'design_note':'One continuous painted rear sheet with two custom taper details; no donor pixels.'}
 comp=plate.copy();comp.alpha_composite(clean)
 # Detail crops at 3x nearest-neighbor to inspect actual raster joins and line weight.
 board=Image.new('RGB',(1840,1500),(28,31,38));d=ImageDraw.Draw(board)
 try:
  from PIL import ImageFont
  title=ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf',28)
  sub=ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',17)
 except OSError:title=sub=None
 d.text((30,20),'T67.71 · HAND-PAINTED CONTINUATION STUDY V2 · NEW DESIGN / NOT SOURCE TRUTH',font=title,fill=(245,246,249))
 d.text((32,58),'Isolated underlay + independently cleaned cuff/hand foreground; 3× nearest-neighbor detail crops. Not C-validated or production.',font=sub,fill=(190,199,212))
 for row,side in enumerate(('left','right')):
  x0,y0,x1,y1=ROIS[side];y=100+row*690
  d.text((32,y),side.upper(),font=title,fill=(117,202,232));y+=42
  crops=[('SOURCE',src.crop(ROIS[side])),('UNDERLAY ONLY',plate.crop(ROIS[side])),('CLEAN HAIR + UNDERLAY',comp.crop(ROIS[side]))]
  cw,ch=570,620
  for j,(label,img) in enumerate(crops):
   x=30+j*600
   d.rounded_rectangle((x,y,x+cw,y+ch),radius=10,fill=(40,43,52),outline=(77,84,97),width=2)
   d.text((x+12,y+8),label,font=sub,fill=(231,234,239))
   bg=checkboard(img.size);bg.alpha_composite(img)
   # preserve individual source pixels at 3x nearest, fit within panel
   scale=min((cw-24)/img.width,(ch-52)/img.height,3.0)
   size=(round(img.width*scale),round(img.height*scale));view=bg.resize(size,Image.Resampling.NEAREST)
   board.paste(view.convert('RGB'),(x+(cw-size[0])//2,y+40+(ch-48-size[1])//2))
 board.save(OUT/'t67_71_handpainted_continuation_v2_review.png',optimize=True)
 plate.save(OUT/'t67_71_handpainted_continuation_v2_underlay.png',optimize=True)
 clean.save(OUT/'t67_71_handpainted_continuation_v2_clean_front.png',optimize=True)
 comp.save(OUT/'t67_71_handpainted_continuation_v2_composite.png',optimize=True)
 outputs={p.name:{'size':list(Image.open(p).size),'sha256':sha(p)} for p in OUT.glob('t67_71_handpainted_continuation_v2_*.png')}
 metrics={'task':'T67.71','status':'isolated new-design WIP; not accepted; not hidden-original truth; not production','method':'hand-painted continuous rear hair mass with hand-shaped tapered internal locks, a gentle cool gradient, and sparse irregular line accents; no AI, inpainting, or pixel donor','source':{'path':str(SRC.relative_to(ROOT)),'size':list(src.size),'sha256':sha(SRC)},'object_trace':{'path':str(POLY.relative_to(ROOT)),'sha256':sha(POLY),'use':'visible cuff/hand cleanup only; not hidden-hair alpha'},'regions':regions,'outputs':outputs,'limitations':['New line and lock topology is a design proposal, not recovered original hidden source.','No true C arm/cuff composition, action/transition, or ParamHairSway validation.','No production sprite, rig, or generator was modified.']}
 (OUT/'t67_71_handpainted_continuation_v2_metrics.json').write_text(json.dumps(metrics,ensure_ascii=False,indent=2)+'\n')
 print(json.dumps(metrics,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
