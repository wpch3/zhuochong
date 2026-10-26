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
import io
import json
import os
import re
import signal
import subprocess
import sys
import time
import urllib.parse
import urllib.error
import urllib.request
import struct
import zlib

from PIL import Image

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

    def json_any(self, path):
        """4xx 也要拿到响应体（有些端点用 400 表示"合法地拒绝"，见记忆写入的 t 越界）。"""
        try:
            st, b = self.get(path)
            return st, json.loads(b.decode("utf-8"))
        except urllib.error.HTTPError as e:
            try:
                return e.code, json.loads(e.read().decode("utf-8"))
            except Exception:                        # noqa: BLE001
                return e.code, {}

    def code(self, path):
        """只要状态码（404 也算正常返回，不当异常）。"""
        try:
            st, _ = self.get(path)
            return st
        except urllib.error.HTTPError as e:
            return e.code
        except Exception:                            # noqa: BLE001
            return 0

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

    # ---- 单测的 stub 不能比真服务宽松（教训 60 的系统性修法）----
    # web-test 跑的是一份假的 info.json。真服务加了字段而 stub 没跟上时，
    # 组件在单测里好好的，一上真服务就取到 undefined。这里拿真响应反查 stub。
    print("== 测试替身与真服务的字段集 ==")
    tw = os.path.join(root, "tests/test_web.js")
    if os.path.exists(tw):
        with open(tw, encoding="utf-8") as _f:
            src = _f.read()
        m = re.search(r"const INFO = \{(.*?)\n\};", src, re.S)
        if m:
            stub_keys = set(re.findall(r"[\{\s,]([A-Za-z_][A-Za-z0-9_]*)\s*:", m.group(1)))
            # 只管组件真的会读的那些（_ 开头的内部字段和纯数值统计不算）
            real = set(info.keys())
            # 这几个是每帧都在变的运行时状态，stub 里没有也不影响组件逻辑
            runtime = {"blink", "idle", "sleeping", "reason", "root", "character",
                       "frame_w", "frame_h", "blink_manual", "engine", "tier",
                       "affection", "viseme_weight", "expression"}
            missing = sorted((real - stub_keys) - runtime)
            check("web-test 的 INFO 替身覆盖真服务字段", not missing,
                  "stub 缺 %s —— 组件在单测里读不到这些，上真服务才暴露" % missing)

    # ---- 立绘能力回归（G65）：底层做了的，要确认真能被外部驱动 ----
    # 判据是"设进去能读回来"，不是"接口返回 200"。今天踩过的坑：参数名写错时
    # 端点照样回 ok:true，功能静默失效。
    print("== 立绘能力：每一项都要真能驱动 ==")
    a.get("/api/pause?on=0")                     # 时钟必须走，look 类参数靠 dt 收敛
    a.get("/api/param?all=1")
    pj = a.json("/api/params.json")
    plist = pj.get("params", [])
    check("参数表非空", len(plist) >= 30, "%d 个" % len(plist))

    # 每个参数都应该能设进去。look 类（ParamAngleX/Y）是平滑收敛的，给它时间。
    import time as _t
    drive_bad = []
    for d in plist:
        pid, lo, hi = d["id"], d["min"], d["max"]
        tgt = hi if abs(hi) >= abs(lo) else lo       # 挑幅度大的那一端
        if tgt == d["default"]:
            tgt = lo if hi == d["default"] else hi
        if tgt == d["default"]:
            continue                                  # 区间退化，没法测
        a.get("/api/param?id=%s&v=%s" % (pid, tgt))
        got = None
        for _ in range(12):                           # look 类要等收敛
            _t.sleep(0.05)
            cur = [x for x in a.json("/api/params.json")["params"] if x["id"] == pid]
            if cur and abs(cur[0]["value"] - tgt) < max(abs(tgt) * 0.05, 0.02):
                got = cur[0]["value"]
                break
            got = cur[0]["value"] if cur else None
        if got is None or abs(got - tgt) > max(abs(tgt) * 0.05, 0.02):
            drive_bad.append("%s 设 %.2f 只到 %s" % (pid, tgt, got))
        a.get("/api/param?id=%s&reset=1" % pid)
    check("每个参数都能被设进去", not drive_bad,
          "；".join(drive_bad[:3]) if drive_bad else "%d 个参数逐个设过" % len(plist))
    a.get("/api/param?all=1")

    info2 = a.json("/api/info.json")
    sc_boot = info2.get("scale", 1.0)       # 启动时的缩放，用例跑完要还原回去
    # 表情：每个都要能切进去，而且切完 info 要如实报告
    exp_bad = []
    for e in info2.get("expressions", []):
        a.get("/api/expression?id=" + e["id"])
        if a.json("/api/info.json").get("expression") != e["id"]:
            exp_bad.append(e["id"])
    a.get("/api/expression?off=1")
    check("每个表情都能切换", not exp_bad, str(exp_bad))
    check("表情能取消", a.json("/api/info.json").get("expression") == "", "")

    # 口型：7 个音素。参数名是 v=音素&w=音量（不是 id/v —— 今天就栽在这）
    vis_bad = []
    for v in info2.get("visemes", []):
        r = a.json("/api/viseme?v=%s&w=1" % v)
        # SIL 是静默（闭嘴），语义上等于松口 —— 引擎把它归零并交还嘴形控制权，
        # 所以 viseme 回空串、weight 回 0 是对的，不是没生效。
        want = "" if v == "SIL" else v
        if not r.get("ok") or r.get("viseme") != want:
            vis_bad.append("%s→%r" % (v, r.get("viseme")))
    a.get("/api/viseme?v=off")
    check("每个口型都能驱动", not vis_bad, str(vis_bad))

    # —— 交互区域（G67）——
    # info 要报区域表和画布尺寸，否则前端只能把 head/body/feet 和 848x1360 硬编码。
    regs = info2.get("regions") or []
    check("info 报了区域表", len(regs) >= 1, "regions=%d" % len(regs))
    check("info 报了画布尺寸",
          info2.get("canvas_w", 0) > 0 and info2.get("canvas_h", 0) > 0,
          "canvas=%sx%s" % (info2.get("canvas_w"), info2.get("canvas_h")))
    for g in regs:
        for k in ("id", "action", "cursor", "rect"):
            if k not in g:
                check("区域字段齐全", False, "%s 缺 %s" % (g.get("id"), k))
                break
        else:
            check("区域 %s 字段齐全" % g["id"], len(g["rect"]) == 4, str(g["rect"]))

    # 自洽性：把区域矩形的中心换算成帧坐标，/api/region 必须命中它自己。
    # 2026-10-14 踩过：head 区域只到画布 y=310，而脸画到 y=385，下半张脸被判成 body
    #（点嘴巴触发的是「摸身体」）。那种偏移光看接口返回 ok 是发现不了的。
    cw, ch = info2.get("canvas_w", 0), info2.get("canvas_h", 0)
    fw, fh = info2.get("frame_w", 0), info2.get("frame_h", 0)
    if cw and ch and fw and fh:
        for g in regs:
            x, y, w, h = g["rect"]
            # 按网格采样，不用矩形中心：角色是非凸形状，feet 的矩形中心正好落在
            # 两腿之间的空隙上（alpha=0），而命中测试要求不透明像素，中心必然落空。
            hits, acts = {}, {}
            for i in range(1, 5):
                for j in range(1, 5):
                    fx = int((x + w * i / 5.0) / cw * fw)
                    fy = int((y + h * j / 5.0) / ch * fh)
                    r = a.json("/api/region?x=%d&y=%d" % (fx, fy))
                    rid = r.get("region") or ""
                    if rid:
                        hits[rid] = hits.get(rid, 0) + 1
                        acts[rid] = r.get("action")
            check("区域 %s 点得到" % g["id"], hits.get(g["id"], 0) > 0,
                  "矩形内 16 个采样点一个都没命中它自己（命中分布 %s）；"
                  "要么矩形画在角色外面，要么被别的区域整个盖住" % (hits or "全空"))
            check("区域 %s 不串台" % g["id"], set(hits) <= {g["id"]},
                  "矩形内还命中了别的区域 %s（区域之间不该重叠）"
                  % sorted(set(hits) - {g["id"]}))
            if hits.get(g["id"]):
                check("区域 %s 报对了动作" % g["id"], acts.get(g["id"]) == g["action"],
                      "%r != %r" % (acts.get(g["id"]), g["action"]))
        # 画面外必须不命中，否则光标到处变手型
        r0 = a.json("/api/region?x=2&y=2")
        check("画面角落不命中任何区域", not r0.get("region"),
              "左上角回了 %r" % r0.get("region"))
        # 坐标系必须是写明的，不能靠猜：同一个点用两套坐标问，答案要一样。
        # 2026-10-15 之前这里只有一套隐式坐标系，而且**渲染过和没渲染过不是同一套**。
        g0 = regs[0]
        cx = g0["rect"][0] + g0["rect"][2] // 2
        cy = g0["rect"][1] + g0["rect"][3] // 3   # 1/3 高：头区取脸，不取发顶空隙
        rc = a.json("/api/region?x=%d&y=%d&space=canvas" % (cx, cy))
        rf = a.json("/api/region?x=%d&y=%d" % (int(cx * fw / cw), int(cy * fh / ch)))
        check("space=canvas 回报 canvas", rc.get("space") == "canvas",
              "回了 %r" % rc.get("space"))
        check("不写 space 默认是 frame", rf.get("space") == "frame",
              "回了 %r" % rf.get("space"))
        check("同一点两套坐标给同一个答案",
              rc.get("region") == rf.get("region") and rc.get("region") == g0["id"],
              "canvas 回 %r / frame 回 %r，期望都是 %r"
              % (rc.get("region"), rf.get("region"), g0["id"]))
        check("答复要回报换算后的画布坐标",
              abs(rf.get("cx", -999) - cx) <= 3 and abs(rf.get("cy", -999) - cy) <= 3,
              "帧坐标换回画布是 (%s,%s)，期望 ≈(%d,%d)"
              % (rf.get("cx"), rf.get("cy"), cx, cy))

    # 换一个 scale 再测一遍：region/poke 吃的是**引擎帧缓冲**坐标（画布 × pet scale），
    # 而前端图片的尺寸是画布 × 画质档 s%。两者只在碰巧相等时一致，
    # 代码里拿 img.naturalWidth 换算就会整体点偏 —— 这条闸专门拦这个。
    sc0 = info2.get("scale", 1.0)
    try:
        a.get("/api/scale?s=1.0")   # 参数名是 s，值是比例不是百分比
        i3 = a.json("/api/info.json")
        fw3, fh3 = i3["frame_w"], i3["frame_h"]
        check("scale 改了帧尺寸要跟着变", (fw3, fh3) != (fw, fh) or abs(sc0 - 1.0) < 1e-6,
              "scale=1.0 时 frame=%dx%d（原 %dx%d）" % (fw3, fh3, fw, fh))
        ok_after = 0
        for g in regs:
            x, y, w, h = g["rect"]
            for i in range(1, 5):
                for j in range(1, 5):
                    fx = int((x + w * i / 5.0) / cw * fw3)
                    fy = int((y + h * j / 5.0) / ch * fh3)
                    if a.json("/api/region?x=%d&y=%d" % (fx, fy)).get("region") == g["id"]:
                        ok_after += 1
                        break
                else:
                    continue
                break
        check("换 scale 后区域仍然点得到", ok_after == len(regs),
              "%d/%d 个区域在 scale=1.0 下还能命中（坐标换算必须按 info.frame_w/h 走）"
              % (ok_after, len(regs)))
        # 改完 scale 必须渲染一帧，帧缓冲才会变成新尺寸。
        # info.frame_w/h 是立刻就报新值的，但 fb 要等下一帧 —— 这中间 hover/region
        # 的入参坐标系和 info 报的对不上，点击会偏。这条闸把这个时序钉住。
        a.get("/api/frame.png?s=100")
        i4 = a.json("/api/info.json")
        check("渲染一帧后 info 和帧缓冲尺寸对得上",
              a.json("/api/region?x=%d&y=%d" % (int(i4["frame_w"] * 0.5),
                                                int(i4["frame_h"] * 0.12))).get("region")
              in ("head", "body"),
              "按 info.frame_w/h 取的点落到了 %r（scale 改完没渲染就用，坐标系会错位）"
              % a.json("/api/region?x=%d&y=%d" % (int(i4["frame_w"] * 0.5),
                                                  int(i4["frame_h"] * 0.12))).get("region"))
    finally:
        a.get("/api/scale?s=%.3f" % sc0)   # 还原，别把状态漏给后面的用例
        a.get("/api/frame.png?s=100")      # 还原后同样要推一帧，让 fb 跟上

    # —— 视线跟随 hover（G67）——
    # 参数名是 x/y/in（不是 on/inside）。hover 走 dt 收敛，要给它时间。
    a.get("/api/pause?on=0")
    a.get("/api/idle?s=0")        # 前面的用例会把空闲时间推到 99999 把角色弄睡着，
    a.get("/api/action?id=idle")  # 睡着时不跟视线，hover 看起来就像坏了
    a.get("/api/gaze?x=0&y=0")
    time.sleep(0.4)
    a.get("/api/hover?x=%d&y=%d&in=1" % (int(fw * 0.92), int(fh * 0.10)))
    time.sleep(0.9)
    pv = {p_["id"]: p_["value"] for p_ in a.json("/api/params.json")["params"]}
    check("hover 能把头转过去", pv.get("ParamAngleX", 0) > 5,
          "ParamAngleX=%.2f（hover 到右上角后应该明显为正）" % pv.get("ParamAngleX", 0))
    check("hover 能带动眼球", abs(pv.get("ParamEyeBallX", 0)) > 0.2,
          "ParamEyeBallX=%.2f" % pv.get("ParamEyeBallX", 0))
    a.get("/api/hover?x=0&y=0&in=0")
    time.sleep(0.6)
    pv2 = {p_["id"]: p_["value"] for p_ in a.json("/api/params.json")["params"]}
    check("鼠标移出后眼球回正", abs(pv2.get("ParamEyeBallX", 1)) < 0.2,
          "ParamEyeBallX=%.2f" % pv2.get("ParamEyeBallX", 1))

    # —— 台词口型 speak（G67）——
    man = a.json("/voice_manifest.json")
    mlines = man.get("lines") or []
    check("台词清单可读", len(mlines) > 0, "lines=%d" % len(mlines))
    if mlines:
        sid = mlines[0]["id"] + "_" + (mlines[0].get("variant") or "base0")
        r = a.json("/api/speak?id=%s" % sid)
        check("台词能播", r.get("ok") and r.get("text"),
              "speak(%s) → %r" % (sid, r))
        check("台词返回时长", float(r.get("remain", 0)) > 0, str(r.get("remain")))
        lv = []
        for _ in range(6):
            time.sleep(0.15)
            lv.append(a.json("/api/speech.json").get("lipsync", {}).get("level", 0))
        check("口型包络在动", max(lv) > 0.05 and len(set(round(v, 2) for v in lv)) > 1,
              "电平序列 %s（全 0 或恒定说明包络没驱动嘴）" % [round(v, 3) for v in lv])
        st = a.json("/api/speak?stop=1")
        check("台词能停", st.get("stopped") is True, str(st))
        time.sleep(0.1)
        check("停了之后口型退出", not a.json("/api/speech.json")
              .get("lipsync", {}).get("active", True), "")
        # 不存在的台词必须 404，不能回 200 假装成功（那样前端永远发现不了 id 写错）
        check("不存在的台词回 404", a.code("/api/speak?id=__no_such_line__") == 404,
              "实际 %s" % a.code("/api/speak?id=__no_such_line__"))

    # 互斥差分：每个档位 + 整组关掉
    pose_bad = []
    for g in info2.get("poses", []):
        for e in list(g["entries"]) + ["none"]:
            r = a.json("/api/pose?group=%s&id=%s" % (g["id"], e))
            if not r.get("ok"):
                pose_bad.append("%s/%s" % (g["id"], e))
        a.get("/api/pose?group=%s&id=%s" % (g["id"], g["entries"][0]))
    check("每个差分档位都能切", not pose_bad, str(pose_bad))

    # 动作：info 列出来的都要能触发，外加 idle/sleep 这两个没列出来的
    act_bad = []
    for act in list(info2.get("actions", [])) + ["idle", "sleep"]:
        if not a.json("/api/action?id=" + act).get("ok"):
            act_bad.append(act)
    a.get("/api/action?id=idle")
    check("每个动作都能触发（含隐藏的 idle/sleep）", not act_bad, str(act_bad))

    # 视线：gaze 要能驱动眼球参数
    a.get("/api/gaze?x=0.9&y=0.3")
    _t.sleep(0.25)
    eb = [x for x in a.json("/api/params.json")["params"] if x["id"] == "ParamEyeBallX"]
    check("视线能驱动眼球", bool(eb) and abs(eb[0]["value"] - 0.9) < 0.05,
          "ParamEyeBallX=%s" % (eb[0]["value"] if eb else "?"))
    a.get("/api/gaze?off=1")

    print("== 网关（G51） ==")
    # ---- /api/route：双路由沙盘（DC18 / G99）----
    # 这里用的是真配置（云端默认关着），所以看到的主要是"本地兜住了"；
    # 三支柱的完整分叉在 test_core 里用自造路由表验（真表验不全）。
    rt = a.json("/api/route?cap=chat.completion")
    check("route 端点能读", isinstance(rt, dict) and "reason" in rt)
    check("默认短请求留在本地", rt.get("local") is True,
          "%s / %s" % (rt.get("provider"), rt.get("reason")))
    check("阈值要报出来（不是写死在代码里）",
          (rt.get("rules") or {}).get("tokens_cloud", 0) > 0,
          str(rt.get("rules")))
    sens = a.json("/api/route?cap=chat.completion&sensitive=1")
    check("敏感请求的落点必须是本地或拒绝，绝不是云端",
          sens.get("local") is True or sens.get("blocked_sensitive") is True,
          "provider=%s reason=%s" % (sens.get("provider"), sens.get("reason")))
    check("敏感请求的理由要写明白", sens.get("reason") in ("sensitive_local", "sensitive_blocked"),
          sens.get("reason"))
    down = a.json("/api/route?cap=chat.completion&tokens=4000&cloud_down=1")
    check("云端挂了要退回本地而不是失败", down.get("ok") is True and down.get("local") is True,
          down.get("reason"))
    miss = a.json("/api/route?cap=nobody.does.this")
    check("没人提供的能力要老实说不行", miss.get("ok") is False, str(miss.get("reason")))
    # 自动判重活（DC27）：同一个端点，光换文本就该换判定
    chat = a.json("/api/route?cap=chat.completion&q=" + urllib.parse.quote("陪我聊聊天"))
    code = a.json("/api/route?cap=chat.completion&q=" + urllib.parse.quote("帮我写个快速排序函数"))
    check("闲聊判成简单活", chat.get("task") == "simple", str(chat.get("task_hit")))
    check("写代码判成重活", code.get("task") == "heavy", str(code.get("task_hit")))
    check("要说得出凭哪个词判的", bool(code.get("task_hit")),
          "界面要解释给用户听，不能只给 heavy")

    st = (a.json("/api/route?cap=chat.completion") or {}).get("stats") or {}
    check("决策要记账（为了事后重标阈值）", st.get("local", 0) + st.get("cloud", 0) > 0,
          str(st))

    # 记账只记在内存里，一重启就没了 —— 阈值要重标就必须落盘（G99/DC18）。
    # 这里验的是端到端那一段：服务端真的在往 data/usage.jsonl 追行。
    ulog = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "data", "usage.jsonl")
    def _ulines():
        try:
            with open(ulog, "rb") as f:
                return f.read().count(b"\n")
        except IOError:
            return -1
    before = _ulines()
    a.json("/api/route?cap=chat.completion&tokens=1234")
    after = _ulines()
    check("路由决策要落盘到 data/usage.jsonl", after > before >= 0,
          "落盘前 %d 行、后 %d 行（-1 = 文件压根没建）" % (before, after))
    if after > 0:
        try:
            with open(ulog, "rb") as f:
                last = f.read().strip().split(b"\n")[-1].decode("utf-8")
            rec = json.loads(last)
        except Exception as e:
            rec = {}
            check("流水最后一行要是能解析的 JSON", False, str(e))
        if rec:
            check("流水要记下 token 数（重标 512 那条阈值全靠它）",
                  rec.get("tokens") == 1234, str(rec.get("tokens")))
            check("流水要记下理由", bool(rec.get("reason")), str(rec))

    gw = a.json("/api/gateway.json")
    check("gateway.json 能读", isinstance(gw, dict) and "loaded" in gw)
    check("路由表要真的加载上", gw.get("loaded") is True,
          "%d 条路由，策略 %s" % (gw.get("routes", 0), gw.get("strategy")))
    check("策略应是 prefer_local（本机优先）", gw.get("strategy") == "prefer_local")
    caps = {c["cap"]: c for c in gw.get("caps", [])}
    check("网关要报告能力状态", len(caps) >= 10, "%d 种" % len(caps))
    # 用户点名的能力必须都在这张表里有交代，哪怕交代的是"还没接入"
    for want in ("chat.completion", "image.generate", "video.generate",
                 "code.generate", "model3d.generate"):
        check("能力 %s 有状态交代" % want, want in caps,
              caps.get(want, {}).get("state", "缺失"))
    chat = caps.get("chat.completion", {})
    check("对话应路由到本机 ollama", chat.get("state") == "ready"
          and chat.get("provider") == "ollama" and chat.get("local") is True,
          "%s → %s" % (chat.get("state"), chat.get("provider")))
    # 状态值只有三种，不能冒出别的——界面是按这三种写话术的
    bad_state = [c for c in gw.get("caps", []) if c.get("state") not in ("ready", "disabled", "missing")]
    check("能力状态只能是 ready/disabled/missing", not bad_state,
          str([c.get("state") for c in bad_state]))
    # 没路由到供应商时不许留下残缺字段（界面会直接拼进字符串）
    ghost = [c for c in gw.get("caps", []) if c.get("state") != "ready" and c.get("provider")]
    check("没选中供应商时 provider 必须是空的", not ghost, str(ghost))
    led = gw.get("ledger") or {}
    for k in ("spent", "held", "tokens_in", "tokens_out", "calls", "failed"):
        check("账本有 %s" % k, k in led)
    check("新进程的账本应是干净的", led.get("spent") == 0 and led.get("calls") == 0)

    # /api/chat 这一段必须排在「新进程的账本应是干净的」后面：真发一次就会记一笔账，
    # 而用户自己机器上本地模型多半是开着的 —— 那样这段会真的成功、真的记账，
    # 把上面那条干净账本的断言冲红。顺序本身就是测试的一部分。
    # ---- /api/chat：真的把话发出去那一段（G54）----
    # 在这之前，网关只会"选谁"，选完就没下文了 —— 人设提示词一个字节都没出过门。
    # 冒烟机上没有模型在跑，所以这里主要验两件事：
    #   ① dry-run（只看不发）给出的"将要发什么"是不是真的对；
    #   ② 真发失败时，说的是不是人话、有没有谎报成功。
    def chat(path):
        """/api/chat 失败时会回 502，a.json 会抛 —— 这里要连状态码一起拿。"""
        try:
            st, b = a.get(path, timeout=10.0)
        except urllib.error.HTTPError as e:
            st, b = e.code, e.read()
        try:
            return st, json.loads(b.decode("utf-8"))
        except Exception:                            # noqa: BLE001
            return st, {}

    HI = urllib.parse.quote("你今天过得怎么样")
    st, _ = chat("/api/chat")
    check("chat 不给 text 要回 400", st == 400, "实际 %s" % st)

    st, d = chat("/api/chat?dry=1&text=" + HI)
    check("chat dry-run 能用", st == 200 and d.get("ok") is True, "%s %s" % (st, d.get("error")))
    check("dry-run 要说清会发给谁", d.get("provider") == "ollama" and d.get("local") is True,
          "%s local=%s" % (d.get("provider"), d.get("local")))
    check("dry-run 一个字节都没发（http_status 必须是 0）", d.get("http_status") == 0,
          str(d.get("http_status")))
    check("dry-run 要给出目标地址", "127.0.0.1:11434" in (d.get("url") or ""), str(d.get("url")))
    try:
        rb = json.loads(d.get("request_body") or "{}")
    except Exception as e:                           # noqa: BLE001
        rb = {}
        check("dry-run 给的请求体得是合法 JSON", False, str(e))
    msgs = rb.get("messages") or []
    roles = [m.get("role") for m in msgs]
    check("请求体带 model", rb.get("model") == "qwen2.5:7b", str(rb.get("model")))
    check("请求体必须显式写 stream:false（不写有的中转站会回 SSE）",
          rb.get("stream") is False, str(rb.get("stream")))
    check("请求体要有 system + user 两条消息", roles == ["system", "user"], str(roles))
    if len(msgs) == 2:
        check("★ 人设真的进了 system（这是 G54 之前整条断掉的那一段）",
              "小寻" in msgs[0].get("content", ""),
              msgs[0].get("content", "")[:40])
        check("用户原话要原样送达、不许被改写",
              msgs[1].get("content") == "你今天过得怎么样", msgs[1].get("content"))
    check("人设字数要如实报出来", (d.get("persona_bytes") or 0) > 100, str(d.get("persona_bytes")))
    # 密钥绝不许出现在给界面看的东西里
    blob = (d.get("url") or "") + (d.get("request_body") or "")
    check("★ dry-run 的输出里不许夹带密钥",
          "Authorization" not in blob and "Bearer" not in blob and "sk-" not in blob)

    st, d0 = chat("/api/chat?dry=1&persona=0&text=" + HI)
    try:
        rb0 = json.loads(d0.get("request_body") or "{}")
    except Exception:                                # noqa: BLE001
        rb0 = {}
    check("persona=0 要真的不带人设", d0.get("persona_bytes") == 0
          and [m.get("role") for m in (rb0.get("messages") or [])] == ["user"],
          "persona_bytes=%s" % d0.get("persona_bytes"))

    st, ds = chat("/api/chat?dry=1&sensitive=1&text=" + HI)
    check("带隐私标记时落点必须是本地", ds.get("local") is True
          and ds.get("reason") == "sensitive_local",
          "%s / %s" % (ds.get("provider"), ds.get("reason")))

    # dry-run 不许动账本：它根本没发请求，记一笔调用就是在骗人
    led0 = (a.json("/api/gateway.json") or {}).get("ledger") or {}
    chat("/api/chat?dry=1&text=" + HI)
    led1 = (a.json("/api/gateway.json") or {}).get("ledger") or {}
    check("dry-run 不许记调用数", led1.get("calls") == led0.get("calls"),
          "%s → %s" % (led0.get("calls"), led1.get("calls")))
    check("dry-run 不许留悬空预扣", (led1.get("held") or 0) == 0, str(led1.get("held")))

    # 真发一次。冒烟机上没有本地模型 ⇒ 必须老实失败。
    # 这里不假设一定失败：万一机器上真跑着 ollama，成功也算对，但不许"假成功"。
    st, dr = chat("/api/chat?timeout=2500&text=" + HI)
    if dr.get("ok") is True:
        check("真发成功时必须带回正文", bool(dr.get("text")) and st == 200, str(st))
        check("真发成功时 http_status 要是 2xx", 200 <= (dr.get("http_status") or 0) < 300,
              str(dr.get("http_status")))
    else:
        check("本地模型没开时要回 502、不许伪装成 200", st == 502, "实际 %s" % st)
        check("没发出去时 http_status 要是 0", dr.get("http_status") == 0,
              str(dr.get("http_status")))
        # 失败的样子不止一种：没开是"连不上"，开着但慢是"等太久"。
        # 这条要守的是**意图**——说人话 + 带上地址，而不是某一句特定措辞。
        # （2026-10-24 踩到：挂个慢模型跑这条就红，其实软件没毛病。）
        _err = dr.get("error") or ""
        check("失败要说人话、带上地址（不是裸 errno）",
              "11434" in _err and any("\u4e00" <= ch <= "\u9fff" for ch in _err),
              _err)
        check("失败不许留悬空预扣",
              ((a.json("/api/gateway.json") or {}).get("ledger") or {}).get("held") == 0)

    # ---- /api/context.json：上下文清单（T60.1）----
    # 这个端点存在的理由：在它之前，"这次请求到底带了什么上去"没人答得上来。
    # 清单必须可打印、可 diff —— 这是 T60.1 的验收条件本身。
    print("== 上下文清单（T60.1）：这次带了什么上去，必须说得清 ==")
    a.get("/api/context.json?reset=1")
    cx = a.json("/api/context.json")
    check("context.json 能读", isinstance(cx, dict) and cx.get("ok") is True)
    check("清空后历史为 0 轮", cx.get("turns") == 0, str(cx.get("turns")))
    man = cx.get("manifest") or ""
    check("清单是给人看的纯文本", "上下文清单" in man and "合计" in man, man[:60])
    check("清单要列出人设那一块", any(b.get("id") == "persona" for b in cx.get("blocks", [])),
          str([b.get("id") for b in cx.get("blocks", [])]))
    check("人设必须是 pinned（永不被裁）",
          all(b.get("pinned") for b in cx.get("blocks", []) if b.get("id") == "persona"))

    # 可 diff：同样状态下连读两次，清单必须逐字节一样
    man2 = (a.json("/api/context.json") or {}).get("manifest") or ""
    check("同样状态读两次，清单必须一模一样（否则没法 diff）", man == man2)

    # ---- 多轮（T61.11）：她要记得住上一句 ----
    print("== 多轮上下文（T61.11）：她得记住刚才说了什么 ==")
    a.get("/api/context.json?reset=1")
    _st1, r1 = chat("/api/chat?timeout=2500&text=%E6%88%91%E5%8F%AB%E9%98%BF%E4%BC%9F&persona=0")
    if r1.get("ok"):
        # 本机有模型在跑才验得了多轮
        check("第一句没有历史可带", r1.get("history_sent") == 0, str(r1.get("history_sent")))
        _st2, r2 = chat("/api/chat?timeout=2500&text=%E6%88%91%E5%8F%AB%E4%BB%80%E4%B9%88&persona=0")
        check("第二句要把前一轮带上", r2.get("history_sent", 0) >= 2,
              "带了 %s 条" % r2.get("history_sent"))
        cx2 = a.json("/api/context.json")
        check("历史要能逐条看到，不是只给个数字",
              len(cx2.get("history", [])) >= 2, str(len(cx2.get("history", []))))
        roles = [h.get("role") for h in cx2.get("history", [])]
        check("她说过的话 role 要记成 assistant", "assistant" in roles, str(roles))
        _st3, r3 = chat("/api/chat?timeout=2500&text=hi&persona=0&history=0")
        check("history=0 要能关掉多轮", r3.get("history_sent") == 0)
    else:
        # 没有本地模型时真发验不了 —— 说清楚是"没验"，不是"通过"
        print("     （本机没有模型在跑，多轮的真发用例跳过——跳过≠通过）")
        check("没有模型时也要如实报失败，不许伪装成 200", r1.get("ok") is False)
        # 但 dry-run 不需要模型，多轮的拼装照样能验
        _std, rd = chat("/api/chat?dry=1&text=hi&persona=0")
        check("dry-run 不需要模型也能看到多轮字段", "history_sent" in rd, str(sorted(rd)[:6]))
    a.get("/api/context.json?reset=1")   # 把历史清掉，别影响后面的用例

    h0, n0 = a.frame_hash()
    check("frame.png 是张真图", n0 > 2000, "%d 字节 %dx%d" % (n0, info["frame_w"], info["frame_h"]))

    print("== PNG 并行编码：浏览器用的标准解码器必须认这个流 ==")
    # T30.2：PNG 的 deflate 现在是**多段并行压完再按字节拼接**的。
    # 自己编自己解很容易两边一起错，所以这里用 Python 自带的 zlib（和浏览器同一类
    # 标准实现，完全独立于我们的 C 代码）把流整个解出来，并逐项验：
    #   结构 / 每个 chunk 的 CRC32 / deflate 流正常终止 / adler32 / 反滤波后的像素数
    _, png_bytes = a.get("/api/frame.png?t=%d" % (time.time() * 1000))
    ok_sig = png_bytes[:8] == b"\x89PNG\r\n\x1a\n"
    check("PNG 签名正确", ok_sig)
    if ok_sig:
        off, idat, pw, ph, crc_bad = 8, b"", 0, 0, []
        while off + 12 <= len(png_bytes):
            ln = struct.unpack(">I", png_bytes[off:off + 4])[0]
            typ = png_bytes[off + 4:off + 8]
            data = png_bytes[off + 8:off + 8 + ln]
            crc = struct.unpack(">I", png_bytes[off + 8 + ln:off + 12 + ln])[0]
            if crc != (zlib.crc32(typ + data) & 0xFFFFFFFF):
                crc_bad.append(typ.decode("ascii", "replace"))
            if typ == b"IHDR":
                pw, ph, bd, ct = struct.unpack(">IIBB", data[:10])
            if typ == b"IDAT":
                idat += data
            off += 12 + ln
        check("每个 chunk 的 CRC32 都对", not crc_bad, str(crc_bad))
        check("IHDR 尺寸与 info 一致",
              pw == info["frame_w"] and ph == info["frame_h"],
              "%dx%d vs %dx%d" % (pw, ph, info["frame_w"], info["frame_h"]))
        d = zlib.decompressobj()
        try:
            un = d.decompress(idat) + d.flush()
            err = ""
        except zlib.error as ex:          # adler32 不对、段拼错都会在这里炸
            un, err = b"", str(ex)
        check("标准 zlib 能解开 IDAT（段间拼接合法 + adler32 正确）", not err, err)
        check("deflate 流正常终止（只有最后一段 BFINAL=1）", bool(un) and d.eof)
        check("解压后末尾没有多余字节", bool(un) and not d.unused_data)
        check("反滤波前的长度 = (宽*4+1)*高",
              len(un) == (pw * 4 + 1) * ph, "%d vs %d" % (len(un), (pw * 4 + 1) * ph))
        # 滤波类型只允许 None/Sub/Up（我们的编码器就产这三种），越界说明段边界错位
        if un:
            fts = set(un[i * (pw * 4 + 1)] for i in range(ph))
            check("滤波类型都在 0/1/2 之内", fts <= {0, 1, 2}, str(sorted(fts)))

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
    a.hit("/api/blink?v=0.75"); time.sleep(0.15)
    h_half_lid, _ = a.frame_hash()
    check("眨眼 0.75 半闭仍是独立画面", h_half_lid not in (h_open, h_half, h_shut), h_half_lid)
    a.hit("/api/blink?v=0.925"); time.sleep(0.15)
    h_late_blend, _ = a.frame_hash()
    check("最后 15% 闭合过渡仍连续可见", h_late_blend not in (h_half_lid, h_shut), h_late_blend)
    a.hit("/api/blink?v=auto")
    check("切回自动眨眼", a.json("/api/info.json")["blink_manual"] < 0)
    r = a.json("/api/blink?on=0") or {}
    check("on=0 能真的关掉自动眨眼（以前这个参数被静默忽略）",
          r.get("ok") is True and r.get("auto") is False, json.dumps(r, ensure_ascii=False))
    r = a.json("/api/blink?on=1") or {}
    check("on=1 交回自动", r.get("ok") is True and r.get("auto") is True,
          json.dumps(r, ensure_ascii=False))
    # 关自动眨眼的本意是"眼睛别动"，不是"闭着别动"。
    # ⚠ 这条以前是先 /api/idle?s=99999 把角色弄睡着再关眨眼，然后要求眼睛睁开 ——
    #   构造场景就选错了：睡着时眼睛本来就该闭。2026-10-15 修了
    #   「blink_enabled=0 时 blink_hold 够不到」那个缺陷之后，睡着的角色会老老实实
    #   闭着眼，这条才红出来。拆成两条，把两个意图分开守：
    a.hit("/api/idle?s=0")              # ① 醒着（idle 没有 blink_hold）
    a.hit("/api/action?id=idle&force=1")
    time.sleep(0.3)
    a.hit("/api/blink?on=0")
    time.sleep(0.2)                     # 响应里的 blink 是本帧旧值，等下一帧
    r = a.json("/api/info.json") or {}
    check("关自动眨眼 = 眼睛常睁（不是停在闭眼上）", (r.get("blink", 1)) < 0.01,
          "blink=%s" % r.get("blink"))
    a.hit("/api/idle?s=99999")          # ② 睡着：动作要求闭眼，关不关自动眨眼都得闭
    time.sleep(0.4)
    r = a.json("/api/info.json") or {}
    check("睡着时就算关了自动眨眼，眼睛也必须闭着（blink_hold 是动作的要求，不归眨眼开关管）",
          (r.get("blink", 0)) > 0.9, "blink=%s sleeping=%s" % (r.get("blink"), r.get("sleeping")))
    a.hit("/api/idle?s=0")
    a.hit("/api/blink?on=1")
    try:
        a.json("/api/blink")
        bad = False
        detail = "居然回了 2xx"
    except urllib.error.HTTPError as e:
        bad, detail = e.code == 400, "HTTP %d" % e.code
    check("/api/blink 不给参数要报 400（不许静默当成功）", bad, detail)
    # 睡着 → 非 poke 唤醒 → 眼睛必须还回来（2026-10-13 事故：醒着也永远闭眼）
    a.hit("/api/idle?s=99999")
    time.sleep(0.35)
    sleep_info = a.json("/api/info.json") or {}
    check("空闲超时会睡着并闭眼",
          sleep_info.get("action") == "sleep" and sleep_info.get("blink", 0) > 0.9,
          "action=%s blink=%s" % (sleep_info.get("action"), sleep_info.get("blink")))
    a.hit("/api/idle?s=0")
    a.hit("/api/action?id=idle")
    # ⚠ 不能只抓一帧：醒来后自动眨眼又开始跑了，单帧有概率正好抓在眨眼中间。
    #    判据是"这 1.5 秒里眼睛确实睁开过"。
    woke_blink, woke_eye = 1.0, 0.0
    for _ in range(15):
        time.sleep(0.1)
        b = (a.json("/api/info.json") or {}).get("blink", 1.0)
        e = next((q for q in (a.json("/api/params.json") or {}).get("params", [])
                  if q["id"] == "ParamEyeLOpen"), {}).get("effective", 0.0)
        woke_blink, woke_eye = min(woke_blink, b), max(woke_eye, e)
        if woke_blink < 0.5 and woke_eye > 0.5: break
    check("醒来之后眼睛要睁开（强制闭眼必须解除）",
          woke_blink < 0.5 and woke_eye > 0.5,
          "1.5s 内最小 blink=%.2f / 最大 ParamEyeLOpen=%.2f" % (woke_blink, woke_eye))

    print("== 口型同步 LipSync（A4）==")
    ls = a.json("/api/speak?id=hammer_1_base0")
    check("能起一条口型包络", ls.get("ok") is True and ls.get("remain", 0) > 1.0,
          "%s %.2fs" % (ls.get("id"), ls.get("remain", 0)))
    check("包络带台词文本", bool(ls.get("text")), ls.get("text", ""))
    lv = []
    for _ in range(6):
        time.sleep(0.12)
        lv.append(a.json("/api/speech.json")["lipsync"]["level"])
    check("说话时开口度在动", max(lv) > 0.2 and max(lv) > min(lv) + 0.1,
          "max=%.2f min=%.2f" % (max(lv), min(lv)))
    a.hit("/api/speak?stop=1"); time.sleep(0.2)
    st = a.json("/api/speech.json")["lipsync"]
    check("停下后开口度归零", st["active"] is False and st["level"] < 1e-6,
          "active=%s level=%s" % (st["active"], st["level"]))
    try:
        urllib.request.urlopen(base + "/api/speak?id=no_such_line", timeout=3).read()
        check("不存在的包络要报 404", False, "返回了 200")
    except urllib.error.HTTPError as e:
        check("不存在的包络要报 404", e.code == 404, "HTTP %d" % e.code)

    print("== 命名参数层（≈ Live2D ParamXxx）==")
    pr = a.json("/api/params.json")
    plist = pr.get("params", [])
    pids = [q["id"] for q in plist]
    check("params.json 能读", len(plist) >= 5, "%d 个参数" % len(plist))
    check("内建参数在表里", all(k in pids for k in
          ("ParamAngleX", "ParamAngleY", "ParamEyeOpen", "ParamEyeBallX")),
          " ".join(pids[:5]))
    if "ParamMouthOpenY" in pids:
        a.hit("/api/action?id=sleep&force=1"); time.sleep(0.3)
        hb, _ = a.frame_hash()
        a.hit("/api/param?id=ParamMouthOpenY&v=1"); time.sleep(0.3)
        ho, _ = a.frame_hash()
        check("写 ParamMouthOpenY 画面有变化", hb != ho, "%s → %s" % (hb, ho))
        a.hit("/api/param?id=ParamMouthOpenY&reset=1"); time.sleep(0.2)
        v = [q for q in a.json("/api/params.json")["params"] if q["id"] == "ParamMouthOpenY"][0]
        check("参数复位回默认值", abs(v["value"] - v["default"]) < 1e-6, "value=%s" % v["value"])
        a.hit("/api/action?id=idle&force=1")
    if "ParamHairAhogeS" in pids:
        a.hit("/api/action?id=sleep&force=1"); time.sleep(0.35)
        h0, _ = a.frame_hash()
        a.hit("/api/param?id=ParamHairAhogeS&v=1"); time.sleep(0.35)
        h1, _ = a.frame_hash()
        check("网格形变（A5）让画面变了", h0 != h1, "%s → %s" % (h0, h1))
        a.hit("/api/param?id=ParamHairAhogeS&reset=1")
        a.hit("/api/action?id=idle&force=1"); time.sleep(0.2)

    # A7 混合模式 + 冻结时钟：暂停后两帧必须逐字节相同，然后只有参数能改画面
    a.hit("/api/action?id=idle&force=1"); time.sleep(0.4)
    a.hit("/api/pause?on=1"); time.sleep(0.15)
    # ★ 连拍 6 帧而不是 2 帧。2026-10-17 的教训：T45.2g 给尾巴加行波延迟环时，
    #   每 tick 都往环里压一格 —— 冻结时钟下环照样转，回读到的历史跟着变。
    #   症状是**第 1 帧和后面几帧不一样、第 3 帧起才稳**，只比两帧有一半概率放过去
    #   （当时是下游那条「笑眼归零回到原样」替它红的，隔了十几行，很难顺藤摸到）。
    #   冻结时钟的契约是"同一时刻重复 tick 必须幂等"，所以这里要多比几帧。
    hs = [a.frame_hash()[0] for _ in range(6)]
    check("冻结时钟后连拍 6 帧完全相同", len(set(hs)) == 1,
          "、".join(hs) if len(set(hs)) > 1 else hs[0])
    # 冻结中改一个参数：画面必须变（证明冻的是时钟不是渲染），且改完再连拍还得稳
    a.hit("/api/param?id=ParamAngleZ&v=8")
    hz = [a.frame_hash()[0] for _ in range(4)]
    check("冻结时钟中改参数后，画面变了且重新稳定",
          hz[0] != hs[0] and len(set(hz)) == 1,
          "改前 %s → 改后 %s" % (hs[0], "、".join(hz)))
    a.hit("/api/param?id=ParamAngleZ&reset=1")
    # ⚠ 这里以前写的是 ParamBlush，改名成标准的 ParamCheek 之后 if 不成立，
    #    这条检查**静悄悄少掉了一项**（64 → 63）而不是变红。所以下面改成硬断言：
    #    参数不在表里 = 直接红，别再出现"跳过即通过"。
    check("腮红参数用标准名 ParamCheek", "ParamCheek" in pids, " ".join(pids[:6]))
    if "ParamCheek" in pids:
        a.hit("/api/param?id=ParamCheek&v=0"); b0, _ = a.frame_hash()
        a.hit("/api/param?id=ParamCheek&v=1"); b1, _ = a.frame_hash()
        check("腮红（乘算）改变画面", b0 != b1, "%s → %s" % (b0, b1))
        a.hit("/api/param?id=ParamCheek&reset=1")
    # Live2D 标准：左右眼是两个参数（EyeBlink 组），挤眼睛要能挤出来
    check("左右眼各有一个标准参数",
          "ParamEyeLOpen" in pids and "ParamEyeROpen" in pids, " ".join(pids[:6]))
    if "ParamEyeLOpen" in pids and "ParamEyeROpen" in pids:
        a.hit("/api/blink?on=0"); time.sleep(0.1)
        e0, _ = a.frame_hash()
        a.hit("/api/param?id=ParamEyeLOpen&v=0"); el, _ = a.frame_hash()
        check("只闭左眼画面有变化", e0 != el, "%s → %s" % (e0, el))
        a.hit("/api/param?id=ParamEyeLOpen&reset=1")
        a.hit("/api/param?id=ParamEyeROpen&v=0"); er, _ = a.frame_hash()
        check("闭右眼和闭左眼不是同一张脸", el != er, "%s vs %s" % (el, er))
        a.hit("/api/param?id=ParamEyeROpen&reset=1")
        a.hit("/api/blink?on=1")
    # Live2D 标准 6/7：笑眼 = 山型 ∩ 的闭眼（官方 Haru F05 = EyeOpen 0 Multiply + Smile 1 Add）
    check("笑眼用标准名 ParamEyeLSmile / ParamEyeRSmile",
          "ParamEyeLSmile" in pids and "ParamEyeRSmile" in pids, " ".join(pids[:8]))
    if "ParamEyeLSmile" in pids:
        a.hit("/api/blink?on=0"); time.sleep(0.1)
        s0, _ = a.frame_hash()
        a.hit("/api/param?id=ParamEyeLOpen&v=0"); a.hit("/api/param?id=ParamEyeROpen&v=0")
        s_closed, _ = a.frame_hash()
        a.hit("/api/param?id=ParamEyeLOpen&reset=1"); a.hit("/api/param?id=ParamEyeROpen&reset=1")
        a.hit("/api/param?id=ParamEyeLSmile&v=1"); a.hit("/api/param?id=ParamEyeRSmile&v=1")
        s_smile, _ = a.frame_hash()
        check("笑眼改变画面（不用再写 ParamEyeOpen）", s0 != s_smile, "%s → %s" % (s0, s_smile))
        check("笑眼和谷型闭眼不是同一张脸", s_smile != s_closed,
              "smile %s vs closed %s" % (s_smile, s_closed))
        a.hit("/api/param?id=ParamEyeRSmile&reset=1")
        s_wink, _ = a.frame_hash()
        check("单眼笑（只笑左眼）又是另一张脸", s_wink not in (s0, s_smile, s_closed), s_wink)
        a.hit("/api/param?id=ParamEyeLSmile&reset=1")
        back, _ = a.frame_hash()
        check("笑眼归零回到原样", back == s0, "%s vs %s" % (back, s0))
        r = a.json("/api/expression?id=happy") or {}
        time.sleep(0.45)
        eff = {q["id"]: q.get("effective") for q in (a.json("/api/params.json") or {}).get("params", [])}
        check("表情 happy 带笑眼",
              r.get("ok") is not False
              and (eff.get("ParamEyeLSmile") or 0) > 0.9 and (eff.get("ParamEyeRSmile") or 0) > 0.9,
              "L=%s R=%s" % (eff.get("ParamEyeLSmile"), eff.get("ParamEyeRSmile")))
        a.hit("/api/expression?off=1")
        a.hit("/api/blink?on=1")

    # ---- 外部动作文件（.motion3.json）：导入的动作也要真的把参数推起来 ----
    # 这一段的判据是**参数读数**，不是像素：待机本身的呼吸/眨眼能把头部 67% 的
    # 像素翻一遍（tools/measure_motion.py 实测），像素差在这件事上没有分辨力。
    info = a.json("/api/info.json") or {}
    acts = info.get("actions") or []
    anames = info.get("action_names") or []
    if "curious_tilt" in acts:
        idx = acts.index("curious_tilt")
        title = anames[idx] if idx < len(anames) else ""
        check("外部 .motion3 动作挂进了动作表（curious_tilt）", True, title)
        check("外部动作的中文名取自文件自己的 Title 字段", title == "好奇地歪头张望", title)
        a.hit("/api/pause?on=0"); time.sleep(0.15)
        r = a.json("/api/action?id=curious_tilt&force=1") or {}
        time.sleep(0.2)
        check("点播外部动作返回 ok", r.get("ok") is not False, str(r)[:60])
        cur = (a.json("/api/info.json") or {}).get("action")
        check("引擎当前动作切到外部动作", cur == "curious_tilt", str(cur))
        lo, hi = 9e9, -9e9
        for _i in range(64):                 # 3.2s ≈ 一个 4s 循环的前 80%
            time.sleep(0.05)
            eff = {q["id"]: (q.get("effective") or 0)
                   for q in (a.json("/api/params.json") or {}).get("params", [])}
            v = eff.get("ParamAngleZ") or 0
            lo, hi = min(lo, v), max(hi, v)
        check("★ 外部动作把 ParamAngleZ 推到文件写的两端（约 +22 / −18）",
              hi > 19 and lo < -15, "实测 %.1f .. %.1f" % (lo, hi))
        a.hit("/api/action?id=idle&force=1"); time.sleep(0.2)

    # ---- 外部表情文件（.exp3.json）：三种 Blend 的语义要真的落到位 ----
    # 判据用参数读数（/api/params.json 的 effective），不用像素：
    # Multiply 是"乘"，算成加法时 0.5×0.5=0.25 会变成 0.5+0.5=1.0，直接能看出来。
    exps = [e.get("id") for e in (a.json("/api/info.json") or {}).get("expressions", [])]
    if "peek_blush" in exps:
        a.hit("/api/pause?on=0"); time.sleep(0.15)
        a.hit("/api/action?id=idle&force=1"); time.sleep(0.3)
        r = a.json("/api/expression?id=peek_blush") or {}
        check("外部 .exp3 表情能选中（peek_blush）", r.get("ok") is not False, str(r)[:60])
        time.sleep(0.5)                      # FadeInTime = 0.35s
        eff0 = {q["id"]: (q.get("effective") or 0)
                for q in (a.json("/api/params.json") or {}).get("params", [])}
        check("★ Multiply：眼睛睁度 1.0 × 0.45 = 0.45（算成加法会到 1.45 被夹成 1.0）",
              abs((eff0.get("ParamEyeLOpen") or 0) - 0.45) < 0.08,
              "ParamEyeLOpen=%.2f" % (eff0.get("ParamEyeLOpen") or 0))
        check("★ Overwrite：腮红被拉到绝对值 1.0",
              abs((eff0.get("ParamCheek") or 0) - 1.0) < 0.05,
              "ParamCheek=%.2f" % (eff0.get("ParamCheek") or 0))
        check("★ Add：嘴角在原值上 +0.3",
              abs((eff0.get("ParamMouthForm") or 0) - 0.3) < 0.09,
              "ParamMouthForm=%.2f" % (eff0.get("ParamMouthForm") or 0))
        a.hit("/api/expression?off=1")
        time.sleep(0.75)                     # FadeOutTime = 0.55s
        eff1 = {q["id"]: (q.get("effective") or 0)
                for q in (a.json("/api/params.json") or {}).get("params", [])}
        check("取消外部表情后参数回到常态（腮红 0 / 睁眼 1）",
              abs(eff1.get("ParamCheek") or 0) < 0.08 and abs((eff1.get("ParamEyeLOpen") or 1) - 1.0) < 0.08,
              "Cheek=%.2f EyeLOpen=%.2f" % (eff1.get("ParamCheek") or 0, eff1.get("ParamEyeLOpen") or 1))

    # ---- 动作通道全部打在参数上（≈ .motion3 的 Parameter 曲线）----
    # 端到端口径：请求一个动作，参数表里对应的参数就该自己动起来。
    # 以前动作直接写部件几何，外面读 params.json 是看不出动作在跑的。
    # 上面那段像素对照是在 /api/pause?on=1 里跑的（冻结时钟才比得了像素）。
    # 动作要跑起来必须先解冻，这一段做完再冻回去给后面的口型对照用。
    a.hit("/api/pause?on=0"); time.sleep(0.15)
    check("瞳孔形状用标准名 ParamEyeBallForm", "ParamEyeBallForm" in pids, " ".join(pids[:8]))
    check("全身倾斜扩展参数 ParamBaseRot 在册", "ParamBaseRot" in pids, " ".join(pids[:8]))
    if "ParamEyeBallForm" in pids:
        a.hit("/api/action?id=idle&force=1"); time.sleep(0.25)
        s0, _ = a.frame_hash()
        a.hit("/api/param?id=ParamEyeBallForm&v=1")
        s1, _ = a.frame_hash()
        check("瞳孔放大改变画面", s0 != s1, "%s → %s" % (s0, s1))
        a.hit("/api/param?id=ParamEyeBallForm&reset=1")
    a.hit("/api/action?id=wave&force=1")
    peak_a = peak_b = 0.0
    peak_fl = 0.0                           # Q48：前臂伸长（ParamForeLongR）峰值
    low_b = 9.9
    peak_b2, low_b2 = -9.9, 9.9             # 后半段（稳态）的肘极值
    peak_h2, low_h2 = -99.0, 99.0           # 后半段的腕极值（Q43：主行程在腕）
    # ★ Q50：采样周期 0.12s → **0.04s**（窗口总长不变，仍是 1.68s）。
    #   手腕 ひらひら 是 2.2 Hz，0.12s 采样 ≈ 3.8 点/周期，奈奎斯特边缘：
    #   真实摆幅 ±12°（24° 峰峰）采出来忽高忽低 19~21°，闸门会随机红。
    #   这不是放宽阈值（仍是 20°），是**把尺子修准**：0.04s ≈ 11 点/周期，
    #   采到的极值和真值差 <2%。顺带所有峰值（上臂/肘/前臂伸长）都更准。
    for _i in range(42):                    # 窗口内轮询取极值（动作淡入要时间）
        time.sleep(0.04)
        eff = {q["id"]: (q.get("effective") or 0)
               for q in (a.json("/api/params.json") or {}).get("params", [])}
        peak_a = max(peak_a, eff.get("ParamArmRA") or 0)
        peak_fl = max(peak_fl, eff.get("ParamForeLongR") or 0)
        peak_b = max(peak_b, eff.get("ParamArmRB") or 0)
        low_b = min(low_b, eff.get("ParamArmRB") or 0)
        if _i >= 21:                        # 后半段 = 稳态窗（t ≳ 0.84s）
            peak_b2 = max(peak_b2, eff.get("ParamArmRB") or 0)
            low_b2 = min(low_b2, eff.get("ParamArmRB") or 0)
            peak_h2 = max(peak_h2, eff.get("ParamHandR") or 0)
            low_h2 = min(low_h2, eff.get("ParamHandR") or 0)
    # ★ 阈值按**角度**写，不按参数值写（Q35/Q37）。
    #   ParamArmRA 的 bind scale 从 6 改成 18（±10 的官方量程 × 18 = ±180°，
    #   这样"参数满量程 = 手臂能转的极限"才对得上 Live2D 的契约）。
    #   参数值 = 角度 / scale，所以同一个动作的参数读数变成了原来的 1/3。
    #   旧阈 4.0（当时 scale=6）＝ 24°；换算到今天就是 24/18 = 1.33。
    #   肘同理：旧阈 3.0 × scale 10 = 30° → 30/18 = 1.67（Q38 把肘的倍率
    #   也提到了 18，阈值按角度等价折算，物理量没变）。
    # ★ Q38：大臂那条从 24° 提到 90°。照参考图 pose_ref/wave_out.png 实测，
    #   打招呼是**整条手臂斜举**（主轴与竖直 135°），不是把肩停在水平、肘折直角
    #   （那个旧姿势被用户判"完全不符合一个人能做出的动作"）。
    # ★ Q43：上臂这条改成**区间**。用户把 Q42 的 A_u=110° 判死刑
    #   （「连个正常人的结构都做不了吗」）：上臂抬到水平以上 = 一根横棍。
    #   参考图是"窄 V 贴身"，定稿 A_u=70° ⇒ ParamArmRA=(70−15)/18=3.06。
    #   下限 2.2（A_u=55°）守住"确实在打招呼"，上限 4.6（A_u=98°）守住"不许再甩平"。
    # ★ Q44：A_u 70° → **38°**。Q43 的 70° 实拍是"上臂横着伸出去、肘甩到
    #   躯干剪影外 104px"，正是用户禁止的那条。38° 时肘只探出 36px、
    #   手指仍到下巴旁（logs/asset_qa/q44_pose_cands.png 四格实拍）。
    #   区间 1.10~1.45 ⇒ A_u 34.8°~41.1°，低了是没打招呼、高了又成横棍。
    # ★ Q45：A_u 38° → **34°**，区间跟着挪到 0.95~1.25（A_u 32.1°~37.5°）。
    #   改的不是"闸松一点"，是**姿势本身换了**：Q44 的肘内角 32° 实拍下
    #   前臂整条压在上臂上（分件染色 logs/asset_qa/q45_tint.png：上臂只剩
    #   1151px 可见），用户看到的是"袖口下吊着一只大拳套"。Q45 把肘内角
    #   张到 48°（A_u=34 / A_f=166）、前臂沿轴线收窄 15%、同侧肩上提 26px，
    #   肘反而更贴身了（出躯干 36px → 28px = 0.12 头宽，参考图是 0.29）。
    # ★ Q48（第四十八问 b）：区间 0.95~1.25 → **0.28~0.52**（A_u 目标 21.7°）。
    #   同样不是放水，是姿势被几何解算推翻了：用户说「小臂有一些偏短」，
    #   对参考模板 wave_up.png 量得 前臂/上臂 参考 0.87 / 我们 0.71 ⇒ 前臂
    #   沿轴加长 26px（新参数 ParamForeLongR）。而用户点名「手不要再动」，
    #   所以解肩-肘-腕三角形（162.4/141.8/125.1）反推上臂必须收回到 21.7°，
    #   肘顺带从切件 (413,531) 收到 (383,547)＝往身上收 30px。
    #   证据：logs/asset_qa/q48_arm_ab2.png（与参考同比例并排）、q48_elbow_tint.png。
    #   「手够不够得到脸」这条不变式改由下面的 ParamForeLongR 闸把守，比旧的单条更严。
    check("挥手上臂要抬起、但不许甩成横棍（ParamArmRA 0.28~0.52）",
          0.28 < peak_a < 0.52,
          "峰值 %.2f ⇒ 上臂离竖直 %.0f°（目标 21.7°）" % (peak_a, 15.0 + peak_a * 18.0))
    # ★ Q48 配套闸：上臂敢收回到 21.7°，全靠前臂那 26px 真的伸出去了。
    #   这条断了手就够不到脸，挥手退化成"抬了抬胳膊"。
    check("挥手时前臂要伸长到位（ParamForeLongR 峰值 >0.90）",
          peak_fl > 0.90,
          "峰值 %.2f ⇒ 前臂/上臂 %.2f（参考模板 0.87）"
          % (peak_fl, (116.0 + 26.0 * peak_fl) / 162.0))
    # ★ Q40：肘这条从"折得够深（≥25°）"改成"摆得够开（摆幅≥20°）"。
    #   不是为过闸放水 —— 旧阈值编码的是"参考图里肘是弯的"，而这一轮重量
    #   （连通域切袖 → 横截面中线 → 靠手 60% 拟合）证明 wave_out.png 的手臂
    #   是**伸直的**（直线残差 0.5%）。挥手的判据本来就该是"手在摆"，
    #   不是"肘折着" ⇒ 换成摆幅，删掉 sine 通道会立刻红，比旧判据更严。
    # ★ Q42：和 test_core 一起反过来 —— 肘必须**折住**。第四十问拿错了参考图
    #   （wave_out.png 是远距离大幅挥手），近距离打招呼的真值源是 wave_up.png：
    #   肘屈曲约 165°、手停在脸颊边。pixiv 百科「手を振る」同口径。
    #   这里只看后半段样本（前 6 次采样是起手斜坡，会污染极值）。
    # ★ Q43：阈值 50°→100°（新姿势折 139°＝内角 41°，这是"贴身窄 V"的关键），
    #   摆动那条从前臂挪到**手腕**（近距離は手首をひらひら；前臂只留 ±5°）。
    check("挥手的肘要折成窄 V（近距离打招呼，稳态≥100°）",
          low_b2 * 18.0 > 100.0, "稳态最小 %.0f°" % (low_b2 * 18.0))
    check("挥手时手腕要一直在摆（稳态摆幅≥20°）",
          (peak_h2 - low_h2) * 22.0 > 20.0,
          "%.0f°（%.2f..%.2f）" % ((peak_h2 - low_h2) * 22.0, low_h2, peak_h2))

    # 非循环动作的收尾：surprised 的手臂通道是 pulse+out、长度跟动作一样，
    # 没有动作级 FadeOutTime 的话最后一帧会停在满值（≈2.67）再硬切回 idle。
    # 真实时钟下单点采样抖得厉害，所以在尾窗里连采取最小值。
    a.hit("/api/action?id=surprised&force=1")
    t0 = time.time(); tail_min = 9.9; mid_peak = 0.0
    while time.time() - t0 < 0.88:
        eff = {q["id"]: abs(q.get("effective") or 0)
               for q in (a.json("/api/params.json") or {}).get("params", [])}
        v = eff.get("ParamArmLA") or 0.0
        dt = time.time() - t0
        if dt < 0.60: mid_peak = max(mid_peak, v)
        elif dt > 0.78: tail_min = min(tail_min, v)
        time.sleep(0.03)
    # 同上：旧阈 1.2 是 scale=6 年代的参数值 ＝ 7.2°，今天写成 7.2/18。
    check("surprised 中段手臂要摆出去（≥7°）", mid_peak > 7.2 / 18.0,
          "峰值 %.2f（＝%.0f°）" % (mid_peak, mid_peak * 18.0))
    # 平台契约清单（G50）：界面靠它画"能力与供应商"面板
    pf = a.json("/platform.json")
    check("/platform.json 能取到", bool(pf and pf.get("capabilities")),
          "%d 能力 / %d 供应商" % (len((pf or {}).get("capabilities") or []),
                                  len((pf or {}).get("providers") or [])))
    core = {"chat.completion", "image.generate", "code.generate"}
    have = {c["id"] for c in ((pf or {}).get("capabilities") or [])}
    check("用户点名的核心能力都已登记", core <= have, "缺 %s" % sorted(core - have) if core - have else "齐")
    locals_ = [p for p in ((pf or {}).get("providers") or []) if p.get("local")]
    nets = [p for p in ((pf or {}).get("providers") or []) if not p.get("local")]
    check("本地与网络供应商都有（两者都要兼容）", locals_ and nets,
          "本机 %d / 网络 %d" % (len(locals_), len(nets)))

    # 界面骨架（G1）：界面是 layout.json 装配出来的，这些静态文件必须真能取到。
    # 少一个组件脚本，页面上就少一块，而且只在浏览器控制台里报错 —— 这里直接拦住。
    lay = a.json("/layout.json")
    check("/layout.json 能取到且有区域", bool(lay and lay.get("regions")),
          "%d 个区域" % len(((lay or {}).get("regions") or {})))
    ids = []
    for items in ((lay or {}).get("regions") or {}).values():
        for it in items:
            ids.append(it if isinstance(it, str) else it.get("id"))
    bad = [c for c in ids if a.code("/components/%s.js" % c) != 200]
    check("每个组件脚本都能下载", not bad, "取不到 %s" % bad if bad else "%d 个都 200" % len(ids))
    badt = [t.get("id") for t in ((lay or {}).get("themes") or [])
            if a.code("/themes/%s.json" % t.get("id")) != 200]
    check("每个主题文件都能下载", not badt, "取不到 %s" % badt if badt else "主题齐")
    check("不存在的组件要 404（不能回落成首页）",
          a.code("/components/__no_such__.js") == 404, "404")

    # 裙摆摆链（G43）：ParamBodyAngleX 只绑 seg_torso.bend_x，不动头组，
    # 所以把它一把推到满格后，画面里还在继续变的就只剩裙摆的惯性。
    # 没有物理的话，参数一写完画面立刻定住，连抓几帧会是同一张。
    a.hit("/api/action?id=idle&force=1"); time.sleep(0.4)
    a.hit("/api/param?id=ParamBodyAngleX&reset=1"); time.sleep(0.6)
    a.hit("/api/param?id=ParamBodyAngleX&v=10")
    hs = []
    for _ in range(7):
        h, _ = a.frame_hash()
        hs.append(h)
        time.sleep(0.07)
    check("推上身一把，裙摆要继续荡几帧（惯性）", len(set(hs)) >= 3,
          "%d/%d 帧不同" % (len(set(hs)), len(hs)))
    # 收敛只能看数值，不能看整帧 hash —— idle 一直在跑，画面永远不会完全静止。
    # /api/info.json 的 deformers 就是摆链的实时输出。
    # 裙子里布（T45.11 → T66.10b 改成继承）：走 /api/partmesh.json 直接量**画出去的**
    # 顶点位移 —— 里布现在自己没有任何网格（逐顶点场按 35% 从表布继承），
    # 读形变器驱动量只会得到 0，那是「做了但量不出来」的假阴性。
    dfm = (a.json("/api/info.json") or {}).get("deformers") or {}
    if a.json("/api/partmesh.json?id=skirt_lining&max=8"):
        a.hit("/api/param?all=1&reset=1"); a.hit("/api/step?n=60&dt=0.016")
        a.hit("/api/param?id=ParamSkirtSway&v=1.0"); a.hit("/api/step?n=150&dt=0.016")
        _sk = a.json("/api/partmesh.json?id=skirt_main&max=64") or {}
        _ln = a.json("/api/partmesh.json?id=skirt_lining&max=64") or {}
        sp = max([abs(v) for v in (_sk.get("dx") or [0])] or [0])
        lp = max([abs(v) for v in (_ln.get("dx") or [0])] or [0])
        check("裙子里布的逐顶点场跟着表布走（继承）", lp > 0.1,
              "里布峰值 %.3f px（表布 %.3f）—— 0 就是继承没接上" % (lp, sp))
        check("里布跟得比表布少（露里子的前提）", 0 < lp < sp * 0.9,
              "里布 %.3f / 表布 %.3f = %.2f（要 <0.9）" % (lp, sp, (lp / sp) if sp else 0))
        a.hit("/api/param?all=1&reset=1")
    # 裙摆**纵**摆（T66.12，补 T66.11c 遗留）：以前物理写的是形变器 amount、ratio 0.055、
    # 点表极限 3.8px ⇒ 满打满算 0.2 帧px，"做了但看不见"。现在是一条命名参数
    # ParamSkirtSwayY 推一张 2x10 keyform。判据同 T66.10b：读**几何**
    # （/api/partmesh.json），不读 deformers —— keyform 的 amount 恒为 0。
    _pj = {q["id"]: q for q in (a.json("/api/params.json") or {}).get("params", [])}
    if "ParamSkirtSwayY" in _pj and a.json("/api/partmesh.json?id=skirt_main&max=8"):
        def _skirt_peak(axis):
            _m = a.json("/api/partmesh.json?id=skirt_main&max=64") or {}
            _v = _m.get(axis) or [0]
            return max(_v, key=abs)
        a.hit("/api/ambient?on=0"); a.hit("/api/physics?on=0")   # 只测参数→网格这一层
        a.hit("/api/param?all=1&reset=1"); a.hit("/api/step?n=60&dt=0.016")
        rest = max(abs(_skirt_peak("dx")), abs(_skirt_peak("dy")))
        a.hit("/api/param?id=ParamSkirtSwayY&v=1.0"); a.hit("/api/step?n=90&dt=0.016")
        lift_dy = _skirt_peak("dy"); lift_dx = _skirt_peak("dx")
        a.hit("/api/param?id=ParamSkirtSwayY&v=-1.0"); a.hit("/api/step?n=90&dt=0.016")
        drop_dy = _skirt_peak("dy")
        check("静止时裙摆纵摆一个像素都不动", rest < 0.05, "峰值 %.3f px" % rest)
        check("纵摆 +1 把裙摆**掀起**（画面上移 = dy<0）", lift_dy < -3.0,
              "dy %.3f px（正数说明方向写反了）" % lift_dy)
        check("纵摆 −1 让裙摆下坠（dy>0），且比掀起小", 0 < drop_dy < abs(lift_dy),
              "坠 %.3f / 掀 %.3f px（布挂在腰上，坠不到掀那么多）" % (drop_dy, abs(lift_dy)))
        check("纵摆会带出伞效应（下摆左右张开，dx 不至于为 0）",
              abs(lift_dx) > 0.5, "dx %.3f px" % lift_dx)
        # 上下和左右是两条独立通道：只推纵摆时不该把横向也甩出去（那就是两条通道串了）
        a.hit("/api/param?all=1&reset=1"); a.hit("/api/step?n=90&dt=0.016")
        a.hit("/api/param?id=ParamSkirtSwayY&v=1.0"); a.hit("/api/step?n=90&dt=0.016")
        _m = a.json("/api/partmesh.json?id=skirt_main&max=64") or {}
        _dy = _m.get("dy") or [0]
        _cols, _rows = _m.get("cols") or 2, _m.get("rows") or 10
        _top = [abs(_dy[r * (_cols + 1) + c]) for r in range(0, min(2, _rows))
                for c in range(_cols + 1)]
        check("纵摆只动下摆，裙腰那几行不许跟着走",
              max(_top or [0]) < 0.5, "裙腰附近最大 %.3f px" % max(_top or [0]))
        a.hit("/api/param?all=1&reset=1")
        a.hit("/api/ambient?on=1"); a.hit("/api/physics?on=1")   # 还原，别影响后面的段落

    # 换装不许换骨绑定（T66.20 / S4 后半）：换装是"同一副骨架换一层皮"。
    # 判据 = **同一个参数、同一套空跑**下，每套服装的裙子几何摆幅一致。
    # ★ 单位：partmesh 是画布像素，所以每次都拿同一次 info.json 的 scale 归一化。
    #   上一轮"cocoa 裙摆幅度减半"的假警报就是没归一化 + 隔次读缓存（G66.11）。
    _outfits = info.get("outfits") or []
    if len(_outfits) >= 2 and a.json("/api/partmesh.json?id=skirt_main&max=8"):
        def _skirt_amp():
            _i = a.json("/api/info.json") or {}
            _m = a.json("/api/partmesh.json?id=skirt_main&max=64") or {}
            _peak = max([abs(v) for v in (_m.get("dy") or [0])] or [0])
            return _peak / max(float(_i.get("scale") or 1.0), 1e-6)

        a.hit("/api/ambient?on=0"); a.hit("/api/physics?on=0")
        _amps = {}
        for _oid in _outfits:
            a.hit("/api/outfit?id=%s" % _oid)
            a.hit("/api/param?all=1&reset=1"); a.hit("/api/step?n=60&dt=0.016")
            a.hit("/api/param?id=ParamSkirtSwayY&v=1.0"); a.hit("/api/step?n=90&dt=0.016")
            _amps[_oid] = _skirt_amp()
            a.hit("/api/param?all=1&reset=1")
        _vals = [v for v in _amps.values() if v > 0.01]
        check("每套服装都真的驱动了裙子几何（不是死参数）",
              len(_vals) == len(_amps),
              "、".join("%s=%.2f" % (k, v) for k, v in _amps.items()))
        _spread = (max(_vals) / min(_vals)) if _vals else 0.0
        check("换装不改骨绑定：各套装裙子摆幅一致（比值 0.95~1.05）",
              bool(_vals) and 0.95 <= _spread <= 1.05,
              "最大/最小 = %.3f（%s）—— 差得多说明换装把骨绑定/网格动了"
              % (_spread, "、".join("%s=%.2f" % (k, v) for k, v in _amps.items())))
        a.hit("/api/outfit?id=default")
        a.hit("/api/param?all=1&reset=1"); a.hit("/api/step?n=30&dt=0.016")
        a.hit("/api/ambient?on=1"); a.hit("/api/physics?on=1")

    # 挂点（T66.19 / S4）：骨架声明的命名位置。三件事必须真的成立：
    #   ① 每个挂点都有 (父骨, 坐标)，而且父骨在这个形态里真的存在；
    #   ② **screen 会跟着父骨走** —— 腕骨转 70°，腕挂点要跟着跑，别的挂点不许跟着跑；
    #   ③ screen 与 pos 的关系只差"父骨当前变换"，静止时两者不能差出半张画布。
    # ★ 为什么要 ②：挂点如果只是"存了一对坐标"，那和把 pos 写死在配件里没有区别。
    #   这一条量的正是它值不值得存在。
    if a.json("/api/sockets.json"):
        _so = a.json("/api/sockets.json") or {}
        _sl = {q["id"]: q for q in (_so.get("sockets") or [])}
        check("挂点表不是一个空数组", len(_sl) >= 6, "%d 个：%s" % (len(_sl), "、".join(_sl)))
        # 父骨是否真的存在：拿这一形态的 rig.json 当名册（info.json 不报骨表，
        # 而"端点上没有"不等于"不存在" —— 别为了省一行去猜）
        _rig = {}
        try:
            with open(os.path.join(root, "characters", info["character"], "forms",
                                   info["form"], "rig.json"), encoding="utf-8") as _fh:
                _rig = json.load(_fh)
        except Exception:                      # noqa: BLE001
            pass
        _groups = set((_rig.get("groups") or {}).keys())
        _bad = [k for k, q in _sl.items()
                if not q.get("group") or (_groups and q["group"] not in _groups)]
        check("挂点都挂在真实存在的骨上", not _bad,
              "都在（骨表 %d 根）" % len(_groups) if not _bad
              else "父骨不存在：%s" % _bad[:4])
        if "socket_wrist_l" in _sl and "ParamHandL" in _pj:
            a.hit("/api/ambient?on=0"); a.hit("/api/physics?on=0")
            a.hit("/api/param?all=1&reset=1"); a.hit("/api/step?n=60&dt=0.016")

            def _screens():
                _d = a.json("/api/sockets.json") or {}
                return {q["id"]: tuple(q["screen"]) for q in (_d.get("sockets") or [])}

            _s0 = _screens()
            a.hit("/api/param?id=ParamHandL&v=3.2")     # 腕骨 22×3.2 = 70.4°
            a.hit("/api/step?n=20&dt=0.016")
            _s1 = _screens()

            def _moved(sid):
                if sid not in _s0 or sid not in _s1:
                    return 0.0
                return abs(_s1[sid][0] - _s0[sid][0]) + abs(_s1[sid][1] - _s0[sid][1])

            check("腕转 70° 后腕挂点跟着走（>5px）", _moved("socket_wrist_l") > 5.0,
                  "socket_wrist_l 走了 %.2f px" % _moved("socket_wrist_l"))
            check("腕挂点跟着走，别的挂点不许跟着走",
                  max([_moved(k) for k in _s0 if "wrist" not in k] or [0]) < 3.0,
                  "其余最大 %.2f px（超了说明挂点没挂在各自的父骨上）"
                  % max([_moved(k) for k in _s0 if "wrist" not in k] or [0]))
            a.hit("/api/param?all=1&reset=1"); a.hit("/api/step?n=30&dt=0.016")
            a.hit("/api/ambient?on=1"); a.hit("/api/physics?on=1")
        # 静止状态下 screen 与 pos 只差父骨变换：两者都必须在画布附近，不能飞到天外
        _far = [k for k, q in _sl.items()
                if not (-200 <= q["screen"][0] <= 1200 and -200 <= q["screen"][1] <= 1800)]
        check("挂点画出来的位置都在画布附近", not _far,
              "都在" if not _far else "跑飞：%s" % _far[:4])

    # 长发（T46.2）：① 能开关；② 开着的时候，转头会把第三段（发梢）带起来。
    if "longhair_tip" in dfm:
        a.hit("/api/param?all=1&reset=1"); a.hit("/api/step?n=120&dt=0.016")
        a.hit("/api/pose?group=hairstyle&id=long")      # T46.3：发型改走互斥组
        a.hit("/api/param?id=ParamAngleX&v=28")
        # 判据是"转头**会**把它带起来"，不是"转到位那一帧正好在摆"：三段摆是弹簧，
        # 冻结时钟下一步一步空跑时，采样点撞在过零点上就会读到一个接近 0 的瞬时值
        # （2026-10-25 连跑十几次撞到 tip=0.024/0.022，旧二进制、新二进制都会，
        #  跟 T66.10b 无关）。所以边走边采，取这一小段里的峰值。
        mid, tip = 0.0, 0.0
        for _k in range(6):
            a.hit("/api/step?n=8&dt=0.016")
            _d = (a.json("/api/info.json") or {}).get("deformers") or {}
            mid = max(mid, abs(_d.get("longhair_mid") or 0.0))
            tip = max(tip, abs(_d.get("longhair_tip") or 0.0))
        check("转头会把长发的中段和发梢都带起来（3 段摆）",
              mid > 0.15 and tip > 0.05, "mid=%.3f tip=%.3f（48 步内峰值）" % (mid, tip))
        pj = {q["id"]: q for q in (a.json("/api/params.json") or {}).get("params", [])}
        check("长发不再有自己的开关参数（显隐归发型互斥组管，不许两套开关并存）",
              "ParamHairLong" not in pj,
              "params 里还剩 %d 条 ParamHair*" %
              len([k for k in pj if k.startswith("ParamHair")]))
        a.hit("/api/param?all=1&reset=1")

    # ★★ 物理 2.0（T47.2）：摆角接到部件上之后，最关键的那条判据 ——
    #    **不碰任何输入，静置 10 秒，发梢还在自己摆**。
    #    旧内核在这里是死的：输出是"滞后量 pos−target"，输入不动就恒等于 0，
    #    画面上那点晃全是 motion 动作在演（用户 2026-10-17：「目前还没有真实的物理效果」）。
    p2 = (a.json("/api/info.json") or {}).get("physics2") or {}
    check("info.json 暴露物理 2.0 的摆链（摆角 + 真正写出去的值）",
          any(k.startswith("longhair2") for k in p2), " ".join(sorted(p2)[:4]))
    if any(k.startswith("longhair2") for k in p2):
        a.hit("/api/param?all=1&reset=1")
        a.hit("/api/ambient?on=0")                 # 环境摆动关掉，免得它替物理背书
        a.hit("/api/pose?group=hairstyle&id=long")
        a.hit("/api/step?n=180&dt=0.0167")         # 先让摆链落定
        # 发梢在画面上走了多远 = 整片头发的 bend(px) + 两张网格的 amount × 各自振幅
        #（振幅取自 attachments.json：中段 6.2px、发梢 15.0px）
        def _tip():
            q = (a.json("/api/info.json") or {}).get("physics2") or {}
            return ((q.get("longhair2#0") or 0.0)
                    + (q.get("longhair2#1") or 0.0) * 6.2
                    + (q.get("longhair2#2") or 0.0) * 15.0)
        lo = hi = _tip()
        for _ in range(60):                        # 60 × 10 帧 ≈ 10 秒
            a.hit("/api/step?n=10&dt=0.0167")
            v = _tip()
            lo, hi = min(lo, v), max(hi, v)
        check("静置 10 秒，长发发梢仍有 >=2px 的自主摆动（旧内核这里恒为 0）",
              hi - lo >= 2.0, "行程 %.2fpx（%.2f ~ %.2f）" % (hi - lo, lo, hi))
        # ---- T47.3 力场：风真的要吹得动头发，而且方向不能反 ----
        # "方向不能反"这条是 2026-10-18 的回归：当时读数相对真实偏向是镜像的
        # （像素空间 Y 轴向下），画面上就是"风往右吹、头发往左飘"。
        info0 = a.json("/api/info.json") or {}
        fr = info0.get("forces") or {}
        check("info.json 暴露力场（重力/定常风/微风/本帧实际风）",
              all(k in fr for k in ("gx", "gy", "wx", "wy", "breeze", "wind_x")),
              "forces=%s" % sorted(fr.keys()))
        check("重力在像素空间是向下为正（写成 -1 头发会朝天飘）",
              (fr.get("gy") or 0) > 0 and abs(fr.get("gx") or 0) < 1e-9,
              "gravity=(%.2f, %.2f)" % (fr.get("gx") or 0, fr.get("gy") or 0))
        a.hit("/api/force?breeze=0")               # 先把微风关掉，读数才干净
        a.hit("/api/step?n=120&dt=0.0167")
        calm = _tip()
        a.hit("/api/force?wx=0.3&wy=0"); a.hit("/api/step?n=300&dt=0.0167")
        right = _tip()
        check("风往右吹，长发要被吹开 >=8px",
              right - calm >= 8.0, "静置 %.2f → 有风 %.2f（偏移 %+.2fpx）"
              % (calm, right, right - calm))
        check("吹开的方向要和风一致（+ = 画面右）", right > 0,
              "longhair2 合成位移 %+.2fpx" % right)
        a.hit("/api/force?wx=-0.3&wy=0"); a.hit("/api/step?n=360&dt=0.0167")
        left = _tip()
        check("风反过来吹，头发也要反过来飘", left < 0,
              "右风 %+.2fpx / 左风 %+.2fpx" % (right, left))
        a.hit("/api/force?wx=0&wy=0"); a.hit("/api/step?n=150&dt=0.0167")
        back = _tip()
        check("风停 2.5 秒后要收敛回静置位附近",
              abs(back - calm) < abs(left - calm) * 0.5,
              "静置 %.2f → 风停后 %.2f（刮风时 %.2f）" % (calm, back, left))
        # 阵风：一股风掀一下再自己落下去（生气/事件会用它，T51.1）
        a.hit("/api/force?gust_x=2.0&gust_t=0.6")
        peak = 0.0
        for _ in range(45):
            a.hit("/api/step?n=2&dt=0.0167")
            peak = max(peak, abs(_tip()))
        a.hit("/api/step?n=180&dt=0.0167")
        check("一阵风能掀起头发，而且会自己衰减下去",
              peak >= 6.0 and abs(_tip()) < peak * 0.6,
              "峰值 %.2fpx → 3 秒后 %.2fpx" % (peak, abs(_tip())))
        a.hit("/api/force?breeze=0.03&hz=0.11")    # 还回角色默认的常驻微风

        # 关掉物理总开关之后必须立刻归零 —— 排查接缝时两套内核要一起静音
        a.hit("/api/physics?on=0"); a.hit("/api/step?n=6&dt=0.0167")
        q = (a.json("/api/info.json") or {}).get("physics2") or {}
        check("关掉物理后摆链输出归零",
              abs(q.get("longhair2#0") or 0.0) < 1e-6,
              "longhair2#0=%.6f" % (q.get("longhair2#0") or 0.0))
        a.hit("/api/physics?on=1"); a.hit("/api/ambient?on=1")
        a.hit("/api/param?all=1&reset=1")

    # ---- T46.3 发型互斥组：双马尾 / 马尾 ----
    # 这一段验的是**运行期**的四件事：切得动、左右一起动、马尾三段都动、整组关得掉。
    # 几何（发髻在不在剪影上、左右对不对称、段数硬不硬）是静态性质，由 selfcheck 第㉖段守。
    def _hairgrp():
        return next((g for g in ((a.json("/api/info.json") or {}).get("poses") or [])
                     if g.get("id") == "hairstyle"), {})
    if "twintail_l_tip" in dfm:
        a.hit("/api/param?all=1&reset=1"); a.hit("/api/ambient?on=0")
        check("发型是一个互斥组，短发/长发/双马尾/马尾都在里面",
              sorted(_hairgrp().get("entries") or []) == ["long", "pony", "twin"],
              "entries=%s（短发 = 整组关掉，不占档位）" % (_hairgrp().get("entries"),))
        a.hit("/api/pose?group=hairstyle&id=twin"); a.hit("/api/step?n=90&dt=0.016")
        check("发型互斥组切得到双马尾", _hairgrp().get("current") == "twin",
              "current=%r" % _hairgrp().get("current"))
        # 左右两束要一起被头带起来，而且**量级相当** —— 差太多就是哪边的锚点或镜像写错了。
        # ★ 这里**故意只转 10°**：角度大了两边会一起顶到削顶上限，
        #   两个被钳平的数当然相等，对称性就验成了废话。要在线性区里比。
        a.hit("/api/param?id=ParamAngleX&v=10"); a.hit("/api/step?n=24&dt=0.016")
        _d = (a.json("/api/info.json") or {}).get("deformers") or {}
        tl, tr = _d.get("twintail_l_tip") or 0.0, _d.get("twintail_r_tip") or 0.0
        check("转头会把双马尾左右两束的发梢一起带起来",
              abs(tl) > 0.15 and abs(tr) > 0.15 and tl * tr > 0,
              "左 %.3f / 右 %.3f" % (tl, tr))
        check("左右两束响应量级相当（差 <25%，差多了就是锚点或镜像写错）",
              abs(abs(tl) - abs(tr)) <= 0.25 * max(abs(tl), abs(tr), 1e-9),
              "左 %.3f / 右 %.3f" % (tl, tr))
        # 削顶回归闸（2026-10-18）：满量程摇头（30° = ParamAngleX 的上限）之下，
        # 发梢的网格输出不许贴在自己的 max 上 —— 贴顶的那几帧画面上是**完全静止**的，
        # 而它恰好发生在动作最大、最招眼的一瞬。
        # ★ 上限从 rig.json **读**出来，不写死：写死的话有人把 max 调回 1.0，
        #   峰值被钳在 1.0 反而"远低于写死的 2.8"，闸门会亮绿灯放它过去。
        with open(os.path.join(root, "characters", info["character"], "forms",
                               info["form"], "rig.json"), encoding="utf-8") as _f:
            _rigj = json.load(_f)
        _LIM = {o["deformer"]: float(o.get("max", 1.0))
                for c in _rigj.get("physics2", [])
                for o in c.get("outputs", [])
                if o.get("deformer") in ("twintail_l_tip", "twintail_r_tip")}
        a.hit("/api/param?all=1&reset=1"); a.hit("/api/step?n=120&dt=0.016")
        for _i in range(16):
            a.hit("/api/param?id=ParamAngleX&v=%.1f" % (30.0 * (_i + 1) / 16.0))
            a.hit("/api/step?n=1&dt=0.016")
        _pk = {k: 0.0 for k in _LIM}
        for _i in range(70):
            a.hit("/api/step?n=1&dt=0.016")
            _d2 = (a.json("/api/info.json") or {}).get("deformers") or {}
            for _k in _LIM:
                _pk[_k] = max(_pk[_k], abs(_d2.get(_k) or 0.0))
        check("满量程摇头也不许削顶（峰值要留在 rig 里那个 max 的 90%% 以内）",
              bool(_LIM) and all(_pk[k] < _LIM[k] * 0.9 for k in _LIM),
              " / ".join("%s 峰值 %.2f（上限 %.1f）" % (k, _pk[k], _LIM[k])
                         for k in sorted(_LIM)))
        # ★ 收拾干净再走：刚才把头摇到了满量程，头发还在大幅摆。
        #   不归零 + 不等它停，后面任何比画面的用例都会被这股余波带红
        #   （第一版就把下游的"眼高光改变画面"撞红了，症状完全不知所云）。
        a.hit("/api/param?all=1&reset=1"); a.hit("/api/step?n=300&dt=0.016")
        # 马尾：3 段，中段和发梢都要动
        a.hit("/api/param?all=1&reset=1"); a.hit("/api/pose?group=hairstyle&id=pony")
        a.hit("/api/step?n=240&dt=0.016")          # 等上一段的余波彻底停掉
        a.hit("/api/param?id=ParamAngleX&v=28")
        # 取 1.1 秒窗口内的**峰值**，不要只采一个瞬时点：
        # 两段的相位是错开的（这正是"柔软"的来源），单点采样碰上零穿越就假红。
        _pm = _pt = 0.0
        for _i in range(70):
            a.hit("/api/step?n=1&dt=0.016")
            _d = (a.json("/api/info.json") or {}).get("deformers") or {}
            _pm = max(_pm, abs(_d.get("pony_mid") or 0.0))
            _pt = max(_pt, abs(_d.get("pony_tip") or 0.0))
        check("转头会把马尾的中段和发梢都带起来（3 段摆）",
              _pm > 0.15 and _pt > 0.05,
              "1.1s 内峰值 mid=%.3f tip=%.3f" % (_pm, _pt))
        # 整组关掉 = 回到短发 bob（这是默认档，default:"none"）
        a.hit("/api/pose?group=hairstyle&id=none"); a.hit("/api/step?n=90&dt=0.016")
        check("发型组能整组关掉（= 短发 bob，也是它的默认档）",
              _hairgrp().get("current") in ("", "none"),
              "current=%r" % _hairgrp().get("current"))
        a.hit("/api/param?all=1&reset=1"); a.hit("/api/ambient?on=1")

    # info.json 是整个调试台和所有探针的唯一数据源，而它是拿一个**定长 char[]**
    # 拼出来的 —— 2026-10-18 加三个发型时就把它写爆了，返回的是一串缺尾括号的烂 JSON。
    # 症状极具误导性（看起来像前端解析 bug），所以在这里钉一条：必须是完整 JSON。
    _, _raw = a.get("/api/info.json")
    _txt = _raw.decode("utf-8", "replace").strip()
    check("info.json 没被缓冲区截断（完整 JSON，以 } 收尾）",
          _txt.endswith("}") and len(_txt) > 200,
          "%d 字节，结尾 %r" % (len(_txt), _txt[-12:]))

    # 后发第二段（T46.1）：转头之后，第二段（发梢）必须被第一段带起来。
    # 这验的是**物理链接上了**（back_x → back_tip → back_s），
    # 形状上的约束（头顶剪影不许动、比侧发软）是静态性质，由 selfcheck 第㉔段守。
    if "back_s" in dfm:
        # ★ T66.11c 起 back_s 是 **keyform**：它的 `amount` 恒为 0（形状由参数决定），
        #   所以判据必须量几何（/api/partmesh.json 的顶点位移），不是量驱动量。
        a.hit("/api/param?all=1&reset=1"); a.hit("/api/step?n=120&dt=0.016")
        def _hair_back_peak():
            d = a.json("/api/partmesh.json?id=hair_back&max=64") or {}
            return max([abs(v) for v in (d.get("dx") or [0])] or [0])
        _b0 = _hair_back_peak()
        a.hit("/api/param?id=ParamAngleX&v=28"); a.hit("/api/step?n=18&dt=0.016")
        _b1 = _hair_back_peak()
        check("转头会把后发的第二段（发梢）带起来",
              _b1 > max(0.2, _b0 * 2.0),
              "转头 0.3s 后后发顶点峰值 %.3f px（静止 %.3f）—— 量的是几何，"
              "keyform 的 amount 恒为 0 不能当判据" % (_b1, _b0))

    # 外套前襟下摆（T45.12）：和裙摆同一条路子，但**更钝** —— 这里验的是
    # 「它确实被自己的参数推得动」，幅度大小是静态性质（selfcheck 第㉓段比 dx 表）。
    if "jacket_hem_x" in dfm:
        # 环境微风也会推 ParamJacketSway —— 不关掉的话"设之前"的读数就不干净，
        # 判据 j1 > j0*2 会随机红（2026-10-26 实测 j0=0.32、j1=0.58）。
        a.hit("/api/ambient?on=0")
        a.hit("/api/param?all=1&reset=1"); a.hit("/api/step?n=240&dt=0.016")
        a.hit("/api/param?id=ParamJacketSway&v=1.0")
        j0 = abs(((a.json("/api/info.json") or {}).get("deformers") or {})
                 .get("jacket_hem_x") or 0.0)
        a.hit("/api/step?n=240&dt=0.016")
        j1 = abs(((a.json("/api/info.json") or {}).get("deformers") or {})
                 .get("jacket_hem_x") or 0.0)
        check("外套下摆被 ParamJacketSway 推得动（lag 0.16 要空跑才到位）",
              j1 > max(0.5, j0 * 2.0),
              "设上去 %.4f → 空跑 3.84s 后 %.4f（环境风已关）" % (j0, j1))
        a.hit("/api/ambient?on=1")
    a.hit("/api/param?all=1&reset=1")
    a.hit("/api/ambient?on=1"); a.hit("/api/pause?on=0"); time.sleep(0.2)

    check("非循环动作结束前要淡出（FadeOutTime）",
          tail_min < max(mid_peak * 0.5, 0.9),
          "中段峰 %.2f → 尾窗最小 %.2f" % (mid_peak, tail_min))
    a.hit("/api/action?id=breath&force=1")
    lo, hi = 9.9, -9.9
    for _ in range(16):
        time.sleep(0.12)
        eff = {q["id"]: (q.get("effective") or 0)
               for q in (a.json("/api/params.json") or {}).get("params", [])}
        v = eff.get("ParamBreath")
        if v is None:
            continue
        lo = min(lo, v); hi = max(hi, v)
    check("呼吸动作驱动官方口径的 ParamBreath（0..1，带 bias）",
          hi > 0.6 and lo >= -1e-6, "区间 %.3f..%.3f" % (lo, hi))
    a.hit("/api/action?id=idle&force=1")
    a.hit("/api/pause?on=1"); time.sleep(0.15)

    # 口型音素（母音識別）：A/I/U/E/O 必须是五张不同的嘴
    pj = a.json("/api/params.json") or {}
    vis = pj.get("visemes") or []
    check("params.json 带音素表", len(vis) >= 6, " ".join(vis))
    check("params.json 带 model3 的 Groups",
          isinstance(pj.get("groups"), dict)
          and pj["groups"].get("LipSync") == ["ParamMouthOpenY"]
          and len(pj["groups"].get("EyeBlink") or []) == 2,
          json.dumps(pj.get("groups"), ensure_ascii=False))
    hashes = {}
    for v in ("A", "I", "U", "E", "O"):
        r = a.json("/api/viseme?v=%s&w=1" % v) or {}
        check("音素 %s 能设上" % v, r.get("ok") is True and r.get("viseme") == v,
              json.dumps(r, ensure_ascii=False))
        hashes[v], _ = a.frame_hash()
    uniq = len(set(hashes.values()))
    check("A/I/U/E/O 是五张不同的嘴", uniq == 5,
          " ".join("%s=%s" % (k, h[:6]) for k, h in hashes.items()))
    try:                                  # 404 会抛 HTTPError，正好就是要的结果
        r = a.json("/api/viseme?v=NOPE") or {}
        bad_ok = r.get("ok") is False
        detail = json.dumps(r, ensure_ascii=False)
    except urllib.error.HTTPError as e:   # noqa: PERF203
        bad_ok = e.code == 404
        detail = "HTTP %d" % e.code
    check("写错音素名要报错（不能静默当静默音）", bad_ok, detail)
    a.hit("/api/viseme?v=off")
    time.sleep(0.25)
    off_hash, _ = a.frame_hash()
    check("松口后嘴回到闭合", off_hash != hashes["A"], "%s vs %s" % (off_hash, hashes["A"]))
    # 表情 × 口型：Cubism 执行序里 LipSync(700) 排在 Expression(300) 之后，
    # 所以「笑着说 う」嘴还得是撅的，不能被笑脸抵消成中性。
    def _eff(pid):
        for q in (a.json("/api/params.json") or {}).get("params", []):
            if q["id"] == pid:
                return q.get("effective")
        return None
    check("params.json 每个参数都带 effective（合成后的最终值）",
          all("effective" in q for q in (pj.get("params") or [])),
          "%d 个参数" % len(pj.get("params") or []))
    check("params.json 每个参数都带 expr（只过表情那一层）",
          all("expr" in q for q in (pj.get("params") or [])),
          "%d 个参数" % len(pj.get("params") or []))
    check("params.json 报出口型权重和当前表情",
          "viseme_weight" in pj and "expression" in pj,
          json.dumps({k: pj.get(k) for k in ("viseme_weight", "expression")},
                     ensure_ascii=False))
    a.hit("/api/expression?id=smile")   # 冻结时钟下服务端会自动 snap
    time.sleep(0.15)
    mouth = next((q for q in (a.json("/api/params.json") or {}).get("params", [])
                  if q["id"] == "ParamMouthForm"), {})
    check("表情只改合成结果，不写坏参数本身的值",
          abs(mouth.get("value", 1)) < 1e-6 and mouth.get("expr", 0) > 0.1,
          "value %.3f / expr %.3f" % (mouth.get("value", 0), mouth.get("expr", 0)))
    form_smile = _eff("ParamMouthForm")
    check("笑脸把 MouthForm 推向 +（横咧）", (form_smile or 0) > 0.1, str(form_smile))
    smile_hash, _ = a.frame_hash()
    a.json("/api/viseme?v=U&w=1")
    time.sleep(0.15)
    form_smile_u = _eff("ParamMouthForm")
    check("笑着说 う 时嘴还是撅的（口型压过表情）", (form_smile_u or 0) < -0.5,
          "笑 %.3f → 笑+う %.3f" % (form_smile or 0, form_smile_u or 0))
    smile_u_hash, _ = a.frame_hash()
    check("笑 + う 和只笑不是同一张嘴", smile_hash != smile_u_hash,
          "%s vs %s" % (smile_hash[:6], smile_u_hash[:6]))
    a.hit("/api/viseme?v=off")
    a.hit("/api/expression?off=1")
    time.sleep(0.2)
    if "ParamEyeSparkle" in pids:
        a.hit("/api/param?id=ParamEyeSparkle&v=0"); s0, _ = a.frame_hash()
        a.hit("/api/param?id=ParamEyeSparkle&v=1"); s1, _ = a.frame_hash()
        check("眼高光（加算）改变画面", s0 != s1, "%s → %s" % (s0, s1))
        a.hit("/api/param?id=ParamEyeSparkle&reset=1")
    a.hit("/api/pause?on=0"); time.sleep(0.2)
    u1, _ = a.frame_hash(); time.sleep(0.45); u2, _ = a.frame_hash()
    check("恢复后画面重新动起来", u1 != u2, "%s → %s" % (u1, u2))

    # A8 Pose 互斥部件组（≈ pose3.json）：同组同一时刻只有一个档位可见
    poses = a.json("/api/info.json").get("poses", [])
    if poses:
        g = poses[0]
        check("info.json 带互斥组表", len(g.get("entries", [])) >= 2,
              "%s: %s" % (g["id"], ",".join(g.get("entries", []))))
        a.hit("/api/pause?on=1")
        # 眼睛必须先按住睁开再比画面：这一组档位比的是**眼高光**，
        # 要是刚好冻在一次眨眼上（闭眼 0.3 秒，每 2~8 秒一次），三个档位
        # 渲出来一模一样，闸就红一次 —— 2026-10-17 在 `make check` 里真红过，
        # 单跑 smoke 又是绿的。这种"按概率红"的闸比没有闸还糟。
        a.hit("/api/blink?v=0")
        shots = {}
        for ent in g["entries"] + ["none"]:
            a.hit("/api/pose?group=%s&id=%s" % (g["id"], ent))
            shots[ent], _ = a.frame_hash()
        a.hit("/api/blink?v=auto")
        check("每个档位画面都不一样", len(set(shots.values())) == len(shots),
              " ".join("%s=%s" % (k, v[:6]) for k, v in shots.items()))
        cur = [x for x in a.json("/api/info.json")["poses"] if x["id"] == g["id"]][0]
        check("none 之后当前档位为空", cur["current"] == "", "current=%r" % cur["current"])
        a.hit("/api/pose?group=%s&id=%s" % (g["id"], g["entries"][0]))
        cur = [x for x in a.json("/api/info.json")["poses"] if x["id"] == g["id"]][0]
        check("切回第一个档位生效", cur["current"] == g["entries"][0], "current=%s" % cur["current"])
        try:
            urllib.request.urlopen(
                base + "/api/pose?group=%s&id=__nope__" % g["id"], timeout=3).read()
            check("未知档位要报 404", False, "返回了 200")
        except urllib.error.HTTPError as e:
            check("未知档位要报 404", e.code == 404, "HTTP %d" % e.code)
        a.hit("/api/pause?on=0")

    # A6 关键帧动作（≈ .motion3）：nod 是逐帧给值的曲线，不是波形
    if "nod" in a.json("/api/info.json").get("actions", []):
        a.hit("/api/action?id=sleep&force=1"); time.sleep(0.4)
        k0, _ = a.frame_hash()
        a.hit("/api/action?id=nod&force=1"); time.sleep(0.3)
        k1, _ = a.frame_hash()
        check("关键帧动作 nod 让画面变了", k0 != k1, "%s → %s" % (k0, k1))
        cur = a.json("/api/info.json").get("action")
        check("nod 播放时就是当前动作", cur == "nod", "当前=%s" % cur)
        time.sleep(1.1)
        check("nod 播完回到 idle", a.json("/api/info.json").get("action") in ("idle", "breath", "sway"),
              "当前=%s" % a.json("/api/info.json").get("action"))
    a.hit("/api/param?id=ParamAngleX&v=30"); time.sleep(0.6)
    ax = [q for q in a.json("/api/params.json")["params"] if q["id"] == "ParamAngleX"][0]
    check("内建参数读数会跟着子系统走", ax["value"] > 25.0, "ParamAngleX=%.1f" % ax["value"])
    a.hit("/api/param?all=1"); time.sleep(0.4)
    try:
        urllib.request.urlopen(base + "/api/param?id=ParamNope&v=1", timeout=3).read()
        check("不存在的参数要报 404", False, "返回了 200")
    except urllib.error.HTTPError as e:                  # noqa: PERF203
        check("不存在的参数要报 404", e.code == 404, "HTTP %d" % e.code)

    print("== 表情层（≈ Live2D expression）==")
    exprs = a.json("/api/info.json").get("expressions", [])
    check("info 里有表情表", len(exprs) >= 1, " ".join(e["id"] for e in exprs))
    if exprs:
        a.hit("/api/action?id=sleep&force=1"); time.sleep(0.35)
        hb, _ = a.frame_hash()
        act_before = a.json("/api/info.json")["action"]
        a.hit("/api/expression?id=" + exprs[0]["id"]); time.sleep(0.6)
        he, _ = a.frame_hash()
        inf = a.json("/api/info.json")
        check("叠表情后画面有变化", hb != he, "%s → %s" % (hb, he))
        check("表情不顶掉动作", inf["action"] == act_before, "%s → %s" % (act_before, inf["action"]))
        check("info 能读回当前表情", inf["expression"] == exprs[0]["id"], inf["expression"])
        a.hit("/api/expression?off=1"); time.sleep(0.6)
        check("取消表情后 info 清空", a.json("/api/info.json")["expression"] == "")
        a.hit("/api/action?id=idle&force=1")
        try:
            urllib.request.urlopen(base + "/api/expression?id=__nope__", timeout=3).read()
            check("不存在的表情要报 404", False, "返回了 200")
        except urllib.error.HTTPError as e:                 # noqa: PERF203
            check("不存在的表情要报 404", e.code == 404, "HTTP %d" % e.code)

    print("== 视线 ==")
    a.hit("/api/blink?v=0")
    a.hit("/api/gaze?x=-1&y=0"); time.sleep(0.3)
    gl, _ = a.frame_hash()
    a.hit("/api/gaze?x=1&y=0"); time.sleep(0.3)
    gr, _ = a.frame_hash()
    check("视线左 / 右画面有变化", gl != gr, "%s → %s" % (gl, gr))
    # T2.1.1：表达式候选眼件不能冻结 gaze / blink。
    a.hit("/api/expression?id=angry"); a.hit("/api/blink?on=0"); a.hit("/api/blink?v=0")
    time.sleep(0.35)
    a.hit("/api/gaze?x=-1&y=0"); time.sleep(0.25); candidate_left, _ = a.frame_hash()
    a.hit("/api/gaze?x=1&y=0"); time.sleep(0.25); candidate_right, _ = a.frame_hash()
    check("表达式候选眼件仍响应左右视线", candidate_left != candidate_right,
          "%s → %s" % (candidate_left, candidate_right))
    a.hit("/api/gaze?off=1"); a.hit("/api/blink?v=0"); time.sleep(0.1)
    candidate_open, _ = a.frame_hash()
    a.hit("/api/blink?v=1"); time.sleep(0.1)
    candidate_closed, _ = a.frame_hash()
    check("表达式候选眼件仍响应手动眨眼", candidate_open != candidate_closed,
          "%s → %s" % (candidate_open, candidate_closed))
    a.hit("/api/blink?v=0"); a.hit("/api/blink?on=1"); a.hit("/api/expression?off=1")
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

    print("== 台词气泡：冷却被吞时旧句必须收掉（G105）==")
    # 用户 2026-10-15 实拍反馈：摸完头马上锤一下，气泡还停在「嘿嘿，好舒服～」，
    # 看起来像挨了打还在撒娇。根因两层 ——
    #   引擎：zpet_last_line 是"最后说过的那句"，冷却吞掉台词时原句原封不动留着；
    #   前端：每次轮询都 clearTimeout 重设 4.5s，隐藏计时被无限推后，气泡永不消失。
    # 这里查引擎那一层：换规则要清句 + 同规则不能自己打断自己 + seq 要跟着动。
    settle(a)
    time.sleep(9.0)                      # pat_head 冷却 8s，先让它彻底凉透
    a.hit(poke_url(info, "head"))
    time.sleep(0.35)
    s1 = a.json("/api/speech.json")
    check("摸头应说出一句", bool(s1.get("line")), "「%s」seq=%s" % (s1.get("line"), s1.get("seq")))
    a.hit(poke_url(info, "head"))         # 同一条规则、还在冷却里
    time.sleep(0.35)
    s2 = a.json("/api/speech.json")
    check("同一规则连点不该把自己的气泡打掉",
          s2.get("line") == s1.get("line") and s2.get("seq") == s1.get("seq"),
          "「%s」seq=%s → 「%s」seq=%s" % (s1.get("line"), s1.get("seq"),
                                          s2.get("line"), s2.get("seq")))
    a.hit(poke_url(info, "head", tool=1))  # 换成锤击，仍在冷却里
    time.sleep(0.35)
    s3 = a.json("/api/speech.json")
    check("换规则而台词被冷却吞掉时，旧句要当场清空",
          s3.get("line") == "" and s3.get("seq") != s2.get("seq"),
          "「%s」seq=%s（清空前 seq=%s）" % (s3.get("line"), s3.get("seq"), s2.get("seq")))
    check("没有台词时 age 应为 -1", s3.get("age") == -1.0, "age=%s" % s3.get("age"))
    settle(a)
    time.sleep(3.2)                        # hammer_any 冷却 3s
    a.hit(poke_url(info, "head", tool=1))
    time.sleep(0.35)
    s4 = a.json("/api/speech.json")
    check("过了冷却再锤应说出新句",
          bool(s4.get("line")) and s4.get("seq") != s3.get("seq"),
          "「%s」seq=%s age=%s" % (s4.get("line"), s4.get("seq"), s4.get("age")))

    # —— 同一件事的第二条路：/api/action（G105 第二次返工）——
    # 调试台的动作按钮和前端「叫醒」走的是 /api/action，它**绕过 run_rule**，
    # 所以上面那几项全绿的时候，用户点调试台的「被锤」气泡照样纹丝不动
    # （2026-10-15 实拍 + 沙箱复现：动作已经是 hammered，seq 却冻住不变）。
    # 清句改挂到 zpet_action_request 之后，这条路也要有闸盯着。
    settle(a)
    time.sleep(9.0)
    a.hit(poke_url(info, "head"))
    time.sleep(0.35)
    t1 = a.json("/api/speech.json")
    check("（action 路径）摸头应说出一句", bool(t1.get("line")),
          "「%s」seq=%s" % (t1.get("line"), t1.get("seq")))
    a.hit("/api/action?id=head_pat")          # 同一个动作
    time.sleep(0.35)
    t2 = a.json("/api/speech.json")
    check("（action 路径）点同一个动作不该把自己的气泡打掉",
          t2.get("line") == t1.get("line") and t2.get("seq") == t1.get("seq"),
          "「%s」seq=%s → 「%s」seq=%s" % (t1.get("line"), t1.get("seq"),
                                          t2.get("line"), t2.get("seq")))
    a.hit("/api/action?id=talk")              # talk 是例外：伴随说话，不推翻台词
    time.sleep(0.35)
    t3 = a.json("/api/speech.json")
    check("（action 路径）talk 不清句（voice.js 播音前会先请求它）",
          t3.get("line") == t1.get("line"),
          "「%s」" % t3.get("line"))
    a.hit("/api/action?id=hammered")          # 换动作
    time.sleep(0.35)
    t4 = a.json("/api/speech.json")
    check("（action 路径）切到别的动作要当场清句",
          t4.get("line") == "" and t4.get("seq") != t3.get("seq"),
          "「%s」seq=%s（清空前 seq=%s）" % (t4.get("line"), t4.get("seq"), t3.get("seq")))

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
    a.get("/api/scale?s=%.3f" % sc_boot)   # 还原成启动时的值，别把状态漏给后面的用例和预览
    a.hit("/api/idle?s=600"); time.sleep(0.4)
    check("放空够久会睡着", a.json("/api/info.json")["sleeping"] is True)
    a.hit("/api/idle?s=0"); a.hit("/api/call?kind=call_start"); time.sleep(0.3)
    check("叫一声会醒", a.json("/api/info.json")["sleeping"] is False)
    a.hit("/api/call?kind=call_end")

    print("== 零件表 ==")
    rig = a.json("/media/characters/%s/forms/%s/rig.json" % (info["character"], info["form"]))
    check("rig.json 能读", bool(rig.get("parts")), "%d 件" % len(rig.get("parts", [])))
    parts = {p["id"]: p for p in rig["parts"]}
    # 闭眼有两种实现，二选一都得能过：
    #   · 新（G4r）：AI 重绘的闭眼真素材，tags:["eye_closed"]，和睁眼件交叉淡化；
    #   · 旧（兜底）：几何眼皮 tags:["eyelid"] + eyelid_travel 往下滑。
    closed = [p for p in rig["parts"] if "eye_closed" in p.get("tags", [])]
    lids = [p for p in rig["parts"] if "eyelid" in p.get("tags", [])]
    lid_ids = {p["id"] for p in lids}
    if closed:
        opens = [p for p in rig["parts"] if "eye_open" in p.get("tags", [])]
        check("闭眼件与睁眼件成对",
              len(closed) == 2 and {"eye_l_closed", "eye_r_closed"} == {p["id"] for p in closed}
              and len(opens) >= 2,
              "闭眼 %d 件、睁眼 %d 件" % (len(closed), len(opens)))
        def lash_layer(side):
            return parts.get("eye_%s_lash" % side, {}).get("layer", 0)
        ok_layer = all(parts["eye_%s_closed" % sd]["layer"] > lash_layer(sd) for sd in ("l", "r"))
        check("闭眼件压在睁眼件上面",
              ok_layer and all("mask" not in p for p in closed),
              " ".join("%s:%d>%d" % (sd, parts["eye_%s_closed" % sd]["layer"], lash_layer(sd))
                       for sd in ("l", "r")))
    else:
        check("眼睑部件带行程",
              len(lids) >= 2 and {"eye_l_lid", "eye_r_lid"} <= lid_ids
              and all(p.get("eyelid_travel", 0) > 0 for p in lids),
              " ".join("%s:%d" % (p["id"], p.get("eyelid_travel", 0)) for p in lids))
    # 带 gaze 的除了两颗眼球，还有跟着眼球走的加算高光（A7）
    gz = [p for p in rig["parts"] if "gaze" in p.get("tags", [])]
    gz_ids = {p["id"] for p in gz}
    expr_gaze_ids = {p["id"] for p in gz if p["id"].startswith("expr_eye_")}
    expr_open_ids = {p["id"] for p in rig["parts"]
                     if p["id"].startswith("expr_eye_") and p["id"] not in
                     {"expr_eye_l_happy", "expr_eye_r_happy"}}
    check("眼球部件带 gaze 标签",
          {"eye_l_ball", "eye_r_ball"} <= gz_ids and expr_open_ids <= expr_gaze_ids and gz_ids <= {
              "eye_l_ball", "eye_r_ball", "eye_hl_l", "eye_hl_r",
              "eye_hl_star_l", "eye_hl_star_r",
              # 星形虹膜（T39）：它是常态虹膜的差分件，眼珠往哪看它就得往哪看，
              # 所以同样带 gaze。表情候选开眼件（T2.1.1）也随视线移动；happy 的
              # 笑眼是静态闭眼，不标 gaze。
              "eye_l_ball_star", "eye_r_ball_star"} | expr_gaze_ids,
          " ".join(sorted(gz_ids)))
    layers = [p["layer"] for p in rig["parts"]]
    check("层号不重复", len(set(layers)) == len(layers), "%d 层" % len(layers))
    if all(k in parts for k in ("eye_l_lid", "brow_l", "hair_front")):
        check("眉毛和刘海压在眼皮上面",
              parts["brow_l"]["layer"] > parts["eye_l_lid"]["layer"] >= 0 and
              parts["hair_front"]["layer"] > parts["brow_l"]["layer"],
              "眼皮%d < 眉%d < 刘海%d" % (parts["eye_l_lid"]["layer"], parts["brow_l"]["layer"],
                                          parts["hair_front"]["layer"]))

    print("== 眼眶遮罩探针 /api/mask.png（G66.13 的定位工具）==")
    # 这一节验的是"看不见的东西"：眼眶遮罩这一帧到底被切成什么形状。
    # 它是这一轮为定位 G66.13 新加的调试口，也是唯一能直接看见"裁切边界在哪"的手段，
    # 所以必须留在冒烟里 —— 探针一旦坏了，下次再出眼睛的毛病又只能靠猜。
    a.hit("/api/ambient?on=0")
    a.hit("/api/blink?on=0")
    a.hit("/api/pause?on=1&t=2")
    try:
        st, png = a.get("/api/mask.png?id=eye_l_base")
        arr = Image.open(io.BytesIO(png)).convert("RGBA") if st == 200 else None
    except Exception:                                # noqa: BLE001
        arr = None
    check("/api/mask.png 能取到眼眶遮罩", arr is not None, "eye_l_base")
    if arr is not None:
        def mask_top_h(img):
            al = img.split()[3]
            px = al.load()
            ys = [y for y in range(img.height) if any(px[x, y] > 40 for x in range(img.width))]
            return (min(ys), max(ys)) if ys else (None, None)
        tops = {}
        for v in (1.0, 0.5, 0.0):
            a.hit("/api/param?id=ParamEyeLOpen&v=%.2f" % v)
            a.hit("/api/param?id=ParamEyeROpen&v=%.2f" % v)
            a.hit("/api/step?n=3")
            _, png = a.get("/api/mask.png?id=eye_l_base")
            tops[v] = mask_top_h(Image.open(io.BytesIO(png)).convert("RGBA"))
        t1, t5, t0 = tops[1.0], tops[0.5], tops[0.0]
        check("睁眼时遮罩是满的", t1[0] is not None and t1[1] > t1[0], "y %s..%s" % t1)
        check("闭合到 0 时遮罩上沿真的下来了",
              t0[0] is not None and t1[0] is not None and t0[0] > t1[0] + 3,
              "Open=1 上沿 %s → Open=0 上沿 %s" % (t1[0], t0[0]))
        check("半闭（0.5）时遮罩已经压下一截",
              t5[0] is not None and t1[0] is not None and t5[0] >= t1[0],
              "Open=1 上沿 %s → Open=0.5 上沿 %s" % (t1[0], t5[0]))
    a.hit("/api/param?all=1")
    a.hit("/api/pause?on=0")
    a.hit("/api/ambient?on=1")
    a.hit("/api/blink?on=1")
    a.hit("/api/blink?v=auto")

    print("== 分层隔离探针 /api/part（T67.1：关掉一件再看它画在哪）==")
    # 为什么这条要进冒烟：这一轮查"这块青色属于谁"只能靠反算精灵坐标绕（G66.24/25/26）。
    # 有了探针，"关掉一件再看"就是一条命令；探针坏了就等于失去了唯一的观察窗，
    # 而且它是**会改画面**的接口 —— 用完不恢复会污染后面所有用例，所以必须连恢复一起验。
    a.hit("/api/ambient?on=0")
    a.hit("/api/blink?on=0")
    a.hit("/api/param?all=1")
    a.hit("/api/pause?on=1&t=2")
    a.hit("/api/part?all=1")
    try:
        st, body = a.get("/api/part?list=1")
        listing = json.loads(body.decode("utf-8")) if st == 200 else {}
    except Exception:                                # noqa: BLE001
        listing = {}
    ids = [p.get("id") for p in listing.get("parts", [])]
    check("/api/part?list 列出全部部件", len(ids) > 50 and "seg_head" in ids, "%d 件" % len(ids))

    def frame_alpha():
        a.hit("/api/step?n=2")
        _, png = a.get("/api/frame.png?t=5")
        return Image.open(io.BytesIO(png)).convert("RGBA").split()[3]

    try:
        _, body = a.get("/api/part?id=acc_tail_cat_relaxed&vis=0")
        st_ok = json.loads(body.decode("utf-8")).get("ok")
    except Exception:                                # noqa: BLE001
        st_ok = False
    check("关掉尾巴的请求被接受", st_ok is True, "vis=0")
    # 404 在 urllib 里是抛异常，不能当"返回了 ok=false"来判 —— 用 code() 只看状态码。
    code_bad = a.code("/api/part?id=definitely_not_a_part&vis=0")
    check("不存在的部件要报错而不是静默通过", code_bad == 404, "HTTP %s" % code_bad)
    try:
        _, body = a.get("/api/part?id=acc_hair_long&vis=2")
        iso = json.loads(body.decode("utf-8")).get("isolating")
    except Exception:                                # noqa: BLE001
        iso = None
    check("隔离模式把自己标成 isolating", iso == 1, "vis=2")
    a.hit("/api/part?all=1")
    try:
        _, body = a.get("/api/part?list=1")
        back = json.loads(body.decode("utf-8"))
    except Exception:                                # noqa: BLE001
        back = {}
    check("恢复后没有件被藏起来",
          back.get("isolating") == 0 and all(p.get("vis") == 1 for p in back.get("parts", [])),
          "all=1")
    a.hit("/api/pause?on=0")
    a.hit("/api/ambient?on=1")
    a.hit("/api/blink?on=1")

    print("== 测试台页面 ==")
    for path in ("/test.html", "/test.js", "/index.html"):
        try:
            st, b = a.get(path)
        except Exception:                            # noqa: BLE001
            st, b = 0, b""
        check("页面 %s 能打开" % path, st == 200 and len(b) > 500, "%d 字节" % len(b))
    try:
        _, page = a.get("/test.html")
        _, js = a.get("/test.js")
    except Exception:                                # noqa: BLE001
        page, js = b"", b""
    # 收尾自检：跑完不许给用户留下一个"闭着眼 / 卡着表情 / 还在说话"的小寻
    a.hit("/api/blink?v=auto")
    a.hit("/api/expression?off=1")
    a.hit("/api/viseme?v=off")
    a.hit("/api/param?all=1")
    a.hit("/api/speak?stop=1")
    a.hit("/api/idle?s=0")
    time.sleep(0.6)
    fin = a.json("/api/info.json") or {}
    # 眨眼是自动的，采样时刻可能正好落在那 0.1~0.3 秒的闭眼里 —— 这不是故障。
    # 所以这里**最多等 2 秒**让它睁回来；要是真卡住了（表情锁死、参数被写死），
    # 2 秒也等不回来，闸照样红。（2026-10-17：T46.1 的空跑把时钟往前推了 2.2 秒，
    # 眨眼相位跟着挪，这条闸就随机红了一次。）
    pend = {}
    for _ in range(10):
        pend = {q["id"]: q for q in (a.json("/api/params.json") or {}).get("params", [])}
        if (pend.get("ParamEyeLOpen", {}).get("effective", 0) > 0.5
                and pend.get("ParamEyeROpen", {}).get("effective", 0) > 0.5):
            break
        time.sleep(0.2)
    check("收尾：眨眼回到自动", fin.get("blink_manual", 0) < 0, str(fin.get("blink_manual")))
    check("收尾：眼睛是睁开的（别给用户留个闭眼的小寻）",
          pend.get("ParamEyeLOpen", {}).get("effective", 0) > 0.5
          and pend.get("ParamEyeROpen", {}).get("effective", 0) > 0.5,
          "L=%s R=%s" % (pend.get("ParamEyeLOpen", {}).get("effective"),
                         pend.get("ParamEyeROpen", {}).get("effective")))
    check("收尾：没有卡住的表情和口型",
          not fin.get("expression") and not (a.json("/api/params.json") or {})
          .get("viseme", {}).get("id"),
          "expression=%r" % fin.get("expression"))

    check("测试台有「表情 × 口型」分层看板",
          b"mx-table" in page and b"mixRefresh" in js,
          "test.html %d 字节 / test.js %d 字节" % (len(page), len(js)))

    print("== 节奏：脱口而出 vs 先想一想（T69.1）==")
    t1 = a.json("/api/think.json?text=" + urllib.parse.quote("在吗") + "&hour=15")
    check("短寒暄应判成脱口而出", t1.get("mode") == "blurt",
          "%s / %.1f 分 / %s" % (t1.get("mode"), t1.get("score", 0), t1.get("why", "")))
    check("脱口而出的停顿要短（<=200ms）", (t1.get("delay_ms") or 999) <= 200,
          "%s ms" % t1.get("delay_ms"))
    t2 = a.json("/api/think.json?text=" + urllib.parse.quote("你觉得我该不该和他分手，我很难过")
                + "&hour=15")
    check("重话题不许脱口而出", t2.get("mode") in ("ponder", "deliberate"),
          "%s / %s" % (t2.get("mode"), t2.get("why", "")))
    check("想一下要停得真的久（>=400ms）", (t2.get("delay_ms") or 0) >= 400,
          "%s ms" % t2.get("delay_ms"))
    check("判定要能说出理由（可审计）", "→" in (t2.get("why") or ""), t2.get("why", ""))
    t3 = a.json("/api/think.json?text=" + urllib.parse.quote("你还记得上次的事吗") + "&hour=15")
    check("提到「记得/上次」要翻记忆", t3.get("needs_memory") is True, str(t3.get("why")))
    # 同一个输入两次必须一样（随机不叫性格）
    t4 = a.json("/api/think.json?text=" + urllib.parse.quote("为什么你总是不说话") + "&hour=15")
    t5 = a.json("/api/think.json?text=" + urllib.parse.quote("为什么你总是不说话") + "&hour=15")
    check("同一输入两次判定必须一致",
          (t4.get("mode"), t4.get("delay_ms")) == (t5.get("mode"), t5.get("delay_ms")),
          "%s/%s" % (t4.get("mode"), t5.get("mode")))

    u1 = a.json("/api/urge.json?since=7200000&hour=15")
    check("白天闲两小时她会想说话", u1.get("would_speak") is True,
          "urge=%.2f %s" % (u1.get("urge", 0), u1.get("why", "")))
    check("开口要带理由（哪一种想说话）", u1.get("intent") in ("chat", "remember", "care", "share"),
          str(u1.get("intent")))
    u2 = a.json("/api/urge.json?since=7200000&hour=3")
    check("凌晨三点不许主动开口", u2.get("would_speak") is False, "urge=%.2f" % u2.get("urge", 0))
    u3 = a.json("/api/urge.json?since=30000&hour=15")
    check("刚说过话不许马上又开口", u3.get("would_speak") is False and u3.get("wait_s", 0) > 0,
          "wait=%s s" % u3.get("wait_s"))
    u4 = a.json("/api/urge.json?since=200000&hour=15&promise=1")
    check("约定到期必定开口，且理由是「想起一件事」",
          u4.get("would_speak") is True and u4.get("intent") == "remember",
          "intent=%s" % u4.get("intent"))
    a.hit("/api/urge/spoke?topic=1")

    stc, dryc = chat("/api/chat?dry=1&text=" + urllib.parse.quote("在吗"))
    th = dryc.get("think") or {}
    check("/api/chat 要带回节奏（前端靠它决定先放哪句、停多久）",
          th.get("mode") in ("blurt", "ponder", "deliberate") and "delay_ms" in th,
          str(th)[:120])
    try:
        rb = json.loads(dryc.get("request_body") or "{}")
    except Exception:                                # noqa: BLE001
        rb = {}
    check("脱口而出的 max_tokens 要真的进请求体（不是只报个数）",
          (rb.get("max_tokens") or 0) > 0 and (rb.get("max_tokens") or 0) <= 120,
          "max_tokens=%s" % rb.get("max_tokens"))

    print("== 加权刚体的量法（T66.9c）==")
    v0 = a.json("/api/vertex.json?id=skirt_main&c=1&row=0")
    v1 = a.json("/api/vertex.json?id=skirt_main&c=1&row=10")
    check("控制点落点探针可用（裙腰/下摆都要问到）",
          v0.get("ok") is True and v1.get("ok") is True,
          "裙腰 %s · 下摆 %s" % (v0.get("y"), v1.get("y")))
    check("裙腰在下摆上面（坐标系没错）", (v0.get("y") or 0) < (v1.get("y") or 0),
          "%.1f < %.1f" % (v0.get("y") or 0, v1.get("y") or 0))
    st404, v404 = a.json_any("/api/vertex.json?id=__nope__&c=0&row=0")
    check("问不存在的部件要如实说失败（404 + ok:false）",
          st404 == 404 and v404.get("ok") is False, "%s %s" % (st404, str(v404)[:60]))

    print("== 她自己起头（T69.2）==")
    sc, sd = chat("/api/chat?self=1&dry=1&persona=1")
    try:
        srb = json.loads(sd.get("request_body") or "{}")
    except Exception:                                # noqa: BLE001
        srb = {}
    smsgs = srb.get("messages") or []
    sys_self = smsgs[0].get("content", "") if smsgs else ""
    check("主动开口要带「现在是你自己想开口」这一块",
          "现在是你自己想开口" in sys_self, str(sd.get("think"))[:60])
    check("主动开口要说明为什么（哪一种想说话）",
          any(k in sys_self for k in ("单纯想跟他说句话", "想起了一件跟他有关的事",
                                      "状态不太对", "想分享")), "")
    check("主动开口那一轮的 user 消息必须是引擎提示，不是用户台词",
          bool(smsgs) and "引擎提示" in smsgs[-1].get("content", ""), smsgs[-1]["content"][:40] if smsgs else "")
    check("响应要标出这一句是她自己起头的（self=1）", sd.get("self") == 1, str(sd.get("self")))
    check("引擎提示不许算进节奏（长句项必须为 0）",
          "长句0.00" in ((sd.get("think") or {}).get("why") or ""),
          (sd.get("think") or {}).get("why", ""))
    nc, nd = chat("/api/chat?dry=1&persona=1&text=" + urllib.parse.quote("你好"))
    try:
        nrb = json.loads(nd.get("request_body") or "{}")
    except Exception:                                # noqa: BLE001
        nrb = {}
    nm = nrb.get("messages") or []
    check("普通回答里不许混进主动开口那块",
          not nm or "现在是你自己想开口" not in nm[0].get("content", ""), "")
    check("普通回答的 self 必须是 0", nd.get("self") == 0, str(nd.get("self")))

    print("== 长记忆（T67.45）==")
    # ★ 这一节会**写进当前角色真实的** data/<角色>/memory/chronicle.zm：
    #   写一条、回忆一次、再落墓碑（墓碑不自动清，那是用户的数据）。
    #   用带时间戳的 once 键，所以多跑几次只会在墓碑里多几条，不会污染回忆结果。
    # 这一节守的是"四年后还记得"最容易被悄悄弄坏的三处：
    #   ① 记忆文件没打开 → 她失忆但界面一切正常（必须在这里报出来）；
    #   ② 写进去的东西回忆不到 → 记忆是个黑洞；
    #   ③ 删掉之后还能被回忆到 → 删除是假的。
    mem = a.json("/api/memory.json")
    check("记忆文件是打开的", mem.get("open") is True, str(mem.get("error", "")))
    key = "smoke:%d" % int(time.time())
    text = "冒烟测试写进来的一条记忆，验证回忆链路（%s）" % key
    add = a.json("/api/memory/add?kind=0&salience=6&once=%s&text=%s"
                 % (urllib.parse.quote(key), urllib.parse.quote(text)))
    check("能写进一条记忆", add.get("ok") is True, str(add))
    mid = add.get("id")
    rc = a.json("/api/memory.json?q=%s" % urllib.parse.quote("冒烟测试"))
    check("问一句能把它回忆出来", "冒烟测试" in rc.get("block", ""),
          "block=%s" % rc.get("block", "")[:80])
    ver = a.json("/api/memory.json?verify=1")
    check("全量对账通过（正文没被改过）", ver.get("verify") == 0, str(ver.get("why")))
    st_bad, bad = a.json_any("/api/memory/pin?id=%s&unpin=1" % mid)
    check("降级锚点不带理由要被拒（理由必须落盘）",
          st_bad == 400 and bad.get("ok") is False, "HTTP %s %s" % (st_bad, bad))
    dele = a.json("/api/memory/del?id=%s&reason=%s"
                  % (mid, urllib.parse.quote("冒烟测试收尾")))
    check("能删除（落墓碑）", dele.get("ok") is True, str(dele))
    # ★ 按**这一轮的唯一键**判，不按"冒烟测试"这四个字判：
    #   上一轮崩掉留下的同类条目还在文件里（墓碑不能自动清，那是用户的数据），
    #   用泛词判会把这轮的删除判成失败（第一版就是这样误报的）。
    rc2 = a.json("/api/memory.json?q=%s" % urllib.parse.quote("冒烟测试"))
    check("删掉之后回忆里不许再有", key not in rc2.get("block", ""),
          "block=%s" % rc2.get("block", "")[:80])
    st_t, tbad = a.json_any("/api/memory/add?text=x&t=100")
    check("时间越界要被拒（不许造出 1970 年的记忆）",
          st_t == 400 and tbad.get("ok") is False, "HTTP %s %s" % (st_t, tbad))


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
