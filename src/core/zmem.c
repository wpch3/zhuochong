/* zmem.c —— 长记忆线的实现。设计理由全在 zmem.h 的文件头，这里只写"怎么落"。 */
#include "zmem.h"

#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "zjson.h"

#define ZMEM_MAGIC 0x31454D5Au   /* 'Z''M''E''1' 小端 */
#define ZMEM_HDR   32
#define ZMEM_MAX_STORY 64

enum { RT_ADD = 1, RT_PIN = 2, RT_DEL = 3, RT_TOUCH = 4, RT_SAL = 5, RT_STORY = 6, RT_UNPIN = 7 };

typedef struct { int version; int64_t t; uint32_t off; uint16_t len; } zmem_story;

struct zmem {
    char      path[1024];
    char      dir[1024];
    FILE     *fp;

    zmem_rec *rec;          /* 下标 i 对应 id = i + 1（id 连续且永不复用） */
    int       n, cap;
    int64_t  *flushed;      /* 上次落盘的 last_hit，用来决定关文件时补不补 TOUCH */

    char     *arena;
    size_t    alen, acap;

    zmem_story story[ZMEM_MAX_STORY];
    int        nstory;

    int       nanchor, ndel;
    uint32_t  checksum;
    int64_t   oldest, newest;
    int       bad_lines;    /* 读盘时跳过的坏记录（>0 必须报出来） */
};

/* ------------------------------------------------------------------ 小工具 */

static uint32_t rd32(const unsigned char *p)
{
    return (uint32_t)p[0] | ((uint32_t)p[1] << 8) | ((uint32_t)p[2] << 16) | ((uint32_t)p[3] << 24);
}
static uint64_t rd64(const unsigned char *p)
{
    uint64_t lo = rd32(p), hi = rd32(p + 4);
    return lo | (hi << 32);
}
static void wr32(unsigned char *p, uint32_t v)
{
    p[0] = (unsigned char)(v & 0xFF); p[1] = (unsigned char)((v >> 8) & 0xFF);
    p[2] = (unsigned char)((v >> 16) & 0xFF); p[3] = (unsigned char)((v >> 24) & 0xFF);
}
static void wr64(unsigned char *p, uint64_t v)
{
    wr32(p, (uint32_t)(v & 0xFFFFFFFFu));
    wr32(p + 4, (uint32_t)(v >> 32));
}

static uint32_t fnv1a(const char *s)
{
    uint32_t h = 2166136261u;
    while (s && *s) { h ^= (unsigned char)*s++; h *= 16777619u; }
    return h;
}

/* UTF-8 解码。返回消耗的字节数（0 = 结束），坏字节按 1 字节跳过。 */
static int u8_next(const char *s, size_t len, size_t *i, uint32_t *cp)
{
    unsigned char c;
    if (*i >= len) return 0;
    c = (unsigned char)s[*i];
    if (c < 0x80) { *cp = c; (*i) += 1; return 1; }
    if ((c & 0xE0) == 0xC0 && *i + 1 < len) {
        *cp = ((uint32_t)(c & 0x1F) << 6) | ((unsigned char)s[*i + 1] & 0x3F);
        *i += 2; return 2;
    }
    if ((c & 0xF0) == 0xE0 && *i + 2 < len) {
        *cp = ((uint32_t)(c & 0x0F) << 12) | (((unsigned char)s[*i + 1] & 0x3F) << 6)
            | ((unsigned char)s[*i + 2] & 0x3F);
        *i += 3; return 3;
    }
    if ((c & 0xF8) == 0xF0 && *i + 3 < len) {
        *cp = ((uint32_t)(c & 0x07) << 18) | (((unsigned char)s[*i + 1] & 0x3F) << 12)
            | (((unsigned char)s[*i + 2] & 0x3F) << 6) | ((unsigned char)s[*i + 3] & 0x3F);
        *i += 4; return 4;
    }
    *cp = c; (*i) += 1; return 1;      /* 坏字节：推进 1，别死循环 */
}

static int is_space_cp(uint32_t c)
{
    return c == ' ' || c == '\t' || c == '\n' || c == '\r'
        || (c >= 0x3000 && c <= 0x303F)          /* 中文标点 */
        || (c >= 0xFF00 && c <= 0xFF65)          /* 全角标点 */
        || c == '.' || c == ',' || c == '!' || c == '?' || c == ';' || c == ':'
        || c == '-' || c == '\'' || c == '"' || c == '(' || c == ')';
}

/* 汉字/字母二元组集合。≤256 个，够用（再多也只影响一点召回率，不影响正确性）。 */
typedef struct { uint32_t v[320]; int n; } bg_set;

static void bg_build(bg_set *b, const char *s)
{
    uint32_t prev = 0, cp;
    int have = 0;
    size_t i = 0, len = s ? strlen(s) : 0;
    b->n = 0;
    while (u8_next(s, len, &i, &cp)) {
        if (cp < 0x80) cp = (uint32_t)(cp | 0x20);     /* ASCII 折成小写 */
        if (is_space_cp(cp)) { have = 0; continue; }
        if (have) {
            uint32_t h = prev * 16777619u ^ cp;
            h *= 16777619u;
            if (b->n < (int)(sizeof b->v / sizeof b->v[0])) b->v[b->n++] = h;
        }
        prev = cp;
        have = 1;
    }
}

