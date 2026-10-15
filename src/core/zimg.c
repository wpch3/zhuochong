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

/* 取这张图当前允许写的行范围。clip_y1<=clip_y0 = 不裁剪 = 整幅。
   所有会写 dst 的循环都必须先过这一关，否则分块渲染时线程会互相踩。 */
static void zimg_clip_range(const zimg *im, int *y0, int *y1)
{
    if (im->clip_y1 > im->clip_y0) {
        *y0 = im->clip_y0 < 0 ? 0 : im->clip_y0;
        *y1 = im->clip_y1 > im->h ? im->h : im->clip_y1;
    } else {
        *y0 = 0;
        *y1 = im->h;
    }
}


zimg *zimg_new(int w, int h)
{
    zimg *im;
    if (w <= 0 || h <= 0) return NULL;
    im = (zimg *)z_alloc(sizeof(zimg));
    im->w = w;
    im->h = h;
    /* z_alloc 是裸 malloc，不清零 —— clip 字段必须显式初始化成"不裁剪"，
       否则新图会带着垃圾裁剪范围，画出来少半截还查不出原因。 */
    im->clip_y0 = 0;
    im->clip_y1 = 0;
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

/* 一个像素的混合：q 是目标像素，(sr,sg,sb) 是**非预乘**源颜色 0..1，sa 是源 alpha 0..1。
   加算/乘算都遵循 Live2D 的约定——只改颜色，不改目标 alpha。 */
static void blend_px(uint8_t *q, double sr, double sg, double sb, double sa, int blend)
{
    double da = q[3] / 255.0;
    double dr = q[0] / 255.0, dg = q[1] / 255.0, db = q[2] / 255.0;
    double rr, rg, rb, oa;
    /* 加算/乘算都只改颜色不改 alpha：目标是全透明的地方本来就没有东西可以提亮或压暗，
       直接跳过。否则会留下一堆 alpha=0 但 RGB 不为 0 的"鬼像素"。 */
    if (blend != ZIMG_BLEND_NORMAL && da <= 0.0) return;
    if (blend == ZIMG_BLEND_ADD) {
        rr = dr + sr * sa; rg = dg + sg * sa; rb = db + sb * sa;
        oa = da;
    } else if (blend == ZIMG_BLEND_MULTIPLY) {
        rr = dr * (1.0 - sa + sa * sr);
        rg = dg * (1.0 - sa + sa * sg);
        rb = db * (1.0 - sa + sa * sb);
        oa = da;
    } else {
        oa = sa + da * (1.0 - sa);
        rr = (sr * sa + dr * da * (1.0 - sa)) / (oa > 1e-9 ? oa : 1.0);
        rg = (sg * sa + dg * da * (1.0 - sa)) / (oa > 1e-9 ? oa : 1.0);
        rb = (sb * sa + db * da * (1.0 - sa)) / (oa > 1e-9 ? oa : 1.0);
    }
    /* 四舍五入而不是截断：截断会让每一层合成都掉半个色阶，叠十几层就肉眼可见地发暗 */
    q[0] = (uint8_t)ZC_CLAMP(rr * 255.0 + 0.5, 0, 255);
    q[1] = (uint8_t)ZC_CLAMP(rg * 255.0 + 0.5, 0, 255);
    q[2] = (uint8_t)ZC_CLAMP(rb * 255.0 + 0.5, 0, 255);
    q[3] = (uint8_t)ZC_CLAMP(oa * 255.0 + 0.5, 0, 255);
}

void zimg_composite_masked(zimg *dst, const zimg *src, const zimg *mask)
{
    zimg_composite_masked_blend(dst, src, mask, ZIMG_BLEND_NORMAL);
}

void zimg_composite_masked_blend(zimg *dst, const zimg *src, const zimg *mask, int blend)
{
    /* 把 src 合成到 dst，但只在 mask 不透明的地方生效（alpha 相乘）。
       这就是 Live2D 的 clipping mask：眼球画成完整的圆，靠眼眶形状裁出可见部分，
       眼球移动时边缘始终贴着眼眶，不会滑出去。 */
    int x, y, y_from, y_to;
    if (!dst || !src) return;
    if (dst->w != src->w || dst->h != src->h) return;
    if (mask && (mask->w != dst->w || mask->h != dst->h)) return;
    {
        int cy0, cy1;
        zimg_clip_range(dst, &cy0, &cy1);
        y_from = cy0; y_to = cy1;
    }
    for (y = y_from; y < y_to; ++y) {
        uint8_t *dp = dst->px + (size_t)y * (size_t)dst->w * 4;
        const uint8_t *sp = src->px + (size_t)y * (size_t)src->w * 4;
        const uint8_t *mp = mask ? mask->px + (size_t)y * (size_t)mask->w * 4 : NULL;
        for (x = 0; x < dst->w; ++x, dp += 4, sp += 4) {
            unsigned sa = sp[3];
            unsigned ma = mp ? mp[x * 4 + 3] : 255u;
            unsigned a;
            if (sa == 0 || ma == 0) continue;
            a = (sa * ma + 127u) / 255u;
            if (a == 0) continue;
            blend_px(dp, sp[0] / 255.0, sp[1] / 255.0, sp[2] / 255.0, a / 255.0, blend);
        }
    }
}

zimg *zimg_downscale(const zimg *im, int dw, int dh)
{
    /* 盒式平均缩小。**必须按 alpha 预乘再平均**：直接平均 RGB 会把透明像素里
       残留的颜色也算进去，边缘会发白发灰（抠图那边踩过同一个坑）。 */
    zimg *out;
    int x, y;
    if (!im || dw <= 0 || dh <= 0) return NULL;
    if (dw >= im->w || dh >= im->h) return zimg_clone(im);
    out = zimg_new(dw, dh);
    if (!out) return NULL;
    for (y = 0; y < dh; ++y) {
        int sy0 = (int)((long long)y * im->h / dh);
        int sy1 = (int)((long long)(y + 1) * im->h / dh);
        if (sy1 <= sy0) sy1 = sy0 + 1;
        for (x = 0; x < dw; ++x) {
            int sx0 = (int)((long long)x * im->w / dw);
            int sx1 = (int)((long long)(x + 1) * im->w / dw);
            unsigned long ar = 0, ag = 0, ab = 0, aa = 0;
            int cnt = 0, sx, sy;
            if (sx1 <= sx0) sx1 = sx0 + 1;
            for (sy = sy0; sy < sy1 && sy < im->h; ++sy) {
                const uint8_t *row = im->px + (size_t)sy * (size_t)im->w * 4;
                for (sx = sx0; sx < sx1 && sx < im->w; ++sx) {
                    const uint8_t *p = row + (size_t)sx * 4;
                    unsigned a = p[3];
                    ar += (unsigned long)p[0] * a;
                    ag += (unsigned long)p[1] * a;
                    ab += (unsigned long)p[2] * a;
                    aa += a;
                    cnt++;
                }
            }
            {
                uint8_t *d = out->px + ((size_t)y * (size_t)dw + (size_t)x) * 4;
                if (cnt > 0 && aa > 0) {
                    d[0] = (uint8_t)(ar / aa);
                    d[1] = (uint8_t)(ag / aa);
                    d[2] = (uint8_t)(ab / aa);
                    d[3] = (uint8_t)(aa / (unsigned long)cnt);
                } else {
                    d[0] = d[1] = d[2] = d[3] = 0;
                }
            }
        }
    }
    return out;
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
    int y0, y1;
    if (!im) return;
    zimg_clip_range(im, &y0, &y1);
    if (y1 <= y0) return;
    memset(im->px + (size_t)y0 * im->w * 4, 0, (size_t)(y1 - y0) * im->w * 4);
}

zimg zimg_band(const zimg *im, int y0, int y1)
{
    zimg v;
    memset(&v, 0, sizeof(v));
    if (!im) return v;
    v = *im;
    if (y0 < 0) y0 = 0;
    if (y1 > im->h) y1 = im->h;
    v.clip_y0 = y0;
    v.clip_y1 = y1;
    return v;
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

/* ---------------------------------------------------------- PNG 并行编码

   一帧 848x1360 的编码耗时拆开看（2 核沙箱实测）：滤波 17ms + deflate 72ms。
   两段都能按**行带**切开并行：
     - 滤波：第 y 行的 Up 滤波要读第 y-1 行，但那只是**读源图**，跨带读没有竞争；
       每条带把结果写进 raw 缓冲里自己那一段，互不重叠。
     - deflate：每条带压成一个 BFINAL=0 的段（末尾补空 stored 块对齐到字节），
       最后一段 BFINAL=1，按字节拼起来就是合法的 zlib 流（pigz 就是这么干的）。
   代价是每段开头 LZ77 窗口是空的，压缩率略降；实测 4 段 12.7% → 13.0%，可以接受。 */

#define ZIMG_PNG_MAX_BANDS 8

typedef struct {
    const zimg *im;
    uint8_t    *raw;          /* 滤波后的 (1+stride)*h 字节，各带写自己那段 */
    size_t      stride;
    int         y0[ZIMG_PNG_MAX_BANDS], y1[ZIMG_PNG_MAX_BANDS];
    size_t      roff[ZIMG_PNG_MAX_BANDS], rlen[ZIMG_PNG_MAX_BANDS];
    uint8_t    *part[ZIMG_PNG_MAX_BANDS];
    size_t      plen[ZIMG_PNG_MAX_BANDS];
    int         nb;
} png_job;

static void png_band(void *vctx, int bi)
{
    png_job *j = (png_job *)vctx;
    const zimg *im = j->im;
    size_t stride = j->stride;
    uint8_t *cand = (uint8_t *)z_alloc(stride * 3 + 3);
    uint8_t *o = j->raw + j->roff[bi];
    int y;
    for (y = j->y0[bi]; y < j->y1[bi]; ++y) {
        const uint8_t *cur  = im->px + (size_t)y * stride;
        /* 第 0 行没有上一行；其它行（含带的第一行）正常读上一行——只读不写，安全 */
        const uint8_t *prev = (y > 0) ? im->px + (size_t)(y - 1) * stride : NULL;
        uint8_t *f0 = cand, *f1 = cand + stride, *f2 = cand + stride * 2;
        long score[3];
        size_t i;
        int best = 0;
        score[0] = score[1] = score[2] = 0;
        for (i = 0; i < stride; ++i) {
            int a = (i >= 4) ? cur[i - 4] : 0;
            int b = prev ? prev[i] : 0;
            f0[i] = cur[i];
            f1[i] = (uint8_t)(cur[i] - a);
            f2[i] = (uint8_t)(cur[i] - b);
            score[0] += (signed char)f0[i] < 0 ? -(signed char)f0[i] : (signed char)f0[i];
            score[1] += (signed char)f1[i] < 0 ? -(signed char)f1[i] : (signed char)f1[i];
            score[2] += (signed char)f2[i] < 0 ? -(signed char)f2[i] : (signed char)f2[i];
        }
        if (score[1] < score[best]) best = 1;
        if (score[2] < score[best]) best = 2;
        *o++ = (uint8_t)best;
        memcpy(o, (best == 0) ? f0 : (best == 1 ? f1 : f2), stride);
        o += stride;
    }
    free(cand);
    j->plen[bi] = zdeflate_lz77_part(j->raw + j->roff[bi], j->rlen[bi],
                                     &j->part[bi], (bi == j->nb - 1) ? 1 : 0);
}

/* 把 im 编成 PNG 放进内存，返回 malloc 出来的缓冲（调用方 free），失败返回 NULL。
   原来只有 zimg_save_png，预览服务器为了拿到字节流只能"写 /tmp 再读回来再 remove"——
   每帧三次文件系统往返。帧接口是热路径，这条必须走内存。 */
uint8_t *zimg_encode_png(const zimg *im, size_t *out_len)
{
    png_job j;
    zbuf png;
    uint8_t *zdata = NULL, *result = NULL;
    size_t zlen = 0, rawlen;
    uint8_t ihdr[13];
    static const uint8_t sig[8] = { 0x89, 'P', 'N', 'G', 0x0D, 0x0A, 0x1A, 0x0A };
    int k, nb, ok = 1;

    if (out_len) *out_len = 0;
    if (!im || im->w <= 0 || im->h <= 0) return NULL;

    memset(&j, 0, sizeof(j));
    memset(&png, 0, sizeof(png));
    j.im = im;
    j.stride = (size_t)im->w * 4;
    rawlen = (j.stride + 1) * (size_t)im->h;
    j.raw = (uint8_t *)z_alloc(rawlen);

    nb = z_hw_threads();
    if (nb > ZIMG_PNG_MAX_BANDS) nb = ZIMG_PNG_MAX_BANDS;
    /* 小图分段不划算（线程开销 + 压缩率损失），而且段太碎 adler 都算不回本 */
    if (rawlen < 256 * 1024) nb = 1;
    if (nb > im->h) nb = im->h;
    if (nb < 1) nb = 1;
    j.nb = nb;
    for (k = 0; k < nb; ++k) {
        j.y0[k] = (int)((long)im->h * k / nb);
        j.y1[k] = (int)((long)im->h * (k + 1) / nb);
        j.roff[k] = (j.stride + 1) * (size_t)j.y0[k];
        j.rlen[k] = (j.stride + 1) * (size_t)(j.y1[k] - j.y0[k]);
    }

    z_parallel_for(nb, png_band, &j);

    for (k = 0; k < nb; ++k) if (!j.part[k] || j.plen[k] == 0) ok = 0;
    if (ok) {
        zlen = zlib_wrap_parts((const uint8_t *const *)j.part, j.plen, nb,
                               j.raw, rawlen, &zdata);
    }
    if (!ok || !zdata || zlen == 0) {
        /* 任何一段压缩失败就整体退回单段老路，宁慢勿错 */
        free(zdata); zdata = NULL;
        zlen = zlib_compress_rle(j.raw, rawlen, &zdata);
    }
    for (k = 0; k < nb; ++k) free(j.part[k]);
    free(j.raw);
    if (!zdata || zlen == 0) { free(zdata); return NULL; }

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

    result = png.buf;
    if (out_len) *out_len = png.len;
    return result;
}

int zimg_save_png(const zimg *im, const char *path, zerr *err)
{
    size_t len = 0;
    uint8_t *png;
    int rc;
    if (!im || !path) { zerr_set(err, path, 0, 0, "", "参数为空"); return -1; }
    png = zimg_encode_png(im, &len);
    if (!png) { zerr_set(err, path, 0, 0, "", "压缩失败"); return -1; }
    rc = z_write_file(path, png, len, err);
    free(png);
    return rc;
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
                      double bend_x, int curve_x, double bend_y, int curve_y,
                      double bend_tmin, double bend_tmax, int blend);

void zimg_draw_rect(zimg *dst, const zimg *src, const double m[6], double opacity,
                    int sx0, int sy0, int sx1, int sy1)
{
    draw_impl(dst, src, m, opacity, sx0, sy0, sx1, sy1,
              0.0, ZIMG_BEND_LINEAR, 0.0, ZIMG_BEND_LINEAR, 0.0, 1.0, ZIMG_BLEND_NORMAL);
}

void zimg_draw_warp(zimg *dst, const zimg *src, const double m[6], double opacity,
                    double bend_x, int curve_x, double bend_y, int curve_y)
{
    if (!src) return;
    draw_impl(dst, src, m, opacity, 0, 0, src->w, src->h,
              bend_x, curve_x, bend_y, curve_y, 0.0, 1.0, ZIMG_BLEND_NORMAL);
}

void zimg_draw_blend(zimg *dst, const zimg *src, const double m[6], double opacity, int blend)
{
    if (!src) return;
    draw_impl(dst, src, m, opacity, 0, 0, src->w, src->h,
              0.0, ZIMG_BEND_LINEAR, 0.0, ZIMG_BEND_LINEAR, 0.0, 1.0, blend);
}

void zimg_draw_warp_blend(zimg *dst, const zimg *src, const double m[6], double opacity,
                          double bend_x, int curve_x, double bend_y, int curve_y, int blend)
{
    zimg_draw_warp_blend_t(dst, src, m, opacity, bend_x, curve_x, bend_y, curve_y,
                           blend, 0.0, 1.0);
}

/* 带形变平台的版本：
   bend_tmin 以上的行共用 bend_tmin 处的形变量（上平台，跟随件在上面时用）；
   bend_tmax 以下的行共用 bend_tmax 处的形变量（下平台，跟随件在下面时用）。
   不设下平台就传 1.0。 */
void zimg_draw_warp_blend_t(zimg *dst, const zimg *src, const double m[6], double opacity,
                            double bend_x, int curve_x, double bend_y, int curve_y,
                            int blend, double bend_tmin, double bend_tmax)
{
    if (!src) return;
    draw_impl(dst, src, m, opacity, 0, 0, src->w, src->h,
              bend_x, curve_x, bend_y, curve_y, bend_tmin, bend_tmax, blend);
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
                      double bend_x, int curve_x, double bend_y, int curve_y,
                      double bend_tmin, double bend_tmax, int blend)
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
    {   /* 分块渲染：只画分给我的那几行（坐标系不变，仍是整幅画布坐标） */
        int cy0, cy1;
        zimg_clip_range(dst, &cy0, &cy1);
        if (y0 < cy0) y0 = cy0;
        if (y1 > cy1) y1 = cy1;
        if (y1 <= y0) return;
    }

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
                /* 形变平台：这一行以上不再继续增大形变。
                   躯干贴图的顶边是脖子/衣领，而 ROOT 曲线恰好把最大形变给了顶边 ——
                   结果衣领比它上面的头、下面的胸都移动得多，脖子处出现横向滑移
                   （2026-10-14 用户反馈"颈部整体细微横向位移，包括兜帽"）。
                   把颈线以上的 t 钳到颈线处，衣领就和头完全同步了。 */
                if (t < bend_tmin) t = bend_tmin;
                /* 下平台：这一行以下不再继续增大形变。和上平台互为镜像 ——
                   跟随件挂在下面时（脚跟着腿、手跟着前臂）用它，
                   以前只能靠把源贴图在切线以下整个裁掉来回避（G97）。 */
                if (t > bend_tmax) t = bend_tmax;
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
            double sa;
            if (fx < -0.5 || fy < -0.5 || fx > src->w - 0.5 || fy > src->h - 0.5) continue;
            if (fx < sx0 - 0.5 || fx > sx1 - 0.5 || fy < sy0 - 0.5 || fy > sy1 - 0.5) continue;
            sample_premul(src, fx - 0.5, fy - 0.5, s);
            sa = s[3] * opacity;
            if (sa <= 0.0001) continue;
            q = dst->px + ((size_t)py * dst->w + px) * 4;
            blend_px(q, s[0] / s[3], s[1] / s[3], s[2] / s[3], sa, blend);
        }
    }
}

