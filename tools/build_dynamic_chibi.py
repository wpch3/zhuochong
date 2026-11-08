#!/usr/bin/env python3
"""Build an isolated, inspectable Chibi motion study from the seam trial.

No production forms are touched. The arm partition is reversible at neutral;
a narrow synthetic seam underpaint is not original hidden artwork. Motion must
be visually reviewed.
Requires Pillow/numpy.
"""
import copy
from collections import deque
import hashlib
import json
from pathlib import Path
import shutil

import numpy as np
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'experiments/live2d_chibi_human_blackline_seam'
OUT = ROOT / 'experiments/live2d_chibi_dynamic'
SOURCE_RIG_SHA256 = 'ccf478ff70c11234f9aa5e6ea7209a99a46333cffb42853523e35cafeae4f411'
SOURCE_BODY_SHA256 = '15c746f038f52890433caacd1c4031df9d5b4fe1e5511090eea556e688077625'
# Local coordinates in body.png (480x512). The paths follow jacket/arm edges;
# they are an explicit trial rather than original editable layered art.
LEFT = [(0, 35), (140, 35), (158, 70), (152, 105), (140, 145), (133, 172),
        (135, 190), (131, 205), (115, 220), (110, 240), (0, 240)]
RIGHT = [(480, 35), (315, 35), (302, 70), (308, 105), (320, 145), (327, 172),
         (325, 190), (330, 205), (365, 220), (370, 240), (480, 240)]


def parameter(id, label, minimum, maximum, default, binds):
    return {'id': id, 'label': label, 'min': minimum, 'max': maximum, 'default': default, 'binds': binds}


def bind(group, channel, scale):
    return {'group': group, 'param': channel, 'scale': scale}


