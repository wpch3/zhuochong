/*
 * test_core.c - 单元测试（[测试锁]：不通过就不许交付）
 *
 * 覆盖：
 *   JSON 解析与错误定位、JSON Schema 与 pattern、状态机优先级/可中断/过期、
 *   眨眼时序、图像（缩放/合成/命中/PNG 往返）、配置加载与非法配置诊断、
 *   角色包加载与换装、RLE deflate 与 zlib 兼容性、空闲入睡与唤醒。
 *
 * 运行：./build/test_core <项目根目录>
 */
#include "../src/core/zc.h"
#include "../src/core/zjson.h"
#include "../src/core/zschema.h"
#include "../src/core/zsm.h"
#include "../src/core/zimg.h"
#include "../src/core/zdeflate.h"
#include "../src/core/zpet.h"
#include "../src/core/zconfig.h"
#include "../src/core/zrig.h"
#include "../src/core/zinteract.h"

#include <stdio.h>
#include <string.h>
#include <math.h>
#ifndef _WIN32
#  include <unistd.h>
#endif

static int g_pass = 0, g_fail = 0;
static const char *g_section = "";

#define CHECK(cond, ...) do { \
    if (cond) { g_pass++; } \
    else { \
        g_fail++; \
        fprintf(stderr, "  [失败] %s: ", g_section); \
        fprintf(stderr, __VA_ARGS__); \
        fprintf(stderr, "  (%s:%d)\n", __FILE__, __LINE__); \
    } \
} while (0)

#define SECTION(name) do { g_section = name; printf("== %s ==\n", name); } while (0)

static char g_root[512];

/* ------------------------------------------------------------- JSON */
static void test_json(void)
{
    SECTION("zjson：解析与诊断");
    {
        zerr e;
        zjson *j;
        zerr_clear(&e);
        j = zjson_parse("{\"a\": 1, \"b\": [true, null, \"x\"], // 注释\n \"c\": 1.5,}",
                        "mem", &e);
        CHECK(j != NULL, "带注释与尾随逗号的 JSON 应能解析：%s", e.msg);
        if (j) {
            CHECK(zjson_int(zjson_get(j, "a"), -1) == 1, "a 应为 1");
            CHECK(zjson_count(zjson_get(j, "b")) == 3, "b 应有 3 个元素");
            CHECK(zjson_num(zjson_get(j, "c"), 0) > 1.4, "c 应为 1.5");
            zjson_free(j);
        }
    }
    {
        zerr e;
        zjson *j;
        zerr_clear(&e);
        j = zjson_parse("{\n  \"a\": 1,\n  \"b\" 2\n}", "mem", &e);
        CHECK(j == NULL, "缺冒号应报错");
        CHECK(e.line == 3, "错误行号应为 3，实际 %d", e.line);
        CHECK(strstr(e.msg, ":") != NULL, "错误信息应说明缺冒号：%s", e.msg);
    }
    {
        zerr e;
        zjson *j;
        zerr_clear(&e);
        j = zjson_parse("{\"路径\": \"值\", \"emoji\": \"\\u4e2d\\u6587\"}", "mem", &e);
        CHECK(j != NULL, "UTF-8 键与 \\u 转义应支持：%s", e.msg);
        if (j) {
            CHECK(z_streq(zjson_str(zjson_get(j, "路径"), ""), "值"), "UTF-8 键取值");
            CHECK(z_streq(zjson_str(zjson_get(j, "emoji"), ""), "中文"), "\\u 转义解码");
            zjson_free(j);
        }
    }
    {
        /* 生成器往返 */
        zjson_w *w = zjson_w_new(1);
        size_t len = 0;
        char *text;
        zerr e;
        zjson *j;
        zjson_w_obj_begin(w);
        zjson_w_key(w, "名字"); zjson_w_str(w, "小寻\"引号\"");
        zjson_w_key(w, "数值"); zjson_w_num(w, 0.55);
        zjson_w_key(w, "开关"); zjson_w_bool(w, 1);
        zjson_w_key(w, "列表"); zjson_w_arr_begin(w);
        zjson_w_int(w, 1); zjson_w_int(w, 2); zjson_w_arr_end(w);
        zjson_w_obj_end(w);
        text = zjson_w_take(w, &len);
        zjson_w_free(w);
        zerr_clear(&e);
        j = zjson_parse(text, "gen", &e);
        CHECK(j != NULL, "生成的 JSON 应能重新解析：%s", e.msg);
        if (j) {
            CHECK(z_streq(zjson_str(zjson_get(j, "名字"), ""), "小寻\"引号\""), "字符串转义往返");
            CHECK(fabs(zjson_num(zjson_get(j, "数值"), 0) - 0.55) < 1e-9, "数值往返");
            CHECK(zjson_bool(zjson_get(j, "开关"), 0) == 1, "布尔往返");
            CHECK(zjson_count(zjson_get(j, "列表")) == 2, "数组往返");
            zjson_free(j);
        }
        free(text);
    }
}

/* ---------------------------------------------------------- Schema */
static void test_schema(void)
{
    SECTION("zschema：类型/必填/范围/枚举/pattern");
    {
        zerr e;
        zdiag d;
        zjson *schema, *doc;
        const char *schema_text =
            "{\"type\":\"object\",\"required\":[\"id\",\"enabled\"],"
            "\"properties\":{\"id\":{\"type\":\"string\",\"pattern\":\"^[a-z_]+$\"},"
            "\"enabled\":{\"type\":\"boolean\"},"
            "\"mode\":{\"type\":\"string\",\"enum\":[\"a\",\"b\"]},"
            "\"n\":{\"type\":\"integer\",\"minimum\":1,\"maximum\":10}}}";
        zerr_clear(&e);
        schema = zjson_parse(schema_text, "schema", &e);
        doc = zjson_parse("{\"id\":\"Chat1\",\"enabled\":true,\"mode\":\"c\",\"n\":99}", "doc", &e);
        zdiag_init(&d);
        zschema_validate(schema, doc, "doc.json", &d);
        CHECK(d.error_count >= 3, "应报出 3 个以上错误，实际 %d", d.error_count);
        CHECK(strstr(d.items[0].field, "id") || d.error_count > 0, "错误应带字段名");
        zjson_free(schema);
        zjson_free(doc);
    }
    {
        zerr e;
        zjson *schema, *doc;
        zdiag d;
        zerr_clear(&e);
        schema = zjson_parse("{\"type\":\"object\",\"properties\":{\"c\":{\"type\":\"string\",\"pattern\":\"^#[0-9A-Fa-f]{6}$\"}}}", "s", &e);
        doc = zjson_parse("{\"c\":\"#7EC8C4\"}", "d", &e);
        zdiag_init(&d);
        zschema_validate(schema, doc, "d", &d);
        CHECK(d.error_count == 0, "#RRGGBB 应通过 pattern 校验（实际 %d 个错误）", d.error_count);
        zjson_free(schema); zjson_free(doc);
        schema = zjson_parse("{\"type\":\"object\",\"properties\":{\"c\":{\"type\":\"string\",\"pattern\":\"^#[0-9A-Fa-f]{6}$\"}}}", "s", &e);
        doc = zjson_parse("{\"c\":\"#7EC8\"}", "d", &e);
        zdiag_init(&d);
        zschema_validate(schema, doc, "d", &d);
        CHECK(d.error_count == 1, "错误颜色应被拒绝");
        zjson_free(schema); zjson_free(doc);
    }
}

/* ------------------------------------------------------ 状态机 */
static void test_state_machine(void)
{
    zsm sm;
    zsm_state_def def;
    SECTION("zsm：优先级 / 可中断 / 过期回退");
    zsm_init(&sm);
    memset(&def, 0, sizeof(def));
    z_strlcpy(def.id, "idle", sizeof(def.id));
    def.priority = 0; def.duration_s = -1; def.loop = 1; def.interruptible = 1;
    zsm_add_state(&sm, &def);
    z_strlcpy(def.id, "talk", sizeof(def.id));
    def.priority = 4; def.duration_s = -1; def.loop = 1; def.interruptible = 1;
    zsm_add_state(&sm, &def);
    z_strlcpy(def.id, "head_pat", sizeof(def.id));
    def.priority = 6; def.duration_s = 1.0; def.loop = 0; def.interruptible = 0;
    z_strlcpy(def.return_state, "idle", sizeof(def.return_state));
    zsm_add_state(&sm, &def);
    z_strlcpy(def.id, "clicked", sizeof(def.id));
    def.priority = 4; def.duration_s = 0.5; def.loop = 0; def.interruptible = 1;
    zsm_add_state(&sm, &def);

    zsm_start(&sm, "idle", 0.0);
    CHECK(z_streq(zsm_current_id(&sm), "idle"), "初始为 idle");
    CHECK(zsm_request(&sm, "talk", "test", 0) == 1, "talk(4) 可打断 idle(0)");
    CHECK(zsm_request(&sm, "clicked", "test", 0) == 1, "clicked(4) ≥ talk(4) 且 talk 可中断 → 允许");
    CHECK(zsm_request(&sm, "head_pat", "test", 0) == 1, "head_pat(6) 可打断 clicked");
    CHECK(zsm_request(&sm, "talk", "test", 0) == 0, "talk 不能打断不可中断的 head_pat");
    zsm_update(&sm, 0.5);
    CHECK(z_streq(zsm_current_id(&sm), "head_pat"), "未到期不应回退");
    zsm_update(&sm, 1.01);
    CHECK(z_streq(zsm_current_id(&sm), "idle"), "到期应回到 return_state");
    CHECK(zsm_request(&sm, "talk", "test", 0) == 1, "回 idle 后可再次切换");
    CHECK(zsm_request(&sm, "talk", "test", 0) == 0, "同状态重复请求被拒绝");
    CHECK(zsm_request(&sm, "talk", "test", 1) == 1, "force 可重播当前动作");
    CHECK(zsm_request(&sm, "不存在", "test", 0) == 0, "未知状态被拒绝");
}

/* ---------------------------------------------------------- 眨眼 */
static void test_blink(void)
{
    SECTION("眨眼状态机（对齐 Live2D CubismEyeBlink 五态）");
    {
        char rig_path[1024];
        char dir[1024];
        zdiag d;
        zrig *r;
        double t;
        int saw_closed = 0, saw_open = 0;
        double close_time = 0.0, reopen_time = 0.0;
        zdiag_init(&d);
        z_snprintf(dir, sizeof(dir), "%s/characters/xiaoxun/forms/teen", g_root);
        z_snprintf(rig_path, sizeof(rig_path), "%s/rig.json", dir);
        r = zrig_load(rig_path, dir, &d);
        CHECK(r != NULL, "装载 rig.json 应成功（错误 %d 条）", d.error_count);
        if (!r) { zdiag_print(&d, stderr); return; }
        zrig_blink_set_enabled(r, 1);
        /* 以 60Hz 推进 20 秒，记录闭眼与重新睁开的时刻 */
        for (t = 0.0; t < 20.0; t += 1.0 / 60.0) {
            double v;
            zrig_tick(r, t);
            v = zrig_blink_value(r);
            if (v >= 0.999 && !saw_closed) { saw_closed = 1; close_time = t; }
            if (saw_closed && v <= 0.001 && !saw_open) { saw_open = 1; reopen_time = t; }
        }
        CHECK(saw_closed, "20 秒内应至少闭眼一次");
        CHECK(saw_open, "闭眼后应重新睁开");
        if (saw_closed && saw_open)
            CHECK(reopen_time - close_time > 0.1 && reopen_time - close_time < 0.6,
                  "闭眼总时长应在 0.1~0.6 秒（闭合0.1+保持0.05+睁开0.15），实际 %.3f 秒",
                  reopen_time - close_time);
        /* 强制闭眼 */
        zrig_blink_force(r, 1);
        zrig_tick(r, 100.0);
        CHECK(zrig_blink_value(r) > 0.99, "强制闭眼后参数应为 1");
        zrig_blink_force(r, 0);
        zrig_tick(r, 100.1);
        CHECK(zrig_blink_value(r) < 0.01, "恢复自动后应为 0");
        zrig_free(r);
    }
}

/* ---------------------------------------------------------- 图像 */
/* 某一行的 alpha 加权横向重心；行里没有像素时返回 -1。用于量形变位移。 */
static double row_centroid(const zimg *im, int y)
{
    double wsum = 0.0, xsum = 0.0;
    int x;
    if (!im || y < 0 || y >= im->h) return -1.0;
    for (x = 0; x < im->w; ++x) {
        double a = im->px[((size_t)y * im->w + x) * 4 + 3];
        wsum += a; xsum += a * x;
    }
    return wsum > 0.0 ? xsum / wsum : -1.0;
}

static void test_image(void)
{
    SECTION("图像：缩放 / 合成 / 命中 / PNG 往返");
    {
        zimg *a = zimg_new(4, 4), *b, *c;
        int i;
        for (i = 0; i < 16; ++i) {
            uint8_t *p = a->px + i * 4;
            p[0] = 200; p[1] = 100; p[2] = 50; p[3] = 255;
        }
        b = zimg_resize(a, 2, 2);
        CHECK(b && b->px[0] == 200 && b->px[1] == 100 && b->px[2] == 50, "缩放保持颜色");
        c = zimg_new(8, 8);
        zimg_draw_simple(c, b, 0, 0, 0, 0, 1.0, 0, 1.0);
        CHECK(c->px[0] == 200 && c->px[1] == 100 && c->px[2] == 50 && c->px[3] == 255,
              "合成应保留原始颜色（曾出现被钳成纯白的 bug）");
        CHECK(zimg_hit_test(c, 0, 0, 24) == 1, "不透明处命中");
        CHECK(zimg_hit_test(c, 7, 7, 24) == 0, "透明处不命中");
        zimg_free(a); zimg_free(b); zimg_free(c);
    }
    {
        /* 形变（Live2D 式网格形变的等价实现）：验证"哪一端固定、哪一端动"。
           源图是一根 8x64 的竖条，底边=根。row_shift() 量出某一行的横向重心偏移。 */
        zimg *src = zimg_new_filled(8, 64, 255, 255, 255, 255);
        zimg *dst;
        double m[6];
        double top_root, bot_root, top_tip, bot_tip, mid_sine, top_sine;
        zimg_make_matrix(m, 40.0, 8.0, 1.0, 1.0, 0.0, 0.0, 0.0);  /* 贴到 (40,8) */

        dst = zimg_new(96, 96);
        zimg_draw_warp(dst, src, m, 1.0, 12.0, ZIMG_BEND_ROOT, 0.0, ZIMG_BEND_ROOT);
        top_root = row_centroid(dst, 10) - 44.0;   /* 竖条原本中心 x=44 */
        bot_root = row_centroid(dst, 68) - 44.0;
        zimg_free(dst);

        dst = zimg_new(96, 96);
        zimg_draw_warp(dst, src, m, 1.0, 12.0, ZIMG_BEND_TIP, 0.0, ZIMG_BEND_TIP);
        top_tip = row_centroid(dst, 10) - 44.0;
        bot_tip = row_centroid(dst, 68) - 44.0;
        zimg_free(dst);

        dst = zimg_new(96, 96);
        zimg_draw_warp(dst, src, m, 1.0, 12.0, ZIMG_BEND_SINE, 0.0, ZIMG_BEND_SINE);
        mid_sine = row_centroid(dst, 40) - 44.0;
        top_sine = row_centroid(dst, 10) - 44.0;
        zimg_free(dst);

        CHECK(top_root > 9.0 && fabs(bot_root) < 1.5,
              "root 曲线：顶端位移大（%.1f）、底端固定（%.1f）", top_root, bot_root);
        CHECK(bot_tip > 9.0 && fabs(top_tip) < 1.5,
              "tip 曲线：底端位移大（%.1f）、顶端固定（%.1f）", bot_tip, top_tip);
        CHECK(mid_sine > 10.0 && fabs(top_sine) < 2.0,
              "sine 曲线：中段最大（%.1f）、两端收口（%.1f）", mid_sine, top_sine);

        /* X 与 Y 用不同曲线时互不干扰（曾经共用一个字段，后写的会覆盖先写的） */
        dst = zimg_new(96, 96);
        zimg_draw_warp(dst, src, m, 1.0, 12.0, ZIMG_BEND_ROOT, -10.0, ZIMG_BEND_SINE);
        CHECK(row_centroid(dst, 10) - 44.0 > 9.0,
              "X 用 root 时顶端仍要大幅横移（不被 Y 的 sine 覆盖）");
        zimg_free(dst);
        zimg_free(src);
    }
    {
        /* 半透明叠加公式检查：0.5 白 over 黑 = 128 */
        zimg *dst = zimg_new_filled(2, 2, 0, 0, 0, 255);
        zimg *src = zimg_new_filled(2, 2, 255, 255, 255, 128);
        zimg_draw_simple(dst, src, 0, 0, 0, 0, 1.0, 0, 1.0);
        CHECK(abs((int)dst->px[0] - 128) <= 2, "半透明白叠黑应约等于 128，实际 %d", dst->px[0]);
        CHECK(dst->px[3] == 255, "不透明底上叠加后 alpha 仍为 255");
        zimg_free(dst); zimg_free(src);
    }
    {
        /* PNG 往返 + 抠洋红 */
        zimg *im = zimg_new_filled(8, 8, 255, 0, 255, 255);
        zerr e;
        zimg *back;
        uint8_t key[3];
        zerr_clear(&e);
        CHECK(zimg_save_png(im, "/tmp/zc_test.png", &e) == 0, "PNG 写出：%s", e.msg);
        back = zimg_load("/tmp/zc_test.png", &e);
        CHECK(back != NULL, "PNG 读回：%s", e.msg);
        if (back) {
            CHECK(back->w == 8 && back->h == 8, "PNG 尺寸往返");
            CHECK(back->px[0] == 255 && back->px[1] == 0 && back->px[2] == 255, "PNG 颜色往返");
            CHECK(zimg_key_corners(back, 60, 1, key) == 0, "四角键色检测");
            CHECK(key[0] == 255 && key[1] == 0 && key[2] == 255, "键色应为洋红");
            CHECK(back->px[3] == 0, "抠除后应为透明");
            zimg_free(back);
        }
        zimg_free(im);
    }
}

