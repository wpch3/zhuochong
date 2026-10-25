#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""外部动作（.motion3.json）回放验收 —— 曲线对不对，用参数读数说话。

为什么不能只看"变了多少像素"
----------------------------
`measure_motion.py` 量的变化像素数是**饱和**指标：待机本身（呼吸、眨眼、头发物理）
就能把头部区域 67% 的像素翻一遍。T66.21 第一次验收拿它量导入的挥手动作，
读到「0.8x 混淆底」，工具当场说"单边测不出" —— 换了 A/B 也只有 +19%，
完全无法证明 14° 的歪头真的发生了。

真正该看的是**参数时间曲线**：引擎有 `/api/params.json`（≈ Live2D 的
`getParameterValueById`），导入的动作本来就是"把参数推到某个值"，那就把它推出来的
值和文件里写的值逐点对一遍。这条判据不饱和、不受待机干扰，而且对得上就说明
整条链路（解析 → 绝对值转偏移 → 关键帧 → 动作层 → 参数层）都通。

判据
----
  · 采样期内每个时刻 |实测 − 期望| ≤ tol（默认 2.0 参数单位，约等于 1° 头部转角）；
  · 动作必须真的在播（`/api/info.json` 的 action == 请求的 id）；
  · 负对照：把同一个参数在**待机**下采一遍，用来解释"为什么不能只看有没有动"。

用法
----
    tools/qa_motion3.py --motion characters/xiaoxun/motions/curious_tilt.motion3.json
    tools/qa_motion3.py --id curious_tilt --params ParamAngleZ,ParamMouthForm --png logs/asset_qa/t66_21_curve.png

