#!/usr/bin/env python3
"""Real C sampled-frame regression for one full-mask red pressure patch.

Only tests the selected model, pose, and scales; not a universal art guarantee.
"""
from pathlib import Path
import sys
import tempfile
import numpy as np
from PIL import Image
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from build_underpaint_trial import SOURCE,build
from underpaint_mask import safe_mask
from study_underpaint_sampling import frames,start,stop


def main():
    (ROOT/'build').mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='sampling-test-',dir=ROOT/'build') as tmp:
        tmp=Path(tmp)
        alphas=[np.asarray(Image.open(SOURCE/f'sprites/arm_{s}.png').convert('RGBA'))[...,3] for s in ('l','r')]
        patch=np.zeros((512,480,4),np.uint8);patch[safe_mask(alphas,6)]=[255,0,0,255]
        path=tmp/'red.png';Image.fromarray(patch).save(path)
        candidate=tmp/'candidate';build(path,candidate,6)
        scales=(.35,.55,.8,1.0)
        p,base=start(tmp/'base-preview')
        try:a=frames(base,scales)
        finally:stop(p)
        p,base=start(tmp/'candidate-preview',candidate)
        try:b=frames(base,scales)
        finally:stop(p)
        for scale in scales:
            assert np.array_equal(a[(scale,'neutral')],b[(scale,'neutral')]), f'neutral mismatch at {scale}'
        outward=int(np.any(a[(.55,'outward')]!=b[(.55,'outward')],axis=2).sum())
        assert outward>0, 'test patch unexpectedly has no effect at outward extreme'
        print(f'补画采样：红色压力补画 6px 边距在四个指定比例中立帧一致；0.55 外摆 {outward} 像素不同')


if __name__=='__main__':main()