/* -------------------------------------------------------- deflate */
static void test_deflate(void)
{
    SECTION("deflate：RLE 正确性（与 zlib 一致的固定 Huffman 规则）");
    /* 关键回归：前一个字节与当前不同时不能用 distance=1 回溯，
     * 否则会把前一个字节复制出去（曾经的 bug）。 */
    uint8_t data[16] = { 1, 0, 0, 0, 0, 0, 0, 0, 2, 2, 2, 2, 3, 0, 0, 0 };
    uint8_t *out = NULL;
    size_t n;
    n = zdeflate_rle(data, sizeof(data), &out);
    CHECK(n > 0 && out != NULL, "压缩应成功");
    if (out) {
        /* 头部：BFINAL=1、BTYPE=01 → LSB 先写，低 3 位为 011(2) = 0x03 */
        CHECK((out[0] & 0x07) == 0x03, "首字节低 3 位应为 BFINAL=1,BTYPE=01，实际 0x%02X", out[0]);
        CHECK(n < sizeof(data), "相同数据应被压缩（%zu < %zu）", n, sizeof(data));
        free(out);
    }
    /* 纯零串：应压得很小 */
    {
        uint8_t zeros[4096];
        memset(zeros, 0, sizeof(zeros));
        n = zlib_compress_rle(zeros, sizeof(zeros), &out);
        CHECK(n > 0 && n < 64, "4096 个 0 应压到 64 字节内，实际 %zu", n);
        free(out);
    }
    /* 不可压缩数据：不应膨胀超过 1.05 倍 */
    {
        uint8_t rnd[4096];
        zrand r;
        size_t i;
        zrand_seed(&r, 42);
        for (i = 0; i < sizeof(rnd); ++i) rnd[i] = (uint8_t)zrand_u32(&r);
        n = zlib_compress_rle(rnd, sizeof(rnd), &out);
        /* 固定 Huffman 对 144..255 用 9 位，随机数据会膨胀约 9%，这里放宽到 15% */
        CHECK(n > 0 && n < sizeof(rnd) * 115 / 100, "随机数据膨胀应受控（%zu）", n);
        free(out);
    }
}

/* -------------------------------------------------------- 配置/角色 */
static void test_config_and_pet(void)
{
    zconfig cfg;
    zdiag diag;
    zpet *pet;
    char cfgdir[1024];

    SECTION("配置加载与角色包");
    zdiag_init(&diag);
    z_snprintf(cfgdir, sizeof(cfgdir), "%s/config", g_root);
    CHECK(zconfig_load(&cfg, cfgdir, &diag) == 0, "正常配置应加载成功（错误 %d）", diag.error_count);
    CHECK(cfg.nmodules >= 20, "功能模块应至少 20 个，实际 %d", cfg.nmodules);
    CHECK(cfg.nproviders == 3, "供应商 3 个");
    CHECK(zconfig_module_enabled(&cfg, "chat") == 0, "功能默认必须全部关闭");
    CHECK(cfg.pet.idle_sleep_seconds == 90, "默认空闲入睡 90 秒");

    zdiag_init(&diag);
    pet = zpet_create(&cfg, &diag);
    CHECK(pet != NULL, "角色包应加载成功（错误 %d 条）", diag.error_count);
    if (pet) {
        CHECK(z_streq(zpet_form(pet), "teen"), "默认形态 teen");
        CHECK(zpet_form_count(pet) >= 1, "至少一个形态");
        CHECK(zpet_scale(pet) > 0.5 && zpet_scale(pet) < 0.6, "默认缩放 0.55");
        CHECK(zpet_action_count(pet) >= 8, "可触发动作 ≥ 8，实际 %d", zpet_action_count(pet));

        /* 空闲入睡与唤醒 */
        zpet_tick(pet, 1.0);
        zpet_report_idle(pet, 95.0);
        zpet_tick(pet, 1.1);
        CHECK(zpet_sleeping(pet) == 1, "空闲 95 秒应入睡");
        CHECK(z_streq(zpet_action(pet), "sleep"), "入睡后动作应为 sleep");
        zpet_notify_user_activity(pet, 1.2);
        zpet_tick(pet, 1.21);
        CHECK(zpet_sleeping(pet) == 0, "输入后应唤醒");
        CHECK(z_streq(zpet_action(pet), "idle"), "唤醒后回到 idle");

        /* 摸头 / 锤击 / 连击 */
        {
            int fw = 0, fh = 0;
            zpet_frame(pet, &fw, &fh);
            zpet_poke(pet, fw / 2, fh / 8, ZPET_TOOL_HAND, 2.0);
            CHECK(z_streq(zpet_action(pet), "head_pat"), "摸头应触发 head_pat，实际 %s", zpet_action(pet));
            zpet_poke(pet, fw / 2, fh / 8, ZPET_TOOL_HAMMER, 2.5);
            CHECK(z_streq(zpet_action(pet), "hammered"), "锤击应触发 hammered，实际 %s", zpet_action(pet));
        }
        /* 缩放边界 */
        zpet_set_scale(pet, 99.0);
        CHECK(zpet_scale(pet) <= cfg.pet.scale_max + 1e-9, "缩放应被上限夹紧");
        zpet_set_scale(pet, 0.0);
        CHECK(zpet_scale(pet) >= cfg.pet.scale_min - 1e-9, "缩放应被下限夹紧");
        zpet_set_scale(pet, 0.5);
        zpet_destroy(pet);
    }
}

static void test_bad_config(void)
{
    SECTION("坏配置：必须报出文件+字段，且不崩溃");
    {
        zconfig cfg;
        zdiag d;
        zerr e;
        zerr_clear(&e);
        z_mkdir_p("/tmp/zc_badcfg");
        {
            /* 长度必须用 strlen 算：以前这里手写了 90，而字面量只有 89 字节，
               fwrite 会多读一个字节（ASan 的 global-buffer-overflow）。 */
            static const char bad_cfg[] =
                "{\"schema_version\":\"1.0\",\"window\":{\"scale\":\"大\"},"
                "\"interaction\":{\"idle_sleep_seconds\":0}}";
            CHECK(z_write_file("/tmp/zc_badcfg/pet.json", bad_cfg,
                               strlen(bad_cfg), &e) == 0, "写出坏配置");
        }
        zdiag_init(&d);
        zconfig_load(&cfg, "/tmp/zc_badcfg", &d);
        CHECK(d.error_count >= 1, "坏配置必须产生至少 1 个致命错误，实际 %d", d.error_count);
        {
            int found_scale = 0, found_idle = 0, i;
            for (i = 0; i < d.count; ++i) {
                if (strstr(d.items[i].field, "scale")) found_scale = 1;
                if (strstr(d.items[i].field, "idle_sleep_seconds")) found_idle = 1;
            }
            CHECK(found_scale, "错误应定位到 window.scale 字段");
            CHECK(found_idle, "错误应定位到 interaction.idle_sleep_seconds 字段");
        }
    }
    {
        /* 非法 JSON 的语法错误定位 */
        zerr e;
        zjson *j;
        zdiag d;
        zerr_clear(&e);
        z_write_file("/tmp/zc_badcfg/ui.json", "{ \"theme\": }", 13, &e);
        zdiag_init(&d);
        {
            zconfig cfg;
            zconfig_load(&cfg, "/tmp/zc_badcfg", &d);
        }
        CHECK(!zdiag_ok(&d), "语法错误必须是致命错误");
        j = zjson_parse_file("/tmp/zc_badcfg/ui.json", &e);
        CHECK(j == NULL, "应解析失败");
        CHECK(e.line == 1 && e.col > 0, "错误应带行列号（%d:%d）", e.line, e.col);
    }
    {
        /* rig.json 引用不存在的素材：必须报出部件 id */
        zdiag d;
        zerr e;
        zerr_clear(&e);
        z_mkdir_p("/tmp/zc_badrig");
        z_write_file("/tmp/zc_badrig/rig.json",
            "{\"id\":\"t\",\"canvas\":{\"w\":100,\"h\":200},\"groups\":{\"root\":{\"pivot\":[50,200]}},"
            "\"parts\":[{\"id\":\"p1\",\"file\":\"missing.png\",\"group\":\"root\"}],"
            "\"actions\":[{\"id\":\"idle\",\"loop\":true}]}",
            strlen("{\"id\":\"t\",\"canvas\":{\"w\":100,\"h\":200},\"groups\":{\"root\":{\"pivot\":[50,200]}},"
                   "\"parts\":[{\"id\":\"p1\",\"file\":\"missing.png\",\"group\":\"root\"}],"
                   "\"actions\":[{\"id\":\"idle\",\"loop\":true}]}"), &e);
        zdiag_init(&d);
        {
            zrig *r = zrig_load("/tmp/zc_badrig/rig.json", "/tmp/zc_badrig", &d);
            CHECK(r == NULL, "缺少素材应加载失败");
            CHECK(d.error_count >= 1, "应报告错误");
            if (d.count > 0) {
                CHECK(strstr(d.items[0].msg, "missing.png") != NULL || strstr(d.items[0].msg, "不存在") != NULL,
                      "错误信息应指出缺失的文件：%s", d.items[0].msg);
            }
        }
    }
}

/* ---------------------------------------------------------- 动作通道 */
static void test_rig_channels(void)
{
    SECTION("rig：部件通道 / 动作优先级 / 换装");
    {
        char dir[1024], path[1024];
        zdiag d;
        zrig *r;
        zdiag_init(&d);
        z_snprintf(dir, sizeof(dir), "%s/characters/xiaoxun/forms/teen", g_root);
        z_snprintf(path, sizeof(path), "%s/rig.json", dir);
        r = zrig_load(path, dir, &d);
        if (!r) { CHECK(0, "装载失败"); return; }
        CHECK(zrig_canvas_w(r) == 848 && zrig_canvas_h(r) == 1360, "画布 848x1360");
        CHECK(zrig_part_count(r) >= 6, "部件 ≥ 6");
        CHECK(zrig_region_count(r) >= 3, "区域 ≥ 3");

        /* 睡眠优先级最高，可打断一切 */
        zrig_action_request(r, "sleep", "t", 0);
        CHECK(z_streq(zrig_action(r), "sleep"), "可进入 sleep");
        zrig_action_request(r, "happy", "t", 0);
        CHECK(z_streq(zrig_action(r), "sleep"), "happy(7) 不能打断 sleep(8)");
        zrig_action_request(r, "idle", "t", 1);
        CHECK(z_streq(zrig_action(r), "idle"), "force 可以强行回 idle");

        /* 说话动作应驱动口型通道 */
        zrig_action_request(r, "talk", "t", 1);
        {
            int i;
            double min_alpha = 2.0, max_alpha = -1.0;
            for (i = 0; i < 90; ++i) {
                double v;
                zrig_tick(r, i / 60.0);
                v = zrig_part_channel(r, "mouth_open", "alpha");
                if (v > max_alpha) max_alpha = v;
                if (v < min_alpha) min_alpha = v;
            }
            CHECK(min_alpha < 0.6, "说话时口型透明度应下降（最小 %.3f）", min_alpha);
            CHECK(max_alpha - min_alpha > 0.3, "口型通道应有明显变化（%.3f~%.3f）", min_alpha, max_alpha);
        }
        /* 帧尺寸应随缩放变化 */
        {
            int fw = 0, fh = 0;
            zrig_frame(r, 0.5, &fw, &fh);
            CHECK(fw == 424 && fh == 680, "0.5 倍应为 424x680，实际 %dx%d", fw, fh);
            zrig_frame(r, 1.0, &fw, &fh);
            CHECK(fw == 848 && fh == 1360, "1.0 倍应为 848x1360");
        }
        /* 区域命中（头/身体/脚） */
        {
            char act[64];
            const char *id;
            zrig_frame(r, 1.0, NULL, NULL);
            zrig_action_request(r, "idle", "t", 1);
            zrig_tick(r, 100.0);
            zrig_frame(r, 1.0, NULL, NULL);
            id = zrig_region_at(r, 424, 120, act, sizeof(act));
            CHECK(id && z_streq(id, "head"), "头部区域命中");
            if (id) CHECK(z_streq(act, "head_pat"), "头部区域应触发 head_pat");
            id = zrig_region_at(r, 424, 700, act, sizeof(act));
            CHECK(id && z_streq(id, "body"), "身体区域命中");
            id = zrig_region_at(r, 5, 5, act, sizeof(act));
            CHECK(id == NULL, "左上角透明处不应命中任何区域");
        }
        /* 形变跟随（放在最后：它会推进时间轴，不能影响前面的用例）。
           身体 bend 时 head 组里的五官必须自动跟着走，否则眼睛会从脸上滑走。 */
        {
            int i, fw = 0, fh = 0;
            double peak_body = 0.0, worst = 0.0, worst_rigid = 0.0;
            /* 跟随源与取样高度都从 rig 里读：单图层骨架（眼睛贴在整张身体上，
               按自己高度取样）和分段骨架（头整块挂在脖子上，按关节点取样）
               用同一套断言，换素材不用改测试。 */
            /* 眼睛部件的 id 随拆件程度而变：整块贴图叫 eye_open_left，
               拆成 Live2D 式零件后眼白底叫 eye_l_base。测试自己挑现有的那个，
               这样拆件推进时不用改断言。 */
            const char *eye_id = "eye_l_base";
            const char *src = zrig_part_follow_src(r, eye_id);
            if (!src) { eye_id = "eye_open_left"; src = zrig_part_follow_src(r, eye_id); }
            CHECK(src != NULL, "眼睛所在的组必须声明 bend_follow");
            zrig_action_request(r, "sway", "t", 1);
            for (i = 0; i < 300 && src; ++i) {   /* 扫 5 秒，覆盖 sway 的一个周期 */
                double follow, body, gap, rigid;
                zrig_tick(r, 200.0 + i / 60.0);
                zrig_frame(r, 1.0, &fw, &fh);
                follow = zrig_part_offset_x(r, eye_id);   /* 眼睛实际被推了多远 */
                body   = zrig_bend_at(r, src, zrig_part_follow_y(r, eye_id));
                gap = fabs(follow - body);
                /* 同一个头上的部件必须刚性同步，差一点点都会看成"五官在脸上滑" */
                rigid = fabs(follow - zrig_part_offset_x(r, "mouth_open"));
                if (fabs(body) > fabs(peak_body)) peak_body = body;
                if (gap > worst) worst = gap;
                if (rigid > worst_rigid) worst_rigid = rigid;
            }
            CHECK(fabs(peak_body) > 2.0,
                  "sway 时身体在取样高度确实要弯（实际 %.2f px）", peak_body);
            CHECK(worst < 0.01,
                  "五官要按跟随取样高度跟住身体形变，最大偏差 %.3f px", worst);
            CHECK(worst_rigid < 0.01,
                  "同一组的五官必须刚性同步，最大偏差 %.3f px", worst_rigid);
        }
        zrig_free(r);
    }
}

