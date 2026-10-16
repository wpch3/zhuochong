/*
 * zc.h - 桌宠项目公共基础层（Core Foundation）
 *
 * 提供：错误结构、日志、字符串与文件工具。
 * 这一层不依赖任何平台 API，Windows 与 Linux 沙箱都能编译。
 *
 * 许可：本项目原创代码。第三方库见 src/third_party/。
 */
#ifndef ZC_H
#define ZC_H

#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdarg.h>

#ifdef __cplusplus
extern "C" {
#endif

/* ---------------------------------------------------------------- 版本 */
#define ZC_VERSION "0.1.0"

/* ---------------------------------------------------------------- 错误 */
/* 统一的错误/诊断结构：任何一步出错都要能指出“哪个文件、哪个字段、什么原因”。 */
#define ZERR_MSG_MAX 512
#define ZERR_FILE_MAX 384

typedef struct {
    char file[ZERR_FILE_MAX]; /* 来源文件（相对仓库根或绝对路径） */
    int  line;                /* 行号，未知为 0 */
    int  col;                 /* 列号，未知为 0 */
    char field[128];          /* 字段路径，如 "ui.window.scale.min" */
    char msg[ZERR_MSG_MAX];   /* 人类可读说明（UTF-8，中文） */
} zerr;

void  zerr_clear(zerr *e);
void  zerr_set(zerr *e, const char *file, int line, int col, const char *field,
               const char *fmt, ...);
/* 复制错误（保留已有信息，不覆盖更早的错误） */
void  zerr_copy(zerr *dst, const zerr *src);

/* ------------------------------------------------------- 诊断（可累积） */
/* 一次加载可能产生多条诊断：既有致命错误，也有可以继续的警告。 */
#define ZDIAG_MAX 32
typedef struct {
    zerr items[ZDIAG_MAX];
    int  count;
    int  error_count; /* 致命错误条数（有则加载失败） */
} zdiag;

void zdiag_init(zdiag *d);
void zdiag_error(zdiag *d, const char *file, int line, int col, const char *field,
                 const char *fmt, ...);
void zdiag_warn(zdiag *d, const char *file, int line, int col, const char *field,
                const char *fmt, ...);
int  zdiag_ok(const zdiag *d);   /* 没有致命错误 */
void zdiag_print(const zdiag *d, FILE *out);

/* ------------------------------------------------------------------ 日志 */
typedef enum { ZLOG_DEBUG = 0, ZLOG_INFO, ZLOG_WARN, ZLOG_ERROR } zlog_level;

/* 日志同时写 stderr 与文件（若设置了文件）。UTF-8 中文可读。 */
void zlog_open(const char *path);          /* path 为 NULL 则只写 stderr */
void zlog_close(void);
void zlog_set_level(zlog_level lv);
void zlog_write(zlog_level lv, const char *tag, const char *fmt, ...);
const char *zlog_path(void);

#define ZLOGD(tag, ...) zlog_write(ZLOG_DEBUG, tag, __VA_ARGS__)
#define ZLOGI(tag, ...) zlog_write(ZLOG_INFO,  tag, __VA_ARGS__)
#define ZLOGW(tag, ...) zlog_write(ZLOG_WARN,  tag, __VA_ARGS__)
#define ZLOGE(tag, ...) zlog_write(ZLOG_ERROR, tag, __VA_ARGS__)

/* -------------------------------------------------------------- 内存工具 */
void *z_alloc(size_t n);           /* 失败即记录并 abort（小工具，不做过度容错） */
void *z_calloc(size_t n, size_t sz);
void *z_realloc(void *p, size_t n);
char *z_strdup(const char *s);
char *z_strndup(const char *s, size_t n);

/* -------------------------------------------------------------- 字符串工具 */
char  *z_trim(char *s);                             /* 原地去首尾空白，返回起点 */
int    z_streq(const char *a, const char *b);
int    z_startswith(const char *s, const char *pfx);
int    z_endswith(const char *s, const char *sfx);
size_t z_strlcpy(char *dst, const char *src, size_t cap);
/* 砍掉末尾不完整的 UTF-8 序列。z_strlcpy 按字节截断，中文一超长就会切在
   字符中间产出非法 UTF-8；凡是会被塞进 JSON 的定长中文字段，拷完都要走一遍。 */
void   z_utf8_trim(char *s);
size_t z_snprintf(char *dst, size_t cap, const char *fmt, ...);
/* 按分隔符切分（原地修改 buf）。返回片段数，最多 max 段。 */
int    z_split(char *buf, char sep, char **out, int max);
/* 是否为绝对路径 */
int    z_is_abs(const char *p);

/* -------------------------------------------------------------- 路径工具 */
/* 拼接，自动补 '/'。结果写入 out。 */
void z_path_join(char *out, size_t cap, const char *a, const char *b);
/* 取父目录（原地修改），返回 out。 */
char *z_dirname(char *path);
/* 取文件名（含扩展名） */
const char *z_basename(const char *path);
/* 扩展名（含点），没有则返回 "" */
const char *z_extension(const char *path);
/* 递归创建目录（会创建父级）。返回 0 成功，-1 失败。 */
int   z_mkdir_p(const char *path);
int   z_file_exists(const char *path);
int   z_is_dir(const char *path);
/* 把相对路径解析为“相对可执行文件/项目根”的路径。详见实现。 */
void  z_resolve_path(char *out, size_t cap, const char *base_dir, const char *rel_or_abs);

/* -------------------------------------------------------------- 文件读写 */
/* 读整个文件到堆内存（附加 '\0'）。失败返回 NULL 并写 err。 */
char *z_read_file(const char *path, size_t *out_len, zerr *err);
/* 写文件（会先创建父目录）。返回 0 成功。 */
int   z_write_file(const char *path, const void *data, size_t len, zerr *err);
/* 追加一行（用于日志/记录） */
int   z_append_line(const char *path, const char *line);

/* -------------------------------------------------------------- 时间工具 */
double z_now_seconds(void);   /* 单调时钟，秒 */
void   z_sleep_ms(int ms);

/* ----------------------------------------------------------------- 数学 */
#ifndef ZC_MIN
#  define ZC_MIN(a, b) ((a) < (b) ? (a) : (b))
#  define ZC_MAX(a, b) ((a) > (b) ? (a) : (b))
#  define ZC_CLAMP(v, lo, hi) (ZC_MIN(ZC_MAX(v, lo), hi))
#endif
double z_lerp(double a, double b, double t);
double z_smoothstep(double t);
/* Live2D 官方的动作淡化曲线 CubismMath.getEasingSine：0.5 − 0.5·cos(πt)，自带 0/1 钳位 */
double z_ease_sine(double t);
/* 缓动函数（动效用，配置里的 ease 名称解析到这里） */
typedef enum {
    ZEASE_LINEAR = 0, ZEASE_IN, ZEASE_OUT, ZEASE_IN_OUT,
    ZEASE_OUT_BACK, ZEASE_OUT_ELASTIC, ZEASE_OUT_BOUNCE
} zease;
zease z_ease_from_name(const char *name); /* 未知返回 ZEASE_LINEAR */
double z_ease_apply(zease e, double t);   /* t ∈ [0,1] → [0,1]（back/elastic 可越界） */

/* xorshift 随机数（确定性，便于测试复现） */
typedef struct { uint64_t s; } zrand;
void   zrand_seed(zrand *r, uint64_t seed);
uint32_t zrand_u32(zrand *r);
double zrand_unit(zrand *r);              /* [0,1) */
double zrand_range(zrand *r, double a, double b);
/* 指数分布（眨眼间隔用） */
double zrand_expo(zrand *r, double mean);

/* ------------------------------------------------ 并行（渲染/编码分块用）
   把 [0,n) 的活分给 n 个 worker 跑。没有线程支持时顺序跑，结果完全一致。
   fn 必须只碰自己那一份数据——所有调用点都有"并行结果 == 串行结果"的闸。 */
void z_parallel_for(int n, void (*fn)(void *ctx, int idx), void *ctx);
/* 可用的硬件并行度（CPU 核数，至少 1）。 */
int  z_hw_threads(void);

#ifdef __cplusplus
}
#endif
#endif /* ZC_H */
