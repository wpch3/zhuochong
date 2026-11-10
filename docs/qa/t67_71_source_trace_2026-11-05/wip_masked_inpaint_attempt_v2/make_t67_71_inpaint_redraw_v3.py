#!/usr/bin/env python3
"""T67.71 inpaint redraw v3: fill alpha holes and include object fringe.

This corrects the earlier inpaint test's key limitation: object-shaped alpha
holes must be filled by a back plate, not left transparent. Cuff/hand plus dark
fringe are masked with a broad registered silhouette; inpaint is only an
explicitly authorized new-design material continuation, never source truth.
"""
from __future__ import annotations
import hashlib,json
from pathlib import Path
import cv2,numpy as np
from PIL import Image,ImageDraw,ImageChops,ImageFilter,ImageFont
ROOT=Path(__file__).resolve().parents[4];BASE=Path(__file__).resolve().parent
SOURCE=ROOT/'characters/xiaoxun/forms/teen/sprites/hair_hood_long@2x.png';POLYGONS=BASE/'manual_artifact_silhouette_polygons_v3.json'
ROIS={'left':(51,849,396,1368),'right':(736,849,1081,1368)};DILATE=18
METHODS={'telea':(cv2.INPAINT_TELEA,8,BASE/'163_backhair_inpaint_telea_v3_wip.png'),'ns':(cv2.INPAINT_NS,8,BASE/'164_backhair_inpaint_ns_v3_wip.png')}
CLEAN=BASE/'165_clean_front_inpaint_v3_wip.png';BOARD=BASE/'166_inpaint_alpha_union_review_v3.png';METRICS=BASE/'167_inpaint_alpha_union_v3_metrics.json'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def make_mask(size,obj):
 m=Image.new('L',size,0);d=ImageDraw.Draw(m)
 for k in ('cuff','hand'):d.polygon([tuple(map(int,p)) for p in obj[k]],fill=255)
 return m.filter(ImageFilter.MaxFilter(2*DILATE+1)).filter(ImageFilter.GaussianBlur(.45))
def compose_boards(source,plates,clean):
 W,H=2800,1120;b=Image.new('RGB',(W,H),(26,29,36));d=ImageDraw.Draw(b)
 try:t=ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf',28);s=ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',17)
 except OSError:t=s=ImageFont.load_default()
 d.text((32,20),'T67.71 · INPAINT REDRAW V3 · ALPHA-UNION FIX',font=t,fill=(244,246,250));d.text((34,58),'Cuff/hand and black fringe are replaced; back plate alpha now fills the erased object-shaped transparent holes.',font=s,fill=(192,200,212))
 cols=[('SOURCE',source),('TELEA PLATE',plates['telea']),('TELEA + CLEAN FRONT',None),('NAVIER-STOKES PLATE',plates['ns']),('NS + CLEAN FRONT',None)]
 for i,(name,img) in enumerate(cols):
  if name=='TELEA + CLEAN FRONT':
   img=plates['telea'].copy();img.alpha_composite(clean)
  elif name=='NS + CLEAN FRONT':
   img=plates['ns'].copy();img.alpha_composite(clean)
  x=24+i*552;y=96;d.rounded_rectangle((x,y,x+530,y+990),radius=10,fill=(39,43,53),outline=(73,81,95),width=2);d.text((x+12,y+8),name,font=s,fill=(232,235,242))
  for row,side in enumerate(('left','right')):
   box=ROIS[side];crop=img.crop(box).convert('RGBA');bg=Image.new('RGBA',crop.size,(35,37,44,255));bg.alpha_composite(crop);thumb=bg.resize((round(crop.width*1.25),round(crop.height*1.25)),Image.Resampling.LANCZOS).convert('RGB'); yy=y+42+row*465;d.text((x+12,yy),side.upper(),font=s,fill=(118,202,233));b.paste(thumb,(x+110,yy+20))
 d.rounded_rectangle((24,H-48,W-24,H-14),radius=8,fill=(63,43,34),outline=(235,162,75),width=2);d.text((36,H-44),'WIP only. No actual foreground arm/C movement validation, no hidden-original claim, no production changes.',font=s,fill=(255,223,175));b.save(BOARD,optimize=True)
def main():
 source=Image.open(SOURCE).convert('RGBA');objs=json.loads(POLYGONS.read_text())['objects'];clean=source.copy();plates={k:source.copy() for k in METHODS};info={}
 for side,box in ROIS.items():
  x0,y0,x1,y1=box;size=(x1-x0,y1-y0);crop=source.crop(box);mask=make_mask(size,objs[side]);m=np.array(mask,dtype=np.uint8);rgba=np.array(crop,dtype=np.uint8);rgb=rgba[:,:,:3].copy();alpha=rgba[:,:,3]
  # Fill invisible RGB with nearby median so the matte does not contaminate inpaint.
  visible=alpha>10;med=np.median(rgb[visible],axis=0).astype(np.uint8) if visible.any() else np.array([180,180,200],dtype=np.uint8);rgb[~visible]=med
  front=clean.crop(box);front.putalpha(ImageChops.multiply(front.getchannel('A'),ImageChops.invert(mask)));clean.paste(front,(x0,y0))
  local_alpha=ImageChops.lighter(crop.getchannel('A'),mask)
  sm={'roi_xyxy':list(box),'dilation_px':DILATE,'mask_pixels':int(np.count_nonzero(m)),'source_alpha_pixels':sum(v>0 for v in crop.getchannel('A').tobytes()),'union_alpha_pixels':sum(v>0 for v in local_alpha.tobytes()),'filled_alpha_holes_inside_mask':sum(1 for a,mm in zip(crop.getchannel('A').tobytes(),mask.tobytes()) if a==0 and mm>0),'mask_sha256':hashlib.sha256(m.tobytes()).hexdigest()}
  for key,(method,radius,path) in METHODS.items():
   repaired=cv2.inpaint(rgb,m,radius,method);out=Image.fromarray(np.dstack([repaired,np.array(local_alpha,dtype=np.uint8)]),'RGBA');plates[key].paste(out,(x0,y0));sm[key]={'radius_px':radius,'rgb_sha256':hashlib.sha256(repaired.tobytes()).hexdigest()}
  info[side]=sm
 for key,(_,_,path) in METHODS.items():plates[key].save(path,optimize=True)
 clean.save(CLEAN,optimize=True);compose_boards(source,plates,clean)
 outputs=[v[2] for v in METHODS.values()]+[CLEAN,BOARD]
 metrics={'task':'T67.71','status':'experimental inpaint redraw; not accepted; not hidden truth; not production','authorization':'User explicitly authorized a new design proposal on 2026-11-05 with the constraint to stay close to current design.','source':{'path':str(SOURCE.relative_to(ROOT)),'sha256':sha(SOURCE),'size':list(source.size)},'method':'OpenCV Telea and Navier-Stokes on RGB hair crops. A 18px dilated cuff/hand silhouette is removed from clean-front and unioned with existing alpha on back plates, including transparent holes.','regions':info,'outputs':{p.name:{'size':list(Image.open(p).size),'sha256':sha(p)} for p in outputs},'limitations':['Inpaint may look too smooth or stripe-like and is not accepted art unless local view passes.','No actual arm/cuff layers, C actions, transitions, or ParamHairSway tested.','No production sprite, rig, generator, or engine changed.']}
 METRICS.write_text(json.dumps(metrics,ensure_ascii=False,indent=2)+'\n');print(json.dumps({'regions':info,'outputs':metrics['outputs']},ensure_ascii=False,indent=2))
if __name__=='__main__':main()
