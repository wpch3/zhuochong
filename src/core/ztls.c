/* ztls —— 见 ztls.h。运行期 dlopen OpenSSL 3.x / 1.1.x。 */
#ifndef _WIN32
#  ifndef _POSIX_C_SOURCE
#    define _POSIX_C_SOURCE 200809L
#  endif
#endif

#include "ztls.h"
#include "zc.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <errno.h>

#ifdef _WIN32
#  include <windows.h>
#  define ZDLHANDLE      HMODULE
#  define ZDLOPEN(p)     LoadLibraryA(p)
#  define ZDLSYM(h, n)   ((void *)GetProcAddress((h), (n)))
#else
#  include <dlfcn.h>
#  include <pthread.h>
#  define ZDLHANDLE      void *
#  define ZDLOPEN(p)     dlopen((p), RTLD_LAZY | RTLD_LOCAL)
#  define ZDLSYM(h, n)   dlsym((h), (n))
#endif

/* ---------------------------------------------------------------- 常量
 *
 * 这些值来自 OpenSSL 的公开头文件。它们是 ABI 的一部分，不会变
 * （变了就是 break ABI，OpenSSL 不会那么干）。
 * 之所以要自己抄一遍，是因为我们没有开发头可 include。
 */
#define ZSSL_VERIFY_PEER                 0x01
#define ZSSL_CTRL_SET_TLSEXT_HOSTNAME    55
#define ZTLSEXT_NAMETYPE_host_name       0
#define ZSSL_CTRL_SET_MIN_PROTO_VERSION  123
#define ZTLS1_2_VERSION                  0x0303
#define ZSSL_ERROR_WANT_READ             2
#define ZSSL_ERROR_WANT_WRITE            3
#define ZSSL_ERROR_SYSCALL               5
#define ZSSL_ERROR_ZERO_RETURN           6
#define ZX509_V_OK                       0

/* ---------------------------------------------------------------- 函数表 */

typedef struct {
    int loaded;                 /* 1 = 可用，-1 = 试过但不行，0 = 还没试 */
    char why[256];              /* loaded == -1 时的人话 */
    /* 两个要分开写：ZDLHANDLE 是 void*，写成 `ZDLHANDLE a, b;`
       展开后第二个会变成裸 void —— typedef 省掉就会踩的老坑。 */
    ZDLHANDLE hssl;
    ZDLHANDLE hcrypto;

    int         (*OPENSSL_init_ssl)(unsigned long long opts, const void *settings);
    const void *(*TLS_client_method)(void);
    void       *(*SSL_CTX_new)(const void *meth);
    void        (*SSL_CTX_free)(void *ctx);
    int         (*SSL_CTX_set_default_verify_paths)(void *ctx);
    int         (*SSL_CTX_load_verify_locations)(void *ctx, const char *f, const char *d);
    void        (*SSL_CTX_set_verify)(void *ctx, int mode, void *cb);
    long        (*SSL_CTX_ctrl)(void *ctx, int cmd, long larg, void *parg);
    void       *(*SSL_new)(void *ctx);
    void        (*SSL_free)(void *ssl);
    int         (*SSL_set_fd)(void *ssl, int fd);
    long        (*SSL_ctrl)(void *ssl, int cmd, long larg, void *parg);
    int         (*SSL_set1_host)(void *ssl, const char *host);
    int         (*SSL_connect)(void *ssl);
    int         (*SSL_read)(void *ssl, void *buf, int num);
    int         (*SSL_write)(void *ssl, const void *buf, int num);
    int         (*SSL_get_error)(const void *ssl, int ret);
    int         (*SSL_shutdown)(void *ssl);
    long        (*SSL_get_verify_result)(const void *ssl);

    const char *(*X509_verify_cert_error_string)(long n);
    unsigned long (*ERR_get_error)(void);
    void        (*ERR_error_string_n)(unsigned long e, char *buf, size_t len);
} ztls_api;

static ztls_api A;

struct ztls {
    void *ctx;
    void *ssl;
};

