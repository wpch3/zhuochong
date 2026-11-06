/* zrelay —— 第一条真链路：把网关的决策真正发出去（G54）
 *
 * 在这之前，zgateway 只会"选谁 / 花多少 / 钥匙在哪"，一个字节都没发过网。
 * 人设（zpersona）组装好的提示词也没有任何地方真的用过它。
 * 这个模块就是把那段断头路接上：
 *
 *     zgw_route_for  选一家
 *          ↓
 *     zgw_endpoint_find  查它的地址和鉴权方式
 *          ↓
 *     zgw_secret_resolve 取密钥（取不到就**不发**）
 *          ↓
 *     zgw_hold_open      预扣额度
 *          ↓
 *     zhttp_send         真的发出去
 *          ↓
 *     解析回复 + usage
 *          ↓
 *     zgw_hold_settle / zgw_hold_release
 *
 * 分层的理由和 zgateway 一样：这一层也不认识角色、不认识动作。
 * 它只认识"一段系统提示词 + 一句用户的话 → 一段回复 + 用了多少 token"。
 *
 * ★ 本版只接 openai_compatible 这一族（29 家里的 16 家，含全部本地模型）。
 *   anthropic 的 /messages 是另一套请求体，kind 对不上会明确报错，
 *   不会硬拿 openai 的格式去发 —— 发出去也是 400，还白扣一次额度。
 *
 * ★ 云端目前连不上，因为它们全是 https 而 zhttp 还没有 TLS（见 zhttp.h）。
 *   这不是本模块的 bug，错误会原样透出来（"还没有接 TLS"），不会假装成功。
 */
#ifndef ZRELAY_H
#define ZRELAY_H

#include "zgateway.h"

/* 历史里的一轮。role：0 = 用户说的，1 = 她说的。
   这些会作为独立的 message 进 messages 数组 —— **不许塞进 system 提示词里**：
   模型靠 role 区分"谁说的"，糊成一段之后它分不清哪句是自己说过的。 */
typedef struct {
    int         role;
    const char *text;
} zrelay_turn;

typedef struct {
    const char *cap;            /* NULL = "chat.completion" */
    const char *system_prompt;  /* 可为 NULL；一般是 zpersona_compose 的产物 */
    const char *user_text;      /* 用户说的话，必填 */
    const zrelay_turn *history; /* 之前几轮，按时间顺序；可为 NULL */
    int         nhistory;
    double      temperature;    /* <0 = 不带这个字段，用服务端默认 */
    int         max_tokens;     /* <=0 = 不带 */
    int         timeout_ms;     /* <=0 = 30000 */
    int         max_attempts;   /* 失败后最多换几家，<=0 当 1（不降级） */
    zgw_req     route;          /* 敏感 / 预估 token / 本地负载 / 任务类型 */
} zrelay_chat_req;

typedef struct {
    int    ok;                  /* 1 = 拿到回复 */
    char   provider[48];
    char   model[64];
    char   reason[40];          /* 路由理由的人话名 */
    int    local;
    int    http_status;         /* 0 = 根本没发出去 */
    long   tokens_in, tokens_out;
    double cost;
    int    attempts;            /* 一共试了几家 */
    char  *text;                /* 回复正文；用完 zrelay_result_free */
    char   err[320];            /* 失败原因（人话）。ok=1 时为空串 */
} zrelay_result;

/* 发一次对话。返回 0 = 成功，非 0 = 失败（细节看 out->err）。
 * 不管成功失败，out 都会被填满，可以直接拿去展示/记账。 */
int  zrelay_chat(zgateway *g, const zrelay_chat_req *in, zrelay_result *out);
/* 空转一遍：选路 → 查接入点 → 校接口族 → 拼 URL 和请求体，**但一个字节都不发**。
 *
 * 面板上的"看看将要发什么"用的就是它。和真发共用 prepare_one，所以显示的
 * 就是真会出网的那段字节 —— 不是另写一份好看的示意。
 *   url      ：出参，目标地址（不含密钥）
 *   body_out ：出参，请求体，调用方 free()
 *   out      ：provider/model/local/reason 照常填；http_status 恒为 0
 * 返回 0 = 准备成功。注意：**密钥不会出现在任何出参里**。
 */
int zrelay_dry_run(zgateway *g, const zrelay_chat_req *in,
                   char *url, size_t url_cap, char **body_out,
                   zrelay_result *out);

void zrelay_result_free(zrelay_result *r);

/* 单独导出给单测：把 openai_compatible 的请求体拼出来。
 * 返回 malloc 的串，调用方 free。拼错请求体是这一层最容易犯的错，
 * 而且错了只会收到对面一个 400，看不出哪里错 —— 所以它必须能单独测。 */
char *zrelay_build_chat_body(const char *model, const char *system_prompt,
                             const char *user_text, double temperature,
                             int max_tokens);

/* 带历史的版本。上面那个等价于 nhistory=0，留着是为了不动既有调用方。 */
char *zrelay_build_chat_body_multi(const char *model, const char *system_prompt,
                                   const zrelay_turn *history, int nhistory,
                                   const char *user_text, double temperature,
                                   int max_tokens);

/* 单独导出给单测：从 openai_compatible 的响应体里取回复正文和 usage。
 * 返回 0 = 成功。失败时把人话原因写进 err。
 * *text 是 malloc 的，调用方 free。 */
int zrelay_parse_chat_resp(const char *body, char **text,
                           long *tokens_in, long *tokens_out,
                           char *err, size_t errcap);

#endif /* ZRELAY_H */
