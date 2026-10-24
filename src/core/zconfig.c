/* zconfig.c - 配置加载实现 */
#include "zconfig.h"
#include "zschema.h"

#include <math.h>

/* “自动位置”哨兵：窗口放到默认位置（右下角） */
#define ZCFG_AUTO_POS (1 << 30)

void zconfig_defaults(zconfig *c)
{
    memset(c, 0, sizeof(*c));
    z_strlcpy(c->ui.schema_version, "1.0", sizeof(c->ui.schema_version));
    z_strlcpy(c->ui.theme, "soft_handdrawn", sizeof(c->ui.theme));
    z_strlcpy(c->ui.font_title, "assets/fonts/rounded_title.ttf", sizeof(c->ui.font_title));
    z_strlcpy(c->ui.font_body, "assets/fonts/rounded_body.ttf", sizeof(c->ui.font_body));
    c->ui.corner_radius = 18.0;
    c->ui.border_width = 3.0;
    z_strlcpy(c->ui.palette_primary, "#7EC8C4", sizeof(c->ui.palette_primary));
    z_strlcpy(c->ui.palette_accent, "#F7B7C8", sizeof(c->ui.palette_accent));
    z_strlcpy(c->ui.palette_bg, "#FFFDF6", sizeof(c->ui.palette_bg));
    z_strlcpy(c->ui.palette_text, "#4A4458", sizeof(c->ui.palette_text));
    c->ui.bounce_amp = 0.08;
    c->ui.anim_duration = 0.25;
    z_strlcpy(c->ui.res_tray_icon, "assets/brand/xiaoxun.ico", sizeof(c->ui.res_tray_icon));

    z_strlcpy(c->pet.schema_version, "1.0", sizeof(c->pet.schema_version));
    c->pet.win_x = ZCFG_AUTO_POS;
    c->pet.win_y = ZCFG_AUTO_POS;
    c->pet.scale = 0.55;
    c->pet.scale_min = 0.2;
    c->pet.scale_max = 2.0;
    c->pet.fps = 30;
    c->pet.always_on_top = 1;
    c->pet.click_through = 0;
    c->pet.hit_alpha_threshold = 24;
    c->pet.head_ratio = 0.30;
    c->pet.idle_sleep_seconds = 90;
    c->pet.tray_enabled = 1;
    z_strlcpy(c->pet.character, "xiaoxun", sizeof(c->pet.character));
    z_strlcpy(c->pet.form, "teen", sizeof(c->pet.form));
    z_strlcpy(c->pet.outfit, "default", sizeof(c->pet.outfit));
    c->pet.tool_default = 0;
    z_strlcpy(c->pet.log_file, "logs/pet.log", sizeof(c->pet.log_file));
    c->pet.log_level = 1;
}

/* ------------------------------------------------------------ 小工具 */
static const char *cfg_path(zconfig *c, const char *name, char *out, size_t cap)
{
    z_path_join(out, cap, c->config_dir, name);
    return out;
}

static int load_one_json(zconfig *c, const char *name, zdiag *d, zjson **out)
{
    char path[1024], schema[1024];
    zerr err;
    zjson *doc;
    zerr_clear(&err);
    cfg_path(c, name, path, sizeof(path));
    if (!z_file_exists(path)) {
        zdiag_warn(d, path, 0, 0, "", "配置文件不存在，使用内置默认值");
        *out = NULL;
        return 0;
    }
    doc = zjson_parse_file(path, &err);
    if (!doc) {
        zdiag_error(d, path, err.line, err.col, "", "解析失败：%s", err.msg);
        *out = NULL;
        return -1;
    }
    /* schema 校验（同名 .schema.json，放在 schemas/ 目录） */
    {
        char base[128];
        z_strlcpy(base, z_basename(name), sizeof(base));
        {
            char *dot = strrchr(base, '.');
            if (dot) *dot = 0;
        }
        z_snprintf(schema, sizeof(schema), "%s/schemas/%s.schema.json", c->root_dir, base);
        if (zschema_validate_file(schema, doc, path, d) < 0)
            zdiag_warn(d, schema, 0, 0, "", "缺少 schema 文件，跳过结构校验");
    }
    *out = doc;
    return 0;
}

