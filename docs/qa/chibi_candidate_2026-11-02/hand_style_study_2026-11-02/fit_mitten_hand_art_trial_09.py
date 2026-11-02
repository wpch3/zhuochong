#!/usr/bin/env python3
"""Isolated trial-09 hand-art/source-cuff fit study; never production art.

This preserves selected pixels from independently generated left/right hand
studies, uniformly fits them into the measured Chibi source hand boxes, and
composites the registered source cuffs. No hand shape is drawn by code.
"""
from __future__ import annotations
import hashlib
import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from fit_mitten_source_cuff_trial import (
    BODY_PATH, BOXES, OUT, SHEET_PATH, SOURCE_MANIFEST_PATH,
    component, dilate, fit_hand_to_source,
    sample_source_skin_palette, sha, source_cuff_and_hand,
)

TRIALS = {
    "left": OUT / "chibi_mitten_hand_viewer_left_trial_09_art_wip.png",
    "right": OUT / "chibi_mitten_hand_viewer_right_trial_09_art_wip.png",
}
CUTOUTS = {side: f"mitten_trial_09_{side}_ai_hand_pixels_wip.png" for side in TRIALS}
HAND_LAYERS = {side: f"hand_{side}_mitten_trial09_isolated_wip.png" for side in TRIALS}
CUFF_LAYERS = {side: f"cuff_{side}_source_exact_trial09_layer_wip.png" for side in TRIALS}
VARIANTS = {side: f"mitten_{side}_ai_trial09_source_cuff_wip.png" for side in TRIALS}
PREVIEW = "body_full_ai_trial09_source_cuff_preview_wip.png"
BOARD = "chibi_mitten_trial_09_source_cuff_candidate_board_wip.png"
METRICS = "mitten_trial_09_source_cuff_fit_metrics.json"


def extract_pixels(path: Path) -> tuple[Image.Image, dict]:
    src = Image.open(path).convert("RGB")
    rgb = np.asarray(src).astype(np.int16)
    r, g, b = rgb.transpose(2, 0, 1)
    raw_skin = (r > 185) & (r > g + 10) & (g > b + 5) & (b > 85)
    skin = component(raw_skin)
    if not skin.any():
        raise RuntimeError(f"No warm hand pixels found in {path.name}")
    near = dilate(skin, 10)
    # Preserve the existing warm anti-aliased edge and plum contour around the
    # original generated silhouette; neutral background stays excluded.
    skin_aa = near & (r > 170) & (r > g + 4) & (g > b + 2)
    outline = (r < 180) & (g < 155) & (b < 200) & (r >= g - 6) & ((b - g) > 5) & near
    keep = skin | skin_aa | outline
    ys, xs = np.where(keep)
    x0, y0, x1, y1 = int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1
    rgba = np.zeros((src.height, src.width, 4), dtype=np.uint8)
    rgba[keep, :3] = rgb[keep].astype(np.uint8)
    rgba[keep, 3] = 255
    cutout = Image.fromarray(rgba, "RGBA").crop((x0, y0, x1, y1))
    return cutout, {
        "source_file": path.name,
        "source_sha256": sha(path),
        "selected_skin_pixels": int(skin.sum()),
        "selected_existing_outline_pixels": int(outline.sum()),
        "tight_bbox_xyxy_exclusive": [x0, y0, x1, y1],
        "cutout_size": [cutout.width, cutout.height],
        "selection": "existing warm-skin component and nearby existing plum contour only; no generated pixels or geometry added by script",
    }


