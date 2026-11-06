/* tls_probe —— TLS 这一层的常驻闸门（G54 / T61.9）
 *
 * 为什么不塞进 test_core：它需要一个**真的 TLS 服务端**。
 * 在 C 里起一个就得再 dlopen 一批服务端符号、还要在测试里造证书，
 * 那堆脚手架比被测的东西还重。所以这里只做客户端，
 * 服务端和证书由 tools/check_tls.py 准备好再调用本程序。
 *
 * 用法：tls_probe <https-base-url> <ca-file>
 *   例：tls_probe https://localhost:8443 /tmp/x/cert.pem
 *
 * ★ 这个闸门盯的是一件事：**证书校验是真的开着**。
 *   "能连上 https" 很容易做到 —— 把校验关掉就行，而那样的 https
 *   在中间人面前和明文没有区别，偏偏跑在上面的是用户的 API key。
 *   所以下面每一条"必须被拒"的用例都比"必须能通"更重要。
 */
/* setenv/unsetenv 是 POSIX.1-2001 的，-std=c11 严格模式不暴露 */
#ifndef _WIN32
#  ifndef _POSIX_C_SOURCE
#    define _POSIX_C_SOURCE 200809L
#  endif
#endif

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "core/zhttp.h"
#include "core/ztls.h"
#include "core/zgateway.h"
#include "core/zrelay.h"
#include "core/zc.h"

static int g_pass = 0, g_fail = 0;

static void ck(int ok, const char *what, const char *detail)
{
    if (ok) { g_pass++; printf("  通过  %s\n", what); }
    else    { g_fail++; printf("  失败  %s\n        | %s\n", what, detail ? detail : ""); }
}

static void section(const char *s) { printf("== %s ==\n", s); }