/* ------------------------------------------------------------ ui.json */
static void load_ui(zconfig *c, zjson *j, const char *file, zdiag *d)
{
    zcfg_ui *u = &c->ui;
    if (!j) return;
    zjson_get_strbuf(j, "schema_version", 1, "1.0", u->schema_version, sizeof(u->schema_version), d, file);
    zjson_get_strbuf(j, "theme", 0, u->theme, u->theme, sizeof(u->theme), d, file);
    zjson_get_strbuf(j, "fonts.title", 0, u->font_title, u->font_title, sizeof(u->font_title), d, file);
    zjson_get_strbuf(j, "fonts.body", 0, u->font_body, u->font_body, sizeof(u->font_body), d, file);
    u->corner_radius = zjson_get_num(j, "shapes.corner_radius", 0, u->corner_radius, d, file);
    u->border_width = zjson_get_num(j, "shapes.border_width", 0, u->border_width, d, file);
    zjson_get_strbuf(j, "palette.primary", 0, u->palette_primary, u->palette_primary, sizeof(u->palette_primary), d, file);
    zjson_get_strbuf(j, "palette.accent", 0, u->palette_accent, u->palette_accent, sizeof(u->palette_accent), d, file);
    zjson_get_strbuf(j, "palette.background", 0, u->palette_bg, u->palette_bg, sizeof(u->palette_bg), d, file);
    zjson_get_strbuf(j, "palette.text", 0, u->palette_text, u->palette_text, sizeof(u->palette_text), d, file);
    u->bounce_amp = zjson_get_num(j, "motion.bounce_amp", 0, u->bounce_amp, d, file);
    u->anim_duration = zjson_get_num(j, "motion.duration_s", 0, u->anim_duration, d, file);
    zjson_get_strbuf(j, "resources.bubble", 0, u->res_bubble, u->res_bubble, sizeof(u->res_bubble), d, file);
    zjson_get_strbuf(j, "resources.button", 0, u->res_button, u->res_button, sizeof(u->res_button), d, file);
    zjson_get_strbuf(j, "resources.icon_dir", 0, u->res_icon_dir, u->res_icon_dir, sizeof(u->res_icon_dir), d, file);
    zjson_get_strbuf(j, "resources.tray_icon", 0, u->res_tray_icon, u->res_tray_icon, sizeof(u->res_tray_icon), d, file);

    if (!z_startswith(u->palette_primary, "#") || strlen(u->palette_primary) != 7)
        zdiag_warn(d, file, 0, 0, "palette.primary", "颜色应写成 #RRGGBB 形式");
}

