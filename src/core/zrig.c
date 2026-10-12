/* zrig.c - 动态立绘骨架与图层合成实现 */
#include "zrig.h"
#include "zjson.h"
#include "zsm.h"

#include <math.h>

#define ZRIG_MAX_PARTS    64
#define ZRIG_MAX_GROUPS   16
#define ZRIG_MAX_CHANNELS 64
#define ZRIG_MAX_REGIONS  32
#define ZRIG_MAX_ACTIONS  32
#define ZRIG_MAX_PHYS     12
#define ZRIG_MAX_PARAMS   48
#define ZRIG_MAX_EXPR     16
#define ZRIG_MAX_EXPR_SET 96
#define ZRIG_MAX_BINDS    96
#define ZRIG_MAX_OVERRIDES 32

/* 图层标签（tags）：用位标志，加载时解析 */
enum {
    TAG_BODY = 1u << 0,
    TAG_HEAD = 1u << 1,
    TAG_EYE_OPEN = 1u << 2,
    TAG_EYE_CLOSED = 1u << 3,
    TAG_MOUTH = 1u << 4,
    TAG_HAIR = 1u << 5,
    TAG_ACCESSORY = 1u << 6,
    TAG_TAIL = 1u << 7,
    TAG_GAZE = 1u << 8,     /* 会被视线偏移影响的部件（虹膜/眼球） */
    TAG_EYELID = 1u << 9    /* 眼睑：随眨眼参数往下滑（配 eyelid_travel 用） */
};

/* 通道参数 */
enum { P_DX = 0, P_DY, P_SX, P_SY, P_ROT, P_ALPHA, P_BEND_X, P_BEND_Y };
/* 形变曲线：0=根部固定（头发/裙摆） 1=中间最大（弯腰/呼吸） 2=线性 */
/* 形变曲线与 zimg 保持同一套语义（底边=根）：root 底固定/顶部最大，sine 中段最大，
   linear 线性，tip 顶固定/底端最大（后发、裙摆、尾巴）。 */
enum { BEND_ROOT = ZIMG_BEND_ROOT, BEND_SINE = ZIMG_BEND_SINE,
       BEND_LINEAR = ZIMG_BEND_LINEAR, BEND_TIP = ZIMG_BEND_TIP };
/* 通道波形 */
enum { W_SINE = 0, W_BOUNCE, W_PULSE, W_DECAY, W_FLAP };

typedef struct {
    char   id[48];
    double pivot[2];
    int    parent;            /* 组索引，-1 无 */
    char   follow_id[64];     /* bend_follow：跟随哪个部件的形变（解析期暂存 id） */
    int    follow_part;       /* 解析后的部件索引，-1 表示不跟随 */
    double follow_at;         /* bend_follow_at：按这个画布高度取样（0=按部件自身高度） */
} zgroup;

typedef struct {
    char   id[64];
    char   file[512];
    zimg  *img;               /* 原始（原始分辨率，直通 alpha） */
    zimg  *img_scaled;        /* 当前 scale 下的缓存 */
    int    layer;
    int    group;             /* 组索引 */
    double pos[2];            /* 画布坐标（锚点落点） */
    double anchor[2];         /* 0..1，相对部件图像 */
    double scale;             /* 等比基准缩放（老字段，保留） */
    double scale_x, scale_y;  /* 分轴基准缩放："scale":[sx,sy] 时用，嘴的开合靠它 */
    double rot_deg;
    double opacity;
    unsigned tags;
    char   mask_id[64];       /* rig 里写的 "mask"：被哪个部件裁切（解析期暂存 id） */
    int    mask;              /* 解析后的部件索引，-1 表示不裁切 */
    int    mask_only;         /* 1 = 自己只当遮罩用，不画出来 */
    int    is_mask_src;       /* 1 = 有别的部件拿我当遮罩 */
    char   motion_id[64];     /* motion_from：照抄哪个部件的通道值（解析期暂存 id） */
    int    motion_from;       /* 解析后的部件索引，-1 = 用自己的 */
    double eyelid_travel;     /* 眼睑行程：眨眼参数 1 时往下滑多少画布像素 */
} zpart;

typedef struct {
    char   target[48];        /* 组 id、部件 id，或 "root" */
    int    group;             /* >=0 表示作用在组 */
    int    part;              /* >=0 表示作用在部件 */
    int    param;
    int    wave;
    double amp, freq, phase, dur;
    zease  ease;
    int    curve;             /* 形变曲线（仅 bend_* 用） */
    int    strips;            /* 分段数（仅 bend_* 用；0=默认 24） */
} zchan;

typedef struct { char part[64]; double opacity; int has_dx, has_dy; double dx, dy; } zoverride;

typedef struct {
    char   id[48];
    int    priority;
    double duration;          /* 秒；<0 循环 */
    int    loop;
    int    interruptible;
    char   return_state[48];
    zchan  chans[ZRIG_MAX_CHANNELS];
    int    nchan;
    zoverride ovr[ZRIG_MAX_OVERRIDES];
    int    novr;
    double dim;               /* 0..1：睡眠等状态的压暗程度 */
    double blink_hold;        /* 0..1：这个动作期间眼睛闭合到几成（<0 = 不管） */
    double fade;              /* 秒：从上一个动作淡入到这个动作的时间（Live2D 的 FadeInTime） */
} zaction;

/* 物理摆动（Live2D physics 的最小可用版）：
   一根挂在驱动组上的弹簧-阻尼摆。输入 = 驱动组这一帧的位移，
   输出 = 摆尖**落后/过冲**的那一点距离，加到部件的形变通道上。
   静止时输出收敛到 0，所以它只负责"动起来之后的惯性"，不改变静止姿态。 */
typedef struct {
    char   id[32];
    int    part;              /* 输出到哪个部件 */
    int    driver;            /* 驱动组索引 */
    int    axis;              /* 0 = 看驱动组的 dx，1 = dy */
    int    param;             /* 输出通道（bend_x/bend_y/dx/dy/rot_deg） */
    int    curve;             /* 形变曲线（仅 bend_* 用） */
    double ratio;             /* 摆尖跟随驱动位移的比例 */
    double stiffness;         /* 弹簧刚度（1/s²，越大越跟手） */
    double damping;           /* 阻尼（1/s，越大越快停） */
    double max;               /* 输出限幅（像素或度） */
    double pos, vel;          /* 运行状态 */
} zphys;

/* 指针跟随（Live2D 的 ParamAngleX/Y/Z + ParamBodyAngleX 那一套）：
   一个 [-1,1] 的方向输入，按组配置成旋转/位移。注意它**不是动作**，
   是叠加在动作之上的姿态偏置，所以任何动作期间都能跟着指针转头。 */
typedef struct {
    int    group;
    double rot, dx, dy;
} zlook;

/* ---------------- 命名参数层（对齐 Live2D 的 ParamXxx） ----------------
   Live2D 里「一切都是参数」：动作、表情、物理、口型最后都只是在写同一张
   参数表，外部（脚本 / LLM / 口型驱动）也写同一张表。我们这边补的就是这层：
     - 内建参数（builtin）路由到已有子系统（视线 / 眨眼 / 头部跟随）；
     - 普通参数靠 binds 直接写组或部件的通道，rig.json 里声明，不改 C 代码。 */
enum { PBI_NONE = 0, PBI_ANGLE_X, PBI_ANGLE_Y, PBI_EYE_OPEN,
       PBI_EYEBALL_X, PBI_EYEBALL_Y };

typedef struct {
    int    part;              /* >=0 写部件通道 */
    int    group;             /* >=0 写组通道（part < 0 时才看） */
    int    param;             /* P_DX … P_BEND_Y */
    int    curve, strips;     /* bend_* 用 */
    double scale;             /* 通道值 = 参数值 × scale */
} zpbind;

/* 表情（Live2D 的 expression）：一组参数偏移，叠在当前动作之上，自带淡入淡出。
   和动作的区别 —— 表情不占用动作状态机，"笑着挥手"不需要再做一个新动作。 */
enum { EXPR_ADD = 0, EXPR_SET };

typedef struct {
    int    param;             /* 参数下标 */
    double value;
    int    mode;              /* EXPR_ADD / EXPR_SET */
} zexprp;

typedef struct {
    char   id[32];
    char   name[48];
    double fade;              /* 淡入淡出秒数 */
    int    p0, np;            /* 在 r->exprps 里的区间 */
} zexpr;

typedef struct {
    char   id[40];
    char   label[48];         /* 测试台显示用的中文名，可选 */
    double vmin, vmax, vdef;
    double value;
    int    builtin;           /* PBI_* */
    int    bind0, nbind;      /* 在 r->pbinds 里的区间 */
} zparam;

typedef struct {
    char id[48];
    int  rect[4];             /* x, y, w, h（画布坐标） */
    char action[48];
    char cursor[32];
} zregion;

/* 眨眼状态（对齐 Live2D CubismEyeBlink 的五态机） */
enum { BL_FIRST = 0, BL_INTERVAL, BL_CLOSING, BL_CLOSED, BL_OPENING };

struct zrig {
    char  id[96];
    char  name[192];
    char  dir[512];
    int   cw, ch;
    double origin[2];

    zgroup  groups[ZRIG_MAX_GROUPS];
    int     ngroups;

    zpart   parts[ZRIG_MAX_PARTS];
    int     nparts;
    int     order[ZRIG_MAX_PARTS];   /* 按 layer 升序的绘制顺序 */

    zaction actions[ZRIG_MAX_ACTIONS];
    int     nactions;

    zregion regions[ZRIG_MAX_REGIONS];
    int     nregions;

    zphys   phys[ZRIG_MAX_PHYS];
    int     nphys;
    double  phys_last;           /* 上一次积分的时刻，<0 = 还没开始 */

    zsm     sm;

    /* 动作淡入淡出（Live2D 的 motion fade）：切动作时两套通道按权重混合，
       否则每次切换都是一帧跳变 —— 挥手结束回 idle 时手会"啪"地弹回去。 */
    double  now;
    char    cur_id[48];          /* 上一帧看到的动作 id */
    double  cur_t0;              /* 当前动作的绝对起始时刻 */
    int     fade_prev;           /* 正在淡出的那个动作索引，-1 = 没有 */
    double  fade_prev_t0;        /* 它的绝对起始时刻（淡出期间它继续往前走） */
    double  fade_t0, fade_dur;   /* 淡入开始时刻 / 时长 */
    double  dim_now;             /* 混合后的压暗量 */

    /* 眨眼配置 */
    int    blink_enabled, blink_expo;
    double blink_closing, blink_closed, blink_opening;
    double blink_imin, blink_imax;
    int    blink_state;
    double blink_t0;
    double blink_gap;
    double blink_value;
    int    blink_forced;         /* -1 = 自动 */
    double blink_manual;         /* <0 = 自动；0..1 = 外部按住（测试台/调参用） */
    int    mouth_mute;           /* 口型同步接管嘴：动作里的嘴通道全部让路 */

    char  outfit[64];

    /* 帧缓冲 */
    zimg  *fb;
    zimg  *maskbuf;           /* 遮罩部件画在这里（只取它的 alpha） */
    int    maskbuf_part;      /* maskbuf 当前装的是哪个部件，-1 = 空 */
    zimg  *scratch;           /* 被裁切的部件先画在这里，再按遮罩合成到 fb */
    double fb_scale;
    int    fb_w, fb_h;

    /* 组变换（每帧计算） */
    double g_dx[ZRIG_MAX_GROUPS], g_dy[ZRIG_MAX_GROUPS];
    double g_sx[ZRIG_MAX_GROUPS], g_sy[ZRIG_MAX_GROUPS];
    double g_rot[ZRIG_MAX_GROUPS];

    /* 部件通道（每帧计算）：用于口型、眼部动画等 */
    double p_dx[ZRIG_MAX_PARTS], p_dy[ZRIG_MAX_PARTS];
    double p_bendx[ZRIG_MAX_PARTS], p_bendy[ZRIG_MAX_PARTS];   /* 形变位移（像素，画布坐标） */
    int    p_bendcx[ZRIG_MAX_PARTS], p_bendcy[ZRIG_MAX_PARTS]; /* 形变曲线：X 与 Y 各一条，互不覆盖 */
    int    p_bends[ZRIG_MAX_PARTS];                           /* 分段数 */
    double p_sx[ZRIG_MAX_PARTS], p_sy[ZRIG_MAX_PARTS];
    double p_rot[ZRIG_MAX_PARTS], p_alpha[ZRIG_MAX_PARTS];

    /* 视线跟随（幅度来自 rig.json 的 gaze 段） */
    double gaze_x, gaze_y;      /* [-1,1] 归一化方向 */
    double gaze_max_dx, gaze_max_dy;

    /* 命名参数层 */
    zparam  params[ZRIG_MAX_PARAMS];
    int     nparams;
    zpbind  pbinds[ZRIG_MAX_BINDS];
    int     npbinds;

    /* 表情层 */
    zexpr   exprs[ZRIG_MAX_EXPR];
    int     nexprs;
    zexprp  exprps[ZRIG_MAX_EXPR_SET];
    int     nexprps;
    int     expr_cur, expr_prev;   /* -1 = 无 */
    double  expr_t0, expr_fade;

    /* 渲染用的"最终值"：表情会往上叠，所以和子系统自己的值分开存 */
    double  blink_now;
    double  gaze_nx, gaze_ny;

