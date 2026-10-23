/* zrelay —— 第一条真链路。设计说明见 zrelay.h。 */
#include "zrelay.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "zhttp.h"
#include "zjson.h"

#define ZRELAY_DEF_CAP "chat.completion"

/* 没有 usage 时的 token 估算。
 * 为什么要估：本地那一栈（ollama / llama.cpp / LM Studio）在某些版本里
 * 压根不回 usage 字段。估不准没关系 —— 本地是免费的，这个数只用来
 * 画"今天说了多少话"，不参与扣费。真要计费的云端供应商都回 usage。
 * 4 字节/token 是英文的经验值；中文 UTF-8 一个汉字 3 字节约 1 token，
 * 所以这里对中文会高估一点，宁可高估也不要把花费算少。 */
static long est_tokens(const char *s)
{
    size_t n = s ? strlen(s) : 0;
    return (long)(n / 4 + 1);
}

char *zrelay_build_chat_body(const char *model, const char *system_prompt,
                             const char *user_text, double temperature,
                             int max_tokens)
{
    zjson_w *w = zjson_w_new(0);
    char *out;
    size_t len = 0;
    if (!w) return NULL;

    zjson_w_obj_begin(w);
    zjson_w_key(w, "model");
    zjson_w_str(w, model ? model : "");
    zjson_w_key(w, "messages");
    zjson_w_arr_begin(w);
    if (system_prompt && *system_prompt) {
        zjson_w_obj_begin(w);
        zjson_w_key(w, "role");    zjson_w_str(w, "system");
        zjson_w_key(w, "content"); zjson_w_str(w, system_prompt);
        zjson_w_obj_end(w);
    }
    zjson_w_obj_begin(w);
    zjson_w_key(w, "role");    zjson_w_str(w, "user");
    zjson_w_key(w, "content"); zjson_w_str(w, user_text ? user_text : "");
    zjson_w_obj_end(w);
    zjson_w_arr_end(w);
    /* temperature / max_tokens 是"没填就别写进去"的字段：
       写一个自己编的默认值进去，等于悄悄覆盖了用户在服务端配的默认。 */
    if (temperature >= 0.0) {
        zjson_w_key(w, "temperature");
        zjson_w_num(w, temperature);
    }
    if (max_tokens > 0) {
        zjson_w_key(w, "max_tokens");
        zjson_w_int(w, max_tokens);
    }
    /* 显式写死 stream=false：流式是 G55 的事。
       不写的话有的中转站默认开流，回来的是 SSE，解析器当场看不懂。 */
    zjson_w_key(w, "stream");
    zjson_w_bool(w, 0);
    zjson_w_obj_end(w);

    out = zjson_w_take(w, &len);
    zjson_w_free(w);
    return out;
}

int zrelay_parse_chat_resp(const char *body, char **text,
                           long *tokens_in, long *tokens_out,
                           char *err, size_t errcap)
{
    zerr e;
    zjson *root, *j;
    const char *s;

    if (text) *text = NULL;
    if (tokens_in) *tokens_in = 0;
    if (tokens_out) *tokens_out = 0;
    if (!body) {
        if (err) snprintf(err, errcap, "响应是空的");
        return -1;
    }
    root = zjson_parse(body, "chat_response", &e);
    if (!root) {
        if (err) snprintf(err, errcap, "响应不是合法 JSON：%s", e.msg);
        return -1;
    }
    /* 先看是不是错误体。OpenAI 系的错误一律是 {"error":{"message":...}}，
       而且**可能带 200 状态码**（有的中转站就这么干），所以必须先验这个，
       不能只看 HTTP 状态码。 */
    j = zjson_get(root, "error");
    if (j) {
        const char *m = zjson_str(zjson_obj_get(j, "message"), NULL);
        if (!m) m = zjson_str(j, "（没有 message 字段）");
        if (err) snprintf(err, errcap, "服务端返回错误：%s", m ? m : "未知");
        zjson_free(root);
        return -1;
    }
    j = zjson_get(root, "choices[0].message.content");
    s = zjson_str(j, NULL);
    if (!s) {
        /* 有的实现把内容放在 choices[0].text（补全接口的老形状） */
        s = zjson_str(zjson_get(root, "choices[0].text"), NULL);
    }
    if (!s) {
        if (err) snprintf(err, errcap, "响应里找不到回复正文（choices[0].message.content）");
        zjson_free(root);
        return -1;
    }
    if (text) {
        size_t n = strlen(s);
        *text = (char *)malloc(n + 1);
        if (!*text) {
            if (err) snprintf(err, errcap, "内存不够");
            zjson_free(root);
            return -1;
        }
        memcpy(*text, s, n + 1);
    }
    if (tokens_in)
        *tokens_in = zjson_int(zjson_get(root, "usage.prompt_tokens"), 0);
    if (tokens_out)
        *tokens_out = zjson_int(zjson_get(root, "usage.completion_tokens"), 0);
    zjson_free(root);
    return 0;
}

