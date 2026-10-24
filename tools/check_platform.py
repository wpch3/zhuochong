#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""平台契约校验 + 清单生成（G50）。

框架的本体就是四份契约，而契约只有**被校验**才算数。这个脚本做两件事：

  1. 校验 config/capabilities/*.json 与 config/providers/*.json：
     字段齐全、引用一致（供应商声明的能力必须真的存在）、定价能算钱、
     **密钥不许明文**（只能写 secret:// 引用）、余额口径合法。
  2. 生成 web/platform.json —— 给界面用的汇总清单（能力 × 供应商矩阵）。
     和 voice_manifest.json 一个路子：源文件在 config/，产物在 web/。

纯标准库，不依赖 venv。
    python3 tools/check_platform.py            # 校验并写清单
    python3 tools/check_platform.py --check    # 只校验，不写（CI / precommit 用）
"""
import io
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PASS, FAIL = [], []

KINDS = {"generate", "transform", "analyze", "stream"}
UNITS = {"token", "image", "second", "call", "char"}
BAL_MODES = {"api", "ledger", "none"}
PROV_KINDS = {"openai_compatible", "official", "comfyui", "mcp", "local_script", "tts"}
PERSONAS = {"loli", "shoujo", "young_woman", "onee_san", "mature", "boy", "youth"}
# 各家表达情绪的方式完全不同（实测，见 REFERENCE_NOTES 第十三批）
EMOTION_MODES = {"prosody", "style", "emotion", "inline_tag"}
# 看着像真密钥的东西，一律拦下（它们只能待在本机 .env 里）
SECRET_PAT = re.compile(r"(sk-[A-Za-z0-9]{12,}|AIza[A-Za-z0-9_\-]{20,}|ghp_[A-Za-z0-9]{20,})")


def check(name, ok, detail=""):
    (PASS if ok else FAIL).append(name)
    print(("  通过  " if ok else "  不通过  ") + name + ("   " + detail if detail else ""))
    return ok


def jsonc(path):
    """容忍 // 注释的 JSON（仓库里既有配置就是这个风格）。"""
    s = io.open(path, encoding="utf-8").read()
    s = re.sub(r'(?m)^\s*//[^\n]*$', '', s)
    return json.loads(s)


def load_dir(sub):
    d = os.path.join(ROOT, "config", sub)
    out = {}
    if not os.path.isdir(d):
        return out
    for fn in sorted(os.listdir(d)):
        if not fn.endswith(".json"):
            continue
        try:
            out[fn[:-5]] = jsonc(os.path.join(d, fn))
        except Exception as e:                                  # noqa: BLE001
            check("能解析 config/%s/%s" % (sub, fn), False, repr(e))
    return out


