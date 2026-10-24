/* 尾巴「摆动词汇表」的确定性探针 —— 不经过渲染器、不依赖墙钟。
 *
 * 量两张表：
 *   表一 mood_swing（T45.2f）—— 情绪 → 慢摆的 [频率倍率, 幅度倍率]
 *   表二 tail_flick（T45.2g）—— 情绪 → 自发抽动的 [间隔, 幅度, 时长]
 * 外加一项结构检查：
 *   行波延迟（bind.lag）—— 尾巴梢是不是真的比尾巴根慢半拍
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
 * 算峰峰值和过零频率。跑一次几秒钟，结果可复现。
 *
 * 教训 167 的延伸：读数自相矛盾时，别去调采样参数，去换测量通道。
 *
 * ★ 两张表必须**分开**量。抽动是叠加在慢摆之上的非周期脉冲，混在一起的话
 *   峰峰值里分不清哪份是慢摆、哪份是抽动。所以：
 *     慢摆  = zrig_tail_flick_enable(r, 0) 之后的轨迹
 *     抽动  = （开抽动的轨迹）−（关抽动的轨迹），逐点相减
 *   引擎是确定性的（抽动有自己的固定种子随机流），两条轨迹可以直接相减。
 *
 * 编译：
 *   gcc -O2 -std=c11 -D_POSIX_C_SOURCE=200809L -Isrc/core \
 *       -o /tmp/probe_swing tools/probe_swing.c  src/core/ 下所有 .c  -lm -lpthread
 */
#include <math.h>
#include <stdio.h>
#include <string.h>

#include "zrig.h"

#define SECS 60.0
#define HZ   120.0
#define N    7200            /* = SECS * HZ，要当数组长度用所以写成字面量 */
#define WARM 720             /* 预热 6 秒：等 pose 淡入和物理稳态建立 */

static const char *MOODS[] = {
    "neutral", "angry", "think", "sleepy", "happy",
    "cute", "affection", "smile", "surprise", "sad", "shy",
};
#define NMOOD 11

static const char *RIG = "characters/xiaoxun/forms/teen/rig.json";
static const char *BASE = "characters/xiaoxun/forms/teen";
static const char *PART = "acc_tail_cat_relaxed";
static const char *DFM = "tail_relaxed_s";

static double buf_off[N], buf_on[N], buf_tip[N];

/* 跑一遍 60 秒，把尾巴根的 rot_deg 填进 out[]，尾巴梢的形变填进 tip[]（可为 NULL）。 */
static int run(const char *mood, int flick, double *out, double *tip)
{
    int i;
    zrig *r = zrig_load(RIG, BASE, NULL);
    if (!r) { fprintf(stderr, "[probe] rig 读不进来：%s\n", RIG); return -1; }
    zrig_pose_apply_mood(r, mood);
    zrig_apply_mood_params(r, mood);
    zrig_apply_mood_swing(r, mood);      /* 第四张情绪表 */
    zrig_apply_mood_flick(r, mood);      /* 第五张情绪表 */
    zrig_tail_flick_enable(r, flick);
    /* 摆动是 idle 动作里的一条通道 —— 不把动作点起来，参数恒为 0。
       第一版探针就栽在这：读出来全是 0.0000，差点当成"mood_swing 没生效"。 */
    zrig_action_request(r, "idle", "probe", 1);
    for (i = 0; i < WARM; i++) zrig_tick(r, (double)i / HZ);
    for (i = 0; i < N; i++) {
        zrig_tick(r, WARM / HZ + (double)i / HZ);
        /* ★ 读的是**部件的 rot_deg 通道**，不是参数本身。
           zrig_param_get 只给参数"自己的值"（头文件写明了），
           动作通道推出来的那一份它看不见 —— 第二版探针又读出全 0。 */
        out[i] = zrig_part_channel(r, PART, "rot_deg");
        if (tip) tip[i] = zrig_deform_amount(r, DFM);
    }
    zrig_free(r);
    return 0;
}

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

/* 数抽动：|幅度| 连续超过阈值算一段，返回**事件数**，并给出峰值的最小/最大/均值。
   阈值取 0.15°—— 比数值噪声大两个数量级，比最弱的那一档（sleepy 0.25×1.0×
   3.2 ≈ 0.8°）小得多。
   ★ MERGE 这一步不是装饰：一次抽动的波形是 exp(−4.2u)·sin(1.6πu)，它**自己**
     会过一次零再回摆，所以 |d| 在一次抽动里会冒出两段。第一版计数器照段数报，
     angry 数出 68 次（期望 32）、happy 24 次（期望 12）—— 整整两倍；
     而 think / sleepy / sad 又是对的，因为它们幅度小，回摆那一下（约为峰值
     的 4.4%）压根没过阈值。**又是一次"一半对一半错"。**
     所以间隔短于 MERGE 的两段按同一次抽动合并。 */
