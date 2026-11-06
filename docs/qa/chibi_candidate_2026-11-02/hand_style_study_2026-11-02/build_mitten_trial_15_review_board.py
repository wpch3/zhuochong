#!/usr/bin/env python3
"""Comparison-only review board for reduced-size trial15 full-body concept."""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

OUT = Path(__file__).resolve().parent
FILES = {
    "08": OUT / "chibi_mitten_original_fullbody_concept_trial_08_refined_wip.png",
    "11": OUT / "chibi_mitten_original_fullbody_concept_trial_11_wip.png",
    "13": OUT / "chibi_mitten_original_fullbody_concept_trial_13_wip.png",
    "14": OUT / "chibi_mitten_original_fullbody_concept_trial_14_wip.png",
    "15": OUT / "chibi_mitten_original_fullbody_concept_trial_15_wip.png",
}
BOARD = OUT / "chibi_mitten_trial_15_fullbody_size_comparison_board_wip.png"
LABELS = {
    "08": "08 · APPROVED DIRECTION",
    "11": "11 · TOO LARGE",
    "13": "13 · TOO LARGE",
    "14": "14 · TOO LARGE",
    "15": "15 · REVIEW CANDIDATE",
}

def font(size):
    for path in ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf"):
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            pass
    return ImageFont.load_default()

def main():
    imgs = {k: Image.open(v).convert("RGB") for k, v in FILES.items()}
    if len({im.size for im in imgs.values()}) != 1:
        raise ValueError("concept dimensions differ")
    board = Image.new("RGB", (2000, 1530), (247, 246, 244))
    d = ImageDraw.Draw(board)
    d.text((24, 18), "TRIAL 15 · SMALLER MITTEN SIZE · WIP / NOT PRODUCTION ART", font=font(27), fill=(48, 42, 59))
    d.text((24, 60), "Trials 11–14 were judged too large. Compare 08 / 11 / 13 / 14 / 15 at matched full-body scale and hand crops.", font=font(17), fill=(72, 66, 80))
    xs = [24, 420, 816, 1212, 1608]
    for key, x in zip(FILES, xs):
        d.text((x, 100), LABELS[key], font=font(15), fill=(48, 42, 59))
        board.paste(imgs[key].resize((360, 360), Image.Resampling.LANCZOS), (x, 126))
    d.text((24, 505), "VIEWER-LEFT CUFF + HAND · SAME 115×145px WINDOW · 3× NEAREST-NEIGHBOUR", font=font(17), fill=(48, 42, 59))
    for key, x in zip(FILES, xs):
        d.text((x, 536), LABELS[key], font=font(14), fill=(72, 66, 80))
        board.paste(imgs[key].crop((305, 625, 420, 770)).resize((276, 348), Image.Resampling.NEAREST), (x, 560))
    d.text((24, 930), "VIEWER-RIGHT CUFF + HAND · SAME WINDOW / SCALE", font=font(17), fill=(48, 42, 59))
    for key, x in zip(FILES, xs):
        d.text((x, 961), LABELS[key], font=font(14), fill=(72, 66, 80))
        board.paste(imgs[key].crop((590, 625, 705, 770)).resize((276, 348), Image.Resampling.NEAREST), (x, 985))
    d.text((24, 1395), "AI concept redraws only. Not source-exact; no hand layers, hidden wrist, rig, or engine approval.", font=font(16), fill=(92, 55, 55))
    board.save(BOARD)
    print(f"wrote {BOARD.name}")

if __name__ == "__main__":
    main()
