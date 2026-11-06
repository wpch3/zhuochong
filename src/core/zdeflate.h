/*
 * zdeflate.h - 极简 deflate（固定 Huffman + RLE）与 zlib 封装
 *
 * 为什么不用 zlib：
 *   - Windows 目标要零外部依赖（用户直接双击 exe 就能跑）；
 *   - 我们的图像数据以大片透明像素为主，固定 Huffman + RLE 已能压缩 5~20 倍，
 *     足够让沙箱预览流畅、导出的 PNG 体积可控。
 * 不追求通用压缩率，只求“正确、可离线、无依赖”。
 */
#ifndef ZDEFLATE_H
#define ZDEFLATE_H

#include "zc.h"

#ifdef __cplusplus
extern "C" {
#endif

/* deflate：固定 Huffman + 仅使用 distance=1 的游程匹配（RLE）。
 * out 为动态分配的缓冲，调用者负责 free。返回压缩后长度，0 表示失败。 */
size_t zdeflate_rle(const uint8_t *data, size_t n, uint8_t **out);

/* deflate：固定 Huffman + 32KB 窗口的 LZ77（哈希链，链长上限 48）。
 * 压缩率接近 zlib（实测一帧立绘 287KB → 155KB，zlib 为 151KB），速度够实时。 */
size_t zdeflate_lz77(const uint8_t *data, size_t n, uint8_t **out);

/* 同上，但可以当"一段"用，供多线程并行压缩后**按字节拼接**：
 *   final=1 → 和 zdeflate_lz77 完全一样（BFINAL=1，流到此为止）；
 *   final=0 → BFINAL=0，并在数据块后补一个空的 stored 块把位流对齐到字节边界，
 *             于是 part0+part1+...+partN（最后一个 final=1）仍是合法 deflate 流。
 * 代价：每段开头窗口是空的，压缩率略降（实测 4 段 12.7%→13.0%）。 */
size_t zdeflate_lz77_part(const uint8_t *data, size_t n, uint8_t **out, int final);

/* zlib 封装：2 字节头(0x78 0x01) + 一个或多个 deflate 块 + adler32。 */
size_t zlib_compress_rle(const uint8_t *data, size_t n, uint8_t **out);

/* 把若干个已压好的 deflate 段拼成完整 zlib 流（2 字节头 + 各段 + adler32）。
 * adler32 要按**原始未压缩数据**算，所以得把它一起传进来。 */
size_t zlib_wrap_parts(const uint8_t *const *parts, const size_t *plen, int nparts,
                       const uint8_t *raw, size_t rawlen, uint8_t **out);
/* adler32（延迟取模版；每字节取模会慢 7 倍，4.6MB 实测 14.3ms → 2.1ms）。 */
uint32_t z_adler32(const uint8_t *data, size_t n);

#ifdef __cplusplus
}
#endif
#endif /* ZDEFLATE_H */