需要预览服务在跑；解析 .motion3 只用标准库，画图需要 PIL（~/.imgenv/bin/python3）。
"""
import argparse
import io
import json
import os
import sys
import time
import urllib.request

try:
    from PIL import Image, ImageDraw
except ImportError:
    Image = None


# ---------------------------------------------------------------- .motion3 解析
def load_curves(path):
    """返回 {参数 id: [(t, v), …]}，把官方段编码摊平成采样点。

    段编码（拿真文件核对过，见 src/core/zrig.c「官方段编码」）：
      Segments = [t0, v0, type, …数…, type, …数…]
      type=0/2/3 → (t, v)；type=1 → (c1t,c1v,c2t,c2v,t,v)，控制点在前、终点在后。
    """
    with open(path, encoding="utf-8") as f:
        doc = json.load(f)
    out = {}
    for c in doc.get("Curves", []):
        if c.get("Target") != "Parameter" or "Segments" not in c:
            continue
        s = c["Segments"]
        pts = [(s[0], s[1])]
        i = 2
        while i < len(s):
            t = int(s[i])
            if t == 1:
                pts.append((s[i + 5], s[i + 6]))   # 贝塞尔只取终点（期望值按段尾对齐）
                i += 7
            else:
                pts.append((s[i + 1], s[i + 2]))
                i += 3
        out[c["Id"]] = pts
    return out


def curves_of(path):
    """解析成可求值的段表：[(t0,v0), [(type, pt, pv, t, v, c1t,c1v,c2t,c2v), …]]"""
    with open(path, encoding="utf-8") as f:
        doc = json.load(f)
    out = {}
    for c in doc.get("Curves", []):
        if c.get("Target") != "Parameter" or "Segments" not in c:
            continue
        s = c["Segments"]
        segs = []
        pt, pv = s[0], s[1]
        i = 2
        while i < len(s):
            t = int(s[i])
            if t == 1:
                segs.append((1, pt, pv, s[i + 5], s[i + 6], s[i + 1], s[i + 2], s[i + 3], s[i + 4]))
                pt, pv = s[i + 5], s[i + 6]
                i += 7
            else:
                segs.append((t, pt, pv, s[i + 1], s[i + 2], 0, 0, 0, 0))
                pt, pv = s[i + 1], s[i + 2]
                i += 3
        out[c["Id"]] = segs
    return out


def bez(p0, p1, p2, p3, u):
    iu = 1.0 - u
    return iu ** 3 * p0 + 3 * iu * iu * u * p1 + 3 * iu * u * u * p2 + u ** 3 * p3


def eval_at(segs, t):
    """按官方口径求值：阶梯取段首值，反阶梯取段尾值，贝塞尔二分反解时间。"""
    prev = segs[0]
    for sg in segs:
        typ, pt, pv, tt, tv = sg[0], sg[1], sg[2], sg[3], sg[4]
        if t <= pt:
            return prev[2]
        if t <= tt:
            span = tt - pt
            if span <= 1e-9:
                return tv
            u = (t - pt) / span
            if typ == 2:
                return pv
            if typ == 3:
                return tv
            if typ == 0:
                return pv + (tv - pv) * u
            c1t, c1v, c2t, c2v = sg[5], sg[6], sg[7], sg[8]
            lo, hi = 0.0, 1.0
            for _ in range(40):
                mid = 0.5 * (lo + hi)
                if bez(pt, c1t, c2t, tt, mid) < t:
                    lo = mid
                else:
                    hi = mid
            return bez(pv, c1v, c2v, tv, 0.5 * (lo + hi))
        prev = sg
    return prev[4]


# ---------------------------------------------------------------- HTTP
def get(base, path):
    with urllib.request.urlopen(base + path, timeout=5) as r:
        return r.read()


def jget(base, path):
    return json.loads(get(base, path))


def param_map(base):
    return {p["id"]: p for p in jget(base, "/api/params.json")["params"]}


# ---------------------------------------------------------------- 画图
def draw_plot(rows, png, motion_id):
    """expected vs measured 折线图（PIL 手绘；本机没有 matplotlib）。"""
    if Image is None:
        return None
    W, H, pad = 900, 460, 56
    im = Image.new("RGB", (W, H), (250, 250, 248))
    dr = ImageDraw.Draw(im)
    n = len(rows)
    cols = [(30, 90, 200), (200, 60, 40)]
    vmin = min(min(r["exp"] for r in rows), min(r["meas"] for r in rows))
    vmax = max(max(r["exp"] for r in rows), max(r["meas"] for r in rows))
    if vmax - vmin < 1e-6:
        vmax, vmin = vmin + 1.0, vmin - 1.0
    tmax = max(r["t"] for r in rows) or 1.0

    def X(t):
        return pad + (W - 2 * pad) * t / tmax

    def Y(v):
        return H - pad - (H - 2 * pad) * (v - vmin) / (vmax - vmin)

    dr.rectangle([pad, pad, W - pad, H - pad], outline=(180, 180, 180))
    for k in range(5):
        v = vmin + (vmax - vmin) * k / 4.0
        y = Y(v)
        dr.line([pad, y, W - pad, y], fill=(226, 226, 222))
        dr.text((6, y - 5), "%.1f" % v, fill=(120, 120, 120))
    for k in range(0, 5):
        t = tmax * k / 4.0
        x = X(t)
        dr.line([x, pad, x, H - pad], fill=(238, 238, 234))
        dr.text((x - 10, H - pad + 6), "%.1fs" % t, fill=(120, 120, 120))
    for idx, key in enumerate(("exp", "meas")):
        prev = None
        for r in rows:
            pt = (X(r["t"]), Y(r[key]))
            if prev:
                dr.line([prev, pt], fill=cols[idx], width=3 if idx == 0 else 1)
            elif idx == 1:
                dr.ellipse([pt[0] - 2, pt[1] - 2, pt[0] + 2, pt[1] + 2], fill=cols[1])
            prev = pt
        dr.line([pad + 4, 20 + idx * 16, pad + 40, 20 + idx * 16], fill=cols[idx], width=3)
        dr.text((pad + 46, 12 + idx * 16),
                "expected (motion3 curve)" if idx == 0 else "measured (/api/params.json)",
                fill=(60, 60, 60))
    dr.text((pad, 4), "%s  ParamAngleZ  (ASCII labels only: PIL default font has no CJK)" % motion_id,
            fill=(40, 40, 40))
    im.save(png)
    return png


def make_strip(frames, png, scale):
    """把「动作进行到第几秒」的几帧并排：歪头/耳朵/嘴角的位置就是目视证据。"""
    ims = [(t, Image.open(io.BytesIO(raw)).convert("RGBA")) for t, raw in frames]
    w, h = ims[0][1].size
    # 只取上半身：脚和地面在这个动作里本来就该一动不动，占地方
    box = (0, 0, w, int(h * 0.62))
    cw, ch = (box[2] - box[0]) * scale, (box[3] - box[1]) * scale
    pad, label = 6, 20
    cols = min(3, len(ims))
    rows_n = (len(ims) + cols - 1) // cols
    im = Image.new("RGBA", (cols * (cw + pad) + pad,
                            rows_n * (ch + label + pad) + pad), (250, 250, 248, 255))
    dr = ImageDraw.Draw(im)
    for i, (t, src) in enumerate(ims):
        crop = src.crop(box).resize((cw, ch), Image.LANCZOS)
        x = pad + (i % cols) * (cw + pad)
        y = pad + (i // cols) * (ch + label + pad)
        im.alpha_composite(crop, (x, y + label))
        dr.text((x + 2, y + 4), "t=%.2fs" % t, fill=(30, 30, 30, 255))
    im.convert("RGB").save(png)
    return png


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:5173")
    ap.add_argument("--motion", help=".motion3.json 路径（不给就按 --id 去 motions/ 里找）")
    ap.add_argument("--id", help="动作 id（默认取文件名）")
    ap.add_argument("--character", default="xiaoxun")
    ap.add_argument("--root", default=".")
    ap.add_argument("--param", default="ParamAngleZ", help="拿哪个参数对曲线")
    ap.add_argument("--tol", type=float, default=2.0, help="允许偏差（参数单位）")
    ap.add_argument("--seconds", type=float, default=4.4)
    ap.add_argument("--step", type=float, default=0.05)
    ap.add_argument("--png", help="把 expected/measured 画成图存这里")
    ap.add_argument("--strip", help="把几帧拼成对比图（放大看歪头/耳朵/嘴）")
    ap.add_argument("--strip-scale", type=int, default=2)
    ap.add_argument("--json", help="把逐点结果写成 json")
    args = ap.parse_args()

    path = args.motion
    if not path:
        mid = args.id or ""
        path = os.path.join(args.root, "characters", args.character, "motions", mid + ".motion3.json")
    if not os.path.isfile(path):
        print("[FAIL] 找不到动作文件：%s" % path)
        return 2
    mid = args.id or os.path.basename(path)[: -len(".motion3.json")]
    segs_all = curves_of(path)
    if args.param not in segs_all:
        print("[FAIL] 动作里没有参数 %s（有：%s）" % (args.param, ", ".join(sorted(segs_all))))
        return 2
    segs = segs_all[args.param]
    duration = segs[-1][3]

    # 负对照：先量待机，说明"只看有没有动"没有分辨力
    jget(args.base, "/api/action?id=idle")
    time.sleep(0.4)
    idle = [param_map(args.base)[args.param]["effective"] for _ in range(8)]
    idle_span = max(idle) - min(idle)

    jget(args.base, "/api/action?id=" + mid)
    st = jget(args.base, "/api/info.json")
    playing = st.get("action") == mid
    print("请求动作 %s → 引擎当前动作 %s%s" % (mid, st.get("action"), "" if playing else "  !! 没在播"))

    rows, worst, worst_t = [], 0.0, 0.0
    frames, want = [], [0.10, 0.90, 1.70, 2.40, 3.00, 3.60]
    t0 = time.time()
    while True:
        t = time.time() - t0
        if t > args.seconds:
            break
        pm = param_map(args.base).get(args.param)
        if pm is None:
            print("[FAIL] 引擎里没有参数 %s" % args.param)
            return 2
        meas = pm["effective"]
        # 循环动作：时间对 duration 取模
        tt = t % duration if duration > 0 else t
        exp = eval_at(segs, tt)
        rows.append({"t": t, "exp": exp, "meas": meas, "err": meas - exp})
        if args.strip and want and t >= want[0]:
            frames.append((want.pop(0), get(args.base, "/api/frame.png?s=100")))
        if args.strip and want and t > want[0] + 1.5:
            want.pop(0)      # 抓慢了就跳过这一格，别把时间标签对错
        if abs(meas - exp) > worst:
            worst, worst_t = abs(meas - exp), t
        time.sleep(args.step)

    print("待机（负对照）波动 %.2f 参数单位 —— 单看『有没有动』在这个量级上分不出动作" % idle_span)
    print("逐点最大偏差 %.2f（t=%.2fs，容差 %.2f）" % (worst, worst_t, args.tol))
    for r in rows[:: max(1, len(rows) // 10)]:
        print("  t=%5.2fs  期望 %7.2f  实测 %7.2f  差 %+6.2f" % (r["t"], r["exp"], r["meas"], r["err"]))

    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump({"id": mid, "param": args.param, "tol": args.tol,
                       "idle_span": idle_span, "rows": rows}, f, ensure_ascii=False, indent=1)
        print("逐点结果 → %s" % args.json)
    if args.strip and Image is not None and frames:
        print("对比图 → %s" % make_strip(frames, args.strip, args.strip_scale))
    if args.png and Image is not None:
        print("曲线图 → %s" % draw_plot(rows, args.png, mid))

    ok = playing and worst <= args.tol
    print("结论：%s" % ("通过（曲线与文件一致）" if ok else "不通过"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
