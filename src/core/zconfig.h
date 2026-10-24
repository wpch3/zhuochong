/*
 * zconfig.h - 配置加载（全部可自定义，核心代码不认识具体内容）
 *
 * 对应交接文件第一节之二与第七节：
 *   config/ui.json         主题、调色板、字体、动效
 *   config/pet.json        窗口、交互、托盘、空闲检测、日志（本项目新增，见文档）
 *   config/features.json   功能模块开关与 token 上限（默认全部关闭）
 *   config/providers.json  API 供应商 / 中转站（OpenAI 兼容）
 *   config/voices.json     角色 → 音色映射（按供应商分组）
 *   config/settings.json   本机运行状态（窗口位置、缩放），由程序写入
 *
 * 每个文件带 schema_version，并先过 schemas/<name>.schema.json 校验；
 * 出错时给出“文件 + 行 + 字段 + 原因”，不崩溃。
 */
#ifndef ZCONFIG_H
#define ZCONFIG_H

#include "zc.h"
#include "zjson.h"

#ifdef __cplusplus
extern "C" {
#endif

#define ZCFG_MAX_LIST 48

typedef struct {
    char   id[48];
    char   name[96];
    int    enabled;          /* 默认 0：全部关闭 */
    double token_limit;      /* 0 = 不限 */
    double daily_limit;
} zcfg_module;

typedef struct {
    char id[48];
    char name[96];
    char kind[24];           /* openai_compatible / official */
    char base_url[256];
    char model[96];
    int  enabled;
    int  official;           /* 官方直连：默认关闭（交接文件第六节） */
} zcfg_provider;

typedef struct {
    char id[48];
    char character[48];
    char form[48];           /* 空 = 该角色全部形态 */
    char provider[48];
    char voice[96];
    char style[96];
} zcfg_voice;

typedef struct {
    char   schema_version[16];
    char   theme[64];
    char   font_title[128];
    char   font_body[128];
    double corner_radius;
    double border_width;
    char   palette_primary[16];
    char   palette_accent[16];
    char   palette_bg[16];
    char   palette_text[16];
    double bounce_amp;
    double anim_duration;
    /* 资源路径（全部来自生成图，配置里只引用路径） */
    char   res_bubble[256];
    char   res_button[256];
    char   res_icon_dir[256];
    char   res_tray_icon[256];
} zcfg_ui;

typedef struct {
    char   schema_version[16];
    int    win_x, win_y;         /* 1<<30 表示“自动（右下角）” */
    double scale;
    double scale_min, scale_max;
    int    fps;
    int    always_on_top;
    int    click_through;        /* 启动时是否整窗穿透 */
    int    hit_alpha_threshold;  /* 像素命中阈值（0..255） */
    double head_ratio;           /* 头部区域比例（摸头判定） */
    int    idle_sleep_seconds;   /* 空闲入睡秒数，默认 90 */
    int    tray_enabled;
    char   character[96];        /* 默认角色包 id */
    char   form[48];             /* 默认形态 id */
    char   outfit[48];           /* 默认服装 id */
    int    tool_default;         /* 0 手(抚摸) 1 锤子 */
    char   log_file[512];
    int    log_level;            /* 0 debug 1 info 2 warn 3 error */
} zcfg_pet;

typedef struct {
    char config_dir[512];
    char root_dir[512];          /* 仓库/安装根目录（config_dir 的上级） */
    zcfg_ui  ui;
    zcfg_pet pet;
    zcfg_module   modules[ZCFG_MAX_LIST];
    int           nmodules;
    zcfg_provider providers[ZCFG_MAX_LIST];
    int           nproviders;
    zcfg_voice    voices[ZCFG_MAX_LIST];
    int           nvoices;
} zconfig;

void zconfig_defaults(zconfig *c);

/* 加载 config_dir 下全部配置文件。
 * 返回 0 成功；-1 表示存在致命错误（诊断在 diag 里，错误不影响其它模块继续加载）。 */
int  zconfig_load(zconfig *c, const char *config_dir, zdiag *diag);
/* settings.json：缺失不算错误；存在则覆盖窗口状态。 */
int  zconfig_load_settings(zconfig *c, zdiag *diag);
/* 保存窗口状态（退出时调用）。 */
int  zconfig_save_settings(const zconfig *c, zerr *err);

const zcfg_module *zconfig_module(const zconfig *c, const char *id);
int   zconfig_module_enabled(const zconfig *c, const char *id);
const zcfg_provider *zconfig_provider(const zconfig *c, const char *id);
void  zconfig_print(const zconfig *c, FILE *out);

#ifdef __cplusplus
}
#endif
#endif /* ZCONFIG_H */