/* ----------------------------------------------------------- pet.json */
static void load_pet(zconfig *c, zjson *j, const char *file, zdiag *d)
{
    zcfg_pet *p = &c->pet;
    if (!j) return;
    zjson_get_strbuf(j, "schema_version", 1, "1.0", p->schema_version, sizeof(p->schema_version), d, file);
    /* 允许“自动位置”哨兵值（1<<30）与真实屏幕坐标 */
    p->win_x = (int)zjson_get_int(j, "window.x", 0, p->win_x,
                                  -100000, (long)ZCFG_AUTO_POS, d, file);
    p->win_y = (int)zjson_get_int(j, "window.y", 0, p->win_y,
                                  -100000, (long)ZCFG_AUTO_POS, d, file);
    p->scale = zjson_get_num(j, "window.scale", 0, p->scale, d, file);
    p->scale_min = zjson_get_num(j, "window.scale_min", 0, p->scale_min, d, file);
    p->scale_max = zjson_get_num(j, "window.scale_max", 0, p->scale_max, d, file);
    if (p->scale_min > p->scale_max) {
        zdiag_error(d, file, 0, 0, "window.scale_min", "scale_min (%g) 不能大于 scale_max (%g)",
                    p->scale_min, p->scale_max);
        p->scale = 1.0; p->scale_min = 0.2; p->scale_max = 2.0;
    }
    p->scale = ZC_CLAMP(p->scale, p->scale_min, p->scale_max);
    p->fps = (int)zjson_get_int(j, "window.fps", 0, p->fps, 5, 120, d, file);
    p->always_on_top = zjson_get_bool(j, "window.always_on_top", 0, p->always_on_top, d, file);
    p->click_through = zjson_get_bool(j, "window.click_through", 0, p->click_through, d, file);
    p->hit_alpha_threshold = (int)zjson_get_int(j, "interaction.hit_alpha_threshold", 0,
                                                p->hit_alpha_threshold, 0, 254, d, file);
    p->head_ratio = zjson_get_num(j, "interaction.head_ratio", 0, p->head_ratio, d, file);
    if (p->head_ratio <= 0.0 || p->head_ratio >= 1.0) {
        zdiag_error(d, file, 0, 0, "interaction.head_ratio", "应在 (0,1) 之间，实际 %g", p->head_ratio);
        p->head_ratio = 0.30;
    }
    p->idle_sleep_seconds = (int)zjson_get_int(j, "interaction.idle_sleep_seconds", 0,
                                               p->idle_sleep_seconds, 5, 36000, d, file);
    p->tray_enabled = zjson_get_bool(j, "tray.enabled", 0, p->tray_enabled, d, file);
    zjson_get_strbuf(j, "character.id", 0, p->character, p->character, sizeof(p->character), d, file);
    zjson_get_strbuf(j, "character.form", 0, p->form, p->form, sizeof(p->form), d, file);
    zjson_get_strbuf(j, "character.outfit", 0, p->outfit, p->outfit, sizeof(p->outfit), d, file);
    p->tool_default = (int)zjson_get_int(j, "interaction.tool", 0, p->tool_default, 0, 1, d, file);
    zjson_get_strbuf(j, "log.file", 0, p->log_file, p->log_file, sizeof(p->log_file), d, file);
    p->log_level = (int)zjson_get_int(j, "log.level", 0, p->log_level, 0, 3, d, file);
}

/* ------------------------------------------------------ features.json */
static void load_features(zconfig *c, zjson *j, const char *file, zdiag *d)
{
    const zjson *mods;
    size_t i, n;
    if (!j) return;
    if (!zjson_get(j, "schema_version")) {
        zdiag_error(d, file, j->line, j->col, "schema_version", "缺少 schema_version");
        return;
    }
    mods = zjson_get(j, "modules");
    if (!mods || mods->type != ZJSON_ARR) {
        zdiag_error(d, file, j ? j->line : 0, 0, "modules", "期望 array");
        return;
    }
    n = zjson_count(mods);
    for (i = 0; i < n && c->nmodules < ZCFG_MAX_LIST; ++i) {
        const zjson *mj = zjson_at(mods, i);
        zcfg_module *m = &c->modules[c->nmodules];
        const char *id = zjson_str(zjson_obj_get(mj, "id"), NULL);
        char buf[128];
        if (!id || !*id) {
            zdiag_error(d, file, mj ? mj->line : 0, 0, "modules", "缺少 id");
            continue;
        }
        memset(m, 0, sizeof(*m));
        z_strlcpy(m->id, id, sizeof(m->id));
        z_snprintf(buf, sizeof(buf), "modules[%s]", id);
        z_strlcpy(m->name, zjson_str(zjson_obj_get(mj, "name"), id), sizeof(m->name));
        m->enabled = zjson_bool(zjson_obj_get(mj, "enabled"), 0);
        {
            const zjson *tl = zjson_obj_get(mj, "token_limit");
            m->token_limit = tl ? zjson_num(tl, 0) : 0;
            if (m->token_limit < 0) {
                zdiag_error(d, file, mj->line, 0, buf, "token_limit 不能为负");
                m->token_limit = 0;
            }
            {
                const zjson *dl = zjson_obj_get(mj, "daily_token_limit");
                m->daily_limit = dl ? zjson_num(dl, 0) : 0;
            }
        }
        c->nmodules++;
    }
}

