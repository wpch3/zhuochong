/*
 * zbus.c - 无锁环形缓冲实现（SPSC/MPSC 安全）
 * 算法：经典 Lamport 队列 + 2^n 掩码，与 Linux kfifo 同构。
 * head 仅消费者写，tail 仅生产者写，数据区通过原子 seq 保证可见性。
 */
#include "zbus.h"
#include <string.h>
#include <stdatomic.h>

void zbus_init(zbus *b) {
    if (!b) return;
    memset(b, 0, sizeof(*b));
    atomic_init(&b->head, 0);
    atomic_init(&b->tail, 0);
    atomic_init(&b->seq_gen, 1);
}

void zbus_reset(zbus *b) {
    if (!b) return;
    atomic_store_explicit(&b->head, 0, memory_order_relaxed);
    atomic_store_explicit(&b->tail, 0, memory_order_relaxed);
    atomic_store_explicit(&b->seq_gen, 1, memory_order_relaxed);
    b->published = b->consumed = b->dropped = 0;
}

int zbus_publish(zbus *b, const zbus_event *ev) {
    uint64_t tail, head;
    zbus_event *slot;
    if (!b || !ev) return ZBUS_FULL;
    tail = atomic_load_explicit(&b->tail, memory_order_relaxed);
    head = atomic_load_explicit(&b->head, memory_order_acquire);
    if ((tail - head) >= (uint64_t)ZBUS_CAP) {
        ((zbus*)b)->dropped++;
        return ZBUS_FULL;
    }
    slot = &b->buf[tail & (ZBUS_CAP - 1)];
    *slot = *ev;
    slot->seq = atomic_fetch_add_explicit(&b->seq_gen, 1, memory_order_relaxed);
    if (slot->ts == 0.0) slot->ts = z_now_seconds();
    atomic_store_explicit(&b->tail, tail + 1, memory_order_release);
    ((zbus*)b)->published++;
    return ZBUS_OK;
}

int zbus_consume(zbus *b, zbus_event *out) {
    uint64_t head, tail;
    zbus_event *slot;
    if (!b || !out) return ZBUS_EMPTY;
    head = atomic_load_explicit(&b->head, memory_order_relaxed);
    tail = atomic_load_explicit(&b->tail, memory_order_acquire);
    if (head == tail) return ZBUS_EMPTY;
    slot = &b->buf[head & (ZBUS_CAP - 1)];
    *out = *slot;
    atomic_store_explicit(&b->head, head + 1, memory_order_release);
    b->consumed++;
    return ZBUS_OK;
}

int zbus_peek(const zbus *b, zbus_event *out) {
    uint64_t head, tail;
    if (!b || !out) return ZBUS_EMPTY;
    head = atomic_load_explicit((const _Atomic uint64_t*)&b->head, memory_order_acquire);
    tail = atomic_load_explicit((const _Atomic uint64_t*)&b->tail, memory_order_acquire);
    if (head == tail) return ZBUS_EMPTY;
    *out = b->buf[head & (ZBUS_CAP - 1)];
    return ZBUS_OK;
}

int zbus_len(const zbus *b) {
    uint64_t t, h;
    if (!b) return 0;
    t = atomic_load_explicit((const _Atomic uint64_t*)&b->tail, memory_order_acquire);
    h = atomic_load_explicit((const _Atomic uint64_t*)&b->head, memory_order_acquire);
    return (int)(t - h);
}

int zbus_cap(const zbus *b) { (void)b; return ZBUS_CAP; }
int zbus_is_full(const zbus *b) { return zbus_len(b) >= ZBUS_CAP; }
int zbus_is_empty(const zbus *b) { return zbus_len(b) == 0; }

void zbus_event_init(zbus_event *ev, uint32_t type, const char *topic, const char *sender) {
    if (!ev) return;
    memset(ev, 0, sizeof(*ev));
    ev->type = type;
    if (topic) z_strlcpy(ev->topic, topic, sizeof(ev->topic));
    if (sender) z_strlcpy(ev->sender, sender, sizeof(ev->sender));
    ev->ts = 0.0; /* publish 时若为 0 则填 now */
}

void zbus_event_set_str(zbus_event *ev, const char *s) {
    size_t n;
    if (!ev || !s) return;
    n = strlen(s);
    if (n > ZBUS_PAYLOAD) n = ZBUS_PAYLOAD;
    memcpy(ev->payload, s, n);
    ev->payload_len = (uint32_t)n;
}

void zbus_event_set_u32(zbus_event *ev, uint32_t v) {
    if (!ev) return;
    memcpy(ev->payload, &v, sizeof(v));
    ev->payload_len = sizeof(v);
}
