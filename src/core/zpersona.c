/* zpersona —— 角色人设与剧情的加载、合成、白名单写入。设计说明见 zpersona.h。 */
#include "zpersona.h"
#include "zjson.h"
#include "zschema.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

/* ------------------------------------------------------------------ 小工具 */

/* 往 out 里追加一行，越界就直接不写（宁可少一行，也不要截出半个汉字）。 */
static void line_add(char *out, size_t cap, size_t *len, const char *fmt, ...)
{
    char buf[768];
    va_list ap;
    size_t n;

    va_start(ap, fmt);
    vsnprintf(buf, sizeof(buf), fmt, ap);
    va_end(ap);

    n = strlen(buf);
    if (*len + n + 2 >= cap) return;      /* +2 = 换行和结尾 0 */
    memcpy(out + *len, buf, n);
    *len += n;
    out[(*len)++] = '\n';
    out[*len] = '\0';
}

static int trait_index(const zp_lib *lib, const char *id)
{
    int i;
    for (i = 0; i < lib->ntraits; ++i)
        if (strcmp(lib->traits[i].id, id) == 0) return i;
    return -1;
}

static const zp_preset *preset_find(const zp_lib *lib, const char *id)
{
    int i;
    for (i = 0; i < lib->npresets; ++i)
        if (strcmp(lib->presets[i].id, id) == 0) return &lib->presets[i];
    return NULL;
}

/* 1..5 翻成人话：1=低端原话，2=「比较」+低端，4=「比较」+高端，5=高端原话。
   中间值 3 返回 0 —— 提示词里不写「中等」这种对模型毫无约束力的废话。
   两端的词在 config/persona_presets.json 里必须写成能跟「比较」连用的说法
   （"话多" 而不是 "很爱说话"，否则会合出 "偏很爱说话" 这种不是人话的句子）。 */
static int trait_phrase(const zp_trait *t, int v, char *out, size_t cap)
{
    switch (v) {
        case 1: z_strlcpy(out, t->low, cap); return 1;
        case 2: z_snprintf(out, cap, "比较%s", t->low);  return 1;
        case 4: z_snprintf(out, cap, "比较%s", t->high); return 1;
        case 5: z_strlcpy(out, t->high, cap); return 1;
        default: return 0;
    }
}

/* ------------------------------------------------------------------ 加载 */

static int load_lib(zp_lib *lib, const char *root_dir, zdiag *d)
{
    char path[1024], schema[1024];
    zerr err;
    zjson *doc, *arr, *it, *tr;
    size_t i, n;
    int k;

    z_snprintf(path, sizeof(path), "%s/config/persona_presets.json", root_dir);
    z_snprintf(schema, sizeof(schema), "%s/schemas/persona_presets.schema.json", root_dir);
    if (!z_file_exists(path)) {
        zdiag_error(d, path, 0, 0, "", "性格预设库不存在");
        return 0;
    }
    zerr_clear(&err);
    doc = zjson_parse_file(path, &err);
    if (!doc) {
        zdiag_error(d, path, 0, 0, "", err.msg[0] ? err.msg : "解析失败");
        return 0;
    }
    if (z_file_exists(schema) && zschema_validate_file(schema, doc, path, d) < 0) {
        zjson_free(doc);
        return 0;
    }

    arr = zjson_obj_get(doc, "traits");
    n = zjson_count(arr);
    for (i = 0; i < n && lib->ntraits < ZP_MAX_TRAITS; ++i) {
        zp_trait *t = &lib->traits[lib->ntraits];
        it = zjson_at(arr, i);
        z_strlcpy(t->id,   zjson_str(zjson_obj_get(it, "id"), ""),   sizeof(t->id));
        z_strlcpy(t->name, zjson_str(zjson_obj_get(it, "name"), ""), sizeof(t->name));
        z_strlcpy(t->low,  zjson_str(zjson_obj_get(it, "low"), ""),  sizeof(t->low));
        z_strlcpy(t->high, zjson_str(zjson_obj_get(it, "high"), ""), sizeof(t->high));
        t->def = (int)zjson_int(zjson_obj_get(it, "default"), 3);
        if (t->def < 1) t->def = 1;
        if (t->def > 5) t->def = 5;
        if (t->id[0]) lib->ntraits++;
    }

    arr = zjson_obj_get(doc, "presets");
    n = zjson_count(arr);
    for (i = 0; i < n && lib->npresets < ZP_MAX_PRESETS; ++i) {
        zp_preset *p = &lib->presets[lib->npresets];
        it = zjson_at(arr, i);
        z_strlcpy(p->id,    zjson_str(zjson_obj_get(it, "id"), ""),    sizeof(p->id));
        z_strlcpy(p->name,  zjson_str(zjson_obj_get(it, "name"), ""),  sizeof(p->name));
        z_strlcpy(p->style, zjson_str(zjson_obj_get(it, "style"), ""), sizeof(p->style));
        tr = zjson_obj_get(it, "traits");
        for (k = 0; k < lib->ntraits; ++k) p->traits[k] = lib->traits[k].def;
        if (tr && zjson_is(tr, ZJSON_OBJ)) {
            p->has_traits = 1;
            for (k = 0; k < lib->ntraits; ++k) {
                int v = (int)zjson_int(zjson_obj_get(tr, lib->traits[k].id), lib->traits[k].def);
                p->traits[k] = (v < 1) ? 1 : (v > 5) ? 5 : v;
            }
        }
        if (p->id[0]) lib->npresets++;
    }

    zjson_free(doc);
    return lib->ntraits > 0 && lib->npresets > 0;
}

