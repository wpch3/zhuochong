#!/usr/bin/env python3
"""帧对拍：把"两个引擎 / 两个 rig"的**同一时刻**画出来，逐像素比。

为什么要有这个工具（2026-10-25 血的教训）：
    在同一台已经跑着的预览进程里反复发 `/api/param?all=1&reset=1` + `/api/step`，
    抓到的帧**不是确定的** —— reset 只清参数，清不掉内部计时器/随机流/滞后状态。
    实测：同一个进程连抓两次（n=1500），差 274 px；两个进程同二进制，差 1300 px。
    于是"新旧引擎 diff 0"这种结论可以纯靠运气成立，也可以纯靠运气被推翻。

    唯一稳的协议是：**每次抓图都新起一个进程、只抓第一帧、抓完就杀**。
    这样实测 old/old、new/new、old/new 全是 0 px（T66.10 就是这么验的）。

用法：
    # 抓一帧（新进程，抓完自动退出）
    python3 tools/frame_ab.py shot --bin ./build/zhuochong_preview --root . \\
        --out /tmp/new.png --form teen --n 1500

    # 两边各抓一帧再比（同一条请求序列，只有可执行文件/root 不同）
    python3 tools/frame_ab.py ab \\
        --bin-a /tmp/zold/build/zhuochong_preview --root-a /tmp/zold \\
        --bin-b ./build/zhuochong_preview --root-b . \\
        --out-a /tmp/a.png --out-b /tmp/b.png --form teen --n 1500

退出码：0 = 差异为 0；1 = 有差异（会打印差异像素数与外接框）；2 = 抓图失败。
"""
import argparse
import io
import os
import socket
import subprocess
import sys
import time
import urllib.request

# 这几个参数在"+表情/动作摆好"的姿势下是固定值；不钉住的话微动/表情会自己动，
# 差异就说不清是引擎改的还是它自己动的。
PIN = [
    ("ParamAngleX", 0.6), ("ParamAngleY", -0.4), ("ParamAngleZ", 0.3),
    ("ParamBodyAngleX", 0.5), ("ParamEyeBallX", 0.7), ("ParamEyeBallY", -0.5),
    ("ParamMouthOpenY", 0.6),
]


def wait_port(port, timeout=20.0):
    end = time.time() + timeout
    while time.time() < end:
        s = socket.socket()
        s.settimeout(0.3)
        try:
            s.connect(("127.0.0.1", port))
            return True
        except OSError:
            time.sleep(0.02)
        finally:
            s.close()
    return False


def free_port(start=5300, tries=200):
    for p in range(start, start + tries):
        s = socket.socket()
        try:
            s.bind(("127.0.0.1", p))
            return p
        except OSError:
            continue
        finally:
            s.close()
    raise SystemExit("找不到空闲端口")


def shoot(exe, root, out, form="teen", n=1500, pin=True, port=None):
    if not os.path.exists(exe):
        raise SystemExit("可执行文件不存在：%s（先 make -s build/zhuochong_preview）" % exe)
    port = port or free_port()
    stderr = subprocess.DEVNULL
    p = subprocess.Popen([exe, "--root", root, "--port", str(port), "--bind", "127.0.0.1"],
                         stdout=subprocess.DEVNULL, stderr=stderr)
    try:
        if not wait_port(port):
            raise SystemExit("预览没起来（端口 %d 没监听）" % port)
        base = "http://127.0.0.1:%d" % port

        def get(path):
            return urllib.request.urlopen(base + path, timeout=60).read()

        # 顺序有讲究：先定格形态，再关环境运动，再冻结时钟，最后才是写参数。
        # （/api/pause 要在 ambient/physics 之后发 —— 反过来会把摆动参数冻住）
        get("/api/form?id=" + form)
        get("/api/ambient?on=0")
        get("/api/physics?on=0")
        get("/api/pause?on=1&t=0")
        get("/api/param?all=1&reset=1")
        if pin:
            for k, v in PIN:
                try:
                    get("/api/param?id=%s&v=%f" % (k, v))
                except urllib.error.HTTPError:
                    pass       # 这套 rig 没这个参数就算了
        get("/api/step?n=%d&dt=0.016" % n)
        data = get("/api/frame.png")
        with io.open(out, "wb") as f:
            f.write(data)
    finally:
        p.terminate()
        try:
            p.wait(timeout=10)
        except subprocess.TimeoutExpired:
            p.kill()
    return out


def diff(pa, pb, thr=8):
    """返回 (差异像素数, 外接框)。只用标准库之外的 numpy/PIL —— 用 .imgenv 的 python。"""
    try:
        import numpy as np
        from PIL import Image
    except ImportError:
        raise SystemExit("需要 numpy + PIL：用 /home/user/.imgenv/bin/python 跑")
    a = np.asarray(Image.open(pa).convert("RGBA")).astype(int)
    b = np.asarray(Image.open(pb).convert("RGBA")).astype(int)
    if a.shape != b.shape:
        return -1, None
    m = np.abs(a - b).max(2) > thr
    n = int(m.sum())
    if n == 0:
        return 0, None
    ys, xs = np.nonzero(m)
    return n, (int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max()))


def main(argv=None):
    ap = argparse.ArgumentParser(description="新进程抓单帧 / 两引擎逐像素对拍")
    sub = ap.add_subparsers(dest="cmd", required=True)

    s1 = sub.add_parser("shot", help="抓一帧")
    s1.add_argument("--bin", default="./build/zhuochong_preview")
    s1.add_argument("--root", default=".")
    s1.add_argument("--out", required=True)
    s1.add_argument("--form", default="teen")
    s1.add_argument("--n", type=int, default=1500, help="冻结后推多少帧（默认 1500）")
    s1.add_argument("--no-pin", action="store_true", help="不钉姿势参数（会自己微动，别用来对拍）")

    s2 = sub.add_parser("ab", help="两边各抓一帧再比")
    s2.add_argument("--bin-a", default="/tmp/zold/build/zhuochong_preview")
    s2.add_argument("--root-a", default="/tmp/zold")
    s2.add_argument("--bin-b", default="./build/zhuochong_preview")
    s2.add_argument("--root-b", default=".")
    s2.add_argument("--out-a", default="/tmp/frame_a.png")
    s2.add_argument("--out-b", default="/tmp/frame_b.png")
    s2.add_argument("--form", default="teen")
    s2.add_argument("--n", type=int, default=1500)
    s2.add_argument("--thr", type=int, default=8, help="通道差阈值（默认 8，和别的闸一致）")

    a = ap.parse_args(argv)
    if a.cmd == "shot":
        out = shoot(a.bin, a.root, a.out, a.form, a.n, not a.no_pin)
        print("抓好了：%s" % out)
        return 0

    shoot(a.bin_a, a.root_a, a.out_a, a.form, a.n)
    shoot(a.bin_b, a.root_b, a.out_b, a.form, a.n)
    n, box = diff(a.out_a, a.out_b, a.thr)
    if n < 0:
        print("尺寸都不一样，没法对拍：%s vs %s" % (a.out_a, a.out_b))
        return 2
    if n == 0:
        print("逐像素相同（0 px > %d）" % a.thr)
        return 0
    print("差异 %d px，外接框 x%d..%d y%d..%d" % (n, box[0], box[2], box[1], box[3]))
    print("图：%s  %s" % (a.out_a, a.out_b))
    return 1


if __name__ == "__main__":
    sys.exit(main())