/* ---------------- 网格形变（Live2D 的自由变形器等价物） ----------------
   三角形仿射映射：源三角 (s0,s1,s2) → 目标三角 (d0,d1,d2)。
   逐目标像素算重心坐标，落在三角形内就反推源坐标取样。
   这样做的好处：不需要去求整张网格的逆映射，格子怎么扭都不会裂缝。 */
static void draw_tri(zimg *dst, const zimg *src, double opacity,
                     const double sx[3], const double sy[3],
                     const double dx[3], const double dy[3], int blend)
{
    double den, minx, miny, maxx, maxy;
    int x0, y0, x1, y1, px, py;
    den = (dy[1] - dy[2]) * (dx[0] - dx[2]) + (dx[2] - dx[1]) * (dy[0] - dy[2]);
    if (fabs(den) < 1e-9) return;                 /* 退化三角形 */

    minx = maxx = dx[0]; miny = maxy = dy[0];
    { int i; for (i = 1; i < 3; ++i) {
        if (dx[i] < minx) minx = dx[i];
        if (dx[i] > maxx) maxx = dx[i];
        if (dy[i] < miny) miny = dy[i];
        if (dy[i] > maxy) maxy = dy[i];
    } }
    x0 = ZC_CLAMP((int)floor(minx), 0, dst->w);
    x1 = ZC_CLAMP((int)ceil(maxx) + 1, 0, dst->w);
    y0 = ZC_CLAMP((int)floor(miny), 0, dst->h);
    y1 = ZC_CLAMP((int)ceil(maxy) + 1, 0, dst->h);
    {   /* 分块渲染的行裁剪（网格形变这条路也得走，漏一条就是静默的竞争） */
        int cy0, cy1;
        zimg_clip_range(dst, &cy0, &cy1);
        if (y0 < cy0) y0 = cy0;
        if (y1 > cy1) y1 = cy1;
        if (y1 <= y0) return;
    }

    for (py = y0; py < y1; ++py) {
        for (px = x0; px < x1; ++px) {
            double qx = px + 0.5, qy = py + 0.5;
            double w0, w1, w2, fx, fy, s[4], sa;
            uint8_t *q;
            w0 = ((dy[1] - dy[2]) * (qx - dx[2]) + (dx[2] - dx[1]) * (qy - dy[2])) / den;
            w1 = ((dy[2] - dy[0]) * (qx - dx[2]) + (dx[0] - dx[2]) * (qy - dy[2])) / den;
            w2 = 1.0 - w0 - w1;
            /* 容差 1e-9：格子边界上的像素宁可多画一次，也不要留一条透明缝 */
            if (w0 < -1e-9 || w1 < -1e-9 || w2 < -1e-9) continue;
            fx = w0 * sx[0] + w1 * sx[1] + w2 * sx[2];
            fy = w0 * sy[0] + w1 * sy[1] + w2 * sy[2];
            if (fx < -0.5 || fy < -0.5 || fx > src->w - 0.5 || fy > src->h - 0.5) continue;
            sample_premul(src, fx - 0.5, fy - 0.5, s);
            sa = s[3] * opacity;
            if (sa <= 0.0001) continue;
            q = dst->px + ((size_t)py * dst->w + px) * 4;
            blend_px(q, s[0] / s[3], s[1] / s[3], s[2] / s[3], sa, blend);
        }
    }
}

