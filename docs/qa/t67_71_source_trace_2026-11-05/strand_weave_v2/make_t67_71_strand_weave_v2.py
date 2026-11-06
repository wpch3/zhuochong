#!/usr/bin/env python3
"""Isolated new-design study: flowing lock weave through cuff/hand occlusion.

Hand-authored, separate tapered lock ribbons with nested shading/strand grooves;
no source-image pixel remap, broad single plate, image-generation, or inpainting.
This is a speculative design, never hidden-source recovery or production art.
Requires ImageMagick `convert` and `montage` on PATH.
"""
from __future__ import annotations
import hashlib, json, re, subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
OUT = Path(__file__).resolve().parent
SRC = ROOT / 'characters/xiaoxun/forms/teen/sprites/hair_hood_long@2x.png'
MASK = ROOT / 'docs/qa/t67_71_source_trace_2026-11-05/wip_masked_inpaint_attempt_v2/manual_artifact_polygons_v2.json'
ROIS = {'left': (51, 849, 396, 1368), 'right': (736, 849, 1081, 1368)}
W, H = 1132, 1664

# V2 uses five overlapping lock masses with varied curves and staggered tips.
# They join into a continuous curtain while retaining individual strand rhythm.
LOCKS = [
 ('M 121,250 C 130,305 133,364 140,420 C 146,466 151,494 158,513 C 176,494 173,468 164,425 C 153,363 144,298 146,245 C 138,241 129,244 121,250 Z', '#ada6c0'),
 ('M 140,225 C 145,285 158,354 174,416 C 186,461 195,491 203,516 C 221,490 216,461 205,416 C 190,352 174,283 171,218 C 160,212 149,216 140,225 Z', '#c3bdd4'),
 ('M 160,199 C 165,261 180,328 199,392 C 214,441 224,478 233,510 C 255,483 248,452 234,406 C 215,344 194,266 190,196 C 180,190 169,192 160,199 Z', '#d0cadf'),
 ('M 184,207 C 194,266 212,329 233,388 C 252,438 264,468 275,493 C 296,467 286,435 269,391 C 246,331 221,256 215,203 C 204,198 193,200 184,207 Z', '#bbb5ce'),
 ('M 211,241 C 226,291 248,344 270,393 C 289,432 303,457 316,473 C 334,446 319,416 296,377 C 269,330 244,274 239,237 C 228,233 218,235 211,241 Z', '#c6bfd6'),
]
# Broad, curved interior shade/highlight ribbons create volume without a straight
# central crease. Several fine contour strokes echo the existing painted locks.
DETAILS = [
 ('M 130,266 C 139,330 145,389 151,445', '#77738a', 6.0, .28),
 ('M 137,253 C 145,319 152,383 158,451', '#f4f0f8', 3.0, .66),
 ('M 151,232 C 160,298 175,367 186,432', '#77738a', 7.0, .25),
 ('M 154,226 C 162,292 176,365 190,448', '#f1edf7', 3.2, .62),
 ('M 174,209 C 183,282 203,353 216,431', '#77738a', 7.5, .24),
 ('M 179,211 C 188,283 207,359 224,453', '#f4f0f8', 3.0, .64),
 ('M 201,219 C 213,288 235,354 253,425', '#77738a', 8.0, .23),
 ('M 206,224 C 220,297 241,367 261,445', '#f1edf7', 3.0, .60),
 ('M 230,257 C 247,317 273,379 293,435', '#77738a', 7.0, .24),
 ('M 235,258 C 252,321 278,388 301,451', '#f4f0f8', 2.8, .62),
 ('M 166,270 C 173,332 190,400 199,462', '#817b92', 1.5, .50),
 ('M 193,238 C 205,310 226,383 239,463', '#817b92', 1.5, .48),
 ('M 220,271 C 236,331 258,396 277,461', '#817b92', 1.5, .48),
]

def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

