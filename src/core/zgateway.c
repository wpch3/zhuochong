#include "zgateway.h"
#include "zjson.h"

#include <stdlib.h>
#include <string.h>
#include <ctype.h>

/* --------------------------------------------------------------- 加载 */

int zgw_load(zgateway *g, const char *routes_path, zdiag *d)
{
    zerr err;
    zjson *root, *arr;
    size_t i, n;

    if (!g || !routes_path) return -1;
    memset(g, 0, sizeof(*g));
    g->next_hold_id = 1;
    g->fallback = 1;

    root = zjson_parse_file(routes_path, &err);
    if (!root) {
        if (d) zdiag_error(d, routes_path, err.line, err.col, "gateway_routes",
                           "路由表解析失败：%s", err.msg);
        return -1;
    }
    if (!zjson_get(root, "schema_version")) {
        if (d) zdiag_error(d, routes_path, root->line, root->col, "schema_version",
                           "缺少 schema_version");
        zjson_free(root);
        return -1;
    }

    z_strlcpy(g->strategy, zjson_str(zjson_get(root, "strategy"), "priority"),
              sizeof(g->strategy));
    g->fallback = zjson_bool(zjson_get(root, "fallback"), 1);

    arr = zjson_get(root, "routes");
    n = zjson_count(arr);
    for (i = 0; i < n && g->nroutes < ZGW_MAX_ROUTES; ++i) {
        zjson *r = zjson_at(arr, i);
        zgw_route *o = &g->routes[g->nroutes];
        const char *cap = zjson_str(zjson_obj_get(r, "cap"), NULL);
        const char *pid = zjson_str(zjson_obj_get(r, "provider"), NULL);
        if (!cap || !*cap || !pid || !*pid) {
            if (d) zdiag_error(d, routes_path, r ? r->line : 0, 0, "routes",
                               "第 %d 条路由缺少 cap 或 provider", (int)i);
            continue;
        }
        z_strlcpy(o->cap, cap, sizeof(o->cap));
        z_strlcpy(o->provider, pid, sizeof(o->provider));
        z_strlcpy(o->model, zjson_str(zjson_obj_get(r, "model"), ""), sizeof(o->model));
        o->priority  = (int)zjson_int(zjson_obj_get(r, "priority"), 0);
        o->local     = zjson_bool(zjson_obj_get(r, "local"), 0);
        o->enabled   = zjson_bool(zjson_obj_get(r, "enabled"), 1);
        o->is_free   = zjson_bool(zjson_obj_get(r, "free"), 0);
        o->price_in  = zjson_num(zjson_obj_get(r, "price_in"), 0.0);
        o->price_out = zjson_num(zjson_obj_get(r, "price_out"), 0.0);
        o->price_per = zjson_num(zjson_obj_get(r, "price_per"), 0.0);
        g->nroutes++;
    }

    if (n > (size_t)ZGW_MAX_ROUTES && d)
        zdiag_warn(d, routes_path, 0, 0, "routes",
                   "路由表有 %d 条，超过上限 %d，多出来的被忽略",
                   (int)n, ZGW_MAX_ROUTES);

    zjson_free(root);
    return 0;
}

/* --------------------------------------------------------------- 路由 */

/* 路由表已经按 (cap, -priority, provider) 排好序了，所以这里顺序扫描
 * 第 attempt 个 enabled 的就是答案。排序逻辑留在生成端，运行时不重排。 */
const zgw_route *zgw_pick(const zgateway *g, const char *cap, int attempt, zgw_status *why)
{
    int i, seen = 0, hit = 0;

    if (why) *why = ZGW_OK;
    if (!g || !cap || !*cap || attempt < 0) {
        if (why) *why = ZGW_NO_SUCH_CAP;
        return NULL;
    }
    /* fallback 关掉时只允许首选，不许换家 */
    if (attempt > 0 && !g->fallback) {
        if (why) *why = ZGW_EXHAUSTED;
        return NULL;
    }

    for (i = 0; i < g->nroutes; ++i) {
        const zgw_route *r = &g->routes[i];
        if (strcmp(r->cap, cap) != 0) continue;
        seen++;
        if (!r->enabled) continue;
        if (hit++ == attempt) return r;
    }

    if (why) {
        if (!seen)      *why = ZGW_NO_SUCH_CAP;   /* 没人声明过这个能力 */
        else if (!hit)  *why = ZGW_ALL_DISABLED;  /* 有人能做，但都关着 */
        else            *why = ZGW_EXHAUSTED;     /* 候选用完了 */
    }
    return NULL;
}

int zgw_candidate_count(const zgateway *g, const char *cap)
{
    int i, n = 0;
    if (!g || !cap) return 0;
    for (i = 0; i < g->nroutes; ++i)
        if (strcmp(g->routes[i].cap, cap) == 0 && g->routes[i].enabled) n++;
    return n;
}

/* --------------------------------------------------------------- 估价 */

