/* zctx —— 统一上下文管理器（T60.1）。接口说明见 zctx.h。 */
#include "zctx.h"
#include "zc.h"

#include <stdlib.h>
#include <string.h>
#include <stdio.h>

long zctx_est_tokens(const char *s)
{
    size_t n = s ? strlen(s) : 0;
    return (long)(n / 4 + 1);
}

void zctx_init(zctx *c)
{
    if (!c) return;
    memset(c, 0, sizeof(*c));
}

void zctx_free(zctx *c)
{
    int i;
    if (!c) return;
    for (i = 0; i < c->nblocks; ++i) {
        free(c->blocks[i].text);
        c->blocks[i].text = NULL;
    }
    c->nblocks = 0;
}

int zctx_set_block(zctx *c, const char *id, const char *title,
                   const char *source, const char *text,
                   int priority, int pinned)
{
    int i, slot = -1;
    size_t len;
    char *copy;

    if (!c || !id || !*id) return -1;
    for (i = 0; i < c->nblocks; ++i)
        if (z_streq(c->blocks[i].id, id)) { slot = i; break; }
    if (slot < 0) {
        if (c->nblocks >= ZCTX_MAX_BLOCKS) return -1;
        slot = c->nblocks++;
        memset(&c->blocks[slot], 0, sizeof(c->blocks[slot]));
    } else {
        free(c->blocks[slot].text);
        c->blocks[slot].text = NULL;
    }

    len = text ? strlen(text) : 0;
    copy = (char *)malloc(len + 1);
    if (!copy) { /* 位子已经占了，留个空块总比半块强 */
        c->blocks[slot].len = 0;
        return -1;
    }
    if (len) memcpy(copy, text, len);
    copy[len] = 0;

    z_strlcpy(c->blocks[slot].id, id, sizeof(c->blocks[slot].id));
    z_strlcpy(c->blocks[slot].title, title ? title : id, sizeof(c->blocks[slot].title));
    z_strlcpy(c->blocks[slot].source, source ? source : "", sizeof(c->blocks[slot].source));
    c->blocks[slot].text     = copy;
    c->blocks[slot].len      = len;
    c->blocks[slot].tokens   = zctx_est_tokens(copy);
    c->blocks[slot].priority = priority;
    c->blocks[slot].pinned   = pinned ? 1 : 0;
    c->blocks[slot].kept     = 1;
    c->blocks[slot].drop_reason[0] = 0;
    return 0;
}

void zctx_push_turn(zctx *c, int role, const char *text, int sensitive)
{
    zctx_turn *t;
    int idx;
    if (!c || !text) return;

    if (c->nturns < ZCTX_MAX_TURNS) {
        idx = (c->head + c->nturns) % ZCTX_MAX_TURNS;
        c->nturns++;
    } else {
        /* 满了：盖掉最旧的那轮，起点往前挪一格 */
        idx = c->head;
        c->head = (c->head + 1) % ZCTX_MAX_TURNS;
    }
    t = &c->turns[idx];
    t->role = role ? 1 : 0;
    t->sensitive = sensitive ? 1 : 0;
    z_strlcpy(t->text, text, sizeof(t->text));
}

void zctx_clear_turns(zctx *c)
{
    if (!c) return;
    c->nturns = 0;
    c->head = 0;
    c->last_turns_total = 0;
    c->last_turns_used = 0;
    c->last_turns_dropped = 0;
    c->last_turns_held = 0;
}

int zctx_turn_count(const zctx *c) { return c ? c->nturns : 0; }

const zctx_turn *zctx_turn_at(const zctx *c, int i)
{
    if (!c || i < 0 || i >= c->nturns) return NULL;
    return &c->turns[(c->head + i) % ZCTX_MAX_TURNS];
}

int zctx_block_count(const zctx *c) { return c ? c->nblocks : 0; }

const zctx_block *zctx_block_at(const zctx *c, int i)
{
    if (!c || i < 0 || i >= c->nblocks) return NULL;
    return &c->blocks[i];
}

