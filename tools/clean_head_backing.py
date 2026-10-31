#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Trim detached hair residue from the movable face/neck backing.

The sprite split leaves a few style-specific hair tabs in seg_head. Keep the
connected face/neck backing, preserve a small halo around the measured skin
silhouette, and repair the lower jaw contour from the registered body_full
source. The donor repair is row-wise and limited to a narrow band at the left
and right skin boundaries below the eyes, so it restores broken jaw pixels
without copying eyes, mouth, or neighboring hair back into the face.
"""
from __future__ import annotations

import argparse
import json
import os
from collections import deque

import numpy as np
from PIL import Image, ImageFilter


def largest_component(mask: np.ndarray) -> np.ndarray:
    h, w = mask.shape
    seen = np.zeros_like(mask, dtype=bool)
    best = np.zeros_like(mask, dtype=bool)
    best_n = 0
    for sy, sx in zip(*np.nonzero(mask)):
        if seen[sy, sx]:
            continue
        q = deque([(int(sy), int(sx))])
        seen[sy, sx] = True
        comp = []
        while q:
            y, x = q.popleft()
            comp.append((y, x))
            for dy in (-1, 0, 1):
                for dx in (-1, 0, 1):
                    if not (dy or dx):
                        continue
                    yy, xx = y + dy, x + dx
                    if (0 <= yy < h and 0 <= xx < w and mask[yy, xx]
                            and not seen[yy, xx]):
                        seen[yy, xx] = True
                        q.append((yy, xx))
        if len(comp) > best_n:
            best_n = len(comp)
            best[:] = False
            yy, xx = zip(*comp)
            best[np.asarray(yy), np.asarray(xx)] = True
    return best


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--character", default="xiaoxun")
    ap.add_argument("--form", default="teen")
    ap.add_argument("--root", default=".")
    ap.add_argument("--input", default="")
    ap.add_argument("--output", default="")
    ap.add_argument("--halo", type=int, default=4)
    a = ap.parse_args()

    form = os.path.join(a.root, "characters", a.character, "forms", a.form)
    sprites = os.path.join(form, "sprites")
    src = a.input or os.path.join(sprites, "seg_head.png")
    dst = a.output or src
    bp = json.load(open(os.path.join(sprites, "body_parts.json"), encoding="utf-8"))
    head = next(p for p in bp["parts"] if p["id"] == "seg_head")
    x0, y0 = map(int, head["pos"])
    neck_y = int(bp["cut_lines"]["neck"]) - y0

    rgba = np.asarray(Image.open(src).convert("RGBA")).copy()
    h, w = rgba.shape[:2]
    alpha = rgba[..., 3]

    # Repair only the chin/jaw band from the exact registered source crop.
    full_path = os.path.join(sprites, "body_full.png")
    repaired = 0
    if os.path.exists(full_path):
        full = np.asarray(Image.open(full_path).convert("RGBA"))
        donor = full[y0:y0 + h, x0:x0 + w]
        if donor.shape[:2] == (h, w):
            dr, dg, db = [donor[..., i].astype(np.int16) for i in range(3)]
            donor_skin = ((donor[..., 3] > 16) & (dr - db > 22)
                          & (dr > 150) & (dr - dg > 8))
            face_skin = largest_component(donor_skin)
            near_face = np.asarray(
                Image.fromarray((face_skin * 255).astype(np.uint8), "L")
                .filter(ImageFilter.MaxFilter(5))) > 0
            dark = np.maximum(np.maximum(dr, dg), db) < 170
            contour = face_skin | (near_face & dark)
            # The jaw boundary starts well above the chin's bottom tip. The
            # former 0.81*h cutoff only covered the neck transition, so the
            # broken jaw contour itself was never repaired. Keep this to the
            # lower face and only the outer 10px of each skin edge: copying the
            # whole face row would restore source eyes/mouth over split masks.
            y_start = max(0, int(round(h * 0.72)))
            edge_margin = 10
            y_stop = min(h, neck_y - 3)
            for y in range(y_start, y_stop):
                xs = np.flatnonzero(face_skin[y])
                if len(xs) < 12:
                    continue
                left = max(0, int(xs.min()) - 5)
                right = min(w, int(xs.max()) + 6)
                row_x = np.arange(left, right)
                edge_band = ((row_x <= int(xs.min()) + edge_margin)
                             | (row_x >= int(xs.max()) - edge_margin))
                dst_row = rgba[y, left:right]
                src_row = donor[y, left:right]
                use = (contour[y, left:right] & edge_band
                       & (src_row[:, 3] > 16))
                changed = use & np.any(dst_row != src_row, axis=1)
                dst_row[use] = src_row[use]
                repaired += int(changed.sum())

    rgb = rgba[..., :3].astype(np.int16)
    alpha = rgba[..., 3]
    r, g, b = rgb.transpose(2, 0, 1)
    # Warm skin gate; lavender hair is outside the measured R-B threshold.
    skin = ((alpha > 16) & (r - b > 22) & (r > 150) & (r - g > 8))
    if int(skin.sum()) < 1000:
        raise SystemExit("[head-clean] not enough skin seed pixels; refuse destructive edit")

    row_ids, lefts, rights = [], [], []
    for y in range(h):
        xs = np.flatnonzero(skin[y])
        if len(xs) >= 16:
            row_ids.append(y)
            lefts.append(int(xs.min()))
            rights.append(int(xs.max()))
    if len(row_ids) < 10:
        raise SystemExit("[head-clean] too few face rows; refuse destructive edit")
    rows = np.arange(h)
    left = np.interp(rows, row_ids, lefts) - a.halo
    right = np.interp(rows, row_ids, rights) + a.halo
    xgrid = np.arange(w)[None, :]
    face_band = (xgrid >= left[:, None]) & (xgrid <= right[:, None])

    skin_img = Image.fromarray((skin * 255).astype(np.uint8), "L")
    face_halo = np.asarray(skin_img.filter(ImageFilter.MaxFilter(a.halo * 2 + 1))) > 0
    component = largest_component(alpha > 16)
    yy = np.arange(h)[:, None]
    neck_keep = yy >= max(0, neck_y - 5)
    keep = component & (face_band | face_halo | neck_keep)

    remove = (alpha > 0) & ~keep
    rgba[..., 3][remove] = 0
    rgba[..., :3][rgba[..., 3] == 0] = 0
    os.makedirs(os.path.dirname(os.path.abspath(dst)), exist_ok=True)
    Image.fromarray(rgba, "RGBA").save(dst)
    print("[head-clean] jaw source contour repairs=%d; opaque %d -> %d; removed %d px; halo=%d; neck_y=%d"
          % (repaired, int((alpha > 16).sum()), int((rgba[..., 3] > 16).sum()),
             int(remove.sum()), a.halo, neck_y))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
