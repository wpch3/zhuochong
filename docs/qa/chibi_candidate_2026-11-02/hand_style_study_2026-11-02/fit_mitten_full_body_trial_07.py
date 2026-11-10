#!/usr/bin/env python3
"""Isolated trial-07 hand-only fit under exact Chibi source cuffs; never production art."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from fit_mitten_source_cuff_trial import (
    BODY_PATH, BOXES, OUT, SHEET_PATH, SOURCE_MANIFEST_PATH, PALETTE,
    component, dilate, erase_source_hand, make_variant,
    sample_source_skin_palette, sha, source_cuff_and_hand,
)

TRIAL = OUT / "chibi_mitten_original_fullbody_concept_trial_07_wip.png"
# Tight windows around the selected concept's two hands; exclusive XYXY on 1024x1024.
CROPS = {
    "left": (329, 639, 402, 701),
    "right": (619, 640, 694, 701),
}
CUTOUTS = {s: f"mitten_trial_07_{s}_tight_hand_source_pixels_wip.png" for s in CROPS}
VARIANTS = {s: f"mitten_{s}_ai_trial07_source_cuff_wip.png" for s in CROPS}
PREVIEW = "body_full_ai_trial07_source_cuff_preview_wip.png"
BOARD = "chibi_mitten_trial_07_source_cuff_candidate_board_wip.png"
METRICS = "mitten_trial_07_source_cuff_metrics.json"


def font(size):
    try:
        return ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", size)
    except OSError:
        return ImageFont.load_default()


def extract_existing_hand_pixels(crop: Image.Image) -> tuple[Image.Image, dict]:
    rgb = np.asarray(crop.convert("RGB")).astype(np.int16)
    r, g, b = rgb.transpose(2, 0, 1)
    warm = (r > 175) & (g > 100) & (g < 245) & (b > 70) & (r > g * 1.03) & (g > b * 1.02)
    skin = component(warm)
    if not skin.any():
        raise RuntimeError("No warm hand component in trial 07 crop")
    near = dilate(skin, 2)
    teal_cuff = (g > r + 14) & (b > r + 8) & (g > 85) & (g < 245)
    cream_cuff = (rgb.min(axis=2) > 205) & ((r - g) < 8) & ((g - b) < 12)
    neutral_background = (rgb.min(axis=2) > 195) & ((rgb.max(axis=2) - rgb.min(axis=2)) < 18)
    non_magenta = ~((r > 180) & (g < 100) & (b > 180))
    keep = skin | (near & non_magenta & ~(teal_cuff | cream_cuff) & ~neutral_background)
    ys, xs = np.where(keep)
    x0, y0, x1, y1 = int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1
    rgba = np.zeros((*keep.shape, 4), dtype=np.uint8)
    rgba[keep, :3] = rgb[keep].astype(np.uint8)
    rgba[keep, 3] = 255
    cutout = Image.fromarray(rgba, "RGBA").crop((x0, y0, x1, y1))
    return cutout, {
        "warm_skin_component_px": int(skin.sum()),
        "selected_original_pixels_px": int(keep.sum()),
        "excluded_cuff_color_neighbors_px": int((near & (teal_cuff | cream_cuff) & ~skin).sum()),
        "excluded_neutral_background_neighbors_px": int((near & neutral_background & ~skin).sum()),
        "tight_bbox_in_crop_xyxy_exclusive": [x0, y0, x1, y1],
        "tight_size": [cutout.width, cutout.height],
        "pixel_source": "original RGB pixels from selected trial 07 warm-hand component and 2px non-cuff/non-neutral neighborhood; outside selection transparent",
    }


def map_to_source_palette(cutout_path: Path, palette: dict) -> tuple[Image.Image, dict]:
    src = Image.open(cutout_path).convert("RGBA")
    rgba_src = np.asarray(src)
    rgb = rgba_src[..., :3].astype(np.int16)
    r, g, b = rgb.transpose(2, 0, 1)
    alpha_src = rgba_src[..., 3]
    warm = (alpha_src > 32) & (r > 175) & (g > 100) & (g < 245) & (b > 70) & (r > g * 1.03) & (g > b * 1.02)
    skin = component(warm)
    if not skin.any():
        raise RuntimeError("Trial 07 tight hand cutout lost its skin component")
    near = dilate(skin, 2)
    # Import only the existing plum contour immediately adjacent to the hand;
    # distant sleeve/clothing contours are not part of the silhouette.
    line = (r < 170) & (g < 145) & (b < 190) & (r >= g - 4) & ((b - g) > 6) & near & (alpha_src > 0)
    mask = skin | line
    lum = 0.2126 * rgb[..., 0] + 0.7152 * rgb[..., 1] + 0.0722 * rgb[..., 2]
    lo, hi = np.percentile(lum[skin], [5, 95])
    t = np.clip((lum - lo) / max(hi - lo, 1), 0, 1)
    shadow = np.asarray(palette["skin_shadow"], dtype=np.float32)
    base = np.asarray(palette["skin"], dtype=np.float32)
    highlight = np.asarray(palette["highlight"], dtype=np.float32)
    colors = shadow[None, None, :] * (1 - t[..., None]) + base[None, None, :] * t[..., None]
    hm = np.clip((t - 0.78) / 0.22, 0, 1)[..., None]
    colors = colors * (1 - hm) + highlight[None, None, :] * hm
    out = np.zeros((*mask.shape, 4), dtype=np.uint8)
    out[..., :3] = np.clip(colors, 0, 255).astype(np.uint8)
    out[line, :3] = PALETTE["outline"]
    out[..., 3] = np.asarray(Image.fromarray((mask.astype(np.uint8) * 255), "L").filter(ImageFilter.GaussianBlur(0.3)))
    hand = Image.fromarray(out, "RGBA")
    return hand, {
        "mapped_skin_pixel_count": int(skin.sum()),
        "adjacent_outline_pixel_count": int(line.sum()),
        "method": "selected warm hand pixels plus only immediately adjacent existing plum contour; luminance mapped to source-sampled Chibi small-hand tones",
        "source_sampled_palette": {k: list(v) if isinstance(v, tuple) else v for k, v in palette.items()},
    }


def main():
    body = Image.open(BODY_PATH).convert("RGBA")
    trial = Image.open(TRIAL).convert("RGB")
    preview = body.copy()
    metrics = {
        "status": "isolated_trial07_ai_hand_only_source_cuff_fit_wip_not_production",
        "tool": {"path": Path(__file__).name, "sha256": sha(Path(__file__))},
        "sources": {
            "selected_full_body_concept": {"path": TRIAL.name, "sha256": sha(TRIAL), "size": list(trial.size)},
            "body_full": {"path": "characters/xiaoxun/forms/chibi/sprites/body_full.png", "sha256": sha(BODY_PATH)},
            "design_sheet_chibi": {"path": "characters/xiaoxun/design/design_sheet_chibi.png", "sha256": sha(SHEET_PATH)},
            "source_crop_manifest": {"path": SOURCE_MANIFEST_PATH.name, "sha256": sha(SOURCE_MANIFEST_PATH)},
            "trial07_hand_crop_xyxy_exclusive": {s: list(b) for s, b in CROPS.items()},
            "source_hand_roi_xyxy_exclusive": BOXES,
        },
        "hands": {},
        "limits": [
            "The selected image is an AI-generated concept even though the user selected it as the current option; it is not source-original pixel art or production approval.",
            "Trial 07 visibly redraws cuff stripe geometry; no AI cuff pixels are used in the fitted variants, which restore exact source Chibi cuff pixels.",
            "No hidden wrist continuation was authored as source art; the AI hand-only silhouette is only a shape test and remains unapproved.",
            "No user-marked screenshot pixels, Teen hand art, or programmatically drawn hand geometry are used.",
            "No production sprite, rig, generator, or C-engine state changed.",
        ],
    }
    for side, box in CROPS.items():
        crop = trial.crop(box)
        crop_path = OUT / f"mitten_trial_07_{side}_source_crop_wip.png"
        crop.save(crop_path)
        cutout, selection = extract_existing_hand_pixels(crop)
        cutout_path = OUT / CUTOUTS[side]
        cutout.save(cutout_path)
        source_crop = body.crop(BOXES[side]).convert("RGBA")
        cuff, skin, source_metrics = source_cuff_and_hand(source_crop)
        palette = sample_source_skin_palette(np.asarray(source_crop), skin)
        mapped, palette_metrics = map_to_source_palette(cutout_path, palette)
        target = source_metrics["source_hand_bbox_xyxy_exclusive_with_1px_outline_margin"]
        variant, fit_metrics = make_variant(body, side, mapped, cuff, target)
        variant_path = OUT / VARIANTS[side]
        variant.save(variant_path)
        src_rgba, out_rgba = np.asarray(source_crop), np.asarray(variant)
        if not np.array_equal(src_rgba[cuff], out_rgba[cuff]):
            raise AssertionError(f"{side} fitted source cuff pixel identity failed")
        cuff_sha = hashlib.sha256(np.ascontiguousarray(src_rgba[cuff]).tobytes()).hexdigest()
        erased = erase_source_hand(source_crop, cuff, skin)
        preview.paste(erased, BOXES[side][:2])
        preview.alpha_composite(variant, BOXES[side][:2])
        metrics["hands"][side] = {
            "source_crop_file": crop_path.name,
            "source_crop_sha256": sha(crop_path),
            "hand_cutout_file": cutout_path.name,
            "hand_cutout_sha256": sha(cutout_path),
            "selection": selection,
            "source_fit": {**source_metrics, **fit_metrics,
                            "source_cuff_pixel_identity_verified": True,
                            "source_cuff_selected_pixel_count": int(cuff.sum()),
                            "source_cuff_selected_rgba_sha256": cuff_sha},
            "palette_mapping": palette_metrics,
            "variant_sha256": sha(variant_path),
        }
    preview_path = OUT / PREVIEW
    preview.save(preview_path)

    board = Image.new("RGB", (1500, 1040), (248, 247, 245))
    draw = ImageDraw.Draw(board)
    title, small = font(23), font(15)
    draw.text((24, 22), "XIAOXUN CHIBI · SELECTED TRIAL 07 HAND-ONLY FIT · WIP / NOT PRODUCTION", font=title, fill=(50, 44, 62))
    draw.text((24, 56), "User-selected full-body concept; only hand silhouettes tested; original source cuffs restored exactly.", font=small, fill=(74, 68, 83))
    for i, (art, caption) in enumerate(((body.copy(), "source body_full"), (preview.copy(), "source body + trial 07 hand shapes"))):
        art.thumbnail((160, 390), Image.Resampling.LANCZOS)
        x = 25 + i * 180
        draw.text((x, 95), caption, font=small, fill=(74, 68, 83))
        bg = Image.new("RGBA", art.size, (235, 234, 239, 255)); bg.alpha_composite(art.convert("RGBA"))
        board.paste(bg.convert("RGB"), (x, 120))
    for i, side in enumerate(("left", "right")):
        x = 430 + i * 510
        draw.text((x, 112), f"{side} · original Chibi small vs trial 07 fit", font=title, fill=(50, 44, 62))
        for row, art in enumerate((body.crop(BOXES[side]).convert("RGBA"), Image.open(OUT / VARIANTS[side]).convert("RGBA"))):
            zoom = art.resize((art.width * 4, art.height * 4), Image.Resampling.NEAREST)
            bg = Image.new("RGBA", zoom.size, (235, 234, 239, 255)); bg.alpha_composite(zoom)
            board.paste(bg.convert("RGB"), (x, 150 + row * 390))
            draw.text((x, 522 + row * 390), "original Chibi small · 4×" if row == 0 else "trial 07 hand + source cuff · 4×", font=small, fill=(74, 68, 83))
    draw.text((430, 940), "Exact cuff pixels preserved; visual hand fit rejected (gap / scale / outline).", font=small, fill=(116, 52, 56))
    board_path = OUT / BOARD
    board.save(board_path)
    metrics["visual_review"] = {
        "status": "reviewed_failed_as_reusable_hand_fit",
        "viewed_artifacts": [BOARD, PREVIEW],
        "observations": [
            "Trial 07 was the user's selected full-body concept option; its initial wrists have larger mittens and only one simplified cuff band instead of the source's two narrow stripes.",
            "The extracted existing hand silhouette is 65x54 / 67x53 and therefore fits uniformly to 45x37 / 45x36 inside the source small-hand boxes; the 4x board visibly shows a large cuff-to-hand gap and insufficient source-style outline detail.",
            "The source cuff RGB/A selection is byte-identical in both variants, but correct cuff pixels do not make the failed hand placement acceptable.",
        ],
        "decision": "retain_trial07_as_selected_full_body_concept_only; reject_hand_fit_for_reuse; refine_full_body_concept_separately",
    }
    metrics["files"] = {name: sha(OUT / name) for name in (BOARD, PREVIEW, *VARIANTS.values(), *CUTOUTS.values(), *(f"mitten_trial_07_{s}_source_crop_wip.png" for s in CROPS))}
    metrics_path = OUT / METRICS
    metrics_path.write_text(json.dumps(metrics, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("generated selected trial 07 source-cuff hand-only WIP; not production art")

if __name__ == "__main__":
    main()
