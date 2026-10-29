#include "edge_ring.h"

#define MASK (EMU_EDGE_RING - 1u)

void emu_edge_reset(emu_edge_ring_t *r)
{
    r->head = r->tail = 0;
    r->overflows = 0;
}

int emu_edge_push(emu_edge_ring_t *r, uint32_t t, uint16_t gates)
{
    uint32_t h = r->head;
    if (h - r->tail >= EMU_EDGE_RING) {
        r->overflows++;
        return -1;
    }
    r->e[h & MASK].t = t;
    r->e[h & MASK].gates = gates;
    __asm__ volatile("" ::: "memory");     /* the entry is written before the consumer can see it */
    r->head = h + 1;
    return 0;
}

uint64_t emu_clock_extend(uint64_t prev, uint32_t now32)
{
    return prev + (uint32_t)(now32 - (uint32_t)prev);
}

int emu_edge_take(emu_edge_ring_t *r, uint64_t now64, uint64_t t1, srm_edge_t *out, int max)
{
    uint32_t t = r->tail;
    const uint32_t h = r->head;
    __asm__ volatile("" ::: "memory");
    int n = 0;
    while (t != h && n < max) {
        const emu_raw_edge_t *e = &r->e[t & MASK];
        uint64_t te = now64 + (int64_t)(int32_t)(e->t - (uint32_t)now64);
        if (te >= t1) break;
        out[n].t = te;
        out[n].gates = e->gates;
        n++;
        t++;
    }
    __asm__ volatile("" ::: "memory");
    r->tail = t;
    return n;
}

uint16_t emu_gate_word(uint32_t psr)
{
    return (uint16_t)(((psr >> 18) & 1u) | ((psr >> 19) & 1u) << 1 | ((psr >> 23) & 1u) << 2 |
                      ((psr >> 22) & 1u) << 3 | ((psr >> 17) & 1u) << 8 | ((psr >> 16) & 1u) << 9 |
                      ((psr >> 26) & 1u) << 10 | ((psr >> 27) & 1u) << 11);
}

void emu_pattern_init(emu_pattern_t *p, uint64_t t_on, uint64_t period, uint64_t on, uint16_t word)
{
    p->next = t_on;
    p->period = period;
    p->on = on;
    p->word = word;
    p->high = 0;
}

int emu_pattern_feed(emu_pattern_t *p, emu_edge_ring_t *r, uint64_t t1)
{
    int n = 0;
    while (p->next < t1) {
        emu_edge_push(r, (uint32_t)p->next, p->high ? 0 : p->word);
        p->next += p->high ? p->period - p->on : p->on;
        p->high = !p->high;
        n++;
    }
    return n;
}
