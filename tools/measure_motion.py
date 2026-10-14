#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""动作幅度实测 —— 带负对照和饱和检查。

为什么要有这个工具
------------------
2026-10-14 给 8 个动作补下半身通道时，判据连废两版，两次都"看起来很漂亮"：

  第一版「腿部变化 ≥ idle 噪声底 2.0 倍」
    → 负对照 nod/focus/clicked（根本没有腿部通道）照样 1.5~1.7 倍，
      stroke 更是 5.3 倍。它量的是"切换动作"的扰动，不是"腿在动"。

  第二版「剥掉通道做 A/B」判据对了，但 sleep 报 +1%「基本没用」
    → 指标饱和：sleep 的腿部变化像素 28745 = 腿区角色像素 27137 的 106%，
      顶到天花板了。换成自方差后是 734 → 7583，10.3 倍，八个里最强的一个
      被误判成最弱。

把结论写进 LESSONS 不够 —— 下次换个场景还是会重犯。所以固化成工具：
**只要用这个脚本量，负对照和饱和检查就是自动跑的，想跳过都不行。**

用法
----
    tools/measure_motion.py --actions wave,sad,sleep --control nod
    tools/measure_motion.py --actions tiptoe --region leg --loop sleep,talk

需要预览服务在跑（make -s build/zhuochong_preview && ./build/zhuochong_preview --port 5173 ...）。
需要 PIL + numpy（~/.imgenv/bin/python3）。
"""
import argparse
import io
import json
import sys
import time
import urllib.error
import urllib.request

try:
    import numpy as np
    from PIL import Image
except ImportError:
    sys.exit("需要 pillow 和 numpy：python3 -m venv ~/.imgenv && "
             "~/.imgenv/bin/pip install pillow numpy，然后用 ~/.imgenv/bin/python3 跑")

# 区域按帧高度的比例切，换 scale 也不用改这里
REGIONS = {
    "all":  (0.00, 1.00),
    "head": (0.00, 0.30),
    "body": (0.30, 0.54),
    "leg":  (0.54, 1.00),   # 466x748 时约等于 y>=402
}
DIFF_THRESHOLD = 8          # 单通道差值超过这个才算"变了"，滤掉抗锯齿抖动
ALPHA_SOLID = 16            # alpha 超过这个算角色实体像素


class Pet:
    def __init__(self, base, rig=""):
        self.base = base.rstrip("/")
        self.rig = rig
        self._pids = None

    def get(self, path, timeout=25):
        with urllib.request.urlopen(self.base + path, timeout=timeout) as r:
            return r.read()

    def frame(self):
        # 取帧滞后一帧 —— 必须先推一帧再取，否则拿到的是上一帧
        self.get("/api/frame.png?s=100")
        raw = self.get("/api/frame.png?s=100")
        return Image.open(io.BytesIO(raw)).convert("RGBA")

    def rgb(self):
        return np.asarray(self.frame().convert("RGB"), dtype=np.int16)

    def action(self, aid):
        self.get("/api/action?id=%s" % aid)

    def info(self):
        return json.loads(self.get("/api/info.json"))

    def param_ids(self):
        if getattr(self, "_pids", None) is None:
            with io.open(self.rig, encoding="utf-8") as f:
                self._pids = [p["id"] for p in json.load(f).get("params", [])]
        return self._pids


def loop_period(rig_path, aid):
    """从 rig 里读出这个动作最慢的那条通道的周期（秒）。

    采样窗盖不住一个周期就什么都量不到 —— sleep 的 freq 写的 0.05（周期 20 秒），
    配 3 秒采样窗，再大的幅度也是一条直线。这个防呆就是为了那次。"""
    try:
        with io.open(rig_path, encoding="utf-8") as f:
            rig = json.load(f)
    except (OSError, ValueError):
        return None
    for act in rig.get("actions", []):
        if act.get("id") != aid:
            continue
        freqs = [c["freq"] for c in act.get("channels", [])
                 if isinstance(c.get("freq"), (int, float)) and c["freq"] > 0]
        return 1.0 / min(freqs) if freqs else None
    return None


def band(h, region):
    lo, hi = REGIONS[region]
    return int(h * lo), int(h * hi)


def changed(a, b, y0, y1):
    """两帧之间 [y0,y1) 行里有多少像素真的变了"""
    d = np.abs(a - b).max(axis=2) > DIFF_THRESHOLD
    return int(d[y0:y1].sum())


def ceiling(pet, region):
    """这个区域里有多少角色实体像素 —— 变化量的天花板。

    不先算出天花板就报比例，是 LESSONS 79 栽过的坑。"""
    im = np.asarray(pet.frame())
    y0, y1 = band(im.shape[0], region)
    return int((im[y0:y1, :, 3] > ALPHA_SOLID).sum())


def peak_vs_idle(pet, aid, region, frames, gap):
    """一次性动作：相对 idle 静止态的峰值差。

    循环动作 t=0 位移为 0（sine 波），所以必须连采多帧取峰值，单帧必然量不到。"""
    pet.action("idle")
    time.sleep(0.5)
    ref = pet.rgb()
    y0, y1 = band(ref.shape[0], region)
    pet.action(aid)
    time.sleep(0.10)
    peak = 0
    for _ in range(frames):
        time.sleep(gap)
        peak = max(peak, changed(pet.rgb(), ref, y0, y1))
    return peak


def self_variance(pet, aid, region, seconds, settle=2.0, gap=0.4):
    """循环动作：自方差。

    基准帧取自动作进行中（等它进入循环后再拍），量的是"维持这个状态时
    身体还动不动"。对 sleep 这种整体位移很大的动作，这是唯一有分辨力的指标。"""
    pet.action(aid)
    time.sleep(settle)
    ref = pet.rgb()
    y0, y1 = band(ref.shape[0], region)
    peak = 0
    t0 = time.time()
    while time.time() - t0 < seconds:
        peak = max(peak, changed(pet.rgb(), ref, y0, y1))
        time.sleep(gap)
    return peak



