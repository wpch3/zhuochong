/* zinteract.c - 互动规则与台词实现 */
#include "zinteract.h"
#include "zjson.h"
#include "zschema.h"

#include <string.h>

static const char *const k_kinds[] = {
    "poke", "hammer", "drag_start", "drag_end", "wake", "mood",
    "call_start", "call_end", "call_user_speaking", "call_reply", NULL
};

static int kind_ok(const char *k)
{
    int i;
    for (i = 0; k_kinds[i]; ++i)
        if (z_streq(k, k_kinds[i])) return 1;
    return 0;
}

static int load_dialogue(zinteract *z, const char *path, zdiag *d)
{
    zerr err;
    zjson *doc;
    size_t i;
    char status[16] = "";
    zjson *arr;

    zerr_clear(&err);
    if (!z_file_exists(path)) {
        zdiag_error(d, path, 0, 0, "", "台词文件不存在（角色包不完整）");
        return -1;
    }
    doc = zjson_parse_file(path, &err);
    if (!doc) {
        zdiag_error(d, path, err.line, err.col, "", "解析失败：%s", err.msg);
        return -1;
    }
    if (zjson_get(doc, "status"))
        zjson_get_strbuf(doc, "status", 0, "", status, sizeof(status), d, path);
    z->dialogue_status_draft = z_streq(status, "draft");
    arr = zjson_get(doc, "lines");
    if (!arr || !zjson_is(arr, ZJSON_ARR)) {
        zdiag_error(d, path, 0, 0, "lines", "缺少 lines 数组");
        zjson_free(doc);
        return -1;
    }
    for (i = 0; i < zjson_count(arr) && z->nlines < ZI_MAX_LINES; ++i) {
        zjson *e = zjson_at(arr, i);
        zi_line *ln = &z->lines[z->nlines];
        zjson *texts = e ? zjson_obj_get(e, "texts") : NULL;
        size_t k;
        char field[48];
        z_snprintf(field, sizeof(field), "lines[%u]", (unsigned)i);
        zjson_get_strbuf(e, "id", 1, "", ln->id, sizeof(ln->id), d, path);
        if (!ln->id[0]) { zdiag_error(d, path, 0, 0, field, "台词缺少 id"); continue; }
        if (!texts || !zjson_is(texts, ZJSON_ARR) || zjson_count(texts) == 0) {
            zdiag_error(d, path, 0, 0, field, "台词 '%s' 的 texts 必须是非空数组", ln->id);
            continue;
        }
        for (k = 0; k < zjson_count(texts) && (int)k < ZI_MAX_TEXTS; ++k) {
            zjson *t = zjson_at(texts, k);
            z_strlcpy(ln->texts[ln->ntexts], zjson_str(t, ""), sizeof(ln->texts[0]));
            if (ln->texts[ln->ntexts][0]) ln->ntexts++;
        }
        if (ln->ntexts == 0) { zdiag_error(d, path, 0, 0, field, "台词 '%s' 没有有效文本", ln->id); continue; }
        z->nlines++;
    }
    zjson_free(doc);
    return 0;
}

static const zi_line *find_line(const zinteract *z, const char *id)
{
    int i;
    for (i = 0; i < z->nlines; ++i)
        if (z_streq(z->lines[i].id, id)) return &z->lines[i];
    return NULL;
}

