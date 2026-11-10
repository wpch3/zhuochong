/*
 * zsm.h - 动作状态机（优先级 + 可中断 + 过期回退）
 *
 * 语义参考并简化自参考项目 ds-local-pet 的 animation/state_machine.py：
 *   1. 高优先级动作可以打断低优先级动作；
 *   2. 当前动作若声明“不可中断”，则同优先级或更低优先级的请求一律被拒绝；
 *   3. 动作到期后回到 return_state（默认 idle），或进入排队状态；
 *   4. 同一状态重复请求不会重置计时（除非 force=1，用于连击类交互）。
 *
 * 这是纯逻辑，不涉及平台，可在沙箱里单元测试。
 */
#ifndef ZSM_H
#define ZSM_H

#include "zc.h"

#ifdef __cplusplus
extern "C" {
#endif

/* 2026-10-25（第六十三问 P0）：32 → 96，与 zrig.c 的 ZRIG_MAX_ACTIONS 同步。
   为什么必须一起抬：zrig 的每个动作都会登记成一个状态，两个上限不同步的结果是
   "动作段能装 96 条，但装到第 33 条时状态机先炸"，报错还只说"动作 id 重复或状态数超限"。
   这类"两个上限各说各话"的坑，本文件里已经不是第一次（见 zsm.c 的注释）。 */
#define ZSM_MAX_STATES 96
#define ZSM_ID_MAX 48

typedef struct {
    char id[ZSM_ID_MAX];
    int  priority;                 /* 越大越“抢” */
    double duration_s;             /* < 0 表示循环，不自动结束 */
    int  interruptible;            /* 0：不允许被同/低优先级打断 */
    char return_state[ZSM_ID_MAX]; /* "" → idle */
    int  loop;                     /* duration_s < 0 时的显式声明 */
} zsm_state_def;

typedef struct {
    int  from;                 /* -1 表示无 */
    int  to;
    int  forced;
    double at;
    char reason[64];
} zsm_transition;

typedef struct {
    zsm_state_def defs[ZSM_MAX_STATES];
    int    n;
    int    current;              /* 索引 */
    int    queued;               /* 结束后进入，-1 无 */
    double entered_at;
    double now;
    zrand  rng;
    unsigned change_count;
    unsigned reject_count;
    zsm_transition last;
    /* 可选回调：状态变化时通知（例如打日志） */
    void (*on_change)(void *ud, const char *from, const char *to, const char *reason, int forced);
    void  *ud;
} zsm;

void zsm_init(zsm *sm);
int  zsm_add_state(zsm *sm, const zsm_state_def *def);      /* 返回索引，-1 失败 */
int  zsm_index(const zsm *sm, const char *id);
/* 设置初始状态并复位计时。失败返回 -1。 */
int  zsm_start(zsm *sm, const char *initial, double now);
/* 请求切换。返回 1 已切换 / 0 被拒绝（原因见 zsm_last_reject）。 */
int  zsm_request(zsm *sm, const char *id, const char *reason, int force);
/* 驱动：处理到期回退。返回 1 发生了切换。 */
int  zsm_update(zsm *sm, double now);
void zsm_queue_after(zsm *sm, const char *id);

const char *zsm_current_id(const zsm *sm);
int         zsm_current_priority(const zsm *sm);
double      zsm_elapsed(const zsm *sm);
int         zsm_is_looping(const zsm *sm);
const char *zsm_last_reject(void);

#ifdef __cplusplus
}
#endif
#endif /* ZSM_H */
