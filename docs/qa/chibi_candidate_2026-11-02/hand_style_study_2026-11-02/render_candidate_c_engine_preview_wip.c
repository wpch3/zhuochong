#include "zrig.h"
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static int setv(zrig *r,const char *id,double v){if(zrig_param_set(r,id,v)!=0){fprintf(stderr,"missing parameter %s\n",id);return -1;}return 0;}
int main(int argc,char **argv){
    zrig *r; zdiag d; zerr e; const zimg *f; int w=0,h=0,ambient,rc; double wrist,shoulder,elbow,tick; const char *action;
    if(argc!=12){fprintf(stderr,"usage: %s rig base output style wrist_deg shoulder_deg elbow_deg action tick_sec ambient hide_core_accessories\n",argv[0]);return 2;}
    wrist=strtod(argv[5],NULL);shoulder=strtod(argv[6],NULL);elbow=strtod(argv[7],NULL);action=argv[8];tick=strtod(argv[9],NULL);ambient=atoi(argv[10]);
    if(!isfinite(wrist)||!isfinite(shoulder)||!isfinite(elbow)||!isfinite(tick)||tick<0)return 2;
    zdiag_init(&d);r=zrig_load(argv[1],argv[2],&d);if(!r){zdiag_print(&d,stderr);return 3;}
    if(atoi(argv[11])){const char *hidden[]={"acc_ear_cat_l","acc_ear_cat_r","acc_tail_cat_relaxed","acc_tail_cat_up","acc_tail_cat_puff","acc_tail_cat_tuck"};for(size_t i=0;i<sizeof(hidden)/sizeof(hidden[0]);++i)if(zrig_part_vis_set(r,hidden[i],0)!=0){fprintf(stderr,"could not hide core accessory %s\n",hidden[i]);zrig_free(r);return 10;}}
    if(zrig_pose_set(r,"hand_style",argv[4])!=0){fprintf(stderr,"missing hand_style %s\n",argv[4]);zrig_free(r);return 4;}zrig_pose_snap(r);zrig_ambient_enable(r,ambient);
    if(setv(r,"ParamHandL",wrist/22.0)||setv(r,"ParamHandR",wrist/22.0)||setv(r,"ParamArmLA",shoulder/18.0)||setv(r,"ParamArmRA",shoulder/18.0)||setv(r,"ParamArmLB",elbow/18.0)||setv(r,"ParamArmRB",elbow/18.0)){zrig_free(r);return 5;}
    if(strcmp(action,"none")!=0){rc=zrig_action_request(r,action,"isolated QA matrix",1);if(rc<0){fprintf(stderr,"action request failed: %s\n",action);zrig_free(r);return 6;}}
    zrig_tick(r,tick);f=zrig_frame(r,1.0,&w,&h);if(!f||w!=848||h!=1360){fprintf(stderr,"bad frame %dx%d\n",w,h);zrig_free(r);return 7;}
    zerr_clear(&e);if(zimg_save_png(f,argv[3],&e)!=0){fprintf(stderr,"save failed: %s\n",e.msg);zrig_free(r);return 8;}
    if(zrig_action_geom_channels(r)!=0){fprintf(stderr,"unexpected geometry action channels\n");zrig_free(r);return 9;}
    printf("loaded=%s size=%dx%d parts=%d styles=(%.0f,%.0f) wrist=(%.8f,%.8f) shoulder=(%.8f,%.8f) elbow=(%.8f,%.8f) requested_action=%s active_action=%s sample_tick=%.3fs frame_scale=1.0 ambient=%d core_hidden=%d\n",zrig_id(r),w,h,zrig_part_count(r),zrig_pose_weight(r,"hand_style","small"),zrig_pose_weight(r,"hand_style","mitten"),zrig_param_get(r,"ParamHandL"),zrig_param_get(r,"ParamHandR"),zrig_param_get(r,"ParamArmLA"),zrig_param_get(r,"ParamArmRA"),zrig_param_get(r,"ParamArmLB"),zrig_param_get(r,"ParamArmRB"),strcmp(action,"none")==0?"none":action,zrig_action(r)?zrig_action(r):"(null)",tick,ambient,atoi(argv[11]));
    zrig_free(r);return 0;
}
