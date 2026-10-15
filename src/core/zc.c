/* zc.c - 公共基础层实现 */
#ifndef _WIN32
#  ifndef _POSIX_C_SOURCE
#    define _POSIX_C_SOURCE 200809L
#  endif
#endif
#include "zc.h"

#include <time.h>
#include <math.h>
#include <ctype.h>
#include <errno.h>
#include <sys/stat.h>
#include <sys/types.h>

#ifdef _WIN32
#  include <direct.h>
#  include <windows.h>
#  define Z_MKDIR(p) _mkdir(p)
#else
#  include <unistd.h>
#  define Z_MKDIR(p) mkdir(p, 0755)
#endif

/* ================================================================= 错误 */
void zerr_clear(zerr *e)
{
    if (!e) return;
    e->file[0] = 0;
    e->line = e->col = 0;
    e->field[0] = 0;
    e->msg[0] = 0;
}

void zerr_set(zerr *e, const char *file, int line, int col, const char *field,
              const char *fmt, ...)
{
    va_list ap;
    if (!e) return;
    zerr_clear(e);
    if (file) z_strlcpy(e->file, file, sizeof(e->file));
    e->line = line;
    e->col = col;
    if (field) z_strlcpy(e->field, field, sizeof(e->field));
    va_start(ap, fmt);
    vsnprintf(e->msg, sizeof(e->msg), fmt, ap);
    va_end(ap);
}

void zerr_copy(zerr *dst, const zerr *src)
{
    if (!dst || !src) return;
    *dst = *src;
}

/* =============================================================== 诊断集 */
void zdiag_init(zdiag *d)
{
    if (!d) return;
    d->count = 0;
    d->error_count = 0;
}

static zerr *zdiag_push(zdiag *d)
{
    if (!d || d->count >= ZDIAG_MAX) return NULL;
    zerr *e = &d->items[d->count++];
    zerr_clear(e);
    return e;
}

void zdiag_error(zdiag *d, const char *file, int line, int col, const char *field,
                 const char *fmt, ...)
{
    zerr *e;
    va_list ap;
    if (!d) return;
    e = zdiag_push(d);
    if (!e) return;
    if (file) z_strlcpy(e->file, file, sizeof(e->file));
    e->line = line; e->col = col;
    if (field) z_strlcpy(e->field, field, sizeof(e->field));
    va_start(ap, fmt);
    vsnprintf(e->msg, sizeof(e->msg), fmt, ap);
    va_end(ap);
    d->error_count++;
    zlog_write(ZLOG_ERROR, "diag", "%s:%d%s%s %s", e->file, e->line,
               e->field[0] ? " " : "", e->field, e->msg);
}

void zdiag_warn(zdiag *d, const char *file, int line, int col, const char *field,
                const char *fmt, ...)
{
    zerr *e;
    va_list ap;
    if (!d) return;
    e = zdiag_push(d);
    if (!e) return;
    if (file) z_strlcpy(e->file, file, sizeof(e->file));
    e->line = line; e->col = col;
    if (field) z_strlcpy(e->field, field, sizeof(e->field));
    va_start(ap, fmt);
    vsnprintf(e->msg, sizeof(e->msg), fmt, ap);
    va_end(ap);
    zlog_write(ZLOG_WARN, "diag", "%s:%d%s%s %s", e->file, e->line,
               e->field[0] ? " " : "", e->field, e->msg);
}

int zdiag_ok(const zdiag *d)
{
    return !d || d->error_count == 0;
}

void zdiag_print(const zdiag *d, FILE *out)
{
    int i;
    if (!d) return;
    for (i = 0; i < d->count; ++i) {
        const zerr *e = &d->items[i];
        char loc[64];
        if (e->line > 0) z_snprintf(loc, sizeof(loc), "%d:%d", e->line, e->col);
        else z_strlcpy(loc, "-", sizeof(loc));
        fprintf(out, "[%s] %s:%s -> %s\n",
                e->file[0] ? "配置" : "配置", e->file[0] ? e->file : "(未指定文件)", loc,
                e->msg[0] ? e->msg : "(无说明)");
        if (e->field[0])
            fprintf(out, "          字段: %s\n", e->field);
    }
}

/* ================================================================== 日志 */
static FILE *g_log_fp = NULL;
static char g_log_path[512] = {0};
static zlog_level g_log_level = ZLOG_INFO;

