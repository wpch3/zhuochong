/* zjson.c - JSON 解析与生成实现 */
#include "zjson.h"
#include <math.h>
#include <ctype.h>

/* ================================================================ 解析器 */
typedef struct {
    const char *p;      /* 当前字符 */
    const char *start;  /* 文本起点 */
    const char *src;    /* 源名（诊断用） */
    int line, col;      /* 当前位置（1 基） */
    zerr *err;
    int failed;
    zrand rng_unused;
} jparse;

static void jp_advance(jparse *jp)
{
    if (*jp->p == '\n') { jp->line++; jp->col = 1; }
    else { jp->col++; }
    jp->p++;
}

static void jp_error(jparse *jp, const char *fmt, ...)
{
    va_list ap;
    if (jp->failed) return;
    jp->failed = 1;
    if (!jp->err) return;
    zerr_clear(jp->err);
    z_strlcpy(jp->err->file, jp->src ? jp->src : "<json>", sizeof(jp->err->file));
    jp->err->line = jp->line;
    jp->err->col = jp->col;
    va_start(ap, fmt);
    vsnprintf(jp->err->msg, sizeof(jp->err->msg), fmt, ap);
    va_end(ap);
}

static void jp_skip_ws(jparse *jp)
{
    for (;;) {
        char c = *jp->p;
        if (c == ' ' || c == '\t' || c == '\r' || c == '\n') { jp_advance(jp); continue; }
        /* 支持 UTF-8 BOM */
        if ((unsigned char)c == 0xEF && (unsigned char)jp->p[1] == 0xBB &&
            (unsigned char)jp->p[2] == 0xBF) { jp->p += 3; jp->col += 3; continue; }
        if (c == '/' && jp->p[1] == '/') {
            while (*jp->p && *jp->p != '\n') jp_advance(jp);
            continue;
        }
        if (c == '/' && jp->p[1] == '*') {
            jp_advance(jp); jp_advance(jp);
            while (*jp->p && !(*jp->p == '*' && jp->p[1] == '/')) jp_advance(jp);
            if (*jp->p) { jp_advance(jp); jp_advance(jp); }
            continue;
        }
        break;
    }
}

static zjson *jnew(zjson_type t, int line, int col)
{
    zjson *j = (zjson *)z_calloc(1, sizeof(zjson));
    j->type = t;
    j->line = line;
    j->col = col;
    return j;
}

void zjson_free(zjson *j)
{
    int i;
    if (!j) return;
    if (j->sval) free(j->sval);
    for (i = 0; i < j->count; ++i) {
        zjson_free(j->items[i]);
        if (j->keys) free(j->keys[i]);
    }
    free(j->items);
    free(j->keys);
    free(j);
}

/* 追加元素；键可为 NULL（数组） */
static void jpush(zjson *parent, char *key, zjson *child)
{
    if (parent->count >= parent->cap) {
        parent->cap = parent->cap ? parent->cap * 2 : 8;
        parent->items = (zjson **)z_realloc(parent->items, sizeof(zjson *) * (size_t)parent->cap);
        if (parent->type == ZJSON_OBJ)
            parent->keys = (char **)z_realloc(parent->keys, sizeof(char *) * (size_t)parent->cap);
    }
    if (parent->type == ZJSON_OBJ) parent->keys[parent->count] = key;
    parent->items[parent->count] = child;
    parent->count++;
}

static void utf8_put(char *out, size_t cap, size_t *n, unsigned cp)
{
    if (cp < 0x80) {
        if (*n + 1 < cap) out[(*n)++] = (char)cp;
    } else if (cp < 0x800) {
        if (*n + 2 < cap) {
            out[(*n)++] = (char)(0xC0 | (cp >> 6));
            out[(*n)++] = (char)(0x80 | (cp & 0x3F));
        }
    } else if (cp < 0x10000) {
        if (*n + 3 < cap) {
            out[(*n)++] = (char)(0xE0 | (cp >> 12));
            out[(*n)++] = (char)(0x80 | ((cp >> 6) & 0x3F));
            out[(*n)++] = (char)(0x80 | (cp & 0x3F));
        }
    } else {
        if (*n + 4 < cap) {
            out[(*n)++] = (char)(0xF0 | (cp >> 18));
            out[(*n)++] = (char)(0x80 | ((cp >> 12) & 0x3F));
            out[(*n)++] = (char)(0x80 | ((cp >> 6) & 0x3F));
            out[(*n)++] = (char)(0x80 | (cp & 0x3F));
        }
    }
}

