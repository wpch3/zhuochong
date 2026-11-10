/* zhttp —— 最小 HTTP/1.1 客户端。设计说明见 zhttp.h。 */
/* getaddrinfo / MSG_NOSIGNAL 这些都在 POSIX.1-2008 里，
   -std=c11 是严格模式不会自动暴露它们，所以要在任何 include 之前声明。 */
#ifndef _WIN32
#  ifndef _POSIX_C_SOURCE
#    define _POSIX_C_SOURCE 200809L
#  endif
#endif

#include "zhttp.h"
#include "ztls.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#ifdef _WIN32
#  include <winsock2.h>
#  include <ws2tcpip.h>
   typedef SOCKET zsock;
#  define ZSOCK_BAD   INVALID_SOCKET
#  define zclosesock  closesocket
#else
#  include <arpa/inet.h>
#  include <errno.h>
#  include <fcntl.h>
#  include <netdb.h>
#  include <netinet/in.h>
#  include <sys/socket.h>
#  include <sys/select.h>
#  include <sys/time.h>
#  include <unistd.h>
   typedef int zsock;
#  define ZSOCK_BAD   (-1)
#  define zclosesock  close
#endif

#define ZHTTP_DEF_TIMEOUT 30000
#define ZHTTP_DEF_MAXBODY (1024u * 1024u)

const char *zhttp_err_text(zhttp_err e)
{
    switch (e) {
    case ZHTTP_OK:         return "成功";
    case ZHTTP_E_URL:      return "地址格式不对";
    case ZHTTP_E_TLS:      return "TLS 用不了（看 err_detail）—— 不会降级成明文发送";
    case ZHTTP_E_TLS_CERT: return "对方的证书验不过 —— 已中止，一个字节都没发";
    case ZHTTP_E_DNS:      return "域名解析不了";
    case ZHTTP_E_CONNECT:  return "连不上（服务没开，或者端口不对）";
    case ZHTTP_E_TIMEOUT:  return "超时";
    case ZHTTP_E_SEND:     return "发送失败";
    case ZHTTP_E_RECV:     return "接收失败";
    case ZHTTP_E_PROTO:    return "对面回的不是合法的 HTTP 响应";
    case ZHTTP_E_TOOBIG:   return "响应体太大";
    case ZHTTP_E_OOM:      return "内存不够";
    default:               return "未知错误";
    }
}

/* ------------------------------------------------------------------ URL */

int zhttp_url_parse(const char *url, zhttp_url *out)
{
    const char *p, *host_beg, *host_end, *path_beg;
    size_t n;

    if (!url || !out) return -1;
    memset(out, 0, sizeof(*out));

    p = strstr(url, "://");
    if (!p) return -1;
    n = (size_t)(p - url);
    if (n == 0 || n >= sizeof(out->scheme)) return -1;
    memcpy(out->scheme, url, n);
    out->scheme[n] = 0;

    if (strcmp(out->scheme, "http") == 0) {
        out->tls = 0;
        out->port = 80;
    } else if (strcmp(out->scheme, "https") == 0) {
        out->tls = 1;
        out->port = 443;
    } else {
        return -1;
    }

    host_beg = p + 3;
    /* 路径从第一个 '/' 开始；'?' 也要算（http://h?x 这种没有路径但有查询） */
    path_beg = host_beg;
    while (*path_beg && *path_beg != '/' && *path_beg != '?') path_beg++;
    host_end = path_beg;

    /* IPv6 字面量用方括号包着，里面的冒号不是端口分隔符 */
    if (*host_beg == '[') {
        const char *rb = memchr(host_beg, ']', (size_t)(host_end - host_beg));
        if (!rb) return -1;
        n = (size_t)(rb - host_beg - 1);
        if (n == 0 || n >= sizeof(out->host)) return -1;
        memcpy(out->host, host_beg + 1, n);
        out->host[n] = 0;
        if (rb + 1 < host_end) {
            if (*(rb + 1) != ':') return -1;
            out->port = atoi(rb + 2);
        }
    } else {
        const char *colon = memchr(host_beg, ':', (size_t)(host_end - host_beg));
        const char *he = colon ? colon : host_end;
        n = (size_t)(he - host_beg);
        if (n == 0 || n >= sizeof(out->host)) return -1;
        memcpy(out->host, host_beg, n);
        out->host[n] = 0;
        if (colon) out->port = atoi(colon + 1);
    }
    if (out->port <= 0 || out->port > 65535) return -1;

    if (*path_beg == 0) {
        out->path[0] = '/';
        out->path[1] = 0;
    } else {
        n = strlen(path_beg);
        if (n >= sizeof(out->path)) return -1;
        memcpy(out->path, path_beg, n + 1);
        if (out->path[0] == '?') {
            /* "http://h?x" ⇒ 路径要补成 "/?x" */
            if (n + 2 > sizeof(out->path)) return -1;
            memmove(out->path + 1, out->path, n + 1);
            out->path[0] = '/';
        }
    }
    return 0;
}

