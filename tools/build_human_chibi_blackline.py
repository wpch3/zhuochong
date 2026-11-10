#!/usr/bin/env python3
"""Build a non-destructive dark-outline variant of the human Chibi study.

The source artwork is untouched; this is an automatic tonal pass, not manually
re-inked line art. Requires Pillow and numpy. Alpha and geometry are preserved.
"""
from pathlib import Path
import copy
import json

import numpy as np
from PIL import Image, ImageFilter

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'experiments/live2d_chibi_human_short'
OUT = ROOT / 'experiments/live2d_chibi_human_blackline'


def ink_image(image, silhouette=False):
    a = np.asarray(image.convert('RGBA'), dtype=np.uint8)
    color = a[:, :, :3].astype(np.float32)
    alpha = a[:, :, 3]
    luminance = color @ np.array([.2126, .7152, .0722], dtype=np.float32)
    # Work on opaque color for the local contrast map. Transparent pixels are
    # excluded so their arbitrary RGB does not affect a visible stroke.
    valid_lum = np.where(alpha > 0, luminance, 0).astype(np.uint8)
    brightest = np.asarray(Image.fromarray(valid_lum).filter(ImageFilter.MaxFilter(7)), dtype=np.float32)
    contrast = np.clip((brightest - luminance - 12) / 30, 0, 1)
    dark = np.clip((140 - luminance) / 65, 0, 1)
    strength = contrast * dark * 0.82
    # Mostly neutral, nearly black ink; retain a little original hue at the
    # soft anti-aliased edges. This is a global approximation, not a vector line.
    black = np.minimum(luminance * .18, 18)[..., None]
    result = color * (1 - strength[..., None]) + black * strength[..., None]
    if silhouette:
        # Ink the existing silhouette without dilating alpha or drawing a new
        # contour over the artificial rectangular head/body seam. Expression
        # patches are excluded: their alpha is a diff mask, not line artwork.
        eroded = np.asarray(Image.fromarray(alpha).filter(ImageFilter.MinFilter(3)), dtype=np.float32)
        edge = (1 - eroded / 255) * np.clip(alpha.astype(np.float32) / 80, 0, 1) * .85
        edge[:4, :] = 0
        edge[-4:, :] = 0
        target = np.array([16, 15, 18], dtype=np.float32)
        result = result * (1 - edge[..., None]) + target * edge[..., None]
    result = np.rint(result).clip(0, 255).astype(np.uint8)
    result[alpha == 0] = a[alpha == 0, :3]
    return Image.fromarray(np.dstack((result, alpha)), 'RGBA')


def build(out=OUT):
    out = Path(out)
    if out.resolve() == SOURCE.resolve():
        raise ValueError('Cannot overwrite the source study')
    rig = copy.deepcopy(json.loads((SOURCE / 'rig.json').read_text(encoding='utf-8')))
    if rig.get('id') != 'xiaoxun_live2d_chibi_human_study':
        raise ValueError('Unexpected source rig')
    rig['id'] = 'xiaoxun_live2d_chibi_human_blackline_study'
    rig['name'] = '小寻 · 无兽特征黑描边试装'
    for part in rig['parts']:
        path = Path(part['file'])
        if path.is_absolute() or '..' in path.parts:
            raise ValueError(f'Unsafe sprite path: {path}')
        (out / path).parent.mkdir(parents=True, exist_ok=True)
        with Image.open(SOURCE / path) as image:
            ink_image(image, silhouette=part['id'] in ('head', 'body')).save(out / path)
    (out / 'rig.json').write_text(json.dumps(rig, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print('Built black-line isolated study:', out)


if __name__ == '__main__':
    build()
