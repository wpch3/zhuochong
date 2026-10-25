/* zrig.c - 动态立绘骨架与图层合成实现 */
#include "zrig.h"
#include "zjson.h"
#include "zsm.h"
#include "zphys2.h"

#include <math.h>

/* 2026-10-16 抬到 192/160/512（T43.1）。为什么现在抬：
     实测当时 部件 56/96、参数 60/96、绑定 104/256。接下来要同时进来三批东西 ——
       · 三样眼形素材（>_< 倒 V 闭眼 / 真·瞪大眼 / 情绪两档）≈ +6 部件 +3 参数
       · 手臂差分（T40 卖萌动作）≈ +6 部件 +4 参数
       · 一批漫符（T43，汗/💢/小阴云/ZZZ）≈ +15 部件 +13 参数
     加起来部件就到 83、参数到 80，**顶死在 96 上**，而撞上限的表现是
     zrig_load 直接 exit 3（既定口径：不降级）。做到一半撞墙要返工，所以先抬。
   代价**实测**（不是估的）：
     sizeof(zrig)  617248 → 748064 字节（0.59 → 0.71 MB，+131 KB）
     加载一个角色的常驻内存 12800 → 12876 KB（+76 KB，涨 0.6%）
   结构体涨得比 RSS 多，是因为新加的那片数组 calloc 出来就没被碰过、页不驻留。
   换来的是部件/参数/绑定各 2 倍余量。 */
/* 2026-10-25（第六十三问 P0）：192/16/32 → 512/64/96。
   为什么必须现在抬：少女形态实测 103 件 / 15 组 / 26 动作，组只剩 1 格余量——
   换一套服装（多 3~4 组）就当场撞墙，而撞墙的表现是 **zrig_load 返回 NULL**
   （既定口径：不降级、不静默截断）。用户要「一角色四形态 × 多套服装 × 多配件」，
   组/部件/动作都会成倍长，不能每加一套衣服就改一次 C。
   代价（实测，不是估的）：sizeof(zrig) 1113992 → 2415xxx 字节（见下方 zrig 结构体
   末尾的实测注释），一只角色常驻 1.1 MB → 2.4 MB。进程里同时只有一份 rig
   （zpet.c 一次 zrig_load 一份），2.4 MB 对桌面程序是零头。
   同批加的还有「超限必须报错」：以前 load_groups/load_parts/load_actions 的循环
   写成 `for (... && n < MAX)`，超了**静默丢掉**后面的组/部件/动作 —— 一个部件的
   group 指向被丢掉的组，加载失败报的却是"父组未定义"，查半天。 */
#define ZRIG_MAX_PARTS   512
#define ZRIG_MAX_GROUPS   64
/* 挂点（socket，T66.19 / S4）：配件"挂在哪根骨上"的命名位置。
   每个角色包最多这么多条，够一整套饰品（头顶/脸/耳/颈/腕/背…）。 */
#define ZRIG_MAX_SOCKETS  32
#define ZRIG_MAX_CHANNELS 64
#define ZRIG_MAX_REGIONS  32
#define ZRIG_MAX_ACTIONS  ZRIG_ACTION_CAP   /* 公开在 zrig.h：zpet 的动作清单要用同一个数 */
#define ZRIG_MAX_PHYS     48
#define ZRIG_MAX_POSE_MOOD 16
#define ZRIG_MAX_MOOD_PARAM 12   /* mood_params 能登记多少条参数（耳朵 2 条，留余量） */   /* 每个姿态组能登记多少种情绪（情绪词表现有 11 个） */   /* 2026-10-16 抬：24 → 48。猫尾三姿态差分件各带 3 段摆链 = 9 条，直接把 24 顶到 23/24=96%。每多一种动物形象还要再加 */
#define ZRIG_MAX_PARAMS  160   /* 见上面 ZRIG_MAX_PARTS 处的说明 */
#define ZRIG_MAX_BLINK_MOOD 16    /* 眨眼情绪表上限：情绪词表现在 11 个，留一倍余量 */
#define ZRIG_LAG_SLOTS   128     /* 行波延迟环的深度：60fps 够 2.1 秒，240fps 够 0.53 秒 */
#define ZRIG_LAG_MAX     0.5     /* bind.lag 的上限（秒），超了报错不夹 */
/* 物理 2.0（T47.2）：rig.json 的 "physics2" 段，一条 = 一根 2D 粒子摆链。
   8 条的来历：现在接了呆毛 1 + 长发 1，后面排队的是尾巴 4 姿态（T50.4）、
   侧发 2、裙子 3~5（T47.6）—— 到那时再抬，抬之前这个上限会**报错不静默截断**
   （旧 physics 的 ZRIG_MAX_PHYS 静默丢过第 13 条，坑见 load_physics 的注释）。 */
#define ZRIG_MAX_PHYS2     8
#define ZRIG_MAX_P2_OUT    6     /* 一条链最多挂几个输出（粒子最多 8 个，够了） */
#define ZRIG_MAX_XFADE     8     /* 参数驱动的交叉淡化对（踮脚鞋这类"同一部位两张姿态图"） */
#define ZRIG_MAX_BANDS     8     /* 分块渲染最多切几条行带（= 最多用几个线程） */

/* 线程：渲染分块用。没有 pthread / Win32 线程时整体退化成单线程，
   行为完全一致（render_band 顺序跑），只是慢。 */
#if defined(_WIN32)
#  define ZRIG_THREADS 1
#  include <windows.h>
#  include <process.h>
#elif defined(__unix__) || defined(__APPLE__)
#  define ZRIG_THREADS 1
#  include <pthread.h>
#  include <unistd.h>
#else
#  define ZRIG_THREADS 0
#endif
#define ZRIG_MAX_POSE      8     /* 互斥部件组（≈ pose3.json 的 Groups） */
#define ZRIG_MAX_POSE_ENT 24     /* 所有组的"档位"总数 */
#define ZRIG_MAX_POSE_MEM 48     /* 所有档位引用的部件总数 */
#define ZRIG_MAX_EXPR     16
#define ZRIG_MAX_EXPR_SET 96
/* 2026-10-16：星星眼（T39）一口气加了 1 + 8 个参数、36 条绑定（八颗 ✨ 各一个
   参数 × alpha/sx/sy 三条），96 条当场撞上限。和 ZRIG_MAX_PHYS 那次一样 ——
   上限撞了就改大，绝不能让它静默截断。现在用到 140 条。 */
/* 2026-10-25（第六十三问 P0）：512 → 1024。抬的理由不是"现在不够用"（实测 140 条），
   而是 P0 的变形器树会把绑定当连线用：每个 rotate 节点的 dx/dy/rot/sx/sy 都是一条
   绑定，一条 3 节的头发链就是 15 条。四形态 × 多服装要吃满 512 只是时间问题。 */
#define ZRIG_MAX_BINDS  1024   /* 见上面 ZRIG_MAX_PARTS 处的说明 */
/* 2026-10-17：裙子里布（T45.11）给里布单独挂了一张网格，12 张当场撞顶
   —— 和 ZRIG_MAX_PHYS / ZRIG_MAX_EXPR_SET 那两次一样：**上限撞了就改大，
   绝不能静默截断**。一张 zdeform 约 4.8 KB（289 控制点 × 2 double），
   12 → 24 给 zrig 增重约 58 KB。现在用到 13 张。
   2026-10-23（第四十八问）：前臂「沿轴加长」又给左右各加一张（arm_?_fore_long，
   和 arm_?_fore_slim 挂在同一件上逐点相加），25 张当场撞顶 —— 同样的处理：
   **上限撞了就改大**。24 → 32 再增重约 38 KB，现在用到 25 张。 */
/* 2026-10-25（第六十三问 P0）：32 → 64。变形器从"每件一张网格"升级成
   "部件 → warp → rotate → root 的节点树"之后，一个部件的链就有 2~4 个节点，
   32 张立刻不够。一张 zdeform 现在约 4.8 KB（289 控制点 × 2 double + 树字段），
   多出来的 32 张约 152 KB。
   注意：**同一个部件上的多张网格仍必须同尺寸**（要逐点相加），这条校验没变。 */
#define ZRIG_MAX_DEFORMS  64
#define ZRIG_MAX_DEFPTS   289   /* (16+1)^2 */
#define ZRIG_MAX_DEFKF     6    /* 一个形变器最多几组 keyform（≈ Live2D 的 3 键形变） */
#define ZRIG_MAX_VISEME    8     /* 口型音素表的行数（SIL/A/I/U/E/O/N…） */
#define ZRIG_MAX_VISEME_P  4     /* 一个音素最多同时写几个参数 */
#define ZRIG_VIS_ATTACK   50.0   /* 口型张开的速度（1/s） */
#define ZRIG_VIS_RELEASE  30.0   /* 收口的速度：比张开慢，否则收口像开关 */
#define ZRIG_VIS_RELEASE_OFF  8.0 /* 整句说完的松口：比音素之间的回落再慢一档，
                                     否则嘴会"抽"一下弹回表情（2026-10-13 用户反馈） */
#define ZRIG_MAX_KEYPOOL  32768 /* 所有关键帧共用一个池子，通道里只存 [起点,个数)。
                                   为什么是 32768：外部 .motion3 导入时贝塞尔曲线要
                                   按 20fps 烘焙，一条 11 秒的官方动作整份约 1 万个键，
                                   1024 连一条都装不下（T66.21 实测）。 */
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
    TAG_EYE_SMILE = 1u << 11, /* 笑眼（山型 ∩ 的闭眼）：ParamEyeL/RSmile 淡入，顶替谷型闭眼件 */
    TAG_FX_EYE_OPEN = 1u << 12, /* 画面特效跟着眼睛开合变淡，但**不会全灭**（见 FX_EYE_OPEN_FLOOR） */
    TAG_EYE_PAIN = 1u << 13,    /* >_< 痛苦闭眼：倒 V 的闭眼线，顶替谷型闭眼件（口径同 eye_smile） */
    TAG_EYE_WIDE = 1u << 14,    /* 真·瞪大眼补片：ParamEyeL/RWide 淡入，提供更高的眼线和更多眼白 */
    TAG_EYE_NOT_WIDE = 1u << 15 /* 会被瞪大眼补片顶替掉的常态眼件（眼白 base / 上睫毛 lash） */
};

/* 特效件跟随眨眼时的亮度下限。
   为什么不直接用 eye_open（那条是 opacity *= (1-blink)/0.45，会归零）：
   ✨ 是画在脸周围的画面特效，不是眼睛的零件。眨一次眼 0.3 秒，其中有约 0.12 秒
   blink >= 0.45，硬门会让一圈 ✨ 整体熄掉再亮起来 —— 看着像渲染故障而不是表情。
   真实的动画里特效在眨眼时是**跟着暗一下**，不是消失。所以留一个地板。 */
#define FX_EYE_OPEN_FLOOR 0.45

/* 通道参数 */
enum { P_DX = 0, P_DY, P_SX, P_SY, P_ROT, P_ALPHA, P_BEND_X, P_BEND_Y,
       P_AMOUNT /* 只用于网格形变器 */ };
/* 形变曲线：0=根部固定（头发/裙摆） 1=中间最大（弯腰/呼吸） 2=线性 */
/* 形变曲线与 zimg 保持同一套语义（底边=根）：root 底固定/顶部最大，sine 中段最大，
   linear 线性，tip 顶固定/底端最大（后发、裙摆、尾巴）。 */
enum { BEND_ROOT = ZIMG_BEND_ROOT, BEND_SINE = ZIMG_BEND_SINE,
       BEND_LINEAR = ZIMG_BEND_LINEAR, BEND_TIP = ZIMG_BEND_TIP };
/* 通道波形 */
enum { W_SINE = 0, W_BOUNCE, W_PULSE, W_DECAY, W_FLAP, W_DRIFT };

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
    char   deform_id[48];     /* "deformer"：这件挂在哪根变形器链上（≈ Live2D 的父子付け） */
    /* ── 挂点（T66.19 / S4）──
       "socket": "socket_ear_l" 表示这件**不是自己摆好坐标**，而是挂在某个命名挂点上：
       组 = 挂点所在的那根骨，坐标 = 挂点位置 + "dpos"。配件因此不会因为换装/换形态
       而漂 —— 它跟的是名字，不是画布上的数字。 */
    char   socket_id[48];
    int    socket;            /* 解析后的挂点下标，-1 = 没挂 socket */
    /* ── 逐顶点位移场的继承（T66.10b：从"手调系数"改成"声明继承"）──
       "inherit_from" 写**另一个部件**的 id：这件就按那一件的逐顶点形变场跟着起伏
       （≈ Live2D 里把带子挂在布的变形器下面）。
       "warp_inherit" 是继承强度 0~1：0.35 = 只跟到源件的三成。
       —— 为什么需要它：里布/布带/饰物这类"贴在布上的一层"，跟得比主体少才看得见
          层次（里子就是这么露出来的）。以前的做法是**把主体的点表抄一份再乘个系数**
          （裙子里布抄裙摆的表 ×0.35），主体一改就得两边一起改 —— 这就是 T66.10b。
       显式写了 inherit_from 就**只**继承那一件（不再自动扫祖先链，避免双份）。 */
    char   inherit_from_id[64];
    int    inherit_from;      /* 解析后的部件下标，-1 = 不显式继承（走自动祖先链） */
    double warp_inherit;      /* 继承强度（只在显式模式下用），默认 1.0 */
    int    deformer;          /* 解析后的形变器下标，-1 = 没有（只靠挂在自己身上的网格） */
    double eyelid_travel;     /* 眼睑行程：眨眼参数 1 时往下滑多少画布像素 */
    double lash_hold;         /* 眼睑延迟：闭合度小于它之前睫毛不动（0.5 = 后半程才滑） */
    double aperture_min;      /* 眼眶开口：眨眼参数 1 时纵向还剩几成（0.06 = 基本闭死） */
    double bend_hold_above;   /* 形变平台：这个画布高度以上不再继续增大形变（0 = 不设） */
    double bend_hold_below;   /* 下平台：这个画布高度以下不再继续增大形变（0 = 不设） */
    int    blend;             /* 混合模式 ZIMG_BLEND_*（≈ Live2D CubismBlendMode） */
    int    eye_side;          /* 0=与左右无关 1=左眼 2=右眼（ParamEyeLOpen/ROpen 分开驱动） */
} zpart;

/* 网格形变器（≈ Live2D 的 ワープデフォーマ）与变形器树（第六十三问 P0）。
   两种用法写在同一个结构里，因为它们在 Live2D 里本来就是同一种节点的两面：

   ① 网格（art mesh warp，老用法不变）
      { "id":"ahoge_wave", "part":"hair_ahoge", "cols":2, "rows":3,
        "points":[{"c":1,"r":0,"dx":6,"dy":-2}, ...] }
      points 写的是 amount=1 时该控制点挪多少源图像素，amount 由动作通道/绑定写入。

   ② 逐顶点参数驱动（keyform，≈ Live2D 的 3 键形变）
      { "id":"skirt_kf", "part":"skirt_seg0", "param":"ParamSkirtSwing",
        "cols":2, "rows":2,
        "keys":[ {"v":-1,"points":[...]}, {"v":0,"points":[...]}, {"v":1,"points":[...]} ] }
      第 0 组 key 是**绝对**位移，其余是相对第 0 组的增量；按参数值在相邻两组之间线性插值。
      ★ 这才是与 Live2D 对等的那一层：老的单标量 amount 只能表达"参数越大摆得越多"（一条直线），
        而真实立绘要的是"中间鼓、两边收"或"左摆→竖直→右摆"这种**非线性**形变。

   ③ 节点树（≈ Live2D 的 回転デフォーマ / 親子付け）
      每个节点都有 pivot（画布坐标）和自己的局部变换 dx/dy/rot/sx/sy，
      {"id":"arm_rot","pivot":[360,520],"parent":"shoulder_rot"} —— 不写 part 就是纯变换节点；
      写了 parent 就挂到父节点下。部件这一帧的最终矩阵 = A_chain · 组矩阵 · 部件矩阵，
      链上每个节点的变换按"父包住子"的顺序相乘（与 Live2D 的 deformer 树一致）。
      部件也可以直接用 "deformer":"<id>" 指定自己挂在哪根链上。 */
typedef struct {
    char   id[48];
    char   part_id[64];
    int    part;                                        /* -1 = 纯变换节点（没有自己的网格） */
    int    cols, rows;
    double ox[ZRIG_MAX_DEFPTS], oy[ZRIG_MAX_DEFPTS];   /* 单位位移（keyform 模式下 = 第 0 组 key） */
    double amount;
    /* —— 树 —— */
    char   parent_id[48];
    int    parent;            /* 父形变器下标，-1 = 无（挂在 root 下） */
    double pivot[2];          /* 变换中心（画布坐标） */
    double dx, dy, rot, sx, sy;   /* 本帧局部变换（动作通道 / 绑定写入，每帧清零重算） */
    /* —— keyform —— */
    char   kf_param_id[64];   /* rig 里写的参数 id（参数表在形变器之后才加载，先存着） */
    int    param;             /* 解析后的驱动参数下标，-1 = 没有 keyform */
    int    nkf;               /* key 组数，0 = 没有 keyform */
    int    kf_np;             /* (cols+1)*(rows+1) */
    double kf_v[ZRIG_MAX_DEFKF];
    double *kf_d;             /* 动态：nkf 组增量，每组 kf_np*2 个 double（末组也分配，省下标判断） */
    double kf_w[ZRIG_MAX_DEFKF];  /* 本帧插值权重（不含"第 0 组恒为 1"那一项） */
    /* —— keyform 分段缓动（T66.11）：第 k 段 = 第 k-1 组 key → 第 k 组 key，
       写法挂在**右端点**那一组 key 上（"走到我这儿用什么速度"）。没写 = 线性。 */
    double kf_lag;            /* keyform 也吃迟滞：读 lag 秒之前的参数值（同 bind.lag，T66.11b） */
    zease  kf_ease[ZRIG_MAX_DEFKF];
    unsigned char kf_step[ZRIG_MAX_DEFKF];    /* 1 = 阶梯：到本组 key 才跳过去（≈ Live2D 階段） */
    unsigned char kf_bez_on[ZRIG_MAX_DEFKF];  /* 1 = 用 kf_bez 的三次贝塞尔 */
    double kf_bez[ZRIG_MAX_DEFKF][4];         /* x1,y1,x2,y2（归一化 timing curve，x 必须 ∈[0,1]） */
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
    /* 给人看的名字。放在数据层而不是界面层，是因为界面是要换的
       （测试台只是脚手架，正式软件的 UI 会整个重做），
       而"挥手"这个词两边都要用 —— 写在界面里就得写两遍、改两处。 */
    char   title[64];
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
    double fade;              /* 秒：淡入这个动作要多久（Live2D 的 FadeInTime） */
    double fade_out;          /* 秒：非循环动作在**结束前**自己淡出的时长（Live2D 的 FadeOutTime） */
    /* 切到这个动作时顺手点一次自发抽动，值 = 参数名前缀（"ParamEar"/"ParamAccTail"）。
       为什么不直接在动作通道里写摆动参数：那会违反 T45.9 的红线
       「摆动参数只能挂 ambient，挂进动作后一换待机动作就停」，而且会把
       抽动的幅度叠在摆动值域之外被 clamp 削平（T45.2f 栽过的坑）。
       让动作去**触发既有机制**，比让动作自己画一遍要稳得多。 */
    char   flick_pre[32];
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
    int    pparam;            /* >=0 = 输出到**命名参数**（≈ 官方 Output[].DestinationId；T66.11c）。
                                 和 physics2 的同名字段语义一致：param 写 "ParamXxx" 且没有
                                 deformer 时走这条 —— 网格改 keyform 之后仍然推得动。 */
    double out_last;          /* 这一帧**插值后**的输出（渲染用的就是它） */
    /* 固定步长积分的三个状态（G113，照搬官方 CubismPhysics::Evaluate）：
       out_prev/out_cur = 相邻两个固定步的输出，渲染时按 alpha 在两者之间插值；
       in_prev = 上一个固定步用过的输入，供"输入线性插值"当起点。
       没有这三个的话，低帧率下一帧积一大步，显式欧拉过冲，呆毛/手的惯性
       会被放大好几倍，看着就是**左右抽搐**（2026-10-16 用户报的就是这个）。 */
    double out_prev, out_cur;
    double in_prev;
    int    in_init;           /* in_prev 是否已经装过值（0 = 第一步，直接取当前输入） */
    /* 参数输入（对齐官方 .physics3 的 Input 数组）：官方摆链的输入**就是参数**，
       不是"某个组移动了多少像素"。我们原来只会读驱动组的位移，于是凡是
       「只改形状、不改组矩阵」的参数（典型就是 ParamBodyAngleX → seg_torso.bend_x，
       弯曲是非仿射的，根本不在组矩阵里）都驱动不了摆链。裙摆就卡在这儿。 */
    int    n_in;
    int    in_param[4];       /* 参数下标 */
    double in_weight[4];      /* 对应权重（官方的 Input[].Weight，那边是 0..100） */
} zphys;

/* ───────── 物理 2.0：粒子摆链在 rig 里的挂法（T47.2）─────────
   内核（`zphys2.c`）只会算"摆歪了多少度"，它不认识部件也不认识形变器。
   这一层做的就是那句翻译：

       摆角(度) ×scale → 限幅 ±max → 加到切件的 bend_x / rot_deg / 形变器 amount

   `scale` 和 `max` 的名字取自官方 Output[] 的 **Scale（倍率）** 与
   SDK 的"最大输出"，将来 T47.5 导 `physics3.json` 时一一对得上。

   和旧 `zphys` 的关键差别（也就是用户说的"没有真实的物理效果"的根）：
     旧的输出是 `pos − target`（滞后量）⇒ **输入不动，输出必然是 0**，人一停下头发就死了；
     新的输出是**摆相对重力的角度** ⇒ 重力常在，摆有平衡位置，任何扰动都会绕着它
     衰减振荡 —— 呼吸这种 0.28Hz ±1.2px 的微动也能一直把它推着晃。 */
typedef struct {
    int    particle;          /* 读第几个粒子的摆角（1 = 根下面第一节） */
    int    part;              /* >=0 写部件通道 */
    int    deform;            /* >=0 写形变器 amount（优先于 part） */
    int    pparam;            /* >=0 写**命名参数**（≈ 官方 Output[].DestinationId；T66.11c） */
    int    param;             /* P_DX … P_BEND_Y */
    int    curve;             /* bend_* 用的形变曲线 */
    int    inverted;          /* 官方 Output[].Reflect：参考方向取反 */
    double scale;             /* 每度换算成多少像素 / 多少 amount */
    double max;               /* 限幅（像素或 amount），和旧摆的 max 同口径 */
    double applied;           /* 这一帧真正写出去的值（调试与单测读它） */
} zp2out;

typedef struct {
    char   id[32];
    int    part;              /* 链挂在哪个部件上（取根点；也是默认输出目标） */
    int    driver;            /* 驱动组：根点被这个组带着走了多少像素 */
    /* 像素输入（叠加在 driver 之上）：参数值 × 权重 → 根点位移 */
    int    n_in;
    int    in_param[4];
    double in_wx[4], in_wy[4];
    /* 角度输入（官方 Input[].Type = Angle）：参数值 × 权重 → 整条链的额外倾角（度） */
    int    n_ain;
    int    ain_param[4];
    double ain_w[4];
    /* 输入限幅（官方 Normalization 的像素空间等价物，见 p2_input 的注释） */
    double in_max;            /* 根点位移的模长上限（像素） */
    double in_rate;           /* 根点位移的变化速度上限（像素/秒） */
    double in_last_x, in_last_y;
    int    in_seen;
    zphys2 ch;                /* 内核状态 */
    int    nout;
    zp2out out[ZRIG_MAX_P2_OUT];
} zp2chain;

/* 指针跟随（Live2D 的 ParamAngleX/Y/Z + ParamBodyAngleX 那一套）：
   一个 [-1,1] 的方向输入，按组配置成旋转/位移。注意它**不是动作**，
   是叠加在动作之上的姿态偏置，所以任何动作期间都能跟着指针转头。 */
typedef struct {
    int    group;
    double rot, dx, dy;
    /* 这一组比头**晚多少秒**跟上来。Live2D 官方《クオリティアップのヒント》
       原话：「顔XYZと体XYZを慣性を意識してタイミングをずらす ——
       顔と体がまったく同じタイミングで動くと、やはりロボットのように見えます」
       （sites.google.com/cybernoids.jp/cubism2 → editor/animator/technic/quality-up）。
       我们原先头和胸读的是**同一瞬间**的 look 值，正是那句话说的机器人。
       0 = 不延迟，与改这段之前逐字节一致。 */
    double lag;
} zlook;

/* ---------------- 命名参数层（对齐 Live2D 的 ParamXxx） ----------------
   Live2D 里「一切都是参数」：动作、表情、物理、口型最后都只是在写同一张
   参数表，外部（脚本 / LLM / 口型驱动）也写同一张表。我们这边补的就是这层：
     - 内建参数（builtin）路由到已有子系统（视线 / 眨眼 / 头部跟随）；
     - 普通参数靠 binds 直接写组或部件的通道，rig.json 里声明，不改 C 代码。 */
enum { PBI_NONE = 0, PBI_ANGLE_X, PBI_ANGLE_Y, PBI_EYE_OPEN,
       PBI_EYEBALL_X, PBI_EYEBALL_Y,
       PBI_EYE_L_OPEN, PBI_EYE_R_OPEN,
       PBI_EYE_L_SMILE, PBI_EYE_R_SMILE,
       PBI_EYE_L_PAIN, PBI_EYE_R_PAIN,       /* >_< 痛苦闭眼（非官方参数，口径照搬 Smile） */
       PBI_EYE_L_WIDE, PBI_EYE_R_WIDE };     /* Live2D 标准：ParamEyeLWide/RWide，超出 Open 范围的睁大 */

typedef struct {
    int    part;              /* >=0 写部件通道 */
    int    group;             /* >=0 写组通道（part < 0 时才看） */
    int    deform;            /* >=0 写网格形变器的 amount（part/group 都 <0 时才看） */
    int    param;             /* P_DX … P_BEND_Y */
    int    curve, strips;     /* bend_* 用 */
    double scale;
    double offset;            /* 常数偏移：通道值 = 参数值×scale + offset */             /* 通道值 = 参数值 × scale */
    double lag;               /* 读**lag 秒之前**的参数值（行波：梢比根慢半拍） */
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
    zoverride ovr[ZRIG_MAX_OVERRIDES];
    int    novr;               /* 表情级部件透明度/偏移覆盖 */
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
    int  hid0, nhid;          /* 在 r->posehide 里的区间：这一档**生效时要藏起来**的部件 */
    double opacity;           /* 当前显隐权重 0..1（淡入淡出用） */
} zposeent;

typedef struct {
    char id[48];
    double fade;              /* 切换淡化秒数 */
    int  ent0, nent;          /* 在 r->poseents 里的区间 */
    int  cur;                 /* 当前档位（相对 ent0 的序号），-1 = 全关 */
    /* 情绪 → 档位（T45.2d）。表来自 rig.json 的 poses[].mood_map：
       { "happy":"up", "surprise":"puff", ... }。口径和 blink.mood_rate 一样 ——
       查不到的情绪**不动**当前档位（不是回默认），因为"没写"的含义是
       "这个情绪跟这个部位无关"，而不是"这个情绪要把它复位"。 */
    int    nmood;
    struct { char mood[24]; int ent; } mood_map[ZRIG_MAX_POSE_MOOD];
} zpose;

/* 参数驱动的交叉淡化（T24.5）：同一个部位有两张姿态图（常态鞋 / 踮脚鞋），
   由一个参数在两张之间过渡。和上面的 Pose 是一回事，区别只在驱动源 ——
   Pose 是"切一下、定时淡化"，这里是"参数值到哪，权重就到哪"，
   所以能和动作曲线（.motion3 里的 ParamTiptoe）严丝合缝地同步。
   { "id":"foot_l_tiptoe", "param":"ParamTiptoe", "in":[0.25,0.75],
     "from":"seg_foot_l", "to":"seg_foot_l_tip" } */
typedef struct {
    char id[48];
    int  param;               /* 驱动参数下标 */
    int  from, to;            /* 部件下标：from 淡出、to 淡入 */
    double in0, in1;          /* 参数区间 → 权重 0..1 */
    double w;                 /* 本帧权重（= to 件的不透明度） */
} zxfade;

/* 眨眼状态（对齐 Live2D CubismEyeBlink 的五态机） */
enum { BL_FIRST = 0, BL_INTERVAL, BL_CLOSING, BL_CLOSED, BL_OPENING };

/* 视线移动多远算"换了个方向"（归一化视线坐标，量程 -1..1）、以及带眨眼的概率。
   0.45 ≈ 从正前方看到接近一侧极限；0.55 是"经常但不是每次"。 */
#define LOOK_BLINK_DIST   0.45
#define LOOK_BLINK_CHANCE 0.55
/* 两次"因转视线而眨眼"之间至少隔这么久。
   没有它的话，一次大幅扫视（比如从 -0.9 扫到 +0.9，跨度 1.8）在平滑推进中
   会反复越过 0.45 阈值，一次转头触发四五回 —— 实测 30 秒眨了 29 次
   ≈ 58 次/分钟，真人活跃时也就 20~30 次/分钟，看着直抽搐。 */
#define LOOK_BLINK_COOLDOWN 1.2

/* 物理摆的**固定步长**（G113）。
   口径来自 Live2D 官方 CubismNativeFramework/src/Physics/CubismPhysics.cpp：
     _currentRemainTime += deltaTime;
     if (_currentRemainTime > MaxDeltaTime /· 5.0 ·/) _currentRemainTime = 0;
     physicsDeltaTime = 1 / Fps;                 // physics3.json 的 Fps，5.0 起默认 60
     while (_currentRemainTime >= physicsDeltaTime) { ...积一步...; _currentRemainTime -= h; }
     alpha = _currentRemainTime / physicsDeltaTime;  Interpolate(previous, current, alpha);
   官方对这段的注释原文：「この仕様は補間範囲を逸脱したことが原因の**震えたような見た目**を
   回避を目的にしている」——"为的就是避免那种发抖的观感"。正是用户 2026-10-16 报的抽搐。
   ⚠ 绝对不要退回"用整帧 dt 单步积分 + clamp 到 0.1"：实测 2.5fps 时呆毛惯性 ×3.6、
     手 ×11.3（见 docs/memory/GAPS.md G113）。 */
#define ZRIG_PHYS_FPS        60.0
#define ZRIG_PHYS_STEP       (1.0 / ZRIG_PHYS_FPS)
#define ZRIG_PHYS_MAX_REMAIN 5.0
/* T47.3 风的上限。★量纲要说清楚：内核里力 = 重力方向(单位向量) × Acceleration + 风，
   所以**风是以"几个 g"为单位的**，不是像素。实测 wx=0.3 就能把长发整体吹偏 9px，
   wx=1.0 已经顶到输出上限 —— 这类"看着像小数、其实已经很大"的量最容易写错，
   所以上限按 g 取，而不是按像素取。 */
#define ZRIG_BREEZE_MAX       1.5
#define ZRIG_GUST_MAX         6.0
#define ZRIG_GUST_MAX_SEC     3.0

struct zrig {
    char  id[96];
    char  name[192];
    char  dir[512];
    int   cw, ch;
    double origin[2];

    zgroup  groups[ZRIG_MAX_GROUPS];
    int     ngroups;

    struct { char id[48]; int group; double pos[2]; } sockets[ZRIG_MAX_SOCKETS];
    int     nsockets;

    zpart   parts[ZRIG_MAX_PARTS];
    int     nparts;
    int     order[ZRIG_MAX_PARTS];   /* 按 layer 升序的绘制顺序 */

    zaction actions[ZRIG_MAX_ACTIONS];
    int     nactions;
    int     motion3_count;               /* 其中多少条来自外部 .motion3（T66.21） */
    int    legacy_geom_chans;  /* 动作里"直接写部件几何"的通道条数（合规闸：应为 0） */

    zregion regions[ZRIG_MAX_REGIONS];
    int     nregions;

    zphys   phys[ZRIG_MAX_PHYS];
    int     nphys;
    double  phys_last;           /* 上一次积分的时刻，<0 = 还没开始 */
    double  phys_remain;         /* 还没消化掉的真实时间（固定步长积分的累加器） */

