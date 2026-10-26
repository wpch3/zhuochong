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
 *   GET /api/force?gx=&gy=&wx=&wy=&breeze=&hz=&gust_x=&gust_y=&gust_t=
 *                              力场（T47.3）：重力方向 / 定常风 / 常驻微风 / 一阵风；不给参数 = 只读
 *   GET /api/pose?group=&id=   互斥部件组切档（≈ pose3.json；id=none 整组关掉）
 *   GET /api/sockets.json      挂点表（骨架命名位置）+ 它们这一刻画在哪
 *   GET /api/params.json       命名参数表（≈ Live2D ParamXxx）与当前值
 *   GET /api/param?id=&v=      直接写一个参数（reset=1 回默认；all=1 全部复位）
 *   GET /api/expression?id=    叠一个表情（off=1 取消），表情和动作是两条轨
 *   GET /api/form?id=          切换形态
 *   GET /api/outfit?id=        换装
 *   GET /api/idle?s=           上报系统空闲秒数（沙箱里由浏览器上报）
 *   GET /api/gateway.json      网关：每种能力实际会路由到谁、账本、密钥是否就位
 *   GET /api/chat              真的发一次 chat（G54）。dry=1 则只给出"将要发什么"，一个字节都不发
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
#include "../core/zrelay.h"
#include "../core/zctx.h"
#include "../core/zconfig.h"
#include "../core/zpersona.h"
#include "../core/zmem.h"
#include "../core/zthink.h"
#include "../core/zjson.h"

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
/* 虚拟时钟超前真实时钟的量。`/api/step` 是拿冻结时刻往后加的，物理/台词/冷却的判据
   都记在**虚拟**时间上；一拍一拍空跑 30 秒之后解冻，真实单调钟还落在 30 秒前，
   那些判据就全变成了"未来时间"：`now - last < cooldown` 恒成立 ⇒ 台词被静音，
   要等墙上时钟追上来才恢复（60 秒级别的假死）。这里把超前的部分记成偏移量，
   解冻时一次性补回，让引擎时钟**只前进不后退**。
   注意：显式 `t=` 不参与补偿 —— 那是给 A/B 对照图固定环境相位的（t=0 之类），
   它本来就该是"任意时间点"，钳到此刻反而会毁掉逐像素可比性。 */
static double g_time_off = 0.0;
static double pet_now(void)
{
    return g_frozen ? g_freeze_t : z_now_seconds() + g_time_off;
}

static zpet *g_pet = NULL;
/* 长记忆线（T67.45）。NULL = 没打开（data/ 不可写等）—— 这时她只是失忆，
   不许因此起不来，但必须能在 /api/memory.json 里看见 open:false。 */
static zmem *g_mem = NULL;
/* 她的节奏（T69.1）：脱口而出还是先想一想。由 mind.params.json 决定「她有多快」，
   由 zthink 决定「这一次用不用想」。 */
static zthink_profile g_think;
/* 她自己上次开口的时间（monotonic 秒）—— 主动开口的冷却用它，不是用户说话的时间 */
static double g_self_spoke_at = 0.0;
static int    g_self_topic_open = 0;   /* 上一句是她主动提的、对方还没接 */
/* 网关（G51）：进程启动时读一次路由表。读不到不影响桌宠本体跑，
   只是 /api/gateway.json 会如实说"没加载"。 */
static zgateway g_gw;
static int      g_gw_ok = 0;

/* 统一上下文（T60.1）。会话历史存在这儿 —— 进程内存，重启就忘。
   持久化是另一件事（得先想清楚"她该记多久"要不要用户说了算），
   现在先把"这一次运行里记得住"做对。 */
static zctx g_ctx;
/* UI 与静态资源目录：界面文件放 web/，媒体（配音/素材）走 /media/，
 * 这样改界面完全不用动 C 代码（对应“全部可自定义”的原则）。 */
static char g_root[1024] = ".";
static char g_frames_dir[1024] = "web";
static zconfig g_cfg;
static double g_start_time = 0.0;
static volatile int g_quit = 0;

/* 两把锁，分管两件事 —— 这不是优化，是**功能要求**。
 *
 * 2026-10-24 实测：模型想 6 秒，整个预览服务卡死 6 秒 ——
 * /api/info.json 直接超时，立绘停成一张照片。本地大模型想 10~30 秒是常事，
 * 也就是说"每说一句话她就变雕塑"。对一个桌宠来说这是致命的。
 *
 * 根因有两层，两层都得修：
 *   ① g_lock 被 /api/chat 攥着跨越整个网络往返 → 渲染线程拿不到锁；
 *   ② HTTP 是单线程 accept 循环，而那个循环同时负责 zpet_tick → 请求一慢全停。
 *
 * 所以：g_lock 只管宠物自己（状态机/动作/表情），
 *       g_ai_lock 管网关账本和上下文。慢请求攥着 g_ai_lock 不要紧，
 *       渲染线程要的是 g_lock，两边不打架。
 */
#ifndef _WIN32
static pthread_mutex_t g_lock = PTHREAD_MUTEX_INITIALIZER;
static pthread_mutex_t g_ai_lock = PTHREAD_MUTEX_INITIALIZER;
#  define LOCK()   pthread_mutex_lock(&g_lock)
#  define UNLOCK() pthread_mutex_unlock(&g_lock)
#  define AILOCK()   pthread_mutex_lock(&g_ai_lock)
#  define AIUNLOCK() pthread_mutex_unlock(&g_ai_lock)
#else
static CRITICAL_SECTION g_lock;
static CRITICAL_SECTION g_ai_lock;
#  define LOCK()   EnterCriticalSection(&g_lock)
#  define UNLOCK() LeaveCriticalSection(&g_lock)
#  define AILOCK()   EnterCriticalSection(&g_ai_lock)
#  define AIUNLOCK() LeaveCriticalSection(&g_ai_lock)
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

/* 把一次加载失败的诊断原样回给界面（文件 + 行 + 字段 + 原因）。
   ★ 2026-10-24（第六十一问）：换形态/换装失败原来静默回 {"ok":true}，
     用户只看到"点了没反应"。项目对配置错误的老口径是"能定位、不崩溃、
     不静默忽略"，接口这一层也必须守同一条。 */