static int hex4(const char *p, unsigned *out)
{
    int i; unsigned v = 0;
    for (i = 0; i < 4; ++i) {
        char c = p[i];
        v <<= 4;
        if (c >= '0' && c <= '9') v |= (unsigned)(c - '0');
        else if (c >= 'a' && c <= 'f') v |= (unsigned)(c - 'a' + 10);
        else if (c >= 'A' && c <= 'F') v |= (unsigned)(c - 'A' + 10);
        else return 0;
    }
    *out = v;
    return 1;
}

/* 解析字符串字面量（jp->p 指向开引号） */
static char *jparse_string(jparse *jp)
{
    size_t cap = 32, n = 0;
    char *out;
    if (*jp->p != '"') { jp_error(jp, "期望字符串起始的引号"); return NULL; }
    jp_advance(jp);
    out = (char *)z_alloc(cap);
    while (*jp->p && *jp->p != '"') {
        char c = *jp->p;
        if (n + 8 >= cap) { cap *= 2; out = (char *)z_realloc(out, cap); }
        if (c == '\\') {
            jp_advance(jp);
            switch (*jp->p) {
                case '"':  out[n++] = '"';  jp_advance(jp); break;
                case '\\': out[n++] = '\\'; jp_advance(jp); break;
                case '/':  out[n++] = '/';  jp_advance(jp); break;
                case 'b':  out[n++] = '\b'; jp_advance(jp); break;
                case 'f':  out[n++] = '\f'; jp_advance(jp); break;
                case 'n':  out[n++] = '\n'; jp_advance(jp); break;
                case 'r':  out[n++] = '\r'; jp_advance(jp); break;
                case 't':  out[n++] = '\t'; jp_advance(jp); break;
                case 'u': {
                    unsigned cp = 0;
                    jp_advance(jp);
                    if (!hex4(jp->p, &cp)) { jp_error(jp, "\\u 转义需要 4 位十六进制"); free(out); return NULL; }
                    jp->p += 4; jp->col += 4;
                    if (cp >= 0xD800 && cp <= 0xDBFF && jp->p[0] == '\\' && jp->p[1] == 'u') {
                        unsigned lo = 0;
                        if (hex4(jp->p + 2, &lo) && lo >= 0xDC00 && lo <= 0xDFFF) {
                            cp = 0x10000 + ((cp - 0xD800) << 10) + (lo - 0xDC00);
                            jp->p += 6; jp->col += 6;
                        }
                    }
                    utf8_put(out, cap, &n, cp);
                    break;
                }
                default:
                    jp_error(jp, "非法转义字符 '\\%c'", isprint((unsigned char)*jp->p) ? *jp->p : '?');
                    free(out);
                    return NULL;
            }
        } else if ((unsigned char)c < 0x20) {
            jp_error(jp, "字符串中出现未转义的控制字符 (0x%02X)", (unsigned char)c);
            free(out);
            return NULL;
        } else {
            out[n++] = c;
            jp_advance(jp);
        }
    }
    if (*jp->p != '"') { jp_error(jp, "字符串没有闭合的引号"); free(out); return NULL; }
    jp_advance(jp);
    out[n] = 0;
    return out;
}

static zjson *jparse_value(jparse *jp);