int zpersona_load(zpersona *zp, const char *root_dir, const char *character, zdiag *d)
{
    char path[1024], schema[1024];
    zerr err;
    zjson *doc, *o, *arr;
    size_t i, n;
    int k;

    memset(zp, 0, sizeof(*zp));
    z_strlcpy(zp->character, character, sizeof(zp->character));
    z_strlcpy(zp->preset, "blueprint", sizeof(zp->preset));
    z_strlcpy(zp->selfname, "我", sizeof(zp->selfname));

    if (!load_lib(&zp->lib, root_dir, d)) return 0;
    for (k = 0; k < zp->lib.ntraits; ++k) zp->tv[k] = zp->lib.traits[k].def;

    /* ① 蓝本：character.json 的 persona。读不到不算错，只是少一层。 */
    z_snprintf(path, sizeof(path), "%s/characters/%s/character.json", root_dir, character);
    if (z_file_exists(path)) {
        zerr_clear(&err);
        doc = zjson_parse_file(path, &err);
        if (doc) {
            z_strlcpy(zp->blueprint, zjson_str(zjson_obj_get(doc, "persona"), ""),
                      sizeof(zp->blueprint));
            z_strlcpy(zp->name, zjson_str(zjson_obj_get(doc, "name"), ""), sizeof(zp->name));
            zjson_free(doc);
        }
    }

    /* ②③ persona.json。**不存在是合法状态**（= 全默认 = 沿用角色原设）。 */
    z_snprintf(path, sizeof(path), "%s/characters/%s/persona.json", root_dir, character);
    if (!z_file_exists(path)) return 1;

    zerr_clear(&err);
    doc = zjson_parse_file(path, &err);
    if (!doc) {
        zdiag_error(d, path, 0, 0, "", err.msg[0] ? err.msg : "解析失败");
        return 0;
    }
    z_snprintf(schema, sizeof(schema), "%s/schemas/persona.schema.json", root_dir);
    if (z_file_exists(schema) && zschema_validate_file(schema, doc, path, d) < 0) {
        zjson_free(doc);
        return 0;
    }

    z_strlcpy(zp->preset, zjson_str(zjson_obj_get(doc, "preset"), "blueprint"), sizeof(zp->preset));
    if (!preset_find(&zp->lib, zp->preset)) {
        zdiag_error(d, path, 0, 0, "preset", "预设 id 不在 config/persona_presets.json 里");
        zjson_free(doc);
        return 0;
    }
    /* 先铺预设自带的 traits，再让 persona.json 里显式写的覆盖它 —— 这就是"预设+微调"。 */
    zpersona_apply_preset(zp, zp->preset);

    o = zjson_obj_get(doc, "traits");
    if (o) {
        for (k = 0; k < zp->lib.ntraits; ++k) {
            zjson *v = zjson_obj_get(o, zp->lib.traits[k].id);
            if (v) {
                int x = (int)zjson_int(v, zp->tv[k]);
                zp->tv[k] = (x < 1) ? 1 : (x > 5) ? 5 : x;
            }
        }
    }

    o = zjson_obj_get(doc, "address");
    if (o) {
        z_strlcpy(zp->nickname, zjson_str(zjson_obj_get(o, "nickname"), ""), sizeof(zp->nickname));
        z_strlcpy(zp->selfname, zjson_str(zjson_obj_get(o, "self"), "我"), sizeof(zp->selfname));
    }
    z_strlcpy(zp->custom, zjson_str(zjson_obj_get(doc, "custom"), ""), sizeof(zp->custom));

    arr = zjson_obj_get(doc, "taboo");
    n = zjson_count(arr);
    for (i = 0; i < n && zp->ntaboo < ZP_MAX_TABOO; ++i) {
        const char *s = zjson_str(zjson_at(arr, i), "");
        if (s[0]) z_strlcpy(zp->taboo[zp->ntaboo++], s, sizeof(zp->taboo[0]));
    }

    o = zjson_obj_get(doc, "meeting");
    if (o) {
        zp->meeting_on = zjson_bool(zjson_obj_get(o, "enabled"), 1);
        z_strlcpy(zp->m_user,     zjson_str(zjson_obj_get(o, "user_name"), ""), sizeof(zp->m_user));
        z_strlcpy(zp->m_where,    zjson_str(zjson_obj_get(o, "where"), ""),     sizeof(zp->m_where));
        z_strlcpy(zp->m_when,     zjson_str(zjson_obj_get(o, "when"), ""),      sizeof(zp->m_when));
        z_strlcpy(zp->m_how,      zjson_str(zjson_obj_get(o, "how"), ""),       sizeof(zp->m_how));
        z_strlcpy(zp->m_relation, zjson_str(zjson_obj_get(o, "relation"), ""),  sizeof(zp->m_relation));
    }

    o = zjson_obj_get(doc, "story");
    arr = o ? zjson_obj_get(o, "tiers") : NULL;
    n = zjson_count(arr);
    for (i = 0; i < n && zp->nstory < ZP_MAX_STORY; ++i) {
        zjson *it = zjson_at(arr, i);
        long t = zjson_int(zjson_obj_get(it, "tier"), (long)i);
        if (t < 0 || t >= ZP_MAX_STORY) continue;
        z_strlcpy(zp->story_name[t], zjson_str(zjson_obj_get(it, "name"), ""),
                  sizeof(zp->story_name[0]));
        z_strlcpy(zp->story[t], zjson_str(zjson_obj_get(it, "brief"), ""), sizeof(zp->story[0]));
        if ((int)t + 1 > zp->nstory) zp->nstory = (int)t + 1;
    }

    zjson_free(doc);
    return 1;
}

