#!/usr/bin/env python3
"""Replace the flattened hand with experimental continuous webbed SVG art.

Reuses the local mesh-field diagnostic. No separate finger depth or curl.
"""
import argparse
from io import BytesIO
import json
import shutil
import sys
from pathlib import Path
import numpy as np
from PIL import Image
import resvg_py
import build_chibi_whole_hand_study as base
import build_chibi_underlay as torso

ROOT = Path(__file__).resolve().parents[1]
ART = ROOT / 'experiments/live2d_chibi_morph_study/hand_continuous.svg'


def build(output, distance=2.0, sigma=3.5):
    out = Path(output)
    report = base.build(out, distance, sigma, padding=2)
    try:
        art = np.asarray(Image.open(BytesIO(resvg_py.svg_to_bytes(svg_path=str(ART), width=480,
                                                                height=512, skip_system_fonts=True))).convert('RGBA'))
        xx = np.indices((512, 480))[1]
        for side in 'lr':
            x0, y0, x1, y1 = report['sides'][side]['bbox']
            mask = np.zeros((512, 480), dtype=bool)
            mask[y0:y1, x0:x1] = True
            side_mask = xx < 240 if side == 'l' else xx >= 240
            if np.any((art[:, :, 3] > 0) & side_mask & ~mask):
                raise ValueError('new artwork extends beyond the fixed hand mesh')
            cropped = art[y0:y1, x0:x1]
            if not np.any(cropped[:, :, 3]):
                raise ValueError('new hand artwork is empty')
            Image.fromarray(cropped).save(out / f'sprites/whole_hand_{side}.png')
        result = {'visual_acceptance': 'not evaluated', 'art_sha256': torso.sha(ART),
                  'distance': distance, 'sigma': sigma, 'limitations': report['limitations']}
        (out / 'webbed_hand_report.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        return result
    except BaseException:
        shutil.rmtree(out)
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    parser.add_argument('--distance', type=float, default=2.0)
    parser.add_argument('--sigma', type=float, default=3.5)
    args = parser.parse_args()
    try:
        print(json.dumps(build(args.output, args.distance, args.sigma), ensure_ascii=False, indent=2))
    except (ValueError, OSError, KeyError, StopIteration) as exc:
        print(f'webbed hand study: {exc}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
