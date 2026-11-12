#!/usr/bin/env python3
"""Build the current semantic head/face WIP pass from the selected v1.1 reference.

Masks are hand-traced in native 1280x1920 coordinates. White clothing is not keyed;
this pass reads the border-connected alpha reference prepared in round 01.
OpenCV inpainting under features is approximate WIP and requires visual cleanup.
"""
from __future__ import annotations

import argparse
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
OUT = BASE / "head_pass_03"
CANVAS = (1280, 1920)
IS_PASS_04 = False
SCALE = 4

# Facial parts follow the official material-preparation tutorial's semantic
# split: sclera, eyeball and eyelashes are not one generic eye sticker.
EYE_BALL = {
    "L": [(552, 406), (555, 398), (562, 393), (572, 391), (582, 394), (590, 401), (595, 411), (597, 422), (594, 432), (587, 439), (577, 442), (566, 440), (558, 434), (553, 425), (551, 415)],
    "R": [(684, 406), (687, 398), (694, 393), (704, 391), (714, 394), (722, 401), (727, 411), (729, 422), (726, 432), (719, 439), (709, 442), (698, 440), (690, 434), (685, 425), (683, 415)],
}
EYELASH_BAND = {
    "L": [(524, 411), (528, 401), (538, 394), (550, 389), (563, 385), (576, 386), (589, 392), (600, 400), (607, 409), (602, 415), (594, 408), (584, 402), (574, 398), (563, 397), (553, 399), (543, 404), (535, 411), (529, 418)],
    "R": [(674, 411), (678, 401), (688, 394), (700, 389), (713, 385), (726, 386), (739, 392), (746, 400), (750, 409), (745, 415), (737, 408), (727, 402), (717, 398), (706, 397), (696, 399), (686, 404), (680, 411), (676, 418)],
}
EYE_WHITE_PATCHES = {
    "L": [
        [(537, 410), (540, 405), (546, 405), (551, 409), (553, 416), (553, 423), (557, 431), (560, 435), (553, 433), (547, 429), (541, 423), (538, 417)],
        [(591, 405), (596, 404), (601, 408), (603, 414), (601, 421), (597, 426), (593, 429), (595, 420)],
    ],
    "R": [
        [(679, 410), (682, 405), (687, 404), (691, 408), (691, 415), (689, 422), (685, 429), (681, 432), (679, 426)],
        [(729, 405), (734, 404), (738, 408), (740, 414), (738, 421), (734, 426), (730, 429), (732, 420), (733, 414)],
    ],
}
BROW_POLY = {
    "L": [(565, 381), (568, 378), (574, 375), (581, 374), (589, 376), (596, 379), (598, 382), (594, 383), (587, 381), (580, 379), (573, 379), (568, 382)],
    "R": [(686, 382), (690, 379), (696, 376), (704, 374), (711, 376), (717, 379), (720, 382), (716, 383), (710, 381), (703, 379), (696, 380), (691, 382)],
}
FACE_PARTS = [
    ("EyeWhite_L", "20 Face parts / left eye"), ("EyeBall_L", "20 Face parts / left eye"), ("Eyelash_L", "20 Face parts / left eye"),
    ("Brow_L", "20 Face parts"),
    ("EyeWhite_R", "20 Face parts / right eye"), ("EyeBall_R", "20 Face parts / right eye"), ("Eyelash_R", "20 Face parts / right eye"),
    ("Brow_R", "20 Face parts"), ("Nose", "20 Face parts"), ("Mouth_Closed", "20 Face parts"), ("Whale_Clip", "30 Hair and accessory"),
]
SLEEVE_L_PATH = [(453, 641), (472, 642), (483, 670), (493, 705), (497, 745), (496, 785), (487, 820), (474, 855), (461, 890), (451, 925), (444, 958), (436, 985), (420, 1002), (396, 1012), (365, 1013), (340, 1006), (323, 988), (320, 962), (327, 934), (341, 902), (357, 875), (373, 846), (388, 816), (400, 785), (412, 750), (424, 713), (438, 680)]
SLEEVE_PARTS = [("JacketSleeve_Teal_L", "10 Jacket / visible teal sleeve"), ("JacketSleeve_Teal_R", "10 Jacket / visible teal sleeve")]
PARTS = FACE_PARTS
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
    # BOX downsamples the 4x coverage mask without Lanczos ringing outside the
    # traced boundary; mask halos can otherwise leak adjacent line art.
    return np.asarray(mask.resize((w, h), Image.Resampling.BOX), dtype=np.uint8)


