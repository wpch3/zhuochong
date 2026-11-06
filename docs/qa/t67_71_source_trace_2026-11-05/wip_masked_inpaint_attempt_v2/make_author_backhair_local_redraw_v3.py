#!/usr/bin/env python3
"""T67.71 registered local redraw proposal v3 (AI-assisted, new design only).

The v2 plate kept the old sprite alpha, which left transparent cuff/hand holes.
This version unions the old visible-object silhouette with the existing hair
alpha, so the newly drawn back-hair also fills transparent gaps inside the old
cuff/hand. The objects are separately removed from clean-front. This is an
isolated proposal only: no hidden-source truth or production change.
"""
from __future__ import annotations
import hashlib,json
from pathlib import Path
from PIL import Image,ImageDraw,ImageChops,ImageFilter,ImageFont
ROOT=Path(__file__).resolve().parents[4]
BASE=Path(__file__).resolve().parent
SOURCE=ROOT/'characters/xiaoxun/forms/teen/sprites/hair_hood_long@2x.png'
POLYGONS=BASE/'manual_artifact_silhouette_polygons_v3.json'
ROIS={'left':(51,849,396,1368),'right':(736,849,1081,1368)}
CROPS={'left':(0,780,440,1420),'right':(692,780,1132,1420)}
PROPOSALS={'left':BASE/'122_left_backhair_local_redraw_proposal.png','right':BASE/'123_right_backhair_local_redraw_proposal.png'}
PLATE=BASE/'139_backhair_ai_local_redraw_v3_plate_wip.png'
CLEAN=BASE/'140_clean_front_ai_local_redraw_v3_wip.png'
COMPOSITE=BASE/'141_ai_local_backhair_composite_v3_wip.png'
BOARD=BASE/'142_ai_local_backhair_review_v3.png'
METRICS=BASE/'143_ai_local_backhair_redraw_v3_metrics.json'
DILATE=2

def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def object_mask(size,objects):
 m=Image.new('L',size,0); d=ImageDraw.Draw(m)
 for key in ('cuff','hand'): d.polygon([tuple(map(int,p)) for p in objects[key]],fill=255)
 if DILATE: m=m.filter(ImageFilter.MaxFilter(2*DILATE+1))
 # Keep object interior opaque while gently antialiasing its border.
 return m.filter(ImageFilter.GaussianBlur(0.45))
def register_proposal(path,size):
 im=Image.open(path).convert('RGB'); w,h=size
 target_h=round(im.width*h/w)
 if im.height>target_h:
  top=(im.height-target_h)//2; im=im.crop((0,top,im.width,top+target_h))
 return im.resize(size,Image.Resampling.LANCZOS).convert('RGBA')
