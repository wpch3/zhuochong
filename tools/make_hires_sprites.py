#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""make_hires_sprites.py —— 给每个切件生成 2× 高清版（T30.1）。

为什么是这个做法（原计划被否掉了）
----------------------------------
T30.1 原来的打法是「整条切件链切到 2× 坐标系」：prepare_sprites 输出 2× 的
body_full，16 个切件脚本都在 2× 坐标里跑，make_rig 再把坐标除回画布尺度。
**动手前先数了一遍改动面，发现不可行**：坐标散在 17 个 JSON、上百个字段名里
（pos / size / pivot / patch_pos / ball_pos / iris_center / travel / aperture_px /
socket_size / lash_travel …），而且 `*_px` 里有些是距离、有些是统计量，
逐个判断必然漏，漏一个就是整件错位。

换成现在这个做法：**切件链一行都不改**，在它跑完之后、make_rig 之前插一步，
把每个 sprite 单独放大到 2×，make_rig 发现有 `@2x` 就改用它并把 `scale` 乘 0.5。
画布坐标系完全不动，所以 rig 里所有像素常数（travel / lift / pivot / hold 线）
一个都不用改。

2026-10-15 实测（先拿 4 个脸部件验的，`logs/asset_qa/hires_part_ab.png`）
-------------------------------------------------------------------------
    画质   1.0 档锐度 ×1.947，2.0 档 ×1.948      （眼睛轮廓/睫毛/发卡描边肉眼可见变锐）
    性能   0.55/1.0/1.2/2.0 四档 **全部在 ±1% 噪声内**，没有代价
           —— 渲染成本由输出像素数决定，不是源图大小；部件都小，照样在 cache 里。

放大策略（不是所有件都该走超分）
--------------------------------
    有原生 2× 源      → **直接用它**（sprites/hires_src/<件名>@2x.png）
                        超分是「只有 1× 像素可用」时的退路，不是目的。
                        AI 生成的差分件（星形虹膜 / 闪光特效）源图就有 2048px，
                        从源图直接缩到 62px，比「缩到 31px 再超分回 62px」
                        多留一整档细节 —— 星形的描边和碎钻高光只有这样才活得下来
                        （2026-10-16 实测，logs/asset_qa/star_eye_v2.png）。
                        alpha 仍按下面那条规则由 1× 插值而来，所以遮罩与同组件逐像素对齐。
    RGB 有内容        → Real-ESRGAN anime 4× 再降到 2×（和 upscale_sheet.py 同一个模型）
    RGB 空 / 近纯色   → 直接 LANCZOS
                        （mask_only 的 mouth_mask / eye_*_socket 三件 RGB 标准差为 0；
                         eye_hl_* 四个高光件标准差 3.9。对这些做超分没有信息可恢复，
                         还可能引入噪声。）
    alpha            → 一律 LANCZOS（软边插值够用，超分模型也只吃 RGB）

★ 必须全量，不许挑着做
----------------------
`mask` / `motion_from` 把件两两绑在一起（eye_*_socket 罩着 eye_*_base/ball，
mouth_mask 罩着 mouth_cavity，hair_front 罩着 brow_*_ghost）。
一个 2× 一个 1× 会让遮罩对不上。所以要么全做要么全不做，闸会检查这一点。

用法
----
    python3 tools/make_hires_sprites.py --character xiaoxun --form teen
    python3 tools/make_hires_sprites.py --character xiaoxun --form teen --clean  # 删掉所有 @2x

依赖 onnxruntime + pillow + numpy（和 upscale_sheet.py 一样走 ~/.imgenv）。
模型由 upscale_sheet.fetch_model() 负责下载与 sha256 校验，缓存在 .cache/models/。
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import sys
import time

SUFFIX = "@2x.png"
NATIVE_DIR = "hires_src"   # 原生 2× 源：有就直接用，不走超分（见下）
FACTOR = 2
NATIVE = 4            # 模型原生倍率
FLAT_RGB_STD = 6.0    # RGB 标准差低于这个就认为"没内容"，走插值


