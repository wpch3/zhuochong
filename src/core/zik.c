#include "zik.h"

#include <math.h>
#include <stddef.h>

#define ZIK_PI 3.14159265358979323846
#define ZIK_EPS 1e-8

static double clampd(double v, double lo, double hi)
{
    return v < lo ? lo : (v > hi ? hi : v);
}

static double wrap180(double deg)
{
    while (deg > 180.0) deg -= 360.0;
    while (deg < -180.0) deg += 360.0;
    return deg;
}

static double excess(double v, double lo, double hi)
{
    return v < lo ? lo - v : (v > hi ? v - hi : 0.0);
}

static zik_vec2 add_scaled(zik_vec2 p, double len, double deg)
{
    zik_vec2 q;
    double a = deg * ZIK_PI / 180.0;
    q.x = p.x + len * cos(a);
    q.y = p.y + len * sin(a);
    return q;
}

typedef struct {
    zik_solution sol;
    double score;
} candidate;

static candidate solve_branch(zik_vec2 shoulder, zik_vec2 target,
                              double upper_len, double forearm_len,
                              double rest_upper_deg, double rest_rel_deg,
                              double shoulder_min, double shoulder_max,
                              double elbow_min, double elbow_max,
                              int branch, double target_clamp_error)
{
    candidate c;
    double dx = target.x - shoulder.x;
    double dy = target.y - shoulder.y;
    double d = hypot(dx, dy);
    double phi = atan2(dy, dx);
    double cos_alpha, alpha, upper, fore, rel, flex, sh_delta;
    double elbow_dot;
    c.sol.shoulder = shoulder;
    c.sol.branch = branch;
    c.sol.target_clamped = target_clamp_error > 1e-7;
    c.sol.target_error = target_clamp_error;
    c.sol.constraints_satisfied = 0;
    c.score = 1e30;
    if (d < ZIK_EPS) return c;

    cos_alpha = (upper_len * upper_len + d * d - forearm_len * forearm_len) /
                (2.0 * upper_len * d);
    alpha = acos(clampd(cos_alpha, -1.0, 1.0));
    upper = phi + (double)branch * alpha;
    c.sol.elbow = add_scaled(shoulder, upper_len, upper * 180.0 / ZIK_PI);
    c.sol.effector = target;
    fore = atan2(target.y - c.sol.elbow.y, target.x - c.sol.elbow.x) *
           180.0 / ZIK_PI;
    upper *= 180.0 / ZIK_PI;
    rel = wrap180(fore - upper);
    flex = fabs(rel);                    /* 0° is collinear/fully extended */
    sh_delta = wrap180(upper - rest_upper_deg);
    elbow_dot = wrap180(rel - rest_rel_deg);
    c.sol.shoulder_delta_deg = sh_delta;
    c.sol.elbow_delta_deg = elbow_dot;
    c.sol.elbow_flex_deg = flex;

    c.score = excess(sh_delta, shoulder_min, shoulder_max) +
              excess(flex, elbow_min, elbow_max);
    if (c.score < 1e-6) c.sol.constraints_satisfied = 1;
    return c;
}

int zik_solve_two_link(zik_vec2 shoulder, zik_vec2 target,
                       double upper_len, double forearm_len,
                       double rest_upper_deg, double rest_forearm_deg,
                       double shoulder_min_delta_deg,
                       double shoulder_max_delta_deg,
                       double elbow_min_flex_deg,
                       double elbow_max_flex_deg,
                       int preferred_branch,
                       zik_solution *out)
{
    double dx, dy, d, d_min, d_max, min_flex_rad, max_flex_rad;
    double use_d, ux, uy, clamp_error, rest_rel;
    zik_vec2 target_use;
    candidate a, b, *best;

    if (!out || !(upper_len > 0.0) || !(forearm_len > 0.0) ||
        !(shoulder_min_delta_deg <= shoulder_max_delta_deg) ||
        !(elbow_min_flex_deg > 0.0) ||
        !(elbow_min_flex_deg <= elbow_max_flex_deg) ||
        elbow_max_flex_deg >= 180.0 ||
        (preferred_branch != -1 && preferred_branch != 1)) return ZIK_BAD_INPUT;

    dx = target.x - shoulder.x;
    dy = target.y - shoulder.y;
    d = hypot(dx, dy);
    if (d < ZIK_EPS) return ZIK_BAD_INPUT;
    ux = dx / d;
    uy = dy / d;

    /* Flex bounds define the reachable annulus. Clamp only the endpoint distance,
       not either joint angle, so an infeasible target is explicit in target_error. */
    min_flex_rad = elbow_min_flex_deg * ZIK_PI / 180.0;
    max_flex_rad = elbow_max_flex_deg * ZIK_PI / 180.0;
    d_max = sqrt(upper_len * upper_len + forearm_len * forearm_len +
                 2.0 * upper_len * forearm_len * cos(min_flex_rad));
    d_min = sqrt(upper_len * upper_len + forearm_len * forearm_len +
                 2.0 * upper_len * forearm_len * cos(max_flex_rad));
    use_d = clampd(d, d_min, d_max);
    clamp_error = fabs(d - use_d);
    target_use.x = shoulder.x + ux * use_d;
    target_use.y = shoulder.y + uy * use_d;
    rest_rel = wrap180(rest_forearm_deg - rest_upper_deg);

    a = solve_branch(shoulder, target_use, upper_len, forearm_len,
                     rest_upper_deg, rest_rel,
                     shoulder_min_delta_deg, shoulder_max_delta_deg,
                     elbow_min_flex_deg, elbow_max_flex_deg,
                     preferred_branch, clamp_error);
    b = solve_branch(shoulder, target_use, upper_len, forearm_len,
                     rest_upper_deg, rest_rel,
                     shoulder_min_delta_deg, shoulder_max_delta_deg,
                     elbow_min_flex_deg, elbow_max_flex_deg,
                     -preferred_branch, clamp_error);
    best = a.score <= b.score ? &a : &b;
    *out = best->sol;
    return out->constraints_satisfied ? ZIK_OK : ZIK_CONSTRAINT_UNSAT;
}
