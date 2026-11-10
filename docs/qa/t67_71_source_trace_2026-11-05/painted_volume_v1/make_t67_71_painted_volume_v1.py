#!/usr/bin/env python3
"""T67.71 isolated painterly back-hair design study.

A single softly shaded, scalloped hair volume with asymmetric hand-authored
paint strokes; deliberately not a geometric comb, a source-pixel warp, or an
inpaint. New design only; hidden topology is unknown. Uses Pillow.
"""
from __future__ import annotations
import hashlib, json, math, random
from pathlib import Path
from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont, ImageOps

ROOT=Path(__file__).resolve().parents[4]
OUT=Path(__file__).resolve().parent
SRC=ROOT/'characters/xiaoxun/forms/teen/sprites/hair_hood_long@2x.png'
MASK=ROOT/'docs/qa/t67_71_source_trace_2026-11-05/wip_masked_inpaint_attempt_v2/manual_artifact_polygons_v2.json'
ROIS={'left':(51,849,396,1368),'right':(736,849,1081,1368)}
S=3

# One irregular volume profile, not a hidden-source silhouette. Its crest tucks
# behind the existing lock; the lower boundary breaks into varied hair tips.
VOLUME=[
 ('M',(144,174)),('C',(161,164),(186,176),(199,202)),
 ('C',(215,236),(213,273),(229,308)),('C',(246,348),(266,379),(284,416)),
 ('C',(300,447),(304,468),(291,482)),('C',(278,496),(269,482),(257,486)),
 ('C',(244,490),(244,515),(228,518)),('C',(212,520),(204,492),(192,492)),
 ('C',(178,492),(181,511),(167,503)),('C',(151,493),(150,467),(145,439)),
 ('C',(139,401),(142,364),(132,331)),('C',(122,297),(119,262),(126,228)),
 ('C',(131,205),(132,185),(144,174)),('Z',())]

# Unevenly spaced, hand-routed grain paths, with distinct highlights and shadows.
# Coordinates follow the large lock flow and fork/split rather than parallel rails.
VOLUME_STROKES=[
 ([(137,194),(151,250),(144,309),(156,364),(163,423),(166,466)],(114,107,132,52),10),
 ([(151,182),(163,236),(157,294),(173,350),(181,413),(193,479)],(244,240,249,82),7),
 ([(170,181),(183,234),(176,283),(194,336),(204,390),(215,459)],(116,108,135,58),12),
 ([(180,180),(194,234),(189,282),(207,333),(221,388),(236,459)],(246,242,250,75),6),
 ([(198,205),(210,247),(209,292),(229,336),(246,382),(266,439)],(113,106,133,52),11),
 ([(207,211),(221,253),(221,295),(240,337),(256,383),(279,435)],(244,240,249,78),6),
 ([(224,250),(238,285),(243,321),(263,357),(281,397),(294,435)],(112,105,132,44),9),
 ([(145,325),(155,362),(157,404),(171,445),(181,475)],(238,232,245,55),4),
 ([(190,292),(199,324),(208,359),(215,394),(229,430)],(124,116,143,48),4),
 ([(236,322),(251,350),(267,376),(282,404),(294,430)],(244,240,248,52),4),
 ([(162,235),(170,270),(168,301)],(110,103,127,42),3),
 ([(219,365),(229,395),(240,421)],(249,245,251,58),3),
]

def sha(p:Path)->str:return hashlib.sha256(p.read_bytes()).hexdigest()
def cubic(p0,p1,p2,p3,t):
 u=1-t
 return (u**3*p0[0]+3*u*u*t*p1[0]+3*u*t*t*p2[0]+t**3*p3[0],u**3*p0[1]+3*u*u*t*p1[1]+3*u*t*t*p2[1]+t**3*p3[1])
def volume_points():
 pts=[];cur=None
 for item in VOLUME:
  op=item[0];args=item[1:]
  if op=='M':cur=args[0];pts.append(cur)
  elif op=='C':
   p1,p2,p3=args
   for k in range(1,61):pts.append(cubic(cur,p1,p2,p3,k/60))
   cur=p3
 return pts

def scaled_points(points):return [(round(x*S),round(y*S)) for x,y in points]

