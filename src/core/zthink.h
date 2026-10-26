/* zthink —— 脱口而出，还是先想一想（T69.1）
 *
 * 用户原话（第六十九问）
 * ------------------------------------------------------------------
 * 「能不能同时做出人类拥有的脱口而出和思考等跟人类一样的思维模式。并且两种都能
 *   不需要点击什么选项，而且由 AI 自己选择，就像是她真的会自己想事情，
 *   或者就是单纯的想和你说话。」
 *
 * 拆成三件事，缺一件就假
 * ------------------------------------------------------------------
 *   ① **脱口而出**（System 1）：先有反应，再补话。特征是**快**、句子短、
 *      常常是「诶？」「才不是」这种半句，而且不需要先把事情想明白。
 *   ② **认真想**（System 2）：慢，中间有一段沉默，回答更长、更有结构。
 *   ③ **自己想说话**：没有任何人发问，她也会开口。这条最像真人，也最容易被做成
 *      "定时弹广告" —— 所以它必须有**理由**，而且理由要能被打出来看。
 *
 * 三条硬规矩
 * ------------------------------------------------------------------
 *   1. **选择权在引擎，不在用户。** 没有任何"要不要深思"的开关；
 *      用不用想由她自己（数据 + 当下状态）决定。用户能调的只有她这个人本身。
 *   2. **决定必须可解释。** 每个结论都带 `why`：哪几项加了多少分、哪几项减了多少分。
 *      说不清为什么这次脱口而出，那和随机没区别 —— 随机不叫性格。
 *   3. **相同输入必须相同输出。** 不做随机数。她的"快"和"慢"是**倾向**，
 *      不是掷骰子；同一句话同一状态下问两次，判断必须一模一样。
 *
 * 为什么不在提示词里写"请先思考再回答"
 * ------------------------------------------------------------------
 *   那种写法有两个死穴：
 *   · 它只改**措辞**，不改**时序** —— 用户看到的仍然是"发出去 → 等 8 秒 → 一长段"，
 *     中间没有任何"她正在想"的东西。
 *   · 模型没法拒绝。真实的脱口而出是**来不及想**，不是"决定不想"。
 *     所以时序必须由引擎控制：先放一句真反应（preface），再放正答。
 */
#ifndef ZTHINK_H
#define ZTHINK_H

#include <stddef.h>
#include <stdint.h>

#include "zc.h"

/* 三种节奏。名字取的是"她做了什么"，不是"用了哪个模型"。 */
enum {
    ZTHINK_BLURT = 0,      /* 脱口而出：几乎不停顿，短句，常常只有半句 */
    ZTHINK_PONDER = 1,     /* 想一下：几百毫秒到一秒多的停顿 */
    ZTHINK_DELIBERATE = 2  /* 认真想：两秒以上，先给一句"我想想" */
};

/* 她自己开口的四种理由。没有理由的开口 = 打扰。 */
enum {
    ZINTENT_CHAT = 0,      /* 单纯想说话 */
    ZINTENT_REMEMBER = 1,  /* 想起一件事 */
    ZINTENT_CARE = 2,      /* 觉得你状态不对 */
    ZINTENT_SHARE = 3      /* 看到/想到一样东西想给你看 */
};

/* 她的节奏参数（由 tools/mind_probe.py 从 inner.json 的 mind 块导出，
   落在 characters/<id>/mind.params.json）。0~1 的小数，全部有出处。 */
typedef struct {
    int    ok;             /* 0 = 没读到参数文件，走缺省 */
    double pace_fast;      /* 反应快慢：快的 0.85，慢的 0.2 */
    double effort;         /* 愿不愿为一个问题花力气（thinking.effort） */
    double express;        /* 情绪外显（emotion.express） */
    double proactive;      /* 主动开口的倾向（由依恋+冲突脚本+习惯推出） */
    double curiosity;      /* 对"想起一件事"的倾向（openness） */
} zthink_profile;

typedef struct {
    const char *text;      /* 用户这句话（可以为空 = 没人在说话） */
    int    tier;           /* 好感档 0..3 */
    double mood;           /* 当下情绪 0..1（1 = 好） */
    int    hour;           /* 本地小时 0..23 */
    int64_t since_last_ms; /* 距上一句过去多久 */
    int    had_topic;      /* 上一句是不是她提的（连着说会被视为啰嗦） */
} zthink_in;

typedef struct {
    int    mode;           /* ZTHINK_BLURT/PONDER/DELIBERATE */
    int    delay_ms;       /* 正文之前先沉默多久 */
    char   preface[48];    /* 先放出来的那句真反应（空 = 不放） */
    int    max_tokens;     /* 给模型的预算建议（脱口而出就该短） */
    int    needs_memory;   /* 要不要翻记忆（问过去的事才翻） */
    double score;          /* 想一想的分数（可审计） */
    char   why[192];       /* 加减分明细，人话 */
} zthink_out;

typedef struct {
    double urge;           /* 0~1：她现在有多想说 */
    int    would_speak;    /* 1 = 现在就会开口 */
    int    intent;         /* ZINTENT_* */
    int    wait_s;         /* 还要等多久再看一次（0 = 随时） */
    char   why[160];
} zthink_urge;

/* 读 characters/<character>/mind.params.json。缺文件是合法状态（走缺省值）。 */
void zthink_profile_load(zthink_profile *p, const char *root_dir, const char *character);
/* 缺省参数（没有参数文件时用；也是测试的基线） */
void zthink_profile_default(zthink_profile *p);

/* 这一句她会不会先想。纯函数：相同输入必然相同输出。 */
void zthink_decide(const zthink_profile *p, const zthink_in *in, zthink_out *out);

/* 她要不要自己开口。同样纯函数。
 *   due_promise  1 = 记忆里有个约定到期了（这是最正当的开口理由）
 *   due_memory   1 = 记忆里有件值得提的旧事
 *   in            text 可留空；since_last_ms 是**距她自己上次开口**（不是用户说话） */
void zthink_urge_now(const zthink_profile *p, const zthink_in *in,
                     int due_promise, int due_memory, zthink_urge *out);

const char *zthink_mode_id(int mode);      /* "blurt"/"ponder"/"deliberate" */
const char *zthink_intent_id(int intent);  /* "chat"/"remember"/"care"/"share" */

#endif /* ZTHINK_H */
