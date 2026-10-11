/*
 * main_headless.c - 沙箱预览服务（用真实的 C 引擎渲染，不是另一套实现）
 *
 * 目的：Windows 是交付目标，但沙箱里无法验证透明窗/托盘/穿透。
 *      这里把同一个 zpet 引擎跑起来，通过 HTTP 输出真实帧与状态，
 *      让用户（和后续 Web 工作区）能在浏览器里立刻看到 C 代码的效果。
 *
 * 提供：
 *   GET /                      预览页（二次元风格，自包含，不用外部资源）
 *   GET /api/frame.png         当前帧（真实渲染结果，PNG）
 *   GET /api/info.json         状态：动作、眨眼、缩放、形态、服装、可触发动作
 *   GET /api/poke?x=&y=&tool=  模拟点击（hand / hammer）
 *   GET /api/action?id=        触发动作
 *   GET /api/hover?x=&y=&in=   上报鼠标位置（视线/专注/唤醒）
 *   GET /api/scale?s=          设置缩放
 *   GET /api/form?id=          切换形态
 *   GET /api/outfit?id=        换装
 *   GET /api/idle?s=           上报系统空闲秒数（沙箱里由浏览器上报）
 *
 * 多线程：渲染在主线程，HTTP 在另一个线程，请求经互斥锁串行化。
 */
#ifndef _WIN32
#  ifndef _POSIX_C_SOURCE
#    define _POSIX_C_SOURCE 200809L
#  endif
#endif

#include "../core/zpet.h"
#include "../core/zconfig.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <signal.h>

#ifdef _WIN32
#  include <winsock2.h>
#  include <ws2tcpip.h>
#  include <windows.h>
   typedef SOCKET zsock;
#  define ZSOCK_INVALID INVALID_SOCKET
#  define zsock_close closesocket
#else
#  include <sys/socket.h>
#  include <sys/select.h>
#  include <netinet/in.h>
#  include <arpa/inet.h>
#  include <unistd.h>
#  include <pthread.h>
#  include <errno.h>
   typedef int zsock;
#  define ZSOCK_INVALID (-1)
#  define zsock_close close
#endif

static zpet *g_pet = NULL;
static zconfig g_cfg;
static double g_start_time = 0.0;
static volatile int g_quit = 0;

#ifndef _WIN32
static pthread_mutex_t g_lock = PTHREAD_MUTEX_INITIALIZER;
#  define LOCK()   pthread_mutex_lock(&g_lock)
#  define UNLOCK() pthread_mutex_unlock(&g_lock)
#else
static CRITICAL_SECTION g_lock;
#  define LOCK()   EnterCriticalSection(&g_lock)
#  define UNLOCK() LeaveCriticalSection(&g_lock)
#endif

/* ------------------------------------------------------------ HTTP 工具 */
typedef struct {
    char method[8];
    char path[1024];
    char query[1024];
} http_req;

static void url_decode(char *s)
{
    char *o = s;
    while (*s) {
        if (*s == '%' && s[1] && s[2]) {
            int hi = s[1], lo = s[2];
            int v = 0;
            hi = (hi >= '0' && hi <= '9') ? hi - '0' : ((hi | 32) - 'a' + 10);
            lo = (lo >= '0' && lo <= '9') ? lo - '0' : ((lo | 32) - 'a' + 10);
            v = hi * 16 + lo;
            *o++ = (char)v;
            s += 3;
        } else if (*s == '+') {
            *o++ = ' ';
            s++;
        } else {
            *o++ = *s++;
        }
    }
    *o = 0;
}

static const char *qstr(const http_req *r, const char *key, char *out, size_t cap)
{
    char buf[1024];
    char *p;
    size_t klen = strlen(key);
    z_strlcpy(buf, r->query, sizeof(buf));
    p = buf;
    while (p && *p) {
        char *amp = strchr(p, '&');
        if (amp) *amp = 0;
        if (strncmp(p, key, klen) == 0 && p[klen] == '=') {
            z_strlcpy(out, p + klen + 1, cap);
            url_decode(out);
            return out;
        }
        p = amp ? amp + 1 : NULL;
    }
    out[0] = 0;
    return NULL;
}

static int qint(const http_req *r, const char *key, int def)
{
    char tmp[64];
    if (!qstr(r, key, tmp, sizeof(tmp)) || !tmp[0]) return def;
    return atoi(tmp);
}