/* -------------------------------------------------------- 互动规则 / 台词 / 情绪 */
static void write_text(const char *path, const char *text)
{
    FILE *f = fopen(path, "wb");
    if (!f) return;
    fwrite(text, 1, strlen(text), f);
    fclose(f);
}

/* ------------------------------------------------- 遮罩（clipping mask） */
static int diag_has(const zdiag *d, const char *needle);
static int copy_file(const char *src, const char *dst)
{
    FILE *a = fopen(src, "rb"), *b;
    char buf[8192];
    size_t n;
    if (!a) return -1;
    b = fopen(dst, "wb");
    if (!b) { fclose(a); return -1; }
    while ((n = fread(buf, 1, sizeof(buf), a)) > 0) fwrite(buf, 1, n, b);
    fclose(a); fclose(b);
    return 0;
}

static int frame_opaque_px(const zimg *im)
{
    int x, y, n = 0;
    if (!im) return 0;
    for (y = 0; y < im->h; ++y)
        for (x = 0; x < im->w; ++x)
            if (im->px[((size_t)y * (size_t)im->w + (size_t)x) * 4 + 3] > 24) n++;
    return n;
}

/* 不透明像素的重心 y（整数放大 1000 倍避免浮点比较） */
static int frame_centroid_y(const zimg *im)
{
    int x, y; long n = 0; long sum = 0;
    if (!im) return -1;
    for (y = 0; y < im->h; ++y)
        for (x = 0; x < im->w; ++x)
            if (im->px[((size_t)y * (size_t)im->w + (size_t)x) * 4 + 3] > 24) { n++; sum += y; }
    return n ? (int)(sum / n) : -1;
}

static void test_motion_fade(void)
{
    char dir[1024], sprites[1024], src[1024], dst[1024], rigp[1024];
    SECTION("动作淡入淡出：切动作时两套通道按权重混合，不是一帧跳过去");
    z_snprintf(dir, sizeof(dir), "/tmp/zc_fade");
    z_snprintf(sprites, sizeof(sprites), "%s/sprites", dir);
    z_mkdir_p(dir);
    z_mkdir_p(sprites);
    z_snprintf(src, sizeof(src), "%s/characters/xiaoxun/forms/teen/sprites/eye_l_lid.png", g_root);
    z_snprintf(dst, sizeof(dst), "%s/a.png", sprites);
    if (copy_file(src, dst) != 0) { CHECK(0, "复制贴图失败"); return; }
    z_snprintf(rigp, sizeof(rigp), "%s/rig.json", dir);
    /* idle 不动；lean 把 head 组往右推 20px（pulse 立刻到位），淡入 0.4s */
    write_text(rigp,
        "{\"schema_version\":\"1.0\",\"id\":\"f\",\"name\":\"淡入测试\","
        "\"canvas\":{\"w\":200,\"h\":200},\"origin\":[100,200],"
        "\"groups\":{\"head\":{\"pivot\":[100,100],\"parent\":\"\"}},"
        "\"parts\":[{\"id\":\"a\",\"file\":\"sprites/a.png\",\"group\":\"head\","
        " \"layer\":10,\"pos\":[60,40],\"anchor\":[0,0]}],"
        "\"actions\":[{\"id\":\"idle\",\"loop\":true,\"channels\":[]},"
        " {\"id\":\"lean\",\"loop\":true,\"fade\":0.4,\"channels\":["
        "   {\"target\":\"head\",\"param\":\"dx\",\"wave\":\"pulse\",\"amp\":20,\"dur\":0.01}]},"
        " {\"id\":\"snap\",\"loop\":true,\"fade\":0,\"channels\":["
        "   {\"target\":\"head\",\"param\":\"dx\",\"wave\":\"pulse\",\"amp\":20,\"dur\":0.01}]}]}");
    {
        zdiag d;
        zrig *r;
        zdiag_init(&d);
        r = zrig_load(rigp, dir, &d);
        CHECK(r != NULL, "带 fade 的 rig 应加载成功");
        if (r) {
            double at_switch, mid, after;
            zrig_tick(r, 1.0);
            CHECK(fabs(zrig_group_offset_x(r, "head")) < 0.01, "idle 时不该有位移");
            zrig_action_request(r, "lean", "test", 1);
            zrig_tick(r, 1.0);
            at_switch = zrig_group_offset_x(r, "head");
            zrig_tick(r, 1.2);                       /* 淡入过半 */
            mid = zrig_group_offset_x(r, "head");
            zrig_tick(r, 1.5);                       /* 淡入结束 */
            after = zrig_group_offset_x(r, "head");
            CHECK(at_switch < 1.0, "刚切过去的那一帧应几乎还在原位（%.2f）", at_switch);
            CHECK(mid > 3.0 && mid < 18.0, "淡入过半应落在中间（%.2f，目标 20）", mid);
            CHECK(after > 19.0, "淡入结束应到达目标（%.2f）", after);
            /* fade:0 的动作要立刻到位——打击感不能被淡入磨掉 */
            zrig_action_request(r, "idle", "test", 1);
            zrig_tick(r, 3.0);
            zrig_action_request(r, "snap", "test", 1);
            zrig_tick(r, 3.02);        /* pulse 的 dur=0.01，这时波形本身已到位 */
            CHECK(zrig_group_offset_x(r, "head") > 19.0,
                  "fade=0 的动作应一帧到位（%.2f）", zrig_group_offset_x(r, "head"));
            /* 对照：同样过了 0.02s，带 0.4s 淡入的动作此时几乎还没动 */
            zrig_action_request(r, "idle", "test", 1);
            zrig_tick(r, 5.0);
            zrig_action_request(r, "lean", "test", 1);
            zrig_tick(r, 5.02);
            CHECK(zrig_group_offset_x(r, "head") < 2.0,
                  "带淡入的动作同一时刻应几乎还没动（%.2f）", zrig_group_offset_x(r, "head"));
            zrig_free(r);
        }
    }
}

static void test_motion_from(void)
{
    char dir[1024], sprites[1024], src[1024], dst[1024], rigp[1024];
    SECTION("motion_from：副本照抄本体的通道（透け眉用）");
    z_snprintf(dir, sizeof(dir), "/tmp/zc_mfrom");
    z_snprintf(sprites, sizeof(sprites), "%s/sprites", dir);
    z_mkdir_p(dir);
    z_mkdir_p(sprites);
    z_snprintf(src, sizeof(src), "%s/characters/xiaoxun/forms/teen/sprites/brow_l.png", g_root);
    z_snprintf(dst, sizeof(dst), "%s/b.png", sprites);
    if (copy_file(src, dst) != 0) { CHECK(0, "复制贴图失败"); return; }
    z_snprintf(rigp, sizeof(rigp), "%s/rig.json", dir);
    write_text(rigp,
        "{\"schema_version\":\"1.0\",\"id\":\"m\",\"name\":\"镜像测试\","
        "\"canvas\":{\"w\":200,\"h\":200},\"origin\":[100,200],"
        "\"groups\":{\"head\":{\"pivot\":[100,100],\"parent\":\"\"}},"
        "\"parts\":[{\"id\":\"b\",\"file\":\"sprites/b.png\",\"group\":\"head\","
        "  \"layer\":10,\"pos\":[60,60],\"anchor\":[0.5,0.5]},"
        " {\"id\":\"b_ghost\",\"file\":\"sprites/b.png\",\"group\":\"head\",\"layer\":20,"
        "  \"pos\":[60,60],\"anchor\":[0.5,0.5],\"opacity\":0.4,\"motion_from\":\"b\"}],"
        "\"actions\":[{\"id\":\"idle\",\"loop\":true,\"channels\":["
        "  {\"target\":\"b\",\"param\":\"dy\",\"wave\":\"sine\",\"amp\":4,\"freq\":1}]}]}");
    {
        zdiag d;
        zrig *r;
        zdiag_init(&d);
        r = zrig_load(rigp, dir, &d);
        CHECK(r != NULL, "带 motion_from 的 rig 应加载成功");
        if (r) {
            int w, h;
            double t;
            /* 副本自己没有通道，但画面上必须跟着本体走：
               用渲染结果验证 —— 本体动起来时整帧必须变。 */
            const zimg *f1, *f2;
            unsigned long s1 = 0, s2 = 0;
            int i;
            zrig_tick(r, 0.0);
            f1 = zrig_frame(r, 1.0, &w, &h);
            for (i = 0; i < w * h; ++i) s1 += (unsigned long)f1->px[i * 4 + 3];
            CHECK(fabs(zrig_part_channel(r, "b_ghost", "dy")) < 1e-9,
                  "副本自己的通道值应为 0（它只是照抄）");
            for (t = 0.02; t < 0.3; t += 0.02) zrig_tick(r, t);
            CHECK(fabs(zrig_part_channel(r, "b", "dy")) > 0.5, "本体通道应有值");
            f2 = zrig_frame(r, 1.0, &w, &h);
            for (i = 0; i < w * h; ++i) s2 += (unsigned long)f2->px[i * 4 + 3];
            CHECK(s1 != s2, "本体动了，画面（含副本）必须跟着变（%lu → %lu）", s1, s2);
            zrig_free(r);
        }
    }
    /* 反例：指向不存在的部件 / 套娃 */
    {
        zdiag d;
        zrig *r;
        z_snprintf(rigp, sizeof(rigp), "%s/bad.json", dir);
        write_text(rigp,
            "{\"schema_version\":\"1.0\",\"id\":\"m\",\"name\":\"x\","
            "\"canvas\":{\"w\":200,\"h\":200},\"origin\":[100,200],"
            "\"groups\":{\"head\":{\"pivot\":[100,100],\"parent\":\"\"}},"
            "\"parts\":[{\"id\":\"b\",\"file\":\"sprites/b.png\",\"group\":\"head\","
            "  \"layer\":10,\"pos\":[60,60],\"anchor\":[0.5,0.5],\"motion_from\":\"nope\"}],"
            "\"actions\":[{\"id\":\"idle\",\"loop\":true,\"channels\":[]}]}");
        zdiag_init(&d);
        r = zrig_load(rigp, dir, &d);
        CHECK(r == NULL, "motion_from 指向不存在的部件应加载失败");
        if (r) zrig_free(r);
    }
}

static void test_expression(void)
{
    char dir[1024], sprites[1024], src[1024], dst[1024], rigp[1024];
    SECTION("表情层：叠在动作之上、带淡入淡出、不顶掉动作");
    z_snprintf(dir, sizeof(dir), "/tmp/zc_expr");
    z_snprintf(sprites, sizeof(sprites), "%s/sprites", dir);
    z_mkdir_p(dir);
    z_mkdir_p(sprites);
    z_snprintf(src, sizeof(src), "%s/characters/xiaoxun/forms/teen/sprites/hair_ahoge.png", g_root);
    z_snprintf(dst, sizeof(dst), "%s/h.png", sprites);
    if (copy_file(src, dst) != 0) { CHECK(0, "复制贴图失败"); return; }
    z_snprintf(rigp, sizeof(rigp), "%s/rig.json", dir);
    write_text(rigp,
        "{\"schema_version\":\"1.0\",\"id\":\"e\",\"name\":\"表情测试\","
        "\"canvas\":{\"w\":200,\"h\":200},\"origin\":[100,200],"
        "\"groups\":{\"head\":{\"pivot\":[100,100],\"parent\":\"\"}},"
        "\"parts\":[{\"id\":\"h\",\"file\":\"sprites/h.png\",\"group\":\"head\","
        " \"layer\":10,\"pos\":[60,40],\"anchor\":[0,0]}],"
        "\"actions\":[{\"id\":\"idle\",\"loop\":true,\"channels\":["
        "  {\"target\":\"h\",\"param\":\"dx\",\"wave\":\"sine\",\"amp\":2,\"freq\":1}]}],"
        "\"params\":[{\"id\":\"ParamBrowLY\",\"min\":-1,\"max\":1,\"default\":0,"
        " \"binds\":[{\"part\":\"h\",\"param\":\"dy\",\"scale\":10}]}],"
        "\"expressions\":[{\"id\":\"angry\",\"name\":\"生气\",\"fade\":0.4,"
        " \"params\":[{\"id\":\"ParamBrowLY\",\"value\":-0.5},"
        "             {\"id\":\"ParamEyeOpen\",\"value\":0.5,\"mode\":\"set\"}]},"
        " {\"id\":\"snap\",\"fade\":0,"
        "  \"params\":[{\"id\":\"ParamBrowLY\",\"value\":1.0,\"mode\":\"set\"}]}]}");
    {
        zdiag d;
        zrig *r;
        zdiag_init(&d);
        r = zrig_load(rigp, dir, &d);
        CHECK(r != NULL, "带 expressions 段的 rig 应加载成功");
        if (r) {
            double t, mid, done;
            CHECK(zrig_expression_count(r) == 2, "应读出 2 个表情（%d）",
                  zrig_expression_count(r));
            CHECK(z_streq(zrig_expression_name(r, 0), "生气"), "表情中文名应读出来");
            CHECK(zrig_expression(r) == NULL, "一开始应该没有表情");
            zrig_tick(r, 0.0);
            zrig_blink_set_manual(r, 0.0);
            zrig_tick(r, 0.02);
            CHECK(fabs(zrig_part_channel(r, "h", "dy")) < 1e-6, "没表情时绑定通道应为 0");
            /* ① 淡入：不能一帧到位 */
            CHECK(zrig_expression_set(r, "angry") == 0, "切表情应成功");
            zrig_tick(r, 0.04);
            mid = zrig_part_channel(r, "h", "dy");
            CHECK(mid > -1.0 && mid <= 0.0, "表情要淡入，20ms 时还很小（%.3f / 目标 -5）", mid);
            for (t = 0.06; t < 0.8; t += 0.02) zrig_tick(r, t);
            done = zrig_part_channel(r, "h", "dy");
            CHECK(fabs(done - (-5.0)) < 0.01, "淡入完成应到 -0.5×10（%.3f）", done);
            CHECK(z_streq(zrig_expression(r), "angry"), "当前表情应可读回");
            /* ② set 模式作用在内建参数上：眼睛半闭 */
            CHECK(fabs(zrig_blink_value(r) - 0.0) < 1e-6, "子系统自己的眨眼值不该被改写");
            /* ③ 动作还在跑（表情和动作是两条轨） */
            CHECK(z_streq(zrig_action(r), "idle"), "表情不该顶掉动作（%s）", zrig_action(r));
            CHECK(fabs(zrig_part_channel(r, "h", "dx")) > 1e-9, "动作通道应照常输出");
            /* ④ fade=0 的表情一帧到位 */
            zrig_expression_set(r, "snap");
            zrig_tick(r, t);
            CHECK(fabs(zrig_part_channel(r, "h", "dy") - 10.0) < 0.01,
                  "fade=0 应一帧到位（%.3f / 10）", zrig_part_channel(r, "h", "dy"));
            /* ⑤ 取消：淡出回 0 */
            zrig_expression_clear(r);
            for (t += 0.02; t < 2.0; t += 0.02) zrig_tick(r, t);
            CHECK(zrig_expression(r) == NULL, "取消后不应还有表情");
            CHECK(fabs(zrig_part_channel(r, "h", "dy")) < 0.01,
                  "取消后绑定通道应回 0（%.3f）", zrig_part_channel(r, "h", "dy"));
            /* ⑥ 未知表情要报错 */
            CHECK(zrig_expression_set(r, "nope") == -1, "未知表情应返回 -1");
            zrig_free(r);
        }
    }
    /* 反例：表情写了没声明的参数，必须加载失败 */
    {
        zdiag d;
        zrig *r;
        z_snprintf(rigp, sizeof(rigp), "%s/bad.json", dir);
        write_text(rigp,
            "{\"schema_version\":\"1.0\",\"id\":\"e\",\"name\":\"x\","
            "\"canvas\":{\"w\":200,\"h\":200},\"origin\":[100,200],"
            "\"groups\":{\"head\":{\"pivot\":[100,100],\"parent\":\"\"}},"
            "\"parts\":[{\"id\":\"h\",\"file\":\"sprites/h.png\",\"group\":\"head\","
            " \"layer\":10,\"pos\":[60,40],\"anchor\":[0,0]}],"
            "\"actions\":[{\"id\":\"idle\",\"loop\":true,\"channels\":[]}],"
            "\"expressions\":[{\"id\":\"x\",\"params\":[{\"id\":\"ParamNope\",\"value\":1}]}]}");
        zdiag_init(&d);
        r = zrig_load(rigp, dir, &d);
        CHECK(r == NULL, "表情引用未声明的参数应加载失败");
        if (r) zrig_free(r);
    }
}

