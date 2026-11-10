#!/usr/bin/env python3
"""Unapproved pose-controlled pocket cover for the fixed Chibi stress rig.

Preserves the original body pixels and neutral draw; independent temporary
patches cover pockets near a sampled arm extreme. Requires OpenCV. The actual
occlusion depends on all joints/body, not just the shoulder: do not promote
without checking motion, layering and original art.
"""
import argparse
import json
import shutil
import sys
from pathlib import Path
import cv2
import numpy as np
from PIL import Image
import build_chibi_layered_sleeve_study as layered


def build(output):
    out = Path(output)
    layered.build(out)
    try:
        path = out / 'rig.json'
        rig = json.loads(path.read_text(encoding='utf-8'))
        body = next(p for p in rig['parts'] if p['id'] == 'body')
        if body['pos'] != [280,458] or body['group'] != 'body' or body['layer'] != 10:
            raise ValueError('unexpected body binding')
        source = np.array(Image.open(out/body['file']).convert('RGBA'))
        if source.shape != (512,480,4):
            raise ValueError('unexpected body image')
        r,g,b = source[:,:,:3].astype(float).transpose(2,0,1)
        yy,xx = np.indices(r.shape)
        parts = {}
        for side,lo,hi in (('l',138,174),('r',285,322)):
            teal = ((g>r+15)&(b>r+8)&(r<180)&(xx>=lo)&(xx<hi)&(yy>=125)&(yy<174))
            count,labels,stats,_ = cv2.connectedComponentsWithStats(teal.astype('uint8'))
            if count < 2:
                raise ValueError(f'missing {side} pocket')
            index = 1+np.argmax(stats[1:,cv2.CC_STAT_AREA])
            x,y,w,h,area = (int(v) for v in stats[index])
            if not (240<=area<=350 and 20<=w<=30 and 34<=h<=43):
                raise ValueError(f'unexpected {side} pocket structure')
            mask = cv2.dilate((labels==index).astype('uint8'),np.ones((5,5),np.uint8))
            restored = cv2.inpaint(source[:,:,:3],mask,3,cv2.INPAINT_TELEA)
            patch = np.zeros_like(source)
            patch[:,:,:3] = restored
            patch[:,:,3] = mask*255
            ident = f'pocket_cover_{side}'
            filename = f'sprites/{ident}.png'
            Image.fromarray(patch).save(out/filename)
            rig['parts'].append({'id':ident,'file':filename,'group':'body',
                                 'pos':[280,458],'anchor':[0,0],'layer':11})
            param = next(p for p in rig['params'] if p['id'] == f'ParamArm{side.upper()}')
            param['binds'].append({'part':ident,'param':'alpha','scale':-2,'offset':-1})
            parts[side] = {'bounds':[x,y,w,h], 'pixels':int(mask.sum()),
                           'trigger':'alpha=clamp(-2*ParamArm,0,1)'}
        path.write_text(json.dumps(rig,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        report = {'visual_acceptance':'not evaluated', 'parts':parts,
                  'limitations':['covers pocket even if it is not actually occluded',
                                 'transition may look faded and pocket may vanish unnaturally',
                                 'inpaint is not original underlying artwork',
                                 'shoulder alone cannot predict all relative poses',
                                 'fixed-rig prototype, not production']}
        (out/'pocket_cover_report.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
        return report
    except BaseException:
        shutil.rmtree(out)
        raise


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('output',type=Path)
    a = p.parse_args()
    try:
        print(json.dumps(build(a.output),indent=2))
    except (ValueError,OSError,KeyError,StopIteration) as exc:
        print(f'pocket cover study: {exc}',file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
