#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Build teen Xiaoxun's surprised-hand sprite pair from its keyed art source.

The art source is a single hand facing the viewer, fingers gently gathered and
curled. The opposite hand is mirrored so its tucked thumb points toward the
character's center. Both resolutions are produced from one high-resolution
alpha image to keep the 1x/@2x silhouettes exactly aligned.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
from PIL import Image

SIZE = (86, 109)
TARGET_BOX_2X = (156, 204)
MARGIN_TOP_2X = 6
HORIZONTAL_SHAPE_FACTOR = 1.28


def key_magenta(image: Image.Image) -> Image.Image:
    """Remove the flat magenta key while retaining antialiased line edges."""
    rgb = np.asarray(image.convert("RGB"), dtype=np.float32)
    r, g, b = rgb[:, :, 0], rgb[:, :, 1], rgb[:, :, 2]
    magenta = np.clip((np.minimum(r, b) - g) / 180.0, 0.0, 1.0)
    alpha = np.clip(1.0 - magenta * 1.35, 0.0, 1.0)

    # Despill magenta from partially transparent edge pixels.
    edge = (alpha > 0.02) & (alpha < 0.98)
    green = g.copy()
    green[edge] = np.maximum(green[edge], (r[edge] + b[edge]) * 0.46)
    rgba = np.dstack((r, green, b, alpha * 255.0)).clip(0, 255).astype(np.uint8)
    return Image.fromarray(rgba, "RGBA")


def gather_fingers(image: Image.Image) -> Image.Image:
    """Gently bring the raised fingers toward one another above the palm.

    The source illustration is a five-fingered hand, but generative art tends to
    over-spread the upper fingers. A smooth row-wise remap narrows only the
    finger fan (0.68x at the tips, back to 1.0x across the palm), preserving the
    hand's painted contours instead of redrawing them as geometric shapes.
    """
    rgba = np.asarray(image, dtype=np.float32)
    h, w = rgba.shape[:2]
    x = np.arange(w, dtype=np.float32)
    center = (w - 1) * 0.5
    out = np.zeros_like(rgba)
    for y in range(h):
        t = np.clip((y / max(1, h - 1) - 0.38) / 0.17, 0.0, 1.0)
        t = t * t * (3.0 - 2.0 * t)
        factor = 0.68 + 0.32 * t
        source_x = center + (x - center) / factor
        x0 = np.floor(source_x).astype(np.int32)
        frac = (source_x - x0)[:, None]
        valid = (x0 >= 0) & (x0 + 1 < w)
        x0 = np.clip(x0, 0, w - 2)
        row = rgba[y]
        out[y, valid] = row[x0[valid]] * (1.0 - frac[valid]) + row[x0[valid] + 1] * frac[valid]
    return Image.fromarray(np.clip(out, 0, 255).astype(np.uint8), "RGBA")


def prepare_source(path: Path) -> Image.Image:
    image = gather_fingers(key_magenta(Image.open(path)))
    alpha = image.getchannel("A")
    bbox = alpha.point(lambda p: 255 if p > 20 else 0).getbbox()
    if not bbox:
        raise ValueError(f"no hand pixels after chroma key: {path}")

    hand = image.crop(bbox)
    # The generated pose is intentionally a little slimmer than the raw crop;
    # normalize width only, preserving finger and palm length.
    hand = hand.resize((round(hand.width * HORIZONTAL_SHAPE_FACTOR), hand.height),
                       Image.Resampling.LANCZOS)
    hand.thumbnail(TARGET_BOX_2X, Image.Resampling.LANCZOS)

    canvas = Image.new("RGBA", (SIZE[0] * 2, SIZE[1] * 2), (0, 0, 0, 0))
    canvas.alpha_composite(hand, ((canvas.width - hand.width) // 2, MARGIN_TOP_2X))
    # Part-space faces the same way as the existing surprise hand slot; the
    # hand group performs the authored wrist rotation at runtime.
    return canvas.rotate(180, resample=Image.Resampling.BICUBIC, expand=False)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", type=Path, default=Path("."))
    ap.add_argument("--form", default="teen")
    args = ap.parse_args()

    root = args.root.resolve()
    design = root / "characters/xiaoxun/design/hands/hand_surprised_raw.png"
    sprites = root / "characters/xiaoxun/forms" / args.form / "sprites"
    right = prepare_source(design)
    left = right.transpose(Image.Transpose.FLIP_LEFT_RIGHT)

    for side, artwork in (("l", left), ("r", right)):
        one = artwork.resize(SIZE, Image.Resampling.LANCZOS)
        one_path = sprites / f"hand_{side}_surprised.png"
        two_path = sprites / f"hand_{side}_surprised@2x.png"
        one.save(one_path)
        artwork.save(two_path)
        # Guard exact 2x alignment and reject chroma residue in transparent pixels.
        if artwork.size != (one.width * 2, one.height * 2):
            raise AssertionError(f"1x/@2x size mismatch: {side}")
        rgba = np.asarray(artwork)
        if np.any(rgba[rgba[:, :, 3] == 0, :3] != 0):
            raise AssertionError(f"transparent pixels must be clean RGB zero: {side}")
        print(f"{one_path}: {one.size}; {two_path}: {artwork.size}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
