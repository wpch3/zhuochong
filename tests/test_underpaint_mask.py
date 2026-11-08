#!/usr/bin/env python3
"""JS editor and Python builder must use identical per-arm erosion."""
import base64
import json
from pathlib import Path
import subprocess
import sys
import unittest
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from underpaint_mask import safe_mask


class MaskTest(unittest.TestCase):
    def test_per_arm_before_union_and_border(self):
        a=np.zeros((9,11),dtype=np.uint8);b=a.copy()
        a[:, :6]=255;b[:,6:]=255
        zero=safe_mask([a,b],0);one=safe_mask([a,b],1)
        self.assertTrue(zero.all());self.assertFalse(one[4,5]);self.assertFalse(one[4,6])
        self.assertTrue(one[4,3]);self.assertFalse(one[0,3]);self.assertFalse(one[8,3])
    def test_javascript_python_parity(self):
        h,w=23,29; rng=np.random.default_rng(231)
        a=np.zeros((h,w),np.uint8);b=a.copy();a[1:22,2:17]=255;b[2:22,15:28]=255
        a[10,9]=254;b[7,19]=0
        a[rng.integers(0,h,20),rng.integers(0,w,20)]=255
        payload={'w':w,'h':h,'alpha':[base64.b64encode(x.tobytes()).decode() for x in (a,b)]}
        script="""const m=require('./tools/underpaint_editor/mask.js');let d='';process.stdin.on('data',c=>d+=c);process.stdin.on('end',()=>{const x=JSON.parse(d),a=x.alpha.map(s=>Uint8Array.from(Buffer.from(s,'base64')));console.log(JSON.stringify(Array.from({length:9},(_,r)=>Buffer.from(m.safeMask(a,x.w,x.h,r)).toString('base64'))));});"""
        result=subprocess.run(['node','-e',script],cwd=ROOT,input=json.dumps(payload),text=True,capture_output=True,check=True)
        for margin,encoded in enumerate(json.loads(result.stdout)):
            actual=np.frombuffer(base64.b64decode(encoded),np.uint8).reshape(h,w).astype(bool)
            self.assertTrue(np.array_equal(actual,safe_mask([a,b],margin)),f'margin {margin}')
    def test_invalid(self):
        a=np.full((3,3),255,np.uint8)
        for margin in (-1,9,1.5,True):
            with self.assertRaises(ValueError):safe_mask([a],margin)
        with self.assertRaises(ValueError):safe_mask([],0)
        with self.assertRaises(ValueError):safe_mask([a,np.ones((2,2))],0)


if __name__=='__main__':unittest.main(verbosity=2)
