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
#define ZRIG_MAX_POSE      8     /* 互斥部件组（≈ pose3.json 的 Groups） */
#define ZRIG_MAX_POSE_ENT 24     /* 所有组的"档位"总数 */
#define ZRIG_MAX_POSE_MEM 48     /* 所有档位引用的部件总数 */
#define ZRIG_MAX_EXPR     16
#define ZRIG_MAX_EXPR_SET 96
#define ZRIG_MAX_BINDS    96
#define ZRIG_MAX_DEFORMS  12
#define ZRIG_MAX_DEFPTS   289   /* (16+1)^2 */
#define ZRIG_MAX_VISEME    8     /* 口型音素表的行数（SIL/A/I/U/E/O/N…） */
#define ZRIG_MAX_VISEME_P  4     /* 一个音素最多同时写几个参数 */
#define ZRIG_VIS_ATTACK   50.0   /* 口型张开的速度（1/s） */
#define ZRIG_VIS_RELEASE  30.0   /* 收口的速度：比张开慢，否则收口像开关 */
#define ZRIG_VIS_RELEASE_OFF  8.0 /* 整句说完的松口：比音素之间的回落再慢一档，
                                     否则嘴会"抽"一下弹回表情（2026-10-13 用户反馈） */
#define ZRIG_MAX_KEYPOOL  1024  /* 所有关键帧共用一个池子，通道里只存 [起点,个数) */
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
    TAG_EYELID = 1u << 9,   /* 眼睑：随眨眼参数往下滑（配 eyelid_travel 用） */
    TAG_EYE_APERTURE = 1u << 10, /* 眼眶开口：随眨眼参数按下沿压扁（配 aperture_min 用） */
    TAG_EYE_SMILE = 1u << 11 /* 笑眼（山型 ∩ 的闭眼）：ParamEyeL/RSmile 淡入，顶替谷型闭眼件 */
};

/* 通道参数 */
enum { P_DX = 0, P_DY, P_SX, P_SY, P_ROT, P_ALPHA, P_BEND_X, P_BEND_Y,
       P_AMOUNT /* 只用于网格形变器 */ };
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
    char   mask_id[4][64];    /* rig 里写的 "mask"：被哪些部件裁切（解析期暂存 id） */
    int    mask[4];           /* 解析后的部件索引 */
    int    nmask;             /* 0 = 不裁切；多个遮罩取**并集**（≈ Live2D 的多重 clipping） */
    int    mask_invert;       /* 1 = 取反：只在遮罩**外面**可见（≈ IsInverted） */
    int    mask_only;         /* 1 = 自己只当遮罩用，不画出来 */
    int    is_mask_src;       /* 1 = 有别的部件拿我当遮罩 */
    char   motion_id[64];     /* motion_from：照抄哪个部件的通道值（解析期暂存 id） */
    int    motion_from;       /* 解析后的部件索引，-1 = 用自己的 */
    double eyelid_travel;     /* 眼睑行程：眨眼参数 1 时往下滑多少画布像素 */
    double aperture_min;      /* 眼眶开口：眨眼参数 1 时纵向还剩几成（0.06 = 基本闭死） */
    int    blend;             /* 混合模式 ZIMG_BLEND_*（≈ Live2D CubismBlendMode） */
    int    eye_side;          /* 0=与左右无关 1=左眼 2=右眼（ParamEyeLOpen/ROpen 分开驱动） */
} zpart;

/* 网格形变器（≈ Live2D 的 ワープデフォーマ）：
   给某个部件铺 cols×rows 的控制网格，points 是"amount = 1 时每个控制点挪多少源图像素"。
   amount 由动作通道（target = 形变器 id，param = amount）或参数绑定写入，每帧清零重算。 */
typedef struct {
    char   id[48];
    char   part_id[64];
    int    part;
    int    cols, rows;
    double ox[ZRIG_MAX_DEFPTS], oy[ZRIG_MAX_DEFPTS];   /* 单位位移 */
    double amount;                                      /* 本帧累加值 */
} zdeform;

typedef struct {
    char   target[48];        /* 组 id、部件 id、形变器 id，或 "root" */
    int    group;             /* >=0 表示作用在组 */
    int    part;              /* >=0 表示作用在部件 */
    int    deform;            /* >=0 表示作用在网格形变器（param 固定为 amount） */
    int    pparam;            /* >=0 表示作用在**命名参数**（≈ .motion3 的曲线目标） */
    int    param;
    int    wave;
    double amp, freq, phase, dur;
    double bias;              /* 直流偏置：官方 CubismBreath 的 offset（value = offset + peak*sin） */
    zease  ease;
    int    curve;             /* 形变曲线（仅 bend_* 用） */
    int    strips;            /* 分段数（仅 bend_* 用；0=默认 24） */
    /* 关键帧曲线（≈ Live2D 的 .motion3 曲线）：有 keys 时忽略 wave/amp/freq。
       key0 是在 r->key_t / r->key_v 池子里的起点。 */
    int    key0, nkeys;
    int    interp;            /* KI_LINEAR / KI_SMOOTH / KI_STEP */
} zchan;

enum { KI_LINEAR = 0, KI_SMOOTH, KI_STEP };

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
    /* 多段摆（G16）：driver 写另一条 physics 的 id 时，输入就是**上一段的输出**，
       这样两三段串起来就是一条有惯性传递的摆链（头发梢比发根再慢半拍）。 */
    int    driver_phys;       /* >=0 = 上一段的下标（必须比自己小，保证先算父段） */
    int    deform;            /* >=0 = 输出到网格形变器的 amount，而不是部件通道 */
    double out_last;          /* 上一帧输出，供下一段当输入 */
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
       PBI_EYEBALL_X, PBI_EYEBALL_Y,
       PBI_EYE_L_OPEN, PBI_EYE_R_OPEN,
       PBI_EYE_L_SMILE, PBI_EYE_R_SMILE };   /* Live2D 标准：左右眼各一个参数 */

typedef struct {
    int    part;              /* >=0 写部件通道 */
    int    group;             /* >=0 写组通道（part < 0 时才看） */
    int    deform;            /* >=0 写网格形变器的 amount（part/group 都 <0 时才看） */
    int    param;             /* P_DX … P_BEND_Y */
    int    curve, strips;     /* bend_* 用 */
    double scale;
    double offset;            /* 常数偏移：通道值 = 参数值×scale + offset */             /* 通道值 = 参数值 × scale */
} zpbind;

/* 表情（Live2D 的 expression）：一组参数偏移，叠在当前动作之上，自带淡入淡出。
   和动作的区别 —— 表情不占用动作状态机，"笑着挥手"不需要再做一个新动作。 */
/* Cubism 的 exp3.json 有三种 Blend：Add / Multiply / Overwrite —— 三种都要有，
   否则别人做的表情文件导进来会按加算算，数值差一大截。 */
enum { EXPR_ADD = 0, EXPR_SET, EXPR_MUL };

typedef struct {
    int    param;             /* 参数下标 */
    double value;
    int    mode;              /* EXPR_ADD / EXPR_SET */
} zexprp;

/* 口型音素（Live2D 的「母音認識方式」）：一个音素 = 一组标准参数取值。
   音量连动只能开合嘴（ParamMouthOpenY），あ/い/う/え/お 的区别靠的是
   「开多大 × 嘴形横向咧开还是撅圆（ParamMouthForm）」的组合。 */
typedef struct {
    char   id[8];                      /* "SIL"/"A"/"I"/"U"/"E"/"O"/"N" */
    int    np;
    int    pidx[ZRIG_MAX_VISEME_P];    /* 参数下标 */
    double val[ZRIG_MAX_VISEME_P];     /* 该音素下这个参数的取值 */
} zvisrow;

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

/* Pose（A8，≈ pose3.json）：一组互斥的"档位"，同一时刻只有一个可见。
   典型用法是 Live2D 的差分切换：眼高光 圆形/星形/无、手势 握拳/张开/比耶。
   { "id":"eye_hl_style", "fade":0.3, "default":"round",
     "entries":[{"id":"round","parts":["eye_hl_l","eye_hl_r"]},
                {"id":"star", "parts":["eye_hl_star_l","eye_hl_star_r"]}] } */
typedef struct {
    char id[48];
    int  mem0, nmem;          /* 在 r->posemem 里的区间 */
    double opacity;           /* 当前显隐权重 0..1（淡入淡出用） */
} zposeent;

typedef struct {
    char id[48];
    double fade;              /* 切换淡化秒数 */
    int  ent0, nent;          /* 在 r->poseents 里的区间 */
    int  cur;                 /* 当前档位（相对 ent0 的序号），-1 = 全关 */
} zpose;

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
    int    legacy_geom_chans;  /* 动作里"直接写部件几何"的通道条数（合规闸：应为 0） */

    zregion regions[ZRIG_MAX_REGIONS];
    int     nregions;

    zphys   phys[ZRIG_MAX_PHYS];
    int     nphys;
    double  phys_last;           /* 上一次积分的时刻，<0 = 还没开始 */
    double  pose_last;           /* Pose 淡化上一次推进的时刻，<0 = 还没开始 */

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

    /* 网格形变器（A5） */
    zdeform deforms[ZRIG_MAX_DEFORMS];
    int     ndeforms;

    /* Pose：互斥部件组（A8，≈ Live2D pose3.json）。
       一组里同一时刻只有一个档位可见，切换时旧档淡出、新档淡入。 */
    zpose   poses[ZRIG_MAX_POSE];
    int     nposes;
    zposeent poseents[ZRIG_MAX_POSE_ENT];
    int     nposeents;
    int     posemem[ZRIG_MAX_POSE_MEM];     /* 档位成员的部件下标（连续分配） */
    int     nposemem;

    /* 关键帧池（所有动作通道共用） */
    double  key_t[ZRIG_MAX_KEYPOOL], key_v[ZRIG_MAX_KEYPOOL];
    int     nkeypool;

    /* 表情层 */
    zexpr   exprs[ZRIG_MAX_EXPR];
    int     nexprs;
    zexprp  exprps[ZRIG_MAX_EXPR_SET];
    int     nexprps;
    int     expr_cur, expr_prev;   /* -1 = 无 */
    double  expr_t0, expr_fade;

    double  p_action[ZRIG_MAX_PARAMS];   /* 本帧由动作通道写进来的参数偏移 */

    /* 参数分组（= model3.json 的 "Groups"）：EyeBlink / LipSync 等。
       不是摆设 —— 自动眨眼只眨 EyeBlink 里列出来的那只眼，口型只写 LipSync 里的参数。 */
    int     blink_targets;       /* 位 0 = 左眼、位 1 = 右眼；0 = 没声明 → 两眼都眨 */
    char    lipsync_param[64];   /* LipSync 组的第一个参数，默认 ParamMouthOpenY */

    /* 口型音素层（见 zvisrow）。表来自 rig.json 的 "visemes"，没写就用内建默认表。 */
    zvisrow vis_rows[ZRIG_MAX_VISEME];
    int     nvis;
    int     vis_pidx[ZRIG_MAX_VISEME_P];  /* 音素表用到的参数（并集） */
    double  vis_cur[ZRIG_MAX_VISEME_P];   /* 平滑后的当前值 */
    int     nvis_p;
    int     vis_target;      /* 当前目标音素下标，-1 = 没有 */
    double  vis_weight;      /* 目标强度 0..1（= 这一帧的音量） */
    int     vis_active;      /* 嘴是否由音素层接管 */
    double  vis_last;        /* 上次平滑的时刻，<0 = 还没开始 */
    double  vis_mix;         /* 口型压过表情的权重（官方 SDK 对 LipSync 用 0.8） */

    /* 渲染用的"最终值"：表情会往上叠，所以和子系统自己的值分开存 */
    double  blink_now;
    double  blink_l, blink_r;          /* 本帧左右眼各自的闭合度 */
    double  smile_l, smile_r;          /* 本帧左右眼各自的笑眼量（0..1，1 = 山型笑眼） */
    double  blink_manual_l, blink_manual_r;  /* <0 = 跟随两眼共同值 */
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
    if (z_streq(name, "amount")) { *out = P_AMOUNT; return 0; }
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
        else if (z_streq(s, "eye_smile")) t |= TAG_EYE_SMILE;
        else if (z_streq(s, "mouth")) t |= TAG_MOUTH;
        else if (z_streq(s, "hair")) t |= TAG_HAIR;
        else if (z_streq(s, "accessory")) t |= TAG_ACCESSORY;
        else if (z_streq(s, "tail")) t |= TAG_TAIL;
        else if (z_streq(s, "gaze")) t |= TAG_GAZE;
        else if (z_streq(s, "eyelid")) t |= TAG_EYELID;
        else if (z_streq(s, "eye_aperture")) t |= TAG_EYE_APERTURE;
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

