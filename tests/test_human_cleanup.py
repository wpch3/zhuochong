#!/usr/bin/env python3
"""Rebuild the isolated cleanup and verify source, locality, and exact outputs."""
import hashlib
import importlib.util
import json
import tempfile
from pathlib import Path
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('cleanup', ROOT / 'tools/build_human_chibi_cleanup.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
source = module.SOURCE
committed = module.OUT


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    rig = json.loads((source / 'rig.json').read_text(encoding='utf-8'))
    files = [source / 'rig.json'] + [source / p['file'] for p in rig['parts']]
    before = [digest(p) for p in files]
    try:
        module.build(source)
        raise AssertionError('source overwrite must be refused')
    except ValueError:
        pass
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / 'study'
        module.build(out)
        report = json.loads((out / 'cleanup_report.json').read_text(encoding='utf-8'))
        assert sum(c['pixels'] for group in report['removed'].values() for c in group) == 13
        for name in ('rig.json', 'cleanup_report.json'):
            assert digest(out / name) == digest(committed / name)
        for part in rig['parts']:
            path = Path(part['file'])
            assert digest(out / path) == digest(committed / path), path
            if part['id'] not in ('body', 'head'):
                assert digest(out / path) == digest(source / path), path
                continue
            a = Image.open(source / path).convert('RGBA')
            b = Image.open(out / path).convert('RGBA')
            assert a.size == b.size
            changes = []
            for y in range(a.height):
                for x in range(a.width):
                    p, q = a.getpixel((x, y)), b.getpixel((x, y))
                    if p != q:
                        gx, gy = x + part['pos'][0], y + part['pos'][1]
                        x0, y0, x1, y1 = module.ROI
                        assert x0 <= gx < x1 and y0 <= gy < y1
                        assert p[3] > 32 and q == (0, 0, 0, 0)
                        changes.append((gx, gy))
            assert len(changes) == sum(c['pixels'] for c in report['removed'][part['id']])
    assert before == [digest(p) for p in files], 'source study changed'
    print('清边试装：13 个局部像素、源与其他切件不变、可复现')


if __name__ == '__main__':
    main()