void zimg_draw_mesh(zimg *dst, const zimg *src, const double m[6], double opacity,
                    int cols, int rows, const double *offsets)
{
    zimg_draw_mesh_blend(dst, src, m, opacity, cols, rows, offsets, ZIMG_BLEND_NORMAL);
}

void zimg_draw_mesh_blend(zimg *dst, const zimg *src, const double m[6], double opacity,
                          int cols, int rows, const double *offsets, int blend)
{
    zimg_draw_mesh_bend_blend(dst, src, m, opacity, cols, rows, offsets,
                              0.0, ZIMG_BEND_ROOT, 0.0, ZIMG_BEND_ROOT, blend);
}

/* 网格形变 + 平滑形变一起画。
   以前这两条路是 if/else 互斥的：部件一旦挂上形变器，它的 bend_x/bend_y 就被整个
   丢掉。多段摆链正是"第一段写 bend、第二段写形变器"，所以第一段一直白写。
   Live2D 的变形器本来就是可以嵌套叠加的，这里按同样的语义来：
   先把控制点按 offsets（源图像素）挪好、过矩阵，再在**目标坐标**上叠 bend 位移——
   和 draw_impl 里逐像素那套用的是同一个 zimg_bend_factor，口径一致。
   差别只在采样密度：warp 是逐像素求 t，这里是逐控制点求 t、格子内线性插值，
   所以网格行数太少时 bend 的曲线会被折线化（rows>=4 肉眼已看不出）。 */
