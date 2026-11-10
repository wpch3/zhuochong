#!/usr/bin/env python3
"""Evidence input fingerprint tests; no assertion about visual quality."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import chibi_capture_provenance as provenance


class ProvenanceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'model'
        self.root.mkdir()
        (self.root / 'sprites').mkdir()
        self.sprite = self.root / 'sprites/a.png'
        self.sprite.write_bytes(b'texture')
        self.rig = self.root / 'rig.json'
        self.rig.write_text(json.dumps({'groups': {}, 'parts': [{'file': 'sprites/a.png'}]}))
        self.binary = Path(self.temp.name) / 'preview'
        self.binary.write_bytes(b'binary')

    def test_stable_and_mutations(self):
        before = provenance.snapshot(self.root, self.binary)
        self.assertEqual(before, provenance.verify_unchanged(before, self.root, self.binary))
        self.sprite.write_bytes(b'altered')
        with self.assertRaisesRegex(RuntimeError, 'sprites/a.png'):
            provenance.verify_unchanged(before, self.root, self.binary)
        self.sprite.write_bytes(b'texture')
        self.binary.write_bytes(b'changed binary')
        with self.assertRaisesRegex(RuntimeError, 'preview executable'):
            provenance.verify_unchanged(before, self.root, self.binary)

    def test_escaping_path_and_external_dependencies_rejected(self):
        self.sprite.unlink()
        self.sprite.symlink_to(self.binary)
        with self.assertRaisesRegex(ValueError, 'escaping'):
            provenance.snapshot(self.root, self.binary)
        self.sprite.unlink()
        self.sprite.write_bytes(b'texture')
        for data in ({'groups': {}, 'parts': [{'file': '../bad.png'}]},
                     {'groups': {}, 'parts': [{'file': 'sprites/a.png'}], 'motions': ['motion.json']}):
            self.rig.write_text(json.dumps(data))
            with self.assertRaises(ValueError):
                provenance.snapshot(self.root, self.binary)

    def test_missing_sprite_is_not_silently_omitted(self):
        self.sprite.unlink()
        with self.assertRaises(OSError):
            provenance.snapshot(self.root, self.binary)


if __name__ == '__main__':
    unittest.main()
