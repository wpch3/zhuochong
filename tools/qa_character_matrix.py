#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""角色进度盘：把「谁有素材、谁只有契约」画成一张能一眼看懂的证据图（T66.23）。

为什么要有这张图
----------------
这一轮改的全是契约与闸，没有美术 —— 恰恰这种改动最容易被"看起来都通过了"骗过去。
所以要一张**用眼睛看**的图：八个角色排成一行一行，有素材的那一行放**真实素材的缩略图**，
没有素材的那一行就是空白 + 一行 `no sprites`。空白本身就是结论。

★ 图里不放任何画出来的角色形状。有素材就贴真图，没素材就留白 —— 否则这张"证据图"
  自己就成了假素材（用户红线）。文字只用 ASCII，因为沙箱没有中文字体。
"""
import argparse
import json
import os
import sys

from PIL import Image, ImageDraw, ImageFont

FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"
FONT_B = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf"
THUMB = (132, 200)


def load(p):
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def rows(root):
    out = []
    cdir = os.path.join(root, "characters")
    for cid in sorted(os.listdir(cdir)):
        d = os.path.join(cdir, cid)
        if not os.path.isdir(d):
            continue
        r = {"id": cid, "status": "-", "bones": 0, "sockets": 0,
             "forms": [], "planned": [], "thumb": None}
        skp = os.path.join(d, "skeleton.json")
        if os.path.isfile(skp):
            sk = load(skp)
            r["status"] = sk.get("status", "full")
            r["bones"] = len(sk.get("bones", []))
            r["sockets"] = sum(1 for b in sk.get("bones", []) if b.get("kind") == "socket")
        fp = os.path.join(d, "forms.json")
        if os.path.isfile(fp):
            for e in load(fp).get("forms", []):
                (r["forms"] if e.get("status") == "ready" else r["planned"]).append(e["id"])
        fdir = os.path.join(d, "forms")
        ready = sorted(x for x in (os.listdir(fdir) if os.path.isdir(fdir) else [])
                       if os.path.isfile(os.path.join(fdir, x, "rig.json")))
        r["forms"] = ready or r["forms"]
        # 缩略图：有 rig 的形态里挑第一个有 body_full.png 的（真素材）
        for f in ready:
            p = os.path.join(fdir, f, "sprites", "body_full.png")
            if os.path.isfile(p):
                r["thumb"] = (f, p)
                break
        out.append(r)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    ap.add_argument("--out", default="logs/asset_qa/t66_23_character_matrix.png")
    ap.add_argument("--scale", type=int, default=2, help="整体放大倍数（小图看不清就放大）")
    a = ap.parse_args()
    root = os.path.abspath(a.root)
    rs = rows(root)

    f1 = ImageFont.truetype(FONT, 15)
    f2 = ImageFont.truetype(FONT_B, 17)
    rowh = THUMB[1] + 18
    W, H = 760, 58 + rowh * len(rs) + 40
    im = Image.new("RGBA", (W, H), (26, 28, 32, 255))
    g = ImageDraw.Draw(im)
    g.text((16, 12), "characters/ -- who has real sprites, who only has a contract",
           font=f2, fill=(238, 238, 238))
    g.text((16, 34), "T66.23  2026-10-26  (x2 zoom for reading; sprites are the real PNGs)",
           font=f1, fill=(150, 155, 165))

    y = 58
    for r in rs:
        has = bool(r["thumb"])
        box = [16, y, 16 + THUMB[0], y + THUMB[1]]
        g.rectangle(box, outline=(70, 74, 82) if not has else (90, 160, 110), width=2)
        if has:
            f, p = r["thumb"]
            sp = Image.open(p).convert("RGBA")
            sp.thumbnail((THUMB[0] - 8, THUMB[1] - 8), Image.LANCZOS)
            checker = Image.new("RGBA", box[2:], (40, 42, 48, 255))
            # 棋盘底，证明缩略图带 alpha（不是白底贴图）
            for cy in range(box[1] + 4, box[3] - 4, 10):
                for cx in range(box[0] + 4, box[2] - 4, 10):
                    if ((cx - box[0]) // 10 + (cy - box[1]) // 10) % 2:
                        checker.paste((58, 60, 68, 255), (cx, cy, cx + 10, cy + 10))
            im.paste(checker, (box[0] + 4, box[1] + 4))
            im.alpha_composite(sp, (box[0] + 4 + (THUMB[0] - 8 - sp.width) // 2,
                                    box[1] + 4 + (THUMB[1] - 8 - sp.height) // 2))
        else:
            g.line([box[0] + 6, box[1] + 6, box[2] - 6, box[3] - 6], fill=(70, 74, 82), width=1)
            g.line([box[0] + 6, box[3] - 6, box[2] - 6, box[1] + 6], fill=(70, 74, 82), width=1)
            g.text((box[0] + 24, box[1] + THUMB[1] // 2 - 10), "no sprites", font=f2,
                   fill=(200, 90, 90))

        tx = box[2] + 18
        col = (120, 220, 150) if has else (215, 175, 110)
        g.text((tx, y + 4), "%-9s %s" % (r["id"], r["status"]), font=f2, fill=col)
        g.text((tx, y + 30), "bones %2d   sockets %d" % (r["bones"], r["sockets"]),
               font=f1, fill=(200, 205, 215))
        g.text((tx, y + 52), "ready   : %s" % (", ".join(r["forms"]) or "-"),
               font=f1, fill=(200, 205, 215))
        g.text((tx, y + 74), "planned : %s" % (", ".join(r["planned"]) or "-"),
               font=f1, fill=(140, 145, 155))
        if not has:
            g.text((tx, y + 96), "status=contract_only -> todo in skeleton.json",
                   font=f1, fill=(215, 175, 110))
        g.line([16, y + rowh - 6, W - 16, y + rowh - 6], fill=(48, 50, 56), width=1)
        y += rowh

    n_has = sum(1 for r in rs if r["thumb"])
    g.text((16, H - 30), "%d/%d have real sprites   %d contract-only   -- blank is the point"
           % (n_has, len(rs), len(rs) - n_has), font=f1, fill=(200, 205, 215))
    if a.scale != 1:
        im = im.resize((W * a.scale, H * a.scale), Image.NEAREST)
    im = im.convert("RGB")
    out = os.path.join(root, a.out)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    im.save(out)
    print("[matrix] 写出 %s  (%dx%d, %d/%d 有素材)"
          % (os.path.relpath(out, root), im.width, im.height, n_has, len(rs)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