/* ----------------------------------------------------- providers.json */
static void load_providers(zconfig *c, zjson *j, const char *file, zdiag *d)
{
    const zjson *arr;
    size_t i, n;
    if (!j) return;
    if (!zjson_get(j, "schema_version")) {
        zdiag_error(d, file, j->line, j->col, "schema_version", "缺少 schema_version");
        return;
    }
    arr = zjson_get(j, "providers");
    n = zjson_count(arr);
    for (i = 0; i < n && c->nproviders < ZCFG_MAX_LIST; ++i) {
        const zjson *pj = zjson_at(arr, i);
        zcfg_provider *p = &c->providers[c->nproviders];
        const char *id = zjson_str(zjson_obj_get(pj, "id"), NULL);
        char buf[128];
        if (!id || !*id) {
            zdiag_error(d, file, pj ? pj->line : 0, 0, "providers", "缺少 id");
            continue;
        }
        memset(p, 0, sizeof(*p));
        z_strlcpy(p->id, id, sizeof(p->id));
        z_snprintf(buf, sizeof(buf), "providers[%s]", id);
        z_strlcpy(p->name, zjson_str(zjson_obj_get(pj, "name"), id), sizeof(p->name));
        z_strlcpy(p->kind, zjson_str(zjson_obj_get(pj, "kind"), "openai_compatible"), sizeof(p->kind));
        z_strlcpy(p->base_url, zjson_str(zjson_obj_get(pj, "base_url"), ""), sizeof(p->base_url));
        z_strlcpy(p->model, zjson_str(zjson_obj_get(pj, "model"), ""), sizeof(p->model));
        p->enabled = zjson_bool(zjson_obj_get(pj, "enabled"), 0);
        p->official = zjson_bool(zjson_obj_get(pj, "official"), 0);
        if (p->official && p->enabled) {
            zdiag_warn(d, file, pj->line, 0, buf,
                       "官方直连默认关闭：确认已阅读服务条款后再改为 enabled");
        }
        if (p->enabled && !p->base_url[0]) {
            zdiag_error(d, file, pj->line, 0, buf, "启用状态但缺少 base_url");
        }
        c->nproviders++;
    }
}

/* -------------------------------------------------------- voices.json */
static void load_voices(zconfig *c, zjson *j, const char *file, zdiag *d)
{
    const zjson *arr;
    size_t i, n;
    if (!j) return;
    arr = zjson_get(j, "voices");
    n = zjson_count(arr);
    for (i = 0; i < n && c->nvoices < ZCFG_MAX_LIST; ++i) {
        const zjson *vj = zjson_at(arr, i);
        zcfg_voice *v = &c->voices[c->nvoices];
        const char *cid = zjson_str(zjson_obj_get(vj, "character"), NULL);
        char buf[160];
        if (!cid) {
            zdiag_error(d, file, vj ? vj->line : 0, 0, "voices", "缺少 character");
            continue;
        }
        memset(v, 0, sizeof(*v));
        z_strlcpy(v->character, cid, sizeof(v->character));
        z_snprintf(buf, sizeof(buf), "voices[%s]", cid);
        z_strlcpy(v->id, zjson_str(zjson_obj_get(vj, "id"), cid), sizeof(v->id));
        z_strlcpy(v->form, zjson_str(zjson_obj_get(vj, "form"), ""), sizeof(v->form));
        z_strlcpy(v->provider, zjson_str(zjson_obj_get(vj, "provider"), ""), sizeof(v->provider));
        z_strlcpy(v->voice, zjson_str(zjson_obj_get(vj, "voice"), ""), sizeof(v->voice));
        z_strlcpy(v->style, zjson_str(zjson_obj_get(vj, "style"), ""), sizeof(v->style));
        if (!v->provider[0])
            zdiag_warn(d, file, vj->line, 0, buf, "未指定 provider（接入语音时会跳过）");
        c->nvoices++;
    }
}

