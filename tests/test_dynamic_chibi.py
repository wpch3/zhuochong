#!/usr/bin/env python3
"""Rebuild and check the isolated dynamic study without touching its source."""
import hashlib
import json
import shutil
import sys
import tempfile
from pathlib import Path
import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import build_dynamic_chibi as m


def manifest(path):
    return {p.relative_to(path).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in path.rglob('*') if p.is_file()}


def main():
    before = manifest(m.SOURCE)
    for forbidden in (m.SOURCE, m.SOURCE.parent, ROOT, ROOT / 'characters/xiaoxun/forms/chibi',
                      ROOT / 'experiments/live2d_chibi_human_short'):
        try:
            m.build(forbidden)
            raise AssertionError(f'unsafe output accepted: {forbidden}')
        except ValueError:
            pass
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / 'study'
        m.build(out)
        # The generated artifacts must be reproducible; QA/README are separate.
        for rel, digest in manifest(out).items():
            assert manifest(m.OUT)[rel] == digest, rel
        source = Image.open(m.SOURCE / 'sprites/body.png').convert('RGBA')
        composed = Image.open(out / 'sprites/body.png').convert('RGBA')
        for side in ('l', 'r'):
            composed.alpha_composite(Image.open(out / f'sprites/arm_{side}.png').convert('RGBA'))
        assert np.array_equal(np.asarray(source), np.asarray(composed)), 'default art composite changed'
        rig = json.loads((out / 'rig.json').read_text(encoding='utf-8'))
        ids = {p['id'] for p in rig['parts']}
        assert {'arm_l', 'arm_r', 'body', 'head'} <= ids
        assert {p['id'] for p in rig['params']} >= {'ParamArmL', 'ParamArmR', 'ParamBreath', 'ParamMotionDrive', 'ParamSleeveFollow'}
        assert {a['id'] for a in rig['actions']} == {'neutral', 'idle', 'sway', 'hand_wave', 'head_test', 'talk'}
        assert rig['physics2'][0]['outputs'][0]['param'] == 'ParamSleeveFollow'
        changed = Path(tmp) / 'changed-source'
        shutil.copytree(m.SOURCE, changed)
        body_path = changed / 'sprites/body.png'
        altered = Image.open(body_path).convert('RGBA')
        altered.putpixel((200,200), (1,2,3,255)); altered.save(body_path)
        original = m.SOURCE
        m.SOURCE = changed
        try:
            try:
                m.build(Path(tmp) / 'reject')
                raise AssertionError('changed partition source accepted')
            except ValueError as error:
                assert 'source body changed' in str(error)
        finally:
            m.SOURCE = original
    assert before == manifest(m.SOURCE), 'source changed'
    print('动态试装：可复现、原素材未改，默认拆层 RGBA 合成与源逐像素一致')


if __name__ == '__main__':
    main()
