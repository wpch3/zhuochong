/* zmem —— 长记忆线：让她四年后还是她（T67.45）
 *
 * 要解决的问题（用户原话）
 * ------------------------------------------------------------------
 * 「对真正的『人』记忆线是很长的……她在四年后还能想起最开始陪着她成长的
 *   那个人。要让我们知道，在很久之后她还是她。」
 *
 * 这句话不能靠"把聊天记录存下来、需要时检索"来实现。三条硬理由：
 *
 *   ① **检索会失败。** 主流做法是 recency × importance × relevance 打分
 *      （Generative Agents）。recency 是指数衰减，四年前的条目分数趋近 0 ——
 *      除非它是 importance 极高的那一条。也就是说：**能留到四年的记忆，
 *      必须在写入时就被认定"不许淡"**，而不是靠四年后碰巧被检索到。
 *      实测研究也说得很清楚：长程对话里"轨迹回忆"准确率只有 44%（Anchor, 2026），
 *      指望模型自己记住是不可能的事。
 *
 *   ② **模型自己会漂。** 人格漂移是实测现象：8~12 轮就开始掉（Li et al. 2024），
 *      100 轮左右普遍偏离（Abdulhai et al. 2025）。所以"她还是她"不能交给模型，
 *      必须由引擎提供**稳定的锚**（身份内核 + 不可改写的原话）。
 *
 *   ③ **记忆会自己长歪。** 重巩固（reconsolidation）研究会告诉你"回忆会改写记忆"。
 *      对人来说这是特性，对陪伴产品是灾难：她会在三年后"记得"一件没发生过的事。
 *      所以本模块最硬的一条规矩是：**正文一次写成，永不改写**。
 *      之后只许变三个数：被回忆过几次、上次被回忆是什么时候、重要性（只许升）。
 *
 * 所以设计是「两种命运 + 一条铁律」
 * ------------------------------------------------------------------
 *   会淡的：日常事件（EVENT）。衰减只发生在**检索端**，文件里的字一个都不少。
 *   不会淡的：锚点（ANCHOR）。第一次见面、第一次叫名字、第一次吵架……
 *            上限 ZMEM_MAX_ANCHORS 条，**永远**进上下文；满了必须显式降级并留理由，
 *            绝不静默挤掉一个。
 *   铁律：正文不可变。删除只能是用户显式命令，落成墓碑（墓碑也留在文件里，可审计）。
 *
 * 为什么"遗忘"不做成删除
 * ------------------------------------------------------------------
 * 自动遗忘 = 静默数据丢失。人也会忘，但人忘的不是"内容被删掉"，是"想不起来了"。
 * 我们的遗忘也只发生在检索端，而且**用户随时能把原话翻出来**（/api/memory.json）。
 * 这和之前几条教训是同一条：悄悄少掉的东西，比明着缺的东西可怕得多。
 *
 * 落盘格式（append-only，重放即状态）
 * ------------------------------------------------------------------
 *   <root>/data/<character>/memory/chronicle.zm
 *   每条记录 32 字节头 + 正文：
 *     0  u32 magic 'ZME1'
 *     4  u16 type   1=ADD 2=PIN 3=DEL 4=TOUCH 5=SALIENCE 6=STORY
 *     6  u16 len    正文长度（<= ZMEM_MAX_TEXT）
 *     8  u32 id
 *     12 i64 t      unix 秒（写入方给；测试里可以用假时钟做"四年快进"）
 *     20 u32 hash   正文 FNV-1a，读盘时对账
 *     24 u32 aux    按 type 解释（ADD: kind | salience<<8）
 *     28 u32 key    "只记一次" 的键哈希（0 = 不参与去重）
 *     32 正文
 *   为什么不是"每次改都整份重写"：四年 2.9 万条，整份重写 = 2.9 万次全文件 IO；
 *   而且 append-only 天然能回答"她三个月前是怎么描述的"（历史版本都在）。
 */
#ifndef ZMEM_H
#define ZMEM_H

#include <stddef.h>
#include <stdint.h>

#include "zc.h"

#define ZMEM_MAX_TEXT     240      /* 一条正文上限（UTF-8 字节，按整字截断） */
#define ZMEM_MAX_ITEMS    40000    /* 4 年 x 每天 27 条；超了拒绝写入，不悄悄覆盖 */
#define ZMEM_MAX_ANCHORS  12       /* 常驻锚点上限 —— 满了必须显式降级 */
/* 每次回忆带几条"相关"条目（锚点另算）。
 * 6 → 8（T67.45 长跑实测）：同一件事在四年里被提过好几遍时，6 个名额不够铺开
 * 时间，最远的那两条必被挤掉 —— 而"最开始那件事"恰是最远的那条。
 * 8 条的块仍然远小于 ZMEM_BLOCK_CAP，预算上不疼。 */
#define ZMEM_RECALL_K     8
#define ZMEM_BLOCK_CAP    2400     /* 进提示词那一段的字节上限 */
#define ZMEM_STORY_GAP    2592000  /* 自述最短改写间隔：30 天 */
#define ZMEM_STORY_DRIFT  55       /* 自述与上一版的最小重合度（百分比） */

enum {
    ZMEM_EVENT  = 0,   /* 日常事件：会淡（只在检索端淡） */
    ZMEM_ANCHOR = 1,   /* 锚点：永不淡，永远进上下文 */
    ZMEM_DEED   = 2,   /* 她做过的事（她说的话、她的反应） */
    ZMEM_PROMISE= 3    /* 约定/承诺：到期要能被翻出来 */
};