/* ------------------------------------------------------------------ 合成 */

size_t zpersona_compose(const zpersona *zp, int tier, char *out, size_t cap)
{
    size_t len = 0;
    const zp_preset *p;
    int k, nwrote;

    if (!out || cap == 0) return 0;
    out[0] = '\0';

    /* ① 蓝本。名字用 character.json 的 name（中文名），不是目录 id ——
       提示词里出现 "xiaoxun" 会把模型带向英文语境，它还可能真的这么自称。 */
    line_add(out, cap, &len, "你现在扮演「%s」，是对方桌面上的伙伴。",
             zp->name[0] ? zp->name : zp->character);
    line_add(out, cap, &len, "回答要口语、简短，像在说话而不是写文章；不要用 Markdown 排版。");
    if (zp->blueprint[0]) line_add(out, cap, &len, "角色原设：%s", zp->blueprint);

    /* ② 预设风格 */
    p = preset_find(&zp->lib, zp->preset);
    if (p && strcmp(p->id, "blueprint") != 0 && p->style[0])
        line_add(out, cap, &len, "性格基调（%s）：%s", p->name, p->style);

    /* ② 微调：只写偏离中间值的维度 */
    nwrote = 0;
    for (k = 0; k < zp->lib.ntraits; ++k) {
        const zp_trait *t = &zp->lib.traits[k];
        char phrase[96];
        if (!trait_phrase(t, zp->tv[k], phrase, sizeof(phrase))) continue;
        if (!nwrote) { line_add(out, cap, &len, "说话风格："); nwrote = 1; }
        line_add(out, cap, &len, "  - %s：%s", t->name, phrase);
    }

    /* 称呼 */
    if (zp->nickname[0]) line_add(out, cap, &len, "你称呼对方为「%s」。", zp->nickname);
    if (zp->selfname[0] && strcmp(zp->selfname, "我") != 0)
        line_add(out, cap, &len, "你自称「%s」。", zp->selfname);

    /* 相遇设定 */
    if (zp->meeting_on &&
        (zp->m_user[0] || zp->m_where[0] || zp->m_when[0] || zp->m_how[0] || zp->m_relation[0])) {
        line_add(out, cap, &len, "你们怎么认识的：");
        if (zp->m_user[0])     line_add(out, cap, &len, "  - 对方叫%s", zp->m_user);
        if (zp->m_when[0])     line_add(out, cap, &len, "  - 时间：%s", zp->m_when);
        if (zp->m_where[0])    line_add(out, cap, &len, "  - 地点：%s", zp->m_where);
        if (zp->m_how[0])      line_add(out, cap, &len, "  - 经过：%s", zp->m_how);
        if (zp->m_relation[0]) line_add(out, cap, &len, "  - 现在的关系：%s", zp->m_relation);
        line_add(out, cap, &len, "  （这段是你们共同的记忆，可以自然提起，但不要逐字复述。）");
    }

    /* 当前好感档的剧情 —— 只给这一档，后面的不剧透 */
    if (tier >= 0 && tier < zp->nstory && zp->story[tier][0]) {
        line_add(out, cap, &len, "当前关系阶段：%s —— %s",
                 zp->story_name[tier][0] ? zp->story_name[tier] : "", zp->story[tier]);
        line_add(out, cap, &len, "不要表现得比这个阶段更亲密，也不要提到还没发生的事。");
    }

    /* 禁忌 */
    if (zp->ntaboo > 0) {
        line_add(out, cap, &len, "不要谈：");
        for (k = 0; k < zp->ntaboo; ++k) line_add(out, cap, &len, "  - %s", zp->taboo[k]);
    }

    /* ③ 自由文本，最后、最高优先级 */
    if (zp->custom[0]) line_add(out, cap, &len, "补充设定（优先级最高）：%s", zp->custom);

    return len;
}

