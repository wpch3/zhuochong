#!/usr/bin/env python3
"""Isolated pocket relocation diagnostic; NOT approved production artwork.

Extract the coloured trims independently from a fixed study source, restore
underlying jacket by inpainting, and shift each toward the centre. This tests
partial pocket occlusion; it does not address sleeve geometry, and changes the
jacket design and underlying pixels. Requires OpenCV, numpy and Pillow.
"""
import argparse
import json
import shutil
import sys
from pathlib import Path
import cv2
import numpy as np
from PIL import Image
import build_chibi_layered_sleeve_study as layered


def build(output, distance=8):
    if not isinstance(distance, int) or not 1 <= distance <= 12:
        raise ValueError('distance must be an integer in 1..12')
    out = Path(output)
    layered.build(out)
    try:
        path = out / 'sprites/body.png'
        original = np.array(Image.open(path).convert('RGBA'))
        if original.shape != (512, 480, 4):
            raise ValueError('unexpected body shape')
        rgb = original[:, :, :3].astype(float)
        red, green, blue = rgb.transpose(2, 0, 1)
        yy, xx = np.indices(red.shape)
        total = np.zeros(red.shape, np.uint8)
        masks, stats_out = [], {}
        for side, lo, hi, dx in (('l', 138, 174, distance), ('r', 285, 322, -distance)):
            teal = ((green > red+15) & (blue > red+8) & (red < 180)
                    & (xx >= lo) & (xx < hi) & (yy >= 125) & (yy < 174))
            count, labels, stats, _ = cv2.connectedComponentsWithStats(teal.astype('uint8'))
            if count < 2:
                raise ValueError('pocket not found')
            idx = 1 + np.argmax(stats[1:, cv2.CC_STAT_AREA])
            x, y, width, height, area = [int(v) for v in stats[idx]]
            if not (240 <= area <= 350 and 20 <= width <= 30 and 34 <= height <= 43):
                raise ValueError(f'unexpected pocket shape {side}')
            mask = cv2.dilate((labels == idx).astype('uint8'), np.ones((5, 5), np.uint8))
            total = np.maximum(total, mask)
            masks.append((mask, dx))
            stats_out[side] = [x, y, width, height, area]
        clean = cv2.inpaint(original[:, :, :3], total, 3, cv2.INPAINT_TELEA).astype(float)
        result = original.copy()
        result[:, :, :3] = clean.astype('uint8')
        for mask, dx in masks:
            ys, xs = np.where(mask > 0)
            src = rgb[ys, xs]
            # Approximate extraction on white jacket; this is NOT original
            # layered art. Clamp to avoid division by zero at white pixels.
            alpha = np.clip((255 - np.min(src, axis=1))*1.5/255, 0, 1)
            bg = result[ys, xs+dx, :3].astype(float)
            fg = np.clip((src-(1-alpha[:, None])*255)/np.maximum(alpha[:, None], 1e-9), 0, 255)
            result[ys, xs+dx, :3] = np.round(alpha[:, None]*fg + (1-alpha[:, None])*bg).astype('uint8')
        if not np.array_equal(result[:, :, 3], original[:, :, 3]):
            raise ValueError('body alpha changed')
        Image.fromarray(result).save(path)
        info = {'visual_acceptance': 'not evaluated', 'distance_px': distance, 'components': stats_out,
                'limitations': ['changes jacket design and modifies neutral image',
                                'extracted trim is not source layered art',
                                'inpainted background needs close visual review',
                                'other sleeve deformation and hands unresolved']}
        (out/'pocket_split_report.json').write_text(json.dumps(info, indent=2)+'\n', encoding='utf-8')
        return info
    except BaseException:
        shutil.rmtree(out)
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    parser.add_argument('--distance', type=int, default=8)
    args = parser.parse_args()
    try:
        print(json.dumps(build(args.output, args.distance), indent=2))
    except (ValueError, OSError, KeyError, StopIteration) as exc:
        print(f'pocket split study: {exc}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
