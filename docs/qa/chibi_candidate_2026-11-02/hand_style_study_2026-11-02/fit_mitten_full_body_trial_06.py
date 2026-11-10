#!/usr/bin/env python3
"""Fit hand silhouettes from full-body WIP concept 06 under exact Chibi source cuffs.

The full-body concept is an unapproved AI style study. This tool crops only its
visible hand regions after the full-body concept exists, selects existing
hand/outline pixels, maps color to the Chibi source palette, and uses the
source-measured fit/cuff helpers. It never draws a hand and never writes to
production assets. Outputs are isolated WIP and must not be treated as approved.
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
    SHEET_PATH,
    SOURCE_MANIFEST_PATH,
    component,
    dilate,
    erase_source_hand,
    extract_ai_hand,
    make_variant,
    sample_source_skin_palette,
    sha,
    source_cuff_and_hand,
)

FULL_BODY_TRIAL = OUT / "chibi_full_body_mitten_concept_trial_06_wip.png"
# Crops are measured from the generated full-body concept; first source is full-body,
# then these hand-only regions are selected. Coordinates are exclusive XYXY.
AI_HAND_CROPS = {
    "left": (320, 600, 440, 730),
    "right": (590, 600, 710, 730),
}
CROP_NAMES = {side: f"mitten_trial_06_{side}_source_crop_wip.png" for side in AI_HAND_CROPS}
CUTOUT_NAMES = {side: f"mitten_trial_06_{side}_tight_hand_source_pixels_wip.png" for side in AI_HAND_CROPS}
VARIANT_NAMES = {side: f"mitten_{side}_ai_trial06_source_cuff_wip.png" for side in AI_HAND_CROPS}
PREVIEW_NAME = "body_full_ai_trial06_source_cuff_preview_wip.png"
BOARD_NAME = "chibi_mitten_trial_06_source_cuff_candidate_board_wip.png"
METRICS_NAME = "mitten_trial_06_source_cuff_metrics.json"


def font(size: int):
    try:
        return ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", size)
    except OSError:
        return ImageFont.load_default()


def select_original_ai_hand_pixels(crop: Image.Image) -> tuple[Image.Image, dict]:
    """Select the full-body trial's warm hand + 2px neighborhood of source pixels."""
    rgb = np.asarray(crop.convert("RGB")).astype(np.int16)
    r, g, b = rgb.transpose(2, 0, 1)
    warm = (r > 175) & (g > 100) & (g < 245) & (b > 70) & (r > g * 1.03) & (g > b * 1.02)
    skin = component(warm)
    if not skin.any():
        raise RuntimeError("Full-body trial crop contains no warm hand component")
    near = dilate(skin, 2)
    # The full-body AI reference has a solid magenta key background. Retain only
    # existing non-magenta pixels in this small neighborhood; no silhouette is drawn.
    non_magenta = ~((r > 180) & (g < 100) & (b > 180))
    # Exclude AI sleeve/cuff colors even when they touch the hand at the crop edge.
    teal_cuff = (g > r + 14) & (b > r + 8) & (g > 85) & (g < 245)
    cream_cuff = (rgb.min(axis=2) > 205) & ((r - g) < 8) & ((g - b) < 12)
    non_cuff = ~(teal_cuff | cream_cuff)
    mask = skin | (near & non_magenta & non_cuff)
    ys, xs = np.where(mask)
    x0, y0, x1, y1 = int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1
    rgba = np.zeros((*mask.shape, 4), dtype=np.uint8)
    rgba[mask, :3] = rgb[mask].astype(np.uint8)
    rgba[mask, 3] = 255
    hand = Image.fromarray(rgba, "RGBA").crop((x0, y0, x1, y1))
    return hand, {
        "warm_skin_component_px": int(skin.sum()),
        "excluded_ai_cuff_like_neighbors_px": int((near & (teal_cuff | cream_cuff) & ~skin).sum()),
        "selected_original_pixels_px": int(mask.sum()),
        "tight_bbox_in_fullbody_crop_xyxy_exclusive": [x0, y0, x1, y1],
        "tight_size": [hand.width, hand.height],
        "pixel_source": "selected unchanged RGB values from full-body AI trial crop; outside mask transparent",
    }


