/* zsm.c - 动作状态机实现 */
#include "zsm.h"

static char g_last_reject[160] = "none";

void zsm_init(zsm *sm)
{
    memset(sm, 0, sizeof(*sm));
    sm->current = -1;
    sm->queued = -1;
    zrand_seed(&sm->rng, 0xC0FFEEull);
}

int zsm_add_state(zsm *sm, const zsm_state_def *def)
{
    if (!sm || !def || sm->n >= ZSM_MAX_STATES || !def->id[0]) return -1;
    if (zsm_index(sm, def->id) >= 0) return -1;   /* 重名 */
    sm->defs[sm->n] = *def;
    return sm->n++;
}

int zsm_index(const zsm *sm, const char *id)
{
    int i;
    if (!sm || !id) return -1;
    for (i = 0; i < sm->n; ++i)
        if (strcmp(sm->defs[i].id, id) == 0) return i;
    return -1;
}

int zsm_start(zsm *sm, const char *initial, double now)
{
    int idx;
    if (!sm) return -1;
    idx = initial ? zsm_index(sm, initial) : -1;
    if (idx < 0) idx = zsm_index(sm, "idle");
    if (idx < 0 && sm->n > 0) idx = 0;
    if (idx < 0) return -1;
    sm->current = idx;
    sm->queued = -1;
    sm->entered_at = now;
    sm->now = now;
    sm->last.from = -1;
    sm->last.to = idx;
    sm->last.forced = 0;
    sm->last.at = now;
    z_strlcpy(sm->last.reason, "startup", sizeof(sm->last.reason));
    if (sm->on_change) sm->on_change(sm->ud, NULL, sm->defs[idx].id, "startup", 0);
    return 0;
}

int zsm_request(zsm *sm, const char *id, const char *reason, int force)
{
    int target, cur;
    const zsm_state_def *cd;
    if (!sm) return 0;
    target = zsm_index(sm, id);
    if (target < 0) {
        z_snprintf(g_last_reject, sizeof(g_last_reject), "未知状态 '%s'", id ? id : "(null)");
        return 0;
    }
    cur = sm->current;
    if (cur < 0) {
        sm->current = target;
        sm->entered_at = sm->now;
        return 1;
    }
    if (target == cur) {
        if (!force) {
            z_snprintf(g_last_reject, sizeof(g_last_reject), "已处于状态 '%s'", id);
            return 0;
        }
        /* force：重播当前动作（连击反馈） */
        sm->entered_at = sm->now;
        return 1;
    }
    cd = &sm->defs[target];
    {
        const zsm_state_def *cc = &sm->defs[cur];
        if (!force) {
            if (!cc->interruptible && cd->priority <= cc->priority) {
                z_snprintf(g_last_reject, sizeof(g_last_reject),
                           "'%s'(优先级 %d) 被不可中断的 '%s'(优先级 %d) 拒绝",
                           cd->id, cd->priority, cc->id, cc->priority);
                sm->reject_count++;
                return 0;
            }
            if (cd->priority < cc->priority) {
                z_snprintf(g_last_reject, sizeof(g_last_reject),
                           "'%s'(优先级 %d) 低于当前 '%s'(优先级 %d)",
                           cd->id, cd->priority, cc->id, cc->priority);
                sm->reject_count++;
                return 0;
            }
        }
    }
    sm->last.from = cur;
    sm->last.to = target;
    sm->last.forced = force ? 1 : 0;
    sm->last.at = sm->now;
    z_strlcpy(sm->last.reason, reason ? reason : "", sizeof(sm->last.reason));
    sm->current = target;
    sm->entered_at = sm->now;
    sm->queued = -1;
    sm->change_count++;
    if (sm->on_change) sm->on_change(sm->ud, sm->defs[cur].id, sm->defs[target].id,
                                     reason, force ? 1 : 0);
    return 1;
}

int zsm_update(zsm *sm, double now)
{
    const zsm_state_def *cur;
    if (!sm || sm->current < 0) return 0;
    sm->now = now;
    cur = &sm->defs[sm->current];
    if (cur->loop || cur->duration_s < 0) return 0;
    if (now - sm->entered_at < cur->duration_s) return 0;
    {
        int target = sm->queued;
        if (target < 0) {
            target = cur->return_state[0] ? zsm_index(sm, cur->return_state) : -1;
            if (target < 0) target = zsm_index(sm, "idle");
        }
        if (target < 0 || target == sm->current) {
            sm->entered_at = now;   /* 无处可回则原地重播，避免卡死 */
            return 0;
        }
        {
            char reason[80];
            z_snprintf(reason, sizeof(reason), "%s_finished", cur->id);
            sm->last.from = sm->current;
            sm->last.to = target;
            sm->last.forced = 0;
            sm->last.at = now;
            z_strlcpy(sm->last.reason, reason, sizeof(sm->last.reason));
            sm->current = target;
            sm->entered_at = now;
            sm->queued = -1;
            sm->change_count++;
            if (sm->on_change) sm->on_change(sm->ud, reason, sm->defs[target].id, reason, 0);
            return 1;
        }
    }
}

void zsm_queue_after(zsm *sm, const char *id)
{
    int idx;
    if (!sm || !id) return;
    idx = zsm_index(sm, id);
    sm->queued = idx;
}

const char *zsm_current_id(const zsm *sm)
{
    if (!sm || sm->current < 0 || sm->current >= sm->n) return "";
    return sm->defs[sm->current].id;
}

int zsm_current_priority(const zsm *sm)
{
    if (!sm || sm->current < 0 || sm->current >= sm->n) return 0;
    return sm->defs[sm->current].priority;
}

double zsm_elapsed(const zsm *sm)
{
    if (!sm) return 0.0;
    return sm->now - sm->entered_at;
}

int zsm_is_looping(const zsm *sm)
{
    if (!sm || sm->current < 0) return 0;
    return sm->defs[sm->current].loop || sm->defs[sm->current].duration_s < 0;
}

const char *zsm_last_reject(void) { return g_last_reject; }
