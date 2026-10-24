/* bench_frame.c —— 真机帧率测试（T63.5）
 *
 * 为什么要这个东西：
 *   开发沙箱只有 2 核，848×1360 一帧纯渲染 33.3ms（30fps）。按实测的并行效率
 *   1.81×/2 线程外推，4 核该到 17ms、8 核该到 10ms —— 但**那是外推，不是测量**。
 *   能不能真的跑满 60fps，只有在你自己的机器上跑一遍才知道。
 *   这个程序就是去拿那个真数字的。
 *
 * 它测三件事：
 *   A. 线程伸缩  —— 1/2/4/…/N 线程各要多少 ms。沙箱里问不出来的就是这个。
 *   B. 各缩放档  —— tick / 渲染 / PNG 编码 三段分开计时。
 *   C. 持续稳定  —— 连跑 8 秒，看抖动（p95、最慢帧）。
 *      平均 60fps 但时不时卡一下 40ms，人眼看到的是"卡"，不是"顺"。
 *
 * 跑完会在同目录写一份 `帧率报告.txt`，把那个文件发回来就行。
 *
 * 编译（本机）：
 *   gcc -O2 -std=c11 -Isrc/core -o build/bench_frame tools/bench/bench_frame.c \
 *       src/core/all-c-files -lm -lpthread -ldl
 * 编译（Windows）：make win-bench
 */
#define _POSIX_C_SOURCE 200809L
#include "zrig.h"
#include "zimg.h"
#include "zc.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <stdarg.h>

#ifdef _WIN32
#  include <windows.h>
#else
#  include <unistd.h>
#endif

/* ---- 计时与环境 ---- */

static double now_s(void)
{
#ifdef _WIN32
    static LARGE_INTEGER freq;
    LARGE_INTEGER c;
    if (!freq.QuadPart) QueryPerformanceFrequency(&freq);
    QueryPerformanceCounter(&c);
    return (double)c.QuadPart / (double)freq.QuadPart;
#else
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return (double)ts.tv_sec + (double)ts.tv_nsec * 1e-9;
#endif
}

static int cpu_cores(void)
{
#ifdef _WIN32
    SYSTEM_INFO si;
    GetSystemInfo(&si);
    return (int)si.dwNumberOfProcessors;
#else
    long n = sysconf(_SC_NPROCESSORS_ONLN);
    return n > 0 ? (int)n : 1;
#endif
}

/* 两个出口：屏幕和报告文件。测完要把文件发回来，所以每一行都得进文件。 */
static FILE *g_rep = NULL;
static void outf(const char *fmt, ...)
{
    va_list ap;
    va_start(ap, fmt);
    vprintf(fmt, ap);
    va_end(ap);
    if (g_rep) {
        va_start(ap, fmt);
        vfprintf(g_rep, fmt, ap);
        va_end(ap);
    }
}

static int cmp_d(const void *a, const void *b)
{
    double x = *(const double *)a, y = *(const double *)b;
    return x < y ? -1 : (x > y ? 1 : 0);
}

typedef struct { double avg, p50, p95, worst; } stat;

static stat stat_of(double *v, int n)
{
    stat s;
    double sum = 0;
    int i;
    qsort(v, (size_t)n, sizeof(double), cmp_d);
    for (i = 0; i < n; ++i) sum += v[i];
    s.avg = sum / n;
    s.p50 = v[n / 2];
    s.p95 = v[(int)((double)n * 0.95)];
    s.worst = v[n - 1];
    return s;
}

/* ---- 找素材：双击 exe 时工作目录可能是任何地方 ---- */

static int file_ok(const char *p)
{
    FILE *f = fopen(p, "rb");
    if (!f) return 0;
    fclose(f);
    return 1;
}

/* 从当前目录逐级往上找，再试 exe 旁边。找不到就老老实实报错，不瞎猜。 */
static int find_rig(char *rig, size_t rn, char *base, size_t bn, const char *form)
{
    static const char *pre[] = { "", "../", "../../", "../../../", "../../../../" };
    size_t i;
    for (i = 0; i < sizeof(pre) / sizeof(pre[0]); ++i) {
        char b[512], r[640];
        snprintf(b, sizeof(b), "%scharacters/xiaoxun/forms/%s", pre[i], form);
        snprintf(r, sizeof(r), "%s/rig.json", b);
        if (file_ok(r)) {
            z_strlcpy(rig, r, rn);
            z_strlcpy(base, b, bn);
            return 1;
        }
    }
    return 0;
}

