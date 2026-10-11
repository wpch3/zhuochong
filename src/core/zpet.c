/* zpet.c - 桌宠应用逻辑实现 */
#include "zpet.h"
#include "zjson.h"

#include <math.h>

#ifdef _WIN32
#  include <windows.h>
#else
#  include <dirent.h>
#endif

struct zpet {
    zconfig cfg;            /* 配置副本（窗口状态会回写） */
    char    root[512];
    char    char_dir[1024];
    char    form_dir[1024];
    zrig   *rig;
    zdiag   diag;

    double  scale;
    double  now;
    double  idle_seconds;
    int     sleeping;
    zpet_tool tool;

    /* 摸头持续判定 */
    double  pat_last_at;
    int     pat_count;

    /* 形态 / 服装枚举 */
    char    forms[ZPET_MAX_FORMS][48];
    char    form_names[ZPET_MAX_FORMS][96];
    int     nforms;
    char    outfits[ZPET_MAX_OUTFITS][64];
    char    outfit_names[ZPET_MAX_OUTFITS][128];
    int     noutfits;

    /* 手动整理的可触发动作顺序 */
    char    action_ids[32][48];
    int     nactions;

    int     hover_inside;
    double  hover_x, hover_y;
};

#define ZPET_MAX_ACTIONS 32

/* ------------------------------------------------------------ 目录扫描 */
static void scan_forms(zpet *p)
{
    char dir[1200];
    z_path_join(dir, sizeof(dir), p->char_dir, "forms");
    p->nforms = 0;
#ifdef _WIN32
    {
        char pat[1300];
        WIN32_FIND_DATAA fd;
        HANDLE h;
        z_snprintf(pat, sizeof(pat), "%s/*", dir);
        h = FindFirstFileA(pat, &fd);
        if (h == INVALID_HANDLE_VALUE) return;
        do {
            char rig_path[1400];
            if (!(fd.dwFileAttributes & FILE_ATTRIBUTE_DIRECTORY)) continue;
            if (fd.cFileName[0] == '.') continue;
            z_snprintf(rig_path, sizeof(rig_path), "%s/%s/rig.json", dir, fd.cFileName);
            if (!z_file_exists(rig_path)) continue;
            z_strlcpy(p->forms[p->nforms], fd.cFileName, sizeof(p->forms[0]));
            z_snprintf(p->form_names[p->nforms], sizeof(p->form_names[0]), "%s", fd.cFileName);
            if (++p->nforms >= ZPET_MAX_FORMS) break;
        } while (FindNextFileA(h, &fd));
        FindClose(h);
    }
#else
    {
        DIR *dp = opendir(dir);
        struct dirent *de;
        if (!dp) return;
        while (p->nforms < ZPET_MAX_FORMS && (de = readdir(dp))) {
            char rig_path[1400];
            if (de->d_name[0] == '.') continue;
            z_snprintf(rig_path, sizeof(rig_path), "%s/%s/rig.json", dir, de->d_name);
            if (!z_file_exists(rig_path)) continue;
            z_strlcpy(p->forms[p->nforms], de->d_name, sizeof(p->forms[0]));
            z_strlcpy(p->form_names[p->nforms], de->d_name, sizeof(p->form_names[0]));
            p->nforms++;
        }
        closedir(dp);
    }
#endif
}

