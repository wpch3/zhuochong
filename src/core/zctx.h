/* zctx —— 统一上下文管理器（T60.1）
 *
 * 要解决的问题：在这之前，"发给模型的那段话"是在 /api/chat 里现拼的 ——
 * 人设拼一段、用户那句话拼一段，拼完就扔。于是：
 *   · 工作区知道的事，聊天区不知道；
 *   · 语音模式和文字模式会演出两种性格；
 *   · 没人说得清某一次请求"到底带了什么上去"。
 *
 * 这个模块把上下文变成**一张有名字的清单**：每一块都有 id、人话标题、来源、
 * 字节数、估算 token、以及"这次有没有被带上"。清单可以打印、可以 diff ——
 * 这是 T60.1 的验收条件，也是唯一能回答"她凭什么这么说"的办法。
 *
 * 设计上的两条硬规矩：
 *
 * 1) **预算不够时裁掉谁，是明写的，不是碰运气。**
 *    每块有优先级；pinned 的块（人设）永远不裁。会话历史从最旧的开始丢。
 *    被裁掉的块不会从清单里消失，只是标成"裁掉"并写明原因 ——
 *    悄悄少带一段上下文，比带不全更可怕，因为没人知道。
 *
 * 2) **带敏感标记的会话轮次，不许跟着上云。**
 *    这是 T61.7 那个隐私洞的延伸：当时修的是"这一句"不许降级上云，
 *    但如果上一句是敏感的、还留在历史里，下一句走云端就把它一起带出去了。
 *    所以每一轮自己记着 sensitive，组装时按目的地过滤。
 */
#ifndef ZCTX_H
#define ZCTX_H

#include <stddef.h>

#define ZCTX_MAX_BLOCKS   16
#define ZCTX_MAX_TURNS    64
#define ZCTX_ID_MAX       32
#define ZCTX_TITLE_MAX    48
#define ZCTX_SRC_MAX      96
#define ZCTX_TURN_MAX     4096

/* 一轮对话。role：0 = 用户说的，1 = 她说的。 */
typedef struct {
    int    role;
    int    sensitive;           /* 1 = 这轮带隐私标记，只许在本地模型之间流转 */
    char   text[ZCTX_TURN_MAX];
} zctx_turn;

/* 一块上下文（人设、系统状态、正在执行的任务…）。
   会话历史不走这里 —— 它是单独的环形缓冲，见下。 */
typedef struct {
    char   id[ZCTX_ID_MAX];
    char   title[ZCTX_TITLE_MAX];
    char   source[ZCTX_SRC_MAX];   /* 哪来的：文件路径 / "内存" / "引擎" */
    char  *text;                   /* 自己 malloc 的副本 */
    size_t len;
    long   tokens;                 /* 估算 */
    int    priority;               /* 越小越先被裁 */
    int    pinned;                 /* 1 = 永不裁 */
    int    kept;                   /* 组装后回填：这次有没有被带上 */
    char   drop_reason[64];        /* kept=0 时写明为什么 */
} zctx_block;

typedef struct {
    zctx_block blocks[ZCTX_MAX_BLOCKS];
    int        nblocks;

    /* 会话历史：环形缓冲。满了从最旧的覆盖 —— 这是"记不住很久以前"的物理上限，
       和下面按 token 预算的裁剪是两回事，两道都要有。 */
    zctx_turn  turns[ZCTX_MAX_TURNS];
    int        nturns;             /* 实际存了几轮（<= ZCTX_MAX_TURNS） */
    int        head;               /* 环形起点 */

    /* 上一次 zctx_build 的结果，供清单打印 */
    long       last_budget;
    long       last_tokens;
    int        last_turns_total;   /* 组装那一刻历史里有几轮（不是"现在"有几轮） */
    int        last_turns_used;
    int        last_turns_dropped;
    int        last_turns_held;    /* 因为敏感而没带上云的轮数 */
    char       last_cap[48];
    int        last_local;         /* 上次组装是按"发往本地"还是"发往云端"算的 */
} zctx;

/* 估算 token。和 zrelay 里那个口径保持一致（4 字节 ≈ 1 token）。
   这是个粗估，但**必须和真正发出去的那段用同一个口径**，否则预算是假的。 */
long zctx_est_tokens(const char *s);

void zctx_init(zctx *c);
void zctx_free(zctx *c);

/* 加一块上下文。同 id 重复加 = 覆盖（人设会随好感档变，每次重算）。
   返回 0 成功。text 会被复制一份，调用方不用保留。 */
int  zctx_set_block(zctx *c, const char *id, const char *title,
                    const char *source, const char *text,
                    int priority, int pinned);

/* 压一轮对话进历史。role：0 用户 / 1 她。sensitive：这轮要不要只留本地。 */
void zctx_push_turn(zctx *c, int role, const char *text, int sensitive);
void zctx_clear_turns(zctx *c);
int  zctx_turn_count(const zctx *c);
/* 按时间顺序取第 i 轮（0 = 最旧）。越界返回 NULL。 */
const zctx_turn *zctx_turn_at(const zctx *c, int i);

/* 组装：按预算决定哪些块进、历史带几轮。
 *   budget_tokens ：<=0 表示不限
 *   local         ：1 = 这次发往本地模型；0 = 发往云端（敏感轮次会被挡下）
 * 组装只做标记和统计，不产出字节 —— 真正拼请求体的是 zrelay。
 * 这样"带了什么"和"怎么拼"分开，清单才能和实际出网的内容对上。
 * 返回实际估算的总 token。 */
long zctx_build(zctx *c, const char *cap, long budget_tokens, int local);

/* 把上一次 zctx_build 的结果打印成清单。**这就是 T60.1 的验收物**：
 * 可打印、可 diff —— 同一个问题在聊天区问和在工作区问，
 * 把两张清单放一起就能看出差在哪。
 * 返回写入的字节数。 */
size_t zctx_manifest(const zctx *c, char *out, size_t cap);

/* 组装后，第 i 块是否被带上（给 zrelay / 单测用） */
const zctx_block *zctx_block_at(const zctx *c, int i);
int  zctx_block_count(const zctx *c);
/* 按 id 找块；没有返回 NULL */
const zctx_block *zctx_block_find(const zctx *c, const char *id);

/* 上一次 build 判定为"要带上"的历史轮次：第 i 条（0 = 最旧）。
   没有更多返回 NULL。这是 zrelay 拼 messages 数组时真正要遍历的东西。 */
const zctx_turn *zctx_kept_turn_at(const zctx *c, int i);
int  zctx_kept_turn_count(const zctx *c);

#endif /* ZCTX_H */
