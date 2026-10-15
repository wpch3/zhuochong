#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""upscale_sheet.py —— 把洋红底 design_sheet 做 2x 超分，给 T30.1 提供真正的高清基准。

为什么需要它
------------
T30.1 原来的说法是「按源图 1696x2528 重切」。2026-10-15 查下来**这个前提是错的**：

  · 真正的拆件基准是 `characters/<角色>/design/design_sheet_*.png`，**只有 1024x1536**，
    里面的人物是 500x1452。
  · 根目录那张 1696x2528 的 `小寻.png` 是**白底参考图 / LoRA 数据**（用户 2026-10-11 定的），
    而且实拍对比发现它**是另一个姿势和服装细节**（外套敞开度、手臂角度、衬衫领子都不同），
    不是 design_sheet 的高清版。换过去等于换造型 + rig 全部坐标作废。
  · 现行 `prepare_sprites.py` 只做了 0.889x 的轻微降采样（445x1292），
    取消它只能换来 +12.4% 像素 / **+7.8% 锐度** —— 实测对照图里肉眼勉强可辨，
    解决不了用户要的「放大到整个桌面仍清晰」。

所以真正的 2x 只能靠超分。用 Real-ESRGAN 的 anime 专用轻量模型
（RealESR-AnimeVideo-v3 x4，compact 架构，ONNX 只有 2.4MB，CPU 可跑），
超到 4x 再下采样到 2x（Real-ESRGAN 的常规用法，顺带降噪）。

2026-10-15 实测（沙箱 2 核 CPU，design_sheet_short 1024x1536）
--------------------------------------------------------------
  耗时            22.6 s（24 块 tile）
  几何倍率        2.0020x 宽 / 1.9993x 高（期望 2.0）
  bbox 原点偏差   (-1, 0) px —— 在 2x 坐标系下
  轮廓 IoU        0.9938
  前景灰度 NCC    0.9822   MAE 6.35/255
  锐度            +33.3%（对照：取消降采样只有 +7.8%）
  → 动手前定的判据是 NCC>0.97 且 IoU>0.97 才能直接换基准，**通过**。

  留证：logs/asset_qa/upscale_ab.png

注意：度量时**必须只比两边 alpha 都实心的像素**。第一版把透明区也算进去，
得到 NCC 0.921 / MAE 61.9 的"不通过"，差点把这条可行的路否掉。

模型怎么来
----------
不进仓库（它是工具依赖，不是素材）。首次运行会自动从 GitHub 拉：
  https://codeload.github.com/ntsc-rs-fan/RealESRGAN-AnimeVideo-v3-x4-ONNX/tar.gz/refs/heads/main
  （BSD 3-Clause；Real-ESRGAN 本体 BSD 3-Clause，xinntao/Real-ESRGAN）
缓存在 `--model-dir`（默认 `.cache/models/`，已在 .gitignore）。
沙箱只允许 github.com / codeload.github.com / api.github.com / pypi.org 等少数几个域，
**raw.githubusercontent.com 不在白名单**，所以只能走 codeload 的 tarball。

依赖：onnxruntime + pillow + numpy（和其它切件脚本一样走 ~/.imgenv）。

用法
----
  python3 tools/upscale_sheet.py --character xiaoxun --sheet design_sheet_short.png
  python3 tools/upscale_sheet.py --character xiaoxun --sheet design_sheet_short.png --factor 2 --check
