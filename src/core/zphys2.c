/* zphys2.c - 2D 粒子摆链（T47.1）。算法注释见 zphys2.h。 */
#include "zphys2.h"

#include <math.h>
#include <string.h>

#define ZP2_PI 3.14159265358979323846

/* 官方 CubismMath::DirectionToRadian：从 from 方向转到 to 方向要转多少弧度，
   结果规整到 (−π, π]。摆角就是这么来的 —— **不是"落后了几个像素"**。 */
static double dir_to_radian(double fx, double fy, double tx, double ty)
{
    double q1 = atan2(ty, tx);
    double q2 = atan2(fy, fx);
    double ret = q1 - q2;
    while (ret < -ZP2_PI) ret += ZP2_PI * 2.0;
    while (ret >  ZP2_PI) ret -= ZP2_PI * 2.0;
    return ret;
}

static void normalize2(double *x, double *y)
{
    double len = sqrt((*x) * (*x) + (*y) * (*y));
    if (len > 1e-12) { *x /= len; *y /= len; }
    else { *x = 0.0; *y = -1.0; }   /* 退化时按重力默认方向，不要留 NaN */
}

void zphys2_init(zphys2 *c, int n)
{
    int i;
    if (!c) return;
    memset(c, 0, sizeof(*c));
    if (n < 2) n = 2;
    if (n > ZPHYS2_MAX_PARTICLES) n = ZPHYS2_MAX_PARTICLES;
    c->n = n;
    for (i = 0; i < n; ++i) {
        c->p[i].radius       = (i == 0) ? 0.0 : 10.0;
        c->p[i].mobility     = 0.95;
        c->p[i].delay        = 1.0;
        c->p[i].acceleration = 1.0;
        c->p[i].last_gx      = 0.0;
        c->p[i].last_gy      = -1.0;
    }
}

void zphys2_set(zphys2 *c, int i, double radius, double mobility,
                double delay, double acceleration)
{
    if (!c || i < 1 || i >= c->n) return;
    c->p[i].radius       = radius;
    c->p[i].mobility     = mobility;
    c->p[i].delay        = delay;
    c->p[i].acceleration = acceleration;
}

void zphys2_reset(zphys2 *c, double gx, double gy)
{
    int i;
    if (!c) return;
    normalize2(&gx, &gy);
    c->p[0].x = c->p[0].y = 0.0;
    for (i = 0; i < c->n; ++i) {
        if (i > 0) {
            c->p[i].x = c->p[i - 1].x + gx * c->p[i].radius;
            c->p[i].y = c->p[i - 1].y + gy * c->p[i].radius;
        }
        c->p[i].last_x = c->p[i].x;
        c->p[i].last_y = c->p[i].y;
        c->p[i].vx = c->p[i].vy = 0.0;
        c->p[i].last_gx = gx;
        c->p[i].last_gy = gy;
        c->out_prev[i] = c->out_cur[i] = c->out[i] = 0.0;
    }
    c->remain = 0.0;
    c->in_init = 0;
    c->in_tx = c->in_ty = c->in_angle = 0.0;
}