    /* 头/身跟随指针 */
    zlook  looks[ZRIG_MAX_GROUPS];
    int    nlooks;
    double look_speed;          /* 追踪速度（1/s），越大越跟手 */
    double look_x, look_y;      /* 目标方向 [-1,1] */
    double look_cx, look_cy;    /* 平滑后的当前方向 */
    double look_last;           /* 上次平滑的时刻 */

    zrand  rng;
};

/* ============================================================ 小工具 */
static int parse_param(const char *name, int *out)
{
    if (z_streq(name, "dx")) { *out = P_DX; return 0; }
    if (z_streq(name, "dy")) { *out = P_DY; return 0; }
    if (z_streq(name, "sx")) { *out = P_SX; return 0; }
    if (z_streq(name, "sy")) { *out = P_SY; return 0; }
    if (z_streq(name, "rot_deg")) { *out = P_ROT; return 0; }
    if (z_streq(name, "alpha")) { *out = P_ALPHA; return 0; }
    if (z_streq(name, "bend_x")) { *out = P_BEND_X; return 0; }
    if (z_streq(name, "bend_y")) { *out = P_BEND_Y; return 0; }
    return -1;
}

static int parse_wave(const char *name, int *out)
{
    if (z_streq(name, "sine")) { *out = W_SINE; return 0; }
    if (z_streq(name, "bounce")) { *out = W_BOUNCE; return 0; }
    if (z_streq(name, "pulse")) { *out = W_PULSE; return 0; }
    if (z_streq(name, "decay")) { *out = W_DECAY; return 0; }
    if (z_streq(name, "flap")) { *out = W_FLAP; return 0; }
    return -1;
}

static unsigned parse_tags(const zjson *arr)
{
    unsigned t = 0;
    size_t i, n = zjson_count(arr);
    for (i = 0; i < n; ++i) {
        const char *s = zjson_str(zjson_at(arr, i), NULL);
        if (!s) continue;
        if (z_streq(s, "body")) t |= TAG_BODY;
        else if (z_streq(s, "head")) t |= TAG_HEAD;
        else if (z_streq(s, "eye_open")) t |= TAG_EYE_OPEN;
        else if (z_streq(s, "eye_closed")) t |= TAG_EYE_CLOSED;
        else if (z_streq(s, "mouth")) t |= TAG_MOUTH;
        else if (z_streq(s, "hair")) t |= TAG_HAIR;
        else if (z_streq(s, "accessory")) t |= TAG_ACCESSORY;
        else if (z_streq(s, "tail")) t |= TAG_TAIL;
        else if (z_streq(s, "gaze")) t |= TAG_GAZE;
        else if (z_streq(s, "eyelid")) t |= TAG_EYELID;
    }
    return t;
}

/* 读数组前两个数为二元点 */
static void read_pair(const zjson *arr, double def_x, double def_y, double out[2])
{
    out[0] = def_x;
    out[1] = def_y;
    if (arr && arr->type == ZJSON_ARR) {
        if (zjson_count(arr) > 0) out[0] = zjson_num(zjson_at(arr, 0), def_x);
        if (zjson_count(arr) > 1) out[1] = zjson_num(zjson_at(arr, 1), def_y);
    }
}

static int find_group(const zrig *r, const char *id)
{
    int i;
    for (i = 0; i < r->ngroups; ++i)
        if (strcmp(r->groups[i].id, id) == 0) return i;
    return -1;
}

static int find_part(const zrig *r, const char *id)
{
    int i;
    for (i = 0; i < r->nparts; ++i)
        if (strcmp(r->parts[i].id, id) == 0) return i;
    return -1;
}

static const zaction *current_action(const zrig *r)
{
    int idx = zsm_index(&r->sm, zsm_current_id(&r->sm));
    if (idx < 0 || idx >= r->nactions) return NULL;
    return &r->actions[idx];
}

/* ============================================================ 加载 */
static int load_groups(zrig *r, const zjson *jgroups, zdiag *d, const char *file)
{
    size_t i, n = zjson_count(jgroups);
    if (!jgroups || jgroups->type != ZJSON_OBJ) {
        zdiag_error(d, file, jgroups ? jgroups->line : 0, 0, "groups", "期望 object");
        return -1;
    }
    for (i = 0; i < n && r->ngroups < ZRIG_MAX_GROUPS; ++i) {
        const char *gid = zjson_key_at(jgroups, i);
        const zjson *gj = zjson_at(jgroups, i);
        zgroup *g = &r->groups[r->ngroups];
        char path[256];
        z_strlcpy(g->id, gid, sizeof(g->id));
        g->parent = -1;
        g->follow_part = -1;
        g->follow_id[0] = 0;
        g->follow_at = 0.0;
        {
            /* bend_follow：本组里的部件要跟着某个父部件一起弯（例：五官跟着身体摆）。
               部件此时还没加载，先记 id，load_parts 之后再解析。 */
            const char *bf = zjson_str(zjson_obj_get(gj, "bend_follow"), NULL);
            if (bf && *bf) z_strlcpy(g->follow_id, bf, sizeof(g->follow_id));
            /* bend_follow_at：关节点高度。头接在脖子上、手臂接在肩上——
               这类"整块挂在关节上"的部件要在关节处取样；
               不写就按部件自己的高度取样（适合贴在父部件上的五官）。 */
            if (zjson_get(gj, "bend_follow_at"))
                g->follow_at = zjson_num(zjson_obj_get(gj, "bend_follow_at"), 0.0);
        }
        z_snprintf(path, sizeof(path), "groups.%s.pivot", gid);
        read_pair(zjson_obj_get(gj, "pivot"), r->origin[0], r->origin[1], g->pivot);
        z_snprintf(path, sizeof(path), "groups.%s.parent", gid);
        {
            const char *p = zjson_str(zjson_obj_get(gj, "parent"), NULL);
            if (p && *p) {
                int pi = find_group(r, p);
                if (pi < 0) {
                    zdiag_error(d, file, gj ? gj->line : 0, 0, path,
                                "父组 '%s' 未定义（必须先定义父组）", p);
                    return -1;
                }
                g->parent = pi;
            }
        }
        r->ngroups++;
    }
    /* 循环引用检查 */
    {
        int gi;
        for (gi = 0; gi < r->ngroups; ++gi) {
            int depth = 0, p = r->groups[gi].parent;
            while (p >= 0) {
                if (++depth > ZRIG_MAX_GROUPS) {
                    zdiag_error(d, file, 0, 0, "groups", "组的父链出现循环引用（组 '%s'）",
                                r->groups[gi].id);
                    return -1;
                }
                p = r->groups[p].parent;
            }
        }
    }
    return 0;
}

static int load_parts(zrig *r, const zjson *jparts, zdiag *d, const char *file)
{
    size_t i, n = zjson_count(jparts);
    if (!jparts || jparts->type != ZJSON_ARR) {
        zdiag_error(d, file, jparts ? jparts->line : 0, 0, "parts", "期望 array");
        return -1;
    }
    if (n == 0) {
        zdiag_error(d, file, jparts->line, 0, "parts", "至少需要一个部件");
        return -1;
    }
    for (i = 0; i < n && r->nparts < ZRIG_MAX_PARTS; ++i) {
        const zjson *pj = zjson_at(jparts, i);
        zpart *p = &r->parts[r->nparts];
        char buf[512];


        memset(p, 0, sizeof(*p));
        p->group = -1;
        p->scale = 1.0;
        p->opacity = 1.0;
        z_snprintf(buf, sizeof(buf), "parts[%d]", (int)i);

        {
            const char *id = zjson_str(zjson_obj_get(pj, "id"), NULL);
            if (!id || !*id) {
                zdiag_error(d, file, pj ? pj->line : 0, 0, buf, "缺少部件 id");
                return -1;
            }
            z_strlcpy(p->id, id, sizeof(p->id));
        }
        {
            const char *f = zjson_str(zjson_obj_get(pj, "file"), NULL);
            if (!f || !*f) {
                zdiag_error(d, file, pj ? pj->line : 0, 0, buf, "缺少 file");
                return -1;
            }
            z_strlcpy(p->file, f, sizeof(p->file));
        }
        p->layer = (int)zjson_int(zjson_obj_get(pj, "layer"), 0);
        read_pair(zjson_obj_get(pj, "anchor"), 0.5, 0.5, p->anchor);
        read_pair(zjson_obj_get(pj, "pos"), r->origin[0], r->origin[1], p->pos);
        {
            /* scale 可以写成一个数（等比），也可以写成 [sx, sy]（分轴）。
               分轴是嘴开合这类动作的前提：嘴型要上下压扁而不是整体缩小。 */
            const zjson *sj = zjson_obj_get(pj, "scale");
            p->scale = 1.0;
            p->scale_x = p->scale_y = 1.0;
            if (zjson_is(sj, ZJSON_ARR)) {
                p->scale_x = zjson_num(zjson_at(sj, 0), 1.0);
                p->scale_y = zjson_num(zjson_at(sj, 1), 1.0);
            } else if (sj) {
                p->scale = zjson_num(sj, 1.0);
            }
        }
        p->rot_deg = zjson_num(zjson_obj_get(pj, "rot_deg"), 0.0);
        p->opacity = zjson_num(zjson_obj_get(pj, "opacity"), 1.0);
            /* 遮罩（Live2D 的 clipping mask 等价物）：本部件只在 mask 指向的那个
               部件的不透明区域内可见。眼球/高光/腮红这类"必须被眼眶或脸裁住"的
               部件靠它，否则眼球一动就滑出眼眶。
               约束：遮罩部件的 layer 必须更小（先画），加载时会校验。 */
            {
                const char *mk = zjson_str(zjson_obj_get(pj, "mask"), NULL);
                p->mask = -1;
                p->mask_id[0] = 0;
                p->is_mask_src = 0;
                if (mk && *mk) z_strlcpy(p->mask_id, mk, sizeof(p->mask_id));
                p->mask_only = zjson_bool(zjson_obj_get(pj, "mask_only"), 0);
            }
            /* motion_from：这个部件不自己接通道，照抄另一个部件的动作值。
               用来做"同一个零件画两遍"的场合 —— 典型就是透け眉（眉毛的半透明
               副本画在刘海之上），副本必须和本体分毫不差地一起动。 */
            {
                const char *mf = zjson_str(zjson_obj_get(pj, "motion_from"), NULL);
                p->motion_from = -1;
                p->motion_id[0] = 0;
                if (mf && *mf) z_strlcpy(p->motion_id, mf, sizeof(p->motion_id));
            }
        p->tags = parse_tags(zjson_obj_get(pj, "tags"));
        /* 眼睑行程：带 eyelid 标签的部件按 blink 参数下滑这么多像素。
           眨眼不再靠「睁眼图淡出 / 闭眼图淡入」，而是真的有一片眼皮盖下来。 */
        p->eyelid_travel = zjson_num(zjson_obj_get(pj, "eyelid_travel"), 0.0);
        {
            const char *gid = zjson_str(zjson_obj_get(pj, "group"), "root");
            p->group = find_group(r, gid);
            if (p->group < 0) {
                zdiag_error(d, file, pj ? pj->line : 0, 0, buf, "未知的组 '%s'", gid);
                return -1;
            }
        }
        {
            char full[1200];
            zerr e;
            zerr_clear(&e);
            z_resolve_path(full, sizeof(full), r->dir, p->file);
            if (!z_file_exists(full)) {
                zdiag_error(d, file, pj ? pj->line : 0, 0, buf,
                            "部件图片不存在：%s（相对基准目录 %s）", p->file, r->dir);
                return -1;
            }
            p->img = zimg_load(full, &e);
            if (!p->img) {
                zdiag_error(d, file, pj ? pj->line : 0, 0, buf,
                            "加载部件图片失败：%s（%s）", full, e.msg);
                return -1;
            }
        }
        r->nparts++;
    }
    return 0;
}

static void sort_parts(zrig *r)
{
    int i, j;
    for (i = 0; i < r->nparts; ++i) r->order[i] = i;
    for (i = 1; i < r->nparts; ++i) {   /* 稳定插入排序（按 layer） */
        int key = r->order[i];
        j = i - 1;
        while (j >= 0 && r->parts[r->order[j]].layer > r->parts[key].layer) {
            r->order[j + 1] = r->order[j];
            j--;
        }
        r->order[j + 1] = key;
    }
}

/* physics：弹簧摆配置。可选，没写就没有物理。
   { "id":"ahoge", "part":"hair_ahoge", "driver":"head", "axis":"x",
     "param":"bend_x", "curve":"root", "ratio":0.6,
     "stiffness":55, "damping":7, "max":9 } */
