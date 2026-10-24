/* probe_sync.c —— 量「几个自律振荡器是不是在同一个节拍上」（T63.2 验收探针）
 *
 * 判据出处：
 *   「動きが単調に見える場合は、呼吸、髪、目線、まばたきの周期を少しずつずらします。
 *     全部が同じ周期で動くと、機械的な印象になりやすいためです。」
 *   —— https://d-gear.biz/column/8573
 *
 * 怎么量：对每一对参数的时间序列做**零延迟相关系数**（各自去均值再归一化）。
 *   |r| → 1  两条曲线步调完全一致（同涨同落，或完全反相）= 机械感
 *   |r| → 0  互相独立 = 自然
 * 零延迟就够了：我们要抓的是"同时达到峰值"这种一眼能看出来的同步，
 * 不是任意相移下的相似性（那是另一回事，而且相移本身正是我们想要的）。
 *
 * 编译：gcc -O2 -std=c11 -Isrc/core -o build/probe_sync \
 *          tools/bench/probe_sync.c src/core/*.c -lm -lpthread -ldl
 */
#define _POSIX_C_SOURCE 200809L
#include "zrig.h"
#include "zc.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>

#define NS 1200          /* 20 秒 @60fps —— 比最慢的那条（0.085Hz ≈ 11.8s）长 */

static const char *WATCH[] = {
    "ParamBreath",
    "ParamHairSway",
    "ParamSkirtSway",
    "ParamJacketSway",
    "ParamAccTailRelaxedSwing",
    "ParamEarLAngle",
    "ParamEarRAngle",
};
#define NW ((int)(sizeof(WATCH) / sizeof(WATCH[0])))

static double corr(const double *a, const double *b, int n)
{
    double ma = 0, mb = 0, sa = 0, sb = 0, s = 0;
    int i;
    for (i = 0; i < n; ++i) { ma += a[i]; mb += b[i]; }
    ma /= n; mb /= n;
    for (i = 0; i < n; ++i) {
        double x = a[i] - ma, y = b[i] - mb;
        sa += x * x; sb += y * y; s += x * y;
    }
    if (sa < 1e-12 || sb < 1e-12) return 0.0;   /* 常量序列：无从谈同步 */
    return s / sqrt(sa * sb);
}

int main(int argc, char **argv)
{
    const char *form = argc > 1 ? argv[1] : "teen";
    zdiag d;
    zrig *r;
    char path[512], base[512];
    static double v[NW][NS];
    int idx[NW], i, k, j;
    double worst = 0.0;
    const char *wa = "", *wb = "";

    zdiag_init(&d);
    snprintf(path, sizeof(path), "characters/xiaoxun/forms/%s/rig.json", form);
    snprintf(base, sizeof(base), "characters/xiaoxun/forms/%s", form);
    r = zrig_load(path, base, &d);
    if (!r) { zdiag_print(&d, stderr); return 1; }

    for (k = 0; k < NW; ++k) {
        idx[k] = -1;
        for (j = 0; j < zrig_param_count(r); ++j) {
            const char *id = zrig_param_id(r, j);
            if (id && strcmp(id, WATCH[k]) == 0) { idx[k] = j; break; }
        }
    }

    /* 待机状态下自己跑。呼吸挂在 breath 动作上，先切过去。 */
    zrig_action_request(r, "breath", "probe", 1);
    {
        double t = 1000.0;
        for (i = 0; i < NS; ++i) {
            t += 1.0 / 60.0;
            zrig_tick(r, t);
            for (k = 0; k < NW; ++k)
                v[k][i] = (idx[k] >= 0) ? zrig_param_effective(r, WATCH[k]) : 0.0;
        }
    }

    printf("\n=== 自律振荡器同步度  xiaoxun/%s  （%d 帧 = %.0f 秒 @60fps）===\n",
           form, NS, NS / 60.0);
    printf("  |相关系数| 越接近 1 越是同一个节拍（机械感），越接近 0 越独立（自然）\n\n");
    printf("  %-26s", "");
    for (k = 0; k < NW; ++k) printf("%7.6s", WATCH[k] + 5);
    printf("\n");
    for (k = 0; k < NW; ++k) {
        printf("  %-26s", WATCH[k] + 5);
        for (j = 0; j < NW; ++j) {
            double c = (idx[k] < 0 || idx[j] < 0) ? 0.0 : fabs(corr(v[k], v[j], NS));
            printf("%7.2f", c);
            if (j > k && c > worst) { worst = c; wa = WATCH[k]; wb = WATCH[j]; }
        }
        printf("\n");
    }
    for (k = 0; k < NW; ++k)
        if (idx[k] < 0) printf("  （%s 这个 rig 里没有，按 0 计）\n", WATCH[k]);

    printf("\n  最同步的一对：%s ↔ %s  |r| = %.4f\n", wa, wb, worst);
    printf("  %s\n", worst > 0.90
           ? "★ 红：有一对几乎完全同节拍，就是官方说的『全部が同じ周期』"
           : "绿：没有哪两条锁死在一起");

    zrig_free(r);
    return 0;
}