def gray_level(rgb: np.ndarray) -> np.ndarray:
    return 0.299 * rgb[..., 0].astype(np.float32) + 0.587 * rgb[..., 1].astype(np.float32) + 0.114 * rgb[..., 2].astype(np.float32)


def dark_mark_mask(rgba: np.ndarray, name: str, threshold: float = 215) -> np.ndarray:
    """Isolate dark source marks in small native-coordinate face ROIs."""
    rois = {"Nose": (631, 438, 650, 461), "Mouth_Closed": (610, 477, 678, 498)}
    x0, y0, x1, y1 = rois[name]
    crop = rgba[y0:y1, x0:x1]
    selected = ((gray_level(crop[..., :3]) < threshold) & (crop[..., 3] > 0)).astype(np.uint8) * 255
    full = np.zeros(rgba.shape[:2], dtype=np.uint8)
    full[y0:y1, x0:x1] = selected
    return full


def largest_component(mask: np.ndarray) -> np.ndarray:
    count, labels, stats, _ = cv2.connectedComponentsWithStats((mask > 0).astype(np.uint8), 8)
    out = np.zeros(mask.shape, dtype=np.uint8)
    if count > 1:
        idx = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
        out[labels == idx] = 255
    return out


def semantic_face_masks(rgba: np.ndarray) -> dict[str, np.ndarray]:
    """Separate eyes into whites, eyeballs, and upper lash lines (WIP masks)."""
    h, w = rgba.shape[:2]
    result: dict[str, np.ndarray] = {}
    gray = gray_level(rgba[..., :3])
    rgb = rgba[..., :3].astype(np.int16)
    for side in ("L", "R"):
        ball_shape = polygon_mask(EYE_BALL[side], (w, h))
        lash_band = polygon_mask(EYELASH_BAND[side], (w, h))
        brow_shape = polygon_mask(BROW_POLY[side], (w, h))
        # Restrict eyelash extraction to the hand-traced upper contour band;
        # low luminance avoids cutting the surrounding eyelid/skin patch.
        # Upper eyeliner is a dark green/gray stroke; reject dark blue iris
        # pixels by hue-channel relation as well as luminance.
        lash = ((lash_band > 0) & (gray < 150) & ((rgb[..., 2] - rgb[..., 1]) < 22) & (rgb[..., 1] >= rgb[..., 0] - 15) & (rgba[..., 3] > 0)).astype(np.uint8) * 255
        ball = ((ball_shape > 0) & (rgba[..., 3] > 0)).astype(np.uint8) * 255
        ball[lash > 0] = 0
        # Trace only the visible white crescents beside the iris; do not use a
        # broad eye oval that can select nearby fringe/eyelash pixels.
        white_region = np.zeros((h, w), dtype=np.uint8)
        for points in EYE_WHITE_PATCHES[side]:
            white_region = np.maximum(white_region, polygon_mask(points, (w, h)))
        chroma = rgb.max(axis=2) - rgb.min(axis=2)
        whites = ((white_region > 0) & (rgb.min(axis=2) > 195) & (chroma < 65) & (ball == 0) & (lash == 0) & (rgba[..., 3] > 0)).astype(np.uint8) * 255
        # Brow is a thin dark-stroke selection inside a narrow hand-traced arc,
        # rather than a broad skin-colored ribbon.
        brow = ((brow_shape > 0) & (gray < 225) & (rgba[..., 3] > 0)).astype(np.uint8) * 255
        # Exclude disconnected fringe flecks outside the main eyebrow stroke.
        brow = largest_component(brow)
        result[f"EyeWhite_{side}"] = whites
        result[f"EyeBall_{side}"] = ball
        result[f"Eyelash_{side}"] = lash
        result[f"Brow_{side}"] = brow
    result["Nose"] = dark_mark_mask(rgba, "Nose")
    result["Mouth_Closed"] = dark_mark_mask(rgba, "Mouth_Closed")
    result["Whale_Clip"] = clip_mask(rgba)
    # Round 04 garment study: extract the visible teal sleeve fabric only.
    # Cuffs, white stripes, hands, and hidden upper-arm art remain unseparated.
    for side in ("L", "R"):
        path = SLEEVE_L_PATH if side == "L" else [(1280 - x, y) for x, y in SLEEVE_L_PATH]
        boundary = polygon_mask(path, (w, h))
        r = rgba[..., :3].astype(np.int16)
        teal = ((r[..., 1] > r[..., 0] + 20) & (r[..., 2] > r[..., 0] + 10) & (r[..., 1] > 100) & (boundary > 0) & (rgba[..., 3] > 0)).astype(np.uint8)
        teal = cv2.morphologyEx(teal, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))
        teal = largest_component(teal)
        expanded = cv2.dilate(teal, np.ones((3, 3), np.uint8), iterations=1)
        # Keep a binary registered cutout in this WIP pass; fractional polygon
        # alpha over an inpainted base causes double-compositing halos.
        result[f"JacketSleeve_Teal_{side}"] = ((expanded > 0) & (boundary > 127)).astype(np.uint8) * 255
    return result


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
    global OUT, PARTS, IS_PASS_04
    parser = argparse.ArgumentParser(description="Build an editable WIP cutout stack from the selected Loli v1.1 reference.")
    parser.add_argument("--with-sleeves", action="store_true", help="write pass 04 with two visible teal sleeve-region cutouts")
    args = parser.parse_args()
    if args.with_sleeves:
        OUT = BASE / "authoring_pass_04"
        PARTS = SLEEVE_PARTS + FACE_PARTS
        IS_PASS_04 = True
    else:
        OUT = BASE / "head_pass_03"
        PARTS = FACE_PARTS
        IS_PASS_04 = False
    OUT.mkdir(parents=True, exist_ok=True)
    source = Image.open(SOURCE).convert("RGBA")
    if source.size != CANVAS:
        raise SystemExit(f"expected 1280x1920 isolated v1.1 reference, got {source.size}")
    rgba = np.asarray(source).copy()
    h, w = rgba.shape[:2]

    all_masks = semantic_face_masks(rgba)
    masks = {name: all_masks[name] for name, _ in PARTS}
    for name in masks:
        masks[name] = ((masks[name].astype(np.uint16) * rgba[..., 3].astype(np.uint16)) // 255).astype(np.uint8)
        min_pixels = 5 if name == "Nose" else 12
        if np.count_nonzero(masks[name] > 32) < min_pixels:
            raise SystemExit(f"cutout selection unexpectedly small: {name}")
    if set(masks) != {name for name, _ in PARTS}:
        raise SystemExit("semantic source-mask set does not match declared layer stack")

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
    for name, group in PARTS:
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
            "selection": ("native-coordinate teal fabric mask in traced sleeve ROI; largest component plus 1px expansion" if name.startswith("JacketSleeve_Teal_") else ("near-neutral light-pixel selection inside traced sclera crescents" if name.startswith("EyeWhite_") else ("hand-traced iris/eyeball region" if name.startswith("EyeBall_") else ("dark pixels in a hand-traced upper-lash band" if name.startswith("Eyelash_") else ("dark pixels in a hand-traced brow ROI" if name.startswith("Brow_") else ("ROI dark-pixel mask, gray < 215" if name in {"Nose", "Mouth_Closed"} else "ROI-constrained teal mask, largest component with 2px expansion")))))),
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
    pass_name = "authoring pass 04" if IS_PASS_04 else "head pass 03"
    xml_root = Element("image", {"version": "0.0.1", "w": str(w), "h": str(h), "name": f"Xiaoxun Loli v1.1 - {pass_name} WIP", "xres": "72", "yres": "72"})
    stack = SubElement(xml_root, "stack")
    SubElement(stack, "layer", {"name": "NEW v1.1 full reference - locked, hidden", "src": "data/reference.png", "opacity": "0.55", "visibility": "hidden", "composite-op": "svg:src-over", "x": "0", "y": "0"})
    group_name = "10 Body and 20 Face semantic layers - WIP" if IS_PASS_04 else "20 Face semantic layers - WIP; verify layer ownership before rigging"
    group = SubElement(stack, "stack", {"name": group_name, "opacity": "1.0", "visibility": "visible", "composite-op": "svg:src-over"})
    for i in reversed(range(len(layer_images))):
        name, _, _ = layer_images[i]
        SubElement(group, "layer", {"name": name, "src": f"data/part_{i:02d}.png", "opacity": "1.0", "visibility": "visible", "composite-op": "svg:src-over", "x": "0", "y": "0"})
    SubElement(stack, "layer", {"name": "00 Figure base with approximate face underpaint (WIP; body/hair still flat)", "src": "data/base.png", "opacity": "1.0", "visibility": "visible", "composite-op": "svg:src-over", "x": "0", "y": "0"})
    ora_name = "xiaoxun_loli_v1_1_authoring_pass_04.ora" if IS_PASS_04 else "xiaoxun_loli_v1_1_head_pass_03.ora"
    ora = OUT / ora_name
    with zipfile.ZipFile(ora, "w") as z:
        z.writestr("mimetype", "image/openraster", compress_type=zipfile.ZIP_STORED)
        files = {"data/reference.png": ref_bytes, "data/base.png": base_bytes, **part_bytes,
                 "stack.xml": tostring(xml_root, encoding="utf-8", xml_declaration=True),
                 "mergedimage.png": png_bytes(composite)}
        for name, data in files.items():
            z.writestr(name, data, compress_type=zipfile.ZIP_DEFLATED)

    known_limits = [
        "The current eye components are approximate source-pixel selections; sclera/eyeball/upper-lash masks need manual ownership review and are not deformation-ready.",
        "No pupil/highlight subparts, blink-closed redraw, open-mouth shapes or hand-painted hidden eye/mouth art are included.",
        "Hair, scalp, face silhouette, ears, neck, torso, jacket, sleeves, hands, skirt, legs, socks and shoes remain fused in the flat base.",
        "Underpaint is algorithmic interpolation, not hand-painted production art; all masks need edge review and hidden-region redraw before deformation.",
        "No PSD/PSB, Cubism Editor project, ArtMesh, CMO3, MOC3, Model3 JSON or runtime validation is included.",
    ]
    if IS_PASS_04:
        known_limits.append("Pass 04 additionally has visible teal sleeve-color selections only; cuffs, white stripes, hands, hidden overlaps and complete sleeve parts remain unseparated.")
    manifest = {
        "status": "WIP source-visible cutout stack based on selected v1.1; not finished art, not PSD, not Cubism",
        "source": "../reference_v1_1_alpha_edge_connected.png",
        "source_sha256": digest(SOURCE),
        "canvas_px": list(CANVAS),
        "ora_file": ora.name,
        "base_layer": {"file": "Base_Figure_Face_Underpaint_WIP.png", "note": "face details removed and locally inpainted; all other character art remains one flat figure"},
        "parts": part_entries,
        "reconstruction_check": {"pixels_changed_over_2_rgb_levels": changed, "max_channel_difference": max_diff, "interpretation": "registered cutout assembly only, not art approval"},
        "known_limits": known_limits,

    }
    mp = OUT / "layer_manifest.json"
    mp.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    files_for_sums = sorted(p for p in OUT.iterdir() if p.is_file() and p.name != "SHA256SUMS.txt")
    (OUT / "SHA256SUMS.txt").write_text("".join(f"{digest(p)}  {p.name}\n" for p in files_for_sums))
    print(json.dumps({"ora": ora.name, "cutout_parts": len(part_entries), "reconstruction_changed_pixels_over_2": changed, "max_rgb_difference": max_diff, "status": manifest["status"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
