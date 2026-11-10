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

# A new flowing cascade composition: S-curved lock masses overlap from roots
# tucked into visible side hair and separate into uneven ends below the cuff.
LOCKS = [
 ('M 124,181 C 134,233 126,284 135,337 C 144,393 145,454 158,500 C 164,516 172,524 181,520 C 196,494 181,462 171,423 C 157,371 150,320 154,272 C 157,226 153,187 146,158 C 138,160 130,169 124,181 Z', '#aaa4bf'),
 ('M 143,137 C 154,191 169,242 169,294 C 170,352 183,409 201,463 C 211,493 222,513 233,520 C 252,496 238,463 224,421 C 206,368 191,320 190,270 C 189,220 179,164 169,126 C 159,125 150,130 143,137 Z', '#c1bbd2'),
 ('M 163,128 C 177,177 194,223 198,275 C 202,326 221,376 241,425 C 257,464 269,487 281,495 C 300,467 281,435 261,397 C 237,351 218,304 215,256 C 211,202 199,149 188,119 C 179,118 170,122 163,128 Z', '#d1cbdf'),
 ('M 190,145 C 207,190 229,232 239,278 C 250,328 272,370 288,405 C 305,434 320,454 329,460 C 340,433 322,405 301,372 C 275,328 256,287 244,238 C 232,193 215,151 205,133 C 199,135 194,139 190,145 Z', '#bdb7cf'),
 ('M 218,206 C 234,242 250,275 265,310 C 280,348 300,380 317,408 C 330,430 337,444 340,451 C 346,424 330,397 312,371 C 289,338 269,302 255,266 C 243,232 230,199 224,186 C 220,190 218,198 218,206 Z', '#c7c1d7'),
]
# Wavy, off-center volume bands; each follows the lock's S-flow instead of a
# straight central seam. Highlights and shadows vary in width and spacing.
DETAILS = [
 ('M 132,190 C 140,252 135,308 146,366 C 154,414 159,463 171,494', '#77738a', 6.0, .24),
 ('M 139,178 C 147,240 143,301 154,361 C 162,416 167,461 177,493', '#f4f0f8', 3.0, .62),
 ('M 155,146 C 165,205 179,253 181,309 C 184,364 198,416 215,468', '#77738a', 7.0, .23),
 ('M 161,145 C 172,205 185,259 187,311 C 190,371 205,425 222,474', '#f4f0f8', 3.2, .62),
 ('M 176,139 C 190,194 207,243 211,295 C 216,346 236,397 257,454', '#77738a', 8.0, .22),
 ('M 184,138 C 198,195 214,246 220,297 C 225,354 245,409 267,462', '#f4f0f8', 3.0, .62),
 ('M 203,157 C 222,204 242,248 254,294 C 268,342 292,387 315,435', '#77738a', 7.5, .22),
 ('M 210,160 C 229,211 249,254 263,302 C 277,351 301,397 324,444', '#f4f0f8', 3.0, .60),
 ('M 234,215 C 254,250 278,288 294,330 C 307,362 324,394 338,421', '#77738a', 7.0, .22),
 ('M 241,215 C 262,255 286,294 303,337 C 317,374 331,406 342,435', '#f4f0f8', 2.8, .60),
 ('M 169,188 C 177,242 190,285 193,335 C 197,389 213,437 229,482', '#817b92', 1.5, .46),
 ('M 198,171 C 214,220 232,265 241,314 C 251,363 274,407 294,455', '#817b92', 1.5, .46),
 ('M 227,226 C 246,264 266,303 283,346 C 301,389 323,423 345,452', '#817b92', 1.5, .44),
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
    local = OUT/'t67_71_ribbon_cascade_v1_left_local.png'
    local_art(local)
    right_local = OUT/'t67_71_ribbon_cascade_v1_right_local.png'
    run('convert', str(local), '-flop', str(right_local))
    under = OUT/'t67_71_ribbon_cascade_v1_underlay.png'
    run('convert', '-size', f'{W}x{H}', 'xc:none', str(local), '-geometry', '+51+849', '-compose', 'Over', '-composite', str(under))
    run('convert', str(under), str(right_local), '-geometry', '+736+849', '-compose', 'Over', '-composite', str(under))

    objects = OUT/'t67_71_ribbon_cascade_v1_object_clear_mask.png'
    object_mask(mask_doc, objects)
    invmask = OUT/'t67_71_ribbon_cascade_v1_keep_mask.png'
    run('convert', str(objects), '-negate', str(invmask))
    source_alpha = OUT/'.source_alpha.png'
    run('convert', str(SRC), '-alpha', 'extract', str(source_alpha))
    clean_alpha = OUT/'.clean_alpha.png'
    run('convert', str(source_alpha), str(invmask), '-compose', 'Multiply', '-composite', str(clean_alpha))
    clean = OUT/'t67_71_ribbon_cascade_v1_clean_front.png'
    run('convert', str(SRC), str(clean_alpha), '-compose', 'CopyOpacity', '-composite', str(clean))
    comp = OUT/'t67_71_ribbon_cascade_v1_composite.png'
    run('convert', str(under), str(clean), '-compose', 'Over', '-composite', str(comp))
    fg_alpha = OUT/'.foreground_alpha.png'
    run('convert', str(source_alpha), str(objects), '-compose', 'Multiply', '-composite', str(fg_alpha))
    fg = OUT/'t67_71_ribbon_cascade_v1_registration_foreground.png'
    run('convert', str(SRC), str(fg_alpha), '-compose', 'CopyOpacity', '-composite', str(fg))
    static = OUT/'t67_71_ribbon_cascade_v1_static_mock.png'
    run('convert', str(comp), str(fg), '-compose', 'Over', '-composite', str(static))
    source_alpha.unlink();clean_alpha.unlink();fg_alpha.unlink()

    panels={}
    for side,box in ROIS.items():
        for kind,img in [('source',SRC),('underlay',under),('composite',comp),('static_mock',static)]:
            p=OUT/f't67_71_ribbon_cascade_v1_{side}_{kind}.png'
            checker_crop(img,box,p);panels[(side,kind)]=p
            if kind in ('composite','static_mock'):
                zoom=OUT/f't67_71_ribbon_cascade_v1_{side}_{kind}_3x.png'
                run('convert',str(p),'-filter','point','-resize','300%',str(zoom));panels[(side,kind+'_3x')]=zoom
    args=['montage']
    for side in ('left','right'):
        for kind in ('source','underlay','composite','static_mock'):
            args += ['-label',side.upper()+' / '+kind.replace('_',' ').upper(),str(panels[(side,kind)])]
    board=OUT/'t67_71_ribbon_cascade_v1_review.png'
    args += ['-tile','4x2','-geometry','345x519+12+24','-background','#1b1e25','-fill','#f0f2f6','-font','/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf','-pointsize','15',str(board)]
    run(*args)

    outputs=[local,right_local,under,objects,clean,comp,fg,static,board]+[p for (s,k),p in panels.items() if k.endswith('_3x')]
    metrics={
      'task':'T67.71','status':'isolated speculative new-design WIP; not accepted; not hidden source truth; not production',
      'design_method':'new S-flow cascade: five overlapping, curved lock volumes with hand-authored asymmetrical highlight/shadow ribbons and staggered ends; no source-image pixel remap, no single broad plate, no image-generation or inpainting',
      'reference':{'path':str(SRC.relative_to(ROOT)),'sha256':sha(SRC),'size':[W,H],'use':'visible silhouette/color/line-flow reference only; not proof of occluded topology'},
      'cleanup_mask':{'path':str(MASK.relative_to(ROOT)),'sha256':sha(MASK),'warning':'visible cuff/hand cleanup ROI only; overlaps some legal hair and is not a hair silhouette'},
      'manual_new_art_local_bounds':[120,118,342,520], 'c_validation':False,'production_changed':False,
      'outputs':{p.name:{'sha256':sha(p),'bytes':p.stat().st_size} for p in outputs},
      'limitations':['Ribbon topology and overlap are a design hypothesis; hidden strand order/coverage remain unknown.','Static foreground is a registered duplicate from the flattened sprite, not an actual C arm/cuff.','Must pass isolated local human review and user confirmation before real C action/transition testing; production requires separate approval.']}
    (OUT/'t67_71_ribbon_cascade_v1_metrics.json').write_text(json.dumps(metrics,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(metrics,ensure_ascii=False,indent=2))

if __name__=='__main__': main()
