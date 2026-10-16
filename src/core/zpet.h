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

/* 画布尺寸（画布坐标 ↔ 帧坐标换算用） */
int         zpet_canvas_w(const zpet *p);
int         zpet_canvas_h(const zpet *p);

/* 区域表枚举：UI 靠它发现 head/body/feet 而不是硬编码 */
int         zpet_region_count(const zpet *p);
const char *zpet_region_id_at(const zpet *p, int i);
const char *zpet_region_action_at(const zpet *p, int i);
const char *zpet_region_cursor_at(const zpet *p, int i);
int         zpet_region_rect_at(const zpet *p, int i, int out[4]);

const char *zpet_region(const zpet *p, int x, int y, char *out_action, size_t cap,
                        const char **out_cursor);
/* 同上，但可以指明入参就是画布坐标，并回填换算后的画布坐标 */
const char *zpet_region_ex(const zpet *p, int x, int y, int is_canvas,
                           char *out_action, size_t cap,
                           const char **out_cursor, int *out_cx, int *out_cy);
/* 在某个位置“用工具戳一下”：锤击 → hammered，手 → 抚摸/摸头 */
int   zpet_poke(zpet *p, int x, int y, zpet_tool tool, double now);
/* 拖动开始时调用（角色被拽住会挣扎/惊讶） */
int   zpet_drag_start(zpet *p, int x, int y, double now);
int   zpet_drag_end(zpet *p, double now);
/* 鼠标悬停（用于视线跟随/专注状态） */
void  zpet_hover(zpet *p, int x, int y, int inside, double now);
/* 外部活动（键盘/鼠标输入）发生时调用，用于唤醒 */
void  zpet_notify_user_activity(zpet *p, double now);

/* 测试台用的直控：按住眨眼参数（<0 恢复自动）、直接给视线方向 */
void   zpet_set_blink(zpet *p, double v);
void   zpet_set_blink_enabled(zpet *p, int on);  /* 关=常睁，开=交回自动 */
int    zpet_blink_enabled(const zpet *p);
/* 物理摆总开关（排查接缝用：冻结时钟时物理会虚报滞后，见 zrig_phys_set_enabled） */
void   zpet_set_phys_enabled(zpet *p, int on);
int    zpet_phys_enabled(const zpet *p);
double zpet_blink_manual(const zpet *p);
/* 形变器（网格形变）当前量：摆链输出多半落在这儿，便于观测与端到端自检 */
int         zpet_phys_count(const zpet *p);
const char *zpet_phys_id_at(const zpet *p, int i);
double      zpet_phys_output(const zpet *p, const char *id);
int         zpet_deform_count(const zpet *p);
const char *zpet_deform_id_at(const zpet *p, int i);
double      zpet_deform_amount(const zpet *p, const char *id);
void   zpet_set_gaze(zpet *p, double nx, double ny, int on);
/* 表情层（≈ Live2D expression）：叠在当前动作之上，和动作互不覆盖 */
int    zpet_expression_count(const zpet *p);
const char *zpet_expression_id_at(const zpet *p, int i);
const char *zpet_expression_name_at(const zpet *p, int i);
const char *zpet_expression(const zpet *p);       /* 当前表情 id，无则 NULL */
int    zpet_expression_set(zpet *p, const char *id);  /* NULL/"" = 取消；未知 id 返回 -1 */

/* Pose：互斥部件组（≈ Live2D pose3.json）。entry 传 NULL/""/"none" = 整组淡出。 */
int    zpet_pose_count(const zpet *p);
const char *zpet_pose_id_at(const zpet *p, int i);
int    zpet_pose_entry_count(const zpet *p, const char *group);
const char *zpet_pose_entry_id_at(const zpet *p, const char *group, int i);
const char *zpet_pose_current(const zpet *p, const char *group);
int    zpet_pose_set(zpet *p, const char *group, const char *entry);
void   zpet_pose_snap(zpet *p);   /* 跳过淡化直接到位（冻结时钟时用） */