/* base_url 和 chat_path 拼起来，处理好中间那个斜杠。
   "/v1" + "/chat/completions" 要拼成 "/v1/chat/completions"，
   "/v1/" + "/chat/completions" 不能拼成 "/v1//chat/completions" —— 有的网关会 404。 */
/* 选不到路时给人话。两处要用同一套说法，所以抽出来。 */
static const char *route_fail_text(zgw_status why)
{
    if (why == ZGW_NO_SUCH_CAP)       return "没有任何供应商声明过这个能力（功能没接入）";
    if (why == ZGW_ALL_DISABLED)      return "有供应商但都被关掉了（去设置里打开）";
    if (why == ZGW_SENSITIVE_NO_LOCAL)
        return "这条带隐私标记、只许本地处理，但本地没有可用模型 —— 不会偷偷上云";
    return "没有可用的供应商";
}

static void join_url(const char *base, const char *path, char *out, size_t cap)
{
    size_t bl;
    z_strlcpy(out, base ? base : "", cap);
    bl = strlen(out);
    while (bl > 0 && out[bl - 1] == '/') out[--bl] = 0;
    if (!path || !*path) return;
    if (*path != '/' && bl + 1 < cap) { out[bl++] = '/'; out[bl] = 0; }
    z_strlcpy(out + bl, path, cap - bl);
}

/* 发之前要准备的全部东西：查接入点、校接口族、取密钥、拼 URL、拼请求体。
 * 返回 0 = 准备好了（*body_out 需调用方 free），非 0 = 别发，out->err 已填好。
 *
 * ★ 为什么单独抽出来：dry-run（给用户看"将要发什么"）和真发必须走同一段代码。
 *   要是分两处写，面板上显示的请求体和实际出网的字节迟早对不上，
 *   而那种不一致恰恰是最难查的 —— 用户看着没问题，线上却不是那么回事。
 */
static int prepare_one(zgateway *g, const zgw_route *rt, const zrelay_chat_req *in,
                       char *url, size_t url_cap,
                       char *key, size_t key_cap,
                       char *authhdr, size_t authhdr_cap,
                       char **body_out, zrelay_result *out)
{
    const zgw_endpoint *ep;
    const char *secret_err = NULL;

    *body_out = NULL;
    key[0] = 0;
    authhdr[0] = 0;
    url[0] = 0;

    z_strlcpy(out->provider, rt->provider, sizeof(out->provider));
    z_strlcpy(out->model, rt->model, sizeof(out->model));
    out->local = rt->local;

    ep = zgw_endpoint_find(g, rt->provider);
    if (!ep) {
        snprintf(out->err, sizeof(out->err),
                 "供应商 %s 没有接入点信息（重跑 tools/check_platform.py 生成）", rt->provider);
        return -1;
    }
    if (strcmp(ep->kind, "openai_compatible") != 0) {
        snprintf(out->err, sizeof(out->err),
                 "%s 的接口是 %s，本版只接 openai_compatible —— 不会拿错格式硬发",
                 rt->provider, ep->kind[0] ? ep->kind : "(未知)");
        return -1;
    }
    if (!ep->chat_path[0]) {
        snprintf(out->err, sizeof(out->err), "%s 没有声明聊天端点", rt->provider);
        return -1;
    }
    if (!ep->base_url[0]) {
        snprintf(out->err, sizeof(out->err), "%s 没有 base_url", rt->provider);
        return -1;
    }

    /* 密钥：取不到就**不发**。空密钥发出去只会换回一个 401，
       但那一下已经把请求（含用户说的话）送到对面了。 */
    if (strcmp(ep->auth_type, "none") != 0) {
        if (!ep->key_ref[0]) {
            snprintf(out->err, sizeof(out->err),
                     "%s 要鉴权但契约里没写 key_ref", rt->provider);
            return -1;
        }
        if (zgw_secret_resolve(ep->key_ref, key, key_cap, &secret_err) != 0) {
            snprintf(out->err, sizeof(out->err),
                     "拿不到 %s 的密钥：%s", rt->provider,
                     secret_err ? secret_err : "未知原因");
            return -1;
        }
        if (strcmp(ep->auth_type, "header") == 0) {
            snprintf(authhdr, authhdr_cap, "%s: %s\r\n",
                     ep->auth_header[0] ? ep->auth_header : "x-api-key", key);
            key[0] = 0;     /* 走自定义头就不要再发 Authorization */
        }
    }

    join_url(ep->base_url, ep->chat_path, url, url_cap);
    *body_out = zrelay_build_chat_body(rt->model, in->system_prompt, in->user_text,
                                       in->temperature, in->max_tokens);
    if (!*body_out) {
        snprintf(out->err, sizeof(out->err), "请求体拼不出来（内存不够）");
        return -1;
    }
    return 0;
}

