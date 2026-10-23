/* probe_follow.c —— 量「头转了身子跟不跟、跟多晚」和「停得干不干净」
 * （2026-10-24，T63.1 的验收探针）
 *
 * 判据来自 Live2D 官方《クオリティアップのヒント》两条：
 *   ① 顔XYZと体XYZを慣性を意識してタイミングをずらす
 *      —— 顔と体がまったく同じタイミングで動くと、やはりロボットのように見えます
 *   ② 反動、ブレーキを付ける
 *      —— 人間はピタッと瞬時に動きをとめることができません
 *
 * 所以要量两件事：
 *   · 胸的位移峰值比头的峰值**晚多少毫秒**（0 = 机器人）
 *   · 头的位移有没有**冲过稳态值**再荡回来（没冲过 = 刹得太干净）
 *
 * 编译：gcc -O2 -std=c11 -Isrc/core -o build/probe_follow \
 *          tools/bench/probe_follow.c src/core/*.c -lm -lpthread -ldl
 */
#define _POSIX_C_SOURCE 200809L
#include "zrig.h"
#include "zc.h"
#include <stdio.h>
#include <stdlib.h>
#include <math.h>

int main(int argc, char **argv)
{
    const char *form = argc > 1 ? argv[1] : "teen";
    zdiag d;
    zrig *rig;
    char path[512], base[512];
    int i;
    const int N = 90;                 /* 1.5 秒 @60fps */
    double t = 1000.0, hx[128], cx[128], lk[128];

    zdiag_init(&d);
    snprintf(path, sizeof(path), "characters/xiaoxun/forms/%s/rig.json", form);
    snprintf(base, sizeof(base), "characters/xiaoxun/forms/%s", form);
    rig = zrig_load(path, base, &d);
    if (!rig) { zdiag_print(&d, stderr); return 1; }

    /* 先让它在"看正前方"上稳住，避免初始瞬态混进来 */
    zrig_look(rig, 0.0, 0.0);
    for (i = 0; i < 120; ++i) { t += 1.0 / 60.0; zrig_tick(rig, t); }

    /* 啪地把视线甩到最右边 —— 这就是"猛地转头" */
    zrig_look(rig, 1.0, 0.0);
    for (i = 0; i < N; ++i) {
        t += 1.0 / 60.0;
        zrig_tick(rig, t);
        hx[i] = zrig_group_offset_x(rig, "head");
        cx[i] = zrig_group_offset_x(rig, "chest");
        lk[i] = zrig_look_x(rig);   /* 平滑后的跟随量本身：量"反动"要看它，不受组继承干扰 */
    }

    printf("\n=== 转头跟随探针  xiaoxun/%s  （甩到最右，采 %d 帧 @60fps）===\n", form, N);
    printf("  帧   时刻ms    头位移px    胸位移px\n");
    for (i = 0; i < N; i += 3)
        printf("  %3d  %6.1f   %9.3f   %9.3f\n", i, i * 1000.0 / 60.0, hx[i], cx[i]);

    /* 用「到达终值一半的时刻」来比先后。
       ★ 不能用峰值时刻 —— 头是胸的子组，zrig_group_offset_x("head") 里
         **含着胸那一份**（终值 5.5 = 头自己 4.0 + 继承胸 1.5），
         胸那一份是延迟的，会把头的峰值一起往后拖，两个峰于是撞在同一帧，
         看上去像"没有延迟"。第一版探针就是这么误报的。
       半高时刻只看各自曲线何时起来，不受这个耦合影响。 */
    {
        double hf = hx[N - 1], cf = cx[N - 1];
        double ht = -1, ct = -1, ovr = 0;
        for (i = 0; i < N; ++i) {
            if (ht < 0 && fabs(hx[i]) >= fabs(hf) * 0.5) ht = i * 1000.0 / 60.0;
            if (ct < 0 && fabs(cx[i]) >= fabs(cf) * 0.5) ct = i * 1000.0 / 60.0;
            if (fabs(lk[i]) > ovr) ovr = fabs(lk[i]);
        }
        printf("\n  头 到一半用了 %.1f ms（终值 %.3f px）\n", ht, hf);
        printf("  胸 到一半用了 %.1f ms（终值 %.3f px）\n", ct, cf);
        printf("\n  ① 身子比头晚 %.1f ms  %s\n", ct - ht,
               (ct - ht > 20.0) ? "← 有先后，头先转身子后到，不是机器人"
                                : "← 几乎同时：就是官方说的机器人");
        printf("  ② 跟随量冲过稳态 %.2f%%  %s\n",
               (ovr - 1.0) * 100.0,
               (ovr > 1.005) ? "← 有反动，会冲一点再荡回来"
                             : "← 没冲过：停得太干净，像机械臂");
        printf("\n  参考口径：Live2D 官方《クオリティアップのヒント》\n"
               "    「顔XYZと体XYZを慣性を意識してタイミングをずらす」\n"
               "    「反動、ブレーキを付ける —— 人間はピタッと瞬時に動きをとめることができません」\n");
    }

    zrig_free(rig);
    return 0;
}