static int find_deform(const zrig *r, const char *id)
{
    int i;
    if (!id || !*id) return -1;
    for (i = 0; i < r->ndeforms; ++i)
        if (strcmp(r->deforms[i].id, id) == 0) return i;
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
                /* "mask" 可以写一个部件 id，也可以写一个数组（多个遮罩取并集）。 */
                const zjson *mj = zjson_obj_get(pj, "mask");
                p->nmask = 0;
                p->is_mask_src = 0;
                memset(p->mask_id, 0, sizeof(p->mask_id));
                if (mj && zjson_is(mj, ZJSON_ARR)) {
                    size_t q, qn = zjson_count((zjson *)mj);
                    if (qn > 4) {
                        zdiag_error(d, file, mj->line, 0, buf,
                                    "一个部件最多挂 4 个遮罩（写了 %d 个）", (int)qn);
                        return -1;
                    }
                    for (q = 0; q < qn; ++q) {
                        const char *mk = zjson_str(zjson_at((zjson *)mj, q), NULL);
                        if (!mk || !*mk) continue;
                        z_strlcpy(p->mask_id[p->nmask], mk, sizeof(p->mask_id[0]));
                        p->nmask++;
                    }
                } else {
                    const char *mk = zjson_str(mj, NULL);
                    if (mk && *mk) {
                        z_strlcpy(p->mask_id[0], mk, sizeof(p->mask_id[0]));
                        p->nmask = 1;
                    }
                }
                p->mask_invert = zjson_bool(zjson_obj_get(pj, "mask_invert"), 0);
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
        /* 眼眶开口：带 eye_aperture 标签的部件按 blink 纵向压扁（锚点写在下沿 =
           上眼皮往下合）。被它当遮罩裁切的眼白/眼球/高光会跟着被切掉 ——
           这才是真正的"眼睛闭上"，而不是把睁眼图整张淡出。 */
        p->aperture_min = zjson_num(zjson_obj_get(pj, "aperture_min"), 0.06);
        if (p->aperture_min < 0.0) p->aperture_min = 0.0;
        if (p->aperture_min > 1.0) p->aperture_min = 1.0;
        /* 左右眼分开驱动（Live2D 的 ParamEyeLOpen / ParamEyeROpen 是两个参数）：
           显式写 "eye_side":"l"|"r"，不写就按 id 前缀 eye_l / eye_r 猜。 */
        {
            const char *es = zjson_str(zjson_obj_get(pj, "eye_side"), NULL);
            p->eye_side = 0;
            if (es && (*es == 'l' || *es == 'L')) p->eye_side = 1;
            else if (es && (*es == 'r' || *es == 'R')) p->eye_side = 2;
            else if (!es) {
                if (strncmp(p->id, "eye_l", 5) == 0) p->eye_side = 1;
                else if (strncmp(p->id, "eye_r", 5) == 0) p->eye_side = 2;
            }
        }
        {   /* 混合模式：normal（默认）/ add 加算高光 / multiply 乘算腮红·阴影 */
            const char *bl = zjson_str(zjson_obj_get(pj, "blend"), "normal");
            if (z_streq(bl, "add") || z_streq(bl, "additive")) p->blend = ZIMG_BLEND_ADD;
            else if (z_streq(bl, "multiply") || z_streq(bl, "mult")) p->blend = ZIMG_BLEND_MULTIPLY;
            else if (z_streq(bl, "normal")) p->blend = ZIMG_BLEND_NORMAL;
            else {
                zdiag_error(d, file, pj ? pj->line : 0, 0, buf,
                            "blend 只能是 normal/add/multiply，写了 '%s'", bl);
                return -1;
            }
        }
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
/* 网格形变器（A5，≈ Live2D 的 ワープデフォーマ）：
   "deformers":[{ "id":"ahoge_wave", "part":"hair_ahoge", "cols":2, "rows":3,
                  "points":[{"c":1,"r":0,"dx":6,"dy":-2}, ...] }]
   points 里写的是 **amount=1 时该控制点挪多少源图像素**；没写到的控制点不动。
   amount 由动作通道（target 写形变器 id，param 写 amount）或参数 binds 写入。 */
static int load_deformers(zrig *r, const zjson *jd, zdiag *d, const char *file)
{
    size_t i, n;
    if (!jd) return 0;
    if (!zjson_is(jd, ZJSON_ARR)) {
        zdiag_error(d, file, jd->line, 0, "deformers", "deformers 应是数组");
        return -1;
    }
    n = zjson_count(jd);
    for (i = 0; i < n; ++i) {
        const zjson *dj = zjson_at((zjson *)jd, i);
        const zjson *pts;
        zdeform *g;
        const char *id = zjson_str(zjson_obj_get((zjson *)dj, "id"), NULL);
        const char *part = zjson_str(zjson_obj_get((zjson *)dj, "part"), NULL);
        size_t k, np;
        if (r->ndeforms >= ZRIG_MAX_DEFORMS) {
            zdiag_error(d, file, dj ? dj->line : 0, 0, "deformers",
                        "网格形变器过多（上限 %d）", ZRIG_MAX_DEFORMS);
            return -1;
        }
        g = &r->deforms[r->ndeforms];
        memset(g, 0, sizeof(*g));
        if (!id || !*id) {
            zdiag_error(d, file, dj ? dj->line : 0, 0, "deformers", "形变器缺 id");
            return -1;
        }
        if (find_deform(r, id) >= 0 || find_part(r, id) >= 0 || find_group(r, id) >= 0) {
            zdiag_error(d, file, dj ? dj->line : 0, 0, "deformers",
                        "形变器 id '%s' 和已有的部件/组/形变器重名", id);
            return -1;
        }
        z_strlcpy(g->id, id, sizeof(g->id));
        g->part = part ? find_part(r, part) : -1;
        if (g->part < 0) {
            zdiag_error(d, file, dj ? dj->line : 0, 0, "deformers",
                        "形变器 '%s' 的 part '%s' 不存在", id, part ? part : "(缺)");
            return -1;
        }
        z_strlcpy(g->part_id, part, sizeof(g->part_id));
        g->cols = (int)zjson_int(zjson_obj_get((zjson *)dj, "cols"), 2);
        g->rows = (int)zjson_int(zjson_obj_get((zjson *)dj, "rows"), 2);
        if (g->cols < 1 || g->rows < 1 || g->cols > 16 || g->rows > 16) {
            zdiag_error(d, file, dj ? dj->line : 0, 0, "deformers",
                        "形变器 '%s' 的 cols/rows 要在 1~16（实为 %d×%d）",
                        id, g->cols, g->rows);
            return -1;
        }
        pts = zjson_obj_get((zjson *)dj, "points");
        np = pts ? zjson_count((zjson *)pts) : 0;
        for (k = 0; k < np; ++k) {
            const zjson *pj = zjson_at((zjson *)pts, k);
            int cc = (int)zjson_int(zjson_obj_get((zjson *)pj, "c"), -1);
            int rr = (int)zjson_int(zjson_obj_get((zjson *)pj, "r"), -1);
            int idx;
            if (cc < 0 || cc > g->cols || rr < 0 || rr > g->rows) {
                zdiag_error(d, file, pj ? pj->line : 0, 0, "deformers",
                            "形变器 '%s' 的控制点 (c=%d,r=%d) 越界（网格是 %d×%d，"
                            "控制点下标 0..%d / 0..%d）",
                            id, cc, rr, g->cols, g->rows, g->cols, g->rows);
                return -1;
            }
            idx = rr * (g->cols + 1) + cc;
            g->ox[idx] = zjson_num(zjson_obj_get((zjson *)pj, "dx"), 0.0);
            g->oy[idx] = zjson_num(zjson_obj_get((zjson *)pj, "dy"), 0.0);
        }
        r->ndeforms++;
    }
    return 0;
}

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
        ph->driver_phys = -1;
        if (ph->driver < 0 && drv) {
            /* driver 不是组，就看看是不是上一段摆（多段摆链） */
            int q;
            for (q = 0; q < r->nphys; ++q)
                if (strcmp(r->phys[q].id, drv) == 0) { ph->driver_phys = q; break; }
        }
        if (ph->driver < 0 && ph->driver_phys < 0) {
            zdiag_error(d, file, pj ? pj->line : 0, 0, path,
                        "driver '%s' 既不是组，也不是**写在它前面**的另一条 physics"
                        "（多段摆要按根→梢的顺序声明）", drv ? drv : "(缺)");
            return -1;
        }
        ph->axis = (ax && (*ax == 'y' || *ax == 'Y')) ? 1 : 0;
        {
            const char *dfm = zjson_str(zjson_obj_get(pj, "deformer"), NULL);
            ph->deform = dfm ? find_deform(r, dfm) : -1;
            if (dfm && ph->deform < 0) {
                zdiag_error(d, file, pj ? pj->line : 0, 0, path,
                            "deformer '%s' 不存在", dfm);
                return -1;
            }
        }
        if (ph->deform >= 0) ph->param = P_AMOUNT;
        else if (parse_param(pn, &ph->param) != 0) {
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

/* 老名字 → 现名字。2026-10-13 起左右眼是两个真参数（Live2D 标准），
   这里只保留"历史写法仍然能用"的兼容别名。 */
static const char *param_alias(const char *id)
{
    if (z_streq(id, "ParamBlush")) return "ParamCheek";   /* 旧名，标准名是 ParamCheek */
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
    param_add_builtin(r, "ParamEyeOpen",  "睁眼(两眼)", 0.0, 1.0, 1.0, PBI_EYE_OPEN);
    param_add_builtin(r, "ParamEyeLOpen", "左眼 睁开", 0.0,  1.0, 1.0, PBI_EYE_L_OPEN);
    param_add_builtin(r, "ParamEyeROpen", "右眼 睁开", 0.0,  1.0, 1.0, PBI_EYE_R_OPEN);
    /* 笑眼：官方标准表里是 min 0 / default 0 / max 1，「+ 时变成笑眼」。
       做法上笑眼 = 闭着的眼的另一种形状（谷型 ∪ → 山型 ∩），
       所以它隐含"眼睛是闭的"——见 accumulate 里的 blink = max(blink, smile)。 */
    param_add_builtin(r, "ParamEyeLSmile", "左眼 笑眼", 0.0, 1.0, 0.0, PBI_EYE_L_SMILE);
    param_add_builtin(r, "ParamEyeRSmile", "右眼 笑眼", 0.0, 1.0, 0.0, PBI_EYE_R_SMILE);
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
            {
                const char *did = zjson_str(zjson_obj_get(bj, "deformer"), NULL);
                b->deform = did ? find_deform(r, did) : -1;
                if (did && b->deform < 0) {
                    zdiag_error(d, file, bj ? bj->line : 0, 0, path,
                                "deformer '%s' 不存在", did);
                    return -1;
                }
            }
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
            if (b->part < 0 && b->group < 0 && b->deform < 0) {
                zdiag_error(d, file, bj ? bj->line : 0, 0, path,
                            "binds 要写 part、group 或 deformer");
                return -1;
            }
            if (b->deform >= 0) { b->param = P_AMOUNT; b->curve = BEND_ROOT; b->strips = 0; }
            else if (!pn || parse_param(pn, &b->param) != 0) {
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
            /* offset：参数为 0 时通道也可以不是 0。腮红/高光这种"基础 opacity=1、
               靠 alpha 通道减到 0"的零件要用它（scale 1 + offset −1 → 透明度 = 参数值）。 */
            b->offset = zjson_num(zjson_obj_get(bj, "offset"), 0.0);
            r->npbinds++;
            q->nbind++;
        }
    }
    return 0;
}

/* poses：互斥部件组（A8）。写法见上面的 zpose 注释。
   校验：部件必须存在、同一个部件不能出现在两个档位里（否则谁说了算？）、
   default 必须是声明过的档位 id。 */
/* 参数分组（≈ model3.json 的 "Groups"）：
     "param_groups":[ {"name":"EyeBlink","ids":["ParamEyeLOpen","ParamEyeROpen"]},
                      {"name":"LipSync","ids":["ParamMouthOpenY"]} ]
   里面写的参数必须真的存在；EyeBlink 决定自动眨眼眨哪只眼，LipSync 决定口型写哪个参数。 */
static int load_param_groups(zrig *r, const zjson *jg, zdiag *d, const char *file)
{
    size_t i, n;
    r->blink_targets = 0;
    z_strlcpy(r->lipsync_param, "ParamMouthOpenY", sizeof(r->lipsync_param));
    if (!jg) return 0;
    if (jg->type != ZJSON_ARR) {
        zdiag_error(d, file, jg->line, 0, "param_groups", "期望 array");
        return -1;
    }
    n = zjson_count(jg);
    for (i = 0; i < n; ++i) {
        const zjson *gj = zjson_at(jg, i);
        const char *name = zjson_str(zjson_obj_get(gj, "name"), NULL);
        const zjson *ids = zjson_obj_get(gj, "ids");
        size_t k, m;
        if (!name) {
            zdiag_error(d, file, gj ? gj->line : 0, 0, "param_groups", "缺 name");
            return -1;
        }
        if (!ids || ids->type != ZJSON_ARR) {
            zdiag_error(d, file, gj ? gj->line : 0, 0, "param_groups",
                        "分组 '%s' 的 ids 期望 array", name);
            return -1;
        }
        m = zjson_count(ids);
        for (k = 0; k < m; ++k) {
            const char *pid = zjson_str(zjson_at(ids, k), NULL);
            int pi = pid ? param_find(r, param_alias(pid)) : -1;
            if (pi < 0) {
                zdiag_error(d, file, gj->line, 0, "param_groups",
                            "分组 '%s' 里的参数 '%s' 不存在", name, pid ? pid : "(缺)");
                return -1;
            }
            if (z_streq(name, "EyeBlink")) {
                if (r->params[pi].builtin == PBI_EYE_L_OPEN) r->blink_targets |= 1;
                else if (r->params[pi].builtin == PBI_EYE_R_OPEN) r->blink_targets |= 2;
                else if (r->params[pi].builtin == PBI_EYE_OPEN) r->blink_targets |= 3;
                else {
                    zdiag_error(d, file, gj->line, 0, "param_groups",
                                "EyeBlink 只能写 ParamEyeLOpen / ParamEyeROpen / ParamEyeOpen，写了 '%s'",
                                pid);
                    return -1;
                }
            } else if (z_streq(name, "LipSync") && k == 0) {
                z_strlcpy(r->lipsync_param, r->params[pi].id, sizeof(r->lipsync_param));
            }
        }
    }
    if (!r->blink_targets) r->blink_targets = 3;   /* 没声明 = 两只眼一起眨（老 rig 照常） */
    return 0;
}

/* 口型同步该写哪个参数（= model3.json 的 LipSync 组）。 */
const char *zrig_lipsync_param(const zrig *r)
{
    return (r && r->lipsync_param[0]) ? r->lipsync_param : "ParamMouthOpenY";
}

/* ------------------------------------------------ 口型音素表（visemes）
   内建默认表。数值取自 Live2D 标准参数的约定：
     ParamMouthOpenY 0..1（0 闭 1 张到最大）、ParamMouthForm -1..1（+ 咧开笑、- 撅圆）。
   官方标准参数表里**没有** ParamMouthA/I/U/E/O 这种音素参数，
   母音是用「开合 × 嘴形」两个标准参数的组合摆出来的，所以这里是一张表而不是五个新参数。 */
static const struct { const char *id; double open, form; } VIS_DEFAULT[] = {
    { "SIL", 0.00,  0.00 },   /* 静默：闭嘴 */
    { "A",   1.00,  0.00 },   /* あ：张到最大，嘴形中性 */
    { "I",   0.22,  1.00 },   /* い：几乎不张，横向咧到最宽 */
    { "U",   0.30, -1.00 },   /* う：小口撅圆 */
    { "E",   0.58,  0.55 },   /* え：半开偏宽 */
    { "O",   0.88, -0.70 },   /* お：大口撅圆 */
    { "N",   0.06, -0.35 }    /* ん/闭音：基本闭上，嘴角收住 */
};

/* 音素层用到的参数做个并集，平滑状态按并集存（将来加 ParamMouthSize 也不用改结构） */
static int viseme_add_param(zrig *r, int pi)
{
    int k;
    for (k = 0; k < r->nvis_p; ++k)
        if (r->vis_pidx[k] == pi) return k;
    if (r->nvis_p >= ZRIG_MAX_VISEME_P) return -1;
    r->vis_pidx[r->nvis_p] = pi;
    r->vis_cur[r->nvis_p] = r->params[pi].vdef;
    return r->nvis_p++;
}

static void viseme_default_table(zrig *r)
{
    int po = param_find(r, zrig_lipsync_param(r));
    int pf = param_find(r, "ParamMouthForm");
    size_t k;
    if (po < 0 && pf < 0) return;            /* 这个角色没有嘴参数，就没有音素层 */
    for (k = 0; k < sizeof(VIS_DEFAULT) / sizeof(VIS_DEFAULT[0]); ++k) {
        zvisrow *row;
        if (r->nvis >= ZRIG_MAX_VISEME) break;
        row = &r->vis_rows[r->nvis++];
        memset(row, 0, sizeof(*row));
        z_strlcpy(row->id, VIS_DEFAULT[k].id, sizeof(row->id));
        if (po >= 0 && viseme_add_param(r, po) >= 0) {
            row->pidx[row->np] = po;
            row->val[row->np++] = VIS_DEFAULT[k].open;
        }
        if (pf >= 0 && viseme_add_param(r, pf) >= 0) {
            row->pidx[row->np] = pf;
            row->val[row->np++] = VIS_DEFAULT[k].form;
        }
    }
}

/* rig.json:
     "visemes":[ {"id":"A","params":{"ParamMouthOpenY":1.0,"ParamMouthForm":0.0}}, ... ]
   参数必须是模型里真有的参数（写错名字当场报错，不静默忽略）。 */
static int load_visemes(zrig *r, const zjson *jv, zdiag *d, const char *file)
{
    size_t i;
    r->nvis = 0;
    r->nvis_p = 0;
    r->vis_target = -1;
    r->vis_weight = 0.0;
    r->vis_active = 0;
    r->vis_last = -1.0;
    /* 只夹范围，不替换 0：写 0 的意思就是「口型不压表情」，必须照做，
       否则负控试验永远红不了（见 LESSONS「跳过即通过」）。 */
    if (r->vis_mix < 0.0) r->vis_mix = 0.0;
    if (r->vis_mix > 1.0) r->vis_mix = 1.0;
    if (!jv) { viseme_default_table(r); return 0; }
    if (!zjson_is(jv, ZJSON_ARR)) {
        zdiag_error(d, file, jv->line, 0, "visemes", "期望 array");
        return -1;
    }
    for (i = 0; i < zjson_count(jv); ++i) {
        const zjson *vj = zjson_at((zjson *)jv, i);
        const char *id = zjson_str(zjson_obj_get((zjson *)vj, "id"), NULL);
        zjson *pj = zjson_obj_get((zjson *)vj, "params");
        zvisrow *row;
        size_t k;
        char path[64];
        z_snprintf(path, sizeof(path), "visemes[%d]", (int)i);
        if (!id || !*id) {
            zdiag_error(d, file, vj->line, 0, path, "缺少 id");
            return -1;
        }
        if (r->nvis >= ZRIG_MAX_VISEME) {
            zdiag_error(d, file, vj->line, 0, path, "音素最多 %d 个", ZRIG_MAX_VISEME);
            return -1;
        }
        if (!pj || !zjson_is(pj, ZJSON_OBJ)) {
            zdiag_error(d, file, vj->line, 0, path, "params 期望 object");
            return -1;
        }
        row = &r->vis_rows[r->nvis++];
        memset(row, 0, sizeof(*row));
        z_strlcpy(row->id, id, sizeof(row->id));
        for (k = 0; k < zjson_count(pj); ++k) {
            const char *pid = zjson_key_at(pj, k);
            int pi = pid ? param_find(r, param_alias(pid)) : -1;
            if (pi < 0) {
                zdiag_error(d, file, pj->line, 0, path,
                            "参数 '%s' 不存在（音素只能写模型声明过的参数）",
                            pid ? pid : "?");
                return -1;
            }
            if (row->np >= ZRIG_MAX_VISEME_P || viseme_add_param(r, pi) < 0) {
                zdiag_error(d, file, pj->line, 0, path,
                            "一个音素最多写 %d 个参数", ZRIG_MAX_VISEME_P);
                return -1;
            }
            row->pidx[row->np] = pi;
            row->val[row->np++] = zjson_num(zjson_obj_get(pj, pid), 0.0);
        }
    }
    return 0;
}

/* 这个参数在该音素下的目标值（按当前强度插在默认值和音素值之间） */
static double viseme_target_for(const zrig *r, int pi)
{
    const zvisrow *row;
    int k;
    double base = r->params[pi].vdef;
    if (r->vis_target < 0 || r->vis_target >= r->nvis) return base;
    row = &r->vis_rows[r->vis_target];
    for (k = 0; k < row->np; ++k)
        if (row->pidx[k] == pi) return base + (row->val[k] - base) * r->vis_weight;
    return base;
}

static void viseme_release(zrig *r)
{
    int k;
    for (k = 0; k < r->nvis_p; ++k) {
        /* 只收回音素层自己的值；基础参数是用户/动作的地盘，不碰 */
        r->vis_cur[k] = r->params[r->vis_pidx[k]].vdef;
    }
    r->vis_active = 0;
    r->vis_target = -1;
    r->vis_weight = 0.0;
    r->mouth_mute = 0;
}

/* 每帧平滑。张开快、收口慢（参考 airi 的 wlipsync vowel driver：
   attack/release 两档指数平滑；一口气切到目标会抖得像机器）。 */
static void viseme_update(zrig *r, double now)
{
    double dt, kup, kdn;
    int k, settled = 1, all_base = 1;
    if (!r->vis_active || r->nvis_p <= 0) { r->vis_last = now; return; }
    dt = (r->vis_last < 0.0) ? 0.0 : now - r->vis_last;
    r->vis_last = now;
    if (dt < 0.0) dt = 0.0;
    if (dt > 0.25) dt = 0.25;
    kup = 1.0 - exp(-ZRIG_VIS_ATTACK * dt);
    /* 还在说话（weight>0）= 音素之间的回落，要快；整句说完（weight=0）= 松口，要慢 */
    kdn = 1.0 - exp(-((r->vis_weight > 1e-6) ? ZRIG_VIS_RELEASE
                                             : ZRIG_VIS_RELEASE_OFF) * dt);
    for (k = 0; k < r->nvis_p; ++k) {
        int pi = r->vis_pidx[k];
        double base = r->params[pi].vdef;
        double tgt = viseme_target_for(r, pi);
        double cur = r->vis_cur[k];
        double kk = (fabs(tgt - base) > fabs(cur - base)) ? kup : kdn;
        cur += (tgt - cur) * kk;
        if (fabs(cur - tgt) < 1e-4) cur = tgt;
        r->vis_cur[k] = cur;
        if (fabs(cur - base) > 4e-3) settled = 0;
        if (fabs(tgt - base) > 1e-6) all_base = 0;
    }
    if (settled && all_base) viseme_release(r);   /* 收干净了就把嘴交还给动作 */
}

/* ------------------------------------------------ 口型音素层（对外） */
int zrig_viseme_count(const zrig *r) { return r ? r->nvis : 0; }

const char *zrig_viseme_id(const zrig *r, int i)
{
    if (!r || i < 0 || i >= r->nvis) return NULL;
    return r->vis_rows[i].id;
}

int zrig_viseme_find(const zrig *r, const char *id)
{
    int i;
    if (!r || !id || !*id) return -1;
    for (i = 0; i < r->nvis; ++i) {
        const char *a = r->vis_rows[i].id;
        const char *b = id;
        while (*a && *b) {
            int ca = (*a >= 'a' && *a <= 'z') ? *a - 32 : *a;
            int cb = (*b >= 'a' && *b <= 'z') ? *b - 32 : *b;
            if (ca != cb) break;
            ++a; ++b;
        }
        if (!*a && !*b) return i;
    }
    return -1;
}

int zrig_viseme_entry(const zrig *r, int vi, int k, const char **param_id, double *value)
{
    const zvisrow *row;
    if (!r || vi < 0 || vi >= r->nvis) return -1;
    row = &r->vis_rows[vi];
    if (k < 0 || k >= row->np) return -1;
    if (param_id) *param_id = r->params[row->pidx[k]].id;
    if (value) *value = row->val[k];
    return 0;
}

int zrig_viseme_entry_count(const zrig *r, int vi)
{
    if (!r || vi < 0 || vi >= r->nvis) return 0;
    return r->vis_rows[vi].np;
}

int zrig_viseme_set(zrig *r, const char *id, double weight)
{
    int vi;
    if (!r || r->nvis <= 0) return -1;
    if (!id || !*id) vi = zrig_viseme_find(r, "SIL");
    else {
        vi = zrig_viseme_find(r, id);
        if (vi < 0) return -1;              /* 不认识的音素要报错，不能当静默吞掉 */
    }
    r->vis_target = vi;
    r->vis_weight = ZC_CLAMP(weight, 0.0, 1.0);
    if (!r->vis_active) r->vis_last = r->now;   /* 重新接管时别用上一次的时间差 */
    r->vis_active = 1;
    r->mouth_mute = 1;                      /* 说话时动作里的嘴通道让路 */
    return 0;
}

/* 松口：不是"啪"地一下清零，而是把目标收回默认值，让平滑把嘴送回去
   （release 30/s）；收干净了 viseme_update() 会自动 viseme_release()。
   说完话一帧之内从说话嘴形弹回笑脸，人眼看着就是"抽一下"（2026-10-13 用户反馈）。 */
void zrig_viseme_clear(zrig *r)
{
    if (!r || r->nvis_p <= 0) return;
    if (!r->vis_active) { viseme_release(r); return; }
    r->vis_weight = 0.0;        /* 目标 = 默认值；vis_target 保留，形状一路收回去 */
}

/* 真的立刻清掉（换角色/换形态这种"不用管好不好看"的场合） */
void zrig_viseme_reset(zrig *r)
{
    if (r) viseme_release(r);
}

/* 冻结时钟（dt 恒为 0）时平滑走不动，直接到位——测试台和自检靠它 */
void zrig_viseme_snap(zrig *r)
{
    int k;
    if (!r || !r->vis_active) return;
    for (k = 0; k < r->nvis_p; ++k)
        r->vis_cur[k] = viseme_target_for(r, r->vis_pidx[k]);
    r->vis_last = r->now;
}

double zrig_viseme_mix(const zrig *r) { return r ? r->vis_mix : 0.0; }

const char *zrig_viseme_current(const zrig *r)
{
    if (!r || !r->vis_active || r->vis_target < 0) return NULL;
    return r->vis_rows[r->vis_target].id;
}

double zrig_viseme_weight(const zrig *r)
{
    return (r && r->vis_active) ? r->vis_weight : 0.0;
}

/* 自动眨眼眨哪只眼：位 0 = 左、位 1 = 右（= model3.json 的 EyeBlink 组）。 */
int zrig_blink_targets(const zrig *r) { return r ? r->blink_targets : 3; }

static int load_poses(zrig *r, const zjson *jp, zdiag *d, const char *file)
{
    size_t i, n;
    if (!jp) return 0;
    if (!zjson_is(jp, ZJSON_ARR)) {
        zdiag_error(d, file, jp->line, 0, "poses", "poses 应是数组");
        return -1;
    }
    n = zjson_count((zjson *)jp);
    for (i = 0; i < n; ++i) {
        const zjson *gj = zjson_at((zjson *)jp, i);
        const zjson *ents = zjson_obj_get((zjson *)gj, "entries");
        const char *gid = zjson_str(zjson_obj_get((zjson *)gj, "id"), NULL);
        const char *defid = zjson_str(zjson_obj_get((zjson *)gj, "default"), NULL);
        zpose *g;
        char path[128];
        size_t k, kn;
        if (r->nposes >= ZRIG_MAX_POSE) {
            zdiag_error(d, file, gj ? gj->line : 0, 0, "poses",
                        "互斥部件组过多（上限 %d）", ZRIG_MAX_POSE);
            return -1;
        }
        g = &r->poses[r->nposes];
        memset(g, 0, sizeof(*g));
        if (!gid || !*gid) {
            zdiag_error(d, file, gj ? gj->line : 0, 0, "poses", "pose 组缺 id");
            return -1;
        }
        z_strlcpy(g->id, gid, sizeof(g->id));
        z_snprintf(path, sizeof(path), "poses[%s]", g->id);
        g->fade = zjson_num(zjson_obj_get((zjson *)gj, "fade"), 0.3);
        if (g->fade < 0.0) g->fade = 0.0;
        g->ent0 = r->nposeents;
        kn = zjson_count((zjson *)ents);
        if (!ents || !zjson_is(ents, ZJSON_ARR) || kn < 2) {
            zdiag_error(d, file, gj ? gj->line : 0, 0, path,
                        "entries 至少要两个档位（只有一个就不叫互斥了）");
            return -1;
        }
        for (k = 0; k < kn; ++k) {
            const zjson *ej = zjson_at((zjson *)ents, k);
            const zjson *ps = zjson_obj_get((zjson *)ej, "parts");
            const char *eid = zjson_str(zjson_obj_get((zjson *)ej, "id"), NULL);
            zposeent *e;
            size_t q, qn = zjson_count((zjson *)ps);
            if (r->nposeents >= ZRIG_MAX_POSE_ENT) {
                zdiag_error(d, file, ej ? ej->line : 0, 0, path,
                            "档位过多（上限 %d）", ZRIG_MAX_POSE_ENT);
                return -1;
            }
            e = &r->poseents[r->nposeents];
            memset(e, 0, sizeof(*e));
            if (!eid || !*eid) {
                zdiag_error(d, file, ej ? ej->line : 0, 0, path, "档位缺 id");
                return -1;
            }
            z_strlcpy(e->id, eid, sizeof(e->id));
            e->mem0 = r->nposemem;
            if (!ps || !zjson_is(ps, ZJSON_ARR) || qn < 1) {
                zdiag_error(d, file, ej ? ej->line : 0, 0, path,
                            "档位 '%s' 的 parts 至少写一个部件", eid);
                return -1;
            }
            for (q = 0; q < qn; ++q) {
                const char *pid = zjson_str(zjson_at((zjson *)ps, q), NULL);
                int pi = pid ? find_part(r, pid) : -1;
                int t;
                if (pi < 0) {
                    zdiag_error(d, file, ej ? ej->line : 0, 0, path,
                                "档位 '%s' 引用了不存在的部件 '%s'", eid, pid ? pid : "(空)");
                    return -1;
                }
                for (t = 0; t < r->nposemem; ++t) {
                    if (r->posemem[t] == pi) {
                        zdiag_error(d, file, ej ? ej->line : 0, 0, path,
                                    "部件 '%s' 已经属于另一个档位了（一个部件只能归一处）", pid);
                        return -1;
                    }
                }
                if (r->nposemem >= ZRIG_MAX_POSE_MEM) {
                    zdiag_error(d, file, ej ? ej->line : 0, 0, path,
                                "档位成员过多（上限 %d）", ZRIG_MAX_POSE_MEM);
                    return -1;
                }
                r->posemem[r->nposemem++] = pi;
                e->nmem++;
            }
            r->nposeents++;
            g->nent++;
        }
        /* 默认档位：没写就取第一个。切换前所有非当前档都是全透明。 */
        g->cur = 0;
        if (defid) {
            int t, found = -1;
            for (t = 0; t < g->nent; ++t)
                if (z_streq(r->poseents[g->ent0 + t].id, defid)) { found = t; break; }
            if (found < 0) {
                zdiag_error(d, file, gj ? gj->line : 0, 0, path,
                            "default '%s' 不是这个组里的档位", defid);
                return -1;
            }
            g->cur = found;
        }
        {
            int t;
            for (t = 0; t < g->nent; ++t)
                r->poseents[g->ent0 + t].opacity = (t == g->cur) ? 1.0 : 0.0;
        }
        r->nposes++;
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
            x->mode = (z_streq(md, "set") || z_streq(md, "overwrite")) ? EXPR_SET
                    : ((z_streq(md, "multiply") || z_streq(md, "mul")) ? EXPR_MUL : EXPR_ADD);
            r->nexprps++;
            e->np++;
        }
    }
    return 0;
}

