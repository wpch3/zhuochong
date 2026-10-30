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
import json
from pathlib import Path

import numpy as np
from PIL import Image

SIZE = (86, 109)
TARGET_BOX_2X = (156, 204)
MARGIN_TOP_2X = 6
WRIST_INSERT_FRAC = 0.035  # short tapered wrist overlap; cuff hides the cut edge
# Calibrated in the live render: local hand groups inherit a near-half-turn, so
# local x/y signs are opposite screen directions. These positions move both wrists
# inward/down into the cuff; do not flip the signs. This only registers the art,
# without translating the wrist bone or changing the shoulder/elbow chain.
SURPRISED_PART_POS = {"l": [1, 650], "r": [358, 650]}
SURPRISED_PART_LAYERS = {"l": 319, "r": 320}


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


def match_skin_palette(image: Image.Image, palette_path: Path) -> Image.Image:
    """Transfer the hand's warm-skin luminance ramp to Xiaoxun's own hand art.

    The concept hand was painted with a much stronger peach/pink base than the
    character. Match its skin pixels to the face's own skin ramp (not another
    hand asset), retaining linework, alpha, and shading shape.
    """
    src = np.asarray(image.convert("RGBA"), dtype=np.float32)
    tgt = np.asarray(Image.open(palette_path).convert("RGBA"), dtype=np.float32)

    def skin_mask(rgba: np.ndarray) -> np.ndarray:
        r, g, b, a = (rgba[:, :, i] for i in range(4))
        return ((a > 24) & (r > 140) & (g > 90) & (b > 70)
                & (r > g + 3) & (g > b + 2))

    sm, tm = skin_mask(src), skin_mask(tgt)
    # seg_head contains the character's face palette. Restrict samples to the
    # center-lower face so hair, ears, and the neck/collar cannot skew it.
    yy, xx = np.indices(tm.shape)
    h, w = tm.shape
    face = ((xx >= w * 0.22) & (xx <= w * 0.78)
            & (yy >= h * 0.38) & (yy <= h * 0.84))
    tm &= face
    if int(sm.sum()) < 100 or int(tm.sum()) < 100:
        raise ValueError(f"skin palette samples too small: {image.size}, {palette_path}")
    weights = np.array((0.2126, 0.7152, 0.0722), dtype=np.float32)
    sy = src[:, :, :3] @ weights
    ty = tgt[:, :, :3] @ weights
    q = np.linspace(0.0, 1.0, 257)
    sq = np.quantile(sy[sm], q)
    tq = np.quantile(ty[tm], q)
    trgb = np.stack([np.quantile(tgt[:, :, c][tm], q) for c in range(3)], axis=1)
    rank = np.interp(sy[sm], sq, q)
    for c in range(3):
        src[:, :, c][sm] = np.interp(rank, q, trgb[:, c])
    return Image.fromarray(np.clip(src, 0, 255).astype(np.uint8), "RGBA")


