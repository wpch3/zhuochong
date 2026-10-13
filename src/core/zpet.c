/* zpet.c - 桌宠应用逻辑实现 */
#include "zpet.h"
#include "zjson.h"
#include "zinteract.h"

#include <math.h>
#include <time.h>

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
    int     last_fw, last_fh;   /* 上一帧尺寸：hover 换算视线方向要用 */

    /* 互动规则与台词（config/interactions.json + dialogue.json） */
    zinteract *inter;
    char    last_line[256];
    char    last_mood[24];

    /* 口型同步（A4）：一条 0~1 的开口度包络按时间推进 */
    double *ls_vals;
    int    *ls_vis;        /* 每帧的音素（rig 音素表下标，-1 = 没有）；NULL = 只有音量 */
    int     ls_n;
    double  ls_fps, ls_t0, ls_level;
    double  ls_cursor;     /* 当前采样位置（帧），音素查表用 */
    int     ls_active;
    char    ls_id[64];
    char    ls_text[256];
};

#define ZPET_LIPSYNC_MAX 4096

#define ZPET_MAX_ACTIONS 32

static const zi_rule *match_rule(zpet *p, const char *kind, const char *region,
                                 const char *mood, int count);
static void lipsync_tick(zpet *p, double now);
static int run_rule(zpet *p, const zi_rule *r, const char *fb_action,
                    const char *fb_reason, int fb_force, double now);

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
    /* 互动规则：加载失败不致命，回退到内置的最简互动（诊断已写入 diag） */
    p->inter = zinteract_load(cfg->root_dir, cfg->pet.character, diag);
    if (!p->inter)
        zdiag_warn(diag, cfg->root_dir, 0, 0, "interactions", "互动规则加载失败，已回退为最简互动（只做动作）");
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
    zinteract_free(p->inter);
    zrig_free(p->rig);
    free(p->ls_vals);
    free(p->ls_vis);
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
    lipsync_tick(p, now);

    /* 空闲 → 睡眠；任何输入唤醒（交接文件 6、8.6） */
    if (p->sleeping) {
        if (p->idle_seconds < 0.5) {
            p->sleeping = 0;
            zrig_blink_set_enabled(p->rig, 1);
            /* 唤醒必须 force：sleep 优先级最高且声明为不可中断 */
            run_rule(p, match_rule(p, "wake", "", NULL, 0), "idle", "wake_up", 1, now);
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
    const zimg *fr;
    int w = 0, h = 0;
    if (!p || !p->rig) return NULL;
    fr = zrig_frame(p->rig, p->scale, &w, &h);
    p->last_fw = w;
    p->last_fh = h;
    if (out_w) *out_w = w;
    if (out_h) *out_h = h;
    return fr;
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

/* ---- 口型同步 ---- */
static void lipsync_apply(zpet *p, double v)
{
    p->ls_level = v;
    if (!p->rig) return;
    if (p->ls_vis) {              /* 母音識別方式：音素给嘴形，包络给强度 */
        int i = (int)p->ls_cursor;
        const char *vid;
        if (i < 0) i = 0;
        if (i >= p->ls_n) i = p->ls_n - 1;
        vid = zrig_viseme_id(p->rig, p->ls_vis[i]);
        if (vid) { zrig_viseme_set(p->rig, vid, v); return; }
    }
    zrig_param_set(p->rig, zrig_lipsync_param(p->rig), v);   /* 音量连动方式 */
}

int zpet_lipsync_start_v(zpet *p, const double *values, const char *const *visemes,
                         int n, double fps, double now)
{
    int i;
    if (!p || !values || n < 2 || fps <= 0.0) return -1;
    if (n > ZPET_LIPSYNC_MAX) n = ZPET_LIPSYNC_MAX;
    free(p->ls_vals);
    free(p->ls_vis);
    p->ls_vis = NULL;
    p->ls_vals = (double *)malloc(sizeof(double) * (size_t)n);
    if (!p->ls_vals) { p->ls_active = 0; return -1; }
    for (i = 0; i < n; ++i) p->ls_vals[i] = ZC_CLAMP(values[i], 0.0, 1.0);
    if (visemes && p->rig && zrig_viseme_count(p->rig) > 0) {
        p->ls_vis = (int *)malloc(sizeof(int) * (size_t)n);
        if (p->ls_vis) {
            for (i = 0; i < n; ++i) {
                int vi = visemes[i] ? zrig_viseme_find(p->rig, visemes[i]) : -1;
                if (vi < 0) vi = zrig_viseme_find(p->rig, "SIL");
                if (vi < 0) vi = 0;
                p->ls_vis[i] = vi;
            }
        }
    }
    p->ls_n = n;
    p->ls_fps = fps;
    p->ls_t0 = now;
    p->ls_cursor = 0.0;
    p->ls_active = 1;
    if (p->rig) zrig_set_mouth_mute(p->rig, 1);
    lipsync_apply(p, p->ls_vals[0]);
    return 0;
}

int zpet_lipsync_start(zpet *p, const double *values, int n, double fps, double now)
{
    return zpet_lipsync_start_v(p, values, NULL, n, fps, now);
}

void zpet_lipsync_stop(zpet *p)
{
    if (!p) return;
    p->ls_active = 0;
    p->ls_level = 0.0;
    p->ls_cursor = 0.0;
    free(p->ls_vis);
    p->ls_vis = NULL;
    if (p->rig) {
        zrig_viseme_clear(p->rig);
        zrig_param_reset(p->rig, zrig_lipsync_param(p->rig));
        zrig_set_mouth_mute(p->rig, 0);
    }
}

int    zpet_lipsync_active(const zpet *p) { return p ? p->ls_active : 0; }
double zpet_lipsync_level(const zpet *p)  { return p ? p->ls_level : 0.0; }
const char *zpet_lipsync_id(const zpet *p)   { return (p && p->ls_id[0]) ? p->ls_id : ""; }
const char *zpet_lipsync_text(const zpet *p) { return (p && p->ls_text[0]) ? p->ls_text : ""; }

double zpet_lipsync_remain(const zpet *p)
{
    double total;
    if (!p || !p->ls_active || p->ls_fps <= 0.0) return 0.0;
    total = (p->ls_n - 1) / p->ls_fps;
    total -= (p->now - p->ls_t0);
    return total > 0.0 ? total : 0.0;
}

/* 按当前时间取样包络；播完返回 0 并自动收尾 */
static void lipsync_tick(zpet *p, double now)
{
    double x, frac, v;
    int i;
    if (!p->ls_active || !p->ls_vals || p->ls_n < 2) return;
    x = (now - p->ls_t0) * p->ls_fps;
    if (x <= 0.0) { p->ls_cursor = 0.0; lipsync_apply(p, p->ls_vals[0]); return; }
    i = (int)x;
    if (i >= p->ls_n - 1) { zpet_lipsync_stop(p); return; }
    frac = x - (double)i;
    p->ls_cursor = x;
    v = p->ls_vals[i] * (1.0 - frac) + p->ls_vals[i + 1] * frac;
    lipsync_apply(p, v);
}

int zpet_lipsync_load(zpet *p, const char *line_id, double now)
{
    char path[1024];
    zjson *root = NULL, *arr;
    zerr err;
    double *vals = NULL;
    double fps;
    int n, i, rc = -1;
    const char *s;
    if (!p || !line_id || !*line_id) return -1;
    /* 只允许安全字符，避免 ../ 之类越权读文件 */
    for (s = line_id; *s; ++s)
        if (!((*s >= 'a' && *s <= 'z') || (*s >= 'A' && *s <= 'Z') ||
              (*s >= '0' && *s <= '9') || *s == '_' || *s == '-')) return -1;
    z_snprintf(path, sizeof(path), "%s/voice/lipsync/%s.json", p->char_dir, line_id);
    root = zjson_parse_file(path, &err);
    if (!root) {
        ZLOGW("pet", "口型包络读不到：%s", path);
        return -1;
    }
    arr = zjson_obj_get(root, "values");
    n = arr ? (int)zjson_count(arr) : 0;
    fps = zjson_num(zjson_obj_get(root, "fps"), 30.0);
    if (n >= 2) {
        /* 可选的 visemes：每帧一个音素名（"A"/"I"/…）。有就走母音識別，
           没有就还是音量连动——不编口型，编出来的嘴型对不上反而更假。 */
        zjson *vis = zjson_obj_get(root, "visemes");
        const char **vnames = NULL;
        if (n > ZPET_LIPSYNC_MAX) n = ZPET_LIPSYNC_MAX;
        vals = (double *)malloc(sizeof(double) * (size_t)n);
        if (vis && zjson_is(vis, ZJSON_ARR) && (int)zjson_count(vis) >= n)
            vnames = (const char **)malloc(sizeof(char *) * (size_t)n);
        if (vals) {
            for (i = 0; i < n; ++i) vals[i] = zjson_num(zjson_at(arr, (size_t)i), 0.0);
            if (vnames)
                for (i = 0; i < n; ++i)
                    vnames[i] = zjson_str(zjson_at(vis, (size_t)i), "SIL");
            rc = zpet_lipsync_start_v(p, vals, vnames, n, fps, now);
            free(vals);
        }
        free((void *)vnames);
    }
    if (rc == 0) {
        z_strlcpy(p->ls_id, line_id, sizeof(p->ls_id));
        z_strlcpy(p->ls_text, zjson_str(zjson_obj_get(root, "text"), ""), sizeof(p->ls_text));
        ZLOGI("pet", "口型同步：%s（%d 帧 @ %.0ffps）", line_id, n, fps);
    } else {
        ZLOGW("pet", "口型包络格式不对：%s", path);
    }
    zjson_free(root);
    return rc;
}

int zpet_action_request(zpet *p, const char *id, const char *reason, int force)
{
    if (!p || !p->rig) return 0;
    return zrig_action_request(p->rig, id, reason, force);
}

/* ------------------------------------------------------------ 互动分发 */
static const zi_rule *match_rule(zpet *p, const char *kind, const char *region,
                                 const char *mood, int count)
{
    return p->inter ? zinteract_match(p->inter, kind, region, mood, count) : NULL;
}

/* 执行规则：动作（无规则时用回退动作）+ 台词（受冷却/间隔限制）。 */
static int local_day(void)
{
    time_t t = time(NULL);
    struct tm *tm = localtime(&t);
    return tm ? tm->tm_year * 400 + tm->tm_yday : 0;
}

static void lipsync_tick(zpet *p, double now);
static int run_rule(zpet *p, const zi_rule *r, const char *fb_action,
                    const char *fb_reason, int fb_force, double now)
{
    char line[256] = "";
    int ok, up = 0;
    if (!p->rig) return 0;
    if (!r) return zrig_action_request(p->rig, fb_action, fb_reason, fb_force);
    ok = zrig_action_request(p->rig, r->action, r->id, r->force);
    if (p->inter && r->affection_gain)
        up = zinteract_add_affection(p->inter, r->affection_gain, local_day());
    if (up) {
        /* 好感升档：优先说升档台词，本次互动的普通台词让位 */
        const zi_rule *tu = match_rule(p, "tier_up", "", NULL, 0);
        if (tu && zinteract_speak(p->inter, tu, now, line, sizeof(line)))
            z_strlcpy(p->last_line, line, sizeof(p->last_line));
    } else if (p->inter && zinteract_speak(p->inter, r, now, line, sizeof(line))) {
        z_strlcpy(p->last_line, line, sizeof(p->last_line));
    }
    return ok;
}

int zpet_poke(zpet *p, int x, int y, zpet_tool tool, double now)
{
    char action[48] = {0};
    const char *region = NULL;
    const char *kind;
    const zi_rule *r;
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
        kind = "hammer";
    } else {
        kind = "poke";
        /* 连续摸头计数只统计头部 */
        if (region && z_streq(region, "head")) {
            p->pat_count++;
            p->pat_last_at = now;
        }
    }
    r = match_rule(p, kind, region ? region : "", NULL, p->pat_count);
    if (r && r->reset_count) p->pat_count = 0;
    if (!r) return run_rule(p, NULL, "clicked", "click", 0, now);
    return run_rule(p, r, NULL, NULL, 0, now);
}

int zpet_drag_start(zpet *p, int x, int y, double now)
{
    (void)x; (void)y;
    if (!p) return 0;
    p->idle_seconds = 0.0;
    if (!p->rig) return 0;
    zrig_blink_trigger(p->rig);
    return run_rule(p, match_rule(p, "drag_start", "", NULL, 0), "dragged", "drag", 0, now);
}

int zpet_drag_end(zpet *p, double now)
{
    if (!p || !p->rig) return 0;
    return run_rule(p, match_rule(p, "drag_end", "", NULL, 0), "surprised", "drag_drop", 0, now);
}

/* ------------------------------------------------------------ 情绪与语音事件 */
int zpet_express(zpet *p, const char *mood, double now)
{
    const zi_rule *r;
    if (!p || !p->rig || !mood || !mood[0]) return 0;
    z_strlcpy(p->last_mood, mood, sizeof(p->last_mood));
    r = match_rule(p, "mood", "", mood, 0);
    if (!r) return 0;   /* 没有对应规则：只记录情绪，不改动作 */
    return run_rule(p, r, NULL, NULL, 0, now);
}

int zpet_call_event(zpet *p, const char *kind, const char *text, const char *mood, double now)
{
    const zi_rule *r;
    int ok = 0;
    if (!p || !p->rig || !kind) return 0;
    if (z_streq(kind, "call_reply") && text && text[0])
        z_strlcpy(p->last_line, text, sizeof(p->last_line));   /* 模型回复原文优先于台词表 */
    r = match_rule(p, kind, "", NULL, 0);
    if (r) ok = run_rule(p, r, NULL, NULL, 0, now);
    if (mood && mood[0]) ok = zpet_express(p, mood, now) || ok;
    return ok;
}

const char *zpet_last_line(const zpet *p) { return p ? p->last_line : ""; }
const char *zpet_last_mood(const zpet *p) { return p ? p->last_mood : ""; }

/* ------------------------------------------------------------ 好感度 */
int zpet_affection(const zpet *p) { return p && p->inter ? zinteract_affection(p->inter) : 0; }
int zpet_affection_tier(const zpet *p) { return p && p->inter ? zinteract_tier(p->inter) : 0; }
const char *zpet_affection_tier_name(const zpet *p)
{
    return p && p->inter ? zinteract_tier_name(p->inter) : "";
}
void zpet_set_affection(zpet *p, int points)
{
    if (p && p->inter) zinteract_set_affection(p->inter, points);
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
        /* 视线跟随光标：眼球是独立部件（带 gaze 标签），这里把屏幕坐标
           换成 [-1,1] 的方向喂给 rig。原来这段算完就丢了（zrig_gaze(NULL,0,0)），
           等于拆了眼球却没人看 —— 2026-10-12 修。 */
        if (p->last_fw > 0 && p->last_fh > 0) {
            double nx = ((double)x - p->last_fw * 0.5) / (p->last_fw * 0.5);
            double ny = ((double)y - p->last_fh * 0.32) / (p->last_fh * 0.5);
            if (nx < -1.0) nx = -1.0;
            if (nx > 1.0) nx = 1.0;
            if (ny < -1.0) ny = -1.0;
            if (ny > 1.0) ny = 1.0;
            zrig_gaze(p->rig, nx, ny);
        }
    } else {
        if (z_streq(zrig_action(p->rig), "focus"))
            zrig_action_request(p->rig, "idle", "hover_end", 0);
        zrig_gaze_reset(p->rig);
    }
    (void)now;
}

