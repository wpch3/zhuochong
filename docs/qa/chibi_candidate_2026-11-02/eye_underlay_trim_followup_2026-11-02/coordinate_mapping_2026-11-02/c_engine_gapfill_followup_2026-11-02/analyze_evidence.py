#!/usr/bin/env python3
"""Recompute the C-frame -> Chibi seg_head texel evidence in this folder.

Run from the repository root with Python that has Pillow and NumPy. The script
reads only archived screenshots, runtime/socket state, archived candidate
textures, and archived Chibi donor/mapping files; it does not edit production.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
ROOT = next(p for p in HERE.parents if (p / "tools" / "make_eyeline_parts.py").exists())
sys.path.insert(0, str(ROOT))
from tools.make_eyeline_parts import clean_skin  # noqa: E402


def py(value):
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.floating):
        return float(value)
    if isinstance(value, dict):
        return {str(k): py(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [py(v) for v in value]
    return value


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def hist(alpha: np.ndarray) -> dict[str, int]:
    values, counts = np.unique(alpha, return_counts=True)
    return {str(int(k)): int(v) for k, v in zip(values, counts)}


def luma(rgba: np.ndarray) -> np.ndarray:
    return 0.299 * rgba[..., 0] + 0.587 * rgba[..., 1] + 0.114 * rgba[..., 2]


with open(HERE / "baseline_runtime_state.json", encoding="utf-8") as f:
    state = json.load(f)
socket_rows = [s for s in state["sockets"]["sockets"] if s["group"] == "head"]
P = np.asarray([s["pos"] for s in socket_rows], dtype=float)
Q = np.asarray([s["screen"] for s in socket_rows], dtype=float)
D = np.c_[P, np.ones(len(P))]
coef_x = np.linalg.lstsq(D, Q[:, 0], rcond=None)[0]
coef_y = np.linalg.lstsq(D, Q[:, 1], rcond=None)[0]
M = np.asarray([
    [coef_x[0], coef_x[1], coef_x[2]],
    [coef_y[0], coef_y[1], coef_y[2]],
    [0.0, 0.0, 1.0],
])
Mi = np.linalg.inv(M)
residual = np.c_[D @ coef_x, D @ coef_y] - Q

with open(HERE / "seg_head_rig_entry.json", encoding="utf-8") as f:
    head_part = json.load(f)
part_pos = np.asarray(head_part["pos"], dtype=float)
with open(HERE / "source_eye_parts.json", encoding="utf-8") as f:
    eye_parts = json.load(f)["eyes"]
with open(HERE / "source_eye_closed_parts.json", encoding="utf-8") as f:
    closed_parts = json.load(f)["eyes"]

def by_side(rows, side):
    return next(x for x in rows if x["side"] == side)

base_full = np.asarray(Image.open(HERE / "baseline_full.png").convert("RGBA"))
cand_full = np.asarray(Image.open(HERE / "candidate_full.png").convert("RGBA"))
base_head = np.asarray(Image.open(HERE / "baseline_seg_head_isolation.png").convert("RGBA"))
cand_head = np.asarray(Image.open(HERE / "candidate_seg_head_isolation.png").convert("RGBA"))
base_1x = np.asarray(Image.open(HERE / "baseline_seg_head_unmodified.png").convert("RGBA"))
cand_1x = np.asarray(Image.open(HERE / "candidate_seg_head_wip.png").convert("RGBA"))
base_2x = np.asarray(Image.open(HERE / "baseline_seg_head_unmodified@2x.png").convert("RGBA"))
cand_2x = np.asarray(Image.open(HERE / "candidate_seg_head_wip@2x.png").convert("RGBA"))

# Boxes are C-frame pixel windows, half-open. Thresholds identify observed
# dark/gray pixels only; they are not a proposed source edit mask.
observed = [
    ("left_dark_short_dash", "l", (289, 536, 299, 537), 60),
    ("left_gray_mark_unconfirmed", "l", (292, 518, 302, 522), 200),
    ("right_upper_outer_dash", "r", (555, 518, 570, 520), 90),
    ("right_lower_short_edge", "r", (553, 533, 557, 535), 90),
]
features = []
for name, side, (x0, y0, x1, y1), threshold in observed:
    crop = base_full[y0:y1, x0:x1]
    selected = luma(crop) < threshold
    sy, sx = np.where(selected)
    screen_centers = np.c_[sx + x0 + 0.5, sy + y0 + 0.5, np.ones(len(sx))]
    group_xy = (screen_centers @ Mi.T)[:, :2]
    tex_xy = group_xy - part_pos
    group_min, group_max = group_xy.min(0), group_xy.max(0)
    tmin, tmax = tex_xy.min(0), tex_xy.max(0)
    tx0, ty0 = np.floor(tmin).astype(int)
    tx1, ty1 = np.floor(tmax).astype(int) + 1
    tx1, ty1 = max(tx1, tx0 + 1), max(ty1, ty0 + 1)
    eye = by_side(eye_parts, side)
    closed = by_side(closed_parts, side)
    patch_xy = tex_xy - np.asarray(eye["patch_pos"], dtype=float)
    donor_xy = tex_xy - np.asarray(closed["pos"], dtype=float)
    dx0, dy0 = np.floor(donor_xy.min(0)).astype(int)
    dx1, dy1 = np.floor(donor_xy.max(0)).astype(int) + 1
    donor_raw = np.asarray(Image.open(HERE / f"donor_eye_{side}_closed.png").convert("RGBA"))
    donor_clean, _ = clean_skin(donor_raw)
    donor_clean = donor_clean.astype(np.uint8)
    donor_roi = donor_clean[dy0:dy1, dx0:dx1]
    hx0, hy0, hx1, hy1 = 2 * tx0, 2 * ty0, 2 * tx1, 2 * ty1
    screen_diff = np.any(base_full[y0:y1, x0:x1] != cand_full[y0:y1, x0:x1], axis=2)
    head_diff = np.any(base_head[y0:y1, x0:x1] != cand_head[y0:y1, x0:x1], axis=2)
    features.append({
        "id": name,
        "side": side,
        "screen_roi_xyxy_exclusive": [x0, y0, x1, y1],
        "luma_selection_threshold_strict_lt": threshold,
        "selected_screen_pixels": int(selected.sum()),
        "group_local_continuous_span_xy": {"min": group_min.tolist(), "max": group_max.tolist()},
        "seg_head_texture_continuous_span_xy": {"min": tex_xy.min(0).tolist(), "max": tex_xy.max(0).tolist()},
        "seg_head_texture_roi_xyxy_exclusive": [tx0, ty0, tx1, ty1],
        "seg_head_2x_texture_roi_xyxy_exclusive": [hx0, hy0, hx1, hy1],
        "eye_patch_position": eye["patch_pos"],
        "eye_patch_local_continuous_span_xy": {"min": patch_xy.min(0).tolist(), "max": patch_xy.max(0).tolist()},
        "closed_eye_donor_position": closed["pos"],
        "closed_eye_donor_local_continuous_span_xy": {"min": donor_xy.min(0).tolist(), "max": donor_xy.max(0).tolist()},
        "clean_donor_roi_xyxy_exclusive": [dx0, dy0, dx1, dy1],
        "clean_donor_alpha_gt0": int((donor_roi[..., 3] > 0).sum()),
        "baseline_1x_alpha_histogram": hist(base_1x[ty0:ty1, tx0:tx1, 3]),
        "candidate_1x_alpha_histogram": hist(cand_1x[ty0:ty1, tx0:tx1, 3]),
        "baseline_2x_alpha_histogram": hist(base_2x[hy0:hy1, hx0:hx1, 3]),
        "candidate_2x_alpha_histogram": hist(cand_2x[hy0:hy1, hx0:hx1, 3]),
        "1x_pixels_changed_in_mapped_roi": int(np.any(base_1x[ty0:ty1, tx0:tx1] != cand_1x[ty0:ty1, tx0:tx1], axis=2).sum()),
        "2x_pixels_changed_in_mapped_roi": int(np.any(base_2x[hy0:hy1, hx0:hx1] != cand_2x[hy0:hy1, hx0:hx1], axis=2).sum()),
        "C_full_changed_pixels_in_screen_roi": int(screen_diff.sum()),
        "C_seg_head_changed_pixels_in_screen_roi": int(head_diff.sum()),
        "dark_pixel_count_before": int((luma(base_full[y0:y1, x0:x1]) < threshold).sum()),
        "dark_pixel_count_after": int((luma(cand_full[y0:y1, x0:x1]) < threshold).sum()),
    })

# Exact changed-pixel bounds used by the isolated WIP, separate from the
# screen ROIs (which include bilinear sampling contributions).
patches = [
    ("left_dark_short_dash", "l", (145, 156, 470, 472)),
    ("right_upper_outer_dash", "r", (411, 426, 447, 449)),
    ("right_lower_short_edge", "r", (409, 413, 462, 464)),
]
patch_results = []
for name, side, (x0, x1, y0, y1) in patches:
    closed = by_side(closed_parts, side)
    donor_roi_box = [x0 - closed["pos"][0], y0 - closed["pos"][1], x1 - closed["pos"][0], y1 - closed["pos"][1]]
    donor_raw = np.asarray(Image.open(HERE / f"donor_eye_{side}_closed.png").convert("RGBA"))
    donor_clean, _ = clean_skin(donor_raw)
    donor_clean = donor_clean.astype(np.uint8)
    dx0, dy0, dx1, dy1 = donor_roi_box
    donor = donor_clean[dy0:dy1, dx0:dx1]
    before1, after1 = base_1x[y0:y1, x0:x1], cand_1x[y0:y1, x0:x1]
    ax0, ay0, ax1, ay1 = 2 * x0, 2 * y0, 2 * x1, 2 * y1
    before2, after2 = base_2x[ay0:ay1, ax0:ax1], cand_2x[ay0:ay1, ax0:ax1]
    patch_results.append({
        "id": name,
        "screen_roi": next(x[2] for x in observed if x[0] == name),
        "texture_roi_1x_xyxy_exclusive": [x0, y0, x1, y1],
        "texture_roi_2x_xyxy_exclusive": [ax0, ay0, ax1, ay1],
        "donor_file": f"donor_eye_{side}_closed.png",
        "donor_roi_xyxy_exclusive": donor_roi_box,
        "donor_clean_alpha_gt0": int((donor[..., 3] > 0).sum()),
        "donor_clean_alpha_gt160": int((donor[..., 3] > 160).sum()),
        "pixels_changed_1x": int(np.any(before1 != after1, axis=2).sum()),
        "pixels_changed_2x": int(np.any(before2 != after2, axis=2).sum()),
        "1x_alpha_before": hist(before1[..., 3]),
        "1x_alpha_after": hist(after1[..., 3]),
        "2x_alpha_before": hist(before2[..., 3]),
        "2x_alpha_after": hist(after2[..., 3]),
    })

full_diff = np.any(base_full != cand_full, axis=2)
head_diff = np.any(base_head != cand_head, axis=2)
y, x = np.where(full_diff)
hy, hx = np.where(head_diff)

# Isolation SHA equality for eye base/lash layers.
eye_isolations = {}
for name in ("eye_l_base", "eye_l_lash", "eye_r_base", "eye_r_lash"):
    baseline_path = HERE / f"isolate_{name}.png"
    candidate_path = HERE / f"candidate_isolate_{name}.png"
    eye_isolations[name] = {
        "baseline_sha256": sha(baseline_path),
        "candidate_sha256": sha(candidate_path),
        "byte_identical": baseline_path.read_bytes() == candidate_path.read_bytes(),
    }

sidehair = {}
for part in ("hair_side_l", "hair_side_r"):
    baseline_path = HERE / f"isolate_{part}.png"
    candidate_path = HERE / f"candidate_isolate_{part}.png"
    arr = np.asarray(Image.open(baseline_path).convert("RGBA"))
    candidate_arr = np.asarray(Image.open(candidate_path).convert("RGBA"))
    regions = {}
    for name, _, (x0, y0, x1, y1), _ in observed:
        alpha = arr[y0:y1, x0:x1, 3]
        candidate_alpha = candidate_arr[y0:y1, x0:x1, 3]
        regions[name] = {
            "pixels": int(alpha.size),
            "baseline_alpha_gt0": int((alpha > 0).sum()),
            "candidate_alpha_gt0": int((candidate_alpha > 0).sum()),
            "baseline_alpha_max": int(alpha.max()),
            "candidate_alpha_max": int(candidate_alpha.max()),
        }
    sidehair[part] = {
        "baseline_sha256": sha(baseline_path),
        "candidate_sha256": sha(candidate_path),
        "byte_identical": baseline_path.read_bytes() == candidate_path.read_bytes(),
        "regions": regions,
    }

with open(HERE / "asset_qa_check_assets_snapshot.json", encoding="utf-8") as f:
    qa = json.load(f)
with open(HERE / "candidate_runtime_state.json", encoding="utf-8") as f:
    cand_state = json.load(f)

report = {
    "date": "2026-11-02",
    "scope": "isolated C-engine mapping and visual WIP; no production texture/rig edits",
    "render_controls": {"form": "chibi", "physics": False, "ambient": False, "scale": 1.0, "gaze": "off", "params_reset": True, "paused": True, "time": 0.0, "action": "idle"},
    "affine_fit": {
        "socket_ids": [s["id"] for s in socket_rows],
        "group_to_screen": M.tolist(),
        "screen_to_group": Mi.tolist(),
        "max_abs_socket_residual_px": float(np.max(np.abs(residual))),
        "rms_socket_residual_px": float(np.sqrt(np.mean(residual ** 2))),
        "rotation_degrees": float(np.degrees(np.arctan2(M[1, 0], M[0, 0]))),
        "seg_head_runtime_pos": head_part["pos"],
        "active_texture": head_part["file"],
        "texture_scale": head_part["scale"],
        "hires_factor": head_part["hires"],
        "mapping_rule": "Transform screen pixel centers by inverse affine, subtract runtime seg_head pos [140,68] to obtain seg_head texture coordinates, then multiply by 2 for active @2x texels.",
    },
    "matched_state": {
        "params_exact": state["params"] == cand_state["params"],
        "sockets_exact": state["sockets"] == cand_state["sockets"],
        "eye_base_lash_isolation": eye_isolations,
    },
    "C_frame_differences": {
        "full_frame_changed_pixels": int(full_diff.sum()),
        "full_frame_bbox_xyxy_exclusive": [int(x.min()), int(y.min()), int(x.max() + 1), int(y.max() + 1)],
        "seg_head_isolation_changed_pixels": int(head_diff.sum()),
        "seg_head_isolation_bbox_xyxy_exclusive": [int(hx.min()), int(hy.min()), int(hx.max() + 1), int(hy.max() + 1)],
        "interpretation": "The larger whole-frame difference is unexplained and must not be attributed to the patch. The head-only changes are localized to the mapped eye-adjacent windows; eye base/lash isolation frames are identical.",
    },
    "observed_screen_features": features,
    "isolated_WIP_patch_regions": patch_results,
    "sidehair_isolation": sidehair,
    "texture_sha256": {
        "baseline_1x": sha(HERE / "baseline_seg_head_unmodified.png"),
        "candidate_1x": sha(HERE / "candidate_seg_head_wip.png"),
        "baseline_2x": sha(HERE / "baseline_seg_head_unmodified@2x.png"),
        "candidate_2x": sha(HERE / "candidate_seg_head_wip@2x.png"),
    },
    "asset_check_snapshot": {
        "command": "tools/check_assets.py --character xiaoxun --form chibi --root . --json <report>",
        "pass": qa["pass"],
        "items": len(qa["items"]),
        "fail_count": qa["fail_count"],
        "design_iou": qa["design_iou"],
        "caveat": "Run on the already-built isolated candidate after local pixel edits; not a fresh 27-step dependency-chain rebuild. This independent snapshot must not be merged with historical QA counts as a continuous trend.",
    },
    "limitations": [
        "Left dark dash: luma<60 count drops from 10 to 1; one edge pixel remains dark, so the repair is not visually complete.",
        "Left gray mark: active @2x source pixels were not a transparent gap and were deliberately left unchanged in the final WIP candidate.",
        "Right upper and lower mapped gaps: local dark-pixel counts drop to zero in the C frame; no rectangle/seam judged visible in the saved zoom, but this is not production acceptance.",
        "No full rebuild, production integration, expression/hand/hair/hood/outfit/action matrix, or whole-Chibi acceptance was completed.",
    ],
}
(HERE / "screen_to_texture_map.json").write_text(json.dumps(py(report), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

# Review image: full-C crops and exact head-isolation diff mask (magenta).
font = ImageFont.load_default()
rows = [
    ("Left eye: dark dash mostly cleared; gray mark retained", (260, 510, 320, 545), [(289, 536, 299, 537), (292, 518, 302, 522)]),
    ("Right eye: mapped upper and lower gaps", (545, 510, 582, 542), [(555, 518, 570, 520), (553, 533, 557, 535)]),
]
scale = 7
panels = []
for title, box, marks in rows:
    x0, y0, x1, y1 = box
    row = []
    for arr, label in ((base_full, "baseline C frame"), (cand_full, "candidate C frame")):
        im = Image.fromarray(arr).crop(box).resize(((x1 - x0) * scale, (y1 - y0) * scale), Image.Resampling.NEAREST)
        d = ImageDraw.Draw(im)
        for a, b, c, e in marks:
            d.rectangle(((a - x0) * scale, (b - y0) * scale, (c - x0) * scale, (e - y0) * scale), outline=(255, 0, 255), width=2)
        row.append((im, label))
    mask = head_diff[y0:y1, x0:x1]
    rgb = np.zeros((mask.shape[0] * scale, mask.shape[1] * scale, 3), dtype=np.uint8)
    rgb[np.repeat(np.repeat(mask, scale, 0), scale, 1)] = [255, 0, 255]
    row.append((Image.fromarray(rgb), "seg_head changed pixels"))
    panels.append((title, row))
W = 3 * max(im.width for _, row in panels for im, _ in row) + 32
H = sum(row[0][0].height + 36 for _, row in panels) + 20
canvas = Image.new("RGB", (W, H), (248, 248, 248))
draw = ImageDraw.Draw(canvas)
ypos = 8
for title, row in panels:
    draw.text((8, ypos), title + " — magenta boxes = observed screen windows", font=font, fill=(0, 0, 0))
    ypos += 18
    for i, (im, label) in enumerate(row):
        xpos = 8 + i * (im.width + 8)
        canvas.paste(im, (xpos, ypos))
        draw.text((xpos, ypos + im.height + 2), label, font=font, fill=(0, 0, 0))
    ypos += row[0][0].height + 36
canvas.save(HERE / "C_frame_gapfill_crosscheck.png")
print("wrote screen_to_texture_map.json and C_frame_gapfill_crosscheck.png")
