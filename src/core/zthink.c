/* zthink —— 脱口而出 vs 先想一想，以及"她自己想说话"。设计说明见 zthink.h。
 *
 * 这里是全引擎唯一一处"决定她要多快回答"的地方。
 * ★ 不写随机数：随机不叫性格，叫掷骰子。同样的输入必须得到同样的判断，
 *   否则"她今天好像有点心事"就变成了没人能解释的抖动。
 */
#include "zthink.h"
#include "zjson.h"

#include <math.h>
#include <stdio.h>
#include <string.h>

/* ------------------------------------------------------------------ 参数 */

void zthink_profile_default(zthink_profile *p)
{
    if (!p) return;
    p->ok = 0;
    p->pace_fast = 0.5;
    p->effort = 0.5;
    p->express = 0.5;
    p->proactive = 0.35;
    p->curiosity = 0.5;
}

static double num01(const zjson *o, const char *k, double def)
{
    double v = zjson_num(zjson_obj_get((zjson *)o, k), -1.0);
    if (v < 0.0) return def;
    if (v > 1.0) v = 1.0;
    return v;
}

void zthink_profile_load(zthink_profile *p, const char *root_dir, const char *character)
{
    char path[1024];
    zjson *doc;
    zerr err;

    zthink_profile_default(p);
    if (!p || !root_dir || !character || !character[0]) return;
    z_snprintf(path, sizeof(path), "%s/characters/%s/mind.params.json", root_dir, character);
    zerr_clear(&err);
    doc = zjson_parse_file(path, &err);
    if (!doc) return;                   /* 缺文件 = 合法状态，不报错 */
    p->pace_fast  = num01(doc, "pace_fast", p->pace_fast);
    p->effort     = num01(doc, "effort", p->effort);
    p->express    = num01(doc, "express", p->express);
    p->proactive  = num01(doc, "proactive", p->proactive);
    p->curiosity  = num01(doc, "curiosity", p->curiosity);
    p->ok = 1;
    zjson_free(doc);
}

/* ------------------------------------------------------------------ 词表 */

/* 「这句话要我想一想」的信号。
 * 为什么用词表而不是长度阈值：真人不是因为句子长才要想，是因为**里面有个要想的东西**。
 * 这些词全部是"没有现成答案"的题：为什么 / 该不该 / 以后 / 难过 / 吵架 …… */
static const char *THINK_WHY[] = {"为什么", "怎么会", "怎么办", "怎么弄", "如何", NULL};
static const char *THINK_CHOICE[] = {"该不该", "要不要", "是不是该", "选哪个", "哪个好",
                                    "你觉得", "你建议", NULL};
static const char *THINK_HEAVY[] = {"难过", "难受", "生气", "吵架", "分手", "离开", "死",
                                   "意义", "后悔", "对不起", "道歉", "孤独", "委屈",
                                   "害怕", "担心", NULL};
static const char *THINK_PAST[] = {"记得", "上次", "以前", "那天", "那时候", "后来",
                                  "第一次", "多久", NULL};

static int hit_any(const char *text, const char *const *tab, int *n)
{
    int i, c = 0;
    for (i = 0; tab[i]; ++i) {
        if (strstr(text, tab[i])) {
            c++;
            if (n) (*n)++;
        }
    }
    return c;
}

/* 按 UTF-8 数"字"，不是数字节：一个汉字 3 字节，按字节算会把一句话判成三倍长 */
static int utf8_chars(const char *s)
{
    int n = 0;
    if (!s) return 0;
    while (*s) {
        unsigned char c = (unsigned char)*s;
        if ((c & 0xC0) != 0x80) n++;
        s++;
    }
    return n;
}

static void clamp01(double *v)
{
    if (*v < 0.0) *v = 0.0;
    if (*v > 1.0) *v = 1.0;
}

const char *zthink_mode_id(int mode)
{
    switch (mode) {
        case ZTHINK_BLURT: return "blurt";
        case ZTHINK_PONDER: return "ponder";
        case ZTHINK_DELIBERATE: return "deliberate";
        default: return "?";
    }
}

const char *zthink_intent_id(int intent)
{
    switch (intent) {
        case ZINTENT_CHAT: return "chat";
        case ZINTENT_REMEMBER: return "remember";
        case ZINTENT_CARE: return "care";
        case ZINTENT_SHARE: return "share";
        default: return "?";
    }
}

