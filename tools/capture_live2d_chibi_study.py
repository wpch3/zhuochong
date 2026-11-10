#!/usr/bin/env python3
"""Exercise and capture the isolated C Chibi preview, not production/personal data.

Requires Pillow and numpy. Leaves the model in idle with automatic blinking.
"""
from io import BytesIO
import json
from pathlib import Path
import urllib.request

import numpy as np
from PIL import Image

BASE = 'http://127.0.0.1:5202'
OUT = Path(__file__).resolve().parents[1] / 'experiments/live2d_chibi_short/qa'


def get(path):
    with urllib.request.urlopen(BASE + path, timeout=20) as response:
        return response.read()


def image():
    return Image.open(BytesIO(get('/api/frame.png?s=100'))).convert('RGBA')


def main():
    if json.loads(get('/api/info.json')).get('form') != 'live2d_study':
        raise SystemExit('Refusing: port 5202 is not the isolated live2d_study preview')
    OUT.mkdir(parents=True, exist_ok=True)
    try:
        get('/api/pause?on=1')
        get('/api/action?id=idle')
        get('/api/param?id=ParamMouthOpenY&v=0')
        get('/api/blink?v=0')
        get('/api/step?n=1')
        ref = image()
        images = {'idle': ref}
        get('/api/blink?v=1')
        get('/api/step?n=1')
        images['closed'] = image()
        get('/api/blink?v=0')
        get('/api/param?id=ParamMouthOpenY&v=1')
        get('/api/step?n=1')
        images['mouth'] = image()
        get('/api/param?id=ParamMouthOpenY&v=0')
        for name in ('head_test', 'ear_test', 'tail_test'):
            get('/api/action?id=idle')
            get('/api/step?n=1')
            get('/api/action?id=' + name)
            get('/api/step?n=60')
            images[name] = image()
        for name, im in images.items():
            im.save(OUT / (name + '.png'))
        a = np.asarray(ref)
        h, w = a.shape[:2]
        def changed(im, box):
            d = np.any(a != np.asarray(im), axis=2)
            x0, y0, x1, y1 = box
            return int(d[round(y0*h/1024):round(y1*h/1024), round(x0*w/1024):round(x1*w/1024)].sum())
        metrics = {'frame': [w, h],
                   'left_blink_pixels': changed(images['closed'], (390, 286, 490, 400)),
                   'right_blink_pixels': changed(images['closed'], (525, 286, 630, 400)),
                   'mouth_pixels': changed(images['mouth'], (480, 405, 542, 445)),
                   'head_motion_pixels': changed(images['head_test'], (320, 100, 700, 450)),
                   'left_ear_motion_pixels': changed(images['ear_test'], (315, 80, 440, 220)),
                   'right_ear_motion_pixels': changed(images['ear_test'], (580, 80, 705, 220)),
                   'tail_motion_pixels': changed(images['tail_test'], (600, 680, 760, 850)),
                   'head_test_body_pixels': changed(images['head_test'], (320, 500, 700, 950)),
                   'ear_test_body_pixels': changed(images['ear_test'], (320, 500, 700, 950)),
                   'tail_test_head_pixels': changed(images['tail_test'], (300, 50, 720, 450))}
        (OUT / 'metrics.json').write_text(json.dumps(metrics, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
        print(json.dumps(metrics, ensure_ascii=False))
        motion = ('left_blink_pixels', 'right_blink_pixels', 'mouth_pixels', 'head_motion_pixels',
                  'left_ear_motion_pixels', 'right_ear_motion_pixels', 'tail_motion_pixels')
        if min(metrics[k] for k in motion) < 20:
            raise SystemExit('A tested facial or animated region did not change')
        if any(metrics[k] for k in ('head_test_body_pixels', 'ear_test_body_pixels', 'tail_test_head_pixels')):
            raise SystemExit('A supposedly stationary region changed')
    finally:
        get('/api/action?id=idle')
        get('/api/param?id=ParamMouthOpenY&v=0')
        get('/api/blink?v=auto')
        get('/api/pause?on=0')


if __name__ == '__main__':
    main()
