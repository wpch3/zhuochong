# -*- coding: utf-8 -*-
"""把 cut_hood_from_sheets.py 切出来的兜帽件接进 attachments.json（T46.17）。**幂等**。

用法：

    /tmp/imgenv/bin/python tools/cut_hood_from_sheets.py
    /tmp/imgenv/bin/python tools/wire_hoodcuts.py
    ZC_PYTHON=/tmp/imgenv/bin/python bash tools/rebuild_parts.sh xiaoxun teen

接了什么
--------
  hood_up        短发档的帽壳（**沿用既有 id**，只把源图从解析平涂那张
                 acc_hood_cute.png 换成模板切片，几何一并重算）
  hood_up_twin   双马尾档的帽壳
  hood_up_pony   马尾档的帽壳
  hood_up_long   长发档的帽壳
  hair_hood_twin 戴帽时从帽口垂下来的两束（双马尾档）
  hair_hood_pony 戴帽时从帽口垂下来的那一束（马尾档）

「戴帽 ∧ 发型=X」这个与条件怎么实现
-----------------------------------
引擎 `pose_opacity`（src/core/zrig.c:4621）对**所有** pose 组是连乘的：

    一个部件属于某档位  ⇒ 乘那个档位的权重
    一个部件被某档位 hide ⇒ 乘 (1 - 那个档位的权重)

所以：六件全部挂在 `hood_pose.up` 下（兜帽收起时一起消失），
再让 `hairstyle.<档>` 把**不属于这个发型的那几件** hide 掉。
两个组相乘 = 与条件，一行 C 代码都不用改。

★ 为什么 `hood_pose.up` 还要 hide 掉扎发件
   把第一版帽壳贴回「不戴帽」底图做验收（教程：切り分けた後には元絵と
   重ねあわせて不足パーツを必ず確認），一眼看出 twin / pony / long 三档
   **发尾从帽顶戳出来**。戴上兜帽时头发本身的造型是变了的 —— 马尾不再
   高高扎起，而是从帽口垂到胸前。所以戴上时要收走：
   三片头顶扎发件（hair_crown_*）+ 双马尾两束 + 高马尾，
   换成从戴帽模板上切下来的 hair_hood_twin / hair_hood_pony。

★ 长发档的 hair_hood_long（2026-10-20 补齐，原欠账 T46.17b）
   第一版切出来碎成 9 段不连续的发片（用户明令「头发不许有断缺」），
   当时不合格就退回「只收走头顶扎发件、保留原来的长发与鬓发」。
   现在 cut_hood_from_sheets.py 加了沿线稿的测地生长（种子 = 旧发片，
   闸 = 线稿 ∧ b>=r ∧ 远离薄荷罗纹），9 段 → 5 段，剩下的 5 段是
   **原画本来的遮挡**（手臂压住发帘、裙子压住腿间那一缕），所以接上了。
   接上之后 hood_pose.up 要同时收走长发档原来那三件
   （acc_hair_long / acc_hair_sidelong_l / acc_hair_sidelong_r）——
   戴帽模板上的发帘是从帽口垂到胸前的，和不戴帽时披在背后的形状不是一个，
   两套叠在一起会错位重影。
"""
import collections
import io
import json

GEO = json.load(io.open('characters/xiaoxun/design/sheets/hood_geometry.json',
                        encoding='utf-8'))
P = 'characters/xiaoxun/design/attachments.json'
with io.open(P, encoding='utf-8') as fh:
    d = json.load(fh, object_pairs_hook=collections.OrderedDict)

S = GEO['scale_sheet_to_bodyfull']
U = GEO['head_unit_px']
BBOX0 = (257, 27)
REF = (215.0, 0.0)
MARGIN = 0.04


def place(px):
    """内容框(模板坐标) → anchor=[0.5,0.0] 的 pos_rel。与 wire_sheetcuts 同一套。"""
    x0, y0, x1, y1 = px
    cx = (x0 + x1) / 2.0
    top = y0 - MARGIN * (y1 - y0)
    bfx = (cx - BBOX0[0]) * S
    bfy = (top - BBOX0[1]) * S
    return [round((bfx - REF[0]) / U, 6), round((bfy - REF[1]) / U, 6)]


NOTE = ("★ 2026-10-19 T46.17：兜帽按参考模板重做。此前这里挂的是 "
        "acc_hood_cute.png —— 一张**单独生成再按头部几何缩放**的图，"
        "和身体没有共同约束，用户从第十三问到第十六问连着打回四次。"
        "现在这一片是从 design/sheets/sheet_<发型>_hood.png 上切下来的："
        "同一张全身差分立绘、同一次落笔，帽口与脸、内衬与衣领天然对得上。"
        "四种发型各切一片，因为帽口处发缕穿出来的位置每档都不同。")