void zpet_set_blink(zpet *p, double v)
{
    if (p && p->rig) zrig_blink_set_manual(p->rig, v);
}

double zpet_blink_manual(const zpet *p)
{
    return (p && p->rig) ? zrig_blink_manual(p->rig) : -1.0;
}

/* 表情层（≈ Live2D expression）：叠在动作之上的一组参数偏移。 */
int zpet_expression_count(const zpet *p) { return (p && p->rig) ? zrig_expression_count(p->rig) : 0; }

const char *zpet_expression_id_at(const zpet *p, int i)
{
    return (p && p->rig) ? zrig_expression_id(p->rig, i) : NULL;
}

const char *zpet_expression_name_at(const zpet *p, int i)
{
    return (p && p->rig) ? zrig_expression_name(p->rig, i) : NULL;
}

const char *zpet_expression(const zpet *p)
{
    return (p && p->rig) ? zrig_expression(p->rig) : NULL;
}

int zpet_expression_set(zpet *p, const char *id)
{
    return (p && p->rig) ? zrig_expression_set(p->rig, id) : -1;
}

/* Pose：互斥部件组（≈ pose3.json）。zpet 同样只做转发。 */
int zpet_pose_count(const zpet *p) { return (p && p->rig) ? zrig_pose_count(p->rig) : 0; }