def row_shift(a, b, y, span=6):
    """第 y 行在两帧之间的水平位移（亚像素，互相关）。"""
    ra = a[y, :, 3].astype(float)
    rb = b[y, :, 3].astype(float)
    if ra.sum() < 200 or rb.sum() < 200:
        return None
    ra = ra - ra.mean()
    rb = rb - rb.mean()

    def corr(sh):
        return float(np.dot(ra, np.roll(rb, sh)))

    best, bv = 0, -1e18
    for sh in range(-span, span + 1):
        v = corr(sh)
        if v > bv:
            bv, best = v, sh
    y0, y1, y2 = corr(best - 1), corr(best), corr(best + 1)
    den = y0 - 2 * y1 + y2
    # 分母接近 0（这一行几乎没信号）时抛物线插值会炸出天文数字，
    # 必须钳住：亚像素修正按定义不可能超过半个像素。
    sub = (y0 - y2) / (2 * den) if abs(den) > 1e-9 else 0.0
    if sub < -0.5:
        sub = -0.5
    elif sub > 0.5:
        sub = 0.5
    return best + sub


def profile(pet, pid, value, step=2, span=(0.10, 0.70)):
    """逐行水平位移剖面 —— 用来查「各部分动得一不一致」。

    为什么需要它（2026-10-14 吃的亏）：
    此前所有实测都在量「动作幅度够不够大」（整帧或分区的像素差）。那量的是
    「有没有动」。用户反馈的却是「颈部会横向整体错误细微的位移，包括兜帽」——
    **幅度完全正常，是各部分之间动得不一致**，分区像素差对这种问题是瞎的。

    位移随 y 应当连续变化；**出现跳变就是接缝**。实测躯干顶边（脖子/衣领）
    相对头部跳了 0.40px，根因是 root 曲线把满额形变给了贴图顶边，而头按
    颈关节那一行刚性平移。
    """
    # 必须冻结时钟 —— 否则 idle 动画也在动，逐行位移里混进来的抖动
    # （实测 ±0.2px）比要找的接缝跳变还大，什么都看不出来。
    pet.get("/api/action?id=idle")
    pet.get("/api/pause?on=1")
    time.sleep(0.4)
    for q in pet.param_ids():
        pet.get("/api/param?id=%s&reset=1" % q)
    time.sleep(0.2)
    a = np.asarray(pet.frame())
    pet.get("/api/param?id=%s&v=%s" % (pid, value))
    time.sleep(0.25)
    b = np.asarray(pet.frame())
    h = a.shape[0]
    rows = []
    for fy in range(int(h * span[0]), int(h * span[1]), step):
        s = row_shift(a, b, fy)
        if s is not None:
            rows.append((fy, s))
    return rows