def make_one_side(side:str)->Image.Image:
 # High-res antialiased silhouette mask.
 mask_hi=Image.new('L',(345*S,519*S),0);md=ImageDraw.Draw(mask_hi)
 md.polygon(scaled_points(volume_points()),fill=255)
 mask=mask_hi.resize((345,519),Image.Resampling.LANCZOS)
 # A smooth per-pixel color field sampled from the visible target palette and
 # varied across width/length. Small deterministic grain avoids flat vector fill.
 base=(178,173,198) if side=='left' else (172,176,204)
 rng=random.Random(67071 if side=='left' else 67072)
 field=Image.new('RGBA',(345,519),(0,0,0,0));px=field.load()
 for y in range(519):
  v=y/518
  for x in range(345):
   u=x/344
   mid=math.exp(-((u-.48)/.32)**2)
   edge=(abs(u-.5)*2)**1.5
   lift=24*mid-17*edge+7*math.sin(math.pi*v)-5*v
   grain=rng.gauss(0,1.15)
   rgb=tuple(max(0,min(255,round(c+lift+grain))) for c in base)
   # Top alpha eases into the visible existing hair rather than forming a cap.
   top=max(0,min(1,(y-125)/95));top=top*top*(3-2*top)
   px[x,y]=(*rgb,round(255*top))
 field.putalpha(ImageChops.multiply(field.getchannel('A'),mask))
 # Soft, broad value bands add painted volume before the fine linework.
 shade_hi=Image.new('RGBA',(345*S,519*S),(0,0,0,0));sd=ImageDraw.Draw(shade_hi)
 for pts,color,width in VOLUME_STROKES[:7]:
  sd.line(scaled_points(pts),fill=color,width=width*S,joint='curve')
 shade=shade_hi.resize((345,519),Image.Resampling.LANCZOS).filter(ImageFilter.GaussianBlur(2.3))
 field=Image.alpha_composite(field,shade)
 # Fine contour strokes and split highlights follow non-uniform trajectories.
 fine_hi=Image.new('RGBA',(345*S,519*S),(0,0,0,0));fd=ImageDraw.Draw(fine_hi)
 for pts,color,width in VOLUME_STROKES[7:]:
  fd.line(scaled_points(pts),fill=color,width=max(2,width*S),joint='curve')
 # Partial boundary accents, deliberately broken so no outlined sticker edge.
 fd.line(scaled_points([(130,219),(126,256),(131,293)]),fill=(108,101,125,105),width=2*S,joint='curve')
 fd.line(scaled_points([(285,421),(296,450),(290,466)]),fill=(107,101,126,95),width=2*S,joint='curve')
 fine=fine_hi.resize((345,519),Image.Resampling.LANCZOS)
 fine.putalpha(ImageChops.multiply(fine.getchannel('A'),mask))
 field=Image.alpha_composite(field,fine)
 return field

def full_mask(maskdoc):
 out={}
 for side,(x0,y0,x1,y1) in ROIS.items():
  m=Image.new('L',(x1-x0,y1-y0),0);d=ImageDraw.Draw(m)
  for poly in maskdoc['polygons'][side]:d.polygon(poly,fill=255)
  m=m.filter(ImageFilter.MaxFilter(3))
  full=Image.new('L',(1132,1664),0);full.paste(m,(x0,y0));out[side]=full
 return out

