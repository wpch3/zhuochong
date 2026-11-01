#!/usr/bin/env python3
"""Regression test for bounded-memory seam compositing without canvas/roll drift."""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from fill_seam_holes import _canvas_alpha, _canvas_rgba, _norm, _place  # noqa: E402


def legacy_canvas(base: Path, part: dict, width: int, height: int) -> np.ndarray:
    """Reference the former full-canvas paste path, including its sway roll semantics."""
    image = Image.open(base / part["file"]).convert("RGBA")
    sx, sy = _norm(part.get("scale"), 1.0)
    if (sx, sy) != (1.0, 1.0):
        image = image.resize((max(1, int(image.width * sx)),
                              max(1, int(image.height * sy))), Image.LANCZOS)
    ax, ay = _norm(part.get("anchor"), 0.0)
    ox = int(round(part["pos"][0] - ax * image.width))
    oy = int(round(part["pos"][1] - ay * image.height))
    canvas = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    canvas.paste(image, (ox, oy))
    return np.asarray(canvas)


def main() -> int:
    width, height = 17, 13
    yy, xx = np.mgrid[:9, :11]
    alpha = np.array([0, 32, 127, 128, 191, 255], dtype=np.uint8)[(xx + yy) % 6]
    rgb = np.stack(((xx * 19) % 256, (yy * 27) % 256,
                    ((xx + 3 * yy) * 13) % 256), axis=-1).astype(np.uint8)
    sprite = np.dstack((rgb, alpha))
    cases = [
        {"file": "part_a.png", "pos": [4, 2], "anchor": [0.0, 0.0]},
        {"file": "part_b.png", "pos": [-2, -1], "anchor": [0.5, 0.5],
         "scale": [1.5, 1.2]},
        {"file": "part_c.png", "pos": [16, 12], "anchor": [1.0, 1.0]},
    ]
    with tempfile.TemporaryDirectory(prefix="zc-fill-seam-") as td:
        base = Path(td)
        for part in cases:
            Image.fromarray(sprite, "RGBA").save(base / part["file"])
        for part in cases:
            cached = _place(str(base), part, width, height)
            rgba, (ox, oy, sw, sh) = cached
            reference = legacy_canvas(base, part, width, height)
            assert rgba.shape[:2] == (sh, sw)
            assert rgba.shape[:2] != (height, width), "cache regressed to full-canvas storage"
            assert np.array_equal(_canvas_rgba(cached, width, height), reference)
            assert np.array_equal(_canvas_alpha(cached, width, height), reference[..., 3] > 127)
            for dx in (-3, 3):
                rolled = np.roll(reference, dx, axis=1)
                assert np.array_equal(_canvas_rgba(cached, width, height, dx), rolled)
                assert np.array_equal(_canvas_alpha(cached, width, height, dx),
                                      rolled[..., 3] > 127)
    print("fill_seam_holes: cropped-cache RGBA/alpha/±sway matches legacy for 3 clipped/scaled fixtures")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
