#!/usr/bin/env python3
"""Build an isolated Chibi arm/hand-style QA candidate.

The production tree is copied to a temporary root before the existing generators run.
Only generated candidate sprites/rig and explicitly WIP trial24 hand art are written to
this QA directory. This script must never write to characters/xiaoxun/forms/chibi.
"""
from __future__ import annotations
import argparse, hashlib, json, os, shutil, subprocess, sys, tempfile
from pathlib import Path
from PIL import Image

STUDY = Path(__file__).resolve().parent
REPO = STUDY.parents[3]
OUT = STUDY / "chibi_arm_rig_candidate_2026-11-03_wip"
TRIAL = STUDY / "trial24_sourcefit_candidate_parts"
TRIAL24_METRICS = STUDY / "mitten_trial24_sourcefit_metrics.json"
SMALL_METRICS = STUDY / "chibi_small_hand_source_extraction_metrics.json"
SMALL_CUTOUTS = {"l": STUDY / "chibi_small_left_source_pixels_wip.png", "r": STUDY / "chibi_small_right_source_pixels_wip.png"}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def copy_tree(src: Path, dst: Path) -> None:
    shutil.copytree(src, dst, dirs_exist_ok=True)


def rel_file(path: Path, base: Path) -> str:
    return Path(os.path.relpath(path, base)).as_posix()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true", help="replace this isolated QA output directory only")
    args = parser.parse_args()
    needed = [
        STUDY / "chibi_small_left_source_pixels_wip.png",
        STUDY / "chibi_small_right_source_pixels_wip.png",
        TRIAL / "hand_left_mitten_trial24_candidate_wip.png",
        TRIAL / "hand_right_mitten_trial24_candidate_wip.png",
        TRIAL24_METRICS,
        SMALL_METRICS,
        *SMALL_CUTOUTS.values(),
    ]
    missing = [str(path) for path in needed if not path.is_file()]
    if missing:
        raise SystemExit("missing isolated hand-study input(s): " + ", ".join(missing))
    if OUT.exists():
        if not args.force:
            raise SystemExit(f"{OUT} exists; pass --force to replace the QA candidate only")
        # Guard: the only permitted deletion target is the exact dated QA output directory.
        if OUT.resolve() != (STUDY / "chibi_arm_rig_candidate_2026-11-03_wip").resolve():
            raise SystemExit("refusing unexpected output path")
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)
    source_body = REPO / "characters/xiaoxun/forms/chibi/sprites/body_full.png"
    metrics = json.loads(TRIAL24_METRICS.read_text(encoding="utf-8"))
    with tempfile.TemporaryDirectory(prefix="chibi_arm_parts_build_") as tmp_name:
        tmp = Path(tmp_name)
        copy_tree(REPO / "characters/xiaoxun", tmp / "characters/xiaoxun")
        copy_tree(REPO / "tools", tmp / "tools")
        env = os.environ.copy()
        env["PYTHONPATH"] = str(tmp / "tools") + os.pathsep + env.get("PYTHONPATH", "")
        py = sys.executable
        subprocess.run([py, str(tmp / "tools/make_arm_parts.py"), "--character", "xiaoxun", "--form", "chibi", "--root", str(tmp)], cwd=tmp, env=env, check=True)
        subprocess.run([py, str(tmp / "tools/make_rig.py"), "--character", "xiaoxun", "--form", "chibi", "--root", str(tmp)], cwd=tmp, env=env, check=True)
        form = tmp / "characters/xiaoxun/forms/chibi"
        sprites = form / "sprites"
        rig = json.loads((form / "rig.json").read_text(encoding="utf-8"))
        copy_tree(sprites, OUT / "sprites")

        # For the QA `small` variant, replace the builder's generated wrist-stub sprite
        # with the registered source-pixel cutout. No hidden wrist continuation is drawn;
        # rotations may therefore expose the known source gap and are diagnostic only.
        small_metrics = json.loads(SMALL_METRICS.read_text(encoding="utf-8"))
        source_small_records = {}
        source_canvas_offset = (int(round((848 - 567) / 2)), 1360 - 1292)
        for side in ("l", "r"):
            side_name = "left" if side == "l" else "right"
            record = small_metrics["hands"][side_name]
            roi = record["body_full_roi_xyxy_exclusive"]
            extraction = record["extraction_crop_xyxy_exclusive_with_3px_source_neighborhood"]
            # The cutout coordinates are local to the registered body_full ROI.
            x = source_canvas_offset[0] + roi[0] + extraction[0]
            y = source_canvas_offset[1] + roi[1] + extraction[1]
            image = Image.open(SMALL_CUTOUTS[side]).convert("RGBA")
            group = rig.get("groups", {}).get(f"hand_{side}")
            if not group:
                raise SystemExit(f"make_rig did not produce hand_{side} group")
            pivot = group["pivot"]
            anchor = [(pivot[0] - x) / image.width, (pivot[1] - y) / image.height]
            if not all(-0.25 <= value <= 1.25 for value in anchor):
                raise SystemExit(f"out-of-range exact-source hand anchor: {side} {anchor}")
            filename = f"hand_{side}.png"
            image.save(OUT / "sprites" / filename)
            part = next(p for p in rig["parts"] if p["id"] == f"hand_{side}")
            part.update({
                "file": f"sprites/{filename}",
                "pos": [round(pivot[0], 2), round(pivot[1], 2)],
                "anchor": [round(anchor[0], 6), round(anchor[1], 6)],
                "note": "QA exact registered Chibi small-hand source pixels; hidden wrist absent and intentionally not invented",
            })
            source_small_records[side] = {
                "source_cutout": SMALL_CUTOUTS[side].name,
                "source_cutout_sha256": sha(SMALL_CUTOUTS[side]),
                "source_rgba_identity_verified": record["source_rgba_identity_verified_after_png_round_trip"],
                "registered_canvas_top_left": [x, y],
                "pivot_canvas": pivot,
                "image_size": list(image.size),
                "anchor": part["anchor"],
                "hidden_wrist_invented": False,
            }

        # Retarget only the candidate rig's external action/expression references to
        # existing character-owned data. Sprite references remain candidate-local.
        for section in ("motions", "expression_files"):
            sub = "motions" if section == "motions" else "expressions"
            for row in rig.get(section, []):
                source = REPO / "characters/xiaoxun" / sub / Path(row["file"]).name
                if not source.is_file():
                    raise SystemExit(f"missing motion/expression source: {source}")
                row["file"] = rel_file(source, OUT)

        # Registered source body canvas offset and measured left/right hand ROIs.
        canvas_offset = (int(round((848 - 567) / 2)), 1360 - 1292)
        body_roi_top_left = {"l": (43, 846), "r": (435, 846)}
        new_parts: list[str] = []
        placements = {}
        for side in ("l", "r"):
            side_name = "left" if side == "l" else "right"
            fit = metrics["fit_metrics"][side_name]
            placement = fit["placement_xy"]
            roi_x, roi_y = body_roi_top_left[side]
            x = canvas_offset[0] + roi_x + placement[0]
            y = canvas_offset[1] + roi_y + placement[1]
            image_path = TRIAL / f"hand_{side_name}_mitten_trial24_candidate_wip.png"
            image = Image.open(image_path).convert("RGBA")
            width, height = image.size
            group = rig.get("groups", {}).get(f"hand_{side}")
            if not group:
                raise SystemExit(f"make_rig did not produce hand_{side} group")
            pivot = group["pivot"]
            anchor = [(pivot[0] - x) / width, (pivot[1] - y) / height]
            if not all(-0.25 <= value <= 1.25 for value in anchor):
                raise SystemExit(f"out-of-range candidate anchor: {side} {anchor}")
            filename = f"hand_{side}_mitten_trial24_candidate_wip.png"
            image.save(OUT / "sprites" / filename)
            part_id = f"hand_{side}_mitten_trial24_candidate_wip"
            reference = next((part for part in rig["parts"] if part["id"] == f"hand_{side}"), None)
            if not reference:
                raise SystemExit(f"missing generated small-hand part hand_{side}")
            part = dict(reference)
            part.update({
                "id": part_id,
                "file": f"sprites/{filename}",
                "pos": [round(pivot[0], 2), round(pivot[1], 2)],
                "anchor": [round(anchor[0], 6), round(anchor[1], 6)],
                "note": "isolated trial24 AI mitten WIP; unapproved; exact source cuff remains in forearm layer",
            })
            rig["parts"].append(part)
            new_parts.append(part_id)
            placements[side] = {
                "target_top_left_canvas": [x, y],
                "pivot_canvas": pivot,
                "image_size": [width, height],
                "anchor": part["anchor"],
                "roi_body_xy": [roi_x, roi_y],
                "placement_in_roi": placement,
                "source_ai_art_sha256": sha(image_path),
            }

        if any(pose.get("id") == "hand_style" for pose in rig.get("poses", [])):
            raise SystemExit("unexpected existing hand_style pose")
        rig.setdefault("poses", []).append({
            "id": "hand_style",
            "fade": 0,
            "default": "small",
            "entries": [
                {"id": "small", "parts": ["hand_l", "hand_r"]},
                {"id": "mitten", "parts": new_parts},
            ],
            "note": "isolated QA feasibility pose; does not approve AI art or production integration",
        })
        rig["id"] = "xiaoxun_chibi_arm_rig_candidate_wip"
        (OUT / "rig_candidate_wip.json").write_text(json.dumps(rig, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        shutil.copy2(sprites / "arm_parts.json", OUT / "arm_parts_candidate_wip.json")
        shutil.copy2(sprites / "parts_report.json", OUT / "parts_report_candidate_wip.json")
        (OUT / "candidate_parts").mkdir(exist_ok=True)
        for side in ("l", "r"):
            shutil.copy2(OUT / "sprites" / f"hand_{side}_mitten_trial24_candidate_wip.png", OUT / "candidate_parts" / f"hand_{side}_mitten_trial24_candidate_wip.png")
        candidate_record = {
            "status": "isolated_candidate_wip_only",
            "generated_from_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO, text=True).strip(),
            "builder_source_hashes": {
                "make_arm_parts.py": sha(REPO / "tools/make_arm_parts.py"),
                "make_rig.py": sha(REPO / "tools/make_rig.py"),
            },
            "source_body_sha256": sha(source_body),
            "trial24_metrics_sha256": sha(TRIAL24_METRICS),
            "candidate_rig_id": rig["id"],
            "part_count": len(rig["parts"]),
            "group_count": len(rig["groups"]),
            "pose_group_count": len(rig.get("poses", [])),
            "hand_style": rig["poses"][-1],
            "hand_parts_added": new_parts,
            "source_small_hand_parts": source_small_records,
            "hand_art_placement": placements,
            "limits": [
                "only isolated QA assets; no official Chibi sprite/rig/generator writes",
                "mitten parts are AI-origin WIP and remain unapproved",
                "small source hand pixels stop at original cuff; no hidden-wrist art is invented",
                "only default Chibi outfit/hair is available",
                "gesture hand artwork is absent",
            ],
        }
        (OUT / "candidate_metrics.json").write_text(json.dumps(candidate_record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    hashes = []
    for path in sorted(item for item in OUT.rglob("*") if item.is_file() and item.name != "SHA256SUMS.txt"):
        hashes.append(f"{sha(path)}  {path.relative_to(OUT).as_posix()}")
    (OUT / "SHA256SUMS.txt").write_text("\n".join(hashes) + "\n", encoding="utf-8")
    print(f"candidate={OUT} parts={len(rig['parts'])} groups={len(rig['groups'])} pose_groups={len(rig.get('poses', []))}")


if __name__ == "__main__":
    main()
