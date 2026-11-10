#!/usr/bin/env python3
"""Isolated T67.71 proposal: warp texture from the same target hair panel.

The source is the existing hood-up long-hair sprite itself, sampling only a
visible, non-cuff lower hair curtain. It is remapped into a separately drawn
smooth back-hair silhouette. This is new-design texture synthesis, not original
hidden-pixel recovery. The cuff/hand removal mask is independent.
"""
from __future__ import annotations
import hashlib,json,math
from pathlib import Path
import cv2
import numpy as np
from PIL import Image,ImageDraw,ImageFilter,ImageChops
ROOT=Path(__file__).resolve().parents[4]
OUT=Path(__file__).resolve().parent
SRC=ROOT/'characters/xiaoxun/forms/teen/sprites/hair_hood_long@2x.png'
MASKJSON=ROOT/'docs/qa/t67_71_source_trace_2026-11-05/wip_masked_inpaint_attempt_v2/manual_artifact_polygons_v2.json'
ROIS={'left':(51,849,396,1368),'right':(736,849,1081,1368)}
DONORS={'left':(252,1290,332,1470),'right':(805,1275,885,1455)}
S=4

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def bez(p0,p1,p2,p3,t):
 u=1-t;return (u**3*p0[0]+3*u*u*t*p1[0]+3*u*t*t*p2[0]+t**3*p3[0],u**3*p0[1]+3*u*u*t*p1[1]+3*u*t*t*p2[1]+t**3*p3[1])
def curve(seg,n=80):return [bez(*seg,i/n) for i in range(n+1)]
# Hand-designed silhouette edges. These boundaries are a new proposal and are
# not derived from the cuff/hand silhouette.
SHAPES={
 'left':{
  'left':[((120,135),(121,184),(132,231),(151,280)),((151,280),(173,331),(181,388),(190,441)),((190,441),(202,490),(213,538),(216,577))],
  'right':[((170,135),(209,186),(239,232),(250,280)),((250,280),(260,331),(266,388),(257,441)),((257,441),(248,490),(232,538),(216,577))]},
 'right':{
  'left':[((179,135),(130,186),(100,232),(90,280)),((90,280),(80,331),(74,388),(83,441)),((83,441),(92,490),(108,538),(129,577))],
  'right':[((229,135),(228,184),(217,231),(198,280)),((198,280),(176,331),(168,388),(159,441)),((159,441),(147,490),(132,538),(129,577))]}
}

def make_shape_mask(size,side,roi):
 x0,y0,_,_=roi;shape=SHAPES[side]
 left=sum((curve(seg)[:-1] for seg in shape['left']),[])+curve(shape['left'][-1])
 right=sum((curve(seg)[:-1] for seg in shape['right']),[])+curve(shape['right'][-1])
 m=Image.new('L',(size[0]*S,size[1]*S),0);d=ImageDraw.Draw(m)
 poly=[((x0+x)*S,(y0+y)*S) for x,y in left+right[::-1]]
 d.polygon(poly,fill=255)
 m=m.resize(size,Image.Resampling.LANCZOS).filter(ImageFilter.GaussianBlur(.7))
 # Fade only the new sheet's top and tapered lower end. The upper overlap sits
 # beneath the existing side lock; it must not form a horizontal cut edge.
 arr=np.array(m,dtype=np.float32);x0,y0,_,_=roi
 ys=np.arange(size[1],dtype=np.float32)-y0
 fade=np.ones_like(ys)
 top0,top1=135.0,245.0
 q=np.clip((ys-top0)/(top1-top0),0,1);fade*=q*q*(3-2*q)
 bot0,bot1=545.0,580.0
 q=np.clip((bot1-ys)/(bot1-bot0),0,1);fade*=q*q*(3-2*q)
 arr*=fade[:,None]
 return Image.fromarray(np.clip(arr,0,255).astype(np.uint8),'L')

def warp_patch(src_rgba, donor_box, dest_box):
 dx0,dy0,dx1,dy1=donor_box;bx0,by0,bx1,by1=dest_box
 patch=np.array(src_rgba.crop(donor_box).convert('RGB'))[:,:,::-1].copy() # BGR
 h,w=by1-by0,bx1-bx0
 yy,xx=np.mgrid[0:h,0:w].astype(np.float32)
 u=xx/max(1,w-1);v=yy/max(1,h-1)
 # Gently bend the copied source grain to follow the proposed lock flow; this
 # is a real 2-D map, not a column smear or OpenCV inpainting.
 sx=(u*(dx1-dx0-1)+0.9*np.sin(np.pi*v)*np.sin(np.pi*u)).astype(np.float32)
 sy=(v*(dy1-dy0-1)+5*np.sin(np.pi*u)*(1-v)).astype(np.float32)
 warped=cv2.remap(patch,sx,sy,cv2.INTER_CUBIC,borderMode=cv2.BORDER_REPLICATE)
 return Image.fromarray(warped[:,:,::-1],'RGB')

def object_clear_mask(size,side,roi,polys):
 x0,y0,x1,y1=roi;w=x1-x0;h=y1-y0
 m=Image.new('L',(w*S,h*S),0);d=ImageDraw.Draw(m)
 for poly in polys[side]:d.polygon([(round(x*S),round(y*S)) for x,y in poly],fill=255)
 m=m.resize((w,h),Image.Resampling.LANCZOS).filter(ImageFilter.MaxFilter(3))
 full=Image.new('L',size,0);full.paste(m,(x0,y0));return full

