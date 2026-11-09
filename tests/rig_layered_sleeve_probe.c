/* Test the fixed-rig mirrored deformers against the original parent groups.
   Numerical geometry checks, not a visual or general group-space guarantee. */
#include "core/zrig.h"
#include <math.h>
#include <stdio.h>

int main(int argc, char **argv)
{
    zrig *r[5] = {0};
    const char *ids[] = {"ParamArmL", "ParamArmR", "ParamElbowL", "ParamElbowR",
                         "ParamBreath", "ParamMotionDrive", "ParamSleeveFollow"};
    const double poses[][7] = {{0,0,0,0,0,0,0}, {1,-1,-1,1,1,1,.7},
                                {-1,1,1,-1,1,-1,-.7}, {.4,-.3,.6,-.8,.4,.35,.2}};
    int i, pose, side, col, row, scale_index;
    double maxerr = 0, separation = 0;
    if (argc != 6) return 2;
    for (i = 0; i < 5; ++i) {
        zdiag diag;
        char path[2048];
        zdiag_init(&diag);
        if (snprintf(path, sizeof(path), "%s/rig.json", argv[i + 1]) >= (int)sizeof(path)) return 2;
        r[i] = zrig_load(path, argv[i + 1], &diag);
        if (!r[i]) { fprintf(stderr, "could not load fixture %s\n", argv[i + 1]); return 1; }
        zrig_ambient_enable(r[i], 0);
        zrig_phys_set_enabled(r[i], 0);
    }
    for (pose = 0; pose < 4; ++pose) {
        for (i = 0; i < 5; ++i) {
            int k;
            for (k = 0; k < 7; ++k)
                if (zrig_param_set(r[i], ids[k], poses[pose][k])) {
                    fprintf(stderr, "parameter %s rejected\n", ids[k]); return 1;
                }
            zrig_tick(r[i], 1.0 + pose);
        }
        for (scale_index = 0; scale_index < 2; ++scale_index) {
            double scale = scale_index ? .6 : 1.0;
            for (i = 0; i < 5; ++i) if (!zrig_frame(r[i], scale, NULL, NULL)) return 1;
            for (side = 0; side < 2; ++side) {
                const char *part = side ? "arm_r" : "arm_l";
                const char *lower = side ? "forearm_r" : "forearm_l";
                for (row = 0; row <= 16; row += 8) for (col = 0; col <= 8; col += 4) {
                    double p[5][2], q[2];
                    for (i = 0; i < 5; ++i) {
                        if (!zrig_part_vertex_pos(r[i], part, scale, col, row, p[i])) return 1;
                        if (i < 3) {
                            if (!zrig_part_vertex_pos(r[i], lower, scale, col, row, q)) return 1;
                            if (fabs(q[0]-p[i][0]) > .0001 || fabs(q[1]-p[i][1]) > .0001) {
                                fprintf(stderr, "upper/lower mesh misaligned\n"); return 1;
                            }
                        }
                    }
                    for (i = 0; i < 2; ++i) {
                        double e0 = fabs(p[0][i] - p[3][i]);
                        double e1 = fabs(p[2][i] - p[4][i]);
                        double eh = fabs(p[1][i] - (p[3][i] + p[4][i]) * .5);
                        if (e0 > maxerr) maxerr = e0;
                        if (e1 > maxerr) maxerr = e1;
                        if (eh > maxerr) maxerr = eh;
                        if (fabs(p[3][i] - p[4][i]) > separation) separation = fabs(p[3][i] - p[4][i]);
                    }
                }
            }
        }
    }
    for (i = 0; i < 5; ++i) zrig_free(r[i]);
    printf("group/deformer max vertex error %.9g, nontrivial elbow difference %.3f\n", maxerr, separation);
    return (maxerr < .0001 && separation > 1.0) ? 0 : 1;
}
