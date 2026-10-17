/* zschema.c - 极简 JSON Schema 校验器实现 */
#include "zschema.h"
#include <math.h>
#include <ctype.h>

static const char *type_of(const zjson *j)
{
    return zjson_type_name(zjson_type_of(j));
}

static int type_matches(const zjson *doc, const char *t)
{
    zjson_type ty = zjson_type_of(doc);
    if (strcmp(t, "object") == 0) return ty == ZJSON_OBJ;
    if (strcmp(t, "array") == 0) return ty == ZJSON_ARR;
    if (strcmp(t, "string") == 0) return ty == ZJSON_STR;
    if (strcmp(t, "number") == 0) return ty == ZJSON_NUM;
    if (strcmp(t, "integer") == 0) return ty == ZJSON_NUM && doc->num == floor(doc->num);
    if (strcmp(t, "boolean") == 0) return ty == ZJSON_BOOL;
    if (strcmp(t, "null") == 0) return ty == ZJSON_NULL;
    return 1;   /* 未知类型：放过，避免误报 */
}

/* 极简正则：支持 ^ 与 $ 锚点、字面量、[a-z0-9_] 字符类、. 任意字符、
 * 以及 + * ? 三个量词。足够表达配置里用到的 id / 颜色 / 版本号规则。 */
static int cls_match(const char *cls, int neg, char c)
{
    int hit = 0;
    while (*cls && *cls != ']') {
        if (cls[1] == '-' && cls[2] && cls[2] != ']') {
            if (c >= cls[0] && c <= cls[2]) hit = 1;
            cls += 3;
        } else {
            if (c == *cls) hit = 1;
            cls++;
        }
    }
    return neg ? !hit : hit;
}

static int mini_match(const char *pat, const char *str)
{
    if (!pat) return 1;
    if (!*pat) return !*str;
    /* 处理 ^ */
    if (*pat == '^') {
        if (!*str) return 0;
        return mini_match(pat + 1, str);  /* 交给下面的分支处理首字符 */
    }
    if (*pat != '$') {
        /* 取出一个“单元”：字符类 / 字面量 / . */
        const char *next = pat;
        int matched = 0;
        if (*pat == '[') {
            const char *end = strchr(pat, ']');
            int neg = 0;
            const char *cls = pat + 1;
            if (!end) return 0;
            if (*cls == '^') { neg = 1; cls++; }
            matched = *str ? cls_match(cls, neg, *str) : 0;
            next = end + 1;
        } else if (*pat == '.') {
            matched = *str ? 1 : 0;
            next = pat + 1;
        } else {
            matched = (*str && *str == *pat);
            next = pat + 1;
        }
        /* 量词 {n} / {n,} / {n,m} */
        if (*next == '{') {
            const char *close = strchr(next, '}');
            if (close) {
                int lo = 0, hi = -1;
                char num[16];
                size_t k = 0;
                const char *q = next + 1;
                while (q < close && *q != ',' && k < sizeof(num) - 1) num[k++] = *q++;
                num[k] = 0;
                lo = atoi(num);
                if (q < close && *q == ',') {
                    k = 0;
                    q++;
                    while (q < close && k < sizeof(num) - 1) num[k++] = *q++;
                    num[k] = 0;
                    hi = (*num && isdigit((unsigned char)num[0])) ? atoi(num) : -1;
                } else {
                    hi = lo;
                }
                {
                    const char *rest = close + 1;
                    const char *s2 = str;
                    int count = 0;
                    while (*s2 && (hi < 0 || count < hi)) {
                        int ok;
                        if (*pat == '[') {
                            const char *end = strchr(pat, ']');
                            const char *cls = pat + 1;
                            int neg = 0;
                            if (*cls == '^') { neg = 1; cls++; }
                            ok = cls_match(cls, neg, *s2);
                            (void)end;
                        } else if (*pat == '.') ok = 1;
                        else ok = (*s2 == *pat);
                        if (!ok) break;
                        s2++;
                        count++;
                    }
                    while (count >= lo) {
                        if (mini_match(rest, s2)) return 1;
                        if (count == 0) break;
                        count--;
                        s2--;
                    }
                    return 0;
                }
            }
        }
        if (*next == '+' || *next == '*' || *next == '?') {
            char q = *next;
            const char *rest = next + 1;
            int min = (q == '+') ? 1 : 0;
            int max = (q == '?') ? 1 : -1;
            int count = 0;
            const char *s = str;
            /* 贪心匹配，然后回溯 */
            while (*s && (max < 0 || count < max)) {
                int ok;
                if (*pat == '[') {
                    const char *end = strchr(pat, ']');
                    const char *cls = pat + 1;
                    int neg = 0;
                    if (*cls == '^') { neg = 1; cls++; }
                    ok = cls_match(cls, neg, *s);
                    (void)end;
                } else if (*pat == '.') {
                    ok = 1;
                } else {
                    ok = (*s == *pat);
                }
                if (!ok) break;
                s++;
                count++;
            }
            while (count >= min) {
                if (mini_match(rest, s)) return 1;
                if (count == 0) break;
                count--;
                s--;
            }
            return 0;
        }
        if (!matched) return 0;
        return mini_match(next, str + 1);
    }
    /* 遇到 $：要求串结束 */
    return (!str[0] || (str[0] == '\0'));
}