void zlog_open(const char *path)
{
    zlog_close();
    if (!path) return;
    z_strlcpy(g_log_path, path, sizeof(g_log_path));
    g_log_fp = fopen(path, "a");
    if (!g_log_fp) {
        g_log_path[0] = 0;
        fprintf(stderr, "[log] 无法打开日志文件: %s\n", path);
    }
}

void zlog_close(void)
{
    if (g_log_fp) { fclose(g_log_fp); g_log_fp = NULL; }
}

void zlog_set_level(zlog_level lv) { g_log_level = lv; }
const char *zlog_path(void) { return g_log_path; }

static const char *level_name(zlog_level lv)
{
    switch (lv) {
        case ZLOG_DEBUG: return "DEBUG";
        case ZLOG_INFO:  return "INFO ";
        case ZLOG_WARN:  return "WARN ";
        default:         return "ERROR";
    }
}

void zlog_write(zlog_level lv, const char *tag, const char *fmt, ...)
{
    char buf[2048];
    char line[2240];
    va_list ap;
    time_t t;
    struct tm tmv;
    int n;
    if (lv < g_log_level) return;

    va_start(ap, fmt);
    vsnprintf(buf, sizeof(buf), fmt, ap);
    va_end(ap);

    time(&t);
#ifdef _WIN32
    localtime_s(&tmv, &t);
#else
    localtime_r(&t, &tmv);
#endif
    n = snprintf(line, sizeof(line), "%04d-%02d-%02d %02d:%02d:%02d [%s] %-6s %s\n",
                 tmv.tm_year + 1900, tmv.tm_mon + 1, tmv.tm_mday,
                 tmv.tm_hour, tmv.tm_min, tmv.tm_sec,
                 tag ? tag : "-", level_name(lv), buf);
    if (n < 0) return;

    fputs(line, stderr);
    if (g_log_fp) {
        fputs(line, g_log_fp);
        fflush(g_log_fp);
    }
}

/* ================================================================ 内存 */
void *z_alloc(size_t n)
{
    void *p = malloc(n ? n : 1);
    if (!p) { ZLOGE("mem", "内存分配失败: %zu 字节", n); abort(); }
    return p;
}

void *z_calloc(size_t n, size_t sz)
{
    void *p = calloc(n ? n : 1, sz ? sz : 1);
    if (!p) { ZLOGE("mem", "内存分配失败: %zu x %zu", n, sz); abort(); }
    return p;
}

void *z_realloc(void *p, size_t n)
{
    void *q = realloc(p, n ? n : 1);
    if (!q) { ZLOGE("mem", "内存重分配失败: %zu 字节", n); abort(); }
    return q;
}

char *z_strdup(const char *s)
{
    size_t n;
    char *p;
    if (!s) return NULL;
    n = strlen(s);
    p = (char *)z_alloc(n + 1);
    memcpy(p, s, n + 1);
    return p;
}

char *z_strndup(const char *s, size_t n)
{
    char *p = (char *)z_alloc(n + 1);
    memcpy(p, s, n);
    p[n] = 0;
    return p;
}

/* ============================================================ 字符串 */
char *z_trim(char *s)
{
    char *end;
    if (!s) return s;
    while (*s && (unsigned char)*s <= ' ') s++;
    if (!*s) return s;
    end = s + strlen(s) - 1;
    while (end > s && (unsigned char)*end <= ' ') *end-- = 0;
    return s;
}

int z_streq(const char *a, const char *b)
{
    if (!a || !b) return a == b;
    return strcmp(a, b) == 0;
}

int z_startswith(const char *s, const char *pfx)
{
    size_t n;
    if (!s || !pfx) return 0;
    n = strlen(pfx);
    return strncmp(s, pfx, n) == 0;
}

int z_endswith(const char *s, const char *sfx)
{
    size_t ls, lf;
    if (!s || !sfx) return 0;
    ls = strlen(s); lf = strlen(sfx);
    if (lf > ls) return 0;
    return strcmp(s + (ls - lf), sfx) == 0;
}

size_t z_strlcpy(char *dst, const char *src, size_t cap)
{
    size_t n;
    if (!dst || cap == 0) return 0;
    if (!src) { dst[0] = 0; return 0; }
    n = strlen(src);
    if (n >= cap) n = cap - 1;
    memcpy(dst, src, n);
    dst[n] = 0;
    return n;
}

size_t z_snprintf(char *dst, size_t cap, const char *fmt, ...)
{
    va_list ap;
    int n;
    if (!dst || cap == 0) return 0;
    va_start(ap, fmt);
    n = vsnprintf(dst, cap, fmt, ap);
    va_end(ap);
    if (n < 0) { dst[0] = 0; return 0; }
    if ((size_t)n >= cap) n = (int)cap - 1;
    return (size_t)n;
}

