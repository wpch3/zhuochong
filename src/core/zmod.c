/*
 * zmod.c - 热加载实现（POSIX dlopen，Windows LoadLibrary）
 */
#include "zmod.h"
#include "zjson.h"
#include <string.h>
#include <stdlib.h>

#ifndef _WIN32
#include <dlfcn.h>
#include <dirent.h>
#include <unistd.h>
#else
#include <windows.h>
#endif

static const zmod_api dummy_api = {
    .name = "dummy",
    .version = ZMOD_ABI_VERSION,
    .init = NULL, .tick = NULL, .on_event = NULL, .shutdown = NULL
};
const zmod_api* zmod_get_api_default(void) { return &dummy_api; }

void zmod_mgr_init(zmod_mgr *m, const char *root_dir, zbus *bus) {
    if (!m) return;
    memset(m, 0, sizeof(*m));
    m->bus = bus;
    if (root_dir) {
        z_strlcpy(m->root_dir, root_dir, sizeof(m->root_dir));
        z_path_join(m->mod_dir, sizeof(m->mod_dir), root_dir, "config/modules");
    } else {
        z_strlcpy(m->mod_dir, "config/modules", sizeof(m->mod_dir));
    }
}

static void close_handle(void *h) {
    if (!h) return;
#ifndef _WIN32
    dlclose(h);
#else
    FreeLibrary((HMODULE)h);
#endif
}

void zmod_mgr_shutdown(zmod_mgr *m) {
    int i;
    if (!m) return;
    for (i = 0; i < m->count; ++i) {
        zmod_ctx *c = &m->mods[i];
        if (c->api && c->api->shutdown) c->api->shutdown(c);
        close_handle(c->handle);
    }
    m->count = 0;
}

/* 读单份 mod json，填 ctx（不 dlopen） */
static int parse_mod_json(const char *path, zmod_ctx *out, zdiag *diag, const char *root_dir) {
    char *buf = NULL; size_t len = 0; zerr err; zjson *j = NULL;
    const zjson *jv;
    memset(out, 0, sizeof(*out));
    buf = z_read_file(path, &len, &err);
    if (!buf) {
        zdiag_error(diag, path, 0,0,"","读模块配置失败：%s", err.msg);
        return -1;
    }
    zerr_clear(&err);
    j = zjson_parse(buf, path, &err);
    free(buf);
    if (!j) {
        zdiag_error(diag, path, err.line, err.col, "", "解析失败：%s", err.msg);
        return -1;
    }
    jv = zjson_obj_get(j, "id");
    if (!jv || jv->type != ZJSON_STR || !jv->sval || !jv->sval[0]) {
        zdiag_error(diag, path, j->line,0,"id","缺少 id 字符串");
        zjson_free(j); return -1;
    }
    z_strlcpy(out->id, jv->sval, sizeof(out->id));
    jv = zjson_obj_get(j, "path");
    if (jv && jv->type == ZJSON_STR) {
        char resolved[ZMOD_PATH_MAX];
        z_resolve_path(resolved, sizeof(resolved), root_dir ? root_dir : ".", jv->sval);
        z_strlcpy(out->path, resolved, sizeof(out->path));
    }
    jv = zjson_obj_get(j, "enabled");
    out->enabled = (jv && jv->type == ZJSON_BOOL) ? (jv->bval != 0) : 1;
    out->root_dir = root_dir; /* 借用外部寿命，mgr 保证 */
    zjson_free(j);
    if (!out->path[0]) {
        zdiag_error(diag, path, 0,0,"path","缺少 path（.so/.dll 路径）");
        return -1;
    }
    return 0;
}

