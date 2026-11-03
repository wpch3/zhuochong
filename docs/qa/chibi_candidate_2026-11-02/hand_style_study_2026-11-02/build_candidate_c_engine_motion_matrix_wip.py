#!/usr/bin/env python3
"""Run the isolated 86-case matrix through the project's real C zrig renderer."""
from __future__ import annotations
import hashlib,json,subprocess,tempfile
from pathlib import Path
from PIL import Image,ImageDraw,ImageFont
STUDY=Path(__file__).resolve().parent; OUT=STUDY/'chibi_arm_rig_candidate_2026-11-03_wip'; REPO=STUDY.parents[3]; SRC=REPO/'src'; FONT=ImageFont.load_default(); EXE=Path(tempfile.gettempdir())/'chibi_candidate_renderer'
def checker(size,tile=12):
 w,h=size;im=Image.new('RGB',size,(239,238,243));d=ImageDraw.Draw(im)
 for y in range(0,h,tile):
  for x in range(0,w,tile):
   if (x//tile+y//tile)%2==0:d.rectangle((x,y,x+tile-1,y+tile-1),fill=(216,215,223))
 return im
def panel(im,label,size,scale):
 v=im.convert('RGBA').resize((round(im.width*scale),round(im.height*scale)),Image.Resampling.LANCZOS);bg=checker(v.size);bg.paste(v,(0,0),v.getchannel('A'));p=Image.new('RGB',size,(248,247,249));x=(size[0]-v.width)//2;y=23+(size[1]-23-v.height)//2;p.paste(bg,(x,y));ImageDraw.Draw(p).text((5,5),label,fill=(30,30,38),font=FONT);return p
def board(path,title,subtitle,panels,cols,pw,ph):
 gap,head=9,48;rows=(len(panels)+cols-1)//cols;o=Image.new('RGB',(gap+cols*(pw+gap),head+gap+rows*(ph+gap)),(248,247,249));d=ImageDraw.Draw(o);d.text((gap,5),title,fill=(30,30,38),font=FONT);d.text((gap,23),subtitle,fill=(76,74,82),font=FONT)
 for i,p in enumerate(panels):o.paste(p,(gap+(i%cols)*(pw+gap),head+gap+(i//cols)*(ph+gap)))
 o.save(path)
def render(rig,out,style,wrist=0,shoulder=0,elbow=0,action='none',tick=.02,ambient=True):
 r=subprocess.run([str(EXE),str(rig),str(OUT),str(out),style,str(wrist),str(shoulder),str(elbow),action,str(tick),'1' if ambient else '0','1'],cwd=REPO,text=True,capture_output=True)
 if r.returncode:raise RuntimeError(r.stdout+'\n'+r.stderr)
 log=r.stdout.strip();want=f"styles=({1 if style=='small' else 0},{1 if style=='mitten' else 0})"
 if want not in log:raise RuntimeError('pose not one-hot: '+log)
 if action!='none' and f'active_action={action}' not in log:raise RuntimeError('action not active: '+log)
 if action=='none' and 'active_action=idle' not in log:raise RuntimeError('default idle missing: '+log)
 if 'core_hidden=1' not in log:raise RuntimeError('separated accessories not hidden: '+log)
 im=Image.open(out).convert('RGBA')
 if im.size!=(848,1360) or im.getchannel('A').getbbox() is None:raise RuntimeError('invalid frame '+str(im.size))
 return im.copy(),{'style':style,'wrist_deg':wrist,'shoulder_deg':shoulder,'elbow_deg':elbow,'requested_action':action,'sample_tick_sec':tick,'ambient_enabled':ambient,'log':log,'alpha_bbox':list(im.getchannel('A').getbbox()),'sha256':hashlib.sha256(out.read_bytes()).hexdigest()}
def main():
 rig=OUT/'rig_candidate_wip.json';assert rig.exists()
 subprocess.run(['cc','-std=c11','-O2','-pthread',f'-I{SRC/"core"}',str(STUDY/'render_candidate_c_engine_preview_wip.c'),*map(str,sorted((SRC/'core').glob('*.c'))),'-lm','-pthread','-ldl','-o',str(EXE)],cwd=REPO,check=True)
 records=[]
 with tempfile.TemporaryDirectory(prefix='chibi_c_matrix_') as td:
  tmp=Path(td);controls=[]
  for style in ('small','mitten'):
   im,r=render(rig,tmp/f'control_{style}.png',style);r['case']='default_idle_'+style;records.append(r);controls.append((style,im))
  angles=list(range(-70,71,5));extreme={};sweeps={'small':[],'mitten':[]}
  for style in ('small','mitten'):
   for a in angles:
    im,r=render(rig,tmp/f'wrist_{style}_{a:+03d}.png',style,wrist=a);r['case']=f'wrist_{style}_{a:+03d}';r['requested_wrist_param']=a/22.;actual=float(r['log'].split('wrist=(')[1].split(',')[0]);r['clamp_check']=abs(actual-a/22.)<1e-6
    if not r['clamp_check']:raise RuntimeError('wrist clamp '+r['log'])
    records.append(r);sweeps[style].append(panel(im,f'{style} · wrist {a:+d}°',(170,286),.195))
    if abs(a)==70:extreme[(style,a)]=im
   board(OUT/f'candidate_c_engine_{style}_wrist_sweep_review_board_wip.png',f'C ENGINE · {style.upper()} WRIST SWEEP · ISOLATED QA WIP','29 samples from -70° to +70° by 5°; ±70° are stress points, not approved safe limits.',sweeps[style],5,170,286)
  joints=[]
  for style in ('small','mitten'):
   for sh in (0,30,60):
    for el in (0,45,90):
     im,r=render(rig,tmp/f'joint_{style}_{sh}_{el}.png',style,shoulder=sh,elbow=el);r['case']=f'joint_{style}_s{sh}_e{el}';r['requested_shoulder_param']=sh/18.;r['requested_elbow_param']=el/18.;records.append(r);joints.append(panel(im,f'{style} · shoulder {sh}° / elbow {el}°',(184,292),.205))
  board(OUT/'candidate_c_engine_shoulder_elbow_matrix_review_board_wip.png','C ENGINE · SHOULDER / ELBOW MATRIX · ISOLATED QA WIP','18 samples · 0/30/60° shoulder × 0/45/90° elbow per style; coarse visibility check only.',joints,6,184,292)
  specs=[('wave_both',t,'small' if i%2==0 else 'mitten') for i,t in enumerate((.20,.42,.68,.96))]+[('heart_hands',t,'mitten' if i%2==0 else 'small') for i,t in enumerate((.20,.46,.76,1.10))];actions=[]
  for i,(act,t,style) in enumerate(specs):
   im,r=render(rig,tmp/f'action_{i:02d}.png',style,action=act,tick=t);r['case']=f'action_{act}_{i}';records.append(r);actions.append(panel(im,f'{act} · t={t:.2f}s · {style}',(190,310),.205))
  board(OUT/'candidate_c_engine_action_pose_review_board_wip.png','C ENGINE · ACTION / HAND-STYLE ORTHOGONALITY · ISOLATED QA WIP','8 runtime samples from wave_both and heart_hands; sample visibility only, not full gesture acceptance.',actions,4,190,310)
  board(OUT/'candidate_c_engine_default_idle_controls_review_board_wip.png','C ENGINE · DEFAULT-IDLE CONTROLS · ISOLATED QA WIP','No action request; idle remains active at tick 0.02s, ordinary ambient enabled.',[panel(im,f'default idle · {style}',(350,560),.39) for style,im in controls],2,350,560)
  details=[]
  for style in ('small','mitten'):
   for side,box in (('left',(183,914,272,1006)),('right',(575,914,664,1006))):
    for a in (-70,70):
     crop=extreme[(style,a)].crop(box).resize((356,368),Image.Resampling.NEAREST);p=Image.new('RGB',(210,270),(248,247,249));bg=checker(crop.size);bg.paste(crop,(0,0),crop.getchannel('A'));p.paste(bg,((210-crop.width)//2,28+(235-crop.height)//2));ImageDraw.Draw(p).text((5,5),f'{style} · {side} · {a:+d}° · zoom',fill=(30,30,38),font=FONT);details.append(p)
  board(OUT/'candidate_c_engine_wrist_extremes_4x_detail_review_board_wip.png','C ENGINE · EXTREME WRIST / CUFF DETAILS · ISOLATED QA WIP','Selected ±70° stress frames enlarged with nearest-neighbour; assess samples only, not safety.',details,4,210,270)
 breakdown={'default_idle_controls':2,'wrist_sweep':58,'shoulder_elbow':18,'action_pose':8};assert len(records)==sum(breakdown.values())==86
 report={'title':'Isolated Chibi arm rig C-engine matrix (WIP)','date':'2026-11-03','candidate_rig_sha256':hashlib.sha256(rig.read_bytes()).hexdigest(),'case_count':86,'case_breakdown':breakdown,'wrist_angles_deg':angles,'actions':['wave_both','heart_hands'],'assertions':['C load/render success','848x1360 non-empty-alpha frames','hand_style one-hot','wrist values unclamped','requested action active','action geometry channels zero'],'limitations':['all 6 separated ear/tail accessory parts hidden for the body-only QA matrix','trial24 AI mitten pixels unapproved','small style uses exact visible source pixels but hidden wrist absent','default outfit/hair only','±70° stress samples not safety range','gesture hand artwork absent','not production acceptance'],'review_boards':['candidate_c_engine_default_idle_controls_review_board_wip.png','candidate_c_engine_small_wrist_sweep_review_board_wip.png','candidate_c_engine_mitten_wrist_sweep_review_board_wip.png','candidate_c_engine_shoulder_elbow_matrix_review_board_wip.png','candidate_c_engine_action_pose_review_board_wip.png','candidate_c_engine_wrist_extremes_4x_detail_review_board_wip.png'],'records':records}
 (OUT/'candidate_c_engine_motion_matrix_results_wip.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');print('Rendered isolated C-engine matrix: 86 frames (2 controls, 58 wrist, 18 joint, 8 action); boards and metrics written.')
if __name__=='__main__':main()
