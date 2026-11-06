#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""TLS 闸门：起一个自签名的 TLS 服务，让 build/tls_probe 去连。

为什么要有这道闸（G54 / T61.9）：
  "能连上 https" 这件事太容易做到了 —— 把证书校验关掉就行。
  而关掉校验的 https 在中间人面前和明文没有任何区别，
  偏偏这条链路上跑的是用户的 API key 和聊天内容。
  所以这道闸的重点**不是"能连通"，而是"该拒的必须拒"**：
  自签名要拒、域名对不上要拒，而且拒的时候一个字节都不许发出去。

整个过程不碰外网：证书现生成、服务端在本机、跑完就删。

用法：
  python3 tools/check_tls.py            # 自己准备环境并跑
  make tls                              # 同上（会先编 build/tls_probe）
"""

import json
import os
import shutil
import socket
import ssl
import subprocess
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROBE = os.path.join(ROOT, "build", "tls_probe")


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def make_cert(d):
    """现生成一张 CN=localhost 的自签名证书。

    ★ 不把证书和私钥提交进仓库：
      一来仓库里躺着私钥会被各种安全扫描判红（而且那是对的），
      二来证书会过期，到时候 CI 会在一个和代码完全无关的地方变红。
    """
    cert = os.path.join(d, "cert.pem")
    key = os.path.join(d, "key.pem")
    r = subprocess.run(
        ["openssl", "req", "-x509", "-newkey", "rsa:2048",
         "-keyout", key, "-out", cert, "-days", "2", "-nodes",
         "-subj", "/CN=localhost",
         "-addext", "subjectAltName=DNS:localhost"],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    if r.returncode != 0:
        raise RuntimeError("openssl 生成证书失败：\n" + r.stdout.decode("utf-8", "replace"))
    return cert, key


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):
        pass

    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0))
        try:
            req = json.loads(self.rfile.read(n).decode("utf-8"))
        except Exception:                                # noqa: BLE001
            req = {}
        sysmsg = usermsg = ""
        for m in req.get("messages", []):
            if m.get("role") == "system":
                sysmsg = m.get("content", "")
            elif m.get("role") == "user":
                usermsg = m.get("content", "")
        # 把收到的东西回显出来，好证明"真的经 TLS 到达了"而不是本地糊弄
        reply = ("over-TLS|auth=%s|sys=%d字|user=%s|model=%s|stream=%s"
                 % (self.headers.get("Authorization", ""), len(sysmsg),
                    usermsg, req.get("model"), req.get("stream")))
        body = json.dumps({
            "choices": [{"message": {"role": "assistant", "content": reply}}],
            "usage": {"prompt_tokens": 11, "completion_tokens": 22},
        }, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(body)


def main():
    if not os.path.exists(PROBE):
        print("没有 %s —— 先 make build/tls_probe" % PROBE)
        return 2
    if not shutil.which("openssl"):
        print("本机没有 openssl 命令行，没法生成测试证书 —— 这道闸跳过")
        print("（注意：跳过不等于通过。CI 的 ubuntu 镜像自带 openssl。）")
        return 0

    d = tempfile.mkdtemp(prefix="zc_tls_")
    try:
        cert, key = make_cert(d)
        port = free_port()

        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.load_cert_chain(cert, key)
        srv = HTTPServer(("127.0.0.1", port), Handler)
        srv.socket = ctx.wrap_socket(srv.socket, server_side=True)
        th = threading.Thread(target=srv.serve_forever, daemon=True)
        th.start()
        time.sleep(0.3)

        print("TLS 闸门：自签名服务已起在 127.0.0.1:%d" % port)
        print("          证书 %s（现生成，跑完就删）\n" % cert)

        env = dict(os.environ)
        env["ZC_TLS_TMP"] = d
        # 这两个必须由被测程序自己管，父进程先清干净，免得污染判定
        env.pop("ZHUOCHONG_CA_FILE", None)
        env.pop("ZHUOCHONG_SECRET_TLSCLOUD", None)
        r = subprocess.run([PROBE, "https://localhost:%d" % port, cert], env=env)

        srv.shutdown()
        return r.returncode
    finally:
        shutil.rmtree(d, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
