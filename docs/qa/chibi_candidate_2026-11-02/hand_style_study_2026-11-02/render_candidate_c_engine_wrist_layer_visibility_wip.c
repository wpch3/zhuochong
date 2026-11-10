#include "zrig.h"
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static int setv(zrig *r, const char *id, double value) {
    if (zrig_param_set(r, id, value) != 0) {
        fprintf(stderr, "missing parameter %s\n", id);
        return -1;
    }
    return 0;
}

static int hide_part(zrig *r, const char *id) {
    if (zrig_part_vis_set(r, id, 0) != 0) {
        fprintf(stderr, "could not hide part %s\n", id);
        return -1;
    }
    return 0;
}

int main(int argc, char **argv) {
    zrig *r;
    zdiag d;
    zerr e;
    const zimg *frame;
    int w = 0, h = 0, ambient;
    double wrist, shoulder, elbow, tick;
    const char *mode;

    if (argc != 13) {
        fprintf(stderr,
                "usage: %s rig base output style wrist_deg shoulder_deg elbow_deg "
                "action tick_sec ambient hide_core_accessories layer_mode\n",
                argv[0]);
        return 2;
    }
    wrist = strtod(argv[5], NULL);
    shoulder = strtod(argv[6], NULL);
    elbow = strtod(argv[7], NULL);
    tick = strtod(argv[9], NULL);
    ambient = atoi(argv[10]);
    mode = argv[12];
    if (!isfinite(wrist) || !isfinite(shoulder) || !isfinite(elbow) ||
        !isfinite(tick) || tick < 0) return 2;

    zdiag_init(&d);
    r = zrig_load(argv[1], argv[2], &d);
    if (!r) {
        zdiag_print(&d, stderr);
        return 3;
    }
    if (atoi(argv[11])) {
        const char *hidden[] = {
            "acc_ear_cat_l", "acc_ear_cat_r", "acc_tail_cat_relaxed",
            "acc_tail_cat_up", "acc_tail_cat_puff", "acc_tail_cat_tuck"
        };
        for (size_t i = 0; i < sizeof(hidden) / sizeof(hidden[0]); ++i) {
            if (hide_part(r, hidden[i]) != 0) {
                zrig_free(r);
                return 4;
            }
        }
    }
    if (zrig_pose_set(r, "hand_style", argv[4]) != 0) {
        fprintf(stderr, "missing hand_style %s\n", argv[4]);
        zrig_free(r);
        return 5;
    }
    zrig_pose_snap(r);
    zrig_ambient_enable(r, ambient);

    if (setv(r, "ParamHandL", wrist / 22.0) ||
        setv(r, "ParamHandR", wrist / 22.0) ||
        setv(r, "ParamArmLA", shoulder / 18.0) ||
        setv(r, "ParamArmRA", shoulder / 18.0) ||
        setv(r, "ParamArmLB", elbow / 18.0) ||
        setv(r, "ParamArmRB", elbow / 18.0)) {
        zrig_free(r);
        return 6;
    }
    if (strcmp(argv[8], "none") != 0 &&
        zrig_action_request(r, argv[8], "isolated wrist-layer QA", 1) < 0) {
        fprintf(stderr, "action request failed: %s\n", argv[8]);
        zrig_free(r);
        return 7;
    }

    if (strcmp(mode, "forearm_hidden") == 0) {
        if (hide_part(r, "arm_l_fore") || hide_part(r, "arm_r_fore")) {
            zrig_free(r);
            return 8;
        }
    } else if (strcmp(mode, "mitten_hidden") == 0) {
        if (hide_part(r, "hand_l_mitten_trial24_candidate_wip") ||
            hide_part(r, "hand_r_mitten_trial24_candidate_wip")) {
            zrig_free(r);
            return 9;
        }
    } else if (strcmp(mode, "normal") != 0) {
        fprintf(stderr, "unknown layer_mode %s\n", mode);
        zrig_free(r);
        return 10;
    }

    zrig_tick(r, tick);
    frame = zrig_frame(r, 1.0, &w, &h);
    if (!frame || w != 848 || h != 1360) {
        fprintf(stderr, "bad frame %dx%d\n", w, h);
        zrig_free(r);
        return 11;
    }
    zerr_clear(&e);
    if (zimg_save_png(frame, argv[3], &e) != 0) {
        fprintf(stderr, "save failed: %s\n", e.msg);
        zrig_free(r);
        return 12;
    }
    if (zrig_action_geom_channels(r) != 0) {
        fprintf(stderr, "unexpected geometry action channels\n");
        zrig_free(r);
        return 13;
    }
    printf("loaded=%s size=%dx%d style=%s wrist=%.1f shoulder=%.1f elbow=%.1f "
           "requested_action=%s active_action=%s mode=%s tick=%.3fs ambient=%d core_hidden=%d\n",
           zrig_id(r), w, h, argv[4], wrist, shoulder, elbow,
           strcmp(argv[8], "none") == 0 ? "none" : argv[8],
           zrig_action(r) ? zrig_action(r) : "(null)", mode, tick,
           ambient, atoi(argv[11]));
    zrig_free(r);
    return 0;
}