static int bg_has(const bg_set *b, uint32_t h)
{
    int i;
    for (i = 0; i < b->n; ++i) if (b->v[i] == h) return 1;
    return 0;
}

/* 两个字符串的二元组重合度（0..100），自述漂移闸要用。 */
static int bg_overlap_pct(const char *a, const char *b)
{
    bg_set A, B;
    int i, inter = 0, uni;
    bg_build(&A, a);
    bg_build(&B, b);
    if (A.n == 0 || B.n == 0) return 0;
    for (i = 0; i < A.n; ++i) if (bg_has(&B, A.v[i])) inter++;
    uni = A.n + B.n - inter;
    return uni > 0 ? (int)(inter * 100 / uni) : 0;
}

/* ------------------------------------------------------------------ 时间 */

static void civil_from_days(int64_t z, int *y, int *m, int *d)
{
    int64_t era, doe, yoe, doy, mp;
    z += 719468;
    era = (z >= 0 ? z : z - 146096) / 146097;
    doe = z - era * 146097;
    yoe = (doe - doe / 1460 + doe / 36524 - doe / 146096) / 365;
    *y = (int)(yoe + era * 400);
    doy = doe - (365 * yoe + yoe / 4 - yoe / 100);
    mp = (5 * doy + 2) / 153;
    *d = (int)(doy - (153 * mp + 2) / 5 + 1);
    *m = (int)(mp < 10 ? mp + 3 : mp - 9);
    if (*m <= 2) (*y)++;
}

static int g_tz_min = 480;          /* 东八区；桌面陪伴的主用户在中国 */
static int g_tz_init = 0;

static void tz_init(void)
{
    const char *e;
    if (g_tz_init) return;
    g_tz_init = 1;
    e = getenv("ZMEM_TZ_OFFSET_MIN");
    if (e && e[0]) {
        int v = atoi(e);
        if (v > -1440 && v < 1440) g_tz_min = v;
    }
}

void zmem_set_tz_offset(int minutes)
{
    tz_init();
    if (minutes > -1440 && minutes < 1440) g_tz_min = minutes;
}

int zmem_tz_offset(void) { tz_init(); return g_tz_min; }

size_t zmem_date_text(int64_t t, char *out, size_t cap)
{
    int y, mo, d;
    int64_t days;
    tz_init();
    t += (int64_t)g_tz_min * 60;      /* 先挪到本地时间再取日期 */
    days = t / 86400;
    civil_from_days(days, &y, &mo, &d);
    return z_snprintf(out, cap, "%04d-%02d-%02d", y, mo, d);
}

size_t zmem_age_text(int64_t t, int64_t now, char *out, size_t cap)
{
    int64_t days = (now - t) / 86400;
    int64_t yrs, mos;
    if (days <= 0)  return z_snprintf(out, cap, "今天");
    if (days == 1)  return z_snprintf(out, cap, "昨天");
    if (days < 30)  return z_snprintf(out, cap, "%d 天前", (int)days);
    if (days < 365) return z_snprintf(out, cap, "%d 个月前", (int)(days / 30));
    yrs = days / 365;
    mos = (days % 365) / 30;
    if (mos <= 0) return z_snprintf(out, cap, "约 %d 年", (int)yrs);
    return z_snprintf(out, cap, "约 %d 年 %d 个月", (int)yrs, (int)mos);
}

/* ------------------------------------------------------------------ 存储 */

static void push_record(zmem *m, int type, uint32_t id, int64_t t,
                        uint32_t aux, uint32_t key, const char *text, size_t len)
{
    unsigned char hdr[ZMEM_HDR];
    if (!m->fp) return;
    if (len > ZMEM_MAX_TEXT) len = ZMEM_MAX_TEXT;
    wr32(hdr + 0, ZMEM_MAGIC);
    wr32(hdr + 4, (uint32_t)(type & 0xFFFF) | ((uint32_t)len << 16));
    wr32(hdr + 8, id);
    wr64(hdr + 12, (uint64_t)t);
    wr32(hdr + 20, fnv1a(text));
    wr32(hdr + 24, aux);
    wr32(hdr + 28, key);
    fwrite(hdr, 1, ZMEM_HDR, m->fp);
    if (len) fwrite(text, 1, len, m->fp);
    fflush(m->fp);
}

/* 按整字截断（绝不切出半个 UTF-8） */
static size_t utf8_prefix(const char *s, size_t cap)
{
    size_t len = strlen(s), i = 0, last = 0;
    uint32_t cp;
    if (len <= cap) return len;
    while (i < len) {
        size_t before = i;
        if (!u8_next(s, len, &i, &cp)) break;
        if (i > cap) return last;
        last = i;
        (void)before;
    }
    return last;
}

static uint32_t arena_put(zmem *m, const char *s, size_t len)
{
    if (m->alen + len + 1 > m->acap) {
        size_t nc = m->acap ? m->acap * 2 : 65536;
        while (nc < m->alen + len + 1) nc *= 2;
        m->arena = (char *)z_realloc(m->arena, nc);
        m->acap = nc;
    }
    memcpy(m->arena + m->alen, s, len);
    m->arena[m->alen + len] = 0;
    {
        uint32_t off = (uint32_t)m->alen;
        m->alen += len + 1;
        return off;
    }
}