/* 这一帧某个参数被表情改了多少（已含淡入淡出权重）。 */
/* 表情层：把 base 过一遍当前/上一个表情（带淡化权重），返回表情之后的值。
   三个累加器照搬 Cubism 的 CubismExpressionMotion：overwrite / additive / multiply，
   最终 (overwrite + additive) * multiply。 */
static double expr_apply(const zrig *r, int pi, double base)
{
    double w = 1.0, ov = 0.0, add = 0.0, mul = 1.0;
    int pass;
    if (r->expr_cur < 0 && r->expr_prev < 0) return base;
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
            if (x->mode == EXPR_SET)      ov  += ww * (x->value - base);
            else if (x->mode == EXPR_MUL) mul += ww * (x->value - 1.0);
            else                          add += ww * x->value;
        }
    }
    return (base + ov + add) * mul;
}

/* 这个参数是不是正由口型音素层接管？是就返回它在音素层里的槽位。 */
/* 这个参数是不是口型表驱动的（不看口型此刻有没有在说话）。
   动作里的嘴通道要不要让路，看的是"归不归口型管"，不是"现在正不正在说"。 */
static int param_is_viseme_target(const zrig *r, int pi)
{
    int k;
    for (k = 0; k < r->nvis_p; ++k)
        if (r->vis_pidx[k] == pi) return 1;
    return 0;
}