/* 不同发行版的名字不一样，挨个试。顺序是"新的在前"。 */
static const char *SSL_NAMES[] = {
#ifdef _WIN32
    "libssl-3-x64.dll", "libssl-3.dll", "libssl-1_1-x64.dll", "ssleay32.dll",
#else
    "libssl.so.3", "libssl.so.1.1", "libssl.so",
#endif
    NULL
};
static const char *CRYPTO_NAMES[] = {
#ifdef _WIN32
    "libcrypto-3-x64.dll", "libcrypto-3.dll", "libcrypto-1_1-x64.dll", "libeay32.dll",
#else
    "libcrypto.so.3", "libcrypto.so.1.1", "libcrypto.so",
#endif
    NULL
};

static ZDLHANDLE try_open(const char **names, const char **picked)
{
    int i;
    for (i = 0; names[i]; ++i) {
        ZDLHANDLE h = ZDLOPEN(names[i]);
        if (h) { if (picked) *picked = names[i]; return h; }
    }
    return NULL;
}

/* 取符号。少一个就整个不可用 —— 半套函数比没有更危险：
   万一少的恰好是 SSL_get_verify_result，就会变成"连上了但没验证书"。 */
#define GETSYM(h, field, name)                                              \
    do {                                                                     \
        *(void **)(&A.field) = ZDLSYM(h, name);                              \
        if (!A.field) { missing = name; goto nope; }                         \
    } while (0)

static void load_once(void)
{
    const char *sslname = "?", *cryptoname = "?";
    const char *missing = NULL;

    A.hssl = try_open(SSL_NAMES, &sslname);
    if (!A.hssl) {
        z_snprintf(A.why, sizeof(A.why),
                   "这台机器上找不到 OpenSSL 运行库（试过 %s 等）—— "
                   "云端模型连不上，本地模型照常用。装一下系统的 openssl 就能恢复。",
                   SSL_NAMES[0]);
        A.loaded = -1;
        return;
    }
    A.hcrypto = try_open(CRYPTO_NAMES, &cryptoname);
    if (!A.hcrypto) {
        z_snprintf(A.why, sizeof(A.why),
                   "找到了 %s 但找不到配套的 libcrypto —— OpenSSL 装得不完整", sslname);
        A.loaded = -1;
        return;
    }

    GETSYM(A.hssl, OPENSSL_init_ssl,                 "OPENSSL_init_ssl");
    GETSYM(A.hssl, TLS_client_method,                "TLS_client_method");
    GETSYM(A.hssl, SSL_CTX_new,                      "SSL_CTX_new");
    GETSYM(A.hssl, SSL_CTX_free,                     "SSL_CTX_free");
    GETSYM(A.hssl, SSL_CTX_set_default_verify_paths, "SSL_CTX_set_default_verify_paths");
    GETSYM(A.hssl, SSL_CTX_load_verify_locations,    "SSL_CTX_load_verify_locations");
    GETSYM(A.hssl, SSL_CTX_set_verify,               "SSL_CTX_set_verify");
    GETSYM(A.hssl, SSL_CTX_ctrl,                     "SSL_CTX_ctrl");
    GETSYM(A.hssl, SSL_new,                          "SSL_new");
    GETSYM(A.hssl, SSL_free,                         "SSL_free");
    GETSYM(A.hssl, SSL_set_fd,                       "SSL_set_fd");
    GETSYM(A.hssl, SSL_ctrl,                         "SSL_ctrl");
    /* SSL_set1_host 是 1.1.0 才有的。没有它就没有主机名校验，
       而没有主机名校验的"验证书"是假的（任何合法证书都能冒充任何站），
       所以这里宁可判定整个 TLS 不可用。 */
    GETSYM(A.hssl, SSL_set1_host,                    "SSL_set1_host");
    GETSYM(A.hssl, SSL_connect,                      "SSL_connect");
    GETSYM(A.hssl, SSL_read,                         "SSL_read");
    GETSYM(A.hssl, SSL_write,                        "SSL_write");
    GETSYM(A.hssl, SSL_get_error,                    "SSL_get_error");
    GETSYM(A.hssl, SSL_shutdown,                     "SSL_shutdown");
    GETSYM(A.hssl, SSL_get_verify_result,            "SSL_get_verify_result");

    GETSYM(A.hcrypto, X509_verify_cert_error_string, "X509_verify_cert_error_string");
    GETSYM(A.hcrypto, ERR_get_error,                 "ERR_get_error");
    GETSYM(A.hcrypto, ERR_error_string_n,            "ERR_error_string_n");

    A.OPENSSL_init_ssl(0, NULL);
    A.loaded = 1;
    return;

nope:
    z_snprintf(A.why, sizeof(A.why),
               "%s 里缺符号 %s —— 版本太老（需要 OpenSSL 1.1.0 以上）",
               sslname, missing ? missing : "?");
    A.loaded = -1;
}

