#!/usr/bin/env python3
"""Export cropped, lightweight browser layer assets for the Loli pass07 preview."""
from __future__ import annotations
import hashlib,json
from pathlib import Path
from PIL import Image
ROOT=Path(__file__).resolve().parents[1]
PASS=ROOT/'characters/xiaoxun/design/loli_live2d_v1/authoring_v1_1/authoring_pass_07'
OUT=ROOT/'web/loli-authoring-preview-assets/pass_07'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 OUT.mkdir(parents=True,exist_ok=True)
 m=json.loads((PASS/'layer_manifest.json').read_text(encoding='utf-8'));entries=[];pixels=0
 for p in m['parts']:
  im=Image.open(PASS/p['file']).convert('RGBA');bbox=im.getchannel('A').getbbox()
  if bbox is None:raise SystemExit(f"empty layer: {p['name']}")
  crop=im.crop(bbox);dst=OUT/f"{p['name']}.png";crop.save(dst,optimize=True)
  entries.append({'name':p['name'],'file':dst.name,'offset_xy':[bbox[0],bbox[1]],'canvas_px':[im.width,im.height],'crop_px':[crop.width,crop.height],'state':p.get('state','WIP')})
  pixels+=crop.width*crop.height
 data={'source_pass':'authoring_pass_07','source_manifest_sha256':sha(PASS/'layer_manifest.json'),'parts':entries,'total_cropped_pixels':pixels}
 (OUT/'manifest.json').write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 files=sorted(p for p in OUT.iterdir() if p.is_file() and p.name!='SHA256SUMS.txt')
 (OUT/'SHA256SUMS.txt').write_text(''.join(f'{sha(p)}  {p.name}\n' for p in files),encoding='utf-8')
 full=len(entries)*1280*1920
 print(f"PASS: {len(entries)} cropped layer assets; {pixels:,}/{full:,} pixel slots ({pixels/full:.1%}), {sum(p.stat().st_size for p in files)/1024:.1f} KiB")
if __name__=='__main__':main()