def checker(im):
 bg=Image.new('RGBA',im.size,(40,43,51,255));d=ImageDraw.Draw(bg);cell=18
 for y in range(0,im.height,cell):
  for x in range(0,im.width,cell):
   if (x//cell+y//cell)%2:d.rectangle((x,y,x+cell-1,y+cell-1),fill=(58,61,69,255))
 bg.alpha_composite(im);return bg

def review_board(src,under,cleancomp,static):
 board=Image.new('RGB',(2048,1520),(27,30,37));d=ImageDraw.Draw(board)
 font=ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',15)
 bold=ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf',24)
 d.text((24,15),'T67.71 · PAINTED VOLUME V1 · NEW DESIGN / NOT HIDDEN TRUTH',font=bold,fill=(245,246,249))
 d.text((26,47),'Soft shaded lock mass with hand-routed flow details. Isolated registration only; not C-validated or production.',font=font,fill=(190,198,211))
 names=[('SOURCE',src),('UNDERLAY',under),('CLEAN HAIR + UNDERLAY',cleancomp),('STATIC REGISTRATION MOCK',static)]
 cellw=492;cellh=660;gap=12;left=20;top=85
 for ri,side in enumerate(('left','right')):
  rowy=top+ri*700;d.text((left,rowy),side.upper(),font=bold,fill=(117,202,232));y=rowy+32
  for ci,(label,img) in enumerate(names):
   x=left+ci*(cellw+gap);d.rounded_rectangle((x,y,x+cellw,y+cellh),radius=8,fill=(39,42,50),outline=(72,79,91),width=2)
   d.text((x+10,y+8),label,font=font,fill=(233,236,241))
   crop=checker(img.crop(ROIS[side]));scale=min((cellw-18)/crop.width,(cellh-42)/crop.height)
   crop=crop.resize((round(crop.width*scale),round(crop.height*scale)),Image.Resampling.LANCZOS)
   board.paste(crop.convert('RGB'),(x+(cellw-crop.width)//2,y+32+(cellh-42-crop.height)//2))
 return board

def main():
 src=Image.open(SRC).convert('RGBA');maskdoc=json.loads(MASK.read_text());clears=full_mask(maskdoc)
 under=Image.new('RGBA',src.size,(0,0,0,0))
 for side,(x0,y0,x1,y1) in ROIS.items():
  patch=make_one_side(side)
  if side=='right':patch=ImageOps.mirror(patch)
  under.alpha_composite(patch,(x0,y0))
 clear=Image.new('L',src.size,0)
 for m in clears.values():clear=ImageChops.lighter(clear,m)
 source_alpha=src.getchannel('A')
 clean=src.copy();clean.putalpha(ImageChops.multiply(source_alpha,ImageChops.invert(clear)))
 comp=under.copy();comp.alpha_composite(clean)
 fg=src.copy();fg.putalpha(ImageChops.multiply(source_alpha,clear))
 static=comp.copy();static.alpha_composite(fg)
 outputs={}
 for name,im in [('t67_71_painted_volume_v1_underlay.png',under),('t67_71_painted_volume_v1_clean_front.png',clean),('t67_71_painted_volume_v1_composite.png',comp),('t67_71_painted_volume_v1_static_mock.png',static)]:
  p=OUT/name;im.save(p,optimize=True);outputs[name]={'sha256':sha(p),'size':im.size}
 board=review_board(src,under,comp,static);p=OUT/'t67_71_painted_volume_v1_review.png';board.save(p,optimize=True);outputs[p.name]={'sha256':sha(p),'size':board.size}
 for side,box in ROIS.items():
  x0,y0,x1,y1=box
  for name,im in [('source',src),('underlay',under),('composite',comp),('static_mock',static)]:
   p=OUT/f't67_71_painted_volume_v1_{side}_{name}_3x.png'
   im.crop(box).resize(((x1-x0)*3,(y1-y0)*3),Image.Resampling.NEAREST).save(p,optimize=True)
   outputs[p.name]={'sha256':sha(p),'size':Image.open(p).size}
 metrics={'task':'T67.71','status':'isolated new-design WIP; not accepted; not hidden source truth; not production',
  'design_method':'painterly shaded hair volume with asymmetric hand-routed strand lines; generated from a new design shape and visible hood-up palette/flow only, no source-pixel remap/inpaint/AI',
  'reference':{'path':str(SRC.relative_to(ROOT)),'sha256':sha(SRC),'size':list(src.size),'use':'visible palette and stroke direction only'},
  'object_clear_mask':{'path':str(MASK.relative_to(ROOT)),'sha256':sha(MASK),'warning':'cleanup ROI only, not a hair silhouette; it overlaps legal hair'},
  'outputs':outputs,'c_validation':False,'production_changed':False,
  'limitations':['The continuous hair mass and hidden strand topology are a speculative new design, not original pixels.','Static foreground is an identity-registered flattened-source cuff/hand mock, not real C arms or transitions.','Local visual gate and user confirmation are still required before C; production requires independent approval.']}
 (OUT/'t67_71_painted_volume_v1_metrics.json').write_text(json.dumps(metrics,ensure_ascii=False,indent=2)+'\n')
 print(json.dumps(metrics,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
