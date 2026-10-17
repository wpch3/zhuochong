#include "zgateway.h"
#include "zjson.h"

#include <stdlib.h>
#include <string.h>
#include <ctype.h>
#include <stdio.h>
#include <time.h>

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

    /* 双路由阈值：表里没写就用抄来的默认值（DC18 的复查触发里写明要重标） */
    {
        zjson *ru = zjson_get(root, "rules");
        g->rules.tokens_cloud   = (long)zjson_int(zjson_obj_get(ru, "tokens_cloud"), 512);
        g->rules.local_busy_pct = (int)zjson_int(zjson_obj_get(ru, "local_busy_pct"), 85);
        g->rules.sensitive_local_only =
            zjson_bool(zjson_obj_get(ru, "sensitive_local_only"), 1);
    }

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

/* ---- 本地↔云端双路由（DC18）----------------------------------------
 *
 * 判据抄自 docs/REFERENCE_NOTES 第二十批，三支柱的次序是有讲究的：
 *   敏感 > 复杂/长 > 忙或故障。
 * 敏感排第一且**不可被后面两条推翻** —— 本地不可用时宁可失败，也不上云。
 * 这条是整个函数里唯一一个"宁可功能不可用"的分支，别人改代码时最容易
 * 顺手给它加个 fallback，所以测试里专门盯着它（test_core / check_platform）。
 */

const char *zgw_reason_name(zgw_reason r)
{
    switch (r) {
    case ZGW_R_DEFAULT_LOCAL:     return "default_local";
    case ZGW_R_SENSITIVE_LOCAL:   return "sensitive_local";
    case ZGW_R_LONG_CLOUD:        return "long_cloud";
    case ZGW_R_HEAVY_CLOUD:       return "heavy_cloud";
    case ZGW_R_LOCAL_BUSY:        return "local_busy";
    case ZGW_R_CLOUD_DOWN:        return "cloud_down";
    case ZGW_R_ONLY_CHOICE:       return "only_choice";
    case ZGW_R_SENSITIVE_BLOCKED: return "sensitive_blocked";
    case ZGW_R_NO_CANDIDATE:      return "no_candidate";
    default:                      return "unknown";
    }
}

/* 重活的特征词。中文按 UTF-8 字节子串匹配即可（UTF-8 不会出现错位子串）。
   分三类是为了让界面能说清楚"凭什么判的"。 */
static const char *const HEAVY_CODE[] = {
    "```", "def ", "function ", "class ", "SELECT ", "import ",
    "代码", "函数", "报错", "异常", "调试", "重构", "正则", "脚本", "编译", "堆栈", NULL
};
static const char *const HEAVY_REASON[] = {
    "为什么", "分析", "比较", "权衡", "推导", "证明", "规划", "设计一个", "方案",
    "逐步", "一步步", "step by step", "原因", "评估", NULL
};
static const char *const HEAVY_TOOL[] = {
    "搜索", "查一下", "查查", "帮我订", "调用", "接口", "爬", "翻译整篇", NULL
};

static int hit_any(const char *text, const char *const *tab, const char **hit)
{
    int i;
    for (i = 0; tab[i]; ++i) {
        if (strstr(text, tab[i])) {
            if (hit) *hit = tab[i];
            return 1;
        }
    }
    return 0;
}

zgw_task zgw_classify(const char *text, const char **hit)
{
    size_t n;
    if (hit) *hit = "";
    if (!text || !*text) return ZGW_TASK_SIMPLE;
    if (hit_any(text, HEAVY_CODE, hit))   return ZGW_TASK_HEAVY;
    if (hit_any(text, HEAVY_REASON, hit)) return ZGW_TASK_HEAVY;
    if (hit_any(text, HEAVY_TOOL, hit))   return ZGW_TASK_HEAVY;
    /* 够长也算重活：一句话寒暄和一段材料，处理成本差一个量级。
       600 字节 ≈ 200 个汉字，比 tokens_cloud 那条线更早触发，两条是互补的。 */
    n = strlen(text);
    if (n >= 600) {
        if (hit) *hit = "长文";
        return ZGW_TASK_HEAVY;
    }
    return ZGW_TASK_SIMPLE;
}

/* 在同一张表里按优先级挑第一条 enabled 且 local 符合要求的 */
static const zgw_route *pick_side(const zgateway *g, const char *cap, int want_local)
{
    int i;
    for (i = 0; i < g->nroutes; ++i) {
        const zgw_route *r = &g->routes[i];
        if (strcmp(r->cap, cap) != 0) continue;
        if (!r->enabled) continue;
        if (!!r->local != !!want_local) continue;
        return r;
    }
    return NULL;
}

void zgw_set_usage_log(zgateway *g, const char *path)
{
    if (!g) return;
    if (!path || !*path) { g->usage_log[0] = 0; return; }
    z_strlcpy(g->usage_log, path, sizeof(g->usage_log));
}

/* 往流水里追一行 JSON。
 *
 * 为什么是 JSONL 而不是 CSV 或数据库：一行一条、追加写、崩了最多丢最后一行，
 * 而且用 `grep` / `wc -l` 就能看个大概，不用先起一个服务。
 *
 * 为什么连"没选中"（敏感被拒）也记：重标阈值时最需要知道的就是被拒了多少次，
 * 只记成功的那些会把分母做小，算出来的本地占比虚高。 */
