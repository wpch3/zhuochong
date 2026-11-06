#!/usr/bin/env python3
"""Create an isolated human-appearance variant from the existing Chibi study.

The source study contains ear-free hair and tail-free body underpainting, with
cat ears and tail on separate parts. This script retains only non-animal parts;
it does not modify the original study or any production form. Run
build_live2d_chibi_study.py first to rebuild the source study when necessary.
"""
from pathlib import Path
import copy
import json
import shutil

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'experiments/live2d_chibi_short'
OUT = ROOT / 'experiments/live2d_chibi_human_short'


def build(out=OUT):
    out = Path(out)
    if out.resolve() == SOURCE.resolve():
        raise ValueError('Refusing to overwrite the source study')
    rig = copy.deepcopy(json.loads((SOURCE / 'rig.json').read_text(encoding='utf-8')))
    if rig.get('id') != 'xiaoxun_live2d_chibi_study':
        raise ValueError('Unexpected source rig')
    removed_parts = {'ear_l', 'ear_r', 'tail'}
    source_ids = {p['id'] for p in rig['parts']}
    if not removed_parts <= source_ids:
        raise ValueError('Source study is missing separate animal-feature parts')
    rig['id'] = 'xiaoxun_live2d_chibi_human_study'
    rig['name'] = '小寻 · 无兽特征 Chibi 试装'
    rig['parts'] = [p for p in rig['parts'] if p['id'] not in removed_parts]
    for group in ('ear_l', 'ear_r', 'tail'):
        del rig['groups'][group]
    rig['actions'] = [a for a in rig['actions'] if a['id'] not in ('ear_test', 'tail_test')]
    for action in rig['actions']:
        action['channels'] = [c for c in action['channels'] if c['target'] not in removed_parts]
    (out / 'sprites').mkdir(parents=True, exist_ok=True)
    for part in rig['parts']:
        path = Path(part['file'])
        if path.is_absolute() or '..' in path.parts:
            raise ValueError(f'Unsafe part path: {path}')
        shutil.copyfile(SOURCE / path, out / path)
    (out / 'rig.json').write_text(json.dumps(rig, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print('Built independent no-animal-feature Chibi study:', out)


if __name__ == '__main__':
    build()
