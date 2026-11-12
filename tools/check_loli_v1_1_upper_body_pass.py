#!/usr/bin/env python3
"""Structural and pixel-registration checks for upper-body pass06 WIP."""
from __future__ import annotations
import json, zipfile
from pathlib import Path
from xml.etree import ElementTree as ET
import numpy as np
from PIL import Image
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'characters/xiaoxun/design/loli_live2d_v1/authoring_v1_1/authoring_pass_06'
NEW=['Jacket_Body_L','Jacket_Body_R','Shirt_Front','Neck','Cuff_L','Cuff_R','Hand_L','Hand_R']
FILL=['Underpaint_Shirt_WIP','Underpaint_Hand_L_WIP','Underpaint_Hand_R_WIP','Underpaint_Jacket_WIP']
BOUNDS={'Jacket_Body_L':(465,620,605,1095),'Jacket_Body_R':(675,620,815,1095),'Shirt_Front':(580,640,710,1150),'Neck':(585,565,695,665),'Cuff_L':(315,1010,410,1070),'Cuff_R':(870,1010,965,1070),'Hand_L':(310,1045,390,1150),'Hand_R':(890,1045,970,1150)}
def main():
 errors=[];m=json.loads((OUT/'layer_manifest.json').read_text(encoding='utf-8'));parts=m['parts'];names=[p['name'] for p in parts]
 if len(parts)!=32 or len(set(names))!=32: errors.append('expected 32 unique stack parts')
 if not set(NEW+FILL).issubset(names): errors.append('missing new body or overlap-fill layers')
 for name in NEW+FILL:
  p=OUT/f'{name}.png'
  if not p.exists(): errors.append(f'missing {name}');continue
  im=Image.open(p).convert('RGBA')
  if im.size!=(1280,1920): errors.append(f'canvas mismatch: {name}')
  bbox=im.getchannel('A').getbbox()
  if bbox is None: errors.append(f'empty: {name}');continue
  if name in BOUNDS:
   x0,y0,x1,y1=BOUNDS[name]
   if not(x0<=bbox[0] and y0<=bbox[1] and bbox[2]<=x1 and bbox[3]<=y1):errors.append(f'outside traced ROI: {name} {bbox}')
 if m['reconstruction_check']['pixels_changed_over_2_rgb_levels']!=0 or m['reconstruction_check']['max_channel_difference']!=0:errors.append('manifest static registration is not exact')
 # Exact RGB provenance for each newly cut source-visible region.
 source=np.asarray(Image.open(ROOT/'characters/xiaoxun/design/loli_live2d_v1/authoring_v1_1/reference_v1_1_alpha_edge_connected.png').convert('RGBA'))
 new_rgba={n:np.asarray(Image.open(OUT/f'{n}.png').convert('RGBA')) for n in NEW}
 for n,layer in new_rgba.items():
  visible=layer[...,3]>0
  if np.any(visible) and not np.array_equal(layer[visible,:3],source[visible,:3]):errors.append(f'non-source RGB in visible cutout: {n}')
 # Every estimated fill must remain fully behind its intended visible cover in
 # the neutral view; otherwise it would change the approved still.
 alphas={n:np.asarray(Image.open(OUT/f'{n}.png').convert('RGBA'))[...,3] for n in names}
 covers={'Underpaint_Shirt_WIP':np.maximum.reduce([alphas['Jacket_Body_L'],alphas['Jacket_Body_R'],alphas['Skirt']]),
         'Underpaint_Hand_L_WIP':np.maximum(alphas['Cuff_L'],alphas['JacketSleeve_Teal_L']),
         'Underpaint_Hand_R_WIP':np.maximum(alphas['Cuff_R'],alphas['JacketSleeve_Teal_R']),
         'Underpaint_Jacket_WIP':np.maximum(alphas['JacketSleeve_Teal_L'],alphas['JacketSleeve_Teal_R'])}
 for n,cover in covers.items():
  fill=alphas[n]>0
  if np.any(fill & (cover==0)):errors.append(f'estimated hidden fill spills outside current cover: {n}')
 with zipfile.ZipFile(OUT/m['ora_file']) as z:
  if z.read('mimetype')!=b'image/openraster' or z.getinfo('mimetype').compress_type!=zipfile.ZIP_STORED:errors.append('ORA mimetype invalid')
  root=ET.fromstring(z.read('stack.xml'));layers=root.findall('.//layer')
  if len(layers)!=34:errors.append(f'ORA expected 34 layer nodes, found {len(layers)}')
  merged=np.asarray(Image.open(z.open('mergedimage.png')).convert('RGBA'))
 comp=np.asarray(Image.open(OUT/'authoring_pass_06_composite.png').convert('RGBA'))
 if not np.array_equal(merged,comp):errors.append('ORA merged image differs from composite')
 diff=np.asarray(Image.open(OUT/'reconstruction_diff.png').convert('RGBA'))
 changed=int(np.count_nonzero(np.any(diff[...,:3]>2,axis=2)));maxdiff=int(diff[...,:3].max())
 if changed or maxdiff:errors.append(f'source reassembly diff: {changed}px / max {maxdiff}')
 if errors:
  print('\n'.join('FAIL: '+x for x in errors));return 1
 print('PASS: 32 parts, 8 bounded new visible cutouts, 4 overlap-fill layers, 34 ORA layer nodes; static reassembly 0px/max0')
 print('LIMIT: estimated flat underfills and source-mask registration only; no hand-paint, hidden-art, edge-quality or motion acceptance')
 return 0
if __name__=='__main__':raise SystemExit(main())
