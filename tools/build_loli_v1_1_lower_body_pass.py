#!/usr/bin/env python3
"""Create a lower-body-visible source-pixel pass from the approved v1.1 ref.

This adds skirt, left/right leg skin, socks and shoes to the current WIP stack.
It does not hand-paint hidden overlaps and is not Cubism-ready art.
"""
from __future__ import annotations

import hashlib
import json
import zipfile
from io import BytesIO
from pathlib import Path
from xml.etree.ElementTree import Element, SubElement, tostring

import cv2
import numpy as np
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "characters/xiaoxun/design/loli_live2d_v1/authoring_v1_1"
SOURCE = BASE / "reference_v1_1_alpha_edge_connected.png"
PREVIOUS = BASE / "authoring_pass_04"
OUT = BASE / "authoring_pass_05"
SIZE = (1280, 1920)
SCALE = 4

# Native-coordinate silhouettes traced on the approved 1280x1920 reference.
SKIRT = [(440,1090),(825,1090),(838,1120),(847,1150),(844,1172),(831,1184),(807,1190),(782,1194),(757,1196),(731,1200),(705,1204),(675,1206),(645,1207),(615,1205),(588,1201),(561,1198),(535,1195),(510,1192),(484,1189),(461,1184),(445,1176),(437,1158),(439,1130)]
LEG_L = [(478,1193),(603,1193),(625,1210),(622,1240),(615,1280),(608,1320),(603,1360),(599,1400),(600,1435),(606,1465),(614,1495),(610,1514),(500,1514),(494,1495),(500,1460),(507,1420),(510,1380),(506,1340),(500,1300),(493,1260),(488,1225)]
SOCK_L = [(500,1500),(605,1500),(610,1535),(610,1580),(608,1625),(603,1665),(594,1700),(585,1724),(574,1735),(545,1737),(528,1725),(518,1695),(510,1660),(505,1620),(501,1580)]
SHOE_L = [(520,1716),(578,1716),(592,1725),(603,1747),(610,1780),(616,1815),(622,1844),(618,1857),(604,1868),(580,1875),(553,1875),(532,1870),(516,1859),(508,1845),(510,1822),(514,1788),(517,1750)]

# Add antialiased polygons without ringing beyond the manually traced boundaries.
def polygon(points: list[tuple[int,int]]) -> np.ndarray:
    im = Image.new("L", (SIZE[0]*SCALE, SIZE[1]*SCALE), 0)
    d = ImageDraw.Draw(im)
    d.polygon([(x*SCALE,y*SCALE) for x,y in points], fill=255)
    return np.asarray(im.resize(SIZE, Image.Resampling.BOX), dtype=np.uint8)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def png_bytes(image: Image.Image) -> bytes:
    stream = BytesIO(); image.save(stream, format="PNG", optimize=True); return stream.getvalue()


