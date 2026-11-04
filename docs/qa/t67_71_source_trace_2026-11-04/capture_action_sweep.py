#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Capture selected real-C action transition points for T67.71 (diagnostic only)."""
from __future__ import annotations

import argparse
import io
import json
import urllib.request
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

DT = 1 / 60
START_T = 2.0
CASES = {
    "surprised": (0.15, 0.30, 0.60, 0.90, 1.10, 1.30),
    "wave": (0.15, 0.30, 0.60, 0.90, 1.10, 1.80, 2.30),
}
INTEREST = ("ParamArmLA", "ParamArmRA", "ParamArmLB", "ParamArmRB",
            "ParamSurpriseArmSwap", "ParamHairSway", "ParamHairFront", "ParamHairSide")


def fetch(base, path):
    with urllib.request.urlopen(base + path, timeout=20) as r:
        return r.read()


def jget(base, path):
    return json.loads(fetch(base, path).decode("utf-8"))


def api(base, path):
    r = jget(base, path)
    if isinstance(r, dict) and r.get("ok") is False:
        raise RuntimeError(f"API rejected {path}: {r}")
    return r


def reset(base):
    api(base, f"/api/pause?on=1&t={START_T:.1f}")
    for path in ("/api/ambient?on=0", "/api/blink?on=0", "/api/idle?on=0", "/api/physics?on=0",
                 "/api/param?all=1&reset=1", "/api/part?all=1", "/api/scale?s=1",
                 "/api/pose?group=hairstyle&id=long", "/api/pose?group=hood_pose&id=up",
                 "/api/action?id=idle", "/api/param?id=ParamHairSway&v=0", "/api/physics?on=1"):
        api(base, path)


def make_tile(label, image, crop=(145, 320, 700, 930), scale=0.65):
    image = image.crop(crop).convert("RGBA")
    bg = Image.new("RGB", image.size, (38, 40, 44))
    bg.paste(image, (0, 0), image)
    bg = bg.resize((round(bg.width * scale), round(bg.height * scale)), Image.Resampling.LANCZOS)
    out = Image.new("RGB", (bg.width + 2, bg.height + 26), (18, 18, 20))
    out.paste(bg, (1, 26))
    draw = ImageDraw.Draw(out)
    draw.text((4, 5), label, font=ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf", 13), fill=(255, 239, 110))
    return out


def save_board(out, action, records):
    tiles = []
    for rec in records:
        im = Image.open(out / rec["frame"])
        tiles.append(make_tile(f"{action} t={rec['actual_action_seconds']:.3f}s", im))
    gap = 6
    width = gap + sum(x.width + gap for x in tiles)
    height = max(x.height for x in tiles) + gap * 2
    board = Image.new("RGB", (width, height), (20, 20, 22))
    x = gap
    for tile in tiles:
        board.paste(tile, (x, gap))
        x += tile.width + gap
    board.save(out / f"c_engine_{action}_timing_sweep.png")


def restore(base):
    reset(base)
    api(base, "/api/step?n=120&dt=0.01666667")
    api(base, "/api/pause?on=0")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:5173")
    ap.add_argument("--out", default=str(Path(__file__).resolve().parent))
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    all_records = {}
    try:
        for action, times in CASES.items():
            reset(args.base)
            api(args.base, f"/api/action?id={action}")
            records = []
            prev_frame = 0
            for target in times:
                target_frame = round(target / DT)
                delta = target_frame - prev_frame
                step = api(args.base, f"/api/step?n={delta}&dt={DT:.8f}")
                prev_frame = target_frame
                actual = target_frame * DT
                condition = f"{action}_t{target_frame:03d}"
                image_file = f"timing_{condition}_c_engine.png"
                Image.open(io.BytesIO(fetch(args.base, "/api/frame.png?t=5"))).convert("RGBA").save(out / image_file)
                info = jget(args.base, "/api/info.json")
                params = jget(args.base, "/api/params.json")
                bones = jget(args.base, "/api/bones.json")
                (out / f"timing_{condition}_info.json").write_text(json.dumps(info, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
                (out / f"timing_{condition}_params.json").write_text(json.dumps(params, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
                (out / f"timing_{condition}_bones.json").write_text(json.dumps(bones, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
                chosen = {p["id"]: {k: p.get(k) for k in ("value", "expr", "effective")}
                          for p in params.get("params", []) if p.get("id") in INTEREST}
                rec = {
                    "action": action,
                    "requested_action_seconds": target,
                    "actual_action_seconds": round(actual, 6),
                    "absolute_virtual_time": step.get("t"),
                    "params": chosen,
                    "arms": bones.get("arms", []),
                    "info_action": info.get("action"),
                    "frame": image_file,
                    "step": step,
                }
                records.append(rec)
                print(action, f"t={actual:.3f}", [(x.get("side"), x.get("wrist")) for x in rec["arms"]])
            save_board(out, action, records)
            all_records[action] = records
        meta = {
            "scope": "selected real C action transition frames at ParamHairSway=0; diagnostic only, not an exhaustive pose matrix or artwork approval",
            "form": "teen",
            "poses": {"hairstyle": "long", "hood_pose": "up"},
            "canvas_px": [848, 1360],
            "scale": 1,
            "ambient": "off",
            "physics": "on; reset by switching off at shared virtual start time before each action",
            "action_samples": all_records,
            "unresolved": ["other action transitions and arm-angle combinations", "sway extremes during every transition", "source-art continuity / reviewed repair path", "production and full C acceptance"],
        }
        (out / "action_sweep_metrics.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    finally:
        restore(args.base)
    print("captured", sum(map(len, all_records.values())), "transition frames")


if __name__ == "__main__":
    main()
