#!/usr/bin/env python3
"""标定眼球微动幅度：把 rig 的 gaze.micro.amp 扫一遍，量虹膜质心实际漂了几个像素。

为什么要有这个工具：视线满量程只有 max_offset = 4.0 x 2.5 像素，
"微动"要落在亚像素到 1 像素之间，靠猜必然不是太小看不见就是太大像眼神乱飘。
而且渲染链里有取整，归一化幅度和实际像素位移不是简单线性关系 —— 必须实测。

用法：python3 tools/calib_saccade.py [--character xiaoxun --form teen]
"""
import argparse, json, os, shutil, subprocess, sys, tempfile

HARNESS = r'''
#include "zrig.h"
#include <stdio.h>
#include <stdlib.h>
int main(int argc, char **argv) {
    zrig *r = zrig_load(argv[2], argv[1], NULL);
    if (!r) { fprintf(stderr, "load failed\n"); return 2; }
    double t;
    for (t = 0.0; t <= 30.0 + 1e-9; t += 1.0 / 30.0) {
        zrig_tick(r, t);
        printf("%.4f %.6f %.6f\n", t, zrig_gaze_eff_x(r), zrig_gaze_eff_y(r));
    }
    zrig_free(r);
    return 0;
}
'''

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--character", default="xiaoxun")
    ap.add_argument("--form", default="teen")
    ap.add_argument("--amps", default="0.0,0.10,0.18,0.26,0.34,0.50")
    a = ap.parse_args()
    base = os.path.join("characters", a.character, "forms", a.form)
    rig_p = os.path.join(base, "rig.json")
    with open(rig_p, encoding="utf-8") as f:
        rig = json.load(f)
    mx, my = rig["gaze"]["max_offset"]

    tmp = tempfile.mkdtemp(prefix="calib_sacc_")
    try:
        src = os.path.join(tmp, "h.c")
        with open(src, "w") as f:
            f.write(HARNESS)
        exe = os.path.join(tmp, "h")
        cc = ["gcc", "-O2", "-std=c11", "-D_POSIX_C_SOURCE=200809L", "-Isrc/core",
              "-o", exe, src] + sorted(
                  os.path.join("src/core", x) for x in os.listdir("src/core")
                  if x.endswith(".c")) + ["-lm", "-lpthread"]
        subprocess.run(cc, check=True)

        print(f"max_offset = {mx} x {my} px（满量程）")
        print(f"{'amp':>6} {'峰值px_x':>9} {'RMS px_x':>9} {'峰值px_y':>9} {'每分钟微跳':>11}")
        rows = []
        for amp in [float(x) for x in a.amps.split(",")]:
            rig.setdefault("gaze", {})["micro"] = {
                "amp": amp, "gap_min": 0.45, "gap_max": 1.60, "speed": 16.0}
            with open(rig_p, "w", encoding="utf-8") as f:
                json.dump(rig, f, ensure_ascii=False, indent=2)
            out = subprocess.run([exe, base, rig_p], check=True,
                                 capture_output=True, text=True).stdout
            xs, ys = [], []
            for line in out.strip().splitlines():
                _, gx, gy = line.split()
                xs.append(float(gx) * mx)
                ys.append(float(gy) * my)
            peak = max(abs(v) for v in xs)
            rms = (sum(v * v for v in xs) / len(xs)) ** 0.5
            peaky = max(abs(v) for v in ys)
            # 数"换目标"的次数：相邻帧差的符号翻转近似不可靠，直接看速度尖峰
            d = [abs(xs[i + 1] - xs[i]) for i in range(len(xs) - 1)]
            thr = (max(d) * 0.35) if max(d) > 0 else 1e9
            jumps, armed = 0, True
            for v in d:
                if v >= thr and armed: jumps, armed = jumps + 1, False
                elif v < thr * 0.4: armed = True
            print(f"{amp:>6.2f} {peak:>9.2f} {rms:>9.2f} {peaky:>9.2f} {jumps * 2:>11}")
            rows.append((amp, peak, rms))
        print("\n判读：峰值落在 0.8~1.2px 之间最合适 —— 亚像素级看不出来，"
              "超过 1.5px 就是 cgbox 警告的\"常に慌てている\"。")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

if __name__ == "__main__":
    sys.exit(main())
