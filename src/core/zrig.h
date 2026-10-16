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
/* 这一帧用几个线程做分块合成（默认 = CPU 核数，上限 8；
   环境变量 ZC_RENDER_THREADS 可覆盖，对拍单线程/多线程就靠它）。 */
int zrig_render_threads(void);
/* 强制指定渲染线程数（1 = 单线程）。测试拿它做"单线程 vs 多线程逐字节一致"的对拍。 */
void zrig_set_render_threads(int n);

const zimg *zrig_frame(zrig *r, double scale, int *out_w, int *out_h);

/* --------------------------------------------------------------- 交互 */
/* 画布坐标（未乘 scale）命中测试。threshold 建议 24（alpha 0..255）。 */
int   zrig_hit_test(const zrig *r, int x, int y, int threshold);
/* 返回命中的区域 id（无则 NULL），动作名写入 out_action。
 * 坐标使用画布坐标（rig.json 的 regions 坐标）。 */
const char *zrig_region_at(const zrig *r, int x, int y, char *out_action, size_t cap);
/* 帧缓冲坐标 → 画布坐标（平台层把窗口内坐标换算后调用上面的函数） */
void zrig_frame_to_canvas(const zrig *r, int fx, int fy, int *cx, int *cy);
/* 画布坐标 → 帧缓冲坐标 */
void zrig_canvas_to_frame(const zrig *r, int cx, int cy, int *fx, int *fy);
/* 当前显示缩放；平台层在首帧之前要先 set，否则坐标换算会按 1:1 算 */
double zrig_view_scale(const zrig *r);
void   zrig_set_view_scale(zrig *r, double s);
const char *zrig_region_cursor(const zrig *r, const char *region_id);
/* 按索引枚举区域（给平台层报给 UI 用）；rect 回填画布坐标 [x,y,w,h] */
const char *zrig_region_id_at(const zrig *r, int i);
const char *zrig_region_action_at(const zrig *r, int i);
const char *zrig_region_cursor_at(const zrig *r, int i);
int         zrig_region_rect_at(const zrig *r, int i, int out[4]);

/* --------------------------------------------------------------- 动作 */
int   zrig_action_request(zrig *r, const char *id, const char *reason, int force);
const char *zrig_action(const zrig *r);
int   zrig_action_priority(const zrig *r);
double zrig_action_elapsed(const zrig *r);
/* 动作通道里"直接写部件几何"的条数。Live2D 的 .motion3 只有 Parameter /
   PartOpacity / Model 三种曲线目标，所以合规的 rig 这里应该返回 0。 */
int   zrig_action_geom_channels(const zrig *r);
const char *zrig_action_last_reason(const zrig *r);

/* --------------------------------------------------------------- 眨眼 */
/* 口型同步接管嘴：打开后，动作里所有打了 mouth 标签的通道都不生效，
   嘴完全由参数层（ParamMouthOpenY）说了算。关掉就回到动作驱动。 */
/* 网格形变器（A5）：当前形变量（amount）。没有这个 id 返回 0。 */
/* ---- Pose：互斥部件组（A8，≈ Live2D pose3.json）----
   一组里同一时刻只有一个档位可见，切换带淡入淡出。
   zrig_pose_set 的 entry 传 NULL/""/"none" = 整组淡出；组或档位不存在返回 -1。 */
/* 情绪 → 姿态（T45.2d）。按 poses[].mood_map 把每个组切到对应档位；
   某个组没登记这个情绪就**不动它**（没写 = 与该部位无关，不是要复位）。 */
void   zrig_pose_apply_mood(zrig *r, const char *mood);
/* 情绪 → 参数值（T45.3）。按 rig.json 的 mood_params 直接写参数当前值；
   某条参数没登记这个情绪就**不动它**。猫耳的「直立/飞机耳/前倾」走这条。 */
void   zrig_apply_mood_params(zrig *r, const char *mood);
/* 情绪 → 摆动倍率（第四张情绪表，T45.2f）。读 rig.json 的 mood_swing：
   { "params": [...], "moods": { "angry": [频率倍率, 幅度倍率], ... } }。
   只缩放 amp 不缩放 bias（bias 是静态姿态偏置），切换时做相位补偿避免跳相。
   和另外三张表同口径：**查不到的情绪不动**。 */
void   zrig_apply_mood_swing(zrig *r, const char *mood);
/* 第五张情绪表 tail_flick：情绪 → 自发抽动的频度/力度（T45.2g）。
   前四张改的是"摆动长什么样"，这张改的是"它多久自己动一次、动多狠"。 */
void   zrig_apply_mood_flick(zrig *r, const char *mood);
/* 自发抽动的总开关（默认开）。探针量「慢摆」那张表时必须关掉它，
   不然抽动的非周期脉冲会混进峰峰值里，两张表就分不开了。 */
void   zrig_tail_flick_enable(zrig *r, int on);
int    zrig_pose_count(const zrig *r);
const char *zrig_pose_id(const zrig *r, int i);
int    zrig_pose_entry_count(const zrig *r, const char *group);
const char *zrig_pose_entry_id(const zrig *r, const char *group, int i);
const char *zrig_pose_current(const zrig *r, const char *group);
double zrig_pose_weight(const zrig *r, const char *group, const char *entry);
int    zrig_pose_set(zrig *r, const char *group, const char *entry);
void   zrig_pose_snap(zrig *r);   /* 跳过淡化，直接到位（冻结时钟时用） */

