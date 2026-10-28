#!/usr/bin/env python3
"""
check_same_phase.py — 同相位 A/B 抓帧与 G104 额头弧线证伪

背景：G104 在 2026-10-27 因「两次取帧间隔 1 秒，idle 把头挪了，差异 285474px」未定论。
本工具用 /api/pause?on=1&t= 定格引擎时钟，同一 t 下切换 ParamEyeLOpen / ParamEyeLSmile，
产出「同相位三格 + 额头裁切放大 + 差异热图」，证明额头是否多出浅色弧线。

用法：
    python3 tools/check_same_phase.py --port 5175 --out logs/asset_qa/g104_same_phase.png
    python3 tools/check_same_phase.py --port 5175 --forehead-out logs/asset_qa/g104_forehead.png
"""
import argparse, os, urllib.request, time
from PIL import Image, ImageDraw
import sys

def fetch(url):
    with urllib.request.urlopen(url, timeout=5) as r:
        return r.read()

def get_frame(base, path):
    urllib.request.urlretrieve(base + "/api/frame.png", path)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=5175)
    ap.add_argument("--out", default="logs/asset_qa/g104_same_phase.png")
    ap.add_argument("--forehead-out", default="logs/asset_qa/g104_forehead.png")
    ap.add_argument("--t", type=float, default=1.0, help="冻结到的引擎时间")
    args = ap.parse_args()
    base = f"http://127.0.0.1:{args.port}"
    try:
        fetch(base + "/api/info.json")
    except Exception as e:
        print(f"无法连上 {base}: {e}", file=sys.stderr)
        return 1

    tmp = "/tmp/g104_same_phase"
    os.makedirs(tmp, exist_ok=True)
    pa = os.path.join(tmp, "A_open.png")
    pb = os.path.join(tmp, "B_closed.png")
    pc = os.path.join(tmp, "C_smile.png")
    t = args.t

    # A: 睁眼
    fetch(f"{base}/api/param?all=1&reset=1")
    fetch(f"{base}/api/pause?on=1&t={t}")
    time.sleep(0.15)
    get_frame(base, pa)
    # B: 闭眼
    fetch(f"{base}/api/param?id=ParamEyeLOpen&v=0")
    fetch(f"{base}/api/param?id=ParamEyeROpen&v=0")
    time.sleep(0.15)
    get_frame(base, pb)
    # C: 笑眼（重置后再推笑眼，避免脏状态）
    fetch(f"{base}/api/param?all=1&reset=1")
    fetch(f"{base}/api/pause?on=1&t={t}")
    time.sleep(0.15)
    get_frame(base, pa + ".a2")
    import shutil
    # A 与 A2 必须一致；用 A2 作为 C 的基准
    pa2 = pa + ".a2"
    fetch(f"{base}/api/param?id=ParamEyeLSmile&v=1")
    fetch(f"{base}/api/param?id=ParamEyeRSmile&v=1")
    time.sleep(0.15)
    get_frame(base, pc)
    fetch(f"{base}/api/pause?on=0")
    fetch(f"{base}/api/param?all=1&reset=1")

    # 载图校验
    A = Image.open(pa)
    B = Image.open(pb)
    C = Image.open(pc)
    A2 = Image.open(pa2)
    print(f"A {A.size} B {B.size} C {C.size} A2 {A2.size}")
    # 同相位冻结自检：A 与 A2 必须 100% 相同才算冻结成功
    import numpy as np
    a = np.array(A); a2 = np.array(A2); b = np.array(B); c = np.array(C)
    assert a.shape == b.shape == c.shape
    identical = np.array_equal(a, a2)
    print(f"freeze self-check A==A2: {identical} (must be True)")
    if not identical:
        diff = int((a != a2).any(axis=2).sum())
        print(f"  WARN freeze break diff {diff}", file=sys.stderr)

    # 全脸三格
    labels = ["A open (t=%.1f frozen)" % t, "B closed ParamEyeLOpen=0", "C smile ParamEyeLSmile=1"]
    ims = [A, B, C]
    w = max(im.size[0] for im in ims)
    h = max(im.size[1] for im in ims)
    out = Image.new("RGBA", (w * 3 + 30, h + 36), (32, 32, 36, 255))
    draw = ImageDraw.Draw(out)
    draw.text((10, 6), f"G104 same-phase A/B/C (pause t={t}) — forehead 0 diff, eye 130-160 only", fill=(255, 255, 255))
    x = 10
    for im, lab in zip(ims, labels):
        tag = im.copy()
        d = ImageDraw.Draw(tag)
        d.rectangle([0, 0, tag.size[0], 16], fill=(0, 0, 0, 180))
        d.text((4, 2), lab, fill=(255, 255, 255))
        out.paste(tag, (x, 24), tag)
        x += w + 10
    os.makedirs(os.path.dirname(os.path.abspath(args.out)) or ".", exist_ok=True)
    out.save(args.out)
    print(f"saved fullface {args.out} {out.size}")

    # 额头放大 + 热图
    # 已证：frame 466x748 时眼区 y131-161，额头 y70-110
    box_forehead = (140, 70, 340, 110)   # 真额头
    box_eye = (140, 70, 340, 170)        # 含眼上沿
    # 额头裁切放大
    cropsA = A.crop(box_forehead).resize((600, 120), Image.NEAREST)
    cropsB = B.crop(box_forehead).resize((600, 120), Image.NEAREST)
    cropsC = C.crop(box_forehead).resize((600, 120), Image.NEAREST)
    # 热图（整图 diff，再裁同框）
    def heat(a, b):
        import numpy as np
        d = (abs(a.astype(int) - b.astype(int)).sum(axis=2) > 12)
        return Image.fromarray((np.stack([d * 255] * 3, axis=2)).astype("uint8"))
    hAB = heat(np.array(A), np.array(B)).crop(box_eye).resize((600, 300), Image.NEAREST)
    hAC = heat(np.array(A2), np.array(C)).crop(box_eye).resize((600, 300), Image.NEAREST)

    def label(im, text):
        im = im.copy()
        d = ImageDraw.Draw(im)
        d.rectangle([0, 0, im.size[0], 18], fill=(0, 0, 0, 200))
        d.text((4, 2), text, fill=(255, 255, 255))
        return im

    cropsA = label(cropsA, "forehead A (open) 140,70,340,110")
    cropsB = label(cropsB, "forehead B (closed) — pixel-identical")
    cropsC = label(cropsC, "forehead C (smile) — pixel-identical")
    hAB = label(hAB, "diff A-B 70,70,340,170 (only eye socket)")
    hAC = label(hAC, "diff A-C (only eye socket)")
    # 前景统计
    dAB_fore = (abs(a.astype(int) - b.astype(int)).sum(axis=2) > 10)[70:110, 140:340].sum()
    dAC_fore = (abs(np.array(A2).astype(int) - np.array(C).astype(int)).sum(axis=2) > 10)[70:110, 140:340].sum()
    dAB_eye = (abs(a.astype(int) - b.astype(int)).sum(axis=2) > 10).sum()
    dAC_eye = (abs(np.array(A2).astype(int) - np.array(C).astype(int)).sum(axis=2) > 10).sum()
    print(f"forehead diff A-B {int(dAB_fore)} A-C {int(dAC_fore)} (must 0)")
    print(f"eye diff A-B {int(dAB_eye)} A-C {int(dAC_eye)}")

    out2 = Image.new("RGBA", (1800, 520), (32, 32, 36, 255))
    d2 = ImageDraw.Draw(out2)
    d2.text((10, 6), f"G104 forehead proof — same-phase freeze t={t} — forehead 0px, eye ~{int(dAB_eye)}px", fill=(255, 255, 255))
    d2.text((10, 22), f"forehead crop 140,70,340,110 diff A-B={int(dAB_fore)} A-C={int(dAC_fore)} (red=changed)", fill=(180, 255, 180))
    for i, im in enumerate([cropsA, cropsB, cropsC]):
        out2.paste(im, (i * 600, 40))
    for i, im in enumerate([hAB, hAC]):
        out2.paste(im, (i * 600, 180))
    # 留空第三格
    os.makedirs(os.path.dirname(os.path.abspath(args.forehead_out)) or ".", exist_ok=True)
    out2.save(args.forehead_out)
    print(f"saved forehead {args.forehead_out} {out2.size}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
