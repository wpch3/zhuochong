/*
 * zpet.h - 桌宠应用逻辑（平台无关）
 *
 * 这一层是“桌宠的行为大脑”：加载角色包、驱动状态机、处理交互、
 * 空闲后入睡、换形态、换服装。Windows 层（src/win32）与沙箱预览层
 * （src/headless）都只负责“显示与输入”，行为全部在这里，保证一致。
 */
#ifndef ZPET_H
#define ZPET_H

#include "zc.h"
#include "zimg.h"
#include "zrig.h"
#include "zconfig.h"

#ifdef __cplusplus
extern "C" {
#endif

#define ZPET_MAX_FORMS   16
#define ZPET_MAX_OUTFITS 32

typedef enum {
    ZPET_TOOL_HAND = 0,   /* 抚摸 */
    ZPET_TOOL_HAMMER = 1  /* 锤击 */
} zpet_tool;

typedef struct zpet zpet;

/* --------------------------------------------------------------- 生命周期 */
/* 从配置里读角色/形态/服装，加载 characters/<角色>/forms/<形态>/rig.json。 */
zpet *zpet_create(const zconfig *cfg, zdiag *diag);
void  zpet_destroy(zpet *p);

/* --------------------------------------------------------------- 每帧 */
/* 驱动：状态机、眨眼、空闲入睡。now 为单调秒。返回是否发生状态切换。 */
int   zpet_tick(zpet *p, double now);
/* 当前帧（含窗口缩放）。返回只读帧缓冲。 */
const zimg *zpet_frame(zpet *p, int *out_w, int *out_h);

/* --------------------------------------------------------------- 信息 */
const char *zpet_character(const zpet *p);
const char *zpet_form(const zpet *p);
const char *zpet_form_name(const zpet *p);
const char *zpet_outfit(const zpet *p);
const char *zpet_action(const zpet *p);
const char *zpet_last_reason(const zpet *p);
double      zpet_scale(const zpet *p);
double      zpet_blink(const zpet *p);
int         zpet_sleeping(const zpet *p);
double      zpet_idle_seconds(const zpet *p);

/* --------------------------------------------------------------- 交互 */
/* 点命中测试（帧缓冲坐标） */
int   zpet_hit(const zpet *p, int x, int y);
/* 区域查询：x、y 用窗口内（帧缓冲）坐标；返回区域 id（无则 NULL），
 * 并把动作名与光标名写入 out_action / out_cursor */

const char *zpet_region(const zpet *p, int x, int y, char *out_action, size_t cap,
                        const char **out_cursor);
/* 在某个位置“用工具戳一下”：锤击 → hammered，手 → 抚摸/摸头 */
int   zpet_poke(zpet *p, int x, int y, zpet_tool tool, double now);
/* 拖动开始时调用（角色被拽住会挣扎/惊讶） */
int   zpet_drag_start(zpet *p, int x, int y, double now);
int   zpet_drag_end(zpet *p, double now);
/* 鼠标悬停（用于视线跟随/专注状态） */
void  zpet_hover(zpet *p, int x, int y, int inside, double now);
/* 外部活动（键盘/鼠标输入）发生时调用，用于唤醒 */
void  zpet_notify_user_activity(zpet *p, double now);
/* 上报系统级空闲秒数（Windows 用 GetLastInputInfo，其它平台可传 0） */
void  zpet_report_idle(zpet *p, double seconds);
/* 直接触发动作（托盘菜单用） */
int   zpet_action_request(zpet *p, const char *id, const char *reason, int force);

/* --------------------------------------------------------------- 情绪与语音 */
/* 情绪表达：mood 取 joy/sad/surprise/think/sleepy 等（见 interactions.json）。
 * 有对应规则时切换动作并可能说话；没有则只记录。 */
int   zpet_express(zpet *p, const char *mood, double now);
/* 语音通话事件（语音模块接入后调用，语音模块未接入前可由测试/预览调用）：
 *   kind ∈ call_start / call_end / call_user_speaking / call_reply。
 *   call_reply 时 text 为模型回复原文（优先显示）；mood 可选（回复情绪）。 */
int   zpet_call_event(zpet *p, const char *kind, const char *text, const char *mood, double now);
/* 最近一句台词/回复原文，最近一次情绪（UI 显示用；无则为空串） */
const char *zpet_last_line(const zpet *p);
const char *zpet_last_mood(const zpet *p);

/* --------------------------------------------------------------- 形态/服装 */
int   zpet_form_count(const zpet *p);
const char *zpet_form_id_at(const zpet *p, int i);
const char *zpet_form_name_at(const zpet *p, int i);
int   zpet_set_form(zpet *p, const char *form_id, zdiag *diag);
int   zpet_outfit_count(const zpet *p);
const char *zpet_outfit_id_at(const zpet *p, int i);
const char *zpet_outfit_name_at(const zpet *p, int i);
int   zpet_set_outfit(zpet *p, const char *outfit_id, zdiag *diag);

/* 可触发动作列表（托盘菜单用，排除 idle） */
int   zpet_action_count(const zpet *p);
const char *zpet_action_id_at(const zpet *p, int i);

/* --------------------------------------------------------------- 缩放 */
void  zpet_set_scale(zpet *p, double scale);
void  zpet_scale_step(zpet *p, int dir);
void  zpet_scale_reset(zpet *p);

/* --------------------------------------------------------------- 工具 */
void       zpet_set_tool(zpet *p, zpet_tool t);
zpet_tool  zpet_tool_get(const zpet *p);

/* 角色包根目录（用于把窗口状态写回 settings.json） */
void  zpet_sync_to_config(const zpet *p, zconfig *cfg);

#ifdef __cplusplus
}
#endif
#endif /* ZPET_H */
