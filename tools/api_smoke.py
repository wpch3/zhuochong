#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""预览服务端点冒烟测试（命令行版，和 web/test.html 里的「自动测试」是同一套判据）。

为什么要有命令行版：浏览器那套只能手点，这份能进 selfcheck、能在没有浏览器的机器上跑。
判据不看 HTTP 200，而是**看画面真的变了没有**——抓 /api/frame.png 的字节做哈希比对。

用法：
    python3 tools/api_smoke.py --port 5173            # 连已经起着的预览
    python3 tools/api_smoke.py --spawn                # 自己起一个预览再测
"""
import argparse
import hashlib
import json
import os
import signal
import subprocess
import sys
import time
import urllib.parse
import urllib.request

PASS, FAIL = [], []


def check(name, ok, detail=""):
    (PASS if ok else FAIL).append(name)
    print(("  通过  " if ok else "  失败  ") + name + ("   " + detail if detail else ""))
    return ok


class Api:
    def __init__(self, base):
        self.base = base

    def get(self, path, timeout=5.0):
        url = self.base + path
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return r.status, r.read()

    def json(self, path):
        _, b = self.get(path)
        return json.loads(b.decode("utf-8"))

    def hit(self, path):
        try:
            st, _ = self.get(path)
            return st == 200
        except Exception as e:                       # noqa: BLE001
            print("    （请求失败）", path, e)
            return False

    def frame_hash(self):
        _, b = self.get("/api/frame.png?t=%d" % (time.time() * 1000))
        return hashlib.sha1(b).hexdigest()[:12], len(b)


# 三个互动区在画面上的大致纵向位置（0=头顶 1=脚底）。
# 注意 feet 不能取到 0.9：区域矩形比人物还长一截，下面那段是透明的，
# 引擎的区域判定带不透明像素命中，点在透明处等于没点到。
REGION_FY = {"head": 0.11, "body": 0.40, "feet": 0.84}
# 横向位置：脚那一档不能取正中——两条腿之间是透明的，区域判定要求点在不透明像素上。
REGION_FX = {"head": 0.50, "body": 0.50, "feet": 0.45}


def region_xy(info, region):
    return (int(info["frame_w"] * REGION_FX.get(region, 0.5)),
            int(info["frame_h"] * REGION_FY.get(region, 0.4)))


def poke_url(info, region, tool=0):
    """区域中心的帧坐标：/api/poke 收帧坐标，引擎自己换算到画布区域。"""
    x, y = region_xy(info, region)
    return "/api/poke?x=%d&y=%d&tool=%d" % (x, y, tool)


def settle(a, timeout=3.0):
    """等当前动作放完回到待机：动作还在演的时候，新的互动请求会被状态机挡掉，
       不等就测，测出来的是"上一条动作还在演"，不是互动没反应。"""
    t0 = time.time()
    while time.time() - t0 < timeout:
        if a.json("/api/info.json")["action"] in ("idle", "breath", "sway"):
            return True
        time.sleep(0.12)
    return False


def run(base, root):
    a = Api(base)
    print("== 基本端点 ==")
    info = a.json("/api/info.json")
    check("info.json 能读", bool(info.get("engine")), "引擎 " + str(info.get("engine")))
    h0, n0 = a.frame_hash()
    check("frame.png 是张真图", n0 > 2000, "%d 字节 %dx%d" % (n0, info["frame_w"], info["frame_h"]))

    print("== 眨眼（眼睑下滑）==")
    a.hit("/api/blink?v=0"); time.sleep(0.25)
    h_open, _ = a.frame_hash()
    a.hit("/api/blink?v=1"); time.sleep(0.25)
    h_shut, _ = a.frame_hash()
    check("眨眼 0 → 1 画面有变化", h_open != h_shut, "%s → %s" % (h_open, h_shut))
    a.hit("/api/blink?v=0.5"); time.sleep(0.25)
    h_half, _ = a.frame_hash()
    check("眨眼 0.5 是第三种画面", h_half not in (h_open, h_shut), h_half)
    check("info 能读回手动眨眼值", abs(a.json("/api/info.json")["blink_manual"] - 0.5) < 0.01)
    a.hit("/api/blink?v=auto")
    check("切回自动眨眼", a.json("/api/info.json")["blink_manual"] < 0)

    print("== 视线 ==")
    a.hit("/api/blink?v=0")
    a.hit("/api/gaze?x=-1&y=0"); time.sleep(0.3)
    gl, _ = a.frame_hash()
    a.hit("/api/gaze?x=1&y=0"); time.sleep(0.3)
    gr, _ = a.frame_hash()
    check("视线左 / 右画面有变化", gl != gr, "%s → %s" % (gl, gr))
    a.hit("/api/gaze?off=1"); a.hit("/api/blink?v=auto")

    print("== 动作 ==")
    acts = info["actions"]
    ok_switch, moving = 0, 0
    for act in acts:
        a.hit("/api/action?id=" + urllib.parse.quote(act))
        # 状态要**马上**读：clicked 只演 0.55 秒，慢一拍读到的是演完以后的 idle
        if a.json("/api/info.json")["action"] == act:
            ok_switch += 1
        s1, _ = a.frame_hash()
        time.sleep(0.25)
        s2, _ = a.frame_hash()
        if s1 != s2:
            moving += 1
    check("每个动作都能切过去", ok_switch == len(acts), "%d/%d" % (ok_switch, len(acts)))
    check("动作期间画面在动", moving >= int(len(acts) * 0.6), "%d/%d 个动作逐帧有差别" % (moving, len(acts)))

    print("== 互动区命中 ==")
    for region in ("head", "body", "feet"):
        qx, qy = region_xy(info, region)
        q = a.json("/api/region?x=%d&y=%d" % (qx, qy))
        check("区域判定 %s" % region, q["region"] == region,
              "命中 %s → 动作 %s" % (q["region"] or "（空）", q["action"]))

    print("== 互动 ==")
    #                 名字      请求                        期望动作
    cases = (("摸头", poke_url(info, "head"), "head_pat"),
             ("抚摸身体", poke_url(info, "body"), "stroke"),
             ("戳脚", poke_url(info, "feet"), "surprised"),
             ("锤一下", poke_url(info, "head", 1), "hammered"),
             ("来电话", "/api/call?kind=call_start", "talk"),
             ("对面说话", "/api/call?kind=call_user_speaking", "focus"))
    for name, url, want in cases:
        settle(a)
        before = a.json("/api/info.json")["action"]
        a.hit(url)
        time.sleep(0.25)
        after = a.json("/api/info.json")
        line = a.json("/api/speech.json").get("line", "")
        check("互动「%s」→ %s" % (name, want), after["action"] == want,
              "动作 %s → %s（规则 %s）%s" % (before, after["action"], after["reason"],
                                            ("  「%s」" % line) if line else ""))
    a.hit("/api/call?kind=call_end")

    print("== 连续摸头升级为 happy ==")
    # 连击窗口 0.8 秒（zpet.c：超过就把计数清零），所以要快摸，不能等动作演完
    settle(a)
    got_combo = False
    for _ in range(4):
        a.hit(poke_url(info, "head"))
        time.sleep(0.2)
        if a.json("/api/info.json")["reason"] == "pat_head_combo":
            got_combo = True
            break
    check("连摸三次触发 pat_head_combo（摸头连击 → happy）", got_combo)

    print("== 情绪 ==")
    for m in ("happy", "sad", "surprised", "calm"):
        a.hit("/api/express?mood=" + m)
        time.sleep(0.12)
        check("情绪 %s 记进状态" % m, a.json("/api/info.json")["mood"] == m)

    print("== 缩放 / 睡眠 ==")
    a.hit("/api/scale?s=0.6"); time.sleep(0.2)
    small = a.json("/api/info.json")
    a.hit("/api/scale?s=1.2"); time.sleep(0.2)
    big = a.json("/api/info.json")
    check("缩放改变画面尺寸", big["frame_w"] > small["frame_w"],
          "%dx%d → %dx%d" % (small["frame_w"], small["frame_h"], big["frame_w"], big["frame_h"]))
    a.hit("/api/scale?s=1")
    a.hit("/api/idle?s=600"); time.sleep(0.4)
    check("放空够久会睡着", a.json("/api/info.json")["sleeping"] is True)
    a.hit("/api/idle?s=0"); a.hit("/api/call?kind=call_start"); time.sleep(0.3)
    check("叫一声会醒", a.json("/api/info.json")["sleeping"] is False)
    a.hit("/api/call?kind=call_end")

    print("== 零件表 ==")
    rig = a.json("/media/characters/%s/forms/%s/rig.json" % (info["character"], info["form"]))
    check("rig.json 能读", bool(rig.get("parts")), "%d 件" % len(rig.get("parts", [])))
    parts = {p["id"]: p for p in rig["parts"]}
    # 带 eyelid 标签的 = 两片眼皮 + 跟着下滑的两条睫毛（睫毛行程比眼皮少几像素，
    # 这样闭到底时它停在眼眶下沿当闭眼线，而不是被盖进去）
    lids = [p for p in rig["parts"] if "eyelid" in p.get("tags", [])]
    lid_ids = {p["id"] for p in lids}
    check("眼睑部件带行程",
          len(lids) >= 2 and {"eye_l_lid", "eye_r_lid"} <= lid_ids
          and all(p.get("eyelid_travel", 0) > 0 for p in lids),
          " ".join("%s:%d" % (p["id"], p.get("eyelid_travel", 0)) for p in lids))
    gz = [p for p in rig["parts"] if "gaze" in p.get("tags", [])]
    check("眼球部件带 gaze 标签", len(gz) == 2, " ".join(p["id"] for p in gz))
    layers = [p["layer"] for p in rig["parts"]]
    check("层号不重复", len(set(layers)) == len(layers), "%d 层" % len(layers))
    if all(k in parts for k in ("eye_l_lid", "brow_l", "hair_front")):
        check("眉毛和刘海压在眼皮上面",
              parts["brow_l"]["layer"] > parts["eye_l_lid"]["layer"] >= 0 and
              parts["hair_front"]["layer"] > parts["brow_l"]["layer"],
              "眼皮%d < 眉%d < 刘海%d" % (parts["eye_l_lid"]["layer"], parts["brow_l"]["layer"],
                                          parts["hair_front"]["layer"]))

    print("== 测试台页面 ==")
    for path in ("/test.html", "/test.js", "/index.html"):
        try:
            st, b = a.get(path)
        except Exception:                            # noqa: BLE001
            st, b = 0, b""
        check("页面 %s 能打开" % path, st == 200 and len(b) > 500, "%d 字节" % len(b))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=5173)
    ap.add_argument("--root", default=".")
    ap.add_argument("--spawn", action="store_true", help="自己起一个 build/zhuochong_preview 再测")
    args = ap.parse_args()
    base = "http://%s:%d" % (args.host, args.port)
    proc = None
    if args.spawn:
        exe = os.path.join(args.root, "build", "zhuochong_preview")
        # 预览的绑定参数是 --bind（不是 --host，写错会被静默忽略，默认绑 0.0.0.0）
        proc = subprocess.Popen([exe, "--port", str(args.port), "--root", args.root, "--bind", "127.0.0.1"],
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(40):
            time.sleep(0.25)
            try:
                urllib.request.urlopen(base + "/api/info.json", timeout=1).read()
                break
            except Exception:                        # noqa: BLE001
                pass
    try:
        run(base, args.root)
    finally:
        if proc:
            try:
                urllib.request.urlopen(base + "/api/quit", timeout=1).read()
            except Exception:                        # noqa: BLE001
                pass
            time.sleep(0.3)
            if proc.poll() is None:
                os.kill(proc.pid, signal.SIGTERM)
    print("\n合计 %d 项，%d 项不通过 → %s" %
          (len(PASS) + len(FAIL), len(FAIL), "全部通过" if not FAIL else "有问题：" + "；".join(FAIL)))
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
