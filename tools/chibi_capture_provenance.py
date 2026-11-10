#!/usr/bin/env python3
"""Fingerprint the limited self-contained zproj-v1 inputs to a C capture.

This is not a reproducible-build claim: config, libraries, fonts, environment,
transient mutations and other preview dependencies are not fully captured.
"""
import hashlib
from pathlib import Path

from zrig_project import MAX_PNG, MAX_RIG, MAX_TOTAL, decode_json, image_paths


def digest(data):
    return hashlib.sha256(data).hexdigest()


def snapshot(candidate, executable):
    root = Path(candidate).resolve(strict=True)
    rig_path = root / 'rig.json'
    if rig_path.is_symlink() or not rig_path.is_file() or rig_path.stat().st_size > MAX_RIG:
        raise ValueError('invalid rig file')
    rig_bytes = rig_path.read_bytes()
    if len(rig_bytes) > MAX_RIG:
        raise ValueError('oversized rig file')
    rig = decode_json(rig_bytes)
    files = {'rig.json': {'size': len(rig_bytes), 'sha256': digest(rig_bytes)}}
    total = len(rig_bytes)
    for name in sorted(image_paths(rig)):
        path = root / name
        resolved = path.resolve(strict=True)
        if not resolved.is_relative_to(root) or not resolved.is_file() or resolved.stat().st_size > MAX_PNG:
            raise ValueError('missing, escaping or oversized sprite: ' + name)
        data = resolved.read_bytes()
        total += len(data)
        if len(data) > MAX_PNG or total > MAX_TOTAL:
            raise ValueError('capture inputs exceed size limits')
        files[name] = {'size': len(data), 'sha256': digest(data)}
    binary = Path(executable).resolve(strict=True)
    if not binary.is_file():
        raise ValueError('invalid preview executable')
    binary_hash = hashlib.sha256()
    with binary.open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            binary_hash.update(block)
    return {'rig_sha256': files['rig.json']['sha256'], 'preview_executable_sha256': binary_hash.hexdigest(),
            'referenced_files': files}


def verify_unchanged(before, candidate, executable):
    after = snapshot(candidate, executable)
    if before != after:
        changed = sorted(set(before['referenced_files']) | set(after['referenced_files']))
        changed = [name for name in changed if before['referenced_files'].get(name) != after['referenced_files'].get(name)]
        if before['preview_executable_sha256'] != after['preview_executable_sha256']:
            changed.append('preview executable')
        raise RuntimeError('capture inputs changed: ' + ', '.join(changed))
    return after
