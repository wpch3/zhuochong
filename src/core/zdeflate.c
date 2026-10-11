/* zdeflate.c - 固定 Huffman + RLE 的 deflate 实现 */
#include "zdeflate.h"

/* ------------------------------------------------------------ 位写入流 */
typedef struct {
    uint8_t *buf;
    size_t   len, cap;
    uint32_t bitbuf;
    int      bitcnt;
    int      failed;
} bitw;

static void bw_init(bitw *b, size_t hint)
{
    b->cap = hint + hint / 4 + 64;
    b->buf = (uint8_t *)z_alloc(b->cap);
    b->len = 0;
    b->bitbuf = 0;
    b->bitcnt = 0;
    b->failed = 0;
}

static void bw_putbit(bitw *b, unsigned bit)
{
    b->bitbuf |= (uint32_t)(bit & 1) << b->bitcnt;
    if (++b->bitcnt == 8) {
        if (b->len >= b->cap) {
            b->cap *= 2;
            b->buf = (uint8_t *)z_realloc(b->buf, b->cap);
        }
        b->buf[b->len++] = (uint8_t)(b->bitbuf & 0xFF);
        b->bitbuf = 0;
        b->bitcnt = 0;
    }
}

/* deflate 的 Huffman 码按“高位在先”写入 */
static void bw_putcode(bitw *b, unsigned code, int nbits)
{
    int i;
    for (i = nbits - 1; i >= 0; --i) bw_putbit(b, (code >> i) & 1u);
}

/* 直接按值写 n 位（LSB 在先，用于额外位与头部） */
static void bw_putbits_lsb(bitw *b, unsigned value, int nbits)
{
    int i;
    for (i = 0; i < nbits; ++i) bw_putbit(b, (value >> i) & 1u);
}

static void bw_flush(bitw *b)
{
    if (b->bitcnt > 0) {
        if (b->len >= b->cap) {
            b->cap *= 2;
            b->buf = (uint8_t *)z_realloc(b->buf, b->cap);
        }
        b->buf[b->len++] = (uint8_t)(b->bitbuf & 0xFF);
        b->bitbuf = 0;
        b->bitcnt = 0;
    }
}

/* --------------------------------------------------- 固定 Huffman 码表 */
static void put_litlen(bitw *b, unsigned sym)
{
    if (sym <= 143) bw_putcode(b, 0x30 + sym, 8);
    else if (sym <= 255) bw_putcode(b, 0x190 + (sym - 144), 9);
    else if (sym <= 279) bw_putcode(b, sym - 256, 7);
    else bw_putcode(b, 0xC0 + (sym - 280), 8);
}

static const unsigned short len_base[29] = {
    3,4,5,6,7,8,9,10,11,13,15,17,19,23,27,31,35,43,51,59,67,83,99,115,131,163,195,227,258
};
static const unsigned char len_extra[29] = {
    0,0,0,0,0,0,0,0,1,1,1,1,2,2,2,2,3,3,3,3,4,4,4,4,5,5,5,5,0
};

static int len_code_for(unsigned len, unsigned *base, unsigned *extra)
{
    int i;
    for (i = 28; i >= 0; --i) {
        if (len >= len_base[i]) {
            *base = len_base[i];
            *extra = len_extra[i];
            return 257 + i;
        }
    }
    return -1;
}

/* 距离码 0 = 距离 1（额外位 0）。我们只用 distance=1。 */
static void put_rle_match(bitw *b, unsigned len)
{
    unsigned base = 0, extra = 0;
    int code = len_code_for(len, &base, &extra);
    if (code < 0) return;
    put_litlen(b, (unsigned)code);
    if (extra) bw_putbits_lsb(b, len - base, (int)extra);
    /* 距离码 0：5 位固定码 00000，无额外位 */
    bw_putcode(b, 0, 5);
}

