#!/usr/bin/env python3
"""Check the source-visible lower-body WIP pass (not artistic/Cubism QA)."""
from __future__ import annotations

import json
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

import numpy as np
from PIL import Image

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"characters/xiaoxun/design/loli_live2d_v1/authoring_v1_1/authoring_pass_05"
EXPECTED={"Leg_Skin_L","Leg_Skin_R","Skirt","Sock_L","Sock_R","Shoe_L","Shoe_R","JacketSleeve_Teal_L","JacketSleeve_Teal_R","EyeWhite_L","EyeBall_L","Eyelash_L","Brow_L","EyeWhite_R","EyeBall_R","Eyelash_R","Brow_R","Nose","Mouth_Closed","Whale_Clip"}
BOUNDS={
 "Leg_Skin_L":(470,1180,635,1530),"Leg_Skin_R":(645,1180,810,1530),"Skirt":(425,1080,860,1230),
 "Sock_L":(485,1485,625,1750),"Sock_R":(655,1485,795,1750),"Shoe_L":(495,1700,635,1890),"Shoe_R":(645,1700,785,1890),
}

def main()->int:
 errors=[]
 m=json.loads((OUT/"layer_manifest.json").read_text(encoding="utf-8"))
 parts=m.get("parts",[])
 if {p.get("name") for p in parts}!=EXPECTED or len(parts)!=20: errors.append("expected the 20 registered lower-body/garment/face WIP layers")
 for part in parts:
  name=part["name"]; f=OUT/part["file"]
  if not f.exists(): errors.append(f"missing {name}"); continue
  im=Image.open(f).convert("RGBA")
  if im.size!=(1280,1920): errors.append(f"canvas mismatch: {name}")
  bbox=im.getchannel("A").getbbox()
  if bbox is None: errors.append(f"empty layer: {name}"); continue
  if name in BOUNDS:
   x0,y0,x1,y1=BOUNDS[name]
   if not (x0<=bbox[0] and y0<=bbox[1] and bbox[2]<=x1 and bbox[3]<=y1): errors.append(f"ROI bounds mismatch {name}: {bbox}")
 with zipfile.ZipFile(OUT/m["ora_file"]) as z:
  if z.namelist()[0]!="mimetype" or z.getinfo("mimetype").compress_type!=zipfile.ZIP_STORED or z.read("mimetype")!=b"image/openraster": errors.append("invalid ORA mimetype")
  root=ET.fromstring(z.read("stack.xml"))
  if (root.get("w"),root.get("h"))!=("1280","1920"): errors.append("ORA canvas mismatch")
  layers=root.findall(".//layer")
  if len(layers)!=22 or not EXPECTED.issubset({n.get("name") for n in layers}): errors.append(f"ORA stack mismatch: {len(layers)} layers")
  merged=np.asarray(Image.open(z.open("mergedimage.png")).convert("RGBA"))
 comp=np.asarray(Image.open(OUT/"authoring_pass_05_composite.png").convert("RGBA"))
 if not np.array_equal(merged,comp): errors.append("ORA merged image differs from review composite")
 diff=np.asarray(Image.open(OUT/"reconstruction_diff.png").convert("RGBA"))
 changed=int(np.count_nonzero(np.any(diff[...,:3]>2,axis=2))); maxdiff=int(diff[...,:3].max())
 qa=m.get("reconstruction_check",{})
 if changed!=qa.get("pixels_changed_over_2_rgb_levels") or maxdiff!=qa.get("max_channel_difference"): errors.append("static QA metrics disagree")
 if changed>300 or maxdiff>64: errors.append(f"static diagnostic outside bound: {changed}px/max{maxdiff}")
 if errors:
  for e in errors: print("FAIL:",e)
  return 1
 print(f"PASS: 20 visible-source layers; 22-layer ORA; bounds and static reassembly match ({changed}px/max{maxdiff})")
 print("LIMIT: static source coverage only; not hidden-art, deformation, PSD import, or Cubism QA")
 return 0

if __name__=="__main__": raise SystemExit(main())