zinteract *zinteract_load(const char *root_dir, const char *character, zdiag *diag)
{
    char path[1024], dpath[1024], schema[1024];
    zerr err;
    zjson *doc;
    zjson *rules;
    zinteract *z;
    size_t i;
    int bad = 0;

    z = (zinteract *)z_calloc(1, sizeof(zinteract));
    z->speech_enabled = 1;
    z->min_gap_s = 2.0;
    z->last_any_speak_at = -1e9;
    z_strlcpy(z->character, character, sizeof(z->character));
    for (i = 0; i < ZI_MAX_RULES; ++i) z->rules[i].last_speak_at = -1e9;

    z_snprintf(path, sizeof(path), "%s/config/interactions.json", root_dir);
    z_snprintf(dpath, sizeof(dpath), "%s/characters/%s/dialogue.json", root_dir, character);
    z_snprintf(schema, sizeof(schema), "%s/schemas/interactions.schema.json", root_dir);

    zerr_clear(&err);
    if (!z_file_exists(path)) {
        zdiag_error(diag, path, 0, 0, "", "互动规则文件不存在");
        free(z);
        return NULL;
    }
    doc = zjson_parse_file(path, &err);
    if (!doc) {
        zdiag_error(diag, path, err.line, err.col, "", "解析失败：%s", err.msg);
        free(z);
        return NULL;
    }
    if (zschema_validate_file(schema, doc, path, diag) < 0)
        zdiag_warn(diag, schema, 0, 0, "", "缺少 schema 文件，跳过结构校验");

    /* 可选字段：缺键时保留默认值（zjson_get_* 缺键会写警告，所以先判断是否存在） */
    if (zjson_get(doc, "speech.enabled"))
        z->speech_enabled = (int)zjson_get_bool(doc, "speech.enabled", 0, 1, diag, path);
    if (zjson_get(doc, "speech.min_gap_s"))
        z->min_gap_s = zjson_get_num(doc, "speech.min_gap_s", 0, 2.0, diag, path);

    if (load_dialogue(z, dpath, diag) != 0) bad = 1;

    rules = zjson_get(doc, "rules");
    if (!rules || !zjson_is(rules, ZJSON_ARR)) {
        zdiag_error(diag, path, 0, 0, "rules", "缺少 rules 数组");
        bad = 1;
    } else {
        for (i = 0; i < zjson_count(rules); ++i) {
            zjson *e = zjson_at(rules, i);
            zi_rule *r;
            size_t k;
            char field[48], kind[32] = "";
            if (z->nrules >= ZI_MAX_RULES) {
                zdiag_warn(diag, path, 0, 0, "rules", "规则超过 %d 条，多余的被忽略", ZI_MAX_RULES);
                break;
            }
            z_snprintf(field, sizeof(field), "rules[%u]", (unsigned)i);
            r = &z->rules[z->nrules];
            zjson_get_strbuf(e, "id", 1, "", r->id, sizeof(r->id), diag, path);
            zjson_get_strbuf(e, "kind", 1, "", kind, sizeof(kind), diag, path);
            z_strlcpy(r->kind, kind, sizeof(r->kind));
            if (kind[0] && !kind_ok(kind)) {
                zdiag_error(diag, path, 0, 0, field, "未知的触发类型 kind='%s'", kind);
                bad = 1;
                continue;
            }
            if (zjson_get(e, "region"))
                zjson_get_strbuf(e, "region", 0, "", r->region, sizeof(r->region), diag, path);
            if (zjson_get(e, "mood"))
                zjson_get_strbuf(e, "mood", 0, "", r->mood, sizeof(r->mood), diag, path);
            zjson_get_strbuf(e, "action", 1, "", r->action, sizeof(r->action), diag, path);
            if (zjson_get(e, "force"))
                r->force = (int)zjson_get_bool(e, "force", 0, 0, diag, path);
            if (zjson_get(e, "reset_count"))
                r->reset_count = (int)zjson_get_bool(e, "reset_count", 0, 0, diag, path);
            if (zjson_get(e, "priority"))
                r->priority = (int)zjson_get_int(e, "priority", 0, 0, -100, 100, diag, path);
            if (zjson_get(e, "min_count"))
                r->min_count = (int)zjson_get_int(e, "min_count", 0, 0, 0, 100, diag, path);
            if (zjson_get(e, "cooldown_s"))
                r->cooldown_s = zjson_get_num(e, "cooldown_s", 0, 0.0, diag, path);
            if (r->cooldown_s < 0) r->cooldown_s = 0;
            if (kind[0] && z_streq(kind, "mood") && !r->mood[0]) {
                zdiag_error(diag, path, 0, 0, field, "kind=mood 的规则必须写 mood");
                bad = 1;
                continue;
            }
            {
                zjson *lines = zjson_obj_get(e, "lines");
                for (k = 0; lines && k < zjson_count(lines) && (int)k < ZI_MAX_REF; ++k) {
                    const char *lid = zjson_str(zjson_at(lines, k), "");
                    if (!find_line(z, lid)) {
                        zdiag_error(diag, path, 0, 0, field,
                                    "台词 id '%s' 在 %s 中不存在", lid, dpath);
                        bad = 1;
                        continue;
                    }
                    z_strlcpy(r->lines[r->nlines], lid, sizeof(r->lines[0]));
                    r->nlines++;
                }
            }
            z->nrules++;
        }
    }
    zjson_free(doc);
    if (bad) {
        zinteract_free(z);
        return NULL;
    }
    return z;
}

void zinteract_free(zinteract *z)
{
    free(z);
}

const zi_rule *zinteract_match(const zinteract *z, const char *kind,
                               const char *region, const char *mood, int count)
{
    const zi_rule *best = NULL;
    int i;
    if (!z || !kind) return NULL;
    for (i = 0; i < z->nrules; ++i) {
        const zi_rule *r = &z->rules[i];
        if (!z_streq(r->kind, kind)) continue;
        if (r->region[0] && !(region && z_streq(r->region, region))) continue;
        if (r->mood[0] && !(mood && z_streq(r->mood, mood))) continue;
        if (count < r->min_count) continue;
        if (!best || r->priority > best->priority) best = r;
    }
    return best;
}

int zinteract_speak(zinteract *z, const zi_rule *r, double now, char *out, size_t cap)
{
    const zi_line *ln;
    zi_rule *rw;
    zi_line *lw = NULL;
    int i;
    if (out && cap) out[0] = 0;
    if (!z || !r || !z->speech_enabled || r->nlines == 0) return 0;
    if (now - z->last_any_speak_at < z->min_gap_s) return 0;
    if (now - r->last_speak_at < r->cooldown_s) return 0;

    /* 规则是 const 进来的，这里需要写回冷却时间：从 z->rules 里找回可写指针 */
    rw = NULL;
    for (i = 0; i < z->nrules; ++i)
        if (&z->rules[i] == r) { rw = &z->rules[i]; break; }
    if (!rw) return 0;

    ln = find_line(z, r->lines[0]);
    if (!ln) return 0;
    for (i = 0; i < z->nlines; ++i)
        if (&z->lines[i] == ln) { lw = &z->lines[i]; break; }
    if (lw) {
        z_strlcpy(out, lw->texts[lw->next % lw->ntexts], cap);
        lw->next++;
    }
    rw->last_speak_at = now;
    z->last_any_speak_at = now;
    return 1;
}