static void scan_outfits(zpet *p)
{
    char dir[1200];
    z_path_join(dir, sizeof(dir), p->char_dir, "outfits");
    p->noutfits = 0;
#ifdef _WIN32
    {
        char pat[1300];
        WIN32_FIND_DATAA fd;
        HANDLE h;
        z_snprintf(pat, sizeof(pat), "%s/*.json", dir);
        h = FindFirstFileA(pat, &fd);
        if (h == INVALID_HANDLE_VALUE) return;
        do {
            char *dot;
            if (fd.dwFileAttributes & FILE_ATTRIBUTE_DIRECTORY) continue;
            z_strlcpy(p->outfits[p->noutfits], fd.cFileName, sizeof(p->outfits[0]));
            dot = strrchr(p->outfits[p->noutfits], '.');
            if (dot) *dot = 0;
            z_strlcpy(p->outfit_names[p->noutfits], p->outfits[p->noutfits],
                      sizeof(p->outfit_names[0]));
            if (++p->noutfits >= ZPET_MAX_OUTFITS) break;
        } while (FindNextFileA(h, &fd));
        FindClose(h);
    }
#else
    {
        DIR *dp = opendir(dir);
        struct dirent *de;
        if (!dp) return;
        while (p->noutfits < ZPET_MAX_OUTFITS && (de = readdir(dp))) {
            char name[256], *dot;
            if (de->d_name[0] == '.') continue;
            if (!z_endswith(de->d_name, ".json")) continue;
            z_strlcpy(name, de->d_name, sizeof(name));
            dot = strrchr(name, '.');
            if (dot) *dot = 0;
            z_strlcpy(p->outfits[p->noutfits], name, sizeof(p->outfits[0]));
            z_strlcpy(p->outfit_names[p->noutfits], name, sizeof(p->outfit_names[0]));
            p->noutfits++;
        }
        closedir(dp);
    }
#endif
}

/* 读形态显示名（rig.json 的 name 字段），失败则回退目录名 */
static void read_form_name(zpet *p, int i)
{
    char path[1400];
    zerr e;
    zjson *j;
    z_snprintf(path, sizeof(path), "%s/forms/%s/rig.json", p->char_dir, p->forms[i]);
    zerr_clear(&e);
    j = zjson_parse_file(path, &e);
    if (!j) return;
    {
        const char *nm = zjson_str(zjson_obj_get(j, "name"), NULL);
        if (nm && *nm) z_strlcpy(p->form_names[i], nm, sizeof(p->form_names[i]));
    }
    zjson_free(j);
}

/* 读服装显示名 */
static void read_outfit_name(zpet *p, int i)
{
    char path[1400];
    zerr e;
    zjson *j;
    z_snprintf(path, sizeof(path), "%s/outfits/%s.json", p->char_dir, p->outfits[i]);
    zerr_clear(&e);
    j = zjson_parse_file(path, &e);
    if (!j) return;
    {
        const char *nm = zjson_str(zjson_obj_get(j, "name"), NULL);
        if (nm && *nm) z_strlcpy(p->outfit_names[i], nm, sizeof(p->outfit_names[i]));
    }
    zjson_free(j);
}

static void collect_actions(zpet *p)
{
    int i, n;
    p->nactions = 0;
    if (!p->rig) return;
    n = zrig_action_count(p->rig);
    for (i = 0; i < n && p->nactions < ZPET_MAX_ACTIONS; ++i) {
        const char *id = zrig_action_id_at(p->rig, i);
        if (!id || !*id) continue;
        if (z_streq(id, "idle") || z_streq(id, "sleep")) continue;   /* 睡眠加到菜单末尾单独处理 */
        z_strlcpy(p->action_ids[p->nactions], id, sizeof(p->action_ids[0]));
        p->nactions++;
    }
}

static int load_rig_for(zpet *p, const char *form, zdiag *diag)
{
    char rig_path[1400];
    zrig *r;
    z_snprintf(rig_path, sizeof(rig_path), "%s/forms/%s/rig.json", p->char_dir, form);
    if (!z_file_exists(rig_path)) {
        zdiag_error(diag, rig_path, 0, 0, "", "找不到形态的 rig.json（角色包不完整？）");
        return -1;
    }
    z_snprintf(p->form_dir, sizeof(p->form_dir), "%s/forms/%s", p->char_dir, form);
    r = zrig_load(rig_path, p->form_dir, diag);
    if (!r) return -1;
    zrig_free(p->rig);
    p->rig = r;
    z_strlcpy(p->cfg.pet.form, form, sizeof(p->cfg.pet.form));
    collect_actions(p);
    {
        char line[512];
        zrig_describe(r, line, sizeof(line));
        ZLOGI("pet", "%s", line);
    }
    return 0;
}