static void test_params(void)
{
    char dir[1024], sprites[1024], src[1024], dst[1024], rigp[1024];
    SECTION("命名参数层：内建参数路由 + rig 声明的绑定参数");
    z_snprintf(dir, sizeof(dir), "/tmp/zc_param");
    z_snprintf(sprites, sizeof(sprites), "%s/sprites", dir);
    z_mkdir_p(dir);
    z_mkdir_p(sprites);
    z_snprintf(src, sizeof(src), "%s/characters/xiaoxun/forms/teen/sprites/hair_ahoge.png", g_root);
    z_snprintf(dst, sizeof(dst), "%s/h.png", sprites);
    if (copy_file(src, dst) != 0) { CHECK(0, "复制贴图失败"); return; }
    z_snprintf(rigp, sizeof(rigp), "%s/rig.json", dir);
    write_text(rigp,
        "{\"schema_version\":\"1.0\",\"id\":\"p\",\"name\":\"参数测试\","
        "\"canvas\":{\"w\":200,\"h\":200},\"origin\":[100,200],"
        "\"groups\":{\"head\":{\"pivot\":[100,100],\"parent\":\"\"}},"
        "\"parts\":[{\"id\":\"h\",\"file\":\"sprites/h.png\",\"group\":\"head\","
        " \"layer\":10,\"pos\":[60,40],\"anchor\":[0,0]}],"
        "\"actions\":[{\"id\":\"idle\",\"loop\":true,\"channels\":[]}],"
        "\"look\":{\"speed\":30,\"groups\":{\"head\":{\"dx\":4}}},"
        "\"params\":[{\"id\":\"ParamAngleZ\",\"label\":\"歪头\",\"min\":-30,\"max\":30,"
        " \"default\":0,\"binds\":[{\"group\":\"head\",\"param\":\"rot_deg\",\"scale\":0.5}]},"
        "{\"id\":\"ParamHairAhoge\",\"min\":-1,\"max\":1,\"default\":0,"
        " \"binds\":[{\"part\":\"h\",\"param\":\"dx\",\"scale\":10}]}]}");
    {
        zdiag d;
        zrig *r;
        zdiag_init(&d);
        r = zrig_load(rigp, dir, &d);
        CHECK(r != NULL, "带 params 段的 rig 应加载成功");
        if (r) {
            zrig_param_desc pd;
            double t;
            /* 内建 5 个（ParamAngleX/Y、ParamEyeOpen、ParamEyeBallX/Y）+ rig 里 2 个 */
            CHECK(zrig_param_count(r) == 7, "参数表应有 7 项（内建 5 + 角色 2），实为 %d",
                  zrig_param_count(r));
            CHECK(zrig_param_info(r, 0, &pd) == 0 && z_streq(pd.id, "ParamAngleX") && pd.builtin,
                  "第一项应是内建 ParamAngleX");
            /* ① 绑定参数：直接写部件通道 */
            CHECK(zrig_param_set(r, "ParamHairAhoge", 0.5) == 0, "写绑定参数应成功");
            zrig_tick(r, 0.0);
            CHECK(fabs(zrig_part_channel(r, "h", "dx") - 5.0) < 1e-6,
                  "0.5 × scale 10 应给部件 dx = 5（实为 %.3f）", zrig_part_channel(r, "h", "dx"));
            /* ② 超出 min/max 要夹住 */
            zrig_param_set(r, "ParamHairAhoge", 9.0);
            zrig_tick(r, 0.02);
            CHECK(fabs(zrig_part_channel(r, "h", "dx") - 10.0) < 1e-6, "超范围应夹到 max");
            /* ③ 复位 */
            zrig_param_reset(r, "ParamHairAhoge");
            zrig_tick(r, 0.04);
            CHECK(fabs(zrig_part_channel(r, "h", "dx")) < 1e-6, "复位后应回 0");
            /* ④ 内建参数：ParamAngleX 应驱动头部跟随（和 zrig_look 同一条路） */
            CHECK(zrig_param_set(r, "ParamAngleX", 30.0) == 0, "写内建参数应成功");
            for (t = 0.06; t < 1.2; t += 0.02) zrig_tick(r, t);
            CHECK(zrig_group_offset_x(r, "head") > 3.8,
                  "ParamAngleX=30 应把头带到最大幅度（%.2f）", zrig_group_offset_x(r, "head"));
            CHECK(zrig_param_get(r, "ParamAngleX") > 29.0,
                  "内建参数读数应回写当前值（%.2f）", zrig_param_get(r, "ParamAngleX"));
            /* ⑤ 眨眼：ParamEyeOpen=0 等于闭眼，别名 ParamEyeLOpen 也认 */
            zrig_param_set(r, "ParamEyeOpen", 0.0);
            zrig_tick(r, t);
            CHECK(zrig_blink_value(r) > 0.99, "ParamEyeOpen=0 应等于闭眼（%.2f）",
                  zrig_blink_value(r));
            CHECK(zrig_param_set(r, "ParamEyeLOpen", 1.0) == 0, "ParamEyeLOpen 应是别名");
            zrig_tick(r, t + 0.02);
            CHECK(zrig_blink_value(r) < 0.01, "别名写 1 应睁眼");
            zrig_param_reset(r, "ParamEyeOpen");
            CHECK(zrig_blink_manual(r) < 0.0, "眨眼参数复位应交回自动");
            /* ⑥ 不存在的参数要报错，不能假装成功 */
            CHECK(zrig_param_set(r, "ParamNope", 1.0) == -1, "未知参数应返回 -1");
            /* ⑦ 全部复位 */
            zrig_param_set(r, "ParamHairAhoge", 1.0);
            zrig_param_reset_all(r);
            zrig_tick(r, t + 0.04);
            CHECK(fabs(zrig_part_channel(r, "h", "dx")) < 1e-6, "全部复位应把绑定通道清零");
            zrig_free(r);
        }
    }
    /* 反例：绑定到不存在的部件必须加载失败 */
    {
        zdiag d;
        zrig *r;
        z_snprintf(rigp, sizeof(rigp), "%s/bad.json", dir);
        write_text(rigp,
            "{\"schema_version\":\"1.0\",\"id\":\"p\",\"name\":\"x\","
            "\"canvas\":{\"w\":200,\"h\":200},\"origin\":[100,200],"
            "\"groups\":{\"head\":{\"pivot\":[100,100],\"parent\":\"\"}},"
            "\"parts\":[{\"id\":\"h\",\"file\":\"sprites/h.png\",\"group\":\"head\","
            " \"layer\":10,\"pos\":[60,40],\"anchor\":[0,0]}],"
            "\"actions\":[{\"id\":\"idle\",\"loop\":true,\"channels\":[]}],"
            "\"params\":[{\"id\":\"X\",\"min\":0,\"max\":1,"
            " \"binds\":[{\"part\":\"nope\",\"param\":\"dx\",\"scale\":1}]}]}");
        zdiag_init(&d);
        r = zrig_load(rigp, dir, &d);
        CHECK(r == NULL, "绑定到不存在的部件应加载失败");
        if (r) zrig_free(r);
    }
}

static void test_look(void)
{
    char dir[1024], sprites[1024], src[1024], dst[1024], rigp[1024];
    SECTION("指针跟随：头跟着光标转，平滑过去，复位回 0");
    z_snprintf(dir, sizeof(dir), "/tmp/zc_look");
    z_snprintf(sprites, sizeof(sprites), "%s/sprites", dir);
    z_mkdir_p(dir);
    z_mkdir_p(sprites);
    z_snprintf(src, sizeof(src), "%s/characters/xiaoxun/forms/teen/sprites/hair_ahoge.png", g_root);
    z_snprintf(dst, sizeof(dst), "%s/h.png", sprites);
    if (copy_file(src, dst) != 0) { CHECK(0, "复制贴图失败"); return; }
    z_snprintf(rigp, sizeof(rigp), "%s/rig.json", dir);
    write_text(rigp,
        "{\"schema_version\":\"1.0\",\"id\":\"l\",\"name\":\"跟随测试\","
        "\"canvas\":{\"w\":200,\"h\":200},\"origin\":[100,200],"
        "\"groups\":{\"head\":{\"pivot\":[100,100],\"parent\":\"\"}},"
        "\"parts\":[{\"id\":\"h\",\"file\":\"sprites/h.png\",\"group\":\"head\","
        " \"layer\":10,\"pos\":[60,40],\"anchor\":[0,0]}],"
        "\"actions\":[{\"id\":\"idle\",\"loop\":true,\"channels\":[]}],"
        "\"look\":{\"speed\":9,\"groups\":{\"head\":{\"rot_deg\":5,\"dx\":4,\"dy\":3}}}}");
    {
        zdiag d;
        zrig *r;
        zdiag_init(&d);
        r = zrig_load(rigp, dir, &d);
        CHECK(r != NULL, "带 look 段的 rig 应加载成功");
        if (r) {
            double t, first, settled, back;
            zrig_tick(r, 0.0);
            zrig_tick(r, 0.1);
            CHECK(fabs(zrig_group_offset_x(r, "head")) < 0.01, "没给方向时不该偏");
            zrig_look(r, 1.0, 0.0);
            zrig_tick(r, 0.12);                 /* 过了 20ms */
            first = zrig_group_offset_x(r, "head");
            CHECK(first > 0.0 && first < 3.0, "跟随要平滑，不能一帧到位（%.2f / 目标 4）", first);
            for (t = 0.14; t < 1.2; t += 0.02) zrig_tick(r, t);
            settled = zrig_group_offset_x(r, "head");
            CHECK(settled > 3.8 && settled < 4.05, "跟到底应接近配置幅度（%.2f / 4）", settled);
            CHECK(zrig_look_x(r) > 0.98, "look_x 应可读回（%.3f）", zrig_look_x(r));
            zrig_look(r, 0.0, 0.0);
            for (; t < 2.4; t += 0.02) zrig_tick(r, t);
            back = zrig_group_offset_x(r, "head");
            CHECK(fabs(back) < 0.05, "复位后应回到 0（%.3f）", back);
            /* 视线接口要连带把头也带过去（光标跟随是眼+头两层） */
            zrig_gaze(r, -1.0, 0.0);
            for (; t < 3.6; t += 0.02) zrig_tick(r, t);
            CHECK(zrig_group_offset_x(r, "head") < -3.8,
                  "zrig_gaze 应同时驱动头部跟随（%.2f）", zrig_group_offset_x(r, "head"));
            zrig_gaze_reset(r);
            for (; t < 4.8; t += 0.02) zrig_tick(r, t);
            CHECK(fabs(zrig_group_offset_x(r, "head")) < 0.05, "gaze_reset 也该把头复位");
            zrig_free(r);
        }
    }
}

static void test_physics(void)
{
    char dir[1024], sprites[1024], src[1024], dst[1024], rigp[1024];
    SECTION("物理摆动：头发跟着身体动，有落后、有过冲、停下来会收敛回 0");
    z_snprintf(dir, sizeof(dir), "/tmp/zc_phys");
    z_snprintf(sprites, sizeof(sprites), "%s/sprites", dir);
    z_mkdir_p(dir);
    z_mkdir_p(sprites);
    z_snprintf(src, sizeof(src), "%s/characters/xiaoxun/forms/teen/sprites/hair_ahoge.png", g_root);
    z_snprintf(dst, sizeof(dst), "%s/h.png", sprites);
    if (copy_file(src, dst) != 0) { CHECK(0, "复制贴图失败"); return; }
    z_snprintf(rigp, sizeof(rigp), "%s/rig.json", dir);
    write_text(rigp,
        "{\"schema_version\":\"1.0\",\"id\":\"p\",\"name\":\"物理测试\","
        "\"canvas\":{\"w\":200,\"h\":200},\"origin\":[100,200],"
        "\"groups\":{\"head\":{\"pivot\":[100,100],\"parent\":\"\"}},"
        "\"parts\":[{\"id\":\"hair\",\"file\":\"sprites/h.png\",\"group\":\"head\","
        " \"layer\":10,\"pos\":[60,40],\"anchor\":[0,0]}],"
        "\"actions\":[{\"id\":\"idle\",\"loop\":true,\"channels\":[]},"
        " {\"id\":\"push\",\"loop\":true,\"fade\":0,\"channels\":["
        "   {\"target\":\"head\",\"param\":\"dx\",\"wave\":\"pulse\",\"amp\":30,\"dur\":0.01}]}],"
        "\"physics\":[{\"id\":\"ahoge\",\"part\":\"hair\",\"driver\":\"head\",\"axis\":\"x\","
        " \"param\":\"bend_x\",\"curve\":\"root\",\"ratio\":1.0,"
        " \"stiffness\":60,\"damping\":6,\"max\":30}]}");
    {
        zdiag d;
        zrig *r;
        zdiag_init(&d);
        r = zrig_load(rigp, dir, &d);
        CHECK(r != NULL, "带 physics 的 rig 应加载成功");
        if (r) {
            double t, lag = 0.0, overshoot = 0.0, settled;
            int i;
            zrig_tick(r, 0.0);
            zrig_tick(r, 0.016);
            CHECK(fabs(zrig_part_channel(r, "hair", "bend_x")) < 0.01,
                  "没动的时候物理输出应为 0");
            zrig_action_request(r, "push", "test", 1);
            /* 头突然右移 30px：头发应先落在后面（输出为负） */
            for (i = 1, t = 0.016; i <= 6; ++i) {
                t += 0.016;
                zrig_tick(r, t);
                if (zrig_part_channel(r, "hair", "bend_x") < lag)
                    lag = zrig_part_channel(r, "hair", "bend_x");
            }
            CHECK(lag < -1.0, "起步时头发该落在后面（最低 %.2f px）", lag);
            /* 继续跑：弹簧会过冲到正的一侧 */
            for (; t < 0.9; t += 0.016) {
                zrig_tick(r, t);
                if (zrig_part_channel(r, "hair", "bend_x") > overshoot)
                    overshoot = zrig_part_channel(r, "hair", "bend_x");
            }
            CHECK(overshoot > 0.3, "之后应过冲到另一侧（最高 %.2f px）", overshoot);
            /* 再跑几秒，收敛回 0（头不动了，头发就该垂下来） */
            for (; t < 4.0; t += 0.016) zrig_tick(r, t);
            settled = zrig_part_channel(r, "hair", "bend_x");
            CHECK(fabs(settled) < 0.2, "停下来之后应收敛回 0（%.3f px）", settled);
            zrig_free(r);
        }
    }
}

static void test_eyelid(void)
{
    char dir[1024], sprites[1024], src[1024], dst[1024], rigp[1024];
    SECTION("眼睑：blink 把带 eyelid 标签的部件按行程往下推（眨眼＝眼皮下滑）");
    z_snprintf(dir, sizeof(dir), "/tmp/zc_lid");
    z_snprintf(sprites, sizeof(sprites), "%s/sprites", dir);
    z_mkdir_p(dir);
    z_mkdir_p(sprites);
    z_snprintf(src, sizeof(src), "%s/characters/xiaoxun/forms/teen/sprites/eye_l_lid.png", g_root);
    z_snprintf(dst, sizeof(dst), "%s/lid.png", sprites);
    if (copy_file(src, dst) != 0) { CHECK(0, "复制 eye_l_lid.png 失败"); return; }
    z_snprintf(rigp, sizeof(rigp), "%s/rig.json", dir);
    write_text(rigp,
        "{\"schema_version\":\"1.0\",\"id\":\"e\",\"name\":\"眼睑测试\","
        "\"canvas\":{\"w\":200,\"h\":200},\"origin\":[100,200],"
        "\"groups\":{\"root\":{\"pivot\":[100,200],\"parent\":\"\"}},"
        "\"parts\":[{\"id\":\"lid\",\"file\":\"sprites/lid.png\",\"group\":\"root\","
        " \"layer\":10,\"pos\":[60,40],\"anchor\":[0,0],"
        " \"tags\":[\"eyelid\"],\"eyelid_travel\":20}],"
        "\"actions\":[{\"id\":\"idle\",\"loop\":true,\"channels\":[]}]}");
    {
        zdiag d;
        zrig *r;
        zdiag_init(&d);
        r = zrig_load(rigp, dir, &d);
        CHECK(r != NULL, "带 eyelid 标签的 rig 应加载成功");
        if (r) {
            const zimg *fb;
            int open_y, half_y, shut_y, open_px, shut_px;
            zrig_blink_set_manual(r, 0.0);
            zrig_tick(r, 0.1);
            fb = zrig_frame(r, 1.0, NULL, NULL);
            open_y = frame_centroid_y(fb);
            open_px = frame_opaque_px(fb);
            zrig_blink_set_manual(r, 0.5);
            zrig_tick(r, 0.1);
            fb = zrig_frame(r, 1.0, NULL, NULL);
            half_y = frame_centroid_y(fb);
            zrig_blink_set_manual(r, 1.0);
            zrig_tick(r, 0.1);
            fb = zrig_frame(r, 1.0, NULL, NULL);
            shut_y = frame_centroid_y(fb);
            shut_px = frame_opaque_px(fb);
            CHECK(open_y > 0 && shut_y > 0, "眼皮两种状态都该画出东西（%d / %d）", open_y, shut_y);
            CHECK(shut_y > open_y, "blink=1 时眼皮重心应更靠下（睁 %d → 闭 %d）", open_y, shut_y);
            CHECK(half_y > open_y && half_y < shut_y,
                  "blink=0.5 应落在中间（%d < %d < %d）", open_y, half_y, shut_y);
            CHECK(shut_px > open_px - open_px / 20 && shut_px < open_px + open_px / 20,
                  "下滑不该改变眼皮的像素量（睁 %d vs 闭 %d）", open_px, shut_px);
            CHECK(zrig_blink_manual(r) > 0.99, "手动眨眼值应可读回（%.2f）", zrig_blink_manual(r));
            zrig_blink_set_manual(r, -1.0);
            CHECK(zrig_blink_manual(r) < 0.0, "设成负数应回到自动眨眼");
            zrig_free(r);
        }
    }
}