/* --------------------------------------------------------------- 套接字 */

#ifdef _WIN32
static void zhttp_wsa_once(void)
{
    static int done = 0;
    if (!done) {
        WSADATA wsa;
        WSAStartup(MAKEWORD(2, 2), &wsa);
        done = 1;   /* 进程生命周期内只初始化一次；不做 WSACleanup，
                       因为别处可能还在用，清理反而会把人家的套接字弄死 */
    }
}
#endif

static void sock_set_blocking(zsock s, int blocking)
{
#ifdef _WIN32
    u_long mode = blocking ? 0 : 1;
    ioctlsocket(s, FIONBIO, &mode);
#else
    int fl = fcntl(s, F_GETFL, 0);
    if (fl < 0) return;
    fcntl(s, F_SETFL, blocking ? (fl & ~O_NONBLOCK) : (fl | O_NONBLOCK));
#endif
}

static void sock_set_timeout(zsock s, int ms)
{
#ifdef _WIN32
    DWORD tv = (DWORD)ms;
    setsockopt(s, SOL_SOCKET, SO_RCVTIMEO, (const char *)&tv, sizeof(tv));
    setsockopt(s, SOL_SOCKET, SO_SNDTIMEO, (const char *)&tv, sizeof(tv));
#else
    struct timeval tv;
    tv.tv_sec = ms / 1000;
    tv.tv_usec = (ms % 1000) * 1000;
    setsockopt(s, SOL_SOCKET, SO_RCVTIMEO, &tv, sizeof(tv));
    setsockopt(s, SOL_SOCKET, SO_SNDTIMEO, &tv, sizeof(tv));
#endif
}

/* 带超时的 connect：先切非阻塞发起，再用 select 等可写。
   阻塞式 connect 的超时是系统定的（Linux 上能到 2 分钟），
   桌宠点一下要等两分钟是不能接受的，所以必须自己控。 */
