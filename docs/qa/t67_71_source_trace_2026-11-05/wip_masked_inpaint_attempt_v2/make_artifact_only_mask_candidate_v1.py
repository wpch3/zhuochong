#!/usr/bin/env python3
"""WIP mask exploration only. Broad manual ROI constrains color classes; output is not yet an approved cleanup mask."""
from pathlib import Path
import json
import numpy as np
from PIL import Image, ImageDraw
BASE=Path(__file__).resolve().parent; ROOT=Path(__file__).resolve().parents[4]
SRC=ROOT/'characters/xiaoxun/forms/teen/sprites/hair_hood_long@2x.png'
POLY=BASE/'manual_artifact_polygons_v2.json'
MASKS=BASE/'68_artifact_color_mask_candidate_v1.png'; BOARD=BASE/'69_artifact_color_mask_candidate_v1_review.png'; CLEAN=BASE/'70_artifact_color_mask_clear_only_test.png'; REPORT=BASE/'71_artifact_color_mask_candidate_v1_metrics.json'
BOXES={'left':(51,849,396,1368),'right':(736,849,1081,1368)}; S=3

def dilate(m,n=1):
 for _ in range(n):
  m=m.copy();m[1:] |= m[:-1];m[:-1] |= m[1:];m[:,1:] |= m[:,:-1];m[:,:-1] |= m[:,1:]
 return m

def roi_mask(size,polys):
 m=Image.new('L',size,0);d=ImageDraw.Draw(m)
 for p in polys:d.polygon(p,fill=255)
 return np.asarray(m)>0

source=Image.open(SRC).convert('RGBA'); a=np.array(source); rgb=a[:,:,:3].astype(np.int16);R,G,B=rgb.transpose(2,0,1);A=a[:,:,3]
polydata=json.loads(POLY.read_text(encoding='utf-8'))['polygons'];combined=np.zeros(A.shape,bool);side_data={};overlay=source.copy();clean=source.copy()
for side,box in BOXES.items():
 x0,y0,x1,y1=box;crop=a[y0:y1,x0:x1];cr=crop[:,:,:3].astype(np.int16);r,g,b=cr.transpose(2,0,1);alpha=crop[:,:,3]
 cuff=roi_mask((345,519),[polydata[side][0]]);hand=roi_mask((345,519),[polydata[side][1]])
 opaque=alpha>12
 # Warm transparent/residual skin seed: hair palette is cold lilac/blue, foreign palm is weakly warm.
 skin=(r-g>=2)&(r-b>=2)&(r>165)&(g>115)&opaque&hand
 # Cuff cyan seed: lower-saturation remnants require a softer threshold than the old purge tool.
 teal=(g-r>=6)&(b-g<=28)&(b-g>=-16)&(g<250)&opaque&cuff
 # The source contains nearly white cuff stripes and washed-out palm interiors.
 # Include near-neutral regions only when tethered to the colored object cores, and keep
 # each class inside its own reviewed cuff/hand ROI.
 spread=np.maximum(np.maximum(r,g),b)-np.minimum(np.minimum(r,g),b)
 neutral_cuff=(np.minimum(np.minimum(r,g),b)>=225)&(spread<=46)&opaque&cuff
 cuff_mask=teal | (neutral_cuff & dilate(teal,12))
 neutral_hand=(np.minimum(np.minimum(r,g),b)>=220)&(spread<=44)&opaque&hand
 hand_mask=skin | (neutral_hand & dilate(skin,18))
 seed=hand_mask|cuff_mask
 # A narrow outline ring around the detected foreign-colored core retains its dark contour,
 # but only inside the broad cuff/hand ROI; review the resulting edge manually.
 allowed=cuff|hand
 dark=(np.maximum(np.maximum(r,g),b)<165)&(alpha>12)&allowed&dilate(seed,2)
 mask=(seed|dark)&allowed
 mask=dilate(mask,1)&allowed
 combined[y0:y1,x0:x1] |= mask
 # Visual overlay is only for location review; it does not alter the candidate mask.
 crop_rgba=Image.fromarray(crop,'RGBA'); local=Image.new('RGBA',(345,519),(0,0,0,0));local.putalpha(Image.fromarray((mask*128).astype('uint8')))
 tint=Image.new('RGBA',(345,519),(255,40,30,0));tint.putalpha(Image.fromarray((mask*120).astype('uint8')))
 cropvis=Image.alpha_composite(crop_rgba,tint)
 overlay.paste(cropvis,(x0,y0))
 cr_clean=crop.copy();cr_clean[:,:,3][mask]=0;clean.paste(Image.fromarray(cr_clean,'RGBA'),(x0,y0))
 side_data[side]={'artifact_mask_pixels':int(mask.sum()),'skin_seed_px':int(skin.sum()),'teal_seed_px':int(teal.sum()),'neutral_cuff_px':int((neutral_cuff&dilate(teal,12)).sum()),'neutral_hand_px':int((neutral_hand&dilate(skin,18)).sum()),'dark_outline_px':int(dark.sum()),'mask_nonzero_alpha_source_px':int(((alpha>0)&mask).sum())}
