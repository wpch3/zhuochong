#!/usr/bin/env python3
"""Serve only the underpaint editor and three public demo PNGs, not the repository."""
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import argparse
import shutil
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=5211)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='zchibi-underpaint-web-') as temp:
        preview = Path(temp)
        editor = preview / 'tools/underpaint_editor'
        sprites = preview / 'experiments/live2d_chibi_dynamic/sprites'
        editor.mkdir(parents=True); sprites.mkdir(parents=True)
        for name in ('index.html', 'style.css', 'mask.js', 'app.js'):
            shutil.copyfile(ROOT/'tools/underpaint_editor'/name, editor/name)
        for name in ('body.png', 'arm_l.png', 'arm_r.png'):
            shutil.copyfile(ROOT/'experiments/live2d_chibi_dynamic/sprites'/name, sprites/name)
        (preview/'index.html').write_text('<!doctype html><meta charset="utf-8"><meta http-equiv="refresh" content="0;url=/tools/underpaint_editor/"><a href="/tools/underpaint_editor/">打开工作台</a>',encoding='utf-8')
        handler = partial(SimpleHTTPRequestHandler, directory=str(preview))
        server = ThreadingHTTPServer(('0.0.0.0',args.port),handler)
        print(f'Underpaint editor: http://0.0.0.0:{args.port}/ (isolated public demo only)',flush=True)
        server.serve_forever()


if __name__ == '__main__': main()