def source_composite(body: Image.Image, side: str, hand: Image.Image) -> tuple[Image.Image, dict, dict]:
    crop = body.crop(BOXES[side]).convert("RGBA")
    cuff_cover, skin_component, source_metrics = source_cuff_and_hand(crop)
    target_bbox = source_metrics["source_hand_bbox_xyxy_exclusive_with_1px_outline_margin"]
    palette = sample_source_skin_palette(np.asarray(crop), skin_component)
    mapped, ai_metrics = extract_ai_hand(hand, palette)
    variant, fit_metrics = make_variant(body, side, mapped, cuff_cover, target_bbox)
    src_rgba = np.asarray(crop)
    fitted_rgba = np.asarray(variant)
    if not np.array_equal(src_rgba[cuff_cover], fitted_rgba[cuff_cover]):
        raise AssertionError(f"{side} fitted cuff pixels differ from Chibi source")
    cuff_pixel_sha = hashlib.sha256(np.ascontiguousarray(src_rgba[cuff_cover]).tobytes()).hexdigest()
    cuff_metrics = {
        "source_cuff_pixel_identity_verified": True,
        "source_cuff_selected_pixel_count": int(cuff_cover.sum()),
        "source_cuff_selected_rgba_sha256": cuff_pixel_sha,
    }
    return variant, {**source_metrics, **fit_metrics, **cuff_metrics}, {**ai_metrics, "source_sampled_palette": palette}


