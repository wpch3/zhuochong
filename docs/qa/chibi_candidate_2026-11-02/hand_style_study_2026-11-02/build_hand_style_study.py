#!/usr/bin/env python3
"""Build a source-locked geometry study for Chibi small/mitten hands.

This writes only into this QA/WIP folder. The original source crops are derived
from the Chibi body_full coordinate system. The procedural mitten silhouette is
explicitly rejected as hand artwork under the project's no-programmatic-hands
rule; it is retained only as an isolated shape/fit diagram. No production
sprite/rig is modified.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter

ROOT = Path(__file__).resolve().parents[4]
OUT = Path(__file__).resolve().parent
BODY = ROOT / "characters/xiaoxun/forms/chibi/sprites/body_full.png"
SOURCE_SHEET = ROOT / "characters/xiaoxun/design/design_sheet_chibi.png"

# body_full pixel crops; preserve the original left/right shape exactly for small.
CROPS = {
    "left": (43, 846, 132, 938),
    "right": (435, 846, 524, 938),
}
# Rejected geometry schematic only, not hand artwork: it keeps Chibi's hanging
# wrist scale and sketches a rounded palm. The repository rule requires source-art
# hands; do not promote this procedural silhouette into art, reference approval,
# a production texture, or rig input. Right is the mirrored anatomy.
LEFT_PATH = (
    (73, 878),
    ((67, 883), (62, 892), (59, 901)),
    ((55, 912), (56, 922), (62, 927)),
    ((69, 932), (80, 931), (89, 929)),
    ((99, 927), (106, 922), (110, 915)),
    ((113, 910), (113, 906), (110, 903)),
    ((107, 900), (102, 900), (99, 904)),
    ((97, 909), (95, 914), (92, 917)),
    ((90, 905), (91, 891), (97, 878)),
    ((89, 876), (79, 876), (73, 878)),
)


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def bezier(p0, p1, p2, p3, n=16):
    t = np.linspace(0.0, 1.0, n, endpoint=False)[:, None]
    omt = 1.0 - t
    pts = (omt**3) * np.asarray(p0) + 3 * (omt**2) * t * np.asarray(p1) + 3 * omt * (t**2) * np.asarray(p2) + (t**3) * np.asarray(p3)
    return [tuple(map(float, p)) for p in pts]


def path_points(side: str):
    points = [LEFT_PATH[0]]
    current = LEFT_PATH[0]
    for c1, c2, end in LEFT_PATH[1:]:
        points.extend(bezier(current, c1, c2, end))
        current = end
    points.append(LEFT_PATH[0])
    if side == "right":
        return [(566.0 - x, y) for x, y in points]
    return points


def cuff_layer(body: Image.Image, side: str, box):
    crop = body.crop(box).convert("RGBA")
    x0, y0, x1, y1 = box
    # This polygon follows the actual lower cuff seam in body_full space. The
    # whole source region above it is kept byte-for-byte, including line art,
    # antialiasing and stripe colors; it also occludes the new hand's insertion.
    edge = {
        "left": [(43, 878), (61, 878), (73, 879), (84, 883), (94, 889), (105, 895), (116, 899), (132, 900)],
        "right": [(435, 890), (446, 893), (457, 896), (469, 898), (479, 896), (489, 891), (500, 888), (524, 888)],
    }[side]
    local_edge = [(x - x0, y - y0) for x, y in edge]
    mask = Image.new("L", crop.size, 0)
    ImageDraw.Draw(mask).polygon([(0, 0), (crop.width, 0), (crop.width, local_edge[-1][1])] + local_edge[::-1], fill=255)
    return crop, mask


def draw_mitten(body: Image.Image, side: str, box):
    x0, y0, x1, y1 = box
    w, h = x1 - x0, y1 - y0
    s = 8
    high = Image.new("RGBA", (w * s, h * s), (0, 0, 0, 0))
    draw = ImageDraw.Draw(high)
    points = [((x - x0) * s, (y - y0) * s) for x, y in path_points(side)]
    # Colors sampled from the source Chibi hand's skin and nearby outline range.
    draw.polygon(points, fill=(253, 234, 222, 255))
    draw.line(points, fill=(91, 75, 95, 255), width=8, joint="curve")
    hand = high.resize((w, h), Image.Resampling.LANCZOS)

    # Keep the original source sleeve/cuff over the hand insertion. The matching
    # hand is rendered underneath so the cuff edge, stripes and line work stay
    # from the Chibi source, not from the concept generator.
    source_cuff, mask = cuff_layer(body, side, box)
    hand.alpha_composite(Image.composite(source_cuff, Image.new("RGBA", (w, h)), mask))
    return hand


def skin_count(im):
    a = np.asarray(im.convert("RGBA"), dtype=np.int16)
    r, g, b, alpha = a[..., 0], a[..., 1], a[..., 2], a[..., 3]
    m = (alpha > 128) & (r > 200) & (g > 150) & (b > 130) & ((r - b) < 90)
    return int(m.sum()), int(np.where(m)[1].min()) if m.any() else -1, int(np.where(m)[1].max() + 1) if m.any() else -1, int(np.where(m)[0].min()) if m.any() else -1, int(np.where(m)[0].max() + 1) if m.any() else -1


def main():
    body = Image.open(BODY).convert("RGBA")
    small = {}
    mitten = {}
    stats = {}
    fullbody_mitten = body.copy()
    for side, box in CROPS.items():
        original = body.crop(box)
        small[side] = original
        candidate = draw_mitten(body, side, box)
        mitten[side] = candidate
        original.save(OUT / f"small_{side}_source.png")
        candidate.save(OUT / f"mitten_{side}_concept.png")

        # For proportion review only: remove the source hand's warm-skin pixels
        # and its immediate outline in this wrist ROI, then composite the WIP
        # mitten over the same Chibi body. The source file remains untouched.
        arr = np.asarray(original).copy()
        rr, gg, bb, aa = [arr[..., i].astype(np.int16) for i in range(4)]
        skin = (aa > 24) & (rr > 200) & (gg > 150) & (bb > 130) & ((rr - bb) < 90)
        erase = Image.fromarray((skin * 255).astype(np.uint8), "L").filter(ImageFilter.MaxFilter(5))
        cut = np.asarray(erase) > 0
        arr[cut, 3] = 0
        arr[cut, :3] = 0
        fullbody_mitten.paste(Image.fromarray(arr.astype(np.uint8), "RGBA"), (box[0], box[1]))
        fullbody_mitten.alpha_composite(candidate, (box[0], box[1]))
        stats[side] = {
            "body_full_roi_xyxy_exclusive": list(box),
            "crop_size": list(original.size),
            "small_skin_bbox_local_xyxy_exclusive": list(skin_count(original)[1:]),
            "mitten_skin_bbox_local_xyxy_exclusive": list(skin_count(candidate)[1:]),
            "small_skin_pixels_thresholded": skin_count(original)[0],
            "mitten_skin_pixels_thresholded": skin_count(candidate)[0],
            "source_hand_erasure": "warm-skin threshold within the recorded wrist crop plus 2px outline dilation; only applied to WIP full-body preview",
        }
    fullbody_mitten.save(OUT / "body_full_mitten_preview_wip.png")

    # Comparison sheet: source/candidate full-body thumbnails provide identity
    # context; detailed panels show source small vs WIP mitten at 4x nearest.
    scale = 4
    canvas = Image.new("RGB", (1500, 1120), (247, 246, 243))
    d = ImageDraw.Draw(canvas)
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 23)
        small_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 15)
    except OSError:
        font = ImageFont.load_default()
        small_font = ImageFont.load_default()
    d.text((28, 22), "XIAOXUN · CHIBI HAND-STYLE STUDY · WIP / NOT PRODUCTION", font=font, fill=(50, 44, 62))
    d.text((28, 58), "Source-locked small hands vs. rejected procedural mitten geometry; not valid hand artwork.", font=small_font, fill=(74, 68, 83))
    # Context figures on a neutral field, side by side.
    for i, (figure, label) in enumerate(((body.copy(), "source body_full"), (fullbody_mitten.copy(), "WIP mitten overlay"))):
        figure.thumbnail((165, 390), Image.Resampling.LANCZOS)
        bg = Image.new("RGBA", figure.size, (236, 235, 238, 255))
        bg.alpha_composite(figure)
        fx = 38 + i * 190
        canvas.paste(bg.convert("RGB"), (fx, 145))
        d.text((fx, 545), label, font=small_font, fill=(74, 68, 83))

    panel_x = [455, 960]
    panel_y = [132, 592]
    headings = [("small · original source", (small["left"], small["right"])), ("mitten · rejected geometry only", (mitten["left"], mitten["right"]))]
    for col, (title, pair) in enumerate(headings):
        d.text((panel_x[col], 105), title, font=font, fill=(50, 44, 62))
        for row, hand in enumerate(pair):
            x, y = panel_x[col], panel_y[row]
            # checkerboard transparency preview
            preview = hand.resize((hand.width * scale, hand.height * scale), Image.Resampling.NEAREST)
            check = Image.new("RGBA", preview.size, (0, 0, 0, 0))
            cd = ImageDraw.Draw(check)
            cell = 24
            for yy in range(0, preview.height, cell):
                for xx in range(0, preview.width, cell):
                    if (xx // cell + yy // cell) % 2 == 0:
                        cd.rectangle((xx, yy, xx + cell - 1, yy + cell - 1), fill=(224, 222, 228, 255))
                    else:
                        cd.rectangle((xx, yy, xx + cell - 1, yy + cell - 1), fill=(244, 243, 246, 255))
            check.alpha_composite(preview)
            canvas.paste(check.convert("RGB"), (x, y))
            label = "left" if row == 0 else "right"
            d.text((x, y + preview.height + 5), f"{label} · body_full crop {CROPS[label][0]},{CROPS[label][1]} …", font=small_font, fill=(74, 68, 83))
    d.text((455, 1040), "Rejected schematic: no-programmatic-hands rule applies; not art, texture, rig input, or visual acceptance.", font=small_font, fill=(116, 52, 56))
    canvas.save(OUT / "hand_style_board_wip.png")

    manifest = {
        "status": "wip_geometry_study_procedural_mitten_rejected_as_art",
        "source_sheet": str(SOURCE_SHEET.relative_to(ROOT)),
        "source_sheet_sha256": sha(SOURCE_SHEET),
        "source_body_full": str(BODY.relative_to(ROOT)),
        "source_body_full_sha256": sha(BODY),
        "source_sheet_crop_and_fit": {
            "box": [628, 101, 1416, 1891],
            "body_full_size": [567, 1292],
            "note": "body_full was re-derived from the Chibi-owned design sheet geometry; hand crop coordinates are body_full coordinates."
        },
        "hand_crops": stats,
        "constraints": [
            "small is the exact current Chibi source crop, not re-drawn",
            "mitten is a procedural geometry schematic explicitly rejected as hand artwork under the no-programmatic-hands rule",
            "the schematic uses a Chibi source-derived cuff but is not an approved art reference, texture, or rig input",
            "no marked screenshot or Teen hand assets used",
            "production sprites and rig untouched"
        ],
        "files": {},
    }
    for name in ["small_left_source.png", "small_right_source.png", "mitten_left_concept.png", "mitten_right_concept.png", "body_full_mitten_preview_wip.png", "hand_style_board_wip.png"]:
        manifest["files"][name] = sha(OUT / name)
    (OUT / "study_metrics.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("wrote source-locked geometry study; procedural mitten schematic remains rejected as art")


if __name__ == "__main__":
    main()
