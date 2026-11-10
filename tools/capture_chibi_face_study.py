#!/usr/bin/env python3
"""Capture and compare actual C-rendered face-study states on local port 5201.

This resets the isolated preview's action, blink and mouth state. Requires
Pillow and numpy. Do not point it at a production/personal preview instance.
"""
from io import BytesIO
from pathlib import Path
import json
import urllib.request
import numpy as np
from PIL import Image

BASE = 'http://127.0.0.1:5201'
OUT = Path(__file__).resolve().parents[1] / 'experiments/chibi_face_study/qa'


def get(path):
    with urllib.request.urlopen(BASE + path, timeout=20) as r:
        return r.read()


def frame():
    get('/api/step?n=1')
    return Image.open(BytesIO(get('/api/frame.png?s=100'))).convert('RGBA')


def main():
    info = json.loads(get('/api/info.json'))
    if info.get('form') != 'face_study':
        raise SystemExit('Refusing: port 5201 is not the isolated face_study preview')
    OUT.mkdir(parents=True, exist_ok=True)
    try:
        get('/api/action?id=idle')
        get('/api/pause?on=1')
        get('/api/param?id=ParamMouthOpenY&v=0')
        get('/api/blink?v=0')
        opened = frame()
        get('/api/blink?v=1')
        closed = frame()
        get('/api/blink?v=0')
        get('/api/param?id=ParamMouthOpenY&v=1')
        mouth = frame()
        for name, image in [('open', opened), ('closed', closed), ('mouth', mouth)]:
            image.save(OUT / (name + '.png'))
        a, b, c = (np.asarray(x) for x in (opened, closed, mouth))
        eye_diff = np.any(a != b, axis=2)
        mouth_diff = np.any(a != c, axis=2)
        h, w = eye_diff.shape
        # Canvas is 1008x1042; frame size is controlled by the user's scale.
        def count(mask, box):
            x0, y0, x1, y1 = box
            return int(mask[round(y0*h/1042):round(y1*h/1042),
                            round(x0*w/1008):round(x1*w/1008)].sum())
        results = {'frame': [w, h],
                   'blink_left_changed_pixels': count(eye_diff, (350, 315, 480, 450)),
                   'blink_right_changed_pixels': count(eye_diff, (528, 315, 654, 450)),
                   'mouth_changed_pixels': count(mouth_diff, (475, 443, 538, 488))}
        (OUT / 'metrics.json').write_text(json.dumps(results, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        print(json.dumps(results, ensure_ascii=False))
        if min(results['blink_left_changed_pixels'], results['blink_right_changed_pixels'],
               results['mouth_changed_pixels']) < 20:
            raise SystemExit('One of the actual rendered regions did not change')
    finally:
        get('/api/param?id=ParamMouthOpenY&v=0')
        get('/api/blink?v=auto')
        get('/api/pause?on=0')


if __name__ == '__main__':
    main()
