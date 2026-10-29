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
WRIST_SHAFT_TRIM = 0.12  # hide only the cuff-buried end; keep the source proportions natural


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


def prepare_source(path: Path) -> Image.Image:
    image = key_magenta(Image.open(path))
    alpha = image.getchannel("A")
    bbox = alpha.point(lambda p: 255 if p > 20 else 0).getbbox()
    if not bbox:
        raise ValueError(f"no hand pixels after chroma key: {path}")

    # Trim only the excess wrist shaft that will sit inside the cuff, then keep
    # the remaining source silhouette's natural aspect ratio (uniform resize).
    hand = image.crop(bbox)
    trim = round(hand.height * WRIST_SHAFT_TRIM)
    if trim:
        hand = hand.crop((0, 0, hand.width, hand.height - trim))
    hand.thumbnail(TARGET_BOX_2X, Image.Resampling.LANCZOS)

    canvas = Image.new("RGBA", (SIZE[0] * 2, SIZE[1] * 2), (0, 0, 0, 0))
    canvas.alpha_composite(hand, ((canvas.width - hand.width) // 2, MARGIN_TOP_2X))
    # The hand group inherits the forearm's near-half-turn in this pose; the
    # part-space compensation keeps final screen-space fingers up, wrist down.
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
