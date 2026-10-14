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
import re
import signal
import subprocess
import sys
import time
import urllib.parse
import urllib.error
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
    r = a.json("/api/blink?on=0") or {}
    check("on=0 能真的关掉自动眨眼（以前这个参数被静默忽略）",
          r.get("ok") is True and r.get("auto") is False, json.dumps(r, ensure_ascii=False))
    r = a.json("/api/blink?on=1") or {}
    check("on=1 交回自动", r.get("ok") is True and r.get("auto") is True,
          json.dumps(r, ensure_ascii=False))
    a.hit("/api/idle?s=99999")          # 先睡着（强制闭眼）
    time.sleep(0.3)
    a.hit("/api/blink?on=0")            # 关自动眨眼：本意是"眼睛别动"，不是"闭着别动"
    time.sleep(0.2)                     # 响应里的 blink 是本帧旧值，等下一帧
    r = a.json("/api/info.json") or {}
    check("关自动眨眼 = 眼睛常睁（不是停在闭眼上）", (r.get("blink", 1)) < 0.01,
          "blink=%s" % r.get("blink"))
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
    p1, _ = a.frame_hash(); p2, _ = a.frame_hash()
    check("冻结时钟后连续两帧完全相同", p1 == p2, "%s vs %s" % (p1, p2))
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
    for _ in range(14):                     # 窗口内轮询取极值（动作淡入要时间）
        time.sleep(0.12)
        eff = {q["id"]: (q.get("effective") or 0)
               for q in (a.json("/api/params.json") or {}).get("params", [])}
        peak_a = max(peak_a, eff.get("ParamArmRA") or 0)
        peak_b = max(peak_b, eff.get("ParamArmRB") or 0)
    check("挥手动作要驱动 ParamArmRA（大臂）", peak_a > 4.0, "峰值 %.2f" % peak_a)
    check("挥手动作要驱动 ParamArmRB（肘）", peak_b > 3.0, "峰值 %.2f" % peak_b)

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
    check("surprised 中段手臂要摆出去", mid_peak > 1.2, "峰值 %.2f" % mid_peak)
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
    dfm = (a.json("/api/info.json") or {}).get("deformers") or {}
    check("info.json 暴露形变器当前量（摆链可观测）",
          "skirt_sway_x" in dfm and "skirt_sway_y" in dfm,
          " ".join(sorted(dfm)[:6]))
    peak = 0.0
    for _ in range(10):
        dfm = (a.json("/api/info.json") or {}).get("deformers") or {}
        peak = max(peak, abs(dfm.get("skirt_sway_x") or 0.0))
        time.sleep(0.05)
    time.sleep(2.0)                       # 等摆链收敛
    rest = abs(((a.json("/api/info.json") or {}).get("deformers") or {}).get("skirt_sway_x") or 0.0)
    check("停住之后裙摆要收敛回零（只给惯性，不永久吹偏）", rest < 0.05,
          "刚推时 %.3f → 静止后 %.4f" % (peak, rest))
    a.hit("/api/param?id=ParamBodyAngleX&reset=1"); time.sleep(0.5)

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
        shots = {}
        for ent in g["entries"] + ["none"]:
            a.hit("/api/pose?group=%s&id=%s" % (g["id"], ent))
            shots[ent], _ = a.frame_hash()
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
    check("眼球部件带 gaze 标签",
          {"eye_l_ball", "eye_r_ball"} <= gz_ids and gz_ids <= {
              "eye_l_ball", "eye_r_ball", "eye_hl_l", "eye_hl_r",
              "eye_hl_star_l", "eye_hl_star_r"},
          " ".join(sorted(gz_ids)))
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
    pend = {q["id"]: q for q in (a.json("/api/params.json") or {}).get("params", [])}
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
