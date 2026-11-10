#!/usr/bin/env python3
"""Capture facial and head-motion checks of the isolated no-animal Chibi.

Requires Pillow and numpy, and resets preview 5203 to idle after testing.
"""
from io import BytesIO
from pathlib import Path
import argparse
import json
import urllib.request

import numpy as np
from PIL import Image

BASE = 'http://127.0.0.1:5203'
OUT = Path(__file__).resolve().parents[1] / 'experiments/live2d_chibi_human_short/qa'


def get(path):
    with urllib.request.urlopen(BASE + path, timeout=20) as response:
        return response.read()


def image():
    return Image.open(BytesIO(get('/api/frame.png?s=100'))).convert('RGBA')


def main():
    global BASE, OUT
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--blackline', action='store_true', help='Capture the separate black-outline study on port 5205')
    mode.add_argument('--clean', action='store_true', help='Capture the isolated edge cleanup on port 5206')
    mode.add_argument('--seam', action='store_true', help='Capture the reviewed seam study on port 5207')
    args = parser.parse_args()
    expected = 'human_study'
    if args.seam:
        BASE = 'http://127.0.0.1:5207'
        OUT = Path(__file__).resolve().parents[1] / 'experiments/live2d_chibi_human_blackline_seam/qa'
        expected = 'human_seam_study'
    elif args.clean:
        BASE = 'http://127.0.0.1:5206'
        OUT = Path(__file__).resolve().parents[1] / 'experiments/live2d_chibi_human_blackline_clean/qa'
        expected = 'human_clean_study'
    elif args.blackline:
        BASE = 'http://127.0.0.1:5205'
        OUT = Path(__file__).resolve().parents[1] / 'experiments/live2d_chibi_human_blackline/qa'
        expected = 'human_blackline_study'
    info = json.loads(get('/api/info.json'))
    if info.get('form') != expected:
        raise SystemExit('Refusing: preview is not the expected isolated study')
    OUT.mkdir(parents=True, exist_ok=True)
    try:
        get('/api/pause?on=1')
        get('/api/action?id=idle')
        get('/api/param?id=ParamMouthOpenY&v=0')
        get('/api/blink?v=0')
        get('/api/step?n=1')
        frames = {'idle': image()}
        get('/api/blink?v=1')
        get('/api/step?n=1')
        frames['closed'] = image()
        get('/api/blink?v=0')
        get('/api/param?id=ParamMouthOpenY&v=1')
        get('/api/step?n=1')
        frames['mouth'] = image()
        get('/api/param?id=ParamMouthOpenY&v=0')
        get('/api/action?id=head_test')
        get('/api/step?n=60')
        frames['head_test'] = image()
        if args.seam:
            # Half a cycle later for the opposite head rotation (0.25 Hz).
            get('/api/step?n=120&dt=0.0166666667')
            frames['head_opposite'] = image()
        for name, im in frames.items():
            im.save(OUT / (name + '.png'))
        if args.blackline or args.clean or args.seam:
            # The model image is still an actual C frame; the neutral backdrops
            # are post-composites for inspection of thin outlines and matte.
            for name, color in [('idle_light', (247, 247, 247, 255)), ('idle_dark', (38, 43, 49, 255))]:
                bg = Image.new('RGBA', frames['idle'].size, color)
                bg.alpha_composite(frames['idle'])
                bg.convert('RGB').save(OUT / (name + '.png'))
        if args.clean or args.seam:
            # The detail images are derived from real C frames, not new renders.
            details = ('idle', 'head_test', 'head_opposite', 'closed') if args.seam else ('idle', 'head_test', 'closed')
            for name in details:
                bg = Image.new('RGBA', frames[name].size, (235, 236, 236, 255))
                bg.alpha_composite(frames[name])
                bg.crop((160, 100, 405, 285)).resize((980, 740)).convert('RGB').save(OUT / (name + '_detail.png'))
        base = np.asarray(frames['idle'])
        h, w = base.shape[:2]
        def count(name, box):
            x0, y0, x1, y1 = box
            diff = np.any(base != np.asarray(frames[name]), axis=2)
            return int(diff[round(y0*h/1024):round(y1*h/1024), round(x0*w/1024):round(x1*w/1024)].sum())
        metrics = {'frame': [w, h],
                   'left_blink_pixels': count('closed', (390, 286, 490, 400)),
                   'right_blink_pixels': count('closed', (525, 286, 630, 400)),
                   'mouth_pixels': count('mouth', (480, 405, 542, 445)),
                   'head_motion_pixels': count('head_test', (320, 100, 700, 450)),
                   'head_test_body_pixels': count('head_test', (320, 500, 700, 950))}
        (OUT / 'metrics.json').write_text(json.dumps(metrics, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        print(json.dumps(metrics, ensure_ascii=False))
        if min(metrics[k] for k in ('left_blink_pixels', 'right_blink_pixels', 'mouth_pixels', 'head_motion_pixels')) < 20:
            raise SystemExit('A tested facial or head region did not change')
        if metrics['head_test_body_pixels']:
            raise SystemExit('Head-only test unexpectedly changed the body')
    finally:
        get('/api/action?id=idle')
        get('/api/param?id=ParamMouthOpenY&v=0')
        get('/api/blink?v=auto')
        get('/api/pause?on=0')


if __name__ == '__main__':
    main()