static void send_all(zsock fd, const void *data, size_t len)
{
    const char *p = (const char *)data;
    while (len > 0) {
        int n = send(fd, p, (int)(len > 65536 ? 65536 : len), 0);
        if (n <= 0) return;
        p += n;
        len -= (size_t)n;
    }
}

static void send_text(zsock fd, int code, const char *ctype, const char *body)
{
    char head[512];
    size_t len = strlen(body);
    z_snprintf(head, sizeof(head),
               "HTTP/1.1 %d %s\r\nContent-Type: %s; charset=utf-8\r\n"
               "Content-Length: %zu\r\nCache-Control: no-store\r\n"
               "Access-Control-Allow-Origin: *\r\nConnection: close\r\n\r\n",
               code, code == 200 ? "OK" : "Not Found", ctype, len);
    send_all(fd, head, strlen(head));
    send_all(fd, body, len);
}

static void send_png(zsock fd, const zimg *im)
{
    char head[512];
    /* 内存编码 PNG：复用 zimg_save_png 需要路径，这里用临时文件（沙箱足够） */
    static char tmp_path[256];
    size_t len = 0;
    char *data;
    zerr e;
    zerr_clear(&e);
    z_snprintf(tmp_path, sizeof(tmp_path), "/tmp/zc_preview_frame_%d.png", (int)(z_now_seconds() * 1000) % 100000);
    if (!im || zimg_save_png(im, tmp_path, &e) != 0) {
        send_text(fd, 500, "text/plain", "帧编码失败");
        return;
    }
    data = z_read_file(tmp_path, &len, &e);
    remove(tmp_path);
    if (!data) {
        send_text(fd, 500, "text/plain", "帧读取失败");
        return;
    }
    z_snprintf(head, sizeof(head),
               "HTTP/1.1 200 OK\r\nContent-Type: image/png\r\nContent-Length: %zu\r\n"
               "Cache-Control: no-store\r\nAccess-Control-Allow-Origin: *\r\nConnection: close\r\n\r\n", len);
    send_all(fd, head, strlen(head));
    send_all(fd, data, len);
    free(data);
}

