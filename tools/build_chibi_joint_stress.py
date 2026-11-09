#!/usr/bin/env python3
"""Produce a deliberately unapproved large-angle stress fixture, never a release rig."""
import argparse,json,shutil,sys
from pathlib import Path
import build_chibi_extended as base

def build(output):
 out=Path(output);base.build(out)
 try:
  f=out/'rig.json';rig=json.loads(f.read_text(encoding='utf-8'))
  # This is a diagnostic exaggeration, not a verified motion range.
  scales={'Arm':12,'Elbow':20,'Wrist':15}
  for typ,angle in scales.items():
   for side in 'LR':
    p=next(p for p in rig['params'] if p['id']==f'Param{typ}{side}')
    if len(p['binds'])!=1 or p['binds'][0]['param']!='rot_deg':raise ValueError('unexpected joint binding')
    p['binds'][0]['scale']=angle if side=='L' else -angle
  f.write_text(json.dumps(rig,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
  report={'joint_degrees':scales,'purpose':'diagnostic only; known visual failures','visual_acceptance':'failed'}
  (out/'joint_stress_report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');return report
 except BaseException:shutil.rmtree(out);raise

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('output',type=Path);a=p.parse_args()
 try:print(json.dumps(build(a.output),ensure_ascii=False,indent=2))
 except (ValueError,OSError,KeyError,StopIteration) as e:print('stress fixture:',e,file=sys.stderr);return 1
 return 0
if __name__=='__main__':raise SystemExit(main())
