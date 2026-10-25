/* zinteract.c - 互动规则、台词（按好感档变体）与好感度实现 */
#include "zinteract.h"
#include "zjson.h"
#include "zschema.h"

#include <string.h>

static const char *const k_kinds[] = {
    "poke", "hammer", "drag_start", "drag_end", "wake", "mood",
    "call_start", "call_end", "call_user_speaking", "call_reply", "tier_up",
    /* dress：换装/切差分（互斥组切档）时触发。region 写成 "<组>:<档>"，
       例如 "hairstyle:long"；只写组名 "hairstyle" 的规则当该组的兜底。
       这样不用给 zinteract_match 加参数 —— 组和档合成一个键就够了。 */
    "dress", NULL
};

static int kind_ok(const char *k)
{
    int i;
    for (i = 0; k_kinds[i]; ++i)
        if (z_streq(k, k_kinds[i])) return 1;
    return 0;
}

static int find_line_idx(const zinteract *z, const char *id)
{
    int i;
    for (i = 0; i < z->nlines; ++i)
        if (z_streq(z->lines[i].id, id)) return i;
    return -1;
}

/* 读取一个 texts 数组；返回有效句子数 */
static int load_texts(zi_var *v, const zjson *arr)
{
    size_t k;
    v->ntexts = 0;
    for (k = 0; arr && k < zjson_count(arr) && v->ntexts < ZI_MAX_TEXTS; ++k) {
        const char *t = zjson_str(zjson_at(arr, k), "");
        if (!t[0]) continue;
        z_strlcpy(v->texts[v->ntexts], t, sizeof(v->texts[0]));
        v->ntexts++;
    }
    return v->ntexts;
}

static void default_tiers(zinteract *z)
{
    static const char *const names[ZI_MAX_TIERS] = {"初识", "熟络", "亲近", "挚友"};
    static const int mins[ZI_MAX_TIERS] = {0, 30, 100, 250};
    int i;
    z->ntiers = ZI_MAX_TIERS;
    for (i = 0; i < ZI_MAX_TIERS; ++i) {
        z_strlcpy(z->tiers[i].name, names[i], sizeof(z->tiers[i].name));
        z->tiers[i].min_points = mins[i];
    }
}

/* 读取 affection 段（缺省用内置四档）。档位不合法时报错。 */
static int load_affection(zinteract *z, const zjson *doc, const char *path, zdiag *d)
{
    const zjson *tiers;
    size_t k;
    int bad = 0;

    z->daily_cap = 30;
    z->ntiers = 0;
    if (zjson_get((zjson *)doc, "affection.daily_cap"))
        z->daily_cap = (int)zjson_get_int(doc, "affection.daily_cap", 0, 30, 0, 100000, d, path);

    tiers = zjson_get((zjson *)doc, "affection.tiers");
    if (!tiers) {
        default_tiers(z);
        return 0;
    }
    if (!zjson_is(tiers, ZJSON_ARR)) {
        zdiag_error(d, path, 0, 0, "affection.tiers", "必须是数组");
        return -1;
    }
    for (k = 0; k < zjson_count(tiers); ++k) {
        const zjson *t = zjson_at(tiers, k);
        zi_tier *zt;
        int mn;
        char field[48];
        z_snprintf(field, sizeof(field), "affection.tiers[%u]", (unsigned)k);
        if (z->ntiers >= ZI_MAX_TIERS) {
            zdiag_warn(d, path, 0, 0, field, "好感档位超过 %d 个，多余的被忽略", ZI_MAX_TIERS);
            break;
        }
        zt = &z->tiers[z->ntiers];
        zjson_get_strbuf(t, "name", 1, "", zt->name, sizeof(zt->name), d, path);
        mn = (int)zjson_get_int(t, "min", 1, 0, 0, 1000000, d, path);
        zt->min_points = mn;
        if (z->ntiers == 0 && mn != 0) {
            zdiag_error(d, path, 0, 0, field, "第一档 min 必须是 0（未达到任何档位时的起点）");
            bad = 1;
        }
        if (z->ntiers > 0 && mn <= z->tiers[z->ntiers - 1].min_points) {
            zdiag_error(d, path, 0, 0, field, "档位 min 必须逐档递增（当前 %d ≤ 上一档）", mn);
            bad = 1;
        }
        z->ntiers++;
    }
    if (z->ntiers == 0) default_tiers(z);
    return bad ? -1 : 0;
}

