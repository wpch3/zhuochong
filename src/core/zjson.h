/*
 * zjson.h - 轻量 JSON 解析/生成器（无第三方依赖）
 *
 * 为什么自己写：
 *   - 配置是本项目的扩展入口，报错必须精确到“文件 + 行 + 列 + 字段路径”；
 *   - 需要容忍注释与尾随逗号（配置由人手工编辑，中文注释有用）；
 *   - 需要 JSON Schema 校验时的“类型不符”诊断，第三方库不提供中文诊断。
 *
 * 支持：JSON 标准子集 + // 与 /  * *  / 注释 + 尾随逗号 + \uXXXX（含代理对）。
 * 不支持：数字 NaN/Infinity（按标准非法）。
 */
#ifndef ZJSON_H
#define ZJSON_H

#include "zc.h"

#ifdef __cplusplus
extern "C" {
#endif

typedef enum {
    ZJSON_NULL = 0, ZJSON_BOOL, ZJSON_NUM, ZJSON_STR, ZJSON_ARR, ZJSON_OBJ
} zjson_type;

typedef struct zjson zjson;

struct zjson {
    zjson_type type;
    double num;          /* NUM */
    int    bval;         /* BOOL */
    char  *sval;         /* STR（自有） */
    zjson **items;       /* ARR 元素 / OBJ 值 */
    char  **keys;        /* OBJ 键（自有） */
    int    count, cap;
    int    line, col;    /* 源位置，用于诊断 */
};

/* --------------------------------------------------------------- 解析 */
/* 失败时返回 NULL 并写 err（含行号、列号）。src_name 用于诊断显示，可为 NULL。 */
zjson *zjson_parse(const char *text, const char *src_name, zerr *err);
/* 从文件解析；失败时 err 里带文件名。 */
zjson *zjson_parse_file(const char *path, zerr *err);
void   zjson_free(zjson *j);

/* --------------------------------------------------------------- 访问 */
zjson_type  zjson_type_of(const zjson *j);
const char *zjson_type_name(zjson_type t);
int         zjson_is(const zjson *j, zjson_type t);

size_t      zjson_count(const zjson *j);            /* ARR/OBJ 长度 */
zjson      *zjson_at(const zjson *j, size_t i);     /* ARR */
const char *zjson_key_at(const zjson *j, size_t i); /* OBJ */
zjson      *zjson_obj_get(const zjson *obj, const char *key);
zjson      *zjson_get(const zjson *root, const char *path); /* "a.b[0].c" */

/* 取值（无诊断，按类型强制转换；类型不符返回默认值） */
const char *zjson_str(const zjson *j, const char *def);
double      zjson_num(const zjson *j, double def);
long        zjson_int(const zjson *j, long def);
int         zjson_bool(const zjson *j, int def);

/* --------------------------------------------- 带诊断的取值（配置加载用） */
/* 语义：
 *   - 字段存在且类型正确 → 通过；
 *   - 字段存在但类型不符 → 记一条“致命错误”，返回默认值；
 *   - 字段缺失：
 *       def_required 为真 → 记致命错误（缺少必填字段）；
 *       否则 → 记一条警告（使用默认值）。
 * 说明：类型上 int 接受 NUM，NUM 也接受可以整数值；STR 只接受 STR；
 *       bool 只接受 BOOL（不接受 0/1，避免配置歧义）。 */
double      zjson_get_num(const zjson *root, const char *path, int def_required,
                          double def, zdiag *d, const char *file);
long        zjson_get_int(const zjson *root, const char *path, int def_required,
                          long def, long min_v, long max_v, zdiag *d, const char *file);
int         zjson_get_bool(const zjson *root, const char *path, int def_required,
                           int def, zdiag *d, const char *file);
const char *zjson_get_strbuf(const zjson *root, const char *path, int def_required,
                             const char *def, char *out, size_t cap,
                             zdiag *d, const char *file);
/* 枚举字符串：value 必须在 allowed（NULL 结尾）里，否则报错。 */
const char *zjson_get_enum(const zjson *root, const char *path, int def_required,
                           const char *def, const char *const *allowed,
                           char *out, size_t cap, zdiag *d, const char *file);

/* --------------------------------------------------------------- 生成 */
typedef struct zjson_w zjson_w;
zjson_w *zjson_w_new(int pretty);
void     zjson_w_free(zjson_w *w);
void     zjson_w_obj_begin(zjson_w *w);
void     zjson_w_obj_end(zjson_w *w);
void     zjson_w_arr_begin(zjson_w *w);
void     zjson_w_arr_end(zjson_w *w);
void     zjson_w_key(zjson_w *w, const char *key);
void     zjson_w_str(zjson_w *w, const char *s);
void     zjson_w_num(zjson_w *w, double v);
void     zjson_w_int(zjson_w *w, long v);
void     zjson_w_bool(zjson_w *w, int v);
void     zjson_w_null(zjson_w *w);
/* 取走缓冲区（调用者 free），w 仍可继续使用（内部换新缓冲）。 */
char    *zjson_w_take(zjson_w *w, size_t *len);

/* 简易转义（写入字符串值用）；返回 out */
void zjson_escape(const char *s, char *out, size_t cap);

#ifdef __cplusplus
}
#endif
#endif /* ZJSON_H */
