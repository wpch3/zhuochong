#!/usr/bin/env python3
"""T67.71 local back-hair redraw v6 from cleaned, smooth hair-form guides.

Unlike v3, these inputs mask the cuff/hand artifact before generation, so the
redrawn layer does not inherit black/teal/skin marks. This is a design proposal,
not source truth; only the mapped target ROI is written into an isolated plate.
"""
from __future__ import annotations
import hashlib,json
from pathlib import Path
from PIL import Image,ImageDraw,ImageChops,ImageFilter,ImageFont
ROOT=Path(__file__).resolve().parents[4]; BASE=Path(__file__).resolve().parent
SOURCE=ROOT/'characters/xiaoxun/forms/teen/sprites/hair_hood_long@2x.png'
POLYGONS=BASE/'manual_artifact_silhouette_polygons_v3.json'
ROIS={'left':(51,849,396,1368),'right':(736,849,1081,1368)}
CROPS={'left':(0,780,440,1420),'right':(692,780,1132,1420)}
PROPOSALS={'left':BASE/'122_left_backhair_local_redraw_proposal.png','right':BASE/'123_right_backhair_local_redraw_proposal.png'}
PLATE=BASE/'158_backhair_local_redraw_v6_plate_wip.png'; CLEAN=BASE/'159_clean_front_redraw_v6_wip.png'; COMP=BASE/'160_clean_hair_composite_redraw_v6_wip.png'; BOARD=BASE/'161_backhair_local_redraw_v6_review.png'; METRICS=BASE/'162_backhair_local_redraw_v6_metrics.json'
DILATE=18  # include traced cuff/hand plus black negative-space fringe

def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def mk_objmask(size,obj):
 m=Image.new('L',size,0); d=ImageDraw.Draw(m)
 for key in ('cuff','hand'): d.polygon([tuple(map(int,p)) for p in obj[key]],fill=255)
 return m.filter(ImageFilter.MaxFilter(DILATE*2+1)).filter(ImageFilter.GaussianBlur(.45))
def register(path,size):
 im=Image.open(path).convert('RGB'); w,h=size; want=round(im.width*h/w)
 if im.height>want:
  top=(im.height-want)//2; im=im.crop((0,top,im.width,top+want))
 return im.resize(size,Image.Resampling.LANCZOS).convert('RGBA')
