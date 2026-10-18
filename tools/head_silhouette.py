#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""头部剪影的连续性检查（T46.8）。

2026-10-18 第九问的教训：给 twin/pony 加了 `hide_parts:[hair_side_l, hair_side_r]`
之后，画面上出现了四个用户能一眼看见、而所有既有闸门都查不出来的缺陷 ——
人耳裸露在脸颊上、后发壳的平切口横在颧骨、切件残留的发丝碎片、头部剪影缺一块。

根因是同一件事：**鬓发是承重件**，它底下的 `seg_head` 是一张光头侧脸、
`hair_back` 的下沿是一条本来就指望被盖住的平切口。藏掉它，底下没有东西接着。

这个模块把"底下有没有东西"量成一个**几何判据**：

    ① 接管闸（硬闸）：某一档藏掉的件，必须由这一档**自己带的差分件**盖住 ≥95%。
    ② 头饰尺寸闸（硬闸）：戴头上的件按**实测剪影宽度**定标，不许拿抽象 head unit。
    ③ 剪影断崖（参考值）：从头顶往下，宽度猛收一截往往就是某个零件的平切口露了；
       但双马尾会把最宽行拉到发梢、下颌本身也会收窄，所以这一项只打印不判死。

真人/二次元的头都满足这条：颅顶最窄，往下到颧骨最宽，再到下颌收窄 —— 而收窄是
**渐变**的。一旦某一行比上一行猛地窄掉一大截，那就是某个零件的直边切口暴露了。

实测（teen，画布像素）：
  · 保留鬓发：全程最大单步收窄 3.4%（合格）
  · 隐藏鬓发：y258→y278 从 132 掉到 95，单步 **-28%**（当场抓到）

用法：
    python3 tools/head_silhouette.py --character xiaoxun --form teen [--json]