/* 试一家。返回 0 = 成功。失败时 out->err 已填好。 */
static int try_one(zgateway *g, const zgw_route *rt, const zrelay_chat_req *in,
                   const char *cap, zrelay_result *out)
{
    char url[320], key[256], authhdr[320];
    char *body = NULL;
    zhttp_req q;
    zhttp_resp rp;
    zhttp_err he;
    long hold = 0;
    long tin = 0, tout = 0;
    double est;
    int rc = -1;

    if (prepare_one(g, rt, in, url, sizeof(url), key, sizeof(key),
                    authhdr, sizeof(authhdr), &body, out) != 0)
        return -1;

    /* 预扣：发之前占住额度。估不准没关系，结算时按实际值入账。 */
    est = zgw_estimate(rt, est_tokens(in->system_prompt) + est_tokens(in->user_text),
                       in->max_tokens > 0 ? in->max_tokens : 512);
    hold = zgw_hold_open(g, cap, rt->provider, est);

    memset(&q, 0, sizeof(q));
    q.method = "POST";
    q.url = url;
    q.body = body;
    q.content_type = "application/json";
    q.bearer = key[0] ? key : NULL;
    q.extra_headers = authhdr[0] ? authhdr : NULL;
    q.timeout_ms = in->timeout_ms > 0 ? in->timeout_ms : 30000;

    he = zhttp_send(&q, &rp);
    free(body);

    if (he != ZHTTP_OK) {
        /* err_detail 只有 TLS 那条路会填，但它恰恰是最需要细说的一条：
           "没装 OpenSSL" / "证书是自签名的" / "域名对不上" 三种情况
           用户要做的事完全不同，只给一句"TLS 用不了"等于没说。 */
        if (rp.err_detail[0])
            snprintf(out->err, sizeof(out->err), "%.150s：%.160s", url, rp.err_detail);
        else
            snprintf(out->err, sizeof(out->err), "%.220s：%s", url, zhttp_err_text(he));
        if (hold) zgw_hold_release(g, hold);
        return -1;
    }
    out->http_status = rp.status;

    if (rp.status < 200 || rp.status >= 300) {
        /* 对面明确拒绝。把它的错误正文带出来 —— 401/429/404 的区别
           对用户是完全不同的操作建议，吞掉它等于让人去猜。 */
        char detail[200];
        char perr[200];
        detail[0] = 0;
        if (zrelay_parse_chat_resp(rp.body, NULL, NULL, NULL, perr, sizeof(perr)) != 0)
            z_strlcpy(detail, perr, sizeof(detail));
        else if (rp.body)
            z_strlcpy(detail, rp.body, sizeof(detail));
        snprintf(out->err, sizeof(out->err), "HTTP %d：%s", rp.status, detail);
        if (hold) zgw_hold_release(g, hold);
        zhttp_resp_free(&rp);
        return -1;
    }

    rc = zrelay_parse_chat_resp(rp.body, &out->text, &tin, &tout,
                                out->err, sizeof(out->err));
    zhttp_resp_free(&rp);
    if (rc != 0) {
        if (hold) zgw_hold_release(g, hold);
        return -1;
    }

    if (tin <= 0)  tin = est_tokens(in->system_prompt) + est_tokens(in->user_text);
    if (tout <= 0) tout = est_tokens(out->text);
    out->tokens_in = tin;
    out->tokens_out = tout;
    out->cost = zgw_estimate(rt, tin, tout);
    if (hold) zgw_hold_settle(g, hold, tin, tout, out->cost);
    out->ok = 1;
    out->err[0] = 0;
    return 0;
}

