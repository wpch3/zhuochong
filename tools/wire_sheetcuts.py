# -*- coding: utf-8 -*-
"""把 cut_from_sheets.py 切出来的 7 片接进 attachments.json。**幂等**。

用法（跑之前先 `git checkout -- characters/<角色>/design/attachments.json`，
或者直接重复跑 —— 对已改过的表再跑一遍结果相同）：

    /tmp/imgenv/bin/python tools/wire_sheetcuts.py
    ZC_PYTHON=/tmp/imgenv/bin/python bash tools/rebuild_parts.sh xiaoxun teen

接法刻意选了**最小侵入**的一种：每片就当一张普通的 `source` 图引用，
于是现有的 keyout / recolor_match / @2x 全链路一行都不用改。
几何全部来自 cut_geometry.json（从模板量出来的），没有一个手调常数。
"""
import json, io, collections

GEO = json.load(open('characters/xiaoxun/design/sheets/cut_geometry.json'))
P = 'characters/xiaoxun/design/attachments.json'
d = json.load(open(P, encoding='utf-8'), object_pairs_hook=collections.OrderedDict)

S = GEO['scale_sheet_to_bodyfull']          # 0.889195
U = GEO['head_unit_px']                     # 278.0384
BBOX0 = (257, 27)                           # 底图人物 bbox 左上（模板坐标）
REF = (215.0, 0.0)                          # anchors.points.head_top（body_full 像素）
MARGIN = 0.04                               # make_attach_parts 的 CROP_MARGIN

def place(px):
    """内容框(模板坐标) -> anchor=[0.5,0.0] 用的 pos_rel。

    ★ 为什么是顶边不是中心：后发/马尾挂的是摆链，anchor 同时是**物理支点**。
      支点必须在发根（精灵顶边），放中心的话整束头发会绕着自己的腰甩。
    ★ 精灵比内容框四周各大 CROP_MARGIN，所以顶边在内容框上面 0.04·h 处。
    """
    x0, y0, x1, y1 = px
    cx = (x0 + x1) / 2.0
    top = y0 - MARGIN * (y1 - y0)
    bfx = (cx - BBOX0[0]) * S
    bfy = (top - BBOX0[1]) * S
    return [round((bfx - REF[0]) / U, 6), round((bfy - REF[1]) / U, 6)]

CUT_NOTE = ("★ 2026-10-19 T46.14：源图换成**从参考模板切下来的那一片**"
            "（tools/cut_from_sheets.py）。此前这里挂的是一张单独生成的 AI 图，"
            "和本体、和同发型的其它件之间没有任何共同约束 —— 用户说的"
            "「拼接痕迹很明显」就是这么来的。现在同一发型的后发与头顶"
            "**出自同一张全身图的同一次落笔**，接缝从定义上不存在。"
            "几何也不再是估的：pos_rel / sprite_h_rel 由切件器按"
            "模板→body_full→rig 的坐标链算出来。")

# ---- 1) 新增 head_crown_tied 槽（层 239）------------------------------------
if not any(s['id'] == 'head_crown_tied' for s in d['slots']):
    d['slots'].append(collections.OrderedDict([
        ('id', 'head_crown_tied'),
        ('label', '扎发的头顶（刘海之下、后发之上）'),
        ('layer', 189),
        ('group', 'head'),
        ('anchor', [0.5, 0.0]),
        ('curve', 'root'),
        ('note', '扎起来的发型专用：头顶被收拢的那一片。★ 层 187~189 卡在 '
                 '呆毛(190) 之下、头壳 seg_head(180) 之上 —— 呆毛压在它上面，'
                 '刘海(240) 也压在它上面，所以件的下沿切在发际线就够了、不会露边；'
                 '而它压在头壳和后发壳上面，'
                 '于是颅顶看起来真的被扎起来了。用户第十二问原话「扎发造型头顶'
                 '必须跟着变」，缺的就是这一层：以前只换尾巴不换头顶，'
                 '结果是一颗短发脑袋后面挂两根辫子。★ 下沿绝对不能切到眼线 —— '
                 '眼睛在 211~234，比 239 低，切过头会把眼睛盖住（第十一问）。'),
    ]))
    print('+ slot head_crown_tied (239)')