static int viseme_slot(const zrig *r, int pi)
{
    int k;
    if (!r->vis_active) return -1;
    for (k = 0; k < r->nvis_p; ++k)
        if (r->vis_pidx[k] == pi) return k;
    return -1;
}

/* 一个参数这一帧的**最终值**：动作通道 → 表情 → 口型。
   顺序照 Cubism 官方的执行序（ICubismUpdater：EyeBlink 200 / Expression 300 /
   Drag 400 / Breath 500 / Physics 600 / **LipSync 700** / Pose 800）——
   口型排在表情后面，所以「笑着说う」时嘴还是撅圆的，不会被笑脸抵消成中性。 */
/* 口型层这一帧"用了多大力"：所有音素参数里偏离默认值最多的那个（归一化 0..1）。
   说「あ」用满力、停顿（SIL）是 0、小声说话介于中间。
   接管力度随它走，于是：① 停顿时表情自己回来；② 说完松口是连续的，没有跳变；
   ③ 小声说话时表情还能透出来。 */
static double viseme_activity(const zrig *r)
{
    int k;
    double act = 0.0;
    for (k = 0; k < r->nvis_p; ++k) {
        const zparam *q = &r->params[r->vis_pidx[k]];
        double rng = ZC_MAX(q->vmax - q->vdef, q->vdef - q->vmin);
        double d;
        if (rng <= 1e-9) continue;
        d = fabs(r->vis_cur[k] - q->vdef) / rng;
        if (d > act) act = d;
    }
    return ZC_CLAMP(act, 0.0, 1.0);
}