static int open_mod(zmod_ctx *c, zdiag *diag) {
    void *h = NULL;
    const zmod_api *api = NULL;
    const char *path = c->path;
    if (!c->enabled) return 0; /* 禁用：不加载，但记录条目 */
#ifndef _WIN32
    {
        typedef const zmod_api* (*getter_fn)(void);
        getter_fn getter = NULL;
        h = dlopen(path, RTLD_NOW);
        if (!h) {
            zdiag_error(diag, path,0,0,"dlopen", "dlopen 失败：%s", dlerror());
            return -1;
        }
        getter = (getter_fn)dlsym(h, "zmod_get_api");
        if (!getter) {
            zdiag_error(diag, path,0,0,"dlsym", "找不到符号 zmod_get_api（是否未导出？）");
            dlclose(h); return -1;
        }
        api = getter();
        if (!api) {
            zdiag_error(diag, path,0,0,"dlsym", "zmod_get_api 返回空");
            dlclose(h); return -1;
        }
    }
#else
    {
        HMODULE hm = LoadLibraryA(path);
        if (!hm) {
            zdiag_error(diag, path,0,0,"LoadLibrary", "LoadLibrary 失败：%lu", GetLastError());
            return -1;
        }
        h = (void*)hm;
        api = (const zmod_api*)GetProcAddress(hm, "zmod_get_api");
        if (!api) {
            zdiag_error(diag, path,0,0,"GetProcAddress", "找不到 zmod_get_api");
            FreeLibrary(hm); return -1;
        }
        /* Windows: dlsym 得到的是函数指针，需调用 */
        if (api) {
            typedef const zmod_api* (*getter)(void);
            getter g = (getter)api;
            api = g();
        }
    }
#endif
    if (api->version != ZMOD_ABI_VERSION) {
        zdiag_error(diag, path,0,0,"version","ABI 版本不匹配：模块 %d vs 引擎 %d", api->version, ZMOD_ABI_VERSION);
        close_handle(h); return -1;
    }
    c->handle = h;
    c->api = api;
    if (api->init) {
        int rc = api->init(c, diag);
        if (rc != 0) {
            zdiag_error(diag, path,0,0,"init", "模块 init 返回 %d", rc);
            close_handle(h); c->handle=NULL; c->api=NULL; return -1;
        }
    }
    return 0;
}

int zmod_scan(zmod_mgr *m, zdiag *diag) {
    char dirpath[1024];
    if (!m) return -1;
    z_strlcpy(dirpath, m->mod_dir, sizeof(dirpath));
    if (!z_is_dir(dirpath)) {
        /* 无目录＝零模组，不算错（裸引擎可跑） */
        return 0;
    }
#ifndef _WIN32
    {
        DIR *d = opendir(dirpath);
        struct dirent *ent;
        if (!d) {
            zdiag_error(diag, dirpath,0,0,"","打开模块目录失败");
            return -1;
        }
        while ((ent = readdir(d)) != NULL) {
            char full[1024];
            if (ent->d_name[0]=='.') continue;
            if (!z_endswith(ent->d_name, ".json")) continue;
            z_path_join(full, sizeof(full), dirpath, ent->d_name);
            if (m->count >= ZMOD_MAX) {
                zdiag_error(diag, full,0,0,"","模块数超上限 %d", ZMOD_MAX);
                closedir(d); return -1;
            }
            zmod_ctx tmp;
            if (parse_mod_json(full, &tmp, diag, m->root_dir) != 0) { closedir(d); return -1; }
            tmp.bus = m->bus;
            tmp.root_dir = m->root_dir;
            if (open_mod(&tmp, diag) != 0) { closedir(d); return -1; }
            if (!tmp.enabled) continue; /* 禁用：不占位，仅作声明 */
            zmod_ctx *c = &m->mods[m->count];
            *c = tmp;
            m->count++;
        }
        closedir(d);
    }
#else
    /* Windows 目录遍历简化：FindFirstFile */
    {
        char pat[1024];
        WIN32_FIND_DATAA fd; HANDLE h;
        z_path_join(pat, sizeof(pat), dirpath, "*.json");
        h = FindFirstFileA(pat, &fd);
        if (h != INVALID_HANDLE_VALUE) {
            do {
                char full[1024];
                if (fd.cFileName[0]=='.') continue;
                z_path_join(full, sizeof(full), dirpath, fd.cFileName);
                if (m->count >= ZMOD_MAX) {
                    zdiag_error(diag, full,0,0,"","模块数超上限 %d", ZMOD_MAX);
                    FindClose(h); return -1;
                }
                zmod_ctx tmp2;
                if (parse_mod_json(full, &tmp2, diag, m->root_dir) != 0) { FindClose(h); return -1; }
                tmp2.bus = m->bus;
                tmp2.root_dir = m->root_dir;
                if (open_mod(&tmp2, diag) != 0) { FindClose(h); return -1; }
                if (!tmp2.enabled) continue;
                zmod_ctx *c = &m->mods[m->count];
                *c = tmp2;
                m->count++;
            } while (FindNextFileA(h, &fd));
            FindClose(h);
        }
    }
#endif
    return 0;
}

