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
BASE_MATCH = None     # 下面从 hair_long 上取一份当模板
GRPNOTE = ('★★★ 2026-10-21 第二十九问：色彩迁移**留着，但改成整组共用一套系数**。上一版曾把 recolor_match 整个摘掉，理由是「切件和本体同源，不必再迁移」—— 实拍打脸：短发是淡紫、twin/pony/long 变成银灰，同一个角色换发型头发颜色就变了（七张模板是分别出图的，底色本来就偏银）。真正的病因不是「做了迁移」，而是**逐片各算一套 μ/σ**：刘海片一套、横髪片另一套，两片在脸侧相接处颜色对不上 ⇒ 用户说的「头发突然截断变淡粉」；长发帘自带蓝梢渐变，σ 一归一化就被压平成粉灰。stats_group 让同一张模板切下来的所有片共用一个仿射变换：组内相对关系原样保留，只把整组平移到本体头发的分布上。另一半病因是反预乘没抹边（见 make_attach_parts 的 bleed_edge）。')

BASE_MATCH = {k: v for k, v in (by_id['hair_long'].get('recolor_match') or {}).items()
              if k in ('ref_sprites', 'palette_hex', 'keep', 'l_sigma_max', 'l_offset')}
assert BASE_MATCH.get('ref_sprites'), '取不到本体头发的配色参照'

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
    a.pop('_nomatch_note', None)
    rm = dict(a.get('recolor_match') or BASE_MATCH)
    rm['stats_group'] = 'sheet_' + piece.split('_')[1]
    rm['grp_note'] = GRPNOTE
    a['recolor_match'] = rm
    a['_cut_note'] = CUT_NOTE
    print('~ %-14s <- %-22s pos_rel %s  h_rel %.4f'
          % (aid, g['sprite_file'], a['pos_rel'], a['sprite_h_rel']))

ref_match_side = by_id['hair_long'].get('recolor_match')

# ---- 2b) 脸侧鬓发也换成模板切片（原来是从本体侧发拉长派生的）----
#   用户看 2026-10-19 的截图说「长发没有跟模板一致，而且有很多拼接的痕迹」
#   「短发的造型和双马尾合在一起了」。根因是只加不减：底图那颗短发的
#   后脑壳(hair_back 170) 和齐腮鬓发(hair_side_l/r 245/246) 原样留着。
#   现在三档都把它们藏掉，换成从模板上切的**同源**头壳 + 鬓发。
#   ★ 只剩长发还需要独立的鬓发件。扎发那两档的脸侧碎发已经整个包含在
#     头壳件里了（头壳 = 下巴以上的整片头发），再单切一遍只会多一条横缝。
SIDE_REWIRE = {
    'hair_sidelong_l':   'hair_long_side_l',
    'hair_sidelong_r':   'hair_long_side_r',
}

#   ★ 这四件是「AI 碎片」时代的产物：从本体侧发拉长派生、再手调几何。
#     它们和模板不同源，正是用户说的「很多拼接的痕迹」的来源之一。
#     头壳件接管之后它们完全多余 —— 删掉，而不是留着藏起来。
DROP = ['hair_sweep_twin_l', 'hair_sweep_twin_r',
        'hair_sweep_pony_l', 'hair_sweep_pony_r']
_before = len(d['attachments'])
d['attachments'] = [a for a in d['attachments'] if a.get('id') not in DROP]
by_id = {a['id']: a for a in d['attachments']}
if len(d['attachments']) != _before:
    print('- 删掉 %d 件 AI 碎片时代的脸侧件：%s'
          % (_before - len(d['attachments']), ', '.join(DROP)))
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
    a.pop('_nomatch_note', None)
    rm = dict(a.get('recolor_match') or BASE_MATCH)
    rm['stats_group'] = 'sheet_long'
    rm['grp_note'] = GRPNOTE
    a['recolor_match'] = rm
    print('~ %-18s <- %-26s pos_rel %s  h_rel %.4f'
          % (aid, g['sprite_file'], a['pos_rel'], a['sprite_h_rel']))