static zjson *jparse_array(jparse *jp)
{
    zjson *arr = jnew(ZJSON_ARR, jp->line, jp->col);
    jp_advance(jp); /* [ */
    jp_skip_ws(jp);
    if (*jp->p == ']') { jp_advance(jp); return arr; }
    for (;;) {
        zjson *v;
        jp_skip_ws(jp);
        if (*jp->p == ']') { jp_advance(jp); break; }   /* 容忍尾随逗号 */
        v = jparse_value(jp);
        if (!v) { zjson_free(arr); return NULL; }
        jpush(arr, NULL, v);
        jp_skip_ws(jp);
        if (*jp->p == ',') { jp_advance(jp); continue; }
        if (*jp->p == ']') { jp_advance(jp); break; }
        jp_error(jp, "数组中期望 ',' 或 ']'，实际为 '%c'", *jp->p ? *jp->p :  '\0');
        zjson_free(arr);
        return NULL;
    }
    return arr;
}

static zjson *jparse_object(jparse *jp)
{
    zjson *obj = jnew(ZJSON_OBJ, jp->line, jp->col);
    jp_advance(jp); /* { */
    jp_skip_ws(jp);
    if (*jp->p == '}') { jp_advance(jp); return obj; }
    for (;;) {
        char *key;
        zjson *v;
        jp_skip_ws(jp);
        if (*jp->p == '}') { jp_advance(jp); break; }   /* 容忍尾随逗号 */
        key = jparse_string(jp);
        if (!key) { zjson_free(obj); return NULL; }
        jp_skip_ws(jp);
        if (*jp->p != ':') {
            jp_error(jp, "对象键 '%s' 后缺少 ':'", key);
            free(key);
            zjson_free(obj);
            return NULL;
        }
        jp_advance(jp);
        jp_skip_ws(jp);
        v = jparse_value(jp);
        if (!v) { free(key); zjson_free(obj); return NULL; }
        jpush(obj, key, v);
        jp_skip_ws(jp);
        if (*jp->p == ',') { jp_advance(jp); continue; }
        if (*jp->p == '}') { jp_advance(jp); break; }
        jp_error(jp, "对象中期望 ',' 或 '}'，实际为 '%c'", *jp->p ? *jp->p :  '\0');
        zjson_free(obj);
        return NULL;
    }
    return obj;
}

static zjson *jparse_number(jparse *jp)
{
    char buf[64];
    size_t n = 0;
    const char *q = jp->p;
    int is_num = 0;
    zjson *v;
    while (*q && n < sizeof(buf) - 1) {
        char c = *q;
        if ((c >= '0' && c <= '9') || c == '-' || c == '+' || c == '.' ||
            c == 'e' || c == 'E') { buf[n++] = c; q++; is_num = 1; }
        else break;
    }
    buf[n] = 0;
    if (!is_num) { jp_error(jp, "非法数字"); return NULL; }
    {
        char *endp = NULL;
        double d = strtod(buf, &endp);
        if (endp && *endp) { jp_error(jp, "非法数字 '%s'", buf); return NULL; }
        v = jnew(ZJSON_NUM, jp->line, jp->col);
        v->num = d;
    }
    jp->p = q;
    jp->col += (int)n;
    return v;
}

static zjson *jparse_value(jparse *jp)
{
    jp_skip_ws(jp);
    switch (*jp->p) {
        case '{': return jparse_object(jp);
        case '[': return jparse_array(jp);
        case '"': {
            char *s = jparse_string(jp);
            zjson *v;
            if (!s) return NULL;
            v = jnew(ZJSON_STR, jp->line, jp->col);
            v->sval = s;
            return v;
        }
        case 't':
            if (strncmp(jp->p, "true", 4) == 0) {
                zjson *v = jnew(ZJSON_BOOL, jp->line, jp->col);
                v->bval = 1; jp->p += 4; jp->col += 4; return v;
            }
            jp_error(jp, "非法字面量（期望 true）");
            return NULL;
        case 'f':
            if (strncmp(jp->p, "false", 5) == 0) {
                zjson *v = jnew(ZJSON_BOOL, jp->line, jp->col);
                v->bval = 0; jp->p += 5; jp->col += 5; return v;
            }
            jp_error(jp, "非法字面量（期望 false）");
            return NULL;
        case 'n':
            if (strncmp(jp->p, "null", 4) == 0) {
                zjson *v = jnew(ZJSON_NULL, jp->line, jp->col);
                jp->p += 4; jp->col += 4; return v;
            }
            jp_error(jp, "非法字面量（期望 null）");
            return NULL;
        default:
            if (*jp->p == '-' || (*jp->p >= '0' && *jp->p <= '9')) return jparse_number(jp);
            jp_error(jp, "意外的字符 '%c'（0x%02X）", isprint((unsigned char)*jp->p) ? *jp->p : '?',
                     (unsigned char)*jp->p);
            return NULL;
    }
}

