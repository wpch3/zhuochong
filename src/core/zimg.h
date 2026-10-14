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

typedef struct {
    int      w, h;
    uint8_t *px;   /* RGBA8，长度 w*h*4，直通 alpha（非预乘） */
} zimg;

/* --------------------------------------------------------------- 生命周期 */
zimg *zimg_new(int w, int h);                  /* 全透明 */
zimg *zimg_new_filled(int w, int h, uint8_t r, uint8_t g, uint8_t b, uint8_t a);
void  zimg_free(zimg *im);
zimg *zimg_clone(const zimg *im);
/* 盒式平均缩小（按 alpha 预乘）。dw/dh 不小于原图时等同于 clone。
   预览按帧走网络，像素数直接等于流畅度——这是唯一的降码率手段。 */
zimg *zimg_downscale(const zimg *im, int dw, int dh);
void  zimg_clear(zimg *im);                    /* 清为全透明 */

/* --------------------------------------------------------------- 读写 */
/* 支持 PNG / JPG（由 stb_image 决定）。失败返回 NULL 并写 err。 */
zimg     *zimg_load(const char *path, zerr *err);
/* 写 PNG（RGBA8，无压缩存储块）。成功返回 0。 */
int       zimg_save_png(const zimg *im, const char *path, zerr *err);

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

/* 便捷：把 src 缩放到 scale、绕锚点 anchor(0..1) 平移 pos（画布坐标）。 */
void zimg_draw_simple(zimg *dst, const zimg *src, double pos_x, double pos_y,
                      double anchor_x, double anchor_y, double scale,
                      double rotate_deg, double opacity);

/* 命中测试：该点 alpha 是否 > threshold（用于“只让角色挡鼠标”）。 */
int  zimg_hit_test(const zimg *im, int x, int y, int threshold);

/* 便捷：生成旋转+缩放的矩阵 */
void zimg_make_matrix(double m[6], double tx, double ty, double sx, double sy,
                      double rotate_deg, double pivot_x, double pivot_y);
void zimg_matrix_mul(double out[6], const double a[6], const double b[6]);

#ifdef __cplusplus
}
#endif
#endif /* ZIMG_H */