int zmod_load(zmod_mgr *m, const char *mod_json_path, zdiag *diag) {
    zmod_ctx tmp;
    if (!m || !mod_json_path) return -1;
    if (m->count >= ZMOD_MAX) {
        zdiag_error(diag, mod_json_path,0,0,"","模块数超上限 %d", ZMOD_MAX);
        return -1;
    }
    if (parse_mod_json(mod_json_path, &tmp, diag, m->root_dir) != 0) return -1;
    tmp.bus = m->bus;
    tmp.root_dir = m->root_dir;
    if (open_mod(&tmp, diag) != 0) return -1;
    m->mods[m->count++] = tmp;
    return 0;
}

int zmod_unload(zmod_mgr *m, const char *id) {
    int i, f = -1;
    if (!m || !id) return -1;
    for (i=0;i<m->count;++i) if (z_streq(m->mods[i].id, id)) { f=i; break; }
    if (f<0) return -1;
    {
        zmod_ctx *c=&m->mods[f];
        if (c->api && c->api->shutdown) c->api->shutdown(c);
        close_handle(c->handle);
    }
    for (i=f;i<m->count-1;++i) m->mods[i]=m->mods[i+1];
    m->count--;
    return 0;
}

int zmod_reload(zmod_mgr *m, const char *id, zdiag *diag) {
    int i, f=-1; char path[ZMOD_PATH_MAX]={0};
    if (!m || !id) return -1;
    for (i=0;i<m->count;++i) if (z_streq(m->mods[i].id, id)) { f=i; break; }
    if (f<0) return -1;
    z_strlcpy(path, m->mods[f].path, sizeof(path));
    zmod_unload(m, id);
    /* 重新从已知的 json 路径加载：id 对应 config/modules/<id>.json */
    {
        char jpath[1024];
        z_path_join(jpath, sizeof(jpath), m->mod_dir, id);
        if (!z_endswith(jpath, ".json")) z_strlcpy(jpath+strlen(jpath), ".json", sizeof(jpath)-strlen(jpath));
        if (!z_file_exists(jpath)) {
            /* 若 json 已被删，直接用旧 path 搭一个临时 json */
            zmod_ctx tmp; memset(&tmp,0,sizeof(tmp));
            z_strlcpy(tmp.id, id, sizeof(tmp.id));
            z_strlcpy(tmp.path, path, sizeof(tmp.path));
            tmp.enabled=1; tmp.bus=m->bus; tmp.root_dir=m->root_dir;
            if (open_mod(&tmp, diag)!=0) return -1;
            if (m->count>=ZMOD_MAX) { close_handle(tmp.handle); return -1; }
            m->mods[m->count++]=tmp;
            return 0;
        }
        return zmod_load(m, jpath, diag);
    }
}

void zmod_tick(zmod_mgr *m, double now) {
    int i;
    if (!m) return;
    for (i=0;i<m->count;++i) {
        zmod_ctx *c=&m->mods[i];
        if (!c->enabled || !c->api || !c->api->tick) continue;
        c->api->tick(c, now);
        c->last_tick = now;
    }
}

int zmod_dispatch(zmod_mgr *m, const zbus_event *ev) {
    int i, n=0;
    if (!m || !ev) return 0;
    for (i=0;i<m->count;++i) {
        zmod_ctx *c=&m->mods[i];
        if (!c->enabled || !c->api || !c->api->on_event) continue;
        if (c->api->on_event(c, ev)==0) n++;
    }
    return n;
}

int zmod_count(const zmod_mgr *m) { return m? m->count : 0; }
const char* zmod_id_at(const zmod_mgr *m, int i) {
    if (!m || i<0 || i>=m->count) return NULL;
    return m->mods[i].id;
}
int zmod_enabled(const zmod_mgr *m, const char *id) {
    int i;
    if (!m || !id) return 0;
    for (i=0;i<m->count;++i) if (z_streq(m->mods[i].id, id)) return m->mods[i].enabled ? 1:0;
    return 0;
}
zmod_ctx* zmod_find(zmod_mgr *m, const char *id) {
    int i;
    if (!m || !id) return NULL;
    for (i=0;i<m->count;++i) if (z_streq(m->mods[i].id, id)) return &m->mods[i];
    return NULL;
}
