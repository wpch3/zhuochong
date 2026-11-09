#!/usr/bin/env python3
"""Bind the experimental five-finger and layered-mouth drawings to Chibi.

Output is a fresh build subdirectory; replacing the old hands and mouth open
changes the neutral artwork. This is an unapproved prototype, not production.
"""
import argparse
from io import BytesIO
import json
from pathlib import Path
import shutil
import sys
import tempfile
import xml.etree.ElementTree as ET
import numpy as np
from PIL import Image
import resvg_py
import build_chibi_joint_art as joint
import build_chibi_underlay as torso
from build_dynamic_chibi import bind,parameter

ROOT=Path(__file__).resolve().parents[1]
ART=ROOT/'experiments/live2d_chibi_binding_art'
NS='{http://www.w3.org/2000/svg}'
ET.register_namespace('',NS[1:-1]);ET.register_namespace('xlink','http://www.w3.org/1999/xlink')
FINGERS=('little','ring','middle','index','thumb')
MOUTH=('hidden_cavity','tongue','upper_lip','lower_lip','tooth_light')


def render_piece(path,element,hand=False):
 root=ET.parse(path).getroot()
 if hand:
  target=next(g for g in root.iter() if g.get('id')=='hand')
  for child in list(target):
   keep=(child.get('id')==element or (element=='palm' and child.get('id') is None))
   if not keep:target.remove(child)
 else:
  for child in list(root):
   if child.tag!=NS+'defs' and child.get('id')!=element:root.remove(child)
 svg=ET.tostring(root,encoding='unicode')
 return np.array(Image.open(BytesIO(resvg_py.svg_to_bytes(svg_string=svg,skip_system_fonts=True))).convert('RGBA'))


def build(output):
 out=Path(output);scratch=(ROOT/'build').resolve();resolved=out.resolve()
 if scratch not in resolved.parents:raise ValueError('output must be inside build')
 if out.exists() or out.is_symlink() or not out.parent.is_dir():raise ValueError('output must be a new directory with existing parent')
 finger_layers={name:render_piece(ART/'fingers.svg',name,True) for name in FINGERS+('palm',)}
 mouth_layers={name:render_piece(ART/'mouth.svg',name) for name in MOUTH}
 if any(not np.any(im[:,:,3]) for im in list(finger_layers.values())+list(mouth_layers.values())):raise ValueError('empty art layer')
 yy,xx=np.indices((512,480))
 with tempfile.TemporaryDirectory(prefix='binding-base-',dir=scratch) as t:
  base=Path(t)/'base';joint.build(base);rig=json.loads((base/'rig.json').read_text(encoding='utf-8'))
  out.mkdir()
  try:
   shutil.copytree(base/'sprites',out/'sprites')
   for name in ('wrist_report.json','joint_report.json'):shutil.copyfile(base/name,out/name)
   pivots={'little':[365,677],'ring':[364,675],'middle':[362,673],'index':[360,670],'thumb':[372,675]}
   parts=[]
   for side in 'lr':
    side_mask=(xx<240) if side=='l' else (xx>=240)
    # Each fingertip becomes a child of its side's wrist; palm stays at wrist.
    for i,name in enumerate(FINGERS):
     art=finger_layers[name].copy();art[~side_mask]=0
     path=f'sprites/finger_{side}_{name}.png';Image.fromarray(art).save(out/path)
     l=pivots[name];pivot=l if side=='l' else [1020-l[0],l[1]]
     group=f'finger_{side}_{name}';rig['groups'][group]={'pivot':pivot,'parent':'wrist_'+side}
     rig['parts'].append({'id':group,'file':path,'group':group,'pos':[280,458],'anchor':[0,0],'layer':13+i})
     label={'little':'小指','ring':'无名指','middle':'中指','index':'食指','thumb':'拇指'}[name]
     rig['params'].append(parameter('ParamFinger'+side.upper()+name.capitalize(),('左' if side=='l' else '右')+label,-1,1,0,
                                    [bind(group,'rot_deg',(5 if side=='l' else -5))]))
     parts.append(group)
    palm=finger_layers['palm'].copy();palm[~side_mask]=0
    Image.fromarray(palm).save(out/f'sprites/hand_{side}.png')
    next(x for x in rig['parts'] if x['id']=='hand_'+side)['layer']=19
   # A short blend restores the original smile at zero; matching meshes
   # compress all mouth layers to a curved line, not a full phoneme rig.
   rig['parts']=[p for p in rig['parts'] if p['id']!='mouth_speak']
   (out/'sprites/mouth_speak.png').unlink()
   rig['xfades']=[x for x in rig.get('xfades',[]) if x.get('id')!='mouth']
   deformers=rig.setdefault('deformers',[])
   closed=[{'c':c,'r':r,'dy':round(10.45-9.5*r+[0,3,4,3,0][c],2)} for r in range(5) for c in range(5)]
   mouth_param=next(p for p in rig['params'] if p['id']=='ParamMouthOpenY')
   mouth_param['binds']=[{'part':'mouth_rest','param':'alpha','scale':-5}]
   for i,name in enumerate(MOUTH):
    path=f'sprites/mouth_{name}.png';Image.fromarray(mouth_layers[name]).save(out/path)
    pid='mouth_'+name
    rig['parts'].append({'id':pid,'file':path,'group':'head','pos':[480,405],'anchor':[0,0],'layer':40+i})
    mouth_param['binds'].append({'part':pid,'param':'alpha','scale':5,'offset':-1})
    deformers.append({'id':'mesh_'+pid,'part':pid,'cols':4,'rows':4,'param':'ParamMouthOpenY',
                      'keys':[{'v':0,'points':closed},{'v':1,'points':[]}]})
   # Modest test: each side's fingers fan in sequence rather than act as a fist.
   channels=[]
   for side in 'lr':
    for i,name in enumerate(FINGERS):
     channels.append({'target':'ParamFinger'+side.upper()+name.capitalize(),'param':'value','wave':'sine',
                      'amp':.7,'freq':.32,'phase':i*.08+(0 if side=='l' else .5)})
   rig['actions'].append({'id':'finger_test','title':'手指小摆（试验）','priority':2,'loop':True,'channels':channels})
   (out/'rig.json').write_text(json.dumps(rig,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
   report={'art_sha256':{x:torso.sha(ART/x) for x in ('fingers.svg','mouth.svg')},
           'joint_art_sha256':json.loads((base/'joint_report.json').read_text())['art_sha256'],
           'finger_parts':parts,'mouth_parts':['mouth_'+n for n in MOUTH],
           'mouth_strategy':'five matching keyform meshes and a 0-0.2 closed-line transition',
           'neutral_source_equal_to_prior':False,'visual_acceptance':'not evaluated',
           'limitations':'redrawn mirrored hands, limited rotations, near-closed mouth mesh, no eye redraw in this trial'}
   (out/'binding_report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
   return report
  except BaseException:shutil.rmtree(out);raise

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('output',type=Path);a=p.parse_args()
 try:print(json.dumps(build(a.output),ensure_ascii=False,indent=2))
 except (ValueError,OSError,KeyError,StopIteration,ET.ParseError) as e:print('binding trial:',e,file=sys.stderr);return 1
 return 0
if __name__=='__main__':sys.exit(main())
