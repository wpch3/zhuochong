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
 *   GET /api/pause?on=&t=      冻结/恢复引擎时钟（冻结后连续两帧完全相同，便于抓图比对；t 指定冻结到哪一秒）
 *   GET /api/step?n=&dt=       冻结状态下按固定步长空跑 n 帧，让物理与 lag 走到位（A/B 对照必备）
 *   GET /api/ambient?on=       环境摆动总开关（关掉参数才真的等于你设的值，A/B 对照必备）
 *   GET /api/pose?group=&id=   互斥部件组切档（≈ pose3.json；id=none 整组关掉）
 *   GET /api/params.json       命名参数表（≈ Live2D ParamXxx）与当前值
 *   GET /api/param?id=&v=      直接写一个参数（reset=1 回默认；all=1 全部复位）
 *   GET /api/expression?id=    叠一个表情（off=1 取消），表情和动作是两条轨
 *   GET /api/form?id=          切换形态
 *   GET /api/outfit?id=        换装
 *   GET /api/idle?s=           上报系统空闲秒数（沙箱里由浏览器上报）
 *   GET /api/gateway.json      网关：每种能力实际会路由到谁、账本、密钥是否就位
 *
 * 多线程：渲染在主线程，HTTP 在另一个线程，请求经互斥锁串行化。
 */
#ifndef _WIN32
#  ifndef _POSIX_C_SOURCE
#    define _POSIX_C_SOURCE 200809L
#  endif
#endif

#include "../core/zpet.h"
#include "../core/zgateway.h"
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

/* 冻结时钟（/api/pause）：暂停后所有 tick 都用同一个时间戳，
   于是连续两帧**逐字节相同**——抓对照图、做哈希断言时不会被呼吸/眨眼/物理搅乱。 */
static int    g_frozen = 0;
static double g_freeze_t = 0.0;
static double pet_now(void)
{
    return g_frozen ? g_freeze_t : z_now_seconds();
}

static zpet *g_pet = NULL;
/* 网关（G51）：进程启动时读一次路由表。读不到不影响桌宠本体跑，
   只是 /api/gateway.json 会如实说"没加载"。 */
static zgateway g_gw;
static int      g_gw_ok = 0;
/* UI 与静态资源目录：界面文件放 web/，媒体（配音/素材）走 /media/，
 * 这样改界面完全不用动 C 代码（对应“全部可自定义”的原则）。 */
static char g_root[1024] = ".";
static char g_frames_dir[1024] = "web";
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
    size_t len = 0;
    uint8_t *data;
    /* 直接在内存里编码。以前这里是"写 /tmp/zc_frame_*.png → 读回来 → remove"，
       每帧三次文件系统往返，还得给文件名拼进程号+序号防并发撞车；
       换成 zimg_encode_png 之后那堆问题整个消失了。 */
    if (!im) {
        send_text(fd, 500, "text/plain", "帧编码失败");
        return;
    }
    data = zimg_encode_png(im, &len);
    if (!data) {
        send_text(fd, 500, "text/plain", "帧编码失败");
        return;
    }
    z_snprintf(head, sizeof(head),
               "HTTP/1.1 200 OK\r\nContent-Type: image/png\r\nContent-Length: %zu\r\n"
               "Cache-Control: no-store\r\nAccess-Control-Allow-Origin: *\r\nConnection: close\r\n\r\n", len);
    send_all(fd, head, strlen(head));
    send_all(fd, data, len);
    free(data);
}

/* ------------------------------------------------------ 静态文件服务 */

static const char *ctype_for(const char *path)
{
    const char *dot = strrchr(path, '.');
    if (!dot) return "application/octet-stream";
    if (z_streq(dot, ".html")) return "text/html";
    if (z_streq(dot, ".css")) return "text/css";
    if (z_streq(dot, ".js")) return "application/javascript";
    if (z_streq(dot, ".json")) return "application/json";
    if (z_streq(dot, ".png")) return "image/png";
    if (z_streq(dot, ".jpg") || z_streq(dot, ".jpeg")) return "image/jpeg";
    if (z_streq(dot, ".mp3")) return "audio/mpeg";
    if (z_streq(dot, ".wav")) return "audio/wav";
    if (z_streq(dot, ".ogg")) return "audio/ogg";
    return "application/octet-stream";
}

/* 相对路径安全检查：拒绝 .. / 绝对路径 / 反斜杠 / 冒号（避免越界读文件） */
static int safe_relpath(const char *rel)
{
    if (!rel || !rel[0]) return 0;
    if (rel[0] == '/' || rel[0] == '\\') return 0;
    if (strstr(rel, "..")) return 0;
    if (strchr(rel, ':') || strchr(rel, '\\')) return 0;
    return 1;
}