static int load_physics(zrig *r, const zjson *jp, zdiag *d, const char *file)
{
    size_t i, n = zjson_count(jp);
    if (!jp) return 0;
    if (jp->type != ZJSON_ARR) {
        zdiag_error(d, file, jp->line, 0, "physics", "期望 array");
        return -1;
    }
    for (i = 0; i < n && r->nphys < ZRIG_MAX_PHYS; ++i) {
        const zjson *pj = zjson_at(jp, i);
        zphys *ph = &r->phys[r->nphys];
        const char *pid = zjson_str(zjson_obj_get(pj, "part"), NULL);
        const char *drv = zjson_str(zjson_obj_get(pj, "driver"), NULL);
        const char *ax  = zjson_str(zjson_obj_get(pj, "axis"), "x");
        const char *pn  = zjson_str(zjson_obj_get(pj, "param"), "bend_x");
        const char *cv  = zjson_str(zjson_obj_get(pj, "curve"), "root");
        char path[128];
        memset(ph, 0, sizeof(*ph));
        z_strlcpy(ph->id, zjson_str(zjson_obj_get(pj, "id"), pid ? pid : "phys"), sizeof(ph->id));
        z_snprintf(path, sizeof(path), "physics[%s]", ph->id);
        ph->part = pid ? find_part(r, pid) : -1;
        if (ph->part < 0) {
            zdiag_error(d, file, pj ? pj->line : 0, 0, path,
                        "part '%s' 不存在", pid ? pid : "(缺)");
            return -1;
        }
        ph->driver = drv ? find_group(r, drv) : -1;
        if (ph->driver < 0) {
            zdiag_error(d, file, pj ? pj->line : 0, 0, path,
                        "driver 组 '%s' 不存在", drv ? drv : "(缺)");
            return -1;
        }
        ph->axis = (ax && (*ax == 'y' || *ax == 'Y')) ? 1 : 0;
        if (parse_param(pn, &ph->param) != 0) {
            zdiag_error(d, file, pj ? pj->line : 0, 0, path, "param 非法：%s", pn);
            return -1;
        }
        ph->curve = BEND_ROOT;
        if (z_streq(cv, "tip")) ph->curve = BEND_TIP;
        else if (z_streq(cv, "sine")) ph->curve = BEND_SINE;
        else if (z_streq(cv, "linear")) ph->curve = BEND_LINEAR;
        ph->ratio     = zjson_num(zjson_obj_get(pj, "ratio"), 0.6);
        ph->stiffness = zjson_num(zjson_obj_get(pj, "stiffness"), 55.0);
        ph->damping   = zjson_num(zjson_obj_get(pj, "damping"), 7.0);
        ph->max       = zjson_num(zjson_obj_get(pj, "max"), 10.0);
        if (ph->stiffness <= 0.0) ph->stiffness = 55.0;
        if (ph->damping < 0.0) ph->damping = 0.0;
        if (ph->max <= 0.0) ph->max = 10.0;
        r->nphys++;
    }
    return 0;
}

/* ---------------- 命名参数层 ----------------
   内建参数在 load 时固定注册（即使 rig.json 什么都不写也有一张可用的表），
   rig.json 的 "params" 段再往上加角色自己的参数：
   { "id":"ParamMouthOpenY", "label":"张嘴", "min":0, "max":1, "default":0,
     "binds":[ {"part":"mouth_mask","param":"sy","scale":0.737},
               {"part":"mouth_open","param":"alpha","scale":-0.5} ] } */
static int param_find(const zrig *r, const char *id)
{
    int i;
    if (!id) return -1;
    for (i = 0; i < r->nparams; ++i)
        if (z_streq(r->params[i].id, id)) return i;
    return -1;
}

/* Live2D 的左右眼分开，我们现在只有一个眨眼量 —— 收到 L/R 都映射到同一个。 */
static const char *param_alias(const char *id)
{
    if (z_streq(id, "ParamEyeLOpen") || z_streq(id, "ParamEyeROpen")) return "ParamEyeOpen";
    return id;
}

static void param_add_builtin(zrig *r, const char *id, const char *label,
                              double vmin, double vmax, double vdef, int kind)
{
    zparam *q;
    if (r->nparams >= ZRIG_MAX_PARAMS) return;
    q = &r->params[r->nparams++];
    memset(q, 0, sizeof(*q));
    z_strlcpy(q->id, id, sizeof(q->id));
    z_strlcpy(q->label, label, sizeof(q->label));
    q->vmin = vmin; q->vmax = vmax; q->vdef = vdef; q->value = vdef;
    q->builtin = kind;
    q->bind0 = r->npbinds;
    q->nbind = 0;
}

static void load_builtin_params(zrig *r)
{
    param_add_builtin(r, "ParamAngleX",   "头 左右", -30.0, 30.0, 0.0, PBI_ANGLE_X);
    param_add_builtin(r, "ParamAngleY",   "头 上下", -30.0, 30.0, 0.0, PBI_ANGLE_Y);
    param_add_builtin(r, "ParamEyeOpen",  "睁眼",     0.0,  1.0, 1.0, PBI_EYE_OPEN);
    param_add_builtin(r, "ParamEyeBallX", "眼球 左右", -1.0, 1.0, 0.0, PBI_EYEBALL_X);
    param_add_builtin(r, "ParamEyeBallY", "眼球 上下", -1.0, 1.0, 0.0, PBI_EYEBALL_Y);
}

static int load_params(zrig *r, const zjson *jp, zdiag *d, const char *file)
{
    size_t i, n = zjson_count(jp);
    if (!jp) return 0;
    if (jp->type != ZJSON_ARR) {
        zdiag_error(d, file, jp->line, 0, "params", "期望 array");
        return -1;
    }
    for (i = 0; i < n; ++i) {
        const zjson *qj = zjson_at(jp, i);
        const zjson *bs = zjson_obj_get(qj, "binds");
        const char *id = zjson_str(zjson_obj_get(qj, "id"), NULL);
        size_t k, nb = zjson_count(bs);
        char path[128];
        zparam *q;
        if (!id || !*id) {
            zdiag_error(d, file, qj ? qj->line : 0, 0, "params", "缺少参数 id");
            return -1;
        }
        z_snprintf(path, sizeof(path), "params[%s]", id);
        if (param_find(r, id) >= 0) {
            zdiag_error(d, file, qj ? qj->line : 0, 0, path, "参数 id 重复");
            return -1;
        }
        if (r->nparams >= ZRIG_MAX_PARAMS) {
            zdiag_error(d, file, qj ? qj->line : 0, 0, path,
                        "参数过多（上限 %d）", ZRIG_MAX_PARAMS);
            return -1;
        }
        q = &r->params[r->nparams++];
        memset(q, 0, sizeof(*q));
        z_strlcpy(q->id, id, sizeof(q->id));
        z_strlcpy(q->label, zjson_str(zjson_obj_get(qj, "label"), ""), sizeof(q->label));
        q->vmin = zjson_num(zjson_obj_get(qj, "min"), -1.0);
        q->vmax = zjson_num(zjson_obj_get(qj, "max"), 1.0);
        q->vdef = zjson_num(zjson_obj_get(qj, "default"), 0.0);
        if (q->vmax <= q->vmin) {
            zdiag_error(d, file, qj ? qj->line : 0, 0, path, "max 必须大于 min");
            return -1;
        }
        q->vdef = ZC_CLAMP(q->vdef, q->vmin, q->vmax);
        q->value = q->vdef;
        q->builtin = PBI_NONE;
        q->bind0 = r->npbinds;
        if (bs && bs->type != ZJSON_ARR) {
            zdiag_error(d, file, bs->line, 0, path, "binds 期望 array");
            return -1;
        }
        for (k = 0; k < nb; ++k) {
            const zjson *bj = zjson_at(bs, k);
            const char *pid = zjson_str(zjson_obj_get(bj, "part"), NULL);
            const char *gid = zjson_str(zjson_obj_get(bj, "group"), NULL);
            const char *pn  = zjson_str(zjson_obj_get(bj, "param"), NULL);
            const char *cv  = zjson_str(zjson_obj_get(bj, "curve"), "root");
            zpbind *b;
            if (r->npbinds >= ZRIG_MAX_BINDS) {
                zdiag_error(d, file, bj ? bj->line : 0, 0, path,
                            "绑定过多（上限 %d）", ZRIG_MAX_BINDS);
                return -1;
            }
            b = &r->pbinds[r->npbinds];
            memset(b, 0, sizeof(*b));
            b->part = pid ? find_part(r, pid) : -1;
            b->group = gid ? find_group(r, gid) : -1;
            if (pid && b->part < 0) {
                zdiag_error(d, file, bj ? bj->line : 0, 0, path, "part '%s' 不存在", pid);
                return -1;
            }
            if (gid && b->group < 0) {
                zdiag_error(d, file, bj ? bj->line : 0, 0, path, "组 '%s' 不存在", gid);
                return -1;
            }
            if (b->part < 0 && b->group < 0) {
                zdiag_error(d, file, bj ? bj->line : 0, 0, path, "binds 要写 part 或 group");
                return -1;
            }
            if (!pn || parse_param(pn, &b->param) != 0) {
                zdiag_error(d, file, bj ? bj->line : 0, 0, path,
                            "param 非法：%s", pn ? pn : "(缺)");
                return -1;
            }
            b->curve = BEND_ROOT;
            if (z_streq(cv, "tip")) b->curve = BEND_TIP;
            else if (z_streq(cv, "sine")) b->curve = BEND_SINE;
            else if (z_streq(cv, "linear")) b->curve = BEND_LINEAR;
            b->strips = (int)zjson_int(zjson_obj_get(bj, "strips"), 0);
            b->scale = zjson_num(zjson_obj_get(bj, "scale"), 1.0);
            r->npbinds++;
            q->nbind++;
        }
    }
    return 0;
}

/* expressions：一组参数偏移。
   { "id":"shy", "name":"害羞", "fade":0.3,
     "params":[ {"id":"ParamBrowLY","value":-0.5},
                {"id":"ParamEyeOpen","value":0.6,"mode":"set"} ] } */
static int load_expressions(zrig *r, const zjson *je, zdiag *d, const char *file)
{
    size_t i, n = zjson_count(je);
    if (!je) return 0;
    if (je->type != ZJSON_ARR) {
        zdiag_error(d, file, je->line, 0, "expressions", "期望 array");
        return -1;
    }
    for (i = 0; i < n; ++i) {
        const zjson *ej = zjson_at(je, i);
        const zjson *ps = zjson_obj_get(ej, "params");
        const char *id = zjson_str(zjson_obj_get(ej, "id"), NULL);
        size_t k, np = zjson_count(ps);
        char path[128];
        zexpr *e;
        if (!id || !*id) {
            zdiag_error(d, file, ej ? ej->line : 0, 0, "expressions", "缺少表情 id");
            return -1;
        }
        z_snprintf(path, sizeof(path), "expressions[%s]", id);
        if (r->nexprs >= ZRIG_MAX_EXPR) {
            zdiag_error(d, file, ej ? ej->line : 0, 0, path,
                        "表情过多（上限 %d）", ZRIG_MAX_EXPR);
            return -1;
        }
        e = &r->exprs[r->nexprs++];
        memset(e, 0, sizeof(*e));
        z_strlcpy(e->id, id, sizeof(e->id));
        z_strlcpy(e->name, zjson_str(zjson_obj_get(ej, "name"), id), sizeof(e->name));
        e->fade = zjson_num(zjson_obj_get(ej, "fade"), 0.25);
        if (e->fade < 0.0) e->fade = 0.0;
        if (e->fade > 2.0) e->fade = 2.0;
        e->p0 = r->nexprps;
        if (ps && ps->type != ZJSON_ARR) {
            zdiag_error(d, file, ps->line, 0, path, "params 期望 array");
            return -1;
        }
        for (k = 0; k < np; ++k) {
            const zjson *pj = zjson_at(ps, k);
            const char *pid = zjson_str(zjson_obj_get(pj, "id"), NULL);
            const char *md = zjson_str(zjson_obj_get(pj, "mode"), "add");
            zexprp *x;
            if (r->nexprps >= ZRIG_MAX_EXPR_SET) {
                zdiag_error(d, file, pj ? pj->line : 0, 0, path,
                            "表情参数过多（上限 %d）", ZRIG_MAX_EXPR_SET);
                return -1;
            }
            x = &r->exprps[r->nexprps];
            memset(x, 0, sizeof(*x));
            x->param = param_find(r, param_alias(pid));
            if (x->param < 0) {
                zdiag_error(d, file, pj ? pj->line : 0, 0, path,
                            "参数 '%s' 不存在（表情只能写 params 里声明过的参数）",
                            pid ? pid : "(缺)");
                return -1;
            }
            x->value = zjson_num(zjson_obj_get(pj, "value"), 0.0);
            x->mode = z_streq(md, "set") ? EXPR_SET : EXPR_ADD;
            r->nexprps++;
            e->np++;
        }
    }
    return 0;
}

/* 这一帧某个参数被表情改了多少（已含淡入淡出权重）。 */
static double expr_offset(const zrig *r, int pi)
{
    double w = 1.0, off = 0.0;
    int pass;
    if (r->expr_cur < 0 && r->expr_prev < 0) return 0.0;
    if (r->expr_fade > 1e-6) w = z_smoothstep(ZC_CLAMP((r->now - r->expr_t0) / r->expr_fade, 0.0, 1.0));
    for (pass = 0; pass < 2; ++pass) {
        int ei = pass ? r->expr_prev : r->expr_cur;
        double ww = pass ? (1.0 - w) : w;
        const zexpr *e;
        int k;
        if (ei < 0 || ei >= r->nexprs || ww <= 0.0) continue;
        e = &r->exprs[ei];
        for (k = 0; k < e->np; ++k) {
            const zexprp *x = &r->exprps[e->p0 + k];
            if (x->param != pi) continue;
            if (x->mode == EXPR_SET) off += ww * (x->value - r->params[pi].value);
            else                     off += ww * x->value;
        }
    }
    return off;
}