zpet *zpet_create(const zconfig *cfg, zdiag *diag)
{
    zpet *p = (zpet *)z_calloc(1, sizeof(zpet));
    p->cfg = *cfg;
    z_strlcpy(p->root, cfg->root_dir, sizeof(p->root));
    z_snprintf(p->char_dir, sizeof(p->char_dir), "%s/characters/%s", cfg->root_dir, cfg->pet.character);
    p->scale = cfg->pet.scale;
    p->tool = (zpet_tool)cfg->pet.tool_default;
    p->pat_last_at = -100.0;
    zdiag_init(&p->diag);

    if (!z_is_dir(p->char_dir)) {
        zdiag_error(diag, p->char_dir, 0, 0, "", "角色包目录不存在");
        free(p);
        return NULL;
    }
    scan_forms(p);
    scan_outfits(p);
    {
        int i;
        for (i = 0; i < p->nforms; ++i) read_form_name(p, i);
        for (i = 0; i < p->noutfits; ++i) read_outfit_name(p, i);
    }
    if (p->nforms == 0) {
        zdiag_error(diag, p->char_dir, 0, 0, "forms", "角色包没有任何形态（forms/<形态>/rig.json）");
        free(p);
        return NULL;
    }
    if (load_rig_for(p, cfg->pet.form, diag) != 0) {
        /* 回退到第一个可用形态 */
        zdiag_warn(diag, p->char_dir, 0, 0, "form", "形态 '%s' 加载失败，回退到 '%s'",
                   cfg->pet.form, p->forms[0]);
        zdiag_init(&p->diag);
        if (load_rig_for(p, p->forms[0], diag) != 0) {
            free(p);
            return NULL;
        }
    }
    /* 默认服装（存在且配置指定才应用） */
    if (cfg->pet.outfit[0] && !z_streq(cfg->pet.outfit, "default")) {
        zdiag tmp;
        zdiag_init(&tmp);
        zpet_set_outfit(p, cfg->pet.outfit, &tmp);
    }
    return p;
}

void zpet_destroy(zpet *p)
{
    if (!p) return;
    zrig_free(p->rig);
    free(p);
}

/* ------------------------------------------------------------ 每帧 */
int zpet_tick(zpet *p, double now)
{
    int changed = 0;
    double dt;
    if (!p || !p->rig) return 0;
    dt = now - p->now;
    p->now = now;

    zrig_tick(p->rig, now);

    /* 空闲 → 睡眠；任何输入唤醒（交接文件 6、8.6） */
    if (p->sleeping) {
        if (p->idle_seconds < 0.5) {
            p->sleeping = 0;
            zrig_blink_set_enabled(p->rig, 1);
            /* 唤醒必须 force：sleep 优先级最高且声明为不可中断 */
            zrig_action_request(p->rig, "idle", "wake_up", 1);
            ZLOGI("pet", "用户输入，唤醒");
            changed = 1;
        }
    } else if (p->cfg.pet.idle_sleep_seconds > 0 &&
               p->idle_seconds > p->cfg.pet.idle_sleep_seconds) {
        if (zrig_action_request(p->rig, "sleep", "idle_timeout", 0))
            ZLOGI("pet", "空闲 %.0f 秒，进入睡眠", p->idle_seconds);
        p->sleeping = 1;
        zrig_blink_force(p->rig, 1);
        changed = 1;
    }

    /* 摸头持续：连续抚摸会累计到开心的表情 */
    if (p->pat_count > 0 && now - p->pat_last_at > 0.8) p->pat_count = 0;

    (void)dt;
    return changed;
}

const zimg *zpet_frame(zpet *p, int *out_w, int *out_h)
{
    if (!p || !p->rig) return NULL;
    return zrig_frame(p->rig, p->scale, out_w, out_h);
}

const char *zpet_character(const zpet *p) { return p ? p->cfg.pet.character : ""; }
const char *zpet_form(const zpet *p) { return p ? p->cfg.pet.form : ""; }
const char *zpet_outfit(const zpet *p) { return p && p->rig ? zrig_outfit(p->rig) : ""; }
const char *zpet_action(const zpet *p) { return p && p->rig ? zrig_action(p->rig) : ""; }
const char *zpet_last_reason(const zpet *p) { return p && p->rig ? zrig_action_last_reason(p->rig) : ""; }
double zpet_scale(const zpet *p) { return p ? p->scale : 1.0; }
double zpet_blink(const zpet *p) { return p && p->rig ? zrig_blink_value(p->rig) : 0.0; }
int zpet_sleeping(const zpet *p) { return p ? p->sleeping : 0; }
double zpet_idle_seconds(const zpet *p) { return p ? p->idle_seconds : 0.0; }