/* ------------------------------------------------------------------ 决定 */

void zthink_decide(const zthink_profile *p, const zthink_in *in, zthink_out *out)
{
    zthink_profile def;
    double len_press = 0.0, why = 0.0, choice = 0.0, heavy = 0.0;
    double self_need, quick, familiar, low_mood = 0.0, night = 0.0;
    double score;
    int nlen, nwhy = 0, nchoice = 0, nheavy = 0;
    char *wp;

    if (!out) return;
    memset(out, 0, sizeof(*out));
    if (!p) { zthink_profile_default(&def); p = &def; }
    if (!in) return;

    out->needs_memory = in->text && hit_any(in->text, THINK_PAST, NULL) > 0;

    nlen = utf8_chars(in->text);
    /* 长度压力：12 字以内基本不占分（"嗯""在吗""我回来了"），60 字以上满压 */
    len_press = ((double)nlen - 12.0) / 48.0;
    clamp01(&len_press);
    len_press *= 0.55;

    hit_any(in->text ? in->text : "", THINK_WHY, &nwhy);
    hit_any(in->text ? in->text : "", THINK_CHOICE, &nchoice);
    hit_any(in->text ? in->text : "", THINK_HEAVY, &nheavy);
    /* 多个信号叠加是有上限的：一句话里塞三个"为什么"不会让她想三次 */
    why = (nwhy > 0 ? 0.32 : 0.0) + (nwhy > 1 ? 0.08 : 0.0);
    choice = (nchoice > 0 ? 0.26 : 0.0);
    heavy = (nheavy > 0 ? 0.42 : 0.0) + (nheavy > 1 ? 0.10 : 0.0);
    if (out->needs_memory) heavy += 0.12;      /* 要翻旧账，本来就得想 */

    /* 她自己的倾向 */
    self_need = p->effort * 0.45;
    quick = p->pace_fast * 0.45 + p->express * 0.15;
    familiar = (double)(in->tier < 0 ? 0 : (in->tier > 3 ? 3 : in->tier)) * 0.05;
    if (in->mood < 0.35) low_mood = 0.22;      /* 心情差的时候更容易愣一下 */
    if (in->hour < 7 || in->hour >= 23) night = 0.12;   /* 深夜慢半拍 */

    score = len_press + why + choice + heavy + self_need + low_mood + night
            - quick - familiar;
    out->score = score;

    if (score >= 1.05) out->mode = ZTHINK_DELIBERATE;
    else if (score >= 0.45) out->mode = ZTHINK_PONDER;
    else out->mode = ZTHINK_BLURT;

    /* 停顿：由她的"快"决定，不由模型决定。脱口而出真的可以几乎不停。 */
    switch (out->mode) {
        case ZTHINK_BLURT:
            out->delay_ms = (int)(30.0 + (1.0 - p->pace_fast) * 150.0);
            out->max_tokens = 90;
            break;
        case ZTHINK_PONDER:
            out->delay_ms = (int)(550.0 + p->effort * 700.0);
            out->max_tokens = 170;
            break;
        default:
            out->delay_ms = (int)(1500.0 + p->effort * 2300.0);
            out->max_tokens = 320;
            break;
    }

    /* 先放出来的那句"真反应"。它是这个功能最要紧的部分：
       没有它，"脱口而出"和"想了三秒再回"在用户眼里没有任何区别。 */
    switch (out->mode) {
        case ZTHINK_BLURT:
            if (p->express >= 0.7) z_strlcpy(out->preface, "诶？", sizeof(out->preface));
            else if (p->express >= 0.4) z_strlcpy(out->preface, "嗯", sizeof(out->preface));
            else out->preface[0] = 0;      /* 不外显的人，脱口而出就是直接说，不铺垫 */
            break;
        case ZTHINK_PONDER:
            z_strlcpy(out->preface, p->pace_fast >= 0.6 ? "嗯……让我想想" : "唔……",
                      sizeof(out->preface));
            break;
        default:
            z_strlcpy(out->preface, p->effort >= 0.7 ? "这个我得慢慢想一下"
                                                     : "等一下，我想想", sizeof(out->preface));
            break;
    }

    /* 可审计的加减分明细。缺了它，"她这次为什么想了想"就永远只能猜。 */
    wp = out->why;
    z_snprintf(wp, sizeof(out->why),
               "长句%.2f 为什么%.2f 选择%.2f 重话题%.2f 她的努力%.2f 深夜%.2f 心情%.2f "
               "− 快嘴%.2f − 熟%.2f = %.2f → %s",
               len_press, why, choice, heavy, self_need, night, low_mood,
               quick, familiar, score, zthink_mode_id(out->mode));
}