def build(out=OUT):
    out = Path(out)
    resolved = out.resolve()
    source = SOURCE.resolve()
    if resolved == source or source in resolved.parents or resolved in source.parents:
        raise ValueError('refusing to write inside or above source study')
    # Inside the repository, permit only the dedicated output and build scratch.
    # This prevents accidentally overwriting any other experiment or a formal rig.
    build_root = (ROOT / 'build').resolve()
    if ROOT.resolve() in resolved.parents and resolved != OUT.resolve() and build_root not in resolved.parents:
        raise ValueError('refusing to write outside dynamic study or build scratch')
    rig_bytes = (SOURCE / 'rig.json').read_bytes()
    if hashlib.sha256(rig_bytes).hexdigest() != SOURCE_RIG_SHA256:
        raise ValueError('source rig changed; review bindings before rebuilding')
    rig = copy.deepcopy(json.loads(rig_bytes))
    if rig.get('id') != 'xiaoxun_live2d_chibi_human_seam_study':
        raise ValueError('unexpected source rig')
    body = next(p for p in rig['parts'] if p['id'] == 'body')
    if body['pos'] != [280, 458] or body['file'] != 'sprites/body.png':
        raise ValueError('source body layout changed; review partition')
    if hashlib.sha256((SOURCE / body['file']).read_bytes()).hexdigest() != SOURCE_BODY_SHA256:
        raise ValueError('source body changed; review the manual partition before rebuilding')
    source = np.array(Image.open(SOURCE / body['file']).convert('RGBA'))
    if source.shape != (512, 480, 4):
        raise ValueError('source body size changed')
    masks = []
    for points in (LEFT, RIGHT):
        im = Image.new('1', (480, 512)); ImageDraw.Draw(im).polygon(points, fill=1)
        masks.append(np.array(im, dtype=bool))
    # Below the cuff the two hands are disconnected from the skirt in the
    # source. Use their real alpha components, rather than cutting a thumb or
    # inadvertently moving a strip of the skirt with a polygon.
    alpha = source[..., 3] > 0
    for mask, seed in zip(masks, ((90, 210), (370, 210))):
        mask[200:] = False
        x0, y0 = seed
        if not alpha[y0, x0]:
            raise ValueError('hand seed is no longer on source artwork')
        queue = deque([(x0, y0)])
        mask[y0, x0] = True
        while queue:
            x, y = queue.popleft()
            for xx, yy in ((x-1,y), (x+1,y), (x,y-1), (x,y+1)):
                if 0 <= xx < 480 and 200 <= yy < 512 and alpha[yy,xx] and not mask[yy,xx]:
                    mask[yy,xx] = True
                    queue.append((xx,yy))
        ys, xs = np.nonzero(mask[200:])
        if len(xs) < 500 or (xs.max()-xs.min()) > 80 or ys.max() > 50:
            raise ValueError('hand component merged with another body part')
    if np.any(masks[0] & masks[1]):
        raise ValueError('sleeve masks overlap')
    out.mkdir(parents=True, exist_ok=True)
    for part in rig['parts']:
        path = Path(part['file'])
        if path.is_absolute() or '..' in path.parts:
            raise ValueError('unsafe sprite path')
        (out / path).parent.mkdir(parents=True, exist_ok=True)
        if part['id'] != 'body':
            shutil.copyfile(SOURCE / path, out / path)
    # Deliberately limited synthetic seam underpaint: extend the adjacent torso
    # colours underneath fully opaque arm pixels only. It is not original
    # hidden artwork and cannot repair large swings or missing anatomy.
    underpaint = np.zeros_like(source)
    for y in range(35, 190):
        for mask, sign in ((masks[0], 1), (masks[1], -1)):
            xs = np.flatnonzero(mask[y])
            if len(xs) == 0:
                continue
            boundary = int(xs.max() if sign == 1 else xs.min())
            sample = boundary + sign * 6
            if not (0 <= sample < source.shape[1]) or source[y, sample, 3] != 255:
                continue
            for n in range(16):
                x = boundary - sign*n
                if 0 <= x < source.shape[1] and mask[y, x] and source[y, x, 3] == 255:
                    underpaint[y, x] = source[y, sample]
    for name, mask in [('body', ~(masks[0] | masks[1])), ('arm_l', masks[0]), ('arm_r', masks[1])]:
        rgba = source.copy()
        rgba[~mask] = 0
        if name == 'body':
            opaque = underpaint[..., 3] == 255
            rgba[opaque] = underpaint[opaque]
        Image.fromarray(rgba).save(out / 'sprites' / (name + '.png'))
    rig['id'] = 'xiaoxun_live2d_chibi_dynamic_study'
    rig['name'] = '小寻 · 无兽动态绑定试装'
    rig['groups']['shoulder_l'] = {'pivot': [420, 493], 'parent': 'body'}
    rig['groups']['shoulder_r'] = {'pivot': [595, 493], 'parent': 'body'}
    for side in ('l', 'r'):
        rig['parts'].append({'id': 'arm_' + side, 'file': 'sprites/arm_' + side + '.png',
                             'group': 'shoulder_' + side, 'pos': [280, 458], 'anchor': [0, 0], 'layer': 11})
    rig['params'].extend([
        parameter('ParamHeadTilt', '头部倾斜', -1, 1, 0, [bind('head', 'rot_deg', 4)]),
        parameter('ParamHeadShiftX', '头部平移 X', -1, 1, 0, [bind('head', 'dx', 5)]),
        parameter('ParamHeadShiftY', '头部平移 Y', -1, 1, 0, [bind('head', 'dy', 3)]),
        parameter('ParamArmL', '左侧袖手', -1, 1, 0, [bind('shoulder_l', 'rot_deg', 2)]),
        parameter('ParamArmR', '右侧袖手', -1, 1, 0, [bind('shoulder_r', 'rot_deg', -2)]),
        parameter('ParamBreath', '呼吸（轻微缩放）', 0, 1, 0, [bind('body', 'sy', .006)]),
        parameter('ParamMotionDrive', '身体摆动', -1, 1, 0, [bind('body', 'rot_deg', 1.2), bind('head', 'rot_deg', -1)]),
        parameter('ParamSleeveFollow', '袖子物理跟随', -1, 1, 0,
                  [bind('shoulder_l', 'rot_deg', .4), bind('shoulder_r', 'rot_deg', -.4)]),
    ])
    rig['physics2'] = [{'id': 'sleeve_follow', 'part': 'arm_l',
                        'angle_input': [{'param': 'ParamMotionDrive', 'weight': 1.0}],
                        'particles': [{'radius': 0}, {'radius': 20, 'mobility': .9, 'delay': 1.0, 'acceleration': 1.0}],
                        'outputs': [{'particle': 1, 'param': 'ParamSleeveFollow', 'scale': .05, 'max': 1.0}]}]
    def channel(target, wave, amp, freq, **extra):
        return {'target': target, 'param': 'value', 'wave': wave, 'amp': amp, 'freq': freq, **extra}
    rig['actions'] = [
        {'id':'neutral', 'title':'静止检查', 'priority':2, 'loop':True, 'channels':[]},
        {'id':'idle', 'title':'呼吸待机', 'priority':0, 'loop':True, 'channels':[
            channel('ParamBreath','sine',.5,.18,bias=.5),
            channel('ParamMotionDrive','drift',.35,.12),
            channel('ParamHeadTilt','drift',.22,.13,phase=.2)]},
        {'id':'sway', 'title':'轻轻摇摆', 'priority':2, 'loop':True, 'channels':[
            channel('ParamMotionDrive','sine',.8,.18), channel('ParamHeadTilt','sine',.4,.18,phase=.15),
            channel('ParamBreath','sine',.5,.18,bias=.5)]},
        {'id':'hand_wave', 'title':'袖手轻摆', 'priority':2, 'loop':True, 'channels':[
            channel('ParamArmL','sine',.8,.3), channel('ParamArmR','sine',.8,.3,phase=.5)]},
        {'id':'head_test', 'title':'头部倾斜', 'priority':2, 'loop':True, 'channels':[
            channel('ParamHeadTilt','sine',1,.25)]},
        {'id':'talk', 'title':'说话', 'priority':2, 'loop':True, 'channels':[
            channel('ParamMouthOpenY','flap',1,2), channel('ParamBreath','sine',.5,.18,bias=.5)]},
    ]
    for region in rig['regions']:
        region['action'] = 'sway' if region['id'] == 'body' else 'head_test'
    report = {'source': str(SOURCE.relative_to(ROOT)), 'body_size':[480,512],
              'left_polygon':LEFT, 'right_polygon':RIGHT,
              'left_source_pixels':int(np.count_nonzero(masks[0] & (source[...,3]>0))),
              'right_source_pixels':int(np.count_nonzero(masks[1] & (source[...,3]>0))),
              'underpaint_pixels': int(np.count_nonzero(underpaint[...,3])),
              'limitation':'binary partition with synthetic narrow seam underpaint; no original hidden shoulder art'}
    (out / 'rig.json').write_text(json.dumps(rig, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    (out / 'parts_report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print('Built dynamic study:', json.dumps(report, ensure_ascii=False))


if __name__ == '__main__':
    build()