static int load_actions(zrig *r, const zjson *jacts, zdiag *d, const char *file)
{
    size_t i, n = zjson_count(jacts);
    zsm_state_def def;
    if (!jacts || jacts->type != ZJSON_ARR) {
        zdiag_error(d, file, jacts ? jacts->line : 0, 0, "actions", "期望 array");
        return -1;
    }
    for (i = 0; i < n && r->nactions < ZRIG_MAX_ACTIONS; ++i) {
        const zjson *aj = zjson_at(jacts, i);
        zaction *a = &r->actions[r->nactions];
        char buf[256];
        const char *id;
        memset(a, 0, sizeof(*a));
        a->duration = -1;
        a->loop = 1;
        a->interruptible = 1;

        id = zjson_str(zjson_obj_get(aj, "id"), NULL);
        if (!id || !*id) {
            zdiag_error(d, file, aj ? aj->line : 0, 0, "actions", "缺少动作 id");
            return -1;
        }
        z_strlcpy(a->id, id, sizeof(a->id));
        z_snprintf(buf, sizeof(buf), "actions[%s]", id);

        a->priority = (int)zjson_int(zjson_obj_get(aj, "priority"), 0);
        /* 默认不循环：只有写了 "loop": true 的动作才循环（否则 head_pat/happy 等永远不回 idle） */
        a->loop = zjson_bool(zjson_obj_get(aj, "loop"), 0);
        a->interruptible = zjson_bool(zjson_obj_get(aj, "interruptible"), 1);
        a->dim = zjson_num(zjson_obj_get(aj, "dim"), 0.0);
        /* blink_hold：动作期间把眼睛按住在某个闭合度（眯眼笑 0.55、睡着 1.0）。
           眼皮拆成零件之后，表情不用再换一张「闭眼图」，压参数就行。 */
        a->blink_hold = zjson_num(zjson_obj_get(aj, "blink_hold"), -1.0);
        /* fade：从上一个动作淡入到这个动作要多久。0 = 立刻切（锤子这种打击感要的就是硬切）。
           默认 0.22s —— 比 Live2D 默认的 0.5s 短，桌宠的反馈要更跟手。 */
        a->fade = zjson_num(zjson_obj_get(aj, "fade"), 0.22);
        if (a->fade < 0.0) a->fade = 0.0;
        if (a->fade > 2.0) a->fade = 2.0;
        a->duration = zjson_num(zjson_obj_get(aj, "duration"), a->loop ? -1.0 : 1.0);
        if (a->loop) a->duration = -1.0;
        {
            const char *rs = zjson_str(zjson_obj_get(aj, "return_state"), "idle");
            z_strlcpy(a->return_state, rs, sizeof(a->return_state));
        }
        /* 通道 */
        {
            const zjson *chs = zjson_obj_get(aj, "channels");
            size_t k, kn = zjson_count(chs);
            for (k = 0; k < kn && a->nchan < ZRIG_MAX_CHANNELS; ++k) {
                const zjson *cj = zjson_at(chs, k);
                zchan *c = &a->chans[a->nchan];
                const char *tgt = zjson_str(zjson_obj_get(cj, "target"), "root");
                const char *pname = zjson_str(zjson_obj_get(cj, "param"), NULL);
                const char *wname = zjson_str(zjson_obj_get(cj, "wave"), "sine");
                memset(c, 0, sizeof(*c));
                z_strlcpy(c->target, tgt, sizeof(c->target));
                c->group = -1;
                c->part = -1;
                c->group = find_group(r, tgt);
                if (c->group < 0) {
                    /* 允许直接指向部件（口型/眼部动画） */
                    c->part = find_part(r, tgt);
                    if (c->part < 0) {
                        zdiag_error(d, file, cj ? cj->line : 0, 0, buf,
                                    "通道 target '%s' 既不是组也不是部件（检查 groups / parts 里的 id）", tgt);
                        return -1;
                    }
                }
                {
                    const char *cname = zjson_str(zjson_obj_get(cj, "curve"), NULL);
                    if (cname) {
                        if (z_streq(cname, "root")) c->curve = BEND_ROOT;
                        else if (z_streq(cname, "sine")) c->curve = BEND_SINE;
                        else if (z_streq(cname, "linear")) c->curve = BEND_LINEAR;
                        else if (z_streq(cname, "tip")) c->curve = BEND_TIP;
                    }
                    if (zjson_get(cj, "strips")) c->strips = (int)zjson_num(zjson_obj_get(cj, "strips"), 0);
                }
                if (!pname || parse_param(pname, &c->param) != 0) {
                    zdiag_error(d, file, cj ? cj->line : 0, 0, buf,
                                "通道 param 非法（允许 dx/dy/sx/sy/rot_deg/alpha/bend_x/bend_y）");
                    return -1;
                }
                if (parse_wave(wname, &c->wave) != 0) {
                    zdiag_error(d, file, cj ? cj->line : 0, 0, buf,
                                "通道 wave 非法（允许 sine/bounce/pulse/decay）");
                    return -1;
                }
                c->amp = zjson_num(zjson_obj_get(cj, "amp"), 0.0);
                c->freq = zjson_num(zjson_obj_get(cj, "freq"), 1.0);
                c->phase = zjson_num(zjson_obj_get(cj, "phase"), 0.0);
                c->dur = zjson_num(zjson_obj_get(cj, "dur"), a->duration > 0 ? a->duration : 1.0);
                c->ease = z_ease_from_name(zjson_str(zjson_obj_get(cj, "ease"), "out"));
                a->nchan++;
            }
        }
        /* 部件覆盖 */
        {
            const zjson *ovs = zjson_obj_get(aj, "part_overrides");
            size_t k, kn = zjson_count(ovs);
            for (k = 0; k < kn && a->novr < ZRIG_MAX_OVERRIDES; ++k) {
                const char *pid = zjson_key_at(ovs, k);
                const zjson *oj = zjson_at(ovs, k);
                zoverride *o = &a->ovr[a->novr];
                memset(o, 0, sizeof(*o));
                z_strlcpy(o->part, pid, sizeof(o->part));
                if (find_part(r, pid) < 0) {
                    zdiag_error(d, file, oj ? oj->line : 0, 0, buf,
                                "part_overrides 引用了不存在的部件 '%s'", pid);
                    return -1;
                }
                if (zjson_obj_get(oj, "opacity")) { o->opacity = zjson_num(zjson_obj_get(oj, "opacity"), 1.0); }
                else o->opacity = 1.0;
                if (zjson_obj_get(oj, "dx")) { o->has_dx = 1; o->dx = zjson_num(zjson_obj_get(oj, "dx"), 0.0); }
                if (zjson_obj_get(oj, "dy")) { o->has_dy = 1; o->dy = zjson_num(zjson_obj_get(oj, "dy"), 0.0); }
                a->novr++;
            }
        }
        r->nactions++;

        /* 同步到状态机 */
        memset(&def, 0, sizeof(def));
        z_strlcpy(def.id, a->id, sizeof(def.id));
        def.priority = a->priority;
        def.duration_s = a->duration;
        def.interruptible = a->interruptible;
        def.loop = a->loop;
        z_strlcpy(def.return_state, a->return_state, sizeof(def.return_state));
        if (zsm_add_state(&r->sm, &def) < 0) {
            zdiag_error(d, file, aj ? aj->line : 0, 0, buf, "动作 id 重复或状态数超限");
            return -1;
        }
    }
    if (zsm_index(&r->sm, "idle") < 0) {
        zdiag_error(d, file, 0, 0, "actions", "必须定义 id 为 \"idle\" 的动作");
        return -1;
    }
    return 0;
}

static int load_regions(zrig *r, const zjson *jreg, zdiag *d, const char *file)
{
    size_t i, n = zjson_count(jreg);
    for (i = 0; i < n && r->nregions < ZRIG_MAX_REGIONS; ++i) {
        const zjson *rj = zjson_at(jreg, i);
        zregion *g = &r->regions[r->nregions];
        const char *id = zjson_str(zjson_obj_get(rj, "id"), NULL);
        const char *act = zjson_str(zjson_obj_get(rj, "action"), NULL);
        const zjson *rect = zjson_obj_get(rj, "rect");
        char buf[128];
        if (!id || !act) {
            zdiag_error(d, file, rj ? rj->line : 0, 0, "regions", "缺少 id 或 action");
            return -1;
        }
        if (!rect || zjson_count(rect) != 4) {
            zdiag_error(d, file, rj ? rj->line : 0, 0, "regions", "rect 必须是 [x,y,w,h]");
            return -1;
        }
        if (zsm_index(&r->sm, act) < 0) {
            zdiag_error(d, file, rj->line, 0, "regions", "区域 '%s' 指向未定义的动作 '%s'", id, act);
            return -1;
        }
        memset(g, 0, sizeof(*g));
        z_strlcpy(g->id, id, sizeof(g->id));
        z_strlcpy(g->action, act, sizeof(g->action));
        z_strlcpy(g->cursor, zjson_str(zjson_obj_get(rj, "cursor"), "hand"), sizeof(g->cursor));
        g->rect[0] = (int)zjson_num(zjson_at(rect, 0), 0);
        g->rect[1] = (int)zjson_num(zjson_at(rect, 1), 0);
        g->rect[2] = (int)zjson_num(zjson_at(rect, 2), 0);
        g->rect[3] = (int)zjson_num(zjson_at(rect, 3), 0);
        z_snprintf(buf, sizeof(buf), "regions[%s]", id);
        r->nregions++;
    }
    return 0;
}