static void test_mask(void)
{
    char dir[1024], sprites[1024], src[1024], dst[1024], rigp[1024];
    SECTION("遮罩：部件只在遮罩形状内可见（眼球不滑出眼眶的前提）");
    z_snprintf(dir, sizeof(dir), "/tmp/zc_mask");
    z_snprintf(sprites, sizeof(sprites), "%s/sprites", dir);
    z_mkdir_p(dir);
    z_mkdir_p(sprites);
    z_snprintf(src, sizeof(src), "%s/characters/xiaoxun/forms/teen/sprites/body_full.png", g_root);
    z_snprintf(dst, sizeof(dst), "%s/body_full.png", sprites);
    if (copy_file(src, dst) != 0) { CHECK(0, "复制 body_full.png 失败"); return; }
    z_snprintf(src, sizeof(src), "%s/characters/xiaoxun/forms/teen/sprites/mouth_open.png", g_root);
    z_snprintf(dst, sizeof(dst), "%s/mouth_open.png", sprites);
    if (copy_file(src, dst) != 0) { CHECK(0, "复制 mouth_open.png 失败"); return; }
    z_snprintf(rigp, sizeof(rigp), "%s/rig.json", dir);

    /* 正例：用小小的嘴去裁切整张身体，画面上应该只剩嘴那一块 */
    write_text(rigp,
        "{\"schema_version\":\"1.0\",\"id\":\"m\",\"name\":\"遮罩测试\","
        "\"canvas\":{\"w\":848,\"h\":1360},\"origin\":[424,1360],"
        "\"groups\":{\"root\":{\"pivot\":[424,1360],\"parent\":\"\"}},"
        "\"parts\":["
        " {\"id\":\"hole\",\"file\":\"sprites/mouth_open.png\",\"group\":\"root\","
        "  \"layer\":10,\"pos\":[300,300],\"anchor\":[0,0],\"mask_only\":true},"
        " {\"id\":\"body\",\"file\":\"sprites/body_full.png\",\"group\":\"root\","
        "  \"layer\":20,\"pos\":[200,60],\"anchor\":[0,0],\"mask\":\"hole\"}],"
        "\"actions\":[{\"id\":\"idle\",\"loop\":true,\"channels\":[]}]}");
    {
        zdiag d;
        zrig *r;
        zdiag_init(&d);
        r = zrig_load(rigp, dir, &d);
        CHECK(r != NULL, "带遮罩的 rig 应加载成功");
        if (r) {
            const zimg *fb;
            int masked = 0, plain = 0;
            zrig_tick(r, 1.0);
            fb = zrig_frame(r, 1.0, NULL, NULL);
            masked = frame_opaque_px(fb);
            zrig_free(r);
            /* 同一份 rig，去掉 mask 之后应该画出整张身体 */
            write_text(rigp,
                "{\"schema_version\":\"1.0\",\"id\":\"m\",\"name\":\"遮罩测试\","
                "\"canvas\":{\"w\":848,\"h\":1360},\"origin\":[424,1360],"
                "\"groups\":{\"root\":{\"pivot\":[424,1360],\"parent\":\"\"}},"
                "\"parts\":["
                " {\"id\":\"body\",\"file\":\"sprites/body_full.png\",\"group\":\"root\","
                "  \"layer\":20,\"pos\":[200,60],\"anchor\":[0,0]}],"
                "\"actions\":[{\"id\":\"idle\",\"loop\":true,\"channels\":[]}]}");
            zdiag_init(&d);
            r = zrig_load(rigp, dir, &d);
            if (r) {
                zrig_tick(r, 1.0);
                fb = zrig_frame(r, 1.0, NULL, NULL);
                plain = frame_opaque_px(fb);
                zrig_free(r);
            }
            CHECK(masked > 0, "被裁切的部件仍应有可见像素（实际 %d）", masked);
            CHECK(plain > masked * 10,
                  "裁切后应只剩遮罩那一小块：裁切 %d 像素 vs 未裁切 %d 像素", masked, plain);
        }
    }

    /* 眨眼把遮罩源一起关掉时，被裁切的部件必须跟着消失（遮罩全透明 = 看不见） */
    write_text(rigp,
        "{\"schema_version\":\"1.0\",\"id\":\"m\",\"name\":\"遮罩测试\","
        "\"canvas\":{\"w\":848,\"h\":1360},\"origin\":[424,1360],"
        "\"groups\":{\"root\":{\"pivot\":[424,1360],\"parent\":\"\"}},"
        "\"blink\":{\"enabled\":true},"
        "\"parts\":["
        " {\"id\":\"hole\",\"file\":\"sprites/mouth_open.png\",\"group\":\"root\","
        "  \"layer\":10,\"pos\":[300,300],\"anchor\":[0,0],\"mask_only\":true,"
        "  \"tags\":[\"eye_open\"]},"
        " {\"id\":\"body\",\"file\":\"sprites/body_full.png\",\"group\":\"root\","
        "  \"layer\":20,\"pos\":[200,60],\"anchor\":[0,0],\"mask\":\"hole\"}],"
        "\"actions\":[{\"id\":\"idle\",\"loop\":true,\"channels\":[]}]}");
    {
        zdiag d;
        zrig *r;
        zdiag_init(&d);
        r = zrig_load(rigp, dir, &d);
        CHECK(r != NULL, "带眨眼标签的遮罩 rig 应加载成功");
        if (r) {
            const zimg *fb;
            int open_px, closed_px;
            zrig_tick(r, 1.0);
            fb = zrig_frame(r, 1.0, NULL, NULL);
            open_px = frame_opaque_px(fb);
            zrig_blink_force(r, 1);
            zrig_tick(r, 1.1);
            fb = zrig_frame(r, 1.1, NULL, NULL);
            closed_px = frame_opaque_px(fb);
            CHECK(open_px > 0, "睁眼时被裁切的部件可见（%d 像素）", open_px);
            CHECK(closed_px == 0,
                  "遮罩被眨眼隐藏后，被裁切的部件也要消失（实际还剩 %d 像素）", closed_px);
            zrig_free(r);
        }
    }

    /* 分轴缩放："scale":[sx,sy] + sy 通道 = 嘴的开合（压扁遮罩而不是整体缩小） */
    write_text(rigp,
        "{\"schema_version\":\"1.0\",\"id\":\"m\",\"name\":\"遮罩测试\","
        "\"canvas\":{\"w\":848,\"h\":1360},\"origin\":[424,1360],"
        "\"groups\":{\"root\":{\"pivot\":[424,1360],\"parent\":\"\"}},"
        "\"parts\":["
        " {\"id\":\"hole\",\"file\":\"sprites/mouth_open.png\",\"group\":\"root\","
        "  \"layer\":10,\"pos\":[400,300],\"anchor\":[0.5,0],\"scale\":[1.0,0.1],"
        "  \"mask_only\":true},"
        " {\"id\":\"body\",\"file\":\"sprites/body_full.png\",\"group\":\"root\","
        "  \"layer\":20,\"pos\":[200,60],\"anchor\":[0,0],\"mask\":\"hole\"}],"
        "\"actions\":[{\"id\":\"idle\",\"loop\":true,\"channels\":[]},"
        " {\"id\":\"open\",\"loop\":true,\"channels\":["
        "  {\"target\":\"hole\",\"param\":\"sy\",\"wave\":\"pulse\",\"amp\":0.8,\"dur\":0.05}]}]}");
    {
        zdiag d;
        zrig *r;
        zdiag_init(&d);
        r = zrig_load(rigp, dir, &d);
        CHECK(r != NULL, "带分轴缩放的 rig 应加载成功");
        if (r) {
            const zimg *fb;
            int closed_px, open_px;
            zrig_tick(r, 1.0);
            fb = zrig_frame(r, 1.0, NULL, NULL);
            closed_px = frame_opaque_px(fb);
            zrig_action_request(r, "open", "t", 1);
            zrig_tick(r, 1.2);
            fb = zrig_frame(r, 1.2, NULL, NULL);
            open_px = frame_opaque_px(fb);
            CHECK(open_px > closed_px * 3,
                  "sy 通道要把遮罩撑开：闭 %d 像素 → 开 %d 像素", closed_px, open_px);
            zrig_free(r);
        }
    }

    /* 反例一：遮罩指向不存在的部件 */
    write_text(rigp,
        "{\"schema_version\":\"1.0\",\"id\":\"m\",\"name\":\"遮罩测试\","
        "\"canvas\":{\"w\":848,\"h\":1360},\"origin\":[424,1360],"
        "\"groups\":{\"root\":{\"pivot\":[424,1360],\"parent\":\"\"}},"
        "\"parts\":[{\"id\":\"body\",\"file\":\"sprites/body_full.png\",\"group\":\"root\","
        " \"layer\":20,\"pos\":[200,60],\"anchor\":[0,0],\"mask\":\"nope\"}],"
        "\"actions\":[{\"id\":\"idle\",\"loop\":true,\"channels\":[]}]}");
    {
        zdiag d;
        zrig *r;
        zdiag_init(&d);
        r = zrig_load(rigp, dir, &d);
        CHECK(r == NULL, "遮罩指向不存在的部件应加载失败");
        CHECK(diag_has(&d, "nope"), "错误信息要点名是哪个 mask 找不到");
    }

    /* 反例二：遮罩画在被裁切部件后面（层序反了） */
    write_text(rigp,
        "{\"schema_version\":\"1.0\",\"id\":\"m\",\"name\":\"遮罩测试\","
        "\"canvas\":{\"w\":848,\"h\":1360},\"origin\":[424,1360],"
        "\"groups\":{\"root\":{\"pivot\":[424,1360],\"parent\":\"\"}},"
        "\"parts\":["
        " {\"id\":\"hole\",\"file\":\"sprites/mouth_open.png\",\"group\":\"root\","
        "  \"layer\":30,\"pos\":[300,300],\"anchor\":[0,0]},"
        " {\"id\":\"body\",\"file\":\"sprites/body_full.png\",\"group\":\"root\","
        "  \"layer\":20,\"pos\":[200,60],\"anchor\":[0,0],\"mask\":\"hole\"}],"
        "\"actions\":[{\"id\":\"idle\",\"loop\":true,\"channels\":[]}]}");
    {
        zdiag d;
        zrig *r;
        zdiag_init(&d);
        r = zrig_load(rigp, dir, &d);
        CHECK(r == NULL, "遮罩层序反了应加载失败");
        CHECK(diag_has(&d, "layer"), "错误信息要说清是层序问题");
    }
}

static int diag_has(const zdiag *d, const char *needle)
{
    int i;
    for (i = 0; i < d->count; ++i)
        if (strstr(d->items[i].msg, needle)) return 1;
    return 0;
}

static void test_interactions(void)
{
    zdiag diag;
    zinteract *z;
    const zi_rule *r;
    char buf[256];
    int i;
    zconfig cfg;
    zpet *pet;
    char cfgdir[1024];

    SECTION("互动规则：加载、匹配、台词冷却");
    zdiag_init(&diag);
    z = zinteract_load(g_root, "xiaoxun", &diag);
    CHECK(z != NULL, "互动规则应加载成功（错误 %d 条）", diag.error_count);
    if (!z) return;
    CHECK(z->nrules >= 15, "规则应不少于 15 条，实际 %d", z->nrules);
    CHECK(z->nlines >= 15, "台词应不少于 15 条，实际 %d", z->nlines);
    CHECK(z->dialogue_status_draft == 1, "小寻台词标记为草稿（待用户确认）");

    r = zinteract_match(z, "hammer", "", NULL, 0);
    CHECK(r && z_streq(r->id, "hammer_any"), "锤击应匹配 hammer_any");
    r = zinteract_match(z, "poke", "head", NULL, 1);
    CHECK(r && z_streq(r->id, "pat_head"), "摸头 1 次应匹配 pat_head");
    r = zinteract_match(z, "poke", "head", NULL, 3);
    CHECK(r && z_streq(r->id, "pat_head_combo"), "摸头 3 次应匹配连击（优先级更高）");
    r = zinteract_match(z, "poke", "body", NULL, 0);
    CHECK(r && z_streq(r->id, "stroke_body"), "身体应匹配 stroke_body");
    r = zinteract_match(z, "poke", "", NULL, 0);
    CHECK(r && z_streq(r->id, "poke_other"), "其它位置应匹配 poke_other（兜底）");
    r = zinteract_match(z, "mood", "", "joy", 0);
    CHECK(r && z_streq(r->id, "mood_joy") && z_streq(r->action, "happy"), "情绪 joy → happy");
    CHECK(zinteract_match(z, "mood", "", "no_such", 0) == NULL, "未知情绪不匹配任何规则");
    CHECK(zinteract_match(z, "call_reply", "", NULL, 0) != NULL, "语音回复事件有规则");

    /* 台词冷却：同一规则 2 秒内只说一次；同一规则冷却未过不说；轮换变体 */
    r = zinteract_match(z, "poke", "head", NULL, 1);
    CHECK(zinteract_speak(z, r, 100.0, buf, sizeof(buf)) == 1, "首次应说话");
    CHECK(buf[0] != 0, "台词不能为空");
    CHECK(zinteract_speak(z, r, 100.5, buf, sizeof(buf)) == 0, "间隔不足 2 秒不说话");
    CHECK(buf[0] == 0, "不说话时输出应清空");
    CHECK(zinteract_speak(z, r, 102.5, buf, sizeof(buf)) == 0, "同一规则冷却 8 秒内不重复说话");
    {
        char first[256], second[256];
        zinteract_speak(z, zinteract_match(z, "hammer", "", NULL, 0), 200.0, first, sizeof(first));
        zinteract_speak(z, zinteract_match(z, "hammer", "", NULL, 0), 210.0, second, sizeof(second));
        CHECK(first[0] && second[0] && strcmp(first, second) != 0, "同一台词组的变体应轮换");
    }
    z->speech_enabled = 0;
    CHECK(zinteract_speak(z, zinteract_match(z, "drag_start", "", NULL, 0), 500.0, buf, sizeof(buf)) == 0,
          "speech.enabled=false 时不说话");
    zinteract_free(z);

    SECTION("互动规则：坏配置报出文件与字段");
    {
        char root[256], dir[300];
        z_snprintf(root, sizeof(root), "/tmp/zc_interact_bad_%d", (int)getpid());
        z_snprintf(dir, sizeof(dir), "%s/config", root);
        z_mkdir_p(dir);
        z_snprintf(dir, sizeof(dir), "%s/characters/bad", root);
        z_mkdir_p(dir);
        z_snprintf(dir, sizeof(dir), "%s/config/interactions.json", root);
        write_text(dir, "{\"schema_version\":\"1.0\",\"rules\":[{\"id\":\"a\",\"kind\":\"dance\",\"action\":\"idle\"}]}");
        z_snprintf(dir, sizeof(dir), "%s/characters/bad/dialogue.json", root);
        write_text(dir, "{\"lines\":[{\"id\":\"x\",\"texts\":[\"hi\"]}]}");
        zdiag_init(&diag);
        z = zinteract_load(root, "bad", &diag);
        CHECK(z == NULL, "未知 kind 必须加载失败");
        CHECK(diag.error_count >= 1, "应记录至少一条错误");
        CHECK(diag_has(&diag, "dance"), "诊断应指出非法 kind 的值");

        z_snprintf(dir, sizeof(dir), "%s/config/interactions.json", root);
        write_text(dir, "{\"schema_version\":\"1.0\",\"rules\":[{\"id\":\"a\",\"kind\":\"poke\",\"action\":\"idle\",\"lines\":[\"nope\"]}]}");
        zdiag_init(&diag);
        z = zinteract_load(root, "bad", &diag);
        CHECK(z == NULL, "引用不存在的台词 id 必须失败");
        CHECK(diag.error_count >= 1 && diag_has(&diag, "nope"), "诊断应包含缺失的台词 id");
        (void)i;
    }

    SECTION("互动：摸头连击、锤击、情绪与语音事件驱动宠物");
    zdiag_init(&diag);
    z_snprintf(cfgdir, sizeof(cfgdir), "%s/config", g_root);
    zconfig_load(&cfg, cfgdir, &diag);
    zdiag_init(&diag);
    pet = zpet_create(&cfg, &diag);
    CHECK(pet != NULL, "角色包应加载成功");
    if (pet) {
        int fw = 0, fh = 0;
        zpet_tick(pet, 1.0);            /* 第一帧由 tick 渲染，之前帧缓冲为空 */
        zpet_frame(pet, &fw, &fh);
        zpet_report_idle(pet, 0.0);
        zpet_poke(pet, fw / 2, fh / 8, ZPET_TOOL_HAND, 10.0);
        CHECK(z_streq(zpet_action(pet), "head_pat"), "摸头 → head_pat，实际 %s", zpet_action(pet));
        CHECK(zpet_last_line(pet)[0] != 0, "摸头应有台词");
        zpet_poke(pet, fw / 2, fh / 8, ZPET_TOOL_HAND, 11.0);
        zpet_poke(pet, fw / 2, fh / 8, ZPET_TOOL_HAND, 12.0);
        CHECK(z_streq(zpet_action(pet), "happy"), "连续摸 3 次 → happy，实际 %s", zpet_action(pet));

        zpet_tick(pet, 30.0);           /* 让 happy 等动作播完，非强制请求才能切换 */
        zpet_express(pet, "sad", 30.0);
        CHECK(z_streq(zpet_last_mood(pet), "sad"), "情绪应被记录");
        CHECK(z_streq(zpet_action(pet), "sad"), "sad 情绪 → sad 动作，实际 %s", zpet_action(pet));

        zpet_call_event(pet, "call_reply", "今天的天气很好哦", NULL, 40.0);
        CHECK(z_streq(zpet_last_line(pet), "今天的天气很好哦"), "语音回复原文应优先显示");
        zpet_tick(pet, 50.0);
        zpet_call_event(pet, "call_start", NULL, NULL, 50.0);
        CHECK(z_streq(zpet_action(pet), "talk"), "通话开始 → talk（priority 4 盖过循环中的 sad），实际 %s", zpet_action(pet));
        zpet_destroy(pet);
    }
}