/* 读取 dialogue.json。每条台词：texts（基础，任何好感档可用）+ tiers（按档位的变体）。 */
static int load_dialogue(zinteract *z, const char *path, const char *schema_path, zdiag *d)
{
    zerr err;
    zjson *doc;
    zjson *arr;
    size_t i;
    char status[16] = "";

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
    if (zschema_validate_file(schema_path, doc, path, d) < 0)
        zdiag_warn(d, schema_path, 0, 0, "", "缺少台词 schema 文件，跳过结构校验");
    if (zjson_get(doc, "status"))
        zjson_get_strbuf(doc, "status", 0, "", status, sizeof(status), d, path);
    z->dialogue_status_draft = z_streq(status, "draft");
    arr = zjson_get(doc, "lines");
    if (!arr || !zjson_is(arr, ZJSON_ARR)) {
        zdiag_error(d, path, 0, 0, "lines", "缺少 lines 数组");
        zjson_free(doc);
        return -1;
    }
    for (i = 0; i < zjson_count(arr); ++i) {
        zjson *e = zjson_at(arr, i);
        zi_line *ln;
        zjson *base, *tiers;
        size_t k;
        char field[48];
        int ok_base = 0;
        z_snprintf(field, sizeof(field), "lines[%u]", (unsigned)i);
        if (z->nlines >= ZI_MAX_LINES) {
            zdiag_warn(d, path, 0, 0, "lines", "台词超过 %d 条，多余的被忽略", ZI_MAX_LINES);
            break;
        }
        ln = &z->lines[z->nlines];
        memset(ln, 0, sizeof(*ln));
        zjson_get_strbuf(e, "id", 1, "", ln->id, sizeof(ln->id), d, path);
        if (!ln->id[0]) { zdiag_error(d, path, 0, 0, field, "台词缺少 id"); continue; }

        base = zjson_obj_get(e, "texts");
        if (base) {
            if (!zjson_is(base, ZJSON_ARR)) {
                zdiag_error(d, path, 0, 0, field, "台词 '%s' 的 texts 必须是数组", ln->id);
                continue;
            }
            if (load_texts(&ln->vars[0], base) > 0) {
                ln->vars[0].min_tier = 0;
                ln->nvars = 1;
                ok_base = 1;
            }
        }
        if (!ok_base) {
            zdiag_error(d, path, 0, 0, field, "台词 '%s' 缺少基础文本 texts（任何好感档都需要）", ln->id);
            continue;
        }
        tiers = zjson_obj_get(e, "tiers");
        for (k = 0; tiers && k < zjson_count(tiers); ++k) {
            zjson *te = zjson_at(tiers, k);
            zi_var *v;
            int tier;
            char tf[64];
            z_snprintf(tf, sizeof(tf), "%s.tiers[%u]", field, (unsigned)k);
            if (ln->nvars >= ZI_MAX_VARS) {
                zdiag_warn(d, path, 0, 0, tf, "变体超过 %d 个，多余的被忽略", ZI_MAX_VARS);
                break;
            }
            tier = (int)zjson_get_int(te, "tier", 1, 0, 0, ZI_MAX_TIERS - 1, d, path);
            if (tier >= z->ntiers) {
                zdiag_error(d, path, 0, 0, tf, "台词 '%s' 的 tier=%d 超出好感档位数（%d）", ln->id, tier, z->ntiers);
                continue;
            }
            v = &ln->vars[ln->nvars];
            if (load_texts(v, zjson_obj_get(te, "texts")) > 0) {
                v->min_tier = tier;
                ln->nvars++;
            } else {
                zdiag_error(d, path, 0, 0, tf, "台词 '%s' 的该档变体没有有效文本", ln->id);
            }
        }
        z->nlines++;
    }
    zjson_free(doc);
    return 0;
}

