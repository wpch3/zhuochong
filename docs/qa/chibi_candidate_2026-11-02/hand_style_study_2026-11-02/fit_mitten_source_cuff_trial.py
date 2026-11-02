#!/usr/bin/env python3
"""Source-measured AI mitten fit study; isolated WIP only, never production art.

The hand silhouettes remain from independent AI trials 04/05. This script does
not draw or synthesize hands: it derives the Chibi cuff cover from the source
body pixels, measures each source small-hand bounding box, fits the AI artwork
without distortion, and restores the exact source cuff over it. Outputs stay in
this QA study directory.
"""
from __future__ import annotations

from collections import deque
import hashlib
import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

ROOT = Path(__file__).resolve().parents[4]
OUT = Path(__file__).resolve().parent
BODY_PATH = ROOT / "characters/xiaoxun/forms/chibi/sprites/body_full.png"
SHEET_PATH = ROOT / "characters/xiaoxun/design/design_sheet_chibi.png"
TRIALS = {
    "left": OUT / "mitten_left_art_trial_04.png",
    "right": OUT / "mitten_right_art_trial_05.png",
}
# Source-registered ROIs are loaded from the saved manifest, not hand-edited.
SOURCE_MANIFEST_PATH = OUT / "source_crop_manifest.json"
SOURCE_MANIFEST = json.loads(SOURCE_MANIFEST_PATH.read_text(encoding="utf-8"))
BOXES = {
    side: tuple(SOURCE_MANIFEST["source_crops"][side]["body_full_roi_xyxy_exclusive"])
    for side in ("left", "right")
}
PALETTE = {
    "skin": (252, 228, 216),
    "skin_shadow": (232, 184, 168),
    "outline": (90, 90, 110),
    "highlight": (255, 250, 246),
}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def component(mask: np.ndarray, score: np.ndarray | None = None) -> np.ndarray:
    """Return the connected component with the greatest seed score/area."""
    h, w = mask.shape
    seen = np.zeros((h, w), dtype=bool)
    best_points: list[tuple[int, int]] = []
    best_score = -1
    ys, xs = np.where(mask)
    for sy, sx in zip(ys.tolist(), xs.tolist()):
        if seen[sy, sx]:
            continue
        queue = deque([(sy, sx)])
        seen[sy, sx] = True
        points: list[tuple[int, int]] = []
        seed_count = 0
        while queue:
            y, x = queue.popleft()
            points.append((y, x))
            seed_count += int(score[y, x]) if score is not None else 1
            for dy in (-1, 0, 1):
                for dx in (-1, 0, 1):
                    ny, nx = y + dy, x + dx
                    if 0 <= ny < h and 0 <= nx < w and mask[ny, nx] and not seen[ny, nx]:
                        seen[ny, nx] = True
                        queue.append((ny, nx))
        rank = seed_count if score is not None else len(points)
        if rank > best_score:
            best_score = rank
            best_points = points
    out = np.zeros((h, w), dtype=bool)
    for y, x in best_points:
        out[y, x] = True
    return out


def fill_holes(mask: np.ndarray) -> np.ndarray:
    """Fill enclosed gaps without scipy, using a padded exterior flood fill."""
    p = np.pad(mask, 1, constant_values=False)
    h, w = p.shape
    exterior = np.zeros((h, w), dtype=bool)
    queue: deque[tuple[int, int]] = deque()
    for x in range(w):
        if not p[0, x]:
            exterior[0, x] = True
            queue.append((0, x))
        if not p[h - 1, x]:
            exterior[h - 1, x] = True
            queue.append((h - 1, x))
    for y in range(h):
        if not p[y, 0]:
            exterior[y, 0] = True
            queue.append((y, 0))
        if not p[y, w - 1]:
            exterior[y, w - 1] = True
            queue.append((y, w - 1))
    while queue:
        y, x = queue.popleft()
        for dy, dx in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            ny, nx = y + dy, x + dx
            if 0 <= ny < h and 0 <= nx < w and not p[ny, nx] and not exterior[ny, nx]:
                exterior[ny, nx] = True
                queue.append((ny, nx))
    return ~exterior[1:-1, 1:-1]


