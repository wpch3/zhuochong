/* Same-state part A/B probe: hide/show/hide without advancing the rig clock.
 * Diagnostic frame generation, not an image-quality or performance verdict.
 * Usage: rig_part_ab rig.json base_dir part action steps scale outdir
 * Caller supplies a new empty output directory. */
#include "core/zrig.h"
#include <ctype.h>
#include <errno.h>
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static int save(const zimg *img, const char *dir, const char *name)
{
    char path[4096]; size_t size; uint8_t *data; FILE *f; int ok;
    int n = snprintf(path, sizeof(path), "%s/%s", dir, name);
    if (n < 0 || (size_t)n >= sizeof(path)) return -1;
    data = zimg_encode_png(img, &size); if (!data) return -1;
    /* C11 exclusive creation also refuses existing symlinks; never replace. */
    f = fopen(path,"wbx");
    if (!f) { free(data); return -1; }
    ok = fwrite(data, 1, size, f) == size;
    if (fclose(f) != 0) ok = 0;
    free(data);
    if (!ok) { remove(path); return -1; }
    return 0;
}

static int safe_id(const char *s)
{
    const unsigned char *p = (const unsigned char *)s;
    if (!*p) return 0;
    for (; *p; ++p) if (!isalnum(*p) && *p != '_' && *p != '-') return 0;
    return 1;
}

int main(int argc, char **argv)
{
    zdiag d; zrig *rig; const zimg *frame; zimg *off = NULL, *on = NULL, *off_again = NULL;
    char *end; long steps; double scale; int i, w, h, rc = 1;
    size_t count = 0, pixels;
    if (argc != 8) { fprintf(stderr,"usage: rig_part_ab rig.json base_dir part action steps scale outdir\n"); return 2; }
    if (!safe_id(argv[3]) || !safe_id(argv[4])) return 2;
    errno=0; steps=strtol(argv[5],&end,10);
    if (errno || end==argv[5] || *end || steps<0 || steps>36000) return 2;
    errno=0; scale=strtod(argv[6],&end);
    if (errno || end==argv[6] || *end || !isfinite(scale) || scale<0.2 || scale>2.0) return 2;
    zdiag_init(&d); zrig_set_render_threads(1);
    rig=zrig_load(argv[1],argv[2],&d);
    if (!rig) { fprintf(stderr,"rig load failed (check external dependencies)\n"); return 1; }
    zrig_blink_set_manual(rig,0);
    zrig_tick(rig,0.0);
    if (!zrig_action_request(rig,argv[4],"part_ab",1)) { fprintf(stderr,"action unavailable\n"); goto done; }
    for (i=1;i<=steps;i++) zrig_tick(rig,(double)i/60.0);
    if (zrig_part_vis_set(rig,argv[3],0)!=0) { fprintf(stderr,"part unavailable\n"); goto done; }
    frame=zrig_frame(rig,scale,&w,&h); if (!frame || !(off=zimg_clone(frame))) goto done;
    if (zrig_part_vis_set(rig,argv[3],1)!=0) goto done;
    frame=zrig_frame(rig,scale,&w,&h); if (!frame || !(on=zimg_clone(frame))) goto done;
    if (zrig_part_vis_set(rig,argv[3],0)!=0) goto done;
    frame=zrig_frame(rig,scale,&w,&h); if (!frame || !(off_again=zimg_clone(frame))) goto done;
    if (off->w!=on->w || off->h!=on->h || off->w!=off_again->w || off->h!=off_again->h) goto done;
    pixels=(size_t)off->w*(size_t)off->h;
    if (memcmp(off->px,off_again->px,pixels*4)!=0) { fprintf(stderr,"same-state hide/show/hide not stable\n"); goto done; }
    for (size_t j=0;j<pixels;j++) if (memcmp(off->px+j*4,on->px+j*4,4)!=0) count++;
    if (save(off,argv[7],"off.png") || save(on,argv[7],"on.png")) { fprintf(stderr,"output failed or already exists\n"); goto done; }
    printf("{\"part\":\"%s\",\"action\":\"%s\",\"steps\":%ld,\"scale\":%.3f,\"width\":%d,\"height\":%d,\"changed_pixels\":%zu,\"hide_show_hide_equal\":true}\n",
           argv[3],argv[4],steps,scale,off->w,off->h,count);
    rc=0;
done:
    zimg_free(off);zimg_free(on);zimg_free(off_again);zrig_free(rig);return rc;
}
