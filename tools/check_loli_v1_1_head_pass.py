#!/usr/bin/env python3
"""Validate Loli v1.1 WIP ORA structure, semantic masks, and static assembly."""
from __future__ import annotations

import argparse
import json
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "characters/xiaoxun/design/loli_live2d_v1/authoring_v1_1"
FACE_EXPECTED = {"Whale_Clip", "Brow_L", "Brow_R", "EyeWhite_L", "EyeWhite_R", "EyeBall_L", "EyeBall_R", "Eyelash_L", "Eyelash_R", "Nose", "Mouth_Closed"}
SLEEVE_EXPECTED = {"JacketSleeve_Teal_L", "JacketSleeve_Teal_R"}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pass04", action="store_true", help="check the expanded head + visible teal sleeve stack")
    args = parser.parse_args()
    out = BASE / ("authoring_pass_04" if args.pass04 else "head_pass_03")
    expected = FACE_EXPECTED | (SLEEVE_EXPECTED if args.pass04 else set())
    errors: list[str] = []
    manifest = json.loads((out / "layer_manifest.json").read_text(encoding="utf-8"))
    if manifest.get("status") != "WIP source-visible cutout stack based on selected v1.1; not finished art, not PSD, not Cubism":
        errors.append("WIP/non-Cubism status missing")
    parts = manifest.get("parts", [])
    if {p.get("name") for p in parts} != expected or len(parts) != len(expected):
        errors.append(f"expected {len(expected)} named v1.1 source-visible cutouts")
    loaded: dict[str, np.ndarray] = {}
    for part in parts:
        name = part["name"]
        file = out / part["file"]
        if not file.is_file():
            errors.append(f"missing layer: {file.name}")
            continue
        im = Image.open(file).convert("RGBA")
        if im.size != (1280, 1920):
            errors.append(f"wrong canvas on {file.name}: {im.size}")
        alpha = np.asarray(im.getchannel("A"))
        loaded[name] = alpha > 0
        bbox = im.getchannel("A").getbbox()
        if bbox is None:
            errors.append(f"empty cutout: {file.name}")
            continue
        width, height = bbox[2] - bbox[0], bbox[3] - bbox[1]
        if name.startswith("JacketSleeve_Teal_"):
            if width > 230 or height > 450:
                errors.append(f"unexpected sleeve ROI bounds on {file.name}: {bbox}")
            if np.count_nonzero(alpha) < 5000:
                errors.append(f"sleeve mask unexpectedly small: {file.name}")
        elif width > 150 or height > 130:
            errors.append(f"unexpected facial cutout bounds on {file.name}: {bbox}")
        pixel_count = int(np.count_nonzero(alpha))
        limits = {"Nose": 60, "Mouth_Closed": 250, "Brow_L": 1000, "Brow_R": 1000}
        if name in limits and pixel_count > limits[name]:
            errors.append(f"selection unexpectedly broad on {file.name}: {pixel_count} pixels")

    # The three semantic eye layers must not double-own the same source pixels.
    for side in ("L", "R"):
        eye_masks = [loaded.get(f"{prefix}_{side}") for prefix in ("EyeWhite", "EyeBall", "Eyelash")]
        if any(mask is None for mask in eye_masks):
            continue
        for i in range(len(eye_masks)):
            for j in range(i + 1, len(eye_masks)):
                if np.any(eye_masks[i] & eye_masks[j]):
                    errors.append(f"overlapping semantic eye-layer ownership for side {side}")

    ora = out / manifest["ora_file"]
    with zipfile.ZipFile(ora) as z:
        names = z.namelist()
        if not names or names[0] != "mimetype" or z.getinfo("mimetype").compress_type != zipfile.ZIP_STORED:
            errors.append("invalid ORA mimetype ordering/compression")
        if z.read("mimetype") != b"image/openraster":
            errors.append("invalid ORA mimetype value")
        root = ET.fromstring(z.read("stack.xml"))
        if (root.get("w"), root.get("h")) != ("1280", "1920"):
            errors.append("ORA canvas mismatch")
        layers = root.findall(".//layer")
        layer_names = {x.get("name", "") for x in layers}
        if len(layers) != len(expected) + 2 or not expected.issubset(layer_names):
            errors.append(f"ORA layer list mismatch: {len(layers)} layers")
        merged = np.asarray(Image.open(z.open("mergedimage.png")).convert("RGBA"))
    composite = np.asarray(Image.open(out / "head_pass_composite.png").convert("RGBA"))
    if not np.array_equal(merged, composite):
        errors.append("ORA merged image differs from the review composite")
    diff = np.asarray(Image.open(out / "reconstruction_diff.png").convert("RGBA"))
    changed = int(np.count_nonzero(np.any(diff[..., :3] > 2, axis=2)))
    max_diff = int(diff[..., :3].max())
    qa = manifest.get("reconstruction_check", {})
    if changed != qa.get("pixels_changed_over_2_rgb_levels") or max_diff != qa.get("max_channel_difference"):
        errors.append("reconstruction QA metrics disagree with diff image")
    if changed > 300 or max_diff > 64:
        errors.append(f"reconstruction delta exceeds WIP bound: {changed} px, max {max_diff}")
    if errors:
        for error in errors:
            print("FAIL:", error)
        return 1
    print(f"PASS: {len(expected)} nonempty v1.1 cutouts; {len(expected)+2}-layer ORA and preview match; static delta {changed}px / max RGB {max_diff}")
    print("LIMIT: registered source-pixel masks and algorithmic underpaint only; not art approval or Cubism validation")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