# ---- 2c) twin / pony 的脸侧细缕（2026-10-20 第二十四问）----------------------
#   背景：用户看 pony 的截图说「马尾的前发还是短发原件没变」。
#   把四张模板并排放大一比就看出来了（/tmp/z_bangs_cmp.png）——
#   前髪（额前那一片）四档几乎一样，真正不同的是**横髪**：
#       短发底图 = 齐腮、粗、**蓝梢**
#       twin / pony / long = 细、长、淡紫
#   之前三档一直沿用底图那对 hair_side_l/r(245/246)，所以不管换哪个发型，
#   脸两边永远挂着短发那对蓝梢粗鬓 —— 这就是"前发没变"的真身。
#   头壳件现在自己切到**下巴 +80**，扎发那两档的脸侧基本够用；
#   万一某档的细缕真的垂到胸口（掩膜 ≥8000px 才会被切件器保留），
#   就在这里补一件，接到 head_side_sweep 槽。**没切出来就跳过**，
#   不会凭空造一个空件。
# ★ 2026-10-20 第二十五问：原来写的 241/242 **撞了眉毛的 ghost 件**
#   （brow_l_ghost=241、brow_r_ghost=242），selfcheck 的「层号不重复」闸直接红。
#   240~251 这一段实际占用情况：240 hair_front、241/242 brow_*_ghost、
#   245/246 hair_side_l/r（本档已藏）、249/251 acc_hair_sidelong_*。
#   空着的是 243/244/247/248/250 —— 这四件挑 243/244/247/248。
#   四件两两互斥（twin 和 pony 不会同时在），但闸门是一刀切的，仍要各不相同。
SWEEP_LAYER = {('pony', 'l'): 243, ('pony', 'r'): 244,
               ('twin', 'l'): 247, ('twin', 'r'): 248}
for pose, label in (('twin', '双马尾'), ('pony', '高马尾')):
    for side in ('l', 'r'):
        piece = 'hair_%s_side_%s' % (pose, side)
        if piece not in GEO['pieces']:
            continue
        cid = 'hair_sweep_%s_%s' % (pose, side)
        g = GEO['pieces'][piece]
        if cid in by_id:
            a = by_id[cid]
        else:
            a = collections.OrderedDict([
                ('id', cid),
                ('label', '脸侧细缕·%s（%s）' % (label, '左' if side == 'l' else '右')),
                ('slot', 'head_side_sweep'),
                ('sprite', '%s.png' % cid),
                ('tags', ['hair', 'hairstyle']),
                ('pose_group', 'hairstyle'),
                ('pose_id', pose),
                ('ref', 'head_top'),
                ('unit', 'head'),
                ('note', '和同档的头壳/后发**切自同一张参考模板**，'
                         '所以发缕走向与色相天然连续。'
                         '层号排在刘海(240)与眉毛(236/237)之上、'
                         '本体鬓发(245/246，本档已藏)之下。'),
            ])
            d['attachments'].append(a)
            by_id[cid] = a
            print('+ %-18s <- %s' % (cid, g['sprite_file']))
        a['source'] = g['sprite_file']
        a['anchor'] = [0.5, 0.0]
        a['pos_rel'] = place(g['px'])
        a['sprite_h_rel'] = g['sprite_h_rel']
        a['width_ratio'] = 1.0
        a['layer'] = SWEEP_LAYER[(pose, side)]
        a['_cut_note'] = CUT_NOTE
        a.pop('_nomatch_note', None)
        rm = dict(a.get('recolor_match') or BASE_MATCH)
        rm['stats_group'] = 'sheet_' + pose
        rm['grp_note'] = GRPNOTE
        a['recolor_match'] = rm
        print('~ %-18s <- %-26s pos_rel %s  h_rel %.4f'
              % (cid, g['sprite_file'], a['pos_rel'], a['sprite_h_rel']))

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
    g = GEO['pieces'][piece]
    # ★ 已经在库里的，**要把几何重新刷一遍**，不能 `continue` 跳过。
    #   栽过一次：上一轮这里写的是「存在就跳过」，于是重切之后件还挂着
    #   上一版的 sprite_h_rel 0.266（=74px），而新切片是 287x255 —— 引擎把
    #   74px 的图拉到 245px 高，渲染出来是一团半透明的糊状方块盖在脸上。
    #   接线脚本的幂等指的是「重跑结果一致」，不是「重跑什么都不做」。
    if cid in by_id:
        a = by_id[cid]
        a['source'] = g['sprite_file']
        a['pos_rel'] = place(g['px'])
        a['sprite_h_rel'] = g['sprite_h_rel']
        a['width_ratio'] = 1.0
        a['layer'] = CROWN_LAYER[pose]
        a.pop('_nomatch_note', None)
        rm = dict(a.get('recolor_match') or BASE_MATCH)
        rm['stats_group'] = 'sheet_' + pose
        rm['grp_note'] = GRPNOTE
        a['recolor_match'] = rm
        a['_cut_note'] = CUT_NOTE
        print('~ %-16s <- %-24s pos_rel %s  h_rel %.4f'
              % (cid, g['sprite_file'], a['pos_rel'], a['sprite_h_rel']))
        continue
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
    att.pop('_nomatch_note', None)
    _rm = dict(att.get('recolor_match') or BASE_MATCH)
    _rm['stats_group'] = 'sheet_' + pose
    _rm['grp_note'] = GRPNOTE
    att['recolor_match'] = _rm
    d['attachments'].append(att)
    print('+ %-16s <- %-24s pos_rel %s  h_rel %.4f'
          % (cid, g['sprite_file'], att['pos_rel'], att['sprite_h_rel']))

