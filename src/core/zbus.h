/*
 * zbus.h - 无锁事件总线（Lock-Free Ring Buffer，铁律一/三）
 *
 * 解决：渲染 60FPS（zrig_frame）与 AI 推理/桌面抓图抢同一把 g_lock，
 *       chat 想 6 秒 → 立绘冻 6 秒（2026-10-24 实测）。根因双层：
 *         ① g_lock 被慢请求攥着跨网往返
 *         ② HTTP 单线程 accept 同时兼做 tick
 *       已做第一层拆分（g_lock / g_ai_lock），本层做第二层——
 *       彻底的无锁化：生产者（AI/桌面/输入）与消费者（渲染/逻辑）只碰原子头尾。
 *
 * 设计：
 *   - SPSC 变体可扩 MPSC：头尾各一条原子计数，数据区预分配 2^n 环。
 *   - 事件为定长 256 字节（含 64 字节 payload），publish 时拷贝，不持有指针。
 *   - 无锁但有界：满时返回 ZBUS_FULL，调用方自行丢弃或退避，不阻塞渲染。
 *   - C11 atomics（memory_order_acq_rel），x86 上编译成 lock xadd，ARM 上 dmb。
 *   - 测试口径：单线程 vs 双线程并发 10 万条不丢不重，且快于 mutex 版。
 */
#ifndef ZBUS_H
#define ZBUS_H

#include "zc.h"
#include <stdatomic.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define ZBUS_CAP 1024          /* 必须 2 的幂 */
#define ZBUS_PAYLOAD 64
#define ZBUS_TOPIC_MAX 32
#define ZBUS_SENDER_MAX 32

typedef enum {
    ZBUS_EVT_TICK = 1,         /* 帧心跳（渲染侧发出，其他模块跟随） */
    ZBUS_EVT_ACTION = 2,       /* 动作请求 {action_id} */
    ZBUS_EVT_POSE = 3,
    ZBUS_EVT_PHYS = 4,         /* 物理推力事件 */
    ZBUS_EVT_CUSTOM = 100,     /* 模块自定义起点 */
} zbus_type;

typedef struct {
    uint32_t type;                      /* zbus_type */
    uint32_t seq;                       /* 发布序号（单调） */
    double   ts;                        /* 发布时刻（monotonic 秒） */
    char     topic[ZBUS_TOPIC_MAX];     /* 路由键，如 "pet/action" */
    char     sender[ZBUS_SENDER_MAX];   /* 发送者模块名 */
    uint8_t  payload[ZBUS_PAYLOAD];    /* 定长载荷（小事件内联，大事件走共享句柄） */
    uint32_t payload_len;              /* 实际长度 0..64 */
    uint32_t _pad;
} zbus_event;

#define ZBUS_OK      0
#define ZBUS_FULL   -1
#define ZBUS_EMPTY  -2

typedef struct {
    zbus_event buf[ZBUS_CAP];
    _Atomic uint64_t head;     /* 消费者已读位置 */
    _Atomic uint64_t tail;     /* 生产者已写位置 */
    _Atomic uint32_t seq_gen;  /* 序号生成器 */
    /* 统计（非原子快照，仅 debug 用） */
    uint64_t published;
    uint64_t consumed;
    uint64_t dropped;
} zbus;

/* 生命周期 */
void zbus_init(zbus *b);
void zbus_reset(zbus *b);

/* 发布/消费（线程安全，任意线程可调 publish，任意线程可调 consume） */
int  zbus_publish(zbus *b, const zbus_event *ev);          /* 0 成功，-1 满 */
int  zbus_consume(zbus *b, zbus_event *out);               /* 0 成功，-2 空 */
int  zbus_peek(const zbus *b, zbus_event *out);            /* 看一眼不消费 */

/* 容量/水位（快照，不加锁） */
int  zbus_len(const zbus *b);
int  zbus_cap(const zbus *b);
int  zbus_is_full(const zbus *b);
int  zbus_is_empty(const zbus *b);

/* 便捷构造 */
void zbus_event_init(zbus_event *ev, uint32_t type, const char *topic, const char *sender);
void zbus_event_set_str(zbus_event *ev, const char *s);
void zbus_event_set_u32(zbus_event *ev, uint32_t v);

#ifdef __cplusplus
}
#endif
#endif