def main():
    ap = argparse.ArgumentParser(description="动作幅度实测（带负对照和饱和检查）")
    ap.add_argument("--base", default="http://127.0.0.1:5173")
    ap.add_argument("--actions", default="", help="逗号分隔的动作 id")
    ap.add_argument("--profile", default="",
                    help="改查『一致性』：给一个参数 id，输出逐行水平位移剖面。"
                         "位移应随 y 连续变化，跳变=接缝（颈部滑移就是这么查出来的）")
    ap.add_argument("--profile-value", default="1.0", help="--profile 时把参数置到多少")
    ap.add_argument("--jump", type=float, default=0.25,
                    help="相邻采样行位移差超过这个就标记为跳变（像素）")
    ap.add_argument("--control", default="nod",
                    help="负对照动作：一个确定不受本次改动影响的动作。"
                         "它的读数就是测量误差底，低于它的结果一律不算数")
    ap.add_argument("--region", default="leg", choices=sorted(REGIONS))
    ap.add_argument("--loop", default="",
                    help="逗号分隔：哪些是循环动作（用自方差量）。"
                         "一次性动作和循环动作不能用同一个指标")
    ap.add_argument("--frames", type=int, default=10)
    ap.add_argument("--gap", type=float, default=0.14)
    ap.add_argument("--loop-seconds", type=float, default=12.0)
    ap.add_argument("--json", default="", help="把结果写到这个文件，方便做 A/B 相减")
    ap.add_argument("--rig", default="characters/xiaoxun/forms/teen/rig.json",
                    help="用来核对循环动作的周期，确认采样窗盖得住")
    a = ap.parse_args()

    pet = Pet(a.base, a.rig)
    try:
        info = pet.info()
    except (urllib.error.URLError, OSError) as e:
        sys.exit("连不上预览服务 %s：%s\n先启动：./build/zhuochong_preview "
                 "--port 5173 --root . --host 0.0.0.0" % (a.base, e))

    if a.profile:
      try:
        rows = profile(pet, a.profile, a.profile_value)
        print("逐行水平位移剖面：%s = %s" % (a.profile, a.profile_value))
        print("位移应随 y 连续变化，**跳变就是接缝**\n")
        print("%8s %10s  %s" % ("帧行", "位移px", "图示"))
        print("-" * 56)
        prev, jumps = None, []
        for fy, sh in rows:
            mark = ""
            if prev is not None and abs(sh - prev) > a.jump:
                mark = "  ★ 跳变 %+.2f" % (sh - prev)
                jumps.append((fy, sh - prev))
            bar = "#" * min(60, int(abs(sh) * 8))
            print("%8d %10.2f  %s%s" % (fy, sh, bar, mark))
            prev = sh
        print("-" * 56)
        if jumps:
            print("发现 %d 处跳变：%s" % (len(jumps),
                  "、".join("帧行%d 差%+.2f" % j for j in jumps)))
            print("跳变处两侧属于不同的部件/组，它们动得不一致 —— 那里会看到接缝。")
        else:
            print("没有超过 %.2fpx 的跳变，各部分动得一致。" % a.jump)
        for q in pet.param_ids():
            pet.get("/api/param?id=%s&reset=1" % q)
        pet.get("/api/pause?on=0")      # 一定要解冻，崩在这里会把引擎时钟留在停摆状态
      finally:
        pet.get("/api/pause?on=0")
      return

    loops = {s for s in a.loop.split(",") if s}
    acts = [s for s in a.actions.split(",") if s]
    if not acts:
        sys.exit("要么给 --actions，要么给 --profile")
    cap = ceiling(pet, a.region)

    print("帧 %dx%d  scale %s  区域 %s（占全帧 %.0f%%~%.0f%%）"
          % (info["frame_w"], info["frame_h"], info["scale"], a.region,
             REGIONS[a.region][0] * 100, REGIONS[a.region][1] * 100))
    print("该区域角色实体像素 %d ← 变化量的天花板，贴顶就说明指标没分辨力\n" % cap)

    results = {}
    try:
        # 负对照先跑 —— 没有它，后面的数字都没有参照系
        ctrl = peak_vs_idle(pet, a.control, a.region, a.frames, a.gap)
        results[a.control] = ctrl
        print("负对照 %s：%d 像素 ← 混淆底" % (a.control, ctrl))
        print("  这个动作不碰目标区域的参数，它的读数全部来自『整体位移把该区域像素带着变』。")
        print("  单边测量只要没明显超过它，就不能把效果归因到新通道上。\n")

        print("%-14s %-6s %9s %9s %8s  %s"
              % ("动作", "类型", "变化像素", "比混淆底", "占天花板", "判定"))
        print("-" * 68)
        for aid in acts:
            if aid in loops:
                period = loop_period(a.rig, aid)
                if period and a.loop_seconds < period:
                    print("   !! %s 最慢通道周期 %.0f 秒，而采样窗只有 %.0f 秒 —— "
                          "盖不住一个周期，量到的会偏小。建议 --loop-seconds %d"
                          % (aid, period, a.loop_seconds, int(period * 1.2) + 1))
                v = self_variance(pet, aid, a.region, a.loop_seconds)
                kind = "循环"
            else:
                v = peak_vs_idle(pet, aid, a.region, a.frames, a.gap)
                kind = "一次性"
            results[aid] = v
            ratio = v / max(ctrl, 1)
            sat = v / max(cap, 1)
            if sat > 0.85:
                verdict = "!! 指标饱和，加 --loop 用自方差重测"
            elif ratio >= 2.0:
                verdict = "明显超过混淆底"
            elif ratio >= 1.3:
                verdict = "略高于混淆底，需 A/B 确认"
            else:
                verdict = "!! 混淆底量级，单边测不出，必须 A/B"
            print("%-14s %-6s %9d %8.1fx %7.0f%%  %s"
                  % (aid, kind, v, ratio, sat * 100, verdict))
        print("-" * 68)
        print("注：要确认效果真来自某批通道，还得做 A/B —— 把那批通道从 rig.json 剥掉，")
        print("    重启服务再跑一次本脚本（--json 存两份相减）。只看单边数字不足以下结论。")
    finally:
        try:
            pet.action("idle")
            print("\n[收尾] 已复位 idle")
        except Exception as e:                     # noqa: BLE001 - 收尾失败不能盖住主结果
            print("\n[收尾] 复位失败：%s" % e)

    if a.json:
        with io.open(a.json, "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=1)
        print("结果已写入 %s" % a.json)


if __name__ == "__main__":
    main()
