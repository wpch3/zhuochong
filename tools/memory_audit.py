#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""memory_audit.py —— 长记忆文件的静态体检（T67.45）

为什么要有它
------------
`zmem` 的 "四年后还记得" 靠三件事撑着，三件都能被**悄悄破坏**：

  ① 正文不可变   —— 有人（脚本/编辑器/同步工具）改了一个字节，她就"记得"一件没发生的事；
  ② 锚点有上限   —— 锚点被挤掉，四年后最先忘的就是第一天；
  ③ 自述有闸     —— 自述每次改写都要引用真实记忆、有间隔、不许整篇换人。

C 侧运行时会校验 ①②（`/api/memory.json?verify=1`），但**只有运行起来才校验**。
这个工具是仓库级的静态闸：CI / 提交前 / 换机器之后都能跑，不需要启动服务。

判据（全部可机检）
------------------
G1 文件结构：magic / 长度 / 正文哈希（= 正文不可变）
G2 id 连续、锚点 ≤ ZMEM_MAX_ANCHORS、墓碑自洽
G3 自述：每个 [#id] 必须存在且未删；相邻版本间隔 ≥ 30 天；汉字二元组重合 ≥ 55%
G4 不许存秘密：密钥/口令/令牌/银行卡/身份证号一律报红
G5 锚点与规模匹配：条目数 > 100 却一个锚点都没有 ⇒ 报红（记忆在长，但什么都不剩）
G6 单条正文 ≤ 240 字节（超了说明写入路径没走 zmem_add）

用法
----
    python3 tools/memory_audit.py                  # 全库
    python3 tools/memory_audit.py --character xiaoxun
    python3 tools/memory_audit.py --fail           # 有问题返回 1（给 Makefile 用）
"""
from __future__ import annotations

import argparse
import glob
import os
import re
import struct
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

MAGIC = 0x31454D5A          # 'ZME1' 小端
HDR = 32
RT_ADD, RT_PIN, RT_DEL, RT_TOUCH, RT_SAL, RT_STORY, RT_UNPIN = 1, 2, 3, 4, 5, 6, 7
MAX_TEXT = 240
MAX_ANCHORS = 12
STORY_GAP_DAYS = 30
STORY_DRIFT_PCT = 55
DAY = 86400

# 这些模式出现在记忆正文里 = 有人把不该记的东西写进去了（G4）
SECRET_PATTERNS = [
    (re.compile(r"sk-[A-Za-z0-9_\-]{16,}"), "疑似 API Key（sk-…）"),
    (re.compile(r"(?i)\b(api[_-]?key|secret|token|password|passwd)\s*[:=]\s*\S{6,}"), "疑似密钥/口令"),
    (re.compile(r"(?i)bearer\s+[A-Za-z0-9._\-]{16,}"), "疑似 Bearer 令牌"),
    (re.compile(r"\b\d{16,19}\b"), "疑似银行卡号"),
    (re.compile(r"\b\d{17}[\dXx]\b"), "疑似身份证号"),
]


def fnv1a(b: bytes) -> int:
    h = 2166136261
    for c in b:
        h ^= c
        h = (h * 16777619) & 0xFFFFFFFF
    return h


def bigrams(s: str):
    s = re.sub(r"[\s，。、：；「」（）—…·,.\-\[\]#\d]", "", s)
    return set(s[i:i + 2] for i in range(max(0, len(s) - 1)))


def jacc(a, b):
    if not a or not b:
        return 0.0
    return len(a & b) / float(len(a | b))


def parse(path):
    """返回 (records, errors)。records 是按顺序的重放后的状态。"""
    errs = []
    with open(path, "rb") as f:
        raw = f.read()
    off = 0
    line = 0
    items = []        # dict: id,t,kind,sal,pinned,deleted,text,key,touched
    story = []
    pin = {}
    while off + HDR <= len(raw):
        line += 1
        magic = struct.unpack_from("<I", raw, off)[0]
        a = struct.unpack_from("<I", raw, off + 4)[0]
        rid = struct.unpack_from("<I", raw, off + 8)[0]
        t = struct.unpack_from("<q", raw, off + 12)[0]
        h = struct.unpack_from("<I", raw, off + 20)[0]
        aux = struct.unpack_from("<I", raw, off + 24)[0]
        key = struct.unpack_from("<I", raw, off + 28)[0]
        rtype = a & 0xFFFF
        tlen = a >> 16
        if magic != MAGIC:
            errs.append("G1 第 %d 条：magic 不对（0x%08X）—— 文件被改过或不是记忆文件" % (line, magic))
            break
        if tlen > MAX_TEXT or off + HDR + tlen > len(raw):
            errs.append("G1 第 %d 条：长度 %d 越界（文件尾被截断？）" % (line, tlen))
            break
        body = raw[off + HDR:off + HDR + tlen]
        text = body.decode("utf-8", "replace")
        if fnv1a(body) != h:
            errs.append("G1 第 %d 条：正文哈希不符 —— **正文被改过**（正文必须不可变）" % line)
        if rtype == RT_ADD:
            if rid != len(items) + 1:
                errs.append("G2 第 %d 条：id 不连续（期望 %d 实际 %d）" % (line, len(items) + 1, rid))
            items.append(dict(id=rid, t=t, kind=aux & 0xFF, sal=(aux >> 8) & 0xFF,
                              pinned=(aux & 0xFF) == 1, deleted=False,
                              text=text, key=key, touched=0))
        elif rtype == RT_PIN and 1 <= rid <= len(items):
            items[rid - 1]["pinned"] = True
        elif rtype == RT_UNPIN and 1 <= rid <= len(items):
            items[rid - 1]["pinned"] = False
        elif rtype == RT_DEL and 1 <= rid <= len(items):
            items[rid - 1]["deleted"] = True
            items[rid - 1]["pinned"] = False
        elif rtype == RT_TOUCH and 1 <= rid <= len(items):
            items[rid - 1]["touched"] += 1
        elif rtype == RT_SAL and 1 <= rid <= len(items):
            v = (aux >> 8) & 0xFF
            items[rid - 1]["sal"] = max(items[rid - 1]["sal"], v)
        elif rtype == RT_STORY:
            story.append(dict(v=rid, t=t, text=text))
        else:
            errs.append("G1 第 %d 条：未知记录类型 %d" % (line, rtype))
        off += HDR + tlen
    if off != len(raw):
        errs.append("G1 文件尾部有 %d 字节不成记录" % (len(raw) - off))
    return dict(items=items, story=story, bytes=len(raw)), errs


def check_one(path, verbose=True):
    rel = os.path.relpath(path, ROOT)
    state, errs = parse(path)
    items = state["items"]
    alive = [r for r in items if not r["deleted"]]
    anchors = [r for r in alive if r["pinned"]]

    # G2 锚点上限
    if len(anchors) > MAX_ANCHORS:
        errs.append("G2 锚点 %d 条，超过上限 %d" % (len(anchors), MAX_ANCHORS))

    # G4 不许存秘密
    for r in items:
        for pat, why in SECRET_PATTERNS:
            if pat.search(r["text"]):
                errs.append("G4 #%d 疑似%s：%s" % (r["id"], why, r["text"][:40]))

    # G6 单条长度
    for r in items:
        if len(r["text"].encode("utf-8")) > MAX_TEXT:
            errs.append("G6 #%d 正文 %d 字节，超过 %d（有人在绕过 zmem_add 直写？）"
                        % (r["id"], len(r["text"].encode("utf-8")), MAX_TEXT))

    # G5 规模与锚点匹配
    if len(alive) > 100 and not anchors:
        errs.append("G5 有 %d 条记忆却一条锚点都没有 —— 记忆在长，但四年后什么都不剩"
                    % len(alive))

    # G3 自述三道闸
    prev = None
    for s in state["story"]:
        ids = [int(x) for x in re.findall(r"#(\d+)", s["text"][: s["text"].find("]") + 1])
               if s["text"].startswith("[")]
        if not ids:
            errs.append("G3 自述 v%d 没有引用任何记忆（[#id]）—— 不许凭空抒情" % s["v"])
        for i in ids:
            if not (1 <= i <= len(items)):
                errs.append("G3 自述 v%d 引用了不存在的记忆 #%d" % (s["v"], i))
            elif items[i - 1]["deleted"]:
                errs.append("G3 自述 v%d 引用了已删除的 #%d（删了就该一起改掉）" % (s["v"], i))
        if prev is not None:
            gap = (s["t"] - prev["t"]) / float(DAY)
            if gap < STORY_GAP_DAYS - 0.01:
                errs.append("G3 自述 v%d 距上一版只有 %.1f 天（下限 %d）—— 人格在抖"
                            % (s["v"], gap, STORY_GAP_DAYS))
            body = s["text"]
            if body.startswith("["):
                body = body[body.find("]") + 1:]
            pb = prev["text"]
            if pb.startswith("["):
                pb = pb[pb.find("]") + 1:]
            ov = jacc(bigrams(body), bigrams(pb)) * 100
            if ov < STORY_DRIFT_PCT:
                errs.append("G3 自述 v%d 与上一版重合 %.0f%%（下限 %d%%）—— 那是换了个角色"
                            % (s["v"], ov, STORY_DRIFT_PCT))
        prev = s

    if verbose:
        span = ""
        if alive:
            span = "  %s ~ %s" % (
                __import__("time").strftime("%Y-%m-%d", __import__("time").gmtime(
                    min(r["t"] for r in alive) + 8 * 3600)),
                __import__("time").strftime("%Y-%m-%d", __import__("time").gmtime(
                    max(r["t"] for r in alive) + 8 * 3600)))
        print("%-46s %5d 条（锚点 %2d、墓碑 %2d、自述 %d 版）%8d 字节%s"
              % (rel, len(alive), len(anchors), len(items) - len(alive),
                 len(state["story"]), state["bytes"], span))
        for e in errs:
            print("    [不通过] %s" % e)
    return errs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--character", default="")
    ap.add_argument("--fail", action="store_true")
    a = ap.parse_args()

    pat = "data/%s/memory/chronicle.zm" % (a.character if a.character else "*")
    files = sorted(glob.glob(os.path.join(ROOT, pat)))
    if not files:
        print("没有记忆文件（data/<角色>/memory/chronicle.zm）—— 这是干净状态，不是错误")
        return 0

    total = 0
    bad = 0
    for f in files:
        errs = check_one(f)
        total += 1
        if errs:
            bad += 1
    print("-" * 96)
    print("共 %d 份记忆文件；%d 份不通过" % (total, bad))
    if a.fail and bad:
        print("长记忆体检：不通过")
        return 1
    print("长记忆体检：通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