#define MERGE 0.35
static int count_flicks(const double *d, int n, double *pmin, double *pmax,
                        double *pmean, double *gap_mean)
{
    const double TH = 0.15;
    int i, ev = 0, in = 0, last_end = -1, merging = 0;
    double cur = 0.0, sum = 0.0, gsum = 0.0;
    int ng = 0;
    *pmin = 1e9; *pmax = 0.0;
    for (i = 0; i <= n; i++) {
        double a = (i < n) ? fabs(d[i]) : 0.0;
        if (i < n && a > TH) {
            if (!in) {
                /* 刚结束的那一段离现在很近 ⇒ 是同一次抽动的回摆，接着算 */
                merging = (last_end >= 0 && (i - last_end) / HZ < MERGE);
                if (!merging) {
                    cur = 0.0;
                    if (last_end >= 0) { gsum += (i - last_end) / HZ; ng++; }
                }
                in = 1;
            }
            if (a > cur) cur = a;
        } else if (in) {
            in = 0;
            last_end = i;
            /* 收尾推迟到"确认后面 MERGE 秒内没有回摆"才做 —— 用一个小前瞻 */
            {
                int j, quiet = 1;
                for (j = i; j < n && (j - i) / HZ < MERGE; j++)
                    if (fabs(d[j]) > TH) { quiet = 0; break; }
                if (quiet) {
                    ev++;
                    sum += cur;
                    if (cur < *pmin) *pmin = cur;
                    if (cur > *pmax) *pmax = cur;
                }
            }
        }
    }
    if (ev == 0) *pmin = 0.0;
    *pmean = ev ? sum / ev : 0.0;
    *gap_mean = ng ? gsum / ng : 0.0;
    return ev;
}

int main(void)
{
    int m, i;
    double base_pp = 0.0, base_hz = 0.0;

    puts("尾巴摆动探针 —— 仿真 60 秒 @120Hz，读 acc_tail_cat_relaxed 的 rot_deg（度）\n");

    /* ───────── 表一：mood_swing（慢摆）。抽动关掉，单独量。 ───────── */
    puts("【表一】mood_swing：情绪 → 慢摆的频率/幅度倍率（抽动已关闭）");
    printf("%-10s %-11s %-11s %-9s %s\n",
           "情绪", "峰峰值", "频率Hz", "amp×", "freq×");
    puts("-------------------------------------------------------------");
    for (m = 0; m < NMOOD; m++) {
        double pp, hz;
        if (run(MOODS[m], 0, buf_off, NULL) != 0) return 2;
        stats(buf_off, N, &pp, &hz);
        if (m == 0) { base_pp = pp; base_hz = hz; }
        printf("%-10s %-11.4f %-11.3f %-9.2f %.2f\n", MOODS[m], pp, hz,
               base_pp > 1e-9 ? pp / base_pp : 0.0,
               base_hz > 1e-9 ? hz / base_hz : 0.0);
    }

    /* ───────── 表二：tail_flick（自发抽动）。开减关，拿到纯抽动。 ───────── */
    puts("\n【表二】tail_flick：情绪 → 自发抽动（= 开抽动的轨迹 − 关抽动的轨迹）");
    printf("%-10s %-8s %-11s %-22s %s\n",
           "情绪", "60秒次数", "平均间隔s", "峰值度数 最小~最大", "平均峰值");
    puts("---------------------------------------------------------------------");
    for (m = 0; m < NMOOD; m++) {
        double lo, hi, mean, gap;
        int ev;
        if (run(MOODS[m], 0, buf_off, NULL) != 0) return 2;
        if (run(MOODS[m], 1, buf_on, NULL) != 0) return 2;
        for (i = 0; i < N; i++) buf_on[i] -= buf_off[i];
        ev = count_flicks(buf_on, N, &lo, &hi, &mean, &gap);
        printf("%-10s %-8d %-11.2f %8.2f ~ %-11.2f %.2f\n",
               MOODS[m], ev, gap, lo, hi, mean);
    }

    /* ───────── 结构检查：行波延迟 ───────── */
    puts("\n【结构】行波延迟（bind.lag）：尾巴梢应该比尾巴根慢半拍");
    {
        double besta = -2.0;
        int bestL = -1, L;
        if (run("neutral", 1, buf_on, buf_tip) != 0) return 2;
        for (L = 0; L < (int)(0.45 * HZ); L++) {
            /* 根在前、梢在后：相关最高的那个 L 就是实测延迟 */
            double sa = 0, sb = 0, saa = 0, sbb = 0, sab = 0, c;
            int n = N - L;
            for (i = 0; i < n; i++) {
                double a = buf_on[i], b = buf_tip[i + L];
                sa += a; sb += b; saa += a * a; sbb += b * b; sab += a * b;
            }
            c = (n * sab - sa * sb) /
                (sqrt(n * saa - sa * sa) * sqrt(n * sbb - sb * sb) + 1e-12);
            if (c > besta) { besta = c; bestL = L; }
        }
        printf("  互相关最高点在延迟 %.3f 秒处（相关系数 %.4f）\n",
               bestL / HZ, besta);
        puts("  rig 里 acc_tail_cat_relaxed 的 bind.lag = 0.17 —— 两者应当吻合；");
        puts("  量出 0.000 就说明行波没接上（根和梢同相位推 = 僵硬的钟摆）。");
    }
    return 0;
}