def dilate(mask: np.ndarray, iterations: int = 1) -> np.ndarray:
    image = Image.fromarray((mask.astype(np.uint8) * 255), "L")
    for _ in range(iterations):
        image = image.filter(ImageFilter.MaxFilter(3))
    return np.asarray(image) > 0


def dilate_one(mask: np.ndarray) -> np.ndarray:
    return dilate(mask, 1)


def warm_skin_mask(rgba: np.ndarray) -> np.ndarray:
    a = rgba.astype(np.int16)
    r, g, b, alpha = (a[..., i] for i in range(4))
    # Separates the Chibi warm skin from its nearly neutral cream cuff stripes.
    return (alpha > 32) & (r > 205) & ((r - g) > 12) & ((g - b) > 2)


def source_cuff_and_hand(crop: Image.Image) -> tuple[np.ndarray, np.ndarray, dict]:
    rgba = np.asarray(crop.convert("RGBA"))
    p = rgba.astype(np.int16)
    r, g, b, alpha = (p[..., i] for i in range(4))
    # Chibi source sleeve/cuff: teal seed plus neutral cream stripes, all selected
    # by the dominant connected material component in the registered hand ROI.
    teal = (alpha > 32) & (g > r + 14) & (b > r + 8) & (g > 85) & (g < 245)
    cream_stripe = (
        (alpha > 32) & (p[..., :3].min(axis=2) > 205) & ((r - g) < 8) & ((g - b) < 12)
    )
    material_core = teal | cream_stripe
    cuff_core = component(material_core, teal)
    if not cuff_core.any():
        raise RuntimeError("No source Chibi teal cuff component found")
    cuff_filled = fill_holes(cuff_core)
    # Preserve source alpha; one source-pixel expansion includes its contour and
    # AA edge, while confident warm skin remains excluded from the cuff.
    cuff_cover = dilate_one(cuff_filled) & (alpha > 32)
    confident_skin = (alpha > 32) & (r > 210) & ((r - g) > 18) & ((g - b) > 3)
    cuff_cover &= ~confident_skin

    skin = warm_skin_mask(rgba) & ~cuff_cover
    skin_component = component(skin)
    if not skin_component.any():
        raise RuntimeError("No source Chibi hand skin found below cuff")
    ys, xs = np.where(skin_component)
    # Include the original outline/AA margin around the measured skin region.
    x0, y0 = max(0, int(xs.min()) - 1), max(0, int(ys.min()) - 1)
    x1, y1 = min(crop.width, int(xs.max()) + 2), min(crop.height, int(ys.max()) + 2)
    metrics = {
        "cuff_core_px": int(cuff_core.sum()),
        "cuff_filled_px": int(cuff_filled.sum()),
        "cuff_cover_px": int(cuff_cover.sum()),
        "source_hand_skin_component_px": int(skin_component.sum()),
        "source_hand_bbox_xyxy_exclusive_with_1px_outline_margin": [x0, y0, x1, y1],
        "source_hand_bbox_size": [x1 - x0, y1 - y0],
    }
    return cuff_cover, skin_component, metrics


def sample_source_skin_palette(rgba: np.ndarray, skin_component: np.ndarray) -> dict:
    """Sample candidate tones from the real Chibi small-hand pixels, not guesses."""
    rgb = rgba[..., :3].astype(np.float32)
    samples = rgb[skin_component]
    if len(samples) < 16:
        raise RuntimeError("Too few Chibi source skin pixels to sample a fit palette")
    lum = samples @ np.asarray([0.2126, 0.7152, 0.0722], dtype=np.float32)
    q10, q50, q90 = np.percentile(lum, [10, 50, 90])
    low = np.median(samples[lum <= q10], axis=0)
    mid = np.median(samples[(lum >= np.percentile(lum, 40)) & (lum <= np.percentile(lum, 60))], axis=0)
    high = np.median(samples[lum >= q90], axis=0)
    return {
        "skin_shadow": tuple(np.clip(np.rint(low), 0, 255).astype(np.uint8).tolist()),
        "skin": tuple(np.clip(np.rint(mid), 0, 255).astype(np.uint8).tolist()),
        "highlight": tuple(np.clip(np.rint(high), 0, 255).astype(np.uint8).tolist()),
        "source_skin_luminance_p10_p50_p90": [float(q10), float(q50), float(q90)],
        "source_skin_sample_count": int(len(samples)),
    }