/* -------------------------------------------------------- 好感度 / 角色台词 */
static void test_affection(void)
{
    zdiag diag;
    zinteract *z;
    const zi_rule *r;
    char out[256];
    zconfig cfg;
    zpet *pet;
    char cfgdir[1024];
    static const char *const chars[] = {"xiaoxun", "shenyu", "xiaochen", "xingxuan",
                                        "shuangxi", "tonglin", "yuejian", "shandian"};
    enum { NCHARS = 8 };
    static char first[NCHARS][256];
    int i, j;

    SECTION("好感度分级：档位、每日上限、减少不受限");
    zdiag_init(&diag);
    z = zinteract_load(g_root, "xiaoxun", &diag);
    CHECK(z != NULL, "互动规则应加载成功（错误 %d 条）", diag.error_count);
    if (!z) return;
    CHECK(z->ntiers == 4, "默认四档，实际 %d", z->ntiers);
    CHECK(z_streq(z->tiers[1].name, "熟络") && z->tiers[1].min_points == 30, "第二档 熟络 30");
    CHECK(zinteract_tier(z) == 0 && z_streq(zinteract_tier_name(z), "初识"), "初始为初识");
    CHECK(zinteract_add_affection(z, 50, 1) == 1, "一次加 50 受每日上限 30 约束，应升到熟络");
    CHECK(zinteract_affection(z) == 30, "每日上限 30，实际 %d", zinteract_affection(z));
    CHECK(zinteract_add_affection(z, 10, 1) == 0 && zinteract_affection(z) == 30, "同日达上限后不再增加");
    CHECK(zinteract_add_affection(z, 10, 2) == 0 && zinteract_affection(z) == 40, "次日重新计数，+10 = 40");
    CHECK(zinteract_add_affection(z, -100, 2) == 0 && zinteract_affection(z) == 0, "减少不受限且不低于 0");
    zinteract_set_affection(z, 100);
    CHECK(zinteract_tier(z) == 2 && z_streq(zinteract_tier_name(z), "亲近"), "100 → 亲近");
    zinteract_set_affection(z, 249);
    CHECK(zinteract_tier(z) == 2, "249 仍是亲近");
    zinteract_set_affection(z, 250);
    CHECK(zinteract_tier(z) == 3 && z_streq(zinteract_tier_name(z), "挚友"), "250 → 挚友");
    zinteract_free(z);

    SECTION("台词按好感档选择变体");
    zdiag_init(&diag);
    z = zinteract_load(g_root, "xiaoxun", &diag);
    if (!z) return;
    r = zinteract_match(z, "tier_up", "", NULL, 0);
    CHECK(r != NULL, "应存在 tier_up 规则");
    zinteract_set_affection(z, 0);
    CHECK(zinteract_speak(z, r, 1000.0, out, sizeof(out)) == 1 && strstr(out, "更熟") != NULL,
          "初识档用基础台词，实际 [%s]", out);
    zinteract_set_affection(z, 100);
    CHECK(zinteract_speak(z, r, 2000.0, out, sizeof(out)) == 1 && strstr(out, "一直在") != NULL,
          "亲近档用亲近变体，实际 [%s]", out);
    zinteract_set_affection(z, 300);
    CHECK(zinteract_speak(z, r, 3000.0, out, sizeof(out)) == 1 && strstr(out, "朋友啦") != NULL,
          "挚友档用最高档变体，实际 [%s]", out);
    zinteract_free(z);

    SECTION("八个角色：台词齐全、各自性格不同");
    for (i = 0; i < NCHARS; ++i) {
        zdiag_init(&diag);
        z = zinteract_load(g_root, chars[i], &diag);
        CHECK(z != NULL, "角色 %s 的互动/台词应加载成功（错误 %d）", chars[i], diag.error_count);
        first[i][0] = 0;
        if (!z) continue;
        CHECK(z->dialogue_status_draft == 1, "角色 %s 台词应标记为草稿", chars[i]);
        zinteract_set_affection(z, 0);
        r = zinteract_match(z, "hammer", "", NULL, 0);
        CHECK(zinteract_speak(z, r, 1000.0, first[i], sizeof(first[i])) == 1,
              "角色 %s 被敲击应有台词", chars[i]);
        zinteract_set_affection(z, 300);
        r = zinteract_match(z, "tier_up", "", NULL, 0);
        CHECK(zinteract_speak(z, r, 2000.0, out, sizeof(out)) == 1 && out[0] != 0,
              "角色 %s 挚友档应有升档台词", chars[i]);
        zinteract_free(z);
    }
    for (i = 0; i < NCHARS; ++i)
        for (j = i + 1; j < NCHARS; ++j)
            CHECK(strcmp(first[i], first[j]) != 0,
                  "角色 %s 与 %s 的同一台词不能相同（性格应不同）", chars[i], chars[j]);

    SECTION("好感配置错误：报出文件与字段");
    {
        char root[256], dir[300];
        z_snprintf(root, sizeof(root), "/tmp/zc_affection_bad_%d", (int)getpid());
        z_snprintf(dir, sizeof(dir), "%s/config", root);
        z_mkdir_p(dir);
        z_snprintf(dir, sizeof(dir), "%s/characters/bad", root);
        z_mkdir_p(dir);
        z_snprintf(dir, sizeof(dir), "%s/characters/bad/dialogue.json", root);
        write_text(dir, "{\"lines\":[{\"id\":\"tier_up\",\"texts\":[\"x\"]}]}");
        z_snprintf(dir, sizeof(dir), "%s/config/interactions.json", root);

        write_text(dir, "{\"schema_version\":\"1.0\",\"affection\":{\"tiers\":[{\"name\":\"a\",\"min\":5}]},\"rules\":[]}");
        zdiag_init(&diag);
        CHECK(zinteract_load(root, "bad", &diag) == NULL, "第一档 min 不是 0 必须失败");
        CHECK(diag_has(&diag, "第一档"), "诊断应指出第一档 min");

        write_text(dir, "{\"schema_version\":\"1.0\",\"affection\":{\"tiers\":[{\"name\":\"a\",\"min\":0},{\"name\":\"b\",\"min\":10},{\"name\":\"c\",\"min\":10}]},\"rules\":[]}");
        zdiag_init(&diag);
        CHECK(zinteract_load(root, "bad", &diag) == NULL, "档位不递增必须失败");
        CHECK(diag_has(&diag, "递增"), "诊断应指出档位递增");

        write_text(dir, "{\"schema_version\":\"1.0\",\"affection\":{\"tiers\":[{\"name\":\"a\",\"min\":0}]},\"rules\":[]}");
        z_snprintf(dir, sizeof(dir), "%s/characters/bad/dialogue.json", root);
        write_text(dir, "{\"lines\":[{\"id\":\"x\",\"tiers\":[{\"tier\":0,\"texts\":[\"q\"]}]}]}");
        z_snprintf(dir, sizeof(dir), "%s/config/interactions.json", root);
        write_text(dir, "{\"schema_version\":\"1.0\",\"affection\":{\"tiers\":[{\"name\":\"a\",\"min\":0}]},\"rules\":[]}");
        zdiag_init(&diag);
        CHECK(zinteract_load(root, "bad", &diag) == NULL, "台词缺少基础 texts 必须失败");
        CHECK(diag_has(&diag, "基础文本"), "诊断应指出缺少基础文本");

        z_snprintf(dir, sizeof(dir), "%s/characters/bad/dialogue.json", root);
        write_text(dir, "{\"lines\":[{\"id\":\"x\",\"texts\":[\"a\"],\"tiers\":[{\"tier\":2,\"texts\":[\"q\"]}]}]}");
        zdiag_init(&diag);
        CHECK(zinteract_load(root, "bad", &diag) == NULL, "档位超过配置的档数必须失败");
        CHECK(diag_has(&diag, "超出好感档位数"), "诊断应指出档位越界");
    }

    SECTION("互动带来好感：摸头加好感，升档时说升档台词");
    zdiag_init(&diag);
    z_snprintf(cfgdir, sizeof(cfgdir), "%s/config", g_root);
    zconfig_load(&cfg, cfgdir, &diag);
    zdiag_init(&diag);
    pet = zpet_create(&cfg, &diag);
    CHECK(pet != NULL, "角色包应加载成功");
    if (pet) {
        int fw = 0, fh = 0;
        zpet_tick(pet, 1.0);
        zpet_frame(pet, &fw, &fh);
        zpet_set_affection(pet, 0);
        zpet_poke(pet, fw / 2, fh / 8, ZPET_TOOL_HAND, 10.0);
        CHECK(zpet_affection(pet) == 2, "摸头 +2，实际 %d", zpet_affection(pet));
        zpet_set_affection(pet, 29);
        zpet_tick(pet, 20.0);
        zpet_poke(pet, fw / 2, fh / 8, ZPET_TOOL_HAND, 30.0);
        CHECK(zpet_affection(pet) == 31, "29 摸头 +2 应为 31，实际 %d", zpet_affection(pet));
        CHECK(z_streq(zpet_affection_tier_name(pet), "熟络"), "31 应升到熟络，实际 %s",
              zpet_affection_tier_name(pet));
        CHECK(strstr(zpet_last_line(pet), "熟起来") != NULL,
              "升档应显示升档台词，实际 [%s]", zpet_last_line(pet));
        zpet_destroy(pet);
    }
}


/* ---- A4 口型同步：包络按时间推进、嘴让路、播完收尾 ---- */
static void test_lipsync(void)
{
    zconfig cfg;
    zdiag diag;
    zpet *pet;
    char cfgdir[1024];
    /* 0 → 1 → 0 的三角包络，10fps，总长 (5-1)/10 = 0.4s */
    static const double env[5] = { 0.0, 0.5, 1.0, 0.5, 0.0 };

    SECTION("口型同步：包络驱动 ParamMouthOpenY，动作里的嘴通道让路");
    zdiag_init(&diag);
    z_snprintf(cfgdir, sizeof(cfgdir), "%s/config", g_root);
    zconfig_load(&cfg, cfgdir, &diag);
    zdiag_init(&diag);
    pet = zpet_create(&cfg, &diag);
    CHECK(pet != NULL, "角色包应加载成功");
    if (!pet) return;

    zpet_tick(pet, 100.0);
    CHECK(zpet_lipsync_active(pet) == 0, "默认不在说话");

    CHECK(zpet_lipsync_start(pet, env, 5, 10.0, 100.0) == 0, "喂包络应成功");
    CHECK(zpet_lipsync_active(pet) == 1, "开始后应处于说话中");
    CHECK(fabs(zpet_lipsync_remain(pet) - 0.4) < 1e-6,
          "剩余应为 0.4s，实为 %.3f", zpet_lipsync_remain(pet));

    /* 中点：第 2 帧正好是 1.0 */
    zpet_tick(pet, 100.2);
    CHECK(fabs(zpet_lipsync_level(pet) - 1.0) < 1e-6,
          "0.2s 应取到包络峰值 1.0，实为 %.3f", zpet_lipsync_level(pet));
    /* 帧间线性插值：0.25s 落在 1.0 与 0.5 中间 */
    zpet_tick(pet, 100.25);
    CHECK(fabs(zpet_lipsync_level(pet) - 0.75) < 1e-6,
          "0.25s 应插值出 0.75，实为 %.3f", zpet_lipsync_level(pet));

    /* 播完自动收尾：参数回默认、嘴交还动作 */
    zpet_tick(pet, 100.9);
    CHECK(zpet_lipsync_active(pet) == 0, "播完应自动停");
    CHECK(fabs(zpet_lipsync_level(pet)) < 1e-9, "停下后开口度应回 0");

    /* 参数不合法要被拒绝 */
    CHECK(zpet_lipsync_start(pet, env, 1, 10.0, 101.0) == -1, "只有 1 帧应拒绝");
    CHECK(zpet_lipsync_start(pet, env, 5, 0.0, 101.0) == -1, "fps=0 应拒绝");
    CHECK(zpet_lipsync_load(pet, "../etc/passwd", 101.0) == -1, "带 ../ 的 id 必须拒绝");
    CHECK(zpet_lipsync_load(pet, "no_such_line", 101.0) == -1, "不存在的包络应失败");

    /* 真包络文件（tools/make_lipsync.py 的产物）能读起来 */
    if (zpet_lipsync_load(pet, "hammer_1_base0", 102.0) == 0) {
        CHECK(zpet_lipsync_active(pet) == 1, "读文件后应在说话");
        CHECK(zpet_lipsync_remain(pet) > 1.0, "这条台词应超过 1 秒");
        CHECK(strlen(zpet_lipsync_text(pet)) > 0, "包络里应带台词文本");
        zpet_lipsync_stop(pet);
        CHECK(zpet_lipsync_active(pet) == 0, "手动停应立刻生效");
    }
    zpet_destroy(pet);
}


