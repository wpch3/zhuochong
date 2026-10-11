/* zimg.c - 图像处理与合成实现 */
#include "zimg.h"
#include "zdeflate.h"

#include <math.h>

/* stb_image 只用到 PNG/JPG 读取 */
#define STB_IMAGE_IMPLEMENTATION
#define STBI_ONLY_PNG
#define STBI_ONLY_JPEG
#define STBI_NO_STDIO
#define STBI_NO_HDR
#define STBI_NO_LINEAR
#include "../third_party/stb_image.h"

zimg *zimg_new(int w, int h)
{
    zimg *im;
    if (w <= 0 || h <= 0) return NULL;
    im = (zimg *)z_alloc(sizeof(zimg));
    im->w = w;
    im->h = h;
    im->px = (uint8_t *)z_calloc((size_t)w * h * 4, 1);
    return im;
}

zimg *zimg_new_filled(int w, int h, uint8_t r, uint8_t g, uint8_t b, uint8_t a)
{
    zimg *im = zimg_new(w, h);
    size_t i, n = (size_t)w * h;
    if (!im) return NULL;
    for (i = 0; i < n; ++i) {
        im->px[i * 4 + 0] = r;
        im->px[i * 4 + 1] = g;
        im->px[i * 4 + 2] = b;
        im->px[i * 4 + 3] = a;
    }
    return im;
}

void zimg_free(zimg *im)
{
    if (!im) return;
    free(im->px);
    free(im);
}

zimg *zimg_clone(const zimg *im)
{
    zimg *out;
    if (!im) return NULL;
    out = zimg_new(im->w, im->h);
    memcpy(out->px, im->px, (size_t)im->w * im->h * 4);
    return out;
}

void zimg_clear(zimg *im)
{
    if (!im) return;
    memset(im->px, 0, (size_t)im->w * im->h * 4);
}

/* stb 回调式读取（不依赖 stdio 之外的东西，但我们要自己控制路径/错误） */
static int stb_read_file(const char *path, unsigned char **out, int *out_len)
{
    zerr e;
    size_t n = 0;
    char *buf = z_read_file(path, &n, &e);
    if (!buf) return 0;
    *out = (unsigned char *)buf;
    *out_len = (int)n;
    return 1;
}

zimg *zimg_load(const char *path, zerr *err)
{
    unsigned char *data = NULL;
    int len = 0;
    int w = 0, h = 0, comp = 0;
    stbi_uc *pix;
    zimg *im;
    if (!path) { zerr_set(err, "", 0, 0, "", "路径为空"); return NULL; }
    if (!stb_read_file(path, &data, &len)) {
        zerr_set(err, path, 0, 0, "", "无法读取图像文件");
        return NULL;
    }
    pix = stbi_load_from_memory(data, len, &w, &h, &comp, 4);
    free(data);
    if (!pix) {
        zerr_set(err, path, 0, 0, "", "图像解码失败：%s", stbi_failure_reason());
        return NULL;
    }
    im = zimg_new(w, h);
    memcpy(im->px, pix, (size_t)w * h * 4);
    stbi_image_free(pix);
    return im;
}

/* ====================================================== PNG 写出（自实现） */
static uint32_t crc_table[256];
static int crc_ready = 0;

static void crc_init(void)
{
    uint32_t c;
    int n, k;
    if (crc_ready) return;
    for (n = 0; n < 256; n++) {
        c = (uint32_t)n;
        for (k = 0; k < 8; k++) c = (c & 1) ? (0xEDB88320u ^ (c >> 1)) : (c >> 1);
        crc_table[n] = c;
    }
    crc_ready = 1;
}

static uint32_t crc32_buf(const uint8_t *buf, size_t len)
{
    uint32_t c = 0xFFFFFFFFu;
    size_t n;
    crc_init();
    for (n = 0; n < len; n++) c = crc_table[(c ^ buf[n]) & 0xFF] ^ (c >> 8);
    return c ^ 0xFFFFFFFFu;
}

