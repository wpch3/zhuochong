#!/usr/bin/env python3
"""Check the first Loli v1.1 edge-connected background isolation derivative."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "characters/xiaoxun/design/loli_live2d_v1/concept_front_proportion_v1_1.png"
OUT = ROOT / "characters/xiaoxun/design/loli_live2d_v1/authoring_v1_1"
PNG = OUT / "reference_v1_1_alpha_edge_connected.png"
METRICS = OUT / "isolation_metrics.json"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    m = json.loads(METRICS.read_text(encoding="utf-8"))
    src = Image.open(SRC).convert("RGB")
    out = Image.open(PNG).convert("RGBA")
    if src.size != (1280, 1920) or out.size != src.size:
        raise SystemExit("FAIL: source/output dimensions are not 1280x1920")
    if m.get("source_sha256") != digest(SRC) or m.get("output_sha256") != digest(PNG):
        raise SystemExit("FAIL: manifest hash mismatch")
    arr = np.asarray(out)
    alpha = arr[..., 3]
    expected_bbox = tuple(m.get("foreground_bbox_xyxy", []))
    ys, xs = np.where(alpha > 0)
    bbox = (int(xs.min()), int(ys.min()), int(xs.max()+1), int(ys.max()+1))
    if bbox != expected_bbox:
        raise SystemExit(f"FAIL: alpha bounds mismatch: {bbox} vs {expected_bbox}")
    if alpha[0, 0] != 0 or alpha[-1, -1] != 0 or alpha[0, -1] != 0 or alpha[-1, 0] != 0:
        raise SystemExit("FAIL: an outer canvas corner is not transparent")
    transparent = int(np.count_nonzero(alpha == 0))
    if transparent != m.get("transparent_pixels"):
        raise SystemExit("FAIL: transparent pixel count mismatch")
    # Fixed samples are known white/near-white shirt/jacket pixels in this immutable source.
    for xy in ((520, 800), (475, 900), (700, 800)):
        x, y = xy
        if min(src.getpixel((x, y))) < 240 or int(alpha[y, x]) != 255:
            raise SystemExit(f"FAIL: enclosed white fabric was lost at {xy}")
    if int(alpha[800, 600]) != 255:
        raise SystemExit("FAIL: cream shirt sample was lost at (600, 800)")
    src_arr = np.asarray(src)
    opaque = alpha == 255
    if not np.array_equal(arr[..., :3][opaque], src_arr[opaque]):
        raise SystemExit("FAIL: opaque source pixels were altered")
    if "not separated artwork" not in m.get("status", ""):
        raise SystemExit("FAIL: derivative limitations missing from manifest")
    print(f"PASS: transparent exterior={transparent}px; bounds={bbox}; sampled white fabric retained; RGB source identity preserved")
    print("LIMIT: single flat RGBA reference only; this is not part separation or Cubism validation")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
