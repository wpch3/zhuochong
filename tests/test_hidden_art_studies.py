#!/usr/bin/env python3
"""Isolated source, asset, and real-C checks; not an artistic acceptance test."""
from io import BytesIO
import json
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request

from PIL import Image
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
import build_hidden_art_studies as studies
from underpaint_mask import safe_mask
from study_underpaint_sampling import start,stop,frames


def get(url):
    with urllib.request.urlopen(url,timeout=20) as r:return r.read()


def main():
    (ROOT/'build').mkdir(exist_ok=True)
    before={p:studies.sha(ROOT/p) for p in studies.EXPECTED}
    with tempfile.TemporaryDirectory(prefix='two-art-test-',dir=ROOT/'build') as t:
        t=Path(t);out=t/'output';summary=studies.build(out)
        try:studies.build(out);raise AssertionError('existing output overwritten')
        except ValueError:pass
        try:studies.build(ROOT/'experiments'/'not-a-valid-output');raise AssertionError('unsafe output accepted')
        except ValueError:pass
        patch=np.array(Image.open(out/'chibi_patch.png').convert('RGBA'))
        arms=[np.array(Image.open(studies.CHIBI/f'sprites/arm_{s}.png').convert('RGBA'))[:,:,3] for s in 'lr']
        assert not np.any((patch[:,:,3]>0)&~safe_mask(arms,0))
        assert summary['chibi_candidate_report']['neutral_rgba_equal']
        assert np.array_equal(patch,np.array(Image.open(studies.ART/'chibi/inner_jacket_clipped.png').convert('RGBA')))
        teen=Image.open(out/'teen_underarms@2x.png');assert teen.size==(546,1000) and teen.getbbox()
        teen1=studies.render(studies.ART/'teen/torso_underarms.svg',273,500)
        assert np.array_equal(np.array(teen1),np.array(Image.open(studies.ART/'teen/torso_underarms.png').convert('RGBA')))
        preview_cmd=[sys.executable,str(ROOT/'tools/preview_teen_hidden_art.py'),str(out/'teen'),'--preview-root',str(out)]
        assert subprocess.run(preview_cmd,capture_output=True,timeout=10).returncode!=0, 'preview reused or nested output'
        rig=json.loads((out/'teen/rig.json').read_text());part=next(p for p in rig['parts'] if p['id']=='hidden_torso_underarms')
        assert part['pos']==[282,308] and part['group']=='chest' and part['layer']==97 and part['scale']==.5
        proc,url=start(t/'chibi-preview',out/'chibi')
        try:
            im=frames(url,(.55,));assert im[(.55,'neutral')].shape[2]==4
            assert np.any(im[(.55,'outward')]!=im[(.55,'neutral')])
        finally:stop(proc)
        # Copy into the temporary form path rather than symlinking it: the rig
        # references ../../motions, which must resolve in this isolated tree.
        preview=t/'teen-preview';shutil.copytree(ROOT/'config',preview/'config')
        char=preview/'characters/xiaoxun';(char/'forms').mkdir(parents=True)
        shutil.copytree(out/'teen',char/'forms/teen')
        for src in (ROOT/'characters/xiaoxun').iterdir():
            if src.name not in ('forms','forms.json'):(char/src.name).symlink_to(src,target_is_directory=src.is_dir())
        (preview/'schemas').symlink_to(ROOT/'schemas',target_is_directory=True)
        # Same rig, identical animation/physics state: toggle only the new layer.
        ab=t/'same-state';ab.mkdir()
        rigdir=char/'forms/teen';probe=ROOT/'build/rig_part_ab'
        cmd=[str(probe),str(rigdir/'rig.json'),str(rigdir),'hidden_torso_underarms','wave','30','0.55',str(ab)]
        result=subprocess.run(cmd,capture_output=True,text=True,check=True,timeout=30)
        stats=json.loads(result.stdout);assert stats['hide_show_hide_equal'] and stats['changed_pixels']>0
        off=np.array(Image.open(ab/'off.png').convert('RGBA'));on=np.array(Image.open(ab/'on.png').convert('RGBA'))
        assert int(np.any(off!=on,axis=2).sum())==stats['changed_pixels']
        assert subprocess.run(cmd,capture_output=True,timeout=30).returncode!=0, 'probe overwrote existing output'
        symlink_out=t/'link-output';symlink_out.mkdir();(symlink_out/'off.png').symlink_to(t/'not-created.png')
        linked=cmd.copy();linked[-1]=str(symlink_out)
        assert subprocess.run(linked,capture_output=True,timeout=30).returncode!=0 and not (t/'not-created.png').exists()
        bad=cmd.copy();bad[3]='no_such_part';bad[-1]=str(t)
        assert subprocess.run(bad,capture_output=True,timeout=30).returncode!=0
        with socket.socket() as s:s.bind(('127.0.0.1',0));port=s.getsockname()[1]
        proc=subprocess.Popen([str(ROOT/'build/zhuochong_preview'),'--root',str(preview),'--web',str(ROOT/'web'),
                               '--port',str(port),'--bind','127.0.0.1'],stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
        url=f'http://127.0.0.1:{port}'
        try:
            for _ in range(100):
                if proc.poll() is not None:raise RuntimeError(proc.stderr.read().decode(errors='replace'))
                try:info=json.loads(get(url+'/api/info.json'));break
                except OSError:time.sleep(.1)
            else:raise RuntimeError('teen C preview did not start')
            assert info['form']=='teen' and 'wave' in info['actions'] and 'curious_tilt' in info['actions']
            for path in ('/api/pause?on=1','/api/blink?v=0','/api/action?id=wave','/api/step?n=30'):get(url+path)
            frame=Image.open(BytesIO(get(url+'/api/frame.png?s=100'))).convert('RGBA')
            assert frame.getbbox() and frame.size[0]>0
        finally:stop(proc)
    assert before=={p:studies.sha(ROOT/p) for p in studies.EXPECTED}
    print('双形态底稿：隔离输出、源指纹、Chibi 掩膜与两套真实 C 载入/动作通过（不代表视觉验收）')
if __name__=='__main__':main()
