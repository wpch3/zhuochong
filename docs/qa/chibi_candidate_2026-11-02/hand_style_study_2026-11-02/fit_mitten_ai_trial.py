#!/usr/bin/env python3
"""Fit two AI-generated Chibi mitten art trials under the original source cuffs.

This writes only isolated QA/WIP previews. It does not draw hands: the left and
right silhouettes come from AI trials 04 and 05. Cropping, palette mapping,
scaling, and exact source-cuff compositing are alignment operations only. No
production sprite, rig, generator, or engine is touched.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont, ImageOps
from scipy import ndimage

ROOT = Path(__file__).resolve().parents[4]
OUT = Path(__file__).resolve().parent
BODY = ROOT / "characters/xiaoxun/forms/chibi/sprites/body_full.png"
AI_TRIALS = {
    "left": OUT / "mitten_left_art_trial_04.png",
    "right": OUT / "mitten_right_art_trial_05.png",
}
BOXES = {"left": (43, 846, 132, 938), "right": (435, 846, 524, 938)}
CUFF_EDGES = {
    "left": [(43, 878), (61, 878), (73, 879), (84, 883), (94, 889), (105, 895), (116, 899), (132, 900)],
    "right": [(435, 890), (446, 893), (457, 896), (469, 898), (479, 896), (489, 891), (500, 888), (524, 888)],
}
PALETTE = {
    "skin": (252, 228, 216),
    "skin_shadow": (232, 184, 168),
    "outline": (90, 90, 110),
    "highlight": (255, 250, 246),
}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def largest_component(mask: np.ndarray) -> np.ndarray:
    labels, _ = ndimage.label(mask)
    counts = np.bincount(labels.ravel())
    counts[0] = 0
    return labels == int(counts.argmax())


def extract_ai_hand(ai_path: Path) -> tuple[Image.Image, dict]:
    src = Image.open(ai_path).convert("RGB")
    rgb = np.asarray(src).astype(np.int16)
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    # Warm-pink/peach interior from each AI art; largest component is its hand.
    raw_skin = (r > 175) & (g > 100) & (g < 240) & (b > 70) & (r > g * 1.03) & (g > b * 1.02)
    skin = largest_component(raw_skin)
    near = ndimage.binary_dilation(skin, iterations=22)
    # Keep the muted-plum outline adjacent to that skin component; ignore cuff/background.
    line = (r < 170) & (g < 130) & (b < 180) & (r >= g) & ((b - g) > 10) & near
    silhouette = ndimage.binary_closing(skin | line, structure=np.ones((3, 3), dtype=bool))
    silhouette = ndimage.binary_fill_holes(largest_component(silhouette))
    ys, xs = np.where(silhouette)
    if not len(xs):
        raise RuntimeError(f"No AI mitten silhouette found in {ai_path.name}")
    pad = 3
    x0, y0 = max(0, int(xs.min()) - pad), max(0, int(ys.min()) - pad)
    x1, y1 = min(src.width, int(xs.max()) + 1 + pad), min(src.height, int(ys.max()) + 1 + pad)
    mask = silhouette[y0:y1, x0:x1]
    core = skin[y0:y1, x0:x1]
    rgb_crop = rgb[y0:y1, x0:x1]
    lum = 0.2126 * rgb_crop[..., 0] + 0.7152 * rgb_crop[..., 1] + 0.0722 * rgb_crop[..., 2]
    lo, hi = np.percentile(lum[core], [5, 95])
    t = np.clip((lum - lo) / max(hi - lo, 1), 0, 1)
    sh = np.asarray(PALETTE["skin_shadow"], dtype=np.float32)
    base = np.asarray(PALETTE["skin"], dtype=np.float32)
    high = np.asarray(PALETTE["highlight"], dtype=np.float32)
    colors = sh[None, None, :] * (1 - t[..., None]) + base[None, None, :] * t[..., None]
    hmix = np.clip((t - 0.78) / 0.22, 0, 1)[..., None]
    colors = colors * (1 - hmix) + high[None, None, :] * hmix
    out = np.zeros((y1 - y0, x1 - x0, 4), dtype=np.uint8)
    out[..., :3] = np.clip(colors, 0, 255).astype(np.uint8)
    out[line[y0:y1, x0:x1], :3] = PALETTE["outline"]
    alpha = Image.fromarray((mask * 255).astype(np.uint8), "L").filter(ImageFilter.GaussianBlur(0.35))
    out[..., 3] = np.asarray(alpha)
    hand = Image.fromarray(out, "RGBA")
    info = {
        "ai_source_file": ai_path.name,
        "ai_source_sha256": sha(ai_path),
        "ai_source_bbox_xyxy": [x0, y0, x1, y1],
        "ai_source_hand_size": list(hand.size),
    }
    return hand, info


def cuff_mask(side: str) -> Image.Image:
    box = BOXES[side]
    width, height = box[2] - box[0], box[3] - box[1]
    scale = 4
    edge = [((x - box[0]) * scale, (y - box[1]) * scale) for x, y in CUFF_EDGES[side]]
    mask_hi = Image.new("L", (width * scale, height * scale), 0)
    ImageDraw.Draw(mask_hi).polygon(
        [(0, 0), (width * scale, 0), (width * scale, edge[-1][1])] + edge[::-1],
        fill=255,
    )
    return mask_hi.resize((width, height), Image.Resampling.LANCZOS)


def source_cuff(body: Image.Image, side: str) -> Image.Image:
    crop = body.crop(BOXES[side]).convert("RGBA")
    return Image.composite(crop, Image.new("RGBA", crop.size), cuff_mask(side))


def fit_hand(hand: Image.Image, side: str) -> Image.Image:
    target_h = 65
    target_w = max(1, round(hand.width * target_h / hand.height))
    resized = hand.resize((target_w, target_h), Image.Resampling.LANCZOS)
    layer = Image.new("RGBA", (89, 92), (0, 0, 0, 0))
    center_x = {"left": 46.5, "right": 38.5}[side]
    x = round(center_x - target_w / 2)
    layer.alpha_composite(resized, (x, 14))
    return layer


def make_variant(body: Image.Image, side: str, base_hand: Image.Image) -> Image.Image:
    local_hand = base_hand.copy()
    # Clip generated wrist contours to a measured 1px underlap at the source cuff
    # opening, then put the exact source cuff pixels over that insertion.
    seam = cuff_mask(side).filter(ImageFilter.MinFilter(3))
    visible = ImageOps.invert(seam)
    local_hand.putalpha(ImageChops.multiply(local_hand.getchannel("A"), visible))
    local_hand.alpha_composite(source_cuff(body, side))
    return local_hand


def remove_source_hand(crop: Image.Image) -> Image.Image:
    a = np.asarray(crop.convert("RGBA")).copy()
    r, g, b, alpha = [a[..., i].astype(np.int16) for i in range(4)]
    skin = (alpha > 24) & (r > 200) & (g > 150) & (b > 130) & ((r - b) < 90)
    erase = Image.fromarray((skin * 255).astype(np.uint8), "L").filter(ImageFilter.MaxFilter(5))
    cut = np.asarray(erase) > 0
    a[cut, 3] = 0
    a[cut, :3] = 0
    return Image.fromarray(a.astype(np.uint8), "RGBA")


def main() -> None:
    body = Image.open(BODY).convert("RGBA")
    variants: dict[str, Image.Image] = {}
    side_metrics: dict[str, dict] = {}
    for side in BOXES:
        hand, info = extract_ai_hand(AI_TRIALS[side])
        variants[side] = make_variant(body, side, fit_hand(hand, side))
        side_metrics[side] = info

    preview = body.copy()
    for side, box in BOXES.items():
        preview.paste(remove_source_hand(body.crop(box)), (box[0], box[1]))
        preview.alpha_composite(variants[side], (box[0], box[1]))
        variants[side].save(OUT / f"mitten_{side}_ai_fit_wip.png")
    preview.save(OUT / "body_full_ai_mitten_preview_wip.png")

    canvas = Image.new("RGB", (1500, 1000), (247, 246, 243))
    d = ImageDraw.Draw(canvas)
    try:
        title = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 24)
        small = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 15)
    except OSError:
        title = small = ImageFont.load_default()
    d.text((28, 22), "XIAOXUN CHIBI · AI MITTEN FIT STUDY · WIP / NOT PRODUCTION", font=title, fill=(50, 44, 62))
    d.text((28, 59), "Independent AI hand trials 04/05, palette-fitted under exact Chibi source cuffs; both remain unapproved.", font=small, fill=(74, 68, 83))
    for i, (fig, label) in enumerate(((body.copy(), "source body_full"), (preview.copy(), "AI hand fit preview"))):
        fig.thumbnail((155, 390), Image.Resampling.LANCZOS)
        bg = Image.new("RGBA", fig.size, (236, 235, 238, 255))
        bg.alpha_composite(fig)
        x = 35 + i * 180
        canvas.paste(bg.convert("RGB"), (x, 130))
        d.text((x, 530), label, font=small, fill=(74, 68, 83))
    for i, side in enumerate(("left", "right")):
        x = 430 + i * 510
        d.text((x, 112), f"{side} · original small vs fitted mitten", font=title, fill=(50, 44, 62))
        for row, art in enumerate((body.crop(BOXES[side]), variants[side])):
            art = art.resize((356, 368), Image.Resampling.NEAREST)
            checker = Image.new("RGBA", art.size, (0, 0, 0, 0))
            cd = ImageDraw.Draw(checker)
            cell = 32
            for yy in range(0, art.height, cell):
                for xx in range(0, art.width, cell):
                    fill = (224, 222, 228, 255) if (xx // cell + yy // cell) % 2 == 0 else (244, 243, 246, 255)
                    cd.rectangle((xx, yy, xx + cell - 1, yy + cell - 1), fill=fill)
            checker.alpha_composite(art)
            canvas.paste(checker.convert("RGB"), (x, 150 + row * 390))
            d.text((x, 150 + row * 390 + 372), "small source" if row == 0 else "AI-fit WIP", font=small, fill=(74, 68, 83))
    d.text((430, 940), "No production paths touched; seam, line style, proportions and pose fit still need review.", font=small, fill=(116, 52, 56))
    canvas.save(OUT / "hand_style_ai_candidate_board_wip.png")

    metrics = {
        "status": "isolated_ai_art_candidate_wip_not_production",
        "ai_trials": side_metrics,
        "source_body_full_sha256": sha(BODY),
        "source_cuff_overlay": "Original Chibi source cuff pixels composited over each side's AI hand at recorded body_full edge",
        "fitting": {
            "target_height_px": 65,
            "aspect_ratio_preserved": True,
            "right_hand": "independently generated trial 05; not mirrored",
        },
        "palette_adjustment": "AI hand luminosity mapped to Chibi palette colors #FCE4D8, #E8B8A8, #5A5A6E, #FFFAF6",
        "limits": [
            "AI trials 04 and 05 changed cuff geometry; their cuffs were not used",
            "fitted hand silhouettes remain unapproved for Chibi style/identity and are not production textures",
            "the user-marked screenshot was a shape cue only, never copied, cropped, or used as texture",
            "no Teen hand asset used",
            "no production sprite, rig, generator, or engine changed",
            "cuff seam, line style, proportions and C-engine fit remain unverified",
        ],
        "files": {},
    }
    names = ["mitten_left_ai_fit_wip.png", "mitten_right_ai_fit_wip.png", "body_full_ai_mitten_preview_wip.png", "hand_style_ai_candidate_board_wip.png"]
    for name in names:
        metrics["files"][name] = sha(OUT / name)
    (OUT / "mitten_ai_fit_metrics.json").write_text(json.dumps(metrics, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("wrote isolated fitted AI hand candidates; not production art")


if __name__ == "__main__":
    main()