def checker(crop):
 bg=Image.new('RGBA',crop.size,(39,42,50,255)); cell=18; d=ImageDraw.Draw(bg)
 for y in range(0,crop.height,cell):
  for x in range(0,crop.width,cell):
   if (x//cell+y//cell)%2: d.rectangle((x,y,x+cell-1,y+cell-1),fill=(58,61,69,255))
 bg.alpha_composite(crop); return bg

def make_board(source,plate,clean,composite,mock):
 W,H=3000,1760; board=Image.new('RGB',(W,H),(26,29,36)); d=ImageDraw.Draw(board)
 try:
  title=ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf',30)
  label=ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',17)
 except OSError: title=label=ImageFont.load_default()
 d.text((34,20),'T67.71 · LOCAL BACK-HAIR REDRAW V3 · REGISTERED NEW-DESIGN PROPOSAL',font=title,fill=(244,246,250))
 d.text((36,58),'Transparent cuff/hand holes are now covered by the back plate. This is a local review WIP, not a recovered original and not C-validated.',font=label,fill=(192,200,212))
 # Full canvas overview: source and proposed composite.
 panel_y=98; panel_h=420; gap=18; margin=34; full_w=660
 for i,(name,img) in enumerate((('FULL SOURCE',source),('FULL HAIR-ONLY PROPOSAL',composite))):
  x=margin+i*(full_w+gap); d.rounded_rectangle((x,panel_y,x+full_w,panel_y+panel_h),radius=10,fill=(39,43,53),outline=(73,81,95),width=2); d.text((x+12,panel_y+9),name,font=label,fill=(232,235,242))
  thumb=checker(img).thumbnail((300,370)) if False else None
  tmp=checker(img); tmp.thumbnail((300,370),Image.Resampling.LANCZOS); board.paste(tmp.convert('RGB'),(x+180,panel_y+40))
  # outline ROI positions on overview
  sx=tmp.width/img.width; sy=tmp.height/img.height
  for side,box in ROIS.items():
   x0,y0,x1,y1=box; ax=x+180+round(x0*sx); ay=panel_y+40+round(y0*sy); bx=x+180+round(x1*sx); by=panel_y+40+round(y1*sy)
   d.rectangle((ax,ay,bx,by),outline=(255,166,80),width=2)
 # Region rows: source, back plate alpha, clean-front+plate, static foreground mock.
 cols=[('SOURCE ROI',source),('BACK PLATE ONLY',plate),('CLEAN HAIR ONLY',composite),('STATIC MOCK · LEGACY ARM ON TOP',mock)]
 cw=(W-2*margin-3*gap)//4; row_h=520; top=540
 for row,side in enumerate(('left','right')):
  y=top+row*(row_h+34); d.text((margin,y),side.upper(),font=title,fill=(118,202,233)); py=y+38
  for j,(name,img) in enumerate(cols):
   x=margin+j*(cw+gap); d.rounded_rectangle((x,py,x+cw,py+row_h),radius=10,fill=(39,43,53),outline=(73,81,95),width=2); d.text((x+12,py+8),name,font=label,fill=(232,235,242))
   crop=img.crop(CROPS[side]).convert('RGBA'); shown=checker(crop); maxw,maxh=cw-22,row_h-44; s=min(maxw/crop.width,maxh/crop.height); shown=shown.resize((round(crop.width*s),round(crop.height*s)),Image.Resampling.LANCZOS)
   board.paste(shown.convert('RGB'),(x+(cw-shown.width)//2,py+35+(maxh-shown.height)//2))
 footer='Static mock reuses source cuff/hand pixels only to check registration; production/C must use actual moving foreground parts after local approval.'
 d.rounded_rectangle((margin,H-52,W-margin,H-16),radius=8,fill=(63,43,34),outline=(235,162,75),width=2); d.text((margin+12,H-48),footer,font=label,fill=(255,223,175))
 board.save(BOARD,optimize=True)

def main():
 source=Image.open(SOURCE).convert('RGBA'); pol=json.loads(POLYGONS.read_text(encoding='utf-8'))['objects']
 plate=Image.new('RGBA',source.size,(0,0,0,0)); clean=source.copy(); oldfg=Image.new('RGBA',source.size,(0,0,0,0)); details={}
 for side,roi in ROIS.items():
  x0,y0,x1,y1=roi; size=(x1-x0,y1-y0); mask=object_mask(size,pol[side])
  front=clean.crop(roi); front.putalpha(ImageChops.multiply(front.getchannel('A'),ImageChops.invert(mask))); clean.paste(front,(x0,y0))
  cx0,cy0,cx1,cy1=CROPS[side]; csize=(cx1-cx0,cy1-cy0)
  proposal=register_proposal(PROPOSALS[side],csize)
  existing=source.getchannel('A').crop(CROPS[side])
  # Crucial v3 fix: fill all cuff/hand pixels, including transparent holes, and
  # keep the back plate within the target sprite's existing silhouette union.
  local_obj=Image.new('L',csize,0); local_obj.paste(mask,(x0-cx0,y0-cy0))
  alpha=ImageChops.lighter(existing,local_obj)
  proposal.putalpha(alpha); plate.alpha_composite(proposal,(cx0,cy0))
  fg=source.crop(roi); fg.putalpha(ImageChops.multiply(fg.getchannel('A'),mask)); oldfg.alpha_composite(fg,(x0,y0))
  details[side]={'roi_xyxy':list(roi),'registered_crop_xyxy':list(CROPS[side]),'input_proposal':str(PROPOSALS[side].relative_to(ROOT)),'input_proposal_sha256':sha(PROPOSALS[side]),'object_mask_pixels':sum(v>0 for v in mask.tobytes()),'source_alpha_pixels':sum(v>0 for v in existing.tobytes()),'union_plate_alpha_pixels':sum(v>0 for v in alpha.tobytes()),'filled_alpha_holes_inside_mask':sum(1 for a,m in zip(existing.tobytes(),local_obj.tobytes()) if a==0 and m>0),'mask_sha256':hashlib.sha256(mask.tobytes()).hexdigest()}
 hair=plate.copy(); hair.alpha_composite(clean)
 mock=hair.copy(); mock.alpha_composite(oldfg)
 plate.save(PLATE,optimize=True); clean.save(CLEAN,optimize=True); hair.save(COMPOSITE,optimize=True); make_board(source,plate,clean,hair,mock)
 outputs=[PLATE,CLEAN,COMPOSITE,BOARD]
 metrics={'task':'T67.71','status':'AI-assisted local new-design redraw WIP; not hidden truth; not accepted; not production','authorization':'User explicitly authorized a new design proposal on 2026-11-05 with the constraint not to depart substantially from the current design.','source':{'path':str(SOURCE.relative_to(ROOT)),'size':list(source.size),'sha256':sha(SOURCE)},'mask_source':{'path':str(POLYGONS.relative_to(ROOT)),'sha256':sha(POLYGONS)},'method':'Two local design proposals are registered to the corresponding 440x640 target crops. Back-plate alpha is union(existing target alpha, traced cuff/hand silhouette), repairing alpha holes inside the contaminated objects. The cuff/hand is removed from clean-front, with the new plate underneath. Static mock reuses old pixels solely to show registration.','regions':details,'outputs':{p.name:{'size':list(Image.open(p).size),'sha256':sha(p)} for p in outputs},'limitations':['The generated pixels are new design, not original hidden hair truth.','The back-plate silhouette is bounded by the union of old sprite alpha and traced cuff/hand; action reveal extent is not yet tested.','Mock foreground is not the actual dynamic arm/cuff layer.','No local acceptance, C action/transition/ParamHairSway validation, or production change is claimed.']}
 METRICS.write_text(json.dumps(metrics,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 print(json.dumps({'regions':details,'outputs':metrics['outputs']},ensure_ascii=False,indent=2))
if __name__=='__main__': main()