static int pattern_matches(const char *pat, const char *s)
{
    return mini_match(pat, s);
}

static int validate_node(const zjson *schema, const zjson *doc, const char *file,
                         const char *path, zdiag *d);

static int validate_object(const zjson *schema, const zjson *doc, const char *file,
                           const char *path, zdiag *d)
{
    int errors = 0;
    const zjson *required = zjson_obj_get(schema, "required");
    const zjson *props = zjson_obj_get(schema, "properties");
    const zjson *addl = zjson_obj_get(schema, "additionalProperties");
    size_t i, n;

    /* required */
    n = zjson_count(required);
    for (i = 0; i < n; ++i) {
        const char *key = zjson_str(zjson_at(required, i), NULL);
        if (!key) continue;
        if (!zjson_obj_get(doc, key)) {
            zdiag_error(d, file, doc->line, doc->col, path,
                        "缺少必填字段 \"%s\"", key);
            errors++;
        }
    }
    /* properties + additionalProperties */
    n = zjson_count(doc);
    for (i = 0; i < n; ++i) {
        const char *key = zjson_key_at(doc, i);
        const zjson *sub = zjson_at(doc, i);
        const zjson *sub_schema = props ? zjson_obj_get(props, key) : NULL;
        char subpath[256];
        if (path && *path) z_snprintf(subpath, sizeof(subpath), "%s.%s", path, key);
        else z_snprintf(subpath, sizeof(subpath), "%s", key);
        if (!sub_schema) {
            if (addl && addl->type == ZJSON_BOOL && !addl->bval) {
                zdiag_error(d, file, sub->line, sub->col, subpath,
                            "不允许的额外字段（schema 中未声明）");
                errors++;
            }
            continue;
        }
        errors += validate_node(sub_schema, sub, file, subpath, d);
    }
    return errors;
}

static int validate_array(const zjson *schema, const zjson *doc, const char *file,
                          const char *path, zdiag *d)
{
    int errors = 0;
    const zjson *items = zjson_obj_get(schema, "items");
    size_t i, n = zjson_count(doc);
    long min_items = -1, max_items = -1;
    const zjson *mi = zjson_obj_get(schema, "minItems");
    const zjson *ma = zjson_obj_get(schema, "maxItems");
    if (mi && mi->type == ZJSON_NUM) min_items = (long)mi->num;
    if (ma && ma->type == ZJSON_NUM) max_items = (long)ma->num;
    if (min_items >= 0 && (long)n < min_items) {
        zdiag_error(d, file, doc->line, doc->col, path, "元素太少：至少 %ld 个，实际 %d 个",
                    min_items, (int)n);
        errors++;
    }
    if (max_items >= 0 && (long)n > max_items) {
        zdiag_error(d, file, doc->line, doc->col, path, "元素太多：最多 %ld 个，实际 %d 个",
                    max_items, (int)n);
        errors++;
    }
    for (i = 0; i < n; ++i) {
        char subpath[256];
        if (items) {
            z_snprintf(subpath, sizeof(subpath), "%s[%d]", path ? path : "", (int)i);
            errors += validate_node(items, zjson_at(doc, i), file, subpath, d);
        }
    }
    return errors;
}