def main() -> None:
    body = Image.open(BODY_PATH).convert("RGBA")
    full_trial = Image.open(FULL_BODY_TRIAL).convert("RGB")
    preview = body.copy()
    metrics: dict = {
        "status": "isolated_full_body_ai_concept_fit_wip_not_production",
        "tool": {"path": Path(__file__).name, "sha256": sha(Path(__file__))},
        "method": "begin with full-body AI concept 06; crop left/right hand regions; select existing warm hand pixels and a 2px adjacent non-magenta, non-cuff-color source-pixel neighborhood; map to source-sampled Chibi tones; fit uniformly to each original Chibi small-hand box; composite exact source cuff over the underlapping hand",
        "sources": {
            "full_body_trial_06": {"path": FULL_BODY_TRIAL.name, "sha256": sha(FULL_BODY_TRIAL), "size": list(full_trial.size)},
            "body_full": {"path": "characters/xiaoxun/forms/chibi/sprites/body_full.png", "sha256": sha(BODY_PATH)},
            "design_sheet_chibi": {"path": "characters/xiaoxun/design/design_sheet_chibi.png", "sha256": sha(SHEET_PATH)},
            "source_crop_manifest": {"path": SOURCE_MANIFEST_PATH.name, "sha256": sha(SOURCE_MANIFEST_PATH)},
            "full_body_hand_crop_xyxy_exclusive": {side: list(box) for side, box in AI_HAND_CROPS.items()},
            "source_roi_xyxy_exclusive": BOXES,
        },
        "hands": {},
        "visual_review": {
            "viewed_artifacts": [
                "chibi_full_body_mitten_trial_06_review_board_wip.png",
                "chibi_full_body_mitten_trial_06_wrist_detail_wip.png",
                BOARD_NAME,
                PREVIEW_NAME,
                *VARIANT_NAMES.values(),
                *CUTOUT_NAMES.values(),
            ],
            "observations": [
                "Trial 06 shows rounded mitten-like hand shapes in a complete Chibi figure, following the full-body-first workflow; the openings remain small and the shape reads as a mitten concept.",
                "Tight 45x43 left/right hand selections visually exclude the skirt/shirt fragments picked up by the earlier broad-neighborhood diagnostic masks; no AI cuff/body pixels were used in the fitted silhouettes.",
                "Per-side selected source-cuff RGBA pixel identity assertions passed; the exact Chibi cuff pixels remain present in both fitted WIP crops.",
                "At 4x, despite exact cuffs, the shorter fitted silhouette and cuff-facing contour leave visible uneven wrist transitions/transparent slivers, most evident on the left; a warm/pale seam band and outline-density mismatch remain. Static crop fit is not seam-clean.",
                "The full-body AI image also changes facial line detail, hair rendering, jacket/skirt/shoe details and exact proportions compared with the source sheet; reject the whole image as production art.",
            ],
            "decision": "shape_only_concept_reference_not_reusable_hand_art_or_approved_fit",
        },
        "limits": [
            "AI full-body concept 06 is not user-approved original Chibi art and is not a production source.",
            "The 2px neighborhood selection is a WIP pixel selector, not an artist-approved final hand mask.",
            "No hidden wrist continuation under the cuff was fabricated; motion/rotation and C-engine fit are untested.",
            "No Teen hand asset, generic raw hand image, or user-marked screenshot pixels were used.",
            "No production sprite, rig, generator, or engine changed.",
        ],
        "files": {},
    }
    for side, box in AI_HAND_CROPS.items():
        crop_path = OUT / CROP_NAMES[side]
        crop = full_trial.crop(box)
        crop.save(crop_path)
        raw_hand, selection_metrics = select_original_ai_hand_pixels(crop)
        cutout_path = OUT / CUTOUT_NAMES[side]
        raw_hand.save(cutout_path)
        variant, fit_metrics, ai_metrics = source_composite(body, side, cutout_path)
        variant_path = OUT / VARIANT_NAMES[side]
        variant.save(variant_path)
        source_box = BOXES[side]
        old_crop = body.crop(source_box).convert("RGBA")
        cuff, skin, _ = source_cuff_and_hand(old_crop)
        erased = erase_source_hand(old_crop, cuff, skin)
        preview.paste(erased, (source_box[0], source_box[1]))
        preview.alpha_composite(variant, (source_box[0], source_box[1]))
        metrics["hands"][side] = {
            "full_body_crop_file": CROP_NAMES[side],
            "full_body_crop_sha256": sha(crop_path),
            "selected_hand_cutout_file": CUTOUT_NAMES[side],
            "selected_hand_cutout_sha256": sha(cutout_path),
            "selection": selection_metrics,
            "fit": fit_metrics,
            "ai_and_palette": ai_metrics,
            "source_body_file_sha256": sha(BODY_PATH),
            "output_sha256": sha(variant_path),
        }
    preview_path = OUT / PREVIEW_NAME
    preview.save(preview_path)

    board = Image.new("RGB", (1500, 1040), (248, 247, 245))
    draw = ImageDraw.Draw(board)
    title, small = font(23), font(15)
    draw.text((24, 22), "XIAOXUN CHIBI · FULL-BODY TRIAL 06 SOURCE-CUFF FIT · WIP / NOT PRODUCTION", font=title, fill=(50, 44, 62))
    draw.text((24, 56), "Full-body concept first; visible hand pixels selected afterwards. Original source cuff retained; art approval still required.", font=small, fill=(74, 68, 83))
    for i, (art, caption) in enumerate(((body.copy(), "source body_full"), (preview.copy(), "source body + trial 06 hands"))):
        art.thumbnail((160, 390), Image.Resampling.LANCZOS)
        x = 25 + i * 180
        draw.text((x, 95), caption, font=small, fill=(74, 68, 83))
        bg = Image.new("RGBA", art.size, (235, 234, 239, 255))
        bg.alpha_composite(art.convert("RGBA"))
        board.paste(bg.convert("RGB"), (x, 120))
    for i, side in enumerate(("left", "right")):
        x = 430 + i * 510
        draw.text((x, 112), f"{side} · original Chibi small vs trial 06 fit", font=title, fill=(50, 44, 62))
        source_crop = body.crop(BOXES[side]).convert("RGBA")
        variant = Image.open(OUT / VARIANT_NAMES[side]).convert("RGBA")
        for row, art in enumerate((source_crop, variant)):
            zoom = art.resize((art.width * 4, art.height * 4), Image.Resampling.NEAREST)
            bg = Image.new("RGBA", zoom.size, (235, 234, 239, 255))
            bg.alpha_composite(zoom)
            board.paste(bg.convert("RGB"), (x, 150 + row * 390))
            draw.text((x, 150 + row * 390 + 372), "original Chibi small · 4×" if row == 0 else "trial 06 hand + source cuff · 4×", font=small, fill=(74, 68, 83))
    draw.text((430, 940), "AI concept remains unapproved; full-body source drift, outline/style and warm seam remain non-final.", font=small, fill=(116, 52, 56))
    board_path = OUT / BOARD_NAME
    board.save(board_path)
    metrics["files"] = {
        BOARD_NAME: sha(board_path),
        PREVIEW_NAME: sha(preview_path),
        **{name: sha(OUT / name) for name in (*CROP_NAMES.values(), *CUTOUT_NAMES.values(), *VARIANT_NAMES.values())},
    }
    (OUT / METRICS_NAME).write_text(json.dumps(metrics, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("wrote trial 06 source-cuff hand fit WIP; not production art")


if __name__ == "__main__":
    main()