int zpersona_meeting_todo(const zpersona *zp)
{
    int todo = 0;
    if (!zp->meeting_on) return 0;
    if (!zp->m_user[0])     todo++;
    if (!zp->m_where[0])    todo++;
    if (!zp->m_how[0])      todo++;
    if (!zp->m_relation[0]) todo++;
    return todo;
}

/* ------------------------------------------------------------------ 写入 */

int zpersona_apply_preset(zpersona *zp, const char *preset_id)
{
    const zp_preset *p = preset_find(&zp->lib, preset_id);
    int k;
    if (!p) return 0;
    z_strlcpy(zp->preset, p->id, sizeof(zp->preset));
    if (p->has_traits)
        for (k = 0; k < zp->lib.ntraits; ++k) zp->tv[k] = p->traits[k];
    return 1;
}

int zpersona_set(zpersona *zp, const char *key, const char *value)
{
    int idx;

    if (!key || !value) return 0;

    if (strcmp(key, "preset") == 0)   return zpersona_apply_preset(zp, value);
    if (strcmp(key, "nickname") == 0) { z_strlcpy(zp->nickname, value, sizeof(zp->nickname)); return 1; }
    if (strcmp(key, "selfname") == 0) { z_strlcpy(zp->selfname, value, sizeof(zp->selfname)); return 1; }
    if (strcmp(key, "custom") == 0)   { z_strlcpy(zp->custom,   value, sizeof(zp->custom));   return 1; }

    if (strncmp(key, "trait.", 6) == 0) {
        int v;
        idx = trait_index(&zp->lib, key + 6);
        if (idx < 0) return 0;
        v = atoi(value);
        if (v < 1 || v > 5) return 0;
        zp->tv[idx] = v;
        return 1;
    }

    if (strcmp(key, "taboo.add") == 0) {
        if (!value[0] || zp->ntaboo >= ZP_MAX_TABOO) return 0;
        z_strlcpy(zp->taboo[zp->ntaboo++], value, sizeof(zp->taboo[0]));
        return 1;
    }
    if (strcmp(key, "taboo.clear") == 0) { zp->ntaboo = 0; return 1; }

    if (strcmp(key, "meeting.enabled") == 0)  { zp->meeting_on = (value[0] == '1'); return 1; }
    if (strcmp(key, "meeting.user") == 0)     { z_strlcpy(zp->m_user, value, sizeof(zp->m_user)); return 1; }
    if (strcmp(key, "meeting.where") == 0)    { z_strlcpy(zp->m_where, value, sizeof(zp->m_where)); return 1; }
    if (strcmp(key, "meeting.when") == 0)     { z_strlcpy(zp->m_when, value, sizeof(zp->m_when)); return 1; }
    if (strcmp(key, "meeting.how") == 0)      { z_strlcpy(zp->m_how, value, sizeof(zp->m_how)); return 1; }
    if (strcmp(key, "meeting.relation") == 0) { z_strlcpy(zp->m_relation, value, sizeof(zp->m_relation)); return 1; }

    return 0;   /* 不在白名单 —— 拒绝。对话侧改不了任何别的字段。 */
}

