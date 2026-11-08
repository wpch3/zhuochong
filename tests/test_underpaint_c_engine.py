#!/usr/bin/env python3
"""Build an isolated candidate and exercise its real C runtime and actions."""
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
import numpy as np
from PIL import Image

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
import build_underpaint_trial


def main():
    (ROOT/'build').mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='underpaint-c-',dir=ROOT/'build') as tmp:
        tmp=Path(tmp)
        patch=os.environ.get('UNDERPAINT_PATCH')
        if not patch:
            arms=[np.asarray(Image.open(build_underpaint_trial.SOURCE/f'sprites/arm_{s}.png').convert('RGBA')) for s in ('l','r')]
            allowed=(arms[0][...,3]==255)|(arms[1][...,3]==255)
            arr=np.zeros((512,480,4),dtype=np.uint8);arr[allowed]=[248,245,250,255]
            patch=tmp/'patch.png';Image.fromarray(arr).save(patch)
        candidate=tmp/'candidate';build_underpaint_trial.build(patch,candidate)
        with socket.socket() as s: s.bind(('127.0.0.1',0));port=s.getsockname()[1]
        proc=subprocess.Popen([sys.executable,str(ROOT/'tools/preview_live2d_chibi.py'),'--dynamic',
            '--dynamic-study',str(candidate),'--preview-root',str(tmp/'preview'),str(port)],
            cwd=ROOT,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
        try:
            for _ in range(100):
                if proc.poll() is not None:raise RuntimeError(proc.stderr.read().decode(errors='replace'))
                try:
                    with urllib.request.urlopen(f'http://127.0.0.1:{port}/api/info.json',timeout=1):break
                except OSError:time.sleep(.1)
            else:raise RuntimeError('C candidate preview did not start')
            subprocess.run([sys.executable,str(ROOT/'tools/capture_dynamic_chibi.py'),'--port',str(port),
                            '--out',str(tmp/'qa')],cwd=ROOT,check=True,timeout=60,stdout=subprocess.DEVNULL)
        finally:
            proc.terminate()
            try:proc.wait(timeout=5)
            except subprocess.TimeoutExpired:proc.kill();proc.wait()
            proc.stderr.close()
    print('补画候选：隔离构建并由真实 C 验证参数、循环和物理通过')


if __name__=='__main__':main()
