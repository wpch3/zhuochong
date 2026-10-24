/* bench_soft3d.c —— CPU 软光栅 3D 可行性基准（2026-10-15，支撑 DC42 / A36.3）
 *
 * 为什么留着它：A36.3「自己开窗口渲 3D」本来准备否决，是这个基准把否决结论推翻了。
 * A33.3 要求结论带可复算证据，所以源码进仓库，谁都能重跑。
 *
 *   gcc -O2 -o /tmp/bench_soft3d tools/bench/bench_soft3d.c -lm
 *   /tmp/bench_soft3d <三角形数> <层数> <遍数>
 *   /tmp/bench_soft3d 20000 3 2      # 典型 VRoid 模型 + 3 层 overdraw + MToon 描边遍
 *
 * 2026-10-15 沙箱实测（2 核，单线程，848x1360）：
 *   20000 3 1（无描边）  79.5 ms / 12.6 fps
 *   20000 3 2            116.7 ms / 8.6 fps
 *   40000 3 2            131.7 ms / 7.6 fps
 *   去掉纹理采样         41.3 ms / 24.2 fps
 * 对照：本项目 2D 一帧 848x1360 = 30.8ms（分块多线程，DC37）。3D 约贵 4 倍。
 *
 * 口径与边界（别拿它当"3D 已经能跑"的证据）：
 *   · 建模：参数化壳体，三角形是小片（平均 400px），和真实网格一致。
 *     **第一版用随机顶点连三角形，得到 5 秒/帧的假结果** —— 巨型三角形让包围盒
 *     扫描爆炸。基准本身错了，不是 3D 慢。教训见 LESSONS。
 *   · 含：蒙皮(4 权重) / 透视投影 / z-test / 透视正确 UV / 双线性纹理 / 描边遍。
 *   · 不含：morph target、半透明排序与 alpha blend、抗锯齿、阴影、摇骨物理、
 *     真实 VRM 的不均匀三角形分布。**这些都会让它更慢**，所以 116.7ms 是乐观下界。
 *   · 单线程。本项目 2D 侧分块多线程在 2 核上实测 1.66x。
 */