def save_layer_review_board(layer_images: list[tuple[str, Image.Image, str]]) -> None:
    """Create a reproducible isolated-layer contact board over checkerboard."""
    cols, cell_w, cell_h, margin, label_h = 3, 300, 205, 12, 24
    rows = (len(layer_images) + cols - 1) // cols
    board = Image.new("RGB", (cols*cell_w + (cols+1)*margin, rows*cell_h + (rows+1)*margin), (31, 34, 39))
    draw = ImageDraw.Draw(board)
    tile_w, tile_h = cell_w - 2*margin, cell_h - label_h - 2*margin
    checker = Image.new("RGBA", (tile_w, tile_h), (0, 0, 0, 0))
    cd = ImageDraw.Draw(checker)
    step = 12
    for yy in range(0, tile_h, step):
        for xx in range(0, tile_w, step):
            color = (82, 85, 91, 255) if ((xx//step + yy//step) % 2) else (45, 48, 54, 255)
            cd.rectangle((xx, yy, min(xx+step-1,tile_w-1), min(yy+step-1,tile_h-1)), fill=color)
    for i, (name, layer, _group) in enumerate(layer_images):
        col, row = i % cols, i // cols
        x, y = margin + col*cell_w, margin + row*cell_h
        alpha = layer.getchannel("A")
        bbox = alpha.getbbox()
        draw.text((x, y), f"{name} {bbox}", fill=(242, 244, 248))
        tile = checker.copy()
        if bbox:
            crop = layer.crop(bbox)
            crop.thumbnail((tile_w-8, tile_h-8), Image.Resampling.LANCZOS)
            tile.alpha_composite(crop, ((tile_w-crop.width)//2, (tile_h-crop.height)//2))
        board.paste(tile.convert("RGB"), (x, y+label_h))
    board.save(OUT/"layer_review_board.jpg", quality=94, optimize=True)


def connected_largest(mask: np.ndarray) -> np.ndarray:
    n, labels, stats, _ = cv2.connectedComponentsWithStats((mask>0).astype(np.uint8), 8)
    out = np.zeros(mask.shape, dtype=np.uint8)
    if n > 1:
        i = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA])); out[labels==i] = 255
    return out


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    ref = Image.open(SOURCE).convert("RGBA")
    rgba = np.asarray(ref).copy()
    h,w = rgba.shape[:2]
    alpha = rgba[...,3]

    # Carry the already-authored visible layers forward, not the old flat base.
    previous_manifest = json.loads((PREVIOUS/"layer_manifest.json").read_text(encoding="utf-8"))
    old_layers: dict[str, Image.Image] = {}
    old_parts = {p["name"]:p for p in previous_manifest["parts"]}
    for name in ("JacketSleeve_Teal_L","JacketSleeve_Teal_R", "EyeWhite_L","EyeBall_L","Eyelash_L","Brow_L","EyeWhite_R","EyeBall_R","Eyelash_R","Brow_R","Nose","Mouth_Closed","Whale_Clip"):
        old_layers[name] = Image.open(PREVIOUS/old_parts[name]["file"]).convert("RGBA")

    # Lower body material selections. Hard masks preserve the actual source
    # pixels; hidden areas under the selected material are algorithmic WIP fill.
    skirt_poly = polygon(SKIRT)
    blue = rgba[...,:3].astype(np.int16)
    skirt_color = (blue[...,2] > blue[...,0]+18) & (blue[...,2] < 185) & (blue[...,1] < 150) & (alpha>0)
    skirt = ((skirt_poly>127) & skirt_color).astype(np.uint8)*255

    leg_polys = {}
    for side in ("L","R"):
        points = LEG_L if side=="L" else [(1280-x,y) for x,y in LEG_L]
        leg_polys[f"Leg_Skin_{side}"] = polygon(points)

    sock_masks={}
    shoe_masks={}
    for side in ("L","R"):
        mirror = lambda pts: pts if side=="L" else [(1280-x,y) for x,y in pts]
        sock_masks[f"Sock_{side}"] = (polygon(mirror(SOCK_L))>127).astype(np.uint8)*255
        shoe_masks[f"Shoe_{side}"] = (polygon(mirror(SHOE_L))>127).astype(np.uint8)*255
        # Shoe is in front of sock; assign shared ankle pixels to the shoe layer.
        sock_masks[f"Sock_{side}"][shoe_masks[f"Shoe_{side}"]>0] = 0

    # Source alpha limits all traced layers; transparent exterior is never keyed by RGB.
    leg_masks={}
    for side in ("L","R"):
        name=f"Leg_Skin_{side}"
        m=(leg_polys[name]>127)&(alpha>0)&(skirt==0)&(sock_masks[f"Sock_{side}"]==0)
        leg_masks[name]=m.astype(np.uint8)*255
    new_masks = {"Leg_Skin_L":leg_masks["Leg_Skin_L"], "Leg_Skin_R":leg_masks["Leg_Skin_R"], "Skirt":skirt,
                 "Sock_L":sock_masks["Sock_L"], "Sock_R":sock_masks["Sock_R"], "Shoe_L":shoe_masks["Shoe_L"], "Shoe_R":shoe_masks["Shoe_R"]}
    for name in new_masks:
        new_masks[name] = ((new_masks[name].astype(np.uint16)*alpha.astype(np.uint16))//255).astype(np.uint8)
        if np.count_nonzero(new_masks[name]>127)<500:
            raise SystemExit(f"lower-body selection unexpectedly small: {name}")

    # Render order is bottom to top: legs, skirt, socks, shoes, sleeves, face.
    groups = [
        ("Leg_Skin_L","10 Lower body / legs"),("Leg_Skin_R","10 Lower body / legs"),("Skirt","10 Lower body / skirt"),
        ("Sock_L","10 Lower body / socks"),("Sock_R","10 Lower body / socks"),("Shoe_L","10 Lower body / shoes"),("Shoe_R","10 Lower body / shoes"),
        ("JacketSleeve_Teal_L","20 Body / visible sleeve color"),("JacketSleeve_Teal_R","20 Body / visible sleeve color"),
        ("EyeWhite_L","30 Face / left eye"),("EyeBall_L","30 Face / left eye"),("Eyelash_L","30 Face / left eye"),("Brow_L","30 Face"),
        ("EyeWhite_R","30 Face / right eye"),("EyeBall_R","30 Face / right eye"),("Eyelash_R","30 Face / right eye"),("Brow_R","30 Face"),
        ("Nose","30 Face"),("Mouth_Closed","30 Face"),("Whale_Clip","40 Hair accessory")]
    all_masks={**new_masks}
    for name,layer in old_layers.items():
        all_masks[name]=np.asarray(layer.getchannel("A"),dtype=np.uint8)
    masks={name:all_masks[name] for name,_ in groups}
    union=np.zeros((h,w),dtype=np.uint8)
    for m in masks.values(): union=np.maximum(union,m)
    cleanup=(union>127).astype(np.uint8)*255
    cleanup[alpha==0]=0
    bgr=cv2.cvtColor(rgba[...,:3],cv2.COLOR_RGB2BGR)
    filled=cv2.inpaint(bgr,cleanup,4,cv2.INPAINT_TELEA)
    base_rgba=rgba.copy();base_rgba[...,:3]=cv2.cvtColor(filled,cv2.COLOR_BGR2RGB)
    base_rgba[...,3]=((alpha.astype(np.uint16)*(255-union.astype(np.uint16)))//255).astype(np.uint8)
    base=Image.fromarray(base_rgba,"RGBA");base.save(OUT/"Base_Figure_LowerBodyUnderpaint_WIP.png",optimize=True)

    layer_images=[];manifest_parts=[]
    for name,group in groups:
        if name in old_layers:
            layer=old_layers[name]
        else:
            arr=rgba.copy();arr[...,3]=masks[name]
            layer=Image.fromarray(arr,"RGBA")
        layer.save(OUT/f"{name}.png",optimize=True)
        layer_images.append((name,layer,group))
        source_kind=("carried from pass04 source-visible WIP" if name in old_layers else "native-coordinate polygon/ROI visible-pixel selection")
        manifest_parts.append({"name":name,"file":f"{name}.png","group":group,"state":"source-visible cutout WIP; not hand-painted/rig-ready","selection":source_kind,"canvas_px":[w,h]})
    save_layer_review_board(layer_images)

    composite=base.copy()
    for _,part,_ in layer_images: composite.alpha_composite(part)
    composite.save(OUT/"authoring_pass_05_composite.png",optimize=True)
    ref.save(OUT/"reference_v1_1_alpha_edge_connected.png",optimize=True)
    diff=np.abs(np.asarray(composite).astype(np.int16)-np.asarray(ref).astype(np.int16)).astype(np.uint8)
    Image.fromarray(diff,"RGBA").save(OUT/"reconstruction_diff.png",optimize=True)
    changed=int(np.count_nonzero(np.any(diff[...,:3]>2,axis=2))); maxdiff=int(diff[...,:3].max())

    ora=OUT/"xiaoxun_loli_v1_1_authoring_pass_05.ora"
    root=Element("image",{"version":"0.0.1","w":str(w),"h":str(h),"name":"Xiaoxun Loli v1.1 - authoring pass 05 WIP","xres":"72","yres":"72"})
    stack=SubElement(root,"stack")
    SubElement(stack,"layer",{"name":"NEW v1.1 full reference - locked, hidden","src":"data/reference.png","opacity":"0.55","visibility":"hidden","composite-op":"svg:src-over","x":"0","y":"0"})
    group=SubElement(stack,"stack",{"name":"10 Lower body / 20 Body / 30 Face / 40 Accessory - source-visible WIP","opacity":"1.0","visibility":"visible","composite-op":"svg:src-over"})
    parts_bytes={}
    for i,(name,layer,_) in enumerate(layer_images): parts_bytes[f"data/part_{i:02d}.png"]=png_bytes(layer)
    for i in reversed(range(len(layer_images))):
        name,_,_=layer_images[i]
        SubElement(group,"layer",{"name":name,"src":f"data/part_{i:02d}.png","opacity":"1.0","visibility":"visible","composite-op":"svg:src-over","x":"0","y":"0"})
    SubElement(stack,"layer",{"name":"00 Flat figure with approximate underpaint (WIP)","src":"data/base.png","opacity":"1.0","visibility":"visible","composite-op":"svg:src-over","x":"0","y":"0"})
    with zipfile.ZipFile(ora,"w") as z:
        z.writestr("mimetype","image/openraster",compress_type=zipfile.ZIP_STORED)
        files={"data/reference.png":png_bytes(ref),"data/base.png":png_bytes(base),**parts_bytes,
               "stack.xml":tostring(root,encoding="utf-8",xml_declaration=True),"mergedimage.png":png_bytes(composite)}
        for name,data in files.items(): z.writestr(name,data,compress_type=zipfile.ZIP_DEFLATED)

    manifest={"status":"WIP source-visible split from selected v1.1; not complete art, not PSD/PSB, not Cubism","source":"../reference_v1_1_alpha_edge_connected.png","source_sha256":digest(SOURCE),"canvas_px":[w,h],"ora_file":ora.name,
              "parts":manifest_parts,"reconstruction_check":{"pixels_changed_over_2_rgb_levels":changed,"max_channel_difference":maxdiff,"interpretation":"source-pixel static reassembly only; no motion/art quality claim"},
              "known_gaps":["Only lower-body visible source regions were added this round; jacket front, shirt, hair, neck/head outline, arms/hands, socks/shoes hidden interiors remain incomplete or source-only.","Leg/skirt/sock/shoe cutouts have no hidden overlap paint; underpaint is algorithmic interpolation.","Eye/face layers and visible teal sleeve regions are carried forward from pass04 WIP; their masks are not art-approved.","No PSD/PSB or official Cubism Editor project/export/runtime validation."]}
    mp=OUT/"layer_manifest.json";mp.write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    files=sorted(p for p in OUT.iterdir() if p.is_file() and p.name!="SHA256SUMS.txt")
    (OUT/"SHA256SUMS.txt").write_text("".join(f"{digest(p)}  {p.name}\n" for p in files),encoding="utf-8")
    print(json.dumps({"ora":ora.name,"source_visible_parts":len(layer_images),"reconstruction_changed_pixels_over_2":changed,"max_rgb_difference":maxdiff,"status":manifest["status"]},ensure_ascii=False))
    return 0

if __name__=="__main__": raise SystemExit(main())