int main(int argc, char **argv)
{
    const char *base = argc > 1 ? argv[1] : "https://localhost:8443";
    const char *ca   = argc > 2 ? argv[2] : NULL;
    char url[512], why[256];
    zhttp_req q;
    zhttp_resp r;
    zhttp_err e;

    if (!ca) { printf("用法：tls_probe <https-base> <ca-file>\n"); return 2; }
    z_snprintf(url, sizeof(url), "%s/v1/chat/completions", base);

    section("TLS 能力自报");
    {
        int av = ztls_available(why, sizeof(why));
        ck(av == 1, "这台机器上 dlopen 得到 OpenSSL", why);
        if (!av) {
            /* 没有 OpenSSL 不算测试失败 —— 那是机器的事。
               但必须给出人话，而且后面每一条都只能验"拒绝"那一半。 */
            printf("     （本机没有 OpenSSL：%s）\n", why);
            ck(why[0] != 0, "用不了的时候要说清为什么", "why 是空的");
        }
    }

    section("自签名证书 + 默认信任根 ⇒ 必须拒绝");
    unsetenv("ZHUOCHONG_CA_FILE");
    memset(&q, 0, sizeof(q));
    q.method = "POST";
    q.url = url;
    q.body = "{\"model\":\"m\",\"messages\":[{\"role\":\"user\",\"content\":\"hi\"}]}";
    q.timeout_ms = 8000;
    e = zhttp_send(&q, &r);
    ck(e != ZHTTP_OK, "绝不能握手成功", zhttp_err_text(e));
    ck(e == ZHTTP_E_TLS_CERT, "要明确判成\"证书问题\"而不是笼统的网络错", zhttp_err_text(e));
    ck(r.status == 0, "一个字节都不该发出去（status 必须是 0）", "");
    ck(strstr(r.err_detail, "证书") != NULL, "错误要说人话", r.err_detail);
    zhttp_resp_free(&r);

    section("把这张证书加进信任根 ⇒ 应当通");
    setenv("ZHUOCHONG_CA_FILE", ca, 1);
    e = zhttp_send(&q, &r);
    ck(e == ZHTTP_OK, "握手 + 请求应当成功", r.err_detail[0] ? r.err_detail : zhttp_err_text(e));
    ck(r.status == 200, "HTTP 200", "");
    ck(r.body && strstr(r.body, "over-TLS") != NULL,
       "服务端确认收到的是 TLS 连接", r.body ? r.body : "");
    zhttp_resp_free(&r);

    section("同一张证书，改用 IP 去连 ⇒ 域名对不上，必须拒绝");
    {
        /* 这条专门盯"主机名校验"。只验签名链不验名字的话，
           攻击者拿一张自己域名的合法证书就能冒充任何站 —— 等于没验。 */
        char ipurl[512];
        const char *p = strstr(base, "localhost");
        if (p) {
            z_snprintf(ipurl, sizeof(ipurl), "https://127.0.0.1%s/v1/chat/completions",
                       p + strlen("localhost"));
            q.url = ipurl;
            e = zhttp_send(&q, &r);
            ck(e == ZHTTP_E_TLS_CERT, "域名对不上要判证书错", zhttp_err_text(e));
            ck(r.status == 0, "一个字节都不该发出去", "");
            zhttp_resp_free(&r);
            q.url = url;
        }
    }

    section("密钥经 TLS 送达（整条路最终要运的就是它）");
    q.bearer = "sk-probe-7788";
    e = zhttp_send(&q, &r);
    ck(e == ZHTTP_OK && r.body && strstr(r.body, "Bearer sk-probe-7788") != NULL,
       "Authorization 头正确到达服务端", r.body ? r.body : zhttp_err_text(e));
    zhttp_resp_free(&r);
    q.bearer = NULL;

    section("走完整的 zrelay：云端供应商 + secret:// 密钥 + 记账");
    {
        zgateway g;
        zdiag d;
        zrelay_chat_req rq;
        zrelay_result rr;
        char rpath[512], json[1600];
        FILE *f;
        const char *tmpdir = getenv("ZC_TLS_TMP");
        if (!tmpdir) tmpdir = "/tmp";
        z_snprintf(rpath, sizeof(rpath), "%s/tls_routes.json", tmpdir);
        z_snprintf(json, sizeof(json),
            "{\"schema_version\":\"1.0\",\"strategy\":\"prefer_local\",\"fallback\":true,"
            "\"routes\":[{\"cap\":\"chat.completion\",\"provider\":\"tlscloud\","
             "\"model\":\"gpt-test\",\"priority\":50,\"local\":false,\"enabled\":true,"
             "\"free\":false,\"price_in\":0.001,\"price_out\":0.002,\"price_per\":1000}],"
            "\"endpoints\":[{\"id\":\"tlscloud\",\"kind\":\"openai_compatible\","
             "\"local\":false,\"enabled\":true,\"base_url\":\"%s/v1\","
             "\"auth_type\":\"bearer\",\"key_ref\":\"secret://tlscloud\","
             "\"auth_header\":\"\",\"chat_path\":\"/chat/completions\"}]}", base);
        f = fopen(rpath, "wb");
        if (f) { fputs(json, f); fclose(f); }
        zdiag_init(&d);
        if (zgw_load(&g, rpath, &d) != 0) {
            ck(0, "测试用路由表能加载", rpath);
        } else {
            memset(&rq, 0, sizeof(rq));
            rq.system_prompt = "你是小寻，一只猫娘。";
            rq.user_text = "云端你好";
            rq.timeout_ms = 8000;
            rq.route.local_load_pct = -1;

            /* ① 没配密钥：一个字节都不许发 */
            unsetenv("ZHUOCHONG_SECRET_TLSCLOUD");
            ck(zrelay_chat(&g, &rq, &rr) != 0 && rr.http_status == 0,
               "没配密钥时不许发（空 key 发出去只换回 401，话却已经送出去了）", rr.err);
            ck(strstr(rr.err, "密钥") != NULL, "要说清是密钥的问题", rr.err);
            zrelay_result_free(&rr);

            /* ② 配了密钥但不信任证书：也不许发 */
            setenv("ZHUOCHONG_SECRET_TLSCLOUD", "sk-cloud-abc123", 1);
            unsetenv("ZHUOCHONG_CA_FILE");
            ck(zrelay_chat(&g, &rq, &rr) != 0 && rr.http_status == 0,
               "证书不可信时不许发", rr.err);
            ck(strstr(rr.err, "证书") != NULL, "错误里要点明是证书", rr.err);
            ck(zgw_held_amount(&g) == 0.0, "失败不许留悬空预扣", "");
            zrelay_result_free(&rr);

            /* ③ 信任证书：云端整条链路应当通 */
            setenv("ZHUOCHONG_CA_FILE", ca, 1);
            ck(zrelay_chat(&g, &rq, &rr) == 0 && rr.ok, "云端真链路应当通", rr.err);
            ck(rr.http_status == 200, "HTTP 200", "");
            ck(rr.local == 0, "这家是云端（local=0）", "");
            ck(rr.text && strstr(rr.text, "Bearer sk-cloud-abc123") != NULL,
               "密钥经 TLS 送到了服务端", rr.text ? rr.text : "");
            ck(rr.text && strstr(rr.text, "云端你好") != NULL, "用户的话送到了", "");
            ck(rr.tokens_in == 11 && rr.tokens_out == 22,
               "记账用服务端回的实际 usage", "");
            ck(rr.cost > 0.0, "云端这次要真的扣钱（不是免费栈）", "");
            ck(zgw_held_amount(&g) == 0.0, "预扣已结清", "");
            zrelay_result_free(&rr);
            remove(rpath);
        }
    }

    printf("\n通过 %d 项，失败 %d 项\n", g_pass, g_fail);
    printf("%s\n", g_fail ? "结论：不通过" : "结论：全部通过");
    return g_fail ? 1 : 0;
}
