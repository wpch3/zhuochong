#!/usr/bin/env python3
"""Comparison-only trial08/11/12 board; source concepts are never edited."""
from __future__ import annotations
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

OUT = Path(__file__).resolve().parent
FILES = {
    "08": OUT / "chibi_mitten_original_fullbody_concept_trial_08_refined_wip.png",
    "11": OUT / "chibi_mitten_original_fullbody_concept_trial_11_wip.png",
    "12": OUT / "chibi_mitten_original_fullbody_concept_trial_12_wip.png",
}
BOARD = OUT / "chibi_mitten_trial_12_fullbody_size_comparison_board_wip.png"


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
    imgs = {key: Image.open(path).convert("RGB") for key, path in FILES.items()}
    sizes = {im.size for im in imgs.values()}
    if len(sizes) != 1:
        raise ValueError(f"full-body concept dimensions differ: {sizes}")

    board = Image.new("RGB", (1500, 1600), (247, 246, 244))
    draw = ImageDraw.Draw(board)
    draw.text((28, 18), "TRIAL 12 · MITTEN SIZE CALIBRATION · WIP / NOT PRODUCTION ART", font=font(27), fill=(48, 42, 59))
    draw.text((28, 60), "Trial11 feedback: hands too large. Compare 08 → 11 → 12 at full-body scale and same-position crops.", font=font(18), fill=(72, 66, 80))

    columns = (("08", 50, "TRIAL 08 · APPROVED DIRECTION"), ("11", 550, "TRIAL 11 · TOO LARGE"), ("12", 1050, "TRIAL 12 · REDUCED SIZE"))
    for key, x, label in columns:
        draw.text((x, 105), label, font=font(17), fill=(48, 42, 59))
        board.paste(imgs[key].resize((400, 400), Image.Resampling.LANCZOS), (x, 135))

    crop_x = (50, 550, 1050)
    draw.text((28, 555), "VIEWER-LEFT CUFF + HAND · IDENTICAL 115×145px SOURCE-POSITION WINDOW · 3× NEAREST-NEIGHBOUR", font=font(18), fill=(48, 42, 59))
    for (key, _, label), x in zip(columns, crop_x):
        draw.text((x, 588), label, font=font(15), fill=(72, 66, 80))
        crop = imgs[key].crop((305, 625, 420, 770)).resize((345, 435), Image.Resampling.NEAREST)
        board.paste(crop, (x, 615))

    draw.text((28, 1072), "VIEWER-RIGHT CUFF + HAND · SAME WINDOW / SCALE", font=font(18), fill=(48, 42, 59))
    for (key, _, label), x in zip(columns, crop_x):
        draw.text((x, 1105), label, font=font(15), fill=(72, 66, 80))
        crop = imgs[key].crop((590, 625, 705, 770)).resize((345, 435), Image.Resampling.NEAREST)
        board.paste(crop, (x, 1132))

    draw.text((28, 1580), "AI full-body concepts only. Cuffs/body are redraws; no source-aligned parts, hidden wrist, rig, or engine acceptance.", font=font(16), fill=(92, 55, 55))
    board.save(BOARD)
    print(f"wrote {BOARD.name}: three full-body sizes and identical left/right cuff-hand crops")


if __name__ == "__main__":
    main()