def map_skin_to_source_palette(cutout: Image.Image, palette: dict) -> tuple[Image.Image, dict]:
    rgba = np.asarray(cutout.convert("RGBA")).copy()
    rgb = rgba[..., :3].astype(np.float32)
    r, g, b = rgb.transpose(2, 0, 1)
    alpha = rgba[..., 3] > 0
    skin = alpha & (r > 165) & (r > g + 4) & (g > b + 2) & (b > 60)
    if int(skin.sum()) < 16:
        raise RuntimeError("Too few warm pixels to map the candidate to source-sampled skin tones")
    lum = 0.2126 * rgb[..., 0] + 0.7152 * rgb[..., 1] + 0.0722 * rgb[..., 2]
    lo, hi = np.percentile(lum[skin], [5, 95])
    t = np.clip((lum - lo) / max(hi - lo, 1), 0, 1)
    shadow = np.asarray(palette["skin_shadow"], dtype=np.float32)
    base = np.asarray(palette["skin"], dtype=np.float32)
    highlight = np.asarray(palette["highlight"], dtype=np.float32)
    mapped = shadow[None, None, :] * (1 - t[..., None]) + base[None, None, :] * t[..., None]
    h = np.clip((t - .78) / .22, 0, 1)[..., None]
    mapped = mapped * (1 - h) + highlight[None, None, :] * h
    rgba[skin, :3] = np.clip(mapped[skin], 0, 255).astype(np.uint8)
    # Keep the AI's existing contour pixels; mapping does not draw a new outline.
    return Image.fromarray(rgba, "RGBA"), {
        "mapped_existing_skin_pixel_count": int(skin.sum()),
        "outline_policy": "preserve selected existing plum contour pixels without drawing",
        "source_palette": {k: list(v) if isinstance(v, tuple) else v for k, v in palette.items()},
    }


def assemble_source_roi(body: Image.Image, side: str, hand: Image.Image,
                       cuff_cover: np.ndarray, source_skin: np.ndarray,
                       target_bbox: list[int]) -> tuple[Image.Image, Image.Image, Image.Image, dict]:
    """Fit existing pixels and composite the exact source cuff as the top layer."""
    source_roi = body.crop(BOXES[side]).convert("RGBA")
    resized, fit = fit_hand_to_source(hand, target_bbox)
    x0, y0, x1, y1 = target_bbox
    x = round((x0 + x1) / 2 - resized.width / 2)
    y = y1 - resized.height
    hand_layer = Image.new("RGBA", source_roi.size, (0, 0, 0, 0))
    hand_layer.alpha_composite(resized, (x, y))

    # Trim only selected AI contour pixels inside the source-derived cuff edge;
    # retain the source cuff itself as a separate, unmodified pixel layer.
    ai = np.asarray(hand_layer).copy()
    r, g, b, alpha = (ai[..., i].astype(np.int16) for i in range(4))
    edge_band = dilate(cuff_cover, 2) & ~cuff_cover
    line = (alpha > 0) & (r < 180) & (g < 155) & (b < 200) & (r >= g - 6) & ((b - g) > 5)
    remove = edge_band & line
    ai[remove, 3] = 0
    ai[remove, :3] = 0
    hand_layer = Image.fromarray(ai.astype(np.uint8), "RGBA")

    source_pixels = np.asarray(source_roi).copy()
    source_cuff_layer_rgba = np.zeros_like(source_pixels)
    source_cuff_layer_rgba[cuff_cover] = source_pixels[cuff_cover]
    source_cuff_layer = Image.fromarray(source_cuff_layer_rgba, "RGBA")

    # Clear the old source hand and cuff only in this isolated composition, then
    # stack the candidate hand behind the original cuff. Production source stays untouched.
    base = np.asarray(source_roi).copy()
    old_hand_edge = dilate(source_skin, 3) & ~cuff_cover
    base[old_hand_edge, 3] = 0
    base[old_hand_edge, :3] = 0
    base[cuff_cover, 3] = 0
    base[cuff_cover, :3] = 0
    base_layer = Image.fromarray(base, "RGBA")
    base_layer.alpha_composite(hand_layer)
    base_layer.alpha_composite(source_cuff_layer)
    return base_layer, hand_layer, source_cuff_layer, {
        **fit,
        "actual_placement_xy": [x, y],
        "removed_ai_outline_pixels_in_source_cuff_edge_band": int(remove.sum()),
        "source_cuff_layer_rgba_identity_verified": bool(np.array_equal(source_cuff_layer_rgba[cuff_cover], source_pixels[cuff_cover])),
        "source_cuff_selected_pixel_count": int(cuff_cover.sum()),
        "source_cuff_rgba_sha256": hashlib.sha256(np.ascontiguousarray(source_pixels[cuff_cover]).tobytes()).hexdigest(),
    }


