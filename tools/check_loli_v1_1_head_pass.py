#!/usr/bin/env python3
"""Validate Loli v1.1 head-pass file structure and registered reconstruction."""
from __future__ import annotations

import json
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "characters/xiaoxun/design/loli_live2d_v1/authoring_v1_1/head_pass_03"
EXPECTED = {"Whale_Clip", "Brow_L", "Brow_R", "EyeWhite_L", "EyeWhite_R", "EyeBall_L", "EyeBall_R", "Eyelash_L", "Eyelash_R", "Nose", "Mouth_Closed"}


def main() -> int:
    errors: list[str] = []
    manifest = json.loads((OUT / "layer_manifest.json").read_text(encoding="utf-8"))
    if manifest.get("status") != "WIP head/face cutout pass based on selected v1.1; not finished art, not PSD, not Cubism":
        errors.append("WIP/non-Cubism status missing")
    parts = manifest.get("parts", [])
    if {p.get("name") for p in parts} != EXPECTED or len(parts) != 11:
        errors.append("expected 11 v1.1 semantic face/accessory cutouts")
    for part in parts:
        file = OUT / part["file"]
        if not file.is_file():
            errors.append(f"missing layer: {file.name}")
            continue
        im = Image.open(file).convert("RGBA")
        if im.size != (1280, 1920):
            errors.append(f"wrong canvas on {file.name}: {im.size}")
        bbox = im.getchannel("A").getbbox()
        if bbox is None or bbox[2] - bbox[0] > 150 or bbox[3] - bbox[1] > 130:
            errors.append(f"unexpected cutout bounds on {file.name}: {bbox}")
        pixel_count = int(np.count_nonzero(np.asarray(im.getchannel("A")) > 0))
        limits = {"Nose": 60, "Mouth_Closed": 250, "Brow_L": 1000, "Brow_R": 1000}
        if part["name"] in limits and pixel_count > limits[part["name"]]:
            errors.append(f"selection unexpectedly broad on {file.name}: {pixel_count} pixels")
    # The three semantic eye layers must not double-own the same source pixels.
    for side in ("L", "R"):
        eye_masks = []
        for prefix in ("EyeWhite", "EyeBall", "Eyelash"):
            layer = Image.open(OUT / f"{prefix}_{side}.png").convert("RGBA")
            eye_masks.append(np.asarray(layer.getchannel("A")) > 0)
        for i in range(len(eye_masks)):
            for j in range(i + 1, len(eye_masks)):
                if np.any(eye_masks[i] & eye_masks[j]):
                    errors.append(f"overlapping semantic eye-layer ownership for side {side}")
    ora = OUT / manifest["ora_file"]
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
        if len(layers) != 13 or not EXPECTED.issubset(layer_names):
            errors.append(f"ORA layer list mismatch: {len(layers)} layers")
        merged = np.asarray(Image.open(z.open("mergedimage.png")).convert("RGBA"))
    composite = np.asarray(Image.open(OUT / "head_pass_composite.png").convert("RGBA"))
    if not np.array_equal(merged, composite):
        errors.append("ORA merged image differs from the review composite")
    diff = np.asarray(Image.open(OUT / "reconstruction_diff.png").convert("RGBA"))
    changed = int(np.count_nonzero(np.any(diff[..., :3] > 2, axis=2)))
    max_diff = int(diff[..., :3].max())
    qa = manifest.get("reconstruction_check", {})
    if changed != qa.get("pixels_changed_over_2_rgb_levels") or max_diff != qa.get("max_channel_difference"):
        errors.append("reconstruction QA metrics disagree with diff image")
    if changed > 300 or max_diff > 64:
        errors.append(f"reconstruction delta exceeds first-pass bound: {changed} px, max {max_diff}")
    if errors:
        for e in errors:
            print("FAIL:", e)
        return 1
    print(f"PASS: 11 nonempty semantic facial cutouts; 13-layer ORA and preview match; reconstruction delta {changed}px / max RGB {max_diff}")
    print("LIMIT: only face/clip cutouts; algorithmic underpaint; not artistic approval or Cubism validation")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
