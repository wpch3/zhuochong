#include "zperm.h"
#include "zjson.h"
#include "zc.h"
#include <stdlib.h>
#include <string.h>
#include <stdio.h>
#include <time.h>

#define MAX_CAPS 32
#define MAX_TIERS 8
#define MAX_MASKS 8

struct zperm_cap { char id[48]; char tier[32]; int enabled; };
struct zperm_mask { char id[32]; char pat[128]; };

struct zperm {
    char root[512];
    struct zperm_cap caps[MAX_CAPS]; int ncaps;
    char tier_ids[MAX_TIERS][32]; int ntiers;
    int estop; char hotkey[32]; char estop_cuts[8][32]; int ncuts;
    struct zperm_mask masks[MAX_MASKS]; int nmasks;
    char audit_path[256]; int audit_on; char audit_record[16][48]; int nrecord;
};

static int cap_find(zperm *p, const char *id){ for(int i=0;i<p->ncaps;i++) if(strcmp(p->caps[i].id,id)==0) return i; return -1; }
static int tier_cut(zperm *p, const char *tier){
    for(int i=0;i<p->ncuts;i++){ if(strcmp(p->estop_cuts[i],tier)==0) return 1; } return 0;
}
static int is_recorded(zperm *p, const char *cap){
    if(p->nrecord==0) return 1;
    for(int i=0;i<p->nrecord;i++){ if(strcmp(p->audit_record[i],cap)==0) return 1; } return 0;
}

