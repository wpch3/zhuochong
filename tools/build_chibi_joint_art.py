#!/usr/bin/env python3
"""Make a non-destructive Chibi wrist cleanup and elbow-split art trial.

Explicit new art overlays selected pixels and does not claim neutral equality.
Build only into an unoccupied build subdirectory. Not production art.
"""
import argparse
from io import BytesIO
import json
from pathlib import Path
import shutil
import sys
import tempfile
import numpy as np
from PIL import Image
import resvg_py
import build_chibi_wrists as wrist
import build_chibi_underlay as torso
from build_dynamic_chibi import bind,parameter

ROOT=Path(__file__).resolve().parents[1]
ART=ROOT/'experiments/live2d_chibi_joint_art'
EXPECTED_WRIST='709d1b293b46bfe0f940da5ef016d4800333c92bb92c2825c2ad72b20ecdc832'

def raster(name):
 return np.array(Image.open(BytesIO(resvg_py.svg_to_bytes(svg_path=str(ART/name),width=480,height=512,skip_system_fonts=True))).convert('RGBA'))

def build(output):
 out=Path(output);root=(ROOT/'build').resolve();resolved=out.resolve()
 if root not in resolved.parents:raise ValueError('output must be inside build')
 if out.exists() or out.is_symlink() or not out.parent.is_dir():raise ValueError('output must be a new directory with existing parent')
 if torso.sha(wrist.SVG)!=EXPECTED_WRIST:raise ValueError('wrist source changed; review joint positions')
 cleanup,contours,elbows,shoulders=(raster(n) for n in ('wrist_cleanup.svg','wrist_contours.svg','elbow_underpaint.svg','shoulder_underpaint.svg'))
 yy,xx=np.indices((512,480));summary={}
 with tempfile.TemporaryDirectory(prefix='joint-source-',dir=root) as temp:
  base=Path(temp)/'base';original=wrist.build(base);rig=json.loads((base/'rig.json').read_text())
  out.mkdir()
  try:
   shutil.copytree(base/'sprites',out/'sprites')
   for side in 'lr':
    p=out/f'sprites/hand_{side}.png';hand=np.array(Image.open(p).convert('RGBA'));before=hand.copy()
    d=yy-(.52*xx+156 if side=='l' else 376-.46*xx)
    span=(xx>=84)&(xx<=108) if side=='l' else (xx>=354)&(xx<=378)
    select=span&(d>=0)&(d<=3)&(hand[:,:,3]>0)
    weight=cleanup[:,:,3].astype(np.float32)/255*select
    hand[:,:,:3]=np.round(hand[:,:,:3]*(1-weight[:,:,None])+cleanup[:,:,:3]*weight[:,:,None]).astype(np.uint8)
    if not np.array_equal(hand[:,:,3],before[:,:,3]):raise ValueError('hand transparency changed')
    changed=np.any(hand!=before,axis=2)
    if not changed.any() or np.any(changed&~select):raise ValueError('unexpected hand cleanup')
    Image.fromarray(hand).save(p)
    sleeve=np.array(Image.open(out/f'sprites/arm_{side}.png').convert('RGBA'))
    body=np.array(Image.open(out/'sprites/body.png').convert('RGBA'))
    shoulder=shoulders.copy()
    allowed=((sleeve[:,:,3]==255)|(body[:,:,3]==255)) & ((xx<240) if side=='l' else (xx>=240))
    shoulder[~allowed]=0
    if not np.any(shoulder[:,:,3]):raise ValueError('empty shoulder art')
    Image.fromarray(shoulder).save(out/f'sprites/shoulder_under_{side}.png')
    wrist_art=contours.copy();wrist_art[~((sleeve[:,:,3]==255)&((xx<240) if side=='l' else (xx>=240)))]=0
    if not np.any(wrist_art[:,:,3]):raise ValueError('empty wrist art')
    Image.fromarray(wrist_art).save(out/f'sprites/wrist_under_{side}.png')
    upper=sleeve.copy();upper[yy>=137]=0
    lower=sleeve.copy()
    # Keep a 4px opaque overlap under the original sleeve to avoid exposing
    # the split when C independently filters the two layers at small scales.
    lower[(yy<133)|((yy<137)&(sleeve[:,:,3]!=255))]=0
    elbow=elbows.copy();elbow[~((upper[:,:,3]==255)&((xx<240) if side=='l' else (xx>=240)))]=0
    if not np.any(lower[:,:,3]) or not np.any(upper[:,:,3]) or not np.any(elbow[:,:,3]):raise ValueError('empty elbow split')
    recomposed=Image.fromarray(elbow);recomposed.alpha_composite(Image.fromarray(upper));recomposed.alpha_composite(Image.fromarray(lower))
    if not np.array_equal(np.array(recomposed),sleeve):raise ValueError('elbow neutral source partition changed')
    for name,img in ((f'arm_{side}',upper),(f'forearm_{side}',lower),(f'elbow_under_{side}',elbow)):
     Image.fromarray(img).save(out/f'sprites/{name}.png')
    rig['groups']['elbow_'+side]={'pivot':[405 if side=='l' else 624,595],'parent':'shoulder_'+side}
    wrist_group=rig['groups'].pop('wrist_'+side)
    wrist_group['parent']='elbow_'+side
    rig['groups']['wrist_'+side]=wrist_group
    # Same layer for both sleeve pieces, no overlap at rest. Wrist artwork stays below them.
    rig['parts'] += [
     {'id':'shoulder_under_'+side,'file':f'sprites/shoulder_under_{side}.png','group':'shoulder_'+side,'pos':[280,458],'anchor':[0,0],'layer':9},
     {'id':'elbow_under_'+side,'file':f'sprites/elbow_under_{side}.png','group':'elbow_'+side,'pos':[280,458],'anchor':[0,0],'layer':11},
     {'id':'forearm_'+side,'file':f'sprites/forearm_{side}.png','group':'elbow_'+side,'pos':[280,458],'anchor':[0,0],'layer':12}]
    rig['params'].append(parameter('ParamElbow'+side.upper(),('左' if side=='l' else '右')+'肘',-1,1,0,
                         [bind('elbow_'+side,'rot_deg',4 if side=='l' else -4)]))
    summary[side]={'hand_cleanup_pixels':int(changed.sum()),'wrist_art_pixels':int(np.count_nonzero(wrist_art[:,:,3])),
                   'shoulder_art_pixels':int(np.count_nonzero(shoulder[:,:,3])),
                   'elbow_art_pixels':int(np.count_nonzero(elbow[:,:,3])),'neutral_sleeve_partition_equal':True}
   rig['actions'].append({'id':'elbow_test','title':'肘腕联动（试验）','priority':2,'loop':True,'channels':[
    {'target':'ParamElbowL','param':'value','wave':'sine','amp':.8,'freq':.3},
    {'target':'ParamElbowR','param':'value','wave':'sine','amp':.8,'freq':.3,'phase':.5},
    {'target':'ParamWristL','param':'value','wave':'sine','amp':.5,'freq':.3,'phase':.1},
    {'target':'ParamWristR','param':'value','wave':'sine','amp':.5,'freq':.3,'phase':.6}]})
   (out/'rig.json').write_text(json.dumps(rig,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
   report={'prior_wrist_svg_sha256':EXPECTED_WRIST,'source':original['source_sha256'],
           'art_sha256':{n:torso.sha(ART/n) for n in ('wrist_cleanup.svg','wrist_contours.svg','elbow_underpaint.svg','shoulder_underpaint.svg')},
           'parts':summary,'elbow_cut_y':137,'opaque_overlap_px':4,'elbow_pivots':{'l':[405,595],'r':[624,595]},
           'elbow_rotation_degrees':4,'neutral_source_equal_to_prior':False,'visual_acceptance':'not evaluated'}
   (out/'joint_report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
   # Preserve wrist report for optional controls but replace stale art metadata.
   old=json.loads((base/'wrist_report.json').read_text());old['superseded_by_joint_report']=True
   (out/'wrist_report.json').write_text(json.dumps(old,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
   return report
  except BaseException:shutil.rmtree(out);raise

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('output',type=Path);a=p.parse_args()
 try:print(json.dumps(build(a.output),ensure_ascii=False,indent=2))
 except (ValueError,OSError,KeyError,StopIteration) as e:print('joint trial:',e,file=sys.stderr);return 1
 return 0
if __name__=='__main__':sys.exit(main())