/* ---- xfade：参数驱动的交叉淡化（T24.5）----
   同一个部位有两张姿态图（常态鞋 / 踮脚鞋），由一个参数在两张之间过渡。
   和 Pose 的区别只在驱动源：Pose 是"切一下、定时淡化"，xfade 是"参数到哪、权重到哪"，
   所以能跟动作曲线（.motion3 里的 ParamTiptoe）严丝合缝同步。
   rig.json：{"id":"foot_l_tiptoe","param":"ParamTiptoe","in":[0.25,0.75],
              "from":"seg_foot_l","to":"seg_foot_l_tip"} */
int    zrig_xfade_count(const zrig *r);
const char *zrig_xfade_id(const zrig *r, int i);
/* 淡入件（to）的当前权重 0..1；没有这个 id 返回 -1。 */
double zrig_xfade_weight(const zrig *r, const char *id);
/* 淡出件（from）该留的不透明度 = Live2D SDK CubismPose::DoFade 的曲线
   （Phi=0.5、BackOpacityThreshold=0.15）。纯函数，单测直接打它。 */
double zrig_xfade_hidden(double w);

/* 物理摆当前输出（多段摆调试用）。没有这个 id 返回 0。 */
double zrig_phys_output(const zrig *r, const char *id);

int    zrig_deform_count(const zrig *r);
const char *zrig_deform_id(const zrig *r, int i);
double zrig_deform_amount(const zrig *r, const char *id);

void  zrig_set_mouth_mute(zrig *r, int on);
int   zrig_mouth_mute(const zrig *r);

void  zrig_blink_set_enabled(zrig *r, int enabled);
/* 物理摆总开关。关掉时所有摆立刻停在目标上（输出 0），不攒滞后。
   排查接缝必须关：冻结时钟时物理的 pos 不积分而 target 会跳，输出被拉满 = 假跳变。 */
void  zrig_phys_set_enabled(zrig *r, int enabled);
int   zrig_phys_enabled(const zrig *r);
int   zrig_blink_enabled(const zrig *r);
double zrig_blink_value(const zrig *r);       /* 0 睁 1 闭 */
/* 视线跟随：nx、ny ∈ [-1,1]（归一化屏幕方向）。只作用于带 gaze 标签的部件。 */
void  zrig_gaze(zrig *r, double nx, double ny);
void  zrig_gaze_reset(zrig *r);

/* 指针跟随（头/身跟着光标转，幅度见 rig.json 的 look 段）。
   zrig_gaze 内部已经会调它，单独调用用于只转头不转眼的场合。 */
void   zrig_look(zrig *r, double nx, double ny);
double zrig_look_x(const zrig *r);     /* 平滑后的当前值，测试/调试用 */
/* 有效视线 = 设定视线 + 眼球微动（マイクロサッカード）。
   和 zrig_gaze_x 的区别：后者是"读数"（用户/动作设的值），不含微动底噪。 */
double zrig_gaze_eff_x(const zrig *r);
double zrig_gaze_eff_y(const zrig *r);
double zrig_gaze_x(const zrig *r);        /* 读数：用户/动作设的视线，不含微动 */
double zrig_gaze_max_dx(const zrig *r);   /* 视线满量程（画布像素），换算微动幅度用 */
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
/* 本帧左右眼各自的状态（side: 0=左 1=右）。闭合度 1 = 完全闭上；
   笑眼量 1 = 山型笑眼。笑眼隐含闭眼，所以 close 会 >= smile。 */
double zrig_eye_close(const zrig *r, int side);
double zrig_eye_smile(const zrig *r, int side);
double zrig_eye_pain(const zrig *r, int side);   /* >_< 痛苦闭眼量（0..1），side 0=左 1=右 */
double zrig_eye_wide(const zrig *r, int side);   /* 瞪大量（0..1）；退场由 eye_open 标签管，不在这里压 */
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
/* 部件**最终**的绘制透明度：不只是 alpha 绑定的累乘，还包含标签类的调制
   （eye_open / eye_closed / eye_smile / fx_eye_open）与 Pose 组权重。
   测"特效跟着眨眼变淡"这类行为必须用它 —— zrig_part_channel 只看得到绑定那一半。 */
double zrig_part_draw_opacity(const zrig *r, const char *part_id);

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
void        zrig_viseme_clear(zrig *r);     /* 松口：平滑收回，收干净后自动交还动作 */
void        zrig_viseme_reset(zrig *r);     /* 立刻清空（换角色/换形态用，会跳变） */
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
/* 眨眼随情绪漂移（T44.2）。mood 用平台层的情绪词（happy/angry/sleepy…），
   查 rig.json 的 blink.mood_rate；表里没有就回落常态（1.0/1.0），不算错误。
   rate>1 = 眨得更勤，closed_scale>1 = 每次闭得更久（困倦）。 */
void   zrig_blink_set_mood(zrig *r, const char *mood);
double zrig_blink_rate(const zrig *r);
double zrig_blink_closed_scale(const zrig *r);
const char *zrig_blink_mood(const zrig *r);
int    zrig_blink_mood_count(const zrig *r);

void  zrig_blink_force(zrig *r, int mode);   /* >0 强制闭眼；<=0 交回自动 */
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