def prepare_source(path: Path, palette_path: Path) -> Image.Image:
    image = match_skin_palette(key_magenta(Image.open(path)), palette_path)
    alpha = image.getchannel("A")
    bbox = alpha.point(lambda p: 255 if p > 20 else 0).getbbox()
    if not bbox:
        raise ValueError(f"no hand pixels after chroma key: {path}")

    # Find the actual wrist crease (narrowest alpha row in the lower part of the
    # hand), then retain only a short tapered shaft past it for insertion under
    # the cuff. Cropping by a percentage of the full image kept a broad forearm
    # slab, which read as a floating flesh-colored patch beside the sleeve.
    hand = image.crop(bbox)
    alpha = np.asarray(hand.getchannel("A"))
    rows = []
    for y in range(alpha.shape[0]):
        xs = np.flatnonzero(alpha[y] > 20)
        rows.append((int(xs[0]), int(xs[-1])) if xs.size else None)
    valid = [y for y, row in enumerate(rows) if row is not None]
    if not valid:
        raise ValueError(f"no hand silhouette after key: {path}")
    search_start = int(valid[0] + (valid[-1] - valid[0]) * 0.62)
    wrist_y = min((y for y in range(search_start, valid[-1] + 1)
                   if rows[y] is not None),
                  key=lambda y: rows[y][1] - rows[y][0])
    keep_y = min(hand.height, wrist_y + max(2, round(hand.height * WRIST_INSERT_FRAC)))
    hand = hand.crop((0, 0, hand.width, keep_y))
    hand.thumbnail(TARGET_BOX_2X, Image.Resampling.LANCZOS)
    # Slightly gather the splayed fingers and narrow the wrist so it seats inside
    # the ribbed cuff. Keep height and wrist anchor unchanged; this is silhouette
    # shaping of the hand artwork, not an independent screen-space hand offset.
    hand = hand.resize((max(1, round(hand.width * 0.90)), hand.height),
                       Image.Resampling.LANCZOS)

    canvas = Image.new("RGBA", (SIZE[0] * 2, SIZE[1] * 2), (0, 0, 0, 0))
    canvas.alpha_composite(hand, ((canvas.width - hand.width) // 2, MARGIN_TOP_2X))
    # The hand group inherits the forearm's near-half-turn in this pose; the
    # part-space compensation keeps final screen-space fingers up, wrist down.
    return canvas.rotate(180, resample=Image.Resampling.BICUBIC, expand=False)


def register_hand_parts(sprites: Path) -> None:
    """Write the two surprise sprites into hand_parts.json reproducibly."""
    meta_path = sprites / "hand_parts.json"
    arm_path = sprites / "arm_parts.json"
    if not arm_path.exists():
        raise FileNotFoundError(f"arm metadata missing: {arm_path}")
    data = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {
        "schema_version": "2.0", "parts": [], "checks": {}, "poses": {"": ""}}
    arms = json.loads(arm_path.read_text(encoding="utf-8"))
    arm_by_id = {p["id"]: p for p in arms.get("parts", [])}
    parts = data.setdefault("parts", [])
    by_id = {p["id"]: p for p in parts}
    for side in ("l", "r"):
        hand = arm_by_id.get(f"hand_{side}")
        if not hand or "pivot" not in hand:
            raise ValueError(f"hand_{side} pivot missing from {arm_path}")
        pid = f"hand_{side}_surprised"
        part = by_id.get(pid)
        if part is None:
            part = {"id": pid, "file": f"sprites/{pid}.png",
                    "group": f"hand_{side}"}
            parts.append(part)
        part.update({
            "file": f"sprites/{pid}.png",
            "group": f"hand_{side}",
            "layer": SURPRISED_PART_LAYERS[side],
            "pos": list(SURPRISED_PART_POS[side]),
            "size": list(SIZE),
            "pivot": list(hand["pivot"]),
            "wrist_w": 25,
            "note": ("surprised 专用自然微拢手差分；腕根局部配准到弯袖罗纹袖口，"
                     "差分层压在袖口下以遮住腕桩切边")
        })
    data.setdefault("poses", {})["surprised"] = "surprised"
    data.setdefault("checks", {}).setdefault("wrist_w", {}).update(
        {f"hand_{side}_surprised": 25 for side in ("l", "r")})
    meta_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n",
                         encoding="utf-8")
    print(f"{meta_path}: surprised hand registration updated")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", type=Path, default=Path("."))
    ap.add_argument("--form", default="teen")
    args = ap.parse_args()

    root = args.root.resolve()
    design = root / "characters/xiaoxun/design/hands/hand_surprised_raw.png"
    sprites = root / "characters/xiaoxun/forms" / args.form / "sprites"
    palette = sprites / "seg_head@2x.png"
    if not palette.exists():
        raise FileNotFoundError(f"face palette missing: {palette}")
    right = prepare_source(design, palette)
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
    register_hand_parts(sprites)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