int zrelay_chat(zgateway *g, const zrelay_chat_req *in, zrelay_result *out)
{
    const char *cap;
    zgw_status why = ZGW_OK;
    zgw_reason reason = ZGW_R_NO_CANDIDATE;
    const zgw_route *rt;
    int attempt, max_attempts;
    char tried[8][48];
    int ntried = 0;

    if (!out) return -1;
    memset(out, 0, sizeof(*out));
    if (!g || !in || !in->user_text || !*in->user_text) {
        snprintf(out->err, sizeof(out->err), "没有要发的内容");
        return -1;
    }
    cap = in->cap && *in->cap ? in->cap : ZRELAY_DEF_CAP;
    max_attempts = in->max_attempts > 0 ? in->max_attempts : 1;
    if (max_attempts > 8) max_attempts = 8;

    for (attempt = 0; attempt < max_attempts; ++attempt) {
        int dup = 0, i;
        if (attempt == 0) {
            /* 第一次走三支柱决策（敏感/长度/负载），它才懂"这条该不该上云" */
            rt = zgw_route_for(g, cap, &in->route, &why, &reason);
            z_strlcpy(out->reason, zgw_reason_name(reason), sizeof(out->reason));
        } else {
            /* 降级重试就只按优先级往下走。三支柱的方向判断在第一次已经做过，
               失败后再做一遍只会得到同一个答案。 */
            if (!g->fallback) break;
            rt = zgw_pick(g, cap, attempt, &why);
            /* ★★★ 隐私红线在这儿要再守一遍。
               zgw_pick() 只认优先级，**不认 sensitive** —— 它不是为这条路写的。
               第一次用 zgw_route_for 守住了，一旦本地那家连不上、又允许降级，
               就会沿着优先级往下走，下一家很可能是云端：用户说的身份证号
               就这么出去了。
               这个洞之前没炸，只是因为配置里云端那些家默认 enabled=false ——
               而"默认关着"是配置，不是保证。用户一打开就漏。
               所以这里宁可一家都不换、直接失败：敏感件不可用 > 敏感件上云。 */
            if (rt && !rt->local && in->route.sensitive && g->rules.sensitive_local_only) {
                snprintf(out->err, sizeof(out->err),
                         "本地模型没能答上，而这条带隐私标记 —— 不会改发云端。"
                         "请把本地模型开起来，或去掉隐私标记再试。");
                break;
            }
        }
        if (!rt) {
            if (attempt == 0)
                snprintf(out->err, sizeof(out->err), "%s", route_fail_text(why));
            break;
        }
        for (i = 0; i < ntried; ++i)
            if (strcmp(tried[i], rt->provider) == 0) { dup = 1; break; }
        if (dup) continue;                    /* 这家刚试过，跳过别重复扣 */
        if (ntried < 8) z_strlcpy(tried[ntried++], rt->provider, sizeof(tried[0]));

        out->attempts = attempt + 1;
        if (try_one(g, rt, in, cap, out) == 0) return 0;
        out->ok = 0;
    }
    if (!out->err[0]) snprintf(out->err, sizeof(out->err), "都试过了，没有一家成功");
    return -1;
}

int zrelay_dry_run(zgateway *g, const zrelay_chat_req *in,
                   char *url, size_t url_cap, char **body_out,
                   zrelay_result *out)
{
    const char *cap;
    zgw_status why = ZGW_OK;
    zgw_reason reason = ZGW_R_NO_CANDIDATE;
    const zgw_route *rt;
    char key[256], authhdr[320];
    int rc;

    if (!out || !url || url_cap == 0 || !body_out) return -1;
    memset(out, 0, sizeof(*out));
    *body_out = NULL;
    url[0] = 0;
    if (!g || !in || !in->user_text || !*in->user_text) {
        snprintf(out->err, sizeof(out->err), "没有要发的内容");
        return -1;
    }
    cap = in->cap && *in->cap ? in->cap : ZRELAY_DEF_CAP;

    rt = zgw_route_for(g, cap, &in->route, &why, &reason);
    if (!rt) {
        z_strlcpy(out->reason, zgw_reason_name(reason), sizeof(out->reason));
        snprintf(out->err, sizeof(out->err), "%s", route_fail_text(why));
        return -1;
    }
    z_strlcpy(out->reason, zgw_reason_name(reason), sizeof(out->reason));

    rc = prepare_one(g, rt, in, url, url_cap, key, sizeof(key),
                     authhdr, sizeof(authhdr), body_out, out);
    /* ★ 密钥取到了也绝不往外带：dry-run 的输出是要显示在界面上的。
         这里把它从栈上抹掉，免得哪天有人"顺手"把 authhdr 也打印出去。 */
    memset(key, 0, sizeof(key));
    memset(authhdr, 0, sizeof(authhdr));
    if (rc != 0) return -1;
    out->ok = 1;
    out->attempts = 0;          /* 一次都没发 */
    out->http_status = 0;
    return 0;
}

void zrelay_result_free(zrelay_result *r)
{
    if (!r) return;
    free(r->text);
    r->text = NULL;
}