/* 命名参数层（≈ Live2D 的 ParamXxx）：测试台滑条 / 脚本 / 口型都走这张表 */
double zpet_param_get(const zpet *p, const char *id);
double zpet_param_effective(const zpet *p, const char *id);
double zpet_param_expr_value(const zpet *p, const char *id);
/* model3.json 的 Groups：口型写哪个参数 / 自动眨眼眨哪只眼（位 0 左、位 1 右） */
const char *zpet_lipsync_param(const zpet *p);
int    zpet_blink_targets(const zpet *p);
int    zpet_param_count(const zpet *p);
int    zpet_param_info(const zpet *p, int i, zrig_param_desc *out);
int    zpet_param_set(zpet *p, const char *id, double v);

/* ---- 口型音素（母音識別）：见 zrig.h 的说明 ---- */
int         zpet_viseme_set(zpet *p, const char *id, double weight);
void        zpet_viseme_clear(zpet *p);
void        zpet_viseme_snap(zpet *p);   /* 冻结时钟时跳过平滑 */
void        zpet_expression_snap(zpet *p);  /* 冻结时钟时表情直接到位 */
double      zpet_viseme_mix(const zpet *p);  /* 口型压过表情的权重（官方 0.8） */
const char *zpet_viseme_current(const zpet *p);   /* 没接管时是空串 */
double      zpet_viseme_weight(const zpet *p);
int         zpet_viseme_count(const zpet *p);
const char *zpet_viseme_id(const zpet *p, int i);
int    zpet_param_reset(zpet *p, const char *id);
void   zpet_param_reset_all(zpet *p);

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

/* ---- 口型同步（A4 / LipSync）----
 * 喂一条 0~1 的开口度包络（`tools/make_lipsync.py` 的产物），引擎按 fps 推进，
 * 每帧写进 ParamMouthOpenY，并让动作里的嘴通道让路（zrig_set_mouth_mute）。
 * 播完自动停：参数回默认、嘴交还给动作。*/
int    zpet_lipsync_start(zpet *p, const double *values, int n, double fps, double now);
/* 带音素的版本：visemes[i] 是第 i 帧的音素名（"A"/"I"/"U"/"E"/"O"/"N"/"SIL"），
   传 NULL 就退回只有开合的音量连动方式。音素给嘴形，包络给强度。 */
int    zpet_lipsync_start_v(zpet *p, const double *values, const char *const *visemes,
                            int n, double fps, double now);
int    zpet_lipsync_load(zpet *p, const char *line_id, double now);  /* 读 voice/lipsync/<id>.json */
void   zpet_lipsync_stop(zpet *p);
int    zpet_lipsync_active(const zpet *p);
double zpet_lipsync_level(const zpet *p);
double zpet_lipsync_remain(const zpet *p);
const char *zpet_lipsync_id(const zpet *p);
const char *zpet_lipsync_text(const zpet *p);
/* 最近一句台词/回复原文，最近一次情绪（UI 显示用；无则为空串） */
const char *zpet_last_line(const zpet *p);
/* 台词序号：每换一句（含被清空）加一。前端靠"seq 变了没"判断是不是新的一句，
   而不是靠比对正文 —— 比正文的话，同一句重复下发会把隐藏计时无限推后，气泡永不消失。 */
unsigned    zpet_last_line_seq(const zpet *p);
/* 这句说出来多久了（秒）。没有台词时返回 -1。 */
double      zpet_last_line_age(const zpet *p, double now);
const char *zpet_last_mood(const zpet *p);
/* 好感度：当前值、档位下标、档位名（如 初识/熟络/亲近/挚友）；测试与预览用可直接设置 */
int         zpet_affection(const zpet *p);
int         zpet_affection_tier(const zpet *p);
const char *zpet_affection_tier_name(const zpet *p);
void        zpet_set_affection(zpet *p, int points);

/* --------------------------------------------------------------- 形态/服装 */
int   zpet_form_count(const zpet *p);
const char *zpet_form_id_at(const zpet *p, int i);
const char *zpet_form_name_at(const zpet *p, int i);
/* 形态路线图：status = ready（素材齐，能切）/ planned（只在 forms.json 里声明，界面灰显） */
const char *zpet_form_status_at(const zpet *p, int i);
const char *zpet_form_note_at(const zpet *p, int i);
int         zpet_form_ready_count(const zpet *p);
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
