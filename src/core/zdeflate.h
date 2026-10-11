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

/* zlib 封装：2 字节头(0x78 0x01) + 一个或多个 deflate 块 + adler32。 */
size_t zlib_compress_rle(const uint8_t *data, size_t n, uint8_t **out);

#ifdef __cplusplus
}
#endif
#endif /* ZDEFLATE_H */
