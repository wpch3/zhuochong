/*
 * zrig.h - 动态立绘骨架与图层合成（数据驱动，全部来自 characters/<角色>/forms/<形态>/rig.json）
 *
 * 设计目标（对应交接文件 2.6 / 8.4）：
 *   - 核心代码不认识任何具体角色：角色包换一份 rig.json 就换一套立绘；
 *   - 图层（parts）、骨骼组（groups）、动作（actions，含通道曲线 channels）、
 *     交互区域（regions）、眨眼（blink）全部声明在配置里；
 *   - 拆件到位后（眼睛/嘴/身体分段）不用改 C 代码即可生效。
 *
 * 坐标系：画布原点左上，单位像素；origin 为角色脚底中心。
 * 渲染：每帧把 parts 按 layer 顺序合成为一张 RGBA 画布。
 */
#ifndef ZRIG_H
#define ZRIG_H

#include "zc.h"
#include "zimg.h"

#ifdef __cplusplus
extern "C" {
#endif

typedef struct zrig zrig;

/* --------------------------------------------------------------- 加载 */
/* rig_path: rig.json 路径；base_dir: 资源相对路径的基准目录（通常是 rig.json 所在目录）。
 * 出错时把问题写进 diag（文件/行/字段/原因），返回 NULL。 */
zrig *zrig_load(const char *rig_path, const char *base_dir, zdiag *diag);
void  zrig_free(zrig *r);

/* --------------------------------------------------------------- 信息 */
const char *zrig_id(const zrig *r);
const char *zrig_name(const zrig *r);
int   zrig_canvas_w(const zrig *r);
int   zrig_canvas_h(const zrig *r);
int   zrig_part_count(const zrig *r);
const char *zrig_part_id(const zrig *r, int i);
int   zrig_action_count(const zrig *r);
const char *zrig_action_id_at(const zrig *r, int i);
int   zrig_region_count(const zrig *r);

/* --------------------------------------------------------------- 每帧 */
/* 驱动状态机与眨眼（传入单调时钟秒）。 */
void  zrig_tick(zrig *r, double now);
/* 合成当前帧。scale 为窗口缩放（1.0 = 画布原始比例）。
 * 返回内部帧缓冲（只读，尺寸写入 out_w/out_h）。 */
const zimg *zrig_frame(zrig *r, double scale, int *out_w, int *out_h);

/* --------------------------------------------------------------- 交互 */
/* 画布坐标（未乘 scale）命中测试。threshold 建议 24（alpha 0..255）。 */
int   zrig_hit_test(const zrig *r, int x, int y, int threshold);
/* 返回命中的区域 id（无则 NULL），动作名写入 out_action。
 * 坐标使用画布坐标（rig.json 的 regions 坐标）。 */
const char *zrig_region_at(const zrig *r, int x, int y, char *out_action, size_t cap);
/* 帧缓冲坐标 → 画布坐标（平台层把窗口内坐标换算后调用上面的函数） */
void zrig_frame_to_canvas(const zrig *r, int fx, int fy, int *cx, int *cy);
const char *zrig_region_cursor(const zrig *r, const char *region_id);

/* --------------------------------------------------------------- 动作 */
int   zrig_action_request(zrig *r, const char *id, const char *reason, int force);
const char *zrig_action(const zrig *r);
int   zrig_action_priority(const zrig *r);
double zrig_action_elapsed(const zrig *r);
const char *zrig_action_last_reason(const zrig *r);

/* --------------------------------------------------------------- 眨眼 */
/* 口型同步接管嘴：打开后，动作里所有打了 mouth 标签的通道都不生效，
   嘴完全由参数层（ParamMouthOpenY）说了算。关掉就回到动作驱动。 */
/* 网格形变器（A5）：当前形变量（amount）。没有这个 id 返回 0。 */
/* ---- Pose：互斥部件组（A8，≈ Live2D pose3.json）----
   一组里同一时刻只有一个档位可见，切换带淡入淡出。
   zrig_pose_set 的 entry 传 NULL/""/"none" = 整组淡出；组或档位不存在返回 -1。 */
int    zrig_pose_count(const zrig *r);
const char *zrig_pose_id(const zrig *r, int i);
int    zrig_pose_entry_count(const zrig *r, const char *group);
const char *zrig_pose_entry_id(const zrig *r, const char *group, int i);
const char *zrig_pose_current(const zrig *r, const char *group);
double zrig_pose_weight(const zrig *r, const char *group, const char *entry);
int    zrig_pose_set(zrig *r, const char *group, const char *entry);
void   zrig_pose_snap(zrig *r);   /* 跳过淡化，直接到位（冻结时钟时用） */

/* 物理摆当前输出（多段摆调试用）。没有这个 id 返回 0。 */
double zrig_phys_output(const zrig *r, const char *id);

int    zrig_deform_count(const zrig *r);
const char *zrig_deform_id(const zrig *r, int i);
double zrig_deform_amount(const zrig *r, const char *id);

void  zrig_set_mouth_mute(zrig *r, int on);
int   zrig_mouth_mute(const zrig *r);

void  zrig_blink_set_enabled(zrig *r, int enabled);
int   zrig_blink_enabled(const zrig *r);
double zrig_blink_value(const zrig *r);       /* 0 睁 1 闭 */
/* 视线跟随：nx、ny ∈ [-1,1]（归一化屏幕方向）。只作用于带 gaze 标签的部件。 */
void  zrig_gaze(zrig *r, double nx, double ny);
void  zrig_gaze_reset(zrig *r);

/* 指针跟随（头/身跟着光标转，幅度见 rig.json 的 look 段）。
   zrig_gaze 内部已经会调它，单独调用用于只转头不转眼的场合。 */
void   zrig_look(zrig *r, double nx, double ny);
double zrig_look_x(const zrig *r);     /* 平滑后的当前值，测试/调试用 */
double zrig_look_y(const zrig *r);
/* --------------------------------------------- 命名参数层（≈ Live2D ParamXxx）
   一张"参数表"：内建参数路由到视线/眨眼/头部跟随，其余由 rig.json 的 params 段
   声明并绑定到组或部件的通道。外部（脚本、口型、表情、测试台滑条）只写这张表，
   不需要知道角色内部结构。内建 id：ParamAngleX / ParamAngleY / ParamEyeOpen
   （ParamEyeLOpen / ParamEyeROpen 是它的别名）/ ParamEyeBallX / ParamEyeBallY。 */
typedef struct {
    const char *id;
    const char *label;        /* 中文名，可能是空串 */
    double vmin, vmax, vdef, value;
    int    builtin;           /* 1 = 内建（走子系统），0 = rig.json 声明的绑定参数 */
    int    binds;             /* 绑定条数 */
} zrig_param_desc;

int    zrig_param_count(const zrig *r);
const char *zrig_param_id(const zrig *r, int i);
int    zrig_param_info(const zrig *r, int i, zrig_param_desc *out);
double zrig_param_get(const zrig *r, const char *id);
/* 这一帧的最终值：参数值 → 动作通道 → 表情（Add/Multiply/Overwrite）→ 口型音素。
   `zrig_param_get` 只给参数自己的值，排查"表情和口型抢同一个参数"时要看这个。 */
double zrig_param_effective(const zrig *r, const char *id);
double zrig_param_expr_value(const zrig *r, const char *id); /* 只到表情层，不含口型 */
int    zrig_param_set(zrig *r, const char *id, double v);   /* 找不到返回 -1 */
int    zrig_param_reset(zrig *r, const char *id);           /* 回默认值 */
void   zrig_param_reset_all(zrig *r);

/* --------------------------------------------- 表情层（≈ Live2D expression）
   表情 = 一组参数偏移（add 叠加 / set 覆盖），带淡入淡出，叠在当前动作之上。
   和动作是两条独立的轨：可以"笑着挥手"，不用为每种组合再做一个动作。
   声明在 rig.json 顶层的 expressions 段。 */
int    zrig_expression_count(const zrig *r);
const char *zrig_expression_id(const zrig *r, int i);
const char *zrig_expression_name(const zrig *r, int i);
const char *zrig_expression(const zrig *r);        /* 当前表情 id，无则 NULL */
int    zrig_expression_set(zrig *r, const char *id);  /* id 传 NULL/"" = 取消；未知 id 返回 -1 */
void   zrig_expression_clear(zrig *r);
void   zrig_expression_snap(zrig *r);   /* 跳过淡入淡出直接到位（冻结时钟时用） */
double zrig_expression_weight(const zrig *r);      /* 淡化权重 0..1（测试用） */

/* 手动按住眨眼参数（0=睁 1=闭，传 <0 恢复自动）。测试台的眨眼滑条用。 */
void   zrig_blink_set_manual(zrig *r, double v);
double zrig_blink_manual(const zrig *r);
/* 部件级通道当前值（调试/测试用），param 为 dx/dy/sx/sy/rot_deg/alpha */
double zrig_part_channel(const zrig *r, const char *part_id, const char *param);

/* 参数分组（≈ model3.json 的 "Groups"）：
   LipSync 组的第一个参数 / EyeBlink 组覆盖的眼（位 0 左、位 1 右）。 */
const char *zrig_lipsync_param(const zrig *r);
int         zrig_blink_targets(const zrig *r);

/* ------------------------------------------- 口型音素层（母音識別 / viseme）
   Live2D 官方标准参数里没有 ParamMouthA/I/U/E/O：あ/い/う/え/お 是用
   「ParamMouthOpenY（开多大）× ParamMouthForm（咧开 / 撅圆）」两个标准参数的
   组合摆出来的。这里就是那张组合表 + 一个带张开快/收口慢的平滑器。
   表默认内建，可在 rig.json 顶层用 "visemes" 覆盖：
     "visemes":[{"id":"A","params":{"ParamMouthOpenY":1.0,"ParamMouthForm":0.0}}, ...]
   用法：zrig_viseme_set(r,"I",0.8) 每帧喂「当前音素 + 当前音量」，
         不说话时 zrig_viseme_set(r,"SIL",0) 或 zrig_viseme_clear(r)。 */
int         zrig_viseme_count(const zrig *r);
const char *zrig_viseme_id(const zrig *r, int i);
int         zrig_viseme_find(const zrig *r, const char *id);     /* 大小写不敏感，-1 = 没有 */
int         zrig_viseme_entry_count(const zrig *r, int vi);
int         zrig_viseme_entry(const zrig *r, int vi, int k,
                              const char **param_id, double *value);
int         zrig_viseme_set(zrig *r, const char *id, double weight);  /* 不认识的音素返回 -1 */
void        zrig_viseme_clear(zrig *r);     /* 立刻松口，嘴交还给动作 */
void        zrig_viseme_snap(zrig *r);      /* 跳过平滑直接到位（冻结时钟时用） */
const char *zrig_viseme_current(const zrig *r);   /* 没接管时返回 NULL */
double      zrig_viseme_weight(const zrig *r);   /* 这一帧的音量/强度 0..1（不是下面那个） */
/* 口型压过表情的权重（rig.json 的 viseme_weight，默认 0.8 = 官方 SDK 对 LipSync 的权重）。 */
double      zrig_viseme_mix(const zrig *r);

/* 调试/测试用的只读查询：
   zrig_group_offset_x/y —— 组这一帧的横/纵位移（通道位移 + 自动跟随形变的位移，画布像素）。
   zrig_bend_at          —— 某部件的形变在画布高度 canvas_y 处把像素推了多远（画布像素）。
   二者配合可以验证"五官有没有跟住身体"。查不到对象时返回 0。 */
double zrig_group_offset_x(const zrig *r, const char *group_id);
double zrig_group_offset_y(const zrig *r, const char *group_id);
double zrig_bend_at(const zrig *r, const char *part_id, double canvas_y);
/* 部件这一帧的实际横向位移（通道 + 组 + 跟随形变）与它的画布纵坐标。 */
double zrig_part_offset_x(const zrig *r, const char *part_id);
double zrig_part_pos_y(const zrig *r, const char *part_id);
/* 这个部件的"跟随取样高度"：组写了 bend_follow_at 就是那个关节点高度，
   否则是部件自己的纵坐标。验证跟随对不对时要用它，不能想当然用部件高度。 */
double zrig_part_follow_y(const zrig *r, const char *part_id);
/* 这个部件跟随的是哪个部件（组的 bend_follow）；不跟随返回 NULL。 */
const char *zrig_part_follow_src(const zrig *r, const char *part_id);

/* 调试/测试：强制闭眼或恢复自动 */
void  zrig_blink_force(zrig *r, int force_closed);
/* 立即触发一次眨眼（用于交互反馈，如被锤击） */
void  zrig_blink_trigger(zrig *r);

/* --------------------------------------------------------------- 诊断 */
/* 把当前 rig 摘要写成一行（日志用） */
void  zrig_describe(const zrig *r, char *out, size_t cap);

#ifdef __cplusplus
}
#endif
#endif /* ZRIG_H */

/* --------------------------------------------------------------- 换装 */
/* 应用服装包（outfits/<id>.json）。格式：
 *   { "id": "...", "name": "...",
 *     "parts": { "<部件id>": { "file": "相对基准目录的图片", "pos": [x,y], "scale": 1.0 } } }
 * 只覆盖列出的部件；未列出的保持原样。失败时写 diag 且不改动已加载内容，
 * 返回 -1（调用方决定是否继续用原服装）。 */
int zrig_apply_outfit(zrig *r, const char *outfit_json_path, zdiag *diag);
/* 当前服装 id（未换装时为空串） */
const char *zrig_outfit(const zrig *r);
/* 重新加载全部部件图片（切换形态或外部替换素材后调用） */
int zrig_reload_parts(zrig *r, zdiag *diag);