const zctx_block *zctx_block_find(const zctx *c, const char *id)
{
    int i;
    if (!c || !id) return NULL;
    for (i = 0; i < c->nblocks; ++i)
        if (z_streq(c->blocks[i].id, id)) return &c->blocks[i];
    return NULL;
}

/* ---- 组装 ----
 *
 * 顺序是刻意的：
 *   ① 先按目的地过滤敏感轮次（安全第一，不受预算影响）
 *   ② 再放 pinned 块（人设）
 *   ③ 再按优先级从高到低放其余块
 *   ④ 最后用剩下的预算从**最新**往回收会话历史
 *
 * ④ 为什么从最新往回：对话里最近几轮最有用。预算紧张时宁可忘掉很久以前，
 * 也不能把"你刚说的那句"丢了 —— 那是用户最能察觉的失忆。
 */
long zctx_build(zctx *c, const char *cap, long budget_tokens, int local)
{
    long used = 0;
    int i;
    int kept_turns = 0, dropped = 0, held = 0;

    if (!c) return 0;
    z_strlcpy(c->last_cap, cap ? cap : "chat.completion", sizeof(c->last_cap));
    c->last_budget = budget_tokens;
    c->last_local  = local ? 1 : 0;

    /* ② pinned 先占位：它们不参与裁剪，但要算进已用预算 */
    for (i = 0; i < c->nblocks; ++i) {
        zctx_block *b = &c->blocks[i];
        b->kept = 0;
        b->drop_reason[0] = 0;
        if (b->pinned) {
            b->kept = 1;
            used += b->tokens;
        }
    }

    /* ③ 其余块按 priority 从大到小放，放不下就标原因。
       这里用朴素的选择式遍历 —— 块最多 16 个，不值得上排序。 */
    for (;;) {
        int best = -1;
        for (i = 0; i < c->nblocks; ++i) {
            zctx_block *b = &c->blocks[i];
            if (b->pinned || b->kept || b->drop_reason[0]) continue;
            if (best < 0 || b->priority > c->blocks[best].priority) best = i;
        }
        if (best < 0) break;
        {
            zctx_block *b = &c->blocks[best];
            if (budget_tokens > 0 && used + b->tokens > budget_tokens) {
                z_snprintf(b->drop_reason, sizeof(b->drop_reason),
                           "预算不够（还差 %ld token）",
                           (long)(used + b->tokens - budget_tokens));
                b->kept = 0;
            } else {
                b->kept = 1;
                used += b->tokens;
            }
        }
    }

    /* ④ 会话历史：从最新往回收，直到预算用完。
       同时按目的地挡下敏感轮次 —— 这一条**先于预算**判，
       因为"装不下"可以商量，"不许出门"不能商量。 */
    for (i = c->nturns - 1; i >= 0; --i) {
        const zctx_turn *t = zctx_turn_at(c, i);
        long tk;
        if (!t) continue;
        if (t->sensitive && !local) { held++; continue; }
        tk = zctx_est_tokens(t->text);
        if (budget_tokens > 0 && used + tk > budget_tokens) { dropped++; continue; }
        used += tk;
        kept_turns++;
    }

    c->last_turns_total   = c->nturns;
    c->last_tokens        = used;
    c->last_turns_used    = kept_turns;
    c->last_turns_dropped = dropped;
    c->last_turns_held    = held;
    return used;
}

/* 上次 build 判定要带上的历史：按时间顺序第 i 条。
   重新走一遍和 zctx_build ④ 一样的判据 —— 两处判据必须一致，
   所以这里刻意不缓存索引表：缓存会和 build 的逻辑漂移，
   而漂移的后果是"清单上说带了、实际没带"，那比不带更糟。 */