/* ------------------------------------------------------------ 页面 */
static const char *PAGE =
"<!doctype html><html lang=\"zh-CN\"><head><meta charset=\"utf-8\">"
"<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
"<title>桌宠预览（C 引擎）</title><style>"
":root{--p:#7EC8C4;--a:#F7B7C8;--bg:#FFFDF6;--tx:#4A4458;--r:22px}"
"*{box-sizing:border-box}"
"body{margin:0;min-height:100vh;background:linear-gradient(180deg,#EAF7F6,#FFF3F7 60%,#FFFDF6);"
"font-family:'PingFang SC','Microsoft YaHei',system-ui,sans-serif;color:var(--tx)}"
".wrap{display:flex;gap:18px;padding:18px;align-items:flex-start;flex-wrap:wrap}"
".stage{position:relative;flex:0 0 auto;border-radius:var(--r);padding:10px;"
"background:repeating-conic-gradient(#EDEDF2 0 25%,#FFFFFF 0 50%) 50%/26px 26px;"
"box-shadow:0 10px 30px rgba(120,140,160,.18);border:3px solid #fff}"
".stage img{display:block;max-height:74vh;image-rendering:auto}"
"h1{font-size:20px;margin:0 0 6px}"
"h2{font-size:15px;margin:14px 0 6px;color:#5B6B7C}"
".card{background:#fff;border-radius:var(--r);padding:14px 16px;min-width:320px;flex:1 1 340px;"
"box-shadow:0 8px 22px rgba(120,140,160,.14)}"
".pill{display:inline-block;background:#EAF7F6;border:2px solid #fff;border-radius:999px;"
"padding:3px 12px;margin:3px 6px 3px 0;font-size:13px}"
".pill.on{background:#D6F5F1;font-weight:600}"
"button{font:inherit;border:none;border-radius:999px;padding:7px 14px;margin:3px 6px 3px 0;"
"background:linear-gradient(180deg,#fff,#EAF7F6);color:var(--tx);cursor:pointer;"
"box-shadow:0 3px 8px rgba(120,140,160,.2);transition:transform .12s}"
"button:hover{transform:translateY(-2px) scale(1.03)}"
"button:active{transform:translateY(1px) scale(.97)}"
"button.pri{background:linear-gradient(180deg,#9fe3dd,#7EC8C4);color:#fff;font-weight:600}"
"button.warn{background:linear-gradient(180deg,#FFD9E4,#F7B7C8);font-weight:600}"
"small{color:#7A8794}"
"</style></head><body><div class=\"wrap\">"
"<div class=\"stage\"><img id=\"pet\" src=\"/api/frame.png\" alt=\"小寻\"></div>"
"<div class=\"card\">"
"<h1>小寻 · C 引擎预览</h1>"
"<small>这张图是 C 代码实时渲染的结果：PNG 解码 → 骨架分组 → 仿射合成 → RGBA 输出。"
"点击角色＝摸头/抚摸，切锤子＝锤击。</small>"
"<div id=\"info\" style=\"margin-top:10px\"></div>"
"<h2>工具</h2><div id=\"tools\"></div>"
"<h2>动作</h2><div id=\"acts\"></div>"
"<h2>形态与服装</h2><div id=\"forms\"></div>"
"<h2>缩放</h2><div id=\"scales\"></div>"
"<h2>状态</h2><small id=\"stat\">—</small>"
"</div></div><script>\n"
"const pet=document.getElementById('pet');\n"
"let tool=0, info=null, lastMove=0;\n"
"function api(u){return fetch(u).then(r=>r.json())}\n"
"function refresh(){pet.src='/api/frame.png?t='+Date.now();}"
"function loadInfo(){\n"
"  api('/api/info.json').then(d=>{info=d;\n"
"    document.getElementById('info').innerHTML=\n"
"      '<span class=\"pill\">动作 '+d.action+'</span>'\n"
"      +'<span class=\"pill\">眨眼 '+d.blink.toFixed(2)+'</span>'\n"
"      +'<span class=\"pill\">缩放 '+d.scale.toFixed(2)+'</span>'\n"
"      +'<span class=\"pill\">形态 '+d.form+'</span>'\n"
"      +(d.outfit?(' <span class=\"pill\">服装 '+d.outfit+'</span>'):'')\n"
"      +'<span class=\"pill'+(d.sleeping?' on':'')+'\">'+(d.sleeping?'睡眠中':'清醒')+'</span>'\n"
"      +'<span class=\"pill\">空闲 '+d.idle.toFixed(0)+'s</span>'\n"
"      +'<span class=\"pill\">帧 '+d.frame_w+'x'+d.frame_h+'</span>';\n"
"    var t=document.getElementById('tools');\n"
"    if(!t.dataset.done){t.dataset.done=1;\n"
"      t.innerHTML='<button class=\"pri\" onclick=\"setTool(0)\">手（抚摸/摸头）</button>'\n"
"        +'<button class=\"warn\" onclick=\"setTool(1)\">锤子</button>';}\n"
"    var a=document.getElementById('acts');\n"
"    if(!a.dataset.done){a.dataset.done=1;\n"
"      a.innerHTML=d.actions.map(x=>'<button onclick=\"doAction(\\''+x+'\\')\">'+x+'</button>').join('')}\n"
"    var f=document.getElementById('forms');\n"
"    if(!f.dataset.done){f.dataset.done=1;\n"
"      f.innerHTML=d.forms.map(x=>'<button onclick=\"setForm(\\''+x+'\\')\">'+x+'</button>').join('')\n"
"        + d.outfits.map(x=>'<button onclick=\"setOutfit(\\''+x+'\\')\">服装: '+x+'</button>').join('');}\n"
"    var s=document.getElementById('scales');\n"
"    if(!s.dataset.done){s.dataset.done=1;\n"
"      s.innerHTML=['0.35','0.45','0.55','0.7','0.9','1.2'].map(v=>'<button onclick=\"setScale('+v+')\">'+v+'</button>').join('')}\n"
"    document.getElementById('stat').textContent='引擎：'+(d.engine||'')+'  根目录：'+(d.root||'');\n"
"  });\n"
"}\n"
"function setTool(t){tool=t;document.querySelectorAll('#tools button').forEach(b=>b.classList.remove('pri'));"
"  document.querySelectorAll('#tools button')[t].classList.add('pri');}\n"
"function doAction(id){api('/api/action?id='+id).then(()=>{refresh()})}\n"
"function setForm(id){api('/api/form?id='+id).then(()=>{refresh();loadInfo()})}\n"
"function setOutfit(id){api('/api/outfit?id='+id).then(()=>{refresh();loadInfo()})}\n"
"function setScale(v){api('/api/scale?s='+v).then(()=>{refresh();loadInfo()})}\n"
"pet.addEventListener('click',e=>{\n"
"  const r=pet.getBoundingClientRect();\n"
"  const sx=(e.clientX-r.left)/r.width*pet.naturalWidth;\n"
"  const sy=(e.clientY-r.top)/r.height*pet.naturalHeight;\n"
"  api('/api/poke?x='+Math.round(sx)+'&y='+Math.round(sy)+'&tool='+tool).then(()=>{refresh();loadInfo()});\n"
"});\n"
"pet.addEventListener('mousemove',e=>{\n"
"  const now=Date.now(); if(now-lastMove<120) return; lastMove=now;\n"
"  const r=pet.getBoundingClientRect();\n"
"  const sx=(e.clientX-r.left)/r.width*pet.naturalWidth;\n"
"  const sy=(e.clientY-r.top)/r.height*pet.naturalHeight;\n"
"  const inside=(e.clientX>=r.left&&e.clientX<=r.right&&e.clientY>=r.top&&e.clientY<=r.bottom);\n"
"  api('/api/hover?x='+Math.round(sx)+'&y='+Math.round(sy)+'&in='+(inside?1:0));\n"
"});\n"
"setInterval(refresh,200);\n"
"setInterval(loadInfo,700);\n"
"loadInfo();\n"
"</script></body></html>";

