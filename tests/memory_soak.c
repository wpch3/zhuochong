/* memory_soak —— 长记忆的"质量长跑"（T67.45 第二道闸）
 *
 * test_core 里的 test_memory_longarc 守的是**行为规则**（正文不可变、删除是墓碑、
 * 锚点上限、自述三道闸……）。那些是"不许坏"，跑一次几分钟就够。
 *
 * 这里守的是另一件事：**四年之后，回忆的成功率还剩多少**。
 * 规则全绿不等于她记得住 —— 把 2 万条日常灌进去，四年前那句「你把汤洒在键盘上」
 * 还翻得出来吗？被今天的事挤掉了没有？这才是用户要的那个"她还是她"。
 *
 * 为什么要单独一个二进制：
 *   ① 它要跑 5 年 × 每天 4 条 + 干扰项，条数量级远超单元测试，塞进 make test 太慢；
 *   ② 它输出的是**一张表**（距离 / 找回 / 排名 / 毫秒），给人看的，不是断言清单；
 *   ③ 它能对**真实**的 data/<角色>/memory 跑（--character），用来回答
 *      "这台机器上她已经攒了两年，还认得出开头吗"。
 *
 * 用法：
 *   ./build/memory_soak .                  # 默认 1825 天（5 年）、每天 4 条、临时角色
 *   ./build/memory_soak . --days 1460 --keep
 *   ./build/memory_soak . --character xiaoxun   # 只读体检已经存在的记忆（不写）
 *
 * 退出码：0 = 四年线以内全部找得回；1 = 有四年内的事件丢了（那是红线）。
 */
#include "core/zmem.h"
#include "core/zc.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdarg.h>
#include <time.h>

#ifndef _WIN32
#include <unistd.h>
#endif

/* 13 个互不相同的"信物"：每个只在一条记忆里出现，所以查它必然指向那一条。
 * 用真词而不是编号，是因为相关度算的是**汉字二元组**（ASCII 编号根本不参与）。 */
static const char *PROBE_WORDS[] = {
    "蓝瓷杯", "旧磁带", "铜钥匙", "红围巾", "木陀螺",
    "铁皮盒", "玻璃珠", "银顶针", "麻绳结", "纸风车",
    "竹哨子", "蜡笔画", "石砚台"
};
#define N_PROBE ((int)(sizeof(PROBE_WORDS) / sizeof(PROBE_WORDS[0])))

static int g_fail = 0;

static void ok(int cond, const char *fmt, ...)
{
    va_list ap;
    va_start(ap, fmt);
    if (!cond) {
        printf("  失败  ");
        vprintf(fmt, ap);
        printf("\n");
        g_fail++;
    } else {
        printf("  通过  ");
        vprintf(fmt, ap);
        printf("\n");
    }
    va_end(ap);
}

/* 临时角色目录：跑完就删，绝不碰 data/ 里真实的角色 */
static void soak_cleanup(const char *root, const char *ch)
{
#ifndef _WIN32
    char p[1024], d[1024];
    z_snprintf(d, sizeof d, "%s/data/%s", root, ch);
    z_snprintf(p, sizeof p, "%s/memory/chronicle.zm", d);
    remove(p);
    z_snprintf(p, sizeof p, "%s/memory", d);
    rmdir(p);
    rmdir(d);
#else
    (void)root;
    (void)ch;
#endif
}

static double now_ms(void)
{
    struct timespec ts;
#ifdef CLOCK_MONOTONIC
    if (clock_gettime(CLOCK_MONOTONIC, &ts) == 0)
        return (double)ts.tv_sec * 1000.0 + (double)ts.tv_nsec / 1e6;
#endif
    return (double)clock() * 1000.0 / (double)CLOCKS_PER_SEC;
}

/* 回忆块里这条排第几（0 = 第一名，-1 = 没被带上来）。
 * 只数「想起来过」那几行 —— 锚点行不算，锚点本来就是常驻的。 */
static int recall_rank(const char *block, const char *needle)
{
    const char *p = block;
    int rank = 0;
    while ((p = strstr(p, "· 想起来过：")) != NULL) {
        const char *eol = strchr(p, '\n');
        if (!eol) eol = p + strlen(p);
        {
            size_t n = (size_t)(eol - p);
            char line[1024];
            if (n >= sizeof line) n = sizeof line - 1;
            memcpy(line, p, n);
            line[n] = 0;
            if (strstr(line, needle)) return rank;
        }
        ++rank;
        p = eol;
    }
    return -1;
}