const char *zpet_pose_id_at(const zpet *p, int i)
{
    return (p && p->rig) ? zrig_pose_id(p->rig, i) : "";
}

int zpet_pose_entry_count(const zpet *p, const char *group)
{
    return (p && p->rig) ? zrig_pose_entry_count(p->rig, group) : 0;
}

const char *zpet_pose_entry_id_at(const zpet *p, const char *group, int i)
{
    return (p && p->rig) ? zrig_pose_entry_id(p->rig, group, i) : "";
}

const char *zpet_pose_current(const zpet *p, const char *group)
{
    return (p && p->rig) ? zrig_pose_current(p->rig, group) : "";
}

int zpet_pose_set(zpet *p, const char *group, const char *entry)
{
    return (p && p->rig) ? zrig_pose_set(p->rig, group, entry) : -1;
}

void zpet_pose_snap(zpet *p) { if (p && p->rig) zrig_pose_snap(p->rig); }

/* 命名参数层（≈ Live2D ParamXxx）：外部直驱一张参数表。
   zpet 只做转发，参数的定义与绑定都在角色包的 rig.json 里。 */
int zpet_param_count(const zpet *p) { return (p && p->rig) ? zrig_param_count(p->rig) : 0; }

int zpet_param_info(const zpet *p, int i, zrig_param_desc *out)
{
    return (p && p->rig) ? zrig_param_info(p->rig, i, out) : -1;
}

