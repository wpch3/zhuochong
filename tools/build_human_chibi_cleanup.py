#!/usr/bin/env python3
"""Off-chain local cleanup of isolated magenta specks near the neck/hair seam.

Only tiny disconnected alpha islands in a reviewed ROI are removed. All other
pixels and the previous black-line study remain untouched. Requires Pillow.
"""
from collections import deque
import copy
import json
from pathlib import Path
import shutil
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'experiments/live2d_chibi_human_blackline'
OUT = ROOT / 'experiments/live2d_chibi_human_blackline_clean'
ROI = (390, 455, 465, 470)  # global canvas coordinates, right/bottom exclusive
MAX_AREA = 12


def cleanup(src, dst, origin):
    image = Image.open(src).convert('RGBA')
    w, h = image.size
    pixels = image.load()
    visited = bytearray(w*h)
    removed = []
    # Search only inside the reviewed ROI, but flood through the entire image to
    # avoid mistaking a projection of a larger connected strand for an island.
    x0, y0, x1, y1 = ROI
    for gy in range(y0, y1):
        for gx in range(x0, x1):
            x, y = gx-origin[0], gy-origin[1]
            if not (0 <= x < w and 0 <= y < h) or visited[y*w+x] or pixels[x, y][3] <= 32:
                continue
            stack = deque([(x, y)])
            visited[y*w+x] = 1
            component = []
            while stack:
                cx, cy = stack.pop()
                component.append((cx, cy))
                for dy in (-1, 0, 1):
                    for dx in (-1, 0, 1):
                        nx, ny = cx+dx, cy+dy
                        if 0 <= nx < w and 0 <= ny < h and not visited[ny*w+nx] and pixels[nx, ny][3] > 32:
                            visited[ny*w+nx] = 1
                            stack.append((nx, ny))
            if len(component) <= MAX_AREA and all(x0 <= px+origin[0] < x1 and y0 <= py+origin[1] < y1 for px, py in component):
                # Require a magenta-contaminated pixel to avoid removing a
                # deliberately drawn small independent stroke in this ROI.
                if any((p := pixels[px, py])[0]-p[1] > 45 and p[2]-p[1] > 35 for px, py in component):
                    for px, py in component:
                        pixels[px, py] = (0, 0, 0, 0)
                    removed.append({'pixels': len(component), 'canvas_bbox': [
                        min(px for px, _ in component)+origin[0], min(py for _, py in component)+origin[1],
                        max(px for px, _ in component)+origin[0], max(py for _, py in component)+origin[1]]})
    image.save(dst)
    return removed


def build(out=OUT):
    out = Path(out)
    if out.resolve() == SOURCE.resolve():
        raise ValueError('refusing to overwrite source study')
    rig = copy.deepcopy(json.loads((SOURCE / 'rig.json').read_text(encoding='utf-8')))
    if rig.get('id') != 'xiaoxun_live2d_chibi_human_blackline_study':
        raise ValueError('unexpected source rig')
    rig['id'] = 'xiaoxun_live2d_chibi_human_clean_study'
    rig['name'] = '小寻 · 无兽特征黑描边清边试装'
    out.mkdir(parents=True, exist_ok=True)
    report = {'roi': list(ROI), 'max_component_pixels': MAX_AREA, 'removed': {}}
    for part in rig['parts']:
        path = Path(part['file'])
        if path.is_absolute() or '..' in path.parts:
            raise ValueError('unsafe sprite path')
        (out / path).parent.mkdir(parents=True, exist_ok=True)
        if part['id'] in ('head', 'body'):
            report['removed'][part['id']] = cleanup(SOURCE / path, out / path, part['pos'])
        else:
            shutil.copyfile(SOURCE / path, out / path)
    (out / 'rig.json').write_text(json.dumps(rig, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    (out / 'cleanup_report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print('Built isolated seam cleanup:', json.dumps(report, ensure_ascii=False))


if __name__ == '__main__':
    build()