static int send_file(zsock fd, const char *path)
{
    zerr e;
    size_t len = 0;
    char *data;
    char head[512];
    zerr_clear(&e);
    data = z_read_file(path, &len, &e);
    if (!data || len == 0) {
        free(data);
        return -1;
    }
    z_snprintf(head, sizeof(head),
               "HTTP/1.1 200 OK\r\nContent-Type: %s\r\nContent-Length: %zu\r\n"
               "Cache-Control: no-store\r\nAccess-Control-Allow-Origin: *\r\nConnection: close\r\n\r\n",
               ctype_for(path), len);
    send_all(fd, head, strlen(head));
    send_all(fd, data, len);
    free(data);
    return 0;
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
"<div id=\"speech\" style=\"margin-top:10px;min-height:1.6em;font-size:15px\"></div>"
"<div id=\"mood\" style=\"font-size:12px;opacity:.7\"></div>"
"<div id=\"info\" style=\"margin-top:6px\"></div>"
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
"function loadSpeech(){api('/api/speech.json').then(d=>{\n"
"  document.getElementById('speech').textContent=d.line?('「'+d.line+'」'):'';\n"
"  document.getElementById('mood').textContent=d.mood?('情绪：'+d.mood):'';});}\n"
"setInterval(loadSpeech,500);\n"
"</script></body></html>";

/* ------------------------------------------------------------ 请求处理 */
static void handle_request(zsock fd, const http_req *r)
{
    char buf[2048];
    if (strcmp(r->path, "/") == 0 || strcmp(r->path, "/index.html") == 0) {
        char p[1024];
        z_path_join(p, sizeof(p), g_frames_dir, "index.html");
        if (send_file(fd, p) == 0) return;      /* 优先用 web/ 里的界面 */
        send_text(fd, 200, "text/html", PAGE);  /* 缺失时退回内置调试页 */
        return;
    }
    /* 媒体文件：/media/<仓库内相对路径>（只允许 web/ 与 characters/ 下的音频图片） */
    if (strncmp(r->path, "/media/", 7) == 0) {
        char rel[1024], p[1024];
        z_strlcpy(rel, r->path + 7, sizeof(rel));
        if (!safe_relpath(rel) ||
            (strncmp(rel, "characters/", 11) != 0 && strncmp(rel, "web/", 4) != 0 &&
             strncmp(rel, "voices/", 7) != 0 && strncmp(rel, "logs/", 5) != 0)) {
            send_text(fd, 403, "text/plain", "路径不允许");
            return;
        }
        z_path_join(p, sizeof(p), g_root, rel);
        if (send_file(fd, p) != 0) send_text(fd, 404, "text/plain", "文件不存在");
        return;
    }
    /* 其余非 /api/ 的 GET：当作 web/ 下的静态资源（css/js/图片/清单） */
    if (strncmp(r->path, "/api/", 5) != 0 && r->path[0] == '/') {
        char rel[1024], p[1024];
        z_strlcpy(rel, r->path + 1, sizeof(rel));
        if (safe_relpath(rel)) {
            z_path_join(p, sizeof(p), g_frames_dir, rel);
            if (send_file(fd, p) == 0) return;
        }
    }
    if (strcmp(r->path, "/api/route") == 0) {
        /* 双路由沙盘（DC18）：给一条假请求，看它会落到本地还是云端、为什么。
           这是纯决策，不发任何网络请求 —— 所以在没有密钥、没有显卡的机器上
           也能把"敏感数据绝不上云"这类规则验到底。 */
        char body[1024], cap_s[64], task_hit[32];
        zgw_req req;
        zgw_status why = ZGW_NO_SUCH_CAP;
        zgw_reason reason = ZGW_R_DEFAULT_LOCAL;
        const zgw_route *rt;
        double share;

        if (!qstr(r, "cap", cap_s, sizeof(cap_s)) || !cap_s[0])
            z_strlcpy(cap_s, "chat.completion", sizeof(cap_s));
        task_hit[0] = 0;
        memset(&req, 0, sizeof(req));
        req.sensitive      = qint(r, "sensitive", 0) ? 1 : 0;
        req.tokens_est     = (long)qint(r, "tokens", 0);
        req.local_load_pct = qint(r, "load", -1);
        req.cloud_down     = qint(r, "cloud_down", 0) ? 1 : 0;
        /* heavy 可以显式传；没传就按文本自动判（q=问题原文）。
           自动判的结果要连"凭哪个词判的"一起报出去，否则界面只能说"它觉得重"。 */
        {
            char qtext[512];
            const char *hit = "";
            if (qstr(r, "q", qtext, sizeof(qtext)) && qtext[0]) {
                req.task = zgw_classify(qtext, &hit);
                z_strlcpy(task_hit, hit, sizeof(task_hit));
            }
            if (r->query[0] && strstr(r->query, "heavy="))
                req.task = qint(r, "heavy", 0) ? ZGW_TASK_HEAVY : ZGW_TASK_SIMPLE;
        }

        LOCK();
        rt = g_gw_ok ? zgw_route_for(&g_gw, cap_s, &req, &why, &reason) : NULL;
        share = zgw_local_share(&g_gw);
        z_snprintf(body, sizeof(body),
            "{\"cap\":\"%s\",\"ok\":%s,\"provider\":\"%s\",\"model\":\"%s\",\"local\":%s,"
            "\"reason\":\"%s\",\"blocked_sensitive\":%s,"
            "\"task\":\"%s\",\"task_hit\":\"%s\","
            "\"rules\":{\"tokens_cloud\":%ld,\"local_busy_pct\":%d,\"sensitive_local_only\":%s},"
            "\"stats\":{\"local\":%ld,\"cloud\":%ld,\"local_share\":%.4f,"
            "\"logged\":%ld,\"log_failed\":%ld}}",
            cap_s, rt ? "true" : "false",
            rt ? rt->provider : "", rt ? rt->model : "",
            (rt && rt->local) ? "true" : "false",
            zgw_reason_name(reason),
            (why == ZGW_SENSITIVE_NO_LOCAL) ? "true" : "false",
            req.task == ZGW_TASK_HEAVY ? "heavy" : "simple", task_hit,
            g_gw.rules.tokens_cloud, g_gw.rules.local_busy_pct,
            g_gw.rules.sensitive_local_only ? "true" : "false",
            g_gw.picks_local, g_gw.picks_cloud, share,
            g_gw.log_written, g_gw.log_failed);
        UNLOCK();
        send_text(fd, 200, "application/json", body);
        return;
    }

    if (strcmp(r->path, "/api/gateway.json") == 0) {
        /* 界面要回答用户三个问题：这功能能不能用？会用谁？花了多少钱？
           所以这里导出的是"路由的结果"，不是路由表原样——原样在 platform.json 里有。 */
        char body[8192];
        char *p = body;
        size_t cap = sizeof(body);
        int i, shown = 0;
        static const char *const WATCH[] = {
            "chat.completion", "chat.stream", "image.generate", "video.generate",
            "code.generate", "model3d.generate", "tts.speak", "stt.listen",
            "embed.text", "vision.describe", "web.search", "memory.recall", NULL
        };
        LOCK();
        p += z_snprintf(p, cap - (size_t)(p - body),
            "{\"loaded\":%s,\"strategy\":\"%s\",\"fallback\":%s,\"routes\":%d,"
            "\"ledger\":{\"spent\":%.6f,\"held\":%.6f,\"tokens_in\":%ld,\"tokens_out\":%ld,"
            "\"calls\":%ld,\"failed\":%ld},\"caps\":[",
            g_gw_ok ? "true" : "false", g_gw_ok ? g_gw.strategy : "",
            (g_gw_ok && g_gw.fallback) ? "true" : "false", g_gw_ok ? g_gw.nroutes : 0,
            g_gw.spent_total, zgw_held_amount(&g_gw), g_gw.tokens_in_total,
            g_gw.tokens_out_total, g_gw.calls_total, g_gw.failed_total);
        for (i = 0; WATCH[i]; ++i) {
            zgw_status why = ZGW_NO_SUCH_CAP;
            const zgw_route *rt = g_gw_ok ? zgw_pick(&g_gw, WATCH[i], 0, &why) : NULL;
            const char *state = rt ? "ready"
                              : (why == ZGW_ALL_DISABLED ? "disabled" : "missing");
            /* 失败原因要分开报：disabled 是"去设置里打开"，missing 是"还没接入"。
               混成一个 false 的话界面只能说"不可用"，用户不知道该干什么。 */
            p += z_snprintf(p, cap - (size_t)(p - body),
                "%s{\"cap\":\"%s\",\"state\":\"%s\",\"provider\":\"%s\",\"model\":\"%s\","
                "\"local\":%s,\"free\":%s,\"candidates\":%d}",
                shown++ ? "," : "", WATCH[i], state,
                rt ? rt->provider : "", rt ? rt->model : "",
                (rt && rt->local) ? "true" : "false",
                (rt && (rt->local || rt->is_free)) ? "true" : "false",
                g_gw_ok ? zgw_candidate_count(&g_gw, WATCH[i]) : 0);
        }
        p += z_snprintf(p, cap - (size_t)(p - body), "]}");
        UNLOCK();
        send_text(fd, 200, "application/json", body);
        return;
    }

    if (strcmp(r->path, "/api/info.json") == 0) {
        char body[4096];
        char *p = body;
        int i, fw = 0, fh = 0;
        size_t cap = sizeof(body);
        const char *mood;
        LOCK();
        zpet_frame(g_pet, &fw, &fh);
        /* 界面的状态片要显示真实情绪与好感，所以这里把 zpet 的内部状态一并导出；
           mood 可能为空（还没表达过情绪），统一给 "calm" 以免界面显示破折号。 */
        mood = zpet_last_mood(g_pet);
        if (!mood || !*mood) mood = "calm";
        p += z_snprintf(p, cap - (size_t)(p - body),
            "{\"engine\":\"%s\",\"action\":\"%s\",\"reason\":\"%s\",\"blink\":%.3f,"
            "\"scale\":%.3f,\"form\":\"%s\",\"form_name\":\"%s\",\"outfit\":\"%s\","
            "\"mood\":\"%s\",\"affection\":%d,\"tier\":%d,\"tier_name\":\"%s\","
            "\"sleeping\":%s,\"idle\":%.1f,\"frame_w\":%d,\"frame_h\":%d,"
            "\"canvas_w\":%d,\"canvas_h\":%d,\"character\":\"%s\","
            "\"root\":\"%s\",\"blink_manual\":%.3f,\"actions\":[",
            ZC_VERSION, zpet_action(g_pet), zpet_last_reason(g_pet), zpet_blink(g_pet),
            zpet_scale(g_pet), zpet_form(g_pet), zpet_form_name(g_pet), zpet_outfit(g_pet),
            mood, zpet_affection(g_pet), zpet_affection_tier(g_pet), zpet_affection_tier_name(g_pet),
            zpet_sleeping(g_pet) ? "true" : "false", zpet_idle_seconds(g_pet), fw, fh,
            zpet_canvas_w(g_pet), zpet_canvas_h(g_pet),
            zpet_character(g_pet), g_cfg.root_dir, zpet_blink_manual(g_pet));
        for (i = 0; i < zpet_action_count(g_pet); ++i)
            p += z_snprintf(p, cap - (size_t)(p - body), "%s\"%s\"", i ? "," : "", zpet_action_id_at(g_pet, i));
        /* forms / form_names 的语义是**能切过去的形态**，所以只报 ready 的。
           规划中但还没做的形态走下面的 form_roadmap，界面上灰显。
           两者分开是为了不破坏既有调用方：谁拿 forms 去渲染切换按钮都不会切到空形态。 */
        p += z_snprintf(p, cap - (size_t)(p - body), "],\"forms\":[");
        {
            int shown = 0;
            for (i = 0; i < zpet_form_count(g_pet); ++i) {
                if (!z_streq(zpet_form_status_at(g_pet, i), "ready")) continue;
                p += z_snprintf(p, cap - (size_t)(p - body), "%s\"%s\"",
                                shown++ ? "," : "", zpet_form_id_at(g_pet, i));
            }
            /* 界面按钮要显示中文名（"少女"）而不是形态 id（"teen"），所以 id 与名字成对导出。 */
            p += z_snprintf(p, cap - (size_t)(p - body), "],\"form_names\":[");
            shown = 0;
            for (i = 0; i < zpet_form_count(g_pet); ++i) {
                if (!z_streq(zpet_form_status_at(g_pet, i), "ready")) continue;
                p += z_snprintf(p, cap - (size_t)(p - body), "%s\"%s\"",
                                shown++ ? "," : "", zpet_form_name_at(g_pet, i));
            }
            /* 形态路线图：ready + planned 全报，界面据此画出「做好的」和「还没做的」。
               没有这张表，用户看不出这个角色将来还会有萝莉/御姐/Q 版。 */
            p += z_snprintf(p, cap - (size_t)(p - body), "],\"form_roadmap\":[");
            for (i = 0; i < zpet_form_count(g_pet); ++i)
                p += z_snprintf(p, cap - (size_t)(p - body),
                                "%s{\"id\":\"%s\",\"name\":\"%s\",\"status\":\"%s\",\"note\":\"%s\"}",
                                i ? "," : "", zpet_form_id_at(g_pet, i),
                                zpet_form_name_at(g_pet, i), zpet_form_status_at(g_pet, i),
                                zpet_form_note_at(g_pet, i));
        }
        p += z_snprintf(p, cap - (size_t)(p - body), "],\"outfits\":[");
        for (i = 0; i < zpet_outfit_count(g_pet); ++i)
            p += z_snprintf(p, cap - (size_t)(p - body), "%s\"%s\"", i ? "," : "", zpet_outfit_id_at(g_pet, i));
        p += z_snprintf(p, cap - (size_t)(p - body), "],\"outfit_names\":[");
        for (i = 0; i < zpet_outfit_count(g_pet); ++i)
            p += z_snprintf(p, cap - (size_t)(p - body), "%s\"%s\"", i ? "," : "", zpet_outfit_name_at(g_pet, i));
        /* 表情层：当前表情 + 可选表情表（测试台的表情按钮按它生成） */
        p += z_snprintf(p, cap - (size_t)(p - body), "],\"expression\":\"%s\",\"expressions\":[",
                        zpet_expression(g_pet) ? zpet_expression(g_pet) : "");
        for (i = 0; i < zpet_expression_count(g_pet); ++i)
            p += z_snprintf(p, cap - (size_t)(p - body), "%s{\"id\":\"%s\",\"name\":\"%s\"}",
                            i ? "," : "", zpet_expression_id_at(g_pet, i),
                            zpet_expression_name_at(g_pet, i));
        /* Pose：互斥部件组 + 每组当前档位（测试台的差分按钮按它生成） */
        p += z_snprintf(p, cap - (size_t)(p - body), "],\"poses\":[");
        for (i = 0; i < zpet_pose_count(g_pet); ++i) {
            const char *gid = zpet_pose_id_at(g_pet, i);
            int k;
            p += z_snprintf(p, cap - (size_t)(p - body),
                            "%s{\"id\":\"%s\",\"current\":\"%s\",\"entries\":[",
                            i ? "," : "", gid, zpet_pose_current(g_pet, gid));
            for (k = 0; k < zpet_pose_entry_count(g_pet, gid); ++k)
                p += z_snprintf(p, cap - (size_t)(p - body), "%s\"%s\"",
                                k ? "," : "", zpet_pose_entry_id_at(g_pet, gid, k));
            p += z_snprintf(p, cap - (size_t)(p - body), "]}");
        }
        /* 交互区域表：UI 要知道有哪些区域、点下去触发什么、用什么光标。
           不报这张表前端就只能把 head/body/feet 写死，rig.json 一改区域就对不上。 */
        p += z_snprintf(p, cap - (size_t)(p - body), "],\"regions\":[");
        for (i = 0; i < zpet_region_count(g_pet); ++i) {
            int rc[4];
            if (!zpet_region_rect_at(g_pet, i, rc)) continue;
            p += z_snprintf(p, cap - (size_t)(p - body),
                            "%s{\"id\":\"%s\",\"action\":\"%s\",\"cursor\":\"%s\","
                            "\"rect\":[%d,%d,%d,%d]}",
                            i ? "," : "", zpet_region_id_at(g_pet, i),
                            zpet_region_action_at(g_pet, i),
                            zpet_region_cursor_at(g_pet, i),
                            rc[0], rc[1], rc[2], rc[3]);
        }
        /* 口型音素表 + 当前接管状态（测试台的口型按钮按它生成）。
           没有这张表，调试台只能把 A/I/U/E/O 硬编码进前端，rig 改了前端就对不上。 */
        p += z_snprintf(p, cap - (size_t)(p - body),
                        "],\"viseme\":\"%s\",\"viseme_weight\":%.3f,\"visemes\":[",
                        zpet_viseme_current(g_pet), zpet_viseme_weight(g_pet));
        for (i = 0; i < zpet_viseme_count(g_pet); ++i)
            p += z_snprintf(p, cap - (size_t)(p - body), "%s\"%s\"",
                            i ? "," : "", zpet_viseme_id(g_pet, i));
        /* 形变器当前量：摆链（头发/裙摆）的输出就落在这里。
           光看截图没法判断"裙摆是不是真的在荡"，这组数能直接读。 */
        p += z_snprintf(p, cap - (size_t)(p - body), "],\"deformers\":{");
        for (i = 0; i < zpet_deform_count(g_pet); ++i) {
            const char *did = zpet_deform_id_at(g_pet, i);
            p += z_snprintf(p, cap - (size_t)(p - body), "%s\"%s\":%.5f",
                            i ? "," : "", did ? did : "?",
                            zpet_deform_amount(g_pet, did));
        }
        /* 物理摆链各节点的输出。★ 和 deformers 分开给，是因为形变器的当前量
           是**物理 + 环境摆动（ambient）之和** —— 环境摆动不管身体动不动都一直
           在跑，拿形变器去断言"身体停住后摆链要收敛回零"永远不成立。
           要验摆链收敛，看的是这一组。 */
        p += z_snprintf(p, cap - (size_t)(p - body), "},\"physics\":{");
        for (i = 0; i < zpet_phys_count(g_pet); ++i) {
            const char *xid = zpet_phys_id_at(g_pet, i);
            p += z_snprintf(p, cap - (size_t)(p - body), "%s\"%s\":%.5f",
                            i ? "," : "", xid ? xid : "?",
                            zpet_phys_output(g_pet, xid));
        }
        /* 物理 2.0 的摆链（T47.2）。两组数：
             "<链>.<粒子>" = 这一节的**摆角（度）**，输入不动它也不为零 —— 这就是"活着"；
             "<链>#<第几条输出>" = 翻译成通道之后**真正写出去的值**（像素或形变量）。
           冒烟判据（静置 10 秒发梢仍有 ≥2px 自主摆动）量的就是后者。 */
        p += z_snprintf(p, cap - (size_t)(p - body), "},\"physics2\":{");
        {
            int first = 1, k, np, no;
            for (i = 0; i < zpet_phys2_count(g_pet); ++i) {
                const char *cid = zpet_phys2_id_at(g_pet, i);
                if (!cid) continue;
                np = zpet_phys2_particles(g_pet, cid);
                for (k = 1; k < np; ++k) {
                    p += z_snprintf(p, cap - (size_t)(p - body), "%s\"%s.%d\":%.5f",
                                    first ? "" : ",", cid, k,
                                    zpet_phys2_angle(g_pet, cid, k));
                    first = 0;
                }
                no = zpet_phys2_out_count(g_pet, cid);
                for (k = 0; k < no; ++k) {
                    p += z_snprintf(p, cap - (size_t)(p - body), "%s\"%s#%d\":%.5f",
                                    first ? "" : ",", cid, k,
                                    zpet_phys2_applied(g_pet, cid, k));
                    first = 0;
                }
            }
        }
        z_snprintf(p, cap - (size_t)(p - body), "}}");
        UNLOCK();
        send_text(fd, 200, "application/json", body);
        return;
    }
    if (strcmp(r->path, "/api/pose") == 0) {
        /* 互斥部件组切档：group=组 id，id=档位 id（none / 省略 = 整组关掉）。
           组或档位不存在返回 404 —— 差分写错名字必须当场看见。 */
        char group[64], id[64];
        int rc;
        if (!qstr(r, "group", group, sizeof(group))) {
            send_text(fd, 400, "application/json", "{\"ok\":false,\"error\":\"缺少 group\"}");
            return;
        }
        if (!qstr(r, "id", id, sizeof(id))) z_strlcpy(id, "none", sizeof(id));
        LOCK();
        rc = zpet_pose_set(g_pet, group, id);
        /* 冻结时钟时淡化走不动（dt 恒为 0），直接到位，否则切档像没反应 */
        if (g_frozen) zpet_pose_snap(g_pet);
        zpet_tick(g_pet, pet_now());
        UNLOCK();
        if (rc != 0) {
            char body2[192];
            z_snprintf(body2, sizeof(body2),
                       "{\"ok\":false,\"error\":\"没有这个互斥组或档位\","
                       "\"group\":\"%s\",\"id\":\"%s\"}", group, id);
            send_text(fd, 404, "application/json", body2);
        } else {
            char body2[192];
            z_snprintf(body2, sizeof(body2), "{\"ok\":true,\"group\":\"%s\",\"id\":\"%s\"}",
                       group, id);
            send_text(fd, 200, "application/json", body2);
        }
        return;
    }
    if (strcmp(r->path, "/api/frame.png") == 0) {
        const zimg *fr;
        zimg *copy = NULL;
        int fw = 0, fh = 0;
        /* ?s=50..100：按百分比缩小后再编码。浏览器会拉回原尺寸显示，
           画面略软但码率降到 1/4，远程预览能不能流畅全看这个。 */
        int spct = qint(r, "s", 100);
        if (spct < 25) spct = 25;
        if (spct > 100) spct = 100;
        LOCK();
        fr = zpet_frame(g_pet, &fw, &fh);
        if (fr) copy = zimg_clone(fr);
        UNLOCK();
        if (copy && spct < 100) {
            zimg *small = zimg_downscale(copy, copy->w * spct / 100, copy->h * spct / 100);
            if (small) { zimg_free(copy); copy = small; }
        }
        if (copy) {
            send_png(fd, copy);
            zimg_free(copy);
        } else {
            send_text(fd, 500, "text/plain", "无帧");
        }
        return;
    }
    if (strcmp(r->path, "/api/speech.json") == 0) {
        /* 832 而不是 640：seq/age 两个字段是 2026-10-15 补的（G105）。
           line 本身最长 256 字节，加上 mood/tier/lipsync 一圈，640 已经贴边了。 */
        char body[832];
        double now_s = pet_now();
        LOCK();
        z_snprintf(body, sizeof(body),
                   "{\"line\":\"%s\",\"mood\":\"%s\",\"affection\":%d,\"tier\":\"%s\","
                   "\"seq\":%u,\"age\":%.2f,"
                   "\"lipsync\":{\"active\":%s,\"id\":\"%s\",\"level\":%.3f,\"remain\":%.3f}}",
                   zpet_last_line(g_pet), zpet_last_mood(g_pet),
                   zpet_affection(g_pet), zpet_affection_tier_name(g_pet),
                   zpet_last_line_seq(g_pet), zpet_last_line_age(g_pet, now_s),
                   zpet_lipsync_active(g_pet) ? "true" : "false",
                   zpet_lipsync_id(g_pet), zpet_lipsync_level(g_pet),
                   zpet_lipsync_remain(g_pet));
        UNLOCK();
        send_text(fd, 200, "application/json", body);
        return;
    }
    if (strcmp(r->path, "/api/express") == 0) {
        char mood[32];
        if (qstr(r, "mood", mood, sizeof(mood))) {
            LOCK();
            zpet_express(g_pet, mood, pet_now());
            zpet_tick(g_pet, pet_now());
            UNLOCK();
        }
        send_text(fd, 200, "application/json", "{\"ok\":true}");
        return;
    }
    if (strcmp(r->path, "/api/call") == 0) {
        /* 沙箱模拟语音通话事件：kind=call_start|call_end|call_user_speaking|call_reply&text=&mood= */
        char kind[32], text[512], mood[32];
        if (qstr(r, "kind", kind, sizeof(kind))) {
            if (!qstr(r, "text", text, sizeof(text))) text[0] = 0;
            if (!qstr(r, "mood", mood, sizeof(mood))) mood[0] = 0;
            LOCK();
            zpet_call_event(g_pet, kind, text, mood, pet_now());
            zpet_tick(g_pet, pet_now());
            UNLOCK();
        }
        send_text(fd, 200, "application/json", "{\"ok\":true}");
        return;
    }
    if (strcmp(r->path, "/api/poke") == 0) {
        int x = qint(r, "x", 0), y = qint(r, "y", 0), tool = qint(r, "tool", 0);
        LOCK();
        zpet_poke(g_pet, x, y, tool ? ZPET_TOOL_HAMMER : ZPET_TOOL_HAND, pet_now());
        zpet_tick(g_pet, pet_now());
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
    if (strcmp(r->path, "/api/speak") == 0) {
        /* 口型同步：/api/speak?id=<包络名>（tools/make_lipsync.py 的产物），
           /api/speak?stop=1 立刻收嘴。包络播完引擎会自动收尾。 */
        char id[64], body[512];
        int rc = -1;
        if (qint(r, "stop", 0)) {
            LOCK();
            zpet_lipsync_stop(g_pet);
            UNLOCK();
            send_text(fd, 200, "application/json", "{\"ok\":true,\"stopped\":true}");
            return;
        }
        if (!qstr(r, "id", id, sizeof(id))) {
            send_text(fd, 400, "application/json",
                      "{\"ok\":false,\"error\":\"缺少 id（voice/lipsync/<id>.json）\"}");
            return;
        }
        LOCK();
        rc = zpet_lipsync_load(g_pet, id, pet_now());
        zpet_tick(g_pet, pet_now());
        z_snprintf(body, sizeof(body),
                   "{\"ok\":%s,\"id\":\"%s\",\"text\":\"%s\",\"remain\":%.3f}",
                   rc == 0 ? "true" : "false", zpet_lipsync_id(g_pet),
                   zpet_lipsync_text(g_pet), zpet_lipsync_remain(g_pet));
        UNLOCK();
        send_text(fd, rc == 0 ? 200 : 404, "application/json", body);
        return;
    }
    if (strcmp(r->path, "/api/hover") == 0) {
        int x = qint(r, "x", 0), y = qint(r, "y", 0), inside = qint(r, "in", 1);
        LOCK();
        /* 视线换算在 zpet_hover 里做（它知道上一帧多大），这里不要重复渲染 */
        zpet_hover(g_pet, x, y, inside, pet_now());
        UNLOCK();
        send_text(fd, 200, "application/json", "{\"ok\":true}");
        return;
    }
    if (strcmp(r->path, "/api/region") == 0) {
        /* 测试台要能回答"鼠标现在压在哪个互动区上"：给坐标，回区域 id/动作/光标。
           区域判定还带不透明像素命中（透明的角落不算），所以这里也能验出"点空了"。

           坐标系要说清楚：默认 `space=frame`（窗口内／帧缓冲坐标，前端鼠标位置就是它），
           `space=canvas` 时直接按 rig.json 的画布坐标算（info.json 的 rect 就是这套）。
           答复里回报 `space` 和换算后的 `cx/cy` —— 2026-10-15 之前这里的坐标系
           会跟着"渲染过没渲染过"偷偷切换，两种都回 200，谁都发现不了。 */
        char body[320], action[48], space[16];
        const char *cursor = "arrow";
        const char *id;
        int x = qint(r, "x", 0), y = qint(r, "y", 0);
        int cx = x, cy = y, is_canvas;
        action[0] = 0;
        space[0] = 0;
        qstr(r, "space", space, sizeof(space));
        is_canvas = (strcmp(space, "canvas") == 0);
        LOCK();
        id = zpet_region_ex(g_pet, x, y, is_canvas, action, sizeof(action),
                            &cursor, &cx, &cy);
        UNLOCK();
        z_snprintf(body, sizeof(body),
                   "{\"region\":\"%s\",\"action\":\"%s\",\"cursor\":\"%s\","
                   "\"x\":%d,\"y\":%d,\"space\":\"%s\",\"cx\":%d,\"cy\":%d}",
                   id ? id : "", action, cursor ? cursor : "arrow", x, y,
                   is_canvas ? "canvas" : "frame", cx, cy);
        send_text(fd, 200, "application/json", body);
        return;
    }
    if (strcmp(r->path, "/api/blink") == 0) {
        /* 测试台的眨眼滑条：v=0..1 按住，v=auto 交回自动眨眼 */
        /* on=0 关自动眨眼（常睁）、on=1 开；一个都没给就报 400 ——
           以前 `?on=0` 会被静默忽略还回 ok，"关眨眼"根本没生效（见 LESSONS 的"跳过即通过"）。 */
        char s[32];
        int got = 0;
        if (qstr(r, "v", s, sizeof(s))) {
            LOCK();
            zpet_set_blink(g_pet, (z_streq(s, "auto") || !*s) ? -1.0 : atof(s));
            UNLOCK();
            got = 1;
        }
        if (qstr(r, "on", s, sizeof(s))) {
            LOCK();
            zpet_set_blink_enabled(g_pet, atoi(s) != 0);
            UNLOCK();
            got = 1;
        }
        if (!got) {
            send_text(fd, 400, "application/json",
                      "{\"ok\":false,\"error\":\"要给 v=0..1|auto 或 on=0|1\"}");
            return;
        }
        {
            char body[128];
            LOCK();
            z_snprintf(body, sizeof(body),
                       "{\"ok\":true,\"blink\":%.3f,\"manual\":%.3f,\"auto\":%s}",
                       zpet_blink(g_pet), zpet_blink_manual(g_pet),
                       zpet_blink_enabled(g_pet) ? "true" : "false");
            UNLOCK();
            send_text(fd, 200, "application/json", body);
        }
        return;
    }
    if (strcmp(r->path, "/api/gaze") == 0) {
        /* 视线直控：x、y ∈ [-1,1]；off=1 收回视线 */
        char sx[32], sy[32];
        int off = qint(r, "off", 0);
        double nx = qstr(r, "x", sx, sizeof(sx)) ? atof(sx) : 0.0;
        double ny = qstr(r, "y", sy, sizeof(sy)) ? atof(sy) : 0.0;
        LOCK();
        zpet_set_gaze(g_pet, nx, ny, !off);
        UNLOCK();
        send_text(fd, 200, "application/json", "{\"ok\":true}");
        return;
    }
    if (strcmp(r->path, "/api/expression") == 0) {
        /* 表情层：叠在当前动作之上。off=1 取消；未知 id 返回 404 */
        char id[64];
        int rc;
        if (qint(r, "off", 0) || !qstr(r, "id", id, sizeof(id))) {
            LOCK();
            zpet_expression_set(g_pet, NULL);
            if (g_frozen) zpet_expression_snap(g_pet);
            UNLOCK();
            send_text(fd, 200, "application/json", "{\"ok\":true,\"expression\":\"\"}");
            return;
        }
        LOCK();
        rc = zpet_expression_set(g_pet, id);
        if (g_frozen) zpet_expression_snap(g_pet);  /* 冻结时钟时淡入走不动，直接到位 */
        UNLOCK();
        if (rc != 0) {
            char body[160];
            z_snprintf(body, sizeof(body),
                       "{\"ok\":false,\"error\":\"没有这个表情\",\"id\":\"%s\"}", id);
            send_text(fd, 404, "application/json", body);
        } else {
            char body[160];
            z_snprintf(body, sizeof(body), "{\"ok\":true,\"expression\":\"%s\"}", id);
            send_text(fd, 200, "application/json", body);
        }
        return;
    }
    if (strcmp(r->path, "/api/params.json") == 0) {
        /* 命名参数层：测试台据此自动长出一排滑条，加参数不用改前端 */
        char body[16384];
        size_t off = 0;
        int i, n;
        body[0] = 0;
        off += (size_t)z_snprintf(body + off, sizeof(body) - off, "{\"params\":[");
        LOCK();
        n = zpet_param_count(g_pet);
        for (i = 0; i < n; ++i) {
            zrig_param_desc d;
            if (zpet_param_info(g_pet, i, &d) != 0) continue;
            if (off + 320 >= sizeof(body)) break;
            off += (size_t)z_snprintf(body + off, sizeof(body) - off,
                "%s{\"id\":\"%s\",\"label\":\"%s\",\"min\":%.3f,\"max\":%.3f,"
                "\"default\":%.3f,\"value\":%.4f,\"expr\":%.4f,\"effective\":%.4f,"
                "\"builtin\":%s,\"binds\":%d}",
                i ? "," : "", d.id, d.label ? d.label : "", d.vmin, d.vmax,
                d.vdef, d.value, zpet_param_expr_value(g_pet, d.id),
                zpet_param_effective(g_pet, d.id),
                d.builtin ? "true" : "false", d.binds);
        }
        /* Live2D model3.json 的 Groups：口型写哪个参数、自动眨眼眨哪只眼 */
        off += (size_t)z_snprintf(body + off, sizeof(body) - off,
            "],\"groups\":{\"LipSync\":[\"%s\"],\"EyeBlink\":[",
            zpet_lipsync_param(g_pet));
        {
            int bt = zpet_blink_targets(g_pet);
            int first = 1;
            if (bt & 1) { off += (size_t)z_snprintf(body + off, sizeof(body) - off,
                                                    "\"ParamEyeLOpen\""); first = 0; }
            if (bt & 2) off += (size_t)z_snprintf(body + off, sizeof(body) - off,
                                                  "%s\"ParamEyeROpen\"", first ? "" : ",");
        }
        /* 口型音素表（母音識別方式）：测试台据此长出 A/I/U/E/O 按钮 */
        off += (size_t)z_snprintf(body + off, sizeof(body) - off, "]},\"visemes\":[");
        {
            int vi, vn = zpet_viseme_count(g_pet);
            for (vi = 0; vi < vn; ++vi) {
                const char *vid = zpet_viseme_id(g_pet, vi);
                if (!vid || off + 64 >= sizeof(body)) break;
                off += (size_t)z_snprintf(body + off, sizeof(body) - off,
                                          "%s\"%s\"", vi ? "," : "", vid);
            }
        }
        off += (size_t)z_snprintf(body + off, sizeof(body) - off,
                                  "],\"viseme\":{\"id\":\"%s\",\"weight\":%.3f},"
                                  "\"viseme_weight\":%.3f,\"expression\":\"%s\"",
                                  zpet_viseme_current(g_pet), zpet_viseme_weight(g_pet),
                                  zpet_viseme_mix(g_pet),
                                  zpet_expression(g_pet) ? zpet_expression(g_pet) : "");
        UNLOCK();
        z_snprintf(body + off, sizeof(body) - off, "}");
        send_text(fd, 200, "application/json", body);
        return;
    }
    if (strcmp(r->path, "/api/viseme") == 0) {
        /* 口型音素：v=A/I/U/E/O/N/SIL（off/- = 松口），w=0..1 是这一帧的音量。
           音素决定嘴形，w 决定张多大 —— 和真语音接上时 w 就是包络。 */
        char v[16], sw[32];
        double w = 1.0;
        int rc = 0;
        if (!qstr(r, "v", v, sizeof(v))) {
            send_text(fd, 400, "application/json", "{\"ok\":false,\"error\":\"缺少 v\"}");
            return;
        }
        if (qstr(r, "w", sw, sizeof(sw))) w = atof(sw);
        LOCK();
        if (strcmp(v, "off") == 0 || strcmp(v, "-") == 0) zpet_viseme_clear(g_pet);
        else rc = zpet_viseme_set(g_pet, v, w);
        if (g_frozen) zpet_viseme_snap(g_pet);   /* 冻结时钟时平滑走不动，直接到位 */
        zpet_tick(g_pet, pet_now());
        UNLOCK();
        if (rc != 0) {
            char body2[192];
            z_snprintf(body2, sizeof(body2),
                       "{\"ok\":false,\"error\":\"没有这个音素\",\"v\":\"%s\"}", v);
            send_text(fd, 404, "application/json", body2);
        } else {
            char body2[192];
            LOCK();
            z_snprintf(body2, sizeof(body2),
                       "{\"ok\":true,\"viseme\":\"%s\",\"weight\":%.3f,\"open\":%.4f,\"form\":%.4f}",
                       zpet_viseme_current(g_pet), zpet_viseme_weight(g_pet),
                       zpet_param_effective(g_pet, zpet_lipsync_param(g_pet)),
                       zpet_param_effective(g_pet, "ParamMouthForm"));
            UNLOCK();
            send_text(fd, 200, "application/json", body2);
        }
        return;
    }
    if (strcmp(r->path, "/api/param") == 0) {
        char id[64], sv[32];
        int rc = 0;
        if (qint(r, "all", 0)) {
            LOCK();
            zpet_param_reset_all(g_pet);
            UNLOCK();
            send_text(fd, 200, "application/json", "{\"ok\":true,\"reset\":\"all\"}");
            return;
        }
        if (!qstr(r, "id", id, sizeof(id))) {
            send_text(fd, 400, "application/json", "{\"ok\":false,\"error\":\"缺少 id\"}");
            return;
        }
        LOCK();
        if (qint(r, "reset", 0)) rc = zpet_param_reset(g_pet, id);
        else if (qstr(r, "v", sv, sizeof(sv))) rc = zpet_param_set(g_pet, id, atof(sv));
        else rc = -2;
        UNLOCK();
        if (rc == -1) {
            char body[160];
            z_snprintf(body, sizeof(body),
                       "{\"ok\":false,\"error\":\"没有这个参数\",\"id\":\"%s\"}", id);
            send_text(fd, 404, "application/json", body);
        } else if (rc == -2) {
            send_text(fd, 400, "application/json", "{\"ok\":false,\"error\":\"缺少 v\"}");
        } else {
            char body[160];
            z_snprintf(body, sizeof(body), "{\"ok\":true,\"id\":\"%s\"}", id);
            send_text(fd, 200, "application/json", body);
        }
        return;
    }
    if (strcmp(r->path, "/api/physics") == 0) {
        /* 物理摆总开关。on=0 关（所有摆立刻停在目标上、输出归零）、on=1 开。
           排查接缝必须先关它：冻结时钟时物理的 pos 不再积分，而改参数会让
           target 立刻跳，输出 pos-target 被人为拉满 → 剖面上凭空多出假跳变
           （2026-10-14 实测虚报过一处 +2.35px 的"躯干底边接缝"）。
           和 /api/blink 一样：一个参数都没给就报 400，不许静默忽略。 */
        char s[32];
        char body[96];
        if (!qstr(r, "on", s, sizeof(s))) {
            send_text(fd, 400, "application/json",
                      "{\"ok\":false,\"error\":\"要给 on=0 或 on=1\"}");
            return;
        }
        LOCK();
        zpet_set_phys_enabled(g_pet, atoi(s) != 0);
        zpet_tick(g_pet, pet_now());
        UNLOCK();
        z_snprintf(body, sizeof(body), "{\"ok\":true,\"physics\":%s}",
                   atoi(s) != 0 ? "true" : "false");
        send_text(fd, 200, "application/json", body);
        return;
    }
    if (strcmp(r->path, "/api/ambient") == 0) {
        /* 环境摆动（ambient）总开关。on=0 关、on=1 开。

           为什么要能关：ambient 是**往参数上加偏移**的（裙摆那条 drift 幅度就有 0.72）。
           开着的时候 `/api/param?id=ParamSkirtSway&v=0` 得到的并不是"裙子不动"，
           而是 0 叠上一个随时刻变化的底噪；推到 1.15 又会被上限夹住。
           做"改了这一处到底影响了哪些像素"的对照图时，必须先把底噪关掉。 */
        char s[32];
        char body[96];
        if (!qstr(r, "on", s, sizeof(s))) {
            send_text(fd, 400, "application/json",
                      "{\"ok\":false,\"error\":\"要给 on=0 或 on=1\"}");
            return;
        }
        LOCK();
        zpet_set_ambient_enabled(g_pet, atoi(s) != 0);
        zpet_tick(g_pet, pet_now());
        UNLOCK();
        z_snprintf(body, sizeof(body), "{\"ok\":true,\"ambient\":%s}",
                   atoi(s) != 0 ? "true" : "false");
        send_text(fd, 200, "application/json", body);
        return;
    }
    if (strcmp(r->path, "/api/pause") == 0) {
        /* 冻结/恢复引擎时钟。on=1 冻结（默认），on=0 恢复。
           冻结期间 /api/frame.png 反复取是同一帧，参数一改就只有参数的影响。 */
        /* t=<秒>（可选）：冻结到**指定**时间戳而不是"此刻"。
           做 A/B 对照图时两个进程各自的"此刻"不同 ⇒ 环境摆动（ambient 是绝对时间的函数）
           相位对不上，整张图都在动，根本比不出改了什么。给定同一个 t，
           再让它空跑一会（物理是固定步长，输入恒定就会收敛到同一个平衡点），
           两次运行就能逐像素比较。T45.11 做里布 A/B 时踩到的。 */
        char body[128];
        int on = 1;
        double tq = 0.0;
        int has_t = 0;
        if (r->query[0]) {
            char tb[64];
            on = qint(r, "on", 1);
            if (qstr(r, "t", tb, sizeof(tb)) && tb[0]) { tq = atof(tb); has_t = 1; }
        }
        LOCK();
        if (on && (!g_frozen || has_t)) {
            g_freeze_t = has_t ? tq : z_now_seconds();
            g_frozen = 1;
        }
        else if (!on) { g_frozen = 0; }
        zpet_tick(g_pet, pet_now());
        UNLOCK();
        z_snprintf(body, sizeof(body), "{\"ok\":true,\"paused\":%s}", on ? "true" : "false");
        send_text(fd, 200, "application/json", body);
        return;
    }
    if (strcmp(r->path, "/api/step") == 0) {
        /* 冻结状态下**按固定步长空跑** n 帧（dt 默认 1/60 秒）。

           为什么需要它：冻结时钟后 dt 恒为 0，物理、摆动延迟（bind 的 lag）
           这些"需要时间才能走到位"的东西**一步都不会走**——改了参数只有直连的
           绑定会动，经过物理/lag 的部件原地不动。T45.11 做裙子里布时就是栽在这：
           里布挂的是 lag 0.2 的绑定，暂停下无论等多久都跟不上，看起来像"没接上"。

           有了固定步长空跑，"同一个起始时刻 + 同一串参数 + 同样多的步数"就必然
           得到同一帧，A/B 对照图才真的可比（物理固定步长是 DC53 的既定前提）。 */
        char body[160];
        int    n  = qint(r, "n", 1);
        char   tb[64];
        double dt = 1.0 / 60.0;
        if (qstr(r, "dt", tb, sizeof(tb)) && tb[0]) dt = atof(tb);
        if (n < 0) n = 0;
        if (n > 6000) n = 6000;            /* 100 秒封顶，别让一个请求把服务卡死 */
        if (!(dt > 0.0) || dt > 1.0) dt = 1.0 / 60.0;
        LOCK();
        if (!g_frozen) { g_freeze_t = z_now_seconds(); g_frozen = 1; }
        for (int i = 0; i < n; i++) {
            g_freeze_t += dt;
            zpet_tick(g_pet, g_freeze_t);
        }
        UNLOCK();
        z_snprintf(body, sizeof(body),
                   "{\"ok\":true,\"steps\":%d,\"dt\":%.6f,\"t\":%.3f}", n, dt, g_freeze_t);
        send_text(fd, 200, "application/json", body);
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
        else if (z_streq(argv[i], "--web") && i + 1 < argc) {
            z_strlcpy(g_frames_dir, argv[++i], sizeof(g_frames_dir));
            continue;
        }
        else if (z_streq(argv[i], "--port") && i + 1 < argc) port = atoi(argv[++i]);
        else if (z_streq(argv[i], "--bind") && i + 1 < argc) bind_ip = argv[++i];
    }

    z_strlcpy(g_root, root, sizeof(g_root));
    if (g_frames_dir[0] != '/') {                 /* 相对路径按 root 解析 */
        char tmp[1024];
        z_strlcpy(tmp, g_frames_dir, sizeof(tmp));
        z_path_join(g_frames_dir, sizeof(g_frames_dir), root, tmp);
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
    g_start_time = pet_now();

    /* 网关路由表：读不到只是平台功能不可用，桌宠本体照常跑。
       所以这里不 return，只把失败如实记下来——/api/gateway.json 会报 loaded:false。 */
    {
        char gwpath[1200];
        zdiag gwd;
        zdiag_init(&gwd);
        z_snprintf(gwpath, sizeof(gwpath), "%s/config/gateway_routes.json", g_cfg.root_dir);
        g_gw_ok = (zgw_load(&g_gw, gwpath, &gwd) == 0);
        if (!g_gw_ok) {
            ZLOGW("gateway", "路由表没读到（%s），平台功能先关着", gwpath);
        } else {
            char logpath[1200];
            /* 决策流水落盘：阈值是抄来的，得用自己的数据重标（DC18 的复查触发）。
               data/ 不入库，是本机运行数据。 */
            z_snprintf(logpath, sizeof(logpath), "%s/data", g_cfg.root_dir);
            z_mkdir_p(logpath);
            z_snprintf(logpath, sizeof(logpath), "%s/data/usage.jsonl", g_cfg.root_dir);
            zgw_set_usage_log(&g_gw, logpath);
            ZLOGI("gateway", "路由表 %d 条，策略 %s，决策流水 %s",
                  g_gw.nroutes, g_gw.strategy, logpath);
        }
    }

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
        zpet_tick(g_pet, pet_now());
    }

    zsock_close(srv);
    zpet_destroy(g_pet);
    zlog_close();
    return 0;
}
