#!/usr/bin/env python3
"""Regression tests for face-backed underlay preservation during head trimming."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from clean_head_backing import preserve_existing_regions  # noqa: E402


class PreserveExistingUnderlayTests(unittest.TestCase):
    def test_keeps_only_existing_body_backed_connected_source_alpha(self):
        keep = np.zeros((8, 10), dtype=bool)
        source = np.zeros((8, 10, 4), dtype=np.uint8)
        body = np.zeros_like(source)
        component = np.zeros((8, 10), dtype=bool)
        roi = np.s_[2:4, 2:6]
        source[roi + (3,)] = 255
        body[roi + (3,)] = 255
        component[roi] = True

        # Each veto demonstrates that the rule cannot invent alpha or rescue
        # pixels outside the main connected sprite component.
        source[2, 2, 3] = 0
        body[2, 3, 3] = 0
        component[3, 4] = False
        original = source.copy()

        preserved = preserve_existing_regions(
            keep, source, body, component, [(2, 2, 6, 4)]
        )

        self.assertEqual(preserved, 5)
        self.assertEqual(int(keep.sum()), 5)
        self.assertFalse(keep[2, 2])
        self.assertFalse(keep[2, 3])
        self.assertFalse(keep[3, 4])
        self.assertFalse(keep[0, 0])
        np.testing.assert_array_equal(source, original)

    def test_rejects_out_of_bounds_region(self):
        keep = np.zeros((4, 4), dtype=bool)
        rgba = np.zeros((4, 4, 4), dtype=np.uint8)
        with self.assertRaises(ValueError):
            preserve_existing_regions(
                keep, rgba, rgba, keep.copy(), [(-1, 0, 2, 2)]
            )

    def test_rejects_mismatched_backing_shape(self):
        keep = np.zeros((4, 4), dtype=bool)
        rgba = np.zeros((4, 4, 4), dtype=np.uint8)
        with self.assertRaises(ValueError):
            preserve_existing_regions(
                keep, rgba, np.zeros((3, 4, 4), dtype=np.uint8), keep.copy(), []
            )


if __name__ == "__main__":
    unittest.main()
