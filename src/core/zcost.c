#include "zcost.h"
#include "zjson.h"
#include "zc.h"
#include <stdlib.h>
#include <string.h>
#include <stdio.h>
#define MAX_CAPS 8
struct zcost_cap { char id[32]; double daily; double quota_pct; double spent; };
struct zcost {
    char root[512];
    double daily_cap, monthly_cap; char action[16];
    struct zcost_cap caps[MAX_CAPS]; int ncaps;
    char downgrade_order[8][32]; int norder;
    double hourly_factor;
    int idle_enabled; double idle_s; double idle_fps;
    double month_spent;
};
zcost *zcost_load(const char *root, char *err, size_t errcap){
    zcost *p=(zcost*)calloc(1,sizeof(*p));
    if(!p) return NULL;
    z_strlcpy(p->root, root?root:".", sizeof(p->root));
    p->daily_cap=5.0; p->monthly_cap=50.0; z_strlcpy(p->action,"auto_stop",sizeof(p->action));
    p->hourly_factor=2.5; p->idle_enabled=1; p->idle_s=300; p->idle_fps=0.2;
    char path[1024]; snprintf(path,sizeof(path),"%s/config/cost_limits.json", p->root);
    zerr ze; zjson *j=zjson_parse_file(path,&ze);
    if(!j){
        if(err) snprintf(err,errcap,"no cost_limits.json");
        return p;
    }
    zjson *hard=zjson_get(j,"hard_caps");
    if(hard){
        p->daily_cap=zjson_num(zjson_get(hard,"daily_cny"),p->daily_cap);
        p->monthly_cap=zjson_num(zjson_get(hard,"monthly_cny"),p->monthly_cap);
        const char *a=zjson_str(zjson_get(hard,"action"),NULL);
        if(a) z_strlcpy(p->action,a,sizeof(p->action));
    }
    zjson *pc=zjson_get(j,"per_capability");
    if(pc){
        for(size_t i=0;i<zjson_count(pc)&&p->ncaps<MAX_CAPS;i++){
            zjson *c=zjson_at(pc,i);
            const char *id=zjson_str(zjson_get(c,"id"),NULL);
            if(!id) continue;
            z_strlcpy(p->caps[p->ncaps].id,id,sizeof(p->caps[0].id));
            p->caps[p->ncaps].daily=zjson_num(zjson_get(c,"daily_cny"),1.0);
            p->caps[p->ncaps].quota_pct=zjson_num(zjson_get(c,"quota_pct"),25);
            p->ncaps++;
        }
    }
    zjson *dg=zjson_get(j,"downgrade");
    if(dg){
        zjson *o=zjson_get(dg,"order");
        if(o) for(size_t i=0;i<zjson_count(o)&&p->norder<8;i++){
            const char *s=zjson_str(zjson_at(o,i),NULL);
            if(s) z_strlcpy(p->downgrade_order[p->norder++],s,sizeof(p->downgrade_order[0]));
        }
    }
    zjson *est=zjson_get(j,"estimate");
    if(est) p->hourly_factor=zjson_num(zjson_get(est,"realtime_factor"),p->hourly_factor);
    zjson *idle=zjson_get(j,"idle_downclock");
    if(idle){
        p->idle_enabled=zjson_bool(zjson_get(idle,"enabled"),1);
        p->idle_s=zjson_num(zjson_get(idle,"idle_s"),p->idle_s);
        p->idle_fps=zjson_num(zjson_get(idle,"target_fps"),p->idle_fps);
    }
    zjson_free(j); return p;
}
void zcost_free(zcost *p){ if(p) free(p); }
int zcost_add(zcost *p, const char *cap_id, double cny){
    if(!p||!cap_id) return -1;
    p->month_spent+=cny;
    for(int i=0;i<p->ncaps;i++) if(strcmp(p->caps[i].id,cap_id)==0){ p->caps[i].spent+=cny; break; }
    return 0;
}
static double cap_spent(zcost *p, const char *cap){ for(int i=0;i<p->ncaps;i++) if(strcmp(p->caps[i].id,cap)==0) return p->caps[i].spent; return 0; }
static double cap_daily(zcost *p, const char *cap){ for(int i=0;i<p->ncaps;i++) if(strcmp(p->caps[i].id,cap)==0) return p->caps[i].daily; return p->daily_cap; }
int zcost_tripped(zcost *p, const char *cap_id){
    if(!p) return 0;
    if(p->month_spent >= p->monthly_cap) return 1;
    double total=0; for(int i=0;i<p->ncaps;i++) total+=p->caps[i].spent;
    if(total >= p->daily_cap) return 1;
    if(cap_id){ double sp=cap_spent(p,cap_id); double dc=cap_daily(p,cap_id); if(sp >= dc) return 1; }
    return 0;
}
const char *zcost_downgrade(zcost *p){
    if(!p||p->norder==0) return "local_model";
    return p->downgrade_order[0];
}
double zcost_estimate_hourly(zcost *p){
    if(!p) return 0;
    double sum=0; for(int i=0;i<p->ncaps;i++) sum+=p->caps[i].daily;
    if(sum==0) sum=p->daily_cap;
    return sum/24.0 * p->hourly_factor;
}
int zcost_idle_should_downclock(zcost *p, double idle_s){
    if(!p||!p->idle_enabled) return 0;
    return idle_s >= p->idle_s ? 1 : 0;
}
