#!/usr/bin/env python3
"""Trial24: isolate/fix-scale AI mitten studies over exact Chibi cuff source; WIP only.

This script does not draw a hand. It selects existing AI hand pixels, applies the
registered Chibi source palette, uniformly fits each side to measured source
hand anchors, places it under the source cuff, and writes QA-only artifacts.
"""
from __future__ import annotations
import hashlib, importlib.util, json, sys
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw, ImageFont

OUT = Path(__file__).resolve().parent
REPO = Path(__file__).resolve().parents[4]
BODY = REPO / "characters/xiaoxun/forms/chibi/sprites/body_full.png"
HELPER = OUT / "fit_mitten_source_cuff_trial.py"
RAW = {
    "left": OUT / "hand_viewer_left_trial_24_ai_art_wip.png",
    "right": OUT / "hand_viewer_right_trial_24_ai_art_wip.png",
}
TARGET_SIZE = (52, 58)

spec = importlib.util.spec_from_file_location("sourcefit_trial24", HELPER)
fit = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = fit
assert spec.loader
spec.loader.exec_module(fit)
BOXES = fit.BOXES

def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

def font(size: int):
    for f in ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf"):
        try: return ImageFont.truetype(f, size)
        except OSError: pass
    return ImageFont.load_default()

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
    parts_dir = OUT / "trial24_sourcefit_candidate_parts"
    parts_dir.mkdir(exist_ok=True)
    review, metrics = {}, {}
    for side in ("left", "right"):
        roi = BOXES[side]
        crop = source.crop(roi).convert("RGBA")
        cuff, source_skin, source_meta = fit.source_cuff_and_hand(crop)
        palette = fit.sample_source_skin_palette(np.asarray(crop), source_skin)
        hand, art_meta = fit.extract_ai_hand(RAW[side], palette)
        sx0, sy0, sx1, sy1 = source_meta["source_hand_bbox_xyxy_exclusive_with_1px_outline_margin"]
        tw, th = TARGET_SIZE
        target = [round((sx0 + sx1 - tw) / 2), sy1 - th, round((sx0 + sx1 - tw) / 2) + tw, sy1]
        variant, fit_meta = fit.make_variant(source, side, hand, cuff, target)
        v = np.asarray(variant.convert("RGBA")).copy()
        src = np.asarray(crop)
        v[cuff] = src[cuff]
        if not np.array_equal(v[cuff], src[cuff]):
            raise AssertionError(f"{side} source cuff RGBA changed")
        variant = Image.fromarray(v, "RGBA")
        erased = fit.erase_source_hand(crop, cuff, source_skin)
        preview.paste(erased, (roi[0], roi[1]))
        preview.alpha_composite(variant, (roi[0], roi[1]))
        review[side] = (crop, variant)
        fitted_hand, hand_meta = fit.fit_hand_to_source(hand, target)
        fitted_hand.save(parts_dir / f"hand_{side}_mitten_trial24_candidate_wip.png")
        fitted_hand.resize((fitted_hand.width * 2, fitted_hand.height * 2), Image.Resampling.LANCZOS).save(parts_dir / f"hand_{side}_mitten_trial24_candidate_2x_wip.png")
        variant.save(parts_dir / f"hand_{side}_mitten_source_cuff_trial24_candidate_wip.png")
        metrics[side] = {
            **source_meta, **palette, **art_meta, **fit_meta,
            "candidate_target_source_bbox_xyxy": target,
            "candidate_local_size": list(variant.size),
            "cuff_exact_rgba_identity_px": int(cuff.sum()),
            "source_rgba_cuff_equal": True,
            "uniform_fit_output": hand_meta,
        }
    preview_path = OUT / "body_full_trial24_mitten_sourcefit_preview_wip.png"
    board_path = OUT / "chibi_mitten_trial24_sourcefit_review_board_wip.png"
    preview.save(preview_path)

    board = Image.new("RGB", (1900, 1440), (248, 247, 245))
    d = ImageDraw.Draw(board)
    d.text((24, 18), "CHIBI MITTEN · TRIAL24 SOURCE-FIT · WIP / NOT PRODUCTION", font=font(25), fill=(48,42,59))
    d.text((24, 56), "Trial15 size direction only is user-approved; source cuff retained byte-exact; AI hands remain unapproved.", font=font(16), fill=(72,66,80))
    for i, (im, label) in enumerate(((source, "original Chibi body_full"), (preview, "source + trial24 static fit"))):
        show = im.copy(); show.thumbnail((320, 790), Image.Resampling.LANCZOS)
        board.paste(checker(show), (24 + i * 350, 105))
        d.text((24 + i * 350, 910), label, font=font(15), fill=(72,66,80))
    for i, side in enumerate(("left", "right")):
        x = 760 + i * 560
        src, var = review[side]
        d.text((x, 105), f"viewer-{side} · same source ROI", font=font(18), fill=(48,42,59))
        board.paste(checker(src, 4), (x, 145))
        d.text((x, 530), "original source hand + cuff · 4×", font=font(14), fill=(72,66,80))
        board.paste(checker(var, 4), (x, 560))
        d.text((x, 945), "trial24 hand + exact source cuff · 4×", font=font(14), fill=(72,66,80))
        seam = var.crop((0, 22, var.width, min(var.height, 67))).resize((var.width * 7, 45 * 7), Image.Resampling.NEAREST)
        board.paste(checker(seam), (x, 985))
        d.text((x, 1310), "cuff join · 7×", font=font(14), fill=(72,66,80))
    d.text((24, 1400), "Static fit only. Hidden-wrist coverage, wrist rotation, rig and C-engine gates are not tested.", font=font(15), fill=(110,50,52))
    board.save(board_path)

    payload = {
        "status": "isolated_ai_hand_candidate_pending_visual_review_not_production",
        "created_on": "2026-11-03",
        "approval_scope": "User approved only the trial15 full-body mitten size direction.",
        "sources": {
            "body_full": {"path": "characters/xiaoxun/forms/chibi/sprites/body_full.png", "sha256": sha(BODY)},
            "approved_size_direction": {"path": "chibi_mitten_original_fullbody_concept_trial_15_wip.png", "sha256": sha(OUT / "chibi_mitten_original_fullbody_concept_trial_15_wip.png")},
            "fit_method": "select existing AI pixels; source-sample palette; fit uniformly to registered source small-hand bbox; retain exact Chibi cuff mask; no hand geometry drawn",
            "target_size_px": list(TARGET_SIZE),
        },
        "ai_art_inputs": {side: {"file": p.name, "sha256": sha(p)} for side,p in RAW.items()},
        "fit_metrics": metrics,
        "visual_review": {"reviewed": [], "observations": [], "decision": "pending_agent_visual_review"},
        "limits": ["AI WIP, not source pixels or production art", "no hand geometry programmatically drawn", "no user screenshot pixels or Teen/generic art", "no production sprite/rig/generator changed", "no hidden-wrist animation or C-engine test"],
        "files": {},
    }
    for p in [preview_path, board_path]: payload["files"][p.name] = sha(p)
    for p in sorted(parts_dir.glob("*.png")): payload["files"][str(p.relative_to(OUT))] = sha(p)
    (OUT / "mitten_trial24_sourcefit_metrics.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("wrote isolated trial24 source-fit; production assets untouched")

if __name__ == "__main__": main()