/* ---- 一轮测量 ---- */

typedef struct { stat tick, rend, enc; int w, h; } runres;

static runres run_once(zrig *r, double scale, int reps, int do_png)
{
    runres out;
    double *tt = (double *)malloc(sizeof(double) * (size_t)reps);
    double *tr = (double *)malloc(sizeof(double) * (size_t)reps);
    double *te = (double *)malloc(sizeof(double) * (size_t)reps);
    double t0 = now_s();
    int i, w = 0, h = 0;

    /* 预热：首帧要分配缩放缓冲、要把贴图读进缓存，算进去会虚高 */
    for (i = 0; i < 5; ++i) { zrig_tick(r, t0 + i * 0.0167); zrig_frame(r, scale, &w, &h); }

    for (i = 0; i < reps; ++i) {
        const zimg *fr;
        double a, b, c, e;
        a = now_s();
        zrig_tick(r, t0 + 1.0 + (double)i / 60.0);
        b = now_s();
        fr = zrig_frame(r, scale, &w, &h);
        c = now_s();
        if (do_png && fr) {
            size_t n = 0;
            uint8_t *png = zimg_encode_png(fr, &n);
            free(png);
        }
        e = now_s();
        tt[i] = (b - a) * 1000.0;
        tr[i] = (c - b) * 1000.0;
        te[i] = (e - c) * 1000.0;
    }
    out.tick = stat_of(tt, reps);
    out.rend = stat_of(tr, reps);
    out.enc  = stat_of(te, reps);
    out.w = w; out.h = h;
    free(tt); free(tr); free(te);
    return out;
}

