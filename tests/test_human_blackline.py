#!/usr/bin/env python3
"""Black-outline study is reproducible, non-destructive and keeps original alpha."""
from pathlib import Path
import hashlib
import json
import sys
import tempfile

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from build_human_chibi_blackline import build
SOURCE = ROOT / 'experiments/live2d_chibi_human_short'
TARGET = ROOT / 'experiments/live2d_chibi_human_blackline'


def manifest(path):
    return {p.relative_to(path).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in path.rglob('*') if p.is_file()}


def main():
    before = manifest(SOURCE)
    with tempfile.TemporaryDirectory(prefix='blackline-test-') as temp:
        target = Path(temp)
        build(target)
        assert before == manifest(SOURCE), 'source study changed'
        rig = json.loads((target / 'rig.json').read_text(encoding='utf-8'))
        assert rig == json.loads((TARGET / 'rig.json').read_text(encoding='utf-8'))
        changed, darker, brighter = 0, 0, 0
        for part in rig['parts']:
            path = part['file']
            a = np.asarray(Image.open(SOURCE / path).convert('RGBA')).astype(int)
            b = np.asarray(Image.open(target / path).convert('RGBA')).astype(int)
            c = np.asarray(Image.open(TARGET / path).convert('RGBA')).astype(int)
            assert np.array_equal(a[:, :, 3], b[:, :, 3]), f'alpha changed: {path}'
            assert np.array_equal(b, c), f'generated asset differs: {path}'
            m = (a[:, :, 3] > 0) & np.any(a[:, :, :3] != b[:, :, :3], axis=2)
            changed += int(m.sum())
            brightness_a = a[:, :, :3].sum(axis=2)
            brightness_b = b[:, :, :3].sum(axis=2)
            darker += int((m & (brightness_b < brightness_a)).sum())
            brighter += int((m & (brightness_b > brightness_a)).sum())
            demo = ROOT / 'tools/rig_editor/demo' / path
            assert demo.read_bytes() == (target / path).read_bytes(), f'editor demo stale: {path}'
        assert changed > 1000 and darker > changed * .98 and brighter < changed * .01
        assert rig == json.loads((ROOT / 'tools/rig_editor/demo.json').read_text(encoding='utf-8'))
        print(f'黑描边：{changed} 个有色像素变化、{darker} 变暗；alpha 不变、来源不变、编辑器示例一致')


if __name__ == '__main__':
    main()
