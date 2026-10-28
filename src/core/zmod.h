/*
 * zmod.h - 动态模组热加载管理器（铁律三：微内核 / 万物皆模组）
 *
 * 目标：不重启、不卡渲染地热卸/热更/动态挂载任意功能模组。
 * 契约：每个 .so/.dll 导出一个符号：
 *   const zmod_api* zmod_get_api(void);
 * 引擎通过 dlopen → dlsym 拿到表，调 init → tick/on_event → shutdown → dlclose。
 *
 * 配置：config/modules/<id>.json
 *   { "id":"live2d_core","path":"modules/live2d_core.so","enabled":true,"version":1 }
 * 无配置也能跑（零模组即裸引擎）。
 *
 * 线程：tick 在主 tick 串里（持 g_lock 小段），on_event 可从任意线程经 zbus 投递，
 *       模块内部若要慢活应自起线程，不得阻塞 tick。
 */
#ifndef ZMOD_H
#define ZMOD_H

#include "zc.h"
#include "zbus.h"

#ifdef __cplusplus
extern "C" {
#endif

#define ZMOD_ABI_VERSION 1
#define ZMOD_MAX 32
#define ZMOD_PATH_MAX 512
#define ZMOD_NAME_MAX 64

typedef struct zmod_api {
    const char *name;                 /* 人类可读名，log 用 */
    int         version;              /* 必须 == ZMOD_ABI_VERSION */
    int (*init)(void *ctx, zdiag *diag);          /* ctx 为 zmod_ctx（见下） */
    void (*tick)(void *ctx, double now);
    int  (*on_event)(void *ctx, const zbus_event *ev);
    void (*shutdown)(void *ctx);
} zmod_api;

/* 模组上下文（引擎传给模块的句柄） */
typedef struct {
    char   id[64];
    char   path[ZMOD_PATH_MAX];
    void  *handle;                    /* dlopen 句柄（Windows 用 HMODULE 转 void*） */
    const zmod_api *api;
    void  *user;                      /* 模块私有数据（模块自己 malloc，shutdown 时 free） */
    zbus  *bus;                       /* 全局总线（模块可 publish） */
    const char *root_dir;             /* 仓库根，供读配置/素材 */
    int    enabled;
    double last_tick;
} zmod_ctx;

typedef struct {
    zmod_ctx mods[ZMOD_MAX];
    int      count;
    zbus    *bus;                     /* 引擎持有的总线 */
    char     mod_dir[512];            /* config/modules 目录 */
    char     root_dir[512];
} zmod_mgr;

/* 生命周期 */
void zmod_mgr_init(zmod_mgr *m, const char *root_dir, zbus *bus);
void zmod_mgr_shutdown(zmod_mgr *m);

/* 从目录加载全部 declared 模块（缺目录亦算成功，count=0） */
int  zmod_scan(zmod_mgr *m, zdiag *diag);           /* 0 成功，-1 有致命错 */

/* 单件操作（热插拔） */
int  zmod_load(zmod_mgr *m, const char *mod_json_path, zdiag *diag);
int  zmod_unload(zmod_mgr *m, const char *id);      /* 不存在返回 -1 */
int  zmod_reload(zmod_mgr *m, const char *id, zdiag *diag); /* unload+load */

/* 每帧 */
void zmod_tick(zmod_mgr *m, double now);
int  zmod_dispatch(zmod_mgr *m, const zbus_event *ev); /* 广播给全部启用模组，返回处理数 */

/* 查询 */
int         zmod_count(const zmod_mgr *m);
const char* zmod_id_at(const zmod_mgr *m, int i);
int         zmod_enabled(const zmod_mgr *m, const char *id);
zmod_ctx*   zmod_find(zmod_mgr *m, const char *id);

/* 内部：路径解析 */
const zmod_api* zmod_get_api_default(void); /* 单元测试用：返回空实现 */

#ifdef __cplusplus
}
#endif
#endif
