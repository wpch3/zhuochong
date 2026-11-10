#!/usr/bin/env python3
"""T67.71 explicit back-hair redraw WIP, informed by Live2D part-prep guidance.

Creates left/right independent, editable full-canvas plates and a diagnostic
front-clear composite. Shapes are new artistic proposals, not hidden source truth.
No production asset, rig, or generator is touched.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter

ROOT = Path(__file__).resolve().parents[4]
BASE = Path(__file__).resolve().parent
SOURCE = ROOT / "characters/xiaoxun/forms/teen/sprites/hair_hood_long@2x.png"
POLYGONS = BASE / "manual_artifact_silhouette_polygons_v3.json"
BACK_PLATE = BASE / "114_author_backhair_redraw_v1_plate_wip.png"
CLEAN_FRONT = BASE / "115_author_backhair_redraw_v1_clean_front_wip.png"
COMPOSITE = BASE / "116_author_backhair_redraw_v1_local_review.png"
METRICS = BASE / "117_author_backhair_redraw_v1_metrics.json"
ROIS = {"left": (51, 849, 396, 1368), "right": (736, 849, 1081, 1368)}
SCALE = 4
CLEAN_DILATE = 2

# A broad, curved back-hair plate sits behind the animated arm/cuff. Two
# independent centerlines and different widths preserve side asymmetry.
DESIGN = {
    "left": {
        "base": ([(183, 205), (153, 307), (181, 423), (194, 565)], [150, 190, 204, 112]),
        "locks": [
            ([(143, 238), (116, 329), (125, 434), (105, 554)], [34, 46, 34, 0], (194, 188, 211, 150)),
            ([(193, 223), (215, 333), (197, 444), (221, 552)], [29, 39, 30, 0], (207, 199, 220, 150)),
            ([(236, 246), (258, 348), (245, 455), (267, 540)], [22, 32, 21, 0], (163, 165, 193, 110)),
        ],
        "lines": [
            ([(120, 272), (136, 348), (119, 448), (111, 515)], (111, 104, 135, 94), 1.7),
            ([(165, 251), (183, 334), (168, 449), (154, 520)], (243, 237, 246, 135), 2.8),
            ([(210, 260), (222, 354), (216, 453), (233, 520)], (117, 110, 142, 78), 1.5),
            ([(245, 286), (259, 365), (254, 451), (270, 509)], (229, 232, 245, 100), 2.2),
        ],
    },
    "right": {
        "base": ([(176, 205), (205, 309), (205, 423), (177, 565)], [158, 204, 212, 118]),
        "locks": [
            ([(119, 258), (112, 352), (123, 448), (95, 548)], [29, 42, 30, 0], (164, 164, 192, 125)),
            ([(168, 231), (184, 341), (171, 451), (151, 553)], [35, 45, 31, 0], (202, 194, 216, 150)),
            ([(218, 251), (235, 355), (221, 457), (238, 546)], [28, 38, 24, 0], (208, 201, 221, 145)),
        ],
        "lines": [
            ([(104, 291), (123, 370), (113, 456), (98, 516)], (113, 106, 137, 82), 1.5),
            ([(150, 265), (169, 352), (157, 453), (143, 518)], (244, 239, 247, 132), 2.5),
            ([(198, 266), (213, 361), (202, 461), (217, 518)], (115, 108, 140, 78), 1.6),
            ([(236, 290), (251, 373), (246, 461), (258, 510)], (231, 234, 245, 102), 2.1),
        ],
    },
}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def cubic(P, n=160):
    p0, p1, p2, p3 = P
    out = []
    for i in range(n + 1):
        t = i / n
        u = 1 - t
        out.append((u**3*p0[0] + 3*u*u*t*p1[0] + 3*u*t*t*p2[0] + t**3*p3[0],
                    u**3*p0[1] + 3*u*u*t*p1[1] + 3*u*t*t*p2[1] + t**3*p3[1]))
    return out


def width_at(t, widths):
    s = t * (len(widths) - 1)
    i = min(len(widths) - 2, int(s))
    q = s - i
    q = q*q*(3 - 2*q)
    return widths[i] * (1 - q) + widths[i + 1] * q


def ribbon_poly(points, widths):
    left, right = [], []
    for i, (x, y) in enumerate(points):
        a, b = max(0, i - 1), min(len(points) - 1, i + 1)
        dx, dy = points[b][0] - points[a][0], points[b][1] - points[a][1]
        length = max(1e-6, math.hypot(dx, dy))
        nx, ny = -dy / length, dx / length
        width = width_at(i / (len(points) - 1), widths) / 2
        left.append(((x + nx * width) * SCALE, (y + ny * width) * SCALE))
        right.append(((x - nx * width) * SCALE, (y - ny * width) * SCALE))
    return left + right[::-1]


def vertical_color(t, u):
    stops = [(0.0, (204, 196, 218)), (0.28, (187, 181, 207)), (0.62, (173, 173, 200)), (1.0, (177, 182, 207))]
    for i in range(len(stops) - 1):
        if t <= stops[i + 1][0]:
            p = (t - stops[i][0]) / (stops[i + 1][0] - stops[i][0])
            p = p*p*(3 - 2*p)
            base = [stops[i][1][k] * (1-p) + stops[i+1][1][k] * p for k in range(3)]
            break
    else:
        base = list(stops[-1][1])
    # Slight center highlight, restrained edge shadow, no flat vector slab.
    center_light = 6.0 * math.exp(-((u - 0.48) / 0.18) ** 2)
    edge_shade = 4.0 * abs(2*u - 1) ** 1.5
    return tuple(max(0, min(255, round(c + center_light - edge_shade))) for c in base)


def make_plate(side, size):
    w, h = size
    dsize = (w * SCALE, h * SCALE)
    spec = DESIGN[side]
    mask = Image.new("L", dsize, 0)
    draw = ImageDraw.Draw(mask)
    pts = cubic(spec["base"][0])
    draw.polygon(ribbon_poly(pts, spec["base"][1]), fill=255)
    mask = mask.filter(ImageFilter.GaussianBlur(0.8 * SCALE))

    base = Image.new("RGBA", dsize, (0, 0, 0, 0))
    bp = base.load()
    for y in range(dsize[1]):
        t = y / max(1, dsize[1] - 1)
        for x in range(dsize[0]):
            u = x / max(1, dsize[0] - 1)
            bp[x, y] = (*vertical_color(t, u), 255)
    base.putalpha(mask)

    # Soft folds/locks are independent flowing shapes inside the base plate.
    detail = Image.new("RGBA", dsize, (0, 0, 0, 0))
    dd = ImageDraw.Draw(detail)
    for curve, widths, color in spec["locks"]:
        p = cubic(curve)
        m = Image.new("L", dsize, 0)
        ImageDraw.Draw(m).polygon(ribbon_poly(p, widths), fill=255)
        m = m.filter(ImageFilter.GaussianBlur(1.5 * SCALE))
        layer = Image.new("RGBA", dsize, color)
        layer.putalpha(ImageChops.multiply(layer.getchannel("A"), m))
        detail.alpha_composite(layer)
    # Thin linework follows each long lock; low contrast to match the source.
    for curve, color, width in spec["lines"]:
        p = [(round(x * SCALE), round(y * SCALE)) for x, y in cubic(curve, 120)]
        dd.line(p, fill=color, width=max(1, round(width * SCALE)), joint="curve")
        # A small blurred twin softens vector-like edges while preserving the fine line.
    detail.putalpha(ImageChops.multiply(detail.getchannel("A"), mask))
    base.alpha_composite(detail)
    return base.resize((w, h), Image.Resampling.LANCZOS)


def draw_board(source, plate, clean, composite):
    W, H = 2600, 1640
    board = Image.new("RGB", (W, H), (26, 29, 36))
    d = ImageDraw.Draw(board)
    try:
        title = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 30)
        small = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 18)
    except OSError:
        title = small = ImageFont.load_default()
    d.text((48, 26), "T67.71 · AUTHOR REDRAW V1 · BACK-HAIR PLATE + CLEAN FRONT", font=title, fill=(244, 246, 250))
    d.text((50, 68), "A new explicit design proposal guided by adjacent target strands; hidden topology remains unknown.", font=small, fill=(191, 199, 212))
    cols = ["SOURCE ROI", "NEW BACK PLATE", "CLEAN FRONT", "LOCAL COMPOSITE"]
    margin, gap = 42, 16
    cw = (W - 2*margin - 3*gap) // 4
    ch = 720
    for row, side in enumerate(("left", "right")):
        y0 = 120 + row * (ch + 38)
        d.text((margin, y0), side.upper(), font=title, fill=(118, 202, 233))
        ypanel = y0 + 42
        for col, (img, label) in enumerate(((source, cols[0]), (plate, cols[1]), (clean, cols[2]), (composite, cols[3]))):
            x0 = margin + col * (cw + gap)
            d.rounded_rectangle((x0, ypanel, x0+cw, ypanel+ch), radius=12, fill=(39, 43, 53), outline=(73, 81, 95), width=2)
            d.text((x0+12, ypanel+10), label, font=small, fill=(232, 235, 242))
            crop = img.crop(ROIS[side]).convert("RGBA")
            split = crop.width // 2
            back = Image.new("RGBA", crop.size, (39, 42, 50, 255))
            light = Image.new("RGBA", crop.size, (229, 228, 235, 255))
            light.alpha_composite(crop.crop((0,0,split,crop.height)))
            back.alpha_composite(crop.crop((split,0,crop.width,crop.height)), (split,0))
            back.alpha_composite(light.crop((0,0,split,crop.height)), (0,0))
            maxw, maxh = cw - 26, ch - 58
            scale = min(maxw/crop.width, maxh/crop.height)
            sw, sh = round(crop.width*scale), round(crop.height*scale)
            thumb = back.resize((sw,sh), Image.Resampling.LANCZOS).convert("RGB")
            px = x0 + 13 + (maxw-sw)//2
            py = ypanel + 42 + (maxh-sh)//2
            board.paste(thumb, (px,py))
            d.line((px+sw//2, py, px+sw//2, py+sh), fill=(255,165,80), width=2)
    footer = "WIP only. No C test, no acceptance, no claim of recovered original hair. Real front arm/cuff layer must later be tested over the rear plate."
    d.rounded_rectangle((margin, H-58, W-margin, H-20), radius=8, fill=(63,43,34), outline=(235,162,75), width=2)
    d.text((margin+14,H-52),footer,font=small,fill=(255,223,175))
    board.save(COMPOSITE, optimize=True)


def main():
    source = Image.open(SOURCE).convert("RGBA")
    poly_data = json.loads(POLYGONS.read_text(encoding="utf-8"))
    plate_full = Image.new("RGBA", source.size, (0,0,0,0))
    clean_front = source.copy()
    region_metrics = {}
    for side, box in ROIS.items():
        x0,y0,x1,y1 = box
        size=(x1-x0,y1-y0)
        obj=poly_data["objects"][side]
        mask=Image.new("L",size,0)
        md=ImageDraw.Draw(mask)
        for name in ("cuff","hand"):
            md.polygon([tuple(map(float,p)) for p in obj[name]],fill=255)
        if CLEAN_DILATE:
            mask=mask.filter(ImageFilter.MaxFilter(CLEAN_DILATE*2+1))
        crop=clean_front.crop(box)
        alpha=ImageChops.multiply(crop.getchannel("A"),ImageChops.invert(mask))
        crop.putalpha(alpha)
        clean_front.paste(crop,(x0,y0))
        local=make_plate(side,size)
        plate_full.alpha_composite(local,(x0,y0))
        region_metrics[side]={
            "roi_xyxy":list(box),
            "clean_mask_dilated_pixels":sum(v>0 for v in mask.tobytes()),
            "plate_alpha_gt0_pixels":sum(v>0 for v in local.getchannel("A").tobytes()),
            "plate_alpha_gt240_pixels":sum(v>240 for v in local.getchannel("A").tobytes()),
            "mask_sha256":hashlib.sha256(mask.tobytes()).hexdigest(),
        }
    # Local composite order: rear plate first, then cleaned original front hair.
    composite=plate_full.copy()
    composite.alpha_composite(clean_front)
    plate_full.save(BACK_PLATE,optimize=True)
    clean_front.save(CLEAN_FRONT,optimize=True)
    draw_board(source,plate_full,clean_front,composite)
    composite.save(BASE/"118_author_backhair_redraw_v1_composite_wip.png",optimize=True)
    metrics={
        "task":"T67.71",
        "status":"explicit author-redraw WIP; not hidden truth, not locally accepted, not production",
        "reference_basis":[
            "Live2D official illustration-processing guidance: separate bangs/sides/back and add portions hidden in source before modeling.",
            "Clip Studio Official tutorial (MUGENUP commentary): splitting a merged illustration requires drawing background behind parts; hidden back-hair tuft portions are redrawn.",
            "Project target-side visible hair strands and existing alpha only; no pixels from hair_long_backonly_v1/v2 were copied."
        ],
        "source":{"path":str(SOURCE.relative_to(ROOT)),"size":list(source.size),"sha256":sha(SOURCE)},
        "visible_object_mask":{"path":str(POLYGONS.relative_to(ROOT)),"sha256":sha(POLYGONS)},
        "method":"Independent left/right soft back-hair plates with curved tapered locks; clean the visible cuff/hand from a separate front layer, then composite the new rear plate underneath. Design is inferred and explicitly labeled as a redraw.",
        "regions":region_metrics,
        "outputs":{
            BACK_PLATE.name:{"sha256":sha(BACK_PLATE),"size":list(plate_full.size)},
            CLEAN_FRONT.name:{"sha256":sha(CLEAN_FRONT),"size":list(clean_front.size)},
            COMPOSITE.name:{"sha256":sha(COMPOSITE),"size":list(Image.open(COMPOSITE).size)},
            "118_author_backhair_redraw_v1_composite_wip.png":{"sha256":sha(BASE/"118_author_backhair_redraw_v1_composite_wip.png"),"size":list(composite.size)},
        },
        "limitations":[
            "The occluded hair design cannot be recovered from the merged source; this is a new proposal, not source truth.",
            "The mask may clear adjacent legitimate hair and must be visually checked at 100/200/400 percent on light and dark backgrounds.",
            "This composite has not been tested with real foreground arms/cuffs, action extremes, transitions, or ParamHairSway.",
            "The plate must be placed behind actual moving arm/cuff; front side locks remain separate. No rig or production integration has been made.",
        ],
    }
    METRICS.write_text(json.dumps(metrics,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"status":metrics["status"],"method":metrics["method"],"regions":region_metrics,"outputs":metrics["outputs"]},ensure_ascii=False,indent=2))


if __name__=="__main__":
    from PIL import ImageFont
    main()