static void rec_push(zmem *m, zmem_rec r)
{
    if (m->n >= m->cap) {
        int nc = m->cap ? m->cap * 2 : 1024;
        m->rec = (zmem_rec *)z_realloc(m->rec, (size_t)nc * sizeof(zmem_rec));
        m->flushed = (int64_t *)z_realloc(m->flushed, (size_t)nc * sizeof(int64_t));
        m->cap = nc;
    }
    m->rec[m->n] = r;
    m->flushed[m->n] = r.last_hit;
    m->n++;
}

/* 重放一条记录。返回 0 = 正常；-1 = 结构坏了（调用方决定跳过还是中止）。 */
static int apply_record(zmem *m, int type, uint32_t id, int64_t t, uint32_t aux,
                        uint32_t key, const char *text, size_t len, char *why, size_t whycap)
{
    switch (type) {
    case RT_ADD: {
        zmem_rec r;
        size_t cut;
        if (id == 0 || id > ZMEM_MAX_ITEMS) { z_snprintf(why, whycap, "id %u 越界", id); return -1; }
        if ((int)id != m->n + 1) {
            z_snprintf(why, whycap, "id 不连续：期望 %d 实际 %u", m->n + 1, id);
            return -1;
        }
        cut = utf8_prefix(text, len);      /* 读盘时也再截一次：防手工改坏长度 */
        memset(&r, 0, sizeof r);
        r.id = id;
        r.t = t;
        r.kind = (uint8_t)(aux & 0xFF);
        r.salience = (uint8_t)((aux >> 8) & 0xFF);
        if (r.salience < 1) r.salience = 5;
        if (r.salience > 9) r.salience = 9;
        r.hash = fnv1a(text);
        r.text_off = arena_put(m, text, cut);
        r.text_len = (uint16_t)cut;
        r.key = key;
        r.pinned = (r.kind == ZMEM_ANCHOR);
        rec_push(m, r);
        m->checksum += r.hash;
        if (r.pinned) m->nanchor++;
        if (t > m->newest || m->newest == 0) m->newest = t;
        if (t < m->oldest || m->oldest == 0) m->oldest = t;
        return 0;
    }
    case RT_PIN:
        if (id == 0 || id > (uint32_t)m->n) { z_snprintf(why, whycap, "PIN 指向不存在的 %u", id); return -1; }
        if (!m->rec[id - 1].pinned) { m->rec[id - 1].pinned = 1; m->nanchor++; }
        return 0;
    case RT_DEL:
        if (id == 0 || id > (uint32_t)m->n) { z_snprintf(why, whycap, "DEL 指向不存在的 %u", id); return -1; }
        if (!m->rec[id - 1].deleted) {
            m->rec[id - 1].deleted = 1;
            m->ndel++;
            if (m->rec[id - 1].pinned) { m->rec[id - 1].pinned = 0; m->nanchor--; }
            m->checksum -= m->rec[id - 1].hash;
        }
        return 0;
    case RT_TOUCH:
        if (id == 0 || id > (uint32_t)m->n) return -1;
        m->rec[id - 1].access++;
        if (t > m->rec[id - 1].last_hit) m->rec[id - 1].last_hit = t;
        return 0;
    case RT_SAL:
        if (id == 0 || id > (uint32_t)m->n) return -1;
        if ((int)((aux >> 8) & 0xFF) > m->rec[id - 1].salience)
            m->rec[id - 1].salience = (uint8_t)((aux >> 8) & 0xFF);
        return 0;
    case RT_UNPIN:
        if (id == 0 || id > (uint32_t)m->n) return -1;
        if (m->rec[id - 1].pinned) { m->rec[id - 1].pinned = 0; m->nanchor--; }
        return 0;
    case RT_STORY: {
        if (m->nstory >= ZMEM_MAX_STORY) return -1;
        {
            size_t keep = utf8_prefix(text, len);
            m->story[m->nstory].version = m->nstory + 1;
            m->story[m->nstory].t = t;
            m->story[m->nstory].off = arena_put(m, text, keep);
            m->story[m->nstory].len = (uint16_t)keep;
            m->nstory++;
        }
        return 0;
    }
    default:
        z_snprintf(why, whycap, "未知记录类型 %d", type);
        return -1;
    }
}

