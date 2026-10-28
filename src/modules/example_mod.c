/*
 * example_mod.c - 示例热插拔模组（铁律三演示）
 * 编译：make modules/example_mod.so
 * 配置：config/modules/_example.json 指向 build/modules/example_mod.so 并把 enabled 设 true
 */
#include "../core/zmod.h"
#include <stdio.h>

static int ex_init(void *ctx, zdiag *diag) {
    (void)diag;
    zmod_ctx *c = (zmod_ctx*)ctx;
    fprintf(stderr, "[example_mod] init id=%s root=%s\n", c->id, c->root_dir ? c->root_dir : ".");
    return 0;
}
static void ex_tick(void *ctx, double now) {
    (void)ctx; (void)now;
    /* 可选：在此向总线发事件 */
    /* zbus_event ev; zbus_event_init(&ev, ZBUS_EVT_CUSTOM, "example/tick", "example_mod"); zbus_publish(c->bus, &ev); */
}
static int ex_event(void *ctx, const zbus_event *ev) {
    (void)ctx; (void)ev;
    /* 收到广播事件 */
    return 0;
}
static void ex_shutdown(void *ctx) {
    (void)ctx;
    fprintf(stderr, "[example_mod] shutdown\n");
}

static const zmod_api k_api = {
    .name = "example_mod",
    .version = ZMOD_ABI_VERSION,
    .init = ex_init,
    .tick = ex_tick,
    .on_event = ex_event,
    .shutdown = ex_shutdown,
};

/* 引擎 dlopen 后 dlsym 此符号 */
#if defined(_WIN32)
__declspec(dllexport)
#endif
const zmod_api* zmod_get_api(void) { return &k_api; }