size_t zdeflate_rle(const uint8_t *data, size_t n, uint8_t **out)
{
    bitw b;
    size_t i = 0;
    if (!out) return 0;
    *out = NULL;
    bw_init(&b, n);
    bw_putbit(&b, 1);           /* BFINAL */
    bw_putbits_lsb(&b, 1, 2);   /* BTYPE = 01 固定 Huffman */

    while (i < n) {
        size_t run = 1;
        /* 统计“同一个字节”的连续长度 */
        while (i + run < n && data[i + run] == data[i] && run < 258) run++;

        /* distance=1 的自复制（RLE）成立的两个前提，缺一不可：
         *   1) 前面至少已经输出过 1 个字节（i > 0）；
         *   2) 紧邻的前一个字节与当前字节相同 —— 否则解码器复制出来的
         *      是前一个字节的值（例如 …01 00 00 00… 会被解成 …01 01 01 01…）。
         * 不满足时先输出一个字面量，下一轮就满足条件了。 */
        if (run >= 4 && i > 0 && data[i - 1] == data[i]) {
            put_rle_match(&b, (unsigned)run);
            i += run;
        } else {
            put_litlen(&b, data[i]);
            i++;
        }
    }
    put_litlen(&b, 256);   /* 块结束 */
    bw_flush(&b);
    if (b.failed) {
        free(b.buf);
        return 0;
    }
    *out = b.buf;
    return b.len;
}


/* ------------------------------------------------------------------ LZ77
 * 只有 RLE（distance=1）时，一帧立绘 PNG 要 287KB；加上真正的 LZ77 窗口匹配
 * 后降到 ~155KB（标准 zlib 是 151KB）。预览是按帧走网络的，体积直接等于流畅度。
 * 仍然用固定 Huffman：不用统计、不用建表，代码短、没有外部依赖。 */
#define ZD_WSIZE     32768u            /* 窗口 32KB（deflate 上限） */
#define ZD_HSIZE     32768u            /* 哈希桶数 */
#define ZD_MIN_MATCH 3
#define ZD_MAX_MATCH 258
#define ZD_MAX_CHAIN 48                /* 每个位置最多回溯这么多候选，换速度 */

static const unsigned zd_dist_base[30] = {
    1, 2, 3, 4, 5, 7, 9, 13, 17, 25, 33, 49, 65, 97, 129, 193, 257, 385, 513, 769,
    1025, 1537, 2049, 3073, 4097, 6145, 8193, 12289, 16385, 24577
};
static const int zd_dist_extra[30] = {
    0, 0, 0, 0, 1, 1, 2, 2, 3, 3, 4, 4, 5, 5, 6, 6, 7, 7, 8, 8,
    9, 9, 10, 10, 11, 11, 12, 12, 13, 13
};

static int zd_dist_code(unsigned d, unsigned *base, unsigned *extra)
{
    int i;
    for (i = 29; i >= 0; --i) {
        if (d >= zd_dist_base[i]) {
            *base = zd_dist_base[i];
            *extra = (unsigned)zd_dist_extra[i];
            return i;
        }
    }
    return -1;
}

static void put_match(bitw *b, unsigned len, unsigned dist)
{
    unsigned lbase = 0, lextra = 0, dbase = 0, dextra = 0;
    int lc = len_code_for(len, &lbase, &lextra);
    int dc = zd_dist_code(dist, &dbase, &dextra);
    if (lc < 0 || dc < 0) return;
    put_litlen(b, (unsigned)lc);
    if (lextra) bw_putbits_lsb(b, len - lbase, (int)lextra);
    bw_putcode(b, (unsigned)dc, 5);           /* 固定 Huffman 的距离码就是 5 位码号 */
    if (dextra) bw_putbits_lsb(b, dist - dbase, (int)dextra);
}

