#!/usr/bin/env python3
"""Extract visible small-hand pixels from Chibi body_full for isolated study.

This is a source-pixel selection diagnostic, not hand drawing, repainting, or a
production cutout. It preserves original RGB/alpha for selected pixels only;
there is no resampling, recoloring, or generated hand geometry. The cuff-hidden
wrist continuation is not present in body_full and is intentionally not invented.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from fit_mitten_source_cuff_trial import (
    BODY_PATH,
    BOXES,
    OUT,
    SOURCE_MANIFEST_PATH,
    component,
    dilate_one,
    source_cuff_and_hand,
)

OUTPUT_NAMES = {
    "left": "chibi_small_left_source_pixels_wip.png",
    "right": "chibi_small_right_source_pixels_wip.png",
}
BOARD_NAME = "chibi_small_hand_source_extraction_board_wip.png"
METRICS_NAME = "chibi_small_hand_source_extraction_metrics.json"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def font(size: int):
    try:
        return ImageFont.truetype("DejaVuSans.ttf", size)
    except OSError:
        return ImageFont.load_default()


def main() -> None:
    body = Image.open(BODY_PATH).convert("RGBA")
    metrics: dict = {
        "status": "isolated_source_pixel_reference_wip_not_production",
        "method": "select the measured Chibi source warm-skin connected component and original-alpha contour pixels within a 3px neighborhood; exclude source cuff mask; preserve selected RGB/alpha exactly; no drawing, recoloring, or resizing of saved cutouts",
        "limitations": [
            "The hidden wrist continuation under the cuff is not present in body_full and was not invented; this is not a rig-ready hand part.",
            "Selection is a color/component diagnostic and must be visually checked for missing or extraneous contour pixels.",
            "This documents only the existing small-hand source, not original mitten artwork or approval of AI mitten trials.",
            "No production sprite, rig, generator, or engine was changed.",
        ],
        "sources": {
            "body_full": {
                "path": "characters/xiaoxun/forms/chibi/sprites/body_full.png",
                "sha256": sha(BODY_PATH),
            },
            "source_crop_manifest": {
                "path": SOURCE_MANIFEST_PATH.name,
                "sha256": sha(SOURCE_MANIFEST_PATH),
            },
        },
        "hands": {},
        "files": {},
    }
    board = Image.new("RGB", (1440, 1080), (248, 247, 245))
    draw = ImageDraw.Draw(board)
    title = font(26)
    label = font(17)
    draw.text((20, 18), "CHIBI SMALL HAND · EXACT SOURCE-PIXEL EXTRACTION · WIP / NOT A RIG PART", font=title, fill=(40, 36, 48))
    draw.text((20, 52), "No redrawing, recoloring, interpolation, Teen asset, or screenshot pixels; hidden under-cuff continuation intentionally absent.", font=label, fill=(86, 78, 95))

    for index, side in enumerate(("left", "right")):
        roi = BOXES[side]
        source_crop = body.crop(roi)
        cuff_cover, skin_component, source_metrics = source_cuff_and_hand(source_crop)
        # The hand's thin colored contour sits a few pixels outside the warm fill.
        # Keep a 3px source-pixel neighborhood, but only where original alpha exists;
        # this selects existing contour/AA pixels rather than drawing a new outline.
        source_rgba = np.asarray(source_crop).copy()
        hand_mask = dilate_one(skin_component)
        for _ in range(2):
            hand_mask = dilate_one(hand_mask)
        hand_mask &= (source_rgba[..., 3] > 32) & ~cuff_cover
        source_ys, source_xs = np.where(skin_component)
        x0 = max(0, int(source_xs.min()) - 3)
        y0 = max(0, int(source_ys.min()) - 3)
        x1 = min(source_crop.width, int(source_xs.max()) + 4)
        y1 = min(source_crop.height, int(source_ys.max()) + 4)
        rgba = source_rgba.copy()
        rgba[~hand_mask, 3] = 0
        rgba[~hand_mask, :3] = 0
        hand = Image.fromarray(rgba, "RGBA").crop((x0, y0, x1, y1))
        output = OUT / OUTPUT_NAMES[side]
        hand.save(output)
        # Verify that every visible exported pixel is byte-for-byte present in
        # the corresponding registered body_full region after PNG round-trip.
        source_region = source_rgba[y0:y1, x0:x1]
        saved = np.asarray(Image.open(output).convert("RGBA"))
        visible = saved[..., 3] > 0
        if not np.array_equal(saved[visible], source_region[visible]):
            raise RuntimeError(f"Export changed source pixels for {side} hand")

        # Board images are nearest-neighbor enlargements for pixel inspection only.
        col_x = 20 + index * 700
        draw.text((col_x, 86), f"{side} source ROI · 5× nearest-neighbor", font=label, fill=(74, 68, 83))
        roi_zoom = source_crop.resize((source_crop.width * 5, source_crop.height * 5), Image.Resampling.NEAREST)
        roi_bg = Image.new("RGBA", roi_zoom.size, (235, 234, 239, 255))
        roi_bg.alpha_composite(roi_zoom)
        board.paste(roi_bg.convert("RGB"), (col_x, 112))
        draw.text((col_x, 590), f"{side} selected original pixels · 8× nearest-neighbor · transparent outside mask", font=label, fill=(74, 68, 83))
        hand_zoom = hand.resize((hand.width * 8, hand.height * 8), Image.Resampling.NEAREST)
        bg = Image.new("RGBA", hand_zoom.size, (235, 234, 239, 255))
        bg.alpha_composite(hand_zoom)
        board.paste(bg.convert("RGB"), (col_x, 620))

        gx0, gy0, _, _ = roi
        global_bbox = [gx0 + x0, gy0 + y0, gx0 + x1, gy0 + y1]
        metrics["hands"][side] = {
            **source_metrics,
            "body_full_roi_xyxy_exclusive": list(roi),
            "source_hand_bbox_body_full_xyxy_exclusive": global_bbox,
            "extraction_crop_xyxy_exclusive_with_3px_source_neighborhood": [x0, y0, x1, y1],
            "selected_source_pixel_count": int(hand_mask.sum()),
            "saved_cutout_size": [hand.width, hand.height],
            "saved_cutout_sha256": sha(output),
            "pixel_operation": "exact source pixels and alpha retained inside selected mask; all other cutout pixels transparent",
            "source_rgba_identity_verified_after_png_round_trip": True,
        }
        metrics["files"][OUTPUT_NAMES[side]] = sha(output)

    draw.text((20, 1040), "Inspection only: verify mask edges against source; no hidden hand was fabricated and this does not satisfy mitten art / engine gates.", font=label, fill=(116, 52, 56))
    board_path = OUT / BOARD_NAME
    board.save(board_path)
    metrics["files"][BOARD_NAME] = sha(board_path)
    (OUT / METRICS_NAME).write_text(json.dumps(metrics, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("wrote exact Chibi small-hand source-pixel reference WIP; not production art")


if __name__ == "__main__":
    main()
