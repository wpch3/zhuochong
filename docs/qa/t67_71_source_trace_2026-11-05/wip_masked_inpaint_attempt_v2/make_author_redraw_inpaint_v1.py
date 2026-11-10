#!/usr/bin/env python3
"""T67.71 isolated author-redraw WIP: continue visible hair texture through occluders.

This is a deliberately inferred redraw candidate, NOT recovered hidden pixels or
an accepted repair. It uses only the same sprite's immediately adjacent vertical
hair colors/strands and a hand-traced visible cuff/hand mask. The output is for
local review only; never overwrite production or install in C without passing
all gates and explicit approval.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter

ROOT = Path(__file__).resolve().parents[4]
BASE = Path(__file__).resolve().parent
SOURCE = ROOT / "characters/xiaoxun/forms/teen/sprites/hair_hood_long@2x.png"
POLYGONS = BASE / "manual_artifact_silhouette_polygons_v3.json"
OUT = BASE / "110_author_redraw_inpaint_v1_wip.png"
BOARD = BASE / "111_author_redraw_inpaint_v1_local_review.png"
METRICS = BASE / "112_author_redraw_inpaint_v1_metrics.json"
ROIS = {"left": (51, 849, 396, 1368), "right": (736, 849, 1081, 1368)}
DILATE_RADIUS = 2


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def srgb_to_linear(v: float) -> float:
    v /= 255.0
    return v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4


def linear_to_srgb(v: float) -> int:
    v = max(0.0, min(1.0, v))
    c = 12.92 * v if v <= 0.0031308 else 1.055 * (v ** (1 / 2.4)) - 0.055
    return max(0, min(255, round(c * 255)))


def make_mask(size, shapes):
    mask = Image.new("L", size, 0)
    draw = ImageDraw.Draw(mask)
    for poly in shapes:
        draw.polygon([tuple(map(float, p)) for p in poly], fill=255)
    if DILATE_RADIUS:
        mask = mask.filter(ImageFilter.MaxFilter(DILATE_RADIUS * 2 + 1))
    return mask


def find_visible_y(alpha, mask, x, y, step, max_steps=80):
    h = len(alpha)
    for dist in range(1, max_steps + 1):
        yy = y + step * dist
        if yy < 0 or yy >= h:
            return None
        if mask[yy][x] < 128 and alpha[yy][x] >= 180:
            return yy
    return None


def interpolate_run(pixels, alpha, mask, x, y0, y1):
    above = find_visible_y(alpha, mask, x, y0, -1)
    below = find_visible_y(alpha, mask, x, y1, +1)
    if above is None and below is None:
        # No local opaque hair on this scanline: remove the baked object here
        # rather than inventing an isolated floating strand.
        for y in range(y0, y1 + 1):
            pixels[y][x] = (0, 0, 0, 0)
        return {"mode": "transparent_no_hair_boundary"}

    top = pixels[above][x] if above is not None else None
    bot = pixels[below][x] if below is not None else None
    length = y1 - y0 + 1
    for y in range(y0, y1 + 1):
        if top is not None and bot is not None:
            t = (y - y0 + 1) / (length + 1)
            rgb = tuple(
                linear_to_srgb(srgb_to_linear(top[c]) * (1 - t) + srgb_to_linear(bot[c]) * t)
                for c in range(3)
            )
            a = round(top[3] * (1 - t) + bot[3] * t)
        elif top is not None:
            rgb, a = top[:3], top[3]
        else:
            rgb, a = bot[:3], bot[3]
        pixels[y][x] = (*rgb, a)
    return {"mode": "vertical_neighbor_interpolation", "above_y": above, "below_y": below}


def run():
    source = Image.open(SOURCE).convert("RGBA")
    original = source.copy()
    poly_data = json.loads(POLYGONS.read_text(encoding="utf-8"))
    art = source.load()
    totals = {}

    for side, box in ROIS.items():
        x0, y0, x1, y1 = box
        w, h = x1 - x0, y1 - y0
        obj = poly_data["objects"][side]
        mask = make_mask((w, h), [obj["cuff"], obj["hand"]])
        ma = list(mask.tobytes())
        mgrid = [ma[y * w : (y + 1) * w] for y in range(h)]
        crop = source.crop(box)
        raw_rgba = crop.tobytes()
        rgba = [tuple(raw_rgba[i : i + 4]) for i in range(0, len(raw_rgba), 4)]
        pix = [rgba[y * w : (y + 1) * w] for y in range(h)]
        agrid = [[pix[y][x][3] for x in range(w)] for y in range(h)]
        spans = []
        mask_hits = 0
        reconstructed = 0
        erased = 0
        for x in range(w):
            y = 0
            while y < h:
                if mgrid[y][x] < 128:
                    y += 1
                    continue
                start = y
                while y + 1 < h and mgrid[y + 1][x] >= 128:
                    y += 1
                end = y
                mask_hits += end - start + 1
                result = interpolate_run(pix, agrid, mgrid, x, start, end)
                if result["mode"] == "transparent_no_hair_boundary":
                    erased += end - start + 1
                else:
                    reconstructed += end - start + 1
                spans.append({"x": x, "y0": start, "y1": end, **result})
                y += 1

        repaired = Image.new("RGBA", (w, h))
        repaired.putdata([px for row in pix for px in row])
        source.paste(repaired, (x0, y0))
        totals[side] = {
            "roi_xyxy": list(box),
            "visible_object_mask_dilated_px": mask_hits,
            "pixels_interpolated_from_same_column_neighbors": reconstructed,
            "pixels_left_transparent_no_local_hair_boundary": erased,
            "mask_sha256": hashlib.sha256(mask.tobytes()).hexdigest(),
            "span_count": len(spans),
            "span_modes": {
                "vertical_neighbor_interpolation": sum(s["mode"] == "vertical_neighbor_interpolation" for s in spans),
                "transparent_no_hair_boundary": sum(s["mode"] == "transparent_no_hair_boundary" for s in spans),
            },
            "spans": spans,
        }

    source.save(OUT, optimize=True)
    build_board(original, source)
    metrics = {
        "task": "T67.71",
        "status": "isolated author-redraw WIP; local-review only; not hidden truth, not accepted, not production",
        "method": "directional same-sprite inpainting: for the manually traced visible cuff/hand silhouette, blend the nearest opaque pixels above and below each x-column in linear-light sRGB; leave a run transparent if no local opaque hair boundary exists",
        "source": {"path": str(SOURCE.relative_to(ROOT)), "sha256": sha(SOURCE), "size": list(original.size)},
        "visible_artifact_mask": {"path": str(POLYGONS.relative_to(ROOT)), "sha256": sha(POLYGONS)},
        "dilate_radius_px": DILATE_RADIUS,
        "regions": totals,
        "outputs": {
            OUT.name: {"size": list(source.size), "sha256": sha(OUT)},
            BOARD.name: {"size": list(Image.open(BOARD).size), "sha256": sha(BOARD)},
        },
        "limitations": [
            "The hidden strand topology is unknown; interpolation is a new artistic reconstruction, not recovered original pixels.",
            "The visible-object polygons can include legitimate adjacent hair; inspect all boundaries at 100%, 200%, and 400% on light and dark backgrounds.",
            "This script does not create front/back rig layers or render the real C engine.",
            "Do not submit to C unless the local visual gate passes; do not promote to production without full action/transition review and approval.",
        ],
    }
    METRICS.write_text(json.dumps(metrics, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": metrics["status"], "outputs": metrics["outputs"], "regions": {k: {q: v for q, v in x.items() if q != "spans"} for k, x in totals.items()}}, ensure_ascii=False, indent=2))


def build_board(before: Image.Image, after: Image.Image):
    from PIL import ImageFont

    try:
        ftitle = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 30)
        fsmall = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 18)
    except OSError:
        ftitle = fsmall = ImageFont.load_default()
    bg = (28, 31, 39)
    panel = (39, 43, 53)
    w, h = 2600, 1610
    board = Image.new("RGB", (w, h), bg)
    d = ImageDraw.Draw(board)
    d.text((50, 30), "T67.71 · LOCAL AUTHOR-REDRAW WIP 1", font=ftitle, fill=(245, 246, 250))
    d.text((52, 75), "Same-sprite vertical continuation across traced cuff/hand pixels; inferred redraw, NOT recovered hidden hair truth.", font=fsmall, fill=(193, 201, 214))
    margin, gap = 50, 22
    cellw = (w - 2 * margin - gap) // 2
    cellh = 680
    rows = [("LEFT ROI", "left"), ("RIGHT ROI", "right")]
    for r, (title, side) in enumerate(rows):
        xbase = margin
        ybase = 130 + r * (cellh + 28)
        d.text((xbase, ybase), title, font=ftitle, fill=(124, 204, 235))
        for col, (im, label) in enumerate(((before, "BEFORE · original sprite"), (after, "AFTER · local continuation WIP"))):
            x = margin + col * (cellw + gap)
            y = ybase + 46
            d.rounded_rectangle((x, y, x + cellw, y + cellh - 50), radius=12, fill=panel, outline=(77, 84, 98), width=2)
            d.text((x + 14, y + 10), label, font=fsmall, fill=(230, 233, 240))
            crop = im.crop(ROIS[side])
            # Show against both light and dark split mattes to reveal alpha fringes.
            mat = Image.new("RGBA", crop.size, (42, 45, 53, 255))
            light = Image.new("RGBA", crop.size, (230, 229, 236, 255))
            xsplit = crop.width // 2
            part = crop.crop((0, 0, xsplit, crop.height))
            light.alpha_composite(part)
            mat.alpha_composite(crop.crop((xsplit, 0, crop.width, crop.height)), (xsplit, 0))
            mat.alpha_composite(light.crop((0, 0, xsplit, crop.height)), (0, 0))
            maxw = cellw - 34
            maxh = cellh - 132
            scale = min(maxw / mat.width, maxh / mat.height)
            sw = max(1, round(mat.width * scale))
            sh = max(1, round(mat.height * scale))
            scaled = mat.resize((sw, sh), Image.Resampling.LANCZOS).convert("RGB")
            px = x + 17 + (maxw - sw) // 2
            py = y + 52 + (maxh - sh) // 2
            board.paste(scaled, (px, py))
            d.line((px + sw // 2, py, px + sw // 2, py + sh), fill=(255, 165, 80), width=2)
    foot_y = h - 78
    d.rounded_rectangle((margin, foot_y, w - margin, h - 25), radius=10, fill=(61, 42, 34), outline=(238, 165, 78), width=2)
    d.text((margin + 18, foot_y + 12), "Local visual gate only. This test does not establish original topology, front/back rigging, or C-engine success.", font=fsmall, fill=(255, 225, 180))
    board.save(BOARD, optimize=True)


if __name__ == "__main__":
    run()