void zimg_draw_mesh_bend_blend(zimg *dst, const zimg *src, const double m[6], double opacity,
                               int cols, int rows, const double *offsets,
                               double bend_x, int curve_x, double bend_y, int curve_y,
                               int blend)
{
    zimg_draw_mesh_bend_blend_t(dst, src, m, opacity, cols, rows, offsets,
                                bend_x, curve_x, bend_y, curve_y, blend, 0.0, 1.0);
}

/* 带形变平台的网格版本。
   ⚠ 必须和 zimg_draw_warp_blend_t 口径一致 —— 一个部件挂没挂形变器是**运行期**
   才知道的（形变器 amount 为 0 时走 warp 路径、不为 0 时走 mesh 路径），
   两条路算出来的形变必须一模一样，否则裙子一摆脖子就会突然错位
   （2026-10-14 实测：bend_hold_above 当时只接了 warp 那条，
    颈部修复"只在裙子不动的时候有效"）。 */
void zimg_draw_mesh_bend_blend_t(zimg *dst, const zimg *src, const double m[6], double opacity,
                                 int cols, int rows, const double *offsets,
                                 double bend_x, int curve_x, double bend_y, int curve_y,
                                 int blend, double bend_tmin, double bend_tmax)
{
    int c, rr, moved = 0, np;
    int bent = (fabs(bend_x) > 1e-9 || fabs(bend_y) > 1e-9);
    if (!dst || !src || cols < 1 || rows < 1 || !offsets) {
        if (bent) zimg_draw_warp_blend_t(dst, src, m, opacity, bend_x, curve_x,
                                         bend_y, curve_y, blend, bend_tmin, bend_tmax);
        else      zimg_draw_blend(dst, src, m, opacity, blend);
        return;
    }
    if (cols > 16) cols = 16;
    if (rows > 16) rows = 16;
    np = (cols + 1) * (rows + 1);
    for (c = 0; c < np * 2; ++c)
        if (fabs(offsets[c]) > 1e-6) { moved = 1; break; }
    if (!moved) {                        /* 没挪控制点就走原路（但 bend 和平台都不能丢） */
        if (bent) zimg_draw_warp_blend_t(dst, src, m, opacity, bend_x, curve_x,
                                         bend_y, curve_y, blend, bend_tmin, bend_tmax);
        else      zimg_draw_blend(dst, src, m, opacity, blend);
        return;
    }

    for (rr = 0; rr < rows; ++rr) {
        for (c = 0; c < cols; ++c) {
            int idx[4];
            double sx[4], sy[4], dxp[4], dyp[4];
            int k;
            idx[0] = rr * (cols + 1) + c;           /* 左上 */
            idx[1] = idx[0] + 1;                    /* 右上 */
            idx[2] = (rr + 1) * (cols + 1) + c + 1; /* 右下 */
            idx[3] = idx[2] - 1;                    /* 左下 */
            sx[0] = (double)src->w * c / cols;       sy[0] = (double)src->h * rr / rows;
            sx[1] = (double)src->w * (c + 1) / cols; sy[1] = sy[0];
            sx[2] = sx[1];                           sy[2] = (double)src->h * (rr + 1) / rows;
            sx[3] = sx[0];                           sy[3] = sy[2];
            for (k = 0; k < 4; ++k) {
                double lx = sx[k] + offsets[idx[k] * 2];
                double ly = sy[k] + offsets[idx[k] * 2 + 1];
                dxp[k] = m[0] * lx + m[2] * ly + m[4];
                dyp[k] = m[1] * lx + m[3] * ly + m[5];
                if (bent) {               /* 叠加平滑形变（和 warp 同一套曲线） */
                    double tb = sy[k] / (double)src->h;
                    if (tb < bend_tmin) tb = bend_tmin;   /* 形变平台，口径同 draw_impl */
                    if (tb > bend_tmax) tb = bend_tmax;
                    dxp[k] += bend_x * zimg_bend_factor(tb, curve_x);
                    dyp[k] += bend_y * zimg_bend_factor(tb, curve_y);
                }
            }
            {   /* 一个格子 = 两个三角形 */
                double tsx[3], tsy[3], tdx[3], tdy[3];
                int a[2][3] = { {0, 1, 2}, {0, 2, 3} };
                int t;
                for (t = 0; t < 2; ++t) {
                    for (k = 0; k < 3; ++k) {
                        tsx[k] = sx[a[t][k]]; tsy[k] = sy[a[t][k]];
                        tdx[k] = dxp[a[t][k]]; tdy[k] = dyp[a[t][k]];
                    }
                    draw_tri(dst, src, opacity, tsx, tsy, tdx, tdy, blend);
                }
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