int zconfig_load(zconfig *c, const char *config_dir, zdiag *diag)
{
    zjson *j = NULL;
    char path[1024];
    int fatal = 0;

    zconfig_defaults(c);
    z_strlcpy(c->config_dir, config_dir, sizeof(c->config_dir));
    z_strlcpy(c->root_dir, config_dir, sizeof(c->root_dir));
    {
        char tmp[1024];
        z_strlcpy(tmp, config_dir, sizeof(tmp));
        z_dirname(tmp);
        z_strlcpy(c->root_dir, tmp, sizeof(c->root_dir));
    }

    if (!z_is_dir(config_dir)) {
        zdiag_error(diag, config_dir, 0, 0, "", "配置目录不存在");
        return -1;
    }

    if (load_one_json(c, "ui.json", diag, &j) == 0 && j) {
        load_ui(c, j, cfg_path(c, "ui.json", path, sizeof(path)), diag);
        zjson_free(j);
    }
    if (load_one_json(c, "pet.json", diag, &j) == 0 && j) {
        load_pet(c, j, cfg_path(c, "pet.json", path, sizeof(path)), diag);
        zjson_free(j);
    }
    if (load_one_json(c, "features.json", diag, &j) == 0 && j) {
        load_features(c, j, cfg_path(c, "features.json", path, sizeof(path)), diag);
        zjson_free(j);
    }
    if (load_one_json(c, "providers.json", diag, &j) == 0 && j) {
        load_providers(c, j, cfg_path(c, "providers.json", path, sizeof(path)), diag);
        zjson_free(j);
    }
    if (load_one_json(c, "voices.json", diag, &j) == 0 && j) {
        load_voices(c, j, cfg_path(c, "voices.json", path, sizeof(path)), diag);
        zjson_free(j);
    }

    /* settings.json 覆盖（本机运行状态，不是用户手写配置） */
    zconfig_load_settings(c, diag);

    fatal = !zdiag_ok(diag);
    return fatal ? -1 : 0;
}

int zconfig_load_settings(zconfig *c, zdiag *d)
{
    char path[1024];
    zerr err;
    zjson *j;
    cfg_path(c, "settings.json", path, sizeof(path));
    if (!z_file_exists(path)) return 1;   /* 首次运行：正常 */
    zerr_clear(&err);
    j = zjson_parse_file(path, &err);
    if (!j) {
        zdiag_error(d, path, err.line, err.col, "", "运行状态文件损坏：%s（将使用默认值）", err.msg);
        return -1;
    }
    c->pet.win_x = (int)zjson_int(zjson_get(j, "window.x"), c->pet.win_x);
    c->pet.win_y = (int)zjson_int(zjson_get(j, "window.y"), c->pet.win_y);
    c->pet.scale = zjson_num(zjson_get(j, "window.scale"), c->pet.scale);
    c->pet.click_through = zjson_bool(zjson_get(j, "window.click_through"), c->pet.click_through);
    c->pet.tool_default = (int)zjson_int(zjson_get(j, "interaction.tool"), c->pet.tool_default);
    {
        const char *ch = zjson_str(zjson_get(j, "character.id"), NULL);
        const char *fm = zjson_str(zjson_get(j, "character.form"), NULL);
        if (ch && *ch) z_strlcpy(c->pet.character, ch, sizeof(c->pet.character));
        if (fm && *fm) z_strlcpy(c->pet.form, fm, sizeof(c->pet.form));
    }
    c->pet.scale = ZC_CLAMP(c->pet.scale, c->pet.scale_min, c->pet.scale_max);
    zjson_free(j);
    (void)path;
    return 0;
}