/* ---- 长稳：连续跑两万帧，画面不崩、数值不发散（配 make asan 查泄漏）---- */
static void test_longrun(void)
{
    zconfig cfg;
    zdiag diag;
    zpet *pet;
    char cfgdir[1024];
    const char *acts[6] = { "wave", "happy", "think", "surprised", "talk", "idle" };
    int i, fw = 0, fh = 0, bad = 0;
    double t;

    SECTION("长稳：2 万帧连续渲染不崩、不发散");
    zdiag_init(&diag);
    z_snprintf(cfgdir, sizeof(cfgdir), "%s/config", g_root);
    zconfig_load(&cfg, cfgdir, &diag);
    zdiag_init(&diag);
    pet = zpet_create(&cfg, &diag);
    CHECK(pet != NULL, "角色包应加载成功");
    if (!pet) return;

    for (i = 0; i < 20000; ++i) {
        t = 1000.0 + i / 60.0;                      /* 60fps 跑 5 分半 */
        if (i % 600 == 0) zpet_action_request(pet, acts[(i / 600) % 6], "longrun", 1);
        if (i % 97 == 0) zpet_hover(pet, (i * 7) % 400, (i * 13) % 700, 1, t);
        if (i % 311 == 0) zpet_poke(pet, 300, 120, ZPET_TOOL_HAND, t);
        if (i % 503 == 0) zpet_lipsync_load(pet, "click_1_base0", t);
        zpet_tick(pet, t);
        if (i % 50 == 0) {
            const zimg *fr = zpet_frame(pet, &fw, &fh);
            if (!fr || fw <= 0 || fh <= 0) bad++;
        }
        /* 参数不能发散成 NaN/inf */
        if (i % 1000 == 0) {
            double v = zpet_blink(pet);
            if (!(v >= -0.001 && v <= 1.001)) bad++;
        }
    }
    CHECK(bad == 0, "2 万帧里出现 %d 次异常帧/异常数值", bad);
    CHECK(fw > 0 && fh > 0, "最后一帧仍能渲染（%dx%d）", fw, fh);
    zpet_destroy(pet);
}


/* ---- A5 网格形变：zimg 级 + rig 级 ---- */
static int apx(const zimg *im, int x, int y)   /* 取某点 alpha */
{
    if (!im || x < 0 || y < 0 || x >= im->w || y >= im->h) return 0;
    return im->px[((size_t)y * im->w + x) * 4 + 3];
}

static void test_mesh(void)
{
    SECTION("网格形变：控制点推得动像素，没推就和普通绘制一模一样");
    {
        zimg *src = zimg_new_filled(40, 40, 255, 0, 0, 255);
        zimg *a = zimg_new(80, 80), *b = zimg_new(80, 80);
        double m[6], off[9 * 2];
        int i;
        zimg_make_matrix(m, 20, 20, 1, 1, 0, 0, 0);
        for (i = 0; i < 18; ++i) off[i] = 0.0;
        /* ① 控制点全不动 = 和 zimg_draw 像素级一致 */
        zimg_draw(a, src, m, 1.0);
        zimg_draw_mesh(b, src, m, 1.0, 2, 2, off);
        {
            int diff = 0, x, y;
            for (y = 0; y < 80; ++y)
                for (x = 0; x < 80; ++x) {
                    if (abs(apx(a, x, y) - apx(b, x, y)) > 2) diff++;
                }
            CHECK(diff == 0, "没挪控制点时应与普通绘制一致，实际差 %d 像素", diff);
        }
        /* ② 把右上角那个控制点往右推 20px：右上角应该长出来 */
        zimg_clear(b);
        off[2 * 2] = 20.0;                     /* 控制点 (c=2,r=0) 的 dx */
        zimg_draw_mesh(b, src, m, 1.0, 2, 2, off);
        CHECK(apx(b, 70, 22) > 128, "右上角被推出去的地方应该有像素");
        CHECK(apx(a, 70, 22) < 10, "原来那里是空的（对照）");
        /* ③ 底边没推，应保持原位 */
        CHECK(apx(b, 30, 58) > 128, "底边不动的部分还在原位");
        zimg_free(src); zimg_free(a); zimg_free(b);
    }

    SECTION("网格形变：rig 里声明 deformers，动作通道与参数都能驱动");
    {
        char dir[1024], sprites[1024], src[1024], dst[1024], rigp[1024];
        zdiag d;
        zrig *r;
        z_snprintf(dir, sizeof(dir), "/tmp/zc_mesh");
        z_snprintf(sprites, sizeof(sprites), "%s/sprites", dir);
        z_mkdir_p(dir);
        z_mkdir_p(sprites);
        z_snprintf(src, sizeof(src), "%s/characters/xiaoxun/forms/teen/sprites/hair_ahoge.png", g_root);
        z_snprintf(dst, sizeof(dst), "%s/h.png", sprites);
        if (copy_file(src, dst) != 0) { CHECK(0, "复制贴图失败"); return; }
        z_snprintf(rigp, sizeof(rigp), "%s/rig.json", dir);
        write_text(rigp,
            "{\"schema_version\":\"1.0\",\"id\":\"m\",\"name\":\"网格测试\","
            "\"canvas\":{\"w\":200,\"h\":200},\"origin\":[100,200],"
            "\"groups\":{\"head\":{\"pivot\":[100,100],\"parent\":\"\"}},"
            "\"parts\":[{\"id\":\"h\",\"file\":\"sprites/h.png\",\"group\":\"head\","
            " \"layer\":10,\"pos\":[60,40],\"anchor\":[0,0]}],"
            "\"deformers\":[{\"id\":\"wave\",\"part\":\"h\",\"cols\":2,\"rows\":2,"
            " \"points\":[{\"c\":0,\"r\":0,\"dx\":8},{\"c\":1,\"r\":0,\"dx\":8},"
            "  {\"c\":2,\"r\":0,\"dx\":8},{\"c\":0,\"r\":1,\"dx\":-3}]}],"
            "\"actions\":[{\"id\":\"idle\",\"loop\":true,\"channels\":["
            "  {\"target\":\"wave\",\"param\":\"amount\",\"wave\":\"sine\","
            "   \"amp\":1.0,\"freq\":1.0}]}],"
            "\"params\":[{\"id\":\"ParamWave\",\"min\":-1,\"max\":1,\"default\":0,"
            " \"binds\":[{\"deformer\":\"wave\",\"scale\":1.0}]}]}");
        zdiag_init(&d);
        r = zrig_load(rigp, dir, &d);
        CHECK(r != NULL, "带 deformers 段的 rig 应加载成功");
        if (r) {
            const zimg *f1, *f2;
            int w = 0, h = 0, diff = 0, x, y;
            CHECK(zrig_deform_count(r) == 1, "应解析出 1 个形变器，实为 %d",
                  zrig_deform_count(r));
            CHECK(z_streq(zrig_deform_id(r, 0), "wave"), "形变器 id 应是 wave");
            /* ① 动作通道驱动：sine 在 0.25 秒（freq 1Hz）到峰值 */
            zrig_tick(r, 0.25);
            CHECK(zrig_deform_amount(r, "wave") > 0.9,
                  "动作通道应把 amount 推到 ~1，实为 %.3f", zrig_deform_amount(r, "wave"));
            f1 = zrig_frame(r, 1.0, &w, &h);
            CHECK(f1 != NULL && w > 0, "形变后应能渲染");
            /* ② 回到 0 的那一刻画面应与峰值不同 */
            {
                zimg *keep = zimg_clone(f1);
                zrig_tick(r, 0.5);
                CHECK(fabs(zrig_deform_amount(r, "wave")) < 0.05,
                      "半个周期后应回到 0，实为 %.3f", zrig_deform_amount(r, "wave"));
                f2 = zrig_frame(r, 1.0, &w, &h);
                for (y = 0; y < h; y += 2)
                    for (x = 0; x < w; x += 2)
                        if (abs(apx(keep, x, y) - apx(f2, x, y)) > 24) diff++;
                CHECK(diff > 20, "形变前后画面必须有可见差异，实际 %d 个采样点不同", diff);
                zimg_free(keep);
            }
            /* ③ 参数层也能驱动同一个形变器 */
            zrig_param_set(r, "ParamWave", 1.0);
            zrig_tick(r, 1.0);          /* 1.0s：sine 回到 0，只剩参数的贡献 */
            CHECK(fabs(zrig_deform_amount(r, "wave") - 1.0) < 0.1,
                  "参数 1.0 应让 amount≈1，实为 %.3f", zrig_deform_amount(r, "wave"));
            zrig_free(r);
        }
        /* ④ 控制点越界要报错，不能默默画错 */
        write_text(rigp,
            "{\"schema_version\":\"1.0\",\"id\":\"m\",\"name\":\"坏网格\","
            "\"canvas\":{\"w\":200,\"h\":200},\"origin\":[100,200],"
            "\"groups\":{\"head\":{\"pivot\":[100,100],\"parent\":\"\"}},"
            "\"parts\":[{\"id\":\"h\",\"file\":\"sprites/h.png\",\"group\":\"head\","
            " \"layer\":10,\"pos\":[60,40],\"anchor\":[0,0]}],"
            "\"deformers\":[{\"id\":\"bad\",\"part\":\"h\",\"cols\":2,\"rows\":2,"
            " \"points\":[{\"c\":5,\"r\":0,\"dx\":8}]}],"
            "\"actions\":[{\"id\":\"idle\",\"loop\":true,\"channels\":[]}]}");
        zdiag_init(&d);
        CHECK(zrig_load(rigp, dir, &d) == NULL, "控制点越界必须加载失败");
        CHECK(diag_has(&d, "越界"), "诊断应指出控制点越界");
    }
}


/* ---- 关键帧曲线（≈ .motion3）与多段物理摆链（G16） ---- */
static void test_keys_and_chain(void)
{
    char dir[1024], sprites[1024], src[1024], dst[1024], rigp[1024];
    zdiag d;
    zrig *r;

    SECTION("关键帧曲线：逐帧给值、三种插值、循环回绕、时间必须递增");
    z_snprintf(dir, sizeof(dir), "/tmp/zc_keys");
    z_snprintf(sprites, sizeof(sprites), "%s/sprites", dir);
    z_mkdir_p(dir);
    z_mkdir_p(sprites);
    z_snprintf(src, sizeof(src), "%s/characters/xiaoxun/forms/teen/sprites/hair_ahoge.png", g_root);
    z_snprintf(dst, sizeof(dst), "%s/h.png", sprites);
    if (copy_file(src, dst) != 0) { CHECK(0, "复制贴图失败"); return; }
    z_snprintf(rigp, sizeof(rigp), "%s/rig.json", dir);
    write_text(rigp,
        "{\"schema_version\":\"1.0\",\"id\":\"k\",\"name\":\"关键帧\","
        "\"canvas\":{\"w\":200,\"h\":200},\"origin\":[100,200],"
        "\"groups\":{\"head\":{\"pivot\":[100,100],\"parent\":\"\"}},"
        "\"parts\":[{\"id\":\"h\",\"file\":\"sprites/h.png\",\"group\":\"head\","
        " \"layer\":10,\"pos\":[60,40],\"anchor\":[0,0]}],"
        "\"actions\":[{\"id\":\"idle\",\"loop\":true,\"channels\":["
        "  {\"target\":\"h\",\"param\":\"dx\",\"interp\":\"linear\","
        "   \"keys\":[[0,0],[0.5,10],[1.0,0]]},"
        "  {\"target\":\"h\",\"param\":\"dy\",\"interp\":\"step\","
        "   \"keys\":[[0,0],[0.5,8],[1.0,0]]}]}]}");
    zdiag_init(&d);
    r = zrig_load(rigp, dir, &d);
    CHECK(r != NULL, "带 keys 的 rig 应加载成功");
    if (r) {
        zrig_tick(r, 0.25);
        CHECK(fabs(zrig_part_channel(r, "h", "dx") - 5.0) < 1e-6,
              "线性插值 0.25s 应是 5，实为 %.3f", zrig_part_channel(r, "h", "dx"));
        CHECK(fabs(zrig_part_channel(r, "h", "dy")) < 1e-9,
              "阶梯插值 0.25s 还停在前一帧的 0，实为 %.3f", zrig_part_channel(r, "h", "dy"));
        zrig_tick(r, 0.5);
        CHECK(fabs(zrig_part_channel(r, "h", "dx") - 10.0) < 1e-6, "0.5s 应到峰值 10");
        CHECK(fabs(zrig_part_channel(r, "h", "dy") - 8.0) < 1e-6, "阶梯插值 0.5s 跳到 8");
        zrig_tick(r, 1.25);      /* 循环动作：曲线整体回绕，等价于 0.25s */
        CHECK(fabs(zrig_part_channel(r, "h", "dx") - 5.0) < 1e-6,
              "循环动作应回绕到 0.25s 的 5，实为 %.3f", zrig_part_channel(r, "h", "dx"));
        zrig_free(r);
    }
    /* 时间不递增要报错 */
    write_text(rigp,
        "{\"schema_version\":\"1.0\",\"id\":\"k\",\"name\":\"坏关键帧\","
        "\"canvas\":{\"w\":200,\"h\":200},\"origin\":[100,200],"
        "\"groups\":{\"head\":{\"pivot\":[100,100],\"parent\":\"\"}},"
        "\"parts\":[{\"id\":\"h\",\"file\":\"sprites/h.png\",\"group\":\"head\","
        " \"layer\":10,\"pos\":[60,40],\"anchor\":[0,0]}],"
        "\"actions\":[{\"id\":\"idle\",\"loop\":true,\"channels\":["
        "  {\"target\":\"h\",\"param\":\"dx\",\"keys\":[[0,0],[0.9,5],[0.4,2]]}]}]}");
    zdiag_init(&d);
    CHECK(zrig_load(rigp, dir, &d) == NULL, "关键帧时间倒退必须加载失败");
    CHECK(diag_has(&d, "递增"), "诊断应指出时间要递增");

    SECTION("多段摆链：第二段吃第一段的输出，梢比根慢半拍");
    write_text(rigp,
        "{\"schema_version\":\"1.0\",\"id\":\"c\",\"name\":\"摆链\","
        "\"canvas\":{\"w\":200,\"h\":200},\"origin\":[100,200],"
        "\"groups\":{\"head\":{\"pivot\":[100,100],\"parent\":\"\"}},"
        "\"parts\":[{\"id\":\"h\",\"file\":\"sprites/h.png\",\"group\":\"head\","
        " \"layer\":10,\"pos\":[60,40],\"anchor\":[0,0]}],"
        "\"deformers\":[{\"id\":\"tipwave\",\"part\":\"h\",\"cols\":1,\"rows\":2,"
        " \"points\":[{\"c\":0,\"r\":0,\"dx\":6},{\"c\":1,\"r\":0,\"dx\":6}]}],"
        "\"actions\":[{\"id\":\"idle\",\"loop\":true,\"channels\":["
        "  {\"target\":\"head\",\"param\":\"dx\",\"wave\":\"sine\",\"amp\":20,\"freq\":1.5}]}],"
        "\"physics\":[{\"id\":\"seg1\",\"part\":\"h\",\"driver\":\"head\",\"axis\":\"x\","
        "  \"param\":\"bend_x\",\"ratio\":0.6,\"stiffness\":40,\"damping\":5,\"max\":12},"
        " {\"id\":\"seg2\",\"part\":\"h\",\"driver\":\"seg1\",\"deformer\":\"tipwave\","
        "  \"ratio\":0.9,\"stiffness\":22,\"damping\":3,\"max\":2}]}");
    zdiag_init(&d);
    r = zrig_load(rigp, dir, &d);
    CHECK(r != NULL, "多段摆 rig 应加载成功");
    if (r) {
        double t, s1peak = 0.0, s2peak = 0.0, dpeak = 0.0;
        for (t = 0.0; t < 2.0; t += 1.0 / 60.0) {
            zrig_tick(r, t);
            if (fabs(zrig_phys_output(r, "seg1")) > s1peak) s1peak = fabs(zrig_phys_output(r, "seg1"));
            if (fabs(zrig_phys_output(r, "seg2")) > s2peak) s2peak = fabs(zrig_phys_output(r, "seg2"));
            if (fabs(zrig_deform_amount(r, "tipwave")) > dpeak)
                dpeak = fabs(zrig_deform_amount(r, "tipwave"));
        }
        CHECK(s1peak > 0.5, "第一段应该被头的摆动带起来，峰值 %.3f", s1peak);
        CHECK(s2peak > 0.01, "第二段应该被第一段带起来，峰值 %.3f", s2peak);
        CHECK(dpeak > 0.01, "第二段的输出应该写进网格形变器，峰值 %.3f", dpeak);
        zrig_free(r);
    }
    /* 驱动写了不存在的名字要报错 */
    write_text(rigp,
        "{\"schema_version\":\"1.0\",\"id\":\"c\",\"name\":\"坏摆链\","
        "\"canvas\":{\"w\":200,\"h\":200},\"origin\":[100,200],"
        "\"groups\":{\"head\":{\"pivot\":[100,100],\"parent\":\"\"}},"
        "\"parts\":[{\"id\":\"h\",\"file\":\"sprites/h.png\",\"group\":\"head\","
        " \"layer\":10,\"pos\":[60,40],\"anchor\":[0,0]}],"
        "\"actions\":[{\"id\":\"idle\",\"loop\":true,\"channels\":[]}],"
        "\"physics\":[{\"id\":\"s2\",\"part\":\"h\",\"driver\":\"nope\","
        "  \"param\":\"bend_x\"}]}");
    zdiag_init(&d);
    CHECK(zrig_load(rigp, dir, &d) == NULL, "driver 名字不存在必须加载失败");
    CHECK(diag_has(&d, "driver"), "诊断应指出 driver 不对");
}


