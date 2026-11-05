#!/usr/bin/env python3
"""Create a registered, blank OpenRaster handoff template for T67.71.

The template contains the current sprite only as a reference, three empty art
layers, and ROI guide outlines. It creates no hair pixels and is not a repair.
"""
from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET
from PIL import Image, ImageDraw, ImageFont

BASE = Path(__file__).resolve().parent
ROOT = Path(__file__).resolve().parents[4]
TARGET = ROOT / "characters/xiaoxun/forms/teen/sprites/hair_hood_long@2x.png"
ORA = BASE / "107_T67_71_registered_artist_template.ora"
PREVIEW = BASE / "107_artist_template_preview.png"
METRICS = BASE / "108_artist_template_metrics.json"
BOXES = {"LEFT": (51, 849, 396, 1368), "RIGHT": (736, 849, 1081, 1368)}
COLORS = {"LEFT": (25, 142, 205, 255), "RIGHT": (237, 123, 49, 255)}
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def make_checker(size: tuple[int, int], cell: int = 28) -> Image.Image:
    w, h = size
    out = Image.new("RGB", size, (238, 238, 242))
    d = ImageDraw.Draw(out)
    for y in range(0, h, cell):
        for x in range(0, w, cell):
            if (x // cell + y // cell) % 2:
                d.rectangle((x, y, x + cell - 1, y + cell - 1), fill=(211, 213, 220))
    return out


def main() -> None:
    ref = Image.open(TARGET).convert("RGBA")
    width, height = ref.size
    if (width, height) != (1132, 1664):
        raise SystemExit(f"unexpected current target canvas: {ref.size}")

    blank = Image.new("RGBA", ref.size, (0, 0, 0, 0))
    guide = Image.new("RGBA", ref.size, (0, 0, 0, 0))
    gd = ImageDraw.Draw(guide)
    fnt = ImageFont.truetype(FONT, 17)
    for side, (x0, y0, x1, y1) in BOXES.items():
        gd.rectangle((x0, y0, x1 - 1, y1 - 1), outline=COLORS[side], width=5)
        label = f"{side} ROI - bounds only"
        tx = x0 + 6
        ty = max(3, y0 - 29)
        gd.rounded_rectangle((tx - 3, ty - 2, tx + gd.textbbox((0, 0), label, font=fnt)[2] + 5, ty + 23), radius=4, fill=(255, 255, 255, 224))
        gd.text((tx, ty), label, font=fnt, fill=COLORS[side])

    # ORA has a top-first stack. Blank draft layers remain transparent; reference
    # remains visible so an artist can work in registration without exporting it.
    layer_rows = [
        ("DRAFT - Clean hair plate (EMPTY; author art only)", blank, "data/0000.png", "visible"),
        ("DRAFT - Back-hair continuation LEFT (EMPTY)", blank, "data/0001.png", "visible"),
        ("DRAFT - Back-hair continuation RIGHT (EMPTY)", blank, "data/0002.png", "visible"),
        ("GUIDE - ROI outlines only; NOT segmentation or hair geometry", guide, "data/0003.png", "visible"),
        ("REFERENCE ONLY - current production sprite; do not export", ref, "data/0004.png", "visible"),
    ]
    root = ET.Element("image", {"version": "0.0.3", "w": str(width), "h": str(height), "name": "T67.71 - blank artist source template; not a repair"})
    stack = ET.SubElement(root, "stack", {"name": "root", "opacity": "1.0", "visibility": "visible", "composite-op": "svg:src-over"})
    for name, _img, src, visibility in layer_rows:
        ET.SubElement(stack, "layer", {"name": name, "src": src, "x": "0", "y": "0", "opacity": "1.0", "visibility": visibility, "composite-op": "svg:src-over"})
    stack_xml = ET.tostring(root, encoding="utf-8", xml_declaration=True)

    merged = ref.copy()
    merged.alpha_composite(guide)
    thumb = merged.copy()
    thumb.thumbnail((256, 256), Image.Resampling.LANCZOS)

    with zipfile.ZipFile(ORA, "w") as zf:
        info = zipfile.ZipInfo("mimetype")
        info.compress_type = zipfile.ZIP_STORED
        zf.writestr(info, b"image/openraster")
        zf.writestr("stack.xml", stack_xml, compress_type=zipfile.ZIP_DEFLATED)
        for _name, img, src, _visibility in layer_rows:
            from io import BytesIO
            buf = BytesIO()
            img.save(buf, format="PNG", optimize=True)
            zf.writestr(src, buf.getvalue(), compress_type=zipfile.ZIP_DEFLATED)
        from io import BytesIO
        buf = BytesIO()
        merged.save(buf, format="PNG", optimize=True)
        zf.writestr("mergedimage.png", buf.getvalue(), compress_type=zipfile.ZIP_DEFLATED)
        buf = BytesIO()
        thumb.save(buf, format="PNG", optimize=True)
        zf.writestr("Thumbnails/thumbnail.png", buf.getvalue(), compress_type=zipfile.ZIP_DEFLATED)

    # User-facing preview on checkerboard, with no added hair pixels.
    checker = make_checker((width, height))
    preview_rgba = checker.convert("RGBA")
    preview_rgba.alpha_composite(merged)
    preview = Image.new("RGB", (width + 96, height + 112), (246, 246, 249))
    pd = ImageDraw.Draw(preview)
    pd.text((28, 18), "BLANK AUTHOR TEMPLATE - current sprite reference + ROI guides only", font=ImageFont.truetype(FONT, 20), fill=(34, 39, 51))
    preview.paste(preview_rgba.convert("RGB"), (48, 72))
    preview.save(PREVIEW, optimize=True)

    # Structural verification of OpenRaster metadata, blank draft layers, and
    # reference pixel identity; this is not an application-open test.
    with zipfile.ZipFile(ORA, "r") as zf:
        names = zf.namelist()
        if names[0] != "mimetype" or zf.read("mimetype") != b"image/openraster":
            raise SystemExit("ORA mimetype/order invalid")
        parsed = ET.fromstring(zf.read("stack.xml"))
        if parsed.attrib.get("w") != str(width) or parsed.attrib.get("h") != str(height):
            raise SystemExit("ORA dimensions mismatch")
        layers = parsed.find("stack").findall("layer")
        if len(layers) != 5:
            raise SystemExit(f"expected five layers, got {len(layers)}")
        expected = [row[0] for row in layer_rows]
        if [layer.attrib["name"] for layer in layers] != expected:
            raise SystemExit("ORA layer order/name mismatch")
        for src in ("data/0000.png", "data/0001.png", "data/0002.png"):
            with Image.open(zf.open(src)) as im:
                if im.size != ref.size or im.getbbox() is not None:
                    raise SystemExit(f"draft layer is not blank/registered: {src}")
        with Image.open(zf.open("data/0004.png")) as im:
            if im.convert("RGBA").tobytes() != ref.tobytes():
                raise SystemExit("reference layer pixel mismatch")
        with Image.open(zf.open("mergedimage.png")) as im:
            if im.convert("RGBA").tobytes() != merged.tobytes():
                raise SystemExit("merged image differs from reference + guide")

    report = {
        "task": "T67.71",
        "status": "blank registered source template; no hair reconstruction",
        "application_open_test": "not run (Krita not installed in this environment)",
        "ora_structural_validation": "passed: mimetype/order, canvas dimensions, 5 named layers, 3 empty full-canvas draft layers, reference pixel identity, merged-image identity",
        "production_changes": False,
        "canvas_px": [width, height],
        "target_source": str(TARGET.relative_to(ROOT)),
        "target_sha256": sha256_file(TARGET),
        "roi_xyxy_half_open": BOXES,
        "draft_layer_names": [layer_rows[0][0], layer_rows[1][0], layer_rows[2][0]],
        "guide_semantics": "thin ROI outlines only; not object mask, segmentation, hair alpha, or hidden strand shape",
        "ora": {"path": str(ORA.relative_to(ROOT)), "sha256": sha256_file(ORA), "bytes": ORA.stat().st_size},
        "preview": {"path": str(PREVIEW.relative_to(ROOT)), "sha256": sha256_file(PREVIEW), "dimensions": list(preview.size)},
    }
    METRICS.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"ora": report["ora"], "preview": report["preview"], "status": report["status"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
