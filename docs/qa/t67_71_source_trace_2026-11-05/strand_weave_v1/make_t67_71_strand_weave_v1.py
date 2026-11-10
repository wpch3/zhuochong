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

# The design is a fan of six separately shaded lock ribbons, not a single sheet.
# These hand-authored paths fit the visible hood-up long-hair downward flow.
LOCKS = [
 ('M 126,247 C 129,297 137,353 142,404 C 147,454 149,492 151,511 C 162,488 162,465 157,426 C 151,372 142,307 144,246 C 138,241 132,242 126,247 Z', '#aaa3bd'),
 ('M 143,205 C 143,269 151,333 165,397 C 176,447 179,482 184,519 C 202,492 200,462 191,414 C 178,346 166,268 164,202 C 157,198 149,200 143,205 Z', '#c5bfd5'),
 ('M 163,191 C 164,256 177,326 191,391 C 203,442 208,477 213,510 C 231,482 225,450 215,403 C 200,335 185,260 184,192 C 177,188 169,188 163,191 Z', '#d0cbdf'),
 ('M 184,211 C 190,271 205,334 222,393 C 238,445 246,474 252,495 C 267,470 259,438 246,396 C 226,333 209,267 204,211 C 197,207 190,208 184,211 Z', '#bbb5ce'),
 ('M 207,245 C 217,299 236,356 254,405 C 270,447 280,468 287,480 C 299,454 289,426 274,388 C 252,334 232,278 228,244 C 220,240 213,241 207,245 Z', '#c8c2d7'),
 ('M 233,279 C 245,323 264,367 281,405 C 296,438 305,451 313,461 C 322,437 309,410 292,377 C 271,337 252,298 251,274 C 244,273 238,275 233,279 Z', '#b3adc6'),
]
DETAILS = [
 ('M 138,258 C 141,327 149,394 153,463', '#f1edf6', 2.4, .72),
 ('M 151,220 C 155,297 171,376 178,473', '#77738a', 1.5, .55),
 ('M 162,199 C 168,273 185,354 198,458', '#f2eef7', 2.2, .65),
 ('M 174,210 C 179,292 196,368 205,467', '#79758d', 1.5, .50),
 ('M 185,220 C 193,290 211,365 224,457', '#f4f0f8', 2.0, .62),
 ('M 198,230 C 204,301 226,379 241,456', '#78748c', 1.6, .50),
 ('M 210,252 C 224,318 246,382 262,446', '#f2eef7', 2.1, .65),
 ('M 222,260 C 234,322 256,387 273,439', '#77738a', 1.5, .48),
 ('M 243,289 C 256,344 278,405 294,435', '#f0ecf5', 2.0, .62),
 ('M 255,295 C 271,348 291,404 305,430', '#77738a', 1.5, .47),
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
    local = OUT/'t67_71_strand_weave_v1_left_local.png'
    local_art(local)
    right_local = OUT/'t67_71_strand_weave_v1_right_local.png'
    run('convert', str(local), '-flop', str(right_local))
    under = OUT/'t67_71_strand_weave_v1_underlay.png'
    run('convert', '-size', f'{W}x{H}', 'xc:none', str(local), '-geometry', '+51+849', '-compose', 'Over', '-composite', str(under))
    run('convert', str(under), str(right_local), '-geometry', '+736+849', '-compose', 'Over', '-composite', str(under))

    objects = OUT/'t67_71_strand_weave_v1_object_clear_mask.png'
    object_mask(mask_doc, objects)
    invmask = OUT/'t67_71_strand_weave_v1_keep_mask.png'
    run('convert', str(objects), '-negate', str(invmask))
    source_alpha = OUT/'.source_alpha.png'
    run('convert', str(SRC), '-alpha', 'extract', str(source_alpha))
    clean_alpha = OUT/'.clean_alpha.png'
    run('convert', str(source_alpha), str(invmask), '-compose', 'Multiply', '-composite', str(clean_alpha))
    clean = OUT/'t67_71_strand_weave_v1_clean_front.png'
    run('convert', str(SRC), str(clean_alpha), '-compose', 'CopyOpacity', '-composite', str(clean))
    comp = OUT/'t67_71_strand_weave_v1_composite.png'
    run('convert', str(under), str(clean), '-compose', 'Over', '-composite', str(comp))
    fg_alpha = OUT/'.foreground_alpha.png'
    run('convert', str(source_alpha), str(objects), '-compose', 'Multiply', '-composite', str(fg_alpha))
    fg = OUT/'t67_71_strand_weave_v1_registration_foreground.png'
    run('convert', str(SRC), str(fg_alpha), '-compose', 'CopyOpacity', '-composite', str(fg))
    static = OUT/'t67_71_strand_weave_v1_static_mock.png'
    run('convert', str(comp), str(fg), '-compose', 'Over', '-composite', str(static))
    source_alpha.unlink();clean_alpha.unlink();fg_alpha.unlink()

    panels={}
    for side,box in ROIS.items():
        for kind,img in [('source',SRC),('underlay',under),('composite',comp),('static_mock',static)]:
            p=OUT/f't67_71_strand_weave_v1_{side}_{kind}.png'
            checker_crop(img,box,p);panels[(side,kind)]=p
            if kind in ('composite','static_mock'):
                zoom=OUT/f't67_71_strand_weave_v1_{side}_{kind}_3x.png'
                run('convert',str(p),'-filter','point','-resize','300%',str(zoom));panels[(side,kind+'_3x')]=zoom
    args=['montage']
    for side in ('left','right'):
        for kind in ('source','underlay','composite','static_mock'):
            args += ['-label',side.upper()+' / '+kind.replace('_',' ').upper(),str(panels[(side,kind)])]
    board=OUT/'t67_71_strand_weave_v1_review.png'
    args += ['-tile','4x2','-geometry','345x519+12+24','-background','#1b1e25','-fill','#f0f2f6','-font','/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf','-pointsize','15',str(board)]
    run(*args)

    outputs=[local,right_local,under,objects,clean,comp,fg,static,board]+[p for (s,k),p in panels.items() if k.endswith('_3x')]
    metrics={
      'task':'T67.71','status':'isolated speculative new-design WIP; not accepted; not hidden source truth; not production',
      'design_method':'hand-authored fan of six separate tapered lock ribbons with nested shading and fine flow grooves; no source-image pixel remap, no broad single plate, no image-generation or inpainting',
      'reference':{'path':str(SRC.relative_to(ROOT)),'sha256':sha(SRC),'size':[W,H],'use':'visible silhouette/color/line-flow reference only; not proof of occluded topology'},
      'cleanup_mask':{'path':str(MASK.relative_to(ROOT)),'sha256':sha(MASK),'warning':'visible cuff/hand cleanup ROI only; overlaps some legal hair and is not a hair silhouette'},
      'manual_new_art_local_bounds':[126,191,313,519], 'c_validation':False,'production_changed':False,
      'outputs':{p.name:{'sha256':sha(p),'bytes':p.stat().st_size} for p in outputs},
      'limitations':['Ribbon topology and overlap are a design hypothesis; hidden strand order/coverage remain unknown.','Static foreground is a registered duplicate from the flattened sprite, not an actual C arm/cuff.','Must pass isolated local human review and user confirmation before real C action/transition testing; production requires separate approval.']}
    (OUT/'t67_71_strand_weave_v1_metrics.json').write_text(json.dumps(metrics,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(metrics,ensure_ascii=False,indent=2))

if __name__=='__main__': main()