static int replay(zmem *m, const unsigned char *buf, size_t len, char *why, size_t whycap)
{
    size_t off = 0;
    int line = 0;
    char local[160];
    while (off + ZMEM_HDR <= len) {
        uint32_t magic = rd32(buf + off);
        uint32_t a = rd32(buf + off + 4);
        uint16_t type = (uint16_t)(a & 0xFFFF);
        uint16_t tlen = (uint16_t)(a >> 16);
        uint32_t id = rd32(buf + off + 8);
        int64_t t = (int64_t)rd64(buf + off + 12);
        uint32_t hash = rd32(buf + off + 20);
        uint32_t aux = rd32(buf + off + 24);
        uint32_t key = rd32(buf + off + 28);
        line++;
        if (magic != ZMEM_MAGIC) {
            z_snprintf(why, whycap, "第 %d 条 magic 不对（0x%08X）—— 文件被改过或不是记忆文件", line, magic);
            return line;
        }
        if (tlen > ZMEM_MAX_TEXT || off + ZMEM_HDR + tlen > len) {
            z_snprintf(why, whycap, "第 %d 条长度 %u 越界（文件尾可能被截断）", line, tlen);
            return line;
        }
        {
            char tmp[ZMEM_MAX_TEXT + 1];
            memcpy(tmp, buf + off + ZMEM_HDR, tlen);
            tmp[tlen] = 0;
            if (hash != fnv1a(tmp)) {
                z_snprintf(why, whycap, "第 %d 条正文校验不过 —— 正文被改过（正文必须不可变）", line);
                return line;
            }
            if (apply_record(m, type, id, t, aux, key, tmp, tlen, local, sizeof local) != 0) {
                z_snprintf(why, whycap, "第 %d 条：%s", line, local);
                return line;
            }
        }
        off += ZMEM_HDR + tlen;
    }
    if (off != len) {
        z_snprintf(why, whycap, "文件尾部有 %d 字节不成记录（截断？）", (int)(len - off));
        return line + 1;
    }
    return 0;
}

zmem *zmem_open(const char *root_dir, const char *character, zdiag *d)
{
    zmem *m = (zmem *)z_calloc(1, sizeof(zmem));
    unsigned char *raw = NULL;
    size_t rawlen = 0;

    z_snprintf(m->dir, sizeof m->dir, "%s/data/%s/memory", root_dir, character);
    z_mkdir_p(m->dir);
    z_snprintf(m->path, sizeof m->path, "%s/chronicle.zm", m->dir);

    if (z_file_exists(m->path)) {
        zerr err;
        zerr_clear(&err);
        raw = (unsigned char *)z_read_file(m->path, &rawlen, &err);
        if (!raw) {
            zdiag_error(d, m->path, 0, 0, "", "记忆文件读不出来：%s", err.msg);
            free(m);
            return NULL;
        }
        {
            char why[192];
            why[0] = 0;
            if (replay(m, raw, rawlen, why, sizeof why) != 0) {
                /* ★ 读不完整**不许当空文件继续跑**：那等于把她的人生清空。
                   报错、把原文件留着、返回 NULL —— 宁可这次起不来。 */
                zdiag_error(d, m->path, 0, 0, "", "记忆文件损坏：%s", why);
                free(raw);
                free(m->rec); free(m->flushed); free(m->arena); free(m);
                return NULL;
            }
        }
        free(raw);
    }

    m->fp = fopen(m->path, "ab");
    if (!m->fp) {
        zdiag_error(d, m->path, 0, 0, "", "记忆文件打不开（没有写权限？）");
        free(m->rec); free(m->flushed); free(m->arena); free(m);
        return NULL;
    }
    return m;
}

void zmem_close(zmem *m)
{
    int i;
    if (!m) return;
    /* 把"被回忆过"落盘：只补有变化的，一次关文件最多写 n 条。 */
    if (m->fp) {
        for (i = 0; i < m->n; ++i) {
            if (m->rec[i].last_hit != m->flushed[i]) {
                push_record(m, RT_TOUCH, m->rec[i].id, m->rec[i].last_hit, 0, 0, "", 0);
                m->flushed[i] = m->rec[i].last_hit;
            }
        }
        fclose(m->fp);
        m->fp = NULL;
    }
    free(m->rec);
    free(m->flushed);
    free(m->arena);
    free(m);
}

/* ------------------------------------------------------------------ 写入 */

uint32_t zmem_add(zmem *m, int64_t t, int kind, int salience,
                  const char *text, const char *once_key)
{
    uint32_t key = once_key && once_key[0] ? fnv1a(once_key) : 0;
    size_t len, cut;
    uint32_t id;

    if (!m || !text || !text[0]) return 0;
    if (m->n >= ZMEM_MAX_ITEMS) return 0;                  /* 拒绝，不覆盖 */
    if (kind == ZMEM_ANCHOR && m->nanchor >= ZMEM_MAX_ANCHORS) return 0;  /* 满了不降级 */

    if (key) {                       /* 幂等：同一个键只写一次（键跟着文件走，另开索引会漂） */
        int i;
        for (i = 0; i < m->n; ++i) {
            if (m->rec[i].key == key && !m->rec[i].deleted) return m->rec[i].id;
        }
    }
    if (kind < 0 || kind > ZMEM_PROMISE) kind = ZMEM_EVENT;
    if (salience < 1) salience = 5;
    if (salience > 9) salience = 9;

    id = (uint32_t)(m->n + 1);
    len = strlen(text);
    cut = utf8_prefix(text, len > ZMEM_MAX_TEXT ? ZMEM_MAX_TEXT : len);
    push_record(m, RT_ADD, id, t, (uint32_t)kind | ((uint32_t)salience << 8),
                key, text, cut);
    {
        char why[96];
        if (apply_record(m, RT_ADD, id, t, (uint32_t)kind | ((uint32_t)salience << 8),
                         key, text, cut, why, sizeof why) != 0)
            return 0;
    }
    return id;
}

