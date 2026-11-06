#!/usr/bin/env python3
"""The reviewed seam trial must change exactly four isolated source pixels."""
import hashlib
import importlib.util
import json
import shutil
import tempfile
from pathlib import Path
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('seam', ROOT / 'tools/build_human_chibi_seam_review.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def digest(p):
    return hashlib.sha256(p.read_bytes()).digest()


def main():
    rig = json.loads((m.SOURCE / 'rig.json').read_text(encoding='utf-8'))
    files = [m.SOURCE / 'rig.json'] + [m.SOURCE / p['file'] for p in rig['parts']]
    before = [digest(p) for p in files]
    try:
        m.build(m.SOURCE)
        raise AssertionError('refusing source overwrite')
    except ValueError:
        pass
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / 'study'
        m.build(out)
        assert digest(out/'rig.json') == digest(m.OUT/'rig.json')
        assert digest(out/'seam_report.json') == digest(m.OUT/'seam_report.json')
        for part in rig['parts']:
            p = Path(part['file'])
            assert digest(out/p) == digest(m.OUT/p)
            if part['id'] != 'body':
                assert digest(out/p) == digest(m.SOURCE/p)
                continue
            old = Image.open(m.SOURCE/p).convert('RGBA')
            new = Image.open(out/p).convert('RGBA')
            ox, oy = part['pos']
            changes = {(x+ox,y+oy) for y in range(old.height) for x in range(old.width)
                       if old.getpixel((x,y)) != new.getpixel((x,y))}
            assert changes == set(m.PIXELS)
            for gx,gy in changes:
                assert old.getpixel((gx-ox,gy-oy)) == m.PIXELS[(gx,gy)]
                assert new.getpixel((gx-ox,gy-oy)) == (0,0,0,0)
        # A changed reviewed pixel must fail closed, not erase a different feature.
        altered = Path(tmp) / 'altered-source'
        shutil.copytree(m.SOURCE, altered)
        image_path = altered / 'sprites/body.png'
        image = Image.open(image_path).convert('RGBA')
        image.putpixel((412-280,465-458),(255,255,255,255))
        image.save(image_path)
        original = m.SOURCE
        m.SOURCE = altered
        try:
            try:
                m.build(Path(tmp) / 'reject')
                raise AssertionError('changed source pixel must be rejected')
            except ValueError as error:
                assert 'pixels changed' in str(error)
        finally:
            m.SOURCE = original
    assert before == [digest(p) for p in files]
    print('发梢复核试装：恰好移除 4 个已检查像素，保留源与其他贴图；源变化会拒绝')


if __name__ == '__main__':
    main()
