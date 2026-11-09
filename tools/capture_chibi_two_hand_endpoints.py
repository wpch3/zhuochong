#!/usr/bin/env python3
"""Capture all 2^10 two-hand endpoint poses from the actual C renderer.

Uses Gray-code ordering (one parameter change at a time), verifies the ten
reported parameters for every frame, and records hashes of both hand crops.
The 64 representatives do NOT constitute automated visual acceptance.
"""
import argparse
import hashlib
import json
import shutil
import tempfile
from pathlib import Path
from PIL import Image
from capture_chibi_art_review import reset
from capture_chibi_joint_art import image
from capture_chibi_refinement import setup, save_crop
from capture_chibi_visual_matrix import FINGERS, verify_pose
from study_underpaint_sampling import ROOT, request, start, stop


def gray_codes():
    return [i ^ (i >> 1) for i in range(1024)]


def capture(candidate, output):
    root = (ROOT / 'build').resolve()
    candidate = Path(candidate).resolve()
    out = Path(output)
    dest = out.resolve()
    if root not in candidate.parents or root not in dest.parents or dest == candidate or dest in candidate.parents or candidate in dest.parents:
        raise ValueError('separate paths inside build required')
    if out.exists() or out.is_symlink() or not out.parent.is_dir():
        raise ValueError('output must be new')
    if not (candidate / 'extended_report.json').is_file():
        raise ValueError('expected extended study')
    rig_hash = hashlib.sha256((candidate / 'rig.json').read_bytes()).hexdigest()
    executable_hash = hashlib.sha256((ROOT / 'build/zhuochong_preview').read_bytes()).hexdigest()
    out.mkdir()
    names = [f'ParamFinger{side}{finger}' for side in 'LR' for finger in FINGERS]
    boxes = {'L': (325, 625, 410, 710), 'R': (610, 625, 695, 710)}
    # Mapping uses name order above as high-to-low bit order per hand.
    representatives, hashes, variations = {}, [], {'L': 0, 'R': 0}
    try:
        with tempfile.TemporaryDirectory(prefix='two-hand-endpoints-', dir=root) as temp:
            proc, url = start(Path(temp) / 'preview', candidate)
            try:
                setup(url)
                reset(url)
                for name in names:
                    request(url, f'/api/param?id={name}&v=-1')
                previous = 0
                for i, gray in enumerate(gray_codes()):
                    if i:
                        changed = gray ^ previous
                        bit = changed.bit_length() - 1
                        name = names[9 - bit]
                        request(url, f'/api/param?id={name}&v={1 if gray & changed else -1}')
                    previous = gray
                    params = {name: (1 if gray & (1 << (9-j)) else -1) for j, name in enumerate(names)}
                    request(url, '/api/step?n=3')
                    verify_pose(url, params)
                    frame = image(url)
                    entries = {}
                    for side, shift in (('L', 5), ('R', 0)):
                        bits = format((gray >> shift) & 31, '05b')
                        box = boxes[side]
                        crop = Image.fromarray(frame).crop(box).convert('RGBA')
                        digest = hashlib.sha256(crop.tobytes()).hexdigest()
                        key = side + '_' + bits
                        if key not in representatives:
                            representatives[key] = digest
                            for label, bg in (('light', (247,247,247,255)), ('dark', (38,43,49,255))):
                                save_crop(frame, box, 1, out / f'{key}_{label}.png', bg)
                        elif digest != representatives[key]:
                            variations[side] += 1
                            # Keep first contrary frame as evidence, without overwriting.
                            p = out / f'{side}_first_variation.png'
                            if not p.exists():
                                save_crop(frame, box, 1, p, (247,247,247,255))
                        entries[side] = {'bits': bits, 'sha256_rgba': digest}
                    hashes.append({'gray_index': i, 'gray': gray, 'hands': entries})
                    if i and i % 128 == 0:
                        print(f'captured {i}/1024', flush=True)
            finally:
                stop(proc)
        report = {'rig_sha256': rig_hash, 'preview_executable_sha256': executable_hash,
                  'order': names, 'poses': len(hashes), 'samples_per_local_pose': 32,
                  'representatives': representatives, 'crop_hash_variations': variations,
                  'crops': boxes, 'frames': hashes, 'visual_acceptance': 'not evaluated',
                  'note': 'hash variation may reflect other animation; identical hashes do not prove visual quality'}
        (out / 'report.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
        return report
    except BaseException:
        shutil.rmtree(out)
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('candidate')
    parser.add_argument('output')
    args = parser.parse_args()
    try:
        report = capture(args.candidate, args.output)
        print('C two-hand poses:', report['poses'], 'crop variations:', report['crop_hash_variations'])
    except (ValueError, OSError, RuntimeError) as exc:
        print(f'capture: {exc}', file=__import__('sys').stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