def main():
    only_check = "--check" in sys.argv
    print("== 平台契约（G50）==")

    caps = load_dir("capabilities")
    provs = load_dir("providers")
    check("能力契约存在", len(caps) > 0, "%d 个" % len(caps))
    check("供应商契约存在", len(provs) > 0, "%d 个" % len(provs))

    # ---- 能力 ----
    bad = []
    for fid, c in caps.items():
        for k in ("id", "name", "kind", "unit", "input", "output"):
            if k not in c:
                bad.append("%s 缺 %s" % (fid, k))
        if c.get("id") != fid:
            bad.append("%s 的 id 与文件名不一致（%s）" % (fid, c.get("id")))
        if c.get("kind") not in KINDS:
            bad.append("%s 的 kind 非法：%s" % (fid, c.get("kind")))
        if c.get("unit") not in UNITS:
            bad.append("%s 的 unit 非法：%s" % (fid, c.get("unit")))
    check("每个能力字段齐全且 id 与文件名一致", not bad, "；".join(bad[:3]) if bad else "%d 个" % len(caps))

    # ---- 供应商 ----
    bad, unknown_cap, plain_secret, bad_bal = [], [], [], []
    for fid, p in provs.items():
        for k in ("id", "name", "kind", "base_url", "auth", "capabilities", "balance"):
            if k not in p:
                bad.append("%s 缺 %s" % (fid, k))
        if p.get("id") != fid:
            bad.append("%s 的 id 与文件名不一致" % fid)
        if p.get("kind") not in PROV_KINDS:
            bad.append("%s 的 kind 非法：%s" % (fid, p.get("kind")))
        # 引用一致性：声明的能力必须真的注册过 —— 否则路由时才炸
        for e in p.get("capabilities", []):
            if e.get("cap") not in caps:
                unknown_cap.append("%s → %s" % (fid, e.get("cap")))
            if "model" not in e:
                bad.append("%s 的 %s 没写 model" % (fid, e.get("cap")))
            pr = e.get("price") or {}
            if not pr.get("free") and not any(k in pr for k in ("in", "out", "unit")):
                bad.append("%s 的 %s 定价写不出来（既不是 free，也没有 in/out/unit）" % (fid, e.get("cap")))
        # 余额口径
        b = p.get("balance") or {}
        if b.get("mode") not in BAL_MODES:
            bad_bal.append("%s → %s" % (fid, b.get("mode")))
        if b.get("mode") == "api":
            # 实测自 one-api：各家余额端点和算法都不一样（DeepSeek 直接给 total_balance，
            # OpenRouter 和 credit_grants 式要 total - used），所以光一个 path 表达不了。
            if not b.get("endpoint"):
                bad_bal.append("%s 声明了 api 余额但没给 endpoint" % fid)
            if not b.get("pick"):
                bad_bal.append("%s 声明了 api 余额但没说从哪个字段取（pick）" % fid)
            if b.get("path"):
                bad_bal.append("%s 还在用老的 balance.path，改成 endpoint + pick" % fid)
        if p.get("local") and b.get("mode") != "none":
            bad_bal.append("%s 是本地供应商，余额口径应为 none" % fid)
        # 优先级：路由按它分层（照 one-api 的 Ability.priority 做法）
        if not isinstance(p.get("priority"), int):
            bad.append("%s 没写 priority（整数，越大越优先）" % fid)
        # 密钥绝不许明文
        blob = json.dumps(p, ensure_ascii=False)
        if SECRET_PAT.search(blob):
            plain_secret.append(fid)
        kr = (p.get("auth") or {}).get("key_ref")
        if (p.get("auth") or {}).get("type") not in (None, "none") and not str(kr or "").startswith("secret://"):
            plain_secret.append("%s 的 key_ref 不是 secret:// 引用" % fid)

    check("每个供应商字段齐全", not bad, "；".join(bad[:3]) if bad else "%d 个" % len(provs))
    check("供应商声明的能力都已注册（引用一致）", not unknown_cap,
          "；".join(unknown_cap[:3]) if unknown_cap else "全部对得上")
    check("余额口径合法（本地必须 none，api 必须给 path）", not bad_bal,
          "；".join(bad_bal[:3]) if bad_bal else "api/ledger/none 都合规")
    check("契约里没有明文密钥（只能写 secret:// 引用）", not plain_secret,
          "；".join(plain_secret[:3]) if plain_secret else "干净")

    # ---- 网关 ----
    gw_p = os.path.join(ROOT, "config", "gateway.json")
    gw = jsonc(gw_p) if os.path.exists(gw_p) else {}
    check("网关配置存在", bool(gw), "config/gateway.json")
    if gw:
        strat = (gw.get("routing") or {}).get("strategy")
        allowed = (gw.get("routing") or {}).get("_strategy_values") or []
        check("路由策略合法", strat in allowed, "%s ∈ %s" % (strat, allowed))
        check("记账账本指向本机不入库的路径",
              str((gw.get("accounting") or {}).get("ledger", "")).startswith("data/"),
              (gw.get("accounting") or {}).get("ledger"))

    # ---- 音色库（G64）：全部云端，本地音源已按用户要求去掉 ----
    vb_dir = os.path.join(ROOT, "config", "voicebank")
    vb = {}
    vb_bad = []
    for fn in sorted(os.listdir(vb_dir)) if os.path.isdir(vb_dir) else []:
        if not fn.endswith(".json"):
            continue
        v = jsonc(os.path.join(vb_dir, fn))
        vid = fn[:-5]
        if v.get("id") != vid:
            vb_bad.append("%s 的 id 与文件名不一致（%s）" % (fn, v.get("id")))
            continue
        for k in ("name", "provider", "voice_id", "persona", "emotion_mode", "langs"):
            if not v.get(k):
                vb_bad.append("%s 缺 %s" % (fn, k))
        if v.get("persona") not in PERSONAS:
            vb_bad.append("%s 的 persona 不在允许列表：%s" % (fn, v.get("persona")))
        if v.get("emotion_mode") not in EMOTION_MODES:
            vb_bad.append("%s 的 emotion_mode 不认识：%s" % (fn, v.get("emotion_mode")))
        if v.get("provider") not in provs:
            vb_bad.append("%s 指向不存在的供应商 %s" % (fn, v.get("provider")))
        # prosody 档就是做不了情绪，别在契约里假装能做
        if v.get("emotion_mode") == "prosody" and v.get("emotions"):
            vb_bad.append("%s 是 prosody 档（只能调语速音调），不该声明 emotions" % fn)
        if v.get("emotion_mode") != "prosody" and not v.get("emotions"):
            vb_bad.append("%s 声明了 %s 档却没列出支持哪些情绪" % (fn, v.get("emotion_mode")))
        if not v.get("source"):
            vb_bad.append("%s 没写 source（音色信息必须能追溯到出处）" % fn)
        vb[vid] = v
    check("音色库契约齐全", not vb_bad, "；".join(vb_bad[:4]) if vb_bad else "%d 个音色" % len(vb))

    # 本地音源必须已经去掉（用户 2026-10-14 明确要求）
    local_voice = [v for v in vb.values() if (provs.get(v.get("provider"), {}) or {}).get("local")]
    check("音色全部是云端的（本地声源已去掉）", not local_voice,
          str([v["id"] for v in local_voice]))

    # 覆盖面：用户点名要少女、萝莉、青年女性
    personas = {v["persona"] for v in vb.values()}
    for need in ("shoujo", "loli", "young_woman"):
        has = [v["id"] for v in vb.values() if v["persona"] == need]
        check("有 %s 音色" % need, bool(has), "%d 个：%s" % (len(has), " ".join(has[:3])))
    anime = [v for v in vb.values() if v.get("anime")]
    check("二次元风格音色过半", len(anime) * 2 >= len(vb),
          "%d / %d" % (len(anime), len(vb)))
    # 英语音色（GPT / Gemini 这类美国模型要用）
    en = [v["id"] for v in vb.values() if "en-US" in (v.get("langs") or [])]
    check("有英语音色（给英文模型用）", bool(en), "%d 个" % len(en))
    # 跨语言：同一把嗓子能说中文和日文/英文
    cross = [v["id"] for v in vb.values()
             if "zh-CN" in (v.get("langs") or []) and
             ({"ja-JP", "en-US"} & set(v.get("langs") or []))]
    check("有跨语言音色（中文音色也能说日/英）", bool(cross), "%d 个：%s" % (len(cross), " ".join(cross[:3])))

    # ---- 情绪映射：同一个情绪，各家表达方式完全不同 ----
    em = jsonc(os.path.join(ROOT, "config", "emotion_map.json"))
    emo = em.get("emotions", {})
    em_bad = []
    # 桌宠脸上有哪些表情 —— 声音的情绪不能指向一个不存在的表情，否则脸和声音对不上
    rigp = os.path.join(ROOT, "characters/xiaoxun/forms/teen/rig.json")
    rig_exp = set()
    if os.path.exists(rigp):
        rig_exp = {e["id"] for e in (jsonc(rigp).get("expressions") or [])}
    for k, e in emo.items():
        if e.get("expression") and e["expression"] not in rig_exp:
            em_bad.append("%s 指向不存在的表情 %s" % (k, e["expression"]))
        for need in ("minimax", "prosody"):
            if need not in e:
                em_bad.append("%s 缺 %s 通路" % (k, need))
        pr = e.get("prosody") or {}
        for axis, lim in (("rate", 100), ("pitch", 50), ("volume", 50)):
            if abs(pr.get(axis, 0)) > lim:
                em_bad.append("%s 的 %s 超出范围" % (k, axis))
    check("情绪映射表自洽", not em_bad, "；".join(em_bad[:3]) if em_bad else "%d 种情绪" % len(emo))

    # 写了却没有任何音色支持的 style = 这条映射永远走不到，属于写错
    styles = {e["style"] for e in emo.values() if e.get("style")}
    sup = set()
    for v in vb.values():
        if v.get("emotion_mode") == "style":
            sup |= set(v.get("emotions") or [])
    orphan_style = sorted(styles - sup)
    check("情绪映射里的 style 都有音色支持", not orphan_style,
          "没人支持 %s" % orphan_style if orphan_style else "%d 种" % len(styles))

    # 诚实度：prosody 档不许在清单里显得和别家一样能表达情绪
    pros = [v["id"] for v in vb.values() if v.get("emotion_mode") == "prosody"]
    check("免费通道如实标注做不了情绪", all(not vb[i].get("emotions") for i in pros),
          "%s（只能用语速音调模拟）" % " ".join(pros))

    # ---- 分配表：用户两条硬要求 ----
    cast = jsonc(os.path.join(ROOT, "config", "voice_cast.json"))
    cast_bad = []
    for sect in ("characters", "agents"):
        for e in cast.get(sect, []):
            if e.get("voice") not in vb:
                cast_bad.append("%s 用了不存在的音色 %s" % (e.get(sect[:-1]), e.get("voice")))
            if e.get("fallback") and e["fallback"] not in vb:
                cast_bad.append("%s 的兜底音色 %s 不存在" % (e.get(sect[:-1]), e["fallback"]))
    check("分配表引用的音色都存在", not cast_bad, "；".join(cast_bad[:3]))

    # 用户点名排除的供应商：豆包 / 火山引擎（含其 Seed 系列模型与 TTS）。
    # 这条是硬要求，不是偏好 —— 所以要静态拦住，而不是靠记性。
    # 新增供应商时如果手滑把火山的接入写进来，这里会直接红。
    BANNED = ("doubao", "volcengine", "volces", "byteplus", "seed-tts",
              "seedtts", "豆包", "火山引擎", "火山方舟")
    scan_files = []
    for sub in ("providers", "capabilities", "voicebank"):
        d = os.path.join(ROOT, "config", sub)
        if os.path.isdir(d):
            scan_files += [os.path.join(d, f) for f in sorted(os.listdir(d))
                           if f.endswith(".json")]
    for f in ("providers.json", "voices.json", "voice_cast.json",
              "gateway_routes.json", "emotion_map.json"):
        fp = os.path.join(ROOT, "config", f)
        if os.path.exists(fp):
            scan_files.append(fp)
    hits = []
    for fp in scan_files:
        low = io.open(fp, encoding="utf-8").read().lower()
        for b in BANNED:
            if b in low:
                hits.append("%s 命中 %s" % (os.path.relpath(fp, ROOT), b))
    check("供应商里没有豆包 / 火山引擎（用户明确排除）", not hits,
          "；".join(hits[:3]) if hits
          else "扫了 %d 份配置，%d 个关键词" % (len(scan_files), len(BANNED)))

    # ---- 界面圆角：按 Fluent 的三档来（DC20）----
    # 微软官方口径：顶层容器 8px、控件 4px、嵌套元素比外层小 2px（→ 6px）、
    # 与直边相交处 0px。药丸/圆点另算，允许 999px 与 50%。
    # 为什么值得立闸：圆角是最容易"随手写个 10px 12px 14px"的地方，
    # 写散了以后整个界面就不像一个系统里的东西了，而这种漂移没人会专门去查。
    RADIUS_OK = {"0", "0px", "2px", "4px", "6px", "8px", "999px", "9999px", "50%"}
    css_files, bad_r, nrad = [], [], 0
    for dirpath, _dn, fns in os.walk(os.path.join(ROOT, "web")):
        for fn in fns:
            if fn.endswith(".css"):
                css_files.append(os.path.join(dirpath, fn))
    for cf in css_files:
        txt = io.open(cf, encoding="utf-8").read()
        # 变量本身也要守规矩，否则 var(--radius) 就是个后门
        for name, val in re.findall(r"(--[a-z-]*radius[a-z-]*)\s*:\s*([^;]+);", txt):
            nrad += 1
            if val.strip() not in RADIUS_OK:
                bad_r.append("%s 里 %s = %s" % (os.path.basename(cf), name, val.strip()))
        for val in re.findall(r"border-radius\s*:\s*([^;]+);", txt):
            nrad += 1
            v = val.strip()
            if v.startswith("var(") or v in RADIUS_OK:
                continue
            bad_r.append("%s 里 border-radius: %s" % (os.path.basename(cf), v))
    check("界面圆角只用 Fluent 的档位（0/2/4/6/8/药丸）", not bad_r,
          "；".join(bad_r[:4]) if bad_r
          else "扫了 %d 个 css、%d 处圆角" % (len(css_files), nrad))

    # ---- 档一的"零输入"要在代码层成立，不只是配置里写着（AC-20）----
    # 配置可以改，注释可以删，但"仓库里根本没有发送输入的代码"是查得出来的事实。
    # 将来真要做档三（手柄），把文件登记进 TIER3_ALLOW，这个闸会继续盯着其余地方。
    INJECT = [
        r"\bSendInput\b", r"\bkeybd_event\b", r"\bmouse_event\b", r"\bSetCursorPos\b",
        r"\bXTestFake(Key|Button|Motion)Event\b", r"\bCGEventPost\b",
        r"\bpyautogui\b", r"\brobotjs\b", r"\bpynput\b", r"\bvJoy\b", r"\bViGEm\b",
    ]
    TIER3_ALLOW = ()      # 档三还没做；做的时候把那个文件写进来
    SCAN_EXT = (".c", ".h", ".py", ".js", ".ts", ".rs", ".cs", ".json")
    SKIP_DIRS = {".git", "build", "node_modules", "logs", "dist", "characters"}
    hits_inj, nscan = [], 0
    for dirpath, dns, fns in os.walk(ROOT):
        dns[:] = [d for d in dns if d not in SKIP_DIRS and not d.startswith(".")]
        for fn in fns:
            if not fn.endswith(SCAN_EXT):
                continue
            rel = os.path.relpath(os.path.join(dirpath, fn), ROOT)
            if rel in TIER3_ALLOW or rel == os.path.join("tools", "check_platform.py"):
                continue
            nscan += 1
            try:
                txt = io.open(os.path.join(dirpath, fn), encoding="utf-8", errors="ignore").read()
            except OSError:
                continue
            for pat in INJECT:
                if re.search(pat, txt):
                    hits_inj.append("%s 里出现 %s" % (rel, pat.strip("\\b")))
    # 自检：探测器自己得能探到东西，否则"0 命中"可能只是正则写坏了
    probe_ok = all(re.search(p, s) for p, s in (
        (INJECT[0], "SendInput(1, &in, sizeof in);"),
        (INJECT[6], "import pyautogui"),
    ))
    check("输入注入探测器自己是好的（自检）", probe_ok,
          "探测器对样本都不报警的话，下面那条『0 命中』就是假绿")
    check("代码层面不存在输入通道（档一零输入，AC-20）", not hits_inj,
          "；".join(hits_inj[:4]) if hits_inj
          else "扫了 %d 个源文件、%d 个注入 API 关键词" % (nscan, len(INJECT)))
    # ---- 游戏档位表（A25）：网游只能陪聊，不许代打 ----
    # 用户 2026-10-14：「不是完全禁止网游，而是让他们可以在网游也陪伴聊天和
    # 实时屏幕操作进行回应对话，而其他的可以真正的游玩。」
    # 档位是硬约束不是偏好，所以在这里钉死 —— 将来谁手滑把英雄联盟改成档三会直接红。
    gt_path = os.path.join(ROOT, "config", "game_tiers.json")
    if os.path.exists(gt_path):
        gt = json.load(io.open(gt_path, encoding="utf-8"))
        tiers, cats, games = gt.get("tiers", {}), gt.get("categories", {}), gt.get("games", [])

        check("档位表默认档是最安全的那档", gt.get("default_tier") == 1,
              "default_tier=%s，不在表里的游戏必须按档一（零输入）处理" % gt.get("default_tier"))

        t1 = tiers.get("1", {})
        check("档一是真的零输入（不是『默认关闭』）",
              t1.get("input") == "none"
              and {"input.keyboard", "input.mouse", "input.gamepad"} <= set(t1.get("forbidden", [])),
              "档一 input=%s forbidden=%s" % (t1.get("input"), t1.get("forbidden")))

        # 网游类别必须锁死在档一
        bad_cat = [k for k, v in cats.items()
                   if k.startswith("online") and not (v.get("max_tier") == 1 and v.get("locked"))]
        check("网游类别锁死在档一且不可提升", not bad_cat,
              "%s 的 max_tier/locked 不对 —— 网游只能陪聊" % bad_cat)

        # 每个游戏不得越过它所属类别的上限
        over = []
        for g in games:
            cap = cats.get(g.get("category"), {}).get("max_tier")
            if cap is None:
                over.append("%s 的类别 %s 没定义" % (g.get("id"), g.get("category")))
            elif g.get("max_tier", 99) > cap:
                over.append("%s 档位 %s 超过类别上限 %s" % (g.get("id"), g.get("max_tier"), cap))
        check("没有游戏越过它所属类别的档位上限", not over, "；".join(over[:3]))

        # 用户点名的例子单独钉一遍
        lol = next((g for g in games if g.get("id") == "lol"), None)
        check("英雄联盟锁在档一（用户点名的例子）",
              bool(lol) and lol.get("max_tier") == 1
              and cats.get(lol.get("category"), {}).get("locked") is True,
              "表里查不到 lol" if not lol else "max_tier=%s" % lol.get("max_tier"))

        # 档位引用必须有定义
        undef = [g.get("id") for g in games if str(g.get("max_tier")) not in tiers]
        check("游戏引用的档位都有定义", not undef, "%s 引用了未定义的档位" % undef[:3])

        # 真玩档必须带安全前提，否则就是裸奔
        t3 = tiers.get("3", {})
        check("手柄游玩档带齐安全前提（急停 / 限频 / 显式授权）",
              {"input.emergency_stop", "input.rate_limit", "user.explicit_grant"}
              <= set(t3.get("requires", [])),
              "档三 requires=%s" % t3.get("requires"))

    agents = cast.get("agents", [])
    av = [a.get("voice") for a in agents]
    dup = sorted({x for x in av if av.count(x) > 1})
    check("每个 AI 的声音都不一样（用户硬要求）", not dup,
          "重复用了 %s" % dup if dup else "%d 个 AI，%d 种声音" % (len(av), len(set(av))))
    asrc = {vb[v]["provider"] for v in av if v in vb}
    check("AI 的声音不是同一种生源（用户硬要求）", len(asrc) > 1,
          "只有 %s" % sorted(asrc) if len(asrc) <= 1 else "来自 %s" % sorted(asrc))
    # 每个角色形态都要有免费兜底——没配密钥的用户也得听得到声音
    nofb = [c.get("form") for c in cast.get("characters", [])
            if not c.get("fallback") or
            not (provs.get(vb.get(c.get("fallback"), {}).get("provider"), {}) or {}).get("enabled")]
    check("每个形态都有能直接用的兜底音色", not nofb, str(nofb))

    # ---- 覆盖面：用户点名的能力必须都有人能提供 ----
    served = {}
    for p in provs.values():
        for e in p.get("capabilities", []):
            served.setdefault(e.get("cap"), []).append(p["id"])
    must = ["chat.completion", "image.generate", "code.generate", "embed.text"]
    miss = [c for c in must if not served.get(c)]
    check("核心能力都至少有一个供应商", not miss, "缺 %s" % miss if miss else " ".join(must))
    orphan = [c for c in caps if c not in served]
    # 孤儿能力是允许的（先登记契约、后面再接供应商），只报告不判错
    print("  说明  暂时没有供应商的能力   %s" % (sorted(orphan) if orphan else "无"))

    # ---- 生成清单 ----
    def emit(rel, data, note):
        """写出生成物；--check 模式下改为比对磁盘内容，过期即判红。

        生成物过期是最阴的一类问题：契约改了但投影没重算，C 侧照旧读到老数据，
        没有任何报错。所以 --check 不是"跳过生成"，而是"验证生成物是最新的"。
        """
        full = os.path.join(ROOT, rel)
        want = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
        if only_check:
            have = io.open(full, encoding="utf-8").read() if os.path.exists(full) else None
            check("生成物 %s 与契约一致" % rel, have == want,
                  "" if have == want else
                  ("文件不存在" if have is None else "契约改了但没重新生成")
                  + " → 跑一次 python3 tools/check_platform.py")
        else:
            io.open(full, "w", encoding="utf-8").write(want)
            print("  写出  %s   %s" % (rel, note))

    if not FAIL:
        manifest = {
            "_note": "由 tools/check_platform.py 生成，不要手改。源文件在 config/capabilities 与 config/providers。",
            "capabilities": [
                {"id": c["id"], "name": c["name"], "kind": c["kind"], "unit": c["unit"],
                 "ui": c.get("ui", {}), "providers": sorted(served.get(c["id"], []))}
                for c in sorted(caps.values(), key=lambda x: x["id"])
            ],
            "providers": [
                {"id": p["id"], "name": p["name"], "kind": p["kind"],
                 "local": bool(p.get("local")), "enabled": bool(p.get("enabled", True)),
                 "balance_mode": (p.get("balance") or {}).get("mode"),
                 "caps": [e["cap"] for e in p.get("capabilities", [])]}
                for p in sorted(provs.values(), key=lambda x: x["id"])
            ],
            "routing": (gw.get("routing") or {}).get("strategy"),
            "proxy_enabled": bool((gw.get("proxy") or {}).get("enabled")),
        }
        emit("web/platform.json", manifest,
             "%d 能力 / %d 供应商" % (len(caps), len(provs)))

        # 兼容投影：C 侧 zconfig.c 读的是老格式的 config/providers.json。
        # 不恢复成"两套各写各的"——老文件从此是**生成物**，新契约是唯一真相。
        legacy = {
            "_note": "由 tools/check_platform.py 从 config/providers/*.json 生成，不要手改。"
                     "新增供应商请在 config/providers/ 下加契约文件。",
            "schema_version": "1.0",
            "providers": [],
        }
        for p in sorted(provs.values(), key=lambda x: x["id"]):
            chat = next((e for e in p.get("capabilities", [])
                         if e.get("cap", "").startswith("chat.")), None)
            first = chat or (p.get("capabilities") or [{}])[0]
            # C 侧（zconfig.c）只认三种 kind，新契约的 comfyui/mcp/local_script
            # 在它看来都是"本机服务"。原值留在 kind_ext 里，C 会忽略未知字段。
            kmap = {"openai_compatible": "openai_compatible", "official": "official",
                    "comfyui": "local", "mcp": "local", "local_script": "local"}
            legacy["providers"].append({
                "id": p["id"], "name": p["name"],
                "kind": kmap.get(p["kind"], "local"), "kind_ext": p["kind"],
                "base_url": p.get("base_url", ""),
                "model": first.get("model", ""),
                "enabled": bool(p.get("enabled", True)),
                "official": p.get("kind") == "official",
                "local": bool(p.get("local")),
            })
        emit("config/providers.json", legacy,
             "给 C 侧的兼容投影，%d 条" % len(legacy["providers"]))

        # 路由表：(能力 → 候选供应商) 的反向索引，照 one-api 的 Ability 表物化出来。
        # 运行时不该去遍历 config/providers/ 再反查——那是每次请求都做一遍的活儿。
        # 预计算好，C 侧读一个扁平数组就能路由。
        routes = []
        for pv in sorted(provs.values(), key=lambda x: x["id"]):
            for e in pv.get("capabilities", []):
                pr = e.get("price") or {}
                routes.append({
                    "cap": e["cap"], "provider": pv["id"], "model": e.get("model", ""),
                    "priority": pv.get("priority", 0),
                    "local": bool(pv.get("local")),
                    "enabled": bool(pv.get("enabled", True)),
                    "free": bool(pr.get("free")),
                    "price_in": float(pr.get("in", 0) or 0),
                    "price_out": float(pr.get("out", 0) or 0),
                    "price_per": float(pr.get("per", 0) or 0),
                })
        # 排序即优先级：先按能力分组，组内高优先级在前，同级按 id 稳定排序。
        # 网关取"第一个可用的"就是正确路由，重试则顺序往下走。
        routes.sort(key=lambda r: (r["cap"], -r["priority"], r["provider"]))

        # 接入点表（G54）：路由表只回答"选谁"，真要把请求发出去还缺
        # "往哪个地址发、怎么带密钥"。这两件事都在契约里，一起物化出来，
        # C 侧就不用在运行时再去读 config/providers/ 那 29 个文件。
        #
        # chat_path 为什么由 kind 推导而不是写在契约里：openai_compatible
        # 这一族（16 家）的聊天端点一律是 base_url + /chat/completions，
        # 写 16 遍等于 16 次抄错的机会。真有特例再在契约里加 chat_path 覆盖。
        endpoints = []
        for pv in sorted(provs.values(), key=lambda x: x["id"]):
            au = pv.get("auth") or {}
            kind = pv.get("kind", "")
            if kind == "openai_compatible":
                cpath = "/chat/completions"
            elif kind == "official" and pv["id"] == "anthropic":
                cpath = "/messages"
            else:
                cpath = ""           # 这一族还没接聊天，留空 = 不可用
            endpoints.append({
                "id": pv["id"],
                "kind": kind,
                "local": bool(pv.get("local")),
                "enabled": bool(pv.get("enabled", True)),
                "base_url": pv.get("base_url", ""),
                "auth_type": au.get("type", "none"),
                "key_ref": au.get("key_ref", ""),
                "auth_header": au.get("header", ""),
                "chat_path": pv.get("chat_path", cpath),
            })
        # 音色：界面用的全量清单 + C 侧读的老格式投影。
        # 和 providers 一样的套路——契约是真相，老文件是生成物。
        def emotion_distinct(v, emo):
            m = v.get("emotion_mode")
            sup = set(v.get("emotions") or [])
            if m == "prosody":
                return 0          # 做不了情绪，别给它算分
            if m == "style":
                return len({e["style"] for e in emo.values() if e.get("style") in sup})
            if m == "emotion":
                return len({e["minimax"] for e in emo.values() if e.get("minimax") in sup})
            return len({e["tag"] for e in emo.values() if e.get("tag")})

        def live(vid):
            """挑出当前真能用的那个音色：首选供应商没开就落到兜底。
            和网关的路由逻辑一致（只认 enabled 的），否则界面说能用、实际发不出去。"""
            v = vb.get(vid)
            if v and (provs.get(v["provider"], {}) or {}).get("enabled"):
                return v, False
            return None, True

        emit("web/voicebank.json", {
            "_note": "由 tools/check_platform.py 生成，不要手改。源在 config/voicebank/ 与 config/voice_cast.json。",
            "voices": [
                {"id": v["id"], "name": v["name"], "provider": v["provider"],
                 "voice_id": v["voice_id"], "persona": v["persona"],
                 "anime": bool(v.get("anime")), "langs": v.get("langs", []),
                 "emotion_mode": v["emotion_mode"], "emotions": v.get("emotions", []),
                 "roles": v.get("roles", []), "tunable": v.get("tunable", {}),
                 "recommend": v.get("recommend", ""),
                 "ready": bool((provs.get(v["provider"], {}) or {}).get("enabled")),
                 # 区分度 = 这个音色能把 11 种情绪分成几种不同的声音。
                 # 比"支持几种情绪"诚实：MiniMax 的 11 种情绪其实只落到 5 个不同取值。
                 "emotion_distinct": emotion_distinct(v, emo)}
                for v in sorted(vb.values(), key=lambda x: (x["persona"], x["id"]))
            ],
            "cast": {
                "characters": cast.get("characters", []),
                "agents": cast.get("agents", []),
            },
            "personas": sorted(PERSONAS),
            "emotion_modes": sorted(EMOTION_MODES),
        }, "%d 个音色 / %d 个角色形态 / %d 个 AI"
           % (len(vb), len(cast.get("characters", [])), len(cast.get("agents", []))))

        emit("web/emotion_map.json", {
            "_note": "由 tools/check_platform.py 从 config/emotion_map.json 投影，不要手改。"
                     "面板只能从 web 根目录取文件，config/ 下的取不到。",
            "fallback_order": em.get("fallback_order", []),
            "emotions": emo,
        }, "%d 种情绪 x 四条通路" % len(emo))

        legacy_voices = {
            "_note": "由 tools/check_platform.py 从 config/voicebank/ 与 config/voice_cast.json 生成，"
                     "不要手改。这里写的是**当前真能用**的音色：首选供应商没开就落到兜底。",
            "schema_version": "1.0",
            "voices": [],
        }
        for c in cast.get("characters", []):
            v, fell = live(c["voice"])
            if v is None:
                v = vb.get(c.get("fallback"))
            if not v:
                continue
            legacy_voices["voices"].append({
                "id": "%s_%s" % (c["character"], c["form"]) if c.get("form") else c["character"],
                "character": c["character"], "form": c.get("form", ""),
                "provider": v["provider"], "voice": v["voice_id"],
                "style": v["name"] + (" ｜ 首选 %s 没开，先用兜底" % c["voice"] if fell else ""),
                "note": v.get("recommend", ""),
            })
        emit("config/voices.json", legacy_voices,
             "给 C 侧的兼容投影，%d 条" % len(legacy_voices["voices"]))

        emit("config/gateway_routes.json", {
            "_note": "由 tools/check_platform.py 从 config/providers/*.json 生成，不要手改。"
                     "这是能力→供应商的路由表，顺序即优先级。",
            "schema_version": "1.0",
            "strategy": (gw.get("routing") or {}).get("strategy"),
            "fallback": (gw.get("routing") or {}).get("fallback", True),
            "rules": {k: v for k, v in ((gw.get("routing") or {}).get("rules") or {}).items()
                      if not k.startswith("_")},
            "routes": routes,
            "endpoints": endpoints,
        }, "路由表 %d 条 + 接入点 %d 条" % (len(routes), len(endpoints)))

    print("")
    print("合计 %d 项，%d 项不通过 → %s"
          % (len(PASS) + len(FAIL), len(FAIL), "全部通过" if not FAIL else "有问题，别交付"))
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