typedef struct { uint8_t *buf; size_t len, cap; } zbuf;

static void zbuf_put(zbuf *z, const void *d, size_t n)
{
    if (z->len + n > z->cap) {
        while (z->len + n > z->cap) z->cap = z->cap ? z->cap * 2 : 1024;
        z->buf = (uint8_t *)z_realloc(z->buf, z->cap);
    }
    memcpy(z->buf + z->len, d, n);
    z->len += n;
}

static void zbuf_be32(zbuf *z, uint32_t v)
{
    uint8_t b[4] = { (uint8_t)(v >> 24), (uint8_t)(v >> 16), (uint8_t)(v >> 8), (uint8_t)v };
    zbuf_put(z, b, 4);
}

static void png_chunk(zbuf *out, const char *type, const uint8_t *data, size_t len)
{
    uint32_t crc;
    uint8_t *tmp;
    zbuf_be32(out, (uint32_t)len);
    zbuf_put(out, type, 4);
    if (len) zbuf_put(out, data, len);
    tmp = (uint8_t *)z_alloc(4 + len);
    memcpy(tmp, type, 4);
    if (len) memcpy(tmp + 4, data, len);
    crc = crc32_buf(tmp, 4 + len);
    free(tmp);
    zbuf_be32(out, crc);
}

int zimg_save_png(const zimg *im, const char *path, zerr *err)
{
    zbuf raw = {0}, png = {0};
    uint8_t *zdata = NULL;
    size_t zlen = 0;
    int y;
    uint8_t ihdr[13];
    static const uint8_t sig[8] = { 0x89, 'P', 'N', 'G', 0x0D, 0x0A, 0x1A, 0x0A };

    if (!im || !path) { zerr_set(err, path, 0, 0, "", "参数为空"); return -1; }

    /* 逐行自适应滤波（None / Sub / Up），按“绝对值和最小”选择，
     * 让大片透明与渐变区域更容易被 RLE 压缩。 */
    {
        size_t stride = (size_t)im->w * 4;
        uint8_t *cand = (uint8_t *)z_alloc(stride * 3 + 3);
        for (y = 0; y < im->h; ++y) {
            const uint8_t *cur = im->px + (size_t)y * stride;
            const uint8_t *prev = (y > 0) ? im->px + (size_t)(y - 1) * stride : NULL;
            size_t i;
            long score[3] = {0, 0, 0};
            int best = 0;
            uint8_t *f0 = cand;
            uint8_t *f1 = cand + stride;
            uint8_t *f2 = cand + stride * 2;
            for (i = 0; i < stride; ++i) {
                int a = (i >= 4) ? cur[i - 4] : 0;
                int b = prev ? prev[i] : 0;
                f0[i] = cur[i];
                f1[i] = (uint8_t)(cur[i] - a);
                f2[i] = (uint8_t)(cur[i] - b);
            }
            for (i = 0; i < stride; ++i) {
                score[0] += (signed char)f0[i] < 0 ? -(signed char)f0[i] : (signed char)f0[i];
                score[1] += (signed char)f1[i] < 0 ? -(signed char)f1[i] : (signed char)f1[i];
                score[2] += (signed char)f2[i] < 0 ? -(signed char)f2[i] : (signed char)f2[i];
            }
            if (score[1] < score[best]) best = 1;
            if (score[2] < score[best]) best = 2;
            {
                uint8_t ft = (uint8_t)best;
                const uint8_t *src = (best == 0) ? f0 : (best == 1 ? f1 : f2);
                zbuf_put(&raw, &ft, 1);
                zbuf_put(&raw, src, stride);
            }
        }
        free(cand);
    }

    zlen = zlib_compress_rle(raw.buf, raw.len, &zdata);
    free(raw.buf);
    if (!zdata || zlen == 0) {
        zerr_set(err, path, 0, 0, "", "压缩失败");
        free(zdata);
        return -1;
    }

    zbuf_put(&png, sig, 8);
    ihdr[0] = (uint8_t)((unsigned)im->w >> 24); ihdr[1] = (uint8_t)((unsigned)im->w >> 16);
    ihdr[2] = (uint8_t)((unsigned)im->w >> 8);  ihdr[3] = (uint8_t)im->w;
    ihdr[4] = (uint8_t)((unsigned)im->h >> 24); ihdr[5] = (uint8_t)((unsigned)im->h >> 16);
    ihdr[6] = (uint8_t)((unsigned)im->h >> 8);  ihdr[7] = (uint8_t)im->h;
    ihdr[8] = 8;   /* 位深 */
    ihdr[9] = 6;   /* RGBA */
    ihdr[10] = 0; ihdr[11] = 0; ihdr[12] = 0;
    png_chunk(&png, "IHDR", ihdr, 13);
    png_chunk(&png, "IDAT", zdata, zlen);
    png_chunk(&png, "IEND", NULL, 0);
    free(zdata);

    {
        int rc = z_write_file(path, png.buf, png.len, err);
        free(png.buf);
        return rc;
    }
}