int z_split(char *buf, char sep, char **out, int max)
{
    int n = 0;
    char *p = buf;
    if (!buf || !out || max <= 0) return 0;
    while (n < max) {
        out[n++] = p;
        p = strchr(p, sep);
        if (!p) break;
        *p++ = 0;
        if (n == max) break;
    }
    return n;
}

int z_is_abs(const char *p)
{
    if (!p || !*p) return 0;
#ifdef _WIN32
    if (p[0] == '\\' || p[0] == '/') return 1;
    if (isalpha((unsigned char)p[0]) && p[1] == ':') return 1;
    return 0;
#else
    return p[0] == '/';
#endif
}

/* ================================================================ 路径 */
void z_path_join(char *out, size_t cap, const char *a, const char *b)
{
    size_t la;
    if (!out || cap == 0) return;
    if (!a || !*a) { z_strlcpy(out, b ? b : "", cap); return; }
    if (!b || !*b) { z_strlcpy(out, a, cap); return; }
    la = strlen(a);
    if (la > 0 && (a[la - 1] == '/' || a[la - 1] == '\\'))
        z_snprintf(out, cap, "%s%s", a, b);
    else
        z_snprintf(out, cap, "%s/%s", a, b);
}

char *z_dirname(char *path)
{
    char *s;
    if (!path) return path;
    s = strrchr(path, '/');
#ifdef _WIN32
    {
        char *b = strrchr(path, '\\');
        if (b && (!s || b > s)) s = b;
    }
#endif
    if (!s) { path[0] = '.'; path[1] = 0; return path; }
    if (s == path) { path[1] = 0; return path; }
    *s = 0;
    return path;
}

const char *z_basename(const char *path)
{
    const char *s;
    if (!path) return "";
    s = strrchr(path, '/');
#ifdef _WIN32
    {
        const char *b = strrchr(path, '\\');
        if (b && (!s || b > s)) s = b;
    }
#endif
    return s ? s + 1 : path;
}

const char *z_extension(const char *path)
{
    const char *base = z_basename(path);
    const char *dot = strrchr(base, '.');
    return dot ? dot : "";
}

int z_is_dir(const char *path)
{
    struct stat st;
    if (!path) return 0;
    if (stat(path, &st) != 0) return 0;
    return S_ISDIR(st.st_mode) ? 1 : 0;
}

int z_file_exists(const char *path)
{
    struct stat st;
    if (!path) return 0;
    return stat(path, &st) == 0;
}

int z_mkdir_p(const char *path)
{
    char tmp[1024];
    char *p;
    if (!path || !*path) return -1;
    if (z_is_dir(path)) return 0;
    z_strlcpy(tmp, path, sizeof(tmp));
    for (p = tmp + 1; *p; ++p) {
        if (*p == '/' || *p == '\\') {
            char save = *p;
            *p = 0;
            if (!z_is_dir(tmp)) Z_MKDIR(tmp);
            *p = save;
        }
    }
    if (Z_MKDIR(tmp) == 0) return 0;
    return z_is_dir(tmp) ? 0 : -1;
}

void z_resolve_path(char *out, size_t cap, const char *base_dir, const char *rel_or_abs)
{
    if (!rel_or_abs || !*rel_or_abs) { z_strlcpy(out, "", cap); return; }
    if (z_is_abs(rel_or_abs) || !base_dir || !*base_dir) {
        z_strlcpy(out, rel_or_abs, cap);
        return;
    }
    z_path_join(out, cap, base_dir, rel_or_abs);
}

/* ============================================================ 文件 IO */
char *z_read_file(const char *path, size_t *out_len, zerr *err)
{
    FILE *fp;
    long sz;
    char *buf;
    size_t got;
    if (!path) { zerr_set(err, "", 0, 0, "", "文件路径为空"); return NULL; }
    fp = fopen(path, "rb");
    if (!fp) {
        zerr_set(err, path, 0, 0, "", "无法打开文件: %s", strerror(errno));
        return NULL;
    }
    if (fseek(fp, 0, SEEK_END) != 0) {
        fclose(fp);
        zerr_set(err, path, 0, 0, "", "无法定位文件末尾");
        return NULL;
    }
    sz = ftell(fp);
    if (sz < 0) {
        fclose(fp);
        zerr_set(err, path, 0, 0, "", "无法获取文件大小");
        return NULL;
    }
    rewind(fp);
    buf = (char *)z_alloc((size_t)sz + 1);
    got = fread(buf, 1, (size_t)sz, fp);
    fclose(fp);
    buf[got] = 0;
    if (out_len) *out_len = got;
    return buf;
}

