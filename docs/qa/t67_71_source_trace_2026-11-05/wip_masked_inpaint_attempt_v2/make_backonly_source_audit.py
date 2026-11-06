#!/usr/bin/env python3
"""Build a source-only visual audit of legacy hair-only references for T67.71.

This board compares existing target ROI pixels and existing hair-only assets only.
It does not create a repair layer, transplant pixels, infer hidden geometry, or
modify production files.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[4]
OUT = Path(__file__).resolve().parent
TARGET = ROOT / "characters/xiaoxun/forms/teen/sprites/hair_hood_long@2x.png"
V1 = ROOT / "characters/xiaoxun/design/redraw/hair_only/hair_long_backonly_v1.png"
V2 = ROOT / "characters/xiaoxun/design/redraw/hair_only/hair_long_backonly_v2.png"
V1_RAW = ROOT / "characters/xiaoxun/design/redraw/hair_only/hair_long_backonly_v1_raw.png"
V2_RAW = ROOT / "characters/xiaoxun/design/redraw/hair_only/hair_long_backonly_v2_raw.png"
ROI_LEFT = (51, 849, 396, 1368)
ROI_RIGHT = (736, 849, 1081, 1368)

W, H = 2560, 1510
BG = (24, 27, 34)
PANEL = (37, 41, 50)
TEXT = (238, 240, 245)
MUTED = (180, 188, 200)
ACCENT = (96, 174, 210)
WARNING = (245, 167, 73)


def font(size: int, bold: bool = False):
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
    ]
    for path in candidates:
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def alpha_stats(path: Path):
    im = Image.open(path).convert("RGBA")
    alpha = im.getchannel("A")
    hist = alpha.histogram()
    total = im.width * im.height
    return {
        "size": [im.width, im.height],
        "alpha_zero_pixels": hist[0],
        "alpha_partial_pixels": sum(hist[1:255]),
        "alpha_opaque_pixels": hist[255],
        "alpha_nonzero_fraction": round((total - hist[0]) / total, 6),
        "sha256": digest(path),
    }


def checker(size, cell=24):
    w, h = size
    im = Image.new("RGB", (w, h), (44, 48, 57))
    d = ImageDraw.Draw(im)
    c1, c2 = (55, 60, 70), (43, 47, 56)
    for y in range(0, h, cell):
        for x in range(0, w, cell):
            if ((x // cell) + (y // cell)) % 2:
                d.rectangle((x, y, min(w - 1, x + cell - 1), min(h - 1, y + cell - 1)), fill=c1)
            else:
                d.rectangle((x, y, min(w - 1, x + cell - 1), min(h - 1, y + cell - 1)), fill=c2)
    return im


def contain(im: Image.Image, box, scale_up=True):
    x0, y0, x1, y1 = box
    maxw, maxh = x1 - x0, y1 - y0
    factor = min(maxw / im.width, maxh / im.height)
    if not scale_up:
        factor = min(factor, 1.0)
    size = (max(1, round(im.width * factor)), max(1, round(im.height * factor)))
    return im.resize(size, Image.Resampling.LANCZOS)


def composite_cell(canvas, title, subtitle, im, x, y, w, h, mode="contain"):
    d = ImageDraw.Draw(canvas)
    d.rounded_rectangle((x, y, x + w, y + h), radius=16, fill=PANEL, outline=(70, 78, 91), width=2)
    d.text((x + 22, y + 16), title, font=font(27, True), fill=TEXT)
    d.text((x + 22, y + 53), subtitle, font=font(18), fill=MUTED)
    image_box = (x + 18, y + 88, x + w - 18, y + h - 18)
    bx0, by0, bx1, by1 = image_box
    back = checker((bx1 - bx0, by1 - by0))
    if mode == "crop":
        sized = im.resize((bx1 - bx0, by1 - by0), Image.Resampling.LANCZOS)
    else:
        sized = contain(im, image_box)
    px = bx0 + (bx1 - bx0 - sized.width) // 2
    py = by0 + (by1 - by0 - sized.height) // 2
    if sized.mode == "RGBA":
        back.paste(sized, (px - bx0, py - by0), sized.getchannel("A"))
    else:
        back.paste(sized.convert("RGB"), (px - bx0, py - by0))
    canvas.paste(back, (bx0, by0))
    d.rectangle((bx0, by0, bx1 - 1, by1 - 1), outline=ACCENT if title.startswith("TARGET") else (96, 102, 116), width=2)


def main():
    target = Image.open(TARGET).convert("RGBA")
    left = target.crop(ROI_LEFT)
    right = target.crop(ROI_RIGHT)
    v1 = Image.open(V1).convert("RGBA")
    v2 = Image.open(V2).convert("RGBA")

    canvas = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(canvas)
    d.text((64, 38), "T67.71  |  LEGACY HAIR-ONLY SOURCE AUDIT", font=font(37, True), fill=TEXT)
    d.text((66, 93), "Same target sprite ROI vs. earlier hair-only plates; visual provenance review only — no pixel transfer or hidden-geometry claim.", font=font(21), fill=MUTED)

    margin, gap = 64, 24
    y, ch = 150, 1160
    cw = (W - 2 * margin - 3 * gap) // 4
    cells = [
        ("TARGET · LEFT ROI", "Current production sprite; ROI [51,849,396,1368]", left),
        ("TARGET · RIGHT ROI", "Current production sprite; ROI [736,849,1081,1368]", right),
        ("HAIR-ONLY · V1", "843×1264 processed plate; open center / twin side masses", v1),
        ("HAIR-ONLY · V2", "843×1264 processed plate; broad center back panel", v2),
    ]
    for i, (title, subtitle, image) in enumerate(cells):
        x = margin + i * (cw + gap)
        composite_cell(canvas, title, subtitle, image, x, y, cw, ch, "crop" if i < 2 else "contain")

    strip_y = 1345
    d.rounded_rectangle((margin, strip_y, W - margin, H - 48), radius=14, fill=(62, 42, 34), outline=WARNING, width=2)
    d.text((margin + 24, strip_y + 15), "RESULT: V2 is a useful palette/material reference, but its center-part topology, silhouette, and strand directions do not match the hood-up target.", font=font(22, True), fill=(255, 225, 177))
    d.text((margin + 24, strip_y + 50), "Neither V1 nor V2 establishes hidden hair truth. Do not register, mirror, cut, or transplant these pixels as a repair candidate.", font=font(21), fill=TEXT)

    out_png = OUT / "109_backonly_source_audit.png"
    canvas.save(out_png, optimize=True)
    raw_paths = [V1_RAW, V2_RAW]
    report = {
        "task": "T67.71",
        "status": "source-only visual audit; no repair candidate",
        "target": {"path": str(TARGET.relative_to(ROOT)), **alpha_stats(TARGET)},
        "target_rois_xyxy": {"left": list(ROI_LEFT), "right": list(ROI_RIGHT)},
        "hair_only_v1": {"path": str(V1.relative_to(ROOT)), **alpha_stats(V1)},
        "hair_only_v2": {"path": str(V2.relative_to(ROOT)), **alpha_stats(V2)},
        "raw_source_files": [
            {"path": str(p.relative_to(ROOT)), "size": list(Image.open(p).size), "sha256": digest(p)}
            for p in raw_paths
        ],
        "visual_findings": [
            "hair-only v1 has a center opening and twin descending masses; it does not define the hood-up hidden topology",
            "hair-only v2 has a broad continuous central back panel and is the closer palette/material reference of these two",
            "hair-only v2 still has a different center-part, silhouette, strand directions, and no hood-up registration; it is not hidden-hair truth",
            "no source pixels were transferred; no candidate was created; no production, rig, or generator files were changed",
        ],
        "board": {"path": out_png.name, "size": [W, H], "sha256": digest(out_png)},
        "disclaimer": "The board is not an acceptance result or C-engine validation. It is a source-suitability record only.",
    }
    (OUT / "109_backonly_source_audit_metrics.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
