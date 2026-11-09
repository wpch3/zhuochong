#!/usr/bin/env python3
"""Unapproved draw-order transition study with full continuous sleeve backing.

The back layer covers the full sleeve. The front layer is a fading copy of the
same composite near the old cut, keeping identical deformation and UVs. This
changes occlusion against the torso and is not a production asset.
"""
import argparse
import json
import shutil
import sys
from pathlib import Path
import numpy as np
from PIL import Image
import build_chibi_layered_sleeve_study as layered


def build(output, transition=16):
    if not isinstance(transition, int) or not 4 <= transition <= 40:
        raise ValueError('transition must be an integer between 4 and 40')
    out = Path(output)
    report = layered.build(out)
    try:
        result = {}
        for side in 'lr':
            back_path = out / f'sprites/arm_{side}.png'
            front_path = out / f'sprites/forearm_{side}.png'
            back = Image.open(back_path).convert('RGBA')
            front = Image.open(front_path).convert('RGBA')
            if back.size != front.size:
                raise ValueError('mismatched sleeve UVs')
            a = np.asarray(back)
            b = np.asarray(front)
            occupied = np.flatnonzero(np.any(b[:, :, 3] > 0, axis=1))
            if not len(occupied):
                raise ValueError('empty front sleeve')
            start = int(occupied[0])
            full = Image.alpha_composite(back, front)
            arr = np.array(full)
            yy = np.arange(arr.shape[0], dtype=float)
            t = np.clip((yy - start) / transition, 0, 1)
            smooth = t * t * (3 - 2 * t)
            arr[:, :, 3] = np.rint(arr[:, :, 3].astype(float) * smooth[:, None]).astype('uint8')
            full.save(back_path)
            Image.fromarray(arr).save(front_path)
            result[side] = {'front_start_row': start, 'transition_rows': transition,
                            'image_size': list(back.size)}
        info = {'visual_acceptance': 'not evaluated', 'sides': result,
                'limitations': ['alters front/back occlusion against body',
                                'may introduce translucent edge or halo',
                                'fixed-rig diagnostic only', 'not general skinning']}
        (out / 'sleeve_backing_report.json').write_text(json.dumps(info, indent=2) + '\n', encoding='utf-8')
        return info
    except BaseException:
        shutil.rmtree(out)
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    parser.add_argument('--transition', type=int, default=16)
    args = parser.parse_args()
    try:
        print(json.dumps(build(args.output, args.transition), indent=2))
    except (ValueError, OSError, KeyError, StopIteration) as exc:
        print(f'sleeve backing study: {exc}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