"""
from __future__ import annotations

import argparse
import hashlib
import io
import os
import sys
import tarfile
import time
import urllib.request

MODEL_URL = ("https://codeload.github.com/ntsc-rs-fan/"
             "RealESRGAN-AnimeVideo-v3-x4-ONNX/tar.gz/refs/heads/main")
MODEL_NAME = "RealESR-AnimeVideo-v3_x4.onnx"
MODEL_SHA256 = "00ece3ac21c43ee31459216b5174b2cea0c5325044c5142aeb840f4890e175ff"
NATIVE_SCALE = 4          # 模型本身是 4x


def fetch_model(model_dir: str) -> str:
    """模型不进仓库，首次用时拉下来缓存。"""
    os.makedirs(model_dir, exist_ok=True)
    dst = os.path.join(model_dir, MODEL_NAME)
    if os.path.exists(dst) and os.path.getsize(dst) > 1_000_000:
        with open(dst, "rb") as fh:
            got = hashlib.sha256(fh.read()).hexdigest()
        if got == MODEL_SHA256:
            return dst
        print(f"[模型] 缓存校验不过（{got[:16]}… != {MODEL_SHA256[:16]}…），重新拉取")
    print(f"[模型] 本地没有，正在拉取 …\n       {MODEL_URL}")
    with urllib.request.urlopen(MODEL_URL, timeout=180) as r:
        blob = r.read()
    with tarfile.open(fileobj=io.BytesIO(blob), mode="r:gz") as tf:
        member = next((m for m in tf.getmembers()
                       if m.name.endswith(MODEL_NAME)), None)
        if member is None:
            print(f"[错误] tarball 里没有 {MODEL_NAME}", file=sys.stderr)
            sys.exit(2)
        f = tf.extractfile(member)
        assert f is not None
        data = f.read()
    got = hashlib.sha256(data).hexdigest()
    if got != MODEL_SHA256:
        print(f"[错误] 模型 sha256 对不上：{got}\n"
              f"       期望 {MODEL_SHA256}\n"
              "       上游换了文件就停下来人工确认，别拿不认识的权重去生成素材。",
              file=sys.stderr)
        sys.exit(2)
    with open(dst, "wb") as fh:
        fh.write(data)
    print(f"[模型] 已缓存 {dst}（{len(data):,} 字节，sha256 校验通过）")
    return dst


def upscale(sess, img_rgb, tile: int = 256, overlap: int = 16):
    """分块 4x 超分。

    为什么分块：整张 1024x1536 一次推理要几 GB 临时内存。
    为什么要 overlap：块边界上卷积拿不到邻域，直接拼会有接缝；
    多算 overlap 像素再裁掉就没有了（实测拼接处零可见接缝）。
    """
    import numpy as np
    from PIL import Image

    name = sess.get_inputs()[0].name
    a = np.asarray(img_rgb, dtype=np.float32) / 255.0
    h, w, _ = a.shape
    out = np.zeros((h * NATIVE_SCALE, w * NATIVE_SCALE, 3), dtype=np.float32)
    ny, nx = (h + tile - 1) // tile, (w + tile - 1) // tile
    t0, n = time.time(), 0
    for by in range(ny):
        for bx in range(nx):
            y0, x0 = by * tile, bx * tile
            y1, x1 = min(y0 + tile, h), min(x0 + tile, w)
            py0, px0 = max(0, y0 - overlap), max(0, x0 - overlap)
            py1, px1 = min(h, y1 + overlap), min(w, x1 + overlap)
            patch = a[py0:py1, px0:px1].transpose(2, 0, 1)[None]
            r = sess.run(None, {name: np.ascontiguousarray(patch)})[0][0]
            r = r.transpose(1, 2, 0)
            cy0, cx0 = (y0 - py0) * NATIVE_SCALE, (x0 - px0) * NATIVE_SCALE
            out[y0 * NATIVE_SCALE:y1 * NATIVE_SCALE,
                x0 * NATIVE_SCALE:x1 * NATIVE_SCALE] = \
                r[cy0:cy0 + (y1 - y0) * NATIVE_SCALE,
                  cx0:cx0 + (x1 - x0) * NATIVE_SCALE]
            n += 1
    print(f"[超分] {n} 块，{time.time() - t0:.1f}s")
    return Image.fromarray((np.clip(out, 0, 1) * 255 + 0.5).astype("uint8"), "RGB")


def verify(orig_path: str, new_path: str, factor: int) -> int:
    """换基准前必须过的闸：几何对得上、内容没被改掉。

    判据是动手前定的，不是看着结果凑的：
      轮廓 IoU > 0.97、前景灰度 NCC > 0.97、倍率误差 < 1%、bbox 原点偏差 <= 2px。
    低于任何一条，44 个部件的坐标就不能简单乘 factor，必须整套重对。
    """
    import numpy as np
    from PIL import Image
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import prepare_sprites as ps                      # noqa: E402

    def fg(p):
        im = ps.load_rgb(p)
        rgba, _ = ps.key_out(im, tol=60)
        return rgba, ps.bbox_of(np.asarray(rgba)[..., 3])

    o, bo = fg(orig_path)
    n, bn = fg(new_path)
    ow, oh = bo[2] - bo[0] + 1, bo[3] - bo[1] + 1
    nw, nh = bn[2] - bn[0] + 1, bn[3] - bn[1] + 1
    kx, ky = nw / ow, nh / oh
    dx, dy = bn[0] - bo[0] * factor, bn[1] - bo[1] * factor

    A = o.crop((bo[0], bo[1], bo[2] + 1, bo[3] + 1)).resize((ow, oh), Image.LANCZOS)
    B = n.crop((bn[0], bn[1], bn[2] + 1, bn[3] + 1)).resize((ow, oh), Image.LANCZOS)
    aA, aB = np.asarray(A), np.asarray(B)
    # ★ 只比两边都实心的像素。把透明区算进来会得到假的「不通过」（见文件头）。
    both = (aA[..., 3] > 200) & (aB[..., 3] > 200)
    gA = np.asarray(A.convert("L"), float)[both]
    gB = np.asarray(B.convert("L"), float)[both]
    ncc = float(((gA - gA.mean()) * (gB - gB.mean())).mean()
                / (gA.std() * gB.std() + 1e-9))
    mA, mB = aA[..., 3] > 128, aB[..., 3] > 128
    iou = float((mA & mB).sum() / max(1, (mA | mB).sum()))

    print(f"\n[验收] 人物 {ow}x{oh} -> {nw}x{nh}")
    rows = [
        ("倍率 x",      f"{kx:.4f}", abs(kx - factor) < factor * 0.01),
        ("倍率 y",      f"{ky:.4f}", abs(ky - factor) < factor * 0.01),
        ("bbox 原点偏差", f"({dx}, {dy}) px", abs(dx) <= 2 and abs(dy) <= 2),
        ("轮廓 IoU",    f"{iou:.4f}", iou > 0.97),
        ("前景 NCC",    f"{ncc:.4f}", ncc > 0.97),
    ]
    bad = 0
    for label, val, ok in rows:
        print(f"  {'通过' if ok else '不通过'}  {label:14s} {val}")
        bad += 0 if ok else 1
    print("  → " + ("可以直接换基准，部件坐标乘 factor 即可"
                    if not bad else "不能直接换，坐标要整套重对"))
    return bad


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--character", required=True)
    ap.add_argument("--sheet", required=True, help="design/ 下的文件名")
    ap.add_argument("--factor", type=int, default=2, choices=(2, 4),
                    help="最终倍率；模型原生 4x，选 2 则 4x 后 LANCZOS 下采样（顺带降噪）")
    ap.add_argument("--root", default=".")
    ap.add_argument("--model-dir", default=".cache/models")
    ap.add_argument("--out", default=None, help="默认写成 <原名>_x<factor>.png")
    ap.add_argument("--check", action="store_true", help="跑换基准前的五项验收")
    ap.add_argument("--tile", type=int, default=256)
    args = ap.parse_args()

    try:
        import onnxruntime as ort
        from PIL import Image
    except ImportError as e:
        print(f"[错误] 缺依赖：{e}\n"
              "  python3 -m venv ~/.imgenv && "
              "~/.imgenv/bin/pip install pillow numpy onnxruntime", file=sys.stderr)
        return 2

    design = os.path.join(args.root, "characters", args.character, "design")
    src_path = os.path.join(design, args.sheet)
    if not os.path.exists(src_path):
        print(f"[错误] 找不到 {src_path}", file=sys.stderr)
        return 2
    out_path = args.out or os.path.join(
        design, args.sheet.replace(".png", f"_x{args.factor}.png"))

    model = fetch_model(os.path.join(args.root, args.model_dir))
    sess = ort.InferenceSession(model, providers=["CPUExecutionProvider"])

    src = Image.open(src_path).convert("RGB")
    print(f"[输入] {src_path} {src.size}")
    big = upscale(sess, src, tile=args.tile)
    if args.factor != NATIVE_SCALE:
        big = big.resize((src.width * args.factor, src.height * args.factor),
                         Image.LANCZOS)
    big.save(out_path)
    print(f"[输出] {out_path} {big.size}  "
          f"({os.path.getsize(out_path):,} 字节)")

    if args.check:
        return 1 if verify(src_path, out_path, args.factor) else 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