int zconfig_save_settings(const zconfig *c, zerr *err)
{
    char path[1024];
    zjson_w *w = zjson_w_new(1);
    char *text;
    size_t len = 0;
    int rc;
    cfg_path((zconfig *)c, "settings.json", path, sizeof(path));
    zjson_w_obj_begin(w);
    zjson_w_key(w, "schema_version"); zjson_w_str(w, "1.0");
    zjson_w_key(w, "window");
    zjson_w_obj_begin(w);
    zjson_w_key(w, "x"); zjson_w_int(w, c->pet.win_x);
    zjson_w_key(w, "y"); zjson_w_int(w, c->pet.win_y);
    zjson_w_key(w, "scale"); zjson_w_num(w, c->pet.scale);
    zjson_w_key(w, "click_through"); zjson_w_bool(w, c->pet.click_through);
    zjson_w_obj_end(w);
    zjson_w_key(w, "interaction");
    zjson_w_obj_begin(w);
    zjson_w_key(w, "tool"); zjson_w_int(w, c->pet.tool_default);
    zjson_w_obj_end(w);
    zjson_w_key(w, "character");
    zjson_w_obj_begin(w);
    zjson_w_key(w, "id"); zjson_w_str(w, c->pet.character);
    zjson_w_key(w, "form"); zjson_w_str(w, c->pet.form);
    zjson_w_obj_end(w);
    zjson_w_obj_end(w);
    text = zjson_w_take(w, &len);
    zjson_w_free(w);
    rc = z_write_file(path, text, len, err);
    free(text);
    return rc;
}

const zcfg_module *zconfig_module(const zconfig *c, const char *id)
{
    int i;
    if (!c || !id) return NULL;
    for (i = 0; i < c->nmodules; ++i)
        if (strcmp(c->modules[i].id, id) == 0) return &c->modules[i];
    return NULL;
}

int zconfig_module_enabled(const zconfig *c, const char *id)
{
    const zcfg_module *m = zconfig_module(c, id);
    return m ? m->enabled : 0;
}

const zcfg_provider *zconfig_provider(const zconfig *c, const char *id)
{
    int i;
    if (!c || !id) return NULL;
    for (i = 0; i < c->nproviders; ++i)
        if (strcmp(c->providers[i].id, id) == 0) return &c->providers[i];
    return NULL;
}

void zconfig_print(const zconfig *c, FILE *out)
{
    int i;
    if (!c) return;
    fprintf(out, "配置目录: %s\n", c->config_dir);
    fprintf(out, "主题: %s  主色 %s 强调色 %s\n", c->ui.theme, c->ui.palette_primary, c->ui.palette_accent);
    fprintf(out, "角色: %s/%s 服装 %s  缩放 %.2f (%.2f~%.2f) 帧率 %d\n",
            c->pet.character, c->pet.form, c->pet.outfit,
            c->pet.scale, c->pet.scale_min, c->pet.scale_max, c->pet.fps);
    fprintf(out, "窗口: %s  置顶 %d  穿透 %d  命中阈值 %d  头部比例 %.2f  空闲入睡 %ds\n",
            c->pet.win_x == ZCFG_AUTO_POS ? "自动" : "记忆",
            c->pet.always_on_top, c->pet.click_through,
            c->pet.hit_alpha_threshold, c->pet.head_ratio, c->pet.idle_sleep_seconds);
    {
        int enabled = 0;
        for (i = 0; i < c->nmodules; ++i) if (c->modules[i].enabled) enabled++;
        fprintf(out, "功能模块 %d 个（开启 %d 个）:\n", c->nmodules, enabled);
    }
    for (i = 0; i < c->nmodules; ++i) {
        unsigned long long lim = (unsigned long long)c->modules[i].token_limit;
        fprintf(out, "  - %-14s %s  %s  token上限 %llu\n",
                c->modules[i].id, c->modules[i].enabled ? "[开]" : "[关]",
                c->modules[i].name, lim);
    }
    fprintf(out, "供应商 %d 个:\n", c->nproviders);
    for (i = 0; i < c->nproviders; ++i)
        fprintf(out, "  - %-12s %s  %s  %s\n", c->providers[i].id,
                c->providers[i].enabled ? "[启用]" : "[关闭]",
                c->providers[i].base_url, c->providers[i].model);
    fprintf(out, "音色绑定 %d 条\n", c->nvoices);
}
