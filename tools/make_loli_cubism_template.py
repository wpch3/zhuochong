#!/usr/bin/env python3
"""Create an OpenRaster (.ora) source-authoring scaffold for Xiaoxun Loli v1.

This is an editable layer template, NOT a Cubism model and NOT a layered PSD.
All art layers are intentionally transparent placeholders; the single reference
layer preserves the accepted flattened concept at native scale, centered on the
project's 848x1360 canvas without upscaling.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import zipfile
from pathlib import Path
from xml.etree.ElementTree import Element, SubElement, tostring

from PIL import Image

CANVAS = (848, 1360)
Y_OFFSET = 48

# Group order is bottom-to-top, matching the conceptual paint stack. ORA's XML
# stores children top-to-bottom, so group creation below reverses this list.
GROUPS = [
    ("00 Reference - LOCK / DO NOT EXPORT", ["Reference_Front_Flat_v1"]),
    ("10 Body and wardrobe", [
        "Body_Base", "Neck", "Blouse", "Jacket_Back", "Jacket_Body_L", "Jacket_Body_R",
        "Jacket_Sleeve_L", "Jacket_Sleeve_R", "Cuff_Back_L", "Cuff_Back_R",
        "Cuff_Front_L", "Cuff_Front_R", "Arm_Upper_L", "Arm_Upper_R",
        "Arm_Fore_L", "Arm_Fore_R", "Hand_L", "Hand_R", "Skirt_Back",
        "Skirt_Front", "Skirt_Lining", "Leg_L", "Leg_R", "Sock_L", "Sock_R",
        "Shoe_L", "Shoe_R",
    ]),
    ("20 Face and expressions", [
        "Face_Base", "Ear_L", "Ear_R", "Brow_L", "Brow_R", "Nose", "Blush_L", "Blush_R",
        "Eye_L_Socket", "Eye_L_White", "Eye_L_Iris", "Eye_L_Pupil", "Eye_L_Highlight",
        "Eye_L_Lash_Upper", "Eye_L_Lash_Lower", "Eye_L_Lid_Upper", "Eye_L_Lid_Lower",
        "Eye_R_Socket", "Eye_R_White", "Eye_R_Iris", "Eye_R_Pupil", "Eye_R_Highlight",
        "Eye_R_Lash_Upper", "Eye_R_Lash_Lower", "Eye_R_Lid_Upper", "Eye_R_Lid_Lower",
        "Mouth_Closed", "Mouth_A", "Mouth_I", "Mouth_U", "Mouth_E", "Mouth_O",
        "Mouth_Smile", "Mouth_Surprised",
    ]),
    ("30 Hair and signature accessory", [
        "Hair_Back", "Hair_Side_L", "Hair_Side_R", "Bangs_Center", "Bangs_L",
        "Bangs_R", "Ahoge", "Whale_Clip",
    ]),
]


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def png_bytes(image: Image.Image) -> bytes:
    import io
    buf = io.BytesIO()
    image.save(buf, format="PNG", optimize=True)
    return buf.getvalue()



def build(source: Path, outdir: Path) -> dict:
    source = source.resolve()
    outdir.mkdir(parents=True, exist_ok=True)
    image = Image.open(source).convert("RGBA")
    if image.size != (848, 1264):
        raise SystemExit(f"Expected accepted Loli v1 source 848x1264, got {image.size}")
    canvas = Image.new("RGBA", CANVAS, (0, 0, 0, 0))
    canvas.alpha_composite(image, (0, Y_OFFSET))

    # Images are named by stable layer id. Empty placeholders remain transparent.
    ref_data = png_bytes(canvas)
    blank_data = png_bytes(Image.new("RGBA", CANVAS, (0, 0, 0, 0)))
    entries: list[dict] = []
    filedata: dict[str, bytes] = {"data/layer000.png": ref_data}
    next_id = 1
    # Generate a map for each group in intended bottom-to-top stack order.
    group_layers: list[tuple[str, list[tuple[str, str]]]] = []
    for group_name, names in GROUPS:
        layer_records = []
        for layer_name in names:
            if layer_name == "Reference_Front_Flat_v1":
                src = "data/layer000.png"
                role = "source reference only; excluded from production export"
                is_reference = True
            else:
                src = f"data/layer{next_id:03d}.png"
                next_id += 1
                filedata[src] = blank_data
                role = "transparent authoring placeholder; draw/paint real artwork before model import"
                is_reference = False
            layer_records.append((layer_name, src))
            entries.append({
                "name": layer_name,
                "ora_src": src,
                "group": group_name,
                "state": "reference_only" if is_reference else "blank_placeholder",
                "role": role,
                "visible": True,
                "canvas_px": list(CANVAS),
            })
        group_layers.append((group_name, layer_records))

    root = Element("image", {
        "version": "0.0.1", "w": str(CANVAS[0]), "h": str(CANVAS[1]),
        "name": "Xiaoxun Loli v1 - Cubism source scaffold, WIP",
        "xres": "72", "yres": "72",
    })
    stack = SubElement(root, "stack")
    # ORA order is topmost-first. Reverse our group order, and each group's
    # layer order; within the reference-only group the source sits at the base.
    for group_name, layers in reversed(group_layers):
        g = SubElement(stack, "stack", {"name": group_name, "opacity": "1.0", "visibility": "visible", "composite-op": "svg:src-over"})
        for layer_name, src in reversed(layers):
            attrs = {"name": layer_name, "src": src, "opacity": "1.0", "visibility": "visible", "composite-op": "svg:src-over", "x": "0", "y": "0"}
            if layer_name == "Reference_Front_Flat_v1":
                attrs["opacity"] = "0.55"
            SubElement(g, "layer", attrs)
    stack_xml = tostring(root, encoding="utf-8", xml_declaration=True)

    # Merged image is intentionally just the low-opacity reference, to make the
    # template safe and visually honest when opened in a generic raster editor.
    merged = canvas.copy()
    merged.putalpha(merged.getchannel("A").point(lambda a: round(a * 0.55)))
    filedata["stack.xml"] = stack_xml
    filedata["mergedimage.png"] = png_bytes(merged)
    ora_path = outdir / "xiaoxun_loli_cubism_source_v1.ora"
    with zipfile.ZipFile(ora_path, "w") as z:
        z.writestr("mimetype", "image/openraster", compress_type=zipfile.ZIP_STORED)
        for name, data in filedata.items():
            z.writestr(name, data, compress_type=zipfile.ZIP_DEFLATED)

    # Keep a normal-scale review image and an exact-size reference PNG alongside
    # the ORA. These are not production layers either.
    canvas.save(outdir / "reference_front_848x1360.png", optimize=True)
    preview = Image.new("RGBA", CANVAS, (248, 248, 248, 255))
    preview.alpha_composite(canvas)
    preview.convert("RGB").save(outdir / "template_preview.jpg", quality=94)

    manifest = {
        "schema_version": "1.0",
        "status": "WIP authoring scaffold; not PSD; not Cubism model; not for runtime",
        "source_image": str(source.relative_to(Path.cwd())) if source.is_relative_to(Path.cwd()) else source.name,
        "source_sha256": sha256(source),
        "source_px": [848, 1264],
        "target_canvas_px": list(CANVAS),
        "source_offset_px": [0, Y_OFFSET],
        "resampling": "none; source pixel size preserved",
        "ora_file": ora_path.name,
        "blank_placeholder_count": sum(x["state"] == "blank_placeholder" for x in entries),
        "reference_layer_count": 1,
        "layers": entries,
        "known_limits": [
            "All drawing layers are intentionally blank; no automatic segmentation or guessed underdraw was added.",
            "The sole reference layer contains one flattened concept and must not be exported as a model ArtMesh.",
            "No PSD, CMO3, MOC3, Model3 JSON, Cubism Editor or Cubism SDK/Core output is included.",
            "The concept source is not yet approved production art; body/face proportions and anchors still need measurement.",
        ],
    }
    manifest_path = outdir / "layer_manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return manifest


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", default="characters/xiaoxun/design/loli_live2d_v1/concept_front_keyed.png")
    ap.add_argument("--outdir", default="characters/xiaoxun/design/loli_live2d_v1/cubism_source")
    args = ap.parse_args()
    m = build(Path(args.source), Path(args.outdir))
    print(json.dumps({k: m[k] for k in ("ora_file", "target_canvas_px", "blank_placeholder_count", "reference_layer_count", "status")}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
