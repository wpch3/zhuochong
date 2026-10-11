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
/* 仿射矩阵（行主序）：x' = m0*x + m2*y + m4 ; y' = m1*x + m3*y + m5 */
void zimg_draw(zimg *dst, const zimg *src, const double m[6], double opacity);

/* 只在源图的 (sx0,sy0)-(sx1,sy1) 矩形内绘制（用于分段形变，避免重复混合）。
   源坐标越界会被夹到图像范围内；矩形为空则什么都不画。 */
void zimg_draw_rect(zimg *dst, const zimg *src, const double m[6], double opacity,
                    int sx0, int sy0, int sx1, int sy1);

/* 平滑形变（推荐）：逐像素反查，源图在目标空间按 bend·f(t) 位移，无分段接缝。
   curve 同下（0=根部固定 1=中间最大 2=线性）。 */
void zimg_draw_warp(zimg *dst, const zimg *src, const double m[6], double opacity,
                    double bend_x, double bend_y, int curve);

/* 分段形变（保留：需要把部件切块处理时使用；平滑形变请用 zimg_draw_warp）：
   把源图按 y 切成 strips 条，每条按曲线 f(t) 施加 (bend_x,bend_y) 偏移。
   curve: 0=根部固定（t²，头发/裙摆摆动）1=中间最大（sin，弯腰/呼吸）2=线性。
   t 为 0（顶部）到 1（底部）的归一化位置。 */
void zimg_draw_bend(zimg *dst, const zimg *src, const double m[6], double opacity,
                    double bend_x, double bend_y, int curve, int strips);
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
