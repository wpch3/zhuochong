/* Probe actual C runtime vertex coordinates of an editor-exported body mesh. */
#include "core/zrig.h"
#include <stdio.h>

int main(int argc, char **argv)
{
    zdiag diag;
    zrig *rig;
    const double values[] = {0.0, 0.5, 1.0};
    int i;
    if (argc != 3) return 2;
    zdiag_init(&diag);
    rig = zrig_load(argv[1], argv[2], &diag);
    if (!rig) { fprintf(stderr, "zrig_load failed\n"); return 1; }
    for (i = 0; i < 3; ++i) {
        double pos[2];
        if (zrig_param_set(rig, "ParamEditorMesh", values[i]) != 0) return 1;
        zrig_tick(rig, (double)i + 1.0);
        if (!zrig_part_vertex_pos(rig, "body", 1.0, 1, 1, pos)) return 1;
        printf("%.1f %.12f %.12f\n", values[i], pos[0], pos[1]);
    }
    zrig_free(rig);
    return 0;
}