# ---- 2) 现有三个发型的后发件改用模板切片 -------------------------------------
REWIRE = {
    'hair_twin_l': 'hair_twin_back_l',
    'hair_twin_r': 'hair_twin_back_r',
    'hair_pony':   'hair_pony_back',
    'hair_long':   'hair_long_back',
}
by_id = {a['id']: a for a in d['attachments']}
# ★ 双马尾两束**仍然走"一张源图 + 镜像"**，不各用各的那一片。
#   模板是 AI 画的，左右两束的发缕走向、长度、外摆角度都有细微出入；
#   而脸是对称参照物，这点出入放在脑袋两边特别显眼（猫耳那四轮返工的教训，
#   rig 里也有一道「双马尾左右真对称」的硬闸）。所以右束 = 左束镜像，
#   位置取两侧实测值的均值 ±，保证关于中线严格对称。
_xl = abs(place(GEO['pieces']['hair_twin_back_l']['px'])[0])
_xr = abs(place(GEO['pieces']['hair_twin_back_r']['px'])[0])
TWIN_X = round((_xl + _xr) / 2.0, 6)

for aid, piece in REWIRE.items():
    a = by_id[aid]; g = GEO['pieces'][piece]
    a['source'] = g['sprite_file']
    a['ref'] = 'head_top'
    a['unit'] = 'head'                  # 几何是按 head=278.0px 量的
    a.pop('pos_unit', None)             # 不再混用 torso/head 两套单位
    a['anchor'] = [0.5, 0.0]
    a['pos_rel'] = place(g['px'])
    a['sprite_h_rel'] = g['sprite_h_rel']
    a['width_ratio'] = 1.0              # 保模板原始宽高比，不再横向压
    a.pop('mirror', None)
    if aid in ('hair_twin_l', 'hair_twin_r'):
        # 两束同源：都用左边那一片，右束靠 mirror 翻过去
        g = GEO['pieces']['hair_twin_back_l']
        a['source'] = g['sprite_file']
        a['sprite_h_rel'] = g['sprite_h_rel']
        sign = -1.0 if aid.endswith('_l') else 1.0
        a['pos_rel'] = [sign * TWIN_X, place(g['px'])[1]]
        if aid.endswith('_r'):
            a['mirror'] = True
    a.pop('source_crop', None)
    a.pop('_slim_note', None)
    a.pop('_size_note', None)
    a.pop('_hl_note', None)
    a['_cut_note'] = CUT_NOTE
    print('~ %-14s <- %-22s pos_rel %s  h_rel %.4f'
          % (aid, g['sprite_file'], a['pos_rel'], a['sprite_h_rel']))

ref_match_side = by_id['hair_long'].get('recolor_match')

# ---- 2b) 脸侧鬓发也换成模板切片（原来是从本体侧发拉长派生的）----
#   用户看 2026-10-19 的截图说「长发没有跟模板一致，而且有很多拼接的痕迹」
#   「短发的造型和双马尾合在一起了」。根因是只加不减：底图那颗短发的
#   后脑壳(hair_back 170) 和齐腮鬓发(hair_side_l/r 245/246) 原样留着。
#   现在三档都把它们藏掉，换成从模板上切的**同源**头壳 + 鬓发。
SIDE_REWIRE = {
    'hair_sweep_twin_l': 'hair_twin_side_l',
    'hair_sweep_twin_r': 'hair_twin_side_r',
    'hair_sweep_pony_l': 'hair_pony_side_l',
    'hair_sweep_pony_r': 'hair_pony_side_r',
    'hair_sidelong_l':   'hair_long_side_l',
    'hair_sidelong_r':   'hair_long_side_r',
}
for aid, piece in SIDE_REWIRE.items():
    if aid not in by_id or piece not in GEO['pieces']:
        continue
    a = by_id[aid]; g = GEO['pieces'][piece]
    a.pop('derive', None)            # 不再从本体侧发拉长派生
    a.pop('_derive_note', None)
    a['source'] = g['sprite_file']
    a['ref'] = 'head_top'
    a['unit'] = 'head'
    a.pop('pos_unit', None)
    a['anchor'] = [0.5, 0.0]
    a['pos_rel'] = place(g['px'])
    a['sprite_h_rel'] = g['sprite_h_rel']
    a['width_ratio'] = 1.0
    a['_cut_note'] = CUT_NOTE
    if ref_match_side:
        a['recolor_match'] = ref_match_side
    print('~ %-18s <- %-26s pos_rel %s  h_rel %.4f'
          % (aid, g['sprite_file'], a['pos_rel'], a['sprite_h_rel']))