zperm *zperm_load(const char *root, char *err, size_t errcap){
    zperm *p=(zperm*)calloc(1,sizeof(*p));
    if(!p) return NULL;
    z_strlcpy(p->root, root?root:".", sizeof(p->root));
    char path[1024]; snprintf(path,sizeof(path),"%s/config/permissions.json", p->root);
    zerr ze; zjson *j=zjson_parse_file(path, &ze);
    if(!j){
        if(err) snprintf(err,errcap,"no permissions.json at %s",path);
        return p;
    }
    zjson *tiers=zjson_get(j,"tiers");
    if(tiers){
        for(size_t i=0;i<zjson_count(tiers) && p->ntiers<MAX_TIERS;i++){
            zjson *t=zjson_at(tiers,i);
            zjson *jid=zjson_get(t,"id");
            const char *id=jid ? zjson_str(jid,NULL) : NULL;
            if(id) z_strlcpy(p->tier_ids[p->ntiers++], id, sizeof(p->tier_ids[0]));
        }
    }
    zjson *caps=zjson_get(j,"capabilities");
    if(caps){
        for(size_t i=0;i<zjson_count(caps) && p->ncaps<MAX_CAPS;i++){
            zjson *c=zjson_at(caps,i);
            const char *id=zjson_str(zjson_get(c,"id"),NULL);
            const char *tier=zjson_str(zjson_get(c,"tier"),NULL);
            int en=zjson_bool(zjson_get(c,"enabled"),0);
            if(id){
                z_strlcpy(p->caps[p->ncaps].id, id, sizeof(p->caps[0].id));
                if(tier) z_strlcpy(p->caps[p->ncaps].tier, tier, sizeof(p->caps[0].tier));
                p->caps[p->ncaps].enabled=en;
                p->ncaps++;
            }
        }
    }
    zjson *est=zjson_get(j,"e_stop");
    if(est){
        p->estop = zjson_bool(zjson_get(est,"enabled"),1);
        const char *hk=zjson_str(zjson_get(est,"hotkey"),NULL);
        if(hk) z_strlcpy(p->hotkey, hk, sizeof(p->hotkey));
        zjson *cuts=zjson_get(est,"cuts_tiers");
        if(cuts){
            for(size_t i=0;i<zjson_count(cuts) && p->ncuts<8;i++){
                const char *s=zjson_str(zjson_at(cuts,i),NULL);
                if(s) z_strlcpy(p->estop_cuts[p->ncuts++], s, sizeof(p->estop_cuts[0]));
            }
        }
    } else {
        p->estop=1; z_strlcpy(p->hotkey,"Ctrl+Shift+Esc",sizeof(p->hotkey));
    }
    zjson *masks=zjson_get(j,"sensitive_masks");
    if(masks){
        for(size_t i=0;i<zjson_count(masks) && p->nmasks<MAX_MASKS;i++){
            zjson *mm=zjson_at(masks,i);
            const char *id=zjson_str(zjson_get(mm,"id"),NULL);
            const char *pat=zjson_str(zjson_get(mm,"pattern"),NULL);
            if(id && pat){
                z_strlcpy(p->masks[p->nmasks].id, id, sizeof(p->masks[0].id));
                z_strlcpy(p->masks[p->nmasks].pat, pat, sizeof(p->masks[0].pat));
                p->nmasks++;
            }
        }
    }
    zjson *audit=zjson_get(j,"audit");
    if(audit){
        p->audit_on=zjson_bool(zjson_get(audit,"enabled"),1);
        const char *lp=zjson_str(zjson_get(audit,"log_path"),NULL);
        if(lp) z_strlcpy(p->audit_path, lp, sizeof(p->audit_path));
        zjson *rec=zjson_get(audit,"record");
        if(rec){
            for(size_t i=0;i<zjson_count(rec) && p->nrecord<16;i++){
                const char *s=zjson_str(zjson_at(rec,i),NULL);
                if(s) z_strlcpy(p->audit_record[p->nrecord++], s, sizeof(p->audit_record[0]));
            }
        }
    }
    zjson_free(j);
    return p;
}
void zperm_free(zperm *p){ if(p) free(p); }
int zperm_cap_enabled(zperm *p, const char *cap_id){
    if(!p||!cap_id) return 0;
    int idx=cap_find(p,cap_id);
    return idx>=0 ? p->caps[idx].enabled : 0;
}
const char *zperm_cap_tier(zperm *p, const char *cap_id){
    int idx=cap_find(p,cap_id);
    return idx>=0 ? p->caps[idx].tier : "";
}
int zperm_estop_active(zperm *p){ return p ? p->estop : 0; }
void zperm_estop_set(zperm *p, int on){ if(p) p->estop=on?1:0; }
int zperm_check(zperm *p, const char *cap_id){
    if(!p||!cap_id) return -1;
    int idx=cap_find(p,cap_id);
    if(idx<0) return -1;
    if(!p->caps[idx].enabled) return -1;
    if(p->estop && tier_cut(p, p->caps[idx].tier)) return -1;
    return 0;
}
int zperm_sensitive_hit(zperm *p, const char *title){
    if(!p||!title||p->nmasks==0) return 0;
    // case-insensitive substring check
    char low_title[256]; size_t n=strlen(title); if(n>=sizeof(low_title)) n=sizeof(low_title)-1;
    for(size_t k=0;k<n;k++) low_title[k]= (title[k]>='A'&&title[k]<='Z')? (title[k]+32): title[k];
    low_title[n]=0;
    for(int i=0;i<p->nmasks;i++){
        char low_pat[128]; size_t pn=strlen(p->masks[i].pat); if(pn>=sizeof(low_pat)) pn=sizeof(low_pat)-1;
        for(size_t k=0;k<pn;k++) low_pat[k]= (p->masks[i].pat[k]>='A'&&p->masks[i].pat[k]<='Z')? (p->masks[i].pat[k]+32): p->masks[i].pat[k];
        low_pat[pn]=0;
        if(strstr(low_title, low_pat)!=NULL) return 1;
        char buf[128]; z_strlcpy(buf, low_pat, sizeof(buf));
        char *tok=strtok(buf,"|");
        while(tok){ if(strstr(low_title,tok)) return 1; tok=strtok(NULL,"|"); }
    }
    return 0;
}
int zperm_audit(zperm *p, const char *cap_id, const char *detail){
    if(!p||!cap_id) return -1;
    if(!p->audit_on) return 0;
    if(!is_recorded(p, cap_id)) return 0;
    char path[1024];
    if(p->audit_path[0]) snprintf(path,sizeof(path),"%s/%s", p->root, p->audit_path);
    else snprintf(path,sizeof(path),"%s/data/audit.log", p->root);
    FILE *f=fopen(path,"a");
    if(!f) return -1;
    time_t now=time(NULL);
    struct tm *tm=gmtime(&now);
    char ts[32]; strftime(ts,sizeof(ts),"%Y-%m-%dT%H:%M:%SZ", tm);
    fprintf(f, "%s cap=%s detail=%s\n", ts, cap_id, detail?detail:"-");
    fclose(f);
    return 0;
}