zjson *zjson_parse(const char *text, const char *src_name, zerr *err)
{
    jparse jp;
    zjson *root;
    if (err) zerr_clear(err);
    if (!text) {
        if (err) zerr_set(err, src_name ? src_name : "<json>", 0, 0, "", "输入为空");
        return NULL;
    }
    memset(&jp, 0, sizeof(jp));
    jp.p = text; jp.start = text; jp.src = src_name; jp.line = 1; jp.col = 1; jp.err = err;
    root = jparse_value(&jp);
    if (!root) return NULL;
    jp_skip_ws(&jp);
    if (*jp.p) {
        jp_error(&jp, "文档结尾后出现多余内容");
        zjson_free(root);
        return NULL;
    }
    return root;
}

zjson *zjson_parse_file(const char *path, zerr *err)
{
    size_t len = 0;
    char *text = z_read_file(path, &len, err);
    zjson *j;
    if (!text) return NULL;
    j = zjson_parse(text, path, err);
    free(text);
    return j;
}

/* ================================================================ 访问 */
zjson_type zjson_type_of(const zjson *j) { return j ? j->type : ZJSON_NULL; }

const char *zjson_type_name(zjson_type t)
{
    switch (t) {
        case ZJSON_NULL: return "null";
        case ZJSON_BOOL: return "bool";
        case ZJSON_NUM:  return "number";
        case ZJSON_STR:  return "string";
        case ZJSON_ARR:  return "array";
        case ZJSON_OBJ:  return "object";
        default: return "?";
    }
}

int zjson_is(const zjson *j, zjson_type t) { return j && j->type == t; }

size_t zjson_count(const zjson *j)
{
    if (!j) return 0;
    if (j->type != ZJSON_ARR && j->type != ZJSON_OBJ) return 0;
    return (size_t)j->count;
}

zjson *zjson_at(const zjson *j, size_t i)
{
    /* 数组与对象都支持按序号取值（对象取的是“第 i 个值”） */
    if (!j || (j->type != ZJSON_ARR && j->type != ZJSON_OBJ) || (int)i >= j->count)
        return NULL;
    return j->items[i];
}

const char *zjson_key_at(const zjson *j, size_t i)
{
    if (!j || j->type != ZJSON_OBJ || (int)i >= j->count) return NULL;
    return j->keys[i];
}

zjson *zjson_obj_get(const zjson *obj, const char *key)
{
    int i;
    if (!obj || obj->type != ZJSON_OBJ || !key) return NULL;
    for (i = 0; i < obj->count; ++i)
        if (strcmp(obj->keys[i], key) == 0) return obj->items[i];
    return NULL;
}

/* 路径语法：a.b[0].c ；键内不允许 '.' 或 '[' */
zjson *zjson_get(const zjson *root, const char *path)
{
    const zjson *cur = root;
    const char *p = path;
    char key[256];
    if (!root || !path) return NULL;
    while (*p && cur) {
        if (*p == '.') { p++; continue; }
        if (*p == '[') {
            char *endp = NULL;
            long idx;
            p++;
            idx = strtol(p, &endp, 10);
            if (!endp || *endp != ']') return NULL;
            cur = zjson_at(cur, (size_t)idx);
            p = endp + 1;
            continue;
        }
        {
            size_t n = 0;
            while (*p && *p != '.' && *p != '[' && n < sizeof(key) - 1) key[n++] = *p++;
            key[n] = 0;
            cur = zjson_obj_get(cur, key);
        }
    }
    return (zjson *)cur;
}

