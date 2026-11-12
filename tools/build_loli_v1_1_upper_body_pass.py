#!/usr/bin/env python3
"""Build a bounded upper-body source-cutout/overlap-fill WIP from v1.1.

All source pixels are retained where possible. Hidden fills are deliberately
flat, shape-guided estimates behind current overlaps; they are not hand-painted
or approved production art.
"""
from __future__ import annotations
import hashlib, json, zipfile
from io import BytesIO
from pathlib import Path
from xml.etree.ElementTree import Element, SubElement, tostring
import cv2
import numpy as np
from PIL import Image, ImageDraw

ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'characters/xiaoxun/design/loli_live2d_v1/authoring_v1_1'
PREV=BASE/'authoring_pass_05'
OUT=BASE/'authoring_pass_06'
SOURCE=BASE/'reference_v1_1_alpha_edge_connected.png'
SCALE=4

def poly_mask(points, size):
    im=Image.new('L',(size[0]*SCALE,size[1]*SCALE),0)
    ImageDraw.Draw(im).polygon([(int(x*SCALE),int(y*SCALE)) for x,y in points],fill=255)
    return (np.asarray(im.resize(size,Image.Resampling.BOX))>127).astype(np.uint8)*255

def mirror(points): return [(1280-x,y) for x,y in points]
def rgba_png(im):
    b=BytesIO(); im.save(b,format='PNG',optimize=True); return b.getvalue()
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def fill_layer(color, mask):
    a=np.zeros((1920,1280,4),dtype=np.uint8);a[...,:3]=color;a[...,3]=mask
    return Image.fromarray(a,'RGBA')
