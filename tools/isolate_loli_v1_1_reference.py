#!/usr/bin/env python3
"""Create a background-transparent review derivative of the selected Loli v1.1.

Background is removed by border-connected near-white topology, not a global white
color key. Enclosed white clothes/highlights remain foreground, but the result is
still one flat image and needs manual edge/alpha review before any layer painting.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "characters/xiaoxun/design/loli_live2d_v1/concept_front_proportion_v1_1.png"
OUT = ROOT / "characters/xiaoxun/design/loli_live2d_v1/authoring_v1_1"
MIN_RGB = 240
MAX_CHROMA = 24


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def composite(img: Image.Image, bg: tuple[int, int, int]) -> Image.Image:
    canvas = Image.new("RGBA", img.size, (*bg, 255))
    canvas.alpha_composite(img)
    return canvas.convert("RGB")


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    source = Image.open(SOURCE).convert("RGB")
    rgb = np.asarray(source)
    h, w = rgb.shape[:2]

    # Near-white candidate mask. Remove only components connected to the image
    # border; isolated near-white islands in hair/shirt/socks remain foreground.
    near = (rgb.min(axis=2) >= MIN_RGB) & ((rgb.max(axis=2) - rgb.min(axis=2)) <= MAX_CHROMA)
    n, labels, stats, _ = cv2.connectedComponentsWithStats(near.astype(np.uint8), connectivity=8)
    edge_labels = np.unique(np.concatenate([labels[0, :], labels[-1, :], labels[:, 0], labels[:, -1]]))
    background = near & np.isin(labels, edge_labels)
    alpha = np.where(background, 0, 255).astype(np.uint8)

    rgba = np.dstack([rgb, alpha])
    output = Image.fromarray(rgba, "RGBA")
    alpha_path = OUT / "reference_v1_1_alpha_edge_connected.png"
    output.save(alpha_path, optimize=True)
    composite(output, (242, 242, 244)).save(OUT / "review_light.jpg", quality=96)
    composite(output, (28, 29, 36)).save(OUT / "review_dark.jpg", quality=96)

    # Count connected near-white islands retained inside the silhouette. This is
    # a safety signal for white fabric, not semantic proof that each is clothing.
    retained = near & ~background
    retained_labels, retained_counts = np.unique(labels[retained], return_counts=True)
    retained_components = sorted(
        [{"label": int(k), "pixels": int(v)} for k, v in zip(retained_labels, retained_counts) if k != 0],
        key=lambda x: x["pixels"], reverse=True,
    )
    ys, xs = np.where(alpha > 0)
    metrics = {
        "status": "flat reference isolation QA derivative; not separated artwork; not PSD; not Cubism",
        "source": SOURCE.relative_to(ROOT).as_posix(),
        "source_sha256": sha256(SOURCE),
        "output": alpha_path.name,
        "output_sha256": sha256(alpha_path),
        "canvas_px": [w, h],
        "method": "remove only near-white pixels in 8-connected components touching any image edge; preserve enclosed near-white components",
        "parameters": {"near_white_min_channel": MIN_RGB, "near_white_max_channel_spread": MAX_CHROMA, "connectivity": 8},
        "foreground_bbox_xyxy": [int(xs.min()), int(ys.min()), int(xs.max() + 1), int(ys.max() + 1)],
        "transparent_pixels": int(np.count_nonzero(alpha == 0)),
        "opaque_pixels": int(np.count_nonzero(alpha == 255)),
        "retained_near_white_component_count": len(retained_components),
        "largest_retained_near_white_components": retained_components[:20],
        "known_limits": [
            "The input illustration is still one flat full-body image; this does not create Live2D parts.",
            "Connected-component isolation is only a background removal aid. Inspect hairline, white garments, shoe edges, and inter-limb gaps before painting or model import.",
            "No hidden/occluded artwork is synthesized; no ArtMesh, PSD/PSB, CMO3, MOC3, Model3 JSON, Cubism Editor or runtime output is present.",
            "The original white-background reference remains immutable and is not replaced by this derivative.",
        ],
    }
    metrics_path = OUT / "isolation_metrics.json"
    metrics_path.write_text(json.dumps(metrics, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    sums = []
    for p in sorted(OUT.iterdir()):
        if p.is_file() and p.name != "SHA256SUMS.txt":
            sums.append(f"{sha256(p)}  {p.name}")
    (OUT / "SHA256SUMS.txt").write_text("\n".join(sums) + "\n", encoding="utf-8")
    print(json.dumps({k: metrics[k] for k in ("status", "canvas_px", "foreground_bbox_xyxy", "transparent_pixels", "retained_near_white_component_count", "output_sha256")}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
