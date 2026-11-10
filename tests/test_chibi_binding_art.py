#!/usr/bin/env python3
"""Structural and C-engine checks for isolated drawing trials, not art approval."""
import json
from pathlib import Path
import sys
import tempfile
import numpy as np
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'))
import build_chibi_binding_art as binding
import build_chibi_lid_art as lid
import build_chibi_underlay as torso
import capture_chibi_binding_art as capture
import zrig_project
from capture_chibi_joint_art import image
from study_underpaint_sampling import start,stop,request

def main():
    (ROOT/'build').mkdir(exist_ok=True)
    before={p:torso.sha(ROOT/p) for p in torso.EXPECTED}
    with tempfile.TemporaryDirectory(prefix='binding-test-',dir=ROOT/'build') as tmp:
        tmp=Path(tmp)
        for builder,model in ((binding.build,tmp/'binding'),(lid.build,tmp/'lid')):
            builder(model)
            for bad in (model,ROOT/'experiments'/'not-allowed'):
                try:builder(bad)
                except ValueError:pass
                else:raise AssertionError('unsafe output accepted')
            link=tmp/'escape'
            if not link.exists():link.symlink_to(ROOT/'experiments',target_is_directory=True)
            try:builder(link/'not-allowed')
            except ValueError:pass
            else:raise AssertionError('symlink escape')
            metrics=capture.capture(model,tmp/(model.name+'-qa'))
            if model.name=='binding':
                rig=json.loads((model/'rig.json').read_text()); ids=[f'finger_{s}_{n}' for s in 'lr' for n in binding.FINGERS]
                assert all(any(p['id']==i for p in rig['parts']) for i in ids)
                assert all(rig['groups'][i]['parent']=='wrist_'+i[7] for i in ids)
                assert len([x for x in rig['deformers'] if x['id'].startswith('mesh_mouth_')])==5
                assert all(metrics['ParamFinger'+s+n]>0 for s in 'LR' for n in capture.FINGERS)
                assert metrics['mouth_full_changed'] and metrics['finger_loop_changed'] and metrics['joint_combined_changed']
            else:
                rig=json.loads((model/'rig.json').read_text())
                assert metrics['half_blink_changed']>0 and metrics['closed_blink_changed']>0
                for s in 'lr':
                    mask=next(p for p in rig['parts'] if p['id']=='aperture_'+s)
                    assert mask['anchor']==[0,105/114] and 'eye_aperture' in mask['tags']
            archive=tmp/(model.name+'.zproj');zrig_project.create(model/'rig.json',archive);zrig_project.verify(archive)
            unpack=tmp/(model.name+'-unpacked');zrig_project.unpack(archive,unpack);frames=[]
            for i,source in enumerate((model,unpack)):
                proc,url=start(tmp/(model.name+'-run-'+str(i)),source)
                try:
                    capture.setup(url)
                    if model.name=='binding':
                        request(url,'/api/param?id=ParamFingerLIndex&v=1');request(url,'/api/param?id=ParamMouthOpenY&v=0.5')
                    else:request(url,'/api/blink?v=0.5')
                    request(url,'/api/step?n=15');frames.append(image(url))
                finally:stop(proc)
            assert np.array_equal(*frames),model.name+' roundtrip differs'
    assert before=={p:torso.sha(ROOT/p) for p in torso.EXPECTED}
    print('Chibi 绑定试验：安全构建、C 参数与循环、半眨眼、项目包帧往返通过；非美术验收')
if __name__=='__main__':main()
