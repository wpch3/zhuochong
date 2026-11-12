#!/usr/bin/env python3
"""Create a bounded hair-source separation and flat hidden-fill WIP from v1.1.

Color/ROI masks retain source-visible pixels. Hidden face under hair is an
estimated flat fill only; it is not hand-painted or model-ready.
"""
from __future__ import annotations
import hashlib,json,zipfile
from io import BytesIO
from pathlib import Path
from xml.etree.ElementTree import Element,SubElement,tostring
import cv2,numpy as np
from PIL import Image,ImageDraw
ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'characters/xiaoxun/design/loli_live2d_v1/authoring_v1_1'
PREV=BASE/'authoring_pass_06';OUT=BASE/'authoring_pass_07';SOURCE=BASE/'reference_v1_1_alpha_edge_connected.png'
SCALE=4

def polygon(points,size):
 im=Image.new('L',(size[0]*SCALE,size[1]*SCALE),0);ImageDraw.Draw(im).polygon([(int(x*SCALE),int(y*SCALE)) for x,y in points],fill=255)
 return (np.asarray(im.resize(size,Image.Resampling.BOX))>127).astype(np.uint8)*255
def mirror(pts):return [(1280-x,y) for x,y in pts]
def png(im):
 b=BytesIO();im.save(b,format='PNG',optimize=True);return b.getvalue()
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def source_layer(src,mask):
 a=np.asarray(src).copy();a[...,3]=((a[...,3].astype(np.uint16)*mask.astype(np.uint16))//255).astype(np.uint8);return Image.fromarray(a,'RGBA')
def fill(color,mask):
 a=np.zeros((1920,1280,4),np.uint8);a[...,:3]=color;a[...,3]=mask;return Image.fromarray(a,'RGBA')
def review_board(items,path,cols=2,cw=560,ch=300):
 g,lh=14,24;rows=(len(items)+cols-1)//cols;board=Image.new('RGB',(cols*cw+(cols+1)*g,rows*ch+(rows+1)*g),(27,30,35));d=ImageDraw.Draw(board)
 tw,th=cw-2*g,ch-lh-2*g;checker=Image.new('RGBA',(tw,th));cd=ImageDraw.Draw(checker)
 for y in range(0,th,14):
  for x in range(0,tw,14):cd.rectangle((x,y,x+13,y+13),fill=(78,81,88,255) if (x//14+y//14)%2 else (45,48,54,255))
 for i,(name,im) in enumerate(items):
  col,row=i%cols,i//cols;x,y=g+col*cw,g+row*ch;bbox=im.getchannel('A').getbbox();d.text((x,y),f'{name}  {bbox}',fill=(245,245,248));tile=checker.copy()
  if bbox:
   crop=im.crop(bbox);crop.thumbnail((tw-8,th-8),Image.Resampling.NEAREST);tile.alpha_composite(crop,((tw-crop.width)//2,(th-crop.height)//2))
  board.paste(tile.convert('RGB'),(x,y+lh))
 board.save(path,quality=96,optimize=True)

def main():
 OUT.mkdir(parents=True,exist_ok=True);src=Image.open(SOURCE).convert('RGBA');rgba=np.asarray(src);alpha=rgba[...,3];h,w=alpha.shape
 pm=json.loads((PREV/'layer_manifest.json').read_text(encoding='utf-8'));old_order=[p['name'] for p in pm['parts']]
 old={n:Image.open(PREV/f'{n}.png').convert('RGBA') for n in old_order}
 old_masks={n:np.asarray(im.getchannel('A'),np.uint8) for n,im in old.items()}
 rgb=rgba[...,:3];hsv=cv2.cvtColor(rgb,cv2.COLOR_RGB2HSV);H,S,V=cv2.split(hsv)
 # Lavender/pearl hair only: hue range for lavender shading plus low-saturation
 # pearl highlights, bounded to hand-traced head/hair regions. Skin/teal/blue
 # eyes are excluded by hue and geometry. Dark line edges are expanded 1 px.
 lavender=(H>=112)&(H<=158)&(S>=12)&(V>=95)
 pearl=(S<=24)&(np.abs(rgb[...,0].astype(np.int16)-rgb[...,2].astype(np.int16))<=24)&(rgb.min(axis=2)>170)&(V>200)
 pearl[610:,:]=False
 # White/lavender highlights are included only when they touch hair-colored
 # pixels; detached eye whites and garment pixels are therefore not keyed in.
 pearl_near=cv2.dilate(lavender.astype(np.uint8),np.ones((3,3),np.uint8),iterations=1)>0
 haircolor=(lavender|(pearl&pearl_near))&(alpha>0)
 nonhair_parts=['EyeWhite_L','EyeBall_L','Eyelash_L','Brow_L','EyeWhite_R','EyeBall_R','Eyelash_R','Brow_R','Nose','Mouth_Closed','Whale_Clip','Jacket_Body_L','Jacket_Body_R','Shirt_Front','Neck','Cuff_L','Cuff_R','Hand_L','Hand_R']
 nonhair=np.zeros((h,w),np.uint8)
 for n in nonhair_parts:nonhair=np.maximum(nonhair,old_masks[n])
 haircolor&=(nonhair==0)
 ahoge_poly=[(548,50),(668,50),(700,95),(696,150),(674,182),(645,203),(594,199),(565,177),(548,140)]
 bangs_poly=[(505,302),(535,278),(565,267),(595,269),(625,274),(657,278),(691,286),(723,301),(745,323),(746,365),(733,401),(718,438),(700,472),(680,495),(652,514),(623,520),(594,512),(565,490),(542,461),(525,430),(510,397),(502,360)]
 side_l_poly=[(380,190),(445,184),(500,205),(525,270),(530,340),(522,420),(532,500),(548,565),(548,625),(508,630),(465,615),(430,580),(400,530),(382,470),(374,390),(378,300)]
 side_r_poly=mirror(side_l_poly)
 back_poly=[(392,250),(408,210),(453,180),(500,160),(555,151),(610,148),(666,151),(722,160),(773,179),(816,210),(842,250),(844,300),(825,340),(795,365),(760,366),(730,345),(700,324),(665,309),(630,298),(590,295),(550,305),(520,327),(490,350),(455,360),(426,342),(405,314)]
 polys={'Hair_Ahoge':ahoge_poly,'Hair_Bangs':bangs_poly,'Hair_Side_L':side_l_poly,'Hair_Side_R':side_r_poly,'Hair_Back':back_poly}
 # source-coordinate extraction, with 1px edge expansion contained in each ROI
 m={}
 eye_guard=np.zeros((h,w),np.uint8)
 cv2.ellipse(eye_guard,(520,412),(30,30),0,0,360,255,-1)
 cv2.ellipse(eye_guard,(744,412),(30,30),0,0,360,255,-1)
 for name,pts in polys.items():
  roi=polygon(pts,(w,h))>0
  face_guard=(eye_guard==0) if name=='Hair_Bangs' else np.ones((h,w),dtype=bool)
  candidate=(haircolor&roi&face_guard).astype(np.uint8)
  candidate=cv2.morphologyEx(candidate,cv2.MORPH_CLOSE,np.ones((3,3),np.uint8))
  candidate=cv2.dilate(candidate,np.ones((3,3),np.uint8),iterations=1)
  candidate=(candidate>0)&roi&(alpha>0)
  m[name]=candidate.astype(np.uint8)*255
 # Assign mutually-exclusive visible pixels: ahoge, bangs, side locks, then
 # residual crown/back hair. This avoids duplicate dark edges between parts.
 assigned=np.zeros((h,w),np.uint8)
 for name in ('Hair_Ahoge','Hair_Bangs','Hair_Side_L','Hair_Side_R'):
  m[name][assigned>0]=0;assigned=np.maximum(assigned,m[name])
 m['Hair_Back'][assigned>0]=0
 # Keep small detached color specks out of these large silhouette cuts.
 for name in m:
  num,labels,stats,_=cv2.connectedComponentsWithStats((m[name]>0).astype(np.uint8),8)
  cleaned=np.zeros((h,w),np.uint8)
  # Small isolated components in the face ROI were inspected as stray edge
  # fragments/ambiguous line ownership; keep only coherent hair masses here.
  minarea=12 if name=='Hair_Ahoge' else (500 if name in ('Hair_Bangs','Hair_Side_L','Hair_Side_R') else 20)
  for i in range(1,num):
   if stats[i,cv2.CC_STAT_AREA]>=minarea:cleaned[labels==i]=255
  m[name]=cleaned
 areas={n:int(np.count_nonzero(a)) for n,a in m.items()}
 for n,a in areas.items():
  if a<250:raise SystemExit(f'hair selection too small: {n}={a}')
 # Approximate skin-colored hidden fill under fringe and face-side locks. Erode
 # masks so these flat fills remain fully covered in the approved neutral pose.
 front=np.maximum.reduce([m['Hair_Bangs'],m['Hair_Side_L'],m['Hair_Side_R']])
 under=cv2.erode((front>0).astype(np.uint8),np.ones((7,7),np.uint8),iterations=1)*255
 # Limit to front hair regions whose projection is over the face, not crown.
 face_roi=polygon([(455,300),(815,300),(825,650),(455,650)],(w,h))
 under=((under>0)&(face_roi>0)).astype(np.uint8)*255
 # use average of visible cheek skin (v1.1 source sample region)
 skin_roi=rgba[430:610,535:750,:3]
 skin_rgb=tuple(int(v) for v in np.median(skin_roi.reshape(-1,3),axis=0))
 skinfill=fill(skin_rgb,under)
 new={n:source_layer(src,a) for n,a in m.items()};new['Underpaint_FaceBehindHair_WIP']=skinfill
 # old layer order: keep body underparts first; add hair back behind face
 # features, then side/bangs/ahoge above them, whale clip remains foremost.
 face_start=old_order.index('EyeWhite_L')
 order=old_order[:face_start]+['Underpaint_FaceBehindHair_WIP','Hair_Back']+old_order[face_start:]
 insert=order.index('Whale_Clip')
 order[insert:insert]=['Hair_Side_L','Hair_Side_R','Hair_Bangs','Hair_Ahoge']
 # The color clip is independent and should remain topmost over hair.
 all_masks=np.zeros((h,w),np.uint8)
 for a in old_masks.values():all_masks=np.maximum(all_masks,a)
 for a in m.values():all_masks=np.maximum(all_masks,a)
 bgr=cv2.cvtColor(rgb,cv2.COLOR_RGB2BGR);clean=cv2.inpaint(bgr,(all_masks>0).astype(np.uint8)*255,4,cv2.INPAINT_TELEA)
 ba=rgba.copy();ba[...,:3]=cv2.cvtColor(clean,cv2.COLOR_BGR2RGB);ba[...,3]=((alpha.astype(np.uint16)*(255-all_masks.astype(np.uint16)))//255).astype(np.uint8)
 base=Image.fromarray(ba,'RGBA');base.save(OUT/'Base_Figure_HairUnderpaint_WIP.png',optimize=True)
 new['Underpaint_FaceBehindHair_WIP'].save(OUT/'Underpaint_FaceBehindHair_WIP.png',optimize=True)
 for n in m:new[n].save(OUT/f'{n}.png',optimize=True)
 layers=[]
 for n in order:
  im=new[n] if n in new else old[n]
  im.save(OUT/f'{n}.png',optimize=True);layers.append((n,im))
 comp=base.copy()
 for _,im in layers:comp.alpha_composite(im)
 comp.save(OUT/'authoring_pass_07_composite.png',optimize=True);src.save(OUT/'reference_v1_1_alpha_edge_connected.png',optimize=True)
 diff=np.abs(np.asarray(comp).astype(np.int16)-np.asarray(src).astype(np.int16)).astype(np.uint8)
 Image.fromarray(diff,'RGBA').save(OUT/'reconstruction_diff.png',optimize=True)
 changed=int(np.count_nonzero(np.any(diff[...,:3]>2,axis=2)));maxdiff=int(diff[...,:3].max())
 review_board([(n,new[n]) for n in ['Hair_Back','Hair_Side_L','Hair_Side_R','Hair_Bangs','Hair_Ahoge','Underpaint_FaceBehindHair_WIP']],OUT/'hair_edge_review.jpg')
 # All-layer board for overall stack
 review_board(layers,OUT/'layer_review_board.jpg',3,310,205)
 ora=OUT/'xiaoxun_loli_v1_1_authoring_pass_07.ora'
 root=Element('image',{'version':'0.0.1','w':str(w),'h':str(h),'name':'Xiaoxun Loli v1.1 - authoring pass 07 WIP','xres':'72','yres':'72'});stack=SubElement(root,'stack')
 SubElement(stack,'layer',{'name':'NEW v1.1 reference - locked, hidden','src':'data/reference.png','opacity':'0.55','visibility':'hidden','composite-op':'svg:src-over','x':'0','y':'0'})
 group=SubElement(stack,'stack',{'name':'Hair source-visible cuts + estimated face underfill - WIP','opacity':'1.0','visibility':'visible','composite-op':'svg:src-over'})
 data={f'data/part_{i:02d}.png':png(im) for i,(_,im) in enumerate(layers)}
 for i in reversed(range(len(layers))):
  n,_=layers[i];SubElement(group,'layer',{'name':n,'src':f'data/part_{i:02d}.png','opacity':'1.0','visibility':'visible','composite-op':'svg:src-over','x':'0','y':'0'})
 SubElement(stack,'layer',{'name':'00 Flat figure with approximate inpaint (WIP)','src':'data/base.png','opacity':'1.0','visibility':'visible','composite-op':'svg:src-over','x':'0','y':'0'})
 with zipfile.ZipFile(ora,'w') as z:
  z.writestr('mimetype','image/openraster',compress_type=zipfile.ZIP_STORED)
  for k,v in {'data/reference.png':png(src),'data/base.png':png(base),**data,'stack.xml':tostring(root,encoding='utf-8',xml_declaration=True),'mergedimage.png':png(comp)}.items():z.writestr(k,v,compress_type=zipfile.ZIP_DEFLATED)
 parts=[]
 for n,im in layers:
  state='estimated flat face-color fill; not hand-painted' if n.startswith('Underpaint_') else ('carried from pass06' if n in old else 'source-visible color/ROI cutout WIP')
  parts.append({'name':n,'file':f'{n}.png','state':state,'canvas_px':[w,h]})
 manifest={'status':'WIP source-visible hair split with estimated hidden face fill; not complete art/PSD/PSB/Cubism','source':'../reference_v1_1_alpha_edge_connected.png','source_sha256':sha(SOURCE),'canvas_px':[w,h],'ora_file':ora.name,'parts':parts,'hair_selection_pixels':areas,'reconstruction_check':{'pixels_changed_over_2_rgb_levels':changed,'max_channel_difference':maxdiff,'interpretation':'static registered pixels only; no hidden-art/edge/deformation acceptance'},'known_gaps':['Hair color masks are ROI-constrained source cuts, not full semantic painted parts; visible alpha edges need brush cleanup. Small disconnected/ambiguous edge fragments were deliberately not force-assigned and remain fused in the base.','Face fill under fringe is a flat sampled-color estimate and does not restore line art, shading, or a complete 3D head surface.','No true back-hair extensions beneath bangs or strand-specific overlap reconstruction.','Ears/head contour remain fused; brows/eyes and mouth hidden-state artwork remain incomplete.','No manual raster-editor work, PSD/PSB, Cubism Editor project/export, or runtime QA.']}
 (OUT/'layer_manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 files=sorted(p for p in OUT.iterdir() if p.is_file() and p.name!='SHA256SUMS.txt')
 (OUT/'SHA256SUMS.txt').write_text(''.join(f'{sha(p)}  {p.name}\n' for p in files),encoding='utf-8')
 print(json.dumps({'ora':ora.name,'parts':len(layers),'hair_pixels':areas,'static_changed':changed,'max_diff':maxdiff,'status':manifest['status']},ensure_ascii=False))
 return 0
if __name__=='__main__':raise SystemExit(main())