def make_board(src,under,cleancomp,static):
 W,H=2048,1520;board=Image.new('RGB',(W,H),(27,30,37));d=ImageDraw.Draw(board)
 try:
  from PIL import ImageFont
  title=ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf',26)
  label=ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',17)
 except OSError:title=label=None
 d.text((28,18),'T67.71 · SAME-SPRITE WARP TEXTURE STUDY V3 · NEW DESIGN / NOT HIDDEN TRUTH',font=title,fill=(245,246,249))
 d.text((30,53),'Warped local texture from visible lower back-hair; independent hand/cuff cleanup and new silhouette. Static foreground is registration-only, not C validation.',font=label,fill=(190,198,211))
 def checker(im):
  bg=Image.new('RGBA',im.size,(40,43,51,255));dd=ImageDraw.Draw(bg);cell=22
  for y in range(0,im.height,cell):
   for x in range(0,im.width,cell):
    if (x//cell+y//cell)%2:dd.rectangle((x,y,x+cell-1,y+cell-1),fill=(58,61,69,255))
  bg.alpha_composite(im);return bg
 cols=[('SOURCE',src),('UNDERLAY',under),('CLEAN HAIR + NEW UNDERLAY',cleancomp),('STATIC REGISTRATION MOCK',static)]
 top=105;rowh=670;gap=12;margin=28;cw=(W-2*margin-3*gap)//4
 for ri,side in enumerate(('left','right')):
  y=top+ri*rowh;d.text((margin,y),side.upper(),font=title,fill=(117,202,232));y+=36
  for ci,(name,im) in enumerate(cols):
   x=margin+ci*(cw+gap);d.rounded_rectangle((x,y,x+cw,y+rowh-60),radius=9,fill=(40,43,52),outline=(74,82,96),width=2);d.text((x+10,y+8),name,font=label,fill=(233,236,241))
   crop=checker(im.crop(ROIS[side]));scale=min((cw-18)/crop.width,(rowh-110)/crop.height);crop=crop.resize((round(crop.width*scale),round(crop.height*scale)),Image.Resampling.LANCZOS);board.paste(crop.convert('RGB'),(x+(cw-crop.width)//2,y+35+(rowh-110-crop.height)//2))
 board.save(OUT/'t67_71_same_sprite_warp_v3_review.png',optimize=True)

def main():
 src=Image.open(SRC).convert('RGBA');maskdoc=json.loads(MASKJSON.read_text());polys=maskdoc['polygons']
 under=Image.new('RGBA',src.size,(0,0,0,0));clean=src.copy();details={};clear_full=Image.new('L',src.size,0)
 for side,roi in ROIS.items():
  donor=DONORS[side];x0,y0,x1,y1=roi
  # New independent sheet shape overlaps source hair at its top and runs into
  # the existing lower panel. The cuff/hand polygon is not used as this alpha.
  sm=make_shape_mask(src.size,side,roi)
  bx0=max(0,x0+105);by0=y0+125;bx1=min(src.width,x0+285);by1=y0+580
  tex=warp_patch(src,donor,(bx0,by0,bx1,by1)).convert('RGBA');tex.putalpha(sm.crop((bx0,by0,bx1,by1)))
  under.alpha_composite(tex,(bx0,by0))
  cm=object_clear_mask(src.size,side,roi,polys);clear_full=ImageChops.lighter(clear_full,cm)
  details[side]={'roi_xyxy':list(roi),'donor_xyxy':list(donor),'donor_opaque_fraction':round(sum(v>200 for v in src.getchannel('A').crop(donor).getdata())/((donor[2]-donor[0])*(donor[3]-donor[1])),5),'proposal_alpha_pixels':sum(v>0 for v in sm.tobytes()),'visible_object_clear_pixels':sum(v>0 for v in cm.tobytes())}
 clean.putalpha(ImageChops.multiply(clean.getchannel('A'),ImageChops.invert(clear_full)))
 comp=under.copy();comp.alpha_composite(clean)
 fg=Image.new('RGBA',src.size,(0,0,0,0)); fga=ImageChops.multiply(src.getchannel('A'),clear_full);fg=src.copy();fg.putalpha(fga)
 static=comp.copy();static.alpha_composite(fg)
 outputs={}
 for name,im in [('t67_71_same_sprite_warp_v3_underlay.png',under),('t67_71_same_sprite_warp_v3_clean_front.png',clean),('t67_71_same_sprite_warp_v3_composite.png',comp),('t67_71_same_sprite_warp_v3_static_mock.png',static)]:
  p=OUT/name;im.save(p,optimize=True);outputs[name]={'size':list(im.size),'sha256':sha(p)}
 make_board(src,under,comp,static)
 p=OUT/'t67_71_same_sprite_warp_v3_review.png';outputs[p.name]={'size':list(Image.open(p).size),'sha256':sha(p)}
 m={'task':'T67.71','status':'isolated new-design WIP; not accepted; not hidden-original truth; not production','method':'2-D mesh remap of a fully opaque, visible lower-panel texture from the same target hood-up hair sprite into a separately drawn, vertically feathered flowing silhouette whose root overlaps the existing side hair; not inpainting and not a foreign-hairstyle donor','source':{'path':str(SRC.relative_to(ROOT)),'sha256':sha(SRC),'size':list(src.size)},'mask_source':{'path':str(MASKJSON.relative_to(ROOT)),'sha256':sha(MASKJSON),'scope':'visible cuff/hand cleanup only, independent of proposed hair alpha'},'regions':details,'outputs':outputs,'limitations':['Warped visible source pixels are a texture/design reference only; hidden topology remains unknown. The patch uses fully opaque donor rectangles to avoid key-color/alpha holes.','Static mock reuses source cuff/hand only to show registration; actual C arms/cuffs, actions/transitions and ParamHairSway are not tested.','No production sprite, rig, generator or engine was changed.']}
 (OUT/'t67_71_same_sprite_warp_v3_metrics.json').write_text(json.dumps(m,ensure_ascii=False,indent=2)+'\n')
 print(json.dumps(m,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
