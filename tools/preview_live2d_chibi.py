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
    parser.add_argument('--bind', choices=('0.0.0.0', '127.0.0.1'), default='0.0.0.0',
                        help='bind address; use loopback for internal automated tests')
    parser.add_argument('--preview-root', type=Path, help='Isolated preview directory (default: build/<study>-preview)')
    parser.add_argument('--dynamic-study', type=Path, help='Use an isolated dynamic candidate; requires --dynamic and a separate --preview-root')
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--human', action='store_true', help='Use the independent no-animal-feature study')
    mode.add_argument('--blackline', action='store_true', help='Use the independent black-outline human study')
    mode.add_argument('--clean', action='store_true', help='Use the isolated black-outline seam cleanup')
    mode.add_argument('--seam', action='store_true', help='Use the reviewed seam cleanup study')
    mode.add_argument('--dynamic', action='store_true', help='Use the isolated dynamic Chibi study')
    args = parser.parse_args()
    human = args.human or args.blackline or args.clean or args.seam or args.dynamic
    if args.dynamic:
        preview = ROOT / 'build/human-dynamic-preview'
        study = ROOT / 'experiments/live2d_chibi_dynamic'
        form = 'human_dynamic_study'
    elif args.seam:
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
    if args.dynamic_study:
        if not args.dynamic or not args.preview_root:
            raise SystemExit('--dynamic-study requires --dynamic and an isolated --preview-root')
        study = args.dynamic_study.resolve()
        build_root = (ROOT / 'build').resolve()
        exp_root = (ROOT / 'experiments').resolve()
        if not (build_root in study.parents or
                (study.parent == exp_root and study.name.startswith('live2d_chibi_underpaint_'))):
            raise SystemExit('Dynamic candidate must be a build scratch or named underpaint experiment')
        rig_path = study / 'rig.json'
        if not rig_path.is_file() or json.loads(rig_path.read_text(encoding='utf-8')).get('id') != 'xiaoxun_live2d_chibi_underpaint_trial':
            raise SystemExit('Dynamic candidate is not an underpaint trial')
    if not (study / 'rig.json').exists():
        raise SystemExit('Build the selected study first')
    if args.preview_root:
        preview = args.preview_root.resolve()
        root = ROOT.resolve()
        build_root = (ROOT / 'build').resolve()
        if preview == root or (root in preview.parents and build_root not in preview.parents):
            raise SystemExit('Refusing to write a preview into repository sources; use build or a temporary directory')
        if preview == study.resolve() or study.resolve() in preview.parents or preview in study.resolve().parents:
            raise SystemExit('Refusing to use study or its ancestor as preview root')
    underlay_trial = bool(args.dynamic_study and (study / 'underlay_report.json').is_file())
    target = preview / 'characters/xiaoxun/forms' / form
    if target.is_symlink():
        if target.resolve() != study.resolve():
            raise SystemExit('Preview root already points to a different study; choose a fresh --preview-root')
    elif target.exists():
        raise SystemExit('Preview form path is not the expected study symlink; choose a fresh --preview-root')
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
    layout['title'] = ('小寻 · 衣身底稿试验（未验收）' if underlay_trial else
                       '小寻 · 遮挡补画候选（未验收）' if args.dynamic_study else
                       '小寻 · 无兽动态绑定试装' if args.dynamic else
                       '小寻 · 黑描边发梢清理试装' if args.seam else
                       '小寻 · 黑描边清边试装' if args.clean else
                       '小寻 · 无兽特征黑描边试装' if args.blackline else
                       '小寻 · 无兽特征 Chibi 试装' if human else '小寻 · Live2D 风格 Chibi 试装')
    hint = ('独立无兽特征试装：头与眼口分层；手臂和身体尚未独立拆分。' if human else
            '隔离试装：头、猫耳、尾巴和眼口分层；手臂和身体尚未独立拆分。')
    description = ('实验模型：头与眼口独立；无猫耳、猫尾。手臂仍包含在身体中，暂未绑定完整网格与物理。' if human else
                   '实验模型：头、猫耳、尾巴、眼口独立；手臂仍包含在身体中，暂未绑定完整网格与物理。')
    if args.dynamic:
        hint = '独立动态试装：袖手拆分、头部、呼吸、眨眼和嘴型；接缝与隐藏底稿仍需审查。'
        description = '参数由自研 C 引擎计算；袖手是平面切分实验，没有真实肩部遮挡底稿。'
        if args.dynamic_study:
            hint = '隔离补画候选：真实 C 帧，仅供对照；尚未通过视觉验收。'
            description = '透明补画仅限中立袖手遮挡区，不代表拥有完整肩部隐藏画稿。'
            if underlay_trial:
                hint = '独立衣身底稿候选：真实 C 帧，袖手仍仅小幅试动；未通过视觉验收。'
                description = '新绘衣身侧片在原身体分割层下方，缩放中立帧仍有差异；不是完整肩袖原画。'
    layout['regions'] = {
        'topbar': ['statuschips'],
        'stage': [{'id': 'stage', 'options': {'buttons': [], 'hint': hint}}],
        'side': (['dynamic_study'] if args.dynamic else []) +
                [{'id': 'face_study', 'options': {'title': '表情控制', 'description': description}}, 'actions'],
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
    port = args.port or ('5209' if args.dynamic else '5207' if args.seam else '5206' if args.clean else '5205' if args.blackline else '5203' if human else '5202')
    os.execv(str(exe), [str(exe), '--root', str(preview), '--web', str(web),
                        '--port', port, '--bind', args.bind])


if __name__ == '__main__':
    main()