static void send_diag_json(zsock fd, const char *what, const char *req,
                           const char *current, const zdiag *d)
{
    char ef[ZERR_FILE_MAX], efd[160], em[ZERR_MSG_MAX], eb[ZERR_MSG_MAX];
    char body[2048];
    const zerr *e = NULL;
    for (int i = 0; i < d->count; i++)
        if (d->items[i].msg[0]) { e = &d->items[i]; break; }   /* 第一条就是根因 */
    zjson_escape(e ? e->file : "", ef, sizeof(ef));
    zjson_escape(e ? e->field : "", efd, sizeof(efd));
    zjson_escape(e ? e->msg : "未知错误", em, sizeof(em));
    zjson_escape(req, eb, sizeof(eb));
    current = current ? current : "";
    char cur[ZERR_MSG_MAX];
    zjson_escape(current, cur, sizeof(cur));
    z_snprintf(body, sizeof(body),
               "{\"ok\":false,\"error\":\"%s\",\"requested\":\"%s\","
               "\"current\":\"%s\",\"diag\":{\"file\":\"%s\",\"line\":%d,"
               "\"field\":\"%s\",\"message\":\"%s\"},\"count\":%d}",
               what, eb, cur, ef, e ? e->line : 0, efd, em, d->count);
    send_text(fd, 409, "application/json", body);
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
/* ★★★ 2026-10-23 第四十八问：内置调试页原来是 200ms = 5fps，翻页一样卡。
   官方口径（docs/REFERENCE_NOTES.md 第六十一批）：cybernoids FAQ「一个模型
   最低 30FPS 以上」；nizima LIVE 把帧率拆成 Drawing FPS / Physics FPS 两档
   各 30/60。实测本机 /api/frame.png 单帧 s100 只要 32.8ms（直连 127.0.0.1，
   12 次中位），30fps 够得着，所以改 33ms。主 UI 那条循环在
   web/components/stage.js，同批从 12fps 提到 30fps。 */
"setInterval(refresh,33);\n"
"setInterval(loadInfo,700);\n"
"loadInfo();\n"
"function loadSpeech(){api('/api/speech.json').then(d=>{\n"
"  document.getElementById('speech').textContent=d.line?('「'+d.line+'」'):'';\n"
"  document.getElementById('mood').textContent=d.mood?('情绪：'+d.mood):'';});}\n"
"setInterval(loadSpeech,500);\n"
"</script></body></html>";

/* ------------------------------------------------------------ 请求处理 */
/* 慢端点（/api/chat）的工作线程。
 *
 * 为什么非要开线程：accept 循环和 zpet_tick 在同一个 while 里 ——
 * 请求处理一慢，立绘就停。实测模型想 6 秒 ⇒ 她当场变雕塑 6 秒。
 * 桌宠最不能接受的就是"你跟她说话，她僵住"。
 *
 * 只有真发的 chat 走这条路：dry-run 和其它端点都是微秒级，
 * 开线程的开销反而更大。 */
typedef struct {
    zsock    fd;
    http_req req;
} slow_job;

static void handle_request(zsock fd, const http_req *r);

#ifndef _WIN32
static void *slow_worker(void *arg)
{
    slow_job *j = (slow_job *)arg;
    handle_request(j->fd, &j->req);
    zsock_close(j->fd);
    free(j);
    return NULL;
}
#else
static DWORD WINAPI slow_worker(LPVOID arg)
{
    slow_job *j = (slow_job *)arg;
    handle_request(j->fd, &j->req);
    zsock_close(j->fd);
    free(j);
    return 0;
}
#endif

/* 返回 1 = 已经交给工作线程（调用方不要再 close fd） */
static int dispatch_slow(zsock fd, const http_req *r)
{
    slow_job *j;
    if (strcmp(r->path, "/api/chat") != 0) return 0;
    /* dry-run 不出网，几微秒就回来，不值得开线程 */
    if (strstr(r->query, "dry=1")) return 0;

    j = (slow_job *)malloc(sizeof(*j));
    if (!j) return 0;                      /* 开不出来就退回同步，功能不受影响 */
    j->fd = fd;
    j->req = *r;
#ifndef _WIN32
    {
        pthread_t th;
        if (pthread_create(&th, NULL, slow_worker, j) != 0) { free(j); return 0; }
        pthread_detach(th);
    }
#else
    {
        HANDLE th = CreateThread(NULL, 0, slow_worker, j, 0, NULL);
        if (!th) { free(j); return 0; }
        CloseHandle(th);
    }
#endif
    return 1;
}

static void handle_request(zsock fd, const http_req *r)
{
    char buf[2048];
    /* 长记忆的两块上下文（T67.45）：锚点块 + 相关回忆块。
       放函数作用域是因为聊天handler里有多层嵌套块，声明在里层用不到外层。 */
    char mem_anchor[ZMEM_BLOCK_CAP + 64], mem_recall[ZMEM_BLOCK_CAP + 64];
    /* 真正发出去的系统提示词（T67.45 顺手修的既有缺陷）。
       ★ 原来 `q.system_prompt` 只塞了人设那段，zctx 里其它块**根本不上路** ——
         清单上写着"带上了"，实际没发出去。人设之外最先需要它的是长期记忆：
         记忆块只在清单里存在、不进请求，等于她压根想不起来。
         现在按清单里 kept=1 的块顺序拼，和上面 history 那条规矩一致：
         清单写带了几块，出网的就得是那几块。 */
    char sysbuf[12288];
    /* 她主动开口时的立场（T69.2）。放在这个作用域：块要注册进 zctx，
       而 zctx_set_block 只存指针，所以缓冲区必须活到拼提示词那一步之后。 */
    char self_block[768];
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
        /* ★ 缓冲区 2026-10-18 从 4096 扩到 16384（T46.3 当场撞上）：
             这份 JSON 的长度跟着 rig 的部件 / 形变器 / 摆链条数线性涨。
             加三个发型（+3 部件 +4 形变器 +3 摆链）之后就超了 4096，
             而 z_snprintf 是**静默截断**的 —— 返回的是一串缺尾括号的烂 JSON，
             前端和探针都只会报「JSON 解析失败」，不会告诉你是谁写满了。
             所以除了扩容，下面收尾处还加了一条\"写满了就明着报错\"的守卫。 */
        char body[16384];
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
        /* action_names 和 actions 一一对应（照 forms / form_names 的老写法）。
           名字来自 rig.json，不是界面里的硬编码表 —— 正式软件的 UI 要整个重做，
           界面层存的任何文案都得重写一遍，数据层存的不用。 */
        p += z_snprintf(p, cap - (size_t)(p - body), "],\"action_names\":[");
        for (i = 0; i < zpet_action_count(g_pet); ++i)
            p += z_snprintf(p, cap - (size_t)(p - body), "%s\"%s\"", i ? "," : "", zpet_action_title_at(g_pet, i));
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
        {   /* T47.3 力场：gravity / 定常 wind / 常驻微风 amp / **本帧实际吹的风**。
               最后那一对是关键 —— "我设了风"和"风真吹到头发上了"是两件事。 */
            double gx = 0, gy = 0, wx = 0, wy = 0, ex = 0, ey = 0;
            zpet_force_get(g_pet, &gx, &gy, &wx, &wy);
            zpet_wind_now(g_pet, &ex, &ey);
            p += z_snprintf(p, cap - (size_t)(p - body),
                            "},\"forces\":{\"gx\":%.4f,\"gy\":%.4f,\"wx\":%.4f,\"wy\":%.4f,"
                            "\"breeze\":%.4f,\"wind_x\":%.4f,\"wind_y\":%.4f",
                            gx, gy, wx, wy, zpet_breeze_amp(g_pet), ex, ey);
        }
        p += z_snprintf(p, cap - (size_t)(p - body), "}}");
        UNLOCK();
        /* 写满 = 这份 JSON 已经被截断了。宁可返回 500 也不要送一份烂 JSON 出去：
           截断过的 body 照样以 200 发出去的话，症状会伪装成「前端解析失败」，
           而真正的原因（缓冲区小了）藏在 C 这一侧，没人会往这里看。 */
        if ((size_t)(p - body) >= cap - 1) {
            send_text(fd, 500, "application/json",
                      "{\"ok\":false,\"error\":\"info.json 超出缓冲区被截断了，"
                      "去 main_headless.c 把 body[] 调大\"}");
            return;
        }
        send_text(fd, 200, "application/json", body);
        return;
    }
    if (strcmp(r->path, "/api/force") == 0) {
        /* T47.3 调试端点：重力方向、定常风、常驻微风、阵风，全在这一个口子上。
             ?gx=&gy=        重力方向（不必归一化；两个都给才算改）
             ?wx=&wy=        定常风
             ?breeze=&hz=    常驻微风幅度与主频（breeze=0 关）
             ?gust_x=&gust_y=&gust_t=  来一阵风（情绪/事件用，生气就是一股风）
           一个参数都不给 = 只读当前值。 */
        char tb[64], body[320];
        double gx = 0, gy = 0, wx = 0, wy = 0, ex = 0, ey = 0;
        int got = 0;
        LOCK();
        zpet_force_get(g_pet, &gx, &gy, &wx, &wy);
        if (qstr(r, "gx", tb, sizeof(tb))) { gx = atof(tb); got = 1; }
        if (qstr(r, "gy", tb, sizeof(tb))) { gy = atof(tb); got = 1; }
        if (qstr(r, "wx", tb, sizeof(tb))) { wx = atof(tb); got = 1; }
        if (qstr(r, "wy", tb, sizeof(tb))) { wy = atof(tb); got = 1; }
        if (got) zpet_force_set(g_pet, gx, gy, wx, wy);
        if (qstr(r, "breeze", tb, sizeof(tb))) {
            char hb[64];
            double hz = qstr(r, "hz", hb, sizeof(hb)) ? atof(hb) : 0.0;
            zpet_breeze_set(g_pet, atof(tb), hz);
            got = 1;
        }
        if (qstr(r, "gust_x", tb, sizeof(tb)) || qstr(r, "gust_y", tb, sizeof(tb))) {
            char xb[64], yb[64], sb[64];
            double sx = qstr(r, "gust_x", xb, sizeof(xb)) ? atof(xb) : 0.0;
            double sy = qstr(r, "gust_y", yb, sizeof(yb)) ? atof(yb) : 0.0;
            double sc = qstr(r, "gust_t", sb, sizeof(sb)) ? atof(sb) : 0.6;
            zpet_gust(g_pet, sx, sy, sc);
            got = 1;
        }
        zpet_force_get(g_pet, &gx, &gy, &wx, &wy);
        zpet_wind_now(g_pet, &ex, &ey);
        z_snprintf(body, sizeof(body),
                   "{\"ok\":true,\"changed\":%s,\"gx\":%.4f,\"gy\":%.4f,"
                   "\"wx\":%.4f,\"wy\":%.4f,\"breeze\":%.4f,"
                   "\"wind_x\":%.4f,\"wind_y\":%.4f}",
                   got ? "true" : "false", gx, gy, wx, wy,
                   zpet_breeze_amp(g_pet), ex, ey);
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
    if (strcmp(r->path, "/api/part") == 0) {
        /* T67.1 分层隔离探针：关掉一件 / 只看一件。
           ?id=<部件>&vis=0|1|2   （0 隐藏、1 正常、2 隔离只看它）
           ?all=1                 全部恢复
           ?list=1                列出全部部件与当前可见性
           它只影响"画不画"，不碰遮罩缓冲、命中区和参数 —— 是一个观察窗。 */
        char id[96];
        int list = qint(r, "list", 0);
        int all = qint(r, "all", 0);
        LOCK();
        if (list) {
            char body[8192];
            int n = 0, k, np = zpet_part_count(g_pet);
            n += z_snprintf(body + n, sizeof body - n, "{\"ok\":true,\"isolating\":%d,\"parts\":[",
                            zpet_vis_isolating(g_pet));
            for (k = 0; k < np && n < (int)sizeof body - 80; ++k) {
                n += z_snprintf(body + n, sizeof body - n, "%s{\"id\":\"%s\",\"vis\":%d}",
                                k ? "," : "", zpet_part_id(g_pet, k), zpet_part_vis(g_pet, k));
            }
            n += z_snprintf(body + n, sizeof body - n, "]}");
            UNLOCK();
            send_text(fd, 200, "application/json", body);
            return;
        }
        if (all) {
            zpet_vis_clear(g_pet);
            zpet_tick(g_pet, pet_now());
            UNLOCK();
            send_text(fd, 200, "application/json", "{\"ok\":true,\"cleared\":true}");
            return;
        }
        if (!qstr(r, "id", id, sizeof id) || !id[0]) {
            UNLOCK();
            send_text(fd, 400, "application/json", "{\"ok\":false,\"error\":\"缺少 id\"}");
            return;
        }
        {
            int vis = qint(r, "vis", 0);
            int rc = zpet_part_vis_set(g_pet, id, vis);
            if (rc == 0) zpet_tick(g_pet, pet_now());
            UNLOCK();
            if (rc != 0) {
                char body2[192];
                z_snprintf(body2, sizeof body2,
                           "{\"ok\":false,\"error\":\"没有这个部件（或 vis 越界）\",\"id\":\"%s\"}", id);
                send_text(fd, 404, "application/json", body2);
            } else {
                char body2[224];
                z_snprintf(body2, sizeof body2,
                           "{\"ok\":true,\"id\":\"%s\",\"vis\":%d,\"isolating\":%d}",
                           id, vis, zpet_vis_isolating(g_pet));
                send_text(fd, 200, "application/json", body2);
            }
        }
        return;
    }

    if (strcmp(r->path, "/api/mask.png") == 0) {
        /* G66.13 调试图：把「某个被裁部件这一帧看到的遮罩」直接出一张 PNG。
           ?id= 必填（挂 mask 的部件，如 eye_l_base）；?s= 同 frame.png。 */
        char mask_id[96];
        const zimg *mi = NULL;
        int mw = 0, mh = 0;
        int spct = qint(r, "s", 100);
        if (spct < 25) spct = 25;
        if (spct > 100) spct = 100;
        if (!qstr(r, "id", mask_id, sizeof mask_id) || !mask_id[0]) {
            send_text(fd, 400, "application/json", "{\"ok\":false,\"error\":\"缺少 id\"}");
            return;
        }
        LOCK();
        mi = zpet_mask_frame(g_pet, mask_id, &mw, &mh);
        if (mi && spct < 100) {
            zimg *small = zimg_downscale(mi, mi->w * spct / 100, mi->h * spct / 100);
            if (small) {
                send_png(fd, small);
                zimg_free(small);
                UNLOCK();
                return;
            }
        }
        if (mi) send_png(fd, mi);
        UNLOCK();
        if (!mi) {
            send_text(fd, 404, "application/json",
                      "{\"ok\":false,\"error\":\"没有这个带遮罩的部件\"}");
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
    if (strcmp(r->path, "/api/persona.json") == 0) {
        /* 把三层人设合成的系统提示词原样吐出来。
           这是"所见即所得"那条线的关键：面板上显示的就是真的会喂给模型的那段文本，
           不做任何隐藏拼接 —— 用户改一个滑杆，马上能看见提示词哪一行变了。 */
        static char body[8192];
        char prompt[4096], esc[6144];
        zpersona zp;
        zdiag d;
        size_t n;
        int tier, k, off;

        zdiag_init(&d);
        LOCK();
        tier = zpet_affection_tier(g_pet);
        UNLOCK();
        if (!zpersona_load(&zp, g_root, zpet_character(g_pet), &d)) {
            send_text(fd, 500, "application/json",
                      "{\"ok\":false,\"error\":\"人设加载失败，看 logs/preview.log\"}");
            return;
        }
        n = zpersona_compose(&zp, tier, prompt, sizeof(prompt));
        zjson_escape(prompt, esc, sizeof(esc));
        {
            char en[128], ec[1536];
            zjson_escape(zp.nickname, en, sizeof(en));
            zjson_escape(zp.custom, ec, sizeof(ec));
            off = (int)z_snprintf(body, sizeof(body),
                   "{\"ok\":true,\"character\":\"%s\",\"name\":\"%s\",\"preset\":\"%s\","
                   "\"tier\":%d,\"meeting_todo\":%d,\"nickname\":\"%s\",\"custom\":\"%s\","
                   "\"prompt_bytes\":%u,\"prompt\":\"%s\",\"traits\":[",
                   zp.character, zp.name, zp.preset, tier, zpersona_meeting_todo(&zp),
                   en, ec, (unsigned)n, esc);
        }
        for (k = 0; k < zp.lib.ntraits && off < (int)sizeof(body) - 256; ++k)
            off += (int)z_snprintf(body + off, sizeof(body) - (size_t)off,
                       "%s{\"id\":\"%s\",\"name\":\"%s\",\"low\":\"%s\",\"high\":\"%s\",\"v\":%d}",
                       k ? "," : "", zp.lib.traits[k].id, zp.lib.traits[k].name,
                       zp.lib.traits[k].low, zp.lib.traits[k].high, zp.tv[k]);
        off += (int)z_snprintf(body + off, sizeof(body) - (size_t)off, "],\"presets\":[");
        for (k = 0; k < zp.lib.npresets && off < (int)sizeof(body) - 256; ++k)
            off += (int)z_snprintf(body + off, sizeof(body) - (size_t)off,
                       "%s{\"id\":\"%s\",\"name\":\"%s\"}",
                       k ? "," : "", zp.lib.presets[k].id, zp.lib.presets[k].name);
        z_snprintf(body + off, sizeof(body) - (size_t)off, "]}");
        send_text(fd, 200, "application/json", body);
        return;
    }
    /* 她的节奏（T69.1）：这一句她会脱口而出，还是先想一想。
       ★ 这个端点存在的理由不是给用户看的，是**可审计**：
         她"这次为什么想了想"必须能被打出来，否则和随机数没区别。
         决定完全由引擎做，没有任何"要不要深思"的开关。 */
    if (strcmp(r->path, "/api/think.json") == 0) {
        static char body[2048];
        zthink_in in;
        zthink_out out;
        char text[512], esc[768], escwhy[512], escpre[160];
        double mood = qint(r, "mood", -1) >= 0 ? (double)qint(r, "mood", 50) / 100.0 : 0.6;
        time_t now = time(NULL);
        struct tm lt;
        int hour = qint(r, "hour", -1);

        memset(&in, 0, sizeof(in));
        qstr(r, "text", text, sizeof text);
        in.text = text;
        in.tier = qint(r, "tier", g_pet ? zpet_affection_tier(g_pet) : 0);
        in.mood = mood;
        if (hour < 0) {
            localtime_r(&now, &lt);
            hour = lt.tm_hour;
        }
        in.hour = hour;
        in.since_last_ms = (int64_t)qint(r, "since", 60000);
        in.had_topic = qint(r, "topic", 0) ? 1 : 0;

        zthink_decide(&g_think, &in, &out);
        zjson_escape(text, esc, sizeof esc);
        zjson_escape(out.why, escwhy, sizeof escwhy);
        zjson_escape(out.preface, escpre, sizeof escpre);
        z_snprintf(body, sizeof(body),
                   "{\"ok\":true,\"text\":\"%s\",\"mode\":\"%s\",\"mode_id\":%d,"
                   "\"delay_ms\":%d,\"preface\":\"%s\",\"max_tokens\":%d,"
                   "\"needs_memory\":%s,\"score\":%.3f,\"why\":\"%s\","
                   "\"params_ok\":%s,\"tier\":%d,\"hour\":%d}",
                   esc, zthink_mode_id(out.mode), out.mode, out.delay_ms, escpre,
                   out.max_tokens, out.needs_memory ? "true" : "false", out.score,
                   escwhy, g_think.ok ? "true" : "false", in.tier, in.hour);
        send_text(fd, 200, "application/json", body);
        return;
    }

    /* 她自己想不想开口（T69.1）。UI 隔一会儿问一次，够阈值就让她说一句。
       ★ 这个端点**只回答"要不要"和"为什么"，不替她说** —— 说话仍然走 /api/chat，
         这样"她主动开口"和"回答你"用同一条链路，不会长成两套性格。
       ★ 冷却按**她自己上次开口**算，不是按用户说话算：用户刚说完她当然可以接，
         那不算"主动"。 */
    if (strcmp(r->path, "/api/urge.json") == 0) {
        static char body[2048];
        zthink_in in;
        zthink_urge u;
        time_t now = time(NULL);
        struct tm lt;
        int hour = qint(r, "hour", -1);
        double since_ms;

        memset(&in, 0, sizeof(in));
        in.text = "";
        in.tier = qint(r, "tier", g_pet ? zpet_affection_tier(g_pet) : 0);
        in.mood = (double)qint(r, "mood", 60) / 100.0;
        if (hour < 0) {
            localtime_r(&now, &lt);
            hour = lt.tm_hour;
        }
        in.hour = hour;
        since_ms = (pet_now() - g_self_spoke_at) * 1000.0;
        if (qint(r, "since", -1) >= 0) since_ms = (double)qint(r, "since", 0);
        in.since_last_ms = (int64_t)(since_ms < 0 ? 0 : since_ms);
        in.had_topic = g_self_topic_open;

        zthink_urge_now(&g_think, &in, qint(r, "promise", 0), qint(r, "memory", 0), &u);
        {
            char escwhy[512];
            zjson_escape(u.why, escwhy, sizeof escwhy);
            z_snprintf(body, sizeof(body),
                       "{\"ok\":true,\"urge\":%.3f,\"would_speak\":%s,"
                       "\"intent\":\"%s\",\"intent_id\":%d,\"wait_s\":%d,"
                       "\"why\":\"%s\",\"idle_s\":%d,\"hour\":%d}",
                       u.urge, u.would_speak ? "true" : "false",
                       zthink_intent_id(u.intent), u.intent, u.wait_s, escwhy,
                       (int)(in.since_last_ms / 1000), in.hour);
        }
        send_text(fd, 200, "application/json", body);
        return;
    }

    /* 她说完一句自己起头的话（UI 在展示自发言之后调一下）：
       记下时间（冷却）并把"话题还没被接"标上。对方回话时这个标记会清掉。 */
    if (strcmp(r->path, "/api/urge/spoke") == 0) {
        g_self_spoke_at = pet_now();
        g_self_topic_open = qint(r, "topic", 1) ? 1 : 0;
        send_text(fd, 200, "application/json",
                  "{\"ok\":true,\"self_spoke_at\":0,\"topic_open\":0}");
        return;
    }

    if (strcmp(r->path, "/api/memory.json") == 0) {
        /* 长记忆线的观察窗（T67.45）。三种问法：
             ?verify=1        全量对账（正文被改一个字节就报出来）
             ?q=<一句话>      她此刻会想起什么（原样打印给模型的那一段）
             其它             统计 + 锚点 + 最近 n 条
           ★ 这个端点只读。写入走 /api/memory/add|del|pin，删除必须带理由。 */
        static char body[16384];
        char q[512], blk[ZMEM_BLOCK_CAP + 256];
        zmem_stat st;
        int off = 0, n = qint(r, "n", 12);
        qstr(r, "q", q, sizeof q);
        if (!g_mem) {
            send_text(fd, 200, "application/json",
                      "{\"ok\":false,\"open\":false,\"error\":\"记忆文件没打开（data/ 不可写？见 logs/preview.log）\"}");
            return;
        }
        if (qint(r, "verify", 0)) {
            char why[192], escw[1024];
            int rc;
            why[0] = 0;
            LOCK();
            rc = zmem_verify(g_mem, why, sizeof why);
            UNLOCK();
            zjson_escape(why, escw, sizeof escw);
            off = (int)z_snprintf(body, sizeof body,
                     "{\"ok\":%s,\"open\":true,\"verify\":%d,\"why\":\"%s\"}",
                     rc == 0 ? "true" : "false", rc, escw);
            (void)off;
            send_text(fd, 200, "application/json", body);
            return;
        }
        LOCK();
        zmem_stats(g_mem, &st);
        blk[0] = 0;
        if (q[0]) zmem_recall(g_mem, q, (int64_t)time(NULL), blk, sizeof blk);
        else      zmem_anchors_block(g_mem, (int64_t)time(NULL), blk, sizeof blk);
        UNLOCK();
        {
            char dates[24], datee[24], escq[1900];
            zjson_escape(blk, escq, sizeof escq);
            zmem_date_text(st.oldest, dates, sizeof dates);
            zmem_date_text(st.newest, datee, sizeof datee);
            off = (int)z_snprintf(body, sizeof body,
                     "{\"ok\":true,\"open\":true,\"items\":%d,\"anchors\":%d,\"deleted\":%d,"
                     "\"stories\":%d,\"bytes\":%ld,\"oldest\":\"%s\",\"newest\":\"%s\","
                     "\"tz_offset_min\":%d,\"query\":\"%s\",\"block\":\"%s\",\"list\":",
                     st.items, st.anchors, st.deleted, st.stories, st.bytes,
                     st.items ? dates : "", st.items ? datee : "",
                     zmem_tz_offset(), q, escq);
        }
        {
            char items[8192];
            LOCK();
            zmem_export_json(g_mem, items, sizeof items, n, qint(r, "with_deleted", 0));
            UNLOCK();
            off += (int)z_snprintf(body + off, sizeof body - (size_t)off, "%s}", items);
        }
        send_text(fd, 200, "application/json", body);
        return;
    }
    if (strcmp(r->path, "/api/memory/add") == 0) {
        /* 写入一条。默认不自动记录任何对话（长期记忆默认关，见 MEMORY_PLAN）——
           只有用户显式要她记住，才会走到这里。 */
        char text[512], once[96], ts[32];
        int kind = qint(r, "kind", 0), sal = qint(r, "salience", 5);
        int64_t when = (int64_t)time(NULL);
        uint32_t id;
        if (!g_mem) { send_text(fd, 200, "application/json", "{\"ok\":false,\"open\":false}"); return; }
        if (!qstr(r, "text", text, sizeof text) || !text[0]) {
            send_text(fd, 400, "application/json", "{\"ok\":false,\"error\":\"缺少 text\"}");
            return;
        }
        qstr(r, "once", once, sizeof once);
        /* 可选 t（unix 秒）：导入历史经历时用。★ 只接受**过去**的时间，
           而且不能早于 2000 年 —— 否则一个笔误就能造出"公元 1900 年我们见过"，
           那种记忆一旦落盘就永远洗不掉（正文不可变）。 */
        if (qstr(r, "t", ts, sizeof ts) && ts[0]) {
            long long v = strtoll(ts, NULL, 10);
            long long nowq = (long long)time(NULL);
            if (v >= 946684800LL && v <= nowq + 86400LL) when = (int64_t)v;
            else {
                send_text(fd, 400, "application/json",
                          "{\"ok\":false,\"error\":\"t 越界：只接受 2000 年之后、且不晚于明天的过去时间\"}");
                return;
            }
        }
        LOCK();
        id = zmem_add(g_mem, when, kind, sal, text, once[0] ? once : NULL);
        UNLOCK();
        if (!id) {
            send_text(fd, 200, "application/json",
                      "{\"ok\":false,\"error\":\"没写进去：锚点已满（要先降级一条）或记忆条目到上限\"}");
            return;
        }
        {
            char body[160];
            z_snprintf(body, sizeof body, "{\"ok\":true,\"id\":%u}", id);
            send_text(fd, 200, "application/json", body);
        }
        return;
    }
    if (strcmp(r->path, "/api/memory/del") == 0 ||
        strcmp(r->path, "/api/memory/pin") == 0) {
        char reason[256];
        int id = qint(r, "id", 0), rc;
        int ispin = (strcmp(r->path, "/api/memory/pin") == 0);
        int unpin = qint(r, "unpin", 0);
        if (!g_mem) { send_text(fd, 200, "application/json", "{\"ok\":false,\"open\":false}"); return; }
        if (id <= 0) { send_text(fd, 400, "application/json", "{\"ok\":false,\"error\":\"缺少 id\"}"); return; }
        qstr(r, "reason", reason, sizeof reason);
        if (ispin && unpin && !reason[0]) {
            /* 升锚点可以不写理由；降级必须写 —— 否则以后没人解释得清"她为什么不再提这件事" */
            send_text(fd, 400, "application/json", "{\"ok\":false,\"error\":\"降级锚点必须写 reason\"}");
            return;
        }
        LOCK();
        if (!ispin)      rc = zmem_del(g_mem, (uint32_t)id, reason);
        else if (unpin)  rc = zmem_unpin(g_mem, (uint32_t)id, reason);
        else             rc = zmem_pin(g_mem, (uint32_t)id);
        UNLOCK();
        {
            char body[160];
            z_snprintf(body, sizeof body, "{\"ok\":%s}", rc ? "true" : "false");
            send_text(fd, rc ? 200 : 400, "application/json", body);
        }
        return;
    }
    if (strcmp(r->path, "/api/memory/story") == 0) {
        /* 她的自述：最新一版 + 历史版本（历史都在，能回答"她三个月前是怎么说的"） */
        static char body[8192];
        char cur[1024], esc[2048];
        int64_t stv = 0;
        int off = 0, k, cnt;
        if (!g_mem) { send_text(fd, 200, "application/json", "{\"ok\":false,\"open\":false}"); return; }
        LOCK();
        cnt = zmem_story_count(g_mem);
        cur[0] = 0;
        zmem_story_get(g_mem, 0, &stv, cur, sizeof cur);
        UNLOCK();
        zjson_escape(cur, esc, sizeof esc);
        off = (int)z_snprintf(body, sizeof body,
                 "{\"ok\":true,\"versions\":%d,\"latest_t\":%lld,\"latest\":\"%s\",\"history\":[",
                 cnt, (long long)stv, esc);
        for (k = 1; k <= cnt && off < (int)sizeof(body) - 512; ++k) {
            char v[1024], e2[2048];
            int64_t vt = 0;
            LOCK();
            zmem_story_get(g_mem, k, &vt, v, sizeof v);
            UNLOCK();
            zjson_escape(v, e2, sizeof e2);
            off += (int)z_snprintf(body + off, sizeof(body) - (size_t)off,
                       "%s{\"version\":%d,\"t\":%lld,\"text\":\"%s\"}",
                       k > 1 ? "," : "", k, (long long)vt, e2);
        }
        z_snprintf(body + off, sizeof(body) - (size_t)off, "]}");
        send_text(fd, 200, "application/json", body);
        return;
    }
    if (strcmp(r->path, "/api/persona/set") == 0) {
        /* 白名单写入：k=<键> v=<值>。键不在 zpersona_set 的名单里一律 400。
           对话侧要改人设也只能走这里 —— 不开"模型直接写 json"的口子。 */
        char key[64], val[512];
        zpersona zp;
        zdiag d;
        char body2[256];

        if (!qstr(r, "k", key, sizeof(key))) {
            send_text(fd, 400, "application/json", "{\"ok\":false,\"error\":\"缺少 k\"}");
            return;
        }
        if (!qstr(r, "v", val, sizeof(val))) val[0] = '\0';
        zdiag_init(&d);
        if (!zpersona_load(&zp, g_root, zpet_character(g_pet), &d)) {
            send_text(fd, 500, "application/json", "{\"ok\":false,\"error\":\"人设加载失败\"}");
            return;
        }
        if (!zpersona_set(&zp, key, val)) {
            z_snprintf(body2, sizeof(body2),
                       "{\"ok\":false,\"error\":\"这个键不可改或值非法\",\"k\":\"%s\"}", key);
            send_text(fd, 400, "application/json", body2);
            return;
        }
        if (!zpersona_save(&zp, g_root)) {
            send_text(fd, 500, "application/json", "{\"ok\":false,\"error\":\"写回失败\"}");
            return;
        }
        z_snprintf(body2, sizeof(body2), "{\"ok\":true,\"k\":\"%s\",\"v\":\"%s\"}", key, val);
        send_text(fd, 200, "application/json", body2);
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
        /* ★ 缓冲区 2026-10-18 从 4096 扩到 16384（T46.3 当场撞上）：
             这份 JSON 的长度跟着 rig 的部件 / 形变器 / 摆链条数线性涨。
             加三个发型（+3 部件 +4 形变器 +3 摆链）之后就超了 4096，
             而 z_snprintf 是**静默截断**的 —— 返回的是一串缺尾括号的烂 JSON，
             前端和探针都只会报「JSON 解析失败」，不会告诉你是谁写满了。
             所以除了扩容，下面收尾处还加了一条\"写满了就明着报错\"的守卫。 */
        char body[16384];
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
        /* action_names 和 actions 一一对应（照 forms / form_names 的老写法）。
           名字来自 rig.json，不是界面里的硬编码表 —— 正式软件的 UI 要整个重做，
           界面层存的任何文案都得重写一遍，数据层存的不用。 */
        p += z_snprintf(p, cap - (size_t)(p - body), "],\"action_names\":[");
        for (i = 0; i < zpet_action_count(g_pet); ++i)
            p += z_snprintf(p, cap - (size_t)(p - body), "%s\"%s\"", i ? "," : "", zpet_action_title_at(g_pet, i));
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
        {   /* T47.3 力场：gravity / 定常 wind / 常驻微风 amp / **本帧实际吹的风**。
               最后那一对是关键 —— "我设了风"和"风真吹到头发上了"是两件事。 */
            double gx = 0, gy = 0, wx = 0, wy = 0, ex = 0, ey = 0;
            zpet_force_get(g_pet, &gx, &gy, &wx, &wy);
            zpet_wind_now(g_pet, &ex, &ey);
            p += z_snprintf(p, cap - (size_t)(p - body),
                            "},\"forces\":{\"gx\":%.4f,\"gy\":%.4f,\"wx\":%.4f,\"wy\":%.4f,"
                            "\"breeze\":%.4f,\"wind_x\":%.4f,\"wind_y\":%.4f",
                            gx, gy, wx, wy, zpet_breeze_amp(g_pet), ex, ey);
        }
        p += z_snprintf(p, cap - (size_t)(p - body), "}}");
        UNLOCK();
        /* 写满 = 这份 JSON 已经被截断了。宁可返回 500 也不要送一份烂 JSON 出去：
           截断过的 body 照样以 200 发出去的话，症状会伪装成「前端解析失败」，
           而真正的原因（缓冲区小了）藏在 C 这一侧，没人会往这里看。 */
        if ((size_t)(p - body) >= cap - 1) {
            send_text(fd, 500, "application/json",
                      "{\"ok\":false,\"error\":\"info.json 超出缓冲区被截断了，"
                      "去 main_headless.c 把 body[] 调大\"}");
            return;
        }
        send_text(fd, 200, "application/json", body);
        return;
    }
    if (strcmp(r->path, "/api/force") == 0) {
        /* T47.3 调试端点：重力方向、定常风、常驻微风、阵风，全在这一个口子上。
             ?gx=&gy=        重力方向（不必归一化；两个都给才算改）
             ?wx=&wy=        定常风
             ?breeze=&hz=    常驻微风幅度与主频（breeze=0 关）
             ?gust_x=&gust_y=&gust_t=  来一阵风（情绪/事件用，生气就是一股风）
           一个参数都不给 = 只读当前值。 */
        char tb[64], body[320];
        double gx = 0, gy = 0, wx = 0, wy = 0, ex = 0, ey = 0;
        int got = 0;
        LOCK();
        zpet_force_get(g_pet, &gx, &gy, &wx, &wy);
        if (qstr(r, "gx", tb, sizeof(tb))) { gx = atof(tb); got = 1; }
        if (qstr(r, "gy", tb, sizeof(tb))) { gy = atof(tb); got = 1; }
        if (qstr(r, "wx", tb, sizeof(tb))) { wx = atof(tb); got = 1; }
        if (qstr(r, "wy", tb, sizeof(tb))) { wy = atof(tb); got = 1; }
        if (got) zpet_force_set(g_pet, gx, gy, wx, wy);
        if (qstr(r, "breeze", tb, sizeof(tb))) {
            char hb[64];
            double hz = qstr(r, "hz", hb, sizeof(hb)) ? atof(hb) : 0.0;
            zpet_breeze_set(g_pet, atof(tb), hz);
            got = 1;
        }
        if (qstr(r, "gust_x", tb, sizeof(tb)) || qstr(r, "gust_y", tb, sizeof(tb))) {
            char xb[64], yb[64], sb[64];
            double sx = qstr(r, "gust_x", xb, sizeof(xb)) ? atof(xb) : 0.0;
            double sy = qstr(r, "gust_y", yb, sizeof(yb)) ? atof(yb) : 0.0;
            double sc = qstr(r, "gust_t", sb, sizeof(sb)) ? atof(sb) : 0.6;
            zpet_gust(g_pet, sx, sy, sc);
            got = 1;
        }
        zpet_force_get(g_pet, &gx, &gy, &wx, &wy);
        zpet_wind_now(g_pet, &ex, &ey);
        z_snprintf(body, sizeof(body),
                   "{\"ok\":true,\"changed\":%s,\"gx\":%.4f,\"gy\":%.4f,"
                   "\"wx\":%.4f,\"wy\":%.4f,\"breeze\":%.4f,"
                   "\"wind_x\":%.4f,\"wind_y\":%.4f}",
                   got ? "true" : "false", gx, gy, wx, wy,
                   zpet_breeze_amp(g_pet), ex, ey);
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
    if (strcmp(r->path, "/api/persona.json") == 0) {
        /* 把三层人设合成的系统提示词原样吐出来。
           这是"所见即所得"那条线的关键：面板上显示的就是真的会喂给模型的那段文本，
           不做任何隐藏拼接 —— 用户改一个滑杆，马上能看见提示词哪一行变了。 */
        static char body[8192];
        char prompt[4096], esc[6144];
        zpersona zp;
        zdiag d;
        size_t n;
        int tier, k, off;

        zdiag_init(&d);
        LOCK();
        tier = zpet_affection_tier(g_pet);
        UNLOCK();
        if (!zpersona_load(&zp, g_root, zpet_character(g_pet), &d)) {
            send_text(fd, 500, "application/json",
                      "{\"ok\":false,\"error\":\"人设加载失败，看 logs/preview.log\"}");
            return;
        }
        n = zpersona_compose(&zp, tier, prompt, sizeof(prompt));
        zjson_escape(prompt, esc, sizeof(esc));
        {
            char en[128], ec[1536];
            zjson_escape(zp.nickname, en, sizeof(en));
            zjson_escape(zp.custom, ec, sizeof(ec));
            off = (int)z_snprintf(body, sizeof(body),
                   "{\"ok\":true,\"character\":\"%s\",\"name\":\"%s\",\"preset\":\"%s\","
                   "\"tier\":%d,\"meeting_todo\":%d,\"nickname\":\"%s\",\"custom\":\"%s\","
                   "\"prompt_bytes\":%u,\"prompt\":\"%s\",\"traits\":[",
                   zp.character, zp.name, zp.preset, tier, zpersona_meeting_todo(&zp),
                   en, ec, (unsigned)n, esc);
        }
        for (k = 0; k < zp.lib.ntraits && off < (int)sizeof(body) - 256; ++k)
            off += (int)z_snprintf(body + off, sizeof(body) - (size_t)off,
                       "%s{\"id\":\"%s\",\"name\":\"%s\",\"low\":\"%s\",\"high\":\"%s\",\"v\":%d}",
                       k ? "," : "", zp.lib.traits[k].id, zp.lib.traits[k].name,
                       zp.lib.traits[k].low, zp.lib.traits[k].high, zp.tv[k]);
        off += (int)z_snprintf(body + off, sizeof(body) - (size_t)off, "],\"presets\":[");
        for (k = 0; k < zp.lib.npresets && off < (int)sizeof(body) - 256; ++k)
            off += (int)z_snprintf(body + off, sizeof(body) - (size_t)off,
                       "%s{\"id\":\"%s\",\"name\":\"%s\"}",
                       k ? "," : "", zp.lib.presets[k].id, zp.lib.presets[k].name);
        z_snprintf(body + off, sizeof(body) - (size_t)off, "]}");
        send_text(fd, 200, "application/json", body);
        return;
    }
    if (strcmp(r->path, "/api/persona/set") == 0) {
        /* 白名单写入：k=<键> v=<值>。键不在 zpersona_set 的名单里一律 400。
           对话侧要改人设也只能走这里 —— 不开"模型直接写 json"的口子。 */
        char key[64], val[512];
        zpersona zp;
        zdiag d;
        char body2[256];

        if (!qstr(r, "k", key, sizeof(key))) {
            send_text(fd, 400, "application/json", "{\"ok\":false,\"error\":\"缺少 k\"}");
            return;
        }
        if (!qstr(r, "v", val, sizeof(val))) val[0] = '\0';
        zdiag_init(&d);
        if (!zpersona_load(&zp, g_root, zpet_character(g_pet), &d)) {
            send_text(fd, 500, "application/json", "{\"ok\":false,\"error\":\"人设加载失败\"}");
            return;
        }
        if (!zpersona_set(&zp, key, val)) {
            z_snprintf(body2, sizeof(body2),
                       "{\"ok\":false,\"error\":\"这个键不可改或值非法\",\"k\":\"%s\"}", key);
            send_text(fd, 400, "application/json", body2);
            return;
        }
        if (!zpersona_save(&zp, g_root)) {
            send_text(fd, 500, "application/json", "{\"ok\":false,\"error\":\"写回失败\"}");
            return;
        }
        z_snprintf(body2, sizeof(body2), "{\"ok\":true,\"k\":\"%s\",\"v\":\"%s\"}", key, val);
        send_text(fd, 200, "application/json", body2);
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
    if (strcmp(r->path, "/api/context.json") == 0) {
        /* T60.1 的验收物：**把上一次组装的上下文清单原样打印出来**。
         *
         * 为什么非要有这个端点：在它之前，"这次请求到底带了什么上去"
         * 没有任何人能回答 —— 人设拼一段、历史拼几轮，拼完就扔。
         * 出了问题（她为什么忘了刚才说的 / 她为什么突然不像她了）只能靠猜。
         *
         * 清单是纯文本、字段定长，所以**可以 diff** ——
         * 同一个问题在聊天区问和在工作区问，两张清单一比就知道差在哪。
         *
         *   reset=1   清空会话历史（"重新开始聊"）
         */
        static char body[8192];
        char manifest[4096], esc[6144];
        int i, n;
        int off;

        if (qint(r, "reset", 0)) {
            LOCK(); zctx_clear_turns(&g_ctx); UNLOCK();
        }
        LOCK();
        zctx_manifest(&g_ctx, manifest, sizeof(manifest));
        n = zctx_turn_count(&g_ctx);
        UNLOCK();

        zjson_escape(manifest, esc, sizeof(esc));
        off = (int)z_snprintf(body, sizeof(body),
            "{\"ok\":true,\"turns\":%d,\"budget\":%ld,\"tokens\":%ld,"
            "\"turns_sent\":%d,\"turns_dropped\":%d,\"turns_held\":%d,"
            "\"local\":%s,\"manifest\":\"%s\",\"blocks\":[",
            n, g_ctx.last_budget, g_ctx.last_tokens,
            g_ctx.last_turns_used, g_ctx.last_turns_dropped, g_ctx.last_turns_held,
            g_ctx.last_local ? "true" : "false", esc);
        LOCK();
        for (i = 0; i < zctx_block_count(&g_ctx); ++i) {
            const zctx_block *b = zctx_block_at(&g_ctx, i);
            char eb[256], et[128], es[256];
            if (!b) continue;
            zjson_escape(b->title, et, sizeof(et));
            zjson_escape(b->source, es, sizeof(es));
            zjson_escape(b->drop_reason, eb, sizeof(eb));
            off += (int)z_snprintf(body + off, sizeof(body) - (size_t)off,
                "%s{\"id\":\"%s\",\"title\":\"%s\",\"source\":\"%s\","
                "\"bytes\":%lu,\"tokens\":%ld,\"pinned\":%s,\"kept\":%s,"
                "\"drop_reason\":\"%s\"}",
                i ? "," : "", b->id, et, es, (unsigned long)b->len, b->tokens,
                b->pinned ? "true" : "false", b->kept ? "true" : "false", eb);
        }
        /* 会话历史也要能逐条看到 —— 只给个轮数等于没给。
           带隐私标记的轮次照样列出来，但标明它没上云：
           **藏起来和不告诉他没区别。** */
        off += (int)z_snprintf(body + off, sizeof(body) - (size_t)off,
                               "],\"history\":[");
        for (i = 0; i < n && off < (int)sizeof(body) - 512; ++i) {
            const zctx_turn *t = zctx_turn_at(&g_ctx, i);
            char etx[1024];
            if (!t) continue;
            zjson_escape(t->text, etx, sizeof(etx));
            off += (int)z_snprintf(body + off, sizeof(body) - (size_t)off,
                "%s{\"role\":\"%s\",\"sensitive\":%s,\"text\":\"%s\"}",
                i ? "," : "", t->role ? "assistant" : "user",
                t->sensitive ? "true" : "false", etx);
        }
        UNLOCK();
        z_snprintf(body + off, sizeof(body) - (size_t)off, "]}");
        send_text(fd, 200, "application/json", body);
        return;
    }

    if (strcmp(r->path, "/api/chat") == 0) {
        /* G54：真的把话发给模型。
         *
         * 在这之前，网关只会"选谁"——选完就没了下文，人设提示词一个字节都没出过门。
         * 这个端点把最后那一段接上：选路 → 取密钥 → 拼请求体 → 真发 HTTP → 记账。
         *
         *   text=      要说的话（必填）
         *   cap=       能力名，默认 chat.completion
         *   persona=0  不带人设（默认带：按当前角色和好感档合成的那段系统提示词，
         *              和 /api/persona.json 显示的完全是同一段）
         *   dry=1      只看不发：把目标地址和请求体原样给出来，一个字节都不出网
         *   tries=     失败后最多换几家（默认 1，即不降级）
         *   timeout=   毫秒，默认 30000
         *
         * 返回里总带 provider/model/local/reason —— 用户有权知道这句话是谁答的、
         * 为什么挑的它、有没有离开过这台机器。
         */
        /* 不能是 static：这个端点会在工作线程上跑，两个请求同时进来
           会把同一块缓冲区写花。16KB 放栈上没问题。 */
        char body[16384];
        char text[4096], cap_s[64], prompt[4096];
        char url[320] = "";
        char *reqbody = NULL;
        zrelay_chat_req q;
        zrelay_result res;
        zrelay_turn hist[ZCTX_MAX_TURNS];
        int nhist = 0;
        int dry = qint(r, "dry", 0);
        int want_persona = qint(r, "persona", 1);
        zthink_out think;                 /* 这一句的节奏（T69.1），响应里要带回去 */
        int rc, off;
        /* 她**自己**开口（T69.2）。self=1~4 是引擎给的方向（闲着想说话 / 想起一件事 /
           觉得对方不对 / 想分享），不是用户说的话 —— 所以：
             · text 可以为空，空的时候引擎自己写一行"这不是有人在跟你说话"的提示；
             · 这一轮**不记成用户的话**（否则历史里会多出一句谁也没说过的用户台词）；
             · 成功之后更新"她上次开口的时间"，冷却与"上一句没人接"都靠它。 */
        int self = qint(r, "self", 0);
        const char *self_cue =
            "（引擎提示：现在没有人在跟你说话，是你自己想开口。"
            "就照此刻的心情说一两句，别复述这句提示，别问「在吗」这种空话。）";

        if (self > 0) {
            char t[1024];
            const char *it = qstr(r, "text", t, sizeof(t)) ? t : "";
            if (!it[0]) {
                z_strlcpy(text, self_cue, sizeof(text));
            } else {
                /* 允许带上一句自己的由头（例如刚从记忆里想到的那件事） */
                z_snprintf(text, sizeof(text), "%s\n%s", self_cue, it);
            }
        } else if (!qstr(r, "text", text, sizeof(text)) || !text[0]) {
            send_text(fd, 400, "application/json",
                      "{\"ok\":false,\"error\":\"缺少 text（要说的话）\"}");
            return;
        }
        if (!g_gw_ok) {
            send_text(fd, 503, "application/json",
                      "{\"ok\":false,\"error\":\"路由表没加载成功，看 /api/gateway.json\"}");
            return;
        }
        if (!qstr(r, "cap", cap_s, sizeof(cap_s)) || !cap_s[0])
            z_strlcpy(cap_s, "chat.completion", sizeof(cap_s));

        prompt[0] = 0;
        if (want_persona) {
            zpersona zp;
            zdiag d;
            int tier;
            zdiag_init(&d);
            LOCK();
            tier = zpet_affection_tier(g_pet);
            UNLOCK();
            /* 人设加载不上不是致命错：没有人设也能聊，只是少了性格。
               但要让用户看见"这次没带人设"，所以下面照实报 persona_bytes=0。 */
            if (zpersona_load(&zp, g_root, zpet_character(g_pet), &d))
                zpersona_compose(&zp, tier, prompt, sizeof(prompt));
        }

        /* ---- 组装上下文（T60.1）----
           人设是 pinned 的（永不裁），会话历史按预算从最新往回收。
           组装结果既决定真正发什么，也决定 /api/context.json 打印什么 ——
           **同一次组装，两处共用**，否则清单会和实际出网的内容对不上。 */
        {
            int keep   = qint(r, "history", 1);        /* history=0 关掉多轮 */
            long budget = (long)qint(r, "budget", 2000);
            int tries  = qint(r, "tries", 1);
            int sens   = qint(r, "sensitive", 0) ? 1 : 0;
            int dest_local;

            /* 组装前要先知道目的地，否则没法判断"敏感的那几轮能不能跟着走"。
               选路本身是纯决策（不出网、不花钱），所以这里先问一遍网关。

               什么情况下才算**确定**留在本机：
                 ① 这次带了敏感标记 —— zrelay 保证它只会走本地（T61.7）；或
                 ② 首选就是本地，而且 tries=1（没有降级余地，目的地唯一）。
               只要存在"可能换一家"的空间，就按云端算、把敏感轮挡下。
               这不是保守过头：请求发出去就收不回来了。 */
            if (sens) {
                dest_local = 1;
            } else {
                zgw_status why;
                const zgw_route *first;
                AILOCK();
                first = zgw_pick(&g_gw, cap_s, 0, &why);
                AIUNLOCK();
                dest_local = (first && first->local && tries <= 1) ? 1 : 0;
            }

            /* 长记忆（T67.45）：在拿 AILOCK 之前算好，避免两把锁嵌套。
               ★ 分成两块，去向不同：
                 · memory_anchor —— 锚点，**pinned**：预算再紧也不许裁。
                   裁掉它就等于「四年后忘了第一天」，那正是这条路要防的事。
                 · memory_recall —— 这次想起来的相关旧事，可裁。
                   裁掉的只是「这次没想起来」，不是「她这个人」。 */
            mem_anchor[0] = mem_recall[0] = 0;
            self_block[0] = 0;
            /* ★ persona=0 是"完全裸跑"的对照档（冒烟里用它验证不带人设），
               那就连记忆也不许带 —— 否则"基线"里混进了她的过去，
               对照就失去意义了。 */
            if (g_mem && want_persona) {
                int64_t mt = (int64_t)time(NULL);
                LOCK();
                zmem_anchors_block(g_mem, mt, mem_anchor, sizeof mem_anchor);
                zmem_recall_related(g_mem, text, mt, mem_recall, sizeof mem_recall);
                UNLOCK();
            }

            AILOCK();
            zctx_set_block(&g_ctx, "persona", "角色设定",
                           prompt[0] ? "characters/<角色>/persona.json" : "(没带)",
                           prompt, 100, 1);
            /* ★ 必须**无条件**重写这两块：块是存在 g_ctx 上的，上一轮写进去的
               锚点不会自己消失。带 persona=0 跑基线时若沿用上一轮的块，
               "裸跑"里就会混进她的过去（冒烟正是这样抓到过一次）。
               空文本照样写，拼提示词那一步会跳过空块。 */
            zctx_set_block(&g_ctx, "memory_anchor", "长期记忆·她一直记得",
                           "data/<角色>/memory/chronicle.zm", mem_anchor, 95, 1);
            zctx_set_block(&g_ctx, "memory_recall", "长期记忆·这次想起来的",
                           "data/<角色>/memory/chronicle.zm", mem_recall, 60, 0);
            /* 主动开口的立场（T69.2）：同样走 zctx 的块，和记忆/人设一个口径 ——
               「这次为什么开口」在清单里看得见，不是藏在某个 if 里的隐形提示。 */
            if (self > 0) {
                static const char *SELF_TITLE = "现在是你自己想开口";
                const char *want = "你单纯想跟他说句话。可以很小、很没目的：一句抱怨、一句想到的事、一个刚冒出来的念头。";
                if (self == 2) want = "你想起了一件跟他有关的事。只许说**记忆里真的有的**事；想不起来就别装作想起来。";
                else if (self == 3) want = "你隐约觉得他这会儿状态不太对。先关心，别追问，也别讲道理。";
                else if (self == 4) want = "你想分享一个你正在想的东西（画面、念头、手上在做的事）。";
                z_snprintf(self_block, sizeof self_block,
                           "%s\n说话规矩：一到两句，像突然开口的真人；不用「在吗」「你好」开头；"
                           "不解释自己是 AI；不要每句都以提问结尾（那会变成在盘问他）。",
                           want);
                zctx_set_block(&g_ctx, "self_talk", SELF_TITLE,
                               "引擎判定：她想开口（urge 过阈值）", self_block, 98, 1);
            } else {
                zctx_set_block(&g_ctx, "self_talk", "现在是你自己想开口", "", "", 0, 0);
            }
            if (!keep) zctx_clear_turns(&g_ctx);
            zctx_build(&g_ctx, cap_s, budget, dest_local);
            AIUNLOCK();
        }

        /* 系统提示词 = 清单判定"要带上"的那几块，按注册顺序拼。
           人设块照旧放最前（它是身份），其余块各带一行标题。 */
        sysbuf[0] = 0;
        AILOCK();
        {
            size_t off = 0;
            int bi;
            for (bi = 0; bi < zctx_block_count(&g_ctx) && off + 8 < sizeof sysbuf; ++bi) {
                const zctx_block *b = zctx_block_at(&g_ctx, bi);
                size_t n;
                if (!b || !b->kept || !b->text || !b->text[0]) continue;
                if (strcmp(b->id, "persona") == 0) {
                    n = (size_t)z_snprintf(sysbuf + off, sizeof sysbuf - off, "%s\n", b->text);
                } else {
                    n = (size_t)z_snprintf(sysbuf + off, sizeof sysbuf - off,
                                           "【%s】\n%s\n", b->title, b->text);
                }
                if (off + n >= sizeof sysbuf) { sysbuf[off] = 0; break; }
                off += n;
            }
        }
        AIUNLOCK();

        memset(&q, 0, sizeof(q));
        q.cap = cap_s;
        q.system_prompt = sysbuf[0] ? sysbuf
                        : (prompt[0] ? prompt : NULL);
        q.user_text = text;
        /* 把组装结果摊成 zrelay 要的数组。注意只取 zctx 判定"要带上"的那几轮 ——
           清单上写带了几轮，这里就必须是几轮，两边同源。 */
        AILOCK();
        {
            int i;
            nhist = zctx_kept_turn_count(&g_ctx);
            if (nhist > (int)(sizeof(hist) / sizeof(hist[0])))
                nhist = (int)(sizeof(hist) / sizeof(hist[0]));
            for (i = 0; i < nhist; ++i) {
                const zctx_turn *t = zctx_kept_turn_at(&g_ctx, i);
                hist[i].role = t ? t->role : 0;
                hist[i].text = t ? t->text : "";
            }
            q.history = nhist > 0 ? hist : NULL;
            q.nhistory = nhist;
        }
        AIUNLOCK();
        /* 她的节奏（T69.1）：这一句是多快说出来的，由引擎判，用户没有开关。
           ★ 预算也由这里给：脱口而出就该短（90 token），认真想才给到 320。
             显式传了 max_tokens 就听用户的（调试/测试要用）。 */
        {
            zthink_in tin;
            time_t nowt = time(NULL);
            struct tm lt;
            memset(&tin, 0, sizeof tin);
            memset(&think, 0, sizeof think);
            /* 她自己开口时判节奏要看"她要说的话"，而不是引擎塞进去的那行提示 ——
               按提示判会把 100 多字的提示算成"长句"，凭空多出 0.52 分。 */
            tin.text = (self > 0) ? "" : text;
            tin.tier = g_pet ? zpet_affection_tier(g_pet) : 0;
            tin.mood = 0.6;
            localtime_r(&nowt, &lt);
            tin.hour = qint(r, "hour", lt.tm_hour);
            tin.since_last_ms = (int64_t)((pet_now() - g_self_spoke_at) * 1000.0);
            tin.had_topic = 0;
            zthink_decide(&g_think, &tin, &think);
            /* 对方开口了 —— 她自提的话题就不再是"没人接" */
            g_self_topic_open = 0;
        }
        q.temperature = -1.0;                 /* 没填就不往请求体里塞，别覆盖服务端配置 */
        q.max_tokens = qint(r, "max_tokens", think.max_tokens);
        q.timeout_ms = qint(r, "timeout", 30000);
        q.max_attempts = qint(r, "tries", 1);
        q.route.sensitive = qint(r, "sensitive", 0) ? 1 : 0;
        q.route.tokens_est = (long)(strlen(text) / 4 + strlen(prompt) / 4);
        q.route.local_load_pct = qint(r, "load", -1);
        q.route.cloud_down = qint(r, "cloud_down", 0) ? 1 : 0;
        q.route.task = zgw_classify(text, NULL);

        /* 这一段会卡住整个网络往返（本地大模型想 10~30 秒是常事）。
           攥的是 g_ai_lock 不是 g_lock —— 渲染线程要的是后者，
           所以她在等回复的时候照样会呼吸、会眨眼、会摇尾巴。 */
        AILOCK();
        if (dry)
            rc = zrelay_dry_run(&g_gw, &q, url, sizeof(url), &reqbody, &res);
        else
            rc = zrelay_chat(&g_gw, &q, &res);

        /* 只有真发且真拿到回复，才把这一来一回记进历史。
           dry-run 不记（它什么都没发生）；失败也不记 ——
           把一句没人回答的话留在历史里，下一轮模型会以为自己当时没理人。 */
        if (!dry && rc == 0 && res.ok) {
            /* 这一轮算不算敏感，不只看用户有没有勾选。
               实测发现的洞：上一轮是敏感的、这一轮把它当上下文发了过去，
               模型的回复里就可能**原样引用**那段敏感内容 ——
               如果把回复记成"不敏感"，它下次就能大摇大摆跟着上云。
               所以：只要这次请求带上了任何一条敏感历史，回复就一起算敏感。 */
            int tainted = q.route.sensitive;
            int k;
            for (k = 0; !tainted && k < nhist; ++k) {
                const zctx_turn *kt = zctx_kept_turn_at(&g_ctx, k);
                if (kt && kt->sensitive) tainted = 1;
            }
            /* 她自己开口那一轮**不记用户的话** —— text 里装的是引擎提示，
               记进去就等于历史里多了一句谁也没说过的用户台词，
               下一轮模型会以为"用户让我自己想点话说"。 */
            if (self <= 0) zctx_push_turn(&g_ctx, 0, text, q.route.sensitive);
            zctx_push_turn(&g_ctx, 1, res.text ? res.text : "", tainted);
        }
        AIUNLOCK();
        /* 她开口了：冷却从现在算起，并且"她自己提的话题"进入没人接的状态。
           这两个量都只在这里改（还有一个是 /api/urge/spoke，前端主动上报）。 */
        if (self > 0 && !dry && rc == 0 && res.ok) {
            g_self_spoke_at = pet_now();
            g_self_topic_open = 1;
        }

        {
            char esc_err[768], esc_txt[8192];
            zjson_escape(res.err, esc_err, sizeof(esc_err));
            zjson_escape(res.text ? res.text : "", esc_txt, sizeof(esc_txt));
            off = (int)z_snprintf(body, sizeof(body),
                "{\"ok\":%s,\"dry\":%s,\"cap\":\"%s\",\"provider\":\"%s\",\"model\":\"%s\","
                "\"local\":%s,\"reason\":\"%s\",\"http_status\":%d,\"attempts\":%d,"
                "\"tokens_in\":%ld,\"tokens_out\":%ld,\"cost\":%.6f,"
                "\"persona_bytes\":%u,\"history_sent\":%d,\"turns_total\":%d,"
                "\"turns_held\":%d,\"self\":%d,\"text\":\"%s\",\"error\":\"%s\"",
                (rc == 0 && res.ok) ? "true" : "false", dry ? "true" : "false",
                cap_s, res.provider, res.model, res.local ? "true" : "false",
                res.reason, res.http_status, res.attempts,
                res.tokens_in, res.tokens_out, res.cost,
                (unsigned)strlen(prompt), nhist, zctx_turn_count(&g_ctx),
                g_ctx.last_turns_held, self, esc_txt, esc_err);
            if (dry) {
                /* 把真会发出去的那段原样摆出来。密钥不在里面（zrelay_dry_run 保证）。 */
                char esc_url[640], esc_body[6144];
                zjson_escape(url, esc_url, sizeof(esc_url));
                zjson_escape(reqbody ? reqbody : "", esc_body, sizeof(esc_body));
                off += (int)z_snprintf(body + off, sizeof(body) - (size_t)off,
                           ",\"url\":\"%s\",\"request_body\":\"%s\"", esc_url, esc_body);
            }
            {
                /* 她"多快说的"要一起回去：前端靠这两个字段决定先放哪句、停多久。
                   没有它们，"脱口而出"在界面上就退化成了"一样地等一下"。 */
                char escpre[160], escwhy[512];
                zjson_escape(think.preface, escpre, sizeof escpre);
                zjson_escape(think.why, escwhy, sizeof escwhy);
                off += (int)z_snprintf(body + off, sizeof(body) - (size_t)off,
                    ",\"think\":{\"mode\":\"%s\",\"delay_ms\":%d,\"preface\":\"%s\","
                    "\"max_tokens\":%d,\"needs_memory\":%s,\"score\":%.3f,\"why\":\"%s\"}",
                    zthink_mode_id(think.mode), think.delay_ms, escpre,
                    think.max_tokens, think.needs_memory ? "true" : "false",
                    think.score, escwhy);
            }
            z_snprintf(body + off, sizeof(body) - (size_t)off, "}");
        }
        {
            /* 成败在释放之前先存下来，别在 free 之后还去读 res —— 今天的
               zrelay_result_free 只动 text，但靠"它现在只动 text"写代码是埋雷。 */
            int good = (rc == 0 && res.ok);
            free(reqbody);
            if (!dry) zrelay_result_free(&res);
            /* HTTP 码照实说：200 = 真答上了；502 = 上游没答上（原因在 error 里）。
               不把上游的失败伪装成 200，否则前端只能靠猜。 */
            send_text(fd, good ? 200 : 502, "application/json", body);
        }
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
    if (strcmp(r->path, "/api/partmesh.json") == 0) {
        /* 探针：一个部件这一帧**实际画出去**的网格顶点位移（源图像素）。
           id=<部件 id>，可选 max=<取前几个点，默认 64>。
           为什么非有不可：T66.10/T66.10b 的继承是**逐顶点**的，形变器的驱动量
           （/api/info.json 的 deformers）根本看不出继承有没有生效 ——
           里布现在自己一张网格都没有，全靠继承表布，只读驱动量会永远是 0。 */
        char id[64];
        /* 16×16 网格是引擎上限（zrig.c 里 cols/rows 都 <= 16）⇒ 17×17 个点 */
        double dx[289], dy[289];
        int cols = 0, rows = 0, np = 0, i, cap = 64;
        char body[8192];
        size_t off = 0;
        if (!qstr(r, "id", id, sizeof(id))) {
            send_text(fd, 400, "application/json", "{\"ok\":false,\"error\":\"缺少 id\"}");
            return;
        }
        if (qint(r, "max", 0) > 0) cap = qint(r, "max", 0);
        if (cap > 289) cap = 289;
        LOCK();
        np = zpet_part_mesh(g_pet, id, &cols, &rows, dx, dy, cap);
        UNLOCK();
        off += (size_t)z_snprintf(body + off, sizeof(body) - off,
            "{\"ok\":true,\"id\":\"%s\",\"cols\":%d,\"rows\":%d,\"n\":%d,\"dx\":[",
            id, cols, rows, np);
        for (i = 0; i < np && i < cap; ++i)
            off += (size_t)z_snprintf(body + off, sizeof(body) - off,
                                      "%s%.4f", i ? "," : "", dx[i]);
        off += (size_t)z_snprintf(body + off, sizeof(body) - off, "],\"dy\":[");
        for (i = 0; i < np && i < cap; ++i)
            off += (size_t)z_snprintf(body + off, sizeof(body) - off,
                                      "%s%.4f", i ? "," : "", dy[i]);
        z_snprintf(body + off, sizeof(body) - off, "]}");
        send_text(fd, 200, "application/json", body);
        return;
    }
    if (strcmp(r->path, "/api/vertex.json") == 0) {
        /* 探针：部件网格的某个控制点这一帧落在画面哪里（T66.9c 加，T66.14 的工具要用）。
           id=<部件>，c=<列>，row=<行>，scale=<默认 1>。
           和 /api/partmesh.json 的分工：那个给"位移场"（源图像素），
           这个给"落点"（帧缓冲坐标，含组、链、逐顶点加权刚体）。
           加权刚体到底有没有把裙腰按住，只有落点能量出来。 */
        char id[64], body[512];
        double xy[2] = {0, 0};
        int c = qint(r, "c", 0), row = qint(r, "row", 0);
        double sc = qint(r, "scale", 1) > 0 ? (double)qint(r, "scale", 1) : 1.0;
        int ok = 0;
        if (!qstr(r, "id", id, sizeof(id))) {
            send_text(fd, 400, "application/json", "{\"ok\":false,\"error\":\"缺少 id\"}");
            return;
        }
        LOCK();
        ok = zpet_part_vertex(g_pet, id, sc, c, row, xy);
        UNLOCK();
        z_snprintf(body, sizeof(body),
                   "{\"ok\":%s,\"id\":\"%s\",\"c\":%d,\"row\":%d,\"scale\":%.2f,"
                   "\"x\":%.3f,\"y\":%.3f}",
                   ok ? "true" : "false", id, c, row, sc, xy[0], xy[1]);
        send_text(fd, ok ? 200 : 404, "application/json", body);
        return;
    }
    if (strcmp(r->path, "/api/sockets.json") == 0) {
        /* 挂点探针（T66.19 / S4）。两个数各回答一个问题：
             pos    —— 骨架把挂点摆在哪（画布像素）；
             screen —— 过完父骨矩阵之后它**这一刻**在哪（画布像素 × 当前缩放）。
           配件"跟着手腕动"能不能机检，就看 screen 在抬手之后有没有跟着走。
           模组要做的事因此变成：一张 PNG + 一个挂点名，不需要知道画布多大。 */
        char body[4096];
        size_t off = 0;
        int n, i;
        LOCK();
        n = zpet_socket_count(g_pet);
        off += (size_t)z_snprintf(body + off, sizeof(body) - off,
                                  "{\"ok\":true,\"n\":%d,\"sockets\":[", n);
        for (i = 0; i < n; ++i) {
            const char *sid = "", *sgrp = "";
            double pos[2] = {0, 0}, scr[2] = {0, 0};
            zpet_socket_get(g_pet, i, &sid, &sgrp, pos, scr);
            off += (size_t)z_snprintf(body + off, sizeof(body) - off,
                "%s{\"id\":\"%s\",\"group\":\"%s\",\"pos\":[%.1f,%.1f],"
                "\"screen\":[%.2f,%.2f]}",
                i ? "," : "", sid, sgrp, pos[0], pos[1], scr[0], scr[1]);
        }
        UNLOCK();
        z_snprintf(body + off, sizeof(body) - off, "]}");
        send_text(fd, 200, "application/json", body);
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
            g_freeze_t = has_t ? tq : pet_now();   /* 冻结在**引擎时钟**上，别用裸真实钟 */
            g_frozen = 1;
        }
        else if (!on) {
            /* 解冻：虚拟时间要是已经跑到真实时钟前面（/api/step 空跑的产物），
               把超前的量记进偏移，引擎时钟接着往前走，绝不后退。 */
            double real = z_now_seconds() + g_time_off;
            if (g_frozen && g_freeze_t > real) g_time_off += g_freeze_t - real;
            g_frozen = 0;
        }
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
    /* ★ 2026-10-24（第六十一问）：换形态 / 换装失败**不许再回 {"ok":true}**。
       原来无论 zpet_set_form 成功还是失败都回同一个 200，于是"Q 版整个 rig 被
       引擎拒载"这件事在接口层面完全看不见 —— 点一下按钮，界面刷新，还是原来
       那张脸，没有任何提示。用户看到的现象是"切不过去"，日志里才有真因。
       失败时必须把**文件 + 字段 + 原因**原样交给界面（这是项目一贯的配置错误口径：
       能定位、不崩溃、不静默）。成功时把最终形态一并回过去，前端不用再猜。 */
    if (strcmp(r->path, "/api/form") == 0) {
        char id[64];
        if (!qstr(r, "id", id, sizeof(id)))
            { send_text(fd, 400, "application/json",
                        "{\"ok\":false,\"error\":\"缺少 id\"}"); return; }
        zdiag d;
        zdiag_init(&d);
        int rc;
        LOCK();
        rc = zpet_set_form(g_pet, id, &d);
        UNLOCK();
        if (rc != 0) {
            zdiag_print(&d, stderr);
            send_diag_json(fd, "换形态失败", id, zpet_form(g_pet), &d);
            return;
        }
        char body[256];
        z_snprintf(body, sizeof(body),
                   "{\"ok\":true,\"form\":\"%s\",\"warnings\":%d}",
                   zpet_form(g_pet) ? zpet_form(g_pet) : id, d.count);
        send_text(fd, 200, "application/json", body);
        return;
    }
    if (strcmp(r->path, "/api/outfit") == 0) {
        char id[64];
        if (!qstr(r, "id", id, sizeof(id)))
            { send_text(fd, 400, "application/json",
                        "{\"ok\":false,\"error\":\"缺少 id\"}"); return; }
        zdiag d;
        zdiag_init(&d);
        int rc;
        LOCK();
        rc = zpet_set_outfit(g_pet, id, &d);
        UNLOCK();
        if (rc != 0) {
            zdiag_print(&d, stderr);
            send_diag_json(fd, "换装失败", id, zpet_outfit(g_pet), &d);
            return;
        }
        char body[256];
        z_snprintf(body, sizeof(body),
                   "{\"ok\":true,\"outfit\":\"%s\"}",
                   zpet_outfit(g_pet) ? zpet_outfit(g_pet) : id);
        send_text(fd, 200, "application/json", body);
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
    g_self_spoke_at = pet_now();
    /* 她的节奏参数（T69.1）。缺文件是合法状态 —— 走缺省值，绝不因为
       没导出过 mind.params.json 就起不来。 */
    zthink_profile_load(&g_think, g_cfg.root_dir, zpet_character(g_pet));
    ZLOGI("think", "节奏参数：%s（快%.2f 努力%.2f 外显%.2f 主动%.2f 好奇%.2f）",
          g_think.ok ? "已读 mind.params.json" : "缺文件，走缺省",
          g_think.pace_fast, g_think.effort, g_think.express,
          g_think.proactive, g_think.curiosity);

    /* 长记忆线：四年后还认得你的物理前提就是它。
       ★ 打不开**不阻塞启动**（记忆只是失忆，不是死机），但一定要在
         /api/memory.json 里如实报 open:false —— 悄悄失忆比崩溃更糟。 */
    {
        zdiag md;
        zdiag_init(&md);
        g_mem = zmem_open(g_cfg.root_dir, zpet_character(g_pet), &md);
        if (!g_mem) {
            ZLOGW("memory", "长记忆打不开，本次不记也不回忆（见 /api/memory.json）");
            zdiag_print(&md, stderr);
        } else {
            zmem_stat st;
            char a[24], b[24];
            zmem_stats(g_mem, &st);
            zmem_date_text(st.oldest, a, sizeof a);
            zmem_date_text(st.newest, b, sizeof b);
            /* ★ 首次启动写一条锚点。这是**真实发生的事**（引擎知道今天是什么日子），
               不是编的剧情。once 键保证这辈子只写一次 —— 四年后她提起"那天你把我
               放到桌面上"，日期是真的。 */
            zmem_add(g_mem, (int64_t)time(NULL), ZMEM_ANCHOR, 9,
                     "第一次见面：这一天，你把我放到了你的桌面上。", "first-launch");
            zmem_stats(g_mem, &st);
            zmem_date_text(st.oldest, a, sizeof a);
            zmem_date_text(st.newest, b, sizeof b);
            ZLOGI("memory", "长记忆 %d 条（锚点 %d、墓碑 %d、自述 %d 版），%s ~ %s，%ld 字节",
                  st.items, st.anchors, st.deleted, st.stories,
                  st.items ? a : "-", st.items ? b : "-", st.bytes);
        }
    }

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
    InitializeCriticalSection(&g_ai_lock);
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
                            /* 慢端点交给工作线程，别把 accept 循环和
                               zpet_tick 一起拖住 —— 她得继续动。 */
                            if (dispatch_slow(cfd, &req)) {
                                cfd = ZSOCK_INVALID;   /* 线程接管了，这儿不许再 close */
                            } else {
                                handle_request(cfd, &req);
                            }
                        }
                    }
                }
                if (cfd != ZSOCK_INVALID) zsock_close(cfd);
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