    zp2chain p2[ZRIG_MAX_PHYS2];
    int      np2;
    double   p2_last;            /* 物理 2.0 上一次积分的时刻，<0 = 还没开始 */
    /* 引擎级力场（官方 Meta.EffectiveForces，SDK 的 Options 可运行时改）。
       像素空间 Y 向下 ⇒ 向下的重力是 (0,+1)，不是官方那个 Y 向上的 (0,−1)。
       风默认 0；T47.3 会给它接上环境微风 / 情绪阵风 / 场景事件。 */
    double   p2_gx, p2_gy, p2_wx, p2_wy;
    /* T47.3 风有三路，相加后喂给内核：
       ① 定常风 p2_wx/wy（rig 里的 forces.wind，或外部用 /api/force 设）
       ② 常驻微风 breeze（低频噪声，角色站着不动也有的那一点点飘）
       ③ 阵风 gust（一次性冲击，情绪/事件用：生气＝一股风把头发掀一下）
       官方 Meta.EffectiveForces 只有两个常量，但 SDK 的 Options 允许运行时覆盖，
       所以"风会变"是官方架构里的合法扩展点（REFERENCE_NOTES 第四十批）。 */
    double   p2_breeze_amp;          /* 常驻微风幅度（0 = 关） */
    double   p2_breeze_hz;           /* 主频 */
    double   p2_gust_x, p2_gust_y;   /* 阵风强度向量 */
    double   p2_gust_left, p2_gust_dur;  /* 阵风剩余 / 总时长（秒） */
    double   p2_wind_ex, p2_wind_ey; /* 本帧实际合成出来的风（给 /api/force 读回） */
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
    /* 眨眼随情绪漂移（T44.2）。表来自 rig.json 的 blink.mood_rate，
       zrig_blink_set_mood() 查表后把 rate / closed_scale 填进来。
       rate>1 = 眨得更勤（怒、紧张），closed_scale>1 = 闭得更久（困）。
       依据见 docs/REFERENCE_NOTES.md 第二十九批。 */
    int    nblink_mood;
    struct { char mood[24]; double rate, closed_scale; } blink_mood[ZRIG_MAX_BLINK_MOOD];
    char   blink_mood_cur[24];
    /* 情绪 → 参数值（T45.3）。表来自 rig.json 的 mood_params：
       { "ParamEarLAngle": { "happy": 0.85, "angry": -0.9, ... } }。
       和 blink.mood_rate、poses[].mood_map 并列的第三张情绪表，口径一致 ——
       **查不到的情绪不动这条参数**（没写 = 这个情绪跟这条参数无关）。 */
    int    nmood_param;
    struct {
        int    param;                  /* 参数下标 */
        int    n;
        struct { char mood[24]; double v; } e[ZRIG_MAX_BLINK_MOOD];
    } mood_param[ZRIG_MAX_MOOD_PARAM];
    /* 情绪 → 摆动倍率（T45.2f）。表来自 rig.json 的 mood_swing：
         { "params": ["ParamAccTailRelaxedSwing", ...],
           "moods":  { "angry": [3.2, 1.8], ... } }   // [频率倍率, 幅度倍率]
       这是第四张情绪表（前三张：blink.mood_rate / poses[].mood_map / mood_params）。
       ★ 口径和前三张一致：**查不到的情绪不动**，不是回 1.0。
       ★ 只乘 amp 不乘 bias —— bias 是静态姿态偏置，amp 才是动态幅度（LESSONS 162）。
       sw_tshift 是**相位补偿**：频率倍率变了之后，sin(2π·f·t) 会当场跳相，
       t 大的时候等于尾巴瞬移。切换时按
            tshift' = t* − (m_old/m_new)·(t* − tshift)
       重算，保证切换瞬间相位连续（m 的基频会约掉，所以和通道自己的 freq 无关）。 */
    int    nswing_param;
    int    swing_param[ZRIG_MAX_MOOD_PARAM];
    int    nmood_swing;
    struct { char mood[24]; double fmul, amul; } mood_swing[ZRIG_MAX_BLINK_MOOD];
    double sw_fmul[ZRIG_MAX_PARAMS], sw_amul[ZRIG_MAX_PARAMS];
    double sw_tshift[ZRIG_MAX_PARAMS];

    /* ── 行波延迟环（bind.lag，T45.2g）──
       每帧把每条参数的**合成值**压进环，带 lag 的绑定按 now−lag 线性插值回读。
       时间戳只存一份（所有参数同一帧采样），所以多出来的内存是
       ZRIG_MAX_PARAMS × ZRIG_LAG_SLOTS 个 double ≈ 160KB，可接受。
       历史不够长时取最老的一帧（不外推），不会抖。 */
    int     lag_used;                               /* 没人用 lag 就整块跳过 */
    int     lag_fill;                               /* 已写入的帧数（上限 SLOTS） */
    int     lag_head;                               /* 最近一帧所在的槽 */
    double  lag_t[ZRIG_LAG_SLOTS];
    double  lag_v[ZRIG_MAX_PARAMS][ZRIG_LAG_SLOTS];

    /* ── 自发抽动（tail_flick，T45.2g）──
       桌宠**自己**决定什么时候甩一下尾巴，和自动眨眼同构。
       依据（2023, Université Paris Nanterre, de Mouzon et al.）：猫在被人忽视时
       平均摆尾 13.98 秒，被搭理时只有 0.39 秒 ⇒ 摆尾是**阵发事件**，
       不是待机时的匀速节拍。行为学的升级链是「尾尖抽动 → 整条摆 → 拍打」，
       频度和力度都随情绪走，所以表的四个数是 [间隔下限, 间隔上限, 幅度, 时长]。
       ★ 用**自己的随机流** flick_rng：绝不去动 r->rng，那条正在喂眨眼间隔，
         共用会把现有眨眼测试的时序全改掉（而且是悄悄改）。 */
    /* ── 环境摆动（ambient，T45.9）──
       尾巴/裙摆这类"自己一直在动"的通道**不属于任何动作**。
       以前它们写在 idle 的 channels 里，于是：
         ① 待机动作有四个（idle/sway/shift_weight/breath）会轮换，
            切到 breath 裙摆幅度直接变 0.0000 —— 布料整个冻住；
         ② 动作通道按 zsm_elapsed 求值，一换动作就从 0 重来 ⇒ **相位跳回原点**。
       提升成 rig 级之后：不受动作切换影响，按**绝对时刻 r->now** 求值，
       相位永远连续。复用 zaction 这个壳，是为了让 accumulate_action 的
       全部语义（mood_swing 倍率、口型让路、参数/形变器/部件三种目标）原样生效。 */
    zaction ambient;
    int    has_ambient;
    int    ambient_off;      /* 1 = 关掉环境摆动。测物理链时必须关 —— 
                                否则"摇头有没有把裙子带起来"这种断言会把
                                一直在跑的自主摆动算进去，分不出是谁推的。 */

    int    nflick_param;
    int    flick_param[ZRIG_MAX_MOOD_PARAM];
    double flick_scale[ZRIG_MAX_MOOD_PARAM];        /* 每条参数自己的力度系数 */
    struct { double next_t, t0, amp, dur; } flick_st[ZRIG_MAX_MOOD_PARAM];
    int    nmood_flick;
    struct { char mood[24]; double gmin, gmax, amp, dur; }
           mood_flick[ZRIG_MAX_BLINK_MOOD];
    double flick_gmin, flick_gmax, flick_amp, flick_dur;   /* 当前情绪那一档 */
    int    flick_off;        /* 1 = 关掉自发抽动。探针量「慢摆」时必须关，
                                否则两张表的效果叠在一条曲线上分不开。 */
    zrand  flick_rng;
    double blink_rate, blink_closed_scale;
    int    phys_enabled;      /* 0 = 关掉物理摆（排查接缝时用，见 zrig_phys_set_enabled） */
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
    /* 分块渲染每条带各一份（共享会被 zimg_clear 互相清掉） */
    zimg  *band_scratch[ZRIG_MAX_BANDS];
    zimg  *band_maskbuf[ZRIG_MAX_BANDS];
    double fb_scale;
    int    fb_w, fb_h;
    double view_scale;        /* 平台层打算用的缩放；首帧渲染出来之前靠它换算坐标 */

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
    zxfade  xfades[ZRIG_MAX_XFADE];
    int     nxfades;

    zpose   poses[ZRIG_MAX_POSE];
    int     nposes;
    zposeent poseents[ZRIG_MAX_POSE_ENT];
    int      posehide[ZRIG_MAX_POSE_MEM];   /* 各档位的 hide 名单，按 hid0/nhid 切片 */
    int      nposehide;
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
    double  pain_l, pain_r;            /* 本帧左右眼各自的痛苦闭眼量（0..1，1 = 倒 V 的 >_<） */
    double  wide_l, wide_r;            /* 本帧左右眼各自的瞪大量（0..1，1 = 换成瞪大眼补片） */
    double  blink_manual_l, blink_manual_r;  /* <0 = 跟随两眼共同值 */
    double  gaze_nx, gaze_ny;

    /* 头/身跟随指针 */
    zlook  looks[ZRIG_MAX_GROUPS];
    int    nlooks;
    double look_speed;          /* 追踪速度（1/s），越大越跟手 */
    double look_x, look_y;      /* 目标方向 [-1,1] */
    double look_cx, look_cy;    /* 平滑后的当前方向 */
    double look_blink_x, look_blink_y;  /* 上次因转视线而眨眼时的方向（算位移用） */
    double look_blink_last;             /* 上次因转视线而眨眼的时刻（冷却用） */
    int    look_blink_init;
    double look_last;           /* 上次平滑的时刻 */

    /* ── 反动/刹车（look_overshoot）──
       同一篇官方技巧的另一条：「反動、ブレーキを付ける ——
       人間はピタッと瞬時に動きをとめることができません」。
       原来的 look_cx += (目标-当前)*k 是纯指数趋近：永远从一侧慢慢贴上去，
       **到不了也冲不过**，所以停得过于干净，像机械臂落位。
       改成阻尼弹簧后阻尼比 <1 会冲过一点再荡回来，就是"反动"。
       overshoot=0 时走原来那条指数路径，逐字节一致。 */
    double look_overshoot;      /* 0=不冲（纯指数，旧行为）；0.35 左右是自然的一点点 */
    double look_vx, look_vy;    /* 弹簧速度 */
    double look_acc;            /* 固定步长累加器（照 G113 物理那套，低帧率也不变形） */

    /* ── 跟随历史环（给 zlook.lag 回读用）──
       只存 x/y 两条，深度复用 ZRIG_LAG_SLOTS。和参数行波环**分开**：
       那个环按 params_compose 的节奏写，这个要在 look 平滑之后立刻写。 */
    int    lookh_used, lookh_fill, lookh_head;
    double lookh_t[ZRIG_LAG_SLOTS];
    double lookh_x[ZRIG_LAG_SLOTS], lookh_y[ZRIG_LAG_SLOTS];