typedef struct {
    uint32_t id;
    int64_t  t;
    uint32_t access;      /* 被回忆次数 */
    int64_t  last_hit;
    uint32_t hash;
    uint32_t key;         /* "只记一次"的去重键（0 = 不参与去重） */
    uint32_t text_off;
    uint16_t text_len;
    uint8_t  kind;
    uint8_t  salience;    /* 1..9，写入时定，之后只许升 */
    uint8_t  deleted;     /* 墓碑 */
    uint8_t  pinned;      /* 1 = 锚点 */
} zmem_rec;

typedef struct {
    int      items;       /* 有效条数（不含墓碑） */
    int      anchors;
    int      deleted;
    long     bytes;       /* 落盘字节 */
    int64_t  oldest;
    int64_t  newest;
    uint32_t checksum;
    int      stories;     /* 自述版本数 */
} zmem_stat;

typedef struct zmem zmem;

/* 打开（不存在就建）。root_dir 是仓库根；文件落在 data/<character>/memory/ 下。 */
zmem *zmem_open(const char *root_dir, const char *character, zdiag *d);
void  zmem_close(zmem *m);

/* 写入一条。返回 id（>0）；失败返回 0。
 *   kind = ZMEM_ANCHOR 且锚点已满 → 返回 0（**不静默降级成事件**）。
 *   once_key 非空时：同一个键只会写入一次，重复调用返回已有 id（幂等）。 */
uint32_t zmem_add(zmem *m, int64_t t, int kind, int salience,
                  const char *text, const char *once_key);

/* 把已有条目升成锚点（锚点满则返回 0）。 */
int zmem_pin(zmem *m, uint32_t id);
/* 降级锚点：必须给理由（理由会落盘，回答"为什么她不再提这件事"）。 */
int zmem_unpin(zmem *m, uint32_t id, const char *reason);
/* 删除：墓碑，正文保留可审计，但不再被检索、不再进上下文。理由同样落盘。 */
int zmem_del(zmem *m, uint32_t id, const char *reason);
/* 重要性只许升（9 为顶）。降级一律拒绝 —— 那是悄悄篡改。 */
int zmem_salience_up(zmem *m, uint32_t id, int v);

/* 回忆：锚点全带（永不衰减）+ 与 query 相关的 top-K。
 *   没有相关条目时**不硬凑** —— 只在块里写"没有相关记忆，说记不清"。
 *   返回写进 buf 的字节数（0 = 没有任何可带的内容）。 */
size_t zmem_recall(zmem *m, const char *query, int64_t now,
                   char *buf, size_t cap);
/* 只要"相关条目"（锚点由 zmem_anchors_block 单独给）。
   为什么拆成两块：锚点块要被 pin 住（预算再紧也不许裁），
   相关回忆可以被裁 —— 裁掉的是"这次想起来的"，不是"她这个人"。 */
size_t zmem_recall_related(zmem *m, const char *query, int64_t now,
                           char *buf, size_t cap);

/* 只要锚点（给"她一直记得"的常驻块用）。 */
size_t zmem_anchors_block(const zmem *m, int64_t now, char *buf, size_t cap);

/* 自述（版本化）：一次改写必须同时满足
 *   ① 距上一版 >= ZMEM_STORY_GAP；② 与上一版汉字二元组重合度 >= ZMEM_STORY_DRIFT%；
 *   ③ 至少引用一条**真实存在且未删除**的记忆 id。
 *   text 用 "[#12,#34]正文" 的写法带上引用。返回新版号（>0），被拒返回 0。 */
int zmem_story_set(zmem *m, int64_t t, const char *text);
/* 取某一版（version<=0 = 最新）。返回正文长度，0 = 没有。 */
size_t zmem_story_get(const zmem *m, int version, int64_t *t_out,
                      char *out, size_t cap);
int zmem_story_count(const zmem *m);

/* 取一条的正文副本（用于展示/对账）。返回长度，0 = 没有或已删。 */
size_t zmem_text(const zmem *m, uint32_t id, char *out, size_t cap);
int zmem_get(const zmem *m, uint32_t id, zmem_rec *out);

/* 导出片（JSON，给 /api/memory.json）：最多 n 条，按时间倒序；include_deleted=1 时连墓碑一起。 */
size_t zmem_export_json(const zmem *m, char *out, size_t cap, int n, int include_deleted);

void zmem_stats(const zmem *m, zmem_stat *s);
long zmem_get_file_size(const zmem *m);

/* 全量对账：重放一遍，检查 magic/长度/hash/id 连续/锚点上限/自述引用。
 * 返回 0 = 通过；否则返回第一个问题所在的行号（>0），why 里写明原因。 */
int zmem_verify(zmem *m, char *why, size_t cap);

/* 时区偏移（分钟）。日期和"多久以前"必须按用户本地时区算 ——
   否则凌晨 1 点发生的事会被写成前一天的日期，用户一看就知道是假的。
   默认 +480（东八区），可用环境变量 ZMEM_TZ_OFFSET_MIN 覆盖。 */
void zmem_set_tz_offset(int minutes);
int  zmem_tz_offset(void);

/* 把"多少天前"说成人话（"约 4 年前"/"3 天前"）。返回写入长度。 */
size_t zmem_age_text(int64_t t, int64_t now, char *out, size_t cap);
/* unix 秒 → "2026-10-26"（UTC）。 */
size_t zmem_date_text(int64_t t, char *out, size_t cap);

#endif /* ZMEM_H */