const char *zpet_form_name(const zpet *p)
{
    int i;
    if (!p) return "";
    for (i = 0; i < p->nforms; ++i)
        if (z_streq(p->forms[i], p->cfg.pet.form)) return p->form_names[i];
    return "";
}

int zpet_form_count(const zpet *p) { return p ? p->nforms : 0; }
const char *zpet_form_id_at(const zpet *p, int i)
{
    if (!p || i < 0 || i >= p->nforms) return "";
    return p->forms[i];
}
const char *zpet_form_name_at(const zpet *p, int i)
{
    if (!p || i < 0 || i >= p->nforms) return "";
    return p->form_names[i];
}
int zpet_outfit_count(const zpet *p) { return p ? p->noutfits : 0; }
const char *zpet_outfit_id_at(const zpet *p, int i)
{
    if (!p || i < 0 || i >= p->noutfits) return "";
    return p->outfits[i];
}
const char *zpet_outfit_name_at(const zpet *p, int i)
{
    if (!p || i < 0 || i >= p->noutfits) return "";
    return p->outfit_names[i];
}
int zpet_action_count(const zpet *p) { return p ? p->nactions : 0; }
const char *zpet_action_id_at(const zpet *p, int i)
{
    if (!p || i < 0 || i >= p->nactions) return "";
    return p->action_ids[i];
}

int zpet_set_form(zpet *p, const char *form_id, zdiag *diag)
{
    if (!p || !form_id) return -1;
    if (z_streq(form_id, p->cfg.pet.form)) return 0;
    if (load_rig_for(p, form_id, diag) != 0) return -1;
    /* 换形态后重新应用当前服装 */
    if (p->cfg.pet.outfit[0] && !z_streq(p->cfg.pet.outfit, "default")) {
        zdiag tmp;
        zdiag_init(&tmp);
        zpet_set_outfit(p, p->cfg.pet.outfit, &tmp);
    }
    return 0;
}

int zpet_set_outfit(zpet *p, const char *outfit_id, zdiag *diag)
{
    char path[1400];
    if (!p || !p->rig || !outfit_id) return -1;
    z_snprintf(path, sizeof(path), "%s/outfits/%s.json", p->char_dir, outfit_id);
    if (!z_file_exists(path)) {
        zdiag_error(diag, path, 0, 0, "outfit", "服装不存在");
        return -1;
    }
    if (zrig_apply_outfit(p->rig, path, diag) != 0) return -1;
    z_strlcpy(p->cfg.pet.outfit, outfit_id, sizeof(p->cfg.pet.outfit));
    return 0;
}

/* ------------------------------------------------------------ 交互 */
int zpet_hit(const zpet *p, int x, int y)
{
    if (!p || !p->rig) return 0;
    return zrig_hit_test(p->rig, x, y, p->cfg.pet.hit_alpha_threshold);
}

const char *zpet_region(const zpet *p, int x, int y, char *out_action, size_t cap,
                        const char **out_cursor)
{
    const char *id;
    int cx = 0, cy = 0;
    if (!p || !p->rig) return NULL;
    /* 入参是窗口内（帧缓冲）坐标；区域定义在画布坐标里 */
    zrig_frame_to_canvas(p->rig, x, y, &cx, &cy);
    id = zrig_region_at(p->rig, cx, cy, out_action, cap);
    if (id && out_cursor) *out_cursor = zrig_region_cursor(p->rig, id);
    return id;
}

int zpet_action_request(zpet *p, const char *id, const char *reason, int force)
{
    if (!p || !p->rig) return 0;
    return zrig_action_request(p->rig, id, reason, force);
}

