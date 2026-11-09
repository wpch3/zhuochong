#!/usr/bin/env python3
"""Launch an isolated, explicitly unapproved teen hidden-art candidate preview."""
import argparse
import json
import os
from pathlib import Path
import shutil

ROOT=Path(__file__).resolve().parents[1]

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('candidate',type=Path,help='build/.../teen from build_hidden_art_studies.py')
    p.add_argument('--preview-root',type=Path,required=True,help='new build/ subdirectory')
    p.add_argument('--port',type=int,default=5214)
    a=p.parse_args();scratch=(ROOT/'build').resolve();candidate=a.candidate.resolve();preview=a.preview_root.resolve()
    if scratch not in candidate.parents or scratch not in preview.parents:
        raise SystemExit('candidate and preview root must be inside build/')
    if preview == candidate or candidate in preview.parents or preview in candidate.parents:
        raise SystemExit('candidate and preview must be separate')
    if a.preview_root.exists() or a.preview_root.is_symlink():raise SystemExit('preview root already exists; use a fresh path')
    if not a.preview_root.parent.is_dir():raise SystemExit('preview parent does not exist')
    if not 1<=a.port<=65535:raise SystemExit('invalid port')
    rig=json.loads((candidate/'rig.json').read_text(encoding='utf-8'))
    if rig.get('id')!='xiaoxun_teen_hidden_art_trial':raise SystemExit('not the teen hidden-art trial')
    exe=ROOT/'build/zhuochong_preview'
    if not exe.is_file():raise SystemExit('run make build/zhuochong_preview first')
    a.preview_root.mkdir()
    try:
        shutil.copytree(ROOT/'config',preview/'config')
        char=preview/'characters/xiaoxun';(char/'forms').mkdir(parents=True)
        # A real copy, not a symlink: ../../motions resolves relative to the rig.
        shutil.copytree(candidate,char/'forms/teen')
        for src in (ROOT/'characters/xiaoxun').iterdir():
            if src.name not in ('forms','forms.json'):
                (char/src.name).symlink_to(src,target_is_directory=src.is_dir())
        (preview/'schemas').symlink_to(ROOT/'schemas',target_is_directory=True)
    except BaseException:
        shutil.rmtree(preview);raise
    print('少女隐藏画稿试验（未验收），独立副本：',preview,flush=True)
    os.execv(str(exe),[str(exe),'--root',str(preview),'--web',str(ROOT/'web'),
                        '--port',str(a.port),'--bind','0.0.0.0'])

if __name__=='__main__':main()