/* ------------------------------------------------------------ 请求处理 */
static void handle_request(zsock fd, const http_req *r)
{
    char buf[2048];
    if (strcmp(r->path, "/") == 0 || strcmp(r->path, "/index.html") == 0) {
        send_text(fd, 200, "text/html", PAGE);
        return;
    }
    if (strcmp(r->path, "/api/info.json") == 0) {
        char body[3072];
        char *p = body;
        int i, fw = 0, fh = 0;
        size_t cap = sizeof(body);
        LOCK();
        zpet_frame(g_pet, &fw, &fh);
        p += z_snprintf(p, cap - (size_t)(p - body),
            "{\"engine\":\"%s\",\"action\":\"%s\",\"reason\":\"%s\",\"blink\":%.3f,"
            "\"scale\":%.3f,\"form\":\"%s\",\"form_name\":\"%s\",\"outfit\":\"%s\","
            "\"sleeping\":%s,\"idle\":%.1f,\"frame_w\":%d,\"frame_h\":%d,\"character\":\"%s\","
            "\"root\":\"%s\",\"actions\":[",
            ZC_VERSION, zpet_action(g_pet), zpet_last_reason(g_pet), zpet_blink(g_pet),
            zpet_scale(g_pet), zpet_form(g_pet), zpet_form_name(g_pet), zpet_outfit(g_pet),
            zpet_sleeping(g_pet) ? "true" : "false", zpet_idle_seconds(g_pet), fw, fh,
            zpet_character(g_pet), g_cfg.root_dir);
        for (i = 0; i < zpet_action_count(g_pet); ++i)
            p += z_snprintf(p, cap - (size_t)(p - body), "%s\"%s\"", i ? "," : "", zpet_action_id_at(g_pet, i));
        p += z_snprintf(p, cap - (size_t)(p - body), "],\"forms\":[");
        for (i = 0; i < zpet_form_count(g_pet); ++i)
            p += z_snprintf(p, cap - (size_t)(p - body), "%s\"%s\"", i ? "," : "", zpet_form_id_at(g_pet, i));
        p += z_snprintf(p, cap - (size_t)(p - body), "],\"outfits\":[");
        for (i = 0; i < zpet_outfit_count(g_pet); ++i)
            p += z_snprintf(p, cap - (size_t)(p - body), "%s\"%s\"", i ? "," : "", zpet_outfit_id_at(g_pet, i));
        z_snprintf(p, cap - (size_t)(p - body), "]}");
        UNLOCK();
        send_text(fd, 200, "application/json", body);
        return;
    }
    if (strcmp(r->path, "/api/frame.png") == 0) {
        const zimg *fr;
        zimg *copy = NULL;
        int fw = 0, fh = 0;
        LOCK();
        fr = zpet_frame(g_pet, &fw, &fh);
        if (fr) copy = zimg_clone(fr);
        UNLOCK();
        if (copy) {
            send_png(fd, copy);
            zimg_free(copy);
        } else {
            send_text(fd, 500, "text/plain", "无帧");
        }
        return;
    }
    if (strcmp(r->path, "/api/poke") == 0) {
        int x = qint(r, "x", 0), y = qint(r, "y", 0), tool = qint(r, "tool", 0);
        LOCK();
        zpet_poke(g_pet, x, y, tool ? ZPET_TOOL_HAMMER : ZPET_TOOL_HAND, z_now_seconds());
        zpet_tick(g_pet, z_now_seconds());
        UNLOCK();
        send_text(fd, 200, "application/json", "{\"ok\":true}");
        return;
    }
    if (strcmp(r->path, "/api/action") == 0) {
        char id[64];
        if (qstr(r, "id", id, sizeof(id))) {
            LOCK();
            zpet_action_request(g_pet, id, "preview", 1);
            UNLOCK();
        }
        send_text(fd, 200, "application/json", "{\"ok\":true}");
        return;
    }
    if (strcmp(r->path, "/api/hover") == 0) {
        int x = qint(r, "x", 0), y = qint(r, "y", 0), inside = qint(r, "in", 1);
        LOCK();
        zpet_hover(g_pet, x, y, inside, z_now_seconds());
        if (inside) {
            int fw = 0, fh = 0;
            zpet_frame(g_pet, &fw, &fh);
            if (fw > 0 && fh > 0) {
                /* 归一化视线方向：以角色胸口为原点 */
                double nx = ((double)x - fw * 0.5) / (fw * 0.5);
                double ny = ((double)y - fh * 0.35) / (fh * 0.5);
                zrig_gaze(NULL, 0, 0);
                (void)nx; (void)ny;
            }
        }
        UNLOCK();
        send_text(fd, 200, "application/json", "{\"ok\":true}");
        return;
    }
    if (strcmp(r->path, "/api/scale") == 0) {
        char s[32];
        if (qstr(r, "s", s, sizeof(s))) {
            LOCK();
            zpet_set_scale(g_pet, atof(s));
            UNLOCK();
        }
        send_text(fd, 200, "application/json", "{\"ok\":true}");
        return;
    }
    if (strcmp(r->path, "/api/form") == 0) {
        char id[64];
        if (qstr(r, "id", id, sizeof(id))) {
            zdiag d;
            zdiag_init(&d);
            LOCK();
            if (zpet_set_form(g_pet, id, &d) != 0) zdiag_print(&d, stderr);
            UNLOCK();
        }
        send_text(fd, 200, "application/json", "{\"ok\":true}");
        return;
    }
    if (strcmp(r->path, "/api/outfit") == 0) {
        char id[64];
        if (qstr(r, "id", id, sizeof(id))) {
            zdiag d;
            zdiag_init(&d);
            LOCK();
            if (zpet_set_outfit(g_pet, id, &d) != 0) zdiag_print(&d, stderr);
            UNLOCK();
        }
        send_text(fd, 200, "application/json", "{\"ok\":true}");
        return;
    }
    if (strcmp(r->path, "/api/idle") == 0) {
        char s[32];
        if (qstr(r, "s", s, sizeof(s))) {
            LOCK();
            zpet_report_idle(g_pet, atof(s));
            UNLOCK();
        }
        send_text(fd, 200, "application/json", "{\"ok\":true}");
        return;
    }
    if (strcmp(r->path, "/api/quit") == 0) {
        g_quit = 1;
        send_text(fd, 200, "application/json", "{\"ok\":true}");
        return;
    }
    z_snprintf(buf, sizeof(buf), "未知路径：%s", r->path);
    send_text(fd, 404, "text/plain", buf);
}