int zmem_pin(zmem *m, uint32_t id)
{
    if (!m || id == 0 || id > (uint32_t)m->n) return 0;
    if (m->rec[id - 1].deleted) return 0;
    if (m->rec[id - 1].pinned) return 1;
    if (m->nanchor >= ZMEM_MAX_ANCHORS) return 0;
    push_record(m, RT_PIN, id, m->rec[id - 1].t, 0, 0, "", 0);
    m->rec[id - 1].pinned = 1;
    m->nanchor++;
    return 1;
}

int zmem_unpin(zmem *m, uint32_t id, const char *reason)
{
    if (!m || id == 0 || id > (uint32_t)m->n) return 0;
    if (!m->rec[id - 1].pinned) return 1;
    /* 降级锚点 = 允许她"以后不再提这件事"。正文还在（还能翻出来），
       只是不再占常驻位。理由落盘 —— 以后能回答"为什么她不再提这件事"。 */
    push_record(m, RT_UNPIN, id, m->rec[id - 1].t, 0, 0,
                reason ? reason : "", reason ? utf8_prefix(reason, strlen(reason)) : 0);
    m->rec[id - 1].pinned = 0;
    m->nanchor--;
    return 1;
}

int zmem_del(zmem *m, uint32_t id, const char *reason)
{
    if (!m || id == 0 || id > (uint32_t)m->n) return 0;
    if (m->rec[id - 1].deleted) return 1;
    push_record(m, RT_DEL, id, m->rec[id - 1].t, 0, 0,
                reason ? reason : "", reason ? utf8_prefix(reason, strlen(reason)) : 0);
    if (m->rec[id - 1].pinned) m->nanchor--;
    m->rec[id - 1].pinned = 0;
    m->rec[id - 1].deleted = 1;
    m->ndel++;
    m->checksum -= m->rec[id - 1].hash;
    return 1;
}

int zmem_salience_up(zmem *m, uint32_t id, int v)
{
    if (!m || id == 0 || id > (uint32_t)m->n) return 0;
    if (v < 1) v = 1;
    if (v > 9) v = 9;
    if (v <= m->rec[id - 1].salience) return v == m->rec[id - 1].salience;  /* 降级拒绝 */
    push_record(m, RT_SAL, id, m->rec[id - 1].t, (uint32_t)v << 8, 0, "", 0);
    m->rec[id - 1].salience = (uint8_t)v;
    return 1;
}

/* ------------------------------------------------------------------ 回忆 */

static const char *text_ptr(const zmem *m, const zmem_rec *r)
{
    return m->arena + r->text_off;
}

static double recency_of(int64_t t, int64_t now)
{
    double days = (double)(now - t) / 86400.0;
    if (days < 0) days = 0;
    /* 半衰期 90 天。四年 ≈ 2.7 个半衰期的 16 次方 ≈ 0，所以老事只靠"重要"或"锚点"活下来 */
    return exp(-days / 90.0);
}

/* 相关度：查询的二元组被正文覆盖了多少（0..1） */
static double relevance(const char *query, const char *text)
{
    bg_set Q, T;
    int i, hit = 0;
    bg_build(&Q, query);
    if (Q.n == 0) return 0.0;
    bg_build(&T, text);
    for (i = 0; i < Q.n; ++i) if (bg_has(&T, Q.v[i])) hit++;
    return (double)hit / (double)Q.n;
}

size_t zmem_anchors_block(const zmem *m, int64_t now, char *buf, size_t cap)
{
    size_t len = 0;
    int i, shown = 0, skipped = 0;
    if (!m || !buf || cap < 64) return 0;
    buf[0] = 0;
    for (i = 0; i < m->n; ++i) {
        const zmem_rec *r = &m->rec[i];
        char date[24], age[32], line[512];
        size_t n;
        if (!r->pinned || r->deleted) continue;
        zmem_date_text(r->t, date, sizeof date);
        zmem_age_text(r->t, now, age, sizeof age);
        n = (size_t)z_snprintf(line, sizeof line, "· 一直记得：%s（%s）｜%s\n",
                               date, age, text_ptr(m, r));
        if (len + n + 1 >= cap) { skipped++; continue; }
        memcpy(buf + len, line, n);
        len += n;
        buf[len] = 0;
        shown++;
    }
    if (skipped) {
        char tail[128];
        size_t n = (size_t)z_snprintf(tail, sizeof tail,
                                      "· （还有 %d 条锚点这次没放下 —— 不是没有，是这块地方不够）\n",
                                      skipped);
        if (len + n + 1 < cap) { memcpy(buf + len, tail, n); len += n; buf[len] = 0; }
    }
    (void)shown;
    return len;
}

/* ------------------------------------------------------------ 选取（T67.45 分层召回）
 *
 * 原来的选法是"分数前 K 名"。长跑里当场暴露了问题：
 *   八件礼物散在 0.5~3.9 年之间，用户随口问"你记得我送过你东西吗"，
 *   八条的相关度**全都一样**（共享同一批词），于是分数只由 recency + salience 决定 ——
 *   K=6 个名额被最近六件占满，**最早那两件永远想不起来**。
 *   而"最开始那件事"恰恰是最远的那件。这就是"四年后忘了开头"的机制本身。
 *
 * 改法：先按分数排出候选，再按**年龄桶**限量取（每桶最多 ZMEM_BUCKET_PER 条，
 * 桶 = 0..1 年 / 1..2 年 / 2..3 年 / 3..4 年 / 4 年以上）。
 * 名额没用完时，再按分数从高到低把剩下的补满（不退化成"只看远处"）。
 *
 * 为什么不是"按时间均匀抽样"：那样会把大量又远又不相关的事塞进来，
 * 违反"宁可不带也不硬凑"。分桶只作用在**已经过相关性闸门**的候选上。
 */