double zpet_param_get(const zpet *p, const char *id)
{
    return (p && p->rig) ? zrig_param_get(p->rig, id) : 0.0;
}

const char *zpet_lipsync_param(const zpet *p)
{
    return (p && p->rig) ? zrig_lipsync_param(p->rig) : "ParamMouthOpenY";
}

int zpet_blink_targets(const zpet *p)
{
    return (p && p->rig) ? zrig_blink_targets(p->rig) : 3;
}

/* ---- 口型音素层（测试台 / 语音模块用）---- */
int zpet_viseme_set(zpet *p, const char *id, double weight)
{
    if (!p || !p->rig) return -1;
    return zrig_viseme_set(p->rig, id, weight);
}

void zpet_viseme_clear(zpet *p) { if (p && p->rig) zrig_viseme_clear(p->rig); }
void zpet_viseme_snap(zpet *p)  { if (p && p->rig) zrig_viseme_snap(p->rig); }

const char *zpet_viseme_current(const zpet *p)
{
    const char *v = (p && p->rig) ? zrig_viseme_current(p->rig) : NULL;
    return v ? v : "";
}

double zpet_viseme_weight(const zpet *p)
{
    return (p && p->rig) ? zrig_viseme_weight(p->rig) : 0.0;
}

int zpet_viseme_count(const zpet *p) { return (p && p->rig) ? zrig_viseme_count(p->rig) : 0; }

const char *zpet_viseme_id(const zpet *p, int i)
{
    return (p && p->rig) ? zrig_viseme_id(p->rig, i) : NULL;
}

int zpet_param_set(zpet *p, const char *id, double v)
{
    return (p && p->rig) ? zrig_param_set(p->rig, id, v) : -1;
}

int zpet_param_reset(zpet *p, const char *id)
{
    return (p && p->rig) ? zrig_param_reset(p->rig, id) : -1;
}

void zpet_param_reset_all(zpet *p)
{
    if (p && p->rig) zrig_param_reset_all(p->rig);
}

void zpet_set_gaze(zpet *p, double nx, double ny, int on)
{
    if (!p || !p->rig) return;
    if (on) zrig_gaze(p->rig, nx, ny);
    else    zrig_gaze_reset(p->rig);
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
