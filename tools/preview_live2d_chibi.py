#!/usr/bin/env python3
"""Preview the experimental Chibi C rig without touching either production form."""
from pathlib import Path
import argparse
import json
import os
import shutil

ROOT = Path(__file__).resolve().parents[1]


def link(source, target):
    if not target.exists() and not target.is_symlink():
        target.symlink_to(source, target_is_directory=source.is_dir())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('port', nargs='?', default=None)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--human', action='store_true', help='Use the independent no-animal-feature study')
    mode.add_argument('--blackline', action='store_true', help='Use the independent black-outline human study')
    mode.add_argument('--clean', action='store_true', help='Use the isolated black-outline seam cleanup')
    mode.add_argument('--seam', action='store_true', help='Use the reviewed seam cleanup study')
    args = parser.parse_args()
    human = args.human or args.blackline or args.clean or args.seam
    if args.seam:
        preview = ROOT / 'build/human-seam-preview'
        study = ROOT / 'experiments/live2d_chibi_human_blackline_seam'
        form = 'human_seam_study'
    elif args.clean:
        preview = ROOT / 'build/human-clean-preview'
        study = ROOT / 'experiments/live2d_chibi_human_blackline_clean'
        form = 'human_clean_study'
    elif args.blackline:
        preview = ROOT / 'build/human-blackline-preview'
        study = ROOT / 'experiments/live2d_chibi_human_blackline'
        form = 'human_blackline_study'
    elif human:
        preview = ROOT / 'build/human-chibi-preview'
        study = ROOT / 'experiments/live2d_chibi_human_short'
        form = 'human_study'
    else:
        preview = ROOT / 'build/live2d-chibi-preview'
        study = ROOT / 'experiments/live2d_chibi_short'
        form = 'live2d_study'
    if not (study / 'rig.json').exists():
        raise SystemExit('Build the selected study first')
    preview.mkdir(parents=True, exist_ok=True)
    shutil.copytree(ROOT / 'config', preview / 'config', dirs_exist_ok=True)
    pet = preview / 'config/pet.json'
    text = pet.read_text(encoding='utf-8')
    if '"form": "teen"' not in text:
        raise SystemExit('Default form changed; update isolated preview setup')
    pet.write_text(text.replace('"form": "teen"', '"form": "' + form + '"', 1), encoding='utf-8')
    link(ROOT / 'schemas', preview / 'schemas')
    web = preview / 'web-study'
    shutil.copytree(ROOT / 'web', web, dirs_exist_ok=True)
    layout_path = web / 'layout.json'
    layout = json.loads(layout_path.read_text(encoding='utf-8'))
    layout['title'] = ('小寻 · 黑描边发梢清理试装' if args.seam else
                       '小寻 · 黑描边清边试装' if args.clean else
                       '小寻 · 无兽特征黑描边试装' if args.blackline else
                       '小寻 · 无兽特征 Chibi 试装' if human else '小寻 · Live2D 风格 Chibi 试装')
    hint = ('独立无兽特征试装：头与眼口分层；手臂和身体尚未独立拆分。' if human else
            '隔离试装：头、猫耳、尾巴和眼口分层；手臂和身体尚未独立拆分。')
    description = ('实验模型：头与眼口独立；无猫耳、猫尾。手臂仍包含在身体中，暂未绑定完整网格与物理。' if human else
                   '实验模型：头、猫耳、尾巴、眼口独立；手臂仍包含在身体中，暂未绑定完整网格与物理。')
    layout['regions'] = {
        'topbar': ['statuschips'],
        'stage': [{'id': 'stage', 'options': {'buttons': [], 'hint': hint}}],
        'side': [{'id': 'face_study', 'options': {'title': '表情控制', 'description': description}}, 'actions'],
        'footer': ['statusbar'],
    }
    layout_path.write_text(json.dumps(layout, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    html = web / 'index.html'
    html.write_text(html.read_text(encoding='utf-8').replace('桌面伴侣 · 基础软件（沙箱预览）', layout['title']), encoding='utf-8')
    char = preview / 'characters/xiaoxun'
    char.mkdir(parents=True, exist_ok=True)
    for src in (ROOT / 'characters/xiaoxun').iterdir():
        if src.name not in ('forms', 'forms.json'):
            link(src, char / src.name)
    forms = char / 'forms'
    forms.mkdir(exist_ok=True)
    link(study, forms / form)
    exe = ROOT / 'build/zhuochong_preview'
    if not exe.exists():
        raise SystemExit('Run make build/zhuochong_preview first')
    port = args.port or ('5207' if args.seam else '5206' if args.clean else '5205' if args.blackline else '5203' if human else '5202')
    os.execv(str(exe), [str(exe), '--root', str(preview), '--web', str(web),
                        '--port', port, '--bind', '0.0.0.0'])


if __name__ == '__main__':
    main()