退出码 0 = 全过，1 = 有档位不合格。
"""
import argparse
import glob
import io
import json
import os
import sys

MAX_DROP = 0.12          # 单步最大允许收窄比例
ROW_STEP = 10            # 采样步长（画布像素）
MIN_ROW_PX = 14          # 少于这些像素的行当作呆毛细尖，不参与
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load_rig(base):
    with io.open(os.path.join(base, "rig.json"), encoding="utf-8") as f:
        return json.load(f)


def part_mask(base, part, canvas, np, Image):
    """把一个部件按 rig 里的 pos/anchor/scale 贴到画布上，返回 alpha 掩码。"""
    im = Image.open(os.path.join(base, part["file"])).convert("RGBA")
    sc = part.get("scale", 1.0)              # 可能是标量，也可能是 [sx, sy]
    sx, sy = (float(sc[0]), float(sc[1])) if isinstance(sc, (list, tuple)) \
        else (float(sc), float(sc))
    if (sx, sy) != (1.0, 1.0):
        im = im.resize((max(1, int(im.width * sx)), max(1, int(im.height * sy))),
                       Image.LANCZOS)
    ax, ay = part.get("anchor", [0, 0])
    x = int(round(part["pos"][0] - ax * im.width))
    y = int(round(part["pos"][1] - ay * im.height))
    out = Image.new("L", canvas, 0)
    out.paste(im.getchannel("A"), (x, y))
    return np.asarray(out) > 110


def visible_ids(rig, picks):
    """picks: {组 id: 档位 id}。返回这一组合下应当显示的部件 id 集合。"""
    posed, chosen, hidden = set(), set(), set()
    for g in rig.get("poses", []):
        for e in g.get("entries", []):
            posed |= set(e.get("parts") or [])
        pick = picks.get(g["id"], g.get("default"))
        ent = next((e for e in g.get("entries", []) if e["id"] == pick), None)
        if ent:
            chosen |= set(ent.get("parts") or [])
            hidden |= set(ent.get("hide") or [])
    ids = {p["id"] for p in rig["parts"]}
    return (ids - posed | chosen) - hidden


def profile(base, rig, picks, np, Image, head_only=True):
    """返回 [(画布行, 剪影宽度)]，只取头部区域。"""
    canvas = (int(rig["canvas"]["w"]), int(rig["canvas"]["h"]))
    keep = visible_ids(rig, picks)
    acc = np.zeros((canvas[1], canvas[0]), dtype=bool)
    for p in rig["parts"]:
        if p["id"] not in keep:
            continue
        if head_only and p.get("group") != "head":
            continue
        if p["id"].startswith("fx_"):            # 闪光特效不是身体
            continue
        acc |= part_mask(base, p, canvas, np, Image)
    rows = []
    for y in range(0, canvas[1], ROW_STEP):
        idx = np.nonzero(acc[y])[0]
        if len(idx) < MIN_ROW_PX:
            continue
        rows.append((y, int(idx.max() - idx.min()), int(idx.min()), int(idx.max())))
    return rows


def check_form(character, form, verbose=True):
    from PIL import Image
    import numpy as np
    base = os.path.join(ROOT, "characters", character, "forms", form)
    rig = load_rig(base)
    anc_p = os.path.join(base, "design", "anchors.json")
    with io.open(anc_p, encoding="utf-8") as f:
        anc = json.load(f)
    oy = float(rig["canvas"]["h"]) - float(anc["meta"]["height_px"])
    # 下巴以下（脖子）本来就该收窄，不在检查区间内
    y_stop = oy + float(anc["points"]["mouth_line"][1])

    groups = {g["id"]: [e["id"] for e in g.get("entries", [])] for g in rig.get("poses", [])}
    hair = ["none"] + groups.get("hairstyle", []) if "hairstyle" in groups else ["none"]
    results = []
    for hs in hair:
        picks = {"hairstyle": hs, "hood_pose": "down"}
        rows = [r for r in profile(base, rig, picks, np, Image) if r[0] <= y_stop]
        worst, worst_y = 0.0, None
        for (y0, w0, _, _), (y1, w1, _, _) in zip(rows, rows[1:]):
            if w0 <= 0:
                continue
            drop = (w0 - w1) / float(w0)
            if drop > worst:
                worst, worst_y = drop, y1
        ok = worst <= MAX_DROP
        results.append({"hairstyle": hs, "worst_drop": round(worst, 4),
                        "at_y": worst_y, "ok": ok, "rows": len(rows)})
        if verbose:
            print("  %-6s %-4s 最大单步收窄 %5.1f%%  @y=%s  （%d 行）%s"
                  % (form, hs, worst * 100, worst_y, len(rows),
                     "" if ok else "  ← 参考值偏大（下颌收窄也会命中，仅供人工复核）"))
    return results


MAX_HOLE = 0.02           # 藏掉之后露出**透明背景**的面积上限（占被藏件）

def hole_ratio(base, rig, hidden, region, canvas, np, Image):
    """露出来的那块，底下**有没有东西接着**——返回露出透明背景的面积占比。

    只合成层序低于 hidden 的那些件（压在上面的不算接管）。
    """
    lay = float(hidden.get("layer", 0))
    base_im = Image.new("RGBA", canvas, (0, 0, 0, 0))
    for p in sorted(rig["parts"], key=lambda q: float(q.get("layer", 0))):
        if float(p.get("layer", 0)) >= lay:
            continue
        im = Image.open(os.path.join(base, p["file"])).convert("RGBA")
        sc = p.get("scale", 1.0)
        sx, sy = (float(sc[0]), float(sc[1])) if isinstance(sc, (list, tuple)) \
            else (float(sc), float(sc))
        if (sx, sy) != (1.0, 1.0):
            im = im.resize((max(1, int(im.width * sx)), max(1, int(im.height * sy))),
                           Image.LANCZOS)
        ax, ay = p.get("anchor", [0, 0])
        lyr = Image.new("RGBA", canvas, (0, 0, 0, 0))
        lyr.paste(im, (int(round(p["pos"][0] - ax * im.width)),
                       int(round(p["pos"][1] - ay * im.height))))
        base_im = Image.alpha_composite(base_im, lyr)
    a = np.asarray(base_im)
    opaque = np.asarray(a[..., 3]) > 110
    return float((region & ~opaque).sum()) / float(max(1, int(region.sum())))


def hide_backing(character, form, need=0.45):
    """『这一档藏掉的件，必须由**这一档自己带的件**接管』闸。

    第九问的四个缺陷（人耳裸露在脸颊、后发壳平切口横在颧骨、发丝碎片、剪影缺块）
    都出自第八问那条 hide_parts:[hair_side_l, hair_side_r] —— 只藏不换。

    判据两条，都要满足：
      ① 接管：这一档自己带的差分件盖住被藏件 >= need。
         接管者**只能是这一档自己的件**，不算碰巧垫在底下的本体。
      ② 不破洞：藏掉之后露出**透明背景**的面积 <= MAX_HOLE。

    实测（teen，2026-10-18。twin/pony 两档各自带了 hair_sweep_* 两缕掠发）：
      twin  hair_side_l 77.6% / hair_side_r 82.9%      破洞 0.00%
      pony  hair_side_l 52.0% / hair_side_r 83.1%      破洞 0.00%   <- 最紧
      第八问那版（只藏不换）                0% / 0%
    阈值取 45%：对最紧的 pony 左侧留 7 个点余量，对第八问那版有 45 个点。
    为什么不取更高 —— 向后掠的细缕本来就比齐腮鬓发窄，覆盖率天生到不了 90%，
    硬抬阈值只会逼出"为过闸而画的假件"。第九问那版定的 95% 有个隐含前提
    （被藏件底下是见不得人的光头底图），第十问用 tools/make_scalp_patch.py
    把 seg_head 的头皮补画之后（Live2D 官方 PSD 教程：元画で隠れていた部分の
    描き足しを忘れずに / docs.live2d.com/en/cubism-editor-tutorials/psd/），
    那个前提没了，数也就跟着改。

    走过的弯路，省得下次再走：中间试过"露出来的是不是头发色"和"假边最长横向
    连段"两种像素判据，**负向对照都抓不到**——把补画前的光头底图塞回去，两个
    数几乎不动（18.28% -> 18.26%）。因为被藏件露出来的那块早被差分件和前髪盖掉
    了，补画的像素根本不在量程里。判据必须落在"谁来接管"这种结构事实上。
    """
    from PIL import Image
    import numpy as np
    base = os.path.join(ROOT, "characters", character, "forms", form)
    rig = load_rig(base)
    canvas = (int(rig["canvas"]["w"]), int(rig["canvas"]["h"]))
    by = {p["id"]: p for p in rig["parts"]}
    out = []
    for g in rig.get("poses", []):
        for ent in g.get("entries", []):
            hides = [h for h in (ent.get("hide") or []) if h in by]
            if not hides:
                continue
            own = np.zeros((canvas[1], canvas[0]), dtype=bool)
            for pid in (ent.get("parts") or []):
                if pid in by:
                    own |= part_mask(base, by[pid], canvas, np, Image)
            for h in hides:
                mk = part_mask(base, by[h], canvas, np, Image)
                tot = max(1, int(mk.sum()))
                cov = int((mk & own).sum()) / float(tot)
                rest = mk & ~own
                hole = 0.0 if not rest.any() else \
                    hole_ratio(base, rig, by[h], rest, canvas, np, Image)
                out.append({"group": g["id"], "entry": ent["id"], "part": h,
                            "area_px": tot, "cover": cov, "hole": hole,
                            "max_hole": MAX_HOLE, "need": need,
                            "ok": cov >= need and hole <= MAX_HOLE})
    return out


def headwear_fit(character, form, parts=("acc_hood_up",)):
    """『戴在头上的件要按头量尺寸』闸。

    第八问那版兜帽之所以"大小完全不匹配"却过了闸，是因为旧闸拿 anchors 里的
    **抽象 head unit（278px）** 当尺子 —— 那是个比例常数，不是头的实际宽度。
    头部剪影实测只有 244px 宽，兜帽 370px，1.52 倍，看着就是顶在头上的一口锅。
    这里改用**实测剪影宽度**，并顺带查帽顶不许低于头顶（会削掉颅顶）。
    """
    from PIL import Image
    import numpy as np
    base = os.path.join(ROOT, "characters", character, "forms", form)
    rig = load_rig(base)
    canvas = (int(rig["canvas"]["w"]), int(rig["canvas"]["h"]))
    by = {p["id"]: p for p in rig["parts"]}
    rows = profile(base, rig, {"hairstyle": "none", "hood_pose": "down"}, np, Image)
    hw = max((w for _, w, _, _ in rows), default=0)
    htop = min((y for y, _, _, _ in rows), default=0)
    out = []
    for pid in parts:
        if pid not in by:
            continue
        mk = part_mask(base, by[pid], canvas, np, Image)
        ys, xs = np.nonzero(mk)
        if not len(xs):
            continue
        w = int(xs.max() - xs.min())
        ratio = w / float(hw or 1)
        top_ok = int(ys.min()) <= htop + 12
        out.append({"part": pid, "width_px": w, "head_width_px": hw,
                    "ratio": round(ratio, 3), "top_y": int(ys.min()),
                    "head_top_y": htop, "covers_crown": top_ok,
                    "ok": 1.10 <= ratio <= 1.40 and top_ok})
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--character", default="xiaoxun")
    ap.add_argument("--form", default=None, help="不给就查这个角色所有 ready 形态")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    forms = [a.form] if a.form else []
    if not forms:
        for p in sorted(glob.glob(os.path.join(ROOT, "characters", a.character,
                                               "forms", "*", "rig.json"))):
            forms.append(os.path.basename(os.path.dirname(p)))
    allr, bad = [], 0
    for fm in forms:
        try:
            rs = check_form(a.character, fm, verbose=not a.json)
        except FileNotFoundError:
            continue
        for r in rs:
            r["form"] = fm
            r["kind"] = "profile"
            allr.append(r)
        for r in hide_backing(a.character, fm):
            r["form"] = fm
            r["kind"] = "hide_backing"
            allr.append(r)
            bad += 0 if r["ok"] else 1
            if not a.json:
                print("  %-6s %s:%s 藏 %-14s 本档自带件覆盖 %5.1f%%  %s"
                      % (fm, r["group"], r["entry"], r["part"], r["cover"] * 100,
                         "" if r["ok"] else "← 没人接管，底图会露出来"))
        for r in headwear_fit(a.character, fm):
            r["form"] = fm
            r["kind"] = "headwear_fit"
            allr.append(r)
            bad += 0 if r["ok"] else 1
            if not a.json:
                print("  %-6s %-14s 外宽 %d / 头宽 %d = %.2f 倍，帽顶 y=%d（头顶 %d）%s"
                      % (fm, r["part"], r["width_px"], r["head_width_px"],
                         r["ratio"], r["top_y"], r["head_top_y"],
                         "" if r["ok"] else "  ← 尺寸不匹配"))
    if a.json:
        print(json.dumps(allr, ensure_ascii=False, indent=2))
    else:
        print("头部几何：%d 项，%d 项不合格" % (len(allr), bad))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
