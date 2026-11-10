#!/usr/bin/env python3
"""T67.71 isolated texture-transfer study using hair_long_back_v2 as a pixel donor.

This deliberately tests the donor as texture, not as hidden-geometry truth. It
makes one narrow, curved inferred lock per side; the alpha geometry is separately
specified and is NOT derived from the cuff/hand mask. Outputs remain QA-only.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from PIL import Image, ImageChops, ImageDraw, ImageFilter

BASE = Path(__file__).resolve().parent
ROOT = Path(__file__).resolve().parents[4]
TARGET = ROOT / "characters/xiaoxun/forms/teen/sprites/hair_hood_long@2x.png"
DONOR = ROOT / "characters/xiaoxun/design/redraw/hair_long_back_v2.png"
OBJECTS = BASE / "manual_artifact_silhouette_polygons_v3.json"
PATCH_PATH = BASE / "101_hair_long_back_v2_texture_donor_crop.png"
LAYER_PATH = BASE / "102_texture_transfer_underlay_v1.png"
BOARD_PATH = BASE / "103_texture_transfer_v1_local_review.png"
REPORT_PATH = BASE / "104_texture_transfer_v1_metrics.json"

# Source sprites are 2x. This donor crop contains internal painted hair only,
# avoiding the magenta background and the known green edge specks in a fitted
# @2x variant. The sample includes real strand lines/gradients, not a flat fill.
DONOR_BOX = (260, 430, 480, 800)
S = 4
BOXES = {"left": (51, 849, 396, 1368), "right": (736, 849, 1081, 1368)}
# Curves follow a free-flowing hair direction and intentionally do not trace the
# cuff, palm, or finger silhouette. Widths in source-sprite pixels.
LOCKS = {
    "left": ([(171, 218), (160, 286), (176, 365), (192, 438), (208, 493)], [42, 60, 68, 56, 24]),
    "right": ([(174, 218), (188, 286), (172, 365), (154, 438), (138, 493)], [42, 60, 68, 56, 24]),
}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def cubic(points: list[tuple[float, float]], samples_per_segment: int = 100) -> list[tuple[float, float]]:
    # Catmull-Rom anchors converted to cubic Beziers. This passes through every
    # independently authored point without tracing the visible hand/cuff edge.
    out: list[tuple[float, float]] = []
    for i in range(len(points) - 1):
        p0, p1 = points[i], points[i + 1]
        prev = points[max(0, i - 1)]
        nxt = points[min(len(points) - 1, i + 2)]
        c1 = (p0[0] + (p1[0] - prev[0]) / 6, p0[1] + (p1[1] - prev[1]) / 6)
        c2 = (p1[0] - (nxt[0] - p0[0]) / 6, p1[1] - (nxt[1] - p0[1]) / 6)
        for j in range(samples_per_segment):
            t = j / samples_per_segment
            u = 1 - t
            x = u**3*p0[0] + 3*u*u*t*c1[0] + 3*u*t*t*c2[0] + t**3*p1[0]
            y = u**3*p0[1] + 3*u*u*t*c1[1] + 3*u*t*t*c2[1] + t**3*p1[1]
            out.append((x, y))
    out.append(points[-1])
    return out


def smooth_width(t: float, values: list[float]) -> float:
    stops = [0.0, 0.25, 0.5, 0.75, 1.0]
    for i in range(len(stops) - 1):
        if t <= stops[i + 1]:
            q = (t - stops[i]) / (stops[i + 1] - stops[i])
            q = q * q * (3 - 2 * q)
            return values[i] * (1 - q) + values[i + 1] * q
    return values[-1]


def ribbon_polygon(points: list[tuple[float, float]], widths: list[float]) -> list[tuple[float, float]]:
    left, right = [], []
    for i, (x, y) in enumerate(points):
        a, b = max(0, i - 2), min(len(points) - 1, i + 2)
        dx, dy = points[b][0] - points[a][0], points[b][1] - points[a][1]
        ln = max(math.hypot(dx, dy), 1e-8)
        nx, ny = -dy / ln, dx / ln
        w = smooth_width(i / max(1, len(points) - 1), widths)
        left.append(((x + nx*w/2) * S, (y + ny*w/2) * S))
        right.append(((x - nx*w/2) * S, (y - ny*w/2) * S))
    return left + right[::-1]


def main() -> None:
    target = Image.open(TARGET).convert("RGBA")
    donor = Image.open(DONOR).convert("RGB")
    sample = donor.crop(DONOR_BOX)
    sample.save(PATCH_PATH)

    layer = Image.new("RGBA", target.size, (0, 0, 0, 0))
    counts = {}
    for side, box in BOXES.items():
        x0, y0, x1, y1 = box
        crop_size = (x1 - x0, y1 - y0)
        curve, widths = LOCKS[side]
        points = cubic(curve)
        full = Image.new("RGBA", (crop_size[0] * S, crop_size[1] * S), (0, 0, 0, 0))
        mask = Image.new("L", full.size, 0)
        ImageDraw.Draw(mask).polygon(ribbon_polygon(points, widths), fill=255)
        # Subpixel antialiasing only; the inferred alpha remains an independent
        # flowing lock, not a copy of the visible cuff/hand silhouette.
        mask = mask.filter(ImageFilter.GaussianBlur(0.55 * S))
        donor_scaled = sample.resize((crop_size[0] * S, crop_size[1] * S), Image.Resampling.BICUBIC)
        local = Image.new("RGBA", donor_scaled.size, (0, 0, 0, 0))
        local.paste(donor_scaled, (0, 0))
        local.putalpha(mask)
        local = local.resize(crop_size, Image.Resampling.LANCZOS)
        layer.alpha_composite(local, (x0, y0))
        counts[side] = {
            "backfill_alpha_gt24": sum(v > 24 for v in local.getchannel("A").tobytes()),
            "curve_anchors_local": curve,
            "widths_px": widths,
        }
    layer.save(LAYER_PATH)

    # Diagnostic clear-only foreground derived from the prior manually traced
    # visible cuff+hand contours. It is not reused as the new backfill alpha.
    objects = json.loads(OBJECTS.read_text(encoding="utf-8"))["objects"]
    clean = target.copy()
    S2 = 4
    for side, box in BOXES.items():
        x0, y0, x1, y1 = box
        size = (x1 - x0, y1 - y0)
        m = Image.new("L", (size[0] * S2, size[1] * S2), 0)
        d = ImageDraw.Draw(m)
        for key in ("cuff", "hand"):
            d.polygon([(x*S2, y*S2) for x, y in objects[side][key]], fill=255)
        m = m.resize(size, Image.Resampling.LANCZOS)
        original = target.crop(box)
        alpha = ImageChops.multiply(original.getchannel("A"), ImageChops.invert(m))
        original.putalpha(alpha)
        clean.paste(original, (x0, y0))

    # Review panels: original source / exact donor pixels / donor-derived inferred
    # lock under the cleaned foreground. These are local diagnostic views only.
    tile_w, tile_h, scale = 552, 830, 2
    board = Image.new("RGB", (tile_w * 3 + 64, (tile_h + 54) * 2), (244, 242, 247))
    draw = ImageDraw.Draw(board)
    donor_tile = sample.resize((tile_w, tile_h), Image.Resampling.LANCZOS).convert("RGB")
    for row, (side, box) in enumerate(BOXES.items()):
        src = target.crop(box)
        mat = Image.new("RGBA", src.size, (239, 239, 244, 255)); mat.alpha_composite(src)
        patch = layer.crop(box)
        patch_matte = Image.new("RGBA", patch.size, (239, 239, 244, 255)); patch_matte.alpha_composite(patch)
        composite = Image.new("RGBA", src.size, (239, 239, 244, 255))
        composite.alpha_composite(patch)
        composite.alpha_composite(clean.crop(box))
        views = ((mat.convert("RGB"), f"{side}: source"), (donor_tile, f"{side}: hair_long_back_v2 donor pixels"), (composite.convert("RGB"), f"{side}: donor-textured inferred lock under cleared object"))
        for col, (im, title) in enumerate(views):
            x = 16 + col * (tile_w + 16)
            y = 38 + row * (tile_h + 54)
            board.paste(im.resize((tile_w, tile_h), Image.Resampling.LANCZOS), (x, y))
            draw.text((x + 3, y - 22), title, fill=(32, 26, 42))
    board.save(BOARD_PATH)

    # Detect whether the chosen source patch accidentally contains the magenta
    # key color or lacks image detail; this is provenance, not an art gate.
    donor_px = sample.load()
    magenta_like = sum(
        1
        for y in range(sample.height)
        for x in range(sample.width)
        for r, g, b in (donor_px[x, y],)
        if r > 180 and b > 120 and g < 100
    )
    report = {
        "task": "T67.71",
        "status": "isolated texture-transfer WIP; not accepted, not C-tested, not production",
        "method_change": "literal donor RGB pixels from hair_long_back_v2, rather than a newly painted flat gradient; inferred lock alpha is independent of cuff/hand contours",
        "source_donor": str(DONOR.relative_to(ROOT)),
        "source_donor_sha256": sha256(DONOR),
        "donor_crop_xyxy": DONOR_BOX,
        "donor_crop_size": sample.size,
        "donor_crop_magenta_like_pixels": magenta_like,
        "target": str(TARGET.relative_to(ROOT)),
        "target_sha256": sha256(TARGET),
        "artifact_mask_source": str(OBJECTS.relative_to(ROOT)),
        "alpha_shape_is_not_artifact_mask": True,
        "outputs": [str(PATCH_PATH.relative_to(ROOT)), str(LAYER_PATH.relative_to(ROOT)), str(BOARD_PATH.relative_to(ROOT))],
        "counts": counts,
        "gate": "must pass this exact local review for hair-strand direction, value/palette integration, silhouette, and no cuff/hand contour before any C test; failure means stop this donor-transfer method, not tweak repeatedly",
    }
    REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