def extract_ai_hand(path: Path, source_palette: dict | None = None) -> tuple[Image.Image, dict]:
    src = Image.open(path).convert("RGB")
    palette = source_palette or PALETTE
    rgb = np.asarray(src).astype(np.int16)
    r, g, b = rgb.transpose(2, 0, 1)
    raw_skin = (r > 175) & (g > 100) & (g < 240) & (b > 70) & (r > g * 1.03) & (g > b * 1.02)
    ai_skin = component(raw_skin)
    near = Image.fromarray((ai_skin.astype(np.uint8) * 255), "L").filter(ImageFilter.MaxFilter(45))
    near_mask = np.asarray(near) > 0
    line = (r < 170) & (g < 130) & (b < 180) & (r >= g) & ((b - g) > 10) & near_mask
    silhouette = Image.fromarray(((ai_skin | line).astype(np.uint8) * 255), "L")
    silhouette = silhouette.filter(ImageFilter.MaxFilter(3)).filter(ImageFilter.MinFilter(3))
    silhouette_mask = component(np.asarray(silhouette) > 0)
    silhouette_mask = fill_holes(silhouette_mask)
    ys, xs = np.where(silhouette_mask)
    if not len(xs):
        raise RuntimeError(f"No AI mitten silhouette found in {path.name}")
    x0, y0, x1, y1 = int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1
    mask = silhouette_mask[y0:y1, x0:x1]
    core = ai_skin[y0:y1, x0:x1]
    crop_rgb = rgb[y0:y1, x0:x1]
    lum = 0.2126 * crop_rgb[..., 0] + 0.7152 * crop_rgb[..., 1] + 0.0722 * crop_rgb[..., 2]
    lo, hi = np.percentile(lum[core], [5, 95])
    t = np.clip((lum - lo) / max(hi - lo, 1), 0, 1)
    shadow = np.asarray(palette["skin_shadow"], dtype=np.float32)
    base = np.asarray(palette["skin"], dtype=np.float32)
    highlight = np.asarray(palette["highlight"], dtype=np.float32)
    colors = shadow[None, None, :] * (1 - t[..., None]) + base[None, None, :] * t[..., None]
    hm = np.clip((t - 0.78) / 0.22, 0, 1)[..., None]
    colors = colors * (1 - hm) + highlight[None, None, :] * hm
    rgba = np.zeros((y1 - y0, x1 - x0, 4), dtype=np.uint8)
    rgba[..., :3] = np.clip(colors, 0, 255).astype(np.uint8)
    rgba[line[y0:y1, x0:x1], :3] = PALETTE["outline"]
    alpha = Image.fromarray((mask * 255).astype(np.uint8), "L").filter(ImageFilter.GaussianBlur(0.35))
    rgba[..., 3] = np.asarray(alpha)
    hand = Image.fromarray(rgba, "RGBA")
    return hand, {
        "ai_source_file": path.name,
        "ai_source_sha256": sha(path),
        "ai_source_silhouette_bbox_xyxy": [x0, y0, x1, y1],
        "ai_source_silhouette_size": [hand.width, hand.height],
        "method": "AI-trial warm skin component + adjacent plum outline; color mapped to source-sampled Chibi hand tones",
        "source_sampled_palette": {
            key: list(value) if isinstance(value, tuple) else value
            for key, value in palette.items()
            if key in {"skin_shadow", "skin", "highlight", "source_skin_luminance_p10_p50_p90", "source_skin_sample_count"}
        },
    }


def erase_source_hand(crop: Image.Image, cuff_cover: np.ndarray, skin_component: np.ndarray) -> Image.Image:
    rgba = np.asarray(crop.convert("RGBA")).copy()
    erase = dilate_one(skin_component) & ~cuff_cover
    rgba[erase, 3] = 0
    rgba[erase, :3] = 0
    return Image.fromarray(rgba, "RGBA")


