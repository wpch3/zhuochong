#!/usr/bin/env python3
"""Validate the Xiaoxun Loli v1 OpenRaster authoring scaffold (not Cubism)."""
from __future__ import annotations

import argparse
import json
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

from PIL import Image, ImageChops


def check(outdir: Path) -> list[str]:
    errors: list[str] = []
    ora_path = outdir / "xiaoxun_loli_cubism_source_v1.ora"
    manifest_path = outdir / "layer_manifest.json"
    ref_path = outdir / "reference_front_848x1360.png"
    if not all(p.is_file() for p in (ora_path, manifest_path, ref_path)):
        missing = [p.name for p in (ora_path, manifest_path, ref_path) if not p.is_file()]
        return [f"missing required file(s): {', '.join(missing)}"]

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("status") != "WIP authoring scaffold; not PSD; not Cubism model; not for runtime":
        errors.append("manifest does not clearly mark this as a non-Cubism WIP scaffold")
    if manifest.get("target_canvas_px") != [848, 1360]:
        errors.append("manifest canvas is not 848x1360")
    if manifest.get("blank_placeholder_count") != 69 or manifest.get("reference_layer_count") != 1:
        errors.append("manifest layer counts differ from expected 69 blank + 1 reference")

    with zipfile.ZipFile(ora_path) as z:
        names = z.namelist()
        if not names or names[0] != "mimetype":
            errors.append("ORA mimetype is not the first archive entry")
        elif z.getinfo("mimetype").compress_type != zipfile.ZIP_STORED:
            errors.append("ORA mimetype entry must be uncompressed")
        if z.read("mimetype") != b"image/openraster":
            errors.append("invalid ORA mimetype value")
        root = ET.fromstring(z.read("stack.xml"))
        if (root.get("w"), root.get("h")) != ("848", "1360"):
            errors.append("stack.xml canvas is not 848x1360")
        stack = root.find("stack")
        if stack is None:
            return errors + ["stack.xml has no root stack"]
        groups = stack.findall("stack")
        if len(groups) != 4:
            errors.append(f"expected 4 layer groups, found {len(groups)}")
        layers = root.findall(".//layer")
        if len(layers) != 70:
            errors.append(f"expected 70 layers, found {len(layers)}")
        layer_names = [layer.get("name", "") for layer in layers]
        if len(set(layer_names)) != len(layer_names):
            errors.append("layer names are not unique")
        if "Reference_Front_Flat_v1" not in layer_names:
            errors.append("flattened reference layer missing")
        elif next(l for l in layers if l.get("name") == "Reference_Front_Flat_v1").get("opacity") != "0.55":
            errors.append("reference layer opacity is not 0.55")

        by_src = {layer.get("src"): layer for layer in layers}
        ref_layer = next((l for l in layers if l.get("name") == "Reference_Front_Flat_v1"), None)
        if ref_layer is not None:
            ref_img = Image.open(z.open(ref_layer.get("src"))).convert("RGBA")
            ref_disk = Image.open(ref_path).convert("RGBA")
            if ref_img.size != (848, 1360) or ref_disk.size != (848, 1360):
                errors.append("reference layer dimensions are not 848x1360")
            elif ImageChops.difference(ref_img, ref_disk).getbbox() is not None:
                errors.append("ORA reference pixels differ from sidecar reference PNG")

        placeholders = [x for x in manifest.get("layers", []) if x.get("state") == "blank_placeholder"]
        if len(placeholders) != 69:
            errors.append(f"expected 69 blank placeholders in manifest, found {len(placeholders)}")
        for item in placeholders:
            src = item.get("ora_src")
            if src not in by_src or src not in names:
                errors.append(f"placeholder image missing from ORA: {src}")
                continue
            img = Image.open(z.open(src)).convert("RGBA")
            if img.size != (848, 1360):
                errors.append(f"placeholder dimensions incorrect: {src} {img.size}")
            if img.getchannel("A").getextrema() != (0, 0):
                errors.append(f"placeholder is not blank/transparent: {src}")

        merged = Image.open(z.open("mergedimage.png")).convert("RGBA")
        if merged.size != (848, 1360):
            errors.append("mergedimage dimensions are not 848x1360")
        elif ref_layer is not None:
            expected = ref_img.copy()
            expected.putalpha(expected.getchannel("A").point(lambda a: round(a * 0.55)))
            if ImageChops.difference(merged, expected).getbbox() is not None:
                errors.append("mergedimage is not the declared 55%-opacity reference-only preview")
    return errors


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--outdir", default="characters/xiaoxun/design/loli_live2d_v1/cubism_source")
    args = ap.parse_args()
    errors = check(Path(args.outdir))
    if errors:
        for error in errors:
            print("FAIL:", error)
        return 1
    print("PASS: ORA structure, 848x1360 registration, 69 blank authoring layers, reference identity and WIP status")
    print("NOTE: this is not a PSD, Cubism Editor project, MOC3, or runtime model")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
