#!/usr/bin/env python3
"""Build the first hand-defined facial cutout/underpaint pass for Loli v1.

This extracts a small set of facial features from the accepted flat concept,
cleans the matching holes with OpenCV inpainting, and packages both the editable
PNG layers and an ORA. The underpaint is only an approximate starter, not finished
production illustration or Cubism-ready segmentation.
Requires Pillow, NumPy, and opencv-python-headless.
"""
from __future__ import annotations

import hashlib
import json
import zipfile
from io import BytesIO
from pathlib import Path
from xml.etree.ElementTree import Element, SubElement, tostring

import cv2
import numpy as np
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "characters/xiaoxun/design/loli_live2d_v1/concept_front_keyed.png"
OUT = ROOT / "characters/xiaoxun/design/loli_live2d_v1/cubism_source/face_pass_01"
CANVAS = (848, 1360)
Y_OFFSET = 48
SCALE = 4

# Tight hand-traced polygons in source-image coordinates (848x1264).
# They deliberately include each feature's outline but not neighboring features.
PARTS = [
    ("Whale_Clip", "30 Hair and signature accessory", [(306, 211), (309, 205), (318, 207), (324, 211), (337, 211), (344, 205), (349, 198), (353, 201), (353, 208), (359, 212), (365, 219), (362, 228), (356, 235), (349, 239), (337, 239), (329, 235), (320, 233), (313, 229), (307, 225), (304, 219)]),
    ("Brow_L", "20 Face and expressions", [(348, 258), (353, 254), (362, 251), (374, 251), (386, 253), (396, 257), (400, 262), (394, 266), (383, 262), (371, 259), (359, 262)]),
    ("Brow_R", "20 Face and expressions", [(448, 262), (453, 256), (463, 252), (475, 251), (487, 254), (495, 259), (497, 264), (491, 266), (480, 261), (469, 259), (457, 262)]),
    ("Eye_L", "20 Face and expressions", [(347, 266), (353, 260), (363, 257), (375, 258), (386, 262), (395, 269), (400, 279), (396, 289), (388, 297), (377, 301), (366, 300), (357, 295), (350, 287), (346, 277)]),
    ("Eye_R", "20 Face and expressions", [(449, 268), (456, 260), (467, 256), (478, 257), (489, 262), (497, 269), (501, 279), (498, 289), (491, 297), (481, 301), (469, 300), (459, 295), (452, 287), (448, 278)]),
    ("Nose", "20 Face and expressions", [(414, 294), (420, 293), (426, 296), (429, 302), (428, 311), (424, 316), (419, 314), (416, 308)]),
    ("Mouth_Closed", "20 Face and expressions", [(401, 323), (407, 320), (414, 322), (422, 324), (430, 322), (437, 320), (442, 324), (438, 331), (430, 335), (420, 337), (411, 335), (404, 331)]),
]


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def polygon_mask(points: list[tuple[int, int]], size: tuple[int, int]) -> np.ndarray:
    w, h = size
    m = Image.new("L", (w * SCALE, h * SCALE), 0)
    d = ImageDraw.Draw(m)
    d.polygon([(x * SCALE, y * SCALE) for x, y in points], fill=255)
    m = m.resize((w, h), Image.Resampling.LANCZOS)
    return np.asarray(m, dtype=np.uint8)


def to_canvas(img: Image.Image) -> Image.Image:
    canvas = Image.new("RGBA", CANVAS, (0, 0, 0, 0))
    canvas.alpha_composite(img, (0, Y_OFFSET))
    return canvas