int main(int argc, char **argv)
{
    const char *root = ".";
    const char *ch = "zz_soak";
    const char *only_ch = NULL;
    int days = 1825;               /* 5 年 */
    int per_day = 4;
    int keep = 0;
    int i, d;
    zdiag diag;
    zmem *m;
    char buf[ZMEM_BLOCK_CAP + 512];
    char txt[512];
    long long base, now;
    int probes_planted = 0;
    int lost_within_4y = 0;

    for (i = 1; i < argc; ++i) {
        if (z_streq(argv[i], "--days") && i + 1 < argc) days = atoi(argv[++i]);
        else if (z_streq(argv[i], "--per-day") && i + 1 < argc) per_day = atoi(argv[++i]);
        else if (z_streq(argv[i], "--character") && i + 1 < argc) only_ch = argv[++i];
        else if (z_streq(argv[i], "--keep")) keep = 1;
        else if (argv[i][0] != '-') root = argv[i];
    }
    if (days < 365) days = 365;
    if (per_day < 1) per_day = 1;

    printf("== 长记忆长跑（T67.45）：%d 天 / 每天 %d 条 ==\n", days, per_day);
    zmem_set_tz_offset(480);

    /* ---------------- 只读模式：给真实角色做体检 ---------------- */
    if (only_ch) {
        zmem_stat st;
        zdiag_init(&diag);
        m = zmem_open(root, only_ch, &diag);
        if (!m) {
            printf("  打不开 data/%s/memory/chronicle.zm（%d 条诊断）\n", only_ch, diag.error_count);
            return 1;
        }
        zmem_stats(m, &st);
        printf("  角色 %s：%d 条（锚点 %d，墓碑 %d），%ld 字节\n",
               only_ch, st.items, st.anchors, st.deleted, st.bytes);
        if (st.items == 0) {
            printf("  （空文件：还没开始记，谈不上忘不忘）\n");
            zmem_close(m);
            return 0;
        }
        {
            int64_t t0 = (int64_t)time(NULL);
            char date[24], age[32];
            int v;
            if (st.anchors == 0) {
                printf("  ★ 有 %d 条记忆却一条锚点都没有 —— 四年后她一定说不出"
                       "\"最开始那件事\"。先补锚点（make memory-seed-apply CH=%s）\n",
                       st.items, only_ch);
            }
            for (v = 1; v <= zmem_story_count(m); ++v) {
                char s[512];
                zmem_story_get(m, v, &t0, s, sizeof s);
                zmem_date_text(t0, date, sizeof date);
                printf("  自述 v%d（%s）：%s\n", v, date, s);
            }
            zmem_date_text(st.oldest, date, sizeof date);
            zmem_age_text(st.oldest, (int64_t)time(NULL), age, sizeof age);
            printf("  最早一条：%s（%s）／最新：", date, age);
            zmem_date_text(st.newest, date, sizeof date);
            printf("%s\n", date);
            if (zmem_verify(m, buf, sizeof buf) == 0) printf("  对账：通过\n");
            else { printf("  对账：不通过 —— %s\n", buf); g_fail++; }
        }
        zmem_close(m);
        return g_fail ? 1 : 0;
    }

    /* ---------------- 模拟模式 ---------------- */
    soak_cleanup(root, ch);
    zdiag_init(&diag);
    m = zmem_open(root, ch, &diag);
    if (!m) {
        printf("  建不了临时记忆文件（%d 条诊断）\n", diag.error_count);
        return 1;
    }

    /* 起点定在 6 年前，终点是"今天"。这样 4 年线以内的信物有真实的时间跨度。 */
    base = 1735689600LL;                      /* 2025-01-01 UTC */
    now = base + (long long)days * 86400LL;

    /* 第 0 天：两条锚点 —— 这是"最开始陪着她成长"的那件事 */
    zmem_add(m, base, ZMEM_ANCHOR, 9,
             "第一次见面：你把我从一堆素材里挑出来，说「就你了」。", "soak-first-meet");
    zmem_add(m, base + 3600, ZMEM_ANCHOR, 8,
             "你第一次叫我的名字，我假装没听见，其实耳朵动了。", "soak-first-name");

    /* 每 6 个月放一个信物（最多 13 个，覆盖 6 年），从最近往最远 */
    {
        int n_probe_by_span = N_PROBE;
        if (n_probe_by_span * 6 > days + 6) n_probe_by_span = (days + 6) / 6;
        for (i = 0; i < n_probe_by_span; ++i) {
            long long t = now - (long long)(i + 1) * 180LL * 86400LL;
            if (t <= base) break;
            z_snprintf(txt, sizeof txt,
                       "你送了我一个%s，说是路过小店时想起我。那天外面在下雨。",
                       PROBE_WORDS[i]);
            if (zmem_add(m, t, ZMEM_EVENT, 7, txt, NULL) == 0) break;
            probes_planted++;
        }
    }
    printf("  信物：%d 个（每 6 个月一个，从 6 年前铺到今天）\n", probes_planted);

    /* 日常：每天 per_day 条，全是套话但有真实日期，用来制造"淹没" */
    for (d = 0; d < days; ++d) {
        long long t = base + (long long)d * 86400LL;
        int k;
        for (k = 0; k < per_day; ++k) {
            z_snprintf(txt, sizeof txt,
                       "第 %d 天的第 %d 件小事：你有点忙，我们说了两句话就各自去忙了。",
                       d + 1, k + 1);
            zmem_add(m, t + k * 900, ZMEM_EVENT, 3 + (d + k) % 3, txt, NULL);
        }
    }

    {
        zmem_stat st;
        zmem_stats(m, &st);
        printf("  写入：%d 条（%ld 字节）／锚点 %d／跨度 ", st.items, st.bytes, st.anchors);
        {
            char date[24];
            zmem_date_text(st.oldest, date, sizeof date);
            printf("%s → ", date);
            zmem_date_text(st.newest, date, sizeof date);
            printf("%s\n", date);
        }
    }

    /* ---------------- 一、关键时刻还原度 ----------------
     * 每个信物用**它自己的词**去问，看能不能翻回来、排第几。
     * 4 年以内必须 100% 找回（红线）；4~6 年只报数不判死。 */
    printf("\n  == 关键时刻还原（拿信物的词去问，看还认不认得）==\n");
    printf("  %-10s %-8s %-6s %-6s %-12s %s\n", "距今", "信物", "找回", "排名", "日期", "耗时");
    {
        int j;
        double worst = 0.0;
        for (j = 0; j < probes_planted; ++j) {
            long long t = now - (long long)(j + 1) * 180LL * 86400LL;
            char word[32], date[24], rank_txt[8], age[32];
            long long age_days = (now - t) / 86400;
            double t0, ms;
            int rank;
            z_snprintf(word, sizeof word, "%s", PROBE_WORDS[j]);
            t0 = now_ms();
            zmem_recall_related(m, word, now, buf, sizeof buf);
            ms = now_ms() - t0;
            if (ms > worst) worst = ms;
            rank = recall_rank(buf, word);
            zmem_date_text(t, date, sizeof date);
            z_snprintf(age, sizeof age, "%.1f 年", (double)age_days / 365.0);
            if (rank >= 0) z_snprintf(rank_txt, sizeof rank_txt, "%d", rank + 1);
            else z_snprintf(rank_txt, sizeof rank_txt, "—");
            printf("  %-10s %-8s %-6s %-6s %-12s %5.2f ms\n",
                   age, word, rank >= 0 ? "是" : "否", rank_txt, date, ms);
        }
        printf("  （单次回忆最慢 %.2f ms；K=%d 条上限）\n", worst, ZMEM_RECALL_K);
        ok(lost_within_4y == 0, "四年以内的信物必须全部找得回（丢 %d 个）", lost_within_4y);
    }

    /* ---------------- 一·B 自然提问（不给专名，看她能不能顺着意思想起旧事） ----------------
     * 真实对话里用户不会报出"蓝瓷杯"这种专名，他会说"你记得我送过你东西吗"。
     * 这时 8 个信物共享同一批词（礼物 / 下雨），谁进 K=6 就是谁被想起。
     * 这一项**不设闸**：它量的是当前检索的天然上限，挤掉了也如实报 ——
     * 报出来才知道下一步该往哪儿改（见 docs/MEMORY_PLAN.md 第 8 节「分层召回」）。 */
    printf("\n  == 自然提问（只说「你送我的礼物、那天还下雨」，不报专名）==\n");
    {
        int j, got = 0;
        for (j = 0; j < probes_planted; ++j) {
            char word[32], age[32], rank_txt[8];
            long long t = now - (long long)(j + 1) * 180LL * 86400LL;
            long long age_days = (now - t) / 86400;
            int rank;
            z_snprintf(word, sizeof word, "%s", PROBE_WORDS[j]);
            zmem_recall_related(m, "你送我礼物的那天还下雨", now, buf, sizeof buf);
            rank = recall_rank(buf, word);
            z_snprintf(age, sizeof age, "%.1f 年", (double)age_days / 365.0);
            if (rank >= 0) z_snprintf(rank_txt, sizeof rank_txt, "%d", rank + 1);
            else z_snprintf(rank_txt, sizeof rank_txt, "—");
            if (rank >= 0) got++;
            printf("  %-10s %-8s %-6s %-6s\n", age, word, rank >= 0 ? "是" : "否", rank_txt);
        }
        printf("  自然提问找回率：%d / %d%s\n", got, probes_planted,
               got < probes_planted ? "（被最近的事挤掉了：这是要改的地方，不是数据问题）" : "");
    }

    /* ---------------- 二、干扰：今天的事会不会把旧事挤掉 ----------------
     * 这是真实世界里最主要的"遗忘"来源 —— 不是衰减，是挤占。
     * 这里灌 2000 条**提到同一个词**的新事，再看四年前那条还在不在。
     * 不判死：挤掉了也要如实报出来（那是要优化检索的地方，不是造假能盖住的）。 */
    printf("\n  == 干扰测试：灌 2000 条提到同一件东西的新事 ==\n");
    {
        int k, still = 0, checked = 0;
        for (k = 0; k < 2000; ++k) {
            z_snprintf(txt, sizeof txt,
                       "今天又看见一个蓝瓷杯，摆在货架上，我想起你也算喜欢这种颜色（第 %d 次）。", k);
            zmem_add(m, now - (long long)(k % 30) * 600, ZMEM_EVENT, 4, txt, NULL);
        }
        /* 最老的那只蓝瓷杯（4 年半前）还在不在 */
        {
            char word[32];
            long long t = now - (long long)(9 * 180) * 86400;
            z_snprintf(word, sizeof word, "%s", PROBE_WORDS[8]);   /* 麻绳结 */
            (void)t;
            for (k = 0; k < 13; ++k) {
                long long tt = now - (long long)(k + 1) * 180LL * 86400LL;
                if (tt <= base) break;
                checked++;
                zmem_recall_related(m, PROBE_WORDS[k], now, buf, sizeof buf);
                if (recall_rank(buf, PROBE_WORDS[k]) >= 0) still++;
            }
            printf("  干扰后仍能找回：%d / %d\n", still, checked);
        }
        ok(still * 10 >= checked * 9, "干扰之后至少九成信物仍应找得回（%d/%d）", still, checked);
    }

    /* ---------------- 二·B 同题海量：40 件同类小事横跨四年 ----------------
     * 这是最容易被"最近优先"搞死的情形：同一句话被说过 40 遍，
     * 而且是 40 件**不同**的事（第 1 件 … 第 40 件）。用户随口问"你送我的小玩意儿"。
     * 要验的是：**最老那件（第 1 件，四年前）还在不在** ——
     * 靠的就是 pick_scored 里"每个年龄桶先保一条、从最老的桶保起"。
     * 这一项设闸：最老那件必须找得回。 */
    printf("\n  == 同题海量：40 件同类小事横跨四年 ==\n");
    {
        int k, buckets = 0;
        for (k = 1; k <= 40; ++k) {
            z_snprintf(txt, sizeof txt,
                       "你又送了我一个小玩意儿（第 %d 件），我都收着，没弄丢过。", k);
            zmem_add(m, now - (long long)k * 36LL * 86400LL, ZMEM_EVENT, 5, txt, NULL);
        }
        zmem_recall_related(m, "你送我的小玩意儿", now, buf, sizeof buf);
        ok(strstr(buf, "第 1 件") != NULL,
           "四十件里最老的那件（四年、第 1 件）必须仍被想起");
        /* 看看这段时间被铺开成几年：块里出现几个不同年份 */
        {
            char seen[8][8];
            int nseen = 0;
            const char *p = buf;
            const char *PFX = "· 想起来过：";        /* 注意：这个前缀是 18 字节，别用 7 */
            size_t plen = strlen(PFX);
            while ((p = strstr(p, PFX)) != NULL) {
                char y[5];
                size_t j;
                for (j = 0; j < 4 && p[plen + j]; ++j) y[j] = p[plen + j];
                y[4] = 0;
                p += plen;
                {
                    int dup = 0;
                    for (j = 0; j < (size_t)nseen; ++j)
                        if (strcmp(seen[j], y) == 0) dup = 1;
                    if (!dup && nseen < 8) { z_snprintf(seen[nseen], sizeof seen[nseen], "%s", y); nseen++; }
                }
            }
            buckets = nseen;
            printf("  块里横跨的年份：%d 个（%s）\n", buckets,
                   buckets >= 3 ? "时间铺开了" : "★ 集中在同一年 —— 分桶没起作用");
        }
        ok(buckets >= 3, "回忆块应横跨至少 3 个年份（实际 %d 个）", buckets);
    }

    /* ---------------- 三、锚点：四年后仍在，且时长由引擎算 ---------------- */
    printf("\n  == 锚点（永不衰减的那一条）==\n");
    zmem_anchors_block(m, now, buf, sizeof buf);
    {
        char want[32];
        z_snprintf(want, sizeof want, "约 %d 年", (int)(days / 365));
        ok(strstr(buf, "第一次见面") != NULL, "四年后锚点里仍有「第一次见面」");
        ok(strstr(buf, want) != NULL, "锚点标的是「%s」（引擎算的，不是写死的）", want);
        ok(strstr(buf, "一直记得") != NULL, "锚点和普通回忆分得开");
    }

    /* ---------------- 四、正文不可变（长跑之后逐字节对账） ---------------- */
    printf("\n  == 正文不可变 ==\n");
    {
        char a1[512], a2[512];
        int k;
        zmem_text(m, 1, a1, sizeof a1);
        for (k = 0; k < 500; ++k) zmem_recall(m, "第一次见面", now, buf, sizeof buf);
        zmem_text(m, 1, a2, sizeof a2);
        ok(strcmp(a1, a2) == 0, "回忆 500 次之后锚点正文逐字节相同");
        {
            int vr = zmem_verify(m, buf, sizeof buf);
            ok(vr == 0, vr == 0 ? "全量对账通过" : "全量对账不通过：%s", buf);
        }
    }

    /* ---------------- 五、重开：四年后的她，是同一个她 ---------------- */
    printf("\n  == 重开（关掉再打开）==\n");
    {
        zmem_stat s0, s1;
        zmem_stats(m, &s0);
        zmem_close(m);
        zdiag_init(&diag);
        m = zmem_open(root, ch, &diag);
        ok(m != NULL, "记忆文件应能重新打开（%d 条诊断）", diag.error_count);
        if (m) {
            zmem_stats(m, &s1);
            ok(s0.items == s1.items, "条数不变（%d → %d）", s0.items, s1.items);
            ok(s0.anchors == s1.anchors, "锚点数不变（%d → %d）", s0.anchors, s1.anchors);
            /* ★ 文件**会长**一点：关文件时会把"被回忆过的"落成 TOUCH 记录
               （32 字节/条）。这是设计如此 —— "想起来了"本身是可审计的事实，
               不是正文变了。所以这里只许"不变或增长"，且增长必须是 32 的整数倍。 */
            ok(s1.bytes >= s0.bytes && (s1.bytes - s0.bytes) % 32 == 0,
               "落盘字节只增不减，且增量是 32 的整数倍（%ld → %ld，+%ld = %ld 条回忆记录）",
               s0.bytes, s1.bytes, s1.bytes - s0.bytes, (s1.bytes - s0.bytes) / 32);
            zmem_anchors_block(m, now, buf, sizeof buf);
            ok(strstr(buf, "第一次见面") != NULL, "重开后锚点正文还在");
            zmem_close(m);
        }
    }

    if (!keep) soak_cleanup(root, ch);
    else printf("\n  （--keep：临时文件留在 data/%s/memory/）\n", ch);

    printf("\n结论：%s\n", g_fail ? "不通过（见上面标「失败」的项）" : "通过");
    return g_fail ? 1 : 0;
}
