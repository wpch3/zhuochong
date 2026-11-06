#!/usr/bin/env python3
"""Render a real-C visibility diagnostic for trial24 wrist layering (WIP only)."""
from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import tempfile
from pathlib import Path

STUDY = Path(__file__).resolve().parent
REPO = STUDY.parents[3]
SRC = REPO / "src"
CANDIDATE = STUDY / "chibi_arm_rig_candidate_2026-11-03_wip"
OUT = STUDY / "trial24_wrist_layer_visibility_wip"
RUNNER = STUDY / "render_candidate_c_engine_wrist_layer_visibility_wip.c"
EXE = Path(tempfile.gettempdir()) / "chibi_candidate_wrist_layer_visibility"
BOARD = STUDY / "trial24_wrist_layer_visibility_board_wip.png"
METRICS = STUDY / "trial24_wrist_layer_visibility_metrics_wip.json"
ANGLES = (-30, 0, 30)
MODES = ("normal", "forearm_hidden", "mitten_hidden")
CANVAS = (848, 1360)
CROP_SCALE = 4

def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

def run(args: list[str]) -> str:
    p = subprocess.run(args, cwd=REPO, text=True, capture_output=True)
    if p.returncode:
        raise RuntimeError(f"command failed ({p.returncode}): {' '.join(args)}\n{p.stdout}\n{p.stderr}")
    return p.stdout.strip()

def registered_rois() -> dict[str, tuple[int, int, int, int]]:
    manifest = json.loads((STUDY / "source_crop_manifest.json").read_text(encoding="utf-8"))
    body_w, body_h = manifest["body_full_size"]
    offset_x = (CANVAS[0] - body_w) // 2
    offset_y = CANVAS[1] - body_h
    result = {}
    for side, rec in manifest["source_crops"].items():
        x0, y0, x1, y1 = rec["body_full_roi_xyxy_exclusive"]
        result[side] = (x0 + offset_x, y0 + offset_y, x1 - x0, y1 - y0)
    return result

def compile_runner() -> None:
    core_sources = sorted((SRC / "core").glob("*.c"))
    run([
        "cc", "-std=c11", "-O2", "-pthread", f"-I{SRC / 'core'}",
        str(RUNNER), *map(str, core_sources), "-lm", "-pthread", "-ldl", "-o", str(EXE)
    ])

def make_board(tiles: list[Path]) -> None:
    montage = shutil.which("montage")
    convert = shutil.which("convert")
    if not montage or not convert:
        raise RuntimeError("ImageMagick montage/convert are required for diagnostic layout")
    temp = Path(tempfile.mkdtemp(prefix="chibi_trial24_layer_board_"))
    try:
        labeled = []
        for i, tile in enumerate(tiles):
            label = temp / f"label_{i:02d}.png"
            run([
                convert, str(tile), "-background", "#f8f7f9", "-fill", "#26242a",
                "-font", "DejaVu-Sans", "-pointsize", "14", "-gravity", "NorthWest",
                "-splice", "0x24", "-annotate", "+6+4", tile.stem.replace("_", " "), str(label)
            ])
            labeled.append(label)
        montage_args = [montage, *map(str, labeled), "-tile", "3x3", "-geometry", "+8+8",
                        "-background", "#f8f7f9", str(BOARD)]
        run(montage_args)
        run([convert, str(BOARD), "-gravity", "NorthWest", "-background", "#f8f7f9",
             "-fill", "#26242a", "-font", "DejaVu-Sans", "-pointsize", "15", "-splice", "0x48",
             "-annotate", "+8+6", "REAL C zrig · trial24 wrist layer visibility · WIP",
             "-annotate", "+8+26", "Columns: normal / whole forearm hidden / mitten hidden. Rows: wrist −30° / 0° / +30°. Forearm-hidden removes the entire sleeve, not just the cuff.", str(BOARD)])
    finally:
        shutil.rmtree(temp, ignore_errors=True)

def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    compile_runner()
    rois = registered_rois()
    frames = []
    tiles = []
    with tempfile.TemporaryDirectory(prefix="chibi_trial24_layer_frames_") as td:
        temp = Path(td)
        for angle in ANGLES:
            for mode in MODES:
                frame = temp / f"frame_{angle:+03d}_{mode}.png"
                args = [
                    str(EXE), str(CANDIDATE / "rig_candidate_wip.json"), str(CANDIDATE), str(frame),
                    "mitten", str(angle), "0", "0", "none", "0.02", "0", "1", mode
                ]
                log = run(args)
                if f"style=mitten wrist={angle:.1f}" not in log or f"mode={mode}" not in log or "size=848x1360" not in log or "active_action=idle" not in log:
                    raise RuntimeError(f"unexpected C render log: {log}")
                if run(["identify", "-format", "%wx%h %[channels]", str(frame)])[:9] != "848x1360 ":
                    raise RuntimeError(f"invalid C frame: {frame}")
                frame_sha = sha(frame)
                frames.append({"angle_deg": angle, "layer_mode": mode, "sha256": frame_sha, "log": log})
                panel = temp / f"panel_{angle:+03d}_{mode}.png"
                crops = []
                for side in ("left", "right"):
                    x, y, w, h = rois[side]
                    crop = temp / f"crop_{angle:+03d}_{mode}_{side}.png"
                    run(["convert", str(frame), "-crop", f"{w}x{h}+{x}+{y}", "+repage", "-filter", "point", "-resize", f"{CROP_SCALE*100}%", str(crop)])
                    crops.append(crop)
                run(["convert", str(crops[0]), str(crops[1]), "+append", str(panel)])
                tiles.append(panel)
        make_board(tiles)
    metrics = {
        "status": "isolated visibility diagnostic only; trial24 AI art remains unapproved WIP",
        "candidate_rig_sha256": sha(CANDIDATE / "rig_candidate_wip.json"),
        "runner_sha256": sha(RUNNER),
        "board": BOARD.name,
        "board_sha256": sha(BOARD),
        "angles_deg": list(ANGLES),
        "modes": {
            "normal": "all candidate and arm layers visible",
            "forearm_hidden": "both complete arm_*_fore parts hidden; this is NOT a cuff-only toggle",
            "mitten_hidden": "both trial24 mitten hand parts hidden after selecting the mitten pose"
        },
        "render_conditions": {"style": "mitten", "shoulder_elbow_deg": [0, 0], "requested_action": "none", "active_action_asserted": "idle", "tick_sec": 0.02, "ambient": 0, "core_accessories_hidden": True},
        "registered_rois_canvas_xywh": {k: list(v) for k, v in rois.items()},
        "crop_scale_nearest": CROP_SCALE,
        "frames": frames,
        "limitations": [
            "This visibility diagnostic itself generated or modified no art; all C frames are temporary and represented by hashes/logs.",
            "Forearm-hidden removes the entire forearm/sleeve layer, not a separate cuff-front part.",
            "Three wrist samples are a visibility diagnostic, not an exhaustive motion matrix, safe range, or art approval.",
            "The test uses an isolated candidate rig; production assets/rig/generator are untouched."
        ]
    }
    METRICS.write_text(json.dumps(metrics, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Rendered {len(frames)} real-C visibility samples; wrote {BOARD.name} and {METRICS.name}.")

if __name__ == "__main__":
    main()