zrig *zrig_load(const char *rig_path, const char *base_dir, zdiag *diag)
{
    zerr err;
    zjson *root;
    zrig *r;
    const char *file = rig_path;

    zerr_clear(&err);
    root = zjson_parse_file(rig_path, &err);
    if (!root) {
        zdiag_error(diag, file, err.line, err.col, "", "解析失败：%s", err.msg);
        return NULL;
    }
    r = (zrig *)z_calloc(1, sizeof(zrig));
    z_strlcpy(r->dir, base_dir ? base_dir : "", sizeof(r->dir));
    zrand_seed(&r->rng, 0x5EED1234ull);
    zsm_init(&r->sm);
    r->blink_state = BL_FIRST;
    r->blink_forced = -1;
    r->blink_manual = -1.0;
    r->blink_imin = 2.0;
    r->blink_imax = 8.0;

    z_strlcpy(r->id, zjson_str(zjson_obj_get(root, "id"), z_basename(base_dir ? base_dir : "rig")),
              sizeof(r->id));
    z_strlcpy(r->name, zjson_str(zjson_obj_get(root, "name"), r->id), sizeof(r->name));

    {
        const zjson *cv = zjson_obj_get(root, "canvas");
        r->cw = (int)zjson_int(zjson_obj_get(cv, "w"), 848);
        r->ch = (int)zjson_int(zjson_obj_get(cv, "h"), 1360);
        if (r->cw < 64 || r->cw > 8192 || r->ch < 64 || r->ch > 8192) {
            zdiag_error(diag, file, cv ? cv->line : 0, 0, "canvas", "画布尺寸不合理：%dx%d",
                        r->cw, r->ch);
            zjson_free(root);
            zrig_free(r);
            return NULL;
        }
    }
    read_pair(zjson_obj_get(root, "origin"), r->cw * 0.5, r->ch * 1.0, r->origin);
    if (find_group(r, "root") < 0 && r->ngroups < ZRIG_MAX_GROUPS) {
        /* 自动补一个 root 组（多数角色包不需要显式写） */
        zgroup *g = &r->groups[r->ngroups++];
        memset(g, 0, sizeof(*g));
        z_strlcpy(g->id, "root", sizeof(g->id));
        g->pivot[0] = r->origin[0];
        g->pivot[1] = r->origin[1];
        g->parent = -1;
    }
    if (load_groups(r, zjson_obj_get(root, "groups"), diag, file) != 0) goto fail;
    if (load_parts(r, zjson_obj_get(root, "parts"), diag, file) != 0) goto fail;
    /* 解析 bend_follow（必须在部件加载之后） */
    {
        int gi;
        for (gi = 0; gi < r->ngroups; ++gi) {
            zgroup *g = &r->groups[gi];
            if (!g->follow_id[0]) continue;
            g->follow_part = find_part(r, g->follow_id);
            if (g->follow_part < 0) {
                char path[160];
                z_snprintf(path, sizeof(path), "groups.%s.bend_follow", g->id);
                zdiag_error(diag, file, 0, 0, path,
                            "bend_follow 指向的部件 '%s' 不存在", g->follow_id);
                goto fail;
            }
        }
    }
    sort_parts(r);
    /* 解析 motion_from 引用 */
    {
        int i;
        for (i = 0; i < r->nparts; ++i) {
            zpart *p = &r->parts[i];
            if (!p->motion_id[0]) continue;
            p->motion_from = find_part(r, p->motion_id);
            if (p->motion_from < 0 || p->motion_from == i) {
                char path[160];
                z_snprintf(path, sizeof(path), "parts.%s.motion_from", p->id);
                zdiag_error(diag, file, 0, 0, path,
                            "motion_from 指向的部件 '%s' %s", p->motion_id,
                            (p->motion_from == i) ? "不能是自己" : "不存在");
                goto fail;
            }
            if (r->parts[p->motion_from].motion_id[0]) {
                char path[160];
                z_snprintf(path, sizeof(path), "parts.%s.motion_from", p->id);
                zdiag_error(diag, file, 0, 0, path,
                            "motion_from 不能套娃（'%s' 自己也在抄别人）", p->motion_id);
                goto fail;
            }
        }
    }
    /* 解析遮罩引用（必须在 sort_parts 之后：要按最终绘制顺序校验先后） */
    {
        int i;
        for (i = 0; i < r->nparts; ++i) {
            zpart *p = &r->parts[i];
            if (!p->mask_id[0]) continue;
            p->mask = find_part(r, p->mask_id);
            if (p->mask < 0) {
                char path[160];
                z_snprintf(path, sizeof(path), "parts.%s.mask", p->id);
                zdiag_error(diag, file, 0, 0, path,
                            "mask 指向的部件 '%s' 不存在", p->mask_id);
                goto fail;
            }
            if (p->mask == i) {
                char path[160];
                z_snprintf(path, sizeof(path), "parts.%s.mask", p->id);
                zdiag_error(diag, file, 0, 0, path, "mask 不能指向自己");
                goto fail;
            }
            if (r->parts[p->mask].layer >= p->layer) {
                char path[160];
                z_snprintf(path, sizeof(path), "parts.%s.mask", p->id);
                zdiag_error(diag, file, 0, 0, path,
                            "遮罩部件 '%s' 的 layer(%d) 必须小于被裁切部件的 layer(%d)，"
                            "否则遮罩还没画出来就要用它裁切",
                            p->mask_id, r->parts[p->mask].layer, p->layer);
                goto fail;
            }
            r->parts[p->mask].is_mask_src = 1;
        }
        /* 画一个遮罩只用一块缓冲：遮罩与被裁切部件之间不能插进另一个遮罩源，
           否则缓冲被覆盖。这里按最终绘制顺序检查，不合规直接报错而不是悄悄画错。 */
        for (i = 0; i < r->nparts; ++i) {
            zpart *p = &r->parts[i];
            int k, pos_self = -1, pos_mask = -1;
            if (p->mask < 0) continue;
            for (k = 0; k < r->nparts; ++k) {
                if (r->order[k] == i) pos_self = k;
                if (r->order[k] == p->mask) pos_mask = k;
            }
            for (k = pos_mask + 1; k < pos_self; ++k) {
                if (r->parts[r->order[k]].is_mask_src) {
                    char path[160];
                    z_snprintf(path, sizeof(path), "parts.%s.mask", p->id);
                    zdiag_error(diag, file, 0, 0, path,
                                "遮罩 '%s' 与本部件之间夹着另一个遮罩源 '%s'，"
                                "请调整 layer 让每组遮罩相邻",
                                p->mask_id, r->parts[r->order[k]].id);
                    goto fail;
                }
            }
        }
    }
    if (load_actions(r, zjson_obj_get(root, "actions"), diag, file) != 0) goto fail;
    if (load_regions(r, zjson_obj_get(root, "regions"), diag, file) != 0) goto fail;
    if (load_physics(r, zjson_obj_get(root, "physics"), diag, file) != 0) goto fail;
    load_builtin_params(r);
    if (load_params(r, zjson_obj_get(root, "params"), diag, file) != 0) goto fail;
    if (load_expressions(r, zjson_obj_get(root, "expressions"), diag, file) != 0) goto fail;

    /* 眨眼 */
    {
        const zjson *bj = zjson_obj_get(root, "blink");
        if (bj) {
            r->blink_enabled = zjson_bool(zjson_obj_get(bj, "enabled"), 1);
            r->blink_closing = zjson_num(zjson_obj_get(bj, "closing_s"), 0.1);
            r->blink_closed = zjson_num(zjson_obj_get(bj, "closed_s"), 0.05);
            r->blink_opening = zjson_num(zjson_obj_get(bj, "opening_s"), 0.15);
            r->blink_imin = zjson_num(zjson_obj_get(bj, "interval_min_s"), 2.0);
            r->blink_imax = zjson_num(zjson_obj_get(bj, "interval_max_s"), 8.0);
            r->blink_expo = zjson_bool(zjson_obj_get(bj, "interval_exponential"), 0);
        } else {
            r->blink_enabled = 0;   /* 没有配置就不眨眼（避免素材未拆件时出错） */
        }
        if (r->blink_imax < r->blink_imin) r->blink_imax = r->blink_imin;
    }

    /* 视线跟随 */
    {
        const zjson *gj = zjson_obj_get(root, "gaze");
        double pair[2];
        r->gaze_x = r->gaze_y = 0.0;
        read_pair(zjson_obj_get(gj, "max_offset"), 0.0, 0.0, pair);
        r->gaze_max_dx = pair[0];
        r->gaze_max_dy = pair[1];
    }

    /* 指针跟随：
       "look": { "speed": 9,
                 "groups": { "head": {"rot_deg":5,"dx":4,"dy":3},
                             "chest": {"dx":1.5,"rot_deg":1} } } */
    r->look_speed = 9.0;
    {
        const zjson *lj = zjson_obj_get(root, "look");
        if (lj) {
            const zjson *gs = zjson_obj_get(lj, "groups");
            size_t i, n = zjson_count(gs);
            r->look_speed = zjson_num(zjson_obj_get(lj, "speed"), 9.0);
            if (r->look_speed <= 0.0) r->look_speed = 9.0;
            for (i = 0; i < n && r->nlooks < ZRIG_MAX_GROUPS; ++i) {
                const char *gid = zjson_key_at(gs, i);
                const zjson *ej = zjson_at(gs, i);
                int gi = gid ? find_group(r, gid) : -1;
                if (gi < 0) {
                    zdiag_error(diag, file, ej ? ej->line : 0, 0, "look.groups",
                                "组 '%s' 不存在", gid ? gid : "(空)");
                    goto fail;
                }
                r->looks[r->nlooks].group = gi;
                r->looks[r->nlooks].rot = zjson_num(zjson_obj_get(ej, "rot_deg"), 0.0);
                r->looks[r->nlooks].dx  = zjson_num(zjson_obj_get(ej, "dx"), 0.0);
                r->looks[r->nlooks].dy  = zjson_num(zjson_obj_get(ej, "dy"), 0.0);
                r->nlooks++;
            }
        }
    }

    r->fade_prev = -1;
    r->expr_cur = r->expr_prev = -1;
    r->phys_last = -1.0;
    r->look_last = -1.0;
    r->cur_id[0] = 0;
    zsm_start(&r->sm, "idle", 0.0);
    zjson_free(root);
    return r;

fail:
    zjson_free(root);
    zrig_free(r);
    return NULL;
}

void zrig_free(zrig *r)
{
    int i;
    if (!r) return;
    for (i = 0; i < r->nparts; ++i) {
        zimg_free(r->parts[i].img);
        zimg_free(r->parts[i].img_scaled);
    }
    zimg_free(r->fb);
    zimg_free(r->maskbuf);
    zimg_free(r->scratch);
    free(r);
}

/* ============================================================ 信息 */
const char *zrig_id(const zrig *r) { return r ? r->id : ""; }
const char *zrig_name(const zrig *r) { return r ? r->name : ""; }
int zrig_canvas_w(const zrig *r) { return r ? r->cw : 0; }
int zrig_canvas_h(const zrig *r) { return r ? r->ch : 0; }
int zrig_part_count(const zrig *r) { return r ? r->nparts : 0; }
int zrig_action_count(const zrig *r) { return r ? r->nactions : 0; }
int zrig_region_count(const zrig *r) { return r ? r->nregions : 0; }

const char *zrig_part_id(const zrig *r, int i)
{
    if (!r || i < 0 || i >= r->nparts) return "";
    return r->parts[i].id;
}

const char *zrig_action_id_at(const zrig *r, int i)
{
    if (!r || i < 0 || i >= r->nactions) return "";
    return r->actions[i].id;
}

void zrig_describe(const zrig *r, char *out, size_t cap)
{
    if (!r) { z_strlcpy(out, "(null)", cap); return; }
    z_snprintf(out, cap, "rig %s(%s) 画布 %dx%d 部件 %d 组 %d 动作 %d 区域 %d 当前动作 %s",
               r->id, r->name, r->cw, r->ch, r->nparts, r->ngroups,
               r->nactions, r->nregions, zsm_current_id(&r->sm));
}

/* ============================================================ 通道求值 */
static double eval_channel(const zchan *c, double t, double total)
{
    switch (c->wave) {
        case W_SINE:
            return c->amp * sin(2.0 * 3.14159265358979323846 * (c->freq * t + c->phase));
        case W_BOUNCE: {
            /* 一次“抬起-回落”弧线：用于跳动、拍打 */
            double d = c->dur > 0 ? c->dur : 1.0;
            double u = ZC_CLAMP(t / d, 0.0, 1.0);
            return c->amp * sin(3.14159265358979323846 * z_ease_apply(c->ease, u));
        }
        case W_PULSE: {
            /* 快速进入并保持（用于前倾、下沉、表情维持） */
            double d = c->dur > 0 ? c->dur : 0.2;
            double u = ZC_CLAMP(t / d, 0.0, 1.0);
            double k = z_ease_apply(c->ease, u);
            if (total > 0 && t > total - 0.15) {   /* 结束前回零，避免突跳 */
                double back = ZC_CLAMP((t - (total - 0.15)) / 0.15, 0.0, 1.0);
                k *= (1.0 - z_smoothstep(back));
            }
            return c->amp * k;
        }
        case W_FLAP: {
            /* 只往一个方向摆的余弦：0 → amp → 0 循环。
               嘴的开合必须用它——用 sine 会摆到负数，缩放成负值就是把嘴翻过来画。 */
            return c->amp * (0.5 - 0.5 * cos(2.0 * 3.14159265358979323846 * c->freq * t));
        }
        case W_DECAY:
        default: {
            /* 阻尼振荡：被打/被锤后的抖动 */
            double d = c->dur > 0 ? c->dur : 1.0;
            double k = exp(-6.0 * t / d);
            return c->amp * k * sin(2.0 * 3.14159265358979323846 * c->freq * t);
        }
    }
}

/* 把一个动作在时刻 t 的所有通道按权重 w 累加进当前帧的变换数组。
   w < 1 时就是"淡入淡出"里的那一份权重，两个动作各累加一次即可。 */
/* 把一个数值写进「部件或组的某条通道」。动作、物理、参数层共用同一套语义：
   位移/旋转/形变是累加，alpha 是相乘（0.5 两次 = 0.25），缩放累加在基准 1.0 上。 */
static void apply_chan(zrig *r, int part, int group, int param,
                       double v, int curve, int strips)
{
    if (part >= 0 && part < r->nparts) {
        switch (param) {
            case P_DX:  r->p_dx[part] += v; break;
            case P_DY:  r->p_dy[part] += v; break;
            case P_SX:  r->p_sx[part] += v; break;
            case P_SY:  r->p_sy[part] += v; break;
            case P_ROT: r->p_rot[part] += v; break;
            case P_ALPHA: r->p_alpha[part] *= ZC_CLAMP(1.0 + v, 0.0, 1.0); break;
            case P_BEND_X:
                r->p_bendx[part] += v;
                r->p_bendcx[part] = curve;
                if (strips > 0) r->p_bends[part] = strips;
                break;
            case P_BEND_Y:
                r->p_bendy[part] += v;
                r->p_bendcy[part] = curve;
                if (strips > 0) r->p_bends[part] = strips;
                break;
        }
        return;
    }
    if (group < 0 || group >= r->ngroups) return;
    switch (param) {
        case P_DX:  r->g_dx[group] += v; break;
        case P_DY:  r->g_dy[group] += v; break;
        case P_SX:  r->g_sx[group] += v; break;
        case P_SY:  r->g_sy[group] += v; break;
        case P_ROT: r->g_rot[group] += v; break;
        case P_ALPHA: break;   /* 组级 alpha 未使用（部件级用 p_alpha） */
        default: break;
    }
}

static void accumulate_action(zrig *r, const zaction *a, double t, double w, double total)
{
    int i;
    if (!a || w <= 0.0) return;
    for (i = 0; i < a->nchan; ++i) {
        const zchan *c = &a->chans[i];
        double v;
        /* 口型同步接管时，动作里的嘴通道一律让路：
           否则 talk 的 flap 和包络会叠在一起，嘴越张越大（sy 超过素材高度就是拉伸）。 */
        if (r->mouth_mute && c->part >= 0 && c->part < r->nparts &&
            (r->parts[c->part].tags & TAG_MOUTH)) continue;
        v = eval_channel(c, t, total) * w;
        apply_chan(r, c->part, c->group, c->param, v, c->curve, c->strips);
    }
}