int z_write_file(const char *path, const void *data, size_t len, zerr *err)
{
    char dir[1024];
    FILE *fp;
    if (!path) { zerr_set(err, "", 0, 0, "", "文件路径为空"); return -1; }
    z_strlcpy(dir, path, sizeof(dir));
    z_dirname(dir);
    if (dir[0] && strcmp(dir, ".") != 0) z_mkdir_p(dir);
    fp = fopen(path, "wb");
    if (!fp) {
        zerr_set(err, path, 0, 0, "", "无法写入文件: %s", strerror(errno));
        return -1;
    }
    if (len && fwrite(data, 1, len, fp) != len) {
        fclose(fp);
        zerr_set(err, path, 0, 0, "", "写入不完整");
        return -1;
    }
    fclose(fp);
    return 0;
}

int z_append_line(const char *path, const char *line)
{
    char dir[1024];
    FILE *fp;
    if (!path) return -1;
    z_strlcpy(dir, path, sizeof(dir));
    z_dirname(dir);
    if (dir[0] && strcmp(dir, ".") != 0) z_mkdir_p(dir);
    fp = fopen(path, "a");
    if (!fp) return -1;
    fputs(line, fp);
    fputc('\n', fp);
    fclose(fp);
    return 0;
}

/* ================================================================ 时间 */
double z_now_seconds(void)
{
#ifdef _WIN32
    LARGE_INTEGER f, c;
    QueryPerformanceFrequency(&f);
    QueryPerformanceCounter(&c);
    return (double)c.QuadPart / (double)f.QuadPart;
#else
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return (double)ts.tv_sec + (double)ts.tv_nsec / 1e9;
#endif
}

void z_sleep_ms(int ms)
{
#ifdef _WIN32
    Sleep((DWORD)ms);
#else
    struct timespec ts;
    if (ms <= 0) return;
    ts.tv_sec = ms / 1000;
    ts.tv_nsec = (long)(ms % 1000) * 1000000L;
    nanosleep(&ts, NULL);
#endif
}

/* ================================================================ 数学 */
double z_lerp(double a, double b, double t) { return a + (b - a) * t; }

/* Live2D 官方动作淡入淡出用的缓动（CubismMath.getEasingSine）：
   0.5 − 0.5·cos(πt)。和 smoothstep 形状很像（最大只差 0.01），
   但这是官方写死的那条曲线，动作权重一律用它，别再混用两种口径。 */
double z_ease_sine(double t)
{
    if (t <= 0.0) return 0.0;
    if (t >= 1.0) return 1.0;
    return 0.5 - 0.5 * cos(t * 3.14159265358979323846);
}

double z_smoothstep(double t)
{
    t = ZC_CLAMP(t, 0.0, 1.0);
    return t * t * (3.0 - 2.0 * t);
}

zease z_ease_from_name(const char *name)
{
    if (!name) return ZEASE_LINEAR;
    if (z_streq(name, "in")) return ZEASE_IN;
    if (z_streq(name, "out")) return ZEASE_OUT;
    if (z_streq(name, "in_out")) return ZEASE_IN_OUT;
    if (z_streq(name, "out_back")) return ZEASE_OUT_BACK;
    if (z_streq(name, "out_elastic")) return ZEASE_OUT_ELASTIC;
    if (z_streq(name, "out_bounce")) return ZEASE_OUT_BOUNCE;
    return ZEASE_LINEAR;
}

double z_ease_apply(zease e, double t)
{
    t = ZC_CLAMP(t, 0.0, 1.0);
    switch (e) {
        case ZEASE_IN:      return t * t;
        case ZEASE_OUT:     return 1.0 - (1.0 - t) * (1.0 - t);
        case ZEASE_IN_OUT:  return z_smoothstep(t);
        case ZEASE_OUT_BACK: {
            const double c1 = 1.70158, c3 = c1 + 1.0;
            double u = t - 1.0;
            return 1.0 + c3 * u * u * u + c1 * u * u;
        }
        case ZEASE_OUT_ELASTIC: {
            const double c4 = (2.0 * 3.14159265358979323846) / 3.0;
            if (t <= 0.0) return 0.0;
            if (t >= 1.0) return 1.0;
            return pow(2.0, -10.0 * t) * sin((t * 10.0 - 0.75) * c4) + 1.0;
        }
        case ZEASE_OUT_BOUNCE: {
            const double n1 = 7.5625, d1 = 2.75;
            if (t < 1.0 / d1) return n1 * t * t;
            if (t < 2.0 / d1) { t -= 1.5 / d1; return n1 * t * t + 0.75; }
            if (t < 2.5 / d1) { t -= 2.25 / d1; return n1 * t * t + 0.9375; }
            t -= 2.625 / d1;
            return n1 * t * t + 0.984375;
        }
        default: return t;
    }
}

