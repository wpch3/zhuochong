#include <stddef.h>
#ifndef ZPERF_H
#define ZPERF_H
#ifdef __cplusplus
extern "C" {
#endif
// zperf - 性能预算 A31/G81：渲染优先、占用上限实测、可独立降档、用户活跃时让出
typedef struct zperf zperf;
zperf *zperf_load(const char *root, char *err, size_t errcap);
void zperf_free(zperf *p);
int zperf_render_first(zperf *p);
int zperf_budget_ok(zperf *p, const char *mode, double cpu, double mem_mb);
const char *zperf_degrade_next(zperf *p, const char *cur);
int zperf_should_yield(zperf *p, double user_idle_s);
double zperf_measured(zperf *p, const char *key);
#ifdef __cplusplus
}
#endif
#endif
