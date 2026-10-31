#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Generate the hood-up inner cast-shadow as a soft multiply attachment.

The registered short-hair hood sheet is the visual truth source.  The shadow is
kept as an independent, hood_pose-gated part (rather than painted into hair or
hood fabric), placed in the same template/body coordinate transform as the hood.
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
MAGENTA = np.array([255.0, 0.0, 255.0])
SHADOW_RGB = np.array([82.0, 82.0, 82.0])  # neutral multiply; preserves the hair's lavender hue
PEAK_ALPHA = 0.56
MARGIN = 0.04


def _load_geometry(character: str, form: str, source: np.ndarray, alpha: np.ndarray):
    ys, xs = np.nonzero(alpha > 0.35)
    if not len(xs):
        raise SystemExit("[hood-shadow] empty shadow mask")
    x0, x1, y0, y1 = int(xs.min()), int(xs.max()) + 1, int(ys.min()), int(ys.max()) + 1

    design = os.path.join(ROOT, "characters", character, "design")
    form_root = os.path.join(ROOT, "characters", character, "forms", form)
    base = os.path.join(design, "design_sheet_short.png")
    _, base_op = C.key_rgba(base)
    by, bx = np.nonzero(base_op)
    bbox = (int(bx.min()), int(by.min()), int(bx.max()), int(by.max()))
    char_h = bbox[3] - bbox[1] + 1
    scale = (C.TARGET_CANVAS[1] * C.HEIGHT_RATIO) / char_h
    with open(os.path.join(form_root, "design", "anchors.json"), encoding="utf-8") as fh:
        anchors = json.load(fh)
    unit = float(anchors["meta"]["head_ratio"]) * float(anchors["meta"]["height_px"])
    head_top = anchors["points"]["head_top"]

    # Match the attachment pipeline's 4% transparent crop margin and the
    # registered sheet -> body_full transform used by cut_hood_from_sheets.
    cx = (x0 + x1) / 2.0
    top = y0 - MARGIN * (y1 - y0)
    cx_body = (cx - bbox[0]) * scale
    top_body = (top - bbox[1]) * scale
    pos_rel = [(cx_body - float(head_top[0])) / unit,
               (top_body - float(head_top[1])) / unit]
    sprite_h_rel = (y1 - y0) * (1.0 + 2.0 * MARGIN) * scale / unit

    # The hood uses socket_head_top. Calculate the equivalent socket-relative
    # offset so both parts share the same parent/pivot and follow head motion.
    sockets = attach_geom.load_sockets(os.path.join(ROOT, "characters", character))
    socket = next((s for s in sockets.values() if s["id"] == "socket_head_top"), None)
    if socket is None:
        raise SystemExit("[hood-shadow] missing socket_head_top")
    base_x = float(head_top[0]) + float(socket["pos_rel"][0]) * unit
    base_y = float(head_top[1]) + float(socket["pos_rel"][1]) * unit
    dpos_rel = [(cx_body - base_x) / unit,
                (top_body - base_y) / unit]

    geom = {
        "source": "sheetcut_hood_inner_shadow_short.png",
        "pos_rel": [round(v, 6) for v in pos_rel],
        "dpos_rel": [round(v, 6) for v in dpos_rel],
        "sprite_h_rel": round(sprite_h_rel, 6),
        "width_ratio": 1.0,
        "template_bbox": [x0, y0, x1, y1],
        "scale_sheet_to_bodyfull": round(scale, 6),
    }
    return geom


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--character", default="xiaoxun")
    ap.add_argument("--form", default="teen")
    ap.add_argument("--update-attachments", action="store_true")
    a = ap.parse_args()

    design = os.path.join(ROOT, "characters", a.character, "design")
    ref_path = os.path.join(design, "sheets", "sheet_short_hood.png")
    ref = np.asarray(Image.open(ref_path).convert("RGB"), dtype=np.uint8)
    h, w = ref.shape[:2]
    yy, xx = np.mgrid[0:h, 0:w]
    r = ref[..., 0].astype(np.int16)
    g = ref[..., 1].astype(np.int16)
    b = ref[..., 2].astype(np.int16)

    # Trace the lower edge of the hood's inner rib at the top of the opening.
    # The cast shadow fades down across the hair, following the arch; warm skin,
    # mint lining and white shell are excluded by a cool-hair color gate.
    dx = xx.astype(np.float32) - 512.0
    rim_y = 166.0 + 0.0080 * dx * dx
    depth = yy.astype(np.float32) - rim_y
    xfade = np.clip(np.minimum((xx - 406.0) / 20.0, (620.0 - xx) / 20.0), 0.0, 1.0)
    xfade = xfade * xfade * (3.0 - 2.0 * xfade)
    inward = np.clip((depth - 1.0) / 28.0, 0.0, 1.0)
    falloff = (1.0 - inward) ** 1.65
    ramp = np.clip((depth - 0.5) / 4.0, 0.0, 1.0)
    # Hair is cool lavender/blue; the boundary avoids warm skin, mint cloth,
    # and the pale jacket even where their values approach the same brightness.
    hair = ((b >= r - 8) & (b >= g + 4) & (g <= r + 18))
    region = ((xx >= 406) & (xx <= 620) & (yy >= 150) & (yy <= 288)
              & (depth >= 0.5) & (depth <= 30.0))
    alpha = PEAK_ALPHA * falloff * ramp * xfade * hair * region

    # Slightly soften the color-class boundary; the geometric falloff remains
    # responsible for the cast-shadow edge, not a hard polygon contour.
    alpha_img = Image.fromarray(np.clip(alpha * 255.0, 0, 255).astype(np.uint8), "L")
    alpha_img = alpha_img.filter(ImageFilter.GaussianBlur(0.65))
    alpha = np.asarray(alpha_img, dtype=np.float32) / 255.0
    alpha[~region] = 0.0

    # Encode RGBA coverage over the pipeline's magenta key. Neutral RGB makes
    # key_alpha_soft recover the requested soft alpha exactly.
    keyed = (MAGENTA[None, None, :] * (1.0 - alpha[..., None])
             + SHADOW_RGB[None, None, :] * alpha[..., None])
    keyed = np.clip(keyed, 0, 255).astype(np.uint8)
    source_path = os.path.join(design, "redraw", "sheetcut_hood_inner_shadow_short.png")
    Image.fromarray(keyed, "RGB").save(source_path)

    geom = _load_geometry(a.character, a.form, ref, alpha)
    geom_path = os.path.join(design, "sheets", "hood_inner_shadow_geometry.json")
    with open(geom_path, "w", encoding="utf-8") as fh:
        json.dump(geom, fh, ensure_ascii=False, indent=2)
        fh.write("\n")

    # An overlaid reference proof is kept only in /tmp, not as generated repo art.
    preview = Image.fromarray(ref.copy(), "RGB")
    tint = np.array([88.0, 90.0, 118.0], dtype=np.float32)
    base_rgb = np.asarray(preview, dtype=np.float32)
    out = base_rgb * (1.0 - alpha[..., None]) + tint[None, None, :] * alpha[..., None]
    Image.fromarray(np.clip(out, 0, 255).astype(np.uint8), "RGB").save(
        "/tmp/zc_t679_shadow_reference_preview.png")

    if a.update_attachments:
        table_path = os.path.join(design, "attachments.json")
        with open(table_path, encoding="utf-8") as fh:
            table = json.load(fh)
        item = {
            "id": "hood_inner_shadow",
            "label": "兜帽内侧投影",
            "forms": [a.form],
            "slot": "head_over_hair",
            "sprite": "hood_inner_shadow.png",
            "anchor": [0.5, 0.0],
            "tags": ["hood", "shadow"],
            "pose_group": "hood_pose",
            "pose_id": "up",
            "source": "sheetcut_hood_inner_shadow_short.png",
            "ref": "head_top",
            "unit": "head",
            "socket": "socket_head_top",
            "dpos_rel": geom["dpos_rel"],
            "sprite_h_rel": geom["sprite_h_rel"],
            "width_ratio": geom["width_ratio"],
            "layer": 250,
            "blend": "multiply",
            "solid_fill": False,
            "note": ("T67.9：独立乘算投影，随 socket_head_top 与兜帽同动；"
                     "仅在 hood_pose=up 显示，遮在帽体之下、头发之上。"
                     "参考 sheet_short_hood 的内沿落影，软边只覆冷色发区。")
        }
        items = table.setdefault("attachments", [])
        old = next((x for x in items if x.get("id") == item["id"]), None)
        if old is None:
            items.append(item)
        else:
            old.update(item)
        with open(table_path, "w", encoding="utf-8") as fh:
            json.dump(table, fh, ensure_ascii=False, indent=2)
            fh.write("\n")

    print("[hood-shadow] source=%s bbox=%s pos_rel=%s dpos_rel=%s h_rel=%.6f"
          % (source_path, geom["template_bbox"], geom["pos_rel"],
             geom["dpos_rel"], geom["sprite_h_rel"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