/* 写一个 "key": "escaped-value" */
static void wr_str(FILE *f, const char *key, const char *val, const char *tail)
{
    char esc[2048];
    zjson_escape(val, esc, sizeof(esc));
    fprintf(f, "\"%s\": \"%s\"%s", key, esc, tail);
}

int zpersona_save(const zpersona *zp, const char *root_dir)
{
    char path[1024], tmp[1100];
    FILE *f;
    int k;

    z_snprintf(path, sizeof(path), "%s/characters/%s/persona.json", root_dir, zp->character);
    z_snprintf(tmp, sizeof(tmp), "%s.tmp", path);

    f = fopen(tmp, "wb");
    if (!f) return 0;

    fprintf(f, "{\n  \"schema_version\": \"1.0\",\n  ");
    wr_str(f, "character", zp->character, ",\n  ");
    wr_str(f, "preset", zp->preset, ",\n");

    fprintf(f, "  \"traits\": {");
    for (k = 0; k < zp->lib.ntraits; ++k)
        fprintf(f, "%s\n    \"%s\": %d", k ? "," : "", zp->lib.traits[k].id, zp->tv[k]);
    fprintf(f, "\n  },\n");

    fprintf(f, "  \"address\": {\n    ");
    wr_str(f, "nickname", zp->nickname, ",\n    ");
    wr_str(f, "self", zp->selfname, "\n  },\n  ");

    wr_str(f, "custom", zp->custom, ",\n");

    fprintf(f, "  \"taboo\": [");
    for (k = 0; k < zp->ntaboo; ++k) {
        char esc[256];
        zjson_escape(zp->taboo[k], esc, sizeof(esc));
        fprintf(f, "%s\"%s\"", k ? ", " : "", esc);
    }
    fprintf(f, "],\n");

    fprintf(f, "  \"meeting\": {\n    \"enabled\": %s,\n    ", zp->meeting_on ? "true" : "false");
    wr_str(f, "user_name", zp->m_user, ",\n    ");
    wr_str(f, "where", zp->m_where, ",\n    ");
    wr_str(f, "when", zp->m_when, ",\n    ");
    wr_str(f, "how", zp->m_how, ",\n    ");
    wr_str(f, "relation", zp->m_relation, "\n  },\n");

    fprintf(f, "  \"story\": {\n    \"tiers\": [");
    for (k = 0; k < zp->nstory; ++k) {
        char en[128], eb[512];
        zjson_escape(zp->story_name[k], en, sizeof(en));
        zjson_escape(zp->story[k], eb, sizeof(eb));
        fprintf(f, "%s\n      {\"tier\": %d, \"name\": \"%s\", \"brief\": \"%s\"}",
                k ? "," : "", k, en, eb);
    }
    fprintf(f, "\n    ]\n  }\n}\n");

    if (fclose(f) != 0) return 0;
    if (rename(tmp, path) != 0) { remove(tmp); return 0; }   /* 原子替换，改坏了不会半截文件 */
    return 1;
}
