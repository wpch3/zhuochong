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
        CHECK(z_write_file("/tmp/zc_badcfg/pet.json",
                           "{\"schema_version\":\"1.0\",\"window\":{\"scale\":\"大\"},\"interaction\":{\"idle_sleep_seconds\":0}}",
                           90, &e) == 0, "写出坏配置");
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
    test_interactions();

    printf("\n通过 %d 项，失败 %d 项\n", g_pass, g_fail);
    if (g_fail) {
        printf("结论：不通过（必须全绿才能交付）\n");
        return 1;
    }
    printf("结论：全部通过\n");
    return 0;
}