zinteract *zinteract_load(const char *root_dir, const char *character, zdiag *diag)
{
    char path[1024], dpath[1024], schema[1024], dschema[1024];
    zerr err;
    zjson *doc;
    zjson *rules;
    zinteract *z;
    size_t i;
    int bad = 0;
    int err_before = 0;

    z = (zinteract *)z_calloc(1, sizeof(zinteract));
    z->speech_enabled = 1;
    z->min_gap_s = 2.0;
    z->last_any_speak_at = -1e9;
    z->gain_day = -1;
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

    if (zjson_get(doc, "speech.enabled"))
        z->speech_enabled = (int)zjson_get_bool(doc, "speech.enabled", 0, 1, diag, path);
    if (zjson_get(doc, "speech.min_gap_s"))
        z->min_gap_s = zjson_get_num(doc, "speech.min_gap_s", 0, 2.0, diag, path);

    /* 好感与台词的错误都记在 diag 里：用错误计数判断是否失败 */
    err_before = diag ? diag->error_count : 0;
    if (load_affection(z, doc, path, diag) != 0) bad = 1;
    z_snprintf(dschema, sizeof(dschema), "%s/schemas/dialogue.schema.json", root_dir);
    if (load_dialogue(z, dpath, dschema, diag) != 0) bad = 1;
    if (diag && diag->error_count > err_before) bad = 1;

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
            zjson *lines;
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
            /* 可选字段：缺键时保留默认值（zjson_get_* 缺键会写警告，所以先判断是否存在） */
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
            if (zjson_get(e, "affection_gain"))
                r->affection_gain = (int)zjson_get_int(e, "affection_gain", 0, 0, -50, 50, diag, path);
            if (zjson_get(e, "cooldown_s"))
                r->cooldown_s = zjson_get_num(e, "cooldown_s", 0, 0.0, diag, path);
            if (r->cooldown_s < 0) r->cooldown_s = 0;
            if (kind[0] && z_streq(kind, "mood") && !r->mood[0]) {
                zdiag_error(diag, path, 0, 0, field, "kind=mood 的规则必须写 mood");
                bad = 1;
                continue;
            }
            lines = zjson_obj_get(e, "lines");
            for (k = 0; lines && k < zjson_count(lines) && (int)k < ZI_MAX_REF; ++k) {
                const char *lid = zjson_str(zjson_at(lines, k), "");
                if (find_line_idx(z, lid) < 0) {
                    zdiag_error(diag, path, 0, 0, field,
                                "台词 id '%s' 在 %s 中不存在", lid, dpath);
                    bad = 1;
                    continue;
                }
                z_strlcpy(r->lines[r->nlines], lid, sizeof(r->lines[0]));
                r->nlines++;
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

/* 当前好感档下，取最高可用档的变体并轮换句子 */
static int pick_text(zinteract *z, zi_line *ln, char *out, size_t cap)
{
    zi_var *best = NULL;
    int i, cur = zinteract_tier(z);
    for (i = 0; i < ln->nvars; ++i) {
        zi_var *v = &ln->vars[i];
        if (v->min_tier > cur) continue;
        if (!best || v->min_tier > best->min_tier) best = v;
    }
    if (!best || best->ntexts == 0) return 0;
    z_strlcpy(out, best->texts[best->next % best->ntexts], cap);
    best->next++;
    return 1;
}

int zinteract_speak(zinteract *z, const zi_rule *r, double now, char *out, size_t cap)
{
    zi_rule *rw = NULL;
    int i, li;
    if (out && cap) out[0] = 0;
    if (!z || !r || !z->speech_enabled || r->nlines == 0) return 0;
    /* 时钟倒流要当"早就凉透了"，不能当"刚说过"。
       `now - last < gap` 在 now < last 时是负数、恒成立 —— 一旦某个调用方先拿
       虚拟时间（预览台 /api/pause + /api/step 空跑）记了时间戳，再换回真实单调钟，
       台词就会整整哑掉一段时间，而且**没有任何报错**（2026-10-25 实测：
       摸头 → 空跑 30 秒 → 解冻 → 再摸头，气泡冻在上一句，seq 不动）。
       宿主嵌入时 likewise：时钟源可以换，但"过去了多久"不能是负的。 */
    if (now >= z->last_any_speak_at
            && now - z->last_any_speak_at < z->min_gap_s) return 0;
    if (now >= r->last_speak_at
            && now - r->last_speak_at < r->cooldown_s) return 0;

    /* 规则由调用方以 const 传入：这里从 z->rules 里找回可写指针，用来记录冷却与轮换 */
    for (i = 0; i < z->nrules; ++i)
        if (&z->rules[i] == r) { rw = &z->rules[i]; break; }
    if (!rw) return 0;

    li = find_line_idx(z, rw->lines[rw->speak_count % rw->nlines]);
    if (li < 0) return 0;
    if (!pick_text(z, &z->lines[li], out, cap)) return 0;

    rw->last_speak_at = now;
    rw->speak_count++;
    z->last_any_speak_at = now;
    return 1;
}

/* ---------------------------------------------------------- 好感度 */
int zinteract_affection(const zinteract *z) { return z ? z->affection : 0; }

void zinteract_set_affection(zinteract *z, int points)
{
    if (!z) return;
    z->affection = points < 0 ? 0 : points;
}

int zinteract_tier(const zinteract *z)
{
    int t = 0, i;
    if (!z) return 0;
    for (i = 0; i < z->ntiers; ++i)
        if (z->affection >= z->tiers[i].min_points) t = i;
    return t;
}

const char *zinteract_tier_name(const zinteract *z)
{
    if (!z || z->ntiers == 0) return "";
    return z->tiers[zinteract_tier(z)].name;
}

int zinteract_add_affection(zinteract *z, int delta, int day)
{
    int before, after;
    if (!z) return 0;
    if (day != z->gain_day) {
        z->gain_day = day;
        z->day_gain = 0;
    }
    before = zinteract_tier(z);
    if (delta > 0) {
        int room = z->daily_cap - z->day_gain;
        if (room <= 0) return 0;
        if (delta > room) delta = room;
        z->day_gain += delta;
    }
    z->affection += delta;
    if (z->affection < 0) z->affection = 0;
    after = zinteract_tier(z);
    return after > before;
}