HOODS = [
    ('hood_up',      'short', 'acc_hood_short', 252, '兜帽·戴上（短发）'),
    ('hood_up_twin', 'twin',  'acc_hood_twin',  253, '兜帽·戴上（双马尾）'),
    ('hood_up_pony', 'pony',  'acc_hood_pony',  254, '兜帽·戴上（马尾）'),
    ('hood_up_long', 'long',  'acc_hood_long',  255, '兜帽·戴上（长发）'),
]
HOODHAIR = [
    ('hair_hood_twin', 'twin', 'hair_hood_twin', 256, '戴帽时垂下的双马尾'),
    ('hair_hood_pony', 'pony', 'hair_hood_pony', 257, '戴帽时垂下的马尾'),
    ('hair_hood_long', 'long', 'hair_hood_long', 258, '戴帽时垂下的长发'),
]

by_id = {a['id']: a for a in d['attachments']}

# ---- 1) 四片帽壳 --------------------------------------------------------------
base = by_id['hood_up']
for aid, style, piece, layer, label in HOODS:
    g = GEO['pieces'].get(piece)
    if g is None:
        print('! %s 没有切出来，跳过' % piece)
        continue
    if aid in by_id:
        a = by_id[aid]
    else:
        a = collections.OrderedDict([
            ('id', aid),
            ('label', label),
            ('slot', 'head_over_hair'),
            ('sprite', '%s.png' % piece),
            ('anchor', [0.5, 0.0]),
            ('curve', 'tip'),
            ('tags', ['accessory', 'outfit', 'hood']),
            ('pose_group', 'hood_pose'),
            ('pose_id', 'up'),
            ('physics', collections.OrderedDict([
                ('segments', [collections.OrderedDict([
                    ('id', '%s_x' % aid),
                    ('driver', 'head'),
                    ('axis', 'x'),
                    ('param', 'bend_x'),
                    ('ratio', 0.22),
                    ('stiffness', 74.0),
                    ('damping', 8.4),
                    ('max', 3.0),
                    ('note', '和短发档那顶同参数：兜帽是**跟着头走**的硬件，'
                             '不是吊着的软件。布越厚越贴头越不该晃，'
                             '而且它和脸挨着，晃大了会穿帮。'),
                ])]),
            ])),
        ])
        d['attachments'].append(a)
        by_id[aid] = a
        print('+ %s' % aid)
    a['source'] = g['sprite_file']
    a['ref'] = 'head_top'
    a['unit'] = 'head'
    a['anchor'] = [0.5, 0.0]
    a['pos_rel'] = place(g['px'])
    a['sprite_h_rel'] = g['sprite_h_rel']
    a['width_ratio'] = 1.0           # 保模板原始宽高比，不再横向拉伸
    a['layer'] = layer
    a.pop('source_crop', None)
    a.pop('pos_unit', None)
    a['_cut_note'] = NOTE
    print('~ %-14s <- %-28s pos_rel %s  h_rel %.4f  layer %d'
          % (aid, g['sprite_file'], a['pos_rel'], a['sprite_h_rel'], layer))

# ---- 2) 戴帽时垂下来的头发 ----------------------------------------------------
BASE_MATCH = {k: v for k, v in (by_id['hair_long'].get('recolor_match') or {}).items()
              if k in ('ref_sprites', 'palette_hex', 'keep', 'l_sigma_max', 'l_offset')}
