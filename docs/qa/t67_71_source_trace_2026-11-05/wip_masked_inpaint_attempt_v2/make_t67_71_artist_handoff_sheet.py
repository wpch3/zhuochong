#!/usr/bin/env python3
"""Build a source-only artist handoff board for T67.71.

This assembles existing source evidence and current target crops. It does NOT
paint, infer, transfer, or alter any hidden hair pixels. QA-only output.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

BASE = Path(__file__).resolve().parent
ROOT = Path(__file__).resolve().parents[4]
SOURCE = ROOT / "characters/xiaoxun/design/sheets/sheet_long_hood.png"
TARGET = ROOT / "characters/xiaoxun/forms/teen/sprites/hair_hood_long@2x.png"
RAW_CROP_BOARD = BASE / "49_raw_source_cuff_hand_crop_review.png"
OUT = BASE / "105_artist_handoff_reference.png"
METRICS = BASE / "106_artist_handoff_metrics.json"
BOXES = {"LEFT": (51, 849, 396, 1368), "RIGHT": (736, 849, 1081, 1368)}
# Approximate back-map from the resampled production sprite, documented in
# 2026-11-04/capture_metrics.json. These mark source-sheet locations only.
SOURCE_BOXES = {
    "LEFT": (270.59, 790.78, 312.17, 858.21),
    "RIGHT": (702.08, 791.35, 744.22, 858.21),
}
W, H = 2800, 1840
BG = (242, 242, 247)
INK = (34, 39, 51)
MUTED = (83, 91, 107)
BLUE = (34, 143, 199)
ORANGE = (236, 123, 52)
RED = (188, 52, 63)
GREEN = (52, 143, 105)
FONT_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
FONT_BOLD_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(FONT_BOLD_PATH if bold else FONT_PATH, size)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def fit(im: Image.Image, box: tuple[int, int]) -> Image.Image:
    return im.copy().convert("RGBA")


def scale_to(im: Image.Image, max_w: int, max_h: int) -> Image.Image:
    im = im.convert("RGBA")
    s = min(max_w / im.width, max_h / im.height)
    return im.resize((max(1, round(im.width * s)), max(1, round(im.height * s))), Image.Resampling.LANCZOS)


def checker(size: tuple[int, int], step: int = 24) -> Image.Image:
    w, h = size
    im = Image.new("RGB", size, (232, 232, 237))
    d = ImageDraw.Draw(im)
    for y in range(0, h, step):
        for x in range(0, w, step):
            if (x // step + y // step) % 2:
                d.rectangle((x, y, x + step - 1, y + step - 1), fill=(205, 207, 215))
    return im


def panel(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], title: str) -> None:
    x0, y0, x1, y1 = box
    draw.rounded_rectangle(box, radius=24, fill=(255, 255, 255), outline=(210, 213, 222), width=3)
    draw.text((x0 + 28, y0 + 20), title, font=font(30, True), fill=INK)


def wrap(draw: ImageDraw.ImageDraw, xy: tuple[int, int], text: str, width: int, fnt: ImageFont.FreeTypeFont, fill=INK, leading=8) -> int:
    words = text.split()
    lines: list[str] = []
    line = ""
    for word in words:
        test = word if not line else line + " " + word
        if draw.textbbox((0, 0), test, font=fnt)[2] <= width:
            line = test
        else:
            if line:
                lines.append(line)
            line = word
    if line:
        lines.append(line)
    x, y = xy
    for line in lines:
        draw.text((x, y), line, font=fnt, fill=fill)
        y += fnt.size + leading
    return y


def main() -> None:
    source = Image.open(SOURCE).convert("RGB")
    target = Image.open(TARGET).convert("RGBA")
    raw_board = Image.open(RAW_CROP_BOARD).convert("RGB")
    board = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(board)

    d.text((64, 38), "T67.71  |  AUTHOR HANDOFF  |  SOURCE REQUEST ONLY", font=font(45, True), fill=INK)
    d.text((68, 104), "No accepted hair reconstruction. Highlighted boxes locate the problem; they do NOT define hidden strand geometry.", font=font(25), fill=RED)

    # A: flattened, full-body source with approximate back-mapped locations.
    a = (60, 170, 600, 1230)
    panel(d, a, "A  FLAT SOURCE — CONTEXT")
    src_disp = scale_to(source, 475, 820)
    ax = a[0] + (a[2] - a[0] - src_disp.width) // 2
    ay = a[1] + 86
    board.paste(src_disp.convert("RGB"), (ax, ay))
    scale_x, scale_y = src_disp.width / source.width, src_disp.height / source.height
    for side, color in (("LEFT", BLUE), ("RIGHT", ORANGE)):
        x0, y0, x1, y1 = SOURCE_BOXES[side]
        rect = (round(ax + x0 * scale_x), round(ay + y0 * scale_y), round(ax + x1 * scale_x), round(ay + y1 * scale_y))
        d.rectangle(rect, outline=color, width=7)
        d.text((rect[0] + 7, rect[1] - 30), side, font=font(18, True), fill=color)
    wrap(d, (a[0] + 28, a[1] + 920), "Flattened RGB. The hands/cuffs cover the hair; the source does not contain the hidden pixels underneath.", a[2] - a[0] - 56, font(21), MUTED)
    wrap(d, (a[0] + 28, a[1] + 1000), "Boxes are approximate source-sheet mapping after crop/resampling, not paint masks.", a[2] - a[0] - 56, font(18), MUTED)

    # B: actual raw cutout crop, showing the contamination that reached the hair layer.
    b = (625, 170, 1730, 1230)
    panel(d, b, "B  ENLARGED RAW CUTOUT — VISIBLE OBJECTS")
    raw_disp = scale_to(raw_board, 1040, 790)
    bx = b[0] + (b[2] - b[0] - raw_disp.width) // 2
    by = b[1] + 90
    board.paste(raw_disp, (bx, by))
    wrap(d, (b[0] + 28, b[1] + 930), "The extracted hair cutout visibly includes cuff bands and hand/finger pixels. This is observed source content, not a reconstruction target.", b[2] - b[0] - 56, font(21), MUTED)
    wrap(d, (b[0] + 28, b[1] + 1010), "Do not trace these object contours as the shape of new hair.", b[2] - b[0] - 56, font(21, True), RED)

    # C: current production target crops, shown against checkerboard to preserve alpha.
    c = (1755, 170, 2740, 1230)
    panel(d, c, "C  CURRENT TARGET — ALPHA CONTEXT")
    crop_y = c[1] + 104
    crop_w, crop_h = 420, 632
    for index, (side, color) in enumerate((("LEFT", BLUE), ("RIGHT", ORANGE))):
        crop = target.crop(BOXES[side])
        crop = scale_to(crop, crop_w, crop_h)
        x = c[0] + 40 + index * 465
        matte = checker((crop.width, crop.height))
        matte_rgba = matte.convert("RGBA")
        matte_rgba.alpha_composite(crop)
        board.paste(matte_rgba.convert("RGB"), (x, crop_y))
        d.rectangle((x, crop_y, x + crop.width - 1, crop_y + crop.height - 1), outline=color, width=5)
        d.text((x, crop_y + crop.height + 12), f"{side} crop 345 x 519 px", font=font(20, True), fill=color)
    wrap(d, (c[0] + 30, c[1] + 850), "The current hair sprite still shows cuff/hand pixels. Separately audited transparent blocks are a distinct issue; neither their boundaries nor this crop prove hidden hair topology.", c[2] - c[0] - 60, font(20), MUTED)
    wrap(d, (c[0] + 30, c[1] + 970), "No candidate art is shown on this board.", c[2] - c[0] - 60, font(22, True), RED)

    # Deliverable contract and stage gates.
    d.rounded_rectangle((60, 1260, 2740, 1775), radius=24, fill=(255, 255, 255), outline=(210, 213, 222), width=3)
    d.text((90, 1280), "REQUESTED SOURCE PACKAGE", font=font(30, True), fill=INK)
    columns = [
        ("1  SOURCE", "Provide an approved layered source for this exact long-hood form, or an explicitly authored repair layer. Keep the original canvas and registration; no mirrored left/right assumption."),
        ("2  SEPARATE PARTS", "Deliver complete back-hair beneath moving arms, with cuff/hand foreground separate or sufficient overlap. Hair alpha must be continuous where the design requires it; do not flatten the moving objects into hair."),
        ("3  LOCAL REVIEW", "Export RGBA PNG plus editable layered file. Review full-body and both 345x519 ROIs at 100-400%. Require natural flow, palette/value integration, clean edges, no cuff/hand silhouettes, and no unexplained gaps."),
        ("4  REAL C GATE", "Only after local review passes: test isolated copies in real C across idle, surprised, wave, wave_both, heart_hands and transitions; separate arm action from ParamHairSway (-1/0/+1), with object-only/hidden controls."),
    ]
    col_w = 625
    for i, (head, body) in enumerate(columns):
        x = 90 + i * 650
        d.text((x, 1335), head, font=font(23, True), fill=(GREEN if i < 3 else BLUE))
        wrap(d, (x, 1380), body, col_w - 20, font(19), INK, leading=7)
    d.text((90, 1730), "Gate order: approved source -> isolated art -> agent local visual pass -> real C action/transition matrix -> user approval -> production. No production change is authorized by this brief.", font=font(20, True), fill=RED)

    board.save(OUT, optimize=True)
    report = {
        "task": "T67.71",
        "status": "source-only author handoff; not a hair candidate and not a repair",
        "production_changes": False,
        "source_sheet": {"path": str(SOURCE.relative_to(ROOT)), "sha256": sha256(SOURCE), "dimensions": list(source.size), "flattened": True},
        "target_sprite": {"path": str(TARGET.relative_to(ROOT)), "sha256": sha256(TARGET), "dimensions": list(target.size)},
        "raw_cutout_crop_board": {"path": str(RAW_CROP_BOARD.relative_to(ROOT)), "sha256": sha256(RAW_CROP_BOARD)},
        "visually_audited_nonmatching_style_sources": {
            str((ROOT / "characters/xiaoxun/forms/teen/sprites/hair_long_back@2x.png").relative_to(ROOT)): sha256(ROOT / "characters/xiaoxun/forms/teen/sprites/hair_long_back@2x.png"),
            str((ROOT / "characters/xiaoxun/forms/teen/sprites/hair_hood_pony@2x.png").relative_to(ROOT)): sha256(ROOT / "characters/xiaoxun/forms/teen/sprites/hair_hood_pony@2x.png"),
            str((ROOT / "characters/xiaoxun/forms/teen/sprites/hair_hood_twin@2x.png").relative_to(ROOT)): sha256(ROOT / "characters/xiaoxun/forms/teen/sprites/hair_hood_twin@2x.png"),
        },
        "target_crop_boxes_xyxy_half_open": BOXES,
        "approx_source_sheet_boxes_xyxy": SOURCE_BOXES,
        "output": str(OUT.relative_to(ROOT)),
        "output_sha256": sha256(OUT),
        "output_dimensions": [W, H],
        "visual_claim": "Boxes localize source evidence only; hidden hair shape remains unknown. No pixels were painted, inferred, or transferred.",
        "next_gate": "author-approved layered source or explicitly authored repair layer; then local visual pass before any real C test",
    }
    METRICS.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(OUT.relative_to(ROOT)), "sha256": report["output_sha256"], "dimensions": report["output_dimensions"], "status": report["status"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