const char *zjson_str(const zjson *j, const char *def)
{
    if (!j) return def;
    if (j->type == ZJSON_STR) return j->sval;
    return def;
}

double zjson_num(const zjson *j, double def)
{
    if (!j) return def;
    if (j->type == ZJSON_NUM) return j->num;
    if (j->type == ZJSON_BOOL) return j->bval ? 1.0 : 0.0;
    return def;
}

long zjson_int(const zjson *j, long def)
{
    double d;
    if (!j) return def;
    if (j->type == ZJSON_NUM) { d = j->num; return (long)(d < 0 ? d - 0.5 : d + 0.5); }
    if (j->type == ZJSON_BOOL) return j->bval ? 1 : 0;
    return def;
}

int zjson_bool(const zjson *j, int def)
{
    if (!j) return def;
    if (j->type == ZJSON_BOOL) return j->bval;
    return def;
}

/* ==================================================== 带诊断的取值 */
static const char *missing_text(int def_required)
{
    return def_required ? "缺少必填字段" : "字段缺失，使用默认值";
}

double zjson_get_num(const zjson *root, const char *path, int def_required,
                     double def, zdiag *d, const char *file)
{
    zjson *j = zjson_get(root, path);
    if (!j) {
        if (def_required)
            zdiag_error(d, file, root ? root->line : 0, 0, path, "%s", missing_text(def_required));
        else
            zdiag_warn(d, file, root ? root->line : 0, 0, path, "%s（默认 %.4g）", missing_text(0), def);
        return def;
    }
    if (j->type != ZJSON_NUM) {
        zdiag_error(d, file, j->line, j->col, path, "类型不符：期望 number，实际 %s",
                    zjson_type_name(j->type));
        return def;
    }
    return j->num;
}

long zjson_get_int(const zjson *root, const char *path, int def_required,
                   long def, long min_v, long max_v, zdiag *d, const char *file)
{
    zjson *j = zjson_get(root, path);
    double v;
    if (!j) {
        if (def_required)
            zdiag_error(d, file, root ? root->line : 0, 0, path, "%s", missing_text(1));
        else
            zdiag_warn(d, file, root ? root->line : 0, 0, path, "%s（默认 %ld）", missing_text(0), def);
        return def;
    }
    if (j->type != ZJSON_NUM) {
        zdiag_error(d, file, j->line, j->col, path, "类型不符：期望整数，实际 %s",
                    zjson_type_name(j->type));
        return def;
    }
    v = j->num;
    if (v != floor(v)) {
        zdiag_error(d, file, j->line, j->col, path, "期望整数，实际为小数 %.4g", v);
        return def;
    }
    if (min_v != max_v && (v < (double)min_v || v > (double)max_v)) {
        zdiag_error(d, file, j->line, j->col, path, "超出范围：应在 [%ld, %ld]，实际 %.4g",
                    min_v, max_v, v);
        return def;
    }
    return (long)v;
}

int zjson_get_bool(const zjson *root, const char *path, int def_required,
                   int def, zdiag *d, const char *file)
{
    zjson *j = zjson_get(root, path);
    if (!j) {
        if (def_required)
            zdiag_error(d, file, root ? root->line : 0, 0, path, "%s", missing_text(1));
        else
            zdiag_warn(d, file, root ? root->line : 0, 0, path, "%s（默认 %s）",
                       missing_text(0), def ? "true" : "false");
        return def;
    }
    if (j->type != ZJSON_BOOL) {
        zdiag_error(d, file, j->line, j->col, path, "类型不符：期望 bool(true/false)，实际 %s",
                    zjson_type_name(j->type));
        return def;
    }
    return j->bval;
}