static zhttp_err sock_connect(const zhttp_url *u, int timeout_ms, zsock *out)
{
    struct addrinfo hints, *res = NULL, *ai;
    char portbuf[16];
    zhttp_err rc = ZHTTP_E_CONNECT;

    snprintf(portbuf, sizeof(portbuf), "%d", u->port);
    memset(&hints, 0, sizeof(hints));
    hints.ai_family = AF_UNSPEC;
    hints.ai_socktype = SOCK_STREAM;
    if (getaddrinfo(u->host, portbuf, &hints, &res) != 0 || !res)
        return ZHTTP_E_DNS;

    for (ai = res; ai; ai = ai->ai_next) {
        zsock s = socket(ai->ai_family, ai->ai_socktype, ai->ai_protocol);
        int cr;
        if (s == ZSOCK_BAD) continue;

        sock_set_blocking(s, 0);
        cr = connect(s, ai->ai_addr, (int)ai->ai_addrlen);
        if (cr != 0) {
            fd_set wset, eset;
            struct timeval tv;
            int sel;
#ifdef _WIN32
            if (WSAGetLastError() != WSAEWOULDBLOCK) { zclosesock(s); continue; }
#else
            if (errno != EINPROGRESS) { zclosesock(s); continue; }
            if (s >= FD_SETSIZE) { zclosesock(s); continue; }  /* select 的硬限制 */
#endif
            FD_ZERO(&wset); FD_SET(s, &wset);
            FD_ZERO(&eset); FD_SET(s, &eset);
            tv.tv_sec = timeout_ms / 1000;
            tv.tv_usec = (timeout_ms % 1000) * 1000;
            sel = select((int)s + 1, NULL, &wset, &eset, &tv);
            if (sel == 0) { zclosesock(s); rc = ZHTTP_E_TIMEOUT; continue; }
            if (sel < 0 || FD_ISSET(s, &eset)) { zclosesock(s); continue; }
            {   /* select 说可写不等于连上了，还得问 SO_ERROR */
                int soerr = 0;
#ifdef _WIN32
                int len = sizeof(soerr);
                getsockopt(s, SOL_SOCKET, SO_ERROR, (char *)&soerr, &len);
#else
                socklen_t len = sizeof(soerr);
                getsockopt(s, SOL_SOCKET, SO_ERROR, &soerr, &len);
#endif
                if (soerr != 0) { zclosesock(s); continue; }
            }
        }
        sock_set_blocking(s, 1);
        sock_set_timeout(s, timeout_ms);
        freeaddrinfo(res);
        *out = s;
        return ZHTTP_OK;
    }
    freeaddrinfo(res);
    return rc;
}

/* ---------------------------------------------------------------- 连接
 *
 * 明文和 TLS 只在"字节怎么过线"这一层不同，上面的 HTTP 处理完全一样。
 * 所以把读写收进 zconn，**只在这两个函数里分叉** ——
 * 要是让 TLS 分支把整个 zhttp_send 复制一份，两条路迟早会长歪
 * （比如 chunked 解析只修了一边）。
 */
typedef struct {
    zsock  s;
    ztls  *tls;      /* NULL = 明文 */
} zconn;

static zhttp_err conn_send_all(zconn *c, const char *buf, size_t len)
{
    size_t off = 0;
    while (off < len) {
        int n;
        if (c->tls) {
            n = ztls_write(c->tls, buf + off, (int)(len - off));
        } else {
#ifdef _WIN32
            n = send(c->s, buf + off, (int)(len - off), 0);
#else
            n = (int)send(c->s, buf + off, len - off, MSG_NOSIGNAL);
#endif
        }
        if (n <= 0) {
#ifndef _WIN32
            if (!c->tls && n < 0 && (errno == EAGAIN || errno == EWOULDBLOCK))
                return ZHTTP_E_TIMEOUT;
#endif
            return ZHTTP_E_SEND;
        }
        off += (size_t)n;
    }
    return ZHTTP_OK;
}

/* 读一段。>0 = 字节数，0 = 对端关闭，-1 = 出错，-2 = 被打断（重试），
   -3 = 超时。把超时单独分出来是因为它要报成 ZHTTP_E_TIMEOUT 而不是 E_RECV。 */
static int conn_recv(zconn *c, char *buf, size_t len)
{
    if (c->tls) {
        int to = 0;
        int n = ztls_read(c->tls, buf, (int)len, &to);
        if (n < 0 && to) return -3;
        return n;
    }
    {
#ifdef _WIN32
        int n = recv(c->s, buf, (int)len, 0);
#else
        ssize_t n = recv(c->s, buf, len, 0);
#endif
        if (n >= 0) return (int)n;
#ifndef _WIN32
        if (errno == EINTR) return -2;
        if (errno == EAGAIN || errno == EWOULDBLOCK) return -3;
#endif
        return -1;
    }
}

static void conn_close(zconn *c)
{
    if (c->tls) { ztls_close(c->tls); c->tls = NULL; }
    if (c->s != ZSOCK_BAD) { zclosesock(c->s); c->s = ZSOCK_BAD; }
}

