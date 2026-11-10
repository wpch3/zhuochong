#!/usr/bin/env python3
"""WIP visual review of retraced cuff/hand silhouettes; produces diagnostic only."""
from pathlib import Path
import json
import numpy as np
from PIL import Image, ImageDraw
BASE=Path(__file__).resolve().parent; ROOT=Path(__file__).resolve().parents[4]
SRC=ROOT/'characters/xiaoxun/forms/teen/sprites/hair_hood_long@2x.png'
POLY=BASE/'manual_artifact_silhouette_polygons_v3.json'
MASK_OUT=BASE/'77_visible_artifact_silhouette_v3_mask.png'
BOARD_OUT=BASE/'78_visible_artifact_silhouette_v3_review.png'
REPORT_OUT=BASE/'79_visible_artifact_silhouette_v3_metrics.json'
BOXES={'left':(51,849,396,1368),'right':(736,849,1081,1368)}; SCALE=4
source=Image.open(SRC).convert('RGBA'); src=np.asarray(source).copy()
obj=json.loads(POLY.read_text(encoding='utf-8'))['objects']; fullmask=np.zeros(src.shape[:2],dtype=np.uint8); sides={}
for side,(x0,y0,x1,y1) in BOXES.items():
 hi=Image.new('L',((x1-x0)*SCALE,(y1-y0)*SCALE),0); d=ImageDraw.Draw(hi)
 for key in ('cuff','hand'):
  points=obj[side][key];d.polygon([(int(x*SCALE),int(y*SCALE)) for x,y in points],fill=255)
 local=hi.resize((x1-x0,y1-y0),Image.Resampling.LANCZOS); lm=np.asarray(local,dtype=np.uint8);fullmask[y0:y1,x0:x1]=np.maximum(fullmask[y0:y1,x0:x1],lm)
 sides[side]={'mask_gt127_px':int((lm>127).sum()),'mask_gt0_px':int((lm>0).sum()),'opaque_source_px_under_mask':int(((src[y0:y1,x0:x1,3]>0)&(lm>127)).sum())}
out=src.copy();out[:,:,3]=(src[:,:,3].astype(np.uint16)*(255-fullmask.astype(np.uint16))//255).astype(np.uint8)
mask=Image.fromarray(fullmask,'L');mask.save(MASK_OUT);clear=Image.fromarray(out,'RGBA')
allowed=np.zeros(src.shape[:2],bool)
for x0,y0,x1,y1 in BOXES.values():allowed[y0:y1,x0:x1]=True
changed=np.any(np.asarray(clear)!=src,axis=2)
if np.any(changed&~allowed):raise SystemExit('modified outside reviewed ROIs')
thumb_w,thumb_h=690,1038;board=Image.new('RGB',(thumb_w*3+48,(thumb_h+58)*2),(244,242,247));d=ImageDraw.Draw(board)
for row,(side,box) in enumerate(BOXES.items()):
 x0,y0,x1,y1=box; original=source.crop(box); matte=Image.new('RGBA',original.size,(239,239,244,255));matte.alpha_composite(original)
 lm=Image.fromarray(fullmask[y0:y1,x0:x1],'L');tint=Image.new('RGBA',original.size,(255,35,25,0));tint.putalpha(lm.point(lambda p:p*110//255));over=Image.alpha_composite(matte,tint).convert('RGB')
 cleared=clear.crop(box);bg=Image.new('RGBA',cleared.size,(239,239,244,255));bg.alpha_composite(cleared)
 for col,(im,label) in enumerate(zip((matte.convert('RGB'),over,bg.convert('RGB')),('source on matte','red = retraced full object silhouette','clear-only diagnostic; no backfill'))):
  x=12+col*(thumb_w+12);y=42+row*(thumb_h+58);board.paste(im.resize((thumb_w,thumb_h),Image.Resampling.LANCZOS),(x,y));d.text((x+3,y-24),f'{side}: {label}',fill=(30,25,40))
board.save(BOARD_OUT)
report={'task':'T67.71','status':'WIP candidate only, not accepted and not production','source':str(SRC.relative_to(ROOT)),'mask_basis':'manual_artifact_silhouette_polygons_v3, tracing the full visible cuff and hand contours rather than the broad edit ROI','hidden_region':'original hair shape under cuff/hand remains unknown; no fill or neighbor copy','review_warning':'Check all cuff bands, palm, every fingertip, outline antialiasing, and negative spaces. Any hair overlap or contour mismatch rejects mask.','outside_reviewed_roi_modifications':int((changed&~allowed).sum()),'sides':sides,'outputs':[str(MASK_OUT.relative_to(ROOT)),str(BOARD_OUT.relative_to(ROOT))]}
REPORT_OUT.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');print(json.dumps(report,ensure_ascii=False,indent=2))
