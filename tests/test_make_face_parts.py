#!/usr/bin/env python3
"""Regression checks for the optional expression-image extraction pipeline.

Run in the image-tools environment (Pillow + NumPy):
  PYTHONPATH=<image-env-site-packages> python3 -m unittest tests.test_make_face_parts
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from make_face_parts import (  # noqa: E402
    CANON,
    REF,
    align_to_canon,
    detect_eyes,
    fit_mouth,
    key_out,
    mask_eye_patch,
    warp_to_canon,
    magenta_residue,
    save_candidate_pair,
)


class FacePartAlignmentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        src = ROOT / "characters/xiaoxun/parts_src/expressions_a"
        cls.paths = sorted(src.glob("*.png"))
        cls.paths.append(ROOT / "characters/xiaoxun/parts_src/expressions/smile.png")

    def test_all_nine_reference_faces_align_to_body_eye_scale(self):
        self.assertEqual(len(self.paths), 9)
        for path in self.paths:
            with self.subTest(expression=path.stem):
                with Image.open(path) as source:
                    keyed, _ = key_out(source.convert("RGB"), tol=60, despill=1)
                rgba = np.asarray(keyed)
                lc, rc, method = detect_eyes(rgba)
                expected = "face_geometry" if path.stem in {"closed", "happy"} else "iris"
                self.assertEqual(method, expected)
                self.assertIsNotNone(lc)
                self.assertIsNotNone(rc)
                scale, sx, sy = align_to_canon(rgba, lc, rc, None)
                self.assertGreater(scale, 0.37)
                self.assertLess(scale, 0.45)
                target_y = CANON["eye_mid_y"] - 5 if method == "face_geometry" else CANON["eye_mid_y"]
                aligned = warp_to_canon(rgba, scale, sx, sy, target_y=target_y)
                a = np.asarray(aligned)
                self.assertGreater(a.shape[1], CANON["eye_mid_x"] + CANON["eye_dist"])
                # The face anchors must map to the canonical iris/eyelid line, not the blue hairclip.
                eye_mid_y = (lc[1] + rc[1]) / 2.0
                mapped_mid_y = (eye_mid_y - sy) * scale + target_y
                self.assertLess(abs(mapped_mid_y - target_y), 1.0)
                self.assertGreater(float((a[..., 3] > 0).mean()), 0.05)

    def test_eye_patch_removes_rectangular_corners(self):
        source = Image.new("RGBA", (75, 52), (240, 210, 190, 255))
        ImageDraw.Draw(source).ellipse((9, 12, 66, 43), fill=(20, 30, 40, 255))
        masked = mask_eye_patch(source)
        alpha = np.asarray(masked.getchannel("A"))
        self.assertEqual(masked.size, source.size)
        self.assertEqual(int(alpha[0, 0]), 0)
        self.assertEqual(int(alpha[-1, -1]), 0)
        self.assertGreater(int(alpha[26, 37]), 200)

    def test_mouth_panel_is_fixed_size_soft_edged_and_preserves_keyed_transparency(self):
        source = Image.new("RGBA", (64, 36), (245, 215, 195, 255))
        from PIL import ImageDraw
        ImageDraw.Draw(source).ellipse((17, 5, 47, 31), fill=(110, 30, 40, 255))
        panel = fit_mouth(source)
        x0, y0, x1, y1 = REF["mouth_box"]
        self.assertEqual(panel.size, (x1 - x0, y1 - y0))
        alpha = np.asarray(panel.getchannel("A"))
        self.assertLess(int(alpha[0, 0]), 32)
        self.assertGreater(int(alpha[panel.height // 2, panel.width // 2]), 200)


class CandidateAssetPackageTests(unittest.TestCase):
    def test_save_candidate_pair_generates_true_2x_alpha_sprite(self):
        from tempfile import TemporaryDirectory

        with TemporaryDirectory() as directory:
            path = Path(directory) / "test.png"
            source = Image.new("RGBA", (75, 52), (20, 40, 60, 128))
            save_candidate_pair(source, str(path))
            with Image.open(path) as base, Image.open(path.with_name("test@2x.png")) as hires:
                self.assertEqual(base.size, (75, 52))
                self.assertEqual(hires.size, (150, 104))
                self.assertEqual(hires.mode, "RGBA")
                self.assertEqual(hires.getpixel((50, 50))[3], 128)

    def test_rig_candidate_anchors_reproject_to_original_teen_eyes(self):
        import json

        form = ROOT / "characters/xiaoxun/forms/teen"
        pack = form / "sprites/expression_parts_a"
        rig = json.loads((form / "rig.json").read_text(encoding="utf-8"))
        parts = {part["id"]: part for part in rig["parts"]}

        def center(part_id, kind):
            part = parts[part_id]
            with Image.open(form / part["file"]) as image:
                rgba = np.asarray(image.convert("RGBA"))
            r, g, b = rgba[..., :3].astype(np.int16).transpose(2, 0, 1)
            alpha = rgba[..., 3] > 32
            if kind == "blue":
                mask = alpha & (b - r > 42) & (b - g > 5) & (r < 150) & (b > 90)
            else:
                mask = alpha & (r < 120) & (g < 130) & (b < 150)
            ys, xs = np.where(mask)
            self.assertGreater(len(xs), 0, part_id)
            x = part["pos"][0] + float(xs.mean()) * part["scale"]
            y = part["pos"][1] + float(ys.mean()) * part["scale"]
            return x, y

        original = {side: center(f"eye_{side}_ball", "blue") for side in ("l", "r")}
        scale = (original["r"][0] - original["l"][0]) / CANON["eye_dist"]
        canonical_x = {
            "l": CANON["eye_mid_x"] - CANON["eye_dist"] / 2,
            "r": CANON["eye_mid_x"] + CANON["eye_dist"] / 2,
        }
        source_origins = {"l": REF["eye_left_box"][0] - 2,
                          "r": REF["eye_right_box"][0] - 2}
        source_y = REF["eye_left_box"][1] - 2

        for side in ("l", "r"):
            for mood in ("smile", "shy", "angry", "sad", "surprised", "thinking", "sleepy"):
                part = parts[f"expr_eye_{side}_{mood}"]
                expected = (
                    original[side][0] - (canonical_x[side] - source_origins[side]) * scale,
                    original[side][1] - (CANON["eye_mid_y"] - source_y) * scale,
                )
                self.assertAlmostEqual(part["pos"][0], expected[0], delta=0.01, msg=part["id"])
                self.assertAlmostEqual(part["pos"][1], expected[1], delta=0.01, msg=part["id"])
                self.assertEqual(part["anchor"], [0, 0], part["id"])
                self.assertAlmostEqual(part["scale_1x"], scale, delta=1e-5, msg=part["id"])
                self.assertAlmostEqual(part["scale"], scale / 2, delta=1e-5, msg=part["id"])

            happy = parts[f"expr_eye_{side}_happy"]
            smile_center = center(f"eye_{side}_smile", "dark")
            expected_happy_y = smile_center[1] - (199.0 - source_y) * scale
            self.assertAlmostEqual(happy["pos"][0], original[side][0] -
                                   (canonical_x[side] - source_origins[side]) * scale,
                                   delta=0.01, msg=happy["id"])
            self.assertAlmostEqual(happy["pos"][1], expected_happy_y, delta=0.01, msg=happy["id"])
            self.assertEqual(happy["anchor"], [0, 0], happy["id"])
            self.assertAlmostEqual(happy["scale_1x"], scale, delta=1e-5, msg=happy["id"])
            self.assertAlmostEqual(happy["scale"], scale / 2, delta=1e-5, msg=happy["id"])

        for side in ("l", "r"):
            calm_center = center(f"expr_eye_{side}_calm", "blue")
            self.assertLessEqual(abs(calm_center[0] - original[side][0]), 2.5, side)
            self.assertLessEqual(abs(calm_center[1] - original[side][1]), 2.5, side)

    def test_candidate_package_matches_report_and_acceptance_bounds(self):
        import json

        pack = ROOT / "characters/xiaoxun/forms/teen/sprites/expression_parts_a"
        report_path = pack / "face_parts_report.json"
        self.assertTrue(report_path.is_file())
        report = json.loads(report_path.read_text(encoding="utf-8"))
        self.assertEqual(report.get("errors"), [])
        items = {item["name"]: item for item in report.get("items", [])}
        required_moods = {
            "calm", "smile", "happy", "shy", "angry", "sad",
            "surprised", "thinking", "sleepy",
        }
        self.assertTrue(required_moods.issubset(items))
        self.assertIn("closed", items)  # additional blink candidate, not a tenth mood
        self.assertEqual(len(items), 10)

        seen = set()
        for mood, item in items.items():
            with self.subTest(mood=mood):
                self.assertEqual(len(item.get("parts", [])), 3)
                for part in item["parts"]:
                    name = part["file"]
                    seen.add(name)
                    path = pack / name
                    self.assertTrue(path.is_file(), name)
                    with Image.open(path) as image:
                        image.load()
                        self.assertEqual(image.mode, "RGBA", name)
                        expected = (75, 52) if name.startswith("eye_") else (44, 28)
                        self.assertEqual(image.size, expected, name)
                        self.assertEqual(list(image.size), part["size"], name)
                        residue = magenta_residue(np.asarray(image))
                    self.assertLess(residue, 200, name)
                    self.assertEqual(residue, part["magenta_residue"], name)
                    hires_path = pack / (Path(name).stem + "@2x.png")
                    self.assertTrue(hires_path.is_file(), str(hires_path))
                    with Image.open(hires_path) as hires:
                        self.assertEqual(hires.mode, "RGBA")
                        self.assertEqual(hires.size, (expected[0] * 2, expected[1] * 2))
        self.assertEqual(len(seen), 30)
        self.assertTrue((pack / "preview_contact_sheet.png").is_file())



if __name__ == "__main__":
    unittest.main()