io.open(P, 'w', encoding='utf-8').write(
    json.dumps(d, ensure_ascii=False, indent=2) + '\n')
print('\nattachments.json 已更新')

# long 档不藏本体鬓发（理由见 pose_groups.hairstyle 的 note）
for g in d['pose_groups']:
    if g['id'] == 'hairstyle':
        # ★ 三档都要把**底图短发的后脑壳**藏掉（hair_back 170）。
        #   接管者是同一张模板上切下来的 hair_crown_*（头壳，下巴以上整片），
        #   同源所以不会有拼接痕；只藏鬓发不藏头壳 = 「一颗短发脑袋 +
        #   挂了两根辫子」，正是用户 2026-10-19 判的「短发造型和双马尾合在一起」。
        #
        # ★★★ 2026-10-20 第二十三问：**鬓发 hair_side_l/r 不再藏**。
        #   原来三档连鬓发一起藏，理由是「脸侧碎发已经包含在头壳件里」。
        #   实拍证伪：头壳件的轮廓根本没垂到脸颊两侧，于是 twin / pony / long
        #   在下颌两侧各留一块**全透明的楔形缺口**（实拍 /tmp/z_jaw.png，
        #   黑色＝什么都没画），戴上兜帽后缺口更大更显眼。
        #   用户三次截图里脸颊上那些「怪东西」就是这个洞的边缘。
        #   —— 鬓发是**齐腮短鬓**，四张模板（short/twin/pony/long）在脸颊
        #   这一段的头发形状本来就几乎一样，留着不会变回「短发头」：
        #   换头壳、换后发、换发尾这三件事都照做。
        #   真正的长远解法是从每张发型模板上单独切一对横髪，记在欠账里。
        #
        # ★★★ 2026-10-20 第二十四问：**鬓发重新藏回去**，欠账同时还掉。
        #   上面那段"四张模板脸颊这一段形状几乎一样"是我没放大看图就下的结论，
        #   错了。把四张模板并排放大（/tmp/z_bangs_cmp.png）一眼就能看见：
        #       短发底图 = 齐腮 / 粗 / **蓝梢**
        #       twin / pony / long = 细 / 长 / 淡紫、无蓝梢
        #   所以留着底图那对鬓发，换了发型脸前面还是短发 ——
        #   用户原话「马尾的前发是短发原件未改变」。
        #   现在敢藏的理由是**下颌那块地有人接管了**：头壳件的下界从"下巴线"
        #   推到"下巴 +80"，而且脸的开口改用**模板自己的皮肤**来挖
        #   （底图两腮被短鬓发盖着，拿它挖会在下巴上方横切一刀 = 断链），
        #   所以头壳现在一路连到下颌以下，第二十三问那个透明楔形不会回来。
        #   —— 这条必须配实拍验收，不能只看闸门（第二十三问已经吃过两次亏）。
        #
        # ★★★ 2026-10-20 第二十六问：**刘海 hair_front(240) 也藏掉**。
        #   这是\"换发型只换了后面\"的最后一块，也是用户第 ① 条
        #   「不戴帽子时两边脸消失了很多」的主因。
        #   查实过程：把三档的 hide 名单打出来，`hair_front` 一个都没在里面；
        #   拿模板的脸按眼距套准到渲染帧上做红色缺失图（/tmp/z_missface.png），
        #   8151 个脸像素里丢了 **1507 个（18.5%）**，集中在两眉上方
        #   和左右颊各一条竖带 —— 正是短发底图那对**齐腮粗蓝梢**刘海的形状。
        #   它在层 240，压在新头壳(189)、眼睛(211~234)之上，
        #   等于给长发/马尾硬扣了一顶短发刘海。
        #   敢藏的前提是**额头和脸侧有人接管**：头壳件上半段本来就从颅顶
        #   一路盖到眼线+20（避开眼睛），下半段这一轮改成按区域挖脸、
        #   贴着脸的轮廓垂到下巴 +20，再往下交给 side_l/side_r。
        #   —— 实拍验收图 logs/asset_qa/q26_face_before_after.png。
        for k in ('twin', 'pony', 'long'):
            g['hide_parts'][k] = ['hair_back', 'hair_side_l', 'hair_side_r',
                                  'hair_front']
io.open(P, 'w', encoding='utf-8').write(json.dumps(d, ensure_ascii=False, indent=2) + '\n')
