#!/usr/bin/env python3
"""Build a first head/face cutout pass from the selected Loli v1.1 reference.

Masks are hand-traced in native 1280x1920 coordinates. White clothing is not keyed;
this pass reads the border-connected alpha reference prepared in round 01.
OpenCV inpainting under features is approximate WIP and requires visual cleanup.
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
BASE = ROOT / "characters/xiaoxun/design/loli_live2d_v1/authoring_v1_1"
SOURCE = BASE / "reference_v1_1_alpha_edge_connected.png"
OUT = BASE / "head_pass_02"
CANVAS = (1280, 1920)
SCALE = 4

PARTS = [
    # Source coordinates, full-resolution, from the approved v1.1 front reference.
    ("Whale_Clip", "30 Hair and accessory", None),
    # Revised after plotting a full-resolution native-coordinate close-up; the
    # previous guesses were shifted left and caught adjacent fringe as eye art.
    ("Brow_L", "20 Face parts", [(539, 389), (544, 383), (553, 378), (565, 375), (578, 375), (590, 379), (600, 385), (602, 388), (595, 390), (583, 384), (570, 381), (557, 383), (547, 389)]),
    ("Brow_R", "20 Face parts", [(677, 389), (682, 383), (695, 378), (708, 375), (721, 377), (732, 383), (736, 388), (730, 391), (719, 385), (706, 381), (694, 383), (684, 389)]),
    ("Eye_L", "20 Face parts", [(526, 408), (531, 399), (540, 393), (551, 388), (563, 385), (576, 386), (589, 392), (600, 400), (605, 410), (605, 419), (600, 428), (591, 436), (579, 441), (565, 442), (552, 440), (541, 435), (533, 428), (528, 419)]),
    ("Eye_R", "20 Face parts", [(676, 408), (681, 399), (690, 393), (701, 388), (713, 385), (726, 386), (739, 392), (743, 400), (745, 410), (745, 419), (740, 428), (731, 436), (719, 441), (705, 442), (692, 440), (681, 435), (679, 428), (678, 419)]),
    ("Nose", "20 Face parts", None),  # preserve the original tiny dark nose mark only
    ("Mouth_Closed", "20 Face parts", None),  # dark smile strokes only; do not cut a pink skin patch

]
CLIP_ROI = (458, 288, 552, 358)


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def polygon_mask(points: list[tuple[int, int]], size: tuple[int, int]) -> np.ndarray:
    w, h = size
    mask = Image.new("L", (w * SCALE, h * SCALE), 0)
    draw = ImageDraw.Draw(mask)
    draw.polygon([(x * SCALE, y * SCALE) for x, y in points], fill=255)
    return np.asarray(mask.resize((w, h), Image.Resampling.LANCZOS), dtype=np.uint8)


def dark_mark_mask(rgba: np.ndarray, name: str) -> np.ndarray:
    """Isolate only dark source marks in tiny, registered face ROIs.

    This avoids cutting a conspicuous cheek-colored patch around static nose or
    mouth strokes. The threshold includes antialiased dark stroke pixels but not
    the surrounding peach skin; hand cleanup is still required for animation.
    """
    rois = {"Nose": (631, 438, 650, 461), "Mouth_Closed": (610, 477, 678, 498)}
    x0, y0, x1, y1 = rois[name]
    crop = rgba[y0:y1, x0:x1]
    rgb = crop[..., :3].astype(np.float32)
    gray = 0.299 * rgb[..., 0] + 0.587 * rgb[..., 1] + 0.114 * rgb[..., 2]
    selected = ((gray < 215) & (crop[..., 3] > 0)).astype(np.uint8) * 255
    full = np.zeros(rgba.shape[:2], dtype=np.uint8)
    full[y0:y1, x0:x1] = selected
    return full


def clip_mask(rgba: np.ndarray) -> np.ndarray:
    x0, y0, x1, y1 = CLIP_ROI
    crop = rgba[y0:y1, x0:x1, :3].astype(np.int16)
    teal = (crop[..., 1] > crop[..., 0] + 34) & (crop[..., 2] > crop[..., 0] + 28) & (crop[..., 1] > 145)
    teal = cv2.morphologyEx(teal.astype(np.uint8), cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))
    # Keep only the whale's main connected silhouette; ignore detached tiny
    # color flecks in the hair/anti-aliasing around this accessory.
    count, labels, stats, _ = cv2.connectedComponentsWithStats(teal, 8)
    if count > 1:
        largest = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
        teal = (labels == largest).astype(np.uint8)
    # Expand by two pixels so dark antialiased ink remains attached to the clip.
    local = cv2.dilate(teal, np.ones((3, 3), np.uint8), iterations=2) * 255
    full = np.zeros(rgba.shape[:2], dtype=np.uint8)
    full[y0:y1, x0:x1] = local
    return full


def png_bytes(img: Image.Image) -> bytes:
    b = BytesIO()
    img.save(b, format="PNG", optimize=True)
    return b.getvalue()


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    source = Image.open(SOURCE).convert("RGBA")
    if source.size != CANVAS:
        raise SystemExit(f"expected 1280x1920 isolated v1.1 reference, got {source.size}")
    rgba = np.asarray(source).copy()
    h, w = rgba.shape[:2]

    masks: dict[str, np.ndarray] = {}
    for name, _, points in PARTS:
        if name == "Whale_Clip":
            m = clip_mask(rgba)
        elif points is None:
            m = dark_mark_mask(rgba, name)
        else:
            m = polygon_mask(points, (w, h))
        m = ((m.astype(np.uint16) * rgba[..., 3].astype(np.uint16)) // 255).astype(np.uint8)
        min_pixels = 5 if name == "Nose" else 25
        if np.count_nonzero(m > 32) < min_pixels:
            raise SystemExit(f"cutout selection unexpectedly small: {name}")
        masks[name] = m

    union = np.zeros((h, w), dtype=np.uint8)
    for m in masks.values():
        union = np.maximum(union, m)
    # Keep the cleanup strictly bounded to artist-marked feature regions to avoid
    # smearing nearby hair/linework. Underpaint is approximate, not seam-final.
    cleanup = (union > 127).astype(np.uint8) * 255
    cleanup[rgba[..., 3] == 0] = 0
    bgr = cv2.cvtColor(rgba[..., :3], cv2.COLOR_RGB2BGR)
    filled = cv2.inpaint(bgr, cleanup, 4, cv2.INPAINT_TELEA)
    base_rgba = rgba.copy()
    base_rgba[..., :3] = cv2.cvtColor(filled, cv2.COLOR_BGR2RGB)
    # Subtract the selected cutout coverage from the base alpha. This leaves
    # the inpainted base visible beneath each feature while preserving the
    # original antialiased alpha when the isolated feature is composited back.
    base_rgba[..., 3] = ((rgba[..., 3].astype(np.uint16) * (255 - union.astype(np.uint16))) // 255).astype(np.uint8)
    base_img = Image.fromarray(base_rgba, "RGBA")
    base_img.save(OUT / "Base_Figure_Face_Underpaint_WIP.png", optimize=True)

    layer_images: list[tuple[str, Image.Image, str]] = []
    part_entries: list[dict] = []
    for name, group, _ in PARTS:
        p = rgba.copy()
        p[..., 3] = ((p[..., 3].astype(np.uint16) * masks[name].astype(np.uint16)) // 255).astype(np.uint8)
        layer = Image.fromarray(p, "RGBA")
        layer.save(OUT / f"{name}.png", optimize=True)
        layer_images.append((name, layer, group))
        part_entries.append({
            "name": name,
            "file": f"{name}.png",
            "group": group,
            "state": "source-pixel cutout from selected v1.1 reference",
            "selection": ("ROI-constrained dark-pixel mask (gray < 215)" if name in {"Nose", "Mouth_Closed"} else ("hand-traced native-coordinate polygon" if name != "Whale_Clip" else "ROI-constrained teal color mask with 2px outline expansion")),
            "underpaint": "feature selection removed from base and filled by OpenCV Telea; approximate WIP",
            "canvas_px": list(CANVAS),
        })

    composite = base_img.copy()
    for _, part, _ in layer_images:
        composite.alpha_composite(part)
    composite.save(OUT / "head_pass_composite.png", optimize=True)
    ref = Image.open(SOURCE).convert("RGBA")
    ref.save(OUT / "reference_v1_1_alpha_edge_connected.png", optimize=True)
    diff = np.abs(np.asarray(composite).astype(np.int16) - np.asarray(ref).astype(np.int16)).astype(np.uint8)
    Image.fromarray(diff, "RGBA").save(OUT / "reconstruction_diff.png", optimize=True)
    changed = int(np.count_nonzero(np.any(diff[..., :3] > 2, axis=2)))
    max_diff = int(diff[..., :3].max())

    # ORA stack order: reference (hidden), cutout group, clean base at bottom.
    ref_bytes = png_bytes(ref)
    base_bytes = png_bytes(base_img)
    part_bytes = {f"data/part_{i:02d}.png": png_bytes(layer) for i, (_, layer, _) in enumerate(layer_images)}
    xml_root = Element("image", {"version": "0.0.1", "w": str(w), "h": str(h), "name": "Xiaoxun Loli v1.1 - head pass 02 WIP", "xres": "72", "yres": "72"})
    stack = SubElement(xml_root, "stack")
    SubElement(stack, "layer", {"name": "NEW v1.1 full reference - locked, hidden", "src": "data/reference.png", "opacity": "0.55", "visibility": "hidden", "composite-op": "svg:src-over", "x": "0", "y": "0"})
    group = SubElement(stack, "stack", {"name": "20 Face cutouts - WIP", "opacity": "1.0", "visibility": "visible", "composite-op": "svg:src-over"})
    for i in reversed(range(len(layer_images))):
        name, _, _ = layer_images[i]
        SubElement(group, "layer", {"name": name, "src": f"data/part_{i:02d}.png", "opacity": "1.0", "visibility": "visible", "composite-op": "svg:src-over", "x": "0", "y": "0"})
    SubElement(stack, "layer", {"name": "00 Figure base with approximate face underpaint (WIP; body/hair still flat)", "src": "data/base.png", "opacity": "1.0", "visibility": "visible", "composite-op": "svg:src-over", "x": "0", "y": "0"})
    ora = OUT / "xiaoxun_loli_v1_1_head_pass_02.ora"
    with zipfile.ZipFile(ora, "w") as z:
        z.writestr("mimetype", "image/openraster", compress_type=zipfile.ZIP_STORED)
        files = {"data/reference.png": ref_bytes, "data/base.png": base_bytes, **part_bytes,
                 "stack.xml": tostring(xml_root, encoding="utf-8", xml_declaration=True),
                 "mergedimage.png": png_bytes(composite)}
        for name, data in files.items():
            z.writestr(name, data, compress_type=zipfile.ZIP_DEFLATED)

    manifest = {
        "status": "WIP head/face cutout pass based on selected v1.1; not finished art, not PSD, not Cubism",
        "source": "../reference_v1_1_alpha_edge_connected.png",
        "source_sha256": digest(SOURCE),
        "canvas_px": list(CANVAS),
        "ora_file": ora.name,
        "base_layer": {"file": "Base_Figure_Face_Underpaint_WIP.png", "note": "face details removed and locally inpainted; all other character art remains one flat figure"},
        "parts": part_entries,
        "reconstruction_check": {"pixels_changed_over_2_rgb_levels": changed, "max_channel_difference": max_diff, "interpretation": "registered cutout assembly only, not art approval"},
        "known_limits": [
            "Only the whale clip, brows, eyes, nose and closed mouth are cut out in this pass.",
            "The face parts are source-pixel selections; hair, scalp, face silhouette, ears, neck, torso, jacket, sleeves, hands, skirt, legs, socks and shoes remain fused in the flat base.",
            "Underpaint is algorithmic interpolation, not hand-painted production art; masks need edge review and hidden-region redraw before deformation.",
            "No PSD/PSB, Cubism Editor project, ArtMesh, CMO3, MOC3, Model3 JSON or runtime validation is included.",
        ],
    }
    mp = OUT / "layer_manifest.json"
    mp.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    files_for_sums = sorted(p for p in OUT.iterdir() if p.is_file() and p.name != "SHA256SUMS.txt")
    (OUT / "SHA256SUMS.txt").write_text("".join(f"{digest(p)}  {p.name}\n" for p in files_for_sums))
    print(json.dumps({"ora": ora.name, "cutout_parts": len(part_entries), "reconstruction_changed_pixels_over_2": changed, "max_rgb_difference": max_diff, "status": manifest["status"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
