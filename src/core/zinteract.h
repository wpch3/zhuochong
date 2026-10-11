/*
 * zinteract.h - 互动规则、台词、好感度分级（平台无关）
 *
 * 作用：把“点哪里 → 做什么动作 → 说什么话 → 好感变化”放进配置：
 *   config/interactions.json          规则 + 好感度分级（全局）
 *   characters/<角色>/dialogue.json   该角色的台词（按好感档位给不同说法）
 *   characters/<角色>/character.json  该角色的性格设定（给人看/给模型用）
 * 每个角色的台词与性格不同；互动规则是共用的，只引用台词 id。
 */
#ifndef ZINTERACT_H
#define ZINTERACT_H

#include "zc.h"

#ifdef __cplusplus
extern "C" {
#endif

#define ZI_MAX_RULES  64
#define ZI_MAX_LINES  128
#define ZI_MAX_VARS   6      /* 每条台词的变体数（基础 + 各好感档） */
#define ZI_MAX_TEXTS  8      /* 每个变体里的句子数（轮换） */
#define ZI_MAX_REF    8
#define ZI_MAX_TIERS  4      /* 好感档位数 */

typedef struct {
    char name[24];           /* 档位名，如 初识 / 熟络 / 亲近 / 挚友 */
    int  min_points;         /* 进入该档所需好感值（第一档必须为 0，逐档递增） */
} zi_tier;

typedef struct {
    int  min_tier;           /* 好感档位下限：当前档 ≥ 它才可用，取最高的一个 */
    int  ntexts;
    char texts[ZI_MAX_TEXTS][256];
    int  next;               /* 轮换下标 */
} zi_var;

typedef struct {
    char   id[48];
    zi_var vars[ZI_MAX_VARS];
    int    nvars;
} zi_line;

typedef struct {
    char   id[48];
    char   kind[32];       /* 触发类型，见 interactions.json 说明 */
    char   region[24];     /* 可选：区域 id（head/body/feet） */
    char   mood[24];       /* 可选：情绪（kind=mood 时必填） */
    char   action[48];     /* 要触发的 rig 动作 */
    int    force;          /* 动作是否强制打断 */
    int    reset_count;    /* 命中后连续摸头计数清零 */
    int    priority;
    int    min_count;      /* 连续摸头次数下限 */
    int    affection_gain; /* 好感变化（可为负，如锤击） */
    double cooldown_s;     /* 台词冷却（只限制说话） */
    double last_speak_at;
    int    speak_count;    /* 轮换多条台词用 */
    char   lines[ZI_MAX_REF][48];
    int    nlines;
} zi_rule;

typedef struct {
    zi_rule rules[ZI_MAX_RULES];
    int     nrules;
    zi_line lines[ZI_MAX_LINES];
    int     nlines;
    int     speech_enabled;
    double  min_gap_s;
    double  last_any_speak_at;
    char    character[48];
    int     dialogue_status_draft;   /* dialogue.json 的 status = draft */

    /* 好感度 */
    zi_tier tiers[ZI_MAX_TIERS];
    int     ntiers;
    int     affection;               /* 当前好感值（≥0） */
    int     daily_cap;               /* 每天最多增加的好感值（减少不受限） */
    int     day_gain;                /* 今天已增加的好感值 */
    int     gain_day;                /* 上次计数的日期编号 */
} zinteract;

/* 加载 config/interactions.json 与 characters/<character>/dialogue.json。
 * 失败（文件缺失、schema 不符、档位不递增、台词缺基础文本、引用的台词 id 不存在）时返回 NULL 并写 diag。 */
zinteract *zinteract_load(const char *root_dir, const char *character, zdiag *diag);
void       zinteract_free(zinteract *z);

/* 匹配：kind 必须相同；规则里写了 region / mood 时必须相同；
 * count 为连续摸头次数。返回 priority 最高的规则（同分取先写的）；无匹配返回 NULL。
 * 不做冷却判断（动作总是触发）。 */
const zi_rule *zinteract_match(const zinteract *z, const char *kind,
                               const char *region, const char *mood, int count);

/* 说话：冷却与全局间隔都满足时，轮换选取规则的台词，并按当前好感档选择变体，
 * 写入 out 并返回 1；否则返回 0 且 out 清空。 */
int zinteract_speak(zinteract *z, const zi_rule *r, double now, char *out, size_t cap);

/* ---- 好感度 ---- */
int         zinteract_affection(const zinteract *z);
void        zinteract_set_affection(zinteract *z, int points);
int         zinteract_tier(const zinteract *z);            /* 当前档位下标 */
const char *zinteract_tier_name(const zinteract *z);       /* 当前档位名 */
/* 增加（delta>0 受每日上限约束）或减少（delta<0，不受限，不低于 0）。
 * day 为本地日期编号，用于每日上限重置。返回 1 表示档位提升了。 */
int         zinteract_add_affection(zinteract *z, int delta, int day);

#ifdef __cplusplus
}
#endif
#endif /* ZINTERACT_H */
