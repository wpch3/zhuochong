/*
 * zimg.h - 图像（RGBA8）与合成
 *
 * 设计原则：
 *   - 所有素材最终统一为“直通 alpha 的 RGBA8 缓冲区”，方便验证与测试；
 *   - 解码用 stb_image（见 src/third_party），编码自己实现（只写 PNG，用 0 压缩块，
 *     目的是让沙箱里也能导出合成结果做验收，不追求体积）；
 *   - 抠图/缩放/仿射合成都要求 alpha 正确，边缘不能出现黑边或彩边。
 */
#ifndef ZIMG_H
#define ZIMG_H

#include "zc.h"

#ifdef __cplusplus
extern "C" {
#endif

typedef struct zimg_s {
    int      w, h;
    uint8_t *px;   /* RGBA8，长度 w*h*4，直通 alpha（非预乘） */
    /* 行裁剪 [clip_y0, clip_y1)：所有写这张图的函数都只许碰这个范围内的行。
       clip_y1 <= clip_y0 表示"不裁剪"（zimg_new 默认就是不裁）。
       这是多线程分块渲染的基础：N 个线程拿同一张 fb 的**浅拷贝头**，
       各自设一段 y，坐标系完全不变（还是整幅画布的坐标），
       于是分块前后的像素可以要求**逐字节相同**——那条闸比任何性能数字都重要。 */
    int      clip_y0, clip_y1;
    /* 半分辨率预滤波副本链（mipmap）。缩小绘制时用它代替"每个屏幕像素只挑一个
       texel"——手部那种 1~2 texel 的指缝线，在 3.6× 缩小时单点采样会整条丢掉
       （T31.4「手指粘连」的真因）。每级宽高减半，最多两级（4× 已经够用）。
       NULL = 还没建；由 zimg_mip_build() 建立，zimg_load() 读完自动建。 */
    struct zimg_s *mip;
} zimg;

/* 做一个共享像素、只负责某几行的"视图"。返回的是栈上可用的值类型，
   不要对它调 zimg_free（它不拥有 px）。 */
zimg  zimg_band(const zimg *im, int y0, int y1);

/* --------------------------------------------------------------- 生命周期 */
zimg *zimg_new(int w, int h);                  /* 全透明 */
zimg *zimg_new_filled(int w, int h, uint8_t r, uint8_t g, uint8_t b, uint8_t a);
void  zimg_free(zimg *im);
zimg *zimg_clone(const zimg *im);
/* 建 mip 链（2×、4×）。幂等；短边不足 4 px 就停在那一级。
   建完之后缩小绘制走预滤波级别，放大/1:1 仍然读原图 —— 那条路一像素都不许变。 */
void  zimg_mip_build(zimg *im);
/* 盒式平均缩小（按 alpha 预乘）。dw/dh 不小于原图时等同于 clone。
   预览按帧走网络，像素数直接等于流畅度——这是唯一的降码率手段。 */
zimg *zimg_downscale(const zimg *im, int dw, int dh);
void  zimg_clear(zimg *im);                    /* 清为全透明 */

/* --------------------------------------------------------------- 读写 */
/* 支持 PNG / JPG（由 stb_image 决定）。失败返回 NULL 并写 err。 */
zimg     *zimg_load(const char *path, zerr *err);
/* 写 PNG（RGBA8，无压缩存储块）。成功返回 0。 */
int       zimg_save_png(const zimg *im, const char *path, zerr *err);
/* 内存里编 PNG（返回 malloc 的缓冲，调用方 free）。帧接口走这条，不碰磁盘。 */
uint8_t  *zimg_encode_png(const zimg *im, size_t *out_len);

/* --------------------------------------------------------------- 处理 */
/* 按键色抠透明（用于 AI 生成图：纯洋红/绿色背景）。
 * tol 为 0..255 的色差容差；despill 非 0 时对边缘像素做去彩边处理。 */
void zimg_key_color(zimg *im, uint8_t r, uint8_t g, uint8_t b, int tol, int despill);
/* 自动从四角推断键色并抠除（要求四角同色）。成功返回 0。 */
int  zimg_key_corners(zimg *im, int tol, int despill, uint8_t *out_key_rgb);

/* 统计不透明像素的包围盒；返回 1 找到，0 为空。 */
int  zimg_alpha_bbox(const zimg *im, int alpha_threshold, int *x, int *y, int *w, int *h);
/* 裁剪出子图（越界部分视为透明）。 */
zimg *zimg_crop(const zimg *im, int x, int y, int w, int h);
/* 双线性缩放（先预乘再采样，避免边缘发黑）。 */
zimg *zimg_resize(const zimg *im, int w, int h);
/* 放到更大的透明画布的 (x,y) 处。 */
zimg *zimg_place(const zimg *im, int cw, int ch, int x, int y);

/* --------------------------------------------------------------- 合成 */
/* 混合模式（≈ Live2D 的 CubismBlendMode）。
   NORMAL   普通 source-over。
   ADD      加算：C = Cd + Cs·As，**不改目标 alpha** —— 高光/发光只在已有画面上提亮，
            不会在透明背景上凭空多出一块。
   MULTIPLY 乘算：C = Cd·(1 − As + As·Cs)，同样不改目标 alpha —— 腮红/阴影压暗底下的皮肤。 */
enum { ZIMG_BLEND_NORMAL = 0, ZIMG_BLEND_ADD = 1, ZIMG_BLEND_MULTIPLY = 2 };
/* 仿射矩阵（行主序）：x' = m0*x + m2*y + m4 ; y' = m1*x + m3*y + m5 */
void zimg_draw(zimg *dst, const zimg *src, const double m[6], double opacity);
/* 遮罩合成：把 src 叠到 dst，但只在 mask 不透明处生效（三张图尺寸必须一致）。
   Live2D 的 clipping mask 等价物——眼球/高光/腮红靠它被眼眶或脸裁住。 */
void zimg_composite_masked(zimg *dst, const zimg *src, const zimg *mask);
/* 同上，但按 blend 指定的混合模式叠加（ZIMG_BLEND_*）。 */
void zimg_composite_masked_blend(zimg *dst, const zimg *src, const zimg *mask, int blend);

/* 只在源图的 (sx0,sy0)-(sx1,sy1) 矩形内绘制（用于分段形变，避免重复混合）。
   源坐标越界会被夹到图像范围内；矩形为空则什么都不画。 */
void zimg_draw_rect(zimg *dst, const zimg *src, const double m[6], double opacity,
                    int sx0, int sy0, int sx1, int sy1);

/* 形变曲线：决定"部件的哪一端固定、哪一端位移最大"。
   约定 u = 1 - y/h（0=图像底边，1=图像顶边），即**底边是根**（站立的人物脚踩地）。
   ZIMG_BEND_ROOT   底边固定，越往上位移越大（u²）——身体侧摆、脖子带动头。
   ZIMG_BEND_SINE   两端固定、中段最大（sin πu）——呼吸、弯腰。
   ZIMG_BEND_LINEAR 底边 0、顶边 1 线性（u）。
   ZIMG_BEND_TIP    顶边固定，越往下位移越大（(1-u)²）——后发、裙摆、尾巴这类"吊在上面"的部件。 */
#define ZIMG_BEND_ROOT   0
#define ZIMG_BEND_SINE   1
#define ZIMG_BEND_LINEAR 2
#define ZIMG_BEND_TIP    3

/* 形变权重 f(t)：t 是部件内的归一化纵坐标（0=顶边，1=底边）。
   给外部（zrig 的"子组跟随父部件形变"）用，保证跟随量与实际绘制完全一致。 */
double zimg_bend_factor(double t, int curve);

/* 平滑形变（推荐）：逐像素反查，源图在目标空间按 bend·f(u) 位移，无分段接缝。
   X 与 Y 各有自己的曲线（例：侧摆用 ROOT，同时呼吸用 SINE，互不干扰）。 */
void zimg_draw_warp(zimg *dst, const zimg *src, const double m[6], double opacity,
                    double bend_x, int curve_x, double bend_y, int curve_y);

/* 分段形变（保留：需要把部件切块处理时使用；平滑形变请用 zimg_draw_warp）：
   把源图按 y 切成 strips 条，每条按曲线 f(t) 施加 (bend_x,bend_y) 偏移。
   curve 取值见上面的 ZIMG_BEND_*（与 zimg_draw_warp 同一套语义）。 */
void zimg_draw_bend(zimg *dst, const zimg *src, const double m[6], double opacity,
                    double bend_x, double bend_y, int curve, int strips);
/* 网格形变（≈ Live2D 的 ワープデフォーマ / 自由变形器）：
   把源图切成 cols×rows 个格子，(cols+1)×(rows+1) 个控制点各自可以挪动。
   offsets 是每个控制点的位移（**源图像素**，行优先 [(r*(cols+1)+c)*2 + 0/1]），
   位移完再过矩阵 m。每个格子拆成两个三角形做仿射映射，所以格子之间不会裂缝。
   位移全为 0 时自动走普通绘制（和 zimg_draw 像素级一致）。 */
void zimg_draw_mesh(zimg *dst, const zimg *src, const double m[6], double opacity,
                    int cols, int rows, const double *offsets);

/* 带混合模式的三个入口（blend 取 ZIMG_BLEND_*；传 NORMAL 时与不带后缀的版本完全一致）。 */
void zimg_draw_blend(zimg *dst, const zimg *src, const double m[6], double opacity, int blend);
void zimg_draw_warp_blend(zimg *dst, const zimg *src, const double m[6], double opacity,
                          double bend_x, int curve_x, double bend_y, int curve_y, int blend);
/* 同上，但带「形变平台」。两条平台线互为镜像，不设就传 0.0 / 1.0：
     bend_tmin —— 源图归一化行 t < bend_tmin 的部分共用 bend_tmin 处的形变量。
                  用于躯干这种「贴图顶边其实是脖子」的部件：颈线以上跟着头走，不再加码。
     bend_tmax —— t > bend_tmax 的部分共用 bend_tmax 处的形变量。
                  用于「跟随件挂在下面」的部件（脚跟腿、手跟前臂）：
                  踝线以下交给鞋件自己画，腿不要再把它越掰越远。 */
void zimg_draw_warp_blend_t(zimg *dst, const zimg *src, const double m[6], double opacity,
                            double bend_x, int curve_x, double bend_y, int curve_y,
                            int blend, double bend_tmin, double bend_tmax);
void zimg_draw_mesh_blend(zimg *dst, const zimg *src, const double m[6], double opacity,
                          int cols, int rows, const double *offsets, int blend);
/* 网格形变与平滑形变叠加（≈ Live2D 变形器嵌套）。两者不是二选一：
   多段摆链的第一段写 bend、第二段写形变器，必须同时生效。 */
void zimg_draw_mesh_bend_blend(zimg *dst, const zimg *src, const double m[6], double opacity,
                               int cols, int rows, const double *offsets,
                               double bend_x, int curve_x, double bend_y, int curve_y,
                               int blend);
/* 同上，但带「形变平台」。必须和 zimg_draw_warp_blend_t 口径一致：
   同一个部件会按形变器 amount 是否为 0 在两条路之间来回切，算出来的形变必须相同。 */
void zimg_draw_mesh_bend_blend_t(zimg *dst, const zimg *src, const double m[6], double opacity,
                                 int cols, int rows, const double *offsets,
                                 double bend_x, int curve_x, double bend_y, int curve_y,
                                 int blend, double bend_tmin, double bend_tmax);

/* 网格 + 平滑形变 + **逐顶点加权刚体**（T66.9c）。
   同一个部件，每个顶点用不同的矩阵：
       p_out = (1 - chain_w[q]) · m0 · p + chain_w[q] · m · p
   用途：一片网格跨两段骨时，上缘只跟腰（w=0）、下缘跟摆（w=1）。
   为什么要两个矩阵而不是一个：链上的刚性变换是**连乘**出来的，
   想只让一部分顶点吃到其中某个节点，就必须再算一份"跳过该节点"的矩阵。
   ★ 数学上这就是 lerp(m0·p, m·p, w) = ((1-w)·m0 + w·m)·p ——
     所以实现只需在算完两个候选坐标之后插值，不涉及旋转的球面插值。
   chain_w == NULL 或 nw <= 0 时等价于 zimg_draw_mesh_bend_blend_t。 */
void zimg_draw_mesh_chainw_blend_t(zimg *dst, const zimg *src,
                                   const double m[6], const double m0[6],
                                   const double *chain_w, int nw,
                                   double opacity, int cols, int rows,
                                   const double *offsets,
                                   double bend_x, int curve_x, double bend_y, int curve_y,
                                   int blend, double bend_tmin, double bend_tmax);

/* 便捷：把 src 缩放到 scale、绕锚点 anchor(0..1) 平移 pos（画布坐标）。 */
void zimg_draw_simple(zimg *dst, const zimg *src, double pos_x, double pos_y,
                      double anchor_x, double anchor_y, double scale,
                      double rotate_deg, double opacity);

/* 命中测试：该点 alpha 是否 > threshold（用于“只让角色挡鼠标”）。 */
int  zimg_hit_test(const zimg *im, int x, int y, int threshold);

/* --------------------------------------------------------------- 调试叠加（铁律七 2.2 / R2） */
/* 在已合成好的帧上直接画调试几何（像素空间，覆盖式，不改 alpha 逻辑）。 */
void zimg_draw_line(zimg *im, int x0, int y0, int x1, int y1,
                    uint8_t r, uint8_t g, uint8_t b, uint8_t a);
void zimg_draw_circle(zimg *im, int cx, int cy, int radius,
                      uint8_t r, uint8_t g, uint8_t b, uint8_t a);
void zimg_draw_rect_outline(zimg *im, int x, int y, int w, int h,
                            uint8_t r, uint8_t g, uint8_t b, uint8_t a);
void zimg_draw_text_px(zimg *im, int x, int y, const char *s,
                       uint8_t r, uint8_t g, uint8_t b, uint8_t a);

/* 便捷：生成旋转+缩放的矩阵 */
void zimg_make_matrix(double m[6], double tx, double ty, double sx, double sy,
                      double rotate_deg, double pivot_x, double pivot_y);
void zimg_matrix_mul(double out[6], const double a[6], const double b[6]);

#ifdef __cplusplus
}
#endif
#endif /* ZIMG_H */
