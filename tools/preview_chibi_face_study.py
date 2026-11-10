#!/usr/bin/env python3
"""Run the C preview with the facial study as an isolated, temporary form.

Build the study first with build_chibi_face_study.py. No production rig is
modified. Preview root and runtime data stay under ignored build/.
"""
from pathlib import Path
import json
import os
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
PREVIEW = ROOT / 'build/chibi-face-preview'
STUDY = ROOT / 'experiments/chibi_face_study'


def link(src, dst):
    if not dst.exists() and not dst.is_symlink():
        dst.symlink_to(src, target_is_directory=src.is_dir())


def main():
    if not (STUDY / 'rig.json').exists():
        raise SystemExit('Run tools/build_chibi_face_study.py first')
    PREVIEW.mkdir(parents=True, exist_ok=True)
    shutil.copytree(ROOT / 'config', PREVIEW / 'config', dirs_exist_ok=True)
    pet = PREVIEW / 'config/pet.json'
    text = pet.read_text(encoding='utf-8')
    old = '"form": "teen"'
    if old not in text:
        raise SystemExit('Default form changed; update isolated preview setup')
    pet.write_text(text.replace(old, '"form": "face_study"', 1), encoding='utf-8')
    link(ROOT / 'schemas', PREVIEW / 'schemas')
    # A separate UI makes the limited scope explicit and avoids presenting
    # unsupported clothing/voice/AI features as part of this test model.
    web = PREVIEW / 'web-study'
    shutil.copytree(ROOT / 'web', web, dirs_exist_ok=True)
    layout_path = web / 'layout.json'
    layout = json.loads(layout_path.read_text(encoding='utf-8'))
    layout['title'] = '小寻 · Q 版面部试作'
    layout['regions'] = {'topbar': ['statuschips'],
                         'stage': [{'id': 'stage', 'options': {'buttons': [], 'hint': '隔离面部试作：眨眼和口型可以测试，身体和头发尚未拆件。'}}],
                         'side': ['face_study', 'actions'], 'footer': ['statusbar']}
    layout_path.write_text(json.dumps(layout, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    html = web / 'index.html'
    html.write_text(html.read_text(encoding='utf-8').replace('桌面伴侣 · 基础软件（沙箱预览）', 'Q 版面部试作 · 非完整模型'), encoding='utf-8')
    char = PREVIEW / 'characters/xiaoxun'
    char.mkdir(parents=True, exist_ok=True)
    for src in (ROOT / 'characters/xiaoxun').iterdir():
        if src.name not in ('forms', 'forms.json'):
            link(src, char / src.name)
    forms = char / 'forms'
    forms.mkdir(exist_ok=True)
    link(STUDY, forms / 'face_study')
    exe = ROOT / 'build/zhuochong_preview'
    if not exe.exists():
        raise SystemExit('Run make build/zhuochong_preview first')
    port = sys.argv[1] if len(sys.argv) > 1 else '5201'
    os.execv(str(exe), [str(exe), '--root', str(PREVIEW), '--web', str(web),
                        '--port', port, '--bind', '0.0.0.0'])


if __name__ == '__main__':
    main()