#define ZMEM_CAND 64
#define ZMEM_BUCKET_PER 2
#define ZMEM_BUCKETS 5

static int age_bucket(int64_t t, int64_t now)
{
    long long days = (now - t) / 86400;
    long long y;
    if (days < 0) days = 0;
    y = days / 365;
    if (y >= ZMEM_BUCKETS) y = ZMEM_BUCKETS - 1;
    return (int)y;
}

/* 返回选中的条数；idx/sc 按分数从高到低排好（最相关的放最前面，模型读起来也顺）。 */
static int pick_scored(const zmem *m, const char *query, int64_t now,
                       int *idx, double *sc, int cap)
{
    int cand[ZMEM_CAND];
    double csc[ZMEM_CAND];
    int ncand = 0, i, j, picked = 0;
    int bc[ZMEM_BUCKETS];
    int used[ZMEM_CAND];

    for (i = 0; i < ZMEM_BUCKETS; ++i) bc[i] = 0;
    for (i = 0; i < m->n; ++i) {
        const zmem_rec *r = &m->rec[i];
        double rel, s;
        int pos;
        if (r->deleted || r->pinned) continue;      /* 锚点上面已经带了 */
        rel = relevance(query, text_ptr(m, r));
        if (rel < 0.20) continue;                   /* 不够相关：宁可不带，也不硬凑 */
        s = 2.0 * rel + 1.2 * ((double)r->salience / 9.0) + 0.8 * recency_of(r->t, now);
        if (s < 0.45) continue;
        /* 收进候选表（保持降序，满了就顶掉最小的那个） */
        if (ncand == ZMEM_CAND && s <= csc[ncand - 1]) continue;
        pos = ncand < ZMEM_CAND ? ncand : ZMEM_CAND - 1;
        while (pos > 0 && csc[pos - 1] < s) {
            csc[pos] = csc[pos - 1];
            cand[pos] = cand[pos - 1];
            --pos;
        }
        csc[pos] = s;
        cand[pos] = i;
        if (ncand < ZMEM_CAND) ncand++;
    }
    if (ncand == 0) return 0;

    for (i = 0; i < ncand; ++i) used[i] = 0;

    /* 第一轮（保底）：**每个有候选的年龄桶，先保一条，从最老的桶开始**。
       为什么从最老的开始而不是从最好的分数开始：近处的事本来就占便宜
       （recency 项、还有会话历史里刚说过的话），丢了也容易再想起来；
       四年前那一件丢了，就真的再也没有了。所以名额紧的时候，先保远的。 */
    {
        int b;
        for (b = ZMEM_BUCKETS - 1; b >= 0 && picked < cap; --b) {
            for (i = 0; i < ncand; ++i) {
                if (used[i]) continue;
                if (age_bucket(m->rec[cand[i]].t, now) != b) continue;
                idx[picked] = cand[i];
                sc[picked] = csc[i];
                used[i] = 1;
                bc[b]++;
                picked++;
                break;                     /* 这一桶先只保一条 */
            }
        }
    }
    /* 第二轮：剩下的名额按分数补，每桶最多 ZMEM_BUCKET_PER 条（别让某一桶包场） */
    for (i = 0; i < ncand && picked < cap; ++i) {
        int b;
        if (used[i]) continue;
        b = age_bucket(m->rec[cand[i]].t, now);
        if (bc[b] >= ZMEM_BUCKET_PER) continue;
        bc[b]++;
        idx[picked] = cand[i];
        sc[picked] = csc[i];
        used[i] = 1;
        picked++;
    }
    /* 第三轮：桶配额只是"别让某一桶包场"的软约束，不许因此浪费名额 ——
       名额没满就按分数补满（远的事已经在前两轮保过底了）。 */
    for (i = 0; i < ncand && picked < cap; ++i) {
        if (used[i]) continue;
        idx[picked] = cand[i];
        sc[picked] = csc[i];
        picked++;
    }
    /* 追加的是低分项，重排一次，保证块里从最相关排到最不重要 */
    for (i = 1; i < picked; ++i) {
        int ki = idx[i];
        double ks = sc[i];
        for (j = i - 1; j >= 0 && sc[j] < ks; --j) {
            idx[j + 1] = idx[j];
            sc[j + 1] = sc[j];
        }
        idx[j + 1] = ki;
        sc[j + 1] = ks;
    }
    return picked;
}

