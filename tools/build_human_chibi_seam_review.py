#!/usr/bin/env python3
"""Remove one manually reviewed detached body-sprite dash in an isolated copy."""
import copy
import json
from pathlib import Path
import shutil
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'experiments/live2d_chibi_human_blackline_clean'
OUT = ROOT / 'experiments/live2d_chibi_human_blackline_seam'
# Global canvas positions and original RGBA, identified by inspecting the
# detached stroke at the bottom of the original head/upper edge of the body.
PIXELS = {(412,465):(46,27,50,255), (413,465):(47,29,52,255),
          (414,465):(46,28,51,255), (415,465):(45,26,49,255)}


def build(out=OUT):
    out = Path(out)
    if out.resolve() == SOURCE.resolve() or SOURCE.resolve() in out.resolve().parents:
        raise ValueError('refusing to overwrite source study')
    rig = copy.deepcopy(json.loads((SOURCE / 'rig.json').read_text(encoding='utf-8')))
    if rig.get('id') != 'xiaoxun_live2d_chibi_human_clean_study':
        raise ValueError('unexpected source rig')
    bodies = [p for p in rig['parts'] if p['id'] == 'body']
    if len(bodies) != 1 or bodies[0].get('pos') != [280, 458]:
        raise ValueError('body source geometry changed; inspect again')
    rig['id'] = 'xiaoxun_live2d_chibi_human_seam_study'
    rig['name'] = '小寻 · 黑描边发梢清理试装'
    out.mkdir(parents=True, exist_ok=True)
    for part in rig['parts']:
        path = Path(part['file'])
        if path.is_absolute() or '..' in path.parts:
            raise ValueError('unsafe sprite path')
        (out / path).parent.mkdir(parents=True, exist_ok=True)
        if part['id'] == 'body':
            image = Image.open(SOURCE / path).convert('RGBA')
            ox, oy = part['pos']
            # Fail closed if the specific reviewed pixels have changed.
            for (gx, gy), expected in PIXELS.items():
                if image.getpixel((gx-ox, gy-oy)) != expected:
                    raise ValueError('reviewed pixels changed; inspect again')
            for gx, gy in PIXELS:
                image.putpixel((gx-ox, gy-oy), (0,0,0,0))
            image.save(out / path)
        else:
            shutil.copyfile(SOURCE / path, out / path)
    (out / 'rig.json').write_text(json.dumps(rig, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    report = {'source': 'live2d_chibi_human_blackline_clean', 'body_removed_global': [list(p) for p in PIXELS]}
    (out / 'seam_report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print('Built reviewed seam study:', json.dumps(report))


if __name__ == '__main__':
    build()