int main(int argc, char **argv)
{
    const char *form = argc > 1 ? argv[1] : "teen";
    char rig_path[640], base[512];
    zdiag d;
    zrig *r;
    int cores = cpu_cores();
    int i;
    double base1 = 0.0, best = 1e9;
    int best_t = 1;

#ifdef _WIN32
    SetConsoleOutputCP(CP_UTF8);     /* 不设这个，中文在 cmd 里是乱码 */
#endif

    g_rep = fopen("帧率报告.txt", "w");

    outf("\n");
    outf("================ 桌宠真机帧率测试 ================\n");
    outf("  目的：确认这台机器能不能让她跑满 60fps。\n");
    outf("  跑完请把同目录下的「帧率报告.txt」发回来。\n");
    outf("==================================================\n\n");
    outf("机器：CPU 逻辑核心 %d 个\n", cores);

    zdiag_init(&d);
    if (!find_rig(rig_path, sizeof(rig_path), base, sizeof(base), form)) {
        outf("\n找不到角色素材。\n");
        outf("请把这个程序放在 zhuochong 目录里（和 characters 文件夹并列）再跑。\n");
        outf("现在找的是：characters/xiaoxun/forms/%s/rig.json\n", form);
        if (g_rep) fclose(g_rep);
#ifdef _WIN32
        printf("\n按回车键关闭…"); getchar();
#endif
        return 1;
    }
    outf("素材：%s\n", rig_path);

    r = zrig_load(rig_path, base, &d);
    if (!r) {
        outf("\n素材读不起来：\n");
        zdiag_print(&d, stderr);
        if (g_rep) fclose(g_rep);
#ifdef _WIN32
        printf("\n按回车键关闭…"); getchar();
#endif
        return 1;
    }
    zrig_blink_set_enabled(r, 0);     /* 眨眼是随机的，会给逐帧耗时加噪声 */

    /* ---------- A. 线程伸缩 ---------- */
    outf("\n");
    outf("── A. 线程伸缩（画面 848x1360，只算渲染，不算 PNG）──\n");
    outf("   沙箱只有 2 核，这一段是**只有真机能回答**的问题。\n\n");
    outf("   线程   中位耗时     折合帧率    相对单线程\n");
    for (i = 1; i <= cores * 2 && i <= 16; i *= 2) {
        runres rr;
        zrig_set_render_threads(i);
        rr = run_once(r, 1.0, 40, 0);
        if (i == 1) base1 = rr.rend.p50;
        if (rr.rend.p50 < best) { best = rr.rend.p50; best_t = i; }
        outf("   %4d   %7.2f ms   %6.1f fps      %5.2fx\n",
             i, rr.rend.p50, 1000.0 / rr.rend.p50,
             base1 > 0 ? base1 / rr.rend.p50 : 1.0);
    }
    outf("\n   最快是 %d 线程：%.2f ms（%.1f fps）\n", best_t, best, 1000.0 / best);

    /* 后面都用最快的那档 */
    zrig_set_render_threads(best_t);

    /* ---------- B. 各缩放档 ---------- */
    outf("\n");
    outf("── B. 各尺寸档（%d 线程）──\n", best_t);
    outf("   PNG 编码那一列**只有网页预览需要**；桌面版直接把像素贴到窗口，没有这一步。\n\n");
    outf("   画面尺寸        状态机    渲染      PNG编码    渲染帧率   含编码帧率\n");
    {
        static const double sc[] = { 0.55, 1.0, 1.2 };
        size_t k;
        for (k = 0; k < sizeof(sc) / sizeof(sc[0]); ++k) {
            runres rr = run_once(r, sc[k], 40, 1);
            double only = rr.tick.p50 + rr.rend.p50;
            double all  = only + rr.enc.p50;
            outf("   %4dx%-9d %6.2f  %7.2f ms  %7.2f ms  %6.1f fps  %6.1f fps\n",
                 rr.w, rr.h, rr.tick.p50, rr.rend.p50, rr.enc.p50,
                 1000.0 / only, 1000.0 / all);
        }
    }

    /* ---------- C. 持续稳定性 ---------- */
    outf("\n");
    outf("── C. 持续 8 秒（848x1360，%d 线程，只算渲染）──\n", best_t);
    outf("   平均快不代表看着顺：偶尔卡一下，眼睛立刻就能看出来。\n\n");
    {
        int reps = 480;
        runres rr = run_once(r, 1.0, reps, 0);
        outf("   平均 %.2f ms   中位 %.2f   p95 %.2f   最慢 %.2f\n",
             rr.rend.avg, rr.rend.p50, rr.rend.p95, rr.rend.worst);
        outf("   抖动（p95 ÷ 中位）= %.2fx  %s\n",
             rr.rend.p50 > 0 ? rr.rend.p95 / rr.rend.p50 : 0.0,
             (rr.rend.p50 > 0 && rr.rend.p95 / rr.rend.p50 < 1.35)
                 ? "稳" : "← 有明显卡顿，需要查后台占用");

        /* ---------- 判定 ---------- */
        outf("\n");
        outf("================ 判定 ================\n");
        outf("  目标：848x1360 一帧 ≤ 16.67ms = 60fps\n");
        outf("        （标准出处：VTube Studio 官方 wiki 建议常驻 60fps；\n");
        outf("          Live2D Cubism 自 5.0 起物理默认帧率也从 30 改成了 60）\n\n");
        if (rr.rend.p95 <= 16.67) {
            outf("  ✅ 达标。p95 %.2f ms，满帧 60fps 跑得动，还有余量。\n", rr.rend.p95);
        } else if (rr.rend.p95 <= 33.3) {
            outf("  ⚠ 60fps 差一点（p95 %.2f ms），30fps 稳稳的。\n", rr.rend.p95);
            outf("     够用，但要 60 的话得做 T63.6（脏矩形 / 按窗口尺寸渲染）。\n");
        } else {
            outf("  ❌ 不达标（p95 %.2f ms，%.1f fps）。\n",
                 rr.rend.p95, 1000.0 / rr.rend.p95);
            outf("     T63.6 变成必做项，而且可能得上 GPU。\n");
        }
        outf("\n  注意：上面这个判定看的是**渲染**，不含 PNG 编码。\n");
        outf("        桌面版不走 PNG，所以这才是桌宠真实的上限。\n");
        outf("======================================\n");
    }

    zrig_free(r);
    outf("\n报告已写到同目录的「帧率报告.txt」，把它发回来就行。\n");
    if (g_rep) fclose(g_rep);
#ifdef _WIN32
    printf("\n按回车键关闭…");
    getchar();
#endif
    return 0;
}
