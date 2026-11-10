#!/usr/bin/env python3
"""真实 C 预览服务：动作 API 与形态切换回归，无第三方 Python 依赖。"""
import json
import socket
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def request(base, path):
    try:
        response = urllib.request.urlopen(base + path, timeout=20)
    except urllib.error.HTTPError as error:
        response = error
    with response:
        data = response.read()
        return response.status, data


def main():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    base = f"http://127.0.0.1:{port}"
    proc = subprocess.Popen([str(ROOT / "build/zhuochong_preview"), "--root", str(ROOT),
                             "--bind", "127.0.0.1", "--port", str(port)],
                            cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(100):
            if proc.poll() is not None:
                raise AssertionError(f"预览服务启动失败: {proc.returncode}")
            try:
                status, body = request(base, "/api/info.json")
                break
            except (OSError, urllib.error.URLError):
                time.sleep(0.1)
        else:
            raise AssertionError("预览服务启动超时")
        assert status == 200 and json.loads(body)["form"] == "teen"
        for path, expected in [("/api/action", 400), ("/api/action?id=", 400),
                               ("/api/action?id=__no_such_action__", 404)]:
            status, body = request(base, path)
            assert status == expected and json.loads(body)["ok"] is False, (path, status, body)
        for form in ("teen", "chibi"):
            status, body = request(base, "/api/form?id=" + form)
            result = json.loads(body)
            assert status == 200 and result["ok"] and result["form"] == form, result
            status, body = request(base, "/api/info.json")
            info = json.loads(body)
            assert info["form"] == form
            for action in ("idle", "sway", "surprised", "wave"):
                assert action == "idle" or action in info["actions"], (form, action)
                status, body = request(base, "/api/action?id=" + action)
                assert status == 200 and json.loads(body)["ok"], (form, action, body)
                status, body = request(base, "/api/info.json")
                assert json.loads(body)["action"] == action, (form, action, body)
            status, body = request(base, "/api/frame.png")
            assert status == 200 and body.startswith(b"\x89PNG\r\n\x1a\n"), form
            print(f"{form}: 模型加载、四个动作及 PNG 帧通过；加载警告 {result['warnings']} 条")
        print("动作 API：空 id 和未知 id 正确报错")
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()


if __name__ == "__main__":
    main()