size_t zdeflate_lz77(const uint8_t *data, size_t n, uint8_t **out)
{
    bitw b;
    size_t i = 0;
    int *head = NULL, *prev = NULL;
    unsigned h;

    if (!out) return 0;
    *out = NULL;
    if (n < 16) return zdeflate_rle(data, n, out);   /* 太短，不值得建表 */

    head = (int *)z_alloc(sizeof(int) * ZD_HSIZE);
    prev = (int *)z_alloc(sizeof(int) * ZD_WSIZE);
    if (!head || !prev) { free(head); free(prev); return zdeflate_rle(data, n, out); }
    for (h = 0; h < ZD_HSIZE; ++h) head[h] = -1;
    for (h = 0; h < ZD_WSIZE; ++h) prev[h] = -1;

    bw_init(&b, n / 2 + 64);
    bw_putbit(&b, 1);           /* BFINAL */
    bw_putbits_lsb(&b, 1, 2);   /* BTYPE = 01 固定 Huffman */

    while (i < n) {
        size_t best_len = 0, best_dist = 0;
        if (i + ZD_MIN_MATCH <= n) {
            unsigned hv = (unsigned)((data[i] << 10) ^ (data[i + 1] << 5) ^ data[i + 2]) & (ZD_HSIZE - 1);
            int cand = head[hv];
            int chain = ZD_MAX_CHAIN;
            while (cand >= 0 && chain-- > 0) {
                size_t d = i - (size_t)cand;
                size_t l = 0, maxl;
                if (d == 0 || d > ZD_WSIZE) break;
                maxl = n - i; if (maxl > ZD_MAX_MATCH) maxl = ZD_MAX_MATCH;
                /* 先比第 best_len 个字节：不比已有最优长就直接跳过（zlib 的老把戏） */
                if (best_len >= ZD_MIN_MATCH && data[cand + best_len] != data[i + best_len]) {
                    cand = prev[(size_t)cand & (ZD_WSIZE - 1)];
                    continue;
                }
                while (l < maxl && data[cand + l] == data[i + l]) l++;
                if (l > best_len) { best_len = l; best_dist = d; if (l >= ZD_MAX_MATCH) break; }
                cand = prev[(size_t)cand & (ZD_WSIZE - 1)];
            }
            /* 把当前位置挂进哈希链 */
            prev[i & (ZD_WSIZE - 1)] = head[hv];
            head[hv] = (int)i;
        }
        if (best_len >= ZD_MIN_MATCH) {
            size_t k;
            put_match(&b, (unsigned)best_len, (unsigned)best_dist);
            /* 匹配跨过的位置也要挂进哈希链，否则后面找不到它们 */
            for (k = 1; k < best_len; ++k) {
                size_t j = i + k;
                if (j + ZD_MIN_MATCH <= n) {
                    unsigned hv2 = (unsigned)((data[j] << 10) ^ (data[j + 1] << 5) ^ data[j + 2]) & (ZD_HSIZE - 1);
                    prev[j & (ZD_WSIZE - 1)] = head[hv2];
                    head[hv2] = (int)j;
                }
            }
            i += best_len;
        } else {
            put_litlen(&b, data[i]);
            i++;
        }
    }
    put_litlen(&b, 256);
    bw_flush(&b);
    free(head);
    free(prev);
    if (b.failed) { free(b.buf); return 0; }
    *out = b.buf;
    return b.len;
}

size_t zlib_compress_rle(const uint8_t *data, size_t n, uint8_t **out)
{
    uint8_t *def = NULL;
    size_t deflen, total;
    uint8_t *buf;
    uint32_t a = 1, bb = 0;
    size_t i;

    deflen = zdeflate_lz77(data, n, &def);
    if (!def || deflen == 0) deflen = zdeflate_rle(data, n, &def);
    if (!def || deflen == 0) {
        /* 压缩失败则退化为存储型块（保证正确性优先） */
        size_t off = 0;
        total = 2 + ((n + 65534) / 65535) * 5 + n + 4;
        buf = (uint8_t *)z_alloc(total);
        buf[0] = 0x78; buf[1] = 0x01;
        total = 2;
        while (off < n) {
            size_t chunk = n - off > 65535 ? 65535 : n - off;
            int last = (off + chunk >= n) ? 1 : 0;
            buf[total++] = (uint8_t)last;
            buf[total++] = (uint8_t)(chunk & 0xFF);
            buf[total++] = (uint8_t)(chunk >> 8);
            buf[total++] = (uint8_t)(~chunk & 0xFF);
            buf[total++] = (uint8_t)((~chunk >> 8) & 0xFF);
            memcpy(buf + total, data + off, chunk);
            total += chunk;
            off += chunk;
        }
        buf[total++] = 0; buf[total++] = 0; buf[total++] = 0; buf[total++] = 0;
        free(def);
        *out = buf;
        return total;
    }
    total = 2 + deflen + 4;
    buf = (uint8_t *)z_alloc(total);
    buf[0] = 0x78;
    buf[1] = 0x01;
    memcpy(buf + 2, def, deflen);

    /* adler32 */
    for (i = 0; i < n; ++i) {
        a = (a + data[i]) % 65521;
        bb = (bb + a) % 65521;
    }
    {
        uint32_t ad = (bb << 16) | a;
        buf[2 + deflen + 0] = (uint8_t)(ad >> 24);
        buf[2 + deflen + 1] = (uint8_t)(ad >> 16);
        buf[2 + deflen + 2] = (uint8_t)(ad >> 8);
        buf[2 + deflen + 3] = (uint8_t)ad;
    }
    free(def);
    *out = buf;
    return total;
}