/* ------------------------------------------------------------ 动态缓冲 */

typedef struct { char *p; size_t len, cap; } zbuf;

static int zbuf_grow(zbuf *b, size_t need)
{
    size_t cap = b->cap ? b->cap : 2048;
    char *np;
    while (cap < b->len + need + 1) {
        if (cap > (size_t)1 << 30) return -1;
        cap *= 2;
    }
    if (cap == b->cap) return 0;
    np = (char *)realloc(b->p, cap);
    if (!np) return -1;
    b->p = np;
    b->cap = cap;
    return 0;
}

static int zbuf_add(zbuf *b, const char *s, size_t n)
{
    if (zbuf_grow(b, n) != 0) return -1;
    memcpy(b->p + b->len, s, n);
    b->len += n;
    b->p[b->len] = 0;
    return 0;
}

/* ------------------------------------------------------------ 响应解析 */

static int hdr_find(const char *head, const char *name, char *out, size_t cap)
{
    /* head 是以 '\0' 结尾的响应头（不含空行）。大小写不敏感逐行找。 */
    const char *line = strchr(head, '\n');
    size_t nlen = strlen(name);
    if (!line) return 0;
    line++;
    while (*line) {
        const char *eol = strchr(line, '\n');
        size_t llen = eol ? (size_t)(eol - line) : strlen(line);
        if (llen && line[llen - 1] == '\r') llen--;
        if (llen > nlen && line[nlen] == ':') {
            size_t i;
            int same = 1;
            for (i = 0; i < nlen; i++) {
                char a = line[i], b = name[i];
                if (a >= 'A' && a <= 'Z') a = (char)(a - 'A' + 'a');
                if (b >= 'A' && b <= 'Z') b = (char)(b - 'A' + 'a');
                if (a != b) { same = 0; break; }
            }
            if (same) {
                const char *v = line + nlen + 1;
                size_t vlen;
                while (v < line + llen && (*v == ' ' || *v == '\t')) v++;
                vlen = (size_t)(line + llen - v);
                if (vlen >= cap) vlen = cap - 1;
                memcpy(out, v, vlen);
                out[vlen] = 0;
                return 1;
            }
        }
        if (!eol) break;
        line = eol + 1;
    }
    return 0;
}

/* 解 chunked。成功返回 0。就地把 src 解到 dst。 */
static int dechunk(const char *src, size_t len, zbuf *dst)
{
    size_t off = 0;
    for (;;) {
        size_t i = off, sz = 0;
        int any = 0;
        while (i < len && src[i] != '\r' && src[i] != '\n') {
            char c = src[i];
            int d;
            if (c >= '0' && c <= '9') d = c - '0';
            else if (c >= 'a' && c <= 'f') d = c - 'a' + 10;
            else if (c >= 'A' && c <= 'F') d = c - 'A' + 10;
            else if (c == ';') break;        /* chunk 扩展，忽略 */
            else return -1;
            sz = sz * 16 + (size_t)d;
            any = 1;
            i++;
        }
        if (!any) return -1;
        while (i < len && src[i] != '\n') i++;
        if (i >= len) return -1;
        i++;                                  /* 跳过 \n */
        if (sz == 0) return 0;                /* 收尾块 */
        if (i + sz > len) return -1;
        if (zbuf_add(dst, src + i, sz) != 0) return -1;
        off = i + sz;
        /* 块后面跟一个 CRLF */
        if (off < len && src[off] == '\r') off++;
        if (off < len && src[off] == '\n') off++;
    }
}

/* ------------------------------------------------------------------ 主体 */

