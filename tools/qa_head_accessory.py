#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""头部挂件（兽耳等）的几何体检 —— 对着跑起来的预览量，不靠肉眼。

为什么要有这个脚本
------------------
猫耳的位置和大小被连着打回了四次。前三次都是"我觉得差不多"然后交付，
用户看一眼就说不对。第四次用户的原话是「你自己也检测一下，然后学习和
参考教程以及网络上的资料」—— 这两件事缺一不可：

  · 光查教程不检测  ⇒ 不知道自己做出来的到底是多少；
  · 光检测不查教程  ⇒ 不知道该是多少，判据只能靠拍脑袋。

所以这个脚本做的是把**教程里的口径**变成**可执行的判据**。

判据的出处（docs/REFERENCE_NOTES.md 第三十三批有全文和 URL）
------------------------------------------------------------
  1. 大小：猫耳长 = 脸高的 1/3。
     medibangpaint.com「The ideal ear length ratio in cats is one third of
     the face length」、note.com/kakaman 同口径（兔 2/3、狐 1/2）。
  2. 耳根：必须被头发压住，不能画在头发之上。
     kiri-hana.com「耳が浮いて見えるのは『髪の上』に描いてしまうから」
     「髪の上に耳を『乗せる』のではなく、頭のラインに沿って『差し込む』」。
  3. 左右：「頭の円を時計に見立てて 11 時と 1 時」（kiri-hana.com），
     两耳合起来不该比头还宽。
  4. 形状：猫耳是「少し平べったい正三角形」（atam-academy.com），
     宽高比落在 0.7~1.0；明显大于 1 就会读成兔耳/摊开的叶子。

量法上踩过的四个坑（都在下面的实现里绕开了）
----------------------------------------------
  a. **逐列取最高不透明像素 ≠ 头发表面** —— 呆毛那根细尖会被当成发团，
     害我把发顶读成画布 y=55（真值 ≈118），一路错到耳根悬空。
     ⇒ 先做水平腐蚀，把细过 ~9px 的尖抹掉。
  b. **两帧差分会混进别的动件** —— 关耳朵拍一帧、开耳朵拍一帧做差，
     尾巴和呆毛一直在动，差分包围盒能跨到 y=746。
     ⇒ 每档连拍 6 帧取**逐像素均值**，动件自然糊掉。
  c. **软边头发会让差分虚高** —— 耳朵躲在半透明发梢后面时，合成 alpha
     会被顶过阈值，整条发缘都被误判成耳朵。
     ⇒ 判据改成**强跃变**：戴上 α≥200 且 摘掉 α≤60。
  d. **抗锯齿杂点会撑爆包围盒** —— 几粒孤立像素就能把耳高从 95 读成 171。
     ⇒ 连通域标记，只留最大的两块。

另有一个前提 bug（本轮一并修了，见 tools/make_rig.py）：
挂件开关参数以前绑的是 `{"param":"alpha","scale":1.0}`，而引擎的 alpha 是
**乘性**的（zrig.c:2764 `p_alpha *= clamp(1.0+v,0,1)`），v∈[0,1] 时因子恒为 1，
开关怎么拨都摘不掉 —— 本脚本依赖"摘掉"这一档，少了 offset:-1 就没法量。

用法
----
    ./build/zhuochong_preview --host 0.0.0.0 --port 5173 &
    ~/.imgenv/bin/python tools/qa_head_accessory.py
    ~/.imgenv/bin/python tools/qa_head_accessory.py --save-overlay logs/asset_qa/x.png