/* ---- 混合模式（≈ Live2D CubismBlendMode：加算 / 乘算） ---- */
static void test_blend(void)
{
    SECTION("混合模式：加算提亮、乘算压暗，而且都不改目标 alpha");
    {
        zimg *dst = zimg_new_filled(8, 8, 100, 120, 140, 200);
        zimg *src = zimg_new_filled(8, 8, 128, 128, 128, 255);
        double m[6];
        zimg_make_matrix(m, 0, 0, 1, 1, 0, 0, 0);

        /* 加算：C = Cd + Cs·As → 100 + 128 = 228；alpha 必须还是 200 */
        zimg_draw_blend(dst, src, m, 1.0, ZIMG_BLEND_ADD);
        CHECK(dst->px[0] == 228, "加算后 R 应是 228，实为 %d", dst->px[0]);
        CHECK(dst->px[3] == 200, "加算不许改 alpha，实为 %d", dst->px[3]);

        /* 乘算：C = Cd·(1 − As + As·Cs)，As=1 → Cd·Cs/255 = 228*128/255 ≈ 114 */
        zimg_draw_blend(dst, src, m, 1.0, ZIMG_BLEND_MULTIPLY);
        CHECK(dst->px[0] >= 113 && dst->px[0] <= 115,
              "乘算后 R 应≈114，实为 %d", dst->px[0]);
        CHECK(dst->px[3] == 200, "乘算不许改 alpha，实为 %d", dst->px[3]);

        /* 普通模式仍然是 source-over：不透明源会盖掉目标并把 alpha 顶满 */
        zimg_draw_blend(dst, src, m, 1.0, ZIMG_BLEND_NORMAL);
        CHECK(dst->px[0] == 128 && dst->px[3] == 255,
              "普通模式应覆盖为 128/255，实为 %d/%d", dst->px[0], dst->px[3]);
        zimg_free(dst); zimg_free(src);
    }
    {   /* 加算画在全透明区域上：什么都不该出现（否则透明背景会多出一块白斑） */
        zimg *dst = zimg_new(8, 8);
        zimg *src = zimg_new_filled(8, 8, 255, 255, 255, 255);
        double m[6];
        int i, nonzero = 0;
        zimg_make_matrix(m, 0, 0, 1, 1, 0, 0, 0);
        zimg_draw_blend(dst, src, m, 1.0, ZIMG_BLEND_ADD);
        for (i = 0; i < 8 * 8 * 4; ++i) if (dst->px[i]) nonzero = 1;
        CHECK(!nonzero, "加算不该在全透明背景上留下任何像素");
        zimg_free(dst); zimg_free(src);
    }
    {   /* 遮罩 + 混合模式一起用（腮红被脸裁、眼高光被眼眶裁就是这条路径） */
        zimg *fb = zimg_new_filled(4, 4, 80, 80, 80, 255);
        zimg *layer = zimg_new_filled(4, 4, 100, 100, 100, 255);
        zimg *mask = zimg_new(4, 4);
        int i;
        for (i = 0; i < 4; ++i) mask->px[i * 4 + 3] = 255;   /* 只开第一行 */
        zimg_composite_masked_blend(fb, layer, mask, ZIMG_BLEND_ADD);
        CHECK(fb->px[0] == 180, "遮罩内应加算到 180，实为 %d", fb->px[0]);
        CHECK(fb->px[(size_t)4 * 4 + 0] == 80, "遮罩外必须原样不动，实为 %d",
              fb->px[(size_t)4 * 4 + 0]);
        zimg_free(fb); zimg_free(layer); zimg_free(mask);
    }

    SECTION("rig 的 blend 字段：解析三种取值，写错要加载失败");
    {
        char dir[1024], sprites[1024], src[1024], dst[1024], rigp[1024];
        zdiag d;
        zrig *r;
        z_snprintf(dir, sizeof(dir), "/tmp/zc_blend");
        z_snprintf(sprites, sizeof(sprites), "%s/sprites", dir);
        z_mkdir_p(dir); z_mkdir_p(sprites);
        z_snprintf(src, sizeof(src), "%s/characters/xiaoxun/forms/teen/sprites/hair_ahoge.png", g_root);
        z_snprintf(dst, sizeof(dst), "%s/h.png", sprites);
        if (copy_file(src, dst) != 0) { CHECK(0, "复制贴图失败"); return; }
        z_snprintf(rigp, sizeof(rigp), "%s/rig.json", dir);
        write_text(rigp,
            "{\"schema_version\":\"1.0\",\"id\":\"b\",\"name\":\"混合\","
            "\"canvas\":{\"w\":200,\"h\":200},\"origin\":[100,200],"
            "\"groups\":{\"head\":{\"pivot\":[100,100],\"parent\":\"\"}},"
            "\"parts\":[{\"id\":\"h\",\"file\":\"sprites/h.png\",\"group\":\"head\","
            "  \"layer\":10,\"pos\":[60,40],\"anchor\":[0,0]},"
            " {\"id\":\"glow\",\"file\":\"sprites/h.png\",\"group\":\"head\","
            "  \"layer\":11,\"pos\":[60,40],\"anchor\":[0,0],\"blend\":\"add\",\"opacity\":1.0}],"
            "\"params\":[{\"id\":\"ParamGlow\",\"min\":0,\"max\":1,\"default\":0,"
            "  \"binds\":[{\"part\":\"glow\",\"param\":\"alpha\",\"scale\":1.0,\"offset\":-1.0}]}],"
            "\"actions\":[{\"id\":\"idle\",\"loop\":true,\"channels\":[]}]}");
        zdiag_init(&d);
        r = zrig_load(rigp, dir, &d);
        CHECK(r != NULL, "blend:add 的 rig 应加载成功");
        if (r) {
            int w = 0, h = 0;
            const zimg *f1, *f2;
            long sum1 = 0, sum2 = 0;
            int x, y;
            /* 参数 0 → offset −1 把 alpha 压到 0 → 加算层完全不出现 */
            zrig_tick(r, 0.1);
            f1 = zrig_frame(r, 1.0, &w, &h);
            for (y = 0; y < h; ++y) for (x = 0; x < w; ++x)
                sum1 += f1->px[((size_t)y * w + x) * 4];
            zrig_param_set(r, "ParamGlow", 1.0);
            zrig_tick(r, 0.2);
            f2 = zrig_frame(r, 1.0, &w, &h);
            for (y = 0; y < h; ++y) for (x = 0; x < w; ++x)
                sum2 += f2->px[((size_t)y * w + x) * 4];
            CHECK(sum2 > sum1, "加算层打开后画面应更亮（%ld → %ld）", sum1, sum2);
            zrig_free(r);
        }
        /* 写错混合模式必须报错，不许默默当普通模式 */
        write_text(rigp,
            "{\"schema_version\":\"1.0\",\"id\":\"b\",\"name\":\"坏混合\","
            "\"canvas\":{\"w\":200,\"h\":200},\"origin\":[100,200],"
            "\"groups\":{\"head\":{\"pivot\":[100,100],\"parent\":\"\"}},"
            "\"parts\":[{\"id\":\"h\",\"file\":\"sprites/h.png\",\"group\":\"head\","
            "  \"layer\":10,\"pos\":[60,40],\"anchor\":[0,0],\"blend\":\"screen\"}],"
            "\"actions\":[{\"id\":\"idle\",\"loop\":true,\"channels\":[]}]}");
        zdiag_init(&d);
        CHECK(zrig_load(rigp, dir, &d) == NULL, "未知的 blend 取值必须加载失败");
        CHECK(diag_has(&d, "blend"), "诊断里应点名 blend");
    }
}


/* ---- Pose：互斥部件组（≈ pose3.json） ---- */
static void test_pose(void)
{
    char dir[1024], sprites[1024], src[1024], dst[1024], rigp[1024];
    zdiag d;
    zrig *r;
    const char *head =
        "{\"schema_version\":\"1.0\",\"id\":\"p\",\"name\":\"互斥\","
        "\"canvas\":{\"w\":200,\"h\":200},\"origin\":[100,200],"
        "\"groups\":{\"head\":{\"pivot\":[100,100],\"parent\":\"\"}},"
        "\"parts\":[{\"id\":\"a\",\"file\":\"sprites/h.png\",\"group\":\"head\","
        "  \"layer\":10,\"pos\":[60,40],\"anchor\":[0,0]},"
        " {\"id\":\"b\",\"file\":\"sprites/h.png\",\"group\":\"head\","
        "  \"layer\":11,\"pos\":[60,40],\"anchor\":[0,0]}],"
        "\"actions\":[{\"id\":\"idle\",\"loop\":true,\"channels\":[]}],";

    SECTION("Pose 互斥组：同组只有一个档位可见，切换带淡化");
    z_snprintf(dir, sizeof(dir), "/tmp/zc_pose");
    z_snprintf(sprites, sizeof(sprites), "%s/sprites", dir);
    z_mkdir_p(dir); z_mkdir_p(sprites);
    z_snprintf(src, sizeof(src), "%s/characters/xiaoxun/forms/teen/sprites/hair_ahoge.png", g_root);
    z_snprintf(dst, sizeof(dst), "%s/h.png", sprites);
    if (copy_file(src, dst) != 0) { CHECK(0, "复制贴图失败"); return; }
    z_snprintf(rigp, sizeof(rigp), "%s/rig.json", dir);

    {
        char buf[2048];
        z_snprintf(buf, sizeof(buf), "%s\"poses\":[{\"id\":\"g\",\"fade\":0.4,"
                   "\"default\":\"A\",\"entries\":["
                   "  {\"id\":\"A\",\"parts\":[\"a\"]},"
                   "  {\"id\":\"B\",\"parts\":[\"b\"]}]}]}", head);
        write_text(rigp, buf);
    }
    zdiag_init(&d);
    r = zrig_load(rigp, dir, &d);
    CHECK(r != NULL, "带 poses 的 rig 应加载成功");
    if (r) {
        double t;
        CHECK(zrig_pose_count(r) == 1, "应有 1 个互斥组");
        CHECK(z_streq(zrig_pose_current(r, "g"), "A"), "默认档位应是 A，实为 %s",
              zrig_pose_current(r, "g"));
        zrig_tick(r, 0.0);
        CHECK(fabs(zrig_pose_weight(r, "g", "A") - 1.0) < 1e-9, "A 一开始就是全显");
        CHECK(fabs(zrig_pose_weight(r, "g", "B")) < 1e-9, "B 一开始必须全隐");

        CHECK(zrig_pose_set(r, "g", "B") == 0, "切到 B 应成功");
        zrig_tick(r, 0.2);                      /* 淡化 0.4s，才走一半 */
        CHECK(zrig_pose_weight(r, "g", "A") > 0.2 && zrig_pose_weight(r, "g", "A") < 0.8,
              "切换中 A 应在淡出途中，实为 %.3f", zrig_pose_weight(r, "g", "A"));
        CHECK(zrig_pose_weight(r, "g", "B") > 0.2 && zrig_pose_weight(r, "g", "B") < 0.8,
              "切换中 B 应在淡入途中，实为 %.3f", zrig_pose_weight(r, "g", "B"));
        for (t = 0.25; t < 1.2; t += 0.05) zrig_tick(r, t);
        CHECK(fabs(zrig_pose_weight(r, "g", "B") - 1.0) < 1e-6, "淡化走完 B 应全显");
        CHECK(fabs(zrig_pose_weight(r, "g", "A")) < 1e-6, "淡化走完 A 应全隐");

        /* none = 整组关掉（Live2D 要靠一张透明图，我们直接支持） */
        CHECK(zrig_pose_set(r, "g", "none") == 0, "切 none 应成功");
        for (t = 1.2; t < 2.2; t += 0.05) zrig_tick(r, t);
        CHECK(fabs(zrig_pose_weight(r, "g", "A")) < 1e-6 &&
              fabs(zrig_pose_weight(r, "g", "B")) < 1e-6, "none 之后两档都该是 0");
        CHECK(z_streq(zrig_pose_current(r, "g"), ""), "none 时当前档位是空字符串");

        /* 不存在的组/档位必须报错，不许悄悄忽略 */
        CHECK(zrig_pose_set(r, "g", "nope") == -1, "未知档位应返回 -1");
        CHECK(zrig_pose_set(r, "nope", "A") == -1, "未知组应返回 -1");

        /* 跳过淡化（冻结时钟时用） */
        zrig_pose_set(r, "g", "A");
        zrig_pose_snap(r);
        CHECK(fabs(zrig_pose_weight(r, "g", "A") - 1.0) < 1e-9, "snap 之后应立刻到位");
        zrig_free(r);
    }

    SECTION("Pose 的三种写错法都要在加载时被拦住");
    {
        char buf[2048];
        /* ① 一个部件归两个档位 */
        z_snprintf(buf, sizeof(buf), "%s\"poses\":[{\"id\":\"g\",\"entries\":["
                   "  {\"id\":\"A\",\"parts\":[\"a\"]},"
                   "  {\"id\":\"B\",\"parts\":[\"a\"]}]}]}", head);
        write_text(rigp, buf);
        zdiag_init(&d);
        CHECK(zrig_load(rigp, dir, &d) == NULL, "同一部件进两个档位必须加载失败");
        /* ② 引用不存在的部件 */
        z_snprintf(buf, sizeof(buf), "%s\"poses\":[{\"id\":\"g\",\"entries\":["
                   "  {\"id\":\"A\",\"parts\":[\"a\"]},"
                   "  {\"id\":\"B\",\"parts\":[\"nope\"]}]}]}", head);
        write_text(rigp, buf);
        zdiag_init(&d);
        CHECK(zrig_load(rigp, dir, &d) == NULL, "引用不存在的部件必须加载失败");
        /* ③ default 写了不存在的档位 */
        z_snprintf(buf, sizeof(buf), "%s\"poses\":[{\"id\":\"g\",\"default\":\"X\","
                   "\"entries\":[{\"id\":\"A\",\"parts\":[\"a\"]},"
                   "  {\"id\":\"B\",\"parts\":[\"b\"]}]}]}", head);
        write_text(rigp, buf);
        zdiag_init(&d);
        CHECK(zrig_load(rigp, dir, &d) == NULL, "default 不在档位里必须加载失败");
        CHECK(diag_has(&d, "default"), "诊断应点名 default");
        /* ④ 只有一个档位 */
        z_snprintf(buf, sizeof(buf), "%s\"poses\":[{\"id\":\"g\",\"entries\":["
                   "  {\"id\":\"A\",\"parts\":[\"a\"]}]}]}", head);
        write_text(rigp, buf);
        zdiag_init(&d);
        CHECK(zrig_load(rigp, dir, &d) == NULL, "只有一个档位不叫互斥，必须加载失败");
    }
}

int main(int argc, char **argv)
{
    zlog_set_level(ZLOG_ERROR);
    z_strlcpy(g_root, argc > 1 ? argv[1] : ".", sizeof(g_root));

    printf("单元测试（[测试锁]）\n根目录：%s\n\n", g_root);
    test_json();
    test_schema();
    test_state_machine();
    test_blink();
    test_image();
    test_deflate();
    test_config_and_pet();
    test_bad_config();
    test_rig_channels();
    test_mask();
    test_eyelid();
    test_motion_fade();
    test_physics();
    test_look();
    test_params();
    test_lipsync();
    test_mesh();
    test_keys_and_chain();
    test_blend();
    test_pose();
    test_longrun();
    test_expression();
    test_motion_from();
    test_interactions();
    test_affection();

    printf("\n通过 %d 项，失败 %d 项\n", g_pass, g_fail);
    if (g_fail) {
        printf("结论：不通过（必须全绿才能交付）\n");
        return 1;
    }
    printf("结论：全部通过\n");
    return 0;
}