/* ============================================================ 抠色/处理 */
void zimg_key_color(zimg *im, uint8_t r, uint8_t g, uint8_t b, int tol, int despill)
{
    size_t i, n;
    if (!im) return;
    n = (size_t)im->w * im->h;
    for (i = 0; i < n; ++i) {
        uint8_t *p = im->px + i * 4;
        int dr = (int)p[0] - (int)r;
        int dg = (int)p[1] - (int)g;
        int db = (int)p[2] - (int)b;
        int dist = (int)sqrt((double)(dr * dr + dg * dg + db * db));
        if (dist <= tol) {
            p[3] = 0;
            if (despill) { p[0] = p[1] = p[2] = 0; }
        } else if (despill && dist <= tol * 2 && p[3] > 0) {
            /* 半透明边缘：把键色方向的分量压掉，避免洋红彩边 */
            int over = tol * 2 - dist;
            double k = (double)over / (double)(tol * 2);
            if (r > g && r > b) {           /* 洋红类 */
                int lim = (int)((p[0] + p[1] + p[2]) / 3.0);
                p[0] = (uint8_t)ZC_CLAMP((double)p[0] * (1.0 - k) + lim * k, 0, 255);
            } else if (g > r && g > b) {    /* 绿幕 */
                int lim = (int)((p[0] + p[2]) / 2.0);
                p[1] = (uint8_t)ZC_CLAMP((double)p[1] * (1.0 - k) + lim * k, 0, 255);
            }
        }
    }
}

int zimg_key_corners(zimg *im, int tol, int despill, uint8_t *out_key_rgb)
{
    int x, y, cx[4], cy[4], i;
    int r = 0, g = 0, b = 0;
    if (!im) return -1;
    cx[0] = 0; cy[0] = 0;
    cx[1] = im->w - 1; cy[1] = 0;
    cx[2] = 0; cy[2] = im->h - 1;
    cx[3] = im->w - 1; cy[3] = im->h - 1;
    for (i = 0; i < 4; ++i) {
        uint8_t *p = im->px + ((size_t)cy[i] * im->w + cx[i]) * 4;
        r += p[0]; g += p[1]; b += p[2];
    }
    r /= 4; g /= 4; b /= 4;
    /* 四角必须彼此接近，否则认为不是纯色背景 */
    for (i = 0; i < 4; ++i) {
        uint8_t *p = im->px + ((size_t)cy[i] * im->w + cx[i]) * 4;
        if (abs((int)p[0] - r) + abs((int)p[1] - g) + abs((int)p[2] - b) > tol * 3)
            return -2;
    }
    if (out_key_rgb) { out_key_rgb[0] = (uint8_t)r; out_key_rgb[1] = (uint8_t)g; out_key_rgb[2] = (uint8_t)b; }
    zimg_key_color(im, (uint8_t)r, (uint8_t)g, (uint8_t)b, tol, despill);
    (void)x; (void)y;
    return 0;
}