def kill_keycolor(arr):
    """抑制键色残留（纯绿 / 洋红），返回 (新数组, 处理了几个像素)。

    为什么需要：原图里这些残留躲在 alpha<40 的边缘，`check_assets` 的
    「无键色垃圾像素」闸只看 alpha>40，所以 1× 是干净的。
    **超分 + alpha LANCZOS 之后 alpha 被插值抬到 40 以上，残留就浮出来了** ——
    2026-10-15 首次全量跑完实测 21 个（body_full@2x 8 个、hair_side_l@2x 3 个…）。
    这正是 DC44 复查触发条件②写的情况（"超分会忠实放大抠图残留"）。

    判定口径**和 check_assets 完全一致**，不能各写一套：
        纯绿   G - max(R,B) > 60
        洋红   R-G>60 且 B-G>60 且 R>150 且 B>150
    处理方式：用 3×3 邻域里的非键色像素均值重填 RGB（保留 alpha，边缘不留洞），
    迭代两轮；两轮后仍是键色的，直接把 alpha 清零。
    """
    import numpy as np
    a = arr.astype(np.int16)
    R, G, B, A = a[..., 0], a[..., 1], a[..., 2], a[..., 3]

    def mask_of(x):
        r, g, b, al = x[..., 0], x[..., 1], x[..., 2], x[..., 3]
        green = (g - np.maximum(r, b)) > 60
        mag = (r - g > 60) & (b - g > 60) & (r > 150) & (b > 150)
        return (al > 40) & (green | mag)

    bad0 = mask_of(a)
    n0 = int(bad0.sum())
    if n0 == 0:
        return arr, 0
    for _ in range(2):
        bad = mask_of(a)
        if not bad.any():
            break
        good = (~bad) & (a[..., 3] > 40)
        acc = np.zeros(a.shape[:2] + (3,), np.float64)
        cnt = np.zeros(a.shape[:2], np.float64)
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                if dy == 0 and dx == 0:
                    continue
                gs = np.roll(np.roll(good, dy, 0), dx, 1)
                px = np.roll(np.roll(a[..., :3], dy, 0), dx, 1)
                acc += px * gs[..., None]
                cnt += gs
        fill = bad & (cnt > 0)
        a[..., :3][fill] = (acc[fill] / cnt[fill][:, None]).round()
    left = mask_of(a)
    a[..., 3][left] = 0          # 实在填不掉的（周围也全是键色）就隐掉
    return a.astype(arr.dtype), n0


def is_flat_rgb(arr) -> bool:
    """RGB 是不是没什么内容（纯 alpha 遮罩 / 近纯色高光）。"""
    import numpy as np
    vis = arr[..., 3] > 8
    if not vis.any():
        return True
    return float(arr[..., :3][vis].std()) < FLAT_RGB_STD