def source_layer(src, mask):
    a=np.asarray(src).copy();a[...,3]=((a[...,3].astype(np.uint16)*mask.astype(np.uint16))//255).astype(np.uint8)
    return Image.fromarray(a,'RGBA')
def save_board(items):
    cols,cw,ch,g,lh=3,310,205,12,23;rows=(len(items)+cols-1)//cols
    board=Image.new('RGB',(cols*cw+(cols+1)*g,rows*ch+(rows+1)*g),(29,32,37));d=ImageDraw.Draw(board)
    tw,th=cw-2*g,ch-lh-2*g;checker=Image.new('RGBA',(tw,th));cd=ImageDraw.Draw(checker)
    for y in range(0,th,12):
      for x in range(0,tw,12): cd.rectangle((x,y,x+11,y+11),fill=(77,80,87,255) if (x//12+y//12)%2 else (45,48,54,255))
    for i,(name,im) in enumerate(items):
      col,row=i%cols,i//cols;x,y=g+col*cw,g+row*ch;bbox=im.getchannel('A').getbbox();d.text((x,y),f'{name} {bbox}',fill=(245,245,248))
      tile=checker.copy()
      if bbox:
        crop=im.crop(bbox);crop.thumbnail((tw-8,th-8),Image.Resampling.LANCZOS);tile.alpha_composite(crop,((tw-crop.width)//2,(th-crop.height)//2))
      board.paste(tile.convert('RGB'),(x,y+lh))
    board.save(OUT/'layer_review_board.jpg',quality=94,optimize=True)

def save_zoom_board(items):
    cols,cw,ch,g,lh=2,570,290,14,24;rows=(len(items)+cols-1)//cols
    board=Image.new('RGB',(cols*cw+(cols+1)*g,rows*ch+(rows+1)*g),(27,30,35));d=ImageDraw.Draw(board)
    tw,th=cw-2*g,ch-lh-2*g;checker=Image.new('RGBA',(tw,th));cd=ImageDraw.Draw(checker)
    for y in range(0,th,14):
      for x in range(0,tw,14): cd.rectangle((x,y,x+13,y+13),fill=(78,81,88,255) if (x//14+y//14)%2 else (45,48,54,255))
    for i,(name,im) in enumerate(items):
      col,row=i%cols,i//cols;x,y=g+col*cw,g+row*ch;bbox=im.getchannel('A').getbbox();d.text((x,y),f'{name}   source bbox {bbox}',fill=(245,245,248))
      tile=checker.copy()
      if bbox:
        crop=im.crop(bbox);crop.thumbnail((tw-8,th-8),Image.Resampling.NEAREST);tile.alpha_composite(crop,((tw-crop.width)//2,(th-crop.height)//2))
      board.paste(tile.convert('RGB'),(x,y+lh))
    board.save(OUT/'upper_body_edge_review.jpg',quality=96,optimize=True)

def main():
    OUT.mkdir(parents=True,exist_ok=True)
    src=Image.open(SOURCE).convert('RGBA'); rgba=np.asarray(src);alpha=rgba[...,3];h,w=alpha.shape
    pm=json.loads((PREV/'layer_manifest.json').read_text())
    old={p['name']:Image.open(PREV/p['file']).convert('RGBA') for p in pm['parts']}
    # Traced silhouettes in native reference coordinates. The masks are bounded
    # by garment seams/cuffs; high-frequency edge ownership still needs paint QA.
    # The white jacket fronts sit inside the sleeves, around x=480..600 and
    # x=680..800. Keep the cream shirt in the narrow center channel.
    jacket_left=[(476,625),(493,628),(516,641),(542,651),(565,653),(590,663),(590,705),(586,760),(584,830),(583,900),(583,980),(588,1035),(596,1074),(581,1083),(544,1087),(510,1085),(487,1075),(474,1054),(474,1018),(479,970),(480,900),(481,820),(482,750),(481,690)]
    shirt_poly=[(590,650),(610,655),(628,660),(648,660),(670,655),(690,650),(690,710),(687,780),(685,860),(684,940),(686,1010),(694,1075),(702,1120),(690,1142),(665,1140),(642,1138),(620,1141),(600,1138),(587,1128),(589,1080),(590,1000),(590,900),(591,800),(590,720)]
    neck_poly=[(590,568),(690,568),(688,592),(683,608),(672,624),(658,641),(640,650),(620,650),(601,640),(590,625)]
    cuff_left=[(329,1018),(356,1023),(397,1025),(390,1042),(383,1062),(357,1060),(324,1053)]
    hand_left=[(331,1050),(355,1059),(386,1063),(381,1081),(378,1094),(385,1105),(376,1124),(366,1144),(353,1155),(342,1148),(335,1134),(327,1120),(321,1102),(323,1080)]
    hand_extension_left=[(320,1008),(378,1010),(399,1024),(390,1050),(386,1080),(385,1105),(376,1124),(366,1144),(353,1155),(342,1148),(335,1134),(327,1120),(321,1102)]
    masks={}
    for name,pts in [('Jacket_Body_L',jacket_left),('Jacket_Body_R',mirror(jacket_left)),('Shirt_Front',shirt_poly),('Neck',neck_poly),('Cuff_L',cuff_left),('Cuff_R',mirror(cuff_left)),('Hand_L',hand_left),('Hand_R',mirror(hand_left))]:
      masks[name]=((poly_mask(pts,(w,h)).astype(np.uint16)*alpha.astype(np.uint16))//255).astype(np.uint8)
    # Skin-tone connected pixels gate the neck/hands so adjacent fabric is not
    # swept in by the broad geometry. Dilate by one source pixel for ink edges.
    rgb=rgba[...,:3].astype(np.int16); skin=(rgb[...,0]>rgb[...,1]+4)&(rgb[...,1]>rgb[...,2]-18)&(rgb[...,0]-rgb[...,2]<85)&(rgb[...,0]>150)&(alpha>0)
    for name in ('Neck',):
      region=(masks[name]>0).astype(np.uint8)
      seed=(region.astype(bool)&skin).astype(np.uint8)
      if name=='Neck':
        count, labels, stats, _=cv2.connectedComponentsWithStats(seed,8)
        if count>1:
          keep=1+int(np.argmax(stats[1:,cv2.CC_STAT_AREA]));seed=(labels==keep).astype(np.uint8)
      seed=cv2.dilate(seed,np.ones((3,3),np.uint8),iterations=1)
      masks[name]=((seed>0)&(region>0)).astype(np.uint8)*alpha
    # Native image alpha limits all masks. Keep linework inside the polygon;
    # the body panels intentionally carry a small amount of neighboring source
    # edge where seam ownership is ambiguous, and the reviewer must decide it.
    for n in masks: masks[n][alpha==0]=0
    all_old_masks={n:np.asarray(im.getchannel('A'),dtype=np.uint8) for n,im in old.items()}
    # Keep the white torso-panel layers from inheriting teal sleeve pixels;
    # the existing teal sleeve parts own those visible source regions.
    sleeve_union=np.maximum(all_old_masks['JacketSleeve_Teal_L'],all_old_masks['JacketSleeve_Teal_R'])
    for n in ('Jacket_Body_L','Jacket_Body_R'):
      masks[n][sleeve_union>0]=0
    # Flat hidden-area underfills are restricted to pixels covered by a current
    # foreground overlap, so they do not alter the approved neutral still.
    cover_jacket=np.maximum(masks['Jacket_Body_L'],masks['Jacket_Body_R'])
    cover_skirt=all_old_masks['Skirt']
    shirt_hidden=np.maximum(cover_jacket,cover_skirt)
    shirt_hidden[(masks['Shirt_Front']>0)]=0
    shirt_color=tuple(int(v) for v in np.median(rgb[(masks['Shirt_Front']>0),:],axis=0))
    shirt_fill=fill_layer(shirt_color,shirt_hidden)
    cover_cuffs=np.maximum(masks['Cuff_L'],masks['Cuff_R'])
    sleeve=np.maximum(all_old_masks['JacketSleeve_Teal_L'],all_old_masks['JacketSleeve_Teal_R'])
    hand_cover=np.maximum(cover_cuffs,sleeve)
    hand_l=np.zeros((h,w),np.uint8);hand_r=hand_l.copy()
    for side in ('L','R'):
      n=f'Hand_{side}'; region=(poly_mask(mirror(hand_extension_left) if side=='R' else hand_extension_left,(w,h))>0)
      hidden=(hand_cover>0)&region&(masks[n]==0); (hand_l if side=='L' else hand_r)[hidden]=255
    hand_color=tuple(int(v) for v in np.median(rgb[(masks['Hand_L']>0)|(masks['Hand_R']>0),:],axis=0))
    hand_fill_l=fill_layer(hand_color,hand_l);hand_fill_r=fill_layer(hand_color,hand_r)
    jacket_cover=sleeve.copy(); jacket_hidden=(jacket_cover>0)&(cover_jacket==0)
    jacket_color=tuple(int(v) for v in np.median(rgb[(cover_jacket>0)&(alpha>0),:],axis=0))
    jacket_fill=fill_layer(jacket_color,jacket_hidden.astype(np.uint8)*255)

    # Cut visible source pixels from the flat base; preserve exact source RGB in
    # each extracted part. Existing pass05 visible masks remain unchanged.
    union=np.zeros((h,w),np.uint8)
    for m in all_old_masks.values(): union=np.maximum(union,m)
    for m in masks.values(): union=np.maximum(union,m)
    bgr=cv2.cvtColor(rgba[...,:3],cv2.COLOR_RGB2BGR)
    cleaned=cv2.inpaint(bgr,(union>0).astype(np.uint8)*255,4,cv2.INPAINT_TELEA)
    base_rgba=rgba.copy();base_rgba[...,:3]=cv2.cvtColor(cleaned,cv2.COLOR_BGR2RGB)
    base_rgba[...,3]=((alpha.astype(np.uint16)*(255-union.astype(np.uint16)))//255).astype(np.uint8)
    base=Image.fromarray(base_rgba,'RGBA');base.save(OUT/'Base_Figure_UpperBodyUnderpaint_WIP.png',optimize=True)
    new_layers={n:source_layer(src,m) for n,m in masks.items()}
    new_layers.update({'Underpaint_Shirt_WIP':shirt_fill,'Underpaint_Hand_L_WIP':hand_fill_l,'Underpaint_Hand_R_WIP':hand_fill_r,'Underpaint_Jacket_WIP':jacket_fill})
    order=['Leg_Skin_L','Leg_Skin_R','Sock_L','Sock_R','Shoe_L','Shoe_R','Underpaint_Shirt_WIP','Underpaint_Hand_L_WIP','Underpaint_Hand_R_WIP','Underpaint_Jacket_WIP','Skirt','Shirt_Front','Jacket_Body_L','Jacket_Body_R','Neck','Hand_L','Hand_R','Cuff_L','Cuff_R','JacketSleeve_Teal_L','JacketSleeve_Teal_R','EyeWhite_L','EyeBall_L','Eyelash_L','Brow_L','EyeWhite_R','EyeBall_R','Eyelash_R','Brow_R','Nose','Mouth_Closed','Whale_Clip']
    layers=[]
    for n in order:
      im=new_layers[n] if n in new_layers else old[n]
      im.save(OUT/f'{n}.png',optimize=True);layers.append((n,im))
    # Static reassembly in the exact same order; hidden flat fills are expected
    # to be fully occluded at neutral pose. Any visible spill is a hard fail.
    comp=base.copy()
    for _,im in layers: comp.alpha_composite(im)
    comp.save(OUT/'authoring_pass_06_composite.png',optimize=True)
    ref=src;ref.save(OUT/'reference_v1_1_alpha_edge_connected.png',optimize=True)
    diff=np.abs(np.asarray(comp).astype(np.int16)-np.asarray(ref).astype(np.int16)).astype(np.uint8)
    Image.fromarray(diff,'RGBA').save(OUT/'reconstruction_diff.png',optimize=True)
    changed=int(np.count_nonzero(np.any(diff[...,:3]>2,axis=2)));maxdiff=int(diff[...,:3].max())
    save_board(layers)
    save_zoom_board([(n,new_layers[n]) for n in ['Jacket_Body_L','Jacket_Body_R','Shirt_Front','Neck','Hand_L','Hand_R','Cuff_L','Cuff_R','Underpaint_Shirt_WIP','Underpaint_Hand_L_WIP','Underpaint_Hand_R_WIP','Underpaint_Jacket_WIP']])
    # ORA top-to-bottom; group children's order is reversed from composite order.
    ora=OUT/'xiaoxun_loli_v1_1_authoring_pass_06.ora'
    root=Element('image',{'version':'0.0.1','w':str(w),'h':str(h),'name':'Xiaoxun Loli v1.1 - authoring pass 06 WIP','xres':'72','yres':'72'})
    stack=SubElement(root,'stack')
    SubElement(stack,'layer',{'name':'NEW v1.1 reference - locked, hidden','src':'data/reference.png','opacity':'0.55','visibility':'hidden','composite-op':'svg:src-over','x':'0','y':'0'})
    group=SubElement(stack,'stack',{'name':'Upper-body source-visible parts + estimated hidden fills - WIP','opacity':'1.0','visibility':'visible','composite-op':'svg:src-over'})
    data={f'data/part_{i:02d}.png':rgba_png(im) for i,(_,im) in enumerate(layers)}
    for i in reversed(range(len(layers))):
      n,_=layers[i];SubElement(group,'layer',{'name':n,'src':f'data/part_{i:02d}.png','opacity':'1.0','visibility':'visible','composite-op':'svg:src-over','x':'0','y':'0'})
    SubElement(stack,'layer',{'name':'00 Flat figure with approximate inpaint (WIP)','src':'data/base.png','opacity':'1.0','visibility':'visible','composite-op':'svg:src-over','x':'0','y':'0'})
    with zipfile.ZipFile(ora,'w') as z:
      z.writestr('mimetype','image/openraster',compress_type=zipfile.ZIP_STORED)
      for k,v in {'data/reference.png':rgba_png(ref),'data/base.png':rgba_png(base),**data,'stack.xml':tostring(root,encoding='utf-8',xml_declaration=True),'mergedimage.png':rgba_png(comp)}.items():z.writestr(k,v,compress_type=zipfile.ZIP_DEFLATED)
    entries=[]
    for n,im in layers:
      state='estimated flat overlap underpaint; not hand-painted' if n.startswith('Underpaint_') else ('carried from pass05' if n in old else 'source-visible polygon cutout WIP')
      entries.append({'name':n,'file':f'{n}.png','state':state,'canvas_px':[w,h]})
    manifest={'status':'WIP only; source-visible upper-body cutouts plus estimated hidden fills; not complete illustration/PSD/PSB/Cubism','source':'../reference_v1_1_alpha_edge_connected.png','source_sha256':sha(SOURCE),'canvas_px':[w,h],'ora_file':ora.name,'parts':entries,'reconstruction_check':{'pixels_changed_over_2_rgb_levels':changed,'max_channel_difference':maxdiff,'interpretation':'static registration only; not artistic/edge/motion acceptance'},'known_gaps':['Flat underfills are vector/coordinate-guided estimates, not brush-painted art; hidden extension and deformation fit are still unverified.','Torso/neck/hand/cuff silhouettes are bounded cutouts and require manual line ownership/edge cleanup.','Hair is still fused into the base; neck overlap behind hair is not safely painted.','No upper arm/forearm articulation, no jacket collar/facing split, no hidden face/eye/mouth art, and no motion-validated overlap.','No PSD/PSB or official Cubism Editor project/export/runtime validation.']}
    (OUT/'layer_manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    files=sorted(p for p in OUT.iterdir() if p.is_file() and p.name!='SHA256SUMS.txt')
    (OUT/'SHA256SUMS.txt').write_text(''.join(f'{sha(p)}  {p.name}\n' for p in files),encoding='utf-8')
    print(json.dumps({'ora':ora.name,'parts':len(layers),'changed_pixels_over_2':changed,'max_rgb_diff':maxdiff,'status':manifest['status']},ensure_ascii=False))
    return 0
if __name__=='__main__':raise SystemExit(main())
