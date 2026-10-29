/* Exports of the emulator's portable edge bookkeeping for the tests. */
#include "edge_ring.h"

#if defined(_WIN32)
#define EXPORT __declspec(dllexport)
#else
#define EXPORT
#endif

static emu_edge_ring_t ring;
static emu_pattern_t pattern;

EXPORT void shim_reset(void) { emu_edge_reset(&ring); }
EXPORT int shim_push(uint32_t t, uint16_t gates) { return emu_edge_push(&ring, t, gates); }
EXPORT uint64_t shim_extend(uint64_t prev, uint32_t now32) { return emu_clock_extend(prev, now32); }
EXPORT uint16_t shim_gate_word(uint32_t psr) { return emu_gate_word(psr); }
EXPORT uint32_t shim_overflows(void) { return ring.overflows; }

/* Takes the edges before t1 into t_out/g_out (at most max); returns the count. */
EXPORT int shim_take(uint64_t now64, uint64_t t1, uint64_t *t_out, uint16_t *g_out, int max)
{
    srm_edge_t e[64];
    int n = emu_edge_take(&ring, now64, t1, e, max < 64 ? max : 64);
    for (int i = 0; i < n; i++) {
        t_out[i] = e[i].t;
        g_out[i] = e[i].gates;
    }
    return n;
}

EXPORT void shim_pattern_init(uint64_t t_start, uint64_t period, uint64_t on, uint16_t word)
{
    emu_pattern_init(&pattern, t_start, period, on, word);
}
EXPORT int shim_pattern_feed(uint64_t t1) { return emu_pattern_feed(&pattern, &ring, t1); }