static void compute_group_transforms(zrig *r)
{
    const zaction *a = current_action(r);
    const zaction *prev = (r->fade_prev >= 0 && r->fade_prev < r->nactions)
                          ? &r->actions[r->fade_prev] : NULL;
    double w = 1.0;
    int i;
    for (i = 0; i < r->ngroups; ++i) {
        r->g_dx[i] = r->g_dy[i] = 0.0;
        r->g_sx[i] = r->g_sy[i] = 1.0;
        r->g_rot[i] = 0.0;
    }
    for (i = 0; i < r->nparts; ++i) {
        r->p_dx[i] = r->p_dy[i] = 0.0;
        r->p_bendx[i] = r->p_bendy[i] = 0.0;
        r->p_bendcx[i] = r->p_bendcy[i] = BEND_ROOT;
        r->p_bends[i] = 0;
        r->p_sx[i] = r->p_sy[i] = 1.0;
        r->p_rot[i] = 0.0;
        r->p_alpha[i] = 1.0;
    }
    if (!a) { r->dim_now = 0.0; return; }
    if (prev && r->fade_dur > 1e-6) {
        double u = ZC_CLAMP((r->now - r->fade_t0) / r->fade_dur, 0.0, 1.0);
        w = z_smoothstep(u);                 /* 两头平滑，中间快 */
        if (u >= 1.0) { r->fade_prev = -1; prev = NULL; w = 1.0; }
    } else {
        prev = NULL;
    }
    if (prev) {
        /* 淡出的那个动作继续往前走（Live2D 也是这么做的，不然会卡在最后一帧） */
        double tp = r->now - r->fade_prev_t0;
        double totp = prev->loop ? -1.0 : prev->duration;
        accumulate_action(r, prev, tp, 1.0 - w, totp);
    }
    accumulate_action(r, a, zsm_elapsed(&r->sm), w, a->loop ? -1.0 : a->duration);
    r->dim_now = prev ? (prev->dim * (1.0 - w) + a->dim * w) : a->dim;

    /* 命名参数层 + 表情层：都叠在动作之上。
       内建参数（跟随/眨眼/眼球）走各自的子系统，其余按 binds 写通道。 */
    {
        double lx = r->look_cx, ly = r->look_cy;
        r->blink_now = r->blink_value;
        r->gaze_nx = r->gaze_x;
        r->gaze_ny = r->gaze_y;
        for (i = 0; i < r->nparams; ++i) {
            const zparam *q = &r->params[i];
            double off = expr_offset(r, i);
            double v = q->value + off;
            int k;
            switch (q->builtin) {
                case PBI_ANGLE_X:   lx += off / 30.0; continue;
                case PBI_ANGLE_Y:   ly -= off / 30.0; continue;
                case PBI_EYE_OPEN:  r->blink_now = ZC_CLAMP(r->blink_now - off, 0.0, 1.0); continue;
                case PBI_EYEBALL_X: r->gaze_nx = ZC_CLAMP(r->gaze_nx + off, -1.0, 1.0); continue;
                case PBI_EYEBALL_Y: r->gaze_ny = ZC_CLAMP(r->gaze_ny + off, -1.0, 1.0); continue;
                default: break;
            }
            if (q->nbind <= 0 || fabs(v) < 1e-9) continue;
            for (k = 0; k < q->nbind; ++k) {
                const zpbind *b = &r->pbinds[q->bind0 + k];
                apply_chan(r, b->part, b->group, b->param,
                           v * b->scale, b->curve, b->strips);
            }
        }
        /* 指针跟随叠加在动作之上（Live2D 里这是参数层，不属于任何一个 motion）。
           放在动作之后、物理之前：所以转头也会把头发甩起来。 */
        for (i = 0; i < r->nlooks; ++i) {
            const zlook *lk = &r->looks[i];
            if (lk->group < 0 || lk->group >= r->ngroups) continue;
            r->g_rot[lk->group] += lk->rot * lx;
            r->g_dx[lk->group]  += lk->dx  * lx;
            r->g_dy[lk->group]  += lk->dy  * ly;
        }
    }
}

/* 内建参数的"读数"每帧回写一次：测试台的滑条上能直接看见自动眨眼在动。 */
static void params_refresh_builtin(zrig *r)
{
    int i;
    for (i = 0; i < r->nparams; ++i) {
        zparam *q = &r->params[i];
        switch (q->builtin) {
            case PBI_ANGLE_X:   q->value = r->look_cx * 30.0; break;
            case PBI_ANGLE_Y:   q->value = -r->look_cy * 30.0; break;
            case PBI_EYE_OPEN:  q->value = 1.0 - r->blink_value; break;
            case PBI_EYEBALL_X: q->value = r->gaze_x; break;
            case PBI_EYEBALL_Y: q->value = r->gaze_y; break;
            default: break;
        }
    }
}

static void group_matrix(const zrig *r, int gi, double scale, double m[6]);

/* 驱动输入：拿部件自己的锚点，经过驱动组（含父链）的完整矩阵变换一次，
   位移 = 变换后 − 原位。这样**旋转**也能带动头发（头一歪，呆毛就该甩），
   不是只看 dx/dy —— 实测这个角色的动作里绝大多数头部运动都是 rot_deg。 */
static void physics_input(const zrig *r, const zphys *ph, double *out_x, double *out_y)
{
    double m[6], x0, y0;
    const zpart *p = &r->parts[ph->part];
    *out_x = *out_y = 0.0;
    if (ph->driver < 0) return;
    x0 = p->pos[0];
    y0 = p->pos[1];
    group_matrix(r, ph->driver, 1.0, m);
    *out_x = (m[0] * x0 + m[2] * y0 + m[4]) - x0;
    *out_y = (m[1] * x0 + m[3] * y0 + m[5]) - y0;
}

/* 物理摆动积分：必须在 compute_group_transforms 之后跑，
   因为它的输入就是这一帧算出来的驱动组位移。 */
static void physics_update(zrig *r, double now)
{
    double dt;
    int i;
    if (r->nphys <= 0) return;
    if (r->phys_last < 0.0) { r->phys_last = now; return; }
    dt = now - r->phys_last;
    r->phys_last = now;
    if (dt <= 0.0) return;
    if (dt > 0.1) dt = 0.1;              /* 掉帧时别让积分炸掉 */
    for (i = 0; i < r->nphys; ++i) {
        zphys *ph = &r->phys[i];
        double in, target, acc, out;
        if (ph->part < 0 || ph->driver < 0) continue;
        {
            double ix, iy;
            physics_input(r, ph, &ix, &iy);
            in = (ph->axis == 1) ? iy : ix;
        }
        target = in * ph->ratio;
        acc = ph->stiffness * (target - ph->pos) - ph->damping * ph->vel;
        ph->vel += acc * dt;
        ph->pos += ph->vel * dt;
        /* 输出 = 摆尖相对驱动位置的落后量：静止时 pos→target，输出归零，
           所以它只加"惯性"，不会把头发永久吹偏。 */
        out = ZC_CLAMP(ph->pos - target, -ph->max, ph->max);
        switch (ph->param) {
            case P_DX: r->p_dx[ph->part] += out; break;
            case P_DY: r->p_dy[ph->part] += out; break;
            case P_ROT: r->p_rot[ph->part] += out; break;
            case P_BEND_Y: r->p_bendy[ph->part] += out; r->p_bendcy[ph->part] = ph->curve; break;
            case P_BEND_X:
            default: r->p_bendx[ph->part] += out; r->p_bendcx[ph->part] = ph->curve; break;
        }
    }
}

/* 求组的完整矩阵（含父链） */
/* 子组跟随父部件的形变：把组的枢轴换算到被跟随部件的源图纵坐标，取同一条曲线的权重，
   得到"这一高度上部件被推了多远"，组就跟着推多远。
   这样素材一换（部件高度/位置变了），跟随量自动变，不用在 rig.json 里手算系数。 */
static void bend_follow_abs(const zrig *r, int fp, double pivot_y,
                            double *out_dx, double *out_dy)
{
    const zpart *p;
    double h_canvas, top_canvas, t;
    *out_dx = *out_dy = 0.0;
    if (fp < 0) return;
    p = &r->parts[fp];
    if (!p->img || p->img->h <= 0 || p->scale <= 0.0) return;
    if (fabs(r->p_bendx[fp]) < 1e-6 && fabs(r->p_bendy[fp]) < 1e-6) return;
    h_canvas   = (double)p->img->h * p->scale;        /* 部件在画布上的高度 */
    top_canvas = p->pos[1] - p->anchor[1] * h_canvas; /* 部件顶边的画布纵坐标 */
    t = (pivot_y - top_canvas) / h_canvas;            /* 0=部件顶边 1=部件底边 */
    *out_dx = r->p_bendx[fp] * zimg_bend_factor(t, r->p_bendcx[fp]);
    *out_dy = r->p_bendy[fp] * zimg_bend_factor(t, r->p_bendcy[fp]);
}

/* 部件级跟随：部件所在的组（或祖先组）声明了 bend_follow 时，
   这个部件就按**它自己所在的高度**取父部件的形变位移。
   比"整组按枢轴平移"更接近 Live2D 的逐顶点形变：眼睛取眼睛那一行、嘴取嘴那一行，
   所以五官不会随着身体弯曲程度的变化而在脸上滑移。 */
static void part_follow_offset(const zrig *r, int pi, double *out_dx, double *out_dy)
{
    const zpart *p = &r->parts[pi];
    int gi;
    *out_dx = *out_dy = 0.0;
    for (gi = p->group; gi >= 0; gi = r->groups[gi].parent) {
        int fp = r->groups[gi].follow_part;
        if (fp < 0) continue;
        if (fp == pi) return;                 /* 自己就是形变源，不跟随自己 */
        bend_follow_abs(r, fp,
                        r->groups[gi].follow_at > 0.0 ? r->groups[gi].follow_at : p->pos[1],
                        out_dx, out_dy);
        return;                               /* 只认最近的一层，避免重复叠加 */
    }
}

/* 组矩阵。scale 是画布→帧的缩放：枢轴与位移都要换算到帧坐标，
   否则旋转会绕错点（缩放 0.55 时枢轴会偏出近一倍距离）。 */
static void group_matrix(const zrig *r, int gi, double scale, double m[6])
{
    const zgroup *g = &r->groups[gi];
    double local[6];
    double px = g->pivot[0] * scale, py = g->pivot[1] * scale;
    zimg_make_matrix(local,
                     px + r->g_dx[gi] * scale,
                     py + r->g_dy[gi] * scale,
                     r->g_sx[gi], r->g_sy[gi], r->g_rot[gi], px, py);
    if (g->parent >= 0) {
        double pm[6];
        group_matrix(r, g->parent, scale, pm);
        zimg_matrix_mul(m, pm, local);
    } else {
        memcpy(m, local, sizeof(local));
    }
}

/* 只读查询：组的实际位移（通道 + 自动跟随），画布像素 */
static double group_offset(const zrig *r, const char *group_id, int want_y)
{
    int gi;
    double sum = 0.0;
    if (!r || !group_id) return 0.0;
    gi = find_group(r, group_id);
    if (gi < 0) return 0.0;
    /* 组矩阵是父子相乘的，所以实际位移 = 本组 + 所有祖先组的位移之和 */
    for (; gi >= 0; gi = r->groups[gi].parent)
        sum += want_y ? r->g_dy[gi] : r->g_dx[gi];
    return sum;
}

double zrig_part_offset_x(const zrig *r, const char *part_id)
{
    int pi;
    double fdx = 0.0, fdy = 0.0;
    if (!r || !part_id) return 0.0;
    pi = find_part(r, part_id);
    if (pi < 0) return 0.0;
    part_follow_offset(r, pi, &fdx, &fdy);
    (void)fdy;
    return r->p_dx[pi] + fdx + group_offset(r, r->parts[pi].group >= 0 ?
                                            r->groups[r->parts[pi].group].id : "", 0);
}

double zrig_part_pos_y(const zrig *r, const char *part_id)
{
    int pi;
    if (!r || !part_id) return 0.0;
    pi = find_part(r, part_id);
    return pi < 0 ? 0.0 : r->parts[pi].pos[1];
}

double zrig_part_follow_y(const zrig *r, const char *part_id)
{
    int pi, gi;
    if (!r || !part_id) return 0.0;
    pi = find_part(r, part_id);
    if (pi < 0) return 0.0;
    gi = r->parts[pi].group;
    if (gi >= 0 && r->groups[gi].follow_at > 0.0) return r->groups[gi].follow_at;
    return r->parts[pi].pos[1];
}

const char *zrig_part_follow_src(const zrig *r, const char *part_id)
{
    int pi, gi;
    if (!r || !part_id) return NULL;
    pi = find_part(r, part_id);
    if (pi < 0) return NULL;
    gi = r->parts[pi].group;
    if (gi < 0 || r->groups[gi].follow_part < 0) return NULL;
    return r->parts[r->groups[gi].follow_part].id;
}

double zrig_group_offset_x(const zrig *r, const char *group_id) { return group_offset(r, group_id, 0); }
double zrig_group_offset_y(const zrig *r, const char *group_id) { return group_offset(r, group_id, 1); }

double zrig_bend_at(const zrig *r, const char *part_id, double canvas_y)
{
    int pi;
    double dx = 0.0, dy = 0.0;
    if (!r || !part_id) return 0.0;
    pi = find_part(r, part_id);
    if (pi < 0) return 0.0;
    bend_follow_abs(r, pi, canvas_y, &dx, &dy);
    (void)dy;
    return dx;
}

