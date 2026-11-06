#ifndef ZIK_H
#define ZIK_H

/* Minimal 2D two-link inverse kinematics, pure C.
   Angles use screen coordinates (x right, y down); positive angle follows atan2(y,x).
   Elbow flex is the absolute turn away from a straight chain: 0° = straight. */

typedef struct { double x, y; } zik_vec2;

typedef struct {
    zik_vec2 shoulder;
    zik_vec2 elbow;
    zik_vec2 effector;         /* reachable endpoint; may differ from target if clamped */
    double shoulder_delta_deg; /* relative to rest upper-arm direction */
    double elbow_delta_deg;    /* relative to rest forearm-vs-upper angle */
    double elbow_flex_deg;     /* 0 = straight; strictly positive for a bent elbow */
    double target_error;       /* distance from requested target to returned effector */
    int branch;                /* -1 / +1, selects which side the elbow folds toward */
    int target_clamped;        /* target exceeded permitted chain reach */
    int constraints_satisfied;
} zik_solution;

enum {
    ZIK_OK = 0,
    ZIK_CONSTRAINT_UNSAT = 1, /* best geometric candidate returned, but limits conflict */
    ZIK_BAD_INPUT = -1
};

/* Analytic law-of-cosines solver. The result is populated for both OK and
   CONSTRAINT_UNSAT; callers must check the return before applying angles.
   elbow_min_flex_deg must be > 0 to reject a dead-straight limb. */
int zik_solve_two_link(zik_vec2 shoulder, zik_vec2 target,
                       double upper_len, double forearm_len,
                       double rest_upper_deg, double rest_forearm_deg,
                       double shoulder_min_delta_deg,
                       double shoulder_max_delta_deg,
                       double elbow_min_flex_deg,
                       double elbow_max_flex_deg,
                       int preferred_branch,
                       zik_solution *out);

#endif