int zpet_poke(zpet *p, int x, int y, zpet_tool tool, double now)
{
    char action[48] = {0};
    const char *region = NULL;
    if (!p || !p->rig) return 0;
    p->idle_seconds = 0.0;
    if (p->sleeping) {
        p->sleeping = 0;
        zrig_blink_force(p->rig, -1);
        zrig_action_request(p->rig, "idle", "wake_by_poke", 1);
    }
    region = zpet_region(p, x, y, action, sizeof(action), NULL);

    if (tool == ZPET_TOOL_HAMMER) {
        zrig_blink_trigger(p->rig);
        p->pat_count = 0;
        ZLOGD("pet", "锤击 (%d,%d) 区域=%s", x, y, region ? region : "无");
        return zrig_action_request(p->rig, "hammered", "hammer", 1);
    }
    /* 手：头部 → 摸头；其它 → 抚摸 */
    if (region && z_streq(region, "head")) {
        p->pat_count++;
        p->pat_last_at = now;
        if (p->pat_count >= 3) {
            p->pat_count = 0;
            return zrig_action_request(p->rig, "happy", "head_pat_combo", 0);
        }
        return zrig_action_request(p->rig, "head_pat", "head_pat", 0);
    }
    if (region && z_streq(region, "body")) {
        return zrig_action_request(p->rig, "stroke", "stroke", 0);
    }
    if (region && z_streq(region, "feet")) {
        return zrig_action_request(p->rig, "surprised", "poke_feet", 0);
    }
    return zrig_action_request(p->rig, "clicked", "click", 0);
}

int zpet_drag_start(zpet *p, int x, int y, double now)
{
    (void)x; (void)y; (void)now;
    if (!p) return 0;
    p->idle_seconds = 0.0;
    if (p->rig) {
        zrig_blink_trigger(p->rig);
        return zrig_action_request(p->rig, "dragged", "drag", 0);
    }
    return 0;
}

int zpet_drag_end(zpet *p, double now)
{
    (void)now;
    if (!p || !p->rig) return 0;
    return zrig_action_request(p->rig, "surprised", "drag_drop", 0);
}

void zpet_hover(zpet *p, int x, int y, int inside, double now)
{
    if (!p || !p->rig) return;
    p->hover_inside = inside;
    p->hover_x = x;
    p->hover_y = y;
    if (inside) {
        p->idle_seconds = 0.0;
        if (z_streq(zrig_action(p->rig), "idle"))
            zrig_action_request(p->rig, "focus", "hover", 0);
    } else {
        if (z_streq(zrig_action(p->rig), "focus"))
            zrig_action_request(p->rig, "idle", "hover_end", 0);
    }
    (void)now;
}

void zpet_notify_user_activity(zpet *p, double now)
{
    (void)now;
    if (!p) return;
    p->idle_seconds = 0.0;
}

void zpet_report_idle(zpet *p, double seconds)
{
    if (!p) return;
    p->idle_seconds = seconds;
}

/* ------------------------------------------------------------ 缩放 */
void zpet_set_scale(zpet *p, double scale)
{
    if (!p) return;
    p->scale = ZC_CLAMP(scale, p->cfg.pet.scale_min, p->cfg.pet.scale_max);
}

void zpet_scale_step(zpet *p, int dir)
{
    double step;
    if (!p) return;
    step = 0.05 * (dir >= 0 ? 1.0 : -1.0);
    zpet_set_scale(p, p->scale + step);
}

void zpet_scale_reset(zpet *p)
{
    if (!p) return;
    p->scale = 1.0;
    p->scale = ZC_CLAMP(p->scale, p->cfg.pet.scale_min, p->cfg.pet.scale_max);
}

void zpet_set_tool(zpet *p, zpet_tool t) { if (p) p->tool = t; }
zpet_tool zpet_tool_get(const zpet *p) { return p ? p->tool : ZPET_TOOL_HAND; }

void zpet_sync_to_config(const zpet *p, zconfig *cfg)
{
    if (!p || !cfg) return;
    cfg->pet.scale = p->scale;
    cfg->pet.tool_default = (int)p->tool;
    z_strlcpy(cfg->pet.form, p->cfg.pet.form, sizeof(cfg->pet.form));
    z_strlcpy(cfg->pet.outfit, p->cfg.pet.outfit, sizeof(cfg->pet.outfit));
}