int zimg_alpha_bbox(const zimg *im, int alpha_threshold, int *x, int *y, int *w, int *h)
{
    int minx = im ? im->w : 0, miny = im ? im->h : 0, maxx = -1, maxy = -1;
    int px, py;
    if (!im) return 0;
    for (py = 0; py < im->h; ++py) {
        for (px = 0; px < im->w; ++px) {
            if (im->px[((size_t)py * im->w + px) * 4 + 3] > alpha_threshold) {
                if (px < minx) minx = px;
                if (px > maxx) maxx = px;
                if (py < miny) miny = py;
                if (py > maxy) maxy = py;
            }
        }
    }
    if (maxx < 0) return 0;
    if (x) *x = minx;
    if (y) *y = miny;
    if (w) *w = maxx - minx + 1;
    if (h) *h = maxy - miny + 1;
    return 1;
}

zimg *zimg_crop(const zimg *im, int x, int y, int w, int h)
{
    zimg *out;
    int px, py;
    if (!im || w <= 0 || h <= 0) return NULL;
    out = zimg_new(w, h);
    for (py = 0; py < h; ++py) {
        int sy = y + py;
        if (sy < 0 || sy >= im->h) continue;
        for (px = 0; px < w; ++px) {
            int sx = x + px;
            if (sx < 0 || sx >= im->w) continue;
            memcpy(out->px + ((size_t)py * w + px) * 4, im->px + ((size_t)sy * im->w + sx) * 4, 4);
        }
    }
    return out;
}

/* 预乘 alpha 的双线性采样。
 * 输出约定（必须统一，否则合成会饱和成白色）：
 *   out[0..2] = 颜色 × alpha，颜色归一化到 0..1
 *   out[3]    = alpha，0..1 */
static void sample_premul(const zimg *im, double fx, double fy, double out[4])
{
    int x0 = (int)floor(fx), y0 = (int)floor(fy);
    double tx = fx - x0, ty = fy - y0;
    int i;
    double acc[4] = {0, 0, 0, 0};
    for (i = 0; i < 4; ++i) {
        int dx = (i & 1), dy = (i >> 1);
        int sx = ZC_CLAMP(x0 + dx, 0, im->w - 1);
        int sy = ZC_CLAMP(y0 + dy, 0, im->h - 1);
        const uint8_t *p = im->px + ((size_t)sy * im->w + sx) * 4;
        double a = p[3] / 255.0;
        double wgt = (dx ? tx : 1.0 - tx) * (dy ? ty : 1.0 - ty);
        acc[0] += (p[0] / 255.0) * a * wgt;
        acc[1] += (p[1] / 255.0) * a * wgt;
        acc[2] += (p[2] / 255.0) * a * wgt;
        acc[3] += a * wgt;
    }
    out[0] = acc[0]; out[1] = acc[1]; out[2] = acc[2]; out[3] = acc[3];
}

zimg *zimg_resize(const zimg *im, int w, int h)
{
    zimg *out;
    int px, py;
    if (!im || w <= 0 || h <= 0) return NULL;
    out = zimg_new(w, h);
    for (py = 0; py < h; ++py) {
        double fy = (h > 1) ? (double)py * (im->h - 1) / (h - 1) : 0.0;
        for (px = 0; px < w; ++px) {
            double fx = (w > 1) ? (double)px * (im->w - 1) / (w - 1) : 0.0;
            double s[4];
            uint8_t *q = out->px + ((size_t)py * w + px) * 4;
            sample_premul(im, fx, fy, s);
            if (s[3] > 1e-6) {
                q[0] = (uint8_t)ZC_CLAMP(s[0] / s[3] * 255.0, 0, 255);
                q[1] = (uint8_t)ZC_CLAMP(s[1] / s[3] * 255.0, 0, 255);
                q[2] = (uint8_t)ZC_CLAMP(s[2] / s[3] * 255.0, 0, 255);
                q[3] = (uint8_t)ZC_CLAMP(s[3] * 255.0, 0, 255);
            } else {
                q[0] = q[1] = q[2] = 0; q[3] = 0;
            }
        }
    }
    return out;
}

