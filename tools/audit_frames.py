#!/usr/bin/env python3
"""
audit_frames.py - 一键产出铁律一要求的九宫格验收图（R2）

用法：
    python3 tools/audit_frames.py --port 5175 --out docs/qa/audit_nine_grid.png
    make audit-frames

产出：3×3 九宫格（转头 -30/0/+30 × 眨眼 0/0.5/1）+ 3 张 debug 叠加（wireframe/bones/hitbox）
证据入库 docs/qa/，不落 /tmp。
"""
import argparse, os, urllib.request, urllib.error, time, subprocess, sys, json

def fetch(p, url):
    try:
        with urllib.request.urlopen(url, timeout=10) as r:
            open(p,'wb').write(r.read())
        return True
    except Exception as e:
        print(f"  fail {url}: {e}", file=sys.stderr)
        return False

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--port', type=int, default=5175)
    ap.add_argument('--root', default='.')
    ap.add_argument('--out', default='docs/qa/audit_nine_grid.png')
    ap.add_argument('--spawn', action='store_true', help='自己起一个预览服务（用完即关）')
    args = ap.parse_args()

    base = f"http://127.0.0.1:{args.port}"
    spawned = None
    if args.spawn:
        # 起服务
        proc = subprocess.Popen(
            ["./build/zhuochong_preview","--root", args.root, "--port", str(args.port), "--bind","0.0.0.0"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        spawned = proc
        time.sleep(2)
        print(f"spawned preview pid {proc.pid} on {args.port}")

    try:
        # 尝试连上
        for _ in range(10):
            try:
                urllib.request.urlopen(base+"/api/info.json", timeout=2).read()
                break
            except: time.sleep(0.5)
        else:
            print("无法连上预览服务，确认已 make preview 或加 --spawn", file=sys.stderr)
            return 1

        outdir = os.path.dirname(os.path.abspath(args.out)) or "."
        os.makedirs(outdir, exist_ok=True)
        tmp = "/tmp/audit_frames_nine"
        os.makedirs(tmp, exist_ok=True)

        # 冻结时钟，逐格抓
        angles = [("-30", -30), ("0", 0), ("+30", 30)]
        blinks = [("open", 0.0), ("half", 0.5), ("closed", 1.0)]
        idx = 0
        for bi, (bn, bv) in enumerate(blinks):
            for ai, (an, av) in enumerate(angles):
                # 用 ParamAngleX 转头，blink 手动值
                urllib.request.urlopen(f"{base}/api/param?id=ParamAngleX&v={av}", timeout=5).read()
                urllib.request.urlopen(f"{base}/api/pause?on=1&t={idx*0.1}", timeout=5).read()
                # 眨眼：直接写 blink 手动值（ParamEyeLOpen）
                if bv == 0:
                    urllib.request.urlopen(f"{base}/api/param?all=1&reset=1", timeout=5).read()
                else:
                    urllib.request.urlopen(f"{base}/api/param?id=ParamEyeLOpen&v={1-bv}", timeout=5).read()
                    urllib.request.urlopen(f"{base}/api/param?id=ParamEyeROpen&v={1-bv}", timeout=5).read()
                time.sleep(0.15)
                p = os.path.join(tmp, f"cell_{bi}_{ai}.png")
                fetch(p, f"{base}/api/frame.png?debug=all")
                print(f"  cell {bn}/{an} -> {p}")
                idx += 1

        # 回复位
        urllib.request.urlopen(f"{base}/api/param?all=1&reset=1", timeout=5).read()
        urllib.request.urlopen(f"{base}/api/pause?on=0", timeout=5).read()

        # 拼九宫格（需要 PIL，没有则仅保留单格）
        try:
            from PIL import Image
            cells = []
            for bi in range(3):
                for ai in range(3):
                    cells.append(Image.open(os.path.join(tmp, f"cell_{bi}_{ai}.png")).convert("RGBA"))
            # 统一高度 320
            h = 320
            resized = []
            for im in cells:
                w = int(im.width * h / im.height)
                resized.append(im.resize((w,h), Image.LANCZOS))
            # 3 列
            col_w = max(im.width for im in resized[:3])
            # 实际每列宽度可能略不同，按最大对齐留白
            W = col_w*3 + 20
            H = h*3 + 50
            out = Image.new("RGBA",(W,H),(255,255,255,255))
            from PIL import ImageDraw
            draw = ImageDraw.Draw(out)
            labels = []
            for bi,(bn,_) in enumerate(blinks):
                for ai,(an,_) in enumerate(angles):
                    labels.append(f"{bn}/{an}")
            for r in range(3):
                for c in range(3):
                    idx = r*3+c
                    x = c*(col_w+5)+5
                    y = r*(h+10)+30
                    # 居中贴
                    im = resized[idx]
                    ox = x + (col_w - im.width)//2
                    out.paste(im,(ox,y),im)
                    draw.text((x, y-2), labels[idx], fill=(60,60,60,255))
            out.save(args.out)
            print(f"九宫格已产出 {args.out} {out.size}")
        except ImportError:
            print("  PIL 不可用，单格已落 /tmp/audit_frames_nine/，九宫格跳过", file=sys.stderr)
            return 0

        # 再补 3 张 debug 单态大图
        for dbg in ["wireframe","bones","hitbox"]:
            fetch(os.path.join(outdir, f"audit_debug_{dbg}.png"),
                  f"{base}/api/frame.png?debug={dbg}")
            print(f"  debug {dbg}")

        return 0
    finally:
        if spawned:
            spawned.terminate()
            try: spawned.wait(timeout=3)
            except: spawned.kill()

if __name__ == "__main__":
    sys.exit(main())
