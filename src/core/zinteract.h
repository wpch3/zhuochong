/*
 * zinteract.h - 互动规则与台词（平台无关）
 *
 * 作用：把“点哪里 → 做什么动作 → 说什么话 → 表现什么情绪”从代码里拿出来，
 * 放进 config/interactions.json（规则）与 characters/<角色>/dialogue.json（台词）。
 * 语音通话、情绪回复等新事件只需要新增 kind，不改 zpet 的主流程。
 */
#ifndef ZINTERACT_H
#define ZINTERACT_H

#include "zc.h"

#ifdef __cplusplus
extern "C" {
#endif

#define ZI_MAX_RULES 64
#define ZI_MAX_LINES 128
#define ZI_MAX_TEXTS 8
#define ZI_MAX_REF   8

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
    double cooldown_s;     /* 台词冷却（只限制说话） */
    double last_speak_at;
    char   lines[ZI_MAX_REF][48];
    int    nlines;
} zi_rule;

typedef struct {
    char id[48];
    char texts[ZI_MAX_TEXTS][256];
    int  ntexts;
    int  next;             /* 轮换下标 */
} zi_line;

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
} zinteract;

/* 加载 config/interactions.json 与 characters/<character>/dialogue.json。
 * 失败（文件缺失、schema 不符、引用的台词 id 不存在）时返回 NULL 并写 diag。 */
zinteract *zinteract_load(const char *root_dir, const char *character, zdiag *diag);
void       zinteract_free(zinteract *z);

/* 匹配：kind 必须相同；规则里写了 region / mood 时必须相同；
 * count 为连续摸头次数。返回 priority 最高的规则（同分取先写的）；无匹配返回 NULL。
 * 不做冷却判断（动作总是触发）。 */
const zi_rule *zinteract_match(const zinteract *z, const char *kind,
                               const char *region, const char *mood, int count);

/* 说话：冷却与全局间隔都满足时，取规则第一条台词（按轮换选变体），写入 out 并返回 1；
 * 否则返回 0 且 out 清空。 */
int zinteract_speak(zinteract *z, const zi_rule *r, double now, char *out, size_t cap);

#ifdef __cplusplus
}
#endif
#endif /* ZINTERACT_H */
