#!/usr/bin/env python3
"""Isolated source-fit preview for trial15-approved mitten size; never production.

The hand silhouettes are AI-generated art pixels only. This script crops away
unwanted AI forearm length, source-samples Chibi skin tones, fits both sides to
measured Chibi hand anchors, erases only the original visible hand component in
the preview, and restores the exact source cuff over each candidate. It draws
no hand geometry and changes no production asset or rig.
"""
from __future__ import annotations
import hashlib, importlib.util, json, sys
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw, ImageFont

OUT = Path(__file__).resolve().parent
REPO = Path(__file__).resolve().parents[4]
BODY = REPO / "characters/xiaoxun/forms/chibi/sprites/body_full.png"
FIT_SCRIPT = OUT / "fit_mitten_source_cuff_trial.py"
RAW = {
    # The existing independent AI studies are trimmed to remove excessive wrist length.
    "left": OUT / "hand_viewer_left_trial_16_ai_art_wip.png",
    "right": OUT / "hand_viewer_right_trial_19_ai_art_wip.png",
}
# Body-full exclusive ROIs from the registered source manifest.
ROI = {"left": (43, 846, 132, 938), "right": (435, 846, 524, 938)}
TARGET_SIZE = (52, 58)  # user-approved trial15 scale mapped to the 567x1292 source figure

spec = importlib.util.spec_from_file_location("sourcefit", FIT_SCRIPT)
fit = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = fit
assert spec.loader
spec.loader.exec_module(fit)


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def font(size: int):
    for f in ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf"):
        try: return ImageFont.truetype(f, size)
        except OSError: pass
    return ImageFont.load_default()


def crop_ai_to_compact_art(path: Path, out: Path) -> tuple[Image.Image, dict]:
    im = Image.open(path).convert("RGB")
    rgb = np.asarray(im).astype(np.int16)
    r, g, b = rgb.transpose(2, 0, 1)
    skin = (r > 175) & (g > 100) & (g < 240) & (b > 70) & (r > g * 1.03) & (g > b * 1.02)
    ys, xs = np.where(skin)
    if len(xs) < 1000:
        raise RuntimeError(f"No substantial AI hand skin detected: {path.name}")
    x0, x1 = int(xs.min()), int(xs.max()) + 1
    y0, y1 = int(ys.min()), int(ys.max()) + 1
    # Keep the lower palm/thumb silhouette and only a compact cuff-hidden root.
    # This is a crop of existing AI art pixels, not synthesized hand geometry.
    crop_h = round((x1 - x0) / 0.90)
    cy0 = max(y0, y1 - crop_h)
    box = (max(0, x0 - 24), cy0, min(im.width, x1 + 24), y1 + 8)
    art = im.crop(box)
    art.save(out)
    return art, {
        "input": path.name, "input_sha256": sha(path), "input_size": list(im.size),
        "skin_component_bbox_xyxy": [x0, y0, x1, y1],
        "crop_xyxy": list(box), "crop_size": list(art.size),
        "crop_operation": "bottom-aligned crop of existing AI pixels; no drawing; approximate width/height ratio 0.90",
    }


def checker(im: Image.Image, scale=1) -> Image.Image:
    rgba = im.convert("RGBA")
    if scale != 1:
        rgba = rgba.resize((rgba.width * scale, rgba.height * scale), Image.Resampling.NEAREST)
    bg = Image.new("RGBA", rgba.size, (236, 235, 240, 255))
    bg.alpha_composite(rgba)
    return bg.convert("RGB")


