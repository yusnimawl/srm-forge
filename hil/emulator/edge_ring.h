/* Portable step bookkeeping of the emulator: the gate-edge ring between the gate interrupt (producer) and the step
 * interrupt (consumer), the 64-bit extension of the 32-bit cycle counter, the GPIO6 to gate-word mapping and the
 * software test pattern. No Arduino dependency, so it is tested on the host. */
#ifndef EDGE_RING_H
#define EDGE_RING_H

#include <stdint.h>

#include "srm_gate_avg.h"

#define EMU_EDGE_RING 256    /* entries, a power of two */

typedef struct {
    uint32_t t;              /* cycle counter at the edge */
    uint16_t gates;
} emu_raw_edge_t;

/* Single producer, single consumer: head is written only by emu_edge_push, tail only by emu_edge_take. */
typedef struct {
    volatile uint32_t head, tail;
    volatile uint32_t overflows;
    emu_raw_edge_t e[EMU_EDGE_RING];
} emu_edge_ring_t;

/* A gate pattern of one word: on at t_on + m * period, off on ticks later (64-bit cycle times). */
typedef struct {
    uint64_t next, period, on;
    uint16_t word;
    int high;
} emu_pattern_t;

#ifdef __cplusplus
extern "C" {
#endif

void emu_edge_reset(emu_edge_ring_t *r);
/* Appends an edge; 0 ok, -1 when the ring is full (counted in overflows, the edge is lost). */
int emu_edge_push(emu_edge_ring_t *r, uint32_t t, uint16_t gates);
/* The 64-bit time of the counter value now32, given a 64-bit time prev at most 2^32 - 1 cycles earlier. */
uint64_t emu_clock_extend(uint64_t prev, uint32_t now32);
/* Removes the edges stamped before t1, oldest first, into out (at most max) as 64-bit times; edges at or after t1
 * stay for a later window. Each stamp is extended to the 64-bit time nearest now64, so stamps must lie within
 * 2^31 cycles of now64 (an edge stamped just after now64 was read stays). Returns the count. */
int emu_edge_take(emu_edge_ring_t *r, uint64_t now64, uint64_t t1, srm_edge_t *out, int max);
/* Gate word (bit k upper of phase k, bit 8 + k lower) from the GPIO6 data register: Teensy pins 14..21. */
uint16_t emu_gate_word(uint32_t psr);
void emu_pattern_init(emu_pattern_t *p, uint64_t t_on, uint64_t period, uint64_t on, uint16_t word);
/* Pushes the pattern's edges before t1 into the ring; returns the count. */
int emu_pattern_feed(emu_pattern_t *p, emu_edge_ring_t *r, uint64_t t1);

#ifdef __cplusplus
}
#endif

#endif
