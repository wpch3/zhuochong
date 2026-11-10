#!/usr/bin/env python3
"""Start an isolated C preview and run real-frame/physics checks on it."""
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[1]


def main():
    with tempfile.TemporaryDirectory(prefix='zchibi-engine-') as tmp:
        # A free port is chosen immediately before spawn; another process can
        # theoretically race the bind, in which case this test fails safely.
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0)); port = sock.getsockname()[1]
        cmd = [sys.executable, str(ROOT/'tools/preview_live2d_chibi.py'), '--dynamic',
               '--preview-root', str(Path(tmp)/'preview'), str(port)]
        proc = subprocess.Popen(cmd, cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        try:
            for _ in range(100):
                if proc.poll() is not None:
                    raise RuntimeError('preview exited: ' + proc.stderr.read().decode(errors='replace'))
                try:
                    with urllib.request.urlopen(f'http://127.0.0.1:{port}/api/info.json', timeout=1):
                        break
                except (OSError, urllib.error.URLError):
                    time.sleep(.1)
            else:
                raise RuntimeError('preview did not start')
            subprocess.run([sys.executable, str(ROOT/'tools/capture_dynamic_chibi.py'), '--port', str(port),
                            '--out', str(Path(tmp)/'qa')], cwd=ROOT, check=True, timeout=60)
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill(); proc.wait()
            proc.stderr.close()
    print('独立 C 预览：动态参数、循环、物理和复位测试通过')


if __name__ == '__main__':
    main()
