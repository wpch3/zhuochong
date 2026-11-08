#!/usr/bin/env python3
"""Fail-closed patch application, source protection, and pixel invariants."""
import hashlib
import json
import subprocess
from pathlib import Path
import sys
import tempfile
import unittest
import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
import build_underpaint_trial as tool


def manifest(p):
    return {x.relative_to(p).as_posix():hashlib.sha256(x.read_bytes()).hexdigest()
            for x in p.rglob('*') if x.is_file()}


class UnderpaintTest(unittest.TestCase):
    def setUp(self):
        (ROOT/'build').mkdir(exist_ok=True)
        self.temp=tempfile.TemporaryDirectory(prefix='underpaint-test-',dir=ROOT/'build')
        self.tmp=Path(self.temp.name)
        self.source_before=manifest(tool.SOURCE)
        arms=[np.asarray(Image.open(tool.SOURCE/f'sprites/arm_{s}.png').convert('RGBA')) for s in ('l','r')]
        self.mask=(arms[0][...,3]==255)|(arms[1][...,3]==255)
        self.patch=np.zeros((512,480,4),dtype=np.uint8)
        self.patch[self.mask]=[240,10,80,255]
    def tearDown(self):
        self.assertEqual(manifest(tool.SOURCE),self.source_before)
        self.temp.cleanup()
    def save(self,arr,name='patch.png'):
        p=self.tmp/name;Image.fromarray(arr).save(p);return p
    def test_patch_and_non_destructive_composition(self):
        out=self.tmp/'candidate';report=tool.build(self.save(self.patch),out)
        self.assertTrue(report['neutral_rgba_equal']);self.assertGreater(report['changed_body_pixels'],1000)
        rig=json.loads((out/'rig.json').read_text());self.assertEqual(rig['id'],'xiaoxun_live2d_chibi_underpaint_trial')
        body0=Image.open(tool.SOURCE/'sprites/body.png').convert('RGBA');body1=Image.open(out/'sprites/body.png').convert('RGBA')
        difference=np.any(np.asarray(body0)!=np.asarray(body1),axis=2)
        self.assertFalse(np.any(difference & ~self.mask))
        for side in ('l','r'):
            arm=Image.open(tool.SOURCE/f'sprites/arm_{side}.png').convert('RGBA')
            body0.alpha_composite(arm);body1.alpha_composite(arm)
        self.assertTrue(np.array_equal(body0,body1))
        for path in (tool.SOURCE/'sprites').glob('*.png'):
            if path.name!='body.png':self.assertEqual(path.read_bytes(),(out/'sprites'/path.name).read_bytes())
    def test_reject_overwrite_and_forbidden_locations(self):
        patch=self.save(self.patch)
        for out in (tool.SOURCE,ROOT,ROOT/'characters/xiaoxun/forms/chibi',ROOT/'experiments/live2d_chibi_human_short'):
            with self.assertRaises(ValueError):tool.build(patch,out)
        out=self.tmp/'existing';out.mkdir();(out/'keep').write_text('untouched')
        with self.assertRaises(ValueError):tool.build(patch,out)
        self.assertEqual((out/'keep').read_text(),'untouched')
    def test_reject_outside_mask_empty_and_wrong_size(self):
        for name,arr in [('outside',np.zeros_like(self.patch)),('empty',np.zeros_like(self.patch)),
                         ('small',np.zeros((2,2,4),dtype=np.uint8))]:
            if name=='outside':arr[0,0]=[10,30,40,1]
            with self.assertRaises(ValueError):tool.build(self.save(arr,name+'.png'),self.tmp/name)
            self.assertFalse((self.tmp/name).exists())
    def test_preview_refuses_stale_study_link_before_writing(self):
        candidate=self.tmp/'candidate';tool.build(self.save(self.patch),candidate)
        preview=self.tmp/'preview';form=preview/'characters/xiaoxun/forms/human_dynamic_study'
        form.parent.mkdir(parents=True);form.symlink_to(tool.SOURCE,target_is_directory=True)
        marker=preview/'marker';marker.write_text('keep')
        result=subprocess.run([sys.executable,str(ROOT/'tools/preview_live2d_chibi.py'),'--dynamic',
            '--dynamic-study',str(candidate),'--preview-root',str(preview),'5299'],capture_output=True,text=True)
        self.assertNotEqual(result.returncode,0)
        self.assertIn('different study',result.stderr)
        self.assertEqual(marker.read_text(),'keep')
        self.assertFalse((preview/'config').exists())
        self.assertEqual(form.resolve(),tool.SOURCE.resolve())
    def test_existing_underlay_colour_is_noop(self):
        # Fully transparent patch is explicitly rejected, not silently published.
        with self.assertRaisesRegex(ValueError,'empty patch'):
            tool.build(self.save(np.zeros_like(self.patch)),self.tmp/'noop')


if __name__=='__main__': unittest.main(verbosity=2)
