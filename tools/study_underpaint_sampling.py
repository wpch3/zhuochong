#!/usr/bin/env python3
"""Measure neutral/arm-extreme C-frame differences at multiple safety margins.

Uses an existing transparent patch and isolated temporary previews, never a
running user preview. Dependencies: Pillow/numpy and build/zhuochong_preview.
Results are limited to the tested scales/poses, not a visual quality verdict.
"""
import argparse
import hashlib
from io import BytesIO
import json
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request

import numpy as np
from PIL import Image
from build_underpaint_trial import SOURCE, build
from underpaint_mask import safe_mask

ROOT=Path(__file__).resolve().parents[1]


def port():
    with socket.socket() as s:s.bind(('127.0.0.1',0));return s.getsockname()[1]


def request(base,path):
    with urllib.request.urlopen(base+path,timeout=30) as response:return response.read()


def start(root,study=None):
    n=port();cmd=[sys.executable,str(ROOT/'tools/preview_live2d_chibi.py'),'--dynamic',
                  '--preview-root',str(root),str(n)]
    if study:cmd.extend(['--dynamic-study',str(study)])
    proc=subprocess.Popen(cmd,cwd=ROOT,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
    base=f'http://127.0.0.1:{n}'
    for _ in range(100):
        if proc.poll() is not None:raise RuntimeError(proc.stderr.read().decode(errors='replace'))
        try:
            request(base,'/api/info.json');return proc,base
        except OSError:time.sleep(.1)
    proc.terminate();proc.wait();raise RuntimeError('preview did not start')


def stop(proc):
    proc.terminate()
    try:proc.wait(timeout=5)
    except subprocess.TimeoutExpired:proc.kill();proc.wait()
    proc.stderr.close()


def frames(base,scales):
    for path in ('/api/pause?on=1','/api/action?id=neutral','/api/param?all=1','/api/blink?v=0','/api/step?n=900'):
        request(base,path)
    result={}
    for scale in scales:
        request(base,f'/api/scale?s={scale}')
        info=json.loads(request(base,'/api/info.json'))
        if abs(info.get('scale',0)-scale)>1e-4:
            raise RuntimeError('engine did not apply requested scale')
        for pose,val in (('neutral',0),('outward',1),('inward',-1)):
            for path in (f'/api/param?id=ParamArmL&v={val}',f'/api/param?id=ParamArmR&v={val}',
                         '/api/blink?v=0','/api/step?n=1'):
                request(base,path)
            im=Image.open(BytesIO(request(base,'/api/frame.png?s=100'))).convert('RGBA')
            result[(scale,pose)]=np.array(im)
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--patch',type=Path,default=ROOT/'tools/underpaint_editor/qa/example_patch_not_approved.png')
    p.add_argument('--stress-red',action='store_true',help='use a high-contrast patch covering the full opaque sleeve mask')
    p.add_argument('--out',type=Path,default=ROOT/'build/underpaint-sampling')
    args=p.parse_args()
    margins=(0,1,2,3,4,6,8);scales=(.35,.55,.8,1.0)
    alphas=[np.asarray(Image.open(SOURCE/f'sprites/arm_{s}.png').convert('RGBA'))[...,3] for s in ('l','r')]
    if args.stress_red:
        patch=np.zeros((512,480,4),np.uint8);patch[safe_mask(alphas,0)]=[255,0,0,255]
    else:
        patch=np.asarray(Image.open(args.patch).convert('RGBA')).copy()
    if patch.shape!=(512,480,4):raise ValueError('patch must be 480×512')
    if (ROOT/'build').resolve() not in args.out.resolve().parents:
        raise ValueError('output must be in an isolated build subdirectory')
    args.out.mkdir(parents=True,exist_ok=True)
    (ROOT/'build').mkdir(exist_ok=True)
    report={'source_rig_sha256':hashlib.sha256((SOURCE/'rig.json').read_bytes()).hexdigest(),
            'patch_rgba_sha256':hashlib.sha256(patch.tobytes()).hexdigest(),
            'patch_type':'full_red_stress' if args.stress_red else 'input_png',
            'scales':scales,'margins':{}}
    with tempfile.TemporaryDirectory(prefix='sampling-',dir=ROOT/'build') as temp:
        tmp=Path(temp);baseline,base=start(tmp/'baseline-preview')
        try:ref=frames(base,scales)
        finally:stop(baseline)
        for margin in margins:
            mask=safe_mask(alphas,margin);arr=patch.copy();arr[~mask]=0
            count=int(np.count_nonzero(arr[...,3]));entry={'patch_pixels':count,'scale_pose_differences':{}}
            report['margins'][str(margin)]=entry
            if not count:continue
            patchfile=tmp/f'patch-{margin}.png';Image.fromarray(arr).save(patchfile)
            candidate=tmp/f'candidate-{margin}';build(patchfile,candidate,margin)
            proc,url=start(tmp/f'preview-{margin}',candidate)
            try:observed=frames(url,scales)
            finally:stop(proc)
            for scale in scales:
                diffs={}
                for pose in ('neutral','outward','inward'):
                    a,b=ref[(scale,pose)],observed[(scale,pose)]
                    if a.shape!=b.shape:raise RuntimeError('frame shape mismatch')
                    diffs[pose]=int(np.any(a!=b,axis=2).sum())
                    if scale==.55 and margin in (0,2,4,6) and pose in ('neutral','outward'):
                        Image.fromarray(b).save(args.out/f'margin{margin}_{pose}.png')
                entry['scale_pose_differences'][str(scale)]=diffs
            print(f'margin {margin}: pixels={count}, changes={entry["scale_pose_differences"]}',flush=True)
    (args.out/'metrics.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print('Saved:',args.out/'metrics.json')


if __name__=='__main__':main()
