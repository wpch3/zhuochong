#!/usr/bin/env python3
"""显示扩大后的可见袖手异物 ROI；该 mask 不是头发分割。"""
from pathlib import Path
import json
from PIL import Image, ImageDraw, ImageFont
BASE=Path(__file__).resolve().parent
ROOT=Path(__file__).resolve().parents[4]
polys=json.loads((BASE/'manual_artifact_polygons_v2.json').read_text(encoding='utf-8'))['polygons']
boxes={'left':(51,849,396,1368),'right':(736,849,1081,1368)}
matte=(38,40,44,255); scale=2; gap=10; header=34
w,h=345*scale,519*scale
board=Image.new('RGB',(gap+2*(w+gap),gap+h+header+gap),(18,18,20))
d=ImageDraw.Draw(board); font=ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf',18)
source=Image.open(ROOT/'characters/xiaoxun/forms/teen/sprites/hair_hood_long@2x.png').convert('RGBA')
for ci,(side,box) in enumerate(boxes.items()):
 crop=source.crop(box); bg=Image.new('RGBA',crop.size,matte); bg.alpha_composite(crop); im=bg.convert('RGBA')
 mask=Image.new('L',crop.size,0); md=ImageDraw.Draw(mask)
 for poly in polys[side]: md.polygon(poly,fill=150)
 tint=Image.new('RGBA',crop.size,(255,150,0,0)); tint.putalpha(mask)
 im=Image.alpha_composite(im,tint)
 edge=Image.new('RGBA',crop.size,(0,0,0,0)); ed=ImageDraw.Draw(edge)
 for poly in polys[side]: ed.line(poly+[poly[0]],fill=(255,226,70,255),width=2,joint='curve')
 im=Image.alpha_composite(im,edge).convert('RGB').resize((w,h),Image.Resampling.LANCZOS)
 x=gap+ci*(w+gap); y=gap
 d.text((x+4,y+2),f'{side} / expanded artifact ROI only',font=font,fill=(255,236,100))
 board.paste(im,(x,y+header))
board.save(BASE/'39_manual_artifact_mask_v2_review.png',optimize=True)
print(BASE/'39_manual_artifact_mask_v2_review.png')