static int validate_node(const zjson *schema, const zjson *doc, const char *file,
                         const char *path, zdiag *d)
{
    int errors = 0;
    const zjson *t;
    const zjson *en;

    if (!doc) {
        zdiag_error(d, file, 0, 0, path, "文档为空（缺少该字段的值）");
        return 1;
    }
    if (!schema || schema->type != ZJSON_OBJ) return 0;
    t = zjson_obj_get(schema, "type");
    en = zjson_obj_get(schema, "enum");

    if (t && t->type != ZJSON_STR && t->type != ZJSON_ARR) {
        return 0;   /* schema 写法不支持的类型声明：放过，避免误报 */
    }
    if (t) {
        if (t->type == ZJSON_STR) {
            if (!type_matches(doc, t->sval)) {
                zdiag_error(d, file, doc->line, doc->col, path,
                            "类型不符：schema 要求 %s，实际 %s", t->sval, type_of(doc));
                return 1;
            }
        } else if (t->type == ZJSON_ARR) {
            size_t i, n = zjson_count(t);
            int ok = 0;
            for (i = 0; i < n; ++i) {
                const char *ts = zjson_str(zjson_at(t, i), NULL);
                if (ts && type_matches(doc, ts)) { ok = 1; break; }
            }
            if (!ok) {
                zdiag_error(d, file, doc->line, doc->col, path, "类型不符（多类型 schema）");
                return 1;
            }
        }
    }

    if (en && zjson_count(en) > 0) {
        size_t i, n = zjson_count(en);
        int ok = 0;
        char list[256] = {0};
        size_t ln = 0;
        for (i = 0; i < n; ++i) {
            const zjson *ev = zjson_at(en, i);
            if (ev->type == ZJSON_STR && doc->type == ZJSON_STR && strcmp(ev->sval, doc->sval) == 0) ok = 1;
            if (ev->type == ZJSON_NUM && doc->type == ZJSON_NUM && ev->num == doc->num) ok = 1;
            if (ev->type == ZJSON_BOOL && doc->type == ZJSON_BOOL && ev->bval == doc->bval) ok = 1;
            if (ev->type == ZJSON_STR)
                ln += z_snprintf(list + ln, sizeof(list) - ln, "%s\"%s\"", i ? "、" : "", ev->sval);
        }
        if (!ok) {
            zdiag_error(d, file, doc->line, doc->col, path, "取值不在允许列表内：允许 %s", list);
            errors++;
        }
    }

    if (doc->type == ZJSON_NUM) {
        const zjson *v;
        struct { const char *k; int upper; int exc; } checks[4] = {
            { "minimum", 0, 0 }, { "maximum", 1, 0 },
            { "exclusiveMinimum", 0, 1 }, { "exclusiveMaximum", 1, 1 }
        };
        int ci;
        for (ci = 0; ci < 4; ++ci) {
            v = zjson_obj_get(schema, checks[ci].k);
            if (!v || v->type != ZJSON_NUM) continue;
            if (!checks[ci].upper) {
                if ((!checks[ci].exc && doc->num < v->num) ||
                    (checks[ci].exc && doc->num <= v->num)) {
                    zdiag_error(d, file, doc->line, doc->col, path,
                                "数值过小：应%s %.4g，实际 %.4g",
                                checks[ci].exc ? "大于" : "不小于", v->num, doc->num);
                    errors++;
                }
            } else {
                if ((!checks[ci].exc && doc->num > v->num) ||
                    (checks[ci].exc && doc->num >= v->num)) {
                    zdiag_error(d, file, doc->line, doc->col, path,
                                "数值过大：应%s %.4g，实际 %.4g",
                                checks[ci].exc ? "小于" : "不大于", v->num, doc->num);
                    errors++;
                }
            }
        }
    }

    if (doc->type == ZJSON_STR) {
        const zjson *ml = zjson_obj_get(schema, "minLength");
        const zjson *xl = zjson_obj_get(schema, "maxLength");
        const zjson *pat = zjson_obj_get(schema, "pattern");
        size_t len = strlen(doc->sval);
        if (ml && ml->type == ZJSON_NUM && (double)len < ml->num) {
            zdiag_error(d, file, doc->line, doc->col, path, "字符串太短：至少 %d 字符",
                        (int)ml->num);
            errors++;
        }
        if (xl && xl->type == ZJSON_NUM && (double)len > xl->num) {
            zdiag_error(d, file, doc->line, doc->col, path, "字符串太长：最多 %d 字符",
                        (int)xl->num);
            errors++;
        }
        if (pat && pat->type == ZJSON_STR && !pattern_matches(pat->sval, doc->sval)) {
            zdiag_error(d, file, doc->line, doc->col, path, "格式不符（pattern %s）", pat->sval);
            errors++;
        }
    }

    if (doc->type == ZJSON_OBJ) errors += validate_object(schema, doc, file, path, d);
    if (doc->type == ZJSON_ARR) errors += validate_array(schema, doc, file, path, d);
    return errors;
}

int zschema_validate(const zjson *schema, const zjson *doc, const char *doc_name, zdiag *diag)
{
    if (!schema) return 0;
    if (!doc) {
        zdiag_error(diag, doc_name, 0, 0, "", "文档为空，无法校验");
        return 1;
    }
    return validate_node(schema, doc, doc_name, "", diag);
}

int zschema_validate_file(const char *schema_path, const zjson *doc,
                          const char *doc_name, zdiag *diag)
{
    zerr err;
    zjson *schema;
    int n;
    if (!z_file_exists(schema_path)) return -1;
    zerr_clear(&err);
    schema = zjson_parse_file(schema_path, &err);
    if (!schema) {
        zdiag_error(diag, schema_path, err.line, err.col, "", "schema 文件本身解析失败：%s", err.msg);
        return 1;
    }
    n = zschema_validate(schema, doc, doc_name, diag);
    zjson_free(schema);
    return n;
}
