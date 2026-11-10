#!/usr/bin/env python3
"""Project archive roundtrip, hostile input, and C-engine integration."""
import json
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.error
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import zrig_project as project


class ProjectTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='zrig-project-test-')
        self.root = Path(self.temp.name)
        self.source = ROOT / 'experiments/live2d_chibi_human_blackline'
        self.archive = self.root / 'model.zproj'
        project.create(self.source / 'rig.json', self.archive)

    def tearDown(self):
        self.temp.cleanup()

    def test_roundtrip_and_c_engine(self):
        manifest, files = project.verify(self.archive)
        self.assertEqual(len(manifest['files']), 10)
        saved_manifest, saved_files = project.verify(self.source / 'model.zproj')
        self.assertEqual(saved_manifest, manifest, 'checked-in project manifest is stale')
        self.assertEqual(saved_files, files, 'checked-in project assets are stale')
        target = self.root / 'unpacked'
        project.unpack(self.archive, target)
        for path, contents in files.items():
            self.assertEqual((target / path).read_bytes(), contents)
        with self.assertRaises(FileExistsError):
            project.unpack(self.archive, target)
        with self.assertRaises(ValueError):
            project.create(self.source / 'rig.json', self.archive)
        self.assertTrue(self.archive.exists())

        sandbox = self.root / 'runtime'
        shutil.copytree(ROOT / 'config', sandbox / 'config')
        pet = sandbox / 'config/pet.json'
        cfg = pet.read_text(encoding='utf-8')
        self.assertIn('"form": "teen"', cfg)
        pet.write_text(cfg.replace('"form": "teen"', '"form": "project_test"', 1), encoding='utf-8')
        (sandbox / 'schemas').symlink_to(ROOT / 'schemas', target_is_directory=True)
        char = sandbox / 'characters/xiaoxun'
        char.mkdir(parents=True)
        for p in (ROOT / 'characters/xiaoxun').iterdir():
            if p.name not in ('forms', 'forms.json'):
                (char / p.name).symlink_to(p, target_is_directory=p.is_dir())
        (char / 'forms').mkdir()
        (char / 'forms/project_test').symlink_to(target, target_is_directory=True)
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0)); port = sock.getsockname()[1]
        proc = subprocess.Popen([str(ROOT / 'build/zhuochong_preview'), '--root', str(sandbox),
                                 '--bind', '127.0.0.1', '--port', str(port)],
                                cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        base = f'http://127.0.0.1:{port}'
        try:
            for _ in range(100):
                if proc.poll() is not None:
                    self.fail('C preview exited: ' + proc.stderr.read().decode(errors='replace'))
                try:
                    with urllib.request.urlopen(base + '/api/info.json', timeout=5) as r: info = json.load(r)
                    break
                except (OSError, urllib.error.URLError):
                    time.sleep(.1)
            else:
                self.fail('preview startup timeout')
            self.assertEqual(info['form'], 'project_test')
            with urllib.request.urlopen(base + '/api/frame.png', timeout=10) as r:
                self.assertEqual(r.read(8), b'\x89PNG\r\n\x1a\n')
        finally:
            proc.terminate()
            try: proc.wait(timeout=5)
            except subprocess.TimeoutExpired: proc.kill(); proc.wait()
            proc.stderr.close()

    def test_path_rejections(self):
        for path in ('../bad', '/etc/x', 'sprites/../../x', 'sprites\\evil.png', 'sprites/CON.png', 'sprites/a?.png', 'sprites/a. '):
            with self.subTest(path=path), self.assertRaises(ValueError): project.safe_path(path)
        for path in ('sprites/a.png', 'sprites/二号.png'): self.assertEqual(project.safe_path(path), path)

    def test_tamper_and_extra_file(self):
        with zipfile.ZipFile(self.archive) as z: files = {name: z.read(name) for name in z.namelist()}
        p = 'sprites/body.png'; files[p] = files[p][:-5] + b'12345'
        bad = self.root / 'bad.zproj'
        with zipfile.ZipFile(bad, 'w') as z:
            for name, data in files.items(): z.writestr(name, data)
        with self.assertRaisesRegex(ValueError, 'checksum'): project.verify(bad)
        escaped = self.root / 'escape.zproj'
        with zipfile.ZipFile(escaped, 'w') as z:
            for name, data in files.items(): z.writestr(name, data)
            z.writestr('../escape', b'no')
        with self.assertRaises(ValueError): project.unpack(escaped, self.root / 'should-not-exist')
        self.assertFalse((self.root / 'should-not-exist').exists())

    def test_source_symlink_escape_and_external_motion_rejected(self):
        folder = self.root / 'source'; folder.mkdir(); (folder / 'sprites').mkdir()
        (folder / 'sprites/a.png').symlink_to(self.source / 'sprites/body.png')
        rig = {'groups': {}, 'parts': [{'id':'p', 'file':'sprites/a.png'}]}
        (folder / 'rig.json').write_text(json.dumps(rig), encoding='utf-8')
        with self.assertRaises(ValueError): project.create(folder / 'rig.json', self.root / 'outside.zproj')
        self.assertFalse((self.root / 'outside.zproj').exists())
        rig['motions'] = [{'file':'../../motion.json'}]
        with self.assertRaisesRegex(ValueError, 'external'): project.image_paths(rig)

    def test_duplicate_paths_rejected(self):
        bad = self.root / 'duplicates.zproj'
        with zipfile.ZipFile(bad, 'w') as z:
            z.writestr('project.json', '{}'); z.writestr('rig.json', '{}'); z.writestr('RIG.JSON', '{}')
        with self.assertRaisesRegex(ValueError, 'duplicate'): project.verify(bad)


if __name__ == '__main__':
    unittest.main(verbosity=2)