/* ============================================================ 眨眼 */
static double blink_update(zrig *r, double now)
{
    if (r->blink_manual >= 0.0) {       /* 外部按住：测试台拖滑条时用 */
        r->blink_value = ZC_CLAMP(r->blink_manual, 0.0, 1.0);
        return r->blink_value;
    }
    if (!r->blink_enabled || r->blink_forced == 1) {
        r->blink_value = (r->blink_forced == 1) ? 1.0 : 0.0;
        return r->blink_value;
    }
    if (r->blink_t0 <= 0.0) {
        r->blink_t0 = now;
        r->blink_gap = zrand_range(&r->rng, r->blink_imin, r->blink_imax);
    }
    {
        double dt = now - r->blink_t0;
        switch (r->blink_state) {
            case BL_FIRST:
            case BL_INTERVAL:
                r->blink_value = 0.0;
                if (dt >= r->blink_gap) {
                    r->blink_state = BL_CLOSING;
                    r->blink_t0 = now;
                }
                break;
            case BL_CLOSING:
                r->blink_value = ZC_CLAMP(dt / ZC_MAX(r->blink_closing, 1e-3), 0.0, 1.0);
                if (r->blink_value >= 1.0) { r->blink_state = BL_CLOSED; r->blink_t0 = now; }
                break;
            case BL_CLOSED:
                r->blink_value = 1.0;
                if (dt >= r->blink_closed) { r->blink_state = BL_OPENING; r->blink_t0 = now; }
                break;
            case BL_OPENING:
                r->blink_value = 1.0 - ZC_CLAMP(dt / ZC_MAX(r->blink_opening, 1e-3), 0.0, 1.0);
                if (r->blink_value <= 0.0) {
                    r->blink_state = BL_INTERVAL;
                    r->blink_t0 = now;
                    r->blink_gap = r->blink_expo
                        ? zrand_expo(&r->rng, (r->blink_imin + r->blink_imax) * 0.5)
                        : zrand_range(&r->rng, r->blink_imin, r->blink_imax);
                }
                break;
            default: r->blink_value = 0.0; break;
        }
    }
    {
        /* 动作要求的闭合度只抬不压：眯着眼笑的时候照样能眨一下眼。 */
        const zaction *a = current_action(r);
        if (a && a->blink_hold >= 0.0 && a->blink_hold > r->blink_value)
            r->blink_value = a->blink_hold;
    }
    return r->blink_value;
}

void zrig_set_mouth_mute(zrig *r, int on) { if (r) r->mouth_mute = on ? 1 : 0; }
int  zrig_mouth_mute(const zrig *r) { return r ? r->mouth_mute : 0; }

void zrig_blink_set_enabled(zrig *r, int enabled) { if (r) r->blink_enabled = enabled; }
int  zrig_blink_enabled(const zrig *r) { return r ? r->blink_enabled : 0; }
double zrig_blink_value(const zrig *r) { return r ? r->blink_value : 0.0; }

void zrig_blink_set_manual(zrig *r, double v)
{
    if (r) r->blink_manual = (v < 0.0) ? -1.0 : ZC_CLAMP(v, 0.0, 1.0);
}

double zrig_blink_manual(const zrig *r) { return r ? r->blink_manual : -1.0; }

void zrig_blink_force(zrig *r, int force_closed)
{
    if (!r) return;
    r->blink_forced = force_closed ? 1 : -1;
}

void zrig_blink_trigger(zrig *r)
{
    if (!r) return;
    r->blink_forced = -1;
    r->blink_state = BL_CLOSING;
    r->blink_t0 = r->sm.now;
}

/* ============================================================ 每帧 */
void zrig_tick(zrig *r, double now)
{
    const char *cur;
    double entered;
    if (!r) return;
    r->now = now;
    zsm_update(&r->sm, now);

    /* 动作换了没有？换了就把旧动作挂到"正在淡出"那一路上。
       重播同一个动作（连击 force）不算切换，不淡入，要的就是那一下干脆。 */
    cur = zsm_current_id(&r->sm);
    entered = now - zsm_elapsed(&r->sm);
    if (cur && strcmp(cur, r->cur_id) != 0) {
        int newi = zsm_index(&r->sm, cur);
        if (r->cur_id[0]) {
            int previ = zsm_index(&r->sm, r->cur_id);
            if (previ >= 0 && previ < r->nactions) {
                r->fade_prev = previ;
                r->fade_prev_t0 = r->cur_t0;
                r->fade_t0 = now;
                r->fade_dur = (newi >= 0 && newi < r->nactions) ? r->actions[newi].fade : 0.22;
                if (r->fade_dur <= 1e-6) r->fade_prev = -1;
            }
        }
        z_strlcpy(r->cur_id, cur, sizeof(r->cur_id));
    }
    r->cur_t0 = entered;

    /* 指针跟随要平滑，否则鼠标一跳头就瞬移 */
    {
        double dt = (r->look_last < 0.0) ? 0.0 : now - r->look_last;
        double k;
        r->look_last = now;
        if (dt < 0.0) dt = 0.0;
        if (dt > 0.25) dt = 0.25;
        k = 1.0 - exp(-r->look_speed * dt);
        r->look_cx += (r->look_x - r->look_cx) * k;
        r->look_cy += (r->look_y - r->look_cy) * k;
    }

    blink_update(r, now);
    params_refresh_builtin(r);
    compute_group_transforms(r);
    physics_update(r, now);
}

static int ensure_scaled(zrig *r, double scale)
{
    int i;
    for (i = 0; i < r->nparts; ++i) {
        zpart *p = &r->parts[i];
        int nw = (int)(p->img->w * scale + 0.5);
        int nh = (int)(p->img->h * scale + 0.5);
        if (nw < 1) nw = 1;
        if (nh < 1) nh = 1;
        if (p->img_scaled && p->img_scaled->w == nw && p->img_scaled->h == nh) continue;
        zimg_free(p->img_scaled);
        p->img_scaled = (fabs(scale - 1.0) < 1e-6) ? zimg_clone(p->img) : zimg_resize(p->img, nw, nh);
    }
    return 0;
}

const zimg *zrig_frame(zrig *r, double scale, int *out_w, int *out_h)
{
    const zaction *a;
    int i, fw, fh;
    if (!r) return NULL;
    if (scale < 0.1) scale = 0.1;
    if (scale > 4.0) scale = 4.0;

    fw = (int)(r->cw * scale + 0.5);
    fh = (int)(r->ch * scale + 0.5);
    if (fw < 1) fw = 1;
    if (fh < 1) fh = 1;

    if (fabs(scale - r->fb_scale) > 1e-6) {
        ensure_scaled(r, scale);
        zimg_free(r->fb);
        r->fb = zimg_new(fw, fh);
        zimg_free(r->maskbuf); r->maskbuf = NULL;
        zimg_free(r->scratch); r->scratch = NULL;
        r->fb_scale = scale;
        r->fb_w = fw;
        r->fb_h = fh;
    } else if (!r->fb || r->fb->w != fw || r->fb->h != fh) {
        zimg_free(r->fb);
        r->fb = zimg_new(fw, fh);
        zimg_free(r->maskbuf); r->maskbuf = NULL;
        zimg_free(r->scratch); r->scratch = NULL;
        r->fb_w = fw;
        r->fb_h = fh;
    }
    if (!r->fb) return NULL;
    zimg_clear(r->fb);
    r->maskbuf_part = -1;       /* 新的一帧：遮罩缓冲作废 */

    a = current_action(r);
    {
        double blink = r->blink_now;      /* 表情叠加后的最终闭合度 */
        for (i = 0; i < r->nparts; ++i) {
            int pi = r->order[i];
            zpart *p = &r->parts[pi];
            /* motion_from：通道值照抄别的部件（透け眉这类"同一零件画两遍"用）。
               位置、遮罩、透明度仍然是自己的。 */
            int mi = (p->motion_from >= 0) ? p->motion_from : pi;
            double opacity = p->opacity * r->p_alpha[mi];
            double extra_dx = r->p_dx[mi], extra_dy = r->p_dy[mi];
            double part_rot = r->p_rot[mi];
            double part_sx = 1.0, part_sy = 1.0;
            double gm[6], lm[6], m[6];
            const zimg *src = p->img_scaled ? p->img_scaled : p->img;
            /* 视线跟随：只影响带 gaze 标签的部件（虹膜拆分后自动升级为真·视线） */
            if ((p->tags & TAG_GAZE) && (r->gaze_nx != 0.0 || r->gaze_ny != 0.0)) {
                extra_dx += r->gaze_nx * r->gaze_max_dx;
                extra_dy += r->gaze_ny * r->gaze_max_dy;
            }
            /* 眼睑：眨眼参数直接变成往下滑的位移。
               眼皮本身是从眼睛上方那块皮肤切出来的，静止时被眼眶遮罩挡住看不见，
               blink=1 时正好滑满整个眼眶 —— 这才是 Live2D 里眼睛的做法。 */
            if (p->tags & TAG_EYELID) extra_dy += blink * p->eyelid_travel;
            /* 跟随父部件的形变（五官跟着身体弯） */
            {
                double fdx = 0.0, fdy = 0.0;
                part_follow_offset(r, mi, &fdx, &fdy);
                extra_dx += fdx;
                extra_dy += fdy;
            }
            /* 部件通道里的缩放：取平均作用到等比缩放上 */
            /* 通道里的 sx/sy 相对基准做加法（基准为 1 时与过去的乘法完全一致），
               这样 "scale":[1,0.06] + sy 通道 0.8 → 实际 0.86，rig 里读起来就是它的意思 */
            part_sx = p->scale_x + (r->p_sx[mi] - 1.0);
            part_sy = p->scale_y + (r->p_sy[mi] - 1.0);
            if (part_sx < 0.0) part_sx = 0.0;
            if (part_sy < 0.0) part_sy = 0.0;

            /* 动作对部件的覆盖 */
            if (a) {
                int k;
                for (k = 0; k < a->novr; ++k) {
                    if (strcmp(a->ovr[k].part, p->id) == 0) {
                        opacity *= a->ovr[k].opacity;
                        if (a->ovr[k].has_dx) extra_dx += a->ovr[k].dx;
                        if (a->ovr[k].has_dy) extra_dy += a->ovr[k].dy;
                    }
                }
            }
            /* 眨眼：睁眼部件与闭眼部件按参数交叉淡化 */
            if (r->blink_enabled && blink > 0.001) {
                if (p->tags & TAG_EYE_OPEN)   opacity *= (1.0 - blink);
                if (p->tags & TAG_EYE_CLOSED) opacity *= blink;
            }
            if (opacity <= 0.001) continue;
            if ((p->tags & TAG_EYE_CLOSED) && blink <= 0.001) continue;
            if ((p->tags & TAG_EYE_OPEN) && blink >= 0.999) continue;

            /* 部件矩阵（画布缩放 + 锚点 + 自身旋转） */
            {
                double anchor_px = src->w * p->anchor[0];
                double anchor_py = src->h * p->anchor[1];
                double pos_x = (p->pos[0] + extra_dx) * scale;
                double pos_y = (p->pos[1] + extra_dy) * scale;
                zimg_make_matrix(lm, pos_x, pos_y, p->scale * part_sx, p->scale * part_sy,
                                 p->rot_deg + part_rot, anchor_px, anchor_py);
            }
            if (p->group >= 0) {
                group_matrix(r, p->group, scale, gm);
                zimg_matrix_mul(m, gm, lm);
            } else {
                memcpy(m, lm, sizeof(lm));
            }
            {
                double bx = r->p_bendx[mi] * scale, by = r->p_bendy[mi] * scale;
                int warped = (fabs(bx) > 0.05 || fabs(by) > 0.05);
                zimg *target = r->fb;

                /* 有人拿我当遮罩：我要额外画一份到 maskbuf（只用它的 alpha）。
                   mask_only 的部件只进 maskbuf，不出现在画面上。 */
                if (p->is_mask_src) {
                    if (!r->maskbuf) r->maskbuf = zimg_new(r->fb->w, r->fb->h);
                    if (r->maskbuf) {
                        zimg_clear(r->maskbuf);
                        r->maskbuf_part = pi;
                        if (warped)
                            zimg_draw_warp(r->maskbuf, src, m, 1.0,
                                           bx, r->p_bendcx[mi], by, r->p_bendcy[mi]);
                        else
                            zimg_draw(r->maskbuf, src, m, 1.0);
                    }
                    if (p->mask_only) continue;
                }
                /* 我被别人裁切：先画到 scratch，再按遮罩 alpha 合成过去 */
                if (p->mask >= 0) {
                    /* 遮罩自己没画出来（例如眨眼时眼眶被隐藏）= 遮罩全透明 = 我也看不见，
                       与 Live2D 的 clipping 语义一致 */
                    if (r->maskbuf_part != p->mask) continue;
                    if (!r->scratch) r->scratch = zimg_new(r->fb->w, r->fb->h);
                    if (r->scratch) { zimg_clear(r->scratch); target = r->scratch; }
                }
                if (warped)
                    zimg_draw_warp(target, src, m, opacity,
                                   bx, r->p_bendcx[mi], by, r->p_bendcy[mi]);
                else
                    zimg_draw(target, src, m, opacity);
                if (target != r->fb)
                    zimg_composite_masked(r->fb, r->scratch, r->maskbuf);
            }
        }
    }

    /* 状态压暗（睡眠等） */
    if (r->dim_now > 0.001) {
        size_t n = (size_t)r->fb->w * r->fb->h, k;
        double dim = ZC_CLAMP(r->dim_now, 0.0, 1.0);
        double f = 1.0 - 0.45 * dim;
        for (k = 0; k < n; ++k) {
            uint8_t *q = r->fb->px + k * 4;
            q[0] = (uint8_t)ZC_CLAMP(q[0] * f, 0, 255);
            q[1] = (uint8_t)ZC_CLAMP(q[1] * f, 0, 255);
            q[2] = (uint8_t)ZC_CLAMP(q[2] * (1.0 - 0.25 * dim), 0, 255);
        }
    }

    if (out_w) *out_w = r->fb->w;
    if (out_h) *out_h = r->fb->h;
    return r->fb;
}

/* ============================================================ 交互 */
int zrig_hit_test(const zrig *r, int x, int y, int threshold)
{
    if (!r || !r->fb) return 0;
    return zimg_hit_test(r->fb, x, y, threshold);
}

/* 坐标契约：x、y 使用**画布坐标**（与 rig.json 的 regions 一致）。
 * 帧缓冲是缩放后的，这里按比例换算后再做像素命中检查。 */
