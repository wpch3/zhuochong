#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Generate the teen jaw cast-shadow and the restrained clavicle cues (T67.9).

The registered short-hair design sheet is the visual source of truth.  The
shadows are separate neutral Multiply attachments, clipped to its exposed skin
pixels; no pixels are painted across the shirt, collar, jacket or hair.
"""
from __future__ import annotations

import argparse
import json
import os

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

import attach_geom
import cut_from_sheets as C

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MAGENTA = np.array([255.0, 0.0, 255.0], dtype=np.float32)
JAW_RGB = np.array([139.0, 119.0, 116.0], dtype=np.float32)
CLAVICLE_RGB = np.array([112.0, 97.0, 98.0], dtype=np.float32)
JAW_PEAK = 0.34
CLAVICLE_PEAK = 0.19


def _skin_mask(rgb: np.ndarray, opaque: np.ndarray) -> np.ndarray:
    r, g, b = [rgb[..., i].astype(np.float32) for i in range(3)]
    # Peach skin separates from the cream blouse by its stronger red-over-green
    # and green-over-blue deltas.  Region bounds below further constrain use.
    return opaque & (r > 175.0) & (g > 105.0) & (b > 85.0) \
        & ((r - g) > 18.0) & ((g - b) > 6.0)


def _bezier(points, steps=96):
    p0, p1, p2 = (np.asarray(p, dtype=np.float32) for p in points)
    t = np.linspace(0.0, 1.0, steps, dtype=np.float32)[:, None]
    return (1.0 - t) ** 2 * p0 + 2.0 * (1.0 - t) * t * p1 + t ** 2 * p2


def _make_jaw_alpha(rgb: np.ndarray, opaque: np.ndarray) -> np.ndarray:
    h, w = opaque.shape
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    skin = _skin_mask(rgb, opaque)
    dx = xx - 510.0
    # Fit the visible lower-face contour: center at y≈337; lateral jaw corners
    # rise toward y≈310.  The contact shadow starts just under that contour.
    jaw_y = 337.0 - 0.0088 * dx * dx
    depth = yy - jaw_y
    xedge = np.minimum((xx - 448.0) / 18.0, (572.0 - xx) / 18.0)
    xedge = np.clip(xedge, 0.0, 1.0)
    xedge = xedge * xedge * (3.0 - 2.0 * xedge)
    ramp = np.clip((depth - 0.25) / 2.0, 0.0, 1.0)
    fade = np.exp(-np.maximum(depth, 0.0) / 8.5)
    vertical = (depth >= 0.0) & (depth <= 18.0) & (yy <= 360.0)
    region = (xx >= 448.0) & (xx <= 572.0) & vertical
    alpha = JAW_PEAK * ramp * fade * xedge * skin * region
    # Small blur takes the edge off color-gate transitions; the distance field
    # defines the actual cast-shadow profile.
    a = Image.fromarray(np.clip(alpha * 255.0, 0, 255).astype(np.uint8), "L")
    a = a.filter(ImageFilter.GaussianBlur(0.55))
    out = np.asarray(a, dtype=np.float32) / 255.0
    out[~(region & skin)] = 0.0
    return out


def _make_clavicle_alpha(rgb: np.ndarray, opaque: np.ndarray) -> np.ndarray:
    h, w = opaque.shape
    skin = _skin_mask(rgb, opaque)
    # The hoodie and buttoned blouse cover most of the clavicles.  These are
    # intentionally short, shallow cues only on the exposed neck-root skin;
    # they stop before the shirt opening rather than drawing bones over fabric.
    scale = 4
    line = Image.new("L", (w * scale, h * scale), 0)
    draw = ImageDraw.Draw(line)
    for pts in (
        ((476, 350), (488, 354), (501, 358)),
        ((544, 350), (532, 354), (519, 358)),
    ):
        curve = _bezier(pts)
        curve = [(int(round(x * scale)), int(round(y * scale))) for x, y in curve]
        draw.line(curve, fill=255, width=12, joint="curve")
    line = line.resize((w, h), Image.Resampling.LANCZOS)
    line = line.filter(ImageFilter.GaussianBlur(0.22))
    line_a = np.asarray(line, dtype=np.float32) / 255.0
    yy, xx = np.mgrid[0:h, 0:w]
    region = (xx >= 465) & (xx <= 555) & (yy >= 346) & (yy <= 361)
    alpha = CLAVICLE_PEAK * line_a * skin * opaque * region
    return np.clip(alpha, 0.0, 1.0)


def _write_keyed(path: str, alpha: np.ndarray, shadow_rgb: np.ndarray, peak: float) -> None:
    # Keep matte coverage separate from Multiply strength: make_attach_parts' keyed
    # source expects opaque interior pixels, so encode strength in a near-white
    # multiply color and reserve alpha for shape/antialias coverage.
    coverage = np.clip(alpha / max(peak, 1e-6), 0.0, 1.0)
    multiply_rgb = 255.0 + peak * (shadow_rgb - 255.0)
    keyed = MAGENTA[None, None, :] * (1.0 - coverage[..., None]) \
        + multiply_rgb[None, None, :] * coverage[..., None]
    Image.fromarray(np.clip(keyed, 0, 255).astype(np.uint8), "RGB").save(path)


def _geometry(character: str, form: str, alpha: np.ndarray, socket_id: str) -> dict:
    ys, xs = np.nonzero(alpha > 0.02)
    if not len(xs):
        raise SystemExit(f"[neck-details] {socket_id}: generated alpha is empty")
    x0, x1 = int(xs.min()), int(xs.max()) + 1
    y0, y1 = int(ys.min()), int(ys.max()) + 1
    char_root = os.path.join(ROOT, "characters", character)
    design = os.path.join(char_root, "design")
    form_root = os.path.join(char_root, "forms", form)
    base = os.path.join(design, "design_sheet_short.png")
    _, opaque = C.key_rgba(base)
    by, bx = np.nonzero(opaque)
    bbox = (int(bx.min()), int(by.min()), int(bx.max()), int(by.max()))
    char_h = bbox[3] - bbox[1] + 1
    sheet_to_body = (C.TARGET_CANVAS[1] * C.HEIGHT_RATIO) / char_h
    with open(os.path.join(form_root, "design", "anchors.json"), encoding="utf-8") as f:
        anchors = json.load(f)
    unit = float(anchors["meta"]["head_ratio"]) * float(anchors["meta"]["height_px"])

    cx = (x0 + x1) / 2.0
    crop_h = (y1 - y0) * (1.0 + 2.0 * CROP_MARGIN)
    # Keep the same transparent crop allowance as make_attach_parts.
    cx_body = (cx - bbox[0]) * sheet_to_body
    top_body = (y0 - CROP_MARGIN * (y1 - y0) - bbox[1]) * sheet_to_body
    sockets = attach_geom.load_sockets(char_root)
    socket = next((s for s in sockets.values() if s["id"] == socket_id), None)
    if socket is None:
        raise SystemExit(f"[neck-details] missing {socket_id}")
    base_x, base_y = attach_geom.socket_pos(socket, anchors)
    return {
        "unit": "head",
        "socket": socket_id,
        "dpos_rel": [round((cx_body - base_x) / unit, 6),
                     round((top_body - base_y) / unit, 6)],
        "sprite_h_rel": round(crop_h * sheet_to_body / unit, 6),
        "width_ratio": 1.0,
    }


# Keep in sync with tools/make_attach_parts.py's source-space crop margin.
CROP_MARGIN = 0.04


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--character", default="xiaoxun")
    ap.add_argument("--form", default="teen")
    ap.add_argument("--update-attachments", action="store_true")
    a = ap.parse_args()
    if a.character != "xiaoxun" or a.form != "teen":
        raise SystemExit("[neck-details] currently authored for xiaoxun/teen only")

    char_root = os.path.join(ROOT, "characters", a.character)
    design = os.path.join(char_root, "design")
    redraw = os.path.join(design, "redraw")
    os.makedirs(redraw, exist_ok=True)
    ref = os.path.join(design, "design_sheet_short.png")
    rgb, opaque = C.key_rgba(ref)
    skin = _skin_mask(rgb, opaque)
    jaw = _make_jaw_alpha(rgb, opaque)
    clav = _make_clavicle_alpha(rgb, opaque)

    # Fail closed if the selected geometry leaks outside the reference skin.
    for name, alpha in (("jaw", jaw), ("clavicle", clav)):
        n = int(np.count_nonzero(alpha > 0.01))
        if n < 8:
            raise SystemExit(f"[neck-details] {name}: only {n} pixels survived skin clipping")
        leaks = int(np.count_nonzero((alpha > 0.0) & ~skin))
        if leaks:
            raise SystemExit(f"[neck-details] {name}: {leaks} alpha pixels escaped the reference skin mask")
    _write_keyed(os.path.join(redraw, "sheetcut_chin_shadow_short.png"), jaw, JAW_RGB, JAW_PEAK)
    _write_keyed(os.path.join(redraw, "sheetcut_clavicle_line_short.png"), clav, CLAVICLE_RGB, CLAVICLE_PEAK)

    # A before/after source proof for tuning only; final verification must use
    # the live engine render, not this static design-sheet composite.
    preview = rgb.copy().astype(np.float32)
    for alpha, shade in ((jaw, JAW_RGB), (clav, CLAVICLE_RGB)):
        f = alpha[..., None]
        preview = preview * (1.0 - f + f * shade[None, None, :] / 255.0)
    Image.fromarray(np.clip(preview, 0, 255).astype(np.uint8), "RGB").save(
        "/tmp/zc_t679_neck_details_reference_preview.png")

    if a.update_attachments:
        table_path = os.path.join(design, "attachments.json")
        with open(table_path, encoding="utf-8") as f:
            table = json.load(f)
        slot_defs = [
            {"id": "neck_cast_shadow", "label": "下颏落影（头侧）", "layer": 179,
             "group": "head", "anchor": [0.5, 0.0], "curve": "root",
             "note": "T67.9：下颏阴影叠在颈部底色上、藏于 seg_head 轮廓之下；跟随 head。"},
            {"id": "neck_clavicle_detail", "label": "颈根/锁骨细节", "layer": 101,
             "group": "chest", "anchor": [0.5, 0.0], "curve": "root",
             "note": "T67.9：仅叠在原图明确可见的颈根皮肤范围，服装仍由皮肤 alpha/color gate 遮开。"},
        ]
        slots = {x["id"]: x for x in table.get("slots", [])}
        for slot in slot_defs:
            slots[slot["id"]] = slot
        table["slots"] = list(slots.values())
        rows = {x["id"]: x for x in table.get("attachments", [])}
        definitions = [
            ("chin_neck_shadow", "sheetcut_chin_shadow_short.png", "chin_neck_shadow.png",
             "neck_cast_shadow", "socket_face", jaw,
             "下颏落影：独立柔乘算片，按原始颌线曲率向颈部衰减；跟头动，只在皮肤上有效。"),
            ("clavicle_line", "sheetcut_clavicle_line_short.png", "clavicle_line.png",
             "neck_clavicle_detail", "socket_neck", clav,
             "颈根锁骨提示线：短、浅、只落在参考图可见皮肤；不把锁骨画到衬衫或夹克上。"),
        ]
        for pid, src_name, sprite, slot_id, socket_id, alpha, note in definitions:
            geom = _geometry(a.character, a.form, alpha, socket_id)
            rows[pid] = {
                "id": pid, "label": slot_id, "forms": ["teen"], "slot": slot_id,
                "sprite": sprite, "anchor": [0.5, 0.0],
                "tags": ["neck", "shadow" if "shadow" in pid else "structure"],
                "source": src_name, "unit": geom["unit"],
                "socket": geom["socket"], "dpos_rel": geom["dpos_rel"],
                "sprite_h_rel": geom["sprite_h_rel"], "width_ratio": geom["width_ratio"],
                "layer": slot_defs[0]["layer"] if slot_id == "neck_cast_shadow" else slot_defs[1]["layer"],
                "blend": "multiply", "solid_fill": False, "note": note,
            }
        table["attachments"] = list(rows.values())
        with open(table_path, "w", encoding="utf-8") as f:
            json.dump(table, f, ensure_ascii=False, indent=2)
            f.write("\n")
    print("[neck-details] jaw pixels=%d max_alpha=%d; clavicle pixels=%d max_alpha=%d" % (
        int(np.count_nonzero(jaw > 0.01)), int(jaw.max() * 255),
        int(np.count_nonzero(clav > 0.01)), int(clav.max() * 255)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
