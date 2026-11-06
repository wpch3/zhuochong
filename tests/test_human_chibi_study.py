#!/usr/bin/env python3
"""Structural/isolation test for the no-animal-feature Chibi variant."""
from pathlib import Path
import hashlib
import json
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from build_human_chibi_study import build
SOURCE = ROOT / 'experiments/live2d_chibi_short'
TARGET = ROOT / 'experiments/live2d_chibi_human_short'


def manifest(path):
    return {p.relative_to(path).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in path.rglob('*') if p.is_file()}


def main():
    before = manifest(SOURCE)
    with tempfile.TemporaryDirectory(prefix='human-chibi-test-') as tmp:
        target = Path(tmp)
        build(target)
        assert before == manifest(SOURCE), 'building the human variant changed the animal-feature study'
        rig = json.loads((target / 'rig.json').read_text(encoding='utf-8'))
        assert rig == json.loads((TARGET / 'rig.json').read_text(encoding='utf-8')), 'saved rig is out of date'
        assert rig['id'] == 'xiaoxun_live2d_chibi_human_study'
        assert not {'ear_l', 'ear_r', 'tail'} & {p['id'] for p in rig['parts']}
        assert not {'ear_l', 'ear_r', 'tail'} & set(rig['groups'])
        for action in rig['actions']:
            assert action['id'] not in ('ear_test', 'tail_test')
            assert not any(c['target'] in ('ear_l', 'ear_r', 'tail') for c in action['channels'])
        for part in rig['parts']:
            assert (target / part['file']).read_bytes() == (SOURCE / part['file']).read_bytes()
            assert (target / part['file']).read_bytes() == (TARGET / part['file']).read_bytes()
    print('无兽特征版：移除耳尾部件及动作；来源试作未修改；各保留切件一致')


if __name__ == '__main__':
    main()