# ---- 3) 新增三个头顶件 --------------------------------------------------------
# ★ 三件互斥，但层号仍要各不相同（沿用 sweep_twin/sweep_pony 的既有约定；
#   rig 的「层号不重复」闸门是一刀切的）。选 187~189 的理由：
#   紧挨呆毛(190)**之下** —— 切件时特意把呆毛从头顶件里剔出去了（它有独立
#   摆动物理），所以呆毛必须压在头顶件上面；再往下 seg_head(180) 是头壳，
#   头顶件必须在它之上才盖得住本体颅顶。181~189 整段空着。
CROWN_LAYER = {'twin': 187, 'pony': 188, 'long': 189}
CROWN = [('twin', 'hair_twin_crown', '双马尾'),
         ('pony', 'hair_pony_crown', '高马尾'),
         ('long', 'hair_long_crown', '长发')]
ref_match = by_id['hair_long'].get('recolor_match')
for pose, piece, label in CROWN:
    cid = 'hair_crown_' + pose
    if cid in by_id:
        continue
    g = GEO['pieces'][piece]
    att = collections.OrderedDict([
        ('id', cid),
        ('label', '头顶·%s' % label),
        ('slot', 'head_crown_tied'),
        ('source', g['sprite_file']),
        ('sprite', 'hair_crown_%s.png' % pose),
        ('tags', ['hair', 'hairstyle']),
        ('pose_group', 'hairstyle'),
        ('pose_id', pose),
        ('anchor', [0.5, 0.0]),
        ('ref', 'head_top'),
        ('unit', 'head'),
        ('pos_rel', place(g['px'])),
        ('sprite_h_rel', g['sprite_h_rel']),
        ('width_ratio', 1.0),
        ('layer', CROWN_LAYER[pose]),
        ('note', '%s 档位的头顶。和同档的后发/尾巴**切自同一张参考模板**，'
                 '所以发缕走向、高光位置、色相天然连续。'
                 '件只覆盖发际线以上，发际线以下交给本体原有的刘海件(240)。'
                 % label),
        ('_cut_note', CUT_NOTE),
    ])
    if ref_match:
        att['recolor_match'] = ref_match
    d['attachments'].append(att)
    print('+ %-16s <- %-24s pos_rel %s  h_rel %.4f'
          % (cid, g['sprite_file'], att['pos_rel'], att['sprite_h_rel']))

io.open(P, 'w', encoding='utf-8').write(
    json.dumps(d, ensure_ascii=False, indent=2) + '\n')
print('\nattachments.json 已更新')

# long 档不藏本体鬓发（理由见 pose_groups.hairstyle 的 note）
for g in d['pose_groups']:
    if g['id'] == 'hairstyle':
        # ★ 三档都要把**底图短发的头壳和鬓发**一起藏掉。
        #   只藏鬓发不藏头壳 = 「一颗短发脑袋 + 挂了两根辫子」，
        #   这正是用户 2026-10-19 判的「短发的造型和双马尾合在一起了」。
        #   接管者是同一张模板上切下来的 hair_crown_* （头壳）与
        #   hair_sweep_* / hair_sidelong_*（鬓发），同源所以不会有拼接痕。
        for k in ('twin', 'pony', 'long'):
            g['hide_parts'][k] = ['hair_side_l', 'hair_side_r', 'hair_back']
io.open(P, 'w', encoding='utf-8').write(json.dumps(d, ensure_ascii=False, indent=2) + '\n')