const char *zjson_get_strbuf(const zjson *root, const char *path, int def_required,
                             const char *def, char *out, size_t cap,
                             zdiag *d, const char *file)
{
    zjson *j = zjson_get(root, path);
    if (!j) {
        if (def_required)
            zdiag_error(d, file, root ? root->line : 0, 0, path, "%s", missing_text(1));
        else
            zdiag_warn(d, file, root ? root->line : 0, 0, path, "%s（默认 \"%s\"）",
                       missing_text(0), def ? def : "");
        z_strlcpy(out, def ? def : "", cap);
        return out;
    }
    if (j->type != ZJSON_STR) {
        zdiag_error(d, file, j->line, j->col, path, "类型不符：期望 string，实际 %s",
                    zjson_type_name(j->type));
        z_strlcpy(out, def ? def : "", cap);
        return out;
    }
    z_strlcpy(out, j->sval, cap);
    return out;
}

const char *zjson_get_enum(const zjson *root, const char *path, int def_required,
                           const char *def, const char *const *allowed,
                           char *out, size_t cap, zdiag *d, const char *file)
{
    zjson *j = zjson_get(root, path);
    int i, ok = 0;
    if (!j) {
        if (def_required)
            zdiag_error(d, file, root ? root->line : 0, 0, path, "%s", missing_text(1));
        else
            zdiag_warn(d, file, root ? root->line : 0, 0, path, "%s（默认 \"%s\"）",
                       missing_text(0), def ? def : "");
        z_strlcpy(out, def ? def : "", cap);
        return out;
    }
    if (j->type != ZJSON_STR) {
        zdiag_error(d, file, j->line, j->col, path, "类型不符：期望 string，实际 %s",
                    zjson_type_name(j->type));
        z_strlcpy(out, def ? def : "", cap);
        return out;
    }
    for (i = 0; allowed && allowed[i]; ++i)
        if (strcmp(allowed[i], j->sval) == 0) { ok = 1; break; }
    if (!ok) {
        char list[256] = {0};
        size_t n = 0;
        for (i = 0; allowed && allowed[i]; ++i)
            n += z_snprintf(list + n, sizeof(list) - n, "%s\"%s\"", i ? "、" : "", allowed[i]);
        zdiag_error(d, file, j->line, j->col, path, "取值非法：\"%s\"，允许值为 %s",
                    j->sval, list);
        z_strlcpy(out, def ? def : "", cap);
        return out;
    }
    z_strlcpy(out, j->sval, cap);
    return out;
}

/* ================================================================ 生成 */
struct zjson_w {
    char *buf;
    size_t len, cap;
    int pretty;
    int depth;
    int need_comma[64];
    int after_key;      /* 刚写完 key：下一个值不能自己再加逗号 */
};

zjson_w *zjson_w_new(int pretty)
{
    zjson_w *w = (zjson_w *)z_calloc(1, sizeof(zjson_w));
    w->cap = 1024;
    w->buf = (char *)z_alloc(w->cap);
    w->buf[0] = 0;
    w->pretty = pretty;
    return w;
}

void zjson_w_free(zjson_w *w)
{
    if (!w) return;
    free(w->buf);
    free(w);
}

static void w_reserve(zjson_w *w, size_t extra)
{
    if (w->len + extra + 1 <= w->cap) return;
    while (w->len + extra + 1 > w->cap) w->cap *= 2;
    w->buf = (char *)z_realloc(w->buf, w->cap);
}

static void w_puts(zjson_w *w, const char *s)
{
    size_t n = strlen(s);
    w_reserve(w, n);
    memcpy(w->buf + w->len, s, n);
    w->len += n;
    w->buf[w->len] = 0;
}

static void w_putc(zjson_w *w, char c)
{
    w_reserve(w, 1);
    w->buf[w->len++] = c;
    w->buf[w->len] = 0;
}

static void w_indent(zjson_w *w)
{
    int i;
    if (!w->pretty) return;
    w_putc(w, '\n');
    for (i = 0; i < w->depth; ++i) { w_puts(w, "  "); }
}

static void w_pre_value(zjson_w *w)
{
    if (w->after_key) {
        /* key 之后的第一个值：逗号由 key 负责，这里只清标志 */
        w->after_key = 0;
        return;
    }
    if (w->depth > 0 && w->depth < 64) {
        if (w->need_comma[w->depth]) w_putc(w, ',');
        w->need_comma[w->depth] = 1;
    }
    w_indent(w);
}