退出码 0 = 全部达标，1 = 有不达标项。
"""
import argparse
import io
import json
import sys
import time
import urllib.request
from collections import deque

import numpy as np
from PIL import Image

CANVAS_W = 848.0
FRAME_W = 466.0
K = FRAME_W / CANVAS_W          # 画布像素 → 渲染帧像素

# —— 判据区间（出处见上面的文档字符串）——
RATIO_LO, RATIO_HI = 0.26, 0.40     # 露出高 / 脸高，教程值 0.333
ASPECT_LO, ASPECT_HI = 0.60, 1.05   # 宽 / 高
SPAN_MAX = 1.02                     # 两耳总跨度 / 头最宽
ROOT_COVER_MIN = 80.0               # 耳根底下是头发的比例 %

N_FRAMES = 6
SETTLE = 1.2


def _get(base, path):
    with urllib.request.urlopen(base + path, timeout=8) as r:
        return r.read()


def grab(base, n=N_FRAMES):
    """连拍 n 帧取 alpha 均值 —— 把呆毛、眨眼这些动件糊掉。"""
    acc = None
    for _ in range(n):
        a = np.asarray(Image.open(io.BytesIO(
            _get(base, "/api/frame.png?s=100"))).convert("RGBA"))[..., 3]
        acc = a.astype(np.float64) if acc is None else acc + a
        time.sleep(0.3)
    return acc / float(n)


def hair_profile(alpha):
    """发团剖面：先水平腐蚀抹掉呆毛那类细尖，再逐列取最高不透明像素。"""
    m = alpha > 120
    e = m.copy()
    # ±7px 的水平腐蚀。4px 不够 —— 呆毛在 6 帧均值里会糊成一条十几像素宽的
    # 淡影，照样能骗过阈值，把发顶读成 y=66（真值 ≈118，在带网格的渲染图上
    # 核对过）。脸高是所有判据的分母，这里读错一次全表都跟着错。
    for s in range(1, 8):
        e[:, s:] &= m[:, :-s]
        e[:, :-s] &= m[:, s:]
    return m, e


def components(mask, keep=2):
    """连通域标记，返回最大的 keep 块的 (xs, ys)，按 x 均值排序。"""
    lab = np.zeros(mask.shape, np.int32)
    cur = 0
    sizes = {}
    for sy, sx in zip(*np.nonzero(mask)):
        if lab[sy, sx]:
            continue
        cur += 1
        q = deque([(sy, sx)])
        lab[sy, sx] = cur
        n = 0
        while q:
            y, x = q.popleft()
            n += 1
            for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                b, a = y + dy, x + dx
                if (0 <= b < mask.shape[0] and 0 <= a < mask.shape[1]
                        and mask[b, a] and not lab[b, a]):
                    lab[b, a] = cur
                    q.append((b, a))
        sizes[cur] = n
    if not sizes:
        return [], sizes
    top = sorted(sizes, key=sizes.get, reverse=True)[:keep]
    out = []
    for k in top:
        ys, xs = np.nonzero(lab == k)
        out.append((xs, ys))
    out.sort(key=lambda t: t[0].mean())
    return out, sizes


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:5173")
    ap.add_argument("--params", default="ParamAccEarL,ParamAccEarR",
                    help="要开关的挂件参数，逗号分隔")
    ap.add_argument("--chin", type=float, default=342.0,
                    help="下颌在画布 y 的位置。默认值是在带坐标网格的渲染图上"
                         "人工核对过的（logs/asset_qa/head_grid.png）")
    ap.add_argument("--save-overlay", default="")
    ap.add_argument("--parts", default="acc_ear_cat_l,acc_ear_cat_r")
    ap.add_argument("--root", default="characters/xiaoxun/forms/teen")
    ap.add_argument("--rig", default="characters/xiaoxun/forms/teen/rig.json")
    a = ap.parse_args()
    pids = [s for s in a.params.split(",") if s]

    for v in ("0", "1"):
        pass
    for pid in pids:
        _get(a.base, "/api/param?id=%s&v=0" % pid)
    time.sleep(SETTLE)
    off = grab(a.base)
    for pid in pids:
        _get(a.base, "/api/param?id=%s&v=1" % pid)
    time.sleep(SETTLE)
    on = grab(a.base)

    hair, eroded = hair_profile(off)
    rows = np.nonzero(eroded.any(axis=1))[0]
    if not len(rows):
        print("[qa] 取不到剪影，预览跑起来了吗？")
        return 2
    top = rows.min() / K
    face = a.chin - top

    # 强跃变判据 + ROI 锁在头部，再去连通域杂点
    roi = np.zeros(off.shape, bool)
    roi[0:int(260 * K), int(260 * K):int(590 * K)] = True
    mask = (on >= 200) & (off <= 60) & roi
    ears, sizes = components(mask, 2)
    if len(ears) < 2:
        print("[qa] 只找到 %d 块挂件区域，期望 2 块" % len(ears))
        return 2

    hw = np.nonzero(hair[int(300 * K)])[0]
    head_w = (hw.max() - hw.min() + 1) / K

    # 从 rig 读挂件脚印（底边的 x 区间和 y），用来做耳根覆盖率
    rig = json.load(open(a.rig))
    foot = {}
    for nm, pid in zip(("左耳", "右耳"), a.parts.split(",")):
        pt = next((q for q in rig["parts"] if q["id"] == pid), None)
        if pt is None:
            print("[qa] rig 里没有部件 %s" % pid)
            return 2
        im2 = Image.open(a.root + "/" + pt["file"])
        w = im2.size[0] * float(pt.get("scale", 1.0))
        ax, ay = pt.get("anchor", [0.5, 0.5])
        px, py = pt["pos"]
        foot[nm] = (px - w * ax, px + w * (1.0 - ax), py)

    print("参照尺（画布像素）：发团顶 y=%.0f  下颌 y=%.0f  **脸高 %.0f**  头最宽 %.0f"
          % (top, a.chin, face, head_w))
    print("教程目标：露出高 = 脸高/3 = %.0f\n" % (face / 3.0))
    hdr = ("%-6s %-10s %-16s %-8s %-10s %s"
           % ("", "露出高", "/脸高 目标.33", "宽", "宽/高 .6~1.05", "耳根压在发下"))
    print(hdr)
    print("-" * 74)

    bad = []
    allx = []
    for name, (xs, ys) in zip(("左耳", "右耳"), ears):
        allx += [xs.min(), xs.max()]
        h = (ys.max() - ys.min() + 1) / K
        w = (xs.max() - xs.min() + 1) / K
        ratio = h / face
        asp = w / h
        # 耳根覆盖率要按**耳件的真实脚印**量，不能按"可见部分的最低点"量 ——
        # 后者是循环论证：可见部分之所以到此为止，正是因为再往下被头发盖住了，
        # 于是它下面必然有头发，这条判据永远是 100%，测不出外侧角悬空。
        # 真实脚印从 rig 里读：pos 是锚点落点，anchor=[0.5,1.0] ⇒ 底边中点。
        fx0, fx1, fy = foot[name]
        row = min(int(round(fy * K)), hair.shape[0] - 1)
        seg = hair[row, int(round(fx0 * K)):int(round(fx1 * K)) + 1]
        cover = seg.mean() * 100.0 if seg.size else 0.0
        c1 = RATIO_LO <= ratio <= RATIO_HI
        c2 = ASPECT_LO <= asp <= ASPECT_HI
        c3 = cover >= ROOT_COVER_MIN
        if not c1:
            bad.append("%s 露出高/脸高 %.2f 不在 %.2f~%.2f" % (name, ratio, RATIO_LO, RATIO_HI))
        if not c2:
            bad.append("%s 宽高比 %.2f 不在 %.2f~%.2f" % (name, asp, ASPECT_LO, ASPECT_HI))
        if not c3:
            bad.append("%s 耳根只有 %.0f%% 压在头发下（该 ≥%.0f%%，否则就是"
                       "教程说的『画在髪の上』会浮起来）" % (name, cover, ROOT_COVER_MIN))
        print("%-6s %-10.0f %-16s %-8.0f %-10s %s"
              % (name, h, "%.2f %s" % (ratio, "OK" if c1 else "NG"), w,
                 "%.2f %s" % (asp, "OK" if c2 else "NG"),
                 "%.0f%% %s" % (cover, "OK" if c3 else "NG")))

    span = (max(allx) - min(allx) + 1) / K
    sp = span / head_w
    c4 = sp <= SPAN_MAX
    if not c4:
        bad.append("两耳总跨度/头宽 %.2f > %.2f（横着铺满了整个头顶）" % (sp, SPAN_MAX))
    tip = min(ys.min() for _, ys in ears) / K
    c5 = tip > 2
    if not c5:
        bad.append("耳尖贴到画布顶了（y=%.0f），旋转时会被切" % tip)
    print("-" * 74)
    print("两耳总跨度 %.0f / 头最宽 %.0f = %.2f %s（惯例 ≤%.2f）"
          % (span, head_w, sp, "OK" if c4 else "NG", SPAN_MAX))
    print("耳尖离画布顶 %.0f px %s" % (tip, "OK" if c5 else "NG"))

    if a.save_overlay:
        im = Image.open(io.BytesIO(_get(a.base, "/api/frame.png?s=100"))).convert("RGB")
        ov = np.asarray(im).copy()
        keep = np.zeros(mask.shape, bool)
        for xs, ys in ears:
            keep[ys, xs] = True
        ov[keep] = [255, 0, 0]
        Image.fromarray(ov).crop((140, 0, 340, 170)).resize(
            (800, 680), Image.NEAREST).save(a.save_overlay)
        print("留证图：%s（红 = 判为挂件的像素）" % a.save_overlay)

    print()
    if bad:
        print("不达标 %d 项：" % len(bad))
        for b in bad:
            print("  · " + b)
        return 1
    print("全部达标。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