/* 修正版：上一版用随机顶点连三角形，结果每个三角形横跨整个人体包围盒，
   包围盒光栅化扫了巨量像素再被重心坐标剔掉 —— 基准本身是错的。
   这一版按真实网格建模：参数化壳体（nu x nv 网格）连相邻点，
   三角形在屏幕上就是几十像素的小片，和真实 VRM 一致。
   仍然刻意便宜：无纹理、无 MToon 描边、无阴影、无 AA、无 morph target。 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include <time.h>
#define W 848
#define H 1360
#define TEXW 1024
#define TEXH 1024
static unsigned char *tex;
static double now_ms(void){struct timespec ts;clock_gettime(CLOCK_MONOTONIC,&ts);
    return ts.tv_sec*1000.0+ts.tv_nsec/1e6;}
typedef struct{float x,y,z;}V3;
typedef struct{V3 p,n;float u,v;unsigned char bi[4];float bw[4];}Vtx;
#define NBONE 64
static float bone[NBONE][12];
static float *zbuf; static unsigned char *cbuf;
static Vtx *vtx; static int *idx; static int NV,NT;
static long px_tested=0, px_written=0;

static void skin(const Vtx*v,V3*op,V3*on){
    float px=0,py=0,pz=0,nx=0,ny=0,nz=0;
    for(int k=0;k<4;k++){float w=v->bw[k];if(w<=0.f)continue;const float*m=bone[v->bi[k]];
        px+=w*(m[0]*v->p.x+m[1]*v->p.y+m[2]*v->p.z+m[3]);
        py+=w*(m[4]*v->p.x+m[5]*v->p.y+m[6]*v->p.z+m[7]);
        pz+=w*(m[8]*v->p.x+m[9]*v->p.y+m[10]*v->p.z+m[11]);
        nx+=w*(m[0]*v->n.x+m[1]*v->n.y+m[2]*v->n.z);
        ny+=w*(m[4]*v->n.x+m[5]*v->n.y+m[6]*v->n.z);
        nz+=w*(m[8]*v->n.x+m[9]*v->n.y+m[10]*v->n.z);}
    op->x=px;op->y=py;op->z=pz;on->x=nx;on->y=ny;on->z=nz;
}
static void tri(V3 a,V3 b,V3 c,V3 na,float ua,float va_,float ub,float vb,float uc,float vc){
    float minx=a.x,maxx=a.x,miny=a.y,maxy=a.y;
    if(b.x<minx)minx=b.x; if(b.x>maxx)maxx=b.x;
    if(c.x<minx)minx=c.x; if(c.x>maxx)maxx=c.x;
    if(b.y<miny)miny=b.y; if(b.y>maxy)maxy=b.y;
    if(c.y<miny)miny=c.y; if(c.y>maxy)maxy=c.y;
    int x0=(int)floorf(minx),x1=(int)ceilf(maxx),y0=(int)floorf(miny),y1=(int)ceilf(maxy);
    if(x0<0)x0=0; if(y0<0)y0=0; if(x1>W-1)x1=W-1; if(y1>H-1)y1=H-1;
    float d=(b.y-c.y)*(a.x-c.x)+(c.x-b.x)*(a.y-c.y);
    if(fabsf(d)<1e-6f)return; float inv=1.f/d;
    float L=na.z>0?na.z:-na.z; unsigned char lum=(unsigned char)(60+195*L);
    for(int y=y0;y<=y1;y++)for(int x=x0;x<=x1;x++){
        px_tested++;
        float fx=x+0.5f,fy=y+0.5f;
        float w0=((b.y-c.y)*(fx-c.x)+(c.x-b.x)*(fy-c.y))*inv;
        float w1=((c.y-a.y)*(fx-c.x)+(a.x-c.x)*(fy-c.y))*inv;
        float w2=1.f-w0-w1;
        if(w0<0||w1<0||w2<0)continue;
        float z=w0*a.z+w1*b.z+w2*c.z; int o=y*W+x;
        if(z>=zbuf[o])continue;
        /* 透视正确 UV 插值 + 双线性纹理采样 */
        float iw0=w0/a.z, iw1=w1/b.z, iw2=w2/c.z, iws=iw0+iw1+iw2;
        float uu=(iw0*ua+iw1*ub+iw2*uc)/iws, vv=(iw0*va_+iw1*vb+iw2*vc)/iws;
        float tx=uu*(TEXW-1), ty=vv*(TEXH-1);
        int ix=(int)tx, iy=(int)ty; if(ix<0)ix=0; if(iy<0)iy=0;
        if(ix>TEXW-2)ix=TEXW-2; if(iy>TEXH-2)iy=TEXH-2;
        float fx2=tx-ix, fy2=ty-iy;
        const unsigned char*t00=&tex[(iy*TEXW+ix)*4], *t10=t00+4;
        const unsigned char*t01=&tex[((iy+1)*TEXW+ix)*4], *t11=t01+4;
        unsigned char px4[4];
        for(int ch=0;ch<4;ch++){
            float v0=t00[ch]+(t10[ch]-t00[ch])*fx2;
            float v1=t01[ch]+(t11[ch]-t01[ch])*fx2;
            px4[ch]=(unsigned char)(v0+(v1-v0)*fy2);
        }
        zbuf[o]=z; px_written++;
        cbuf[o*4+0]=(unsigned char)(px4[0]*lum/255);
        cbuf[o*4+1]=(unsigned char)(px4[1]*lum/255);
        cbuf[o*4+2]=(unsigned char)(px4[2]*lum/255);
        cbuf[o*4+3]=255;
    }
}
int main(int argc,char**argv){
    int target = argc>1?atoi(argv[1]):20000;
    int SHELL = argc>2?atoi(argv[2]):3;
    int PASSES = argc>3?atoi(argv[3]):1;  /* 2 = 加 MToon 描边遍 */   /* 层数：身体/衣服/头发，制造真实 overdraw */
    /* 每层一个参数化壳：nu x nv 网格 -> nu*nv*2 三角形 */
    int per = target/SHELL;
    int nv_=(int)sqrt(per/2.0), nu_=per/(2*nv_); if(nu_<3)nu_=3; if(nv_<3)nv_=3;
    NV=SHELL*(nu_+1)*(nv_+1); NT=SHELL*nu_*nv_*2;
    vtx=malloc(sizeof(Vtx)*NV); idx=malloc(sizeof(int)*NT*3);
    zbuf=malloc(sizeof(float)*W*H); cbuf=malloc(4*W*H);
    tex=malloc(4*TEXW*TEXH); for(int i=0;i<TEXW*TEXH*4;i++) tex[i]=(unsigned char)(i*37%251);
    srand(12345);
    for(int i=0;i<NBONE;i++){memset(bone[i],0,sizeof(bone[i]));
        bone[i][0]=bone[i][5]=bone[i][10]=1.f; bone[i][3]=(rand()%100)/2000.f;}
    int vi=0, ti=0;
    for(int s=0;s<SHELL;s++){
        int base=vi; float rr=0.16f+0.015f*s;      /* 壳半径，层层外扩 */
        for(int u=0;u<=nu_;u++)for(int v=0;v<=nv_;v++){
            float fu=(float)u/nu_, fv=(float)v/nv_;
            float ang=fv*6.2831853f;
            float rad=rr*(0.55f+0.75f*sinf(fu*3.14159f)); /* 腰细肩宽，像个人 */
            vtx[vi].p.x=rad*cosf(ang); vtx[vi].p.z=rad*sinf(ang);
            vtx[vi].p.y=fu*1.55f;
            vtx[vi].n.x=cosf(ang); vtx[vi].n.y=0.2f; vtx[vi].n.z=sinf(ang);
            vtx[vi].u=fv; vtx[vi].v=fu;
            for(int k=0;k<4;k++){vtx[vi].bi[k]=(int)(fu*(NBONE-4))+k; vtx[vi].bw[k]=0.25f;}
            vi++;
        }
        for(int u=0;u<nu_;u++)for(int v=0;v<nv_;v++){
            int a=base+u*(nv_+1)+v, b=a+1, c=a+(nv_+1), d=c+1;
            idx[ti*3]=a;idx[ti*3+1]=b;idx[ti*3+2]=c;ti++;
            idx[ti*3]=b;idx[ti*3+1]=d;idx[ti*3+2]=c;ti++;
        }
    }
    NV=vi; NT=ti;
    V3*sp=malloc(sizeof(V3)*NV),*sn=malloc(sizeof(V3)*NV);
    int FR=20; double tskin=0,trast=0;
    for(int f=0;f<FR;f++){
        for(int i=0;i<W*H;i++)zbuf[i]=1e30f;
        memset(cbuf,0,4*W*H);
        if(f==1){px_tested=0;px_written=0;}
        double t0=now_ms();
        for(int i=0;i<NV;i++){V3 p,n;skin(&vtx[i],&p,&n);
            float zc=p.z+2.0f, s=1700.f/zc;
            sp[i].x=W*0.5f+p.x*s; sp[i].y=H*0.95f-p.y*s; sp[i].z=zc; sn[i]=n;}
        double t1=now_ms();
        for(int pass=0; pass<PASSES; pass++)
          for(int t=0;t<NT;t++){int i0=idx[t*3],i1=idx[t*3+1],i2=idx[t*3+2];
            tri(sp[i0],sp[i1],sp[i2],sn[i0],
                vtx[i0].u,vtx[i0].v,vtx[i1].u,vtx[i1].v,vtx[i2].u,vtx[i2].v);}
        double t2=now_ms();
        if(f>0){tskin+=t1-t0;trast+=t2-t1;}
    }
    long filled=0;for(int i=0;i<W*H;i++)if(zbuf[i]<1e29f)filled++;
    double ms=(tskin+trast)/(FR-1);
    printf("三角形 %d / 顶点 %d / 层数 %d / 画布 %dx%d\n",NT,NV,SHELL,W,H);
    printf("  蒙皮+变换 %6.2f ms\n",tskin/(FR-1));
    printf("  光栅+深度 %6.2f ms\n",trast/(FR-1));
    printf("  合计      %6.2f ms   => %.1f fps\n",ms,1000.0/ms);
    printf("  人物占画布 %.0f%% | 每帧测试像素 %.2fM | 写入像素 %.2fM | 平均三角 %.1f px\n",
        100.0*filled/(W*H), px_tested/(double)(FR-1)/1e6,
        px_written/(double)(FR-1)/1e6, px_tested/(double)(FR-1)/NT);
    return 0;
}