static double param_effective(const zrig *r, int pi)
{
    const zparam *q = &r->params[pi];
    double v = expr_apply(r, pi, q->value + r->p_action[pi]);
    int k = viseme_slot(r, pi);
    if (k >= 0) {
        /* 口型层落到自己的目标形（嘴该多大就多大），给表情/动作留 1-w 的余味，
           w 随这一帧的口型用力程度缩放（停顿时 w→0，表情完整回来，衔接连续）。
           官方是 addParameterValueById(id, v, 0.8)，纯加算——对只驱动开合的
           ParamMouthOpenY 没问题，但我们连 ParamMouthForm 一起驱动，加算会让
           「笑(+Form) + う(-Form)」抵消成中性嘴，所以改成这个口径（见
           docs/LIVE2D_CONFORMANCE.md 的偏差登记）。 */
        double w = r->vis_mix * viseme_activity(r);
        v = r->vis_cur[k] + (v - q->vdef) * (1.0 - w);
    }
    if (v < q->vmin) v = q->vmin;
    if (v > q->vmax) v = q->vmax;
    return v;
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
                c->deform = -1;
                c->pparam = -1;
                /* Live2D 的 .motion3 曲线写的是**参数**，所以 target 先按参数名找：
                   "target":"ParamMouthOpenY" 这种动作可以直接从 Cubism 搬过来。 */
                if (strncmp(tgt, "Param", 5) == 0) c->pparam = param_find(r, param_alias(tgt));
                if (c->pparam < 0) c->group = find_group(r, tgt);
                if (c->pparam < 0 && c->group < 0) {
                    /* 允许直接指向部件（口型/眼部动画）或网格形变器（A5） */
                    c->part = find_part(r, tgt);
                    if (c->part < 0) c->deform = find_deform(r, tgt);
                    if (c->part < 0 && c->deform < 0) {
                        zdiag_error(d, file, cj ? cj->line : 0, 0, buf,
                                    "通道 target '%s' 既不是参数、组、部件，也不是形变器"
                                    "（检查 params / groups / parts / deformers 里的 id）", tgt);
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
                if (c->pparam >= 0) {
                    /* 参数通道只有一个量：参数值本身。写不写 "param":"value" 都行。 */
                    if (pname && !z_streq(pname, "value")) {
                        zdiag_error(d, file, cj ? cj->line : 0, 0, buf,
                                    "参数通道的 param 只能是 \"value\"（写了 '%s'）", pname);
                        return -1;
                    }
                    c->param = P_DX;      /* 占位，不会被用到 */
                } else if (!pname || parse_param(pname, &c->param) != 0) {
                    zdiag_error(d, file, cj ? cj->line : 0, 0, buf,
                                "通道 param 非法（允许 dx/dy/sx/sy/rot_deg/alpha/bend_x/bend_y）");
                    return -1;
                }
                /* 官方 .motion3 的曲线目标只有三种：Model / Parameter / PartOpacity
                   （CubismWebFramework cubismmotion.ts 的 TargetName* 三个常量）。
                   直接写部件的位移/旋转/缩放/弯曲不在其中 —— 记一笔，由 selfcheck 与
                   单测守着它恒为 0，防止几何通道偷偷长回来。 */
                if (c->pparam < 0 && !(c->part >= 0 && c->param == P_ALPHA))
                    r->legacy_geom_chans++;
                /* 关键帧曲线（≈ .motion3）：有 keys 就不看 wave/amp/freq。
                   写法 "keys":[[0,0],[0.3,-12],[1.2,0]]，可选 "interp":"linear|smooth|step"。 */
                {
                    const zjson *ks = zjson_obj_get(cj, "keys");
                    if (ks) {
                        size_t kn = zjson_count(ks), q;
                        const char *ipn = zjson_str(zjson_obj_get(cj, "interp"), "smooth");
                        if (!zjson_is(ks, ZJSON_ARR) || kn < 1) {
                            zdiag_error(d, file, cj ? cj->line : 0, 0, buf,
                                        "keys 应是至少 1 个 [时间,数值] 的数组");
                            return -1;
                        }
                        if (r->nkeypool + (int)kn > ZRIG_MAX_KEYPOOL) {
                            zdiag_error(d, file, cj ? cj->line : 0, 0, buf,
                                        "关键帧总数超上限 %d", ZRIG_MAX_KEYPOOL);
                            return -1;
                        }
                        c->key0 = r->nkeypool;
                        for (q = 0; q < kn; ++q) {
                            const zjson *kj = zjson_at((zjson *)ks, q);
                            double kt, kv;
                            if (!zjson_is(kj, ZJSON_ARR) || zjson_count((zjson *)kj) < 2) {
                                zdiag_error(d, file, kj ? kj->line : 0, 0, buf,
                                            "第 %d 个关键帧应写成 [时间, 数值]", (int)q + 1);
                                return -1;
                            }
                            kt = zjson_num(zjson_at((zjson *)kj, 0), 0.0);
                            kv = zjson_num(zjson_at((zjson *)kj, 1), 0.0);
                            if (q > 0 && kt < r->key_t[r->nkeypool - 1]) {
                                zdiag_error(d, file, kj ? kj->line : 0, 0, buf,
                                            "关键帧时间必须递增（第 %d 个 %.3f 比上一个还早）",
                                            (int)q + 1, kt);
                                return -1;
                            }
                            r->key_t[r->nkeypool] = kt;
                            r->key_v[r->nkeypool] = kv;
                            r->nkeypool++;
                        }
                        c->nkeys = (int)kn;
                        c->interp = z_streq(ipn, "linear") ? KI_LINEAR
                                  : (z_streq(ipn, "step") ? KI_STEP : KI_SMOOTH);
                    }
                }
                if (c->nkeys == 0 && parse_wave(wname, &c->wave) != 0) {
                    zdiag_error(d, file, cj ? cj->line : 0, 0, buf,
                                "通道 wave 非法（允许 sine/bounce/pulse/decay/flap）");
                    return -1;
                }
                c->amp = zjson_num(zjson_obj_get(cj, "amp"), 0.0);
                c->bias = zjson_num(zjson_obj_get(cj, "bias"), 0.0);
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
    r->blink_manual_l = -1.0;
    r->blink_manual_r = -1.0;
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
        /* 遮罩是渲染时**当场画**的（build_maskbuf），所以既不要求遮罩和被裁件在
           图层里挨着，也不要求遮罩画在前面——只要求不自指、不套娃。 */
        for (i = 0; i < r->nparts; ++i) {
            zpart *p = &r->parts[i];
            int q;
            for (q = 0; q < p->nmask; ++q) {
                char path[160];
                int mk = find_part(r, p->mask_id[q]);
                z_snprintf(path, sizeof(path), "parts.%s.mask", p->id);
                if (mk < 0) {
                    zdiag_error(diag, file, 0, 0, path,
                                "mask 指向的部件 '%s' 不存在", p->mask_id[q]);
                    goto fail;
                }
                if (mk == i) {
                    zdiag_error(diag, file, 0, 0, path, "mask 不能指向自己");
                    goto fail;
                }
                p->mask[q] = mk;
                r->parts[mk].is_mask_src = 1;
            }
        }
        /* 遮罩源自己再被别人裁 = 要递归渲染遮罩，没必要也容易写出环。直接禁掉。 */
        for (i = 0; i < r->nparts; ++i) {
            zpart *p = &r->parts[i];
            if (p->is_mask_src && p->nmask > 0) {
                char path[160];
                z_snprintf(path, sizeof(path), "parts.%s.mask", p->id);
                zdiag_error(diag, file, 0, 0, path,
                            "'%s' 既被别人当遮罩用，自己又挂着遮罩（遮罩不支持套娃）", p->id);
                goto fail;
            }
        }
    }
    if (load_deformers(r, zjson_obj_get(root, "deformers"), diag, file) != 0) goto fail;
    /* ⚠ 参数必须在动作之前加载：动作通道可以 target 一个 ParamXxx（≈ .motion3 曲线），
       解析通道时要查得到参数表。参数自己的 binds 只引用组/部件/形变器，都在上面了。 */
    load_builtin_params(r);
    if (load_params(r, zjson_obj_get(root, "params"), diag, file) != 0) goto fail;
    if (load_actions(r, zjson_obj_get(root, "actions"), diag, file) != 0) goto fail;
    if (load_regions(r, zjson_obj_get(root, "regions"), diag, file) != 0) goto fail;
    if (load_physics(r, zjson_obj_get(root, "physics"), diag, file) != 0) goto fail;
    if (load_param_groups(r, zjson_obj_get(root, "param_groups"), diag, file) != 0) goto fail;
    {   /* 口型压过表情的权重：官方 SDK 对 LipSync 用 0.8，缺省就取它 */
        const zjson *jw = zjson_obj_get(root, "viseme_weight");
        r->vis_mix = zjson_num(jw, 1.0);
        if (jw && (r->vis_mix < 0.0 || r->vis_mix > 1.0))
            zdiag_warn(diag, file, jw->line, 0, "viseme_weight", "应在 0~1，已夹回");
    }
    /* 音素表要用参数下标，必须排在 params / param_groups 之后 */
    if (load_visemes(r, zjson_obj_get(root, "visemes"), diag, file) != 0) goto fail;
    if (load_expressions(r, zjson_obj_get(root, "expressions"), diag, file) != 0) goto fail;
    if (load_poses(r, zjson_obj_get(root, "poses"), diag, file) != 0) goto fail;

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
    r->pose_last = -1.0;
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
/* 关键帧曲线取样。t 落在两帧之间按 interp 插值；
   循环动作把 t 对最后一帧的时间取模（曲线自己就是一个循环周期）。 */
static double eval_keys(const zrig *r, const zchan *c, double t, double total)
{
    const double *kt = r->key_t + c->key0, *kv = r->key_v + c->key0;
    int n = c->nkeys, i;
    double span = kt[n - 1];
    if (n == 1) return kv[0];
    if (total < 0.0 && span > 1e-6) {           /* 循环动作：曲线整体循环 */
        t = fmod(t, span);
        if (t < 0.0) t += span;
    }
    if (t <= kt[0]) return kv[0];
    if (t >= kt[n - 1]) return kv[n - 1];
    for (i = 0; i < n - 1; ++i) {
        /* 半开区间 [kt[i], kt[i+1])：正好落在关键帧上时要算"已经到了这一帧"，
           否则阶梯插值在关键帧时刻还停在上一段的值。 */
        if (t >= kt[i] && t < kt[i + 1]) {
            double d = kt[i + 1] - kt[i];
            double u = (d > 1e-9) ? (t - kt[i]) / d : 0.0;
            if (c->interp == KI_STEP) return kv[i];
            if (c->interp == KI_SMOOTH) u = z_smoothstep(u);
            return kv[i] + (kv[i + 1] - kv[i]) * u;
        }
    }
    return kv[n - 1];
}

static double eval_channel_wave(const zrig *r, const zchan *c, double t, double total)
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

/* bias = 直流偏置。官方的 CubismBreath 就是 offset + peak*sin(…)：
   ParamBreath 的值域是 0..1，纯正弦会摆到负半轴被 clamp 掉半个周期，
   所以呼吸这种"单向参数"必须写成 {amp 0.5, bias 0.5}。 */
static double eval_channel(const zrig *r, const zchan *c, double t, double total)
{
    if (c->nkeys > 0) return eval_keys(r, c, t, total);
    return c->bias + eval_channel_wave(r, c, t, total);
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
        if (r->mouth_mute &&
            ((c->part >= 0 && c->part < r->nparts && (r->parts[c->part].tags & TAG_MOUTH)) ||
             (c->pparam >= 0 && param_is_viseme_target(r, c->pparam)))) continue;
        v = eval_channel(r, c, t, total) * w;
        if (c->pparam >= 0 && c->pparam < r->nparams) {
            r->p_action[c->pparam] += v;          /* 动作驱动命名参数（≈ .motion3） */
            continue;
        }
        if (c->deform >= 0 && c->deform < r->ndeforms) {
            r->deforms[c->deform].amount += v;    /* 网格形变器只有一个标量 amount */
            continue;
        }
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
    for (i = 0; i < r->ndeforms; ++i) r->deforms[i].amount = 0.0;
    for (i = 0; i < r->nparams; ++i) r->p_action[i] = 0.0;
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

    /* Pose（A8）：把每个档位的显隐权重往目标值推。
       这里用线性淡化而不是指数趋近：Live2D 的 pose3 也是定长淡化，
       切换手感更可预期（0.3 秒就是 0.3 秒，不会拖一条长尾巴）。 */
    if (r->nposes > 0) {
        int gi;
        double step, dtp;
        if (r->pose_last < 0.0) r->pose_last = r->now;
        dtp = r->now - r->pose_last;
        r->pose_last = r->now;
        if (dtp < 0.0) dtp = 0.0;
        if (dtp > 0.25) dtp = 0.25;
        for (gi = 0; gi < r->nposes; ++gi) {
            zpose *g = &r->poses[gi];
            int t;
            step = (g->fade > 1e-6) ? (dtp / g->fade) : 1.0;
            for (t = 0; t < g->nent; ++t) {
                zposeent *e = &r->poseents[g->ent0 + t];
                double want = (t == g->cur) ? 1.0 : 0.0;
                if (e->opacity < want) e->opacity = ZC_MIN(want, e->opacity + step);
                else if (e->opacity > want) e->opacity = ZC_MAX(want, e->opacity - step);
            }
        }
    }

    /* 命名参数层 + 表情层：都叠在动作之上。
       内建参数（跟随/眨眼/眼球）走各自的子系统，其余按 binds 写通道。 */
    {
        double lx = r->look_cx, ly = r->look_cy;
        double blink_off_l = 0.0, blink_off_r = 0.0;
        double smile_v_l = 0.0, smile_v_r = 0.0;
        r->blink_now = r->blink_value;
        r->gaze_nx = r->gaze_x;
        r->gaze_ny = r->gaze_y;
        for (i = 0; i < r->nparams; ++i) {
            const zparam *q = &r->params[i];
            /* 叠加序：动作通道（≈ .motion3 曲线）→ 表情 → 口型音素（官方 LipSync 排在表情之后） */
            double v = param_effective(r, i);
            double off = v - q->value;
            int k;
            switch (q->builtin) {
                case PBI_ANGLE_X:   lx += off / 30.0; continue;
                case PBI_ANGLE_Y:   ly -= off / 30.0; continue;
                case PBI_EYE_OPEN:  r->blink_now = ZC_CLAMP(r->blink_now - off, 0.0, 1.0); continue;
                case PBI_EYE_L_OPEN: blink_off_l += off; continue;
                case PBI_EYE_R_OPEN: blink_off_r += off; continue;
                /* 笑眼没有别的子系统在写，直接取最终值（不像睁眼那样要算相对眨眼的偏移） */
                case PBI_EYE_L_SMILE: smile_v_l = v; continue;
                case PBI_EYE_R_SMILE: smile_v_r = v; continue;
                case PBI_EYEBALL_X: r->gaze_nx = ZC_CLAMP(r->gaze_nx + off, -1.0, 1.0); continue;
                case PBI_EYEBALL_Y: r->gaze_ny = ZC_CLAMP(r->gaze_ny + off, -1.0, 1.0); continue;
                default: break;
            }
            if (q->nbind <= 0) continue;
            for (k = 0; k < q->nbind; ++k) {
                const zpbind *b = &r->pbinds[q->bind0 + k];
                double bv = v * b->scale + b->offset;
                if (fabs(bv) < 1e-12) continue;
                if (b->deform >= 0 && b->deform < r->ndeforms) {
                    r->deforms[b->deform].amount += bv;
                    continue;
                }
                apply_chan(r, b->part, b->group, b->param, bv, b->curve, b->strips);
            }
        }
        /* 左右眼：各自可以被 ParamEyeLOpen / ParamEyeROpen 按住；没按住就跟两眼共同值。
           眨眼子系统（自动眨眼 / blink_hold）写的是共同值，所以单眼只在被显式驱动时才分家。 */
        r->blink_l = (r->blink_manual_l >= 0.0) ? r->blink_manual_l
                   : ((r->blink_targets & 1) ? r->blink_now : 0.0);
        r->blink_r = (r->blink_manual_r >= 0.0) ? r->blink_manual_r
                   : ((r->blink_targets & 2) ? r->blink_now : 0.0);
        r->blink_l = ZC_CLAMP(r->blink_l - blink_off_l, 0.0, 1.0);
        r->blink_r = ZC_CLAMP(r->blink_r - blink_off_r, 0.0, 1.0);
        /* 笑眼：Live2D 的标准做法是"在闭眼的基础上把睫毛线弯成山型"，
           官方 Haru 的 F05 表情写的就是 ParamEyeLOpen=0(Multiply) + ParamEyeLSmile=1(Add)。
           我们让笑眼自己隐含闭眼（取 max），调用方推一个参数就够；
           官方那种"两个参数一起写"的写法照样成立，因为 max 不会把眼睛又睁开。 */
        r->smile_l = ZC_CLAMP(smile_v_l, 0.0, 1.0);
        r->smile_r = ZC_CLAMP(smile_v_r, 0.0, 1.0);
        if (r->smile_l > r->blink_l) r->blink_l = r->smile_l;
        if (r->smile_r > r->blink_r) r->blink_r = r->smile_r;

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
            case PBI_EYE_L_OPEN:
                q->value = 1.0 - ((r->blink_manual_l >= 0.0) ? r->blink_manual_l : r->blink_value);
                break;
            case PBI_EYE_R_OPEN:
                q->value = 1.0 - ((r->blink_manual_r >= 0.0) ? r->blink_manual_r : r->blink_value);
                break;
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
    if (ph->driver_phys >= 0) {          /* 多段摆：输入 = 上一段这一帧的输出 */
        *out_x = *out_y = r->phys[ph->driver_phys].out_last;
        return;
    }
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
        if (ph->part < 0 || (ph->driver < 0 && ph->driver_phys < 0)) continue;
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
        ph->out_last = out;                      /* 给下一段当输入 */
        if (ph->deform >= 0 && ph->deform < r->ndeforms) {
            r->deforms[ph->deform].amount += out;
            continue;
        }
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

double zrig_phys_output(const zrig *r, const char *id)
{
    int i;
    if (!r || !id) return 0.0;
    for (i = 0; i < r->nphys; ++i)
        if (strcmp(r->phys[i].id, id) == 0) return r->phys[i].out_last;
    return 0.0;
}

int zrig_deform_count(const zrig *r) { return r ? r->ndeforms : 0; }

const char *zrig_deform_id(const zrig *r, int i)
{
    return (r && i >= 0 && i < r->ndeforms) ? r->deforms[i].id : NULL;
}

double zrig_deform_amount(const zrig *r, const char *id)
{
    int i = r ? find_deform(r, id) : -1;
    return i >= 0 ? r->deforms[i].amount : 0.0;
}

void zrig_set_mouth_mute(zrig *r, int on) { if (r) r->mouth_mute = on ? 1 : 0; }
int  zrig_mouth_mute(const zrig *r) { return r ? r->mouth_mute : 0; }

double zrig_eye_close(const zrig *r, int side)
{
    if (!r) return 0.0;
    return side ? r->blink_r : r->blink_l;
}

double zrig_eye_smile(const zrig *r, int side)
{
    if (!r) return 0.0;
    return side ? r->smile_r : r->smile_l;
}

void zrig_blink_set_enabled(zrig *r, int enabled) { if (r) r->blink_enabled = enabled; }
int  zrig_blink_enabled(const zrig *r) { return r ? r->blink_enabled : 0; }
double zrig_blink_value(const zrig *r) { return r ? r->blink_value : 0.0; }

void zrig_blink_set_manual(zrig *r, double v)
{
    if (r) r->blink_manual = (v < 0.0) ? -1.0 : ZC_CLAMP(v, 0.0, 1.0);
}

double zrig_blink_manual(const zrig *r) { return r ? r->blink_manual : -1.0; }

/* mode > 0 = 强制闭眼（睡觉）；mode <= 0 = 交回自动。
   这里原先是 bool（"非 0 就闭眼"），可字段本身用 -1 表示自动，
   调用方照字段语义写 zrig_blink_force(r, -1) 想表达"取消"，结果被当成真 ——
   醒来之后眼睛永远闭着（2026-10-13 用户在测试台看到的就是这个）。
   现在 0 和 -1 都表示取消，两种写法都对。 */
void zrig_blink_force(zrig *r, int mode)
{
    if (!r) return;
    r->blink_forced = (mode > 0) ? 1 : -1;
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
    viseme_update(r, now);
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

/* 这个部件属于某个互斥组时的显隐权重；不属于任何组就是 1。 */
static double pose_opacity(const zrig *r, int part)
{
    int gi, t, q;
    for (gi = 0; gi < r->nposes; ++gi) {
        const zpose *g = &r->poses[gi];
        for (t = 0; t < g->nent; ++t) {
            const zposeent *e = &r->poseents[g->ent0 + t];
            for (q = 0; q < e->nmem; ++q)
                if (r->posemem[e->mem0 + q] == part) return e->opacity;
        }
    }
    return 1.0;
}

/* 一个部件这一帧要怎么画：贴图、矩阵、透明度、弯曲、网格形变。
   抽出来是为了让遮罩可以**按需当场渲染**（不然遮罩缓冲只能靠绘制顺序凑）。
   返回 0 = 这一帧它根本不出现（透明度为 0 / 眨眼交叉淡化到头）。 */
typedef struct {
    const zimg *src;
    double m[6];
    double opacity;
    double bx, by;
    int    curve_x, curve_y;
    int    warped;
    const zdeform *dg;
    double mesh[ZRIG_MAX_DEFPTS * 2];
} zdrawst;

static int compute_draw_state(zrig *r, int pi, double scale, double blink,
                              const zaction *a, zdrawst *st)
{
    zpart *p = &r->parts[pi];
    /* motion_from：通道值照抄别的部件（透け眉这类"同一零件画两遍"用）。
       位置、遮罩、透明度仍然是自己的。 */
    int mi = (p->motion_from >= 0) ? p->motion_from : pi;
    double opacity = p->opacity * r->p_alpha[mi] * pose_opacity(r, pi);
    double extra_dx = r->p_dx[mi], extra_dy = r->p_dy[mi];
    double part_rot = r->p_rot[mi];
    double part_sx, part_sy;
    double smile = 0.0;
    double gm[6], lm[6];
    const zimg *src = p->img_scaled ? p->img_scaled : p->img;

    memset(st, 0, sizeof(*st));
    if (!src) return 0;
    /* 左眼件只看 ParamEyeLOpen，右眼件只看 ParamEyeROpen（眨单眼 / 笑眼都靠这个）。 */
    if (p->eye_side == 1) { blink = r->blink_l; smile = r->smile_l; }
    else if (p->eye_side == 2) { blink = r->blink_r; smile = r->smile_r; }
    /* 视线跟随：只影响带 gaze 标签的部件（虹膜拆分后自动升级为真·视线） */
    if ((p->tags & TAG_GAZE) && (r->gaze_nx != 0.0 || r->gaze_ny != 0.0)) {
        extra_dx += r->gaze_nx * r->gaze_max_dx;
        extra_dy += r->gaze_ny * r->gaze_max_dy;
    }
    /* 眼睑：眨眼参数直接变成往下滑的位移。 */
    if (p->tags & TAG_EYELID) extra_dy += blink * p->eyelid_travel;
    /* 跟随父部件的形变（五官跟着身体弯） */
    {
        double fdx = 0.0, fdy = 0.0;
        part_follow_offset(r, mi, &fdx, &fdy);
        extra_dx += fdx;
        extra_dy += fdy;
    }
    /* 通道里的 sx/sy 相对基准做加法（基准为 1 时与过去的乘法完全一致） */
    part_sx = p->scale_x + (r->p_sx[mi] - 1.0);
    part_sy = p->scale_y + (r->p_sy[mi] - 1.0);
    if (part_sx < 0.0) part_sx = 0.0;
    if (part_sy < 0.0) part_sy = 0.0;
    /* 眼眶开口：按眨眼参数纵向压扁（锚点在开口下沿，所以是上眼皮往下合）。 */
    if ((p->tags & TAG_EYE_APERTURE) && blink > 0.0)
        part_sy *= 1.0 - blink * (1.0 - p->aperture_min);

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
    /* 眨眼：睁眼件淡出、闭眼件淡入。
       ⚠ 不能用线性交叉淡化（opacity = 1-blink / blink）：blink=0.5 时两张图各一半，
       叠出来是一只"灰色幽灵眼"（用户 7 倍放大一眼就看出来）。
       改成**两头让开的斜坡**：睁眼件在 blink<0.75 前不掉透明度（这段由眼眶
       压扁来表现闭合），闭眼件只在最后 25% 淡入——这时两张图都已经是
       "下眼睑上的一条线"，几乎重合，看不出叠影。 */
    /* ⚠ 这里**不能**再看 r->blink_enabled：enabled 只管"自动眨眼定时器要不要跑"，
       不管"这一帧眼睛闭了多少"。曾经写成 (blink_enabled && blink>0.001)，结果关掉
       自动眨眼之后，任何把闭合度推离 0 的东西（表情的 ParamEyeOpen、手动按住、
       blink_hold）都会跳过淡化 → 闭眼件以 100% 不透明直接盖住睁眼件 = 整只眼睛
       突然全闭。判据只看 blink 本身。 */
    if (blink > 0.001) {
        if (p->tags & TAG_EYE_OPEN)
            opacity *= ZC_CLAMP((1.0 - blink) * 4.0, 0.0, 1.0);
        if (p->tags & TAG_EYE_CLOSED)
            opacity *= ZC_CLAMP((blink - 0.75) * 4.0, 0.0, 1.0);
    }
    /* 笑眼和闭眼是同一条睫毛线的两种形状（山型 / 谷型），两张一起画会叠成一团黑：
       笑眼涨多少，谷型闭眼就让多少。笑眼件本身也走"最后 25% 才淡入"那条斜坡，
       前面 75% 由眼眶压扁表现，和闭眼件口径一致。 */
    if (smile > 0.001) {
        if (p->tags & TAG_EYE_CLOSED) opacity *= 1.0 - smile;
        if (p->tags & TAG_EYE_SMILE)
            opacity *= ZC_CLAMP((smile - 0.75) * 4.0, 0.0, 1.0);
    }
    if (opacity <= 0.001) return 0;
    if ((p->tags & TAG_EYE_CLOSED) && blink <= 0.001) return 0;
    if ((p->tags & TAG_EYE_OPEN) && blink >= 0.999) return 0;
    if ((p->tags & TAG_EYE_SMILE) && smile <= 0.001) return 0;

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
        zimg_matrix_mul(st->m, gm, lm);
    } else {
        memcpy(st->m, lm, sizeof(lm));
    }
    st->src = src;
    st->opacity = opacity;
    st->bx = r->p_bendx[mi] * scale;
    st->by = r->p_bendy[mi] * scale;
    st->curve_x = r->p_bendcx[mi];
    st->curve_y = r->p_bendcy[mi];
    st->warped = (fabs(st->bx) > 0.05 || fabs(st->by) > 0.05);

    /* 网格形变（A5）：形变器的位移写的是"原始素材像素"，而这里画的可能是缩放过的
       缓存图，所以要按 src->w / img->w 折算，换画布缩放时形变量才不会跟着变。 */
    {
        int di;
        for (di = 0; di < r->ndeforms; ++di) {
            const zdeform *cand = &r->deforms[di];
            if (cand->part != mi && cand->part != pi) continue;
            if (fabs(cand->amount) < 1e-6) continue;
            st->dg = cand;
            break;
        }
        if (st->dg) {
            double k = (p->img && p->img->w > 0) ? (double)src->w / (double)p->img->w : 1.0;
            int np = (st->dg->cols + 1) * (st->dg->rows + 1), q;
            for (q = 0; q < np; ++q) {
                st->mesh[q * 2]     = st->dg->ox[q] * st->dg->amount * k;
                st->mesh[q * 2 + 1] = st->dg->oy[q] * st->dg->amount * k;
            }
        }
    }
    return 1;
}

/* 按算好的状态画一笔 */
static void draw_state(zimg *dst, const zdrawst *st, int blend)
{
    if (st->dg)
        zimg_draw_mesh_blend(dst, st->src, st->m, st->opacity,
                             st->dg->cols, st->dg->rows, st->mesh, blend);
    else if (st->warped)
        zimg_draw_warp_blend(dst, st->src, st->m, st->opacity,
                             st->bx, st->curve_x, st->by, st->curve_y, blend);
    else
        zimg_draw_blend(dst, st->src, st->m, st->opacity, blend);
}

/* 把 p 的遮罩源画进 maskbuf（多个遮罩取并集；mask_invert 时再取反）。
   返回 0 = 遮罩完全不可见（例如眨眼时眼眶被藏起来）→ 被裁的部件这一帧也不画，
   与 Live2D 的 clipping 语义一致。取反遮罩则相反：遮罩消失＝整块可见。 */
static int build_maskbuf(zrig *r, const zpart *p, double scale, double blink,
                         const zaction *a)
{
    int k, any = 0;
    if (!r->maskbuf) r->maskbuf = zimg_new(r->fb->w, r->fb->h);
    if (!r->maskbuf) return 0;
    zimg_clear(r->maskbuf);
    for (k = 0; k < p->nmask; ++k) {
        zdrawst ms;
        if (!compute_draw_state(r, p->mask[k], scale, blink, a, &ms)) continue;
        ms.opacity = 1.0;              /* 遮罩只用形状，不用它自己的透明度 */
        draw_state(r->maskbuf, &ms, ZIMG_BLEND_NORMAL);
        any = 1;
    }
    if (p->mask_invert) {
        size_t n = (size_t)r->maskbuf->w * r->maskbuf->h, q;
        for (q = 0; q < n; ++q) {
            uint8_t *px = r->maskbuf->px + q * 4;
            px[3] = (uint8_t)(255 - px[3]);
            px[0] = px[1] = px[2] = 255;
        }
        return 1;                      /* 取反后遮罩不可能是"全透明" */
    }
    return any;
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

    a = current_action(r);
    {
        double blink = r->blink_now;      /* 表情叠加后的最终闭合度 */
        for (i = 0; i < r->nparts; ++i) {
            int pi = r->order[i];
            zpart *p = &r->parts[pi];
            zdrawst st;
            zimg *target = r->fb;
            if (!compute_draw_state(r, pi, scale, blink, a, &st)) continue;
            if (p->mask_only) continue;      /* 只当遮罩用的部件不出现在画面上 */

            /* 被裁切：先按需把遮罩画进 maskbuf（可以是多个部件的并集 + 可取反），
               再把自己画进 scratch，最后按遮罩 alpha 合成到画面。
               遮罩是**当场渲染**的，所以不要求遮罩和被裁件在图层里挨着。 */
            if (p->nmask > 0) {
                if (!build_maskbuf(r, p, scale, blink, a)) continue;  /* 遮罩全不可见 = 我也看不见 */
                if (!r->scratch) r->scratch = zimg_new(r->fb->w, r->fb->h);
                if (r->scratch) { zimg_clear(r->scratch); target = r->scratch; }
            }
            /* 被遮罩的部件先画进 scratch（那里是空的，必须用普通混合），
               混合模式留到 composite_masked 那一步再按真正的目标画面算。 */
            draw_state(target, &st, (target == r->fb) ? p->blend : ZIMG_BLEND_NORMAL);
            if (target != r->fb)
                zimg_composite_masked_blend(r->fb, r->scratch, r->maskbuf, p->blend);
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

/* 动作里还剩几条"直接写部件几何"的通道（≈ 不合 .motion3 口径的遗留写法）。
   官方只认 Parameter / PartOpacity / Model 三种曲线目标，所以这个数应该是 0。 */
int zrig_action_geom_channels(const zrig *r) { return r ? r->legacy_geom_chans : 0; }

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

/* 跳过表情的淡入淡出直接到位：冻结时钟（/api/pause）下 now 不走，
   淡入永远卡在 0，测试台和 smoke 就看不到表情——和 zrig_viseme_snap 同一个理由。 */
void zrig_expression_snap(zrig *r)
{
    if (!r) return;
    r->expr_prev = -1;
    r->expr_fade = 0.0;
    r->expr_t0 = r->now;
}

/* ---- Pose（A8）---- */
int zrig_pose_count(const zrig *r) { return r ? r->nposes : 0; }

const char *zrig_pose_id(const zrig *r, int i)
{
    if (!r || i < 0 || i >= r->nposes) return "";
    return r->poses[i].id;
}

int zrig_pose_entry_count(const zrig *r, const char *group)
{
    int gi;
    if (!r || !group) return 0;
    for (gi = 0; gi < r->nposes; ++gi)
        if (z_streq(r->poses[gi].id, group)) return r->poses[gi].nent;
    return 0;
}

const char *zrig_pose_entry_id(const zrig *r, const char *group, int i)
{
    int gi;
    if (!r || !group) return "";
    for (gi = 0; gi < r->nposes; ++gi) {
        const zpose *g = &r->poses[gi];
        if (!z_streq(g->id, group)) continue;
        if (i < 0 || i >= g->nent) return "";
        return r->poseents[g->ent0 + i].id;
    }
    return "";
}

const char *zrig_pose_current(const zrig *r, const char *group)
{
    int gi;
    if (!r || !group) return "";
    for (gi = 0; gi < r->nposes; ++gi) {
        const zpose *g = &r->poses[gi];
        if (!z_streq(g->id, group)) continue;
        return (g->cur >= 0) ? r->poseents[g->ent0 + g->cur].id : "";
    }
    return "";
}

double zrig_pose_weight(const zrig *r, const char *group, const char *entry)
{
    int gi, t;
    if (!r || !group || !entry) return 0.0;
    for (gi = 0; gi < r->nposes; ++gi) {
        const zpose *g = &r->poses[gi];
        if (!z_streq(g->id, group)) continue;
        for (t = 0; t < g->nent; ++t)
            if (z_streq(r->poseents[g->ent0 + t].id, entry))
                return r->poseents[g->ent0 + t].opacity;
    }
    return 0.0;
}

/* 把所有档位的显隐权重直接拉到目标值（跳过淡化）。
   冻结时钟时用：那时 dt=0，淡化永远走不完，切档会看起来没反应。 */
void zrig_pose_snap(zrig *r)
{
    int gi, t;
    if (!r) return;
    for (gi = 0; gi < r->nposes; ++gi) {
        zpose *g = &r->poses[gi];
        for (t = 0; t < g->nent; ++t)
            r->poseents[g->ent0 + t].opacity = (t == g->cur) ? 1.0 : 0.0;
    }
}

/* 切档。entry 传 NULL / "" / "none" = 整组都淡出（Live2D 里要靠一个空白部件实现，
   我们直接支持"全关"，省一张透明图）。组或档位不存在返回 -1（不许悄悄忽略）。 */
int zrig_pose_set(zrig *r, const char *group, const char *entry)
{
    int gi, t, next = -1;
    if (!r || !group) return -1;
    for (gi = 0; gi < r->nposes; ++gi) {
        zpose *g = &r->poses[gi];
        if (!z_streq(g->id, group)) continue;
        if (entry && *entry && !z_streq(entry, "none")) {
            for (t = 0; t < g->nent; ++t)
                if (z_streq(r->poseents[g->ent0 + t].id, entry)) { next = t; break; }
            if (next < 0) return -1;
        }
        g->cur = next;
        return 0;
    }
    return -1;
}

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

/* 参数这一帧的最终值（动作 + 表情 + 口型都算进去）。
   `zrig_param_get` 给的是"参数自己的值"，两者在表情/口型期间会不一样。 */
double zrig_param_effective(const zrig *r, const char *id)
{
    int i;
    if (!r) return 0.0;
    i = param_find(r, param_alias(id));
    return (i < 0) ? 0.0 : param_effective(r, i);
}

/* 只走到表情那一层（不含口型）：测试台要并排显示 参数值 → 表情后 → 最终 */
double zrig_param_expr_value(const zrig *r, const char *id)
{
    int pi;
    if (!r || !id) return 0.0;
    pi = param_find(r, id);
    if (pi < 0) return 0.0;
    return expr_apply(r, pi, r->params[pi].value + r->p_action[pi]);
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
        case PBI_EYE_OPEN:  /* 两眼一起按住：同时交回左右眼的单独控制 */
            r->blink_manual = ZC_CLAMP(1.0 - v, 0.0, 1.0);
            r->blink_manual_l = r->blink_manual_r = -1.0;
            break;
        case PBI_EYE_L_OPEN: r->blink_manual_l = ZC_CLAMP(1.0 - v, 0.0, 1.0); break;
        case PBI_EYE_R_OPEN: r->blink_manual_r = ZC_CLAMP(1.0 - v, 0.0, 1.0); break;
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
        r->blink_manual_l = r->blink_manual_r = -1.0;
        r->params[i].value = r->params[i].vdef;
        return 0;
    }
    if (r->params[i].builtin == PBI_EYE_L_OPEN || r->params[i].builtin == PBI_EYE_R_OPEN) {
        if (r->params[i].builtin == PBI_EYE_L_OPEN) r->blink_manual_l = -1.0;
        else r->blink_manual_r = -1.0;
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
