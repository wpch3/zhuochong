/*
 * zschema.h - 极简 JSON Schema 校验器
 *
 * 目的（交接文件 2.1 第 4 条）：配置写错时必须给出“文件 + 字段 + 原因”，
 * 不崩溃、不静默忽略。因此每个配置文件都配一份 schema，
 * 加载时先过 schema，再做语义检查。
 *
 * 支持的关键字（够用即可，不做完整草案实现）：
 *   type, required, properties, additionalProperties, items,
 *   enum, minimum, maximum, exclusiveMinimum, exclusiveMaximum,
 *   minLength, maxLength, minItems, maxItems, pattern(仅支持 ^...$ 字面前后缀)
 */
#ifndef ZSCHEMA_H
#define ZSCHEMA_H

#include "zc.h"
#include "zjson.h"

#ifdef __cplusplus
extern "C" {
#endif

/* 校验 doc 是否符合 schema。
 * doc_name: 被校验文件的路径（写进诊断）。
 * 返回错误条数（0 = 通过）。所有问题都写进 diag。 */
int zschema_validate(const zjson *schema, const zjson *doc, const char *doc_name, zdiag *diag);

/* 便捷：读 schema 文件再校验；schema 文件不存在时返回 -1（调用方决定是否致命）。 */
int zschema_validate_file(const char *schema_path, const zjson *doc,
                          const char *doc_name, zdiag *diag);

#ifdef __cplusplus
}
#endif
#endif /* ZSCHEMA_H */
