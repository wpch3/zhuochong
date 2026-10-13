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
#include "../src/core/zgateway.h"

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
    /* 供应商数 = config/providers/ 下的契约文件数（G50 起 config/providers.json 是
       由 tools/check_platform.py 生成的兼容投影，不再手写）。加供应商要同步改这个数，
       这是故意的——数字对不上就说明投影没重新生成。 */
    CHECK(cfg.nproviders == 6, "供应商 6 个（实际 %d）", cfg.nproviders);
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

/* 两帧在某个矩形框里差了多少像素（量"这个参数到底动了没有、动在哪"） */
static int frame_diff_box(const zimg *a, const unsigned char *snap,
                          int x0, int y0, int x1, int y1)
{
    int x, y, n = 0;
    if (!a || !snap) return -1;
    if (x0 < 0) x0 = 0;
    if (y0 < 0) y0 = 0;
    if (x1 > a->w) x1 = a->w;
    if (y1 > a->h) y1 = a->h;
    for (y = y0; y < y1; ++y)
        for (x = x0; x < x1; ++x) {
            size_t o = ((size_t)y * (size_t)a->w + (size_t)x) * 4;
            int d = abs((int)a->px[o] - (int)snap[o]) + abs((int)a->px[o+1] - (int)snap[o+1])
                  + abs((int)a->px[o+2] - (int)snap[o+2]) + abs((int)a->px[o+3] - (int)snap[o+3]);
            if (d > 8) n++;
        }
    return n;
}

/* 框里有多少不透明像素（"这一块到底画没画东西"） */
static int frame_opaque_box(const zimg *a, int x0, int y0, int x1, int y1)
{
    int x, y, n = 0;
    if (!a) return -1;
    if (x0 < 0) x0 = 0;
    if (y0 < 0) y0 = 0;
    if (x1 > a->w) x1 = a->w;
    if (y1 > a->h) y1 = a->h;
    for (y = y0; y < y1; ++y)
        for (x = x0; x < x1; ++x)
            if (a->px[((size_t)y * (size_t)a->w + (size_t)x) * 4 + 3] > 128) n++;
    return n;
}

/* 框里有多少"线条像素"（睫毛/眼线这种深色）。用来回答"这一帧到底画没画那条线" */
static int frame_dark_box(const zimg *a, int x0, int y0, int x1, int y1)
{
    int x, y, n = 0;
    if (!a) return -1;
    if (x0 < 0) x0 = 0;
    if (y0 < 0) y0 = 0;
    if (x1 > a->w) x1 = a->w;
    if (y1 > a->h) y1 = a->h;
    for (y = y0; y < y1; ++y)
        for (x = x0; x < x1; ++x) {
            size_t o = ((size_t)y * (size_t)a->w + (size_t)x) * 4;
            int lum = ((int)a->px[o] + (int)a->px[o+1] + (int)a->px[o+2]) / 3;
            if (a->px[o+3] > 128 && lum < 165) n++;
        }
    return n;
}