def main():
    source = Image.open(BODY).convert("RGBA")
    preview = source.copy()
    crops, art_info, parts, metrics = {}, {}, {}, {}
    for side in ("left", "right"):
        ai_crop_path = OUT / f"mitten_{side}_trial16_compact_ai_crop_wip.png"
        cropped, art_meta = crop_ai_to_compact_art(RAW[side], ai_crop_path)
        x0, y0, x1, y1 = ROI[side]
        src_crop = source.crop(ROI[side]).convert("RGBA")
        cuff, source_skin, source_meta = fit.source_cuff_and_hand(src_crop)
        source_palette = fit.sample_source_skin_palette(np.asarray(src_crop), source_skin)
        hand, ai_meta = fit.extract_ai_hand(ai_crop_path, source_palette)
        lx0, ly0, lx1, ly1 = source_meta["source_hand_bbox_xyxy_exclusive_with_1px_outline_margin"]
        tw, th = TARGET_SIZE
        target = [round((lx0 + lx1 - tw) / 2), ly1 - th,
                  round((lx0 + lx1 - tw) / 2) + tw, ly1]
        variant, place_meta = fit.make_variant(source, side, hand, cuff, target)
        # Restore selected source cuff RGBA values byte-for-byte (including AA edge pixels).
        variant_rgba = np.asarray(variant.convert("RGBA")).copy()
        src_rgba = np.asarray(src_crop)
        variant_rgba[cuff] = src_rgba[cuff]
        variant = Image.fromarray(variant_rgba, "RGBA")
        if not np.array_equal(variant_rgba[cuff], src_rgba[cuff]):
            raise AssertionError(f"{side} exact source cuff pixels changed")
        erased = fit.erase_source_hand(src_crop, cuff, source_skin)
        preview.paste(erased, (x0, y0))
        preview.alpha_composite(variant, (x0, y0))
        crops[side] = (src_crop, variant)
        parts[side] = variant
        art_info[side] = {**art_meta, **ai_meta, **place_meta}
        metrics[side] = {
            **source_meta, **source_palette, **place_meta,
            "candidate_local_size": list(variant.size),
            "cuff_exact_rgba_identity_px": int(cuff.sum()),
            "candidate_target_source_bbox_xyxy": target,
            "candidate_hand_art": ai_meta,
            "source_rgba_cuff_equal": True,
        }
        # The transparent 1x/2x art candidate is for source-anchor inspection only.
        variants_dir = OUT / "trial16_sourcefit_candidate_parts"
        variants_dir.mkdir(exist_ok=True)
        hand_rgba = fit.fit_hand_to_source(hand, target)[0]
        name = f"hand_{side}_mitten_trial16_candidate_wip.png"
        hand_rgba.save(variants_dir / name)
        hand_rgba.resize((hand_rgba.width * 2, hand_rgba.height * 2), Image.Resampling.LANCZOS).save(
            variants_dir / name.replace("_wip.png", "_2x_wip.png"))
        variant.save(variants_dir / f"hand_{side}_mitten_source_cuff_trial16_candidate_wip.png")

    preview.save(OUT / "body_full_trial16_mitten_sourcefit_preview_wip.png")
    # Matched board: full-body before/after, two independent hand/cuff crops, and cuff-edge zooms.
    board = Image.new("RGB", (1680, 1500), (248, 247, 245))
    d = ImageDraw.Draw(board)
    d.text((24, 18), "CHIBI MITTEN · TRIAL16 SOURCE-FIT CANDIDATE · WIP / NOT PRODUCTION", font=font(25), fill=(48, 42, 59))
    d.text((24, 58), "Trial15 size approved by user; two generated hand studies fitted to source small-hand anchors; exact cuff retained.", font=font(16), fill=(72, 66, 80))
    for i, (im, label) in enumerate(((source, "original source body_full"), (preview, "source body + trial16 candidate"))):
        show = im.copy(); show.thumbnail((330, 780), Image.Resampling.LANCZOS)
        board.paste(checker(show), (24 + i * 360, 105))
        d.text((24 + i * 360, 900), label, font=font(15), fill=(72, 66, 80))
    for i, side in enumerate(("left", "right")):
        x = 760 + i * 445
        d.text((x, 106), f"viewer-{side} · same source ROI", font=font(18), fill=(48, 42, 59))
        src_crop, var = crops[side]
        board.paste(checker(src_crop, 4), (x, 145))
        board.paste(checker(var, 4), (x, 560))
        d.text((x, 535), "source small hand/cuff · 4×", font=font(14), fill=(72, 66, 80))
        d.text((x, 950), "AI mitten + exact source cuff · 4×", font=font(14), fill=(72, 66, 80))
        seam = var.crop((0, 24, var.width, min(var.height, 68))).resize((var.width * 8, 44 * 8), Image.Resampling.NEAREST)
        board.paste(checker(seam), (x, 990))
        d.text((x, 1348), "cuff join · 8×", font=font(14), fill=(72, 66, 80))
    d.text((24, 1450), "AI hand pixels remain unapproved; static source fit only. Hidden-wrist animation/rig/C-engine gates are not yet passed.", font=font(15), fill=(110, 50, 52))
    board.save(OUT / "chibi_mitten_trial16_sourcefit_review_board_wip.png")

    payload = {
        "status": "isolated_ai_hand_style_candidate_wip_not_production",
        "created_on": "2026-11-03",
        "approval_scope": "User approved trial15 hand size only. This does not approve the AI art, source layers, hidden-wrist completion, rig, or engine integration.",
        "sources": {
            "body_full": {"path": "characters/xiaoxun/forms/chibi/sprites/body_full.png", "sha256": sha(BODY)},
            "approved_size_direction": {"path": "chibi_mitten_original_fullbody_concept_trial_15_wip.png", "sha256": sha(OUT / "chibi_mitten_original_fullbody_concept_trial_15_wip.png")},
            "references": ["docs/REFERENCE_NOTES.md §71 (official Live2D Production Flow / PSD / Pose guidance)", "docs/SHEET_PIPELINE.md", "docs/ART_PARTS.md", "docs/memory/WORKFLOW.md iron laws 0-15"],
            "roi_body_full_xyxy": {k: list(v) for k, v in ROI.items()},
            "parts_target_size_px": list(TARGET_SIZE),
        },
        "art_inputs": {side: art_info[side] for side in art_info},
        "fit_metrics": metrics,
        "visual_review": {
            "reviewed": ["hand_viewer_left_trial_16_ai_art_wip.png", "hand_viewer_right_trial_19_ai_art_wip.png", "chibi_mitten_trial16_sourcefit_review_board_wip.png"],
            "observations": ["Initial isolated AI outputs are inconsistent in wrist length and palm proportions; compact cropping is therefore study-only and does not fix style differences.", "The fitted candidate board must be visually inspected before any further hand-part or engine work.", "Exact source cuff pixels are preserved in this static candidate; old source hands are concealed only in the preview by the new overlay."],
            "decision": "candidate_only_pending_visual_review; no production acceptance",
        },
        "limits": ["AI-generated art; not source pixels", "no user screenshot pixels or Teen/generic hand assets used", "no hand geometry programmatically drawn", "no production sprites/rig/generator changed", "no wrist-angle/gesture/outfit C-engine matrix tested"],
        "files": {},
    }
    for name in ["body_full_trial16_mitten_sourcefit_preview_wip.png", "chibi_mitten_trial16_sourcefit_review_board_wip.png", "mitten_left_trial16_compact_ai_crop_wip.png", "mitten_right_trial16_compact_ai_crop_wip.png"]:
        payload["files"][name] = sha(OUT / name)
    for f in sorted((OUT / "trial16_sourcefit_candidate_parts").glob("*.png")):
        payload["files"][str(f.relative_to(OUT))] = sha(f)
    (OUT / "mitten_trial16_sourcefit_metrics.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("wrote isolated trial16 source-fit WIP; production assets untouched")

if __name__ == "__main__": main()
