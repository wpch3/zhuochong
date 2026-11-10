#include "zperf.h"
#include "zjson.h"
#include "zc.h"
#include <stdlib.h>
#include <string.h>
struct zperf_budget { char mode[32]; double cpu, mem; };
struct zperf {
    char root[512];
    int render_first;
    struct zperf_budget budgets[8]; int nbudgets;
    double idle_cpu, realtime_cpu, render_ms, png_ms;
    char degradable[8][32]; int ndeg;
    int yield_on; double yield_idle;
};
zperf *zperf_load(const char *root, char *err, size_t errcap){
    zperf *p=(zperf*)calloc(1,sizeof(*p)); if(!p) return NULL;
    z_strlcpy(p->root, root?root:".", sizeof(p->root));
    p->render_first=1; p->yield_on=1; p->yield_idle=5.0;
    char path[1024]; snprintf(path,sizeof(path),"%s/config/perf_budget.json", p->root);
    zerr ze; zjson *j=zjson_parse_file(path,&ze);
    if(!j){
        if(err) snprintf(err,errcap,"no perf_budget.json");
        return p;
    }
    zjson *pri=zjson_get(j,"priority"); if(pri) p->render_first=zjson_bool(zjson_get(pri,"render_first"),1);
    zjson *buds=zjson_get(j,"budgets");
    if(buds) for(size_t i=0;i<zjson_count(buds)&&p->nbudgets<8;i++){
        zjson *b=zjson_at(buds,i);
        const char *m=zjson_str(zjson_get(b,"mode"),NULL);
        if(!m) continue;
        z_strlcpy(p->budgets[p->nbudgets].mode,m,sizeof(p->budgets[0].mode));
        p->budgets[p->nbudgets].cpu=zjson_num(zjson_get(b,"cpu_pct"),0);
        p->budgets[p->nbudgets].mem=zjson_num(zjson_get(b,"mem_mb"),0);
        p->nbudgets++;
    }
    zjson *meas=zjson_get(j,"measured");
    if(meas){
        p->idle_cpu=zjson_num(zjson_get(meas,"idle_cpu"),0);
        p->realtime_cpu=zjson_num(zjson_get(meas,"realtime_cpu"),0);
        p->render_ms=zjson_num(zjson_get(meas,"render_ms"),0);
        p->png_ms=zjson_num(zjson_get(meas,"png_ms"),0);
    }
    zjson *deg=zjson_get(j,"degradable");
    if(deg) for(size_t i=0;i<zjson_count(deg)&&p->ndeg<8;i++){
        zjson *d=zjson_at(deg,i);
        const char *id=zjson_str(zjson_get(d,"id"),NULL);
        if(id) z_strlcpy(p->degradable[p->ndeg++],id,sizeof(p->degradable[0]));
    }
    zjson *yl=zjson_get(j,"yield_on_user_active");
    if(yl) p->yield_on=zjson_bool(zjson_get(yl,"enabled"),1);
    zjson_free(j); return p;
}
void zperf_free(zperf *p){ if(p) free(p); }
int zperf_render_first(zperf *p){ return p ? p->render_first : 1; }
int zperf_budget_ok(zperf *p, const char *mode, double cpu, double mem_mb){
    if(!p||!mode) return 1;
    for(int i=0;i<p->nbudgets;i++) if(strcmp(p->budgets[i].mode,mode)==0){
        if(cpu > p->budgets[i].cpu+1e-6) return 0;
        if(mem_mb > p->budgets[i].mem+1e-6) return 0;
        return 1;
    }
    return 1;
}
const char *zperf_degrade_next(zperf *p, const char *cur){
    if(!p||p->ndeg==0) return NULL;
    if(!cur) return p->degradable[0];
    for(int i=0;i<p->ndeg;i++) if(strcmp(p->degradable[i],cur)==0){
        if(i+1<p->ndeg) return p->degradable[i+1];
        return p->degradable[i];
    }
    return p->degradable[0];
}
int zperf_should_yield(zperf *p, double user_idle_s){
    if(!p||!p->yield_on) return 0;
    return user_idle_s < p->yield_idle ? 1 : 0;
}
double zperf_measured(zperf *p, const char *key){
    if(!p||!key) return 0;
    if(strcmp(key,"idle_cpu")==0) return p->idle_cpu;
    if(strcmp(key,"realtime_cpu")==0) return p->realtime_cpu;
    if(strcmp(key,"render_ms")==0) return p->render_ms;
    if(strcmp(key,"png_ms")==0) return p->png_ms;
    return 0;
}
