#!/usr/bin/env python3
"""Create, verify and unpack a small self-contained zrig project (.zproj).

v1 supports rig.json + its PNG part files only. It deliberately rejects
external motions/expressions instead of producing an incomplete project.
Checksums detect corruption, not malicious authors. No Cubism file support.
"""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import shutil
import struct
import sys
import zipfile

MAX_FILES = 512
MAX_TOTAL = 64 * 1024 * 1024
MAX_RIG = 4 * 1024 * 1024
MAX_PNG = 16 * 1024 * 1024
MAX_MANIFEST = 512 * 1024
MAX_ARCHIVE = 80 * 1024 * 1024


def safe_path(value):
    if not isinstance(value, str) or not value or len(value) > 240 or '\\' in value or ':' in value:
        raise ValueError('invalid relative path')
    if any(ord(c) < 32 or c in '<>"|?*' for c in value):
        raise ValueError('invalid character in path')
    path = PurePosixPath(value)
    components = value.split('/')
    if path.is_absolute() or any(p in ('', '.', '..') or p.endswith((' ', '.')) for p in components) or str(path) != value:
        raise ValueError('invalid relative path: ' + value)
    reserved = {'CON', 'PRN', 'AUX', 'NUL'} | {f'{x}{n}' for x in ('COM', 'LPT') for n in range(1, 10)}
    if any(p.split('.')[0].upper() in reserved for p in components):
        raise ValueError('reserved Windows path: ' + value)
    return value


def decode_json(data):
    return json.loads(data.decode('utf-8'), parse_constant=lambda s: (_ for _ in ()).throw(ValueError('non-finite JSON number')))


def image_paths(rig):
    if not isinstance(rig, dict) or not isinstance(rig.get('parts'), list) or not isinstance(rig.get('groups'), dict):
        raise ValueError('rig must contain parts and groups')
    if not rig['parts'] or len(rig['parts']) > MAX_FILES - 2:
        raise ValueError('parts count is out of bounds')
    if rig.get('motions') or rig.get('expression_files'):
        raise ValueError('v1 does not support external motions or expression files')
    files = set()
    for part in rig['parts']:
        if not isinstance(part, dict):
            raise ValueError('invalid part')
        path = safe_path(part.get('file'))
        if not path.startswith('sprites/') or not path.lower().endswith('.png'):
            raise ValueError('v1 supports only PNG files under sprites/')
        files.add(path)
    if len({p.casefold() for p in files}) != len(files):
        raise ValueError('case-insensitive sprite path collision')
    return files


def check_png(data):
    if len(data) < 33 or len(data) > MAX_PNG or data[:8] != b'\x89PNG\r\n\x1a\n' or data[12:16] != b'IHDR':
        raise ValueError('invalid or oversized PNG')
    if struct.unpack('>I', data[8:12])[0] != 13:
        raise ValueError('invalid PNG IHDR length')
    w, h = struct.unpack('>II', data[16:24])
    if not (0 < w <= 8192 and 0 < h <= 8192):
        raise ValueError('PNG dimensions out of bounds')


def digest(data):
    return hashlib.sha256(data).hexdigest()


def validate_files(files):
    if 'rig.json' not in files or len(files['rig.json']) > MAX_RIG:
        raise ValueError('missing or oversized rig.json')
    rig = decode_json(files['rig.json'])
    expected = image_paths(rig) | {'rig.json'}
    if set(files) != expected:
        raise ValueError('project files do not match rig references')
    if sum(len(v) for v in files.values()) > MAX_TOTAL:
        raise ValueError('project exceeds uncompressed size limit')
    for path in expected - {'rig.json'}:
        check_png(files[path])
    return rig