/* ============================================================ 随机数 */
void zrand_seed(zrand *r, uint64_t seed)
{
    if (!r) return;
    r->s = seed ? seed : 0x9E3779B97F4A7C15ull;
}

uint32_t zrand_u32(zrand *r)
{
    uint64_t x;
    if (!r || r->s == 0) return 0;
    x = r->s;
    x ^= x << 13; x ^= x >> 7; x ^= x << 17;
    r->s = x;
    return (uint32_t)(x >> 32);
}

double zrand_unit(zrand *r) { return (double)zrand_u32(r) / 4294967296.0; }
double zrand_range(zrand *r, double a, double b) { return a + (b - a) * zrand_unit(r); }

double zrand_expo(zrand *r, double mean)
{
    double u = zrand_unit(r);
    if (u < 1e-12) u = 1e-12;
    return -mean * log(u);
}

/* ============================================================ 并行助手 */
#if defined(_WIN32)
#  define ZC_THREADS 1
#  include <windows.h>
#  include <process.h>
#elif defined(__unix__) || defined(__APPLE__)
#  define ZC_THREADS 1
#  include <pthread.h>
#  include <unistd.h>
#else
#  define ZC_THREADS 0
#endif

#define ZC_MAX_WORKERS 16

int z_hw_threads(void)
{
    static int cached = 0;
    if (cached > 0) return cached;
#if ZC_THREADS
#  ifdef _WIN32
    { SYSTEM_INFO si; GetSystemInfo(&si); cached = (int)si.dwNumberOfProcessors; }
#  else
    { long sc = sysconf(_SC_NPROCESSORS_ONLN); cached = (sc > 0) ? (int)sc : 1; }
#  endif
#else
    cached = 1;
#endif
    if (cached < 1) cached = 1;
    return cached;
}

typedef struct {
    void (*fn)(void *, int);
    void *ctx;
    int   idx;
} zc_job;

#if ZC_THREADS
#  ifdef _WIN32
static unsigned __stdcall zc_worker(void *p) { zc_job *j = (zc_job *)p; j->fn(j->ctx, j->idx); return 0; }
#  else
static void *zc_worker(void *p) { zc_job *j = (zc_job *)p; j->fn(j->ctx, j->idx); return NULL; }
#  endif
#endif

void z_parallel_for(int n, void (*fn)(void *ctx, int idx), void *ctx)
{
    int i;
    if (!fn || n <= 0) return;
    if (n > ZC_MAX_WORKERS) n = ZC_MAX_WORKERS;
    if (n == 1) { fn(ctx, 0); return; }
#if ZC_THREADS
    {
        zc_job jobs[ZC_MAX_WORKERS];
#  ifdef _WIN32
        HANDLE th[ZC_MAX_WORKERS];
        for (i = 0; i < n; ++i) { jobs[i].fn = fn; jobs[i].ctx = ctx; jobs[i].idx = i; }
        for (i = 1; i < n; ++i)
            th[i] = (HANDLE)_beginthreadex(NULL, 0, zc_worker, &jobs[i], 0, NULL);
        fn(ctx, 0);                       /* 主线程也干一份 */
        for (i = 1; i < n; ++i)
            if (th[i]) { WaitForSingleObject(th[i], INFINITE); CloseHandle(th[i]); }
#  else
        pthread_t th[ZC_MAX_WORKERS];
        int ok[ZC_MAX_WORKERS];
        for (i = 0; i < n; ++i) { jobs[i].fn = fn; jobs[i].ctx = ctx; jobs[i].idx = i; }
        for (i = 1; i < n; ++i)
            ok[i] = (pthread_create(&th[i], NULL, zc_worker, &jobs[i]) == 0);
        fn(ctx, 0);                       /* 主线程也干一份 */
        for (i = 1; i < n; ++i) if (ok[i]) pthread_join(th[i], NULL);
#  endif
    }
#else
    for (i = 0; i < n; ++i) fn(ctx, i);
#endif
}
