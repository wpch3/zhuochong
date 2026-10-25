#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""qa_ear_orient.py —— 猫耳朝向的几何检测（2026-10-17，用户第五次打回猫耳时建的）。

为什么要这个工具
----------------
用户原话：「我感觉少女的这个猫耳像是反了一样，**耳廓那边跑到内边了**。不对劲，是角度不对吗」。
这类问题靠眼睛来回看截图是扯不清的，必须把"反了"翻译成能算的数：

  ① **耳尖的倒向**  = 耳朵顶部 20% 的质心 x − 根部 20% 的质心 x。
     放在头左边的那只，耳尖应该往**画面左**（往外）倒；右边那只往右倒。
  ② **耳廓（内耳）的偏向** = 暖色像素（R 明显大于 B）的横向位置，按同一行的耳宽归一。
     左耳的耳廓应该偏**外**（靠画面左），右耳偏右。

判据从哪来（三家教程口径一致，都说正面要朝外）
----------------------------------------------
  · palmie.jp/lessons/43
      「正面向きは少し耳を**外側**に向けた状態で描きました。猫が力を入れていない時は、
        耳はこの辺を向いています」
  · atam-academy.com/blog/50779（猫耳の描き方）
      「耳の正面は真正面ではなく、**少し外側を向く**イメージで描きましょう」
  · adobe.com/jp/creativecloud/…/how-to-draw-ears
      「猫の耳であればやや斜めに**少し外向き**に生える」
  · 另外对照了真猫正面照与二次元参考图各一张，逐张量过：**耳廓偏外、厚毛边在内侧**。
    原因是猫耳开口朝前**且朝外**，靠内那条边才是转向镜头的那条，露出来的是耳背的毛。

于是「耳尖朝内 + 耳廓朝内」这两处错，其实是同一个错：**左右两张贴图装反了**。

用法
----
    python3 tools/qa_ear_orient.py --character xiaoxun --form teen
    python3 tools/qa_ear_orient.py --json          # 给闸门用的机器可读输出