GRPNOTE = ('★★★ 2026-10-21 第二十九问：色彩迁移**留着，但改成整组共用一套系数**。上一版曾把 recolor_match 整个摘掉，理由是「切件和本体同源，不必再迁移」—— 实拍打脸：短发是淡紫、twin/pony/long 变成银灰，同一个角色换发型头发颜色就变了（七张模板是分别出图的，底色本来就偏银）。真正的病因不是「做了迁移」，而是**逐片各算一套 μ/σ**：刘海片一套、横髪片另一套，两片在脸侧相接处颜色对不上 ⇒ 用户说的「头发突然截断变淡粉」；长发帘自带蓝梢渐变，σ 一归一化就被压平成粉灰。stats_group 让同一张模板切下来的所有片共用一个仿射变换：组内相对关系原样保留，只把整组平移到本体头发的分布上。另一半病因是反预乘没抹边（见 make_attach_parts 的 bleed_edge）。')
for aid, style, piece, layer, label in HOODHAIR:
    g = GEO['pieces'].get(piece)
    if g is None:
        print('! %s 没有切出来，跳过' % piece)
        continue
    if aid in by_id:
        a = by_id[aid]
    else:
        a = collections.OrderedDict([
            ('id', aid),
            ('label', label),
            ('slot', 'head_side_hair'),
            ('sprite', '%s.png' % piece),
            ('anchor', [0.5, 0.0]),
            ('curve', 'tip'),
            ('tags', ['hair', 'hood']),
            ('pose_group', 'hood_pose'),
            ('pose_id', 'up'),
        ])
        d['attachments'].append(a)
        by_id[aid] = a
        print('+ %s' % aid)
    a['source'] = g['sprite_file']
    a['ref'] = 'head_top'
    a['unit'] = 'head'
    a['anchor'] = [0.5, 0.0]
    a['pos_rel'] = place(g['px'])
    a['sprite_h_rel'] = g['sprite_h_rel']
    a['width_ratio'] = 1.0
    a['layer'] = layer               # ★ 压在帽壳之上：发缕是从帽口里**穿出来**的
    # ★ 别写 `if ref_match:` 守卫 —— wire_sheetcuts 先跑，那边会重写
    #   hair_long 的 recolor_match，取快照的时机对不上。栽过一次。
    a.pop('_nomatch_note', None)
    rm = dict(a.get('recolor_match') or BASE_MATCH)
    rm['stats_group'] = 'sheet_' + style + '_hood'
    rm['grp_note'] = GRPNOTE
    a['recolor_match'] = rm
    a['_cut_note'] = NOTE
    print('~ %-14s <- %-28s pos_rel %s  h_rel %.4f  layer %d'
          % (aid, g['sprite_file'], a['pos_rel'], a['sprite_h_rel'], layer))

# ---- 3) 互斥关系 --------------------------------------------------------------
have = set(by_id)
hood_ids = {s: i for i, s, _p, _l, _b in HOODS if i in have}
hair_ids = {s: i for i, s, _p, _l, _b in HOODHAIR if i in have}
mine = {}
for s in ('short', 'twin', 'pony', 'long'):
    mine[s] = [x for x in (hood_ids.get(s), hair_ids.get(s)) if x]
allmine = [x for s in mine for x in mine[s]]
# rig 侧 id = 'acc_' + attachments 侧 id（同上）
RIG = lambda i: 'acc_' + i

# ★★★ 每个部件归哪个档位 —— 引擎只准归一处（zrig.c 加载期硬校验
#     「一个部件只能归一处」），所以不能把帽件同时挂进 hood_pose 和 hairstyle。
#     可用的合法组合只有一种：
#       · 短发那顶 acc_hood_up   → 归 hood_pose.up；三个发型档 hide 掉它。
#       · 另外三顶 + 两片帽下头发 → 归**各自的发型档**；再由 hood_pose.down
#         反向把它们按住（跨组 hide 是允许的，hood_pose.up 藏 acc_hair_twin_l
#         就是同一个写法）。
#     于是「戴帽 ∧ 发型=X」这个与条件由「发型档给的 opacity」×「down 档的
#     1-opacity」凑出来，一行 C 都不用改。
OWNER = {'hood_up': ('hood_pose', 'up'),
         'hood_up_twin': ('hairstyle', 'twin'),
         'hair_hood_twin': ('hairstyle', 'twin'),
         'hood_up_pony': ('hairstyle', 'pony'),
         'hair_hood_pony': ('hairstyle', 'pony'),
         'hood_up_long': ('hairstyle', 'long'),
         'hair_hood_long': ('hairstyle', 'long')}
for _a in d['attachments']:
    if _a['id'] in OWNER:
        _a['pose_group'], _a['pose_id'] = OWNER[_a['id']]

pg = {g['id']: g for g in d['pose_groups']}

