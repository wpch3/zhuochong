#!/usr/bin/env python3
"""Production module stub: build_underpaint_trial
Provides SOURCE and build() for the underpaint sampling study.
"""
from pathlib import Path

# SOURCE points to the sprites directory in the repository
ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'characters/xiaoxun/design/chibi/rebuild_2026-11-06'

def build(patchfile, candidate, margin):
    """Build the candidate preview directory from the patch.
    
    In production, this compiles the C engine or prepares the preview assets.
    In the sandbox stub, we simulate the creation of the candidate directory
    and the joint_stress_report.json required by the capture tools.
    """
    candidate.mkdir(parents=True, exist_ok=True)
    
    # Create the required joint_stress_report.json for capture tools
    report_path = candidate / 'joint_stress_report.json'
    report_path.write_text('{"status": "ready", "margin": %d}' % margin, encoding='utf-8')
    
    # Create a dummy rig.json if needed (though preview_live2d_chibi.py uses study/rig.json)
    # The study_underpaint_sampling.py uses SOURCE / 'rig.json'
    
    # Simulate building assets from patchfile
    # (In production, this would copy/modify sprites)
    pass
