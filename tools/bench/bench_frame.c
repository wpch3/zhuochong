/* bench_frame.c —— 2D 出帧全链路基准（2026-10-24，支撑 T30.3 帧率计划）
 *
 * 为什么要它：谈"达到 Neuro-sama / VTube Studio 那种流畅度"之前，
 * 得先知道我们现在每一帧到底花在哪。没有分项数字，优化就是瞎猜。
 *
 * 量三段，分开计时：
 *   ① tick   ：状态机 + 参数驱动 + 物理摆（zpet_tick）
 *   ② render ：合成一帧像素（zrig_frame，分块多线程）
 *   ③ encode ：PNG 编码（只有网页预览需要；原生窗口不需要这一段）
 *
 * 编译：
 *   gcc -O2 -std=c11 -Isrc/core -o build/bench_frame tools/bench/bench_frame.c \
 *       src/core/*.c -lm -lpthread -ldl
 * 跑：
 *   build/bench_frame <角色> <形态> <缩放> <遍数>
 *   build/bench_frame xiaoxun teen 0.55 60
 */
#define _POSIX_C_SOURCE 200809L
#include "zpet.h"
#include "zrig.h"
#include "zimg.h"
#include "zconfig.h"
#include "zc.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

static double now_s(void)
{
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return (double)ts.tv_sec + (double)ts.tv_nsec * 1e-9;
}

static int cmp_d(const void *a, const void *b)
{
    double x = *(const double *)a, y = *(const double *)b;
    return x < y ? -1 : (x > y ? 1 : 0);
}

/* 中位数比平均值诚实：偶尔一帧特别慢（缺页、调度）会把平均值拖花，
   但用户感觉到的是"大多数帧有多快"和"最慢的那几帧有多慢"。 */
static void stat_line(const char *name, double *v, int n, double total_budget_ms)
{
    double sum = 0, p50, p95, mx;
    int i;
    qsort(v, (size_t)n, sizeof(double), cmp_d);
    for (i = 0; i < n; ++i) sum += v[i];
    p50 = v[n / 2];
    p95 = v[(int)((double)n * 0.95)];
    mx  = v[n - 1];
    printf("  %-8s  平均 %6.2f ms   中位 %6.2f   p95 %6.2f   最慢 %6.2f",
           name, sum / n, p50, p95, mx);
    if (total_budget_ms > 0)
        printf("   占 60fps 预算 %5.1f%%", p50 / total_budget_ms * 100.0);
    printf("\n");
}

int main(int argc, char **argv)
{
    const char *character = argc > 1 ? argv[1] : "xiaoxun";
    const char *form      = argc > 2 ? argv[2] : "teen";
    double scale          = argc > 3 ? atof(argv[3]) : 0.55;
    int    reps           = argc > 4 ? atoi(argv[4]) : 60;

    zconfig cfg;
    zdiag d;
    zpet *pet;
    double *t_tick, *t_rend, *t_enc;
    int i, w = 0, h = 0;
    double t0, t_start;

    zdiag_init(&d);
    if (zconfig_load(&cfg, "config", &d) != 0) { zdiag_print(&d, stderr); return 1; }
    z_strlcpy(cfg.pet.character, character, sizeof(cfg.pet.character));
    z_strlcpy(cfg.pet.form, form, sizeof(cfg.pet.form));
    cfg.pet.scale = scale;
    pet = zpet_create(&cfg, &d);
    if (!pet) { printf("pet 建不起来\n"); return 1; }

    t_tick = (double *)malloc(sizeof(double) * (size_t)reps);
    t_rend = (double *)malloc(sizeof(double) * (size_t)reps);
    t_enc  = (double *)malloc(sizeof(double) * (size_t)reps);

    /* 先空跑几帧，让缓存和首帧分配不要污染数据 */
    for (i = 0; i < 5; ++i) {
        zpet_tick(pet, now_s());
        zpet_frame(pet, &w, &h);
    }

    t_start = now_s();
    for (i = 0; i < reps; ++i) {
        const zimg *fr;
        double a, b, c, e;

        a = now_s();
        zpet_tick(pet, t_start + (double)i / 60.0);   /* 按 60fps 的时间轴推进 */
        b = now_s();
        fr = zpet_frame(pet, &w, &h);
        c = now_s();
        if (fr) {
            size_t n = 0;
            unsigned char *png = zimg_encode_png(fr, &n);
            free(png);
        }
        e = now_s();

        t_tick[i] = (b - a) * 1000.0;
        t_rend[i] = (c - b) * 1000.0;
        t_enc[i]  = (e - c) * 1000.0;
    }
    t0 = now_s() - t_start;

    printf("\n=== 出帧基准  %s/%s  缩放 %.2f  画面 %dx%d  %d 帧  线程 %d ===\n",
           character, form, scale, w, h, reps, zrig_render_threads());
    stat_line("tick",   t_tick, reps, 16.67);
    stat_line("render", t_rend, reps, 16.67);
    stat_line("encode", t_enc,  reps, 16.67);
    {
        double per = t0 / reps * 1000.0;
        printf("  ---------\n");
        printf("  整帧      %6.2f ms  ⇒  %5.1f fps（含 PNG 编码，网页预览走这条）\n",
               per, 1000.0 / per);
        /* 原生窗口不需要 PNG：直接把像素贴到窗口表面。
           把这一段单独报出来，是因为它决定了"桌面版能有多快"。 */
        {
            double s1 = 0, s2 = 0;
            int k;
            for (k = 0; k < reps; ++k) { s1 += t_tick[k]; s2 += t_rend[k]; }
            per = (s1 + s2) / reps;
            printf("  不含编码  %6.2f ms  ⇒  %5.1f fps（原生窗口走这条）\n",
                   per, 1000.0 / per);
        }
        printf("  60fps 的预算是每帧 16.67ms；30fps 是 33.3ms。\n");
    }

    free(t_tick); free(t_rend); free(t_enc);
    zpet_destroy(pet);
    return 0;
}
