#!/usr/bin/env python3
"""Isolated vector re-rasterization study for rotated hand filtering.

Draw the existing hand vector at double resolution and use half-sized parts.
This does not alter the hand topology, fix occlusion or approve the art.
"""
import argparse
from io import BytesIO
import json
from pathlib import Path
import shutil
import sys
import xml.etree.ElementTree as ET

import numpy as np
from PIL import Image
import resvg_py
import build_chibi_binding_art as binding
import build_chibi_layered_sleeve_study as layered
import build_chibi_underlay as torso

ROOT = Path(__file__).resolve().parents[1]
CLOSURE = ROOT / 'experiments/live2d_chibi_closure'
RIGHT_INDEX = ROOT / 'experiments/live2d_chibi_visual_review/hand_right.svg'


def render(path, name, side):
    tree = ET.parse(path).getroot()
    hand = next(g for g in tree.iter() if g.get('id') == 'hand')
    for child in list(hand):
        if not (child.get('id') == name or (name == 'palm' and child.get('id') is None)):
            hand.remove(child)
    data = resvg_py.svg_to_bytes(svg_string=ET.tostring(tree, encoding='unicode'),
                                 width=960, height=1024, skip_system_fonts=True)
    arr = np.asarray(Image.open(BytesIO(data)).convert('RGBA')).copy()
    if side == 'l':
        arr[:, 480:] = 0
    else:
        arr[:, :480] = 0
    if not arr[:, :, 3].any():
        raise ValueError('empty hand art')
    return Image.fromarray(arr)


def build(output):
    out = Path(output)
    layered.build(out)
    try:
        path = out / 'rig.json'
        rig = json.loads(path.read_text(encoding='utf-8'))
        sources = set()
        for side in 'lr':
            for name in binding.FINGERS + ('palm',):
                source = RIGHT_INDEX if side == 'r' and name == 'index' else CLOSURE / f'hand_{"left" if side == "l" else "right"}.svg'
                sources.add(source)
                ident = f'hand_{side}' if name == 'palm' else f'finger_{side}_{name}'
                part = next(p for p in rig['parts'] if p['id'] == ident)
                if part.get('pos') != [280, 458] or part.get('anchor') != [0, 0] or 'scale' in part:
                    raise ValueError('unexpected hand placement or scale: ' + ident)
                if any(d.get('part') == ident for d in rig.get('deformers', [])):
                    raise ValueError('unexpected mesh on hand: ' + ident)
                render(source, name, side).save(out / part['file'])
                part['scale'] = .5
        path.write_text(json.dumps(rig, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        report = {'visual_acceptance': 'not evaluated', 'source_sha256': {str(s.relative_to(ROOT)): torso.sha(s) for s in sorted(sources)},
                  'resolution': [960, 1024], 'part_scale': .5,
                  'limitations': ['original contours and finger depth unchanged', 'neutral not pixel-identical',
                                  'downsampling/rotation may still blur', 'not a root or sleeve fix',
                                  'only fixed isolated fixture, no production changes']}
        (out / 'hires_hand_report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        return report
    except BaseException:
        shutil.rmtree(out)
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    try:
        print(json.dumps(build(args.output), ensure_ascii=False, indent=2))
    except (ValueError, OSError, KeyError, StopIteration, ET.ParseError) as exc:
        print(f'hires hand study: {exc}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
