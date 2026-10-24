#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""physics_ref.py —— 2D 粒子摆链（zphys2）的**独立参考实现**，用来和 C 内核逐步对拍。

为什么要有它（T47.1 的验收口径之一）：
  物理内核这种东西，"看着像在动"根本不算对 —— 差一个系数、少一次归一化，
  表现上只是"摆得小一点"，眼睛分辨不出来，但以后导入别人的 physics3.json 就全错。
  所以先用 Python 照着官方算法独立写一遍（**不看 C 代码的实现，只看同一份算法说明**），
  再让两边跑同一个场景 600 步，**逐步对拍最大误差 < 1e-6**。

用法：
  python3 tools/physics_ref.py --emit     # 生成 tests/data/phys2_golden.json（给 C 单测对拍）
  python3 tools/physics_ref.py --verify   # 重新算一遍，和已提交的金标准比（selfcheck 调它）
  python3 tools/physics_ref.py --demo     # 打几行人看的数，确认"静止时还在动"

算法出处：Live2D Cubism Native Framework `src/Physics/CubismPhysics.cpp`
的 `UpdateParticles()` / `GetOutputAngle()`；四个旋钮名字照抄官方（DC70）。
★ 和官方的一处有意偏离见 DC77：官方那段旋转误用了被覆盖的 direction.X，这里是正确写法。
"""
import argparse
import json
import math
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GOLDEN = os.path.join(ROOT, "tests", "data", "phys2_golden.json")

# —— 这三个常量必须和 src/core/zphys2.h 一字不差（selfcheck 会比对）——
FPS = 60.0
STEP = 1.0 / FPS
AIR_RESISTANCE = 5.0
THRESHOLD = 0.001


def dir_to_radian(fx, fy, tx, ty):
    """官方 CubismMath::DirectionToRadian，结果规整到 (−π, π]。"""
    ret = math.atan2(ty, tx) - math.atan2(fy, fx)
    while ret < -math.pi:
        ret += math.pi * 2.0
    while ret > math.pi:
        ret -= math.pi * 2.0
    return ret


def normalize2(x, y):
    n = math.hypot(x, y)
    if n > 1e-12:
        return x / n, y / n
    return 0.0, -1.0


class Chain(object):
    """一条摆链。p[0] 是根（被输入拖着走，不积分）。"""

    def __init__(self, particles):
        # particles: [(radius, mobility, delay, acceleration), ...]，第 0 项是根（radius 忽略）
        self.n = len(particles)
        self.radius = [p[0] for p in particles]
        self.mobility = [p[1] for p in particles]
        self.delay = [p[2] for p in particles]
        self.accel = [p[3] for p in particles]
        self.x = [0.0] * self.n
        self.y = [0.0] * self.n
        self.lx = [0.0] * self.n
        self.ly = [0.0] * self.n
        self.vx = [0.0] * self.n
        self.vy = [0.0] * self.n
        self.lgx = [0.0] * self.n
        self.lgy = [-1.0] * self.n

    def reset(self, gx, gy):
        gx, gy = normalize2(gx, gy)
        self.x[0] = self.y[0] = 0.0
        for i in range(self.n):
            if i > 0:
                self.x[i] = self.x[i - 1] + gx * self.radius[i]
                self.y[i] = self.y[i - 1] + gy * self.radius[i]
            self.lx[i], self.ly[i] = self.x[i], self.y[i]
            self.vx[i] = self.vy[i] = 0.0
            self.lgx[i], self.lgy[i] = gx, gy

    def step(self, tx, ty, angle_deg, gx, gy, wx, wy, dt):
        gx, gy = normalize2(gx, gy)
        # 旋向照官方：currentGravity = (sin a, cos a) = 把 (0,1) 顺时针转 a
        a = math.radians(-angle_deg)
        ca, sa = math.cos(a), math.sin(a)
        cgx, cgy = normalize2(gx * ca - gy * sa, gx * sa + gy * ca)

        self.x[0], self.y[0] = tx, ty
        for i in range(1, self.n):
            fx = cgx * self.accel[i] + wx
            fy = cgy * self.accel[i] + wy

            self.lx[i], self.ly[i] = self.x[i], self.y[i]
            delay = self.delay[i] * dt * 30.0

            dx = self.x[i] - self.x[i - 1]
            dy = self.y[i] - self.y[i - 1]

            r = dir_to_radian(self.lgx[i], self.lgy[i], cgx, cgy) / AIR_RESISTANCE
            cs, sn = math.cos(r), math.sin(r)
            dx, dy = cs * dx - sn * dy, sn * dx + cs * dy

            self.x[i] = self.x[i - 1] + dx
            self.y[i] = self.y[i - 1] + dy

            self.x[i] += self.vx[i] * delay + fx * delay * delay
            self.y[i] += self.vy[i] * delay + fy * delay * delay

            nx, ny = normalize2(self.x[i] - self.x[i - 1], self.y[i] - self.y[i - 1])
            self.x[i] = self.x[i - 1] + nx * self.radius[i]
            self.y[i] = self.y[i - 1] + ny * self.radius[i]

            if abs(self.x[i]) < THRESHOLD:
                self.x[i] = 0.0

            if delay != 0.0:
                self.vx[i] = ((self.x[i] - self.lx[i]) / delay) * self.mobility[i]
                self.vy[i] = ((self.y[i] - self.ly[i]) / delay) * self.mobility[i]

            self.lgx[i], self.lgy[i] = cgx, cgy

    def angle(self, i, gx, gy, inverted=False):
        """第 i 个粒子相对重力方向的摆角（度）= 官方 GetOutputAngle。"""
        gx, gy = normalize2(gx, gy)
        if inverted:
            gx, gy = -gx, -gy
        dx = self.x[i] - self.x[i - 1]
        dy = self.y[i] - self.y[i - 1]
        if abs(dx) < 1e-12 and abs(dy) < 1e-12:
            return 0.0
        # ★ 取负的理由见 zphys2.c::zphys2_angle：像素空间 Y 轴向下，
        #   atan2 求出来的有号角相对官方（Y 轴向上）是镜像的。
        #   约定：正 = 摆往 +x（画面右）偏。
        return -math.degrees(dir_to_radian(gx, gy, dx, dy))


# ───────────────────────── 对拍场景（C 单测会原样复现）
# 一条 4 粒子的链，参数取"长发三段"的量级：根硬梢软、摆长递减。
PARTICLES = [
    (0.0,  0.00, 0.0, 0.0),    # 根
    (24.0, 0.95, 1.0, 1.0),
    (18.0, 0.92, 1.1, 1.0),
    (12.0, 0.88, 1.2, 0.9),
]
GRAVITY = (0.0, 1.0)           # 我们的像素空间 Y 向下 ⇒ "向下" = (0, +1)
NSTEPS = 600


def scenario_input(k):
    """三段式场景，一次把三件事都验了（C 单测复现同一份输入）：

      ①   0~200 步（0~3.3s）：转头。根粒子左右走 ±8px，整条链再叠 ±6° 倾角。
      ② 200~400 步（3.3~6.7s）：**输入彻底归零**。摆必须继续绕着重力方向衰减振荡
         —— 旧内核这一段输出恒为 0（"静止时头发是死的"就是这么来的）。
      ③ 400~600 步（6.7~10s）：只剩**呼吸**（0.28Hz、±1.2px 的极慢微动）。
         这一段是旧内核最致命的地方：它输出"滞后量"，0.28Hz 的输入摆锤完全跟得上，
         差值≈0（挂件表里实测 0.3px）；新内核输出的是**摆角**，根一动角度就变。
    """
    t = k * STEP
    if k < 200:
        return 8.0 * math.sin(2.0 * math.pi * 0.8 * t), 0.0, 6.0 * math.sin(2.0 * math.pi * 0.8 * t)
    if k < 400:
        return 0.0, 0.0, 0.0
    return 1.2 * math.sin(2.0 * math.pi * 0.28 * t), 0.0, 0.0


def run():
    ch = Chain(PARTICLES)
    ch.reset(*GRAVITY)
    rows = []
    for k in range(NSTEPS):
        tx, ty, ang = scenario_input(k)
        ch.step(tx, ty, ang, GRAVITY[0], GRAVITY[1], 0.0, 0.0, STEP)
        rows.append({
            "k": k,
            "in": [round(tx, 12), round(ty, 12), round(ang, 12)],
            # 对拍容差是 1e-6，存 9 位小数绰绰有余（文件也小一半）
            "pos": [[round(ch.x[i], 9), round(ch.y[i], 9)] for i in range(ch.n)],
            "ang": [round(ch.angle(i, *GRAVITY), 9) for i in range(1, ch.n)],
        })
    return rows


def build():
    return {
        "_note": "tools/physics_ref.py --emit 生成；C 单测 test_phys2_vs_reference 逐步对拍，"
                 "容差 1e-6。别手改这个文件，改算法就重新 --emit。",
        "fps": FPS, "air_resistance": AIR_RESISTANCE, "threshold": THRESHOLD,
        "gravity": list(GRAVITY),
        "particles": [list(p) for p in PARTICLES],
        "nsteps": NSTEPS,
        "steps": run(),
    }


def main():
    ap = argparse.ArgumentParser(description="2D 粒子摆链的参考实现")
    ap.add_argument("--emit", action="store_true", help="写出金标准 JSON")
    ap.add_argument("--verify", action="store_true", help="和已提交的金标准比对")
    ap.add_argument("--demo", action="store_true", help="打几行人看的数")
    args = ap.parse_args()

    if args.emit:
        os.makedirs(os.path.dirname(GOLDEN), exist_ok=True)
        with open(GOLDEN, "w", encoding="utf-8") as f:
            json.dump(build(), f, ensure_ascii=False, separators=(",", ":"))
            f.write("\n")
        print("已写出 %s（%d 步）" % (os.path.relpath(GOLDEN, ROOT), NSTEPS))
        return 0

    if args.verify:
        if not os.path.exists(GOLDEN):
            print("金标准不存在：%s（先跑 --emit）" % GOLDEN)
            return 1
        with open(GOLDEN, encoding="utf-8") as f:
            old = json.load(f)
        new = build()
        if old.get("nsteps") != new["nsteps"] or len(old.get("steps", [])) != len(new["steps"]):
            print("步数对不上：金标准 %s vs 现在 %s" % (old.get("nsteps"), new["nsteps"]))
            return 1
        worst = 0.0
        for key in ("fps", "air_resistance", "threshold", "gravity", "particles"):
            if old.get(key) != new[key]:
                print("参数对不上：%s 金标准 %s vs 现在 %s" % (key, old.get(key), new[key]))
                return 1
        for a, b in zip(old["steps"], new["steps"]):
            for pa, pb in zip(a["pos"], b["pos"]):
                worst = max(worst, abs(pa[0] - pb[0]), abs(pa[1] - pb[1]))
            for qa, qb in zip(a["ang"], b["ang"]):
                worst = max(worst, abs(qa - qb))
        ok = worst < 1e-8   # 金标准存了 9 位小数，这是取整噪声的量级
        print("参考实现 vs 金标准：最大偏差 %.3e → %s" % (worst, "一致" if ok else "**不一致**"))
        return 0 if ok else 1

    rows = run()
    print("步  输入x   摆角1     摆角2     摆角3")
    for k in (0, 50, 100, 199, 200, 210, 240, 300, 399, 450, 500, 599):
        r = rows[k]
        print("%3d %7.2f  %8.3f  %8.3f  %8.3f" % (k, r["in"][0], r["ang"][0], r["ang"][1], r["ang"][2]))
    pk = lambda a, b, j: max(abs(r["ang"][j]) for r in rows[a:b])
    print("\n① 转头段(0~3.3s) 发梢峰值 %.2f°" % pk(0, 200, 2))
    print("② 输入归零后 3.4~4.4s %.3f° / 5.4~6.4s %.3f°  ← 旧内核这里恒为 0" %
          (pk(205, 265, 2), pk(325, 385, 2)))
    print("③ 只剩呼吸(0.28Hz ±1.2px) 8~10s 峰值 %.3f°  ← 旧内核实测只有 0.3px 的滞后量" %
          pk(480, 600, 2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
