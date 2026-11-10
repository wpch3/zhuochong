#!/usr/bin/env python3
"""Rejected source-art diagnostic: move the pockets away from the sleeve.

Uses inpainting solely to test the cause of the apparent sleeve spur. It leaves
visible marks and alters jacket design; never use as production artwork.
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


def build(output):
    out = Path(output)
    layered.build(out)
    try:
        path = out / 'sprites/body.png'
        orig = np.array(Image.open(path).convert('RGBA'))
        if orig.shape != (512, 480, 4):
            raise ValueError('unexpected body image')
        mask = np.zeros(orig.shape[:2], np.uint8)
        pts = np.array([[140, 168], [148, 175], [173, 135], [164, 129]], np.int32)
        cv2.fillPoly(mask, [pts], 255)
        reflected = pts.copy()
        reflected[:, 0] = 460 - reflected[:, 0]
        cv2.fillPoly(mask, [reflected], 255)
        clean = cv2.inpaint(orig[:, :, :3], mask, 3, cv2.INPAINT_TELEA)
        edited = orig.copy()
        edited[:, :, :3] = clean
        for side, dx in (('l', 8), ('r', -8)):
            part = mask.copy()
            part[:, 240 if side == 'l' else 0:480 if side == 'l' else 240] = 0
            ys, xs = np.where(part > 0)
            edited[ys, xs + dx] = orig[ys, xs]
        Image.fromarray(edited).save(path)
        report = {'visual_acceptance': 'rejected', 'pocket_shift_px': 8,
                  'limitations': ['visible restoration marks', 'changes jacket design',
                                  'fixed image coordinates', 'does not fix other sleeve defects']}
        (out / 'pocket_shift_report.json').write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
        return report
    except BaseException:
        shutil.rmtree(out)
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    try:
        print(json.dumps(build(args.output), indent=2))
    except (ValueError, OSError, KeyError, StopIteration) as exc:
        print(f'pocket shift study: {exc}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
