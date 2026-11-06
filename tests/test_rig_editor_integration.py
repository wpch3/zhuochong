#!/usr/bin/env python3
"""Run editor-exported group binding through a temporary real C preview."""
import json
import os
import shutil
import socket
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'experiments/live2d_chibi_human_short'


def main():
    with tempfile.TemporaryDirectory(prefix='zrig-editor-test-') as tmp:
        root = Path(tmp)
        shutil.copytree(ROOT / 'config', root / 'config')
        pet = root / 'config/pet.json'
        text = pet.read_text(encoding='utf-8')
        if '"form": "teen"' not in text:
            raise AssertionError('unexpected default form')
        pet.write_text(text.replace('"form": "teen"', '"form": "editor_test"', 1), encoding='utf-8')
        (root / 'schemas').symlink_to(ROOT / 'schemas', target_is_directory=True)
        char = root / 'characters/xiaoxun'
        char.mkdir(parents=True)
        for path in (ROOT / 'characters/xiaoxun').iterdir():
            if path.name not in ('forms', 'forms.json'):
                (char / path.name).symlink_to(path, target_is_directory=path.is_dir())
        form = char / 'forms/editor_test'
        form.mkdir(parents=True)
        browser_rig = os.environ.get('ZRIG_BROWSER_RIG')
        source = ROOT / 'experiments/live2d_chibi_human_blackline' if browser_rig else SOURCE
        shutil.copytree(source / 'sprites', form / 'sprites')
        if browser_rig:
            shutil.copyfile(browser_rig, form / 'rig.json')
        else:
            subprocess.run(['node', 'tests/test_rig_editor.js', str(form / 'rig.json')], cwd=ROOT, check=True)
        with socket.socket() as s:
            s.bind(('127.0.0.1', 0))
            port = s.getsockname()[1]
        base = f'http://127.0.0.1:{port}'
        proc = subprocess.Popen([str(ROOT / 'build/zhuochong_preview'), '--root', str(root),
                                 '--bind', '127.0.0.1', '--port', str(port)],
                                cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        def get(path):
            with urllib.request.urlopen(base + path, timeout=10) as response:
                return response.read()
        try:
            for _ in range(100):
                if proc.poll() is not None:
                    raise AssertionError('preview exited: ' + proc.stderr.read().decode(errors='replace'))
                try:
                    info = json.loads(get('/api/info.json'))
                    break
                except (OSError, urllib.error.URLError):
                    time.sleep(.1)
            else:
                raise AssertionError('preview startup timeout')
            assert info['form'] == 'editor_test', info
            get('/api/action?id=idle')
            get('/api/pause?on=1')
            get('/api/blink?v=0')
            get('/api/param?id=ParamEditorHead&v=0')
            get('/api/step?n=1')
            a = get('/api/frame.png')
            get('/api/param?id=ParamEditorHead&v=1')
            get('/api/step?n=1')
            b = get('/api/frame.png')
            get('/api/param?id=ParamEditorHead&v=0')
            get('/api/step?n=1')
            restored = get('/api/frame.png')
            assert a.startswith(b'\x89PNG\r\n\x1a\n') and b.startswith(b'\x89PNG\r\n\x1a\n')
            assert a != b, 'editor binding failed to change the rendered frame'
            assert a == restored, 'return to zero must restore the exact original frame'
            get('/api/param?id=ParamEditorMesh&v=0')
            get('/api/step?n=1')
            mesh_neutral = get('/api/frame.png')
            get('/api/param?id=ParamEditorMesh&v=0.5')
            get('/api/step?n=1')
            mesh_mid = get('/api/frame.png')
            get('/api/param?id=ParamEditorMesh&v=1')
            get('/api/step?n=1')
            mesh_deformed = get('/api/frame.png')
            get('/api/param?id=ParamEditorMesh&v=0')
            get('/api/step?n=1')
            mesh_restored = get('/api/frame.png')
            if os.environ.get('ZRIG_QA_DIR'):
                qa_dir = Path(os.environ['ZRIG_QA_DIR'])
                qa_dir.mkdir(parents=True, exist_ok=True)
                (qa_dir / 'keyform_neutral.png').write_bytes(mesh_neutral)
                (qa_dir / 'keyform_max.png').write_bytes(mesh_deformed)
            assert mesh_neutral != mesh_mid and mesh_mid != mesh_deformed, 'keyform intermediate frame must be distinct'
            assert mesh_neutral != mesh_deformed, 'keyform failed to change the rendered frame'
            assert mesh_neutral == mesh_restored, 'keyform must restore exact neutral frame'
            print('编辑器生成 rig：C 引擎参数驱动组与关键形态网格并恢复原帧')
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
            proc.stderr.close()


if __name__ == '__main__':
    main()