static size_t recall_impl(zmem *m, const char *query, int64_t now,
                          char *buf, size_t cap, int with_anchors)
{
    size_t len = 0;
    int i, k, picked = 0;
    int idx[ZMEM_RECALL_K];
    double sc[ZMEM_RECALL_K];
    char head[512];   /* ★ 定长缓冲按字节算：这段中文 ~250 字节，160 会把「记不清」切成半个字 */

    if (!m || !buf || cap < 128) return 0;
    buf[0] = 0;

    len += (size_t)z_snprintf(buf + len, cap - len, "【你的记忆·真实发生过的】\n");

    /* ① 锚点：全带，永不衰减。这是"四年后还记得"的唯一可靠来源。 */
    if (with_anchors) {
        size_t n = zmem_anchors_block(m, now, buf + len, cap - len);
        if (n == 0) {
            len += (size_t)z_snprintf(buf + len, cap - len,
                                      "· （还没有任何锚点：这是刚认识，或者记忆文件是新的）\n");
        } else len += n;
    }

    /* ② 相关条目：只在"相关度够高"时才带，不硬凑。
       ★ 选法不是"取分数前 K 名"，而是**按年龄分桶**再取 —— 见下面 pick_scored 的注释。 */
    i = pick_scored(m, query, now, idx, sc, ZMEM_RECALL_K);
    for (k = 0; k < i; ++k) {
        const zmem_rec *r;
        char date[24], age[32], line[512];
        size_t n;
        if (idx[k] < 0) continue;
        r = &m->rec[idx[k]];
        zmem_date_text(r->t, date, sizeof date);
        zmem_age_text(r->t, now, age, sizeof age);
        n = (size_t)z_snprintf(line, sizeof line, "· 想起来过：%s（%s）｜%s\n",
                               date, age, text_ptr(m, r));
        if (len + n + 1 >= cap) break;
        memcpy(buf + len, line, n);
        len += n;
        buf[len] = 0;
        picked++;
        /* 回忆本身只改"被想起过几次"，一个字的正文都不许动。 */
        m->rec[idx[k]].access++;
        if (now > m->rec[idx[k]].last_hit) m->rec[idx[k]].last_hit = now;
    }

    /* ★ 只要相关条目、却一条都没匹配上时：**整块返回空**。
       否则每次无关的闲聊都会往提示词里塞一段"上面这些……"的空话，
       既浪费预算，也会让模型误以为"这次有记忆被翻出来了"。 */
    if (!with_anchors && picked == 0) { buf[0] = 0; return 0; }

    z_snprintf(head, sizeof head,
               "上面这些是引擎从记忆文件里取出的原文，日期和「多久以前」也是引擎算的。\n"
               "没列在这里的事，就是真的没有记录：说「记不清了」「我没什么印象」，"
               "不许编一个细节来填。\n");
    if (len + strlen(head) + 1 < cap) { memcpy(buf + len, head, strlen(head)); len += strlen(head); buf[len] = 0; }
    return len;
}

size_t zmem_recall(zmem *m, const char *query, int64_t now, char *buf, size_t cap)
{
    return recall_impl(m, query, now, buf, cap, 1);
}

size_t zmem_recall_related(zmem *m, const char *query, int64_t now, char *buf, size_t cap)
{
    return recall_impl(m, query, now, buf, cap, 0);
}

/* ------------------------------------------------------------------ 自述 */

/* "[#12,#34]正文" → 摘出引用 id，返回正文起点 */
static const char *story_parse(const char *text, uint32_t *ids, int *nid)
{
    const char *p = text;
    *nid = 0;
    if (!text || text[0] != '[') return text;
    p = text + 1;
    while (*p && *p != ']' && *nid < 8) {
        if (*p == '#') {
            uint32_t v = 0;
            ++p;
            while (*p >= '0' && *p <= '9') { v = v * 10 + (uint32_t)(*p - '0'); ++p; }
            if (v) ids[(*nid)++] = v;
        } else ++p;
    }
    if (*p == ']') ++p;
    return p;
}

int zmem_story_set(zmem *m, int64_t t, const char *text)
{
    uint32_t ids[8];
    int nid = 0, i;
    const char *body;
    size_t blen;
    if (!m || !text || !text[0]) return 0;
    if (m->nstory >= ZMEM_MAX_STORY) return 0;
    body = story_parse(text, ids, &nid);

    if (nid == 0) return 0;                     /* ③ 必须引用真实记忆，不许凭空抒情 */
    for (i = 0; i < nid; ++i) {
        if (ids[i] == 0 || ids[i] > (uint32_t)m->n) return 0;
        if (m->rec[ids[i] - 1].deleted) return 0;
    }
    if (m->nstory > 0) {
        const zmem_story *prev = &m->story[m->nstory - 1];
        const char *ptext = m->arena + prev->off;
        /* ① 间隔：自述改得太勤 = 人格在抖 */
        if (t - prev->t < ZMEM_STORY_GAP) return 0;
        /* ② 漂移：和上一版要有足够重合，否则是"换了个人" */
        if (bg_overlap_pct(body, ptext) < ZMEM_STORY_DRIFT) return 0;
    }
    blen = utf8_prefix(body, strlen(body) > ZMEM_MAX_TEXT ? ZMEM_MAX_TEXT : strlen(body));
    push_record(m, RT_STORY, (uint32_t)(m->nstory + 1), t, 0, 0, body, blen);
    m->story[m->nstory].version = m->nstory + 1;
    m->story[m->nstory].t = t;
    m->story[m->nstory].off = arena_put(m, body, blen);
    m->story[m->nstory].len = (uint16_t)blen;
    m->nstory++;
    return m->nstory;
}