void zphys2_step(zphys2 *c, double tx, double ty, double angle_deg,
                 double gx, double gy, double wx, double wy, double dt)
{
    int i;
    double cur_gx, cur_gy, a, ca, sa;
    if (!c || c->n < 2 || dt <= 0.0) return;

    /* 当前重力 = 重力向量绕原点转 angle_deg。
       官方是把 totalAngle 直接变成方向向量当"当前重力"（所以 Angle 输入会让
       整条摆的平衡位置跟着转）——歪头时头发保持歪，就是这一项干的。
       我们把重力显式地当参数传进来，是为了后面的风（T47.3）与拖动惯性（T47.4）
       能直接改这个向量。★ 约定：我们的像素空间 **Y 轴向下**，所以"向下"是 (0, +1)。 */
    normalize2(&gx, &gy);
    /* ★ 旋向照官方：官方 currentGravity = RadianToDirection(totalAngle) = (sin a, cos a)，
       等价于把"向下"向量 (0,1) **顺时针**转 a。所以这里用 −a 的旋转矩阵，
       将来 T47.5 导入 physics3.json 时 Angle 输入的符号才不用翻。 */
    a  = -angle_deg * ZP2_PI / 180.0;
    ca = cos(a); sa = sin(a);
    cur_gx = gx * ca - gy * sa;
    cur_gy = gx * sa + gy * ca;
    normalize2(&cur_gx, &cur_gy);

    /* 根粒子被输入直接拖着走，不积分 —— 官方 strand[0].Position = totalTranslation */
    c->p[0].x = tx;
    c->p[0].y = ty;

    for (i = 1; i < c->n; ++i) {
        zphys2_particle *q = &c->p[i];
        double fx, fy, delay, dx, dy, r, cs, sn, nx, ny;

        /* 力 = 重力 × Acceleration + 风。重力常在 ⇒ 输入不动也有平衡位置可绕。 */
        fx = cur_gx * q->acceleration + wx;
        fy = cur_gy * q->acceleration + wy;

        q->last_x = q->x;
        q->last_y = q->y;

        delay = q->delay * dt * 30.0;     /* 官方：Delay × dt × 30 */

        dx = q->x - c->p[i - 1].x;
        dy = q->y - c->p[i - 1].y;

        /* 重力方向变了多少 → 整条摆跟着转多少（除以空气阻力，转得温吞些）。
           ★ 这里是正确的旋转；官方源码在第二行误用了已被覆盖的 dx（见 DC77）。 */
        r  = dir_to_radian(q->last_gx, q->last_gy, cur_gx, cur_gy) / ZPHYS2_AIR_RESISTANCE;
        cs = cos(r); sn = sin(r);
        nx = cs * dx - sn * dy;
        ny = sn * dx + cs * dy;
        dx = nx; dy = ny;

        q->x = c->p[i - 1].x + dx;
        q->y = c->p[i - 1].y + dy;

        q->x += q->vx * delay + fx * delay * delay;
        q->y += q->vy * delay + fy * delay * delay;

        /* 约束：到父粒子的距离必须等于 Radius（这就是"摆长"） */
        nx = q->x - c->p[i - 1].x;
        ny = q->y - c->p[i - 1].y;
        normalize2(&nx, &ny);
        q->x = c->p[i - 1].x + nx * q->radius;
        q->y = c->p[i - 1].y + ny * q->radius;

        /* 官方的 MovementThreshold：太小的横向位移直接吸附到 0。
           这就是社区说的"输入太小摆会不动"的那条规格坑，照抄以保证
           将来导入 physics3.json 的模型表现一致（回避办法是加大输入或摆长）。 */
        if (fabs(q->x) < ZPHYS2_THRESHOLD) q->x = 0.0;

        if (delay != 0.0) {
            q->vx = ((q->x - q->last_x) / delay) * q->mobility;
            q->vy = ((q->y - q->last_y) / delay) * q->mobility;
        }
        q->last_gx = cur_gx;
        q->last_gy = cur_gy;
    }
}

double zphys2_angle(const zphys2 *c, int i, double gx, double gy, int inverted)
{
    double dx, dy, rad;
    if (!c || i < 1 || i >= c->n) return 0.0;
    normalize2(&gx, &gy);
    if (inverted) { gx = -gx; gy = -gy; }
    dx = c->p[i].x - c->p[i - 1].x;
    dy = c->p[i].y - c->p[i - 1].y;
    if (fabs(dx) < 1e-12 && fabs(dy) < 1e-12) return 0.0;
    rad = dir_to_radian(gx, gy, dx, dy);
    return rad * 180.0 / ZP2_PI;
}

void zphys2_advance(zphys2 *c, double tx, double ty, double angle_deg,
                    double gx, double gy, double wx, double wy, double dt)
{
    int i;
    double alpha;
    if (!c || c->n < 2) return;
    if (dt < 0.0) dt = 0.0;
    if (!c->in_init) {
        c->in_tx = tx; c->in_ty = ty; c->in_angle = angle_deg;
        c->in_init = 1;
    }
    c->remain += dt;
    if (c->remain > ZPHYS2_MAX_REMAIN) c->remain = 0.0;   /* 挂起太久就别追了 */

    while (c->remain >= ZPHYS2_STEP) {
        /* 输入线性插值：一帧里的每个子步各吃一段，不是全都吃帧末值 */
        double w = ZPHYS2_STEP / c->remain;
        double sx, sy, sa;
        if (w > 1.0) w = 1.0;
        sx = c->in_tx    * (1.0 - w) + tx        * w;
        sy = c->in_ty    * (1.0 - w) + ty        * w;
        sa = c->in_angle * (1.0 - w) + angle_deg * w;
        c->in_tx = sx; c->in_ty = sy; c->in_angle = sa;

        zphys2_step(c, sx, sy, sa, gx, gy, wx, wy, ZPHYS2_STEP);
        for (i = 1; i < c->n; ++i) {
            c->out_prev[i] = c->out_cur[i];
            c->out_cur[i]  = zphys2_angle(c, i, gx, gy, 0);
        }
        c->remain -= ZPHYS2_STEP;
    }
    alpha = c->remain / ZPHYS2_STEP;
    if (alpha < 0.0) alpha = 0.0;
    if (alpha > 1.0) alpha = 1.0;
    for (i = 1; i < c->n; ++i)
        c->out[i] = c->out_prev[i] * (1.0 - alpha) + c->out_cur[i] * alpha;
}

double zphys2_out(const zphys2 *c, int i)
{
    if (!c || i < 0 || i >= c->n) return 0.0;
    return c->out[i];
}