退出码 0 = 两只耳朵朝向都对；1 = 有耳朵反了。
`tools/selfcheck_repo.py :: check_ear_orientation` 调用本文件的 measure()。
"""
from __future__ import annotations

import argparse
import json
import os
import sys

import struct
import zlib

# ★ 故意不用 pillow/numpy：这个判据要当**闸门**天天跑（selfcheck 用系统 python3，
#   装不了第三方包）。PNG 自己解：标准 8bit 非隔行，IDAT 解压后逐行反滤波即可。
#   —— 以前写的 QA 脚本都挂在 ~/.imgenv 上，结果就是「只有人想起来时才跑一次」。


def _read_png_rgba(path):
    """读 8bit 非隔行 PNG，返回 (w, h, bytearray)，每像素 4 字节 RGBA。"""
    with open(path, "rb") as f:
        data = f.read()
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError(f"{path} 不是 PNG")
    pos, idat, w = 8, [], None
    while pos + 8 <= len(data):
        ln, typ = struct.unpack(">I4s", data[pos:pos + 8])
        body = data[pos + 8:pos + 8 + ln]
        pos += 12 + ln
        if typ == b"IHDR":
            w, h, depth, ctype, _comp, _filt, inter = struct.unpack(">IIBBBBB", body)
            if depth != 8 or inter != 0 or ctype not in (2, 6):
                raise ValueError(f"{path}: 只支持 8bit 非隔行 RGB/RGBA（当前 depth={depth} "
                                 f"color={ctype} interlace={inter}）")
            nch = 4 if ctype == 6 else 3
        elif typ == b"IDAT":
            idat.append(body)
        elif typ == b"IEND":
            break
    raw = zlib.decompress(b"".join(idat))
    stride = w * nch
    out = bytearray(w * h * 4)
    prev = bytearray(stride)
    q = 0
    for y in range(h):
        ft = raw[q]; q += 1
        line = bytearray(raw[q:q + stride]); q += stride
        if ft == 1:
            for i in range(nch, stride):
                line[i] = (line[i] + line[i - nch]) & 0xFF
        elif ft == 2:
            for i in range(stride):
                line[i] = (line[i] + prev[i]) & 0xFF
        elif ft == 3:
            for i in range(stride):
                a = line[i - nch] if i >= nch else 0
                line[i] = (line[i] + ((a + prev[i]) >> 1)) & 0xFF
        elif ft == 4:
            for i in range(stride):
                a = line[i - nch] if i >= nch else 0
                c = prev[i - nch] if i >= nch else 0
                b_ = prev[i]
                pp = a + b_ - c
                pa, pb, pc = abs(pp - a), abs(pp - b_), abs(pp - c)
                pr = a if (pa <= pb and pa <= pc) else (b_ if pb <= pc else c)
                line[i] = (line[i] + pr) & 0xFF
        elif ft != 0:
            raise ValueError(f"{path}: 未知行滤波 {ft}")
        if nch == 4:
            out[y * stride:(y + 1) * stride] = line
        else:
            for x in range(w):
                o, i = (y * w + x) * 4, x * 3
                out[o:o + 3] = line[i:i + 3]
                out[o + 3] = 255
        prev = line
    return w, h, out

ALPHA_THR = 40          # 多不透明才算耳朵的像素
TIP_FRAC = 0.20         # 取顶部/根部各 20% 求质心
WARM_DR = 18            # R 比 B 高多少算"暖色耳廓"
WARM_MIN_R = 170        # 耳廓是亮暖色，排除线稿与阴影


def measure_sprite(path: str) -> dict:
    """量一张耳朵贴图：耳尖相对耳根偏哪边、耳廓偏哪边。坐标一律是贴图自身像素坐标。"""
    w, h, px = _read_png_rgba(path)
    rows = []                       # 每行的不透明像素 x 列表
    for y in range(h):
        base = y * w * 4
        xs = [x for x in range(w) if px[base + x * 4 + 3] > ALPHA_THR]
        rows.append(xs)
    ys = [y for y in range(h) if rows[y]]
    if not ys:
        raise ValueError(f"{path} 是空图")
    y0, y1 = ys[0], ys[-1]
    k = max(2, int((y1 - y0 + 1) * TIP_FRAC))
    top = [x for y in range(y0, min(y0 + k, h)) for x in rows[y]]
    bot = [x for y in range(max(y1 - k + 1, 0), y1 + 1) for x in rows[y]]
    tip_x = sum(top) / len(top)
    root_x = sum(bot) / len(bot)
    lean = tip_x - root_x                      # >0 = 耳尖偏贴图右侧

    warm_px, fracs = 0, []
    for y in range(h):
        xs = rows[y]
        if not xs:
            continue
        base = y * w * 4
        wx = [x for x in xs
              if px[base + x * 4] > px[base + x * 4 + 2] + WARM_DR
              and px[base + x * 4] > WARM_MIN_R]
        warm_px += len(wx)
        if wx and len(xs) > 4 and xs[-1] > xs[0]:
            fracs.append(((sum(wx) / len(wx)) - xs[0]) / (xs[-1] - xs[0]))
    frac = (sum(fracs) / len(fracs)) if (warm_px > 20 and fracs) else None
    return {"path": path, "w": w, "h": h,
            "tip_x": round(tip_x, 2), "root_x": round(root_x, 2), "lean_px": round(lean, 2),
            "pinna_frac": (round(frac, 4) if frac is not None else None), "warm_px": warm_px}


def ear_side(root: str, character: str, form: str, att: dict) -> str:
    """这只耳朵挂在头的哪一边：left / right（按解算出的画布 x 与头中线比）。"""
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import attach_geom
        anc = attach_geom.load_anchors(
            os.path.join(root, "characters", character, "forms", form, "design"))
        if anc:
            socks = attach_geom.load_sockets(os.path.join(root, "characters", character))
            pos, _ = attach_geom.attach_pos(att, socks.get(att.get("socket")), anc)
            cx = float(anc["points"]["head_top"][0])
            return "left" if pos[0] < cx else "right"
    except Exception:            # noqa: BLE001 —— 解不出来就退回老口径，别把闸弄崩
        pass
    px = (att.get("pos_rel") or [att.get("pos", [0, 0])[0]])[0]
    return "left" if px < 0 else "right"


def measure(root: str = ".", character: str = "xiaoxun", form: str = "teen") -> list[dict]:
    """按 attachments.json 里的实际摆放位置判定每只耳朵朝向对不对。

    返回每只耳朵一条记录，含 ok / 原因。不抛异常（没有猫耳的角色返回空表）。
    """
    apath = os.path.join(root, "characters", character, "design", "attachments.json")
    with open(apath, encoding="utf-8") as f:
        design = json.load(f)
    sprites = os.path.join(root, "characters", character, "forms", form, "sprites")
    out = []
    for att in design.get("attachments", []):
        if "ear" not in att.get("tags", []):
            continue
        sp = os.path.join(sprites, att["sprite"])
        if not os.path.exists(sp):
            continue
        # 摆在头的哪一边 —— 按**解算出来的画布坐标**和头中线比，而不是读 pos_rel 的符号。
        # ★ 2026-10-25（T66.19）：猫耳改成挂在 socket_ear_l/r 上之后，表里就没有
        #   pos_rel 了（位置归挂点）。第一版这里读 pos_rel、读不到就退回 0，
        #   于是两只耳朵都被判成"在右边"，左耳当场变红 —— 闸的输入没了，
        #   红的是闸不是画面。凡是"位置由别处决定"的件，闸都必须走同一份解算
        #   （tools/attach_geom.attach_pos），否则它验的是表格式不是几何。
        side = ear_side(root, character, form, att)
        m = measure_sprite(sp)
        m["id"] = att["id"]
        m["side"] = side
        want = -1.0 if side == "left" else 1.0       # 外侧方向：左边的往 −x，右边的往 +x
        m["lean_ok"] = (m["lean_px"] * want) > 0
        if m["pinna_frac"] is None:
            m["pinna_ok"] = None
        else:
            # 耳廓该落在"外侧半边"：左耳 <0.5，右耳 >0.5
            m["pinna_ok"] = (m["pinna_frac"] < 0.5) if side == "left" else (m["pinna_frac"] > 0.5)
        m["ok"] = bool(m["lean_ok"]) and (m["pinna_ok"] is not False)
        out.append(m)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    ap.add_argument("--character", default="xiaoxun")
    ap.add_argument("--form", default="teen")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    rows = measure(args.root, args.character, args.form)
    if args.json:
        print(json.dumps(rows, ensure_ascii=False, indent=2))
    else:
        if not rows:
            print("没有找到带 ear 标签的挂件")
        for m in rows:
            out_dir = "外(画面左)" if m["side"] == "left" else "外(画面右)"
            print(f"{m['id']:<12} 贴在头的{'左' if m['side']=='left' else '右'}边  {m['w']}x{m['h']}")
            print(f"    耳尖相对耳根偏移 {m['lean_px']:+6.1f}px   应往{out_dir}倒"
                  f"   {'通过' if m['lean_ok'] else '不通过 ← 耳尖往内倒了'}")
            if m["pinna_frac"] is None:
                print("    耳廓：没找到暖色像素（跳过）")
            else:
                print(f"    耳廓横向位置 {m['pinna_frac']:.3f}（0=贴图最左 1=最右）"
                      f"   应{'<0.5' if m['side']=='left' else '>0.5'}"
                      f"   {'通过' if m['pinna_ok'] else '不通过 ← 耳廓跑到内侧了'}")
    return 0 if all(m["ok"] for m in rows) else 1


if __name__ == "__main__":
    sys.exit(main())