# 戴上兜帽时要收走的既有部件：三片头顶扎发 + 双马尾两束 + 高马尾
hp = pg['hood_pose']
# ★ rig 里挂件的部件 id 带 `acc_` 前缀（make_rig 加的），hide 名单必须用
#   **rig 侧的 id**，不是 attachments 里的 id。第一版写成 attachments 的 id，
#   make_rig 原样打印「⚠ 本形态没有 [...] —— 档位 'up' 的 hide 名单跳过它们」
#   然后**静默跳过**，于是戴上兜帽发束照样从帽顶戳出来。
#   （hair_side_l / hair_back 那几个没有前缀，是因为它们是身体分段件不是挂件。）
hp['hide_parts'] = collections.OrderedDict([
    ('up', ['acc_hair_crown_twin', 'acc_hair_crown_pony', 'acc_hair_crown_long',
            'acc_hair_twin_l', 'acc_hair_twin_r', 'acc_hair_pony',
            # ★ 2026-10-20：长发档也换整套了。戴帽模板上的长发是从帽口
            #   垂到胸前的，和不戴帽时披在背后的 acc_hair_long 形状不同，
            #   两套叠着会错位重影；鬓发同理。由 acc_hair_hood_long 接手。
            'acc_hair_long', 'acc_hair_sidelong_l', 'acc_hair_sidelong_r']),
    # 不戴帽时，把归在发型档下的那三套帽件按住（见上面 OWNER 的说明）
    ('down', ['acc_hood_up_twin', 'acc_hair_hood_twin',
              'acc_hood_up_pony', 'acc_hair_hood_pony',
              'acc_hood_up_long', 'acc_hair_hood_long']),
])
hp['_hood_note'] = (
    '★ T46.17：`up` 这一档除了显示帽壳，还要**收走**扎起来的那套头发。'
    '把第一版帽壳贴回不戴帽底图做验收时一眼看出：马尾/双马尾的发束会'
    '从帽顶戳出来 —— 戴上兜帽时头发本身的造型就是变了的。收走之后由'
    'hair_hood_twin / hair_hood_pony（从戴帽模板上切的）接手。'
    '★ 2026-10-20 补齐长发档：hair_hood_long 原来碎成 9 段不合格，'
    '切件器加了沿线稿的测地生长之后只剩原画本来的遮挡（手臂、裙子），'
    '于是一并接上；同时把 acc_hair_long 与两片鬓发也收走，'
    '避免「垂到胸前的发帘」和「披在背后的长发」两套错位重影。')

# 每种发型认领自己那顶帽子 —— 用 extra_parts 把帽件**登记成这一档自己的件**
#
# ★★★ 2026-10-19 踩过的坑，别再回头：第一版是给 hairstyle 建了个 `none` 档，
#   让它去 hide 另外三顶帽子。渲染出来四顶帽子叠在一起、帽檐厚得像救生圈。
#   根因在引擎：zrig.c:5619 `zrig_pose_set` 把字符串 "none" **当保留字**
#   （`id=none` 的语义是「整组关掉」，cur=-1），所以叫 `none` 的档位
#   **永远选不中**，它的 hide 名单一行都不会生效 —— 不报错、不告警。
#   （api 文档 src/headless/main_headless.c:21 就写着「id=none 整组关掉」。）
#
# 正解是顺着引擎本来的设计走，不新增档位也不碰 C：
#   · 三顶带发型的帽子 → 用 extra_parts 挂进**对应发型档**。
#     引擎 pose_opacity 对 parts 是乘 entry 的 opacity（zrig.c:4621），
#     一个件同时属于 hood_pose.up 和 hairstyle.twin 就被乘两次 ——
#     「戴帽 ∧ 发型=twin」这个与条件天然成立。发型切到别档 → 乘 0 → 自动消失，
#     连 hide 都不用写。
#   · 短发那顶 acc_hood_up 不属于任何发型档（短发 = 发型组关掉的状态，
#     cur=-1，没有档位可挂），所以反过来由三个发型档 hide 掉它。
hs = pg['hairstyle']
hide = hs.setdefault('hide_parts', collections.OrderedDict())
hide.pop('none', None)              # 清掉第一版那个选不中的死档位
hs.pop('extra_parts', None)         # 也清掉第二版那个「一个部件归两处」的写法
SHORT_HOOD = [RIG(x) for x in mine['short']]
for style in ('twin', 'pony', 'long'):
    # 旧值里把本轮管的件全剔掉再重写，保证反复跑结果一样（幂等）
    cur = [x for x in hide.get(style, [])
           if x not in [RIG(y) for y in allmine] and x not in allmine]
    hide[style] = cur + SHORT_HOOD

hs['_hood_note'] = (
    '★ T46.17：兜帽四形态。四顶帽子 + 两片帽下头发都挂在 hood_pose.up 下；'
    '其中三顶直接归在对应发型档名下，靠引擎的跨组连乘'
    '（zrig.c:4621 pose_opacity，down 档反向 hide）凑出「戴帽 ∧ 发型=X」。短发那顶没有发型档'
    '可挂（短发 = 整组关掉 cur=-1），改由三个发型档 hide 掉。'
    '不要再给 hairstyle 加名叫 `none` 的档位 —— "none" 是 zrig_pose_set 的'
    '保留字，那样的档位永远选不中。')

with io.open(P, 'w', encoding='utf-8') as fh:
    json.dump(d, fh, ensure_ascii=False, indent=2)
    fh.write('\n')
print('\n写回 %s（attachments %d 件）' % (P, len(d['attachments'])))
for pose in ('twin', 'pony', 'long'):
    print('  hairstyle.%-5s hide → %s' % (pose, hide[pose]))
print('  hood_pose.down hide → %s' % hp['hide_parts']['down'])
print('  hood_pose.up  hide → %s' % hp['hide_parts']['up'])