const char *zrig_region_at(const zrig *r, int x, int y, char *out_action, size_t cap)
{
    int i;
    if (!r) return NULL;
    for (i = 0; i < r->nregions; ++i) {
        const zregion *g = &r->regions[i];
        if (x >= g->rect[0] && y >= g->rect[1] &&
            x < g->rect[0] + g->rect[2] && y < g->rect[1] + g->rect[3]) {
            /* 区域必须落在不透明像素上，避免透明角落也响应 */
            if (r->fb && r->cw > 0 && r->ch > 0) {
                int fx = (int)((long)x * r->fb->w / r->cw);
                int fy = (int)((long)y * r->fb->h / r->ch);
                if (!zimg_hit_test(r->fb, fx, fy, 16)) continue;
            }
            if (out_action) z_strlcpy(out_action, g->action, cap);
            return g->id;
        }
    }
    return NULL;
}

/* 把帧缓冲坐标换算为画布坐标（平台层用） */
void zrig_frame_to_canvas(const zrig *r, int fx, int fy, int *cx, int *cy)
{
    if (!r) return;
    if (cx) *cx = (r->fb && r->fb->w > 0) ? (int)((long)fx * r->cw / r->fb->w) : fx;
    if (cy) *cy = (r->fb && r->fb->h > 0) ? (int)((long)fy * r->ch / r->fb->h) : fy;
}

const char *zrig_region_cursor(const zrig *r, const char *region_id)
{
    int i;
    if (!r || !region_id) return "arrow";
    for (i = 0; i < r->nregions; ++i)
        if (strcmp(r->regions[i].id, region_id) == 0) return r->regions[i].cursor;
    return "arrow";
}

/* ============================================================ 动作 */
int zrig_action_request(zrig *r, const char *id, const char *reason, int force)
{
    if (!r) return 0;
    return zsm_request(&r->sm, id, reason, force);
}

const char *zrig_action(const zrig *r) { return r ? zsm_current_id(&r->sm) : ""; }
int zrig_action_priority(const zrig *r) { return r ? zsm_current_priority(&r->sm) : 0; }
double zrig_action_elapsed(const zrig *r) { return r ? zsm_elapsed(&r->sm) : 0.0; }
const char *zrig_action_last_reason(const zrig *r)
{
    return r ? r->sm.last.reason : "";
}

/* ============================================================ 换装 */
const char *zrig_outfit(const zrig *r) { return r ? r->outfit : ""; }

int zrig_reload_parts(zrig *r, zdiag *diag)
{
    int i;
    if (!r) return -1;
    for (i = 0; i < r->nparts; ++i) {
        zpart *p = &r->parts[i];
        char full[1200];
        zerr e;
        zerr_clear(&e);
        z_resolve_path(full, sizeof(full), r->dir, p->file);
        if (!z_file_exists(full)) {
            zdiag_error(diag, r->dir, 0, 0, p->id, "素材文件丢失：%s", p->file);
            return -1;
        }
        {
            zimg *im = zimg_load(full, &e);
            if (!im) {
                zdiag_error(diag, r->dir, 0, 0, p->id, "重新加载失败：%s", e.msg);
                return -1;
            }
            zimg_free(p->img);
            p->img = im;
            zimg_free(p->img_scaled);
            p->img_scaled = NULL;
        }
    }
    /* 让帧缓冲下一帧重建缩放缓存 */
    r->fb_scale = -1.0;
    return 0;
}

int zrig_apply_outfit(zrig *r, const char *outfit_json_path, zdiag *diag)
{
    zerr err;
    zjson *root;
    const zjson *parts;
    const char *file = outfit_json_path;
    size_t i, n;
    int applied = 0, failed = 0;

    if (!r) return -1;
    if (!outfit_json_path || !z_file_exists(outfit_json_path)) {
        zdiag_error(diag, file ? file : "(outfit)", 0, 0, "outfit", "服装包文件不存在");
        return -1;
    }
    zerr_clear(&err);
    root = zjson_parse_file(outfit_json_path, &err);
    if (!root) {
        zdiag_error(diag, file, err.line, err.col, "", "服装包解析失败：%s", err.msg);
        return -1;
    }
    parts = zjson_obj_get(root, "parts");
    if (!parts || parts->type != ZJSON_OBJ) {
        zdiag_error(diag, file, root->line, 0, "parts", "服装包缺少 parts 对象");
        zjson_free(root);
        return -1;
    }
    n = zjson_count(parts);
    for (i = 0; i < n; ++i) {
        const char *pid = zjson_key_at(parts, i);
        const zjson *ov = zjson_at(parts, i);
        int pi = find_part(r, pid);
        char buf[160];
        z_snprintf(buf, sizeof(buf), "parts.%s", pid);
        if (pi < 0) {
            zdiag_error(diag, file, ov ? ov->line : 0, 0, buf, "部件 '%s' 不在本形态中", pid);
            failed++;
            continue;
        }
        {
            const char *f = zjson_str(zjson_obj_get(ov, "file"), NULL);
            zpart *p = &r->parts[pi];
            if (f && *f) {
                char full[1200];
                zerr e2;
                zimg *im;
                zerr_clear(&e2);
                z_resolve_path(full, sizeof(full), r->dir, f);
                if (!z_file_exists(full)) {
                    zdiag_error(diag, file, ov ? ov->line : 0, 0, buf, "服装素材不存在：%s", f);
                    failed++;
                    continue;
                }
                im = zimg_load(full, &e2);
                if (!im) {
                    zdiag_error(diag, file, ov ? ov->line : 0, 0, buf, "服装素材解码失败：%s", e2.msg);
                    failed++;
                    continue;
                }
                z_strlcpy(p->file, f, sizeof(p->file));
                zimg_free(p->img);
                p->img = im;
                zimg_free(p->img_scaled);
                p->img_scaled = NULL;
                applied++;
            }
            if (zjson_obj_get(ov, "pos")) {
                double xy[2];
                read_pair(zjson_obj_get(ov, "pos"), p->pos[0], p->pos[1], xy);
                p->pos[0] = xy[0]; p->pos[1] = xy[1];
            }
            if (zjson_obj_get(ov, "scale"))
                p->scale = zjson_num(zjson_obj_get(ov, "scale"), p->scale);
            if (zjson_obj_get(ov, "layer"))
                p->layer = (int)zjson_int(zjson_obj_get(ov, "layer"), p->layer);
        }
    }
    z_strlcpy(r->outfit, zjson_str(zjson_obj_get(root, "id"), z_basename(outfit_json_path)),
              sizeof(r->outfit));
    zjson_free(root);
    if (applied > 0) {
        sort_parts(r);
        r->fb_scale = -1.0;
        ZLOGI("rig", "已应用服装 %s（覆盖 %d 个部件）", r->outfit, applied);
    }
    return failed ? -1 : 0;
}

/* ============================================================ 视线 */
void zrig_gaze(zrig *r, double nx, double ny)
{
    if (!r) return;
    r->gaze_x = ZC_CLAMP(nx, -1.0, 1.0);
    r->gaze_y = ZC_CLAMP(ny, -1.0, 1.0);
    /* 眼睛看过去，头也跟着转一点点 —— Live2D 的光标跟随就是这两层一起动。
       幅度写在 rig.json 的 look 段里，没写就只有眼睛动。 */
    zrig_look(r, nx, ny);
}

void zrig_gaze_reset(zrig *r)
{
    if (!r) return;
    r->gaze_x = r->gaze_y = 0.0;
    zrig_look(r, 0.0, 0.0);
}

void zrig_look(zrig *r, double nx, double ny)
{
    if (!r) return;
    r->look_x = ZC_CLAMP(nx, -1.0, 1.0);
    r->look_y = ZC_CLAMP(ny, -1.0, 1.0);
}

double zrig_look_x(const zrig *r) { return r ? r->look_cx : 0.0; }
double zrig_look_y(const zrig *r) { return r ? r->look_cy : 0.0; }

/* ------------------------------------------------------------- 表情层 */
int zrig_expression_count(const zrig *r) { return r ? r->nexprs : 0; }

const char *zrig_expression_id(const zrig *r, int i)
{
    if (!r || i < 0 || i >= r->nexprs) return NULL;
    return r->exprs[i].id;
}

const char *zrig_expression_name(const zrig *r, int i)
{
    if (!r || i < 0 || i >= r->nexprs) return NULL;
    return r->exprs[i].name;
}

const char *zrig_expression(const zrig *r)
{
    if (!r || r->expr_cur < 0) return NULL;
    return r->exprs[r->expr_cur].id;
}

int zrig_expression_set(zrig *r, const char *id)
{
    int i, next = -1;
    if (!r) return -1;
    if (id && *id) {
        for (i = 0; i < r->nexprs; ++i)
            if (z_streq(r->exprs[i].id, id)) { next = i; break; }
        if (next < 0) return -1;              /* 没有这个表情：报错，别悄悄忽略 */
    }
    if (next == r->expr_cur) return 0;
    r->expr_prev = r->expr_cur;
    r->expr_cur = next;
    r->expr_t0 = r->now;
    /* 淡入用新表情的 fade；切回"无表情"时用旧表情的 fade 淡出 */
    r->expr_fade = (next >= 0) ? r->exprs[next].fade
                 : (r->expr_prev >= 0 ? r->exprs[r->expr_prev].fade : 0.0);
    return 0;
}

void zrig_expression_clear(zrig *r) { (void)zrig_expression_set(r, NULL); }

double zrig_expression_weight(const zrig *r)
{
    if (!r || (r->expr_cur < 0 && r->expr_prev < 0)) return 0.0;
    if (r->expr_fade <= 1e-6) return r->expr_cur >= 0 ? 1.0 : 0.0;
    {
        double w = z_smoothstep(ZC_CLAMP((r->now - r->expr_t0) / r->expr_fade, 0.0, 1.0));
        return r->expr_cur >= 0 ? w : 1.0 - w;
    }
}

/* ------------------------------------------------- 命名参数层（外部驱动） */
int zrig_param_count(const zrig *r) { return r ? r->nparams : 0; }

const char *zrig_param_id(const zrig *r, int i)
{
    if (!r || i < 0 || i >= r->nparams) return NULL;
    return r->params[i].id;
}

int zrig_param_info(const zrig *r, int i, zrig_param_desc *out)
{
    const zparam *q;
    if (!r || !out || i < 0 || i >= r->nparams) return -1;
    q = &r->params[i];
    out->id = q->id;
    out->label = q->label;
    out->vmin = q->vmin;
    out->vmax = q->vmax;
    out->vdef = q->vdef;
    out->value = q->value;
    out->builtin = (q->builtin != PBI_NONE);
    out->binds = q->nbind;
    return 0;
}

double zrig_param_get(const zrig *r, const char *id)
{
    int i;
    if (!r) return 0.0;
    i = param_find(r, param_alias(id));
    return (i < 0) ? 0.0 : r->params[i].value;
}

int zrig_param_set(zrig *r, const char *id, double v)
{
    int i;
    zparam *q;
    if (!r) return -1;
    i = param_find(r, param_alias(id));
    if (i < 0) return -1;
    q = &r->params[i];
    v = ZC_CLAMP(v, q->vmin, q->vmax);
    q->value = v;
    switch (q->builtin) {                       /* 内建的转发给对应子系统 */
        case PBI_ANGLE_X:   r->look_x = ZC_CLAMP(v / 30.0, -1.0, 1.0); break;
        case PBI_ANGLE_Y:   r->look_y = ZC_CLAMP(-v / 30.0, -1.0, 1.0); break;
        case PBI_EYE_OPEN:  r->blink_manual = ZC_CLAMP(1.0 - v, 0.0, 1.0); break;
        case PBI_EYEBALL_X: r->gaze_x = ZC_CLAMP(v, -1.0, 1.0); break;
        case PBI_EYEBALL_Y: r->gaze_y = ZC_CLAMP(v, -1.0, 1.0); break;
        default: break;
    }
    return 0;
}

int zrig_param_reset(zrig *r, const char *id)
{
    int i;
    if (!r) return -1;
    i = param_find(r, param_alias(id));
    if (i < 0) return -1;
    if (r->params[i].builtin == PBI_EYE_OPEN) {  /* 眨眼复位 = 交回自动 */
        r->blink_manual = -1.0;
        r->params[i].value = r->params[i].vdef;
        return 0;
    }
    return zrig_param_set(r, r->params[i].id, r->params[i].vdef);
}

void zrig_param_reset_all(zrig *r)
{
    int i;
    if (!r) return;
    for (i = 0; i < r->nparams; ++i) zrig_param_reset(r, r->params[i].id);
}

/* 部件级通道的当前值（供外部调试/测试读取） */
double zrig_part_channel(const zrig *r, const char *part_id, const char *param)
{
    int pi, ip;
    if (!r || !part_id || !param) return 0.0;
    pi = find_part(r, part_id);
    if (pi < 0) return 0.0;
    if (parse_param(param, &ip) != 0) return 0.0;
    switch (ip) {
        case P_BEND_X: return r->p_bendx[pi];
        case P_BEND_Y: return r->p_bendy[pi];
        case P_DX: return r->p_dx[pi];
        case P_DY: return r->p_dy[pi];
        case P_SX: return r->p_sx[pi];
        case P_SY: return r->p_sy[pi];
        case P_ROT: return r->p_rot[pi];
        case P_ALPHA: return r->p_alpha[pi];
        default: return 0.0;
    }
}
