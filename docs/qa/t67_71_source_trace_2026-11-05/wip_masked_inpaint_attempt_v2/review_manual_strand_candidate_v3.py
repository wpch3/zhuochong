#!/usr/bin/env python3
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
BASE=Path(__file__).resolve().parent
ROOT=Path(__file__).resolve().parents[4]
orig=Image.open(ROOT/'characters/xiaoxun/forms/teen/sprites/hair_hood_long@2x.png').convert('RGBA')
cand=Image.open(BASE/'40_manual_strand_trace_candidate_v3_wip.png').convert('RGBA')
boxes={'left':(51,849,396,1368),'right':(736,849,1081,1368)}
matte=(38,40,44,255); scale=2; tile=(345*scale,519*scale); gap=14; header=38
board=Image.new('RGB',(gap+3*(tile[0]+gap),gap+2*(tile[1]+header+gap)),(18,18,20))
d=ImageDraw.Draw(board); font=ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf',20)
for ri,(side,box) in enumerate(boxes.items()):
 base=orig.crop(box); new=cand.crop(box)
 b=Image.new('RGBA',base.size,matte); b.alpha_composite(base); b=b.convert('RGB')
 n=Image.new('RGBA',new.size,matte); n.alpha_composite(new); n=n.convert('RGB')
 ov=Image.blend(b,n,.5)
 for ci,(label,im) in enumerate((('original',b),('manual trace v3 WIP',n),('50% overlay',ov))):
  x=gap+ci*(tile[0]+gap); y=gap+ri*(tile[1]+header+gap)
  d.text((x+3,y+2),f'{side} / {label}',font=font,fill=(255,236,100))
  board.paste(im.resize(tile,Image.Resampling.LANCZOS),(x,y+header))
board.save(BASE/'42_manual_strand_trace_v3_review_board.png',optimize=True)
print(BASE/'42_manual_strand_trace_v3_review_board.png')
