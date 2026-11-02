#!/usr/bin/env python3
"""Comparison-only board for full-body mitten size feedback; does not alter art."""
from __future__ import annotations
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

OUT = Path(__file__).resolve().parent
FILES = {
    "08": OUT / "chibi_mitten_original_fullbody_concept_trial_08_refined_wip.png",
    "11": OUT / "chibi_mitten_original_fullbody_concept_trial_11_wip.png",
    "12": OUT / "chibi_mitten_original_fullbody_concept_trial_12_wip.png",
    "13": OUT / "chibi_mitten_original_fullbody_concept_trial_13_wip.png",
}
BOARD = OUT / "chibi_mitten_trial_13_fullbody_size_comparison_board_wip.png"


def font(size: int) -> ImageFont.ImageFont:
    for path in ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf"):
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            pass
    return ImageFont.load_default()


def main() -> None:
    imgs = {key: Image.open(path).convert("RGB") for key, path in FILES.items()}
    if len({im.size for im in imgs.values()}) != 1:
        raise ValueError("concept dimensions differ")
    board = Image.new("RGB", (1640, 1600), (247, 246, 244))
    d = ImageDraw.Draw(board)
    d.text((24, 18), "TRIAL 13 · HAND-SIZE CALIBRATION · WIP / NOT PRODUCTION ART", font=font(26), fill=(48, 42, 59))
    d.text((24, 58), "User: trial11 hands too large. Compare 08 → 11 → 12 → 13 in full-body and same-position crops.", font=font(17), fill=(72, 66, 80))
    cols = (("08", 30, "08 · APPROVED DIRECTION"), ("11", 430, "11 · TOO LARGE"), ("12", 830, "12 · REDUCED"), ("13", 1230, "13 · REDUCED AGAIN"))
    for key, x, label in cols:
        d.text((x, 100), label, font=font(15), fill=(48, 42, 59))
        board.paste(imgs[key].resize((360, 360), Image.Resampling.LANCZOS), (x, 128))
    d.text((24, 512), "VIEWER-LEFT CUFF + HAND · SAME 115×145px WINDOW · 3× NEAREST-NEIGHBOUR", font=font(17), fill=(48, 42, 59))
    for key, x, label in cols:
        d.text((x, 545), label, font=font(14), fill=(72, 66, 80))
        crop = imgs[key].crop((305, 625, 420, 770)).resize((345, 435), Image.Resampling.NEAREST)
        board.paste(crop, (x, 572))
    d.text((24, 1020), "VIEWER-RIGHT CUFF + HAND · SAME WINDOW / SCALE", font=font(17), fill=(48, 42, 59))
    for key, x, label in cols:
        d.text((x, 1053), label, font=font(14), fill=(72, 66, 80))
        crop = imgs[key].crop((590, 625, 705, 770)).resize((345, 435), Image.Resampling.NEAREST)
        board.paste(crop, (x, 1080))
    d.text((24, 1550), "AI concept redraws only; cuff/body pixels are not source-exact and no production approval is implied.", font=font(16), fill=(92, 55, 55))
    board.save(BOARD)
    print(f"wrote {BOARD.name}")


if __name__ == "__main__":
    main()
