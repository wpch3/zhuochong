#!/usr/bin/env python3
"""Capture and assert real C-engine dynamic frames, not a simulated renderer.

Start tools/preview_live2d_chibi.py --dynamic first. This deliberately changes
that isolated preview's state and returns it to idle on exit. Pillow/numpy needed.
"""
import argparse
from io import BytesIO
import json
from pathlib import Path
import urllib.request
import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'experiments/live2d_chibi_dynamic/qa'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=5209)
    parser.add_argument('--baseline-port', type=int, help='optional seam preview for neutral C-frame comparison')
    parser.add_argument('--out', type=Path, default=OUT, help='capture output directory')
    args = parser.parse_args()
    out = args.out
    base = f'http://127.0.0.1:{args.port}'
    def get(path, origin=base):
        with urllib.request.urlopen(origin + path, timeout=30) as r:
            return r.read()
    def call(path):
        return json.loads(get(path))
    def frame(origin=base):
        return Image.open(BytesIO(get('/api/frame.png?s=100', origin))).convert('RGBA')
    def diff(a, b):
        return int(np.any(np.asarray(a) != np.asarray(b), axis=2).sum())
    def val(id):
        return next(p['effective'] for p in call('/api/params.json')['params'] if p['id'] == id)
    if call('/api/info.json').get('form') != 'human_dynamic_study':
        raise SystemExit('Refusing: preview is not the isolated dynamic study')
    out.mkdir(parents=True, exist_ok=True)
    try:
        call('/api/pause?on=1')
        call('/api/action?id=neutral')
        call('/api/param?all=1')
        call('/api/blink?v=0')
        call('/api/step?n=900')
        neutral = frame(); neutral.save(out / 'neutral.png')
        metrics = {'frame': list(neutral.size), 'parameter_pixels': {}, 'action_changes': {}}
        if args.baseline_port:
            origin = f'http://127.0.0.1:{args.baseline_port}'
            if json.loads(get('/api/info.json', origin)).get('form') != 'human_seam_study':
                raise SystemExit('Refusing: baseline is not the seam study')
            for path in ('/api/pause?on=1', '/api/action?id=idle', '/api/param?all=1', '/api/blink?v=0', '/api/step?n=900'):
                get(path, origin)
            metrics['neutral_vs_seam_c_pixels'] = diff(neutral, frame(origin))
            get('/api/blink?v=auto', origin); get('/api/pause?on=0', origin)
        states = [('arm_l_min', 'ParamArmL', -1), ('arm_l_mid', 'ParamArmL', .5),
                  ('arm_l_max', 'ParamArmL', 1), ('arm_r_min', 'ParamArmR', -1),
                  ('arm_r_max', 'ParamArmR', 1), ('head_min', 'ParamHeadTilt', -1),
                  ('head_max', 'ParamHeadTilt', 1), ('shift_x', 'ParamHeadShiftX', 1),
                  ('shift_y', 'ParamHeadShiftY', 1), ('breath', 'ParamBreath', 1),
                  ('mouth', 'ParamMouthOpenY', 1)]
        for name, param, value in states:
            call(f'/api/param?id={param}&v={value}')
            call('/api/step?n=1')
            im = frame(); im.save(out / f'{name}.png')
            changed = diff(neutral, im)
            metrics['parameter_pixels'][name] = changed
            assert changed > 10, f'{name}: parameter did not visibly change frame ({changed})'
            call(f'/api/param?id={param}&v=0')
            call('/api/step?n=1')
            assert diff(neutral, frame()) == 0, f'{name}: did not return to neutral'
        call('/api/blink?v=1'); call('/api/step?n=1')
        closed = frame(); closed.save(out / 'blink.png')
        metrics['blink_pixels'] = diff(neutral, closed)
        assert metrics['blink_pixels'] > 100
        call('/api/blink?v=0'); call('/api/step?n=1')
        assert diff(neutral, frame()) == 0
        # A true physics2 impulse, not action sine: observe transient and decay.
        call('/api/param?id=ParamMotionDrive&v=1')
        physics = []
        for steps in (1, 3, 6, 10, 20, 30, 60):
            call(f'/api/step?n={steps}'); physics.append(val('ParamSleeveFollow'))
        assert max(physics) > .03 and max(physics) > physics[-1] + .005, physics
        call('/api/param?id=ParamMotionDrive&v=0')
        release = []
        for steps in (1, 6, 20, 60, 120, 240):
            call(f'/api/step?n={steps}'); release.append(val('ParamSleeveFollow'))
        assert min(release) < -.005 and abs(release[-1]) < .001, release
        metrics['physics_input_trace'] = physics
        metrics['physics_release_trace'] = release
        action_param = {'idle': 'ParamBreath', 'sway': 'ParamMotionDrive',
                        'hand_wave': 'ParamArmL', 'head_test': 'ParamHeadTilt', 'talk': 'ParamMouthOpenY'}
        metrics['action_param_ranges'] = {}
        for action in ('idle', 'sway', 'hand_wave', 'head_test', 'talk'):
            call('/api/param?all=1'); call(f'/api/action?id={action}')
            ims, values = [], []
            for i in range(8):
                call('/api/step?n=15'); im = frame(); ims.append(im)
                values.append(val(action_param[action]))
                if action in ('sway', 'hand_wave') and i in (0, 2, 4, 6):
                    im.save(out / f'{action}_{i:02}.png')
            changes = [diff(ims[i], ims[i+1]) for i in range(7)]
            metrics['action_changes'][action] = changes
            metrics['action_param_ranges'][action] = [min(values), max(values)]
            assert max(values) - min(values) > .1, f'{action}: channel did not animate: {values}'
            assert max(changes) > 20, f'{action}: action frames do not change: {changes}'
        # Inspection backdrops and torso close-ups are composites of C frames.
        for label, color in (('light', (247,247,247,255)), ('dark', (38,43,49,255))):
            bg = Image.new('RGBA', neutral.size, color); bg.alpha_composite(neutral)
            bg.convert('RGB').save(out / f'neutral_{label}.png')
            for name in ('arm_l_max', 'arm_r_max'):
                im = Image.open(out / f'{name}.png').convert('RGBA')
                detail = Image.new('RGBA', im.size, color); detail.alpha_composite(im)
                detail.crop((160,240,410,400)).resize((1000,640)).convert('RGB').save(out / f'{name}_{label}_detail.png')
        (out / 'metrics.json').write_text(json.dumps(metrics, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
        print(json.dumps(metrics, ensure_ascii=False, indent=2))
    finally:
        call('/api/param?all=1'); call('/api/action?id=idle')
        call('/api/blink?v=auto'); call('/api/pause?on=0')


if __name__ == '__main__':
    main()