static int kept_turn_index(const zctx *c, int want, const zctx_turn **out)
{
    long used = 0;
    int i, n = 0;
    int first;
    if (!c) return 0;

    /* 先把块占掉的预算算回来 */
    for (i = 0; i < c->nblocks; ++i)
        if (c->blocks[i].kept) used += c->blocks[i].tokens;

    /* 从最新往回扫，记下最旧那条能留下的位置 */
    first = c->nturns;
    for (i = c->nturns - 1; i >= 0; --i) {
        const zctx_turn *t = zctx_turn_at(c, i);
        long tk;
        if (!t) continue;
        if (t->sensitive && !c->last_local) continue;
        tk = zctx_est_tokens(t->text);
        if (c->last_budget > 0 && used + tk > c->last_budget) continue;
        used += tk;
        first = i;
    }
    /* 再从 first 正着数，跳过被挡下的敏感轮 */
    for (i = first; i < c->nturns; ++i) {
        const zctx_turn *t = zctx_turn_at(c, i);
        if (!t) continue;
        if (t->sensitive && !c->last_local) continue;
        if (n == want) { if (out) *out = t; return 1; }
        n++;
    }
    if (out) *out = NULL;
    return 0;
}

const zctx_turn *zctx_kept_turn_at(const zctx *c, int i)
{
    const zctx_turn *t = NULL;
    if (i < 0) return NULL;
    kept_turn_index(c, i, &t);
    return t;
}

int zctx_kept_turn_count(const zctx *c)
{
    int n = 0;
    while (zctx_kept_turn_at(c, n)) n++;
    return n;
}

/* 注意：清单描述的是**上一次 zctx_build 那一刻**的状态，不是"现在"。
   两者必须分清 —— 混着打印的话，拿两张清单去 diff 会得出假结论
   （实测踩过：历史里已经多了两轮，清单却还按旧的算，"共 4 轮带上 2 轮"
   看起来像裁剪生效了，其实只是两个数来自两个时刻）。 */
size_t zctx_manifest(const zctx *c, char *out, size_t cap)
{
    char *p = out;
    int i;
    if (!out || cap == 0) return 0;
    out[0] = 0;
    if (!c) return 0;

    {
        char bud[32];
        if (c->last_budget > 0) z_snprintf(bud, sizeof(bud), "%ld token", c->last_budget);
        else                    z_strlcpy(bud, "不限", sizeof(bud));
        p += z_snprintf(p, cap - (size_t)(p - out),
                        "上下文清单  能力=%s  目的地=%s  预算=%s\n",
                        c->last_cap[0] ? c->last_cap : "(没组装过)",
                        c->last_local ? "本地模型" : "云端", bud);
    }

    for (i = 0; i < c->nblocks; ++i) {
        const zctx_block *b = &c->blocks[i];
        p += z_snprintf(p, cap - (size_t)(p - out),
                        "  [%s] %-10s %-12s %6lu 字节 ~%4ld token  来源 %s%s%s\n",
                        b->kept ? "带上" : "裁掉",
                        b->id, b->title, (unsigned long)b->len, b->tokens,
                        b->source[0] ? b->source : "-",
                        b->drop_reason[0] ? "  ← " : "",
                        b->drop_reason);
    }

    p += z_snprintf(p, cap - (size_t)(p - out),
                    "  [%s] %-10s %-12s 共 %d 轮，带上 %d 轮",
                    c->last_turns_used > 0 ? "带上" : "裁掉",
                    "session", "当前会话",
                    c->last_turns_total, c->last_turns_used);
    if (c->last_turns_dropped > 0)
        p += z_snprintf(p, cap - (size_t)(p - out),
                        "，预算不够丢了 %d 轮", c->last_turns_dropped);
    /* 这一行是隐私的凭证：被挡下的轮数必须露出来，
       否则"她好像忘了刚才说的"会被当成 bug，而其实是保护生效了。 */
    if (c->last_turns_held > 0)
        p += z_snprintf(p, cap - (size_t)(p - out),
                        "，**%d 轮带隐私标记没上云**", c->last_turns_held);
    p += z_snprintf(p, cap - (size_t)(p - out), "\n");

    p += z_snprintf(p, cap - (size_t)(p - out),
                    "  合计 ~%ld token\n", c->last_tokens);
    return (size_t)(p - out);
}
