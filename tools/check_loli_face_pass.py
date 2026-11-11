#!/usr/bin/env python3
"""Structural and reconstruction checks for Loli face cutout pass 01."""
from __future__ import annotations

import json
import sys
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

import numpy as np
from PIL import Image, ImageChops

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "characters/xiaoxun/design/loli_live2d_v1/cubism_source/face_pass_01"
EXPECTED = {"Whale_Clip", "Brow_L", "Brow_R", "Eye_L", "Eye_R", "Nose", "Mouth_Closed"}


def main() -> int:
    errors: list[str] = []
    manifest_path = OUT / "layer_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("status") != "WIP face cutout pass; not PSD; not Cubism model; not for runtime":
        errors.append("WIP/non-Cubism status missing")
    if {x["name"] for x in manifest.get("parts", [])} != EXPECTED:
        errors.append("layer set differs from seven named face cutouts")
    for part in manifest.get("parts", []):
        p = OUT / part["file"]
        if not p.is_file():
            errors.append(f"missing layer file: {p.name}")
            continue
        with Image.open(p) as im:
            if im.size != (848, 1360) or im.mode != "RGBA":
                errors.append(f"bad size/mode for {p.name}: {im.size} {im.mode}")
            if im.getchannel("A").getbbox() is None:
                errors.append(f"empty cutout layer: {p.name}")
    ora_path = OUT / "xiaoxun_loli_face_pass_01.ora"
    with zipfile.ZipFile(ora_path) as z:
        names = z.namelist()
        if not names or names[0] != "mimetype" or z.getinfo("mimetype").compress_type != zipfile.ZIP_STORED:
            errors.append("ORA mimetype entry is not first/stored")
        if z.read("mimetype") != b"image/openraster":
            errors.append("ORA mimetype invalid")
        root = ET.fromstring(z.read("stack.xml"))
        if (root.get("w"), root.get("h")) != ("848", "1360"):
            errors.append("ORA canvas is not 848x1360")
        all_layers = root.findall(".//layer")
        names_in_ora = {x.get("name", "") for x in all_layers}
        if len(all_layers) != 9:
            errors.append(f"expected 9 ORA layers, got {len(all_layers)}")
        if not any("hidden" in x.get("name", "") and x.get("visibility") == "hidden" for x in all_layers):
            errors.append("hidden locked-guide reference layer missing")
        if not EXPECTED.issubset(names_in_ora):
            errors.append("one or more face-part layers missing from ORA")
        merged = Image.open(z.open("mergedimage.png")).convert("RGBA")
        preview = Image.open(OUT / "face_pass_composite.png").convert("RGBA")
        if ImageChops.difference(merged, preview).getbbox() is not None:
            errors.append("ORA mergedimage differs from review composite")
    diff = Image.open(OUT / "reconstruction_diff.png").convert("RGBA")
    vals = np.asarray(diff)
    changed = int(np.count_nonzero(np.any(vals[..., :3] > 2, axis=2)))
    max_channel = int(vals[..., :3].max())
    if changed > 500:
        errors.append(f"in-place composite differs from flat source in too many pixels: {changed}")
    if errors:
        for x in errors:
            print("FAIL:", x)
        return 1
    print(f"PASS: 7 cutout layers + underpaint base + hidden reference; ORA and review composite agree; reconstruction changes={changed} px (max channel {max_channel})")
    print("LIMIT: structure/reconstruction only; not art sign-off or Cubism validation")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