def upscale_rgb(sess, img_rgb):
    """Real-ESRGAN 4×。小图直接整张过，不用分块。

    边缘先 edge-pad 8px 再裁回去 —— 不补的话超分会在图块边界上压出一圈暗边，
    而切件全是带透明边的小块，边界瑕疵特别显眼。
    """
    import numpy as np
    from PIL import Image
    name = sess.get_inputs()[0].name
    a = np.asarray(img_rgb, dtype=np.float32) / 255.0
    h, w, _ = a.shape
    pad = 8
    ap = np.pad(a, ((pad, pad), (pad, pad), (0, 0)), mode="edge")
    out = sess.run(None, {name: np.ascontiguousarray(ap.transpose(2, 0, 1)[None])})[0][0]
    out = out.transpose(1, 2, 0)[pad * NATIVE:(pad + h) * NATIVE,
                                 pad * NATIVE:(pad + w) * NATIVE]
    return Image.fromarray((np.clip(out, 0, 1) * 255 + 0.5).astype("uint8"), "RGB")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--character", required=True)
    ap.add_argument("--form", required=True)
    ap.add_argument("--root", default=".")
    ap.add_argument("--model-dir", default=".cache/models")
    ap.add_argument("--clean", action="store_true", help="删掉所有 @2x 再退出")
    args = ap.parse_args()

    sp_dir = os.path.join(args.root, "characters", args.character,
                          "forms", args.form, "sprites")
    if not os.path.isdir(sp_dir):
        print(f"[错误] 没有 {sp_dir}", file=sys.stderr)
        return 2

    existing = sorted(glob.glob(os.path.join(sp_dir, "*" + SUFFIX)))
    if args.clean:
        for f in existing:
            os.remove(f)
        rp = os.path.join(sp_dir, "hires_report.json")
        if os.path.exists(rp):
            os.remove(rp)
        print(f"[清理] 删掉 {len(existing)} 个 {SUFFIX}")
        return 0

    try:
        import numpy as np
        import onnxruntime as ort
        from PIL import Image
    except ImportError as e:
        print(f"[错误] 缺依赖：{e}\n"
              "  python3 -m venv ~/.imgenv && "
              "~/.imgenv/bin/pip install pillow numpy onnxruntime", file=sys.stderr)
        return 2

    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import upscale_sheet                                     # noqa: E402

    model = upscale_sheet.fetch_model(os.path.join(args.root, args.model_dir))
    sess = ort.InferenceSession(model, providers=["CPUExecutionProvider"])

    # 只给 rig 真正引用的件做 @2x。
    #
    # 2026-10-15 首次全量跑完发现 53 个件里有 11 个 rig 根本不用
    # （body_full 是切件源图、seg_arm_* 是拆成 upper/fore 之前的中间产物、
    #  eye_open_*/eye_closed_*/eye_*_lid/eye_*_lash 是配准用的中间件），
    # 白占 **2.09 MB**，光 body_full@2x 就 1.6 MB。
    #
    # 鸡生蛋：本步跑在 make_rig 之前，读到的是**上一次**的 rig.json。
    # 新增部件时第一次会漏，第二次才补上 —— 所以 selfcheck 有一条闸兜底
    # （「rig 引用的件都有 @2x」），漏了会判红而不是悄悄少一个。
    rig_p = os.path.join(args.root, "characters", args.character,
                         "forms", args.form, "rig.json")
    want = None
    if os.path.exists(rig_p):
        with open(rig_p, encoding="utf-8") as f:
            rj = json.load(f)
        want = {os.path.basename(p["file"]).replace(SUFFIX, ".png")
                for p in rj.get("parts", []) if p.get("file")}

    # 有些件的 @2x 由它们**自己的工具**原生产出（2048px 源图直出，比超分清楚得多），
    # 本工具既不重做也不清理：重做 = 把原生 2× 换成超分版；清理 = 直接删掉人家的成果。
    # 目前有两组：星星眼（tools/make_star_eye_parts.py）和裙子里布
    # （tools/make_skirt_parts.py）—— 后者的 @2x 是**用 1× 的掩码放大两倍**后
    # 从 seg_torso@2x 上原样切下来的，和表布逐像素对齐；换成超分就会错开一两像素，
    # 静止时裙边上会多出一条暗线（T45.11 实测）。两组都排在本工具之后跑。
    owned = set()
    sj = os.path.join(sp_dir, "star_eye_parts.json")
    if os.path.exists(sj):
        with open(sj, encoding="utf-8") as f:
            sjd = json.load(f)
        owned = {os.path.basename(e["file"]) for e in sjd.get("eyes", [])}
        if sjd.get("sparkle", {}).get("file"):
            owned.add(os.path.basename(sjd["sparkle"]["file"]))
    kj = os.path.join(sp_dir, "skirt_parts.json")
    if os.path.exists(kj):
        with open(kj, encoding="utf-8") as f:
            kjd = json.load(f)
        owned |= {os.path.basename(e["file"]) for e in kjd.get("parts", []) if e.get("file")}

    srcs = sorted(f for f in glob.glob(os.path.join(sp_dir, "*.png"))
                  if not f.endswith(SUFFIX)
                  and os.path.basename(f) not in owned
                  and (want is None or os.path.basename(f) in want))
    # 把不再需要的旧 @2x 清掉，别留垃圾在库里
    for stale in glob.glob(os.path.join(sp_dir, "*" + SUFFIX)):
        if os.path.basename(stale).replace(SUFFIX, ".png") in owned:
            continue
        if stale[:-len(SUFFIX)] + ".png" not in srcs:
            os.remove(stale)
    t0 = time.time()
    rows, n_sr, n_lz, n_nat, n_fixed = [], 0, 0, 0, 0
    for src in srcs:
        im = Image.open(src).convert("RGBA")
        w, h = im.size
        arr = np.asarray(im)
        nat = os.path.join(sp_dir, NATIVE_DIR,
                           os.path.basename(src)[:-4] + SUFFIX)
        method = None
        if os.path.exists(nat):
            cand = Image.open(nat).convert("RGBA")
            if cand.size == (w * FACTOR, h * FACTOR):
                big = cand.convert("RGB")
                method = "native"
                n_nat += 1
            else:
                # 尺寸对不上就不要硬用：这说明 1× 件被重切过而原生源没跟着更新，
                # 静默缩放会让它和同组件错位。退回超分，并在报告里留痕。
                print(f"[高清] 忽略 {os.path.basename(nat)}："
                      f"{cand.size} ≠ {(w * FACTOR, h * FACTOR)}", file=sys.stderr)
        if method is None:
            flat = is_flat_rgb(arr)
            if flat:
                big = im.convert("RGB").resize((w * FACTOR, h * FACTOR), Image.LANCZOS)
                method = "lanczos"
                n_lz += 1
            else:
                big4 = upscale_rgb(sess, im.convert("RGB"))
                big = big4.resize((w * FACTOR, h * FACTOR), Image.LANCZOS)
                method = "realesrgan"
                n_sr += 1
        big.putalpha(im.split()[3].resize((w * FACTOR, h * FACTOR), Image.LANCZOS))
        cleaned, n_junk = kill_keycolor(np.asarray(big.convert("RGBA")))
        if n_junk:
            big = Image.fromarray(cleaned, "RGBA")
            n_fixed += n_junk
        dst = src[:-4] + SUFFIX
        big.save(dst)
        rows.append({"name": os.path.basename(src), "src": [w, h],
                     "dst": [w * FACTOR, h * FACTOR],
                     "method": method, "keycolor_fixed": n_junk})

    report = {
        "schema_version": "1.0",
        "factor": FACTOR,
        "suffix": SUFFIX,
        "model": os.path.basename(model),
        "count": len(rows),
        "realesrgan": n_sr,
        "lanczos": n_lz,
        "native": n_nat,
        "keycolor_fixed": n_fixed,
        "seconds": round(time.time() - t0, 1),
        "parts": rows,
        "note": "切件链不改坐标，这一步只换像素密度；make_rig 发现 @2x 就把 scale 乘 0.5",
    }
    with open(os.path.join(sp_dir, "hires_report.json"), "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=1)
    print(f"[高清] {len(rows)} 个切件 → 2×   "
          f"（原生 {n_nat} / 超分 {n_sr} / 插值 {n_lz}，"
          f"键色残留修掉 {n_fixed} 像素，{report['seconds']}s）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
