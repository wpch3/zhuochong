#!/usr/bin/env python3
"""Capture repeatable real C frames for hand/mouth and moving-lid trials."""
import argparse
import json
from pathlib import Path
import shutil
import tempfile
import numpy as np
from PIL import Image
from capture_chibi_joint_art import image
from study_underpaint_sampling import ROOT, start, stop, request

FINGERS=('Little','Ring','Middle','Index','Thumb')

def setup(url):
    for path in ('/api/pause?on=1','/api/action?id=neutral','/api/param?all=1',
                 '/api/blink?v=0','/api/step?n=900','/api/scale?s=1'):
        request(url,path)

def capture(model, out):
    model=Path(model).resolve();out=Path(out);target=out.resolve();root=(ROOT/'build').resolve()
    if root not in model.parents or root not in target.parents or model == target or model in target.parents or target in model.parents:
        raise ValueError('model and output must be separate paths inside build')
    if out.exists() or out.is_symlink() or not out.parent.is_dir():raise ValueError('output must be new')
    is_binding=(model/'binding_report.json').is_file();is_lid=(model/'lid_report.json').is_file()
    if not (is_binding or is_lid):raise ValueError('expected a binding or lid trial')
    result={};metrics={}
    with tempfile.TemporaryDirectory(prefix='binding-capture-',dir=root) as tmp:
        proc,url=start(Path(tmp)/'preview',model)
        try:
            setup(url);base=image(url)
            if is_binding:
                for side in 'LR':
                    for name in FINGERS:
                        ident='ParamFinger'+side+name
                        request(url,f'/api/param?id={ident}&v=1');request(url,'/api/step?n=2')
                        frame=image(url);metrics[ident]=int(np.any(frame!=base,axis=2).sum())
                        result[ident]=frame
                        request(url,f'/api/param?id={ident}&v=0');request(url,'/api/step?n=2')
                for path in ('/api/param?id=ParamArmL&v=1','/api/param?id=ParamElbowL&v=-1',
                             '/api/param?id=ParamWristL&v=1','/api/param?id=ParamFingerLIndex&v=1',
                             '/api/param?id=ParamArmR&v=-1','/api/param?id=ParamElbowR&v=1',
                             '/api/param?id=ParamWristR&v=-1','/api/param?id=ParamFingerRThumb&v=-1',
                             '/api/step?n=2'):
                    request(url,path)
                result['joint_combined']=image(url)
                metrics['joint_combined_changed']=int(np.any(result['joint_combined']!=base,axis=2).sum())
                request(url,'/api/param?all=1');request(url,'/api/step?n=2')
                for value in (0,.05,.1,.2,.25,.5,.75,1):
                    request(url,f'/api/param?id=ParamMouthOpenY&v={value}');request(url,'/api/step?n=2')
                    result[f'mouth_{value}']=image(url)
                metrics['mouth_full_changed']=int(np.any(result['mouth_1']!=result['mouth_0'],axis=2).sum())
                request(url,'/api/param?all=1');request(url,'/api/action?id=finger_test');request(url,'/api/step?n=30')
                first=image(url);request(url,'/api/step?n=60');second=image(url)
                metrics['finger_loop_changed']=int(np.any(first!=second,axis=2).sum())
                result['finger_loop']=second
            else:
                for value in (0,.25,.5,.75,.92,1):
                    request(url,f'/api/blink?v={value}');request(url,'/api/step?n=15')
                    result[f'blink_{value}']=image(url)
                metrics['half_blink_changed']=int(np.any(result['blink_0.5']!=result['blink_0'],axis=2).sum())
                metrics['closed_blink_changed']=int(np.any(result['blink_1']!=result['blink_0'],axis=2).sum())
        finally:stop(proc)
    out.mkdir()
    try:
        for name,frame in result.items():
            im=Image.fromarray(frame);bg=Image.new('RGBA',im.size,(247,247,247,255));bg.alpha_composite(im)
            crop=(465,395,555,450) if name.startswith('mouth_') else (380,325,635,410) if name.startswith('blink_') else (280,595,745,770)
            bg.crop(crop).resize(((crop[2]-crop[0])*3,(crop[3]-crop[1])*3)).convert('RGB').save(out/f'{name}.png')
        (out/'metrics.json').write_text(json.dumps(metrics,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        return metrics
    except BaseException:shutil.rmtree(out);raise

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('model');p.add_argument('output');a=p.parse_args()
    try:print(json.dumps(capture(a.model,a.output),ensure_ascii=False,indent=2))
    except (ValueError,OSError,RuntimeError) as e:print('capture:',e);return 1
    return 0
if __name__=='__main__':raise SystemExit(main())
