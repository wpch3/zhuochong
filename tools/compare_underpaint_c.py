#!/usr/bin/env python3
"""Compare isolated dynamic and underpaint previews using actual C frames.

The previews' states are changed and returned to idle; never target production.
Pillow/numpy required. Frame equality and pixel counts do not prove art quality.
"""
import argparse
from io import BytesIO
import json
from pathlib import Path
import urllib.request
import numpy as np
from PIL import Image


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--baseline-port',type=int,default=5209)
    p.add_argument('--candidate-port',type=int,default=5212)
    p.add_argument('--out',type=Path,default=Path('build/underpaint-comparison'))
    args=p.parse_args()
    if args.baseline_port==args.candidate_port: raise SystemExit('Previews must be different')
    bases=[f'http://127.0.0.1:{port}' for port in (args.baseline_port,args.candidate_port)]
    def get(base,path):
        with urllib.request.urlopen(base+path,timeout=20) as r:return r.read()
    for base,name in zip(bases,('小寻 · 无兽动态绑定试装','小寻 · 遮挡补画候选')):
        info=json.loads(get(base,'/api/info.json'))
        if info.get('form')!='human_dynamic_study' or info.get('form_name')!=name:
            raise SystemExit('Refusing to change a non-matching preview: '+base)
    args.out.mkdir(parents=True,exist_ok=True)
    metrics={}
    try:
        for base in bases:
            for path in ('/api/pause?on=1','/api/action?id=neutral','/api/param?all=1','/api/blink?v=0','/api/step?n=900'):
                get(base,path)
        for pose,value in (('neutral',0),('outward',1),('inward',-1)):
            imgs=[]
            for base,version in zip(bases,('baseline','candidate')):
                for path in (f'/api/param?id=ParamArmL&v={value}',f'/api/param?id=ParamArmR&v={value}','/api/step?n=1'):
                    get(base,path)
                im=Image.open(BytesIO(get(base,'/api/frame.png?s=100'))).convert('RGBA');imgs.append(np.asarray(im))
                im.save(args.out/f'{pose}_{version}.png')
                for background,color in (('light',(247,247,247,255)),('dark',(38,43,49,255))):
                    bg=Image.new('RGBA',im.size,color);bg.alpha_composite(im)
                    bg.crop((160,240,410,400)).resize((1250,800)).convert('RGB').save(args.out/f'{pose}_{version}_{background}_detail.png')
            if imgs[0].shape!=imgs[1].shape:raise ValueError('frame dimensions differ')
            metrics[pose+'_changed_pixels']=int(np.any(imgs[0]!=imgs[1],axis=2).sum())
        (args.out/'metrics.json').write_text(json.dumps(metrics,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        print(json.dumps(metrics,ensure_ascii=False))
    finally:
        for base in bases:
            try:
                for path in ('/api/param?all=1','/api/action?id=idle','/api/blink?v=auto','/api/pause?on=0'):get(base,path)
            except OSError:pass


if __name__=='__main__': main()
