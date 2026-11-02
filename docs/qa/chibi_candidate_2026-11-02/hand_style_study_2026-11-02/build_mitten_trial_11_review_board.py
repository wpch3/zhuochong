#!/usr/bin/env python3
"""Build a comparison-only review board; never edits either concept image."""
from __future__ import annotations

from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

OUT = Path(__file__).resolve().parent
TRIAL08 = OUT / "chibi_mitten_original_fullbody_concept_trial_08_refined_wip.png"
TRIAL11 = OUT / "chibi_mitten_original_fullbody_concept_trial_11_wip.png"
BOARD = OUT / "chibi_mitten_trial_11_fullbody_and_hand_detail_review_board_wip.png"


def font(size: int) -> ImageFont.ImageFont:
    for path in (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
    ):
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            pass
    return ImageFont.load_default()


def main() -> None:
    im08 = Image.open(TRIAL08).convert("RGB")
    im11 = Image.open(TRIAL11).convert("RGB")
    if im08.size != im11.size:
        raise ValueError(f"concept dimensions differ: {im08.size} vs {im11.size}")

    board = Image.new("RGB", (1540, 1300), (247, 246, 244))
    d = ImageDraw.Draw(board)
    d.text((28, 20), "TRIAL 11 · FULL-BODY MITTEN SIZE STUDY · WIP / NOT PRODUCTION ART", font=font(27), fill=(48, 42, 59))
    d.text((28, 62), "Same approved trial-08 concept direction; compare whole-body scale first, then cuff/hand detail.", font=font(18), fill=(72, 66, 80))

    full_w = 500
    full_h = 500
    for x, im, label in (
        (155, im08, "TRIAL 08 · USER-APPROVED VISUAL DIRECTION"),
        (885, im11, "TRIAL 11 · LARGER MITTEN CONCEPT · REVIEW PENDING"),
    ):
        d.text((x, 100), label, font=font(18), fill=(48, 42, 59))
        thumb = im.resize((full_w, full_h), Image.Resampling.LANCZOS)
        board.paste(thumb, (x, 132))

    d.text((28, 658), "CUFF + HAND DETAIL · SAME 115×145 SOURCE-POSITION WINDOW · 3× NEAREST-NEIGHBOUR", font=font(19), fill=(48, 42, 59))
    crops = (
        ("TRIAL 08 · VIEWER-LEFT", im08, (305, 625, 420, 770), 30),
        ("TRIAL 11 · VIEWER-LEFT", im11, (305, 625, 420, 770), 400),
        ("TRIAL 08 · VIEWER-RIGHT", im08, (590, 625, 705, 770), 800),
        ("TRIAL 11 · VIEWER-RIGHT", im11, (590, 625, 705, 770), 1170),
    )
    for label, im, box, x in crops:
        d.text((x, 692), label, font=font(16), fill=(72, 66, 80))
        crop = im.crop(box).resize((345, 435), Image.Resampling.NEAREST)
        board.paste(crop, (x, 722))

    d.text((28, 1180), "Concept-only AI redraw. Cuffs/figure are not source pixels; no layers, hidden wrist, rig, or engine acceptance implied.", font=font(17), fill=(92, 55, 55))
    board.save(BOARD)
    print(f"wrote {BOARD.name}: full-body comparison plus four same-position nearest-neighbour crops")


if __name__ == "__main__":
    main()