def font(size: int):
    try:
        return ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", size)
    except OSError:
        return ImageFont.load_default()


def main() -> None:
    body = Image.open(BODY_PATH).convert("RGBA")
    preview = body.copy()
    metrics = {
        "status": "isolated_trial09_ai_hand_art_source_cuff_fit_wip_not_production",
        "tool": {"path": Path(__file__).name, "sha256": sha(Path(__file__))},
        "approved_visual_direction": {
            "path": "chibi_mitten_original_fullbody_concept_trial_08_refined_wip.png",
            "sha256": sha(OUT / "chibi_mitten_original_fullbody_concept_trial_08_refined_wip.png"),
            "user_approved_scope": "visual concept direction only",
        },
        "generation_brief": {
            "method": "two separate image-generation calls, one viewer-left and one viewer-right; no options grid or mirrored duplicate",
            "references": [
                "registered side-specific source cuff/hand ROI",
                "trial-08 user-approved full-body visual concept direction",
            ],
            "intent": "compact rounded mitten with a small side nub, no finger grooves, peach Chibi shading, cuff overlap and wrist extension; standalone neutral-background art study only",
            "limits": "model output may redraw the cuff/line art; only extracted hands are fitted, and the source cuff is restored from body_full for review",
        },
        "source_truth": {
            "body_full": {"path": "characters/xiaoxun/forms/chibi/sprites/body_full.png", "sha256": sha(BODY_PATH)},
            "design_sheet_chibi": {"path": "characters/xiaoxun/design/design_sheet_chibi.png", "sha256": sha(SHEET_PATH)},
            "source_crop_manifest": {"path": SOURCE_MANIFEST_PATH.name, "sha256": sha(SOURCE_MANIFEST_PATH)},
            "registered_rois": {side: list(box) for side, box in BOXES.items()},
        },
        "hands": {},
        "limits": [
            "The two trial-09 hand images are separate AI WIP art studies, not production parts.",
            "Only existing warm-skin and adjacent outline pixels are selected; no programmatic hand geometry is drawn.",
            "The exact source cuff is overlaid from body_full and checked by RGBA identity per selected cuff pixel.",
            "No hidden wrist continuation is invented beyond the existing generated pixels; no hand_style/rig/C-engine check is performed.",
            "No marked screenshot, Teen hand asset, generic-hand source, or production asset is used or modified.",
        ],
    }
    source_rois = {}
    variants = {}
    for side, path in TRIALS.items():
        cutout, extraction = extract_pixels(path)
        cutout_path = OUT / CUTOUTS[side]
        cutout.save(cutout_path)
        source_roi = body.crop(BOXES[side]).convert("RGBA")
        source_rois[side] = source_roi
        cuff_cover, source_skin, source_metrics = source_cuff_and_hand(source_roi)
        palette = sample_source_skin_palette(np.asarray(source_roi), source_skin)
        mapped, palette_metrics = map_skin_to_source_palette(cutout, palette)
        target = source_metrics["source_hand_bbox_xyxy_exclusive_with_1px_outline_margin"]
        variant, hand_layer, cuff_layer, fit_metrics = assemble_source_roi(
            body, side, mapped, cuff_cover, source_skin, target
        )
        hand_layer_path = OUT / HAND_LAYERS[side]
        cuff_layer_path = OUT / CUFF_LAYERS[side]
        out_path = OUT / VARIANTS[side]
        hand_layer.save(hand_layer_path)
        cuff_layer.save(cuff_layer_path)
        variant.save(out_path)
        variants[side] = variant
        if not fit_metrics["source_cuff_layer_rgba_identity_verified"]:
            raise AssertionError(f"{side}: source cuff layer identity failed")
        preview.paste(variant, BOXES[side][:2])
        metrics["hands"][side] = {
            "art_extraction": extraction,
            "source_measurements": source_metrics,
            "source_palette_mapping": palette_metrics,
            "fit": fit_metrics,
            "outputs": {
                "hand_cutout": {"path": CUTOUTS[side], "sha256": sha(cutout_path)},
                "fitted_hand_layer": {"path": HAND_LAYERS[side], "sha256": sha(hand_layer_path)},
                "exact_source_cuff_layer": {"path": CUFF_LAYERS[side], "sha256": sha(cuff_layer_path)},
                "source_cuff_composite": {"path": VARIANTS[side], "sha256": sha(out_path)},
            },
        }

    preview_path = OUT / PREVIEW
    preview.save(preview_path)
    board = Image.new("RGB", (1450, 1020), (247, 246, 244))
    draw = ImageDraw.Draw(board)
    title, label = font(24), font(17)
    draw.text((24, 20), "TRIAL 09 · REJECTED HAND-SCALE FIT · EXACT SOURCE CUFF PRESERVED · WIP", font=title, fill=(48, 42, 59))
    draw.text((24, 58), "User full-body review: hands appear too small and unnatural; static extraction study only, not accepted art. 4× detail.", font=label, fill=(72, 66, 80))
    for i, side in enumerate(("left", "right")):
        x = 28 + i * 710
        draw.text((x, 100), f"VIEWER-{side.upper()} · source small vs candidate", font=label, fill=(48, 42, 59))
        for row, art in enumerate((source_rois[side], variants[side])):
            enlarged = art.resize((art.width * 4, art.height * 4), Image.Resampling.NEAREST)
            bg = Image.new("RGBA", enlarged.size, (235, 234, 239, 255))
            bg.alpha_composite(enlarged)
            board.paste(bg.convert("RGB"), (x, 140 + row * 390))
            draw.text((x, 140 + row * 390 + 372), "source small + exact cuff" if row == 0 else "trial-09 hand + exact source cuff", font=font(14), fill=(72, 66, 80))
    board_path = OUT / BOARD
    board.save(board_path)
    metrics["outputs"] = {
        "full_body_preview": {"path": PREVIEW, "sha256": sha(preview_path)},
        "comparison_board": {"path": BOARD, "sha256": sha(board_path)},
    }
    metrics["visual_review"] = {
        "status": "rejected_by_user_full_body_review_hands_too_small_and_unnatural",
        "user_feedback": "The user reported that the trial-09 source-cuff preview hands appear tiny at the original body positions and look awful; do not accept or reuse this fit.",
        "viewed_artifacts": [BOARD, PREVIEW],
        "observations": [
            "The 4x board shows the exact original source cuffs and their two pale stripes. The original source cuff layers are separately extracted and exact-RGBA verified (2,440 viewer-left pixels; 2,498 viewer-right pixels); this verifies cuff preservation only, not hand-art acceptance.",
            "Uniform source-box fits are 44x48px viewer-left and 39x46px viewer-right. The assistant's static close-up inspection found no obvious cuff gap, but the user's full-body review rejected the result because the hands read too small and unnatural at source positions; user feedback takes precedence.",
            "The AI outlines/anti-aliased edges are softer and lower-contrast than the Chibi source, especially viewer-left; slight pale edge pixels remain. Trial09 is a failed visual fit and must not be represented as promising or production-suitable.",
            "The hand layer has only the existing generated wrist pixels; no wrist-angle sweep was performed, so hidden-wrist sufficiency and movement coverage are not established.",
        ],
        "decision": "rejected_for_visual_use; keep_only_as_failed_WIP_evidence; do_not_promote_or_reuse",
        "next_step": "Reconsider the hand silhouette against the original full-body target size; do not treat minor scale or alignment adjustments to trial09 as a solution.",
    }
    (OUT / METRICS).write_text(json.dumps(metrics, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("generated isolated trial-09 source-cuff WIP; user rejected full-body hand scale/shape; not production art")


if __name__ == "__main__":
    main()