def fit_hand_to_source(hand: Image.Image, target_bbox: list[int]) -> tuple[Image.Image, dict]:
    x0, y0, x1, y1 = target_bbox
    target_w, target_h = x1 - x0, y1 - y0
    scale = min(target_w / hand.width, target_h / hand.height)
    out_w = max(1, round(hand.width * scale))
    out_h = max(1, round(hand.height * scale))
    resized = hand.resize((out_w, out_h), Image.Resampling.LANCZOS)
    # Align to the measured Chibi hand's center and fingertip/bottom row.
    x = round((x0 + x1) / 2 - out_w / 2)
    y = y1 - out_h
    return resized, {
        "target_bbox_xyxy_exclusive": target_bbox,
        "target_bbox_size": [target_w, target_h],
        "scale_uniform": scale,
        "fitted_size": [out_w, out_h],
        "placement_xy": [x, y],
        "bottom_aligned_to_source_hand_bbox": True,
    }


def make_variant(body: Image.Image, side: str, hand: Image.Image, cuff_cover: np.ndarray, target_bbox: list[int]) -> tuple[Image.Image, dict]:
    crop = body.crop(BOXES[side]).convert("RGBA")
    resized, fit_metrics = fit_hand_to_source(hand, target_bbox)
    local = Image.new("RGBA", crop.size, (0, 0, 0, 0))
    fitted_x, fitted_y = fit_metrics["placement_xy"]
    local.alpha_composite(resized, (fitted_x, fitted_y))

    # Keep the hand under the cuff as a real overlap. In the narrow source-derived
    # edge band, remove only the AI wrist's duplicate outline; the source cuff's
    # own outline remains the visible joint boundary. This is a cut/occlusion
    # operation, not hand drawing or a guessed cuff polyline.
    ai = np.asarray(local).copy()
    r, g, b, alpha = (ai[..., i].astype(np.int16) for i in range(4))
    edge_band = dilate(cuff_cover, 2) & ~cuff_cover
    ai_outline = (alpha > 0) & (r < 170) & (g < 170) & (b < 190) & (r >= g - 2) & ((b - g) > 8)
    remove_line = edge_band & ai_outline
    ai[remove_line, 3] = 0
    ai[remove_line, :3] = 0
    local = Image.fromarray(ai.astype(np.uint8), "RGBA")

    cuff_rgba = np.asarray(crop).copy()
    cuff_rgba[~cuff_cover, 3] = 0
    source_cuff_layer = Image.fromarray(cuff_rgba, "RGBA")
    local.alpha_composite(source_cuff_layer)
    return local, {
        **fit_metrics,
        "cuff_edge_band_radius_px": 2,
        "ai_wrist_outline_pixels_removed_in_edge_band": int(remove_line.sum()),
        "ai_hand_underlaps_source_cuff": True,
    }


def checkerboard(image: Image.Image, scale: int = 1) -> Image.Image:
    rgba = image.convert("RGBA")
    if scale != 1:
        rgba = rgba.resize((rgba.width * scale, rgba.height * scale), Image.Resampling.NEAREST)
    bg = Image.new("RGBA", rgba.size, (235, 234, 239, 255))
    bg.alpha_composite(rgba)
    return bg.convert("RGB")


