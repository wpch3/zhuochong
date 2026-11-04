#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Capture a controlled Teen long-hair/hood-up pose × ParamHairSway C-engine matrix.

Diagnostic only; this does not modify or repair production assets. Requires the live
preview API plus Pillow and NumPy (used only for review boards / pixel summaries).
"""
from __future__ import annotations

import argparse
import io
import json
import urllib.parse
import urllib.request
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

ACTIONS = {
    "idle": {"step_n": 180, "dt": 1 / 60, "note": "arms-down baseline; 3 s fixed-step settle"},
    "surprised": {"step_n": 22, "dt": 0.05, "note": "same 1.1 s capture time as prior control"},
    "wave_both": {"step_n": 20, "dt": 0.05, "note": "1.0 s; arm/elbow keys near raised hold"},
    "heart_hands": {"step_n": 12, "dt": 0.05, "note": "0.6 s; both hand pose pulses reached"},
    "wave": {"step_n": 20, "dt": 0.05, "note": "1.0 s; single right-arm wave near raised hold"},
}
SWAYS = (-1.0, 0.0, 1.0)
PART = "acc_hair_hood_long"
PARAMS_OF_INTEREST = {
    "ParamHairSway", "ParamArmLA", "ParamArmRA", "ParamArmLB", "ParamArmRB",
    "ParamSurpriseArmSwap", "ParamSurpriseElbowHide", "ParamSurpriseForeshorten",
    "ParamHandLSurprised", "ParamHandRSurprised",
}


def get(base: str, path: str) -> bytes:
    with urllib.request.urlopen(base + path, timeout=20) as response:
        return response.read()


def get_json(base: str, path: str):
    return json.loads(get(base, path).decode("utf-8"))


def api(base: str, path: str):
    result = get_json(base, path)
    if isinstance(result, dict) and result.get("ok") is False:
        raise RuntimeError(f"API rejected {path}: {result}")
    return result


def reset_condition(base: str, sway: float):
    # Freeze every branch at the same virtual start; turning physics off resets its
    # state before re-enabling, preventing the previous condition leaking into this one.
    api(base, "/api/pause?on=1&t=2.0")
    api(base, "/api/ambient?on=0")
    api(base, "/api/blink?on=0")
    api(base, "/api/idle?on=0")
    api(base, "/api/physics?on=0")
    api(base, "/api/param?all=1&reset=1")
    api(base, "/api/part?all=1")
    api(base, "/api/scale?s=1")
    api(base, "/api/pose?group=hairstyle&id=long")
    api(base, "/api/pose?group=hood_pose&id=up")
    api(base, "/api/action?id=idle")
    api(base, f"/api/param?id=ParamHairSway&v={sway:.1f}")
    api(base, "/api/physics?on=1")


def save_state(base: str, out: Path, action: str, sway: float):
    condition = f"{action}_sway_{sway:+.0f}".replace("+", "plus").replace("-", "minus")
    settings = ACTIONS[action]
    reset_condition(base, sway)
    if action != "idle":
        api(base, f"/api/action?id={urllib.parse.quote(action)}")
    api(base, f"/api/step?n={settings['step_n']}&dt={settings['dt']:.8f}")

    # The state is now frozen at an identical virtual-time trajectory for each branch.
    info = get_json(base, "/api/info.json")
    params = get_json(base, "/api/params.json")
    bones = get_json(base, "/api/bones.json")
    image = Image.open(io.BytesIO(get(base, "/api/frame.png?t=5"))).convert("RGBA")
    image.save(out / f"matrix_{condition}_c_engine.png")
    (out / f"matrix_{condition}_info.json").write_text(
        json.dumps(info, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (out / f"matrix_{condition}_params.json").write_text(
        json.dumps(params, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (out / f"matrix_{condition}_bones.json").write_text(
        json.dumps(bones, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    row = {
        "action": action,
        "action_capture_seconds": round(settings["step_n"] * settings["dt"], 6),
        "action_note": settings["note"],
        "sway_requested": sway,
        "info": {k: info.get(k) for k in ("action", "reason", "form", "frame_w", "frame_h", "poses")},
        "params": {p["id"]: {k: p.get(k) for k in ("min", "max", "value", "expr", "effective")}
                   for p in params.get("params", []) if p.get("id") in PARAMS_OF_INTEREST},
        "arms": bones.get("arms", []),
        "file": f"matrix_{condition}_c_engine.png",
    }

    controls = {}
    # At both sway endpoints, isolate / hide the target cutout without changing the
    # frozen action or physics state. These are visibility controls, not alternate art.
    if abs(sway) == 1.0:
        api(base, "/api/part?all=1")
        api(base, f"/api/part?id={PART}&vis=2")
        controls["isolated"] = f"matrix_{condition}_hair_isolated.png"
        Image.open(io.BytesIO(get(base, "/api/frame.png?t=5"))).convert("RGBA").save(out / controls["isolated"])
        api(base, "/api/part?all=1")
        api(base, f"/api/part?id={PART}&vis=0")
        controls["hidden"] = f"matrix_{condition}_hair_hidden.png"
        Image.open(io.BytesIO(get(base, "/api/frame.png?t=5"))).convert("RGBA").save(out / controls["hidden"])
        api(base, "/api/part?all=1")
    row["visibility_controls"] = controls
    return row


def tile(label: str, image: Image.Image, crop=None, scale=1.0):
    if crop:
        image = image.crop(crop)
    image = image.convert("RGBA")
    bg = Image.new("RGB", image.size, (38, 40, 44))
    bg.paste(image, (0, 0), image)
    if scale != 1:
        bg = bg.resize((round(bg.width * scale), round(bg.height * scale)), Image.Resampling.LANCZOS)
    label_h = 25
    result = Image.new("RGB", (bg.width + 2, bg.height + label_h), (15, 15, 18))
    result.paste(bg, (1, label_h))
    draw = ImageDraw.Draw(result)
    font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf", 14)
    draw.text((4, 4), label, font=font, fill=(255, 239, 110))
    return result


def compose_boards(out: Path, rows):
    # Full-body action × sway overview and upper-body/cuff detail; crops are for review only.
    labels = {"idle": "arms-down idle", "surprised": "surprised", "wave_both": "two-hand wave", "heart_hands": "heart hands", "wave": "single-arm wave"}
    full_rows, detail_rows = [], []
    for action in ACTIONS:
        cells, details = [], []
        for sway in SWAYS:
            condition = f"{action}_sway_{sway:+.0f}".replace("+", "plus").replace("-", "minus")
            image = Image.open(out / f"matrix_{condition}_c_engine.png").convert("RGBA")
            cells.append(tile(f"{labels[action]} | ParamHairSway {sway:+.0f}", image, scale=0.42))
            details.append(tile(f"{action} | sway {sway:+.0f}", image, crop=(145, 320, 700, 930), scale=0.8))
        full_rows.append(cells)
        detail_rows.append(details)

    def grid(rows, filename):
        pad = 8
        row_h = max(cell.height for row in rows for cell in row)
        col_w = max(cell.width for row in rows for cell in row)
        board = Image.new("RGB", (pad + len(rows[0]) * (col_w + pad), pad + len(rows) * (row_h + pad)), (20, 20, 22))
        for ri, row in enumerate(rows):
            for ci, cell in enumerate(row):
                board.paste(cell, (pad + ci * (col_w + pad), pad + ri * (row_h + pad)))
        board.save(out / filename)

    grid(full_rows, "c_engine_sway_pose_matrix_fullbody.png")
    grid(detail_rows, "c_engine_sway_pose_matrix_detail.png")

    # Visibility controls at both sway extremes: full / target-only / target hidden.
    control_rows = []
    for action in ACTIONS:
        row = []
        for sway in (-1.0, 1.0):
            condition = f"{action}_sway_{sway:+.0f}".replace("+", "plus").replace("-", "minus")
            for mode, suffix in (("full", "c_engine"), ("target only", "hair_isolated"), ("target hidden", "hair_hidden")):
                row.append(tile(f"{action} | {sway:+.0f} | {mode}",
                                Image.open(out / f"matrix_{condition}_{suffix}.png"),
                                crop=(145, 320, 700, 930), scale=0.7))
        control_rows.append(row)
    grid(control_rows, "c_engine_sway_pose_matrix_visibility_controls.png")


def visible_diff(path_a: Path, path_b: Path):
    # Compare the displayed result, not hidden RGB stored in fully transparent pixels.
    a = Image.open(path_a).convert("RGBA")
    b = Image.open(path_b).convert("RGBA")
    bg = Image.new("RGBA", a.size, (38, 40, 44, 255))
    aa = np.asarray(Image.alpha_composite(bg, a)).astype(np.int16)[:, :, :3]
    bb = np.asarray(Image.alpha_composite(bg, b)).astype(np.int16)[:, :, :3]
    delta = np.abs(aa - bb)
    return {
        "visible_pixels_any_rgb_change": int(np.count_nonzero(np.any(delta != 0, axis=2))),
        "visible_pixels_channel_delta_gt_4": int(np.count_nonzero(np.any(delta > 4, axis=2))),
        "max_visible_channel_delta": int(delta.max()),
    }


def summarize_pixels(out: Path, rows):
    summary = {}
    for action in ACTIONS:
        full = visible_diff(out / f"matrix_{action}_sway_minus1_c_engine.png",
                            out / f"matrix_{action}_sway_plus1_c_engine.png")
        summary[action] = {
            **full,
            "interpretation": "same action/time, reset physics state, only requested ParamHairSway differs; whole-frame visible diff includes all dependent hair/physics pixels and is not a source-pixel motion field",
        }
        for mode in ("hair_isolated", "hair_hidden"):
            summary[action][mode + "_extreme_diff"] = {
                **visible_diff(out / f"matrix_{action}_sway_minus1_{mode}.png",
                               out / f"matrix_{action}_sway_plus1_{mode}.png"),
                "interpretation": "same frozen pose/action and target visibility; displayed-image diff, not an individual source-pixel motion field",
            }
    return summary


def restore_preview(base: str):
    api(base, "/api/pause?on=1&t=2.0")
    api(base, "/api/ambient?on=0")
    api(base, "/api/blink?on=0")
    api(base, "/api/idle?on=0")
    api(base, "/api/physics?on=0")
    api(base, "/api/param?all=1&reset=1")
    api(base, "/api/part?all=1")
    api(base, "/api/scale?s=1")
    api(base, "/api/pose?group=hairstyle&id=long")
    api(base, "/api/pose?group=hood_pose&id=up")
    api(base, "/api/action?id=idle")
    api(base, "/api/param?id=ParamHairSway&v=0")
    api(base, "/api/physics?on=1")
    api(base, "/api/step?n=120&dt=0.01666667")
    api(base, "/api/pause?on=0")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="http://127.0.0.1:5173")
    parser.add_argument("--out", default=str(Path(__file__).resolve().parent))
    args = parser.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    rows = []
    try:
        for action in ACTIONS:
            for sway in SWAYS:
                row = save_state(args.base, out, action, sway)
                rows.append(row)
                print(action, sway, "wrist", [(arm.get("side"), arm.get("wrist")) for arm in row["arms"]])
        summary = {
            "scope": "diagnostic C-engine pose × hair-sway matrix; not artwork approval or a repair",
            "engine": get_json(args.base, "/api/info.json").get("engine"),
            "preview_base": args.base,
            "form": "teen",
            "poses": {"hairstyle": "long", "hood_pose": "up"},
            "canvas_px": [848, 1360],
            "scale": 1,
            "ambient": "off",
            "physics": "on during captures; reset by switching off at common virtual start t=2 before each branch",
            "visibility": "all parts for matrix frames; target-only and target-hidden controls recorded at both ParamHairSway endpoints for each pose",
            "target_part": PART,
            "display_diff_method": {"matte_rgb": [38, 40, 44], "report_threshold": "per-channel RGB delta > 4", "transparent_hidden_rgb": "composited away before counting"},
            "states": rows,
            "same_pose_sway_extreme_diffs": summarize_pixels(out, rows),
            "unresolved": ["source-art continuity behind hand/cuff cutouts", "complete arm-angle/occlusion extremes beyond these four actions", "reviewed repair path and production approval"],
        }
        (out / "pose_matrix_metrics.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        compose_boards(out, rows)
    finally:
        restore_preview(args.base)
    print("captured", len(rows), "full states; visibility controls at both sway endpoints for", len(ACTIONS), "pose/action states")


if __name__ == "__main__":
    main()