zimg *zimg_place(const zimg *im, int cw, int ch, int x, int y)
{
    zimg *out;
    int px, py;
    if (!im || cw <= 0 || ch <= 0) return NULL;
    out = zimg_new(cw, ch);
    for (py = 0; py < im->h; ++py) {
        int dy = y + py;
        if (dy < 0 || dy >= ch) continue;
        for (px = 0; px < im->w; ++px) {
            int dx = x + px;
            if (dx < 0 || dx >= cw) continue;
            memcpy(out->px + ((size_t)dy * cw + dx) * 4, im->px + ((size_t)py * im->w + px) * 4, 4);
        }
    }
    return out;
}

/* ================================================================ 合成 */
void zimg_matrix_mul(double out[6], const double a[6], const double b[6])
{
    /* out = a ∘ b（先 b 后 a） */
    double r[6];
    r[0] = a[0] * b[0] + a[2] * b[1];
    r[1] = a[1] * b[0] + a[3] * b[1];
    r[2] = a[0] * b[2] + a[2] * b[3];
    r[3] = a[1] * b[2] + a[3] * b[3];
    r[4] = a[0] * b[4] + a[2] * b[5] + a[4];
    r[5] = a[1] * b[4] + a[3] * b[5] + a[5];
    memcpy(out, r, sizeof(r));
}

void zimg_make_matrix(double m[6], double tx, double ty, double sx, double sy,
                      double rotate_deg, double pivot_x, double pivot_y)
{
    double rad = rotate_deg * 3.14159265358979323846 / 180.0;
    double c = cos(rad), s = sin(rad);
    /* 旋转 + 缩放（绕 pivot），再平移 */
    m[0] = c * sx;  m[1] = s * sx;
    m[2] = -s * sy; m[3] = c * sy;
    m[4] = tx - (m[0] * pivot_x + m[2] * pivot_y);
    m[5] = ty - (m[1] * pivot_x + m[3] * pivot_y);
}

void zimg_draw(zimg *dst, const zimg *src, const double m[6], double opacity)
{
    zimg_draw_rect(dst, src, m, opacity, 0, 0, src ? src->w : 0, src ? src->h : 0);
}

/* 内部实现：bend 参数为 0 时等价于 zimg_draw */
static void draw_impl(zimg *dst, const zimg *src, const double m[6], double opacity,
                      int sx0, int sy0, int sx1, int sy1,
                      double bend_x, int curve_x, double bend_y, int curve_y);

void zimg_draw_rect(zimg *dst, const zimg *src, const double m[6], double opacity,
                    int sx0, int sy0, int sx1, int sy1)
{
    draw_impl(dst, src, m, opacity, sx0, sy0, sx1, sy1,
              0.0, ZIMG_BEND_LINEAR, 0.0, ZIMG_BEND_LINEAR);
}

void zimg_draw_warp(zimg *dst, const zimg *src, const double m[6], double opacity,
                    double bend_x, int curve_x, double bend_y, int curve_y)
{
    if (!src) return;
    draw_impl(dst, src, m, opacity, 0, 0, src->w, src->h, bend_x, curve_x, bend_y, curve_y);
}

/* 形变权重。入参 t 是源图内的归一化纵坐标（0=顶边，1=底边）；
   内部换算成 u = 1 - t（0=底边，1=顶边），因为"根"默认在底边（人物站在地上）。 */