zhttp_err zhttp_send(const zhttp_req *req, zhttp_resp *resp)
{
    zhttp_url u;
    zsock s = ZSOCK_BAD;
    zconn c = { ZSOCK_BAD, NULL };
    zbuf raw = {0}, out = {0};
    char head[128];
    zhttp_err rc;
    const char *method;
    size_t body_len, max_body, hdr_end = 0;
    int timeout_ms;
    char *reqbuf = NULL;
    size_t reqcap;
    char lenbuf[64];

    if (!req || !req->url || !resp) return ZHTTP_E_URL;
    memset(resp, 0, sizeof(*resp));

    if (zhttp_url_parse(req->url, &u) != 0) return ZHTTP_E_URL;
    /* ★ https 走 TLS。机器上没有 OpenSSL 就在这儿失败并说清楚，
         **绝不改用明文**把密钥发出去 —— 功能不可用是进度问题，密钥泄露是事故。
         这个检查放在 connect 之前：连都不连，省得对面日志里多一条无用记录。 */
    if (u.tls && !ztls_available(resp->err_detail, sizeof(resp->err_detail)))
        return ZHTTP_E_TLS;

#ifdef _WIN32
    zhttp_wsa_once();
#endif

    method = req->method && *req->method ? req->method : "GET";
    body_len = req->body ? (req->body_len ? req->body_len : strlen(req->body)) : 0;
    timeout_ms = req->timeout_ms > 0 ? req->timeout_ms : ZHTTP_DEF_TIMEOUT;
    max_body = req->max_body ? req->max_body : ZHTTP_DEF_MAXBODY;

    rc = sock_connect(&u, timeout_ms, &s);
    if (rc != ZHTTP_OK) return rc;
    c.s = s;
    if (u.tls) {
        int is_cert = 0;
        c.tls = ztls_connect((int)s, u.host, &is_cert,
                             resp->err_detail, sizeof(resp->err_detail));
        if (!c.tls) {
            conn_close(&c);
            return is_cert ? ZHTTP_E_TLS_CERT : ZHTTP_E_TLS;
        }
    }

    /* ---- 拼请求头 ---- */
    reqcap = 512 + strlen(u.path) + strlen(u.host)
             + (req->bearer ? strlen(req->bearer) : 0)
             + (req->extra_headers ? strlen(req->extra_headers) : 0)
             + body_len;
    reqbuf = (char *)malloc(reqcap);
    if (!reqbuf) { zclosesock(s); return ZHTTP_E_OOM; }
    {
        size_t n = 0;
        n += (size_t)snprintf(reqbuf + n, reqcap - n,
                              "%s %s HTTP/1.1\r\nHost: %s", method, u.path, u.host);
        if (u.port != 80) n += (size_t)snprintf(reqbuf + n, reqcap - n, ":%d", u.port);
        /* Connection: close —— 不做连接复用。桌宠的请求稀疏，
           复用省下的那点握手时间换不来连接池那堆状态机的复杂度。 */
        n += (size_t)snprintf(reqbuf + n, reqcap - n,
                              "\r\nUser-Agent: zhuochong/1.0\r\nAccept: */*\r\nConnection: close\r\n");
        if (req->bearer && *req->bearer)
            n += (size_t)snprintf(reqbuf + n, reqcap - n,
                                  "Authorization: Bearer %s\r\n", req->bearer);
        if (req->extra_headers && *req->extra_headers)
            n += (size_t)snprintf(reqbuf + n, reqcap - n, "%s", req->extra_headers);
        if (body_len) {
            snprintf(lenbuf, sizeof(lenbuf), "%lu", (unsigned long)body_len);
            n += (size_t)snprintf(reqbuf + n, reqcap - n,
                                  "Content-Type: %s\r\nContent-Length: %s\r\n",
                                  req->content_type ? req->content_type : "application/json",
                                  lenbuf);
        }
        n += (size_t)snprintf(reqbuf + n, reqcap - n, "\r\n");
        rc = conn_send_all(&c, reqbuf, n);
        if (rc == ZHTTP_OK && body_len)
            rc = conn_send_all(&c, req->body, body_len);
    }
    free(reqbuf);
    if (rc != ZHTTP_OK) { conn_close(&c); return rc; }

    /* ---- 读到对面关闭（我们声明了 Connection: close）---- */
    for (;;) {
        char tmp[4096];
        int n = conn_recv(&c, tmp, sizeof(tmp));
        if (n == 0) break;
        if (n == -2) continue;                                   /* 被打断，重试 */
        if (n == -3) { rc = ZHTTP_E_TIMEOUT; goto fail; }
        if (n < 0)   { rc = ZHTTP_E_RECV;    goto fail; }
        if (zbuf_add(&raw, tmp, (size_t)n) != 0) { rc = ZHTTP_E_OOM; goto fail; }
        /* 头读全了就可以开始判断要不要继续读（Content-Length 够了就停） */
        if (!hdr_end) {
            char *e = strstr(raw.p, "\r\n\r\n");
            if (e) hdr_end = (size_t)(e - raw.p) + 4;
            else {
                e = strstr(raw.p, "\n\n");       /* 容忍不标准的只用 LF */
                if (e) hdr_end = (size_t)(e - raw.p) + 2;
            }
        }
        if (hdr_end) {
            char cl[32];
            char saved = raw.p[hdr_end];
            raw.p[hdr_end] = 0;
            if (hdr_find(raw.p, "Content-Length", cl, sizeof(cl))) {
                size_t want = (size_t)strtoul(cl, NULL, 10);
                raw.p[hdr_end] = saved;
                if (raw.len - hdr_end >= want) break;
            } else {
                raw.p[hdr_end] = saved;
            }
        }
        if (raw.len > max_body + 65536u) { resp->truncated = 1; break; }
    }
    conn_close(&c);
    s = ZSOCK_BAD;

    if (!hdr_end) {
        char *e = raw.p ? strstr(raw.p, "\r\n\r\n") : NULL;
        if (e) hdr_end = (size_t)(e - raw.p) + 4;
    }
    if (!raw.p || !hdr_end) { rc = ZHTTP_E_PROTO; goto fail; }

    /* ---- 状态行 ---- */
    if (strncmp(raw.p, "HTTP/1.", 7) != 0) { rc = ZHTTP_E_PROTO; goto fail; }
    {
        const char *sp = strchr(raw.p, ' ');
        if (!sp) { rc = ZHTTP_E_PROTO; goto fail; }
        resp->status = atoi(sp + 1);
        if (resp->status < 100 || resp->status > 599) { rc = ZHTTP_E_PROTO; goto fail; }
    }

    /* ---- 响应体 ---- */
    {
        char saved = raw.p[hdr_end];
        char te[32];
        int chunked;
        raw.p[hdr_end] = 0;
        chunked = hdr_find(raw.p, "Transfer-Encoding", te, sizeof(te))
                  && strstr(te, "chunked") != NULL;
        raw.p[hdr_end] = saved;
        (void)head;

        if (chunked) {
            if (dechunk(raw.p + hdr_end, raw.len - hdr_end, &out) != 0) {
                rc = ZHTTP_E_PROTO; goto fail;
            }
        } else {
            if (zbuf_add(&out, raw.p + hdr_end, raw.len - hdr_end) != 0) {
                rc = ZHTTP_E_OOM; goto fail;
            }
        }
    }
    if (out.len > max_body) {
        out.len = max_body;
        out.p[out.len] = 0;
        resp->truncated = 1;
    }
    if (!out.p) {                     /* 空体也要给个合法的 "" */
        out.p = (char *)calloc(1, 1);
        if (!out.p) { rc = ZHTTP_E_OOM; goto fail; }
    }
    resp->body = out.p;
    resp->body_len = out.len;
    free(raw.p);
    return ZHTTP_OK;

fail:
    /* 用 conn_close 而不是 zclosesock：出错路径上 TLS 对象也要释放，
       否则每失败一次漏一个 SSL_CTX。 */
    conn_close(&c);
    s = ZSOCK_BAD;
    free(raw.p);
    free(out.p);
    memset(resp, 0, sizeof(*resp));
    return rc;
}

void zhttp_resp_free(zhttp_resp *r)
{
    if (!r) return;
    free(r->body);
    r->body = NULL;
    r->body_len = 0;
}
