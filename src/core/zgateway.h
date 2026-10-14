/* zgateway —— 平台网关（G51）
 *
 * 职责只有四件，都是纯决策，不碰网络：
 *   1. 路由：给一个能力 id，挑出该用哪个供应商（失败能往下降级重试）
 *   2. 估价：按路由里的定价算这次大概花多少
 *   3. 记账：预扣 → 结算 / 退还（照 one-api relay/billing 的三段式）
 *   4. 密钥：把 secret:// 引用解析成真实密钥，解析不出来必须失败
 *
 * 真正把请求发出去是 G54 的事。把"选谁 / 花多少 / 钥匙在哪"和"怎么发"分开，
 * 是因为前者能在没有任何网络、没有任何密钥的机器上完整测试。
 *
 * 路由表不是在这里现算的，是 tools/check_platform.py 从 config/providers/ 下的契约
 * 预先物化成 config/gateway_routes.json（照 one-api 的 Ability 表做法），
 * 顺序即优先级。运行时不该每次请求都去遍历契约目录。
 */
#ifndef ZGATEWAY_H
#define ZGATEWAY_H

#include <stddef.h>
#include "zc.h"

#define ZGW_MAX_ROUTES 64
#define ZGW_MAX_HOLDS  16

/* 一条路由 = 某个供应商能提供某种能力 */
typedef struct {
    char   cap[48];       /* 能力 id，如 chat.completion */
    char   provider[48];  /* 供应商 id */
    char   model[64];     /* 该供应商下的模型名 */
    int    priority;      /* 越大越优先 */
    int    local;         /* 本机服务（不出网、不花钱） */
    int    enabled;       /* 用户有没有打开它 */
    int    is_free;       /* 定价声明为免费 */
    double price_in;      /* 输入单价 */
    double price_out;     /* 输出单价 */
    double price_per;     /* 单价对应的计量单位数，如 1000000 token */
} zgw_route;

/* 路由失败的原因要分得清，因为给用户的提示完全不同 */
typedef enum {
    ZGW_OK = 0,
    ZGW_NO_SUCH_CAP,    /* 压根没有供应商声明过这个能力 → 功能没接入 */
    ZGW_ALL_DISABLED,   /* 有供应商但全被关掉了 → 让用户去设置里打开 */
    ZGW_EXHAUSTED,      /* 候选都试完了 → 重试到头了 */
    ZGW_SENSITIVE_NO_LOCAL /* 带隐私标记但本机没有可用模型 → 拒绝，不上云 */
} zgw_status;

/* ---- 本地↔云端双路由（DC18 三支柱：敏感 → 复杂/长 → 忙或故障互相兜底）----
 *
 * 为什么不直接用 zgw_pick：zgw_pick 只认"优先级 + 开没开"，它回答不了
 * "这条请求带隐私标记"或"本地显卡正忙"。但两者不是替代关系 ——
 * zgw_route_for 做完方向判断之后，仍然是在同一张路由表里按优先级挑。
 *
 * 这里的阈值全是**抄来的**（见 docs/REFERENCE_NOTES 第二十批），
 * 必须用自己的记账数据重标 —— 所以每次决策都记一笔，见 zgw_local_share()。
 */
typedef struct {
    long tokens_cloud;    /* prompt+预期回复 超过它 → 倾向云端（默认 512） */
    int  local_busy_pct;  /* 本地负载 ≥ 它 → 溢出到云端（默认 85） */
    int  sensitive_local_only; /* 敏感数据只许本地；本地不可用就失败（默认 1） */
} zgw_rules;

typedef enum {
    ZGW_TASK_SIMPLE = 0,  /* 分类 / 抽取 / 格式化 / 简单问答 */
    ZGW_TASK_HEAVY  = 1   /* 推理 / 写代码 / 工具调用 / 长文 */
} zgw_task;

/* 一次请求的上下文。local_load_pct 填 -1 表示"不知道"。 */
typedef struct {
    int      sensitive;       /* 带 PII / 隐私标记 */
    long     tokens_est;      /* 预估 token 数 */
    int      local_load_pct;  /* 0~100，-1 未知 */
    int      cloud_down;      /* 云端不可用 / 限流余量耗尽 */
    zgw_task task;
} zgw_req;

/* 为什么这么选 —— 给用户看的人话理由，也是调阈值时的统计维度 */
typedef enum {
    ZGW_R_DEFAULT_LOCAL = 0,   /* 没有任何理由上云，默认留本地 */
    ZGW_R_SENSITIVE_LOCAL,     /* 带隐私标记，强制本地 */
    ZGW_R_LONG_CLOUD,          /* 超过 token 阈值 */
    ZGW_R_HEAVY_CLOUD,         /* 任务类型属重活 */
    ZGW_R_LOCAL_BUSY,          /* 本地忙，溢出 */
    ZGW_R_CLOUD_DOWN,          /* 本想上云，云端不可用，退回本地 */
    ZGW_R_ONLY_CHOICE,         /* 想要的那边没有候选，只剩另一边 */
    ZGW_R_SENSITIVE_BLOCKED,   /* 敏感 + 本地不可用 = 拒绝，绝不偷偷上云 */
    ZGW_R_COUNT
} zgw_reason;