double zimg_bend_factor(double t, int curve)
{
    double u;
    if (t < 0.0) t = 0.0;
    if (t > 1.0) t = 1.0;
    u = 1.0 - t;
    switch (curve) {
    case ZIMG_BEND_SINE:   return sin(u * 3.14159265358979);  /* 两端固定、中段最大 */
    case ZIMG_BEND_LINEAR: return u;                          /* 底 0 顶 1 */
    case ZIMG_BEND_TIP:    return t * t;                      /* 顶边固定，底端最大 */
    default:               return u * u;                      /* ROOT：底边固定，顶端最大 */
    }
}

static void draw_impl(zimg *dst, const zimg *src, const double m[6], double opacity,
                      int sx0, int sy0, int sx1, int sy1,
                      double bend_x, int curve_x, double bend_y, int curve_y)
{
    double det, inv[6];
    int x0, y0, x1, y1, px, py;
    if (!dst || !src) return;
    det = m[0] * m[3] - m[1] * m[2];
    if (fabs(det) < 1e-12) return;
    inv[0] =  m[3] / det;  inv[1] = -m[1] / det;
    inv[2] = -m[2] / det;  inv[3] =  m[0] / det;
    inv[4] = (m[2] * m[5] - m[3] * m[4]) / det;
    inv[5] = (m[1] * m[4] - m[0] * m[5]) / det;

    /* 目标包围盒：把源四角变换后取包围盒 */
    {
        double cx[4] = { 0, (double)src->w, 0, (double)src->w };
        double cy[4] = { 0, 0, (double)src->h, (double)src->h };
        double minx = 1e18, miny = 1e18, maxx = -1e18, maxy = -1e18;
        int i;
        for (i = 0; i < 4; ++i) {
            double tx = m[0] * cx[i] + m[2] * cy[i] + m[4];
            double ty = m[1] * cx[i] + m[3] * cy[i] + m[5];
            if (tx < minx) minx = tx;
            if (ty < miny) miny = ty;
            if (tx > maxx) maxx = tx;
            if (ty > maxy) maxy = ty;
        }
        x0 = (int)floor(minx); y0 = (int)floor(miny);
        x1 = (int)ceil(maxx);  y1 = (int)ceil(maxy);
        /* 形变会把像素推出原包围盒：按最大位移把扫描范围撑开，否则弯曲的那一端会被裁掉。
           （单测"root 曲线顶端位移大"就是被这个裁没的） */
        if (bend_x != 0.0 || bend_y != 0.0) {
            int ex = (int)ceil(fabs(bend_x)) + 1, ey = (int)ceil(fabs(bend_y)) + 1;
            x0 -= ex; x1 += ex; y0 -= ey; y1 += ey;
        }
    }
    x0 = ZC_CLAMP(x0, 0, dst->w); x1 = ZC_CLAMP(x1, 0, dst->w);
    y0 = ZC_CLAMP(y0, 0, dst->h); y1 = ZC_CLAMP(y1, 0, dst->h);

    /* 源矩形约束（半像素容差，保证相邻分段不重叠也不漏缝） */
    if (sx0 < 0) sx0 = 0;
    if (sy0 < 0) sy0 = 0;
    if (sx1 > src->w) sx1 = src->w;
    if (sy1 > src->h) sy1 = src->h;
    if (sx1 <= sx0 || sy1 <= sy0) return;

    for (py = y0; py < y1; ++py) {
        for (px = x0; px < x1; ++px) {
            double fx, fy;
            if (bend_x != 0.0 || bend_y != 0.0) {
                /* 先估一次源位置求形变权重 t，再把目标坐标按位移反查（逐像素，无接缝） */
                double ay = inv[1] * (px + 0.5) + inv[3] * (py + 0.5) + inv[5];
                double t  = ay / (double)src->h;
                /* X 与 Y 分别用各自的曲线：侧摆（根部固定）与呼吸（中段最大）可以同时存在 */
                double dx = bend_x * zimg_bend_factor(t, curve_x);
                double dy = bend_y * zimg_bend_factor(t, curve_y);
                fx = inv[0] * (px + 0.5 - dx) + inv[2] * (py + 0.5 - dy) + inv[4];
                fy = inv[1] * (px + 0.5 - dx) + inv[3] * (py + 0.5 - dy) + inv[5];
            } else {
                fx = inv[0] * (px + 0.5) + inv[2] * (py + 0.5) + inv[4];
                fy = inv[1] * (px + 0.5) + inv[3] * (py + 0.5) + inv[5];
            }
            double s[4];
            uint8_t *q;
            double sa, da, oa;
            if (fx < -0.5 || fy < -0.5 || fx > src->w - 0.5 || fy > src->h - 0.5) continue;
            if (fx < sx0 - 0.5 || fx > sx1 - 0.5 || fy < sy0 - 0.5 || fy > sy1 - 0.5) continue;
            sample_premul(src, fx - 0.5, fy - 0.5, s);
            sa = s[3] * opacity;
            if (sa <= 0.0001) continue;
            q = dst->px + ((size_t)py * dst->w + px) * 4;
            da = q[3] / 255.0;
            oa = sa + da * (1.0 - sa);
            {
                double sr = (sa > 1e-9) ? s[0] / s[3] : 0.0;
                double sg = (sa > 1e-9) ? s[1] / s[3] : 0.0;
                double sb = (sa > 1e-9) ? s[2] / s[3] : 0.0;
                double dr = q[0] / 255.0, dg = q[1] / 255.0, db = q[2] / 255.0;
                double rr = (sr * sa + dr * da * (1.0 - sa)) / (oa > 1e-9 ? oa : 1.0);
                double rg = (sg * sa + dg * da * (1.0 - sa)) / (oa > 1e-9 ? oa : 1.0);
                double rb = (sb * sa + db * da * (1.0 - sa)) / (oa > 1e-9 ? oa : 1.0);
                q[0] = (uint8_t)ZC_CLAMP(rr * 255.0, 0, 255);
                q[1] = (uint8_t)ZC_CLAMP(rg * 255.0, 0, 255);
                q[2] = (uint8_t)ZC_CLAMP(rb * 255.0, 0, 255);
                q[3] = (uint8_t)ZC_CLAMP(oa * 255.0, 0, 255);
            }
        }
    }
}

