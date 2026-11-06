#!/usr/bin/env python3
"""Experimental local background inpaint for an explicitly authorized redraw.

This only generates isolated WIP candidates. It never writes a production sprite
or claims the unknown occluded hair design is recovered.
"""
from __future__ import annotations
import hashlib, json
from pathlib import Path
import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter

ROOT=Path(__file__).resolve().parents[4]
BASE=Path(__file__).resolve().parent
SOURCE=ROOT/'characters/xiaoxun/forms/teen/sprites/hair_hood_long@2x.png'
POLYGONS=BASE/'manual_artifact_silhouette_polygons_v3.json'
ROIS={'left':(51,849,396,1368),'right':(736,849,1081,1368)}
DILATE=3
METHODS={
 'telea':(cv2.INPAINT_TELEA,12,BASE/'135_backhair_telea_v2_wip.png'),
 'ns':(cv2.INPAINT_NS,12,BASE/'136_backhair_ns_v2_wip.png'),
}
BOARD=BASE/'137_cv2_redraw_inpaint_comparison_v2.png'
METRICS=BASE/'138_cv2_redraw_inpaint_v2_metrics.json'

def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()

def mask_for(size, objects):
 m=Image.new('L',size,0); d=ImageDraw.Draw(m)
 for kind in ('cuff','hand'): d.polygon([tuple(map(int,p)) for p in objects[kind]],fill=255)
 if DILATE: m=m.filter(ImageFilter.MaxFilter(DILATE*2+1))
 return m

def main():
 source=Image.open(SOURCE).convert('RGBA')
 polygons=json.loads(POLYGONS.read_text())['objects']
 outputs={k:source.copy() for k in METHODS}
 reg={}
 for side,box in ROIS.items():
  x0,y0,x1,y1=box; size=(x1-x0,y1-y0); crop=source.crop(box)
  mask=mask_for(size,polygons[side]); m=np.array(mask,dtype=np.uint8)
  rgba=np.array(crop,dtype=np.uint8)
  rgb=rgba[:,:,:3].copy()
  # Transparent boundary pixels are replaced with nearby median hair tone before
  # inpainting so the matte background cannot leak into the repaired interior.
  alpha=rgba[:,:,3]
  visible=alpha>10
  if not visible.all():
   med=np.median(rgb[visible],axis=0).astype(np.uint8) if visible.any() else np.array([180,180,200],dtype=np.uint8)
   rgb[~visible]=med
  side_metrics={'roi_xyxy':list(box),'mask_pixels':int(np.count_nonzero(m)),'mask_sha256':hashlib.sha256(m.tobytes()).hexdigest()}
  for key,(method,radius,path) in METHODS.items():
   repaired=cv2.inpaint(rgb,m,radius,method)
   out_rgba=np.dstack([repaired,alpha])
   local=Image.fromarray(out_rgba.astype(np.uint8),'RGBA')
   outputs[key].paste(local,(x0,y0))
   side_metrics[key]={'radius':radius,'repaired_rgb_sha256':hashlib.sha256(repaired.tobytes()).hexdigest()}
  reg[side]=side_metrics
 for key,(_,_,path) in METHODS.items(): outputs[key].save(path,optimize=True)
 # Comparison board: left/right, source and each inpainting variant.
 W,H=2600,1100; board=Image.new('RGB',(W,H),(26,29,36)); d=ImageDraw.Draw(board)
 try:
  title=ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf',28)
  label=ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',18)
 except OSError: title=label=ImageFont.load_default()
 d.text((36,22),'T67.71 · OPENCV HAIR-SURFACE INPAINT TEST · WIP',font=title,fill=(242,244,248))
 d.text((38,60),'Authorized new-design experiment only; visual comparison, not accepted art and not hidden-source recovery.',font=label,fill=(190,198,210))
 cols=[('SOURCE',source),('TELEA r=12',outputs['telea']),('NAVIER-STOKES r=12',outputs['ns'])]
 margin,gap,top,panel_h=36,16,104,470; cw=(W-2*margin-2*gap)//3
 for row,side in enumerate(('left','right')):
  y=top+row*(panel_h+30); d.text((margin,y),side.upper(),font=title,fill=(118,202,233)); py=y+38
  for i,(name,img) in enumerate(cols):
   x=margin+i*(cw+gap); d.rounded_rectangle((x,py,x+cw,py+panel_h),radius=10,fill=(39,43,53),outline=(73,81,95),width=2)
   d.text((x+12,py+8),name,font=label,fill=(232,235,242))
   crop=img.crop(ROIS[side]).convert('RGBA'); bg=Image.new('RGBA',crop.size,(35,37,44,255)); bg.alpha_composite(crop)
   maxw,maxh=cw-24,panel_h-46; s=min(maxw/crop.width,maxh/crop.height); thumb=bg.resize((round(crop.width*s),round(crop.height*s)),Image.Resampling.LANCZOS).convert('RGB')
   board.paste(thumb,(x+(cw-thumb.width)//2,py+34+(maxh-thumb.height)//2))
 board.save(BOARD,optimize=True)
 metrics={'task':'T67.71','status':'experimental authorized redraw; not accepted; not production','authorization':'User authorized a new design proposal on 2026-11-05, constrained to stay close to the current design.','source':{'path':str(SOURCE.relative_to(ROOT)),'size':list(source.size),'sha256':sha(SOURCE)},'method':'OpenCV Telea and Navier-Stokes inpainting of manually traced cuff/hand mask on local RGB hair crop. This tests texture continuity only; further tapered strand art may be needed.','regions':reg,'outputs':{p.name:{'size':list(Image.open(p).size),'sha256':sha(p)} for p in [* [v[2] for v in METHODS.values()],BOARD]},'limitations':['Algorithmic inpainting is a material continuation proposal, not hidden original hair truth.','No actual moving arm/cuff layers, C actions, transitions, or ParamHairSway were tested.','No production sprite, rig, or engine was modified.']}
 METRICS.write_text(json.dumps(metrics,ensure_ascii=False,indent=2)+'\n')
 print(json.dumps({'regions':reg,'outputs':metrics['outputs']},ensure_ascii=False,indent=2))
if __name__=='__main__': main()
