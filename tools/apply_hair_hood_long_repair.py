#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Reapply the T67.71 hood-up long-hair occlusion repair.

The flat sheet has no hidden hair behind the baked sleeve/hand. The authored
PNG is a new design continuation, not recovered original pixels. It passed a
local visual check (continuous locks, no cuff/hand, no slab) and is registered
to the 1132x1664 production canvas.

Rebuild would otherwise cut the hands back out of the sheet and/or punch
alpha=0 holes. This step copies only the two lower side-lock regions from the
authored repair onto the current sprite, then refreshes the 1x downsample.
Upper hair and other sprites are left untouched. Dimension mismatch aborts
instead of shifting pixels.
"""
from __future__ import annotations

import argparse
import os
import sys

from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AUTHORED = os.path.join(
    ROOT, "characters", "xiaoxun", "design", "redraw",
    "hair_hood_long_occlusion_repair_v1.png",
)
# Lower side locks only. Outer edges sit on transparency so the copy does not
# cut through a hair-to-hair seam on the left/right/bottom.
REGIONS = ((0, 760, 560, 1664), (572, 760, 1132, 1664))
EXPECT = (1132, 1664)


def apply(character: str, form: str, dry_run: bool) -> int:
    if character != "xiaoxun" or form != "teen":
        print("skip hair_hood_long repair: only xiaoxun/teen")
        return 0
    if not os.path.isfile(AUTHORED):
        print("missing authored repair", AUTHORED, file=sys.stderr)
        return 1
    sprite_dir = os.path.join(ROOT, "characters", character, "forms", form, "sprites")
    dest = os.path.join(sprite_dir, "hair_hood_long@2x.png")
    one = os.path.join(sprite_dir, "hair_hood_long.png")
    authored = Image.open(AUTHORED).convert("RGBA")
    if authored.size != EXPECT:
        print("authored size", authored.size, "!=", EXPECT, file=sys.stderr)
        return 1
    if not os.path.isfile(dest):
        print("missing", dest, file=sys.stderr)
        return 1
    current = Image.open(dest).convert("RGBA")
    if current.size != EXPECT:
        print("sprite size", current.size, "!=", EXPECT, "; refuse to shift", file=sys.stderr)
        return 1
    changed = 0
    for box in REGIONS:
        if current.crop(box).tobytes() != authored.crop(box).tobytes():
            changed += 1
            if not dry_run:
                current.paste(authored.crop(box), box)
    if dry_run:
        print(f"hair_hood_long repair dry-run: {changed} region(s) differ")
        return 0
    if changed:
        current.save(dest)
    # 1x is the area-average of the repaired 2x, so the pair cannot drift.
    current.resize((566, 832), Image.Resampling.BOX).save(one)
    print(f"hair_hood_long repair applied: {changed} region(s) updated")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--character", default="xiaoxun")
    ap.add_argument("--form", default="teen")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    return apply(args.character, args.form, args.dry_run)


if __name__ == "__main__":
    raise SystemExit(main())
