#include "ga_selfcheck.h"

#include <string.h>

#include "srm_gate_avg.h"

#define N_WINDOWS 4000
#define TICKS 5040u              /* one 5 us step at 1008 MHz */

/* Fills the stack below the caller's frame with a pattern, so the averager called next from the same frame starts on
   non-zero memory: a build that reads uninitialised stack then gives a different hash. */
#if defined(__GNUC__)
__attribute__((noinline))
#endif
static void scrub_stack(uint8_t pattern)
{
    volatile uint8_t b[2048];
    for (int j = 0; j < (int)sizeof b; j++) b[j] = (uint8_t)(pattern + j);
}

static uint32_t fnv(uint32_t h, uint32_t x)
{
    for (int b = 0; b < 4; b++) h = (h ^ ((x >> (8 * b)) & 0xFFu)) * 16777619u;
    return h;
}

static uint32_t bits(srm_real_t x)
{
    float f = (float)x;
    uint32_t u;
    memcpy(&u, &f, sizeof u);
    return u;
}

/* The windows: 4 phases at 400 V with the default converter delays (rise 605, fall 202 ticks); each window draws up
   to 3 edges that toggle the switches of two neighbouring phases (one edge in 16 stamped up to 200 ticks before the
   window, as a late edge), and fresh fluxes, a quarter of them zero; the stack below is scrubbed before every
   window. */
uint32_t emu_ga_selfcheck(void)
{
    srm_sim_config_t c;
    memset(&c, 0, sizeof c);
    c.n_phases = 4;
    c.bus_voltage = 400.0;
    c.v_switch = 1.0;
    c.v_diode = 1.0;
    c.dt = 5e-6;
    srm_gate_avg_t g;
    srm_gate_avg_init(&g, 605, 202, 0);
    uint32_t lcg = 12345u, h = 2166136261u;
    uint16_t word = 0;
    for (uint32_t w = 0; w < N_WINDOWS; w++) {
        const uint64_t t0 = 1000000u + (uint64_t)w * TICKS;
        const int ph = (int)(w / 250u) % 4, ph2 = (ph + 1) % 4;
        const uint16_t mask = (uint16_t)((1u << ph) | (1u << ph2) | (1u << (8 + ph)) | (1u << (8 + ph2)));
        srm_edge_t ed[3];
        int n = 0;
        uint64_t last = 0;
        for (int j = 0; j < 3; j++) {
            lcg = lcg * 1664525u + 1013904223u;
            if ((lcg >> 28) >= 7) continue;
            const uint32_t off = (lcg >> 8) % TICKS;
            uint64_t t = t0 + off;
            if (n == 0 && ((lcg >> 4) & 15u) == 0) t = t0 - 1 - off % 200u;
            if (t < last) t = last;
            last = t;
            word = (uint16_t)((word ^ (1u << ((lcg >> 2) & 1u ? ph2 : ph)) ^ (((lcg >> 3) & 1u) << (8 + ph))) & mask);
            ed[n].t = t;
            ed[n].gates = word;
            n++;
        }
        srm_real_t psi0[SRM_SIM_MAX_PHASES], v[SRM_SIM_MAX_PHASES];
        for (int k = 0; k < 4; k++) {
            lcg = lcg * 1664525u + 1013904223u;
            psi0[k] = (lcg >> 30) == 0 ? (srm_real_t)0 : (srm_real_t)((lcg >> 8) % 4096u) * (srm_real_t)1e-5;
        }
        scrub_stack((uint8_t)(0xA5u ^ w));
        srm_gate_avg_window(&g, &c, ed, n, t0, TICKS, psi0, v, NULL, NULL);
        for (int k = 0; k < 4; k++) h = fnv(h, bits(v[k]));
        h = fnv(h, (uint32_t)g.eff | (uint32_t)g.pending_valid << 16);
    }
    return h;
}
