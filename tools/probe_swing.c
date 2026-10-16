/* 摆动词汇表的确定性探针 —— 不经过渲染器、不依赖墙钟。
 *
 * 为什么要有它
 * ------------
 * 验「情绪 → 尾巴摆得多快多大」时，我先用 HTTP 连拍 + 质心位移去量，
 * 同一组配置两次跑出来是 neutral 63px / angry 2px 和 neutral 5px / angry 49px，
 * 完全互相矛盾。原因：每次 /api/frame.png 的耗时不定（100~300ms），
 * 等于**按随机相位采样一条正弦**，窗口又只有几个周期，采到的极值纯看运气。
 *
 * 摆动是引擎内部一条参数随时间变化的确定性函数，根本不需要经过渲染和网络。
 * 这个探针直接 zrig_tick(r, t) 按**精确仿真时刻**推进，读参数值，
 * 算峰峰值和过零频率。跑一次 0.2 秒，结果可复现。
 *
 * 教训 167 的延伸：读数自相矛盾时，别去调采样参数，去换测量通道。
 *
 * 编译：
 *   gcc -O2 -std=c11 -D_POSIX_C_SOURCE=200809L -Isrc/core \
 *       -o /tmp/probe_swing tools/probe_swing.c src/core/*.c -lm -lpthread
 */
#include <math.h>
#include <stdio.h>
#include <string.h>

#include "zrig.h"

#define SECS 24.0
#define HZ   120.0
#define N    2880            /* = SECS * HZ，要当数组长度用所以写成字面量 */

static const char *MOODS[] = {
    "neutral", "angry", "think", "sleepy", "happy",
    "cute", "affection", "smile", "surprise", "sad", "shy",
};

/* 峰峰值 + 过均值次数换算频率 */
static void stats(const double *v, int n, double *pp, double *hz)
{
    double lo = v[0], hi = v[0], mean = 0.0;
    int i, z = 0;
    for (i = 0; i < n; i++) {
        if (v[i] < lo) lo = v[i];
        if (v[i] > hi) hi = v[i];
        mean += v[i];
    }
    mean /= (double)n;
    for (i = 1; i < n; i++)
        if ((v[i] - mean) * (v[i - 1] - mean) < 0.0) z++;
    *pp = hi - lo;
    *hz = (double)z / 2.0 / SECS;
}

int main(int argc, char **argv)
{
    const char *rig_path = (argc > 1) ? argv[1]
        : "characters/xiaoxun/forms/teen/rig.json";
    const char *base = (argc > 2) ? argv[2]
        : "characters/xiaoxun/forms/teen";
    /* ★ 读的是**部件的 rot_deg 通道**，不是参数本身。
       zrig_param_get 只给参数"自己的值"（头文件 :169 写明了），
       动作通道推出来的那一份它看不见 —— 第二版探针又读出全 0，
       以为 mood_swing 没生效。摆动最终落在部件的 rot_deg 上，读这个才作数。 */
    const char *part = (argc > 3) ? argv[3] : "acc_tail_cat_relaxed";
    const char *pid = part;

    zrig *r = zrig_load(rig_path, base, NULL);
    if (!r) { fprintf(stderr, "[probe] rig 读不进来：%s\n", rig_path); return 2; }

    printf("探针：%s   仿真 %.0f 秒 @ %.0fHz（%d 步）\n", pid, SECS, HZ, N);
    printf("%-10s %-14s %-14s %s\n", "情绪", "峰峰值", "频率Hz", "相对 neutral");
    puts("-------------------------------------------------------------");

    double base_pp = 0.0, base_hz = 0.0;
    size_t m;
    static double buf[N];
    for (m = 0; m < sizeof(MOODS) / sizeof(MOODS[0]); m++) {
        int i;
        double pp, hz;
        zrig_pose_apply_mood(r, MOODS[m]);
        zrig_apply_mood_params(r, MOODS[m]);
        zrig_apply_mood_swing(r, MOODS[m]);   /* 第四张情绪表 */
        /* 摆动是 idle 动作里的一条通道 —— 不把动作点起来，参数恒为 0。
           第一版探针就栽在这：读出来全是 0.0000，差点当成"mood_swing 没生效"。 */
        zrig_action_request(r, "idle", "probe", 1);
        /* 先空转 4 秒让 pose 淡入和物理稳态建立，再开始采 */
        for (i = 0; i < (int)(4.0 * HZ); i++)
            zrig_tick(r, (double)i / HZ);
        for (i = 0; i < N; i++) {
            zrig_tick(r, 4.0 + (double)i / HZ);
            buf[i] = zrig_part_channel(r, part, "rot_deg");
        }
        stats(buf, N, &pp, &hz);
        if (m == 0) { base_pp = pp; base_hz = hz; }
        printf("%-10s %-14.4f %-14.3f amp×%.2f freq×%.2f\n",
               MOODS[m], pp, hz,
               base_pp > 1e-9 ? pp / base_pp : 0.0,
               base_hz > 1e-9 ? hz / base_hz : 0.0);
    }
    zrig_free(r);
    return 0;
}
