#!/usr/bin/env python3
"""Isolated trial-08 hand-pixel/source-cuff fit study; never production art.

This extracts only existing AI-concept hand pixels and tests two placement
anchors against the registered Chibi cuff. It does not synthesize hand shape,
paint hidden wrists, modify the source body, or write production assets.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from fit_mitten_source_cuff_trial import (
    BODY_PATH, BOXES, OUT, SHEET_PATH, SOURCE_MANIFEST_PATH,
    component, dilate, erase_source_hand, fit_hand_to_source,
    sample_source_skin_palette, sha, source_cuff_and_hand,
)

TRIAL = OUT / "chibi_mitten_original_fullbody_concept_trial_08_refined_wip.png"
CROPS = {
    "left": (336, 660, 394, 700),
    "right": (628, 660, 686, 700),
}
CUTOUTS = {side: f"mitten_trial_08_{side}_ai_hand_pixels_wip.png" for side in CROPS}
VARIANTS = {
    side: {
        "bottom": f"mitten_{side}_ai_trial08_bottom_source_cuff_wip.png",
        "cuff_aligned": f"mitten_{side}_ai_trial08_cuff_aligned_source_cuff_wip.png",
    }
    for side in CROPS
}
PREVIEWS = {
    "bottom": "body_full_ai_trial08_bottom_source_cuff_preview_wip.png",
    "cuff_aligned": "body_full_ai_trial08_cuff_aligned_source_cuff_preview_wip.png",
}
BOARD = "chibi_mitten_trial_08_source_cuff_fit_board_wip.png"
METRICS = "mitten_trial_08_source_cuff_fit_metrics.json"


def extract_existing_pixels(crop: Image.Image) -> tuple[Image.Image, dict]:
    """Keep only existing warm hand pixels and the directly adjacent outline."""
    rgb = np.asarray(crop.convert("RGB")).astype(np.int16)
    r, g, b = rgb.transpose(2, 0, 1)
    skin_raw = (r > 175) & (g > 100) & (g < 245) & (b > 70) & (r > g * 1.03) & (g > b * 1.02)
    skin = component(skin_raw)
    if not skin.any():
        raise RuntimeError("No warm hand component in trial-08 window")
    near = dilate(skin, 2)
    # Existing dark plum contour only; no line or fill is drawn.
    outline = (r < 175) & (g < 150) & (b < 195) & (r >= g - 5) & ((b - g) > 5) & near
    keep = skin | outline
    ys, xs = np.where(keep)
    x0, y0, x1, y1 = int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1
    rgba = np.zeros((crop.height, crop.width, 4), dtype=np.uint8)
    rgba[keep, :3] = rgb[keep].astype(np.uint8)
    rgba[keep, 3] = 255
    cutout = Image.fromarray(rgba, "RGBA").crop((x0, y0, x1, y1))
    return cutout, {
        "warm_skin_component_px": int(skin.sum()),
        "preserved_existing_outline_px": int(outline.sum()),
        "selected_existing_pixels_px": int(keep.sum()),
        "crop_xyxy_exclusive": [x0, y0, x1, y1],
        "cutout_size": [cutout.width, cutout.height],
        "pixel_source": "unaltered RGB pixels selected from trial-08 hand and immediately adjacent existing plum outline; outside pixels transparent",
    }


def compose_variant(body: Image.Image, side: str, hand: Image.Image,
                    cuff_cover: np.ndarray, target_bbox: list[int], anchor: str) -> tuple[Image.Image, dict]:
    """Place existing hand pixels under exact source cuff; only placement differs."""
    crop = body.crop(BOXES[side]).convert("RGBA")
    resized, fit = fit_hand_to_source(hand, target_bbox)
    x0, y0, x1, y1 = target_bbox
    x = round((x0 + x1) / 2 - resized.width / 2)
    y = y1 - resized.height if anchor == "bottom" else y0
    local = Image.new("RGBA", crop.size, (0, 0, 0, 0))
    local.alpha_composite(resized, (x, y))

    # Preserve the registered source cuff as the front occluder. Remove only
    # duplicate AI outline pixels directly under its source-derived edge band.
    ai = np.asarray(local).copy()
    r, g, b, alpha = (ai[..., i].astype(np.int16) for i in range(4))
    edge_band = dilate(cuff_cover, 2) & ~cuff_cover
    ai_outline = (alpha > 0) & (r < 180) & (g < 160) & (b < 205) & (r >= g - 5) & ((b - g) > 5)
    remove_line = edge_band & ai_outline
    ai[remove_line, 3] = 0
    ai[remove_line, :3] = 0
    local = Image.fromarray(ai.astype(np.uint8), "RGBA")

    source_cuff = np.asarray(crop).copy()
    source_cuff[~cuff_cover, 3] = 0
    local.alpha_composite(Image.fromarray(source_cuff, "RGBA"))
    return local, {
        **fit,
        "placement_anchor": anchor,
        "actual_placement_xy": [x, y],
        "removed_existing_ai_outline_px_in_2px_cuff_edge_band": int(remove_line.sum()),
        "cuff_overlay": "original registered body_full RGBA pixels selected by source-derived mask",
    }


def font(size: int):
    try:
        return ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", size)
    except OSError:
        return ImageFont.load_default()


def main() -> None:
    body = Image.open(BODY_PATH).convert("RGBA")
    trial = Image.open(TRIAL).convert("RGB")
    cutouts: dict[str, Image.Image] = {}
    source_rois: dict[str, Image.Image] = {}
    variants: dict[str, dict[str, Image.Image]] = {side: {} for side in CROPS}
    full_previews = {anchor: body.copy() for anchor in PREVIEWS}
    metrics = {
        "status": "isolated_trial08_ai_hand_pixels_source_cuff_fit_wip_not_production",
        "tool": {"path": Path(__file__).name, "sha256": sha(Path(__file__))},
        "sources": {
            "approved_visual_concept": {"path": TRIAL.name, "sha256": sha(TRIAL), "size": list(trial.size)},
            "body_full": {"path": "characters/xiaoxun/forms/chibi/sprites/body_full.png", "sha256": sha(BODY_PATH)},
            "design_sheet_chibi": {"path": "characters/xiaoxun/design/design_sheet_chibi.png", "sha256": sha(SHEET_PATH)},
            "source_crop_manifest": {"path": SOURCE_MANIFEST_PATH.name, "sha256": sha(SOURCE_MANIFEST_PATH)},
            "hand_windows_xyxy_exclusive": {side: list(box) for side, box in CROPS.items()},
            "source_hand_roi_xyxy_exclusive": {side: list(box) for side, box in BOXES.items()},
            "placement_tests": ["bottom-aligned-to-source-hand-box", "top-aligned-to-source-hand-box/cuff insertion"],
        },
        "hands": {},
        "limits": [
            "Trial 08 is user-approved as a visual concept direction only; this fit is isolated and not production approval.",
            "Hand silhouettes and outline pixels come from existing trial-08 pixels; no hand shape or hidden-wrist continuation is drawn or generated by this script.",
            "Exact source cuff pixels are composited over each test; this does not make the AI-derived hand a source-original part.",
            "No user-marked screenshot pixels, Teen hand art, or programmatically drawn hand geometry are used.",
            "No production sprite, rig, generator, or C-engine state changed.",
        ],
    }
    for side, window in CROPS.items():
        cutout, extraction = extract_existing_pixels(trial.crop(window))
        cutout_path = OUT / CUTOUTS[side]
        cutout.save(cutout_path)
        cutouts[side] = cutout
        source_roi = body.crop(BOXES[side]).convert("RGBA")
        source_rois[side] = source_roi
        cuff_cover, source_skin, source_metrics = source_cuff_and_hand(source_roi)
        palette = sample_source_skin_palette(np.asarray(source_roi), source_skin)
        target = source_metrics["source_hand_bbox_xyxy_exclusive_with_1px_outline_margin"]
        side_metrics = {"trial08_extraction": extraction, "source": source_metrics, "source_palette_for_comparison_only": {k: list(v) if isinstance(v, tuple) else v for k, v in palette.items()}}
        for anchor in ("bottom", "cuff_aligned"):
            variant, placement = compose_variant(body, side, cutout, cuff_cover, target, anchor)
            out_path = OUT / VARIANTS[side][anchor]
            variant.save(out_path)
            variants[side][anchor] = variant
            original = np.asarray(source_roi)
            observed = np.asarray(variant)
            if not np.array_equal(original[cuff_cover], observed[cuff_cover]):
                raise AssertionError(f"{side}/{anchor}: source cuff pixel identity failed")
            placement["source_cuff_pixel_identity_verified"] = True
            placement["source_cuff_selected_pixel_count"] = int(cuff_cover.sum())
            placement["source_cuff_rgba_sha256"] = hashlib.sha256(np.ascontiguousarray(original[cuff_cover]).tobytes()).hexdigest()
            side_metrics[anchor] = placement
            erased = erase_source_hand(source_roi, cuff_cover, source_skin)
            preview = full_previews[anchor]
            preview.paste(erased, BOXES[side][:2])
            preview.alpha_composite(variant, BOXES[side][:2])
        metrics["hands"][side] = side_metrics

    for anchor, filename in PREVIEWS.items():
        full_previews[anchor].save(OUT / filename)

    board = Image.new("RGB", (1450, 1570), (247, 246, 244))
    draw = ImageDraw.Draw(board)
    title, label, note = font(24), font(18), font(15)
    draw.text((24, 20), "TRIAL 08 · SOURCE-CUFF HAND FIT TEST · WIP / NOT PRODUCTION", font=title, fill=(48, 42, 59))
    draw.text((24, 58), "Source cuff RGBA is preserved; only existing AI hand pixels are extracted. Compare two placements at 5×.", font=note, fill=(72, 66, 80))
    for col, side in enumerate(("left", "right")):
        x = 28 + col * 710
        draw.text((x, 100), f"{side.upper()} · original small vs trial-08 fit", font=label, fill=(48, 42, 59))
        arts = [
            (source_rois[side], "source small + source cuff"),
            (variants[side]["bottom"], "source-cuff fit · bottom aligned"),
            (variants[side]["cuff_aligned"], "source-cuff fit · cuff aligned"),
        ]
        for row, (art, caption) in enumerate(arts):
            enlarged = art.resize((art.width * 5, art.height * 5), Image.Resampling.NEAREST)
            bg = Image.new("RGBA", enlarged.size, (235, 234, 239, 255))
            bg.alpha_composite(enlarged)
            board.paste(bg.convert("RGB"), (x, 135 + row * 470))
            draw.text((x, 135 + row * 470 + 455), caption, font=note, fill=(72, 66, 80))
    board_path = OUT / BOARD
    board.save(board_path)

    metrics["outputs"] = {
        "cutouts": {side: {"path": CUTOUTS[side], "sha256": sha(OUT / CUTOUTS[side])} for side in CROPS},
        "variants": {side: {anchor: {"path": filename, "sha256": sha(OUT / filename)} for anchor, filename in variants_for_side.items()} for side, variants_for_side in VARIANTS.items()},
        "full_previews": {anchor: {"path": filename, "sha256": sha(OUT / filename)} for anchor, filename in PREVIEWS.items()},
        "board": {"path": BOARD, "sha256": sha(board_path)},
    }
    metrics["visual_review"] = {
        "status": "reviewed_rejected_as_source_aligned_hand_fit",
        "viewed_artifacts": [BOARD, *PREVIEWS.values()],
        "observations": [
            "The source-derived hand windows contain a wide/flat visible trial-08 silhouette; uniform fitting to source width produces a 45x27px hand instead of filling the 45x48px small-hand box.",
            "The bottom-aligned 5x board visibly leaves a large cuff-to-hand gap. Cuff-aligned placement closes the gap but leaves a stubby, weakly outlined hand and still fails to match the source hand's usable wrist length.",
            "The full-body source previews show undersized, faint-looking hand joins and edge artifacts; preserving source cuff pixels alone does not make the AI extraction reusable.",
            "The original cuff layer remains selected from registered body_full pixels; this is a static fit experiment only, not production art or animated hidden-wrist coverage.",
        ],
        "decision": "reject_trial08_flattened_hand_extraction_for_reuse; keep_user_approved_trial08_as_visual_direction; test_independent_hand_art_study",
    }
    (OUT / METRICS).write_text(json.dumps(metrics, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("generated isolated trial-08 source-cuff comparison; visually reviewed as failed fit; not production art")


if __name__ == "__main__":
    main()
