#!/usr/bin/env python3
"""Sample smile and pain together with blink using the real C preview."""
import argparse
import itertools
import hashlib
import json
import math
import shutil
import tempfile
from pathlib import Path
from PIL import Image, ImageDraw
from capture_chibi_art_review import reset
from capture_chibi_joint_art import image
from capture_chibi_refinement import setup, save_crop
from capture_chibi_visual_matrix import verify_pose
from study_underpaint_sampling import ROOT, request, start, stop


def cases(blinks=(0, .5, 1)):
    out = {}
    for side, smile, pain, blink in itertools.product('LR', (0, .5, 1), (0, .5, 1), blinks):
        key = f'{side}_smile{smile}_pain{pain}_blink{blink}'
        out[key] = {f'ParamEye{side}Smile': smile, f'ParamEye{side}Pain': pain, 'blink': blink}
    return out


def capture(candidate, output, executable=None, blinks=(0, .5, 1)):
    root = (ROOT / 'build').resolve()
    candidate = Path(candidate).resolve()
    out = Path(output)
    target = out.resolve()
    if root not in candidate.parents or root not in target.parents or target == candidate or candidate in target.parents or target in candidate.parents:
        raise ValueError('separate paths inside build required')
    if out.exists() or out.is_symlink() or not out.parent.is_dir():
        raise ValueError('output must be new')
    if not (candidate / 'extended_report.json').is_file():
        raise ValueError('expected extended study')
    if not blinks or len(set(blinks)) != len(blinks) or any(not math.isfinite(v) or not 0 <= v <= 1 for v in blinks):
        raise ValueError('blink values must be distinct finite numbers in 0..1')
    binary = Path(executable).resolve() if executable else ROOT / 'build/zhuochong_preview'
    provenance = {'rig_sha256': hashlib.sha256((candidate / 'rig.json').read_bytes()).hexdigest(),
                  'preview_executable_sha256': hashlib.sha256(binary.read_bytes()).hexdigest()}
    poses, shots = cases(blinks), {}
    with tempfile.TemporaryDirectory(prefix='expression-mix-', dir=root) as temp:
        proc, url = start(Path(temp) / 'preview', candidate, executable)
        try:
            setup(url)
            for name, params in poses.items():
                reset(url)
                for k, v in params.items():
                    request(url, f'/api/blink?v={v}' if k == 'blink' else f'/api/param?id={k}&v={v}')
                request(url, '/api/step?n=3')
                verify_pose(url, params)
                shots[name] = image(url)
        finally:
            stop(proc)
    out.mkdir()
    try:
        for name, arr in shots.items():
            save_crop(arr, (375, 320, 640, 410), 1, out / f'{name}.png', (247, 247, 247, 255))
        for side in 'LR':
            for blink in blinks:
                sheet = Image.new('RGB', (265 * 3, 110 * 3), 'white')
                draw = ImageDraw.Draw(sheet)
                for row, smile in enumerate((0, .5, 1)):
                    for col, pain in enumerate((0, .5, 1)):
                        name = f'{side}_smile{smile}_pain{pain}_blink{blink}'
                        im = Image.open(out / f'{name}.png').resize((265, 90))
                        x, y = col * 265, row * 110
                        draw.text((x + 2, y + 2), name, fill='black')
                        sheet.paste(im, (x, y + 20))
                sheet.save(out / f'{side}_blink{blink}_sheet.png')
        (out / 'poses.json').write_text(json.dumps(poses, indent=2) + '\n', encoding='utf-8')
        (out / 'provenance.json').write_text(json.dumps({'before_capture': provenance}, indent=2) + '\n', encoding='utf-8')
    except BaseException:
        shutil.rmtree(out)
        raise
    return len(shots)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('candidate')
    parser.add_argument('output')
    parser.add_argument('--preview-executable', type=Path)
    parser.add_argument('--blink-values', type=float, nargs='+', default=[0, .5, 1])
    args = parser.parse_args()
    try:
        print('C expression-mix poses captured:', capture(args.candidate, args.output, args.preview_executable, args.blink_values))
    except (ValueError, OSError, RuntimeError) as exc:
        print(f'capture: {exc}', file=__import__('sys').stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