def run(*args: str) -> None:
    subprocess.run(args, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

def local_art(path: Path) -> None:
    def doubled(d: str) -> str:
        return re.sub(r'-?\d+(?:\.\d+)?', lambda m: str(float(m.group(0))*2).rstrip('0').rstrip('.'), d)
    def rgba(hexcolor: str, alpha: float) -> str:
        h=hexcolor.lstrip('#')
        return f'rgba({int(h[0:2],16)},{int(h[2:4],16)},{int(h[4:6],16)},{alpha})'
    hi = path.with_name('.local_hi.png')
    run('convert', '-size', '690x1038', 'xc:none', str(hi))
    # Composite six individually shaded ribbons at 2x resolution for clean edges.
    for i,(d,color) in enumerate(LOCKS):
        layer=path.with_name(f'.lock_{i}.png')
        run('convert','-size','690x1038','xc:none','-fill',color,'-stroke',rgba('#777489',.58),'-strokewidth','2.0','-draw',f"path '{doubled(d)}'",str(layer))
        nxt=path.with_name('.local_next.png')
        run('convert',str(hi),str(layer),'-compose','Over','-composite',str(nxt))
        hi.unlink();layer.unlink();nxt.rename(hi)
    # Fine grooves use a second layer and intentionally avoid a single central seam.
    lines=path.with_name('.lines_hi.png')
    run('convert','-size','690x1038','xc:none',str(lines))
    for i,(d,color,width,opacity) in enumerate(DETAILS):
        layer=path.with_name(f'.groove_{i}.png')
        sw=str(width*2)
        run('convert','-size','690x1038','xc:none','-fill','none','-stroke',rgba(color,opacity),'-strokewidth',sw,'-draw',f"path '{doubled(d)}'",str(layer))
        nxt=path.with_name('.lines_next.png')
        run('convert',str(lines),str(layer),'-compose','Over','-composite',str(nxt))
        lines.unlink();layer.unlink();nxt.rename(lines)
    nxt=path.with_name('.art_hi.png')
    run('convert',str(hi),str(lines),'-compose','Over','-composite',str(nxt))
    hi.unlink();lines.unlink()
    run('convert',str(nxt),'-filter','Lanczos','-resize','345x519!',str(path))
    nxt.unlink()

def object_mask(mask_doc: dict, output: Path) -> None:
    draw = []
    for side, (x0, y0, _, _) in ROIS.items():
        for poly in mask_doc['polygons'][side]:
            pts = ' '.join(f'{x0+x},{y0+y}' for x, y in poly)
            draw.append(f'polygon {pts}')
    run('convert', '-size', f'{W}x{H}', 'xc:black', '-fill', 'white', '-draw', ' '.join(draw), str(output))

def checker_crop(img: Path, box: tuple[int,int,int,int], out: Path) -> None:
    x0,y0,x1,y1=box;w=x1-x0;h=y1-y0
    crop=OUT/'.tmp_crop.png'; bg=OUT/'.tmp_bg.png'
    run('convert', str(img), '-crop', f'{w}x{h}+{x0}+{y0}', '+repage', str(crop))
    run('convert', '-size', f'{w}x{h}', 'pattern:checkerboard', str(bg))
    run('convert', str(bg), str(crop), '-compose', 'Over', '-composite', str(out))
    crop.unlink();bg.unlink()

def main() -> None:
    mask_doc = json.loads(MASK.read_text())
    local = OUT/'t67_71_strand_weave_v2_left_local.png'
    local_art(local)
    right_local = OUT/'t67_71_strand_weave_v2_right_local.png'
    run('convert', str(local), '-flop', str(right_local))
    under = OUT/'t67_71_strand_weave_v2_underlay.png'
    run('convert', '-size', f'{W}x{H}', 'xc:none', str(local), '-geometry', '+51+849', '-compose', 'Over', '-composite', str(under))
    run('convert', str(under), str(right_local), '-geometry', '+736+849', '-compose', 'Over', '-composite', str(under))

    objects = OUT/'t67_71_strand_weave_v2_object_clear_mask.png'
    object_mask(mask_doc, objects)
    invmask = OUT/'t67_71_strand_weave_v2_keep_mask.png'
    run('convert', str(objects), '-negate', str(invmask))
    source_alpha = OUT/'.source_alpha.png'
    run('convert', str(SRC), '-alpha', 'extract', str(source_alpha))
    clean_alpha = OUT/'.clean_alpha.png'
    run('convert', str(source_alpha), str(invmask), '-compose', 'Multiply', '-composite', str(clean_alpha))
    clean = OUT/'t67_71_strand_weave_v2_clean_front.png'
    run('convert', str(SRC), str(clean_alpha), '-compose', 'CopyOpacity', '-composite', str(clean))
    comp = OUT/'t67_71_strand_weave_v2_composite.png'
    run('convert', str(under), str(clean), '-compose', 'Over', '-composite', str(comp))
    fg_alpha = OUT/'.foreground_alpha.png'
    run('convert', str(source_alpha), str(objects), '-compose', 'Multiply', '-composite', str(fg_alpha))
    fg = OUT/'t67_71_strand_weave_v2_registration_foreground.png'
    run('convert', str(SRC), str(fg_alpha), '-compose', 'CopyOpacity', '-composite', str(fg))
    static = OUT/'t67_71_strand_weave_v2_static_mock.png'
    run('convert', str(comp), str(fg), '-compose', 'Over', '-composite', str(static))
    source_alpha.unlink();clean_alpha.unlink();fg_alpha.unlink()

    panels={}
    for side,box in ROIS.items():
        for kind,img in [('source',SRC),('underlay',under),('composite',comp),('static_mock',static)]:
            p=OUT/f't67_71_strand_weave_v2_{side}_{kind}.png'
            checker_crop(img,box,p);panels[(side,kind)]=p
            if kind in ('composite','static_mock'):
                zoom=OUT/f't67_71_strand_weave_v2_{side}_{kind}_3x.png'
                run('convert',str(p),'-filter','point','-resize','300%',str(zoom));panels[(side,kind+'_3x')]=zoom
    args=['montage']
    for side in ('left','right'):
        for kind in ('source','underlay','composite','static_mock'):
            args += ['-label',side.upper()+' / '+kind.replace('_',' ').upper(),str(panels[(side,kind)])]
    board=OUT/'t67_71_strand_weave_v2_review.png'
    args += ['-tile','4x2','-geometry','345x519+12+24','-background','#1b1e25','-fill','#f0f2f6','-font','/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf','-pointsize','15',str(board)]
    run(*args)

    outputs=[local,right_local,under,objects,clean,comp,fg,static,board]+[p for (s,k),p in panels.items() if k.endswith('_3x')]
    metrics={
      'task':'T67.71','status':'isolated speculative new-design WIP; not accepted; not hidden source truth; not production',
      'design_method':'hand-authored cohesive curtain of five overlapping, individually shaded tapered locks with nested curved volume bands and fine flow grooves; no source-image pixel remap, no single flat plate, no image-generation or inpainting',
      'reference':{'path':str(SRC.relative_to(ROOT)),'sha256':sha(SRC),'size':[W,H],'use':'visible silhouette/color/line-flow reference only; not proof of occluded topology'},
      'cleanup_mask':{'path':str(MASK.relative_to(ROOT)),'sha256':sha(MASK),'warning':'visible cuff/hand cleanup ROI only; overlaps some legal hair and is not a hair silhouette'},
      'manual_new_art_local_bounds':[126,191,313,519], 'c_validation':False,'production_changed':False,
      'outputs':{p.name:{'sha256':sha(p),'bytes':p.stat().st_size} for p in outputs},
      'limitations':['Ribbon topology and overlap are a design hypothesis; hidden strand order/coverage remain unknown.','Static foreground is a registered duplicate from the flattened sprite, not an actual C arm/cuff.','Must pass isolated local human review and user confirmation before real C action/transition testing; production requires separate approval.']}
    (OUT/'t67_71_strand_weave_v2_metrics.json').write_text(json.dumps(metrics,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(metrics,ensure_ascii=False,indent=2))

if __name__=='__main__': main()