# Keep an explicit full-canvas black/white mask for repro only; never use ROI itself as the inferred hair alpha.
mask_img=Image.fromarray((combined*255).astype('uint8'),'L');mask_img.save(MASKS)
# Preserve all bytes outside candidate mask exactly.
cleana=np.array(clean);outside=(~combined)
if not np.array_equal(cleana[outside],a[outside]):raise SystemExit('clear-only candidate modified outside the color mask')
clean.save(CLEAN)
# Review each side over an opaque neutral matte so alpha is visible, never mistaken for black.
W,H=690,1038;board=Image.new('RGB',(W*2+36,(H+54)*2),(244,242,247));d=ImageDraw.Draw(board)
for row,(side,box) in enumerate(BOXES.items()):
 x0,y0,x1,y1=box;src_crop=source.crop(box); bg=Image.new('RGBA',src_crop.size,(239,239,244,255));bg.alpha_composite(src_crop)
 local=combined[y0:y1,x0:x1]; tint=Image.new('RGBA',src_crop.size,(255,35,25,0));tint.putalpha(Image.fromarray((local*125).astype('uint8')));marked=Image.alpha_composite(bg,tint)
 cl=clean.crop(box).convert('RGBA');bg2=Image.new('RGBA',cl.size,(239,239,244,255));bg2.alpha_composite(cl)
 for col,im in enumerate((marked.convert('RGB'),bg2.convert('RGB'))):
  im=im.resize((W,H),Image.Resampling.LANCZOS);x=12+col*(W+12);y=42+row*(H+54);board.paste(im,(x,y));d.text((x+4,y-26),f'{side}: '+('red = color-segment candidate mask' if col==0 else 'diagnostic clear only; no backfill'),fill=(30,25,40))
board.save(BOARD)
report={'task':'T67.71','status':'WIP mask exploration; not production, not hair truth','source':str(SRC.relative_to(ROOT)),'broad_roi':'manual_artifact_polygons_v2 covers whole cuff band and hand; includes adjacent legal hair',
 'seed_rules':{'skin':'R-G>=2, R-B>=2, R>165, G>115, alpha>12 within broad hand ROI','cuff_teal':'G-R>=6, -16<=B-G<=28, G<250, alpha>12 within cuff ROI','cuff_neutral':'near-white cuff candidates only within 12px of cyan seeds','hand_neutral':'near-neutral palm pixels only within 18px of warm skin seeds','outline':'dark pixels within 2px of color seeds and broad ROI; mask expanded 1px for anti-alias edge'},
 'warning':'Heuristics locate candidate foreign pixels; warm hair highlights or neutral hair may be false positives. Inspect red overlay at native/zoom before using. Clear-only output is a hole diagnostic, not an acceptable repair.',
 'side_counts':side_data,'total_mask_pixels':int(combined.sum()),'outside_mask_byte_identity':'asserted exact for clear-only diagnostic','outputs':[str(MASKS.relative_to(ROOT)),str(BOARD.relative_to(ROOT)),str(CLEAN.relative_to(ROOT))]}
REPORT.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'status':report['status'],'total_mask_pixels':report['total_mask_pixels'],'sides':side_data,'warning':report['warning']},ensure_ascii=False,indent=2))