double zgw_estimate(const zgw_route *r, long tokens_in, long tokens_out)
{
    double per;
    if (!r) return 0.0;
    /* 本机服务不花钱；声明 free 的也不花钱。两个条件都要认——
     * 本机服务的契约里未必写了 price。 */
    if (r->local || r->is_free) return 0.0;
    if (tokens_in < 0) tokens_in = 0;
    if (tokens_out < 0) tokens_out = 0;

    per = r->price_per;
    if (per <= 0.0) {
        /* 没写计量单位 = 按次计价，单价直接就是一次的钱 */
        return r->price_in + r->price_out;
    }
    return (r->price_in * (double)tokens_in + r->price_out * (double)tokens_out) / per;
}

/* --------------------------------------------------------------- 记账 */

long zgw_hold_open(zgateway *g, const char *cap, const char *provider, double estimated)
{
    int i;
    if (!g || !cap || !provider) return 0;
    if (estimated < 0.0) estimated = 0.0;
    for (i = 0; i < ZGW_MAX_HOLDS; ++i) {
        zgw_hold *h = &g->holds[i];
        if (h->id) continue;
        h->id = g->next_hold_id++;
        z_strlcpy(h->cap, cap, sizeof(h->cap));
        z_strlcpy(h->provider, provider, sizeof(h->provider));
        h->estimated = estimated;
        g->nholds++;
        return h->id;
    }
    return 0; /* 预扣槽位满了：说明有请求没收尾，不该再放行 */
}

static zgw_hold *find_hold(zgateway *g, long id)
{
    int i;
    if (!g || id <= 0) return NULL;
    for (i = 0; i < ZGW_MAX_HOLDS; ++i)
        if (g->holds[i].id == id) return &g->holds[i];
    return NULL;
}

int zgw_hold_settle(zgateway *g, long hold_id, long tokens_in, long tokens_out, double actual)
{
    zgw_hold *h = find_hold(g, hold_id);
    if (!h) return -1;
    if (actual < 0.0) actual = 0.0;
    /* 入账的是实际花费，不是当初预扣的数。预扣只是占位。 */
    g->spent_total += actual;
    g->tokens_in_total  += (tokens_in  > 0 ? tokens_in  : 0);
    g->tokens_out_total += (tokens_out > 0 ? tokens_out : 0);
    g->calls_total++;
    memset(h, 0, sizeof(*h));
    g->nholds--;
    return 0;
}

int zgw_hold_release(zgateway *g, long hold_id)
{
    zgw_hold *h = find_hold(g, hold_id);
    if (!h) return -1;
    /* 请求没成功：一分钱不记，但失败次数要记——它是"这家是不是该降权"的依据 */
    g->failed_total++;
    memset(h, 0, sizeof(*h));
    g->nholds--;
    return 0;
}

double zgw_held_amount(const zgateway *g)
{
    int i;
    double s = 0.0;
    if (!g) return 0.0;
    for (i = 0; i < ZGW_MAX_HOLDS; ++i)
        if (g->holds[i].id) s += g->holds[i].estimated;
    return s;
}

/* --------------------------------------------------------------- 密钥 */

int zgw_secret_resolve(const char *ref, char *out, size_t cap, const char **err)
{
    char name[96];
    const char *p, *v;
    size_t i;

    if (err) *err = NULL;
    if (out && cap) out[0] = '\0';

    if (!ref || !*ref) {
        if (err) *err = "没有给密钥引用";
        return -1;
    }
    if (strncmp(ref, "secret://", 9) != 0) {
        /* 这里不是"宽容一下也行"的地方：允许裸值就等于允许把密钥写进配置文件，
         * 而配置文件是会被提交进仓库的。 */
        if (err) *err = "密钥必须写成 secret:// 引用，不接受明文";
        return -1;
    }
    p = ref + 9;
    if (!*p) {
        if (err) *err = "secret:// 后面没有名字";
        return -1;
    }

    /* secret://deepseek → ZHUOCHONG_SECRET_DEEPSEEK */
    z_strlcpy(name, "ZHUOCHONG_SECRET_", sizeof(name));
    i = strlen(name);
    for (; *p && i + 1 < sizeof(name); ++p) {
        unsigned char c = (unsigned char)*p;
        if (c == '-' || c == '.' || c == '/') c = '_';
        else c = (unsigned char)toupper(c);
        name[i++] = (char)c;
    }
    name[i] = '\0';

    v = getenv(name);
    if (!v || !*v) {
        /* 失败路径必须明确：拿不到密钥就是拿不到，不能让调用方带着空串继续。 */
        if (err) *err = "环境变量里没有这个密钥（没配或是空的）";
        return -1;
    }
    if (!out || cap == 0) {
        if (err) *err = "没有给输出缓冲";
        return -1;
    }
    if (strlen(v) + 1 > cap) {
        if (err) *err = "密钥太长，装不下";
        return -1;
    }
    z_strlcpy(out, v, cap);
    return 0;
}