def main() -> None:
    body = Image.open(BODY_PATH).convert("RGBA")
    full_preview = body.copy()
    variants: dict[str, Image.Image] = {}
    metrics: dict[str, dict] = {}
    source_crops: dict[str, Image.Image] = {}
    cuff_masks: dict[str, np.ndarray] = {}
    for side, box in BOXES.items():
        crop = body.crop(box).convert("RGBA")
        cuff_cover, skin_component, source_metrics = source_cuff_and_hand(crop)
        x0, y0, x1, y1 = source_metrics["source_hand_bbox_xyxy_exclusive_with_1px_outline_margin"]
        target_bbox = [x0, y0, x1, y1]
        source_palette = sample_source_skin_palette(np.asarray(crop), skin_component)
        ai_hand, ai_metrics = extract_ai_hand(TRIALS[side], source_palette)
        variant, fit_metrics = make_variant(body, side, ai_hand, cuff_cover, target_bbox)
        variants[side] = variant
        metrics[side] = {**ai_metrics, **source_metrics, **fit_metrics}
        source_crops[side] = crop
        cuff_masks[side] = cuff_cover
        erased = erase_source_hand(crop, cuff_cover, skin_component)
        full_preview.paste(erased, (box[0], box[1]))
        full_preview.alpha_composite(variant, (box[0], box[1]))
        variant.save(OUT / f"mitten_{side}_ai_source_cuff_wip.png")

    full_preview.save(OUT / "body_full_ai_source_cuff_preview_wip.png")

    board = Image.new("RGB", (1500, 1040), (248, 247, 245))
    d = ImageDraw.Draw(board)
    try:
        title = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 24)
        small = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 15)
    except OSError:
        title = small = ImageFont.load_default()
    d.text((28, 22), "XIAOXUN CHIBI · SOURCE-MEASURED MITTEN FIT · WIP / NOT PRODUCTION", font=title, fill=(50, 44, 62))
    d.text((28, 59), "Independent AI trials 04/05; source-derived cuff mask and hand-size fit; visual/art approval still required.", font=small, fill=(74, 68, 83))
    for i, (fig, label) in enumerate(((body.copy(), "source body_full"), (full_preview.copy(), "source-cuff AI fit preview"))):
        fig.thumbnail((155, 390), Image.Resampling.LANCZOS)
        x = 35 + i * 180
        board.paste(checkerboard(fig), (x, 125))
        d.text((x, 520), label, font=small, fill=(74, 68, 83))
    for i, side in enumerate(("left", "right")):
        x = 430 + i * 510
        d.text((x, 112), f"{side} · source small vs measured fit", font=title, fill=(50, 44, 62))
        for row, art in enumerate((source_crops[side], variants[side])):
            enlarged = checkerboard(art, 4)
            board.paste(enlarged, (x, 150 + row * 390))
            d.text((x, 150 + row * 390 + 372), "small source · 4×" if row == 0 else "source-cuff AI WIP · 4×", font=small, fill=(74, 68, 83))
    d.text((430, 940), "Exact cuff pixels retained; AI hand silhouettes remain unapproved and are not production textures.", font=small, fill=(116, 52, 56))
    board.save(OUT / "hand_style_ai_source_cuff_candidate_board_wip.png")

    mask_board = Image.new("RGB", (1200, 680), (248, 247, 245))
    md = ImageDraw.Draw(mask_board)
    md.text((20, 15), "SOURCE CUFF REGION MASK · derived from Chibi teal/cream connected component · WIP", font=title, fill=(40, 36, 48))
    for i, side in enumerate(("left", "right")):
        crop = source_crops[side]
        rgba = np.asarray(crop).copy()
        rgba[cuff_masks[side] == 0, 3] = 0
        overlay = Image.fromarray(rgba, "RGBA").resize((crop.width * 6, crop.height * 6), Image.Resampling.NEAREST)
        bg = Image.new("RGBA", overlay.size, (235, 234, 239, 255))
        bg.alpha_composite(crop.resize(overlay.size, Image.Resampling.NEAREST))
        tint = Image.new("RGBA", overlay.size, (255, 32, 28, 0))
        tint.putalpha(Image.fromarray((cuff_masks[side].astype(np.uint8) * 125), "L").resize(overlay.size, Image.Resampling.NEAREST))
        bg.alpha_composite(tint)
        bg.alpha_composite(overlay)
        xx = 25 + i * 590
        mask_board.paste(bg.convert("RGB"), (xx, 65))
        md.text((xx, 625), f"{side}: source pixels covered by the material mask", font=small, fill=(74, 68, 83))
    mask_board.save(OUT / "source_cuff_mask_diagnostic_wip.png")

    seam_board = Image.new("RGB", (1500, 860), (248, 247, 245))
    sd = ImageDraw.Draw(seam_board)
    sd.text((20, 15), "FINAL SOURCE-MEASURED CUFF SEAM · 8× detail · isolated WIP / not production", font=title, fill=(40, 36, 48))
    for i, side in enumerate(("left", "right")):
        x = 20 + i * 740
        sd.text((x, 52), side, font=title, fill=(50, 44, 62))
        source_crop = source_crops[side]
        for row, art in enumerate((source_crop, variants[side])):
            detail = art.crop((0, 24, art.width, 66)).resize((art.width * 8, 42 * 8), Image.Resampling.NEAREST)
            bg = Image.new("RGBA", detail.size, (235, 234, 239, 255))
            bg.alpha_composite(detail)
            y = 85 + row * 385
            seam_board.paste(bg.convert("RGB"), (x, y))
            label = "original Chibi cuff + small hand · 8×" if row == 0 else "source cuff + AI fit · 8×"
            sd.text((x, y + 340), label, font=small, fill=(74, 68, 83))
    seam_board.save(OUT / "mitten_cuff_seam_detail_wip.png")

    payload = {
        "status": "isolated_ai_art_candidate_wip_not_production",
        "sources": {
            "design_sheet_chibi": {"path": "characters/xiaoxun/design/design_sheet_chibi.png", "sha256": sha(SHEET_PATH)},
            "body_full": {"path": "characters/xiaoxun/forms/chibi/sprites/body_full.png", "sha256": sha(BODY_PATH)},
            "source_crop_manifest": {"path": SOURCE_MANIFEST_PATH.name, "sha256": sha(SOURCE_MANIFEST_PATH)},
            "body_full_roi_coordinates": BOXES,
            "source_cuff_method": "dominant connected component of Chibi teal pixels plus strict neutral cream stripe pixels; enclosed color gaps filled; one source pixel of contour included; source alpha retained; warm hand pixels excluded",
            "source_hand_fit_method": "each AI silhouette fitted uniformly within its own measured source small-hand bounding box; centered and bottom-aligned; no hand-drawn geometry",
            "source_sampled_skin_tone_method": "low/mid/high luminance colors sampled from the measured Chibi source small-hand skin component; only the outline color uses the existing Chibi palette entry",
            "wrist_join_method": "AI hand underlaps source cuff; retain exact source cuff/edge; remove only duplicate AI outline pixels in the 2px cuff-adjacent band",
        },
        "ai_trials": {},
        "fitting": metrics,
        "visual_review": {
            "viewed_artifacts": ["hand_style_ai_source_cuff_candidate_board_wip.png", "mitten_cuff_seam_detail_wip.png", "source_cuff_mask_diagnostic_wip.png"],
            "observations": [
                "Source cuff stripes and outer contour remain continuous; the 8x static detail shows no obvious transparent gap after source-mask fitting.",
                "Removing the duplicate AI wrist outline reduces the double-line seam, but a slight warm shadow-band and style-density mismatch remain visible.",
                "Left/right silhouettes are independently fitted, but visual identity/style approval and animated behavior are not established.",
            ],
            "decision": "improved_isolated_static_candidate_only_not_approved_for_production",
        },
        "limits": [
            "AI trials 04 and 05 changed cuff geometry in their source outputs; their cuffs were not used",
            "AI hand silhouettes remain unapproved for Chibi style/identity and are not production textures",
            "the user-marked screenshot was a shape cue only, never copied, cropped, or used as texture",
            "no Teen hand asset used",
            "no production sprite, rig, generator, or engine changed",
            "static seam appearance was visually reviewed but is not approved as final hand art; wrist rotation, hand proportions under motion, and C-engine fit remain unverified",
        ],
        "files": {},
    }
    for side, path in TRIALS.items():
        payload["ai_trials"][side] = {"file": path.name, "sha256": sha(path)}
    names = [
        "mitten_left_ai_source_cuff_wip.png",
        "mitten_right_ai_source_cuff_wip.png",
        "body_full_ai_source_cuff_preview_wip.png",
        "hand_style_ai_source_cuff_candidate_board_wip.png",
        "source_cuff_mask_diagnostic_wip.png",
        "mitten_cuff_seam_detail_wip.png",
    ]
    for name in names:
        payload["files"][name] = sha(OUT / name)
    (OUT / "mitten_source_cuff_fit_metrics.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("wrote source-measured cuff/hand fit WIP; not production art")


if __name__ == "__main__":
    main()