#ifndef _WIN32
static pthread_once_t g_once = PTHREAD_ONCE_INIT;
static void load_once_wrap(void) { load_once(); }
#endif

static void ensure_loaded(void)
{
#ifndef _WIN32
    pthread_once(&g_once, load_once_wrap);
#else
    /* Windows 版预览是单线程 UI 循环，这里用简单标志即可 */
    if (A.loaded == 0) load_once();
#endif
}

int ztls_available(char *why, size_t cap)
{
    ensure_loaded();
    if (A.loaded == 1) {
        if (why && cap) why[0] = 0;
        return 1;
    }
    if (why && cap) z_strlcpy(why, A.why, cap);
    return 0;
}

/* 把 OpenSSL 的错误栈转成一行人话（它那套 error string 是英文且很长，
   但出错时宁可啰嗦也不要只给个数字）。 */
static void err_stack(char *out, size_t cap)
{
    unsigned long e = A.ERR_get_error();
    if (!e) { z_strlcpy(out, "没有更多信息", cap); return; }
    A.ERR_error_string_n(e, out, cap);
    while (A.ERR_get_error()) { /* 把栈清干净，免得污染下一次调用 */ }
}

ztls *ztls_connect(int fd, const char *host, int *is_cert, char *err, size_t cap)
{
    ztls *t;
    long vr;

    if (is_cert) *is_cert = 0;
    if (err && cap) err[0] = 0;

    if (!ztls_available(err, cap)) return NULL;
    if (!host || !*host) {
        if (err) z_strlcpy(err, "没有域名，无法校验证书", cap);
        return NULL;
    }

    t = (ztls *)calloc(1, sizeof(*t));
    if (!t) { if (err) z_strlcpy(err, "内存不够", cap); return NULL; }

    t->ctx = A.SSL_CTX_new(A.TLS_client_method());
    if (!t->ctx) {
        if (err) z_strlcpy(err, "SSL_CTX_new 失败", cap);
        free(t);
        return NULL;
    }

    /* TLS 1.0/1.1 早就该退休了，明确要求 1.2 起步 */
    A.SSL_CTX_ctrl(t->ctx, ZSSL_CTRL_SET_MIN_PROTO_VERSION, ZTLS1_2_VERSION, NULL);

    /* 信任根：默认用系统证书库。
       ZHUOCHONG_CA_FILE 可以**额外**指定一个 CA 文件（自建服务 / 测试用自签名）。
       注意这是"多信一个"，不是"谁都信" —— 没有跳过校验的开关。 */
    {
        const char *ca = getenv("ZHUOCHONG_CA_FILE");
        int ok = 0;
        if (ca && *ca) ok = A.SSL_CTX_load_verify_locations(t->ctx, ca, NULL);
        if (!ca || !*ca) ok = A.SSL_CTX_set_default_verify_paths(t->ctx);
        if (!ok) {
            if (err)
                z_snprintf(err, cap, "装不上信任根（%s）—— 系统证书库可能坏了",
                           (ca && *ca) ? ca : "系统默认");
            A.SSL_CTX_free(t->ctx);
            free(t);
            return NULL;
        }
    }
    A.SSL_CTX_set_verify(t->ctx, ZSSL_VERIFY_PEER, NULL);

    t->ssl = A.SSL_new(t->ctx);
    if (!t->ssl) {
        if (err) z_strlcpy(err, "SSL_new 失败", cap);
        A.SSL_CTX_free(t->ctx);
        free(t);
        return NULL;
    }

    /* SNI：现在一个 IP 上挂几十个站是常态，不发 SNI 很多服务器直接拒握手 */
    A.SSL_ctrl(t->ssl, ZSSL_CTRL_SET_TLSEXT_HOSTNAME, ZTLSEXT_NAMETYPE_host_name,
               (void *)(size_t)host);
    /* 主机名校验：**这一行是"验证书"的一半**。
       只验签名链不验名字的话，攻击者拿一张自己域名的合法证书就能冒充任何站。 */
    if (A.SSL_set1_host(t->ssl, host) != 1) {
        if (err) z_snprintf(err, cap, "设置待校验域名失败：%s", host);
        A.SSL_free(t->ssl);
        A.SSL_CTX_free(t->ctx);
        free(t);
        return NULL;
    }

    A.SSL_set_fd(t->ssl, fd);

    if (A.SSL_connect(t->ssl) != 1) {
        char detail[192];
        vr = A.SSL_get_verify_result(t->ssl);
        if (vr != ZX509_V_OK) {
            const char *vs = A.X509_verify_cert_error_string(vr);
            if (is_cert) *is_cert = 1;
            if (err)
                z_snprintf(err, cap,
                           "证书验不过（%s）—— 不会继续发送，"
                           "因为验不过的 https 和明文没区别",
                           vs ? vs : "未知原因");
        } else {
            err_stack(detail, sizeof(detail));
            if (err) z_snprintf(err, cap, "TLS 握手失败：%s", detail);
        }
        A.SSL_free(t->ssl);
        A.SSL_CTX_free(t->ctx);
        free(t);
        return NULL;
    }

    /* 握手成功后再查一次。SSL_VERIFY_PEER 下握手失败就会被上面拦住，
       但这一行是"万一哪天有人把 set_verify 改成 NONE"的最后一道 ——
       白拿的保险，不要省。 */
    vr = A.SSL_get_verify_result(t->ssl);
    if (vr != ZX509_V_OK) {
        const char *vs = A.X509_verify_cert_error_string(vr);
        if (is_cert) *is_cert = 1;
        if (err) z_snprintf(err, cap, "证书验不过（%s）", vs ? vs : "未知原因");
        A.SSL_free(t->ssl);
        A.SSL_CTX_free(t->ctx);
        free(t);
        return NULL;
    }

    return t;
}

