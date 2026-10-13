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
PROV_KINDS = {"openai_compatible", "official", "comfyui", "mcp", "local_script"}
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
        if b.get("mode") == "api" and not b.get("path"):
            bad_bal.append("%s 声明了 api 余额但没给 path" % fid)
        if p.get("local") and b.get("mode") != "none":
            bad_bal.append("%s 是本地供应商，余额口径应为 none" % fid)
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

    print("")
    print("合计 %d 项，%d 项不通过 → %s"
          % (len(PASS) + len(FAIL), len(FAIL), "全部通过" if not FAIL else "有问题，别交付"))
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
