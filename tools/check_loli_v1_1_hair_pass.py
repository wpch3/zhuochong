#!/usr/bin/env python3
"""Structural/provenance checks for pass07 hair cutout WIP."""
from __future__ import annotations
import json,zipfile
from pathlib import Path
from xml.etree import ElementTree as ET
import numpy as np
from PIL import Image
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'characters/xiaoxun/design/loli_live2d_v1/authoring_v1_1/authoring_pass_07'
HAIR=['Hair_Back','Hair_Side_L','Hair_Side_R','Hair_Bangs','Hair_Ahoge']
FILL='Underpaint_FaceBehindHair_WIP'
BOUNDS={'Hair_Back':(495,150,790,375),'Hair_Side_L':(400,205,560,610),'Hair_Side_R':(720,205,885,625),'Hair_Bangs':(495,255,760,485),'Hair_Ahoge':(550,50,700,215)}
def main():
 errors=[];m=json.loads((OUT/'layer_manifest.json').read_text(encoding='utf-8'));parts=m['parts'];names=[p['name'] for p in parts]
 if len(parts)!=38 or len(set(names))!=38:errors.append('expected 38 unique ORA parts')
 if not set(HAIR+[FILL]).issubset(names):errors.append('missing hair or underfill layer')
 src=np.asarray(Image.open(ROOT/'characters/xiaoxun/design/loli_live2d_v1/authoring_v1_1/reference_v1_1_alpha_edge_connected.png').convert('RGBA'))
 layers={}
 for n in HAIR+[FILL]:
  p=OUT/f'{n}.png'
  if not p.exists():errors.append(f'missing {n}');continue
  im=Image.open(p).convert('RGBA')
  if im.size!=(1280,1920):errors.append(f'canvas mismatch {n}')
  layers[n]=np.asarray(im)
  bbox=im.getchannel('A').getbbox()
  if bbox is None:errors.append(f'empty layer {n}');continue
  if n in BOUNDS:
   x0,y0,x1,y1=BOUNDS[n]
   if not(x0<=bbox[0] and y0<=bbox[1] and bbox[2]<=x1 and bbox[3]<=y1):errors.append(f'out-of-ROI {n}: {bbox}')
  if n in HAIR:
   active=layers[n][...,3]>0
   if not np.array_equal(layers[n][active,:3],src[active,:3]):errors.append(f'non-source RGB in {n}')
 union=np.maximum.reduce([layers[n][...,3] for n in HAIR])
 fillmask=layers.get(FILL,np.zeros((1920,1280,4),np.uint8))[...,3]>0
 if np.any(fillmask&(union==0)):errors.append('face underfill extends beyond hair coverage in neutral pose')
 if m['reconstruction_check']['pixels_changed_over_2_rgb_levels']!=0 or m['reconstruction_check']['max_channel_difference']!=0:errors.append('manifest says nonzero static diff')
 with zipfile.ZipFile(OUT/m['ora_file']) as z:
  if z.read('mimetype')!=b'image/openraster' or z.getinfo('mimetype').compress_type!=zipfile.ZIP_STORED:errors.append('invalid ORA mimetype')
  root=ET.fromstring(z.read('stack.xml'));nodes=root.findall('.//layer')
  if len(nodes)!=40:errors.append(f'expected 40 ORA layer nodes, got {len(nodes)}')
  merged=np.asarray(Image.open(z.open('mergedimage.png')).convert('RGBA'))
 comp=np.asarray(Image.open(OUT/'authoring_pass_07_composite.png').convert('RGBA'))
 if not np.array_equal(merged,comp):errors.append('ORA merged image differs from composite')
 diff=np.asarray(Image.open(OUT/'reconstruction_diff.png').convert('RGBA'))
 changed=int(np.count_nonzero(np.any(diff[...,:3]>2,axis=2)));maxdiff=int(diff[...,:3].max())
 if changed or maxdiff:errors.append(f'source reconstruction diff {changed}px/max{maxdiff}')
 if errors:print('\n'.join('FAIL: '+e for e in errors));return 1
 print('PASS: 38 parts, 5 bounded source-hair cuts, underfill coverage, exact source RGB, 40 ORA layer nodes; static diff 0px/max0')
 print('LIMIT: ROI/color cutouts and flat estimated fill only; no manual edge cleanup, hidden-art or motion acceptance')
 return 0
if __name__=='__main__':raise SystemExit(main())