int ztls_read(ztls *t, void *buf, int len, int *timed_out)
{
    int n;
    if (timed_out) *timed_out = 0;
    if (!t || !t->ssl) return -1;
    n = A.SSL_read(t->ssl, buf, len);
    if (n > 0) return n;
    {
        int e = A.SSL_get_error(t->ssl, n);
        if (e == ZSSL_ERROR_ZERO_RETURN) return 0;      /* 对端正常关闭 */
        if (e == ZSSL_ERROR_SYSCALL) {
            /* fd 上设了 SO_RCVTIMEO，超时会以 EAGAIN 冒出来 */
#ifndef _WIN32
            if (errno == EAGAIN || errno == EWOULDBLOCK) {
                if (timed_out) *timed_out = 1;
                return -1;
            }
            if (errno == EINTR) return -2;              /* 调用方重试 */
#endif
            if (n == 0) return 0;   /* 对端直接断了 TCP（没走 close_notify）。
                                       HTTP 里这很常见，当成正常收尾。 */
            return -1;
        }
        if (e == ZSSL_ERROR_WANT_READ || e == ZSSL_ERROR_WANT_WRITE) return -2;
    }
    return -1;
}

int ztls_write(ztls *t, const void *buf, int len)
{
    if (!t || !t->ssl) return -1;
    return A.SSL_write(t->ssl, buf, len);
}

void ztls_close(ztls *t)
{
    if (!t) return;
    if (t->ssl) {
        A.SSL_shutdown(t->ssl);     /* 失败也无所谓，反正马上就关 fd 了 */
        A.SSL_free(t->ssl);
    }
    if (t->ctx) A.SSL_CTX_free(t->ctx);
    free(t);
}