/* 一笔预扣。请求发出前占住额度，回来后结算或退还。 */
typedef struct {
    long   id;            /* 0 表示这个槽位空着 */
    char   cap[48];
    char   provider[48];
    double estimated;     /* 预扣了多少 */
} zgw_hold;

typedef struct {
    zgw_route routes[ZGW_MAX_ROUTES];
    int       nroutes;
    char      strategy[24];   /* prefer_local / cheapest / priority */
    int       fallback;       /* 失败了允不允许换下一家 */

    zgw_rules rules;          /* 双路由阈值 */
    long      reason_hits[ZGW_R_COUNT]; /* 每种理由命中几次（调阈值用） */
    long      picks_local;    /* 决策落到本地几次 */
    long      picks_cloud;    /* 决策落到云端几次 */

    zgw_hold  holds[ZGW_MAX_HOLDS];
    int       nholds;
    long      next_hold_id;

    /* 本地账本累计量：balance.mode = ledger 的供应商靠它显示余额 */
    double    spent_total;
    long      tokens_in_total;
    long      tokens_out_total;
    long      calls_total;
    long      failed_total;
} zgateway;

const char *zgw_reason_name(zgw_reason r);

/* 按文本内容判这是不是"重活"（推理 / 写代码 / 工具调用 / 长文）。
 *
 * 为什么是关键词而不是模型：调研里这条写得很死 ——
 * **路由器本身必须 <1ms，不能为了决定路由再调一次 LLM**，那样延迟预算直接爆掉。
 * 代价是关键词表必然有漏判（见 DECISIONS DC27 的复查触发）：
 * 漏判的后果是"本该上云的留在了本地"，用户看到的是答得差，不是答不出来 ——
 * 这个方向的错误比反过来便宜，所以表宁可保守。
 *
 * hit 不为 NULL 时写回命中的那个词（指向静态串），给界面解释用。 */
zgw_task zgw_classify(const char *text, const char **hit);

/* 按三支柱挑路由。g 非 const 是因为每次决策都要记账。
 * 返回 NULL 时 why 给出原因；敏感请求在本地不可用时返回
 * ZGW_SENSITIVE_NO_LOCAL —— **不会**退而求其次去云端。 */
const zgw_route *zgw_route_for(zgateway *g, const char *cap, const zgw_req *req,
                               zgw_status *why, zgw_reason *reason);

/* 本地分流占比（0~1）。调研给的目标区间是 0.70~0.85；
 * 长期偏离说明阈值不对，而不是说明用户变了。没决策过返回 -1。 */
double zgw_local_share(const zgateway *g);

/* 读取 config/gateway_routes.json。成功返回 0。 */
int zgw_load(zgateway *g, const char *routes_path, zdiag *d);

/* 挑一条路由。attempt=0 要首选，1、2… 是重试时依次降级。
 * 挑不到返回 NULL，并把原因写进 why（why 可为 NULL）。
 * 只会挑 enabled 的；fallback 关掉时 attempt>0 一律返回 NULL。 */
const zgw_route *zgw_pick(const zgateway *g, const char *cap, int attempt, zgw_status *why);

/* 某个能力一共有几个可用候选（enabled 的） */
int zgw_candidate_count(const zgateway *g, const char *cap);

/* 估价：本机和免费的恒为 0。price_per 为 0 时按"按次计价"处理。 */
double zgw_estimate(const zgw_route *r, long tokens_in, long tokens_out);

/* 记账三段。hold 返回 >0 的单号，满了返回 0。 */
long zgw_hold_open(zgateway *g, const char *cap, const char *provider, double estimated);
/* 结算：按实际用量入账，预扣槽位释放。找不到单号返回 -1。 */
int  zgw_hold_settle(zgateway *g, long hold_id, long tokens_in, long tokens_out, double actual);
/* 退还：请求失败时把预扣原样放掉，不计入花费，但计一次失败。 */
int  zgw_hold_release(zgateway *g, long hold_id);
/* 还没结算的预扣总额——它和 spent_total 是两笔账，不能混。 */
double zgw_held_amount(const zgateway *g);

/* 把 secret://name 解析成真实密钥，读环境变量 ZHUOCHONG_SECRET_<NAME>（大写）。
 * 成功返回 0；失败返回非 0，并把人话原因写进 *err（指向静态串）。
 * 解析不出来绝不能返回空串当成功——那会让程序拿着空密钥去发请求。 */
int zgw_secret_resolve(const char *ref, char *out, size_t cap, const char **err);

#endif /* ZGATEWAY_H */
