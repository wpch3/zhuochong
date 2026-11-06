#!/usr/bin/env python3
"""T67.71 local author-redraw proposal using the approved design-redraw direction.

AI-assisted crop outputs are used only as new design material (never as hidden
source truth). They are registered back to the 2x sprite crop, clipped to the
existing target alpha, and placed underneath a clean front layer. This is an
isolated review candidate: no rig, C runtime, or production asset is modified.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFont, ImageFilter

ROOT = Path(__file__).resolve().parents[4]
BASE = Path(__file__).resolve().parent
SOURCE = ROOT / "characters/xiaoxun/forms/teen/sprites/hair_hood_long@2x.png"
POLYGONS = BASE / "manual_artifact_silhouette_polygons_v3.json"
CROP_INPUTS = {
    "left": (0, 780, 440, 1420),
    "right": (692, 780, 1132, 1420),
}
PROPOSALS = {
    "left": BASE / "122_left_backhair_local_redraw_proposal.png",
    "right": BASE / "123_right_backhair_local_redraw_proposal.png",
}
PLATE = BASE / "126_backhair_ai_local_redraw_v2_plate_wip.png"
CLEAN = BASE / "127_clean_front_ai_local_redraw_v2_wip.png"
COMPOSITE = BASE / "129_ai_local_backhair_composite_v2_wip.png"
BOARD = BASE / "128_ai_local_backhair_review_v2.png"
METRICS = BASE / "130_ai_local_backhair_redraw_v2_metrics.json"
CLEAN_DILATE = 2


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def make_object_mask(size, objects):
    mask = Image.new("L", size, 0)
    draw = ImageDraw.Draw(mask)
    for kind in ("cuff", "hand"):
        draw.polygon([tuple(map(int, p)) for p in objects[kind]], fill=255)
    if CLEAN_DILATE:
        mask = mask.filter(ImageFilter.MaxFilter(CLEAN_DILATE * 2 + 1))
    return mask


def make_review(source, plate, clean, hair_only, old_object_mock):
    W, H = 2960, 1670
    board = Image.new("RGB", (W, H), (26, 29, 36))
    d = ImageDraw.Draw(board)
    try:
        title = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 30)
        label = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 18)
    except OSError:
        title = label = ImageFont.load_default()
    d.text((40, 22), "T67.71 · LOCAL BACK-HAIR REDRAW V2 · DESIGN PROPOSAL", font=title, fill=(244, 246, 250))
    d.text((42, 62), "New hair only; foreground arm/cuff must remain a separate moving layer. No hidden-original claim; no C test yet.", font=label, fill=(192, 200, 212))
    columns = [
        (source, "SOURCE ROI"),
        (plate, "BACK-HAIR PLATE (ALPHA)"),
        (hair_only, "CLEAN HAIR-ONLY COMPOSITE"),
        (old_object_mock, "STATIC MOCK: OLD ARM PIXELS ON TOP"),
    ]
    margin, gap, top, panel_h = 34, 14, 105, 720
    cw = (W - 2 * margin - 3 * gap) // 4
    for row, side in enumerate(("left", "right")):
        y0 = top + row * (panel_h + 36)
        d.text((margin, y0), side.upper(), font=title, fill=(118, 202, 233))
        py0 = y0 + 42
        for col, (image, name) in enumerate(columns):
            x0 = margin + col * (cw + gap)
            d.rounded_rectangle((x0, py0, x0 + cw, py0 + panel_h), radius=10, fill=(39, 43, 53), outline=(73, 81, 95), width=2)
            d.text((x0 + 12, py0 + 10), name, font=label, fill=(232, 235, 242))
            crop = image.crop(CROP_INPUTS[side]).convert("RGBA")
            bg = Image.new("RGBA", crop.size, (35, 37, 44, 255))
            bg.alpha_composite(crop)
            maxw, maxh = cw - 24, panel_h - 58
            scale = min(maxw / crop.width, maxh / crop.height)
            size = (round(crop.width * scale), round(crop.height * scale))
            thumb = bg.resize(size, Image.Resampling.LANCZOS).convert("RGB")
            px = x0 + (cw - thumb.width) // 2
            py = py0 + 42 + (maxh - thumb.height) // 2
            board.paste(thumb, (px, py))
    footer = "STATIC MOCK ONLY: last column reuses the corrupted source's arm pixels to check registration; replace it with real C foreground parts only after approval."
    d.rounded_rectangle((margin, H - 58, W - margin, H - 18), radius=8, fill=(63, 43, 34), outline=(235, 162, 75), width=2)
    d.text((margin + 14, H - 52), footer, font=label, fill=(255, 223, 175))
    board.save(BOARD, optimize=True)


def main():
    source = Image.open(SOURCE).convert("RGBA")
    polygon_data = json.loads(POLYGONS.read_text(encoding="utf-8"))
    plate = Image.new("RGBA", source.size, (0, 0, 0, 0))
    clean = source.copy()
    details = {}
    for side, obj_box in {"left": (51, 849, 396, 1368), "right": (736, 849, 1081, 1368)}.items():
        x0, y0, x1, y1 = obj_box
        obj_mask = make_object_mask((x1 - x0, y1 - y0), polygon_data["objects"][side])
        front_crop = clean.crop(obj_box)
        front_crop.putalpha(ImageChops.multiply(front_crop.getchannel("A"), ImageChops.invert(obj_mask)))
        clean.paste(front_crop, (x0, y0))

        crop_box = CROP_INPUTS[side]
        proposal = Image.open(PROPOSALS[side]).convert("RGB")
        # Generated canvases are portrait 848x1264; crop the tiny aspect overshoot
        # symmetrically before resampling to the exact registered 440x640 target crop.
        target_w, target_h = crop_box[2] - crop_box[0], crop_box[3] - crop_box[1]
        wanted_h = round(proposal.width * target_h / target_w)
        if proposal.height > wanted_h:
            top = (proposal.height - wanted_h) // 2
            proposal = proposal.crop((0, top, proposal.width, top + wanted_h))
        proposal = proposal.resize((target_w, target_h), Image.Resampling.LANCZOS)
        # Only use generated new-design pixels where the source sprite already has
        # alpha in this crop; keep the plate registration and silhouette bounded.
        existing_alpha = source.getchannel("A").crop(crop_box)
        local_plate = proposal.convert("RGBA")
        local_plate.putalpha(existing_alpha)
        plate.alpha_composite(local_plate, (crop_box[0], crop_box[1]))

        old_fg = source.crop(obj_box)
        old_fg.putalpha(ImageChops.multiply(old_fg.getchannel("A"), obj_mask))
        fg_full = Image.new("RGBA", source.size, (0, 0, 0, 0))
        fg_full.alpha_composite(old_fg, (x0, y0))
        details[side] = {
            "roi_xyxy": list(obj_box),
            "proposal_path": str(PROPOSALS[side].relative_to(ROOT)),
            "proposal_sha256": sha(PROPOSALS[side]),
            "crop_xyxy": list(crop_box),
            "generated_input_size": list(Image.open(PROPOSALS[side]).size),
            "registered_size": [target_w, target_h],
            "source_alpha_pixels": sum(v > 0 for v in existing_alpha.tobytes()),
            "clean_object_mask_pixels": sum(v > 0 for v in obj_mask.tobytes()),
            "mask_sha256": hashlib.sha256(obj_mask.tobytes()).hexdigest(),
        }
        if side == "left":
            mock_fg = fg_full
        else:
            mock_fg.alpha_composite(fg_full)
    # Plate sits behind original hair after the old object foreground is removed.
    hair_only = plate.copy()
    hair_only.alpha_composite(clean)
    # Diagnostic only: reapply old object pixels as if they were a static foreground
    # layer; this checks exact registration and is not a C/rig arm layer.
    old_object_mock = hair_only.copy()
    old_object_mock.alpha_composite(mock_fg)
    plate.save(PLATE, optimize=True)
    clean.save(CLEAN, optimize=True)
    hair_only.save(COMPOSITE, optimize=True)
    make_review(source, plate, clean, hair_only, old_object_mock)

    out_paths = [PLATE, CLEAN, BOARD, COMPOSITE]
    metrics = {
        "task": "T67.71",
        "status": "AI-assisted local new-design redraw WIP; not hidden truth; not accepted; not production",
        "authorization": "User explicitly authorized a new design proposal on 2026-11-05, with the constraint not to depart substantially from the current design.",
        "source": {"path": str(SOURCE.relative_to(ROOT)), "size": list(source.size), "sha256": sha(SOURCE)},
        "visible_object_mask": {"path": str(POLYGONS.relative_to(ROOT)), "sha256": sha(POLYGONS)},
        "method": "Use one tightly framed AI-assisted repaint per side as new design material; register to the exact target ROI; clip the back plate to existing hair-sprite alpha; remove the visible cuff/hand polygons from a separate clean-front layer; plate remains underneath. The mock foreground reuses original contaminated pixels only to verify static registration.",
        "regions": details,
        "outputs": {p.name: {"size": list(Image.open(p).size), "sha256": sha(p)} for p in out_paths},
        "limitations": [
            "Generated proposals are new art, not the original hidden hair; they may change strand topology and painterly detail.",
            "Static mock arm/cuff is copied from the contaminated source and is not a real moving foreground layer.",
            "No local visual acceptance is claimed until both complete sprite and 100/200/400% ROI views pass review.",
            "No C action, transition, ParamHairSway, production sprite, rig, or engine validation has been performed.",
        ],
    }
    METRICS.write_text(json.dumps(metrics, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": metrics["status"], "regions": details, "outputs": metrics["outputs"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