/* ------------------------------------------------------------------ 主动 */

void zthink_urge_now(const zthink_profile *p, const zthink_in *in,
                     int due_promise, int due_memory, zthink_urge *out)
{
    zthink_profile def;
    double idle_min, base, night_gate = 1.0;
    int64_t since = 0;

    if (!out) return;
    memset(out, 0, sizeof(*out));
    if (!p) { zthink_profile_default(&def); p = &def; }
    if (!in) return;

    /* 冷却：刚开过口就先闭嘴。没有这一条，她会变成复读机。
       90 秒是**她自己**上次开口的时间，不是用户说话的时间 ——
       用户刚说完话她当然可以接，那不算"自己开口"。 */
    since = in->since_last_ms;
    if (since < 90000) {
        out->urge = 0.0;
        out->would_speak = 0;
        out->wait_s = (int)((90000 - since) / 1000) + 1;
        z_snprintf(out->why, sizeof(out->why), "刚说过话（%.0f 秒前），先不打扰",
                   (double)since / 1000.0);
        return;
    }

    /* 闲得越久越想说话：前十几分钟缓慢爬升，之后趋于平顶。
       用 1-exp(-t/T) 而不是线性：真人不会"每分钟固定想说话一次"。 */
    idle_min = (double)since / 60000.0;
    base = 1.0 - exp(-idle_min / 12.0);
    /* ★ 有 0.15 的底、再乘 0.8：否则"主动倾向"就等于她的上限，
       偏内向的人**永远**开不了口（0.55 x 1.0 刚好卡在阈值上）。
       实测踩到过这一格：小寻整整两小时冲动停在 0.55，判定差一个浮点误差就变成永不出声。 */
    out->urge = 0.15 + 0.80 * p->proactive * (0.35 + 0.65 * base);

    /* 好感越高越敢开口（她确定自己不会被打断） */
    out->urge += 0.06 * (double)(in->tier < 0 ? 0 : (in->tier > 3 ? 3 : in->tier));

    /* 记忆里有约定到期：这是**最正当**的开口理由，直接顶上去 */
    if (due_promise) {
        out->urge = 1.0;
        out->intent = ZINTENT_REMEMBER;
    } else if (due_memory && p->curiosity >= 0.45) {
        out->urge += 0.28;
        out->intent = ZINTENT_REMEMBER;
    } else if (in->mood < 0.4) {
        out->urge += 0.20;
        out->intent = ZINTENT_CARE;
    } else {
        out->intent = p->curiosity >= 0.6 ? ZINTENT_SHARE : ZINTENT_CHAT;
    }

    /* 深夜静音：0~6 点几乎不主动（"她真的会自己想事情"不等于半夜吵醒你）。
       7 点前 / 23 点后打折，不是一刀切 —— 熬夜的人确实需要有人说话。 */
    if (in->hour >= 0 && in->hour < 6) night_gate = 0.10;
    else if (in->hour < 8 || in->hour >= 23) night_gate = 0.45;
    out->urge *= night_gate;

    /* 她刚提过话题，对方没接 —— 别追着说第二句（真实的人会退半步） */
    if (in->had_topic) out->urge *= 0.45;

    clamp01(&out->urge);
    out->would_speak = out->urge >= 0.55;
    out->wait_s = out->would_speak ? 0 : (int)(30 + 120 * (1.0 - out->urge));

    z_snprintf(out->why, sizeof(out->why),
               "闲了 %.0f 分钟 · 主动倾向%.2f · 好感档%d%s%s · 夜深折扣%.2f → %.2f%s",
               idle_min, p->proactive, in->tier,
               due_promise ? " · 约定到期" : (due_memory ? " · 有件旧事" : ""),
               in->had_topic ? " · 上一句没被接" : "",
               night_gate, out->urge,
               out->would_speak ? "" : "（还不到开口的时候）");
}
