/*
 * zphys2.h - 物理内核 2.0：官方那种 2D 粒子摆链（T47.1）
 *
 * 为什么要换内核（用户 2026-10-17：「目前还没有真实的物理效果」）：
 *   旧内核 `zphys` 是 1D 弹簧，**输出的是滞后量 `pos − target`** ——
 *   输入不动，输出必然是 0，于是人一静止，头发尾巴就彻底死了；
 *   现在看到的"自主摇晃"全是 motion 动作通道在演，所以看久了像在循环播放。
 *   官方（CubismPhysics）是 **2D 粒子链 + 输出摆角**：重力常在，
 *   摆有一个被重力拉住的平衡位置，任何扰动都会绕着它衰减振荡 —— 这才是"真实"的来源。
 *
 * 算法出处：Live2D Cubism Native Framework `src/Physics/CubismPhysics.cpp`
 *   的 `UpdateParticles()` / `GetOutputAngle()`，以及 `.physics3.json` 的
 *   `Vertices[] { Radius, Mobility, Delay, Acceleration }`。
 *   **四个旋钮的名字照抄官方**（DC70）：社区教程里的数值可以直接往里填，
 *   将来 T47.5 做 `physics3.json` 双向互通时也不用再翻译一次。
 *     長さ       Radius        摆长（小→快，大→慢）
 *     揺れやすさ  Mobility      0.7~0.99，越大越容易晃
 *     反応速度   Delay         1.0 为标准
 *     収束の速さ  Acceleration  1.0 为标准（它乘在重力上，所以也是"多重"）
 *
 * 和官方的**一处有意偏离**（见 DC77）：官方 `UpdateParticles` 里那段旋转
 *   `direction.Y = sin*direction.X + direction.Y*cos;` 用的是**已经被覆盖过的**
 *   `direction.X`，是实打实的变量覆盖 bug。平时重力方向不变（radian≈0）看不出来，
 *   但我们马上要做风（T47.3）和拖动惯性（T47.4），重力方向会一直转 ——
 *   所以这里实现成正确的旋转，并在 `tools/physics_ref.py` 里用同样的写法对拍。
 *
 * 这一层**只算摆**，不碰部件、不碰 rig：摆角怎么翻译成切件的 rot / 形变器 amount
 * 是 T47.2 的事。好处是它能被单测直接驱动，也能被 Python 参考实现逐步对拍。
 */
#ifndef ZPHYS2_H
#define ZPHYS2_H

#define ZPHYS2_MAX_PARTICLES 8      /* 一条链最多几个粒子（含根）。官方模型常见 2~5 */

/* 固定步长：和旧内核同一套口径（G113 / DC53）。
   ⚠ 不要改成"整帧 dt 单步积分"：低帧率下显式欧拉过冲，看着就是抽搐。 */
#define ZPHYS2_FPS           60.0
#define ZPHYS2_STEP          (1.0 / ZPHYS2_FPS)
#define ZPHYS2_MAX_REMAIN    5.0

/* 官方 `CubismPhysics::Options` 的两个默认值，名字照抄 */
#define ZPHYS2_AIR_RESISTANCE 5.0    /* 重力方向变化被它除，越大转得越温吞 */
#define ZPHYS2_THRESHOLD      0.001  /* 官方的 MovementThreshold：|x| 小于它就吸附到 0 */
/* ⚠ 官方传进去的是 MovementThreshold × NormalizationPosition.Maximum（模型单位），
   我们这边位置直接用**像素**，所以 T47.5 导入 physics3.json 时要按归一化最大值换算一次。 */

typedef struct {
    double x, y;                /* 当前位置 */
    double last_x, last_y;      /* 上一步位置（官方 LastPosition） */
    double vx, vy;              /* 速度 */
    double last_gx, last_gy;    /* 上一步的重力方向（官方 LastGravity） */
    double radius;              /* Radius：到父粒子的固定距离 */
    double mobility;            /* Mobility 0.7~0.99 */
    double delay;               /* Delay */
    double acceleration;        /* Acceleration */
} zphys2_particle;

typedef struct {
    int    n;                   /* 粒子数（含根粒子 [0]） */
    zphys2_particle p[ZPHYS2_MAX_PARTICLES];

    /* 固定步长积分的状态：和旧内核一样，渲染时刻落在两个固定步之间要插值，
       否则 60fps 的物理配上 144fps 的渲染会出现规律性的台阶。 */
    double remain;
    double out_prev[ZPHYS2_MAX_PARTICLES];  /* 上一个固定步的摆角（度） */
    double out_cur[ZPHYS2_MAX_PARTICLES];   /* 这一个固定步的摆角（度） */
    double out[ZPHYS2_MAX_PARTICLES];       /* 插值到渲染时刻的摆角（度）← 外面要读的就是它 */

    /* 输入插值（官方 _parameterCaches 那一手）：一帧里的 N 个子步不能共用帧末输入 */
    double in_tx, in_ty, in_angle;
    int    in_init;
} zphys2;

/* 建链：n 个粒子，全部先给一组默认参数（radius 由调用方逐个设）。
   root（下标 0）是"被带着走"的那个点，它不参与积分。 */
void   zphys2_init(zphys2 *c, int n);

/* 设一个粒子的四个官方旋钮。i 从 1 开始（0 是根，没有摆长）。 */
void   zphys2_set(zphys2 *c, int i, double radius, double mobility,
                  double delay, double acceleration);

/* 按重力方向把链摆直、速度清零。换形态 / 关物理 / 传送时用。 */
void   zphys2_reset(zphys2 *c, double gx, double gy);

/* 走**一个固定步**（内部用，单测与参考实现对拍时直接调它）。
   tx/ty      根粒子这一步的位置（官方 totalTranslation）
   angle_deg  整条链的额外倾角（官方 totalAngle，度）
   gx/gy      重力方向（不必归一化，官方默认 (0,−1)）
   wx/wy      风（官方 Meta.EffectiveForces.Wind） */
void   zphys2_step(zphys2 *c, double tx, double ty, double angle_deg,
                   double gx, double gy, double wx, double wy, double dt);

/* 走**一帧**：累积 dt → 若干个固定步（含输入线性插值）→ 把摆角插值进 out[]。 */
void   zphys2_advance(zphys2 *c, double tx, double ty, double angle_deg,
                      double gx, double gy, double wx, double wy, double dt);

/* 第 i 个粒子相对重力方向的摆角（度）。官方 GetOutputAngle 的等价物。
   inverted = 1 时把参考方向取反（官方 Output[].Reflect）。 */
double zphys2_angle(const zphys2 *c, int i, double gx, double gy, int inverted);

/* 插值后的摆角（度），渲染/绑定要读的就是这个 */
double zphys2_out(const zphys2 *c, int i);

#endif /* ZPHYS2_H */
