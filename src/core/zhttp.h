/* zhttp —— 最小 HTTP/1.1 客户端（G54 的运输层）
 *
 * 为什么要自己写：本仓库零第三方依赖（只带一个 stb_image.h），
 * 机器上也没有 openssl 开发头。为了发一个 POST 去引入 libcurl，
 * 等于把"一个 exe 拷过去就能跑"这条产品前提给砸了。
 * HTTP/1.1 的请求-响应本身不复杂，难的是 TLS —— 所以这一版**只做明文 http 协议**，
 * 见下面那段「关于 https」。
 *
 * 这一层只管「把字节送出去、把字节收回来」：
 *   · 不认识 JSON，不认识供应商，不认识模型
 *   · 不做重试（重试是网关的事，它才知道还有没有下一家可降级）
 *   · 不碰全局状态，可以并发调用
 * 上层 zrelay 负责「拼什么请求、怎么解析回来的东西」。
 *
 * ★★★ 关于 https ——
 * 真实的云端供应商（OpenAI / DeepSeek / 月之暗面 …）**全是 https**，
 * 所以这一版还连不上它们。这件事必须明着说，不能让它悄悄失败：
 * 传 https 地址进来会立刻返回 ZHTTP_E_TLS，并给一句人话。
 * **宁可拒绝，也不能偷偷降级成明文** —— 那是在用户不知情的情况下
 * 把 API key 用明文发到网上，属于安全事故，不是"先凑合用"。
 *
 * 那现在它有什么用：**本地那一栈全是明文 http**。
 *   ollama        http://127.0.0.1:11434/v1
 *   llama.cpp     http://127.0.0.1:8080/v1
 *   LM Studio     http://127.0.0.1:1234/v1
 *   vLLM          http://127.0.0.1:8000/v1
 *   ComfyUI / speaches / whisper.cpp 同理
 * 也就是说，**第一条真链路可以先在本地这一栈上整条跑通**，
 * 而且本地这一栈恰好是"断网也能用"那条产品承诺的落点。
 * TLS 怎么补，两条路都记在 docs/PROVIDER_PLAN.md 的 G54 一节里。
 */
#ifndef ZHTTP_H
#define ZHTTP_H

#include <stddef.h>

typedef enum {
    ZHTTP_OK = 0,
    ZHTTP_E_URL,        /* URL 不合法 */
    ZHTTP_E_TLS,        /* https —— 本版没有 TLS，明确拒绝 */
    ZHTTP_E_DNS,        /* 域名解析不了 */
    ZHTTP_E_CONNECT,    /* 连不上（对面没开 / 被拒） */
    ZHTTP_E_TIMEOUT,    /* 连接或读写超时 */
    ZHTTP_E_SEND,
    ZHTTP_E_RECV,
    ZHTTP_E_PROTO,      /* 对面回的不是合法 HTTP */
    ZHTTP_E_TOOBIG,     /* 响应体超过上限 */
    ZHTTP_E_OOM,
    ZHTTP_E_COUNT
} zhttp_err;

/* 人话错误名，直接可以显示给用户（指向静态串，不要 free） */
const char *zhttp_err_text(zhttp_err e);

/* ---------------------------------------------------------------- URL */
typedef struct {
    char scheme[8];
    char host[160];
    int  port;
    char path[768];     /* 含查询串；空路径补成 "/" */
    int  tls;           /* scheme == https */
} zhttp_url;

/* 0 = 成功。单独导出是因为它值得单测：端口缺省、IPv6 方括号、
   path 为空、带 query 这几种都栽过人。 */
int zhttp_url_parse(const char *url, zhttp_url *out);

/* ------------------------------------------------------------- 请求 */
typedef struct {
    const char *method;         /* NULL = "GET" */
    const char *url;
    const char *body;           /* 可为 NULL */
    size_t      body_len;       /* 0 且 body 非空 ⇒ 用 strlen */
    const char *content_type;   /* NULL 且有 body ⇒ application/json */
    const char *bearer;         /* NULL = 不带 Authorization */
    const char *extra_headers;  /* 已拼好的 "K: V\r\n…"，可为 NULL */
    int         timeout_ms;     /* <=0 用默认 30000 */
    size_t      max_body;       /* 0 用默认 1MB */
} zhttp_req;

typedef struct {
    int    status;      /* HTTP 状态码 */
    char  *body;        /* 调用方 zhttp_resp_free；总是 '\0' 结尾 */
    size_t body_len;
    int    truncated;   /* 响应体被 max_body 截断过 */
} zhttp_resp;

/* 发一次请求。返回 ZHTTP_OK 表示**网络层**成功（拿到了一个完整响应），
 * HTTP 状态码好不好要看 resp->status —— 404 也是 ZHTTP_OK。
 * 这两件事必须分开：连不上和被拒绝，给用户的提示完全不同。 */
zhttp_err zhttp_send(const zhttp_req *req, zhttp_resp *resp);

void zhttp_resp_free(zhttp_resp *r);

#endif /* ZHTTP_H */