void zjson_w_key(zjson_w *w, const char *key)
{
    w_pre_value(w);
    w->after_key = 1;
    w_putc(w, '"');
    {
        char *esc = (char *)z_alloc(strlen(key) * 6 + 4);
        zjson_escape(key, esc, strlen(key) * 6 + 4);
        w_puts(w, esc);
        free(esc);
    }
    w_putc(w, '"');
    w_puts(w, w->pretty ? ": " : ":");
}

void zjson_w_str(zjson_w *w, const char *s)
{
    char *esc;
    w_pre_value(w);
    w_putc(w, '"');
    if (s) {
        esc = (char *)z_alloc(strlen(s) * 6 + 4);
        zjson_escape(s, esc, strlen(s) * 6 + 4);
        w_puts(w, esc);
        free(esc);
    }
    w_putc(w, '"');
}

void zjson_w_num(zjson_w *w, double v)
{
    char buf[64];
    w_pre_value(w);
    if (v == floor(v) && fabs(v) < 1e15) snprintf(buf, sizeof(buf), "%ld", (long)v);
    else snprintf(buf, sizeof(buf), "%.10g", v);
    w_puts(w, buf);
}

void zjson_w_int(zjson_w *w, long v)
{
    char buf[32];
    w_pre_value(w);
    snprintf(buf, sizeof(buf), "%ld", v);
    w_puts(w, buf);
}

void zjson_w_bool(zjson_w *w, int v) { w_pre_value(w); w_puts(w, v ? "true" : "false"); }
void zjson_w_null(zjson_w *w) { w_pre_value(w); w_puts(w, "null"); }

void zjson_w_obj_begin(zjson_w *w)
{
    w_pre_value(w);
    w_putc(w, '{');
    if (w->depth < 63) { w->depth++; w->need_comma[w->depth] = 0; }
}

void zjson_w_obj_end(zjson_w *w)
{
    int had = (w->depth < 64) ? w->need_comma[w->depth] : 0;
    if (w->depth > 0) w->depth--;
    if (had) w_indent(w);
    w_putc(w, '}');
}

void zjson_w_arr_begin(zjson_w *w)
{
    w_pre_value(w);
    w_putc(w, '[');
    if (w->depth < 63) { w->depth++; w->need_comma[w->depth] = 0; }
}

void zjson_w_arr_end(zjson_w *w)
{
    int had = (w->depth < 64) ? w->need_comma[w->depth] : 0;
    if (w->depth > 0) w->depth--;
    if (had) w_indent(w);
    w_putc(w, ']');
}

char *zjson_w_take(zjson_w *w, size_t *len)
{
    char *out = w->buf;
    if (len) *len = w->len;
    w->cap = 1024;
    w->len = 0;
    w->depth = 0;
    memset(w->need_comma, 0, sizeof(w->need_comma));
    w->buf = (char *)z_alloc(w->cap);
    w->buf[0] = 0;
    return out;
}

void zjson_escape(const char *s, char *out, size_t cap)
{
    size_t n = 0;
    if (!s) { if (cap) out[0] = 0; return; }
    while (*s && n + 8 < cap) {
        unsigned char c = (unsigned char)*s++;
        switch (c) {
            case '"':  out[n++] = '\\'; out[n++] = '"'; break;
            case '\\': out[n++] = '\\'; out[n++] = '\\'; break;
            case '\n': out[n++] = '\\'; out[n++] = 'n'; break;
            case '\r': out[n++] = '\\'; out[n++] = 'r'; break;
            case '\t': out[n++] = '\\'; out[n++] = 't'; break;
            default:
                if (c < 0x20) {
                    n += (size_t)snprintf(out + n, cap - n, "\\u%04X", c);
                } else {
                    out[n++] = (char)c;   /* UTF-8 原样输出 */
                }
        }
    }
    out[n] = 0;
}
