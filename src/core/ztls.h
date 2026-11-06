/* ztls —— TLS 客户端，运行期 dlopen OpenSSL（G54 / T61.9）
 *
 * 为什么是 dlopen 而不是 -lssl：
 *   这台机器（以及不少精简镜像）上**只有运行库没有开发头** ——
 *   /usr/lib/.../libssl.so.3 在，/usr/include/openssl/ssl.h 不在。
 *   链接期依赖会让整个项目在这种机器上编不出来，而这个项目的硬规矩是零第三方依赖。
 *   运行期 dlopen 的代价是要自己声明用到的那十几个函数原型
 *   （OpenSSL 3.x 的 ABI 是稳定的，这些签名十年没动过），
 *   换来的是：有库就能连云端，没库就把话说清楚，两种情况都不影响编译和本地功能。
 *
 * ★ 这里没有、也绝不会有"跳过证书校验"的开关。
 *   不验证书的 https 在中间人面前和明文 http 没有区别，
 *   而这条链路上跑的是用户的 API key 和聊天内容。
 *   要连自签名的服务（比如测试），把 CA 证书路径放进环境变量
 *   ZHUOCHONG_CA_FILE —— 那是"多信一个 CA"，不是"谁都信"。
 */
#ifndef ZTLS_H
#define ZTLS_H

#include <stddef.h>

typedef struct ztls ztls;

/* 这台机器上能不能用 TLS。
 * 返回 1 = 能；0 = 不能，原因写进 why（人话，可以直接给用户看）。
 * why 可以传 NULL。第一次调用会真的去 dlopen，之后走缓存。 */
int ztls_available(char *why, size_t cap);

/* 在一个**已经连上**的 socket 上做 TLS 握手。
 *   fd        已连接的 socket（Windows 上传 (int)SOCKET）
 *   host      服务器域名。SNI 和证书名校验都要用它 —— 两样都不能省：
 *             少了 SNI 很多站直接握手失败；少了名字校验，
 *             任何一张合法证书都能冒充任何站。
 *   is_cert   出参，可为 NULL。1 = 失败原因是证书不可信
 *             （这和"连不上"要分开说：前者是安全问题，后者是网络问题）
 *   err/cap   出参，失败原因（人话）
 * 返回非 NULL = 握手成功。失败返回 NULL，**不会**关掉 fd（由调用方负责）。 */
ztls *ztls_connect(int fd, const char *host, int *is_cert, char *err, size_t cap);

/* 读。语义同 recv：>0 收到的字节数，0 = 对端正常关闭，<0 = 出错。
 * 出错时 *timed_out（可为 NULL）置 1 表示是超时而不是别的错。 */
int ztls_read(ztls *t, void *buf, int len, int *timed_out);

/* 写。语义同 send：返回写出的字节数，<=0 = 出错。 */
int ztls_write(ztls *t, const void *buf, int len);

/* 关掉 TLS 层并释放。**不关 fd** —— fd 是调用方开的，由调用方关。 */
void ztls_close(ztls *t);

#endif /* ZTLS_H */