size_t zmem_story_get(const zmem *m, int version, int64_t *t_out, char *out, size_t cap)
{
    const zmem_story *s;
    size_t n;
    if (!m || m->nstory == 0) return 0;
    if (version <= 0) version = m->nstory;
    if (version > m->nstory) return 0;
    s = &m->story[version - 1];
    n = s->len < cap - 1 ? s->len : cap - 1;
    memcpy(out, m->arena + s->off, n);
    out[n] = 0;
    if (t_out) *t_out = s->t;
    return n;
}

int zmem_story_count(const zmem *m) { return m ? m->nstory : 0; }

/* ------------------------------------------------------------------ 查询 */

size_t zmem_text(const zmem *m, uint32_t id, char *out, size_t cap)
{
    const zmem_rec *r;
    size_t n;
    if (!m || id == 0 || id > (uint32_t)m->n || !out || cap == 0) return 0;
    r = &m->rec[id - 1];
    if (r->deleted) return 0;
    n = r->text_len < cap - 1 ? r->text_len : cap - 1;
    memcpy(out, m->arena + r->text_off, n);
    out[n] = 0;
    return n;
}

int zmem_get(const zmem *m, uint32_t id, zmem_rec *out)
{
    if (!m || id == 0 || id > (uint32_t)m->n) return 0;
    if (out) *out = m->rec[id - 1];
    return 1;
}

void zmem_stats(const zmem *m, zmem_stat *s)
{
    long fsz = 0;
    FILE *f;
    if (!s) return;
    memset(s, 0, sizeof *s);
    if (!m) return;
    s->items = m->n - m->ndel;
    s->anchors = m->nanchor;
    s->deleted = m->ndel;
    s->oldest = m->oldest;
    s->newest = m->newest;
    s->checksum = m->checksum;
    s->stories = m->nstory;
    f = fopen(m->path, "rb");
    if (f) { fseek(f, 0, SEEK_END); fsz = ftell(f); fclose(f); }
    s->bytes = fsz;
}

long zmem_get_file_size(const zmem *m)
{
    long fsz = 0;
    FILE *f;
    if (!m) return 0;
    f = fopen(m->path, "rb");
    if (f) { fseek(f, 0, SEEK_END); fsz = ftell(f); fclose(f); }
    return fsz;
}

size_t zmem_export_json(const zmem *m, char *out, size_t cap, int n, int include_deleted)
{
    size_t len = 0;
    int i, shown = 0;
    if (!m || !out || cap == 0) return 0;
    out[0] = 0;
    len += (size_t)z_snprintf(out + len, cap - len, "{\"items\":[");
    for (i = m->n - 1; i >= 0 && shown < n; --i) {
        const zmem_rec *r = &m->rec[i];
        char esc[1024], date[24];
        if (r->deleted && !include_deleted) continue;
        zjson_escape(text_ptr(m, r), esc, sizeof esc);
        zmem_date_text(r->t, date, sizeof date);
        len += (size_t)z_snprintf(out + len, cap - len,
                                  "%s{\"id\":%u,\"date\":\"%s\",\"t\":%lld,\"kind\":%u,"
                                  "\"salience\":%u,\"pinned\":%d,\"deleted\":%d,"
                                  "\"access\":%u,\"text\":\"%s\"}",
                                  shown ? "," : "", r->id, date, (long long)r->t,
                                  (unsigned)r->kind, (unsigned)r->salience,
                                  (int)r->pinned, (int)r->deleted, (unsigned)r->access, esc);
        shown++;
    }
    len += (size_t)z_snprintf(out + len, cap - len, "],\"shown\":%d}", shown);
    return len;
}

int zmem_verify(zmem *m, char *why, size_t cap)
{
    zmem tmp;
    unsigned char *raw;
    size_t rawlen = 0;
    int line;
    zerr err;
    if (!m) return -1;
    if (!z_file_exists(m->path)) return 0;
    zerr_clear(&err);
    raw = (unsigned char *)z_read_file(m->path, &rawlen, &err);
    if (!raw) { z_snprintf(why, cap, "读不出来：%s", err.msg); return -1; }
    memset(&tmp, 0, sizeof tmp);
    line = replay(&tmp, raw, rawlen, why, cap);
    free(raw);
    if (line != 0) {
        free(tmp.rec); free(tmp.flushed); free(tmp.arena);
        return line;
    }
    if (tmp.nanchor > ZMEM_MAX_ANCHORS) {
        z_snprintf(why, cap, "锚点 %d 条超过上限 %d", tmp.nanchor, ZMEM_MAX_ANCHORS);
        free(tmp.rec); free(tmp.flushed); free(tmp.arena);
        return -2;
    }
    if (tmp.n != m->n || tmp.nanchor != m->nanchor || tmp.ndel != m->ndel) {
        z_snprintf(why, cap, "重放结果与内存不一致（%d/%d vs %d/%d）",
                   tmp.n, tmp.nanchor, m->n, m->nanchor);
        free(tmp.rec); free(tmp.flushed); free(tmp.arena);
        return -3;
    }
    free(tmp.rec); free(tmp.flushed); free(tmp.arena);
    return 0;
}