static void usage_append(zgateway *g, const char *cap, const zgw_req *req,
                         zgw_reason why, const zgw_route *r)
{
    FILE *f;
    long sz;
    if (!g || !g->usage_log[0]) return;

    /* 先看要不要滚：2MB 大约是 2 万条决策，够回标用了 */
    f = fopen(g->usage_log, "rb");
    if (f) {
        fseek(f, 0, SEEK_END);
        sz = ftell(f);
        fclose(f);
        if (sz > 2L * 1024L * 1024L) {
            char old_path[300];
            z_snprintf(old_path, sizeof(old_path), "%s.1", g->usage_log);
            remove(old_path);
            rename(g->usage_log, old_path);
        }
    }

    f = fopen(g->usage_log, "ab");
    if (!f) { g->log_failed++; return; }
    fprintf(f,
            "{\"t\":%ld,\"cap\":\"%s\",\"provider\":\"%s\",\"model\":\"%s\","
            "\"local\":%d,\"reason\":\"%s\",\"task\":\"%s\",\"tokens\":%ld,"
            "\"load\":%d,\"sensitive\":%d,\"cloud_down\":%d,\"picked\":%d}\n",
            (long)time(NULL), cap ? cap : "",
            r ? r->provider : "", r ? r->model : "",
            r ? (r->local ? 1 : 0) : 0,
            zgw_reason_name(why),
            (req && req->task == ZGW_TASK_HEAVY) ? "heavy" : "simple",
            req ? req->tokens_est : 0L,
            req ? req->local_load_pct : -1,
            (req && req->sensitive) ? 1 : 0,
            (req && req->cloud_down) ? 1 : 0,
            r ? 1 : 0);
    fclose(f);
    g->log_written++;
}

static void note(zgateway *g, const char *cap, const zgw_req *req,
                 zgw_reason why, const zgw_route *r)
{
    if (why >= 0 && why < ZGW_R_COUNT) g->reason_hits[why]++;
    if (r) { if (r->local) g->picks_local++; else g->picks_cloud++; }
    usage_append(g, cap, req, why, r);
}

const zgw_route *zgw_route_for(zgateway *g, const char *cap, const zgw_req *req,
                               zgw_status *why, zgw_reason *reason)
{
    const zgw_route *local_r, *cloud_r, *r;
    zgw_rules ru;
    zgw_reason rs = ZGW_R_DEFAULT_LOCAL;
    int want_cloud = 0;

    if (why) *why = ZGW_OK;
    if (reason) *reason = ZGW_R_DEFAULT_LOCAL;
    if (!g || !cap || !*cap || !req) {
        if (why) *why = ZGW_NO_SUCH_CAP;
        return NULL;
    }

    ru = g->rules;
    if (ru.tokens_cloud <= 0)   ru.tokens_cloud = 512;
    if (ru.local_busy_pct <= 0) ru.local_busy_pct = 85;

    local_r = pick_side(g, cap, 1);
    cloud_r = pick_side(g, cap, 0);
    if (!local_r && !cloud_r) {
        /* 分不清是"没人声明过"还是"全关了"，交给 zgw_pick 的口径 */
        zgw_pick(g, cap, 0, why);
        if (why && *why == ZGW_OK) *why = ZGW_ALL_DISABLED;
        /* 这一类也要记流水：重标阈值时得知道"根本没候选"占了多少，
           只记成功的那些会把分母做小、本地占比虚高（这就是它原来一条都不记的坑）。 */
        rs = ZGW_R_NO_CANDIDATE;
        if (reason) *reason = rs;
        note(g, cap, req, rs, NULL);
        return NULL;
    }

    /* 支柱一：敏感数据强制本地。注意这里**没有** else 去兜云端。 */
    if (req->sensitive && ru.sensitive_local_only != 0) {
        if (local_r) {
            rs = ZGW_R_SENSITIVE_LOCAL;
            if (reason) *reason = rs;
            note(g, cap, req, rs, local_r);
            return local_r;
        }
        rs = ZGW_R_SENSITIVE_BLOCKED;
        if (reason) *reason = rs;
        if (why) *why = ZGW_SENSITIVE_NO_LOCAL;
        note(g, cap, req, rs, NULL);
        return NULL;
    }

    /* 支柱二：复杂 / 长上下文上云 */
    if (req->tokens_est > ru.tokens_cloud)      { want_cloud = 1; rs = ZGW_R_LONG_CLOUD; }
    else if (req->task == ZGW_TASK_HEAVY)       { want_cloud = 1; rs = ZGW_R_HEAVY_CLOUD; }
    /* 支柱三之一：本地忙 → 溢出 */
    else if (req->local_load_pct >= 0 &&
             req->local_load_pct >= ru.local_busy_pct) { want_cloud = 1; rs = ZGW_R_LOCAL_BUSY; }

    /* 支柱三之二：云端故障 → 退回本地 */
    if (want_cloud && req->cloud_down && local_r) {
        rs = ZGW_R_CLOUD_DOWN;
        if (reason) *reason = rs;
        note(g, cap, req, rs, local_r);
        return local_r;
    }

    r = want_cloud ? cloud_r : local_r;
    if (!r) {                       /* 想要的那边没有候选，只剩另一边 */
        r = want_cloud ? local_r : cloud_r;
        rs = ZGW_R_ONLY_CHOICE;
    }
    if (!r) {                       /* 理论上到不了这里（上面已排除两边都空） */
        if (why) *why = ZGW_ALL_DISABLED;
        return NULL;
    }
    if (reason) *reason = rs;
    note(g, cap, req, rs, r);
    return r;
}

double zgw_local_share(const zgateway *g)
{
    long tot;
    if (!g) return -1.0;
    tot = g->picks_local + g->picks_cloud;
    if (tot <= 0) return -1.0;
    return (double)g->picks_local / (double)tot;
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