    /* 眼球微动（マイクロサッカード）。人的眼球从来不会真的静止 ——
       cgbox「目の動きのクオリティアップ」原话：「人の眼球は静止していることはありません」，
       给瞳孔加上常驻的微小游移能明显提升"活着"的感觉。
       同一篇也给了反面警告：「やりすぎると違和感がでますし、常に慌てている印象になる」
       —— 幅度必须是**亚像素到 1 像素**级别，大了就成了眼神乱飘的慌张人。 */
    double sacc_amp;            /* 幅度（归一化视线单位，0 = 关掉） */
    double sacc_gap_min, sacc_gap_max;  /* 两次微跳之间的间隔范围（秒） */
    double sacc_speed;          /* 趋近速度（1/s）。眼跳是"跳"不是"飘"，这个要大 */
    double sacc_x, sacc_y;      /* 当前偏移 */
    double sacc_tx, sacc_ty;    /* 本次微跳的目标偏移 */
    double sacc_next;           /* 下次微跳的时刻 */
    int    sacc_init;
    /* ⚠ 微动**必须用自己的随机流**，不能蹭 r->rng。
       r->rng 同时在喂眨眼间隔（zrand_expo/zrand_range）和"转视线是否眨眼"的 55% 掷骰；
       微动每秒要抽 3 个数，混进去会把眨眼的整条随机序列往后挪 ——
       既有的眨眼时序测试会以"看起来无关的改动"为由莫名其妙地红，
       而且以后每加一个用随机的小功能就再挪一次，谁都别想复现谁。 */
    zrand  sacc_rng;

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
    if (z_streq(name, "drift")) { *out = W_DRIFT; return 0; }
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
        else if (z_streq(s, "eye_pain")) t |= TAG_EYE_PAIN;
        else if (z_streq(s, "eye_wide")) t |= TAG_EYE_WIDE;
        else if (z_streq(s, "eye_not_wide")) t |= TAG_EYE_NOT_WIDE;
        else if (z_streq(s, "mouth")) t |= TAG_MOUTH;
        else if (z_streq(s, "hair")) t |= TAG_HAIR;
        else if (z_streq(s, "accessory")) t |= TAG_ACCESSORY;
        else if (z_streq(s, "tail")) t |= TAG_TAIL;
        else if (z_streq(s, "gaze")) t |= TAG_GAZE;
        else if (z_streq(s, "eyelid")) t |= TAG_EYELID;
        else if (z_streq(s, "eye_aperture")) t |= TAG_EYE_APERTURE;
        else if (z_streq(s, "fx_eye_open")) t |= TAG_FX_EYE_OPEN;
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

static int find_socket(const zrig *r, const char *id)
{
    int i;
    if (!id || !*id) return -1;
    for (i = 0; i < r->nsockets; ++i)
        if (strcmp(r->sockets[i].id, id) == 0) return i;
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
    /* 超限必须报错。老写法是 `i < n && ngroups < MAX` —— 超出的组被静默丢掉，
       而被丢掉的组名还被后面的部件/父组引用，于是报出来的是"父组 'xxx' 未定义"，
       查错方向完全被带偏（第六十三问 P0 修的就是这类静默截断）。
       ★ 判据要写在**循环里**看真实槽位：装载前可能已经自动补了一个 root 组，
         只比"声明条数 vs 上限"会放过"声明 64 组 + root = 65"这一格。 */
    for (i = 0; i < n; ++i) {
        if (r->ngroups >= ZRIG_MAX_GROUPS) {
            zdiag_error(d, file, jgroups->line, 0, "groups",
                        "组数超过上限 %d（含自动补的 root；超出的会被丢掉，"
                        "必须改大 ZRIG_MAX_GROUPS）", ZRIG_MAX_GROUPS);
            return -1;
        }
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
    for (i = 0; i < n; ++i) {
        if (r->nparts >= ZRIG_MAX_PARTS) {
            zdiag_error(d, file, jparts->line, 0, "parts",
                        "部件数超过上限 %d（超出的会被丢掉，必须改大 ZRIG_MAX_PARTS）",
                        ZRIG_MAX_PARTS);
            return -1;
        }
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
            /* deformer：这件挂在哪个变形器节点下（≈ Live2D 的 親子付け）。
               形变器段在部件之后加载，所以这里只存 id，装载末尾再解析。
               自己的网格形变器不需要写这个 —— 它会自动成为本部件的链头；
               只有"整件挂在一个 rotate 节点下、自己没有任何网格"时才必须写。 */
            {
                const char *df = zjson_str(zjson_obj_get(pj, "deformer"), NULL);
                p->deformer = -1;
                p->deform_id[0] = 0;
                if (df && *df) z_strlcpy(p->deform_id, df, sizeof(p->deform_id));
            }
            /* inherit_from / warp_inherit：逐顶点形变场的显式继承（T66.10b）。
               id 在装载末尾解析（那时形变器已经加载完，能查源件有没有网格）；
               强度先夹在这里，范围外当场报错 —— 静默夹会让"我明明写了 1.5"变成 1.0。 */
            {
                const char *ifo = zjson_str(zjson_obj_get(pj, "inherit_from"), NULL);
                p->inherit_from = -1;
                p->inherit_from_id[0] = 0;
                p->warp_inherit = zjson_num(zjson_obj_get(pj, "warp_inherit"), 1.0);
                if (ifo && *ifo) z_strlcpy(p->inherit_from_id, ifo, sizeof(p->inherit_from_id));
                if (!(p->warp_inherit >= 0.0) || p->warp_inherit > 1.0) {
                    char path[160];
                    z_snprintf(path, sizeof(path), "parts.%s.warp_inherit", p->id);
                    zdiag_error(d, file, pj ? pj->line : 0, 0, path,
                                "warp_inherit 要在 0~1 之间（写的是 %.3f）："
                                "0 = 完全不跟随源件，1 = 与源件同一个场", p->warp_inherit);
                    return -1;
                }
            }
        p->tags = parse_tags(zjson_obj_get(pj, "tags"));
        /* 眼睑行程：带 eyelid 标签的部件按 blink 参数下滑这么多像素。
           眨眼不再靠「睁眼图淡出 / 闭眼图淡入」，而是真的有一片眼皮盖下来。 */
        p->eyelid_travel = zjson_num(zjson_obj_get(pj, "eyelid_travel"), 0.0);
        /* 眼睑延迟（lash_hold）：睫毛在闭合度到这个值之前**完全不动**，之后
           smoothstep 补齐到满行程。为什么要延迟见 2026-10-15 的实测：
           眼眶开口是按「开口高度 × 闭合度」从上往下收的，睫毛按同样的像素数
           一起下滑，本意是让两者贴合；但睫毛贴图的弧线本身画在上眼睑线上、
           比开口顶边高一截，而且内眼角那条尾巴更低 —— 一起下滑的结果是半闭
           时那条尾巴正好压进虹膜，放大看就是一个黑钩，瞳孔和高光被吃掉，整
           只眼睛变成一条扁平的青色带（用户 2026-10-15 的截图就是这个画面）。
           实测 A/B（logs/asset_qa/lash_ab.png）：闭合度 0.3~0.6 这一段，睫毛
           不滑明显更干净；但全闭时睫毛必须落在闭眼线上，否则闭眼线上方会露
           出一截睫毛。延迟曲线两头都要：前半程 = 不滑，闭合度 1 = 满行程，
           和改之前**完全一样**。
           默认 0 = 旧的线性行程（不写这个字段的 rig 行为完全不变）；小寻的
           上眼线在 make_rig.py 里显式写 0.5。 */
        p->lash_hold = zjson_num(zjson_obj_get(pj, "lash_hold"), 0.0);
        if (p->lash_hold < 0.0) p->lash_hold = 0.0;
        if (p->lash_hold > 0.95) p->lash_hold = 0.95;
        /* 眼眶开口：带 eye_aperture 标签的部件按 blink 纵向压扁（锚点写在下沿 =
           上眼皮往下合）。被它当遮罩裁切的眼白/眼球/高光会跟着被切掉 ——
           这才是真正的"眼睛闭上"，而不是把睁眼图整张淡出。 */
        /* bend_hold_above：形变平台线（画布 y）。
           躯干贴图的顶边其实是脖子/衣领，而 ROOT 曲线把最大形变给了顶边 ——
           衣领比它上面的头、下面的胸移动得都多，脖子处就出现横向滑移。
           写上颈线以后，颈线以上的行共用颈线处的形变量，和头完全同步。 */
        p->bend_hold_above = zjson_num(zjson_obj_get(pj, "bend_hold_above"), 0.0);
        /* 下平台：跟随件挂在下面时用（脚跟腿、手跟前臂）。
           以前没有它，只能靠把源贴图在切线以下整个裁掉来回避（G97）。 */
        p->bend_hold_below = zjson_num(zjson_obj_get(pj, "bend_hold_below"), 0.0);
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
        p->socket = -1;
        {
            const char *sid = zjson_str(zjson_obj_get(pj, "socket"), NULL);
            if (sid && *sid) {
                /* 挂 socket 的件：组和坐标都由挂点给，自己只写 dpos。
                   为什么不许同时写 pos：两套坐标并存时"谁赢"没有任何直觉答案，
                   而这类歧义在换装/换形态后才会以"配件漂了"的形式暴露出来。 */
                int si = find_socket(r, sid);
                const zjson *dp = zjson_obj_get(pj, "dpos");
                if (si < 0) {
                    zdiag_error(d, file, pj ? pj->line : 0, 0, buf,
                                "未知的挂点 '%s'（本 rig 声明了 %d 个：见 sockets 段；"
                                "挂点要写在 skeleton.json 的 kind:socket 骨上，再由生成器落到 rig）",
                                sid, r->nsockets);
                    return -1;
                }
                z_strlcpy(p->socket_id, sid, sizeof(p->socket_id));
                p->socket = si;
                p->group = r->sockets[si].group;
                p->pos[0] = r->sockets[si].pos[0];
                p->pos[1] = r->sockets[si].pos[1];
                if (dp && dp->type == ZJSON_ARR && zjson_count(dp) >= 2) {
                    p->pos[0] += zjson_num(zjson_at(dp, 0), 0.0);
                    p->pos[1] += zjson_num(zjson_at(dp, 1), 0.0);
                }
                /* 生成器会把算好的 pos 一起写进来（美术/QA 工具要读它），所以两处都在是常态。
                   但**位置只有一个来源**：挂点 + dpos。pos 与它对不上就是有一处过时了，
                   这种错不会在画面上立刻显形，只会在换装/换形态之后表现为"配件漂了"。 */
                {
                    const zjson *pp2 = zjson_obj_get(pj, "pos");
                    if (pp2 && pp2->type == ZJSON_ARR && zjson_count(pp2) >= 2) {
                        double px = zjson_num(zjson_at(pp2, 0), 0.0);
                        double py = zjson_num(zjson_at(pp2, 1), 0.0);
                        if (fabs(px - p->pos[0]) > 1.0 || fabs(py - p->pos[1]) > 1.0) {
                            zdiag_error(d, file, pj ? pj->line : 0, 0, buf,
                                "部件 '%s' 的 pos [%.1f,%.1f] 与挂点 '%s' 给出的 "
                                "[%.1f,%.1f] 不一致：挂 socket 的件位置由挂点决定，"
                                "pos 只能写同一个值（要偏移就写 dpos）",
                                p->id, px, py, sid, p->pos[0], p->pos[1]);
                            return -1;
                        }
                    }
                }
            } else {
                const char *gid = zjson_str(zjson_obj_get(pj, "group"), "root");
                p->group = find_group(r, gid);
                if (p->group < 0) {
                    zdiag_error(d, file, pj ? pj->line : 0, 0, buf, "未知的组 '%s'", gid);
                    return -1;
                }
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

/* 挂点表（T66.19 / S4）：sockets 是 rig 级的命名位置，配件按名字挂上来。
   ┌ 为什么要有它 ────────────────────────────────────────────────
   │ 配件的坐标现在只能写死画布数字。换装换了躯干、换形态换了画布，那个数字就过期，
   │ 表现是"耳饰 / 腕带漂到脸外面"。挂点把坐标收进**骨架**（pivot 级别的东西），
   │ 配件只写名字 + 偏移 ⇒ 换装/换形态/换角色都不用重摆。
   │ 契约面：skeleton.json 里 kind:socket 的骨 + 一根父骨；生成器把父骨（组）的 pivot
   │ 和算出来的位置落进 rig 的 sockets 段。引擎不认识"语义"，只认 id → (组, 坐标)。
   └──────────────────────────────────────────────────────────── */
static int load_sockets(zrig *r, const zjson *js, zdiag *d, const char *file)
{
    size_t i, n = zjson_count(js);
    if (!js) return 0;                     /* 可选段：老 rig 没有 sockets 照跑 */
    if (js->type != ZJSON_OBJ) {
        zdiag_error(d, file, js->line, 0, "sockets", "期望 object");
        return -1;
    }
    for (i = 0; i < n; ++i) {
        const char *sid = zjson_key_at(js, i);
        const zjson *sj = zjson_at(js, i);
        const zjson *gp = zjson_obj_get(sj, "group");
        const zjson *pp = zjson_obj_get(sj, "pos");
        char path[256];
        const char *gid;
        int gi;
        if (r->nsockets >= ZRIG_MAX_SOCKETS) {
            zdiag_error(d, file, js->line, 0, "sockets",
                        "挂点超过上限 %d（要更多就改大 ZRIG_MAX_SOCKETS，不许静默丢）",
                        ZRIG_MAX_SOCKETS);
            return -1;
        }
        z_snprintf(path, sizeof(path), "sockets.%s", sid);
        gid = zjson_str(gp, NULL);
        if (!gid || !*gid) {
            zdiag_error(d, file, sj ? sj->line : 0, 0, path,
                        "挂点必须写 group（挂在哪根骨上）");
            return -1;
        }
        gi = find_group(r, gid);
        if (gi < 0) {
            zdiag_error(d, file, sj ? sj->line : 0, 0, path,
                        "挂点指向的组 '%s' 不存在（挂点只能挂在已有的骨上）", gid);
            return -1;
        }
        if (!pp || pp->type != ZJSON_ARR || zjson_count(pp) < 2) {
            zdiag_error(d, file, sj ? sj->line : 0, 0, path,
                        "挂点必须写 pos [x, y]（画布坐标）");
            return -1;
        }
        z_strlcpy(r->sockets[r->nsockets].id, sid, sizeof(r->sockets[r->nsockets].id));
        r->sockets[r->nsockets].group = gi;
        r->sockets[r->nsockets].pos[0] = zjson_num(zjson_at(pp, 0), 0.0);
        r->sockets[r->nsockets].pos[1] = zjson_num(zjson_at(pp, 1), 0.0);
        r->nsockets++;
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
/* 网格形变器（A5，≈ Live2D 的 ワープデフォーマ）+ 变形器树（第六十三问 P0）：
   "deformers":[{ "id":"ahoge_wave", "part":"hair_ahoge", "cols":2, "rows":3,
                  "points":[{"c":1,"r":0,"dx":6,"dy":-2}, ...] }]
   points 里写的是 **amount=1 时该控制点挪多少源图像素**；没写到的控制点不动。
   amount 由动作通道（target 写形变器 id，param 写 amount）或参数 binds 写入。

   第六十三问新增三种字段（全部可选，老 rig 逐字节不变）：
     "parent"  父形变器 id（必须先声明）→ 组成 part → warp → rotate → root 的链
     "pivot"   节点的变换中心（画布坐标）；dx/dy/rot_deg/sx/sy 由通道/绑定写入
     "param" + "keys"  逐顶点参数驱动（keyform）：按参数值在几组控制点位移之间插值
   三者互不冲突：一个节点可以既是网格、又有父节点、又由参数驱动。

   keyform 的分段缓动（T66.11，写在**右端点**那一组 key 上，管 [q-1, q] 这一段）：
     "ease":"in" / "out" / "in_out" / "out_back" / "out_elastic" / "out_bounce"
     "ease":"step"                 阶梯：到了这组 key 才跳过去（≈ Live2D 階段）
     "ease":[x1,y1,x2,y2]          三次贝塞尔 timing curve（x 必须 ∈[0,1]）
   不写 = 线性 = 老行为。*/

/* 把一组 points 解析进 ox/oy（长度 npts）。idx 越界、点重复都报错。 */
static int parse_deform_points(const zjson *pts, int cols, int rows, double *ox, double *oy,
                               const char *id, zdiag *d, const char *file, const char *what)
{
    size_t k, np = pts ? zjson_count((zjson *)pts) : 0;
    int seen[ZRIG_MAX_DEFPTS];
    int npts = (cols + 1) * (rows + 1);
    memset(seen, 0, sizeof(seen));
    for (k = 0; k < np; ++k) {
        const zjson *pj = zjson_at((zjson *)pts, k);
        int cc = (int)zjson_int(zjson_obj_get((zjson *)pj, "c"), -1);
        int rr = (int)zjson_int(zjson_obj_get((zjson *)pj, "r"), -1);
        int idx;
        if (cc < 0 || cc > cols || rr < 0 || rr > rows) {
            zdiag_error(d, file, pj ? pj->line : 0, 0, "deformers",
                        "形变器 '%s'%s的控制点 (c=%d,r=%d) 越界（网格是 %d×%d，"
                        "控制点下标 0..%d / 0..%d）",
                        id, what, cc, rr, cols, rows, cols, rows);
            return -1;
        }
        idx = rr * (cols + 1) + cc;
        /* 同一个控制点写两次 = 作者以为会叠加，实际后一条悄悄盖掉前一条。报错。 */
        if (seen[idx]) {
            zdiag_error(d, file, pj ? pj->line : 0, 0, "deformers",
                        "形变器 '%s'%s的控制点 (c=%d,r=%d) 写了两次（同一控制点只能写一次）",
                        id, what, cc, rr);
            return -1;
        }
        seen[idx] = 1;
        if (idx >= 0 && idx < npts) {
            ox[idx] = zjson_num(zjson_obj_get((zjson *)pj, "dx"), 0.0);
            oy[idx] = zjson_num(zjson_obj_get((zjson *)pj, "dy"), 0.0);
        }
    }
    return 0;
}

static int load_deformers(zrig *r, const zjson *jd, zdiag *d, const char *file)
{
    size_t i, n;
    if (!jd) return 0;
    if (!zjson_is(jd, ZJSON_ARR)) {
        zdiag_error(d, file, jd->line, 0, "deformers", "deformers 应是数组");
        return -1;
    }
    n = zjson_count(jd);
    /* 超了报错，不静默截断（老代码是 `i < n && ndeforms < MAX` —— 第 33 张网格会
       静默消失，画面只是"少了一点摆动"，没人查得出来）。 */
    for (i = 0; i < n; ++i) {
        if (r->ndeforms >= ZRIG_MAX_DEFORMS) {
            zdiag_error(d, file, jd->line, 0, "deformers",
                        "网格/变形器超过上限 %d（超出的会被丢掉，必须改大 "
                        "ZRIG_MAX_DEFORMS 而不是让它静默截断）", ZRIG_MAX_DEFORMS);
            return -1;
        }
        const zjson *dj = zjson_at((zjson *)jd, i);
        const zjson *pts, *keys;
        zdeform *g;
        const char *id = zjson_str(zjson_obj_get((zjson *)dj, "id"), NULL);
        const char *part = zjson_str(zjson_obj_get((zjson *)dj, "part"), NULL);
        const char *parent = zjson_str(zjson_obj_get((zjson *)dj, "parent"), NULL);
        const char *kparam = zjson_str(zjson_obj_get((zjson *)dj, "param"), NULL);
        g = &r->deforms[r->ndeforms];
        memset(g, 0, sizeof(*g));
        g->part = -1;
        g->parent = -1;
        g->param = -1;
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
        if (part && g->part < 0) {
            zdiag_error(d, file, dj ? dj->line : 0, 0, "deformers",
                        "形变器 '%s' 的 part '%s' 不存在", id, part);
            return -1;
        }
        if (part) z_strlcpy(g->part_id, part, sizeof(g->part_id));
        /* —— 树：parent 必须先声明（和 groups.parent 同口径）—— */
        g->parent = -1;
        if (parent && *parent) {
            int pi = find_deform(r, parent);
            if (pi < 0) {
                zdiag_error(d, file, dj ? dj->line : 0, 0, "deformers",
                            "形变器 '%s' 的 parent '%s' 未定义（父节点必须先声明）",
                            id, parent);
                return -1;
            }
            g->parent = pi;
            z_strlcpy(g->parent_id, parent, sizeof(g->parent_id));
        }
        /* 纯变换节点（没有 part、没有网格）要么做别人的 parent，要么被部件的
           "deformer" 点名；两样都没有 = 写了但谁也影响不到，必须当场报错。
           （部件在形变器之前加载，所以这里能直接查到 deform_id。） */
        if (!part && !parent) {
            int referenced = 0, k;
            for (k = 0; k < r->nparts; ++k) {
                if (r->parts[k].deform_id[0] && z_streq(r->parts[k].deform_id, id)) {
                    referenced = 1;
                    break;
                }
            }
            if (!referenced) {
                zdiag_error(d, file, dj ? dj->line : 0, 0, "deformers",
                            "形变器 '%s' 既没有 part 也没有 parent：它影响不到任何部件"
                            "（纯变换节点要么做别人的 parent，要么被部件的 \"deformer\" 点名）",
                            id);
                return -1;
            }
        }
        read_pair(zjson_obj_get((zjson *)dj, "pivot"), r->origin[0], r->origin[1], g->pivot);
        g->sx = 1.0;
        g->sy = 1.0;
        g->cols = (int)zjson_int(zjson_obj_get((zjson *)dj, "cols"), 2);
        g->rows = (int)zjson_int(zjson_obj_get((zjson *)dj, "rows"), 2);
        if (g->cols < 1 || g->rows < 1 || g->cols > 16 || g->rows > 16) {
            zdiag_error(d, file, dj ? dj->line : 0, 0, "deformers",
                        "形变器 '%s' 的 cols/rows 要在 1~16（实为 %d×%d）",
                        id, g->cols, g->rows);
            return -1;
        }
        g->kf_np = (g->cols + 1) * (g->rows + 1);
        if (g->kf_np > ZRIG_MAX_DEFPTS) {
            zdiag_error(d, file, dj ? dj->line : 0, 0, "deformers",
                        "形变器 '%s' 的控制点 %d 个，超过上限 %d",
                        id, g->kf_np, ZRIG_MAX_DEFPTS);
            return -1;
        }
        if (g->part >= 0) {
            /* 同一个部件上的多张网格要逐点相加（裙摆 = 横摆 + 纵摆两张），
               尺寸不一样就加不起来。与其在渲染里静默丢掉一张，不如这里就拦住。 */
            int q;
            for (q = 0; q < r->ndeforms; ++q) {
                if (r->deforms[q].part != g->part) continue;
                if (r->deforms[q].cols == g->cols && r->deforms[q].rows == g->rows) continue;
                zdiag_error(d, file, dj ? dj->line : 0, 0, "deformers",
                            "形变器 '%s' 和同一部件上的 '%s' 网格尺寸不一样"
                            "（%dx%d vs %dx%d）：同部件的多张网格要逐点相加，必须同尺寸",
                            id, r->deforms[q].id, g->cols, g->rows,
                            r->deforms[q].cols, r->deforms[q].rows);
                return -1;
            }
        }
        keys = zjson_obj_get((zjson *)dj, "keys");
        if (keys) {
            /* —— keyform：逐顶点参数驱动 —— */
            size_t nk, q;
            if (!kparam || !*kparam) {
                zdiag_error(d, file, dj ? dj->line : 0, 0, "deformers",
                            "形变器 '%s' 写了 keys 就必须写 param（keys 要用某个参数来插值）", id);
                return -1;
            }
            z_strlcpy(g->kf_param_id, kparam, sizeof(g->kf_param_id));
            /* keyform 的迟滞（可选）：和 bind.lag 同一个语义、同一个上限 */
            g->kf_lag = zjson_num(zjson_obj_get((zjson *)dj, "lag"), 0.0);
            if (g->kf_lag < 0.0 || g->kf_lag > ZRIG_LAG_MAX) {
                zdiag_error(d, file, dj ? dj->line : 0, 0, "deformers",
                            "形变器 '%s' 的 lag 要在 0~%.2f 秒之间（写的是 %.3f）",
                            id, (double)ZRIG_LAG_MAX, g->kf_lag);
                return -1;
            }
            if (g->kf_lag > 0.0) r->lag_used = 1;
            if (!zjson_is(keys, ZJSON_ARR) || zjson_count((zjson *)keys) < 2) {
                zdiag_error(d, file, dj ? dj->line : 0, 0, "deformers",
                            "形变器 '%s' 的 keys 至少要 2 组（一组定不了插值）", id);
                return -1;
            }
            nk = zjson_count((zjson *)keys);
            if (nk > ZRIG_MAX_DEFKF) {
                zdiag_error(d, file, dj ? dj->line : 0, 0, "deformers",
                            "形变器 '%s' 的 keys %d 组超过上限 %d",
                            id, (int)nk, ZRIG_MAX_DEFKF);
                return -1;
            }
            g->kf_d = (double *)calloc(nk * (size_t)g->kf_np * 2, sizeof(double));
            if (!g->kf_d) {
                zdiag_error(d, file, dj ? dj->line : 0, 0, "deformers",
                            "形变器 '%s' 的 keyform 内存分配失败（%d 组 × %d 点）",
                            id, (int)nk, g->kf_np);
                return -1;
            }
            for (q = 0; q < nk; ++q) {
                const zjson *kj = zjson_at((zjson *)keys, q);
                double tx[ZRIG_MAX_DEFPTS], ty[ZRIG_MAX_DEFPTS];
                int t;
                char what[64];
                double v = zjson_num(zjson_obj_get((zjson *)kj, "v"), 0.0);
                if (q > 0 && v <= g->kf_v[q - 1]) {
                    zdiag_error(d, file, kj ? kj->line : 0, 0, "deformers",
                                "形变器 '%s' 的 keys 参数值必须严格递增（第 %d 组 %.3f 不大于上一组 %.3f）",
                                id, (int)q + 1, v, g->kf_v[q - 1]);
                    free(g->kf_d);          /* 这个形变器还没计入 ndeforms，zrig_free 看不到它 */
                    g->kf_d = NULL;
                    return -1;
                }
                g->kf_v[q] = v;
                memset(tx, 0, sizeof(tx));
                memset(ty, 0, sizeof(ty));
                z_snprintf(what, sizeof(what), " 的第 %d 组 key", (int)q + 1);
                if (parse_deform_points(zjson_obj_get((zjson *)kj, "points"),
                                        g->cols, g->rows, tx, ty, id, d, file, what) != 0) {
                    free(g->kf_d);
                    g->kf_d = NULL;
                    return -1;
                }
                for (t = 0; t < g->kf_np; ++t) {
                    if (q == 0) {
                        /* 第 0 组是**绝对**位移：直接写进 ox/oy（和老的 amount 通道同址） */
                        g->ox[t] = tx[t];
                        g->oy[t] = ty[t];
                    } else {
                        /* 其余是相对第 0 组的增量，按 [组][点][xy] 排 */
                        size_t base = ((size_t)q * (size_t)g->kf_np + (size_t)t) * 2;
                        g->kf_d[base]     = tx[t] - g->ox[t];
                        g->kf_d[base + 1] = ty[t] - g->oy[t];
                    }
                }
                /* —— 分段缓动（T66.11）：写在**右端点**这组 key 上，管 [q-1, q] 这一段。
                   三种写法：名字（linear/in/out/in_out/out_back/out_elastic/out_bounce）、
                   名字 "step"（阶梯）、四个数（三次贝塞尔 x1,y1,x2,y2）。不写 = 线性。 */
                {
                    const zjson *ej = zjson_obj_get((zjson *)kj, "ease");
                    if (ej) {
                        if (q == 0) {
                            zdiag_error(d, file, kj ? kj->line : 0, 0, "deformers",
                                        "形变器 '%s' 的第 1 组 key 写了 ease：它前面没有段可管"
                                        "（缓动写在**右端点**那一组 key 上）", id);
                            free(g->kf_d); g->kf_d = NULL;
                            return -1;
                        }
                        if (zjson_is(ej, ZJSON_STR)) {
                            const char *en = zjson_str(ej, "");
                            static const char *const ok_names[] = {
                                "linear", "in", "out", "in_out",
                                "out_back", "out_elastic", "out_bounce", NULL
                            };
                            int i2, hit = 0;
                            if (z_streq(en, "step")) {
                                g->kf_step[q] = 1;
                            } else {
                                for (i2 = 0; ok_names[i2]; ++i2)
                                    if (z_streq(en, ok_names[i2])) { hit = 1; break; }
                                if (!hit) {
                                    zdiag_error(d, file, ej->line, 0, "deformers",
                                                "形变器 '%s' 第 %d 组 key 的 ease '%s' 不认识"
                                                "（可用：linear/in/out/in_out/out_back/"
                                                "out_elastic/out_bounce/step，或四个数的贝塞尔）",
                                                id, (int)q + 1, en);
                                    free(g->kf_d); g->kf_d = NULL;
                                    return -1;
                                }
                                g->kf_ease[q] = z_ease_from_name(en);
                            }
                        } else if (zjson_is(ej, ZJSON_ARR) && zjson_count(ej) == 4) {
                            int i2;
                            for (i2 = 0; i2 < 4; ++i2) g->kf_bez[q][i2] = zjson_num(zjson_at(ej, (size_t)i2), 0.0);
                            /* x1/x2 出界会让 x(t) 不单调，二分就解不出唯一解 —— 必须当错，
                               不许"悄悄夹一下"，否则画面只是在对不上的地方。 */
                            if (g->kf_bez[q][0] < 0.0 || g->kf_bez[q][0] > 1.0 ||
                                g->kf_bez[q][2] < 0.0 || g->kf_bez[q][2] > 1.0) {
                                zdiag_error(d, file, ej->line, 0, "deformers",
                                            "形变器 '%s' 第 %d 组 key 的贝塞尔 x 控制点 %.3f/%.3f"
                                            " 必须在 [0,1]（否则 x(t) 不单调）",
                                            id, (int)q + 1, g->kf_bez[q][0], g->kf_bez[q][2]);
                                free(g->kf_d); g->kf_d = NULL;
                                return -1;
                            }
                            g->kf_bez_on[q] = 1;
                        } else {
                            zdiag_error(d, file, ej->line, 0, "deformers",
                                        "形变器 '%s' 第 %d 组 key 的 ease 要么是名字（字符串），"
                                        "要么是四个数的数组 [x1,y1,x2,y2]，现在是 %s",
                                        id, (int)q + 1, zjson_type_name(zjson_type_of(ej)));
                            free(g->kf_d); g->kf_d = NULL;
                            return -1;
                        }
                    }
                }
            }
            g->nkf = (int)nk;
        } else {
            pts = zjson_obj_get((zjson *)dj, "points");
            if (parse_deform_points(pts, g->cols, g->rows, g->ox, g->oy,
                                    id, d, file, "") != 0) return -1;
        }
        r->ndeforms++;
    }
    return 0;
}

/* param_find 的函数体在下面（参数层那一节），physics 的 input 要先用到它 *//* param_find 的函数体在下面（参数层那一节），physics 的 input 要先用到它 */
static int param_find(const zrig *r, const char *id);
static const char *param_alias(const char *id);

static int load_physics(zrig *r, const zjson *jp, zdiag *d, const char *file)
{
    size_t i, n = zjson_count(jp);
    if (!jp) return 0;
    if (jp->type != ZJSON_ARR) {
        zdiag_error(d, file, jp->line, 0, "physics", "期望 array");
        return -1;
    }
    /* ⚠ 超了必须报错，不能静默丢。
       2026-10-14 实测：上限曾是 12，而 rig 里已经声明到 13 条 ——
       第 13 条 back_x（后发摆动）**一直被悄悄丢掉**，没有任何报错，
       谁也没发现它是哑的。再加一条之后 skirt_y 也跟着掉了，
       单测「裙摆纵摆」才终于红出来。
       同类坑：ZRIG_MAX_PARAMS 也撞过（48 → 64）。 */
    if (n > ZRIG_MAX_PHYS) {
        zdiag_error(d, file, jp->line, 0, "physics",
                    "物理条数 %d 超过上限 %d（超出的会被丢掉，必须改大 "
                    "ZRIG_MAX_PHYS 而不是让它静默截断）",
                    (int)n, ZRIG_MAX_PHYS);
        return -1;
    }
    for (i = 0; i < n; ++i) {
        if (r->nphys >= ZRIG_MAX_PHYS) {
            zdiag_error(d, file, jp->line, 0, "physics",
                        "物理条数超过上限 %d（超出的会被丢掉，必须改大 ZRIG_MAX_PHYS）",
                        ZRIG_MAX_PHYS);
            return -1;
        }
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
        /* input: [{"param":"ParamBodyAngleX","weight":1.0}, ...]
           有它就不看 driver（官方 physics3 也是只有 Input 一种来源）。 */
        ph->n_in = 0;
        {
            const zjson *ij = zjson_obj_get(pj, "input");
            if (ij && ij->type == ZJSON_ARR) {
                int k, n = (int)zjson_count((zjson *)ij);
                if (n > 4) {
                    zdiag_error(d, file, pj ? pj->line : 0, 0, path,
                                "input 最多 4 项（给了 %d 项）", n);
                    return -1;
                }
                for (k = 0; k < n; ++k) {
                    const zjson *one = zjson_at(ij, k);
                    const char *pnm = zjson_str(zjson_obj_get(one, "param"), NULL);
                    int idx = pnm ? param_find(r, pnm) : -1;
                    if (idx < 0) {
                        zdiag_error(d, file, one ? one->line : 0, 0, path,
                                    "input[%d] 的参数 '%s' 不存在", k, pnm ? pnm : "(缺)");
                        return -1;
                    }
                    ph->in_param[ph->n_in] = idx;
                    ph->in_weight[ph->n_in] = zjson_num(zjson_obj_get(one, "weight"), 1.0);
                    ph->n_in++;
                }
            }
        }
        ph->driver = drv ? find_group(r, drv) : -1;
        ph->driver_phys = -1;
        if (ph->driver < 0 && drv) {
            /* driver 不是组，就看看是不是上一段摆（多段摆链） */
            int q;
            for (q = 0; q < r->nphys; ++q)
                if (strcmp(r->phys[q].id, drv) == 0) { ph->driver_phys = q; break; }
        }
        if (ph->driver < 0 && ph->driver_phys < 0 && ph->n_in == 0) {
            zdiag_error(d, file, pj ? pj->line : 0, 0, path,
                        "没有输入：driver '%s' 既不是组，也不是**写在它前面**的另一条 physics"
                        "（多段摆要按根→梢的顺序声明），也没给 input 参数数组",
                        drv ? drv : "(缺)");
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
        /* T66.11c：和 physics2 一样，param 写 "ParamXxx" 且没有 deformer ⇒ 写**命名参数**。
           旧摆链（侧发/后发/裙摆）就靠这条把"物理 → 参数 → keyform 网格"接起来；
           没有它的话，这些网格一改 keyform 就丢掉物理跟随（G66.13）。 */
        ph->pparam = -1;
        if (ph->deform < 0 && pn && strncmp(pn, "Param", 5) == 0) {
            ph->pparam = param_find(r, param_alias(pn));
            if (ph->pparam < 0) {
                zdiag_error(d, file, pj ? pj->line : 0, 0, path,
                            "param '%s' 不在参数表里（params 段要先声明它）", pn);
                return -1;
            }
        }
        if (ph->deform >= 0) ph->param = P_AMOUNT;
        else if (ph->pparam >= 0) ph->param = P_AMOUNT;   /* 占位：写参数时不看通道 */
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

/* physics2：物理 2.0 的摆链（T47.2）。可选，没写就一条都没有。

   rig.json 的样子（四个旋钮的名字**照抄官方编辑器**，DC70）：
     "physics2": [{
       "id": "longhair2", "part": "acc_hair_long", "driver": "head",
       "angle_input": [{"param":"ParamAngleZ","weight":0.5}],
       "input":       [{"param":"ParamBreath","wy":-0.8}],
       "particles": [{"radius":0},                                   // [0] 是根，不积分
                     {"radius":72,"mobility":0.95,"delay":0.9,"acceleration":1.0}, ...],
       "outputs":   [{"particle":1,"param":"bend_x","curve":"root","scale":2.6,"max":16},
                     {"particle":3,"deformer":"longhair_tip","scale":0.05,"max":1.0}]
     }]

   注意 driver 和 input 是**叠加**关系，不像旧 physics 那样二选一：
   driver 把"这个组这一帧把根点带着走了多少像素"喂进来（动作、视线跟随、呼吸
   全都自动算在内，不用一条条列参数），input 再补那些**只改形状不改组矩阵**的
   参数（典型是躯干弯曲，弯曲是非仿射的，根本不在组矩阵里）。 */
static int load_physics2(zrig *r, const zjson *jp, zdiag *d, const char *file)
{
    size_t i, n = zjson_count(jp);
    if (!jp) return 0;
    if (jp->type != ZJSON_ARR) {
        zdiag_error(d, file, jp->line, 0, "physics2", "期望 array");
        return -1;
    }
    if (n > ZRIG_MAX_PHYS2) {
        zdiag_error(d, file, jp->line, 0, "physics2",
                    "摆链条数 %d 超过上限 %d（必须改大 ZRIG_MAX_PHYS2，"
                    "不能让它静默截断）", (int)n, ZRIG_MAX_PHYS2);
        return -1;
    }
    for (i = 0; i < n; ++i) {
        const zjson *cj = zjson_at(jp, i);
        zp2chain *c = &r->p2[r->np2];
        const char *pid = zjson_str(zjson_obj_get(cj, "part"), NULL);
        const char *drv = zjson_str(zjson_obj_get(cj, "driver"), NULL);
        const zjson *parts_j = zjson_obj_get(cj, "particles");
        const zjson *outs_j  = zjson_obj_get(cj, "outputs");
        char path[128];
        int k, np;
        memset(c, 0, sizeof(*c));
        z_strlcpy(c->id, zjson_str(zjson_obj_get(cj, "id"), pid ? pid : "chain"),
                  sizeof(c->id));
        z_snprintf(path, sizeof(path), "physics2[%s]", c->id);
        c->part = pid ? find_part(r, pid) : -1;
        if (pid && c->part < 0) {
            zdiag_error(d, file, cj ? cj->line : 0, 0, path, "part '%s' 不存在", pid);
            return -1;
        }
        c->driver = drv ? find_group(r, drv) : -1;
        if (drv && c->driver < 0) {
            zdiag_error(d, file, cj ? cj->line : 0, 0, path, "driver '%s' 不是组", drv);
            return -1;
        }
        /* 像素输入：{"param":..,"wx":..,"wy":..}；只写 weight 就等同 wx=wy=weight */
        {
            const zjson *ij = zjson_obj_get(cj, "input");
            int m = ij ? (int)zjson_count((zjson *)ij) : 0;
            if (m > 4) {
                zdiag_error(d, file, cj ? cj->line : 0, 0, path,
                            "input 最多 4 项（给了 %d 项）", m);
                return -1;
            }
            for (k = 0; k < m; ++k) {
                const zjson *one = zjson_at(ij, k);
                const char *pnm = zjson_str(zjson_obj_get(one, "param"), NULL);
                int idx = pnm ? param_find(r, pnm) : -1;
                double w = zjson_num(zjson_obj_get(one, "weight"), 0.0);
                if (idx < 0) {
                    zdiag_error(d, file, one ? one->line : 0, 0, path,
                                "input[%d] 的参数 '%s' 不存在", k, pnm ? pnm : "(缺)");
                    return -1;
                }
                c->in_param[c->n_in] = idx;
                c->in_wx[c->n_in] = zjson_num(zjson_obj_get(one, "wx"), w);
                c->in_wy[c->n_in] = zjson_num(zjson_obj_get(one, "wy"), w);
                c->n_in++;
            }
        }
        /* 角度输入（官方 Input[].Type = Angle），单位是度 */
        {
            const zjson *ij = zjson_obj_get(cj, "angle_input");
            int m = ij ? (int)zjson_count((zjson *)ij) : 0;
            if (m > 4) {
                zdiag_error(d, file, cj ? cj->line : 0, 0, path,
                            "angle_input 最多 4 项（给了 %d 项）", m);
                return -1;
            }
            for (k = 0; k < m; ++k) {
                const zjson *one = zjson_at(ij, k);
                const char *pnm = zjson_str(zjson_obj_get(one, "param"), NULL);
                int idx = pnm ? param_find(r, pnm) : -1;
                if (idx < 0) {
                    zdiag_error(d, file, one ? one->line : 0, 0, path,
                                "angle_input[%d] 的参数 '%s' 不存在", k, pnm ? pnm : "(缺)");
                    return -1;
                }
                c->ain_param[c->n_ain] = idx;
                c->ain_w[c->n_ain] = zjson_num(zjson_obj_get(one, "weight"), 1.0);
                c->n_ain++;
            }
        }
        /* 粒子：[0] 是根（不积分），后面每个都要有正的 radius */
        np = parts_j ? (int)zjson_count((zjson *)parts_j) : 0;
        if (np < 2) {
            zdiag_error(d, file, cj ? cj->line : 0, 0, path,
                        "particles 至少要 2 个（[0] 是根点），给了 %d 个", np);
            return -1;
        }
        if (np > ZPHYS2_MAX_PARTICLES) {
            zdiag_error(d, file, cj ? cj->line : 0, 0, path,
                        "particles %d 个超过上限 %d", np, ZPHYS2_MAX_PARTICLES);
            return -1;
        }
        zphys2_init(&c->ch, np);
        for (k = 1; k < np; ++k) {
            const zjson *one = zjson_at(parts_j, (size_t)k);
            double rad = zjson_num(zjson_obj_get(one, "radius"), 0.0);
            double mob = zjson_num(zjson_obj_get(one, "mobility"), 0.95);
            double dly = zjson_num(zjson_obj_get(one, "delay"), 1.0);
            double acc = zjson_num(zjson_obj_get(one, "acceleration"), 1.0);
            if (rad <= 0.0) {
                zdiag_error(d, file, one ? one->line : 0, 0, path,
                            "particles[%d].radius 必须 > 0（摆长 0 = 这一节不会动）", k);
                return -1;
            }
            /* 官方编辑器把「揺れやすさ」限在 0.7~0.99：低于 0.7 几乎不晃，
               到 1.0 就不衰减了（永动机）。越界直接报错，不要悄悄夹。 */
            if (mob < 0.7 || mob > 0.99) {
                zdiag_error(d, file, one ? one->line : 0, 0, path,
                            "particles[%d].mobility=%.3f 越界（官方编辑器的区间是 0.7~0.99）",
                            k, mob);
                return -1;
            }
            zphys2_set(&c->ch, k, rad, mob, dly, acc);
        }
        /* 输出 */
        c->nout = 0;
        {
            int m = outs_j ? (int)zjson_count((zjson *)outs_j) : 0;
            if (m < 1) {
                zdiag_error(d, file, cj ? cj->line : 0, 0, path,
                            "outputs 不能为空（没有输出 = 这条链白算）");
                return -1;
            }
            if (m > ZRIG_MAX_P2_OUT) {
                zdiag_error(d, file, cj ? cj->line : 0, 0, path,
                            "outputs %d 条超过上限 %d", m, ZRIG_MAX_P2_OUT);
                return -1;
            }
            for (k = 0; k < m; ++k) {
                const zjson *one = zjson_at(outs_j, (size_t)k);
                const char *opid = zjson_str(zjson_obj_get(one, "part"), NULL);
                const char *dfm  = zjson_str(zjson_obj_get(one, "deformer"), NULL);
                const char *pn   = zjson_str(zjson_obj_get(one, "param"), "bend_x");
                const char *cv   = zjson_str(zjson_obj_get(one, "curve"), "root");
                zp2out *o = &c->out[c->nout];
                memset(o, 0, sizeof(*o));
                o->particle = (int)zjson_num(zjson_obj_get(one, "particle"), (double)(np - 1));
                if (o->particle < 1 || o->particle >= np) {
                    zdiag_error(d, file, one ? one->line : 0, 0, path,
                                "outputs[%d].particle=%d 越界（这条链是 1..%d）",
                                k, o->particle, np - 1);
                    return -1;
                }
                o->part = opid ? find_part(r, opid) : c->part;
                if (opid && o->part < 0) {
                    zdiag_error(d, file, one ? one->line : 0, 0, path,
                                "outputs[%d].part '%s' 不存在", k, opid);
                    return -1;
                }
                o->deform = dfm ? find_deform(r, dfm) : -1;
                if (dfm && o->deform < 0) {
                    zdiag_error(d, file, one ? one->line : 0, 0, path,
                                "outputs[%d].deformer '%s' 不存在", k, dfm);
                    return -1;
                }
                /* T66.11c：写出目标是**命名参数**（Live2D 的正解：物理推参数，网格跟参数）。
                   认法：param 以 "Param" 开头就是参数 id，否则按老的通道名（dx/dy/bend_x…）解析。
                   为什么必须区分开：同名位置以前只能写部件通道，而 keyform 只读参数 ——
                   物理写不到参数，网格一改 keyform 就再也推不动（G66.13）。 */
                o->pparam = -1;
                if (!dfm && !opid && pn && strncmp(pn, "Param", 5) == 0) {
                    o->pparam = param_find(r, param_alias(pn));
                    if (o->pparam < 0) {
                        zdiag_error(d, file, one ? one->line : 0, 0, path,
                                    "outputs[%d].param '%s' 不在参数表里（params 段要先声明它）",
                                    k, pn);
                        return -1;
                    }
                }
                if (o->deform >= 0) {
                    o->param = P_AMOUNT;
                    if (r->deforms[o->deform].nkf > 0) {
                        zdiag_error(d, file, one ? one->line : 0, 0, path,
                                    "outputs[%d] 把物理写到形变器 '%s' 的 amount，"
                                    "但这件有 keyform（keys）→ 写了也不动（同 bind 的规矩）",
                                    k, r->deforms[o->deform].id);
                        return -1;
                    }
                }
                else if (o->pparam < 0 && parse_param(pn, &o->param) != 0) {
                    zdiag_error(d, file, one ? one->line : 0, 0, path,
                                "outputs[%d].param 非法：%s", k, pn);
                    return -1;
                }
                if (o->deform < 0 && o->part < 0 && o->pparam < 0) {
                    zdiag_error(d, file, one ? one->line : 0, 0, path,
                                "outputs[%d] 既没有 part、deformer，也没有 Param 目标，没地方写", k);
                    return -1;
                }
                o->curve = BEND_ROOT;
                if (z_streq(cv, "tip")) o->curve = BEND_TIP;
                else if (z_streq(cv, "sine")) o->curve = BEND_SINE;
                else if (z_streq(cv, "linear")) o->curve = BEND_LINEAR;
                o->inverted = (int)zjson_num(zjson_obj_get(one, "inverted"), 0.0) != 0;
                o->scale = zjson_num(zjson_obj_get(one, "scale"), 1.0);
                o->max   = zjson_num(zjson_obj_get(one, "max"), 10.0);
                if (o->max <= 0.0) o->max = 10.0;
                c->nout++;
            }
        }
        /* 输入限幅的默认值：模长上限 = 半条链长、速度上限 300px/s。
           为什么要有它，见 p2_input 的注释（官方靠 Normalization 天然有上限）。 */
        {
            double total = 0.0;
            for (k = 1; k < np; ++k) total += c->ch.p[k].radius;
            c->in_max  = zjson_num(zjson_obj_get(cj, "input_max"), total * 0.5);
            c->in_rate = zjson_num(zjson_obj_get(cj, "input_rate"), 300.0);
            if (c->in_max <= 0.0) c->in_max = total * 0.5;
            if (c->in_rate <= 0.0) c->in_rate = 300.0;
        }
        zphys2_reset(&c->ch, r->p2_gx, r->p2_gy);
        r->np2++;
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
    /* 痛苦闭眼（>_<）：官方标准参数表里没有这一项（只有 Smile），但它和笑眼是同一类东西
       ——闭着的眼的第三种形状（谷型 ∪ / 山型 ∩ / 倒 V ∧），所以口径完全照搬笑眼，
       包括"自己隐含闭眼"。素材见 tools/make_eye_closed_parts.py --variant pain。 */
    param_add_builtin(r, "ParamEyeLPain", "左眼 痛苦闭眼", 0.0, 1.0, 0.0, PBI_EYE_L_PAIN);
    param_add_builtin(r, "ParamEyeRPain", "右眼 痛苦闭眼", 0.0, 1.0, 0.0, PBI_EYE_R_PAIN);
    /* 瞪大眼：官方标准参数 ParamEyeLWide / ParamEyeRWide（0~1），
       存在的理由就是"ParamEyeOpen 的 1.0 只是常态睁开，再睁大要另给一个参数"。
       和笑眼/痛苦眼相反，它**不隐含闭眼** —— 眼是睁着的，只是睁得更开。 */
    param_add_builtin(r, "ParamEyeLWide", "左眼 瞪大", 0.0, 1.0, 0.0, PBI_EYE_L_WIDE);
    param_add_builtin(r, "ParamEyeRWide", "右眼 瞪大", 0.0, 1.0, 0.0, PBI_EYE_R_WIDE);
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
        z_utf8_trim(q->label);   /* 中文标签超长会被按字节切断，必须退回字符边界 */

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
            if (b->deform >= 0) {
                /* 绑到变形器节点：param 不写就是 amount（老行为，一张网格一个标量），
                   写了就写节点的哪个变换量（第六十三问 P0 的"每根骨头单独驱动"）。 */
                b->curve = BEND_ROOT;
                b->strips = 0;
                if (pn && *pn) {
                    if (parse_param(pn, &b->param) != 0 ||
                        b->param == P_BEND_X || b->param == P_BEND_Y) {
                        zdiag_error(d, file, bj ? bj->line : 0, 0, path,
                                    "绑到形变器的 param 只能是 dx/dy/sx/sy/rot_deg/amount"
                                    "（写了 '%s'）", pn);
                        return -1;
                    }
                } else {
                    b->param = P_AMOUNT;
                }
                /* keyform 那条路只读参数值，amount 根本不参与求值（deform_vertex_at 里
                   nkf>0 就直接 return 了）。这条绑定写进去等于石沉大海 —— 画面"该动的不动"，
                   锅还会甩给物理。宁可加载失败。 */
                if (b->param == P_AMOUNT && r->deforms[b->deform].nkf > 0) {
                    zdiag_error(d, file, bj ? bj->line : 0, 0, path,
                                "形变器 '%s' 有 keyform（写了 keys），绑定又给它写 amount："
                                "keyform 只由参数值驱动，这条绑定会被忽略（要跟物理走就把 keys 删掉）",
                                r->deforms[b->deform].id);
                    return -1;
                }
            }
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
            /* lag：这条绑定读的不是参数**此刻**的值，而是 lag 秒之前的值。
               动画教科书里「尾巴分段、每段比上一段延迟 2~3 帧」那条规矩
               （相位差 φ = 2πfΔt）在时域里的直接实现。
               为什么做在时域而不是直接写个相位偏移：相位偏移只对正弦成立，
               而自发抽动（tail_flick）是非周期的脉冲 —— 时域延迟对**任何**
               波形都对，一个字段同时管住慢摆和抽动。
               根和梢同相位推 = 僵硬的钟摆；错开之后形状在 C 形和 S 形之间
               来回变，这就是「柔软」的来源。 */
            b->lag = zjson_num(zjson_obj_get(bj, "lag"), 0.0);
            if (b->lag < 0.0 || b->lag > ZRIG_LAG_MAX) {
                zdiag_error(d, file, bj ? bj->line : 0, 0, path,
                            "bind.lag 要在 0~%.2f 秒之间（写的是 %.3f）",
                            (double)ZRIG_LAG_MAX, b->lag);
                return -1;
            }
            if (b->lag > 0.0) r->lag_used = 1;
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

/* 隐藏件（正在淡出的那张）该留多少不透明度。
   直接照搬 Live2D SDK 的 CubismPose::DoFade：Phi=0.5、BackOpacityThreshold=0.15。
   为什么不能用最朴素的 1-w：两张图各画一半时，合成覆盖率 = w + (1-w)² ，
   w=0.5 时只有 0.75 —— 中途会**透出 25% 的背景**，看起来像鞋突然变半透明。
   官方的做法是把隐藏件的不透明度抬起来，保证背景透出不超过 15%：
       a1 = 1-w ；若 (1-a1)(1-w) > 0.15 则 a1 = 1 - 0.15/(1-w)
   出处：https://docs.live2d.com/en/cubism-sdk-manual/pose/ */
double zrig_xfade_hidden(double w)
{
    const double phi = 0.5, back_thr = 0.15;
    double a1, rest;
    w = ZC_CLAMP(w, 0.0, 1.0);
    a1 = (w < phi) ? (w * (phi - 1.0) / phi + 1.0) : ((1.0 - w) * phi / (1.0 - phi));
    rest = 1.0 - w;
    if (rest > 1e-6 && (1.0 - a1) * rest > back_thr) a1 = 1.0 - back_thr / rest;
    return ZC_CLAMP(a1, 0.0, 1.0);
}

/* xfades：参数驱动的两张姿态图交叉淡化。结构见上面 zxfade 的注释。 */
static int load_xfades(zrig *r, const zjson *jx, zdiag *d, const char *file)
{
    size_t i, n;
    if (!jx) return 0;
    if (!zjson_is(jx, ZJSON_ARR)) {
        zdiag_error(d, file, jx->line, 0, "xfades", "xfades 应是数组");
        return -1;
    }
    n = zjson_count((zjson *)jx);
    for (i = 0; i < n; ++i) {
        const zjson *xj = zjson_at((zjson *)jx, i);
        const char *xid = zjson_str(zjson_obj_get((zjson *)xj, "id"), NULL);
        const char *pid = zjson_str(zjson_obj_get((zjson *)xj, "param"), NULL);
        const char *fid = zjson_str(zjson_obj_get((zjson *)xj, "from"), NULL);
        const char *tid = zjson_str(zjson_obj_get((zjson *)xj, "to"), NULL);
        const zjson *in = zjson_obj_get((zjson *)xj, "in");
        zxfade *x;
        int line = xj ? xj->line : 0;
        if (r->nxfades >= ZRIG_MAX_XFADE) {
            zdiag_error(d, file, line, 0, "xfades", "交叉淡化过多（上限 %d）", ZRIG_MAX_XFADE);
            return -1;
        }
        if (!xid || !pid || !fid || !tid) {
            zdiag_error(d, file, line, 0, "xfades", "id/param/from/to 四个都要写");
            return -1;
        }
        x = &r->xfades[r->nxfades];
        memset(x, 0, sizeof(*x));
        z_strlcpy(x->id, xid, sizeof(x->id));
        x->param = param_find(r, param_alias(pid));
        x->from = find_part(r, fid);
        x->to = find_part(r, tid);
        if (x->param < 0) {
            zdiag_error(d, file, line, 0, "xfades", "参数 '%s' 不存在", pid);
            return -1;
        }
        if (x->from < 0 || x->to < 0) {
            zdiag_error(d, file, line, 0, "xfades", "部件不存在：from='%s' to='%s'", fid, tid);
            return -1;
        }
        if (x->from == x->to) {
            zdiag_error(d, file, line, 0, "xfades", "from 和 to 是同一个部件");
            return -1;
        }
        x->in0 = 0.0; x->in1 = 1.0;
        if (in && zjson_is((zjson *)in, ZJSON_ARR) && zjson_count((zjson *)in) == 2) {
            x->in0 = zjson_num(zjson_at((zjson *)in, 0), 0.0);
            x->in1 = zjson_num(zjson_at((zjson *)in, 1), 1.0);
        }
        if (x->in1 - x->in0 < 1e-6) {
            zdiag_error(d, file, line, 0, "xfades", "in 区间必须是递增的两个数");
            return -1;
        }
        /* 开机先按参数默认值把权重摆好，免得第一帧闪一下 */
        x->w = ZC_CLAMP((r->params[x->param].vdef - x->in0) / (x->in1 - x->in0), 0.0, 1.0);
        r->nxfades++;
    }
    return 0;
}

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
            if (ps && !zjson_is(ps, ZJSON_ARR)) {
                zdiag_error(d, file, ej ? ej->line : 0, 0, path,
                            "档位 '%s' 的 parts 要写成数组", eid);
                return -1;
            }
            if (qn < 1 && !zjson_obj_get((zjson *)ej, "hide")) {
                /* 空 parts 只在"这一档靠藏别人成立"时才合法（例如 bob：
                   不加任何一束头发，但要把 twin/pony 藏掉的侧发留着）。
                   两者都没有的档位是个空壳，切过去画面不会有任何变化。 */
                zdiag_error(d, file, ej ? ej->line : 0, 0, path,
                            "档位 '%s' 既没有 parts 也没有 hide（空档位）", eid);
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
            /* hide：这一档生效时要藏起来的既有部件（本引擎扩展，见 pose_opacity）。
               可选；允许多个档位藏同一个部件（侧发被 twin 和 pony 同时点名）。 */
            {
                const zjson *hs = zjson_obj_get((zjson *)ej, "hide");
                size_t hq, hn = zjson_count((zjson *)hs);
                e->hid0 = r->nposehide;
                if (hs && !zjson_is(hs, ZJSON_ARR)) {
                    zdiag_error(d, file, ej ? ej->line : 0, 0, path,
                                "档位 '%s' 的 hide 要写成数组", eid);
                    return -1;
                }
                for (hq = 0; hs && hq < hn; ++hq) {
                    const char *hid = zjson_str(zjson_at((zjson *)hs, hq), NULL);
                    int hpi = hid ? find_part(r, hid) : -1;
                    if (hpi < 0) {
                        zdiag_error(d, file, ej ? ej->line : 0, 0, path,
                                    "档位 '%s' 的 hide 引用了不存在的部件 '%s'",
                                    eid, hid ? hid : "(空)");
                        return -1;
                    }
                    if (r->nposehide >= ZRIG_MAX_POSE_MEM) {
                        zdiag_error(d, file, ej ? ej->line : 0, 0, path,
                                    "hide 名单过长（上限 %d）", ZRIG_MAX_POSE_MEM);
                        return -1;
                    }
                    r->posehide[r->nposehide++] = hpi;
                    e->nhid++;
                }
            }
            r->nposeents++;
            g->nent++;
        }
        /* 默认档位：没写就取第一个。切换前所有非当前档都是全透明。
           ★ default:"none" = 一上来整组都不显示（T46.3 发型组要的就是这个：
             默认短发 = 不额外挂任何一束头发，长发/双马尾/马尾才是档位）。
             运行期本来就有 cur=-1 这个状态（zrig_pose_set 的 id=none），
             这里只是让它**可以当初始值**，不必硬造一个空档位。 */
        g->cur = 0;
        if (defid && z_streq(defid, "none")) {
            g->cur = -1;
        } else if (defid) {
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
        {   /* mood_map: { "happy":"up", "surprise":"puff", ... }（T45.2d） */
            const zjson *mm = zjson_obj_get((zjson *)gj, "mood_map");
            if (mm && zjson_is(mm, ZJSON_OBJ)) {
                size_t mi, mn = zjson_count((zjson *)mm);
                for (mi = 0; mi < mn; ++mi) {
                    const char *k = zjson_key_at((zjson *)mm, mi);
                    const char *v = zjson_str(zjson_at((zjson *)mm, mi), NULL);
                    int t, found = -1;
                    if (!k || !*k || k[0] == '_') continue;   /* _note 之类跳过 */
                    if (g->nmood >= ZRIG_MAX_POSE_MOOD) {
                        zdiag_error(d, file, gj ? gj->line : 0, 0, path,
                                    "mood_map 条目过多（上限 %d）", ZRIG_MAX_POSE_MOOD);
                        return -1;
                    }
                    if (!v || !*v) continue;
                    for (t = 0; t < g->nent; ++t)
                        if (z_streq(r->poseents[g->ent0 + t].id, v)) { found = t; break; }
                    if (found < 0) {
                        zdiag_error(d, file, gj ? gj->line : 0, 0, path,
                                    "mood_map['%s'] 指向的档位 '%s' 不存在", k, v);
                        return -1;
                    }
                    z_strlcpy(g->mood_map[g->nmood].mood, k,
                              sizeof(g->mood_map[0].mood));
                    g->mood_map[g->nmood].ent = found;
                    g->nmood++;
                }
            }
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
        const zjson *ovs = zjson_obj_get(ej, "part_overrides");
        const char *id = zjson_str(zjson_obj_get(ej, "id"), NULL);
        size_t k, np = zjson_count(ps), no = zjson_count(ovs);
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
        if (ovs && ovs->type != ZJSON_OBJ) {
            zdiag_error(d, file, ovs->line, 0, path, "part_overrides 期望 object");
            return -1;
        }
        if (no > ZRIG_MAX_OVERRIDES) {
            zdiag_error(d, file, ovs ? ovs->line : 0, 0, path,
                        "表情部件覆盖过多（上限 %d）", ZRIG_MAX_OVERRIDES);
            return -1;
        }
        for (k = 0; k < no; ++k) {
            const char *pid = zjson_key_at(ovs, k);
            const zjson *oj = zjson_at(ovs, k);
            zoverride *o = &e->ovr[e->novr];
            memset(o, 0, sizeof(*o));
            z_strlcpy(o->part, pid ? pid : "", sizeof(o->part));
            if (!pid || find_part(r, pid) < 0) {
                zdiag_error(d, file, oj ? oj->line : 0, 0, path,
                            "part_overrides 引用了不存在的部件 '%s'", pid ? pid : "(缺)");
                return -1;
            }
            /* 表情 opacity 是渲染透明度的绝对目标（非乘数），所以 base opacity=0 的候选件也能淡入；dx/dy 仍为附加位移。 */
            o->opacity = zjson_num(zjson_obj_get(oj, "opacity"), 1.0);
            if (zjson_obj_get(oj, "dx")) {
                o->has_dx = 1;
                o->dx = zjson_num(zjson_obj_get(oj, "dx"), 0.0);
            }
            if (zjson_obj_get(oj, "dy")) {
                o->has_dy = 1;
                o->dy = zjson_num(zjson_obj_get(oj, "dy"), 0.0);
            }
            e->novr++;
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

/* 表情级部件覆盖：与表情参数共享同一淡入/淡出权重。
   没写覆盖的表情按 opacity=1、dx/dy=0 参与混合，使切换到普通表情时旧覆盖自然退场。 */
static void expr_part_override(const zrig *r, int part, double *opacity,
                               double *dx, double *dy)
{
    double w = 1.0, base_opacity, blended_opacity = 0.0;
    int pass;
    if (!r || part < 0 || part >= r->nparts ||
        (r->expr_cur < 0 && r->expr_prev < 0)) return;
    base_opacity = *opacity;
    if (r->expr_fade > 1e-6)
        w = z_smoothstep(ZC_CLAMP((r->now - r->expr_t0) / r->expr_fade, 0.0, 1.0));
    for (pass = 0; pass < 2; ++pass) {
        int ei = pass ? r->expr_prev : r->expr_cur;
        double ww = pass ? (1.0 - w) : w;
        double target_opacity = base_opacity;
        const zexpr *e;
        int k;
        if (ww <= 0.0) continue;
        if (ei >= 0 && ei < r->nexprs) {
            e = &r->exprs[ei];
            for (k = 0; k < e->novr; ++k) {
                const zoverride *o = &e->ovr[k];
                if (strcmp(o->part, r->parts[part].id) != 0) continue;
                /* expression opacity 是显式目标值，因而也能把 base opacity=0 的候选件淡入。 */
                target_opacity = o->opacity;
                if (o->has_dx) *dx += ww * o->dx;
                if (o->has_dy) *dy += ww * o->dy;
                break;
            }
        }
        blended_opacity += ww * target_opacity;
    }
    *opacity = blended_opacity;
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

/* 解析一组通道（channels）到 a->chans。
   ★ 抽出来是因为**环境摆动 ambient 和动作共用同一套通道语义**（T45.9）。
     以前只有 load_actions 会解析通道；ambient 提升成 rig 级之后要是再抄一份，
     以后给通道加字段就会漏掉一边 —— 那正是"死表"和"只接了一个入口"这两类
     bug 的温床（LESSONS 169 / DC41）。
   tag 只用于报错定位（动作写动作名，环境摆动写 "ambient"）。 */
static int load_channels(zrig *r, zaction *a, const zjson *chs,
                         zdiag *d, const char *file, const char *buf)
{
    /* ⚠ 这里只能有**一层**循环。第一版抽函数时我在外面又包了一个同名的
       for(k...)，于是 7 条通道被解析成 7×7=49 条，摆动参数被顶到值域两端
       （尾巴 rot_deg 峰峰值 28.2°，正常是 6.4°）。单条通道的测试 1×1=1
       恰好看不出来 —— 又一次"一半对一半错"。 */
    size_t k, kn = zjson_count((zjson *)chs);
    {
        for (k = 0; k < kn; ++k) {
            if (a->nchan >= ZRIG_MAX_CHANNELS) {
                zdiag_error(d, file, chs ? chs->line : 0, 0, buf,
                            "动作 '%s' 的通道超过上限 %d（超出的会被丢掉，必须改大 "
                            "ZRIG_MAX_CHANNELS）", a->id, ZRIG_MAX_CHANNELS);
                return -1;
            }
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
                            "通道 param 非法（允许 dx/dy/sx/sy/rot_deg/alpha/bend_x/bend_y/amount）");
                return -1;
            }
            /* 往形变器节点上写 bend 没有意义（节点没有网格形变曲线），当场拦住。 */
            if (c->deform >= 0 && (c->param == P_BEND_X || c->param == P_BEND_Y)) {
                zdiag_error(d, file, cj ? cj->line : 0, 0, buf,
                            "通道 target '%s' 是形变器，param 只能是 amount/dx/dy/sx/sy/rot_deg", tgt);
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
                            "通道 wave 非法（允许 sine/drift/bounce/pulse/decay/flap）");
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
    return 0;
}

/* ============================================================ 外部动作文件
   .motion3.json（T66.21 / S3 后半）

   ┌ 为什么底层必须能读它 ────────────────────────────────────────────────
   │ "自制 Live2D 等价底层" 的等价面有两半：**能被同一套参数驱动**（我们早就
   │ 用参数通道做到）和**能吃别人产出的动作文件**（这一节）。没有后者，
   │ 生态里的动作资源一个也用不上，所谓"等价"只等价到自己的 JSON。
   └────────────────────────────────────────────────────────────────────
   官方格式（CubismWebFramework 的 motion3 定义）：
     { Version, Meta:{Duration,Fps,Loop,FadeInTime,FadeOutTime,...},
       Curves:[ {Target:"Parameter"|"PartOpacity"|"Model", Id:"...",
                 Segments:[…]} ] }
   段编码的准确口径见下面「官方段编码」那一段注释（是真文件核对出来的，
   第一版按文档猜的写法是错的：首两个数是起点、段类型逐段重复）。

   ★ 两个必须说清的换算：
   ① **绝对值 → 偏移**：.motion3 的曲线写的是参数的**绝对值**，而我们的
      p_action 是**加在参数当前值上的偏移**（zrig.c:3090 `q->value + p_action`）。
      所以导入时把每个值都减掉该参数的默认值；不这么做的话，一条"把 ParamAngleX
      摆到 30°"的动作在这边会变成"在当前基础上再加 30°"。
   ② **贝塞尔 → 关键帧**：我们的通道插值只有 linear/smooth/step 三种（每通道一种），
      没有逐段的贝塞尔。含贝塞尔（或类型混排）的曲线按 20fps 烘焙成线性关键帧，
      段端点精确落键、阶梯段用"跳变前一刻"两个键保证不拖尾。 */
#define M3_MAX_SEGS 64
#define M3_BAKE_HZ  20.0        /* 烘焙采样率：20fps 足够，池子只有 1024 个键 */

typedef struct {
    int    type;                /* 每段自己的类型：0 线性 / 1 贝塞尔 / 2 阶梯 / 3 反阶梯 */
    double pt, pv;              /* 段起点（时间, 值），继承上一段终点 */
    double t, v;                /* 段终点 */
    double c1t, c1v, c2t, c2v;  /* 贝塞尔控制点（绝对坐标，官方口径） */
} m3seg;

/* 三次贝塞尔求值：给时间轴参数 u 求 (x,y)。点 = (c1t,c1v) (c2t,c2v) 与两端。 */
static double m3_bez(double p0, double p1, double p2, double p3, double u)
{
    double iu = 1.0 - u;
    return iu * iu * iu * p0 + 3.0 * iu * iu * u * p1
         + 3.0 * iu * u * u * p2 + u * u * u * p3;
}

/* 段内求值：time 落在 [pt, t] 里，返回该时刻的**绝对值**。 */
static double m3_eval(const m3seg *sg, double time)
{
    double span = sg->t - sg->pt, u = 0.0;
    if (span <= 1e-9) return sg->v;
    u = (time - sg->pt) / span;
    if (u < 0.0) u = 0.0;
    if (u > 1.0) u = 1.0;
    if (sg->type == 2 || sg->type == 3)
        return (u >= 1.0) ? sg->v : sg->pv;      /* 阶梯：到点才跳 */
    if (sg->type == 0)
        return sg->pv + (sg->v - sg->pv) * u;
    {   /* 贝塞尔：x(u) 是时间的单调函数 → 二分反解 */
        double lo = 0.0, hi = 1.0, mid;
        int k;
        for (k = 0; k < 40; ++k) {
            mid = 0.5 * (lo + hi);
            if (m3_bez(sg->pt, sg->c1t, sg->c2t, sg->t, mid) < time) lo = mid;
            else hi = mid;
        }
        return m3_bez(sg->pv, sg->c1v, sg->c2v, sg->v, 0.5 * (lo + hi));
    }
}

/* ============================================================ 官方段编码
   这一节的口径是拿**真文件**核对出来的（不是照文档猜的）：
     Segments = [ t0, v0,  type, …段的数…,  type, …段的数…, … ]
   ① 头两个数字是曲线起点，**不是段类型**；
   ② 之后每一段是「类型 + 该段的数」，类型**逐段重复**，同一条曲线里可以混排；
   ③ 线性 / 阶梯 / 反阶梯：类型 + (t, v) 三个数；
      贝塞尔：类型 + (c1t,c1v, c2t,c2v, t,v) 七个数，控制点是**绝对坐标**，
      且 (t,v) 是这个段的**终点**（起点继承上一段）。
   核对手头：CubismWebFramework `cubismmotion.ts` 的 Segments 装载代码
   （`segmentPosition == 0` 先读 t0/v0 再 +2；Linear/Stepped 每段 +3；
   Bezier 每段 +7，并把 +1..+6 读成 points[1..3]，points[0] 是上一段终点）。
   ★ 一开始我按"首数字是类型、整条曲线只有一种类型"写，测试样本照着我的错误
     口径喂进去，居然"通过"了 —— 那正是自证。改用真实 motion3 文件核对后才发现：
     段类型逐段重复、首两个数是起点。样本现在按真格式写。
   ④ 阶梯取值 = 段起点的值（保持到段末才跳）；反阶梯 = 段终点的值（段首就跳）。 */

/* 追加一个关键帧；时间与上一帧相同就**覆盖**（段首会和上一段末撞秒）。
   调用方已按上限预留池子，这里只管写。 */
static void m3_push_key(zrig *r, zchan *c, double t, double v)
{
    int last;
    if (c->nkeys > 0) {
        last = c->key0 + c->nkeys - 1;
        if (fabs(r->key_t[last] - t) < 1e-6) {
            r->key_v[last] = v;
            return;
        }
    }
    r->key_t[r->nkeypool] = t;
    r->key_v[r->nkeypool] = v;
    r->nkeypool++;
    c->nkeys++;
}

/* 把一条曲线推进关键帧池。返回 0 成功；失败已写诊断（说清缺什么数）。 */
static int m3_curve_to_keys(zrig *r, zchan *c, const zjson *segs, double vdef,
                            const char *file, const char *cid, zdiag *d)
{
    double buf[600], t0, v0;
    size_t n, i, pos;
    m3seg sg[M3_MAX_SEGS];
    int nseg = 0, k, need, all_lin = 1, all_step = 1, all_inv = 1;
    char field[160];

    z_snprintf(field, sizeof(field), "Curves[%s].Segments", cid ? cid : "?");
    memset(buf, 0, sizeof(buf));
    if (!segs || segs->type != ZJSON_ARR || zjson_count(segs) < 5) {
        zdiag_error(d, file, segs ? segs->line : 0, 0, field,
                    "Segments 至少 5 个数（起点 t,v + 一个「类型 + 端点」段），实际 %d 个",
                    segs ? (int)zjson_count(segs) : 0);
        return -1;
    }
    n = zjson_count(segs);
    if (n > sizeof(buf) / sizeof(buf[0])) {
        zdiag_error(d, file, segs->line, 0, field,
                    "Segments 有 %d 个数，超过单条曲线上限 %d（真动作请拆文件）", (int)n,
                    (int)(sizeof(buf) / sizeof(buf[0])));
        return -1;
    }
    for (i = 0; i < n; ++i) buf[i] = zjson_num(zjson_at((zjson *)segs, i), 0.0);
    t0 = buf[0];
    v0 = buf[1];
    pos = 2;
    while (pos < n) {
        int type = (int)buf[pos];
        double pt = (nseg > 0) ? sg[nseg - 1].t : t0;
        double pv = (nseg > 0) ? sg[nseg - 1].v : v0;
        if (type < 0 || type > 3) {
            zdiag_error(d, file, segs->line, 0, field,
                        "第 %d 个数字是段类型，只能是 0/1/2/3（线性/贝塞尔/阶梯/反阶梯），"
                        "读到 %d —— 位置错了通常意味着少写了一对数", (int)pos, type);
            return -1;
        }
        if (nseg >= M3_MAX_SEGS) {
            zdiag_error(d, file, segs->line, 0, field,
                        "段数超过 %d（手写样本的余量；真动作请拆文件）", M3_MAX_SEGS);
            return -1;
        }
        pos++;
        memset(&sg[nseg], 0, sizeof(sg[nseg]));
        sg[nseg].type = type;
        sg[nseg].pt = pt;
        sg[nseg].pv = pv;
        if (type == 1) {
            if (pos + 6 > n) {
                zdiag_error(d, file, segs->line, 0, field,
                            "贝塞尔段要 6 个数（c1t,c1v, c2t,c2v, t,v），只给了 %d 个",
                            (int)(n - pos));
                return -1;
            }
            sg[nseg].c1t = buf[pos];     sg[nseg].c1v = buf[pos + 1];
            sg[nseg].c2t = buf[pos + 2]; sg[nseg].c2v = buf[pos + 3];
            sg[nseg].t = buf[pos + 4];   sg[nseg].v = buf[pos + 5];
            pos += 6;
            /* 控制点时间跑出段外：官方工具不产出这种数，但我们不掀桌，只提醒 */
            if (sg[nseg].c1t < pt - 1e-6 || sg[nseg].c1t > sg[nseg].t + 1e-6 ||
                sg[nseg].c2t < pt - 1e-6 || sg[nseg].c2t > sg[nseg].t + 1e-6)
                zdiag_warn(d, file, segs->line, 0, field,
                           "贝塞尔控制点时间在段外（%.3f..%.3f），按内插裁剪处理",
                           pt, sg[nseg].t);
        } else {
            if (pos + 2 > n) {
                zdiag_error(d, file, segs->line, 0, field,
                            "线性/阶梯段要（t, v）一对数，剩下的不够");
                return -1;
            }
            sg[nseg].t = buf[pos]; sg[nseg].v = buf[pos + 1];
            pos += 2;
        }
        if (sg[nseg].t < sg[nseg].pt) {
            zdiag_error(d, file, segs->line, 0, field,
                        "第 %d 段的终点时间 %.3f 比起点 %.3f 还早（时间必须单调）",
                        nseg + 1, sg[nseg].t, sg[nseg].pt);
            return -1;
        }
        if (type != 0) all_lin = 0;
        if (type != 2) all_step = 0;
        if (type != 3) all_inv = 0;
        nseg++;
    }
    if (nseg == 0) {
        zdiag_error(d, file, segs->line, 0, field, "曲线里一段都没有");
        return -1;
    }

    /* 先算要几个键，再落池：宁可当场说"池子不够"，也不要写一半 */
    need = 1;
    if (all_lin || all_step || all_inv) need += nseg;
    else {
        for (k = 0; k < nseg; ++k) {
            if (sg[k].type == 1) need += (int)((sg[k].t - sg[k].pt) * M3_BAKE_HZ) + 2;
            else need += 2;
        }
    }
    if (r->nkeypool + need > ZRIG_MAX_KEYPOOL) {
        zdiag_error(d, file, segs->line, 0, field,
                    "曲线 %s 要 %d 个关键帧，池子只剩 %d（全模型共用 %d；"
                    "贝塞尔/混排按 %.0ffps 烘焙，纯线性/阶梯按端点存）",
                    cid ? cid : "?", need, ZRIG_MAX_KEYPOOL - r->nkeypool,
                    ZRIG_MAX_KEYPOOL, M3_BAKE_HZ);
        return -1;
    }

    c->key0 = r->nkeypool;
    c->nkeys = 0;
    if (all_lin) c->interp = KI_LINEAR;
    else if (all_step || all_inv) c->interp = KI_STEP;
    else c->interp = KI_LINEAR;              /* 烘焙出来的密关键帧走线性 */
    m3_push_key(r, c, t0, v0 - vdef);
    for (k = 0; k < nseg; ++k) {
        if (all_lin || all_step) {           /* 端点即全部信息 */
            m3_push_key(r, c, sg[k].t, sg[k].v - vdef);
            continue;
        }
        if (all_inv) {                        /* 反阶梯：段首就跳 */
            m3_push_key(r, c, sg[k].pt, sg[k].v - vdef);
            m3_push_key(r, c, sg[k].t, sg[k].v - vdef);
            continue;
        }
        /* 混排（含贝塞尔）：按 20fps 烘焙成线性关键帧 */
        if (sg[k].type == 0) {
            m3_push_key(r, c, sg[k].t, sg[k].v - vdef);
        } else if (sg[k].type == 2) {
            m3_push_key(r, c, sg[k].t - 1e-3, sg[k].pv - vdef);
            m3_push_key(r, c, sg[k].t, sg[k].v - vdef);
        } else if (sg[k].type == 3) {
            m3_push_key(r, c, sg[k].pt, sg[k].v - vdef);
            m3_push_key(r, c, sg[k].t, sg[k].v - vdef);
        } else {
            double step = 1.0 / M3_BAKE_HZ, t;
            for (t = sg[k].pt + step; t < sg[k].t - 1e-6; t += step)
                m3_push_key(r, c, t, m3_eval(&sg[k], t) - vdef);
            m3_push_key(r, c, sg[k].t, sg[k].v - vdef);
        }
    }
    return 0;
}

int zrig_motion3_add(zrig *r, const char *path, const char *id_override, zdiag *d)
{
    zjson *root = NULL;
    zerr err;
    const zjson *meta, *curves;
    const char *cid;
    char full[1200];
    double dur = 1.0;
    int loop = 0, applied = 0, skipped = 0, i, n;
    zaction *a;

    if (!r || !path) return -1;
    z_resolve_path(full, sizeof(full), r->dir, path);
    if (!z_file_exists(full)) {
        zdiag_error(d, full, 0, 0, "motion3", "动作文件不存在：%s", path);
        return -1;
    }
    zerr_clear(&err);
    root = zjson_parse_file(full, &err);
    if (!root) {
        zdiag_error(d, full, err.line, err.col, "motion3", "解析失败：%s", err.msg);
        return -1;
    }
    if (r->nactions >= ZRIG_MAX_ACTIONS) {
        zdiag_error(d, full, root->line, 0, "motion3",
                    "动作数已到上限 %d（改大 ZRIG_MAX_ACTIONS）", ZRIG_MAX_ACTIONS);
        zjson_free(root);
        return -1;
    }
    curves = zjson_obj_get(root, "Curves");
    if (!curves || curves->type != ZJSON_ARR || zjson_count(curves) == 0) {
        zdiag_error(d, full, root->line, 0, "motion3", "缺少非空的 Curves 数组");
        zjson_free(root);
        return -1;
    }

    a = &r->actions[r->nactions];
    memset(a, 0, sizeof(*a));
    a->interruptible = 1;
    a->priority = 1;                     /* idle 是 0：导入的动作默认能打断 idle */
    a->blink_hold = -1.0;
    cid = id_override;
    if (!cid || !*cid) cid = zjson_str(zjson_obj_get(root, "Id"), NULL);
    if (!cid || !*cid) cid = z_basename(full);
    z_strlcpy(a->id, cid, sizeof(a->id));
    z_strlcpy(a->title, zjson_str(zjson_obj_get(root, "Title"), a->id), sizeof(a->title));
    z_strlcpy(a->return_state, "idle", sizeof(a->return_state));

    meta = zjson_obj_get(root, "Meta");
    dur = zjson_num(zjson_obj_get(meta, "Duration"), 1.0);
    if (dur <= 0.0) {
        zdiag_error(d, full, meta ? meta->line : 0, 0, "Meta.Duration",
                    "Duration 必须 > 0（读到 %.3f）", dur);
        zjson_free(root);
        return -1;
    }
    loop = zjson_bool(zjson_obj_get(meta, "Loop"), 0);
    /* 我们的约定：循环动作 duration < 0（见 load_actions 的注释） */
    a->loop = loop;
    a->duration = loop ? -1.0 : dur;
    a->fade = zjson_num(zjson_obj_get(meta, "FadeInTime"), 0.22);
    a->fade_out = zjson_num(zjson_obj_get(meta, "FadeOutTime"), 0.2);
    if (a->fade < 0.0) a->fade = 0.0;
    if (a->fade_out < 0.0) a->fade_out = 0.0;

    n = (int)zjson_count(curves);
    for (i = 0; i < n; ++i) {
        const zjson *cj = zjson_at(curves, i);
        const char *target = zjson_str(zjson_obj_get(cj, "Target"), "Parameter");
        const char *pid = zjson_str(zjson_obj_get(cj, "Id"), NULL);
        int pi;
        zchan *c;
        if (!z_streq(target, "Parameter")) {
            /* PartOpacity / Model 我们没有对应的量：**数出来**并记警告，
               不静默丢 —— 全丢光的时候要能一眼看出是"目标类型不支持"。 */
            skipped++;
            continue;
        }
        pi = param_find(r, param_alias(pid));
        if (pi < 0) {
            zdiag_warn(d, full, cj ? cj->line : 0, 0, pid ? pid : "Curves",
                       "动作里的参数 %s 不在本模型里，这条曲线跳过", pid ? pid : "?");
            skipped++;
            continue;
        }
        if (a->nchan >= ZRIG_MAX_CHANNELS) {
            zdiag_error(d, full, cj ? cj->line : 0, 0, "Curves",
                        "通道数超过上限 %d（.motion3 最多 63 条曲线，先合并同类参数）",
                        ZRIG_MAX_CHANNELS);
            zjson_free(root);
            return -1;
        }
        c = &a->chans[a->nchan];
        memset(c, 0, sizeof(*c));
        c->group = c->part = c->deform = -1;
        c->pparam = pi;
        c->param = P_DX;                    /* 占位：参数通道只看 pparam */
        c->amp = 0.0; c->freq = 1.0; c->dur = dur;
        if (m3_curve_to_keys(r, c, zjson_obj_get(cj, "Segments"),
                             r->params[pi].vdef, full, pid, d) != 0) {
            zjson_free(root);
            return -1;
        }
        a->nchan++;
        applied++;
    }
    zjson_free(root);
    if (applied == 0) {
        zdiag_error(d, full, 0, 0, "motion3",
                    "一条曲线都没能用上（%d 条被跳过：目标类型不是 Parameter，"
                    "或参数不在本模型里）", skipped);
        return -1;
    }
    r->nactions++;
    r->motion3_count++;                  /* 统计用：加载完要能说清"其中几条是外部文件" */
    /* 动作表加了不等于**能点播**：状态机是另一张表（zsm），不登记的话
       zrig_action_request("wave_ext") 会以"未知状态"被拒 —— 这正是第一次
       自测时 8 条断言全读到 0.00 的原因。 */
    {
        zsm_state_def def;
        memset(&def, 0, sizeof(def));
        z_strlcpy(def.id, a->id, sizeof(def.id));
        def.priority = a->priority;
        def.duration_s = a->duration;
        def.interruptible = a->interruptible;
        def.loop = a->loop;
        z_strlcpy(def.return_state, a->return_state, sizeof(def.return_state));
        if (zsm_index(&r->sm, a->id) >= 0) {
            zdiag_error(d, full, 0, 0, "motions",
                        "外部动作 id '%s' 与既有动作重名（换一个 id，或删掉一条）", a->id);
            r->nactions--;
            return -1;
        }
        if (zsm_add_state(&r->sm, &def) < 0) {
            zdiag_error(d, full, 0, 0, "motions",
                        "状态数超过上限 %d（ZSM_MAX_STATES 要和 ZRIG_MAX_ACTIONS 同步）",
                        ZSM_MAX_STATES);
            r->nactions--;
            return -1;
        }
    }
    ZLOGI("rig", "导入动作 %s（%d 条曲线，跳过 %d，时长 %.2fs%s）",
          a->id, applied, skipped, dur, loop ? "，循环" : "");
    return applied;
}

/* rig.json 的 "motions" 段：把外部 .motion3 文件接进这个模型。
   写法 [{"id":"wave_ext", "file":"motions/wave.motion3.json"}]，
   id 不给就用文件里的 Id / 文件名。**缺文件是硬错误** —— 声明了却读不到，
   等于这个动作永远播不出来，静默跳过只会让人以为是"动作写坏了"。 */
static int load_motions(zrig *r, const zjson *jm, zdiag *d, const char *file)
{
    size_t i, n = zjson_count(jm);
    if (!jm) return 0;
    if (jm->type != ZJSON_ARR) {
        zdiag_error(d, file, jm->line, 0, "motions", "期望 array");
        return -1;
    }
    for (i = 0; i < n; ++i) {
        const zjson *mj = zjson_at(jm, i);
        const char *f = zjson_str(zjson_obj_get(mj, "file"), NULL);
        const char *id = zjson_str(zjson_obj_get(mj, "id"), NULL);
        if (!f || !*f) {
            zdiag_error(d, file, mj ? mj->line : 0, 0, "motions", "缺 file");
            return -1;
        }
        if (zrig_motion3_add(r, f, id, d) < 0) return -1;
    }
    return 0;
}

static int load_actions(zrig *r, const zjson *jacts, zdiag *d, const char *file)
{
    size_t i, n = zjson_count(jacts);
    zsm_state_def def;
    if (!jacts || jacts->type != ZJSON_ARR) {
        zdiag_error(d, file, jacts ? jacts->line : 0, 0, "actions", "期望 array");
        return -1;
    }
    for (i = 0; i < n; ++i) {
        if (r->nactions >= ZRIG_MAX_ACTIONS) {
            zdiag_error(d, file, jacts->line, 0, "actions",
                        "动作数超过上限 %d（超出的会被丢掉，必须改大 ZRIG_MAX_ACTIONS）",
                        ZRIG_MAX_ACTIONS);
            return -1;
        }
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
        /* 没写 title 就退回 id：新动作不写名字也能用，只是界面上显示英文 */
        z_strlcpy(a->title, zjson_str(zjson_obj_get(aj, "title"), id), sizeof(a->title));
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
        z_strlcpy(a->flick_pre, zjson_str(zjson_obj_get(aj, "flick_trigger"), ""),
                  sizeof(a->flick_pre));
        /* FadeOutTime：官方每个 motion 自带，非循环动作快演完时按
           getEasingSine((结束时刻 − 现在) / FadeOutTime) 自己收尾。
           以前我们是在 W_PULSE 波形里硬写"结束前 0.15 秒乘个衰减"，
           那只管得到 pulse 一种波形，别的波形该怎么收尾全靠运气。 */
        a->fade_out = zjson_num(zjson_obj_get(aj, "fade_out"), 0.2);
        if (a->fade_out < 0.0) a->fade_out = 0.0;
        if (a->fade < 0.0) a->fade = 0.0;
        if (a->fade > 2.0) a->fade = 2.0;
        a->duration = zjson_num(zjson_obj_get(aj, "duration"), a->loop ? -1.0 : 1.0);
        if (a->loop) a->duration = -1.0;
        {
            const char *rs = zjson_str(zjson_obj_get(aj, "return_state"), "idle");
            z_strlcpy(a->return_state, rs, sizeof(a->return_state));
        }
        /* 通道 */
        if (load_channels(r, a, zjson_obj_get(aj, "channels"),
                          d, file, buf) != 0) return -1;
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
        /* 两种失败原因要分开报：以前合成一句"动作 id 重复或状态数超限"，
           撞上限时人会一直去查重名（第六十三问 P0 顺手分开）。 */
        if (zsm_index(&r->sm, a->id) >= 0) {
            zdiag_error(d, file, aj ? aj->line : 0, 0, buf,
                        "动作 id '%s' 重复", a->id);
            return -1;
        }
        if (zsm_add_state(&r->sm, &def) < 0) {
            zdiag_error(d, file, aj ? aj->line : 0, 0, buf,
                        "状态数超过上限 %d（ZSM_MAX_STATES 要和 ZRIG_MAX_ACTIONS 同步）",
                        ZSM_MAX_STATES);
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
    for (i = 0; i < n; ++i) {
        if (r->nregions >= ZRIG_MAX_REGIONS) {
            zdiag_error(d, file, jreg ? jreg->line : 0, 0, "regions",
                        "交互区域超过上限 %d（超出的会被丢掉，必须改大 ZRIG_MAX_REGIONS）",
                        ZRIG_MAX_REGIONS);
            return -1;
        }
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
    zrand_seed(&r->sacc_rng, 0x5ACCAD3Dull);   /* 微动自己的流，见 sacc_rng 的注释 */
    zsm_init(&r->sm);
    r->blink_state = BL_FIRST;
    r->phys_enabled = 1;
    r->look_blink_init = 0;
    r->look_blink_last = -1e9;
    r->blink_forced = -1;
    r->blink_manual = -1.0;
    r->blink_manual_l = -1.0;
    r->blink_manual_r = -1.0;
    {   /* ★ 摆动倍率必须显式初始化成 1.0。zrig 是 calloc 出来的 ⇒ 默认 0.0，
           而 0.0 的含义是"幅度归零、频率归零" —— 不是"不调制"。
           漏了这步的话，**所有**挂件的自主摆动在加载后就直接死掉。 */
        int _i;
        for (_i = 0; _i < ZRIG_MAX_PARAMS; ++_i) {
            r->sw_fmul[_i] = 1.0;
            r->sw_amul[_i] = 1.0;
            r->sw_tshift[_i] = 0.0;
        }
    }
    {   /* 抽动：自己的随机流 + 「还没排过班」的哨兵。
           flick_amp 默认 0 = 不抽；要等 tail_flick 表里的某一行被应用。 */
        int _i;
        zrand_seed(&r->flick_rng, 0xF11CCA7ull);
        r->flick_gmin = 5.0;
        r->flick_gmax = 13.0;
        r->flick_amp  = 0.0;
        r->flick_dur  = 0.9;
        for (_i = 0; _i < ZRIG_MAX_MOOD_PARAM; ++_i) {
            r->flick_st[_i].next_t = -1.0;
            r->flick_st[_i].t0 = -1.0;
        }
    }
    r->lag_head = -1;
    r->lookh_head = -1;
    r->blink_imin = 2.0;
    r->blink_imax = 8.0;
    r->blink_rate = 1.0;
    r->blink_closed_scale = 1.0;

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
    /* 挂点必须在部件之前 —— 部件装载时就要按名字解析成 (组, 坐标) */
    if (load_sockets(r, zjson_obj_get(root, "sockets"), diag, file) != 0) goto fail;
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
    /* 变形器树的两处延迟解析（都必须等参数表/形变器两者都到位）：
       ① 形变器的 keyform 驱动参数名 → 参数下标；
       ② 部件的 "deformer" → 形变器下标。
       这两条以前不存在（形变器只有"挂在自己身上的那张网格"），所以没有对应报错路径；
       现在写错了名字必须当场红，而不是让整个节点静默不起作用。 */
    {
        int i;
        for (i = 0; i < r->ndeforms; ++i) {
            zdeform *g = &r->deforms[i];
            if (!g->kf_param_id[0]) continue;
            g->param = param_find(r, g->kf_param_id);
            if (g->param < 0) {
                zdiag_error(diag, file, 0, 0, "deformers",
                            "形变器 '%s' 的 param '%s' 不在参数表里（params 段要声明它）",
                            g->id, g->kf_param_id);
                goto fail;
            }
        }
        for (i = 0; i < r->nparts; ++i) {
            zpart *p = &r->parts[i];
            if (!p->deform_id[0]) continue;
            p->deformer = find_deform(r, p->deform_id);
            if (p->deformer < 0) {
                char path[160];
                z_snprintf(path, sizeof(path), "parts.%s.deformer", p->id);
                zdiag_error(diag, file, 0, 0, path,
                            "deformer '%s' 不存在（形变器段要先声明它）", p->deform_id);
                goto fail;
            }
        }
        /* inherit_from → 部件下标（T66.10b）。三条必须在装载期就红：
           ① 源件不存在；② 指到自己（等于自己套自己）；③ 源件没有任何网格
           （那不是"继承到空"，而是写错了目标 —— 静默的 0 位移最难查）。 */
        for (i = 0; i < r->nparts; ++i) {
            zpart *p = &r->parts[i];
            int k, has_mesh = 0;
            if (!p->inherit_from_id[0]) continue;
            p->inherit_from = find_part(r, p->inherit_from_id);
            if (p->inherit_from < 0) {
                char path[160];
                z_snprintf(path, sizeof(path), "parts.%s.inherit_from", p->id);
                zdiag_error(diag, file, 0, 0, path, "部件 '%s' 不存在", p->inherit_from_id);
                goto fail;
            }
            if (p->inherit_from == i) {
                char path[160];
                z_snprintf(path, sizeof(path), "parts.%s.inherit_from", p->id);
                zdiag_error(diag, file, 0, 0, path, "不能继承自己（'%s'）", p->id);
                goto fail;
            }
            for (k = 0; k < r->ndeforms; ++k) {
                const zdeform *g = &r->deforms[k];
                if (g->part != p->inherit_from) continue;
                if (g->cols < 1 || g->rows < 1) continue;
                has_mesh = 1;
                break;
            }
            if (!has_mesh) {
                char path[160];
                z_snprintf(path, sizeof(path), "parts.%s.inherit_from", p->id);
                zdiag_error(diag, file, 0, 0, path,
                            "源件 '%s' 没有任何网格（它自己没有可继承的形变场 —— "
                            "要么写错目标，要么得先给它一张网格）", p->inherit_from_id);
                goto fail;
            }
        }
    }
    if (load_actions(r, zjson_obj_get(root, "actions"), diag, file) != 0) goto fail;
    /* 外部动作文件（T66.21）：排在 actions 之后，因为 id 不能和既有动作撞车时
       要能看到完整清单（motion3 自己不带 id 冲突检查，撞了就以后来的为准不行） */
    if (load_motions(r, zjson_obj_get(root, "motions"), diag, file) != 0) goto fail;
    if (load_regions(r, zjson_obj_get(root, "regions"), diag, file) != 0) goto fail;
    if (load_physics(r, zjson_obj_get(root, "physics"), diag, file) != 0) goto fail;
    /* 力场要在摆链之前定好：建链时就按重力把链摆直（不然第一帧会从原点"掉"下来） */
    {
        const zjson *fj = zjson_obj_get(root, "forces");
        const zjson *gj = fj ? zjson_obj_get(fj, "gravity") : NULL;
        const zjson *wj = fj ? zjson_obj_get(fj, "wind") : NULL;
        r->p2_gx = gj ? zjson_num(zjson_at(gj, 0), 0.0) : 0.0;
        r->p2_gy = gj ? zjson_num(zjson_at(gj, 1), 1.0) : 1.0;
        r->p2_wx = wj ? zjson_num(zjson_at(wj, 0), 0.0) : 0.0;
        r->p2_wy = wj ? zjson_num(zjson_at(wj, 1), 0.0) : 0.0;
        {   /* breeze 写在 rig 里而不是写死在引擎里：室内的角色和站天台上的角色，
               这个值本来就该不一样；将来换形态/换场景也只改数据。 */
            const zjson *bz = fj ? zjson_obj_get(fj, "breeze") : NULL;
            r->p2_breeze_amp = bz ? zjson_num(zjson_obj_get(bz, "amp"), 0.0) : 0.0;
            r->p2_breeze_hz  = bz ? zjson_num(zjson_obj_get(bz, "hz"), 0.11) : 0.11;
            if (r->p2_breeze_amp < 0.0) r->p2_breeze_amp = 0.0;
            if (r->p2_breeze_amp > ZRIG_BREEZE_MAX) {
                zdiag_warn(diag, file, bz ? bz->line : 0, 0, "forces.breeze.amp",
                           "超过上限，已夹回（微风不是台风）");
                r->p2_breeze_amp = ZRIG_BREEZE_MAX;
            }
            if (!(r->p2_breeze_hz > 0.0) || r->p2_breeze_hz > 2.0) r->p2_breeze_hz = 0.11;
        }
    }
    if (load_physics2(r, zjson_obj_get(root, "physics2"), diag, file) != 0) goto fail;
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
    {   /* ambient（T45.9）：环境摆动通道。必须排在 actions / params 之后 ——
           通道的 target 要能查到参数、组、部件、形变器。
           借 load_channels()（就是 actions 用的那一个）解析，所以通道以后加字段，
           动作和环境摆动会自动一起跟上。 */
        const zjson *amb = zjson_obj_get(root, "ambient");
        if (amb && zjson_is(amb, ZJSON_ARR) && zjson_count((zjson *)amb) > 0) {
            memset(&r->ambient, 0, sizeof(r->ambient));
            z_strlcpy(r->ambient.id, "__ambient", sizeof(r->ambient.id));
            r->ambient.loop = 1;
            r->ambient.duration = -1.0;
            if (load_channels(r, &r->ambient, amb, diag, file, "ambient") != 0)
                goto fail;
            /* ★ ambient 是**无限循环**（duration = -1），所以它的通道只能用
               「周期性」波形。pulse 是"冲上去然后保持"（收尾靠动作自己的 fade_out），
               decay 是"抖两下然后归零" —— 这两个在无限循环里 t 一直涨，
               结果就是**冲到顶之后永远卡在那**。
               这不是假想：猫耳的 ParamEarLAngle/RAngle 曾经就写着
               {"wave":"pulse","amp":0.14,"freq":0.085}，实测 30 秒里值恒等于
               0.1400 纹丝不动 —— 一对永远不会抖的猫耳，而且 freq 根本没人读。
               与其靠人记住，不如在这儿拦下来。 */
            {
                int ci;
                for (ci = 0; ci < r->ambient.nchan; ++ci) {
                    const zchan *c = &r->ambient.chans[ci];
                    if (c->nkeys > 0) continue;          /* 关键帧自带循环语义，放行 */
                    if (c->wave == W_PULSE || c->wave == W_DECAY) {
                        zdiag_error(diag, file, amb->line, 0, "ambient",
                                    "环境摆动是无限循环，通道不能用一次性波形 "
                                    "pulse/decay（会冲到顶就卡住不动）；"
                                    "要周期摆动用 sine/drift/flap/bounce，"
                                    "要偶发抽动用 tail_flick");
                        goto fail;
                    }
                }
            }
            r->has_ambient = (r->ambient.nchan > 0);
        }
    }

    {   /* mood_swing（T45.2f）：情绪 → 摆动倍率。同样要在 params 之后。
           ★ 这张表以前只躺在 design/attachments.json 里，生成器不读、rig 里没有、
             引擎不认识 —— 是一张**死表**：看着像配置，其实只是注释。
             「生气时尾巴快速甩」「专注时慢而大」这两条词汇因此从来没交付过。
             发现它靠的是一个确定性探针（tools/probe_swing.c）：
             11 种情绪跑出来峰峰值全是 6.4、频率全是 0.21Hz。 */
        const zjson *ms = zjson_obj_get(root, "mood_swing");
        if (ms && zjson_is(ms, ZJSON_OBJ)) {
            const zjson *ps = zjson_obj_get(ms, "params");
            const zjson *mo = zjson_obj_get(ms, "moods");
            size_t i, n;
            if (ps && zjson_is(ps, ZJSON_ARR)) {
                n = zjson_count((zjson *)ps);
                for (i = 0; i < n; ++i) {
                    const char *pid = zjson_str(zjson_at((zjson *)ps, i), NULL);
                    int pi;
                    if (!pid || !*pid) continue;
                    pi = param_find(r, pid);
                    if (pi < 0) {
                        zdiag_error(diag, file, ps->line, 0, "mood_swing",
                                    "mood_swing.params 提到了不存在的参数 '%s'", pid);
                        goto fail;
                    }
                    if (r->nswing_param >= ZRIG_MAX_MOOD_PARAM) {
                        zdiag_error(diag, file, ps->line, 0, "mood_swing",
                                    "mood_swing.params 过多（上限 %d）",
                                    ZRIG_MAX_MOOD_PARAM);
                        goto fail;
                    }
                    r->swing_param[r->nswing_param++] = pi;
                }
            }
            if (mo && zjson_is(mo, ZJSON_OBJ)) {
                n = zjson_count((zjson *)mo);
                for (i = 0; i < n; ++i) {
                    const char *mk = zjson_key_at((zjson *)mo, i);
                    const zjson *pr = zjson_at((zjson *)mo, i);
                    int slot = r->nmood_swing;
                    if (!mk || !*mk || mk[0] == '_') continue;
                    if (!pr || !zjson_is(pr, ZJSON_ARR) || zjson_count((zjson *)pr) < 2) {
                        zdiag_error(diag, file, mo->line, 0, "mood_swing",
                                    "mood_swing.moods['%s'] 要写成 [频率倍率, 幅度倍率]", mk);
                        goto fail;
                    }
                    if (slot >= ZRIG_MAX_BLINK_MOOD) {
                        zdiag_error(diag, file, mo->line, 0, "mood_swing",
                                    "mood_swing.moods 条目过多（上限 %d）",
                                    ZRIG_MAX_BLINK_MOOD);
                        goto fail;
                    }
                    z_strlcpy(r->mood_swing[slot].mood, mk,
                              sizeof(r->mood_swing[0].mood));
                    r->mood_swing[slot].fmul =
                        ZC_CLAMP(zjson_num(zjson_at((zjson *)pr, 0), 1.0), 0.05, 20.0);
                    r->mood_swing[slot].amul =
                        ZC_CLAMP(zjson_num(zjson_at((zjson *)pr, 1), 1.0), 0.0, 20.0);
                    r->nmood_swing++;
                }
            }
        }
    }

    {   /* tail_flick（T45.2g）：情绪 → **自发抽动**的频度和力度。第五张情绪表。
           格式：
             { "params": ["ParamAccTailRelaxedSwing", ...],
               "scale":  [1.0, 0.25, ...],                 // 和 params 同序
               "moods":  { "angry": [0.7, 2.0, 1.15, 0.5], ... } }
                                   // [间隔下限秒, 间隔上限秒, 幅度(参数单位), 时长秒]
           为什么要有这张表：摆尾在行为学上是**阵发事件**不是匀速节拍
           （de Mouzon 2023：被忽视时平均摆 13.98 秒，被搭理时 0.39 秒），
           而「尾尖抽动 → 整条摆 → 拍打」是一条随唤醒度升级的链。
           口径同前四张情绪表：**查不到的情绪不动**。 */
        const zjson *tf = zjson_obj_get(root, "tail_flick");
        if (tf && zjson_is(tf, ZJSON_OBJ)) {
            const zjson *ps = zjson_obj_get(tf, "params");
            const zjson *sc = zjson_obj_get(tf, "scale");
            const zjson *mo = zjson_obj_get(tf, "moods");
            size_t i, n;
            if (ps && zjson_is(ps, ZJSON_ARR)) {
                n = zjson_count((zjson *)ps);
                for (i = 0; i < n; ++i) {
                    const char *pid = zjson_str(zjson_at((zjson *)ps, i), NULL);
                    int pi;
                    if (!pid || !*pid) continue;
                    pi = param_find(r, pid);
                    if (pi < 0) {
                        zdiag_error(diag, file, ps->line, 0, "tail_flick",
                                    "tail_flick.params 提到了不存在的参数 '%s'", pid);
                        goto fail;
                    }
                    if (r->nflick_param >= ZRIG_MAX_MOOD_PARAM) {
                        zdiag_error(diag, file, ps->line, 0, "tail_flick",
                                    "tail_flick.params 过多（上限 %d）",
                                    ZRIG_MAX_MOOD_PARAM);
                        goto fail;
                    }
                    r->flick_param[r->nflick_param] = pi;
                    /* scale 缺省 1.0：四种尾巴姿态的 rot 系数差 14 倍
                       （relaxed 3.2° / up 20° / puff 16° / tuck 1.4°），
                       同一个 amp 直接用会让竖起的尾巴抽出去半屏。 */
                    r->flick_scale[r->nflick_param] =
                        (sc && zjson_is(sc, ZJSON_ARR) && i < zjson_count((zjson *)sc))
                        ? ZC_CLAMP(zjson_num(zjson_at((zjson *)sc, i), 1.0), 0.0, 4.0)
                        : 1.0;
                    r->nflick_param++;
                }
            }
            if (mo && zjson_is(mo, ZJSON_OBJ)) {
                n = zjson_count((zjson *)mo);
                for (i = 0; i < n; ++i) {
                    const char *mk = zjson_key_at((zjson *)mo, i);
                    const zjson *pr = zjson_at((zjson *)mo, i);
                    int slot = r->nmood_flick;
                    double g0, g1;
                    if (!mk || !*mk || mk[0] == '_') continue;
                    if (!pr || !zjson_is(pr, ZJSON_ARR) ||
                        zjson_count((zjson *)pr) < 4) {
                        zdiag_error(diag, file, mo->line, 0, "tail_flick",
                                    "tail_flick.moods['%s'] 要写成 "
                                    "[间隔下限, 间隔上限, 幅度, 时长]", mk);
                        goto fail;
                    }
                    if (slot >= ZRIG_MAX_BLINK_MOOD) {
                        zdiag_error(diag, file, mo->line, 0, "tail_flick",
                                    "tail_flick.moods 条目过多（上限 %d）",
                                    ZRIG_MAX_BLINK_MOOD);
                        goto fail;
                    }
                    g0 = zjson_num(zjson_at((zjson *)pr, 0), 5.0);
                    g1 = zjson_num(zjson_at((zjson *)pr, 1), 13.0);
                    if (g1 < g0) {
                        zdiag_error(diag, file, mo->line, 0, "tail_flick",
                                    "tail_flick.moods['%s'] 的间隔上限 %.2f "
                                    "小于下限 %.2f", mk, g1, g0);
                        goto fail;
                    }
                    z_strlcpy(r->mood_flick[slot].mood, mk,
                              sizeof(r->mood_flick[0].mood));
                    r->mood_flick[slot].gmin = ZC_CLAMP(g0, 0.1, 600.0);
                    r->mood_flick[slot].gmax = ZC_CLAMP(g1, 0.1, 600.0);
                    r->mood_flick[slot].amp =
                        ZC_CLAMP(zjson_num(zjson_at((zjson *)pr, 2), 0.0), 0.0, 8.0);
                    r->mood_flick[slot].dur =
                        ZC_CLAMP(zjson_num(zjson_at((zjson *)pr, 3), 0.8), 0.05, 6.0);
                    r->nmood_flick++;
                }
            }
            /* 开机就按 neutral 那一档抽 —— 不这么做的话，在任何人设情绪之前
               尾巴是**完全**不抽的，而"刚启动的那十几秒"恰恰是最常被看到的。 */
            zrig_apply_mood_flick(r, "neutral");
        }
    }

    {   /* mood_params（T45.3）：情绪 → 参数值。放在 params/poses 之后解析，
           因为要按 id 找参数下标。 */
        const zjson *mp = zjson_obj_get(root, "mood_params");
        if (mp && zjson_is(mp, ZJSON_OBJ)) {
            size_t i, n = zjson_count((zjson *)mp);
            for (i = 0; i < n; ++i) {
                const char *pid = zjson_key_at((zjson *)mp, i);
                const zjson *tbl = zjson_at((zjson *)mp, i);
                int pi;
                size_t k, kn;
                if (!pid || !*pid || pid[0] == '_') continue;
                if (!tbl || !zjson_is(tbl, ZJSON_OBJ)) continue;
                pi = param_find(r, pid);
                if (pi < 0) {
                    zdiag_error(diag, file, tbl->line, 0, "mood_params",
                                "mood_params 提到了不存在的参数 '%s'", pid);
                    goto fail;
                }
                if (r->nmood_param >= ZRIG_MAX_MOOD_PARAM) {
                    zdiag_error(diag, file, tbl->line, 0, "mood_params",
                                "mood_params 条目过多（上限 %d）", ZRIG_MAX_MOOD_PARAM);
                    goto fail;
                }
                r->mood_param[r->nmood_param].param = pi;
                r->mood_param[r->nmood_param].n = 0;
                kn = zjson_count((zjson *)tbl);
                for (k = 0; k < kn; ++k) {
                    const char *mk = zjson_key_at((zjson *)tbl, k);
                    int slot = r->mood_param[r->nmood_param].n;
                    if (!mk || !*mk || mk[0] == '_') continue;
                    if (slot >= ZRIG_MAX_BLINK_MOOD) {
                        zdiag_error(diag, file, tbl->line, 0, "mood_params",
                                    "参数 '%s' 的情绪条目过多（上限 %d）",
                                    pid, ZRIG_MAX_BLINK_MOOD);
                        goto fail;
                    }
                    z_strlcpy(r->mood_param[r->nmood_param].e[slot].mood, mk,
                              sizeof(r->mood_param[0].e[0].mood));
                    r->mood_param[r->nmood_param].e[slot].v =
                        zjson_num(zjson_at((zjson *)tbl, k), 0.0);
                    r->mood_param[r->nmood_param].n++;
                }
                r->nmood_param++;
            }
        }
    }
    if (load_xfades(r, zjson_obj_get(root, "xfades"), diag, file) != 0) goto fail;

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
            {   /* blink.mood_rate: { "angry": {"rate":1.7}, "sleepy": {"rate":1.15,"closed_scale":3.0} } */
                const zjson *mr = zjson_obj_get(bj, "mood_rate");
                if (mr && mr->type == ZJSON_OBJ) {
                    size_t mi, mn = zjson_count(mr);
                    for (mi = 0; mi < mn && r->nblink_mood < ZRIG_MAX_BLINK_MOOD; ++mi) {
                        const char *k = zjson_key_at(mr, mi);
                        const zjson *v = zjson_at(mr, mi);
                        double rate, cs;
                        if (!k || !k[0] || !v || v->type != ZJSON_OBJ) continue;
                        rate = zjson_num(zjson_obj_get(v, "rate"), 1.0);
                        cs   = zjson_num(zjson_obj_get(v, "closed_scale"), 1.0);
                        /* 钳死范围：rate 失控会变成痉挛，closed_scale 失控会变成装死。
                           0.2 = 每 25 秒才眨一次（专注盯着看的上限），
                           3.0 = 每 1.7 秒一次（已经是"非常に多い"那一档）。 */
                        if (rate < 0.2) rate = 0.2;
                        if (rate > 3.0) rate = 3.0;
                        if (cs < 1.0) cs = 1.0;
                        if (cs > 8.0) cs = 8.0;
                        z_strlcpy(r->blink_mood[r->nblink_mood].mood, k,
                                  sizeof(r->blink_mood[0].mood));
                        r->blink_mood[r->nblink_mood].rate = rate;
                        r->blink_mood[r->nblink_mood].closed_scale = cs;
                        r->nblink_mood++;
                    }
                }
            }
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
        {
            const zjson *mo = zjson_obj_get(gj, "micro");
            r->sacc_amp     = zjson_num(zjson_obj_get(mo, "amp"), 0.0);
            r->sacc_gap_min = zjson_num(zjson_obj_get(mo, "gap_min"), 0.45);
            r->sacc_gap_max = zjson_num(zjson_obj_get(mo, "gap_max"), 1.60);
            r->sacc_speed   = zjson_num(zjson_obj_get(mo, "speed"), 16.0);
            if (r->sacc_gap_min < 0.05) r->sacc_gap_min = 0.05;
            if (r->sacc_gap_max < r->sacc_gap_min) r->sacc_gap_max = r->sacc_gap_min;
            if (r->sacc_speed < 1.0) r->sacc_speed = 1.0;
        }
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
            r->look_overshoot = zjson_num(zjson_obj_get(lj, "overshoot"), 0.0);
            if (r->look_speed <= 0.0) r->look_speed = 9.0;
            for (i = 0; i < n; ++i) {
                if (r->nlooks >= ZRIG_MAX_GROUPS) {
                    zdiag_error(diag, file, gs ? gs->line : 0, 0, "look.groups",
                                "look.groups 超过上限 %d", ZRIG_MAX_GROUPS);
                    goto fail;
                }
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
                r->looks[r->nlooks].lag = zjson_num(zjson_obj_get(ej, "lag_s"), 0.0);
                if (r->looks[r->nlooks].lag > 0.0) r->lookh_used = 1;
                r->nlooks++;
            }
        }
    }

    r->fade_prev = -1;
    r->expr_cur = r->expr_prev = -1;
    r->phys_last = -1.0;
    r->phys_remain = 0.0;
    r->p2_last = -1.0;
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
    /* keyform 的增量表是动态分配的（只有写了 keys 的形变器才有），必须显式释放。 */
    for (i = 0; i < r->ndeforms; ++i) {
        free(r->deforms[i].kf_d);
        r->deforms[i].kf_d = NULL;
    }
    zimg_free(r->fb);
    zimg_free(r->maskbuf);
    zimg_free(r->scratch);
    {
        int bi;
        for (bi = 0; bi < ZRIG_MAX_BANDS; ++bi) {
            zimg_free(r->band_scratch[bi]); r->band_scratch[bi] = NULL;
            zimg_free(r->band_maskbuf[bi]); r->band_maskbuf[bi] = NULL;
        }
    }
    free(r);
}

/* ============================================================ 信息 */
const char *zrig_id(const zrig *r) { return r ? r->id : ""; }
const char *zrig_name(const zrig *r) { return r ? r->name : ""; }
int zrig_canvas_w(const zrig *r) { return r ? r->cw : 0; }
int zrig_canvas_h(const zrig *r) { return r ? r->ch : 0; }
int zrig_part_count(const zrig *r) { return r ? r->nparts : 0; }
int zrig_socket_count(const zrig *r) { return r ? r->nsockets : 0; }
const char *zrig_socket_id(const zrig *r, int i)
{
    return (r && i >= 0 && i < r->nsockets) ? r->sockets[i].id : "";
}
const char *zrig_socket_group(const zrig *r, int i)
{
    if (!r || i < 0 || i >= r->nsockets) return "";
    return r->groups[r->sockets[i].group].id;
}
int zrig_socket_pos(const zrig *r, int i, double out[2])
{
    if (!r || i < 0 || i >= r->nsockets || !out) return 0;
    out[0] = r->sockets[i].pos[0];
    out[1] = r->sockets[i].pos[1];
    return 1;
}
int zrig_part_socket(const zrig *r, const char *part_id)
{
    int pi;
    if (!r || !part_id) return -1;
    pi = find_part(r, part_id);
    return pi < 0 ? -1 : r->parts[pi].socket;
}
static void group_matrix(const zrig *r, int gi, double scale, double m[6]);

int zrig_socket_screen_pos(const zrig *r, int i, double scale, double out[2])
{
    double m[6], x, y;
    if (!r || i < 0 || i >= r->nsockets || !out || scale <= 0.0) return 0;
    group_matrix(r, r->sockets[i].group, scale, m);
    x = r->sockets[i].pos[0] * scale;
    y = r->sockets[i].pos[1] * scale;
    out[0] = m[0] * x + m[2] * y + m[4];
    out[1] = m[1] * x + m[3] * y + m[5];
    return 1;
}
int zrig_action_count(const zrig *r) { return r ? r->nactions : 0; }
int zrig_region_count(const zrig *r) { return r ? r->nregions : 0; }

/* 按索引读区域定义：平台层要把区域表报给 UI，否则前端只能把 head/body/feet 硬编码，
   rig.json 改了区域前端就对不上（visemes/poses 当初也是这个理由加的）。 */
const char *zrig_region_id_at(const zrig *r, int i)
{
    if (!r || i < 0 || i >= r->nregions) return "";
    return r->regions[i].id;
}

const char *zrig_region_action_at(const zrig *r, int i)
{
    if (!r || i < 0 || i >= r->nregions) return "";
    return r->regions[i].action;
}

const char *zrig_region_cursor_at(const zrig *r, int i)
{
    if (!r || i < 0 || i >= r->nregions) return "arrow";
    return r->regions[i].cursor;
}

/* rect 回填画布坐标 [x,y,w,h]；UI 要拿它画区域框 */
int zrig_region_rect_at(const zrig *r, int i, int out[4])
{
    int k;
    if (!r || i < 0 || i >= r->nregions || !out) return 0;
    for (k = 0; k < 4; ++k) out[k] = r->regions[i].rect[k];
    return 1;
}

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

const char *zrig_action_title_at(const zrig *r, int i)
{
    if (!r || i < 0 || i >= r->nactions) return "";
    return r->actions[i].title[0] ? r->actions[i].title : r->actions[i].id;
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
            /* 收尾不在这里做：整个动作的淡出由 compute_group_transforms 按
               动作自己的 fade_out（≈ FadeOutTime）统一处理，和官方一致。 */
            return c->amp * k;
        }
        case W_FLAP: {
            /* 只往一个方向摆的余弦：0 → amp → 0 循环。
               嘴的开合必须用它——用 sine 会摆到负数，缩放成负值就是把嘴翻过来画。 */
            return c->amp * (0.5 - 0.5 * cos(2.0 * 3.14159265358979323846 * c->freq * t));
        }
        case W_DRIFT: {
            /* 「活着」的慢摆：三条**不可通约**频率的正弦叠加。
               频率比取 1 : 1/φ : φ（φ = 黄金比，1.6180339887…），两两之比都是
               无理数 ⇒ 合成波是准周期的，**永远不会精确重复**。

               为什么不能用单条 sine：拿确定性探针量过现在这条尾巴 ——
               60 秒里 12 个正峰全是 3.2279°，标准差 0.000015°，变异系数 0.0005%。
               那是节拍器，不是动物。动画教科书管这叫「僵硬的钟摆摆动」，
               真实的软组织要「C 形曲线和 S 形曲线反复切换」才有柔软感。

               权重按**和**归一（0.62 + 0.26 + 0.12 = 1.00）⇒ |输出| ≤ amp，
               绝不会顶到参数值域被 clamp 削平 —— T45.2f 刚在这上面栽过一次
               （放大倍率全被削成 1.00，而且只错一半，极难发现）。

               两条附加相位（1.7 / 4.1 弧度）是为了让三条波在 t=0 不同时过零，
               否则开场第一下会像被谁推了一把。 */
            const double TAU = 2.0 * 3.14159265358979323846;
            double w = TAU * c->freq, ph = TAU * c->phase;
            return c->amp * (0.62 * sin(w * t + ph)
                           + 0.26 * sin(w * 0.6180339887 * t + ph + 1.7)
                           + 0.12 * sin(w * 1.6180339887 * t + ph + 4.1));
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
    /* 情绪 → 摆动倍率（mood_swing）。只对**命名参数**通道生效：摆动的语义载体
       就是那条参数，直接改部件通道会把别的动作也一起缩放。
       bias 不参与缩放 —— 它是静态姿态偏置（"尾巴常态偏向一侧"），
       跟着 amp 一起放大会让尾巴整条歪出去。 */
    if (c->pparam >= 0 && c->pparam < r->nparams &&
        (r->sw_amul[c->pparam] != 1.0 || r->sw_fmul[c->pparam] != 1.0)) {
        zchan m = *c;
        m.amp  *= r->sw_amul[c->pparam];
        m.freq *= r->sw_fmul[c->pparam];
        return c->bias + eval_channel_wave(r, &m,
                                           t - r->sw_tshift[c->pparam], total);
    }
    return c->bias + eval_channel_wave(r, c, t, total);
}

/* 把一个动作在时刻 t 的所有通道按权重 w 累加进当前帧的变换数组。
   w < 1 时就是"淡入淡出"里的那一份权重，两个动作各累加一次即可。 */
/* 把一个数值写进「部件或组的某条通道」。动作、物理、参数层共用同一套语义：
   位移/旋转/形变是累加，alpha 是相乘（0.5 两次 = 0.25），缩放累加在基准 1.0 上。 */
/* 把一个通道/绑定值写进**变形器节点**。这就是"每根骨头都能被单独驱动"的落点：
   amount 走网格位移（老语义），dx/dy/rot/sx/sy 走节点自己的变换（新语义，第六十三问 P0）。 */
static void apply_deform_chan(zrig *r, int di, int param, double v)
{
    zdeform *g;
    if (di < 0 || di >= r->ndeforms) return;
    g = &r->deforms[di];
    switch (param) {
        case P_DX:    g->dx += v; break;
        case P_DY:    g->dy += v; break;
        case P_SX:    g->sx += v; break;    /* 1.0 基准的加法，和部件通道同口径 */
        case P_SY:    g->sy += v; break;
        case P_ROT:   g->rot += v; break;
        case P_AMOUNT: g->amount += v; break;
        case P_ALPHA: break;                /* 节点没有自己的透明度，静默忽略 */
        default: break;
    }
}

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
            /* 目标写形变器 id：param 决定写它的哪个量（amount = 网格位移，
               dx/dy/rot_deg/sx/sy = 节点变换）。不写 param 时 load_channels 已默认成 amount。 */
            apply_deform_chan(r, c->deform, c->param, v);
            continue;
        }
        apply_chan(r, c->part, c->group, c->param, v, c->curve, c->strips);
    }
}

/* 回读 want 时刻的参数值（行波延迟 bind.lag 用）。
   线性插值；历史比 lag 还短时取**最老**的一帧，不外推 —— 外推会在刚加载的
   头几帧甩出一个假峰。 */
static double lag_sample(const zrig *r, int pi, double want)
{
    int n = r->lag_fill, h = r->lag_head, k;
    if (h < 0) return 0.0;
    if (n <= 1) return r->lag_v[pi][h];
    for (k = 0; k < n; ++k) {
        int idx = (h - k + ZRIG_LAG_SLOTS * 2) % ZRIG_LAG_SLOTS;
        if (r->lag_t[idx] <= want) {
            int nxt;
            double t0, t1, u;
            if (k == 0) return r->lag_v[pi][idx];   /* 比最新帧还新：就是当前值 */
            nxt = (idx + 1) % ZRIG_LAG_SLOTS;       /* 它后面那一帧（时间更晚） */
            t0 = r->lag_t[idx];
            t1 = r->lag_t[nxt];
            u = (t1 - t0 > 1e-9) ? (want - t0) / (t1 - t0) : 0.0;
            if (u < 0.0) u = 0.0;
            if (u > 1.0) u = 1.0;
            return r->lag_v[pi][idx] + (r->lag_v[pi][nxt] - r->lag_v[pi][idx]) * u;
        }
    }
    return r->lag_v[pi][(h - (n - 1) + ZRIG_LAG_SLOTS * 2) % ZRIG_LAG_SLOTS];
}

/* 回读 want 时刻的跟随方向（zlook.lag 用）。体例照抄上面的 lag_sample：
   线性插值、历史不够长时取最老一帧**不外推**（外推会在刚加载的头几帧甩出假峰）。 */
static void lookh_sample(const zrig *r, double want, double *ox, double *oy)
{
    int n = r->lookh_fill, h = r->lookh_head, k;
    if (h < 0) { *ox = r->look_cx; *oy = r->look_cy; return; }
    if (n <= 1) { *ox = r->lookh_x[h]; *oy = r->lookh_y[h]; return; }
    for (k = 0; k < n; ++k) {
        int idx = (h - k + ZRIG_LAG_SLOTS * 2) % ZRIG_LAG_SLOTS;
        if (r->lookh_t[idx] <= want) {
            int nxt;
            double t0, t1, u;
            if (k == 0) { *ox = r->lookh_x[idx]; *oy = r->lookh_y[idx]; return; }
            nxt = (idx + 1) % ZRIG_LAG_SLOTS;
            t0 = r->lookh_t[idx];
            t1 = r->lookh_t[nxt];
            u = (t1 - t0 > 1e-9) ? (want - t0) / (t1 - t0) : 0.0;
            if (u < 0.0) u = 0.0;
            if (u > 1.0) u = 1.0;
            *ox = r->lookh_x[idx] + (r->lookh_x[nxt] - r->lookh_x[idx]) * u;
            *oy = r->lookh_y[idx] + (r->lookh_y[nxt] - r->lookh_y[idx]) * u;
            return;
        }
    }
    {
        int old = (h - (n - 1) + ZRIG_LAG_SLOTS * 2) % ZRIG_LAG_SLOTS;
        *ox = r->lookh_x[old];
        *oy = r->lookh_y[old];
    }
}

/* 自发抽动（tail_flick）：在动作通道之外，往摆动参数上叠一个**非周期**的脉冲。
   这是「桌宠自己操控尾巴」的那一半 —— 慢摆只是底噪，抽动才是它自己的决定。
   结构和自动眨眼同构：排一个将来的时刻，到点起一次，起完再排下一个。 */
static void accumulate_tail_flick(zrig *r)
{
    const double PI = 3.14159265358979323846;
    int k;
    if (r->flick_off || r->nflick_param <= 0 || r->flick_amp <= 0.0) return;
    for (k = 0; k < r->nflick_param; ++k) {
        int pi = r->flick_param[k];
        double u;
        if (pi < 0 || pi >= r->nparams) continue;
        /* 没排过班，或者时间往回跳了（探针逐个情绪重跑会把 now 拨回 0）：重排。 */
        if (r->flick_st[k].next_t < 0.0 ||
            r->flick_st[k].next_t > r->now + r->flick_gmax + r->flick_dur * 2.0) {
            r->flick_st[k].next_t =
                r->now + zrand_range(&r->flick_rng, r->flick_gmin, r->flick_gmax);
            r->flick_st[k].t0 = -1.0;
        }
        if (r->flick_st[k].t0 < 0.0 && r->now >= r->flick_st[k].next_t) {
            /* 起一次：方向随机，力度 ±35%、时长 ±25% 各自抖一抖。
               **每一下都不一样大** —— 这正是「节拍器 vs 动物」的分界线。 */
            double sgn = (zrand_range(&r->flick_rng, 0.0, 1.0) < 0.5) ? -1.0 : 1.0;
            r->flick_st[k].t0  = r->now;
            r->flick_st[k].dur = r->flick_dur * zrand_range(&r->flick_rng, 0.8, 1.3);
            r->flick_st[k].amp = sgn * r->flick_amp * r->flick_scale[k]
                               * zrand_range(&r->flick_rng, 0.65, 1.35);
            r->flick_st[k].next_t = r->now + r->flick_st[k].dur
                + zrand_range(&r->flick_rng, r->flick_gmin, r->flick_gmax);
        }
        if (r->flick_st[k].t0 < 0.0) continue;
        u = (r->now - r->flick_st[k].t0) / r->flick_st[k].dur;
        if (u < 0.0 || u >= 1.0) { r->flick_st[k].t0 = -1.0; continue; }
        /* 抽动的形：**急出缓回**的阻尼振荡 exp(−4.2u)·sin(1.6πu)。
           猫的 flick 是「弹」出去再晃回来，不是对称的来回摆，所以要衰减包络
           而不是定幅正弦；1.6 个半周期 = 弹出去、回摆过头一点、收住。
           (1−u⁴) 是收尾闸：不乘它，u→1 时还剩 4% 的值然后被硬切成 0，
           那一下是个阶跃（在物理链上会炸出一个假抖）。
           除以 0.3694 把峰值归一到 1.0（极值在 u=0.174，解析可得），
           这样表里的 amp 就是「参数单位的真实峰值」，不是个要靠猜的系数。 */
        r->p_action[pi] += r->flick_st[k].amp
            * exp(-4.2 * u) * sin(PI * 1.6 * u) * (1.0 - u * u * u * u) / 0.3694;
    }
}

/* 归一化三次贝塞尔的单轴求值：端点固定在 0/1，只由两个控制点决定。
   （Live2D 官方的参数曲线是"参数-位移平面上的贝塞尔"，四个绝对坐标；
     这里刻意改成 CSS 那种"这一段怎么走"的归一化曲线 —— 见 kf_seg_ease 的注释。） */
static double bez_axis(double p1, double p2, double t)
{
    double u = 1.0 - t;
    return 3.0 * u * u * t * p1 + 3.0 * u * t * t * p2 + t * t * t;
}

/* timing curve：给 x（段内线性进度），返回 y（位移权重）。
   x1/x2 被限制在 [0,1]（加载时校验），所以 x(t) 单调 —— 直接二分 40 次，
   误差 2^-40；每帧每个形变器只调一次，不值得上牛顿法。 */
static double bez_y(const double *b, double x)
{
    double lo = 0.0, hi = 1.0, m;
    int it;
    if (x <= 0.0) return 0.0;
    if (x >= 1.0) return 1.0;
    for (it = 0; it < 40; ++it) {
        m = 0.5 * (lo + hi);
        if (bez_axis(b[0], b[2], m) < x) lo = m; else hi = m;
    }
    return bez_axis(b[1], b[3], 0.5 * (lo + hi));
}

/* 第 k 段（第 k-1 组 key → 第 k 组 key）的段内缓动：线性进度 t → 位移权重。
   三种写法共用这一个入口：名字缓动（z_ease_apply，含回弹/弹性）、三次贝塞尔、阶梯。
   为什么要有它：只有线性插值时"中间鼓两边收"这类形状只能靠堆 key 逼近，
   而 key 越多越难调、越容易在参数中间段抖一下（这是第六十五问 P0-3）。 */
static double kf_seg_ease(const zdeform *g, int k, double t)
{
    if (t <= 0.0) return 0.0;
    if (t >= 1.0) return 1.0;          /* 阶梯也在到点这一下给 1，否则永远走不到下一组 key */
    if (g->kf_step[k]) return 0.0;
    if (g->kf_bez_on[k]) return bez_y(g->kf_bez[k], t);
    return z_ease_apply(g->kf_ease[k], t);
}

/* keyform 求值（第六十三问 P0）：参数值 → 相邻两组 key 的插值权重。
   每帧只算一次，结果存 kf_w[]，渲染时每个顶点按权重线性组合增量表。
   为什么不能并进渲染：一张网格可能被 3~4 个部件引用（同部件多网格累加），
   放进渲染就是每帧重算几十遍同一个插值。 */
static void deform_update_keys(zrig *r)
{
    int i;
    for (i = 0; i < r->ndeforms; ++i) {
        zdeform *g = &r->deforms[i];
        double v;
        int k;
        if (g->nkf <= 0 || g->param < 0) continue;
        for (k = 0; k < g->nkf; ++k) g->kf_w[k] = 0.0;
        /* 读**合成后**的参数值（动作 → 表情 → 口型），和 bind 走同一个口径：
           否则动作曲线推 ParamXxx 时网格不动，只有滑条动 —— 那是最难查的一类 bug。 */
        /* lag 走的是和 bind 同一口井（参数历史环）：keyform 自己不再另存一份历史。
           为什么 keyform 也要 lag：网格从 amount 通路改成 keyform 之后，
           bind 的迟滞就没了 —— 侧发/裙摆那种"根先动、梢后动"会整条一起动，
           看着立刻变硬（G66.12）。 */
        v = (g->kf_lag > 0.0) ? lag_sample(r, g->param, r->now - g->kf_lag)
                              : param_effective(r, g->param);
        if (v <= g->kf_v[0]) continue;                        /* 低于第一组：第 0 组 */
        if (v >= g->kf_v[g->nkf - 1]) { g->kf_w[g->nkf - 1] = 1.0; continue; }
        for (k = 1; k < g->nkf; ++k) {
            if (v <= g->kf_v[k]) {
                double span = g->kf_v[k] - g->kf_v[k - 1];
                double t = (span > 1e-12) ? (v - g->kf_v[k - 1]) / span : 0.0;
                double te = kf_seg_ease(g, k, t);   /* 线性进度 → 缓动后的权重（T66.11） */
                g->kf_w[k - 1] += 1.0 - te;
                g->kf_w[k]     += te;
                break;
            }
        }
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
    for (i = 0; i < r->ndeforms; ++i) {
        zdeform *dg = &r->deforms[i];
        dg->amount = 0.0;
        /* 节点的局部变换也每帧清零重算：漏清一次，一根被"拧"过的骨头会永远歪着。 */
        dg->dx = dg->dy = dg->rot = 0.0;
        dg->sx = dg->sy = 1.0;
    }
    for (i = 0; i < r->nparams; ++i) r->p_action[i] = 0.0;
    if (!a) { r->dim_now = 0.0; return; }
    if (prev && r->fade_dur > 1e-6) {
        double u = ZC_CLAMP((r->now - r->fade_t0) / r->fade_dur, 0.0, 1.0);
        w = z_ease_sine(u);                  /* 官方 CubismMath.getEasingSine */
        if (u >= 1.0) { r->fade_prev = -1; prev = NULL; w = 1.0; }
    } else {
        prev = NULL;
    }
    if (prev) {
        /* 淡出的那个动作继续往前走（Live2D 也是这么做的，不然会卡在最后一帧）。
           它同样要吃自己的 FadeOutTime：官方每个 motion 的淡出是挂在
           motion 身上的，不是挂在"谁接替它"身上。漏掉这一乘，动作演完的
           那一帧会把 pulse 的满值整个闪出来（实测 ParamArmLA 0 → 2.67）。 */
        double tp = r->now - r->fade_prev_t0;
        double totp = prev->loop ? -1.0 : prev->duration;
        double wp = 1.0 - w;
        if (totp > 0.0 && prev->fade_out > 1e-6)
            wp *= z_ease_sine((totp - tp) / prev->fade_out);
        accumulate_action(r, prev, tp, wp, totp);
    }
    {
        /* 非循环动作的收尾淡出（≈ Live2D 的 FadeOutTime）：
           官方 tmpFadeOut = getEasingSine((endTime − now) / fadeOutSeconds)，
           循环动作（endTime < 0）不淡出。整段动作一起收，所以不管通道写的是
           哪种波形都能平稳落地，不用再给某一种波形开后门。 */
        double el = zsm_elapsed(&r->sm);
        double tot = a->loop ? -1.0 : a->duration;
        if (tot > 0.0 && a->fade_out > 1e-6)
            w *= z_ease_sine((tot - el) / a->fade_out);
        accumulate_action(r, a, el, w, tot);
    }
    /* 环境摆动：按**绝对时刻**求值，所以动作怎么切它都连续（T45.9）。
       放在动作之后、抽动之前 —— 三者都往 p_action 累加，顺序不影响结果，
       但这个排法读起来就是「编排好的动作 → 一直在跑的底噪 → 它自己的抽动」。 */
    if (r->has_ambient && !r->ambient_off)
        accumulate_action(r, &r->ambient, r->now, 1.0, -1.0);
    accumulate_tail_flick(r);   /* 自发抽动叠在动作通道之上，一起走 binds（含行波延迟） */
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
        double pain_v_l = 0.0, pain_v_r = 0.0, wide_v_l = 0.0, wide_v_r = 0.0;
        r->blink_now = r->blink_value;
        /* 微动叠在"用户/动作设定的视线"之上，但**不回写 gaze_x** ——
           gaze_x 是读数（测试台滑条、/api/param 读它），
           把底噪混进读数会让"我设了 0.5 怎么读出来 0.53"这种鬼问题冒出来。 */
        r->gaze_nx = ZC_CLAMP(r->gaze_x + r->sacc_x, -1.0, 1.0);
        r->gaze_ny = ZC_CLAMP(r->gaze_y + r->sacc_y, -1.0, 1.0);
        if (r->lag_used) {
            /* 行波延迟环推进。★ 只在**时钟真的往前走了**的时候才占一个新格子。
               理由是 /api/pause 的契约（src/headless/main_headless.c:63）：
               「暂停后所有 tick 都用同一个时间戳，于是连续两帧**逐字节相同**」——
               引擎必须对"同一时刻重复 tick"幂等。第一版每 tick 都推进一格，
               冻结时钟下环会一直转，回读到的历史跟着变，连拍的帧就不再相同，
               api_smoke 的「笑眼归零回到原样」这类像素对照当场挂掉。
               时间没走就**原地覆盖**当前格（参数值可能被 /api/param 改了）。
               时间往回跳（重设时钟）则把历史清空 —— 留着会让插值跨过负的时间差。 */
            int fresh = 1;
            if (r->lag_fill > 0 && r->lag_head >= 0) {
                if (r->now < r->lag_t[r->lag_head]) r->lag_fill = 0;
                else if (r->now <= r->lag_t[r->lag_head]) fresh = 0;
            }
            if (fresh) {
                r->lag_head = (r->lag_head + 1) % ZRIG_LAG_SLOTS;
                r->lag_t[r->lag_head] = r->now;
                if (r->lag_fill < ZRIG_LAG_SLOTS) r->lag_fill++;
            }
        }
        for (i = 0; i < r->nparams; ++i) {
            const zparam *q = &r->params[i];
            /* 叠加序：动作通道（≈ .motion3 曲线）→ 表情 → 口型音素（官方 LipSync 排在表情之后） */
            double v = param_effective(r, i);
            double off = v - q->value;
            int k;
            if (r->lag_used && r->lag_head >= 0) r->lag_v[i][r->lag_head] = v;
            /* 交叉淡化的权重跟着**合成后**的参数值走（不是参数自身的值）：
               踮脚是动作曲线在推 ParamTiptoe，读 q->value 的话永远是 0。 */
            if (r->nxfades > 0) {
                int xi;
                for (xi = 0; xi < r->nxfades; ++xi) {
                    zxfade *xf = &r->xfades[xi];
                    if (xf->param != (int)i) continue;
                    xf->w = ZC_CLAMP((v - xf->in0) / (xf->in1 - xf->in0), 0.0, 1.0);
                }
            }
            switch (q->builtin) {
                case PBI_ANGLE_X:   lx += off / 30.0; continue;
                case PBI_ANGLE_Y:   ly -= off / 30.0; continue;
                case PBI_EYE_OPEN:  r->blink_now = ZC_CLAMP(r->blink_now - off, 0.0, 1.0); continue;
                case PBI_EYE_L_OPEN: blink_off_l += off; continue;
                case PBI_EYE_R_OPEN: blink_off_r += off; continue;
                /* 笑眼没有别的子系统在写，直接取最终值（不像睁眼那样要算相对眨眼的偏移） */
                case PBI_EYE_L_SMILE: smile_v_l = v; continue;
                case PBI_EYE_R_SMILE: smile_v_r = v; continue;
                case PBI_EYE_L_PAIN: pain_v_l = v; continue;
                case PBI_EYE_R_PAIN: pain_v_r = v; continue;
                case PBI_EYE_L_WIDE: wide_v_l = v; continue;
                case PBI_EYE_R_WIDE: wide_v_r = v; continue;
                case PBI_EYEBALL_X: r->gaze_nx = ZC_CLAMP(r->gaze_nx + off, -1.0, 1.0); continue;
                case PBI_EYEBALL_Y: r->gaze_ny = ZC_CLAMP(r->gaze_ny + off, -1.0, 1.0); continue;
                default: break;
            }
            if (q->nbind <= 0) continue;
            for (k = 0; k < q->nbind; ++k) {
                const zpbind *b = &r->pbinds[q->bind0 + k];
                /* 行波：带 lag 的绑定读的是 lag 秒之前的值。尾巴梢比尾巴根慢
                   半拍，形状才会在 C 形和 S 形之间来回变（动画的 wave principle）。 */
                double src = (b->lag > 0.0)
                           ? lag_sample(r, i, r->now - b->lag) : v;
                double bv = src * b->scale + b->offset;
                if (fabs(bv) < 1e-12) continue;
                if (b->deform >= 0 && b->deform < r->ndeforms) {
                    apply_deform_chan(r, b->deform, b->param, bv);
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
        /* 痛苦闭眼：和笑眼同类，也隐含闭眼（>_< 本来就是闭着的）。 */
        r->pain_l = ZC_CLAMP(pain_v_l, 0.0, 1.0);
        r->pain_r = ZC_CLAMP(pain_v_r, 0.0, 1.0);
        if (r->pain_l > r->blink_l) r->blink_l = r->pain_l;
        if (r->pain_r > r->blink_r) r->blink_r = r->pain_r;
        /* 瞪大眼：**不**动 blink —— 眼睛是睁着的。
           眨眼期间怎么退场**不在这里**算：补片同时挂着 eye_open 标签，
           走的是和常态睁眼件一模一样的那条曲线（blink 0.45 前全出、0.55 后才轮到闭眼件）。
           第一版在这里乘了 (1 − blink)，结果眨到一半变成"补片 50% + 常态眼件 50%"
           两条上眼线一起画，糊成重影 —— 交叉淡化必须硬交接，不能两头都半透明。 */
        r->wide_l = ZC_CLAMP(wide_v_l, 0.0, 1.0);
        r->wide_r = ZC_CLAMP(wide_v_r, 0.0, 1.0);

        /* 指针跟随叠加在动作之上（Live2D 里这是参数层，不属于任何一个 motion）。
           放在动作之后、物理之前：所以转头也会把头发甩起来。 */
        for (i = 0; i < r->nlooks; ++i) {
            const zlook *lk = &r->looks[i];
            double glx = lx, gly = ly;
            if (lk->group < 0 || lk->group >= r->ngroups) continue;
            /* 带 lag 的组读**过去**的方向：头先转，身子后到。 */
            if (lk->lag > 0.0) lookh_sample(r, r->now - lk->lag, &glx, &gly);
            r->g_rot[lk->group] += lk->rot * glx;
            r->g_dx[lk->group]  += lk->dx  * glx;
            r->g_dy[lk->group]  += lk->dy  * gly;
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
    if (ph->n_in > 0) {                  /* 参数输入（官方 physics3 的 Input） */
        int k;
        double sum = 0.0;
        for (k = 0; k < ph->n_in; ++k)
            sum += param_effective(r, ph->in_param[k]) * ph->in_weight[k];
        *out_x = *out_y = sum;
        return;
    }
    if (ph->driver_phys >= 0) {          /* 多段摆：输入 = 上一段**这一个固定步**的输出 */
        /* ⚠ 这里读 out_cur 不是 out_last：out_last 是插值到渲染时刻的值，
           拿它当下一段的输入会让摆链在子步之间混进半拍的未来值。
           driver_phys 保证比自己小，所以同一子步里父段已经算完。 */
        *out_x = *out_y = r->phys[ph->driver_phys].out_cur;
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
    /* 关掉物理：把所有摆的输出清零并让状态跟上目标，这样再打开时不会"攒了一大口气"。
       用途是排查接缝 —— 冻结时钟时物理的 pos 不再积分，而改参数会让 target 立刻跳，
       输出 pos-target 被人为拉满，剖面上就会凭空多出假跳变
       （2026-10-14 实测虚报过一处 +2.35px 的"躯干底边接缝"）。 */
    if (!r->phys_enabled) {
        for (i = 0; i < r->nphys; ++i) {
            double ix, iy, in;
            zphys *ph = &r->phys[i];
            if (ph->part < 0) continue;
            physics_input(r, ph, &ix, &iy);
            in = (ph->axis == 1) ? iy : ix;
            ph->pos = in * ph->ratio;      /* 停在目标上 = 零滞后 */
            ph->vel = 0.0;
            ph->out_last = ph->out_prev = ph->out_cur = 0.0;
            ph->in_prev = in; ph->in_init = 1;
        }
        r->phys_last = now;
        r->phys_remain = 0.0;
        return;
    }
    if (r->phys_last < 0.0) { r->phys_last = now; return; }
    dt = now - r->phys_last;
    r->phys_last = now;
    if (dt < 0.0) dt = 0.0;
    /* ── 固定步长积分（照搬官方 CubismPhysics::Evaluate，见 ZRIG_PHYS_* 的注释）──
       ⚠ 不要写成 "dt 一大步 + clamp"：那是显式欧拉过冲，低帧率下惯性被放大数倍。 */
    r->phys_remain += dt;
    if (r->phys_remain > ZRIG_PHYS_MAX_REMAIN) r->phys_remain = 0.0;  /* 挂起太久就别追了 */
    while (r->phys_remain >= ZRIG_PHYS_STEP) {
        /* 输入线性插值：官方那句
             _parameterCaches[j] = _parameterInputCaches[j]*(1-w) + parameterValues[j]*w
           的等价物。没有它的话，一帧里的 N 个子步会共用同一个"帧末输入"，
           摆等于被瞬移的目标拽了 N 次。 */
        double inw = ZRIG_PHYS_STEP / r->phys_remain;
        if (inw > 1.0) inw = 1.0;
        for (i = 0; i < r->nphys; ++i) {
            zphys *ph = &r->phys[i];
            double ix, iy, in_now, in, target, acc;
            if (ph->part < 0 || (ph->driver < 0 && ph->driver_phys < 0 && ph->n_in == 0)) continue;
            physics_input(r, ph, &ix, &iy);
            in_now = (ph->axis == 1) ? iy : ix;
            if (!ph->in_init) { ph->in_prev = in_now; ph->in_init = 1; }
            in = ph->in_prev * (1.0 - inw) + in_now * inw;
            ph->in_prev = in;
            target = in * ph->ratio;
            acc = ph->stiffness * (target - ph->pos) - ph->damping * ph->vel;
            ph->vel += acc * ZRIG_PHYS_STEP;
            ph->pos += ph->vel * ZRIG_PHYS_STEP;
            /* 输出 = 摆尖相对驱动位置的落后量：静止时 pos→target，输出归零，
               所以它只加"惯性"，不会把头发永久吹偏。 */
            ph->out_prev = ph->out_cur;
            ph->out_cur  = ZC_CLAMP(ph->pos - target, -ph->max, ph->max);
        }
        r->phys_remain -= ZRIG_PHYS_STEP;
    }
    /* 渲染时刻落在两个固定步之间 → 按余量插值（官方的 Interpolate）。
       ⚠ 写通道这一段必须**每帧都跑**，即使这一帧一个子步都没走：
         p_dx/p_rot/deform.amount 每帧都被清零重算，漏一帧头发就会"啪"地归位。 */
    {
        double alpha = r->phys_remain / ZRIG_PHYS_STEP;
        if (alpha < 0.0) alpha = 0.0;
        if (alpha > 1.0) alpha = 1.0;
        for (i = 0; i < r->nphys; ++i) {
            zphys *ph = &r->phys[i];
            ph->out_last = ph->out_prev * (1.0 - alpha) + ph->out_cur * alpha;
        }
    }
    for (i = 0; i < r->nphys; ++i) {
        zphys *ph = &r->phys[i];
        double out = ph->out_last;
        if (ph->part < 0 || (ph->driver < 0 && ph->driver_phys < 0 && ph->n_in == 0)) continue;
        if (ph->deform >= 0 && ph->deform < r->ndeforms) {
            r->deforms[ph->deform].amount += out;
            continue;
        }
        if (ph->pparam >= 0 && ph->pparam < r->nparams) {
            r->p_action[ph->pparam] += out;     /* 和动作通道挤同一个累加位 */
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

/* 摆链这一帧的输入：根点被驱动组带着走了多少像素 + 参数补的位移 + 额外倾角。
   和旧摆的 physics_input 是同一招（拿部件锚点过一遍组矩阵），
   差别只在**旧的二选一、这里是叠加**：组矩阵带不动的那些纯形变参数用 input 补。 */
/* ★ 输入限幅：官方 physics3 的输入经过 Normalization 夹在 ±10「模型单位」里，
   而摆长 Radius 也在同一套单位里（常见 5~15）—— 所以"根点一帧能跑多远"
   天然就有上限。我们的输入是**像素**，没有这个天然上限：实测把
   ParamAngleX 从 −30 一帧跳到 +30，发根瞬移 123px，而第一节摆长才 48px，
   摆直接被甩过头顶 —— 单帧 179° 的翻转，那是在转圈不是在摆。
   所以这一层补两道闸（这是 T47.2 的适配层做的，内核 zphys2 保持纯净）：
     in_max  位移模长上限（相当于官方的 NormalizationPosition.Maximum）
     in_rate 位移变化速度上限（像素/秒）—— 真人转头 0.25s 走 61px ≈ 244px/s，
             300px/s 不影响正常动作，只拦住"参数瞬跳"这种非物理输入。
   实测效果：同样的瞬跳，峰值从 179° 降到 47°，1 秒后残抖 <1°。 */
static void p2_input(const zrig *r, zp2chain *c,
                     double *tx, double *ty, double *ang, double dt)
{
    int k;
    double len;
    *tx = *ty = *ang = 0.0;
    if (c->driver >= 0 && c->part >= 0) {
        double m[6], x0 = r->parts[c->part].pos[0], y0 = r->parts[c->part].pos[1];
        group_matrix(r, c->driver, 1.0, m);
        *tx = (m[0] * x0 + m[2] * y0 + m[4]) - x0;
        *ty = (m[1] * x0 + m[3] * y0 + m[5]) - y0;
    }
    for (k = 0; k < c->n_in; ++k) {
        double v = param_effective(r, c->in_param[k]);
        *tx += v * c->in_wx[k];
        *ty += v * c->in_wy[k];
    }
    for (k = 0; k < c->n_ain; ++k)
        *ang += param_effective(r, c->ain_param[k]) * c->ain_w[k];

    len = sqrt((*tx) * (*tx) + (*ty) * (*ty));
    if (c->in_max > 0.0 && len > c->in_max) {
        *tx *= c->in_max / len;
        *ty *= c->in_max / len;
    }
    if (c->in_seen && c->in_rate > 0.0 && dt > 0.0) {
        double dx = *tx - c->in_last_x, dy = *ty - c->in_last_y;
        double d = sqrt(dx * dx + dy * dy), cap = c->in_rate * dt;
        if (d > cap && d > 1e-12) {
            *tx = c->in_last_x + dx * cap / d;
            *ty = c->in_last_y + dy * cap / d;
        }
    }
    c->in_last_x = *tx;
    c->in_last_y = *ty;
    c->in_seen = 1;
}

/* 物理 2.0 的每帧推进 + 输出适配（T47.2）。
   顺序上必须排在 compute_group_transforms 之后、渲染之前，和旧摆一样。

   ⚠ 写通道这一段**每帧都要跑**，即使这一帧一个固定步都没走：
     p_dx / p_rot / deform.amount 每帧清零重算，漏一帧头发就会"啪"地归位。 */
static void physics2_update(zrig *r, double now)
{
    double dt;
    int i, k;
    if (r->np2 <= 0) return;
    if (!r->phys_enabled) {
        /* 关物理：链按重力摆直、输出清零。和旧摆同一个开关，排查接缝时一起关。 */
        for (i = 0; i < r->np2; ++i) {
            zphys2_reset(&r->p2[i].ch, r->p2_gx, r->p2_gy);
            r->p2[i].in_seen = 0;      /* 再打开时别从旧位置猛拉一下 */
            for (k = 0; k < r->p2[i].nout; ++k) r->p2[i].out[k].applied = 0.0;
        }
        r->p2_last = now;
        r->p2_wind_ex = r->p2_wind_ey = 0.0;
        return;
    }
    if (r->p2_last < 0.0) { r->p2_last = now; return; }
    dt = now - r->p2_last;
    r->p2_last = now;
    if (dt < 0.0) dt = 0.0;

    {   /* 本帧的合成风。微风用两路**不可公度**的正弦相加（0.11Hz 与它的 2.71 倍），
           听不出周期，又不用随机数 —— 随机数会让"同一时刻"两次渲染结果不同，
           A/B 对照图和固定步长回放就全废了（DC53 的同一个理由）。 */
        double bz = 0.0, gk = 0.0;
        if (r->p2_breeze_amp > 0.0) {
            const double TAU = 2.0 * 3.14159265358979323846;
            bz = r->p2_breeze_amp *
                 (0.62 * sin(TAU * r->p2_breeze_hz * now) +
                  0.38 * sin(TAU * r->p2_breeze_hz * 2.71 * now + 1.3));
        }
        if (r->p2_gust_left > 0.0 && r->p2_gust_dur > 0.0) {
            /* 阵风包络：瞬间起、指数落（真实的一阵风就是这样，不是方波） */
            double u = 1.0 - r->p2_gust_left / r->p2_gust_dur;   /* 0→1 */
            gk = exp(-3.2 * u);
            r->p2_gust_left -= dt;
            if (r->p2_gust_left < 0.0) r->p2_gust_left = 0.0;
        }
        r->p2_wind_ex = r->p2_wx + bz + r->p2_gust_x * gk;
        r->p2_wind_ey = r->p2_wy + r->p2_gust_y * gk;
    }

    for (i = 0; i < r->np2; ++i) {
        zp2chain *c = &r->p2[i];
        double tx, ty, ang;
        p2_input(r, c, &tx, &ty, &ang, dt);
        /* 固定步长、输入插值、帧间插值都在内核里（zphys2_advance），这里只喂输入 */
        zphys2_advance(&c->ch, tx, ty, ang,
                       r->p2_gx, r->p2_gy, r->p2_wind_ex, r->p2_wind_ey, dt);
        for (k = 0; k < c->nout; ++k) {
            zp2out *o = &c->out[k];
            /* 这就是 T47.2 的那句翻译：摆角(度) × 倍率 → 限幅 → 写进通道 */
            double v = zphys2_out(&c->ch, o->particle) * o->scale;
            if (o->inverted) v = -v;
            v = ZC_CLAMP(v, -o->max, o->max);
            o->applied = v;
            if (o->deform >= 0 && o->deform < r->ndeforms) {
                r->deforms[o->deform].amount += v;
                continue;
            }
            /* 写命名参数：和动作通道挤同一个 p_action 累加位（官方也是"物理叠在参数上"）。
               注意顺序：keyform 在这之后求值（见 rig_update 的注释），所以同帧就能吃到。 */
            if (o->pparam >= 0 && o->pparam < r->nparams) {
                r->p_action[o->pparam] += v;
                continue;
            }
            if (o->part < 0) continue;
            switch (o->param) {
                case P_DX:  r->p_dx[o->part]  += v; break;
                case P_DY:  r->p_dy[o->part]  += v; break;
                case P_ROT: r->p_rot[o->part] += v; break;
                case P_BEND_Y:
                    r->p_bendy[o->part] += v; r->p_bendcy[o->part] = o->curve; break;
                case P_BEND_X:
                default:
                    r->p_bendx[o->part] += v; r->p_bendcx[o->part] = o->curve; break;
            }
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

/* ── 变形器树（第六十三问 P0）：A_chain ────────────────────────────────
   一个部件这一帧的最终矩阵 = A_chain · 组矩阵 · 部件矩阵。
   A_chain 是"从本部件往上直到 root"所有节点变换的连乘（父包住子），
   与 Live2D 的 deformer 树同序：点先过子节点、再过父节点。

   哪些节点进链：① 挂在本部件上的所有网格形变器（含它们各自的父链）；
                ② 部件自己用 "deformer" 点名的那根链。
   为什么按**下标升序**连乘就行：加载时强制 parent 必须先声明（parent 下标 < 子下标），
   升序即"父→子"，配合 out = out · local 就是父包住子。                    */
static void deform_local_matrix(const zrig *r, int di, double scale, double m[6])
{
    const zdeform *g = &r->deforms[di];
    double px = g->pivot[0] * scale, py = g->pivot[1] * scale;
    zimg_make_matrix(m, px + g->dx * scale, py + g->dy * scale,
                     g->sx, g->sy, g->rot, px, py);
}

static void deform_mark_chain(const zrig *r, int pi, int *mark)
{
    int i, x;
    memset(mark, 0, sizeof(int) * (size_t)ZRIG_MAX_DEFORMS);
    for (i = 0; i < r->ndeforms; ++i) {
        if (r->deforms[i].part != pi) continue;
        for (x = i; x >= 0 && x < ZRIG_MAX_DEFORMS && !mark[x]; ) {
            mark[x] = 1;
            x = r->deforms[x].parent;
        }
    }
    if (pi >= 0 && pi < r->nparts && r->parts[pi].deformer >= 0) {
        for (x = r->parts[pi].deformer; x >= 0 && x < ZRIG_MAX_DEFORMS && !mark[x]; ) {
            mark[x] = 1;
            x = r->deforms[x].parent;
        }
    }
}

/* 从链的根连乘到第 upto 个节点（含）。upto < 0 = 整条链。
   T66.10 才需要"只连到某个祖先为止"的版本：取父级 warp 时，子件顶点要映进
   **父件自己的**坐标系，而那个坐标系只包含到父件为止的变换（再往下就把子的
   变换乘进去了，等于自己套自己）。 */
static void deform_chain_matrix_upto(const zrig *r, const int *mark, int upto,
                                     double scale, double out[6])
{
    int i;
    out[0] = 1.0; out[1] = 0.0; out[2] = 0.0;
    out[3] = 1.0; out[4] = 0.0; out[5] = 0.0;
    for (i = 0; i < r->ndeforms; ++i) {
        double loc[6], acc[6];
        if (!mark[i]) continue;
        if (upto >= 0 && i > upto) break;
        if (r->deforms[i].dx == 0.0 && r->deforms[i].dy == 0.0 &&
            r->deforms[i].rot == 0.0 &&
            r->deforms[i].sx == 1.0 && r->deforms[i].sy == 1.0) continue;
        deform_local_matrix(r, i, scale, loc);
        zimg_matrix_mul(acc, out, loc);
        memcpy(out, acc, sizeof(acc));
    }
}

static void deform_chain_matrix(const zrig *r, int pi, double scale, double out[6])
{
    int mark[ZRIG_MAX_DEFORMS];
    deform_mark_chain(r, pi, mark);
    /* 单位矩阵。⚠ 这个项目的 6 元素矩阵是 [a,b,c,d,e,f]（e/f 是平移），
       单位阵是 [1,0,0,1,0,0] —— 第一版写成 [1,0,0,0,1,0]，把纵向缩放抹成 0，
       整张立绘被压成一条线（画面只剩 29 个不透明像素）。矩阵初始化错了不会有任何
       报错，只会"什么都画不出来"，所以这里必须写清楚。 */
    deform_chain_matrix_upto(r, mark, -1, scale, out);
}

/* 一张网格第 q 个控制点这一帧挪多少（源图像素）。
   amount 通路与 keyform 通路的**唯一**求值点：渲染和 zrig_deform_mesh 都走这里，
   免得探针量到的数和画出来的数不是一回事（这类"探针自证"以前吃过亏）。 */
static void deform_vertex_at(const zdeform *g, int q, double *dx, double *dy)
{
    if (g->nkf > 0 && g->kf_d) {
        /* 第 0 组是绝对位移，其余组是增量：顶点 = P0 + Σ w_k · D_k */
        int kk;
        double x = g->ox[q], y = g->oy[q];
        for (kk = 1; kk < g->nkf; ++kk) {
            size_t bse = ((size_t)kk * (size_t)g->kf_np + (size_t)q) * 2;
            x += g->kf_w[kk] * g->kf_d[bse];
            y += g->kf_w[kk] * g->kf_d[bse + 1];
        }
        *dx = x;
        *dy = y;
        return;
    }
    *dx = g->ox[q] * g->amount;
    *dy = g->oy[q] * g->amount;
}

/* ── 父级 warp 的位移场（T66.10 / G58.8）──────────────────────────────
   为什么需要它：节点树现在只传**刚体**变换（位移/旋转/缩放）。父级网格把一片
   区域揉弯之后，挂在它下面的**别的部件**只会跟着整体位移，逐顶点的弯一点都吃不到
   —— 三节发链因此"看起来像链、断起来像两截"，裙摆也没法带起下面那条里布。

   Live2D 的口径（官方 combinaton 页 + creatorsforum「メッシュがワープから
   はみ出すと自動補間されて挙動がおかしくなる」）：
     父 warp 的网格是**一张位移场**，子部件（アートメッシュ）的每个顶点都要在该
     场里取值后一起挪；子件超出父 warp 范围的部分会被"自动补间"（我们取边界值，
     也就是把场往外延），所以**warp 要盖住整个部件**。

   这里做的是同一件事，分三步：
     ① 子件顶点（画布坐标）→ 反解进祖先件的素材坐标（只包含到那个祖先为止的
        链矩阵，再往下就把子自己的变换乘进去了）；
     ② 在祖先件的 (cols×rows) 控制点网格上双线性取位移（deform_field_at）；
     ③ 位移换成画布向量（乘祖先件的矩阵线性部分），再反解回**子件自己的素材像素**
        （乘子件矩阵线性部分的逆）——因为 mesh[] 的口径是"子件素材像素"。
   多个祖先时逐层相加；都按**未位移**的位置取值（链一般只有一层 warp，误差小于
   一个像素，和 Live2D 的近似同量级）。 */

/* 双线性取形变场在归一化坐标 (u,v) 处的位移（单位 = 该件的素材像素）。
   u/v 会被夹到 [0,1]：超出 warp 的顶点按边界值走（"场往外延"），
   既不突然归零也不外插出奇怪的摆幅。 */
static void deform_field_at(const zdeform *g, double u, double v,
                            double *dx, double *dy)
{
    int cols = g->cols, rows = g->rows, c0, r0, q00;
    double fx, fy, tx, ty, d[4][2];
    *dx = *dy = 0.0;
    if (cols < 1 || rows < 1) return;
    if (u < 0.0) u = 0.0; else if (u > 1.0) u = 1.0;
    if (v < 0.0) v = 0.0; else if (v > 1.0) v = 1.0;
    fx = u * cols; fy = v * rows;
    c0 = (int)floor(fx); r0 = (int)floor(fy);
    if (c0 < 0) c0 = 0; else if (c0 > cols - 1) c0 = cols - 1;
    if (r0 < 0) r0 = 0; else if (r0 > rows - 1) r0 = rows - 1;
    tx = fx - c0; if (tx < 0.0) tx = 0.0; else if (tx > 1.0) tx = 1.0;
    ty = fy - r0; if (ty < 0.0) ty = 0.0; else if (ty > 1.0) ty = 1.0;
    q00 = r0 * (cols + 1) + c0;
    deform_vertex_at(g, q00, &d[0][0], &d[0][1]);
    deform_vertex_at(g, q00 + 1, &d[1][0], &d[1][1]);
    deform_vertex_at(g, q00 + (cols + 1), &d[2][0], &d[2][1]);
    deform_vertex_at(g, q00 + (cols + 1) + 1, &d[3][0], &d[3][1]);
    *dx = (d[0][0] * (1.0 - tx) + d[1][0] * tx) * (1.0 - ty)
        + (d[2][0] * (1.0 - tx) + d[3][0] * tx) * ty;
    *dy = (d[0][1] * (1.0 - tx) + d[1][1] * tx) * (1.0 - ty)
        + (d[2][1] * (1.0 - tx) + d[3][1] * tx) * ty;
}

/* 一个部件自己的"组矩阵 · 部件矩阵"（画布坐标）。
   给父级 warp 用：要把它自己的顶点映回素材坐标，就得知道它这一帧被摆在哪里。
   刻意只取**素材自有**的量（位置/缩放/旋转/锚点 + 本件的 dx/dy/rot 通道），
   不参与视线、眨眼、跟随父件形变那几条 —— 那几条只对脸有意义，而父级 warp
   的典型使用者是头发/裙子/袖子这类件。 */
static void part_base_matrix(const zrig *r, int pid, double scale, double out[6])
{
    const zpart *p = &r->parts[pid];
    const zimg *src = p->img_scaled ? p->img_scaled : p->img;
    double lm[6], gm[6];
    double ax = 0.0, ay = 0.0;
    if (src) { ax = src->w * p->anchor[0]; ay = src->h * p->anchor[1]; }
    zimg_make_matrix(lm,
                     (p->pos[0] + r->p_dx[pid]) * scale,
                     (p->pos[1] + r->p_dy[pid]) * scale,
                     p->scale * (p->scale_x + (r->p_sx[pid] - 1.0)),
                     p->scale * (p->scale_y + (r->p_sy[pid] - 1.0)),
                     p->rot_deg + r->p_rot[pid],
                     ax, ay);
    if (p->group >= 0) {
        group_matrix(r, p->group, scale, gm);
        zimg_matrix_mul(out, gm, lm);
    } else {
        memcpy(out, lm, sizeof(lm));
    }
}

/* 2×2 线性部分求逆（6 元素仿射矩阵的左上角）。返回 0 = 退化（缩放 0），
   这种情况直接放弃继承，别把 NaN 写进顶点。 */
static int mat_linear_inv(const double m[6], double inv[4])
{
    double det = m[0] * m[3] - m[1] * m[2];
    if (fabs(det) < 1e-12) return 0;
    inv[0] =  m[3] / det;
    inv[1] = -m[2] / det;
    inv[2] = -m[1] / det;
    inv[3] =  m[0] / det;
    return 1;
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

/* 眨眼的开合曲线：原本是线性斜坡，改成两端慢、中段快的 S 曲线。

   为什么要改（2026-10-14 实测）：眼睛闭到 0.35~0.75 这一段最难看 ——
   睁眼图要到 0.75 才开始淡出，这之前全靠眼眶压扁来表现闭合，而上眼线的
   行程（实测值，不能乱调）只够走一半，于是中间几帧会露出一条水平硬边，
   虹膜像被平切了一刀。用户截图反馈"眼睛很怪"就是撞上这几帧。

   线性斜坡在这段难看区间里要待 0.4*(0.1+0.15) = 100ms，占整次眨眼的三分之一，
   60fps 下约 6 帧。换成 smoothstep 之后同一段只要约 0.27 的参数行程，
   停留时间降到 ~68ms。真人眨眼本来也是中段最快、到位前后慢，所以这个改动
   既更好看也更像真的。

   注意这里只改"时间 → 闭合度"的映射，不动 lash_travel / aperture_min /
   交叉淡化阈值 —— 那几个是逐列实测出来的，动它们会掉回已知的坏结果
   （"眼白露在眼线上方"）。*/
static double z_blink_shape(double u)
{
    if (u <= 0.0) return 0.0;
    if (u >= 1.0) return 1.0;
    return u * u * (3.0 - 2.0 * u);
}

static double blink_update(zrig *r, double now)
{
    if (r->blink_manual >= 0.0) {       /* 外部按住：测试台拖滑条时用 */
        r->blink_value = ZC_CLAMP(r->blink_manual, 0.0, 1.0);
        return r->blink_value;
    }
    if (!r->blink_enabled || r->blink_forced == 1) {
        r->blink_value = (r->blink_forced == 1) ? 1.0 : 0.0;
        /* ⚠ blink_hold 是**动作**要求的闭合度（睡觉 1.0、眯眼笑 0.55），和
           "自动眨眼定时器开不开"是两码事。以前这里直接 return，于是
           zrig_blink_set_enabled(r,0) 之后睡觉动作的眼睛是睁着的，
           测试台把自动眨眼一关也复现不出动作该有的闭眼（2026-10-15 发现：
           为笑眼时序写的闸因为这个在关眨眼的测试里永远绿，变异检验才暴露）。
           下面这段和函数末尾那段是同一个口径：只抬不压。 */
        {
            const zaction *a = current_action(r);
            if (a && a->blink_hold >= 0.0 && a->blink_hold > r->blink_value)
                r->blink_value = a->blink_hold;
        }
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
                /* ⚠ 这里用 gap/rate 现算，而不是抽签时就把 rate 乘进去：
                   情绪是会中途变的，抽签时乘死的话，刚被惹毛还要等上一轮
                   最长 8 秒的间隔走完才看得出来。现算 = 换情绪立刻生效。 */
                if (dt >= r->blink_gap / ZC_MAX(r->blink_rate, 1e-3)) {
                    r->blink_state = BL_CLOSING;
                    r->blink_t0 = now;
                }
                break;
            case BL_CLOSING:
                r->blink_value = z_blink_shape(
                    ZC_CLAMP(dt / ZC_MAX(r->blink_closing, 1e-3), 0.0, 1.0));
                if (r->blink_value >= 1.0) { r->blink_state = BL_CLOSED; r->blink_t0 = now; }
                break;
            case BL_CLOSED:
                r->blink_value = 1.0;
                if (dt >= r->blink_closed * ZC_MAX(r->blink_closed_scale, 1.0)) {
                    r->blink_state = BL_OPENING; r->blink_t0 = now;
                }
                break;
            case BL_OPENING:
                r->blink_value = 1.0 - z_blink_shape(
                    ZC_CLAMP(dt / ZC_MAX(r->blink_opening, 1e-3), 0.0, 1.0));
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

int zrig_phys_count(const zrig *r) { return r ? r->nphys : 0; }

const char *zrig_phys_id(const zrig *r, int i)
{
    return (r && i >= 0 && i < r->nphys) ? r->phys[i].id : NULL;
}

/* ---- 物理 2.0 的读数口（调试端点与单测用）---- */
int zrig_phys2_count(const zrig *r) { return r ? r->np2 : 0; }

const char *zrig_phys2_id(const zrig *r, int i)
{
    return (r && i >= 0 && i < r->np2) ? r->p2[i].id : NULL;
}

static const zp2chain *p2_find(const zrig *r, const char *id)
{
    int i;
    if (!r || !id) return NULL;
    for (i = 0; i < r->np2; ++i)
        if (strcmp(r->p2[i].id, id) == 0) return &r->p2[i];
    return NULL;
}

int zrig_phys2_particles(const zrig *r, const char *id)
{
    const zp2chain *c = p2_find(r, id);
    return c ? c->ch.n : 0;
}

double zrig_phys2_angle(const zrig *r, const char *id, int particle)
{
    const zp2chain *c = p2_find(r, id);
    return c ? zphys2_out(&c->ch, particle) : 0.0;
}

int zrig_phys2_out_count(const zrig *r, const char *id)
{
    const zp2chain *c = p2_find(r, id);
    return c ? c->nout : 0;
}

double zrig_phys2_applied(const zrig *r, const char *id, int out_index)
{
    const zp2chain *c = p2_find(r, id);
    if (!c || out_index < 0 || out_index >= c->nout) return 0.0;
    return c->out[out_index].applied;
}

void zrig_phys2_force(zrig *r, double gx, double gy, double wx, double wy)
{
    if (!r) return;
    if (gx == 0.0 && gy == 0.0) gy = 1.0;   /* 重力不许是零向量 */
    r->p2_gx = gx; r->p2_gy = gy;
    r->p2_wx = wx; r->p2_wy = wy;
}

void zrig_phys2_force_get(const zrig *r, double *gx, double *gy, double *wx, double *wy)
{
    if (!r) return;
    if (gx) *gx = r->p2_gx;
    if (gy) *gy = r->p2_gy;
    if (wx) *wx = r->p2_wx;
    if (wy) *wy = r->p2_wy;
}

void zrig_phys2_breeze(zrig *r, double amp, double hz)
{
    if (!r) return;
    if (amp < 0.0) amp = 0.0;
    if (amp > ZRIG_BREEZE_MAX) amp = ZRIG_BREEZE_MAX;
    r->p2_breeze_amp = amp;
    if (hz > 0.0 && hz <= 2.0) r->p2_breeze_hz = hz;
}

double zrig_phys2_breeze_amp(const zrig *r) { return r ? r->p2_breeze_amp : 0.0; }

void zrig_phys2_gust(zrig *r, double wx, double wy, double sec)
{
    if (!r) return;
    wx = ZC_CLAMP(wx, -ZRIG_GUST_MAX, ZRIG_GUST_MAX);
    wy = ZC_CLAMP(wy, -ZRIG_GUST_MAX, ZRIG_GUST_MAX);
    if (!(sec > 0.0)) sec = 0.6;
    if (sec > ZRIG_GUST_MAX_SEC) sec = ZRIG_GUST_MAX_SEC;
    r->p2_gust_x = wx;
    r->p2_gust_y = wy;
    r->p2_gust_dur = sec;
    r->p2_gust_left = sec;
}

/* 本帧真正喂进内核的风（定常 + 微风 + 阵风）。调试端点读它，
   否则"我设了风"和"风真的吹到头发上了"是两件事，又会变成看不见的失效。 */
void zrig_phys2_wind_now(const zrig *r, double *wx, double *wy)
{
    if (!r) return;
    if (wx) *wx = r->p2_wind_ex;
    if (wy) *wy = r->p2_wind_ey;
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

/* 变形器树的读取接口（第六十三问 P0）。测试台与单测靠它们看"树接没接上"——
   只看画面是分不清"节点旋转生效"和"部件自己转了一下"的。 */
int zrig_deform_parent(const zrig *r, const char *id)
{
    int i = r ? find_deform(r, id) : -1;
    return i >= 0 ? r->deforms[i].parent : -1;
}

const char *zrig_deform_parent_id(const zrig *r, const char *id)
{
    int i = r ? find_deform(r, id) : -1;
    if (i < 0 || r->deforms[i].parent < 0) return NULL;
    return r->deforms[r->deforms[i].parent].id;
}

/* 节点的局部变换量：param 取 dx / dy / rot_deg / sx / sy。查不到返回 0（sx/sy 返回 1）。 */
double zrig_deform_transform(const zrig *r, const char *id, const char *param)
{
    int i = r ? find_deform(r, id) : -1;
    const zdeform *g;
    if (i < 0) return 0.0;
    g = &r->deforms[i];
    if (z_streq(param, "dx")) return g->dx;
    if (z_streq(param, "dy")) return g->dy;
    if (z_streq(param, "rot_deg")) return g->rot;
    if (z_streq(param, "sx")) return g->sx;
    if (z_streq(param, "sy")) return g->sy;
    if (z_streq(param, "amount")) return g->amount;
    return 0.0;
}

/* 这张网格这一帧的控制点位移（源图像素）：写进 dx/dy（各 cap 个），返回控制点数。
   0 = 没有这个形变器 / 不是网格节点。它和渲染走同一个 deform_vertex_at。 */
int zrig_deform_mesh(const zrig *r, const char *id,
                     int *cols, int *rows, double *dx, double *dy, int cap)
{
    int i = r ? find_deform(r, id) : -1;
    const zdeform *g;
    int np, q;
    if (i < 0) return 0;
    g = &r->deforms[i];
    if (g->cols < 1 || g->rows < 1) return 0;
    np = (g->cols + 1) * (g->rows + 1);
    if (cols) *cols = g->cols;
    if (rows) *rows = g->rows;
    for (q = 0; q < np && q < cap; ++q) {
        double vx, vy;
        deform_vertex_at(g, q, &vx, &vy);
        if (dx) dx[q] = vx;
        if (dy) dy[q] = vy;
    }
    return np;
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

double zrig_eye_pain(const zrig *r, int side)
{
    if (!r) return 0.0;
    return side ? r->pain_r : r->pain_l;
}

double zrig_eye_wide(const zrig *r, int side)
{
    if (!r) return 0.0;
    return side ? r->wide_r : r->wide_l;
}

void zrig_blink_set_enabled(zrig *r, int enabled) { if (r) r->blink_enabled = enabled; }
void zrig_phys_set_enabled(zrig *r, int enabled) { if (r) r->phys_enabled = enabled; }
int  zrig_phys_enabled(const zrig *r) { return r ? r->phys_enabled : 0; }
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
void zrig_blink_set_mood(zrig *r, const char *mood)
{
    int i;
    if (!r) return;
    r->blink_rate = 1.0;
    r->blink_closed_scale = 1.0;
    r->blink_mood_cur[0] = 0;
    if (!mood || !mood[0]) return;
    z_strlcpy(r->blink_mood_cur, mood, sizeof(r->blink_mood_cur));
    for (i = 0; i < r->nblink_mood; ++i) {
        if (z_streq(r->blink_mood[i].mood, mood)) {
            r->blink_rate = r->blink_mood[i].rate;
            r->blink_closed_scale = r->blink_mood[i].closed_scale;
            return;
        }
    }
    /* 表里没有这个情绪 = 维持常态，不是错误：情绪词表归平台层管，
       rig 只给它关心的几个写条目。 */
}

double zrig_blink_rate(const zrig *r) { return r ? r->blink_rate : 1.0; }
double zrig_blink_closed_scale(const zrig *r) { return r ? r->blink_closed_scale : 1.0; }
const char *zrig_blink_mood(const zrig *r) { return r ? r->blink_mood_cur : ""; }
int zrig_blink_mood_count(const zrig *r) { return r ? r->nblink_mood : 0; }

void zrig_blink_force(zrig *r, int mode)
{
    if (!r) return;
    r->blink_forced = (mode > 0) ? 1 : -1;
}

/* 手动点一次抽动（「抖耳朵」「甩尾巴」这类点播动作用）。
   ★ 刻意**不另开一套播放逻辑**：只是把排班表上的 next_t 拨到当下，
     剩下的交给 accumulate_tail_flick 原样处理。好处是点出来的那一下
     和它自己抖的那一下**走的是同一段代码** —— 力度/时长/方向照样每次都抖，
     不会出现"手动的很整齐、自发的很随机"这种一眼假。
   prefix = 参数名前缀（"ParamEar" / "ParamAccTail"）；NULL = 全部。 */
void zrig_flick_trigger(zrig *r, const char *prefix)
{
    int k;
    if (!r || r->flick_off || r->flick_amp <= 0.0) return;
    for (k = 0; k < r->nflick_param; ++k) {
        int pi = r->flick_param[k];
        if (pi < 0 || pi >= r->nparams) continue;
        if (prefix && *prefix && strncmp(r->params[pi].id, prefix, strlen(prefix)) != 0)
            continue;
        /* 正在抖的那条不要打断 —— 连点两下不该让它卡在半路重来。 */
        if (r->flick_st[k].t0 >= 0.0) continue;
        r->flick_st[k].next_t = r->now;
    }
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
        if (newi >= 0 && newi < r->nactions && r->actions[newi].flick_pre[0])
            zrig_flick_trigger(r, r->actions[newi].flick_pre);
    }
    r->cur_t0 = entered;

    /* 指针跟随要平滑，否则鼠标一跳头就瞬移 */
    {
        double dt = (r->look_last < 0.0) ? 0.0 : now - r->look_last;
        double k;
        r->look_last = now;
        if (dt < 0.0) dt = 0.0;
        if (dt > 0.25) dt = 0.25;
        if (r->look_overshoot <= 0.0) {
            k = 1.0 - exp(-r->look_speed * dt);
            r->look_cx += (r->look_x - r->look_cx) * k;
            r->look_cy += (r->look_y - r->look_cy) * k;
        } else {
            /* 阻尼弹簧：ζ<1 ⇒ 冲过去一点再荡回来 = 官方说的"反动/刹车"。
               固定 1/60 步长 + 累加器，理由同 G113 的物理积分：
               整帧 dt 单步积分在低帧率下会过冲到失真，而我们恰恰可能跑在 10fps 的
               预览里。步长固定后，10fps 和 60fps 出来的曲线一致。 */
            const double H = 1.0 / 60.0;
            double zeta = 1.0 - ZC_CLAMP(r->look_overshoot, 0.0, 0.95);
            double w = r->look_speed;       /* 固有角频率沿用原来的"跟手速度" */
            int guard = 0;
            r->look_acc += dt;
            if (r->look_acc > 0.5) r->look_acc = 0.5;   /* 卡顿后不追补几百步 */
            while (r->look_acc >= H && guard++ < 64) {
                double ax = w * w * (r->look_x - r->look_cx) - 2.0 * zeta * w * r->look_vx;
                double ay = w * w * (r->look_y - r->look_cy) - 2.0 * zeta * w * r->look_vy;
                r->look_vx += ax * H;
                r->look_vy += ay * H;
                r->look_cx += r->look_vx * H;
                r->look_cy += r->look_vy * H;
                r->look_acc -= H;
            }
        }

        /* 写跟随历史环。★ 只在时钟真往前走了才占新槽 —— /api/pause 的契约要求
           「同一时间戳重复 tick 必须逐字节相同」，每 tick 都推进会让暂停期间
           历史被同一个值灌满，lag 组于是慢慢"追上"头，画面在暂停中偷偷变化。 */
        if (r->lookh_used) {
            int fresh = 1;
            if (r->lookh_fill > 0 && r->lookh_head >= 0) {
                if (now < r->lookh_t[r->lookh_head]) r->lookh_fill = 0;       /* 时钟倒流：丢历史 */
                else if (now <= r->lookh_t[r->lookh_head]) fresh = 0;
            }
            if (fresh) {
                r->lookh_head = (r->lookh_head + 1) % ZRIG_LAG_SLOTS;
                r->lookh_t[r->lookh_head] = now;
                r->lookh_x[r->lookh_head] = r->look_cx;
                r->lookh_y[r->lookh_head] = r->look_cy;
                if (r->lookh_fill < ZRIG_LAG_SLOTS) r->lookh_fill++;
            } else {
                r->lookh_x[r->lookh_head] = r->look_cx;
                r->lookh_y[r->lookh_head] = r->look_cy;
            }
        }

        /* 转脸 / 换视线时带一次眨眼。
           Live2D 官方《提高动态质量的技巧》第 4 条原话：
           "人在转脸或换视线时经常眨眼"
           （docs.live2d.com/zh-CHS/cubism-editor-tutorials/motion-hint/）。
           在这之前我们的眨眼是纯随机定时器，和视线毫无关系 —— 眼珠转过去、
           眼皮一动不动，正是那篇教程说的"看起来像一个机器人"。

           两个刻意的设计：
             · 用"自上次触发以来累计移动了多远"而不是瞬时速度 —— 慢慢扫过去
               和猛地转过去都该眨，判据应该是位移不是速度。
             · 只有 55% 概率真眨。每次都眨同样像机器人，官方那句说的是"经常"
               不是"总是"。 */
        /* 眼球微动：每隔 gap 换一个新的微小目标，然后快速趋近过去。
           刻意**不走 look_cx** —— 微动是眼球自己的事，不该带着脑袋一起晃。 */
        if (r->sacc_amp > 0.0) {
            if (!r->sacc_init) { r->sacc_next = now; r->sacc_init = 1; }
            if (now >= r->sacc_next) {
                r->sacc_tx = zrand_range(&r->sacc_rng, -r->sacc_amp, r->sacc_amp);
                r->sacc_ty = zrand_range(&r->sacc_rng, -r->sacc_amp, r->sacc_amp);
                r->sacc_next = now + zrand_range(&r->sacc_rng,
                                                 r->sacc_gap_min, r->sacc_gap_max);
            }
            {
                double ks = 1.0 - exp(-r->sacc_speed * dt);
                r->sacc_x += (r->sacc_tx - r->sacc_x) * ks;
                r->sacc_y += (r->sacc_ty - r->sacc_y) * ks;
            }
        } else {
            r->sacc_x = r->sacc_y = 0.0;
        }

        if (!r->look_blink_init) {
            r->look_blink_x = r->look_cx;
            r->look_blink_y = r->look_cy;
            r->look_blink_init = 1;
        } else if (r->blink_enabled && r->blink_state == BL_INTERVAL
                   && now - r->look_blink_last >= LOOK_BLINK_COOLDOWN) {
            double mx = r->look_cx - r->look_blink_x;
            double my = r->look_cy - r->look_blink_y;
            if (mx * mx + my * my >= LOOK_BLINK_DIST * LOOK_BLINK_DIST) {
                r->look_blink_x = r->look_cx;
                r->look_blink_y = r->look_cy;
                r->look_blink_last = now;
                if (zrand_range(&r->rng, 0.0, 1.0) < LOOK_BLINK_CHANCE)
                    zrig_blink_trigger(r);
            }
        }
    }

    blink_update(r, now);
    viseme_update(r, now);
    params_refresh_builtin(r);
    compute_group_transforms(r);
    physics_update(r, now);
    physics2_update(r, now);
    /* keyform 必须在**所有**参数来源都定稿之后算：动作 / 表情 / 口型 / 物理 2.0
       （T66.11c 起物理也能写命名参数）。以前放在物理前面是因为"物理只写 amount，
       两边不重叠"；现在物理写参数了，早算一帧就等于网格永远慢一帧。 */
    deform_update_keys(r);
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
    /* 一个部件的显隐可能被两件事决定：
         ① 它**属于**某个档位 ⇒ 跟着那个档位的权重走（官方 pose3.json 的本来语义）；
         ② 它被某个档位**点名藏起来**（entries[].hide）⇒ 那个档位越显，它越透明。
       ② 是本引擎的扩展，为了「扎起来的发型要把披着的侧发收上去」这类需求：
       侧发在 bob / long 两档里都要露，而官方语义下一个部件只能归一个档位，
       真要照官方做就得把同一绺侧发复制成两份美术资源。
       登记在 docs/LIVE2D_CONFORMANCE.md。 */
    double op = 1.0;
    int gi, t, q;
    for (gi = 0; gi < r->nposes; ++gi) {
        const zpose *g = &r->poses[gi];
        for (t = 0; t < g->nent; ++t) {
            const zposeent *e = &r->poseents[g->ent0 + t];
            for (q = 0; q < e->nmem; ++q)
                if (r->posemem[e->mem0 + q] == part) op *= e->opacity;
            for (q = 0; q < e->nhid; ++q)
                if (r->posehide[e->hid0 + q] == part) op *= 1.0 - e->opacity;
        }
    }
    if (op < 0.0) op = 0.0;
    return op;
}

/* 一个部件这一帧要怎么画：贴图、矩阵、透明度、弯曲、网格形变。
   抽出来是为了让遮罩可以**按需当场渲染**（不然遮罩缓冲只能靠绘制顺序凑）。
   返回 0 = 这一帧它根本不出现（透明度为 0 / 眨眼交叉淡化到头）。 */
typedef struct {
    const zimg *src;
    double m[6];
    double opacity;
    double bx, by;
    double bend_tmin;
    double bend_tmax;
    int    curve_x, curve_y;
    int    warped;
    const zdeform *dg;
    double mesh[ZRIG_MAX_DEFPTS * 2];
} zdrawst;

/* 把链上**别的部件**的 warp 位移场叠进 st->mesh（T66.10 / G58.8）。
   调用点：compute_draw_state 里算完本部件自己的网格之后、返回之前。

   两个入口口径：
     · 子件自己有网格（st->dg 非空）→ 用子件的 cols/rows 采样祖先的场，
       两者分辨率不同也无所谓（双线性）；
     · 子件**没有网格**（st->dg 为空）→ 借祖先那张网格的分辨率给子件现搭一张。
       这就是"三条带子不用各写一张网格，也能被同一片布带着起伏"的关键：
       带子只要在链上，场就够用。 */
static void deform_inherit_parent_warp(zrig *r, int pi, int mi, double scale,
                                       zdrawst *st)
{
    int mark[ZRIG_MAX_DEFORMS], smark[ZRIG_MAX_DEFORMS];
    int i, c, rr, cols, rows, q, borrow = -1;
    int src = -1;                 /* >=0 = 显式 inherit_from（T66.10b），用 smark 算链 */
    int *use_mark = mark;
    const zpart *cp = &r->parts[pi];
    const zimg *csrc = cp->img_scaled ? cp->img_scaled : cp->img;
    double cm[6], cinv[4];
    double wamp = cp->warp_inherit;   /* 继承强度（显式模式才有意义） */

    if (r->ndeforms <= 0 || !csrc || csrc->w <= 0 || csrc->h <= 0) return;
    deform_mark_chain(r, pi, mark);
    if (cp->inherit_from >= 0) {
        src = cp->inherit_from;
        if (!(wamp > 0.0)) return;                  /* 0 = 明确写了"不跟随"，白跑一趟没意义 */
        /* 源件的链单独算（两个部件不一定在同一棵树上；混用一张 mark 会把两棵树
           的变换按节点顺序乘在一起，得到一个谁也没写过的矩阵）。 */
        deform_mark_chain(r, src, smark);
        use_mark = smark;
    }
    /* 先扫一遍：有没有"挂在别的部件上的网格节点"可继承。没有就立刻返回 ——
       这是绝大多数部件每帧的常态，不能为它付矩阵求逆的钱。
       显式模式只认**源件自己**的网格节点（写了 inherit_from 就只跟那一件，
       不再叠加祖先链上的 —— 否则同一份位移会被算两次）。 */
    for (i = 0; i < r->ndeforms; ++i) {
        const zdeform *g = &r->deforms[i];
        if (!use_mark[i] || g->cols < 1 || g->rows < 1 || g->part < 0) continue;
        if (src >= 0) {
            if (g->part != src) continue;
        } else if (g->part == pi || g->part == mi) {
            continue;
        }
        borrow = i;
        break;
    }
    if (borrow < 0) return;

    if (st->dg) {
        cols = st->dg->cols; rows = st->dg->rows;
    } else {
        /* 借分辨率：网格顶点数上限由引擎常量兜住（≤16×16），和正常网格同一口锅 */
        cols = r->deforms[borrow].cols; rows = r->deforms[borrow].rows;
        st->dg = &r->deforms[borrow];
        for (q = 0; q < (cols + 1) * (rows + 1) * 2; ++q) st->mesh[q] = 0.0;
    }
    memcpy(cm, st->m, sizeof(cm));
    if (!mat_linear_inv(cm, cinv)) return;      /* 子件被缩成 0，这一帧本来也看不见 */

    for (i = 0; i < r->ndeforms; ++i) {
        const zdeform *g = &r->deforms[i];
        const zpart *ap;
        const zimg *asrc;
        double base[6], chain[6], am[6], ainv[4], k, np;
        if (!use_mark[i] || g->cols < 1 || g->rows < 1 || g->part < 0) continue;
        if (src >= 0) {
            if (g->part != src) continue;
        } else if (g->part == pi || g->part == mi) {
            continue;
        }
        ap = &r->parts[g->part];
        asrc = ap->img_scaled ? ap->img_scaled : ap->img;
        if (!asrc || asrc->w <= 0 || asrc->h <= 0) continue;
        part_base_matrix(r, g->part, scale, base);
        deform_chain_matrix_upto(r, use_mark, i, scale, chain);
        zimg_matrix_mul(am, chain, base);        /* 祖先件这一帧的绘制矩阵 */
        if (!mat_linear_inv(am, ainv)) continue;
        k = (ap->img && ap->img->w > 0) ? (double)asrc->w / (double)ap->img->w : 1.0;
        for (rr = 0; rr <= rows; ++rr) {
            for (c = 0; c <= cols; ++c) {
                double u = (double)c / (double)cols;
                double v = (double)rr / (double)rows;
                double px = csrc->w * u, py = csrc->h * v;
                double cx = cm[0] * px + cm[2] * py + cm[4];
                double cy = cm[1] * px + cm[3] * py + cm[5];
                double lx, ly, fdx, fdy, dcx, dcy;
                /* ① 画布 → 祖先件的素材坐标 */
                lx = ainv[0] * (cx - am[4]) + ainv[1] * (cy - am[5]);
                ly = ainv[2] * (cx - am[4]) + ainv[3] * (cy - am[5]);
                /* ② 在该件的控制点网格上取位移（素材像素） */
                deform_field_at(g, lx / (double)asrc->w, ly / (double)asrc->h,
                                &fdx, &fdy);
                if (fdx == 0.0 && fdy == 0.0) continue;
                fdx *= k; fdy *= k;
                /* 继承强度：里布/布带跟得比主体少，差出来的那一层才是"里子" */
                fdx *= wamp; fdy *= wamp;
                /* ③ 祖先素材位移 → 画布向量 → 子件素材像素 */
                dcx = am[0] * fdx + am[2] * fdy;
                dcy = am[1] * fdx + am[3] * fdy;
                np = (double)(rr * (cols + 1) + c) * 2.0;
                st->mesh[(int)np]     += cinv[0] * dcx + cinv[1] * dcy;
                st->mesh[(int)np + 1] += cinv[2] * dcx + cinv[3] * dcy;
            }
        }
    }
}

static int compute_draw_state(zrig *r, int pi, double scale, double blink,
                              const zaction *a, zdrawst *st)
{
    zpart *p = &r->parts[pi];
    /* motion_from：通道值照抄别的部件（透け眉这类"同一零件画两遍"用）。
       位置、遮罩、透明度仍然是自己的。
       ⚠ 2026-10-16：alpha 以前错写成 p_alpha[mi]，和上面这行注释自相矛盾。
       后果是**差分件没法用 motion_from** —— 星形虹膜照抄常态虹膜的位移/缩放
       （正是想要的），却连带把"常态虹膜已被 ParamStarEye 淡成 0"也抄了过来，
       于是切到星星眼时两张虹膜一起消失，眼睛变成两颗空白眼球（实测截图）。
       alpha 必须是自己的：差分切换的整个前提就是"同一位置、两张图各自淡入淡出"。
       现有的 motion_from 用户（brow_*_ghost / mouth_cavity）都没有 alpha 绑定，
       所以这一改对它们是逐像素不变的（tests/test_core.c 的 motion_from 用例守着）。 */
    int mi = (p->motion_from >= 0) ? p->motion_from : pi;
    double opacity = p->opacity * r->p_alpha[pi] * pose_opacity(r, pi);
    double extra_dx = r->p_dx[mi], extra_dy = r->p_dy[mi];
    double part_rot = r->p_rot[mi];
    double part_sx, part_sy;
    double smile = 0.0, pain = 0.0, wide = 0.0;
    double gm[6], lm[6];
    const zimg *src = p->img_scaled ? p->img_scaled : p->img;

    memset(st, 0, sizeof(*st));
    if (!src) return 0;
    /* 左眼件只看 ParamEyeLOpen，右眼件只看 ParamEyeROpen（眨单眼 / 笑眼都靠这个）。 */
    if (p->eye_side == 1) { blink = r->blink_l; smile = r->smile_l; pain = r->pain_l; wide = r->wide_l; }
    else if (p->eye_side == 2) { blink = r->blink_r; smile = r->smile_r; pain = r->pain_r; wide = r->wide_r; }
    /* 视线跟随：只影响带 gaze 标签的部件（虹膜拆分后自动升级为真·视线） */
    if ((p->tags & TAG_GAZE) && (r->gaze_nx != 0.0 || r->gaze_ny != 0.0)) {
        extra_dx += r->gaze_nx * r->gaze_max_dx;
        extra_dy += r->gaze_ny * r->gaze_max_dy;
    }
    /* 眼睑：闭合度变成往下滑的位移，但前半程按住不动（见 lash_hold 的注释）。
       lash_hold = 0 时退化成旧的线性行程，两端（0 和 1）在任何 hold 下都不变。 */
    if (p->tags & TAG_EYELID) {
        double h = p->lash_hold;
        double u = (blink - h) / ((1.0 - h) > 1e-6 ? (1.0 - h) : 1e-6);
        extra_dy += z_blink_shape(ZC_CLAMP(u, 0.0, 1.0)) * p->eyelid_travel;
    }
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
    if ((p->tags & TAG_EYE_APERTURE) && blink > 0.0) {
        part_sy *= 1.0 - blink * (1.0 - p->aperture_min);
    }

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
    /* 表情级部件覆盖：作为独立表情轨淡入淡出，覆盖几何值可与动作覆盖叠加。 */
    expr_part_override(r, pi, &opacity, &extra_dx, &extra_dy);
    /* 眨眼：睁眼件和闭眼件只在最后四分之一闭合行程交叉淡化。
       0.85 之前不画闭眼补片；由原眼睑的下移表现半闭，避免中途双线/灰影。
       全闭时闭眼补片仍满不透明，睁眼件归零。 */
    /* ⚠ 这里**不能**再看 r->blink_enabled：enabled 只管"自动眨眼定时器要不要跑"，
       不管"这一帧眼睛闭了多少"。曾经写成 (blink_enabled && blink>0.001)，结果关掉
       自动眨眼之后，任何把闭合度推离 0 的东西（表情的 ParamEyeOpen、手动按住、
       blink_hold）都会跳过淡化 → 闭眼件以 100% 不透明直接盖住睁眼件 = 整只眼睛
       突然全闭。判据只看 blink 本身。 */
    if (blink > 0.001) {
        if (p->tags & TAG_EYE_OPEN)
            opacity *= ZC_CLAMP((1.0 - blink) / 0.15, 0.0, 1.0);
        if (p->tags & TAG_EYE_CLOSED)
            opacity *= ZC_CLAMP((blink - 0.85) / 0.15, 0.0, 1.0);
        if (p->tags & TAG_FX_EYE_OPEN)
            opacity *= FX_EYE_OPEN_FLOOR + (1.0 - FX_EYE_OPEN_FLOOR)
                       * ZC_CLAMP((1.0 - blink) / 0.45, 0.0, 1.0);
    }
    /* 笑眼和闭眼是同一条睫毛线的两种形状（山型 / 谷型），两张一起画会叠成一团黑：
       笑眼涨多少，谷型闭眼就让多少。笑眼件本身也走"最后 25% 才淡入"那条斜坡，
       前面 75% 由眼眶压扁表现，和闭眼件口径一致。 */
    if (smile > 0.001) {
        if (p->tags & TAG_EYE_CLOSED) opacity *= 1.0 - smile;
        if (p->tags & TAG_EYE_SMILE)
            opacity *= ZC_CLAMP((smile - 0.75) * 4.0, 0.0, 1.0);
    }
    /* 痛苦闭眼（倒 V）：和笑眼同一条睫毛线的第三种形状，口径完全一致 ——
       它涨多少，谷型闭眼件和山型笑眼件就让多少，三张不能同时画。 */
    if (pain > 0.001) {
        if (p->tags & (TAG_EYE_CLOSED | TAG_EYE_SMILE)) opacity *= 1.0 - pain;
        if (p->tags & TAG_EYE_PAIN)
            opacity *= ZC_CLAMP((pain - 0.75) * 4.0, 0.0, 1.0);
    }
    /* 瞪大眼：补片**顶替**常态的眼白和上睫毛（它们画的是常态开口，留着会在补片下面
       透出一条旧眼线）。这里不用笑眼那种"最后 25% 才淡入"的斜坡：
       瞪大是连续量（惊讶的强弱），要能停在半路，所以线性交叉淡化。
       虹膜（tags:["gaze"]）不在顶替之列 —— 补片里的虹膜已经被挖掉了，
       视线照常由 eye_*_ball 负责（见 make_eye_closed_parts.py 的 erase_iris）。 */
    if (wide > 0.001) {
        if (p->tags & TAG_EYE_NOT_WIDE) opacity *= 1.0 - wide;
        if (p->tags & TAG_EYE_WIDE) opacity *= wide;
    } else if (p->tags & TAG_EYE_WIDE) {
        return 0;
    }
    /* 参数驱动的交叉淡化（踮脚鞋）：淡入件按权重，淡出件按官方 Pose 的曲线。
       放在这里（动作覆盖之后、early-out 之前）是为了和眨眼那套走同一个口径。 */
    if (r->nxfades > 0) {
        int xi;
        for (xi = 0; xi < r->nxfades; ++xi) {
            const zxfade *xf = &r->xfades[xi];
            if (xf->to == pi) opacity *= xf->w;
            else if (xf->from == pi) opacity *= zrig_xfade_hidden(xf->w);
        }
    }
    if (opacity <= 0.001) return 0;
    if ((p->tags & TAG_EYE_CLOSED) && blink <= 0.001) return 0;
    if ((p->tags & TAG_EYE_OPEN) && blink >= 0.999) return 0;
    if ((p->tags & TAG_EYE_SMILE) && smile <= 0.001) return 0;
    if ((p->tags & TAG_EYE_PAIN) && pain <= 0.001) return 0;

    /* 部件矩阵（画布缩放 + 锚点 + 自身旋转） */
    {
        double anchor_px = src->w * p->anchor[0];
        double anchor_py = src->h * p->anchor[1];
        double pos_x = (p->pos[0] + extra_dx) * scale;
        double pos_y = (p->pos[1] + extra_dy) * scale;
        zimg_make_matrix(lm, pos_x, pos_y, p->scale * part_sx, p->scale * part_sy,
                         p->rot_deg + part_rot, anchor_px, anchor_py);
    }
    {
        double base[6];
        if (p->group >= 0) {
            group_matrix(r, p->group, scale, gm);
            zimg_matrix_mul(base, gm, lm);
        } else {
            memcpy(base, lm, sizeof(lm));
        }
        /* 变形器链在**最外层**：A_chain 的 pivot 是画布坐标，所以它绕的是画布上的
           关节（肩、肘、腕），不是素材里的锚点。128~136 行那段注释讲的就是这条链。 */
        if (r->ndeforms > 0) {
            double am[6];
            deform_chain_matrix(r, pi, scale, am);
            zimg_matrix_mul(st->m, am, base);
        } else {
            memcpy(st->m, base, sizeof(base));
        }
    }
    st->src = src;
    st->opacity = opacity;
    st->bx = r->p_bendx[mi] * scale;
    st->by = r->p_bendy[mi] * scale;
    st->curve_x = r->p_bendcx[mi];
    st->curve_y = r->p_bendcy[mi];
    st->warped = (fabs(st->bx) > 0.05 || fabs(st->by) > 0.05);
    /* 形变平台换算成源图归一化行：(平台画布y − 部件顶边) / 部件画布高度 */
    st->bend_tmin = 0.0;
    st->bend_tmax = 1.0;
    if (src && src->h > 0 && p->scale > 0.0 && p->img && p->img->h > 0) {
        double h_canvas   = (double)p->img->h * p->scale;
        double top_canvas = p->pos[1] - p->anchor[1] * h_canvas;
        if (p->bend_hold_above > 0.0) {
            double tm = (p->bend_hold_above - top_canvas) / h_canvas;
            st->bend_tmin = tm < 0.0 ? 0.0 : (tm > 1.0 ? 1.0 : tm);
        }
        if (p->bend_hold_below > 0.0) {
            double tx = (p->bend_hold_below - top_canvas) / h_canvas;
            st->bend_tmax = tx < 0.0 ? 0.0 : (tx > 1.0 ? 1.0 : tx);
            /* 两条平台线交叉了说明 rig 写反了：宁可退化成"整块按住"，也不要出现
               tmin > tmax 这种"下界比上界还大"的状态（那会让钳位顺序决定画面）。 */
            if (st->bend_tmax < st->bend_tmin) st->bend_tmax = st->bend_tmin;
        }
    }

    /* 网格形变（A5）：形变器的位移写的是"原始素材像素"，而这里画的可能是缩放过的
       缓存图，所以要按 src->w / img->w 折算，换画布缩放时形变量才不会跟着变。 */
    {
        /* 一个部件可以挂多张网格（裙摆就是横摆 + 纵摆两张）：全部累加，
           不能找到第一张就 break——那样第二张起全部静默失效。
           网格尺寸必须一致才能逐点相加，load_deformers 里已经把这条拦住了。 */
        int di;
        double k = (p->img && p->img->w > 0) ? (double)src->w / (double)p->img->w : 1.0;
        for (di = 0; di < r->ndeforms; ++di) {
            const zdeform *cand = &r->deforms[di];
            int np, q, has_kf;
            if (cand->part != mi && cand->part != pi) continue;
            has_kf = (cand->nkf > 0 && cand->kf_d != NULL);
            /* keyform 网格不看 amount（它由参数插值驱动），所以别拿 amount 的
               早退把它挡掉 —— 那会让"参数驱动"静默失效，只剩动作通道还活着。 */
            if (!has_kf && fabs(cand->amount) < 1e-6) continue;
            if (!st->dg) {
                st->dg = cand;
                np = (cand->cols + 1) * (cand->rows + 1);
                for (q = 0; q < np * 2; ++q) st->mesh[q] = 0.0;
            } else if (cand->cols != st->dg->cols || cand->rows != st->dg->rows) {
                continue;                       /* 理论上不会发生（加载时已校验） */
            }
            np = (cand->cols + 1) * (cand->rows + 1);
            for (q = 0; q < np; ++q) {
                double dx, dy;
                /* 位移怎么算统一在 deform_vertex_at 里（amount 通路 / keyform 通路），
                   这里只负责按画布缩放折算并累加。kf_w 由 deform_update_keys
                   每帧算一次，读的是合成后的参数值。 */
                deform_vertex_at(cand, q, &dx, &dy);
                st->mesh[q * 2]     += dx * k;
                st->mesh[q * 2 + 1] += dy * k;
            }
        }
    }
    /* 父级 warp 的逐顶点位移场（T66.10 / G58.8）：本部件自己那几张网格算完之后
       再叠祖先件的场。顺序不能反 —— 上面的循环会把 mesh[] 清零并定下网格尺寸。 */
    deform_inherit_parent_warp(r, pi, mi, scale, st);
    return 1;
}

/* 一个部件这一帧**实际会画出去的网格位移**（源像素，和渲染同一份求值）。
   和 zrig_deform_mesh 的区别：那个读的是某个形变器**自己**的控制点位移，
   读不到"父级 warp 传下来的场"（T66.10）。测试台/单测要看"画出来是什么样"，
   必须走这条 —— 否则继承写没写对，探针根本看不见。 */
int zrig_part_mesh(const zrig *r, const char *part_id, double scale,
                   int *cols, int *rows, double *dx, double *dy, int cap)
{
    int pi, np, q;
    zdrawst st;
    if (!r || !part_id) return 0;
    pi = find_part(r, part_id);
    if (pi < 0) return 0;
    /* compute_draw_state 只读 r（不写），const 在这里是给调用方的承诺，
       内部签名是历史原因保留了非 const。 */
    if (!compute_draw_state((zrig *)r, pi, scale, 1.0, NULL, &st)) return 0;
    if (!st.dg) return 0;
    np = (st.dg->cols + 1) * (st.dg->rows + 1);
    if (cols) *cols = st.dg->cols;
    if (rows) *rows = st.dg->rows;
    for (q = 0; q < np && q < cap; ++q) {
        if (dx) dx[q] = st.mesh[q * 2];
        if (dy) dy[q] = st.mesh[q * 2 + 1];
    }
    return np;
}

/* 按算好的状态画一笔 */
static void draw_state(zimg *dst, const zdrawst *st, int blend)
{
    if (st->dg)
        /* 网格 + 平滑形变一起画：以前这里丢掉 bend，多段摆链的第一段就白写了 */
        zimg_draw_mesh_bend_blend_t(dst, st->src, st->m, st->opacity,
                                    st->dg->cols, st->dg->rows, st->mesh,
                                    st->warped ? st->bx : 0.0, st->curve_x,
                                    st->warped ? st->by : 0.0, st->curve_y,
                                    blend, st->bend_tmin, st->bend_tmax);
    else if (st->warped)
        zimg_draw_warp_blend_t(dst, st->src, st->m, st->opacity,
                               st->bx, st->curve_x, st->by, st->curve_y,
                               blend, st->bend_tmin, st->bend_tmax);
    else
        zimg_draw_blend(dst, st->src, st->m, st->opacity, blend);
}

/* 把 p 的遮罩源画进 maskbuf（多个遮罩取并集；mask_invert 时再取反）。
   返回 0 = 遮罩完全不可见（例如眨眼时眼眶被藏起来）→ 被裁的部件这一帧也不画，
   与 Live2D 的 clipping 语义一致。取反遮罩则相反：遮罩消失＝整块可见。 */
static int build_maskbuf(zrig *r, zimg *maskbuf, const zpart *p, double scale,
                         double blink, const zaction *a)
{
    int k, any = 0;
    if (!maskbuf) return 0;
    zimg_clear(maskbuf);
    for (k = 0; k < p->nmask; ++k) {
        zdrawst ms;
        if (!compute_draw_state(r, p->mask[k], scale, blink, a, &ms)) continue;
        ms.opacity = 1.0;              /* 遮罩只用形状，不用它自己的透明度 */
        draw_state(maskbuf, &ms, ZIMG_BLEND_NORMAL);
        any = 1;
    }
    if (p->mask_invert) {
        /* 取反也只许碰分给本线程的那几行 */
        int iy0 = (maskbuf->clip_y1 > maskbuf->clip_y0) ? maskbuf->clip_y0 : 0;
        int iy1 = (maskbuf->clip_y1 > maskbuf->clip_y0) ? maskbuf->clip_y1 : maskbuf->h;
        size_t n = (size_t)(iy1 - iy0) * maskbuf->w, q;
        uint8_t *base = maskbuf->px + (size_t)iy0 * maskbuf->w * 4;
        for (q = 0; q < n; ++q) {
            uint8_t *px = base + q * 4;
            px[3] = (uint8_t)(255 - px[3]);
            px[0] = px[1] = px[2] = 255;
        }
        return 1;                      /* 取反后遮罩不可能是"全透明" */
    }
    return any;
}

static void free_band_bufs(zrig *r)
{
    int bi;
    for (bi = 0; bi < ZRIG_MAX_BANDS; ++bi) {
        zimg_free(r->band_scratch[bi]); r->band_scratch[bi] = NULL;
        zimg_free(r->band_maskbuf[bi]); r->band_maskbuf[bi] = NULL;
    }
}

/* ---------------------------------------------- 分块渲染（T30.2）
   合成本身是"按层序把 44 个部件逐像素混到 fb 上"，不同 y 的像素互不影响，
   所以按**行带**切开、每个线程在自己的带里跑一遍完整的层序，结果和单线程
   **逐字节相同**（test_core 有这条闸）。坐标系不切——每个线程拿的是 fb 的
   浅拷贝头 + 一段 clip_y，画布坐标保持全局，省掉所有矩阵平移的麻烦。
   maskbuf / scratch 必须每线程一份：它们会被 zimg_clear 整段清掉，共享就是竞争。 */
typedef struct {
    zrig          *r;
    zimg           fb;        /* fb 的带视图（共享像素） */
    zimg          *scratch;   /* 本线程私有 */
    zimg          *maskbuf;   /* 本线程私有 */
    double         scale, blink;
    const zaction *a;
} zband;

static void render_band(zband *b)
{
    zrig *r = b->r;
    int i;
    for (i = 0; i < r->nparts; ++i) {
        int pi = r->order[i];
        zpart *p = &r->parts[pi];
        zdrawst st;
        zimg *target = &b->fb;
        if (!compute_draw_state(r, pi, b->scale, b->blink, b->a, &st)) continue;
        if (p->mask_only) continue;      /* 只当遮罩用的部件不出现在画面上 */

        /* 被裁切：先按需把遮罩画进 maskbuf（可以是多个部件的并集 + 可取反），
           再把自己画进 scratch，最后按遮罩 alpha 合成到画面。
           遮罩是**当场渲染**的，所以不要求遮罩和被裁件在图层里挨着。 */
        if (p->nmask > 0) {
            if (!build_maskbuf(r, b->maskbuf, p, b->scale, b->blink, b->a)) continue;
            if (!b->scratch) continue;
            zimg_clear(b->scratch);
            target = b->scratch;
        }
        /* 被遮罩的部件先画进 scratch（那里是空的，必须用普通混合），
           混合模式留到 composite_masked 那一步再按真正的目标画面算。 */
        draw_state(target, &st, (target == &b->fb) ? p->blend : ZIMG_BLEND_NORMAL);
        if (target != &b->fb)
            zimg_composite_masked_blend(&b->fb, b->scratch, b->maskbuf, p->blend);
    }
}

#if ZRIG_THREADS
#  ifdef _WIN32
static unsigned __stdcall band_thread(void *arg) { render_band((zband *)arg); return 0; }
#  else
static void *band_thread(void *arg) { render_band((zband *)arg); return NULL; }
#  endif
#endif

/* 渲染线程数：默认跟 CPU 核数走（上限 ZRIG_MAX_BANDS），
   环境变量 ZC_RENDER_THREADS 可以覆盖——**对拍单线程/多线程就靠它**。 */
static int g_render_threads = -1;   /* <0 = 还没定；由 zrig_render_threads() 首次调用时算出 */

void zrig_set_render_threads(int n)
{
    if (n < 1) n = 1;
    if (n > ZRIG_MAX_BANDS) n = ZRIG_MAX_BANDS;
    g_render_threads = n;
}

int zrig_render_threads(void)
{
    int cached = g_render_threads;
    if (cached > 0) return cached;
    {
        const char *e = getenv("ZC_RENDER_THREADS");
        int n = 0;
        if (e && *e) n = atoi(e);
        if (n <= 0) {
#if ZRIG_THREADS
#  ifdef _WIN32
            SYSTEM_INFO si;
            GetSystemInfo(&si);
            n = (int)si.dwNumberOfProcessors;
#  else
            long sc = sysconf(_SC_NPROCESSORS_ONLN);
            n = (sc > 0) ? (int)sc : 1;
#  endif
#else
            n = 1;
#endif
        }
        if (n < 1) n = 1;
        if (n > ZRIG_MAX_BANDS) n = ZRIG_MAX_BANDS;
        g_render_threads = n;
    }
    return g_render_threads;
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
        free_band_bufs(r);
        r->fb_scale = scale;
        r->fb_w = fw;
        r->fb_h = fh;
    } else if (!r->fb || r->fb->w != fw || r->fb->h != fh) {
        zimg_free(r->fb);
        r->fb = zimg_new(fw, fh);
        zimg_free(r->maskbuf); r->maskbuf = NULL;
        zimg_free(r->scratch); r->scratch = NULL;
        free_band_bufs(r);
        r->fb_w = fw;
        r->fb_h = fh;
    }
    if (!r->fb) return NULL;
    zimg_clear(r->fb);

    a = current_action(r);
    {
        double blink = r->blink_now;      /* 表情叠加后的最终闭合度 */
        int nb = zrig_render_threads();
        if (nb > fh) nb = fh;             /* 带比行还多没意义 */
        if (nb < 1) nb = 1;
        /* 每条带的 scratch/maskbuf 是惰性分配的，必须在**起线程之前**备好，
           不然两个线程会同时去 malloc 同一个槽位。 */
        for (i = 0; i < nb; ++i) {
            if (!r->band_scratch[i]) r->band_scratch[i] = zimg_new(fw, fh);
            if (!r->band_maskbuf[i]) r->band_maskbuf[i] = zimg_new(fw, fh);
        }
        if (nb == 1) {
            zband b;
            b.r = r; b.fb = zimg_band(r->fb, 0, fh);
            b.scratch = r->band_scratch[0]; b.maskbuf = r->band_maskbuf[0];
            /* 必须显式写回"整幅"：上一帧可能是多线程跑的，band_scratch[0] 还留着
               [0, fh/nb) 的旧 clip，不重置的话这一帧 y 靠下的带遮罩部件会整个消失。 */
            b.scratch->clip_y0 = 0; b.scratch->clip_y1 = fh;
            b.maskbuf->clip_y0 = 0; b.maskbuf->clip_y1 = fh;
            b.scale = scale; b.blink = blink; b.a = a;
            render_band(&b);
        } else {
            zband bands[ZRIG_MAX_BANDS];
            int k;
            for (k = 0; k < nb; ++k) {
                int y0 = (int)((long)fh * k / nb);
                int y1 = (int)((long)fh * (k + 1) / nb);
                bands[k].r = r;
                bands[k].fb = zimg_band(r->fb, y0, y1);
                bands[k].scratch = r->band_scratch[k];
                bands[k].maskbuf = r->band_maskbuf[k];
                /* 带视图要和 fb 同尺寸同坐标系，只是 clip 不同 */
                bands[k].scratch->clip_y0 = y0; bands[k].scratch->clip_y1 = y1;
                bands[k].maskbuf->clip_y0 = y0; bands[k].maskbuf->clip_y1 = y1;
                bands[k].scale = scale; bands[k].blink = blink; bands[k].a = a;
            }
#if ZRIG_THREADS
            {
#  ifdef _WIN32
                HANDLE th[ZRIG_MAX_BANDS];
                for (k = 1; k < nb; ++k)
                    th[k] = (HANDLE)_beginthreadex(NULL, 0, band_thread, &bands[k], 0, NULL);
                render_band(&bands[0]);        /* 主线程也干一份活 */
                for (k = 1; k < nb; ++k)
                    if (th[k]) { WaitForSingleObject(th[k], INFINITE); CloseHandle(th[k]); }
#  else
                pthread_t th[ZRIG_MAX_BANDS];
                int started[ZRIG_MAX_BANDS];
                for (k = 1; k < nb; ++k)
                    started[k] = (pthread_create(&th[k], NULL, band_thread, &bands[k]) == 0);
                render_band(&bands[0]);        /* 主线程也干一份活 */
                for (k = 1; k < nb; ++k)
                    if (started[k]) pthread_join(th[k], NULL);
#  endif
            }
#else
            for (k = 0; k < nb; ++k) render_band(&bands[k]);
#endif
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

/* 现在用的显示缩放：渲染过就按帧缓冲的真实比例算，没渲染过用平台层声明的那个值。
 *
 * 2026-10-15 实测到的坑：这里原本在 `r->fb == NULL` 时退化成 1:1，于是
 * `/api/region` 在**首帧之前收画布坐标、首帧之后收帧坐标** —— 同一个请求，
 * 渲染过没渲染过给两种答案，而且两种都"看起来正常"。
 * 坐标系不能跟着渲染历史变，所以这里永远有一个确定的比例。 */
double zrig_view_scale(const zrig *r)
{
    if (!r) return 1.0;
    if (r->fb && r->fb->w > 0 && r->cw > 0) return (double)r->fb->w / (double)r->cw;
    return (r->view_scale > 0.0) ? r->view_scale : 1.0;
}

void zrig_set_view_scale(zrig *r, double s)
{
    if (!r || !(s > 0.0)) return;
    r->view_scale = s;
}

/* 把帧缓冲坐标换算为画布坐标（平台层用） */
void zrig_frame_to_canvas(const zrig *r, int fx, int fy, int *cx, int *cy)
{
    double s;
    if (!r) return;
    s = zrig_view_scale(r);
    if (s <= 0.0) s = 1.0;
    if (cx) *cx = (int)((double)fx / s + 0.5);
    if (cy) *cy = (int)((double)fy / s + 0.5);
}

/* 画布坐标 → 帧缓冲坐标（上面那个的反向，给要在画面上标出区域的调用方） */
void zrig_canvas_to_frame(const zrig *r, int cx, int cy, int *fx, int *fy)
{
    double s;
    if (!r) return;
    s = zrig_view_scale(r);
    if (s <= 0.0) s = 1.0;
    if (fx) *fx = (int)((double)cx * s + 0.5);
    if (fy) *fy = (int)((double)cy * s + 0.5);
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
double zrig_part_draw_opacity(const zrig *r, const char *part_id)
{
    int pi;
    zdrawst st;
    if (!r || !part_id) return 0.0;
    pi = find_part(r, part_id);
    if (pi < 0) return 0.0;
    if (!compute_draw_state((zrig *)r, pi, 1.0, r->blink_now,
                            current_action((zrig *)r), &st)) return 0.0;
    return st.opacity;
}

/* 这一帧部件的锚点落在帧缓冲的哪个坐标（画布坐标 × 窗口缩放）。
   ★ 它算的是**真正用来画的那个矩阵**（含组、部件自身旋转、变形器树）。
   为什么测试需要它：只看"画面变了"分不清"节点绕 pivot 转了 90°"还是"部件自己平移了一下"；
   有了它就能直接断言几何：绕 (px,py) 转 90° 后 (x,y) → (px−(y−py), py+(x−px))。
   查不到返回 0（pos 不动）。 */
int zrig_part_anchor_pos(const zrig *r, const char *part_id, double scale, double out[2])
{
    int pi;
    zdrawst st;
    const zimg *src;
    double ax, ay;
    if (!r || !part_id || scale <= 0.0) return 0;
    pi = find_part(r, part_id);
    if (pi < 0) return 0;
    if (!compute_draw_state((zrig *)r, pi, scale, r->blink_now,
                            current_action((zrig *)r), &st)) return 0;
    src = st.src;
    if (!src) return 0;
    ax = src->w * r->parts[pi].anchor[0];
    ay = src->h * r->parts[pi].anchor[1];
    /* ⚠ 本项目的 6 元素矩阵是 [a,b,c,d,e,f]：x' = a·x + c·y + e，y' = b·x + d·y + f。
       第一版按数学课本的 [a b c; d e f] 写，把 y 当成了平移，量出来的 x 恒为 0。 */
    out[0] = st.m[0] * ax + st.m[2] * ay + st.m[4];
    out[1] = st.m[1] * ax + st.m[3] * ay + st.m[5];
    return 1;
}

double zrig_gaze_eff_x(const zrig *r) { return r ? r->gaze_nx : 0.0; }
double zrig_gaze_x(const zrig *r) { return r ? r->gaze_x : 0.0; }
double zrig_gaze_max_dx(const zrig *r) { return r ? r->gaze_max_dx : 0.0; }
double zrig_gaze_eff_y(const zrig *r) { return r ? r->gaze_ny : 0.0; }
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
int zrig_xfade_count(const zrig *r) { return r ? r->nxfades : 0; }

const char *zrig_xfade_id(const zrig *r, int i)
{
    if (!r || i < 0 || i >= r->nxfades) return "";
    return r->xfades[i].id;
}

double zrig_xfade_weight(const zrig *r, const char *id)
{
    int i;
    if (!r || !id) return -1.0;
    for (i = 0; i < r->nxfades; ++i)
        if (z_streq(r->xfades[i].id, id)) return r->xfades[i].w;
    return -1.0;
}

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
void zrig_apply_mood_params(zrig *r, const char *mood)
{
    int i, k;
    if (!r || !mood || !*mood) return;
    for (i = 0; i < r->nmood_param; ++i) {
        for (k = 0; k < r->mood_param[i].n; ++k) {
            if (!z_streq(r->mood_param[i].e[k].mood, mood)) continue;
            r->params[r->mood_param[i].param].value = r->mood_param[i].e[k].v;
            break;
        }
        /* 查不到就不动：没写 = 这个情绪跟这条参数无关 */
    }
}

void zrig_apply_mood_swing(zrig *r, const char *mood)
{
    int i, k;
    double now;
    if (!r || !mood || !*mood || r->nswing_param <= 0) return;
    for (k = 0; k < r->nmood_swing; ++k)
        if (z_streq(r->mood_swing[k].mood, mood)) break;
    if (k >= r->nmood_swing) return;   /* 查不到就不动（和另外三张情绪表同口径） */
    /* ★ 基准必须是**绝对时刻** —— 摆动通道搬去 ambient 之后就是按 r->now 求值的
       （T45.9）。这里要是还拿动作内经过时间算相位补偿，换一次动作补偿量就错一次。 */
    now = r->now;
    for (i = 0; i < r->nswing_param; ++i) {
        int pi = r->swing_param[i];
        double m0 = r->sw_fmul[pi], m1 = r->mood_swing[k].fmul;
        if (pi < 0 || pi >= r->nparams || m1 <= 0.0) continue;
        /* 相位连续：切换瞬间 f1·(t−shift1) 必须等于 f0·(t−shift0)。
           f = 基频×倍率，基频约掉 ⇒ 只跟倍率比有关。 */
        r->sw_tshift[pi] = now - (m0 / m1) * (now - r->sw_tshift[pi]);
        r->sw_fmul[pi] = m1;
        r->sw_amul[pi] = r->mood_swing[k].amul;
    }
}

void zrig_apply_mood_flick(zrig *r, const char *mood)
{
    int k;
    if (!r || !mood || !*mood || r->nflick_param <= 0) return;
    for (k = 0; k < r->nmood_flick; ++k)
        if (z_streq(r->mood_flick[k].mood, mood)) break;
    if (k >= r->nmood_flick) return;   /* 查不到就不动（和另外四张情绪表同口径） */
    r->flick_gmin = r->mood_flick[k].gmin;
    r->flick_gmax = r->mood_flick[k].gmax;
    r->flick_amp  = r->mood_flick[k].amp;
    r->flick_dur  = r->mood_flick[k].dur;
    /* ★ 不动 flick_st[].t0：正在进行中的那一下让它演完。
       情绪一变就把抽动掐断 = 尾巴瞬间弹回原位，比不抽还假。
       只改"下一次排在什么时候"：把已排的班重排到新档位里。 */
    for (k = 0; k < r->nflick_param; ++k)
        r->flick_st[k].next_t =
            r->now + zrand_range(&r->flick_rng, r->flick_gmin, r->flick_gmax);
}

void zrig_tail_flick_enable(zrig *r, int on)
{
    if (r) r->flick_off = on ? 0 : 1;
}

void zrig_ambient_enable(zrig *r, int on)
{
    if (r) r->ambient_off = on ? 0 : 1;
}

int zrig_ambient_enabled(const zrig *r)
{
    return (r && !r->ambient_off) ? 1 : 0;
}

void zrig_pose_apply_mood(zrig *r, const char *mood)
{
    int gi, m;
    if (!r || !mood || !*mood) return;
    for (gi = 0; gi < r->nposes; ++gi) {
        zpose *g = &r->poses[gi];
        for (m = 0; m < g->nmood; ++m) {
            if (!z_streq(g->mood_map[m].mood, mood)) continue;
            g->cur = g->mood_map[m].ent;   /* 淡化由 pose 自己的 fade 负责 */
            break;
        }
        /* 查不到就不动：没写 = 这个情绪跟这个部位无关，不是"要复位" */
    }
}

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
