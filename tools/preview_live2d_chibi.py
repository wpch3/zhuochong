#!/usr/bin/env python3
"""Preview the experimental Chibi C rig without touching either production form."""
from pathlib import Path
import json
import os
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
PREVIEW = ROOT / 'build/live2d-chibi-preview'
STUDY = ROOT / 'experiments/live2d_chibi_short'


def link(source, target):
    if not target.exists() and not target.is_symlink():
        target.symlink_to(source, target_is_directory=source.is_dir())


def main():
    if not (STUDY / 'rig.json').exists():
        raise SystemExit('Run tools/build_live2d_chibi_study.py first')
    PREVIEW.mkdir(parents=True, exist_ok=True)
    shutil.copytree(ROOT / 'config', PREVIEW / 'config', dirs_exist_ok=True)
    pet = PREVIEW / 'config/pet.json'
    text = pet.read_text(encoding='utf-8')
    if '"form": "teen"' not in text:
        raise SystemExit('Default form changed; update isolated preview setup')
    pet.write_text(text.replace('"form": "teen"', '"form": "live2d_study"', 1), encoding='utf-8')
    link(ROOT / 'schemas', PREVIEW / 'schemas')
    web = PREVIEW / 'web-study'
    shutil.copytree(ROOT / 'web', web, dirs_exist_ok=True)
    layout_path = web / 'layout.json'
    layout = json.loads(layout_path.read_text(encoding='utf-8'))
    layout['title'] = '小寻 · Live2D 风格 Chibi 试装'
    layout['regions'] = {
        'topbar': ['statuschips'],
        'stage': [{'id': 'stage', 'options': {'buttons': [], 'hint': '隔离试装：头、猫耳、尾巴和眼口分层；手臂和身体尚未独立拆分。'}}],
        'side': [{'id': 'face_study', 'options': {'title': '表情控制', 'description': '实验模型：头、猫耳、尾巴、眼口独立；手臂仍包含在身体中，暂未绑定完整网格与物理。'}}, 'actions'],
        'footer': ['statusbar'],
    }
    layout_path.write_text(json.dumps(layout, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    html = web / 'index.html'
    html.write_text(html.read_text(encoding='utf-8').replace('桌面伴侣 · 基础软件（沙箱预览）', 'Live2D 风格 Chibi · 隔离试装'), encoding='utf-8')
    char = PREVIEW / 'characters/xiaoxun'
    char.mkdir(parents=True, exist_ok=True)
    for src in (ROOT / 'characters/xiaoxun').iterdir():
        if src.name not in ('forms', 'forms.json'):
            link(src, char / src.name)
    forms = char / 'forms'
    forms.mkdir(exist_ok=True)
    link(STUDY, forms / 'live2d_study')
    exe = ROOT / 'build/zhuochong_preview'
    if not exe.exists():
        raise SystemExit('Run make build/zhuochong_preview first')
    port = sys.argv[1] if len(sys.argv) > 1 else '5202'
    os.execv(str(exe), [str(exe), '--root', str(PREVIEW), '--web', str(web),
                        '--port', port, '--bind', '0.0.0.0'])


if __name__ == '__main__':
    main()