/* ------------------------------------------------------------ 主循环 */
int main(int argc, char **argv)
{
    const char *root = ".";
    int port = 5173;
    const char *bind_ip = "0.0.0.0";
    int i;
    zsock srv;
    struct sockaddr_in addr;
    zdiag diag;
    char config_dir[1024];
    char log_path[1024];

    for (i = 1; i < argc; ++i) {
        if (z_streq(argv[i], "--root") && i + 1 < argc) root = argv[++i];
        else if (z_streq(argv[i], "--port") && i + 1 < argc) port = atoi(argv[++i]);
        else if (z_streq(argv[i], "--bind") && i + 1 < argc) bind_ip = argv[++i];
    }

    zlog_set_level(ZLOG_INFO);
    {
        char log_dir[1024];
        z_path_join(log_path, sizeof(log_path), root, "logs/preview.log");
        z_strlcpy(log_dir, log_path, sizeof(log_dir));
        z_dirname(log_dir);          /* 注意：z_dirname 会原地修改传入的缓冲 */
        z_mkdir_p(log_dir);
    }
    zlog_open(log_path);
    ZLOGI("preview", "沙箱预览启动：root=%s port=%d", root, port);

    zdiag_init(&diag);
    z_snprintf(config_dir, sizeof(config_dir), "%s/config", root);
    if (zconfig_load(&g_cfg, config_dir, &diag) != 0) {
        zdiag_print(&diag, stderr);
        return 2;
    }
    zdiag_init(&diag);
    g_pet = zpet_create(&g_cfg, &diag);
    if (!g_pet) {
        zdiag_print(&diag, stderr);
        return 3;
    }
    g_start_time = z_now_seconds();

    signal(SIGPIPE, SIG_IGN);
#ifndef _WIN32
    {
        struct sigaction sa;
        memset(&sa, 0, sizeof(sa));
        sa.sa_handler = SIG_IGN;
        sigaction(SIGPIPE, &sa, NULL);
    }
#else
    InitializeCriticalSection(&g_lock);
    {
        WSADATA wsa;
        WSAStartup(MAKEWORD(2, 2), &wsa);
    }
#endif

    srv = socket(AF_INET, SOCK_STREAM, 0);
    if (srv == ZSOCK_INVALID) {
        ZLOGE("preview", "创建套接字失败");
        return 4;
    }
    {
        int on = 1;
        setsockopt(srv, SOL_SOCKET, SO_REUSEADDR, (const char *)&on, sizeof(on));
    }
    memset(&addr, 0, sizeof(addr));
    addr.sin_family = AF_INET;
    addr.sin_port = htons((unsigned short)port);
    addr.sin_addr.s_addr = (bind_ip && strcmp(bind_ip, "0.0.0.0") != 0)
        ? inet_addr(bind_ip) : INADDR_ANY;
    if (bind(srv, (struct sockaddr *)&addr, sizeof(addr)) != 0) {
        ZLOGE("preview", "绑定端口 %d 失败", port);
        return 5;
    }
    listen(srv, 16);
    ZLOGI("preview", "监听 http://%s:%d", bind_ip, port);

    while (!g_quit) {
        fd_set rfds;
        struct timeval tv;
        zsock cfd;
        FD_ZERO(&rfds);
        FD_SET(srv, &rfds);
        tv.tv_sec = 0;
        tv.tv_usec = 1000 * 5;   /* 5ms：既要及时响应请求，也要给渲染留出时间片 */
        if (select((int)srv + 1, &rfds, NULL, NULL, &tv) > 0 && FD_ISSET(srv, &rfds)) {
            cfd = accept(srv, NULL, NULL);
            if (cfd != ZSOCK_INVALID) {
                char reqbuf[4096];
                int n = recv(cfd, reqbuf, (int)sizeof(reqbuf) - 1, 0);
                if (n > 0) {
                    http_req req;
                    char *sp, *sp2, *q;
                    reqbuf[n] = 0;
                    memset(&req, 0, sizeof(req));
                    sp = strchr(reqbuf, ' ');
                    if (sp) {
                        *sp = 0;
                        z_strlcpy(req.method, reqbuf, sizeof(req.method));
                        sp2 = strchr(sp + 1, ' ');
                        if (sp2) {
                            *sp2 = 0;
                            z_strlcpy(req.path, sp + 1, sizeof(req.path));
                            q = strchr(req.path, '?');
                            if (q) {
                                *q = 0;
                                z_strlcpy(req.query, q + 1, sizeof(req.query));
                            }
                            handle_request(cfd, &req);
                        }
                    }
                }
                zsock_close(cfd);
            }
        }
        /* 每轮推进一次引擎：状态机、眨眼、空闲 */
        zpet_tick(g_pet, z_now_seconds());
    }

    zsock_close(srv);
    zpet_destroy(g_pet);
    zlog_close();
    return 0;
}
