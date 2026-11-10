#!/usr/bin/env python3
"""Unapproved independent pain-line drawing / matched-motion experiment.

A tapered hand-specified secondary stroke shares eyelid position and blink
mesh, and moves into the upper stroke when pain=0. Requires the isolated
morph-experiment engine; no production assets or default C changes.
"""
import argparse
import copy
from io import BytesIO
import json
import math
import shutil
import sys
from pathlib import Path
from PIL import Image
import resvg_py
import build_chibi_pupil_hold_study as base
import build_chibi_underlay as torso

ROOT = Path(__file__).resolve().parents[1]
ART = ROOT/'experiments/live2d_chibi_morph_study/pain_branch_art_study.svg'


def build(output):
    out = Path(output)
    base.build(out)
    try:
        path = out/'rig.json'
        rig = json.loads(path.read_text(encoding='utf-8'))
        art = Image.open(BytesIO(resvg_py.svg_to_bytes(svg_path=str(ART), width=215,height=114,skip_system_fonts=True))).convert('RGBA')
        for side in 'lr':
            remove = {f'lid_closed_{side}',f'lid_smile_{side}',f'lid_pain_{side}'}
            rig['parts'] = [p for p in rig['parts'] if p['id'] not in remove]
            rig['deformers'] = [d for d in rig['deformers'] if d.get('part') not in remove]
            lid = next(p for p in rig['parts'] if p['id']==f'lid_{side}')
            lid['tags'] = ['eyelid','eye_keyform_effective_blink','eye_closed_morph']
            branch = copy.deepcopy(lid)
            branch.update(id=f'lid_branch_{side}',file=f'sprites/lid_branch_{side}.png',layer=lid['layer']+1)
            x0,x1 = (0,100) if side=='l' else (110,215)
            art.crop((x0,0,x1,114)).save(out/branch['file'])
            rig['parts'].append(branch)
            original = next(d for d in rig['deformers'] if d['id']==f'mesh_lid_{side}')
            clone = copy.deepcopy(original)
            clone.update(id=f'mesh_lid_branch_{side}',part=branch['id'])
            rig['deformers'].append(clone)
            for i,part in enumerate((lid,branch)):
                smile=[]
                for row in range(5):
                    for col in range(9):
                        t=col/8 if side=='l' else 1-col/8
                        smile.append({'c':col,'r':row,'dy':round(-5*math.sin(math.pi*t),4)})
                rig['deformers'].append({'id':f'mesh_{part["id"]}_smile','part':part['id'],
                    'cols':8,'rows':4,'param':f'ParamEye{side.upper()}Smile',
                    'keys':[{'v':0,'points':[]},{'v':1,'points':smile}]})
                if i==1:
                    collapsed=[]
                    for row in range(5):
                        for col in range(9):
                            t=col/8 if side=='l' else 1-col/8
                            collapsed.append({'c':col,'r':row,'dy':round(-8*(1-t),4)})
                    rig['deformers'].append({'id':f'mesh_{part["id"]}_pain','part':part['id'],
                        'cols':8,'rows':4,'param':f'ParamEye{side.upper()}Pain',
                        'keys':[{'v':0,'points':collapsed},{'v':1,'points':[]}]})
        path.write_text(json.dumps(rig,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        report={'visual_acceptance':'not evaluated','art_sha256':torso.sha(ART),
                'requires':'build/zhuochong_eye_morph_experiment',
                'limitations':['manual line may not match actual moving lash','separate overlap can darken edges',
                               'not original source art','single-eye smile/pain combinations not exhaustive']}
        (out/'drawn_pain_branch_report.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
        return report
    except BaseException:
        shutil.rmtree(out)
        raise


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output',type=Path)
    args=parser.parse_args()
    try:
        print(json.dumps(build(args.output),indent=2))
    except (ValueError,OSError,KeyError,StopIteration) as exc:
        print(f'drawn branch study: {exc}',file=sys.stderr)
        return 1
    return 0


if __name__=='__main__':
    raise SystemExit(main())