void zimg_draw_simple(zimg *dst, const zimg *src, double pos_x, double pos_y,
                      double anchor_x, double anchor_y, double scale,
                      double rotate_deg, double opacity)
{
    double m[6];
    double px = src->w * anchor_x;
    double py = src->h * anchor_y;
    zimg_make_matrix(m, pos_x, pos_y, scale, scale, rotate_deg, px, py);
    zimg_draw(dst, src, m, opacity);
}

int zimg_hit_test(const zimg *im, int x, int y, int threshold)
{
    if (!im || x < 0 || y < 0 || x >= im->w || y >= im->h) return 0;
    return im->px[((size_t)y * im->w + x) * 4 + 3] > threshold;
}

void zimg_draw_bend(zimg *dst, const zimg *src, const double m[6], double opacity,
                    double bend_x, double bend_y, int curve, int strips)
{
    int i;
    if (!dst || !src) return;
    if (fabs(bend_x) < 0.05 && fabs(bend_y) < 0.05) {
        zimg_draw(dst, src, m, opacity);
        return;
    }
    if (strips < 1) strips = 1;
    if (strips > 64) strips = 64;
    for (i = 0; i < strips; ++i) {
        int y0 = (int)((long)src->h * i / strips);
        int y1 = (int)((long)src->h * (i + 1) / strips);
        double t, f, mb[6];
        if (y1 <= y0) continue;
        t = (double)(y0 + y1) * 0.5 / (double)src->h;
        f = zimg_bend_factor(t, curve);   /* 与平滑形变共用同一套曲线语义 */
        memcpy(mb, m, sizeof(mb));
        mb[4] += bend_x * f;
        mb[5] += bend_y * f;
        zimg_draw_rect(dst, src, mb, opacity, 0, y0, src->w, y1);
    }
}