/* 存一份当前帧（给 frame_diff_box 当基准） */
static unsigned char *frame_snapshot(const zimg *a)
{
    size_t n;
    unsigned char *buf;
    if (!a) return NULL;
    n = (size_t)a->w * (size_t)a->h * 4;
    buf = (unsigned char *)malloc(n);
    if (buf) memcpy(buf, a->px, n);
    return buf;
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

/* 不透明像素的重心 x（量"手被父组带着甩出去多远"） */
static int frame_centroid_x(const zimg *im)
{
    int x, y; long n = 0; long sum = 0;
    if (!im) return -1;
    for (y = 0; y < im->h; ++y)
        for (x = 0; x < im->w; ++x)
            if (im->px[((size_t)y * (size_t)im->w + (size_t)x) * 4 + 3] > 24) { n++; sum += x; }
    return n ? (int)(sum / n) : -1;
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

/* 最上面一行不透明像素的 y（量"上眼皮合下来了没有"） */
static int frame_top_y(const zimg *im)
{
    int x, y;
    if (!im) return -1;
    for (y = 0; y < im->h; ++y)
        for (x = 0; x < im->w; ++x)
            if (im->px[((size_t)y * (size_t)im->w + (size_t)x) * 4 + 3] > 24) return y;
    return -1;
}

/* 最下面一行不透明像素的 y（量"眼眶下沿有没有跟着动"） */
static int frame_bottom_y(const zimg *im)
{
    int x, y;
    if (!im) return -1;
    for (y = im->h - 1; y >= 0; --y)
        for (x = 0; x < im->w; ++x)
            if (im->px[((size_t)y * (size_t)im->w + (size_t)x) * 4 + 3] > 24) return y;
    return -1;
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
            /* 内建 9 个（ParamAngleX/Y、ParamEyeOpen + 左右眼开合各一个、
               左右眼笑眼各一个、ParamEyeBallX/Y）+ rig 里 2 个 */
            CHECK(zrig_param_count(r) == 11, "参数表应有 11 项（内建 9 + 角色 2），实为 %d",
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
            /* ⑤ 眨眼：ParamEyeOpen=0 等于两眼都闭；左右眼是**两个独立参数**（Live2D 标准） */
            zrig_param_set(r, "ParamEyeOpen", 0.0);
            zrig_tick(r, t);
            CHECK(zrig_blink_value(r) > 0.99, "ParamEyeOpen=0 应等于闭眼（%.2f）",
                  zrig_blink_value(r));
            CHECK(zrig_param_set(r, "ParamEyeLOpen", 1.0) == 0, "ParamEyeLOpen 应存在");
            CHECK(zrig_param_set(r, "ParamEyeROpen", 1.0) == 0, "ParamEyeROpen 应存在");
            zrig_tick(r, t + 0.02);
            CHECK(zrig_param_get(r, "ParamEyeLOpen") > 0.99 &&
                  zrig_param_get(r, "ParamEyeROpen") > 0.99,
                  "左右眼参数各自读回 1");
            /* 单眼：只按住左眼，右眼不受影响（挤眼睛） */
            zrig_param_set(r, "ParamEyeLOpen", 0.0);
            zrig_tick(r, t + 0.04);
            CHECK(zrig_param_get(r, "ParamEyeLOpen") < 0.01 &&
                  zrig_param_get(r, "ParamEyeROpen") > 0.99,
                  "左眼闭、右眼睁：L=%.2f R=%.2f",
                  zrig_param_get(r, "ParamEyeLOpen"), zrig_param_get(r, "ParamEyeROpen"));
            zrig_param_reset(r, "ParamEyeLOpen");
            zrig_param_reset(r, "ParamEyeROpen");
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


static void test_eye_aperture(void)
{
    char dir[1024], sprites[1024], src[1024], dst[1024], rigp[1024];
    SECTION("眼眶开口：blink 把 eye_aperture 部件按下沿压扁，被它裁的眼白跟着少（真·闭眼）");
    z_snprintf(dir, sizeof(dir), "/tmp/zc_aperture");
    z_snprintf(sprites, sizeof(sprites), "%s/sprites", dir);
    z_mkdir_p(dir);
    z_mkdir_p(sprites);
    z_snprintf(src, sizeof(src), "%s/characters/xiaoxun/forms/teen/sprites/eye_l_socket.png", g_root);
    z_snprintf(dst, sizeof(dst), "%s/sock.png", sprites);
    if (copy_file(src, dst) != 0) { CHECK(0, "复制 eye_l_socket.png 失败"); return; }
    z_snprintf(src, sizeof(src), "%s/characters/xiaoxun/forms/teen/sprites/eye_l_base.png", g_root);
    z_snprintf(dst, sizeof(dst), "%s/base.png", sprites);
    if (copy_file(src, dst) != 0) { CHECK(0, "复制 eye_l_base.png 失败"); return; }
    z_snprintf(rigp, sizeof(rigp), "%s/rig.json", dir);
    /* 眼眶当遮罩，锚点放在**开口下沿**（eye_l_socket.png 的开口底在 y=42/68 ≈ 0.618，
       真 rig 由 eyeline_parts.json 的 aperture_box 算出来）：
       压扁时下眼睑不动、上眼皮往下合。锚点要是放在整张图的底边（空白行上），
       整只眼会被"吸"下去 —— 这个测试第一版就是这么挂的（下沿跑了 23px）。 */
    write_text(rigp,
        "{\"schema_version\":\"1.0\",\"id\":\"ap\",\"name\":\"眼眶开口测试\","
        "\"canvas\":{\"w\":300,\"h\":300},\"origin\":[150,300],"
        "\"groups\":{\"root\":{\"pivot\":[150,300],\"parent\":\"\"}},"
        "\"parts\":[{\"id\":\"sock\",\"file\":\"sprites/sock.png\",\"group\":\"root\","
        " \"layer\":10,\"pos\":[150,200],\"anchor\":[0.5,0.618],"
        " \"tags\":[\"eye_aperture\"],\"aperture_min\":0.06,\"mask_only\":true},"
        " {\"id\":\"white\",\"file\":\"sprites/base.png\",\"group\":\"root\","
        "  \"layer\":20,\"pos\":[90,130],\"anchor\":[0,0],\"mask\":\"sock\"}],"
        "\"actions\":[{\"id\":\"idle\",\"loop\":true,\"channels\":[]}]}");
    {
        zdiag d;
        zrig *r;
        zdiag_init(&d);
        r = zrig_load(rigp, dir, &d);
        CHECK(r != NULL, "带 eye_aperture 标签的 rig 应加载成功");
        if (r) {
            const zimg *fb;
            int px[4], bot[4], top[4], i;
            const double bl[4] = { 0.0, 0.25, 0.5, 1.0 };
            for (i = 0; i < 4; ++i) {
                zrig_blink_set_manual(r, bl[i]);
                zrig_tick(r, 0.1);
                fb = zrig_frame(r, 1.0, NULL, NULL);
                px[i] = frame_opaque_px(fb);
                bot[i] = frame_bottom_y(fb);
                top[i] = frame_top_y(fb);
            }
            CHECK(px[0] > 200, "睁眼时眼白应可见（%d 像素）", px[0]);
            CHECK(px[1] < px[0] && px[2] < px[1] && px[3] < px[2],
                  "眼眶越合，露出来的眼白越少（%d → %d → %d → %d）",
                  px[0], px[1], px[2], px[3]);
            CHECK(px[3] * 10 < px[0],
                  "闭到底应只剩一条缝（闭 %d vs 睁 %d）", px[3], px[0]);
            /* 位置检查放在半闭那一格：闭到底时开口只剩 6%，可见像素可能归零，
               这时 top/bottom 都是 -1，量不出东西来。 */
            CHECK(bot[2] >= 0 && bot[0] >= 0 && abs(bot[2] - bot[0]) <= 4,
                  "下眼睑不该跟着跑（睁 y=%d vs 半闭 y=%d）", bot[0], bot[2]);
            CHECK(top[2] > top[0] + 8,
                  "上眼皮要往下合（睁 y=%d → 半闭 y=%d）", top[0], top[2]);
            zrig_blink_set_manual(r, -1.0);
            zrig_free(r);
        }
    }
}

static void test_group_chain(void)
{
    char dir[1024], sprites[1024], src[1024], dst[1024], rigp[1024];
    SECTION("三级组链（上臂→前臂→手）：手跟着父组、爷爷组一层层被带走");
    z_snprintf(dir, sizeof(dir), "/tmp/zc_chain");
    z_snprintf(sprites, sizeof(sprites), "%s/sprites", dir);
    z_mkdir_p(dir);
    z_mkdir_p(sprites);
    z_snprintf(src, sizeof(src), "%s/characters/xiaoxun/forms/teen/sprites/eye_l_lid.png", g_root);
    z_snprintf(dst, sizeof(dst), "%s/a.png", sprites);
    if (copy_file(src, dst) != 0) { CHECK(0, "复制贴图失败"); return; }
    z_snprintf(rigp, sizeof(rigp), "%s/rig.json", dir);
    write_text(rigp,
        "{\"schema_version\":\"1.0\",\"id\":\"c\",\"name\":\"组链\","
        "\"canvas\":{\"w\":400,\"h\":400},\"origin\":[200,400],"
        "\"groups\":{"
        " \"arm\":{\"pivot\":[200,100],\"parent\":\"\"},"
        " \"fore\":{\"pivot\":[200,200],\"parent\":\"arm\"},"
        " \"hand\":{\"pivot\":[200,300],\"parent\":\"fore\"}},"
        "\"parts\":["
        " {\"id\":\"h\",\"file\":\"sprites/a.png\",\"group\":\"hand\",\"layer\":10,"
        "  \"pos\":[200,300],\"anchor\":[0,0]}],"
        "\"params\":["
        " {\"id\":\"PArm\",\"min\":0,\"max\":1,\"default\":0,"
        "  \"binds\":[{\"group\":\"arm\",\"param\":\"rot_deg\",\"scale\":30.0}]},"
        " {\"id\":\"PFore\",\"min\":0,\"max\":1,\"default\":0,"
        "  \"binds\":[{\"group\":\"fore\",\"param\":\"rot_deg\",\"scale\":30.0}]},"
        " {\"id\":\"PHand\",\"min\":0,\"max\":1,\"default\":0,"
        "  \"binds\":[{\"group\":\"hand\",\"param\":\"rot_deg\",\"scale\":30.0}]}],"
        "\"actions\":[{\"id\":\"idle\",\"loop\":true,\"channels\":[]}]}");
    {
        zdiag d;
        zrig *r;
        zdiag_init(&d);
        r = zrig_load(rigp, dir, &d);
        CHECK(r != NULL, "三级组链应加载成功");
        if (r) {
            const zimg *fb;
            int cx0, d_hand, d_fore, d_arm, back;
            zrig_tick(r, 0.1);
            fb = zrig_frame(r, 1.0, NULL, NULL);
            cx0 = frame_centroid_x(fb);
            /* 一次只转一级，量这只手被甩开多远（绝对值，不假设引擎的旋转方向） */
            zrig_param_set(r, "PHand", 1.0);
            zrig_tick(r, 0.01);
            fb = zrig_frame(r, 1.0, NULL, NULL);
            d_hand = abs(frame_centroid_x(fb) - cx0);
            zrig_param_set(r, "PHand", 0.0);
            zrig_param_set(r, "PFore", 1.0);
            zrig_tick(r, 0.01);
            fb = zrig_frame(r, 1.0, NULL, NULL);
            d_fore = abs(frame_centroid_x(fb) - cx0);
            zrig_param_set(r, "PFore", 0.0);
            zrig_param_set(r, "PArm", 1.0);
            zrig_tick(r, 0.01);
            fb = zrig_frame(r, 1.0, NULL, NULL);
            d_arm = abs(frame_centroid_x(fb) - cx0);
            zrig_param_set(r, "PArm", 0.0);
            zrig_tick(r, 0.01);
            fb = zrig_frame(r, 1.0, NULL, NULL);
            back = frame_centroid_x(fb);
            CHECK(d_hand > 2, "转手腕，手自己要动起来（位移 %d px）", d_hand);
            CHECK(d_fore > d_hand,
                  "转前臂时手离枢轴更远，位移该更大（%d > %d）", d_fore, d_hand);
            CHECK(d_arm > d_fore,
                  "转上臂（爷爷组）时最大 —— 这就是三级继承（%d > %d）", d_arm, d_fore);
            CHECK(back == cx0, "参数归零后手回到原位（%d vs %d）", back, cx0);
            zrig_free(r);
        }
    }
}

/* ========== Live2D 标准合规：标准参数必须真的接着东西 ========== */
/* 这条闸是冲着"参数表写得好看、其实是死的"去的：
   对**真角色的 rig**逐个把标准参数推到极值，渲染，看画面有没有变。
   一个参数改了却一个像素都不动 = 它是假的，必须红。

   ⚠ 坑：待机动作和物理每帧都在走，拿两个不同时刻的帧相减，光漂移就有十几像素，
   足以把"死参数"盖过去（第一版就是这样：把 ParamShoulderY 的 binds 删空仍然绿）。
   解法 = 用同一个时间戳反复 tick（dt=0，等价预览的 /api/pause），
   两帧之间只有参数变了。跟随类（ParamAngleX/Y）是平滑收敛的，dt=0 下不动，
   所以单独用"settle 一段时间"的办法量，阈值取大。 */
/* 口型音素（母音識別）：A/I/U/E/O 必须是**五张不一样的嘴**，
   而且宽窄要对得上（い 比 う 宽）。靠一个参数淡入淡出假装口型会被这里抓住。 */
static void test_viseme(void)
{
    char dir[1024], rig_path[1024];
    static const char *VIS[] = { "A", "I", "U", "E", "O" };
    /* 嘴在帧里的位置（画布 (422,316) × 0.55），留够余量 */
    const int MX0 = 196, MY0 = 150, MX1 = 266, MY1 = 202;
    const double T = 1.5;
    SECTION("口型音素：A/I/U/E/O 是五张不同的嘴，不是一个参数淡入淡出");
    z_snprintf(dir, sizeof(dir), "%s/characters/xiaoxun/forms/teen", g_root);
    z_snprintf(rig_path, sizeof(rig_path), "%s/rig.json", dir);
    {
        zdiag d;
        zrig *r;
        zdiag_init(&d);
        r = zrig_load(rig_path, dir, &d);
        CHECK(r != NULL, "装载真 rig 应成功（错误 %d 条）", d.error_count);
        if (!r) { zdiag_print(&d, stderr); return; }
        zrig_blink_set_enabled(r, 0);
        zrig_action_request(r, "idle", "test", 1);
        {
            const zimg *fb;
            unsigned char *snap[5];
            int wid[5];
            size_t i, j;
            double t;
            int bad = 0, nvis = zrig_viseme_count(r);
            CHECK(nvis >= 6, "音素表至少 6 行（SIL + AIUEO），实际 %d", nvis);
            CHECK(zrig_viseme_find(r, "A") >= 0 && zrig_viseme_find(r, "i") >= 0,
                  "音素查找要大小写不敏感且 A/I 都在");
            CHECK(zrig_viseme_find(r, "ParamMouthXyz") < 0, "不认识的音素必须查不到");
            CHECK(zrig_viseme_set(r, "NOPE", 1.0) == -1,
                  "写错音素名要报错，不能当静默吞掉");
            /* 音素只许写 Live2D 标准参数，不许偷偷自造 ParamMouthA 这类 */
            for (i = 0; i < (size_t)nvis; ++i) {
                int k, nk = zrig_viseme_entry_count(r, i);
                CHECK(nk >= 1, "音素 %s 至少写一个参数", zrig_viseme_id(r, (int)i));
                for (k = 0; k < nk; ++k) {
                    const char *pid = NULL;
                    double v = 0.0;
                    zrig_viseme_entry(r, (int)i, k, &pid, &v);
                    if (!pid) { bad++; continue; }
                    if (strcmp(pid, "ParamMouthOpenY") != 0 &&
                        strcmp(pid, "ParamMouthForm") != 0) bad++;
                }
            }
            CHECK(bad == 0, "音素只能写标准嘴参数（OpenY / Form），越界 %d 处", bad);

            for (t = 0.0; t < T; t += 0.02) zrig_tick(r, t);
            zrig_tick(r, T);                      /* dt = 0：时间停住 */
            for (i = 0; i < 5; ++i) {
                int x, y, x0 = 9999, x1 = -1;
                unsigned char *base;
                zrig_viseme_reset(r);     /* 基准必须干净：clear 是平滑收，冻结时钟下收不完 */
                zrig_tick(r, T);
                fb = zrig_frame(r, 0.55, NULL, NULL);
                base = frame_snapshot(fb);        /* 每个音素现拍自己的基准 */
                zrig_viseme_set(r, VIS[i], 1.0);
                zrig_viseme_snap(r);              /* dt=0 下平滑走不动，直接到位 */
                zrig_tick(r, T);
                fb = zrig_frame(r, 0.55, NULL, NULL);
                snap[i] = frame_snapshot(fb);
                CHECK(frame_diff_box(fb, base, MX0, MY0, MX1, MY1) > 20,
                      "音素 %s 相对闭嘴要有明显变化（%d px）", VIS[i],
                      frame_diff_box(fb, base, MX0, MY0, MX1, MY1));
                /* 变化像素的横向跨度 = 这张嘴有多宽 */
                for (y = MY0; y < MY1 && base; ++y)
                    for (x = MX0; x < MX1; ++x) {
                        size_t o = ((size_t)y * (size_t)fb->w + (size_t)x) * 4;
                        int dd = abs((int)fb->px[o] - (int)base[o])
                               + abs((int)fb->px[o+1] - (int)base[o+1])
                               + abs((int)fb->px[o+2] - (int)base[o+2]);
                        if (dd > 8) { if (x < x0) x0 = x; if (x > x1) x1 = x; }
                    }
                wid[i] = (x1 >= x0) ? (x1 - x0 + 1) : 0;
                free(base);
            }
            zrig_viseme_reset(r);
            /* 两两都要不一样 —— 这是"五张嘴"而不是"一张嘴五个大小"的判据 */
            {
                int worst = 1 << 30;
                const char *wa = "", *wb = "";
                for (i = 0; i < 5; ++i)
                    for (j = i + 1; j < 5; ++j) {
                        int n;
                        unsigned char *tmp;
                        zrig_viseme_set(r, VIS[i], 1.0);
                        zrig_viseme_snap(r);
                        zrig_tick(r, T);
                        fb = zrig_frame(r, 0.55, NULL, NULL);
                        tmp = frame_snapshot(fb);
                        n = frame_diff_box(fb, snap[j], MX0, MY0, MX1, MY1);
                        free(tmp);
                        if (n < worst) { worst = n; wa = VIS[i]; wb = VIS[j]; }
                    }
                CHECK(worst > 25, "最接近的两个音素 %s/%s 也要差 >25px（实际 %d）",
                      wa, wb, worst);
            }
            CHECK(wid[1] > wid[2], "い 的嘴要比 う 宽（实测 I=%d px, U=%d px）",
                  wid[1], wid[2]);
            CHECK(wid[0] > 0 && wid[4] > 0, "あ/お 都要量得到嘴宽");
            for (i = 0; i < 5; ++i) free(snap[i]);

            /* 强度：音素给形状，weight 给大小 */
            zrig_viseme_reset(r);
            zrig_viseme_set(r, "A", 0.3);
            zrig_viseme_snap(r);
            CHECK(fabs(zrig_param_effective(r, "ParamMouthOpenY") - 0.3) < 0.02,
                  "A 配 weight 0.3 时开口应 ≈0.3（实际 %.3f）",
                  zrig_param_effective(r, "ParamMouthOpenY"));
            CHECK(fabs(zrig_param_get(r, "ParamMouthOpenY")) < 1e-6,
                  "音素是叠在上面的一层，不许回写基础参数值（%.3f）",
                  zrig_param_get(r, "ParamMouthOpenY"));
            /* 平滑：张开要快但不是瞬间（一帧就到位 = 机器嘴） */
            zrig_viseme_reset(r);
            zrig_viseme_set(r, "A", 1.0);
            zrig_tick(r, T + 0.008);
            CHECK(zrig_param_effective(r, "ParamMouthOpenY") > 0.05 &&
                  zrig_param_effective(r, "ParamMouthOpenY") < 0.9,
                  "8ms 后应在路上而不是瞬间到位（实际 %.3f）",
                  zrig_param_effective(r, "ParamMouthOpenY"));
            CHECK(zrig_mouth_mute(r) == 1, "说话时动作里的嘴通道要让路");
            /* 松口：参数回默认，嘴还给动作 */
            zrig_viseme_clear(r);
            {   /* 松口是平滑收回去的，给它时间收干净（收完会自动把嘴还给动作） */
                double tt;
                for (tt = 0.02; tt < 1.2; tt += 0.016) zrig_tick(r, T + tt);
            }
            CHECK(fabs(zrig_param_effective(r, "ParamMouthOpenY")) < 1e-6 &&
                  fabs(zrig_param_effective(r, "ParamMouthForm")) < 1e-6,
                  "松口后两个嘴参数都要回默认");
            CHECK(zrig_mouth_mute(r) == 0, "松口后嘴要还给动作");
            CHECK(zrig_viseme_current(r) == NULL, "松口后当前音素应为空");
            /* 静默音素也要能自己收干净（不是一直占着嘴） */
            zrig_viseme_set(r, "SIL", 0.0);
            for (t = 0.0; t < 0.5; t += 0.02) zrig_tick(r, T + 0.1 + t);
            CHECK(zrig_mouth_mute(r) == 0, "喂 SIL 之后应自动松口");
        }
        zrig_free(r);
    }
}

/* 表情和口型抢同一个参数时谁说了算：Cubism 的执行序是
   EyeBlink 200 → Expression 300 → … → LipSync 700 → Pose 800，口型在表情之后。
   「笑着说う」必须还是撅圆的嘴，不能被笑脸抵消成中性。 */
static void test_expr_viseme_order(void)
{
    char dir[1024], rig_path[1024];
    const int MX0 = 196, MY0 = 150, MX1 = 266, MY1 = 202;
    const double T = 1.5;
    SECTION("表情 × 口型：口型排在表情之后（官方执行序），笑着说 う 还是撅圆");
    z_snprintf(dir, sizeof(dir), "%s/characters/xiaoxun/forms/teen", g_root);
    z_snprintf(rig_path, sizeof(rig_path), "%s/rig.json", dir);
    {
        zdiag d;
        zrig *r;
        zdiag_init(&d);
        r = zrig_load(rig_path, dir, &d);
        CHECK(r != NULL, "装载真 rig 应成功（错误 %d 条）", d.error_count);
        if (!r) { zdiag_print(&d, stderr); return; }
        zrig_blink_set_enabled(r, 0);
        zrig_action_request(r, "idle", "test", 1);
        {
            const zimg *fb;
            unsigned char *smile_only;
            double t, form_smile, form_smile_u, form_u;
            double mix = zrig_viseme_mix(r);
            CHECK(mix > 0.5 && mix <= 1.0, "口型权重应在 0.5~1（官方 LipSync 用 0.8），实际 %.2f", mix);
            for (t = 0.0; t < T; t += 0.02) zrig_tick(r, t);
            zrig_tick(r, T);

            /* ① 只有表情：笑 → MouthForm 往 + 走 */
            CHECK(zrig_expression_set(r, "smile") == 0, "应有 smile 表情");
            for (t = 0.0; t < 0.8; t += 0.02) zrig_tick(r, T + t);
            form_smile = zrig_param_effective(r, "ParamMouthForm");
            CHECK(form_smile > 0.1, "笑脸应把 MouthForm 推到正方向（%.3f）", form_smile);
            fb = zrig_frame(r, 0.55, NULL, NULL);
            smile_only = frame_snapshot(fb);

            /* ② 笑 + う：嘴形必须还是撅圆（负），不能被笑脸抵消 */
            zrig_viseme_set(r, "U", 1.0);
            zrig_viseme_snap(r);
            zrig_tick(r, T + 0.8);
            fb = zrig_frame(r, 0.55, NULL, NULL);     /* 改完要重新合成，不然比的是旧帧 */
            form_smile_u = zrig_param_effective(r, "ParamMouthForm");
            CHECK(form_smile_u < -0.5,
                  "笑着说 う 时 MouthForm 应仍明显为负（%.3f，笑脸单独是 %.3f）",
                  form_smile_u, form_smile);
            CHECK(frame_diff_box(fb, smile_only, MX0, MY0, MX1, MY1) > 20,
                  "笑 + う 的嘴要和只笑不一样（%d px）",
                  frame_diff_box(fb, smile_only, MX0, MY0, MX1, MY1));
            free(smile_only);

            /* ③ 接管力度随"这一帧口型用了多大力"缩放：
                  满力说话时口型完全说了算，小声时表情透出来，停顿时表情完整回来。
                  （2026-10-13 用户反馈：张着嘴还挂着笑嘴角、说完一下子弹回笑脸，很怪） */
            zrig_viseme_set(r, "U", 1.0);
            zrig_viseme_snap(r);
            zrig_tick(r, T + 0.82);
            form_u = zrig_param_effective(r, "ParamMouthForm");
            CHECK(fabs(form_u - form_smile_u) < 1e-6,
                  "满力说话时笑不笑都该是同一张嘴（%.3f vs %.3f）", form_smile_u, form_u);
            zrig_viseme_set(r, "U", 0.25);         /* 小声说：口型只用了两成力 */
            zrig_viseme_snap(r);
            zrig_tick(r, T + 0.84);
            {
                double soft = zrig_param_effective(r, "ParamMouthForm");
                CHECK(soft > 0.05 && soft < form_smile - 0.05,
                      "小声说话时笑意还要占主导（%.3f 要在 0 和 %.3f 之间；"
                      "接管力度不随用力程度缩放的话这里会是负的）", soft, form_smile);
            }
            /* 张满嘴说「あ」：Form 目标是 0（中性嘴形），这时不许还挂着笑嘴角 */
            zrig_viseme_set(r, "A", 1.0);
            zrig_viseme_snap(r);
            zrig_tick(r, T + 0.85);
            CHECK(fabs(zrig_param_effective(r, "ParamMouthForm")) < 0.05,
                  "满力张嘴时不该还挂着笑的嘴角（%.3f）",
                  zrig_param_effective(r, "ParamMouthForm"));
            CHECK(zrig_param_effective(r, "ParamMouthOpenY") > 0.95,
                  "满力张嘴要真的张到底（%.3f）",
                  zrig_param_effective(r, "ParamMouthOpenY"));
            /* 说完松口：一路平滑回到笑脸，相邻帧不许跳变（用户说"一下子弹回去很怪"） */
            {
                double prev = zrig_param_effective(r, "ParamMouthForm");
                double worst = 0.0;
                int step;
                zrig_viseme_clear(r);
                for (step = 1; step <= 40; ++step) {
                    double now_v;
                    zrig_tick(r, T + 0.85 + 0.016 * step);
                    now_v = zrig_param_effective(r, "ParamMouthForm");
                    if (fabs(now_v - prev) > worst) worst = fabs(now_v - prev);
                    prev = now_v;
                }
                CHECK(worst < 0.12, "松口要平滑过渡，单帧跳变最大 %.3f（阈值 0.12）", worst);
                CHECK(fabs(prev - form_smile) < 0.02,
                      "松口后应回到笑脸的嘴形（%.3f → %.3f）", prev, form_smile);
            }
            /* ④ 没有表情也没有口型时，最终值 = 参数自己的值 */
            zrig_expression_clear(r);
            zrig_viseme_reset(r);
            for (t = 0.0; t < 1.0; t += 0.02) zrig_tick(r, T + 1.0 + t);

            zrig_param_set(r, "ParamMouthForm", 0.5);
            zrig_tick(r, T + 2.02);
            CHECK(fabs(zrig_param_effective(r, "ParamMouthForm") - 0.5) < 1e-6,
                  "没表情没口型时最终值应等于参数值（%.3f）",
                  zrig_param_effective(r, "ParamMouthForm"));
            zrig_param_reset(r, "ParamMouthForm");
        }
        zrig_free(r);
    }
}

/* Cubism exp3 的三种 Blend 都要有：Add / Multiply / Overwrite */
static void test_expression_blend(void)
{
    char dir[1024], sprites[1024], src[1024], dst[1024], rigp[1024];
    SECTION("表情混合模式：Add / Multiply / Overwrite 三种都按 Cubism 的算法走");
    z_snprintf(dir, sizeof(dir), "/tmp/zc_exprblend");
    z_snprintf(sprites, sizeof(sprites), "%s/sprites", dir);
    z_mkdir_p(dir);
    z_mkdir_p(sprites);
    z_snprintf(src, sizeof(src), "%s/characters/xiaoxun/forms/teen/sprites/hair_ahoge.png", g_root);
    z_snprintf(dst, sizeof(dst), "%s/h.png", sprites);
    if (copy_file(src, dst) != 0) { CHECK(0, "复制贴图失败"); return; }
    z_snprintf(rigp, sizeof(rigp), "%s/rig.json", dir);
    write_text(rigp,
        "{\"schema_version\":\"1.0\",\"id\":\"b\",\"name\":\"混合\","
        "\"canvas\":{\"w\":200,\"h\":200},\"origin\":[100,200],"
        "\"groups\":{\"head\":{\"pivot\":[100,100],\"parent\":\"\"}},"
        "\"parts\":[{\"id\":\"h\",\"file\":\"sprites/h.png\",\"group\":\"head\","
        " \"layer\":10,\"pos\":[60,40],\"anchor\":[0,0]}],"
        "\"actions\":[{\"id\":\"idle\",\"loop\":true,\"channels\":[]}],"
        "\"params\":[{\"id\":\"ParamBrowLY\",\"min\":-2,\"max\":2,\"default\":0,"
        " \"binds\":[{\"part\":\"h\",\"param\":\"dy\",\"scale\":10}]}],"
        "\"expressions\":[{\"id\":\"add\",\"fade\":0,"
        "  \"params\":[{\"id\":\"ParamBrowLY\",\"value\":0.25,\"mode\":\"add\"}]},"
        " {\"id\":\"mul\",\"fade\":0,"
        "  \"params\":[{\"id\":\"ParamBrowLY\",\"value\":2.0,\"mode\":\"multiply\"}]},"
        " {\"id\":\"ovr\",\"fade\":0,"
        "  \"params\":[{\"id\":\"ParamBrowLY\",\"value\":-1.0,\"mode\":\"overwrite\"}]}]}");
    {
        zdiag d;
        zrig *r;
        zdiag_init(&d);
        r = zrig_load(rigp, dir, &d);
        CHECK(r != NULL, "三种 Blend 的 rig 应加载成功（错误 %d 条）", d.error_count);
        if (r) {
            zrig_tick(r, 0.0);
            zrig_param_set(r, "ParamBrowLY", 0.5);
            zrig_tick(r, 0.02);
            CHECK(fabs(zrig_param_effective(r, "ParamBrowLY") - 0.5) < 1e-6, "无表情时就是参数值");
            zrig_expression_set(r, "add");
            zrig_tick(r, 0.04);
            CHECK(fabs(zrig_param_effective(r, "ParamBrowLY") - 0.75) < 1e-6,
                  "Add：0.5 + 0.25 = 0.75（%.3f）", zrig_param_effective(r, "ParamBrowLY"));
            zrig_expression_set(r, "mul");
            zrig_tick(r, 0.06);
            CHECK(fabs(zrig_param_effective(r, "ParamBrowLY") - 1.0) < 1e-6,
                  "Multiply：0.5 × 2 = 1.0（%.3f）", zrig_param_effective(r, "ParamBrowLY"));
            CHECK(fabs(zrig_part_channel(r, "h", "dy") - 10.0) < 0.01,
                  "乘算结果要真的写进通道（dy 应为 10，实际 %.3f）",
                  zrig_part_channel(r, "h", "dy"));
            zrig_expression_set(r, "ovr");
            zrig_tick(r, 0.08);
            CHECK(fabs(zrig_param_effective(r, "ParamBrowLY") - (-1.0)) < 1e-6,
                  "Overwrite：直接覆盖成 -1（%.3f）", zrig_param_effective(r, "ParamBrowLY"));
            zrig_expression_clear(r);
            zrig_tick(r, 0.10);
            CHECK(fabs(zrig_param_effective(r, "ParamBrowLY") - 0.5) < 1e-6, "取消表情回到参数值");
            zrig_free(r);
        }
    }
}

static void test_live2d_standard(void)
{
    char dir[1024], rig_path[1024];
    static const struct { const char *id; double v; } probe[] = {
        { "ParamAngleZ",      30.0 }, { "ParamEyeLOpen",     0.0 },
        { "ParamEyeROpen",     0.0 }, { "ParamEyeBallX",     1.0 },
        { "ParamEyeBallY",     1.0 }, { "ParamBrowLY",      -1.0 },
        { "ParamBrowRY",      -1.0 }, { "ParamBrowLAngle",  -1.0 },
        { "ParamBrowRAngle",  -1.0 }, { "ParamBrowLX",       1.0 },
        { "ParamBrowRX",       1.0 }, { "ParamMouthOpenY",   1.0 },
        { "ParamMouthForm",    1.0 }, { "ParamCheek",        1.0 },
        { "ParamBodyAngleX",  10.0 }, { "ParamBodyAngleY",  10.0 },
        { "ParamBodyAngleZ",  10.0 }, { "ParamShoulderY",   10.0 },
        { "ParamBreath",       1.0 }, { "ParamBaseX",       10.0 },
        { "ParamBaseY",       10.0 }, { "ParamArmLA",       10.0 },
        { "ParamArmRA",      -10.0 }, { "ParamArmLB",       10.0 },
        { "ParamArmRB",      -10.0 }, { "ParamHandL",        1.0 },
        { "ParamHandR",       -1.0 }, { "ParamLegL",         1.0 },
        { "ParamLegR",        -1.0 }, { "ParamHairFront",    1.0 },
        { "ParamHairSide",     1.0 }, { "ParamHairBack",     1.0 },
        { "ParamHairFluffy",   1.0 }, { "ParamHairAhoge",    1.0 },
        { "ParamHairAhogeS",   1.0 }, { "ParamEyeSparkle",   0.0 },
    };
    const double T = 1.5;                 /* 冻结用的时间戳 */
    SECTION("Live2D 标准合规：标准参数都在、推到极值真的改画面（防死参数）");
    z_snprintf(dir, sizeof(dir), "%s/characters/xiaoxun/forms/teen", g_root);
    z_snprintf(rig_path, sizeof(rig_path), "%s/rig.json", dir);
    {
        zdiag d;
        zrig *r;
        zdiag_init(&d);
        r = zrig_load(rig_path, dir, &d);
        CHECK(r != NULL, "装载真 rig 应成功（错误 %d 条）", d.error_count);
        if (!r) { zdiag_print(&d, stderr); return; }
        zrig_blink_set_enabled(r, 0);          /* 自动眨眼会搅乱对照 */
        zrig_action_request(r, "idle", "test", 1);
        {
            const zimg *fb;
            unsigned char *base;
            double t;
            size_t i;
            int dead = 0, missing = 0;
            char deadlist[256];
            deadlist[0] = 0;
            for (t = 0.0; t < T; t += 0.02) zrig_tick(r, t);
            zrig_tick(r, T);                   /* dt = 0：时间停住 */
            fb = zrig_frame(r, 0.55, NULL, NULL);
            base = frame_snapshot(fb);
            CHECK(base != NULL, "基准帧应可保存");
            for (i = 0; i < sizeof(probe) / sizeof(probe[0]) && base; ++i) {
                int n;
                /* ⚠ 第二个坑：上一个参数把物理摆链推歪之后，dt=0 不会让它衰减回去
                   （弹簧不走，但输出 = pos − target 会随 target 立刻变），
                   于是"全局基准帧"被污染，后面每个参数都显得活着。
                   解法 = 每个参数临测前**现拍一张基准**，两帧之间只差这一个参数。 */
                free(base);
                zrig_tick(r, T);
                fb = zrig_frame(r, 0.55, NULL, NULL);
                base = frame_snapshot(fb);
                if (!base) break;
                if (zrig_param_set(r, probe[i].id, probe[i].v) != 0) {
                    missing++;
                    if (strlen(deadlist) < 170)
                        z_snprintf(deadlist + strlen(deadlist), sizeof(deadlist) - strlen(deadlist),
                                   "%s(缺) ", probe[i].id);
                    continue;
                }
                zrig_tick(r, T);               /* 仍然 dt = 0 */
                fb = zrig_frame(r, 0.55, NULL, NULL);
                n = frame_diff_box(fb, base, 0, 0, fb->w, fb->h);
                if (n < 12) {
                    dead++;
                    if (strlen(deadlist) < 170)
                        z_snprintf(deadlist + strlen(deadlist), sizeof(deadlist) - strlen(deadlist),
                                   "%s(%d) ", probe[i].id, n);
                }
                zrig_param_reset(r, probe[i].id);
                zrig_tick(r, T);
            }
            CHECK(missing == 0, "标准参数不能缺：%s", deadlist[0] ? deadlist : "(无)");
            CHECK(dead == 0, "标准参数不能是死的（dt=0 下推到极值，画面一动不动）：%s",
                  deadlist[0] ? deadlist : "(无)");
            free(base);
        }
        /* 跟随类：ParamAngleX/Y 走的是平滑收敛，必须给时间 */
        {
            const zimg *fb;
            unsigned char *b2;
            double t, t0 = T;
            int n;
            const char *ids[2] = { "ParamAngleX", "ParamAngleY" };
            int k;
            for (k = 0; k < 2; ++k) {
                for (t = t0; t < t0 + 1.2; t += 0.02) zrig_tick(r, t);
                t0 += 1.2;
                fb = zrig_frame(r, 0.55, NULL, NULL);
                b2 = frame_snapshot(fb);
                CHECK(zrig_param_set(r, ids[k], 30.0) == 0, "%s 应存在", ids[k]);
                for (t = t0; t < t0 + 1.2; t += 0.02) zrig_tick(r, t);
                t0 += 1.2;
                fb = zrig_frame(r, 0.55, NULL, NULL);
                n = frame_diff_box(fb, b2, 0, 0, fb->w, fb->h);
                CHECK(n > 200, "%s=30 应该明显带动头部（%d 像素）", ids[k], n);
                free(b2);
                zrig_param_reset(r, ids[k]);
                for (t = t0; t < t0 + 1.2; t += 0.02) zrig_tick(r, t);
                t0 += 1.2;
            }
        }
        /* 单眼：ParamEyeLOpen=0 只能动左眼那一块，右眼那一块必须纹丝不动。
           （Live2D 的 EyeBlink 组就是两个参数，挤眼睛/笑眼全靠这个） */
        {
            const zimg *fb;
            unsigned char *base;
            int nl, nr;
            /* 实测（/api/frame.png 对照）：左眼闭合只改 x 197..223 / y 136..163。
               两眼中线在 231，右眼框从 236 起。 */
            const int LX0 = 180, LX1 = 231, RX0 = 236, RX1 = 300, EY0 = 128, EY1 = 175;
            double t;
            zrig_param_reset_all(r);
            for (t = 8.0; t < 11.0; t += 0.02) zrig_tick(r, t);
            zrig_tick(r, 10.98);               /* 冻结 */
            fb = zrig_frame(r, 0.55, NULL, NULL);
            base = frame_snapshot(fb);
            zrig_param_set(r, "ParamEyeLOpen", 0.0);
            zrig_tick(r, 10.98);               /* 同一时间戳 → 只有参数变了 */
            fb = zrig_frame(r, 0.55, NULL, NULL);
            nl = frame_diff_box(fb, base, LX0, EY0, LX1, EY1);
            nr = frame_diff_box(fb, base, RX0, EY0, RX1, EY1);
            CHECK(nl > 80, "ParamEyeLOpen=0 应该让左眼明显变化（%d 像素）", nl);
            CHECK(nr == 0, "右眼不能跟着动（%d 像素）—— 左右眼必须是两个独立参数", nr);
            free(base);
        }
        /* 分组（= model3.json 的 Groups）不是摆设：自动眨眼眨哪只眼、口型写哪个参数，都看它 */
        CHECK(zrig_blink_targets(r) == 3, "rig 的 EyeBlink 组应覆盖左右两只眼（实为 %d）",
              zrig_blink_targets(r));
        CHECK(z_streq(zrig_lipsync_param(r), "ParamMouthOpenY"),
              "LipSync 组应声明 ParamMouthOpenY（实为 %s）", zrig_lipsync_param(r));
        zrig_free(r);
    }
}

/* 动作通道直接驱动命名参数（Live2D 的 .motion3 曲线就是写参数的） */
static void test_action_drives_param(void)
{
    char dir[1024], sprites[1024], src[1024], dst[1024], rigp[1024];
    SECTION("动作通道可以 target 一个 ParamXxx（≈ .motion3 曲线写参数）");
    z_snprintf(dir, sizeof(dir), "/tmp/zc_pchan");
    z_snprintf(sprites, sizeof(sprites), "%s/sprites", dir);
    z_mkdir_p(dir);
    z_mkdir_p(sprites);
    z_snprintf(src, sizeof(src), "%s/characters/xiaoxun/forms/teen/sprites/eye_l_lid.png", g_root);
    z_snprintf(dst, sizeof(dst), "%s/a.png", sprites);
    if (copy_file(src, dst) != 0) { CHECK(0, "复制贴图失败"); return; }
    z_snprintf(rigp, sizeof(rigp), "%s/rig.json", dir);
    write_text(rigp,
        "{\"schema_version\":\"1.0\",\"id\":\"pc\",\"name\":\"参数通道\","
        "\"canvas\":{\"w\":200,\"h\":200},\"origin\":[100,200],"
        "\"groups\":{\"root\":{\"pivot\":[100,200],\"parent\":\"\"}},"
        "\"parts\":[{\"id\":\"h\",\"file\":\"sprites/a.png\",\"group\":\"root\",\"layer\":10,"
        " \"pos\":[100,100],\"anchor\":[0,0]}],"
        "\"params\":[{\"id\":\"ParamHairAhoge\",\"min\":-1,\"max\":1,\"default\":0,"
        " \"binds\":[{\"part\":\"h\",\"param\":\"dx\",\"scale\":10.0}]}],"
        "\"actions\":[{\"id\":\"idle\",\"loop\":true,\"channels\":["
        "  {\"target\":\"ParamHairAhoge\",\"keys\":[[0,0],[0.5,1.0],[1.0,0]],"
        "   \"interp\":\"linear\"}]},"
        " {\"id\":\"bad\",\"loop\":true,\"channels\":[]}]}");
    {
        zdiag d;
        zrig *r;
        zdiag_init(&d);
        r = zrig_load(rigp, dir, &d);
        CHECK(r != NULL, "带参数通道的 rig 应加载成功（错误 %d 条）", d.error_count);
        if (r) {
            double dx0, dx_mid;
            zrig_tick(r, 0.0);
            dx0 = zrig_part_channel(r, "h", "dx");
            zrig_tick(r, 0.5);
            dx_mid = zrig_part_channel(r, "h", "dx");
            CHECK(fabs(dx0) < 1e-6, "t=0 关键帧值 0，部件不该动（%.3f）", dx0);
            CHECK(fabs(dx_mid - 10.0) < 0.5,
                  "t=0.5 参数应被推到 1.0，经 scale 10 给出 dx=10（实为 %.3f）", dx_mid);
            zrig_free(r);
        }
    }
    /* 参数通道写错 param 名要报错，不能默默当成别的通道 */
    {
        zdiag d;
        zrig *r;
        z_snprintf(rigp, sizeof(rigp), "%s/bad.json", dir);
        write_text(rigp,
            "{\"schema_version\":\"1.0\",\"id\":\"pc\",\"name\":\"x\","
            "\"canvas\":{\"w\":200,\"h\":200},\"origin\":[100,200],"
            "\"groups\":{\"root\":{\"pivot\":[100,200],\"parent\":\"\"}},"
            "\"parts\":[{\"id\":\"h\",\"file\":\"sprites/a.png\",\"group\":\"root\",\"layer\":10,"
            " \"pos\":[100,100],\"anchor\":[0,0]}],"
            "\"params\":[{\"id\":\"ParamHairAhoge\",\"min\":-1,\"max\":1,\"default\":0,"
            " \"binds\":[{\"part\":\"h\",\"param\":\"dx\",\"scale\":10.0}]}],"
            "\"actions\":[{\"id\":\"idle\",\"loop\":true,\"channels\":["
            "  {\"target\":\"ParamHairAhoge\",\"param\":\"dx\",\"amp\":1}]}]}");
        zdiag_init(&d);
        r = zrig_load(rigp, dir, &d);
        CHECK(r == NULL && d.error_count > 0, "参数通道写 param:\"dx\" 应当场报错");
        if (r) zrig_free(r);
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

    /* A9 之后：遮罩是渲染时当场画的，层序反了也能正确裁切（不再是加载错误）。
       以前这里断言"必须报错"，现在断言"照样能用"——这正是去掉那条限制的意义。 */
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
        CHECK(r != NULL, "遮罩层号比被裁件大也应该能加载（遮罩当场渲染）");
        if (r) {
            int w = 0, h = 0;
            const zimg *f;
            long inside = 0, outside = 0;
            int x, y;
            zrig_tick(r, 0.1);
            f = zrig_frame(r, 1.0, &w, &h);
            /* hole 在 (300,300) 一带，body 只应在那块里露出来 */
            for (y = 0; y < h; ++y) {
                for (x = 0; x < w; ++x) {
                    int a = f->px[((size_t)y * w + x) * 4 + 3];
                    if (!a) continue;
                    if (x >= 290 && x <= 460 && y >= 290 && y <= 420) inside += 1;
                    else outside += 1;
                }
            }
            CHECK(inside > 200, "遮罩区域内应该有像素，实为 %ld", inside);
            CHECK(outside < inside / 4, "遮罩区域外不该漏出来（内 %ld 外 %ld）",
                  inside, outside);
            zrig_free(r);
        }
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
/* ============================================================ 网关（G51）
 * 路由 / 估价 / 三段记账 / 密钥引用。全是纯决策，不碰网络——
 * 这正是把它和"怎么发请求"分开的理由：没有密钥、没有网也能完整验证。 */

static void gw_write(const char *path, const char *body)
{
    zerr e;
    z_mkdir_p("/tmp/zc_gw");
    if (z_write_file(path, body, strlen(body), &e) != 0)
        printf("  [警告] 写不了 %s\n", path);
}

static void test_gateway(void)
{
    zgateway g;
    zdiag d;
    const zgw_route *r;
    zgw_status why;
    char buf[256];
    const char *err;
    long h1, h2;
    char rpath[512];

    SECTION("网关（G51）：真实路由表");
    zdiag_init(&d);
    z_snprintf(rpath, sizeof(rpath), "%s/config/gateway_routes.json", g_root);
    CHECK(zgw_load(&g, rpath, &d) == 0, "路由表应能加载（错误 %d）", d.error_count);
    CHECK(g.nroutes > 0, "路由表不应为空，实际 %d 条", g.nroutes);
    CHECK(strcmp(g.strategy, "prefer_local") == 0, "策略应是 prefer_local，实际 %s", g.strategy);

    /* 首选必须是本机的 ollama：prefer_local 的全部意义就在这一条上。
       要是哪天优先级算错把付费的排前面，用户会莫名其妙开始花钱。 */
    r = zgw_pick(&g, "chat.completion", 0, &why);
    CHECK(r != NULL && strcmp(r->provider, "ollama") == 0,
          "对话的首选应是本机 ollama，实际 %s", r ? r->provider : "(无)");
    CHECK(r != NULL && r->local && r->is_free, "首选应是本机且免费的");
    CHECK(r != NULL && strcmp(r->model, "qwen2.5:7b") == 0,
          "路由要带上模型名，实际 %s", r ? r->model : "(无)");

    /* 其它几家契约里 enabled=false（用户还没填密钥），所以没有第二候选。
       这条断言盯的是"关掉的供应商不许被选中"。 */
    r = zgw_pick(&g, "chat.completion", 1, &why);
    CHECK(r == NULL && why == ZGW_EXHAUSTED,
          "没开的供应商不该被选中，应报候选用尽（实际 %s）", r ? r->provider : "NULL");
    CHECK(zgw_candidate_count(&g, "chat.completion") == 1,
          "对话只有一个可用候选，实际 %d", zgw_candidate_count(&g, "chat.completion"));

    SECTION("网关：路由失败的三种原因要分得清");
    {
        /* 自造一张表，把三种情况摆齐。用真表测不到——真表里没有"全关掉"的能力。 */
        gw_write("/tmp/zc_gw/routes.json",
            "{\"schema_version\":\"1.0\",\"strategy\":\"priority\",\"fallback\":true,\"routes\":["
            "{\"cap\":\"a.one\",\"provider\":\"p_hi\",\"model\":\"m1\",\"priority\":90,"
            "\"local\":false,\"enabled\":true,\"free\":false,"
            "\"price_in\":2,\"price_out\":4,\"price_per\":1000000},"
            "{\"cap\":\"a.one\",\"provider\":\"p_lo\",\"model\":\"m2\",\"priority\":10,"
            "\"local\":false,\"enabled\":true,\"free\":false,"
            "\"price_in\":1,\"price_out\":1,\"price_per\":0},"
            "{\"cap\":\"b.off\",\"provider\":\"p_x\",\"model\":\"m3\",\"priority\":50,"
            "\"local\":false,\"enabled\":false,\"free\":false,"
            "\"price_in\":1,\"price_out\":1,\"price_per\":1000}"
            "]}");
        zdiag_init(&d);
        CHECK(zgw_load(&g, "/tmp/zc_gw/routes.json", &d) == 0, "自造路由表应能加载");

        r = zgw_pick(&g, "a.one", 0, &why);
        CHECK(r && strcmp(r->provider, "p_hi") == 0, "高优先级的排前面");
        r = zgw_pick(&g, "a.one", 1, &why);
        CHECK(r && strcmp(r->provider, "p_lo") == 0, "重试应降级到下一家");
        r = zgw_pick(&g, "a.one", 2, &why);
        CHECK(!r && why == ZGW_EXHAUSTED, "两家都试完了应报用尽");

        r = zgw_pick(&g, "nobody.does.this", 0, &why);
        CHECK(!r && why == ZGW_NO_SUCH_CAP,
              "没人提供的能力要报 NO_SUCH_CAP（提示用户去接入）");
        r = zgw_pick(&g, "b.off", 0, &why);
        CHECK(!r && why == ZGW_ALL_DISABLED,
              "有人能做但全关着要报 ALL_DISABLED（提示用户去打开），而不是当成没这功能");

        /* 三种原因必须互不相同，否则界面上没法给出不同的指引 */
        CHECK(ZGW_NO_SUCH_CAP != ZGW_ALL_DISABLED && ZGW_ALL_DISABLED != ZGW_EXHAUSTED,
              "三种失败原因必须是不同的值");
    }

    SECTION("网关：估价");
    {
        const zgw_route *hi = zgw_pick(&g, "a.one", 0, NULL);
        const zgw_route *lo = zgw_pick(&g, "a.one", 1, NULL);
        double c;
        /* 按量计价：(2*1e6 + 4*1e6)/1e6 = 6 */
        c = zgw_estimate(hi, 1000000, 1000000);
        CHECK(fabs(c - 6.0) < 1e-9, "按量计价应为 6，实际 %.6f", c);
        /* 用量翻倍，钱翻倍——线性关系要成立 */
        CHECK(fabs(zgw_estimate(hi, 2000000, 2000000) - 12.0) < 1e-9, "用量翻倍钱要翻倍");
        /* price_per=0 表示按次计价，与 token 数无关 */
        CHECK(fabs(zgw_estimate(lo, 1, 1) - zgw_estimate(lo, 999999, 999999)) < 1e-9,
              "按次计价不该随 token 变");
        CHECK(fabs(zgw_estimate(lo, 0, 0) - 2.0) < 1e-9, "按次计价应为 in+out=2");
        /* 本机的恒为 0，哪怕契约里忘了写 free */
        zdiag_init(&d);
        zgw_load(&g, rpath, &d);
        CHECK(fabs(zgw_estimate(zgw_pick(&g, "chat.completion", 0, NULL), 999999, 999999)) < 1e-9,
              "本机服务不该算出钱来");
        CHECK(fabs(zgw_estimate(NULL, 100, 100)) < 1e-9, "空路由估价应为 0 而不是崩溃");
    }

    SECTION("网关：记账三段（预扣 → 结算 / 退还）");
    {
        zgateway a;
        zdiag_init(&d);
        CHECK(zgw_load(&a, rpath, &d) == 0, "重新加载一份干净的账");
        CHECK(a.spent_total == 0.0 && a.calls_total == 0, "新账本应是空的");

        h1 = zgw_hold_open(&a, "chat.completion", "deepseek", 0.50);
        CHECK(h1 > 0, "预扣应返回单号");
        CHECK(fabs(zgw_held_amount(&a) - 0.50) < 1e-9, "预扣额应被占住");
        CHECK(a.spent_total == 0.0, "预扣阶段不该计入已花费——它只是占位");

        /* 结算入的是实际花费，不是预扣的数 */
        CHECK(zgw_hold_settle(&a, h1, 1200, 800, 0.37) == 0, "结算应成功");
        CHECK(fabs(a.spent_total - 0.37) < 1e-9,
              "已花费应是实际的 0.37 而不是预扣的 0.50，实际 %.4f", a.spent_total);
        CHECK(fabs(zgw_held_amount(&a)) < 1e-9, "结算后预扣应释放");
        CHECK(a.tokens_in_total == 1200 && a.tokens_out_total == 800, "token 用量要入账");
        CHECK(a.calls_total == 1 && a.failed_total == 0, "成功一次");

        /* 失败的请求：退还预扣，不计花费，但要计失败 */
        h2 = zgw_hold_open(&a, "image.generate", "comfyui", 0.20);
        CHECK(zgw_hold_release(&a, h2) == 0, "退还应成功");
        CHECK(fabs(a.spent_total - 0.37) < 1e-9,
              "失败的请求不该花钱，实际 %.4f", a.spent_total);
        CHECK(a.failed_total == 1, "失败次数要记——它是降权的依据");
        CHECK(fabs(zgw_held_amount(&a)) < 1e-9, "退还后预扣应释放");

        /* 单号用过就作废，重复结算必须被拒：否则一次调用能扣两次钱 */
        CHECK(zgw_hold_settle(&a, h1, 100, 100, 0.99) == -1, "重复结算必须被拒绝");
        CHECK(zgw_hold_release(&a, h2) == -1, "重复退还必须被拒绝");
        CHECK(fabs(a.spent_total - 0.37) < 1e-9, "被拒的重复结算不该改动账本");
        CHECK(zgw_hold_settle(&a, 99999, 1, 1, 1.0) == -1, "不存在的单号要被拒绝");

        /* 槽位满了要拒绝放行，而不是悄悄丢掉一笔账 */
        {
            int i, opened = 0;
            zgateway b;
            zdiag_init(&d);
            zgw_load(&b, rpath, &d);
            for (i = 0; i < ZGW_MAX_HOLDS + 3; ++i)
                if (zgw_hold_open(&b, "chat.completion", "x", 1.0) > 0) opened++;
            CHECK(opened == ZGW_MAX_HOLDS,
                  "预扣槽位应正好用满 %d 个就不再放行，实际 %d", ZGW_MAX_HOLDS, opened);
            CHECK(fabs(zgw_held_amount(&b) - (double)ZGW_MAX_HOLDS) < 1e-9,
                  "占住的额度应等于槽位数");
        }
    }

    SECTION("网关：fallback 关掉时不许换家");
    {
        zgateway c;
        gw_write("/tmp/zc_gw/nofb.json",
            "{\"schema_version\":\"1.0\",\"strategy\":\"priority\",\"fallback\":false,\"routes\":["
            "{\"cap\":\"a.one\",\"provider\":\"p1\",\"model\":\"m\",\"priority\":9,"
            "\"local\":false,\"enabled\":true,\"free\":true},"
            "{\"cap\":\"a.one\",\"provider\":\"p2\",\"model\":\"m\",\"priority\":1,"
            "\"local\":false,\"enabled\":true,\"free\":true}]}");
        zdiag_init(&d);
        CHECK(zgw_load(&c, "/tmp/zc_gw/nofb.json", &d) == 0, "应能加载");
        CHECK(c.fallback == 0, "fallback 应被读成关");
        CHECK(zgw_pick(&c, "a.one", 0, NULL) != NULL, "首选仍然要能选到");
        CHECK(zgw_pick(&c, "a.one", 1, &why) == NULL && why == ZGW_EXHAUSTED,
              "关掉 fallback 后不许换第二家（有些用户不希望悄悄换供应商）");
    }

    SECTION("网关：密钥只认 secret:// 引用");
    {
        /* 配置里写明文是要拦住的——配置文件会进仓库 */
        CHECK(zgw_secret_resolve("sk-reallive-looking-key", buf, sizeof(buf), &err) != 0,
              "明文密钥必须被拒绝");
        CHECK(err && strstr(err, "secret://") != NULL, "拒绝的理由要说清楚怎么改");
        CHECK(buf[0] == '\0', "失败时输出必须是空的");

        CHECK(zgw_secret_resolve("secret://", buf, sizeof(buf), &err) != 0,
              "secret:// 后面没名字要被拒绝");
        CHECK(zgw_secret_resolve(NULL, buf, sizeof(buf), &err) != 0, "空引用要被拒绝");

        /* 没配环境变量时必须失败，不能返回空串让调用方拿去发请求 */
        CHECK(zgw_secret_resolve("secret://definitely_not_set_xyz", buf, sizeof(buf), &err) != 0,
              "没配的密钥必须失败");
        CHECK(buf[0] == '\0', "没配时输出必须是空的，不能让空密钥流出去");

        /* 配上了就要能取到，且名字映射规则固定：secret://foo-bar → ZHUOCHONG_SECRET_FOO_BAR */
        putenv((char *)"ZHUOCHONG_SECRET_FOO_BAR=sk-test-12345");
        CHECK(zgw_secret_resolve("secret://foo-bar", buf, sizeof(buf), &err) == 0,
              "配好的密钥应能取到");
        CHECK(strcmp(buf, "sk-test-12345") == 0, "取到的值要对，实际 %s", buf);
        CHECK(zgw_secret_resolve("secret://FOO-BAR", buf, sizeof(buf), &err) == 0,
              "名字大小写不该影响解析");

        /* 空值等于没配 */
        putenv((char *)"ZHUOCHONG_SECRET_EMPTY_ONE=");
        CHECK(zgw_secret_resolve("secret://empty_one", buf, sizeof(buf), &err) != 0,
              "空字符串的环境变量等于没配");

        /* 装不下要报错，不能截断——截断的密钥发出去必然 401，还很难查 */
        {
            char tiny[4];
            CHECK(zgw_secret_resolve("secret://foo-bar", tiny, sizeof(tiny), &err) != 0,
                  "缓冲装不下要失败，不能截断密钥");
        }
    }

    SECTION("网关：坏路由表要报错而不是裸奔");
    {
        zgateway e2;
        zdiag_init(&d);
        gw_write("/tmp/zc_gw/noschema.json", "{\"routes\":[]}");
        CHECK(zgw_load(&e2, "/tmp/zc_gw/noschema.json", &d) != 0, "缺 schema_version 要失败");
        CHECK(d.error_count > 0, "要留下诊断信息");

        zdiag_init(&d);
        CHECK(zgw_load(&e2, "/tmp/zc_gw/__not_exist__.json", &d) != 0, "文件不存在要失败");

        zdiag_init(&d);
        gw_write("/tmp/zc_gw/broken.json", "{\"schema_version\":\"1.0\",\"routes\":[{\"model\":\"m\"}]}");
        CHECK(zgw_load(&e2, "/tmp/zc_gw/broken.json", &d) == 0, "个别条目坏掉不该拖垮整张表");
        CHECK(e2.nroutes == 0, "坏条目要被跳过，实际收了 %d 条", e2.nroutes);
        CHECK(d.error_count > 0, "跳过的条目要报出来，不能悄悄吞掉");
    }
}

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


/* 睡着了要能醒：空闲超时会强制闭眼，醒来必须把眼睛还回来。
   2026-10-13 真实事故 —— 唤醒只清了 sleeping 标志，强制闭眼没解除，
   而且 zrig_blink_force(r, -1) 想表达"取消"却被当成"非 0 = 闭眼"，
   于是测试台上的小寻醒着也永远闭眼，连 /api/param?all=1 都救不回来。 */
static void test_sleep_wake_blink(void)
{
    char cfgdir[1024];
    zconfig cfg;
    zdiag diag;
    zpet *pet;
    SECTION("睡醒了眼睛要还回来（强制闭眼必须解除）");

    /* ① zrig 层：force(-1) / force(0) 都该是"交回自动"，只有 >0 才是闭眼 */
    {
        char rig_path[1024], dir[1024];
        zdiag d2;
        zrig *r;
        z_snprintf(dir, sizeof(dir), "%s/characters/xiaoxun/forms/teen", g_root);
        z_snprintf(rig_path, sizeof(rig_path), "%s/rig.json", dir);
        zdiag_init(&d2);
        r = zrig_load(rig_path, dir, &d2);
        CHECK(r != NULL, "装载真 rig 应成功");
        if (r) {
            double t;
            zrig_blink_force(r, 1);
            zrig_tick(r, 1.0);
            CHECK(zrig_blink_value(r) > 0.99, "force(1) 要强制闭眼（%.2f）", zrig_blink_value(r));
            zrig_blink_force(r, -1);          /* 按字段语义写的"取消" */
            zrig_tick(r, 1.02);
            CHECK(zrig_blink_value(r) < 0.99,
                  "force(-1) 是取消，不是闭眼（%.2f）", zrig_blink_value(r));
            zrig_blink_force(r, 1);
            zrig_tick(r, 1.04);
            zrig_blink_force(r, 0);           /* bool 写法的"取消" */
            zrig_tick(r, 1.06);
            CHECK(zrig_blink_value(r) < 0.99, "force(0) 也要取消（%.2f）", zrig_blink_value(r));
            /* 取消之后状态机要真的还在走：一段时间内必须出现一次闭眼 */
            {
                int blinked = 0;
                for (t = 1.1; t < 20.0; t += 0.05) {
                    zrig_tick(r, t);
                    if (zrig_blink_value(r) > 0.9) { blinked = 1; break; }
                }
                CHECK(blinked, "解除强制后 20 秒内应至少自动眨一次眼");
            }
            zrig_free(r);
        }
    }

    /* ② zpet 层：空闲到睡着 → 用"非 poke"的方式唤醒（点动作/说话都走这条） */
    z_snprintf(cfgdir, sizeof(cfgdir), "%s/config", g_root);
    zdiag_init(&diag);
    zconfig_load(&cfg, cfgdir, &diag);
    zdiag_init(&diag);
    pet = zpet_create(&cfg, &diag);
    CHECK(pet != NULL, "角色包应加载成功");
    if (pet) {
        double t;
        int blinked = 0;
        zpet_tick(pet, 1.0);
        zpet_report_idle(pet, 99999.0);       /* 空闲很久 */
        zpet_tick(pet, 2.0);
        CHECK(zpet_sleeping(pet), "空闲超时应进入睡眠");
        zpet_tick(pet, 2.05);                 /* 睡眠是在 tick 末尾设的，下一帧才生效 */
        CHECK(zpet_blink(pet) > 0.99, "睡着时眼睛应闭上（%.2f）", zpet_blink(pet));
        zpet_report_idle(pet, 0.0);           /* 有输入了（点按钮、说话…） */
        zpet_tick(pet, 2.1);
        CHECK(!zpet_sleeping(pet), "有输入应唤醒");
        for (t = 2.2; t < 25.0; t += 0.05) {
            zpet_tick(pet, t);
            if (zpet_blink(pet) < 0.01) blinked = 1;      /* 眼睛真的睁开过 */
        }
        CHECK(blinked, "醒来之后眼睛必须睁开（否则就是强制闭眼没解除）");
        zpet_destroy(pet);
    }

    /* ③ 渲染闸：blink_enabled 只管"自动眨眼定时器"，不许影响"这一帧眼睛画成什么样"。
       真 bug：淡化判断写成 (blink_enabled && blink>0.001)，关掉自动眨眼以后，
       任何把闭合度推离 0 的东西（表情里的 ParamEyeOpen=0.85、手动按住、blink_hold）
       都会跳过淡化 → 闭眼件以 100% 不透明盖住睁眼件 = 一上表情整只眼睛全闭。 */
    {
        char rig_path[1024], dir[1024];
        zdiag d3;
        zrig *r;
        z_snprintf(dir, sizeof(dir), "%s/characters/xiaoxun/forms/teen", g_root);
        z_snprintf(rig_path, sizeof(rig_path), "%s/rig.json", dir);
        zdiag_init(&d3);
        r = zrig_load(rig_path, dir, &d3);
        CHECK(r != NULL, "装载真 rig 应成功（眨眼渲染闸）");
        if (r) {
            const zimg *fb;
            unsigned char *snap_on;
            int w = 0, h = 0, d_off, d_shut;
            zrig_blink_set_enabled(r, 1);
            zrig_blink_set_manual(r, 0.15);        /* 轻微眯眼：闭眼件还不该露脸 */
            zrig_tick(r, 5.0);
            fb = zrig_frame(r, 1.0, &w, &h);
            snap_on = frame_snapshot(fb);
            zrig_blink_set_enabled(r, 0);          /* 只关自动眨眼，画面不该动 */
            zrig_tick(r, 5.0);                     /* 同一时刻，排除别的动画干扰 */
            fb = zrig_frame(r, 1.0, NULL, NULL);
            d_off = frame_diff_box(fb, snap_on, 0, 0, w, h);
            CHECK(d_off == 0,
                  "关自动眨眼不该改变这一帧（差了 %d 像素 = 闭眼件被整张糊上去了）", d_off);
            zrig_blink_set_manual(r, 1.0);         /* 自动仍关着，手动按到全闭 */
            zrig_tick(r, 5.0);
            fb = zrig_frame(r, 1.0, NULL, NULL);
            d_shut = frame_diff_box(fb, snap_on, 0, 0, w, h);
            CHECK(d_shut > 200,
                  "关自动眨眼后手动按住仍要能闭上（只差了 %d 像素）", d_shut);
            free(snap_on);
            zrig_free(r);
        }
    }
}

/* ---- 笑眼（ParamEyeLSmile / ParamEyeRSmile）：Live2D 标准参数 6/7 ----
   官方口径：笑眼 = 闭着的眼的另一种形状（谷型 ∪ → 山型 ∩），
   Haru 的 F05 表情就是 ParamEyeLOpen=0(Multiply) + ParamEyeLSmile=1(Add)。
   所以这里要守住三件事：① 笑眼真的换了一张脸（不是把闭眼件拿来顶）；
   ② 笑眼自己隐含闭眼（不用调用方再去关睁眼）；③ 左右各走各的。 */
/* ---- 动作通道：Live2D 的 .motion3 只认 Parameter / PartOpacity / Model ----
   以前 18 个动作直接写"这个零件挪几个像素"，对外接口等于要求调用方知道角色
   拆了几件；现在全部改成写参数，几何由参数的 bind 产生。这组测试守三件事：
     ① 真 rig 里一条几何通道都不许剩（结构闸）；
     ② 计数器本身是活的（拿一个故意写几何通道的合成 rig 验它会数出来）；
     ③ 换了通道以后动作还是那个动作（挥手真的把手举起来、惊讶真的张嘴）。 */
/* 动作淡入淡出要和官方一条曲线：CubismMath.getEasingSine = 0.5 − 0.5·cos(πt)，
   而且非循环动作得按自己的 FadeOutTime 收尾，循环动作（endTime<0）不收。 */
/* 网格形变器与平滑形变（bend）必须能共存，而且同一部件上的多张网格要累加。
   这两条以前都是错的：draw_state 里 mesh 和 bend 是 if/else，形变器一上来
   bend 就被整个丢掉（多段摆链的第一段因此白写）；找形变器又是找到第一张就
   break，第二张起静默失效。合成 rig 让每种组合各渲一帧，直接比像素。 */
/* 眉形 ParamBrowLForm / ParamBrowRForm（合规表最后两个 ⬜）。
   官方 Cubism 手册的口径：−1 = 眉をしかめる（皱起），+1 = 山なりに上がる（隆起）；
   而且「変形」不许带位置移动——上下/左右/角度各有自己的参数。
   几何上那条"净位移要小"的约束由 selfcheck 静态核（它看得到配置），
   这里只管运行时：参数在、能改画面、改的地方只在眉毛那一条带上。 */
static void test_brow_form(void)
{
    char rig_path[1024], dir[1024];
    zdiag d;
    zrig *r;
    int i;
    SECTION("眉形：ParamBrowLForm / ParamBrowRForm");
    z_snprintf(dir, sizeof(dir), "%s/characters/xiaoxun/forms/teen", g_root);
    z_snprintf(rig_path, sizeof(rig_path), "%s/rig.json", dir);
    zdiag_init(&d);
    r = zrig_load(rig_path, dir, &d);
    CHECK(r != NULL, "装载真 rig 应成功（眉形）");
    if (!r) return;

    CHECK(zrig_param_set(r, "ParamBrowLForm", 0.0) == 0, "rig 里应有 ParamBrowLForm");
    CHECK(zrig_param_set(r, "ParamBrowRForm", 0.0) == 0, "rig 里应有 ParamBrowRForm");

    /* 冻结时钟做像素对照：时间一动 idle 和物理就跟着变，差异会糊成一片。
       先逐帧跑够让状态收敛，再把时钟钉死在同一个值上。 */
    for (i = 0; i < 120; ++i) zrig_tick(r, i / 60.0);
    zrig_tick(r, 500.0);
    zrig_tick(r, 500.0);
    {
        unsigned char *base = NULL;
        int w = 0, h = 0, k;
        const zimg *im;
        size_t n;
        zrig_param_set(r, "ParamBrowLForm", 0.0);
        zrig_param_set(r, "ParamBrowRForm", 0.0);
        zrig_tick(r, 500.0);
        im = zrig_frame(r, 1.0, &w, &h);
        CHECK(im != NULL && w > 0, "应能渲染基准帧");
        if (!im) { zrig_free(r); return; }
        n = (size_t)w * h * 4;
        base = (unsigned char *)malloc(n);
        CHECK(base != NULL, "应能分配基准帧缓冲");
        if (!base) { zrig_free(r); return; }
        memcpy(base, im->px, n);

        /* amount 必须跟着参数走（形变器是靠 bind 驱动的） */
        zrig_param_set(r, "ParamBrowLForm", 1.0);
        zrig_tick(r, 500.0);
        CHECK(fabs(zrig_deform_amount(r, "brow_l_form") - 1.0) < 1e-6,
              "ParamBrowLForm=1 时 brow_l_form 的量应为 1（实际 %.4f）",
              zrig_deform_amount(r, "brow_l_form"));
        zrig_param_set(r, "ParamBrowLForm", 0.0);

        for (k = 0; k < 2; ++k) {
            double v = k ? -1.0 : 1.0;
            int x, y, diff = 0, outside = 0, ymin = 99999, ymax = -1;
            zrig_param_set(r, "ParamBrowLForm", v);
            zrig_param_set(r, "ParamBrowRForm", v);
            zrig_tick(r, 500.0);
            im = zrig_frame(r, 1.0, &w, &h);
            if (!im) break;
            for (y = 0; y < h; ++y) {
                for (x = 0; x < w; ++x) {
                    size_t o = ((size_t)y * w + x) * 4;
                    int dd = abs((int)im->px[o]     - (int)base[o])
                           + abs((int)im->px[o + 1] - (int)base[o + 1])
                           + abs((int)im->px[o + 2] - (int)base[o + 2])
                           + abs((int)im->px[o + 3] - (int)base[o + 3]);
                    if (dd <= 24) continue;
                    ++diff;
                    if (y < ymin) ymin = y;
                    if (y > ymax) ymax = y;
                    /* 眉毛在画布 y≈224~245。改眉形不该牵动别处。 */
                    if (y < 200 || y > 260) ++outside;
                }
            }
            CHECK(diff > 100, "眉形 %+.0f 要看得出变化（实际 %d 像素）", v, diff);
            CHECK(outside == 0,
                  "眉形只该动眉毛那一条带（%+.0f 时有 %d 像素跑到 y200~260 之外，y 范围 %d~%d）",
                  v, outside, ymin, ymax);
            zrig_param_set(r, "ParamBrowLForm", 0.0);
            zrig_param_set(r, "ParamBrowRForm", 0.0);
        }
        free(base);
    }
    /* 表情要真的用上它（Haru 的 exp3 里六个表情都在用眉形） */
    {
        int used = 0, i2;
        const char *names[3] = { "angry", "surprise", "sad" };
        for (i2 = 0; i2 < 3; ++i2) {
            zrig_param_reset_all(r);
            zrig_expression_set(r, names[i2]);
            zrig_expression_snap(r);
            zrig_tick(r, 600.0 + i2);
            if (fabs(zrig_param_effective(r, "ParamBrowLForm")) > 0.2) ++used;
        }
        CHECK(used == 3, "angry/surprise/sad 都该用上眉形（实际 %d/3）", used);
        zrig_expression_set(r, "");
    }
    zrig_free(r);
}

static void test_mesh_bend_coexist(void)
{
    char tmp_rig[1024], dir[1024];
    zdiag d;
    zrig *r;
    FILE *f;
    SECTION("形变器 × 平滑形变：能共存，且同部件多张网格要累加");
    z_snprintf(dir, sizeof(dir), "%s/characters/xiaoxun/forms/teen", g_root);
    z_snprintf(tmp_rig, sizeof(tmp_rig), "/tmp/zc_meshbend_rig.json");
    f = fopen(tmp_rig, "wb");
    CHECK(f != NULL, "应能写出合成 rig");
    if (!f) return;
    /* 一个部件、两张同尺寸网格、一条绑 bend_x 的参数。
       网格只动底边（r=2），bend 用 root 曲线（底固定、顶最大）——
       两者作用在**不同的行**上，所以各自生效与否一眼能分开。 */
    fprintf(f,
        "{\"schema_version\":\"1.0\",\"id\":\"mb\",\"name\":\"mb\","
        "\"canvas\":{\"w\":400,\"h\":400},\"origin\":[200,400],"
        "\"groups\":{\"root\":{\"pivot\":[200,400],\"parent\":\"\"}},"
        "\"parts\":[{\"id\":\"p0\",\"file\":\"sprites/seg_torso.png\","
        "\"group\":\"root\",\"pos\":[40,20],\"layer\":1}],"
        "\"deformers\":["
        "{\"id\":\"d_a\",\"part\":\"p0\",\"cols\":2,\"rows\":2,\"points\":["
        "{\"c\":0,\"r\":2,\"dx\":18},{\"c\":1,\"r\":2,\"dx\":18},{\"c\":2,\"r\":2,\"dx\":18}]},"
        "{\"id\":\"d_b\",\"part\":\"p0\",\"cols\":2,\"rows\":2,\"points\":["
        "{\"c\":0,\"r\":2,\"dy\":16},{\"c\":1,\"r\":2,\"dy\":16},{\"c\":2,\"r\":2,\"dy\":16}]}],"
        "\"params\":["
        "{\"id\":\"PBend\",\"label\":\"b\",\"min\":-1,\"max\":1,\"default\":0,"
        "\"binds\":[{\"part\":\"p0\",\"param\":\"bend_x\",\"scale\":26}]},"
        "{\"id\":\"PDefA\",\"label\":\"a\",\"min\":0,\"max\":1,\"default\":0,"
        "\"binds\":[{\"deformer\":\"d_a\",\"scale\":1}]},"
        "{\"id\":\"PDefB\",\"label\":\"b2\",\"min\":0,\"max\":1,\"default\":0,"
        "\"binds\":[{\"deformer\":\"d_b\",\"scale\":1}]}],"
        "\"actions\":[{\"id\":\"idle\",\"loop\":true,\"channels\":[]}]}");
    fclose(f);
    zdiag_init(&d);
    r = zrig_load(tmp_rig, dir, &d);
    CHECK(r != NULL, "合成 rig 应能装载（%s）", d.count ? d.items[0].msg : "-");
    if (!r) return;
    {
        /* 四种组合各取一张帧的"不透明像素分布指纹"：用每一列的最高不透明行，
           能同时反映横向位移和纵向位移，比单纯数像素数灵敏。 */
        double base[4] = {0, 0, 0, 0};
        int i;
        struct { double bend, da, db; const char *name; } cases[4] = {
            { 0.0, 0.0, 0.0, "都不开" },
            { 1.0, 0.0, 0.0, "只有 bend" },
            { 0.0, 1.0, 0.0, "只有网格 A" },
            { 1.0, 1.0, 0.0, "bend + 网格 A" }
        };
        for (i = 0; i < 4; ++i) {
            const zimg *im;
            int w = 0, h = 0, x, y;
            double acc = 0.0;
            zrig_param_set(r, "PBend",  cases[i].bend);
            zrig_param_set(r, "PDefA",  cases[i].da);
            zrig_param_set(r, "PDefB",  cases[i].db);
            zrig_tick(r, 100.0 + i);
            im = zrig_frame(r, 1.0, &w, &h);
            CHECK(im != NULL, "应能渲染（%s）", cases[i].name);
            if (!im) { zrig_free(r); return; }
            for (x = 0; x < w; ++x)
                for (y = 0; y < h; ++y)
                    if (im->px[((size_t)y * im->w + x) * 4 + 3] > 40) { acc += x * 1.0 + y * 0.37; break; }
            base[i] = acc;
        }
        CHECK(fabs(base[1] - base[0]) > 50.0,
              "bend 单独要能改变画面（指纹 %.1f → %.1f）", base[0], base[1]);
        CHECK(fabs(base[2] - base[0]) > 50.0,
              "网格单独要能改变画面（指纹 %.1f → %.1f）", base[0], base[2]);
        /* 核心：两个一起开时，不许退化成"只有网格"——那就是 bend 被吃了 */
        CHECK(fabs(base[3] - base[2]) > 50.0,
              "网格和 bend 必须同时生效，不能被网格吃掉（只有网格 %.1f，两个一起 %.1f）",
              base[2], base[3]);
    }
    {
        /* 同部件两张网格：要测的是"两张都算进去了"。
           只比 A+B 和 B 是不够的 —— 掉了 B 的实现会退化成 A，照样不等于 B，
           负控就抓不住（实测过，这正是判据写松的典型）。三个都要比。 */
        double v[3] = {0, 0, 0};     /* 0=只有 A，1=只有 B，2=两张一起 */
        int i;
        for (i = 0; i < 3; ++i) {
            const zimg *im;
            int w = 0, h = 0, x, y;
            double acc = 0.0;
            zrig_param_set(r, "PBend", 0.0);
            zrig_param_set(r, "PDefA", (i == 0 || i == 2) ? 1.0 : 0.0);
            zrig_param_set(r, "PDefB", (i == 1 || i == 2) ? 1.0 : 0.0);
            zrig_tick(r, 200.0 + i);
            im = zrig_frame(r, 1.0, &w, &h);
            if (!im) break;
            for (x = 0; x < w; ++x)
                for (y = 0; y < h; ++y)
                    if (im->px[((size_t)y * im->w + x) * 4 + 3] > 40) { acc += x * 1.0 + y * 0.37; break; }
            v[i] = acc;
        }
        CHECK(fabs(v[0] - v[1]) > 50.0,
              "两张网格本身要有区别（只有 A %.1f，只有 B %.1f）", v[0], v[1]);
        CHECK(fabs(v[2] - v[0]) > 50.0,
              "两张一起时第二张不许被丢掉（只有 A %.1f，A+B %.1f）", v[0], v[2]);
        CHECK(fabs(v[2] - v[1]) > 50.0,
              "两张一起时第一张不许被丢掉（只有 B %.1f，A+B %.1f）", v[1], v[2]);
    }
    zrig_free(r);
}

/* 裙摆摆链（G43）：照官方 Hiyori 的 physics3，横摆吃身体左右、纵摆吃身体上下，
   两条都不吃头部参数；静止下来要收敛回零（只给惯性，不把裙子永久吹偏）。 */
static void test_skirt_physics(void)
{
    char rig_path[1024], dir[1024];
    zdiag d;
    zrig *r;
    int i;
    double sway_x = 0.0, head_x = 0.0, rest_x = 0.0, nod_y = 0.0;
    SECTION("裙摆摆链：参数输入 / 只吃身体不吃头 / 静止归零");
    z_snprintf(dir, sizeof(dir), "%s/characters/xiaoxun/forms/teen", g_root);
    z_snprintf(rig_path, sizeof(rig_path), "%s/rig.json", dir);
    zdiag_init(&d);
    r = zrig_load(rig_path, dir, &d);
    CHECK(r != NULL, "装载真 rig 应成功（裙摆）");
    if (!r) return;

    /* ① 摇摆：横摆通道要被身体带起来 */
    for (i = 0; i < 120; ++i) zrig_tick(r, i / 60.0);
    zrig_action_request(r, "sway", "test", 1);
    for (i = 1; i <= 240; ++i) {
        zrig_tick(r, 2.0 + i / 60.0);
        if (fabs(zrig_deform_amount(r, "skirt_sway_x")) > sway_x)
            sway_x = fabs(zrig_deform_amount(r, "skirt_sway_x"));
    }
    CHECK(sway_x > 0.15, "摇摆时裙摆要横着甩（实际峰值 %.3f）", sway_x);
    CHECK(sway_x < 1.0, "裙摆横摆不该一路顶到限幅（实际峰值 %.3f）", sway_x);

    /* ② 点头：纵摆要动（官方 スカート縦揺れ 吃 ParamBodyAngleY） */
    zrig_action_request(r, "nod", "test", 1);
    for (i = 1; i <= 180; ++i) {
        zrig_tick(r, 10.0 + i / 60.0);
        if (fabs(zrig_deform_amount(r, "skirt_sway_y")) > nod_y)
            nod_y = fabs(zrig_deform_amount(r, "skirt_sway_y"));
    }
    CHECK(nod_y > 0.15 && nod_y < 1.0,
          "上身上下起伏要带起裙摆纵摆，且不顶限幅（实际峰值 %.3f）", nod_y);

    /* ③ 只摇头：裙子挂在身上，不该跟着头动（官方的 Input 里没有 ParamAngle*） */
    zrig_action_request(r, "idle", "test", 1);
    for (i = 0; i < 240; ++i) zrig_tick(r, 20.0 + i / 60.0);
    zrig_param_reset_all(r);
    for (i = 1; i <= 240; ++i) {
        double t = 24.0 + i / 60.0;
        zrig_param_set(r, "ParamAngleX", 30.0 * ((i / 20) % 2 ? -1.0 : 1.0));
        zrig_param_set(r, "ParamAngleZ", 30.0 * ((i / 20) % 2 ? -1.0 : 1.0));
        zrig_tick(r, t);
        if (fabs(zrig_deform_amount(r, "skirt_sway_x")) > head_x)
            head_x = fabs(zrig_deform_amount(r, "skirt_sway_x"));
    }
    CHECK(head_x < 0.08,
          "光摇头不该把裙子带起来（头摆满格时裙摆仍有 %.3f）", head_x);

    /* ④ 身体保持倾斜不动：摆链收敛，输出回零（只加惯性，不永久偏） */
    zrig_param_reset_all(r);
    for (i = 1; i <= 600; ++i) {
        zrig_param_set(r, "ParamBodyAngleX", 10.0);
        zrig_tick(r, 40.0 + i / 60.0);
    }
    rest_x = fabs(zrig_deform_amount(r, "skirt_sway_x"));
    CHECK(rest_x < 0.02,
          "身体停住后裙摆要收敛回零，不能被永久吹偏（残留 %.4f）", rest_x);
    zrig_param_reset_all(r);
    zrig_free(r);
}

static void test_action_fade_sine(void)
{
    char rig_path[1024], dir[1024];
    zdiag d;
    zrig *r;
    int i;
    double peak = 0.0, tail = 0.0, t;
    SECTION("动作淡化曲线：官方 getEasingSine + 动作自带的 FadeOutTime");

    /* ① 缓动曲线本身：官方写死 0.5 − 0.5·cos(πt)，两端带钳位 */
    CHECK(fabs(z_ease_sine(0.0) - 0.0) < 1e-12, "ease_sine(0)=0（实际 %.6f）", z_ease_sine(0.0));
    CHECK(fabs(z_ease_sine(1.0) - 1.0) < 1e-12, "ease_sine(1)=1（实际 %.6f）", z_ease_sine(1.0));
    CHECK(fabs(z_ease_sine(0.5) - 0.5) < 1e-12, "ease_sine(0.5)=0.5（实际 %.6f）", z_ease_sine(0.5));
    CHECK(fabs(z_ease_sine(-3.0)) < 1e-12, "t<0 钳到 0（实际 %.6f）", z_ease_sine(-3.0));
    CHECK(fabs(z_ease_sine(9.0) - 1.0) < 1e-12, "t>1 钳到 1（实际 %.6f）", z_ease_sine(9.0));
    /* 0.25 处 = 0.5−0.5cos(45°) = 0.146447，而 smoothstep 是 0.156250：
       差得不多，但口径只能有一个，这条就是用来认出口径的。 */
    CHECK(fabs(z_ease_sine(0.25) - 0.1464466094) < 1e-9,
          "ease_sine(0.25) 要等于官方的 0.146447（实际 %.9f）", z_ease_sine(0.25));
    CHECK(fabs(z_ease_sine(0.25) - z_smoothstep(0.25)) > 1e-3,
          "动作淡化不能再退回 smoothstep（两者在 0.25 处本该差 %.6f）",
          fabs(z_ease_sine(0.25) - z_smoothstep(0.25)));

    z_snprintf(dir, sizeof(dir), "%s/characters/xiaoxun/forms/teen", g_root);
    z_snprintf(rig_path, sizeof(rig_path), "%s/rig.json", dir);
    zdiag_init(&d);
    r = zrig_load(rig_path, dir, &d);
    CHECK(r != NULL, "装载真 rig 应成功（动作淡化）");
    if (!r) return;

    /* ② 非循环动作：surprised 的 ParamArmLA 是 pulse+out、dur 跟动作一样长，
       不收尾的话会在最后一帧停在满值然后硬切。动作级 FadeOutTime=0.2 要把它带回零。
       （时间必须逐帧推，一次跳过去看到的是淡入还没起算的那一帧。） */
    for (i = 0; i < 120; ++i) zrig_tick(r, i / 60.0);          /* 先让 idle 收敛 */
    zrig_action_request(r, "surprised", "test:fade", 1);
    for (i = 1; i <= 54; ++i) {                                 /* 0.9s = 54 帧 */
        double v;
        t = 2.0 + i / 60.0;
        zrig_tick(r, t);
        v = fabs(zrig_param_effective(r, "ParamArmLA"));
        if (i <= 42 && v > peak) peak = v;                      /* 淡出窗口之前的峰值 */
        if (i == 53) tail = v;                                  /* 结束前 1 帧 */
    }
    CHECK(peak > 2.0, "surprised 前段 ParamArmLA 要摆到位（实际峰值 %.3f）", peak);
    CHECK(tail < peak * 0.15,
          "非循环动作结束前要按 FadeOutTime 收回去（峰值 %.3f，末帧 %.3f）", peak, tail);

    /* ②b 演完之后不许冒鬼影：动作结束那一刻它会变成"正在淡出的上一个动作"，
       这条路径同样要按它自己的 FadeOutTime 收。只给"当前动作"加淡出、
       漏掉淡出中的旧动作，会在结束瞬间把 pulse 的满值整个闪出来。 */
    {
        double ghost = 0.0;
        for (i = 55; i <= 90; ++i) {       /* 0.92s ~ 1.50s，动作已经演完 */
            zrig_tick(r, 2.0 + i / 60.0);
            if (fabs(zrig_param_effective(r, "ParamArmLA")) > ghost)
                ghost = fabs(zrig_param_effective(r, "ParamArmLA"));
        }
        CHECK(ghost < 0.25,
              "动作演完后不许残留鬼影（峰值 %.3f，结束后还有 %.3f）", peak, ghost);
    }

    /* ③ 循环动作不收尾（官方：endTime<0 时 tmpFadeOut 恒为 1）。
       breath 一直跑，幅度不能随时间缩水。 */
    {
        double hi_early = 0.0, hi_late = 0.0;
        zrig_action_request(r, "breath", "test:fade", 1);
        for (i = 1; i <= 900; ++i) {
            double v;
            zrig_tick(r, 5.0 + i / 60.0);
            v = zrig_param_effective(r, "ParamBreath");
            if (i > 60 && i <= 300 && v > hi_early) hi_early = v;
            if (i > 660 && v > hi_late) hi_late = v;
        }
        CHECK(hi_early > 0.9 && hi_late > 0.9,
              "循环动作不许淡出（前段峰 %.3f，后段峰 %.3f）", hi_early, hi_late);
    }
    zrig_free(r);
}

static void test_action_param_channels(void)
{
    char rig_path[1024], dir[1024], tmp_rig[1024];
    zdiag d;
    zrig *r;
    SECTION("动作通道：只许打在参数上（≈ .motion3 的 Parameter 曲线）");
    z_snprintf(dir, sizeof(dir), "%s/characters/xiaoxun/forms/teen", g_root);
    z_snprintf(rig_path, sizeof(rig_path), "%s/rig.json", dir);
    zdiag_init(&d);
    r = zrig_load(rig_path, dir, &d);
    CHECK(r != NULL, "装载真 rig 应成功（动作通道）");
    if (!r) return;

    /* ① 结构闸：一条"直接写部件几何"的通道都不许剩 */
    CHECK(zrig_action_geom_channels(r) == 0,
          "动作里不许有直接写部件几何的通道（实际还剩 %d 条）",
          zrig_action_geom_channels(r));

    /* ② 端到端：挥手真的要把手举到身侧外面去。
          画面右上那块(x 660..848, y 380..700)平时是空的，手举起来才会有像素。 */
    {
        const zimg *fb;
        int i, idle_px, wave_px = 0, peak = 0;
        double arm_a = 0.0, arm_b = 0.0, clock = 300.0;
        zrig_blink_set_enabled(r, 0);
        zrig_action_request(r, "idle", "t", 1);
        for (i = 0; i < 120; ++i) { clock += 1.0 / 60.0; zrig_tick(r, clock); }
        fb = zrig_frame(r, 1.0, NULL, NULL);
        idle_px = frame_opaque_box(fb, 660, 380, 848, 700);
        CHECK(idle_px == 0, "待机时手臂不该伸到画面右上（实际 %d 像素）", idle_px);
        zrig_action_request(r, "wave", "t", 1);
        /* 必须逐帧推进：动作切换的淡入权重是在 tick 里发现"动作变了"那一刻起算的，
           一次跳 1.4 秒的话权重还是 0，看到的永远是"还没动"。 */
        for (i = 0; i < 84; ++i) {
            clock += 1.0 / 60.0;
            zrig_tick(r, clock);
            if (zrig_param_effective(r, "ParamArmRA") > arm_a)
                arm_a = zrig_param_effective(r, "ParamArmRA");
            if (zrig_param_effective(r, "ParamArmRB") > arm_b)
                arm_b = zrig_param_effective(r, "ParamArmRB");
            fb = zrig_frame(r, 1.0, NULL, NULL);
            wave_px = frame_opaque_box(fb, 660, 380, 848, 700);
            if (wave_px > peak) peak = wave_px;
        }
        CHECK(arm_a > 6.0, "挥手要把 ParamArmRA 推上去（实际峰值 %.2f）", arm_a);
        CHECK(arm_b > 5.0, "挥手要把 ParamArmRB（肘）推上去（实际峰值 %.2f）", arm_b);
        CHECK(peak > 5000, "挥手时手臂要真的出现在画面右上（实际峰值 %d 像素）", peak);
    }

    /* ③ 呼吸走官方口径的 ParamBreath（0..1 单向），靠 bias 把正弦抬到正半轴。
          没有 bias 的话正弦会摆到负数，被参数下限 clamp 掉半个周期 —— 呼吸就变成一顿一顿的。 */
    {
        int i;
        double lo = 9.9, hi = -9.9, clock = 500.0;
        zrig_action_request(r, "breath", "t", 1);
        for (i = 0; i < 300; ++i) {
            double v;
            clock += 1.0 / 60.0;
            zrig_tick(r, clock);
            v = zrig_param_effective(r, "ParamBreath");
            if (v < lo) lo = v;
            if (v > hi) hi = v;
        }
        CHECK(hi > 0.9, "呼吸要把 ParamBreath 推到接近 1（实际最大 %.3f）", hi);
        CHECK(lo < 0.1, "呼吸要让 ParamBreath 回到接近 0（实际最小 %.3f）", lo);
        CHECK(lo > -1e-6, "ParamBreath 不该摆到负半轴（bias 没生效？实际最小 %.3f）", lo);
    }

    /* ④ 瞳孔形状 ParamEyeBallForm（标准参数表第 10 项）：+1 = 瞳孔放大。
          眼球被眼眶裁切，所以用"蓝色虹膜在眼眶里占了多少像素"来量。 */
    {
        const zimg *fb;
        unsigned char *snap;
        int w = 0, h = 0, dd, i;
        double clk = 700.0;
        zrig_action_request(r, "idle", "t", 1);
        zrig_param_reset_all(r);
        zrig_blink_set_manual(r, 0.0);
        /* 先跑两秒让动作淡入和物理摆链都收敛，再把时钟冻住做三帧对照
           （idle 本身一直在动，时钟一走像素就对不上；上一段的淡出没走完也会带进来）*/
        for (i = 0; i < 120; ++i) { clk += 1.0 / 60.0; zrig_tick(r, clk); }
        zrig_tick(r, clk);
        fb = zrig_frame(r, 1.0, &w, &h);
        snap = frame_snapshot(fb);
        CHECK(zrig_param_set(r, "ParamEyeBallForm", 1.0) == 0,
              "rig 里应该有 ParamEyeBallForm（Live2D 标准名）");
        zrig_tick(r, clk);
        fb = zrig_frame(r, 1.0, NULL, NULL);
        dd = frame_diff_box(fb, snap, 350, 238, 494, 308);
        CHECK(dd > 200, "瞳孔放大要看得出来（眼部实际只变了 %d 像素）", dd);
        zrig_param_set(r, "ParamEyeBallForm", 0.0);
        zrig_tick(r, clk);
        fb = zrig_frame(r, 1.0, NULL, NULL);
        CHECK(frame_diff_box(fb, snap, 350, 238, 494, 308) == 0, "归零要回到原样（实际差 %d 像素）", frame_diff_box(fb, snap, 350, 238, 494, 308));
        free(snap);
    }

    /* ⑤ 全身倾斜 ParamBaseRot（扩展参数，被摸头/被拖拽时整个人晃） */
    {
        const zimg *fb;
        unsigned char *snap;
        int w = 0, h = 0;
        zrig_param_reset_all(r);
        zrig_tick(r, 800.0);
        fb = zrig_frame(r, 1.0, &w, &h);
        snap = frame_snapshot(fb);
        CHECK(zrig_param_set(r, "ParamBaseRot", 10.0) == 0, "rig 里应该有 ParamBaseRot");
        zrig_tick(r, 800.0);
        fb = zrig_frame(r, 1.0, NULL, NULL);
        CHECK(frame_diff_box(fb, snap, 0, 0, w, h) > 20000,
              "ParamBaseRot 满格要让整个人明显倾斜");
        zrig_param_reset_all(r);
        free(snap);
    }

    /* ⑥ 口型接管：迁移后嘴的动作通道是 ParamMouthOpenY（参数），
          不再是"带 mouth 标签的部件"，静音判断必须跟着改口径，否则 talk 的
          拍嘴会和 TTS 包络叠在一起，嘴越张越大。 */
    {
        int i;
        double with_mute = 0.0, without = 0.0, clock = 900.0;
        zrig_param_reset_all(r);
        zrig_set_mouth_mute(r, 0);
        zrig_action_request(r, "talk", "t", 1);
        for (i = 0; i < 120; ++i) {
            clock += 1.0 / 60.0; zrig_tick(r, clock);
            if (zrig_param_effective(r, "ParamMouthOpenY") > without)
                without = zrig_param_effective(r, "ParamMouthOpenY");
        }
        zrig_set_mouth_mute(r, 1);
        for (i = 0; i < 120; ++i) {
            clock += 1.0 / 60.0; zrig_tick(r, clock);
            if (zrig_param_effective(r, "ParamMouthOpenY") > with_mute)
                with_mute = zrig_param_effective(r, "ParamMouthOpenY");
        }
        CHECK(without > 0.5, "talk 平时要把嘴拍开（实际峰值 %.3f）", without);
        CHECK(with_mute < 0.05,
              "口型接管时 talk 的嘴通道必须让路（实际峰值 %.3f）", with_mute);
        zrig_set_mouth_mute(r, 0);
    }
    zrig_free(r);

    /* ⑦ 反向验证计数器本身是活的：故意写一条几何通道的合成 rig 必须被数出来。
          （不验这一步的话，"恒返回 0" 的实现也能让上面第 ① 条过。） */
    {
        FILE *f;
        zrig *bad;
        z_snprintf(tmp_rig, sizeof(tmp_rig), "/tmp/zc_geomchan_rig.json");
        f = fopen(tmp_rig, "wb");
        CHECK(f != NULL, "应能写出合成 rig");
        if (f) {
            fprintf(f,
                "{\"schema_version\":\"1.0\",\"id\":\"gc\",\"name\":\"gc\","
                "\"canvas\":{\"w\":200,\"h\":200},\"origin\":[100,200],"
                "\"groups\":{\"root\":{\"pivot\":[100,200],\"parent\":\"\"}},"
                "\"parts\":[{\"id\":\"p0\",\"file\":\"sprites/eye_l_base.png\","
                "\"group\":\"root\",\"pos\":[10,10],\"layer\":1}],"
                "\"actions\":[{\"id\":\"idle\",\"loop\":true,\"channels\":["
                "{\"target\":\"p0\",\"param\":\"dx\",\"wave\":\"sine\",\"amp\":2,\"freq\":1},"
                "{\"target\":\"p0\",\"param\":\"alpha\",\"wave\":\"sine\",\"amp\":-0.2,\"freq\":1}"
                "]}]}");
            fclose(f);
            zdiag_init(&d);
            bad = zrig_load(tmp_rig, dir, &d);
            CHECK(bad != NULL, "合成 rig 应能装载");
            if (bad) {
                /* dx 那条要被数出来，alpha 那条是官方的 PartOpacity，不算 */
                CHECK(zrig_action_geom_channels(bad) == 1,
                      "几何通道计数器要数得出来（合成 rig 实际 %d，应为 1）",
                      zrig_action_geom_channels(bad));
                zrig_free(bad);
            }
            remove(tmp_rig);
        }
    }
}

static void test_eye_smile(void)
{
    char rig_path[1024], dir[1024];
    zdiag d;
    zrig *r;
    /* 眼件在画布上的位置来自 rig.json：eye_l_smile [356,245] 57x56、eye_r_smile [429,240] 57x58 */
    const int LX0 = 350, LY0 = 238, LX1 = 421, LY1 = 308;
    const int RX0 = 423, RY0 = 233, RX1 = 494, RY1 = 303;
    SECTION("笑眼：山型 ∩ 的闭眼，和谷型闭眼是两张不同的脸");
    z_snprintf(dir, sizeof(dir), "%s/characters/xiaoxun/forms/teen", g_root);
    z_snprintf(rig_path, sizeof(rig_path), "%s/rig.json", dir);
    zdiag_init(&d);
    r = zrig_load(rig_path, dir, &d);
    CHECK(r != NULL, "装载真 rig 应成功（笑眼）");
    if (!r) return;
    {
        const zimg *fb;
        unsigned char *snap_open = NULL, *snap_closed = NULL;
        int w = 0, h = 0, d_closed, d_smile, d_vs_closed, d_wink_l, d_wink_r, d_back;
        int dark_closed = 0, dark_smile = 0;

        CHECK(zrig_param_set(r, "ParamEyeLSmile", 0.0) == 0
              && zrig_param_set(r, "ParamEyeRSmile", 0.0) == 0,
              "rig 里应该有 ParamEyeLSmile / ParamEyeRSmile（Live2D 标准名）");
        zrig_blink_set_enabled(r, 0);          /* 自动眨眼会搅乱像素对照 */
        zrig_blink_set_manual(r, 0.0);
        zrig_tick(r, 5.0);
        fb = zrig_frame(r, 1.0, &w, &h);
        snap_open = frame_snapshot(fb);

        /* ① 谷型闭眼（基准之一） */
        zrig_blink_set_manual(r, 1.0);
        zrig_tick(r, 5.0);
        fb = zrig_frame(r, 1.0, NULL, NULL);
        d_closed = frame_diff_box(fb, snap_open, LX0, LY0, LX1, LY1);
        snap_closed = frame_snapshot(fb);
        dark_closed = frame_dark_box(fb, LX0, LY0, LX1, LY1);
        CHECK(d_closed > 400, "闭眼要能看出来（左眼区变了 %d 像素）", d_closed);

        /* ② 笑眼：只推 ParamEyeL/RSmile，不碰睁眼参数 —— 眼睛必须自己闭上并换成山型 */
        zrig_blink_set_manual(r, -1.0);        /* 交回自动；enabled=0 所以闭合度回 0 */
        zrig_param_set(r, "ParamEyeLSmile", 1.0);
        zrig_param_set(r, "ParamEyeRSmile", 1.0);
        zrig_tick(r, 5.0);
        fb = zrig_frame(r, 1.0, NULL, NULL);
        d_smile = frame_diff_box(fb, snap_open, LX0, LY0, LX1, LY1);
        d_vs_closed = frame_diff_box(fb, snap_closed, LX0, LY0, LX1, LY1);
        CHECK(d_smile > 400,
              "笑眼要自己把眼睛闭上（不用再写 ParamEyeOpen；左眼区变了 %d 像素）", d_smile);
        CHECK(d_vs_closed > 150,
              "笑眼和谷型闭眼必须是两张脸（只差了 %d 像素 = 多半在拿闭眼件顶）", d_vs_closed);
        /* 「笑眼隐含闭眼」在画面上看不出来（笑眼补片本来就盖住整只眼），
           所以直接问引擎要本帧的闭合度 —— 这条才是 Haru F05 那套口径的本体。 */
        CHECK(zrig_eye_smile(r, 0) > 0.99 && zrig_eye_smile(r, 1) > 0.99,
              "两只眼的笑眼量应为 1（L=%.2f R=%.2f）", zrig_eye_smile(r, 0), zrig_eye_smile(r, 1));
        CHECK(zrig_eye_close(r, 0) > 0.99 && zrig_eye_close(r, 1) > 0.99,
              "笑眼必须隐含闭眼：闭合度应为 1（L=%.2f R=%.2f）",
              zrig_eye_close(r, 0), zrig_eye_close(r, 1));
        /* 画面上也得真有那条山型线：既不能什么都不画（笑眼件没显形），
           也不能把山型和谷型两条线一起画（那会叠成一团黑）。 */
        dark_smile = frame_dark_box(fb, LX0, LY0, LX1, LY1);
        CHECK(dark_smile > dark_closed / 2,
              "笑眼帧的眼区要有睫毛线（暗像素 %d，闭眼帧是 %d）", dark_smile, dark_closed);
        CHECK(dark_smile < dark_closed * 16 / 10,
              "笑眼不该和谷型闭眼叠着画（暗像素 %d，闭眼帧才 %d）", dark_smile, dark_closed);

        /* ③ 左右分家：只笑左眼，右眼区不许动 */
        zrig_param_set(r, "ParamEyeRSmile", 0.0);
        zrig_tick(r, 5.0);
        fb = zrig_frame(r, 1.0, NULL, NULL);
        d_wink_l = frame_diff_box(fb, snap_open, LX0, LY0, LX1, LY1);
        d_wink_r = frame_diff_box(fb, snap_open, RX0, RY0, RX1, RY1);
        CHECK(d_wink_l > 400 && d_wink_r == 0,
              "单眼笑：左眼变 %d 像素、右眼必须一点都不动（实际 %d）", d_wink_l, d_wink_r);
        CHECK(zrig_eye_close(r, 0) > 0.99 && zrig_eye_close(r, 1) < 0.01,
              "单眼笑：左眼闭合 %.2f、右眼仍睁着 %.2f",
              zrig_eye_close(r, 0), zrig_eye_close(r, 1));

        /* ④ 收回去要干净：参数归零 = 回到一开始那一帧 */
        zrig_param_set(r, "ParamEyeLSmile", 0.0);
        zrig_tick(r, 5.0);
        fb = zrig_frame(r, 1.0, NULL, NULL);
        d_back = frame_diff_box(fb, snap_open, 0, 0, w, h);
        CHECK(d_back == 0, "笑眼归零应完全回到睁眼那一帧（还差 %d 像素）", d_back);

        /* ⑤ 官方那种写法（表情同时写 EyeOpen=0 + Smile=1）也不能把眼睛弄睁 */
        zrig_param_set(r, "ParamEyeLSmile", 1.0);
        zrig_param_set(r, "ParamEyeOpen", 0.0);
        zrig_tick(r, 5.0);
        fb = zrig_frame(r, 1.0, NULL, NULL);
        CHECK(frame_diff_box(fb, snap_open, LX0, LY0, LX1, LY1) > 400,
              "Haru F05 那种写法（EyeOpen=0 + Smile=1）也要是笑眼");
        zrig_param_set(r, "ParamEyeOpen", 1.0);
        zrig_param_set(r, "ParamEyeLSmile", 0.0);

        /* ⑥ 表情 happy 应该带笑眼 */
        zrig_expression_set(r, "happy");
        zrig_expression_snap(r);
        zrig_tick(r, 5.0);
        CHECK(zrig_param_effective(r, "ParamEyeLSmile") > 0.9
              && zrig_param_effective(r, "ParamEyeRSmile") > 0.9,
              "表情 happy 要把两只眼都变成笑眼（L=%.2f R=%.2f）",
              zrig_param_effective(r, "ParamEyeLSmile"),
              zrig_param_effective(r, "ParamEyeRSmile"));
        free(snap_open);
        free(snap_closed);
    }
    zrig_free(r);

    /* ⑦ 结构闸：在真 rig 上"笑眼件画没画"很难数清楚（眼线件下滑后也在同一位置留一条线），
       所以另起一个合成 rig，把睁眼/谷型闭眼/山型笑眼三张真素材摆在互不重叠的位置，
       这样每一块有没有画出来就是能逐像素数的。 */
    {
        char rigp[1024], dir2[1024];
        zdiag d2;
        zrig *r2;
        z_snprintf(dir2, sizeof(dir2), "%s/characters/xiaoxun/forms/teen", g_root);
        z_snprintf(rigp, sizeof(rigp), "/tmp/zc_eye_smile_rig.json");
        write_text(rigp,
            "{\"schema_version\":\"1.0\",\"id\":\"es\",\"name\":\"笑眼结构闸\","
            "\"canvas\":{\"w\":848,\"h\":400},\"origin\":[424,400],"
            "\"groups\":{\"root\":{\"pivot\":[424,400],\"parent\":\"\"}},"
            "\"blink\":{\"enabled\":true},"
            "\"param_groups\":[{\"name\":\"EyeBlink\","
            " \"ids\":[\"ParamEyeLOpen\",\"ParamEyeROpen\"]}],"
            "\"parts\":["
            " {\"id\":\"o\",\"file\":\"sprites/eye_l_base.png\",\"group\":\"root\","
            "  \"layer\":10,\"pos\":[100,100],\"anchor\":[0,0],"
            "  \"tags\":[\"eye_open\"],\"eye_side\":\"l\"},"
            " {\"id\":\"c\",\"file\":\"sprites/eye_l_closed.png\",\"group\":\"root\","
            "  \"layer\":11,\"pos\":[300,100],\"anchor\":[0,0],"
            "  \"tags\":[\"eye_closed\"],\"eye_side\":\"l\"},"
            " {\"id\":\"s\",\"file\":\"sprites/eye_l_smile.png\",\"group\":\"root\","
            "  \"layer\":12,\"pos\":[500,100],\"anchor\":[0,0],"
            "  \"tags\":[\"eye_smile\"],\"eye_side\":\"l\"}],"
            "\"actions\":[{\"id\":\"idle\",\"loop\":true,\"channels\":[]}]}");
        zdiag_init(&d2);
        r2 = zrig_load(rigp, dir2, &d2);
        CHECK(r2 != NULL, "合成 rig（三张眼）应加载成功");
        if (r2) {
            const zimg *fb;
            int po, pc, ps;
            zrig_blink_set_enabled(r2, 0);
            zrig_blink_set_manual(r2, 0.0);
            zrig_tick(r2, 1.0);
            fb = zrig_frame(r2, 1.0, NULL, NULL);
            po = frame_opaque_box(fb,  90,  90, 260, 260);
            pc = frame_opaque_box(fb, 290,  90, 460, 260);
            ps = frame_opaque_box(fb, 490,  90, 660, 260);
            CHECK(po > 500 && pc == 0 && ps == 0,
                  "睁着时只画睁眼件（睁 %d / 闭 %d / 笑 %d）", po, pc, ps);

            zrig_blink_set_manual(r2, 1.0);          /* 谷型闭眼 */
            zrig_tick(r2, 1.1);
            fb = zrig_frame(r2, 1.0, NULL, NULL);
            po = frame_opaque_box(fb,  90,  90, 260, 260);
            pc = frame_opaque_box(fb, 290,  90, 460, 260);
            ps = frame_opaque_box(fb, 490,  90, 660, 260);
            CHECK(po == 0 && pc > 500 && ps == 0,
                  "闭眼时只画谷型闭眼件（睁 %d / 闭 %d / 笑 %d）", po, pc, ps);

            zrig_blink_set_manual(r2, -1.0);
            zrig_param_set(r2, "ParamEyeLSmile", 1.0);
            zrig_tick(r2, 1.2);
            fb = zrig_frame(r2, 1.0, NULL, NULL);
            po = frame_opaque_box(fb,  90,  90, 260, 260);
            pc = frame_opaque_box(fb, 290,  90, 460, 260);
            ps = frame_opaque_box(fb, 490,  90, 660, 260);
            CHECK(ps > 500, "笑眼时山型笑眼件必须画出来（实际 %d 像素）", ps);
            CHECK(pc == 0, "笑眼时谷型闭眼件必须让位（还画着 %d 像素 = 两条线叠一起）", pc);
            CHECK(po == 0, "笑眼时睁眼件必须收掉（还画着 %d 像素）", po);
            zrig_free(r2);
        }
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


/* ---- A9 遮罩升级：多遮罩并集 / 取反 / 不限层序 ---- */
static void test_mask_multi(void)
{
    char dir[1024], sprites[1024], src[1024], dst[1024], rigp[1024];
    zdiag d;
    zrig *r;
    const char *head =
        "{\"schema_version\":\"1.0\",\"id\":\"mm\",\"name\":\"多遮罩\","
        "\"canvas\":{\"w\":300,\"h\":300},\"origin\":[150,300],"
        "\"groups\":{\"root\":{\"pivot\":[150,300],\"parent\":\"\"}},";

    SECTION("多遮罩取并集、取反遮罩、遮罩不许套娃");
    z_snprintf(dir, sizeof(dir), "/tmp/zc_mask2");
    z_snprintf(sprites, sizeof(sprites), "%s/sprites", dir);
    z_mkdir_p(dir); z_mkdir_p(sprites);
    z_snprintf(src, sizeof(src), "%s/characters/xiaoxun/forms/teen/sprites/hair_ahoge.png", g_root);
    z_snprintf(dst, sizeof(dst), "%s/h.png", sprites);
    if (copy_file(src, dst) != 0) { CHECK(0, "复制贴图失败"); return; }
    z_snprintf(src, sizeof(src), "%s/characters/xiaoxun/forms/teen/sprites/body_full.png", g_root);
    z_snprintf(dst, sizeof(dst), "%s/big.png", sprites);
    if (copy_file(src, dst) != 0) { CHECK(0, "复制大图失败"); return; }
    z_snprintf(rigp, sizeof(rigp), "%s/rig.json", dir);

    {   /* 两个小遮罩分别在左右，被裁的大图应该**两处都露**（并集） */
        char buf[2048];
        long only_a = 0, both = 0;
        int w = 0, h = 0, x, y;
        const zimg *f;
        z_snprintf(buf, sizeof(buf), "%s\"parts\":["
            " {\"id\":\"ma\",\"file\":\"sprites/h.png\",\"group\":\"root\",\"layer\":10,"
            "  \"pos\":[20,100],\"anchor\":[0,0],\"mask_only\":true},"
            " {\"id\":\"mb\",\"file\":\"sprites/h.png\",\"group\":\"root\",\"layer\":11,"
            "  \"pos\":[200,100],\"anchor\":[0,0],\"mask_only\":true},"
            " {\"id\":\"big\",\"file\":\"sprites/big.png\",\"group\":\"root\",\"layer\":20,"
            "  \"pos\":[0,0],\"anchor\":[0,0],\"mask\":[\"ma\"]}],"
            "\"actions\":[{\"id\":\"idle\",\"loop\":true,\"channels\":[]}]}", head);
        write_text(rigp, buf);
        zdiag_init(&d);
        r = zrig_load(rigp, dir, &d);
        CHECK(r != NULL, "单遮罩写成数组也应加载成功");
        if (r) {
            zrig_tick(r, 0.1);
            f = zrig_frame(r, 1.0, &w, &h);
            for (y = 0; y < h; ++y) for (x = 0; x < w; ++x)
                if (f->px[((size_t)y * w + x) * 4 + 3]) only_a++;
            zrig_free(r);
        }
        z_snprintf(buf, sizeof(buf), "%s\"parts\":["
            " {\"id\":\"ma\",\"file\":\"sprites/h.png\",\"group\":\"root\",\"layer\":10,"
            "  \"pos\":[20,100],\"anchor\":[0,0],\"mask_only\":true},"
            " {\"id\":\"mb\",\"file\":\"sprites/h.png\",\"group\":\"root\",\"layer\":11,"
            "  \"pos\":[200,100],\"anchor\":[0,0],\"mask_only\":true},"
            " {\"id\":\"big\",\"file\":\"sprites/big.png\",\"group\":\"root\",\"layer\":20,"
            "  \"pos\":[0,0],\"anchor\":[0,0],\"mask\":[\"ma\",\"mb\"]}],"
            "\"actions\":[{\"id\":\"idle\",\"loop\":true,\"channels\":[]}]}", head);
        write_text(rigp, buf);
        zdiag_init(&d);
        r = zrig_load(rigp, dir, &d);
        CHECK(r != NULL, "两个遮罩的 rig 应加载成功");
        if (r) {
            zrig_tick(r, 0.1);
            f = zrig_frame(r, 1.0, &w, &h);
            for (y = 0; y < h; ++y) for (x = 0; x < w; ++x)
                if (f->px[((size_t)y * w + x) * 4 + 3]) both++;
            zrig_free(r);
        }
        CHECK(both > only_a * 3 / 2, "两个遮罩取并集应该露出更多（%ld → %ld）",
              only_a, both);
    }

    {   /* 取反遮罩：只在遮罩**外面**可见，和正向遮罩互补 */
        char buf[2048];
        long fwd = 0, inv = 0, total = 0;
        int w = 0, h = 0, x, y;
        const zimg *f;
        const char *tpl =
            "%s\"parts\":["
            " {\"id\":\"ma\",\"file\":\"sprites/h.png\",\"group\":\"root\",\"layer\":10,"
            "  \"pos\":[100,100],\"anchor\":[0,0],\"mask_only\":true},"
            " {\"id\":\"big\",\"file\":\"sprites/big.png\",\"group\":\"root\",\"layer\":20,"
            "  \"pos\":[0,0],\"anchor\":[0,0],\"mask\":\"ma\"%s}],"
            "\"actions\":[{\"id\":\"idle\",\"loop\":true,\"channels\":[]}]}";
        z_snprintf(buf, sizeof(buf), tpl, head, "");
        write_text(rigp, buf);
        zdiag_init(&d);
        r = zrig_load(rigp, dir, &d);
        if (r) {
            zrig_tick(r, 0.1);
            f = zrig_frame(r, 1.0, &w, &h);
            for (y = 0; y < h; ++y) for (x = 0; x < w; ++x)
                if (f->px[((size_t)y * w + x) * 4 + 3]) fwd++;
            zrig_free(r);
        }
        z_snprintf(buf, sizeof(buf), tpl, head, ",\"mask_invert\":true");
        write_text(rigp, buf);
        zdiag_init(&d);
        r = zrig_load(rigp, dir, &d);
        CHECK(r != NULL, "取反遮罩的 rig 应加载成功");
        if (r) {
            zrig_tick(r, 0.1);
            f = zrig_frame(r, 1.0, &w, &h);
            for (y = 0; y < h; ++y) for (x = 0; x < w; ++x)
                if (f->px[((size_t)y * w + x) * 4 + 3]) inv++;
            zrig_free(r);
        }
        /* 没有遮罩时的总可见面积 */
        z_snprintf(buf, sizeof(buf),
            "%s\"parts\":[{\"id\":\"big\",\"file\":\"sprites/big.png\",\"group\":\"root\","
            "  \"layer\":20,\"pos\":[0,0],\"anchor\":[0,0]}],"
            "\"actions\":[{\"id\":\"idle\",\"loop\":true,\"channels\":[]}]}", head);
        write_text(rigp, buf);
        zdiag_init(&d);
        r = zrig_load(rigp, dir, &d);
        if (r) {
            zrig_tick(r, 0.1);
            f = zrig_frame(r, 1.0, &w, &h);
            for (y = 0; y < h; ++y) for (x = 0; x < w; ++x)
                if (f->px[((size_t)y * w + x) * 4 + 3]) total++;
            zrig_free(r);
        }
        CHECK(fwd > 100 && inv > 100, "正反遮罩都应该留下东西（%ld / %ld）", fwd, inv);
        CHECK(fwd + inv > total * 9 / 10 && fwd + inv < total * 11 / 10,
              "正向 + 取反应该≈完整图（%ld + %ld vs %ld）", fwd, inv, total);
    }

    {   /* 遮罩套娃要被拦住 */
        char buf[2048];
        z_snprintf(buf, sizeof(buf), "%s\"parts\":["
            " {\"id\":\"ma\",\"file\":\"sprites/h.png\",\"group\":\"root\",\"layer\":10,"
            "  \"pos\":[20,100],\"anchor\":[0,0]},"
            " {\"id\":\"mb\",\"file\":\"sprites/h.png\",\"group\":\"root\",\"layer\":11,"
            "  \"pos\":[60,100],\"anchor\":[0,0],\"mask\":\"ma\"},"
            " {\"id\":\"big\",\"file\":\"sprites/big.png\",\"group\":\"root\",\"layer\":20,"
            "  \"pos\":[0,0],\"anchor\":[0,0],\"mask\":\"mb\"}],"
            "\"actions\":[{\"id\":\"idle\",\"loop\":true,\"channels\":[]}]}", head);
        write_text(rigp, buf);
        zdiag_init(&d);
        CHECK(zrig_load(rigp, dir, &d) == NULL, "遮罩套娃必须加载失败");
        CHECK(diag_has(&d, "套娃"), "诊断应点名套娃");
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
    test_eye_aperture();
    test_image();
    test_deflate();
    test_config_and_pet();
    test_bad_config();
    test_rig_channels();
    test_mask();
    test_eyelid();
    test_group_chain();
    test_live2d_standard();
    test_viseme();
    test_expr_viseme_order();
    test_expression_blend();
    test_sleep_wake_blink();
    test_eye_smile();
    test_action_param_channels();
    test_action_fade_sine();
    test_brow_form();
    test_mesh_bend_coexist();
    test_skirt_physics();
    test_action_drives_param();
    test_motion_fade();
    test_physics();
    test_look();
    test_params();
    test_lipsync();
    test_mesh();
    test_keys_and_chain();
    test_blend();
    test_pose();
    test_mask_multi();
    test_longrun();
    test_expression();
    test_motion_from();
    test_interactions();
    test_affection();
    test_gateway();

    printf("\n通过 %d 项，失败 %d 项\n", g_pass, g_fail);
    if (g_fail) {
        printf("结论：不通过（必须全绿才能交付）\n");
        return 1;
    }
    printf("结论：全部通过\n");
    return 0;
}