def bg(crop):
 out=Image.new('RGBA',crop.size,(39,42,50,255)); cell=18; d=ImageDraw.Draw(out)
 for y in range(0,crop.height,cell):
  for x in range(0,crop.width,cell):
   if (x//cell+y//cell)%2:d.rectangle((x,y,x+cell-1,y+cell-1),fill=(58,61,69,255))
 out.alpha_composite(crop); return out
def make_board(src,plate,clean,comp,mock):
 W,H=3000,1760; b=Image.new('RGB',(W,H),(26,29,36));d=ImageDraw.Draw(b)
 try:t=ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf',30);s=ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',17)
 except OSError:t=s=ImageFont.load_default()
 d.text((34,20),'T67.71 · LOCAL-STRAND BACK-HAIR REDRAW V6 · NEW DESIGN PROPOSAL',font=t,fill=(244,246,250));d.text((36,58),'The input guide hid cuff/hand marks before redraw. Review the 100% target ROIs; no hidden-original or C-validation claim.',font=s,fill=(192,200,212))
 # Full-canvas thumbnails.
 for i,(name,img) in enumerate((('FULL SOURCE',src),('FULL PROPOSAL',comp))):
  x=34+i*678;y=100;d.rounded_rectangle((x,y,x+660,y+420),radius=10,fill=(39,43,53),outline=(73,81,95),width=2);d.text((x+12,y+8),name,font=s,fill=(232,235,242));thumb=bg(img);thumb.thumbnail((300,370),Image.Resampling.LANCZOS);b.paste(thumb.convert('RGB'),(x+180,y+38))
  sx=thumb.width/img.width;sy=thumb.height/img.height
  for box in ROIS.values():
   x0,y0,x1,y1=box;d.rectangle((x+180+round(x0*sx),y+38+round(y0*sy),x+180+round(x1*sx),y+38+round(y1*sy)),outline=(255,166,80),width=2)
 cols=[('SOURCE ROI',src),('BACK PLATE ONLY',plate),('CLEAN HAIR ONLY',comp),('STATIC MOCK / SOURCE FOREGROUND',mock)]
 margin,gap=34,14;cw=(W-2*margin-3*gap)//4; row_h=520;top=540
 for row,side in enumerate(('left','right')):
  y=top+row*(row_h+34);d.text((margin,y),side.upper(),font=t,fill=(118,202,233));py=y+38
  for j,(name,img) in enumerate(cols):
   x=margin+j*(cw+gap);d.rounded_rectangle((x,py,x+cw,py+row_h),radius=10,fill=(39,43,53),outline=(73,81,95),width=2);d.text((x+12,py+8),name,font=s,fill=(232,235,242));crop=bg(img.crop(CROPS[side]).convert('RGBA'));mw,mh=cw-22,row_h-44;k=min(mw/crop.width,mh/crop.height);crop=crop.resize((round(crop.width*k),round(crop.height*k)),Image.Resampling.LANCZOS);b.paste(crop.convert('RGB'),(x+(cw-crop.width)//2,py+35+(mh-crop.height)//2))
 d.rounded_rectangle((34,H-52,W-34,H-16),radius=8,fill=(63,43,34),outline=(235,162,75),width=2);d.text((46,H-48),'Static mock reuses legacy cuff/hand pixels only for registration. Real C must use actual moving arms/cuffs after local approval.',font=s,fill=(255,223,175));b.save(BOARD,optimize=True)
def main():
 src=Image.open(SOURCE).convert('RGBA'); objs=json.loads(POLYGONS.read_text())['objects']; plate=Image.new('RGBA',src.size,(0,0,0,0)); clean=src.copy(); oldfg=Image.new('RGBA',src.size,(0,0,0,0)); info={}
 for side,roi in ROIS.items():
  x0,y0,x1,y1=roi;mask=mk_objmask((x1-x0,y1-y0),objs[side]); front=clean.crop(roi);front.putalpha(ImageChops.multiply(front.getchannel('A'),ImageChops.invert(mask)));clean.paste(front,(x0,y0))
  cb=CROPS[side];cw,ch=cb[2]-cb[0],cb[3]-cb[1];proposal=register(PROPOSALS[side],(cw,ch));existing=src.getchannel('A').crop(cb);local=Image.new('L',(cw,ch),0);local.paste(mask,(x0-cb[0],y0-cb[1]));a=ImageChops.lighter(existing,local);proposal.putalpha(a);plate.alpha_composite(proposal,(cb[0],cb[1]))
  fg=src.crop(roi);fg.putalpha(ImageChops.multiply(fg.getchannel('A'),mask));oldfg.alpha_composite(fg,(x0,y0))
  info[side]={'roi_xyxy':list(roi),'registered_crop_xyxy':list(cb),'proposal':str(PROPOSALS[side].relative_to(ROOT)),'proposal_sha256':sha(PROPOSALS[side]),'generated_size':list(Image.open(PROPOSALS[side]).size),'clean_object_pixels':sum(v>0 for v in mask.tobytes()),'filled_alpha_holes':sum(1 for av,mv in zip(existing.tobytes(),local.tobytes()) if av==0 and mv>0)}
 comp=plate.copy();comp.alpha_composite(clean);mock=comp.copy();mock.alpha_composite(oldfg);plate.save(PLATE,optimize=True);clean.save(CLEAN,optimize=True);comp.save(COMP,optimize=True);make_board(src,plate,clean,comp,mock)
 outputs=[PLATE,CLEAN,COMP,BOARD];m={'task':'T67.71','status':'new-design redraw WIP; not accepted; not hidden-original truth; not production','authorization':'User explicitly authorized a new design proposal on 2026-11-05, constrained not to depart substantially from the current design.','source':{'path':str(SOURCE.relative_to(ROOT)),'size':list(src.size),'sha256':sha(SOURCE)},'mask_source':{'path':str(POLYGONS.relative_to(ROOT)),'sha256':sha(POLYGONS)},'method':'Use cleaned guide redraws (cuff/hand marks hidden before generation) as design material, register to target crop; alpha is union of existing target silhouette and traced object mask; place new back-hair under a separate cleaned hair foreground.','regions':info,'outputs':{p.name:{'size':list(Image.open(p).size),'sha256':sha(p)} for p in outputs},'limitations':['The generated art is a proposal and does not recover unknown hidden topology.','Static mock uses the old source cuff/hand as a temporary registration check, not actual C layers.','Local visual review is not yet passed; no C action/transition/ParamHairSway validation.','No production sprite, rig, or engine change.']}
 METRICS.write_text(json.dumps(m,ensure_ascii=False,indent=2)+'\n');print(json.dumps({'regions':info,'outputs':m['outputs']},ensure_ascii=False,indent=2))
if __name__=='__main__':main()