def create(rig_path, output):
    rig_path, output = Path(rig_path), Path(output)
    if output.exists():
        raise ValueError('output already exists')
    if rig_path.name != 'rig.json':
        raise ValueError('source must be named rig.json')
    if rig_path.is_symlink() or not rig_path.is_file() or rig_path.stat().st_size > MAX_RIG:
        raise ValueError('invalid rig file')
    root = rig_path.parent.resolve()
    rig_bytes = rig_path.read_bytes()
    rig = decode_json(rig_bytes)
    files = {'rig.json': rig_bytes}
    total = len(rig_bytes)
    for path in sorted(image_paths(rig)):
        src = root / path
        resolved = src.resolve(strict=True)
        if not resolved.is_relative_to(root) or not resolved.is_file() or src.stat().st_size > MAX_PNG:
            raise ValueError('missing, escaping or oversized asset: ' + path)
        total += src.stat().st_size
        if total > MAX_TOTAL:
            raise ValueError('project exceeds uncompressed size limit')
        files[path] = src.read_bytes()
        if sum(len(data) for data in files.values()) > MAX_TOTAL:
            raise ValueError('project exceeds uncompressed size limit')
    validate_files(files)
    manifest = {'schema': 'zrig-project', 'version': 1,
                'files': [{'path': p, 'size': len(files[p]), 'sha256': digest(files[p])} for p in sorted(files)]}
    manifest_bytes = (json.dumps(manifest, ensure_ascii=False, indent=2) + '\n').encode('utf-8')
    output.parent.mkdir(parents=True, exist_ok=True)
    # Use exclusive creation so an existing project cannot be silently overwritten.
    with output.open('xb') as stream:
        try:
            with zipfile.ZipFile(stream, 'w', compression=zipfile.ZIP_DEFLATED) as z:
                z.writestr('project.json', manifest_bytes)
                for path in sorted(files): z.writestr(path, files[path])
        except BaseException:
            stream.close()
            output.unlink(missing_ok=True)
            raise
    return manifest


def verify(archive):
    archive = Path(archive)
    if not archive.is_file() or archive.stat().st_size > MAX_ARCHIVE:
        raise ValueError('missing or oversized archive')
    with zipfile.ZipFile(archive) as z:
        infos = z.infolist()
        if not infos or len(infos) > MAX_FILES or sum(i.file_size for i in infos) > MAX_TOTAL + MAX_MANIFEST:
            raise ValueError('archive size/count limit exceeded')
        names = [safe_path(i.filename) for i in infos]
        if len(set(names)) != len(names) or len({n.casefold() for n in names}) != len(names):
            raise ValueError('duplicate archive paths')
        for i in infos:
            mode = (i.external_attr >> 16) & 0o170000
            if i.is_dir() or i.flag_bits & 1 or mode == 0o120000:
                raise ValueError('directories, encrypted files and symlinks are not supported')
            if i.compress_type not in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED):
                raise ValueError('unsupported archive compression')
            limit = MAX_MANIFEST if i.filename == 'project.json' else MAX_RIG if i.filename == 'rig.json' else MAX_PNG
            if i.file_size > limit:
                raise ValueError('archive member too large: ' + i.filename)
        if 'project.json' not in names:
            raise ValueError('missing project.json')
        manifest = decode_json(z.read('project.json'))
        if not isinstance(manifest, dict) or manifest.get('schema') != 'zrig-project' or manifest.get('version') != 1 or not isinstance(manifest.get('files'), list):
            raise ValueError('unsupported project manifest')
        entries = manifest['files']
        paths = [safe_path(x.get('path')) for x in entries if isinstance(x, dict)]
        if len(paths) != len(entries) or len(set(paths)) != len(paths) or set(paths) != set(names) - {'project.json'}:
            raise ValueError('manifest paths do not match archive')
        files = {}
        for entry, path in zip(entries, paths):
            data = z.read(path)
            if entry.get('size') != len(data) or entry.get('sha256') != digest(data):
                raise ValueError('size or checksum mismatch: ' + path)
            files[path] = data
        validate_files(files)
        return manifest, files


def unpack(archive, output):
    _, files = verify(archive)
    output = Path(output)
    # mkdir is atomic; do not overwrite even an empty directory.
    output.mkdir(parents=False, exist_ok=False)
    try:
        for path, data in files.items():
            dest = output / path
            dest.parent.mkdir(parents=True, exist_ok=True)
            with dest.open('xb') as f: f.write(data)
    except BaseException:
        shutil.rmtree(output)
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    create_cmd = sub.add_parser('create'); create_cmd.add_argument('rig'); create_cmd.add_argument('output')
    verify_cmd = sub.add_parser('verify'); verify_cmd.add_argument('archive')
    unpack_cmd = sub.add_parser('unpack'); unpack_cmd.add_argument('archive'); unpack_cmd.add_argument('output')
    args = parser.parse_args()
    try:
        if args.command == 'create':
            manifest = create(args.rig, args.output)
            print('Created:', args.output, 'files:', len(manifest['files']))
        elif args.command == 'verify':
            manifest, _ = verify(args.archive)
            print('Verified:', args.archive, 'files:', len(manifest['files']))
        else:
            unpack(args.archive, args.output)
            print('Unpacked:', args.output)
    except (OSError, ValueError, KeyError, TypeError, zipfile.BadZipFile, UnicodeError) as error:
        print('Project error:', error, file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