def png_bytes(img: Image.Image) -> bytes:
    bio = BytesIO()
    img.save(bio, "PNG", optimize=True)
    return bio.getvalue()


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    source = Image.open(SOURCE).convert("RGBA")
    if source.size != (848, 1264):
        raise SystemExit(f"expected 848x1264 concept, got {source.size}")
    rgba = np.asarray(source).copy()
    h, w = rgba.shape[:2]
    masks: dict[str, np.ndarray] = {}
    for name, _, points in PARTS:
        mask = polygon_mask(points, (w, h))
        if name == "Whale_Clip":
            # The clip's teal fill is chromatically distinct from the hair/skin.
            # Keep only its tight ROI, then grow by 2px to retain dark antialiased ink.
            yy, xx = np.mgrid[:h, :w]
            roi = (xx >= 300) & (xx <= 368) & (yy >= 194) & (yy <= 244)
            rgb0 = rgba[..., :3].astype(np.int16)
            teal = roi & (rgb0[..., 1] > rgb0[..., 0] + 38) & (rgb0[..., 2] > rgb0[..., 0] + 38) & (rgb0[..., 1] > 160)
            teal = cv2.morphologyEx(teal.astype(np.uint8), cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))
            mask = cv2.dilate(teal * 255, np.ones((3, 3), np.uint8), iterations=2)
        mask = ((mask.astype(np.uint16) * rgba[..., 3].astype(np.uint16)) // 255).astype(np.uint8)
        if int(np.count_nonzero(mask > 32)) < 20:
            raise SystemExit(f"selection unexpectedly empty: {name}")
        masks[name] = mask

    union = np.zeros((h, w), dtype=np.uint8)
    for mask in masks.values():
        union = np.maximum(union, mask)
    # Keep cleanup strictly within the traced selections. Expanding the mask
    # smears adjacent lash/hair ink; seam-safe margin is intentionally deferred
    # to hand-painted refinement rather than guessed by this first pass.
    cleanup = (union > 127).astype(np.uint8) * 255
    rgb = rgba[..., :3].copy()
    # Inpaint only inside the artwork; do not synthesize over transparent canvas.
    cleanup[rgba[..., 3] == 0] = 0
    cleaned = cv2.inpaint(cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR), cleanup, 5, cv2.INPAINT_TELEA)
    cleaned = cv2.cvtColor(cleaned, cv2.COLOR_BGR2RGB)
    base = rgba.copy()
    base[..., :3] = cleaned
    base_layer = to_canvas(Image.fromarray(base, "RGBA"))
    base_path = OUT / "Base_Face_Underpaint_WIP.png"
    base_layer.save(base_path, optimize=True)

    layers: list[dict] = []
    layer_images: list[tuple[str, Image.Image, str]] = []
    for name, group, _ in PARTS:
        mask = masks[name]
        part = rgba.copy()
        part[..., 3] = ((part[..., 3].astype(np.uint16) * mask.astype(np.uint16)) // 255).astype(np.uint8)
        layer = to_canvas(Image.fromarray(part, "RGBA"))
        filename = f"{name}.png"
        layer.save(OUT / filename, optimize=True)
        layer_images.append((name, layer, group))
        layers.append({
            "name": name,
            "file": filename,
            "group": group,
            "state": "cut_from_accepted_flat_concept",
            "selection": "hand-traced polygon; source pixels preserved; no generated redraw",
            "occlusion_underpaint": "OpenCV Telea inpaint in base layer; approximate and requires human paint cleanup",
            "canvas_px": list(CANVAS),
            "source_offset_px": [0, Y_OFFSET],
        })

    # Composite the cleaned base and extracted cutouts in their original registration.
    assembled = base_layer.copy()
    for _, part_layer, _ in layer_images:
        assembled.alpha_composite(part_layer)
    assembled.save(OUT / "face_pass_composite.png", optimize=True)
    ref_canvas = to_canvas(source)
    ref_canvas.save(OUT / "reference_front_848x1360.png", optimize=True)

    # Difference image enables QA of the registered in-place reconstruction.
    a = np.asarray(assembled).astype(np.int16)
    b = np.asarray(ref_canvas).astype(np.int16)
    diff = np.abs(a - b).astype(np.uint8)
    Image.fromarray(diff, "RGBA").save(OUT / "reconstruction_diff.png", optimize=True)
    max_rgb = int(diff[..., :3].max())
    changed = int(np.count_nonzero(np.any(diff[..., :3] > 2, axis=2)))

    # OpenRaster: source reference starts hidden; editable base and parts are visible.
    stack_root = Element("image", {"version": "0.0.1", "w": str(CANVAS[0]), "h": str(CANVAS[1]), "name": "Xiaoxun Loli v1 - Face pass 01 WIP", "xres": "72", "yres": "72"})
    stack = SubElement(stack_root, "stack")
    filedata: dict[str, bytes] = {}
    ref_png = png_bytes(ref_canvas)
    filedata["data/reference.png"] = ref_png
    SubElement(stack, "layer", {"name": "Reference_Flat_v1 - locked guide, hidden", "src": "data/reference.png", "opacity": "0.55", "visibility": "hidden", "composite-op": "svg:src-over", "x": "0", "y": "0"})
    parts_group = SubElement(stack, "stack", {"name": "20 Face parts - WIP cutouts", "opacity": "1.0", "visibility": "visible", "composite-op": "svg:src-over"})
    for i, (name, layer, _) in reversed(list(enumerate(layer_images))):
        src = f"data/part_{i:02d}.png"
        filedata[src] = png_bytes(layer)
        SubElement(parts_group, "layer", {"name": name, "src": src, "opacity": "1.0", "visibility": "visible", "composite-op": "svg:src-over", "x": "0", "y": "0"})
    base_png = png_bytes(base_layer)
    filedata["data/base.png"] = base_png
    SubElement(stack, "layer", {"name": "00 Base + approximate face underpaint (WIP)", "src": "data/base.png", "opacity": "1.0", "visibility": "visible", "composite-op": "svg:src-over", "x": "0", "y": "0"})
    # Write bottom-to-top order to stack: base, face parts, hidden reference.
    # ORA children are listed topmost first; reorder above by rebuilding explicitly.
    stack.clear()
    SubElement(stack, "layer", {"name": "Reference_Flat_v1 - locked guide, hidden", "src": "data/reference.png", "opacity": "0.55", "visibility": "hidden", "composite-op": "svg:src-over", "x": "0", "y": "0"})
    parts_group = SubElement(stack, "stack", {"name": "20 Face parts - WIP cutouts", "opacity": "1.0", "visibility": "visible", "composite-op": "svg:src-over"})
    for i, (name, layer, _) in reversed(list(enumerate(layer_images))):
        src = f"data/part_{i:02d}.png"
        SubElement(parts_group, "layer", {"name": name, "src": src, "opacity": "1.0", "visibility": "visible", "composite-op": "svg:src-over", "x": "0", "y": "0"})
    SubElement(stack, "layer", {"name": "00 Base + approximate face underpaint (WIP)", "src": "data/base.png", "opacity": "1.0", "visibility": "visible", "composite-op": "svg:src-over", "x": "0", "y": "0"})
    stack_xml = tostring(stack_root, encoding="utf-8", xml_declaration=True)
    ora = OUT / "xiaoxun_loli_face_pass_01.ora"
    with zipfile.ZipFile(ora, "w") as z:
        z.writestr("mimetype", "image/openraster", compress_type=zipfile.ZIP_STORED)
        filedata["stack.xml"] = stack_xml
        filedata["mergedimage.png"] = png_bytes(assembled)
        for name, data in filedata.items():
            z.writestr(name, data, compress_type=zipfile.ZIP_DEFLATED)

    manifest = {
        "status": "WIP face cutout pass; not PSD; not Cubism model; not for runtime",
        "source_image": str(SOURCE.relative_to(ROOT)),
        "source_sha256": sha256(SOURCE),
        "canvas_px": list(CANVAS),
        "source_px": [848, 1264],
        "source_offset_px": [0, Y_OFFSET],
        "tool_method": "hand-defined polygon selections from accepted flat image; preserve source pixels; OpenCV Telea inpaint under removed features",
        "parts": layers,
        "base_layer": {"file": "Base_Face_Underpaint_WIP.png", "contains": "full original concept with facial cutout areas approximately inpainted; body/hair/clothing remain flat and unsegmented"},
        "visual_reconstruction_qa": {"changed_pixels_over_2_levels": changed, "max_channel_difference": max_rgb, "interpretation": "in-place composite check only; not an artistic quality approval"},
        "known_limits": [
            "This pass separates only the whale hair clip, brows, eyes, nose, and closed mouth.",
            "All extracted components are cutouts of the accepted flat concept; there is no semantic redraw of hidden content.",
            "Underpaint is algorithmic interpolation, not hand-painted production art, and needs cleanup before deformation.",
            "Hair, ears, face silhouette, neck, torso, sleeves, hands, skirt, legs, socks, and shoes remain fused in the flat base.",
            "No PSD, CMO3, MOC3, Model3 JSON, official Cubism Editor, SDK/Core, or runtime validation is included.",
        ],
        "ora_file": ora.name,
    }
    (OUT / "layer_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    sums = []
    for p in sorted(OUT.iterdir()):
        if p.is_file() and p.name != "SHA256SUMS.txt":
            sums.append(f"{sha256(p)}  {p.name}")
    (OUT / "SHA256SUMS.txt").write_text("\n".join(sums) + "\n", encoding="utf-8")
    print(json.dumps({"ora": str(ora.relative_to(ROOT)), "parts": len(layers), "changed_pixels_over_2": changed, "max_channel_difference": max_rgb, "status": manifest["status"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
